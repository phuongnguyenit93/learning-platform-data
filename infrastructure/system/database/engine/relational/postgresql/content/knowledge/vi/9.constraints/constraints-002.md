# CHECK và giới hạn kiểm tra tính hợp lệ trong PostgreSQL

Một ứng dụng nhận dữ liệu từ API, file CSV, biểu mẫu quản trị hoặc một dịch vụ khác. Dù ứng dụng đã kiểm tra dữ liệu đầu vào, database vẫn cần bảo vệ các điều kiện cốt lõi của dữ liệu: giá không âm, số lượng lớn hơn 0, ngày kết thúc sau ngày bắt đầu, trạng thái nằm trong danh sách hợp lệ, hay số tiền giảm giá không vượt quá giá gốc.

PostgreSQL cung cấp **ràng buộc `CHECK`** để diễn tả những điều kiện như vậy ngay trong cấu trúc bảng. Khi một thao tác `INSERT` hoặc `UPDATE` tạo ra hàng không đạt điều kiện, PostgreSQL từ chối thay đổi đó. Đây là lớp bảo vệ hữu ích vì nó áp dụng cho mọi đường ghi phù hợp vào bảng — từ ứng dụng, script SQL, công cụ quản trị cho tới nhiều quy trình import.

Tuy nhiên, `CHECK` có **giới hạn rõ ràng**: nó chủ yếu kiểm tra biểu thức trên dữ liệu của **một hàng**, không phải một truy vấn tùy ý qua nhiều hàng/bảng; biểu thức trả về `NULL` được xem là không vi phạm; và PostgreSQL không liên tục kiểm tra lại tất cả hàng chỉ vì thời gian trôi hoặc một hàm đổi hành vi.

Bài học này giải thích cách khai báo `CHECK`, logic ba giá trị của SQL, ràng buộc nhiều cột, giới hạn kiểm tra dữ liệu, quy trình áp dụng lên bảng đang có dữ liệu và cách kết hợp `CHECK` với các cơ chế toàn vẹn khác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Viết `CHECK` ở cấp cột hoặc cấp bảng và đặt tên constraint rõ nghĩa.
- Hiểu PostgreSQL coi kết quả **`TRUE` và `NULL`** là thỏa `CHECK`, còn `FALSE` làm thao tác bị từ chối.
- Kết hợp `CHECK` với `NOT NULL` để chặn dữ liệu thiếu, tránh hiểu sai logic ba giá trị.
- Mô tả các biểu thức hợp lệ cho miền số, tập giá trị, chuỗi, thời gian và quan hệ giữa nhiều cột của cùng hàng.
- Đọc lỗi `check_violation` với SQLSTATE `23514` và phân biệt với các lỗi constraint khác.
- Thêm constraint cho bảng có dữ liệu cũ bằng `NOT VALID`, sửa dữ liệu và `VALIDATE CONSTRAINT`.
- Giải thích vì sao `CHECK` không phù hợp để kiểm tra duy nhất, khóa ngoại, số lượng hàng toàn bảng hay điều kiện giữa hai giao dịch.
- Hiểu yêu cầu ổn định của biểu thức `CHECK` và những rủi ro khi tham chiếu thời gian hiện tại hoặc hàm thay đổi hành vi.
- Phối hợp constraint, transaction, locking, isolation level và kiểm tra ứng dụng để giữ dữ liệu đúng.
- Tự thiết kế và chạy một bài thực hành PostgreSQL với các điều kiện hợp lệ/không hợp lệ.

Ví dụ SQL dành cho PostgreSQL hiện đại. Những lệnh tạo/xóa bảng chỉ nên chạy trong **database thử nghiệm riêng**, tuyệt đối không chép nguyên lên production.

---

## 2. CHECK nằm ở đâu trong hệ thống ràng buộc?

Một bảng PostgreSQL có thể có nhiều loại constraint:

| Loại | Mục tiêu chính | Ví dụ |
| --- | --- | --- |
| `NOT NULL` | Một cột không được có giá trị `NULL` | Tên sản phẩm bắt buộc |
| `CHECK` | Biểu thức kiểm tra phải không trả `FALSE` | `price >= 0` |
| `UNIQUE` | Không có những giá trị hoặc tổ hợp giá trị trùng nhau theo quy tắc unique | Mã SKU riêng |
| `PRIMARY KEY` | Định danh hàng, vừa duy nhất vừa không NULL | `product_id` |
| `FOREIGN KEY` | Giá trị tham chiếu phải phù hợp quan hệ tới bảng khác | `customer_id` tồn tại |
| `EXCLUDE` | Ngăn hai hàng có tổ hợp quan hệ xung đột theo toán tử đã định | Không trùng lịch đặt phòng |

**`CHECK` phù hợp cho những bất biến của từng hàng**: giá không âm, mức giảm giá nằm trong khoảng cho phép, ngày bắt đầu trước ngày kết thúc.

**`UNIQUE`, `FOREIGN KEY` và `EXCLUDE`** phù hợp hơn với những quy tắc phụ thuộc dữ liệu ở hàng khác hoặc bảng khác. Những quy tắc xuyên nhiều dòng hoặc giai đoạn nghiệp vụ còn có thể cần transaction, khóa, trigger hay xử lý ở tầng ứng dụng.

Sơ đồ tổng quát:

```text
Ứng dụng / psql / công cụ import
                |
                | INSERT hoặc UPDATE
                v
       PostgreSQL table
    +----------------------+
    | Kiểu dữ liệu         |
    | NOT NULL             |
    | CHECK                |
    | UNIQUE / PRIMARY KEY |
    | FOREIGN KEY          |
    | Quy tắc khác         |
    +----------------------+
                |
         +------+------+
         |             |
       Hợp lệ       Vi phạm
         |             |
         v             v
   Tiếp tục xử lý   Lỗi SQL
   trong transaction  không ghi
                |
         COMMIT nếu
       toàn bộ hợp lệ
```

Một constraint không tự commit dữ liệu. Nó chỉ là một phần trong quá trình kiểm tra câu SQL của transaction đang chạy.

---

## 3. Cú pháp CHECK cơ bản

Dạng khai báo ngay trong cột:

```sql
CREATE TABLE example_products (
    product_id BIGINT PRIMARY KEY,
    price NUMERIC(12,2) CHECK (price >= 0)
);
```

Dạng đặt tên constraint:

```sql
CREATE TABLE example_products_named (
    product_id BIGINT PRIMARY KEY,
    price NUMERIC(12,2)
        CONSTRAINT example_products_named_price_nonnegative
        CHECK (price >= 0)
);
```

Dạng constraint ở cấp bảng:

```sql
CREATE TABLE example_discounts (
    product_id BIGINT PRIMARY KEY,
    list_price NUMERIC(12,2) NOT NULL,
    sale_price NUMERIC(12,2) NOT NULL,
    CONSTRAINT example_discounts_prices_valid
        CHECK (
            list_price >= 0
            AND sale_price >= 0
            AND sale_price <= list_price
        )
);
```

Cả hai vị trí đều có thể tạo `CHECK`, nhưng **constraint cấp bảng** thường dễ đọc hơn khi cần so sánh nhiều cột.

### 3.1. Nên đặt tên constraint

Nếu không khai báo tên, PostgreSQL tạo tên mặc định. Điều đó hoạt động, nhưng tên tường minh giúp:

- Biết điều kiện nào bị vi phạm khi đọc log.
- Xử lý lỗi có cấu trúc ở backend.
- Thực hiện `ALTER TABLE ... DROP CONSTRAINT` hoặc `VALIDATE CONSTRAINT` rõ ràng.
- Phân biệt nhiều điều kiện trên cùng một bảng.
- Viết migration nhất quán hơn.

Ví dụ tên dễ hiểu:

```text
products_price_nonnegative
products_discount_within_price
bookings_time_order
payments_amount_positive
orders_status_allowed
```

Không dùng tên constraint thay cho tài liệu nghiệp vụ; tên chỉ là đầu mối ngắn gọn, còn quy tắc đầy đủ vẫn cần được mô tả.

### 3.2. CHECK kiểm tra biểu thức nào?

Bên trong `CHECK (...)` thường sử dụng các biểu thức SQL:

```sql
CHECK (quantity > 0)
CHECK (price >= 0 AND price <= 1000000000)
CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED'))
CHECK (length(code) BETWEEN 3 AND 20)
CHECK (start_at < end_at)
```

Trong một hàng mới/cập nhật, PostgreSQL đánh giá điều kiện. Nếu điều kiện trả `FALSE`, thao tác vi phạm constraint.

**Điều kiện CHECK không phải một câu SELECT tùy ý có thể truy vấn toàn bộ database.** PostgreSQL không cho dùng subquery trực tiếp trong biểu thức CHECK để đếm các hàng khác hay tra bảng tham chiếu.

---

## 4. Điểm quan trọng nhất: CHECK chấp nhận TRUE hoặc NULL

Trong SQL, điều kiện logic có **ba giá trị**:

- `TRUE`: đúng.
- `FALSE`: sai.
- `NULL`, còn gọi là unknown: chưa xác định đúng/sai vì thiếu thông tin.

Đối với PostgreSQL `CHECK`, một hàng **đạt điều kiện nếu biểu thức trả `TRUE` hoặc `NULL`**. Chỉ khi biểu thức trả `FALSE`, PostgreSQL mới từ chối theo constraint đó.

### 4.1. Ví dụ CHECK đơn giản

