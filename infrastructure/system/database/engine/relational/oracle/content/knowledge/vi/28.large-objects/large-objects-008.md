# Compression, deduplication và encryption của LOB trong Oracle

## 1. Tổng quan về LOB và SecureFiles

Oracle dùng các kiểu dữ liệu LOB để lưu nội dung lớn:

- `CLOB`: dữ liệu ký tự theo database character set.
- `NCLOB`: dữ liệu ký tự theo national character set.
- `BLOB`: dữ liệu nhị phân.
- `BFILE`: locator tham chiếu đến file bên ngoài database; nội dung file không được lưu trong LOB segment và BFILE chỉ đọc.

Với CLOB, NCLOB và BLOB, Oracle lưu nội dung bằng cơ chế LOB nội bộ. Một LOB nhỏ có thể được lưu inline trong hàng nếu cấu hình cho phép; LOB lớn thường được lưu trong LOB segment riêng. Ứng dụng truy cập nội dung thông qua LOB locator hoặc các API như `DBMS_LOB`.

Khi dữ liệu lớn tăng lên, dung lượng LOB segment, I/O, backup, redo và thời gian truyền dữ liệu có thể trở thành vấn đề. Oracle SecureFiles cung cấp ba tính năng quan trọng:

- **Compression:** nén nội dung LOB để giảm dung lượng.
- **Deduplication:** tránh lưu nhiều bản sao vật lý của nội dung LOB giống nhau trong phạm vi được hỗ trợ.
- **Encryption:** mã hóa nội dung LOB để bảo vệ dữ liệu lưu trữ.

Các tính năng này có thể giảm storage hoặc tăng bảo mật, nhưng có điều kiện sử dụng, chi phí CPU, ảnh hưởng hiệu năng và yêu cầu license riêng. Không nên bật đồng loạt mà chưa hiểu dữ liệu và workload.

Bài học thuộc chương **LOB và dữ liệu lớn**, trình bày SecureFiles và BasicFiles, điều kiện tablespace, các mức compression, deduplication, mã hóa TDE, kết hợp tính năng, cú pháp tạo và thay đổi LOB, di chuyển dữ liệu hiện có, kiểm tra metadata, đo hiệu quả và các điều kiện license/feature cần xác nhận.

## 2. BasicFiles và SecureFiles

Oracle có hai cách tổ chức lưu trữ LOB nội bộ phổ biến:

| Đặc điểm | BasicFiles | SecureFiles |
|---|---|---|
| Công nghệ | LOB truyền thống | Cơ chế LOB hiện đại |
| Compression LOB | Không có SecureFiles compression | Có |
| Deduplication | Không có SecureFiles deduplication | Có |
| Encryption LOB | Không có SecureFiles LOB encryption | Có, thông qua TDE |
| Tablespace | Theo điều kiện của BasicFiles | Yêu cầu ASSM |
| Triển khai mới | Chỉ khi có lý do tương thích | Thường là lựa chọn nên đánh giá |

SecureFiles được giới thiệu từ Oracle Database 11g. Các tính năng và cú pháp chi tiết phụ thuộc phiên bản, edition và cấu hình database.

### 2.1. Vì sao cần SecureFiles?

Compression, deduplication và encryption được cung cấp như thuộc tính của SecureFiles LOB. Nếu cột LOB đang dùng BasicFiles, việc thêm từ khóa `COMPRESS`, `DEDUPLICATE` hoặc `ENCRYPT` không tự biến nó thành SecureFiles.

Khi cần các tính năng này, phải bảo đảm cột LOB được lưu bằng SecureFiles và tablespace đáp ứng điều kiện. Nếu dữ liệu hiện tại đang ở BasicFiles, cần lập kế hoạch di chuyển hoặc tái tổ chức LOB.

### 2.2. Kiểm tra loại LOB

```sql
SELECT table_name,
       column_name,
       segment_name,
       tablespace_name,
       securefile,
       compression,
       deduplication,
       encrypt
FROM user_lobs
ORDER BY table_name, column_name;
```

Các cột `SECUREFILE`, `COMPRESSION`, `DEDUPLICATION` và `ENCRYPT` cho biết loại lưu trữ và thuộc tính LOB trong schema hiện tại. Dùng `ALL_LOBS` hoặc `DBA_LOBS` khi cần xem schema khác và có quyền.

## 3. Điều kiện sử dụng SecureFiles

### 3.1. Tablespace phải dùng ASSM

SecureFiles LOB yêu cầu tablespace dùng **Automatic Segment Space Management (ASSM)**.

```sql
SELECT tablespace_name,
       segment_space_management,
       extent_management,
       status
FROM user_tablespaces
ORDER BY tablespace_name;
```

Hoặc, nếu có quyền DBA:

```sql
SELECT tablespace_name,
       segment_space_management
FROM dba_tablespaces
ORDER BY tablespace_name;
```

Giá trị cần thấy là `AUTO` ở cột `SEGMENT_SPACE_MANAGEMENT`.

Ví dụ tạo tablespace lab:

```sql
CREATE TABLESPACE lob_lab_ts
DATAFILE 'lob_lab_ts01.dbf' SIZE 500M
EXTENT MANAGEMENT LOCAL
SEGMENT SPACE MANAGEMENT AUTO;
```

Đường dẫn datafile và dung lượng phải phù hợp môi trường. Đây chỉ là cú pháp minh họa; không chạy nguyên trạng nếu chưa xác định storage location và quota.

### 3.2. Tham số DB_SECUREFILE

Tham số khởi tạo `DB_SECUREFILE` kiểm soát hành vi tạo SecureFiles LOB. Giá trị và semantics chi tiết cần kiểm tra theo phiên bản Oracle.

```sql
SHOW PARAMETER db_securefile;
```

