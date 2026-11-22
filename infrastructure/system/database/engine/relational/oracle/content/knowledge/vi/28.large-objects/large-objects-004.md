# Temporary LOB, tạo/giải phóng và kiểm soát dung lượng

Trong Oracle Database, **temporary LOB** là một đối tượng LOB tạm thời được tạo để giữ dữ liệu trung gian trong quá trình xử lý. Temporary LOB thường được dùng khi PL/SQL ghép chuỗi CLOB lớn, biến đổi nội dung BLOB, tạo kết quả từ một phép toán LOB hoặc cần xây dựng một tài liệu trước khi ghi vào cột LOB bền vững.

Temporary LOB có locator giống các LOB khác, nhưng vòng đời của nó được quản lý theo thời lượng CALL hoặc SESSION. Dữ liệu temporary LOB sử dụng tài nguyên của temporary tablespace và có thể dùng buffer cache tùy lựa chọn khi tạo. Nếu tạo nhiều temporary LOB hoặc giữ chúng lâu hơn cần thiết, session có thể tiêu thụ nhiều dung lượng TEMP và làm tăng áp lực lên hệ thống.

Các thao tác quản lý chính nằm trong package DBMS_LOB:

- **CREATETEMPORARY**: tạo temporary BLOB/CLOB/NCLOB.
- **ISTEMPORARY**: kiểm tra locator có trỏ tới temporary LOB hay không.
- **FREETEMPORARY**: giải phóng temporary LOB khi không còn cần.
- **GETLENGTH, WRITE, WRITEAPPEND, APPEND, COPY, READ, TRIM**: thao tác dữ liệu LOB.
- **DBMS_LOB.CALL và DBMS_LOB.SESSION**: chọn vòng đời của temporary LOB.

Điều quan trọng là phân biệt temporary LOB với persistent LOB trong bảng. Một locator lấy từ cột CLOB/BLOB của bảng thường trỏ tới dữ liệu bền vững; không được gọi FREETEMPORARY cho locator đó. Temporary LOB cần được giải phóng đúng lúc, đặc biệt trong session chạy lâu hoặc xử lý nhiều batch.

## 1. LOB locator và temporary LOB

LOB (Large Object) là kiểu dữ liệu dùng để lưu nội dung lớn:

- **BLOB**: dữ liệu nhị phân, ví dụ ảnh, file PDF, âm thanh hoặc nội dung mã hóa.
- **CLOB**: dữ liệu ký tự theo character set của database.
- **NCLOB**: dữ liệu ký tự theo national character set.
- **BFILE**: locator tới file nhị phân bên ngoài database; BFILE là read-only từ góc nhìn Oracle và không phải temporary LOB được tạo bằng CREATETEMPORARY.

Một biến CLOB/BLOB trong PL/SQL giữ một **LOB locator**. Locator là tham chiếu cho phép PL/SQL/SQL thao tác với giá trị LOB. Không nên nhầm locator với toàn bộ nội dung LOB được sao chép vào một biến VARCHAR2 hoặc RAW.

### 1.1. Persistent LOB

Persistent LOB là LOB được lưu trong một cột của bảng hoặc một đối tượng lưu trữ LOB bền vững khác.

~~~sql
CREATE TABLE document_store (
    document_id NUMBER PRIMARY KEY,
    body        CLOB
);
~~~

Khi đọc:

~~~sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT body
    INTO l_body
    FROM document_store
    WHERE document_id = 10;
END;
/
~~~

L_BODY nhận locator tới giá trị CLOB trong hàng của DOCUMENT_STORE. Locator này không tự biến dữ liệu persistent thành temporary LOB. Không gọi DBMS_LOB.FREETEMPORARY(l_body) chỉ vì locator nằm trong biến PL/SQL.

Nếu cần cập nhật LOB persistent, phải tuân theo quy tắc DML/locking của hàng và transaction. Thay đổi trên LOB persistent có thể được COMMIT hoặc ROLLBACK cùng transaction.

### 1.2. Temporary LOB

Temporary LOB được tạo để lưu dữ liệu trung gian, không phải một giá trị LOB bền vững trong cột bảng. Ví dụ:

~~~sql
DECLARE
    l_work CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_work,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_work,
        amount  => LENGTH('Temporary content'),
        buffer  => 'Temporary content'
    );

    DBMS_OUTPUT.PUT_LINE(
        'Length=' || DBMS_LOB.GETLENGTH(l_work)
    );

    DBMS_LOB.FREETEMPORARY(l_work);
END;
/
~~~

Temporary LOB thường dùng cho:
- Ghép nhiều phần nội dung thành một CLOB lớn.
- Tạo file nhị phân trước khi lưu vào bảng.
- Nhận kết quả trung gian từ thao tác LOB.
- Chuyển đổi hoặc chuẩn hóa nội dung lớn.
- Xây dựng payload trước khi gửi sang tầng ứng dụng.

### 1.3. So sánh nhanh

| Đặc điểm | Persistent LOB | Temporary LOB |
| --- | --- | --- |
| Nơi chứa giá trị | Cột LOB/đối tượng lưu trữ bền vững | Temporary LOB storage, dùng TEMP resources |
| Vòng đời | Theo hàng/transaction và quy tắc lưu trữ | CALL hoặc SESSION |
| COMMIT/ROLLBACK | Có ý nghĩa với thay đổi dữ liệu persistent | Không phải cơ chế giải phóng temporary LOB |
| Tạo bằng | INSERT/UPDATE hoặc thao tác trên cột LOB | CREATETEMPORARY hoặc một số phép toán tạo implicit temporary LOB |
| Giải phóng | Theo DML/DDL và quản lý đối tượng | FREETEMPORARY hoặc hết duration |
| ISTEMPORARY | Trả 0 | Trả 1 |
| Có thể gọi FREETEMPORARY | Không | Có |

## 2. Tạo temporary LOB bằng CREATETEMPORARY

Cú pháp thường dùng:

~~~sql
DBMS_LOB.CREATETEMPORARY(
    lob_loc IN OUT NOCOPY CLOB,
    cache   IN BOOLEAN,
    dur     IN PLS_INTEGER DEFAULT DBMS_LOB.SESSION
);
~~~

Có overload tương ứng cho BLOB. NCLOB cũng được hỗ trợ theo datatype phù hợp.

Các tham số:

