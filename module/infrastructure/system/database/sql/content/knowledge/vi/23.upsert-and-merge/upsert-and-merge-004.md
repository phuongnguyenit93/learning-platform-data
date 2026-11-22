# INSERT ON DUPLICATE KEY UPDATE của MySQL

Trong ứng dụng thực tế, một bản ghi từ API, file import hoặc hệ thống khác có thể là **dữ liệu mới** hoặc là **phiên bản cập nhật của dữ liệu đã có**. Nếu luôn dùng `INSERT`, hệ quản trị có thể báo trùng khóa. Nếu luôn dùng `UPDATE`, bản ghi chưa tồn tại sẽ không được tạo. Một mẫu giải quyết hai tình huống trong cùng câu lệnh được gọi là **upsert** (*update or insert*).

Trong MySQL, một cú pháp quan trọng để thực hiện upsert là:

```sql
INSERT INTO table_name (key_column, data_column)
VALUES ('K1', 'Giá trị mới') AS incoming
ON DUPLICATE KEY UPDATE
    data_column = incoming.data_column;
```

Nếu việc chèn **không vi phạm khóa chính hoặc chỉ mục UNIQUE**, MySQL thêm hàng mới. Nếu việc chèn gây xung đột `PRIMARY KEY` hoặc `UNIQUE`, nó chuyển sang thực hiện các phép gán trong `ON DUPLICATE KEY UPDATE` trên hàng đang tồn tại.

Tuy nhiên, câu lệnh này **không phải là lời hứa "tự biết bản ghi nào đúng để cập nhật"**. Nó có những đặc điểm dễ gây lỗi: xung đột bởi **bất kỳ chỉ mục UNIQUE phù hợp**, nhiều khóa UNIQUE có thể chỉ tới nhiều hàng khác nhau, bản ghi gửi lại có thể gây cập nhật lặp, số hàng bị ảnh hưởng không đơn thuần là số bản ghi, giá trị `NULL` khác với không truyền cột, và ID tự tăng có thể tạo khoảng trống.

Bài học thuộc **Database SQL → Upsert và MERGE → INSERT ON DUPLICATE KEY UPDATE của MySQL**. Nội dung tập trung vào MySQL 8.x, đặc biệt cách dùng **row alias** trong các phiên bản hỗ trợ; đồng thời phân biệt với cú pháp `VALUES()` cũ, PostgreSQL `ON CONFLICT`, SQL chuẩn `MERGE` và một số đặc điểm của MariaDB.

Các ví dụ có thay đổi dữ liệu được thực hiện trên **bảng tạm MySQL** và thường được đặt trong transaction có `ROLLBACK`. Mục tiêu là hiểu rõ ngữ nghĩa trước khi đem upsert vào đồng bộ đơn hàng, kho hay thông tin khách hàng.

## 1. Upsert giải quyết vấn đề nào?

Giả sử bảng sản phẩm đã có mã `BK-01`:

```text
sku    | product_name | unit_price | stock_qty
-------+--------------+------------+----------
BK-01  | Sổ tay A     |      50.00 |       10
```

Hệ thống nhập liệu nhận bản tin:

```text
sku    = BK-01
name   = Sổ tay A (bản mới)
price  = 55.00
stock  = 12
```

Nếu chỉ dùng `INSERT`, mã `BK-01` đã có nên phát sinh lỗi trùng khóa `UNIQUE(sku)`. Nếu chỉ dùng `UPDATE`, lại không xử lý trường hợp mã SKU mới `PEN-02` chưa tồn tại.

Một cách viết cũ ở tầng ứng dụng:

```text
SELECT kiểm tra SKU có tồn tại?
  ├── Không → INSERT
  └── Có    → UPDATE
```

Cách này cần ít nhất hai thao tác và còn có nguy cơ tranh chấp: sau khi kiểm tra "chưa tồn tại", một transaction khác có thể chèn cùng SKU trước khi ta chèn.

Với upsert, quyết định **insert hay update** được giao cho MySQL thông qua ràng buộc khóa trong cùng một câu lệnh:

```text
INSERT ... ON DUPLICATE KEY UPDATE
                │
                ▼
       Thử chèn hàng mới
                │
       ┌────────┴─────────┐
       │                  │
   Không trùng       Trùng PRIMARY/UNIQUE
       │                  │
       ▼                  ▼
     INSERT              UPDATE
       │                  │
       └────────┬─────────┘
                ▼
        Trạng thái sau lệnh
```

**Điều kiện mấu chốt:** phải có khóa `PRIMARY KEY` hoặc `UNIQUE` phù hợp với **định danh nghiệp vụ**. Không có ràng buộc duy nhất đúng, MySQL không thể biết hai bản tin có cùng SKU là cùng một sản phẩm chỉ từ ý định của lập trình viên.

## 2. Cú pháp tổng quát trong MySQL

Một mẫu với `VALUES` trong `INSERT`:

```sql
INSERT INTO products (
    sku,
    product_name,
    unit_price,
    stock_qty
)
VALUES (
    'BK-01',
    'Sổ tay A mới',
    55.00,
    12
) AS incoming
ON DUPLICATE KEY UPDATE
    product_name = incoming.product_name,
    unit_price   = incoming.unit_price,
    stock_qty    = incoming.stock_qty;
```

Từng thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `INSERT INTO products (...)` | Xác định bảng và các cột đang được đề xuất chèn |
| `VALUES (...)` | Cung cấp dữ liệu của hàng mới |
| `AS incoming` | Đặt alias cho hàng **đang được đề xuất chèn**, theo cú pháp MySQL được hỗ trợ |
| `ON DUPLICATE KEY UPDATE` | Phần xử lý khi việc chèn vi phạm khóa chính hoặc chỉ mục UNIQUE |
| `product_name = incoming.product_name` | Gán cột bảng đích từ giá trị của hàng đề xuất |
| `unit_price = incoming.unit_price` | Khi xung đột, cập nhật giá bán |
| `stock_qty = incoming.stock_qty` | Khi xung đột, **thay thế** số lượng tồn bằng giá trị gửi đến |

Nếu chèn thành công, phần `UPDATE` không được dùng để thay đổi một hàng cũ. Nếu xung đột, phần `UPDATE` được áp dụng cho hàng đích mà MySQL đã tìm thấy qua khóa trùng.

### Row alias là tính năng theo phiên bản

Cú pháp `VALUES (...) AS incoming ON DUPLICATE KEY UPDATE ...` được hỗ trợ trong các phiên bản MySQL 8.0 hiện đại, với row alias cho `VALUES`/`SET` có từ MySQL 8.0.19. Trên MySQL cũ hơn, ví dụ này có thể chưa hợp lệ; cần dùng cú pháp được phiên bản đó hỗ trợ.

Các bản MySQL 8.0.20 trở đi khuyến nghị chuyển khỏi việc gọi **hàm** `VALUES(column_name)` ở vế UPDATE; chi tiết được giải thích ở mục 8.

**Đừng nhầm hai từ "VALUES":**

- `VALUES (...)` ngay sau `INSERT INTO` là cú pháp cung cấp hàng mới.
- `VALUES(column_name)` trong phần `ON DUPLICATE KEY UPDATE` là **cách truy cập giá trị đề xuất kiểu cũ**, đã bị deprecated trong MySQL hiện đại.

## 3. Bảng thực hành và dữ liệu ban đầu

Để tránh ảnh hưởng dữ liệu thật, tạo một **bảng tạm InnoDB**. Chạy toàn bộ ví dụ trong cùng một kết nối MySQL; bảng tạm tồn tại trong phiên tương ứng.

```sql
CREATE TEMPORARY TABLE products_288 (
    product_id   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku          VARCHAR(40) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    unit_price   DECIMAL(12, 2) NOT NULL,
    stock_qty    INT NOT NULL DEFAULT 0,
    description  VARCHAR(255) NULL,
    updated_at   TIMESTAMP(6) NOT NULL
                     DEFAULT CURRENT_TIMESTAMP(6)
                     ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_products_288_sku (sku)
) ENGINE = InnoDB;
```

Hai ràng buộc định danh:

- `product_id` là **khóa chính tự tăng**, dùng nội bộ.
- `sku` là **khóa duy nhất theo nghiệp vụ**, dùng nhận biết một sản phẩm qua dữ liệu nhập.

Nạp dữ liệu ban đầu:

```sql
INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty, description
)
VALUES
    ('BK-01',  'Sổ tay A', 50.00, 10, 'Bản đầu'),
    ('PEN-02', 'Bút xanh',   5.00, 100, 'Mực xanh'),
    ('BAG-03', 'Túi vải', 120.00, 4, NULL);

SELECT
    product_id,
    sku,
    product_name,
    unit_price,
    stock_qty,
    description
FROM products_288
ORDER BY sku;
```

Bảng có ba sản phẩm:

| sku | product_name | unit_price | stock_qty | description |
| --- | --- | ---: | ---: | --- |
| BAG-03 | Túi vải | 120.00 | 4 | `NULL` |
| BK-01 | Sổ tay A | 50.00 | 10 | Bản đầu |
| PEN-02 | Bút xanh | 5.00 | 100 | Mực xanh |

ID `AUTO_INCREMENT` có thể khác giữa các lần chạy và không được coi là số thứ tự liên tục không có khoảng trống. Các truy vấn dự đoán kết quả trong bài dùng `sku` thay vì phụ thuộc vào số ID được sinh.

### Vì sao dùng TEMPORARY TABLE?

`CREATE TEMPORARY TABLE` giúp giới hạn phạm vi bảng trong phiên MySQL thực hành. Nhưng nó **không biến mọi thao tác thành vô hại** nếu bạn thay nhầm tên bảng thành tên thật. Các câu `INSERT`, `UPDATE` và `DELETE` vẫn là thao tác thay đổi dữ liệu.

Các ví dụ thử cập nhật trong phần sau sẽ dùng:

```sql
START TRANSACTION;

-- Lệnh thử trên products_288.
-- SELECT kiểm tra.

ROLLBACK;
```

để hoàn tác các thay đổi dữ liệu của ví dụ. Mỗi ví dụ độc lập giả định bảng trở về **trạng thái ban đầu**.

## 4. Trường hợp thứ nhất: không trùng khóa, MySQL INSERT

Bắt đầu từ dữ liệu ban đầu, thử thêm một SKU hoàn toàn mới:

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty, description
)
VALUES (
    'MUG-04', 'Cốc gốm', 80.00, 6, 'Màu trắng'
) AS incoming
ON DUPLICATE KEY UPDATE
    product_name = incoming.product_name,
    unit_price   = incoming.unit_price,
    stock_qty    = incoming.stock_qty,
    description  = incoming.description;

SELECT sku, product_name, unit_price, stock_qty, description
FROM products_288
WHERE sku = 'MUG-04';

