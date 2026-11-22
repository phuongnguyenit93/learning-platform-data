# Quan hệ một một, một nhiều và nhiều nhiều trong PostgreSQL

Khi thiết kế lược đồ quan hệ, việc chọn kiểu dữ liệu cho từng cột mới là bước đầu. Điều quan trọng tiếp theo là xác định **các thực thể liên hệ với nhau như thế nào**: một khách hàng có bao nhiêu đơn hàng, một đơn hàng có thể chứa bao nhiêu sản phẩm, hay mỗi khách hàng có tối đa một hồ sơ mở rộng?

Trong PostgreSQL, ba dạng quan hệ phổ biến nhất là:

- **Một–một (1:1):** mỗi bản ghi ở phía A có tối đa một bản ghi tương ứng ở phía B và ngược lại.
- **Một–nhiều (1:N):** một bản ghi A có thể liên hệ với nhiều bản ghi B, nhưng mỗi B liên hệ với tối đa hoặc đúng một A theo quy tắc dữ liệu.
- **Nhiều–nhiều (N:M):** một A có thể liên hệ với nhiều B, đồng thời một B cũng có thể liên hệ với nhiều A. Trong lược đồ quan hệ, thường biểu diễn bằng **bảng liên kết**.

Các quan hệ được hiện thực chủ yếu bằng **khóa chính (`PRIMARY KEY`), khóa ngoại (`FOREIGN KEY`), ràng buộc duy nhất (`UNIQUE`) và khả năng cho phép `NULL`**. Thiết kế đúng những ràng buộc này giúp PostgreSQL bảo vệ tính toàn vẹn dữ liệu ngay cả khi nhiều ứng dụng hoặc nhiều transaction cùng ghi.

Bài này xây dựng một ví dụ thương mại điện tử nhỏ với `customers`, `customer_profiles`, `orders`, `products` và `order_items`, sau đó dùng SQL để minh họa cách truy vấn, kiểm tra và bảo trì từng kiểu quan hệ.

## 1. Cardinality và optionality: hai câu hỏi phải tách biệt

**Cardinality** diễn tả số bản ghi tối đa mà một thực thể có thể liên hệ: một hay nhiều. **Optionality** diễn tả một liên hệ có bắt buộc hay không: tối thiểu bằng không hay một.

Ví dụ câu “Một khách hàng có một hồ sơ” còn mơ hồ:

- **Mỗi khách hàng bắt buộc có đúng một hồ sơ** hay có thể chưa tạo hồ sơ?
- **Mỗi hồ sơ bắt buộc thuộc một khách hàng** hay có thể lưu như bản nháp chưa gắn khách hàng?
- Hệ thống có cho phép lưu nhiều phiên bản hồ sơ không?

Tùy câu trả lời, cấu trúc và ràng buộc dữ liệu sẽ khác.

### Các ký hiệu số lượng thường gặp

| Ký hiệu | Cách đọc | Ví dụ |
| --- | --- | --- |
| `0..1` | Không hoặc một | Khách hàng có thể chưa có hồ sơ mở rộng |
| `1..1` | Đúng một | Mỗi đơn hàng phải thuộc một khách hàng |
| `0..N` | Không hoặc nhiều | Khách hàng mới chưa có đơn nào |
| `1..N` | Ít nhất một, có thể nhiều | Đơn hàng đã hoàn tất phải có ít nhất một dòng hàng, nếu nghiệp vụ yêu cầu |

**1:N không có nghĩa mỗi A luôn phải có ít nhất một B.** Một cột khóa ngoại `NOT NULL` ở bảng B đảm bảo rằng mỗi B phải tham chiếu một A hợp lệ; nó không tự ép mỗi A phải có B.

### Sơ đồ tổng quan của bài thực hành

~~~mermaid
erDiagram
    CUSTOMERS ||--o| CUSTOMER_PROFILES : "co hoac khong co"
    CUSTOMERS ||--o{ ORDERS : "dat"
    ORDERS ||--o{ ORDER_ITEMS : "gom"
    PRODUCTS ||--o{ ORDER_ITEMS : "xuat hien trong"
    CUSTOMERS {
        bigint customer_id PK
        text email UK
        text full_name
    }
    CUSTOMER_PROFILES {
        bigint customer_id PK, FK
        text bio
    }
    ORDERS {
        bigint order_id PK
        bigint customer_id FK
    }
    PRODUCTS {
        bigint product_id PK
        text product_name
    }
    ORDER_ITEMS {
        bigint order_id PK, FK
        bigint product_id PK, FK
        integer quantity
    }
~~~

Trong sơ đồ, quan hệ **orders–products** là N:M khi nhìn ở mức nghiệp vụ, nhưng ở mức lưu trữ được tách thành hai quan hệ 1:N từ `orders` và `products` tới `order_items`.

## 2. Khóa chính và khóa ngoại giải quyết vấn đề nào?

### PRIMARY KEY: xác định một bản ghi duy nhất

~~~sql
CREATE TABLE example_customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL
);
~~~

`PRIMARY KEY` đảm bảo mỗi hàng có một giá trị khóa khác `NULL` và không trùng lặp. PostgreSQL tạo một **unique B-tree index** phù hợp để thực thi ràng buộc khóa chính.

Khóa chính có thể là một cột hoặc tổ hợp nhiều cột:

~~~sql
CREATE TABLE example_pairs (
    left_id bigint NOT NULL,
    right_id bigint NOT NULL,
    PRIMARY KEY (left_id, right_id)
);
~~~

Với khóa chính ghép, cặp hai giá trị phải duy nhất; từng cột riêng lẻ vẫn có thể lặp lại.

### FOREIGN KEY: đảm bảo tham chiếu tồn tại

~~~sql
CREATE TABLE example_orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES example_customers(customer_id)
);
~~~

Khóa ngoại đảm bảo `customer_id` của một đơn hàng trỏ tới khách hàng tồn tại (trừ khi cột cho phép `NULL` và dùng ngữ nghĩa `NULL` phù hợp).

Có hai ràng buộc độc lập:

1. `FOREIGN KEY`: khi có giá trị tham chiếu, giá trị đó phải hợp lệ ở bảng cha.
2. `NOT NULL`: cột không được bỏ trống, tức mỗi đơn phải được gắn với khách hàng.

**Khóa ngoại một mình không giới hạn số đơn của một khách hàng.** Nhiều hàng `example_orders` có thể có cùng `customer_id`; đó chính là nền tảng của quan hệ 1:N.

### UNIQUE: giới hạn số bản ghi ở phía tham chiếu

Nếu một cột khóa ngoại cũng được khai báo `UNIQUE`, nhiều hàng con không thể cùng tham chiếu một giá trị cha không rỗng. Đây là một cách thực hiện 1:1.

Trong PostgreSQL, một khóa ngoại phải tham chiếu tới khóa chính hoặc một khóa/cột có tính duy nhất phù hợp ở bảng được tham chiếu. Không thể tham chiếu tùy tiện tới cột chứa giá trị trùng lặp rồi mong database tự xác định hàng cha.

## 3. Quan hệ 1:1: mỗi khách hàng có tối đa một hồ sơ

Giả sử bảng `customers` chứa dữ liệu cơ bản; bảng `customer_profiles` chứa phần hồ sơ mở rộng:

~~~text
customers
---------
customer_id (PK)
email
full_name

customer_profiles
-----------------
customer_id (PK, FK -> customers.customer_id)
bio
birthday
~~~

Lựa chọn này gọi là **shared primary key**: khóa chính của bản ghi hồ sơ đồng thời là khóa ngoại tới khách hàng.

### SQL tạo bảng 1:1

~~~sql
CREATE TABLE customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL
);

CREATE TABLE customer_profiles (
    customer_id bigint PRIMARY KEY
        REFERENCES customers(customer_id)
        ON DELETE CASCADE,
    birthday date,
    bio text
);
~~~

Những điều được PostgreSQL đảm bảo:

- Không thể thêm hai hồ sơ có cùng `customer_id` vì cột là `PRIMARY KEY`.
- Không thể có hồ sơ trỏ tới khách hàng không tồn tại vì `FOREIGN KEY`.
- Một hồ sơ hợp lệ luôn có `customer_id` khác `NULL` vì cột là khóa chính.
- Khách hàng **có thể chưa có hồ sơ**, vì không có ràng buộc nào bắt buộc mọi hàng `customers` phải xuất hiện trong `customer_profiles`.