- **lob_loc**: biến locator nhận temporary LOB mới.
- **cache**: TRUE nếu dữ liệu temporary LOB nên được cache trong buffer cache; FALSE nếu không cache theo tùy chọn này.
- **dur**: thời lượng tồn tại, thường là DBMS_LOB.CALL hoặc DBMS_LOB.SESSION.

Nếu bỏ dur, mặc định là session duration. Với code tạo temporary LOB để xử lý trong một lời gọi PL/SQL, nên cân nhắc truyền DBMS_LOB.CALL tường minh để giới hạn vòng đời.

### 2.1. Tạo CLOB

~~~sql
DECLARE
    l_clob CLOB;
    l_text VARCHAR2(100) := 'Oracle temporary CLOB';
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_clob,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_clob,
        amount  => LENGTH(l_text),
        buffer  => l_text
    );

    DBMS_OUTPUT.PUT_LINE(
        DBMS_LOB.GETLENGTH(l_clob)
    );

    DBMS_LOB.FREETEMPORARY(l_clob);
END;
/
~~~

Với CLOB, amount trong WRITEAPPEND được tính theo số ký tự. LENGTH(l_text) trả số ký tự; không thay bằng LENGTHB một cách máy móc.

### 2.2. Tạo BLOB

BLOB chứa byte. Ví dụ tạo temporary BLOB từ một chuỗi ASCII được chuyển thành RAW:

~~~sql
DECLARE
    l_blob BLOB;
    l_raw  RAW(32767);
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_blob,
        cache   => FALSE,
        dur     => DBMS_LOB.CALL
    );

    l_raw := UTL_RAW.CAST_TO_RAW('Binary payload');

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_blob,
        amount  => UTL_RAW.LENGTH(l_raw),
        buffer  => l_raw
    );

    DBMS_OUTPUT.PUT_LINE(
        'Bytes=' || DBMS_LOB.GETLENGTH(l_blob)
    );

    DBMS_LOB.FREETEMPORARY(l_blob);
END;
/
~~~

Với BLOB, amount được tính theo byte. UTL_RAW.LENGTH trả số byte trong RAW buffer.

### 2.3. CACHE TRUE và FALSE

Tham số CACHE ảnh hưởng cách Oracle xử lý buffer cache cho dữ liệu temporary LOB:

- **TRUE**: cho phép dữ liệu LOB được cache trong buffer cache.
- **FALSE**: tạo LOB theo chế độ không cache bằng tùy chọn này.

Không có lựa chọn tối ưu cho mọi trường hợp. CACHE TRUE có thể hữu ích nếu cùng dữ liệu được đọc nhiều lần; CACHE FALSE có thể phù hợp với dữ liệu trung gian lớn, ít được đọc lại. Hãy đo trên workload thật vì lựa chọn cache còn ảnh hưởng tới áp lực bộ nhớ và I/O của hệ thống.

CACHE không quyết định LOB có phải temporary hay không, và cũng không quyết định vòng đời. Vòng đời do dur quy định.

### 2.4. Kiểm tra locator đã được tạo thành công

Sau CREATETEMPORARY, có thể kiểm tra:

~~~sql
IF l_clob IS NOT NULL
   AND DBMS_LOB.ISTEMPORARY(l_clob) = 1
THEN
    DBMS_OUTPUT.PUT_LINE('Temporary CLOB is ready');
END IF;
~~~

ISTEMPORARY trả 1 nếu locator trỏ tới temporary LOB và 0 nếu không. Kiểm tra này hữu ích trong helper dùng chung hoặc cleanup code có thể nhận nhiều loại locator.

## 3. CALL duration và SESSION duration

Temporary LOB có vòng đời được chọn lúc tạo.

### 3.1. DBMS_LOB.CALL

DBMS_LOB.CALL giới hạn temporary LOB theo thời lượng của lời gọi PL/SQL tương ứng. Khi call kết thúc, Oracle giải phóng temporary LOB theo duration đó.

~~~sql
CREATE OR REPLACE PROCEDURE build_message AS
    l_message CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_message,
        TRUE,
        DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        l_message,
        LENGTH('Generated inside this call'),
        'Generated inside this call'
    );

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_message));
    -- Temporary LOB có CALL duration được giải phóng khi call kết thúc.
END build_message;
/
~~~

Nếu không cần locator sau khi procedure kết thúc, CALL duration thường là lựa chọn hợp lý. Vẫn nên giải phóng sớm khi đã xử lý xong trong call dài để giảm tài nguyên đang bị giữ.

### 3.2. DBMS_LOB.SESSION

DBMS_LOB.SESSION giữ temporary LOB trong suốt session, hoặc cho tới khi được giải phóng tường minh:

~~~sql
DECLARE
    l_buffer CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_buffer,
        TRUE,
        DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        l_buffer,
        LENGTH('Keep for later calls'),
        'Keep for later calls'
    );

    -- Có thể truyền locator cho các routine khác trong cùng session.
    -- Phải FREETEMPORARY khi không còn cần.
END;
/
~~~

Session-duration hữu ích khi một LOB cần sống qua nhiều lời gọi PL/SQL trong cùng session. Đổi lại, nếu quên giải phóng, LOB có thể giữ TEMP resources trong thời gian dài.

### 3.3. COMMIT không thay thế FREETEMPORARY

Temporary LOB có duration CALL/SESSION, không phải thời hạn transaction. COMMIT hoặc ROLLBACK không phải lệnh giải phóng session-duration temporary LOB.

Ví dụ, một session tạo temporary LOB với DBMS_LOB.SESSION, sau đó COMMIT; locator vẫn có thể còn dùng được cho tới khi được FREETEMPORARY hoặc session kết thúc.

Không dùng COMMIT như một cách dọn temporary LOB.

### 3.4. Chọn duration theo quyền sở hữu locator

| Nhu cầu | Duration nên cân nhắc |
| --- | --- |
| Tạo nội dung, xử lý và bỏ trong một call | DBMS_LOB.CALL |
| Cần giữ locator qua nhiều procedure call trong cùng session | DBMS_LOB.SESSION |
| Function/procedure trả locator để caller dùng tiếp | Xác định rõ lifetime; thường cần session duration và caller chịu trách nhiệm free |
| Session pool tái sử dụng session cho request khác | Ưu tiên CALL nếu đủ; free mọi SESSION LOB trước khi trả connection về pool |

Đặc biệt với connection pool, session không đóng sau mỗi request. SESSION LOB bị quên có thể tồn tại khi connection được tái sử dụng cho người dùng/request tiếp theo.

## 4. FREETEMPORARY và ISTEMPORARY

Hai routine này là nền tảng của cleanup.

