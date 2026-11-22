# Giới hạn kích thước chuỗi, MAX_STRING_SIZE và tương thích phiên bản

Trong Oracle Database, câu hỏi “một cột `VARCHAR2` chứa được bao nhiêu ký tự?” không có một đáp án duy nhất. Giới hạn thực tế phụ thuộc vào **kiểu dữ liệu**, **số byte**, **bộ ký tự**, **khai báo `BYTE` hay `CHAR`**, **giá trị `MAX_STRING_SIZE`**, và việc giá trị được xử lý trong **SQL hay PL/SQL**. Một câu lệnh hoạt động trên Oracle mới cũng có thể thất bại khi triển khai lên database cũ hoặc khi chuyển dữ liệu sang hệ thống đang ở chế độ `STANDARD`.

Bài học hướng dẫn cách đọc giới hạn của các kiểu chuỗi Oracle, kiểm tra cấu hình của database/PDB hiện tại, chọn kiểu phù hợp cho dữ liệu dài và nhận diện rủi ro tương thích. Ví dụ sử dụng SQL*Plus/SQLcl và các câu SQL có thể chạy trong schema thực hành được cấp quyền; phần thay đổi cấu hình hệ thống chỉ được **giải thích**, không yêu cầu người học tự chạy lệnh nâng cấp database.

## 1. Ba giới hạn khác nhau thường bị nhầm

Hãy phân biệt ba câu hỏi:

1. **Một cột được khai báo tối đa bao nhiêu byte?** Đây là giới hạn mà Oracle chấp nhận khi tạo cột và lưu giá trị.
2. **Một giá trị hiện tại có bao nhiêu ký tự và bao nhiêu byte?** Tùy dữ liệu, hai con số có thể khác nhau, nhất là với UTF-8.
3. **Một biến PL/SQL, biểu thức SQL hoặc kết quả hàm có thể chứa bao nhiêu byte?** Khả năng của từng ngữ cảnh có thể không trùng giới hạn cột SQL.

Ví dụ trên database dùng `AL32UTF8`:

~~~text
Chuỗi       Số ký tự hiển thị      Byte UTF-8 (minh họa)
-----       -----------------     ----------------------
ABC         3                     3
Hà          2                     3
Tiếng       5                     7
ộ           1                     3
😀          1 Unicode code point   4
~~~

Ở đây `Hà` gồm `H` (1 byte) và `à` (2 byte); `Tiếng` gồm `T`, `i`, `ế`, `n`, `g` nên tổng 7 byte với Unicode dựng sẵn (*precomposed*). Nếu chuỗi có dấu được biểu diễn dưới dạng ký tự cơ sở cộng dấu kết hợp, số byte/độ dài tính theo hàm cũng có thể khác. Vì vậy không thể lấy “100 ký tự” rồi mặc định thành “100 byte”.

~~~mermaid
flowchart TD
    A["Chuỗi từ ứng dụng"] --> B{"Kiểu cột nào?"}
    B --> C["VARCHAR2 / CHAR: database character set"]
    B --> D["NVARCHAR2 / NCHAR: national character set"]
    B --> E["CLOB / NCLOB: dữ liệu ký tự lớn"]
    C --> F["BYTE hay CHAR semantics + MAX_STRING_SIZE"]
    D --> G["National charset + MAX_STRING_SIZE"]
    E --> H["LOB API, lưu trữ và thao tác phù hợp"]
    F --> I["Kiểm tra byte thực tế so với giới hạn cột"]
    G --> I
~~~

## 2. Bảng giới hạn cần nhớ: STANDARD và EXTENDED

Tham số khởi tạo `MAX_STRING_SIZE` kiểm soát mức tối đa của ba kiểu **`VARCHAR2`, `NVARCHAR2`, `RAW` trong SQL**, từ các phiên bản Oracle hỗ trợ tính năng mở rộng này. Hai giá trị quan trọng là `STANDARD` và `EXTENDED`.

| Kiểu SQL | `MAX_STRING_SIZE = STANDARD` | `MAX_STRING_SIZE = EXTENDED` | Ghi chú |
|---|---:|---:|---|
| `VARCHAR2` | Tối đa **4.000 byte** | Tối đa **32.767 byte** | Chịu ảnh hưởng database character set và `BYTE`/`CHAR` |
| `NVARCHAR2` | Tối đa **4.000 byte** | Tối đa **32.767 byte** | Khai báo kích thước theo ký tự; giới hạn byte vẫn áp dụng |
| `RAW` | Tối đa **2.000 byte** | Tối đa **32.767 byte** | Dữ liệu nhị phân, không phải chuỗi ký tự |
| `CHAR` | Tối đa **2.000 byte** | Vẫn **2.000 byte** | Kiểu độ dài cố định; không được mở rộng nhờ tham số này |
| `NCHAR` | Phụ thuộc national character set, tối đa theo giới hạn byte của kiểu | Không được mở rộng lên 32.767 như `NVARCHAR2` | Độ dài cố định, có quy tắc riêng |
| `CLOB` / `NCLOB` | Dữ liệu ký tự lớn | Dữ liệu ký tự lớn | Là LOB, **không dùng giới hạn 4.000/32.767 byte của `VARCHAR2`** |

**32.767 là số byte tối đa, không phải lời hứa rằng 32.767 ký tự Unicode bất kỳ đều vừa.** Chẳng hạn một chuỗi toàn ký tự UTF-8 4 byte chỉ chứa được khoảng 8.191 ký tự trong 32.767 byte, chưa tính các giới hạn khác của loại dữ liệu và phép toán. Với `AL16UTF16`, dữ liệu `NVARCHAR2` thường tiêu thụ ít nhất 2 byte cho đơn vị ký tự cơ bản, và ký tự bổ sung có thể cần 4 byte.

