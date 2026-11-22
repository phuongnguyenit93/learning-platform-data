# CSV, ARCHIVE, FEDERATED và điều kiện sử dụng

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích mục đích và đặc điểm lưu trữ của CSV, ARCHIVE và FEDERATED.
- Tạo và kiểm tra bảng dùng từng engine khi server có hỗ trợ.
- Nhận biết giới hạn về index, transaction, cập nhật dữ liệu và phụ thuộc mạng.
- Chọn engine phù hợp với dữ liệu trao đổi, dữ liệu lịch sử hoặc bảng truy cập từ xa.
- Phân biệt storage engine với công cụ import/export CSV, replication và giải pháp tích hợp dữ liệu.

## 1. Vai trò của các storage engine chuyên biệt

MySQL hỗ trợ nhiều storage engine. Mỗi engine quyết định cách bảng lưu trữ dữ liệu và một phần hành vi khi đọc, ghi, khóa hoặc phục hồi. InnoDB là lựa chọn phổ biến cho dữ liệu nghiệp vụ cần transaction, foreign key và cập nhật đồng thời. Một số engine khác phục vụ tình huống hẹp hơn:

- **CSV** lưu các hàng theo định dạng văn bản phân tách bằng dấu phẩy, phù hợp với một số luồng trao đổi dữ liệu đơn giản.
- **ARCHIVE** lưu dữ liệu theo hướng nén, phù hợp với dữ liệu lịch sử chủ yếu được thêm mới và đọc lại.
- **FEDERATED** cung cấp một bảng cục bộ làm giao diện truy cập tới bảng trên một MySQL server từ xa.

Các engine này không có cùng mức tính năng như InnoDB. Trước khi sử dụng, cần xác minh engine có được build hoặc cài đặt trong bản MySQL đang chạy hay không, sau đó đánh giá workload, yêu cầu toàn vẹn dữ liệu, transaction và khả năng vận hành.

```mermaid
flowchart TB
    SQL[Ứng dụng gửi SQL tới MySQL] --> TABLE[Bảng trong MySQL]
    TABLE --> CSV[CSV: dữ liệu dạng văn bản]
    TABLE --> ARC[ARCHIVE: dữ liệu nén]
    TABLE --> FED[FEDERATED: chuyển yêu cầu tới server từ xa]
    FED --> REMOTE[MySQL server từ xa và bảng thật]
```

Sơ đồ mô tả mục đích sử dụng. Với CSV và ARCHIVE, dữ liệu của bảng nằm trong vùng lưu trữ do server quản lý. Với FEDERATED, dữ liệu của bảng nằm trên server từ xa; server cục bộ giữ định nghĩa và chuyển yêu cầu qua kết nối mạng.

## 2. Kiểm tra engine có sẵn trước khi tạo bảng

Chạy các lệnh sau trên server mục tiêu:

```sql
SHOW ENGINES;
SHOW PLUGINS;
```

`SHOW ENGINES` cho biết các engine và trạng thái hỗ trợ. `SHOW PLUGINS` giúp kiểm tra plugin liên quan đã được nạp hay chưa. Tùy sản phẩm, phiên bản và cách đóng gói, CSV hoặc ARCHIVE có thể đã được tích hợp, trong khi FEDERATED có thể cần được bật hoặc cài plugin riêng. Không giả định mọi bản phân phối đều cung cấp cùng danh sách.

Có thể tra cứu metadata:

```sql
SELECT ENGINE, SUPPORT, COMMENT, TRANSACTIONS, XA, SAVEPOINTS
FROM information_schema.ENGINES
WHERE ENGINE IN ('InnoDB', 'CSV', 'ARCHIVE', 'FEDERATED');
```

Các cột trong `information_schema.ENGINES` và tên engine được công bố có thể khác theo phiên bản. Nếu engine không có hoặc trạng thái không phải `YES`/`DEFAULT`, hãy kiểm tra tài liệu cài đặt của đúng bản server trước khi tạo bảng.

Sau khi tạo bảng, xác minh engine thực tế:

```sql
SHOW CREATE TABLE table_name;

SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'table_name';
```