### 4.1. Kiểm tra ISTEMPORARY

~~~sql
IF DBMS_LOB.ISTEMPORARY(l_clob) = 1 THEN
    DBMS_OUTPUT.PUT_LINE('This locator refers to a temporary LOB');
ELSE
    DBMS_OUTPUT.PUT_LINE('This is not a temporary LOB');
END IF;
~~~

ISTEMPORARY giúp phân biệt temporary LOB với locator của persistent LOB. Khi locator chưa được khởi tạo, hãy kiểm tra IS NOT NULL trước khi gọi các thao tác LOB khác.

### 4.2. Giải phóng bằng FREETEMPORARY

~~~sql
DBMS_LOB.FREETEMPORARY(l_clob);
~~~

Sau khi giải phóng, không tiếp tục đọc/ghi qua locator đó. Có thể gán biến về NULL để thể hiện rõ rằng code không còn sở hữu locator:

~~~sql
DBMS_LOB.FREETEMPORARY(l_clob);
l_clob := NULL;
~~~

Chỉ gọi FREETEMPORARY với locator của temporary LOB. Không dùng nó để giải phóng LOB persistent lấy từ bảng.

### 4.3. Cleanup trên cả nhánh thành công và lỗi

PL/SQL không có khối FINALLY giống một số ngôn ngữ khác. Có thể viết cleanup trong cả luồng bình thường và exception handler:

~~~sql
DECLARE
    l_clob CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_clob,
        TRUE,
        DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        l_clob,
        LENGTH('Work data'),
        'Work data'
    );

    -- Thực hiện công việc với L_CLOB.

    IF l_clob IS NOT NULL
       AND DBMS_LOB.ISTEMPORARY(l_clob) = 1
    THEN
        DBMS_LOB.FREETEMPORARY(l_clob);
    END IF;

    l_clob := NULL;

EXCEPTION
    WHEN OTHERS THEN
        IF l_clob IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_clob) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_clob);
        END IF;

        l_clob := NULL;
        RAISE;
END;
/
~~~

Trong hệ thống production, có thể đóng gói cleanup vào helper. Nếu cleanup tự phát sinh lỗi, cần chính sách rõ để không vô tình che exception gốc; ghi nhận cả lỗi cleanup nếu có thể.

### 4.4. Giải phóng càng sớm càng tốt

Không giữ temporary LOB tới cuối một procedure dài nếu đã xử lý xong từ đầu. Hãy free ngay sau lần sử dụng cuối cùng. Điều này đặc biệt quan trọng khi:
- Một procedure xử lý nhiều tài liệu liên tiếp.
- Mỗi hàng tạo một temporary CLOB.
- Một batch tạo nhiều temporary BLOB.
- Session được giữ lâu trong application server.
- Nhiều worker/session cùng sử dụng TEMP.

## 5. Temporary LOB được tạo ngầm

Không phải mọi temporary LOB đều được tạo trực tiếp bằng CREATETEMPORARY. Một số phép toán trên LOB hoặc biểu thức SQL/PLSQL có thể tạo **implicit temporary LOB** làm kết quả trung gian.

Ví dụ nối CLOB:

~~~sql
DECLARE
    l_clob CLOB;
BEGIN
    l_clob := TO_CLOB('Part A') || TO_CLOB('Part B');

    DBMS_OUTPUT.PUT_LINE(
        'Is temporary=' || DBMS_LOB.ISTEMPORARY(l_clob)
    );
END;
/
~~~

Kết quả từ biểu thức có thể là temporary CLOB. Hãy dùng ISTEMPORARY để xác định locator có thuộc loại temporary và quản lý theo semantics của biểu thức cùng phiên bản Oracle đang dùng.

### 5.1. Nối LOB lặp lại có thể tạo nhiều bản trung gian

Mẫu sau có thể tốn kém khi nội dung rất lớn:

~~~sql
l_document := l_document || p_piece;
~~~

Nếu lặp hàng nghìn lần, phép nối có thể tạo/copy các giá trị trung gian. Điều này làm tăng CPU, bộ nhớ và temporary LOB activity.

Thay vào đó, tạo một temporary CLOB rồi append vào cùng locator:

~~~sql
DBMS_LOB.CREATETEMPORARY(
    l_document,
    TRUE,
    DBMS_LOB.CALL
);

DBMS_LOB.WRITEAPPEND(
    l_document,
    LENGTH(p_piece),
    p_piece
);
~~~

Trong vòng lặp, gọi WRITEAPPEND cho từng phần. Cách này thường giúp kiểm soát việc tạo dữ liệu trung gian tốt hơn.

### 5.2. Không phải kết quả LOB nào cũng là temporary

Một function có thể trả locator tới persistent LOB, hoặc trả một temporary LOB mới. Không suy luận loại locator chỉ từ datatype CLOB/BLOB.

Khi cần quyết định cleanup, kiểm tra ISTEMPORARY. Với locator persistent, caller không được giải phóng bằng FREETEMPORARY.

### 5.3. Temporary LOB ngầm vẫn cần được quản lý

Các temporary LOB được tạo ngầm có thể được Oracle quản lý theo duration của phép toán/call, nhưng trong code xử lý dài hoặc lặp nhiều lần, hãy tránh tạo nhiều giá trị trung gian không cần thiết. Khi nhận được locator temporary có quyền sở hữu rõ ràng, giải phóng sau khi dùng xong.

## 6. EMPTY_CLOB/EMPTY_BLOB không phải CREATETEMPORARY

Một nhầm lẫn phổ biến là coi EMPTY_CLOB() hoặc EMPTY_BLOB() là cách tạo temporary LOB. Hai hàm này thường được dùng để khởi tạo giá trị rỗng cho cột LOB persistent trong INSERT/UPDATE.

~~~sql
INSERT INTO document_store(document_id, body)
VALUES (10, EMPTY_CLOB());
~~~

Sau đó có thể lấy locator của hàng vừa tạo bằng RETURNING:

~~~sql
DECLARE
    l_body CLOB;
    l_text VARCHAR2(100) := 'Persistent document content';
BEGIN
    INSERT INTO document_store(document_id, body)
    VALUES (11, EMPTY_CLOB())
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

L_BODY ở đây trỏ tới LOB persistent của hàng mới. Không gọi FREETEMPORARY cho locator này.

