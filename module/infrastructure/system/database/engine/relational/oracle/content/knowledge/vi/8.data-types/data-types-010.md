# CLOB, NCLOB, BLOB và BFILE

Trong Oracle Database, một cột `VARCHAR2` phù hợp với tên, mã, địa chỉ và phần lớn chuỗi ngắn. Nhưng hệ thống có thể phải lưu **nội dung bài viết dài**, **bản ghi văn bản**, **hình ảnh**, **PDF**, **tệp âm thanh** hoặc **tài liệu nằm sẵn trên máy chủ**. Những trường hợp này dẫn đến nhóm kiểu dữ liệu **LOB (Large Object)**.

Bốn kiểu thường gặp là:

- **`CLOB` (Character Large Object):** dữ liệu văn bản lớn dùng **database character set**.
- **`NCLOB` (National Character Large Object):** dữ liệu văn bản lớn dùng **national character set**.
- **`BLOB` (Binary Large Object):** dữ liệu nhị phân lớn mà Oracle không tự diễn giải thành ký tự.
- **`BFILE` (Binary File):** một **tham chiếu đến tệp nhị phân nằm ngoài database**, trên filesystem mà Oracle server có thể truy cập; nội dung tệp **chỉ đọc qua giao diện BFILE**.

Điểm chung là chúng có thể biểu diễn dữ liệu lớn và dùng **LOB locator** để tham chiếu nội dung; điểm khác nhau quyết định cách mã hóa, lưu trữ, giao dịch, sao lưu, cấp quyền và truy xuất.

## 1. Chọn đúng kiểu LOB ngay từ yêu cầu

| Kiểu | Chứa gì? | Character set | Nơi giữ nội dung | Oracle có thể cập nhật nội dung? | Tình huống điển hình |
| --- | --- | --- | --- | --- | --- |
| **`CLOB`** | Văn bản dài | Database character set | **Trong database** (LOB storage) | **Có**, theo cơ chế giao dịch Oracle | Bài viết, XML dạng text, JSON dạng text khi không dùng kiểu JSON chuyên dụng, log văn bản |
| **`NCLOB`** | Văn bản dài | National character set | **Trong database** | **Có**, theo cơ chế giao dịch Oracle | Dữ liệu văn bản yêu cầu rõ national character set |
| **`BLOB`** | Dãy byte | Không có ngữ nghĩa character set | **Trong database** | **Có**, theo cơ chế giao dịch Oracle | PDF, ảnh PNG/JPEG, ZIP, tài liệu Office, dữ liệu mã hóa dạng byte |
| **`BFILE`** | Locator tham chiếu tệp nhị phân ngoài DB | Không có ngữ nghĩa character set | **Ngoài database**, trong tệp OS | **Không sửa nội dung qua BFILE**; có thể đổi giá trị locator | Tệp đã được đặt trên storage và Oracle cần đọc qua đường dẫn server |

Quy tắc chọn ngắn gọn:

```text
Dữ liệu có phải văn bản không?
   |
   +-- Có --> Có yêu cầu national character set riêng?
   |             |
   |             +-- Có ----------------------> NCLOB
   |             |
   |             +-- Không -------------------> CLOB
   |
   +-- Không --> Muốn Oracle quản lý nội dung file
                 trong database/transaction/backup?
                    |
                    +-- Có -------------------> BLOB
                    |
                    +-- Không, tệp nằm ngoài --> BFILE
                        (chỉ khi đúng yêu cầu chỉ đọc
                         và Oracle server truy cập được)
```

**Đừng chọn `NCLOB` chỉ vì nội dung có tiếng Việt.** Nếu database dùng character set Unicode như `AL32UTF8`, `CLOB` đã có thể lưu văn bản Unicode. `NCLOB` hữu ích khi yêu cầu dữ liệu theo **national character set** riêng, chứ không phải “phiên bản Unicode bắt buộc” của `CLOB`.

**Đừng chọn `BFILE` chỉ vì tệp lớn.** Với `BFILE`, Oracle chỉ quản lý tham chiếu; bản thân tệp không tham gia rollback/commit và không nằm trong backup dữ liệu Oracle theo cách một `BLOB` được lưu trong database.

## 2. LOB khác `VARCHAR2`, `RAW` và `LONG` ở đâu?

Các kiểu chuỗi và nhị phân nhỏ có giới hạn kích thước giá trị phụ thuộc ngữ cảnh SQL/PLSQL và cấu hình Oracle:

| Kiểu | Dùng cho | Ranh giới quan trọng |
| --- | --- | --- |
| `VARCHAR2` / `NVARCHAR2` | Chuỗi ngắn và trung bình | Trong SQL có giới hạn theo `MAX_STRING_SIZE` và ngữ nghĩa byte/ký tự; không thay thế LOB khi tài liệu rất lớn |
| `RAW` | Dữ liệu byte ngắn | Có giới hạn độ dài giá trị trong SQL, không dùng cho ảnh/PDF lớn |
| `LONG` / `LONG RAW` | Kiểu legacy | Bị hạn chế nhiều thao tác SQL/DDL; nên ưu tiên `CLOB`/`BLOB` cho thiết kế mới |
| `CLOB` / `NCLOB` | Văn bản rất dài | Cần chú ý character set, LOB locator, hàm/phương thức thao tác LOB và giới hạn của client |
| `BLOB` | Dữ liệu byte rất dài | Cần API đọc/ghi binary; không dùng hàm chuỗi tùy tiện |
| `BFILE` | Tham chiếu đến tệp server bên ngoài | File phải tồn tại và có quyền đọc ở OS/directory; không quản lý nội dung qua transaction Oracle |

Với cấu hình SQL phổ biến `MAX_STRING_SIZE = STANDARD`, `VARCHAR2` có giới hạn tối đa **4.000 byte** ở mức SQL; chế độ `EXTENDED` cho phép một số kiểu chuỗi/RAW lên đến **32.767 byte** với điều kiện và ràng buộc tương ứng. `VARCHAR2` trong PL/SQL cũng có giới hạn tối đa **32.767 byte**. Đó là những giới hạn của kiểu/biến chuỗi; các LOB được thiết kế cho dữ liệu lớn hơn nhiều, với giới hạn cụ thể phụ thuộc release, block size và cơ chế lưu trữ.

Không nên đổi toàn bộ cột `VARCHAR2` sang `CLOB` theo phản xạ. Một mã khách hàng `VARCHAR2(20)` dễ kiểm soát độ dài, ràng buộc và tạo index B-tree hơn một cột LOB; LOB mang theo chi phí locator, lưu trữ, truy xuất và bảo trì riêng.

## 3. LOB locator và nội dung thật không phải cùng thứ

Một cột LOB lưu thông tin cho phép Oracle **định vị nội dung LOB**. Trong SQL/PLSQL/JDBC, bạn thường nhận hoặc truyền một **LOB locator** (hoặc dùng API stream), chứ không mặc định kéo tất cả byte của tệp vài GB về một biến chuỗi của ứng dụng.

```text
             HÀNG TRONG BẢNG ỨNG DỤNG
   +------------------------------------------------+
   | DOCUMENT_ID | TITLE | CONTENT (LOB locator)    |
   +------------------------------------------------+
                            |
                            v
                   CLOB/BLOB/NCLOB data
                 do Oracle Database quản lý
                 (in-row hoặc out-of-row
                  tùy kích thước/cấu hình)

   Đối với BFILE:
   +------------------------------------------------+
   | DOCUMENT_ID | EXTERNAL_FILE (BFILE locator)    |
   +------------------------------------------------+
                            |
                            v
             DIRECTORY object + tên tệp OS
                            |
                            v
             Tệp trên filesystem của DB server
             (ngoài database, nội dung chỉ đọc)
```

