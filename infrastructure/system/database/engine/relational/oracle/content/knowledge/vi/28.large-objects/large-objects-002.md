# SecureFiles, BasicFiles và điều kiện lựa chọn cơ chế lưu trữ LOB trong Oracle

## 1. LOB là gì?

LOB (Large Object) là kiểu dữ liệu dùng để lưu nội dung lớn như tài liệu, ảnh, âm thanh, video, PDF, XML, JSON hoặc văn bản dài. Oracle Database có bốn kiểu LOB chính:

| Kiểu | Nội dung | Cách lưu |
| --- | --- | --- |
| BLOB | Dữ liệu nhị phân | Lưu byte, không diễn giải theo character set |
| CLOB | Văn bản theo database character set | Lưu ký tự |
| NCLOB | Văn bản theo national character set | Lưu ký tự theo national character set |
| BFILE | Tệp nhị phân bên ngoài database | Locator tới file hệ điều hành; Oracle chỉ đọc |

BLOB, CLOB và NCLOB là internal LOB: nội dung thuộc database và được Oracle quản lý. BFILE là external LOB: nội dung nằm ngoài database, trong thư mục trên máy chủ database; Oracle lưu locator và cung cấp API đọc file.

LOB khác VARCHAR2/RAW ở chỗ có thể chứa lượng dữ liệu lớn hơn nhiều giới hạn scalar column. Một LOB column có thể lưu nội dung lớn trong khi row của bảng chỉ giữ locator hoặc một phần dữ liệu nhỏ.

## 2. LOB locator và vị trí lưu dữ liệu

### 2.1. Locator không phải nội dung LOB

Khi ứng dụng SELECT một LOB column, Oracle thường trả về một LOB locator. Locator là tham chiếu cho phép truy cập nội dung LOB; nó không nhất thiết chứa toàn bộ nội dung tài liệu.

Với internal LOB:
- Row của bảng chứa locator.
- Nội dung nhỏ có thể được lưu ngay trong row nếu bật STORAGE IN ROW và đáp ứng giới hạn.
- Nội dung lớn thường được lưu trong LOB segment riêng.
- Oracle quản lý các block, phiên bản dữ liệu và metadata cần thiết để truy cập LOB.

~~~text
DOCUMENTS
  +----------------------------------------------+
  | DOC_ID | FILE_NAME | PAYLOAD_LOCATOR         |
  +----------------------------------------------+
                          |
                          v
                LOB segment (out-of-row)
                +-----------------------+
                | LOB data              |
                | LOB metadata          |
                +-----------------------+
~~~

Tên segment và cách tổ chức vật lý phụ thuộc loại LOB storage, partitioning và cấu hình. Không thao tác trực tiếp lên LOB index nội bộ như một index nghiệp vụ thông thường.

### 2.2. In-row và out-of-row

Oracle hỗ trợ:
- ENABLE STORAGE IN ROW: cho phép lưu LOB nhỏ ngay trong row của bảng.
- DISABLE STORAGE IN ROW: lưu LOB ngoài row, locator nằm trong row.

~~~sql
CREATE TABLE document_store (
    document_id NUMBER PRIMARY KEY,
    file_name   VARCHAR2(255 CHAR),
    content     BLOB
)
LOB (content) STORE AS SECUREFILE (
    ENABLE STORAGE IN ROW
);
~~~

Với ENABLE STORAGE IN ROW, LOB nhỏ (thông thường tối đa khoảng 4.000 byte, còn phụ thuộc kích thước row và overhead) có thể được lưu inline. LOB lớn hơn sẽ được lưu out-of-row. Không xem 4.000 byte là cam kết rằng mọi nội dung có kích thước đó đều luôn nằm inline; row còn có các cột và overhead khác.

Chọn ENABLE STORAGE IN ROW khi có nhiều LOB nhỏ và ứng dụng thường đọc cùng row và nội dung LOB. Chọn DISABLE STORAGE IN ROW khi LOB thường rất lớn, muốn row table gọn hoặc workload thường đọc metadata mà không đọc nội dung. Đo kích thước LOB thực tế và tỷ lệ truy cập metadata/nội dung trước khi quyết định.

## 3. Persistent LOB, temporary LOB và BFILE

### 3.1. Persistent LOB

Persistent LOB là LOB được lưu trong một row của bảng. BLOB, CLOB và NCLOB có thể là persistent LOB. Chúng tham gia transaction và recovery theo cơ chế database.

~~~sql
CREATE TABLE document_store (
    document_id NUMBER PRIMARY KEY,
    content CLOB
);
~~~

### 3.2. Temporary LOB

Temporary LOB được tạo trong thời gian xử lý để phục vụ thao tác trung gian, chẳng hạn ghép chuỗi lớn, chuyển đổi nội dung hoặc chuẩn bị payload trước khi ghi vào bảng.

Temporary LOB sử dụng temporary tablespace và có vòng đời do session/call quản lý tùy cách tạo. Cần giải phóng khi không còn sử dụng.

~~~sql
DECLARE
    l_buffer CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_buffer,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_buffer,
        amount  => LENGTH('Temporary text'),
        buffer  => 'Temporary text'
    );

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_buffer));
    DBMS_LOB.FREETEMPORARY(l_buffer);
END;
/
~~~

Nếu exception xảy ra trước FREETEMPORARY, nên có exception handler hoặc cấu trúc cleanup để giải phóng temporary LOB. Không để temporary LOB tồn tại lâu hơn cần thiết trong session dùng chung.

### 3.3. BFILE

BFILE trỏ tới file bên ngoài database. Oracle không lưu nội dung file trong datafile và không cho phép sửa nội dung file qua BFILE locator bằng DBMS_LOB.

~~~sql
CREATE DIRECTORY import_dir AS '/u01/app/import';
GRANT READ ON DIRECTORY import_dir TO app_user;

CREATE TABLE external_documents (
    document_id NUMBER PRIMARY KEY,
    file_name   VARCHAR2(255),
    external_file BFILE
);

INSERT INTO external_documents(document_id, file_name, external_file)
VALUES (1, 'manual.pdf', BFILENAME('IMPORT_DIR', 'manual.pdf'));
~~~

BFILE có các đặc điểm:
- Nội dung file nằm trên filesystem của database server.
- Database lưu directory object và tên file trong locator.
- Oracle chỉ cung cấp quyền đọc file qua BFILE.
- File phải tồn tại và database server process phải có quyền đọc.
- Backup database không tự động bảo vệ nội dung file ngoài database.

Nếu file bị đổi tên, xóa hoặc quyền filesystem thay đổi, locator có thể không đọc được. Cần backup và quản lý file ngoài database riêng. BFILE không phải BasicFiles hay SecureFiles; hai cơ chế đó áp dụng cho internal LOB.

