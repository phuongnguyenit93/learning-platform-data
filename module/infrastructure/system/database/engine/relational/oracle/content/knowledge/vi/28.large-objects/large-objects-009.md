# Giao dịch, khóa và tính nhất quán khi cập nhật LOB

LOB (Large Object) là kiểu dữ liệu Oracle dùng để lưu nội dung lớn như văn bản dài, JSON/XML lớn, ảnh, âm thanh, video, tài liệu hoặc dữ liệu nhị phân. Các kiểu LOB chính gồm CLOB, NCLOB, BLOB và BFILE. Vì LOB có thể rất lớn và thường được lưu ngoài phần row data thông thường, việc đọc/ghi LOB có một số đặc điểm riêng về locator, transaction, khóa, consistent read và quản lý phiên bản dữ liệu.

Khi cập nhật LOB, cần hiểu hai lớp trạng thái: hàng của bảng chứa LOB locator và nội dung LOB được quản lý bởi Oracle. Với LOB persistent, thao tác ghi vẫn thuộc transaction của session; row lock thường là ranh giới đồng thời quan trọng. Nếu nhiều ứng dụng cùng sửa một tài liệu, chỉ dựa vào việc ghi từng chunk là chưa đủ để ngăn ghi đè dữ liệu cũ. Cần chọn chiến lược khóa bi quan hoặc kiểm soát phiên bản lạc quan, xác định ranh giới commit và cách xử lý upload dở dang.

Sau bài học, bạn có thể:

- Phân biệt CLOB, NCLOB, BLOB, BFILE và persistent/temporary LOB.
- Hiểu LOB locator tham chiếu nội dung LOB như thế nào.
- Giải thích transaction, COMMIT, ROLLBACK và read consistency khi cập nhật LOB.
- Khóa hàng chứa LOB bằng SELECT ... FOR UPDATE trước khi dùng DBMS_LOB sửa LOB persistent.
- Hiểu row-level locking, thời gian giữ khóa và contention giữa nhiều session.
- Tránh lost update khi hai người cùng chỉnh sửa một tài liệu.
- Dùng version column để triển khai optimistic locking.
- Ghi LOB theo từng phần bằng DBMS_LOB.WRITE, WRITEAPPEND, APPEND và TRIM.
- Phân biệt LOB chunk size với đơn vị khóa hoặc đơn vị transaction.
- Hiểu consistent read, LOB retention và lỗi snapshot too old.
- Thiết kế upload lớn bằng staging, temporary LOB và transaction ngắn.
- Chẩn đoán các lỗi như ORA-22920, ORA-22924, ORA-22275, ORA-00054 và ORA-00060.

> Bài học tập trung vào LOB được lưu trong Oracle Database. BFILE là tham chiếu tới file bên ngoài database và có semantics khác. Cú pháp storage, SecureFiles/BasicFiles và một số tính năng có thể phụ thuộc phiên bản Oracle; hãy xác nhận theo release đang sử dụng.

## 1. Các kiểu LOB và cách Oracle quản lý

### 1.1. CLOB

CLOB (Character Large Object) lưu dữ liệu ký tự theo character set database. Thường dùng cho nội dung văn bản lớn, nội dung HTML, XML, JSON dạng text, log hoặc tài liệu dài.

Ví dụ:

```sql
CREATE TABLE lab_documents (
    document_id NUMBER PRIMARY KEY,
    document_name VARCHAR2(200),
    document_body CLOB,
    updated_at TIMESTAMP
);
```

### 1.2. NCLOB

NCLOB lưu dữ liệu ký tự theo national character set của database. Dùng khi ứng dụng cần semantics của national character set. CLOB và NCLOB đều là character LOB; khi dùng DBMS_LOB, offset/amount có semantics theo ký tự đối với CLOB/NCLOB.

### 1.3. BLOB

BLOB (Binary Large Object) lưu dữ liệu nhị phân như ảnh, PDF, file Office, âm thanh hoặc video.

Ví dụ:

```sql
CREATE TABLE lab_attachments (
    attachment_id NUMBER PRIMARY KEY,
    file_name VARCHAR2(255),
    mime_type VARCHAR2(100),
    file_content BLOB,
    created_at TIMESTAMP
);
```

Với BLOB, offset và amount trong DBMS_LOB được tính theo byte.

### 1.4. BFILE

BFILE là locator tham chiếu tới file nhị phân nằm trong filesystem mà Oracle truy cập thông qua DIRECTORY object. Nội dung file không được lưu trong segment LOB của bảng và database không quản lý nội dung file theo transaction như BLOB/CLOB.

Đặc điểm:

- BFILE là read-only qua giao diện LOB của Oracle.
- Nội dung nằm bên ngoài database.
- Việc thay đổi hoặc xóa file do hệ điều hành/quy trình bên ngoài quản lý.
- COMMIT/ROLLBACK trong Oracle không hoàn tác việc sửa file bên ngoài.
- File phải được truy cập qua DIRECTORY object và quyền phù hợp.

Nếu cần nội dung được bảo vệ bởi transaction và backup/recovery của database, cân nhắc lưu vào BLOB thay vì chỉ tham chiếu BFILE.

### 1.5. Persistent LOB và temporary LOB

| Loại | Nơi quản lý | Vòng đời |
| --- | --- | --- |
| Persistent LOB | LOB column của một hàng trong bảng | Tồn tại cùng dữ liệu bảng và transaction |
| Temporary LOB | Temporary LOB storage do Oracle quản lý | Theo thời hạn CALL hoặc SESSION, tùy cách tạo |
| BFILE | File bên ngoài database, locator lưu trong hàng | Vòng đời file bên ngoài; không thuộc transaction nội dung file |

Persistent LOB là dữ liệu ứng dụng lưu lâu dài. Temporary LOB thường dùng để ghép chuỗi, xử lý nội dung trung gian hoặc tạo payload trước khi ghi vào cột LOB.

## 2. LOB locator và nội dung LOB

### 2.1. Locator là gì?

Khi SELECT một cột LOB vào biến PL/SQL, biến thường giữ một LOB locator. Locator là tham chiếu để truy cập nội dung LOB; không nên hiểu nó là toàn bộ nội dung lớn được sao chép vào biến ngay lập tức.

Ví dụ:

```sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 10;

    DBMS_OUTPUT.PUT_LINE(
        'Length = ' || DBMS_LOB.GETLENGTH(l_body)
    );
END;
/
```

Biến l_body giữ locator tới LOB tương ứng. Các thao tác DBMS_LOB có thể dùng locator để đọc hoặc sửa nội dung theo giới hạn quyền và locking.

### 2.2. Locator không phải bản sao độc lập

Một locator persistent gắn với LOB của hàng trong database. Nếu hàng hoặc LOB bị thay đổi/xóa, locator cũ có thể không còn hợp lệ trong ngữ cảnh sử dụng. Không lưu locator trong bộ nhớ ứng dụng rồi giả định nó tồn tại mãi sau commit, session end hoặc thay đổi dữ liệu.

Đối với ứng dụng client, driver thường cung cấp LOB locator/streaming handle có vòng đời gắn với connection và result set. Phải đọc/ghi theo API driver và đóng tài nguyên đúng cách.

### 2.3. LOB rỗng và NULL

LOB column có thể là NULL hoặc có locator rỗng. Oracle cung cấp EMPTY_CLOB() và EMPTY_BLOB() để khởi tạo LOB rỗng nhưng không NULL:

```sql
INSERT INTO lab_documents (
    document_id,
    document_name,
    document_body,
    updated_at
)
VALUES (
    10,
    'Draft',
    EMPTY_CLOB(),
    SYSTIMESTAMP
);
```

NULL có nghĩa không có giá trị LOB; EMPTY_CLOB() biểu diễn LOB rỗng. Một số thao tác DBMS_LOB yêu cầu locator hợp lệ, vì vậy cần phân biệt hai trường hợp.

### 2.4. LOB length và offset

DBMS_LOB.GETLENGTH trả độ dài LOB:

```sql
SELECT
    document_id,
    DBMS_LOB.GETLENGTH(document_body) AS body_length
FROM lab_documents;
```

Đối với CLOB/NCLOB, length và offset dùng đơn vị ký tự theo semantics LOB. Đối với BLOB, length và offset dùng byte. Không dùng LENGTHB hoặc byte offset cho CLOB một cách tùy tiện; cần đồng nhất đơn vị với API đang gọi.

