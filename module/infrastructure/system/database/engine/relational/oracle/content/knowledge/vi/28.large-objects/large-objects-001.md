# LOB locator, dữ liệu in-row/out-of-row và vòng đời tài nguyên trong Oracle Database

Oracle dùng các kiểu dữ liệu Large Object (LOB) để lưu nội dung lớn như văn bản dài, ảnh, PDF, âm thanh, video hoặc payload nhị phân. Khi làm việc với LOB, ứng dụng không nhất thiết đọc toàn bộ nội dung vào bộ nhớ mỗi lần truy vấn. Thay vào đó, database trả về một **LOB locator** — tham chiếu cho phép PL/SQL hoặc client truy cập nội dung theo từng phần.

Cần phân biệt ba khái niệm:

- **LOB value:** nội dung thực tế, ví dụ các ký tự của CLOB hoặc byte của BLOB.
- **LOB locator:** tham chiếu tới LOB value; biến kiểu CLOB/BLOB trong PL/SQL thường giữ locator thay vì chứa toàn bộ payload.
- **LOB storage:** nơi Oracle lưu payload, có thể nằm cùng hàng dữ liệu (in-row) hoặc trong LOB segment riêng (out-of-row).

Vòng đời tài nguyên còn phụ thuộc loại LOB. Persistent LOB thuộc về một hàng trong bảng; temporary LOB được tạo để xử lý trung gian trong session/call; BFILE chỉ tham chiếu file bên ngoài database và chỉ đọc qua Oracle.

Bài học giải thích locator hoạt động ra sao, khác biệt in-row/out-of-row, BasicFiles và SecureFiles, cách tạo/đọc/ghi LOB bằng DBMS_LOB, quản lý temporary LOB, sử dụng BFILE, kiểm tra metadata và giữ tài nguyên an toàn trong ứng dụng.

## 1. Các kiểu dữ liệu LOB

### 1.1. Bốn loại LOB chính

| Kiểu | Nội dung | Nơi lưu | Đặc điểm |
| --- | --- | --- | --- |
| BLOB | Dữ liệu nhị phân | Trong database | Byte, phù hợp ảnh, PDF, file nén, payload nhị phân |
| CLOB | Văn bản theo database character set | Trong database | Dữ liệu ký tự lớn |
| NCLOB | Văn bản theo national character set | Trong database | Văn bản dùng national character set |
| BFILE | Dữ liệu nhị phân trong file bên ngoài database | File system phía database server | Locator chỉ đọc, database không quản lý nội dung file như LOB nội bộ |

BLOB, CLOB và NCLOB là **internal LOB** vì payload được lưu trong database. BFILE là **external LOB**: database lưu locator và metadata directory/file, còn nội dung nằm trong file system bên ngoài.

### 1.2. CLOB và NCLOB

CLOB lưu dữ liệu ký tự theo database character set. NCLOB lưu theo national character set. Hãy chọn theo yêu cầu mã hóa ký tự và chuẩn dữ liệu của ứng dụng; không dùng NCLOB chỉ vì tên gọi có chữ National.

Các thao tác trên CLOB/NCLOB làm việc theo đơn vị ký tự theo quy tắc LOB API. Điều này khác BLOB, nơi offset và amount được tính theo byte.

### 1.3. BLOB

BLOB lưu byte mà không diễn giải chúng là văn bản. Đây là lựa chọn phù hợp cho:
- Ảnh và tài liệu PDF.
- File nén hoặc dữ liệu mã hóa.
- Tệp âm thanh/video.
- Nội dung nhị phân do ứng dụng tạo.

Không chuyển BLOB thành VARCHAR2 chỉ để tiện xử lý. Việc chuyển đổi có thể làm thay đổi byte hoặc gặp giới hạn độ dài.

### 1.4. BFILE

BFILE lưu locator tới file trong một directory object của Oracle. Database có thể kiểm tra, mở và đọc file qua DBMS_LOB, nhưng không ghi nội dung trở lại file qua BFILE. File nằm ngoài database nên cần quản lý quyền OS, quyền DIRECTORY và backup file system riêng.

### 1.5. Vì sao không dùng VARCHAR2 cho mọi nội dung?

VARCHAR2 phù hợp với dữ liệu chuỗi có giới hạn kích thước SQL. LOB dành cho nội dung lớn và có API đọc/ghi theo từng phần. Dùng LOB cho mọi chuỗi nhỏ cũng không phải lựa chọn tối ưu; hãy chọn kiểu theo kích thước, cách truy cập và vòng đời dữ liệu.

## 2. LOB locator là gì?

### 2.1. Locator là tham chiếu, không phải payload

Khi truy vấn cột CLOB:

~~~sql
SELECT document_body
FROM   documents
WHERE  document_id = 100;
~~~

Oracle có thể trả về locator của LOB. Ứng dụng dùng locator để đọc nội dung, thay vì bắt buộc chuyển toàn bộ CLOB thành một biến chuỗi có kích thước cố định.

Trong PL/SQL:

~~~sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT document_body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100;

    DBMS_OUTPUT.PUT_LINE(
        'Length = ' || DBMS_LOB.GETLENGTH(l_body)
    );
END;
/
~~~

Biến `l_body` giữ locator tới CLOB. `DBMS_LOB.GETLENGTH` lấy độ dài LOB; nó không yêu cầu in toàn bộ nội dung.

### 2.2. Locator và dữ liệu được quản lý riêng

Locator cho phép Oracle xác định LOB value và vị trí lưu trữ của nó. Internal LOB có metadata lưu trong database; payload có thể nằm trong hàng hoặc LOB segment. Oracle quản lý cấu trúc lưu trữ và index nội bộ liên quan.

Không tự sửa các segment hoặc index nội bộ của LOB. Dùng SQL và DBMS_LOB API để thao tác nội dung; dùng dictionary views để quan sát metadata.

### 2.3. Sao chép locator không đồng nghĩa sao chép nội dung

Nếu gán một locator vào biến locator khác, không nên mặc định rằng Oracle đã tạo một bản sao độc lập của toàn bộ LOB. Muốn sao chép nội dung sang LOB đích, dùng các thao tác như `DBMS_LOB.COPY` hoặc `DBMS_LOB.APPEND` phù hợp.

