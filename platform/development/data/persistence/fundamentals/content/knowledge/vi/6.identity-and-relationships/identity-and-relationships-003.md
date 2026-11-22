# Khóa đơn, khóa ghép và phạm vi duy nhất

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **khóa chính (primary key)**, **khóa ứng viên (candidate key)**, **ràng buộc duy nhất (unique constraint)** và **khóa ngoại (foreign key)**.
2. Giải thích khi nào chọn **khóa đơn** và khi nào chọn **khóa ghép**, kể cả trường hợp định danh một bản ghi bằng nhiều thuộc tính nghiệp vụ.
3. Xác định rõ **phạm vi duy nhất** của dữ liệu: toàn bảng, theo tenant, theo thực thể cha, theo khoảng thời gian hoặc chỉ với bản ghi còn hiệu lực.
4. Thiết kế quan hệ trong ứng dụng Java đa tenant sao cho database có thể ngăn bản ghi con tham chiếu nhầm thực thể thuộc tenant khác.
5. Dự đoán tác động của thứ tự cột trong khóa ghép đến truy vấn, chỉ mục, kích thước khóa ngoại và tiến hóa schema.
6. Xử lý xung đột khóa một cách đúng đắn khi hai yêu cầu tạo dữ liệu diễn ra đồng thời, bao gồm cơ chế kiểm tra ở database và xử lý lỗi tại Java.

Bài thuộc chương **Định danh và quan hệ** của module **DATA_PERSISTENCE_FUNDAMENTALS**: học cách thiết kế lưu trữ dữ liệu bền vững cho Java, từ mô hình dữ liệu, lược đồ, truy vấn và chỉ mục đến giao dịch, cô lập, kiểm soát đồng thời, bảo mật và tiến hóa schema. Ví dụ sử dụng **PostgreSQL** để có SQL chạy được trên một hệ quản trị cụ thể; nguyên tắc mô hình hóa có thể áp dụng rộng rãi, nhưng cú pháp và khả năng thực thi ràng buộc thay đổi theo từng hệ.

## 1. Một bản ghi có thể có nhiều cách nhận diện

Ví dụ hệ thống bán hàng phục vụ nhiều cửa hàng (tenant):

| Thuộc tính | Giá trị minh họa | Quy tắc nghiệp vụ |
| --- | --- | --- |
| `id` | `92015` | Định danh nội bộ của một đơn, duy nhất trong bảng đơn hàng |
| `tenant_id` | `a081…` | Cửa hàng sở hữu đơn hàng |
| `order_number` | `SO-2026-0215` | Chỉ cần duy nhất **trong một cửa hàng** |
| `customer_id` | `c4de…` | Khách hàng liên quan đến đơn |
| `created_at` | `2026-11-21T09:20:00Z` | Thời điểm tạo, có thể trùng giữa các đơn |

Hai cửa hàng khác nhau đều có thể phát hành đơn hàng số `SO-2026-0215`. Điều này không trái quy tắc vì **phạm vi duy nhất** là cặp `(tenant_id, order_number)`. Trong khi đó, ứng dụng có thể dùng riêng `id` để tra cứu nội bộ.

Cần tách bốn khái niệm:

- **Khóa chính (PRIMARY KEY)**: một cột hoặc nhóm cột mà database dùng để định danh duy nhất từng hàng. Thành phần khóa chính phải khác `NULL`.
- **Khóa ứng viên**: một tập thuộc tính tối thiểu có thể định danh duy nhất một hàng theo quy tắc dữ liệu. Trong thiết kế quan hệ, có thể có nhiều khóa ứng viên; một khóa được chọn làm khóa chính.
- **Khóa duy nhất bổ sung (UNIQUE)**: bảo vệ quy tắc không trùng của một cột hoặc tổ hợp cột khác với khóa chính; cách xử lý `NULL` tùy hệ quản trị.
- **Khóa ngoại (FOREIGN KEY)**: ràng buộc một giá trị hoặc bộ giá trị của bảng con phải tương ứng với khóa được tham chiếu ở bảng cha, theo chính sách `NULL` và hành động cập nhật/xóa đã khai báo.

Một bảng chỉ có **một ràng buộc PRIMARY KEY**, nhưng có thể có nhiều ràng buộc `UNIQUE` và `FOREIGN KEY`. Khóa chính có thể gồm **nhiều cột**: tên gọi “primary key” không có nghĩa nó luôn là khóa đơn.

## 2. Khóa đơn: một cột làm định danh hàng

Khóa đơn (*single-column key*) chỉ dùng một thuộc tính để định danh hàng:

```sql
CREATE TABLE tenants (
    id   uuid PRIMARY KEY,
    name text NOT NULL
);
```

Từng tenant có một `id` duy nhất. Khóa đơn thường dễ truyền qua API, đặt trong đối tượng Java và tham chiếu từ bảng khác:

```sql
CREATE TABLE products (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    sku       text NOT NULL,
    name      text NOT NULL
);
```

