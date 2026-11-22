# Chuyển đổi CLOB/BLOB, charset và xử lý tiếng Việt

Khi lưu và trao đổi văn bản tiếng Việt trong Oracle, cần phân biệt ba lớp dữ liệu: ký tự Unicode mà người dùng nhìn thấy, byte được dùng để mã hóa ký tự, và kiểu LOB dùng để lưu nội dung lớn. Một CLOB lưu văn bản theo database character set; NCLOB lưu văn bản theo national character set; BLOB lưu byte nhị phân và không tự mang ý nghĩa charset.

Nhiều lỗi tiếng Việt như chữ bị biến thành dấu hỏi, ký tự mojibake kiểu “Tiáº¿ng Viá»‡t”, mất dấu hoặc sai khi xuất/nhập file xuất phát từ việc diễn giải byte bằng charset không đúng, chuyển đổi sang charset không biểu diễn được ký tự, hoặc so sánh hai chuỗi Unicode có dạng chuẩn hóa khác nhau.

Bài học này trình bày:

- Database character set và national character set của Oracle.
- Sự khác nhau giữa CHAR/VARCHAR2, NCHAR/NVARCHAR2, CLOB/NCLOB, BLOB và BFILE.
- LOB locator, temporary LOB và các thao tác DBMS_LOB.
- Chuyển đổi CLOB sang BLOB và BLOB sang CLOB đúng charset.
- Đọc/ghi file lớn, streaming và giới hạn buffer.
- Unicode tiếng Việt, dạng dựng sẵn và dạng tổ hợp dấu.
- NLS, client encoding, JDBC, SQL*Loader và chẩn đoán lỗi mojibake.

Các ví dụ dùng Oracle Database 19c. Trước khi chuyển đổi dữ liệu thật, hãy thử trên bản sao, xác định charset nguồn và đích, kiểm tra ký tự không biểu diễn được, rồi xác nhận kết quả bằng dữ liệu mẫu tiếng Việt.

## 1. Ký tự, charset và byte là ba khái niệm khác nhau

Một chuỗi hiển thị như “Tiếng Việt” là dãy ký tự. Khi lưu hoặc truyền qua file/network, dãy ký tự được mã hóa thành byte theo một character set/encoding cụ thể.

Ví dụ:

~~~text
Ký tự:       ế
Unicode:     U+1EBF
UTF-8 bytes: E1 BA BF
~~~

Byte E1 BA BF chỉ có ý nghĩa là ký tự ế khi được giải mã theo UTF-8. Nếu cùng byte được diễn giải theo một charset khác, kết quả có thể là ký tự lạ hoặc mojibake.

### 1.1. Character set không phải collation

- Character set xác định cách biểu diễn ký tự và byte.
- Collation xác định cách so sánh/sắp xếp chuỗi theo quy tắc ngôn ngữ hoặc nhị phân.
- Unicode normalization xác định cách biểu diễn tương đương của một ký tự bằng chuỗi code point.

Ba khái niệm này liên quan nhưng không thay thế nhau. Đổi NLS_SORT không sửa byte đã bị giải mã sai. Đổi charset không tự chuẩn hóa chuỗi. Chuẩn hóa Unicode cũng không thể khôi phục ký tự đã bị thay bằng dấu hỏi khi chuyển đổi mất dữ liệu.

### 1.2. AL32UTF8 và UTF8 trong Oracle

Oracle thường khuyến nghị dùng AL32UTF8 làm database character set cho ứng dụng Unicode mới. AL32UTF8 là cách Oracle đặt tên cho UTF-8 chuẩn, hỗ trợ đầy đủ Unicode, gồm cả ký tự ngoài Basic Multilingual Plane.

Tên UTF8 trong Oracle là một charset legacy dựa trên CESU-8, không giống UTF-8 chuẩn cho toàn bộ Unicode. Không nên chọn UTF8 chỉ vì tên giống UTF-8. Khi cần hỗ trợ tiếng Việt và Unicode hiện đại, AL32UTF8 thường là lựa chọn phù hợp.

## 2. Database character set và national character set

Oracle có hai character set riêng:

1. Database character set: dùng cho CHAR, VARCHAR2, CLOB và phần lớn literal/identifier thông thường.
2. National character set: dùng cho NCHAR, NVARCHAR2 và NCLOB.

Trong Oracle 19c, national character set thường là AL16UTF16 hoặc UTF8 legacy. Database character set và national character set được xác định khi tạo database; không nên xem việc đổi chúng như một thao tác cấu hình nhỏ.

### 2.1. Kiểm tra charset của database

~~~sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
~~~

NLS_CHARACTERSET cho biết charset của dữ liệu CHAR/VARCHAR2/CLOB. NLS_NCHAR_CHARACTERSET cho biết charset của NCHAR/NVARCHAR2/NCLOB.

### 2.2. Kiểm tra charset name và ID

~~~sql
SELECT
    NLS_CHARSET_ID('AL32UTF8') AS al32utf8_id,
    NLS_CHARSET_NAME(NLS_CHARSET_ID('AL32UTF8')) AS charset_name
FROM dual;
~~~

NLS_CHARSET_ID trả ID của charset; NLS_CHARSET_NAME chuyển ID thành tên. Các hàm này hữu ích khi truyền charset ID vào DBMS_LOB conversion API.

### 2.3. Kiểm tra NLS session

~~~sql
SELECT parameter, value
FROM nls_session_parameters
ORDER BY parameter;
~~~

NLS_SESSION_PARAMETERS phản ánh các thiết lập NLS của session như date format, numeric characters, sort và comparison. Nó không thay thế NLS_DATABASE_PARAMETERS khi cần xác định database character set.

### 2.4. NLS_LANG không phải database charset

NLS_LANG là thiết lập phía client trong môi trường OCI, gồm language, territory và client character set. Phần charset mô tả encoding mà client sử dụng khi trao đổi dữ liệu với Oracle qua OCI.

Ví dụ dạng:

~~~text
NLS_LANG=VIETNAMESE_VIETNAM.AL32UTF8
~~~

Giá trị chính xác phải phù hợp môi trường client và encoding thực tế của ứng dụng/terminal. Khai báo sai có thể khiến client gửi byte bị diễn giải sai trước khi Oracle lưu dữ liệu.

JDBC Thin dùng cơ chế Unicode của Java và không dựa vào NLS_LANG như OCI. Không sửa NLS_LANG để chữa một ứng dụng JDBC Thin nếu nguyên nhân nằm ở cách ứng dụng đọc file hoặc xử lý chuỗi.