## 4. BasicFiles và SecureFiles

Oracle có hai kiến trúc lưu trữ internal LOB:

- **BasicFiles:** cơ chế LOB truyền thống, tồn tại từ các phiên bản Oracle cũ.
- **SecureFiles:** kiến trúc LOB mới hơn, được giới thiệu từ Oracle Database 11g, cung cấp hiệu năng và các khả năng lưu trữ nâng cao.

SecureFiles được Oracle khuyến nghị cho phần lớn workload LOB mới. BasicFiles chủ yếu cần thiết khi duy trì hệ thống cũ, tương thích hoặc có giới hạn kỹ thuật/triển khai cụ thể.

### 4.1. BasicFiles

BasicFiles sử dụng kiến trúc LOB truyền thống:
- Lưu dữ liệu trong LOB segment riêng khi out-of-row.
- Có tham số CHUNK để điều khiển đơn vị lưu trữ LOB.
- Có thể sử dụng PCTVERSION để quản lý không gian giữ phiên bản cũ của LOB.
- Không có đầy đủ các tính năng SecureFiles như deduplication và compression tích hợp.
- Có thể dùng trong tablespace với ASSM hoặc MSSM theo điều kiện hỗ trợ.

BasicFiles phù hợp với hệ thống cũ cần giữ nguyên storage format, ứng dụng đã được kiểm thử với BasicFiles, workload không cần tính năng SecureFiles hoặc môi trường có ràng buộc tương thích. BasicFiles là công nghệ cũ và đã được Oracle đánh dấu deprecated trong các phiên bản mới hơn, nhưng vẫn có thể gặp trong hệ thống hiện hữu. Cần xem tài liệu hỗ trợ và chính sách nâng cấp của đúng release đang vận hành.

### 4.2. SecureFiles

SecureFiles là kiến trúc internal LOB hiện đại hơn. Các khả năng đáng chú ý:
- Cải thiện hiệu năng đọc/ghi LOB trong nhiều workload.
- Hỗ trợ compression, deduplication và encryption.
- Hỗ trợ các tùy chọn cache, logging và retention phù hợp.
- Quản lý không gian và xử lý LOB linh hoạt hơn BasicFiles.

SecureFiles yêu cầu tablespace sử dụng Automatic Segment Space Management (ASSM). SecureFiles cũng yêu cầu mức COMPATIBLE phù hợp, từ 11.1.0 trở lên.

~~~sql
CREATE TABLE document_secure (
    document_id NUMBER PRIMARY KEY,
    file_name   VARCHAR2(255 CHAR),
    content     BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    NOCACHE
    LOGGING
);
~~~

### 4.3. So sánh

| Tiêu chí | BasicFiles | SecureFiles |
| --- | --- | --- |
| Kiến trúc | Truyền thống | Mới hơn, tối ưu cho LOB |
| ASSM | Không bắt buộc trong mọi trường hợp | Bắt buộc |
| COMPATIBLE | Hỗ trợ các môi trường cũ | Cần mức tương thích từ 11.1.0 trở lên |
| CHUNK | Có tham số CHUNK | Không cấu hình theo cách BasicFiles |
| PCTVERSION | Có thể dùng | Dùng cơ chế RETENTION thay vì PCTVERSION |
| Compression | Không có SecureFiles LOB compression | Có |
| Deduplication | Không có tính năng SecureFiles dedup | Có |
| Encryption | Không có cơ chế SecureFiles encryption | Có |
| Khuyến nghị | Duy trì legacy khi cần | Ưu tiên cho thiết kế mới nếu đủ điều kiện |

Không suy ra rằng SecureFiles luôn nhanh hơn trong mọi trường hợp. Kết quả còn phụ thuộc kích thước LOB, cache, storage, redo, mức nén, pattern truy cập và cấu hình hệ thống.

## 5. Điều kiện tạo SecureFiles

### 5.1. Tablespace phải dùng ASSM

SecureFiles yêu cầu tablespace quản lý segment space tự động. Có thể kiểm tra:

~~~sql
SELECT tablespace_name,
       segment_space_management,
       extent_management,
       allocation_type
FROM user_tablespaces
ORDER BY tablespace_name;
~~~

Nếu cần xem toàn database và có quyền:

~~~sql
SELECT tablespace_name, segment_space_management
FROM dba_tablespaces
ORDER BY tablespace_name;
~~~

Giá trị SEGMENT_SPACE_MANAGEMENT phải là AUTO để dùng SecureFiles. Tablespace MSSM không đáp ứng điều kiện này.

### 5.2. Kiểm tra COMPATIBLE

~~~sql
SHOW PARAMETER compatible;
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
~~~

SecureFiles cần COMPATIBLE từ 11.1.0 trở lên. Thay đổi COMPATIBLE là quyết định quản trị database có ảnh hưởng lớn tới khả năng downgrade và tương thích; không nâng chỉ để tạo SecureFiles nếu chưa có kế hoạch tổng thể.

### 5.3. Kiểm tra DB_SECUREFILE

~~~sql
SHOW PARAMETER db_securefile;
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'db_securefile';
~~~

DB_SECUREFILE điều khiển việc tạo SecureFiles. Các giá trị và hành vi cụ thể phụ thuộc cấu hình Oracle; giá trị thường gặp gồm PERMITTED, ALWAYS, FORCE, NEVER và IGNORE. PERMITTED cho phép tạo SecureFiles khi được chỉ định và các điều kiện khác đáp ứng. NEVER ngăn tạo SecureFiles.

Không giả định mọi LOB column tự động trở thành SecureFiles chỉ vì database là Oracle 19c. Hãy chỉ định rõ STORE AS SECUREFILE hoặc STORE AS BASICFILE khi cần kết quả xác định, sau đó kiểm tra dictionary.

### 5.4. Edition và license

SecureFiles storage cơ bản và các tính năng mở rộng có thể có điều kiện license riêng. Đặc biệt:
- SecureFiles compression và deduplication gắn với Oracle Advanced Compression Option.
- SecureFiles encryption gắn với Oracle Advanced Security Option/TDE theo chính sách cấp phép.

Điều kiện license thay đổi theo edition, deployment và hợp đồng. Trước khi bật COMPRESS, DEDUPLICATE hoặc ENCRYPT trong production, phải kiểm tra Oracle Licensing Information hiện hành và entitlement của tổ chức.
## 6. Chỉ định BasicFiles hoặc SecureFiles khi tạo bảng

### 6.1. Tạo BasicFiles rõ ràng

~~~sql
CREATE TABLE document_basic (
    document_id NUMBER PRIMARY KEY,
    content     BLOB
)
LOB (content) STORE AS BASICFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    CHUNK 8192
    PCTVERSION 10
    NOCACHE
    LOGGING
);
~~~

