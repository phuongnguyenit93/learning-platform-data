# COMPACT, DYNAMIC, COMPRESSED và điều kiện row format

Row format xác định cách InnoDB bố trí dữ liệu của một hàng trong trang dữ liệu, lưu thông tin độ dài cột biến thiên và xử lý các cột dài được đưa ra ngoài trang (off-page). Lựa chọn này ảnh hưởng đến kích thước record trong clustered index, giới hạn độ dài khóa index, dung lượng lưu trữ và chi phí CPU/I/O.

Ba row format thường cần hiểu khi thiết kế bảng là COMPACT, DYNAMIC và COMPRESSED. Trong MySQL hiện đại, DYNAMIC thường là lựa chọn mặc định. COMPACT chủ yếu quan trọng khi tương thích hệ thống cũ; COMPRESSED có thể giảm dung lượng nhưng cần đo lợi ích và chi phí nén trên dữ liệu thực tế.

Bài viết giải thích cách lưu cột dài, điều kiện hỗ trợ theo phiên bản và tablespace, giới hạn row/index, cách khai báo hoặc chuyển row format, cũng như cách kiểm tra kết quả trên MySQL.

## 1. Row format quyết định điều gì?

InnoDB lưu bảng trong các trang (page). Với bảng có clustered index, dữ liệu hàng được lưu trong các leaf page của clustered index. Mỗi record có phần thông tin quản lý, dữ liệu các cột và thông tin phục vụ MVCC.

Row format quyết định cách record được mã hóa và cách InnoDB xử lý các giá trị lớn khi một hàng không thể nằm gọn trong trang dữ liệu.

Các điểm chịu ảnh hưởng:

- Cấu trúc record và phần overhead của mỗi hàng.
- Cách lưu cột có độ dài biến thiên.
- Số byte của cột dài được giữ trong record và số byte được lưu off-page.
- Số hàng có thể chứa trong một page.
- Giới hạn độ dài khóa index trong một số phiên bản/page size.
- Khả năng và cách thức nén dữ liệu.

Row format không thay đổi ý nghĩa SQL của cột. Một cột VARCHAR vẫn là VARCHAR; thay đổi row format làm thay đổi cách InnoDB tổ chức dữ liệu vật lý của bảng.

## 2. Bốn row format của InnoDB

InnoDB có các row format REDUNDANT, COMPACT, DYNAMIC và COMPRESSED.

| Row format | Đặc điểm chính | Trường hợp thường gặp |
|---|---|---|
| REDUNDANT | Định dạng record cũ, overhead lưu thông tin cột lớn hơn | Tương thích hệ thống rất cũ |
| COMPACT | Record gọn hơn REDUNDANT; giữ một phần đầu của cột dài trong record khi đưa phần còn lại ra ngoài trang | Tương thích ứng dụng cũ hoặc cần giữ hành vi lưu trữ kiểu Antelope |
| DYNAMIC | Có thể lưu toàn bộ giá trị cột dài off-page, record giữ con trỏ 20 byte khi cột được đưa ra ngoài trang | Lựa chọn mặc định phổ biến trên MySQL hiện đại |
| COMPRESSED | Dựa trên cách lưu cột dài của DYNAMIC và lưu page ở dạng nén | Bảng có dữ liệu nén tốt và cần tiết kiệm dung lượng |

Phần lớn hệ thống mới nên bắt đầu với DYNAMIC. Chỉ chọn COMPRESSED sau khi đo dung lượng tiết kiệm, CPU nén/giải nén, I/O và độ trễ. Không nên chuyển sang COMPACT chỉ vì tên gọi hoặc vì cho rằng record luôn nhỏ hơn trong mọi tình huống.

## 3. COMPACT lưu cột dài như thế nào?

COMPACT giảm overhead record so với REDUNDANT. Với cột dài như BLOB, TEXT hoặc cột có độ dài biến thiên lớn, khi InnoDB quyết định đưa dữ liệu ra ngoài clustered index page, COMPACT giữ tối đa 768 byte đầu tiên của giá trị trong record. Phần còn lại được lưu ở trang overflow và record chứa con trỏ 20 byte đến dữ liệu off-page.

Điều đó có nghĩa một cột TEXT lớn có thể vẫn chiếm đáng kể không gian trong clustered index page ngay cả khi phần lớn nội dung đã được chuyển ra ngoài.