```sql
CREATE TABLE example_scores (
    score_id INTEGER PRIMARY KEY,
    score INTEGER CHECK (score >= 0)
);
```

Thử từng câu khi đang ở chế độ autocommit của psql:

```sql
-- Hợp lệ: CHECK trả TRUE.
INSERT INTO example_scores VALUES (1, 10);

-- Bị từ chối: CHECK trả FALSE.
INSERT INTO example_scores VALUES (2, -3);

-- Hợp lệ theo CHECK: score >= 0 trả NULL.
INSERT INTO example_scores VALUES (3, NULL);
```

Dòng thứ ba có thể khiến người mới ngạc nhiên: **`CHECK (score >= 0)` không có nghĩa score phải có giá trị**.

| Giá trị `score` | `score >= 0` | Kết quả đối với CHECK |
| --- | --- | --- |
| 10 | `TRUE` | Được phép |
| 0 | `TRUE` | Được phép |
| -3 | `FALSE` | Bị từ chối |
| `NULL` | `NULL` | Được phép, nếu không có ràng buộc khác |

Muốn score vừa bắt buộc có giá trị vừa không âm:

```sql
CREATE TABLE example_scores_required (
    score_id INTEGER PRIMARY KEY,
    score INTEGER NOT NULL CHECK (score >= 0)
);
```

### 4.2. Vì sao PostgreSQL cho phép NULL trong CHECK?

SQL có phân biệt giữa “một giá trị đã biết vi phạm” và “chưa biết giá trị”. Ràng buộc `CHECK` không tự coi giá trị thiếu là sai; ràng buộc `NOT NULL` được tạo ra riêng để diễn đạt yêu cầu không được thiếu dữ liệu.

Hành vi này nhất quán với biểu thức SQL:

```sql
SELECT
    NULL::INTEGER >= 0 AS unknown_comparison,
    (NULL::INTEGER >= 0) IS TRUE AS explicitly_true,
    (NULL::INTEGER >= 0) IS NOT FALSE AS not_false;
```

Kết quả ý nghĩa:

- `NULL >= 0` là unknown.
- `(... ) IS TRUE` là `FALSE` khi biểu thức là unknown.
- `(... ) IS NOT FALSE` là `TRUE` khi biểu thức là unknown.

Có thể viết `CHECK (score IS NOT NULL AND score >= 0)` để từ chối NULL, nhưng **`score INTEGER NOT NULL CHECK (score >= 0)` rõ nghĩa hơn**: trách nhiệm về sự hiện diện nằm ở `NOT NULL` và miền giá trị nằm ở `CHECK`.

### 4.3. Nhiều điều kiện vẫn có thể trả NULL

Ví dụ:

```sql
CHECK (discount_amount >= 0 AND discount_amount <= list_price)
```

Nếu `discount_amount = NULL` còn `list_price = 100`, biểu thức tổng thể có thể là unknown. Nếu `list_price` thiếu, việc kiểm tra giới hạn giảm giá cũng có thể trở thành unknown.

Vì vậy khi cả hai cột đều bắt buộc:

```sql
list_price NUMERIC(12,2) NOT NULL,
discount_amount NUMERIC(12,2) NOT NULL,
CHECK (
    list_price >= 0
    AND discount_amount >= 0
    AND discount_amount <= list_price
)
```

**Quy tắc thiết kế:** kiểm tra miền giá trị và kiểm tra có dữ liệu là hai yêu cầu độc lập. Không bỏ qua `NOT NULL` chỉ vì có nhiều điều kiện trong `CHECK`.

---

## 5. Chuẩn bị database thực hành

Phần này xây một bảng sản phẩm với những điều kiện phổ biến. Để dễ học, dữ liệu chỉ là minh họa và không chứa thông tin thật.

> **Cảnh báo:** Các câu `DROP TABLE IF EXISTS` dưới đây xóa dữ liệu của những bảng lab đã tồn tại. Chỉ thực hiện trên database thực hành mà bạn được phép reset, không chạy nguyên khối trong môi trường production.

```sql
CREATE SCHEMA IF NOT EXISTS check_lab;

DROP TABLE IF EXISTS check_lab.products;
DROP TABLE IF EXISTS check_lab.legacy_prices;

CREATE TABLE check_lab.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,

    list_price NUMERIC(12,2) NOT NULL
        CONSTRAINT products_list_price_nonnegative
        CHECK (list_price >= 0),

    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    stock_quantity INTEGER NOT NULL DEFAULT 0,

    status TEXT NOT NULL DEFAULT 'DRAFT',

    CONSTRAINT products_sku_not_blank
        CHECK (btrim(sku) <> ''),

    CONSTRAINT products_name_not_blank
        CHECK (btrim(product_name) <> ''),

    CONSTRAINT products_discount_valid
        CHECK (
            discount_amount >= 0
            AND discount_amount <= list_price
        ),

    CONSTRAINT products_stock_nonnegative
        CHECK (stock_quantity >= 0),

    CONSTRAINT products_status_allowed
        CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')),

    CONSTRAINT products_active_price_positive
        CHECK (
            status <> 'ACTIVE'
            OR list_price > 0
        )
);
```

Các constraint bảo vệ những quy tắc **của mỗi sản phẩm**:

| Constraint | Yêu cầu |
| --- | --- |
| `products_list_price_nonnegative` | Giá niêm yết không âm |
| `products_sku_not_blank` | Mã SKU sau khi bỏ khoảng trắng hai đầu không được rỗng |
| `products_name_not_blank` | Tên sản phẩm không được chỉ chứa khoảng trắng thông thường |
| `products_discount_valid` | Giảm giá từ 0 đến giá gốc |
| `products_stock_nonnegative` | Số lượng tồn không âm |
| `products_status_allowed` | Trạng thái thuộc danh sách cho phép |
| `products_active_price_positive` | Sản phẩm ACTIVE phải có giá gốc lớn hơn 0 |

Những cột cần dữ liệu đều có `NOT NULL`. Nếu thiếu `NOT NULL`, một số biểu thức `CHECK` phía trên có thể trả unknown và không ngăn được hàng thiếu dữ liệu.

### 5.1. Thêm dữ liệu hợp lệ

```sql
INSERT INTO check_lab.products (
    sku, product_name, list_price,
    discount_amount, stock_quantity, status
)
VALUES
    ('BOOK-001', 'Sách PostgreSQL', 125000.00, 5000.00, 10, 'ACTIVE'),
    ('PEN-002',  'Bút xanh',         15000.00,    0.00, 50, 'ACTIVE'),
    ('GIFT-003', 'Quà tặng',             0.00,    0.00,  0, 'DRAFT')
RETURNING
    product_id, sku, list_price,
    discount_amount, stock_quantity, status;
```

Ba hàng đều hợp lệ theo quy tắc đang khai báo.

Đặc biệt, `GIFT-003` có giá 0 vì nó đang ở trạng thái `DRAFT`. Nếu chuyển sang `ACTIVE` mà vẫn giữ giá 0, constraint `products_active_price_positive` sẽ chặn.

### 5.2. Thử các thao tác vi phạm

Mỗi câu sau được dùng **độc lập để quan sát lỗi**:

```sql
-- Lỗi: giá âm.
INSERT INTO check_lab.products (
    sku, product_name, list_price
)
VALUES ('BAD-PRICE', 'Hàng lỗi', -1.00);

-- Lỗi: SKU toàn khoảng trắng.
INSERT INTO check_lab.products (
    sku, product_name, list_price
)
VALUES ('   ', 'Hàng lỗi', 100.00);

-- Lỗi: giảm giá vượt giá gốc.
INSERT INTO check_lab.products (
    sku, product_name, list_price, discount_amount
)
VALUES ('BAD-DISCOUNT', 'Hàng lỗi', 100.00, 200.00);

-- Lỗi: trạng thái không thuộc tập hợp được cho phép.
INSERT INTO check_lab.products (
    sku, product_name, list_price, status
)
VALUES ('BAD-STATUS', 'Hàng lỗi', 100.00, 'PUBLISHED');

-- Lỗi: ACTIVE nhưng giá gốc bằng 0.
INSERT INTO check_lab.products (
    sku, product_name, list_price, status
)
VALUES ('BAD-ACTIVE', 'Hàng lỗi', 0.00, 'ACTIVE');
```

Tất cả các câu trên được mong đợi báo lỗi constraint. Không nên chạy cả nhóm lệnh lỗi trong một transaction rồi tiếp tục `INSERT` bình thường, vì trong PostgreSQL một lỗi trong transaction thường khiến transaction chuyển sang trạng thái aborted cho tới khi rollback hoặc quay về savepoint phù hợp.

---

## 6. CHECK nhiều cột: quy tắc của cùng một hàng

`CHECK` không giới hạn ở từng cột độc lập. Một constraint cấp bảng có thể kiểm tra **mối liên hệ giữa nhiều cột trong một hàng**.

### 6.1. Khoảng thời gian hợp lệ

```sql
CREATE TABLE check_lab.booking_periods (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT booking_periods_time_order
        CHECK (starts_at < ends_at)
);
```

Ví dụ:

```sql
INSERT INTO check_lab.booking_periods (starts_at, ends_at)
VALUES (
    '2026-11-15 09:00:00+07',
    '2026-11-15 10:00:00+07'
);
```

Hợp lệ vì thời điểm bắt đầu sớm hơn kết thúc.

Ví dụ không hợp lệ:

```sql
INSERT INTO check_lab.booking_periods (starts_at, ends_at)
VALUES (
    '2026-11-15 11:00:00+07',
    '2026-11-15 10:00:00+07'
);
```

Ở đây `starts_at < ends_at` là `FALSE`.

**Giới hạn:** constraint này không ngăn hai **hàng khác nhau** đặt cùng một phòng vào những khoảng thời gian chồng lấn. Nó chỉ kiểm tra thứ tự thời gian **bên trong từng hàng**. Muốn cấm các lịch trùng nhau theo một khóa phòng, thường cần ràng buộc loại `EXCLUDE` với range type hoặc một thiết kế concurrency tương đương.

### 6.2. Điều kiện phụ thuộc trạng thái

Một yêu cầu nghiệp vụ:

> Đơn hàng đã giao phải có thời điểm giao hàng; đơn chưa giao có thể chưa có thời điểm đó.

Có thể viết:

```sql
CREATE TABLE check_lab.deliveries (
    delivery_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'IN_TRANSIT', 'DELIVERED')),
    delivered_at TIMESTAMPTZ,
    CONSTRAINT deliveries_delivered_time_required
        CHECK (
            status <> 'DELIVERED'
            OR delivered_at IS NOT NULL
        )
);
```

Hoặc biểu diễn bằng `CASE`:

```sql
CHECK (
    CASE
        WHEN status = 'DELIVERED'
            THEN delivered_at IS NOT NULL
        ELSE TRUE
    END
)
```

Trong thực tế nên chọn dạng đơn giản nhất dễ kiểm chứng. Nếu nghiệp vụ còn yêu cầu `delivered_at` chỉ được có khi trạng thái DELIVERED, cần thêm quy tắc đối xứng; constraint trên chưa cấm trạng thái `NEW` có timestamp.

### 6.3. Kiểm tra tổ hợp cột tùy chọn

Ví dụ một tài khoản có thể có **hoặc email hoặc số điện thoại**, nhưng phải có ít nhất một trong hai:

```sql
CREATE TABLE check_lab.contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    phone TEXT,
    CONSTRAINT contacts_at_least_one_method
        CHECK (
            email IS NOT NULL
            OR phone IS NOT NULL
        )
);
```

Nếu muốn **đúng một** trong hai trường có dữ liệu:

```sql
CREATE TABLE check_lab.exclusive_contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    phone TEXT,
    CONSTRAINT exclusive_contacts_exactly_one
        CHECK (num_nonnulls(email, phone) = 1)
);
```

Hàm `num_nonnulls` đếm số đối số không NULL. Hai cột có chuỗi rỗng vẫn được coi là **không NULL**; nếu nghiệp vụ cấm chuỗi rỗng, cần kiểm tra thêm.

---

## 7. Kiểm tra chuỗi: độ dài, khoảng trắng, regex và giới hạn

`CHECK` có thể dùng những hàm chuỗi PostgreSQL để kiểm tra định dạng cơ bản.

### 7.1. Độ dài và khoảng trắng

```sql
CREATE TABLE check_lab.tags (
    tag_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tag_code TEXT NOT NULL,
    CONSTRAINT tags_length_valid
        CHECK (char_length(tag_code) BETWEEN 3 AND 20),
    CONSTRAINT tags_not_blank
        CHECK (btrim(tag_code) <> '')
);
```

`char_length(text)` đo số ký tự trong ngữ cảnh kiểu text; `octet_length(text)` đo số byte. Với chuỗi Unicode như tiếng Việt có dấu, số byte UTF-8 có thể khác số ký tự.

Vì vậy:

- Nếu giới hạn của nghiệp vụ là **số ký tự**, cân nhắc `char_length`.
- Nếu giới hạn một giao thức/tệp là **số byte**, cần `octet_length` hoặc quy tắc byte tương ứng.
- Nếu muốn tính số ký tự hiển thị (*grapheme cluster*), điều đó phức tạp hơn chỉ số ký tự SQL; `char_length` không tự giải quyết toàn bộ cách người dùng nhìn chữ có dấu hoặc emoji.

Hàm `btrim` mặc định bỏ một số ký tự khoảng trắng theo cách hàm được định nghĩa, không phải trình kiểm tra Unicode whitespace hoàn chỉnh cho mọi ngôn ngữ. Một chuỗi chứa ký tự điều khiển/khoảng trắng đặc biệt vẫn có thể cần chuẩn hóa ở lớp khác.

### 7.2. Định dạng bằng regex

Một mã currency có đúng ba chữ cái Latin in hoa:

```sql
CREATE TABLE check_lab.currency_codes (
    code TEXT PRIMARY KEY,
    CONSTRAINT currency_codes_format
        CHECK (code ~ '^[A-Z]{3}$')
);
```

Toán tử `~` áp dụng regular expression match theo PostgreSQL.

Ví dụ:

- `USD` → khớp.
- `usd` → không khớp theo regex có phân biệt chữ hoa/thường.
- `US` → không khớp.
- `USDD` → không khớp.

Nhưng **`ABC` khớp regex vẫn chưa chứng minh nó là một currency code được công nhận**. Regex kiểm tra hình thức, không phải nguồn tham chiếu và quy tắc hiệu lực. Muốn mã thuộc một danh mục được quản lý, có thể dùng **bảng currency reference + foreign key**.

### 7.3. Kiểm tra email bằng regex có đủ không?

Một biểu thức dạng:

```sql
CHECK (email ~ '^[^@]+@[^@]+\.[^@]+$')
```

chỉ kiểm tra một phần hình thức, không chứng minh:

- Hộp thư tồn tại.
- Domain nhận thư được.
- Người dùng sở hữu email.
- Định dạng đáp ứng toàn bộ các trường hợp hợp lệ của tiêu chuẩn email.
- Địa chỉ đã được xác minh qua quy trình nghiệp vụ.

Với email đăng nhập, ứng dụng thường cần normalize theo chính sách, xác minh sở hữu, unique phù hợp và xử lý địa chỉ thay đổi theo thời gian. `CHECK` có thể là một lớp kiểm tra cú pháp giới hạn, **không thay thế email verification**.

### 7.4. Độ đúng phụ thuộc collation và chuẩn hóa

Các quy tắc so sánh chuỗi, phân biệt chữ hoa/thường, thứ tự sắp xếp và so khớp có thể chịu ảnh hưởng của collation và cách chuẩn hóa dữ liệu. Không dùng một regex đơn giản để tuyên bố mã sản phẩm hoặc tên người dùng đã được chuẩn hóa toàn diện.

Nếu yêu cầu SKU không trùng sau khi chuyển về chữ thường, một lựa chọn là **unique index trên biểu thức**:

```sql
CREATE UNIQUE INDEX products_sku_lower_unique
ON check_lab.products (lower(sku));
```

Chỉ chạy ví dụ này trên bảng lab có dữ liệu không xung đột. Index này giải quyết một khía cạnh **duy nhất**; nó không được thay bằng `CHECK (lower(sku) = sku)` nếu nghiệp vụ thực sự muốn ngăn trùng giá trị giữa **nhiều hàng**.

---

## 8. Những điều CHECK không thể kiểm tra trực tiếp

Giới hạn cơ bản: `CHECK` được định nghĩa để kiểm tra một hàng khi được insert hoặc update. Không dùng nó như một cơ chế truy vấn tùy ý tới những hàng khác hoặc bảng khác.

### 8.1. Không thể viết COUNT(*) của toàn bảng trong CHECK

Giả sử hệ thống chỉ cho phép tối đa 10 thành viên hoạt động trong một nhóm. Một ý tưởng sai là:

```sql
-- Ý tưởng KHÔNG HỢP LỆ cho CHECK trực tiếp:
CHECK (
    (SELECT COUNT(*)
     FROM group_members
     WHERE group_id = ...) <= 10
)
```

PostgreSQL **không cho subquery trực tiếp trong CHECK**. Ngay cả khi bọc phép đếm trong một hàm để né giới hạn cú pháp, tình huống concurrency và dữ liệu thay đổi về sau khiến nó không còn là invariant một hàng an toàn.

Giải pháp phụ thuộc bài toán:

- Thiết kế một hàng tổng/counter được cập nhật có điều kiện trong transaction.
- Khóa đối tượng nhóm khi phân bổ vị trí.
- Dùng isolation level phù hợp, có retry khi cần.
- Đặt constraint cho những yếu tố biểu diễn được thành khóa duy nhất.
- Có thể dùng trigger với thiết kế locking/concurrency đúng nếu yêu cầu.

### 8.2. Không thể dùng CHECK thay FOREIGN KEY

Giả sử `orders.customer_id` phải tham chiếu khách hàng còn tồn tại.

Sai ý tưởng:

```sql
-- CHECK không phải chỗ kiểm tra sự tồn tại ở bảng khác:
CHECK (customer_id IN (SELECT customer_id FROM customers))
```

Hãy dùng:

```sql
customer_id BIGINT REFERENCES customers(customer_id)
```

`FOREIGN KEY` còn phối hợp với transaction, cập nhật và xóa hàng tham chiếu theo cơ chế toàn vẹn mà một truy vấn đọc tạm thời trong CHECK không thể tự tái tạo an toàn.

### 8.3. Không thể dùng CHECK thay UNIQUE

Một bảng có hai hàng cùng `sku = 'ABC'` đều có thể thỏa `CHECK (sku <> '')`. Muốn ngăn trùng, dùng:

```sql
CONSTRAINT products_sku_unique UNIQUE (sku)
```

hoặc index unique phù hợp với nhu cầu normalize/partial predicate.

Không viết hàm CHECK đọc toàn bảng rồi đếm số SKU trùng; cách đó không có các bảo đảm tương tranh và kiểm tra toàn cục giống unique constraint/index.

### 8.4. Không thể dùng CHECK ngăn lịch đặt phòng chồng lấn giữa hai hàng

`CHECK (starts_at < ends_at)` kiểm tra thứ tự thời gian trong **một** booking.

Để ngăn hai booking cùng phòng có khoảng thời gian giao nhau, PostgreSQL cung cấp **range types** như `tstzrange` và ràng buộc `EXCLUDE` kết hợp toán tử phù hợp. Trong một số mô hình cần extension như `btree_gist` để hỗ trợ toán tử equality của khóa phòng trong GiST.

Thiết kế đó khác CHECK vì nó kiểm tra **xung đột giữa các hàng**. Việc cài extension/định nghĩa exclusion constraint cần quyền, kế hoạch migration và hiểu semantics biên thời gian (ví dụ `[)` cho phép các booking kề nhau).

### 8.5. Không thể dùng CHECK tự bảo toàn tổng tiền giữa nhiều hàng

Bảng ví tiền có:

```sql
balance_minor BIGINT NOT NULL
CHECK (balance_minor >= 0)
```

Điều kiện này ngăn một số dư âm trên từng ví. Nhưng với nghiệp vụ chuyển 1000 cents từ A sang B, CHECK không tự bảo đảm rằng **đã trừ ở A thì phải cộng đúng ở B**.

Để bảo vệ invariant này cần transaction, xác định đúng hai ví, kiểm tra đơn vị tiền, update có điều kiện, kiểm tra số hàng cập nhật và ghi lịch sử/idempotency phù hợp.

---

## 9. CHECK không tự theo dõi thời gian đang trôi

Một quy tắc hấp dẫn nhưng thường sai về mô hình là:

```sql
-- Ví dụ thiết kế KHÔNG NÊN DÙNG để bảo vệ tính "còn hạn" dài hạn.
CHECK (expires_at > now())
```

Giả sử lúc INSERT, `expires_at` ở ngày mai nên điều kiện đúng. Sang ngày kia, hàng đã hết hạn nhưng không có `INSERT` hoặc `UPDATE` nào lên hàng đó. PostgreSQL không chạy một tác vụ nền để tự đánh giá lại CHECK liên tục.

Do vậy, một ràng buộc dựa trên **thời gian hiện tại** không phù hợp để định nghĩa invariant tồn tại mãi như “chỉ lưu các hàng chưa hết hạn”.

Cách tiếp cận tốt hơn:

- Lưu `expires_at` như dữ liệu.
- Kiểm tra “còn hiệu lực” trong câu truy vấn hoặc nghiệp vụ tại thời điểm sử dụng:
  `WHERE expires_at > now()`.
- Dùng job/scheduler chuyển trạng thái hoặc dọn dẹp dữ liệu nếu cần.
- Nếu chỉ cần kiểm tra một quan hệ tĩnh bên trong hàng, dùng `CHECK (expires_at > created_at)` với các cột được xác định ổn định và không NULL theo yêu cầu.

Ví dụ quan hệ tĩnh:

```sql
CREATE TABLE check_lab.tokens (
    token_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT tokens_expiry_after_creation
        CHECK (expires_at > created_at)
);
```

Khi thời gian trôi, `expires_at > created_at` vẫn giữ đúng, vì cả hai giá trị của hàng không thay đổi. Trạng thái “đã hết hạn hay chưa” được tính khi cần, không phải một invariant vĩnh viễn của CHECK.

---

## 10. Hàm trong CHECK: yêu cầu ổn định và rủi ro thay đổi hành vi

PostgreSQL cho phép sử dụng nhiều hàm và biểu thức trong `CHECK`, nhưng về mặt thiết kế nó **giả định kết quả kiểm tra là ổn định đối với cùng dữ liệu của hàng**. Điều này thường được diễn giải là yêu cầu **immutable** theo ngữ nghĩa.

Một ví dụ hợp lý:

```sql
CHECK (btrim(sku) <> '')
```

Với cùng một giá trị `sku` và cách xử lý hàm không thay đổi, kết quả có tính ổn định.

Một ví dụ rủi ro:

```sql
-- KHÔNG nên dùng hàm biến thiên trong CHECK:
CHECK (random() > 0.5)
```

`random()` có thể trả kết quả khác nhau dù dữ liệu hàng không đổi. Một hàng có thể được chấp nhận vào lần này, từ chối vào lần khác mà không liên quan giá trị được lưu.

Tương tự, gọi hàm phụ thuộc một bảng khác, trạng thái cấu hình phiên hoặc tài nguyên ngoài database trong `CHECK` là một dấu hiệu thiết kế cần xem lại.

### 10.1. Thay định nghĩa function có thể làm hàng cũ không còn hợp lệ

Giả sử một constraint dùng hàm tùy chỉnh `is_valid_code(code)`. Sau khi bảng đã có dữ liệu, người vận hành thay định nghĩa hàm sao cho cùng giá trị mã nhưng kết quả chuyển từ TRUE sang FALSE.

**PostgreSQL không tự quét lại toàn bộ bảng ngay khi định nghĩa hàm thay đổi**. Những hàng trước đó có thể đang lưu dữ liệu trái với ý nghĩa mới của hàm. Khi dump/restore hoặc cập nhật lại hàng, lỗi mới có thể xuất hiện.

Nếu phải thay logic kiểm tra:

1. Xác định những dữ liệu đã lưu sẽ trở thành không hợp lệ.
2. Thiết kế migration làm sạch/chuyển đổi dữ liệu.
3. Thay hoặc tái tạo constraint theo quy trình có kiểm soát.
4. Dùng validation và kiểm tra kết quả; không tự ý đổi body hàm đang dùng trong CHECK mà không quản lý dữ liệu lịch sử.

Việc đánh dấu hàm `IMMUTABLE` trong DDL là một **cam kết về hành vi**, không phải cách buộc một hàm thực sự phụ thuộc thời gian/bảng khác trở thành an toàn.

### 10.2. CHECK không phải nơi thực hiện tác dụng phụ

Không nên viết hàm CHECK có mục tiêu:

- Gửi email hoặc HTTP request.
- Ghi thêm hàng vào bảng khác.
- Gọi dịch vụ bên ngoài.
- Thay đổi trạng thái ứng dụng.
- Sinh khóa hay biến đổi dữ liệu có tác dụng phụ.

CHECK dành cho **kiểm tra tính hợp lệ**, không phải workflow. Dùng mã ứng dụng, transaction, trigger phù hợp hoặc outbox nếu cần những tác động nghiệp vụ khác.

---

## 11. CHECK, NOT NULL, DEFAULT và kiểu dữ liệu

Bốn cơ chế này bổ sung nhau, không thể hoán đổi tùy tiện.

### 11.1. Kiểu dữ liệu giới hạn dạng giá trị

Ví dụ:

```sql
quantity INTEGER
price NUMERIC(12,2)
created_at TIMESTAMPTZ
```

PostgreSQL chỉ nhận những giá trị có thể chuyển sang kiểu phù hợp. Một chuỗi `'abc'` thường không thể nhập vào cột `INTEGER`.

Tuy nhiên, type `INTEGER` không tự cấm `-5`; type `NUMERIC(12,2)` không tự cấm giá âm; type `TIMESTAMPTZ` không tự biết ngày kết thúc phải sau ngày bắt đầu.

### 11.2. NOT NULL bảo đảm có dữ liệu

```sql
quantity INTEGER NOT NULL
```

Nếu người dùng không cung cấp dữ liệu và không có default phù hợp, `INSERT` bị từ chối với lỗi `not_null_violation`, thường có SQLSTATE `23502`.

### 11.3. DEFAULT cung cấp giá trị khi không chỉ định cột

```sql
stock_quantity INTEGER NOT NULL DEFAULT 0
    CHECK (stock_quantity >= 0)
```

Khi `INSERT` bỏ cột `stock_quantity`, default 0 được sử dụng. Nếu bạn **chủ động truyền NULL** cho cột, `DEFAULT 0` không tự thay giá trị NULL; `NOT NULL` từ chối nó.

DEFAULT cũng không sửa giá trị sai đã được gửi, chẳng hạn `-3`. CHECK sẽ từ chối số âm theo ví dụ.

### 11.4. CHECK bảo vệ quan hệ và miền giá trị

```sql
price NUMERIC(12,2) NOT NULL
    CHECK (price >= 0)
```

Schema kết hợp ba lớp:

1. `NUMERIC(12,2)`: kiểu số thập phân có precision/scale khai báo.
2. `NOT NULL`: bắt buộc có giá trị.
3. `CHECK (price >= 0)`: không cho giá âm.

Lưu ý `NUMERIC(12,2)` có thể **làm tròn** input về scale 2 trước khi giá trị cuối được kiểm tra. Nếu API phải từ chối mọi input có hơn hai chữ số lẻ, bạn cần validation trước khi cast, chẳng hạn tại ứng dụng hoặc staging text.

---

## 12. Lỗi CHECK trông như thế nào?

Với bảng `check_lab.products`, thử:

```sql
INSERT INTO check_lab.products (
    sku, product_name, list_price
)
VALUES ('BAD-001', 'Sản phẩm không hợp lệ', -100);
```

