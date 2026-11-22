# Dữ liệu TEXT/BLOB ngoài trang và giới hạn kích thước record

InnoDB lưu hàng dữ liệu trong các page của tablespace. Một hàng có thể chứa nhiều cột, nhưng không phải mọi byte của một giá trị lớn đều phải nằm trong page chứa record. Với các cột có giá trị dài như `TEXT`, `BLOB` hoặc `VARCHAR` lớn, InnoDB có thể chuyển phần dữ liệu dài sang các overflow page (off-page storage) và giữ một con trỏ trong record của clustered index.

Khả năng lưu ngoài trang phụ thuộc row format. `COMPACT` và `REDUNDANT` giữ một prefix tối đa 768 byte trong record rồi lưu phần còn lại ngoài trang; `DYNAMIC` và `COMPRESSED` có thể lưu toàn bộ giá trị ngoài trang khi InnoDB quyết định cần externalize cột. Dù dùng off-page storage, bảng vẫn chịu giới hạn kích thước hàng ở SQL layer và giới hạn record nội bộ theo kích thước page InnoDB.

Hiểu hai giới hạn này giúp chẩn đoán lỗi `Row size too large`, chọn row format, thiết kế bảng có cột LOB và tránh đọc dữ liệu lớn khi truy vấn chỉ cần metadata.

## 1. Record, page và off-page storage

InnoDB tổ chức dữ liệu theo page. Với cấu hình mặc định phổ biến, `innodb_page_size` là 16 KiB. Bảng InnoDB có clustered index; record của mỗi hàng nằm trong leaf page của clustered index. Nếu hàng có các giá trị biến độ dài rất lớn, việc giữ tất cả byte trong cùng page sẽ làm giảm số record có thể chứa và có thể vượt giới hạn kích thước record nội bộ.

InnoDB giải quyết vấn đề bằng cách lưu một phần giá trị dài trong record và chuyển phần còn lại sang các page riêng. Các page này thường được gọi là overflow pages hoặc BLOB pages. Record trong clustered index giữ thông tin cần thiết để tìm phần dữ liệu được lưu ngoài trang.

**Off-page không có nghĩa dữ liệu được lưu ra một máy chủ hoặc file bên ngoài MySQL.** Dữ liệu vẫn thuộc tablespace của InnoDB; nó chỉ nằm ở page khác với page chứa record chính. Với file-per-table, các page này thường nằm trong tablespace của bảng tương ứng.

Việc externalize có thể làm record chính gọn hơn, nhưng khi truy vấn cần đọc toàn bộ giá trị, InnoDB phải truy cập thêm các page chứa phần dữ liệu đó. Vì vậy, lưu ngoài trang giải quyết giới hạn kích thước record chứ không làm việc đọc LOB miễn phí.

## 2. Hai giới hạn kích thước hàng cần phân biệt

MySQL có giới hạn kích thước hàng ở SQL layer và InnoDB có giới hạn record nội bộ gắn với page size. Hai giới hạn này khác nhau:

| Giới hạn | Phạm vi | Giá trị/đặc điểm |
| --- | --- | --- |
| SQL row-size limit | Tổng kích thước hàng theo cách MySQL biểu diễn cột | Tối đa 65.535 byte; nội dung thực tế của `TEXT`/`BLOB` được lưu riêng và chỉ đóng góp khoảng 9–12 byte metadata vào phép tính này |
| InnoDB maximum row size | Record nằm trong page của InnoDB, không tính toàn bộ nội dung LOB đã externalize | Nhỏ hơn một chút so với một nửa page size |

Với page size 16 KiB, kích thước record nội bộ tối đa thường nhỏ hơn khoảng 8 KiB. Con số cụ thể có thể thấp hơn do record header, transaction metadata, directory và các overhead khác. Khi lỗi báo `Row size too large (> 8126)`, đây thường là giới hạn record InnoDB trên page 16 KiB, không phải giới hạn 65.535 byte của SQL layer.

### 2.1. Giới hạn 65.535 byte ở SQL layer

MySQL giới hạn tổng kích thước hàng ở mức 65.535 byte. Khi tính giới hạn này, nội dung của `TEXT` và `BLOB` không được tính toàn bộ như cột `VARCHAR`; chúng chỉ đóng góp phần metadata độ dài, thường khoảng 9–12 byte tùy kiểu. Tuy nhiên, các cột `VARCHAR`, `CHAR`, kiểu số, ngày giờ và metadata của các cột khác vẫn góp vào kích thước hàng.