ROLLBACK;
```

Khi chưa có `MUG-04`, MySQL **chèn hàng mới**. Kết quả `SELECT` trước `ROLLBACK`:

| sku | product_name | unit_price | stock_qty | description |
| --- | --- | ---: | ---: | --- |
| MUG-04 | Cốc gốm | 80.00 | 6 | Màu trắng |

`ROLLBACK` hoàn tác lần chèn này; sau đó `MUG-04` không còn trong bảng thực hành, trừ khi đã được ghi ở một thao tác khác.

**Điểm cần nhớ:** khi không trùng khóa, câu lệnh hoạt động như `INSERT`. Phần `ON DUPLICATE KEY UPDATE` không có nghĩa MySQL sẽ cập nhật mọi hàng sau khi chèn.

## 5. Trường hợp thứ hai: trùng UNIQUE(sku), MySQL UPDATE

Bắt đầu từ trạng thái ban đầu, `BK-01` đã có sẵn:

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty, description
)
VALUES (
    'BK-01',
    'Sổ tay A tái bản',
    55.00,
    12,
    'Cập nhật danh mục'
) AS incoming
ON DUPLICATE KEY UPDATE
    product_name = incoming.product_name,
    unit_price   = incoming.unit_price,
    stock_qty    = incoming.stock_qty,
    description  = incoming.description;

SELECT sku, product_name, unit_price, stock_qty, description
FROM products_288
WHERE sku = 'BK-01';

ROLLBACK;
```

Vì `sku='BK-01'` vi phạm ràng buộc `UNIQUE(sku)` nếu chèn thêm hàng, MySQL chạy các phép gán trên bản ghi `BK-01` **đã có**.

Kết quả trong transaction:

| sku | product_name | unit_price | stock_qty | description |
| --- | --- | ---: | ---: | --- |
| BK-01 | Sổ tay A tái bản | 55.00 | 12 | Cập nhật danh mục |

Đây là **thay thế trạng thái** (*state replacement*): số lượng tồn mới là 12, không phải số lượng cũ 10 cộng thêm 12.

Nếu không viết phép gán cho `description`, cột này sẽ **giữ giá trị cũ** trong nhánh UPDATE. Upsert không tự cập nhật tất cả cột xuất hiện ở danh sách `INSERT`; chỉ các cột trong mệnh đề `ON DUPLICATE KEY UPDATE` mới được gán khi có xung đột, ngoài những thay đổi tự động do cơ chế bảng, trigger hoặc cột được cấu hình.

## 6. PRIMARY KEY và UNIQUE: điều gì kích hoạt nhánh UPDATE?

MySQL chuyển từ insert sang update khi một giá trị chèn gây **trùng khóa chính** hoặc **trùng khóa duy nhất**. Một điều kiện tìm hàng thông thường `WHERE sku = ...` không tham gia tự động vào quyết định này, vì trong cú pháp `INSERT ... ON DUPLICATE KEY UPDATE` không có `WHERE` để định nghĩa xung đột như một câu `UPDATE`.

Trong bảng mẫu:

```sql
PRIMARY KEY (product_id),
UNIQUE KEY uq_products_288_sku (sku)
```

cả hai ràng buộc có thể xác định xung đột.

### 6.1. Trùng SKU dù không truyền product_id

Trong ví dụ `BK-01`, ta không truyền `product_id`; MySQL có thể dự định sinh một ID mới, nhưng `UNIQUE(sku)` phát hiện SKU đã tồn tại. Nhánh UPDATE vì thế được thực hiện đối với sản phẩm đã có.

### 6.2. Trùng product_id dù SKU mới

Xem ví dụ minh họa sau, **không thực thi** vì cần biết một ID thật:

```sql
-- Mẫu cảnh báo: product_id trùng cũng có thể kích hoạt UPDATE,
-- không chỉ trùng SKU.
--
-- INSERT INTO products_288 (product_id, sku, product_name, unit_price)
-- VALUES (some_existing_product_id, 'NEW-SKU', 'Tên mới', 10.00)
-- AS incoming
-- ON DUPLICATE KEY UPDATE
--     product_name = incoming.product_name;
```

Nếu ID đã tồn tại, MySQL có thể chọn nhánh UPDATE ngay cả khi `sku` mới. Điều này rất quan trọng nếu ứng dụng tưởng rằng nó đang xác định bản ghi chỉ bằng SKU nhưng lại truyền thêm một ID ngoại lai.

### 6.3. UNIQUE không giống khóa ngoại

- `PRIMARY KEY` nhận diện duy nhất một hàng và không cho `NULL`.
- `UNIQUE` ngăn các giá trị hoặc tổ hợp giá trị trùng nhau theo quy tắc của chỉ mục và DBMS.
- `FOREIGN KEY` kiểm tra quan hệ tham chiếu; nó **không phải** một chỉ mục duy nhất được dùng làm mục tiêu upsert, trừ khi các ràng buộc khác cũng tồn tại.

Nếu bảng có `sku` không được đặt `UNIQUE`, việc gửi lại cùng SKU có thể **chèn thêm bản sao** thay vì UPDATE, dù tên cột là `sku`.

## 7. Không có đích xung đột được chỉ định tường minh

Đây là khác biệt đáng chú ý của MySQL so với một số phương ngữ khác.

MySQL:

```sql
INSERT INTO products_288 (sku, product_name, unit_price)
VALUES ('BK-01', 'Sổ tay', 55.00) AS incoming
ON DUPLICATE KEY UPDATE
    unit_price = incoming.unit_price;
```

Không có đoạn như:

```sql
-- Cú pháp PostgreSQL, KHÔNG phải MySQL:
ON CONFLICT (sku) DO UPDATE ...
```

Trong MySQL, điều kiện kích hoạt là **bất kỳ vi phạm PRIMARY/UNIQUE nào liên quan tới hàng đề xuất**. Bạn không chọn một chỉ mục duy nhất cụ thể để làm conflict target trong câu lệnh.

### Một bảng có hai UNIQUE có thể gây xung đột với hai hàng khác nhau

Xem bảng ví dụ riêng:

```sql
CREATE TEMPORARY TABLE customer_keys_288 (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    email       VARCHAR(255) NOT NULL,
    username    VARCHAR(100) NOT NULL,
    note        VARCHAR(255),
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customer_email_288 (email),
    UNIQUE KEY uq_customer_username_288 (username)
) ENGINE = InnoDB;

INSERT INTO customer_keys_288 (email, username, note)
VALUES
    ('an@example.test', 'an_user', 'Khách A'),
    ('binh@example.test', 'binh_user', 'Khách B');
```

Đề xuất mới:

```text
email = 'an@example.test'     → trùng email của khách A
username = 'binh_user'        → trùng username của khách B
```

Một dòng INSERT như vậy **mâu thuẫn với hai hàng khác nhau qua hai chỉ mục UNIQUE**.

```sql
-- CẢNH BÁO: không chạy như một thao tác đồng bộ thực tế.
-- Hàng đề xuất trùng email ở A và username ở B.
--
-- INSERT INTO customer_keys_288 (email, username, note)
-- VALUES ('an@example.test', 'binh_user', 'Dữ liệu mới') AS incoming
-- ON DUPLICATE KEY UPDATE
--     note = incoming.note;
```

MySQL không có quy tắc nghiệp vụ “email quan trọng hơn username” được biểu diễn trong lệnh trên. Việc dựa vào một hàng trong số các hàng xung đột làm mục tiêu UPDATE là **không an toàn**. Nếu nhánh UPDATE còn thay đổi các cột UNIQUE, nó có thể gây **vi phạm khóa thứ hai** và khiến statement lỗi.

**Khuyến nghị:** hạn chế dùng `ON DUPLICATE KEY UPDATE` trên bảng có nhiều UNIQUE mà cùng một đề xuất có thể va vào **các hàng khác nhau**; hoặc phải thiết kế dữ liệu, điều kiện nhập và cách xác định danh tính để loại mâu thuẫn đó trước khi upsert.

## 8. Cách lấy giá trị đề xuất: alias mới và VALUES() kiểu cũ

Nhiều tài liệu cũ dùng:

```sql
-- Cú pháp lịch sử MySQL; VALUES(column) ở phần UPDATE
-- bị deprecated trong MySQL 8.0.20+.
INSERT INTO products_288 (sku, product_name, unit_price)
VALUES ('BK-01', 'Sổ tay A', 55.00)
ON DUPLICATE KEY UPDATE
    product_name = VALUES(product_name),
    unit_price   = VALUES(unit_price);
```

`VALUES(unit_price)` ở đây không phải giá hiện có của bảng đích. Nó chỉ tới **giá trị unit_price được đề xuất chèn**.

Trong MySQL hiện đại, nên dùng row alias:

```sql
INSERT INTO products_288 (
    sku, product_name, unit_price
)
VALUES (
    'BK-01', 'Sổ tay A', 55.00
) AS incoming
ON DUPLICATE KEY UPDATE
    product_name = incoming.product_name,
    unit_price   = incoming.unit_price;
```

### Vì sao chuyển sang alias?

- Nhìn rõ hai phía: cột đích `unit_price` và giá trị đề xuất `incoming.unit_price`.
- Không phụ thuộc vào hàm `VALUES(column)` đã bị deprecated trong MySQL từ 8.0.20.
- Đỡ nhầm `VALUES` dùng để nhập hàng với `VALUES()` dùng để đọc giá trị đề xuất.
- Có thể áp dụng thống nhất cho ví dụ một hàng hoặc nhiều hàng trong dạng `INSERT ... VALUES` theo phiên bản hỗ trợ.

### Phiên bản và MariaDB

Đừng suy ra mọi bản MySQL hoặc MariaDB đều chấp nhận cú pháp row alias giống nhau:

- MySQL trước 8.0.19 chưa hỗ trợ đúng mẫu alias sau `VALUES` như bài này.
- MySQL 8.0.20 trở đi cảnh báo deprecation đối với hàm `VALUES(column)` trong ngữ cảnh này; cần ưu tiên cách tham chiếu mới.
- MariaDB là một sản phẩm khác MySQL; một số phiên bản MariaDB vẫn tài liệu hóa `VALUES(column)` trong `ON DUPLICATE KEY UPDATE`. Không nên áp dụng thông báo deprecation của MySQL một cách máy móc cho mọi MariaDB.

Khi làm việc với một máy chủ cụ thể, kiểm tra `SELECT VERSION();` để biết phiên bản/nhánh sản phẩm trước khi chọn mẫu cú pháp.

## 9. Thay thế số lượng hay cộng số lượng: hai yêu cầu khác nhau

Đây là một trong những lỗi upsert lớn nhất trong ứng dụng kho.

### 9.1. Nguồn gửi số lượng tồn **tuyệt đối**

Nếu bản tin nghĩa là “tồn kho hiện được xác nhận là 12”, dùng **thay thế**:

```sql
INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
VALUES (
    'BK-01', 'Sổ tay A', 50.00, 12
) AS incoming
ON DUPLICATE KEY UPDATE
    stock_qty = incoming.stock_qty;
```

Bản ghi `BK-01` đổi từ 10 thành **12**.

Nếu bản tin giống hệt được gửi lại, số lượng vẫn là 12. Kiểu cập nhật này gần với tính **idempotent** về giá trị kho, với điều kiện không có cơ chế khác làm thay đổi các cột không mong muốn.

### 9.2. Nguồn gửi **khoản tăng thêm**

Nếu bản tin nghĩa là “vừa nhập thêm 12 cuốn”, dùng cộng dồn:

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
VALUES (
    'BK-01', 'Sổ tay A', 50.00, 12
) AS incoming
ON DUPLICATE KEY UPDATE
    stock_qty = stock_qty + incoming.stock_qty;