Điều này quan trọng khi ứng dụng cần giữ một bản nội dung độc lập trước khi chỉnh sửa. Hãy tạo LOB đích và copy payload, thay vì chỉ gán locator rồi nghĩ rằng hai nội dung đã tách rời.

### 2.4. Locator có vòng đời gắn với session/connection

Trong ứng dụng, locator do database trả về gắn với connection và ngữ cảnh thực thi tương ứng. Với JDBC, hãy đọc/ghi LOB và hoàn tất stream khi connection còn hợp lệ. Không giữ locator hoặc stream rồi trả connection về pool, đóng connection hay dùng nó từ một connection khác.

Trong PL/SQL, locator local thường được dùng trong phạm vi block/procedure. Với persistent LOB, nếu muốn ghi nội dung của hàng hiện có, cần khóa hàng theo cách phù hợp, thường dùng `SELECT ... FOR UPDATE`.

## 3. Persistent LOB, temporary LOB và BFILE

### 3.1. Persistent LOB

Persistent LOB là BLOB/CLOB/NCLOB được lưu trong cột của một hàng. Nó có vòng đời theo dữ liệu bảng:
- Tạo hàng và khởi tạo LOB.
- Lấy locator để đọc/ghi.
- Commit thay đổi cùng transaction.
- Cập nhật hoặc thay thế nội dung.
- Xóa hàng hoặc đặt cột LOB thành NULL khi nghiệp vụ yêu cầu.

Persistent LOB được database quản lý trong transaction và backup/recovery của database.

### 3.2. Temporary LOB

Temporary LOB được tạo để xử lý nội dung trung gian, chẳng hạn ghép văn bản lớn, tạo nội dung trả về hoặc biến đổi LOB. Nó không phải một LOB value được lưu như cột persistent của hàng.

Có thể tạo tường minh bằng `DBMS_LOB.CREATETEMPORARY` và giải phóng bằng `DBMS_LOB.FREETEMPORARY`. Temporary LOB tiêu thụ tài nguyên temporary tablespace/session; không giải phóng đúng cách có thể làm tăng mức sử dụng tài nguyên, đặc biệt trong ứng dụng connection pool.

### 3.3. BFILE

BFILE là locator tới file bên ngoài. Database không sở hữu payload file và BFILE là read-only qua DBMS_LOB. File phải tồn tại trên máy chủ database trong đường dẫn được DIRECTORY object ánh xạ, và tài khoản database cần quyền READ trên DIRECTORY.

### 3.4. So sánh vòng đời

| Thuộc tính | Persistent LOB | Temporary LOB | BFILE |
| --- | --- | --- | --- |
| Payload ở đâu? | Database | Temporary storage | File system bên ngoài |
| Có nằm trong cột bảng? | Có | Không nhất thiết | Cột lưu locator |
| Ghi nội dung? | Có, theo quyền và transaction | Có | Không qua BFILE |
| Transaction | Tham gia transaction của dữ liệu | Có quy tắc riêng theo temporary LOB | Nội dung file ngoài DB không thuộc transaction |
| Giải phóng | Theo UPDATE/DELETE và quản lý segment | FREETEMPORARY hoặc hết duration | FILECLOSE; file do OS quản lý |
| Backup database | Có | Không như dữ liệu persistent | File phải backup riêng |

## 4. In-row và out-of-row storage

### 4.1. Locator vẫn nằm trong hàng

Với internal LOB, hàng trong bảng luôn chứa locator/metadata cần thiết để truy cập LOB. Khác biệt in-row/out-of-row là **payload LOB** được lưu ở đâu.

- **In-row:** locator và payload LOB nhỏ được lưu cùng hàng bảng.
- **Out-of-row:** hàng chứa locator, còn payload nằm trong LOB segment riêng.

Vì vậy, out-of-row không có nghĩa hàng không chứa gì liên quan đến LOB. Locator vẫn là cầu nối để Oracle tìm payload.

### 4.2. ENABLE STORAGE IN ROW

Mặc định, Oracle thường cho phép lưu payload LOB nhỏ ngay trong hàng bằng `ENABLE STORAGE IN ROW`. Giá trị nhỏ (thường đến khoảng 4 KB, tùy giới hạn và điều kiện hàng) có thể được lưu in-row. Payload lớn hơn được lưu out-of-row.

Ví dụ:

~~~sql
CREATE TABLE document_notes (
    note_id NUMBER PRIMARY KEY,
    note_text CLOB
)
LOB (note_text) STORE AS SECUREFILE (
    ENABLE STORAGE IN ROW
);
~~~

In-row có thể giúp đọc LOB nhỏ nhanh hơn vì payload nằm cùng hàng, tránh truy cập LOB segment riêng cho trường hợp đó. Đổi lại, hàng bảng lớn hơn.

### 4.3. DISABLE STORAGE IN ROW

Có thể yêu cầu payload LOB luôn được lưu out-of-row:

~~~sql
CREATE TABLE document_payloads (
    payload_id NUMBER PRIMARY KEY,
    payload BLOB
)
LOB (payload) STORE AS SECUREFILE (
    DISABLE STORAGE IN ROW
    NOCACHE
);
~~~

Ngay cả LOB nhỏ cũng được lưu trong LOB segment; hàng giữ locator. Điều này có thể giữ hàng bảng gọn hơn khi nội dung LOB thường lớn hoặc được truy cập riêng biệt.

### 4.4. So sánh

| Tiêu chí | In-row | Out-of-row |
| --- | --- | --- |
| Vị trí payload | Trong table row | LOB segment |
| Kích thước hàng | Tăng theo payload nhỏ | Hàng giữ locator, payload tách riêng |
| Truy cập LOB nhỏ | Có thể ít bước I/O hơn | Có thể cần truy cập LOB segment |
| Quét nhiều hàng không cần nội dung LOB | Hàng có thể lớn hơn | Hàng thường gọn hơn |
| LOB lớn | Không lưu inline khi vượt ngưỡng | Lưu out-of-row |
| Kiểm soát | ENABLE STORAGE IN ROW | DISABLE STORAGE IN ROW |

### 4.5. Không phải mọi LOB đều nên ép out-of-row

Nếu ứng dụng thường truy vấn metadata và đọc các CLOB ngắn, in-row có thể hữu ích. Nếu bảng có hàng triệu bản ghi và truy vấn thường chỉ đọc cột khóa/trạng thái mà không cần LOB, payload out-of-row có thể giúp giảm kích thước hàng và tăng mật độ block.