CHUNK là đơn vị lưu trữ liên quan tới BasicFiles. Giá trị phải phù hợp block size và workload. PCTVERSION dành cho việc giữ các phiên bản LOB cũ để phục vụ consistent read theo cơ chế BasicFiles.

### 6.2. Tạo SecureFiles rõ ràng

~~~sql
CREATE TABLE document_secure (
    document_id NUMBER PRIMARY KEY,
    content     BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    NOCACHE
    LOGGING
);
~~~

SecureFiles không dùng CHUNK và PCTVERSION theo cách cấu hình BasicFiles. SecureFiles sử dụng cơ chế quản lý version/retention riêng.

### 6.3. Nhiều LOB column

Một bảng có thể có nhiều LOB column và mỗi cột có thể có storage clause riêng:

~~~sql
CREATE TABLE customer_documents (
    customer_id NUMBER PRIMARY KEY,
    profile_xml CLOB,
    avatar      BLOB,
    contract_pdf BLOB
)
LOB (profile_xml) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    CACHE READS
)
LOB (avatar) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    CACHE
)
LOB (contract_pdf) STORE AS SECUREFILE (
    TABLESPACE archive_lob_ts
    NOCACHE
    LOGGING
);
~~~

Các LOB column có pattern truy cập khác nhau có thể dùng storage option khác nhau. Ví dụ avatar thường được đọc nhiều, contract PDF có thể lớn và ít được đọc.

### 6.4. Không dựa vào default nếu cần kiểm soát

Default storage có thể phụ thuộc DB_SECUREFILE, COMPATIBLE và cách tạo bảng. Đối với hệ thống cần triển khai nhất quán giữa dev/test/prod, nên chỉ định loại storage tường minh và kiểm tra USER_LOBS sau khi tạo.

## 7. Các tùy chọn SecureFiles quan trọng

### 7.1. CACHE, CACHE READS và NOCACHE

Các tùy chọn cache ảnh hưởng cách LOB data sử dụng database buffer cache:
- CACHE: LOB data được cache trong buffer cache khi truy cập.
- CACHE READS: cache khi đọc; phù hợp một số workload đọc nhiều, ghi ít.
- NOCACHE: không cache LOB data theo cách thông thường; phù hợp LOB lớn, ít đọc hoặc streaming.

~~~sql
LOB (avatar) STORE AS SECUREFILE (CACHE)
~~~

~~~sql
LOB (manual_pdf) STORE AS SECUREFILE (NOCACHE)
~~~

Không chọn CACHE chỉ vì muốn mọi thứ nhanh. LOB rất lớn có thể chiếm buffer cache và đẩy dữ liệu hữu ích khác ra ngoài. NOCACHE cũng không có nghĩa mọi metadata đều bỏ qua cache.

### 7.2. LOGGING và NOLOGGING

LOGGING là lựa chọn an toàn thông thường cho recovery. NOLOGGING có thể giảm redo cho một số thao tác được hỗ trợ, nhưng có thể làm giảm khả năng phục hồi media đối với dữ liệu được tạo theo chế độ đó.

~~~sql
LOB (payload) STORE AS SECUREFILE (LOGGING)
~~~

~~~sql
LOB (staging_payload) STORE AS SECUREFILE (NOLOGGING)
~~~

NOLOGGING không có nghĩa database hoàn toàn không sinh redo. FORCE LOGGING ở cấp database/tablespace có thể ghi đè lựa chọn. Trước khi dùng NOLOGGING, phải xem xét RMAN backup, Data Guard, standby apply, recovery window và quy trình backup sau thao tác.

### 7.3. Compression

SecureFiles có thể nén LOB:

~~~sql
LOB (content) STORE AS SECUREFILE (
    COMPRESS MEDIUM
)
~~~

Các mức nén SecureFiles gồm LOW, MEDIUM và HIGH theo cú pháp Oracle hỗ trợ. Mức nén càng cao có thể giảm dung lượng hơn nhưng tăng CPU hoặc ảnh hưởng latency. Hãy đo trên dữ liệu thật; PDF, JPEG, ZIP, video hoặc dữ liệu đã nén có thể không tiết kiệm thêm nhiều.

Compression hữu ích khi nội dung có tính lặp hoặc dư thừa, storage cost là yếu tố quan trọng và workload có thể chấp nhận CPU overhead. Không bật compression đồng loạt trên mọi LOB column. Kiểm tra tỷ lệ tiết kiệm và tác động CPU/latency trước khi triển khai.

### 7.4. Deduplication

SecureFiles deduplication tìm các LOB content trùng lặp để tránh lưu nhiều bản vật lý giống nhau trong phạm vi được Oracle hỗ trợ:

~~~sql
LOB (document_content) STORE AS SECUREFILE (
    DEDUPLICATE
)
~~~

Nếu nhiều row chứa cùng một file hoặc nội dung giống hệt nhau, deduplication có thể giảm dung lượng. Ví dụ kho tài liệu có nhiều bản hợp đồng template hoặc file hướng dẫn dùng chung.

Không nhầm deduplication với unique constraint:
- Deduplication là tối ưu lưu trữ vật lý.
- Nó không làm các row trở thành một row.
- Mỗi row vẫn có locator và semantics riêng.
- DML, quyền truy cập và metadata của từng row vẫn được quản lý.

Deduplication có thể tiêu tốn CPU để phát hiện nội dung trùng. Nó hữu ích khi dữ liệu trùng lặp thực sự cao; nếu mỗi LOB là duy nhất, lợi ích có thể thấp.

Có thể dùng KEEP_DUPLICATES để không deduplicate:

~~~sql
LOB (private_payload) STORE AS SECUREFILE (
    KEEP_DUPLICATES
)
~~~

### 7.5. Encryption

SecureFiles hỗ trợ mã hóa LOB:

~~~sql
LOB (sensitive_document) STORE AS SECUREFILE (
    ENCRYPT USING 'AES256'
)
~~~

Encryption bảo vệ dữ liệu LOB lưu trên storage theo cơ chế Transparent Data Encryption. Cần cấu hình keystore/wallet và quyền quản trị phù hợp. Encryption không thay thế authorization ở ứng dụng; user có quyền SELECT hợp lệ vẫn có thể đọc nội dung qua database.

Trước khi bật encryption, xem key management và backup keystore, khả năng restore khi chuyển database, Data Guard/standby, hiệu năng CPU, license và chính sách bảo mật.

### 7.6. Kết hợp nhiều tùy chọn

Ví dụ kho tài liệu ít thay đổi, nhiều bản trùng và cần tiết kiệm dung lượng:

~~~sql
CREATE TABLE legal_documents (
    document_id NUMBER PRIMARY KEY,
    owner_id    NUMBER NOT NULL,
    payload     BLOB
)
LOB (payload) STORE AS SECUREFILE (
    TABLESPACE secure_lob_ts
    DISABLE STORAGE IN ROW
    NOCACHE
    LOGGING
    COMPRESS MEDIUM
    DEDUPLICATE
);
~~~

Đây chỉ là cấu hình minh họa. Không dùng COMPRESS/DEDUPLICATE nếu chưa có license phù hợp và chưa đo workload.

## 8. BasicFiles storage parameters và quản lý phiên bản

### 8.1. CHUNK

CHUNK xác định đơn vị lưu trữ liên quan tới BasicFiles LOB. Giá trị được tính theo byte và có ràng buộc với database block size.

Nếu chunk quá lớn so với các thao tác thường chỉ đọc một phần nhỏ, có thể gây đọc thêm dữ liệu. Nếu quá nhỏ, metadata và số lần I/O có thể tăng. Hãy chọn theo pattern đọc/ghi và đo thực tế.

SecureFiles dùng kiến trúc quản lý LOB khác; không áp dụng tư duy tinh chỉnh CHUNK của BasicFiles cho SecureFiles.

### 8.2. PCTVERSION

BasicFiles dùng PCTVERSION để chỉ tỷ lệ không gian LOB segment có thể dành cho các phiên bản cũ. Phiên bản cũ cần thiết cho consistent read khi một transaction khác đang sửa LOB.

Nếu PCTVERSION quá thấp, có thể không giữ đủ old versions cho các truy vấn dài. Nếu quá cao, segment có thể dành nhiều không gian cho phiên bản cũ hơn cần thiết.

### 8.3. RETENTION

LOB storage có thể sử dụng RETENTION để điều khiển việc giữ phiên bản cũ theo thời gian retention/undo semantics. SecureFiles sử dụng RETENTION thay cho PCTVERSION.

Không nhầm RETENTION của LOB với retention policy nghiệp vụ:
- LOB RETENTION liên quan đến khả năng giữ old LOB versions cho consistent read.
- Business retention xác định dữ liệu được giữ trong hệ thống bao lâu.

Hai khái niệm phục vụ mục đích khác nhau.

## 9. DML và thao tác LOB bằng SQL

### 9.1. INSERT LOB trực tiếp

Với nội dung nhỏ, có thể INSERT literal hoặc bind variable phù hợp:

~~~sql
INSERT INTO document_store(document_id, content)
VALUES (1, TO_CLOB('Small text document'));
~~~

Đối với BLOB lớn, ứng dụng thường bind dữ liệu theo stream/LOB API thay vì nhúng literal vào SQL.

### 9.2. EMPTY_CLOB và EMPTY_BLOB

EMPTY_CLOB() và EMPTY_BLOB() tạo empty LOB locator, không phải NULL:

~~~sql
INSERT INTO document_store(document_id, content)
VALUES (2, EMPTY_CLOB());
~~~

Điều này hữu ích khi muốn tạo row trước rồi ghi nội dung bằng DBMS_LOB. Cột NULL và empty LOB khác nhau:
- NULL: không có locator/nội dung được gán.
- EMPTY_CLOB/EMPTY_BLOB: có locator cho LOB rỗng.

### 9.3. RETURNING locator để ghi LOB

Ví dụ ghi CLOB:

~~~sql
DECLARE
    l_content CLOB;
    l_text    VARCHAR2(1000) := 'Oracle SecureFiles example';
BEGIN
    INSERT INTO document_store(document_id, content)
    VALUES (3, EMPTY_CLOB())
    RETURNING content INTO l_content;

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_content,
        amount  => LENGTH(l_text),
        buffer  => l_text
    );

    COMMIT;
END;
/
~~~

Với CLOB, amount được tính theo đơn vị ký tự; với BLOB, thao tác dùng byte. Đọc tài liệu DBMS_LOB cho đúng overload và đơn vị trước khi ghi dữ liệu nhị phân hoặc dữ liệu đa byte.

### 9.4. Cập nhật toàn bộ LOB

~~~sql
UPDATE document_store
SET content = TO_CLOB('Replacement text')
WHERE document_id = 3;
~~~

Đây là cách thay toàn bộ giá trị CLOB bằng nội dung mới. Với LOB lớn, ứng dụng nên cân nhắc streaming và LOB API thay vì truyền chuỗi khổng lồ qua câu SQL.

### 9.5. Truy cập một phần LOB bằng DBMS_LOB

Các routine thường dùng:

| Routine | Mục đích |
| --- | --- |
| GETLENGTH | Lấy độ dài LOB |
| SUBSTR | Đọc một phần LOB |
| READ | Đọc dữ liệu theo offset |
| WRITE | Ghi dữ liệu tại offset |
| WRITEAPPEND | Ghi nối vào cuối |
| APPEND | Nối một LOB vào LOB khác |
| COPY | Sao chép một vùng LOB |
| TRIM | Cắt ngắn LOB |
| ERASE | Xóa một vùng nội dung |
| COMPARE | So sánh nội dung LOB |
| CREATETEMPORARY | Tạo temporary LOB |
| FREETEMPORARY | Giải phóng temporary LOB |

~~~sql
DECLARE
    l_content CLOB;
    l_piece   VARCHAR2(100);
BEGIN
    SELECT content
    INTO l_content
    FROM document_store
    WHERE document_id = 3
    FOR UPDATE;

    l_piece := DBMS_LOB.SUBSTR(l_content, 100, 1);
    DBMS_OUTPUT.PUT_LINE(l_piece);
END;
/
~~~

Với persistent LOB cần sửa, thường lấy locator trong câu SELECT FOR UPDATE hoặc dùng cơ chế locator/DML được Oracle hỗ trợ. Không dùng locator đã hết scope hoặc locator không còn hợp lệ.

### 9.6. OPEN và CLOSE

DBMS_LOB.OPEN/CLOSE có thể dùng khi thực hiện nhiều thao tác trên một LOB. Với một số loại functional/domain index liên quan LOB, việc mở rồi đóng LOB giúp Oracle trì hoãn index maintenance tới CLOSE thay vì cập nhật sau từng thao tác ghi. Chỉ dùng khi hiểu index dependency và phải luôn CLOSE trong cả success/failure path.

## 10. Temporary LOB và quản lý tài nguyên

Temporary LOB có thể phát sinh khi dùng hàm thao tác CLOB trả về một LOB tạm, ghép nhiều chuỗi lớn, chuyển đổi giữa CLOB/NCLOB, dùng DBMS_LOB.CREATETEMPORARY hoặc xử lý dữ liệu trung gian trong PL/SQL.