Không suy luận engine chỉ từ câu lệnh tạo bảng hoặc giá trị `default_storage_engine`; metadata của bảng mới cho biết engine đang sử dụng.

## 3. CSV Storage Engine

### 3.1. CSV lưu dữ liệu như thế nào?

CSV (Comma-Separated Values) Storage Engine lưu nội dung hàng theo định dạng văn bản phân tách bằng dấu phẩy. Dữ liệu có thể được đọc bằng MySQL thông qua SQL và có dạng gần gũi với những công cụ xử lý CSV thông thường.

Engine này có giới hạn đáng kể:

- Không hỗ trợ index, vì vậy truy vấn lọc hoặc nối bảng có thể phải quét dữ liệu.
- Không hỗ trợ transaction và cơ chế rollback như InnoDB.
- Không có foreign key để bảo đảm quan hệ tham chiếu.
- Không phù hợp với workload cập nhật đồng thời hoặc truy vấn cần hiệu năng cao.
- Kiểu dữ liệu và các thao tác bảng cần tuân theo giới hạn của engine; không được giả định mọi tính năng DDL của InnoDB đều có ở CSV.

CSV thường phù hợp với bảng staging nhỏ, dữ liệu trao đổi đơn giản hoặc tình huống cần một bảng mà dữ liệu được biểu diễn dưới dạng CSV. Nếu cần index, kiểm tra ràng buộc, transaction hoặc truy vấn thường xuyên, hãy nạp dữ liệu vào bảng InnoDB.

### 3.2. Tạo bảng CSV

Ví dụ tạo bảng nhận dữ liệu đơn giản:

```sql
CREATE TABLE csv_contacts (
    contact_id INT NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255),
    created_at DATETIME
) ENGINE = CSV
  DEFAULT CHARACTER SET = utf8mb4;
```

Chèn và đọc dữ liệu bằng SQL:

```sql
INSERT INTO csv_contacts (contact_id, full_name, email, created_at)
VALUES
    (1, 'Nguyen An', 'an@example.test', '2026-01-10 09:00:00'),
    (2, 'Tran Binh', 'binh@example.test', '2026-01-11 10:30:00');

SELECT contact_id, full_name, email
FROM csv_contacts;
```

Không thêm `PRIMARY KEY`, `UNIQUE` hoặc index như thể CSV có khả năng index của InnoDB. Nếu cần kiểm tra trùng lặp, hãy thực hiện ở bước xử lý dữ liệu hoặc chuyển vào bảng staging InnoDB có constraint phù hợp.

### 3.3. CSV Storage Engine không đồng nghĩa với import/export CSV

Đây là điểm cần phân biệt. Bạn không cần tạo bảng bằng engine CSV mới có thể nhập hoặc xuất file CSV. Với phần lớn quy trình ETL, cách thông dụng là dùng `LOAD DATA` để nhập dữ liệu vào bảng InnoDB và dùng `SELECT ... INTO OUTFILE` để xuất dữ liệu.

Ví dụ nạp file CSV vào bảng staging InnoDB:

```sql
CREATE TABLE contact_stage (
    contact_id INT NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255),
    created_at DATETIME
) ENGINE = InnoDB;

LOAD DATA LOCAL INFILE 'contacts.csv'
INTO TABLE contact_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(contact_id, full_name, email, created_at);
```

`LOCAL` đọc file từ máy client; nếu bỏ `LOCAL`, file được đọc theo quyền và cấu hình phía server. Cần kiểm tra `local_infile`, quyền truy cập file, định dạng dòng, dấu phân tách, dấu bao chuỗi, encoding và xử lý newline phù hợp với nguồn dữ liệu. Không mở quyền `LOCAL INFILE` rộng hơn yêu cầu bảo mật của hệ thống.

Sau khi nạp, có thể kiểm tra dữ liệu, loại bỏ dòng lỗi, chuẩn hóa kiểu và chuyển vào bảng nghiệp vụ:

```sql
SELECT COUNT(*) AS imported_rows
FROM contact_stage;

INSERT INTO contacts (contact_id, full_name, email, created_at)
SELECT contact_id, TRIM(full_name), email, created_at
FROM contact_stage;
```