Ví dụ, một bảng có nhiều cột `VARCHAR(10000)` với charset `utf8mb4` có thể vượt giới hạn SQL row size ngay cả khi dữ liệu thực tế đang lưu ngắn. `utf8mb4` có thể cần tối đa 4 byte cho mỗi ký tự, nên độ dài khai báo theo ký tự không đồng nghĩa số byte tối đa bằng số ký tự.

Đổi một số cột lớn từ `VARCHAR` sang `TEXT` có thể giảm phần đóng góp vào giới hạn SQL row size, nhưng không phải cách chữa mọi lỗi. Cần xét cả giới hạn record nội bộ, row format, số cột và dữ liệu thực tế.

### 2.2. Giới hạn record của InnoDB theo page size

InnoDB cần giữ record chính đủ nhỏ để lưu trong page. Quy tắc tổng quát là maximum row size nhỏ hơn một nửa page size:

| `innodb_page_size` | Giới hạn record gần đúng trước overhead |
| ---: | ---: |
| 4 KiB | Nhỏ hơn khoảng 2 KiB |
| 8 KiB | Nhỏ hơn khoảng 4 KiB |
| 16 KiB | Nhỏ hơn khoảng 8 KiB |
| 32 KiB | Nhỏ hơn khoảng 16 KiB |
| 64 KiB | Nhỏ hơn khoảng 32 KiB |

Đây là cách ước lượng để hiểu giới hạn, không phải cam kết rằng record có thể dùng toàn bộ đúng một nửa page. Record header, page directory, metadata và cách lưu cột làm giảm dung lượng khả dụng.

Kiểm tra page size:

```sql
SELECT @@innodb_page_size AS innodb_page_size_bytes;
```

`innodb_page_size` được chọn khi khởi tạo instance và không thể thay đổi bằng một lệnh `SET` trên instance đang chạy. Chọn page size khác thường cần tạo instance mới và di chuyển dữ liệu theo kế hoạch.

## 3. Các kiểu TEXT và BLOB

MySQL có bốn cỡ cho mỗi nhóm `TEXT` và `BLOB`:

| Kiểu | Dung lượng dữ liệu tối đa theo kiểu | Ghi chú |
| --- | ---: | --- |
| `TINYTEXT` / `TINYBLOB` | 255 byte | Giá trị nhỏ |
| `TEXT` / `BLOB` | 65.535 byte | Tương đương giới hạn 16-bit độ dài |
| `MEDIUMTEXT` / `MEDIUMBLOB` | 16.777.215 byte | Gần 16 MiB |
| `LONGTEXT` / `LONGBLOB` | 4.294.967.295 byte | Gần 4 GiB theo giới hạn kiểu |

Đây là giới hạn lý thuyết theo kiểu dữ liệu. Giá trị thực tế còn bị giới hạn bởi `max_allowed_packet`, khả năng của client/driver, bộ nhớ, giao thức, cấu hình server và tài nguyên lưu trữ. Không nên hiểu `LONGBLOB` có nghĩa mọi ứng dụng đều có thể gửi một giá trị gần 4 GiB trong một câu lệnh.

### 3.1. TEXT là dữ liệu ký tự

`TEXT` lưu nội dung theo character set và collation của cột. Độ dài được định nghĩa theo byte capacity của loại TEXT, không phải số ký tự cố định. Một ký tự UTF-8 có thể chiếm nhiều byte.

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(300) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    PRIMARY KEY (article_id)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Với `utf8mb4`, một chuỗi 10.000 ký tự có thể cần nhiều hơn 10.000 byte. Dung lượng thực phụ thuộc ký tự được lưu.

### 3.2. BLOB là dữ liệu nhị phân

`BLOB` lưu byte nhị phân và không áp dụng chuyển đổi character set như `TEXT`. Nó phù hợp với ảnh, tệp đính kèm, nội dung nén hoặc payload nhị phân.

```sql
CREATE TABLE document_attachments (
    attachment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    file_data LONGBLOB NOT NULL,
    PRIMARY KEY (attachment_id)
) ENGINE=InnoDB;
```