### 3.1. Internal LOB và external LOB

`CLOB`, `NCLOB` và `BLOB` là **internal LOBs**: Oracle quản lý dữ liệu LOB trong database. Các thay đổi được ghi nhận bằng cơ chế transaction/recovery tương ứng với tính năng và tùy chọn lưu trữ đang dùng.

`BFILE` là **external LOB**: trong cột chỉ có locator trỏ tới **DIRECTORY object** và tên file; dữ liệu thật nằm ở OS. Oracle có thể quản lý việc cập nhật **giá trị locator** trong row, nhưng không kiểm soát hoặc rollback được thay đổi nội dung file do chương trình bên ngoài thực hiện.

| Hành động | Internal `BLOB` / `CLOB` / `NCLOB` | External `BFILE` |
| --- | --- | --- |
| `INSERT` locator/giá trị vào row | Có | Có, lưu tham chiếu file |
| Đọc nội dung bằng API LOB | Có | Có, nếu server đọc được file |
| Sửa nội dung qua `DBMS_LOB` | Có, bằng thao tác được hỗ trợ | **Không**, BFILE là nội dung chỉ đọc |
| `COMMIT`/`ROLLBACK` kiểm soát nội dung | Có, theo cơ chế giao dịch của Oracle | Không kiểm soát thay đổi byte trong file OS |
| RMAN backup của database giữ nội dung | Có, vì dữ liệu thuộc database theo phạm vi backup | Không tự sao lưu nội dung file OS mà BFILE trỏ tới |
| Quyền cần quan tâm | Quyền trên bảng/LOB và các chính sách database | Thêm quyền trên DIRECTORY và quyền đọc file OS |

### 3.2. In-row và out-of-row không phải hai kiểu dữ liệu

Đối với internal LOB, Oracle có thể lưu giá trị LOB nhỏ **trong vùng row** hoặc lưu nội dung ở **LOB segment** riêng, còn row chứa locator và thông tin liên quan. Điều này tùy kích thước, thuộc tính storage, phiên bản và khả năng lưu của Oracle.

```text
Trường hợp internal LOB nhỏ:
  Data block của bảng
    -> row và có thể có dữ liệu LOB nằm trong row

Trường hợp internal LOB lớn:
  Data block của bảng
    -> row + locator
                  |
                  +--> LOB segment chứa nội dung lớn
                       (và metadata/index nội bộ tùy kiểu)
```

Không đặt ra quy tắc cứng “giá trị dưới X byte luôn in-row”: overhead, kiểu LOB, cấu hình `ENABLE/DISABLE STORAGE IN ROW`, SecureFiles/BasicFiles và giới hạn của block có thể làm kết quả khác. Việc truy cập LOB out-of-row có thể cần I/O bổ sung và cách đọc/stream phù hợp.

## 4. `CLOB`: lưu và xử lý văn bản dài

**`CLOB` dùng database character set**. Trên database cấu hình `AL32UTF8`, đây thường là lựa chọn tự nhiên để lưu tài liệu, nội dung bài viết và các chuỗi Unicode lớn của ứng dụng hiện đại.

Ví dụ các nội dung phù hợp với CLOB:

- Bài hướng dẫn kỹ thuật vài trăm KB.
- Văn bản hợp đồng hoặc transcript chứa nhiều ngôn ngữ.
- Dữ liệu JSON dạng text nếu thiết kế chưa dùng kiểu JSON native hoặc ràng buộc JSON phù hợp.
- Nội dung HTML/XML dài cần giữ đầy đủ ký tự.

Nhưng LOB không biến database thành hệ thống tìm kiếm full-text tối ưu theo mặc định. Nếu cần tìm toàn văn có đánh chỉ mục, có thể đánh giá **Oracle Text** hoặc tính năng tìm kiếm phù hợp với release/edition thay vì trông chờ một B-tree index trên toàn bộ nội dung `CLOB`.

### 4.1. Khai báo CLOB

```sql
CREATE TABLE lab_articles (
    article_id NUMBER PRIMARY KEY,
    title      VARCHAR2(200 CHAR) NOT NULL,
    body       CLOB
);
```

Thêm dữ liệu văn bản nhỏ để minh họa cú pháp:

```sql
INSERT INTO lab_articles (article_id, title, body)
VALUES (
    1,
    'Ghi chú Oracle',
    TO_CLOB('Nội dung hướng dẫn về kiểu dữ liệu CLOB.')
);

COMMIT;
```

`TO_CLOB` giúp chuyển một giá trị tương thích sang CLOB, nhưng **một literal SQL vẫn có giới hạn độ dài literal/biểu thức SQL**. Không dùng chuỗi literal dài hàng MB trong lệnh `INSERT`: với dữ liệu lớn, dùng bind variable, JDBC stream hoặc API đọc/ghi LOB.

### 4.2. Độ dài và trích đoạn

```sql
SELECT
    article_id,
    title,
    DBMS_LOB.GETLENGTH(body) AS body_length,
    DBMS_LOB.SUBSTR(body, 80, 1) AS first_80_units
FROM lab_articles;
```

Với CLOB, `DBMS_LOB.GETLENGTH` và các offset/amount của API LOB theo **đơn vị ký tự theo quy tắc của Oracle**, còn BLOB dùng **byte**. Các ký tự Unicode bổ sung (supplementary characters) có những lưu ý về đơn vị UCS2 trong một số API Oracle; đừng tự coi giá trị offset là số byte UTF-8 hoặc luôn tương ứng với số grapheme hiển thị trên màn hình.

`DBMS_LOB.SUBSTR` chỉ trả một **đoạn**. Ở ngữ cảnh SQL, kích thước chuỗi trả về còn chịu giới hạn kiểu trả về, character set và client. Không dùng `DBMS_LOB.SUBSTR(body, 1000000, 1)` rồi kỳ vọng nhận nguyên văn tài liệu MB trong một ô VARCHAR2.

### 4.3. Nối thêm nội dung

Trong PL/SQL, bạn có thể lấy locator internal LOB và gọi `DBMS_LOB.WRITEAPPEND`:

```sql
DECLARE
    l_body   CLOB;
    l_chunk  VARCHAR2(200) := ' Đoạn văn bản bổ sung.';
BEGIN
    SELECT body
      INTO l_body
      FROM lab_articles
     WHERE article_id = 1
       FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_body,
        amount  => LENGTH(l_chunk),
        buffer  => l_chunk
    );

    COMMIT;
END;
/
```

`FOR UPDATE` thể hiện ý định khóa hàng trước thao tác thay đổi LOB trong ví dụ. Các API sửa persistent LOB phải được dùng trong transaction hợp lệ, với quyền phù hợp, locator hợp lệ và dữ liệu đã được khởi tạo (không phải locator `NULL`). Một số tình huống có thể cần dùng `DBMS_LOB.OPEN`/`CLOSE` để tối ưu thao tác liên tiếp hoặc xử lý index đặc thù; không tự thêm chúng như quy tắc bắt buộc cho mọi lệnh.

## 5. `NCLOB`: văn bản với national character set