Trong quy trình thực tế, cần xử lý khóa trùng, dữ liệu thiếu, giá trị ngày giờ sai và đối soát số dòng trước khi ghi vào bảng nghiệp vụ.

### 3.4. Khi nào nên và không nên dùng CSV?

| Tình huống | Đánh giá |
|---|---|
| Bảng trao đổi dữ liệu đơn giản, ít truy vấn | Có thể cân nhắc CSV nếu giới hạn engine đáp ứng được |
| Dữ liệu staging tạm thời trước khi chuyển sang InnoDB | Thường nên dùng bảng InnoDB để có kiểm tra, index và transaction; CSV chỉ phù hợp khi cần đặc tính file CSV trực tiếp |
| Bảng nghiệp vụ có cập nhật đồng thời | Không phù hợp |
| Cần tìm kiếm theo nhiều cột hoặc JOIN thường xuyên | Không phù hợp vì không có index |
| Cần rollback nhiều thao tác như một transaction | Không phù hợp |
| Cần import/export file CSV | Thường dùng `LOAD DATA` hoặc `SELECT ... INTO OUTFILE`; không bắt buộc dùng CSV engine |

Không chỉnh sửa trực tiếp file dữ liệu mà server đang quản lý trong khi MySQL hoạt động. Việc sửa file bên ngoài có thể làm nội dung và trạng thái mà engine quản lý không nhất quán. Hãy dùng SQL hoặc quy trình bảo trì được tài liệu engine hỗ trợ.

## 4. ARCHIVE Storage Engine

### 4.1. Mục đích và cách hoạt động

ARCHIVE được thiết kế cho dữ liệu lưu trữ theo hướng nén, thường là dữ liệu có tần suất thêm mới cao và được đọc lại khi cần. Engine sử dụng cơ chế nén để giảm dung lượng lưu trữ; đổi lại, việc nén/giải nén và khả năng truy xuất ngẫu nhiên có thể làm tăng chi phí CPU hoặc thời gian đọc.

Các đặc điểm cần nhớ:

- Mô hình sử dụng chủ yếu là thêm dữ liệu và đọc lại.
- Không hỗ trợ `UPDATE` và `DELETE` theo cách của InnoDB; không thiết kế ARCHIVE cho thao tác sửa/xóa từng hàng.
- Khả năng index rất hạn chế; MySQL hỗ trợ index cho cột `AUTO_INCREMENT` trong phạm vi engine, không có hệ index tổng quát như InnoDB.
- Không hỗ trợ transaction và foreign key như InnoDB.
- Truy vấn lọc theo các cột không có index có thể phải đọc nhiều dữ liệu đã nén.

Vì vậy, ARCHIVE có thể hữu ích với log hoặc dữ liệu lịch sử ít thay đổi, nhưng cần cân nhắc kỹ nếu phải tìm kiếm thường xuyên theo thời gian, người dùng hoặc loại sự kiện. Có thể cần phân vùng theo thời gian ở tầng thiết kế, bảng tổng hợp, hoặc lưu dữ liệu truy vấn nóng trong InnoDB.

### 4.2. Tạo bảng ARCHIVE

Ví dụ một bảng lưu sự kiện lịch sử, trong đó `event_id` là khóa tự tăng:

```sql
CREATE TABLE archived_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_time DATETIME NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload MEDIUMTEXT NOT NULL,
    PRIMARY KEY (event_id)
) ENGINE = ARCHIVE;
```

Thêm và đọc dữ liệu:

```sql
INSERT INTO archived_events (event_time, event_type, payload)
VALUES
    ('2026-01-10 09:15:00', 'LOGIN', '{"userId": 101}'),
    ('2026-01-10 09:20:00', 'ORDER_CREATED', '{"orderId": 9001}');

SELECT event_id, event_time, event_type
FROM archived_events
WHERE event_id >= 1;
```