SELECT sku, stock_qty
FROM products_288
WHERE sku = 'BK-01';

ROLLBACK;
```

Với số lượng ban đầu 10, kết quả trong transaction là **22**.

Nếu gửi lại **hai lần** cùng bản tin, kho có thể tăng thêm **24**, không phải 12. `ON DUPLICATE KEY UPDATE` **không tự chống áp dụng sự kiện lặp**.

### So sánh

| Nguồn biểu thị | Phép gán thích hợp | Gửi lại cùng bản tin |
| --- | --- | --- |
| Trạng thái tồn kho mới | `stock_qty = incoming.stock_qty` | Không tăng lần nữa |
| Chênh lệch tồn kho | `stock_qty = stock_qty + incoming.stock_qty` | Có thể cộng thêm lần nữa |
| Chênh lệch đã có mã sự kiện duy nhất | Cần cơ chế ghi nhận sự kiện đã xử lý | Có thể ngăn xử lý lặp nếu giao dịch được thiết kế đúng |

Trước khi chọn `= incoming.value` hay `= old + incoming.value`, phải trả lời: **hệ thống nguồn gửi trạng thái hay gửi sự kiện?**

## 10. Upsert counters và nguy cơ không idempotent

Một bảng đếm lượt truy cập có thể dùng khóa chính làm định danh:

```sql
CREATE TEMPORARY TABLE daily_counters_288 (
    counter_key VARCHAR(100) NOT NULL PRIMARY KEY,
    hit_count   BIGINT NOT NULL DEFAULT 0
) ENGINE = InnoDB;
```

Tăng thêm một lượt:

```sql
START TRANSACTION;

INSERT INTO daily_counters_288 (counter_key, hit_count)
VALUES ('home:2026-11-14', 1) AS incoming
ON DUPLICATE KEY UPDATE
    hit_count = hit_count + incoming.hit_count;

-- Gửi lại cùng thao tác:
INSERT INTO daily_counters_288 (counter_key, hit_count)
VALUES ('home:2026-11-14', 1) AS incoming
ON DUPLICATE KEY UPDATE
    hit_count = hit_count + incoming.hit_count;

SELECT counter_key, hit_count
FROM daily_counters_288;

ROLLBACK;
```

Kết quả trong transaction là **2**, không phải 1.

Phép cộng dồn có thể chính xác khi **mỗi lần gọi thật sự là một lượt mới**. Nhưng với bản tin có thể retry do timeout, kết nối gián đoạn hoặc hệ thống hàng đợi gửi lại, cần thiết kế *deduplication* theo **event ID**, không chỉ theo `counter_key`.

Một giải pháp ứng dụng thường dùng bảng sự kiện có khóa `UNIQUE(event_id)`, ghi nhận việc đã áp dụng sự kiện và điều chỉnh bộ đếm trong **cùng transaction**. Cách triển khai cụ thể cần bảo đảm nếu event ID đã xử lý thì **không tăng thêm lần nữa**.

**Upsert giải quyết xung đột khóa của bản ghi đích; nó không mặc định bảo đảm exactly-once processing cho các sự kiện.**

## 11. Insert nhiều hàng trong một statement

MySQL cho phép upsert một batch:

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
VALUES
    ('BK-01',  'Sổ tay A mới', 55.00, 12),
    ('PEN-02', 'Bút xanh mới',   6.00, 80),
    ('MUG-04', 'Cốc gốm',      80.00,  6)
AS incoming
ON DUPLICATE KEY UPDATE
    product_name = incoming.product_name,
    unit_price   = incoming.unit_price,
    stock_qty    = incoming.stock_qty;

SELECT sku, product_name, unit_price, stock_qty
FROM products_288
ORDER BY sku;

ROLLBACK;
```

Trong batch này:

- `BK-01` đã có, dùng nhánh UPDATE.
- `PEN-02` đã có, dùng nhánh UPDATE.
- `MUG-04` chưa có, dùng nhánh INSERT.
- `BAG-03` không xuất hiện trong batch, được giữ nguyên.

Khi làm việc theo batch, cần nhớ rằng **mỗi hàng đề xuất** được xử lý theo xung đột khóa tương ứng. Không có quy tắc “batch có một hàng trùng thì tất cả hàng đều UPDATE”.

### Điều gì xảy ra nếu batch chứa hai hàng cùng SKU?

Ví dụ:

```sql
-- Cảnh báo: nguồn có hai hàng cùng khóa nghiệp vụ.
-- Không sử dụng như một mẫu đồng bộ sản phẩm.
--
-- INSERT INTO products_288
--     (sku, product_name, unit_price, stock_qty)
-- VALUES
--     ('BK-01', 'Tên A', 55.00, 12),
--     ('BK-01', 'Tên B', 60.00, 15)
-- AS incoming
-- ON DUPLICATE KEY UPDATE
--     product_name = incoming.product_name,
--     unit_price = incoming.unit_price,
--     stock_qty = incoming.stock_qty;
```

Hai bản tin trong cùng batch đang yêu cầu **hai trạng thái khác nhau** cho một SKU. Ngay cả khi MySQL có thể thực hiện nhiều thao tác với cùng hàng trong quá trình xử lý, điều đó không định nghĩa rằng giá trị nào mới là hợp đồng nghiệp vụ.

Hãy **chuẩn hóa nguồn trước khi upsert**: xác định bản nào được phê duyệt, bản nào mới nhất theo timestamp/sequence, cách xử lý đồng hạng và cách phát hiện các mâu thuẫn.

### Không dùng DISTINCT tùy tiện để "sửa" batch

`SELECT DISTINCT sku, price, stock_qty` chỉ loại những hàng **trùng toàn bộ giá trị**, không giải quyết hai giá khác nhau của cùng một SKU. Để giữ một bản theo SKU, cần quy tắc ưu tiên rõ ràng (ví dụ `ROW_NUMBER()` trong nguồn được chuẩn bị) hoặc từ chối batch chưa hợp lệ.

## 12. INSERT ... SELECT ... ON DUPLICATE KEY UPDATE

Bên cạnh `VALUES`, MySQL cho phép lấy hàng từ một `SELECT` làm nguồn của `INSERT`. Ví dụ đồng bộ giá sản phẩm từ bảng staging.

Tạo bảng tạm:

```sql
CREATE TEMPORARY TABLE incoming_prices_288 (
    sku        VARCHAR(40) NOT NULL,
    new_price  DECIMAL(12, 2) NOT NULL,
    source_seq BIGINT NOT NULL,
    PRIMARY KEY (sku)
) ENGINE = InnoDB;

INSERT INTO incoming_prices_288 (sku, new_price, source_seq)
VALUES
    ('BK-01', 56.00, 101),
    ('PEN-02',  6.00, 102);
```

Lúc này nguồn đã có một hàng cho mỗi SKU nhờ `PRIMARY KEY(sku)`.

### MySQL: SELECT từ một derived table có alias

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
SELECT
    src.sku,
    CONCAT('Đồng bộ ', src.sku),
    src.new_price,
    0
FROM (
    SELECT sku, new_price, source_seq
    FROM incoming_prices_288
) AS src
WHERE TRUE
ON DUPLICATE KEY UPDATE
    unit_price = src.new_price;

SELECT sku, unit_price, stock_qty
FROM products_288
WHERE sku IN ('BK-01', 'PEN-02')
ORDER BY sku;

ROLLBACK;
```

Kết quả hai SKU đã có sẽ được cập nhật giá thành 56 và 6, còn `stock_qty` **giữ nguyên** vì không có phép gán cho nó trong nhánh UPDATE.

Chú ý hai điểm riêng của MySQL:

1. Với `INSERT ... SELECT ... ON DUPLICATE KEY UPDATE`, cách tham chiếu giá trị nguồn và phạm vi alias khác mẫu `VALUES (...) AS incoming`. Ví dụ dùng `src.new_price` từ derived table.
2. Khi `INSERT ... SELECT` không có `WHERE`, trình phân tích cú pháp của MySQL có thể gặp sự nhập nhằng giữa `ON` của `JOIN` và `ON DUPLICATE KEY UPDATE`. Viết `WHERE TRUE` là một mẫu được sử dụng để làm rõ cú pháp trong những trường hợp đó.

`WHERE TRUE` trong ví dụ **không phải bộ lọc nghiệp vụ**; mọi hàng của nguồn đều được chọn. Nó chỉ giúp câu lệnh dễ phân tích. Với nguồn thật, có thể thêm bộ lọc cần thiết thay vì `TRUE`.

### Đừng dùng dữ liệu nguồn nhiều hàng trên cùng khóa nếu chưa định nghĩa kết quả

Một bảng staging có thể chứa nhiều bản cập nhật giá cho cùng SKU theo thời gian. Nếu đưa tất cả vào `INSERT ... SELECT`, một SKU có thể được xử lý nhiều lần. Tốt hơn là chọn **một hàng duy nhất theo SKU** trước, dựa trên timestamp/sequence và quy tắc phá hòa, hoặc kiểm tra nguồn trùng rồi từ chối import.

## 13. Chọn dữ liệu staging mới nhất với ROW_NUMBER

Giả sử bảng staging có lịch sử nhiều bản tin, không phải một hàng mỗi SKU:

```sql
CREATE TEMPORARY TABLE catalog_feed_288 (
    feed_id       BIGINT NOT NULL PRIMARY KEY,
    sku           VARCHAR(40) NOT NULL,
    product_name  VARCHAR(200) NOT NULL,
    new_price     DECIMAL(12, 2) NOT NULL,
    source_time   DATETIME(6) NOT NULL
) ENGINE = InnoDB;

INSERT INTO catalog_feed_288 (
    feed_id, sku, product_name, new_price, source_time
)
VALUES
    (10, 'BK-01', 'Sổ tay bản 1', 54.00, '2026-10-01 08:00:00'),
    (11, 'BK-01', 'Sổ tay bản 2', 58.00, '2026-10-03 08:00:00'),
    (12, 'PEN-02', 'Bút mới',     6.00, '2026-10-02 09:00:00'),
    (13, 'BK-01', 'Sổ tay bản 3', 59.00, '2026-10-03 08:00:00');
```

SKU `BK-01` có **hai bản cùng `source_time` mới nhất**, `feed_id = 11` và `feed_id = 13`.

Nếu nghiệp vụ đồng ý dùng `feed_id` làm khóa phá hòa, chọn:

```sql
WITH ranked AS (
    SELECT
        feed_id,
        sku,
        product_name,
        new_price,
        source_time,
        ROW_NUMBER() OVER (
            PARTITION BY sku
            ORDER BY source_time DESC, feed_id DESC
        ) AS rn
    FROM catalog_feed_288
)
SELECT feed_id, sku, product_name, new_price, source_time
FROM ranked
WHERE rn = 1
ORDER BY sku;
```

Kết quả:

| sku | feed_id | product_name | new_price |
| --- | ---: | --- | ---: |
| BK-01 | 13 | Sổ tay bản 3 | 59.00 |
| PEN-02 | 12 | Bút mới | 6.00 |

### Ghép lựa chọn nguồn với INSERT ... SELECT

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
SELECT
    chosen.sku,
    chosen.product_name,
    chosen.new_price,
    0
FROM (
    SELECT
        f.sku,
        f.product_name,
        f.new_price,
        ROW_NUMBER() OVER (
            PARTITION BY f.sku
            ORDER BY f.source_time DESC, f.feed_id DESC
        ) AS rn
    FROM catalog_feed_288 AS f
) AS chosen
WHERE chosen.rn = 1
ON DUPLICATE KEY UPDATE
    product_name = chosen.product_name,
    unit_price   = chosen.new_price;

SELECT sku, product_name, unit_price
FROM products_288
WHERE sku IN ('BK-01', 'PEN-02')
ORDER BY sku;

ROLLBACK;
```

