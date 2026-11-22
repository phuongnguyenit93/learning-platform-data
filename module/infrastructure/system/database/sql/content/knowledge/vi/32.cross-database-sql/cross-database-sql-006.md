# Hàm chuỗi, toán tử nối và quy tắc đối chiếu

Trong một hệ thống bán hàng, hai tên khách hàng có thể chỉ khác chữ hoa/thường; một mã sản phẩm có thể chứa dấu gạch dưới; một địa chỉ có thể được nhập bằng Unicode dạng dựng sẵn hoặc dạng dấu kết hợp. Báo cáo cần sắp xếp tên theo ngôn ngữ người dùng, còn API phải ghép họ tên nhưng không tạo chuỗi có chữ NULL ở giữa.

Những yêu cầu này đều liên quan đến **chuỗi ký tự**, nhưng SQL không có một quy tắc duy nhất cho mọi hệ quản trị. Hàm có tên khác nhau, chỉ số vị trí có thể khác, phép nối xử lý NULL khác nhau, còn **collation** quyết định cách so sánh/sắp xếp và đôi khi cả cách LIKE hoặc UNIQUE hoạt động.

Bài **“Hàm chuỗi, toán tử nối và quy tắc đối chiếu”** thuộc chương **SQL đa hệ quản trị**, module **Database SQL**. Phần chính giải thích những hàm thường dùng và sự khác biệt giữa **PostgreSQL, MySQL, SQL Server, Oracle Database và SQLite**, tập trung vào:

- Độ dài chuỗi: ký tự, byte và đơn vị Unicode.
- Cắt chuỗi, tìm vị trí, thay thế, trim và chuẩn hóa.
- Nối chuỗi bằng toán tử hoặc hàm, đặc biệt là hành vi với NULL.
- Character set, encoding, collation và quy tắc hoa/thường, dấu, khoảng trắng.
- Unicode normalization, index, so sánh, ORDER BY và tính duy nhất.
- Bind parameter, wildcard, SQL injection và kiểm thử đa phương ngữ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt kiểu chuỗi cố định, biến độ dài và kiểu lưu văn bản lớn.
2. Chọn hàm lấy độ dài theo **ký tự** hay theo **byte**.
3. Dùng các nhóm hàm cắt, tìm, thay thế, trim và nối chuỗi.
4. Giải thích vì sao cùng một phép nối có thể trả NULL hoặc chuỗi rỗng trên các hệ.
5. Phân biệt **character set/encoding** với **collation**.
6. Đọc hậu tố collation như CI, CS, AI, AS và BIN/BIN2 khi hệ hỗ trợ.
7. Hiểu collation ảnh hưởng so sánh, ORDER BY, GROUP BY, LIKE và UNIQUE như thế nào.
8. Nhận biết khác biệt giữa byte, code point và grapheme cluster.
9. Xử lý Unicode, dấu tiếng Việt và chuỗi rỗng một cách có chủ đích.
10. Tránh ghép input trực tiếp vào SQL; dùng bind parameter và escape pattern đúng.
11. Thiết kế index cho truy vấn tìm kiếm/sắp xếp theo collation mong muốn.
12. Viết SQL có chủ đích khi cần chuyển giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite.

## 2. Chuỗi trong SQL: kiểu dữ liệu trước khi dùng hàm

Các kiểu chuỗi phổ biến:

| Kiểu | Ý nghĩa thường gặp | Dùng khi |
| --- | --- | --- |
| **CHAR(n)** | Chuỗi độ dài cố định, có thể được đệm khoảng trắng | Mã có độ dài cố định |
| **VARCHAR(n)** | Chuỗi biến độ dài với giới hạn | Tên, email, mã có giới hạn |
| **NCHAR/NVARCHAR** | Kiểu Unicode riêng ở một số hệ, nhất là SQL Server | Nội dung đa ngôn ngữ trong SQL Server |
| **TEXT/CLOB** | Văn bản dài, chi tiết lưu trữ phụ thuộc hệ | Nội dung bài viết, ghi chú dài |

Tên kiểu không bảo đảm cùng giới hạn hay cùng encoding trên mọi hệ:

- PostgreSQL dùng **text**, **varchar(n)** và **char(n)**; text/varchar có khả năng lưu Unicode theo database encoding.
- MySQL dùng **CHAR/VARCHAR/TEXT** cùng character set/collation của cột.
- SQL Server có **char/varchar** và **nchar/nvarchar**; varchar cũng có thể hỗ trợ UTF-8 khi dùng collation UTF-8 phù hợp.
- Oracle dùng **CHAR/VARCHAR2/NCHAR/NVARCHAR2/CLOB/NCLOB** với quy tắc character set riêng.
- SQLite dùng storage class **TEXT** theo mô hình dynamic typing; khai báo VARCHAR(n) không thực thi giới hạn n như một số RDBMS khác.

### 2.1. CHAR và VARCHAR không giống nhau

Với CHAR(n), hệ thường đệm phần còn thiếu bằng khoảng trắng để đạt độ dài cố định theo quy tắc kiểu. VARCHAR lưu chuỗi biến độ dài.

~~~sql
CREATE TABLE code_demo (
    country_code CHAR(2),
    display_name VARCHAR(100)
);
~~~

CHAR có thể phù hợp mã quốc gia hai ký tự; tên người dùng thường phù hợp VARCHAR. Tuy nhiên, việc so sánh chuỗi có khoảng trắng cuối phụ thuộc kiểu, collation và engine. Đừng dựa vào giả định rằng khoảng trắng cuối luôn được giữ hoặc luôn bị bỏ trong mọi phép so sánh.

### 2.2. Giới hạn độ dài không đồng nhất

Tham số VARCHAR(n) có thể được tính theo ký tự hoặc byte tùy RDBMS/kiểu dữ liệu. Trong Oracle, khai báo có thể dùng **BYTE** hoặc **CHAR** semantics; trong SQL Server, giới hạn varchar/nvarchar có các quy tắc byte riêng; SQLite không áp dụng giới hạn VARCHAR(n) như constraint tự động.

Nếu độ dài là quy tắc nghiệp vụ, nên tạo constraint rõ ràng hoặc validate ở ứng dụng và database theo đúng đơn vị cần đo.

## 3. Ba khái niệm độ dài: byte, code point và grapheme

Một chuỗi hiển thị cho người dùng không nhất thiết tương ứng với một byte hoặc một đơn vị ký tự mà hàm SQL đếm.

Ví dụ:

~~~text
A
é
e + dấu sắc kết hợp
🇻🇳
👩‍💻
~~~

Những chuỗi trên có thể gồm số lượng byte, Unicode code point và **grapheme cluster** khác nhau.

| Đơn vị | Mô tả | Dùng để |
| --- | --- | --- |
| **Byte** | Đơn vị lưu trữ mã hóa | Kích thước truyền/lưu |
| **Unicode code point** | Một mã Unicode | Một số phép đo chuỗi trong RDBMS |
| **Grapheme cluster** | Đơn vị gần với ký tự người dùng nhìn thấy | Giới hạn ký tự giao diện, con trỏ và xóa ký tự |

Một chữ có dấu dạng tổ hợp có thể gồm chữ cái và combining mark. Emoji có thể gồm nhiều code point kết hợp bằng variation selector hoặc zero-width joiner. Vì vậy, **CHAR_LENGTH không mặc định là số ký tự người dùng nhìn thấy**.

## 4. Hàm lấy độ dài chuỗi theo từng hệ

Các hàm quen thuộc không cùng tên:

| Mục tiêu | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Độ dài ký tự | CHAR_LENGTH / CHARACTER_LENGTH | CHAR_LENGTH | LEN | LENGTH | length |
| Độ dài byte | OCTET_LENGTH | LENGTH | DATALENGTH | LENGTHB | length(BLOB) / biểu diễn byte |
| Đơn vị Unicode đặc thù | Tùy kiểu/encoding | Theo character set | DATALENGTH/LEN và SC collation | LENGTHC/LENGTH2/LENGTH4 | length(TEXT) theo code point |

### 4.1. PostgreSQL

~~~sql
SELECT
    CHAR_LENGTH('cà phê') AS char_count,
    OCTET_LENGTH('cà phê') AS byte_count;
~~~

- **CHAR_LENGTH** đếm ký tự theo cách PostgreSQL xử lý chuỗi trong encoding database.
- **OCTET_LENGTH** trả số byte.

Trong database UTF-8, một ký tự có dấu có thể chiếm nhiều byte. Hai giá trị không nhất thiết bằng nhau.

### 4.2. MySQL

~~~sql
SELECT
    CHAR_LENGTH('cà phê') AS char_count,
    LENGTH('cà phê') AS byte_count;
~~~

Trong MySQL, **CHAR_LENGTH** đếm ký tự theo character set; **LENGTH** trả số byte. Cùng chuỗi có thể cho LENGTH khác khi cột/literal được xử lý với character set khác.

### 4.3. SQL Server

~~~sql
SELECT
    LEN(N'cà phê') AS len_value,
    DATALENGTH(N'cà phê') AS bytes_value;