## 3. Chọn đúng kiểu dữ liệu ký tự và LOB

| Kiểu | Nội dung | Character set/ý nghĩa |
| --- | --- | --- |
| CHAR | Chuỗi ký tự độ dài cố định | Database character set |
| VARCHAR2 | Chuỗi ký tự độ dài thay đổi | Database character set |
| NCHAR | Chuỗi độ dài cố định | National character set |
| NVARCHAR2 | Chuỗi độ dài thay đổi | National character set |
| CLOB | Character large object | Database character set |
| NCLOB | National character large object | National character set |
| BLOB | Binary large object | Byte thô, không có charset nội tại |
| BFILE | File nhị phân ngoài database | Byte của file hệ điều hành, read-only từ PL/SQL |

### 3.1. CLOB

CLOB lưu văn bản lớn theo database character set. Nếu database dùng AL32UTF8, CLOB có thể lưu văn bản tiếng Việt Unicode theo charset đó.

Các thao tác CLOB thường tính offset theo ký tự, không phải byte. Dùng DBMS_LOB.GETLENGTH để lấy độ dài LOB theo đơn vị của LOB đó.

### 3.2. NCLOB

NCLOB lưu văn bản lớn theo national character set. Nó hữu ích khi ứng dụng cần dùng NCHAR/NVARCHAR2/NCLOB để giữ ngữ nghĩa national character set độc lập với database character set.

Nếu database đã dùng AL32UTF8, CLOB thường đủ cho dữ liệu Unicode tiếng Việt. Không cần chọn NCLOB chỉ vì nội dung có dấu. Hãy chọn dựa trên contract dữ liệu, hệ thống cũ và yêu cầu national character set.

### 3.3. BLOB

BLOB lưu byte. Oracle không biết byte đó là UTF-8, JPEG, PDF, ZIP hay một định dạng nhị phân khác. Khi chuyển BLOB thành CLOB, ứng dụng phải cung cấp đúng charset của byte nguồn.

Không dùng phép ép kiểu BLOB thành chuỗi để “thử xem có ra tiếng Việt không”. Hãy xác định encoding từ metadata của file/API hoặc hợp đồng tích hợp.

### 3.4. BFILE

BFILE là locator trỏ đến file ngoài database qua DIRECTORY object. File được đọc từ hệ điều hành, không được cập nhật nội dung qua DBMS_LOB; muốn thay đổi file phải dùng công cụ bên ngoài.

BFILE phù hợp khi cần tham chiếu file lớn ở filesystem. Nó không giống BLOB được lưu trong segment database và có yêu cầu quyền DIRECTORY/file system riêng.

## 4. Độ dài ký tự và độ dài byte

Trong charset đa byte như AL32UTF8, một ký tự có thể chiếm từ một đến bốn byte. Vì vậy số ký tự và số byte không giống nhau.

### 4.1. LENGTH và LENGTHB

~~~sql
SELECT
    LENGTH('Tiếng Việt') AS char_length,
    LENGTHB('Tiếng Việt') AS byte_length
FROM dual;
~~~

LENGTH trả độ dài theo ký tự; LENGTHB trả số byte trong biểu diễn của charset áp dụng cho biểu thức. Với AL32UTF8, các chữ có dấu thường dùng nhiều byte hơn chữ ASCII.

### 4.2. LENGTHC, LENGTH2 và LENGTH4

Oracle còn có các hàm LENGTHC, LENGTH2 và LENGTH4 với quy tắc đếm theo Unicode complete characters, UCS2 code points và UCS4 code points tương ứng. Chúng có thể cho kết quả khác nhau với ký tự supplementary hoặc chuỗi có combining mark.

Đối với dữ liệu tiếng Việt thông thường, LENGTH thường là lựa chọn quen thuộc. Khi xử lý emoji hoặc ký tự ngoài BMP, cần hiểu rõ đơn vị đếm mà ứng dụng và Oracle API sử dụng.

### 4.3. CLOB và DBMS_LOB.GETLENGTH

~~~sql
SELECT
    DBMS_LOB.GETLENGTH(document_text) AS character_count
FROM documents;
~~~

Với CLOB/NCLOB, GETLENGTH trả độ dài theo ký tự. Với BLOB, GETLENGTH trả số byte. Không áp dụng cùng một cách diễn giải cho mọi loại LOB.

### 4.4. BYTE và CHAR length semantics

Khai báo cột:

~~~sql
CREATE TABLE customer_names (
    name_bytes VARCHAR2(100 BYTE),
    name_chars VARCHAR2(100 CHAR)
);
~~~

BYTE semantics giới hạn theo byte; CHAR semantics giới hạn theo đơn vị ký tự của database character set. Một cột VARCHAR2(100 CHAR) vẫn chịu giới hạn byte tối đa của kiểu dữ liệu và phiên bản database.

NLS_LENGTH_SEMANTICS ảnh hưởng semantics mặc định khi tạo cột CHAR/VARCHAR2 nếu không ghi BYTE hoặc CHAR. Nó không đổi database character set và không chuyển đổi dữ liệu đang lưu. Với schema quan trọng, nên khai báo BYTE/CHAR tường minh để tránh phụ thuộc session tạo bảng.

## 5. Unicode tiếng Việt và dấu tổ hợp

Tiếng Việt dùng nhiều ký tự có dấu. Một ký tự hiển thị có thể được biểu diễn bằng một code point dựng sẵn hoặc một chuỗi code point gồm chữ cái và combining marks.

Ví dụ chữ “ế”:

~~~text
Dạng dựng sẵn:       U+1EBF
Dạng phân rã chuẩn:  U+0065 U+0302 U+0301
                     e       circumflex acute
~~~

Hai chuỗi có thể hiển thị giống nhau nhưng có dãy code point khác nhau. Việc so sánh byte, độ dài và tìm kiếm có thể khác nếu hệ thống không chuẩn hóa nhất quán.

### 5.1. Oracle không tự bảo đảm mọi chuỗi được chuẩn hóa cùng dạng

Lưu chuỗi Unicode vào AL32UTF8 không đồng nghĩa Oracle tự chuyển mọi chuỗi sang NFC hoặc NFD. Hai chuỗi canonically equivalent vẫn có thể được lưu dưới hai dãy code point khác nhau.

