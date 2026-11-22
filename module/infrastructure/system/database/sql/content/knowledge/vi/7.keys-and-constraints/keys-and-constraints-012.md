# Phân biệt ràng buộc dữ liệu với chỉ mục hỗ trợ

Trong cơ sở dữ liệu quan hệ, **ràng buộc dữ liệu** (*constraint*) và **chỉ mục** (*index*) thường xuất hiện cùng nhau. Khi tạo `PRIMARY KEY` hoặc `UNIQUE`, nhiều hệ quản trị tự tạo một chỉ mục để thực thi yêu cầu không trùng lặp. Vì vậy, người mới học SQL dễ kết luận rằng “ràng buộc và chỉ mục là một”. Thực tế, chúng trả lời **hai câu hỏi khác nhau**:

- **Ràng buộc:** *Dữ liệu nào được phép tồn tại trong bảng?* Nó diễn đạt quy tắc toàn vẹn và có thể từ chối một thao tác `INSERT`, `UPDATE` hoặc `DELETE` làm dữ liệu vi phạm quy tắc.
- **Chỉ mục:** *Làm thế nào tìm, nối, lọc hoặc sắp xếp các dòng hiệu quả hơn?* Nó là một cấu trúc hỗ trợ truy cập dữ liệu, được hệ quản trị duy trì khi bảng thay đổi.

Có **vùng giao nhau**: một **unique index** vừa là cấu trúc truy cập vừa **ngăn các giá trị trùng theo khóa chỉ mục**. Một `PRIMARY KEY` hoặc `UNIQUE` constraint trong PostgreSQL thường được một unique B-tree index hỗ trợ. Tuy nhiên, `CHECK` và `FOREIGN KEY` không đồng nghĩa với việc có chỉ mục, và một index thường không thể thay thế các quy tắc toàn vẹn đó.

Bài học này nằm trong chương **Khóa và ràng buộc** của Database SQL, tập trung vào cách thiết kế, đọc và kiểm tra sự khác biệt này. Ví dụ chạy thực hành dùng **PostgreSQL**; phần cuối nêu khác biệt quan trọng với MySQL và SQLite.

## 1. Mô hình tư duy: quy tắc dữ liệu và đường đi tới dữ liệu

Hãy hình dung một hệ thống bán hàng có ba bảng:

```text
customers
  customer_id (PK)
  email (UNIQUE)
  full_name (NOT NULL)
       │
       │ 1 khách hàng có thể có nhiều đơn
       ▼
orders
  order_id (PK)
  customer_id (FK → customers.customer_id)
  total_amount (CHECK >= 0)
  placed_at
       │
       │ 1 đơn có thể có nhiều dòng sản phẩm
       ▼
order_items
  order_id (FK → orders.order_id)
  line_no
  quantity (CHECK > 0)
  (PK: order_id, line_no)
```

Trong mô hình này:

- **`customers.customer_id` là khóa chính:** không được trống, không được trùng; mỗi khách hàng có một định danh.
- **`customers.email` có ràng buộc duy nhất:** không cho hai khách hàng có cùng email theo quy tắc so sánh áp dụng. Cách xử lý `NULL` và phân biệt chữ hoa/thường cần xét riêng.
- **`orders.customer_id` là khóa ngoại:** mỗi mã khách trong đơn phải trỏ đến một khách hàng tồn tại, theo chính sách ràng buộc đã khai báo.
- **`orders.total_amount >= 0` là điều kiện hợp lệ:** số tiền âm không được lưu nếu ràng buộc bắt buộc điều đó.
- **Index trên `orders(customer_id, placed_at)`** có thể tăng tốc việc tìm đơn của một khách theo ngày. Tự thân index thông thường **không bắt buộc khách hàng phải tồn tại** và **không ngăn tiền âm**.

Một cách tách trách nhiệm:

```text
Yêu cầu nghiệp vụ / tính toàn vẹn
          │
          ▼
PRIMARY KEY • UNIQUE • FOREIGN KEY • CHECK • NOT NULL
          │
          │ được hệ quản trị kiểm tra khi dữ liệu đổi
          ▼
Các trạng thái dữ liệu được phép tồn tại

Yêu cầu truy vấn / đường truy cập
          │
          ▼
CREATE INDEX • cấu trúc B-tree / loại index khác
          │
          │ được bộ tối ưu cân nhắc khi chạy truy vấn
          ▼
Giảm công đọc, lọc, nối hoặc sắp xếp khi thích hợp
```

Nhận biết câu hỏi thuộc nhóm nào sẽ giúp tránh hai sai lầm: chỉ tạo index mà quên quy tắc dữ liệu, hoặc chỉ tạo constraint rồi cho rằng mọi truy vấn liên quan đã có đủ index để chạy nhanh.

## 2. Ràng buộc dữ liệu là một cam kết về trạng thái bảng

**Constraint** được khai báo trong lược đồ (*schema*) và là một phần quy tắc về dữ liệu. Khi một thao tác thay đổi dữ liệu khiến ràng buộc không còn được thỏa mãn, hệ quản trị từ chối thao tác hoặc giao dịch theo thời điểm kiểm tra áp dụng.

| Ràng buộc | Điều gì phải đúng? | Có tự tạo index trong PostgreSQL? |
|---|---|---|
| `PRIMARY KEY` | Một bộ cột xác định duy nhất mỗi dòng; cột khóa không được `NULL` | **Có**, unique B-tree index hỗ trợ |
| `UNIQUE` | Các bộ giá trị khóa không được trùng theo quy tắc xử lý `NULL` | **Có**, unique B-tree index hỗ trợ |
| `FOREIGN KEY` | Giá trị tham chiếu phải có dòng cha tương ứng hoặc thỏa quy tắc `NULL` | **Không tự tạo index trên cột khóa ngoại phía bảng con** |
| `CHECK` | Biểu thức kiểm tra không được là `FALSE` | **Không** |
| `NOT NULL` | Cột phải có giá trị khác `NULL` | **Không** |