~~~

- **LEN** đếm ký tự nhưng bỏ qua khoảng trắng ở cuối chuỗi.
- **DATALENGTH** trả số byte được lưu cho biểu thức.
- Với NVARCHAR, byte thường được lưu theo đơn vị mã hóa UTF-16; supplementary characters có thể cần collation hỗ trợ SC để các hàm đếm/cắt xử lý như mong muốn.

Đừng dùng LEN như một phép đo kích thước lưu trữ.

### 4.4. Oracle

~~~sql
SELECT
    LENGTH('cà phê') AS char_length,
    LENGTHB('cà phê') AS byte_length,
    LENGTHC('cà phê') AS complete_char_length,
    LENGTH2('cà phê') AS ucs2_length,
    LENGTH4('cà phê') AS ucs4_length
FROM dual;
~~~

Oracle cung cấp nhiều cách đo:

- **LENGTH:** độ dài theo ký tự của character set.
- **LENGTHB:** số byte.
- **LENGTHC:** Unicode complete characters theo định nghĩa Oracle.
- **LENGTH2:** đơn vị UCS2 code point.
- **LENGTH4:** đơn vị UCS4 code point.

Các hàm LENGTHC/LENGTH2/LENGTH4 có giới hạn áp dụng với một số kiểu LOB/character set; xem đúng phiên bản Oracle khi dùng trong thiết kế thực tế.

### 4.5. SQLite

~~~sql
SELECT
    length('cà phê') AS text_length,
    length(CAST('cà phê' AS BLOB)) AS byte_length;
~~~

Với TEXT, **length** đếm Unicode code point theo cách SQLite định nghĩa và dừng tại ký tự NUL đầu tiên trong trường hợp có U+0000. Với BLOB, length trả số byte.

### 4.6. Không lấy số byte để giới hạn ký tự giao diện

Nếu yêu cầu là “tên hiển thị tối đa 30 ký tự người dùng nhìn thấy”, dùng một hàm đếm byte có thể cắt chuỗi Unicode sai. Ngược lại, nếu giới hạn là dung lượng truyền hoặc kích thước payload, số byte mới là thước đo cần xem.

**Đơn vị phải đi cùng yêu cầu nghiệp vụ.**

## 5. Cắt chuỗi: SUBSTRING, SUBSTR, LEFT và RIGHT

Các hệ đều có hàm lấy một phần chuỗi nhưng khác tên, tham số và quy tắc vị trí.

| Hệ | Hàm thường dùng |
| --- | --- |
| PostgreSQL | SUBSTRING, SUBSTR, LEFT, RIGHT |
| MySQL | SUBSTRING/SUBSTR, LEFT, RIGHT |
| SQL Server | SUBSTRING, LEFT, RIGHT |
| Oracle | SUBSTR, SUBSTRB, SUBSTRC, SUBSTR2, SUBSTR4 |
| SQLite | substr, substring trên phiên bản có hỗ trợ alias |

### 5.1. PostgreSQL

~~~sql
SELECT
    SUBSTRING('PostgreSQL' FROM 1 FOR 4) AS first_four,
    LEFT('PostgreSQL', 4) AS left_four,
    RIGHT('PostgreSQL', 3) AS right_three;
~~~

Kết quả: **Post**, **Post**, **SQL**.

Dạng hàm cũng được hỗ trợ:

~~~sql
SELECT SUBSTRING('Database' FROM 5) AS tail_text;
~~~

### 5.2. MySQL

~~~sql
SELECT
    SUBSTRING('PostgreSQL', 1, 4) AS first_four,
    LEFT('PostgreSQL', 4) AS left_four,
    RIGHT('PostgreSQL', 3) AS right_three,
    SUBSTRING('PostgreSQL', -3) AS from_end;
~~~

MySQL dùng vị trí bắt đầu 1-based; vị trí âm trong SUBSTRING có thể tính từ cuối chuỗi.

### 5.3. SQL Server

~~~sql
SELECT
    SUBSTRING(N'PostgreSQL', 1, 4) AS first_four,
    LEFT(N'PostgreSQL', 4) AS left_four,
    RIGHT(N'PostgreSQL', 3) AS right_three;
~~~

SQL Server dùng vị trí bắt đầu 1-based. Hàm SUBSTRING có quy tắc về start/length và hỗ trợ biểu thức kiểu ký tự/binary; hãy xem đúng phiên bản nếu dựa vào việc bỏ length hoặc giá trị âm.

### 5.4. Oracle

~~~sql
SELECT
    SUBSTR('PostgreSQL', 1, 4) AS first_four,
    SUBSTR('PostgreSQL', -3) AS right_three
FROM dual;
~~~

Oracle có các biến thể SUBSTRB, SUBSTRC, SUBSTR2, SUBSTR4 để đo/cắt theo byte, complete characters, UCS2 hoặc UCS4 unit trong phạm vi hỗ trợ.

### 5.5. SQLite

~~~sql
SELECT
    substr('PostgreSQL', 1, 4) AS first_four,
    substr('PostgreSQL', -3) AS right_three;
~~~

SQLite substr hỗ trợ chỉ số âm tính từ cuối chuỗi. Vị trí và độ dài cần kiểm tra kỹ khi port sang hệ khác.

### 5.6. Bẫy off-by-one

Nếu ứng dụng Java dùng String.substring(start, end), chỉ số của Java là **0-based** và end không bao gồm; SQL SUBSTRING phổ biến là **1-based**. Không chuyển hai chỉ số trực tiếp mà không đổi quy tắc.

~~~text
Java: substring(0, 4)  → bốn ký tự đầu
SQL:  SUBSTRING(x, 1, 4) → bốn ký tự đầu
~~~

## 6. Tìm vị trí chuỗi con

Các hàm tìm vị trí thường trả về **vị trí bắt đầu 1-based**, hoặc 0 nếu không tìm thấy; nhưng cần kiểm tra riêng từng hệ.

| Hệ | Hàm | Tham số khái quát |
| --- | --- | --- |
| PostgreSQL | POSITION(sub IN str), STRPOS(str, sub) | Chuỗi cần tìm, chuỗi nguồn |
| MySQL | LOCATE(sub, str), INSTR(str, sub) | Chuỗi cần tìm, chuỗi nguồn |
| SQL Server | CHARINDEX(sub, str [, start]) | Chuỗi cần tìm, nguồn, vị trí bắt đầu |
| Oracle | INSTR(str, sub [, start [, occurrence]]) | Chuỗi nguồn, chuỗi cần tìm, vị trí, lần xuất hiện |
| SQLite | instr(str, sub) | Chuỗi nguồn, chuỗi cần tìm |

### 6.1. PostgreSQL

~~~sql
SELECT
    POSITION('SQL' IN 'PostgreSQL') AS pos_position,
    STRPOS('PostgreSQL', 'SQL') AS pos_strpos,
    STRPOS('PostgreSQL', 'Oracle') AS not_found;
~~~

Vị trí bắt đầu của SQL trong PostgreSQL là **8**; không tìm thấy trả **0**.

### 6.2. MySQL

~~~sql
SELECT
    LOCATE('SQL', 'PostgreSQL') AS pos_locate,
    INSTR('PostgreSQL', 'SQL') AS pos_instr;
~~~

Chú ý thứ tự đối số của LOCATE khác INSTR.

### 6.3. SQL Server

~~~sql
SELECT
    CHARINDEX(N'SQL', N'PostgreSQL') AS pos_sql,
    CHARINDEX(N'Oracle', N'PostgreSQL') AS not_found;
~~~

CHARINDEX trả 0 khi không tìm thấy. Có thể truyền start_location để tìm từ vị trí nhất định.

### 6.4. Oracle

~~~sql
SELECT
    INSTR('PostgreSQL SQL', 'SQL') AS first_pos,
    INSTR('PostgreSQL SQL', 'SQL', 1, 2) AS second_pos
FROM dual;
~~~

Oracle INSTR có tham số occurrence để tìm lần xuất hiện thứ hai, thứ ba... và hỗ trợ tìm ngược bằng start âm trong các trường hợp được định nghĩa.

### 6.5. SQLite

~~~sql
SELECT
    instr('PostgreSQL', 'SQL') AS pos_sql,
    instr('PostgreSQL', 'Oracle') AS not_found;
~~~

### 6.6. Không giả định tìm kiếm vị trí là không phân biệt hoa/thường

Các hàm trên thường tìm theo quy tắc so khớp của biểu thức/collation tương ứng. Nếu nghiệp vụ cần case-insensitive, hãy quy định collation hoặc chuẩn hóa input rõ ràng. Không dựa vào một kết quả trên máy phát triển rồi cho rằng mọi môi trường có cùng collation.

## 7. Thay thế chuỗi: REPLACE và TRANSLATE

**REPLACE** thay mọi lần xuất hiện của một chuỗi con bằng chuỗi thay thế.

~~~sql
-- Ví dụ PostgreSQL
SELECT REPLACE(
    'SQL, PostgreSQL, MySQL',
    'SQL',
    'DATABASE'
) AS replaced;
~~~