Temporary LOB tiêu thụ temporary tablespace và có thể tăng mạnh nếu ứng dụng tạo nhiều LOB lớn hoặc không giải phóng.

~~~sql
DECLARE
    l_temp_clob CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_temp_clob,
        cache   => FALSE,
        dur     => DBMS_LOB.SESSION
    );

    -- Thực hiện các thao tác trên l_temp_clob.

    DBMS_LOB.FREETEMPORARY(l_temp_clob);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_temp_clob);
        END IF;
        RAISE;
END;
/
~~~

Nếu dùng duration CALL, Oracle quản lý vòng đời theo call. Nếu dùng duration SESSION, ứng dụng cần đảm bảo giải phóng đúng lúc hoặc đóng session. Trong connection pool, session sống lâu nên việc quên cleanup có thể làm tăng temporary LOB usage.
## 11. Chọn CACHE, COMPRESSION, DEDUPLICATION và ENCRYPTION theo workload

### 11.1. Ma trận lựa chọn

| Workload | Hướng cân nhắc | Lý do |
| --- | --- | --- |
| Ảnh avatar nhỏ, đọc thường xuyên | ENABLE STORAGE IN ROW nếu kích thước phù hợp; CACHE | Nội dung nhỏ và hay được đọc cùng row |
| Video lớn, đọc streaming, ít cập nhật | DISABLE STORAGE IN ROW; NOCACHE | Tránh đẩy LOB lớn vào buffer cache |
| PDF hợp đồng, đọc không thường xuyên | SecureFiles; NOCACHE hoặc CACHE READS | Tối ưu theo tỷ lệ đọc và cache pressure |
| Nhiều file giống hệt nhau | SecureFiles DEDUPLICATE | Có thể tiết kiệm dung lượng |
| Văn bản lớn, dễ nén | SecureFiles COMPRESS sau benchmark | Giảm storage nếu CPU overhead chấp nhận được |
| Nội dung nhạy cảm | SecureFiles ENCRYPT và TDE | Bảo vệ dữ liệu at-rest |
| CLOB được cập nhật thường xuyên từng phần | Benchmark SecureFiles và API DBMS_LOB | Pattern random/partial update ảnh hưởng hiệu năng |
| Legacy application, không đủ điều kiện SecureFiles | Giữ BasicFiles trong kế hoạch chuyển đổi | Tránh thay đổi storage khi chưa sẵn sàng |

### 11.2. Không bật tất cả tính năng cùng lúc

Compression, deduplication và encryption có thể tác động đồng thời tới CPU, I/O, latency, redo và khả năng quản trị key. Không bật tất cả chỉ vì SecureFiles hỗ trợ.

Quy trình lựa chọn:
1. Đo phân bố kích thước LOB.
2. Đo tỷ lệ đọc/ghi và kích thước mỗi lần đọc/ghi.
3. Kiểm tra tỷ lệ nội dung trùng.
4. Đo khả năng nén của dữ liệu thật.
5. Xác định yêu cầu encryption và key management.
6. Benchmark trên storage tương tự production.
7. So sánh throughput, p95/p99 latency, CPU, I/O, redo và dung lượng.
8. Kiểm tra license và recovery trước khi triển khai.

## 12. SecureFiles và BasicFiles trong bảng partitioned

Bảng partitioned có thể lưu LOB theo partition. Mỗi partition có LOB segment tương ứng và có thể đặt storage option theo yêu cầu.

~~~sql
CREATE TABLE archived_documents (
    document_id NUMBER NOT NULL,
    created_at  DATE NOT NULL,
    payload     BLOB
)
PARTITION BY RANGE (created_at)
(
    PARTITION p2025 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026 VALUES LESS THAN (DATE '2027-01-01')
)
LOB (payload) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    NOCACHE
    LOGGING
);
~~~

Với partition maintenance, cần xem LOB segment của partition nào bị tác động, LOB index nội bộ, local/global indexes khác, dung lượng cần thiết khi MOVE/EXCHANGE và tính năng compression/encryption có được hỗ trợ cho thao tác cụ thể không.

Metadata LOB partition có thể xem qua USER_LOB_PARTITIONS hoặc DBA_LOB_PARTITIONS.

## 13. Di chuyển BasicFiles sang SecureFiles

### 13.1. Vì sao chuyển đổi?

Có thể chuyển đổi khi muốn dùng compression, deduplication hoặc encryption; workload LOB cần hiệu năng tốt hơn; chuẩn hóa kiến trúc lưu trữ cho ứng dụng mới; hoặc BasicFiles trở thành rào cản cho chiến lược vận hành.

Không chuyển đổi chỉ vì SecureFiles mới hơn. Trước tiên đo lợi ích, xác nhận license, kiểm tra tablespace ASSM và lập kế hoạch downtime/space.

### 13.2. MOVE LOB

Với bảng không partition, có thể dùng ALTER TABLE MOVE LOB để chuyển LOB segment:

~~~sql
ALTER TABLE document_basic
MOVE LOB (content)
STORE AS SECUREFILE (
    TABLESPACE lob_ts
    NOCACHE
    LOGGING
);
~~~

Lệnh này tạo lại cách lưu trữ LOB theo SecureFiles. Cần kiểm tra cú pháp/giới hạn của release và loại bảng cụ thể, dự trù dung lượng tạm thời, thời gian DDL và tác động khóa.

### 13.3. Kiểm tra sau chuyển đổi

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       tablespace_name,
       securefile,
       in_row,
       cache,
       logging,
       compression,
       deduplication,
       encrypt
FROM user_lobs
WHERE table_name = 'DOCUMENT_BASIC';
~~~

SECUREFILE cần hiển thị YES sau chuyển đổi. Cần đối chiếu row count, DBMS_LOB.GETLENGTH, checksum/hash ở tầng ứng dụng nếu yêu cầu và thử đọc/ghi bằng ứng dụng.

### 13.4. Chuyển đổi khi bảng đang phục vụ ứng dụng

ALTER TABLE MOVE LOB có thể có tác động khóa và downtime tùy thao tác, phiên bản và đối tượng. Nếu yêu cầu availability cao, đánh giá DBMS_REDEFINITION hoặc chiến lược copy/swap:
1. Tạo bảng đích có SecureFiles.
2. Đồng bộ dữ liệu và các thay đổi phát sinh.
3. Tạo lại constraint, index, grants, trigger và dependency cần thiết.
4. Kiểm tra dữ liệu.
5. Chuyển đổi tên/đối tượng theo quy trình được kiểm soát.

DBMS_REDEFINITION có điều kiện hỗ trợ và có thể yêu cầu materialized view log hoặc quyền riêng. Không áp dụng như một lệnh tự động cho mọi bảng LOB.