Hoặc:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'db_securefile';
```

Các giá trị thường gặp gồm:

- `PERMITTED`: cho phép tạo SecureFiles khi được yêu cầu rõ trong DDL.
- `ALWAYS`: yêu cầu Oracle ưu tiên tạo SecureFiles theo quy tắc của tham số.
- `NEVER`: không cho phép tạo SecureFiles.
- Một số phiên bản còn có giá trị điều khiển khác như `FORCE` hoặc `IGNORE`.

Không tự thay đổi tham số này trên production. Đây là cấu hình database có thể ảnh hưởng nhiều schema; thay đổi cần quyền quản trị và phải theo quy trình vận hành.

### 3.3. Tương thích phiên bản

SecureFiles có từ Oracle Database 11g, nhưng mức compression, thuật toán, cú pháp, hỗ trợ partition và khả năng quản trị có thể thay đổi theo phiên bản.

Trước khi triển khai, xác nhận:
- Phiên bản và Release Update.
- Giá trị `COMPATIBLE`.
- Edition và các option được cấp phép.
- Tablespace có ASSM.
- `DB_SECUREFILE` cho phép SecureFiles.
- Backup, Data Pump, replication và standby hỗ trợ cấu hình cần dùng.

### 3.4. Điều kiện license

Có cú pháp SQL hoặc tạo được LOB không đồng nghĩa tổ chức đã có quyền sử dụng mọi option.

Theo mô hình cấp phép Oracle phổ biến:

| Tính năng SecureFiles | Option thường cần xác nhận |
|---|---|
| SecureFiles compression | Oracle Advanced Compression Option |
| SecureFiles deduplication | Oracle Advanced Compression Option |
| SecureFiles encryption | Oracle Advanced Security Option |
| SecureFiles cơ bản, không bật các option trên | Kiểm tra edition và điều khoản hiện hành |

Điều kiện license có thể thay đổi theo phiên bản, edition, dịch vụ cloud và hợp đồng. Hãy kiểm tra Oracle Database Licensing Information User Manual tương ứng release và hợp đồng của tổ chức trước khi bật tính năng. DBA hoặc license administrator cần xác nhận quyền sử dụng; không suy ra license từ việc DDL chạy thành công.

## 4. Compression của SecureFiles LOB

Compression nén dữ liệu LOB để giảm dung lượng. Nó thường hữu ích với văn bản, XML, JSON, log và nội dung có nhiều cấu trúc lặp.

### 4.1. Các mức compression

SecureFiles hỗ trợ các mức `LOW`, `MEDIUM` và `HIGH` trong các phiên bản tương ứng:

| Mức | Đặc điểm khái quát | Khi cân nhắc |
|---|---|---|
| `LOW` | Ưu tiên tốc độ, mức nén thường thấp hơn | Workload nhạy CPU hoặc truy cập thường xuyên |
| `MEDIUM` | Cân bằng tỷ lệ nén và CPU | Điểm bắt đầu để benchmark |
| `HIGH` | Ưu tiên tiết kiệm dung lượng, thường tiêu tốn CPU hơn | Dữ liệu lưu lâu, ít cập nhật |

Tỷ lệ nén thực tế phụ thuộc nội dung. Không có tỷ lệ phần trăm cố định cho mọi CLOB/BLOB.

### 4.2. Dữ liệu nào nén tốt?

Thường có khả năng nén tốt:
- Văn bản thuần, XML, JSON.
- Nội dung có nhiều chuỗi lặp.
- Tài liệu có cấu trúc và metadata lặp.

Thường nén kém:
- JPEG, PNG, MP4 và media đã nén.
- ZIP, GZIP và archive đã nén.
- Dữ liệu đã mã hóa trước khi đưa vào LOB.
- Dữ liệu nhị phân có entropy cao.

Nếu ứng dụng đã nén file trước khi lưu BLOB, compression thêm trong SecureFiles có thể tiết kiệm rất ít nhưng vẫn tiêu tốn CPU.

### 4.3. Tạo SecureFiles có compression

```sql
CREATE TABLE documents (
    document_id NUMBER PRIMARY KEY,
    document_name VARCHAR2(200),
    document_content BLOB
)
LOB (document_content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
);
```

`STORE AS SECUREFILE` yêu cầu Oracle lưu LOB bằng SecureFiles. `COMPRESS MEDIUM` bật compression mức MEDIUM.

Ví dụ dùng mức LOW:

```sql
CREATE TABLE text_documents (
    document_id NUMBER PRIMARY KEY,
    document_body CLOB
)
LOB (document_body) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS LOW
);
```

Hoặc mức HIGH:

```sql
CREATE TABLE archive_documents (
    document_id NUMBER PRIMARY KEY,
    document_body CLOB
)
LOB (document_body) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS HIGH
);
```

### 4.4. Đánh đổi hiệu năng

Compression có thể giảm số block cần lưu và đọc, nhưng cần CPU để nén/giải nén. Với workload cập nhật thường xuyên, LOB lớn hoặc độ trễ nghiêm ngặt, mức nén cao có thể làm tăng CPU và latency.

Hãy đo:
- Kích thước LOB trước và sau.
- CPU khi INSERT, UPDATE và SELECT.
- Thời gian đọc toàn LOB và đọc từng phần.
- Tỷ lệ cập nhật so với đọc.
- Mức độ cạnh tranh CPU của database.

## 5. Deduplication của SecureFiles LOB

Deduplication tránh lưu nhiều bản sao nội dung LOB giống nhau trong phạm vi LOB segment được hỗ trợ. Khi nhiều hàng lưu cùng nội dung, Oracle có thể dùng chung phần dữ liệu LOB thay vì tạo nhiều bản sao vật lý.

Ví dụ hệ thống quản lý tài liệu có nhiều hồ sơ cùng đính kèm một mẫu PDF. Nếu nội dung BLOB hoàn toàn giống nhau, deduplication có thể giảm dung lượng đáng kể.

### 5.1. Deduplication khác compression

| Tính năng | Compression | Deduplication |
|---|---|---|
| Cách tiết kiệm | Nén biểu diễn của dữ liệu | Tránh lưu nhiều bản sao nội dung giống nhau |
| Hiệu quả phụ thuộc | Khả năng nén của từng nội dung | Tỷ lệ LOB trùng lặp |
| Dữ liệu phù hợp | Văn bản và dữ liệu có cấu trúc lặp | File/tài liệu giống hệt nhau |
| Chi phí | CPU nén/giải nén | CPU và metadata để nhận diện/quản lý bản sao |

File khác tên nhưng byte nội dung giống nhau có thể là ứng viên dedup. Hai tài liệu chỉ giống phần lớn nội dung nhưng có một vài byte khác nhau không nhất thiết được deduplicate thành một bản duy nhất.

### 5.2. Cú pháp DEDUPLICATE

```sql
CREATE TABLE shared_documents (
    document_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    document_content BLOB
)
LOB (document_content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    DEDUPLICATE
);
```

`DEDUPLICATE` bật deduplication cho LOB segment.

Có thể kết hợp với compression:

```sql
CREATE TABLE shared_text_documents (
    document_id NUMBER PRIMARY KEY,
    document_body CLOB
)
LOB (document_body) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
    DEDUPLICATE
);
```

Khả năng kết hợp và điều kiện hỗ trợ cần được xác nhận với release đang sử dụng.

### 5.3. KEEP_DUPLICATES

Nếu muốn giữ từng bản sao LOB riêng:

```sql
CREATE TABLE private_documents (
    document_id NUMBER PRIMARY KEY,
    document_content BLOB
)
LOB (document_content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    KEEP_DUPLICATES
);
```

`KEEP_DUPLICATES` tắt deduplication cho LOB segment. Nó phù hợp khi nội dung không có nhiều bản sao hoặc khi chi phí dedup không đem lại lợi ích đáng kể.

### 5.4. Deduplication không phải backup hoặc versioning

Deduplication không tạo bản sao dự phòng và không lưu lịch sử phiên bản tài liệu. Nó là tối ưu lưu trữ. Nếu ứng dụng cần versioning, audit hoặc khôi phục phiên bản cũ, cần thiết kế dữ liệu riêng.

### 5.5. Khi nào dedup có lợi?

Phù hợp khi:
- Nhiều hàng chứa cùng file hoặc cùng nội dung.
- Dữ liệu ít thay đổi sau khi ghi.
- Có tỷ lệ duplicate cao.
- Chi phí storage lớn hơn chi phí CPU/metadata.
- Cùng một LOB segment có đủ cơ hội chia sẻ nội dung.

Có thể không đáng bật khi:
- Mỗi LOB gần như duy nhất.
- File được mã hóa riêng trước khi lưu, khiến byte nội dung khác nhau.
- Dữ liệu thường xuyên bị sửa đổi.
- Tập dữ liệu nhỏ và storage không phải vấn đề.

## 6. Encryption của SecureFiles LOB

Encryption bảo vệ nội dung LOB khi lưu trữ. SecureFiles encryption sử dụng Transparent Data Encryption (TDE), giúp Oracle mã hóa và giải mã dữ liệu trong quá trình ghi/đọc; ứng dụng thường vẫn thao tác qua SQL hoặc DBMS_LOB như trước.

### 6.1. Encryption at rest

Mục tiêu chính là bảo vệ dữ liệu khi nằm trên storage, datafile hoặc media lưu trữ.

TDE không thay thế mọi lớp bảo mật:
- Không thay thế TLS/Oracle Native Network Encryption để bảo vệ dữ liệu trên đường truyền.
- Không thay thế quyền SELECT/UPDATE và kiểm soát truy cập.
- Không ngăn người dùng database có quyền hợp lệ đọc dữ liệu qua SQL.
- Không loại bỏ yêu cầu bảo vệ wallet/keystore và backup.
- Không thay thế audit và quản lý danh tính.

### 6.2. Cú pháp ENCRYPT

```sql
CREATE TABLE confidential_documents (
    document_id NUMBER PRIMARY KEY,
    document_content BLOB
)
LOB (document_content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    ENCRYPT USING 'AES256'
);
```

`ENCRYPT` bật mã hóa LOB. `USING 'AES256'` chọn thuật toán AES 256-bit trong các phiên bản hỗ trợ. Thuật toán mặc định và tập thuật toán được hỗ trợ có thể phụ thuộc release/cấu hình; kiểm tra tài liệu đúng phiên bản.

Có thể dùng `ENCRYPT` mà không ghi thuật toán nếu chính sách database cho phép mặc định:

```sql
LOB (document_content) STORE AS SECUREFILE (
    ENCRYPT
);
```

### 6.3. Điều kiện TDE keystore

TDE cần keystore/wallet được cấu hình và khóa mã hóa được quản lý đúng. Trước khi tạo hoặc truy cập LOB mã hóa, DBA cần xác nhận:
- TDE đã được cấu hình theo kiến trúc database.
- Keystore đã được tạo và mở theo chính sách.
- Master encryption key đã được thiết lập.
- Backup và quy trình khôi phục bao gồm keystore.
- Quyền truy cập và vận hành khóa được phân tách phù hợp.

Các lệnh quản trị keystore phụ thuộc phiên bản và chính sách bảo mật. Không ghi mật khẩu wallet vào script dùng chung, source control hoặc tài liệu học tập.

### 6.4. Đổi thuật toán hoặc tắt encryption

Có thể thay đổi thuộc tính SecureFiles LOB bằng `ALTER TABLE ... MODIFY LOB` theo cú pháp và khả năng của phiên bản. Ví dụ:

```sql
ALTER TABLE confidential_documents
MODIFY LOB (document_content)
(
    ENCRYPT USING 'AES256'
);
```

Tắt encryption:

```sql
ALTER TABLE confidential_documents
MODIFY LOB (document_content)
(
    DECRYPT
);
```

Kiểm tra tài liệu Oracle cho release cụ thể, trạng thái keystore, quyền và yêu cầu di chuyển dữ liệu trước khi thực hiện trên LOB lớn. Một số thay đổi có thể cần tái tổ chức hoặc xử lý dữ liệu hiện có; không giả định thay đổi metadata luôn chuyển đổi toàn bộ dữ liệu ngay lập tức.

## 7. Kết hợp compression, deduplication và encryption

SecureFiles cho phép thiết kế LOB với nhiều thuộc tính lưu trữ, nhưng cần kiểm tra tính tương thích, license và tác động thực tế của từng kết hợp.

Ví dụ:

```sql
CREATE TABLE protected_shared_documents (
    document_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    document_content BLOB
)
LOB (document_content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
    DEDUPLICATE
    ENCRYPT USING 'AES256'
);
```

Ý nghĩa:
- `COMPRESS MEDIUM`: nén dữ liệu LOB ở mức trung bình.
- `DEDUPLICATE`: tránh lưu nhiều bản sao vật lý của nội dung giống nhau trong phạm vi được hỗ trợ.
- `ENCRYPT USING 'AES256'`: mã hóa LOB bằng thuật toán AES256 được cấu hình.

Cú pháp kết hợp cần được kiểm thử trên phiên bản, edition và cấu hình đích trước khi triển khai. Từng tính năng vẫn có yêu cầu license riêng.

### 7.1. Hiểu thứ tự xử lý ở mức khái niệm

Compression giảm biểu diễn dữ liệu; deduplication nhận diện nội dung trùng; encryption biến dữ liệu thành ciphertext. Ciphertext có entropy cao và thường không nén tốt nếu cố nén sau khi mã hóa. Oracle quản lý pipeline nội bộ của SecureFiles; không tự mã hóa file ở ứng dụng rồi kỳ vọng database tiếp tục deduplicate nội dung đã mã hóa riêng bằng các khóa/nonce khác nhau.

### 7.2. Khi nào nên kết hợp?

| Đặc điểm dữ liệu | Compression | Deduplication | Encryption |
|---|---|---|---|
| Tài liệu text giống nhau nhiều lần | Có thể hữu ích | Có thể hữu ích | Theo yêu cầu bảo mật |
| PDF giống hệt lưu cho nhiều khách hàng | Tùy mức nén của PDF | Có thể hữu ích | Theo phân loại dữ liệu |
| Ảnh JPEG hoặc video đã nén | Thường tiết kiệm ít | Có thể hữu ích nếu file trùng hoàn toàn | Theo yêu cầu bảo mật |
| File ZIP giống nhau | Thường tiết kiệm ít | Có thể hữu ích | Theo yêu cầu bảo mật |
| File đã mã hóa riêng ở ứng dụng | Thường tiết kiệm ít | Thường khó dedup nếu ciphertext khác nhau | Xem xét kiến trúc mã hóa |
| Dữ liệu duy nhất, cập nhật thường xuyên | Đo CPU và latency | Có thể không đáng | Theo yêu cầu bảo mật |

### 7.3. Encryption không thay thế phân quyền

Nếu user có quyền SELECT LOB, TDE thường giải mã trong database để user hợp lệ đọc dữ liệu. TDE chủ yếu bảo vệ dữ liệu lưu trữ; nó không phải cơ chế che dữ liệu khỏi mọi user có quyền truy vấn.

Nếu cần che một phần dữ liệu theo người dùng hoặc vai trò, cân nhắc quyền đối tượng, VPD, Data Redaction hoặc mã hóa ở tầng ứng dụng theo yêu cầu. Các giải pháp này có mục tiêu và giới hạn khác nhau.

## 8. Tạo bảng LOB SecureFiles với thuộc tính cụ thể

Ví dụ bảng quản lý hồ sơ:

```sql
CREATE TABLE customer_files (
    file_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    file_name VARCHAR2(255) NOT NULL,
    file_content BLOB,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
)
LOB (file_content) STORE AS SECUREFILE customer_files_lob (
    TABLESPACE lob_lab_ts
    ENABLE STORAGE IN ROW
    CHUNK 8192
    CACHE READS
    LOGGING
    COMPRESS MEDIUM
    DEDUPLICATE
    ENCRYPT USING 'AES256'
);
```

Giải thích:
- `STORE AS SECUREFILE`: chọn SecureFiles.
- `TABLESPACE`: vị trí LOB segment.
- `ENABLE STORAGE IN ROW`: cho phép LOB nhỏ được lưu trong hàng nếu đủ điều kiện.
- `CHUNK`: đơn vị phân bổ/đọc ghi LOB theo quy tắc lưu trữ.
- `CACHE READS`: cho phép cache thao tác đọc theo semantics của Oracle.
- `LOGGING`: ghi redo theo cấu hình logging.
- `COMPRESS MEDIUM`: bật compression.
- `DEDUPLICATE`: bật deduplication.
- `ENCRYPT USING 'AES256'`: bật encryption.

Các thuộc tính `CACHE`, `CHUNK`, `LOGGING` và storage in-row ảnh hưởng I/O và lưu trữ; chúng không phải yêu cầu bắt buộc để bật ba tính năng đang học. Hãy chọn theo workload thay vì sao chép nguyên ví dụ.

### 8.1. Lưu ý về BFILE

`BFILE` là locator đến file ngoài database, không phải nội dung LOB được lưu trong LOB segment. SecureFiles compression, deduplication và encryption không áp dụng cho file ngoài thông qua BFILE theo cách áp dụng cho CLOB/BLOB nội bộ.

Nếu cần database quản lý bảo mật và lưu trữ LOB, cân nhắc BLOB/CLOB nội bộ. Nếu dùng BFILE, phải quản lý quyền filesystem, directory object và vòng đời file bên ngoài.

## 9. Thay đổi thuộc tính LOB hiện có

Với SecureFiles LOB đã tạo, có thể dùng `ALTER TABLE ... MODIFY LOB` để thay đổi một số thuộc tính theo khả năng phiên bản.

Bật compression:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    COMPRESS MEDIUM
);
```