Khi so sánh `TEXT`, collation có thể khiến hai chuỗi được xem là bằng nhau dù khác hoa/thường hoặc dấu. Với `BLOB`, so sánh dựa trên byte. Không dùng BLOB để lưu văn bản chỉ vì muốn tránh suy nghĩ về charset; điều đó làm mất ngữ nghĩa văn bản và khiến truy vấn khó đọc hơn.

## 4. Đo số byte và số ký tự

Khi chẩn đoán kích thước, cần phân biệt byte với ký tự:

- `CHAR_LENGTH(value)` trả số ký tự.
- `OCTET_LENGTH(value)` trả số byte.
- `LENGTH(value)` trong MySQL cũng trả số byte.

Ví dụ:

```sql
SELECT
    'Cơ sở dữ liệu' AS sample_text,
    CHAR_LENGTH('Cơ sở dữ liệu') AS character_count,
    OCTET_LENGTH('Cơ sở dữ liệu') AS byte_count;
```

Với chuỗi có ký tự ngoài ASCII, `byte_count` có thể lớn hơn `character_count`. Đây là lý do cần kiểm tra byte khi ước lượng record size, `VARCHAR` và payload.

Đo dữ liệu thực tế trong bảng:

```sql
SELECT
    article_id,
    CHAR_LENGTH(body) AS body_characters,
    OCTET_LENGTH(body) AS body_bytes
FROM articles
ORDER BY body_bytes DESC
LIMIT 20;
```

Đối với BLOB:

```sql
SELECT
    attachment_id,
    OCTET_LENGTH(file_data) AS file_bytes
FROM document_attachments
ORDER BY file_bytes DESC
LIMIT 20;
```

Các truy vấn này đo độ dài logic của giá trị, không cho biết chính xác số byte vật lý trên disk sau khi InnoDB tổ chức page, nén, metadata và lưu trữ ngoài trang.

## 5. Row format quyết định cách lưu giá trị dài

InnoDB hỗ trợ các row format chính: `REDUNDANT`, `COMPACT`, `DYNAMIC` và `COMPRESSED`. Row format quy định cấu trúc record và cách lưu cột biến độ dài.

| Row format | Prefix inline khi giá trị được lưu ngoài trang | Phần còn lại |
| --- | --- | --- |
| `REDUNDANT` | Tối đa 768 byte | Lưu ngoài trang |
| `COMPACT` | Tối đa 768 byte | Lưu ngoài trang |
| `DYNAMIC` | Không giữ prefix 768 byte; record giữ con trỏ 20 byte khi cột được externalize | Toàn bộ giá trị được lưu ngoài trang |
| `COMPRESSED` | Cách xử lý LOB tương tự `DYNAMIC` | Toàn bộ giá trị được lưu ngoài trang |

Các giá trị ngắn có thể vẫn nằm hoàn toàn trong record. InnoDB chỉ externalize cột khi cần để record vừa page và theo chiến lược của row format. Vì vậy, khai báo cột `TEXT` không đồng nghĩa mọi giá trị của cột đó luôn nằm ngoài trang.

### 5.1. REDUNDANT và COMPACT: giữ prefix 768 byte

Với hai row format cũ này, khi giá trị biến độ dài được lưu ngoài trang, InnoDB giữ tối đa 768 byte đầu trong record clustered index và lưu phần còn lại ở overflow page. Record còn có con trỏ 20 byte tới phần dữ liệu ngoài trang.

Điều này giúp truy cập prefix mà không nhất thiết phải đọc toàn bộ phần còn lại trong một số trường hợp, nhưng 768 byte inline vẫn chiếm chỗ trong record. Nếu một hàng có nhiều cột LOB dài, các prefix inline có thể cộng lại và khiến record vượt giới hạn page.

Vì vậy, chỉ đổi cột `VARCHAR` thành `TEXT` chưa chắc giải quyết được lỗi `Row size too large` nếu bảng vẫn dùng `COMPACT` và nhiều prefix 768 byte vẫn được giữ trong record.

### 5.2. DYNAMIC và COMPRESSED: lưu toàn bộ giá trị ngoài trang

Với `DYNAMIC` và `COMPRESSED`, khi một cột dài được externalize, InnoDB có thể lưu toàn bộ giá trị ở overflow page và chỉ giữ con trỏ 20 byte trong record clustered index. Cách này giảm đáng kể phần dữ liệu LOB nằm inline so với prefix 768 byte.