### 13.5. Rollback plan

Trước chuyển đổi:
- Backup hoặc bảo đảm có restore point/recovery strategy phù hợp.
- Ghi lại DDL, grants, indexes, constraints và triggers.
- Đo dung lượng source/destination.
- Chuẩn bị kế hoạch quay lại bằng bảng/segment cũ hoặc restore.
- Kiểm tra dữ liệu LOB sau migration.

DDL có implicit commit. Không thể rollback MOVE LOB bằng câu ROLLBACK thông thường.

## 14. Theo dõi LOB storage bằng data dictionary

### 14.1. USER_LOBS

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       tablespace_name,
       securefile,
       in_row,
       cache,
       logging,
       compression,
       deduplication,
       encrypt
FROM user_lobs
ORDER BY table_name, column_name;
~~~

Các cột hữu ích:
- TABLE_NAME và COLUMN_NAME: LOB column.
- SEGMENT_NAME: LOB segment.
- TABLESPACE_NAME: tablespace.
- SECUREFILE: loại storage.
- IN_ROW: có bật storage in row hay không.
- CACHE và LOGGING: lựa chọn cache/logging.
- COMPRESSION, DEDUPLICATION, ENCRYPT: tính năng SecureFiles.

Một số cột dictionary phụ thuộc phiên bản và quyền; nếu query báo invalid identifier, xem Reference của đúng release.

### 14.2. DBA_LOBS và ALL_LOBS

DBA_LOBS cho toàn database nếu có quyền:

~~~sql
SELECT owner,
       table_name,
       column_name,
       segment_name,
       tablespace_name,
       securefile
FROM dba_lobs
ORDER BY owner, table_name, column_name;
~~~

ALL_LOBS hiển thị LOB columns mà user có quyền nhìn thấy.

### 14.3. LOB partitions

~~~sql
SELECT table_name,
       column_name,
       partition_name,
       segment_name,
       tablespace_name,
       securefile
FROM user_lob_partitions
ORDER BY table_name, column_name, partition_name;
~~~

Với subpartitioned table, xem các view LOB subpartition tương ứng.

### 14.4. Dung lượng segment

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       bytes,
       blocks
FROM user_segments
WHERE segment_type LIKE 'LOB%'
ORDER BY bytes DESC;
~~~

LOB segment có thể chiếm dung lượng lớn hơn phần table row/locator nhiều lần. Theo dõi tăng trưởng riêng thay vì chỉ xem dung lượng table segment.

### 14.5. Temporary LOB usage

Có thể kiểm tra temporary segment usage qua các dynamic performance views phù hợp với quyền và cấu hình database, ví dụ V$TEMPSEG_USAGE. Cần phân biệt temporary LOB usage với temporary tablespace dùng cho sort/hash.

## 15. Những giới hạn và điểm cần cân nhắc

### 15.1. SQL operations trên LOB không giống scalar

Không phải mọi phép toán SQL thông thường đều áp dụng trực tiếp lên LOB. Ví dụ, không thể coi CLOB/BLOB như VARCHAR2/RAW trong mọi biểu thức, GROUP BY, ORDER BY hoặc phép so sánh.

Dùng các hàm LOB được hỗ trợ như DBMS_LOB.COMPARE, DBMS_LOB.SUBSTR và DBMS_LOB.GETLENGTH khi phù hợp. Với tìm kiếm văn bản lớn, xem Oracle Text hoặc kiến trúc tìm kiếm chuyên dụng.

### 15.2. LOB locator có vòng đời

Locator cần còn hợp lệ trong session/transaction và theo API được dùng. Không lưu locator rồi sử dụng tùy tiện sau khi row bị xóa, session kết thúc hoặc locator scope hết hạn.

### 15.3. CLOB và character set

CLOB sử dụng database character set; NCLOB dùng national character set. Chuyển đổi giữa các character set có thể phát sinh conversion, mất ký tự nếu bộ ký tự đích không biểu diễn được nội dung.

Với nội dung đa ngôn ngữ, phải kiểm tra database character set, national character set, driver và cách bind dữ liệu.

### 15.4. BLOB là byte, không phải text

Không chuyển BLOB sang VARCHAR2 chỉ để thuận tiện. BLOB có thể chứa byte 0, dữ liệu nhị phân và encoding bất kỳ. Nếu BLOB là PDF/ZIP/image, ứng dụng phải xử lý theo định dạng tương ứng.

### 15.5. Backup và recovery

Internal LOB được database quản lý và nằm trong phạm vi backup/recovery của database theo cấu hình. BFILE nằm ngoài database nên phải backup filesystem/object store riêng.

NOLOGGING, encryption, keystore và standby có thể thay đổi yêu cầu backup/recovery. Hãy thử restore thực tế, không chỉ xác nhận job backup báo SUCCESS.
## 16. Chọn BasicFiles hay SecureFiles?

### 16.1. SecureFiles cho hệ thống mới

Ưu tiên SecureFiles khi database đáp ứng COMPATIBLE và tablespace ASSM, cần hiệu năng LOB hiện đại, có thể dùng compression/dedup/encryption khi cần, đã kiểm tra license và ứng dụng có thể được kiểm thử với SecureFiles.

### 16.2. Giữ BasicFiles cho hệ thống cũ khi có lý do

Giữ BasicFiles trong ngắn hạn khi ứng dụng hoặc môi trường có ràng buộc tương thích, tablespace hiện tại dùng MSSM và chưa có kế hoạch chuyển sang ASSM, chưa có cửa sổ chuyển đổi hoặc benchmark cho thấy không có lợi ích đủ lớn.

Đây nên là quyết định có quản lý và có kế hoạch hiện đại hóa nếu BasicFiles trở thành hạn chế.

### 16.3. Bảng quyết định nhanh

| Câu hỏi | Nếu có | Hướng lựa chọn |
| --- | --- | --- |
| Tạo hệ thống mới trên Oracle 19c? | Có | Bắt đầu đánh giá SecureFiles |
| Tablespace dùng ASSM? | Có | Đáp ứng điều kiện quan trọng cho SecureFiles |
| COMPATIBLE từ 11.1 trở lên? | Có | Đáp ứng điều kiện phiên bản cơ bản |
| Cần compression/deduplication/encryption? | Có | SecureFiles và kiểm tra license |
| Dữ liệu LOB nhỏ, đọc cùng row? | Có | Xem ENABLE STORAGE IN ROW và CACHE |
| LOB lớn, streaming, ít đọc? | Có | Xem DISABLE STORAGE IN ROW và NOCACHE |
| Hệ thống legacy đang ổn định? | Có | Giữ BasicFiles tạm thời nếu migration chưa có lợi ích rõ |
| Cần đọc file ngoài database? | Có | BFILE hoặc object/file storage, không phải BasicFiles/SecureFiles |