Đổi mức compression:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    COMPRESS HIGH
);
```

Tắt compression:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    NOCOMPRESS
);
```

Bật deduplication:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    DEDUPLICATE
);
```

Giữ các bản sao riêng:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    KEEP_DUPLICATES
);
```

Bật encryption:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    ENCRYPT USING 'AES256'
);
```

Tắt encryption:

```sql
ALTER TABLE customer_files
MODIFY LOB (file_content)
(
    DECRYPT
);
```

Các lệnh trên minh họa cú pháp thuộc tính. Trước khi chạy production, kiểm tra tài liệu đúng release để xác định thay đổi nào áp dụng cho LOB được ghi mới, thay đổi metadata hay cần di chuyển/rewrite dữ liệu hiện có. Với dữ liệu lớn, ước lượng thời gian, dung lượng tạm, redo, undo, lock và cửa sổ bảo trì.

## 10. Di chuyển BasicFiles sang SecureFiles

Nếu cột LOB hiện đang là BasicFiles, cần chuyển đổi lưu trữ sang SecureFiles trước khi dùng compression, deduplication hoặc encryption của SecureFiles.

### 10.1. Kiểm tra trạng thái hiện tại

```sql
SELECT table_name,
       column_name,
       segment_name,
       securefile,
       compression,
       deduplication,
       encrypt