Quyết định phụ thuộc kích thước payload, tỷ lệ truy cập LOB, pattern scan, cache và workload. Không chọn chỉ theo cảm giác.

### 4.6. Ngưỡng 4 KB không phải cam kết tuyệt đối về kích thước hàng

Quy tắc thường gặp là payload LOB nhỏ đến khoảng 4 KB có thể được lưu in-row khi bật ENABLE STORAGE IN ROW. Khả năng thực tế còn liên quan row format và không gian hàng. Payload lớn hơn ngưỡng được lưu out-of-row. Kiểm tra tài liệu đúng release và đo trên dữ liệu thực tế.

## 5. LOB segment, LOB index và CHUNK

### 5.1. LOB segment

Khi payload được lưu out-of-row, Oracle dùng LOB segment để lưu nội dung. Một cột LOB có thể có segment riêng; với bảng partitioned, tổ chức storage có thể được phân theo partition/subpartition.

LOB segment do Oracle quản lý. Không truy cập trực tiếp block hoặc tự cập nhật segment để sửa nội dung.

### 5.2. LOB index

Oracle tạo và quản lý LOB index nội bộ để ánh xạ locator tới các phần dữ liệu LOB. Đây không phải index nghiệp vụ thông thường để ứng dụng tự tạo predicate. Không tự DROP, rebuild hoặc sửa LOB index nội bộ ngoài các thao tác được Oracle hỗ trợ.

### 5.3. CHUNK

Với BasicFiles, `CHUNK` xác định đơn vị cấp phát/đọc ghi LOB theo block hoặc nhóm block. Chọn chunk phù hợp với kích thước và pattern truy cập; chunk quá lớn có thể lãng phí cho thao tác nhỏ, chunk quá nhỏ có thể tăng overhead.

SecureFiles quản lý storage khác BasicFiles; không áp dụng máy móc mọi tham số BasicFiles cho SecureFiles. Xem SQL Language Reference và LOB storage clause theo phiên bản Oracle.

### 5.4. Quan sát segment

Có thể kiểm tra các segment trong schema:

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       bytes,
       blocks
FROM   user_segments
WHERE  segment_type LIKE 'LOB%'
ORDER  BY segment_type, segment_name;
~~~

Tên segment có thể do Oracle sinh. Dùng metadata từ USER_LOBS để xác định cột LOB tương ứng.

## 6. BasicFiles và SecureFiles

### 6.1. BasicFiles

BasicFiles là cách triển khai LOB truyền thống. Nó hỗ trợ internal LOB nhưng có ít khả năng tối ưu và tính năng hơn SecureFiles. Một số tham số như CHUNK và PCTVERSION thường xuất hiện trong cấu hình BasicFiles.

### 6.2. SecureFiles

SecureFiles là kiến trúc LOB hiện đại của Oracle, được thiết kế để tăng hiệu năng và hỗ trợ các tính năng như:
- Compression.
- Deduplication.
- Encryption.
- Caching và quản lý storage được cải thiện.

Khả năng sử dụng phụ thuộc phiên bản, cấu hình database, tablespace và chính sách license. SecureFiles thường yêu cầu tablespace dùng Automatic Segment Space Management (ASSM) và cấu hình tương thích phù hợp.

### 6.3. Tạo SecureFiles LOB

~~~sql
CREATE TABLE documents (
    document_id NUMBER GENERATED ALWAYS AS IDENTITY,
    title       VARCHAR2(200) NOT NULL,
    body        CLOB,
    payload     BLOB,
    CONSTRAINT pk_documents PRIMARY KEY (document_id)
)
LOB (body) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    NOCACHE
    LOGGING
)
LOB (payload) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    DISABLE STORAGE IN ROW
    NOCACHE
    LOGGING
);
~~~

Ví dụ giả định tablespace LOB_TS đã tồn tại và thỏa yêu cầu SecureFiles. Hãy điều chỉnh tên tablespace và tùy chọn theo môi trường.

### 6.4. Tạo BasicFiles LOB

~~~sql
CREATE TABLE legacy_documents (
    document_id NUMBER PRIMARY KEY,
    body CLOB
)
LOB (body) STORE AS BASICFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    CHUNK 8192
    PCTVERSION 10
    NOCACHE
    LOGGING
);
~~~

Đây là ví dụ cho schema cần BasicFiles. Với hệ thống mới, hãy đánh giá SecureFiles trước; không chuyển đổi chỉ vì một tham số riêng lẻ có vẻ hấp dẫn.

### 6.5. Compression, deduplication và encryption

SecureFiles có thể hỗ trợ:
- **Compression:** giảm dung lượng với dữ liệu phù hợp, đổi lại tiêu thụ CPU khi nén/giải nén.
- **Deduplication:** nhận diện nội dung trùng để giảm lưu trữ, hữu ích khi nhiều LOB giống nhau.
- **Encryption:** bảo vệ dữ liệu lưu trữ theo cấu hình Oracle.

Các tùy chọn này có thể có yêu cầu license hoặc giới hạn tính năng theo edition/version. Xác nhận chính sách license và kiểm thử chi phí CPU, latency, dung lượng trước khi bật.

## 7. CACHE, NOCACHE và LOGGING

### 7.1. CACHE

CACHE cho phép LOB blocks tham gia buffer cache theo chính sách của Oracle. Có thể hữu ích khi ứng dụng thường xuyên đọc lại cùng LOB hoặc đọc nhiều lần trong một phiên.

### 7.2. NOCACHE

NOCACHE hạn chế đưa LOB data vào buffer cache theo hành vi storage của Oracle. Có thể phù hợp với LOB lớn, truy cập ít lặp lại hoặc workload không muốn LOB chiếm cache của dữ liệu OLTP.

### 7.3. CACHE READS

Một số cấu hình hỗ trợ CACHE READS, tức cache khi đọc nhưng không áp dụng cùng chính sách cache cho ghi. Kiểm tra cú pháp và hành vi theo loại LOB và phiên bản.

### 7.4. LOGGING và NOLOGGING

LOGGING/NOLOGGING ảnh hưởng redo generation cho các thao tác được hỗ trợ. NOLOGGING không đồng nghĩa “không cần backup” hoặc “không có rủi ro phục hồi”. Nó có thể ảnh hưởng khả năng media recovery và Data Guard tùy thao tác/cấu hình.

