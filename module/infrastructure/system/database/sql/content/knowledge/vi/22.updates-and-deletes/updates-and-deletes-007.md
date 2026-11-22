# Xóa theo quan hệ phụ thuộc và tác động của khóa ngoại trong SQL

Trong cơ sở dữ liệu quan hệ, một dòng thường không tồn tại độc lập. Một **khách hàng** có thể có nhiều **đơn hàng**; mỗi đơn hàng có các **dòng chi tiết**, **thanh toán** hoặc **phiếu hỗ trợ**. Vì vậy, thao tác xóa một khách hàng không chỉ là câu lệnh `DELETE FROM customers WHERE customer_id = ...`. Nó đặt ra một câu hỏi quan trọng:

> Những dòng đang **tham chiếu đến khách hàng**, trực tiếp hoặc gián tiếp, sẽ bị xử lý thế nào khi dòng khách hàng bị xóa?

**Khóa ngoại (foreign key – FK)** định nghĩa mối quan hệ giữa bảng con và bảng cha, đồng thời có thể quyết định hành vi khi **khóa được tham chiếu** bị xóa. Tùy ràng buộc, hệ quản trị có thể **từ chối xóa**, **tự xóa các dòng phụ thuộc**, **đặt khóa ngoại về `NULL`** hoặc **đặt về một giá trị mặc định hợp lệ**.

Bài học thuộc chương **Cập nhật và xóa**, module **Database SQL**. Các ví dụ thực hành dùng **PostgreSQL**, nhấn mạnh việc **xem trước tác động**, **xóa đúng thứ tự**, **giao dịch an toàn** và **phân biệt chính sách của các khóa ngoại khác nhau**. Những điểm có thể khác giữa các hệ quản trị được ghi rõ.

## 1. Nhìn từ mô hình dữ liệu: bảng cha, bảng con và khóa ngoại

Giả sử có ba bảng:

```text
customers
  customer_id (PK)
       │
       │ orders.customer_id (FK)
       ▼
orders
  order_id (PK)
  customer_id (FK)
       │
       │ order_items.order_id (FK)
       ▼
order_items
  item_id (PK)
  order_id (FK)
```

- `customers` là **bảng cha** đối với `orders`.
- `orders` là **bảng con** đối với `customers`, đồng thời là **bảng cha** đối với `order_items`.
- `order_items` là bảng con của `orders`.
- `orders.customer_id` tham chiếu `customers.customer_id`.
- `order_items.order_id` tham chiếu `orders.order_id`.

Nếu có dòng đơn `(order_id = 101, customer_id = 1)`, nó chỉ hợp lệ khi khách hàng `customer_id = 1` tồn tại, trừ những ngoại lệ cho phép theo cấu hình ràng buộc và trạng thái giao dịch. Hệ quản trị dùng khóa ngoại để ngăn quan hệ trở thành **dòng mồ côi** (*orphan row*).

### 1.1. Xóa cha khác xóa con

Giả sử:

```text
Khách An (customer_id = 1)
 ├─ Đơn 101
 │   ├─ Chi tiết 1001
 │   ├─ Chi tiết 1002
 │   └─ Thanh toán 501
 └─ Đơn 102
     └─ Chi tiết 1003
```

Nếu xóa **chi tiết 1001**, không nhất thiết ảnh hưởng đến đơn 101 hoặc khách An: bạn đang xóa dòng **con**.

Nếu xóa **đơn 101**, việc xóa tác động tới các dòng chi tiết và thanh toán có FK trỏ tới đơn 101. Cách xử lý phụ thuộc **chính sách `ON DELETE` của từng FK**.

Nếu xóa **khách An**, các đơn 101 và 102 tham chiếu khách hàng; thao tác có thể bị chặn **trước khi** cần xét các dòng phụ thuộc sâu hơn.

### 1.2. Chính sách nằm ở khóa ngoại phía con

Ví dụ:

```sql
CREATE TABLE example_parent (
    id INTEGER PRIMARY KEY
);

CREATE TABLE example_child (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES example_parent(id)
        ON DELETE CASCADE
);
```

`ON DELETE CASCADE` được khai báo **ở cột/ràng buộc FK của bảng con**. Ý nghĩa là:

> Khi xóa dòng `example_parent` mà `parent_id` đang tham chiếu, hệ quản trị tự xóa những dòng `example_child` tương ứng.

Nó **không** có nghĩa xóa một dòng `example_child` sẽ tự xóa `example_parent`. Hướng tác động là **từ đối tượng được tham chiếu (cha) đến đối tượng đang tham chiếu (con)** khi có thao tác xóa cha.

### 1.3. Một bảng có thể vừa là con vừa là cha

`orders` là con của `customers`, nhưng là cha của `order_items`. Vì vậy, để xóa một khách có đơn, bạn có thể cần xử lý một **chuỗi phụ thuộc nhiều cấp**.

Không có quy tắc “chỉ kiểm tra một cấp”. Xóa một dòng có thể kích hoạt hiệu ứng theo nhiều cạnh trong đồ thị quan hệ; đồng thời, **một FK với chính sách chặn** ở bất cứ cấp liên quan nào có thể khiến thao tác bị từ chối.

## 2. Năm chính sách ON DELETE thường gặp

Những lựa chọn phổ biến:

| Chính sách | Khi xóa dòng cha đang được tham chiếu | Kết quả chính |
|---|---|---|
| `NO ACTION` | Không tự sửa dòng con; kiểm tra ràng buộc theo thời điểm áp dụng | Thường **từ chối** nếu còn tham chiếu; ở DBMS hỗ trợ deferrable có thể hoãn kiểm tra |
| `RESTRICT` | Chặn xóa cha khi còn dòng con tham chiếu | **Từ chối ngay** theo ngữ nghĩa hạn chế |
| `CASCADE` | Tự xóa các dòng con tham chiếu | **Xóa lan truyền** |
| `SET NULL` | Đặt cột FK của dòng con thành `NULL` | **Giữ dòng con, bỏ liên kết** |
| `SET DEFAULT` | Đặt cột FK của dòng con về giá trị mặc định | **Giữ dòng con, chuyển liên kết theo default**, nếu default hợp lệ |

Những lựa chọn này không “tốt” hoặc “xấu” tuyệt đối: chúng phản ánh **vòng đời của dữ liệu**.

Ví dụ:

- **Thanh toán** có thể cần giữ để đối soát, vì vậy thường không nên tự xóa theo đơn nếu chưa có chính sách rõ.
- **Dòng chi tiết đơn hàng** có thể được thiết kế phụ thuộc vòng đời đơn hàng, phù hợp `CASCADE` trong một số hệ thống.
- **Phiếu hỗ trợ** có thể cần giữ nhưng không còn liên kết với khách hàng, phù hợp `SET NULL` nếu nghiệp vụ cho phép.
- **Thẻ gắn khách hàng** chỉ có ý nghĩa khi khách còn tồn tại, có thể dùng `CASCADE`.

**Lưu ý:** chọn `CASCADE` không tự tạo chính sách lưu trữ hoặc xóa dữ liệu hợp pháp. Cần cân nhắc kiểm toán, lưu trữ, bảo vệ dữ liệu, khôi phục và yêu cầu nghiệp vụ trước khi thiết kế.

## 3. Mô hình thực hành PostgreSQL với các chính sách khác nhau

Ta tạo sáu bảng để thấy rõ tác động thực tế:

```text
lesson278_customers
       │
       ├── RESTRICT ──► lesson278_orders
       │                       │
       │                       ├── CASCADE ──► lesson278_order_items
       │                       │
       │                       └── RESTRICT ─► lesson278_payments
       │
       ├── SET NULL ──► lesson278_support_tickets
       │
       └── CASCADE ───► lesson278_customer_tags
```

Chữ trên các mũi tên là chính sách `ON DELETE` của FK **trên bảng bên phải** khi dòng cha bên trái bị xóa.

### 3.1. Tạo bảng customers

```sql
CREATE TABLE lesson278_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
```

### 3.2. Đơn hàng: RESTRICT khi xóa khách

```sql
CREATE TABLE lesson278_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    ordered_on DATE NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    CONSTRAINT lesson278_orders_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES lesson278_customers(customer_id)
        ON DELETE RESTRICT
);
```

Nếu khách có đơn hàng, lệnh xóa khách sẽ bị ngăn bởi `lesson278_orders_customer_fk`.

Câu này có ý nghĩa nghiệp vụ: **không được xóa khách khi còn đơn liên quan**, trừ khi trước đó đã xử lý đơn.

### 3.3. Dòng chi tiết: CASCADE khi xóa đơn

```sql
CREATE TABLE lesson278_order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    CONSTRAINT lesson278_items_order_fk
        FOREIGN KEY (order_id)
        REFERENCES lesson278_orders(order_id)
        ON DELETE CASCADE
);
```

Nếu xóa một đơn hợp lệ, những dòng chi tiết của đơn đó tự động bị xóa.

`CASCADE` tác động **chính xác các dòng con tham chiếu dòng cha bị xóa**; nó không xóa toàn bộ `order_items`.

### 3.4. Thanh toán: RESTRICT khi xóa đơn

```sql
CREATE TABLE lesson278_payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    paid_amount NUMERIC(12, 2) NOT NULL CHECK (paid_amount > 0),
    CONSTRAINT lesson278_payments_order_fk
        FOREIGN KEY (order_id)
        REFERENCES lesson278_orders(order_id)
        ON DELETE RESTRICT
);
```

Một đơn có thanh toán không được xóa trực tiếp. Phải có **quyết định nghiệp vụ** về thanh toán trước: có thể cần giữ bản ghi, hoàn tiền, lưu trữ, chuyển sang thực thể phù hợp, hoặc không cho xóa đơn.

Trong bài thực hành, ta sẽ dùng **một giao dịch thử với `ROLLBACK`** để minh họa thứ tự xóa. Điều đó không phải lời khuyên xóa thanh toán của hệ thống sản xuất.

### 3.5. Phiếu hỗ trợ: SET NULL khi xóa khách

```sql
CREATE TABLE lesson278_support_tickets (
    ticket_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    subject VARCHAR(200) NOT NULL,
    CONSTRAINT lesson278_tickets_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES lesson278_customers(customer_id)
        ON DELETE SET NULL
);
```

Cột `customer_id` phải **cho phép `NULL`** nếu dự kiến dùng `SET NULL`.

Xóa khách liên quan làm `customer_id` của phiếu trở thành `NULL`, nhưng dòng phiếu và `subject` vẫn tồn tại.

### 3.6. Thẻ khách hàng: CASCADE khi xóa khách

```sql
CREATE TABLE lesson278_customer_tags (
    tag_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    tag_name VARCHAR(50) NOT NULL,
    CONSTRAINT lesson278_tags_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES lesson278_customers(customer_id)
        ON DELETE CASCADE
);
```

Khi xóa khách, các dòng gắn thẻ của khách đó bị xóa tự động.

### 3.7. Tạo dữ liệu

```sql
INSERT INTO lesson278_customers (
    customer_id, customer_name, is_active
)
VALUES
    (1, 'An',   TRUE),
    (2, 'Bình', TRUE),
    (3, 'Chi',  TRUE),
    (4, 'Dũng', TRUE),
    (5, 'Hà',   TRUE);

INSERT INTO lesson278_orders (
    order_id, customer_id, ordered_on, amount
)
VALUES
    (101, 1, DATE '2026-11-01', 120000),
    (102, 1, DATE '2026-11-02', 200000),
    (103, 2, DATE '2026-11-03',  90000),
    (104, 3, DATE '2026-11-04',  80000),
    (105, 5, DATE '2026-11-05',  70000);

INSERT INTO lesson278_order_items (
    item_id, order_id, product_name, quantity
)
VALUES
    (1001, 101, 'Sách SQL', 2),
    (1002, 101, 'Bút', 1),
    (1003, 102, 'Bàn phím', 1),
    (1004, 103, 'Chuột', 1),
    (1005, 104, 'Vở', 4),
    (1006, 105, 'Sổ', 1);

INSERT INTO lesson278_payments (
    payment_id, order_id, paid_amount
)
VALUES
    (501, 101, 120000),
    (502, 103,  90000);

INSERT INTO lesson278_support_tickets (
    ticket_id, customer_id, subject
)
VALUES
    (901, 1, 'Hỗ trợ đơn hàng'),
    (902, 2, 'Hỏi về thanh toán'),
    (903, 4, 'Đổi thông tin');

INSERT INTO lesson278_customer_tags (
    tag_id, customer_id, tag_name
)
VALUES
    (701, 1, 'VIP'),
    (702, 1, 'ONLINE'),
    (703, 2, 'NEW'),
    (704, 4, 'TRIAL');
```