Do đó đây là quan hệ **customers 0..1 profiles**, còn mỗi profile gắn với **đúng một customer**.

### Tại sao dùng shared primary key?

Ưu điểm:

1. Không cần thêm cột `profile_id` chỉ để định danh một thực thể có vòng đời gắn trực tiếp với khách hàng.
2. Khóa chung diễn đạt rõ “một hồ sơ cho mỗi khách hàng”.
3. Truy vấn `JOIN` đơn giản, không cần một ràng buộc unique bổ sung.
4. Nếu xóa khách hàng theo chính sách được phép, `ON DELETE CASCADE` có thể tự xóa hồ sơ phụ thuộc.

Hạn chế: nếu sau này một khách hàng phải có **nhiều hồ sơ lịch sử**, quan hệ 1:1 không còn phù hợp; cần thiết kế phiên bản hoặc quan hệ 1:N.

### Phương án khác: khóa chính riêng + UNIQUE foreign key

Một lựa chọn vẫn hợp lệ là:

~~~sql
CREATE TABLE customer_profiles_v2 (
    profile_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL UNIQUE
        REFERENCES customers(customer_id),
    bio text
);
~~~

`profile_id` là định danh của hồ sơ, còn `UNIQUE(customer_id)` đảm bảo một khách hàng tối đa một hồ sơ. Cách này phù hợp nếu hồ sơ có ID độc lập cần được tham chiếu ở nơi khác.

Không chỉ dùng:

~~~sql
customer_id bigint REFERENCES customers(customer_id)
~~~

và gọi đó là 1:1. Nếu thiếu `UNIQUE` hoặc shared primary key, nhiều hàng hồ sơ có thể trỏ cùng khách hàng, làm quan hệ thực tế trở thành 1:N.

### Có bắt buộc khách hàng phải có một hồ sơ không?

Chưa. `customer_profiles.customer_id` là `PRIMARY KEY`/`FOREIGN KEY` chỉ bảo đảm **hồ sơ nào tồn tại thì có khách hàng hợp lệ**. Nó không bắt buộc khi thêm khách hàng phải thêm hồ sơ ngay.

Nếu yêu cầu thật sự là **mỗi khách hàng luôn có đúng một hồ sơ**, cần một phương án thiết kế bổ sung, ví dụ:

- Gộp các thuộc tính vào cùng bảng nếu chúng cùng vòng đời và luôn tồn tại.
- Tạo khách hàng và hồ sơ trong một transaction nghiệp vụ, đồng thời có cơ chế bảo vệ bất biến khi các luồng ghi khác can thiệp.
- Thiết kế ràng buộc trì hoãn/circular dependency hoặc trigger phù hợp trong trường hợp bắt buộc tách bảng, với hiểu biết đầy đủ về thời điểm kiểm tra ràng buộc.

**Một foreign key một chiều không tự diễn đạt điều kiện “mọi khách hàng phải có hồ sơ”.**

## 4. Quan hệ 1:N: một khách hàng có nhiều đơn hàng

Trong mô hình đơn hàng:

~~~text
customers (1) ---- (0..N) orders
~~~

Mỗi đơn hàng thuộc **đúng một** khách hàng, trong khi một khách hàng có thể có 0, 1 hoặc nhiều đơn hàng.

~~~sql
CREATE TABLE orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES customers(customer_id)
        ON DELETE RESTRICT,
    ordered_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled'))
);
~~~

Chìa khóa thiết kế là **khóa ngoại nằm ở phía nhiều**: `orders.customer_id`. Nếu đặt danh sách các `order_id` vào một cột ở `customers`, việc kiểm tra tồn tại và truy vấn quan hệ sẽ trở nên khó hơn nhiều.

### Cách đọc ràng buộc

| Ràng buộc | Điều được bảo vệ |
| --- | --- |
| `orders.order_id PRIMARY KEY` | Không có hai đơn trùng ID |
| `orders.customer_id REFERENCES customers` | Không gắn đơn với khách hàng không tồn tại |
| `orders.customer_id NOT NULL` | Không có đơn không được gắn khách hàng |
| **Không có UNIQUE trên orders.customer_id** | Nhiều đơn được phép cùng thuộc một khách hàng |
| `ON DELETE RESTRICT` | Không xóa được khách hàng vẫn bị đơn hàng tham chiếu |

`ON DELETE RESTRICT` trong ví dụ phù hợp với tư duy **không xóa mất khách hàng khi còn đơn giao dịch cần giữ**. Những hệ thống có yêu cầu lưu trữ hóa đơn/chứng từ có thể cần chính sách bất biến dữ liệu và lưu trữ lâu dài phức tạp hơn.

### Khi quan hệ 1:N có thể tùy chọn ở phía con

Đôi khi một yêu cầu chưa được gán người phụ trách:

~~~sql
assignee_id bigint NULL REFERENCES employees(employee_id)
~~~

Khi đó một hàng công việc có thể **không gắn nhân viên nào**. Đây vẫn là dạng một–nhiều từ nhân viên tới công việc, nhưng mỗi công việc gắn với **0 hoặc 1** nhân viên thay vì đúng 1.

Quyết định `NULL` hay `NOT NULL` phải dựa vào nghiệp vụ, không chỉ dựa vào cụm từ “một–nhiều”.

### PostgreSQL có tự tạo index cho khóa ngoại không?

PostgreSQL tạo index hỗ trợ `PRIMARY KEY` và `UNIQUE` ở phía được tham chiếu. Nhưng nó **không tự tạo index trên mọi cột khóa ngoại ở bảng con**.

Với `orders.customer_id`, thường nên cân nhắc:

~~~sql
CREATE INDEX idx_orders_customer_id
ON orders(customer_id);
~~~

Chỉ mục có thể giúp truy vấn “lấy đơn của khách hàng X” và một số thao tác kiểm tra khóa ngoại khi cập nhật/xóa bản ghi cha. Quyết định cuối cùng vẫn cần dựa trên số hàng, điều kiện truy vấn, tần suất ghi và kế hoạch thực thi.

## 5. Quan hệ N:M: đơn hàng chứa nhiều sản phẩm, sản phẩm ở nhiều đơn

Ở mức nghiệp vụ:

~~~text
orders (0..N) <----> (0..N) products
~~~

Một đơn có thể có nhiều sản phẩm; một sản phẩm có thể xuất hiện ở nhiều đơn khác nhau. Hệ thống quan hệ thường không lưu quan hệ N:M bằng cột chứa danh sách ID, mà tạo **bảng liên kết**:

~~~text
orders (1) --- (0..N) order_items (0..N) --- (1) products
~~~

Mỗi dòng `order_items` gắn **một đơn** với **một sản phẩm**. Tập các dòng làm nên mối quan hệ nhiều–nhiều.

### SQL thiết kế bảng liên kết

~~~sql
CREATE TABLE products (
    product_id bigint PRIMARY KEY,
    product_name text NOT NULL,
    current_price numeric(12,2) NOT NULL CHECK (current_price >= 0)
);

CREATE TABLE order_items (
    order_id bigint NOT NULL
        REFERENCES orders(order_id)
        ON DELETE CASCADE,
    product_id bigint NOT NULL
        REFERENCES products(product_id)
        ON DELETE RESTRICT,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price_at_order numeric(12,2) NOT NULL
        CHECK (unit_price_at_order >= 0),
    PRIMARY KEY (order_id, product_id)
);
~~~

`order_items` chứa:

- `order_id`: khóa ngoại tới đơn hàng.
- `product_id`: khóa ngoại tới sản phẩm.
- `quantity`: số lượng sản phẩm trong đơn.
- `unit_price_at_order`: **giá tại thời điểm mua**, tránh tính lại lịch sử đơn theo giá catalog hiện tại.
- `PRIMARY KEY(order_id, product_id)`: một sản phẩm có tối đa một dòng tổng hợp trong mỗi đơn.

Ví dụ quan hệ:

| order_id | product_id | quantity | Nghĩa |
| ---: | ---: | ---: | --- |
| 1001 | 501 | 2 | Đơn 1001 mua hai sản phẩm 501 |
| 1001 | 502 | 1 | Đơn 1001 mua một sản phẩm 502 |
| 1002 | 503 | 3 | Đơn 1002 mua ba sản phẩm 503 |
| 1003 | 501 | 1 | Sản phẩm 501 cũng xuất hiện ở đơn 1003 |

Như vậy **một đơn có nhiều sản phẩm**, đồng thời **một sản phẩm thuộc nhiều đơn**, nhưng mỗi bản ghi liên kết vẫn được kiểm soát bằng hai khóa ngoại.

### Khi nào không nên dùng cặp ID làm PRIMARY KEY?

Nếu nghiệp vụ cho phép cùng một sản phẩm xuất hiện nhiều lần trong một đơn, ví dụ các dòng có đợt giảm giá, lô hàng hoặc cấu hình sản phẩm khác nhau, `PRIMARY KEY(order_id, product_id)` sẽ quá chặt.

Khi đó có thể dùng:

~~~sql
CREATE TABLE order_item_lines (
    order_item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES orders(order_id),
    product_id bigint NOT NULL REFERENCES products(product_id),
    line_number integer NOT NULL CHECK (line_number > 0),
    quantity integer NOT NULL CHECK (quantity > 0),
    UNIQUE (order_id, line_number)
);
~~~

Thiết kế này cho phép hai dòng khác nhau cùng `product_id` trong một `order_id`, nhưng giữ số dòng duy nhất trong mỗi đơn. Nên chọn ràng buộc theo **đơn vị nghiệp vụ thực tế**, không áp dụng khóa ghép chỉ vì đó là mô hình sách giáo khoa.

### Có nên dùng mảng product_id thay bảng liên kết?

Một cột như `orders.product_ids bigint[]` hoặc chuỗi `'501,502,503'` có thể lưu được danh sách, nhưng không tương đương với bảng N:M có foreign key và dữ liệu quan hệ:

- Khó dùng khóa ngoại chuẩn để bảo đảm **từng phần tử** trong mảng tham chiếu sản phẩm tồn tại.
- Không có vị trí tự nhiên cho các thuộc tính của liên kết như số lượng và giá mua.
- Khó áp dụng `UNIQUE(order_id,product_id)`, kiểm soát trùng lặp và cascade theo từng liên kết.
- Câu JOIN, thống kê và cập nhật từng phần tử có thể phức tạp hơn.

PostgreSQL hỗ trợ arrays và JSONB cho các bài toán thích hợp, nhưng với quan hệ thực thể cần tính toàn vẹn tham chiếu, **junction table** thường là lựa chọn rõ ràng hơn.

## 6. Bộ SQL thực hành hoàn chỉnh trong một schema riêng

Phần này kết hợp cả ba quan hệ thành ví dụ có thể chạy trong database lab. Tạo một database phát triển riêng, ví dụ `relationship_lab`, và kết nối bằng role có quyền tạo schema. **Chỉ chạy lệnh reset khi chắc chắn schema `relation_lab` là của bài tập và không chứa dữ liệu cần giữ.**

### Bước 1: Tạo lại schema và các bảng

~~~sql
-- CHỈ CHẠY TRONG database thực hành.
DROP SCHEMA IF EXISTS relation_lab CASCADE;
CREATE SCHEMA relation_lab;

-- Bảng gốc: khách hàng.
CREATE TABLE relation_lab.customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL
);

-- 1:1 tùy chọn: mỗi khách hàng có tối đa một profile.
CREATE TABLE relation_lab.customer_profiles (
    customer_id bigint PRIMARY KEY
        REFERENCES relation_lab.customers(customer_id)
        ON DELETE CASCADE,
    birthday date,
    bio text
);

-- 1:N: mỗi đơn bắt buộc thuộc một khách hàng.
CREATE TABLE relation_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES relation_lab.customers(customer_id)
        ON DELETE RESTRICT,
    ordered_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled'))
);

-- Danh mục sản phẩm.
CREATE TABLE relation_lab.products (
    product_id bigint PRIMARY KEY,
    product_name text NOT NULL,
    current_price numeric(12,2) NOT NULL
        CHECK (current_price >= 0)
);

-- N:M orders - products qua bảng liên kết.
CREATE TABLE relation_lab.order_items (
    order_id bigint NOT NULL
        REFERENCES relation_lab.orders(order_id)
        ON DELETE CASCADE,
    product_id bigint NOT NULL
        REFERENCES relation_lab.products(product_id)
        ON DELETE RESTRICT,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price_at_order numeric(12,2) NOT NULL
        CHECK (unit_price_at_order >= 0),
    PRIMARY KEY (order_id, product_id)
);

-- Các chỉ mục bổ sung thường hữu ích cho chiều truy cập từ con.
CREATE INDEX idx_orders_customer
    ON relation_lab.orders(customer_id);

CREATE INDEX idx_order_items_product
    ON relation_lab.order_items(product_id);
~~~

Các bảng đều dùng tên đầy đủ `relation_lab.table_name`, tránh phụ thuộc vào `search_path`. Chỉ mục khóa chính và `UNIQUE` được PostgreSQL tạo để thực thi ràng buộc; chỉ mục `idx_orders_customer` và `idx_order_items_product` được thêm riêng cho những đường truy cập từ khóa ngoại.

### Bước 2: Nạp dữ liệu cố định

~~~sql
BEGIN;

INSERT INTO relation_lab.customers
    (customer_id, email, full_name)
VALUES
    (1, 'an@example.test',   'An'),
    (2, 'binh@example.test', 'Binh'),
    (3, 'chi@example.test',  'Chi');

INSERT INTO relation_lab.customer_profiles
    (customer_id, birthday, bio)
VALUES
    (1, DATE '1998-05-10', 'Khach hang than thiet'),
    (2, DATE '2000-09-02', 'Uu tien giao trong ngay');

INSERT INTO relation_lab.orders
    (order_id, customer_id, ordered_at, status)
VALUES
    (1001, 1, '2026-11-01 08:00:00+00', 'paid'),
    (1002, 1, '2026-11-02 09:00:00+00', 'paid'),
    (1003, 2, '2026-11-03 10:00:00+00', 'pending');

INSERT INTO relation_lab.products
    (product_id, product_name, current_price)
VALUES
    (501, 'Mouse',    200.00),
    (502, 'Keyboard', 400.00),
    (503, 'Cable',     50.00);

INSERT INTO relation_lab.order_items
    (order_id, product_id, quantity, unit_price_at_order)
VALUES
    (1001, 501, 2, 180.00),
    (1001, 502, 1, 400.00),
    (1002, 503, 3,  50.00),
    (1003, 501, 1, 200.00),
    (1003, 503, 1,  50.00);

COMMIT;
~~~

Dữ liệu có chủ ý:

- Khách hàng **An** có profile và hai đơn.
- **Binh** có profile và một đơn.
- **Chi** chưa có profile và chưa có đơn.
- Đơn **1001** có hai sản phẩm; sản phẩm **501** xuất hiện ở cả đơn 1001 và 1003.
- Giá sản phẩm 501 lúc mua ở đơn 1001 là 180.00, khác `current_price` hiện tại là 200.00.

Nhờ dữ liệu cố định, chúng ta có thể dự đoán kết quả truy vấn mà không cần phụ thuộc thời điểm chạy.

## 7. Truy vấn 1:1 bằng LEFT JOIN

Muốn lấy **tất cả khách hàng**, kể cả người chưa tạo hồ sơ:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    p.birthday,
    p.bio
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.customer_profiles AS p
    ON p.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Kết quả mong đợi:

| customer_id | full_name | birthday | bio |
| ---: | --- | --- | --- |
| 1 | An | 1998-05-10 | Khach hang than thiet |
| 2 | Binh | 2000-09-02 | Uu tien giao trong ngay |
| 3 | Chi | NULL | NULL |

`LEFT JOIN` giữ khách hàng Chi. Nếu dùng `INNER JOIN`, Chi bị loại vì không có bản ghi tương ứng trong `customer_profiles`.

### Tìm khách hàng chưa có profile

~~~sql
SELECT c.customer_id, c.full_name
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.customer_profiles AS p
    ON p.customer_id = c.customer_id
WHERE p.customer_id IS NULL
ORDER BY c.customer_id;
~~~

Kết quả: khách hàng Chi, ID 3.