Không chọn NOLOGGING chỉ để tăng tốc nếu chưa đánh giá backup, recovery, standby và yêu cầu bảo vệ dữ liệu.

## 8. NULL, EMPTY_CLOB và EMPTY_BLOB

### 8.1. NULL khác LOB rỗng

Một cột LOB có thể là NULL hoặc chứa một LOB value rỗng:
- NULL: không có LOB locator hợp lệ để thao tác nội dung.
- EMPTY_CLOB()/EMPTY_BLOB(): tạo một LOB rỗng đã được khởi tạo, có thể lấy locator và ghi thêm dữ liệu.

Ví dụ:

~~~sql
INSERT INTO documents (title, body, payload)
VALUES ('Draft', EMPTY_CLOB(), EMPTY_BLOB());
~~~

Không dùng NULL khi dự định gọi DBMS_LOB.WRITE hoặc WRITEAPPEND mà chưa khởi tạo LOB phù hợp.

### 8.2. Kiểm tra NULL và độ dài

~~~sql
SELECT document_id,
       CASE WHEN body IS NULL THEN 'NULL' ELSE 'NOT NULL' END AS body_state,
       CASE
           WHEN body IS NULL THEN NULL
           ELSE DBMS_LOB.GETLENGTH(body)
       END AS body_length
FROM   documents;
~~~

LOB rỗng có locator và độ dài 0; LOB NULL không có locator. Kiểm tra trạng thái NULL trước khi gọi API yêu cầu locator hợp lệ.

### 8.3. Khởi tạo qua UPDATE

~~~sql
UPDATE documents
SET body = EMPTY_CLOB()
WHERE document_id = 100;
~~~

Sau đó có thể lấy locator bằng SELECT FOR UPDATE để ghi nội dung.

## 9. Tạo và ghi persistent LOB bằng DBMS_LOB

### 9.1. INSERT và RETURNING locator

Cách thường dùng để tạo hàng rồi ghi nội dung ngay trong cùng block:

~~~sql
DECLARE
    l_body CLOB;
    l_text VARCHAR2(32767) := 'Nội dung tài liệu mới';
BEGIN
    INSERT INTO documents (title, body)
    VALUES ('Getting Started', EMPTY_CLOB())
    RETURNING body INTO l_body;

    IF l_text IS NOT NULL THEN
        DBMS_LOB.WRITEAPPEND(
            l_body,
            LENGTH(l_text),
            l_text
        );
    END IF;

    COMMIT;
END;
/
~~~

RETURNING lấy locator của LOB vừa khởi tạo. WRITEAPPEND thêm nội dung vào cuối CLOB. Với CLOB, amount được tính theo ký tự; với BLOB, amount được tính theo byte.

Trong ứng dụng thật, không COMMIT bên trong procedure dùng chung nếu transaction thuộc quyền kiểm soát của caller. Ví dụ COMMIT ở đây chỉ để minh họa một script độc lập.

### 9.2. Ghi vào LOB đã có

Khi cập nhật một LOB persistent hiện hữu, lấy locator và khóa hàng:

~~~sql
DECLARE
    l_body CLOB;
    l_text VARCHAR2(32767) := 'Phần bổ sung';
BEGIN
    SELECT body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100
    FOR UPDATE;

    IF l_body IS NULL THEN
        UPDATE documents
        SET body = EMPTY_CLOB()
        WHERE document_id = 100
        RETURNING body INTO l_body;
    END IF;

    IF l_text IS NOT NULL THEN
        DBMS_LOB.WRITEAPPEND(
            l_body,
            LENGTH(l_text),
            l_text
        );
    END IF;

    COMMIT;
END;
/
~~~

SELECT FOR UPDATE khóa hàng để bảo vệ cập nhật LOB theo transaction. Nếu LOB đang NULL, cần khởi tạo locator trước khi ghi.

### 9.3. WRITE và WRITEAPPEND

- WRITE ghi dữ liệu tại offset chỉ định.
- WRITEAPPEND thêm dữ liệu vào cuối LOB.

Ví dụ ghi từ đầu:

~~~sql
DBMS_LOB.WRITE(
    lob_loc => l_body,
    amount  => LENGTH(l_text),
    offset  => 1,
    buffer  => l_text
);
~~~

WRITE không tự động cắt phần dữ liệu cũ phía sau vùng vừa ghi. Nếu muốn thay toàn bộ nội dung, cần TRIM về 0 trước khi ghi hoặc thay LOB bằng giá trị mới theo cách phù hợp.

### 9.4. Thay toàn bộ nội dung

~~~sql
DECLARE
    l_body CLOB;
    l_text VARCHAR2(32767) := 'Nội dung thay thế';
BEGIN
    SELECT body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100
    FOR UPDATE;

    IF l_body IS NULL THEN
        UPDATE documents
        SET body = EMPTY_CLOB()
        WHERE document_id = 100
        RETURNING body INTO l_body;
    ELSE
        DBMS_LOB.TRIM(l_body, 0);
    END IF;

    IF l_text IS NOT NULL THEN
        DBMS_LOB.WRITEAPPEND(l_body, LENGTH(l_text), l_text);
    END IF;
END;
/
~~~

TRIM giảm độ dài LOB xuống số đơn vị được chỉ định. Với CLOB, length tính theo ký tự; với BLOB, theo byte. Ví dụ chưa COMMIT để caller quyết định transaction.

### 9.5. Ghi BLOB theo byte

Với BLOB, buffer có kiểu RAW. Ví dụ dữ liệu byte minh họa:

~~~sql
DECLARE
    l_payload BLOB;
    l_chunk   RAW(32767);
BEGIN
    l_chunk := HEXTORAW('4F5241434C45');

    INSERT INTO documents (title, payload)
    VALUES ('Binary sample', EMPTY_BLOB())
    RETURNING payload INTO l_payload;

    DBMS_LOB.WRITEAPPEND(
        l_payload,
        UTL_RAW.LENGTH(l_chunk),
        l_chunk
    );
END;
/
~~~

Hex 4F5241434C45 là byte minh họa. Khi xử lý file thật, đọc byte từ stream/file; không giả định mọi dữ liệu nhị phân có thể chuyển an toàn qua chuỗi ký tự.

## 10. Đọc LOB theo từng phần

### 10.1. GETLENGTH

Lấy độ dài LOB:

~~~sql
SELECT document_id,
       DBMS_LOB.GETLENGTH(body) AS body_length
FROM   documents
WHERE  body IS NOT NULL;
~~~

GETLENGTH trả số ký tự cho CLOB/NCLOB và số byte cho BLOB/BFILE theo loại locator.

### 10.2. SUBSTR

DBMS_LOB.SUBSTR lấy một phần nội dung:

~~~sql
DECLARE
    l_body  CLOB;
    l_piece VARCHAR2(4000);
BEGIN
    SELECT body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100;

    l_piece := DBMS_LOB.SUBSTR(l_body, 1000, 1);

    DBMS_OUTPUT.PUT_LINE(l_piece);
END;
/
~~~

Tham số thứ hai là số đơn vị đọc; tham số thứ ba là offset bắt đầu. Với CLOB, offset/amount theo ký tự; với BLOB, theo byte. Giá trị trả về còn chịu giới hạn kiểu VARCHAR2/RAW của PL/SQL và bộ ký tự.

Không dùng SUBSTR để tải toàn bộ LOB rất lớn vào một biến VARCHAR2. Đọc theo chunk.

### 10.3. READ

DBMS_LOB.READ đọc vào buffer PL/SQL:

~~~sql
DECLARE
    l_body   CLOB;
    l_buffer VARCHAR2(32767);
    l_amount PLS_INTEGER := 1000;
    l_offset PLS_INTEGER := 1;
BEGIN
    SELECT body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100;

    IF l_body IS NOT NULL THEN
        DBMS_LOB.READ(
            lob_loc => l_body,
            amount  => l_amount,
            offset  => l_offset,
            buffer  => l_buffer
        );

        DBMS_OUTPUT.PUT_LINE(l_buffer);
    END IF;
END;
/
~~~

READ có thể điều chỉnh amount theo lượng dữ liệu thực tế đọc được. Với LOB lớn, lặp qua các offset để xử lý từng phần; cần kiểm soát kích thước buffer và điều kiện kết thúc.

### 10.4. Vòng lặp đọc chunk

~~~sql
DECLARE
    l_body   CLOB;
    l_buffer VARCHAR2(32767);
    l_offset INTEGER := 1;
    l_amount INTEGER;
    l_length INTEGER;
BEGIN
    SELECT body
    INTO   l_body
    FROM   documents
    WHERE  document_id = 100;

    IF l_body IS NOT NULL THEN
        l_length := DBMS_LOB.GETLENGTH(l_body);

        WHILE l_offset <= l_length LOOP
            l_amount := LEAST(4000, l_length - l_offset + 1);

            DBMS_LOB.READ(
                l_body,
                l_amount,
                l_offset,
                l_buffer
            );

            -- Xử lý chunk tại đây; không nhất thiết in toàn bộ.
            l_offset := l_offset + l_amount;
        END LOOP;
    END IF;
END;
/
~~~

Trong ứng dụng, xử lý từng chunk và ghi ra stream/file hoặc parser tương ứng. Tránh nối mọi chunk vào một VARCHAR2 nếu tổng nội dung có thể vượt giới hạn bộ nhớ.

## 11. Các thao tác DBMS_LOB quan trọng

| API | Mục đích |
| --- | --- |
| GETLENGTH | Lấy độ dài LOB |
| SUBSTR | Lấy một đoạn LOB |
| READ | Đọc một đoạn vào buffer |
| WRITE | Ghi tại offset |
| WRITEAPPEND | Ghi thêm vào cuối |
| APPEND | Thêm nội dung từ một LOB nguồn |
| COPY | Sao chép một đoạn từ LOB nguồn sang LOB đích |
| TRIM | Cắt LOB về độ dài chỉ định |
| ERASE | Xóa/ghi đè một vùng theo quy tắc LOB |
| INSTR | Tìm chuỗi hoặc mẫu byte trong LOB |
| COMPARE | So sánh nội dung LOB |
| OPEN/CLOSE | Mở/đóng LOB tường minh khi cần |

### 11.1. APPEND và COPY

APPEND nối toàn bộ nội dung của source LOB vào destination LOB:

~~~sql
DBMS_LOB.APPEND(
    dest_lob => l_destination,
    src_lob  => l_source
);
~~~

COPY cho phép chọn amount và offset nguồn/đích:

~~~sql
DBMS_LOB.COPY(
    dest_lob    => l_destination,
    src_lob     => l_source,
    amount      => 1000,
    dest_offset => 1,
    src_offset  => 1
);
~~~

Các locator phải hợp lệ và tương thích loại LOB. Nếu cần tạo bản sao độc lập, hãy tạo LOB đích trước rồi copy payload.

### 11.2. TRIM và ERASE khác nhau

- TRIM giảm độ dài LOB từ cuối.
- ERASE thay thế nội dung trong một vùng theo quy tắc của loại LOB, nhưng không nhất thiết giảm độ dài LOB.

Với BLOB, vùng bị erase được điền byte zero; với CLOB, vùng được điền khoảng trắng theo ngữ nghĩa LOB. Hãy kiểm tra API và offset/amount theo loại dữ liệu trước khi dùng.

### 11.3. INSTR và COMPARE

INSTR tìm vị trí chuỗi hoặc mẫu byte trong LOB. COMPARE so sánh một vùng của hai LOB. Các API này hữu ích khi cần tìm hoặc xác nhận nội dung mà không tải toàn bộ LOB về client.

### 11.4. OPEN và CLOSE

DBMS_LOB.OPEN/CLOSE cho phép mở LOB tường minh cho một chuỗi thao tác. Không phải mọi thao tác LOB đều bắt buộc gọi OPEN trước. Khi đã OPEN tường minh, hãy CLOSE sau khi hoàn tất và trước khi kết thúc transaction theo hướng dẫn Oracle, đặc biệt nếu có index phụ thuộc nội dung LOB.

Dùng exception handler để bảo đảm đóng LOB khi có lỗi. Đừng giữ LOB đã mở lâu hơn cần thiết.

## 12. Temporary LOB và giải phóng tài nguyên

### 12.1. Tạo temporary LOB

~~~sql
DECLARE
    l_temp CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_temp,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        l_temp,
        LENGTH('Temporary content'),
        'Temporary content'
    );

    DBMS_OUTPUT.PUT_LINE(
        'Length = ' || DBMS_LOB.GETLENGTH(l_temp)
    );

    DBMS_LOB.FREETEMPORARY(l_temp);