Giờ mỗi SKU của nguồn có **tối đa một hàng**, nên logic upsert không còn phải phụ thuộc vào thứ tự một batch có nhiều bản cập nhật cùng SKU.

**Lưu ý:** đây là quyết định theo quy tắc **nguồn staging mới nhất**, không tự giải quyết tình huống **bảng đích đã chứa một phiên bản còn mới hơn**. Bài toán đồng bộ hai chiều hoặc nhận bản tin lệch thứ tự còn cần versioning và quy tắc chống ghi đè dữ liệu mới bằng dữ liệu cũ.

## 14. Chống bản tin cũ ghi đè bản mới

Trong một hệ thống đồng bộ, hai bản tin có thể đến không đúng thứ tự:

```text
Bản tin A: SKU BK-01, version 8, price 58
Bản tin B: SKU BK-01, version 7, price 54
```

Nếu B đến sau A và phần UPDATE luôn ghi đè giá, trạng thái sẽ **thoái lui** từ version 8 xuống version 7.

Một bảng có thể lưu phiên bản nguồn:

```sql
CREATE TEMPORARY TABLE versioned_prices_288 (
    sku            VARCHAR(40) NOT NULL PRIMARY KEY,
    unit_price     DECIMAL(12, 2) NOT NULL,
    source_version BIGINT NOT NULL
) ENGINE = InnoDB;

INSERT INTO versioned_prices_288
    (sku, unit_price, source_version)
VALUES ('BK-01', 58.00, 8);
```

Truy vấn upsert theo nguyên tắc “chỉ nhận giá mới khi version mới lớn hơn”:

```sql
START TRANSACTION;

INSERT INTO versioned_prices_288
    (sku, unit_price, source_version)
VALUES ('BK-01', 54.00, 7) AS incoming
ON DUPLICATE KEY UPDATE
    unit_price = IF(
        incoming.source_version > source_version,
        incoming.unit_price,
        unit_price
    ),
    source_version = GREATEST(
        source_version,
        incoming.source_version
    );

SELECT sku, unit_price, source_version
FROM versioned_prices_288;

ROLLBACK;
```

Kết quả giữ **58.00 / version 8**.

Trong MySQL, các phép gán trong câu cập nhật một bảng thường được đánh giá theo thứ tự viết; ví dụ đặt phép gán `unit_price` **trước** việc thay đổi `source_version` để điều kiện so sánh dùng phiên bản cũ. Không nên coi thứ tự đánh giá phép gán là giống nhau giữa mọi phương ngữ hay mọi dạng cập nhật nhiều bảng.

Đối với quy tắc versioning phức tạp hơn, có thể thiết kế một cột/trạng thái nguồn duy nhất và kiểm soát transaction/locking riêng. Điều quan trọng nhất là **tiêu chí mới hơn phải do hợp đồng nguồn quy định**, không mặc định dùng thời gian máy khách nếu đồng hồ có thể lệch.

### MySQL không có WHERE riêng sau ON DUPLICATE KEY UPDATE

Không thể bê nguyên mẫu PostgreSQL:

```sql
-- PostgreSQL, không phải MySQL:
ON CONFLICT (sku) DO UPDATE
SET unit_price = EXCLUDED.unit_price
WHERE EXCLUDED.source_version > target.source_version;
```

sang MySQL. Với MySQL, điều kiện chọn có thể được diễn đạt trong các phép gán bằng `IF`/`CASE`, hoặc được giải quyết tại một bước xác nhận dữ liệu và cập nhật có kiểm soát khác.

## 15. Số hàng bị ảnh hưởng: 1, 2 và 0 không đơn giản là số SKU

Với `INSERT ... ON DUPLICATE KEY UPDATE`, MySQL thường báo số hàng bị ảnh hưởng **trên mỗi hàng đề xuất** theo ngữ nghĩa sau:

| Trường hợp | Affected rows thông thường |
| --- | ---: |
| Thêm một hàng mới | 1 |
| Trùng khóa và thực sự cập nhật giá trị | 2 |
| Trùng khóa nhưng các giá trị được gán vẫn giống hệt giá trị đang có | 0 |

Ví dụ, từ trạng thái ban đầu:

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
VALUES (
    'BK-01', 'Sổ tay A', 55.00, 10
) AS incoming
ON DUPLICATE KEY UPDATE
    unit_price = incoming.unit_price;

SELECT ROW_COUNT() AS affected_rows_for_statement;

ROLLBACK;
```

`BK-01` đã có và `unit_price` đổi từ 50 lên 55, nên trong cách báo thông thường giá trị `ROW_COUNT()` là **2**, mặc dù **chỉ một hàng sản phẩm** thực sự được cập nhật.

### CLIENT_FOUND_ROWS và no-op

Nếu kết nối được cấu hình với cờ `CLIENT_FOUND_ROWS`, việc cập nhật một hàng đã có nhưng **không làm thay đổi dữ liệu** có thể được tính là **1** thay vì 0. Mặt khác, các trigger hoặc cột tự động có thể ảnh hưởng việc quan sát giá trị thay đổi.

Vì vậy không nên viết logic ứng dụng:

```text
affectedRows == 2 → chắc chắn có hai sản phẩm thay đổi
affectedRows == 1 → chắc chắn chèn
affectedRows == 0 → chắc chắn không tìm thấy khóa
```

Các kết luận trên không đúng một cách tổng quát.

### Sau batch, affected rows cộng theo từng hàng đề xuất

Một batch gồm một insert mới, một update có thay đổi và một no-op có thể trả **1 + 2 + 0 = 3** affected rows theo cấu hình thông thường, dù batch xử lý **ba SKU**.

Khi cần **đếm chính xác số sản phẩm đã được chèn và đã được cập nhật** cho báo cáo kiểm toán, nên dùng cơ chế lưu vết và kết quả nghiệp vụ riêng, không chỉ dựa vào tổng affected rows.

## 16. AUTO_INCREMENT: không hứa hẹn ID liên tục

Trong bảng `products_288`:

```sql
product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT
```

ngay cả khi một hàng đề xuất với SKU đã tồn tại chuyển sang nhánh UPDATE, MySQL/InnoDB có thể đã cấp phát giá trị tự tăng trong quá trình xử lý INSERT. Điều này có thể tạo ra **khoảng trống trong dãy product_id**.

Ví dụ ý nghĩa:

```text
product_id: 1, 2, 3, 5, 8, ...
```

Không có gì bất thường nếu ID nhảy số do rollback, xung đột, retry, concurrency hoặc cơ chế cấp phát của DBMS.

**Không dùng AUTO_INCREMENT như số lượng giao dịch, thứ tự thời gian tuyệt đối, hoặc chứng cứ rằng mọi ID giữa hai đầu phải tồn tại.**

### LAST_INSERT_ID() có phải cách xác định insert/update?

`LAST_INSERT_ID()` chủ yếu dùng khi cần ID tự tăng liên quan tới câu lệnh trong một kết nối. Tuy nhiên, cách trả giá trị của driver, câu lệnh và trường hợp trùng khóa có các chi tiết riêng. Không nên suy ngược loại thao tác chỉ từ ID này.

Một mẫu được dùng để lấy ID của hàng tồn tại khi nhánh UPDATE chạy là:

```sql
-- MySQL: mẫu nâng cao; chỉ dùng khi hiểu quy ước API/driver.
-- INSERT INTO products_288 (...)
-- VALUES (...) AS incoming
-- ON DUPLICATE KEY UPDATE
--     product_id = LAST_INSERT_ID(product_id),
--     unit_price = incoming.unit_price;
```

Biểu thức `LAST_INSERT_ID(product_id)` có tác dụng phụ đặt giá trị truy xuất qua `LAST_INSERT_ID()` cho kết nối theo quy tắc MySQL. Đây **không phải điều kiện quyết định row nào được chọn**, và không biến một lệnh có nhiều UNIQUE mâu thuẫn thành an toàn.

Khi cần ID của hàng vừa upsert để dùng tiếp, hãy kiểm tra hợp đồng của connector/driver và phiên bản MySQL, đồng thời tránh trộn lẫn "ID hàng" với "số hàng bị ảnh hưởng".

## 17. Giá trị NULL: khác giữa không truyền cột và truyền NULL

Ba tình huống này không giống nhau:

1. **Không truyền cột** trong `INSERT`: MySQL dùng `DEFAULT` của cột nếu có, hoặc xử lý theo ràng buộc và SQL mode.
2. **Truyền NULL tường minh:** đề xuất giá trị thiếu; nếu cột `NOT NULL`, có thể gây lỗi hoặc bị xử lý theo chế độ thích hợp.
3. **Trong nhánh UPDATE, không gán cột đó:** giá trị đang có **giữ nguyên**, ngoài các cột tự cập nhật/triggers.

Ví dụ với `description` cho phép `NULL`.

### Giữ mô tả cũ khi nguồn thiếu giá trị

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty, description
)
VALUES (
    'BK-01', 'Sổ tay A', 55.00, 10, NULL
) AS incoming
ON DUPLICATE KEY UPDATE
    unit_price  = incoming.unit_price,
    description = COALESCE(
        incoming.description,
        description
    );

SELECT sku, unit_price, description
FROM products_288
WHERE sku = 'BK-01';

ROLLBACK;
```

Kết quả: `unit_price = 55`, `description` vẫn là **'Bản đầu'** vì `incoming.description IS NULL` được coi là "không có mô tả mới để thay thế".

### Muốn xóa mô tả cũ thì sao?

Nếu nguồn gửi `NULL` với ý nghĩa **“xóa mô tả”**, biểu thức `COALESCE(incoming.description, description)` là **sai**, vì nó giữ nguyên nội dung cũ.

Lúc đó cần:

```sql
description = incoming.description
```

để cho phép cập nhật thành `NULL`.

**Cần hợp đồng API phân biệt “trường không xuất hiện trong payload” và “trường có mặt với giá trị null”** nếu ứng dụng hỗ trợ cập nhật từng phần. Một câu `INSERT` thường có schema cột cố định; việc chuyển payload thành SQL phải bảo toàn sự phân biệt đó một cách có chủ đích.

### NULL trong UNIQUE

Trong MySQL, một chỉ mục `UNIQUE` trên cột **cho phép NULL** thông thường có thể chứa nhiều hàng có `NULL` ở cột đó. Hai hàng cùng `NULL` trong một UNIQUE nullable không nhất thiết bị coi là xung đột để kích hoạt upsert.