`RAW` nằm trong bảng để thấy phạm vi tác động của `MAX_STRING_SIZE`, nhưng `RAW` là byte nhị phân, không chịu ý nghĩa độ dài “ký tự tiếng Việt”. Chọn `RAW` cho dữ liệu binary có cấu trúc phù hợp; dữ liệu binary lớn thường cân nhắc `BLOB`.

### 2.1 Vì sao kiểu `VARCHAR2(4000 CHAR)` chưa chắc lưu được 4.000 ký tự?

Giả sử database dùng `AL32UTF8`, và một cột đã được khai báo:

~~~sql
CREATE TABLE lab_length_semantics (
    id            NUMBER PRIMARY KEY,
    value_bytes   VARCHAR2(100 BYTE),
    value_chars   VARCHAR2(100 CHAR)
);
~~~

- `VARCHAR2(100 BYTE)` là giới hạn tối đa 100 **byte**. Có thể chứa 100 chữ ASCII, nhưng một số chuỗi 100 ký tự tiếng Việt sẽ vượt 100 byte.
- `VARCHAR2(100 CHAR)` biểu đạt mục tiêu tối đa 100 **ký tự** theo ngữ nghĩa Oracle; với `AL32UTF8`, dữ liệu nhiều byte vẫn phải nằm trong giới hạn byte thực tế của kiểu/cột.
- `MAX_STRING_SIZE` quyết định **trần byte SQL**: 4.000 ở `STANDARD` hoặc 32.767 ở `EXTENDED`. Viết `CHAR` không cho phép vượt trần đó.

`NLS_LENGTH_SEMANTICS` ảnh hưởng ngữ nghĩa độ dài mặc định của các khai báo ký tự phù hợp khi không ghi `BYTE` hoặc `CHAR`:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_LENGTH_SEMANTICS';
~~~

Vì thế trong DDL nghiệp vụ, nên ghi rõ `VARCHAR2(n BYTE)` hoặc `VARCHAR2(n CHAR)` để giảm phụ thuộc vào thiết lập môi trường. `NLS_LENGTH_SEMANTICS` không đổi định nghĩa các cột đã tồn tại; `NVARCHAR2` dùng ngữ nghĩa độ dài theo ký tự riêng của nó.

### 2.2 Xem ký tự và byte thực tế

~~~sql
SELECT LENGTH('ABC') AS ascii_characters,
       LENGTHB('ABC') AS ascii_bytes,
       LENGTH(UNISTR('\1ED9')) AS unicode_characters,
       LENGTHB(CAST(UNISTR('\1ED9') AS VARCHAR2(10 CHAR)))
           AS unicode_bytes_in_db_charset
FROM dual;
~~~

`UNISTR('\1ED9')` tạo ký tự `ộ` bằng escape Unicode để tránh phụ thuộc vào cách terminal đọc script có dấu. Khi database dùng `AL32UTF8`, `ộ` (U+1ED9) chiếm **3 byte** sau khi chuyển sang `VARCHAR2`. Nếu database dùng bộ ký tự khác, số byte hoặc khả năng biểu diễn có thể khác. `LENGTH` và `LENGTHB` giúp quan sát hai khái niệm độc lập; đừng chỉ nhìn độ dài chữ do giao diện hiển thị.

Có thể xem biểu diễn hex của giá trị theo character set:

~~~sql
SELECT DUMP(
           CAST(UNISTR('\1ED9') AS VARCHAR2(10 CHAR)),
           1016
       ) AS bytes_hex
FROM dual;
~~~

## 3. SQL và PL/SQL có giới hạn khác nhau

Một tình huống dễ gây nhầm:

~~~sql
DECLARE
    v_text VARCHAR2(32767);
BEGIN
    v_text := RPAD('X', 5000, 'X');
    DBMS_OUTPUT.PUT_LINE('PL/SQL length = ' || LENGTH(v_text));
END;
/
~~~

Khối PL/SQL này có thể giữ chuỗi 5.000 ký tự ASCII trong biến `VARCHAR2` vì **biến `VARCHAR2` trong PL/SQL hỗ trợ tối đa 32.767 byte**, ngay cả khi SQL/database đang dùng `MAX_STRING_SIZE = STANDARD`. Tuy nhiên điều đó **không cho phép** chèn tự động 5.000 byte vào một cột SQL `VARCHAR2(4000 BYTE)`.

Nếu tiếp tục:

~~~sql
-- DDL cho ví dụ ở chế độ STANDARD:
CREATE TABLE lab_sql_limit (
    id      NUMBER PRIMARY KEY,
    payload VARCHAR2(4000 BYTE)
);
~~~

và cố insert `v_text` dài 5.000 byte, giá trị vượt giới hạn cột và Oracle sẽ từ chối. Điều quan trọng là **không nhầm giới hạn biến PL/SQL với giới hạn lưu trữ kiểu SQL**.

| Nơi giá trị sống | Trần cần quan tâm |
|---|---|
| Biến `VARCHAR2` trong PL/SQL | Tối đa **32.767 byte** cho biến PL/SQL |
| Cột `VARCHAR2` trong SQL chế độ `STANDARD` | Tối đa **4.000 byte** |
| Cột `VARCHAR2` trong SQL chế độ `EXTENDED` | Tối đa **32.767 byte** |
| Biến/giá trị `CLOB` | Thiết kế cho dữ liệu ký tự lớn hơn nhiều; dùng API/hàm LOB |
| Biểu thức/hàm SQL trả về `VARCHAR2` | Chịu trần kích thước SQL của kiểu và quy tắc hàm cụ thể; không mặc định thành CLOB |