`products.id` là khóa chính đơn, nhưng chỉ khóa này **chưa thể hiện** quy tắc “SKU không được trùng trong cùng tenant”. Nếu nghiệp vụ yêu cầu quy tắc đó, ta phải bổ sung:

```sql
ALTER TABLE products
ADD CONSTRAINT uq_products_tenant_sku UNIQUE (tenant_id, sku);
```

Vậy một bản ghi `products` vừa được nhận diện bằng `id`, vừa có cặp `(tenant_id, sku)` duy nhất. Hai cơ chế phục vụ hai nhu cầu khác nhau: ID nội bộ ổn định cho quan hệ và SKU theo phạm vi kinh doanh.

### Khi khóa đơn phù hợp

Khóa đơn là lựa chọn thường gặp khi:

- Đối tượng có danh tính độc lập với thuộc tính nghiệp vụ có thể đổi: tên, mã nhập hàng, địa chỉ email.
- Nhiều bảng khác cần tham chiếu đến nó, và muốn giữ khóa ngoại nhỏ, đơn giản.
- Hệ quản trị hoặc ORM làm việc thuận lợi với ID một cột.
- Có kế hoạch đổi cách đặt mã nghiệp vụ mà không muốn phải thay toàn bộ quan hệ.

Tuy nhiên, **khóa đơn không đồng nghĩa với khóa số tăng dần**. Một cột đơn có thể mang `bigint`, `uuid`, chuỗi mã hoặc kiểu khác. Việc so sánh cơ chế sinh giá trị (sequence, UUID, Snowflake) là một quyết định khác với câu hỏi **một hay nhiều cột tạo thành khóa**.

### Hạn chế

Nếu chọn một ID kỹ thuật rồi bỏ qua các quy tắc duy nhất khác, dữ liệu vẫn có thể sai nghiệp vụ: hai khách trong cùng tenant có cùng mã thành viên, hai dòng hóa đơn có cùng số thứ tự hoặc hai người dùng dùng cùng tên đăng nhập khi hệ thống yêu cầu duy nhất. Khóa chính **không tự bảo vệ** những quy tắc đó.

## 3. Khóa ghép: nhiều cột cùng xác định một hàng

Khóa ghép (*composite key*) sử dụng từ hai thuộc tính trở lên trong một ràng buộc khóa. Tình huống tự nhiên là mỗi dòng hàng thuộc một đơn và có số thứ tự chỉ duy nhất **bên trong đơn đó**.

```sql
CREATE TABLE order_lines (
    order_id   bigint NOT NULL,
    line_no    integer NOT NULL CHECK (line_no > 0),
    product_id bigint NOT NULL REFERENCES products(id),
    quantity   integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(18, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
```

Trong bảng trên, `line_no = 1` có thể xuất hiện trong rất nhiều đơn, nhưng **cặp** `(order_id, line_no)` không được lặp lại. Để ví dụ chạy như một schema hoàn chỉnh, phần sau sẽ tạo bảng `orders` và thêm khóa ngoại tương ứng.

Dữ liệu hợp lệ:

```text
order_id | line_no | product_id
---------+---------+-----------
92015    | 1       | 501
92015    | 2       | 502
92016    | 1       | 503
```

Dữ liệu không hợp lệ:

```text
order_id | line_no | product_id
---------+---------+-----------
92015    | 1       | 501
92015    | 1       | 504    <-- trùng khóa ghép (92015, 1)
```

Một khóa ghép khác có thể xuất hiện trong bảng đo cảm biến: `(device_id, measured_at, sequence_no)`, nếu hệ thống xác định một thiết bị có thể ghi nhiều số đo cùng thời điểm và `sequence_no` đảm bảo phân biệt trong đúng thời điểm đó. Nhưng nếu thiết bị có thể gửi lại bản ghi hoặc sửa timestamp, phải xác định rõ sự ổn định của khóa trước khi dùng nó làm định danh lâu dài.

### Khóa ghép tự nhiên và khóa ghép kỹ thuật

Khóa ghép có thể sử dụng dữ liệu nghiệp vụ, chẳng hạn `(country_code, tax_number)`, hoặc kết hợp khóa kỹ thuật với phạm vi, chẳng hạn `(tenant_id, customer_id)`. Khóa ghép không nhất thiết là “natural key”, và khóa đơn không nhất thiết là “surrogate key”.

- **Natural key** đến từ ý nghĩa nghiệp vụ, ví dụ mã hàng đã được bảo đảm duy nhất trong một danh mục.
- **Surrogate key** là định danh do hệ thống cấp để đại diện cho thực thể, ít phụ thuộc thay đổi nghiệp vụ.

Nếu một thành phần natural key dễ đổi hoặc dài, dùng nó làm phần PK kéo theo chi phí cập nhật khóa ngoại và các quan hệ. Có thể giữ một surrogate PK đơn và thêm `UNIQUE` trên khóa nghiệp vụ, thay vì bắt tất cả bảng con tham chiếu natural key.

## 4. Phạm vi duy nhất: hỏi “duy nhất ở đâu?” trước khi viết SQL