Có thể dùng `NOT EXISTS`:

~~~sql
SELECT c.customer_id, c.full_name
FROM relation_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM relation_lab.customer_profiles AS p
    WHERE p.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Ở cả hai cách, **không tìm profile** là dữ kiện nghiệp vụ, không mặc định là lỗi ràng buộc khi quan hệ 1:1 cho phép tùy chọn.

## 8. Truy vấn 1:N và cách đếm đúng

### Lấy đơn của một khách hàng

~~~sql
SELECT
    o.order_id,
    o.ordered_at,
    o.status
FROM relation_lab.orders AS o
WHERE o.customer_id = 1
ORDER BY o.order_id;
~~~

Dự kiến có đơn 1001 và 1002.

### Đếm số đơn theo khách hàng, kể cả 0 đơn

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Kết quả:

| customer_id | full_name | order_count |
| ---: | --- | ---: |
| 1 | An | 2 |
| 2 | Binh | 1 |
| 3 | Chi | 0 |

**Đừng dùng `COUNT(*)` để đếm đơn** sau `LEFT JOIN` trong ví dụ này. Với Chi, phép nối ngoài vẫn tạo một hàng có các cột `orders` là `NULL`; `COUNT(*)` sẽ cho 1, trong khi `COUNT(o.order_id)` cho 0.

### Lọc trạng thái mà không làm mất khách hàng chưa có đơn

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_orders
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Kết quả: An 2, Binh 0, Chi 0. Nếu đặt điều kiện `o.status = 'paid'` ở `WHERE`, các hàng không có đơn khớp sẽ bị loại theo ngữ nghĩa SQL, làm thay đổi mục đích của `LEFT JOIN`.

## 9. Truy vấn N:M bằng bảng liên kết

### Liệt kê sản phẩm trong một đơn

~~~sql
SELECT
    o.order_id,
    p.product_id,
    p.product_name,
    oi.quantity,
    oi.unit_price_at_order,
    (oi.quantity * oi.unit_price_at_order)
        AS line_amount
FROM relation_lab.orders AS o
JOIN relation_lab.order_items AS oi
    ON oi.order_id = o.order_id
JOIN relation_lab.products AS p
    ON p.product_id = oi.product_id
WHERE o.order_id = 1001
ORDER BY p.product_id;
~~~

Kết quả mong đợi:

| order_id | product_id | product_name | quantity | unit_price_at_order | line_amount |
| ---: | ---: | --- | ---: | ---: | ---: |
| 1001 | 501 | Mouse | 2 | 180.00 | 360.00 |
| 1001 | 502 | Keyboard | 1 | 400.00 | 400.00 |

**Tổng đơn 1001 = 760.00.** Không dùng giá hiện tại của sản phẩm 501 để tính lại dòng lịch sử vì giá có thể thay đổi sau thời điểm mua.

### Tính tổng tiền cho mọi đơn

~~~sql
SELECT
    o.order_id,
    COALESCE(
        SUM(oi.quantity * oi.unit_price_at_order), 0
    )::numeric(14,2) AS order_amount
FROM relation_lab.orders AS o
LEFT JOIN relation_lab.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Kết quả:

| order_id | order_amount |
| ---: | ---: |
| 1001 | 760.00 |
| 1002 | 150.00 |
| 1003 | 250.00 |

`LEFT JOIN` cho phép thấy cả đơn hiện chưa có dòng hàng (khi schema cho phép). `COALESCE` chuyển kết quả `SUM` là `NULL` thành 0 trong trường hợp đó.

### Xem một sản phẩm xuất hiện trong những đơn nào

~~~sql
SELECT
    p.product_id,
    p.product_name,
    o.order_id,
    o.status,
    oi.quantity
FROM relation_lab.products AS p
JOIN relation_lab.order_items AS oi
    ON oi.product_id = p.product_id
JOIN relation_lab.orders AS o
    ON o.order_id = oi.order_id
WHERE p.product_id = 501
ORDER BY o.order_id;
~~~

Sản phẩm 501 xuất hiện ở đơn 1001 và 1003. Đây là chiều ngược của quan hệ N:M, cũng dùng cùng bảng liên kết.

### Đếm số đơn có từng sản phẩm

~~~sql
SELECT
    p.product_id,
    p.product_name,
    COUNT(oi.order_id) AS number_of_orders
FROM relation_lab.products AS p
LEFT JOIN relation_lab.order_items AS oi
    ON oi.product_id = p.product_id
GROUP BY p.product_id, p.product_name
ORDER BY p.product_id;
~~~

Vì `PRIMARY KEY(order_id, product_id)` bảo đảm mỗi cặp chỉ có một dòng, `COUNT(oi.order_id)` ở thiết kế này cho số đơn khác nhau có sản phẩm đó. Nếu dùng thiết kế `order_item_lines` cho phép nhiều dòng cùng sản phẩm/đơn, phải dùng `COUNT(DISTINCT oi.order_id)` nếu mục tiêu là số đơn, không phải số dòng.

## 10. Bẫy nhân số hàng khi JOIN nhiều quan hệ 1:N

Một khách hàng có hai đơn; mỗi đơn lại có nhiều dòng hàng. Khi nối cả ba bảng:

~~~sql
SELECT
    c.customer_id,
    o.order_id,
    oi.product_id
FROM relation_lab.customers AS c
JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
JOIN relation_lab.order_items AS oi
    ON oi.order_id = o.order_id
WHERE c.customer_id = 1
ORDER BY o.order_id, oi.product_id;
~~~

Khách hàng An có **hai đơn**, nhưng kết quả có **ba dòng hàng**: đơn 1001 hai sản phẩm và đơn 1002 một sản phẩm.

Nếu viết:

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count
FROM relation_lab.customers AS c
JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
JOIN relation_lab.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY c.customer_id;
~~~

thì số lượng `o.order_id` có thể bị **đếm lặp** vì mỗi đơn xuất hiện một lần cho mỗi item.

Cách sửa phù hợp với mục đích “đếm đơn có ít nhất một item”:

~~~sql
SELECT
    c.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN relation_lab.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Tuy nhiên, nếu chỉ cần **đếm toàn bộ đơn** bất kể có item hay không, cách tốt hơn là **không JOIN `order_items` khi không cần**. Cần hiểu mối quan hệ làm nhân tập hàng trước khi tổng hợp, không thêm `DISTINCT` theo thói quen để che mọi vấn đề.

### Tổng hợp trước khi JOIN

Đối với báo cáo nhiều cấp, đôi khi rõ hơn nếu tổng hợp theo đơn trước:

~~~sql
WITH order_totals AS (
    SELECT
        oi.order_id,
        SUM(oi.quantity * oi.unit_price_at_order) AS amount
    FROM relation_lab.order_items AS oi
    GROUP BY oi.order_id
)
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(ot.amount), 0)::numeric(14,2)
        AS total_amount
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_totals AS ot
    ON ot.order_id = o.order_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Kết quả mong đợi: An có hai đơn với tổng 910.00, Binh có một đơn tổng 250.00, Chi không có đơn tổng 0.00. Đây là ví dụ về cách tách **đơn vị tổng hợp** để tránh nhân số liệu khi tham gia nhiều quan hệ.

## 11. Điều gì xảy ra khi dữ liệu vi phạm quan hệ?

Một ưu điểm của việc thiết kế quan hệ bằng constraint là PostgreSQL từ chối những thao tác không hợp lệ, bất kể client nào đang ghi.

### 11.1. Trùng hồ sơ trong 1:1

Sau khi đã có profile cho khách hàng 1:

~~~sql
-- Ví dụ cố ý gây lỗi unique/primary key:
INSERT INTO relation_lab.customer_profiles
    (customer_id, bio)
VALUES
    (1, 'Mot profile thu hai');
~~~

PostgreSQL sẽ báo lỗi vi phạm khóa chính/unique (SQLSTATE `23505`). Điều này là bằng chứng ràng buộc **tối đa một profile mỗi customer** đang hoạt động.

### 11.2. Hồ sơ trỏ tới khách hàng không tồn tại

~~~sql
-- Ví dụ cố ý gây lỗi foreign key:
INSERT INTO relation_lab.customer_profiles
    (customer_id, bio)
VALUES
    (9999, 'Khong co customer 9999');