FROM user_lobs
WHERE table_name = 'LEGACY_DOCUMENTS';
```

Nếu `SECUREFILE` là `NO`, LOB đang dùng BasicFiles.

### 10.2. MOVE LOB

Cú pháp minh họa:

```sql
ALTER TABLE legacy_documents
MOVE LOB (document_content)
STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
    DEDUPLICATE
);
```

Thao tác MOVE có thể tạo lại LOB segment và di chuyển nội dung. Cần đánh giá:
- Thời gian chuyển đổi theo dung lượng.
- Dung lượng trống cho segment mới.
- Lock và khả năng truy cập trong lúc chuyển đổi.
- Index, constraint, trigger và dependency liên quan.
- Backup trước và sau chuyển đổi.
- Tác động đến replication, standby và quy trình khôi phục.

### 10.3. Online redefinition

Với bảng lớn cần hạn chế thời gian gián đoạn, có thể đánh giá `DBMS_REDEFINITION` để tái định nghĩa online nếu bảng và cấu trúc đáp ứng điều kiện. Đây là quy trình phức tạp hơn MOVE và cần DBA lập kế hoạch, kiểm tra dependency, dung lượng và đồng bộ DML trong quá trình redefinition.

Không chạy MOVE hoặc online redefinition trên production chỉ để thử tính năng. Thực hiện trên bản sao hoặc môi trường staging trước.

## 11. Kiểm tra metadata và cấu hình

### 11.1. USER_LOBS

```sql
SELECT table_name,
       column_name,
       tablespace_name,
       segment_name,
       securefile,
       compression,
       deduplication,
       encrypt,
       in_row,
       cache
