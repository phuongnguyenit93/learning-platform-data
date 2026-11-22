# Xây dựng schema quản lý đơn hàng với ràng buộc, sequence và dữ liệu mẫu

Một schema quản lý đơn hàng cần mô tả được khách hàng, sản phẩm, đơn hàng và các dòng hàng trong đơn. Thiết kế tốt phải giữ được tính toàn vẹn khi ứng dụng tạo đơn, thêm sản phẩm, thay đổi trạng thái hoặc cập nhật giá sản phẩm. Oracle Database cung cấp primary key, foreign key, unique, check, not null, sequence, trigger và view để xây dựng nền tảng dữ liệu có thể kiểm soát.

Bài thực hành này xây dựng một schema nhỏ nhưng có cấu trúc gần với ứng dụng thực tế. Chúng ta sẽ tạo các bảng `CUSTOMERS`, `CURRENCIES`, `PRODUCTS`, `ORDERS` và `ORDER_ITEMS`; định nghĩa khóa và ràng buộc; dùng sequence kết hợp trigger để sinh ID; nạp dữ liệu mẫu; rồi chạy truy vấn kiểm tra và tổng hợp đơn hàng.

Các lệnh được viết cho Oracle SQL. Chạy trong schema ứng dụng đã được DBA cấp quyền tạo bảng, sequence, trigger, view và đủ quota tablespace. Không cần cấp quyền `DBA` cho user ứng dụng.

## 1. Xác định yêu cầu và mô hình dữ liệu

### 1.1. Các thực thể chính

| Bảng | Vai trò | Khóa chính |
|---|---|---|
| `CUSTOMERS` | Lưu thông tin khách hàng. | `CUSTOMER_ID` |
| `CURRENCIES` | Danh mục tiền tệ hợp lệ. | `CURRENCY_CODE` |
| `PRODUCTS` | Danh mục sản phẩm và giá hiện tại. | `PRODUCT_ID` |
| `ORDERS` | Thông tin phần đầu đơn hàng. | `ORDER_ID` |
| `ORDER_ITEMS` | Các dòng sản phẩm thuộc một đơn hàng. | (`ORDER_ID`, `LINE_NO`) |

Quan hệ dữ liệu:

```text
CUSTOMERS (1) -------- (N) ORDERS
                           |
                           | (1)
                           |
                           (N)
                       ORDER_ITEMS
                           |
                           | (N)
                           |
                           (1)
                        PRODUCTS

CURRENCIES (1) -------- (N) PRODUCTS
CURRENCIES (1) -------- (N) ORDERS
```

Một khách hàng có thể có nhiều đơn hàng. Một đơn hàng có một hoặc nhiều dòng hàng. Mỗi dòng hàng tham chiếu một sản phẩm. Cả sản phẩm và đơn hàng đều tham chiếu mã tiền tệ để tránh lưu mã tiền tệ tùy ý.

### 1.2. Tại sao ORDER_ITEMS là bảng riêng?

Một đơn hàng có thể chứa nhiều sản phẩm; nếu đặt `PRODUCT_ID`, `QUANTITY` và `UNIT_PRICE` trực tiếp trong `ORDERS`, mỗi đơn chỉ lưu được một sản phẩm hoặc phải tạo các cột lặp như `PRODUCT_1`, `PRODUCT_2`. Cách đó khó mở rộng và gây bất thường khi thêm/sửa dữ liệu.

Tách `ORDER_ITEMS` tạo quan hệ một-nhiều rõ ràng. Khóa chính ghép (`ORDER_ID`, `LINE_NO`) xác định từng dòng trong đơn. `LINE_NO` là số thứ tự do ứng dụng cấp trong phạm vi một đơn, không cần sequence riêng.

### 1.3. Lưu giá bán tại thời điểm đặt hàng

`PRODUCTS.UNIT_PRICE` là giá hiện tại trong catalog. `ORDER_ITEMS.UNIT_PRICE` là giá đã chốt tại thời điểm đặt hàng. Không nên tính lại lịch sử đơn hàng bằng giá hiện tại của sản phẩm vì giá catalog có thể thay đổi sau này.

Tương tự, đơn hàng lưu `CURRENCY_CODE` của giao dịch. Nếu sản phẩm đổi giá hoặc đổi cách niêm yết sau này, dữ liệu đơn hàng cũ vẫn giữ được số tiền và tiền tệ đã áp dụng khi mua.

### 1.4. Quy tắc nghiệp vụ và ràng buộc database

Schema sẽ bảo đảm các quy tắc có thể biểu diễn ở cấp hàng hoặc quan hệ:

- ID không được null và không trùng.
- Email khách hàng và SKU sản phẩm là duy nhất.
- Đơn hàng phải tham chiếu khách hàng tồn tại.
- Dòng hàng phải tham chiếu đơn hàng và sản phẩm tồn tại.
- Số lượng phải lớn hơn 0.
- Đơn giá và chiết khấu không âm.
- Chiết khấu của một dòng không được vượt quá thành tiền trước chiết khấu.
- Trạng thái đơn hàng chỉ nhận một trong các giá trị đã quy định.
- Mã tiền tệ phải tồn tại trong danh mục tiền tệ.

Các quy tắc liên quan nhiều bảng, chẳng hạn tiền tệ của sản phẩm phải khớp tiền tệ đơn hàng, cần được kiểm tra trong service hoặc stored procedure trong cùng transaction. Một `CHECK` constraint thông thường không thể truy vấn bảng khác.

## 2. Chọn kiểu dữ liệu Oracle

| Dữ liệu | Kiểu đề xuất | Lý do |
|---|---|---|
| ID | `NUMBER(19,0)` | Dùng cho khóa số nguyên lớn. |
| Tên/email/SKU | `VARCHAR2(... CHAR)` | Chuỗi có giới hạn; dùng character semantics rõ ràng. |
| Số lượng | `NUMBER(12,3)` | Cho phép hàng hóa tính theo phần lẻ. |
| Đơn giá/chiết khấu | `NUMBER(19,4)` | Giữ độ chính xác thập phân, tránh kiểu dấu phẩy động. |
| Trạng thái | `VARCHAR2(20 CHAR)` | Mã trạng thái dễ đọc, có check constraint. |
| Thời điểm | `TIMESTAMP(6) WITH TIME ZONE` | Lưu thời điểm kèm timezone/offset. |
| Ghi chú dài | `CLOB` nếu cần | Dành cho nội dung văn bản lớn. |