`NCLOB` có mục tiêu tương tự CLOB nhưng dùng **national character set** được cấu hình cho database, thường là `AL16UTF16` trong những môi trường Oracle phổ biến. National character set áp dụng cho `NCHAR`, `NVARCHAR2` và `NCLOB`.

Kiểm tra hai thông số character set ở database (quyền xem có thể phụ thuộc cấu hình):

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET')
ORDER BY parameter;
```

Ví dụ kết quả:

```text
NLS_CHARACTERSET       AL32UTF8
NLS_NCHAR_CHARACTERSET AL16UTF16
```

Đây chỉ là **ví dụ**, không được giả định mọi database đều cùng hai giá trị này. Nếu database character set vốn là AL32UTF8 và ứng dụng có Unicode đúng chuẩn, **CLOB thường đáp ứng nhu cầu lưu tiếng Việt, tiếng Nhật, emoji và văn bản đa ngôn ngữ**. Dùng NCLOB chỉ khi có lý do mô hình dữ liệu hoặc tích hợp gắn với national character set.

### 5.1. Khai báo và chuyển đổi

```sql
CREATE TABLE lab_translations (
    translation_id NUMBER PRIMARY KEY,
    locale_code    VARCHAR2(20),
    text_national  NCLOB
);

INSERT INTO lab_translations (translation_id, locale_code, text_national)
VALUES (1, 'vi-VN', TO_NCLOB('Xin chào Oracle'));

COMMIT;
```

`TO_NCLOB` chuyển giá trị được hỗ trợ sang NCLOB. Nếu literal/ứng dụng đã bị mất ký tự **trước khi conversion** vì cấu hình client/database character set, chuyển sang NCLOB không thể khôi phục ký tự đã hỏng. Cần bảo đảm client, driver, connection và encoding đầu vào đúng ngay từ đầu.

Trong SQL cũng có **national character literal** với tiền tố `N'...'`, nhưng cách literal được chuyển giữa client character set và national character set cần được hiểu theo cấu hình Oracle. Dữ liệu Unicode dài nên truyền qua **bind parameter** thay vì ghép literal vào SQL string.

### 5.2. Khác biệt thực tế giữa CLOB và NCLOB

| Câu hỏi | `CLOB` | `NCLOB` |
| --- | --- | --- |
| Character set lưu nội dung | Database character set | National character set |
| Lưu Unicode trong AL32UTF8 database? | Có | Có |
| Khi tích hợp hệ thống đang khai báo NCHAR/NVARCHAR2/NCLOB? | Có thể cần chuyển đổi | Đồng nhất hơn với mô hình national character set |
| Dùng để chứa PDF/ZIP/PNG? | Không | Không |
| Độ dài trong ứng dụng Java | Cần xác nhận API/driver và ký tự | Tương tự, chú ý national-character APIs |
| Chọn mặc định cho hệ thống Unicode mới dùng AL32UTF8 | Thường hợp lý | Chỉ nên chọn khi có lý do rõ ràng |

**Lưu ý kỹ thuật:** các phiên bản JDBC hỗ trợ các phương thức liên quan **national character types** như `setNClob` và `getNClob`. Khi dùng generic `setCharacterStream`, `setString` hoặc `setNString`, cần kiểm tra ánh xạ mà Oracle JDBC driver hỗ trợ và cách framework ORM sử dụng type. Không suy đoán rằng mọi ORM sẽ tự chọn national LOB chỉ dựa trên kiểu Java `String`.

## 6. `BLOB`: byte nhị phân nằm trong database

**`BLOB` không gắn nghĩa character set.** Nếu một ảnh PNG có byte đầu `89 50 4E 47 ...`, các byte đó phải được giữ nguyên. Không chuyển một BLOB nhị phân thành `VARCHAR2` rồi encode/decode tùy ý vì có thể gây hỏng dữ liệu.

Ví dụ các loại dữ liệu phù hợp:

- File ảnh JPEG/PNG, tài liệu PDF và file ZIP.
- Đầu ra nhị phân của một công cụ xuất dữ liệu.
- Bản ghi âm/video nhỏ hoặc trung bình khi yêu cầu ứng dụng lưu nội dung trong DB.
- Payload byte cần transaction và backup cùng dữ liệu nghiệp vụ.

Tuy nhiên, việc lưu file rất lớn trong database hay object storage bên ngoài là **quyết định kiến trúc**: cần xét kích thước, lưu lượng tải xuống, backup/restore, chi phí storage, caching, CDN, vòng đời dữ liệu và phân quyền. `BLOB` đúng về kiểu dữ liệu không có nghĩa Oracle luôn là nơi lưu mọi media lớn tối ưu.

### 6.1. Khai báo và chèn một BLOB nhỏ

```sql
CREATE TABLE lab_binary_files (
    file_id      NUMBER PRIMARY KEY,
    file_name    VARCHAR2(255 CHAR) NOT NULL,
    media_type   VARCHAR2(100 CHAR),
    file_bytes   BLOB
);

-- Chuỗi hex chỉ minh họa byte: 0x25 0x50 0x44 0x46...
INSERT INTO lab_binary_files (file_id, file_name, media_type, file_bytes)
VALUES (
    1,
    'example.bin',
    'application/octet-stream',
    TO_BLOB(HEXTORAW('255044462D312E37'))
);

COMMIT;
```

Các byte mẫu trên bắt đầu giống phần đầu một định dạng PDF, nhưng **không phải tệp PDF hợp lệ hoàn chỉnh**. Trường `MEDIA_TYPE` và `FILE_NAME` là metadata ứng dụng; Oracle không xác thực nội dung BLOB chỉ dựa trên chuỗi MIME type do client cung cấp.

Đọc số byte:

```sql
SELECT
    file_id,
    file_name,
    DBMS_LOB.GETLENGTH(file_bytes) AS file_size_bytes,
    RAWTOHEX(DBMS_LOB.SUBSTR(file_bytes, 8, 1)) AS first_eight_bytes
FROM lab_binary_files;
```

Đối với BLOB, `DBMS_LOB.GETLENGTH` trả độ dài theo byte. `DBMS_LOB.SUBSTR` trả về một giá trị kiểu RAW, vì vậy `RAWTOHEX` giúp hiển thị trích đoạn dạng hex để chẩn đoán; không phải cách xuất toàn bộ file nhị phân lớn.

### 6.2. Thêm dữ liệu nhị phân qua `DBMS_LOB`

```sql
DECLARE
    l_blob BLOB;
    l_raw  RAW(100) := HEXTORAW('01020304AABBCCDD');
BEGIN
    SELECT file_bytes
      INTO l_blob
      FROM lab_binary_files
     WHERE file_id = 1
       FOR UPDATE;

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_blob,
        amount  => UTL_RAW.LENGTH(l_raw),
        buffer  => l_raw
    );

    COMMIT;