Kết quả minh họa:

~~~text
DATABASE, PostgreDATABASE, MyDATABASE
~~~

Đây là thay thế chuỗi con theo cách của hàm REPLACE; nó không hiểu ranh giới từ. Muốn chỉ thay từ SQL độc lập, cần tokenization/regex hoặc logic phù hợp thay vì REPLACE đơn giản.

### 7.1. TRANSLATE

PostgreSQL, Oracle và một số hệ có hàm TRANSLATE để ánh xạ ký tự theo từng vị trí:

~~~sql
-- PostgreSQL / Oracle-style example
SELECT TRANSLATE('abc123', 'abc', 'ABC');
~~~

Kết quả **ABC123**. TRANSLATE phù hợp thay từng ký tự trong tập ký tự nguồn; REPLACE thay một chuỗi con nhiều ký tự. MySQL và SQL Server không có cùng cú pháp TRANSLATE trên mọi phiên bản/đời cũ; SQL Server có hàm TRANSLATE từ SQL Server 2017.

### 7.2. Không dùng REPLACE để chuẩn hóa ngôn ngữ tùy tiện

~~~sql
SELECT REPLACE('cà phê', 'à', 'a');
~~~

Đây chỉ là thay thế đúng chuỗi con ký tự được nêu. Nó không giải quyết đầy đủ:

- Các dạng Unicode dựng sẵn và dấu kết hợp.
- Những chữ có dấu khác.
- Viết hoa/viết thường.
- Từ đồng nghĩa hoặc dấu câu.
- Các ký tự trông giống nhau nhưng có code point khác.

Muốn chuẩn hóa dữ liệu đa ngôn ngữ, cần một chính sách Unicode/locale rõ ràng, không phải một chuỗi REPLACE nối tiếp không kiểm soát.

## 8. TRIM, LTRIM và RTRIM

Hàm trim thường loại bỏ ký tự ở đầu/cuối chuỗi:

~~~sql
SELECT
    TRIM('   SQL   ') AS both_sides,
    LTRIM('   SQL') AS left_side,
    RTRIM('SQL   ') AS right_side;
~~~

### 8.1. TRIM không phải loại mọi whitespace

Không giả định TRIM mặc định loại toàn bộ:

- Tab.
- Newline.
- Non-breaking space.
- Thin space.
- Zero-width characters.
- Mọi Unicode whitespace.

Nhiều hệ chỉ loại dấu cách thông thường hoặc tập ký tự xác định theo cú pháp/hàm. Nếu cần dọn dữ liệu nhập từ nhiều nguồn, hãy định nghĩa rõ danh sách ký tự và kiểm thử.

### 8.2. Cú pháp theo hệ

PostgreSQL hỗ trợ dạng:

~~~sql
SELECT TRIM(BOTH 'x' FROM 'xxxSQLxxx');
~~~

MySQL có cú pháp tương tự:

~~~sql
SELECT TRIM(BOTH 'x' FROM 'xxxSQLxxx');
~~~

SQL Server dùng TRIM ở các phiên bản hỗ trợ, cùng LTRIM/RTRIM; cú pháp tùy phiên bản có thể mở rộng ký tự loại bỏ.

~~~sql
SELECT TRIM('   SQL   ');
~~~

Oracle:

~~~sql
SELECT TRIM(BOTH 'x' FROM 'xxxSQLxxx')
FROM dual;
~~~

SQLite có trim(X [, Y]), ltrim và rtrim; Y là tập ký tự cần loại theo quy tắc hàm:

~~~sql
SELECT trim('xxxSQLxxx', 'x');
~~~

Không giả định tham số Y luôn có nghĩa “chuỗi con dài nhất”; trong nhiều hàm trim, đó là **tập ký tự** ở đầu/cuối.

## 9. Nối chuỗi: toán tử và hàm

Đây là nơi khác biệt đa hệ quản trị rất dễ gây lỗi.

| Hệ | Toán tử thường dùng | Hàm nối |
| --- | --- | --- |
| PostgreSQL | || | concat, concat_ws |
| MySQL | CONCAT_WS; || mặc định là logical OR trừ chế độ SQL riêng | CONCAT, CONCAT_WS |
| SQL Server | + | CONCAT, CONCAT_WS |
| Oracle | \|\| | CONCAT (hai đối số), có thể dùng \|\| |
| SQLite | \|\| | concat, concat_ws trên bản hỗ trợ |

### 9.1. PostgreSQL: || và concat

~~~sql
SELECT
    'SQL' || ' ' || 'Guide' AS operator_result,
    concat('SQL', ' ', 'Guide') AS function_result,
    concat_ws(' ', 'SQL', 'Guide') AS ws_result;
~~~

Cả ba trả **SQL Guide**.

Nhưng khi có NULL:

~~~sql
SELECT
    'SQL' || NULL::TEXT AS operator_null,
    concat('SQL', NULL::TEXT, 'Guide') AS concat_value,
    concat_ws(' ', 'SQL', NULL::TEXT, 'Guide') AS ws_value;
~~~

- Toán tử **||** cho NULL nếu một phía NULL.
- **concat** coi đối số NULL như chuỗi rỗng.
- **concat_ws** dùng đối số đầu làm separator và bỏ qua các đối số NULL sau nó.

### 9.2. MySQL: CONCAT và CONCAT_WS

~~~sql
SELECT
    CONCAT('SQL', ' ', 'Guide') AS normal_concat,
    CONCAT('SQL', NULL, 'Guide') AS null_concat,
    CONCAT_WS(' ', 'SQL', NULL, 'Guide') AS ws_concat;
~~~

- **CONCAT** trả NULL nếu có bất kỳ đối số nào NULL.
- **CONCAT_WS** bỏ qua các đối số NULL sau separator.
- Nếu **separator** của CONCAT_WS là NULL, kết quả là NULL.

Toán tử **||** trong MySQL mặc định được hiểu là logical OR trong cấu hình SQL phổ biến. Chế độ **PIPES_AS_CONCAT** có thể thay đổi ngữ nghĩa. Khi viết SQL đa hệ, dùng CONCAT/CONCAT_WS thay vì giả định || luôn nối chuỗi.

### 9.3. SQL Server: + và CONCAT

~~~sql
SELECT
    N'SQL' + N' ' + N'Guide' AS plus_result,
    CONCAT(N'SQL', NULL, N'Guide') AS concat_result,
    CONCAT_WS(N' ', N'SQL', NULL, N'Guide') AS ws_result;
~~~

- **+** là toán tử nối chuỗi trong ngữ cảnh kiểu chuỗi, nhưng hành vi NULL chịu quy tắc CONCAT_NULL_YIELDS_NULL; ở các phiên bản SQL Server hiện đại, tùy chọn này được duy trì ON.
- **CONCAT** chuyển NULL thành chuỗi rỗng.
- **CONCAT_WS** bỏ qua đối số NULL sau separator.

Hãy dùng kiểu chuỗi tương thích để tránh phép cộng số học hoặc chuyển kiểu ngoài ý muốn.

### 9.4. Oracle: ||

~~~sql
SELECT
    'SQL' || ' ' || 'Guide' AS joined_text,
    'SQL' || NULL AS null_side,
    CONCAT('SQL', ' Guide') AS concat_two_args
FROM dual;
~~~

Oracle xử lý **zero-length character string** như NULL trong nhiều ngữ cảnh SQL; toán tử nối với NULL có quy tắc đặc thù khiến nối một chuỗi với NULL thường cho chuỗi còn lại. Đây là khác biệt lớn so với PostgreSQL/SQLite dùng || mà một toán hạng NULL làm kết quả NULL.

Hàm Oracle **CONCAT** nhận hai đối số; nếu cần nhiều phần, dùng toán tử || hoặc lồng hàm theo cú pháp phù hợp.

### 9.5. SQLite: || và concat

~~~sql
SELECT
    'SQL' || ' ' || 'Guide' AS operator_result,
    concat('SQL', NULL, 'Guide') AS function_result,
    concat_ws(' ', 'SQL', NULL, 'Guide') AS ws_result;
~~~

Toán tử || truyền thống trả NULL nếu một toán hạng NULL; hàm concat/concat_ws ở các bản SQLite hỗ trợ có thể bỏ qua NULL. Nếu ứng dụng dùng SQLite cũ, kiểm tra version và hàm có sẵn thay vì giả định mọi bản build đều hỗ trợ cùng bộ hàm.

### 9.6. Bảng so sánh NULL khi nối

| Biểu thức | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Chuỗi +/|| với NULL | || trả NULL | CONCAT trả NULL; || mặc định là OR | || thường trả chuỗi còn lại do NULL/empty-string semantics | || trả NULL |
| CONCAT('A', NULL, 'B') | 'AB' | NULL | 'AB' | CONCAT nhận hai đối số; NULL theo semantics Oracle | 'AB' trên bản hỗ trợ |
| CONCAT_WS('-', 'A', NULL, 'B') | 'A-B' | 'A-B' | 'A-B' trên bản hỗ trợ | Không cùng hàm phổ biến; dùng cách nối có chủ đích | 'A-B' trên bản hỗ trợ |