Không dùng `FLOAT` hoặc `BINARY_DOUBLE` cho tiền tệ nếu nghiệp vụ cần phép tính thập phân chính xác. Trong Java, `BigDecimal` thường phù hợp với Oracle `NUMBER` cho tiền và số lượng có phần lẻ.

Oracle `DATE` có cả ngày và giờ tới giây. Nếu chỉ cần ngày lịch, có thể dùng `DATE` nhưng cần quy ước phần giờ; nếu cần fractional seconds hoặc timezone, dùng `TIMESTAMP` phù hợp. Ví dụ dưới đây dùng `TIMESTAMP WITH TIME ZONE` cho các mốc thời gian quan trọng.

## 3. Tạo bảng theo thứ tự phụ thuộc

Tạo bảng cha trước bảng con để foreign key có thể tham chiếu. Thực thi trong schema ứng dụng; các tên không có prefix schema sẽ thuộc user hiện tại.

### 3.1. Bảng CURRENCIES

```sql
CREATE TABLE currencies (
    currency_code  VARCHAR2(3 CHAR)  NOT NULL,
    currency_name  VARCHAR2(60 CHAR) NOT NULL,
    minor_units    NUMBER(1,0)       DEFAULT 2 NOT NULL,
    CONSTRAINT pk_currencies PRIMARY KEY (currency_code),
    CONSTRAINT ck_currencies_code_len
        CHECK (LENGTH(currency_code) = 3),
    CONSTRAINT ck_currencies_minor_units
        CHECK (minor_units BETWEEN 0 AND 4)
);
```

`CURRENCY_CODE` là khóa chính dạng mã ba ký tự. `MINOR_UNITS` mô tả số chữ số thập phân thông dụng của đơn vị tiền tệ, nhưng quy tắc làm tròn và tính tiền vẫn phải được xử lý thống nhất ở tầng nghiệp vụ.

### 3.2. Bảng CUSTOMERS

```sql
CREATE TABLE customers (
    customer_id  NUMBER(19,0)       NOT NULL,
    full_name    VARCHAR2(150 CHAR) NOT NULL,
    email        VARCHAR2(320 CHAR) NOT NULL,
    phone        VARCHAR2(30 CHAR),
    created_at   TIMESTAMP(6) WITH TIME ZONE
                 DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_email UNIQUE (email)
);
```

`EMAIL` được đặt unique để tránh hai khách hàng dùng cùng địa chỉ email theo quy tắc của ví dụ. Nếu nghiệp vụ cho phép email trùng hoặc email không phải định danh duy nhất, hãy điều chỉnh constraint. Oracle hiện coi chuỗi rỗng của `VARCHAR2` như `NULL`; vì vậy `NOT NULL` cũng ngăn email rỗng theo semantics Oracle.

### 3.3. Bảng PRODUCTS

```sql
CREATE TABLE products (
    product_id    NUMBER(19,0)        NOT NULL,
    sku           VARCHAR2(40 CHAR)   NOT NULL,
    product_name  VARCHAR2(200 CHAR) NOT NULL,
    unit_price    NUMBER(19,4)        NOT NULL,
    currency_code VARCHAR2(3 CHAR)   NOT NULL,
    is_active     CHAR(1 CHAR)        DEFAULT 'Y' NOT NULL,
    created_at    TIMESTAMP(6) WITH TIME ZONE
                  DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_products PRIMARY KEY (product_id),
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT fk_products_currency
        FOREIGN KEY (currency_code)
        REFERENCES currencies (currency_code),
    CONSTRAINT ck_products_price CHECK (unit_price >= 0),
    CONSTRAINT ck_products_active CHECK (is_active IN ('Y', 'N'))
);
```

SKU là mã sản phẩm duy nhất. Giá hiện tại không được âm. `IS_ACTIVE` cho phép ngừng bán sản phẩm mà vẫn giữ tham chiếu từ các đơn hàng cũ. Không xóa sản phẩm đã được dùng trong lịch sử đơn hàng.

### 3.4. Bảng ORDERS

```sql
CREATE TABLE orders (
    order_id         NUMBER(19,0)        NOT NULL,
    order_number     VARCHAR2(30 CHAR)  NOT NULL,
    customer_id      NUMBER(19,0)        NOT NULL,
    ordered_at       TIMESTAMP(6) WITH TIME ZONE
                     DEFAULT SYSTIMESTAMP NOT NULL,
    order_status     VARCHAR2(20 CHAR)  DEFAULT 'PENDING' NOT NULL,
    currency_code    VARCHAR2(3 CHAR)  NOT NULL,
    shipping_address VARCHAR2(500 CHAR),
    note             VARCHAR2(1000 CHAR),
    CONSTRAINT pk_orders PRIMARY KEY (order_id),
    CONSTRAINT uq_orders_order_number UNIQUE (order_number),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id),
    CONSTRAINT fk_orders_currency
        FOREIGN KEY (currency_code)
        REFERENCES currencies (currency_code),
    CONSTRAINT ck_orders_status
        CHECK (order_status IN (
            'PENDING', 'CONFIRMED', 'SHIPPED',
            'COMPLETED', 'CANCELLED'
        ))
);
```

`ORDER_NUMBER` là mã hiển thị cho người dùng và có unique constraint. `ORDER_ID` là khóa kỹ thuật dùng cho join. Hai loại định danh phục vụ hai mục đích khác nhau.