### 16.4. Quy trình ra quyết định

~~~text
Xác định loại dữ liệu LOB
          |
          v
Internal hay external?
    |             |
 Internal       External
    |             |
 BLOB/CLOB       BFILE / object storage
    |
    v
Oracle 19c, COMPATIBLE phù hợp?
    |
    v
Tablespace ASSM?
    |             |
   Có            Không
    |             |
Đánh giá        Chuyển ASSM hoặc
SecureFiles     xem BasicFiles
    |
    v
Chọn cache / compression / dedup / encryption
    |
    v
Kiểm tra license + benchmark + recovery
    |
    v
Chọn storage và triển khai có kiểm soát
~~~

## 17. Ví dụ lab: tạo và so sánh hai loại LOB

Các ví dụ dùng schema lab và tablespace ASSM có sẵn. Nếu không có tablespace LOB_TS, thay bằng tablespace ASSM được DBA cấp.

### 17.1. Tạo bảng BasicFiles

~~~sql
CREATE TABLE lob_basic_lab (
    id NUMBER PRIMARY KEY,
    payload BLOB
)
LOB (payload) STORE AS BASICFILE (
    TABLESPACE lob_ts
    ENABLE STORAGE IN ROW
    CHUNK 8192
    PCTVERSION 10
    NOCACHE
    LOGGING
);
~~~

### 17.2. Tạo bảng SecureFiles

~~~sql
CREATE TABLE lob_secure_lab (
    id NUMBER PRIMARY KEY,
    payload BLOB
)
LOB (payload) STORE AS SECUREFILE (
    TABLESPACE lob_ts
    DISABLE STORAGE IN ROW
    NOCACHE
    LOGGING
);
~~~

### 17.3. Kiểm tra loại storage

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       securefile,
       in_row,
       cache,
       logging
FROM user_lobs
WHERE table_name IN ('LOB_BASIC_LAB', 'LOB_SECURE_LAB')
ORDER BY table_name;
~~~

Kỳ vọng SECUREFILE = NO cho bảng BasicFiles và YES cho bảng SecureFiles.

### 17.4. Ghi nội dung BLOB bằng DBMS_LOB

~~~sql
DECLARE
    l_payload BLOB;
    l_bytes RAW(100) := UTL_RAW.CAST_TO_RAW('Sample binary payload');
BEGIN
    INSERT INTO lob_secure_lab(id, payload)
    VALUES (1, EMPTY_BLOB())
    RETURNING payload INTO l_payload;

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_payload,
        amount  => UTL_RAW.LENGTH(l_bytes),
        buffer  => l_bytes
    );

    COMMIT;
END;
/
~~~

### 17.5. Đọc độ dài và nội dung

~~~sql
SELECT id, DBMS_LOB.GETLENGTH(payload) AS payload_bytes
FROM lob_secure_lab;
~~~

### 17.6. So sánh segment size

~~~sql
SELECT segment_name,
       segment_type,
       bytes,
       blocks
FROM user_segments
WHERE segment_name IN (
    SELECT segment_name
    FROM user_lobs
    WHERE table_name IN ('LOB_BASIC_LAB', 'LOB_SECURE_LAB')
)
ORDER BY segment_name;
~~~

Với một row nhỏ, kết quả có thể không thể hiện khác biệt hiệu năng/dung lượng có ý nghĩa. Benchmark cần nhiều dữ liệu đại diện và workload thực tế.

### 17.7. Dọn lab

~~~sql
DROP TABLE lob_basic_lab PURGE;
DROP TABLE lob_secure_lab PURGE;
~~~

DDL có implicit commit. Chỉ chạy sau khi hoàn tất bài thực hành.

## 18. Những lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-43853 | Tạo SecureFiles trong tablespace không đáp ứng ASSM hoặc điều kiện cần | Kiểm tra SEGMENT_SPACE_MANAGEMENT và DB_SECUREFILE |
| ORA-43856 | Cấu hình SecureFiles/BasicFiles không phù hợp hoặc không được phép | Kiểm tra DB_SECUREFILE, storage clause và COMPATIBLE |
| ORA-22922 | Locator LOB không còn hợp lệ | Lấy lại locator từ row trong transaction phù hợp |
| ORA-22275 | LOB locator không hợp lệ hoặc không được khởi tạo đúng | Kiểm tra NULL/EMPTY locator và API DBMS_LOB |
| ORA-22288 | Lỗi file operation với BFILE | Kiểm tra DIRECTORY, file tồn tại và quyền OS |
| ORA-01031 | Thiếu quyền trên bảng, directory hoặc package | Cấp quyền tối thiểu phù hợp |
| Temporary tablespace tăng bất thường | Temporary LOB không được giải phóng hoặc xử lý quá nhiều LOB lớn | Kiểm tra vòng đời LOB và FREETEMPORARY |
| SecureFiles không tiết kiệm dung lượng | Dữ liệu đã nén hoặc ít trùng lặp | Đo compression/dedup benefit trước khi bật |
| LOB đọc chậm | CACHE/NOCACHE không phù hợp, storage I/O hoặc truy cập từng phần kém hiệu quả | Benchmark cache mode, streaming và storage |
| MOVE LOB thiếu dung lượng | Cần không gian cho segment đích trong quá trình chuyển | Dự trù tablespace, kiểm tra segment và kế hoạch migration |
| Standby không phục hồi được dữ liệu NOLOGGING | Thao tác giảm redo và chưa có backup phù hợp | Kiểm tra FORCE LOGGING, backup và Data Guard policy |
| Không đọc được LOB sau restore | Thiếu keystore hoặc external BFILE content | Khôi phục keystore và file ngoài database |

## 19. Checklist trước khi chọn hoặc chuyển LOB storage

