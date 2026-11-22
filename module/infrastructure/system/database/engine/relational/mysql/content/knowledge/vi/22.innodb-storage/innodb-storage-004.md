# Secondary index lưu khóa chính và tác động của khóa chính rộng

InnoDB tổ chức bảng theo **clustered index**: các hàng dữ liệu được lưu trong lá của B-tree khóa chính. Mỗi **secondary index** cũng là một B-tree riêng; ở lá của nó, InnoDB lưu các cột của secondary key cùng với các cột khóa chính cần thiết để xác định hàng trong clustered index. Vì vậy, kích thước khóa chính ảnh hưởng tới mọi secondary index của bảng.

Nếu khóa chính là `BIGINT` 8 byte, phần khóa chính được mang theo trong secondary index thường gọn hơn đáng kể so với khóa dạng chuỗi dài hoặc khóa ghép nhiều cột. Khi bảng có hàng triệu bản ghi và nhiều secondary index, chênh lệch nhỏ trên mỗi entry có thể nhân lên thành dung lượng đáng kể, giảm số entry trên mỗi page, tăng số page phải đọc và làm tăng chi phí ghi/cập nhật index.

Trong module `DATABASE_MYSQL`, thiết kế khóa chính cần cân bằng tính ổn định, duy nhất, ý nghĩa nghiệp vụ, khả năng phân phối ID và chi phí lưu trữ. Bài này tập trung vào quan hệ giữa clustered index, secondary index và độ rộng của primary key trong InnoDB.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích cách InnoDB lưu bảng trong clustered index.
- Mô tả vì sao secondary index cần mang khóa chính để tìm hàng tương ứng.
- Nhận diện các cột khóa chính được đưa vào secondary index và trường hợp cột bị trùng không cần lưu lặp.
- Ước lượng tác động của khóa chính hẹp, khóa chuỗi dài và khóa ghép lên tổng dung lượng index.
- Phân biệt `BIGINT`, UUID dạng text và UUID nhị phân `BINARY(16)` về kích thước lưu trữ.
- Hiểu ảnh hưởng của khóa chính rộng tới fan-out, số page, buffer pool, I/O và chi phí DML.
- Chọn khóa chính ổn định, ngắn và phù hợp với workload.
- Kiểm tra kích thước index và kế hoạch truy vấn bằng metadata, `EXPLAIN` và phép đo thực tế.

## 1. Clustered index trong InnoDB

InnoDB không lưu dữ liệu bảng như một heap độc lập rồi để primary key chỉ làm một index phụ. Bảng được tổ chức theo clustered index, thông thường là primary key. Các nút lá của B-tree clustered index chứa dữ liệu hàng.

Ví dụ:

```sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(160) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
```

Trong bảng này, các hàng được tổ chức theo khóa `customer_id`. Tìm một hàng theo primary key đi trực tiếp tới clustered index; khi tìm theo secondary index, InnoDB trước tiên tìm entry trong secondary B-tree rồi dùng giá trị khóa chính ở entry đó để tra hàng trong clustered index nếu truy vấn cần thêm cột chưa có trong secondary index.

### 1.1. Nếu không khai báo PRIMARY KEY

InnoDB cần một clustered index để tổ chức hàng. Nếu bảng không có primary key tường minh, InnoDB chọn khóa `UNIQUE` đầu tiên có tất cả cột `NOT NULL` làm clustered index nếu có. Nếu không có khóa phù hợp, InnoDB tạo một row ID nội bộ ẩn (thường gọi là `GEN_CLUST_INDEX`) để làm khóa clustered.

Không nên dựa vào row ID ẩn làm thiết kế khóa chính. Ứng dụng không thể dùng nó như một khóa nghiệp vụ được khai báo rõ, và việc để InnoDB tự tạo clustered key không thay thế được lợi ích của một primary key ổn định, có chủ đích.

## 2. Secondary index mang theo khóa chính