Ví dụ:

~~~sql
CREATE TABLE articles_compact (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(200) NOT NULL,
    body LONGTEXT,
    PRIMARY KEY (article_id)
) ENGINE = InnoDB
  ROW_FORMAT = COMPACT;
~~~

Khi body quá dài và được chọn để lưu off-page, phần đầu của giá trị vẫn có thể nằm trong record. Điều này làm tăng kích thước record so với cách lưu toàn bộ cột dài off-page.

COMPACT vẫn có thể phù hợp nếu phải duy trì tương thích với môi trường cũ hoặc có lý do đo đạc cụ thể. Tuy nhiên, với bảng chứa nhiều cột văn bản lớn, phần dữ liệu đầu giữ inline có thể làm giảm số record trên mỗi page.

## 4. DYNAMIC xử lý cột dài

DYNAMIC được thiết kế để giảm dữ liệu dài phải giữ trong clustered index record. Khi InnoDB chọn một cột dài để lưu off-page, toàn bộ giá trị cột có thể được lưu ở các trang overflow; record trong clustered index giữ con trỏ 20 byte.

Khác biệt chính:

| Tình huống | COMPACT | DYNAMIC |
|---|---|---|
| Cột dài được lưu off-page | Giữ tối đa 768 byte đầu trong record, phần còn lại off-page | Có thể đưa toàn bộ giá trị cột off-page |
| Dữ liệu inline của cột dài | Có thể lớn hơn | Thường nhỏ hơn khi cột được đưa off-page |
| Record trong clustered index | Có thể chứa phần đầu của nhiều cột dài | Có thể chỉ chứa con trỏ cho các cột dài off-page |
| Hệ quả | Có thể giảm số hàng quá lớn bằng overflow nhưng vẫn giữ inline prefix | Có thể tăng số record vừa page và giảm áp lực kích thước record |

Ví dụ:

~~~sql
CREATE TABLE articles_dynamic (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(200) NOT NULL,
    body LONGTEXT,
    metadata JSON,
    PRIMARY KEY (article_id)
) ENGINE = InnoDB
  ROW_FORMAT = DYNAMIC;
~~~

DYNAMIC hữu ích với bảng có BLOB, TEXT, JSON hoặc VARCHAR dài. Tuy nhiên, không phải mọi giá trị của cột dài đều luôn bị đưa off-page. InnoDB quyết định dựa trên kích thước hàng và khả năng chứa record trong page; giá trị ngắn có thể vẫn được lưu inline.

Không nên diễn giải DYNAMIC là “mọi cột VARCHAR/TEXT đều luôn nằm ngoài trang”. Quyết định off-page phụ thuộc kích thước hàng và nhu cầu làm cho record phù hợp với page.

## 5. COMPRESSED: row format kết hợp nén page

COMPRESSED sử dụng cách tổ chức dữ liệu dài tương tự DYNAMIC và thêm cơ chế nén page. Khi page được ghi xuống tablespace, InnoDB cố gắng nén dữ liệu để page chiếm ít dung lượng hơn.

Kích thước page nén mục tiêu được điều khiển bởi KEY_BLOCK_SIZE. Ví dụ với page size mặc định 16 KB:

~~~sql
CREATE TABLE archived_articles (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(200) NOT NULL,
    body LONGTEXT,
    PRIMARY KEY (article_id)
) ENGINE = InnoDB
  ROW_FORMAT = COMPRESSED
  KEY_BLOCK_SIZE = 8;
~~~

KEY_BLOCK_SIZE = 8 chỉ định kích thước page nén mục tiêu 8 KB. Nó không có nghĩa mỗi hàng hoặc mỗi cột bị giới hạn ở 8 KB. Page gốc vẫn được InnoDB xử lý theo kích thước page của instance; page nén được lưu theo kích thước mục tiêu.

Nếu bỏ KEY_BLOCK_SIZE, InnoDB dùng giá trị mặc định bằng một nửa innodb_page_size. Với page size 16 KB, giá trị mặc định thường là 8 KB.

### 5.1. Nén có lợi khi nào?

Nén có thể phù hợp khi:

- Dữ liệu có nhiều chuỗi lặp, văn bản, JSON hoặc nội dung có khả năng nén tốt.
- Bảng lớn và chi phí lưu trữ hoặc I/O là nút thắt.
- Workload đọc/ghi có thể chấp nhận chi phí CPU bổ sung.
- Đã benchmark với phân bố dữ liệu và kích thước page đại diện production.

Nén có thể không có lợi khi:

- Dữ liệu đã nén sẵn như ảnh JPEG, video hoặc dữ liệu mã hóa.
- Workload bị giới hạn CPU.
- Page thay đổi thường xuyên và việc nén lại gây thêm chi phí.
- Mức tiết kiệm dung lượng thấp so với chi phí vận hành.

Không thể kết luận COMPRESSED luôn nhanh hơn DYNAMIC. Dung lượng nhỏ hơn có thể giảm I/O, nhưng nén và giải nén làm tăng công việc CPU và có thể ảnh hưởng độ trễ.

### 5.2. KEY_BLOCK_SIZE

KEY_BLOCK_SIZE là kích thước page nén tính bằng KB. Các giá trị thường dùng là 1, 2, 4, 8 và 16 KB, trong giới hạn được hỗ trợ bởi innodb_page_size và phiên bản MySQL.

Ví dụ với page size 16 KB:

| Cấu hình | Ý nghĩa |
|---|---|
| KEY_BLOCK_SIZE = 8 | Page nén mục tiêu 8 KB |
| KEY_BLOCK_SIZE = 4 | Page nén mục tiêu 4 KB |
| KEY_BLOCK_SIZE = 2 | Page nén mục tiêu 2 KB |

Page nén càng nhỏ thì tỷ lệ nén yêu cầu càng cao. Nếu dữ liệu không thể nén đến kích thước mục tiêu, InnoDB có thể cần xử lý nén lại, sử dụng padding hoặc gặp tình trạng nén không đạt mục tiêu. Chọn giá trị quá nhỏ có thể làm tăng chi phí CPU và ghi.

Với instance dùng innodb_page_size 32 KB hoặc 64 KB, COMPRESSED row format không được hỗ trợ. Hãy xác nhận @@innodb_page_size trước khi thiết kế bảng nén.

## 6. Điều kiện tương thích theo phiên bản MySQL

Các giới hạn row format thay đổi qua các phiên bản.

### 6.1. Antelope và Barracuda trong các bản cũ

Trong các phiên bản MySQL cũ, InnoDB dùng khái niệm file format:

- **Antelope** hỗ trợ REDUNDANT và COMPACT.
- **Barracuda** bổ sung DYNAMIC và COMPRESSED.

Ở các bản cũ, muốn sử dụng DYNAMIC hoặc COMPRESSED có thể phải bật file format Barracuda và cấu hình liên quan như innodb_file_per_table. Giới hạn độ dài index prefix cũng có thể phụ thuộc innodb_large_prefix.

### 6.2. MySQL 5.7 và MySQL 8.0

Trong các bản MySQL 5.7 mới và MySQL 8.0, các cơ chế file format cũ đã được đơn giản hóa. MySQL 8.0 loại bỏ các cấu hình innodb_file_format và innodb_large_prefix; không cần bật Barracuda hoặc large prefix thủ công như hướng dẫn dành cho MySQL 5.6.

innodb_default_row_format điều khiển row format mặc định khi tạo bảng mà không chỉ định rõ. Trên MySQL hiện đại, mặc định thường là DYNAMIC.

Không áp dụng máy móc hướng dẫn cấu hình của MySQL 5.6 cho MySQL 8.0. Trước khi thay đổi cấu hình production, kiểm tra phiên bản thực tế và tài liệu tương ứng với bản phát hành đó.

## 7. Điều kiện tablespace và page size cho COMPRESSED

COMPRESSED row format không được hỗ trợ trong system tablespace. Trong các phiên bản hiện đại, bảng nén có thể được đặt trong file-per-table tablespace hoặc general tablespace nếu các điều kiện tương thích khác được đáp ứng.

Một số điểm cần xác nhận:

- innodb_file_per_table có bật nếu thiết kế dựa trên file-per-table không.
- Bảng có đang nằm trong system tablespace hay không.
- innodb_page_size có thuộc nhóm được hỗ trợ cho COMPRESSED không; page size 32 KB và 64 KB không hỗ trợ COMPRESSED.
- KEY_BLOCK_SIZE có hợp lệ với page size và phiên bản server không.
- Các tùy chọn tablespace có tương thích với row format đã chọn không.

Không phải mọi cấu hình page size đều có thể đổi sau khi khởi tạo instance. innodb_page_size là thuộc tính cố định của data directory đã khởi tạo; muốn đổi page size thường cần tạo instance mới và di chuyển dữ liệu.

## 8. Row format và giới hạn độ dài index

Row format ảnh hưởng đến giới hạn độ dài khóa index tối đa của InnoDB trong các cấu hình liên quan.

Với page size 16 KB:

| Row format | Giới hạn khóa index tối đa thường gặp |
|---|---:|
| REDUNDANT | 767 byte |
| COMPACT | 767 byte |
| DYNAMIC | 3072 byte |
| COMPRESSED | 3072 byte |

Giới hạn thực tế còn phụ thuộc innodb_page_size, phiên bản MySQL và cấu hình tương thích. Với page size 8 KB, giới hạn tối đa tương ứng thấp hơn (thường 1536 byte cho row format hỗ trợ large prefix); với page size 4 KB là 768 byte.

### 8.1. Ảnh hưởng với utf8mb4

utf8mb4 có thể cần tối đa 4 byte cho mỗi ký tự. Vì vậy, độ dài index prefix theo số ký tự không bằng độ dài theo byte.

Ví dụ:

~~~sql
CREATE TABLE customer_names (
    customer_id BIGINT UNSIGNED NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_display_name (display_name)
) ENGINE = InnoDB
  ROW_FORMAT = DYNAMIC
  DEFAULT CHARSET = utf8mb4;
~~~

Với DYNAMIC và page size 16 KB, giới hạn 3072 byte thường đủ cho index trên VARCHAR(255) utf8mb4 (tối đa 1020 byte cho phần ký tự, chưa tính overhead). Với COMPACT, giới hạn 767 byte có thể khiến index toàn cột quá dài.

Nếu cần tương thích với row format có giới hạn 767 byte, có thể dùng prefix index khi phù hợp:

~~~sql
CREATE INDEX idx_display_name_prefix
ON customer_names (display_name(191));
~~~

Prefix index chỉ lưu và so sánh phần đầu của chuỗi trong index; nó có thể không đủ phân biệt các giá trị có cùng prefix và không thay thế hoàn toàn index trên toàn bộ cột. Hãy chọn prefix dựa trên phân bố dữ liệu và điều kiện truy vấn.

### 8.2. Giới hạn khóa không phải giới hạn kích thước hàng

Không nhầm giới hạn 3072 byte của index key với giới hạn row size. Đây là hai giới hạn khác nhau:

- Index key limit giới hạn tổng độ dài các cột trong một khóa index.
- Row size limit giới hạn dữ liệu inline của một hàng trong clustered index page và giới hạn ở tầng SQL.

Đổi sang DYNAMIC có thể giải quyết một số vấn đề lưu trữ cột dài và cho phép index key dài hơn trong cấu hình phù hợp, nhưng không làm cho mọi thiết kế index hoặc mọi hàng có kích thước tùy ý.

## 9. Giới hạn kích thước hàng và cột off-page

MySQL có giới hạn kích thước hàng ở tầng SQL khoảng 65.535 byte, không tính đầy đủ nội dung BLOB/TEXT được xử lý riêng. InnoDB còn có giới hạn kích thước record inline trong page: dữ liệu record phải vừa với phần dung lượng mà page có thể dành cho một hàng, thường xấp xỉ một nửa page sau khi trừ overhead.

Khi hàng có nhiều cột biến thiên lớn, InnoDB có thể đưa một số cột ra off-page để record inline vừa page. DYNAMIC và COMPRESSED có lợi thế vì có thể đưa toàn bộ giá trị cột dài ra ngoài trang khi cột đó được chọn để overflow.

Nếu vẫn có quá nhiều cột cố định hoặc cột ngắn cần lưu inline, CREATE TABLE hoặc INSERT/UPDATE có thể gặp lỗi row size too large.

Thiết kế bảng nên:

- Tránh tạo quá nhiều cột VARCHAR rất lớn nếu nghiệp vụ không cần.
- Tách dữ liệu lớn ít được truy cập khỏi bảng thường xuyên đọc nếu hợp lý.
- Chọn DYNAMIC cho bảng có nhiều cột dài.
- Đo kích thước thực tế và thử INSERT các giá trị biên.
- Không dựa vào việc đổi row format để thay thế thiết kế schema hợp lý.

## 10. Khai báo row format khi tạo bảng

Có thể chỉ định row format trong CREATE TABLE:

~~~sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content LONGTEXT,
    PRIMARY KEY (document_id)
) ENGINE = InnoDB
  ROW_FORMAT = DYNAMIC;
~~~

Tạo bảng dùng COMPACT:

~~~sql
CREATE TABLE legacy_documents (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content LONGTEXT,
    PRIMARY KEY (document_id)
) ENGINE = InnoDB
  ROW_FORMAT = COMPACT;
~~~

Tạo bảng dùng COMPRESSED:

~~~sql
CREATE TABLE cold_documents (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content LONGTEXT,
    PRIMARY KEY (document_id)
) ENGINE = InnoDB
  ROW_FORMAT = COMPRESSED
  KEY_BLOCK_SIZE = 8;
~~~

Nếu bỏ ROW_FORMAT, InnoDB dùng innodb_default_row_format tại thời điểm tạo bảng. Chỉ rõ row format giúp schema có ý định rõ ràng hơn, đặc biệt khi ứng dụng cần tính tương thích giữa các môi trường.

## 11. Thay đổi row format của bảng hiện có

Có thể yêu cầu InnoDB chuyển bảng sang row format khác bằng ALTER TABLE:

~~~sql
ALTER TABLE documents
ROW_FORMAT = DYNAMIC;
~~~

Chuyển sang COMPRESSED:

~~~sql
ALTER TABLE cold_documents
ROW_FORMAT = COMPRESSED,
KEY_BLOCK_SIZE = 8;
~~~

Thay đổi row format thường yêu cầu xây dựng lại cấu trúc vật lý của bảng. Với bảng lớn, thao tác có thể tiêu tốn thời gian, I/O, CPU và dung lượng tạm; đồng thời có thể cần metadata lock. Khả năng thực hiện online và thuật toán DDL phụ thuộc phiên bản, thao tác cụ thể và cấu trúc bảng.

Trước khi chạy trên production:

1. Kiểm tra kích thước bảng và dung lượng trống.
2. Kiểm tra phiên bản MySQL và khả năng DDL online cho thao tác đó.
3. Thử trên bản sao dữ liệu có kích thước gần production.
4. Xác định thời gian khóa metadata và ảnh hưởng đến ứng dụng.
5. Chuẩn bị backup và phương án rollback/restore.
6. Chạy trong cửa sổ bảo trì nếu không thể bảo đảm tác động chấp nhận được.

Không mặc định ALTER TABLE ... ROW_FORMAT luôn là INSTANT hoặc luôn không khóa. Nếu cần chỉ định ALGORITHM/LOCK, hãy kiểm tra hỗ trợ của phiên bản trước; yêu cầu một thuật toán không được hỗ trợ sẽ khiến câu lệnh thất bại thay vì tự động trở nên an toàn.

## 12. Kiểm tra row format đang dùng

### 12.1. SHOW CREATE TABLE

~~~sql
SHOW CREATE TABLE documents;
~~~

Đây là cách xem DDL mà server lưu cho bảng, bao gồm engine, charset, collation và các tùy chọn row format nếu được thể hiện.

### 12.2. SHOW TABLE STATUS

~~~sql
SHOW TABLE STATUS LIKE 'documents';
~~~

Cột Row_format cho biết row format hiện tại, ví dụ Dynamic, Compact hoặc Compressed.

### 12.3. INFORMATION_SCHEMA.TABLES

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    ROW_FORMAT,
    CREATE_OPTIONS,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'documents';
~~~

TABLE_ROWS của InnoDB thường là ước lượng, không phải lúc nào cũng là số hàng chính xác. DATA_LENGTH và INDEX_LENGTH thể hiện dung lượng ước lượng theo metadata của engine.

### 12.4. Kiểm tra cấu hình instance