Nếu ứng dụng cần so sánh nhất quán, hãy xác định một normalization form, thường là NFC cho dữ liệu văn bản trao đổi, và chuẩn hóa ở ranh giới nhập liệu. Cần áp dụng cùng quy tắc cho dữ liệu hiện có, dữ liệu mới, tìm kiếm và khóa so sánh.

### 5.2. UNISTR để tạo ký tự Unicode

~~~sql
SELECT UNISTR('\1EBF') AS vietnamese_char
FROM dual;
~~~

UNISTR cho phép tạo chuỗi từ mã Unicode theo cú pháp escape. Nó hữu ích để tạo test data độc lập với encoding của file SQL hoặc terminal.

### 5.3. COMPOSE và DECOMPOSE

Oracle cung cấp COMPOSE và DECOMPOSE để làm việc với dạng Unicode composition/decomposition:

~~~sql
SELECT
    COMPOSE(
        UNISTR('\0065') ||
        UNISTR('\0302') ||
        UNISTR('\0301')
    ) AS composed_form,
    DECOMPOSE(UNISTR('\1EBF')) AS decomposed_form
FROM dual;
~~~

COMPOSE tạo dạng dựng sẵn khi có thể; DECOMPOSE tạo dạng phân rã chuẩn. Hãy thử với database character set và dữ liệu thực tế của hệ thống. Ứng dụng cũng có thể dùng thư viện Unicode chuẩn của ngôn ngữ lập trình để chuẩn hóa NFC/NFD.

### 5.4. Chuẩn hóa không sửa lỗi mojibake

Nếu UTF-8 bytes đã bị giải mã nhầm thành một chuỗi ký tự sai rồi lưu vào database, COMPOSE hoặc NFC không thể biết nội dung ban đầu là gì. Cần quay lại byte nguồn hoặc bản backup đúng để giải mã lại bằng charset gốc.

Không chạy chuyển đổi hàng loạt trên dữ liệu thật chỉ dựa vào việc nhìn thấy dấu tiếng Việt sai. Trước tiên phải xác định lỗi xảy ra ở bước encode, decode, truyền client hay lưu database.

## 6. Chẩn đoán dữ liệu tiếng Việt

### 6.1. Xem dạng escape ASCII

~~~sql
SELECT
    customer_name,
    ASCIISTR(customer_name) AS escaped_name
FROM customers;
~~~

ASCIISTR biểu diễn ký tự ngoài ASCII bằng escape Unicode, hữu ích để phân biệt ký tự thực sự đang lưu. Nó không phải cách xuất file UTF-8.

### 6.2. Xem byte nội bộ

~~~sql
SELECT
    customer_name,
    DUMP(customer_name, 1016) AS internal_bytes
FROM customers
WHERE customer_id = 1;
~~~

DUMP hiển thị thông tin kiểu dữ liệu, charset và biểu diễn byte nội bộ. Format 1016 yêu cầu biểu diễn hex cùng thông tin charset. Đây là công cụ chẩn đoán; byte hiển thị phải được diễn giải theo charset thực tế.

### 6.3. So sánh ký tự và byte

~~~sql
SELECT
    'ế' AS sample_text,
    LENGTH('ế') AS char_count,
    LENGTHB('ế') AS byte_count,
    ASCIISTR('ế') AS unicode_escape
FROM dual;
~~~

Trong AL32UTF8, ký tự ế dựng sẵn chiếm ba byte UTF-8. Nếu kết quả byte không như dự kiến, hãy kiểm tra database charset, literal source encoding và client.

### 6.4. Phân biệt lỗi ở đâu

Một chuỗi sai có thể xuất phát từ:

- File nguồn đã được tạo với encoding khác UTF-8.
- Client khai báo charset không đúng encoding byte thực tế.
- Ứng dụng giải mã byte sai trước khi bind.
- Database character set không biểu diễn được ký tự nguồn.
- Chuyển CLOB/BLOB với charset ID sai.
- Export/import dùng charset khai báo không đúng.
- Hai hệ thống dùng normalization form khác nhau.

Hãy lưu một mẫu byte nguồn, một chuỗi Unicode mong đợi và kết quả đọc lại. Nếu chỉ nhìn giao diện hiển thị, khó xác định lỗi nằm ở database hay font/client.

## 7. LOB locator và DBMS_LOB

LOB column không hoạt động giống VARCHAR2 nhỏ. PL/SQL thường làm việc với locator, tức tham chiếu tới giá trị LOB được lưu trong database hoặc trong vùng temporary LOB.

DBMS_LOB cung cấp API đọc, ghi, so sánh, cắt, chuyển đổi và quản lý LOB.

### 7.1. Persistent LOB và temporary LOB

- Persistent LOB được lưu trong cột của bảng và tồn tại theo transaction/database.
- Temporary LOB được tạo trong temporary LOB storage để xử lý trung gian; ứng dụng cần giải phóng khi không còn dùng.

### 7.2. Tạo temporary CLOB

~~~sql
DECLARE
    l_text CLOB;
    l_value VARCHAR2(100) := 'Xin chào, tiếng Việt!';
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_text,
        cache => TRUE,
        dur => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_text,
        amount => LENGTH(l_value),
        buffer => l_value
    );

    DBMS_OUTPUT.PUT_LINE(
        'Characters=' || DBMS_LOB.GETLENGTH(l_text)
    );

    DBMS_LOB.FREETEMPORARY(l_text);
END;
/
~~~

Với CLOB, amount trong WRITEAPPEND là số ký tự được ghi. Với BLOB, amount là số byte. Dùng LENGTH cho buffer văn bản và LENGTHB hoặc RAW length phù hợp cho buffer byte.

### 7.3. Giải phóng temporary LOB khi có lỗi

~~~sql
DECLARE
    l_text CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(l_text, TRUE, DBMS_LOB.CALL);

    -- Xử lý l_text.

    DBMS_LOB.FREETEMPORARY(l_text);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_text) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_text);
        END IF;
        RAISE;
END;
/
~~~

Trong ứng dụng thực tế, bảo đảm temporary LOB được giải phóng cả khi lỗi. Không giữ locator của temporary LOB lâu hơn vòng đời cần thiết.

### 7.4. Lấy locator của persistent CLOB

~~~sql
CREATE TABLE lab_documents (
    document_id NUMBER PRIMARY KEY,
    body CLOB
);
~~~

~~~sql
DECLARE
    l_body CLOB;
    l_text VARCHAR2(100) := 'Nội dung tiếng Việt';