**Không dùng một phép nối rồi mong kết quả NULL giống nhau trên mọi engine.** Khi cần logic portable, xác định trước chính sách NULL và viết CASE/COALESCE phù hợp.

## 10. COALESCE và NULLIF khi xử lý chuỗi

**COALESCE** trả biểu thức đầu tiên không NULL:

~~~sql
SELECT COALESCE(email, '') AS email_for_display
FROM customers;
~~~

**NULLIF** trả NULL khi hai biểu thức bằng nhau:

~~~sql
SELECT NULLIF(TRIM(display_name), '') AS normalized_name
FROM customers;
~~~

Hai hàm này giúp định nghĩa rõ:

- NULL nghĩa là chưa biết/chưa nhập.
- Chuỗi rỗng nghĩa là có giá trị nhưng không có ký tự.
- Chuỗi chỉ có khoảng trắng có được coi như rỗng không.

### 10.1. COALESCE trước khi nối

~~~sql
SELECT
    COALESCE(first_name, '')
    || ' '
    || COALESCE(last_name, '') AS full_name
FROM people;
~~~

Ví dụ PostgreSQL/SQLite/Oracle-style, nhưng phải nhớ **Oracle coi chuỗi rỗng là NULL** và **MySQL cần CONCAT** nếu muốn dùng cách portable.

### 10.2. Chính sách separator khi thiếu thành phần

Nếu first_name NULL và last_name là “Nguyen”, kết quả có thể bắt đầu bằng dấu cách nếu chỉ COALESCE cả hai phía. Có thể dùng CONCAT_WS hoặc CASE để bỏ thành phần thiếu:

~~~sql
SELECT CONCAT_WS(' ', first_name, middle_name, last_name)
FROM people;
~~~

Hàm này có ở PostgreSQL, MySQL và SQL Server phiên bản hỗ trợ; kiểm tra SQLite version. Oracle cần cách viết riêng, chẳng hạn CASE hoặc các biểu thức nối có trim được định nghĩa rõ.

## 11. Character set, encoding và collation

Ba khái niệm dễ bị gộp nhầm:

| Khái niệm | Câu hỏi |
| --- | --- |
| **Character set** | Bộ ký tự nào được hỗ trợ? |
| **Encoding** | Ký tự được mã hóa thành byte như thế nào? |
| **Collation** | Chuỗi được so sánh, sắp xếp và đôi khi match pattern theo quy tắc nào? |

Ví dụ, UTF-8 là encoding; Unicode là tập ký tự/mã điểm; một collation tiếng Việt hoặc collation không phân biệt hoa/thường quyết định cách so sánh theo locale.

**UTF-8 không tự quyết định thứ tự sắp xếp tiếng Việt**, cũng không tự làm cho so sánh bỏ dấu hay bỏ hoa/thường.

## 12. Collation quyết định điều gì?

Collation là quy tắc so sánh chuỗi. Nó có thể tác động tới:

- So sánh bằng và khác.
- ORDER BY.
- GROUP BY và DISTINCT.
- JOIN trên cột chuỗi.
- UNIQUE index/constraint.
- LIKE và các phép tìm chuỗi tùy hệ.
- Cách đánh giá hoa/thường, dấu và một số ký tự tương đương.

### 12.1. Case sensitivity

Giả sử có hai giá trị:

~~~text
SQL
sql
~~~

Một collation **case-insensitive (CI)** có thể coi chúng tương đương trong phép so sánh; **case-sensitive (CS)** phân biệt hoa/thường.

### 12.2. Accent sensitivity

~~~text
cafe
café
~~~

Collation **accent-insensitive (AI)** có thể coi chúng tương đương; **accent-sensitive (AS)** phân biệt dấu. Cách đối chiếu cụ thể còn tùy ngôn ngữ và collation.

### 12.3. Binary collation

Collation dạng binary/BIN/BIN2 hoặc tương đương thường so sánh dựa trên biểu diễn mã/đơn vị nhị phân theo quy tắc của hệ. Nó phù hợp một số yêu cầu mã định danh chính xác, nhưng **thứ tự binary không phải thứ tự từ điển tự nhiên của người dùng**.

### 12.4. Collation không phải normalization

Hai chuỗi Unicode nhìn giống nhau có thể được biểu diễn bằng các chuỗi code point khác nhau. Collation có thể xử lý một số tương đương ngôn ngữ, nhưng không nên giả định nó tự biến mọi dạng NFC/NFD thành một dạng lưu trữ duy nhất. Nếu cần canonical representation, hãy chuẩn hóa Unicode ở một lớp được kiểm soát.

## 13. Hậu tố collation thường gặp

Trong một số hệ, tên collation có quy ước:

| Hậu tố | Ý nghĩa thường gặp |
| --- | --- |
| **CI** | Case-insensitive |
| **CS** | Case-sensitive |
| **AI** | Accent-insensitive |
| **AS** | Accent-sensitive |
| **BIN/BIN2** | Binary-oriented comparison |
| **SC** | Supplementary-character support trong một số collation SQL Server |
| **UTF8** | Encoding UTF-8 trong một số collation SQL Server |

Các hậu tố này nổi bật trong SQL Server và MySQL, nhưng không phải một chuẩn tên chung áp dụng cho mọi hệ. Luôn kiểm tra định nghĩa collation cụ thể.

## 14. PostgreSQL: collation và so sánh chuỗi

PostgreSQL có collation ở cấp database, column hoặc expression. Nguồn collation có thể đến từ libc hoặc ICU tùy build/cấu hình.

### 14.1. Xem collation

~~~sql
SELECT
    datname,
    datcollate,
    datctype
FROM pg_database
WHERE datname = current_database();
~~~

Xem danh sách collation:

~~~sql
SELECT
    collname,
    collprovider,
    collisdeterministic
FROM pg_collation
ORDER BY collname
LIMIT 30;
~~~

### 14.2. COLLATE trên biểu thức

~~~sql
SELECT
    name,
    name COLLATE "C" AS binary_like_order
FROM people
ORDER BY name COLLATE "C";
~~~

**"C"** cung cấp quy tắc đối chiếu đơn giản theo môi trường C, thường hữu ích khi cần thứ tự ổn định/nhị phân cho một số tác vụ kỹ thuật. Nó không tương đương một collation tiếng Việt thân thiện người dùng.

### 14.3. ILIKE và collation

PostgreSQL có **ILIKE** để tìm không phân biệt hoa/thường theo locale hiện hành:

~~~sql
SELECT name
FROM people
WHERE name ILIKE '%nguyen%';
~~~

ILIKE không phải toán tử portable. Nếu muốn tìm không phân biệt dấu tiếng Việt, cần một pipeline riêng như unaccent/dictionary/cột normalized; ILIKE đơn thuần không có nghĩa là bỏ dấu.

### 14.4. ICU nondeterministic collation

PostgreSQL có thể dùng **ICU collation** và collation không deterministic ở những phiên bản/tình huống hỗ trợ để áp dụng so sánh ngôn ngữ như bỏ hoa/thường hoặc dấu theo cấu hình ICU. Các collation không deterministic có giới hạn tương thích với một số toán tử/index và pattern matching; không tạo một collation như vậy rồi mặc định mọi LIKE/regex đều được hỗ trợ.

Khi đổi phiên bản ICU hoặc libc, thứ tự/so sánh có thể thay đổi. Index phụ thuộc collation có thể cần **REINDEX** sau khi phát hiện collation version mismatch.

## 15. MySQL: character set và collation

MySQL gắn character set/collation ở cấp server, database, table, column hoặc expression.

### 15.1. utf8mb4

~~~sql
CREATE TABLE people (
    person_id BIGINT PRIMARY KEY,
    display_name VARCHAR(200)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
);
~~~

**utf8mb4** hỗ trợ toàn bộ dải Unicode của MySQL. Collation **utf8mb4_0900_ai_ci** là một ví dụ collation Unicode 9.0 không phân biệt accent và case trong MySQL 8.0.

Tên collation phải có trên phiên bản MySQL đang dùng. Không copy collation 0900 sang MySQL cũ mà chưa kiểm tra.

### 15.2. Ép collation trên biểu thức

~~~sql
SELECT
    display_name
FROM people
WHERE display_name COLLATE utf8mb4_0900_ai_ci = 'nguyen';
~~~

Đây là cách minh họa ép collation cho biểu thức; literal/column phải tương thích character set. MySQL còn có quy tắc **collation coercibility** để xác định collation kết quả khi biểu thức kết hợp nhiều nguồn.

### 15.3. CI/AI và binary

Các collation hậu tố **_ci** thường không phân biệt hoa/thường; **_ai** không phân biệt dấu; **_as_cs** phân biệt dấu và hoa/thường trong những tên tương ứng; **_bin** so sánh theo binary.