Một yêu cầu mơ hồ như “mã sản phẩm không được trùng” chưa đủ để thiết kế ràng buộc. Cần làm rõ mã có duy nhất **toàn nền tảng**, **trong tenant**, **trong danh mục**, hay **chỉ với bản ghi đang hoạt động**.

| Quy tắc | Ràng buộc điển hình | Ví dụ |
| --- | --- | --- |
| Một mã dùng một lần trong toàn bảng | `UNIQUE (external_id)` | Mã đối soát bên ngoài có namespace toàn cục |
| Một mã chỉ duy nhất trong một tenant | `UNIQUE (tenant_id, sku)` | Hai cửa hàng có thể cùng SKU |
| Một số thứ tự duy nhất dưới thực thể cha | `PRIMARY KEY (order_id, line_no)` | Mỗi đơn có dòng 1, dòng 2… |
| Một mã chỉ duy nhất với bản ghi còn hoạt động | Unique index có điều kiện | Cho phép tái sử dụng tên sau khi soft-delete |
| Duy nhất trong một kỳ | `UNIQUE (tenant_id, accounting_period, invoice_number)` | Số chứng từ theo kỳ, nếu quy tắc nghiệp vụ cho phép |

Với khóa ghép, **từng cột không cần duy nhất**, nhưng toàn bộ bộ giá trị phải duy nhất. Ví dụ:

```sql
UNIQUE (tenant_id, sku)
```

cho phép hai tenant cùng có SKU `ABC-01`, nhưng chặn hai dòng cùng `(tenant_id, sku)` trong một bảng.

Đừng mặc định rằng `UNIQUE (tenant_id, sku)` cũng có nghĩa `tenant_id` hay `sku` tự nó là duy nhất. Đây là hai ràng buộc khác nhau.

### Phân biệt “duy nhất toàn hệ thống” với “duy nhất trong database”

Nếu ứng dụng ghi vào **hai database độc lập**, mỗi database đều có `UNIQUE (external_id)` thì việc kiểm tra tại từng database **không bảo đảm** cả hai nơi không cấp cùng ID. Cần một không gian định danh chung, cơ chế phối hợp cấp ID, hoặc quy tắc định danh gồm cả vùng/nguồn.

Ở hệ thống partition hoặc shard, ràng buộc duy nhất có thể chỉ được thực thi trong một partition/shard hoặc phải chứa khóa phân vùng. Ví dụ, trên bảng phân vùng PostgreSQL, một `UNIQUE`/`PRIMARY KEY` của bảng cha phân vùng phải bao gồm mọi cột partition key theo các giới hạn của PostgreSQL. Không thể tự suy từ cú pháp `UNIQUE` rằng bất cứ thiết kế phân tán nào cũng cung cấp kiểm tra duy nhất toàn cụm.

## 5. Thiết kế PostgreSQL hoàn chỉnh cho hệ thống đa tenant

Giả sử ứng dụng quản lý đơn có ba nhu cầu:

1. Một khách hàng có ID nội bộ duy nhất; mã khách hàng chỉ duy nhất trong tenant.
2. Số đơn chỉ duy nhất trong tenant; khách được gắn vào đơn phải **thuộc chính tenant đó**.
3. Các dòng hàng có số thứ tự chỉ duy nhất trong một đơn.

Để ngăn việc gán sai tenant bằng ràng buộc database, ta sử dụng **khóa ngoại ghép**, ngay cả khi bảng khách có khóa chính đơn.

```sql
CREATE TABLE tenants (
    id   uuid PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE customers (
    id            uuid PRIMARY KEY,
    tenant_id     uuid NOT NULL REFERENCES tenants(id),
    customer_code text NOT NULL,
    full_name     text NOT NULL,

    CONSTRAINT uq_customers_tenant_code
        UNIQUE (tenant_id, customer_code),

    -- Cần cho khóa ngoại ghép từ orders.
    CONSTRAINT uq_customers_tenant_id
        UNIQUE (tenant_id, id)
);

CREATE TABLE orders (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    uuid NOT NULL REFERENCES tenants(id),
    customer_id  uuid NOT NULL,
    order_number text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_orders_tenant_number
        UNIQUE (tenant_id, order_number),

    CONSTRAINT fk_orders_customer_same_tenant
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers (tenant_id, id)
);

CREATE TABLE order_lines (
    order_id   bigint NOT NULL REFERENCES orders(id),
    line_no    integer NOT NULL CHECK (line_no > 0),
    product_id bigint NOT NULL,
    quantity   integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(18, 2) NOT NULL CHECK (unit_price >= 0),

    PRIMARY KEY (order_id, line_no)
);

CREATE INDEX idx_orders_tenant_created
    ON orders (tenant_id, created_at DESC, id DESC);
```

**Lưu ý:** đây là ví dụ độc lập về ràng buộc khóa. `order_lines.product_id` chưa khai báo foreign key vì ví dụ không tạo bảng `products`; hệ thống thực tế cần khai báo quan hệ này nếu dòng hàng bắt buộc tham chiếu danh mục sản phẩm.