Các số ID được cố định để dễ theo dõi. Đây là **dữ liệu giả lập**, không phải thông tin khách hàng thật.

### 3.8. Bảng tóm tắt quan hệ của bộ dữ liệu

| Khách hàng | Đơn hàng | Chi tiết của các đơn | Thanh toán | Phiếu hỗ trợ | Thẻ |
|---|---|---|---|---|---|
| An (1) | 101, 102 | 1001, 1002, 1003 | 501 | 901 | 701, 702 |
| Bình (2) | 103 | 1004 | 502 | 902 | 703 |
| Chi (3) | 104 | 1005 | Không | Không | Không |
| Dũng (4) | Không | Không | Không | 903 | 704 |
| Hà (5) | 105 | 1006 | Không | Không | Không |

Bộ dữ liệu có chủ đích:

- An và Bình **có đơn có thanh toán** nên có nhiều cấp phụ thuộc chặn xóa.
- Chi và Hà có đơn nhưng **không có thanh toán**, để thử xóa đơn có cascade chi tiết.
- Dũng **không có đơn**, nhưng có phiếu hỗ trợ `SET NULL` và thẻ `CASCADE`.

## 4. Xóa bảng cha khi có RESTRICT: vì sao bị từ chối?

Hãy xem câu:

```sql
-- KHÔNG chạy như bước xóa thực; đây là minh họa
-- một DELETE sẽ gặp lỗi khi dữ liệu mẫu còn nguyên.
DELETE FROM lesson278_customers
WHERE customer_id = 1;
```

An có đơn 101 và 102. FK `lesson278_orders.customer_id` khai báo `ON DELETE RESTRICT`. PostgreSQL từ chối xóa khách An vì các đơn vẫn tham chiếu `customer_id = 1`.

Ý nghĩa:

> Hệ thống không thể để đơn 101, 102 vẫn chứa `customer_id = 1` trong khi dòng khách 1 đã bị xóa, vì quy tắc không cho tự hủy hay thay liên kết.

**Không có chuyện `ON DELETE RESTRICT` tự xóa đơn hoặc tự đặt `customer_id` thành `NULL`.** Nó chặn thao tác không hợp lệ.

### 4.1. Tại sao thử trong transaction vẫn có thể phải ROLLBACK?

Nếu chạy một câu `DELETE` vi phạm ràng buộc **bên trong transaction PostgreSQL**, transaction thường chuyển sang trạng thái lỗi. Các lệnh tiếp theo không chạy bình thường cho đến khi `ROLLBACK` (hoặc quay về savepoint hợp lệ).

Ví dụ chỉ để mô tả trình tự lỗi:

```sql
-- Không thực thi đoạn này nếu không muốn chủ động tạo lỗi.
BEGIN;
DELETE FROM lesson278_customers WHERE customer_id = 1;
-- Có lỗi FK: cần ROLLBACK, không tiếp tục như thể chưa lỗi.
ROLLBACK;
```

Để nghiên cứu câu SQL an toàn hơn, hãy dùng **`SELECT` xem trước phụ thuộc** trước khi thử một `DELETE` bị biết chắc sẽ lỗi.

### 4.2. Không nên tắt FK để “cho xóa chạy được”

Tắt kiểm tra khóa ngoại, tắt trigger hoặc thay cấu hình engine chỉ nhằm xóa bằng mọi giá có thể tạo **dòng mồ côi**, dữ liệu mâu thuẫn và vấn đề kiểm toán. Những thao tác như vậy chỉ có thể được cân nhắc trong quy trình quản trị/chuyển đổi có kiểm soát và cơ chế kiểm tra lại, không phải giải pháp mặc định cho một lệnh `DELETE` bị chặn.

## 5. Xóa một đơn: CASCADE và RESTRICT có thể cùng tồn tại

Đơn 101 có:

- Hai dòng `order_items`: 1001 và 1002, FK `ON DELETE CASCADE`.
- Một dòng `payments`: 501, FK `ON DELETE RESTRICT`.

Nếu chạy:

```sql
-- Sẽ bị chặn bởi thanh toán 501 khi dữ liệu mẫu còn nguyên.
DELETE FROM lesson278_orders
WHERE order_id = 101;
```

PostgreSQL phải đảm bảo **tất cả ràng buộc liên quan** cùng được giữ đúng. Không thể coi việc có `CASCADE` từ đơn sang chi tiết là đủ để xóa đơn 101. FK thanh toán vẫn chặn.

### 5.1. Đơn 102 không có thanh toán

Đơn 102 có một chi tiết 1003 nhưng không có thanh toán. Theo mô hình:

- Xóa đơn 102 **được phép**.
- Hệ quản trị tự xóa chi tiết 1003.
- Khách An vẫn còn.
- Đơn 101 và các chi tiết/thanh toán của đơn 101 vẫn còn.

Hãy thử trong transaction rồi hoàn tác:

```sql
BEGIN;

DELETE FROM lesson278_orders
WHERE order_id = 102
RETURNING order_id, customer_id;

SELECT *
FROM lesson278_order_items
WHERE order_id = 102;

SELECT *
FROM lesson278_customers
WHERE customer_id = 1;

ROLLBACK;
```

Trong transaction:

- `DELETE ... RETURNING` trả đơn 102.
- Truy vấn chi tiết đơn 102 không còn dòng nào vì `CASCADE`.
- Khách An vẫn tồn tại.

Sau `ROLLBACK`, cả đơn 102 và chi tiết 1003 trở lại trạng thái ban đầu của giao dịch thử.

**Lưu ý:** câu `DELETE ... RETURNING` trên bảng đơn chỉ trả thông tin những dòng `lesson278_orders` bị xóa trực tiếp; nó **không tự liệt kê toàn bộ chi tiết con bị cascade**. Muốn ghi nhận đầy đủ tác động, hãy xem trước hoặc có cơ chế kiểm toán thích hợp.

## 6. Xóa từ con lên cha: thứ tự phụ thuộc

Khi quan hệ cha–con dùng chính sách chặn như `RESTRICT` hoặc `NO ACTION` không hoãn kiểm tra, một chiến lược phổ biến là **xử lý dòng phụ thuộc trước, rồi xóa dòng cha**.

Với khách An:

```text
lesson278_payments (501)
          │ xóa trước, nếu nghiệp vụ cho phép
          ▼
lesson278_orders (101, 102)
          │ khi xóa đơn, items tự CASCADE
          ▼
lesson278_customers (1)
          │ khi xóa khách, tags tự CASCADE
          │                   tickets SET NULL
          ▼
       Hoàn thành
```

Không phải tất cả quan hệ đều yêu cầu xóa con thủ công. Cụ thể:

- `payments → orders`: **chặn**; trong ví dụ thực hành phải xử lý thanh toán trước.
- `order_items → orders`: **CASCADE**; tự xử lý khi xóa đơn.
- `orders → customers`: **RESTRICT**; phải xử lý đơn trước khách.
- `customer_tags → customers`: **CASCADE**; tự xóa thẻ khi xóa khách.
- `support_tickets → customers`: **SET NULL**; giữ phiếu nhưng bỏ tham chiếu.

### 6.1. Xóa bằng khóa cụ thể, không quên WHERE

Câu nguy hiểm:

```sql
-- CẢNH BÁO: xóa mọi dòng thanh toán, không dùng.
DELETE FROM lesson278_payments;
```

Muốn thao tác đúng phạm vi, phải ràng buộc với khách hàng cụ thể. Ví dụ PostgreSQL `DELETE ... USING`:

```sql
DELETE FROM lesson278_payments AS p
USING lesson278_orders AS o
WHERE p.order_id = o.order_id
  AND o.customer_id = 1;
```

Ở ví dụ này, truy vấn chỉ nhắm các thanh toán của **đơn thuộc khách 1**, không phải mọi thanh toán.

Một cách khác với `EXISTS`:

```sql
DELETE FROM lesson278_payments AS p
WHERE EXISTS (
    SELECT 1
    FROM lesson278_orders AS o
    WHERE o.order_id = p.order_id
      AND o.customer_id = 1
);
```

Hai dạng có thể đạt cùng kết quả cho quan hệ này. `DELETE ... USING` là cú pháp của PostgreSQL; hỗ trợ DELETE có JOIN ở các DBMS khác dùng cú pháp khác.

### 6.2. Đừng xóa dữ liệu thanh toán thật chỉ để “giải phóng” FK

Lệnh xóa thanh toán ở trên **chỉ phục vụ bộ dữ liệu thực hành**. Trong hệ thống sản xuất, giao dịch và thanh toán thường chịu quy tắc lưu trữ, đối soát và kiểm toán nghiêm ngặt. Nếu thanh toán phải được giữ, chính sách đúng có thể là **không xóa đơn/khách**, **lưu trữ dữ liệu** hoặc **thiết kế lại tham chiếu theo yêu cầu**, thay vì đơn giản xóa thanh toán trước.

## 7. Xem trước toàn bộ phạm vi ảnh hưởng của một yêu cầu xóa

Trước khi xóa khách An, nên kiểm tra **những dòng nào sẽ biến mất hoặc thay đổi**.

### 7.1. Đếm theo từng bảng

```sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM lesson278_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS orders_count,
    (
        SELECT COUNT(*)
        FROM lesson278_order_items AS i
        JOIN lesson278_orders AS o
            ON o.order_id = i.order_id
        WHERE o.customer_id = c.customer_id
    ) AS items_count,
    (
        SELECT COUNT(*)
        FROM lesson278_payments AS p
        JOIN lesson278_orders AS o
            ON o.order_id = p.order_id
        WHERE o.customer_id = c.customer_id
    ) AS payments_count,
    (
        SELECT COUNT(*)
        FROM lesson278_support_tickets AS t
        WHERE t.customer_id = c.customer_id
    ) AS tickets_count,
    (
        SELECT COUNT(*)
        FROM lesson278_customer_tags AS g
        WHERE g.customer_id = c.customer_id
    ) AS tags_count
FROM lesson278_customers AS c
WHERE c.customer_id = 1;
```

Với khách An:

| orders_count | items_count | payments_count | tickets_count | tags_count |
|---:|---:|---:|---:|---:|
| 2 | 3 | 1 | 1 | 2 |

Đây là **số dòng liên quan**, chưa phải kế hoạch “xóa tất cả”. Phải đọc chính sách từng FK:

| Bảng liên quan đến An | Số dòng | Tác động theo mô hình nếu xóa khách thành công sau xử lý chặn |
|---|---:|---|
| `lesson278_orders` | 2 | Phải được xử lý/xóa trước do `RESTRICT` |
| `lesson278_order_items` | 3 | Tự xóa khi xóa các đơn liên quan |
| `lesson278_payments` | 1 | Chặn xóa đơn; cần quyết định riêng |
| `lesson278_support_tickets` | 1 | Giữ phiếu, đổi `customer_id` thành `NULL` |
| `lesson278_customer_tags` | 2 | Tự xóa khi xóa khách |

### 7.2. Liệt kê khóa cụ thể trước khi thao tác

```sql
SELECT
    o.order_id,
    o.customer_id,
    o.amount
FROM lesson278_orders AS o
WHERE o.customer_id = 1
ORDER BY o.order_id;
```

Kết quả: đơn 101 và 102.

```sql
SELECT
    p.payment_id,
    p.order_id,
    p.paid_amount
FROM lesson278_payments AS p
JOIN lesson278_orders AS o
    ON o.order_id = p.order_id
WHERE o.customer_id = 1
ORDER BY p.payment_id;
```

Kết quả: thanh toán 501.

```sql
SELECT
    i.item_id,
    i.order_id,
    i.product_name
FROM lesson278_order_items AS i
JOIN lesson278_orders AS o
    ON o.order_id = i.order_id
WHERE o.customer_id = 1
ORDER BY i.item_id;
```

Kết quả: 1001, 1002, 1003.