PostgreSQL có thể trả thông báo có dạng:

```text
ERROR: new row for relation "products"
violates check constraint "products_list_price_nonnegative"
```

Trong các driver, lỗi constraint CHECK có SQLSTATE thường gặp:

```text
23514  check_violation
```

So sánh:

| SQLSTATE | Tên thường gặp | Liên quan |
| --- | --- | --- |
| `23514` | `check_violation` | Biểu thức CHECK bị vi phạm |
| `23502` | `not_null_violation` | Cột bắt buộc nhận NULL |
| `23505` | `unique_violation` | Trùng khóa unique/primary key |
| `23503` | `foreign_key_violation` | Vi phạm quan hệ khóa ngoại |

Ứng dụng nên phân loại lỗi bằng **SQLSTATE và thông tin có cấu trúc** mà driver cung cấp, tránh phụ thuộc vào chuỗi thông báo có thể thay đổi theo ngôn ngữ hoặc phiên bản.

### 12.1. Không gửi chi tiết dữ liệu nhạy cảm ra ngoài API

Thông báo gốc của PostgreSQL có thể có tên bảng, tên constraint và đôi khi chi tiết giá trị hàng. Khi trả lỗi cho client:

- Dịch sang thông điệp nghiệp vụ phù hợp, ví dụ “Giá niêm yết phải không âm”.
- Không lộ cấu trúc nội bộ, dữ liệu riêng tư hoặc toàn bộ SQL.
- Ghi log có kiểm soát để phục vụ chẩn đoán.
- Không biến mọi lỗi CHECK thành HTTP 500 nếu đó là lỗi dữ liệu đầu vào đã biết; nhưng cũng không giả định mọi lỗi 23514 đều do người dùng cuối trực tiếp gây ra.

### 12.2. Một lỗi bên trong transaction

```sql
BEGIN;

INSERT INTO check_lab.products (
    sku, product_name, list_price
)
VALUES ('BAD-002', 'Lỗi', -10);

-- Khi câu trên lỗi, transaction thường ở trạng thái aborted.
ROLLBACK;
```

Nếu bạn muốn thử nhiều câu lỗi trong cùng phiên psql, cách đơn giản nhất là chạy từng câu ở chế độ autocommit. Nếu có transaction tường minh, dùng `ROLLBACK` hoặc `SAVEPOINT` phù hợp.

---

## 13. Cập nhật cũng phải thỏa CHECK

Constraint không chỉ áp dụng tại INSERT. Một UPDATE tạo ra hàng với biểu thức CHECK trả FALSE sẽ bị từ chối.

Ví dụ trong bảng `products`:

```sql
UPDATE check_lab.products
SET discount_amount = 999999.00
WHERE sku = 'BOOK-001';
```

Vì giá `BOOK-001` là 125000, điều kiện `discount_amount <= list_price` trở thành FALSE, nên UPDATE vi phạm constraint.

Hoặc:

```sql
UPDATE check_lab.products
SET status = 'ACTIVE'
WHERE sku = 'GIFT-003';
```

Dòng `GIFT-003` có giá niêm yết 0, vì vậy chuyển sang ACTIVE bị chặn bởi `products_active_price_positive`.

### 13.1. Kiểm tra trạng thái cuối của một câu lệnh

CHECK diễn đạt trạng thái hàng phải hợp lệ theo cách PostgreSQL kiểm tra câu DML, không phải quy tắc làm việc nhiều bước ngoài transaction. Khi thay đổi nhiều cột liên quan, cập nhật chúng **cùng câu UPDATE** nếu cần tạo trạng thái cuối hợp lệ:

```sql
UPDATE check_lab.products
SET
    list_price = 20000.00,
    status = 'ACTIVE'
WHERE sku = 'GIFT-003'
RETURNING sku, list_price, status;
```

Câu này có thể thành công vì hàng sau UPDATE có trạng thái ACTIVE và giá dương.

Không cần chuyển thành ACTIVE ở một câu UPDATE, rồi cập nhật giá ở câu sau nếu hàng trung gian vi phạm CHECK. Với CHECK, bạn không thể chỉ yêu cầu PostgreSQL bỏ qua lỗi để “chờ sửa ở cuối transaction”.

---

## 14. CHECK không hỗ trợ DEFERRABLE

PostgreSQL cho phép trì hoãn kiểm tra một số loại constraint như `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY` và `EXCLUDE` khi được khai báo phù hợp. Nhưng **CHECK không thuộc nhóm constraint có thể khai báo `DEFERRABLE`** trong PostgreSQL.

Do đó không có cách thông thường:

```sql
-- Không hợp lệ cho CHECK trong PostgreSQL:
CHECK (quantity >= 0) DEFERRABLE INITIALLY DEFERRED
```

và:

```sql
SET CONSTRAINTS ALL DEFERRED;
```

không làm một CHECK thông thường bị hoãn tới thời điểm COMMIT.

### 14.1. Vì sao điều này quan trọng?

Giả sử bảng có CHECK `balance >= 0`. Nếu một câu UPDATE tạm làm balance âm, rồi bạn dự định cộng lại trong câu kế tiếp, PostgreSQL không chấp nhận giá trị trung gian vi phạm chỉ vì transaction về sau có thể sửa.

Bạn phải thiết kế thao tác để **từng kết quả DML được kiểm tra đều hợp lệ**.

Đối với bất biến nhiều hàng chỉ có thể đánh giá vào cuối transaction, `CHECK` thường không phải công cụ thích hợp; cần xem xét mô hình dữ liệu, constraint khác hoặc cơ chế trigger/transaction được thiết kế rõ.

---

## 15. Thêm CHECK vào bảng đang có dữ liệu

Một vấn đề thực tế: bảng cũ đã có 10 triệu hàng, một số hàng còn giá âm. Nếu thêm ngay CHECK cho toàn bảng, PostgreSQL phải kiểm tra dữ liệu đã có và có thể từ chối DDL khi gặp vi phạm.

### 15.1. Cách thêm thông thường

```sql
ALTER TABLE check_lab.products
ADD CONSTRAINT products_discount_cap
CHECK (discount_amount <= 1000000);
```

Khi thêm constraint thông thường, PostgreSQL cần bảo đảm dữ liệu hiện hữu đáp ứng yêu cầu. Với bảng lớn, việc quét/khóa liên quan có thể ảnh hưởng vận hành, nên phải lập kế hoạch migration.

### 15.2. NOT VALID: cho phép áp dụng quy tắc mới trước khi kiểm tra toàn bộ dữ liệu cũ

Với CHECK, PostgreSQL hỗ trợ:

```sql
ALTER TABLE some_table
ADD CONSTRAINT some_table_rule
CHECK (some_column >= 0) NOT VALID;
```

Điều này có nghĩa:

- Constraint được thêm mà **không yêu cầu xác minh toàn bộ các hàng cũ ngay**.
- Những thao tác INSERT/UPDATE liên quan sau đó **vẫn phải đáp ứng constraint**.
- Constraint chưa được đánh dấu đã xác minh trên toàn bộ bảng, vì có thể còn hàng cũ vi phạm.
- Sau khi làm sạch dữ liệu, quản trị viên có thể chạy `VALIDATE CONSTRAINT`.

**`NOT VALID` không đồng nghĩa “constraint đã bị tắt cho mọi ghi mới”.** Đây là điểm rất dễ hiểu nhầm.

### 15.3. Lab: thêm CHECK khi có dữ liệu cũ vi phạm

Tạo bảng legacy:

```sql
CREATE TABLE check_lab.legacy_prices (
    legacy_id INTEGER PRIMARY KEY,
    price NUMERIC(12,2)
);

INSERT INTO check_lab.legacy_prices (legacy_id, price)
VALUES
    (1, 100.00),
    (2, -5.00),
    (3,  20.00),
    (4, NULL);
```

Thêm constraint **không validate dữ liệu cũ**:

```sql
ALTER TABLE check_lab.legacy_prices
ADD CONSTRAINT legacy_prices_nonnegative
CHECK (price >= 0) NOT VALID;
```

Kiểm tra constraint:

```sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'check_lab.legacy_prices'::regclass
ORDER BY conname;
```

`convalidated` của `legacy_prices_nonnegative` ban đầu là `false`.

Lúc này hàng có `price = -5` vẫn tồn tại vì chưa validate dữ liệu cũ.

Nếu thử INSERT mới với giá âm:

```sql
-- Dự kiến báo check_violation dù constraint đang NOT VALID.
INSERT INTO check_lab.legacy_prices (legacy_id, price)
VALUES (5, -2.00);
```

PostgreSQL từ chối. Điều đó xác nhận constraint đã bảo vệ các thao tác ghi mới.

### 15.4. Tìm và sửa hàng cũ vi phạm

Với điều kiện `price >= 0`, hàng có giá âm vi phạm. Trong lab:

```sql
SELECT legacy_id, price
FROM check_lab.legacy_prices
WHERE price < 0;
```

Kết quả gồm hàng `legacy_id = 2`.

Để sửa dữ liệu, cần căn cứ vào nguồn nghiệp vụ. Bài lab đặt lại thành 0:

```sql
UPDATE check_lab.legacy_prices
SET price = 0
WHERE legacy_id = 2;
```

Trong production, **không tự đổi mọi giá âm thành 0** nếu có giao dịch hoàn tiền, chiết khấu hoặc dữ liệu sai cần điều tra. Đó chỉ là lựa chọn sửa dữ liệu học tập.