### Vì sao khóa ngoại ghép quan trọng?

Nếu chỉ viết:

```sql
FOREIGN KEY (customer_id) REFERENCES customers(id)
```

database xác nhận `customer_id` tồn tại, nhưng chưa kiểm tra rằng `orders.tenant_id` khớp `customers.tenant_id`. Một lỗi Java có thể lưu đơn của tenant A trỏ đến khách thuộc tenant B. Với:

```sql
FOREIGN KEY (tenant_id, customer_id)
REFERENCES customers (tenant_id, id)
```

bộ `(tenant_id, customer_id)` phải tồn tại trong bảng `customers`; phép tham chiếu chéo tenant sẽ bị database từ chối.

Bảng `customers` có `PRIMARY KEY (id)`; tuy nhiên PostgreSQL cần một khóa unique hoặc primary key phù hợp với **các cột được khóa ngoại ghép tham chiếu**. Vì thế bảng đã khai báo `UNIQUE (tenant_id, id)`. Ràng buộc này có phần dư về mặt **duy nhất**, bởi `id` vốn đã duy nhất; mục đích của nó là hỗ trợ **ràng buộc quan hệ theo tenant**.

Đây là lựa chọn có chi phí: một unique index bổ sung, thêm dữ liệu trong FK ghép, và cập nhật schema phức tạp hơn. Lợi ích là lỗi quan hệ sai tenant được ngăn ở tầng persistence, kể cả khi dữ liệu được ghi từ ứng dụng khác hoặc job nhập liệu.

**Giới hạn an toàn:** ràng buộc FK chỉ bảo vệ tính toàn vẹn quan hệ; nó **không thay thế xác thực và phân quyền**. API vẫn phải kiểm tra người dùng có quyền truy cập tenant và tài nguyên trước khi đọc/ghi. Có thể dùng thêm Row-Level Security khi phù hợp kiến trúc và yêu cầu kiểm soát truy cập.

### Truy vấn theo yêu cầu sử dụng

```sql
-- Tra cứu một đơn bằng số đơn trong đúng tenant.
SELECT id, customer_id, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND order_number = :order_number;

-- Lấy 20 đơn mới nhất của một tenant, phân định hòa khi trùng timestamp.
SELECT id, order_number, created_at
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, id DESC
LIMIT 20;

-- Lấy các dòng của một đơn theo số thứ tự.
SELECT line_no, product_id, quantity, unit_price
FROM order_lines
WHERE order_id = :order_id
ORDER BY line_no;
```

`:tenant_id`, `:order_number` và `:order_id` là placeholder kiểu **named parameter** để dễ đọc; JDBC thuần sử dụng `?` thay thế, còn thư viện hỗ trợ named parameters có thể bind các tên này. Không nối trực tiếp tham số người dùng vào câu SQL.

Đường đọc đầu tiên tận dụng unique index `(tenant_id, order_number)`; đường đọc thứ hai có index riêng `(tenant_id, created_at DESC, id DESC)`. Chỉ mục unique của số đơn không tự tối ưu câu hỏi “20 đơn mới nhất”.

## 6. Thứ tự cột trong khóa ghép ảnh hưởng thế nào?

Trong các hệ dùng chỉ mục B-tree, thứ tự cột của khóa là một quyết định truy cập dữ liệu. Ví dụ:

```sql
CREATE INDEX idx_orders_customer_time
    ON orders (customer_id, created_at DESC);
```

Chỉ mục này thường hữu ích cho:

```sql
SELECT id
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 10;
```

Nhưng không thể mặc định nó tối ưu:

```sql
SELECT id
FROM orders
WHERE created_at >= :from_time
ORDER BY created_at;
```

vì không có điều kiện trên cột đứng đầu `customer_id`. PostgreSQL đôi khi có kế hoạch quét chỉ mục hoặc tối ưu khác trong tình huống đặc biệt, nhưng chi phí tùy dữ liệu và bộ lập kế hoạch; cần xem `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường thử nghiệm để biết kế hoạch thực tế.

Nhớ phân biệt:

- **`PRIMARY KEY (a, b)` và `PRIMARY KEY (b, a)`** cùng biểu diễn tính duy nhất của một cặp giá trị, nhưng tạo thứ tự khóa/index khác nhau và ảnh hưởng cách truy vấn dùng index.
- **`UNIQUE (tenant_id, sku)`** tạo một index phục vụ quy tắc duy nhất; không bảo đảm index đó cũng tối ưu mọi bộ lọc theo `sku`.
- Trong PostgreSQL, khai báo primary key thông thường tạo unique B-tree index, nhưng không có nghĩa dữ liệu trong bảng vật lý luôn được duy trì theo thứ tự khóa chính.
- Với hệ wide-column như Cassandra, partition key/clustering key quyết định cách định tuyến và sắp thứ tự dữ liệu theo mô hình khác. Không áp dụng máy móc quy tắc chỉ mục B-tree của PostgreSQL cho mọi hệ persistence.

Nếu khóa ghép có quá nhiều cột hoặc cột dài, các index và foreign key chứa chúng có thể chiếm nhiều dung lượng và làm tăng chi phí ghi. Điều này là lý do cân nhắc một ID nội bộ đơn, kèm unique constraint cho quy tắc nghiệp vụ, thay vì dùng mọi trường nghiệp vụ làm primary key.

## 7. Quy tắc duy nhất khi cột có NULL

`PRIMARY KEY` không chấp nhận `NULL` ở bất cứ thành phần nào. `UNIQUE` có hành vi khác: theo mặc định của PostgreSQL, hai hàng có `NULL` ở cột unique có thể cùng tồn tại vì các giá trị `NULL` được xem là không bằng nhau khi kiểm tra ràng buộc.

Ví dụ:

```sql
CREATE TABLE contacts (
    id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email   text UNIQUE
);