Không phải mọi collation có cùng padding rule. Một số collation cũ dùng **PAD SPACE**, trong khi một số collation Unicode mới như 0900 dùng **NO PAD**. Điều này có thể ảnh hưởng so sánh chuỗi có khoảng trắng cuối và UNIQUE.

### 15.4. Xem cấu hình

~~~sql
SELECT
    @@character_set_server AS server_charset,
    @@collation_server AS server_collation,
    @@character_set_database AS database_charset,
    @@collation_database AS database_collation;

SHOW FULL COLUMNS FROM people;
~~~

Kiểm tra **collation thực tế của cột** quan trọng hơn việc chỉ nhìn cấu hình server, vì cột có thể override.

## 16. SQL Server: collation là một phần quan trọng của kiểu chuỗi

SQL Server gắn collation ở server, database, column và expression. Tên collation thường có hậu tố như **CI/CS**, **AI/AS**, **BIN2**, **SC** hoặc **UTF8**.

### 16.1. Ví dụ collation không phân biệt case/accent

~~~sql
SELECT
    CASE
      WHEN N'cafe' COLLATE Latin1_General_100_CI_AI
         = N'CAFÉ' COLLATE Latin1_General_100_CI_AI
      THEN 'EQUAL'
      ELSE 'NOT EQUAL'
    END AS comparison_result;
~~~

Đây là ví dụ minh họa cho collation CI/AI trên một hệ có collation đó. Tên cụ thể phải tồn tại trên SQL Server instance:

~~~sql
SELECT name
FROM sys.fn_helpcollations()
WHERE name LIKE 'Latin1_General%CI%AI%';
~~~

### 16.2. Ép COLLATE cho cột/biểu thức

~~~sql
SELECT CustomerName
FROM dbo.Customers
WHERE CustomerName COLLATE Latin1_General_100_CI_AI = N'NGUYEN';
~~~

Việc ép collation có thể làm truy vấn khó dùng index hiện có nếu collation biểu thức khác collation của cột/index. Nếu nhu cầu tìm kiếm khác biệt là thường xuyên, cân nhắc thiết kế cột/index có collation phù hợp thay vì luôn ép trên mọi truy vấn.

### 16.3. varchar và nvarchar

SQL Server có:

- **varchar:** dữ liệu ký tự theo code page/collation; có thể dùng UTF-8 với collation hỗ trợ UTF-8.
- **nvarchar:** Unicode theo mô hình UTF-16.

Literal Unicode thường dùng tiền tố **N**:

~~~sql
SELECT N'Điện thoại và cà phê';
~~~

Nếu bỏ N trong môi trường code page không hỗ trợ ký tự cần lưu, dữ liệu literal có thể bị chuyển đổi/mất ký tự trước khi được lưu.

### 16.4. LEN và khoảng trắng cuối

SQL Server **LEN** bỏ qua trailing spaces, còn **DATALENGTH** đo byte lưu trữ. Đừng dùng LEN để kiểm tra kích thước byte hoặc kiểm tra một trường có giữ khoảng trắng cuối hay không.

## 17. Oracle: NLS và collation

Oracle có cơ chế **NLS_SORT**, **NLS_COMP** và collation theo biểu thức/cột tùy phiên bản.

### 17.1. Xem NLS

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_COMP',
    'NLS_SORT',
    'NLS_LENGTH_SEMANTICS'
)
ORDER BY parameter;
~~~

### 17.2. So sánh không phân biệt case/accent

Oracle có thể sử dụng linguistic sort keys như **BINARY_CI** hoặc **BINARY_AI** qua NLS_SORT ở những ngữ cảnh phù hợp:

~~~sql
ALTER SESSION SET NLS_COMP = LINGUISTIC;
ALTER SESSION SET NLS_SORT = BINARY_AI;

SELECT customer_name
FROM customers
WHERE customer_name = 'cafe';
~~~

Thiết lập session ảnh hưởng các phép so sánh chịu NLS_COMP/NLS_SORT theo quy tắc Oracle. Không coi đây là thay đổi collation toàn database hoặc mặc định cho mọi connection.

### 17.3. NLSSORT

~~~sql
SELECT
    customer_name
FROM customers
ORDER BY NLSSORT(
    customer_name,
    'NLS_SORT=BINARY_CI'
);
~~~

NLSSORT tạo sort key theo quy tắc linguistic được chỉ định. Có thể dùng function-based index nếu cần tối ưu hóa truy vấn thường xuyên, nhưng cần quản lý cùng biểu thức và NLS parameters.

### 17.4. CHAR semantics và BYTE semantics

Trong Oracle, cột có thể được khai báo theo **BYTE** hoặc **CHAR** semantics:

~~~sql
CREATE TABLE name_demo (
    name_byte VARCHAR2(30 BYTE),
    name_char VARCHAR2(30 CHAR)
);
~~~

Với ký tự UTF-8 nhiều byte, hai giới hạn này có ý nghĩa khác nhau. Hãy xác định yêu cầu theo ký tự hay byte thay vì chọn 30 rồi giả định hai cột chứa cùng số lượng ký tự.

### 17.5. Chuỗi rỗng của Oracle

Oracle coi **zero-length character string** như NULL trong nhiều ngữ cảnh SQL:

~~~sql
SELECT
    CASE WHEN '' IS NULL THEN 'EMPTY IS NULL' ELSE 'OTHER' END
FROM dual;
~~~

Điều này ảnh hưởng nối chuỗi, NULLIF, UNIQUE, so sánh và logic ứng dụng. Không port giả định “empty string khác NULL” từ PostgreSQL/MySQL/SQL Server sang Oracle.

## 18. SQLite: BINARY, NOCASE, RTRIM và Unicode

SQLite có các collation built-in thường gặp:

- **BINARY:** so sánh theo biểu diễn byte/code point theo quy tắc SQLite.
- **NOCASE:** không phân biệt hoa/thường cho các ký tự ASCII theo hành vi built-in.
- **RTRIM:** bỏ qua khoảng trắng ASCII cuối trong so sánh theo quy tắc collation.

### 18.1. COLLATE

~~~sql
CREATE TABLE people (
    name TEXT COLLATE NOCASE
);

SELECT name
FROM people
WHERE name = 'nguyen';
~~~

NOCASE built-in của SQLite **không phải Unicode case folding đầy đủ**. Đừng giả định nó xử lý mọi chữ cái tiếng Việt hoặc mọi ngôn ngữ ngoài ASCII giống một ICU collation.

### 18.2. LIKE trong SQLite

SQLite mặc định có hành vi LIKE không phân biệt hoa/thường đối với ASCII trong nhiều trường hợp, nhưng ký tự Unicode ngoài ASCII có thể vẫn phân biệt. Ví dụ các cặp chữ cái có dấu không được bảo đảm case-fold như người dùng mong muốn.

Nếu cần Unicode-aware case-insensitive search, có thể dùng **ICU extension** hoặc đăng ký collation/function riêng trong host application.

### 18.3. COLLATE không tự thay đổi LIKE mọi trường hợp

Không suy luận rằng chỉ đặt COLLATE NOCASE là mọi phép LIKE/regex/substring trong SQLite trở thành Unicode-insensitive. Mỗi toán tử có quy tắc riêng; cần test trên bản SQLite và extension thực tế.

## 19. Unicode normalization và dữ liệu trông giống nhau

Một chữ “é” có thể được biểu diễn:

~~~text
U+00E9                 → é (precomposed)
U+0065 U+0301          → e + combining acute accent
~~~

Hai chuỗi có thể hiển thị giống nhau nhưng byte/code point khác nhau. Nếu hệ thống so sánh theo binary, chúng có thể không bằng nhau.

### 19.1. NFC và NFD

- **NFC:** dạng Unicode composition chuẩn hóa, thường ghép các tổ hợp có thể ghép.
- **NFD:** dạng decomposition, tách ký tự thành base + combining mark.

NFKC/NFKD còn áp dụng compatibility normalization và có thể làm thay đổi biểu diễn của một số ký tự tương thích. Không áp dụng normalization compatibility một cách mù quáng cho mã định danh hoặc dữ liệu pháp lý.

### 19.2. Database không phải lúc nào cũng tự chuẩn hóa khi INSERT

Lưu chuỗi UTF-8 không đồng nghĩa mọi hệ sẽ chuyển NFC/NFD về một dạng thống nhất. Nếu ứng dụng nhận dữ liệu từ web, file CSV, thiết bị di động và API ngoài, hãy xác định:

1. Chuẩn hóa ở đâu: ứng dụng hay database?
2. Dùng NFC hay chính sách khác?
3. Có giữ bản gốc phục vụ pháp lý/audit không?
4. UNIQUE có xét hai dạng tương đương hay không?
5. Index/search có được rebuild sau khi đổi quy tắc không?

### 19.3. Bỏ dấu không phải chuẩn hóa Unicode đơn thuần

Chuyển “cà phê” thành “ca phe” là một chính sách **accent folding** hoặc transliteration, không chỉ là NFC/NFD. Nó có thể làm mất phân biệt giữa những từ khác nghĩa trong ngôn ngữ có dấu. Chỉ dùng khi nghiệp vụ chấp nhận đánh đổi và có kiểm thử.