Nên có bước xác nhận **khóa và số dòng** trước khi chạy `DELETE` trên dữ liệu có giá trị. Điều kiện `WHERE customer_id = 1` phù hợp dữ liệu thực hành, nhưng trong sản xuất cần đảm bảo `customer_id` đến từ yêu cầu đã được xác thực và có quyền thực hiện.

### 7.3. Một bảng có thể được tham chiếu qua nhiều đường

Trong mô hình lớn, cùng một đối tượng có thể được tham chiếu từ nhiều bảng khác nhau; việc chỉ đếm con trực tiếp là chưa đủ. Ví dụ một đơn còn có **vận đơn**, **biên nhận**, **lịch sử thanh toán**, **bút toán**, **điểm thưởng**. Mỗi FK có chính sách riêng.

Khi lên kế hoạch xóa, hãy kiểm tra **đồ thị phụ thuộc đầy đủ**, không chỉ các bảng mà truy vấn hiện tại đang JOIN. Một FK chặn ở nhánh ít được chú ý vẫn có thể làm lệnh xóa thất bại.

## 8. Thực hành xóa nhiều cấp trong một transaction rồi ROLLBACK

Ta thử xóa khách An cùng những dòng liên quan theo **chính sách của schema**, nhưng dùng `ROLLBACK` để giữ nguyên dữ liệu mẫu.

**Cảnh báo:** đây là thao tác xóa thật **bên trong transaction thực hành**. Chỉ chạy trên database thử nghiệm. Dù `ROLLBACK` hoàn tác dữ liệu transactional, các trigger có tác dụng bên ngoài hệ quản trị hoặc hệ thống tích hợp có thể có hành vi khác. Đừng dùng transaction thử kiểu này với dữ liệu sản xuất khi chưa hiểu đầy đủ tác dụng phụ.

```sql
BEGIN;

-- Bước 1: xử lý thanh toán của các đơn thuộc khách An.
-- Trong dữ liệu mẫu, nó xóa payment_id = 501.
DELETE FROM lesson278_payments AS p
USING lesson278_orders AS o
WHERE p.order_id = o.order_id
  AND o.customer_id = 1
RETURNING p.payment_id, p.order_id;

-- Bước 2: xóa hai đơn của An.
-- Items của đơn 101/102 tự bị xóa theo ON DELETE CASCADE.
DELETE FROM lesson278_orders
WHERE customer_id = 1
RETURNING order_id, customer_id;

-- Bước 3: không còn đơn tham chiếu An nên xóa được khách.
-- Tags 701/702 tự CASCADE; ticket 901 được SET NULL.
DELETE FROM lesson278_customers
WHERE customer_id = 1
RETURNING customer_id, customer_name;

-- Quan sát tác động trước khi hoàn tác.
SELECT
    ticket_id,
    customer_id,
    subject
FROM lesson278_support_tickets
WHERE ticket_id = 901;

SELECT COUNT(*) AS remaining_items_of_deleted_orders
FROM lesson278_order_items
WHERE order_id IN (101, 102);

SELECT COUNT(*) AS remaining_tags_of_an
FROM lesson278_customer_tags
WHERE customer_id = 1;

ROLLBACK;
```

### 8.1. Kết quả dự kiến trong transaction

Sau ba lệnh xóa, **trước `ROLLBACK`**:

- Khách An `customer_id = 1` không còn trong `lesson278_customers`.
- Các đơn 101 và 102 không còn.
- Chi tiết 1001, 1002, 1003 bị xóa vì `CASCADE` từ đơn.
- Thanh toán 501 đã được xóa thủ công.
- Thẻ 701, 702 bị xóa vì `CASCADE` từ khách.
- Phiếu 901 **vẫn còn**, nhưng `customer_id = NULL` vì `SET NULL`.
- Các khách Bình, Chi, Dũng, Hà và những dòng liên quan không thuộc phạm vi xóa vẫn còn.

### 8.2. Sau ROLLBACK

`ROLLBACK` hoàn tác tất cả các thay đổi transactional của ba câu `DELETE` và những tác động FK phát sinh trong giao dịch:

- Khách An trở lại.
- Đơn 101, 102 và các chi tiết của chúng trở lại.
- Thanh toán 501 trở lại.
- Thẻ 701, 702 trở lại.
- Phiếu 901 lại có `customer_id = 1`.

Trong PostgreSQL, thao tác FK cascade/set-null là một phần của xử lý giao dịch tương ứng, nên được hoàn tác cùng giao dịch.

### 8.3. Vì sao không xóa khách trước?

`orders.customer_id` dùng `RESTRICT`, nên xóa khách trước sẽ bị chặn bởi các đơn còn tồn tại. `payments.order_id` cũng dùng `RESTRICT`, nên xóa đơn 101 trước khi xử lý thanh toán 501 cũng bị chặn.

Thứ tự trong giao dịch thử phản ánh **chiều phụ thuộc của các FK chặn xóa**. Những quan hệ `CASCADE`/`SET NULL` được DBMS xử lý theo ràng buộc đã khai báo.

## 9. Ví dụ xóa một khách không có đơn: CASCADE và SET NULL trực tiếp

Dũng (khách 4) không có đơn, nhưng có:

- Phiếu hỗ trợ 903: `ON DELETE SET NULL`.
- Thẻ 704: `ON DELETE CASCADE`.

Không có đơn nào chặn xóa khách này.

```sql
BEGIN;

DELETE FROM lesson278_customers
WHERE customer_id = 4
RETURNING customer_id, customer_name;

SELECT ticket_id, customer_id
FROM lesson278_support_tickets
WHERE ticket_id = 903;

SELECT *
FROM lesson278_customer_tags
WHERE tag_id = 704;

ROLLBACK;
```

Kết quả trong transaction:

- `DELETE ... RETURNING` trả Dũng.
- Phiếu 903 vẫn tồn tại với `customer_id NULL`.
- Thẻ 704 không còn.
- Không có đơn hoặc thanh toán nào bị xóa bởi yêu cầu này.

Sau `ROLLBACK`, bộ dữ liệu mẫu trở lại trạng thái ban đầu.

**Chú ý:** “khách không có đơn” không có nghĩa “xóa khách không có tác động phụ”. Các bảng phiếu và thẻ vẫn chịu ảnh hưởng theo chính sách FK.

## 10. ON DELETE CASCADE: tác động lan truyền qua nhiều cấp

Với chuỗi:

```text
A (cha)
  └── B (con của A, ON DELETE CASCADE)
        └── C (con của B, ON DELETE CASCADE)
```

Xóa dòng A có thể làm DBMS tự xóa các dòng B liên quan; việc xóa B sau đó làm xóa các dòng C liên quan. Đây là **xóa lan truyền nhiều cấp**.

Nhưng nếu:

```text
A --CASCADE--> B --RESTRICT--> C
```

và B có C đang tham chiếu, thao tác xóa A có thể bị từ chối vì việc xóa B phải đáp ứng FK từ C. Không nên hiểu `CASCADE` ở cấp đầu là quyền vượt qua mọi FK ở cấp sau.

### 10.1. CASCADE xóa theo quan hệ tham chiếu, không phải theo tên giống nhau

Giả sử bảng `order_items.order_id` tham chiếu `orders.order_id`. Khi xóa đơn 102, chỉ những dòng item có `order_id = 102` bị cascade. Một item có `product_name` giống ở đơn 103 **không bị xóa chỉ vì trùng tên sản phẩm**.

FK dùng **giá trị khóa được tham chiếu**, không dùng suy đoán dựa trên các cột mô tả.

### 10.2. CASCADE không phù hợp với mọi loại dữ liệu

Những ví dụ cần cân nhắc trước khi bật cascade:

- Dòng giao dịch tài chính/bút toán phải lưu theo chính sách kiểm toán.
- Bằng chứng giao nhận, hóa đơn đã phát hành hoặc hồ sơ pháp lý.
- Sự kiện được nhiều hệ thống bên ngoài tham chiếu qua mã nghiệp vụ.
- Lịch sử hoạt động cần phục vụ điều tra sự cố.
- Dữ liệu cần giữ trong thời hạn bắt buộc.

Ở những hệ thống này, FK `RESTRICT` hoặc một mô hình lưu trữ khác có thể phù hợp hơn. **Thiết kế vòng đời dữ liệu trước, rồi mới chọn hành vi ON DELETE**.

## 11. ON DELETE SET NULL: giữ con, bỏ liên kết

Với `lesson278_support_tickets`, một phiếu hỗ trợ vẫn có thể tồn tại sau khi khách bị xóa.

```sql
CONSTRAINT lesson278_tickets_customer_fk
    FOREIGN KEY (customer_id)
    REFERENCES lesson278_customers(customer_id)
    ON DELETE SET NULL
```

Khi xóa khách:

```text
Trước:
ticket_id = 903
customer_id = 4
subject = 'Đổi thông tin'

Sau:
ticket_id = 903
customer_id = NULL
subject = 'Đổi thông tin'
```

### 11.1. Cột FK phải chấp nhận NULL

Nếu bảng con định nghĩa:

```sql
customer_id INTEGER NOT NULL
```

mà FK dùng `ON DELETE SET NULL`, hành động đặt `customer_id = NULL` sẽ xung đột với `NOT NULL` khi được thực thi cho dòng con liên quan. DBMS có thể cho tạo một số tổ hợp schema nhưng phép xóa sẽ lỗi lúc cần thực hiện. Thiết kế đúng là làm cho kiểu ràng buộc **phù hợp với trạng thái “không còn liên kết”**.

### 11.2. NULL không đồng nghĩa với xóa dữ liệu cá nhân hoàn toàn

Phiếu vẫn có thể chứa thông tin nhận dạng trong `subject`, mô tả hoặc tệp đính kèm. `SET NULL` chỉ loại bỏ **liên kết FK**; nó không bảo đảm ẩn danh hóa toàn bộ nội dung hoặc đáp ứng mọi yêu cầu riêng tư.

Nếu nghiệp vụ cần giữ phiếu hỗ trợ nhưng xóa thông tin nhận dạng, phải xác định **toàn bộ trường và hệ thống liên quan** cần xử lý.

### 11.3. Truy vấn sau khi SET NULL

```sql
SELECT ticket_id, subject
FROM lesson278_support_tickets
WHERE customer_id IS NULL;
```

Sau khi xóa thành công một khách có phiếu và chưa rollback, câu này tìm các phiếu hiện **không liên kết khách hàng**. Nhưng không thể suy ra mọi phiếu `customer_id IS NULL` đều do một thao tác xóa sinh ra; nguồn tạo phiếu có thể cho phép `NULL` ngay từ đầu.

## 12. ON DELETE SET DEFAULT: chuyển về giá trị mặc định phải hợp lệ

`SET DEFAULT` không đơn giản là “lưu tạm dữ liệu chưa có cha”. Giá trị mặc định sau khi thay liên kết vẫn phải tuân thủ FK.

Để minh họa, ta tạo mô hình **nhóm phân loại**. Có một nhóm dự phòng `group_id = 0` luôn tồn tại.

```sql
CREATE TABLE lesson278_groups (
    group_id INTEGER PRIMARY KEY,
    group_name VARCHAR(100) NOT NULL
);

CREATE TABLE lesson278_group_members (
    member_id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT lesson278_members_group_fk
        FOREIGN KEY (group_id)
        REFERENCES lesson278_groups(group_id)
        ON DELETE SET DEFAULT
);

INSERT INTO lesson278_groups (group_id, group_name)
VALUES
    (0, 'Chưa phân loại'),
    (10, 'Nhóm A');

INSERT INTO lesson278_group_members (member_id, group_id)
VALUES
    (2001, 10),
    (2002, 10);
```

Thử xóa nhóm 10:

```sql
BEGIN;

DELETE FROM lesson278_groups
WHERE group_id = 10
RETURNING group_id, group_name;

SELECT member_id, group_id
FROM lesson278_group_members
ORDER BY member_id;

ROLLBACK;
```

Trong transaction, thành viên 2001 và 2002 chuyển từ `group_id = 10` sang `group_id = 0`, vì `0` là default và **có tồn tại** trong bảng cha.

### 12.1. Điều gì xảy ra nếu default không có cha?