Một số lỗi xảy ra ở **biểu thức**, trước cả khi ghi dữ liệu. Ví dụ ghép nhiều chuỗi bằng toán tử `||` có thể gặp `ORA-01489: result of string concatenation is too long` nếu kết quả vượt giới hạn biểu thức chuỗi SQL đang áp dụng. `LISTAGG` cũng cần xử lý giới hạn trả về; ở các phiên bản hỗ trợ `ON OVERFLOW TRUNCATE` có thể chủ động chọn cắt kết quả thay vì phát sinh lỗi. Khi yêu cầu trả toàn bộ văn bản rất dài, nên dùng đường xử lý trả về `CLOB` phù hợp thay vì giả định tất cả hàm SQL sẽ tự mở rộng độ dài.

## 4. Cách đọc MAX_STRING_SIZE đang có hiệu lực

Trước khi thử khai báo `VARCHAR2(32767)`, phải **xem database thật đang ở chế độ nào**. Trong SQL*Plus hoặc SQLcl với quyền thích hợp:

~~~sql
SHOW PARAMETER max_string_size
~~~

Hoặc câu SQL:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'max_string_size';
~~~

Kết quả minh họa:

~~~text
NAME             VALUE
---------------- --------
max_string_size  STANDARD
~~~

Nếu `STANDARD`, **không tạo** cột `VARCHAR2(32767 BYTE)` và kỳ vọng thành công. Nếu `EXTENDED`, có thể thử DDL mở rộng trong schema thực hành nhưng vẫn phải lưu ý giới hạn byte, loại cột và khả năng hỗ trợ ở các hệ thống khác.

### 4.1 Xác định đúng phiên bản, database và PDB trước khi so sánh

~~~sql
SELECT banner
FROM v$version;

SELECT instance_name, version
FROM v$instance;

SELECT name, cdb, open_mode
FROM v$database;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
~~~

`MAX_STRING_SIZE` có ý nghĩa từ các bản Oracle Database hỗ trợ extended SQL strings, được giới thiệu trong dòng **Oracle Database 12c**. Khi làm việc với phiên bản, bản vá hoặc kiến trúc CDB/PDB cụ thể, phải tra tài liệu tương ứng; không chỉ dựa vào lời quảng cáo “Oracle 12c+” để xác nhận cấu hình đã bật.

Trong CDB, cần xem **thiết lập của container nơi ứng dụng thực sự chạy**. Một CDB root và các PDB có thể khác nhau về trạng thái chuyển đổi metadata/quy trình nâng cấp. Việc đặt cấu hình ở root không đủ để suy rằng mọi PDB cũ/mới đều sẵn sàng lưu 32.767 byte. Đối với một PDB cụ thể, hãy **kết nối đúng service PDB** rồi đọc `V$PARAMETER` trong phạm vi được hỗ trợ; người quản trị cần đối chiếu toàn bộ quy trình multitenant của phiên bản đó.

### 4.2 Xem character set của database

~~~sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET')
ORDER BY parameter;
~~~

Ví dụ thường gặp:

~~~text
NLS_CHARACTERSET        AL32UTF8
NLS_NCHAR_CHARACTERSET  AL16UTF16
~~~

- `VARCHAR2` sử dụng database character set, ở đây `AL32UTF8`.
- `NVARCHAR2` sử dụng national character set, ở đây `AL16UTF16`.
- Cả hai vẫn chịu trần **byte** tương ứng với `MAX_STRING_SIZE`.

Việc có Unicode support không đồng nghĩa đã bật extended strings. `AL32UTF8` và `MAX_STRING_SIZE` giải quyết **hai câu hỏi khác nhau**: có thể biểu diễn ký tự nào, và giá trị dài tối đa bao nhiêu byte.

### 4.3 Nếu không có quyền xem V$ view

Tài khoản ứng dụng có thể nhận `ORA-00942` hoặc `ORA-01031` khi truy vấn `V$PARAMETER`. Đó thường là vấn đề quyền xem metadata. Nên dùng tài khoản giám sát được phép hoặc đề nghị DBA cung cấp kết quả; không cấp quyền hệ thống rộng chỉ để làm bài thực hành.

Ngoài cấu hình instance, bạn có thể **đọc metadata cột mình truy cập được** để biết giới hạn cột hiện tại mà không cần quyền quản trị toàn database:

~~~sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length,
       char_used,
       char_length
FROM all_tab_columns
WHERE owner = 'APP_OWNER'
  AND table_name = 'CUSTOMER_NOTES'
ORDER BY column_id;
~~~

`DATA_LENGTH` là kích thước tối đa tính theo **byte** của kiểu cột; `CHAR_LENGTH` và `CHAR_USED` cho biết ngữ nghĩa ký tự khi áp dụng (`C` cho character semantics, `B` cho byte semantics). `ALL_TAB_COLUMNS` chỉ cho thấy các object mà user được quyền quan sát. Cần biết cả **giới hạn cột** và **chế độ database** nếu đang phân tích một thiết kế có thể triển khai ở nhiều môi trường.

## 5. Một thử nghiệm được chia đúng theo STANDARD và EXTENDED

Không chạy thử DDL vượt khả năng database production chỉ để “xem có lỗi hay không”. Trước hết xem `MAX_STRING_SIZE`, xác định schema thực hành được phép tạo bảng rồi chọn nhánh phù hợp.

### 5.1 Nhánh chạy được trong cả hai chế độ: giới hạn 100 BYTE/CHAR

~~~sql
CREATE TABLE lab_string_semantics (
    id          NUMBER PRIMARY KEY,
    text_bytes  VARCHAR2(100 BYTE),
    text_chars  VARCHAR2(100 CHAR)
);

INSERT INTO lab_string_semantics (id, text_bytes, text_chars)
VALUES (1, 'Hello', UNISTR('Ti\1EBFng Vi\1EC7t'));

COMMIT;

SELECT id,
       LENGTH(text_bytes) AS bytes_col_char_count,
       LENGTHB(text_bytes) AS bytes_col_byte_count,
       LENGTH(text_chars) AS chars_col_char_count,
       LENGTHB(text_chars) AS chars_col_byte_count