~~~sql
SELECT
    @@version AS mysql_version,
    @@innodb_default_row_format AS default_row_format,
    @@innodb_page_size AS innodb_page_size,
    @@innodb_file_per_table AS file_per_table;
~~~

Các biến và giá trị có thể khác nhau theo phiên bản, bản phân phối hoặc cấu hình. Nếu một biến không tồn tại ở phiên bản cũ/mới đang dùng, hãy kiểm tra tài liệu tương ứng thay vì giả định mọi instance có cùng danh sách biến.

## 13. Phân biệt row compression với page compression

ROW_FORMAT=COMPRESSED là định dạng nén bảng truyền thống của InnoDB, thường kết hợp KEY_BLOCK_SIZE để xác định kích thước page nén.

MySQL cũng có tính năng InnoDB page compression được cấu hình bằng tùy chọn bảng COMPRESSION, ví dụ COMPRESSION='zlib' hoặc thuật toán khác được phiên bản hỗ trợ. Page compression dựa vào khả năng lưu file dạng sparse và filesystem/storage hỗ trợ punch-hole. Cơ chế này khác với COMPRESSED row format.

Không dùng hai khái niệm thay thế cho nhau:

| Tính năng | ROW_FORMAT=COMPRESSED | Page compression |
|---|---|---|
| Cấu hình chính | ROW_FORMAT và KEY_BLOCK_SIZE | Tùy chọn COMPRESSION |
| Cơ chế | Page nén theo kích thước khối mục tiêu | Nén page và giải phóng phần không dùng trong file nếu storage hỗ trợ |
| Phụ thuộc filesystem sparse/punch-hole | Không phải điều kiện cốt lõi của cơ chế truyền thống | Có |
| Mục tiêu | Giảm kích thước page lưu trữ bằng compressed page format | Giảm dung lượng file trên storage |

Khả năng hỗ trợ thuật toán và điều kiện filesystem phụ thuộc phiên bản, hệ điều hành và thiết bị lưu trữ. Hãy xác nhận trong môi trường triển khai trước khi chọn page compression.

## 14. Đo lường trước khi chọn row format

Đừng chỉ so sánh kích thước file sau khi tạo bảng. Cần đo cả dung lượng, CPU, I/O và độ trễ.

Một thử nghiệm có thể thực hiện trên ba bảng cùng schema và cùng dữ liệu:

~~~sql
CREATE TABLE docs_compact (
    id BIGINT UNSIGNED NOT NULL,
    body LONGTEXT,
    PRIMARY KEY (id)
) ENGINE = InnoDB ROW_FORMAT = COMPACT;

CREATE TABLE docs_dynamic (
    id BIGINT UNSIGNED NOT NULL,
    body LONGTEXT,
    PRIMARY KEY (id)
) ENGINE = InnoDB ROW_FORMAT = DYNAMIC;

CREATE TABLE docs_compressed (
    id BIGINT UNSIGNED NOT NULL,
    body LONGTEXT,
    PRIMARY KEY (id)
) ENGINE = InnoDB
  ROW_FORMAT = COMPRESSED
  KEY_BLOCK_SIZE = 8;
~~~

Nạp cùng một tập dữ liệu vào từng bảng. Dữ liệu thử nghiệm nên gồm:

- Nội dung văn bản có nhiều đoạn lặp để kiểm tra khả năng nén.
- Nội dung đã nén hoặc gần ngẫu nhiên để quan sát trường hợp khó nén.
- Các giá trị ngắn và dài.
- Một số hàng có nhiều cột lớn nếu schema thực tế có dạng đó.

Đo các chỉ số:

| Chỉ số | Ý nghĩa |
|---|---|
| DATA_LENGTH | Dung lượng dữ liệu theo metadata của InnoDB |
| INDEX_LENGTH | Dung lượng index |
| Kích thước tablespace trên filesystem | Dung lượng lưu trữ thực tế |
| Thời gian INSERT/UPDATE | Chi phí ghi và nén |
| CPU | Chi phí nén/giải nén |
| Throughput SELECT | Khả năng phục vụ workload đọc |
| p95/p99 latency | Ảnh hưởng đến độ trễ thực tế |
| Buffer pool và I/O | Khả năng tận dụng bộ nhớ và thiết bị lưu trữ |