### 2.1. `PRIMARY KEY`: định danh dòng

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL
);
```

Ở đây, mỗi dòng phải có một `customer_id` khác `NULL` và không trùng với dòng nào khác. Một bảng thông thường chỉ có **một ràng buộc `PRIMARY KEY`**, nhưng khóa chính có thể gồm **nhiều cột**.

Trong PostgreSQL, việc khai báo `PRIMARY KEY` khiến hệ thống tạo một **unique B-tree index** trên cột khóa nếu chưa có index thích hợp được cung cấp qua con đường hỗ trợ. Index đó giúp kiểm tra tính duy nhất, đồng thời có thể dùng để truy cập theo khóa. Bởi vậy, khi xem danh sách index của bảng, ta thường thấy index mang tên gắn với khóa chính.

### 2.2. `UNIQUE`: tính duy nhất của một giá trị nghiệp vụ

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE
);
```

Ràng buộc `UNIQUE(username)` diễn đạt quy tắc: không có hai tài khoản dùng cùng một tên đăng nhập theo quy tắc so sánh của cột. PostgreSQL tạo unique index hỗ trợ ràng buộc này.

Có thể khai báo nhiều ràng buộc `UNIQUE` trên một bảng, khác với `PRIMARY KEY` chỉ có một. Một bảng có thể dùng khóa kỹ thuật như `account_id` làm khóa chính và vẫn bảo vệ khóa nghiệp vụ như `username` hoặc `(tenant_id, external_id)` bằng `UNIQUE`.

**Lưu ý về `NULL`:** trong PostgreSQL, `UNIQUE` mặc định cho phép nhiều dòng có `NULL` ở khóa duy nhất, vì `NULL` được coi là **không trùng nhau** cho mục đích ràng buộc này. Muốn cột không được trống, phải thêm `NOT NULL`. Từ PostgreSQL 15 có cú pháp `UNIQUE NULLS NOT DISTINCT (...)` để xem các giá trị `NULL` là không phân biệt khi kiểm tra duy nhất. Hành vi xử lý `NULL` của unique constraint khác nhau giữa các hệ quản trị.

### 2.3. `FOREIGN KEY`: bảo đảm mối quan hệ tham chiếu

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
```

Một đơn hàng chỉ được tham chiếu một khách hàng có thật trong `customers`. Nếu cố chèn `customer_id` không tồn tại, ràng buộc khóa ngoại sẽ từ chối thao tác.

**Chỉ tạo index trên `orders.customer_id` không cung cấp tính toàn vẹn tham chiếu.** Index biết những giá trị nào có trong bảng đơn, nhưng không tự kiểm tra xem từng giá trị có xuất hiện ở bảng khách hàng hay không. Khóa ngoại cần quy tắc tham chiếu được khai báo riêng.

Trong PostgreSQL, cột được tham chiếu ở bảng cha phải có khóa chính, ràng buộc duy nhất không trì hoãn thích hợp, hoặc unique index không partial đáp ứng điều kiện tham chiếu. Nhưng **phía bảng con không tự được tạo index chỉ vì có khóa ngoại**. Đây là khác biệt quan trọng khi thiết kế truy vấn và thao tác xóa/cập nhật dòng cha.

### 2.4. `CHECK`: chặn giá trị vi phạm biểu thức

```sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    price NUMERIC(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    CONSTRAINT ck_products_price_nonnegative CHECK (price >= 0),
    CONSTRAINT ck_products_stock_nonnegative CHECK (stock_quantity >= 0)
);
```

`CHECK` kiểm tra **điều kiện của dữ liệu**, không phải cách truy cập nó. Một B-tree index trên `price` có thể giúp tìm sản phẩm theo khoảng giá, nhưng **không làm số tiền âm trở nên bất hợp lệ**. Nếu muốn cấm giá âm, cần `CHECK (price >= 0)`.

Trong PostgreSQL, `CHECK` được xem là thỏa nếu biểu thức trả `TRUE` **hoặc `UNKNOWN` do `NULL`**; chỉ `FALSE` làm hàng bị từ chối. Vì vậy:

```sql
-- Chỉ CHECK này chưa đủ để cấm NULL.
price NUMERIC(12, 2) CHECK (price >= 0)

-- Muốn cấm cả NULL và số âm:
price NUMERIC(12, 2) NOT NULL CHECK (price >= 0)
```

Thông thường `CHECK` nên diễn đạt điều kiện của chính dòng đang ghi; không nên dùng nó như cách tự tạo truy vấn liên bảng để thay cho `FOREIGN KEY`, hoặc để diễn đạt một quy tắc phức tạp cần kiểm tra nhiều dòng.

## 3. Index là cấu trúc hỗ trợ truy cập, có chi phí duy trì

Index tương tự mục lục sách: thay vì đọc mọi trang để tìm một mục, hệ thống có thể lần theo cấu trúc đã được sắp tổ chức.

Ví dụ:

```sql
CREATE INDEX idx_orders_customer_placed
    ON orders (customer_id, placed_at);
```

Index B-tree nhiều cột này có thể hỗ trợ truy vấn:

```sql
SELECT order_id, placed_at
FROM orders
WHERE customer_id = 42
ORDER BY placed_at DESC;
```

Với bảng đủ lớn và thống kê phù hợp, bộ tối ưu có thể dùng index để thu hẹp số dòng cần đọc hoặc hỗ trợ thứ tự truy cập. Tuy nhiên, **`CREATE INDEX` không buộc PostgreSQL phải sử dụng index cho mọi truy vấn**: nếu bảng nhỏ, phần lớn dòng thỏa điều kiện, hoặc kế hoạch quét toàn bảng rẻ hơn, hệ quản trị có thể chọn `Seq Scan`.

Index đi kèm chi phí:

- Cần **dung lượng lưu trữ** và bộ nhớ đệm.
- Phải được **cập nhật khi dữ liệu thay đổi**; thêm quá nhiều index có thể làm `INSERT`, `UPDATE`, `DELETE` tốn công hơn.
- Cần bảo trì và thống kê phù hợp; không có một bộ index tối ưu cho mọi loại truy vấn.
- Index nhiều cột có **thứ tự cột**; `ON orders(customer_id, placed_at)` không được coi là hoàn toàn giống `ON orders(placed_at, customer_id)` trong cách hỗ trợ tìm kiếm.

Một index thông thường mặc định **cho phép giá trị khóa lặp**. Một cột `customer_id` trong `orders` phải cho phép nhiều đơn của cùng khách hàng, nên index hỗ trợ khóa ngoại ở bảng con thường **không phải unique index**.

## 4. Vùng giao nhau: `UNIQUE` constraint và unique index

Vì sao một index có thể bảo vệ tính duy nhất?

```sql
CREATE UNIQUE INDEX ux_accounts_username
    ON accounts (username);