## 20. Collation ảnh hưởng UNIQUE và GROUP BY

Giả sử có hai tên:

~~~text
An
AN
~~~

Nếu collation không phân biệt hoa/thường, hai giá trị có thể được coi là bằng nhau trong so sánh. Khi đó:

- GROUP BY có thể gom thành một nhóm.
- DISTINCT có thể loại một giá trị trùng theo collation.
- UNIQUE index/constraint có thể từ chối lưu cả hai giá trị.
- JOIN theo cột chuỗi có thể khớp nhiều hơn so với binary comparison.

### 20.1. Chọn collation trước khi tạo UNIQUE

Nếu username cần phân biệt hoa/thường, collation CI có thể không đúng yêu cầu. Nếu username không phân biệt case, cần thống nhất cách canonicalize và xử lý conflict khi hai tài khoản khác nhau chỉ bởi case.

**Collation là một phần của mô hình định danh**, không chỉ là cách sắp xếp cho đẹp.

### 20.2. Email và mã định danh

Không tự ý dùng collation AI/CI cho mọi trường:

- Tên hiển thị có thể cần sort thân thiện ngôn ngữ.
- Username có thể cần canonical form và quy tắc uniqueness rõ.
- Email có quy tắc so sánh phụ thuộc hệ thống/nhà cung cấp; không tự động giả định local-part luôn case-insensitive.
- Mã đơn/SKU có thể cần so khớp chính xác theo hợp đồng.
- Dữ liệu văn bản dài có thể dùng collation khác với cột khóa.

## 21. Collation và index

Index được xây theo quy tắc so sánh/collation của biểu thức hoặc cột. Khi truy vấn dùng collation khác, database có thể không dùng index cũ như mong đợi.

### 21.1. Tránh bọc cột bằng LOWER tùy tiện

~~~sql
SELECT *
FROM users
WHERE LOWER(username) = LOWER($1);
~~~

Điều kiện này có thể không dùng index B-tree thường trên username, vì biểu thức tìm kiếm là LOWER(username).

Các lựa chọn:

- Dùng collation case-insensitive phù hợp cho cột/index.
- Tạo expression/function-based index trên LOWER(username).
- Lưu cột normalized riêng, duy trì nhất quán.

### 21.2. PostgreSQL expression index

~~~sql
CREATE INDEX users_username_lower_idx
ON users (LOWER(username));

SELECT *
FROM users
WHERE LOWER(username) = LOWER('AnNguyen');
~~~

Expression index chỉ hữu ích khi truy vấn dùng biểu thức tương thích. Cần cân nhắc chi phí cập nhật và semantics Unicode của LOWER/collation.

### 21.3. MySQL

Nếu cột dùng collation CI thích hợp, equality có thể tận dụng index trên cột. Nếu áp dụng hàm/CAST/COLLATE khác trên cột, planner có thể không dùng index như trước; hãy EXPLAIN.

### 21.4. SQL Server

Có thể tạo cột computed phù hợp và index nếu biểu thức đáp ứng điều kiện indexable/persisted của SQL Server, hoặc thiết kế collation cột đúng từ đầu. Ép COLLATE khác trên mọi truy vấn có thể tạo conversion và làm giảm khả năng seek.

### 21.5. Oracle

Với NLSSORT hoặc LOWER, cân nhắc **function-based index** trên cùng biểu thức/sort key. Cấu hình NLS phải được quản lý nhất quán để truy vấn dùng được index đúng ý.

### 21.6. SQLite

SQLite hỗ trợ index với COLLATE cụ thể:

~~~sql
CREATE INDEX people_name_nocase_idx
ON people(name COLLATE NOCASE);
~~~

Truy vấn phải dùng quy tắc so sánh phù hợp để index được sử dụng. NOCASE built-in vẫn chỉ có phạm vi Unicode hạn chế như đã nêu.

## 22. SQL động, bind parameter và wildcard

Chuỗi người dùng không được nối trực tiếp vào SQL:

~~~text
sql = "SELECT * FROM users WHERE name = '" + input + "'"
~~~

Đây là mẫu dễ tạo SQL injection.

Dùng bind parameter:

~~~sql
-- PostgreSQL
PREPARE find_user(TEXT) AS
SELECT user_id, username
FROM users
WHERE username = $1;

EXECUTE find_user('An Nguyen');
DEALLOCATE find_user;
~~~

Hoặc dùng placeholder của driver như **?** trong JDBC.

### 22.1. Bind parameter không thể thay tên cột

Không thể dùng một placeholder value để thay một identifier như tên bảng/cột trong mọi SQL API:

~~~sql
SELECT ? FROM users;
~~~

Truy vấn này thường trả giá trị tham số như một biểu thức, không chọn cột có tên trùng giá trị đó. Nếu cần dynamic column/order:

1. Dùng allowlist tên cột hợp lệ.
2. Map lựa chọn người dùng sang identifier cố định trong code.
3. Quote identifier bằng API phù hợp của driver/database.
4. Không ghép raw input thành tên bảng/cột.

### 22.2. Tìm chuỗi literal với LIKE

Nếu người dùng nhập **100%_complete** và muốn tìm đúng những ký tự này, phải escape wildcard:

~~~sql
-- PostgreSQL-style pattern: dấu ! làm escape
SELECT *
FROM products
WHERE product_name LIKE '%' ||
      REPLACE(
        REPLACE(
          REPLACE($1, '!', '!!'),
          '%', '!%'
        ),
        '_', '!_'
      ) || '%'
ESCAPE '!';
~~~

Thứ tự escape quan trọng: escape chính ký tự escape trước, rồi mới escape % và _. Nếu không, ký tự vừa thêm có thể bị escape lần nữa.

### 22.3. SQL injection và wildcard là hai vấn đề khác nhau

Prepared statement ngăn input trở thành cú pháp SQL, nhưng người dùng vẫn có thể nhập **%** để yêu cầu pattern rộng nếu ứng dụng đưa pattern vào LIKE. Nếu nghiệp vụ là tìm literal substring, phải escape wildcard; nếu nghiệp vụ cho phép người dùng tự viết pattern, hãy giới hạn độ dài và chi phí truy vấn.

## 23. Các hàm hữu ích khác

### 23.1. LOWER và UPPER

~~~sql
SELECT
    LOWER('PostgreSQL') AS lower_value,
    UPPER('PostgreSQL') AS upper_value;
~~~

Đây là chuyển đổi hoa/thường theo quy tắc encoding/locale của hệ. Không tự đồng nghĩa với Unicode case folding hoàn chỉnh cho mọi ngôn ngữ, cũng không phải cách duy nhất để tìm case-insensitive.

### 23.2. REVERSE

Một số hệ có REVERSE:

~~~sql
SELECT REVERSE('SQL');
~~~

Kết quả **LQS**. Cách xử lý chuỗi Unicode phức tạp (combining marks/emoji) có thể không giống đảo grapheme cluster mà người dùng mong muốn.

### 23.3. LPAD và RPAD

~~~sql
-- PostgreSQL / Oracle-style
SELECT
    LPAD('42', 5, '0') AS left_padded,
    RPAD('SQL', 6, '.') AS right_padded;
~~~

Kết quả **00042** và **SQL...**. MySQL cũng hỗ trợ LPAD/RPAD; SQL Server thường dùng REPLICATE/RIGHT/CONCAT theo yêu cầu; SQLite không có cùng bộ hàm chuẩn trên mọi phiên bản.

### 23.4. SPLIT_PART, SUBSTRING_INDEX và STRING_SPLIT

Các hệ cung cấp cách tách chuỗi khác nhau:

- PostgreSQL: **split_part(string, delimiter, field)**.
- MySQL: **SUBSTRING_INDEX(str, delim, count)**.
- SQL Server: **STRING_SPLIT** trên phiên bản hỗ trợ, có tùy chọn ordinal ở phiên bản tương ứng.
- Oracle: có REGEXP_SUBSTR và các hàm khác.
- SQLite: thường dùng recursive CTE hoặc xử lý ở ứng dụng; không mặc định có STRING_SPLIT tương đương.

Ví dụ PostgreSQL:

~~~sql
SELECT split_part('sales.eu.orders', '.', 2) AS region;
~~~

Kết quả **eu**.

Ví dụ MySQL:

~~~sql
SELECT SUBSTRING_INDEX('sales.eu.orders', '.', 2) AS prefix;
~~~

Kết quả **sales.eu**.

Không dùng một cú pháp tách chuỗi của hệ này cho hệ khác mà không chuyển đổi quy tắc delimiter, vị trí và ordinal.

## 24. Ma trận khác biệt hàm chuỗi