Ngược lại, `PRIMARY KEY` không cho phép `NULL`.

Ví dụ:

```sql
CREATE TEMPORARY TABLE nullable_codes_288 (
    id   INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(30) NULL UNIQUE,
    note VARCHAR(100)
) ENGINE = InnoDB;

INSERT INTO nullable_codes_288 (code, note)
VALUES (NULL, 'A'), (NULL, 'B');

SELECT id, code, note
FROM nullable_codes_288
ORDER BY id;
```

Hai hàng có `code = NULL` có thể cùng tồn tại vì UNIQUE nullable không xem chúng là cùng một mã xác định.

Nếu nghiệp vụ cần “mỗi thực thể có đúng một mã duy nhất”, nên cân nhắc `NOT NULL UNIQUE` hoặc một mô hình tách riêng bản ghi chưa có mã, thay vì kỳ vọng upsert tìm thấy bản ghi cũ khi `code = NULL`.

## 18. Collation: hai chuỗi khác chữ vẫn có thể trùng UNIQUE

Trong MySQL, cách so sánh chuỗi chịu ảnh hưởng của **collation** trên cột/chỉ mục. Một collation không phân biệt chữ hoa/chữ thường có thể coi:

```text
BK-01
bk-01
```

là cùng một khóa `UNIQUE(sku)`.

Tùy collation, cả việc so sánh dấu, khoảng trắng ở cuối hoặc các quy tắc ký tự Unicode cũng có thể ảnh hưởng cách xác định trùng khóa.

Vì thế:

- Không mặc định rằng SKU viết khác chữ hoa/thường sẽ được chèn thành hai hàng.
- Không tự khẳng định mọi collation đều phân biệt/không phân biệt dấu giống nhau.
- Chọn collation phản ánh chính sách định danh: mã sản phẩm có phân biệt hoa/thường hay không?
- Khi nhập liệu, chuẩn hóa SKU (nếu nghiệp vụ quy định) ở tầng phù hợp và lưu bằng một biểu diễn nhất quán.
- Nếu đổi collation của cột có UNIQUE, hãy kiểm tra nguy cơ hai mã trước đây khác nhau nay trở thành trùng.

**Upsert dựa trên kết quả kiểm tra khóa của cơ sở dữ liệu, không dựa trên `String.equals` của Java hay so sánh mà lập trình viên suy nghĩ trong đầu.**

## 19. UNIQUE ghép: định danh theo nhiều cột

Một đơn vị tồn kho có thể được nhận diện bởi **(warehouse_id, sku)**, không chỉ SKU.

```sql
CREATE TEMPORARY TABLE warehouse_stock_288 (
    warehouse_id INT NOT NULL,
    sku          VARCHAR(40) NOT NULL,
    stock_qty    INT NOT NULL DEFAULT 0,
    PRIMARY KEY (warehouse_id, sku)
) ENGINE = InnoDB;
```

Khóa chính ghép cho phép:

```text
warehouse_id | sku    | stock_qty
-------------+--------+----------
1            | BK-01  | 10
2            | BK-01  | 20
```

Hai hàng khác nhau vì thuộc hai kho.

```sql
INSERT INTO warehouse_stock_288 (
    warehouse_id, sku, stock_qty
)
VALUES
    (1, 'BK-01', 10),
    (2, 'BK-01', 20);
```

Upsert theo **đúng cặp khóa**:

```sql
START TRANSACTION;

INSERT INTO warehouse_stock_288 (
    warehouse_id, sku, stock_qty
)
VALUES (1, 'BK-01', 15) AS incoming
ON DUPLICATE KEY UPDATE
    stock_qty = incoming.stock_qty;

SELECT warehouse_id, sku, stock_qty
FROM warehouse_stock_288
ORDER BY warehouse_id, sku;

ROLLBACK;
```

Kết quả trong transaction: kho 1 có `BK-01 = 15`, kho 2 vẫn `BK-01 = 20`.

Đừng tạo `UNIQUE(sku)` riêng nếu SKU được phép tồn tại ở nhiều kho. Nếu bảng vừa có `PRIMARY KEY(warehouse_id,sku)` vừa có `UNIQUE(sku)`, bản tin cho kho 2 có thể va vào ràng buộc không phù hợp, làm sai ý nghĩa định danh.

Trong hệ đa tenant, cặp `(tenant_id, external_id)` thường có vai trò tương tự.

## 20. Cập nhật có điều kiện trong nhánh UPDATE

MySQL không có `WHERE` riêng phía sau `ON DUPLICATE KEY UPDATE` để lọc hàng được phép cập nhật như một câu `UPDATE ... WHERE` thông thường. Nhưng có thể dùng biểu thức có điều kiện trong từng phép gán.

Ví dụ chỉ thay giá khi giá mới đã biết và không âm:

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
VALUES ('BK-01', 'Sổ tay A', 65.00, 10) AS incoming
ON DUPLICATE KEY UPDATE
    unit_price = CASE
        WHEN incoming.unit_price >= 0
        THEN incoming.unit_price
        ELSE unit_price
    END;

SELECT sku, unit_price
FROM products_288
WHERE sku = 'BK-01';

ROLLBACK;
```

Kết quả: `unit_price = 65`.

**Nhưng cần kiểm soát cả nhánh INSERT:** nếu nguồn mang giá âm cho SKU **chưa tồn tại**, nhánh INSERT có thể vẫn chèn giá âm vì điều kiện ở phần UPDATE không chạy. Chính sách dữ liệu đúng nên được bảo vệ bằng validation trước lệnh hoặc **CHECK constraint** thích hợp trong các phiên bản MySQL hỗ trợ thực thi CHECK (từ MySQL 8.0.16), ngoài các điều kiện trong nhánh UPDATE.

Để tránh dữ liệu không hợp lệ, không nên chỉ “chữa” nhánh xung đột và bỏ quên nhánh tạo mới.

## 21. ON DUPLICATE KEY UPDATE không giống REPLACE INTO

MySQL có lệnh `REPLACE`:

```sql
-- Cú pháp MySQL để minh họa; KHÔNG chạy thử trên dữ liệu thật.
REPLACE INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
VALUES ('BK-01', 'Sổ tay A', 55.00, 12);
```

Tên `REPLACE` có thể khiến người đọc tưởng đây là `UPDATE`. Nhưng về ngữ nghĩa, khi có xung đột khóa, `REPLACE` có thể **xóa hàng đang tồn tại rồi chèn hàng mới**. Điều này có thể:

- Làm mất những cột không truyền trong `REPLACE` vì hàng mới dùng giá trị mặc định.
- Tạo ID tự tăng mới.
- Tác động tới khóa ngoại, trigger và các hành vi liên quan `DELETE`/`INSERT`.
- Gây hậu quả khác hoàn toàn việc cập nhật một số cột tại chỗ.

Ngược lại, `INSERT ... ON DUPLICATE KEY UPDATE` giữ hàng đích và gán những cột được chỉ rõ theo cơ chế UPDATE khi xung đột. Nhưng nó vẫn có thể kích hoạt các trigger thích hợp và các cột tự động theo quy tắc MySQL.

**Không dùng `REPLACE INTO` như một cách viết ngắn tương đương upsert có UPDATE** khi bảng có quan hệ tham chiếu, audit, ID ổn định hoặc các cột không được truyền.

## 22. ON DUPLICATE KEY UPDATE khác INSERT IGNORE

`INSERT IGNORE` có thể bỏ qua hoặc hạ mức một số lỗi để xử lý tiếp theo quy tắc MySQL/SQL mode, trong đó có trường hợp trùng khóa. Nó **không phải** câu lệnh cập nhật hàng đã tồn tại theo dữ liệu mới.

Ví dụ ý nghĩa:

```sql
-- MySQL: hàng trùng SKU có thể bị bỏ qua thay vì đổi giá.
-- Không thực thi nếu mục tiêu là đồng bộ giá.
--
-- INSERT IGNORE INTO products_288
--     (sku, product_name, unit_price, stock_qty)
-- VALUES ('BK-01', 'Sổ tay A', 55.00, 12);
```

Với upsert:

```sql
INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
VALUES ('BK-01', 'Sổ tay A', 55.00, 12) AS incoming
ON DUPLICATE KEY UPDATE
    unit_price = incoming.unit_price;