```

Khác với `CREATE INDEX` thông thường, `CREATE UNIQUE INDEX` trong PostgreSQL từ chối việc thêm hoặc sửa dòng khiến **khóa được index bị trùng** theo quy tắc tương ứng. Đây là ví dụ index **có tác dụng thực thi toàn vẹn**.

Tuy nhiên, cần phân biệt **cơ chế** và **ý định trong schema**:

```sql
-- Diễn đạt ràng buộc nghiệp vụ trong định nghĩa bảng.
CREATE TABLE members (
    member_id BIGINT PRIMARY KEY,
    member_code TEXT NOT NULL,
    CONSTRAINT uq_members_member_code UNIQUE (member_code)
);

-- Index phục vụ truy vấn, không thêm ràng buộc mới về uniqueness.
CREATE INDEX idx_members_member_code
    ON members (member_code);
```

Trong ví dụ, `uq_members_member_code` đã khiến PostgreSQL tạo một unique index hỗ trợ. Tạo thêm `idx_members_member_code` cùng danh sách cột, cùng cách so sánh và phạm vi thường **dư thừa**; nó không làm tính duy nhất “mạnh hơn”, mà tăng chi phí lưu trữ và cập nhật.

**Khác biệt thực tế giữa hai con đường:**

| Tiêu chí | `UNIQUE` constraint | `CREATE UNIQUE INDEX` |
|---|---|---|
| Mục tiêu chính | Công bố quy tắc dữ liệu trong schema | Tạo cấu trúc index có kiểm tra duy nhất |
| PostgreSQL tạo index hỗ trợ? | Có | Bản thân lệnh tạo index |
| Khai báo trong `CREATE TABLE` / `ALTER TABLE ... ADD CONSTRAINT` | Có | Thường dùng lệnh index riêng |
| Điều kiện lọc một phần (`WHERE`) | Không dùng được trực tiếp với `UNIQUE` constraint thông thường | Có thể tạo **partial unique index** |
| Khóa theo biểu thức như `lower(email)` | Constraint thông thường yêu cầu cột | Có thể tạo **expression unique index** |
| Metadata trong `pg_constraint` | Có | Unique index đứng riêng thường không xuất hiện như một `UNIQUE` constraint |
| Dùng làm khóa được tham chiếu bởi `FOREIGN KEY` | Có nếu đáp ứng quy tắc loại/độ trì hoãn | Trong PostgreSQL, unique index **không partial** phù hợp có thể được dùng; partial/expression index không thay thế khóa tham chiếu thường |

Trong PostgreSQL, có thể dùng một unique index tồn tại sẵn làm index hỗ trợ cho `PRIMARY KEY`/`UNIQUE` constraint khi đáp ứng các điều kiện của `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX`. Điều đó không có nghĩa mọi unique index được tự động ghi nhận thành table constraint.

### 4.1. Partial unique index: duy nhất trong một tập con

Quy tắc nghiệp vụ: **email của tài khoản đang hoạt động không được trùng, nhưng tài khoản đã xóa mềm có thể giữ email cũ**.

```sql
CREATE TABLE app_users (
    user_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX ux_app_users_active_email
    ON app_users (lower(email))
    WHERE deleted_at IS NULL;
```

Index chỉ bao gồm các dòng có `deleted_at IS NULL` và dùng `lower(email)` để kiểm tra trùng không phân biệt chữ hoa/thường theo phép xử lý của PostgreSQL. Vì thế `Alice@example.com` và `alice@example.com` không thể cùng tồn tại trong tập dòng hoạt động theo biểu thức đó. Những dòng đã xóa mềm không nằm trong index.

**Điểm cần phân biệt:** đây là **partial unique expression index**, không phải một `UNIQUE(email)` constraint thông thường. Nó rất hữu ích cho quy tắc duy nhất có điều kiện, nhưng không thể chỉ gọi là “thêm ràng buộc `UNIQUE`” và mong mọi tính năng tham chiếu bằng khóa ngoại hoặc metadata constraint sẽ giống hệt.

Quy tắc xử lý email thực tế cần đặc tả chuẩn hóa, collation và chính sách phân biệt chữ hoa/thường phù hợp; `lower(...)` chỉ minh họa cách index áp dụng biểu thức.

### 4.2. `UNIQUE NULLS NOT DISTINCT`: khi `NULL` cũng phải coi là trùng

PostgreSQL 15 trở lên cho phép:

```sql
CREATE TABLE reservations (
    reservation_id BIGINT PRIMARY KEY,
    booking_code TEXT,
    CONSTRAINT uq_reservations_code UNIQUE NULLS NOT DISTINCT (booking_code)
);
```

Theo ràng buộc này, không thể có **hai dòng cùng `booking_code = NULL`**. Với `UNIQUE (booking_code)` thông thường của PostgreSQL, nhiều `NULL` được cho phép. Nếu không cần lưu `NULL` ở cột mã, yêu cầu trực tiếp và dễ hiểu hơn có thể là `booking_code TEXT NOT NULL UNIQUE`.

## 5. Khóa chính và index hỗ trợ khóa chính

Xét hai khai báo:

```sql
CREATE TABLE categories (
    category_id BIGINT PRIMARY KEY,
    category_name TEXT NOT NULL
);

CREATE TABLE category_labels (
    category_id BIGINT NOT NULL,
    language_code CHAR(2) NOT NULL,
    label_text TEXT NOT NULL,
    CONSTRAINT pk_category_labels PRIMARY KEY (category_id, language_code)
);
```

`categories` dùng khóa chính **một cột**. `category_labels` dùng khóa chính **ghép hai cột**, vì mỗi danh mục có thể có nhiều bản dịch, nhưng cùng một danh mục và mã ngôn ngữ không được xuất hiện hai lần.

PostgreSQL tạo unique index cho cả hai khóa. Với khóa ghép `(category_id, language_code)`, thứ tự cột có ảnh hưởng đến tính hữu ích của index cho truy vấn:

```sql
-- Khớp cột đầu của index khóa ghép, thường thuận lợi:
SELECT *
FROM category_labels
WHERE category_id = 10;

-- Chỉ lọc theo cột thứ hai có thể cần index riêng tùy dữ liệu/truy vấn:
SELECT *
FROM category_labels
WHERE language_code = 'vi';
```

Không nên tạo thêm một index y hệt khóa chính chỉ vì thường xuyên tìm theo khóa chính: **index hỗ trợ khóa chính đã tồn tại**. Nhưng việc có index khóa chính ghép **không đảm bảo mọi truy vấn lọc từng cột đều đã tối ưu**.

## 6. Khóa ngoại không tự sinh index phía tham chiếu trong PostgreSQL

Đây là điểm dễ nhầm nhất khi đọc schema quan hệ.

Giả sử bảng cha là `customers`, bảng con là `orders`:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    placed_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0)
);
```

Sau `CREATE TABLE` trên, PostgreSQL đã có index hỗ trợ `customers.customer_id` và `orders.order_id` vì chúng là khóa chính. Nhưng **chưa tự có index riêng trên `orders.customer_id`** do khai báo `REFERENCES`.

Nếu ứng dụng thường liệt kê đơn của khách hàng hoặc xóa/cập nhật khách hàng, có thể cân nhắc:

```sql
CREATE INDEX idx_orders_customer_id
    ON orders (customer_id);
```

**Vì sao index ở bảng con hữu ích khi xóa dòng cha?** Khi xét một khách hàng bị xóa hoặc thay đổi khóa được tham chiếu, cơ sở dữ liệu phải xác định những đơn đang trỏ tới khách hàng đó để kiểm tra quy tắc `FOREIGN KEY` hoặc thực thi hành động liên quan. Nếu bảng `orders` lớn và không có đường truy cập theo `customer_id`, quá trình tìm các dòng liên quan có thể tốn công.

Trong PostgreSQL, index phía bảng con là **quyết định tối ưu** chứ không phải yêu cầu để khóa ngoại có hiệu lực. Khóa ngoại vẫn kiểm tra tham chiếu ngay cả khi không có index này. Một hệ quản trị khác có thể tự tạo index bắt buộc phù hợp; phần cuối bài nêu khác biệt.

### 6.1. Thứ tự khai báo FK không quyết định cách xóa dữ liệu

Một khóa ngoại có thể quy định hành động tham chiếu:

```sql
CREATE TABLE order_notes (
    note_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    CONSTRAINT fk_order_notes_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
        ON DELETE CASCADE
);
```

`ON DELETE CASCADE` có nghĩa khi xóa một dòng `orders`, các dòng `order_notes` tham chiếu tới đơn đó cũng bị xóa theo. Quy tắc này thuộc về **foreign key**, không thuộc về index trên `order_notes.order_id`.

Nếu không khai báo `ON DELETE ...`, PostgreSQL mặc định dùng `NO ACTION`. Một thao tác xóa cha còn dòng con tham chiếu sẽ vi phạm ràng buộc tại thời điểm kiểm tra áp dụng. `CASCADE` có tác động xóa dữ liệu nên chỉ chọn khi đúng nghiệp vụ, không phải giải pháp tăng tốc truy vấn.

### 6.2. Index không thay thế các lựa chọn tham chiếu

| Mong muốn | Cơ chế dữ liệu | Index liên quan |
|---|---|---|
| Không có đơn trỏ tới khách hàng không tồn tại | `FOREIGN KEY` | Index khóa cha hỗ trợ đối chiếu; index bảng con tùy nhu cầu |
| Không xóa khách hàng khi còn đơn tham chiếu | FK với hành động xóa phù hợp | Index bảng con có thể tăng tốc tìm dòng tham chiếu |
| Khi xóa đơn thì xóa ghi chú của đơn | `ON DELETE CASCADE` | Index bảng con có thể tăng hiệu quả |
| Liệt kê đơn của một khách theo thời gian | Truy vấn có `WHERE`/`ORDER BY` | Index `(customer_id, placed_at)` có thể phù hợp |

Điểm chung: **quy tắc đúng/sai thuộc constraint; đường truy cập thuộc index**. Cả hai bổ trợ nhau nhưng không có quan hệ “một là bản sao của cái kia”.

## 7. `CHECK`, `NOT NULL` và chỉ mục lọc là ba việc khác nhau

Một quy tắc “sản phẩm đang bán phải có giá dương” có thể được viết:

```sql
CREATE TABLE catalog_items (
    item_id BIGINT PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    price NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_catalog_items_active_price
        CHECK (NOT is_active OR price > 0)
);
```

Ràng buộc `CHECK` yêu cầu: nếu `is_active = TRUE`, `price` phải lớn hơn 0; nếu sản phẩm ngưng bán, điều kiện không bắt buộc giá dương. Vì `is_active` và `price` đều `NOT NULL`, biểu thức không có trường hợp `UNKNOWN` do hai cột này.

Để tăng tốc truy vấn “xem mặt hàng đang bán theo giá”, có thể thêm partial index:

```sql
CREATE INDEX idx_catalog_items_active_price
    ON catalog_items (price)
    WHERE is_active = TRUE;
```

Index này chỉ chứa các dòng đang bán, giúp tối ưu một số truy vấn lọc đúng điều kiện:

```sql
SELECT item_id, price
FROM catalog_items
WHERE is_active = TRUE
  AND price BETWEEN 100000 AND 500000;
```

**Không được hiểu rằng partial index chỉ gồm các dòng `is_active = TRUE` thì tự động chặn giá 0 hoặc giá âm.** Nếu thiếu `CHECK`, mặt hàng đang bán có giá âm vẫn có thể được index bình thường. Ngược lại, có `CHECK` mà không có index vẫn bảo vệ dữ liệu, chỉ có thể kém tối ưu hơn ở những truy vấn lớn.

## 8. Thực hành trọn vẹn trên PostgreSQL

Ví dụ dùng **bảng tạm** để tránh thay đổi bảng nghiệp vụ có sẵn. Mở một phiên SQL thực hành mới, bảo đảm bạn có quyền tạo temporary table và kết nối PostgreSQL đang hoạt động. Cú pháp `CREATE TEMP TABLE` và danh mục hệ thống `pg_constraint`/`pg_indexes` trong phần này là của PostgreSQL.

### 8.1. Tạo bảng với các ràng buộc có tên

```sql
CREATE TEMP TABLE lab_customers (
    customer_id INTEGER,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    CONSTRAINT pk_lab_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_lab_customers_email UNIQUE (email)
);

CREATE TEMP TABLE lab_orders (
    order_id INTEGER,
    customer_id INTEGER NOT NULL,
    placed_at DATE NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    CONSTRAINT pk_lab_orders PRIMARY KEY (order_id),
    CONSTRAINT fk_lab_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers(customer_id),
    CONSTRAINT ck_lab_orders_amount CHECK (total_amount >= 0)
);
```

Trong kết quả tạo bảng thành công, người học đang có:

- `pk_lab_customers`, `pk_lab_orders`: bảo vệ khóa chính và được hỗ trợ bằng unique index.
- `uq_lab_customers_email`: bảo vệ tính duy nhất của email và được hỗ trợ bằng unique index.
- `fk_lab_orders_customer`: buộc mã khách hàng trong đơn tham chiếu tới bảng cha.
- `ck_lab_orders_amount`: không cho phép giá trị âm.
- Các khai báo `NOT NULL`: cấm giá trị rỗng ở các cột được chỉ định.

### 8.2. Nạp dữ liệu hợp lệ

```sql
INSERT INTO lab_customers (customer_id, email, full_name)
VALUES
    (1, 'an@example.test', 'An'),
    (2, 'binh@example.test', 'Bình'),
    (3, 'chi@example.test', 'Chi');

INSERT INTO lab_orders (order_id, customer_id, placed_at, total_amount)
VALUES
    (101, 1, DATE '2026-11-01', 150000),
    (102, 1, DATE '2026-11-04', 250000),
    (103, 2, DATE '2026-11-03', 100000);

SELECT o.order_id, c.full_name, o.total_amount
FROM lab_orders AS o
JOIN lab_customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Kết quả có ba đơn hợp lệ: đơn 101 và 102 của An; đơn 103 của Bình. Chi chưa có đơn. Bảng con đã tham chiếu thành công các khóa tồn tại ở bảng cha.

### 8.3. Quan sát các index tự tạo bởi ràng buộc

PostgreSQL cung cấp view `pg_indexes`. Vì bảng thực hành là bảng tạm, lấy tên schema tạm hiện tại bằng `pg_my_temp_schema()`:

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = (
    SELECT nspname
    FROM pg_namespace
    WHERE oid = pg_my_temp_schema()
)
AND tablename IN ('lab_customers', 'lab_orders')
ORDER BY tablename, indexname;
```

Ở thời điểm này, các index điển hình tương ứng với `pk_lab_customers`, `uq_lab_customers_email` và `pk_lab_orders`. **Không có một index riêng được tạo tự động trên `lab_orders(customer_id)` chỉ vì foreign key**. Tên index hiển thị có thể gắn theo tên constraint trong lược đồ.

Để quan sát **constraint dưới dạng metadata**:

```sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid IN (
    'lab_customers'::regclass,
    'lab_orders'::regclass
)
ORDER BY conrelid::regclass::text, conname;
```

`contype` trong PostgreSQL biểu thị các nhóm như `p` (primary key), `u` (unique), `f` (foreign key), `c` (check). `NOT NULL` trong các phiên bản PostgreSQL thông dụng có thể được biểu diễn bằng metadata cột thay vì một dòng `pg_constraint` theo cách như `CHECK`. Vì thế, **đừng suy ra không có NOT NULL chỉ vì không tìm thấy dòng `contype` tương ứng**. Để xem thông tin cột, dùng `information_schema.columns` hoặc meta-command `\d` của `psql`.

### 8.4. Thêm index hỗ trợ truy vấn theo khách hàng

```sql
CREATE INDEX idx_lab_orders_customer_date
    ON lab_orders (customer_id, placed_at);

SELECT order_id, customer_id, placed_at
FROM lab_orders
WHERE customer_id = 1
ORDER BY placed_at DESC;
```

Truy vấn của khách hàng 1 trả về đơn 102 (04/11) rồi đơn 101 (01/11). Index mới có thể hỗ trợ mẫu truy vấn này; nó không thêm bất kỳ giới hạn mới nào về giá trị `customer_id`.

Muốn quan sát kế hoạch do bộ tối ưu lựa chọn:

```sql
EXPLAIN
SELECT order_id, customer_id, placed_at
FROM lab_orders
WHERE customer_id = 1
ORDER BY placed_at DESC;
```

Vì bảng chỉ có ba dòng, PostgreSQL **có thể chọn quét toàn bảng**. Đây không phải bằng chứng rằng index sai hoặc không hoạt động; chỉ là bộ tối ưu đánh giá chi phí toàn bảng thấp hơn cho dữ liệu rất nhỏ. Không nên ép kế hoạch truy vấn chỉ để minh họa một index “phải được dùng”.

### 8.5. Các thao tác sẽ bị ràng buộc từ chối

Thử **từng lệnh riêng** trên phiên thực hành để quan sát thông báo lỗi. Các lệnh được chú thích bên dưới nhằm tránh làm dừng toàn bộ script:

```sql
-- Trùng primary key:
-- INSERT INTO lab_customers (customer_id, email, full_name)
-- VALUES (1, 'another@example.test', 'Người khác');

-- Trùng UNIQUE(email):
-- INSERT INTO lab_customers (customer_id, email, full_name)
-- VALUES (4, 'an@example.test', 'An thứ hai');

-- Vi phạm NOT NULL:
-- INSERT INTO lab_customers (customer_id, email, full_name)
-- VALUES (4, NULL, 'Khách không email');

-- Vi phạm FOREIGN KEY: khách 999 không tồn tại:
-- INSERT INTO lab_orders (order_id, customer_id, placed_at, total_amount)
-- VALUES (104, 999, DATE '2026-11-05', 50000);

-- Vi phạm CHECK: số tiền âm:
-- INSERT INTO lab_orders (order_id, customer_id, placed_at, total_amount)
-- VALUES (105, 1, DATE '2026-11-05', -10000);
```

Các thao tác trên bị từ chối vì **constraint**, không phải vì query planner không tìm thấy index. Một câu `INSERT` bị lỗi trong PostgreSQL có thể khiến giao dịch tường minh hiện tại ở trạng thái lỗi cho tới khi `ROLLBACK` hoặc quay về `SAVEPOINT`; trong môi trường thử có autocommit bật, chạy từng câu riêng thường dễ quan sát hơn.

### 8.6. Chứng minh index thông thường không kiểm soát tính duy nhất

Tạo một bảng tạm không có `UNIQUE` trên cột `label`, sau đó thêm **index thường**:

```sql
CREATE TEMP TABLE lab_tags (
    tag_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE INDEX idx_lab_tags_label
    ON lab_tags (label);

INSERT INTO lab_tags (tag_id, label)
VALUES (1, 'SQL'), (2, 'SQL');

SELECT tag_id, label
FROM lab_tags
ORDER BY tag_id;
```

Hai dòng đều có `label = 'SQL'` và đều hợp lệ. Index hỗ trợ tìm kiếm theo `label` nhưng không cấm trùng. Muốn cấm hai nhãn giống nhau, cần quy tắc duy nhất:

```sql
-- Lệnh sau sẽ lỗi vì bảng đã có hai giá trị 'SQL' trùng.
-- ALTER TABLE lab_tags
-- ADD CONSTRAINT uq_lab_tags_label UNIQUE (label);
```

Muốn áp ràng buộc, trước hết phải **xử lý dữ liệu trùng theo nghiệp vụ**; một `UNIQUE` constraint không “tự sửa” những dòng trùng có sẵn. Đây là khác biệt quan trọng khi bổ sung ràng buộc cho bảng đã chứa dữ liệu.

### 8.7. Kết thúc bài thực hành

Các bảng `TEMP` của PostgreSQL thuộc phiên hiện tại và được xóa khi phiên kết thúc. Nếu muốn xóa ngay trong phiên:

```sql
DROP TABLE IF EXISTS lab_tags;
DROP TABLE IF EXISTS lab_orders;
DROP TABLE IF EXISTS lab_customers;
```

Thứ tự xóa bảng con trước bảng cha nhằm tránh vướng quan hệ tham chiếu. Thực hành trong database riêng cũng giúp phân biệt những thao tác trên bảng tạm với thay đổi schema được ứng dụng sử dụng lâu dài.

## 9. Thời điểm kiểm tra constraint và giao dịch

Ràng buộc là một phần quy tắc dữ liệu, nhưng **khi nào** hệ quản trị kiểm tra có thể ảnh hưởng cách thực hiện giao dịch.

Thông thường, các constraint được kiểm tra tại thời điểm thực thi câu lệnh. PostgreSQL cho phép **một số** `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY` và `EXCLUDE` constraint được khai báo `DEFERRABLE` để có thể trì hoãn kiểm tra đến cuối giao dịch; `NOT NULL` và `CHECK` không thể được trì hoãn theo cùng cơ chế này.

Ví dụ cấu trúc:

```sql
CREATE TEMP TABLE lab_departments (
    department_id INTEGER PRIMARY KEY
);

CREATE TEMP TABLE lab_employees (
    employee_id INTEGER PRIMARY KEY,
    department_id INTEGER,
    CONSTRAINT fk_lab_employees_department
        FOREIGN KEY (department_id)
        REFERENCES lab_departments(department_id)
        DEFERRABLE INITIALLY DEFERRED
);

BEGIN;

INSERT INTO lab_employees (employee_id, department_id)
VALUES (1, 20);

INSERT INTO lab_departments (department_id)
VALUES (20);

COMMIT;
```

Đến lúc `COMMIT`, giá trị `department_id = 20` đã tồn tại ở bảng cha, nên giao dịch có thể xác nhận. Nếu không bổ sung dòng cha, việc kiểm tra khóa ngoại tại thời điểm xác nhận sẽ thất bại. Việc khai báo `DEFERRABLE` là **một lựa chọn về thời điểm kiểm tra constraint**, không phải tối ưu chỉ mục; index phù hợp vẫn là vấn đề độc lập.

Không nên mặc định một `UNIQUE INDEX` đứng riêng có đầy đủ hành vi trì hoãn giống `UNIQUE` constraint được khai báo `DEFERRABLE` trong PostgreSQL.

## 10. Khi nào cần thêm index cho những cột đã có constraint?

Một số quyết định thực tế:

| Cột hoặc quan hệ | Đã có gì từ constraint? | Có nên thêm index? |
|---|---|---|
| `customers.customer_id PRIMARY KEY` | Unique B-tree index trên khóa chính | **Thường không** cần thêm index y hệt |
| `customers.email UNIQUE` | Unique B-tree index trên email | **Thường không** cần thêm index y hệt |
| `orders.order_id PRIMARY KEY` | Unique B-tree index trên mã đơn | **Thường không** cần thêm index y hệt |
| `orders.customer_id FOREIGN KEY` | Quy tắc tham chiếu, **không có index tự tạo phía con trong PostgreSQL** | **Cân nhắc** nếu thường join, lọc theo khách hoặc xóa/cập nhật cha |
| `orders.total_amount CHECK >= 0` | Điều kiện dữ liệu hợp lệ, không có index | Thêm nếu truy vấn lọc/sắp xếp theo tiền cần, không phải để thực thi `CHECK` |
| `orders(placed_at)` | Không nhất thiết có constraint | Thêm nếu thường truy vấn theo khoảng thời gian và đủ lợi ích |
| `order_items(order_id, line_no) PRIMARY KEY` | Index khóa ghép theo thứ tự này | Có thể đủ cho tìm theo `order_id`; đánh giá nhu cầu lọc riêng theo `line_no` |

Một số quy tắc thiết kế:

1. **Khai báo constraint dựa trên nghiệp vụ**, dù bảng nhỏ hay chưa cần tối ưu. Nếu điều kiện luôn phải đúng, nên được bảo vệ tại nơi lưu trữ dữ liệu.
2. **Đọc danh sách index hiện có** trước khi thêm index. Primary/unique constraint đã tạo cấu trúc hỗ trợ nên tránh tạo bản sao cùng khóa.
3. **Thiết kế index theo mẫu truy vấn thực tế**: điều kiện `WHERE`, `JOIN`, `ORDER BY`, tính chọn lọc và thứ tự cột.
4. **Đánh giá chi phí ghi dữ liệu**: mỗi index mới làm tăng công duy trì khi bảng thay đổi.
5. **Dùng `EXPLAIN` và dữ liệu đại diện** khi tối ưu, không dựa hoàn toàn vào tên index hoặc một phép thử trên bảng chỉ vài dòng.
6. **Phân biệt giới hạn vật lý với quy tắc logic**: index có thể bị tạo lại, đổi tên, bảo trì hoặc thay chiến lược; nghiệp vụ phải được biểu diễn rõ bằng constraint hoặc cơ chế thực thi tính toàn vẹn phù hợp.

## 11. Những lỗi thiết kế thường gặp

### Lỗi 1: “Đã có index nên dữ liệu không trùng”

```sql
CREATE INDEX idx_accounts_username ON accounts(username);
```

Lệnh này **không** ngăn trùng username. Cần `UNIQUE(username)` hoặc unique index phù hợp khi muốn bảo đảm tính duy nhất.

### Lỗi 2: “Đã tạo foreign key nên truy vấn tìm theo mã cha sẽ nhanh”

```sql
FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
```

Trong PostgreSQL, lệnh này không tự tạo index trên `orders.customer_id`. Truy vấn theo cột đó có thể cần thêm index tùy khối lượng dữ liệu và tần suất truy vấn.

### Lỗi 3: “`CHECK(price >= 0)` cấm được `NULL`”

`CHECK` trả `UNKNOWN` với `NULL` và PostgreSQL cho phép giá trị đó. Nếu không chấp nhận tiền chưa biết, cần `NOT NULL` **và** `CHECK(price >= 0)`.

### Lỗi 4: “Thêm index cho mọi cột là luôn tốt”

Index có thể giúp đọc nhanh hơn nhưng làm tăng dung lượng và chi phí ghi; hiệu quả phụ thuộc truy vấn. Chọn index theo công việc thực tế thay vì quy tắc “mỗi cột một index”.

### Lỗi 5: “Một unique index partial có thể thay khóa chính”

```sql
CREATE UNIQUE INDEX ux_active_users_email
    ON app_users(lower(email))
    WHERE deleted_at IS NULL;
```

Chỉ những dòng hoạt động được kiểm tra trùng theo biểu thức; đây không phải định danh duy nhất cho **mọi dòng** của bảng. Nếu cần khóa chính hoặc khóa được bảng khác tham chiếu, hãy khai báo thiết kế định danh riêng.

### Lỗi 6: “Hai bảng có cùng kiểu mã nên quan hệ đã được đảm bảo”

Việc `orders.customer_id` và `customers.customer_id` đều là `BIGINT` không ngăn chèn mã không tồn tại. **Kiểu tương thích** không thay cho `FOREIGN KEY`.

### Lỗi 7: “Unique constraint luôn cấm hai `NULL`”

Trong PostgreSQL mặc định, nhiều `NULL` có thể xuất hiện ở cột `UNIQUE`; cần `NOT NULL` nếu cột bắt buộc có giá trị, hoặc lựa chọn `NULLS NOT DISTINCT` khi muốn tính duy nhất coi `NULL` như bằng nhau (PostgreSQL 15+).

### Lỗi 8: “Tạo `UNIQUE` trên bảng đang có dữ liệu trùng sẽ tự hợp nhất các dòng”

Hệ quản trị từ chối thêm ràng buộc nếu dữ liệu hiện có vi phạm; trước đó phải quyết định loại bỏ, hợp nhất hoặc sửa các dòng trùng theo quy tắc nghiệp vụ.

## 12. Khác biệt cần lưu ý giữa PostgreSQL, MySQL và SQLite

Ngôn ngữ SQL có nhiều nguyên tắc chung, nhưng việc tự tạo index, xử lý `NULL` và thực thi khóa ngoại không giống nhau hoàn toàn:

| Chủ đề | PostgreSQL | MySQL (InnoDB) | SQLite |
|---|---|---|---|
| `PRIMARY KEY` / `UNIQUE` | Tạo unique index hỗ trợ | Dùng index để thực thi tính duy nhất; chi tiết phụ thuộc storage engine | Có cơ chế index nội bộ hỗ trợ uniqueness; `INTEGER PRIMARY KEY` có cơ chế rowid đặc biệt ở bảng rowid thông thường |
| Index trên cột FK **phía con** | **Không tự tạo** khi khai báo FK | InnoDB yêu cầu index phù hợp; có thể tự tạo nếu thiếu | **Không tự tạo**, thường nên cân nhắc |
| Foreign key enforcement | Được thực thi theo constraint | InnoDB thực thi FK theo điều kiện hỗ trợ | Cần bảo đảm `PRAGMA foreign_keys = ON` trên từng kết nối nếu môi trường chưa bật |
| `CHECK` | Có thực thi; `UNKNOWN`/`NULL` không vi phạm CHECK | Phiên bản MySQL hiện đại có thực thi CHECK; phiên bản cũ có khác biệt | Có thực thi, tùy phiên bản và cấu hình |
| Unique với `NULL` | Mặc định nhiều `NULL`; PostgreSQL 15+ hỗ trợ `NULLS NOT DISTINCT` | Nhiều giá trị `NULL` thường được phép trong unique index | Thường cho phép nhiều `NULL` |
| Partial/expression unique index | Hỗ trợ cả partial và expression index | Khả năng và cú pháp phụ thuộc phiên bản; không tương đương hoàn toàn PostgreSQL | Hỗ trợ partial/expression index trong các phiên bản tương ứng |

### 12.1. MySQL InnoDB: đừng máy móc kết luận FK không có index

Trong InnoDB, foreign key cần index tương ứng ở phía bảng con; nếu chưa có index thích hợp, InnoDB có thể tạo index tự động. Điều này **khác PostgreSQL**. Khi chuyển kiến thức từ hệ này sang hệ khác, cần kiểm tra index hiện tại thay vì dựa vào quy tắc thuộc một hệ.

Một số DDL MySQL có hành vi implicit commit; khi thực hành thêm/xóa constraint hoặc index trên dữ liệu thật, không nên mặc định `ROLLBACK` hoàn tác mọi lệnh thay đổi schema.

### 12.2. SQLite: khai báo FK chưa đủ nếu chế độ kiểm tra tắt

SQLite có cấu hình `PRAGMA foreign_keys` theo **kết nối**. Khi dùng SQLite trong ứng dụng hoặc môi trường học tập, nên kiểm tra:

```sql
PRAGMA foreign_keys;
PRAGMA foreign_keys = ON;
PRAGMA foreign_keys;
```

Việc đổi thiết lập này cần được thực hiện ngoài một giao dịch đang mở để có hiệu lực theo cách dự định. Index trên khóa tham chiếu phía bảng con vẫn là quyết định quan trọng về hiệu năng.

### 12.3. Không áp đặt một quy tắc `UNIQUE NULL` cho mọi hệ

Giữa các hệ quản trị, cách xử lý một hoặc nhiều `NULL` trong unique constraint có thể khác nhau. Trên PostgreSQL, `UNIQUE` mặc định cho phép nhiều `NULL`; nếu cột phải có giá trị, dùng `NOT NULL` để diễn đạt trực tiếp. Trước khi chuyển schema giữa database, cần kiểm tra hành vi của hệ đích với dữ liệu có `NULL`, khóa ghép và unique index có điều kiện.

## 13. Bài tập tự luyện

Để mỗi lời giải rõ ràng, hãy xác định riêng **quy tắc dữ liệu phải giữ** và **truy vấn cần chạy nhanh**.

### Bài 1 — Phân loại trách nhiệm

Xác định nên khai báo **constraint**, **index** hay **cả hai**:

1. Mỗi sản phẩm phải có `sku` duy nhất.
2. Danh sách đơn cần lọc nhanh theo `customer_id` và sắp xếp theo `placed_at`.
3. Mỗi dòng đơn có `quantity > 0`.
4. Mọi `order_items.order_id` phải tham chiếu một đơn tồn tại.
5. Danh sách sản phẩm có giá trong khoảng 100.000–500.000 cần phản hồi nhanh khi bảng rất lớn.

### Bài 2 — Dự đoán index được tạo

Trong PostgreSQL, tạo bảng:

```sql
CREATE TABLE departments (
    department_id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE
);

CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    department_id INTEGER NOT NULL
        REFERENCES departments(department_id)
);
```

Những index nào thường đã có? Có index nào trên `employees.department_id` được tạo **chỉ vì** foreign key không?

### Bài 3 — Điều kiện có `NULL`

Với cột `score INTEGER CHECK (score >= 0)`, giá trị `NULL` có bị từ chối trong PostgreSQL không? Viết khai báo cột nếu muốn chỉ nhận số nguyên không âm và **bắt buộc có giá trị**.

### Bài 4 — Khóa ghép và truy vấn

Bảng `order_items` có `PRIMARY KEY(order_id, line_no)`. Viết truy vấn lấy toàn bộ dòng hàng của một đơn theo `line_no`. Index hỗ trợ khóa chính có thể hữu ích ra sao? Nếu cần tìm tất cả dòng có `line_no = 1` trên **mọi đơn**, có nhất thiết index ghép trên đủ tốt không?

### Bài 5 — Index không đồng nghĩa `UNIQUE`

Xét:

```sql
CREATE TABLE labels (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);
CREATE INDEX idx_labels_label ON labels(label);
```

Hai dòng khác `id` nhưng cùng `label` có được chèn không? Cần thay đổi schema thế nào để ngăn trùng?

### Bài 6 — Khách hàng và đơn hàng

Bảng `orders` có `FOREIGN KEY(customer_id) REFERENCES customers(customer_id)`, thường được truy vấn theo khách hàng và ngày đặt. Hãy nêu một index phù hợp, giải thích index đó có thay FK được không và tại sao việc thêm index có thể làm `INSERT`/`UPDATE` tốn công hơn.

<details>
<summary>Gợi ý lời giải</summary>

**Bài 1:** (1) `UNIQUE` và `NOT NULL` nếu SKU bắt buộc; PostgreSQL tự có unique index hỗ trợ. (2) Index `(customer_id, placed_at)` theo mẫu truy vấn. (3) `CHECK (quantity > 0)` kết hợp `NOT NULL` nếu bắt buộc có số lượng. (4) `FOREIGN KEY`; index bảng con là quyết định tối ưu riêng. (5) Cân nhắc index trên `price` dựa trên truy vấn và phân bố dữ liệu; constraint chỉ cần nếu có quy tắc giá hợp lệ như `CHECK(price >= 0)`.

**Bài 2:** Thường có unique index hỗ trợ `departments.department_id`, `departments.code` và `employees.employee_id`. PostgreSQL không tự thêm index trên `employees.department_id` chỉ vì `REFERENCES`.

**Bài 3:** `NULL` không vi phạm `CHECK` trong PostgreSQL vì biểu thức là `UNKNOWN`. Đúng yêu cầu:

```sql
score INTEGER NOT NULL CHECK (score >= 0)
```

**Bài 4:**

```sql
SELECT order_id, line_no, quantity
FROM order_items
WHERE order_id = 123
ORDER BY line_no;
```

Index khóa chính `(order_id, line_no)` có thể hỗ trợ vì điều kiện tìm theo cột đầu. Nếu chỉ tìm `line_no = 1` toàn bảng, hiệu quả phụ thuộc cấu trúc và dữ liệu; có thể cần index riêng theo `line_no`.

**Bài 5:** Hai dòng cùng `label` vẫn được chèn vì index thường không cấm trùng. Thêm `UNIQUE(label)` hoặc unique index phù hợp, sau khi xử lý dữ liệu trùng nếu có.

**Bài 6:**

```sql
CREATE INDEX idx_orders_customer_placed
ON orders(customer_id, placed_at);
```

Index hỗ trợ truy cập theo khách và thời gian nhưng không kiểm tra dòng cha có tồn tại. `FOREIGN KEY` vẫn cần để đảm bảo tính toàn vẹn; mỗi thay đổi bảng phải duy trì thêm index nên có chi phí ghi.

</details>

## 14. Nguyên tắc kết luận cho thiết kế schema

Khi định nghĩa một bảng, hãy làm hai lượt tư duy độc lập:

1. **Lượt toàn vẹn dữ liệu:** xác định khóa chính, khóa nghiệp vụ duy nhất, cột bắt buộc, quan hệ tham chiếu và điều kiện hợp lệ. Dùng `PRIMARY KEY`, `UNIQUE`, `NOT NULL`, `FOREIGN KEY`, `CHECK` đúng với quy tắc dữ liệu; không lấy index thường làm bằng chứng rằng dữ liệu hợp lệ.
2. **Lượt đường truy cập:** xem những truy vấn cần hỗ trợ, index nào đã có từ khóa chính/duy nhất, khóa ngoại phía con có cần index riêng không, và thứ tự cột nào phù hợp. Chỉ thêm index khi lợi ích đọc có cơ sở so với chi phí ghi và lưu trữ.

**Constraint bảo vệ tính đúng đắn; index hỗ trợ cách truy cập.** Một số index, đặc biệt unique index, còn thực thi quy tắc không trùng lặp và có thể làm cấu trúc hỗ trợ constraint. Hiểu rõ sự giao nhau này giúp thiết kế SQL vừa giữ được dữ liệu hợp lệ, vừa tránh tạo index thừa và xác định đúng nơi cần tối ưu.