Nếu `DEFAULT 0` nhưng bảng `lesson278_groups` **không có dòng `group_id = 0`**, việc chuyển các dòng con về 0 sẽ vi phạm FK. `SET DEFAULT` **không bỏ qua** tính toàn vẹn tham chiếu.

Ngay cả khi giá trị default hợp lệ ban đầu, chính sách vận hành cần đảm bảo dòng cha dự phòng không bị xóa ngoài ý muốn.

### 12.2. Không nên dùng “nhóm mặc định” nếu sai nghiệp vụ

Nếu việc xóa một dự án không được phép tự chuyển toàn bộ công việc sang “Dự án khác”, thì `SET DEFAULT` có thể làm sai quan hệ trách nhiệm. Phải chọn giá trị mặc định đại diện cho một trạng thái **có ý nghĩa được quy định**, không chỉ để vượt qua lỗi khóa ngoại.

## 13. RESTRICT và NO ACTION không hoàn toàn đồng nghĩa trong PostgreSQL

Nhiều hệ thống dùng `NO ACTION` làm mặc định khi không ghi `ON DELETE`. Trong PostgreSQL, điểm khác quan trọng giữa `NO ACTION` và `RESTRICT` là **khả năng hoãn kiểm tra ràng buộc**.

### 13.1. NO ACTION mặc định vẫn thường bị kiểm tra ngay

Ví dụ:

```sql
FOREIGN KEY (parent_id)
REFERENCES parent_table(id)
ON DELETE NO ACTION
```

Nếu FK **không được khai báo `DEFERRABLE`**, việc xóa cha khi con còn tham chiếu cũng bị từ chối. Đối với một câu xóa đơn giản, nó có thể trông giống `RESTRICT`.

### 13.2. NO ACTION có thể kết hợp DEFERRABLE

Ở PostgreSQL, có thể cho phép **tạm thời vi phạm FK trong một transaction**, miễn các quan hệ hợp lệ lại trước khi kiểm tra ràng buộc ở cuối giao dịch hoặc thời điểm kiểm tra được yêu cầu.

Ví dụ độc lập:

```sql
CREATE TABLE lesson278_deferred_parents (
    parent_id INTEGER PRIMARY KEY
);

CREATE TABLE lesson278_deferred_children (
    child_id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL,
    CONSTRAINT lesson278_deferred_child_fk
        FOREIGN KEY (parent_id)
        REFERENCES lesson278_deferred_parents(parent_id)
        ON DELETE NO ACTION
        DEFERRABLE INITIALLY IMMEDIATE
);

INSERT INTO lesson278_deferred_parents (parent_id)
VALUES (10);

INSERT INTO lesson278_deferred_children (child_id, parent_id)
VALUES (100, 10);
```

Bây giờ thử thao tác “xóa cha trước, xóa con sau” **trong cùng transaction**:

```sql
BEGIN;

SET CONSTRAINTS lesson278_deferred_child_fk DEFERRED;

-- Tạm thời còn child 100 tham chiếu parent 10.
DELETE FROM lesson278_deferred_parents
WHERE parent_id = 10;

-- Giải quyết tham chiếu trước khi transaction kết thúc.
DELETE FROM lesson278_deferred_children
WHERE child_id = 100;

COMMIT;
```

Ở cuối transaction, không còn dòng con tham chiếu cha đã xóa, nên quan hệ hợp lệ. Cấu hình `DEFERRABLE` và lệnh `SET CONSTRAINTS ... DEFERRED` là cơ chế cho phép xử lý trung gian như vậy.

**Lưu ý:** ví dụ này **thực sự commit phép xóa trên hai bảng thử mới tạo**. Nó chỉ nên chạy trong môi trường học tập. Nếu muốn quan sát mà không lưu, thay `COMMIT` bằng `ROLLBACK`.

### 13.3. RESTRICT không cho hoãn việc xóa theo cách này

`ON DELETE RESTRICT` trong PostgreSQL **không thể trì hoãn kiểm tra hành động RESTRICT như `NO ACTION`**. Ngay cả nếu một FK có thể liên quan tới đặc tính deferrable ở mức constraint, hành động RESTRICT khi xóa vẫn có ngữ nghĩa chặn ngay.

Điều này giúp phân biệt:

| Tình huống | `NO ACTION` | `RESTRICT` |
|---|---|---|
| FK không hoãn kiểm tra, con đang tham chiếu | Xóa cha bị chặn | Xóa cha bị chặn |
| FK khai báo deferrable và đang hoãn kiểm tra | Có thể tạm xóa cha, rồi sửa/xóa con trước khi kiểm tra | Không cho phép tạm vi phạm hành động RESTRICT theo cách này |
| Giữ tham chiếu mồ côi sau khi COMMIT | **Không được** | **Không được** |

**Deferrable không có nghĩa cho phép dữ liệu sai ở trạng thái đã commit.** Nó chỉ thay đổi **thời điểm kiểm tra**, trong các điều kiện DBMS hỗ trợ.

### 13.4. Cẩn thận với DDL và hành động ở những DBMS khác

SQL Server và MySQL/InnoDB có quy tắc kiểm tra khóa ngoại khác PostgreSQL; không nên mặc định `NO ACTION DEFERRABLE` có cùng hành vi và cú pháp trên mọi hệ. Phần cuối bài đối chiếu các điểm chính.

## 14. Xóa theo tập điều kiện qua truy vấn con hoặc JOIN

Thay vì xóa một ID cụ thể, một yêu cầu có thể là “xóa tất cả đơn chưa thanh toán được tạo trước ngày X” hoặc “xóa các dòng con thuộc những cha được chọn”.

**Trước tiên phải xác định phạm vi bằng `SELECT`.**

### 14.1. Xem trước các đơn theo khách

```sql
SELECT
    o.order_id,
    o.customer_id,
    o.ordered_on,
    o.amount
FROM lesson278_orders AS o
WHERE o.customer_id IN (1, 3)
ORDER BY o.customer_id, o.order_id;
```

Với dữ liệu mẫu, kết quả là đơn 101, 102 và 104.

Nếu muốn xóa các đơn đó, **không thể chỉ nhìn tập đơn**: đơn 101 có thanh toán 501 đang chặn xóa. Điều kiện lọc đúng chưa bảo đảm thao tác xóa hợp lệ.

### 14.2. DELETE với EXISTS

```sql
-- Minh họa cú pháp: phải xử lý các FK chặn trước khi chạy.
DELETE FROM lesson278_orders AS o
WHERE EXISTS (
    SELECT 1
    FROM lesson278_customers AS c
    WHERE c.customer_id = o.customer_id
      AND c.customer_name = 'Chi'
);
```

Điều kiện `EXISTS` kiểm tra từng đơn có khách tên Chi hay không. Trong dữ liệu mẫu, khách Chi có ID 3 và đơn 104, đơn này không có thanh toán nên có thể bị xóa; chi tiết 1005 sẽ cascade.

Tuy nhiên, `customer_name` **không phải khóa duy nhất** trong schema. Ở hệ thống có hai người trùng tên, câu truy vấn sẽ có phạm vi rộng hơn dự kiến. Trong các thao tác xóa có rủi ro, nên chọn theo **khóa ổn định đã xác thực** thay vì tên hiển thị.

### 14.3. DELETE USING trong PostgreSQL

```sql
BEGIN;

DELETE FROM lesson278_orders AS o
USING lesson278_customers AS c
WHERE o.customer_id = c.customer_id
  AND c.customer_id = 3
RETURNING o.order_id;

ROLLBACK;
```

Đây là ví dụ **xóa theo quan hệ JOIN** trong PostgreSQL. Đơn 104 bị xóa thử, item 1005 cascade, nhưng khách Chi vẫn tồn tại. `ROLLBACK` hoàn tác thao tác.

### 14.4. Tránh xóa rộng do thiếu điều kiện nối

Sai:

```sql
-- CẢNH BÁO: ví dụ nguy hiểm, không chạy.
DELETE FROM lesson278_orders AS o
USING lesson278_customers AS c
WHERE c.customer_id = 3;
```

Thiếu điều kiện `o.customer_id = c.customer_id`. Nếu tồn tại khách 3, điều kiện `c.customer_id = 3` đúng cho một dòng bên nguồn `c` và có thể khiến **mọi đơn ở bảng đích được đưa vào phạm vi xóa**, tùy cấu trúc liên quan. Dù FK khác sau đó có thể chặn, truy vấn đã sai phạm vi nghiêm trọng.

**Mọi DELETE dùng JOIN/USING phải được xem xét cẩn thận về điều kiện nối.**

## 15. Xóa theo nhiều cấp: thứ tự tổng quát và thứ tự trong schema mẫu

Khi có nhiều FK với chính sách chặn, bạn có thể hình dung bảng như một **đồ thị có hướng**:

```text
parent ──(được tham chiếu bởi)──► child
```

Đối với quan hệ chặn xóa, phải đảm bảo các dòng con không còn tham chiếu dòng cha tại thời điểm kiểm tra. Với mô hình phụ thuộc không vòng và kiểm tra ngay, một kế hoạch xóa thủ công thường đi theo thứ tự **từ các bảng con sâu nhất lên các bảng cha**.

Ví dụ:

```text
Customer
  └─ Order
       └─ Payment
            └─ PaymentAllocation
```

Nếu toàn bộ các FK là `RESTRICT`, muốn xóa Customer thì cần xử lý theo thứ tự:

1. `PaymentAllocation`.
2. `Payment`.
3. `Order`.
4. `Customer`.

Nhưng với `CASCADE` ở một số cạnh, DBMS có thể tự xử lý các cấp đó; với `SET NULL`, có thể giữ lại một số dòng con và thay khóa.

### 15.1. Không phải mọi bảng có FK đều phải xóa

Nếu quy tắc là giữ `support_tickets` và bỏ khách tham chiếu, `SET NULL` cho phép thực hiện như vậy. Xóa tất cả phiếu chỉ vì chúng có FK trỏ đến khách sẽ là **quyết định xóa sai nghiệp vụ**.

Bản kế hoạch nên ghi rõ:

| Quan hệ | Chính sách | Hành động thủ công dự kiến |
|---|---|---|
| Payments → Orders | RESTRICT | Quyết định giữ/chuyển/lưu trữ/xóa thanh toán theo quy trình riêng |
| OrderItems → Orders | CASCADE | Không cần xóa thủ công khi xóa đơn, nhưng phải xem trước số dòng |
| Orders → Customers | RESTRICT | Xử lý đơn trước khi xóa khách |
| SupportTickets → Customers | SET NULL | Không xóa phiếu; chú ý thông tin cá nhân còn trong nội dung |
| CustomerTags → Customers | CASCADE | Tự xóa thẻ khi xóa khách |

### 15.2. Vòng phụ thuộc (cycle) làm kế hoạch phức tạp hơn

Hai bảng có thể tham chiếu nhau, hoặc một bảng có khóa ngoại tự tham chiếu. Khi có vòng, không phải lúc nào cũng tồn tại thứ tự đơn giản “xóa tất cả con trước cha”.

Các giải pháp tùy mô hình có thể gồm:

- Thiết kế lại ràng buộc không cần thiết.
- Cho phép một số FK tạm thành `NULL` và cập nhật liên kết trước khi xóa.
- Dùng `NO ACTION DEFERRABLE` ở DBMS hỗ trợ và giải quyết các tham chiếu trước khi commit.
- Dùng cascade một cách có kiểm soát khi vòng đời dữ liệu thực sự phù hợp.
- Lập giao dịch gồm nhiều thao tác với quy tắc kiểm tra rõ ràng.

**Không mặc định tắt FK là giải pháp cho vòng phụ thuộc.** Việc thay schema hoặc trì hoãn kiểm tra cần được xem xét cả tác động vận hành.

## 16. Khóa ngoại tự tham chiếu: xóa cây cha–con trong cùng bảng

Một ví dụ đặc biệt là bảng `employees` có `manager_id` trỏ lại chính `employees.employee_id`:

```sql
CREATE TABLE lesson278_employees (
    employee_id INTEGER PRIMARY KEY,
    employee_name VARCHAR(100) NOT NULL,
    manager_id INTEGER,
    CONSTRAINT lesson278_employee_manager_fk
        FOREIGN KEY (manager_id)
        REFERENCES lesson278_employees(employee_id)
        ON DELETE SET NULL
);
```