Index trên `event_id` phục vụ cơ chế `AUTO_INCREMENT`; đừng giả định có thể thêm index thông thường trên `event_time` hoặc `event_type` như với InnoDB. Truy vấn theo các cột này có thể cần quét nhiều hàng.

### 4.3. Thiết kế luồng dữ liệu cho ARCHIVE

Một cách tổ chức thường gặp là giữ dữ liệu mới trong InnoDB để phục vụ cập nhật và truy vấn nghiệp vụ, sau đó chuyển những bản ghi đã đóng hoặc đã qua thời hạn sử dụng sang bảng ARCHIVE.

```text
Ứng dụng ghi sự kiện
        |
        v
InnoDB: dữ liệu đang hoạt động
        |
        | Quy trình lưu trữ theo thời gian / trạng thái
        v
ARCHIVE: dữ liệu lịch sử nén
        |
        v
Đọc báo cáo hoặc tra cứu lịch sử
```

Quy trình chuyển dữ liệu cần được thiết kế cẩn thận vì thao tác trên hai engine không tạo thành một transaction chung. Một quy trình có thể gồm:

1. Xác định khoảng dữ liệu đã đủ điều kiện lưu trữ.
2. Ghi dữ liệu vào bảng ARCHIVE.
3. Đối soát số dòng và các giá trị quan trọng giữa nguồn và đích.
4. Chỉ sau khi xác minh thành công mới xóa dữ liệu cũ khỏi bảng InnoDB theo chính sách retention.
5. Ghi nhận tiến độ và thiết kế cách chạy lại an toàn nếu job bị gián đoạn.

Không xóa dữ liệu nguồn trước khi xác minh dữ liệu đích. Vì ARCHIVE không cung cấp transaction tương đương InnoDB, quy trình cần có idempotency, batch nhỏ, nhật ký tiến độ và khả năng phục hồi khi lỗi giữa chừng.

### 4.4. Khi nào nên và không nên dùng ARCHIVE?

| Tình huống | Đánh giá |
|---|---|
| Log hoặc sự kiện đã hoàn tất, ít thay đổi | Có thể phù hợp nếu ưu tiên tiết kiệm dung lượng và truy vấn không quá thường xuyên |
| Dữ liệu lịch sử chỉ cần đọc tuần tự hoặc theo khóa tự tăng | Có thể cân nhắc sau khi đo hiệu năng thực tế |
| Bảng cần sửa/xóa hàng thường xuyên | Không phù hợp |
| Truy vấn báo cáo cần lọc nhanh theo nhiều cột | Thường không phù hợp nếu thiếu index; cân nhắc InnoDB hoặc hệ phân tích khác |
| Cần transaction, foreign key hoặc cập nhật đồng thời phức tạp | Không phù hợp |
| Dữ liệu phải được truy xuất ngẫu nhiên với độ trễ thấp | Cần benchmark; nén và giới hạn index có thể không đáp ứng |

ARCHIVE không tự thay thế chính sách backup. Dữ liệu nén vẫn cần được sao lưu, kiểm tra khả năng restore và đối soát theo yêu cầu lưu trữ của tổ chức.

## 5. FEDERATED Storage Engine

### 5.1. FEDERATED hoạt động như thế nào?

FEDERATED cho phép MySQL Server cục bộ cung cấp một bảng có cấu trúc tương ứng với bảng nằm trên MySQL server từ xa. Khi ứng dụng truy vấn bảng cục bộ, engine chuyển yêu cầu tới server từ xa qua kết nối mạng và trả kết quả về client.

```mermaid
flowchart LR
    APP[Ứng dụng] --> LOCAL[MySQL Server cục bộ]
    LOCAL --> FT[Bảng FEDERATED: định nghĩa và endpoint]
    FT -->|Giao thức MySQL qua mạng| REMOTE[MySQL Server từ xa]
    REMOTE --> RT[Bảng thật trên server từ xa]
    RT --> DATA[(Dữ liệu từ xa)]
```

Bảng FEDERATED cục bộ là một giao diện tới bảng từ xa, không phải bản sao dữ liệu. Dữ liệu thật nằm trên server từ xa; do đó, thao tác đọc/ghi phụ thuộc kết nối mạng, server từ xa, quyền tài khoản và trạng thái bảng đích.