INSERT INTO contacts (email) VALUES (NULL);
INSERT INTO contacts (email) VALUES (NULL); -- PostgreSQL mặc định: hợp lệ
```

Nếu nghiệp vụ yêu cầu “chỉ một hàng được thiếu email”, phải khai báo quy tắc khác. PostgreSQL 15+ hỗ trợ cú pháp `UNIQUE NULLS NOT DISTINCT` cho trường hợp muốn coi `NULL` là bằng nhau khi kiểm tra duy nhất. Với những database khác, cú pháp và hành vi `NULL` có thể khác, vì vậy không nên mang nguyên ràng buộc sang hệ khác mà không kiểm tra.

Với khóa ghép `UNIQUE (tenant_id, external_code)`, nếu `external_code` cho phép `NULL`, các hàng cùng tenant với `NULL` ở cột đó vẫn có thể tồn tại nhiều lần theo mặc định của PostgreSQL. Khi mã là bắt buộc, cách đơn giản nhất là khai báo `external_code NOT NULL`.

## 8. Phạm vi duy nhất khi soft-delete và chuẩn hóa chuỗi

### Chỉ bản ghi đang hoạt động được giữ tên duy nhất

Giả sử một tenant có thể xóa mềm tài khoản rồi dùng lại tên hiển thị. Việc đặt:

```sql
UNIQUE (tenant_id, username)
```

cho **mọi** hàng sẽ giữ cả tên của bản ghi đã xóa, không đáp ứng yêu cầu tái sử dụng. PostgreSQL cho phép *partial unique index*:

```sql
CREATE TABLE member_accounts (
    id         uuid PRIMARY KEY,
    tenant_id  uuid NOT NULL REFERENCES tenants(id),
    username   text NOT NULL,
    deleted_at timestamptz
);

CREATE UNIQUE INDEX uq_member_active_username
    ON member_accounts (tenant_id, lower(username))
    WHERE deleted_at IS NULL;
```

Index này bảo đảm trong cùng tenant chỉ có một tài khoản **chưa xóa mềm** với cùng tên sau khi chuyển về chữ thường bằng `lower`. Những hàng có `deleted_at IS NOT NULL` không nằm trong index, nên có thể giữ cùng tên với nhau hoặc với một tài khoản đang hoạt động.

Có các đánh đổi cần dự tính:

- Khôi phục một tài khoản cũ có thể thất bại nếu tên đã được tài khoản mới dùng.
- Quy tắc `lower` không giải quyết mọi biến thể Unicode, khoảng trắng, tên tương đương về mặt nghiệp vụ. Phải quy định quy tắc chuẩn hóa và collation phù hợp.
- Partial unique index là tính năng cụ thể của PostgreSQL; ORM hoặc database khác có thể có cách khai báo khác.
- Việc xóa mềm không đồng nghĩa dữ liệu đã được xóa vật lý; kế hoạch lưu giữ và xóa dữ liệu phải theo yêu cầu thực tế.

### Tách hiển thị và so khớp

Tên người dùng mà người dùng nhìn thấy có thể giữ nguyên chữ hoa/chữ thường, trong khi một cột hoặc biểu thức chuẩn hóa được dùng để so khớp. Tuy nhiên, toàn bộ đường tạo và cập nhật phải dùng chung chính sách. Nếu Java chuẩn hóa một cách nhưng database so sánh cách khác, ràng buộc unique có thể không phản ánh đúng quy tắc sản phẩm.

## 9. Tránh lỗi cạnh tranh khi kiểm tra trùng

Một lỗi phổ biến là kiểm tra trước bằng Java:

```text
Request A: SELECT ... WHERE tenant_id = T AND order_number = N  -> không thấy
Request B: SELECT ... WHERE tenant_id = T AND order_number = N  -> không thấy
Request A: INSERT (T, N)
Request B: INSERT (T, N)
```

Hai request cùng thấy “chưa có” trước khi ghi. Nếu chỉ dựa vào kiểm tra ở ứng dụng, cả hai có thể chèn trùng. **Ràng buộc UNIQUE trong database** là cơ chế quyết định để chặn trường hợp này khi các thao tác ghi cùng đi qua một database có hiệu lực ràng buộc chung.

### Cách viết an toàn bằng PostgreSQL

Cơ sở dữ liệu đã có `uq_orders_tenant_number`. Có thể xử lý xung đột đúng trên khóa đó:

```sql
INSERT INTO orders (tenant_id, customer_id, order_number)
VALUES (:tenant_id, :customer_id, :order_number)
ON CONFLICT (tenant_id, order_number) DO NOTHING
RETURNING id;
```

Nếu chèn thành công, câu lệnh trả ID mới. Nếu số đơn đã tồn tại trong tenant đó, câu lệnh không trả hàng. **Không tự kết luận** đơn đã tồn tại có cùng mọi dữ liệu hoặc thuộc về cùng một yêu cầu tạo đơn; cần hợp đồng nghiệp vụ rõ ràng nếu muốn trả lại bản ghi cũ.

Java JDBC minh họa cách xử lý kết quả; transaction và quyền truy cập do tầng gọi quản lý:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public final class OrderWriter {
    public static final class DuplicateOrderNumberException
            extends RuntimeException {
        public DuplicateOrderNumberException() {
            super("Order number already exists in this tenant");
        }
    }

    public long insert(Connection connection, UUID tenantId,
                       UUID customerId, String orderNumber)
            throws SQLException {
        String sql = """
            INSERT INTO orders (tenant_id, customer_id, order_number)
            VALUES (?, ?, ?)
            ON CONFLICT (tenant_id, order_number) DO NOTHING
            RETURNING id
            """;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, tenantId);
            statement.setObject(2, customerId);
            statement.setString(3, orderNumber);

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    throw new DuplicateOrderNumberException();
                }
                return rows.getLong("id");
            }
        }
    }
}
```