Địa chỉ giao hàng được lưu snapshot trên đơn hàng để lịch sử không thay đổi khi khách hàng cập nhật địa chỉ trong hồ sơ. Trong hệ thống phức tạp hơn, có thể có bảng địa chỉ riêng và vẫn sao chép các trường cần thiết vào đơn tại thời điểm đặt hàng.

### 3.5. Bảng ORDER_ITEMS

```sql
CREATE TABLE order_items (
    order_id         NUMBER(19,0) NOT NULL,
    line_no          NUMBER(5,0)  NOT NULL,
    product_id       NUMBER(19,0) NOT NULL,
    quantity         NUMBER(12,3) NOT NULL,
    unit_price       NUMBER(19,4) NOT NULL,
    discount_amount  NUMBER(19,4) DEFAULT 0 NOT NULL,
    CONSTRAINT pk_order_items PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id),
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id)
        REFERENCES products (product_id),
    CONSTRAINT ck_order_items_line_no CHECK (line_no > 0),
    CONSTRAINT ck_order_items_quantity CHECK (quantity > 0),
    CONSTRAINT ck_order_items_price CHECK (unit_price >= 0),
    CONSTRAINT ck_order_items_discount
        CHECK (
            discount_amount >= 0
            AND discount_amount <= quantity * unit_price
        )
);
```

Khóa chính ghép bảo đảm số dòng không trùng trong cùng đơn. Khóa ngoại ngăn dòng hàng tham chiếu đơn hoặc sản phẩm không tồn tại. `UNIT_PRICE` lưu giá đã chốt tại thời điểm bán; `DISCOUNT_AMOUNT` lưu chiết khấu tiền cho dòng đó.

Ví dụ dùng khóa ngoại mặc định không cho xóa bản ghi cha đang được tham chiếu. Đây là chủ ý để bảo vệ lịch sử đơn hàng. Không dùng `ON DELETE CASCADE` cho `ORDERS`/`ORDER_ITEMS` nếu hệ thống cần lưu dấu vết giao dịch hoặc có yêu cầu audit.

## 4. Tạo index hỗ trợ truy vấn và khóa ngoại

Primary key và unique constraint thường tạo unique index tương ứng. Với các foreign key không phải leading column của index sẵn có, nên cân nhắc index riêng để hỗ trợ join và giảm vấn đề khóa khi cập nhật/xóa hàng cha.

```sql
CREATE INDEX ix_orders_customer_date
    ON orders (customer_id, ordered_at);

CREATE INDEX ix_orders_status_date
    ON orders (order_status, ordered_at);

CREATE INDEX ix_order_items_product
    ON order_items (product_id);
```

Khóa chính của `ORDER_ITEMS` là `(ORDER_ID, LINE_NO)`, nên index PK đã hỗ trợ truy vấn theo `ORDER_ID` ở leading column. Index `PRODUCT_ID` hỗ trợ truy vấn dòng hàng theo sản phẩm và thao tác liên quan tới foreign key.

Không tạo index cho mọi cột. Mỗi index làm tăng dung lượng và chi phí `INSERT`, `UPDATE`, `DELETE`; chọn index theo workload thực tế và kiểm tra execution plan.

## 5. Tạo sequence để sinh khóa chính

### 5.1. Sequence là gì?

Sequence là đối tượng Oracle tạo ra dãy số theo yêu cầu. Nhiều session có thể lấy giá trị từ cùng sequence mà không cần tự khóa một bảng counter. Sequence phù hợp để cấp ID kỹ thuật cho khách hàng, sản phẩm và đơn hàng.

Tạo sequence:

```sql
CREATE SEQUENCE customers_seq
    START WITH 1001
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    CACHE 50
    NOCYCLE;

CREATE SEQUENCE products_seq
    START WITH 5001
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    CACHE 50
    NOCYCLE;

CREATE SEQUENCE orders_seq
    START WITH 9001
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    CACHE 50
    NOCYCLE;
```

Giải thích:

- `START WITH`: giá trị bắt đầu.
- `INCREMENT BY`: bước tăng sau mỗi lần lấy.
- `MINVALUE`/`NOMAXVALUE`: giới hạn dãy.
- `CACHE 50`: cache một nhóm giá trị trong instance để giảm chi phí lấy sequence.
- `NOCYCLE`: không quay vòng khi chạm giới hạn.

Các giá trị bắt đầu chỉ để minh họa. Trong hệ thống có dữ liệu được nạp sẵn, phải chọn giá trị sequence lớn hơn khóa hiện có hoặc đồng bộ sequence theo quy trình triển khai.

### 5.2. NEXTVAL và CURRVAL

Lấy giá trị mới:

```sql
SELECT customers_seq.NEXTVAL
FROM dual;
```

Sau khi đã gọi `NEXTVAL` trong session hiện tại, có thể đọc giá trị vừa lấy bằng:

```sql
SELECT customers_seq.CURRVAL
FROM dual;
```

`CURRVAL` chỉ dùng được trong session sau khi session đó đã gọi `NEXTVAL` ít nhất một lần cho sequence tương ứng. Giá trị của session khác không ảnh hưởng tới `CURRVAL` hiện tại.

Có thể dùng trực tiếp trong `INSERT`:

```sql
INSERT INTO customers (
    customer_id, full_name, email
)
VALUES (
    customers_seq.NEXTVAL,
    'Nguyen An',
    'an@example.com'
);
```

### 5.3. Sequence không bảo đảm ID liên tục

Sequence có thể tạo khoảng trống vì:

- Transaction lấy `NEXTVAL` rồi rollback.
- Instance restart hoặc cache sequence bị mất.
- Nhiều session lấy số đồng thời.
- Câu lệnh lấy sequence nhưng không insert thành công.
- Cấu hình RAC/cache và hoạt động sequence tạo khoảng trống.

Đây là hành vi bình thường. Không dùng sequence làm số hóa đơn cần liên tục tuyệt đối nếu quy định nghiệp vụ/pháp lý yêu cầu không có khoảng trống. Sequence bảo đảm cấp giá trị duy nhất trong phạm vi cấu hình, không phải bộ đếm transaction gapless.