FROM user_lobs
ORDER BY table_name, column_name;
```

View này giúp xác nhận thuộc tính của LOB trong schema hiện tại.

### 11.2. DB_SECUREFILE

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'db_securefile';
```

Cần quyền truy cập `V$PARAMETER`. Có thể dùng `SHOW PARAMETER` trong SQL*Plus/SQLcl.

### 11.3. ASSM của tablespace

```sql
SELECT tablespace_name,
       segment_space_management
FROM user_tablespaces
ORDER BY tablespace_name;
```

SecureFiles cần tablespace ASSM. Nếu tablespace không đáp ứng, hãy tạo hoặc chọn tablespace khác phù hợp.

### 11.4. Trạng thái TDE keystore

DBA có thể kiểm tra view liên quan keystore, ví dụ:

```sql
SELECT wallet_type,
       status,
       wallet_order
FROM v$encryption_wallet;
```

Cột và quyền truy cập phụ thuộc phiên bản. Thông tin keystore là dữ liệu bảo mật; chỉ người có trách nhiệm quản trị TDE nên truy vấn và chia sẻ kết quả phù hợp.

### 11.5. Dung lượng segment

```sql
SELECT s.segment_name,
       s.bytes,
       s.blocks
FROM user_segments s
JOIN user_lobs l
  ON l.segment_name = s.segment_name
WHERE l.table_name = 'CUSTOMER_FILES';
```

Dung lượng segment là số liệu hữu ích nhưng không tự cho biết dung lượng logic của LOB hoặc tỷ lệ dedup chính xác. Cần đo cả số byte nội dung và storage đã cấp phát.

## 12. Đo hiệu quả compression và deduplication

Không nên bật tính năng rồi chỉ nhìn vào một con số dung lượng. Cần so sánh trước và sau trên tập dữ liệu đại diện.

### 12.1. Kích thước logic của LOB

Với BLOB:

```sql
SELECT SUM(DBMS_LOB.GETLENGTH(file_content)) AS logical_bytes,
       COUNT(file_content) AS lob_count
FROM customer_files;
```

Với CLOB, `DBMS_LOB.GETLENGTH` trả số đơn vị ký tự theo semantics của LOB, không phải số byte storage. Không so sánh trực tiếp kết quả CLOB length với `USER_SEGMENTS.BYTES` như cùng một đơn vị.

### 12.2. Dung lượng segment

```sql
SELECT s.segment_name,
       s.bytes,
       s.blocks
FROM user_segments s
JOIN user_lobs l
  ON l.segment_name = s.segment_name
WHERE l.table_name = 'CUSTOMER_FILES';
```

Một số cấu trúc LOB có thể liên quan thêm LOB index hoặc segment phụ. Hãy xác định đúng các segment cần tính và tránh cộng trùng.

### 12.3. Tỷ lệ tiết kiệm

\[
\text{Storage saving} =
\frac{\text{Before bytes} - \text{After bytes}}
{\text{Before bytes}} \times 100\%
\]

Ví dụ: trước 100 GB, sau 65 GB, tiết kiệm 35%. Đây là số minh họa, không phải tỷ lệ đảm bảo của SecureFiles.

### 12.4. Đo deduplication bằng dữ liệu thực

Nếu bảng có nhiều bản sao nội dung giống nhau, so sánh:
- Tổng dung lượng logic của tất cả LOB.
- Dung lượng segment thực tế.
- Số lượng LOB.
- Số nhóm nội dung trùng lặp trong dữ liệu nguồn nếu có thể xác định.
- CPU và thời gian INSERT/UPDATE.

Không suy ra tỷ lệ dedup chỉ từ số hàng. Hai hàng có cùng tên file không có nghĩa nội dung byte giống nhau; hai hàng khác tên có thể có nội dung byte giống hệt.

### 12.5. Đo workload đọc và ghi

| Chỉ số | Mục đích |
|---|---|
| INSERT elapsed time | Đo chi phí ghi LOB |
| UPDATE LOB elapsed time | Đo chi phí thay đổi nội dung |
| SELECT/read latency | Đo chi phí giải nén/giải mã và đọc |
| CPU time | Đánh giá overhead compression/encryption |
| Physical reads | Đánh giá I/O storage |
| Segment bytes | Đánh giá dung lượng thực tế |
| Redo size | Đánh giá chi phí logging/recovery |
| PGA/SGA | Theo dõi tài nguyên bộ nhớ |
| Concurrent throughput | Kiểm tra ảnh hưởng khi nhiều session cùng thao tác |

## 13. Ảnh hưởng hiệu năng

### 13.1. Compression

Lợi ích:
- Giảm dung lượng LOB.
- Có thể giảm I/O khi đọc dữ liệu từ storage.
- Có thể giảm chi phí backup hoặc truyền dữ liệu trong một số quy trình.

Chi phí:
- CPU nén khi ghi.
- CPU giải nén khi đọc.
- Có thể tăng latency cho workload nhạy CPU.
- LOB thường xuyên cập nhật có thể làm chi phí nén lặp lại đáng kể.

### 13.2. Deduplication

Lợi ích:
- Giảm storage khi có nhiều LOB giống hệt.
- Tránh lưu nhiều bản sao vật lý của cùng nội dung trong phạm vi hỗ trợ.

Chi phí:
- Xác định nội dung trùng cần tài nguyên.
- Metadata và quản lý reference phức tạp hơn.
- Workload cập nhật có thể làm giảm lợi ích.
- Nội dung hầu như duy nhất không tạo nhiều tiết kiệm.

### 13.3. Encryption

Lợi ích:
- Bảo vệ dữ liệu LOB at rest.
- Hỗ trợ yêu cầu bảo mật và tuân thủ.

Chi phí:
- CPU cho mã hóa/giải mã.
- Quản lý khóa, keystore và backup.
- Yêu cầu vận hành và khôi phục phức tạp hơn.
- Có thể ảnh hưởng throughput/latency tùy workload và phần cứng.

### 13.4. Benchmark các cấu hình

So sánh trên cùng tập dữ liệu:
1. SecureFiles không bật option.
2. Compression.
3. Deduplication.
4. Compression + deduplication.
5. Encryption.
6. Cấu hình kết hợp đáp ứng license và yêu cầu bảo mật.

Chọn theo số liệu và yêu cầu nghiệp vụ. Không giả định kết hợp nhiều option luôn tốt hơn.

## 14. Cache, logging và các thuộc tính LOB khác

Compression, deduplication và encryption không phải các thuộc tính duy nhất của SecureFiles.