## 3. Transaction khi cập nhật persistent LOB

### 3.1. LOB persistent thuộc transaction

Khi dùng SQL UPDATE hoặc DBMS_LOB để sửa persistent LOB, thay đổi được quản lý bởi transaction hiện tại. COMMIT làm thay đổi được commit; ROLLBACK hủy các thay đổi chưa commit theo transaction.

Ví dụ:

```sql
UPDATE lab_documents
SET document_body = TO_CLOB('New document text'),
    updated_at = SYSTIMESTAMP
WHERE document_id = 10;

-- Kiểm tra trong cùng transaction.
SELECT DBMS_LOB.GETLENGTH(document_body)
FROM lab_documents
WHERE document_id = 10;

-- Caller quyết định:
COMMIT;
-- Hoặc ROLLBACK;
```

Không có implicit commit chỉ vì LOB lớn hoặc vì gọi DBMS_LOB.WRITE. LOB persistent vẫn tuân theo transaction của database.

### 3.2. Atomicity của một câu DML

Một câu UPDATE gán LOB là một statement DML:

```sql
UPDATE lab_documents
SET document_body = :new_document_body
WHERE document_id = :document_id;
```

Nếu statement thất bại, Oracle rollback tác động của statement đó. Các DML thành công trước đó trong cùng transaction vẫn còn pending cho tới khi caller commit hoặc rollback toàn transaction.

### 3.3. Nhiều lần ghi bằng DBMS_LOB trong một transaction

Nếu một transaction gọi DBMS_LOB.WRITE nhiều lần vào cùng LOB, các lần ghi thuộc transaction hiện tại. Có thể commit sau khi hoàn tất tất cả chunk để tài liệu chỉ được công bố ở trạng thái hoàn chỉnh.

Nếu commit sau mỗi chunk, ứng dụng tạo ra nhiều trạng thái đã commit một phần. Khi đó cần thiết kế checkpoint, trạng thái upload, checksum và cơ chế resume; nếu không, người đọc có thể thấy tài liệu chưa hoàn tất.

### 3.4. Transaction dài và LOB lớn

Giữ transaction mở trong toàn bộ thời gian upload một file rất lớn có thể:

- Giữ row lock lâu.
- Làm các session cập nhật cùng hàng phải chờ.
- Giữ undo/version cần thiết lâu hơn.
- Tăng nguy cơ contention và khó rollback.
- Kéo dài thời gian phục hồi nếu client mất kết nối.

Nếu upload mất nhiều phút, cân nhắc ghi vào staging hoặc temporary LOB trước, xác thực nội dung, rồi dùng một transaction ngắn để thay thế locator hoặc chuyển dữ liệu sang hàng chính.

## 4. Khóa hàng chứa LOB

### 4.1. Vì sao cần SELECT FOR UPDATE?

Khi dùng DBMS_LOB để sửa một persistent LOB, cần khóa hàng chứa LOB bằng SELECT ... FOR UPDATE trước khi ghi. Điều này đảm bảo session có quyền sửa LOB của hàng và ngăn session khác đồng thời sửa cùng hàng trong khi transaction đang giữ khóa.

Ví dụ:

```sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 10
    FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(' - revised'),
        ' - revised'
    );

    COMMIT;
END;
/
```

Đối với CLOB, amount là số ký tự. Đối với BLOB, amount là số byte.

Nếu không khóa hàng trước khi sửa persistent LOB qua DBMS_LOB, có thể gặp lỗi:

```text
ORA-22920: row containing the LOB value is not locked
```

### 4.2. SQL UPDATE tự lấy khóa hàng

Nếu cập nhật LOB bằng một câu SQL UPDATE, Oracle tự lấy khóa DML cần thiết trên hàng:

```sql
UPDATE lab_documents
SET document_body = :new_body,
    updated_at = SYSTIMESTAMP
WHERE document_id = :document_id;
```

Không cần SELECT FOR UPDATE riêng trước một UPDATE thông thường chỉ để Oracle khóa hàng; câu UPDATE tự làm việc đó. SELECT FOR UPDATE cần thiết khi ứng dụng muốn lấy locator rồi gọi DBMS_LOB để sửa theo từng phần.

### 4.3. Khóa theo hàng, không phải theo chunk

Không nên hiểu CHUNK size của LOB là đơn vị khóa. Với persistent LOB, row lock trên hàng chứa LOB là ranh giới đồng thời chính. Hai session sửa hai LOB column khác nhau nhưng cùng một hàng vẫn có thể tranh chấp khóa hàng đó.

Ngược lại, hai session sửa LOB ở hai hàng khác nhau thường có thể tiến hành độc lập ở mức row lock, dù vẫn có thể gặp tranh chấp tài nguyên khác như I/O, buffer, LOB segment hoặc index.

### 4.4. Khóa được giữ tới khi kết thúc transaction

Sau SELECT FOR UPDATE hoặc UPDATE, row lock được giữ cho tới COMMIT hoặc ROLLBACK. Đóng cursor hoặc kết thúc block PL/SQL không tự giải phóng row lock.

Do đó:

- Không giữ transaction mở khi người dùng đang đọc/sửa nội dung trên giao diện.
- Không chờ upload từ client chậm sau khi đã khóa hàng chính.
- Không gọi dịch vụ ngoài khi đang giữ row lock.
- Commit/rollback ở ranh giới nghiệp vụ đã xác định.

## 5. SELECT FOR UPDATE: WAIT, NOWAIT và SKIP LOCKED

### 5.1. Mặc định WAIT

Nếu một session muốn khóa hàng đang bị session khác khóa, SELECT FOR UPDATE mặc định có thể chờ cho tới khi khóa được giải phóng:

```sql
SELECT document_body
INTO l_body
FROM lab_documents
WHERE document_id = 10
FOR UPDATE;
```

Session thứ hai chờ cho tới khi session đầu COMMIT hoặc ROLLBACK. Sau đó Oracle tiếp tục kiểm tra và khóa hàng theo semantics của câu SELECT.

### 5.2. NOWAIT

NOWAIT yêu cầu trả lỗi ngay nếu không lấy được khóa:

```sql
SELECT document_body
INTO l_body
FROM lab_documents
WHERE document_id = 10
FOR UPDATE NOWAIT;
```

Nếu hàng đang bị khóa, thường nhận ORA-00054. Ứng dụng có thể báo tài liệu đang được sửa hoặc cho người dùng thử lại.

### 5.3. WAIT n

WAIT n cho phép chờ tối đa số giây được chỉ định:

```sql
SELECT document_body
INTO l_body
FROM lab_documents
WHERE document_id = 10
FOR UPDATE WAIT 5;
```

Nếu không lấy được khóa trong thời gian chờ, Oracle phát sinh lỗi timeout tương ứng, thường là ORA-30006. Chọn timeout theo SLA và trải nghiệm ứng dụng.

### 5.4. SKIP LOCKED

SKIP LOCKED bỏ qua hàng đang bị khóa và hữu ích cho queue worker xử lý nhiều hàng độc lập:

```sql
SELECT document_id
FROM lab_document_jobs
WHERE job_status = 'READY'
FOR UPDATE SKIP LOCKED;
```

Trong thực tế thường kết hợp cursor/ROWNUM hoặc FETCH FIRST để lấy một batch. SKIP LOCKED không phù hợp khi người dùng yêu cầu một document ID cụ thể và cần biết nó có đang bị sửa hay không; bỏ qua hàng có thể bị hiểu nhầm là hàng không tồn tại.

### 5.5. OF column

Trong query join nhiều bảng, FOR UPDATE OF có thể chỉ rõ cột thuộc bảng cần khóa:

```sql
SELECT d.document_id, d.document_body
FROM lab_documents d
JOIN lab_document_types t
  ON t.type_id = d.type_id
WHERE d.document_id = 10
FOR UPDATE OF d.document_body;
```

OF xác định bảng/hàng cần khóa theo cột được nêu; nó không biến LOB thành khóa riêng theo chunk. Cú pháp FOR UPDATE có một số giới hạn với DISTINCT, GROUP BY, set operators và các view phức tạp; thiết kế query khóa đơn giản và kiểm tra trên release đang dùng.

## 6. Lost update khi nhiều người cùng sửa một LOB

### 6.1. Tình huống

Hai người dùng mở cùng tài liệu ở version 7:

1. Session A đọc nội dung version 7.
2. Session B cũng đọc nội dung version 7.
3. A sửa phần đầu và lưu version mới.
4. B sửa phần cuối dựa trên bản cũ rồi ghi toàn bộ nội dung lên hàng.

Nếu B không kiểm tra version hiện tại, nội dung A vừa lưu có thể bị ghi đè. Đây là lost update.

```text
Thời gian       Session A                    Session B
---------       ---------                    ---------
T1              Đọc document version 7       Đọc document version 7
T2              Sửa nội dung A               Sửa nội dung B
T3              Ghi toàn bộ nội dung A
T4                                           Ghi toàn bộ nội dung B
T5              Commit                       Commit

Kết quả cuối: nội dung B có thể ghi đè thay đổi của A.
```

Row lock chỉ bảo vệ các lần ghi đồng thời trong khoảng transaction giữ khóa. Nó không tự phát hiện rằng B đang gửi lại một bản nội dung cũ đã được đọc trước đó.

### 6.2. Pessimistic locking

Khóa bi quan lấy row lock trước khi đọc/ghi để các session khác phải chờ hoặc nhận lỗi:

```sql
SELECT document_body
INTO l_body
FROM lab_documents
WHERE document_id = :document_id
FOR UPDATE;
```

Ứng dụng lấy khóa trước khi thực hiện thay đổi và giữ khóa đến COMMIT/ROLLBACK. Cách này phù hợp khi:

- Tài liệu cần được chỉnh sửa tuần tự.
- Thời gian sửa ngắn, có thể giữ transaction ngắn.
- Xung đột thường xuyên và cần tránh nhiều lần retry.
- Ứng dụng kiểm soát được session và transaction.

Không khóa hàng trong suốt thời gian người dùng mở form hoặc chỉnh sửa offline. Người dùng có thể mất hàng phút; row lock lâu sẽ làm các session khác chờ và giữ transaction quá lâu.

### 6.3. Optimistic locking với version column

Một cách phổ biến là thêm VERSION_NO:

```sql
ALTER TABLE lab_documents
ADD version_no NUMBER DEFAULT 1 NOT NULL;
```

Khi đọc tài liệu, ứng dụng lấy cả nội dung và version:

```sql
SELECT document_body, version_no
FROM lab_documents
WHERE document_id = :document_id;
```

Khi lưu, chỉ cập nhật nếu version vẫn bằng giá trị đã đọc:

```sql
UPDATE lab_documents
SET document_body = :new_body,
    version_no = version_no + 1,
    updated_at = SYSTIMESTAMP
WHERE document_id = :document_id
  AND version_no = :expected_version;
```

Trong PL/SQL:

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_documents
    SET document_body = :new_body,
        version_no = version_no + 1,
        updated_at = SYSTIMESTAMP
    WHERE document_id = :document_id
      AND version_no = :expected_version;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20031,
            'Document changed since it was read. Reload before saving.'
        );
    END IF;
END;
/
```

Nếu row count bằng 1, bản cập nhật đã thắng và version được tăng. Nếu bằng 0, document không tồn tại hoặc version đã đổi; ứng dụng cần đọc lại và xử lý conflict. Điều kiện VERSION_NO trong WHERE mới là cơ chế phát hiện lost update; chỉ đọc SQL%ROWCOUNT sau UPDATE không tự tạo concurrency control.

### 6.4. So sánh pessimistic và optimistic

| Tiêu chí | Pessimistic lock | Optimistic version |
| --- | --- | --- |
| Thời điểm phát hiện xung đột | Trước hoặc trong lúc chờ khóa | Khi ghi và kiểm tra version |
| Khóa trong lúc người dùng sửa | Không nên giữ qua thời gian tương tác dài | Không cần giữ row lock trong thời gian sửa offline |
| Khi có nhiều xung đột | Các session chờ nhau | Một số lần lưu thất bại và phải retry/merge |
| Phù hợp | Sửa ngắn, cần tuần tự hóa | Đọc nhiều, ghi ít, thời gian chỉnh sửa dài |
| Cơ chế | SELECT FOR UPDATE | UPDATE ... WHERE version_no = expected |

Có thể kết hợp cả hai: kiểm tra version để phát hiện bản cũ, rồi lấy row lock trong transaction ngắn khi ghi.

### 6.5. Vì sao không nên chỉ dựa vào ORA_ROWSCN?

ORA_ROWSCN có thể hữu ích để quan sát SCN liên quan đến thay đổi hàng, nhưng độ chính xác phụ thuộc ROWDEPENDENCIES và một số đặc điểm lưu trữ; giá trị không phải một version token nghiệp vụ đơn giản cho mọi ứng dụng. Dùng cột VERSION_NO do ứng dụng tăng trong cùng UPDATE thường rõ ràng và dễ kiểm soát hơn.

## 7. Ghi LOB theo từng phần bằng DBMS_LOB

### 7.1. DBMS_LOB.WRITE

WRITE ghi dữ liệu vào LOB tại offset chỉ định:

```sql
DBMS_LOB.WRITE(
    lob_loc => l_body,
    amount  => 6,
    offset  => 1,
    buffer  => 'Oracle'
);
```

Với CLOB, amount và offset có semantics theo ký tự; với BLOB, theo byte. WRITE ghi đè tại vị trí chỉ định và có thể không thay thế toàn bộ phần còn lại của LOB. Nếu cần thay toàn bộ nội dung, có thể dùng SQL UPDATE gán LOB mới, hoặc TRIM/WRITE theo trình tự rõ ràng.

### 7.2. DBMS_LOB.WRITEAPPEND

WRITEAPPEND nối dữ liệu vào cuối LOB:

```sql
DBMS_LOB.WRITEAPPEND(
    lob_loc => l_body,
    amount  => LENGTH(l_piece),
    buffer  => l_piece
);
```

Ví dụ đầy đủ cho CLOB:

```sql
DECLARE
    l_body CLOB;
    l_piece VARCHAR2(1000) := 'More content';
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 10
    FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(l_piece),
        l_piece
    );

    COMMIT;
END;
/
```

Nếu document_body là NULL, hãy khởi tạo LOB hợp lệ trước khi ghi, ví dụ UPDATE cột thành EMPTY_CLOB() RETURNING locator INTO biến trong cùng transaction, hoặc dùng câu lệnh phù hợp với trường hợp.

### 7.3. DBMS_LOB.APPEND

APPEND nối toàn bộ nội dung từ source LOB vào destination LOB:

```sql
DBMS_LOB.APPEND(
    dest_lob => l_destination,
    src_lob  => l_source
);
```

Source và destination cần là locator hợp lệ và tương thích loại LOB. Với persistent destination, khóa hàng chứa destination trước khi sửa.

### 7.4. DBMS_LOB.TRIM

TRIM rút ngắn LOB tới độ dài được chỉ định:

```sql
DBMS_LOB.TRIM(
    lob_loc => l_body,
    newlen  => 100
);
```

TRIM loại bỏ phần nội dung từ độ dài mới trở đi. Đây là thay đổi dữ liệu persistent và thuộc transaction; khóa hàng trước khi dùng trên persistent LOB.

### 7.5. DBMS_LOB.ERASE

ERASE xóa một đoạn nội dung theo offset/amount mà không nhất thiết rút ngắn LOB. Với BLOB, vùng bị xóa được thay bằng byte zero; với CLOB/NCLOB, bằng khoảng trắng theo semantics LOB. Nếu mục tiêu là xóa phần cuối, TRIM thường phù hợp hơn.

### 7.6. DBMS_LOB.COPY

COPY sao chép một đoạn hoặc toàn bộ source LOB sang destination LOB:

```sql
DBMS_LOB.COPY(
    dest_lob    => l_destination,
    src_lob     => l_source,
    amount      => DBMS_LOB.GETLENGTH(l_source),
    dest_offset => 1,
    src_offset  => 1
);
```

Đơn vị amount/offset theo loại LOB. Destination persistent cần row lock. Với LOB rất lớn, xem xét memory, redo/undo, thời gian giữ khóa và phương án copy trong staging.

### 7.7. Ghi nhiều chunk

Ví dụ ghi CLOB theo từng đoạn trong cùng transaction:

```sql
DECLARE
    l_body CLOB;
    l_piece VARCHAR2(4000);
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 10
    FOR UPDATE;

    l_piece := 'Part one. ';
    DBMS_LOB.WRITEAPPEND(l_body, LENGTH(l_piece), l_piece);

    l_piece := 'Part two. ';
    DBMS_LOB.WRITEAPPEND(l_body, LENGTH(l_piece), l_piece);

    l_piece := 'Part three.';
    DBMS_LOB.WRITEAPPEND(l_body, LENGTH(l_piece), l_piece);

    COMMIT;
