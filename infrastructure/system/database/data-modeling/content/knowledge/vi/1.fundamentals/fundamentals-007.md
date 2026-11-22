# Ví dụ xuyên suốt: khách hàng, danh mục, đơn hàng, thanh toán và tồn kho

Một hệ thống bán hàng trực tuyến thường bắt đầu bằng những câu hỏi rất đời thường: ai đang mua hàng, sản phẩm thuộc danh mục nào, đơn hàng gồm những gì, khách đã thanh toán chưa và kho còn đủ hàng để giao không? Khi chuyển những câu hỏi đó thành dữ liệu, ta phải xác định thực thể, quan hệ, quy tắc nghiệp vụ, cách lưu lịch sử và cách bảo đảm nhiều thao tác đồng thời không làm sai số liệu.

Bài này dùng một cửa hàng trực tuyến làm ví dụ xuyên suốt để thực hành chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu. Ta sẽ đi từ mô hình khái niệm đến lược đồ quan hệ, sau đó đối chiếu với document, graph và mô hình phân tích. Mục tiêu là chọn cấu trúc phù hợp với cách hệ thống vận hành, có thể kiểm chứng bằng ràng buộc và có thể tiến hóa khi nghiệp vụ thay đổi.

## 1. Bắt đầu từ yêu cầu nghiệp vụ

Giả sử cửa hàng có khách hàng, sản phẩm, danh mục, đơn hàng, thanh toán và nhiều kho. Trước khi tạo bảng, hãy viết các quy tắc bằng ngôn ngữ nghiệp vụ. Một mô hình tốt phải trả lời được những quy tắc này mà không dựa vào cách diễn giải tùy tiện của từng lập trình viên.

| Đối tượng | Quy tắc cần lưu |
|---|---|
| Khách hàng | Một khách hàng có hồ sơ, thông tin liên hệ và có thể lưu nhiều địa chỉ nhận hàng. |
| Danh mục | Danh mục có thể có danh mục cha và danh mục con. |
| Sản phẩm | Mỗi sản phẩm có SKU duy nhất; sản phẩm có thể xuất hiện trong nhiều danh mục. |
| Đơn hàng | Một đơn hàng thuộc về một khách hàng và có ít nhất một dòng hàng khi được xác nhận. |
| Dòng hàng | Mỗi dòng ghi sản phẩm, số lượng và giá tại thời điểm đặt hàng. |
| Thanh toán | Một đơn hàng có thể có nhiều lần thử thanh toán, nhiều giao dịch thu tiền hoặc hoàn tiền. |
| Kho | Một sản phẩm có thể tồn tại ở nhiều kho; mỗi kho có số lượng thực tế và số lượng đã giữ chỗ. |
| Biến động kho | Mỗi lần nhập, xuất, giữ chỗ, nhả giữ chỗ hoặc điều chỉnh phải có dấu vết. |

Những quy tắc trên chứa một số quyết định mô hình hóa cần nói rõ:

- Sản phẩm được gán nhiều danh mục. Vì vậy, quan hệ sản phẩm–danh mục là nhiều-nhiều. Nếu nghiệp vụ chỉ cho phép một danh mục chính, có thể thay bảng liên kết bằng khóa ngoại trên sản phẩm.
- Giá sản phẩm hiện tại có thể thay đổi. Đơn hàng phải giữ giá và tên sản phẩm tại thời điểm mua để hóa đơn cũ không đổi theo catalog mới.
- Một đơn hàng có thể có nhiều bản ghi thanh toán. Một lần thanh toán thất bại không được ghi đè lần thành công sau đó.
- Tồn kho được quản lý theo từng kho. Số lượng có thể bán được bằng số lượng thực tế trừ số lượng đang giữ chỗ.
- Địa chỉ giao hàng của đơn hàng là ảnh chụp tại thời điểm đặt hàng. Nếu khách cập nhật địa chỉ trong hồ sơ, địa chỉ của đơn cũ vẫn phải giữ nguyên.

Đây là giả định của ví dụ. Khi làm dự án thật, hãy xác nhận các điểm này với người phụ trách nghiệp vụ trước khi chốt lược đồ.

## 2. Xác định thực thể, thuộc tính và quan hệ

Từ yêu cầu, ta nhận ra các thực thể chính:

- **Customer:** người mua.
- **CustomerAddress:** địa chỉ khách hàng có thể chọn khi đặt hàng.
- **Category:** cây danh mục.
- **Product:** sản phẩm trong catalog.
- **ProductCategory:** bảng liên kết sản phẩm và danh mục.
- **SalesOrder:** phần đầu đơn hàng, chứa khách hàng, trạng thái, thời điểm và tổng tiền.
- **OrderItem:** từng sản phẩm trong đơn hàng.
- **Payment:** một giao dịch hoặc lần thử thanh toán.
- **Warehouse:** địa điểm lưu hàng.
- **Inventory:** số lượng hiện tại theo sản phẩm và kho.
- **InventoryMovement:** sổ ghi nhận các biến động kho.