END;
/
~~~

DBMS_LOB.CALL giới hạn duration theo call; DBMS_LOB.SESSION giữ temporary LOB trong session cho đến khi được giải phóng hoặc session kết thúc. Chọn duration theo vòng đời thực tế, ưu tiên phạm vi ngắn khi có thể.

### 12.2. Kiểm tra temporary LOB

~~~sql
IF DBMS_LOB.ISTEMPORARY(l_temp) = 1 THEN
    DBMS_LOB.FREETEMPORARY(l_temp);
END IF;
~~~

ISTEMPORARY cho biết locator có tham chiếu temporary LOB hay không. Chỉ gọi FREETEMPORARY với locator temporary hợp lệ.

### 12.3. Giải phóng trong exception handler

~~~sql
DECLARE
    l_temp CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        l_temp,
        LENGTH('Working data'),
        'Working data'
    );

    -- Xử lý dữ liệu tại đây.

    DBMS_LOB.FREETEMPORARY(l_temp);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_temp) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_temp);
        END IF;
        RAISE;
END;
/
~~~

Trong code production, bảo đảm cleanup chạy trên mọi đường thoát. Nếu có nhiều temporary LOB, cần quản lý từng locator rõ ràng. Không bắt exception rồi bỏ qua lỗi chỉ để hoàn tất cleanup.

### 12.4. Temporary LOB được tạo ngầm

Một số phép toán SQL/PLSQL trên LOB, chẳng hạn nối chuỗi LOB hoặc hàm trả về LOB, có thể tạo temporary LOB ngầm. Ứng dụng cần biết khi nào kết quả là temporary LOB và giải phóng theo API phù hợp nếu lifetime vượt phạm vi tự động của call.

Đừng giả định mọi locator CLOB/BLOB đều là persistent. Dùng ISTEMPORARY khi cần phân biệt trong code quản lý tài nguyên.

### 12.5. Connection pool

Với connection pool:
- Không để temporary LOB SESSION tồn tại vô thời hạn trong connection được tái sử dụng.
- Giải phóng temporary LOB trước khi trả connection về pool.
- Đóng stream và locator object ở tầng driver theo API.
- Không giữ locator giữa hai request độc lập.
- Theo dõi temporary tablespace và session resource khi có workload LOB lớn.

## 13. BFILE và file bên ngoài database

### 13.1. Tạo DIRECTORY object

Ví dụ DBA tạo directory object:

~~~sql
CREATE DIRECTORY import_files AS '/u01/app/import';
GRANT READ ON DIRECTORY import_files TO app_user;
~~~

Đường dẫn là đường dẫn trên database server, không phải máy client. Oracle database process cần quyền OS phù hợp để đọc file. DIRECTORY object không tự cấp quyền cho OS.

### 13.2. Tạo BFILE locator

~~~sql
DECLARE
    l_file BFILE;
BEGIN
    l_file := BFILENAME('IMPORT_FILES', 'sample.bin');

    IF DBMS_LOB.FILEEXISTS(l_file) = 1 THEN
        DBMS_OUTPUT.PUT_LINE(
            'File bytes = ' || DBMS_LOB.GETLENGTH(l_file)
        );
    ELSE
        DBMS_OUTPUT.PUT_LINE('File not found');
    END IF;
END;
/
~~~

BFILENAME tạo locator; nó không đọc toàn bộ file và không chứng minh caller có quyền OS ngoài các quyền database/OS đã cấu hình.

### 13.3. Mở, đọc và đóng BFILE

~~~sql
DECLARE
    l_file   BFILE;
    l_buffer RAW(32767);
    l_amount BINARY_INTEGER := 100;
BEGIN
    l_file := BFILENAME('IMPORT_FILES', 'sample.bin');

    IF DBMS_LOB.FILEEXISTS(l_file) = 1 THEN
        DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);

        DBMS_LOB.READ(
            lob_loc => l_file,
            amount  => l_amount,
            offset  => 1,
            buffer  => l_buffer
        );

        DBMS_OUTPUT.PUT_LINE(
            'Read bytes = ' || UTL_RAW.LENGTH(l_buffer)
        );

        DBMS_LOB.FILECLOSE(l_file);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
~~~

BFILE là read-only. FILECLOSE sau khi đọc là bước quan trọng để giải phóng handle file.

### 13.4. BFILE không nằm trong backup database

Vì payload ở file system bên ngoài, backup database không tự bảo vệ file. Cần:
- Backup thư mục file riêng.
- Đồng bộ retention giữa hàng lưu locator và file.
- Kiểm tra file tồn tại khi đọc.
- Bảo vệ quyền OS và DIRECTORY.
- Có quy trình xử lý khi file bị đổi tên hoặc xóa ngoài database.

Nếu yêu cầu dữ liệu phải được backup/recover cùng transaction database, cân nhắc lưu nội dung trong BLOB thay vì BFILE.

## 14. Kiểm tra metadata LOB

### 14.1. USER_LOBS

Xem cấu hình LOB của schema hiện tại:

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       index_name,
       tablespace_name,
       securefile,
       in_row,
       chunk,
       cache,
       logging
FROM   user_lobs
ORDER  BY table_name, column_name;
~~~

Một số cột hoặc giá trị hiển thị phụ thuộc phiên bản Oracle và kiểu storage. USER_LOBS giúp liên kết cột LOB với segment/index nội bộ.

### 14.2. DBA_LOBS và ALL_LOBS

- USER_LOBS: LOB thuộc schema hiện tại.
- ALL_LOBS: LOB mà user có quyền xem.
- DBA_LOBS: LOB trên toàn database, cần quyền DBA phù hợp.

Dùng view theo đúng phạm vi quyền; không cấp quyền DBA chỉ để ứng dụng đọc metadata.

### 14.3. Segment và dung lượng

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       bytes / 1024 / 1024 AS size_mb
FROM   user_segments
WHERE  segment_type LIKE 'LOB%'
ORDER  BY bytes DESC;
~~~

Dung lượng segment đã cấp phát không nhất thiết bằng tổng độ dài payload đang được tham chiếu. Xóa hoặc trim LOB có thể tạo không gian tái sử dụng bên trong segment; việc trả dung lượng cho tablespace là một bài toán quản trị riêng.