Secondary index là B-tree bổ sung, được tạo bởi `INDEX` hoặc `UNIQUE KEY` ngoài clustered key. Entry ở lá secondary index chứa:

- Các cột được khai báo trong secondary index.
- Các cột của primary key cần thiết để định vị hàng trong clustered index.

Ví dụ:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_status_created (order_status, created_at)
) ENGINE=InnoDB;
```

Về mặt khái niệm, secondary index `idx_orders_customer` lưu `customer_id` cùng `order_id`; index `idx_orders_status_created` lưu `order_status`, `created_at` cùng `order_id`. `order_id` là giá trị InnoDB cần để định vị hàng trong clustered index.

### 2.1. Khi secondary key đã chứa một phần primary key

Nếu primary key là khóa ghép, InnoDB chỉ cần bổ sung những thành phần primary key chưa có trong secondary key; không cần lưu lặp một cột đã nằm trong phần khóa secondary.

```sql
CREATE TABLE order_line (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_order_line_product (product_id)
) ENGINE=InnoDB;
```

Ở `idx_order_line_product`, entry cần `product_id` và khóa ghép `(order_id, line_no)` để định vị hàng. Nếu secondary index đã khai báo một thành phần khóa chính, InnoDB không cần lặp thành phần đó thêm lần nữa trong record vật lý.

Ví dụ khác:

```sql
KEY idx_order_line_order_created (order_id, created_at)
```

Index này đã chứa `order_id`, nên phần primary key cần bổ sung để định vị hàng chỉ còn `line_no`. Cấu trúc logic của entry có thể hiểu là `(order_id, created_at, line_no)`.

### 2.2. Tại sao secondary index có thể phục vụ truy vấn phủ?

Vì secondary index mang các cột primary key, một số truy vấn lấy khóa chính có thể được phục vụ ngay từ secondary index mà không cần quay lại clustered index:

```sql
EXPLAIN
SELECT customer_id, order_id
FROM orders
WHERE customer_id = 100;
```

Index `idx_orders_customer` có `customer_id` và giá trị `order_id` đi kèm. Nếu truy vấn chỉ cần hai cột này, optimizer có thể chọn covering index scan (`Using index` trong một số dạng EXPLAIN). Đây là một hệ quả hữu ích của việc secondary index lưu primary key.

Không phải mọi truy vấn lọc theo secondary key đều là covering. Nếu truy vấn cần `total_amount`, InnoDB có thể phải tra clustered index cho từng entry phù hợp:

```sql
SELECT customer_id, order_id, total_amount
FROM orders
WHERE customer_id = 100;
```

## 3. Khóa chính rộng làm tăng kích thước mọi secondary index

Giả sử bảng có `N` hàng và `K` secondary index. Nếu phần khóa chính được mang theo trong mỗi entry rộng thêm trung bình `D` byte, chi phí bổ sung thô có thể ước lượng ở mức:

\[
N \times K \times D
\]

Đây chỉ là ước lượng phần payload khóa tăng thêm, không phải công thức tính kích thước file chính xác. Nó chưa tính record header, page directory, fill factor, page split, các cột secondary key, compression, độ dài biến đổi và metadata B-tree. Tuy vậy, nó cho thấy một khóa chính rộng được nhân lên theo số hàng và số secondary index.

Ví dụ, bảng có 5 triệu hàng và 6 secondary index. Nếu thay một primary key 8 byte bằng khóa 36 byte, phần khóa tăng thêm khoảng 28 byte trên mỗi entry secondary index:

\[
5{,}000{,}000 \times 6 \times 28
= 840{,}000{,}000\text{ byte}
\]

Tức khoảng 840 MB theo đơn vị thập phân chỉ tính phần payload tăng thêm. Kích thước thực tế của index có thể khác đáng kể; cần đo trên dữ liệu đại diện.

### 3.1. Bảng so sánh kích thước khóa thường gặp

| Dạng primary key | Payload khóa điển hình | Ghi chú |
|---|---:|---|
| `INT UNSIGNED` | 4 byte | Hẹp, phù hợp nếu miền giá trị đủ |
| `BIGINT UNSIGNED` | 8 byte | Phổ biến cho ID số lớn |
| UUID dạng text `CHAR(36)` ASCII | 36 byte | Dễ đọc nhưng dài hơn UUID nhị phân |
| UUID nhị phân `BINARY(16)` | 16 byte | Gọn hơn text, cần quy ước chuyển đổi nhất quán |
| Khóa ghép `BIGINT + INT` | 12 byte | Cả hai thành phần được mang theo nếu secondary index chưa chứa chúng |

Các con số trên là độ rộng dữ liệu khóa cơ bản. Record thực tế còn có metadata và chi phí căn chỉnh/lưu trữ khác; `CHAR`, `VARCHAR`, charset và định dạng record có thể làm kích thước thay đổi.

## 4. UUID dạng text và BINARY(16)

UUID dạng chuẩn có 36 ký tự hiển thị, bao gồm dấu gạch nối. Nếu lưu bằng `CHAR(36)` với charset ASCII, payload ký tự là 36 byte. Nếu lưu bằng `BINARY(16)`, UUID được biểu diễn bằng 16 byte.

```sql
CREATE TABLE event_text_pk (
    event_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_text_tenant_time (tenant_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE event_binary_pk (
    event_id BINARY(16) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_event_binary_tenant_time (tenant_id, created_at)
) ENGINE=InnoDB;
```

Secondary index của bảng thứ nhất mang theo khóa `CHAR(36)`; bảng thứ hai mang khóa `BINARY(16)`. Riêng phần khóa chính đi kèm secondary entry của UUID nhị phân nhỏ hơn 20 byte mỗi entry so với UUID text 36 byte, trước khi tính overhead khác.

### 4.1. Chuyển UUID text sang binary

MySQL có các hàm `UUID_TO_BIN()` và `BIN_TO_UUID()` để chuyển UUID:

```sql
INSERT INTO event_binary_pk (event_id, tenant_id, created_at, payload)
VALUES (
    UUID_TO_BIN(UUID()),
    10,
    NOW(6),
    JSON_OBJECT('source', 'api')
);

SELECT BIN_TO_UUID(event_id) AS event_id
FROM event_binary_pk;
```

Với UUID v1, tham số `swap_flag = 1` của `UUID_TO_BIN(uuid, 1)` hoán đổi một số trường thời gian để cải thiện tính tuần tự theo byte trong index. Khi đọc lại, phải dùng cùng quy ước `BIN_TO_UUID(binary_uuid, 1)`. Không áp dụng hoán đổi này một cách máy móc cho UUID v4 hoặc các định dạng UUID khác; chọn quy ước theo loại UUID và bảo đảm mọi writer/reader dùng nhất quán.

### 4.2. Trade-off khi dùng BINARY(16)

Ưu điểm:

- Khóa nhỏ hơn UUID text, làm secondary index gọn hơn.
- Giảm số byte cần so sánh và lưu trong B-tree.
- Không phải lưu dấu gạch nối hoặc biểu diễn ký tự của UUID.

Điểm cần quản lý:

- Khó đọc trực tiếp trong SQL client và log nếu không chuyển bằng `BIN_TO_UUID()`.
- Cần thống nhất byte order, UUID version và `swap_flag` giữa các dịch vụ.
- UUID ngẫu nhiên như v4 vẫn có thứ tự chèn phân tán; BINARY(16) giảm độ rộng nhưng không tự biến ID ngẫu nhiên thành tuần tự.
- Cần xác định rõ cách serialize trong API, message queue, backup/restore và công cụ vận hành.

## 5. Khóa ghép cũng có thể trở thành khóa chính rộng

Khóa ghép có thể mô tả danh tính tự nhiên của hàng, ví dụ `(tenant_id, external_code)` hoặc `(order_id, line_no)`. Nhưng mỗi thành phần khóa được đưa vào secondary index nếu index đó chưa chứa thành phần tương ứng.

```sql
CREATE TABLE tenant_document (
    tenant_id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    document_body JSON NOT NULL,
    PRIMARY KEY (tenant_id, external_code),
    KEY idx_document_status_created (status, created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Secondary index `idx_document_status_created` cần mang theo `tenant_id` và `external_code` để định vị hàng. `external_code` có độ dài biến đổi và có thể chiếm nhiều byte, đặc biệt với charset đa byte. Nếu bảng có nhiều secondary index, chi phí khóa ghép có thể lớn.

### 5.1. Natural key và surrogate key

Natural key lấy từ dữ liệu nghiệp vụ, ví dụ mã quốc gia, số tài khoản ngoài hoặc mã chứng từ. Surrogate key là ID kỹ thuật được tạo riêng như `BIGINT AUTO_INCREMENT`.

Một thiết kế thường gặp là dùng surrogate key hẹp làm primary key và đặt unique constraint trên natural key:

```sql
CREATE TABLE tenant_document_alt (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    document_body JSON NOT NULL,
    PRIMARY KEY (document_id),
    UNIQUE KEY uq_document_tenant_code (tenant_id, external_code),
    KEY idx_document_status_created (status, created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Giờ các secondary index khác mang `document_id` hẹp hơn. Tuy nhiên, unique index trên `(tenant_id, external_code)` vẫn phải lưu hai cột natural key của nó; surrogate key không xóa chi phí của unique constraint. Nó chỉ giúp những secondary index không cần natural key trở nên gọn hơn.

### 5.2. Không chuyển sang surrogate key một cách máy móc

Natural composite primary key có thể hợp lý khi:

- Khóa nghiệp vụ nhỏ và ổn định.
- Các truy vấn thường xuyên lọc theo toàn bộ hoặc tiền tố khóa.
- Quan hệ con tham chiếu tự nhiên theo khóa ghép và việc join là rõ ràng.
- Bảng có ít secondary index hoặc khóa ghép không rộng.

Surrogate key có thể hợp lý khi:

- Natural key dài hoặc thay đổi theo nghiệp vụ.
- Nhiều bảng con cần tham chiếu bằng một khóa ngắn.
- Bảng có nhiều secondary index và chi phí lặp khóa ghép là đáng kể.
- Cần tách danh tính nội bộ khỏi mã định danh bên ngoài.

Hãy so sánh chi phí lưu trữ và join thực tế. Không có quy tắc rằng mọi bảng đều phải dùng `BIGINT AUTO_INCREMENT`.

## 6. Khóa chính rộng ảnh hưởng B-tree như thế nào?

### 6.1. Ít entry hơn trên mỗi page

Một page B-tree có kích thước hữu hạn. Khi mỗi entry rộng hơn, page chứa được ít entry hơn. Với cùng số hàng, index cần nhiều page hơn, có thể làm tăng chiều cao cây hoặc số lần đọc page khi truy vấn.

### 6.2. Buffer pool chứa được ít entry hơn

InnoDB dùng buffer pool để cache data và index page. Secondary index rộng chiếm nhiều page hơn, làm giảm số entry có thể nằm trong cùng dung lượng buffer pool. Workload truy vấn theo secondary index có thể cần nhiều lần đọc page từ storage hơn.

### 6.3. Chi phí ghi và cập nhật index tăng

Khi insert hàng mới, InnoDB phải thêm entry vào clustered index và từng secondary index. Khóa chính được mang theo trong secondary entry, nên khóa rộng làm tăng lượng dữ liệu phải ghi, page split có thể tốn kém hơn và index maintenance nặng hơn.

Nếu primary key thay đổi, giá trị khóa chính mới phải được phản ánh trong các secondary index vì chúng dùng khóa chính để định vị hàng. Đây là một lý do quan trọng để chọn primary key bất biến.

### 6.4. Tác động tới backup, restore và replication workload

Index lớn làm tăng dung lượng dữ liệu phải backup/restore và có thể tăng I/O khi dump, import hoặc build lại index. Dữ liệu index cũng làm tăng lượng page phải đọc khi quét. Tác động cụ thể phụ thuộc storage, compression, backup method và workload; không thể suy ra thời gian backup chỉ từ độ rộng khóa.

### 6.5. Khóa ngoại ở các bảng con cũng bị ảnh hưởng

Nếu bảng con tham chiếu một primary key rộng, các cột foreign key ở bảng con cũng phải dùng kiểu dữ liệu tương thích và lưu giá trị rộng đó. Index phục vụ foreign key vì thế cũng chứa khóa tham chiếu rộng; nếu bảng con có secondary index khác, primary key riêng của bảng con tiếp tục được mang theo trong các index đó.

```sql
CREATE TABLE parent_text (
    parent_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    label VARCHAR(80) NOT NULL,
    PRIMARY KEY (parent_id)
) ENGINE=InnoDB;

CREATE TABLE child_of_text_parent (
    child_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    parent_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (child_id),
    KEY idx_child_parent (parent_id),
    KEY idx_child_status (status),
    CONSTRAINT fk_child_text_parent
        FOREIGN KEY (parent_id) REFERENCES parent_text (parent_id)
) ENGINE=InnoDB;
```

Ở bảng con, `idx_child_parent` lưu `parent_id` cùng `child_id` để tìm hàng con. `idx_child_status` lưu `status` cùng `child_id`. Nếu thay `parent_id` bằng `BINARY(16)` ở cả hai bảng, index foreign key sẽ mang giá trị tham chiếu ngắn hơn. Khi một bảng cha có rất nhiều bảng con hoặc bảng con có nhiều hàng, chi phí của khóa tham chiếu rộng có thể lan sang toàn mô hình dữ liệu.

Không tự đổi kiểu khóa ngoại ở một phía; kiểu, kích thước và thuộc tính cần tương thích với khóa được tham chiếu. Việc thay PK trong hệ thống đang chạy có thể kéo theo migration nhiều bảng con, index, ứng dụng và dữ liệu tích hợp.

## 7. Primary key tuần tự và primary key ngẫu nhiên

Độ rộng không phải yếu tố duy nhất. Thứ tự giá trị khóa ảnh hưởng vị trí chèn vào B-tree clustered index.

### 7.1. AUTO_INCREMENT

`BIGINT AUTO_INCREMENT` thường tạo giá trị tăng dần. Insert mới thường đi về vùng cuối của clustered index, giúp locality tốt và giảm insert phân tán. Với workload ghi đồng thời rất cao, điểm cuối cây có thể trở thành vùng cạnh tranh latch/page; cần đo thực tế thay vì mặc định rằng mọi bảng đều gặp bottleneck này.

### 7.2. UUID ngẫu nhiên

UUID v4 có tính ngẫu nhiên cao. Khi dùng làm clustered primary key, insert có thể rải ra nhiều vùng của B-tree, gây page split, phân mảnh và cache locality kém hơn so với khóa tăng dần. Dùng `BINARY(16)` làm khóa gọn hơn text nhưng vẫn giữ đặc tính chèn ngẫu nhiên của UUID v4.

### 7.3. UUID có tính thời gian

UUID có trường thời gian hoặc ID phân phối có thứ tự (time-ordered) có thể cải thiện locality so với UUID ngẫu nhiên hoàn toàn. Tuy nhiên, phải chọn phiên bản/định dạng phù hợp, hiểu thứ tự byte và cân nhắc khả năng lộ thông tin thời gian hoặc pattern sinh ID. Không nên giả định mọi UUID đều có thứ tự chèn tốt.

## 8. Chọn primary key theo workload

Một primary key tốt thường có các đặc điểm:

- Duy nhất và `NOT NULL`.
- Ngắn để giảm payload trong secondary index.
- Ổn định, không thay đổi trong vòng đời hàng.
- Có quy tắc sinh ID rõ ràng, không phụ thuộc dữ liệu dễ sửa.
- Phù hợp với kiểu truy cập và phân phối ghi.
- Có thể được các bảng con tham chiếu hiệu quả.

Ví dụ quyết định:

| Bối cảnh | Lựa chọn cần cân nhắc | Lý do |
|---|---|---|
| Bảng giao dịch nội bộ nhiều secondary index | `BIGINT` surrogate | Hẹp, dễ tham chiếu và thường tăng dần |
| Bảng quan hệ con có khóa tự nhiên nhỏ, ổn định | Khóa ghép | Tránh thêm ID không cần thiết và giữ semantics quan hệ |
| Hệ thống cần ID phân tán không cần central sequence | UUID, ưu tiên dạng nhị phân nếu phù hợp | Tạo ID độc lập giữa node, giảm độ rộng so với text |
| Bảng event ghi nhiều, cần locality | ID tăng dần hoặc ID có thứ tự thời gian | Hỗ trợ insert theo vùng gần cuối index |
| Bảng có natural key dài nhưng nhiều index phụ | Surrogate PK + unique natural key | Không lặp natural key dài trong mọi secondary index |

Đây là điểm bắt đầu để đánh giá, không phải công thức chung. Cần tính tới yêu cầu phân tán, bảo mật, import, thứ tự nghiệp vụ và khả năng tương thích hệ thống.

## 9. Kiểm tra secondary index và dung lượng thực tế

### 9.1. Xem định nghĩa index

```sql
SHOW CREATE TABLE orders\G

SHOW INDEX FROM orders;
```

`SHOW INDEX` hiển thị các cột index được khai báo, thứ tự cột và thuộc tính index. Nó không hiển thị một cách trực quan toàn bộ phần primary key được InnoDB mang ngầm vào secondary index.

### 9.2. Xem kích thước bảng và index ở mức schema

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('event_text_pk', 'event_binary_pk')
ORDER BY TABLE_NAME;
```

`DATA_LENGTH` và `INDEX_LENGTH` là thống kê dung lượng ở mức storage engine và có thể là giá trị ước lượng/cập nhật theo thời điểm; `TABLE_ROWS` với InnoDB thường không phải số đếm chính xác. Không dùng một lần truy vấn metadata làm benchmark cuối cùng.

### 9.3. So sánh bằng dữ liệu đại diện

Để đo tác động của khóa chính, tạo hai bảng có cùng cột nghiệp vụ, cùng số hàng, cùng secondary index, chỉ khác kiểu primary key. Nạp cùng dữ liệu và cùng phân phối giá trị; sau đó:

1. Chạy `ANALYZE TABLE` để cập nhật thống kê khi phù hợp.
2. So sánh `DATA_LENGTH` và `INDEX_LENGTH` sau khi dữ liệu ổn định.
3. Kiểm tra số page/index page bằng công cụ thống kê phù hợp phiên bản và quyền truy cập.
4. Chạy cùng workload truy vấn, ghi và cập nhật.
5. Đo latency, I/O, buffer pool hit và dung lượng backup nếu đó là tiêu chí vận hành.

Không so sánh hai bảng có số hàng, độ dài dữ liệu, số index hoặc fill pattern khác nhau rồi quy toàn bộ chênh lệch cho primary key.

## 10. Covering index và khóa chính ngầm

Do secondary index có primary key, một truy vấn chọn cột primary key cùng cột secondary key có thể được phủ bởi index:

```sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);

EXPLAIN
SELECT customer_id, created_at, order_id
FROM orders
WHERE customer_id = 100
ORDER BY created_at;
```

InnoDB có thể sử dụng các cột secondary key và primary key đi kèm để trả kết quả mà không đọc clustered record. Đây là khả năng hữu ích nhưng không có nghĩa nên bỏ qua thiết kế index. Nếu truy vấn cần thêm cột không nằm trong secondary record, nó vẫn cần lookup clustered index.

Khi thiết kế covering index, tính cả primary key được mang theo. Nếu primary key rộng, một secondary index vốn được tạo chỉ với một vài cột có thể lớn hơn dự kiến.

## 11. Giới hạn độ dài khóa index

Primary key cũng là một index và các cột primary key được đưa vào secondary index. Khóa ghép quá rộng có thể gặp giới hạn độ dài khóa của InnoDB, nhất là khi dùng `VARCHAR` với charset nhiều byte.

Trên cấu hình InnoDB phổ biến với page size 16 KB và row format `DYNAMIC` hoặc `COMPRESSED`, giới hạn key length thường là 3072 byte. Giới hạn giảm theo page size nhỏ hơn và có thể thấp hơn với row format cũ. Phiên bản, row format và cấu hình cụ thể cần được kiểm tra trước khi triển khai.

Ví dụ, `VARCHAR(255)` với `utf8mb4` có thể cần tối đa 4 byte mỗi ký tự cho phần dữ liệu ký tự. Không thể chỉ nhìn số ký tự để kết luận index key vừa giới hạn byte. Với primary key ghép nhiều chuỗi, cần tính cả các thành phần và overhead phù hợp.

Không nên chọn một chuỗi nghiệp vụ dài làm primary key rồi mới phát hiện các secondary index không thể tạo được. Nếu cần unique natural key dài, cân nhắc unique constraint phù hợp, surrogate key hẹp hoặc một mô hình tra cứu khác; không thay thế unique constraint bằng hash mà bỏ qua kiểm tra collision.

## 12. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
|---|---|---|
| Dùng `CHAR(36)` UUID text làm PK trong bảng có nhiều secondary index | Mỗi secondary entry mang khóa text dài | Cân nhắc `BINARY(16)` hoặc surrogate key nếu phù hợp |
| Dùng khóa ghép nhiều cột dài làm PK | Tăng kích thước mọi secondary index không chứa đủ khóa | Đánh giá surrogate key và unique natural key |
| Dùng cột PK có thể thay đổi | Cập nhật clustered key kéo theo thay đổi secondary index | Chọn khóa bất biến |
| Dùng UUID v4 rồi kỳ vọng insert tuần tự | B-tree insert vẫn phân tán dù UUID lưu binary | Chọn ID có thứ tự nếu workload cần locality |
| Tạo quá nhiều secondary index | Tăng dung lượng và chi phí mỗi INSERT/UPDATE/DELETE | Chỉ giữ index phục vụ workload thực tế |
| Cho rằng SHOW INDEX hiển thị toàn bộ entry vật lý | Bỏ sót PK được mang ngầm | Hiểu quy tắc InnoDB và đo index thực tế |
| Dùng `SUM(DISTINCT ...)` hoặc hash để che vấn đề khóa | Có thể loại dữ liệu hợp lệ hoặc gặp collision | Giữ khóa duy nhất đúng semantics và kiểm tra collision |
| Đo dung lượng trên bảng thử nhỏ | Overhead và phân phối page không đại diện production | Benchmark với dữ liệu và workload đại diện |

## 13. Quy trình đánh giá một primary key

Khi thiết kế bảng mới hoặc xem xét thay khóa chính, hãy lần lượt trả lời:

1. Khóa có duy nhất, `NOT NULL` và ổn định suốt vòng đời hàng không?
2. Khóa chiếm bao nhiêu byte thực tế? Với chuỗi, xét charset và độ dài tối đa.
3. Bảng có bao nhiêu secondary index? Mỗi index sẽ mang thêm những thành phần PK nào?
4. Có secondary index nào đã chứa một phần khóa ghép nên không phải lặp lại phần đó không?
5. Có bao nhiêu bảng con tham chiếu PK và các foreign key đó rộng tới đâu?
6. Thứ tự sinh khóa có hỗ trợ locality của clustered index hay gây insert phân tán?
7. Hệ thống có cần sinh ID phân tán, không phụ thuộc một node trung tâm không?
8. Natural key có thể thay đổi hoặc dài lên theo nghiệp vụ không?
9. Độ dài tổng thể có nằm trong giới hạn key length của cấu hình triển khai không?
10. Benchmark với số hàng, số index và workload đại diện cho thấy khác biệt gì?

## 14. Bài thực hành

Thực hiện trong database lab riêng với hai bảng `event_text_pk` và `event_binary_pk`:

1. Tạo bảng có primary key `BIGINT`, `CHAR(36)` ASCII và `BINARY(16)`; giữ các cột nghiệp vụ giống nhau.
2. Tạo cùng các secondary index trên cả ba bảng.
3. Nạp lượng dữ liệu đủ lớn với phân phối giống nhau; không chỉ dùng vài chục hàng.
4. Dùng `SHOW CREATE TABLE` và `SHOW INDEX` để xem index khai báo.
5. Giải thích những cột primary key nào được mang theo trong secondary index.
6. So sánh `DATA_LENGTH` và `INDEX_LENGTH` qua `INFORMATION_SCHEMA.TABLES` sau khi dữ liệu ổn định.
7. Chạy truy vấn lọc theo secondary key và chỉ chọn primary key; kiểm tra liệu optimizer có thể dùng covering index.
8. Thêm cột không nằm trong secondary index vào SELECT; quan sát việc cần lookup clustered index.
9. Tạo khóa ghép `(tenant_id, external_code)` và một secondary index khác; mô tả payload khóa được mang theo.
10. Tạo phiên bản dùng surrogate `BIGINT` cùng unique natural key; so sánh dung lượng secondary index và chi phí join.
11. Nạp UUID v4 ngẫu nhiên vào `CHAR(36)` và `BINARY(16)`; so sánh dung lượng và đặc tính insert trong workload giống nhau.
12. Thử UUID có thứ tự thời gian theo quy ước chuyển đổi nhất quán; so sánh locality và tốc độ ghi trong lab.
13. Đọc giới hạn key length theo page size/row format đang dùng; thử thiết kế khóa ghép rộng trong môi trường thử nghiệm.
14. Viết đề xuất chọn PK cho một bảng event có 5 secondary index và hàng chục triệu bản ghi, kèm ước lượng payload tăng thêm.

Bạn hoàn thành bài khi giải thích được vì sao một primary key được lặp trong nhiều secondary index, ước lượng được chi phí của khóa rộng và bảo vệ được lựa chọn PK dựa trên workload thay vì chỉ dựa trên sự tiện lợi khi sinh ID.

## 15. Nguyên tắc cần ghi nhớ

- InnoDB lưu dữ liệu hàng trong clustered index; thường là primary key.
- Secondary index là B-tree riêng và leaf entry mang các cột secondary key cùng các thành phần primary key cần để định vị hàng.
- Thành phần PK đã có trong secondary key không cần được lưu lặp lại trong entry.
- Primary key rộng làm mọi secondary index không chứa đủ khóa rộng hơn; chi phí tăng theo số hàng và số index.
- Khóa ghép có thể làm secondary index lớn nếu gồm nhiều cột hoặc cột chuỗi dài.
- `BIGINT` thường hẹp hơn UUID text; `BINARY(16)` lưu UUID gọn hơn biểu diễn `CHAR(36)`.
- `BINARY(16)` giảm độ rộng UUID nhưng không tự làm UUID ngẫu nhiên có locality tốt.
- Primary key nên duy nhất, `NOT NULL`, ổn định và ngắn nếu workload cho phép.
- Surrogate key không xóa chi phí của unique natural key; nó giúp secondary index khác mang khóa hẹp hơn.
- Primary key tăng dần có thể hỗ trợ insert locality; cần đo bottleneck thực tế ở workload ghi đồng thời cao.
- Secondary index có thể là covering khi truy vấn chỉ cần các cột đã có trong secondary entry, bao gồm PK.
- Kiểm tra giới hạn key length theo page size, row format, charset và phiên bản.
- Dùng metadata để tham khảo, benchmark với dữ liệu đại diện để quyết định.