### 5.4. CACHE, ORDER và RAC

`CACHE` cải thiện hiệu năng khi nhiều session lấy sequence. Nếu instance dừng bất thường, các giá trị đã cache nhưng chưa dùng có thể bị bỏ qua; khoảng trống không phải lỗi.

Trong RAC, sequence `NOORDER` thường phù hợp khi chỉ cần giá trị duy nhất và throughput. `ORDER` yêu cầu thứ tự cấp phát theo thứ tự request ở mức cluster, có thể tăng chi phí phối hợp. Không bật `ORDER` chỉ vì muốn ID tăng theo thời gian commit; sequence không bảo đảm thứ tự commit của transaction.

### 5.5. Kiểm tra sequence

```sql
SELECT sequence_name,
       min_value,
       max_value,
       increment_by,
       cache_size,
       cycle_flag,
       order_flag,
       last_number
FROM user_sequences
ORDER BY sequence_name;
```

`LAST_NUMBER` với sequence cache có thể phản ánh giá trị tiếp theo đã được ghi nhận/cache boundary chứ không nhất thiết là giá trị cuối đã cấp cho ứng dụng. Không dùng nó như bằng chứng chính xác của ID lớn nhất trong bảng.

## 6. Dùng trigger tự gán ID

### 6.1. Vì sao dùng trigger?

Trigger `BEFORE INSERT` có thể lấy `NEXTVAL` khi ứng dụng không truyền ID. Nhờ đó, câu `INSERT` chỉ cần truyền các cột nghiệp vụ; database tự cấp khóa.

Trigger cho khách hàng:

```sql
CREATE OR REPLACE TRIGGER customers_bir
BEFORE INSERT ON customers
FOR EACH ROW
BEGIN
    IF :NEW.customer_id IS NULL THEN
        :NEW.customer_id := customers_seq.NEXTVAL;
    END IF;
END;
/
```

Trigger cho sản phẩm:

```sql
CREATE OR REPLACE TRIGGER products_bir
BEFORE INSERT ON products
FOR EACH ROW
BEGIN
    IF :NEW.product_id IS NULL THEN
        :NEW.product_id := products_seq.NEXTVAL;
    END IF;
END;
/
```

Trigger cho đơn hàng:

```sql
CREATE OR REPLACE TRIGGER orders_bir
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.order_id IS NULL THEN
        :NEW.order_id := orders_seq.NEXTVAL;
    END IF;
END;
/
```

`FOR EACH ROW` tạo trigger cho từng hàng. `:NEW` đại diện giá trị hàng sau khi insert; trigger chỉ cấp ID khi giá trị được truyền vào là `NULL`, cho phép một số tác vụ migration/import cung cấp ID tường minh nếu được quyền và có kế hoạch đồng bộ sequence.

### 6.2. Kiểm tra trigger và lỗi biên dịch

```sql
SELECT trigger_name,
       table_name,
       status,
       triggering_event
FROM user_triggers
WHERE table_name IN ('CUSTOMERS', 'PRODUCTS', 'ORDERS')
ORDER BY table_name, trigger_name;
```

Nếu trigger không hợp lệ:

```sql
SELECT name, type, line, position, text
FROM user_errors
WHERE type = 'TRIGGER'
ORDER BY name, sequence;
```

Không tiếp tục nạp dữ liệu khi trigger sinh ID đang INVALID hoặc DISABLED. Một insert không có ID sẽ thất bại vì khóa chính `NOT NULL` nếu trigger không chạy.

### 6.3. Lựa chọn hiện đại: identity column

Oracle 12c trở lên hỗ trợ identity column. Nếu dự án không cần quản lý sequence và trigger riêng, có thể khai báo:

```sql
CREATE TABLE customers_identity_demo (
    customer_id NUMBER(19,0)
        GENERATED BY DEFAULT ON NULL AS IDENTITY
        (START WITH 1 INCREMENT BY 1 CACHE 50),
    full_name VARCHAR2(150 CHAR) NOT NULL,
    CONSTRAINT pk_customers_identity_demo PRIMARY KEY (customer_id)
);
```

Identity giúp DDL gọn hơn; Oracle quản lý sequence nội bộ. `GENERATED ALWAYS` không cho ứng dụng truyền giá trị tường minh; `BY DEFAULT` cho phép truyền giá trị; `BY DEFAULT ON NULL` cũng tự sinh khi giá trị truyền vào là `NULL`.

Chọn một cơ chế sinh ID cho mỗi cột: identity hoặc sequence/trigger. Không vừa khai báo identity vừa gắn trigger lấy sequence cho cùng một ID. Ví dụ chính trong bài dùng sequence/trigger để minh họa rõ cơ chế và tương thích với các hệ thống Oracle cũ hơn.

## 7. Nạp dữ liệu danh mục mẫu

Chạy các lệnh trong schema rỗng hoặc schema test mới. Các giá trị unique trong ví dụ được thiết kế cho một lần chạy; nếu chạy lại, các unique constraint sẽ báo trùng. Với seed script cần chạy nhiều lần, hãy chuyển sang `MERGE` hoặc kiểm tra dữ liệu tồn tại trước khi insert.

### 7.1. Nạp tiền tệ

```sql
INSERT INTO currencies (currency_code, currency_name, minor_units)
VALUES ('VND', 'Vietnamese Dong', 0);

INSERT INTO currencies (currency_code, currency_name, minor_units)
VALUES ('USD', 'US Dollar', 2);

INSERT INTO currencies (currency_code, currency_name, minor_units)
VALUES ('EUR', 'Euro', 2);
```

### 7.2. Nạp khách hàng

Không truyền `CUSTOMER_ID`; trigger sẽ lấy giá trị từ `CUSTOMERS_SEQ`:

```sql
INSERT INTO customers (full_name, email, phone)
VALUES ('Nguyen An', 'an@example.com', '+84901234567');

INSERT INTO customers (full_name, email, phone)
VALUES ('Tran Binh', 'binh@example.com', '+84907654321');

INSERT INTO customers (full_name, email, phone)
VALUES ('Le Chi', 'chi@example.com', NULL);
```