| Nhu cầu | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Length ký tự | CHAR_LENGTH | CHAR_LENGTH | LEN (bỏ trailing spaces) | LENGTH | length(TEXT) |
| Length byte | OCTET_LENGTH | LENGTH | DATALENGTH | LENGTHB | length(BLOB) |
| Substring | SUBSTRING/SUBSTR | SUBSTRING/SUBSTR | SUBSTRING | SUBSTR | substr |
| Vị trí | POSITION/STRPOS | LOCATE/INSTR | CHARINDEX | INSTR | instr |
| Nối chuỗi | \|\|, concat | CONCAT | +, CONCAT | \|\|, CONCAT (2 args) | \|\|, concat |
| Nối bỏ NULL | concat/concat_ws | CONCAT_WS | CONCAT/CONCAT_WS | CASE/biểu thức riêng | concat_ws bản hỗ trợ |
| Trim | TRIM/LTRIM/RTRIM | TRIM/LTRIM/RTRIM | TRIM/LTRIM/RTRIM | TRIM/LTRIM/RTRIM | trim/ltrim/rtrim |
| Thay chuỗi | REPLACE | REPLACE | REPLACE | REPLACE | replace |
| Ánh xạ ký tự | TRANSLATE | Không cùng bộ cú pháp phổ biến | TRANSLATE (2017+) | TRANSLATE | replace/host |
| Collation expression | COLLATE | COLLATE | COLLATE | COLLATE/NLS/NLSSORT | COLLATE |

## 25. Ma trận collation và Unicode

| Hệ | Cấu hình chính | Case/accent | Lưu ý |
| --- | --- | --- | --- |
| PostgreSQL | Database/column/expression collation; libc/ICU | ILIKE; ICU collations | Có deterministic/nondeterministic collation và version dependency |
| MySQL | Character set + collation ở server/database/table/column/expression | Hậu tố CI/CS, AI/AS, BIN | utf8mb4; PAD SPACE/NO PAD tùy collation |
| SQL Server | Server/database/column/expression collation | CI/CS, AI/AS, BIN2, SC, UTF8 | varchar/nvarchar; N prefix cho Unicode literal |
| Oracle | NLS_SORT/NLS_COMP, COLLATE, NLSSORT | BINARY_CI/BINARY_AI và linguistic sort | BYTE/CHAR semantics; chuỗi rỗng thường là NULL |
| SQLite | BINARY, NOCASE, RTRIM hoặc custom/ICU | NOCASE built-in chủ yếu ASCII | LIKE Unicode không đầy đủ nếu thiếu ICU/custom logic |

## 26. Kiểm thử hàm chuỗi và collation

Một test suite tốt nên có:

| Nhóm | Input cần thử | Điều cần xác nhận |
| --- | --- | --- |
| NULL | NULL, empty string, chuỗi có khoảng trắng | Chính sách NULL/rỗng |
| Độ dài | ASCII, tiếng Việt, emoji, combining mark | Byte/code point/grapheme |
| Cắt chuỗi | start 1, start âm, length 0, ngoài giới hạn | Quy tắc 1-based và boundary |
| Nối | NULL ở đầu/giữa/cuối, separator NULL | Semantics từng hàm |
| Trim | space, tab, newline, NBSP | Tập ký tự bị loại |
| Case | abc/ABC | Collation CI/CS |
| Accent | cafe/café | Collation AI/AS |
| Unicode | NFC/NFD | Canonical equality |
| Tra cứu | substring, whole token, prefix | Ngữ nghĩa hàm |
| Sort/group | tên có dấu và chữ hoa | Locale ordering |
| UNIQUE | hai chuỗi chỉ khác case/accent | Xung đột theo collation |
| Injection | quote, %, _, identifier | Bind/escape |

### 26.1. Test nối NULL

Không chỉ test chuỗi có đủ ba phần. Hãy test:

~~~text
first = NULL, middle = 'Van', last = 'An'
first = 'Le', middle = NULL, last = 'An'
first = 'Le', middle = '', last = NULL
separator = NULL
~~~

Ghi rõ kết quả mong muốn trước khi chọn CONCAT, CONCAT_WS, || hoặc COALESCE.

### 26.2. Test Unicode normalization

Tạo hai chuỗi trông giống nhau nhưng khác biểu diễn Unicode từ ứng dụng test; so sánh:

- Byte sequence.
- Length theo từng hàm.
- Equality theo collation.
- UNIQUE index.
- Kết quả search/ORDER BY.

Không tạo test chỉ bằng cách gõ hai chuỗi nhìn giống nhau trong cùng editor rồi cho rằng code point chắc chắn khác; nên tạo input theo Unicode code point cụ thể.

### 26.3. Test collation sau nâng cấp

Nếu nâng cấp ICU, libc, MySQL collation version hoặc đổi database collation, cần đánh giá:

- Kết quả sort có thay đổi không?
- Hai giá trị từng khác nhau giờ có bị coi bằng không?
- UNIQUE index có xung đột không?
- Index có cần rebuild không?
- Ứng dụng có phụ thuộc thứ tự phân trang cũ không?

## 27. Lựa chọn chiến lược dữ liệu chuỗi

Trước khi tạo cột và index, hãy trả lời:

1. Dữ liệu có cần giữ nguyên bản gốc không?
2. Có cần phân biệt hoa/thường không?
3. Có cần phân biệt dấu không?
4. Khoảng trắng đầu/cuối có có ý nghĩa không?
5. Độ dài giới hạn theo byte, code point hay grapheme?
6. Có cần tìm kiếm theo substring, prefix hay equality?
7. Có cần sắp xếp theo ngôn ngữ?
8. Có cần unique theo canonical form?
9. Có nhiều database engine cần dùng chung dữ liệu không?
10. Khi thay collation, migration/index được quản lý thế nào?

### 27.1. Không ép mọi cột dùng một collation

Một hệ thống có thể cần:

- **username:** canonical case-insensitive uniqueness theo hợp đồng đăng nhập.
- **display_name:** linguistic sorting thân thiện người dùng.
- **sku:** exact/binary comparison.
- **search_text:** normalized hoặc full-text pipeline.
- **legal_name:** giữ nguyên bản gốc, không tự ý bỏ dấu.

Collation phù hợp phụ thuộc mục tiêu của từng trường.

### 27.2. Lưu cả raw và normalized khi cần

Một thiết kế có thể có:

~~~text
display_name_raw
display_name_normalized
~~~

Raw dùng hiển thị/audit; normalized dùng tìm kiếm hoặc uniqueness theo chính sách. Cần xác định:

- Ai cập nhật normalized?
- Chuẩn hóa bằng thuật toán/version nào?
- Có rebuild dữ liệu khi đổi thuật toán không?
- Unique index đặt trên raw hay normalized?
- Có giữ dấu và chữ gốc để không làm mất thông tin không?

Không để hai cột lệch nhau; có thể dùng generated column, trigger hoặc ứng dụng theo khả năng hệ.

## 28. Những lỗi thường gặp

| Lỗi/nhầm lẫn | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng LENGTH và nghĩ luôn đếm ký tự | MySQL LENGTH đếm byte | Dùng hàm đúng đơn vị |
| Dùng SQL Server LEN để đo byte | LEN bỏ trailing spaces | Dùng DATALENGTH |
| Dùng Oracle LENGTH thay LENGTHB khi cần byte | Giới hạn lưu trữ sai | Chọn LENGTHB/BYTE semantics |
| Coi code point là ký tự hiển thị | Cắt emoji/dấu tổ hợp sai | Grapheme-aware ở tầng Unicode |
| Coi SUBSTRING mọi hệ có cùng chỉ số | Off-by-one hoặc kết quả khác | Kiểm tra 1-based, negative start |
| Nhầm thứ tự LOCATE/INSTR | Tìm sai chuỗi | Ghi rõ signature từng hệ |
| Dùng REPLACE để thay từ độc lập | Thay cả substring trong từ khác | Token/regex/FTS phù hợp |
| Nghĩ TRIM bỏ mọi Unicode whitespace | Dữ liệu vẫn còn NBSP/tab | Định nghĩa tập ký tự cần xử lý |
| Dùng || trên MySQL mặc định | Có thể thành logical OR | Dùng CONCAT |
| Nghĩ || + NULL giống nhau mọi hệ | Kết quả NULL/chuỗi khác nhau | Xác định NULL policy |
| Dùng CONCAT mà quên MySQL NULL | Toàn kết quả thành NULL | CONCAT_WS/COALESCE theo yêu cầu |
| Dùng CONCAT_WS với separator NULL | Kết quả NULL | Validate separator |
| Coi Oracle empty string khác NULL | Logic nối/unique sai | Kiểm tra Oracle empty-string semantics |
| Dùng LOWER để tìm CI mà không xét index | Query có thể scan | Collation/index biểu thức phù hợp |
| Coi UTF-8 là collation | Sort/equality không đúng mong muốn | Chọn collation riêng |
| Coi AI luôn an toàn cho tên/mã | Gộp giá trị đáng lẽ khác nhau | Chọn theo business identity |
| Coi NOCASE SQLite là Unicode đầy đủ | Case tiếng Việt không như mong muốn | ICU/custom collation |
| Coi NFC/NFD tự được chuẩn hóa khi INSERT | Hai chuỗi nhìn giống nhưng khác | Normalize rõ ở pipeline |
| Bỏ dấu bằng REPLACE thủ công | Mất ký tự và lỗi dữ liệu | Chính sách normalization/locale |
| Tạo UNIQUE trước khi chốt collation | Migration có thể xung đột | Xác định equality trước |
| Ép COLLATE khác trên cột trong mọi query | Index không được dùng | Thiết kế index/cột đúng collation |
| Nối raw input vào SQL | SQL injection | Prepared statement |
| Bind pattern LIKE nhưng không escape %/_ | User mở rộng pattern | Escape nếu cần literal |
| Bind tên cột như value parameter | Không chọn identifier động | Allowlist/quote identifier |
| Dựa vào thứ tự ORDER BY ngầm định | Phân trang không ổn định | ORDER BY rõ ràng |