FROM lab_string_semantics;
~~~

Kết quả không nhất thiết giống nhau giữa character set và dữ liệu khác nhau. Để kiểm tra giới hạn thật của cột vừa tạo:

~~~sql
SELECT column_name, data_type, data_length, char_length, char_used
FROM user_tab_columns
WHERE table_name = 'LAB_STRING_SEMANTICS'
ORDER BY column_id;
~~~

Trong ví dụ này, cả hai cột chỉ dùng tối đa 100 đơn vị khai báo và dữ liệu thử nhỏ, nên không cần extended strings. Mục đích là nhìn thấy **metadata `BYTE`/`CHAR`** và khác biệt giữa `LENGTH` với `LENGTHB`.

### 5.2 Nhánh chỉ dùng nếu database/PDB đã bật EXTENDED

Với `MAX_STRING_SIZE = EXTENDED` trong môi trường thực hành:

~~~sql
CREATE TABLE lab_extended_string (
    id      NUMBER PRIMARY KEY,
    payload VARCHAR2(32767 BYTE)
);
~~~

Chèn một chuỗi 5.000 ký tự ASCII qua PL/SQL:

~~~sql
DECLARE
    v_payload VARCHAR2(32767);
BEGIN
    v_payload := RPAD('X', 5000, 'X');
    INSERT INTO lab_extended_string (id, payload)
    VALUES (1, v_payload);
    COMMIT;
END;
/

SELECT id,
       LENGTH(payload) AS char_count,
       LENGTHB(payload) AS byte_count
FROM lab_extended_string;
~~~

Với dữ liệu thử này, `CHAR_COUNT` và `BYTE_COUNT` đều dự kiến là 5.000 vì toàn ký tự ASCII. Với tiếng Việt hoặc ký tự Unicode nhiều byte, hai số có thể khác; trần SQL vẫn là **32.767 byte**.

Để xác minh metadata:

~~~sql
SELECT column_name, data_type, data_length, char_length, char_used
FROM user_tab_columns
WHERE table_name = 'LAB_EXTENDED_STRING';
~~~

### 5.3 Điều gì xảy ra khi thử nhánh EXTENDED trên STANDARD?

Khi `MAX_STRING_SIZE = STANDARD`, DDL dạng:

~~~sql
-- Chỉ để minh họa giới hạn, không chạy như bài kiểm tra bắt buộc:
CREATE TABLE lab_too_long (
    payload VARCHAR2(32767 BYTE)
);
~~~

không được hỗ trợ và có thể gặp lỗi như `ORA-00910: specified length too long for its datatype`. Không dùng lỗi này làm cách xác định cấu hình nếu có quyền truy vấn `V$PARAMETER`; kiểm tra cấu hình trước sẽ rõ ràng hơn.

Ngay cả trên `EXTENDED`, không phải mọi câu `INSERT` dài 32.767 **ký tự** đều hợp lệ: nếu byte vượt giới hạn cột sẽ bị từ chối. Một cột `VARCHAR2(32767 BYTE)` không tự chuyển thành CLOB khi giá trị lớn hơn 32.767 byte.

### 5.4 Kiểm tra trong Java bằng bind thay vì ghép literal SQL

Ví dụ một ứng dụng Java đã có `Connection connection`:

~~~java
String payload = "X".repeat(5000);
String sql = "INSERT INTO lab_extended_string (id, payload) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 2L);
    statement.setString(2, payload);
    statement.executeUpdate();
}
~~~

Đoạn mã giả định driver JDBC, bảng, quyền và cấu hình `EXTENDED` tương thích. `PreparedStatement` tách dữ liệu khỏi SQL text, nhưng **không nâng giới hạn của cột hoặc server**. Nếu đưa cùng payload vào cột `VARCHAR2(4000 BYTE)`, nó vẫn vượt giới hạn. Nếu ứng dụng cần chuỗi dài hơn 32.767 byte hoặc trao đổi với database `STANDARD`, cân nhắc `CLOB` và API tương ứng.

## 6. EXTENDED có khiến VARCHAR2 trở thành CLOB không?

**Không.** `VARCHAR2` vẫn là kiểu ký tự biến độ dài với trần byte hữu hạn và hành vi SQL `VARCHAR2`. `CLOB` là **large object** dành cho nội dung ký tự lớn, có cơ chế lưu trữ và API thao tác khác.

| Nhu cầu | `VARCHAR2` | `CLOB` |
|---|---|---|
| Tên, mã, trạng thái, ghi chú ngắn | Phù hợp | Thường không cần |
| Văn bản vài nghìn byte | `STANDARD` chịu trần 4.000, `EXTENDED` tới 32.767 | Phù hợp nếu muốn tránh phụ thuộc extended hoặc cần lớn hơn |
| Nội dung hàng trăm KB/MB | Không phù hợp | Phù hợp |
| So sánh, sắp xếp, chỉ mục B-tree thông thường | Nhiều thao tác thuận tiện hơn, nhưng chiều dài khóa index vẫn bị giới hạn | Thường cần hàm/thiết kế tìm kiếm phù hợp cho LOB |
| Driver/API | `setString`/`getString` thường dùng | Có `setCharacterStream`, `getCharacterStream`, `Clob` và các API streaming |
| Tương thích với database STANDARD cũ | `VARCHAR2` tối đa 4.000 byte | Hỗ trợ nội dung lớn qua LOB nếu hệ thống/driver tương thích |

Ví dụ bảng được thiết kế cho nội dung dài trong cả môi trường `STANDARD` và `EXTENDED`:

~~~sql
CREATE TABLE lab_large_document (
    document_id NUMBER PRIMARY KEY,
    title       VARCHAR2(200 CHAR),
    body_text   CLOB
);
~~~

Với `CLOB`, câu hỏi “độ dài bao nhiêu” nên dùng hàm LOB phù hợp:

~~~sql
SELECT document_id,
       DBMS_LOB.GETLENGTH(body_text) AS character_count
FROM lab_large_document;
~~~

`DBMS_LOB.GETLENGTH` của CLOB đếm độ dài ký tự theo ngữ nghĩa LOB, không phải mặc định là số byte mã UTF-8 trên đĩa. Tránh đưa nguyên `CLOB` vào biểu thức buộc chuyển sang `VARCHAR2` quá nhỏ; lỗi như `ORA-22835: Buffer too small for CLOB to CHAR ...` có thể phát sinh khi chuyển kiểu không phù hợp.

### 6.1 Cách lưu trữ của EXTENDED cũng có hệ quả hiệu năng

Oracle có thể lưu các giá trị `VARCHAR2` mở rộng lớn hơn ngưỡng thông thường bằng cơ chế **out-of-line** dựa trên hạ tầng LOB nội bộ. Vì thế mở rộng giới hạn không phải tăng độ dài “miễn phí”: có thể phát sinh chi phí I/O, không gian lưu trữ và thay đổi đặc tính truy cập. Tuy nhiên ứng dụng vẫn nhìn thấy kiểu SQL `VARCHAR2` với giới hạn hữu hạn, không phải kiểu `CLOB` được sử dụng một cách tự động.

Quyết định chọn `VARCHAR2(32767)` cần xem **độ dài thực tế, tần suất đọc/ghi, cách lọc/sắp xếp, chỉ mục và driver**, chứ không chỉ khả năng tạo cột thành công.

## 7. Tương thích phiên bản: 11g, 12c và các bản mới hơn

Tính năng mở rộng kích thước SQL string xuất hiện từ dòng Oracle Database **12c**. Trước dòng phiên bản này, trần `VARCHAR2` SQL 4.000 byte và `RAW` SQL 2.000 byte là những giới hạn cơ bản. Từ các bản hỗ trợ `MAX_STRING_SIZE`, **chỉ bật `EXTENDED` khi quy trình nâng cấp/database/container đã hỗ trợ và hoàn tất**.

| Môi trường | Điều có thể kỳ vọng | Hệ quả cho schema ứng dụng |
|---|---|---|
| Oracle 11g và các bản cũ không có extended SQL strings | `VARCHAR2` SQL tối đa 4.000 byte; không có lối bật `MAX_STRING_SIZE = EXTENDED` | Cột `VARCHAR2(32767)` không portable tới môi trường đó; cân nhắc `CLOB` |
| Oracle 12c+ hỗ trợ, ở `STANDARD` | Vẫn giữ trần SQL truyền thống | DDL/insert dài hơn trần sẽ thất bại dù engine “mới” |
| Oracle 12c+ hỗ trợ, ở `EXTENDED` | `VARCHAR2`/`NVARCHAR2`/`RAW` SQL có thể đạt 32.767 byte trong giới hạn kiểu | Schema phụ thuộc extended; khi di chuyển sang `STANDARD` cần thiết kế lại |
| CDB với nhiều PDB | Thiết lập/metadata chuyển đổi cần xét riêng root và các PDB theo tài liệu phiên bản | Không giả định mọi PDB có khả năng lưu cùng độ dài chỉ từ phiên bản CDB |
| Ứng dụng kết nối qua driver/ORM cũ | Một số đường truyền, metadata hoặc mapping có thể giả định giới hạn cũ | Cần kiểm tra phiên bản JDBC/ORM và thử thực tế với payload lớn |

**“Chạy Oracle 19c/21c/23ai” không tự trả lời câu hỏi `VARCHAR2` tối đa bao nhiêu** nếu chưa xem giá trị `MAX_STRING_SIZE` ở nơi ứng dụng thật sự hoạt động. Tương tự, một bản Java/JDBC mới không tự sửa database đang ở `STANDARD`.

### 7.1 Lỗi tương thích khi dịch chuyển schema

Giả sử môi trường phát triển dùng:

~~~sql
CREATE TABLE customer_notes (
    id      NUMBER PRIMARY KEY,
    details VARCHAR2(12000 BYTE)
);
~~~

DDL này phụ thuộc `EXTENDED`. Nếu đem schema sang database `STANDARD` hoặc Oracle cũ, bước tạo cột sẽ không được hỗ trợ. Với việc xuất/nhập dữ liệu qua công cụ migration hoặc Data Pump, cần kiểm tra đồng thời **khả năng tạo metadata** và **khả năng chứa từng giá trị thực tế**. Một cột nguồn 12.000 byte không thể được ánh xạ trực tiếp vào cột đích 4.000 byte nếu dữ liệu có bản ghi vượt trần.

Các cách xử lý phù hợp tùy yêu cầu:

1. Giữ target database/PDB ở chế độ hỗ trợ `EXTENDED`, theo quy trình quản trị đúng phiên bản, nếu kiến trúc và hệ thống tích hợp đều cho phép.
2. Thiết kế cột dữ liệu dài thành `CLOB` và điều chỉnh SQL, index, API/ORM tương ứng.
3. Giới hạn dữ liệu ở tầng ứng dụng **theo byte thực tế phù hợp target**, nếu nghiệp vụ thật sự chỉ cho phép dữ liệu ngắn; không âm thầm cắt chuỗi.
4. Thiết kế mô hình dữ liệu khác khi văn bản dài cần tìm kiếm toàn văn, lưu bản lớn hoặc phân mảnh theo nghiệp vụ.

Không khuyên “dùng `SUBSTR(details,1,4000)` rồi import” như một giải pháp chung: phép cắt theo ký tự có thể vẫn vượt 4.000 byte khi dữ liệu đa byte, và cắt dữ liệu có thể làm mất nội dung quan trọng.

### 7.2 Database link và SQL phân tán