### 7.3. Nạp sản phẩm

```sql
INSERT INTO products (
    sku, product_name, unit_price, currency_code, is_active
)
VALUES (
    'KB-001', 'Mechanical Keyboard', 125.5000, 'USD', 'Y'
);

INSERT INTO products (
    sku, product_name, unit_price, currency_code, is_active
)
VALUES (
    'MS-002', 'Wireless Mouse', 45.0000, 'USD', 'Y'
);

INSERT INTO products (
    sku, product_name, unit_price, currency_code, is_active
)
VALUES (
    'BAG-003', 'Laptop Bag', 750000.0000, 'VND', 'Y'
);
```

### 7.4. Tạo đơn hàng mẫu

Dùng `INSERT ... SELECT` để lấy `CUSTOMER_ID` theo email đã unique:

```sql
INSERT INTO orders (
    order_number,
    customer_id,
    currency_code,
    order_status,
    shipping_address,
    note
)
SELECT
    'ORD-2026-0001',
    customer_id,
    'USD',
    'CONFIRMED',
    '12 Nguyen Hue, District 1, Ho Chi Minh City',
    'Sample order one'
FROM customers
WHERE email = 'an@example.com';
```

```sql
INSERT INTO orders (
    order_number,
    customer_id,
    currency_code,
    order_status,
    shipping_address,
    note
)
SELECT
    'ORD-2026-0002',
    customer_id,
    'VND',
    'PENDING',
    '25 Le Loi, District 1, Ho Chi Minh City',
    'Sample order two'
FROM customers
WHERE email = 'binh@example.com';
```

Mỗi truy vấn phải trả về đúng một khách hàng. Unique constraint trên email hỗ trợ giả định đó; nếu không có dòng nào, `INSERT ... SELECT` sẽ chèn 0 hàng mà không nhất thiết báo lỗi. Trong script production, nên kiểm tra row count hoặc dùng PL/SQL để báo lỗi rõ ràng khi không tìm thấy khách hàng.

### 7.5. Thêm dòng hàng

Giá được sao chép từ catalog vào `ORDER_ITEMS.UNIT_PRICE` tại thời điểm tạo đơn:

```sql
INSERT INTO order_items (
    order_id, line_no, product_id,
    quantity, unit_price, discount_amount
)
SELECT
    o.order_id,
    1,
    p.product_id,
    1,
    p.unit_price,
    0
FROM orders o
CROSS JOIN products p
WHERE o.order_number = 'ORD-2026-0001'
  AND p.sku = 'KB-001';
```

```sql
INSERT INTO order_items (
    order_id, line_no, product_id,
    quantity, unit_price, discount_amount
)
SELECT
    o.order_id,
    2,
    p.product_id,
    2,
    p.unit_price,
    5.0000
FROM orders o
CROSS JOIN products p
WHERE o.order_number = 'ORD-2026-0001'
  AND p.sku = 'MS-002';
```

```sql
INSERT INTO order_items (
    order_id, line_no, product_id,
    quantity, unit_price, discount_amount
)
SELECT
    o.order_id,
    1,
    p.product_id,
    1,
    p.unit_price,
    0
FROM orders o
CROSS JOIN products p
WHERE o.order_number = 'ORD-2026-0002'
  AND p.sku = 'BAG-003';
```

Trong ứng dụng thực tế, service phải xác nhận sản phẩm đang active, giá và currency hợp lệ, rồi tạo order header và các line trong cùng transaction. Ví dụ SQL trên giả định đơn hàng và sản phẩm đã tồn tại.

### 7.6. Commit dữ liệu mẫu

```sql
COMMIT;
```

Các lệnh DML có thể rollback trước commit. Tuy nhiên, DDL trong Oracle có implicit commit trước/sau một số thao tác DDL; không kỳ vọng có thể rollback toàn bộ script tạo bảng và sequence như một transaction DML duy nhất.

## 8. Tạo view tính tổng đơn hàng

Không lưu tổng đơn hàng trùng lặp ở cả header và line nếu chưa có chiến lược cập nhật nhất quán. Có thể tính từ các dòng hàng bằng view:

```sql
CREATE OR REPLACE VIEW v_order_totals AS
SELECT
    o.order_id,
    o.order_number,
    o.customer_id,
    o.ordered_at,
    o.order_status,
    o.currency_code,
    NVL(
        SUM(oi.quantity * oi.unit_price - oi.discount_amount),
        0
    ) AS total_amount
FROM orders o
LEFT JOIN order_items oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    o.customer_id,
    o.ordered_at,
    o.order_status,
    o.currency_code;
```

`LEFT JOIN` giúp đơn hàng chưa có dòng hàng vẫn xuất hiện với tổng bằng 0. `NVL` thay kết quả `NULL` của `SUM` bằng 0. Nếu có thuế, phí vận chuyển, coupon hoặc làm tròn ở cấp đơn, cần mở rộng mô hình và quy tắc tính tổng; không nên giả định tổng chỉ là tổng line amount trong mọi hệ thống.

## 9. Truy vấn kiểm tra dữ liệu

### 9.1. Xem khách hàng

```sql
SELECT customer_id, full_name, email, phone, created_at
FROM customers
ORDER BY customer_id;
```

### 9.2. Xem danh mục sản phẩm

```sql
SELECT p.product_id,
       p.sku,
       p.product_name,
       p.unit_price,
       p.currency_code,
       p.is_active,
       c.currency_name
FROM products p
JOIN currencies c
  ON c.currency_code = p.currency_code
ORDER BY p.sku;
```

### 9.3. Xem danh sách đơn hàng và tổng tiền

```sql
SELECT order_number,
       customer_id,
       ordered_at,
       order_status,
       currency_code,
       total_amount
FROM v_order_totals
ORDER BY ordered_at DESC;
```

### 9.4. Xem chi tiết một đơn hàng