### 14.4. LOB partition

Với bảng partitioned, xem USER_LOB_PARTITIONS hoặc USER_LOB_SUBPARTITIONS nếu release có view tương ứng. LOB storage có thể được tổ chức theo partition; khi thêm, exchange, truncate hoặc drop partition, hãy xem xét cả table partition và LOB partition metadata.

## 15. Vòng đời persistent LOB và thu hồi không gian

### 15.1. Tạo

Khởi tạo LOB bằng EMPTY_CLOB/EMPTY_BLOB, lấy locator qua RETURNING hoặc SELECT FOR UPDATE, rồi ghi payload. NULL và empty LOB có ý nghĩa khác nhau.

### 15.2. Đọc

Lấy locator từ hàng, dùng GETLENGTH/SUBSTR/READ hoặc stream của driver. Với nội dung lớn, đọc theo chunk thay vì materialize toàn bộ vào bộ nhớ.

### 15.3. Cập nhật

Có thể thay toàn bộ LOB, ghi tại offset hoặc append. Khi ghi vào hàng hiện hữu, dùng transaction và khóa hàng phù hợp. Nếu ghi đè từ đầu, nhớ xử lý phần đuôi cũ bằng TRIM nếu nội dung mới ngắn hơn.

### 15.4. Xóa

Đặt cột LOB thành NULL hoặc xóa hàng theo quy tắc nghiệp vụ. Dữ liệu không còn được tham chiếu, nhưng segment có thể vẫn giữ dung lượng đã cấp phát để tái sử dụng. Đừng giả định DELETE một hàng sẽ làm datafile nhỏ lại ngay.

### 15.5. Thu hồi không gian

Quản lý không gian LOB phụ thuộc BasicFiles/SecureFiles, segment, partitioning, tablespace và phiên bản. Trước khi dùng shrink/move/rebuild, xem tài liệu quản trị và đánh giá khóa, I/O, thời gian, availability. Không chạy thao tác reclaim trên production chỉ để xử lý một con số segment mà chưa kiểm tra mức sử dụng thực tế.

## 16. LOB trong ứng dụng và JDBC

### 16.1. Dùng stream thay vì tải toàn bộ

Với Java JDBC:
- CLOB/NCLOB có thể đọc bằng character stream.
- BLOB có thể đọc bằng binary stream.
- Khi ghi, dùng character/binary stream hoặc API LOB tương ứng của driver.
- Đóng stream sau khi hoàn tất.
- Giữ connection hợp lệ trong toàn bộ thời gian đọc/ghi.

Ví dụ đọc CLOB:

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT body FROM documents WHERE document_id = ?")) {
    ps.setLong(1, 100L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (Reader reader = rs.getCharacterStream("BODY")) {
                char[] buffer = new char[8192];
                int count;

                while ((count = reader.read(buffer)) != -1) {
                    // Xử lý phần ký tự vừa đọc.
                }
            }
        }
    }
}
~~~

Ví dụ đọc BLOB:

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT payload FROM documents WHERE document_id = ?")) {
    ps.setLong(1, 100L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (InputStream in = rs.getBinaryStream("PAYLOAD")) {
                byte[] buffer = new byte[8192];
                int count;

                while ((count = in.read(buffer)) != -1) {
                    // Ghi chunk vào file hoặc xử lý binary.
                }
            }
        }
    }
}
~~~

### 16.2. Locator và stream có lifetime

Không trả locator/stream ra khỏi tầng repository rồi đóng connection ngay. Hãy đọc hết stream trong phạm vi connection hợp lệ hoặc thiết kế API streaming có ownership rõ ràng để connection không bị trả về pool quá sớm.

### 16.3. Không dùng DBMS_OUTPUT để truyền payload

DBMS_OUTPUT là buffer văn bản phục vụ debug, không phải kênh vận chuyển file hoặc LOB lớn. Dùng JDBC streams, REST streaming, object storage hoặc cơ chế file transfer phù hợp.

## 17. Hiệu năng và nguyên tắc lựa chọn

### 17.1. Chọn in-row/out-of-row theo pattern

Đặt câu hỏi:
- LOB thường nhỏ hay lớn?
- Truy vấn bảng có thường đọc LOB không?
- Có nhiều truy vấn chỉ đọc metadata mà không đọc payload không?
- Ứng dụng đọc toàn bộ hay theo từng phần?
- Có nhiều hàng trong cùng block không?
- LOB có được cập nhật thường xuyên không?

In-row có thể giảm bước truy cập cho LOB nhỏ. Out-of-row có thể giữ hàng gọn khi payload lớn hoặc ít được đọc.

### 17.2. Chọn CACHE/NOCACHE theo workload

Đo tỷ lệ đọc lại, working set và áp lực buffer cache. CACHE có thể hữu ích cho nội dung thường xuyên đọc; NOCACHE có thể phù hợp với payload lớn ít tái sử dụng. Không có lựa chọn đúng cho mọi bảng.

### 17.3. Tránh round-trip quá nhỏ

Đọc LOB theo chunk quá nhỏ làm tăng số lần gọi API/round-trip. Chunk quá lớn lại tăng memory footprint. Chọn kích thước chunk dựa trên driver, mạng, bộ nhớ và throughput thực tế.

### 17.4. Tránh in hoặc chuyển đổi toàn bộ LOB

DBMS_OUTPUT, VARCHAR2 và các log text không phải nơi phù hợp để chứa toàn bộ file lớn. Chỉ đọc đoạn cần thiết hoặc stream trực tiếp sang consumer.

### 17.5. Đo trước khi thay đổi storage

Thay đổi SecureFiles, compression, deduplication, caching hoặc in-row policy có thể ảnh hưởng CPU, I/O, dung lượng và latency. Dùng dữ liệu đại diện, đo cả read/write và kiểm tra backup/recovery trước khi triển khai.

## 18. Những lỗi và hiểu nhầm thường gặp

**“LOB locator chính là nội dung LOB.”** Không. Locator là tham chiếu; payload có thể được lưu ở nơi khác.

**“Out-of-row nghĩa là locator không nằm trong hàng.”** Không. Hàng vẫn lưu locator; payload nằm trong LOB segment.

**“CLOB và BLOB dùng offset theo cùng đơn vị.”** Không. CLOB/NCLOB dùng đơn vị ký tự theo API; BLOB dùng byte.

