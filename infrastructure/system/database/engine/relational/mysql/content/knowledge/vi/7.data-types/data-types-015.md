# Giới hạn kích thước dòng, độ dài khóa và dữ liệu lưu ngoài trang

Khi thiết kế bảng InnoDB, cần quan tâm đồng thời đến ba giới hạn: kích thước một dòng dữ liệu, độ dài khóa trong index và cách lưu các cột có giá trị lớn. Một bảng có thể khai báo nhiều cột `VARCHAR`, `TEXT` hoặc `BLOB`, nhưng điều đó không có nghĩa mọi byte của mọi cột đều nằm trực tiếp trong một trang dữ liệu. InnoDB có thể chuyển một phần dữ liệu dài sang trang overflow (off-page) và giữ con trỏ trong bản ghi trên trang chính.

Các giới hạn này tác động tới thiết kế schema, index, khóa chính, hiệu năng truy vấn và dung lượng lưu trữ. Trong module `DATABASE_MYSQL`, hiểu rõ chúng giúp tránh lỗi `Row size too large`, lỗi độ dài index, đồng thời chọn đúng kiểu dữ liệu cho ứng dụng cần lưu nội dung lớn.

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt giới hạn kích thước dòng ở tầng SQL với giới hạn bản ghi vật lý của InnoDB.
- Giải thích quan hệ giữa page size, row format và dữ liệu lưu ngoài trang.
- So sánh `COMPACT`, `DYNAMIC` và `COMPRESSED` khi lưu cột dài.
- Tính gần đúng độ dài khóa index theo charset và độ dài cột.
- Thiết kế khóa chính gọn, composite index và prefix index phù hợp.
- Chẩn đoán lỗi row size/index key và kiểm tra cấu trúc bảng bằng metadata của MySQL.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Giới hạn hoặc cơ chế liên quan |
|---|---|---|
| Kích thước dòng ở tầng SQL | Tổng kích thước tối đa của các cột trong định nghĩa dòng theo quy tắc MySQL | MySQL có giới hạn row size 65.535 byte; `BLOB`/`TEXT` được tính chủ yếu bằng phần metadata/con trỏ, không phải toàn bộ nội dung |
| Bản ghi InnoDB trên page | Phần dữ liệu và metadata của bản ghi nằm trong trang InnoDB | Kích thước bản ghi inline bị giới hạn bởi page size; với page 16KB, giới hạn thường được mô tả là hơi nhỏ hơn một nửa trang, khoảng 8KB |
| Độ dài khóa index | Số byte tối đa của các cột/prefix tham gia vào một khóa index | Phụ thuộc page size, row format, charset và tổng độ dài của các thành phần khóa |

Ba giới hạn này không thay thế cho nhau. Một bảng có thể vượt giới hạn 65.535 byte ở tầng SQL dù InnoDB có khả năng lưu một số cột ngoài trang. Ngược lại, định nghĩa bảng có thể qua được giới hạn SQL nhưng khi tạo hoặc ghi dữ liệu lại gặp giới hạn bản ghi InnoDB inline. Index cũng có giới hạn riêng, kể cả khi dữ liệu của cột được lưu ngoài trang.

## 2. Giới hạn kích thước dòng ở tầng SQL

MySQL giới hạn kích thước dòng tối đa ở tầng SQL là 65.535 byte. Khi tính giới hạn này, MySQL xét độ dài tối đa của các cột và phần overhead cần thiết. Đối với `VARCHAR`, độ dài khai báo là số ký tự, nhưng dung lượng tối đa tính theo byte phụ thuộc character set.

Ví dụ, `VARCHAR(255)` dùng `utf8mb4` có thể cần tối đa 1.020 byte dữ liệu vì một ký tự có thể chiếm tới 4 byte. Một cột `VARCHAR` còn có byte lưu độ dài và các metadata khác. Do đó, không thể cộng đơn giản số ký tự rồi kết luận bảng nằm trong giới hạn.