### 14.1. CACHE, NOCACHE và CACHE READS

- `CACHE`: LOB data có thể được đưa vào buffer cache theo semantics của Oracle.
- `NOCACHE`: hạn chế caching LOB data theo cấu hình.
- `CACHE READS`: cho phép cache khi đọc nhưng không áp dụng cache theo cách giống CACHE cho mọi thao tác.

Chọn theo kích thước LOB và tần suất truy cập. Cache một tập LOB rất lớn có thể gây áp lực buffer cache; `NOCACHE` có thể phù hợp với LOB lớn, ít truy cập hoặc streaming.

### 14.2. LOGGING và NOLOGGING

Logging ảnh hưởng redo và khả năng khôi phục. Không chọn `NOLOGGING` chỉ để tăng tốc ghi LOB nếu chưa đánh giá backup/recovery, Data Guard và yêu cầu bảo vệ dữ liệu.

Compression/encryption không thay thế redo logging hoặc backup. Kiểm tra đúng semantics của thuộc tính trong phiên bản và thao tác cụ thể.

### 14.3. ENABLE/DISABLE STORAGE IN ROW

`ENABLE STORAGE IN ROW` cho phép LOB nhỏ được lưu cùng hàng nếu thỏa điều kiện; `DISABLE STORAGE IN ROW` yêu cầu lưu out-of-row. Thuộc tính này ảnh hưởng layout và I/O, không phải tính năng nén hoặc mã hóa.

## 15. Giới hạn và lưu ý vận hành

### 15.1. File đã nén trước

Bật compression trên BLOB chứa ZIP, JPEG, MP4 hoặc file archive có thể không giảm thêm dung lượng đáng kể. Hãy kiểm tra định dạng file và thử nghiệm mẫu trước.

### 15.2. File đã mã hóa ở ứng dụng

Nếu ứng dụng mã hóa mỗi file bằng IV/nonce khác nhau trước khi ghi, ciphertext có thể khác dù plaintext giống nhau. Điều này thường làm deduplication kém hiệu quả. Cân nhắc ranh giới mã hóa: TDE tại database hay encryption ở application layer, tùy yêu cầu threat model và quyền truy cập.

### 15.3. Deduplication không thay thế content management

Deduplication không quản lý tên file, version, quyền chia sẻ, retention hoặc lịch sử thay đổi. Ứng dụng vẫn cần metadata và chính sách tài liệu riêng.

### 15.4. Encryption không bảo vệ dữ liệu sau khi user được phép đọc

User có quyền đọc LOB qua database có thể nhận nội dung đã được giải mã bởi Oracle. Hãy kết hợp TDE với quyền object, role, audit, kiểm soát tài khoản và bảo vệ kết nối.

### 15.5. Backup và recovery phải bao gồm keystore

Với TDE, backup datafile mà không có keystore/master key tương ứng có thể không đủ để khôi phục và đọc dữ liệu. Quy trình backup, restore, clone, standby và disaster recovery phải bảo vệ khóa theo chính sách tổ chức.

### 15.6. Thay đổi thuộc tính có thể cần thời gian và dung lượng

Với LOB segment lớn, thay đổi storage có thể tạo I/O, redo và nhu cầu dung lượng tạm. Lập kế hoạch cửa sổ bảo trì, kiểm tra không gian, backup và khả năng rollback/recovery.

### 15.7. Không dùng DDL thử nghiệm trên production

DDL có thể gây implicit commit và thay đổi cấu trúc ngay lập tức. Dùng schema lab hoặc bản sao dữ liệu trước khi thử `MOVE LOB`, thay đổi encryption hoặc chuyển BasicFiles sang SecureFiles.

## 16. Ví dụ thiết kế theo từng tình huống

### 16.1. Kho tài liệu văn bản nhiều nội dung lặp

Đặc điểm:
- Nhiều CLOB chứa XML/JSON hoặc text.
- Có mẫu nội dung lặp lại.
- Dữ liệu ít cập nhật sau khi tạo.

Có thể thử:

```sql
CREATE TABLE text_archive (
    archive_id NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    body CLOB
)
LOB (body) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
    DEDUPLICATE
);
```

Đo tỷ lệ nén, tỷ lệ duplicate và CPU. Xác nhận Advanced Compression license trước khi bật các option.

### 16.2. Kho ảnh và video

Đặc điểm:
- BLOB chứa JPEG, PNG, MP4.
- Phần lớn file đã được nén.
- Có thể có file trùng hoàn toàn.

Compression có thể không đem lại nhiều tiết kiệm. Deduplication có thể hữu ích nếu nhiều người tải cùng một file. Encryption phụ thuộc yêu cầu bảo mật.

```sql
CREATE TABLE media_store (
    media_id NUMBER PRIMARY KEY,
    media_type VARCHAR2(50),
    media_data BLOB
)
LOB (media_data) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    DEDUPLICATE
    ENCRYPT USING 'AES256'
);
```

Cần xác nhận license encryption và deduplication riêng.

### 16.3. Hồ sơ nhạy cảm

Đặc điểm:
- BLOB chứa bản scan hợp đồng, hồ sơ hoặc tài liệu có dữ liệu cá nhân.
- Yêu cầu bảo vệ at rest.
- Có thể ít trùng lặp.

Encryption là ưu tiên theo yêu cầu bảo mật. Compression/deduplication chỉ bật khi license và workload chứng minh lợi ích.

```sql
CREATE TABLE sensitive_records (
    record_id NUMBER PRIMARY KEY,
    record_document BLOB
)
LOB (record_document) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    ENCRYPT USING 'AES256'
);
```

Ngoài TDE, cần quyền truy cập tối thiểu, audit, keystore backup và bảo vệ network.

### 16.4. Hệ thống tài liệu dùng chung theo tenant

Nếu cùng nội dung được nhiều tenant tham chiếu, deduplication có thể giảm storage, nhưng cần đánh giá chính sách cô lập tenant. Không để thiết kế lưu trữ làm lộ thông tin về việc một tenant khác đã lưu cùng nội dung. API và kiểm soát truy cập phải bảo đảm mỗi tenant chỉ thấy dữ liệu được phép.

## 17. Kiểm tra license và điều kiện tính năng trước triển khai

Checklist cần thực hiện cùng DBA/license administrator:

1. Phiên bản Oracle Database và Release Update.
2. Edition và dịch vụ database đang sử dụng.
3. SecureFiles được cho phép bởi `DB_SECUREFILE`.
4. Tablespace có ASSM.
5. TDE keystore được cấu hình nếu dùng encryption.
6. Advanced Compression entitlement nếu dùng compression/deduplication.
7. Advanced Security entitlement nếu dùng SecureFiles encryption.
8. Cấu hình standby, backup và restore có hỗ trợ.
9. Kiểm tra cú pháp và hành vi trên môi trường staging.
10. Benchmark storage, CPU, latency và concurrency.
11. Kế hoạch migration nếu LOB hiện tại là BasicFiles.
12. Kế hoạch rollback hoặc khôi phục nếu thay đổi thất bại.

Không dùng `V$OPTION`, khả năng hiển thị menu hoặc việc câu lệnh chạy thành công làm bằng chứng duy nhất về license. Hãy đối chiếu Licensing Information User Manual của đúng release và hợp đồng hiện hành.

## 18. Bài thực hành tổng hợp

Các ví dụ dùng bảng riêng trong schema lab. Cần quyền CREATE TABLE và tablespace phù hợp; encryption cần TDE đã cấu hình và license tương ứng. Không chạy nguyên trạng trên production.

### Bước 1. Kiểm tra tham số và tablespace

```sql
SHOW PARAMETER db_securefile;

SELECT tablespace_name,
       segment_space_management
FROM user_tablespaces
ORDER BY tablespace_name;
```

Xác nhận tablespace mục tiêu có `AUTO`.

### Bước 2. Tạo bảng SecureFiles không bật option

```sql
CREATE TABLE lab_lob_plain (
    id NUMBER PRIMARY KEY,
    content BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
);
```

### Bước 3. Tạo bảng có compression

```sql
CREATE TABLE lab_lob_compressed (
    id NUMBER PRIMARY KEY,
    content CLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
);
```

Chỉ chạy khi entitlement Advanced Compression đã được xác nhận.

### Bước 4. Tạo bảng có deduplication

```sql
CREATE TABLE lab_lob_dedup (
    id NUMBER PRIMARY KEY,
    content BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    DEDUPLICATE
);
```

### Bước 5. Tạo bảng có encryption

```sql
CREATE TABLE lab_lob_encrypted (
    id NUMBER PRIMARY KEY,
    content BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    ENCRYPT USING 'AES256'
);
```

Chỉ chạy khi TDE keystore đã sẵn sàng và Advanced Security entitlement được xác nhận.

### Bước 6. Tạo bảng kết hợp tính năng

```sql
CREATE TABLE lab_lob_all_features (
    id NUMBER PRIMARY KEY,
    content BLOB
)
LOB (content) STORE AS SECUREFILE (
    TABLESPACE lob_lab_ts
    COMPRESS MEDIUM
    DEDUPLICATE
    ENCRYPT USING 'AES256'
);
```

Xác nhận cú pháp và kết hợp option theo đúng phiên bản trước khi chạy.

### Bước 7. Kiểm tra metadata

```sql
SELECT table_name,
       column_name,
       segment_name,
       securefile,
       compression,
       deduplication,
       encrypt,
       tablespace_name
FROM user_lobs
WHERE table_name LIKE 'LAB_LOB%'
ORDER BY table_name;
```

### Bước 8. Kiểm tra dung lượng segment

```sql
SELECT segment_name,
       segment_type,
       bytes,
       blocks
FROM user_segments
WHERE segment_name IN (
    SELECT segment_name
    FROM user_lobs
    WHERE table_name LIKE 'LAB_LOB%'
)
ORDER BY segment_name;
```

### Bước 9. Thử thay đổi thuộc tính

```sql
ALTER TABLE lab_lob_compressed
MODIFY LOB (content)
(
    COMPRESS HIGH
);
```

Chỉ thực hiện nếu tính năng đã được cấp phép. Đọc lại `USER_LOBS` và kiểm tra tác động lên dữ liệu hiện có theo phiên bản.

### Bước 10. Dọn bảng lab

Chỉ khi chắc chắn đây là các bảng do bạn tạo và không còn cần giữ dữ liệu:

```sql
DROP TABLE lab_lob_plain PURGE;
DROP TABLE lab_lob_compressed PURGE;
DROP TABLE lab_lob_dedup PURGE;
DROP TABLE lab_lob_encrypted PURGE;
DROP TABLE lab_lob_all_features PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin. DDL có implicit commit. Không chạy trên đối tượng nghiệp vụ hoặc dữ liệu dùng chung.

## 19. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| BasicFiles hỗ trợ SecureFiles compression | Compression/deduplication/encryption LOB trong bài yêu cầu SecureFiles |
| Chỉ cần ghi COMPRESS là mọi tablespace đều dùng được | SecureFiles yêu cầu ASSM và cấu hình database cho phép |
| Compression luôn tiết kiệm dung lượng | File đã nén hoặc mã hóa thường nén thêm rất ít |
| HIGH luôn là lựa chọn tốt nhất | HIGH có thể tốn CPU hơn; cần benchmark |
| Dedup gộp file gần giống nhau | Deduplication tập trung vào nội dung trùng theo semantics của SecureFiles, không phải tìm các file gần giống |
| Dedup thay thế versioning | Dedup là tối ưu storage, không lưu lịch sử phiên bản |
| Tên file giống nhau nghĩa là nội dung trùng | Cần nội dung LOB thực sự giống nhau |
| Encryption bảo vệ dữ liệu khỏi mọi user database | TDE bảo vệ at rest; user có quyền truy vấn vẫn có thể đọc nội dung |
| Encryption thay thế TLS | TDE không thay thế bảo vệ dữ liệu trên đường truyền |
| Bật được DDL nghĩa là có license | Cần xác nhận quyền sử dụng theo Licensing Information và hợp đồng |
| Compression và dedup không có chi phí | Cả hai có thể tăng CPU/metadata và ảnh hưởng latency |
| BFILE có thể dùng SecureFiles options | BFILE tham chiếu file ngoài database; SecureFiles LOB options áp dụng cho LOB nội bộ |
| ALTER metadata luôn chuyển đổi toàn bộ LOB ngay | Hành vi phụ thuộc thao tác và phiên bản; có thể cần MOVE/rewrite |
| TDE không cần backup key | Khôi phục dữ liệu mã hóa cần keystore/master key phù hợp |
| COMMIT trong script dọn dữ liệu là vô hại | DDL có implicit commit; PURGE xóa dữ liệu khỏi recycle bin |

## 20. Quy tắc ghi nhớ

| Nhu cầu | Lựa chọn |
|---|---|
| Lưu CLOB/BLOB lớn với tính năng LOB hiện đại | Đánh giá SecureFiles |
| Bật SecureFiles | Tablespace ASSM và `DB_SECUREFILE` cho phép |
| Nén text/XML/JSON | Thử `COMPRESS LOW`, `MEDIUM`, `HIGH` |
| Lưu nhiều nội dung giống hệt | Đánh giá `DEDUPLICATE` |
| Muốn giữ từng bản sao | `KEEP_DUPLICATES` |
| Bảo vệ LOB at rest | SecureFiles `ENCRYPT` với TDE |
| Chọn cipher | `ENCRYPT USING 'AES256'` nếu release hỗ trợ và policy cho phép |
| Compression/dedup license | Xác nhận Advanced Compression Option |
| Encryption license | Xác nhận Advanced Security Option |
| Kiểm tra thuộc tính | `USER_LOBS`/`ALL_LOBS`/`DBA_LOBS` |
| Kiểm tra tablespace | `SEGMENT_SPACE_MANAGEMENT = AUTO` |
| Kiểm tra DB_SECUREFILE | `SHOW PARAMETER` hoặc `V$PARAMETER` |
| Chuyển BasicFiles | Lập kế hoạch MOVE LOB hoặc online redefinition |
| Đo hiệu quả | So sánh segment bytes, logical bytes, CPU, latency và redo |
| Khôi phục TDE | Bảo vệ và backup keystore/master key |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** SecureFiles khác BasicFiles ở điểm nào liên quan bài học?

**Trả lời:** SecureFiles cung cấp các tính năng LOB compression, deduplication và encryption; BasicFiles không cung cấp các option SecureFiles này.

**Câu 2.** Điều kiện tablespace quan trọng của SecureFiles là gì?

**Trả lời:** Tablespace cần dùng Automatic Segment Space Management, tức `SEGMENT_SPACE_MANAGEMENT = AUTO`.

**Câu 3.** DB_SECUREFILE dùng để làm gì?

**Trả lời:** Tham số điều khiển hành vi tạo SecureFiles LOB của database; cần kiểm tra giá trị theo release.

**Câu 4.** Compression LOW, MEDIUM và HIGH khác nhau thế nào?

**Trả lời:** Chúng thể hiện lựa chọn cân bằng khác nhau giữa tốc độ xử lý và mức tiết kiệm storage; cần benchmark trên dữ liệu thật.

**Câu 5.** Loại dữ liệu nào thường nén kém?

**Trả lời:** JPEG, MP4, ZIP, dữ liệu đã nén hoặc ciphertext đã mã hóa.

**Câu 6.** Deduplication làm gì?

**Trả lời:** Tránh lưu nhiều bản sao vật lý của nội dung LOB trùng lặp trong phạm vi SecureFiles hỗ trợ.

**Câu 7.** Deduplication có thay thế versioning không?

**Trả lời:** Không. Nó chỉ tối ưu storage, không quản lý lịch sử phiên bản.

**Câu 8.** KEEP_DUPLICATES có ý nghĩa gì?

**Trả lời:** Giữ các bản sao riêng và không dùng deduplication cho LOB segment.

**Câu 9.** SecureFiles encryption sử dụng công nghệ nào?

**Trả lời:** Transparent Data Encryption (TDE), với quản lý khóa qua keystore/wallet.

**Câu 10.** TDE có thay thế TLS không?

**Trả lời:** Không. TDE bảo vệ dữ liệu at rest; TLS hoặc cơ chế network encryption bảo vệ dữ liệu khi truyền.

**Câu 11.** Compression và deduplication thường cần license nào?

**Trả lời:** Oracle Advanced Compression Option theo mô hình cấp phép phổ biến; phải xác nhận đúng release, edition và hợp đồng.

**Câu 12.** SecureFiles encryption thường cần license nào?

**Trả lời:** Oracle Advanced Security Option theo mô hình cấp phép phổ biến; cần kiểm tra Licensing Information của release và hợp đồng.

**Câu 13.** Vì sao không thể kết luận có license chỉ vì DDL chạy thành công?

**Trả lời:** Khả năng kỹ thuật của database không phải bằng chứng quyền sử dụng theo hợp đồng.

**Câu 14.** BFILE có dùng các SecureFiles options này không?

**Trả lời:** Không theo cách của CLOB/BLOB nội bộ; BFILE tham chiếu file bên ngoài database.

**Câu 15.** Làm sao kiểm tra cấu hình LOB?

**Trả lời:** Truy vấn USER_LOBS, ALL_LOBS hoặc DBA_LOBS và kiểm tra các cột SECUREFILE, COMPRESSION, DEDUPLICATION, ENCRYPT.

**Câu 16.** Vì sao cần backup keystore khi dùng TDE?

**Trả lời:** Dữ liệu mã hóa cần master key phù hợp để giải mã sau restore hoặc disaster recovery.

**Câu 17.** Compression HIGH có luôn nhanh hơn MEDIUM không?

**Trả lời:** Không. HIGH có thể tiết kiệm storage hơn nhưng tiêu tốn CPU và tăng latency.

**Câu 18.** Khi nào nên dùng MOVE LOB?

**Trả lời:** Khi cần di chuyển/tái tổ chức LOB segment, ví dụ chuyển BasicFiles sang SecureFiles hoặc thay đổi cách lưu trữ cần rewrite dữ liệu.

## 22. Kết luận

SecureFiles cung cấp compression, deduplication và encryption để quản lý LOB lớn hiệu quả hơn. Compression giảm dung lượng dựa trên khả năng nén của nội dung; deduplication tránh lưu nhiều bản sao của LOB trùng lặp; encryption bảo vệ dữ liệu at rest thông qua TDE. Các tính năng có thể được kết hợp theo khả năng release và cấu hình, nhưng mỗi lựa chọn đều có chi phí CPU, storage, I/O và vận hành riêng.

Trước khi bật, phải xác nhận LOB dùng SecureFiles, tablespace có ASSM, `DB_SECUREFILE` cho phép, TDE keystore sẵn sàng nếu mã hóa và quyền license tương ứng. Compression/deduplication thường gắn với Advanced Compression Option; SecureFiles encryption thường gắn với Advanced Security Option. Luôn kiểm tra tài liệu cấp phép đúng release và hợp đồng, không suy luận quyền sử dụng từ việc DDL thành công.

Hãy chọn tính năng dựa trên nội dung thật: text có thể nén tốt, file media đã nén thường tiết kiệm ít, nội dung trùng lặp phù hợp dedup, còn dữ liệu nhạy cảm cần encryption theo threat model. Dùng `USER_LOBS`, segment statistics và benchmark để so sánh dung lượng, CPU, latency, redo và concurrency. Với BasicFiles hiện hữu, lập kế hoạch MOVE LOB hoặc online redefinition, kiểm tra backup/keystore và thực hiện trong môi trường staging trước khi triển khai production.