## 29. Bài tập thực hành

Các bài tập nên chạy riêng trên từng RDBMS. Không gửi nguyên một đoạn SQL của PostgreSQL cho MySQL/SQL Server/Oracle/SQLite rồi mong mọi hàm có cùng tên và semantics.

1. Tạo bảng people với CHAR, VARCHAR và một trường ghi chú dài theo hệ đang học.
2. So sánh CHAR_LENGTH/LENGTH/OCTET_LENGTH trên PostgreSQL.
3. So sánh CHAR_LENGTH và LENGTH trên MySQL với chuỗi tiếng Việt UTF-8.
4. So sánh LEN và DATALENGTH trên SQL Server, bao gồm chuỗi có trailing spaces.
5. So sánh LENGTH và LENGTHB trên Oracle; thử BYTE và CHAR semantics.
6. So sánh length(TEXT) và length(BLOB) trên SQLite.
7. Giải thích byte, code point và grapheme cluster bằng ví dụ emoji.
8. Viết SUBSTRING lấy bốn ký tự đầu của PostgreSQL trên năm hệ.
9. Thử vị trí âm trong SUBSTR/SUBSTRING; ghi hệ nào hỗ trợ và kết quả.
10. Chuyển Java substring(0,4) thành SQL SUBSTRING đúng chỉ số.
11. Dùng POSITION/STRPOS, LOCATE/INSTR, CHARINDEX, INSTR và SQLite instr tìm “SQL”.
12. Tìm lần xuất hiện thứ hai bằng Oracle INSTR.
13. Dùng REPLACE thay SQL trong “PostgreSQL, MySQL”; giải thích vì sao thay substring.
14. Dùng TRANSLATE đổi tập ký tự abc thành ABC trên hệ hỗ trợ.
15. So sánh TRIM/BOTH/LTRIM/RTRIM; thử tab, newline và NBSP.
16. Nối ba phần họ/tên có NULL bằng PostgreSQL ||, concat và concat_ws.
17. Chạy CONCAT với NULL trên MySQL và so sánh CONCAT_WS.
18. So sánh SQL Server +, CONCAT và CONCAT_WS khi một đối số NULL.
19. Kiểm tra Oracle nối chuỗi rỗng và NULL.
20. Kiểm tra SQLite || và concat trên phiên bản đang sử dụng.
21. Dùng COALESCE/NULLIF để chuyển chuỗi chỉ có dấu cách thành NULL.
22. So sánh equality của abc/ABC với CI và CS collation.
23. So sánh cafe/café với AI và AS collation.
24. Xem danh sách collation có sẵn trên MySQL hoặc SQL Server.
25. Dùng PostgreSQL COLLATE "C" và so với collation mặc định.
26. Dùng Oracle NLS_SORT/NLS_COMP hoặc NLSSORT để sắp xếp tên.
27. Dùng SQLite NOCASE để so sánh chữ ASCII và chữ tiếng Việt có dấu.
28. Tạo hai chuỗi NFC/NFD trông giống nhau, so byte và equality.
29. Tạo UNIQUE index với collation CI/AI và thử chèn hai giá trị khác case/dấu.
30. Viết prepared statement tìm username bằng equality.
31. Viết LIKE tìm chuỗi literal có % và _, escape theo một ký tự riêng.
32. Thiết kế allowlist cho ORDER BY column động, giải thích vì sao không bind identifier.
33. Tạo expression index LOWER(username) và chạy EXPLAIN truy vấn tương ứng.
34. Thiết kế raw/normalized column cho tìm kiếm không dấu, mô tả cách đồng bộ.
35. Lập test matrix cho NULL, empty string, Unicode, trailing spaces, collation và uniqueness.

### Câu hỏi tự kiểm tra

**Câu 1.** MySQL LENGTH và CHAR_LENGTH luôn trả cùng giá trị?

**Đáp án:** **Không.** LENGTH trả byte; CHAR_LENGTH trả số ký tự theo character set.

**Câu 2.** SQL Server LEN có tính trailing spaces không?

**Đáp án:** **Không.** LEN bỏ khoảng trắng cuối; DATALENGTH đo byte.

**Câu 3.** Unicode code point luôn bằng một ký tự người dùng nhìn thấy?

**Đáp án:** **Không.** Một grapheme cluster có thể gồm nhiều code point.

**Câu 4.** PostgreSQL || và concat có cùng hành vi khi một đối số NULL?

**Đáp án:** **Không.** || trả NULL; concat bỏ qua đối số NULL.

**Câu 5.** MySQL || mặc định luôn là nối chuỗi?

**Đáp án:** **Không.** Nó thường là logical OR; chế độ SQL riêng có thể thay đổi semantics.

**Câu 6.** Oracle có coi chuỗi rỗng khác NULL như PostgreSQL không?

**Đáp án:** **Không.** Oracle coi zero-length character string như NULL trong nhiều ngữ cảnh.

**Câu 7.** UTF-8 có tự quyết định so sánh không phân biệt dấu không?

**Đáp án:** **Không.** Encoding và collation là hai khái niệm khác nhau.

**Câu 8.** Collation CI/AI có thể ảnh hưởng UNIQUE không?

**Đáp án:** **Có.** Giá trị khác case/dấu có thể được coi tương đương theo collation.

**Câu 9.** SQLite NOCASE built-in có Unicode case folding đầy đủ không?

**Đáp án:** **Không.** Phạm vi built-in chủ yếu là ASCII; cần ICU/custom logic cho yêu cầu Unicode.

**Câu 10.** Bind parameter có tự escape wildcard % và _ trong LIKE không?

**Đáp án:** **Không.** Bind chống việc input trở thành cú pháp SQL; wildcard vẫn có ý nghĩa pattern.

**Câu 11.** Có thể bind tên cột vào ORDER BY như bind một giá trị không?

**Đáp án:** **Không theo cách placeholder value thông thường.** Cần allowlist và quote identifier an toàn.

**Câu 12.** Có thể đổi collation mà không kiểm tra UNIQUE/index không?

**Đáp án:** **Không nên.** Quy tắc bằng nhau/sắp xếp có thể thay đổi và gây xung đột hoặc cần rebuild index.

## 30. Ghi nhớ cốt lõi

**Hàm chuỗi xử lý nội dung; collation quyết định cách đối chiếu nội dung đó.** Hãy chọn đúng hàm cho đơn vị đo và mục đích, rồi chọn collation theo quy tắc nghiệp vụ.

Những điểm cần nhớ khi viết SQL đa hệ:

~~~text
Độ dài:
  PostgreSQL  CHAR_LENGTH / OCTET_LENGTH
  MySQL       CHAR_LENGTH / LENGTH
  SQL Server  LEN / DATALENGTH
  Oracle      LENGTH / LENGTHB / LENGTHC / LENGTH2 / LENGTH4
  SQLite      length(TEXT) / length(BLOB)

Tìm vị trí:
  PostgreSQL  POSITION / STRPOS
  MySQL       LOCATE / INSTR
  SQL Server  CHARINDEX
  Oracle      INSTR
  SQLite      instr

Nối chuỗi:
  PostgreSQL  || / concat / concat_ws
  MySQL       CONCAT / CONCAT_WS
  SQL Server  + / CONCAT / CONCAT_WS
  Oracle      ||
  SQLite      || / concat (bản hỗ trợ)
~~~

Đừng giả định **NULL khi nối**, **chuỗi rỗng**, **trailing spaces**, **đơn vị độ dài**, **chỉ số SUBSTRING** hoặc **case/accent sensitivity** giống nhau giữa các hệ. UTF-8 là encoding, còn collation là quy tắc so sánh; code point không luôn là grapheme cluster. Với dữ liệu tiếng Việt và đa ngôn ngữ, cần kiểm thử Unicode normalization, dấu và sắp xếp trên đúng engine.

Cuối cùng, dùng bind parameter để tách input khỏi cú pháp SQL, escape wildcard khi tìm literal bằng LIKE, và allowlist identifier khi cần SQL động. Index phải phù hợp biểu thức/collation của truy vấn. Một thiết kế tốt giữ rõ bản gốc, quy tắc normalized, uniqueness và thứ tự sắp xếp, để hành vi dữ liệu không thay đổi bất ngờ khi chuyển môi trường hoặc nâng cấp database.