BEGIN
    INSERT INTO lab_documents(document_id, body)
    VALUES (1, EMPTY_CLOB())
    RETURNING body INTO l_body;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(l_text),
        l_text
    );

    COMMIT;
END;
/
~~~

EMPTY_CLOB() tạo LOB rỗng có locator để thao tác. INSERT/UPDATE và RETURNING lấy locator cho phép DBMS_LOB ghi nội dung.

## 8. Offset và buffer khi đọc LOB

Đơn vị offset phụ thuộc loại LOB:

| LOB | Đơn vị offset/độ dài |
| --- | --- |
| CLOB | Ký tự |
| NCLOB | Ký tự |
| BLOB | Byte |
| BFILE | Byte |

### 8.1. Đọc CLOB theo từng đoạn

~~~sql
DECLARE
    l_body CLOB;
    l_buffer VARCHAR2(32767);
    l_offset INTEGER := 1;
    l_amount INTEGER;
BEGIN
    SELECT body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 1;

    WHILE l_offset <= DBMS_LOB.GETLENGTH(l_body) LOOP
        l_amount := 1000;

        DBMS_LOB.READ(
            lob_loc => l_body,
            amount => l_amount,
            offset => l_offset,
            buffer => l_buffer
        );

        DBMS_OUTPUT.PUT_LINE(l_buffer);
        l_offset := l_offset + l_amount;
    END LOOP;
END;
/
~~~

READ trả số ký tự thực tế đã đọc vào amount. Offset CLOB là vị trí ký tự. Buffer VARCHAR2 trong PL/SQL có giới hạn byte, vì vậy kích thước đoạn phải đủ nhỏ cho charset đa byte; không giả định 32767 ký tự luôn vừa trong buffer.

### 8.2. DBMS_LOB.SUBSTR

~~~sql
SELECT DBMS_LOB.SUBSTR(body, 2000, 1)
FROM lab_documents
WHERE document_id = 1;
~~~

SUBSTR lấy một đoạn LOB. Với CLOB, amount/offset tính theo ký tự; với BLOB tính theo byte. Buffer trả về của PL/SQL/SQL có giới hạn, nên SUBSTR không phải cách tải toàn bộ LOB lớn vào một biến VARCHAR2/RAW.

### 8.3. Không cắt giữa dữ liệu đa byte

Không dùng thao tác byte trên UTF-8 như thể mỗi ký tự chiếm một byte. Nếu cắt BLOB ở giữa một chuỗi UTF-8, đoạn byte riêng lẻ có thể kết thúc giữa một code unit sequence và không giải mã được. Với văn bản, đọc theo CLOB character offsets sau khi chuyển đổi đúng charset; nếu phải chia byte stream, hãy dùng bộ giải mã hỗ trợ trạng thái qua các chunk.

## 9. Chuyển BLOB thành CLOB

BLOB chỉ là byte. Muốn biến BLOB chứa file văn bản thành CLOB, cần biết charset nguồn của byte. Ví dụ file CSV/JSON có encoding UTF-8 thì source charset ID phải là AL32UTF8.

### 9.1. Chuẩn bị BLOB và CLOB

~~~sql
CREATE TABLE lab_files (
    file_id NUMBER PRIMARY KEY,
    raw_content BLOB,
    text_content CLOB
);
~~~

### 9.2. CONVERTTOCLOB

~~~sql
DECLARE
    l_source_blob BLOB;
    l_target_clob CLOB;
    l_dest_offset INTEGER := 1;
    l_src_offset INTEGER := 1;
    l_lang_context INTEGER := DBMS_LOB.DEFAULT_LANG_CTX;
    l_warning INTEGER;
BEGIN
    SELECT raw_content
    INTO l_source_blob
    FROM lab_files
    WHERE file_id = 1
    FOR UPDATE;

    DBMS_LOB.CREATETEMPORARY(l_target_clob, TRUE, DBMS_LOB.CALL);

    DBMS_LOB.CONVERTTOCLOB(
        dest_lob => l_target_clob,
        src_blob => l_source_blob,
        amount => DBMS_LOB.LOBMAXSIZE,
        dest_offset => l_dest_offset,
        src_offset => l_src_offset,
        blob_csid => NLS_CHARSET_ID('AL32UTF8'),
        lang_context => l_lang_context,
        warning => l_warning
    );

    IF l_warning = DBMS_LOB.WARN_INCONVERTIBLE_CHAR THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Source contains characters that cannot be converted'
        );
    END IF;

    UPDATE lab_files
    SET text_content = l_target_clob
    WHERE file_id = 1;

    COMMIT;
    DBMS_LOB.FREETEMPORARY(l_target_clob);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_target_clob) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_target_clob);
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

Các điểm cần hiểu:

- blob_csid là charset dùng để diễn giải byte nguồn trong BLOB.
- src_offset tính theo byte; dest_offset tính theo ký tự.
- lang_context giữ trạng thái chuyển đổi, đặc biệt khi xử lý theo nhiều đoạn.
- warning báo tình trạng chuyển đổi không hoàn toàn, ví dụ ký tự không biểu diễn được.
- LOBMAXSIZE yêu cầu chuyển đổi toàn bộ phần còn lại có thể xử lý.

Ví dụ giả định raw_content thực sự chứa UTF-8. Nếu file nguồn là Windows-1258, Shift-JIS hoặc encoding khác, phải dùng charset ID đúng. Gán AL32UTF8 cho byte Windows-1258 không biến chúng thành UTF-8; nó chỉ khiến Oracle giải mã sai.

### 9.3. Kiểm tra warning

Không bỏ qua warning của DBMS_LOB conversion. Nếu có WARN_INCONVERTIBLE_CHAR, nội dung có thể đã bị thay thế hoặc mất ký tự. Với dữ liệu cần bảo toàn, hãy coi warning là lỗi cần xử lý và không commit bản chuyển đổi chưa được xác nhận.

## 10. Chuyển CLOB thành BLOB

Khi xuất văn bản ra file hoặc API cần byte UTF-8, chuyển CLOB sang BLOB với charset đích được chỉ định.

### 10.1. CONVERTTOBLOB

~~~sql
DECLARE
    l_source_clob CLOB;
    l_target_blob BLOB;
    l_dest_offset INTEGER := 1;
    l_src_offset INTEGER := 1;
    l_lang_context INTEGER := DBMS_LOB.DEFAULT_LANG_CTX;
    l_warning INTEGER;