Ví dụ sử dụng **Java 17+** và cú pháp PostgreSQL. Đây là phương án chặn **trùng số đơn**, không phải cơ chế idempotency hoàn chỉnh: nếu client gửi lại sau timeout, mã đơn có thể trùng nhưng dữ liệu của yêu cầu chưa chắc giống bản ghi đã tồn tại. Nếu yêu cầu nghiệp vụ cần đảm bảo “tạo đúng một lần”, hãy dùng `idempotency_key` ổn định với một unique constraint theo phạm vi phù hợp, lưu kết quả giao dịch và xử lý retry nhất quán.

Nếu một thao tác cập nhật nhiều bảng, việc đặt unique constraint không thay thế transaction cho các thay đổi liên quan. Trong Java, cần để tầng service/quản lý transaction xác định điểm commit, rollback và xử lý lỗi; việc nhận được ID từ câu lệnh chưa chứng minh transaction đã commit.

### Lỗi và mức cô lập

Khi ghi trực tiếp và trùng khóa, PostgreSQL thường báo SQLSTATE `23505` (*unique_violation*); khóa ngoại không hợp lệ thường là `23503` (*foreign_key_violation*). Có thể phân loại lỗi trong Java để trả phản hồi nghiệp vụ phù hợp, nhưng cần biết **ràng buộc nào** vi phạm: một SQLSTATE duy nhất không nói rõ lỗi là mã đơn, mã khách hay một unique index khác.

Đọc ở mức cô lập cao hơn có thể giúp giải quyết những quy tắc phức tạp, nhưng không nên thay thế ràng buộc khóa bằng cách “đọc rồi ghi” mà không phân tích race condition. Với quy tắc độc quyền đòi hỏi nhiều bản ghi, có thể cần transaction, khóa, exclusion constraint hoặc thuật toán điều phối phù hợp.

## 10. Khóa ghép và ranh giới persistence trong Java

Một khóa ghép thường xuất hiện ở tầng Java như một **value object**:

```java
import java.util.UUID;

public record CustomerWithinTenantId(UUID tenantId, UUID customerId) {
    public CustomerWithinTenantId {
        if (tenantId == null || customerId == null) {
            throw new IllegalArgumentException("Key parts must not be null");
        }
    }
}
```

Ứng dụng có thể truyền cả hai giá trị vào repository để lấy khách đúng tenant:

```sql
SELECT id, tenant_id, full_name
FROM customers
WHERE tenant_id = :tenant_id
  AND id = :customer_id;
```

Giữ cả `tenantId` trong hợp đồng repository giúp thể hiện rõ phạm vi truy vấn, giảm nguy cơ vô tình thực hiện truy vấn không lọc tenant. Tuy nhiên, **việc truyền tenant ID từ client không đủ làm phân quyền**: tenant ID phải được xác định hoặc kiểm tra dựa trên danh tính đã xác thực và chính sách truy cập.

Nếu sử dụng ORM như JPA/Hibernate, một khóa ghép có thể được biểu diễn bằng `@EmbeddedId` hoặc `@IdClass`, nhưng cần thiết kế cẩn thận ánh xạ `@ManyToOne`, `@JoinColumns`, tính bất biến, `equals/hashCode` và cách serialize ra API. Tránh chọn khóa ghép chỉ vì ngữ pháp ORM hỗ trợ; hãy chọn từ quy tắc dữ liệu và truy vấn thực tế.