| Cách tạo | Mục đích | Có phải temporary LOB? |
| --- | --- | --- |
| DBMS_LOB.CREATETEMPORARY | Tạo LOB trung gian | Có |
| EMPTY_CLOB() trong INSERT/UPDATE | Khởi tạo giá trị rỗng cho cột CLOB persistent | Không |
| EMPTY_BLOB() trong INSERT/UPDATE | Khởi tạo giá trị rỗng cho cột BLOB persistent | Không |
| SELECT lob_column INTO l_lob | Lấy locator tới LOB đã lưu | Thường là persistent, không phải temporary |

## 7. Thao tác dữ liệu temporary LOB

DBMS_LOB cung cấp nhiều routine để ghi, đọc, nối và sao chép dữ liệu.

### 7.1. WRITEAPPEND

WRITEAPPEND thêm buffer vào cuối LOB:

~~~sql
DBMS_LOB.WRITEAPPEND(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    buffer  => l_text
);
~~~

Với CLOB/NCLOB, amount tính theo ký tự. Với BLOB, amount tính theo byte.

### 7.2. APPEND

APPEND nối nội dung từ một LOB nguồn vào LOB đích:

~~~sql
DBMS_LOB.APPEND(
    dest_lob => l_target,
    src_lob  => l_source
);
~~~

Hai locator cần có kiểu LOB tương thích. APPEND nhận LOB locator nguồn, còn WRITEAPPEND nhận buffer scalar như VARCHAR2 hoặc RAW.

### 7.3. WRITE

WRITE ghi buffer tại offset chỉ định:

~~~sql
DBMS_LOB.WRITE(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    offset  => 1,
    buffer  => l_text
);
~~~

Offset của CLOB/NCLOB được tính theo ký tự; offset của BLOB tính theo byte. Ghi vào giữa LOB có thể ghi đè dữ liệu hiện có; không nhầm WRITE với WRITEAPPEND.

### 7.4. READ và SUBSTR

Đọc một đoạn LOB mà không nạp toàn bộ nội dung vào biến:

~~~sql
DECLARE
    l_clob  CLOB;
    l_piece VARCHAR2(4000);
BEGIN
    -- Giả sử L_CLOB đã được khởi tạo và có dữ liệu.
    l_piece := DBMS_LOB.SUBSTR(
        lob_loc => l_clob,
        amount  => 4000,
        offset  => 1
    );
END;
/
~~~

DBMS_LOB.SUBSTR trên CLOB trả VARCHAR2; trên BLOB trả RAW. Buffer PL/SQL có giới hạn kích thước, vì vậy cần đọc theo chunk khi xử lý LOB lớn. Với ký tự đa byte, số ký tự trả về có thể thấp hơn amount yêu cầu để phù hợp giới hạn byte của buffer.

### 7.5. COPY tạo bản sao dữ liệu độc lập

Gán locator:

~~~sql
l_alias := l_source;
~~~

thường chỉ sao chép locator/reference; không tạo một bản sao dữ liệu LOB độc lập. Hai biến có thể cùng tham chiếu một LOB. Nếu cần bản sao riêng, tạo destination LOB rồi dùng DBMS_LOB.COPY:

~~~sql
DECLARE
    l_source CLOB;
    l_copy   CLOB;
BEGIN
    -- Giả sử L_SOURCE đã trỏ tới một CLOB có dữ liệu.
    DBMS_LOB.CREATETEMPORARY(
        l_copy,
        TRUE,
        DBMS_LOB.CALL
    );

    DBMS_LOB.COPY(
        dest_lob    => l_copy,
        src_lob     => l_source,
        amount      => DBMS_LOB.GETLENGTH(l_source),
        dest_offset => 1,
        src_offset  => 1
    );

    -- L_COPY là temporary LOB độc lập, có thể xử lý riêng.

    DBMS_LOB.FREETEMPORARY(l_copy);
END;
/
~~~

Đối với CLOB, amount/offset tính theo ký tự; với BLOB, tính theo byte. Chỉ thực hiện COPY khi cần bản sao thật sự vì copy một LOB lớn tiêu thụ thêm TEMP và I/O.

### 7.6. TRIM

TRIM cắt ngắn LOB tới độ dài mong muốn:

~~~sql
DBMS_LOB.TRIM(l_clob, 1000);
~~~

Với CLOB, length tính theo ký tự; với BLOB, theo byte. Không dùng TRIM để giải phóng temporary LOB; TRIM chỉ thay đổi nội dung/độ dài, còn FREETEMPORARY giải phóng tài nguyên temporary LOB.

## 8. Xử lý LOB lớn theo chunk

Không nên chuyển toàn bộ CLOB/BLOB lớn vào VARCHAR2/RAW nếu kích thước có thể vượt giới hạn buffer PL/SQL. Đọc theo chunk giúp giới hạn bộ nhớ và xử lý streaming.

### 8.1. Đọc CLOB từng đoạn

~~~sql
DECLARE
    l_clob   CLOB;
    l_piece  VARCHAR2(4000);
    l_offset PLS_INTEGER := 1;
BEGIN
    -- Giả sử L_CLOB đã có dữ liệu.
    LOOP
        l_piece := DBMS_LOB.SUBSTR(
            l_clob,
            4000,
            l_offset
        );

        EXIT WHEN l_piece IS NULL;

        -- Xử lý đoạn hiện tại.
        DBMS_OUTPUT.PUT_LINE(
            'Chunk characters=' || LENGTH(l_piece)
        );

        l_offset := l_offset + LENGTH(l_piece);
    END LOOP;
END;
/
~~~

Offset tăng theo số ký tự đã đọc. Đối với CLOB đa byte, không dùng LENGTHB để tăng offset vì offset của CLOB là đơn vị ký tự.

Trong ứng dụng thực tế, không nhất thiết DBMS_OUTPUT từng chunk; có thể chuyển chunk tới parser, writer hoặc tầng xử lý tiếp theo.

### 8.2. Đọc BLOB từng đoạn

~~~sql
DECLARE
    l_blob   BLOB;
    l_buffer RAW(32767);
    l_amount PLS_INTEGER;
    l_offset PLS_INTEGER := 1;
    l_length PLS_INTEGER;
BEGIN
    -- Giả sử L_BLOB đã có dữ liệu.
    l_length := DBMS_LOB.GETLENGTH(l_blob);

    WHILE l_offset <= l_length LOOP
        l_amount := LEAST(32767, l_length - l_offset + 1);

        DBMS_LOB.READ(
            lob_loc => l_blob,
            amount  => l_amount,
            offset  => l_offset,
            buffer  => l_buffer
        );

        -- Xử lý L_BUFFER.

        l_offset := l_offset + l_amount;
    END LOOP;