```sql
SELECT o.order_number,
       c.full_name,
       o.order_status,
       o.currency_code,
       oi.line_no,
       p.sku,
       p.product_name,
       oi.quantity,
       oi.unit_price,
       oi.discount_amount,
       oi.quantity * oi.unit_price - oi.discount_amount AS line_total
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN order_items oi
  ON oi.order_id = o.order_id
JOIN products p
  ON p.product_id = oi.product_id
WHERE o.order_number = 'ORD-2026-0001'
ORDER BY oi.line_no;
```

### 9.5. Top sản phẩm theo doanh thu

```sql
SELECT p.sku,
       p.product_name,
       SUM(oi.quantity) AS units_sold,
       SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS sales_amount
FROM order_items oi
JOIN products p
  ON p.product_id = oi.product_id
JOIN orders o
  ON o.order_id = oi.order_id
WHERE o.order_status IN ('CONFIRMED', 'SHIPPED', 'COMPLETED')
GROUP BY p.sku, p.product_name
ORDER BY sales_amount DESC;
```

Truy vấn tổng hợp này đang nhóm các đơn theo sản phẩm nhưng chưa tách tiền tệ. Trong schema mẫu có thể tồn tại cả USD và VND; cộng trực tiếp các số tiền khác tiền tệ là sai nghiệp vụ. Trong báo cáo thật, phải group thêm `o.currency_code`, hoặc quy đổi theo tỷ giá và thời điểm quy đổi đã được xác định.

Phiên bản phân nhóm theo tiền tệ:

```sql
SELECT p.sku,
       p.product_name,
       o.currency_code,
       SUM(oi.quantity) AS units_sold,
       SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS sales_amount
FROM order_items oi
JOIN products p
  ON p.product_id = oi.product_id
JOIN orders o
  ON o.order_id = oi.order_id
WHERE o.order_status IN ('CONFIRMED', 'SHIPPED', 'COMPLETED')
GROUP BY p.sku, p.product_name, o.currency_code
ORDER BY o.currency_code, sales_amount DESC;
```

## 10. Kiểm tra ràng buộc và metadata

### 10.1. Xem constraint

```sql
SELECT constraint_name,
       constraint_type,
       table_name,
       status,
       validated,
       deferrable,
       deferred
FROM user_constraints
WHERE table_name IN (
    'CURRENCIES', 'CUSTOMERS', 'PRODUCTS', 'ORDERS', 'ORDER_ITEMS'
)
ORDER BY table_name, constraint_type, constraint_name;
```

Các loại constraint thường gặp:

| Mã | Ý nghĩa |
|---|---|
| `P` | Primary key. |
| `R` | Referential integrity / foreign key. |
| `U` | Unique. |
| `C` | Check constraint hoặc not null được biểu diễn trong dictionary. |

### 10.2. Xem cột tham gia constraint

```sql
SELECT uc.table_name,
       uc.constraint_name,
       ucc.column_name,
       ucc.position
FROM user_constraints uc
JOIN user_cons_columns ucc
  ON ucc.constraint_name = uc.constraint_name
 AND ucc.table_name = uc.table_name
WHERE uc.table_name IN ('CUSTOMERS', 'PRODUCTS', 'ORDERS', 'ORDER_ITEMS')
ORDER BY uc.table_name, uc.constraint_name, ucc.position;
```

### 10.3. Xem index

```sql
SELECT index_name,
       table_name,
       uniqueness,
       status,
       visibility
FROM user_indexes
WHERE table_name IN ('CUSTOMERS', 'PRODUCTS', 'ORDERS', 'ORDER_ITEMS')
ORDER BY table_name, index_name;
```

### 10.4. Kiểm tra dữ liệu orphan

Foreign key đã enable/validate sẽ ngăn nhiều trường hợp orphan. Dù vậy, truy vấn đối soát hữu ích sau import hoặc migration:

```sql
SELECT COUNT(*) AS orphan_order_items
FROM order_items oi
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.order_id = oi.order_id
);
```

Và kiểm tra currency:

```sql
SELECT COUNT(*) AS invalid_product_currency
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM currencies c
    WHERE c.currency_code = p.currency_code
);
```

Kết quả mong đợi của hai truy vấn là 0.

## 11. Hiểu rõ ràng buộc và hành vi xóa/cập nhật

### 11.1. PRIMARY KEY

Primary key vừa duy nhất vừa không null. Mỗi bảng nên có một khóa chính ổn định. Với `ORDER_ITEMS`, khóa ghép (`ORDER_ID`, `LINE_NO`) biểu diễn số thứ tự dòng trong một đơn.

### 11.2. FOREIGN KEY

Foreign key bảo đảm giá trị tham chiếu tồn tại ở bảng cha. Oracle mặc định không cho xóa hàng cha đang được tham chiếu. Điều này phù hợp với dữ liệu đơn hàng vì lịch sử phải còn nguyên khi khách hàng hoặc sản phẩm ngừng hoạt động.

Nếu nghiệp vụ cần xóa dữ liệu cá nhân, hãy thiết kế quy trình anonymization/retention phù hợp thay vì xóa dây chuyền đơn hàng và chi tiết giao dịch.

### 11.3. UNIQUE

Unique constraint bảo đảm không có hai giá trị trùng theo tập cột. Oracle cho phép nhiều `NULL` trong unique constraint theo semantics của Oracle; nếu cột phải có giá trị thì kết hợp `NOT NULL` như ví dụ email và SKU.

### 11.4. CHECK

Check constraint phù hợp cho quy tắc trên chính hàng đó như `quantity > 0`, `unit_price >= 0` hoặc trạng thái thuộc danh sách. Trong Oracle, biểu thức check cho kết quả UNKNOWN do `NULL` không làm constraint thất bại; vì vậy cần `NOT NULL` riêng khi giá trị bắt buộc.

Không đặt quy tắc liên bảng hoặc truy vấn dữ liệu khác vào check constraint. Dùng FK, unique, trigger có kiểm soát hoặc logic transaction/service tùy loại quy tắc.

### 11.5. Trạng thái đơn hàng