Khi truy vấn qua **database link** giữa hệ thống có phiên bản/`MAX_STRING_SIZE` khác nhau, giới hạn kiểu ở nguồn, đích và biểu thức trung gian có thể không giống nhau. Một giá trị `VARCHAR2` dài 8.000 byte hợp lệ ở server nguồn `EXTENDED` không mặc nhiên có thể được biểu diễn như `VARCHAR2` trong mọi thao tác SQL của server đích `STANDARD`.

Thử những câu SQL thật có payload dài qua đường liên kết được phép, kiểm tra kiểu đích, phiên bản và driver thay vì chỉ kiểm tra câu `SELECT` trả vài ký tự. Với tích hợp không kiểm soát được phiên bản của đối tác, `CLOB` hoặc giao thức chia dữ liệu có thiết kế rõ ràng thường là lựa chọn cần đánh giá.

### 7.3 Giới hạn của index và ràng buộc

Một cột `VARCHAR2(32767)` không có nghĩa mọi giá trị 32.767 byte đều có thể dùng nguyên làm khóa index B-tree thông thường. Độ dài **index key** còn phụ thuộc vào cấu trúc chỉ mục, kích thước block và các giới hạn Oracle khác; lỗi như `ORA-01450: maximum key length exceeded` có thể xuất hiện khi thiết kế index không phù hợp.

Nếu cần tìm kiếm/định danh văn bản dài, phải làm rõ tiêu chí nghiệp vụ:

- Tra cứu bằng **mã ngắn, khóa surrogate hoặc hash có xử lý va chạm** khi cần định danh.
- Tìm kiếm từ khóa/nội dung bằng công cụ index/tìm kiếm phù hợp, không mặc định index toàn bộ chuỗi dài.
- Không biến toàn bộ payload dài thành khóa chính chỉ vì cột cho phép lưu.

Việc mở rộng cột có thể tác động đến functional index, virtual column hoặc đối tượng phụ thuộc khác trong quá trình nâng cấp; cần có kế hoạch kiểm tra và biên dịch lại theo tài liệu Oracle phiên bản đang dùng.

## 8. Bật MAX_STRING_SIZE = EXTENDED là thay đổi quản trị lớn

Không nên xem `MAX_STRING_SIZE` là một tùy chọn session để đổi qua lại khi truy vấn. Đây là tham số khởi tạo gắn với giới hạn kiểu và **metadata của database**. Việc chuyển từ `STANDARD` sang `EXTENDED` có quy trình nâng cấp cấu trúc nội bộ phù hợp, không chỉ một câu `ALTER SESSION`.

Ở các dòng Oracle hỗ trợ, quy trình quản trị thường bao gồm:

1. Xác nhận phiên bản, bản vá, `COMPATIBLE`, loại database (non-CDB/CDB/PDB) và các điều kiện Oracle quy định.
2. Đánh giá ảnh hưởng với ứng dụng, hệ thống xuất nhập dữ liệu, công cụ giám sát, chỉ mục, đối tượng PL/SQL và các PDB liên quan.
3. Sao lưu, chuẩn bị cửa sổ bảo trì và phương án khôi phục theo chính sách vận hành.
4. Đặt tham số cấu hình bằng thủ tục được Oracle hỗ trợ (thường liên quan cấu hình khởi động và chế độ upgrade).
5. Chạy script nâng cấp metadata do Oracle cung cấp, chẳng hạn `utl32k.sql`, theo tài liệu cho **đúng phiên bản và đúng phạm vi container**; với CDB, có quy trình thực hiện trên các PDB thích hợp.
6. Mở lại database/PDB ở chế độ vận hành thường, xử lý đối tượng invalid/phụ thuộc và xác minh cấu hình cùng dữ liệu ứng dụng.

Đây là **mô tả kiến trúc**, không phải runbook áp dụng trực tiếp. Trình tự lệnh thật, yêu cầu chế độ mở và công cụ chạy script khác nhau theo phiên bản/kiến trúc. Người học không nên chạy `ALTER SYSTEM` hoặc `utl32k.sql` trên database đang dùng chỉ để thử tạo một cột dài.

Điểm đặc biệt: sau khi nâng lên **`EXTENDED`, Oracle không hỗ trợ quay trực tiếp tham số về `STANDARD`** như một cách rollback thông thường. Nếu cần quay lại giới hạn cũ, phải có phương án khôi phục/migration được thiết kế từ trước. Việc bật extended strings vì vậy là quyết định cần đánh giá tương thích ở cấp hệ thống.

### 8.1 Một CDB có nhiều PDB cần cách nhìn riêng

Trên môi trường multitenant, metadata và trạng thái chuyển đổi không thể được giả định đồng nhất chỉ vì root cho thấy một giá trị. Các PDB được tạo, clone, plug/unplug hoặc nâng cấp từ nguồn khác có thể mang lịch sử cấu hình khác nhau. DBA cần xem tài liệu Oracle đúng phiên bản để xử lý PDB trong quy trình mở rộng và xác thực sau plug/migration.

Với người phát triển ứng dụng, cách làm thực tế là:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS current_container
FROM dual;

SELECT name, value
FROM v$parameter
WHERE name = 'max_string_size';
~~~

Kết hợp với metadata cột trong schema/PDB thực tế, sau đó lưu cả tên môi trường và phiên bản vào biên bản triển khai. Đừng chỉ ghi “Oracle phiên bản mới” trong tài liệu yêu cầu kỹ thuật.

## 9. Các lỗi thường gặp và hướng phân tích