END;
/
```

`UTL_RAW.LENGTH` đo số **byte** trong RAW. Đối với dữ liệu lớn từ ứng dụng, nên stream theo từng phần bằng API driver, tránh dồn toàn bộ tệp vào `RAW` hoặc mảng byte cỡ rất lớn trong bộ nhớ Java.

### 6.3. BLOB và mã hóa ký tự

Không gọi `UTL_RAW.CAST_TO_VARCHAR2` cho một BLOB PDF/ZIP bất kỳ rồi kỳ vọng ra văn bản đọc được. Nếu BLOB **thật sự lưu text đã mã hóa UTF-8**, ứng dụng phải biết encoding và giải mã đúng; một file nhị phân nói chung không có nghĩa là văn bản. Ngược lại, nếu nội dung nghiệp vụ là **văn bản cần thao tác bằng hàm SQL dạng character**, `CLOB` thường là lựa chọn rõ nghĩa hơn.

## 7. `BFILE`: tham chiếu tới tệp ở ngoài database

**`BFILE` không chứa toàn bộ byte của file trong datafile**. Nó giữ locator tạo từ hai thành phần:

1. **Oracle DIRECTORY object:** tên logic của một thư mục OS được DBA khai báo.
2. **Tên file:** tên tệp trong thư mục đó.

Sơ đồ:

```text
TABLE LAB_EXTERNAL_DOCS
  DOC_ID = 1
  ATTACHMENT = BFILENAME('LAB_BFILE_DIR', 'manual.pdf')
                           |
                           v
ORACLE DIRECTORY OBJECT LAB_BFILE_DIR
  DIRECTORY_PATH = /srv/oracle-lab/files
                           |
                           v
DB SERVER FILESYSTEM
  /srv/oracle-lab/files/manual.pdf
                           |
                           v
Oracle database process đọc nội dung file
  bằng quyền OS + quyền DIRECTORY phù hợp
```

**Đường dẫn là của máy chạy Oracle Database server, không phải laptop mở SQL Developer hoặc chương trình Java.** Nếu app chạy trên máy khác, `BFILENAME` không thể tự tham chiếu thư mục `C:\Downloads` của client trừ khi đó thực sự là storage mà Oracle server được cấu hình và cấp quyền truy cập.

### 7.1. Tạo DIRECTORY: công việc của DBA

Giả sử DBA đã chuẩn bị thư mục `/srv/oracle-lab/files` và đặt file `manual.pdf` trên **DB server**. Người quản trị có đặc quyền phù hợp có thể cấu hình:

```sql
-- Chỉ DBA/người có quyền CREATE ANY DIRECTORY thực hiện,
-- sau khi đã chuẩn bị thư mục OS và quyền đọc file.
CREATE OR REPLACE DIRECTORY lab_bfile_dir
AS '/srv/oracle-lab/files';

GRANT READ ON DIRECTORY lab_bfile_dir TO lab_student;
```

Chạy `CREATE DIRECTORY` **không tạo thư mục vật lý và không copy file**. Người dùng Oracle cũng cần quyền `READ` trên DIRECTORY; tiến trình database ở mức OS phải thực sự đọc được đường dẫn và file. Không cấp quyền directory rộng cho mọi user nếu không có nhu cầu.

Nếu bài thực hành không có quyền DBA, **không cần tự tạo DIRECTORY**. Hãy sử dụng directory object đã được giảng viên hoặc DBA cấp và ghi nhận tên thật của nó.

### 7.2. Tạo bảng và lưu locator BFILE

Trong schema thực hành đã được cấp quyền:

```sql
CREATE TABLE lab_external_docs (
    doc_id     NUMBER PRIMARY KEY,
    doc_title  VARCHAR2(200 CHAR),
    attachment BFILE
);

INSERT INTO lab_external_docs (doc_id, doc_title, attachment)
VALUES (
    1,
    'Tài liệu PDF trên DB server',
    BFILENAME('LAB_BFILE_DIR', 'manual.pdf')
);

COMMIT;
```

`BFILENAME` tạo locator theo **tên DIRECTORY object** và tên file. Nó **không bắt buộc mở file hoặc kiểm tra tồn tại ngay lúc chèn**: locator có thể được lưu dù file không có trên disk. Khi thao tác đọc thực tế, phải kiểm tra sự hiện diện của file và quyền truy cập.

Giá trị BFILE locator trong row có thể được đổi bằng `UPDATE` hoặc đặt `NULL`, nhưng không có cú pháp LOB nào cho phép sửa byte nội dung của `manual.pdf` thông qua BFILE như một BLOB.

### 7.3. Kiểm tra file có tồn tại và đọc kích thước

```sql
DECLARE
    l_file BFILE;
    l_size NUMBER;