Sơ đồ khái niệm:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ CUSTOMER_ADDRESS : owns
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : appears_in
    PRODUCT ||--o{ PRODUCT_CATEGORY : classified_by
    CATEGORY ||--o{ PRODUCT_CATEGORY : includes
    CATEGORY o|--o{ CATEGORY : parent_of
    SALES_ORDER ||--o{ PAYMENT : has
    PRODUCT ||--o{ INVENTORY : stocked_as
    WAREHOUSE ||--o{ INVENTORY : stores
    PRODUCT ||--o{ INVENTORY_MOVEMENT : changes
    WAREHOUSE ||--o{ INVENTORY_MOVEMENT : records
    SALES_ORDER o|--o{ INVENTORY_MOVEMENT : causes
~~~

Đọc sơ đồ theo chiều nghiệp vụ:

- Một khách hàng có thể có nhiều địa chỉ và nhiều đơn hàng; mỗi đơn hàng chỉ thuộc một khách hàng.
- Một đơn hàng có một hoặc nhiều dòng hàng; mỗi dòng hàng tham chiếu một sản phẩm.
- Sản phẩm và danh mục có quan hệ nhiều-nhiều, được triển khai qua **ProductCategory**.
- Một danh mục có thể có một danh mục cha; một danh mục cha có thể có nhiều danh mục con.
- Một đơn hàng có thể có nhiều bản ghi thanh toán.
- Một sản phẩm có số lượng riêng tại từng kho. Cặp sản phẩm–kho xác định một bản ghi tồn kho.
- Biến động kho chỉ ra sản phẩm, kho và nguyên nhân. Một biến động có thể liên quan đến đơn hàng, nhưng điều chỉnh kiểm kê không nhất thiết có đơn hàng.

Sơ đồ khái niệm chưa quyết định kiểu dữ liệu, chỉ mục hay cách phân vùng. Những quyết định đó thuộc giai đoạn thiết kế logic và vật lý.

## 3. Thiết kế lược đồ quan hệ

### 3.1. Khóa và định danh

Mỗi bảng cần một cách xác định duy nhất một dòng:

- Dùng khóa chính thay thế như **customer_id**, **product_id** hoặc **order_id** để định danh ổn định.
- Dùng khóa nghiệp vụ có ràng buộc duy nhất cho giá trị mà người dùng hoặc hệ thống bên ngoài cần nhận biết, chẳng hạn **sku**, **order_number** và mã tham chiếu từ cổng thanh toán.
- Dùng khóa chính ghép cho bảng liên kết như **(product_id, category_id)** và bảng tồn kho **(product_id, warehouse_id)**.
- Dùng **line_no** kết hợp **order_id** để định danh một dòng trong đơn hàng.

Khóa thay thế không loại bỏ nhu cầu kiểm tra khóa nghiệp vụ. Nếu không đặt **UNIQUE** cho SKU, hai sản phẩm có thể vô tình dùng cùng mã dù khóa chính của chúng khác nhau.

### 3.2. Ví dụ DDL

Ví dụ sau dùng PostgreSQL. Đây là lược đồ minh họa cho các quy tắc đã nêu; kiểu dữ liệu, độ dài và trạng thái cần được điều chỉnh theo hợp đồng nghiệp vụ thực tế.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(320),
    full_name VARCHAR(200) NOT NULL,
    phone VARCHAR(30),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Email không phân biệt chữ hoa/chữ thường.
CREATE UNIQUE INDEX uq_customer_email_ci
    ON customer (lower(email))
    WHERE email IS NOT NULL;

CREATE TABLE customer_address (
    address_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer(customer_id)
        ON DELETE RESTRICT,
    recipient_name VARCHAR(200) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    address_line1 VARCHAR(250) NOT NULL,
    address_line2 VARCHAR(250),
    ward VARCHAR(120),
    city VARCHAR(120) NOT NULL,
    country_code CHAR(2) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_customer_address_customer
    ON customer_address(customer_id);

CREATE TABLE category (
    category_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_category_id BIGINT REFERENCES category(category_id)
        ON DELETE RESTRICT,
    slug VARCHAR(160) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX ix_category_parent
    ON category(parent_category_id);

CREATE TABLE product (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(250) NOT NULL,
    description TEXT,
    current_price NUMERIC(18, 2) NOT NULL CHECK (current_price >= 0),
    currency CHAR(3) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE product_category (
    product_id BIGINT NOT NULL REFERENCES product(product_id)
        ON DELETE RESTRICT,
    category_id BIGINT NOT NULL REFERENCES category(category_id)
        ON DELETE RESTRICT,
    PRIMARY KEY (product_id, category_id)
);

CREATE INDEX ix_product_category_category
    ON product_category(category_id, product_id);

CREATE TABLE sales_order (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL REFERENCES customer(customer_id)
        ON DELETE RESTRICT,
    status VARCHAR(24) NOT NULL
        CHECK (status IN (
            'DRAFT', 'PENDING_PAYMENT', 'PAID',
            'PROCESSING', 'SHIPPED', 'COMPLETED',
            'CANCELLED', 'REFUNDED'
        )),
    placed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    currency CHAR(3) NOT NULL,
    subtotal NUMERIC(18, 2) NOT NULL CHECK (subtotal >= 0),
    discount_total NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (discount_total >= 0),
    shipping_fee NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (shipping_fee >= 0),
    tax_total NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (tax_total >= 0),
    grand_total NUMERIC(18, 2) NOT NULL CHECK (grand_total >= 0),
    delivery_recipient VARCHAR(200) NOT NULL,
    delivery_phone VARCHAR(30) NOT NULL,
    delivery_address TEXT NOT NULL,
    CONSTRAINT ck_order_total
        CHECK (grand_total = subtotal - discount_total
                           + shipping_fee + tax_total)
);

CREATE INDEX ix_order_customer_placed
    ON sales_order(customer_id, placed_at DESC, order_id DESC);

CREATE TABLE order_item (
    order_id BIGINT NOT NULL REFERENCES sales_order(order_id)
        ON DELETE RESTRICT,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL REFERENCES product(product_id)
        ON DELETE RESTRICT,
    sku_snapshot VARCHAR(80) NOT NULL,
    product_name_snapshot VARCHAR(250) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    discount_amount NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (discount_amount >= 0),
    line_total NUMERIC(18, 2)
        GENERATED ALWAYS AS (quantity * unit_price - discount_amount)
        STORED,
    PRIMARY KEY (order_id, line_no),
    CONSTRAINT ck_order_item_discount
        CHECK (discount_amount <= quantity * unit_price)
);

CREATE INDEX ix_order_item_product
    ON order_item(product_id, order_id);

CREATE TABLE payment (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES sales_order(order_id)
        ON DELETE RESTRICT,
    payment_type VARCHAR(12) NOT NULL
        CHECK (payment_type IN ('CHARGE', 'REFUND')),
    provider VARCHAR(60) NOT NULL,
    provider_reference VARCHAR(160),
    idempotency_key VARCHAR(160) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_reference),
    UNIQUE (provider, idempotency_key)
);

CREATE INDEX ix_payment_order_status
    ON payment(order_id, status);

CREATE TABLE warehouse (
    warehouse_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE inventory (
    product_id BIGINT NOT NULL REFERENCES product(product_id)
        ON DELETE RESTRICT,
    warehouse_id BIGINT NOT NULL REFERENCES warehouse(warehouse_id)
        ON DELETE RESTRICT,
    on_hand_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (on_hand_quantity >= 0),
    reserved_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (reserved_quantity >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, warehouse_id),
    CONSTRAINT ck_inventory_reserved
        CHECK (reserved_quantity <= on_hand_quantity)
);

CREATE INDEX ix_inventory_warehouse
    ON inventory(warehouse_id, product_id);

CREATE TABLE inventory_movement (
    movement_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES product(product_id)
        ON DELETE RESTRICT,
    warehouse_id BIGINT NOT NULL REFERENCES warehouse(warehouse_id)
        ON DELETE RESTRICT,
    order_id BIGINT REFERENCES sales_order(order_id)
        ON DELETE RESTRICT,
    movement_type VARCHAR(24) NOT NULL
        CHECK (movement_type IN (
            'RECEIPT', 'RESERVE', 'RELEASE',
            'SHIP', 'RETURN', 'ADJUSTMENT'
        )),
    on_hand_delta INTEGER NOT NULL DEFAULT 0,
    reserved_delta INTEGER NOT NULL DEFAULT 0,
    reason VARCHAR(250),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (on_hand_delta <> 0 OR reserved_delta <> 0)
);

CREATE INDEX ix_movement_stock_time
    ON inventory_movement(product_id, warehouse_id, created_at DESC);
CREATE INDEX ix_movement_order
    ON inventory_movement(order_id)
    WHERE order_id IS NOT NULL;
~~~

Một số điểm cần chú ý trong DDL:

1. **PRIMARY KEY**, **UNIQUE**, **NOT NULL** và **CHECK** biến quy tắc thành điều kiện mà cơ sở dữ liệu có thể từ chối khi dữ liệu sai.
2. **FOREIGN KEY** bảo đảm dòng hàng tham chiếu sản phẩm có thật, đơn hàng tham chiếu khách hàng có thật và tồn kho tham chiếu kho hợp lệ.
3. **ON DELETE RESTRICT** bảo vệ lịch sử giao dịch. Với khách hàng, sản phẩm hoặc kho đã phát sinh giao dịch, thường nên vô hiệu hóa hoặc ẩn thay vì xóa vật lý.
4. **order_item** lưu ảnh chụp SKU, tên và đơn giá. Những cột này có vẻ lặp lại thông tin sản phẩm, nhưng chúng mô tả sự kiện mua hàng trong quá khứ.
5. **sales_order** lưu tổng tiền tại thời điểm xác nhận. Ràng buộc **CHECK** kiểm tra phép cộng các thành phần trong cùng một dòng. Việc đối chiếu tổng đơn với tổng các dòng hàng cần được thực hiện trong cùng giao dịch bằng logic ứng dụng, trigger hoặc quy trình kiểm tra dữ liệu, vì **CHECK** thông thường không tổng hợp các dòng ở bảng khác.
   Trong ví dụ này, **subtotal** là tổng giá trị các dòng trước giảm giá; **discount_total** gồm giảm giá cấp dòng (tổng **order_item.discount_amount**) và giảm giá cấp đơn. **line_total** là giá trị một dòng sau giảm giá cấp dòng. Quy ước này làm cho công thức tổng đơn nhất quán; khi ghi đơn, ứng dụng vẫn phải đối soát các tổng này với các dòng chi tiết.
6. **inventory** là số dư hiện tại để đọc nhanh; **inventory_movement** ghi lịch sử thay đổi. Mọi thao tác cập nhật số dư cần ghi biến động tương ứng trong cùng một giao dịch.

### 3.3. Vì sao cần bảng liên kết và bảng chi tiết?

Không nên lưu danh sách danh mục trong một cột văn bản kiểu “dien-thoai,phu-kien” của sản phẩm. Cách đó làm truy vấn, kiểm tra khóa ngoại và đổi tên danh mục khó tin cậy. Bảng **product_category** cho phép mỗi liên kết được kiểm soát bằng hai khóa ngoại.

Tương tự, không nên lưu tất cả sản phẩm của đơn hàng trong một cột JSON nếu hệ thống cần lọc, tổng hợp, kiểm tra sản phẩm hoặc cập nhật tồn kho theo từng dòng thường xuyên. **order_item** giúp mỗi dòng hàng có định danh, ràng buộc số lượng và giá rõ ràng.

## 4. Chuẩn hóa và những bản sao có chủ đích

Chuẩn hóa giúp giảm bất thường khi thêm, sửa hoặc xóa dữ liệu.

### 4.1. Nhìn qua 1NF, 2NF và 3NF

- **Dạng chuẩn 1 (1NF):** mỗi ô chứa một giá trị theo miền dữ liệu đã định nghĩa; không nhét nhiều SKU hoặc nhiều danh mục vào một cột phân tách bằng dấu phẩy.
- **Dạng chuẩn 2 (2NF):** với khóa chính ghép, thuộc tính không khóa phải phụ thuộc vào toàn bộ khóa. Trong **product_category**, bảng chỉ có cặp khóa nên không có thuộc tính mô tả chỉ phụ thuộc một nửa khóa. Tên sản phẩm phải ở **product**, tên danh mục phải ở **category**.
- **Dạng chuẩn 3 (3NF):** thuộc tính không khóa không nên phụ thuộc bắc cầu vào khóa. Ví dụ, thông tin thành phố và quốc gia của địa chỉ nên thuộc bản ghi địa chỉ, không lặp lại thành các cột mô tả phụ thuộc vào một mã địa điểm ở mọi đơn hàng.

Chuẩn hóa không phải mục tiêu tự thân. Ta chọn mức chuẩn hóa đủ để giữ dữ liệu nhất quán, sau đó chỉ thêm dữ liệu dẫn xuất khi có lý do vận hành rõ ràng.

### 4.2. Ảnh chụp lịch sử không phải bản sao tùy tiện

Giả sử sản phẩm có tên “Tai nghe A” và giá 500.000 đồng lúc khách đặt hàng. Tuần sau, cửa hàng đổi tên sản phẩm và tăng giá lên 550.000 đồng. Nếu đơn hàng chỉ tham chiếu **product_id** rồi đọc tên và giá hiện tại từ **product**, hóa đơn cũ sẽ hiển thị sai lịch sử.

Vì vậy, **order_item** giữ **sku_snapshot**, **product_name_snapshot** và **unit_price**. Đây là dữ kiện của giao dịch tại thời điểm mua, không phải bản sao để thay thế catalog.

### 4.3. Số dư tồn kho và sổ biến động

Có hai cách tính tồn kho:

- Tính mỗi lần đọc bằng cách cộng tất cả biến động trong **inventory_movement**. Cách này có lịch sử đầy đủ nhưng có thể chậm khi bảng biến động lớn.
- Lưu số dư hiện tại trong **inventory** để đọc nhanh, đồng thời ghi sổ biến động trong **inventory_movement**.

Ví dụ dùng cách thứ hai. Hai nơi phải được cập nhật nguyên tử trong cùng một giao dịch. Có thể chạy tác vụ đối soát định kỳ để tính lại số dư từ sổ biến động và phát hiện sai lệch. Sổ biến động nên được xem là dữ liệu lịch sử; hạn chế sửa hoặc xóa các dòng đã ghi.

## 5. Giao dịch đặt hàng và giữ tồn kho an toàn

Mô hình dữ liệu phải chịu được nhiều khách đặt cùng một sản phẩm gần như đồng thời. Nếu hai yêu cầu cùng đọc thấy còn một sản phẩm rồi đều ghi nhận đơn hàng, cửa hàng có thể bán vượt tồn.

Một quy trình đặt hàng có thể thực hiện như sau:

1. Tạo đơn hàng và các dòng hàng với giá, tên, SKU được chụp tại thời điểm đặt.
2. Với từng sản phẩm và kho được chọn, tăng số lượng giữ chỗ có điều kiện.
3. Nếu bất kỳ dòng nào không đủ số lượng khả dụng, rollback toàn bộ giao dịch và báo hết hàng.
4. Nếu giữ chỗ thành công, ghi **inventory_movement** tương ứng và chuyển đơn sang **PENDING_PAYMENT**.
5. Commit giao dịch. Sau đó mới gọi cổng thanh toán hoặc phát sự kiện xử lý thanh toán.

Câu lệnh giữ chỗ cốt lõi:

~~~sql
UPDATE inventory
SET reserved_quantity = reserved_quantity + :requested_quantity,
    updated_at = now()
WHERE product_id = :product_id
  AND warehouse_id = :warehouse_id
  AND on_hand_quantity - reserved_quantity >= :requested_quantity
RETURNING product_id, warehouse_id, on_hand_quantity, reserved_quantity;
~~~

Nếu câu lệnh không trả về dòng nào, bản ghi tồn kho không tồn tại hoặc số lượng khả dụng không đủ. Ứng dụng phải coi đó là thất bại của bước giữ chỗ. Khi thành công, trong cùng transaction hãy thêm dòng **inventory_movement** có **movement_type = 'RESERVE'**, **on_hand_delta = 0** và **reserved_delta** bằng số lượng vừa giữ.

Khi giao hàng, số lượng thực tế và số lượng giữ chỗ cùng giảm:

- **on_hand_delta = -quantity**
- **reserved_delta = -quantity**
- **movement_type = 'SHIP'**

Khi hủy đơn trước khi giao, nhả giữ chỗ:

- **on_hand_delta = 0**
- **reserved_delta = -quantity**
- **movement_type = 'RELEASE'**

Với đơn có nhiều sản phẩm, nên xử lý các cặp **(product_id, warehouse_id)** theo cùng một thứ tự ở mọi luồng để giảm nguy cơ deadlock. Cần đặt thời hạn giữ chỗ và có tác vụ giải phóng những giữ chỗ hết hạn.

Không nên giữ transaction cơ sở dữ liệu mở trong lúc chờ phản hồi mạng từ cổng thanh toán. Tạo bản ghi thanh toán **PENDING**, commit, gọi nhà cung cấp bằng khóa idempotency, rồi cập nhật trạng thái theo phản hồi hoặc webhook. Ràng buộc duy nhất trên **(provider, idempotency_key)** và **(provider, provider_reference)** giúp tránh tạo giao dịch trùng khi hệ thống retry. Webhook cũng cần được xử lý lặp an toàn vì nhà cung cấp có thể gửi lại sự kiện.

## 6. Truy vấn để kiểm chứng mô hình

Một mô hình cần hỗ trợ được các câu hỏi thực tế.

### 6.1. Lịch sử mua hàng của khách

~~~sql
SELECT
    o.order_number,
    o.placed_at,
    o.status,
    oi.product_name_snapshot,
    oi.sku_snapshot,
    oi.quantity,
    oi.unit_price,
    oi.line_total
FROM sales_order AS o
JOIN order_item AS oi ON oi.order_id = o.order_id
WHERE o.customer_id = :customer_id
ORDER BY o.placed_at DESC, o.order_id DESC, oi.line_no;
~~~

Truy vấn đọc tên và giá từ ảnh chụp của dòng hàng, nên lịch sử vẫn đúng sau khi catalog thay đổi. Chỉ mục **(customer_id, placed_at DESC, order_id DESC)** hỗ trợ tìm đơn gần đây của một khách hàng.

### 6.2. Số lượng có thể bán của một sản phẩm tại từng kho

~~~sql
SELECT
    w.code,
    w.name,
    i.on_hand_quantity,
    i.reserved_quantity,
    i.on_hand_quantity - i.reserved_quantity AS available_quantity
FROM inventory AS i
JOIN warehouse AS w ON w.warehouse_id = i.warehouse_id
WHERE i.product_id = :product_id
ORDER BY w.code;
~~~

Số lượng khả dụng là giá trị dẫn xuất. Không cần lưu thêm một cột **available_quantity** có thể lệch với hai cột thành phần.

### 6.3. Tổng tiền đã thu thành công của đơn hàng

~~~sql
SELECT
    order_id,
    SUM(CASE
        WHEN payment_type = 'CHARGE' AND status = 'SUCCEEDED'
            THEN amount
        WHEN payment_type = 'REFUND' AND status = 'SUCCEEDED'
            THEN -amount
        ELSE 0
    END) AS net_paid
FROM payment
WHERE order_id = :order_id
GROUP BY order_id;
~~~

Đây là số tiền thu ròng từ các giao dịch thành công. Nó có thể khác **grand_total** nếu khách thanh toán thiếu, thanh toán nhiều lần hoặc đã được hoàn tiền. Trạng thái đơn hàng nên được cập nhật theo quy tắc nghiệp vụ rõ ràng dựa trên các giao dịch đã xác nhận.

## 7. Nếu chọn document database

Một document database như MongoDB phù hợp khi ứng dụng thường đọc hoặc ghi một aggregate cùng nhau, cấu trúc thuộc tính có thể thay đổi và dữ liệu lồng nhau có vòng đời gần giống nhau.

Đơn hàng là một ứng viên tốt để lưu thành một document vì phần đầu đơn, địa chỉ giao hàng và các dòng hàng thường được đọc cùng nhau:

~~~json
{
  "_id": "order-2026-000123",
  "customerId": "customer-42",
  "status": "PENDING_PAYMENT",
  "placedAt": "2026-11-21T12:30:00Z",
  "currency": "VND",
  "deliveryAddress": {
    "recipient": "Nguyen Van A",
    "phone": "0900000000",
    "line1": "12 Nguyen Trai",
    "city": "Ho Chi Minh City",
    "countryCode": "VN"
  },
  "items": [
    {
      "productId": "product-15",
      "skuSnapshot": "HEADPHONE-A",
      "nameSnapshot": "Tai nghe A",
      "quantity": 1,
      "unitPrice": 500000
    }
  ],
  "totals": {
    "subtotal": 500000,
    "discount": 0,
    "shipping": 20000,
    "tax": 0,
    "grandTotal": 520000
  }
}
~~~

Nhúng các dòng hàng và địa chỉ giao hàng giúp đọc một đơn hàng trong một lần truy vấn. Các dòng hàng cũng có thể giữ ảnh chụp lịch sử giống mô hình quan hệ.

Tuy nhiên, không nên nhúng toàn bộ catalog, lịch sử thanh toán và mọi bản ghi tồn kho vào document đơn hàng:

- Catalog được nhiều đơn hàng tham chiếu và có thể thay đổi độc lập.
- Thanh toán có thể phát sinh nhiều lần, có webhook và quy trình đối soát riêng.
- Tồn kho được nhiều đơn hàng cạnh tranh cập nhật. Một document tồn kho theo sản phẩm–kho thường dễ kiểm soát hơn một bản sao tồn kho nằm trong từng đơn.
- Document có danh sách con tăng không giới hạn có thể trở nên lớn, khó phân trang và khó cập nhật đồng thời.

Có thể dùng document cho đơn hàng, collection riêng cho sản phẩm, thanh toán và tồn kho. Dù chọn document, các quy tắc như SKU duy nhất, idempotency, không bán vượt tồn và bảo toàn lịch sử vẫn phải được thực thi bằng index, transaction, điều kiện cập nhật hoặc logic ứng dụng phù hợp.

## 8. Nếu chọn graph database

Graph database như Neo4j phù hợp khi câu hỏi quan trọng nhất là đường đi và mối liên hệ giữa nhiều thực thể.

Có thể biểu diễn dữ liệu bán hàng bằng node và relationship:

- Node: **Customer**, **Product**, **Category**, **Order**, **Warehouse**.
- Relationship: **PLACED**, **CONTAINS**, **BELONGS_TO**, **STOCKED_AT**, **BOUGHT_WITH**.
- Thuộc tính của relationship **CONTAINS** có thể gồm số lượng và giá tại thời điểm mua.

Ví dụ, để tìm các sản phẩm thường được mua cùng với một sản phẩm:

~~~cypher
MATCH (p:Product {sku: $sku})<-[:CONTAINS]-(o:Order)
      -[:CONTAINS]->(related:Product)
WHERE related <> p
RETURN related.sku, related.name, count(DISTINCT o) AS orderCount
ORDER BY orderCount DESC
LIMIT 10;
~~~

Graph giúp truy vấn các đường liên kết nhiều bước như khách hàng có cùng địa chỉ, sản phẩm cùng xuất hiện trong đơn, danh mục tổ tiên hoặc mạng lưới liên quan đến gian lận.

Nếu phần lớn thao tác là tạo đơn, ghi nhận thanh toán và cập nhật số lượng kho, cơ sở dữ liệu quan hệ thường dễ áp dụng khóa ngoại, transaction và ràng buộc số học hơn. Graph có thể bổ sung cho chức năng gợi ý, khám phá quan hệ hoặc phát hiện bất thường. Không cần chuyển toàn bộ hệ thống sang graph chỉ vì dữ liệu có quan hệ.

## 9. Nếu chọn mô hình phân tích

Cơ sở dữ liệu giao dịch tối ưu cho thao tác nghiệp vụ từng đơn hàng. Báo cáo như doanh thu theo tháng, doanh thu theo danh mục, tỷ lệ hoàn tiền hoặc tồn kho cuối ngày thường cần quét và tổng hợp nhiều dữ liệu lịch sử. Một mô hình phân tích dạng sao (star schema) có thể phục vụ các câu hỏi này hiệu quả hơn.

Ví dụ:

| Bảng phân tích | Hạt dữ liệu (grain) | Nội dung |
|---|---|---|
| **FactSales** | Một dòng hàng của đơn hàng | Số lượng, doanh thu trước và sau giảm giá, thuế |
| **FactPayment** | Một giao dịch thanh toán hoặc hoàn tiền | Số tiền, trạng thái, thời điểm, nhà cung cấp |
| **FactInventorySnapshot** | Một sản phẩm tại một kho tại một thời điểm chụp | Số lượng thực tế, giữ chỗ, khả dụng |
| **DimCustomer** | Một phiên bản hồ sơ khách hàng | Phân khúc, khu vực, thuộc tính phân tích |
| **DimProduct** | Một phiên bản sản phẩm | SKU, tên, thương hiệu, nhóm hàng |
| **DimCategory** | Một phiên bản danh mục | Cây phân cấp danh mục |
| **DimDate** | Một ngày | Ngày, tuần, tháng, quý, năm |
| **DimWarehouse** | Một kho | Mã kho, khu vực |

**FactSales** thường lưu khóa đến các dimension và các số đo có thể cộng. **DimProduct** hoặc **DimCustomer** có thể dùng Slowly Changing Dimension Type 2 để giữ lịch sử thay đổi thuộc tính: khi tên sản phẩm hoặc phân khúc khách hàng thay đổi, thêm phiên bản dimension mới với khoảng hiệu lực thay vì ghi đè lịch sử.

Cần xác định grain trước khi thiết kế fact. Nếu một dòng **FactSales** là một dòng hàng, không được trộn vào đó một số đo chỉ có ý nghĩa ở cấp đơn hàng rồi cộng tổng trên nhiều dòng, vì giá trị đơn hàng sẽ bị nhân lên. Thanh toán và ảnh chụp tồn kho có grain khác nên thường thuộc fact riêng.

Mô hình phân tích có thể được nạp theo lô hoặc luồng sự kiện từ hệ thống giao dịch. Không nên để truy vấn báo cáo nặng làm ảnh hưởng trực tiếp đến luồng đặt hàng và giữ tồn kho.

## 10. So sánh để chọn cấu trúc

| Tiêu chí | Quan hệ | Document | Graph | Phân tích |
|---|---|---|---|---|
| Trọng tâm | Bản ghi có cấu trúc, quan hệ và ràng buộc | Aggregate và dữ liệu lồng nhau | Đường đi và mạng quan hệ | Tổng hợp lịch sử và đo lường |
| Điểm mạnh | Khóa ngoại, transaction, join, tính nhất quán | Đọc aggregate thuận tiện, schema linh hoạt | Truy vấn nhiều bước quan hệ tự nhiên | Quét, tổng hợp và phân tích quy mô lớn |
| Phù hợp trong ví dụ | Đơn hàng, thanh toán, tồn kho | Document chi tiết đơn hàng | Gợi ý sản phẩm, quan hệ khách hàng | Doanh thu, hiệu quả danh mục, xu hướng tồn kho |
| Cần chú ý | Thiết kế join, chỉ mục, migration | Kích thước document, cập nhật đồng thời, dữ liệu trùng | Chi phí đồng bộ và truy vấn cập nhật số dư | Grain, độ trễ dữ liệu, lịch sử dimension |

Một hệ thống thực tế có thể kết hợp nhiều mô hình. Ví dụ, PostgreSQL làm nguồn dữ liệu giao dịch; một kho phân tích nhận sự kiện hoặc dữ liệu CDC; graph phục vụ gợi ý; document store phục vụ một phần nội dung có cấu trúc linh hoạt. Mỗi bản sao cần có nguồn sự thật, quy tắc đồng bộ và cách xử lý dữ liệu đến trễ.

## 11. Thiết kế chỉ mục theo truy vấn

Chỉ mục phải xuất phát từ truy vấn thực tế. Một số mẫu thường gặp:

- Khách hàng xem đơn gần đây: **(customer_id, placed_at DESC, order_id DESC)**.
- Tìm sản phẩm bằng SKU: **UNIQUE(sku)**.
- Tìm sản phẩm theo danh mục: **(category_id, product_id)** trên bảng liên kết.
- Liệt kê thanh toán theo đơn và trạng thái: **(order_id, status)**.
- Tra cứu biến động của một sản phẩm trong một kho: **(product_id, warehouse_id, created_at DESC)**.
- Tìm tồn kho của một kho: **(warehouse_id, product_id)**.

Không tạo chỉ mục cho mọi cột. Chỉ mục làm tăng dung lượng và khiến INSERT, UPDATE, DELETE tốn thêm công sức. Sau khi có dữ liệu đại diện, hãy kiểm tra kế hoạch thực thi bằng **EXPLAIN (ANALYZE, BUFFERS)** và đo độ trễ ở các truy vấn quan trọng.

Các cột khóa ngoại ở phía tham chiếu thường cần chỉ mục nếu được dùng để join, lọc hoặc xóa/cập nhật có kiểm tra tham chiếu. PostgreSQL không tự động tạo chỉ mục trên mọi cột khóa ngoại.

## 12. Làm cho mô hình có thể tiến hóa

Nghiệp vụ cửa hàng sẽ thay đổi. Một mô hình dễ tiến hóa cần có chiến lược cho các thay đổi phổ biến:

- **Thêm biến thể sản phẩm:** tách **Product** và **ProductVariant** nếu mỗi màu hoặc kích thước có SKU và tồn kho riêng.
- **Nhiều loại giá:** thêm bảng **PriceList** hoặc **ProductPrice** có thời gian hiệu lực thay vì ghi đè giá đang dùng.
- **Nhiều phương thức giao hàng:** tạo thực thể shipment hoặc delivery riêng nếu một đơn có thể chia thành nhiều kiện.
- **Hoàn hàng:** bổ sung **Return** và **ReturnItem**; ghi biến động kho **RETURN** khi hàng thực sự được nhập lại.
- **Đơn hàng nhiều tiền tệ:** giữ mã tiền tệ ở đơn hàng, dòng thanh toán và quy tắc tỷ giá; không cộng trực tiếp các số tiền khác tiền tệ.
- **Lịch sử trạng thái:** nếu cần kiểm toán, tạo bảng **OrderStatusHistory** với trạng thái cũ, mới, thời điểm và tác nhân thay đổi.
- **Nhiều kho hoặc chuyển kho:** ghi cặp biến động xuất và nhập trong cùng transaction hoặc quy trình có trạng thái, để không tạo hoặc mất hàng giữa chừng.

Khi triển khai migration trên hệ thống đang chạy, ưu tiên quy trình mở rộng rồi thu hẹp (expand–contract):

1. Thêm cột hoặc bảng mới ở trạng thái tương thích với phiên bản ứng dụng hiện tại.
2. Triển khai ứng dụng có thể đọc/ghi theo cấu trúc mới; nếu cần, ghi song song có kiểm soát.
3. Backfill dữ liệu cũ theo lô và kiểm tra số lượng, tổng tiền, khóa ngoại.
4. Chuyển truy vấn đọc sang cấu trúc mới sau khi đối soát.
5. Chỉ xóa cấu trúc cũ khi không còn phiên bản ứng dụng nào sử dụng.

Không đổi nghĩa một cột đang tồn tại mà không có migration dữ liệu và kế hoạch tương thích. Với trạng thái đơn hàng hoặc thanh toán, hãy xác định chuyển trạng thái hợp lệ; không để mỗi endpoint tự đặt chuỗi trạng thái tùy ý.

## 13. Kiểm chứng mô hình bằng câu hỏi và bất biến

Trước khi xem thiết kế là hoàn tất, hãy thử trả lời các câu hỏi sau bằng truy vấn hoặc kiểm tra dữ liệu:

- Một đơn hàng có thể tồn tại mà không có khách hàng hợp lệ không?
- Có thể có hai sản phẩm cùng SKU không?
- Có thể gán cùng một sản phẩm vào cùng một danh mục hai lần không?
- Một dòng hàng có thể có số lượng bằng 0 hoặc giá âm không?
- Tổng tiền đơn có khớp subtotal, giảm giá, phí giao hàng và thuế không?
- Hai yêu cầu đồng thời có thể giữ cùng một đơn vị hàng vượt quá số lượng khả dụng không?
- Một lần webhook gửi lặp có thể ghi nhận thanh toán hai lần không?
- Đổi tên sản phẩm có làm thay đổi hóa đơn cũ không?
- Có thể lần ngược số dư tồn kho về các biến động đã ghi không?
- Báo cáo doanh thu có nhân đôi số tiền cấp đơn hàng khi join với nhiều dòng hàng không?

Các bất biến quan trọng nên được bảo vệ ở lớp gần dữ liệu nhất có thể:

| Bất biến | Cách bảo vệ |
|---|---|
| SKU duy nhất | **UNIQUE** trên **product.sku** |
| Dòng hàng thuộc đơn và sản phẩm hợp lệ | **FOREIGN KEY** |
| Số lượng dòng hàng dương | **CHECK (quantity > 0)** |
| Giảm giá không vượt giá trị dòng | **CHECK** trên **order_item** |
| Giữ chỗ không vượt số lượng thực tế | **CHECK** trên **inventory** và cập nhật có điều kiện |
| Không xử lý trùng giao dịch thanh toán | Khóa idempotency và mã tham chiếu duy nhất |
| Tổng tiền các thành phần hợp lệ | **CHECK** trên đơn; đối soát tổng các dòng trong transaction |
| Có thể kiểm toán biến động kho | Ghi **inventory_movement** cùng transaction cập nhật số dư |

Kiểm tra định kỳ vẫn cần thiết cho những bất biến phụ thuộc nhiều bảng hoặc hệ thống bên ngoài. Ví dụ, có thể so sánh số dư **inventory** với tổng các **inventory_movement**, so sánh tổng dòng hàng với **sales_order.subtotal**, và đối chiếu thanh toán nội bộ với báo cáo từ nhà cung cấp.

## 14. Quy trình thực hành khi nhận một bài toán tương tự

Khi gặp một yêu cầu nghiệp vụ mới, hãy đi theo trình tự:

1. **Thu thập quy tắc:** viết rõ ai tạo dữ liệu, ai đọc dữ liệu, vòng đời của dữ liệu và điều kiện hợp lệ.
2. **Xác định thực thể:** tìm các danh từ có định danh và vòng đời riêng; tránh biến mọi nhóm thuộc tính thành một bảng.
3. **Xác định quan hệ và lực lượng:** một-một, một-nhiều hay nhiều-nhiều; quan hệ có bắt buộc hay tùy chọn không.
4. **Chọn khóa:** phân biệt khóa kỹ thuật với mã nghiệp vụ; xác định phạm vi duy nhất.
5. **Chuẩn hóa:** loại bỏ nhóm lặp và phụ thuộc sai; quyết định dữ liệu nào là ảnh chụp lịch sử có chủ đích.
6. **Đặt ràng buộc:** dùng kiểu dữ liệu, **NOT NULL**, **CHECK**, **UNIQUE** và **FOREIGN KEY** để thể hiện quy tắc.
7. **Mô phỏng giao dịch đồng thời:** kiểm tra các luồng dễ tranh chấp như giữ tồn kho, cấp mã và ghi nhận thanh toán.
8. **Thiết kế chỉ mục từ truy vấn:** chọn thứ tự cột theo bộ lọc, join và sắp xếp thực tế.
9. **So sánh mô hình lưu trữ:** dùng quan hệ, document, graph hoặc phân tích theo workload; có thể kết hợp khi có ranh giới đồng bộ rõ ràng.
10. **Lập kế hoạch tiến hóa:** migration, backfill, đối soát, tương thích phiên bản và khả năng rollback.

Một mô hình dữ liệu tốt giúp nhóm trả lời chính xác câu hỏi nghiệp vụ, ngăn dữ liệu sai ngay tại nơi lưu trữ và hỗ trợ thay đổi mà không phá vỡ lịch sử. Với ví dụ cửa hàng, mô hình quan hệ là nền tảng phù hợp cho giao dịch đơn hàng, thanh toán và tồn kho; document, graph và mô hình phân tích có thể bổ sung ở những phần mà cách truy cập dữ liệu của chúng phù hợp hơn.