```

hàng cũ có thể đổi giá.

Ngoài ra, phối hợp `INSERT IGNORE` với `ON DUPLICATE KEY UPDATE` và nhiều chỉ mục UNIQUE có thể biến một số lỗi thành cảnh báo theo ngữ nghĩa MySQL. Không nên thêm `IGNORE` chỉ để lệnh batch “không bị dừng”, vì thao tác có thể bỏ qua sự cố dữ liệu cần được điều tra.

### So sánh mục tiêu

| Cấu trúc | Khi khóa chưa tồn tại | Khi khóa đã tồn tại |
| --- | --- | --- |
| `INSERT` | Chèn | Lỗi trùng UNIQUE/PRIMARY |
| `INSERT IGNORE` | Thường chèn nếu hợp lệ | Có thể bỏ qua hoặc cảnh báo, không tự cập nhật theo yêu cầu |
| `INSERT ... ON DUPLICATE KEY UPDATE` | Chèn | Cập nhật cột được chỉ định |
| `REPLACE INTO` | Chèn | Có thể xóa hàng cũ và chèn hàng mới |
| `UPDATE ... WHERE key=...` | Không tạo hàng mới | Cập nhật hàng thỏa điều kiện |

Lựa chọn phụ thuộc ý nghĩa nghiệp vụ: **chỉ tạo mới**, **bỏ qua nếu đã có**, **cập nhật nếu đã có**, hay **thay toàn bộ bản ghi**.

## 23. Trigger và các hiệu ứng phụ

Một câu upsert có thể kích hoạt logic trigger gắn với bảng đích. Trong MySQL, các trigger liên quan tới INSERT và UPDATE có thể tham gia theo diễn biến của câu lệnh upsert, với quy tắc kích hoạt tùy nhánh và cách MySQL xử lý hàng đề xuất.

Vì vậy, khi bảng có trigger:

- Không suy đoán rằng “nhánh UPDATE chỉ chạy trigger UPDATE và hoàn toàn không đụng trigger INSERT” trong mọi giai đoạn.
- Kiểm tra trigger đang áp dụng trên bảng, đặc biệt nếu chúng ghi audit, phát sự kiện hoặc thay đổi giá trị trước khi kiểm tra khóa.
- Tránh xây logic idempotent dựa vào giả định trigger không bao giờ chạy khi dữ liệu không đổi.
- Không sử dụng affected rows làm số lượng “sự kiện nghiệp vụ” nếu trigger có thể tạo thêm tác dụng phụ.

Một câu upsert cũng có thể đụng `FOREIGN KEY`, `CHECK`, `NOT NULL` và các quy tắc DEFAULT/`ON UPDATE CURRENT_TIMESTAMP`. Nhánh UPDATE không miễn trừ việc kiểm tra tính hợp lệ của dữ liệu sau cập nhật.

Nếu hệ thống phát sự kiện ra ngoài database, cần một thiết kế giao dịch/audit phù hợp để không phát sự kiện trùng do retry hoặc trigger chạy trong những tình huống ngoài dự kiến.

## 24. Concurrency: hai người cùng upsert một khóa

Một ưu điểm của `INSERT ... ON DUPLICATE KEY UPDATE` là logic thử chèn rồi xử lý xung đột được thực hiện trong **một câu lệnh** dưới sự kiểm soát khóa/ràng buộc của storage engine. Nó giúp tránh cách kiểm tra tồn tại rồi chèn bằng hai statement không được đồng bộ.

Nhưng concurrency vẫn có các câu hỏi:

- Hai transaction cùng gửi giá mới khác nhau cho một SKU, **giá nào được chấp nhận sau cùng?**
- Một transaction thay thế số lượng tuyệt đối trong khi transaction khác cộng số lượng delta, kết quả phù hợp quy tắc nào?
- Hai batch cập nhật nhiều SKU theo thứ tự khác nhau có nguy cơ **deadlock** không?
- Khi DBMS báo deadlock hoặc lock wait timeout, ứng dụng có retry được không và **retry có an toàn không**?

InnoDB sử dụng cơ chế khóa để duy trì tính nhất quán của thao tác, nhưng **không tự quyết định bản tin nào "mới hơn" theo nghiệp vụ**.

### Ghi đè cuối cùng không phải luôn đúng

Giả sử:

```text
Nguồn B: version 20 → giá 100
Nguồn A: version 19 → giá 90
```

Nếu nguồn A đến sau và câu SQL luôn `unit_price = incoming.unit_price`, giá có thể lùi về 90. Câu lệnh vẫn hợp lệ về ràng buộc UNIQUE.

Với đồng bộ theo phiên bản, cần so sánh `source_version` như ở mục 14 hoặc xây dựng cơ chế phát hành sự kiện theo thứ tự được kiểm soát.

### Atomicity không đồng nghĩa exactly-once

Một statement upsert có thể được thực thi nguyên tử theo các quy tắc của InnoDB, nhưng nếu client mất kết nối sau khi gửi lệnh, nó có thể **không biết chắc server đã commit hay chưa**. Retry phép thay thế trạng thái và retry phép cộng dồn có hệ quả khác nhau.

Khi nghiệp vụ có yêu cầu “một event chỉ áp dụng một lần”, cần **event ID duy nhất** và cơ chế xác nhận xử lý trong transaction. Upsert không tự làm công việc đó chỉ vì đã dùng một statement.

### Deadlock, retry và thứ tự batch

Với batch nhiều khóa, hai transaction lấy khóa theo thứ tự khác nhau có thể tạo vòng chờ. Một biện pháp giảm rủi ro là chuẩn hóa thứ tự xử lý theo khóa nghiệp vụ; tuy nhiên **không bảo đảm loại hết deadlock**.

Ứng dụng cần phân biệt lỗi có thể retry, log đủ thông tin, giới hạn số lần retry và bảo đảm thao tác retry không nhân đôi hiệu ứng nghiệp vụ.

## 25. INSERT ... ON DUPLICATE KEY UPDATE và MERGE khác nhau ở đâu?

`MERGE` của SQL chuẩn và một số hệ quản trị cho phép diễn đạt nhiều nhánh: khi nguồn khớp đích thì UPDATE/DELETE, khi không khớp thì INSERT, đôi khi với các điều kiện nâng cao.

Còn MySQL `ON DUPLICATE KEY UPDATE` chủ yếu dựa trên **vi phạm PRIMARY/UNIQUE khi INSERT**, sau đó thực hiện UPDATE.

So sánh ý tưởng:

```text
MySQL:
  Thử INSERT
    ├── Không vi phạm UNIQUE → INSERT
    └── Vi phạm UNIQUE       → UPDATE

MERGE (khái quát):
  So khớp nguồn với đích theo điều kiện ON
    ├── MATCHED              → UPDATE/DELETE/...
    └── NOT MATCHED          → INSERT/...