END;
/
```

Các chunk đều được commit cùng nhau ở cuối transaction. Nếu xảy ra lỗi trước COMMIT và exception handler rollback transaction, nội dung persistent LOB chưa commit sẽ bị hủy theo transaction.

## 8. CHUNK size và hiệu năng

### 8.1. CHUNK là gì?

LOB CHUNK là đơn vị cấp phát/đọc ghi nội bộ của LOB storage. Có thể truy vấn kích thước chunk bằng:

```sql
SELECT DBMS_LOB.GETCHUNKSIZE(document_body)
FROM lab_documents
WHERE document_id = 10;
```

Chunk size có thể ảnh hưởng hiệu năng khi đọc/ghi theo từng phần và cách Oracle quản lý LOB segment.

### 8.2. CHUNK không phải đơn vị khóa

Không suy luận rằng hai session ghi hai chunk khác nhau của cùng một persistent LOB sẽ không block nhau. Row lock trên hàng chứa LOB là ranh giới đồng thời quan trọng. CHUNK mô tả tổ chức storage/I/O, không phải cơ chế chia quyền ghi độc lập theo đoạn.

### 8.3. Chọn kích thước buffer

Khi streaming từ ứng dụng:

- Dùng buffer có kích thước hợp lý, tránh nạp toàn bộ file lớn vào RAM.
- Với BLOB, tính amount theo byte.
- Với CLOB/NCLOB, tính amount theo ký tự và chú ý character set/multibyte.
- Không cắt giữa một chuỗi ký tự theo byte nếu API yêu cầu ký tự.
- Đo hiệu năng với kích thước chunk thực tế.

Không có một buffer size tối ưu cho mọi LOB. Phụ thuộc kích thước file, network, driver, storage, memory và latency.

### 8.4. CACHE, NOCACHE và LOGGING

LOB storage có các thuộc tính như CACHE/NOCACHE/CACHE READS và LOGGING/NOLOGGING tùy loại LOB và phiên bản. Chúng ảnh hưởng cách dùng buffer cache và redo/recovery characteristics; chúng không thay thế row lock hoặc transaction isolation.

- CACHE có thể hữu ích khi LOB thường xuyên được đọc.
- NOCACHE có thể phù hợp với LOB lớn, ít được đọc lại.
- CACHE READS có thể phù hợp với workload đọc nhưng ít ghi.
- NOLOGGING có thể ảnh hưởng khả năng media recovery/standby tùy operation và cấu hình.

Không chọn NOLOGGING chỉ để tăng tốc mà bỏ qua yêu cầu backup, Data Guard và recoverability. Việc chọn storage attributes cần dựa trên workload và chính sách DBA.

## 9. Read consistency khi đọc LOB

### 9.1. Oracle MVCC

Oracle sử dụng cơ chế multi-version concurrency control (MVCC) để cung cấp read consistency. Một câu SELECT đọc dữ liệu theo một SCN nhất quán; nếu session khác đang cập nhật một hàng chưa commit, reader thông thường vẫn có thể đọc phiên bản đã commit trước đó thay vì phải chờ writer.

Đối với LOB persistent, nội dung LOB cũng cần được đọc theo phiên bản nhất quán của statement. Oracle quản lý các phiên bản cần thiết thông qua cơ chế undo/LOB versioning và cấu hình lưu giữ phiên bản LOB.

### 9.2. Reader và writer

Trong tình huống phổ biến:

- Session A cập nhật LOB và giữ transaction chưa commit.
- Session B chạy SELECT thông thường.
- B thường đọc phiên bản đã commit trước đó, không nhìn thấy nội dung A chưa commit.
- Sau khi A COMMIT, câu SELECT mới của B có thể đọc phiên bản mới.
- Nếu B dùng SELECT FOR UPDATE, B cần lấy row lock và có thể chờ A.

Đây là khác biệt giữa đọc nhất quán và yêu cầu khóa để sửa.

### 9.3. Một statement nhìn thấy một snapshot

Nếu query chạy trong lúc một session khác cập nhật LOB, Oracle cố gắng trả kết quả theo snapshot nhất quán tại thời điểm statement bắt đầu. Không trộn tùy tiện một phần dữ liệu cũ và một phần dữ liệu mới trong cùng phép đọc logic.

Với transaction isolation SERIALIZABLE hoặc READ ONLY, quy tắc snapshot áp dụng ở phạm vi transaction theo semantics tương ứng; khi có xung đột cập nhật, Oracle có thể phát sinh lỗi serialization thay vì cho phép ghi đè.

### 9.4. Consistent read không có nghĩa lưu vô hạn phiên bản

Để tạo consistent read, Oracle cần giữ thông tin phiên bản cũ đủ lâu. Với LOB lớn, quản lý phiên bản LOB có storage policy riêng bên cạnh undo thông thường. Nếu một truy vấn đọc lâu cần phiên bản LOB đã bị thu hồi, có thể gặp ORA-22924.

Không giả định chỉ tăng UNDO_RETENTION là giải quyết mọi lỗi snapshot too old cho LOB. Kiểm tra cả LOB retention/storage policy, workload đọc dài và tốc độ cập nhật LOB.

## 10. LOB retention và snapshot too old

### 10.1. Vì sao cần giữ phiên bản LOB?

Giả sử một truy vấn bắt đầu đọc tài liệu rất lớn. Trong lúc truy vấn còn chạy, session khác cập nhật cùng LOB và commit phiên bản mới. Để truy vấn đầu tiên vẫn thấy dữ liệu đúng snapshot, Oracle có thể cần phiên bản cũ của LOB trong thời gian đọc.

Nếu phiên bản cũ không còn được giữ đủ lâu, truy vấn có thể thất bại thay vì đọc một hỗn hợp dữ liệu không nhất quán.

### 10.2. BasicFiles và PCTVERSION

Với BasicFiles LOB, thuộc tính PCTVERSION điều khiển tỷ lệ không gian LOB segment được dành cho các phiên bản cũ trong cơ chế versioning. Cấu hình quá thấp so với workload cập nhật/đọc dài có thể làm phiên bản cần cho consistent read bị thiếu.

PCTVERSION không phải tỷ lệ phần trăm dung lượng LOB dành cho dữ liệu ứng dụng mới; nó liên quan đến không gian giữ phiên bản cũ theo cơ chế BasicFiles.

### 10.3. SecureFiles và RETENTION

SecureFiles dùng thuộc tính RETENTION để quản lý phiên bản LOB cũ theo chính sách được hỗ trợ bởi release, ví dụ AUTO hoặc các chế độ retention khác. Hành vi cụ thể phụ thuộc phiên bản, cấu hình tablespace và workload.

Không sao chép nguyên giá trị PCTVERSION từ BasicFiles sang SecureFiles. Xem DDL storage clause và tài liệu Oracle cho đúng kiểu LOB.

### 10.4. ORA-22924

ORA-22924 thường chỉ ra snapshot too old khi Oracle không còn phiên bản LOB cần thiết cho consistent read. Khi gặp lỗi:

1. Xác định query/session đọc LOB kéo dài bao lâu.
2. Xác định LOB nào và table/partition nào liên quan.
3. Kiểm tra tốc độ cập nhật LOB trong khoảng thời gian đó.
4. Kiểm tra BasicFiles PCTVERSION hoặc SecureFiles RETENTION.
5. Đánh giá dung lượng LOB segment, tablespace và chi phí giữ phiên bản cũ.
6. Rút ngắn thời gian đọc hoặc chia quy trình streaming theo cách phù hợp.

Không khắc phục bằng cách tắt read consistency. Tính nhất quán là yêu cầu của database; cần cấp đủ tài nguyên/version retention hoặc thay đổi workload.

### 10.5. LOB retention không giống backup retention

Giữ phiên bản cũ để phục vụ consistent read không phải chính sách lưu trữ backup hoặc archive. PCTVERSION/RETENTION không thay thế RMAN backup, flashback, audit hoặc retention nghiệp vụ.

## 11. Temporary LOB và vòng đời

### 11.1. Khi nào dùng temporary LOB?

Temporary LOB phù hợp để:

- Ghép nhiều đoạn CLOB trước khi lưu.
- Tạo nội dung trung gian khi transform dữ liệu.
- Nhận dữ liệu lớn từ API/driver trước khi cập nhật bảng chính.
- Tạo bản xem trước hoặc kết quả tính toán tạm.

Temporary LOB không phải hàng persistent trong bảng và không được chia sẻ như một LOB column bình thường.

### 11.2. Tạo temporary CLOB

```sql
DECLARE
    l_temp_clob CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_temp_clob,
        cache   => TRUE,
        dur     => DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        l_temp_clob,
        LENGTH('Temporary text'),
        'Temporary text'
    );

    DBMS_OUTPUT.PUT_LINE(
        'Length = ' || DBMS_LOB.GETLENGTH(l_temp_clob)
    );

    DBMS_LOB.FREETEMPORARY(l_temp_clob);