Chạy benchmark với cache nóng và lạnh nếu workload có cả hai trạng thái. Lặp lại nhiều lần, giữ nguyên phiên bản server, cấu hình buffer pool, dữ liệu và tải đồng thời để kết quả có thể so sánh.

## 15. Lỗi thường gặp

**“DYNAMIC luôn đưa mọi VARCHAR/TEXT ra off-page.”** Không. InnoDB chỉ đưa cột ra ngoài trang khi cần để record vừa page; giá trị ngắn có thể được giữ inline.

**“COMPACT lưu toàn bộ BLOB/TEXT inline.”** Không. Khi cột dài được chọn off-page, COMPACT giữ tối đa 768 byte đầu trong record và phần còn lại ngoài trang.

**“DYNAMIC luôn nhanh hơn COMPACT.”** Không có bảo đảm. DYNAMIC có thể giảm record inline với cột dài, nhưng hiệu năng thực tế phụ thuộc truy vấn, dữ liệu và cache.

**“COMPRESSED luôn giảm tổng thời gian truy vấn.”** Không. Nó có thể giảm I/O và dung lượng nhưng tăng CPU nén/giải nén.

**“KEY_BLOCK_SIZE là giới hạn kích thước một hàng.”** Không. Đây là kích thước page nén mục tiêu, tính bằng KB.

**“Có thể dùng COMPRESSED với mọi innodb_page_size.”** Không. Page size 32 KB và 64 KB không hỗ trợ COMPRESSED row format.

**“MySQL 8.0 vẫn cần bật Barracuda và innodb_large_prefix.”** Không. Các thiết lập file format cũ đã bị loại bỏ; không áp dụng hướng dẫn cấu hình MySQL 5.6 cho MySQL 8.0.

**“Đổi ROW_FORMAT chỉ sửa metadata.”** Không. Thao tác thường phải xây dựng lại cấu trúc vật lý và có thể tiêu tốn tài nguyên, thời gian, dung lượng tạm và metadata lock.

**“3072 byte là giới hạn kích thước cả hàng.”** Không. Đây là giới hạn index key trong cấu hình phù hợp; row size có giới hạn riêng.

**“COMPRESSED row format và page compression là một tính năng.”** Không. Chúng là hai cơ chế khác nhau, có tùy chọn và điều kiện triển khai khác nhau.

## 16. Checklist chọn row format

- [ ] Đã xác định phiên bản MySQL và storage engine thực tế.
- [ ] Đã kiểm tra innodb_default_row_format và innodb_page_size.
- [ ] Đã xác định bảng có nhiều cột dài hay không.
- [ ] Đã hiểu COMPACT giữ prefix 768 byte khi cột dài được đưa off-page.
- [ ] Đã hiểu DYNAMIC có thể lưu toàn bộ cột dài off-page.
- [ ] Đã xác nhận điều kiện tablespace và page size nếu dùng COMPRESSED.
- [ ] Đã kiểm tra giới hạn index key theo row format, charset và page size.
- [ ] Đã thử dữ liệu biên để phát hiện lỗi row size too large.
- [ ] Đã benchmark dung lượng, CPU, I/O, throughput và p95/p99.
- [ ] Đã đánh giá thời gian, metadata lock và dung lượng cần thiết khi ALTER TABLE.
- [ ] Đã phân biệt COMPRESSED row format với page compression.
- [ ] Đã xác minh row format thực tế bằng SHOW CREATE TABLE hoặc INFORMATION_SCHEMA.

## Kết luận

COMPACT giữ tối đa 768 byte đầu của cột dài trong clustered index record khi cột đó được lưu off-page; DYNAMIC có thể đưa toàn bộ giá trị cột dài ra ngoài trang và giữ con trỏ trong record. COMPRESSED sử dụng cách lưu cột dài tương tự DYNAMIC và bổ sung nén page với KEY_BLOCK_SIZE.

Trên MySQL hiện đại, DYNAMIC thường là lựa chọn mặc định hợp lý. COMPRESSED chỉ nên chọn sau khi xác nhận page size, tablespace và phiên bản hỗ trợ, rồi đo hiệu quả trên workload thực tế. Hãy kiểm tra row format, giới hạn index, kích thước hàng và tác động DDL trước khi triển khai thay đổi trên production.