FEDERATED không phải replication: nó không tự duy trì bản sao cục bộ đồng bộ hoặc một luồng sao chép liên tục. Nó cũng không phải cơ chế distributed transaction giữa hai server.

### 5.2. Điều kiện để tạo bảng FEDERATED

Trước khi sử dụng, cần xác minh:

- FEDERATED engine/plugin có được cung cấp và đã nạp trên server cục bộ.
- Server từ xa có thể truy cập qua mạng và hỗ trợ giao thức, câu lệnh mà workload cần.
- Bảng đích đã tồn tại trên server từ xa.
- Định nghĩa cột và các thuộc tính liên quan của bảng cục bộ khớp với bảng đích: thứ tự cột, kiểu dữ liệu, độ dài, nullability, charset/collation và index cần thiết.
- Tài khoản kết nối từ xa có đúng quyền tối thiểu để thực hiện các thao tác cần thiết.
- DNS, firewall, TLS, timeout và khả năng phục hồi kết nối được cấu hình phù hợp.

Nếu engine không xuất hiện trong `SHOW ENGINES`, hãy kiểm tra tài liệu của đúng bản phân phối để cài hoặc bật plugin. Tên file plugin, cách nạp và khả năng có sẵn khác nhau giữa hệ điều hành, phiên bản và sản phẩm; không sao chép lệnh cài plugin của nền tảng khác.

### 5.3. Tạo bảng từ xa và bảng FEDERATED cục bộ

Trước hết, tạo bảng thật trên server từ xa. Ví dụ chạy tại database `sales` trên server từ xa:

```sql
CREATE TABLE orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    order_time DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_customer_time (customer_id, order_time)
) ENGINE = InnoDB;
```

Trên server cục bộ, tạo bảng có định nghĩa tương ứng và chỉ định endpoint từ xa:

```sql
CREATE TABLE remote_orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    order_time DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_customer_time (customer_id, order_time)
) ENGINE = FEDERATED
CONNECTION = 'mysql://fed_user:password@db.example.internal:3306/sales/orders';
```

Trong ví dụ, thay `password` bằng thông tin xác thực được cấp cho tài khoản kết nối từ xa. Không commit chuỗi chứa mật khẩu vào source control hoặc tài liệu dùng chung; bảo vệ quyền đọc metadata và dùng cơ chế quản lý bí mật phù hợp với môi trường. Nếu mật khẩu có ký tự đặc biệt, cần tuân theo quy tắc mã hóa của định dạng connection string.

Đường dẫn trong connection string có dạng tổng quát:

```text
mysql://user[:password]@host[:port]/database/table
```

Ví dụ truy vấn bảng FEDERATED:

```sql
SELECT order_id, customer_id, order_time, total_amount
FROM remote_orders
WHERE customer_id = 101
ORDER BY order_time DESC;
```

Lệnh SQL được thực hiện qua server từ xa. Hiệu năng phụ thuộc mạng, số lượt trao đổi, lượng dữ liệu trả về, kế hoạch truy vấn và index trên bảng thật. Việc có index trong định nghĩa cục bộ không thay thế việc kiểm tra index và execution plan ở server từ xa.

### 5.4. Giới hạn và rủi ro của FEDERATED

- **Phụ thuộc mạng:** độ trễ và lỗi kết nối từ xa ảnh hưởng trực tiếp truy vấn cục bộ.
- **Phụ thuộc server đích:** server từ xa dừng, quá tải hoặc thay đổi schema có thể làm bảng FEDERATED lỗi.
- **Không có bản sao cục bộ:** mỗi thao tác cần truy cập server từ xa; không dùng FEDERATED như cache.
- **Không có transaction phân tán:** không giả định transaction cục bộ có thể rollback mọi thay đổi đã gửi tới server từ xa hoặc bảo đảm ACID xuyên hai server.
- **Giới hạn hiệu năng:** truy vấn trả về nhiều dữ liệu hoặc tạo nhiều lượt gọi mạng có thể chậm đáng kể.
- **Quản lý schema:** thay đổi bảng từ xa phải được phối hợp với định nghĩa bảng FEDERATED cục bộ.
- **Bảo mật thông tin kết nối:** endpoint và credential phải được bảo vệ; tài khoản từ xa chỉ nên có quyền cần thiết.