Dữ liệu mẫu:

```sql
INSERT INTO lesson278_employees (
    employee_id, employee_name, manager_id
)
VALUES
    (1, 'Giám đốc', NULL),
    (2, 'Quản lý A', 1),
    (3, 'Quản lý B', 1),
    (4, 'Nhân viên C', 2);
```

Xóa giám đốc `employee_id = 1` trong transaction thử:

```sql
BEGIN;

DELETE FROM lesson278_employees
WHERE employee_id = 1
RETURNING employee_id, employee_name;

SELECT
    employee_id,
    employee_name,
    manager_id
FROM lesson278_employees
ORDER BY employee_id;

ROLLBACK;
```

Trong transaction, dòng giám đốc không còn; nhân viên 2 và 3 vẫn tồn tại với `manager_id = NULL`. Nhân viên 4 vẫn có `manager_id = 2` vì người quản lý 2 chưa bị xóa.

Nếu FK tự tham chiếu dùng `ON DELETE CASCADE` thay vì `SET NULL`, việc xóa giám đốc có thể lan truyền xóa cả cấp dưới theo quan hệ quản lý, thậm chí nhiều cấp. Điều này thường **không phù hợp** cho dữ liệu nhân sự, nhưng có thể phù hợp với một số cây thành phần tạm thời.

**Với quan hệ cây, cần đặc biệt hiểu “xóa nút cha” là bỏ nút, chuyển cấp dưới lên cấp cao hơn, tách cây hay xóa toàn bộ nhánh.** FK policy phải phản ánh đúng ý nghĩa đó.

## 17. Khi không nên xóa vật lý: soft delete

Nhiều hệ thống chọn **xóa logic** (*soft delete*) thay vì `DELETE` khỏi bảng:

```sql
UPDATE lesson278_customers
SET is_active = FALSE
WHERE customer_id = 1;
```

Câu này không xóa dòng `customers`, vì vậy:

- Các đơn vẫn tham chiếu được đến `customer_id = 1`.
- Các FK không cần kích hoạt hành động `ON DELETE`.
- Các phiếu hỗ trợ và thẻ vẫn giữ liên kết.
- Ứng dụng có thể **ẩn** khách khỏi danh sách hoạt động bằng `WHERE is_active = TRUE`.

### 17.1. Soft delete không phải xóa dữ liệu hoàn toàn

Dữ liệu vẫn còn trong các bảng và bản sao/lưu trữ liên quan. Soft delete có thể phù hợp khi cần giữ lịch sử giao dịch, nhưng **không thay thế quy trình xử lý yêu cầu xóa hoặc ẩn danh hóa dữ liệu** nếu nghiệp vụ/pháp luật áp dụng yêu cầu khác.

### 17.2. Soft delete có nhược điểm

- Mọi truy vấn danh sách “đang hoạt động” phải lọc đúng `is_active` hoặc thời điểm xóa.
- Khóa `UNIQUE` có thể vẫn chặn việc tạo một dòng mới trùng thông tin dù bản cũ đã bị đánh dấu xóa.
- Dữ liệu phụ thuộc có thể cần một quy tắc riêng: đơn của khách inactive có được hiển thị không?
- Các báo cáo tổng hợp và phân quyền phải nhất quán với trạng thái xóa logic.
- Nếu sau này cần xóa vật lý theo thời hạn lưu trữ, phải xử lý đúng đồ thị FK.

PostgreSQL có **partial unique index** để hỗ trợ một số chính sách unique chỉ trên dòng chưa xóa; tuy nhiên đó là một quyết định schema riêng, không tự giải quyết mọi vấn đề vòng đời dữ liệu.

### 17.3. Ví dụ soft delete trong transaction

```sql
BEGIN;

UPDATE lesson278_customers
SET is_active = FALSE
WHERE customer_id = 1
RETURNING customer_id, customer_name, is_active;

-- Các đơn của An vẫn tồn tại vì không có DELETE.
SELECT COUNT(*) AS remaining_orders
FROM lesson278_orders
WHERE customer_id = 1;

ROLLBACK;
```

Trong transaction, khách An bị đánh dấu inactive; hai đơn 101 và 102 vẫn tồn tại. Sau `ROLLBACK`, `is_active` trở lại TRUE.

## 18. TRUNCATE không giống DELETE theo điều kiện

`DELETE FROM table WHERE ...` xóa **những dòng phù hợp điều kiện**.

`TRUNCATE TABLE` thường nhằm làm rỗng **toàn bộ bảng**, có đặc tính và cách kiểm tra FK khác. Trong PostgreSQL, nếu bảng đang được FK từ bảng khác tham chiếu, `TRUNCATE` có thể bị từ chối trừ khi xử lý đầy đủ các bảng liên quan hoặc dùng tùy chọn phù hợp.

Ví dụ nguy hiểm:

```sql
-- CẢNH BÁO: KHÔNG chạy trên dữ liệu quan trọng.
TRUNCATE TABLE lesson278_customers CASCADE;
```

Trong PostgreSQL, `TRUNCATE ... CASCADE` có thể mở rộng phạm vi đến **toàn bộ những bảng đang tham chiếu bảng bị truncate**, không chỉ “các dòng con có liên quan đến một khách cụ thể”. Đây là khác biệt rất lớn so với `DELETE ... WHERE customer_id = 1`.

Hãy phân biệt:

| Đặc tính | `DELETE ... WHERE` | `TRUNCATE ... CASCADE` (PostgreSQL) |
|---|---|---|
| Chọn một vài dòng theo điều kiện | Có | Không |
| Thao tác theo FK `ON DELETE` | Có | Truncate có cơ chế riêng, không tương đương row-level DELETE |
| Có nguy cơ làm rỗng cả bảng khác | Theo chính sách xóa và phạm vi dòng | **Có**, khi cascade các bảng tham chiếu |
| Phù hợp xóa một khách và dữ liệu liên quan | Có, khi được thiết kế đúng | **Không** |
| Cần xét trigger và hành vi riêng | Có | Có; khác với DELETE |

Không dùng `TRUNCATE CASCADE` để “sửa lỗi không xóa được khách do FK” nếu mục đích chỉ là xóa một khách cụ thể. Hậu quả có thể rộng hơn rất nhiều.

## 19. Truy vấn an toàn: có WHERE, có tham số, có quyền hạn

### 19.1. Không quên WHERE

```sql
-- CẢNH BÁO: xóa toàn bảng, không chạy.
DELETE FROM lesson278_customers;
```

Câu này nhắm toàn bộ khách hàng. Ràng buộc FK có thể chặn một phần hoặc toàn bộ thao tác, nhưng **không được coi FK là lớp bảo vệ chống mọi lệnh DELETE thiếu WHERE**: khách không có đơn vẫn có thể bị xóa, đồng thời tags/tickets chịu tác động.

Thói quen tốt:

1. Viết `SELECT` với cùng điều kiện `WHERE`.
2. Xem số dòng và khóa.
3. Mới chuyển sang `DELETE`.
4. Xem `RETURNING` hoặc số dòng bị ảnh hưởng.

### 19.2. Truyền tham số thay vì ghép chuỗi SQL

Trong ứng dụng Java/JDBC, dùng `PreparedStatement`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