BEGIN
    SELECT body
    INTO l_source_clob
    FROM lab_documents
    WHERE document_id = 1;

    DBMS_LOB.CREATETEMPORARY(l_target_blob, TRUE, DBMS_LOB.CALL);

    DBMS_LOB.CONVERTTOBLOB(
        dest_lob => l_target_blob,
        src_clob => l_source_clob,
        amount => DBMS_LOB.LOBMAXSIZE,
        dest_offset => l_dest_offset,
        src_offset => l_src_offset,
        blob_csid => NLS_CHARSET_ID('AL32UTF8'),
        lang_context => l_lang_context,
        warning => l_warning
    );

    IF l_warning = DBMS_LOB.WARN_INCONVERTIBLE_CHAR THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Text cannot be represented in target charset'
        );
    END IF;

    DBMS_OUTPUT.PUT_LINE(
        'UTF-8 bytes=' || DBMS_LOB.GETLENGTH(l_target_blob)
    );

    DBMS_LOB.FREETEMPORARY(l_target_blob);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_target_blob) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_target_blob);
        END IF;
        RAISE;
END;
/
~~~

Ở đây blob_csid là charset đích để mã hóa văn bản thành byte. Với AL32UTF8, kết quả là byte UTF-8. BLOB sau chuyển đổi có thể được gửi ra file hoặc qua binary stream.

### 10.2. Không dùng CAST_TO_RAW thay cho chuyển charset

UTL_RAW.CAST_TO_RAW và UTL_RAW.CAST_TO_VARCHAR2 là các thao tác cast/reinterpret buffer theo quy tắc của Oracle, không phải API chuyển mã Unicode tổng quát. Không dùng chúng để biến một chuỗi database charset thành UTF-8 bytes nếu chưa xác định rõ byte representation.

Khi cần encode/decode theo charset xác định, dùng DBMS_LOB conversion cho LOB hoặc API encoding chuẩn của ngôn ngữ ứng dụng.

## 11. CONVERT với chuỗi nhỏ và giới hạn của nó

Oracle có hàm CONVERT cho biểu thức ký tự:

~~~sql
SELECT CONVERT(
    'Vietnamese text',
    'AL32UTF8',
    'WE8MSWIN1252'
)
FROM dual;
~~~

Hàm có dạng CONVERT(char, dest_char_set, source_char_set). Nó phù hợp với chuỗi ký tự trong giới hạn kiểu trả về, không phải công cụ streaming cho CLOB/BLOB lớn. Khi làm việc với LOB, dùng DBMS_LOB.CONVERTTOCLOB hoặc DBMS_LOB.CONVERTTOBLOB.

CONVERT không thể khôi phục dữ liệu nếu source_char_set khai báo sai hoặc byte nguồn đã bị diễn giải sai trước đó. Khi ký tự không có trong charset đích, kết quả có thể chứa ký tự thay thế. Hãy kiểm tra khả năng biểu diễn trước khi dùng charset legacy.

### 11.1. Chuyển đổi không giống transliteration

Character-set conversion ánh xạ ký tự sang biểu diễn trong charset khác. Transliteration là thay thế ký tự bằng dạng gần giống, ví dụ bỏ dấu tiếng Việt. Hai việc này khác nhau.

Không hạ tiếng Việt thành ASCII bằng cách đổi charset nếu yêu cầu nghiệp vụ là giữ nguyên nội dung. Nếu cần bản không dấu để tìm kiếm, tạo một trường/search key riêng bằng quy tắc transliteration có chủ đích.

## 12. Đọc file ngoài bằng BFILE

BFILE cho phép PL/SQL tham chiếu file trong DIRECTORY object. File vẫn nằm trên filesystem của database server.

### 12.1. DIRECTORY object

DBA tạo directory:

~~~sql
CREATE OR REPLACE DIRECTORY import_dir AS '/data/import';
GRANT READ ON DIRECTORY import_dir TO app_user;
~~~

Đường dẫn là ví dụ phía database server, không phải đường dẫn trên máy client. Oracle database process cần quyền filesystem phù hợp.

### 12.2. Tạo BFILE locator

~~~sql
DECLARE
    l_file BFILE;
    l_length INTEGER;
BEGIN
    l_file := BFILENAME('IMPORT_DIR', 'customers_utf8.txt');

    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);
    DBMS_OUTPUT.PUT_LINE('File bytes=' || l_length);
    DBMS_LOB.FILECLOSE(l_file);
END;
/
~~~

BFILE locator không chứa nội dung file trong database. Nó tham chiếu file theo DIRECTORY object và filename.

### 12.3. Load file vào LOB

Oracle cung cấp các thủ tục DBMS_LOB.LOADFROMFILE, LOADBLOBFROMFILE và LOADCLOBFROMFILE cho các tình huống tương ứng. Khi load văn bản vào CLOB, cần chỉ rõ charset nguồn và dùng thủ tục có chuyển đổi charset phù hợp. Khi load byte nhị phân vào BLOB, không diễn giải byte như văn bản.

Với file văn bản UTF-8, phải biết file thực sự là UTF-8 và cung cấp charset ID AL32UTF8 cho API đọc/chuyển đổi. File có BOM cần được xử lý theo hợp đồng file: xác định BOM có phải metadata đầu file cần bỏ hay nội dung được giữ lại.

### 12.4. Quyền và bảo mật

- Chỉ cấp READ trên DIRECTORY cần thiết.
- Kiểm soát quyền filesystem của Oracle service account.
- Không cho user truyền đường dẫn filesystem tùy ý.
- Xác thực filename và loại file.
- Giới hạn kích thước và kiểm tra nội dung file.
- Đóng BFILE bằng FILECLOSE khi hoàn tất.

## 13. Làm việc với LOB lớn theo streaming

Không tải toàn bộ CLOB/BLOB lớn vào một biến VARCHAR2/RAW. Buffer PL/SQL có giới hạn; hãy đọc và ghi từng chunk.

### 13.1. Streaming CLOB

Mô hình:

1. Lấy locator CLOB.
2. Đặt offset ban đầu là 1.
3. Đọc một chunk bằng DBMS_LOB.READ hoặc SUBSTR.
4. Xử lý chunk.
5. Tăng offset theo số ký tự thực tế đã đọc.
6. Lặp tới GETLENGTH.