```

Vì vậy không nên xem hai cấu trúc là đồng nhất:

- `MERGE` có thể so khớp theo **điều kiện ON được viết tường minh**, phụ thuộc DBMS.
- MySQL upsert không có một conflict target/ON join predicate tùy ý theo cách đó.
- `MERGE` có thể có nhiều nhánh và các yêu cầu về số nguồn khớp mỗi đích.
- MySQL upsert có thể kích hoạt vì bất kỳ chỉ mục UNIQUE, kể cả khi nó không phải khóa mà ứng dụng định dùng.

Ở một số sản phẩm, `MERGE` hỗ trợ xử lý các trường hợp phức tạp nhưng cũng có cảnh báo riêng về nguồn nhiều hàng; không tự động an toàn hơn nếu định danh và cardinality sai.

## 26. PostgreSQL ON CONFLICT: khác biệt quan trọng

PostgreSQL có cú pháp khác:

```sql
-- PostgreSQL, KHÔNG chạy trên MySQL
INSERT INTO products (sku, product_name, unit_price)
VALUES ('BK-01', 'Sổ tay A', 55.00)
ON CONFLICT (sku) DO UPDATE
SET unit_price = EXCLUDED.unit_price;
```

Khác biệt:

1. `ON CONFLICT (sku)` cho phép chỉ định **conflict target** rõ ràng theo `sku` (hoặc theo một unique constraint/index phù hợp).
2. `EXCLUDED.unit_price` là giá trị đề xuất chèn trong cú pháp PostgreSQL.
3. PostgreSQL hỗ trợ `DO NOTHING` và `DO UPDATE` với các đặc điểm và điều kiện riêng.
4. Một số dạng `ON CONFLICT DO UPDATE ... WHERE ...` cho phép quyết định có thực hiện cập nhật dựa trên bản ghi mới/cũ.

Không sao chép:

```sql
ON DUPLICATE KEY UPDATE ...
```

vào PostgreSQL, và không dùng:

```sql
ON CONFLICT (sku) DO UPDATE ...
```

trong MySQL.

### SQLite và MariaDB

- **SQLite** có cú pháp UPSERT với `ON CONFLICT ... DO UPDATE` theo quy tắc SQLite, không đồng nhất với MySQL. Kiểu dữ liệu, khóa UNIQUE và cú pháp tham chiếu giá trị mới có khác biệt.
- **MariaDB** hỗ trợ `INSERT ... ON DUPLICATE KEY UPDATE` nhưng có chi tiết phiên bản, cú pháp alias và cách dùng `VALUES()` khác MySQL hiện đại. Cần đọc đúng tài liệu nhánh MariaDB đang triển khai.

Nhìn cùng tên “upsert” không đủ để khẳng định có thể copy/paste cú pháp hoặc giữ nguyên hành vi xung đột.

## 27. So sánh trong Java/JDBC và hệ thống ứng dụng

Khi thực thi từ Java, câu SQL thường được gọi qua `PreparedStatement`:

```java
String sql = """
    INSERT INTO products_288
        (sku, product_name, unit_price, stock_qty)
    VALUES (?, ?, ?, ?) AS incoming
    ON DUPLICATE KEY UPDATE
        product_name = incoming.product_name,
        unit_price   = incoming.unit_price,
        stock_qty    = incoming.stock_qty
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, sku);
    ps.setString(2, productName);
    ps.setBigDecimal(3, unitPrice);
    ps.setInt(4, stockQty);

    int affectedRows = ps.executeUpdate();
    // affectedRows không mặc nhiên là "số sản phẩm đã đổi".
}
```

Ví dụ Java này chỉ minh họa cách **parameterize giá trị**, chưa bao gồm mở kết nối, chuẩn bị transaction, validation và xử lý lỗi. Nó giả định MySQL phiên bản hỗ trợ `AS incoming`.

### Những việc tầng ứng dụng vẫn phải chịu trách nhiệm

- Kiểm tra `sku` hợp lệ và không rỗng theo quy tắc riêng.
- Kiểm tra giá không âm và số lượng tồn hợp lệ.
- Xác định bản tin là trạng thái tuyệt đối hay biến động.
- Xử lý retry khi deadlock/timeout theo chính sách có idempotency.
- Không dựa vào `affectedRows == 1` để khẳng định luôn là INSERT, vì cấu hình `CLIENT_FOUND_ROWS` và trường hợp no-op.
- Nếu cần biết ID của bản ghi, dùng cơ chế JDBC/MySQL phù hợp thay vì suy từ thứ tự `AUTO_INCREMENT`.
- Quản lý kết nối và transaction đúng, đặc biệt khi upsert nhiều bảng phải cùng commit hoặc rollback.

Prepared statement bảo vệ **các giá trị tham số**, không cho phép dùng placeholder `?` để thay trực tiếp tên bảng hoặc tên cột; đó là vấn đề identifier và schema.

## 28. Xử lý lỗi và tránh che lỗi dữ liệu

Không phải lỗi nào cũng nên được chuyển thành upsert. `ON DUPLICATE KEY UPDATE` chỉ mô tả cách xử lý **xung đột khóa**; các lỗi khác vẫn có thể xảy ra:

- `NOT NULL`: không thể gán giá trị thiếu vào cột bắt buộc.
- `CHECK`: giá hoặc tồn kho vi phạm quy tắc (trong phiên bản MySQL thực thi CHECK).
- `FOREIGN KEY`: tham chiếu đối tượng không tồn tại.
- Chuyển kiểu hoặc tràn miền số.
- Trùng UNIQUE thứ hai khi nhánh UPDATE thay đổi dữ liệu.
- Deadlock hoặc lock wait timeout.
- Không đủ quyền `INSERT`/`UPDATE` hoặc quyền trên cột liên quan.

Khi batch gặp lỗi, không nên mặc định “các hàng trước lỗi chắc chắn đã commit” hoặc “mọi hàng chắc chắn rollback” mà không xét storage engine, transaction, cách thực thi statement và chính sách xử lý lỗi. Với bảng InnoDB trong transaction, cơ chế rollback là nền tảng để xử lý an toàn, nhưng ứng dụng vẫn phải quản lý trạng thái transaction sau lỗi.

### Mẫu transaction khi có nhiều thao tác liên quan

```sql
START TRANSACTION;

-- 1. Có thể ghi nhận event_id vào bảng dedup (nếu thiết kế cần).
-- 2. Upsert sản phẩm hoặc tồn kho.
-- 3. Ghi audit hoặc cập nhật bảng liên quan trong cùng transaction.

-- COMMIT;   -- chỉ khi mọi bước hợp lệ
ROLLBACK;    -- ví dụ thực hành không giữ thay đổi
```

Khi quy trình liên quan nhiều nguồn dữ liệu ngoài MySQL, commit một transaction database **không tự làm thao tác HTTP hoặc message broker thành nguyên tử**. Một hệ thống phức tạp có thể dùng outbox pattern và cơ chế tiêu thụ idempotent, nhưng đó là chủ đề kiến trúc bổ sung.

## 29. Một số bẫy về kiểu dữ liệu và implicit conversion

Một UNIQUE key có thể dùng chuỗi, số hoặc nhiều cột. MySQL có cơ chế **chuyển kiểu ngầm** và collation tùy SQL mode.

Ví dụ giả định một cột mã sản phẩm kiểu số nhưng nguồn gửi chuỗi:

```text
nguồn: '00123'
cột:   INT
```

Nếu đưa vào cột `INT`, mã sẽ mất các số 0 đầu, và hai mã `'00123'` và `'123'` có thể biến thành cùng giá trị. Đối với mã định danh có số 0 đầu có ý nghĩa, dùng `VARCHAR`/`CHAR` với collation thích hợp thường đúng hơn.

Với tiền, ưu tiên `DECIMAL(p,s)` thay vì dùng số thực nhị phân nếu yêu cầu chính xác theo đơn vị nhỏ nhất của tiền tệ. Không truyền tiền bằng `double` rồi kỳ vọng mọi giá trị thập phân được biểu diễn chính xác.

### Tên khóa và các giá trị rỗng

Một SKU chuỗi rỗng `''` không giống `NULL` trong MySQL. Nếu cột `sku VARCHAR(...) NOT NULL UNIQUE`, chuỗi rỗng **không vi phạm NOT NULL**, và có thể được chèn như một SKU duy nhất nếu không có quy tắc cấm nó.

Nên áp điều kiện kiểm tra chuỗi trắng/rỗng ở tầng dữ liệu hoặc validation phù hợp; không dựa vào `NOT NULL` để tự loại mọi mã không hợp lệ.

## 30. Hiệu năng và chỉ mục cho upsert

Đối với MySQL/InnoDB, các thao tác chèn và kiểm tra xung đột phụ thuộc vào cấu trúc chỉ mục, phân bố khóa, contention và số lượng hàng.

Một số nguyên tắc:

- Đặt `PRIMARY KEY`/`UNIQUE` **đúng với khóa nghiệp vụ**, không thêm UNIQUE giả chỉ để câu upsert kích hoạt.
- Mỗi chỉ mục phụ là chi phí ghi và bảo trì; quá nhiều UNIQUE có thể làm thêm kiểm tra xung đột và tạo nhiều điểm mâu thuẫn.
- Batch có thể giảm round trip so với gửi từng câu SQL, nhưng batch quá lớn làm transaction dài và chiếm khóa nhiều hơn.
- Các transaction cập nhật các khóa phổ biến có thể bị contention.
- Khi source có nhiều bản cùng khóa, **chuẩn hóa trước** thường giảm công việc cập nhật lặp không cần thiết.
- Upsert no-op vẫn có chi phí tìm khóa và đánh giá nhánh xử lý.
- Hành vi `AUTO_INCREMENT`, trigger và secondary indexes ảnh hưởng hiệu năng và log.

Không có một kích thước batch “tối ưu cho mọi hệ thống”. Hãy đo throughput, latency, số deadlock/timeout, số hàng thực sự thay đổi và tải trên bảng nguồn/đích bằng dữ liệu đại diện.

**Đúng ngữ nghĩa trước, tối ưu sau.** Một batch rất nhanh nhưng cập nhật sai giá do trùng UNIQUE không phải một tối ưu thành công.

## 31. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Chèn thêm cùng SKU thay vì UPDATE | `sku` không có `UNIQUE` hoặc khác collation/chuẩn hóa | Định nghĩa đúng khóa nghiệp vụ |
| Câu upsert chạy nhưng cập nhật sản phẩm khác | Có nhiều UNIQUE và một đề xuất va vào nhiều hàng | Loại mâu thuẫn định danh; không dựa vào việc MySQL tự chọn |
| Giá không đổi dù truyền giá mới | Nhánh UPDATE không gán `unit_price` | Kiểm tra danh sách phép gán |
| Gửi stock=12 nhưng kho thành 22 | Dùng `old + incoming` thay vì thay thế | Xác định trạng thái tuyệt đối hay delta |
| Retry làm bộ đếm tăng gấp đôi | Phép cộng không idempotent | Dùng event ID và dedup trong transaction |
| Giá bị lùi về bản cũ | Nhận bản tin lệch thứ tự, không kiểm tra version | Dùng version/source sequence có quy tắc |
| MySQL báo cảnh báo `VALUES()` deprecated | Dùng cú pháp tham chiếu cũ | Dùng row alias trên bản MySQL hỗ trợ |
| `VALUES (...) AS incoming` lỗi trên server cũ | Phiên bản chưa hỗ trợ row alias | Chọn cú pháp tương thích phiên bản |
| `INSERT ... SELECT ... ON DUPLICATE` lỗi cú pháp | Parser nhập nhằng `ON` | Thêm `WHERE TRUE` hoặc cấu trúc SELECT rõ ràng |
| Một batch nhiều nguồn cùng SKU có kết quả khó hiểu | Dữ liệu staging chưa chọn một bản mỗi khóa | Dedup/ranking với quy tắc phá hòa |
| Affected rows = 2 dù chỉ một SKU đổi | MySQL tính UPDATE có thay đổi là 2 | Không coi affected rows là số SKU |
| Affected rows = 0 khi SKU tồn tại | Trùng khóa nhưng các giá trị không đổi | Xem no-op và `CLIENT_FOUND_ROWS` |
| ID AUTO_INCREMENT có khoảng trống | Phân bổ ID, duplicate, rollback, concurrency | Không kỳ vọng ID liên tiếp |
| Cập nhật mô tả thành NULL ngoài ý muốn | `description = incoming.description` khi nguồn thiếu | Xác định chính sách cập nhật một phần |
| Không cập nhật khi `code = NULL` | UNIQUE nullable có thể chứa nhiều NULL | Bảo đảm mã bắt buộc hoặc tách luồng thiếu mã |
| `REPLACE INTO` làm mất dữ liệu phụ | REPLACE có thể xóa/chèn thay vì UPDATE | Dùng upsert đúng mục tiêu |
| `INSERT IGNORE` bỏ qua thay đổi | IGNORE không đồng nghĩa UPDATE | Chọn ON DUPLICATE nếu thật sự cần cập nhật |
| Hai tenant cùng SKU bị đụng nhau | Thiết kế `UNIQUE(sku)` thay vì `UNIQUE(tenant_id,sku)` | Sửa khóa nghiệp vụ |
| Bảng có trigger phát audit ngoài ý muốn | Tác dụng phụ của nhánh insert/update | Kiểm tra trigger và idempotency |
| Tốc độ giảm khi import nhiều | Chỉ mục, batch dài, contention, trigger | Đo và tối ưu sau khi đúng logic |

## 32. Bài tập thực hành

Các bài sau dùng các bảng tạm `products_288`, `daily_counters_288`, `warehouse_stock_288` và `catalog_feed_288` đã tạo trong bài. Nếu chỉ mới đọc một phần, hãy tạo bảng cần dùng theo đúng mục tương ứng.

Hãy **dự đoán kết quả trước khi chạy**. Với bài có thao tác ghi, chạy trong transaction rồi `ROLLBACK` để các bài độc lập.

### Bài 1. Insert hay update?

`products_288` đã có SKU `BK-01`, `PEN-02`, `BAG-03`. Một upsert gửi `('MUG-04', 'Cốc gốm', 80.00, 6)`. Nhánh nào được dùng? Bảng sẽ có bao nhiêu sản phẩm trước khi rollback?

### Bài 2. Trùng SKU

Gửi `BK-01` với giá 55 và stock 12, dùng alias `AS incoming`, cập nhật cả giá và số lượng bằng giá trị đề xuất. Giá và số lượng mới là gì?

### Bài 3. Không truyền mô tả trong phần UPDATE

Một upsert cho `BK-01` có `description='Bản mới'` trong `VALUES` nhưng phần UPDATE chỉ gán `unit_price`. Mô tả cũ sẽ được giữ hay thay?

### Bài 4. Kho tuyệt đối và delta

Tồn `BK-01` ban đầu là 10. Nếu nguồn gửi số 7, so sánh kết quả của:

- `stock_qty = incoming.stock_qty`.
- `stock_qty = stock_qty + incoming.stock_qty`.

Khi bản tin được gửi lại, điều gì xảy ra?

### Bài 5. Cú pháp tham chiếu giá trị mới

Viết lại `unit_price = VALUES(unit_price)` thành cú pháp alias được khuyến nghị cho MySQL hiện đại. Phiên bản nào cần chú ý?

### Bài 6. Affected rows

Dự đoán affected rows **thông thường** cho:

- Chèn SKU mới.
- Cập nhật một SKU đã có với giá khác.
- Cập nhật SKU đã có nhưng mọi giá trị gán không đổi.

Giải thích tại sao không thể coi con số đó là số hàng vật lý được tạo hoặc sửa.

### Bài 7. Nhiều UNIQUE

Bảng có `UNIQUE(email)` và `UNIQUE(username)`. Dữ liệu đề xuất trùng email của A và username của B. Vì sao `ON DUPLICATE KEY UPDATE` không phải một thuật toán hợp lệ để “hợp nhất A và B”?

### Bài 8. Batch nhiều SKU

Viết một câu `INSERT ... VALUES (...), (...), (...) AS incoming ON DUPLICATE KEY UPDATE` cập nhật `BK-01`, `PEN-02` và thêm `MUG-04`. Bảo đảm `BAG-03` không bị thay đổi.

### Bài 9. Chọn giá mới nhất từ staging

`catalog_feed_288` chứa nhiều bản cho `BK-01`, trong đó hai bản có cùng `source_time`. Viết `ROW_NUMBER() OVER (PARTITION BY sku ORDER BY source_time DESC, feed_id DESC)` và chỉ lấy `rn=1`.

### Bài 10. INSERT ... SELECT và parser

Viết upsert từ `incoming_prices_288` để cập nhật `unit_price` cho các SKU đã có. Vì sao `WHERE TRUE` có thể hữu ích khi đặt trước `ON DUPLICATE KEY UPDATE`?

### Bài 11. NULL và cập nhật một phần

`BK-01` có `description='Bản đầu'`. Nguồn gửi `description=NULL`. Viết hai phép gán:

- Giữ mô tả cũ khi nguồn là `NULL`.
- Xóa mô tả cũ khi nguồn là `NULL`.

### Bài 12. Khóa ghép theo kho

Tạo hai hàng `(warehouse_id=1,sku='BK-01')` và `(warehouse_id=2,sku='BK-01')`. Upsert `(1,'BK-01',15)` có ảnh hưởng kho 2 không? Vì sao?

### Bài 13. Upsert counter và retry

Gửi hai lần cùng câu tăng `hit_count` thêm 1 cho cùng `counter_key`. Kết quả gì? Nếu đó chỉ là **một event bị retry**, hệ thống cần thêm gì?

### Bài 14. Không ghi đè version mới bằng version cũ

Một SKU đang có `source_version=8` và giá 58. Nguồn gửi version 7, giá 54. Viết `IF`/`GREATEST` trong nhánh UPDATE sao cho bản cũ không làm lùi dữ liệu.

### Bài 15. So sánh REPLACE, IGNORE và ON DUPLICATE

Cùng một SKU đã tồn tại, giải thích khác nhau giữa `INSERT IGNORE`, `REPLACE INTO` và `INSERT ... ON DUPLICATE KEY UPDATE`. Trường hợp nào có nguy cơ xóa rồi chèn lại hàng?

### Bài 16. Thiết kế đồng bộ đa tenant

Một hệ thống có `tenant_id` và `sku`, mỗi tenant được phép có cùng SKU. Nên đặt ràng buộc UNIQUE nào? Nếu chỉ có UNIQUE(sku), tình huống nào sai?

### Bài 17. Câu hỏi kiến trúc

Một API nhận trạng thái sản phẩm mới, trong khi một queue khác nhận sự kiện nhập kho. Phần nào dùng phép **thay thế**, phần nào dùng **cộng dồn**? Vì sao cả hai có thể cần version/event ID khác nhau?

## 33. Gợi ý lời giải

### Bài 1

`MUG-04` chưa có nên dùng nhánh **INSERT**. Trong transaction có bốn sản phẩm: `BK-01`, `PEN-02`, `BAG-03` và `MUG-04`. Sau `ROLLBACK` quay về ba sản phẩm ban đầu.

### Bài 2

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
VALUES ('BK-01', 'Sổ tay A', 55.00, 12) AS incoming
ON DUPLICATE KEY UPDATE
    unit_price = incoming.unit_price,
    stock_qty  = incoming.stock_qty;

SELECT sku, unit_price, stock_qty
FROM products_288
WHERE sku = 'BK-01';

ROLLBACK;
```

Kết quả là **55.00** và **12**; không cộng stock vào số cũ.

### Bài 3

Ở nhánh UPDATE, `description` **giữ 'Bản đầu'** nếu không có phép gán cho nó. Cột xuất hiện trong `VALUES` nhưng không có trong `ON DUPLICATE KEY UPDATE` không tự được cập nhật khi xung đột.

### Bài 4

- Thay thế: `stock_qty = 7`; retry cùng dữ liệu vẫn 7.
- Cộng dồn: `stock_qty = 10 + 7 = 17`; retry thêm lần nữa có thể thành **24**.

Nếu là delta, cần chống xử lý trùng sự kiện.

### Bài 5

```sql
INSERT INTO products_288 (
    sku, product_name, unit_price
)
VALUES ('BK-01', 'Sổ tay A', 55.00) AS incoming
ON DUPLICATE KEY UPDATE
    unit_price = incoming.unit_price;
```

Row alias sau `VALUES` cần MySQL phiên bản hỗ trợ, từ **MySQL 8.0.19**. Hàm `VALUES(column)` trong nhánh UPDATE là kiểu cũ bị deprecated trong MySQL từ **8.0.20**.

### Bài 6

Thông thường **1 / 2 / 0** lần lượt cho insert mới, update có thay đổi, update không làm thay đổi giá trị. Với `CLIENT_FOUND_ROWS`, no-op có thể được tính là 1. Không dùng affected rows để suy ra chính xác loại biến đổi của mọi hàng trong batch.

### Bài 7

Một đề xuất trùng `email` của A và `username` của B có thể xác định **hai hàng đích khác nhau**. Không có quy tắc tự động chọn danh tính đúng và ghép hai khách. Cần xác minh nguồn, quy tắc thống nhất danh tính và xử lý mâu thuẫn trước khi upsert.

### Bài 8

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
VALUES
    ('BK-01',  'Sổ tay A mới', 55.00, 12),
    ('PEN-02', 'Bút xanh mới',   6.00, 80),
    ('MUG-04', 'Cốc gốm',       80.00,  6)
AS incoming
ON DUPLICATE KEY UPDATE
    product_name = incoming.product_name,
    unit_price = incoming.unit_price,
    stock_qty = incoming.stock_qty;

ROLLBACK;
```

`BAG-03` không nằm trong batch nên không được cập nhật.

### Bài 9

```sql
WITH ranked AS (
    SELECT
        feed_id, sku, product_name, new_price, source_time,
        ROW_NUMBER() OVER (
            PARTITION BY sku
            ORDER BY source_time DESC, feed_id DESC
        ) AS rn
    FROM catalog_feed_288
)
SELECT sku, feed_id, product_name, new_price
FROM ranked
WHERE rn = 1
ORDER BY sku;
```

Kết quả `BK-01→feed_id 13` và `PEN-02→feed_id 12`. `feed_id DESC` phá hòa ở thời điểm bằng nhau.

### Bài 10

```sql
START TRANSACTION;

INSERT INTO products_288 (
    sku, product_name, unit_price, stock_qty
)
SELECT
    src.sku,
    CONCAT('Sản phẩm ', src.sku),
    src.new_price,
    0
FROM (
    SELECT sku, new_price
    FROM incoming_prices_288
) AS src
WHERE TRUE
ON DUPLICATE KEY UPDATE
    unit_price = src.new_price;

ROLLBACK;
```

`WHERE TRUE` giúp tránh nhập nhằng cú pháp `ON` trong `INSERT ... SELECT ... ON DUPLICATE KEY UPDATE` với một số cách phân tích cú pháp của MySQL. Tập nguồn cần được chuẩn bị phù hợp trước khi upsert.

### Bài 11

Giữ khi nguồn thiếu:

```sql
description = COALESCE(incoming.description, description)
```

Xóa theo `NULL` tường minh:

```sql
description = incoming.description
```

Sự lựa chọn phụ thuộc cách API định nghĩa "không cung cấp mô tả" và "xóa mô tả".

### Bài 12

```sql
PRIMARY KEY (warehouse_id, sku)
```

bảo đảm `(1,'BK-01')` và `(2,'BK-01')` là hai bản ghi khác nhau. Upsert kho 1 không đụng kho 2 nếu không có chỉ mục UNIQUE khác làm xung đột ngoài ý muốn.

### Bài 13

Gửi hai lần `hit_count = hit_count + 1` cho cùng khóa cho kết quả **2**. Nếu là một event bị gửi lại, cần mã `event_id` duy nhất và một cơ chế lưu dấu/transaction chỉ áp dụng biến động một lần.

### Bài 14

```sql
INSERT INTO versioned_prices_288 (
    sku, unit_price, source_version
)
VALUES ('BK-01', 54.00, 7) AS incoming
ON DUPLICATE KEY UPDATE
    unit_price = IF(
        incoming.source_version > source_version,
        incoming.unit_price,
        unit_price
    ),
    source_version = GREATEST(
        source_version,
        incoming.source_version
    );
```

Bản ghi đang có version 8/giá 58 được giữ. Ví dụ cần chạy trong transaction/rollback nếu muốn không thay đổi bảng thực hành.

### Bài 15

- `INSERT IGNORE`: thường bỏ qua khóa trùng hoặc hạ lỗi theo quy tắc MySQL, không cập nhật giá cũ.
- `REPLACE INTO`: có thể **xóa hàng cũ rồi chèn hàng mới**, ảnh hưởng ID, khóa ngoại, trigger và giá trị mặc định.
- `ON DUPLICATE KEY UPDATE`: cập nhật các cột được chỉ định trên hàng đang tồn tại khi xung đột.

Không xem REPLACE là đồng nghĩa với UPDATE.

### Bài 16

Ràng buộc đúng là:

```sql
UNIQUE KEY uq_tenant_sku (tenant_id, sku)
```

hoặc dùng cặp này làm `PRIMARY KEY` nếu phù hợp mô hình. `UNIQUE(sku)` riêng sẽ cấm hoặc gây xung đột giữa các tenant có cùng SKU, trái quy tắc dữ liệu.

### Bài 17

API gửi **trạng thái sản phẩm** có thể dùng:

```sql
unit_price = incoming.unit_price,
stock_qty = incoming.stock_qty
```

khi các giá trị là snapshot đầy đủ và có version để tránh bản cũ ghi đè.

Queue gửi **sự kiện nhập thêm kho** có thể dùng:

```sql
stock_qty = stock_qty + incoming.stock_qty
```

nhưng phải chống xử lý một sự kiện hai lần, thường dựa trên event ID duy nhất cùng transaction. Version và event ID phục vụ các bài toán khác nhau: **thứ tự trạng thái** và **danh tính lần tác động**.

## 34. Quy trình tư duy trước khi triển khai MySQL upsert

Trước khi đặt câu `INSERT ... ON DUPLICATE KEY UPDATE` vào production, hãy lần lượt trả lời:

1. **Định danh nghiệp vụ là gì?** SKU, external ID, email hay một cặp `(tenant_id, sku)`?
2. **Cột đó có `PRIMARY KEY`/`UNIQUE` thực sự không?** Nếu không, bản sao có thể được chèn thay vì cập nhật.
3. **Bảng có những UNIQUE nào khác?** Một bản tin có thể va vào những hàng khác nhau qua các UNIQUE đó không?
4. **Nguồn gửi trạng thái hay biến động?** Dùng `= incoming.value` hay `= old + incoming.value` là hai hợp đồng khác nhau.
5. **Có thể gửi lại cùng một bản tin không?** Nếu có, thao tác có idempotent không; có cần event ID?
6. **Bản tin có version hoặc timestamp nguồn không?** Có cần ngăn bản cũ ghi đè bản mới?
7. **NULL nghĩa là gì?** Không cung cấp trường, dữ liệu thiếu, hay lệnh xóa giá trị cũ?
8. **Có batch nhiều hàng cùng khóa không?** Nếu có, chọn một bản theo quy tắc hay từ chối dữ liệu chưa hợp lệ.
9. **MySQL phiên bản nào?** Cú pháp row alias sau `VALUES` và trạng thái `VALUES(column)` phụ thuộc phiên bản.
10. **Số hàng bị ảnh hưởng có được dùng cho nghiệp vụ không?** Đừng hiểu 2 affected rows là hai sản phẩm.
11. **Có AUTO_INCREMENT, trigger, foreign key hay CHECK không?** Cần dự đoán các tác dụng phụ và lỗi.
12. **Có yêu cầu chạy cùng transaction với bảng khác không?** Upsert một bảng không làm toàn bộ quy trình đa bước nguyên tử.
13. **Concurrency và retry được xử lý thế nào?** Phải có chiến lược cho deadlock, timeout và kết quả chưa chắc chắn.
14. **Có cần kiểm toán không?** Lưu ID nguồn, version, thời điểm, tác nhân và giá trị trước/sau khi nghiệp vụ yêu cầu.
15. **Có thực sự cần một bảng rộng với trạng thái hiện tại không?** Với lịch sử, nên giữ thêm bảng sự kiện/phiên bản thay vì chỉ liên tục ghi đè bản mới nhất.

### Kết luận

**`INSERT ... ON DUPLICATE KEY UPDATE` là cơ chế upsert dựa trên vi phạm khóa chính hoặc chỉ mục duy nhất của MySQL.** Nó giúp gộp hai trường hợp “chưa có thì chèn, đã có thì cập nhật” trong một câu lệnh, nhưng không thay thế thiết kế khóa nghiệp vụ, quy tắc chọn phiên bản, xử lý `NULL` hay chống retry.

Để sử dụng an toàn, hãy định nghĩa đúng `PRIMARY KEY`/`UNIQUE`, biết rõ **giá trị mới là trạng thái hay biến động**, ưu tiên tham chiếu row alias trong MySQL hiện đại, chuẩn hóa tập nguồn nhiều phiên bản và không dựa vào affected rows hoặc thứ tự ngầm để suy luận kết quả. Với yêu cầu đồng bộ có tính nhất quán cao, cần kết hợp upsert với **ràng buộc dữ liệu, transaction, version/event ID và chiến lược xử lý đồng thời**.