~~~

PostgreSQL từ chối với lỗi khóa ngoại (SQLSTATE `23503`), vì khách hàng 9999 không tồn tại.

### 11.3. Đơn hàng không có khách hàng

~~~sql
-- Ví dụ cố ý gây lỗi NOT NULL:
INSERT INTO relation_lab.orders
    (order_id, customer_id, ordered_at, status)
VALUES
    (2000, NULL, now(), 'pending');
~~~

Cột `customer_id NOT NULL` khiến câu SQL thất bại (SQLSTATE `23502`). Chỉ để `FOREIGN KEY` mà bỏ `NOT NULL` sẽ không đạt quy tắc “mỗi đơn bắt buộc có khách hàng”.

### 11.4. Hai dòng trùng cặp order–product

~~~sql
-- Đơn 1001 đã có sản phẩm 501.
INSERT INTO relation_lab.order_items
    (order_id, product_id, quantity, unit_price_at_order)
VALUES
    (1001, 501, 1, 180.00);
~~~

Câu SQL sẽ thất bại do `PRIMARY KEY(order_id,product_id)`. Nếu mục tiêu là tăng số lượng sản phẩm đã có, ứng dụng cần **UPDATE** hoặc **INSERT ... ON CONFLICT ... DO UPDATE** theo ngữ nghĩa nghiệp vụ, không chèn một dòng trùng khóa.

**Các câu trên là bài kiểm thử lỗi, không phải dữ liệu seed thành công.** Trong `psql`, sau lỗi trong một transaction đang mở, transaction thường ở trạng thái aborted và cần `ROLLBACK` trước khi chạy tiếp; hãy thực hành các câu riêng biệt hoặc dùng savepoint/transaction có kiểm soát.

## 12. INSERT ... ON CONFLICT trong bảng liên kết

Bảng `order_items` có khóa ghép nên phù hợp với một số thao tác upsert.

Ví dụ muốn thêm 2 đơn vị sản phẩm 501 vào đơn 1001 và giữ nguyên giá đã chốt:

~~~sql
INSERT INTO relation_lab.order_items
    (order_id, product_id, quantity, unit_price_at_order)
VALUES
    (1001, 501, 2, 180.00)
ON CONFLICT (order_id, product_id)
DO UPDATE SET
    quantity = relation_lab.order_items.quantity
             + EXCLUDED.quantity;
~~~

`EXCLUDED.quantity` là giá trị được đề xuất trong câu `INSERT`. Với dữ liệu ban đầu, quantity của (1001,501) sẽ tăng từ 2 thành 4. Đây là **thao tác có thay đổi dữ liệu lab**: muốn giữ kết quả các bài tính tổng như ban đầu, hãy dùng transaction rồi `ROLLBACK` hoặc reset lab sau khi thử.

Không coi mọi upsert cộng dồn là **idempotent**. Nếu một yêu cầu bị gửi lặp lại, quantity tiếp tục tăng. Hệ thống thực tế cần xác định rõ idempotency key và quy tắc xử lý request trùng.

## 13. Hành vi ON DELETE và ON UPDATE ảnh hưởng quan hệ

Khi xóa bản ghi cha, khóa ngoại cần biết phải xử lý các hàng con thế nào. PostgreSQL hỗ trợ nhiều hành động tham chiếu:

| Hành động | Ý nghĩa khi xóa/cập nhật bản ghi được tham chiếu |
| --- | --- |
| `NO ACTION` | Cho phép thao tác nếu ràng buộc vẫn thỏa khi được kiểm tra; có thể xét deferred nếu constraint cho phép |
| `RESTRICT` | Chặn thao tác đang bị tham chiếu theo ngữ nghĩa hạn chế ngay, không áp dụng trì hoãn như `NO ACTION` |
| `CASCADE` | Tự xóa hoặc cập nhật khóa liên quan ở hàng con theo kiểu thao tác |
| `SET NULL` | Đặt cột FK ở hàng con thành `NULL`, chỉ hợp lý nếu ràng buộc/cột cho phép |
| `SET DEFAULT` | Đặt cột FK về giá trị mặc định; giá trị đó vẫn phải thỏa ràng buộc liên quan |

Trong ví dụ lab:

- Xóa khách hàng có profile: `customer_profiles ON DELETE CASCADE` có thể tự xóa profile.
- Xóa khách hàng đang có đơn: `orders ON DELETE RESTRICT` ngăn xóa khách hàng.
- Xóa một đơn: `order_items ON DELETE CASCADE` xóa các dòng hàng của đơn.
- Xóa sản phẩm đang được dùng trong đơn: `order_items.product_id ON DELETE RESTRICT` ngăn xóa sản phẩm, giúp giữ tham chiếu lịch sử.

**Không mặc định CASCADE là cách đơn giản nhất.** Trong hệ thống giao dịch, xóa khách hàng, đơn hàng hoặc sản phẩm có thể liên quan tới yêu cầu lưu trữ và kiểm toán; việc xóa dây chuyền có thể làm mất dữ liệu quan trọng.

### Ví dụ SET NULL cho quan hệ tùy chọn

Một phiếu hỗ trợ có thể chưa được giao nhân viên:

~~~sql
CREATE TABLE employees (
    employee_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE support_tickets (
    ticket_id bigint PRIMARY KEY,
    assignee_id bigint NULL
        REFERENCES employees(employee_id)
        ON DELETE SET NULL
);
~~~

Khi xóa nhân viên được gán, ticket vẫn tồn tại nhưng `assignee_id` trở thành `NULL`. Nếu đặt `assignee_id NOT NULL`, cách thiết kế `ON DELETE SET NULL` sẽ xung đột với ràng buộc và thao tác xóa có thể thất bại. Đây là lý do chọn **cách xử lý xóa và tính bắt buộc của quan hệ** cùng lúc.

## 14. Bảng liên kết cũng có vòng đời và quyền riêng

Bảng N:M không nhất thiết chỉ chứa hai khóa ngoại. Nhiều quan hệ thực tế có **thuộc tính của chính mối liên kết**:

| Quan hệ nghiệp vụ | Bảng liên kết | Thuộc tính liên kết có thể cần |
| --- | --- | --- |
| Sinh viên – khóa học | `enrollments` | Ngày đăng ký, điểm, trạng thái |
| Người dùng – nhóm quyền | `user_roles` | Người cấp quyền, thời hạn, nguồn cấp |
| Đơn hàng – sản phẩm | `order_items` | Số lượng, giá tại thời điểm mua, giảm giá |
| Bác sĩ – bệnh nhân | `care_assignments` | Vai trò, thời gian bắt đầu/kết thúc |
| Nhân viên – dự án | `project_members` | Vai trò, ngày tham gia |

Ví dụ sinh viên–khóa học:

~~~sql
CREATE TABLE students (
    student_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE courses (
    course_id bigint PRIMARY KEY,
    course_name text NOT NULL
);

CREATE TABLE enrollments (
    student_id bigint NOT NULL REFERENCES students(student_id),
    course_id bigint NOT NULL REFERENCES courses(course_id),
    enrolled_at timestamptz NOT NULL DEFAULT now(),
    grade numeric(4,2),
    PRIMARY KEY (student_id, course_id)
);
~~~

Ở đây `enrolled_at` và `grade` thuộc **lần ghi danh**, không thuộc riêng sinh viên hoặc riêng khóa học.

Nếu cho phép sinh viên học lại cùng khóa ở nhiều học kỳ, `PRIMARY KEY(student_id,course_id)` không đủ linh hoạt. Có thể thêm `semester_id` vào khóa ghép hoặc dùng `enrollment_id` riêng và constraint phù hợp. Lựa chọn phụ thuộc đơn vị nghiệp vụ “một lần ghi danh” là gì.

## 15. Composite key hay surrogate key cho junction table?

Hai cách phổ biến:

**Khóa ghép tự nhiên của quan hệ:**

~~~sql
PRIMARY KEY (student_id, course_id)
~~~

Ưu điểm: biểu đạt rõ không có hai liên kết trùng cặp; không cần ID mới. Bất lợi: các bảng khác tham chiếu tới một enrollment có thể phải mang hai cột FK; khi quan hệ được phép có nhiều phiên bản, cần mở rộng khóa.

**Khóa thay thế:**

~~~sql
enrollment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
student_id bigint NOT NULL REFERENCES students(student_id),
course_id bigint NOT NULL REFERENCES courses(course_id),
UNIQUE (student_id, course_id)
~~~

Nếu nghiệp vụ **vẫn** yêu cầu không trùng cặp, ràng buộc `UNIQUE(student_id,course_id)` phải được giữ. Chỉ thêm `enrollment_id` mà bỏ uniqueness dễ tạo dữ liệu trùng liên kết.

Không có cách nào luôn tối ưu. Khi bảng liên kết còn được tham chiếu bởi hệ thống khác, có nhiều thuộc tính hoặc có vòng đời riêng, surrogate key có thể thuận tiện. Khi mối liên kết đơn giản và một cặp chỉ xuất hiện một lần, composite key thường ngắn gọn.

## 16. UNIQUE, NULL và quan hệ 1:1 tùy chọn

Giả sử thiết kế một bảng có `customer_id` nullable và unique:

~~~sql
CREATE TABLE draft_profiles (
    draft_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint UNIQUE REFERENCES relation_lab.customers(customer_id),
    draft_text text
);
~~~

Theo ngữ nghĩa `UNIQUE` mặc định của PostgreSQL, nhiều hàng có `customer_id IS NULL` **có thể cùng tồn tại**, trong khi mỗi giá trị `customer_id` không `NULL` chỉ được xuất hiện một lần.

Điều này có thể đúng nếu draft chưa được gắn khách hàng. Nhưng nếu yêu cầu dữ liệu là “mọi draft phải thuộc đúng một khách hàng”, cần `customer_id NOT NULL`.

Từ PostgreSQL 15, có cú pháp `UNIQUE NULLS NOT DISTINCT` để xem các giá trị NULL là không phân biệt cho mục đích ràng buộc duy nhất. Đây là lựa chọn cho những quy tắc đặc biệt, **không phải yêu cầu bắt buộc của mọi mô hình 1:1**.

### Điều kiện unique chỉ áp dụng cho một nhóm hàng

Giả sử khách hàng có nhiều địa chỉ nhưng chỉ **tối đa một địa chỉ mặc định**. Đây không phải 1:1 giữa khách hàng và tất cả địa chỉ; tổng thể vẫn là 1:N, cộng thêm quy tắc "tối đa một địa chỉ mặc định".

PostgreSQL hỗ trợ **partial unique index**:

~~~sql
CREATE TABLE customer_addresses (
    address_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES relation_lab.customers(customer_id),
    address_text text NOT NULL,
    is_default boolean NOT NULL DEFAULT false
);

CREATE UNIQUE INDEX uq_one_default_address_per_customer
ON customer_addresses(customer_id)
WHERE is_default = true;
~~~

Chỉ những hàng có `is_default = true` tham gia chỉ mục unique này. Một khách hàng có thể có nhiều địa chỉ, nhưng không thể có **hai địa chỉ cùng mặc định**. Tuy nhiên, constraint đó **không bắt buộc phải có ít nhất một** địa chỉ mặc định.

Ví dụ cho thấy nên phân biệt **cardinality tổng thể** với **điều kiện duy nhất có lọc** của nghiệp vụ.

## 17. Index cho khóa ngoại và chiều JOIN

Các quan hệ đúng logic vẫn cần được quan sát về hiệu năng.

- `PRIMARY KEY` và `UNIQUE` tạo index phù hợp ở các cột được định nghĩa.
- PostgreSQL **không mặc định tạo index cho mọi cột FOREIGN KEY ở phía con**.
- Một primary key ghép `(order_id,product_id)` thường hỗ trợ truy cập theo `order_id` là cột đứng đầu.
- Truy vấn tìm các đơn theo `product_id` cần cân nhắc index riêng vì `product_id` là cột thứ hai trong khóa ghép.
- Xóa hoặc cập nhật hàng cha có thể cần tìm các hàng con tham chiếu; index trên FK thường hữu ích ở bảng lớn.

Vì vậy bài lab có:

~~~sql
CREATE INDEX idx_orders_customer
ON relation_lab.orders(customer_id);

CREATE INDEX idx_order_items_product
ON relation_lab.order_items(product_id);
~~~

Ví dụ đo kế hoạch:

~~~sql
EXPLAIN
SELECT order_id
FROM relation_lab.orders
WHERE customer_id = 1;
~~~

Và:

~~~sql
EXPLAIN
SELECT order_id
FROM relation_lab.order_items
WHERE product_id = 501;
~~~

**Một bảng chỉ vài hàng có thể được quét tuần tự** dù có index. Điều này không chứng minh index bị vô hiệu: PostgreSQL có thể chọn seq scan vì chi phí thấp hơn ở dữ liệu nhỏ. Với dữ liệu thật, cần xem `EXPLAIN (ANALYZE, BUFFERS)`, phân bố hàng, thống kê và workload. Lưu ý `EXPLAIN ANALYZE` thực sự chạy câu SQL; với `UPDATE`/`DELETE` phải dùng môi trường an toàn và transaction phù hợp.

## 18. Quan hệ N:M có thể thêm các thuộc tính nghiệp vụ phức tạp

Bảng liên kết không chỉ là một “bảng kỹ thuật”. Trong nhiều hệ thống, nó trở thành một thực thể nghiệp vụ đầy đủ.

Ví dụ `order_items` có `quantity`, `unit_price_at_order`. Nếu mở rộng:

~~~sql
ALTER TABLE relation_lab.order_items
ADD COLUMN discount_amount numeric(12,2) NOT NULL DEFAULT 0
    CHECK (discount_amount >= 0);
~~~

Thì giảm giá thuộc **dòng hàng trong đơn**, không thuộc toàn bộ sản phẩm. Sản phẩm 501 có thể được bán với giá hoặc chương trình giảm giá khác nhau ở từng đơn.

Nếu nghiệp vụ yêu cầu `discount_amount <= quantity * unit_price_at_order`, có thể đặt thêm `CHECK` dựa trên các cột cùng hàng:

~~~sql
ALTER TABLE relation_lab.order_items
ADD CONSTRAINT chk_discount_not_over_line_total
CHECK (
    discount_amount <= quantity * unit_price_at_order
);
~~~

PostgreSQL `CHECK` được thiết kế để kiểm tra biểu thức trên **hàng hiện tại**, không phải công cụ chung để ép các tổng hợp liên bảng như “tổng chiết khấu của đơn không vượt ngân sách khách hàng”. Các bất biến liên bảng cần thiết kế transaction, trigger hoặc cơ chế thích hợp khác.

## 19. Tính bắt buộc “ít nhất một” thường cần bảo vệ riêng

Với schema lab, `orders` có thể tồn tại mà chưa có `order_items`. Từ góc nhìn nghiệp vụ, đơn hàng dạng `draft` có thể hợp lệ khi chưa có sản phẩm. Nhưng khi chuyển trạng thái sang `paid`, hệ thống thường phải đòi **ít nhất một dòng hàng**.

Khóa ngoại từ `order_items.order_id` tới `orders.order_id` chỉ đảm bảo “mọi item có đơn”. Nó **không** đảm bảo “mọi đơn có ít nhất một item”.

Những phương án có thể cân nhắc:

1. Cho phép đơn ở trạng thái `pending`/`draft` chưa có item; khi chuyển sang `paid`, thực hiện kiểm tra tồn tại item trong cùng transaction và có cơ chế chống race condition phù hợp.
2. Sử dụng trigger/constraint trigger với logic cần thiết và cân nhắc thời điểm kiểm tra.
3. Thiết kế workflow tạo đơn và item như một transaction nguyên tử rồi chuyển sang trạng thái được phép công khai.

Không nên cố biến một foreign key đơn giản thành lời hứa cho mọi bất biến hai chiều.

Tương tự, `UNIQUE` trong 1:1 đảm bảo **tối đa một**, không đảm bảo **ít nhất một**; `PRIMARY KEY(order_id,product_id)` đảm bảo cặp duy nhất, không ép đơn có item.

## 20. Transaction khi tạo bản ghi cha và con

Giả sử ứng dụng muốn thêm khách hàng và profile cùng lúc:

~~~sql
BEGIN;

INSERT INTO relation_lab.customers
    (customer_id, email, full_name)
VALUES
    (4, 'dung@example.test', 'Dung');

INSERT INTO relation_lab.customer_profiles
    (customer_id, birthday, bio)
VALUES
    (4, DATE '1997-01-01', 'Khach hang moi');

COMMIT;
~~~

Trong transaction, nếu tạo profile gặp lỗi và ứng dụng thực hiện `ROLLBACK`, cả khách hàng vừa tạo cũng được hoàn tác, tránh trạng thái một nửa của thao tác nghiệp vụ.

Tương tự, tạo đơn và các dòng hàng trong cùng transaction:

~~~sql
BEGIN;

INSERT INTO relation_lab.orders
    (order_id, customer_id, ordered_at, status)
VALUES
    (1004, 1, '2026-11-04 09:00:00+00', 'pending');

INSERT INTO relation_lab.order_items
    (order_id, product_id, quantity, unit_price_at_order)
VALUES
    (1004, 502, 1, 400.00);

COMMIT;
~~~

Nếu muốn thí nghiệm mà không giữ dữ liệu:

~~~sql
BEGIN;

INSERT INTO relation_lab.orders
    (order_id, customer_id, ordered_at, status)
VALUES
    (9999, 1, '2026-11-05 09:00:00+00', 'pending');

ROLLBACK;
~~~

`ROLLBACK` hoàn tác đơn 9999 chưa commit. **Transaction không thay thế constraint**, và constraint không thay thế transaction: hai cơ chế phối hợp để bảo vệ tính đúng đắn khi nhiều thao tác phải xảy ra cùng nhau.

## 21. Thiết kế quan hệ khi dữ liệu phát triển

Một quan hệ thường bắt đầu đơn giản rồi thay đổi theo nghiệp vụ.

### Từ 1:1 sang 1:N

Ban đầu khách hàng có một địa chỉ giao hàng:

~~~text
customers (1) -- (0..1) shipping_address
~~~

Sau đó ứng dụng cho phép nhiều địa chỉ; cần bảng `customer_addresses` với khóa chính riêng và `customer_id` không `UNIQUE`. Nếu có quy tắc một địa chỉ mặc định, dùng partial unique index như mục 16.

Khi chuyển đổi, phải quản lý data migration, API và cách các query `JOIN` có thể nhân số hàng.

### Từ 1:N sang N:M

Ban đầu một nhân viên chỉ thuộc một nhóm:

~~~text
employees.team_id -> teams.team_id
~~~

Khi được phép làm ở nhiều nhóm, chuyển thành bảng `employee_teams(employee_id,team_id,...)`. Không nên thêm cột `team_id_2`, `team_id_3` hay chuỗi danh sách ID trong bảng nhân viên.

### Khi nào không cần tách 1:1?

Nếu một nhóm cột luôn cùng vòng đời, luôn được đọc chung và không có yêu cầu quyền/phân tách cụ thể, có thể giữ chúng trong một bảng để đơn giản hóa mô hình. Tách 1:1 nên có lý do: vòng đời, nhóm quyền, dữ liệu tùy chọn lớn, tổ chức module hoặc nhu cầu mở rộng khác.

Tách bảng vô điều kiện có thể tăng số JOIN và dependency mà không tạo lợi ích tương ứng.

## 22. Kiểm tra ràng buộc và quan hệ trong PostgreSQL

### Qua psql

Trong CLI `psql`:

~~~text
\d relation_lab.customers
\d relation_lab.customer_profiles
\d relation_lab.orders
\d relation_lab.products
\d relation_lab.order_items
~~~

Kết quả hiển thị cột, khóa chính, index và foreign key tương ứng. Đây là meta-command của `psql`, không phải câu SQL chuẩn gửi trực tiếp từ JDBC.

### Qua catalog pg_constraint

~~~sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint AS c
JOIN pg_class AS t
    ON t.oid = c.conrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'relation_lab'
ORDER BY t.relname, c.conname;
~~~

`contype` thường dùng các mã như `p` (primary key), `f` (foreign key), `u` (unique) và `c` (check). `pg_get_constraintdef` giúp xem câu định nghĩa ràng buộc để kiểm tra logic đang lưu trong database thật sự, thay vì chỉ tin vào tài liệu thiết kế.

### Tìm các bảng và cột khóa ngoại

~~~sql
SELECT
    tc.table_schema,
    tc.table_name,
    tc.constraint_name,
    kcu.column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_catalog = kcu.constraint_catalog
   AND tc.constraint_schema = kcu.constraint_schema
   AND tc.constraint_name = kcu.constraint_name
   AND tc.table_name = kcu.table_name
WHERE tc.table_schema = 'relation_lab'
  AND tc.constraint_type = 'FOREIGN KEY'
ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position;
~~~

`information_schema` có thể phụ thuộc quyền của role đang truy vấn. Nếu bảng hoặc ràng buộc không xuất hiện, phải xem cả quyền truy cập và phạm vi schema trước khi kết luận không có foreign key.

## 23. Các lỗi thiết kế thường gặp

### Lỗi 1: Viết một–một nhưng quên UNIQUE ở bảng con

Chỉ có `FOREIGN KEY` cho phép nhiều bản ghi con cùng tham chiếu một bản ghi cha. Dùng `UNIQUE(fk)` hoặc shared primary key nếu phải giới hạn tối đa một.

### Lỗi 2: Đặt FOREIGN KEY ở sai phía của quan hệ 1:N

Một khách hàng có nhiều đơn, nên `customer_id` thường nằm trong `orders`. Nếu muốn lưu nhiều order ID trong một cột `customers`, mô hình sẽ khó kiểm soát tham chiếu và cập nhật.

### Lỗi 3: Cho phép NULL dù nghiệp vụ yêu cầu quan hệ bắt buộc

Khóa ngoại nullable cho phép hàng không gắn parent. Kết hợp `NOT NULL` khi mỗi hàng con phải có parent.

### Lỗi 4: Coi UNIQUE tự bảo đảm ít nhất một hàng liên kết

`UNIQUE` chỉ ngăn trùng; nó không tạo hàng con cho mọi cha. Bắt buộc ít nhất một thường cần workflow/logic hoặc thiết kế bổ sung.

### Lỗi 5: Lưu quan hệ N:M bằng chuỗi danh sách ID

Khó kiểm tra từng tham chiếu, xử lý xóa, lưu thuộc tính liên kết và JOIN. Dùng bảng liên kết nếu cần bảo đảm referential integrity theo mô hình quan hệ.

### Lỗi 6: Chỉ thêm ID tự tăng rồi quên uniqueness nghiệp vụ

`order_item_id` riêng không ngăn hai dòng giống hệt `(order_id,product_id)`. Nếu mỗi cặp được phép xuất hiện một lần, vẫn cần `UNIQUE(order_id,product_id)`.

### Lỗi 7: Dùng COUNT(*) sau LEFT JOIN để đếm bản ghi con

Bảng cha không có bản ghi con vẫn tạo một hàng được bảo toàn. Dùng `COUNT(child.id)` để đếm các hàng con có thật.

### Lỗi 8: JOIN quá nhiều quan hệ rồi SUM/COUNT bị nhân số lần

Quan hệ 1:N nối tiếp có thể làm một thực thể xuất hiện nhiều dòng. Xác định **đơn vị tổng hợp**, dùng `COUNT(DISTINCT ...)` hoặc tổng hợp từng cấp trước khi JOIN khi phù hợp.

### Lỗi 9: Dùng ON DELETE CASCADE không xét vòng đời dữ liệu

Xóa khách hàng có thể kéo theo xóa lịch sử đơn và hóa đơn nếu cascade được cấp bừa bãi. Chọn `RESTRICT`/`NO ACTION`, soft deletion hoặc chính sách lưu trữ phù hợp.

### Lỗi 10: Nghĩ FOREIGN KEY tự tạo index trên bảng con

PostgreSQL không tự tạo mọi index phía tham chiếu. Xem workload JOIN, lọc theo FK và thao tác xóa/cập nhật parent để quyết định chỉ mục bổ sung.

### Lỗi 11: Quên rằng giá trong product catalog có thể đổi

Nếu báo cáo lịch sử đơn dùng `products.current_price` thay vì `order_items.unit_price_at_order`, tổng tiền quá khứ có thể thay đổi không đúng. Thuộc tính của quan hệ phải lưu ở thực thể thích hợp.

### Lỗi 12: Đổi quan hệ mà không di chuyển dữ liệu và sửa query

Chuyển từ 1:1 sang 1:N hoặc 1:N sang N:M đòi migration, index, quyền, API và cách tổng hợp. Sửa DDL đơn lẻ không đủ.

## 24. Bài tập thực hành và kết quả mong đợi

Các bài dưới đây dùng lại schema và dữ liệu mục 6, **trước khi chạy các ví dụ INSERT/UPDATE mở rộng**.

### Bài 1: Khách hàng chưa có profile

Viết câu SQL dùng `LEFT JOIN` hoặc `NOT EXISTS` để tìm khách hàng chưa có hồ sơ.

**Đáp án mẫu:**

~~~sql
SELECT c.customer_id, c.full_name
FROM relation_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM relation_lab.customer_profiles AS p
    WHERE p.customer_id = c.customer_id
);
~~~

Kết quả: Chi, ID 3.

### Bài 2: Số đơn của từng khách hàng

~~~sql
SELECT c.customer_id, COUNT(o.order_id) AS order_count
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Kết quả: `(1,2)`, `(2,1)`, `(3,0)`. Nếu dùng `COUNT(*)`, giá trị của Chi không đúng yêu cầu đếm đơn thực.

### Bài 3: Tổng tiền theo đơn

~~~sql
SELECT
    oi.order_id,
    SUM(oi.quantity * oi.unit_price_at_order)
        AS total_amount
FROM relation_lab.order_items AS oi
GROUP BY oi.order_id
ORDER BY oi.order_id;
~~~

Kết quả: đơn 1001 = 760.00, đơn 1002 = 150.00, đơn 1003 = 250.00. Câu này chỉ hiển thị các đơn **có item**; muốn hiển thị cả đơn không có item, dùng `LEFT JOIN` từ `orders`.

### Bài 4: Một sản phẩm được mua ở bao nhiêu đơn?

~~~sql
SELECT
    p.product_id,
    p.product_name,
    COUNT(oi.order_id) AS order_count
FROM relation_lab.products AS p
LEFT JOIN relation_lab.order_items AS oi
    ON oi.product_id = p.product_id
GROUP BY p.product_id, p.product_name
ORDER BY p.product_id;
~~~

Kết quả: Mouse (501) có 2 đơn, Keyboard (502) có 1 đơn, Cable (503) có 2 đơn.

### Bài 5: Tại sao không thể có hai profile cho An?

Thử chèn một profile nữa có `customer_id = 1`. Ràng buộc nào chặn? Nếu chuyển sang bảng có `profile_id PRIMARY KEY` riêng, phải thêm gì để vẫn đảm bảo một–một?

**Đáp án:** `PRIMARY KEY(customer_id)` chặn; với khóa chính riêng cần `UNIQUE(customer_id)` và `NOT NULL` khi bắt buộc mỗi profile phải gắn customer.

### Bài 6: Thiết kế sinh viên–môn học

Hãy viết ba bảng `students`, `courses` và `enrollments`. Quy tắc: mỗi sinh viên có thể học nhiều môn; mỗi môn có nhiều sinh viên; một sinh viên chỉ được ghi danh một lần cho mỗi môn trong một học kỳ.

**Gợi ý:** Bảng `enrollments` có ba foreign key/thuộc tính định danh, và `UNIQUE(student_id,course_id,semester_id)` hoặc một composite primary key tương ứng. Xác định rõ semester phải là bảng riêng hay giá trị theo domain khi thiết kế thực tế.

### Bài 7: Chọn hành vi xóa

Một hệ thống cho phép xóa một đơn nháp cùng các dòng hàng, nhưng không cho xóa khách hàng vẫn có đơn và không cho xóa sản phẩm đã xuất hiện trong đơn. Những `ON DELETE` nào thích hợp?

**Đáp án theo mô hình lab:** `orders.customer_id ON DELETE RESTRICT`, `order_items.order_id ON DELETE CASCADE` và `order_items.product_id ON DELETE RESTRICT`. Tuy nhiên, cần bổ sung điều kiện “đơn nháp mới được xóa” ở nghiệp vụ/transaction hoặc ràng buộc phù hợp; `ON DELETE CASCADE` đơn thuần không phân biệt trạng thái đơn.

### Bài 8: Giải thích bẫy JOIN

An có hai đơn nhưng ba dòng `order_items`. Vì sao `COUNT(o.order_id)` sau khi JOIN thêm `order_items` trả 3, không phải 2?

**Đáp án:** Mỗi hàng đơn được lặp lại một lần cho mỗi dòng sản phẩm. Cần đếm ở đúng cấp quan hệ, chẳng hạn truy vấn `orders` trước hoặc `COUNT(DISTINCT o.order_id)` khi mục đích và phép nối phù hợp.

## 25. Quy trình ra quyết định khi thiết kế mối quan hệ

Khi chuyển yêu cầu nghiệp vụ thành lược đồ PostgreSQL, có thể theo trình tự:

1. **Xác định thực thể:** ai hoặc cái gì có bản sắc độc lập? Ví dụ khách hàng, đơn hàng, sản phẩm.
2. **Xác định số lượng tối đa mỗi chiều:** A có bao nhiêu B và B có bao nhiêu A? Đừng chỉ hỏi một chiều.
3. **Xác định số lượng tối thiểu:** B có bắt buộc gắn A không? A có bắt buộc có ít nhất một B không?
4. **Chọn nơi đặt khóa ngoại:** 1:N đặt FK ở phía nhiều; 1:1 dùng unique FK/shared PK; N:M dùng junction table.
5. **Thêm NOT NULL/UNIQUE/PRIMARY KEY/CHECK:** bảo đảm các quy tắc có thể diễn đạt trực tiếp bằng constraint.
6. **Chọn hành vi xóa/cập nhật:** `CASCADE`, `RESTRICT`, `NO ACTION` hay `SET NULL` theo vòng đời dữ liệu.
7. **Thiết kế thuộc tính liên kết:** ví dụ quantity/price nằm trên `order_items`, không đặt vào một trong hai phía một cách gượng ép.
8. **Tạo index cần thiết:** nhất là trên FK phía con và các chiều truy vấn thường dùng.
9. **Kiểm tra query thực tế:** `JOIN`, `LEFT JOIN`, `COUNT` và `SUM` có thể làm nhân số hàng.
10. **Kiểm tra các bất biến ngoài phạm vi FK:** “ít nhất một item”, trạng thái nghiệp vụ, đồng thời và workflow cần giải pháp bổ sung.

Không nên bắt đầu từ câu hỏi “dùng bao nhiêu bảng?” rồi cố ép nghiệp vụ cho khớp. Bắt đầu từ **các ràng buộc thật của dữ liệu**, sau đó chọn mô hình và SQL biểu diễn chính xác những ràng buộc đó.

## 26. Tổng kết

Ba dạng quan hệ phổ biến trong PostgreSQL có cách lưu rõ ràng:

| Quan hệ | Cách biểu diễn thường gặp | Constraint quan trọng |
| --- | --- | --- |
| **1:1** | Bảng con có shared PK hoặc FK duy nhất | `FOREIGN KEY` + `PRIMARY KEY` / `UNIQUE` |
| **1:N** | FK nằm ở bảng phía nhiều | `FOREIGN KEY`, thêm `NOT NULL` nếu quan hệ bắt buộc ở phía con |
| **N:M** | Bảng liên kết chứa FK tới hai phía | Hai `FOREIGN KEY` và khóa ghép/`UNIQUE` theo đơn vị liên kết |

**Cardinality và optionality phải được xác định riêng.** Khóa ngoại đảm bảo tham chiếu hợp lệ; unique giới hạn trùng lặp; not null yêu cầu có giá trị. Một số quy tắc như “mỗi khách hàng phải có hồ sơ” hoặc “đơn đã thanh toán phải có item” cần thêm thiết kế ngoài một foreign key đơn giản.

Khi hiểu được ba mối quan hệ này, người học có thể thiết kế dữ liệu ít trùng lặp hơn, biểu diễn quy tắc nghiệp vụ bằng constraint, viết JOIN đúng số lượng và bảo trì lược đồ PostgreSQL dễ dàng hơn khi ứng dụng phát triển.