`DYNAMIC` phù hợp với bảng có nhiều cột dài hoặc giá trị LOB lớn nhưng phần lớn truy vấn chỉ đọc metadata. Đây là row format mặc định phổ biến của InnoDB trong MySQL hiện đại; vẫn nên kiểm tra row format thực tế của bảng thay vì dựa vào mặc định.

`COMPRESSED` cũng hỗ trợ off-page storage theo cách của `DYNAMIC`, đồng thời dùng cơ chế nén page. Nén có thêm chi phí CPU và các ràng buộc về page size/thuật toán; không chọn chỉ vì muốn giảm record size nếu chưa đo workload.

## 6. Kiểm tra row format hiện tại

Có thể xem row format trong `INFORMATION_SCHEMA.TABLES`:

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    ROW_FORMAT
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'articles';
```

Hoặc dùng:

```sql
SHOW TABLE STATUS LIKE 'articles'\G
SHOW CREATE TABLE articles\G
```

Nếu bảng không ghi rõ `ROW_FORMAT`, row format được chọn theo cấu hình mặc định của InnoDB tại thời điểm tạo bảng. Có thể xem cấu hình:

```sql
SHOW VARIABLES LIKE 'innodb_default_row_format';
```

Để tạo bảng mới với DYNAMIC:

```sql
CREATE TABLE article_contents (
    article_id BIGINT UNSIGNED NOT NULL,
    body LONGTEXT NOT NULL,
    PRIMARY KEY (article_id)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC;
```

Để đổi bảng hiện có:

```sql
ALTER TABLE articles ROW_FORMAT=DYNAMIC;
```

Thay đổi row format có thể cần rebuild bảng và tốn I/O, dung lượng tạm, thời gian hoặc metadata lock. Trước khi chạy trên bảng lớn, hãy thử trên staging có dữ liệu đại diện, kiểm tra thuật toán DDL được hỗ trợ trên phiên bản hiện tại, thời gian chạy và dung lượng đĩa dự phòng.

## 7. Vì sao lỗi Row size too large vẫn xảy ra với TEXT/BLOB?

Thông báo thường gặp:

```text
ERROR 1118 (42000): Row size too large (> 8126).
Changing some columns to TEXT or BLOB may help.
In current row format, BLOB prefix of 768 bytes is stored inline.
```

Lỗi này thường cho biết record nội bộ vượt giới hạn của page. Một số nguyên nhân:

- Bảng có quá nhiều cột `VARCHAR` với độ dài khai báo lớn.
- Nhiều cột dùng `utf8mb4`, làm số byte tối đa của mỗi cột tăng.
- Bảng dùng `COMPACT`/`REDUNDANT`, giữ prefix 768 byte của nhiều cột dài inline.
- Có nhiều cột fixed-length, không thể chuyển toàn bộ dữ liệu của chúng ra ngoài trang.
- Row format hoặc page size hiện tại khiến dung lượng inline khả dụng thấp hơn dự tính.

Không nên giải quyết bằng cách chuyển mọi cột sang `TEXT` một cách máy móc. Cần xác định cột nào thực sự là nội dung dài, chọn `DYNAMIC` nếu phù hợp, giảm số cột/độ dài inline hoặc tách dữ liệu thành bảng liên quan.

## 8. Quy trình chẩn đoán và xử lý lỗi record size

Khi gặp lỗi 1118 hoặc nghi ngờ hàng quá lớn:

1. **Đọc DDL:** dùng `SHOW CREATE TABLE` để kiểm tra kiểu cột, charset, nullability, index và row format.
2. **Kiểm tra page size:** xem `@@innodb_page_size`; nhớ giới hạn record InnoDB phụ thuộc page size.
3. **Kiểm tra row format:** xem `INFORMATION_SCHEMA.TABLES.ROW_FORMAT` và `innodb_default_row_format`.
4. **Ước lượng byte:** dùng `OCTET_LENGTH()` trên dữ liệu thật; với cột chưa có dữ liệu, ước lượng theo charset và độ dài khai báo.
5. **Xác định cột dài:** xem các `VARCHAR` lớn, `TEXT`/`BLOB`, cột nullable và số lượng cột trong bảng.
6. **Đánh giá external storage:** nếu đang dùng `COMPACT`, xem xét `DYNAMIC` để bỏ prefix 768 byte inline cho cột được externalize.
7. **Giảm dữ liệu inline:** rút ngắn `VARCHAR`, chọn kiểu phù hợp, hoặc chuyển phần nội dung ít truy cập sang bảng riêng.
8. **Kiểm tra SQL row-size limit:** nếu tổng khai báo vẫn vượt 65.535 byte ở SQL layer, đổi row format không đủ; cần thay đổi schema.
9. **Thử DDL trên staging:** xác nhận bảng tạo được, insert dữ liệu lớn được và truy vấn hoạt động đúng.
10. **Đánh giá chi phí migration:** rebuild, lock, disk, replication lag và thời gian triển khai trước khi áp dụng production.

## 9. Tách metadata và nội dung LOB thành hai bảng

Nếu phần lớn truy vấn chỉ cần tiêu đề, trạng thái, người tạo và thời điểm cập nhật, còn nội dung lớn chỉ được đọc khi người dùng mở tài liệu, có thể tách metadata và nội dung:

```sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(300) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id),
    KEY idx_documents_status_created (status, created_at)
) ENGINE=InnoDB;