| Hiện tượng/lỗi | Nguyên nhân có thể | Bước kiểm tra |
|---|---|---|
| `ORA-00910` khi khai báo `VARCHAR2(32767)` | Database/PDB chưa hỗ trợ hoặc chưa bật extended strings, hay khai báo vượt trần kiểu | Đọc `MAX_STRING_SIZE`, phiên bản và kiểu cột |
| `ORA-12899: value too large for column` | Dữ liệu vượt giới hạn byte/ký tự thực tế của cột | Đọc `DATA_LENGTH`, `CHAR_USED`; đo `LENGTHB` và `LENGTH` của giá trị |
| `ORA-01489: result of string concatenation is too long` | Biểu thức `VARCHAR2` tạo kết quả vượt giới hạn SQL | Xem kiểu kết quả, phép nối, phiên bản và xem có cần dùng CLOB không |
| `ORA-22835` khi chuyển CLOB sang CHAR | CLOB quá lớn cho bộ đệm/kiểu đích | Tránh ép CLOB toàn phần sang VARCHAR2; dùng thao tác LOB/đọc từng phần |
| `ORA-01450` khi tạo index trên chuỗi dài | Index key vượt giới hạn cấu trúc chỉ mục | Xem DDL index, kích thước dữ liệu/khối, thiết kế khóa |
| PL/SQL giữ được 5.000 byte nhưng insert lỗi | Biến PL/SQL và cột SQL có giới hạn khác nhau | So sánh `VARCHAR2(32767)` PL/SQL với giới hạn cột |
| Chạy dev thành công nhưng deploy sang test lỗi DDL | `MAX_STRING_SIZE`/version/PDB khác nhau | So sánh cả hai môi trường và metadata schema |
| “Đủ ký tự nhưng vẫn quá dài” | Unicode đa byte hoặc cột dùng `BYTE` | Đo `LENGTHB` trong đúng character set |
| Ứng dụng JDBC bị lỗi hoặc cắt dữ liệu | Driver/ORM/mapping/API hoặc validation giả định độ dài cũ | Kiểm tra driver, SQL bind, JDBC metadata và payload thực tế |
| Chuyển CLOB về String rồi xử lý không được | Cách ép kiểu, giới hạn API/buffer, chi phí tải dữ liệu | Dùng API LOB thích hợp hoặc streaming |

**Đừng tự cắt dữ liệu để “cho insert chạy được” khi chưa biết hậu quả nghiệp vụ.** Lỗi kích thước là tín hiệu rằng định nghĩa cột, dữ liệu thực tế hoặc hợp đồng hệ thống tích hợp không khớp; cần xác định đúng lớp gây lỗi trước.

### 9.1 Sơ đồ chẩn đoán nhanh

~~~mermaid
flowchart TD
    A["Chuỗi dài gây lỗi Oracle"] --> B{"Lỗi khi CREATE TABLE?"}
    B -->|Có| C["Kiểm tra version, MAX_STRING_SIZE, cú pháp kiểu"]
    B -->|Không| D{"Lỗi khi INSERT/UPDATE?"}
    D -->|Có| E["Đo byte, ký tự; xem DATA_LENGTH/CHAR_USED; bind type"]
    D -->|Không| F["Kiểm tra biểu thức SQL, concatenation, chuyển CLOB"]
    C --> G["Đối chiếu STANDARD/EXTENDED và PDB đích"]
    E --> H["Chọn giới hạn hợp lệ hoặc thiết kế CLOB"]
    F --> H
    G --> H
    H --> I["Thử với dữ liệu Unicode và payload biên trong môi trường được phép"]
~~~

## 10. Thiết kế cột chuỗi theo nhu cầu thực tế

### Trường hợp A: mã, tên và mô tả ngắn

Ví dụ:

~~~sql
CREATE TABLE product_catalog (
    product_id   NUMBER PRIMARY KEY,
    product_code VARCHAR2(40 BYTE) NOT NULL,
    name         VARCHAR2(200 CHAR) NOT NULL
);
~~~

`PRODUCT_CODE` có hợp đồng là mã ngắn dùng ASCII nên byte semantics có thể phù hợp. `NAME` cần tiếng Việt nên khai báo `CHAR` dễ diễn đạt số ký tự nghiệp vụ hơn. Cả hai đều rất nhỏ so với 4.000 byte; không cần bật `EXTENDED` chỉ để dùng hai cột này.

### Trường hợp B: ghi chú có thể dài vài nghìn byte

Đặt câu hỏi: dữ liệu thực tế dài bao nhiêu? Có cần so sánh/sắp xếp/index toàn phần hay chỉ lưu và hiển thị? Môi trường đích có thể là Oracle `STANDARD` hoặc phiên bản cũ không? Nếu hợp đồng cho phép vài KB và phải triển khai rộng, một cột `CLOB` có thể là lựa chọn ổn định hơn về giới hạn, nhưng cần thay đổi xử lý LOB và SQL.

Nếu dự án kiểm soát tất cả môi trường đều `EXTENDED`, `VARCHAR2(8000 BYTE)` hoặc độ dài phù hợp có thể hợp lệ, nhưng phải kiểm tra driver, ORM, index và việc đổi phiên bản/migration.

### Trường hợp C: tài liệu dài, JSON lớn, nội dung do người dùng nhập

Khi nội dung có thể lên tới hàng chục KB, hàng MB hoặc nhiều hơn, một cột `VARCHAR2` dù ở `EXTENDED` vẫn có thể thiếu. `CLOB`/cơ chế lưu nội dung lớn phù hợp hơn; các kiểu JSON chuyên biệt nếu sử dụng còn phụ thuộc phiên bản và nhu cầu nghiệp vụ. Không lấy ngưỡng 32.767 byte làm hạn chế vô tình cho yêu cầu có nội dung không giới hạn rõ ràng.

### Trường hợp D: chuyển dữ liệu giữa nhiều môi trường

Nếu database đích có thể ở `STANDARD`, tránh đưa cột extended SQL string vào schema dùng chung khi không có kế hoạch tương thích. Ghi rõ trong tài liệu:

~~~text
Yêu cầu môi trường:
- Oracle version/release được hỗ trợ: <phiên bản thực tế>
- CDB/PDB đích: <service/PDB>
- MAX_STRING_SIZE: STANDARD hoặc EXTENDED
- NLS_CHARACTERSET: <character set thực tế>
- Kiểu cột và byte/char semantics: <DDL chính thức>
- Driver JDBC/ORM: <phiên bản được kiểm thử>
- Dữ liệu biên: ASCII, tiếng Việt, Unicode 4-byte, payload dài
~~~

Cách này hữu ích khi hai đội phát triển và vận hành nhìn cùng một yêu cầu “cho phép ghi chú 10.000 ký tự” nhưng tính dung lượng byte khác nhau.

## 11. Bài thực hành tự kiểm tra

**Bài 1 — So sánh giới hạn.** Viết ra giới hạn byte SQL của `VARCHAR2`, `NVARCHAR2` và `RAW` ở `STANDARD` và `EXTENDED`. Giải thích vì sao `VARCHAR2(32767 CHAR)` không có nghĩa bất kỳ chuỗi 32.767 ký tự Unicode nào cũng lưu được.

**Bài 2 — Xác định cấu hình thật.** Kết nối vào PDB/schema thực hành; ghi `CON_NAME`, phiên bản server, `MAX_STRING_SIZE`, `NLS_CHARACTERSET` và `NLS_NCHAR_CHARACTERSET`. Nếu thiếu quyền đọc `V$PARAMETER`, ghi nhận giới hạn quyền và xin kết quả từ người quản trị.

**Bài 3 — Khác biệt SQL và PL/SQL.** Giải thích vì sao biến PL/SQL `VARCHAR2(32767)` có thể chứa 5.000 ký tự ASCII trên database `STANDARD`, nhưng một cột `VARCHAR2(4000 BYTE)` không thể lưu chúng.

**Bài 4 — BYTE vs CHAR.** Tạo bảng `LAB_STRING_SEMANTICS` đã nêu. Với `AL32UTF8`, so sánh `LENGTH` và `LENGTHB` của ký tự `ộ`, rồi dự đoán số ký tự Unicode tối đa có thể ghi vào một cột `VARCHAR2(100 BYTE)` nếu mỗi ký tự chiếm 3 byte. Giải thích vì sao việc dự đoán theo byte đáng tin hơn chỉ đếm “số chữ”.

**Bài 5 — Chọn kiểu dữ liệu.** Một ứng dụng phải lưu trường `comment` có thể từ 20 ký tự đến 200.000 ký tự, hoạt động trên cả Oracle `STANDARD` và `EXTENDED`. Hãy chọn kiểu cột, API JDBC và cách kiểm tra dữ liệu biên. Giải thích tại sao `VARCHAR2(32767)` chưa đáp ứng yêu cầu.

**Bài 6 — Tương thích.** Môi trường dev cho phép `VARCHAR2(12000 BYTE)`, nhưng môi trường production báo `MAX_STRING_SIZE=STANDARD`. Nêu ít nhất hai phương án xử lý có đánh đổi rõ ràng; giải thích vì sao không được tự chạy script nâng cấp database trên production.

**Bài 7 — Index.** Một cột `VARCHAR2(32767)` dùng làm khóa tìm kiếm duy nhất. Những rủi ro nào xuất hiện khi tạo index? Đề xuất cách thiết kế khóa hoặc tra cứu mà không dựa vào việc index nguyên văn mọi byte của chuỗi.

**Bài 8 — Xác minh mapping.** Ứng dụng Java `setString` gửi 6.000 ký tự ASCII vào Oracle. Dựa vào DDL cột, `MAX_STRING_SIZE` và loại kết nối, hãy dự đoán khi nào thao tác được hỗ trợ, khi nào lỗi và tại sao driver không tự mở giới hạn của database.

## 12. Nguyên tắc chốt để đọc đúng giới hạn

Khi gặp kiểu dữ liệu chuỗi Oracle, hãy áp dụng chuỗi kiểm tra:

~~~text
Đang ở database/PDB nào?
    ↓
Phiên bản Oracle và MAX_STRING_SIZE đang có hiệu lực?
    ↓
Kiểu cột là VARCHAR2/NVARCHAR2/RAW/CLOB/...?
    ↓
DDL dùng BYTE hay CHAR? Character set nào?
    ↓
Giá trị thực tế dài bao nhiêu ký tự và bao nhiêu byte?
    ↓
SQL expression, PL/SQL variable hay LOB API đang tham gia?
    ↓
Driver/ORM, index và hệ thống tích hợp có cùng giới hạn?
    ↓
Chọn khai báo/thiết kế tương thích, thử dữ liệu biên có kiểm soát
~~~

Ba điểm quan trọng nhất:

- **`MAX_STRING_SIZE=STANDARD`** giữ giới hạn `VARCHAR2`/`NVARCHAR2` SQL ở **4.000 byte**, còn **`EXTENDED`** có thể nâng lên **32.767 byte** trên phiên bản/PDB đã được chuyển đổi hợp lệ.
- **`CHAR` là ngữ nghĩa khai báo độ dài theo ký tự, không xóa giới hạn byte**; khi có Unicode nhiều byte, luôn quan sát `LENGTHB` và metadata cột.
- **`VARCHAR2` SQL, biến `VARCHAR2` trong PL/SQL và `CLOB` phục vụ nhu cầu khác nhau**. Chỉ mở rộng tham số không đảm bảo tương thích với Oracle cũ, driver, index hoặc hệ thống nhận dữ liệu dài.

Thiết kế bền vững là chọn kiểu dữ liệu theo hợp đồng nghiệp vụ và các môi trường cần hỗ trợ, sau đó xác minh bằng **cấu hình thực tế**, **DDL thực tế** và **dữ liệu biên có Unicode**. Khi biết giới hạn đến từ byte, kiểu cột, biểu thức hay phiên bản, bạn sẽ giải quyết đúng vấn đề thay vì chỉ tăng một con số trong DDL.