## 11. Đánh đổi và quyết định thiết kế

| Phương án | Ưu điểm | Chi phí và rủi ro | Dùng khi |
| --- | --- | --- | --- |
| PK đơn bằng ID kỹ thuật | FK gọn, dễ thay thuộc tính nghiệp vụ | Cần bổ sung UNIQUE bảo vệ nghiệp vụ | Thực thể có danh tính ổn định, nhiều quan hệ |
| PK ghép từ thuộc tính nghiệp vụ | Thể hiện phạm vi nhận diện ngay trong khóa | FK rộng; thay một thành phần ảnh hưởng các bảng con | Giá trị thành phần ổn định, quy tắc nhận diện tự nhiên rõ ràng |
| PK đơn + UNIQUE ghép | Tách định danh kỹ thuật và tính duy nhất nghiệp vụ | Thêm index, thêm ràng buộc cần duy trì | Số đơn/SKU duy nhất theo tenant nhưng ID phải ổn định |
| PK đơn + UNIQUE ghép + FK ghép | Vừa FK tiện dụng, vừa chặn liên kết sai phạm vi | Thêm unique index để FK ghép tham chiếu; schema dài hơn | Dữ liệu đa tenant cần bảo đảm quan hệ cùng tenant ở database |

Một quyết định tốt phải đi theo **đường truy vấn và đường ghi**. Ví dụ chỉ chọn `PRIMARY KEY (tenant_id, id)` vì “đã có tenant” chưa chắc là tối ưu: nếu `id` vốn duy nhất toàn bảng, nhóm khóa ghép có thể tăng bề rộng FK và khiến một số truy vấn theo `id` cần thêm index hoặc đường truy cập khác. Ngược lại, khóa ghép theo tenant có thể rất hữu ích cho phân vùng, định tuyến và ràng buộc quan hệ nếu chúng là yêu cầu chính của hệ thống.

Từ góc nhìn vận hành, hãy kiểm tra kích thước index, độ trễ ghi khi bổ sung nhiều unique index, khả năng bảo trì khóa ngoại, tác động khi xóa/cập nhật cha và tính tương thích với chiến lược shard/replication. Ràng buộc mạnh trong một database không tự bảo đảm hành vi như vậy giữa nhiều kho dữ liệu độc lập.

## 12. Thay đổi khóa và phạm vi duy nhất sau khi đã có dữ liệu

Đổi từ `UNIQUE (email)` sang `UNIQUE (tenant_id, email)`, hoặc từ PK đơn sang PK ghép, là một thay đổi **ngữ nghĩa nghiệp vụ**, không chỉ là sửa một dòng DDL.

Quy trình triển khai nên xem xét:

1. **Chốt quy tắc mới**: định nghĩa rõ namespace, giá trị `NULL`, chữ hoa/thường, soft-delete và điều kiện hợp lệ.
2. **Rà soát dữ liệu cũ**: tìm các giá trị trùng theo quy tắc mới và các quan hệ sai tenant; thống nhất cách sửa dữ liệu.
3. **Lập kế hoạch phụ thuộc**: xác định FK, index, query, ORM mapping, API, cache, sự kiện và hệ thống bên ngoài đang dùng khóa cũ.
4. **Tạo ràng buộc và index có kiểm soát**: cân nhắc cách triển khai ít gián đoạn trên bảng lớn, thời điểm validation và chi phí khóa/ghi của DDL.
5. **Triển khai ứng dụng tương thích**: chuyển đường ghi/đọc theo từng giai đoạn; chỉ bỏ ràng buộc/khóa cũ sau khi tất cả consumer đã chuyển đổi.
6. **Kiểm tra và phục hồi**: chạy truy vấn đối soát, kiểm thử dữ liệu thực, theo dõi lỗi trùng/FK, chuẩn bị sao lưu và phương án quay lui.

Cần đặc biệt thận trọng khi **mở rộng phạm vi duy nhất**: ví dụ bỏ `UNIQUE (email)` để cho phép cùng email ở các tenant khác nhau. Đây là thay đổi hợp lệ nếu nghiệp vụ mong muốn, nhưng mọi API từng tra cứu bằng `email` một mình giờ phải bổ sung `tenant_id` hoặc chấp nhận trả nhiều kết quả.

Ngược lại, **thu hẹp phạm vi** (từ trùng được trên nhiều tenant thành duy nhất toàn cục) có thể bị chặn ngay bởi dữ liệu hiện có. Phải giải quyết trùng lặp trước khi áp ràng buộc mới.

## 13. Bài tập áp dụng

### Tình huống A — Nền tảng giáo dục nhiều cơ sở

Mỗi cơ sở có nhiều lớp học. Một học sinh có thể học nhiều lớp, nhưng không được ghi danh hai lần vào cùng lớp trong cùng học kỳ. Mã lớp `A1` có thể tồn tại ở hai cơ sở.

Hãy đề xuất ràng buộc cho:

1. Bảng `classes` có `id` riêng, `campus_id` và `class_code`.
2. Bảng `enrollments` gồm `student_id`, `class_id`, `semester_id`.
3. Nếu học sinh và lớp phải cùng cơ sở, cần thêm cột/ràng buộc gì để database ngăn ghi danh sai cơ sở?
4. Nếu cho phép ghi danh lại sau khi xóa mềm bản ghi cũ, làm sao thay đổi phạm vi unique cho bản ghi đang có hiệu lực?

**Gợi ý:** bảng `classes` có thể dùng PK `id` và `UNIQUE (campus_id, class_code)`. Nếu mỗi học sinh chỉ được ghi danh một lần trong một lớp/học kỳ, dùng `UNIQUE (student_id, class_id, semester_id)` hoặc PK ghép đó khi thành phần ổn định và đáp ứng các yêu cầu quan hệ. Quy tắc cùng cơ sở có thể dùng cặp `(campus_id, class_id)` và `(campus_id, student_id)` làm FK ghép đến các bảng cha có unique tương ứng. Soft-delete thường cần partial unique index với điều kiện `deleted_at IS NULL` trên hệ có hỗ trợ, và phải xét tác động khi khôi phục.

### Tình huống B — Đặt chỗ đồng thời

Hai request cùng đặt ghế số 12 cho chuyến xe số 51. Hệ thống hiện kiểm tra bằng `SELECT` rồi mới gọi `INSERT` và đôi khi tạo hai vé.

1. Quy tắc duy nhất tối thiểu nên là gì nếu mỗi ghế chỉ bán một lần cho một chuyến?
2. Nếu ghế có thể được “giữ tạm” rồi hết hạn, quy tắc khóa có cần thay đổi không?
3. Vì sao việc tăng độ khó đoán của ID vé không giải quyết tranh chấp ghế?

**Gợi ý:** với một bản ghi đại diện cho ghế đã được xác nhận trên chuyến, có thể dùng `UNIQUE (trip_id, seat_no)`. Nếu có nhiều trạng thái đặt chỗ (giữ tạm, hủy, hết hạn, bán) cần mô hình hóa đầy đủ vòng đời và các quy tắc “chỉ một vé còn hiệu lực” bằng transaction và ràng buộc phù hợp; không thể chỉ thêm điều kiện Java mà bảo đảm được khi có ghi đồng thời. ID của vé là định danh, không phải khóa nghiệp vụ ngăn hai người chiếm cùng ghế.

### Câu hỏi tự kiểm tra

- Vì sao `PRIMARY KEY (tenant_id, order_number)` cho phép hai tenant có cùng số đơn?
- Nếu `customers.id` đã là PK, vì sao đôi khi vẫn khai báo `UNIQUE (tenant_id, id)`?
- Vì sao `UNIQUE (email)` và `UNIQUE (tenant_id, email)` không thể dùng thay nhau?
- Cột `external_code` nullable có thể tạo ngoại lệ gì với ràng buộc unique mặc định?
- Vì sao `SELECT` kiểm tra trùng trước `INSERT` chưa đủ dưới tải đồng thời?
- Khi di chuyển dữ liệu từ nhiều database về một, ràng buộc unique cục bộ có đủ để chứng minh ID không trùng toàn cục không?

## 14. Checklist khi đưa thiết kế vào hệ thống

- Mỗi thực thể có một quy tắc định danh rõ: thành phần khóa không đổi tùy tiện và được bảo đảm ở tầng lưu trữ.
- Mỗi trường “không được trùng” đã được xác định **phạm vi** chính xác: toàn bảng, theo tenant, theo cha, theo kỳ hoặc chỉ bản ghi hiệu lực.
- Các quan hệ đa tenant được kiểm tra ở dịch vụ Java và, nếu cần bảo đảm bất kể nguồn ghi, được ràng buộc ở database bằng khóa ngoại phù hợp.
- Thứ tự cột trong khóa/index ghép đã được đối chiếu với các câu `WHERE`/`ORDER BY` thường xuyên; đã đo bằng dữ liệu thực tế.
- Các cột nullable, chuẩn hóa chuỗi và soft-delete có chính sách rõ ràng.
- Race condition khi tạo đồng thời được giải quyết bằng ràng buộc dữ liệu và giao dịch; API có cơ chế phản hồi xung đột và idempotency khi cần.
- Việc đổi khóa hoặc phạm vi duy nhất có kế hoạch migration, đối soát, backup/restore và tương thích với các API, consumer liên quan.

**Điểm cốt lõi:** khóa đơn hay khóa ghép chỉ là **hình dạng của định danh**. Quy tắc nghiệp vụ còn cần định nghĩa **duy nhất trong phạm vi nào**, và quan hệ phải bảo vệ **bản ghi nào được phép tham chiếu bản ghi nào**. Khi ba điều đó được thể hiện đúng trong lược đồ và đường ghi của Java, persistence mới có nền tảng để duy trì toàn vẹn dữ liệu qua lỗi ứng dụng, cập nhật đồng thời và thay đổi hệ thống.