END;
/
```

CREATETEMPORARY tạo LOB tạm; duration có thể là CALL hoặc SESSION. CALL gắn vòng đời với call hiện tại, SESSION giữ trong session cho tới khi được giải phóng hoặc session kết thúc.

### 11.3. Temporary LOB không có transaction semantics như persistent LOB

Thay đổi trên temporary LOB không phải DML transactional của một hàng bảng. Không dựa vào ROLLBACK để hoàn nguyên nội dung temporary LOB như persistent LOB. Temporary LOB thuộc session/call và cần được giải phóng đúng cách.

Nếu cần lưu nội dung lâu dài, phải ghi temporary LOB vào cột persistent LOB bằng INSERT/UPDATE phù hợp. Việc ghi vào cột persistent mới thuộc transaction database.

### 11.4. Giải phóng temporary LOB

Gọi FREETEMPORARY khi không còn dùng locator:

```sql
DBMS_LOB.FREETEMPORARY(l_temp_clob);
```

Không giải phóng locator rồi tiếp tục sử dụng. Khi exception xảy ra, nên có exception handler để giải phóng temporary LOB đã tạo trước khi raise lại lỗi.

### 11.5. Temporary LOB và TEMP space

Temporary LOB có thể sử dụng temporary tablespace và PGA/memory tùy kích thước, cấu hình và cách xử lý. Ứng dụng tạo nhiều temporary LOB hoặc giữ SESSION duration mà không giải phóng có thể làm tăng tài nguyên tạm. Theo dõi session và giải phóng đúng lúc.

## 12. BFILE và giới hạn transaction

### 12.1. BFILE chỉ là tham chiếu

BFILE locator lưu tham chiếu tới file ngoài database. Ví dụ tạo DIRECTORY:

```sql
CREATE OR REPLACE DIRECTORY LAB_FILE_DIR AS '/u01/app/files';
GRANT READ ON DIRECTORY LAB_FILE_DIR TO app_user;
```

Sau đó có thể lưu BFILE locator:

```sql
CREATE TABLE lab_external_files (
    file_id NUMBER PRIMARY KEY,
    file_name VARCHAR2(255),
    external_content BFILE
);

INSERT INTO lab_external_files
VALUES (
    1,
    'manual.pdf',
    BFILENAME('LAB_FILE_DIR', 'manual.pdf')
);
COMMIT;
```

Đường dẫn filesystem ở ví dụ phụ thuộc máy chủ database; DIRECTORY không phải đường dẫn local trên máy client.

### 12.2. BFILE read-only

Có thể mở và đọc BFILE qua DBMS_LOB.FILEOPEN, DBMS_LOB.READ và FILECLOSE. Không thể dùng DBMS_LOB.WRITE để sửa nội dung BFILE. Muốn cập nhật nội dung trong database, đọc file rồi ghi vào BLOB hoặc dùng quy trình import phù hợp.

### 12.3. COMMIT không bảo vệ file bên ngoài

Oracle không kiểm soát transaction của file hệ điều hành. Nếu một process bên ngoài thay file trong lúc session đang đọc BFILE, database không thể rollback file về phiên bản trước hoặc đảm bảo file không đổi theo snapshot của transaction.

Nếu yêu cầu tính nhất quán mạnh:

- Quản lý file theo tên/version bất biến.
- Ghi checksum, kích thước và metadata.
- Copy file vào BLOB khi import để database sở hữu nội dung.
- Chỉ công bố locator sau khi file đã được xác minh.

### 12.4. Quyền và lỗi BFILE

User cần quyền READ trên DIRECTORY object và quyền filesystem phù hợp ở máy chủ database. Lỗi có thể xuất phát từ file không tồn tại, tên directory/file sai, quyền OS hoặc locator không hợp lệ. Không nhầm các lỗi này với row lock của persistent LOB.

## 13. BasicFiles và SecureFiles

### 13.1. BasicFiles

BasicFiles là cơ chế lưu trữ LOB truyền thống. Nó vẫn xuất hiện trong các database cũ hoặc hệ thống chưa chuyển đổi. BasicFiles có các thuộc tính quản lý như CHUNK, PCTVERSION, CACHE/NOCACHE và LOGGING.

### 13.2. SecureFiles

SecureFiles là cơ chế lưu trữ LOB hiện đại của Oracle, được thiết kế để cải thiện hiệu năng và khả năng quản lý LOB. Tùy phiên bản và license/configuration, SecureFiles hỗ trợ các tính năng như compression, deduplication, encryption, retention và các tối ưu lưu trữ.

Ví dụ khai báo:

```sql
CREATE TABLE lab_secure_documents (
    document_id NUMBER PRIMARY KEY,
    document_body CLOB
)
LOB (document_body) STORE AS SECUREFILE (
    ENABLE STORAGE IN ROW
    CACHE
    LOGGING
);
```

Khả năng SecureFiles phụ thuộc tablespace và cấu hình database; không phải môi trường nào cũng có thể dùng mọi tính năng.

### 13.3. Storage type không thay đổi nguyên tắc khóa hàng

Chuyển từ BasicFiles sang SecureFiles không làm ứng dụng được phép bỏ SELECT FOR UPDATE trước DBMS_LOB write trên persistent LOB. Row locking, transaction boundary và concurrency control vẫn cần được thiết kế đúng.

### 13.4. Compression và deduplication

Compression có thể giảm dung lượng lưu trữ nhưng tăng CPU khi đọc/ghi. Deduplication có thể giảm dung lượng khi nhiều LOB có nội dung trùng nhau. Cả hai cần benchmark với pattern dữ liệu thực tế và điều kiện license/phiên bản.

Không coi deduplication là cách chống ghi đè đồng thời. Nó là tối ưu storage, không phải khóa nghiệp vụ.

## 14. OPEN/CLOSE LOB và index maintenance

### 14.1. DBMS_LOB.OPEN

DBMS_LOB.OPEN có thể được dùng để mở LOB trước khi thực hiện nhiều thao tác đọc/ghi:

```sql
DBMS_LOB.OPEN(
    lob_loc => l_body,
    open_mode => DBMS_LOB.LOB_READWRITE
);
```

Với persistent LOB cần sửa, vẫn phải khóa hàng chứa LOB trước khi ghi. OPEN không thay thế SELECT FOR UPDATE.

### 14.2. DBMS_LOB.CLOSE

Sau khi hoàn tất các thao tác, đóng LOB:

```sql
DBMS_LOB.CLOSE(l_body);
```

Nếu đã OPEN tường minh, hãy CLOSE trong cả đường chạy thành công và exception handler. Có thể dùng biến cờ để biết LOB đã mở hay chưa, tránh CLOSE locator chưa OPEN.

### 14.3. Vì sao OPEN/CLOSE có thể hữu ích?

Khi LOB được mở tường minh, Oracle có thể trì hoãn một số hoạt động duy trì functional/domain index liên quan tới LOB cho tới CLOSE thay vì lặp lại sau từng thao tác ghi. Điều này có thể hữu ích khi ghi nhiều đoạn. Tuy nhiên, không phải mọi loại index hoặc workload đều được hưởng lợi; kiểm tra tài liệu và benchmark.

### 14.4. OPEN/CLOSE không phải COMMIT

CLOSE kết thúc chế độ open của locator; nó không thay thế COMMIT. Transaction vẫn pending cho tới khi caller commit hoặc rollback.

### 14.5. Exception-safe pattern

Ví dụ khung xử lý:

```sql
DECLARE
    l_body CLOB;
    l_is_open BOOLEAN := FALSE;
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 10
    FOR UPDATE;

    DBMS_LOB.OPEN(l_body, DBMS_LOB.LOB_READWRITE);
    l_is_open := TRUE;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(' appended'),
        ' appended'
    );

    DBMS_LOB.CLOSE(l_body);
    l_is_open := FALSE;

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF l_is_open THEN
            DBMS_LOB.CLOSE(l_body);
        END IF;
        ROLLBACK;
        RAISE;