`CHECK` chỉ giới hạn tập giá trị, không kiểm soát thứ tự chuyển trạng thái. Ví dụ, đơn `CANCELLED` không nên chuyển lại `SHIPPED` nếu nghiệp vụ cấm. Quy tắc chuyển trạng thái cần được thực hiện trong service hoặc stored procedure, có kiểm soát concurrency và transaction.

## 12. Tạo đơn hàng trong một transaction

Một thao tác tạo đơn thường cần:

1. Kiểm tra khách hàng tồn tại và còn hoạt động.
2. Kiểm tra sản phẩm tồn tại, đang bán và giá/currency phù hợp.
3. Tạo header `ORDERS`.
4. Tạo từng dòng `ORDER_ITEMS` với giá snapshot.
5. Cập nhật tồn kho hoặc ghi nhận reservation nếu có.
6. Commit toàn bộ hoặc rollback khi bất kỳ bước bắt buộc nào thất bại.

Nếu ứng dụng Java/JDBC, transaction boundary nên bao trùm header và mọi line. Không commit header trước rồi mới insert lines nếu nghiệp vụ yêu cầu đơn phải có chi tiết đầy đủ.

Ví dụ PL/SQL minh họa tạo header và hai dòng trong một transaction block (ID được lấy bằng sequence):

```sql
DECLARE
    l_order_id    orders.order_id%TYPE;
    l_customer_id customers.customer_id%TYPE;
    l_product_id  products.product_id%TYPE;
    l_price       products.unit_price%TYPE;
BEGIN
    SELECT customer_id
    INTO l_customer_id
    FROM customers
    WHERE email = 'an@example.com';

    INSERT INTO orders (
        order_number, customer_id, currency_code,
        order_status, shipping_address
    )
    VALUES (
        'ORD-2026-0003', l_customer_id, 'USD',
        'PENDING', '12 Nguyen Hue, Ho Chi Minh City'
    )
    RETURNING order_id INTO l_order_id;

    SELECT product_id, unit_price
    INTO l_product_id, l_price
    FROM products
    WHERE sku = 'KB-001'
      AND is_active = 'Y';

    INSERT INTO order_items (
        order_id, line_no, product_id,
        quantity, unit_price, discount_amount
    )
    VALUES (
        l_order_id, 1, l_product_id,
        1, l_price, 0
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
```

Trigger `ORDERS_BIR` cấp `ORDER_ID` trước khi insert nên `RETURNING` nhận được ID đã sinh. Khối ví dụ chỉ tạo một dòng hàng để minh họa. Với ứng dụng nhiều request đồng thời, dùng bind parameter và transaction manager/JDBC thay vì ghép dữ liệu vào chuỗi SQL.

Nếu thủ tục được gọi bên trong transaction do ứng dụng quản lý, cần thống nhất ai sở hữu commit/rollback. Stored procedure không nên tự commit nếu caller cần kết hợp thao tác này với các thao tác khác trong một transaction lớn.

## 13. Đồng bộ sequence sau khi import dữ liệu có ID tường minh

Khi import hoặc nạp dữ liệu từ nguồn có sẵn ID, sequence có thể thấp hơn `MAX(ID)` trong bảng. Nếu trigger tiếp tục lấy `NEXTVAL`, insert mới có thể va chạm primary key.

Kiểm tra:

```sql
SELECT MAX(customer_id) AS max_customer_id FROM customers;
SELECT MAX(product_id)  AS max_product_id  FROM products;
SELECT MAX(order_id)    AS max_order_id    FROM orders;
```

Sau đó đồng bộ sequence bằng quy trình DBA có kiểm soát. Không sửa trực tiếp dictionary table. Với sequence hiện hữu, có thể điều chỉnh increment tạm thời tới giá trị mong muốn rồi trả `INCREMENT BY` về 1, hoặc tạo lại sequence theo quy trình phù hợp. Cần dừng writer trong lúc đồng bộ để tránh race condition.

Với Oracle hỗ trợ identity, cách quản lý sequence nội bộ có khác biệt; hãy dùng hướng dẫn Oracle tương ứng thay vì áp dụng thủ thuật sequence/trigger bên ngoài.

## 14. Triển khai schema bằng migration script

### 14.1. Tách DDL và seed data

Một cấu trúc thư mục migration có thể như sau:

```text
db/migration/
  V001__create_currencies.sql
  V002__create_customers.sql
  V003__create_products.sql
  V004__create_orders.sql
  V005__create_order_items.sql
  V006__create_sequences_and_triggers.sql
  V007__create_indexes_and_views.sql
  R__reference_data.sql
```

Tên file và cú pháp phụ thuộc Flyway/Liquibase được dự án chọn. Chia migration theo thứ tự phụ thuộc giúp dễ review, kiểm tra và xác định thay đổi nào đã được áp dụng.

### 14.2. DDL trong Oracle có implicit commit

Oracle thực hiện implicit commit trước và sau nhiều DDL statement. Vì vậy, không giả định `ROLLBACK` có thể hoàn tác `CREATE TABLE`, `CREATE SEQUENCE`, `CREATE TRIGGER` hoặc `ALTER TABLE` như DML. Công cụ migration cần quản lý trạng thái và cách phục hồi riêng cho DDL.

### 14.3. Tạo user và quyền

DBA có thể tạo schema owner, cấp quota tablespace và các quyền tạo đối tượng cần thiết. Ví dụ minh họa, phải điều chỉnh tablespace/password theo chuẩn tổ chức:

```sql
CREATE USER order_app IDENTIFIED BY "use-secret-manager-instead";
GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE,
      CREATE TRIGGER, CREATE VIEW TO order_app;
ALTER USER order_app QUOTA 500M ON app_data;
```

Mật khẩu trong ví dụ chỉ là placeholder và không được dùng thật. Không cấp quyền quá rộng như `DBA` hoặc `UNLIMITED TABLESPACE` chỉ để chạy migration. Tách schema owner dùng triển khai khỏi runtime account nếu kiến trúc bảo mật yêu cầu.