BEGIN
    SELECT attachment
      INTO l_file
      FROM lab_external_docs
     WHERE doc_id = 1;

    IF DBMS_LOB.FILEEXISTS(l_file) = 1 THEN
        DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);

        l_size := DBMS_LOB.GETLENGTH(l_file);
        DBMS_OUTPUT.PUT_LINE('Kich thuoc: ' || l_size || ' bytes');

        DBMS_LOB.FILECLOSE(l_file);
    ELSE
        DBMS_OUTPUT.PUT_LINE('Khong thay file hoac khong truy cap duoc.');
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
```

Đây là minh họa PL/SQL, cần bật hiển thị `DBMS_OUTPUT` trong client. Việc mở BFILE và lấy kích thước có thể lỗi nếu directory không được cấp quyền, đường dẫn OS không tồn tại, file bị xóa/đổi tên hoặc không thể mở. Mẫu exception trên đóng file nếu đã mở rồi ném lại lỗi; ứng dụng thực tế phải xử lý các tình huống null locator và lỗi hệ điều hành theo chính sách riêng.

### 7.4. Khi nào không nên dùng BFILE?

- Ứng dụng phải **upload, cập nhật hoặc xóa nội dung** bằng transaction Oracle.
- Muốn dữ liệu được **backup/restore cùng database** mà không triển khai quy trình sao lưu tệp ngoài.
- File nằm trên máy của end user hoặc một cloud object store mà Oracle server không nhìn thấy như filesystem thích hợp.
- Cần kiểm soát phiên bản nội dung cùng row theo cơ chế nhất quán của database.
- Cần bảo đảm atomicity giữa metadata row và byte trong file.

Trong những trường hợp đó, dùng **BLOB** hoặc một kiến trúc lưu object bên ngoài bằng URL/object key cùng cơ chế đồng bộ/backup rõ ràng thường thích hợp hơn. **BFILE không phải API chung để Oracle kết nối trực tiếp tới S3/GCS hay HTTP URL**: nó gắn với DIRECTORY và tệp trên filesystem mà DB server nhìn thấy.

## 8. Ví dụ tổng hợp bốn kiểu trên một bảng

Để quan sát các kiểu cạnh nhau, tạo bảng lab trong một schema riêng:

```sql
CREATE TABLE lab_lob_documents (
    document_id      NUMBER PRIMARY KEY,
    document_title   VARCHAR2(200 CHAR) NOT NULL,
    body_text        CLOB,
    body_national    NCLOB,
    content_binary   BLOB,
    external_file    BFILE,
    created_at       TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

Chèn giá trị minh họa, với BFILE locator chỉ có ý nghĩa khi DIRECTORY tương ứng đã tồn tại:

```sql
INSERT INTO lab_lob_documents (
    document_id, document_title,
    body_text, body_national, content_binary
)
VALUES (
    1,
    'Tai lieu mau',
    TO_CLOB('Đây là văn bản CLOB có dấu tiếng Việt.'),
    TO_NCLOB('Văn bản NCLOB dùng national character set.'),
    TO_BLOB(HEXTORAW('010203040506'))
);

COMMIT;
```

Truy vấn metadata kiểu dữ liệu:

```sql
SELECT column_id, column_name, data_type, nullable
FROM user_tab_columns
WHERE table_name = 'LAB_LOB_DOCUMENTS'
ORDER BY column_id;
```

Kết quả sẽ cho thấy `BODY_TEXT` là `CLOB`, `BODY_NATIONAL` là `NCLOB`, `CONTENT_BINARY` là `BLOB`, `EXTERNAL_FILE` là `BFILE`. Cột BFILE hiện `NULL` trong hàng được chèn ở trên; muốn gắn locator, có thể dùng một DIRECTORY đã được DBA cấu hình:

```sql
-- Chỉ chạy nếu LAB_BFILE_DIR đã tồn tại
-- và có đúng quyền truy cập với file trên DB server.
UPDATE lab_lob_documents
SET external_file = BFILENAME('LAB_BFILE_DIR', 'manual.pdf')
WHERE document_id = 1;

COMMIT;
```

Đọc độ dài nội dung internal LOB:

```sql
SELECT
    document_id,
    DBMS_LOB.GETLENGTH(body_text)      AS clob_length,
    DBMS_LOB.GETLENGTH(body_national)  AS nclob_length,
    DBMS_LOB.GETLENGTH(content_binary) AS blob_bytes
FROM lab_lob_documents;
```

**Cách đọc kết quả:** độ dài CLOB/NCLOB được hiểu theo đơn vị ký tự của API Oracle; BLOB theo byte. Dữ liệu Unicode có ký tự nhiều byte khiến số byte UTF-8 không bằng số ký tự. Đừng so trực tiếp `CLOB_LENGTH` với `BLOB_BYTES` rồi suy ra dữ liệu nào “lớn hơn về bộ nhớ”.

## 9. `NULL` khác LOB rỗng

`NULL` nghĩa là **không có giá trị LOB locator/giá trị LOB** tại cột; một **empty LOB** tồn tại nhưng có độ dài bằng 0. Phân biệt này rất quan trọng khi ứng dụng muốn bổ sung dữ liệu.

```sql
INSERT INTO lab_articles (article_id, title, body)
VALUES (2, 'Chưa có nội dung', NULL);

INSERT INTO lab_articles (article_id, title, body)
VALUES (3, 'Nội dung rỗng', EMPTY_CLOB());

COMMIT;

SELECT
    article_id,
    CASE WHEN body IS NULL THEN 'NULL' ELSE 'NOT NULL' END AS lob_state,
    DBMS_LOB.GETLENGTH(body) AS lob_length
FROM lab_articles
WHERE article_id IN (2, 3)
ORDER BY article_id;
```

Kỳ vọng:

| ARTICLE_ID | LOB_STATE | LOB_LENGTH |
| --- | --- | --- |
| 2 | `NULL` | `NULL` |
| 3 | `NOT NULL` | `0` |

Với BLOB, có hàm `EMPTY_BLOB()`. Đối với NCLOB, nên khởi tạo bằng một **giá trị NCLOB rỗng phù hợp với API/type conversion được hỗ trợ**, tránh tự giả định một tên hàm `EMPTY_NCLOB` tồn tại tương tự. BFILE là locator tới tệp OS, không có khái niệm nội dung rỗng được Oracle tạo bằng một `EMPTY_BFILE` function.

Nếu một cột internal LOB đang `NULL`, hãy cập nhật nó thành LOB rỗng hoặc một LOB hợp lệ trước khi gọi một số API chỉnh sửa yêu cầu locator đã khởi tạo. `NULL`, empty LOB và chuỗi chỉ có ký tự khoảng trắng khác nhau ở ngữ nghĩa ứng dụng.

## 10. SecureFiles, BasicFiles và cấu hình storage

Oracle có hai kiến trúc quản lý internal LOB nổi bật:

- **BasicFiles LOB:** cơ chế LOB truyền thống, xuất hiện trong các hệ thống hoặc dữ liệu cũ.
- **SecureFiles LOB:** cơ chế LOB hiện đại với nhiều khả năng quản lý/lưu trữ nâng cao và tối ưu I/O theo tính năng được hỗ trợ.

**SecureFiles không có nghĩa “file nhạy cảm được tự mã hóa”.** Các tính năng **compression, deduplication, encryption** là những lựa chọn cấu hình cụ thể; tình trạng hỗ trợ, quyền sử dụng/licensing và điều kiện storage phụ thuộc release/edition. Không mặc định bật một tùy chọn nâng cao chỉ vì thấy kiểu SecureFiles.

### 10.1. LOB segment và tùy chọn lưu trong row

Ví dụ cấu hình minh họa với bảng CLOB:

```sql
CREATE TABLE lab_secure_articles (
    article_id NUMBER PRIMARY KEY,
    body       CLOB
)
LOB (body) STORE AS SECUREFILE (
    ENABLE STORAGE IN ROW
    NOCACHE
    LOGGING
);
```

**Điều kiện:** tablespace/segment-space management và phiên bản Oracle phải hỗ trợ SecureFiles; môi trường legacy hoặc chính sách DBA có thể không cho phép tùy chọn này. Trên một lab đã được cấu hình sẵn, tạo `CLOB` theo mặc định của môi trường thường là lựa chọn đơn giản hơn. Ví dụ ở đây nhằm đọc hiểu DDL, không yêu cầu sửa storage policy của máy chủ.

Các khái niệm thường gặp:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `STORE AS SECUREFILE` / `BASICFILE` | Chọn kiểu lưu internal LOB khi được môi trường hỗ trợ |
| `ENABLE/DISABLE STORAGE IN ROW` | Điều khiển khả năng lưu LOB nhỏ trong row theo quy tắc Oracle |
| `CACHE` / `NOCACHE` | Quy tắc tương tác của LOB I/O với buffer cache |
| `LOGGING` / `NOLOGGING` | Chính sách ghi redo của hoạt động phù hợp; `NOLOGGING` có ảnh hưởng tới khả năng recovery |
| LOB tablespace/segment | Vùng storage riêng cho dữ liệu LOB khi out-of-row |
| Compression/deduplication/encryption | Những tính năng tùy chọn, cần đánh giá tài nguyên, tính năng và licensing |

`NOLOGGING` **không tương đương “không có redo trong mọi tình huống”** và có thể làm một số hoạt động không thể phục hồi đầy đủ nếu thiếu backup phù hợp. Không bật chỉ để tăng tốc mà bỏ qua yêu cầu recovery.

### 10.2. Xem LOB metadata qua dictionary

Trong schema sở hữu bảng:

```sql
SELECT
    table_name,
    column_name,
    segment_name,
    tablespace_name,
    securefile,
    in_row,
    cache,
    logging
FROM user_lobs
WHERE table_name IN (
    'LAB_LOB_DOCUMENTS',
    'LAB_ARTICLES',
    'LAB_SECURE_ARTICLES'
)
ORDER BY table_name, column_name;
```

`USER_LOBS` chứa thông tin quản lý các **internal LOB columns**, LOB segment và thuộc tính storage; **`BFILE` không được quản lý như một LOB segment nội bộ của database**, vì nội dung nằm ngoài DB. Để tra kiểu dữ liệu cột BFILE, dùng `USER_TAB_COLUMNS`; để xem DIRECTORY object, dùng các view directory theo quyền phù hợp.

Cột `SEGMENT_NAME` là metadata về LOB segment, nhưng không có nghĩa mỗi LOB nhỏ chắc chắn đã cấp phát sẵn tất cả các block out-of-row. Với bảng mới, cơ chế deferred segment creation và cấu hình storage có thể khiến segment chưa được cấp phát cho tới khi cần.

### 10.3. LOB và undo/redo

Internal LOB có cơ chế **transactional read consistency**, recovery và cách quản lý các phiên bản nội dung phụ thuộc SecureFiles/BasicFiles, logging và cấu hình retention. Thao tác cập nhật một LOB lớn có thể tạo lưu lượng redo/undo hoặc phiên bản LOB đáng kể; chi phí backup cũng tăng theo dữ liệu thực tế.

BFILE không có transaction log cho các thay đổi ở file OS; nếu tiến trình khác sửa `manual.pdf` giữa lúc hai câu SQL đọc BFILE, Oracle không bảo đảm nội dung file ngoài sẽ tuân theo snapshot consistency của row trong database.

## 11. Đọc/ghi LOB trong PL/SQL: tránh giới hạn của chuỗi thường

`DBMS_LOB` cung cấp những API phổ biến:

| API | Vai trò khái quát | Kiểu phù hợp |
| --- | --- | --- |
| `GETLENGTH` | Lấy độ dài | CLOB, NCLOB, BLOB, BFILE với điều kiện mở/đọc phù hợp |
| `SUBSTR` | Lấy đoạn nhỏ từ một offset | CLOB, NCLOB, BLOB; BFILE theo API và trạng thái file phù hợp |
| `INSTR` | Tìm một pattern | Character LOB hoặc binary LOB với pattern đúng kiểu |
| `READ` | Đọc từng đoạn vào buffer | Internal LOB, BFILE qua cơ chế read-only |
| `WRITE` / `WRITEAPPEND` | Ghi vào vị trí hoặc nối thêm | **Internal LOB** được phép sửa |
| `APPEND` | Nối nội dung của một LOB sang LOB khác | Internal LOB với cặp kiểu phù hợp |
| `CREATETEMPORARY` / `FREETEMPORARY` | Tạo và giải phóng temporary LOB | Internal LOB tạm |
| `FILEEXISTS` / `FILEOPEN` / `FILECLOSE` | Kiểm tra, mở và đóng file ngoài | **BFILE** |

Không cần tải toàn bộ tệp vào RAM để đọc: nếu chỉ cần 4.096 byte đầu của BLOB, hãy đọc một đoạn:

```sql
DECLARE
    l_blob BLOB;
    l_part RAW(4096);
BEGIN
    SELECT file_bytes
    INTO l_blob
    FROM lab_binary_files
    WHERE file_id = 1;

    l_part := DBMS_LOB.SUBSTR(l_blob, 4096, 1);
    DBMS_OUTPUT.PUT_LINE('Do dai doan doc: ' || UTL_RAW.LENGTH(l_part));
END;
/
```

Ví dụ sau tạo **temporary CLOB**, nối nội dung và giải phóng:

```sql
DECLARE
    l_temp  CLOB;
    l_text  VARCHAR2(100) := 'Văn bản tạm dùng trong phiên xử lý.';
BEGIN
    DBMS_LOB.CREATETEMPORARY(l_temp, TRUE);
    DBMS_LOB.WRITEAPPEND(l_temp, LENGTH(l_text), l_text);
    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_temp));
    DBMS_LOB.FREETEMPORARY(l_temp);
END;
/
```

Trong xử lý thực tế, cần giải phóng temporary LOB khi không sử dụng và quản lý trường hợp exception. Nếu giữ locator tạm quá lâu trong kết nối dùng connection pool, tài nguyên tạm của session có thể tăng ngoài dự kiến. Temporary LOB không phải đối tượng bảng ứng dụng lưu bền vững chỉ vì đã gọi `CREATETEMPORARY`.

## 12. Java JDBC: stream text và binary đúng cách

Trong ứng dụng Java, kiểu nào dùng để truyền nội dung phụ thuộc API JDBC:

| Oracle type | API JDBC thường dùng | Dữ liệu Java |
| --- | --- | --- |
| `CLOB` | `PreparedStatement.setCharacterStream` / `setClob`, `ResultSet.getCharacterStream` / `getClob` | `Reader`, `Clob` |
| `NCLOB` | `setNCharacterStream` / `setNClob`, `getNCharacterStream` / `getNClob` | `Reader`, `NClob` |
| `BLOB` | `setBinaryStream` / `setBlob`, `getBinaryStream` / `getBlob` | `InputStream`, `Blob` |
| `BFILE` | API Oracle JDBC chuyên biệt hoặc cơ chế được driver hỗ trợ để lấy locator/read-only | File ở DB server, không phải stream upload trực tiếp từ máy khách |

Tùy Oracle JDBC driver và framework JPA/JDBC sử dụng, ánh xạ chi tiết có thể khác. Với hệ thống cần xử lý file lớn, ưu tiên **stream**, đừng luôn gọi `ResultSet.getBytes` cho file nhiều trăm MB.

### 12.1. Upload CLOB và BLOB bằng stream

Ví dụ Java dùng schema lab `LAB_LOB_DOCUMENTS` đã tạo ở mục 8. Giả sử file `content.txt` là UTF-8 và `attachment.bin` là dữ liệu nhị phân:

```java
import java.io.InputStream;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;

public class LobUploadExample {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("ORACLE_JDBC_URL");
        String user = System.getenv("ORACLE_DB_USER");
        String password = System.getenv("ORACLE_DB_PASSWORD");

        Path textPath = Path.of("content.txt");
        Path binaryPath = Path.of("attachment.bin");

        String sql = """
            INSERT INTO lab_lob_documents (
                document_id, document_title, body_text, content_binary
            ) VALUES (?, ?, ?, ?)
            """;

        try (Connection connection =
                 DriverManager.getConnection(url, user, password);
             Reader textReader =
                 Files.newBufferedReader(textPath, StandardCharsets.UTF_8);
             InputStream binaryStream = Files.newInputStream(binaryPath);
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, 1001L);
            statement.setString(2, "Tài liệu được upload bằng JDBC");
            statement.setCharacterStream(3, textReader);
            statement.setBinaryStream(4, binaryStream, Files.size(binaryPath));
            statement.executeUpdate();
        }
    }
}
```

Các biến môi trường cần do cấu hình thực thi cung cấp; ví dụ JDBC URL cho một PDB có thể có dạng `jdbc:oracle:thin:@//localhost:1521/FREEPDB1`, nhưng phải thay bằng service thật. Không lưu mật khẩu cứng trong mã nguồn. Với driver/framework cụ thể, kiểm tra khả năng hỗ trợ overload không khai báo độ dài của `setCharacterStream` và các yêu cầu về kích thước stream.

**Về commit:** JDBC mặc định thường ở chế độ auto-commit khi tạo connection, nhưng ứng dụng thực tế có thể tắt auto-commit hoặc được transaction manager quản lý. Ví dụ trên không sửa trạng thái auto-commit; nếu bạn tự tắt, phải gọi `commit()` sau khi `executeUpdate()` thành công hoặc để transaction manager xử lý.

### 12.2. Download BLOB qua stream

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class LobDownloadExample {
    public static void main(String[] args) throws Exception {
        String sql = """
            SELECT content_binary
            FROM lab_lob_documents
            WHERE document_id = ?
            """;

        try (Connection connection = DriverManager.getConnection(
                 System.getenv("ORACLE_JDBC_URL"),
                 System.getenv("ORACLE_DB_USER"),
                 System.getenv("ORACLE_DB_PASSWORD"));
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, 1001L);
            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    throw new IllegalStateException("Không tìm thấy tài liệu");
                }

                try (InputStream content = rows.getBinaryStream(1);
                     OutputStream output =
                         Files.newOutputStream(Path.of("downloaded.bin"))) {
                    if (content == null) {
                        throw new IllegalStateException("BLOB đang NULL");
                    }
                    content.transferTo(output);
                }
            }
        }
    }
}
```

Giữ **ResultSet, PreparedStatement và Connection còn mở** trong lúc đọc stream; một số driver sẽ làm locator/stream hết hiệu lực nếu đóng session trước. Đọc dữ liệu nhị phân bằng stream và đóng tài nguyên đúng cách còn giúp hạn chế sử dụng RAM.

Với NCLOB, cân nhắc các phương thức `setNCharacterStream` hoặc `setNClob` theo hỗ trợ driver. Với BFILE, mã Java phải xử lý locator đặc thù do Oracle JDBC cung cấp và quyền đọc tệp của **DB server**; gọi `setBinaryStream` để “upload vào BFILE” là sai mô hình.

### 12.3. API web phục vụ BLOB cần chú ý gì?

Khi triển khai HTTP upload/download:

- Dùng giới hạn kích thước file và chính sách quota để tránh làm đầy storage.
- Xác thực loại file bằng chính sách ứng dụng và khi cần bằng nội dung file; không tin hoàn toàn tên file hoặc `Content-Type` do client gửi.
- Stream để hạn chế RAM; đặt timeout và giới hạn thời gian đọc/ghi.
- Kiểm tra quyền truy cập từng tài liệu, nhất là endpoint download.
- Khi gửi response, đặt `Content-Type` và `Content-Disposition` phù hợp, tránh tạo lỗ hổng khi mở nội dung không tin cậy trong trình duyệt.
- Tính đến backup, kiểm tra checksum/hash, xử lý lỗi upload dở và đồng bộ metadata–binary.

LOB giải quyết bài toán **biểu diễn dữ liệu trong database**, không tự giải quyết bảo mật file upload hoặc kiến trúc nội dung phân tán.

## 13. Hiệu năng và vận hành với LOB

### 13.1. Các yếu tố ảnh hưởng hiệu năng

| Yếu tố | Tác động cần cân nhắc |
| --- | --- |
| Kích thước LOB trung bình/tối đa | Dung lượng LOB segment, redo, backup, truyền mạng, cache |
| Giá trị in-row hay out-of-row | Có thể ảnh hưởng số lần truy cập block và độ rộng row của bảng chính |
| `CACHE` / `NOCACHE` | Cách LOB I/O sử dụng bộ nhớ đệm |
| SecureFiles/BasicFiles | Khả năng storage, tính năng quản trị và overhead khác nhau |
| Compression/deduplication | Có thể tiết kiệm dung lượng nhưng tốn CPU và phụ thuộc khả năng hỗ trợ/quyền sử dụng |
| Encryption | Bảo vệ dữ liệu lưu trữ khi cấu hình phù hợp, có chi phí và yêu cầu quản lý khóa |
| Thao tác nguyên LOB hay stream từng phần | Ảnh hưởng mạnh tới RAM ứng dụng và kích thước request/response |
| Kiểu truy vấn và index | Full-text/JSON search có thể cần công cụ/index chuyên dụng; không dùng index B-tree trên toàn bộ LOB như cột khóa ngắn |
| Tần suất update giá trị lớn | Redo, retention/LOB versioning, dung lượng tạm, throughput |

### 13.2. Không nên `SELECT *` để tải LOB vô điều kiện

Với màn hình danh sách tài liệu, nhiều ứng dụng chỉ cần `ID`, `TITLE`, `CREATED_AT` và kích thước nội dung. Truy vấn:

```sql
SELECT document_id,
       document_title,
       created_at,
       DBMS_LOB.GETLENGTH(content_binary) AS byte_count