Trước khi cho phép ứng dụng ghi qua FEDERATED, cần thử hành vi khi timeout, mất mạng giữa thao tác, server đích restart và câu lệnh bị lỗi một phần. Nếu nghiệp vụ yêu cầu transaction nhất quán xuyên nhiều database, hãy dùng kiến trúc và công nghệ hỗ trợ distributed transaction hoặc thiết kế saga/outbox phù hợp thay vì giả định FEDERATED cung cấp khả năng đó.

### 5.5. Khi nào nên và không nên dùng FEDERATED?

| Tình huống | Đánh giá |
|---|---|
| Tích hợp đơn giản với một bảng MySQL từ xa, workload vừa phải | Có thể cân nhắc sau khi kiểm tra plugin, quyền, latency và lỗi mạng |
| Cần truy vấn trực tiếp dữ liệu ở server khác mà không sao chép cục bộ | Có thể phù hợp nếu chấp nhận phụ thuộc server từ xa |
| Truy vấn có độ trễ thấp, tải lớn hoặc cần cache | Thường không phù hợp; cân nhắc replica đọc, cache hoặc dịch vụ truy vấn chuyên dụng |
| Cần join nhiều nguồn với tối ưu hóa phân tán | Không nên giả định FEDERATED sẽ tối ưu tốt; benchmark và cân nhắc tầng tích hợp dữ liệu |
| Cần transaction ACID xuyên hai server | Không phù hợp |
| Cần khả năng hoạt động độc lập khi server từ xa mất kết nối | Không phù hợp nếu không có bản sao hoặc cơ chế dự phòng khác |

## 6. So sánh CSV, ARCHIVE, FEDERATED và InnoDB

| Tiêu chí | CSV | ARCHIVE | FEDERATED | InnoDB |
|---|---|---|---|---|
| Vị trí dữ liệu | File dạng CSV do server quản lý | Dữ liệu lưu trữ nén tại server | Bảng thật ở server từ xa | Tablespace/log của server cục bộ |
| Mục đích chính | Trao đổi dữ liệu đơn giản | Lưu trữ dữ liệu lịch sử nén | Truy cập bảng MySQL từ xa | Dữ liệu nghiệp vụ và OLTP |
| Index | Không hỗ trợ | Rất hạn chế; hỗ trợ cho `AUTO_INCREMENT` theo giới hạn engine | Phụ thuộc định nghĩa và index trên bảng từ xa | Hỗ trợ nhiều loại index phù hợp |
| Transaction | Không | Không | Không có transaction phân tán; không giả định ACID xuyên server | Có |
| Cập nhật/xóa hàng | Có giới hạn, không có hành vi transaction như InnoDB | Không hỗ trợ `UPDATE`/`DELETE` theo mô hình sử dụng thông thường | Gửi thao tác tới bảng từ xa nếu engine/server hỗ trợ | Có |
| Foreign key | Không | Không | Không cung cấp quan hệ toàn vẹn xuyên server | Có |
| Phụ thuộc mạng | Không cần server khác | Không cần server khác | Có | Không cần server khác cho thao tác cục bộ |
| Trường hợp phù hợp | Dữ liệu dạng CSV đơn giản | Dữ liệu append/read lịch sử | Tích hợp bảng từ xa quy mô phù hợp | Phần lớn dữ liệu nghiệp vụ |

Bảng so sánh ở mức khái quát. Khả năng cụ thể còn phụ thuộc MySQL/MariaDB, phiên bản, plugin và cấu hình. Đặc biệt, FEDERATED có thể khác về hỗ trợ câu lệnh và hành vi giữa các bản triển khai.

## 7. Quy trình lựa chọn engine

Trước khi chọn engine, hãy trả lời các câu hỏi theo thứ tự:

1. **Dữ liệu nằm ở đâu?** Nếu cần lưu cục bộ, CSV hoặc ARCHIVE có thể được cân nhắc cho workload hẹp; nếu dữ liệu ở server khác, FEDERATED là một lựa chọn truy cập trực tiếp.
2. **Dữ liệu thay đổi như thế nào?** Dữ liệu cần cập nhật/xóa thường xuyên nên dùng engine hỗ trợ đầy đủ thao tác đó, thường là InnoDB.
3. **Có cần transaction không?** Nếu nhiều thao tác phải commit/rollback cùng nhau, chọn engine hỗ trợ transaction.
4. **Có cần index và truy vấn nhanh không?** Nếu thường lọc, join, sắp xếp hoặc tra cứu theo nhiều cột, cần engine và thiết kế index phù hợp.
5. **Có cần foreign key không?** Nếu cần server bảo đảm quan hệ tham chiếu, dùng engine hỗ trợ foreign key.
6. **Có thể chấp nhận phụ thuộc ngoài hệ thống không?** FEDERATED làm truy vấn phụ thuộc mạng và server từ xa; cần đánh giá timeout, quyền, bảo mật và khả năng dự phòng.
7. **Khả năng backup/restore và vận hành ra sao?** Thử quy trình phục hồi, giám sát và xử lý lỗi trên đúng engine trước khi đưa vào production.

Nếu không có yêu cầu đặc biệt được kiểm chứng, InnoDB thường là lựa chọn mặc định an toàn hơn cho bảng nghiệp vụ. Chỉ chọn CSV, ARCHIVE hoặc FEDERATED khi đặc tính của chúng giải quyết đúng một nhu cầu cụ thể và các giới hạn đã được chấp nhận.

## 8. Kiểm tra và vận hành sau khi triển khai

Sau khi tạo bảng, kiểm tra engine và định nghĩa:

```sql
SHOW CREATE TABLE csv_contacts;
SHOW CREATE TABLE archived_events;
SHOW CREATE TABLE remote_orders;

SELECT TABLE_NAME, ENGINE, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('csv_contacts', 'archived_events', 'remote_orders');
```

`TABLE_ROWS` có thể chỉ là ước lượng hoặc không có ý nghĩa như nhau giữa các engine; không dùng nó thay cho `COUNT(*)` khi cần đối soát chính xác. Với FEDERATED, các phép đo dung lượng cục bộ không phản ánh dung lượng dữ liệu trên server từ xa.

Một số nguyên tắc vận hành:

- **CSV:** kiểm tra dữ liệu sau khi nạp, chuẩn hóa encoding và dấu phân tách; dùng SQL để thao tác với bảng trong khi server đang quản lý nó.
- **ARCHIVE:** theo dõi dung lượng, tốc độ nạp, chi phí đọc và quy trình chuyển dữ liệu; xác minh bản sao lưu có thể phục hồi.
- **FEDERATED:** giám sát lỗi mạng, độ trễ truy vấn, trạng thái server đích, quyền tài khoản và thay đổi schema; không để lộ credential trong log hoặc source control.
- **Mọi engine:** ghi nhận phiên bản server, plugin, định nghĩa bảng và phương án backup/restore. Kiểm tra lại sau nâng cấp vì plugin hoặc tính năng có thể thay đổi.

## 9. Kết luận

CSV phục vụ dữ liệu dạng văn bản đơn giản; ARCHIVE hướng tới dữ liệu lịch sử nén, chủ yếu thêm mới và đọc; FEDERATED cung cấp giao diện SQL tới bảng trên MySQL server từ xa. Mỗi engine có giới hạn rõ ràng về index, transaction, cập nhật hoặc phụ thuộc mạng.

Hãy chọn engine dựa trên cách dữ liệu được ghi, đọc, cập nhật và khôi phục. Với dữ liệu nghiệp vụ cần transaction, index và toàn vẹn tham chiếu, InnoDB thường phù hợp hơn. Với CSV, ARCHIVE và FEDERATED, hãy xác minh plugin, thử workload thật và thiết kế quy trình đối soát, backup, bảo mật trước khi triển khai.