END;
/
~~~

BLOB offset và amount tính theo byte. RAW buffer có giới hạn 32767 byte trong PL/SQL; không yêu cầu READ một lần với kích thước lớn hơn khả năng buffer.

### 8.3. Ghi CLOB theo từng phần

~~~sql
DECLARE
    l_clob CLOB;
    l_part VARCHAR2(4000);
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_clob,
        TRUE,
        DBMS_LOB.CALL
    );

    l_part := 'Header';
    DBMS_LOB.WRITEAPPEND(l_clob, LENGTH(l_part), l_part);

    l_part := ' - Detail';
    DBMS_LOB.WRITEAPPEND(l_clob, LENGTH(l_part), l_part);

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_clob));

    DBMS_LOB.FREETEMPORARY(l_clob);
END;
/
~~~

Mẫu này tránh phải tạo một chuỗi CLOB mới bằng phép nối ở mỗi bước.

## 9. Quản lý locator và quyền sở hữu

Locator là tham chiếu tới giá trị LOB. Quản lý locator rõ ràng giúp tránh giải phóng nhầm hoặc dùng locator đã hết vòng đời.

### 9.1. Gán locator không đồng nghĩa copy dữ liệu

~~~sql
l_second := l_first;
~~~

Phép gán LOB locator không nên được xem là thao tác deep copy. Hai biến có thể tham chiếu cùng một giá trị LOB. Nếu cần dữ liệu độc lập, dùng DBMS_LOB.COPY vào một LOB đích đã tạo.

### 9.2. Chỉ một nơi chịu trách nhiệm free

Nếu nhiều biến giữ locator tham chiếu cùng một temporary LOB, cần xác định rõ nơi sở hữu và nơi giải phóng. Sau khi temporary LOB được free, không tiếp tục sử dụng bất kỳ locator nào còn tham chiếu tới giá trị đó.

Một quy ước dễ bảo trì:
- Routine tạo temporary LOB chịu trách nhiệm giải phóng.
- Routine nhận locator chỉ sử dụng, không free trừ khi hợp đồng API chuyển quyền sở hữu.
- Nếu trả locator cho caller, tài liệu hóa duration và trách nhiệm free.
- Nếu cần bản sao độc lập, dùng COPY và quản lý locator mới riêng.

### 9.3. Không free persistent locator

Ví dụ đọc persistent CLOB:

~~~sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT body
    INTO l_body
    FROM document_store
    WHERE document_id = 11;

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_body));

    -- Không gọi FREETEMPORARY cho L_BODY nếu nó là persistent LOB.
END;
/
~~~

Có thể kiểm tra:

~~~sql
IF DBMS_LOB.ISTEMPORARY(l_body) = 1 THEN
    DBMS_LOB.FREETEMPORARY(l_body);
END IF;
~~~

Nhưng với locator persistent, kết quả là 0 và không có temporary LOB để giải phóng.

### 9.4. Locator không được dùng sau CALL duration

Nếu temporary LOB có CALL duration, khi call kết thúc tài nguyên được giải phóng theo duration. Không lưu locator vào package variable rồi kỳ vọng sử dụng nó sau khi call đã kết thúc.

Nếu dữ liệu phải sống qua nhiều lời gọi, cân nhắc SESSION duration và xác định rõ caller nào sẽ free.

## 10. Temporary LOB và session pool

Application server thường sử dụng connection/session pool. Connection được trả về pool sau request nhưng database session có thể vẫn tồn tại.

Nếu mỗi request tạo SESSION-duration temporary LOB mà không free:
- Temporary LOB tiếp tục tồn tại sau khi request kết thúc.
- Request tiếp theo có thể dùng lại session với các temporary LOB cũ.
- TEMP usage tăng dần theo thời gian.
- Lỗi chỉ xuất hiện sau nhiều request hoặc khi tải đồng thời tăng.

### 10.1. Ưu tiên CALL duration cho dữ liệu request-local

Nếu LOB chỉ cần trong một stored procedure call, dùng:

~~~sql
DBMS_LOB.CREATETEMPORARY(
    l_work,
    TRUE,
    DBMS_LOB.CALL
);
~~~

Nếu phải dùng SESSION duration, đảm bảo cleanup trước khi trả connection về pool.

### 10.2. Cleanup ở ranh giới request

Application nên có quy ước:
1. Routine tạo LOB ghi nhận locator/ownership.
2. Xử lý hoàn tất thì FREETEMPORARY.
3. Exception path cũng cleanup.
4. Không giữ locator trong package global qua request khác.
5. Trước khi trả connection về pool, không còn session LOB không cần thiết.

### 10.3. Đừng dựa vào đóng connection pool như cleanup thông thường

Session có thể tồn tại lâu hơn một request. Đóng logical connection chỉ trả session về pool, không nhất thiết kết thúc database session. Vì vậy, không thể dùng session termination làm cơ chế dọn thường xuyên cho temporary LOB.

## 11. Temporary LOB và temporary tablespace

Temporary LOB sử dụng tài nguyên temporary storage. Dữ liệu trung gian lớn hoặc nhiều session cùng tạo LOB có thể làm TEMP tablespace tăng mức sử dụng.

Cần phân biệt:
- **Temporary LOB**: giá trị LOB tạm thời.
- **Temporary table**: bảng tạm với semantics transaction/session riêng.
- **Temporary tablespace**: tablespace chứa các segment tạm thời.
- **Buffer cache**: vùng cache dữ liệu, không phải nơi định nghĩa vòng đời temporary LOB.

Temporary LOB không phải một global temporary table. Dùng từ "temporary" trong tên không có nghĩa hai đối tượng có cùng cơ chế lưu trữ hoặc cleanup.

### 11.1. Theo dõi số temporary LOB theo session

View V$TEMPORARY_LOBS cung cấp thống kê temporary LOB theo session, thường gồm:
- SID.
- CACHE_LOBS.
- NOCACHE_LOBS.
- ABSTRACT_LOBS.

Ví dụ xem session hiện tại:

~~~sql
SELECT sid,
       cache_lobs,
       nocache_lobs,
       abstract_lobs
FROM v$temporary_lobs
WHERE sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'));
~~~

Các cột cho biết số lượng temporary LOB theo nhóm cache/nocache/abstract; đây là số lượng, không phải trực tiếp dung lượng byte. Cần quyền đọc dynamic performance view phù hợp.

### 11.2. Theo dõi temporary segments