## 15. Các lỗi thường gặp

| Lỗi | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ORA-00955: name is already used` | Bảng, sequence, index hoặc trigger cùng tên đã tồn tại. | Kiểm tra object hiện có; dùng migration versioning thay vì chạy lại script tùy tiện. |
| `ORA-00942: table or view does not exist` | Tạo sai thứ tự, sai schema hoặc thiếu quyền. | Xác nhận owner, current schema và object đã tạo. |
| `ORA-02270` | Cột tham chiếu của FK không có unique/primary key phù hợp. | Tạo PK/UNIQUE ở bảng cha trước khi tạo FK. |
| `ORA-02291` | Insert hàng con tham chiếu khóa cha không tồn tại. | Tạo dữ liệu cha trước hoặc sửa ID tham chiếu. |
| `ORA-02292` | Xóa hàng cha đang có hàng con tham chiếu. | Giữ lịch sử, xóa theo quy trình nghiệp vụ hoặc xử lý dữ liệu con có kiểm soát. |
| `ORA-00001` | Vi phạm primary key/unique. | Kiểm tra duplicate email, SKU, order number hoặc sequence lệch. |
| `ORA-01400` | Insert thiếu cột `NOT NULL`. | Bổ sung giá trị hoặc default phù hợp. |
| `ORA-02290` | Vi phạm check constraint. | Kiểm tra status, quantity, price, discount và giá trị NULL. |
| `ORA-04098` | Trigger INVALID hoặc revalidation thất bại. | Xem `USER_ERRORS`, sửa trigger và compile lại. |
| `ORA-04091` | Mutating table trong row trigger. | Không truy vấn lại bảng đang bị thay đổi từ row trigger; chuyển logic sang thiết kế phù hợp. |
| `ORA-01031` | Thiếu quyền tạo object hoặc chạy package. | Cấp quyền tối thiểu từ DBA theo nhu cầu thực tế. |

Khi trigger chỉ lấy `NEXTVAL` thì không cần query lại bảng đang được insert, do đó tránh được lỗi mutating table. Không mở rộng trigger thành nơi chứa toàn bộ logic nghiệp vụ phức tạp.

## 16. Bài tập thực hành

Sau khi chạy schema và dữ liệu mẫu, thực hiện các bài tập sau:

1. Thêm một khách hàng mới và xác nhận trigger tự sinh `CUSTOMER_ID`.
2. Thêm một sản phẩm VND và một sản phẩm USD; xác nhận currency phải tồn tại.
3. Tạo đơn hàng có hai dòng hàng; lưu đơn giá snapshot.
4. Thử insert dòng hàng với `QUANTITY = 0`; xác nhận check constraint từ chối.
5. Thử insert `ORDER_STATUS = 'UNKNOWN'`; xác nhận check constraint từ chối.
6. Thử tạo hai khách hàng cùng email; xác nhận unique constraint từ chối.
7. Thử xóa sản phẩm đã có trong `ORDER_ITEMS`; xác nhận foreign key bảo vệ lịch sử.
8. Cập nhật giá catalog rồi kiểm tra đơn hàng cũ vẫn giữ `ORDER_ITEMS.UNIT_PRICE`.
9. Viết truy vấn doanh thu theo sản phẩm và currency; không cộng lẫn USD với VND.
10. Thử dùng `orders_seq.NEXTVAL` trực tiếp và kiểm tra `CURRVAL` trong cùng session.
11. Tạo thêm một view hiển thị khách hàng, số đơn và tổng giá trị theo currency.
12. Viết một migration mới thêm cột `CANCEL_REASON` và ràng buộc phù hợp cho đơn đã hủy.

## 17. Checklist xác nhận schema sau khi tạo

Các truy vấn dưới đây dùng để xác nhận trạng thái object và dữ liệu sau khi thực thi script:

```sql
SELECT table_name
FROM user_tables
WHERE table_name IN (
    'CURRENCIES', 'CUSTOMERS', 'PRODUCTS', 'ORDERS', 'ORDER_ITEMS'
)
ORDER BY table_name;
```

```sql
SELECT sequence_name, increment_by, cache_size, cycle_flag
FROM user_sequences
WHERE sequence_name IN ('CUSTOMERS_SEQ', 'PRODUCTS_SEQ', 'ORDERS_SEQ')
ORDER BY sequence_name;
```

```sql
SELECT trigger_name, table_name, status
FROM user_triggers
WHERE trigger_name IN ('CUSTOMERS_BIR', 'PRODUCTS_BIR', 'ORDERS_BIR')
ORDER BY trigger_name;
```

```sql
SELECT 'CUSTOMERS' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL
SELECT 'PRODUCTS', COUNT(*) FROM products
UNION ALL
SELECT 'ORDERS', COUNT(*) FROM orders
UNION ALL
SELECT 'ORDER_ITEMS', COUNT(*) FROM order_items;
```

Schema hoàn tất khi các bảng, constraint, sequence, trigger, index và view tồn tại đúng trạng thái; dữ liệu mẫu liên kết được; truy vấn tổng hợp trả kết quả hợp lý; và các thao tác vi phạm quy tắc bị database từ chối.

## Kết luận

Một schema quản lý đơn hàng cần tách rõ khách hàng, sản phẩm, header đơn hàng và các dòng hàng. Primary key, foreign key, unique, check và not null bảo vệ tính toàn vẹn; sequence kết hợp trigger giúp sinh ID an toàn khi nhiều session insert đồng thời. Dữ liệu mẫu cho thấy cách tạo các bản ghi cha trước, sau đó tạo đơn và dòng hàng với giá snapshot. Khi triển khai thực tế, cần quản lý DDL bằng migration version hóa, kiểm tra quyền tối thiểu, giữ nguyên lịch sử đơn hàng và tính tổng theo từng loại tiền tệ. Schema chỉ thực sự đáng tin cậy khi các constraint được xác nhận và các truy vấn/transaction nghiệp vụ chạy đúng trên Oracle.