END;
/
```

Đây là skeleton minh họa. Trong code production, exception phát sinh từ CLOSE cũng cần được cân nhắc để không che mất lỗi gốc; transaction ownership phải được quy định rõ nếu procedure được gọi từ một transaction lớn hơn.

## 15. Thiết kế upload LOB lớn bằng staging

### 15.1. Vì sao không khóa hàng chính trong toàn bộ upload?

Một file vài trăm MB có thể mất nhiều thời gian để upload qua network. Nếu ứng dụng khóa hàng tài liệu chính trước khi nhận byte đầu tiên, row lock bị giữ trong toàn bộ thời gian truyền dữ liệu. Các thao tác đọc có thể vẫn đọc phiên bản đã commit, nhưng writer khác muốn sửa cùng hàng phải chờ.

Thiết kế tốt hơn thường là nhận dữ liệu vào staging/temp area, kiểm tra hoàn chỉnh rồi mới công bố trong transaction ngắn.

### 15.2. Bảng staging

Ví dụ bảng staging:

```sql
CREATE TABLE lab_document_uploads (
    upload_id NUMBER PRIMARY KEY,
    document_id NUMBER NOT NULL,
    upload_status VARCHAR2(20) NOT NULL,
    payload BLOB,
    expected_size NUMBER,
    actual_size NUMBER,
    checksum_value VARCHAR2(128),
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

Các trạng thái có thể gồm RECEIVING, VALIDATING, READY, PUBLISHED, FAILED hoặc EXPIRED. Thiết kế state machine rõ ràng giúp xử lý client disconnect và retry.

### 15.3. Quy trình upload

1. Tạo upload_id và hàng staging ở trạng thái RECEIVING.
2. Stream các chunk vào payload staging.
3. Cập nhật actual_size và checksum theo tiến độ.
4. Khi upload kết thúc, kiểm tra kích thước, checksum, MIME/type và nội dung.
5. Đánh dấu READY.
6. Mở transaction ngắn để khóa document chính hoặc dùng version predicate.
7. Gán/copy LOB staging sang document chính.
8. Tăng version, cập nhật metadata và đánh dấu PUBLISHED trong cùng transaction.
9. Commit.
10. Dọn staging theo retention policy.

### 15.4. Công bố bằng một UPDATE

Nếu ứng dụng đã có payload BLOB hoàn chỉnh trong staging, có thể cập nhật hàng chính bằng DML:

```sql
UPDATE lab_attachments a
SET a.file_content = (
        SELECT u.payload
        FROM lab_document_uploads u
        WHERE u.upload_id = :upload_id
          AND u.upload_status = 'READY'
    ),
    a.updated_at = SYSTIMESTAMP
WHERE a.attachment_id = :attachment_id
  AND a.version_no = :expected_version;
```

Đây là ví dụ khái niệm; schema thực tế cần thêm version_no và bảo đảm subquery trả đúng một hàng. Kiểm tra SQL%ROWCOUNT để biết publish có cập nhật document không. Nếu bằng 0, có thể version đã đổi hoặc document không tồn tại.

### 15.5. Resume và idempotency

Nếu upload bị ngắt:

- Giữ upload_id ổn định để client có thể resume.
- Ghi nhận chunk sequence/offset đã nhận.
- Kiểm tra chunk trùng trước khi append.
- Tính checksum cuối cùng trước khi publish.
- Không đánh dấu READY cho file chưa hoàn chỉnh.
- Có job dọn staging quá hạn.

Đừng append lại chunk đã nhận nếu không có offset/idempotency key, vì retry có thể làm nội dung bị lặp.

## 16. Transaction granularity và chunk commit

### 16.1. Một transaction cho toàn bộ LOB

Nếu yêu cầu người đọc chỉ thấy tài liệu cũ hoặc tài liệu mới hoàn chỉnh, hãy ghi toàn bộ nội dung vào staging/temporary LOB rồi publish trong transaction ngắn. Hoặc, nếu ghi trực tiếp vào persistent LOB, giữ toàn bộ các chunk trong một transaction và chỉ commit khi đã hoàn tất.

Ưu điểm: người đọc khác không thấy các phần chưa commit; rollback có thể hủy thay đổi persistent chưa commit.

Nhược điểm: transaction dài, row lock lâu, undo/version retention và khả năng retry phức tạp.

### 16.2. Commit sau từng chunk

Commit từng chunk làm giảm thời gian mỗi transaction nhưng công bố trạng thái một phần. Khi đó cần:

- Trạng thái UPLOADING/INCOMPLETE để reader không coi nội dung là hoàn chỉnh.
- Offset/checkpoint đã commit.
- Checksum cho từng chunk hoặc toàn file.
- Cơ chế resume không ghi lặp.
- Cách publish atomic khi đủ chunk.

Nếu reader chỉ truy vấn document_status = 'PUBLISHED', có thể tránh đọc payload chưa hoàn chỉnh.

### 16.3. Không chia sẻ locator qua session

Locator là handle gắn với ngữ cảnh Oracle/connection. Không gửi locator PL/SQL từ session này sang session khác như một token bền vững. Nếu cần chuyển công việc, truyền document_id/upload_id và offset/checksum; session mới lấy locator hợp lệ từ database.

### 16.4. Không giữ row lock trong khi chờ client

Client có thể chậm, mất mạng hoặc đóng trình duyệt. Không giữ SELECT FOR UPDATE trong khi chờ client gửi chunk tiếp theo. Dùng staging và publish transaction ngắn để giới hạn lock duration.

## 17. Lỗi thường gặp khi thao tác LOB

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng kiểm tra/xử lý |
| --- | --- | --- |
| ORA-22920 | Hàng chứa persistent LOB chưa được khóa | SELECT ... FOR UPDATE trước DBMS_LOB write |
| ORA-22275 | Locator không hợp lệ hoặc chưa khởi tạo | Kiểm tra NULL/EMPTY locator, locator lifetime và loại LOB |
| ORA-22924 | Không còn LOB version cần cho consistent read | Kiểm tra PCTVERSION/RETENTION và truy vấn đọc dài |
| ORA-00054 | NOWAIT không lấy được row lock | Báo bận, retry có backoff hoặc dùng WAIT |
| ORA-30006 | Hết thời gian WAIT để lấy lock | Điều chỉnh timeout hoặc giảm thời gian giữ khóa |
| ORA-00060 | Deadlock giữa các transaction | Kiểm tra thứ tự khóa nhiều hàng và transaction graph |
| ORA-01555 | Snapshot too old liên quan undo/read consistency | Xem thời gian query, undo và workload cập nhật |
| LOB bị ghi đè nội dung mới | Lost update do client lưu bản cũ | Dùng version column và optimistic locking |
| LOB bị lặp chunk | Retry append không idempotent | Ghi offset/chunk ID, checksum và trạng thái upload |
| Reader thấy file chưa hoàn chỉnh | Commit theo chunk nhưng không có publish state | Dùng staging và trạng thái PUBLISHED |
| Temporary LOB dùng nhiều TEMP | Không giải phóng hoặc giữ SESSION duration lâu | Gọi FREETEMPORARY và theo dõi session |
| BFILE không mở được | DIRECTORY grant, file path hoặc OS permission | Kiểm tra DIRECTORY, READ grant và quyền máy chủ |
| Dữ liệu BFILE thay đổi ngoài transaction | File do process bên ngoài sửa | Dùng tên/version bất biến hoặc import vào BLOB |

## 18. Chẩn đoán khóa và session chờ

### 18.1. Kiểm tra session đang chờ

DBA có thể quan sát V$SESSION để xem wait event, blocking_session và thời gian chờ:

```sql
SELECT
    sid,
    serial#,
    username,
    status,
    event,
    wait_class,
    seconds_in_wait,
    blocking_session,
    sql_id
FROM v$session
WHERE blocking_session IS NOT NULL;
```

Quyền đọc V$SESSION thường cần được DBA cấp. Không yêu cầu quyền DBA rộng chỉ để chạy ứng dụng; nhờ DBA trích xuất thông tin phù hợp khi điều tra.

### 18.2. Xem object và row wait

V$LOCKED_OBJECT có thể giúp xác định object đang bị transaction khóa ở mức object metadata:

```sql
SELECT
    lo.session_id,
    lo.object_id,
    o.owner,
    o.object_name,
    o.object_type,
    lo.locked_mode
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id;
```

View này không phải công cụ duy nhất để biết chính xác row/LOB chunk nào đang chờ. Kết hợp V$SESSION, V$LOCK, SQL_ID, ASH/AWR nếu được cấp quyền và license phù hợp.

### 18.3. ORA-00060 và thứ tự khóa

Nếu transaction A khóa document 10 rồi document 20, trong khi B khóa document 20 rồi document 10, hai transaction có thể tạo deadlock. Giảm rủi ro bằng cách khóa nhiều hàng theo thứ tự khóa thống nhất, ví dụ tăng dần DOCUMENT_ID.

Không bắt ORA-00060 rồi tiếp tục như thể statement thành công. Oracle rollback statement gây deadlock; ứng dụng cần xử lý retry toàn transaction theo chính sách phù hợp.

### 18.4. Retry có backoff

Với lỗi lock tạm thời, retry nên có:

- Số lần thử giới hạn.
- Delay tăng dần (backoff) và jitter nếu nhiều client.
- Phân biệt lỗi transient với lỗi dữ liệu/constraint.
- Idempotency để retry không ghi lặp chunk hoặc side effect.
- Logging document_id, upload_id, version và mã lỗi.

Không retry vô hạn vì có thể tạo tải cao hơn và kéo dài contention.

## 19. Bài thực hành: tạo bảng LOB và ghi nội dung

Các bài lab dưới đây chạy trong schema riêng. Không dùng bảng production hoặc document ID đang có dữ liệu thật.

### 19.1. Tạo bảng

```sql
CREATE TABLE lab_lob_documents (
    document_id NUMBER
        CONSTRAINT pk_lab_lob_documents PRIMARY KEY,
    document_name VARCHAR2(200) NOT NULL,
    document_body CLOB,
    version_no NUMBER DEFAULT 1 NOT NULL,
    document_status VARCHAR2(20) DEFAULT 'DRAFT' NOT NULL,
    updated_at TIMESTAMP
);

INSERT INTO lab_lob_documents (
    document_id,
    document_name,
    document_body,
    version_no,
    document_status,
    updated_at
)
VALUES (
    1,
    'Concurrency lab',
    EMPTY_CLOB(),
    1,
    'DRAFT',
    SYSTIMESTAMP
);

COMMIT;
```

### 19.2. Ghi CLOB bằng SQL UPDATE

```sql
UPDATE lab_lob_documents
SET document_body = TO_CLOB('First version of the document.'),
    updated_at = SYSTIMESTAMP
WHERE document_id = 1;

SELECT
    document_id,
    DBMS_LOB.GETLENGTH(document_body) AS body_length
FROM lab_lob_documents
WHERE document_id = 1;

COMMIT;
```

### 19.3. Ghi nối CLOB bằng DBMS_LOB

```sql
DECLARE
    l_body CLOB;
    l_piece VARCHAR2(1000) := ' Added through DBMS_LOB.';
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_lob_documents
    WHERE document_id = 1
    FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(l_piece),
        l_piece
    );

    DBMS_OUTPUT.PUT_LINE(
        'New length = ' || DBMS_LOB.GETLENGTH(l_body)
    );

    COMMIT;
END;
/
```

Đọc lại nội dung:

```sql
SELECT DBMS_LOB.SUBSTR(document_body, 4000, 1)
FROM lab_lob_documents
WHERE document_id = 1;
```

DBMS_LOB.SUBSTR trả một phần nội dung. Với LOB rất lớn, đọc theo nhiều offset/buffer thay vì cố đưa toàn bộ vào VARCHAR2.

### 19.4. Thay toàn bộ nội dung bằng RETURNING locator

```sql
DECLARE
    l_body CLOB;
    l_piece VARCHAR2(1000) := 'Replacement content.';
BEGIN
    UPDATE lab_lob_documents
    SET document_body = EMPTY_CLOB(),
        updated_at = SYSTIMESTAMP
    WHERE document_id = 1
    RETURNING document_body INTO l_body;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(l_piece),
        l_piece
    );

    COMMIT;
END;
/
```

UPDATE lấy row lock; locator trả về tham chiếu tới LOB rỗng vừa khởi tạo. Ghi chunk và commit trong cùng transaction.

### 19.5. Kiểm tra version và length

```sql
SELECT
    document_id,
    version_no,
    document_status,
    DBMS_LOB.GETLENGTH(document_body) AS body_length,
    updated_at
FROM lab_lob_documents
WHERE document_id = 1;
```

## 20. Bài thực hành: quan sát row lock với hai session

Mở hai connection riêng tới cùng schema lab.

### 20.1. Session A

Chạy block và chưa COMMIT ngay:

```sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_lob_documents
    WHERE document_id = 1
    FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(' Session A update.'),
        ' Session A update.'
    );

    DBMS_OUTPUT.PUT_LINE('A has updated the LOB; transaction is open.');
END;
/
```

Block kết thúc nhưng transaction chưa commit, nên row lock vẫn được giữ.

### 20.2. Session B

Thử lấy cùng row lock:

```sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT document_body
    INTO l_body
    FROM lab_lob_documents
    WHERE document_id = 1
    FOR UPDATE WAIT 5;

    DBMS_OUTPUT.PUT_LINE('B acquired the row lock.');
END;
/
```

Session B có thể chờ tối đa 5 giây rồi nhận timeout nếu A vẫn giữ khóa.

### 20.3. Quay lại Session A

```sql
COMMIT;
```

Sau khi A commit, chạy lại block Session B. B có thể lấy khóa nếu không có session khác đang giữ.

### 20.4. Quan sát read consistency

Trong khi A đang giữ lock nhưng chưa commit, chạy SELECT thông thường ở B:

```sql
SELECT DBMS_LOB.SUBSTR(document_body, 4000, 1)
FROM lab_lob_documents
WHERE document_id = 1;
```

Reader thông thường thường đọc phiên bản đã commit trước đó, trong khi SELECT FOR UPDATE phải chờ khóa. So sánh kết quả trước và sau COMMIT của A.

## 21. Bài thực hành: optimistic locking chống lost update

### 21.1. Session A và B cùng đọc version

Ở cả hai session:

```sql
SELECT document_id, version_no
FROM lab_lob_documents
WHERE document_id = 1;
```

Giả sử cả hai nhận VERSION_NO = 1.

### 21.2. Session A cập nhật trước

```sql
UPDATE lab_lob_documents
SET document_body = TO_CLOB('Content saved by A'),
    version_no = version_no + 1,
    updated_at = SYSTIMESTAMP
WHERE document_id = 1
  AND version_no = 1;

SELECT SQL%ROWCOUNT FROM dual;
COMMIT;
```

Lưu ý: câu SELECT SQL%ROWCOUNT riêng sau UPDATE không còn là cách đọc đúng row count của UPDATE. Trong thực hành thật, dùng PL/SQL block:

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_lob_documents
    SET document_body = TO_CLOB('Content saved by A'),
        version_no = version_no + 1,
        updated_at = SYSTIMESTAMP
    WHERE document_id = 1
      AND version_no = 1;

    l_rows := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('A updated rows = ' || l_rows);
    COMMIT;
END;
/
```

### 21.3. Session B lưu bằng version cũ

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_lob_documents
    SET document_body = TO_CLOB('Content saved by B'),
        version_no = version_no + 1,
        updated_at = SYSTIMESTAMP
    WHERE document_id = 1
      AND version_no = 1;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 0 THEN
        DBMS_OUTPUT.PUT_LINE(
            'Conflict: document was changed by another session.'
        );
    ELSE
        COMMIT;
    END IF;
END;
/
```

Vì A đã tăng version lên 2, UPDATE của B không khớp và row count là 0. B không ghi đè nội dung A.

### 21.4. Bài học

Pessimistic locking điều phối session trong lúc transaction đang mở. Optimistic locking phát hiện bản cũ khi lưu. Với chỉnh sửa tài liệu kéo dài, version column thường phù hợp hơn việc giữ row lock suốt thời gian người dùng thao tác.

## 22. Bài thực hành: staging upload và publish

### 22.1. Tạo bảng staging

```sql
CREATE TABLE lab_lob_upload_stage (
    upload_id NUMBER PRIMARY KEY,
    document_id NUMBER NOT NULL,
    upload_status VARCHAR2(20) NOT NULL,
    payload CLOB,
    expected_length NUMBER,
    actual_length NUMBER,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

### 22.2. Nạp dữ liệu vào staging

```sql
INSERT INTO lab_lob_upload_stage (
    upload_id,
    document_id,
    upload_status,
    payload,
    expected_length,
    actual_length,
    created_at,
    completed_at
)
VALUES (
    1001,
    1,
    'READY',
    TO_CLOB('Complete staged document content.'),
    LENGTH('Complete staged document content.'),
    LENGTH('Complete staged document content.'),
    SYSTIMESTAMP,
    SYSTIMESTAMP
);

COMMIT;
```

### 22.3. Publish với optimistic version check

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_lob_documents d
    SET document_body = (
            SELECT s.payload
            FROM lab_lob_upload_stage s
            WHERE s.upload_id = 1001
              AND s.upload_status = 'READY'
        ),
        version_no = version_no + 1,
        document_status = 'PUBLISHED',
        updated_at = SYSTIMESTAMP
    WHERE d.document_id = 1
      AND d.version_no = 2;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20032,
            'Publish conflict: document version has changed.'
        );
    END IF;

    UPDATE lab_lob_upload_stage
    SET upload_status = 'PUBLISHED',
        completed_at = SYSTIMESTAMP
    WHERE upload_id = 1001
      AND upload_status = 'READY';

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
```

Trong ví dụ, UPDATE tài liệu và chuyển trạng thái staging nằm trong cùng transaction. Nếu publish thất bại, cả hai thay đổi được rollback. Với dữ liệu thực tế, cần kiểm tra stage row tồn tại duy nhất và expected length/checksum khớp trước khi publish.

## 23. Nguyên tắc thiết kế và vận hành

1. **Phân biệt loại LOB.** CLOB/NCLOB là ký tự; BLOB là byte; BFILE là file ngoài database.
2. **Hiểu locator.** Locator là tham chiếu có vòng đời, không phải bản sao độc lập bền vững.
3. **Khóa hàng trước DBMS_LOB write.** Dùng SELECT FOR UPDATE hoặc UPDATE ... RETURNING locator.
4. **Đừng coi CHUNK là khóa.** Row lock trên hàng chứa LOB là ranh giới đồng thời quan trọng.
5. **Giữ transaction ngắn.** Không khóa hàng chính trong suốt quá trình upload chậm từ client.
6. **Chọn pessimistic hay optimistic locking theo workload.** Tài liệu được chỉnh sửa lâu thường phù hợp version column.
7. **Chụp version khi đọc và kiểm tra khi ghi.** UPDATE ... WHERE version_no = expected giúp phát hiện lost update.
8. **Chọn ranh giới commit rõ ràng.** Một transaction cho toàn bộ thay đổi nếu cần atomic; nếu commit từng chunk, phải có upload state/checkpoint.
9. **Dùng staging cho file lớn.** Validate payload trước khi publish vào hàng chính.
10. **Dùng offset/chunk ID và checksum.** Retry upload phải idempotent để tránh lặp nội dung.
11. **Phân biệt persistent và temporary LOB.** Temporary LOB cần quản lý lifetime và FREETEMPORARY.
12. **Không dùng BFILE nếu cần transaction cho nội dung file.** Import vào BLOB khi cần snapshot bền vững.
13. **Chú ý retention và consistent read.** Đọc LOB lâu trong khi cập nhật liên tục có thể cần giữ phiên bản cũ lâu hơn.
14. **Cấu hình BasicFiles/SecureFiles đúng loại.** PCTVERSION và RETENTION không phải một thuộc tính dùng chung cho mọi LOB.
15. **Dùng OPEN/CLOSE có chủ đích.** CLOSE không thay thế COMMIT; xử lý exception để không bỏ quên locator đã mở.
16. **Theo dõi wait và lỗi.** Phân biệt ORA-22920, ORA-22924, ORA-00054, ORA-30006 và ORA-00060.
17. **Không retry vô hạn.** Dùng backoff, giới hạn lần thử và idempotency.
18. **Kiểm thử nhiều session.** Một session chạy thành công không chứng minh concurrency semantics đúng.

## 24. Câu hỏi tự kiểm tra

1. CLOB, NCLOB, BLOB và BFILE khác nhau như thế nào?
2. Persistent LOB khác temporary LOB ở vòng đời và transaction semantics ra sao?
3. LOB locator là gì? Vì sao không nên xem locator như một bản sao nội dung?
4. EMPTY_CLOB() khác NULL như thế nào?
5. Vì sao cần SELECT FOR UPDATE trước DBMS_LOB.WRITE trên persistent LOB?
6. UPDATE trực tiếp LOB column có cần SELECT FOR UPDATE riêng trước đó không?
7. Row lock trên hàng chứa LOB được giữ tới khi nào?
8. Vì sao hai LOB column khác nhau trong cùng hàng vẫn có thể tranh chấp?
9. CHUNK size có phải đơn vị khóa không?
10. WAIT, NOWAIT và SKIP LOCKED khác nhau thế nào?
11. Lost update xảy ra ra sao khi hai người cùng lưu toàn bộ nội dung?
12. Optimistic locking dùng VERSION_NO để ngăn ghi đè như thế nào?
13. Vì sao ORA_ROWSCN không phải lúc nào cũng là version token nghiệp vụ phù hợp?
14. DBMS_LOB.WRITE khác WRITEAPPEND và APPEND thế nào?
15. Amount/offset của CLOB và BLOB khác nhau ra sao?
16. DBMS_LOB.TRIM khác ERASE thế nào?
17. Vì sao commit sau từng chunk có thể làm reader thấy trạng thái chưa hoàn chỉnh?
18. Read consistency và row lock có vai trò khác nhau thế nào?
19. ORA-22924 liên quan retention/versioning ra sao?
20. BasicFiles PCTVERSION và SecureFiles RETENTION dùng để làm gì?
21. Vì sao temporary LOB phải được giải phóng?
22. Vì sao COMMIT không thể rollback thay đổi file BFILE ở filesystem?
23. Staging upload giúp giảm thời gian giữ row lock như thế nào?
24. Những thông tin nào cần log để hỗ trợ resume và retry upload?

## 25. Mô hình ghi nhớ

```text
PERSISTENT LOB
    |
    +-- LOB locator tham chiếu nội dung trong bảng
    +-- DML/DBMS_LOB write thuộc transaction
    +-- SELECT FOR UPDATE trước DBMS_LOB write
    +-- Row lock giữ tới COMMIT/ROLLBACK
    |
    v
CONCURRENCY
    |
    +-- Pessimistic: khóa hàng trước khi sửa
    +-- Optimistic: VERSION_NO trong WHERE
    +-- SQL%ROWCOUNT = 0: phát hiện conflict
    |
    v
CONSISTENCY
    |
    +-- MVCC cho reader
    +-- LOB version retention cho consistent read
    +-- ORA-22924 khi thiếu phiên bản cần thiết
    |
    v
LARGE UPLOAD
    |
    +-- Staging / temporary LOB
    +-- Stream theo chunk và checksum
    +-- Validate trước publish
    +-- Transaction ngắn để thay LOB chính
    |
    v
LOẠI NGOẠI LỆ
    |
    +-- BFILE nằm ngoài transaction database
    +-- Temporary LOB cần quản lý lifetime
    +-- CHUNK không phải đơn vị khóa
```

**Điểm cần nhớ:** cập nhật persistent LOB là một phần của transaction database. Khi sửa bằng DBMS_LOB, khóa hàng chứa LOB trước; giữ khóa tới khi commit/rollback và không để transaction kéo dài theo tốc độ upload của client. Dùng version column để phát hiện bản tài liệu cũ, staging để chuẩn bị file lớn, và cấu hình retention phù hợp để reader có thể đọc phiên bản nhất quán.