1. **Loại dữ liệu là gì?** BLOB, CLOB, NCLOB hay BFILE.
2. **LOB internal hay external?** BFILE không dùng SecureFiles/BasicFiles.
3. **Kích thước phân bố ra sao?** Trung bình, p95, p99 và maximum.
4. **Tỷ lệ đọc/ghi thế nào?** Đọc toàn bộ, đọc một phần, append hay random update.
5. **Có nhiều LOB nhỏ không?** Đánh giá ENABLE STORAGE IN ROW.
6. **LOB lớn và ít đọc không?** Đánh giá DISABLE STORAGE IN ROW và NOCACHE.
7. **Tablespace có ASSM không?** Điều kiện cần cho SecureFiles.
8. **COMPATIBLE có phù hợp không?** Không tự ý nâng COMPATIBLE.
9. **DB_SECUREFILE có cho phép không?** Kiểm tra cấu hình trước khi tạo.
10. **Có cần compression không?** Đo tỷ lệ nén và CPU overhead.
11. **Có dữ liệu trùng lặp không?** Dedup chỉ có lợi khi duplicate content đáng kể.
12. **Có cần encryption không?** Chuẩn bị TDE keystore, key backup và license.
13. **LOGGING/NOLOGGING phù hợp recovery không?** Xem backup, standby và FORCE LOGGING.
14. **Temporary LOB có được giải phóng không?** Tránh tăng temporary tablespace.
15. **Có kế hoạch chuyển đổi không?** Đánh giá MOVE LOB/DBMS_REDEFINITION, downtime và rollback.
16. **Đã kiểm tra dictionary chưa?** Xác nhận SECUREFILE, cache, logging, compression, dedup và encryption.
17. **Đã benchmark dữ liệu thật chưa?** Đo throughput, latency, CPU, I/O và storage.
18. **BFILE có backup riêng không?** Database backup không thay thế backup filesystem.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** BLOB, CLOB, NCLOB và BFILE khác nhau thế nào?

**Câu 2.** LOB locator là gì? Nó có phải nội dung LOB không?

**Câu 3.** ENABLE STORAGE IN ROW và DISABLE STORAGE IN ROW khác nhau thế nào?

**Câu 4.** BasicFiles và SecureFiles khác nhau ở kiến trúc và tính năng nào?

**Câu 5.** Vì sao SecureFiles yêu cầu ASSM?

**Câu 6.** COMPATIBLE cần đáp ứng mức nào để dùng SecureFiles?

**Câu 7.** DB_SECUREFILE có vai trò gì?

**Câu 8.** CHUNK và PCTVERSION gắn với cơ chế nào?

**Câu 9.** SecureFiles compression và deduplication giúp gì? Có chi phí nào?

**Câu 10.** CACHE, CACHE READS và NOCACHE khác nhau thế nào?

**Câu 11.** Vì sao NOLOGGING cần được đánh giá cùng backup và Data Guard?

**Câu 12.** BFILE có được backup cùng datafile không?

**Câu 13.** EMPTY_CLOB khác NULL thế nào?

**Câu 14.** Vì sao cần FREETEMPORARY?

**Câu 15.** Có thể chuyển BasicFiles sang SecureFiles bằng cách nào?

**Câu 16.** Vì sao không nên bật compression/dedup/encryption trên mọi LOB column?

**Câu 17.** Làm sao xác nhận LOB column thực sự là SecureFiles?

**Câu 18.** Khi nào nên giữ BasicFiles trong hệ thống cũ?

<details>
<summary>Gợi ý đáp án</summary>

1. BLOB là byte; CLOB là ký tự theo database character set; NCLOB theo national character set; BFILE là locator tới file ngoài database.
2. Locator là tham chiếu để truy cập LOB; không nhất thiết chứa toàn bộ nội dung.
3. ENABLE cho phép LOB nhỏ inline; DISABLE lưu ngoài row.
4. SecureFiles là kiến trúc mới hơn, hỗ trợ compression, deduplication, encryption và tối ưu LOB workload; BasicFiles là cơ chế truyền thống.
5. SecureFiles dùng cơ chế quản lý segment space cần ASSM.
6. COMPATIBLE từ 11.1.0 trở lên.
7. Điều khiển việc tạo SecureFiles theo cấu hình database.
8. CHUNK và PCTVERSION là các tham số BasicFiles; SecureFiles dùng cơ chế khác, gồm RETENTION.
9. Compression giảm dung lượng nếu dữ liệu nén được; dedup tránh lưu nhiều bản giống nhau; cả hai có thể tăng CPU và cần license phù hợp.
10. CACHE cache LOB data; CACHE READS cache khi đọc; NOCACHE không cache LOB data theo cách thông thường.
11. NOLOGGING có thể làm giảm redo và ảnh hưởng media recovery/standby; cần backup phù hợp.
12. Không. BFILE nằm trên filesystem ngoài database và cần backup riêng.
13. EMPTY_CLOB là empty LOB locator; NULL là không có giá trị locator.
14. Để giải phóng temporary LOB và tránh chiếm temporary tablespace/session resources.
15. Có thể dùng ALTER TABLE MOVE LOB sang STORE AS SECUREFILE hoặc chiến lược redefinition/copy phù hợp.
16. Vì CPU, I/O, latency, license và lợi ích phụ thuộc dữ liệu/workload.
17. Xem USER_LOBS.SECUREFILE hoặc ALL_LOBS/DBA_LOBS.
18. Khi có ràng buộc tương thích, tablespace/kiến trúc chưa sẵn sàng hoặc chưa có lợi ích đủ lớn để chuyển đổi.

</details>

## 21. Tài liệu Oracle chính thức

1. [Oracle Database SecureFiles and Large Objects Developer's Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/): kiến trúc LOB, SecureFiles, BasicFiles, locator và thao tác LOB.
2. [Oracle Database 19c SecureFiles and Large Objects Developer's Guide — SecureFiles](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/using-oracle-securefiles.html): điều kiện, tính năng và cách tạo SecureFiles.
3. [Oracle Database 19c SecureFiles and Large Objects Developer's Guide — BasicFiles](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/basicfiles.html): kiến trúc và tham số BasicFiles.
4. [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): LOB storage clauses và SecureFiles options.
5. [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): MOVE LOB và thay đổi LOB storage.
6. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_LOB](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_LOB.html): đọc, ghi, so sánh, temporary LOB và BFILE APIs.
7. [Oracle Database 19c Reference — USER_LOBS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_LOBS.html): metadata LOB columns trong schema hiện tại.
8. [Oracle Database 19c Reference — DB_SECUREFILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DB_SECUREFILE.html): tham số điều khiển SecureFiles.
9. [Oracle Database 19c Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html): kiểm tra điều kiện license cho compression, deduplication và encryption.

**Nguyên tắc cần nhớ:** SecureFiles là lựa chọn nên đánh giá đầu tiên cho internal LOB trong hệ thống Oracle hiện đại, nhưng phải đáp ứng COMPATIBLE và ASSM, đồng thời kiểm tra DB_SECUREFILE. BasicFiles vẫn có thể tồn tại vì tương thích hệ thống cũ. Chọn CACHE, in-row, compression, deduplication, encryption và logging theo kích thước dữ liệu, pattern đọc/ghi, yêu cầu bảo mật, license và recovery. BFILE là file ngoài database; temporary LOB cần cleanup; mọi chuyển đổi storage phải có benchmark, dung lượng dự phòng, backup và kế hoạch rollback.