Khi dùng READ, Oracle cập nhật amount thành số đơn vị thực tế đã đọc. Dùng giá trị đó để tăng offset, không luôn cộng kích thước chunk dự kiến.

### 13.2. Streaming BLOB

Với BLOB, offset và amount tính bằng byte. Buffer là RAW, tối đa 32767 byte trong PL/SQL. Nếu byte stream là UTF-8, không cắt tùy tiện giữa một sequence nhiều byte rồi giải mã từng chunk độc lập. Dùng decoder có trạng thái hoặc chuyển sang CLOB trước.

### 13.3. Chunk size và LOB chunk

DBMS_LOB.GETCHUNKSIZE trả kích thước chunk storage của LOB. Có thể cân nhắc chunk size khi tối ưu I/O, nhưng không phải lúc nào buffer ứng dụng cũng phải bằng đúng giá trị này. Đo với workload và storage thực tế.

### 13.4. Temporary LOB và bộ nhớ

Temporary LOB tiêu tốn temporary LOB storage. Nếu tạo nhiều LOB mà không giải phóng, session có thể tăng sử dụng TEMP. Dùng FREETEMPORARY trong cả đường thành công và exception; tránh sao chép LOB không cần thiết.

## 14. Xử lý tiếng Việt ở client

Database có charset đúng vẫn có thể hiển thị tiếng Việt sai nếu client gửi hoặc đọc dữ liệu không đúng encoding.

### 14.1. JDBC Thin

Java String lưu văn bản theo Unicode. JDBC Thin xử lý chuyển đổi giữa Java Unicode và Oracle database character set. Với VARCHAR2/CLOB, dùng API ký tự; với BLOB, dùng API byte.

Ví dụ ghi CLOB bằng character stream:

~~~java
String sql = "insert into lab_documents(document_id, body) values (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql);
     Reader reader = new StringReader("Xin chào, tiếng Việt!")) {
    ps.setLong(1, 10L);
    ps.setCharacterStream(2, reader);
    ps.executeUpdate();
}
~~~

Ví dụ đọc CLOB:

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "select body from lab_documents where document_id = ?")) {
    ps.setLong(1, 10L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (Reader reader = rs.getCharacterStream("BODY")) {
                char[] buffer = new char[4096];
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    String part = new String(buffer, 0, count);
                    System.out.print(part);
                }
            }
        }
    }
}
~~~

Với BLOB, dùng setBinaryStream/getBinaryStream. Không dùng Reader cho byte nhị phân hoặc InputStream cho văn bản nếu chưa chỉ định rõ charset decoder.

### 14.2. NCHAR/NVARCHAR2 và JDBC national character methods

Nếu cột là NVARCHAR2 hoặc NCHAR, JDBC cung cấp các method như setNString/getNString và setNCharacterStream/getNCharacterStream. Với VARCHAR2/CLOB, dùng method ký tự thông thường.

Không phải ứng dụng nào cũng cần national character types. Nếu database character set là AL32UTF8, VARCHAR2/CLOB đã hỗ trợ Unicode tiếng Việt.

### 14.3. BLOB trong JDBC

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "insert into lab_files(file_id, raw_content) values (?, ?)")) {
    ps.setLong(1, 1L);
    try (InputStream in = Files.newInputStream(path)) {
        ps.setBinaryStream(2, in);
        ps.executeUpdate();
    }
}
~~~

Đây là byte stream. Nếu file là văn bản UTF-8, Oracle vẫn chỉ lưu byte; charset phải được ghi ở metadata hoặc biết từ hợp đồng file để sau này chuyển BLOB thành CLOB.

### 14.4. OCI và SQL*Plus

Với client OCI, NLS_LANG phải phản ánh charset mà client thực sự dùng. Terminal, shell, file script và ứng dụng có thể có encoding khác nhau; kiểm tra từng ranh giới.

JDBC Thin không cần NLS_LANG để mã hóa Java String. Đừng áp dụng một cách sửa cho OCI sang JDBC Thin hoặc ngược lại.

## 15. Import/export và charset

### 15.1. SQL*Loader

SQL*Loader có thể chỉ định charset nguồn bằng tham số CHARACTERSET trong control file hoặc command line. Charset phải khớp encoding thật của file đầu vào.

Ví dụ control file:

~~~text
LOAD DATA
CHARACTERSET AL32UTF8
INFILE 'customers.csv'
INTO TABLE customers
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
TRAILING NULLCOLS
(
  customer_id,
  customer_name
)
~~~

Nếu file là Windows-1258, không khai báo AL32UTF8. Trước khi load toàn bộ, chạy thử một mẫu có đủ chữ tiếng Việt, dấu thanh, ký tự đ/Đ, dấu ngoặc kép và dấu phân cách.

### 15.2. Data Pump

Data Pump export/import có thể thực hiện chuyển đổi charset giữa database nguồn và đích theo metadata và khả năng biểu diễn. Nếu charset đích không hỗ trợ mọi ký tự nguồn, dữ liệu có thể bị mất hoặc bị thay thế.

Trước migration:

- Kiểm tra NLS_CHARACTERSET và NLS_NCHAR_CHARACTERSET ở cả hai database.
- Kiểm tra dữ liệu có ký tự ngoài repertoire của charset đích.
- Dùng Database Migration Assistant for Unicode (DMU) khi cần đánh giá/migrate database sang Unicode.
- Kiểm tra log import/export và dữ liệu mẫu sau khi nhập.
- So sánh số hàng, độ dài, byte/character diagnostics và checksum theo quy tắc phù hợp.

Không dùng ALTER DATABASE CHARACTER SET như một cách đổi charset nhanh trên database đã có dữ liệu. Thay đổi database character set cần quy trình migration được Oracle hỗ trợ và đánh giá dữ liệu trước.

### 15.3. File CSV và BOM

UTF-8 BOM thường là ba byte EF BB BF ở đầu file. Một số công cụ chấp nhận BOM, một số công cụ coi nó là ký tự đầu tiên của trường đầu tiên. Hãy xác định chính sách BOM cho từng pipeline:

- Có BOM hay không.
- Nếu có, parser bỏ BOM hay giữ như nội dung.
- Charset được khai báo ở metadata hay chỉ dựa vào phỏng đoán.
- Line ending là LF hay CRLF.
- Escape và quoting CSV có được xử lý đúng không.

Đừng tự bỏ ba byte đầu của mọi file; chỉ bỏ khi đã xác nhận đó là BOM.