Có thể dùng V$TEMPSEG_USAGE để quan sát temporary segment theo session:

~~~sql
SELECT username,
       tablespace,
       segtype,
       blocks,
       sql_id
FROM v$tempseg_usage
WHERE session_addr = (
    SELECT saddr
    FROM v$session
    WHERE sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'))
);
~~~

View này cung cấp thông tin temporary segment đang được session sử dụng. Các loại segment và cách hiển thị có thể phụ thuộc workload/phiên bản. Để quy đổi blocks thành byte, cần biết block size của tablespace.

### 11.3. Xem tổng quan TEMP tablespace

DBA có thể xem không gian TEMP:

~~~sql
SELECT tablespace_name,
       tablespace_size,
       allocated_space,
       free_space
FROM dba_temp_free_space;
~~~

Quyền truy cập và view có thể khác theo phiên bản/quyền của schema. Trong môi trường RAC, xem các view GV$ phù hợp và phân biệt INST_ID/SID để không gộp nhầm session ở nhiều instance.

### 11.4. Đo trước và sau một thao tác

Khi điều tra nghi ngờ temporary LOB leak:
1. Ghi nhận số temporary LOB và temporary segments của session.
2. Chạy một batch đại diện.
3. Free mọi locator được tạo tường minh.
4. Đo lại.
5. Lặp nhiều batch để xem usage có tăng không.
6. So sánh với session kết thúc hoặc call kết thúc theo duration.

Một con số TEMP tăng trong một thời điểm không tự động chứng minh leak. Oracle có thể giữ/thu hồi extent theo cơ chế quản lý temporary segment; cần xem xu hướng và trạng thái session.

## 12. Kiểm soát dung lượng và hiệu năng

Quản lý temporary LOB không chỉ là gọi FREETEMPORARY. Cần giảm số LOB được tạo, kích thước bản sao và thời gian giữ locator.

### 12.1. Chọn duration ngắn nhất đáp ứng yêu cầu

- Dùng CALL nếu dữ liệu chỉ cần trong một call.
- Dùng SESSION khi thực sự cần sống qua nhiều call.
- Free sớm ngay sau lần sử dụng cuối.
- Không mặc định SESSION chỉ vì nó là giá trị mặc định của CREATETEMPORARY.

### 12.2. Hạn chế phép nối tạo bản sao trung gian

Tránh lặp:

~~~sql
l_clob := l_clob || p_piece;
~~~

trên nội dung lớn. Tạo một temporary CLOB rồi WRITEAPPEND từng phần thường giúp kiểm soát việc tạo giá trị trung gian.

### 12.3. Không copy toàn bộ LOB nếu chỉ cần một phần

Dùng DBMS_LOB.SUBSTR hoặc DBMS_LOB.READ theo chunk nếu chỉ cần xử lý từng phần. Copy toàn bộ một LOB lớn sang temporary LOB khác có thể gần như nhân đôi dung lượng tạm thời.

### 12.4. Chọn CACHE theo workload

- Đọc lại nhiều lần một LOB nhỏ có thể hưởng lợi từ cache.
- Dữ liệu lớn, đọc một lần có thể phù hợp với NOCACHE.
- Cần đo I/O, buffer cache pressure và throughput dưới tải đại diện.

Không chọn CACHE TRUE chỉ vì muốn nhanh; cũng không chọn FALSE cho mọi LOB lớn mà không đo.

### 12.5. Giới hạn số LOB đồng thời

Nếu xử lý nhiều tài liệu:
- Dùng batch nhỏ.
- Free LOB của từng tài liệu trước khi sang tài liệu tiếp theo nếu không cần giữ.
- Tránh giữ cả danh sách locator khi chỉ cần một LOB tại một thời điểm.
- Tránh tạo nhiều bản copy song song không cần thiết.

### 12.6. Tránh session-duration leak

Trong session chạy lâu:
- Theo dõi V$TEMPORARY_LOBS.
- Kiểm tra nhánh exception.
- Kiểm tra routine trả locator.
- Kiểm tra package variable giữ locator.
- Đảm bảo cleanup trước khi trả session cho pool.

### 12.7. Không dùng COMMIT để giải phóng TEMP

COMMIT giải quyết transaction, không thay thế FREETEMPORARY. Nếu một session đang giữ session-duration LOB, COMMIT không làm locator tự biến mất.

## 13. Mẫu code quản lý temporary CLOB an toàn

Một procedure có thể tạo, ghi, xử lý và free temporary CLOB như sau:

~~~sql
CREATE OR REPLACE PROCEDURE build_document_preview (
    p_header IN VARCHAR2,
    p_detail IN VARCHAR2
) AS
    l_document CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_document,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    IF p_header IS NOT NULL THEN
        DBMS_LOB.WRITEAPPEND(
            l_document,
            LENGTH(p_header),
            p_header
        );
    END IF;

    IF p_detail IS NOT NULL THEN
        DBMS_LOB.WRITEAPPEND(
            l_document,
            LENGTH(p_detail),
            p_detail
        );
    END IF;

    -- Xử lý hoặc truyền L_DOCUMENT tới routine nhận LOB.
    DBMS_OUTPUT.PUT_LINE(
        'Preview length=' || DBMS_LOB.GETLENGTH(l_document)
    );

    IF DBMS_LOB.ISTEMPORARY(l_document) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_document);
    END IF;

    l_document := NULL;

EXCEPTION
    WHEN OTHERS THEN
        IF l_document IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_document) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_document);
        END IF;

        l_document := NULL;
        RAISE;
END build_document_preview;
/
~~~

Procedure dùng CALL duration vì LOB chỉ cần trong lần gọi. Exception handler giải phóng nếu lỗi xảy ra sau khi tạo LOB. Trong code production, nếu cleanup có thể phát sinh exception, cần thiết kế để không che lỗi ban đầu và để logger ghi nhận lỗi cleanup.

## 14. Mẫu code tạo và lưu persistent CLOB từ temporary CLOB

Có thể tạo nội dung tạm trước, sau đó ghi vào cột persistent. Cần phân biệt locator nguồn và đích.

~~~sql
CREATE TABLE report_store (
    report_id NUMBER PRIMARY KEY,
    report_body CLOB
);
~~~

Ví dụ:

~~~sql
DECLARE
    l_temp   CLOB;
    l_target CLOB;
    l_part   VARCHAR2(100);
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.CALL
    );

    l_part := 'Report header' || CHR(10);
    DBMS_LOB.WRITEAPPEND(l_temp, LENGTH(l_part), l_part);

    l_part := 'Report detail' || CHR(10);
    DBMS_LOB.WRITEAPPEND(l_temp, LENGTH(l_part), l_part);

    INSERT INTO report_store(report_id, report_body)
    VALUES (1, EMPTY_CLOB())
    RETURNING report_body INTO l_target;

    DBMS_LOB.COPY(
        dest_lob    => l_target,
        src_lob     => l_temp,
        amount      => DBMS_LOB.GETLENGTH(l_temp),
        dest_offset => 1,
        src_offset  => 1
    );

    COMMIT;

    IF DBMS_LOB.ISTEMPORARY(l_temp) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_temp);
    END IF;

    -- L_TARGET là persistent locator, không FREETEMPORARY.
EXCEPTION
    WHEN OTHERS THEN
        IF l_temp IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_temp) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_temp);
        END IF;

        ROLLBACK;
        RAISE;
END;
/
~~~

L_TEMP là temporary CLOB; L_TARGET là locator tới cột REPORT_STORE.REPORT_BODY. COMMIT làm thay đổi persistent được lưu; FREETEMPORARY giải phóng L_TEMP. Không gọi FREETEMPORARY trên L_TARGET.

Trong ứng dụng thật, hãy đặt cleanup và transaction boundary theo API sở hữu LOB; nếu COMMIT thành công nhưng cleanup sau đó lỗi, dữ liệu persistent đã được commit và không thể rollback bằng handler nữa.

## 15. Temporary LOB trong function và API trả locator

Một function có thể trả CLOB/BLOB. Nếu function tạo temporary LOB rồi trả locator cho caller, duration phải đủ dài để caller sử dụng.

Ví dụ khái niệm:

~~~sql
CREATE OR REPLACE FUNCTION make_text_lob (
    p_text IN VARCHAR2
) RETURN CLOB
IS
    l_result CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_result,
        TRUE,
        DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        l_result,
        LENGTH(p_text),
        p_text
    );

    RETURN l_result;
END make_text_lob;
/
~~~

Caller nhận locator và phải quản lý việc giải phóng:

~~~sql
DECLARE
    l_value CLOB;
BEGIN
    l_value := make_text_lob('Returned temporary value');

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_value));

    IF DBMS_LOB.ISTEMPORARY(l_value) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_value);
    END IF;
END;
/
~~~

Ví dụ dùng SESSION duration để locator còn tồn tại sau khi function kết thúc. Cần tài liệu hóa rằng caller sở hữu trách nhiệm free. Nếu dùng CALL duration, phải hiểu chính xác ranh giới call trong cách gọi thực tế; không trả locator mà caller dự định giữ sau khi duration đã hết.

### 15.1. Hợp đồng ownership cần rõ

Khi API trả LOB locator, tài liệu hóa:
- Locator trỏ tới persistent hay temporary LOB.
- Temporary LOB dùng CALL hay SESSION duration.
- Caller có được phép ghi/sửa không.
- Ai chịu trách nhiệm FREETEMPORARY.
- Locator có được chia sẻ cho nhiều biến/routine không.
- Có cần COPY nếu caller muốn dữ liệu độc lập không.

Không để cả callee và caller cùng nghĩ bên kia sẽ free; cũng không để hai nơi cùng free một locator mà không có quy ước ownership.

## 16. Các lỗi thường gặp khi quản lý temporary LOB

| Lỗi/tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| ORA-22275 | Locator không hợp lệ hoặc chưa được khởi tạo đúng | Tạo temporary LOB hoặc lấy locator persistent hợp lệ trước khi thao tác |
| ORA-22289 | Thao tác không hợp lệ với locator/LOB trong ngữ cảnh hiện tại | Kiểm tra datatype, locator và routine được dùng |
| ORA-22922 | Locator trỏ tới giá trị LOB không còn hợp lệ | Kiểm tra vòng đời locator và object nguồn |
| TEMP tăng dần theo session | SESSION temporary LOB không được free | Dùng CALL khi phù hợp, cleanup rõ ràng và theo dõi session |
| LOB bị invalid sau khi routine trả về | Locator có CALL duration hết hạn | Chọn duration phù hợp hoặc xử lý LOB trong cùng call |
| Gọi FREETEMPORARY trên persistent LOB | Nhầm locator lấy từ cột bảng là temporary | Dùng ISTEMPORARY và chỉ free khi trả 1 |
| CLOB bị cắt/offset sai | Dùng LENGTHB hoặc byte offset cho CLOB | Dùng đơn vị ký tự cho CLOB/NCLOB |
| BLOB bị cắt/offset sai | Dùng đơn vị ký tự thay vì byte | Dùng byte count như UTL_RAW.LENGTH |
| Bộ nhớ/TEMP tăng khi nối chuỗi | Nhiều implicit temporary LOB/copy trung gian | Tạo một LOB và WRITEAPPEND từng phần |
| Copy LOB quá nhiều | Gán/copy toàn bộ không cần thiết | Dùng locator, đọc chunk hoặc COPY chỉ phần cần |
| Locator alias bị dùng sau khi free | Nhiều biến cùng tham chiếu một temporary LOB | Quy định owner; không dùng alias sau FREETEMPORARY |
| COMMIT nhưng TEMP không giảm | COMMIT không giải phóng SESSION LOB | Gọi FREETEMPORARY hoặc kết thúc session |
| Session pool bị giữ TEMP | Logical connection trả về pool nhưng session còn sống | Cleanup trước khi trả connection |
| Gọi DBMS_LOB trên NULL locator | Biến LOB chưa được khởi tạo | Kiểm tra NULL và tạo/đọc locator hợp lệ |

Mã lỗi cụ thể phụ thuộc thao tác, trạng thái locator và phiên bản Oracle. Khi điều tra, ghi SQLCODE, SQLERRM, error stack và backtrace; đồng thời kiểm tra session đang giữ temporary LOB.

## 17. Quy trình chẩn đoán temporary LOB usage

Khi TEMP tablespace tăng bất thường hoặc một session giữ nhiều temporary LOB:

1. Xác định SID/serial number và SQL_ID của session nghi vấn.
2. Xem số CACHE_LOBS, NOCACHE_LOBS và ABSTRACT_LOBS trong V$TEMPORARY_LOBS.
3. Xem temporary segment của session trong V$TEMPSEG_USAGE.
4. Xác định procedure/package đang chạy và các nhánh tạo LOB.
5. Tìm CREATETEMPORARY với duration SESSION.
6. Tìm implicit LOB expression trong vòng lặp, đặc biệt nối CLOB lặp lại.
7. Kiểm tra mọi nhánh exception có cleanup hay không.
8. Kiểm tra function/procedure trả locator và ownership contract.
9. Đo lại sau khi free LOB hoặc kết thúc call.
10. Kiểm tra xu hướng qua nhiều batch/request thay vì chỉ một snapshot.
11. Đánh giá batch size, cache mode và số LOB đồng thời.
12. Kiểm tra TEMP tablespace tổng thể và tải của các session khác.

Không kết luận leak chỉ từ một lần nhìn TEMP usage. Cần phân biệt temporary segment được Oracle giữ để tái sử dụng với LOB locator thực sự còn sống trong session.

## 18. Những nhầm lẫn thường gặp

**Temporary LOB là temporary table.** Không đúng. Temporary LOB là giá trị LOB trung gian; temporary table là đối tượng bảng có quy tắc dữ liệu tạm riêng.

**Mọi biến CLOB đều là temporary LOB.** Không đúng. Biến có thể giữ locator tới persistent LOB, temporary LOB hoặc chưa được khởi tạo.

**SELECT CLOB từ bảng rồi FREETEMPORARY là cleanup đúng.** Không đúng. Locator thường trỏ tới persistent LOB; không giải phóng bằng FREETEMPORARY.

**EMPTY_CLOB() tạo temporary CLOB.** Không đúng. EMPTY_CLOB thường dùng để khởi tạo cột CLOB persistent rỗng; dùng CREATETEMPORARY cho temporary LOB.

**COMMIT sẽ free temporary LOB.** Không đúng. Duration CALL/SESSION không phải transaction lifetime.

**SESSION duration luôn tốt hơn CALL.** Không đúng. SESSION giữ locator lâu hơn và dễ tạo leak trong session pool nếu không free.

**CALL duration có nghĩa hết block BEGIN/END là tự free.** Không nên suy luận theo block lồng nhau; CALL gắn với thời lượng call theo semantics Oracle. Dùng FREETEMPORARY khi đã dùng xong trong call dài.

**CACHE TRUE luôn nhanh hơn CACHE FALSE.** Không đúng. Phụ thuộc pattern đọc, kích thước, buffer cache pressure và workload.

**Gán L_B := L_A tạo bản sao độc lập.** Không nên coi phép gán locator là deep copy. Dùng DBMS_LOB.COPY nếu cần dữ liệu độc lập.

**TRIM giải phóng temporary LOB.** Không đúng. TRIM chỉ cắt độ dài; FREETEMPORARY mới giải phóng temporary LOB.

**Nối CLOB trong vòng lặp luôn rẻ.** Không đúng. Có thể tạo nhiều giá trị trung gian; WRITEAPPEND thường dễ kiểm soát hơn.

**CLOB amount và offset tính theo byte.** Không đúng. CLOB/NCLOB dùng đơn vị ký tự; BLOB dùng byte.

**V$TEMPORARY_LOBS cho biết chính xác số byte TEMP.** Không đúng. View này cho số lượng theo loại temporary LOB; dùng thêm temporary segment views để xem usage.

**Session pool trả connection nghĩa là database session kết thúc.** Không đúng. Logical connection có thể được trả về pool trong khi session database còn sống.

**FREETEMPORARY được dùng cho mọi locator.** Không đúng. Chỉ free locator của temporary LOB.

## 19. Bài tập tự luyện

1. Tạo temporary CLOB bằng CREATETEMPORARY với CALL duration.
2. Ghi chuỗi vào CLOB bằng WRITEAPPEND và tính amount đúng.
3. Tạo temporary BLOB và append RAW buffer.
4. Vì sao CLOB dùng LENGTH còn BLOB dùng UTL_RAW.LENGTH?
5. Kiểm tra locator bằng ISTEMPORARY.
6. Giải phóng temporary LOB bằng FREETEMPORARY.
7. Viết exception handler đảm bảo cleanup khi thao tác LOB lỗi.
8. So sánh CALL và SESSION duration.
9. Vì sao COMMIT không thay thế FREETEMPORARY?
10. Tạo temporary LOB SESSION duration trong session và free sau một lời gọi khác.
11. Giải thích nguy cơ SESSION LOB trong connection pool.
12. Phân biệt persistent LOB locator và temporary LOB locator.
13. Dùng EMPTY_CLOB trong INSERT và ghi dữ liệu persistent bằng RETURNING.
14. Vì sao không được FREETEMPORARY locator lấy từ cột CLOB?
15. Tạo CLOB bằng phép nối và kiểm tra ISTEMPORARY.
16. Thay phép nối lặp bằng WRITEAPPEND.
17. So sánh APPEND và WRITEAPPEND.
18. Dùng COPY tạo temporary CLOB độc lập từ một nguồn CLOB.
19. Giải thích vì sao gán locator không đồng nghĩa deep copy.
20. Đọc CLOB theo chunk 4000 ký tự và cập nhật offset đúng.
21. Đọc BLOB theo chunk tối đa 32767 byte.
22. Vì sao LENGTHB không phù hợp để tăng offset CLOB?
23. Dùng TRIM rút ngắn CLOB và phân biệt với FREETEMPORARY.
24. Tạo function trả temporary CLOB và tài liệu hóa ownership cho caller.
25. Nêu rủi ro khi trả CALL-duration locator ra ngoài routine.
26. Viết query xem V$TEMPORARY_LOBS của session hiện tại.
27. Viết query xem temporary segments của session trong V$TEMPSEG_USAGE.
28. Phân biệt số lượng temporary LOB và dung lượng temporary segment.
29. Xây dựng quy trình phát hiện SESSION LOB leak trong session pool.
30. Thiết kế API xử lý file lớn: đọc chunk, tạo temporary LOB, lưu persistent LOB, cleanup khi thành công và khi lỗi.

**Temporary LOB là dữ liệu trung gian có vòng đời CALL hoặc SESSION; tạo bằng CREATETEMPORARY, kiểm tra bằng ISTEMPORARY và giải phóng bằng FREETEMPORARY.** Hãy phân biệt locator temporary với locator persistent, dùng đơn vị ký tự cho CLOB và byte cho BLOB, tránh tạo bản sao không cần thiết và theo dõi TEMP usage ở cấp session. Quản lý duration cùng ownership rõ ràng giúp tránh temporary LOB leak, nhất là trong ứng dụng dùng connection pool.