```sql
CREATE TABLE profile_text (
    id BIGINT UNSIGNED NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    biography VARCHAR(1000),
    PRIMARY KEY (id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

`VARCHAR(1000)` cho phép tối đa 1.000 ký tự, không có nghĩa mọi dòng đều chiếm 4.000 byte cho cột này. Khi lưu dữ liệu, `VARCHAR` thường dùng độ dài thực tế cộng phần overhead độ dài; khi kiểm tra khả năng chứa của định nghĩa bảng, cần xét giới hạn tối đa.

### 2.1. Vì sao `TEXT` và `BLOB` khác `VARCHAR`?

`TEXT` và `BLOB` được thiết kế cho nội dung dài. Trong phép tính giới hạn row size của MySQL, nội dung của các cột này không được tính toàn bộ như một `VARCHAR` inline; chỉ một phần nhỏ metadata/con trỏ (thường khoảng 9–12 byte tùy loại) được tính vào kích thước dòng SQL. Nội dung lớn được lưu theo cơ chế riêng của storage engine.

Điều này giúp bảng có thể chứa nhiều cột nội dung lớn mà không vượt giới hạn SQL row size ngay khi khai báo. Tuy nhiên, nó không làm dữ liệu trở nên miễn phí: nội dung vẫn chiếm dung lượng tablespace, có thể cần trang overflow, I/O bổ sung và bộ nhớ khi truy vấn.

Không đổi mọi `VARCHAR` lớn thành `TEXT` chỉ để tránh lỗi. Hãy cân nhắc semantics, giới hạn độ dài, khả năng index, default value theo phiên bản MySQL, cách ứng dụng validate và workload đọc/ghi.

### 2.2. Ví dụ bảng vượt giới hạn SQL row size

Một bảng có nhiều cột `VARCHAR(255)` trên `utf8mb4` có thể vượt 65.535 byte dù mỗi cột trông có vẻ ngắn:

```sql
-- Ví dụ minh họa định nghĩa có thể vượt giới hạn row size của MySQL.
CREATE TABLE wide_profile (
    id BIGINT UNSIGNED NOT NULL,
    field_01 VARCHAR(255),
    field_02 VARCHAR(255),
    field_03 VARCHAR(255),
    field_04 VARCHAR(255),
    field_05 VARCHAR(255),
    field_06 VARCHAR(255),
    field_07 VARCHAR(255),
    field_08 VARCHAR(255),
    field_09 VARCHAR(255),
    field_10 VARCHAR(255),
    -- Trong schema thật, lặp nhiều cột tương tự có thể vượt 65.535 byte.
    PRIMARY KEY (id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Mười cột ở ví dụ này chưa chắc vượt giới hạn; số cột cần thiết phụ thuộc kiểu, charset và overhead. Ý chính là phải tính theo byte tối đa, không phải số ký tự. Nếu cần nhiều trường nội dung độc lập, hãy cân nhắc tách bảng theo quan hệ một-một hoặc nhóm thuộc tính, hoặc dùng `TEXT` cho nội dung dài có semantics phù hợp.

## 3. Giới hạn bản ghi inline của InnoDB

InnoDB lưu dữ liệu trong page. Với cấu hình phổ biến `innodb_page_size=16384` (16KB), kích thước một bản ghi nằm trực tiếp trên page bị giới hạn ở mức hơi nhỏ hơn một nửa page, xấp xỉ 8KB. Phần chênh lệch dành cho cấu trúc page, directory, record header và metadata nội bộ. Giới hạn thực tế không phải phép tính chính xác bằng `page_size / 2` cho mọi schema.

InnoDB còn cần lưu metadata của bản ghi, chẳng hạn:

- Header và thông tin quản lý record.
- Bitmap cho các cột nullable.
- Thông tin độ dài/offset của cột biến độ dài.
- Các trường hệ thống của InnoDB như transaction ID và rollback pointer; bảng không khai báo primary key còn có hidden row ID.

Vì vậy, dung lượng dành cho dữ liệu người dùng luôn nhỏ hơn kích thước page và phụ thuộc vào cấu trúc dòng.

### 3.1. Page size ảnh hưởng như thế nào?

Kiểm tra page size của instance:

```sql
SELECT @@innodb_page_size;
```

MySQL/InnoDB hỗ trợ một số page size được chọn khi khởi tạo instance, thường là 4KB, 8KB, 16KB, 32KB hoặc 64KB tùy nền tảng/bản dựng. Giá trị mặc định phổ biến là 16KB. `innodb_page_size` không phải tham số có thể đổi tùy ý cho một instance đã có data directory; muốn dùng page size khác thường phải tạo instance mới và di chuyển dữ liệu theo kế hoạch.

Không tăng page size chỉ để chữa một lỗi row size. Page size còn ảnh hưởng tới index key limit, I/O, dung lượng page và khả năng tương thích với các tính năng lưu trữ. Hãy đánh giá toàn bộ workload và giới hạn của phiên bản trước khi chọn page size.

### 3.2. Lỗi `Row size too large`

Khi bản ghi inline có thể vượt giới hạn, MySQL có thể trả lỗi dạng:

```text
ERROR 1118 (42000): Row size too large (...).
```

Thông báo thường chỉ ra ngưỡng của page/row format hiện tại. Không nên xử lý bằng cách tắt strict mode hoặc ép server chấp nhận schema. Hãy kiểm tra kiểu cột, charset, row format và khả năng chuyển các cột dài sang off-page storage.

## 4. Row format và dữ liệu lưu ngoài trang

InnoDB có các row format như `REDUNDANT`, `COMPACT`, `DYNAMIC` và `COMPRESSED`. Trong các phiên bản MySQL 8.0 phổ biến, `DYNAMIC` là row format mặc định. Row format quyết định cách record được mã hóa và cách cột dài được lưu inline hoặc ngoài trang.

| Row format | Đặc điểm liên quan tới cột dài |
|---|---|
| `REDUNDANT` | Row format cũ, dùng cấu trúc record legacy; không nên chọn cho bảng mới nếu không có lý do tương thích cụ thể |
| `COMPACT` | Giữ tối đa 768 byte đầu của giá trị `BLOB`/`TEXT` inline trong record clustered index và phần còn lại ở trang overflow; record giữ con trỏ 20 byte |
| `DYNAMIC` | Có thể lưu toàn bộ giá trị cột dài ngoài trang và giữ con trỏ 20 byte trong record khi cần; giảm dữ liệu dài nằm inline |
| `COMPRESSED` | Dựa trên cách tổ chức record tương tự `COMPACT`/`DYNAMIC` cùng cơ chế nén page; việc nén và off-page phụ thuộc cấu hình, page size và phiên bản |

### 4.1. COMPACT: giữ prefix inline

Với `COMPACT`, InnoDB lưu 768 byte đầu của giá trị `BLOB`/`TEXT` inline trong clustered index record; phần còn lại có thể nằm trên overflow page. Record chứa con trỏ 20 byte trỏ tới phần ngoài trang.

Điều này có nghĩa một cột `TEXT` dài có thể vẫn làm record inline lớn lên đáng kể nếu nhiều cột cùng giữ prefix. Khi bảng có nhiều cột dài, phần prefix inline của từng cột cộng lại có thể làm record vượt giới hạn.

### 4.2. DYNAMIC: chuyển toàn bộ giá trị dài ra ngoài trang

Với `DYNAMIC`, khi InnoDB cần chuyển một cột dài ra ngoài trang, toàn bộ giá trị có thể được lưu trong overflow page; record trên clustered index giữ con trỏ 20 byte. Cách này giảm lượng dữ liệu dài phải giữ inline và thường phù hợp hơn với bảng có nhiều cột `VARCHAR`, `TEXT` hoặc `BLOB` lớn.

InnoDB không nhất thiết đưa mọi cột dài ra ngoài trang ngay khi tạo bảng. Engine quyết định theo kích thước record và điều kiện lưu trữ. Những giá trị ngắn vẫn có thể nằm inline; khi record quá lớn, InnoDB chọn các cột biến độ dài phù hợp để chuyển ra ngoài trang cho đến khi record đáp ứng giới hạn.

### 4.3. COMPRESSED

`COMPRESSED` lưu page theo định dạng nén và có cơ chế xử lý cột dài/off-page riêng. Nén có thể giảm dung lượng lưu trữ và I/O, nhưng thêm chi phí CPU, có thể gây page reorganization và chịu giới hạn tương thích theo page size, filesystem và phiên bản. Không chọn `COMPRESSED` chỉ để vượt row-size limit; cần benchmark và kiểm tra tài liệu triển khai.

### 4.4. Kiểm tra và đổi row format

Xem row format hiện tại:

```sql
SHOW TABLE STATUS LIKE 'profile_text'\G
SHOW CREATE TABLE profile_text\G
```

Hoặc truy vấn metadata:

```sql
SELECT TABLE_NAME, ROW_FORMAT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'profile_text';
```

Tạo bảng mới với `DYNAMIC`:

```sql
CREATE TABLE document_store (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    body LONGTEXT,
    attachment LONGBLOB,
    PRIMARY KEY (document_id)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARSET=utf8mb4;
```

Đổi row format cho bảng hiện có:

```sql
ALTER TABLE profile_text ROW_FORMAT=DYNAMIC;
```

Thay đổi row format có thể rebuild bảng, tạo I/O lớn và cần không gian tạm. Hãy thử trên bản sao, kiểm tra thuật toán DDL được hỗ trợ, thời gian lock và dung lượng trống trước khi thực hiện trên production.

## 5. Độ dài khóa index

InnoDB giới hạn độ dài tối đa của một index key theo page size và row format. Với page size 16KB, giới hạn phổ biến của DYNAMIC/COMPRESSED là 3.072 byte; với page size 8KB là 1.536 byte; với page size 4KB là 768 byte. Row format `REDUNDANT` và `COMPACT` có giới hạn legacy 767 byte cho index key trong các cấu hình tương ứng.

Các giới hạn này tính theo byte, không phải số ký tự. Với charset `utf8mb4`, một ký tự có thể chiếm tối đa 4 byte. Vì vậy, một index trên `VARCHAR(1000)` dùng `utf8mb4` có thể cần tới 4.000 byte cho riêng phần dữ liệu ký tự, vượt giới hạn 3.072 byte ở page 16KB.

### 5.1. Ví dụ index quá dài

```sql
CREATE TABLE customer_directory (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(1000) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_customer_email (email)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARSET=utf8mb4;
```

Index toàn bộ `email` có thể vượt giới hạn khóa vì `VARCHAR(1000)` trên `utf8mb4` có thể cần tới 4.000 byte, chưa kể overhead độ dài. Server có thể báo:

```text
ERROR 1071 (42000): Specified key was too long; max key length is ... bytes
```

### 5.2. Prefix index

Với cột `VARCHAR`, `TEXT` hoặc `BLOB`, có thể tạo index trên một prefix khi nghiệp vụ và truy vấn cho phép:

```sql
CREATE TABLE customer_directory (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(1000) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_customer_email_prefix (email(191))
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARSET=utf8mb4;
```

Prefix `191` là số ký tự cho cột chuỗi nonbinary; với `utf8mb4`, phần ký tự có thể cần tối đa 764 byte. Con số 191 thường xuất hiện trong schema cũ vì 191 × 4 = 764, nằm dưới giới hạn legacy 767 byte. Trên cấu hình hiện đại có giới hạn 3.072 byte, có thể chọn prefix dài hơn nếu cần, nhưng phải tính tổng key bytes và đánh giá tính chọn lọc.

Prefix index không lưu toàn bộ giá trị cột. Nếu truy vấn cần phân biệt hai email có cùng 191 ký tự đầu, MySQL có thể phải đọc bản ghi và kiểm tra phần còn lại. Index vẫn có thể hỗ trợ tìm kiếm, nhưng hiệu quả phụ thuộc phân bố dữ liệu và truy vấn thực tế.

Đối với `TEXT` và `BLOB`, MySQL yêu cầu chỉ định prefix length khi tạo index. Với `VARCHAR`, prefix length là tùy chọn. Không dùng prefix quá ngắn nếu nhiều giá trị trùng prefix, vì selectivity thấp sẽ làm index kém hiệu quả.

### 5.3. Composite index tính tổng độ dài các thành phần

Độ dài khóa của composite index là tổng byte tối đa của các thành phần tham gia, cùng phần overhead liên quan. Không thể giả định mỗi cột đều được phép dùng trọn giới hạn 3.072 byte.

Ví dụ:

```sql
CREATE TABLE tenant_contact (
    contact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(800) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    PRIMARY KEY (contact_id),
    KEY idx_tenant_email (tenant_id, email(150)),
    KEY idx_tenant_name (tenant_id, display_name(150))
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARSET=utf8mb4;
```

Trong index `idx_tenant_name`, `tenant_id` dùng 8 byte và prefix `display_name(150)` có thể dùng tới 600 byte cho ký tự `utf8mb4`, cộng overhead. Khi thiết kế composite index, cần cộng tất cả cột/prefix, xác định thứ tự cột theo truy vấn và giữ tổng độ dài dưới giới hạn của cấu hình.

## 6. Khóa chính rộng làm index phụ lớn hơn

InnoDB dùng clustered index để lưu hàng theo primary key. Mỗi secondary index cũng lưu giá trị primary key tương ứng để tìm bản ghi trong clustered index. Do đó, khóa chính không chỉ ảnh hưởng tới primary index; nó còn ảnh hưởng tới kích thước của mọi secondary index.

Ví dụ, bảng có primary key `BIGINT` và năm secondary index sẽ lưu phần khóa chính 8 byte trong các entry của từng index phụ. Nếu khóa chính là chuỗi dài, chi phí lặp lại trong secondary index có thể lớn hơn đáng kể. Khi bảng có hàng triệu hoặc hàng tỷ bản ghi, chênh lệch này ảnh hưởng tới dung lượng, buffer pool và số page phải đọc.

Nguyên tắc thiết kế:

- Ưu tiên primary key ngắn, ổn định và ít thay đổi.
- Tránh dùng một chuỗi dài làm primary key nếu có thể dùng surrogate key gọn hơn.
- Nếu dùng composite primary key, chỉ đưa các cột cần thiết vào khóa.
- Kiểm tra các secondary index hiện có trước khi mở rộng kiểu primary key.
- Giữ kiểu và signedness của khóa ngoại tương thích với primary key được tham chiếu.

Không có nghĩa mọi bảng đều phải dùng số tự tăng. Khóa tự nhiên có thể hợp lý nếu ngắn, ổn định và duy nhất theo nghiệp vụ. Hãy so sánh chi phí lưu trữ, khả năng join, tính ổn định và nhu cầu phân tán ID.

## 7. Tính byte theo charset và metadata cột

Với kiểu chuỗi, `CHARACTER_MAXIMUM_LENGTH` biểu diễn số ký tự tối đa, còn `CHARACTER_OCTET_LENGTH` biểu diễn số byte tối đa theo charset. Có thể truy vấn metadata để ước lượng dung lượng:

```sql
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    CHARACTER_OCTET_LENGTH,
    CHARACTER_SET_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer_directory';
```

`CHARACTER_OCTET_LENGTH` hữu ích để phát hiện cột có số byte tối đa lớn hơn số ký tự khai báo. Với `utf8mb4`, giá trị tối đa thường bằng bốn lần số ký tự; với các charset khác, hệ số thay đổi.

Kiểm tra index và độ dài prefix:

```sql
SHOW INDEX FROM customer_directory;
```

Kiểm tra cấu trúc index mà optimizer sử dụng:

```sql
EXPLAIN
SELECT customer_id
FROM customer_directory
WHERE email = 'learner@example.com';
```

Trường `key_len` trong kết quả `EXPLAIN` cho biết độ dài phần khóa mà optimizer sử dụng trong access path theo byte, có thể bao gồm overhead liên quan đến NULL/độ dài biến đổi. Đây không phải lúc nào cũng là tổng độ dài tối đa của toàn bộ index; hãy đọc cùng `key`, `ref`, `rows` và định nghĩa `SHOW INDEX`.

## 8. Quy trình chẩn đoán lỗi row size và index key

Khi gặp lỗi tạo bảng hoặc index, kiểm tra theo thứ tự:

1. Xác định chính xác lỗi là row size (`1118`) hay key length (`1071`). Hai lỗi có nguyên nhân và cách xử lý khác nhau.
2. Kiểm tra `@@innodb_page_size`, `@@innodb_default_row_format` và row format thực tế của bảng.
3. Kiểm tra charset/collation của bảng và từng cột chuỗi; lấy `CHARACTER_OCTET_LENGTH` thay vì chỉ nhìn số ký tự.
4. Với row size, cộng gần đúng byte tối đa của các cột inline và tính overhead/nullability/variable length; xem cột dài nào phù hợp để tách hoặc lưu ngoài trang.
5. Với index key, tính tổng byte tối đa của tất cả cột/prefix trong index; kiểm tra primary key và composite index.
6. Xem `SHOW CREATE TABLE`, `SHOW TABLE STATUS` và `SHOW INDEX` để xác nhận cấu trúc thực tế.
7. Thử thay đổi trên môi trường lab hoặc bản sao dữ liệu có kích thước gần production, sau đó đo dung lượng và latency.

Các lệnh kiểm tra cấu hình:

```sql
SELECT
    @@innodb_page_size AS page_size_bytes,
    @@innodb_default_row_format AS default_row_format,
    @@character_set_server AS server_charset,
    @@collation_server AS server_collation;

SHOW CREATE TABLE customer_directory\G
SHOW TABLE STATUS LIKE 'customer_directory'\G
SHOW INDEX FROM customer_directory;
```

### 8.1. Hướng xử lý theo loại lỗi

| Lỗi | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `Row size too large` ở tầng SQL | Tổng byte tối đa của các cột vượt 65.535 byte | Giảm độ dài khai báo, tách bảng, chuyển cột nội dung dài sang `TEXT`/`BLOB` khi đúng semantics |
| `Row size too large` ở InnoDB | Record inline vượt giới hạn page/row format | Dùng `DYNAMIC` nếu phù hợp, giảm dữ liệu inline, tách nhóm cột dài hoặc điều chỉnh schema |
| `Specified key was too long` | Tổng byte của index key vượt giới hạn page size/row format | Dùng prefix index có chọn lọc, giảm độ dài cột, đổi charset khi phù hợp hoặc thiết kế lại composite index |
| Secondary index quá lớn | Primary key dài được lặp trong mỗi index phụ | Rút gọn primary key nếu mô hình dữ liệu cho phép, giảm số index dư thừa |

Chuyển cột sang `TEXT` có thể giúp giảm phần dữ liệu tính vào SQL row size và hỗ trợ off-page storage, nhưng index trên `TEXT` cần prefix và việc truy vấn nội dung có thể phát sinh I/O bổ sung. Tách bảng có thể làm truy vấn cần thêm join. Mỗi cách giải quyết có chi phí riêng; chọn theo access pattern.

## 9. Ví dụ thiết kế bảng chứa nội dung dài

Giả sử ứng dụng lưu tài liệu gồm metadata thường được lọc và nội dung lớn. Không nên đưa toàn bộ nội dung vào một bảng có nhiều cột `VARCHAR` dài nếu phần lớn truy vấn chỉ đọc metadata.

Một thiết kế có thể tách metadata và payload:

```sql
CREATE TABLE document (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id),
    KEY idx_document_tenant_created (tenant_id, created_at)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARSET=utf8mb4;

CREATE TABLE document_payload (
    document_id BIGINT UNSIGNED NOT NULL,
    body LONGBLOB NOT NULL,
    PRIMARY KEY (document_id),
    CONSTRAINT fk_document_payload_document
        FOREIGN KEY (document_id)
        REFERENCES document (document_id)
        ON DELETE CASCADE
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC;
```

Truy vấn danh sách tài liệu chỉ đọc metadata:

```sql
SELECT document_id, title, content_type, created_at
FROM document
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

Chỉ khi người dùng mở tài liệu, ứng dụng mới lấy payload:

```sql
SELECT body
FROM document_payload
WHERE document_id = 9001;
```

Thiết kế này tránh kéo payload lớn vào các truy vấn danh sách thường xuyên. Đổi lại, thao tác đọc đầy đủ tài liệu cần truy vấn thêm bảng payload. Nếu nội dung được truy cập gần như luôn cùng metadata, giữ chung bảng với `DYNAMIC` có thể đơn giản hơn. Hãy đo workload để quyết định.

## 10. Bài thực hành

Thực hiện trong database lab riêng, dùng MySQL 8.x và InnoDB:

1. Tạo hai bảng có cùng các cột chuỗi dài, một bảng `ROW_FORMAT=COMPACT` và một bảng `ROW_FORMAT=DYNAMIC`. Kiểm tra `SHOW TABLE STATUS` để xác nhận row format.
2. Chèn các giá trị ngắn và dài vào cột `TEXT`/`LONGTEXT`. Quan sát dung lượng bảng và index trước/sau bằng công cụ thống kê phù hợp; giải thích vì sao giá trị ngắn có thể inline còn giá trị dài có thể được lưu ngoài trang.
3. Tạo bảng có nhiều `VARCHAR(255)` với `utf8mb4`. Ước lượng row size tối đa theo byte và quan sát giới hạn khi tăng số cột trong môi trường lab.
4. Tạo index trên `VARCHAR(1000)` `utf8mb4`, ghi nhận lỗi key length nếu vượt giới hạn. Thử prefix index và so sánh `EXPLAIN`/selectivity.
5. Tạo composite index gồm một cột số và hai cột chuỗi; tính tổng byte tối đa của key và điều chỉnh prefix để nằm trong giới hạn.
6. So sánh bảng dùng primary key `INT` với `BIGINT` và một bảng dùng primary key chuỗi; tạo một vài secondary index rồi quan sát kích thước index.
7. Dùng `information_schema.COLUMNS`, `SHOW CREATE TABLE`, `SHOW INDEX` và `EXPLAIN` để lập báo cáo về row format, charset, byte length và key length.
8. Thiết kế lại một bảng rộng bằng cách tách metadata khỏi payload. So sánh số cột/byte phải đọc trong truy vấn danh sách trước và sau thay đổi.

Bạn hoàn thành bài khi giải thích được hai giới hạn row size khác nhau, dự đoán được index key bytes theo charset, xác định được lúc dữ liệu dài có thể được lưu ngoài trang và chọn được giải pháp phù hợp cho từng lỗi.

## 11. Nguyên tắc thiết kế

- Tính kích thước theo byte tối đa, không chỉ theo số ký tự khai báo.
- Phân biệt giới hạn SQL row size 65.535 byte với giới hạn record inline của InnoDB theo page size.
- Dùng `DYNAMIC` cho bảng có nhiều cột biến độ dài lớn khi phù hợp; kiểm tra row format thực tế.
- Nhớ rằng off-page storage vẫn tiêu thụ dung lượng và có thể phát sinh I/O khi đọc payload.
- Tính tổng byte của mọi thành phần trong composite index; charset `utf8mb4` có thể dùng tối đa 4 byte mỗi ký tự.
- Thiết kế primary key ngắn vì giá trị này được lưu kèm trong secondary index của InnoDB.
- Dùng prefix index khi phù hợp với selectivity và truy vấn; không cắt prefix chỉ để DDL thành công.
- Đo và thử DDL trên môi trường tương tự production trước khi thay đổi row format, page size hoặc cấu trúc bảng.