## 16. Quy trình xử lý chuỗi tiếng Việt bị lỗi

Khi thấy chuỗi như “Tiáº¿ng Viá»‡t”, không chuyển đổi lặp đi lặp lại theo phỏng đoán. Hãy truy ngược byte và charset:

1. Lấy một mẫu dữ liệu bị lỗi và bản gốc nếu có.
2. Xác định encoding của file/request ban đầu.
3. Xác định client API và cách nó decode byte thành string.
4. Kiểm tra database character set và national character set.
5. Dùng ASCIISTR và DUMP để quan sát chuỗi đang lưu.
6. Xác định lỗi xảy ra trước khi bind, trong conversion, hay khi hiển thị.
7. Chọn charset nguồn và đích rõ ràng.
8. Chuyển thử trên một bản sao hoặc một tập nhỏ.
9. Kiểm tra warning, ký tự thay thế, byte length và nội dung đọc lại.
10. Chỉ migration khi kết quả được xác nhận bằng người dùng/nghiệp vụ.

### 16.1. Hai kiểu lỗi khác nhau

**Sai encoding khi decode:** byte UTF-8 bị đọc như Windows-1252. Có thể khôi phục nếu còn byte nguồn.

**Mất dữ liệu khi encode sang charset không hỗ trợ:** ký tự bị thay bằng dấu hỏi hoặc replacement character. Nếu byte gốc đã bị ghi đè và không có backup, không thể phục hồi chỉ bằng đổi charset lần nữa.

### 16.2. Không chuyển đổi hai lần

Nếu driver đã chuyển Java Unicode sang database charset, không chạy thêm CONVERT như thể dữ liệu vẫn là byte nguồn. Chuyển đổi hai lần có thể tạo mojibake mới.

Hãy ghi lại ranh giới dữ liệu:

~~~text
File bytes --decode using source encoding--> Application Unicode String
Application String --driver conversion--> Oracle character data
Oracle CLOB --DBMS_LOB.CONVERTTOBLOB--> UTF-8 bytes
UTF-8 bytes --decode as UTF-8--> Application Unicode String
~~~

Mỗi mũi tên chỉ nên có một conversion đúng với encoding nguồn/đích.

## 17. Ví dụ tích hợp: lưu văn bản tiếng Việt và file UTF-8

### 17.1. Tạo bảng

~~~sql
CREATE TABLE lab_vietnamese_docs (
    doc_id NUMBER PRIMARY KEY,
    title VARCHAR2(200 CHAR),
    body CLOB,
    original_file BLOB,
    source_charset VARCHAR2(30)
);
~~~

### 17.2. Lưu text Unicode qua SQL literal

~~~sql
INSERT INTO lab_vietnamese_docs (
    doc_id,
    title,
    body,
    source_charset
)
VALUES (
    1,
    UNISTR('Tài liệu tiếng Việt'),
    TO_CLOB(UNISTR('Xin chào! Đây là nội dung tiếng Việt có dấu: ă â ê ô ơ ư đ.')),
    'AL32UTF8'
);
~~~

Ví dụ này giả định database character set hỗ trợ các ký tự literal/Unicode tương ứng. Khi tạo script bằng công cụ ngoài, cần lưu script đúng encoding hoặc dùng UNISTR escape để tránh lỗi ở tầng đọc file.

### 17.3. Kiểm tra

~~~sql
SELECT
    doc_id,
    title,
    LENGTH(title) AS title_chars,
    LENGTHB(title) AS title_bytes,
    DBMS_LOB.GETLENGTH(body) AS body_chars,
    ASCIISTR(title) AS title_escaped
FROM lab_vietnamese_docs
WHERE doc_id = 1;
~~~

### 17.4. Lưu byte file gốc

Khi upload file, dùng BLOB để giữ nguyên byte gốc và lưu charset nguồn trong SOURCE_CHARSET nếu file là văn bản. Với PDF, ảnh hoặc ZIP, SOURCE_CHARSET không có ý nghĩa như văn bản; metadata cần mô tả media type/format.

### 17.5. Chuyển file văn bản sang CLOB

Đọc BLOB từ ORIGINAL_FILE và dùng DBMS_LOB.CONVERTTOCLOB với charset ID lấy từ SOURCE_CHARSET đã được kiểm soát. Không lấy charset name tùy ý từ request rồi truyền thẳng vào dynamic SQL. Xác thực tên charset bằng danh sách được hệ thống hỗ trợ và NLS_CHARSET_ID.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tiếng Việt thành dấu hỏi | Charset đích không biểu diễn được ký tự hoặc dữ liệu đã bị thay thế | Xác định charset nguồn/đích và khôi phục từ byte/backup |
| Chuỗi thành mojibake | Byte bị decode bằng charset sai | Decode lại từ byte gốc với encoding đúng |
| CLOB không hiển thị đúng | Database charset hoặc client conversion không đúng | Kiểm tra NLS_CHARACTERSET và client encoding |
| BLOB chuyển thành chữ rác | Dùng sai charset ID cho byte nguồn | Xác định encoding thật của file |
| Dùng NCHAR nhưng vẫn lỗi | Client gửi byte sai trước khi Oracle nhận | Kiểm tra driver/client encoding; NCHAR không sửa byte sai |
| LENGTH khác LENGTHB | Ký tự đa byte trong AL32UTF8 | Phân biệt đơn vị ký tự và byte |
| Vượt giới hạn VARCHAR2 khi đọc CLOB | Tải LOB lớn vào buffer nhỏ | Đọc theo chunk bằng DBMS_LOB |
| Chunk UTF-8 bị lỗi ở ranh giới | Cắt byte giữa sequence nhiều byte | Dùng CLOB offsets hoặc decoder streaming |
| Temporary LOB làm tăng TEMP | Không gọi FREETEMPORARY | Giải phóng trong cả đường thành công và exception |
| Chuyển đổi bị mất ký tự | Bỏ qua warning hoặc charset đích thiếu repertoire | Kiểm tra warning và dùng charset Unicode phù hợp |
| Hai chuỗi nhìn giống nhưng so sánh khác | Dạng Unicode composed/decomposed khác nhau | Chuẩn hóa nhất quán, ví dụ NFC |
| SQL*Loader lỗi tiếng Việt | CHARACTERSET không khớp file | Khai báo charset nguồn chính xác |
| JDBC bị ảnh hưởng khi đổi NLS_LANG | Nhầm OCI setting với JDBC Thin | Kiểm tra API/driver thực sự đang dùng |
| Dùng CAST_TO_RAW để encode UTF-8 | Nhầm cast byte với charset conversion | Dùng DBMS_LOB conversion hoặc encoder chuẩn |
| Cắt BLOB như CLOB | Nhầm offset byte và ký tự | Dùng đúng API và đơn vị cho từng LOB |