**“NULL và EMPTY_CLOB giống nhau.”** Không. NULL không có locator để thao tác; EMPTY_CLOB tạo LOB rỗng đã khởi tạo.

**“Gán locator sang biến khác là sao chép nội dung.”** Không nên giả định như vậy. Dùng DBMS_LOB.COPY/APPEND để copy payload.

**“DBMS_LOB.WRITE ghi đè và tự cắt phần đuôi cũ.”** Không. Nếu cần thay toàn bộ, cân nhắc TRIM hoặc thay LOB value.

**“Temporary LOB tự biến mất ngay khi không dùng.”** Không nên dựa vào giả định đó. Chọn duration và giải phóng rõ ràng bằng FREETEMPORARY.

**“BFILE là BLOB có đường dẫn.”** Không. BFILE là locator external, read-only và file không nằm trong backup database.

**“In-row luôn nhanh hơn.”** Không. Hàng lớn hơn có thể làm giảm mật độ block và tăng chi phí khi truy vấn không cần LOB.

**“Out-of-row luôn tốt hơn cho LOB lớn.”** Không thể kết luận chỉ từ kích thước; pattern truy cập và storage layout cũng quan trọng.

**“DELETE LOB lập tức thu nhỏ datafile.”** Không. Segment có thể giữ không gian để tái sử dụng; reclaim là công việc quản trị riêng.

**“DBMS_LOB.OPEN luôn bắt buộc.”** Không. Chỉ dùng OPEN/CLOSE tường minh khi có lý do; nếu đã mở, hãy đóng đúng cách.

## 19. Bài thực hành

Các bài tập dùng schema học tập. Điều chỉnh tablespace và quyền theo môi trường.

### Bài 1 — Tạo bảng CLOB/BLOB

Tạo bảng DOCUMENTS có CLOB và BLOB. Xác định cột nào chứa văn bản và cột nào chứa byte.

### Bài 2 — So sánh NULL và EMPTY_CLOB

Insert một hàng có BODY NULL và một hàng có EMPTY_CLOB. Dùng IS NULL và DBMS_LOB.GETLENGTH để so sánh.

### Bài 3 — Ghi CLOB bằng RETURNING

Insert EMPTY_CLOB, lấy locator bằng RETURNING INTO và dùng WRITEAPPEND để ghi nội dung. Commit và đọc lại độ dài.

### Bài 4 — Ghi BLOB

Tạo BLOB rỗng và ghi một RAW chunk. Kiểm tra độ dài bằng GETLENGTH.

### Bài 5 — Đọc CLOB theo chunk

Dùng DBMS_LOB.READ trong vòng lặp. Ghi lại offset và amount của từng lần đọc.

### Bài 6 — Thay nội dung ngắn hơn

Ghi một nội dung dài, sau đó thay bằng nội dung ngắn hơn. So sánh kết quả khi chỉ WRITE từ offset 1 với khi TRIM về 0 trước khi ghi.

### Bài 7 — Copy LOB

Tạo LOB đích, dùng DBMS_LOB.COPY để sao chép một phần LOB nguồn. So sánh GETLENGTH và COMPARE.

### Bài 8 — Temporary LOB

Tạo CLOB temporary với duration CALL, ghi dữ liệu, kiểm tra ISTEMPORARY và gọi FREETEMPORARY. Thử thêm exception để kiểm tra cleanup.

### Bài 9 — In-row và out-of-row

Tạo hai bảng có ENABLE STORAGE IN ROW và DISABLE STORAGE IN ROW. Nạp LOB nhỏ và lớn, quan sát metadata và segment. Không kết luận chỉ từ một hàng.

### Bài 10 — SecureFiles và BasicFiles

Tạo hai bảng demo với loại storage được môi trường hỗ trợ. So sánh USER_LOBS, segment và khả năng cấu hình. Kiểm tra ASSM và compatibility trước khi tạo SecureFiles.

### Bài 11 — BFILE

Tạo DIRECTORY object do DBA quản lý, cấp READ cho schema test, tạo BFILE locator và đọc một đoạn file. Đóng file trong cả đường thành công và exception.

### Bài 12 — JDBC streaming

Viết Java code đọc CLOB bằng Reader và BLOB bằng InputStream. Đảm bảo stream được đóng trước khi connection được trả về pool.

### Bài 13 — Theo dõi dung lượng

Truy vấn USER_LOBS và USER_SEGMENTS. So sánh dung lượng segment với tổng độ dài LOB đang được tham chiếu; giải thích vì sao hai số không nhất thiết bằng nhau.

### Bài 14 — Lập kế hoạch vòng đời

Thiết kế quy trình upload, đọc, cập nhật, xóa và backup một tài liệu lớn. Nêu rõ nơi lưu payload, ai sở hữu locator/stream và thời điểm giải phóng từng tài nguyên.

## 20. Tài liệu Oracle tham khảo

- [Oracle Database SecureFiles and Large Objects Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/): LOB locator, storage, SecureFiles, BasicFiles và cách làm việc với LOB.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_LOB](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_LOB.html): READ, WRITE, WRITEAPPEND, COPY, APPEND, TRIM, OPEN/CLOSE và temporary LOB.
- [Oracle Database SQL Language Reference — LOB Storage Clause](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LOB-storage-clause.html): ENABLE/DISABLE STORAGE IN ROW và cấu hình lưu trữ LOB.
- [Oracle Database Reference — USER_LOBS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_LOBS.html): metadata các cột LOB trong schema.
- [Oracle Database Reference — USER_SEGMENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_SEGMENTS.html): dung lượng segment.
- [Oracle Database SQL Language Reference — CREATE DIRECTORY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-DIRECTORY.html): directory object dùng với BFILE.

LOB locator là tham chiếu giúp truy cập nội dung lớn mà không cần tải toàn bộ payload vào một biến chuỗi. Với internal LOB, locator nằm trong hàng còn payload có thể in-row hoặc out-of-row; BasicFiles và SecureFiles có mô hình lưu trữ cùng khả năng khác nhau. Hãy phân biệt persistent LOB, temporary LOB và BFILE, dùng DBMS_LOB để đọc/ghi theo chunk, giải phóng temporary LOB và đóng BFILE/stream đúng vòng đời. **Thiết kế LOB tốt phải tính cả vị trí lưu payload, cách truy cập, transaction, connection và tài nguyên cần thu hồi.**