String sql = """
    DELETE FROM lesson278_customers
    WHERE customer_id = ?
    RETURNING customer_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println("Deleted customer: " + rs.getInt(1));
        }
    }
}
```

Đoạn Java là ví dụ PostgreSQL JDBC vì dùng `RETURNING`. Trong hệ thống thực tế, **chỉ thực hiện sau khi đã xử lý các FK chặn**, kiểm tra quyền người dùng và xác định đúng khách mục tiêu. `PreparedStatement` giúp ràng buộc tham số an toàn, nhưng **không tự giải quyết chính sách xóa dữ liệu**.

### 19.3. Kiểm tra số dòng bị ảnh hưởng

Nếu xóa theo khóa chính:

```sql
DELETE FROM lesson278_customers
WHERE customer_id = 999999
RETURNING customer_id;
```

và không có khách này, PostgreSQL trả **0 dòng `RETURNING`**. Điều đó không nhất thiết là lỗi SQL; ứng dụng phải quyết định “không tìm thấy” nên được trả như thế nào.

Với yêu cầu xóa đúng một khách, nên phân biệt:

- Xóa đúng **1 khách**.
- Không có khách nào khớp.
- Bị FK từ chối.
- Bị lỗi quyền truy cập.
- Lỗi giao dịch khác.

Không mặc định “lệnh chạy không báo lỗi” là đủ cho một tác vụ nghiệp vụ.

### 19.4. Quyền xóa

Ứng dụng có thể có quyền `SELECT` nhưng không có quyền `DELETE`. Ngoài quyền SQL, nghiệp vụ còn cần kiểm tra người yêu cầu **có quyền xóa khách cụ thể** không. Đừng bỏ qua xác thực/phân quyền chỉ vì câu `DELETE` có điều kiện đúng.

## 20. Tính đồng thời: xem trước không khóa được thế giới

Một quy trình có thể:

1. `SELECT` đếm các đơn của khách.
2. Thấy không có đơn.
3. Câu `DELETE` chuẩn bị xóa khách.

Nhưng giữa bước 1 và bước 3, một giao dịch khác có thể **chèn đơn mới** tham chiếu khách đó.

Vì vậy, `SELECT` xem trước là cần thiết để hiểu tác động, nhưng **không đảm bảo dữ liệu không thay đổi** đến lúc xóa. FK và cơ chế khóa/giao dịch của DBMS vẫn phải bảo vệ tính nhất quán.

### 20.1. Tại sao khóa ngoại quan trọng khi có nhiều giao dịch?

FK không chỉ kiểm tra giá trị tĩnh. Hệ quản trị phải phối hợp các thao tác như:

- Một giao dịch đang xóa dòng cha.
- Giao dịch khác đang chèn dòng con tham chiếu cha đó.
- Giao dịch khác đang sửa khóa FK của một dòng con.

Tùy DBMS, các thao tác có thể bị chặn chờ, bị từ chối hoặc được sắp thứ tự để đảm bảo ràng buộc cuối cùng. Không thiết kế ứng dụng dựa trên giả định rằng hai câu `SELECT` liên tiếp luôn nhìn một thế giới bất biến.

### 20.2. Giao dịch và SELECT ... FOR UPDATE

Ở PostgreSQL, có thể khóa dòng khách trước khi xử lý:

```sql
BEGIN;

SELECT customer_id, customer_name
FROM lesson278_customers
WHERE customer_id = 1
FOR UPDATE;

-- Sau đó xác định và xử lý các phụ thuộc trong cùng transaction.
-- Ví dụ có thể tiếp tục DELETE theo kế hoạch, hoặc ROLLBACK.

ROLLBACK;
```

Khóa dòng cha có thể giúp điều phối các thao tác đồng thời liên quan, nhưng **không phải phép màu ngăn mọi thay đổi ở mọi bảng con trong mọi cấu hình**. Hãy xét isolation level, loại khóa, thứ tự khóa và kế hoạch xóa thực tế.

### 20.3. Có thể xảy ra deadlock

Hai giao dịch cùng xóa/sửa các bảng liên quan nhưng lấy khóa theo thứ tự khác nhau có thể tạo **deadlock**. DBMS thường phát hiện và hủy một trong các transaction. Một chiến lược nhất quán về **thứ tự khóa và thứ tự thao tác** giúp giảm rủi ro, nhưng không thể hứa sẽ loại mọi deadlock.

Trong ứng dụng thật, cần biết cách **retry giao dịch thất bại có thể thử lại** khi phù hợp, đồng thời tránh lặp các tác dụng phụ bên ngoài giao dịch.

## 21. Index trên khóa ngoại và chi phí kiểm tra/xóa

Khi xóa dòng cha, DBMS cần biết có những dòng con nào đang tham chiếu cha đó hay không, hoặc cần tìm chúng để thực hiện `CASCADE`/`SET NULL`.

Trong PostgreSQL, khai báo FK **không tự động tạo chỉ mục trên cột FK phía con** trong mọi trường hợp. Khóa chính/unique phía cha thường đã có chỉ mục tương ứng, nhưng phía con có thể cần chỉ mục bổ sung.

Với mô hình bài học:

```sql
CREATE INDEX lesson278_orders_customer_idx
    ON lesson278_orders (customer_id);

CREATE INDEX lesson278_items_order_idx
    ON lesson278_order_items (order_id);

CREATE INDEX lesson278_payments_order_idx
    ON lesson278_payments (order_id);

CREATE INDEX lesson278_tickets_customer_idx
    ON lesson278_support_tickets (customer_id);

CREATE INDEX lesson278_tags_customer_idx
    ON lesson278_customer_tags (customer_id);
```

Các chỉ mục này có thể giúp:

- Tìm đơn theo `customer_id` để kiểm tra `RESTRICT` khi xóa khách.
- Tìm item theo `order_id` để thực hiện cascade khi xóa đơn.
- Tìm thanh toán theo `order_id` để kiểm tra FK chặn xóa đơn.
- Tìm ticket/tag theo `customer_id` để thay liên kết hoặc xóa theo chính sách.

**Tuy nhiên:** chỉ mục cũng tốn dung lượng và chi phí ghi. Với bảng thực hành vài dòng, chúng không làm bài học nhanh hơn rõ rệt. Trong sản xuất, chọn index dựa trên **kích thước bảng, tần suất xóa, truy vấn và kế hoạch thực thi**.

### 21.1. FK giúp toàn vẹn, không tự làm mọi câu DELETE nhanh

Một FK có thể đúng hoàn toàn về dữ liệu nhưng lệnh xóa cha lại chậm vì DBMS phải tìm dòng con trong bảng rất lớn mà thiếu chỉ mục phù hợp.

Nếu có thao tác xóa số lượng lớn, cần quan sát:

- Số dòng con liên quan.
- Số bảng và số cấp cascade.
- Chỉ mục trên khóa con.
- Trigger được gọi khi xóa/cập nhật.
- Khối lượng ghi WAL/redo/transaction log và thời gian giữ khóa.
- Tác động lên truy vấn và giao dịch khác.

### 21.2. Không giả định cascade là “một lệnh rẻ”

Một câu:

```sql
DELETE FROM lesson278_customers
WHERE customer_id = 4;
```

có thể kích hoạt xử lý ở nhiều bảng dù chỉ xóa một dòng khách. Trong cơ sở dữ liệu thực, một khách có hàng triệu dòng con thì tác động và chi phí có thể rất lớn.

**Số dòng ở câu `DELETE` chính không phản ánh đầy đủ số dòng con bị ảnh hưởng.**

## 22. Trigger, kiểm toán và RETURNING

Một hệ thống có thể có **trigger** trên bảng cha hoặc con. Hành động FK như `CASCADE` hoặc `SET NULL` có thể kích hoạt xử lý bổ sung tùy DBMS và loại trigger.

Ví dụ, khi xóa đơn:

- Trigger trên bảng `orders` có thể ghi log.
- Xóa cascade trên `order_items` có thể khiến các trigger liên quan đến những dòng item được thực thi.
- Khi `SET NULL` trên ticket, các trigger cập nhật ticket có thể chạy nếu được định nghĩa.

**Không thể suy ra toàn bộ tác động chỉ bằng cách nhìn dòng `DELETE FROM parent`.**

### 22.1. RETURNING không tự trả “cây bị cascade”

```sql
DELETE FROM lesson278_orders
WHERE order_id = 102
RETURNING order_id;
```

`RETURNING` của câu này trả cột từ **dòng đích `orders` bị xóa**, không tự đưa các dòng `order_items` bị cascade vào cùng kết quả.

Nếu cần nhật ký đầy đủ về tất cả các thực thể liên quan, có thể:

- Xem và lưu danh sách khóa trước khi xóa trong cùng transaction.
- Dùng bảng audit với trigger đúng thiết kế.
- Ghi nhận sự kiện nghiệp vụ ở tầng ứng dụng.
- Đối chiếu số dòng và ràng buộc sau thao tác.

Các cơ chế audit cần được thiết kế đúng về tính nhất quán, bảo mật và lưu trữ; không nên giả định mỗi trigger tùy ý đều có thể rollback các hiệu ứng bên ngoài DBMS.

### 22.2. Kiểm soát tác động ngoài giao dịch

Giao dịch PostgreSQL hoàn tác thay đổi dữ liệu trong DBMS khi `ROLLBACK`, nhưng nếu trigger hoặc ứng dụng gửi email, gọi API hoặc ghi vào hệ thống bên ngoài bằng cơ chế không gắn chặt với transaction, tác dụng phụ đó có thể **không tự hoàn tác**.

Vì vậy, “thử xóa rồi rollback” chỉ an toàn khi bạn hiểu đầy đủ hạ tầng. Trong hệ thống phức tạp, hãy dùng môi trường staging, bản sao kiểm thử hoặc quy trình dry-run chính thức.

## 23. Tìm và giải thích dữ liệu mồ côi

**Dòng mồ côi** là dòng con chứa khóa tham chiếu đến một dòng cha không còn tồn tại (theo một quan hệ mà nghiệp vụ yêu cầu phải có cha).

Nếu FK đang được áp dụng và dữ liệu hợp lệ, các tình huống mồ côi tương ứng thông thường không tồn tại ở trạng thái đã commit. Nhưng dữ liệu nhập lịch sử, hệ thống cũ hoặc các thời điểm FK bị tắt/không được kiểm chứng có thể cần chẩn đoán.

Ví dụ kiểm tra `orders.customer_id` không có khách tương ứng:

```sql
SELECT
    o.order_id,
    o.customer_id
FROM lesson278_orders AS o
LEFT JOIN lesson278_customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
ORDER BY o.order_id;
```

Với bộ dữ liệu mẫu và FK còn hiệu lực, kết quả là **0 dòng**.

Hoặc dùng `NOT EXISTS`:

```sql
SELECT
    o.order_id,
    o.customer_id
FROM lesson278_orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson278_customers AS c
    WHERE c.customer_id = o.customer_id
);
```

### 23.1. Không nhầm NULL hợp lệ với orphan

Với `support_tickets.customer_id` cho phép `NULL`, một phiếu có `customer_id = NULL` **không vi phạm FK**; đó là trạng thái “không gắn khách” được schema cho phép.

Nếu bạn kiểm tra bằng `LEFT JOIN ... WHERE c.customer_id IS NULL`, kết quả có thể gồm cả:

- Dòng con có FK **`NULL` hợp lệ**.
- Dòng con có FK **khác `NULL` nhưng không tìm thấy cha**.

Muốn chỉ tìm tham chiếu hỏng thật sự, cần thêm:

```sql
WHERE t.customer_id IS NOT NULL
  AND c.customer_id IS NULL
```

Ví dụ:

```sql
SELECT
    t.ticket_id,
    t.customer_id
FROM lesson278_support_tickets AS t
LEFT JOIN lesson278_customers AS c
    ON c.customer_id = t.customer_id
WHERE t.customer_id IS NOT NULL
  AND c.customer_id IS NULL;
```

Trong bảng mẫu, kết quả là 0 dòng.

## 24. Khóa ngoại ghép và nhiều cột: không chỉ một ID

FK có thể gồm **nhiều cột**, ví dụ:

```sql
FOREIGN KEY (store_id, order_no)
REFERENCES orders(store_id, order_no)
```

Khi xóa dòng cha, `CASCADE`, `RESTRICT` hoặc hành động khác áp dụng theo **cặp giá trị tham chiếu**, không chỉ `order_no`.

Nếu mã đơn `A101` tồn tại ở cả cửa hàng 1 và 2, việc chỉ lọc theo `order_no = 'A101'` có thể nhắm cả hai. Điều kiện xóa phải tuân theo khóa nghiệp vụ và khóa tham chiếu thật.

### 24.1. SET NULL trên FK ghép

Khi FK ghép dùng `ON DELETE SET NULL`, số cột bị đặt `NULL` và khả năng chỉ định một tập con cột phụ thuộc DBMS và cú pháp ràng buộc. PostgreSQL cho phép các dạng đặc biệt chỉ định cột cho `SET NULL` trong một số tình huống FK ghép; các hệ khác có thể không hỗ trợ.

Quan trọng nhất là bảo đảm trạng thái sau thao tác vẫn phù hợp:

- `NOT NULL` của từng cột.
- Ngữ nghĩa `MATCH` của FK ghép.
- Quy tắc nghiệp vụ về khóa ghép bị thiếu một phần.

Không tự coi “xóa cha sẽ đặt một cột FK thành NULL” là mô tả đủ cho mọi FK nhiều cột.

## 25. Thiết kế chính sách ON DELETE theo vòng đời dữ liệu

Trước khi chọn ràng buộc, hãy hỏi:

1. **Dòng con có thể sống độc lập với cha không?**
2. **Nếu cha biến mất, con còn giá trị nghiệp vụ/kiểm toán không?**
3. **Có một đối tượng dự phòng hợp lệ để chuyển liên kết không?**
4. **Có phải ngăn việc xóa cha cho đến khi con được xử lý thủ công không?**
5. **Việc xóa nhiều cấp có làm mất thông tin khó khôi phục không?**
6. **Có yêu cầu lưu trữ, bảo mật hoặc pháp lý ảnh hưởng vòng đời dữ liệu không?**

Một bảng quyết định minh họa:

| Quan hệ | Chính sách có thể phù hợp | Lý do |
|---|---|---|
| Đơn hàng → chi tiết đơn | `CASCADE` trong hệ thống cho phép xóa toàn đơn | Chi tiết phụ thuộc đơn |
| Đơn hàng → thanh toán | `RESTRICT` hoặc `NO ACTION` | Thanh toán cần xử lý/lưu giữ riêng |
| Khách hàng → đơn hàng | `RESTRICT` | Tránh mất lịch sử đơn do xóa khách |
| Khách hàng → thẻ phân loại tạm | `CASCADE` | Thẻ không còn ý nghĩa khi khách biến mất |
| Khách hàng → phiếu hỗ trợ | `SET NULL` nếu cho phép giữ phiếu không gắn khách | Bảo toàn phiếu, bỏ liên kết |
| Nhóm phân loại → thành viên | `SET DEFAULT` nếu có nhóm dự phòng thực sự hợp lệ | Chuyển sang nhóm mặc định |
| Người quản lý → nhân viên | `SET NULL` trong một số mô hình | Không xóa nhân viên khi quản lý nghỉ |
| Hạng mục → dòng con trong cây tạm | `CASCADE` nếu yêu cầu xóa toàn nhánh | Các phần tử con phụ thuộc hoàn toàn |

Đây **không phải quy tắc cứng** cho mọi sản phẩm. Ví dụ một phiếu hỗ trợ có thể **bắt buộc** gắn khách vì quy định lưu hồ sơ, hoặc cần cơ chế thay thế trước khi xóa. Mô hình dữ liệu phải phục vụ yêu cầu của hệ thống thực tế.

## 26. Khác biệt giữa các hệ quản trị

### 26.1. PostgreSQL

PostgreSQL hỗ trợ:

- `ON DELETE NO ACTION` (mặc định thông dụng).
- `ON DELETE RESTRICT`.
- `ON DELETE CASCADE`.
- `ON DELETE SET NULL`.
- `ON DELETE SET DEFAULT`.
- FK `DEFERRABLE` trong điều kiện phù hợp.
- `DELETE ... USING`, `DELETE ... RETURNING`.
- Giao dịch `BEGIN`, `COMMIT`, `ROLLBACK`.
- `TRUNCATE ... CASCADE` với ngữ nghĩa khác row-level `DELETE`.

Phần lớn ví dụ thực hành trong bài dùng PostgreSQL.

### 26.2. MySQL/InnoDB và MariaDB

InnoDB hỗ trợ các chính sách như `RESTRICT`, `CASCADE`, `SET NULL`. Trong MySQL/InnoDB, `NO ACTION` về thực tế thường được xử lý tương đương `RESTRICT` theo kiểm tra ngay, không có cơ chế deferred FK như PostgreSQL. MySQL/InnoDB **không hỗ trợ `ON DELETE SET DEFAULT` như một hành động FK thông dụng**.

Không dựa vào cấu hình từ engine không thực thi FK giống InnoDB. Với MySQL/MariaDB, cần xác định phiên bản, engine lưu trữ và chính sách liên quan trước khi triển khai.

### 26.3. SQL Server

SQL Server hỗ trợ các hành động FK như `NO ACTION`, `CASCADE`, `SET NULL`, `SET DEFAULT`, với những hạn chế riêng về **nhiều đường cascade (multiple cascade paths)** hoặc chu trình quan hệ trong DDL.

Không giả định SQL Server hỗ trợ cùng cơ chế `DEFERRABLE` của PostgreSQL. Cú pháp xóa có JOIN và xuất dòng bị xóa dùng T-SQL, ví dụ `DELETE ... FROM ... JOIN ...` và `OUTPUT deleted...`, không sao chép nguyên PostgreSQL `DELETE USING RETURNING`.

### 26.4. SQLite

SQLite có hỗ trợ FK, nhưng phải lưu ý **bật cơ chế thực thi FK phù hợp trên connection** và kiểm tra phiên bản/cấu hình:

```sql
PRAGMA foreign_keys = ON;
```

Trong những môi trường SQLite không bật enforcement, dữ liệu có thể được ghi/xóa mà không chịu các quy tắc FK như bạn dự kiến. Các hành động như `CASCADE`, `SET NULL`, `SET DEFAULT`, `RESTRICT`, `NO ACTION` có cơ chế theo SQLite; `NO ACTION` và `RESTRICT` có khác biệt về thời điểm báo lỗi trong các tình huống nhất định.

**Không dùng kết quả thử trên SQLite với FK bị tắt để suy luận hành vi của PostgreSQL có FK hoạt động.**

### 26.5. Oracle Database

Oracle hỗ trợ FK với các lựa chọn như `ON DELETE CASCADE` và `ON DELETE SET NULL`, trong khi cú pháp và tập hành động có thể khác PostgreSQL. Oracle có ràng buộc `DEFERRABLE` theo quy tắc riêng. Không áp dụng nguyên mọi mệnh đề `ON DELETE RESTRICT`/`SET DEFAULT` của PostgreSQL sang Oracle khi chưa đối chiếu DDL.

### 26.6. Bảng đối chiếu khái quát

| Vấn đề | PostgreSQL | MySQL/InnoDB | SQL Server | SQLite |
|---|---|---|---|---|
| `CASCADE` | Có | Có | Có | Có khi FK được thực thi |
| `SET NULL` | Có | Có | Có | Có khi FK được thực thi |
| `SET DEFAULT` | Có | Không hỗ trợ phổ biến trong InnoDB | Có | Có khi FK được thực thi |
| `RESTRICT` vs `NO ACTION` | Khác ở khả năng hoãn kiểm tra | Thường cùng kiểu kiểm tra ngay | Theo quy tắc SQL Server | Có khác biệt về thời điểm kiểm tra |
| FK có thể hoãn kiểm tra | Có, với ràng buộc `DEFERRABLE` | Không như PostgreSQL | Không như PostgreSQL | Có cơ chế deferred FK |
| Cú pháp `DELETE ... RETURNING` | Có | Tùy DBMS/phiên bản, không mặc định giống PostgreSQL | Dùng `OUTPUT` | Có `RETURNING` ở phiên bản hỗ trợ |

Bảng này tóm tắt **xu hướng/cơ chế thường gặp**, không thay thế tài liệu chính thức của phiên bản và engine cụ thể.

## 27. Những lỗi thường gặp và cách sửa

### Lỗi 1. Cho rằng xóa cha sẽ luôn tự xóa con

Không đúng. Nếu FK là `RESTRICT` hoặc `NO ACTION` không hoãn, thao tác có thể bị từ chối. Phải xem **DDL của ràng buộc**, không chỉ tên hai bảng.

### Lỗi 2. Cho rằng CASCADE luôn xóa được cả cây

Một FK khác ở cấp sâu có thể chặn xóa, hoặc trigger/ràng buộc khác gây lỗi. Xem đầy đủ các nhánh phụ thuộc trước khi xóa.

### Lỗi 3. Xóa cha trước khi xử lý con RESTRICT

Xóa khách An trước khi xử lý đơn 101 và 102 sẽ bị chặn. Trong kế hoạch xóa thủ công với FK chặn, xử lý các tham chiếu con trước cha theo đúng nghiệp vụ.

### Lỗi 4. Xóa con thủ công dù schema đã SET NULL

Phiếu hỗ trợ có thể cần giữ. Khi `SET NULL`, việc xóa ticket chỉ để cho phép xóa khách là không cần thiết và có thể làm mất dữ liệu.

### Lỗi 5. Dùng SET NULL trên cột NOT NULL

Nếu hành động cần đặt FK thành `NULL` mà cột cấm `NULL`, phép xóa sẽ không hoàn tất hợp lệ. Kiểm tra khả năng lưu trạng thái “không liên kết” trong schema.

### Lỗi 6. Dùng SET DEFAULT với giá trị không có cha

`DEFAULT 0` vẫn phải tham chiếu một dòng cha hợp lệ nếu FK yêu cầu. Nếu nhóm 0 không tồn tại, việc xóa nhóm khác có thể lỗi khi hệ thống cố chuyển các thành viên về 0.

### Lỗi 7. Dùng DELETE thiếu WHERE

`DELETE FROM customers;` nhắm tất cả khách. FK không thay thế bộ lọc đúng và không bảo vệ toàn bộ các dữ liệu khác bị cascade.

### Lỗi 8. Thiếu điều kiện nối trong DELETE USING/JOIN

Một câu `DELETE ... USING customers` có thể xóa rộng nếu chỉ lọc bảng khách mà quên `orders.customer_id = customers.customer_id`. Viết `SELECT` cùng JOIN để xem trước các khóa trước khi chuyển thành `DELETE`.

### Lỗi 9. Tưởng RETURNING liệt kê mọi dòng cascade

`DELETE FROM orders ... RETURNING order_id` không tự trả các `order_items` bị cascade. Cần cơ chế quan sát/kiểm toán riêng khi cần biết toàn bộ tác động.

### Lỗi 10. Tưởng transaction bảo vệ mọi tác dụng phụ ngoài DB

`ROLLBACK` hoàn tác thay đổi dữ liệu transactional, nhưng không mặc nhiên hoàn tác email, API call, file bên ngoài hoặc thông báo đã gửi. Thử trên môi trường thích hợp.

### Lỗi 11. Tắt FK để xóa thành công

Tắt enforcement có thể tạo dữ liệu mồ côi. Nên sửa kế hoạch xóa hoặc schema theo nghiệp vụ thay vì bỏ lớp bảo vệ.

### Lỗi 12. Xem trước một lần rồi tin dữ liệu không đổi

Giao dịch khác có thể chèn con mới trước khi bạn xóa cha. Giữ FK và thiết kế transaction/concurrency phù hợp.

### Lỗi 13. Nhầm TRUNCATE CASCADE với DELETE CASCADE

Trong PostgreSQL, `TRUNCATE ... CASCADE` có thể làm rỗng toàn bộ những bảng tham chiếu, không chỉ các dòng liên quan đến một khách. Không dùng nó để thay một phép xóa có `WHERE`.

### Lỗi 14. Coi soft delete là đã xóa hoàn toàn

`UPDATE is_active = FALSE` không xóa dữ liệu, không kích hoạt `ON DELETE` và không tự giải quyết lưu trữ hay quyền riêng tư.

### Lỗi 15. Không tạo chỉ mục cột FK phía con

FK bảo đảm tính toàn vẹn nhưng không tự đảm bảo kiểm tra/xóa cha hiệu quả với bảng con lớn. Cân nhắc index trên FK theo workload.

### Lỗi 16. Chỉ nhìn một cấp quan hệ

Khách → Đơn → Thanh toán/Chi tiết có những chính sách khác nhau. Một nhánh RESTRICT có thể chặn cả yêu cầu xóa khách. Cần sơ đồ phụ thuộc đầy đủ.

### Lỗi 17. Dùng tên hiển thị thay cho khóa ổn định

`DELETE ... WHERE customer_name = 'Chi'` có thể nhắm nhiều khách trùng tên. Nên dùng khóa định danh đã xác thực cùng quyền truy cập.

## 28. Bài tập thực hành có lời giải

Các bài dưới đây dùng dữ liệu ở phần 3. Những câu `DELETE` có hiệu lực được đặt trong transaction với `ROLLBACK` để không thay đổi vĩnh viễn bộ dữ liệu thực hành. Nếu đã chạy các bài và không rollback như hướng dẫn, kết quả tiếp theo có thể khác.

### Bài 1. Xác định quan hệ cha–con

**Câu hỏi:** Trong `lesson278_orders`, cột `customer_id` là khóa gì và tham chiếu bảng nào?

**Đáp án:** `customer_id` là FK ở bảng con `orders`, tham chiếu PK `lesson278_customers.customer_id`. `orders` là con của `customers`, nhưng là cha đối với `order_items` và `payments`.

### Bài 2. Vì sao không xóa được khách An trực tiếp?

```sql
-- Dự đoán, không cần chạy để gây lỗi.
DELETE FROM lesson278_customers
WHERE customer_id = 1;
```

**Đáp án:** An có đơn 101 và 102. FK `lesson278_orders.customer_id` dùng `ON DELETE RESTRICT`, vì vậy xóa An trực tiếp bị chặn.

### Bài 3. Dự đoán tác động khi xóa đơn 102

```sql
BEGIN;

DELETE FROM lesson278_orders
WHERE order_id = 102
RETURNING order_id;

SELECT COUNT(*) AS item_count
FROM lesson278_order_items
WHERE order_id = 102;

ROLLBACK;
```

**Đáp án:** Xóa đơn 102 được phép vì không có thanh toán. Item 1003 tự bị xóa do `ON DELETE CASCADE`; `item_count = 0` trong transaction. Khách An vẫn tồn tại. `ROLLBACK` hoàn tác tất cả.

### Bài 4. Vì sao không xóa được đơn 101 ngay?

**Đáp án:** đơn 101 có thanh toán 501; FK `lesson278_payments.order_id` dùng `RESTRICT`. Dù order_items dùng `CASCADE`, thanh toán vẫn chặn. Muốn thực hiện yêu cầu xóa phải quyết định nghiệp vụ về thanh toán trước.

### Bài 5. Đếm toàn bộ quan hệ phụ thuộc của khách An

```sql
SELECT
    (SELECT COUNT(*)
     FROM lesson278_orders WHERE customer_id = 1) AS orders_n,
    (SELECT COUNT(*)
     FROM lesson278_order_items AS i
     JOIN lesson278_orders AS o ON o.order_id = i.order_id
     WHERE o.customer_id = 1) AS items_n,
    (SELECT COUNT(*)
     FROM lesson278_payments AS p
     JOIN lesson278_orders AS o ON o.order_id = p.order_id
     WHERE o.customer_id = 1) AS payments_n,
    (SELECT COUNT(*)
     FROM lesson278_support_tickets WHERE customer_id = 1) AS tickets_n,
    (SELECT COUNT(*)
     FROM lesson278_customer_tags WHERE customer_id = 1) AS tags_n;
```

**Đáp án:** `orders_n = 2`, `items_n = 3`, `payments_n = 1`, `tickets_n = 1`, `tags_n = 2`.

### Bài 6. Chọn thứ tự xóa thủ công cho khách An

**Yêu cầu:** Nếu chính sách thử nghiệm cho phép xóa thanh toán và đơn, viết ba câu xóa theo đúng thứ tự, sau đó rollback.

```sql
BEGIN;

DELETE FROM lesson278_payments
WHERE order_id IN (
    SELECT order_id
    FROM lesson278_orders
    WHERE customer_id = 1
);

DELETE FROM lesson278_orders
WHERE customer_id = 1;

DELETE FROM lesson278_customers
WHERE customer_id = 1;

ROLLBACK;
```

**Đáp án:** thứ tự là **thanh toán → đơn → khách**. Items tự cascade cùng đơn; tags tự cascade cùng khách; tickets được set null. Sau rollback, không có thay đổi được lưu. Đây chỉ là minh họa, không khuyến khích xóa thanh toán thật.

### Bài 7. Xóa Dũng thì hai bảng con chịu tác động gì?

```sql
BEGIN;

DELETE FROM lesson278_customers
WHERE customer_id = 4;

SELECT ticket_id, customer_id
FROM lesson278_support_tickets
WHERE ticket_id = 903;

SELECT *
FROM lesson278_customer_tags
WHERE tag_id = 704;

ROLLBACK;
```

**Đáp án:** ticket 903 còn nhưng `customer_id = NULL`, tag 704 bị xóa. Không có đơn nào của Dũng bị ảnh hưởng. Sau rollback, ticket và tag trở lại như trước.

### Bài 8. Phân biệt NO ACTION với RESTRICT trong PostgreSQL

**Câu hỏi:** Hai chính sách có luôn đồng nghĩa không?

**Đáp án:** Không hoàn toàn. Khi kiểm tra không được hoãn, cả hai đều chặn xóa cha còn bị tham chiếu. `NO ACTION` có thể dùng với ràng buộc `DEFERRABLE` để trì hoãn kiểm tra đến cuối transaction hoặc thời điểm kiểm tra được yêu cầu; `RESTRICT` không cho phép trì hoãn hành động chặn theo cách đó.

### Bài 9. SET DEFAULT phải đáp ứng điều kiện gì?

**Câu hỏi:** Nếu `group_id DEFAULT 0` nhưng không có nhóm 0 trong bảng cha, điều gì xảy ra khi xóa nhóm đang được con tham chiếu?

**Đáp án:** DBMS không thể đặt `group_id = 0` cho con mà vẫn giữ FK hợp lệ, nên thao tác xóa sẽ bị từ chối/rollback theo quy tắc transaction. `SET DEFAULT` không bỏ qua kiểm tra tham chiếu.

### Bài 10. Vì sao SET NULL có thể thất bại?

```sql
customer_id INTEGER NOT NULL
    REFERENCES customers(customer_id)
    ON DELETE SET NULL
```

**Đáp án:** khi xóa cha đang được tham chiếu, hành động muốn đặt `customer_id = NULL`, nhưng cột `NOT NULL` không cho phép. Schema và chính sách FK không phù hợp với trạng thái muốn lưu.

### Bài 11. Viết truy vấn tìm thanh toán của khách Bình

```sql
SELECT
    p.payment_id,
    p.order_id
FROM lesson278_payments AS p
JOIN lesson278_orders AS o
    ON o.order_id = p.order_id
WHERE o.customer_id = 2;
```

**Đáp án:** thanh toán `payment_id = 502`, thuộc đơn 103. Nếu chưa xử lý thanh toán này, đơn 103 không được xóa trực tiếp vì `RESTRICT`.

### Bài 12. Kiểm tra dòng mồ côi trong orders

```sql
SELECT o.order_id, o.customer_id
FROM lesson278_orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson278_customers AS c
    WHERE c.customer_id = o.customer_id
);
```

**Đáp án:** 0 dòng trong dữ liệu mẫu. FK bảo vệ mối quan hệ ở trạng thái giao dịch hợp lệ.

### Bài 13. Phiếu không gắn khách có phải orphan không?

**Câu hỏi:** Nếu `lesson278_support_tickets.customer_id` có `NULL` do `SET NULL`, có phải vi phạm FK không?

**Đáp án:** Không. Với FK đơn cột nullable như bảng mẫu, `NULL` biểu diễn **không có liên kết** và là trạng thái hợp lệ. Dữ liệu mồ côi cần phân biệt với FK `NULL` được cho phép.

### Bài 14. Sửa lỗi DELETE USING thiếu điều kiện nối

Câu nguy hiểm:

```sql
-- KHÔNG CHẠY.
DELETE FROM lesson278_orders AS o
USING lesson278_customers AS c
WHERE c.customer_id = 3;
```

**Đáp án:** thiếu điều kiện `o.customer_id = c.customer_id`. Sửa:

```sql
BEGIN;

DELETE FROM lesson278_orders AS o
USING lesson278_customers AS c
WHERE o.customer_id = c.customer_id
  AND c.customer_id = 3
RETURNING o.order_id;

ROLLBACK;
```

Kết quả xóa thử là đơn 104, và item 1005 cascade; không tác động đơn của khách khác.

### Bài 15. Vì sao TRUNCATE CASCADE không thay DELETE có WHERE?

**Đáp án:** `TRUNCATE ... CASCADE` trong PostgreSQL có thể làm rỗng **toàn bộ các bảng tham chiếu**, không chỉ những dòng con liên quan một khách cụ thể. `DELETE FROM customers WHERE customer_id = 4` nhắm một dòng cha, với tác động FK phù hợp trên những dòng liên quan. Không dùng TRUNCATE để giải quyết yêu cầu xóa một khách.

### Bài 16. Soft delete có kích hoạt ON DELETE không?

```sql
BEGIN;

UPDATE lesson278_customers
SET is_active = FALSE
WHERE customer_id = 1;

SELECT COUNT(*)
FROM lesson278_orders
WHERE customer_id = 1;

ROLLBACK;
```

**Đáp án:** không kích hoạt `ON DELETE` vì không có dòng cha bị xóa. Hai đơn 101 và 102 vẫn tồn tại; lệnh `SELECT COUNT(*)` trả 2 trong transaction.

### Bài 17. Vì sao cần index trên FK phía con?

**Đáp án:** khi xóa cha, DBMS thường phải tìm những dòng con đang tham chiếu để kiểm tra `RESTRICT` hoặc thực hiện `CASCADE`/`SET NULL`. Nếu bảng con lớn và thiếu index phù hợp, thao tác có thể tốn nhiều công quét. Trong PostgreSQL, tạo FK không tự động tạo mọi index cần thiết trên phía con; cân nhắc chỉ mục theo `customer_id`, `order_id` và workload thực.

### Bài 18. Quy trình kiểm tra trước khi xóa một khách

**Yêu cầu:** trình bày các bước an toàn ở mức kỹ thuật/nghiệp vụ.

**Gợi ý đáp án:**

1. Xác định đúng khách theo khóa và kiểm tra quyền xóa.
2. Xác định các FK trực tiếp/gián tiếp, phân loại `RESTRICT`, `NO ACTION`, `CASCADE`, `SET NULL`, `SET DEFAULT`.
3. Dùng `SELECT` xem trước các khóa và số dòng liên quan.
4. Xác định phải giữ, lưu trữ, ẩn danh hóa, soft-delete hay xóa vật lý từng loại dữ liệu.
5. Thiết kế thứ tự thao tác, giao dịch, xử lý xung đột đồng thời và khả năng khôi phục.
6. Thử trong môi trường phù hợp; không dựa hoàn toàn vào rollback nếu có tác dụng phụ bên ngoài.
7. Thực thi với điều kiện `WHERE` chính xác và tham số hóa.
8. Kiểm tra số dòng đích đã xóa, các liên kết set-null/cascade, tính toàn vẹn và log.
9. Ghi nhận kết quả nghiệp vụ, xử lý lỗi và rollback/retry theo chính sách.

Đây là một quy trình có kiểm soát; không có một câu `DELETE` duy nhất phù hợp mọi đồ thị phụ thuộc.

## 29. Bảng ghi nhớ

| Vấn đề | Điều cần nhớ |
|---|---|
| Khóa ngoại nằm ở đâu? | Thường khai báo trên **bảng con**, tham chiếu khóa của **bảng cha** |
| Xóa con có tự xóa cha không? | **Không** chỉ vì có `ON DELETE CASCADE` |
| `ON DELETE RESTRICT` | Chặn xóa cha còn bị tham chiếu |
| `ON DELETE NO ACTION` | Không tự sửa con; có thể hoãn kiểm tra nếu FK deferrable và DBMS hỗ trợ |
| `ON DELETE CASCADE` | Xóa những dòng con liên quan; có thể lan truyền nhiều cấp |
| `ON DELETE SET NULL` | Giữ dòng con, thay khóa tham chiếu bằng `NULL`; cột phải cho phép |
| `ON DELETE SET DEFAULT` | Giữ dòng con, thay bằng default **hợp lệ theo FK** |
| Xóa cha có con RESTRICT | Xử lý con theo chính sách trước khi xóa cha |
| Xóa đơn có cả CASCADE và RESTRICT | Một FK chặn có thể khiến cả thao tác thất bại |
| Xóa khách có ticket SET NULL | Ticket không bị xóa, nhưng mất liên kết |
| Xem trước phạm vi | `SELECT` liệt kê khóa, đếm dòng theo từng bảng, đọc FK |
| Xóa theo quan hệ | `DELETE ... USING`/`EXISTS` với JOIN và WHERE chính xác |
| Giữ transaction an toàn | `BEGIN`, xem tác động, `COMMIT` hoặc `ROLLBACK` theo quy trình |
| `RETURNING` có trả mọi dòng cascade? | **Không**, chỉ trả dòng thuộc target DELETE |
| FK có bảo vệ khi concurrent? | Có vai trò quan trọng; xem trước không thay thế ràng buộc/khóa |
| Index FK phía con | Có thể rất quan trọng để kiểm tra và xử lý xóa với bảng lớn |
| Soft delete | `UPDATE` trạng thái, **không** kích hoạt `ON DELETE` |
| `TRUNCATE CASCADE` | Không tương đương DELETE có WHERE; có thể làm rỗng toàn bảng liên quan |
| Dòng mồ côi | Con tham chiếu khóa không tồn tại; phân biệt với FK `NULL` hợp lệ |
| Dữ liệu thanh toán/kiểm toán | Thường cần vòng đời xử lý riêng, không xóa chỉ để vượt FK |
| Kế hoạch xóa đáng tin | Đúng khóa, đúng quyền, đúng tác động FK, đúng giao dịch và kiểm chứng |

## 30. Kết luận

**Xóa dữ liệu quan hệ không chỉ là lựa chọn những dòng ở bảng đích.** Nó còn là quá trình xử lý các **đường phụ thuộc do khóa ngoại định nghĩa**. Một thao tác xóa cha có thể bị chặn, xóa lan truyền, làm rỗng liên kết hoặc chuyển con sang giá trị mặc định. Kết quả phụ thuộc **chính xác từng ràng buộc `ON DELETE`**.

Với mô hình của bài:

```text
Customers
   ├─ RESTRICT → Orders
   │                ├─ CASCADE → OrderItems
   │                └─ RESTRICT → Payments
   ├─ SET NULL → SupportTickets
   └─ CASCADE  → CustomerTags
```

Muốn xóa An trong môi trường thực hành, cần xử lý **thanh toán trước đơn, đơn trước khách** vì những FK `RESTRICT`, trong khi DBMS tự xử lý `CASCADE` và `SET NULL` theo các quan hệ còn lại. Việc thực hiện trong transaction và `ROLLBACK` giúp quan sát cơ chế mà không lưu thay đổi trong dữ liệu mẫu.

Trước bất kỳ thao tác xóa quan trọng nào, hãy tự trả lời: **Xóa ai? Dòng nào phụ thuộc? Những dữ liệu nào cần giữ? FK sẽ xử lý theo chính sách nào? Có thể xem trước và khôi phục không?** Khi năm câu hỏi đó được trả lời rõ ràng, bạn mới có thể xây dựng một quy trình `DELETE` đúng quan hệ, đúng nghiệp vụ và kiểm soát được tác động.

## Tài liệu tham khảo

- [PostgreSQL — Foreign Keys](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-FK): `NO ACTION`, `RESTRICT`, `CASCADE`, `SET NULL`, `SET DEFAULT` và tính toàn vẹn tham chiếu.
- [PostgreSQL — DELETE](https://www.postgresql.org/docs/current/sql-delete.html): cú pháp `DELETE ... USING`, `WHERE` và `RETURNING`.
- [PostgreSQL — SET CONSTRAINTS](https://www.postgresql.org/docs/current/sql-set-constraints.html): thay đổi thời điểm kiểm tra của ràng buộc `DEFERRABLE`.
- [PostgreSQL — TRUNCATE](https://www.postgresql.org/docs/current/sql-truncate.html): tác động của `TRUNCATE ... CASCADE`.
- [MySQL Reference Manual — FOREIGN KEY Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html): các hành động xóa và lưu ý về InnoDB.
- [Microsoft Learn — Primary and Foreign Key Constraints](https://learn.microsoft.com/en-us/sql/relational-databases/tables/primary-and-foreign-key-constraints): chính sách tham chiếu và các giới hạn SQL Server.
- [SQLite — Foreign Key Support](https://www.sqlite.org/foreignkeys.html): thực thi FK, các hành động `ON DELETE` và deferred constraints.