Hàng `price = NULL` **không vi phạm** `CHECK (price >= 0)` vì biểu thức trả unknown. Nếu giá bắt buộc phải có, cần thêm `NOT NULL` sau khi xử lý NULL theo kế hoạch riêng.

### 15.5. Validate sau khi sửa

```sql
ALTER TABLE check_lab.legacy_prices
VALIDATE CONSTRAINT legacy_prices_nonnegative;
```

Sau khi tất cả hàng được kiểm tra thành công, `convalidated` sẽ là `true`:

```sql
SELECT
    conname, convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'check_lab.legacy_prices'::regclass;
```

Nếu vẫn còn hàng cũ vi phạm, lệnh validate báo lỗi và constraint chưa được xác nhận hoàn toàn. Không được coi `ADD CONSTRAINT ... NOT VALID` là bước migration đã kết thúc khi chưa có validation thành công.

### 15.6. NOT VALID có loại bỏ mọi khóa không?

Không. `ADD CONSTRAINT ... NOT VALID` có thể giảm nhu cầu quét ngay toàn bảng, và `VALIDATE CONSTRAINT` có đặc tính locking phù hợp để quản trị trên bảng lớn, nhưng **không có nghĩa không có lock hoặc không có ảnh hưởng tới workload**.

Trong production, phải đánh giá phiên bản PostgreSQL, kích thước bảng, transaction đang chạy, thời điểm bảo trì và kế hoạch rollback. Không chạy DDL trên bảng nóng chỉ dựa vào giả định “NOT VALID luôn tức thì và không khóa”.

---

## 16. Kiểm tra constraint hiện hữu trong catalog

PostgreSQL lưu metadata constraint trong hệ thống catalog, trong đó `pg_constraint` là nguồn quan trọng.

Ví dụ:

```sql
SELECT
    conname AS constraint_name,
    contype AS constraint_type,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'check_lab.products'::regclass
ORDER BY conname;
```

Một số `contype` thường gặp:

| Giá trị | Loại |
| --- | --- |
| `c` | CHECK |
| `p` | PRIMARY KEY |
| `u` | UNIQUE |
| `f` | FOREIGN KEY |
| `x` | EXCLUDE |

Có thể chỉ lấy CHECK:

```sql
SELECT
    conname,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'check_lab.products'::regclass
  AND contype = 'c'
ORDER BY conname;
```

Nếu đang dùng chương trình `psql`, lệnh:

```text
\d+ check_lab.products
```

giúp xem cột và constraints. Đây là meta-command của psql, không phải SQL gửi nguyên văn cho mọi GUI editor.

### 16.1. Thay đổi hoặc bỏ CHECK

Khi nghiệp vụ đổi, có thể cần thay định nghĩa constraint. PostgreSQL thường dùng thao tác drop/add thay vì sửa trực tiếp biểu thức:

```sql
-- Ví dụ minh họa; chỉ thực hiện khi đã có migration được duyệt.
ALTER TABLE check_lab.products
DROP CONSTRAINT products_discount_cap;
```

Sau đó có thể thêm định nghĩa mới với tên phù hợp.

**Không drop constraint chỉ để xử lý tạm lỗi nhập liệu trên production.** Việc bỏ lớp bảo vệ có thể cho phép những writer khác đưa dữ liệu sai vào ngay trong khoảng thời gian migration.

Trong tình huống an toàn hơn, có thể thiết kế constraint mới trước, làm sạch dữ liệu, validate rồi gỡ logic cũ theo một quy trình có kiểm soát, tùy yêu cầu và mức tương thích giữa hai điều kiện.

---

## 17. CHECK và dữ liệu từ file import

Khi dùng `COPY FROM` hoặc `\copy` để nạp dữ liệu vào bảng, PostgreSQL vẫn áp dụng những constraint được hỗ trợ, bao gồm CHECK.

Giả sử CSV chứa:

```csv
sku,product_name,list_price,discount_amount,stock_quantity,status
BOOK-100,Sách nhập từ CSV,100000,0,20,ACTIVE
BAD-100,Sản phẩm lỗi,-1000,0,10,ACTIVE
```

Câu import vào bảng `check_lab.products` với danh sách cột:

```text
\copy check_lab.products (sku, product_name, list_price, discount_amount, stock_quantity, status) FROM 'products.csv' WITH (FORMAT csv, HEADER true)
```

có thể bị từ chối vì một hàng có `list_price = -1000`, vi phạm `products_list_price_nonnegative`. Không phải chỉ vì file đọc được là mọi hàng được phép ghi vào bảng.

**Lưu ý:** `\copy` là meta-command của `psql`. File `products.csv` được đọc ở máy chạy psql, không phải tự đọc từ filesystem của PostgreSQL server.

### 17.1. Dùng staging khi dữ liệu nguồn chưa được tin cậy

Với dữ liệu cần xử lý nhiều lỗi, nên nhập vào bảng staging dưới dạng raw:

```sql
CREATE TABLE check_lab.product_import_stage (
    source_line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku_text TEXT,
    name_text TEXT,
    price_text TEXT,
    discount_text TEXT,
    stock_text TEXT,
    status_text TEXT
);
```

Staging cho phép:

1. Giữ nguyên input để điều tra.
2. Phân biệt lỗi định dạng với lỗi ràng buộc.
3. Kiểm tra dữ liệu thiếu trước khi cast.
4. Chuẩn hóa khoảng trắng và định dạng số.
5. Xử lý duplicate key theo chính sách.
6. Chỉ đưa hàng đạt yêu cầu vào bảng thật trong một transaction được quản lý.

Ví dụ kiểm tra sơ bộ:

```sql
SELECT *
FROM check_lab.product_import_stage
WHERE sku_text IS NULL
   OR btrim(sku_text) = ''
   OR price_text IS NULL
   OR price_text !~ '^[0-9]+(\.[0-9]{1,2})?$'
   OR status_text IS NULL
   OR status_text NOT IN ('DRAFT', 'ACTIVE', 'ARCHIVED');
```

Đây chỉ là **quy tắc cú pháp đơn giản**: regex chưa ngăn số quá lớn cho `NUMERIC(12,2)`, còn có thể cần phát hiện lỗi currency, giá trị âm theo nghiệp vụ, duplicate SKU, ký tự Unicode bất thường và những xung đột khác.

**Không biến mọi ô trống thành 0** và không bỏ qua dữ liệu lỗi âm thầm để cho import thành công.

### 17.2. CHECK và các giá trị đã bị làm tròn

Với:

```sql
list_price NUMERIC(12,2) NOT NULL CHECK (list_price >= 0)
```

PostgreSQL có thể làm tròn đầu vào `12.345` thành `12.35` theo scale trước khi lưu. CHECK chỉ xác nhận số cuối không âm; nó **không chứng minh file nguồn chỉ chứa tối đa hai chữ số lẻ**.

Nếu yêu cầu “không chấp nhận giá có hơn hai chữ số lẻ”, cần kiểm tra **input gốc** trước khi cast, ví dụ qua staging text hoặc ứng dụng.

---

## 18. CHECK và tính đồng thời: điều gì được bảo đảm?

Khi nhiều transaction cùng ghi vào bảng, PostgreSQL vẫn kiểm tra CHECK đối với các hàng được ghi. Nhưng một biểu thức đúng cho mỗi hàng **không tự bảo đảm** invariant trên tập nhiều hàng.

### 18.1. Ví dụ tồn kho không âm

Giả sử một sản phẩm có `stock_quantity = 3`, hai client cùng muốn bán 2 đơn vị.

Mẫu cập nhật có điều kiện:

```sql
UPDATE check_lab.products
SET stock_quantity = stock_quantity - 2
WHERE sku = 'BOOK-001'
  AND stock_quantity >= 2
RETURNING product_id, stock_quantity;
```

Câu UPDATE vừa trừ hàng vừa kiểm tra đủ tồn kho theo cách phù hợp với mức cô lập và khóa hàng đang sử dụng. Sau khi một transaction bán 2, request khác có thể chỉ cập nhật 0 hàng nếu không còn đủ tồn.

**Ứng dụng phải kiểm tra số hàng từ `RETURNING`**: cập nhật 0 hàng không tự là SQL error, nhưng là kết quả nghiệp vụ “không đủ tồn/không tìm thấy sản phẩm”.

`CHECK (stock_quantity >= 0)` là lớp bảo vệ bổ sung trước các code path khác vô tình đưa tồn kho âm.

### 18.2. Vì sao SELECT rồi UPDATE là rủi ro?

Một luồng không có bảo vệ concurrency:

```text
Client A: SELECT stock = 3
Client B: SELECT stock = 3
Client A: tính 3 - 2 = 1
Client B: tính 3 - 2 = 1
Client A: UPDATE stock = 1
Client B: UPDATE stock = 1
```

Có thể dẫn đến hai đơn hàng cùng coi đã bán thành công trong khi tồn kho chỉ bị trừ một lần. CHECK `stock >= 0` vẫn đúng cho giá trị cuối 1 nên **không phát hiện sai sót lost update/đọc dữ liệu cũ**.

Phương án cần phối hợp:

- `UPDATE ... SET stock = stock - qty WHERE stock >= qty RETURNING ...`.
- Transaction với `SELECT ... FOR UPDATE` trong tình huống phù hợp.
- Mức cô lập và cơ chế retry đúng cho mô hình nghiệp vụ.
- Ghi order/stock movement cùng transaction, kiểm tra số hàng ảnh hưởng.
- Idempotency key nếu client có thể gửi lại yêu cầu.