FROM lab_lob_documents
ORDER BY created_at DESC;
```

Khi người dùng chọn một tài liệu, mới tải nội dung BLOB ở thao tác riêng. Điều này tránh việc một màn hình danh sách phải xử lý nhiều LOB cùng lúc. LOB locator và driver có thể lazy-load theo cơ chế riêng, nhưng tách API metadata/nội dung vẫn tạo hợp đồng rõ hơn.

### 13.3. Backup và khôi phục

Với **internal LOB**, dữ liệu nằm trong database và được quản lý theo phương án backup/recovery Oracle tương ứng. Một bản backup database đầy đủ hợp lệ cần bao gồm các thành phần database theo chiến lược RMAN/backup đã chọn; chỉ export vài hàng metadata mà không xuất LOB có thể không đủ.

Với **BFILE**, cần **kế hoạch backup tệp OS độc lập**, cùng cơ chế bảo đảm file còn đúng pathname, quyền, checksum và thời điểm khi restore database. Khôi phục row có locator BFILE thành công **không đảm bảo file nó trỏ tới vẫn tồn tại**.

Khi tách BLOB sang object storage (S3 hoặc tương đương), tình huống tương tự: database transaction không tự atomically commit cùng một object store trừ khi ứng dụng thiết kế giao thức và quy trình bù/đối soát riêng.

## 14. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Văn bản tiếng Việt bắt buộc dùng NCLOB.” | CLOB với database character set Unicode như `AL32UTF8` đã có thể lưu tiếng Việt. |
| “BLOB là chuỗi lớn có thể tìm bằng LIKE.” | BLOB là byte; nếu bản chất là text, hãy chọn CLOB hoặc xác định encoding và xử lý rõ ràng. |
| “CLOB luôn chiếm chỗ ngay trong row của bảng.” | Oracle có thể lưu internal LOB in-row hoặc out-of-row qua LOB segment. |
| “BFILE chứa file bên trong datafile Oracle.” | BFILE chỉ lưu locator; byte thực ở filesystem của DB server. |
| “CREATE DIRECTORY sẽ tự tạo folder trên Linux.” | Lệnh chỉ tạo Oracle object trỏ tới path; DBA/OS phải chuẩn bị thư mục và quyền riêng. |
| “BFILENAME bảo đảm file đang tồn tại.” | Nó tạo locator; cần kiểm tra sự hiện diện và khả năng đọc của file khi truy cập. |
| “Có COMMIT là Oracle đã sao lưu file BFILE.” | Transaction chỉ ghi thay đổi locator trong row; file OS cần backup riêng. |
| “BFILE có thể UPDATE nội dung như BLOB.” | BFILE là nội dung chỉ đọc qua Oracle; muốn thay byte phải dùng cơ chế ngoài database. |
| “Độ dài CLOB và BLOB cùng một đơn vị.” | CLOB/NCLOB đo theo ký tự của API; BLOB theo byte. |
| “NULL và EMPTY_CLOB() giống nhau.” | NULL không có giá trị LOB; empty CLOB là LOB tồn tại với độ dài bằng 0. |
| “LOB locator là toàn bộ byte của file.” | Locator là tham chiếu; dùng stream/API để lấy hoặc sửa dữ liệu. |
| “SecureFiles nghĩa là đã mã hóa và backup an toàn.” | Encryption/backup là cấu hình và quy trình riêng; tên SecureFiles không tự bảo đảm chúng. |
| “Cứ tăng RAM là có thể tải mọi BLOB bằng getBytes().” | Đọc toàn bộ file vào RAM vẫn tạo rủi ro OOM và tăng áp lực GC; ưu tiên stream. |
| “Index B-tree trên toàn CLOB dùng như index VARCHAR2.” | LOB có giới hạn về việc index trực tiếp; full-text và tìm kiếm nâng cao cần cơ chế phù hợp. |

## 15. Bài tập thực hành

### Bài 1 — Chọn kiểu dữ liệu

Với mỗi mục sau, hãy chọn `CLOB`, `NCLOB`, `BLOB` hoặc `BFILE` và ghi rõ lý do:

1. Một bài hướng dẫn 200 KB cần tìm đoạn văn bản theo từ khóa.
2. Ảnh PNG 2 MB phải được commit cùng bản ghi hồ sơ và phục hồi bằng backup DB.
3. Tệp PDF 50 MB đã có trong thư mục của DB server, chỉ cần Oracle đọc, chính sách backup tệp do nhóm storage đảm nhiệm.
4. Một hệ thống legacy quy định dùng Oracle national character set cho toàn bộ nội dung văn bản dài.
5. File ZIP mã hóa không có ý nghĩa văn bản.

**Gợi ý:** (1) CLOB, đồng thời đánh giá tìm kiếm full-text; (2) BLOB; (3) BFILE **nếu** quyền/path ổn định và chấp nhận mô hình ngoài transaction; (4) NCLOB; (5) BLOB. Khi cần lưu file ngoài DB không gắn với filesystem của Oracle, có thể dùng object storage + metadata thay vì BFILE.

### Bài 2 — Quan sát NULL và empty LOB

Tạo hai hàng trong `LAB_ARTICLES` theo mục 9; truy vấn `BODY IS NULL` và `DBMS_LOB.GETLENGTH(BODY)`. Giải thích vì sao dữ liệu rỗng và dữ liệu không tồn tại có thể cần xử lý khác nhau trong API.

### Bài 3 — Đọc metadata về LOB storage

Sau khi tạo `LAB_LOB_DOCUMENTS`:

```sql
SELECT column_name, data_type
FROM user_tab_columns
WHERE table_name = 'LAB_LOB_DOCUMENTS'
ORDER BY column_id;