CREATE TABLE document_contents (
    document_id BIGINT UNSIGNED NOT NULL,
    body LONGTEXT NOT NULL,
    PRIMARY KEY (document_id),
    CONSTRAINT fk_document_contents_document
        FOREIGN KEY (document_id) REFERENCES documents (document_id)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC;
```

Truy vấn danh sách không cần đọc nội dung:

```sql
SELECT document_id, title, status, created_at
FROM documents
WHERE status = 'published'
ORDER BY created_at DESC, document_id DESC
LIMIT 50;
```

Chỉ khi người dùng mở một tài liệu mới đọc LOB:

```sql
SELECT d.document_id, d.title, c.body
FROM documents AS d
JOIN document_contents AS c
  ON c.document_id = d.document_id
WHERE d.document_id = 1001;
```

Cách tách này giữ record metadata gọn, giúp truy vấn danh sách không phải đọc page LOB. Đổi lại, thao tác tạo/cập nhật/xóa tài liệu cần quản lý hai bảng; nếu chúng phải cùng thay đổi, thực hiện trong cùng transaction InnoDB.

## 10. Đọc LOB có thể làm tăng I/O

Khi một truy vấn chọn cột LOB, InnoDB có thể cần truy cập overflow pages để lấy giá trị. Nếu ứng dụng chỉ cần metadata, hãy không chọn cột lớn:

```sql
-- Tốt hơn cho danh sách: chỉ lấy cột cần hiển thị
SELECT document_id, title, status
FROM documents
WHERE status = 'published';
```

Tránh:

```sql
-- Đọc toàn bộ nội dung dù giao diện chỉ cần tiêu đề
SELECT *
FROM documents_with_body
WHERE status = 'published';
```

Một số lưu ý:

- Tránh `SELECT *` trên bảng có LOB nếu không cần toàn bộ nội dung.
- Phân trang danh sách metadata trước khi tải nội dung chi tiết.
- Dùng streaming API của driver khi xử lý BLOB/TEXT lớn, tránh nạp nhiều giá trị lớn vào bộ nhớ ứng dụng cùng lúc.
- Đặt giới hạn kích thước upload và xác thực loại dữ liệu ở tầng ứng dụng.
- Đánh giá cache và thời gian truy xuất LOB riêng với truy vấn metadata.

Off-page storage không đảm bảo mọi lần đọc đều chậm; nếu page đã ở buffer pool, dữ liệu có thể được phục vụ từ bộ nhớ. Chi phí phụ thuộc kích thước LOB, số page, locality, cache hit và workload.

## 11. Index trên TEXT/BLOB

Không thể tạo index B-tree thông thường trên toàn bộ giá trị `TEXT`/`BLOB` có độ dài tùy ý. MySQL yêu cầu prefix length khi tạo index trên các kiểu này:

```sql
CREATE INDEX idx_articles_body_prefix
ON articles (body(100));
```

Với cột chuỗi không nhị phân, prefix length được chỉ định theo số ký tự; giới hạn index thực tế vẫn tính theo byte và phụ thuộc charset, row format và page size. Với `utf8mb4`, 100 ký tự có thể cần tối đa 400 byte.

Prefix index chỉ index phần đầu của giá trị. Nó có thể hữu ích cho một số điều kiện tìm kiếm theo prefix, nhưng không đại diện cho toàn bộ nội dung. Hai nội dung có cùng prefix vẫn không được phân biệt bởi prefix index như một index đầy đủ.

Ví dụ:

```sql
SELECT article_id
FROM articles
WHERE body LIKE 'MySQL InnoDB%';
```

Index prefix có thể giúp một số truy vấn bắt đầu bằng prefix phù hợp, nhưng không giúp tốt cho mẫu tìm kiếm bắt đầu bằng wildcard như `LIKE '%InnoDB%'`. Hãy kiểm tra `EXPLAIN` và cân nhắc `FULLTEXT` nếu nghiệp vụ là tìm kiếm văn bản toàn nội dung.

Đối với BLOB, prefix length được tính theo byte. Với TEXT, cần lưu ý character set và collation. Giới hạn key length của InnoDB phụ thuộc page size và row format; không nên chọn prefix dài mà chưa kiểm tra giới hạn index.

## 12. Giới hạn index key length liên quan row format

Kích thước index key tối đa của InnoDB phụ thuộc page size và row format. Với page size 16 KiB, giới hạn phổ biến là 3072 byte cho `DYNAMIC`/`COMPRESSED`, trong khi `COMPACT`/`REDUNDANT` có giới hạn lịch sử 767 byte. Page size 8 KiB hoặc 4 KiB làm giới hạn tối đa giảm tương ứng (thường 1536 và 768 byte cho các row format hỗ trợ giới hạn lớn).

Với `utf8mb4`, prefix 191 ký tự có thể cần tối đa 764 byte; đây là lý do con số 191 thường xuất hiện trong schema tương thích giới hạn 767 byte cũ. Tuy nhiên, đây không phải con số tối ưu bắt buộc cho mọi bảng hay mọi phiên bản. Chọn prefix theo truy vấn và giới hạn key length thực tế.

Một prefix `UNIQUE` chỉ bảo đảm phần prefix không trùng theo quy tắc index; nó không thay thế một unique constraint trên toàn bộ nội dung dài. Nếu nghiệp vụ cần duy nhất toàn bộ nội dung, có thể dùng cột hash được tính và xác thực có kiểm soát, nhưng phải xử lý xác suất collision và bảo đảm logic kiểm tra đầy đủ khi ghi.

## 13. max_allowed_packet và giới hạn truyền dữ liệu

Kích thước tối đa của kiểu `LONGTEXT`/`LONGBLOB` không đồng nghĩa ứng dụng có thể gửi giá trị lớn như vậy trong một packet. `max_allowed_packet` giới hạn kích thước packet/statement mà client và server chấp nhận; driver, giao thức và bộ nhớ cũng có giới hạn riêng.

Kiểm tra cấu hình server:

```sql
SHOW VARIABLES LIKE 'max_allowed_packet';
```

Nếu upload một tệp lớn, hãy kiểm tra cả giới hạn ở reverse proxy, web server, ứng dụng, driver và MySQL. Tăng `max_allowed_packet` không giải quyết giới hạn record nội bộ, không thay thế row format và cũng không làm tăng giới hạn kiểu dữ liệu.

Khi xử lý LOB lớn, cân nhắc streaming, chunking ở tầng ứng dụng hoặc lưu object storage rồi chỉ giữ metadata/URL/key trong MySQL. Nếu cần lưu nội dung trực tiếp trong database để có transaction, backup và quyền truy cập thống nhất, hãy cân nhắc chi phí lưu trữ, replication, backup/restore và I/O.

## 14. Chọn lưu BLOB trong MySQL hay object storage

Lưu nội dung nhị phân trong MySQL có một số lợi ích:

- Metadata và nội dung có thể được commit/rollback cùng transaction.
- Có thể áp dụng quyền truy cập database và backup theo cùng quy trình.
- Không cần xử lý tính nhất quán giữa hàng metadata và file ngoài database.

Nhưng cũng có chi phí:

- Tablespace, backup và binary log có thể tăng nhanh.
- Replication phải truyền dữ liệu lớn.
- Đọc danh sách có thể vô tình kéo theo LOB nếu truy vấn chọn rộng.
- Restore một bảng hoặc khôi phục dữ liệu lớn có thể tốn thời gian.

Object storage phù hợp khi tệp lớn, tải đọc/ghi cao hoặc cần phân phối nội dung qua CDN. Khi chọn cách này, database thường lưu object key, checksum, kích thước, content type và trạng thái. Cần thiết kế xử lý file upload thành công nhưng transaction metadata thất bại, hoặc ngược lại; outbox, trạng thái pending và tác vụ dọn orphan object là các mẫu có thể dùng.

Không có lựa chọn đúng cho mọi hệ thống. Quyết định phụ thuộc kích thước tệp, yêu cầu atomicity, tần suất truy cập, backup, retention, quyền truy cập và chi phí vận hành.

## 15. Ví dụ đo và kiểm tra bảng có LOB

Tạo bảng thử nghiệm với row format DYNAMIC:

```sql
CREATE TABLE lob_lab (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    body LONGTEXT NULL,
    binary_payload LONGBLOB NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_lob_lab_created (created_at)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARACTER SET utf8mb4;
```

Kiểm tra row format và engine:

```sql
SELECT TABLE_NAME, ENGINE, ROW_FORMAT
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'lob_lab';
```

Đo kích thước logic của nội dung:

```sql
SELECT
    id,
    CHAR_LENGTH(body) AS body_chars,
    OCTET_LENGTH(body) AS body_bytes,
    OCTET_LENGTH(binary_payload) AS payload_bytes
FROM lob_lab
ORDER BY id;
```

So sánh truy vấn metadata với truy vấn đọc LOB:

```sql
EXPLAIN
SELECT id, title, created_at
FROM lob_lab
WHERE created_at >= '2026-01-01';

EXPLAIN
SELECT id, title, body
FROM lob_lab
WHERE created_at >= '2026-01-01';
```

Hai truy vấn có thể dùng cùng điều kiện và index, nhưng truy vấn thứ hai cần trả thêm nội dung lớn. Dùng `EXPLAIN ANALYZE` trên môi trường lab có dữ liệu đại diện để đo thời gian và số hàng thực tế; bản thân `EXPLAIN` không đo chính xác chi phí đọc LOB trong mọi cache state.

## 16. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| TEXT/BLOB luôn được lưu ngoài trang | Giá trị ngắn có thể nằm inline; InnoDB externalize khi cần và theo row format | Kiểm tra row format và kích thước dữ liệu |
| Off-page nghĩa là file nằm ngoài database | Overflow pages vẫn thuộc tablespace InnoDB | Hiểu off-page là page khác với record chính |
| Đổi VARCHAR thành TEXT luôn sửa lỗi 1118 | SQL row limit và InnoDB page limit là hai giới hạn khác nhau; COMPACT còn giữ prefix 768 byte | Kiểm tra cả SQL size, row format và page size |
| DYNAMIC vẫn giữ prefix 768 byte inline | Khi externalize, DYNAMIC lưu toàn bộ giá trị ngoài trang và giữ con trỏ | Chọn row format đúng và xác minh DDL |
| `LONGTEXT` luôn chứa được gần 4 GiB | Packet, client, memory, server và storage có giới hạn riêng | Kiểm tra `max_allowed_packet` và toàn bộ pipeline |
| 65.535 byte là giới hạn record InnoDB | Đây là giới hạn SQL layer; record InnoDB còn chịu giới hạn nhỏ hơn theo page | Phân biệt hai loại lỗi và giới hạn |
| CHAR_LENGTH bằng số byte | Với charset đa byte, byte count có thể lớn hơn | Dùng `OCTET_LENGTH()` khi đo kích thước |
| Prefix index đại diện cho toàn bộ TEXT/BLOB | Index chỉ chứa prefix được khai báo | Dùng FULLTEXT hoặc chiến lược tìm kiếm phù hợp |
| SELECT * vô hại trên bảng có LOB | Có thể đọc và truyền các giá trị lớn không cần thiết | Chỉ chọn cột ứng dụng thực sự cần |
| Tách bảng nội dung luôn nhanh hơn | Thêm join và quản lý transaction giữa hai bảng | Đo workload và chọn theo access pattern |

## 17. Quy trình thiết kế bảng có TEXT/BLOB

Khi thiết kế bảng có nội dung dài, hãy kiểm tra:

1. Nội dung là văn bản hay byte nhị phân? Chọn `TEXT` hay `BLOB` đúng ngữ nghĩa.
2. Dung lượng tối đa cần thiết là bao nhiêu? Chọn TINY/TEXT/MEDIUM/LONG phù hợp, không chọn LONG chỉ vì “cho chắc”.
3. Charset nào được dùng? Tính dung lượng theo byte, nhất là với `utf8mb4`.
4. Row format hiện tại là gì? Với nhiều LOB, đánh giá `DYNAMIC`.
5. Page size là bao nhiêu? Record limit nội bộ thay đổi theo page size.
6. Bảng có nhiều cột `VARCHAR` lớn hoặc fixed-length không? Ước lượng record inline.
7. Truy vấn thường xuyên có cần đọc LOB không? Nếu không, cân nhắc tách metadata/content.
8. Có cần index nội dung? Chọn prefix index, FULLTEXT hoặc search engine theo kiểu truy vấn.
9. Kích thước upload có vượt `max_allowed_packet` hay giới hạn client không?
10. Backup, restore, replication và retention có chịu được dung lượng LOB không?
11. Migration row format hoặc tách bảng có cần rebuild và dung lượng đĩa dự phòng không?

## 18. Bài tập thực hành

1. Tạo hai bảng cùng schema, một dùng `ROW_FORMAT=COMPACT`, một dùng `ROW_FORMAT=DYNAMIC`; kiểm tra bằng `INFORMATION_SCHEMA.TABLES`.
2. Thêm các giá trị TEXT ngắn và dài; dùng `OCTET_LENGTH()` để so sánh byte với ký tự.
3. Tạo một bảng có nhiều cột `VARCHAR` lớn và thử tạo bảng/insert để quan sát giới hạn SQL row size và InnoDB record size trong môi trường lab.
4. Chuyển một bảng từ COMPACT sang DYNAMIC; so sánh DDL, thời gian rebuild và khả năng ghi dữ liệu lớn.
5. Tìm hiểu thông báo lỗi 1118 trên page size 16 KiB; xác định phần nào đến từ giới hạn record nhỏ hơn khoảng 8 KiB.
6. Tạo index prefix trên cột TEXT; dùng `EXPLAIN` so sánh điều kiện tìm prefix với `LIKE '%term%'`.
7. Tạo bảng metadata và bảng nội dung LOB riêng; so sánh truy vấn danh sách và truy vấn chi tiết.
8. Kiểm tra `max_allowed_packet` và mô phỏng payload lớn trong môi trường thử nghiệm có giới hạn phù hợp.
9. Thiết kế schema lưu ảnh/tệp đính kèm trong BLOB; ghi lại ảnh hưởng đến backup và replication.
10. Đề xuất phương án object storage cho tệp lớn, gồm cách tránh orphan file và cách đồng bộ metadata với object.

## 19. Ghi nhớ

InnoDB lưu record trong page và có thể chuyển cột biến độ dài lớn sang overflow page. `REDUNDANT`/`COMPACT` giữ tối đa 768 byte prefix inline cùng con trỏ 20 byte; `DYNAMIC`/`COMPRESSED` có thể lưu toàn bộ giá trị ngoài trang khi externalize và chỉ giữ con trỏ 20 byte. Off-page vẫn là dữ liệu trong tablespace InnoDB, không phải tự động nằm ngoài database.

Phân biệt giới hạn SQL row size 65.535 byte với giới hạn record InnoDB nhỏ hơn một nửa page size. Với page 16 KiB, record tối đa thường nhỏ hơn khoảng 8 KiB. TEXT/BLOB chỉ đóng góp phần metadata nhỏ vào giới hạn SQL layer, nhưng row format quyết định bao nhiêu byte LOB còn nằm inline. Khi gặp lỗi 1118, kiểm tra charset, số cột, `VARCHAR`, page size và row format; đánh giá DYNAMIC, giảm dữ liệu inline hoặc tách bảng nội dung. Dùng `OCTET_LENGTH()` để đo byte, tránh đọc LOB không cần thiết, kiểm tra prefix index và `max_allowed_packet`, đồng thời tính đến I/O, backup, replication và migration.