### 18.3. CHECK không thay thế isolation level

Hai transaction có thể cùng quan sát những hàng khác nhau rồi cập nhật chúng tạo ra một invariant toàn bảng bị sai (*write skew*), trong khi CHECK của từng hàng vẫn hợp lệ.

Nếu invariant chỉ có thể biểu diễn bằng điều kiện toàn cục, cân nhắc:

- Thiết kế lại schema cho phép một constraint mạnh hơn.
- `SERIALIZABLE` trong trường hợp phù hợp, có xử lý `serialization_failure` bằng retry toàn transaction.
- Khóa một hàng đại diện/quản lý tài nguyên chung.
- Trigger hoặc constraint trigger với chiến lược locking chặt chẽ.

Không chỉ thêm `CHECK (some_custom_function())` rồi xem như đã giải quyết concurrency.

---

## 19. CHECK và trigger: dùng cái nào?

**CHECK** thường tốt nhất khi:

- Điều kiện nằm hoàn toàn trong cùng một hàng.
- Biểu thức tương đối đơn giản và ổn định.
- Không cần tác dụng phụ.
- Bạn muốn rule hiển thị rõ trong schema và được database kiểm tra tự động.

**Trigger** có thể cần khi:

- Phải thực hiện logic phức tạp lúc INSERT/UPDATE/DELETE.
- Phải cập nhật bảng audit hoặc outbox theo quy trình được thiết kế.
- Cần phối hợp nhiều bảng và hiểu rõ transaction/concurrency.

Nhưng trigger không tự mang lại bảo đảm toàn cục: một trigger chỉ chạy `SELECT COUNT(*)` trong môi trường nhiều transaction đồng thời vẫn có thể có race condition nếu thiếu khóa/isolation phù hợp.

### 19.1. So sánh thực hành

| Yêu cầu | Công cụ phù hợp thường gặp |
| --- | --- |
| `quantity >= 0` | CHECK |
| `discount <= price` trong cùng hàng | CHECK |
| `email IS NOT NULL` | NOT NULL |
| Mỗi mã SKU chỉ xuất hiện một lần | UNIQUE hoặc unique index |
| `customer_id` phải tồn tại | FOREIGN KEY |
| Hai booking cùng phòng không được chồng giờ | EXCLUDE với range/type/operator phù hợp |
| Tổng số người active trong nhóm không quá N | Thiết kế counter/transaction/locking hoặc cơ chế phối hợp khác |
| Ghi bản ghi audit khi đơn được cập nhật | Trigger hoặc ứng dụng/outbox, tùy kiến trúc |
| Một đơn hàng chỉ được chuyển trạng thái theo đồ thị workflow | Logic ứng dụng hoặc trigger/transaction; CHECK chỉ bảo vệ tập trạng thái cho phép tại một thời điểm |
| Dữ liệu chỉ còn hiệu lực tới ngày hiện tại | Kiểm tra trong query/nghiệp vụ theo thời gian, không phụ thuộc CHECK động |
| Gửi email sau giao dịch | Workflow/outbox bên ngoài, không phải CHECK |

Lựa chọn nên bắt đầu bằng câu hỏi: **quy tắc này có chỉ phụ thuộc trạng thái của một hàng tại thời điểm ghi không?** Nếu có, CHECK có thể phù hợp. Nếu không, cần xem một công cụ khác.

---

## 20. CHECK trong domain để tái sử dụng quy tắc

Ngoài CHECK trên bảng, PostgreSQL hỗ trợ **domain**: một kiểu dữ liệu do người dùng định nghĩa dựa trên kiểu nền và có thể có constraint.

Ví dụ domain cho phần trăm:

```sql
CREATE DOMAIN check_lab.percentage AS NUMERIC(5,2)
    CHECK (VALUE >= 0 AND VALUE <= 100);
```

Sử dụng:

```sql
CREATE TABLE check_lab.campaigns (
    campaign_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campaign_name TEXT NOT NULL,
    discount_percent check_lab.percentage NOT NULL
);
```

Domain giúp nhiều bảng/cột cùng sử dụng quy tắc của một loại giá trị, giảm lặp lại một số định nghĩa.

Tuy nhiên:

- `CHECK` của domain cũng có những giới hạn về logic NULL; nếu muốn cột bắt buộc, nên đánh giá `NOT NULL` ở cấp cột như trong ví dụ.
- Domain không tự biết những quy tắc phụ thuộc **hai cột của một hàng**, như discount amount không vượt giá gốc; điều đó vẫn là CHECK của bảng.
- Khi thay đổi domain dùng bởi nhiều bảng, cần đánh giá dữ liệu và tác động tới tất cả consumer.

Không nên đưa mọi business rule vào domain chỉ để tái sử dụng; domain thích hợp cho **miền giá trị thực sự có ý nghĩa thống nhất** giữa các bảng.

---

## 21. CHECK với partition và kế thừa bảng

Trong những hệ thống lớn, bảng có thể dùng partitioning hoặc inheritance. Các ràng buộc CHECK có thể tham gia vào việc diễn đạt phạm vi dữ liệu hoặc được kế thừa theo quy tắc PostgreSQL.

Một số điểm cần nhớ:

- CHECK của bảng cha có thể có quan hệ kế thừa với bảng con, tùy cách định nghĩa và kiểu tổ chức bảng.
- PostgreSQL có cú pháp `NO INHERIT` cho một số constraint CHECK theo ngữ cảnh inheritance; không nên dùng mà chưa hiểu ảnh hưởng.
- Với declarative partitioning, giới hạn của từng partition được quản lý bởi partition bounds; CHECK bổ sung có thể phục vụ business rule nhưng không thay partition key bounds.
- Khi thêm hoặc validate constraint trên cây bảng/partition lớn, cần xem phạm vi đối tượng và tác động khóa.

Đối với một bài nhập môn, hãy ưu tiên thiết kế CHECK đúng trên bảng đơn trước, rồi mở rộng sang partition/inheritance khi hiểu mô hình dữ liệu cụ thể.

---

## 22. Những hiểu nhầm thường gặp

| Hiểu nhầm | Điều đúng hơn |
| --- | --- |
| “CHECK(price > 0) ngăn mọi giá trị thiếu.” | CHECK cho phép NULL nếu biểu thức là unknown; dùng NOT NULL khi bắt buộc. |
| “CHECK chỉ chạy lúc INSERT.” | CHECK cũng áp dụng khi UPDATE tạo ra hàng cần được kiểm tra. |
| “CHECK đảm bảo dữ liệu hợp lệ mãi theo thời gian.” | Nó không liên tục kiểm tra lại chỉ vì ngày giờ trôi qua hoặc hàm thay đổi. |
| “Có thể SELECT COUNT(*) trong CHECK.” | PostgreSQL không cho subquery trực tiếp trong CHECK; invariant toàn bảng cần cơ chế khác. |
| “Có thể dùng CHECK để kiểm tra FK.” | Dùng FOREIGN KEY, vì còn phải bảo vệ các thay đổi/xóa ở bảng được tham chiếu. |
| “Có thể dùng CHECK để cấm SKU trùng.” | Dùng UNIQUE/unique index. |
| “CHECK(amount>=0) đảm bảo hệ thống chuyển tiền đúng.” | Nó chỉ giới hạn một hàng, không bảo vệ hai bút toán cùng transaction. |
| “CHECK có thể DEFERRABLE tới COMMIT.” | PostgreSQL không hỗ trợ CHECK DEFERRABLE. |
| “CHECK cần toàn bộ biểu thức trả TRUE.” | Với SQL CHECK, TRUE hoặc NULL đều không bị coi là vi phạm. |
| “DEFAULT 0 biến mọi NULL thành 0.” | DEFAULT thường dùng khi không cung cấp cột/đưa DEFAULT, không thay mọi NULL đã gửi. |
| “NOT VALID nghĩa là bỏ kiểm tra hàng mới.” | NOT VALID bỏ qua xác minh hàng cũ lúc thêm; các thay đổi mới vẫn bị kiểm tra. |
| “VALIDATE CONSTRAINT chỉ là đổi metadata.” | Nó cần kiểm tra dữ liệu hiện hữu và có thể thất bại khi còn vi phạm. |
| “Hàm tùy chỉnh đổi logic thì PostgreSQL tự recheck mọi hàng.” | Không tự quét lại; có thể làm dữ liệu cũ trái với logic mới. |
| “Regex email khớp là email dùng được.” | Regex đơn giản chỉ kiểm tra hình thức, không xác minh tồn tại/sở hữu. |
| “Ràng buộc CHECK xử lý được mọi tình huống chạy đồng thời.” | Nó không bảo đảm invariant nhiều hàng hay ngăn tất cả lost update/write skew. |
| “CHECK giúp chống SQL injection.” | CHECK không thay prepared statements, parameter binding và phân quyền. |
| “Chỉ cần CHECK, ứng dụng không phải validate.” | Ứng dụng vẫn cần thông điệp tốt, quy tắc nghiệp vụ và kiểm tra dữ liệu trước khi gửi. |
| “Có thể tắt constraint để import nhanh cho tiện.” | Việc bỏ lớp bảo vệ có thể để lọt dữ liệu sai; dùng staging/migration có kiểm soát. |