SELECT column_name, segment_name, securefile, in_row
FROM user_lobs
WHERE table_name = 'LAB_LOB_DOCUMENTS'
ORDER BY column_name;
```

Giải thích vì sao cột BFILE xuất hiện ở `USER_TAB_COLUMNS` nhưng không có một LOB data segment nội bộ tương ứng trong `USER_LOBS`.

### Bài 4 — Viết PL/SQL thao tác từng loại LOB

1. Với CLOB: dùng `DBMS_LOB.SUBSTR` lấy đoạn đầu và `DBMS_LOB.WRITEAPPEND` nối một đoạn mới.
2. Với BLOB: dùng `DBMS_LOB.GETLENGTH` và `RAWTOHEX(DBMS_LOB.SUBSTR(...))` để kiểm tra vài byte đầu.
3. Với NCLOB: chèn văn bản nhiều ngôn ngữ và đọc bằng đúng API character LOB.
4. Với BFILE: nhận locator do DBA cấp, dùng `DBMS_LOB.FILEEXISTS`; nếu có file, mở read-only, đọc kích thước và đóng lại.

**Yêu cầu:** chỉ thao tác trên bảng/schema lab của mình; không cần và không được sửa tệp OS bằng BFILE.

### Bài 5 — Phân tích một API upload tài liệu

Ứng dụng Spring Boot nhận file từ người dùng. Hãy mô tả hai phương án:

- **Phương án A:** lưu nội dung thành BLOB trong Oracle và metadata thành các cột bình thường. Chỉ ra cách transaction, backup và streaming được xử lý.
- **Phương án B:** lưu nội dung trong object storage, lưu `OBJECT_KEY`/URL và checksum trong Oracle. Mô tả cách xử lý upload thất bại giữa chừng, quyền truy cập và backup riêng.

Giải thích vì sao **BFILE không mặc nhiên là cách triển khai phương án B** nếu object storage không hiện diện như filesystem do Oracle server truy cập.

### Bài 6 — Kiểm tra giao tiếp JDBC

Viết chương trình Java dùng `setCharacterStream` để gửi file UTF-8 tới CLOB và `setBinaryStream` để gửi file binary tới BLOB. Đọc lại bằng `getCharacterStream` và `getBinaryStream`, sau đó so sánh:

- Văn bản nhận về có bảo toàn các ký tự tiếng Việt và Unicode không?
- Số byte tải về có bằng số byte tải lên không?
- Checksum của byte stream có bằng nhau không?
- Chương trình có đóng connection, statement, result set và stream ngay cả khi lỗi không?

Đối với dữ liệu nhị phân, checksum hoặc so sánh byte là bằng chứng phù hợp hơn việc in nội dung ra console.

### Dọn các đối tượng của bài lab

Chỉ chạy khi chính bạn đã tạo các bảng này, trong đúng schema thực hành:

```sql
DROP TABLE lab_articles PURGE;
DROP TABLE lab_translations PURGE;
DROP TABLE lab_binary_files PURGE;
DROP TABLE lab_external_docs PURGE;
DROP TABLE lab_lob_documents PURGE;
DROP TABLE lab_secure_articles PURGE;
```

`PURGE` bỏ qua recycle bin. Nếu không tạo một bảng nào đó, lệnh `DROP` của bảng đó sẽ báo không tồn tại; không cần thực thi toàn bộ như một script bắt buộc. **Không xóa DIRECTORY object hoặc file vật lý của người khác** chỉ vì dọn lab; đó là tài nguyên do DBA/OS quản lý riêng.

## Kết luận

`CLOB` và `NCLOB` dành cho **văn bản dài**, khác nhau ở database character set và national character set; `BLOB` dành cho **byte nhị phân** nằm trong database; `BFILE` chỉ là **tham chiếu chỉ đọc tới file trên filesystem của DB server**. Ba kiểu internal LOB có thể tham gia transaction, backup và cơ chế lưu trữ Oracle; BFILE cần quản trị path, quyền OS, tính tồn tại và backup bên ngoài.

Trong thực tế, hãy chọn theo **ngữ nghĩa dữ liệu**, không chỉ theo kích thước: text hay binary, nội dung được Oracle quản lý hay nằm ngoài, yêu cầu Unicode nào, cần đọc/ghi hay chỉ đọc, và phải phục hồi cùng transaction/backup hay không. Khi làm việc với nội dung lớn, dùng **LOB locator và streaming API** để tránh nhồi toàn bộ file vào một chuỗi hoặc mảng byte trong bộ nhớ ứng dụng.

## Tài liệu Oracle nên đọc tiếp

- [Oracle Database SecureFiles and Large Objects Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/) — kiến trúc internal/external LOB, SecureFiles/BasicFiles, locator, thao tác SQL và PL/SQL.
- [Oracle Database SQL Language Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — định nghĩa kiểu `CLOB`, `NCLOB`, `BLOB`, `BFILE`, `CREATE TABLE` và `CREATE DIRECTORY`.
- [Oracle Database PL/SQL Packages and Types Reference: DBMS_LOB](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_LOB.html) — `GETLENGTH`, `SUBSTR`, `READ`, `WRITEAPPEND` và thao tác BFILE.
- [Oracle Database JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — xử lý LOB bằng JDBC và các API stream.
- [Oracle Database Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — `USER_LOBS`, `USER_TAB_COLUMNS` và metadata LOB.

Đối với một môi trường Oracle release khác 19c, hãy đối chiếu tài liệu tương ứng về giới hạn LOB, tùy chọn SecureFiles, hàm API và chính sách quyền trước khi triển khai production.