## 19. Checklist thiết kế và migration

Trước khi thiết kế cột hoặc pipeline:

- Chọn database character set hỗ trợ đầy đủ Unicode, thường là AL32UTF8.
- Xác định có thực sự cần NCHAR/NCLOB hay CLOB/VARCHAR2 đã đủ.
- Phân loại dữ liệu văn bản và dữ liệu byte.
- Ghi charset nguồn của mọi file text trong metadata.
- Dùng DBMS_LOB conversion cho LOB và kiểm tra warning.
- Quy định normalization form cho dữ liệu tiếng Việt.
- Xác định BYTE/CHAR semantics cho cột.
- Kiểm tra client driver và encoding của file/script.
- Xác định chính sách BOM, line ending và CSV quoting.
- Có backup và kế hoạch rollback cho migration charset.
- Kiểm tra mẫu có đủ dấu, đ/Đ, ký tự tổ hợp và ký tự supplementary.
- Không dùng CONVERT hoặc CAST_RAW như giải pháp chữa mojibake không rõ nguồn gốc.

## 20. Bài tập thực hành

Sử dụng LAB_DOCUMENTS, LAB_FILES và LAB_VIETNAMESE_DOCS trong bài.

### Bài 1 — Charset metadata

Truy vấn NLS_DATABASE_PARAMETERS để xác định database và national character set. Ghi lại kết quả, giải thích cột VARCHAR2/CLOB dùng charset nào và NVARCHAR2/NCLOB dùng charset nào.

### Bài 2 — Character length và byte length

So sánh LENGTH và LENGTHB cho các chuỗi “A”, “ế”, “Đặng Thị Ánh” và emoji. Giải thích sự khác nhau trong AL32UTF8.

### Bài 3 — Unicode normalization

Tạo hai chuỗi hiển thị cùng một ký tự bằng dạng dựng sẵn và dạng combining marks. So sánh LENGTH, LENGTHB và kết quả COMPOSE/DECOMPOSE. Đề xuất quy tắc chuẩn hóa cho ứng dụng.

### Bài 4 — Temporary CLOB

Tạo temporary CLOB, ghi nhiều đoạn tiếng Việt bằng WRITEAPPEND, đọc theo chunk và giải phóng cả khi có exception.

### Bài 5 — BLOB sang CLOB

Tạo BLOB chứa byte UTF-8 từ một file mẫu. Dùng CONVERTTOCLOB với AL32UTF8. Thử khai báo sai charset trong một bản sao và so sánh kết quả.

### Bài 6 — CLOB sang BLOB

Chuyển CLOB tiếng Việt sang BLOB UTF-8 bằng CONVERTTOBLOB. Xuất byte ra file, đọc lại bằng UTF-8 và so sánh nội dung.

### Bài 7 — Chẩn đoán mojibake

Dùng ASCIISTR và DUMP để quan sát chuỗi đúng và chuỗi bị decode sai. Xác định bước có thể khôi phục nếu còn byte nguồn.

### Bài 8 — Import pipeline

Tạo CSV UTF-8 có BOM và không BOM. Viết control file SQL*Loader với CHARACTERSET phù hợp, thử import và ghi lại quy tắc xử lý BOM của công cụ.

## 21. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn thành bài tập:

~~~sql
DROP TABLE lab_vietnamese_docs PURGE;
DROP TABLE lab_documents PURGE;
DROP TABLE lab_files PURGE;
~~~

Nếu đã tạo thêm DIRECTORY object, bảng hoặc file lab, chỉ xóa đúng tài nguyên thuộc môi trường thực hành. Không xóa DIRECTORY hoặc file dùng chung của database.

## Tổng kết

CLOB và NCLOB lưu ký tự theo database character set và national character set; BLOB lưu byte không có charset nội tại; BFILE tham chiếu file ngoài và chỉ đọc. AL32UTF8 là lựa chọn Unicode đầy đủ thường phù hợp cho database mới. NCHAR/NCLOB không tự sửa dữ liệu đã bị client giải mã sai.

Khi chuyển BLOB sang CLOB, phải biết charset của byte nguồn và dùng CONVERTTOCLOB với charset ID đúng. Khi chuyển CLOB sang BLOB, chỉ rõ charset đích bằng CONVERTTOBLOB. CLOB offsets tính theo ký tự, BLOB offsets tính theo byte; đọc LOB lớn theo chunk và giải phóng temporary LOB. Tiếng Việt có thể tồn tại ở dạng Unicode dựng sẵn hoặc dấu tổ hợp; chuẩn hóa nhất quán ở ranh giới ứng dụng nếu cần so sánh ổn định. Khi điều tra mojibake, hãy truy ngược byte và encoding ở từng ranh giới, kiểm tra warning và không chuyển đổi lặp theo phỏng đoán.

## Tài liệu Oracle tham khảo

- [Oracle Database Globalization Support Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/) — database/national character sets, Unicode và globalization.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_LOB (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_LOB.html) — LOB read/write, conversion, temporary LOB và BFILE.
- [Oracle Database SQL Language Reference — Character Datatypes (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html) — CHAR, VARCHAR2, NCHAR, NVARCHAR2 và LOB.
- [Oracle Database SQL Language Reference — CONVERT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CONVERT.html) — chuyển charset cho biểu thức ký tự.
- [Oracle Database SQL Language Reference — Unicode Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Single-Row-Functions.html) — UNISTR, COMPOSE, DECOMPOSE và các hàm chuỗi.
- [Oracle Database Utilities — SQL*Loader (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/) — nạp dữ liệu và khai báo character set nguồn.
- [Oracle Database Migration Assistant for Unicode](https://docs.oracle.com/en/database/oracle/oracle-database/19/dmuag/) — đánh giá và chuyển database sang Unicode.
- [Oracle JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — trao đổi dữ liệu ký tự và LOB qua JDBC.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu Globalization Support Guide, PL/SQL Packages Reference và tài liệu driver đúng phiên bản, đặc biệt charset ID, LOB conversion warnings, national character set, streaming và Unicode normalization.