---

## 23. Bài tập thực hành

### Bài 1 — Logic ba giá trị

Với:

```sql
CREATE TABLE check_lab.test_nulls (
    id INTEGER PRIMARY KEY,
    amount NUMERIC CHECK (amount > 0)
);
```

Dự đoán kết quả của ba lệnh:

```sql
INSERT INTO check_lab.test_nulls VALUES (1, 10);
INSERT INTO check_lab.test_nulls VALUES (2, -1);
INSERT INTO check_lab.test_nulls VALUES (3, NULL);
```

Giải thích vì sao lệnh thứ ba không nhất thiết lỗi. Sửa DDL để cấm NULL.

### Bài 2 — Kiểm tra nhiều cột

Tạo bảng `invoice_items` có:

- `quantity INTEGER NOT NULL CHECK(quantity > 0)`.
- `unit_price NUMERIC(12,2) NOT NULL CHECK(unit_price >= 0)`.
- `discount NUMERIC(12,2) NOT NULL DEFAULT 0`.
- CHECK để `discount <= quantity * unit_price`.

Viết ba ví dụ INSERT: hợp lệ, discount vượt tổng tiền, và quantity bằng 0.

### Bài 3 — Điều kiện trạng thái

Một vé có `status` trong `NEW, PAID, CANCELED`. Khi status là PAID, `paid_at` bắt buộc có giá trị.

Hãy tạo bảng và viết CHECK sử dụng `OR` hoặc `CASE`. Kiểm tra trường hợp `status = 'PAID'` nhưng `paid_at IS NULL`.

### Bài 4 — Quan hệ thời gian

Tạo bảng có `starts_at` và `ends_at` đều NOT NULL, CHECK `starts_at < ends_at`.

Sau đó giải thích tại sao hai hàng có khoảng thời gian chồng lên nhau vẫn có thể được chèn nếu chỉ dùng CHECK này.

### Bài 5 — NOT VALID và VALIDATE

Trong bảng `check_lab.legacy_prices`:

1. Thêm hàng có giá âm và NULL trước khi đặt constraint.
2. Thêm `CHECK(price >= 0) NOT VALID`.
3. Thử insert giá âm mới.
4. Tìm hàng cũ có giá âm và sửa.
5. Chạy `VALIDATE CONSTRAINT`.
6. Xem `convalidated` trong `pg_constraint`.

Giải thích vì sao hàng NULL có thể vẫn được chấp nhận.

### Bài 6 — Chọn đúng constraint

Với những yêu cầu:

- Số dư không âm.
- Mã sản phẩm không trùng.
- Customer trong order phải tồn tại.
- Một phòng không có hai booking chồng giờ.
- Email phải có giá trị.
- Giá sale không vượt giá gốc.

Hãy chọn `CHECK`, `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, `EXCLUDE` hoặc tổ hợp phù hợp và giải thích lý do.

### Bài 7 — Tìm lỗi nghiệp vụ dù CHECK đúng

Giả sử `CHECK(stock >= 0)` đã bật. Hai request đồng thời cùng đọc stock = 3, rồi đều ghi stock = 1 và cùng ghi nhận bán 2 đơn vị.

Tại sao CHECK không phát hiện sai? Viết mẫu `UPDATE ... SET stock = stock - 2 WHERE stock >= 2 RETURNING ...` và mô tả cách ứng dụng xử lý khi không trả hàng.

### Bài 8 — Ràng buộc không ổn định theo thời gian

Giả sử một hệ thống muốn “mọi row token đang lưu đều chưa hết hạn” bằng `CHECK(expires_at > now())`.

Tại sao hàng hôm nay hợp lệ vẫn có thể hết hạn ngày mai mà PostgreSQL không tự xóa nó? Hãy đề xuất phương án truy vấn `WHERE expires_at > now()` hoặc quy trình trạng thái phù hợp.

### Bài 9 — Regex và nguồn tham chiếu

Một bảng nhận currency code qua `CHECK(code ~ '^[A-Z]{3}$')`. Giá trị `AAA` có vượt qua regex không? Điều đó có chứng minh là mã tiền tệ hợp lệ không? Thiết kế bảng reference và `FOREIGN KEY` để quản lý danh sách hợp lệ.

### Bài 10 — Phân biệt lỗi trong API

PostgreSQL trả SQLSTATE:

```text
23514
23502
23505
23503
```

Hãy phân biệt CHECK, NOT NULL, UNIQUE và FOREIGN KEY. Trong ứng dụng, cần trả thông báo gì cho người dùng và cần tránh lộ loại chi tiết nào?

### Bài 11 — Làm tròn trước CHECK

Cột `price NUMERIC(12,2) NOT NULL CHECK(price >= 0)` nhận chuỗi `19.999` từ file.

PostgreSQL có thể lưu số nào? CHECK có thể phát hiện input có 3 chữ số lẻ không? Nếu nghiệp vụ phải từ chối input này, hãy thiết kế bước kiểm tra text trước khi cast.

### Bài 12 — Quy tắc business phức tạp

Một nhóm chỉ cho phép 10 thành viên ACTIVE. Hãy giải thích vì sao `CHECK((SELECT COUNT(*) ... ) <= 10)` không hợp lệ và một trigger chỉ đọc COUNT chưa đủ an toàn khi hai session đồng thời thêm thành viên.

Đề xuất cách khóa một hàng nhóm và cập nhật counter có điều kiện trong transaction hoặc một cơ chế isolation phù hợp có retry.

---

## 24. Checklist trước khi thêm CHECK vào hệ thống thật

| Câu hỏi | Điều cần quyết định |
| --- | --- |
| Quy tắc có phụ thuộc đúng một hàng không? | Nếu không, xem constraint khác hoặc transaction/locking. |
| Cột nào được phép NULL? | Dùng NOT NULL đúng chỗ, tránh UNKNOWN trong CHECK. |
| Biểu thức có ổn định không? | Tránh `now()`, `random()`, hàm đọc bảng khác hoặc hàm có tác dụng phụ. |
| Kiểu dữ liệu có tự chuyển đổi/làm tròn không? | Validation input gốc khi cần. |
| Có cùng rule ở nhiều bảng không? | Cân nhắc domain cho miền giá trị dùng chung. |
| Có cần ngăn giá trị trùng không? | UNIQUE/unique index thay vì CHECK. |
| Có khóa ngoại không? | FOREIGN KEY, không mô phỏng bằng hàm CHECK. |
| Cần kiểm soát cạnh tranh không? | Transaction, conditional UPDATE, locking/isolation, retry. |
| Bảng đã có dữ liệu cũ chưa? | Khảo sát lỗi trước khi thêm constraint; cân nhắc NOT VALID. |
| Đã validate dữ liệu cũ chưa? | Chạy VALIDATE và kiểm tra pg_constraint. |
| Constraint có tên rõ ràng không? | Hỗ trợ migration và xử lý lỗi ứng dụng. |
| Có rủi ro DDL khóa bảng không? | Lập kế hoạch vận hành và rollback phù hợp. |
| Có các writer/import ngoài ứng dụng không? | Database constraint bảo vệ chung; staging khi cần. |
| API có xử lý lỗi SQLSTATE không? | Phân loại 23514/23502/23505/23503, không lộ dữ liệu nhạy cảm. |
| Có thử dữ liệu biên chưa? | NULL, 0, âm, giá trị cực đại, chuỗi rỗng, ngày bằng nhau. |
| Có giới hạn theo thời gian không? | Truy vấn/job riêng thay vì giả định CHECK tự recheck. |

## Kết luận

**`CHECK` là công cụ quan trọng để bảo vệ tính hợp lệ của từng hàng trong PostgreSQL.** Nó diễn đạt những quy tắc như giá không âm, discount không vượt giá gốc, thời gian kết thúc sau bắt đầu hay trạng thái thuộc tập cho phép. Khi dữ liệu mới/cập nhật vi phạm điều kiện, PostgreSQL từ chối ghi thay vì tin rằng mọi ứng dụng đều đã validate đúng.

Nhưng phải hiểu **giới hạn của CHECK**:

- Biểu thức trả `TRUE` **hoặc `NULL`** đều không vi phạm; cần `NOT NULL` khi giá trị bắt buộc.
- CHECK chủ yếu kiểm tra dữ liệu **cùng một hàng**; không thay UNIQUE, FOREIGN KEY, EXCLUDE hoặc bất biến nhiều hàng.
- CHECK không tự đánh giá lại tất cả dữ liệu khi **thời gian trôi** hoặc hàm thay đổi.
- CHECK **không DEFERRABLE** trong PostgreSQL.
- `NOT VALID` giúp thêm CHECK vào bảng có dữ liệu cũ theo giai đoạn, nhưng vẫn kiểm tra các thao tác ghi mới; cần `VALIDATE CONSTRAINT` để xác minh toàn bộ dữ liệu.
- CHECK không thay transaction, khóa, mức cô lập, idempotency, validation ở ứng dụng hoặc quyền truy cập.

Thiết kế tốt là **đưa những bất biến đơn hàng, ổn định và có thể biểu đạt rõ vào CHECK**, đồng thời chọn đúng loại constraint và cơ chế giao dịch cho những quy tắc còn lại. Khi mỗi lớp bảo vệ đúng phạm vi của nó, PostgreSQL giúp hệ thống giữ dữ liệu nhất quán ngay cả khi có nhiều đường ghi và nhiều ứng dụng cùng sử dụng database.
