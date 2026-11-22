# Xây dựng lược đồ bán hàng với khóa và ràng buộc

Một hệ thống bán hàng cần lưu khách hàng, địa chỉ giao hàng, danh mục, sản phẩm, đơn hàng, dòng hàng và thanh toán. Những bảng này có quan hệ với nhau: một khách hàng có nhiều địa chỉ; một khách hàng tạo nhiều đơn; một đơn có nhiều dòng hàng; mỗi dòng tham chiếu một sản phẩm; một đơn có thể có nhiều lần thanh toán.

Nếu chỉ tạo các bảng với vài cột rồi bắt đầu INSERT, dữ liệu rất dễ rơi vào trạng thái không hợp lệ: đơn tham chiếu khách hàng không tồn tại, số lượng âm, SKU bị trùng, địa chỉ giao hàng thuộc khách khác, hoặc giá bán lịch sử thay đổi theo giá sản phẩm hiện tại. Một lược đồ tốt phải thể hiện được những quy tắc này ngay trong database bằng **khóa và ràng buộc**.

Bài **“Xây dựng lược đồ bán hàng với khóa và ràng buộc”** thuộc chương **Thực hành tổng hợp**, module **Database SQL**. Ta sẽ thiết kế một schema bán hàng thực tế vừa đủ, triển khai bằng PostgreSQL làm ví dụ chính, sau đó đối chiếu những khác biệt quan trọng của MySQL, SQL Server, Oracle và SQLite.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chuyển yêu cầu nghiệp vụ bán hàng thành các thực thể, quan hệ và bảng.
2. Chọn khóa chính tự nhiên, khóa thay thế và khóa ghép phù hợp.
3. Dùng PRIMARY KEY, FOREIGN KEY, UNIQUE, NOT NULL, CHECK và DEFAULT.
4. Chọn hành vi ON DELETE phù hợp với dữ liệu giao dịch.
5. Phân biệt dữ liệu danh mục hiện tại với snapshot cần giữ trong lịch sử đơn hàng.
6. Thiết kế khóa ghép để bảo đảm địa chỉ giao hàng thuộc đúng khách hàng.
7. Đặt kiểu dữ liệu cho số tiền, số lượng, trạng thái và thời gian.
8. Tạo index hỗ trợ khóa ngoại và các truy vấn bán hàng phổ biến.
9. Kiểm thử cả dữ liệu hợp lệ lẫn INSERT/UPDATE phải bị từ chối.
10. Hiểu giới hạn của CHECK khi biểu thức có NULL và khác biệt về UNIQUE/identity giữa các hệ.
11. Tính tổng đơn hàng và thanh toán mà không tạo lỗi nhân bản do JOIN.
12. Lập kế hoạch migration khi cần thay đổi khóa hoặc ràng buộc.

## 2. Từ nghiệp vụ đến mô hình dữ liệu

Một cửa hàng trực tuyến có các yêu cầu:

- Mỗi khách hàng có mã khách hàng duy nhất và thông tin liên hệ.
- Một khách hàng có thể lưu nhiều địa chỉ.
- Sản phẩm thuộc một danh mục; SKU của sản phẩm là duy nhất.
- Giá niêm yết hiện tại có thể thay đổi theo thời gian.
- Một đơn thuộc một khách hàng và có mã đơn duy nhất.
- Một đơn có thể chứa nhiều sản phẩm, mỗi dòng có số lượng, giá bán và chiết khấu tại thời điểm mua.
- Một đơn có thể được thanh toán bằng nhiều giao dịch, ví dụ thanh toán một phần hoặc thử thanh toán lại.
- Địa chỉ và giá trên đơn đã phát sinh phải phản ánh thời điểm đặt hàng, không tự đổi khi hồ sơ khách hàng hoặc giá sản phẩm được sửa.
- Không được xóa tùy tiện khách hàng, sản phẩm hoặc đơn đang được giao dịch khác tham chiếu.

Từ đó xác định các thực thể:

| Thực thể | Vai trò |
| --- | --- |
| customers | Hồ sơ khách hàng |
| customer_addresses | Các địa chỉ của một khách hàng |
| categories | Danh mục sản phẩm |
| products | Sản phẩm và giá hiện tại |
| orders | Phần đầu đơn hàng |
| order_items | Các dòng sản phẩm trong đơn |
| payments | Các lần thanh toán |

### 2.1. Sơ đồ quan hệ

~~~text
customers
   | 1
   +----------------------< customer_addresses
   |
   | 1
   +----------------------< orders
                                  | 1
                                  +------< order_items >------1 products
                                  |
                                  | 1
                                  +------< payments

categories
   | 1
   +----------------------< products
~~~

Ký hiệu 1:N có nghĩa một hàng ở phía 1 có thể liên kết nhiều hàng ở phía N. Ví dụ, một đơn có nhiều dòng order_items nhưng mỗi dòng chỉ thuộc một đơn.

### 2.2. Grain của từng bảng

Trước khi chọn khóa, hãy nói rõ một hàng đại diện cho điều gì:

- customers: một khách hàng.
- customer_addresses: một địa chỉ thuộc một khách hàng.
- products: một mã sản phẩm có giá niêm yết hiện tại.
- orders: một đơn hàng.
- order_items: một dòng trong một đơn.
- payments: một lần ghi nhận thanh toán hoặc một lần thử thanh toán.

Nếu không xác định grain, rất dễ tạo bảng trộn nhiều sự kiện hoặc tổng hợp sai sau này.

## 3. Khóa chính, khóa tự nhiên và khóa thay thế

**Khóa chính (PRIMARY KEY)** nhận diện duy nhất mỗi hàng. Một bảng chỉ có một định nghĩa primary key, nhưng khóa đó có thể gồm một hoặc nhiều cột.

### 3.1. Khóa tự nhiên

Khóa tự nhiên là một giá trị có ý nghĩa nghiệp vụ, ví dụ:

- SKU sản phẩm.
- Mã đơn hàng.
- Mã khách hàng do hệ thống quản lý.

Ưu điểm là người dùng và hệ thống ngoài có thể nhận diện bản ghi bằng mã có ý nghĩa. Nhược điểm là quy tắc nghiệp vụ có thể thay đổi, mã có thể được cấp lại hoặc có phạm vi duy nhất khác nhau.

### 3.2. Khóa thay thế

Khóa thay thế (surrogate key) là ID do hệ thống tạo, thường là số identity hoặc UUID:

~~~sql
customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
~~~

Ưu điểm:

- Ngắn gọn và ổn định khi tên, email hoặc mã nghiệp vụ đổi.
- Thuận tiện làm khóa ngoại.
- Không phụ thuộc vào cách người dùng nhập dữ liệu.

Nhược điểm:

- Không thay thế quy tắc duy nhất của mã nghiệp vụ.
- ID tự tăng không phải bí mật và không nên dùng làm cơ chế phân quyền.
- Có thể xuất hiện khoảng trống; không được giả định ID liên tục.

### 3.3. Dùng cả surrogate key và UNIQUE business key

Một thiết kế phổ biến:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_code VARCHAR(30) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL
);
~~~

customer_id là khóa chính kỹ thuật; customer_code là khóa thay thế/alternate key có ý nghĩa nghiệp vụ và được bảo vệ bằng UNIQUE.

**Không nên chọn email làm primary key** chỉ vì email đang duy nhất. Email có thể thay đổi, có thể chưa được cung cấp và quy tắc so sánh hoa/thường phụ thuộc hệ thống.

## 4. Khóa ghép và phạm vi duy nhất

Khóa ghép (composite key) gồm nhiều cột. Nó hữu ích khi định danh chỉ có ý nghĩa trong một phạm vi.

Ví dụ một khách có thể đánh số địa chỉ từ 1:

~~~sql
PRIMARY KEY (customer_id, address_id)
~~~

Địa chỉ số 1 của khách A và địa chỉ số 1 của khách B không trùng nhau vì khóa đầy đủ gồm cả customer_id.

Tương tự, dòng hàng trong đơn có thể được đánh số từ 1:

~~~sql
PRIMARY KEY (order_id, line_no)
~~~

Dòng số 1 của đơn SO-100 và dòng số 1 của đơn SO-101 là hai dòng khác nhau.

### 4.1. Khóa ghép bảo vệ quan hệ đúng chủ sở hữu

Nếu orders lưu customer_id và shipping_address_id, chỉ tạo hai foreign key riêng có thể chưa đủ để bảo đảm địa chỉ thuộc đúng khách hàng. Ta cần khóa ghép:

~~~sql
FOREIGN KEY (customer_id, shipping_address_id)
REFERENCES customer_addresses(customer_id, address_id)
~~~

Điều này kiểm tra **cặp giá trị**. Một đơn của khách A không thể tham chiếu địa chỉ số 2 của khách B chỉ vì địa chỉ số 2 tồn tại ở đâu đó.

## 5. Các ràng buộc quan trọng

| Ràng buộc | Chức năng | Ví dụ |
| --- | --- | --- |
| PRIMARY KEY | Định danh duy nhất, không NULL | customer_id |
| FOREIGN KEY | Bảo đảm hàng được tham chiếu tồn tại | orders.customer_id |
| UNIQUE | Cấm trùng giá trị/cặp giá trị | product.sku |
| NOT NULL | Bắt buộc phải có giá trị | order_no |
| CHECK | Bảo vệ điều kiện trên hàng | quantity > 0 |
| DEFAULT | Cung cấp giá trị khi INSERT bỏ cột | created_at |

Ràng buộc là một phần của hợp đồng dữ liệu. Kiểm tra ở ứng dụng giúp thông báo sớm và thân thiện, nhưng database constraint vẫn cần thiết vì dữ liệu có thể được ghi từ nhiều ứng dụng, job hoặc câu SQL khác nhau.

### 5.1. PRIMARY KEY

~~~sql
PRIMARY KEY (customer_id)
~~~

PRIMARY KEY tương đương một yêu cầu duy nhất và không NULL trên tập cột đó. Database tạo cơ chế index phù hợp để thực thi.

### 5.2. FOREIGN KEY

~~~sql
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id)
~~~

Giá trị customer_id trong bảng con phải tham chiếu một hàng hợp lệ ở bảng cha, trừ trường hợp cột FK được phép NULL theo quy tắc MATCH.

### 5.3. UNIQUE

~~~sql
CONSTRAINT uq_products_sku UNIQUE (sku)
~~~

UNIQUE thường cho phép NULL theo quy tắc riêng của engine. Nếu mã SKU bắt buộc phải có, cần kết hợp **NOT NULL**.

### 5.4. NOT NULL

~~~sql
sku VARCHAR(40) NOT NULL
~~~

NOT NULL ngăn bỏ trống theo nghĩa SQL NULL. Chuỗi rỗng hoặc chuỗi chỉ có khoảng trắng vẫn có thể được lưu ở nhiều hệ; nếu không chấp nhận, cần CHECK phù hợp và hiểu khác biệt Oracle về chuỗi rỗng.

### 5.5. CHECK

~~~sql
quantity INTEGER NOT NULL
    CHECK (quantity > 0)
~~~

CHECK kiểm tra biểu thức cho từng hàng. Một điểm quan trọng: trong nhiều hệ, CHECK chỉ từ chối khi điều kiện là FALSE; nếu biểu thức cho UNKNOWN vì NULL, hàng có thể vẫn được chấp nhận. Vì vậy, nếu quantity bắt buộc, phải có cả NOT NULL.

### 5.6. DEFAULT

~~~sql
created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
~~~

DEFAULT chỉ được dùng khi INSERT không cung cấp cột hoặc yêu cầu DEFAULT. Nó không tự ghi đè một giá trị NULL được truyền rõ ràng nếu cột cho phép NULL.

## 6. Chọn kiểu dữ liệu cho hệ bán hàng

| Thuộc tính | Kiểu gợi ý trong PostgreSQL | Lý do |
| --- | --- | --- |
| ID | BIGINT identity | Dải số lớn, khóa kỹ thuật |
| Mã SKU | VARCHAR(40) | Có độ dài giới hạn, cần UNIQUE |
| Tên sản phẩm | VARCHAR(200) | Chuỗi Unicode |
| Giá | NUMERIC(12,2) | Tiền cần decimal chính xác |
| Số lượng | INTEGER | Đếm sản phẩm nguyên chiếc |
| Trạng thái | VARCHAR + CHECK | Miền giá trị rõ |
| Thời gian tạo | TIMESTAMPTZ | Gắn với một instant |
| Currency | CHAR(3) | Mã tiền tệ ba ký tự |
| Ghi chú | TEXT | Độ dài linh hoạt |

### 6.1. Không dùng FLOAT cho tiền

FLOAT/REAL lưu số gần đúng theo biểu diễn nhị phân. Nhiều số thập phân như 0.1 không thể biểu diễn chính xác bằng nhị phân hữu hạn.

Với giá và số tiền thanh toán, dùng **NUMERIC/DECIMAL** hoặc số nguyên theo đơn vị nhỏ nhất được quy định. Nếu dùng integer cho tiền, phải biết đơn vị là đồng, xu hay minor unit của từng loại tiền.

### 6.2. Số lượng có thể là số lẻ?

Nếu bán sản phẩm theo kg/lít, quantity có thể cần NUMERIC thay cho INTEGER. Constraint phải theo nghiệp vụ:

~~~sql
quantity NUMERIC(12,3) NOT NULL
    CHECK (quantity > 0)
~~~

Không dùng INTEGER chỉ vì ví dụ sản phẩm là bàn phím; hãy chọn kiểu theo hàng hóa thực tế.

### 6.3. Trạng thái và CHECK

CHECK phù hợp cho tập trạng thái nhỏ, ổn định:

~~~sql
order_status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
    CHECK (
        order_status IN (
            'DRAFT', 'PLACED', 'PAID',
            'CANCELLED', 'FULFILLED'
        )
    )
~~~

Nếu trạng thái cần cấu hình động, dịch thuật, metadata hoặc quy trình phức tạp, có thể dùng bảng status riêng và FK. CHECK không tự quản lý chuyển trạng thái hợp lệ từ DRAFT sang PAID hay cấm CANCELLED sau FULFILLED; đó là quy tắc chuyển trạng thái cần xử lý bằng transaction, trigger hoặc nghiệp vụ ứng dụng.

## 7. Chọn hành vi ON DELETE và ON UPDATE

Khi một hàng cha bị xóa, FK có thể:

| Hành vi | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| RESTRICT | Từ chối xóa nếu còn hàng con tham chiếu | Không xóa sản phẩm đã bán |
| NO ACTION | Kiểm tra FK theo thời điểm engine quy định | Mặc định phổ biến |
| CASCADE | Xóa hàng con theo hàng cha | Dữ liệu phụ thuộc hoàn toàn |
| SET NULL | Đặt FK phía con thành NULL | Danh mục bị xóa, sản phẩm vẫn còn |
| SET DEFAULT | Đặt FK về DEFAULT | Chỉ khi default tham chiếu hợp lệ |

### 7.1. Không CASCADE tùy tiện trên dữ liệu giao dịch

Nếu xóa customer mà CASCADE xuống orders, order_items và payments, hệ thống có thể xóa mất lịch sử bán hàng. Với dữ liệu giao dịch, thường nên:

- Không cho xóa khách đã có đơn (RESTRICT/NO ACTION).
- Đánh dấu khách inactive/archived.
- Giữ đơn và snapshot lịch sử.

CASCADE phù hợp hơn cho dữ liệu con thực sự phụ thuộc vòng đời của cha, chẳng hạn bản ghi tạm hoặc dữ liệu phụ thuộc có thể tái tạo. Với order_items, quyết định CASCADE hay RESTRICT tùy chính sách xóa đơn nháp; trong ví dụ này ta chọn RESTRICT để bảo vệ lịch sử.

### 7.2. ON UPDATE CASCADE

Với surrogate ID, cách tốt thường là **không cập nhật khóa chính**. Nếu mã nghiệp vụ đổi, cập nhật cột mã có UNIQUE, không đổi ID kỹ thuật. ON UPDATE CASCADE có thể hữu ích cho khóa tự nhiên, nhưng làm thay đổi nhiều hàng liên quan và tăng độ phức tạp.

### 7.3. Xóa mềm

Thay vì DELETE:

~~~sql
UPDATE products
SET is_active = FALSE
WHERE product_id = 10;
~~~

Sản phẩm ngừng bán nhưng vẫn được tham chiếu bởi đơn cũ. Xóa mềm không thay thế FK, nhưng thường phù hợp với dữ liệu cần lưu lịch sử.

## 8. Snapshot lịch sử: giá và địa chỉ tại thời điểm mua

Giá niêm yết trong products là **giá hiện tại**. Khi tạo order_item, cần chụp giá bán thực tế vào dòng đơn:

~~~text
products.unit_price             = giá hiện tại
order_items.unit_price          = giá tại thời điểm mua
order_items.product_name_snapshot = tên tại thời điểm mua
order_items.sku_snapshot        = SKU tại thời điểm mua
~~~

Nếu sản phẩm đổi tên hoặc tăng giá sau này, đơn cũ vẫn hiển thị đúng thông tin lúc mua.

Tương tự, orders có thể lưu snapshot người nhận và địa chỉ giao hàng. Khóa ngoại tới customer_addresses giúp xác nhận địa chỉ thuộc đúng khách tại thời điểm tạo đơn; các cột snapshot giữ nội dung lịch sử nếu hồ sơ địa chỉ sau đó thay đổi theo quy trình cho phép.

**Snapshot là một sự lặp dữ liệu có chủ đích**, không phải lỗi chuẩn hóa. Nó ghi lại sự kiện giao dịch tại thời điểm xảy ra.

## 9. Xây dựng lược đồ PostgreSQL hoàn chỉnh

Phần này tạo schema sales_demo. Chạy trên database học tập bằng tài khoản có quyền CREATE SCHEMA/TABLE. Nếu schema đã tồn tại, hãy dùng một database test mới hoặc chủ động đổi tên schema; không xóa schema cũ chỉ để chạy lại ví dụ.

### 9.1. Tạo schema và bảng customers

~~~sql
CREATE SCHEMA sales_demo;

CREATE TABLE sales_demo.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_code VARCHAR(30) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(254),
    phone VARCHAR(30),
    customer_status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_customers
        PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_code
        UNIQUE (customer_code),
    CONSTRAINT ck_customers_status
        CHECK (customer_status IN ('ACTIVE', 'INACTIVE', 'BLOCKED'))
);
~~~

Giải thích:

- customer_id là surrogate primary key.
- customer_code là business key, phải có và không trùng.
- full_name bắt buộc.
- email và phone có thể chưa biết nên cho NULL.
- trạng thái có DEFAULT ACTIVE và CHECK giới hạn giá trị.
- created_at được database gán nếu INSERT bỏ cột.

Ta không đặt UNIQUE trên email trong ví dụ vì quy tắc email trùng/hoa thường cần được xác định theo nghiệp vụ và collation. Nếu email là định danh đăng nhập, cần thiết kế normalized email và uniqueness rõ ràng.

### 9.2. Tạo customer_addresses với khóa ghép

~~~sql
CREATE TABLE sales_demo.customer_addresses (
    customer_id BIGINT NOT NULL,
    address_id SMALLINT NOT NULL,
    address_label VARCHAR(30) NOT NULL,
    recipient_name VARCHAR(150) NOT NULL,
    address_line VARCHAR(300) NOT NULL,
    city VARCHAR(100) NOT NULL,
    province VARCHAR(100),
    postal_code VARCHAR(20),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT pk_customer_addresses
        PRIMARY KEY (customer_id, address_id),
    CONSTRAINT uq_customer_address_label
        UNIQUE (customer_id, address_label),
    CONSTRAINT fk_addresses_customer
        FOREIGN KEY (customer_id)
        REFERENCES sales_demo.customers(customer_id)
        ON DELETE RESTRICT
);
~~~

address_id chỉ duy nhất trong phạm vi một customer. UNIQUE(customer_id,address_label) ngăn cùng khách tạo hai địa chỉ có cùng nhãn, ví dụ HOME.

Ràng buộc trên chưa bảo đảm mỗi khách chỉ có đúng một địa chỉ default. Nếu cần invariant đó, PostgreSQL có thể dùng partial unique index:

~~~sql
CREATE UNIQUE INDEX uq_one_default_address_per_customer
ON sales_demo.customer_addresses(customer_id)
WHERE is_default;
~~~

Partial index là tính năng theo hệ; cần cách tương ứng khi port sang RDBMS khác.

### 9.3. Tạo categories

~~~sql
CREATE TABLE sales_demo.categories (
    category_id BIGINT GENERATED ALWAYS AS IDENTITY,
    category_code VARCHAR(30) NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT pk_categories
        PRIMARY KEY (category_id),
    CONSTRAINT uq_categories_code
        UNIQUE (category_code),
    CONSTRAINT uq_categories_name
        UNIQUE (category_name)
);
~~~

category_code và category_name đang được yêu cầu duy nhất toàn bảng. Nếu tên danh mục chỉ duy nhất trong một ngôn ngữ hoặc một cây phân cấp, phải thay đổi khóa UNIQUE theo đúng phạm vi.

### 9.4. Tạo products

~~~sql
CREATE TABLE sales_demo.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY,
    sku VARCHAR(40) NOT NULL,
    category_id BIGINT,
    product_name VARCHAR(200) NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_products
        PRIMARY KEY (product_id),
    CONSTRAINT uq_products_sku
        UNIQUE (sku),
    CONSTRAINT ck_products_price
        CHECK (unit_price >= 0),
    CONSTRAINT fk_products_category
        FOREIGN KEY (category_id)
        REFERENCES sales_demo.categories(category_id)
        ON DELETE SET NULL
);
~~~

category_id được phép NULL để sản phẩm vẫn tồn tại khi chưa phân loại. Nếu một category bị xóa, FK SET NULL giữ sản phẩm lại. Trong hệ bán hàng lịch sử, sản phẩm thường được ngừng bán bằng is_active = FALSE thay vì DELETE.

### 9.5. Tạo orders

~~~sql
CREATE TABLE sales_demo.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY,
    order_no VARCHAR(30) NOT NULL,
    customer_id BIGINT NOT NULL,
    shipping_address_id SMALLINT,
    shipping_recipient_snapshot VARCHAR(150),
    shipping_address_snapshot VARCHAR(500),
    order_status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    currency_code CHAR(3) NOT NULL DEFAULT 'VND',
    placed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_orders
        PRIMARY KEY (order_id),
    CONSTRAINT uq_orders_order_no
        UNIQUE (order_no),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES sales_demo.customers(customer_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_orders_shipping_address
        FOREIGN KEY (customer_id, shipping_address_id)
        REFERENCES sales_demo.customer_addresses(customer_id, address_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_orders_status
        CHECK (
            order_status IN (
                'DRAFT', 'PLACED', 'PAID',
                'CANCELLED', 'FULFILLED'
            )
        ),
    CONSTRAINT ck_orders_shipping_snapshot
        CHECK (
            (shipping_recipient_snapshot IS NULL
             AND shipping_address_snapshot IS NULL)
            OR
            (shipping_recipient_snapshot IS NOT NULL
             AND shipping_address_snapshot IS NOT NULL)
        )
);
~~~

Các điểm quan trọng:

- order_no là mã đơn nghiệp vụ duy nhất.
- customer_id NOT NULL và FK bảo đảm khách tồn tại.
- Cặp (customer_id, shipping_address_id) tham chiếu đúng địa chỉ của đúng khách.
- shipping_address_id NULL có thể biểu diễn đơn không cần giao địa chỉ, chẳng hạn pickup; composite FK mặc định MATCH SIMPLE không kiểm tra quan hệ nếu một cột tham chiếu NULL. customer_id vẫn được kiểm tra bởi FK riêng.
- Snapshot người nhận và địa chỉ phải cùng NULL hoặc cùng có giá trị.
- currency_code được lưu trên đơn để biết đơn tính theo tiền tệ nào.
- Trạng thái chỉ thuộc miền cho phép; chuyển trạng thái hợp lệ là quy tắc nghiệp vụ bổ sung.

### 9.6. Tạo order_items

~~~sql
CREATE TABLE sales_demo.order_items (
    order_id BIGINT NOT NULL,
    line_no SMALLINT NOT NULL,
    product_id BIGINT NOT NULL,
    sku_snapshot VARCHAR(40) NOT NULL,
    product_name_snapshot VARCHAR(200) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL,
    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0,

    CONSTRAINT pk_order_items
        PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES sales_demo.orders(order_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id)
        REFERENCES sales_demo.products(product_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_order_items_line_no
        CHECK (line_no > 0),
    CONSTRAINT ck_order_items_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_order_items_unit_price
        CHECK (unit_price >= 0),
    CONSTRAINT ck_order_items_discount
        CHECK (
            discount_amount >= 0
            AND discount_amount <= quantity * unit_price
        )
);
~~~

Khóa chính ghép (order_id,line_no) bảo đảm mỗi dòng có số thứ tự riêng trong một đơn. product_id tham chiếu sản phẩm hiện có; sku_snapshot, product_name_snapshot và unit_price lưu thông tin lúc bán.

discount_amount là **tổng chiết khấu của cả dòng**, không phải chiết khấu mỗi sản phẩm. Vì vậy điều kiện tối đa là quantity * unit_price.

Không đặt UNIQUE(order_id, product_id) trong ví dụ: cùng sản phẩm có thể xuất hiện ở nhiều dòng nếu khác lô, mức giá, quà tặng hoặc lý do chiết khấu. Chỉ thêm UNIQUE khi nghiệp vụ thật sự cấm lặp sản phẩm trong một đơn.

### 9.7. Tạo payments

~~~sql
CREATE TABLE sales_demo.payments (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY,
    order_id BIGINT NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    payment_method VARCHAR(20) NOT NULL,
    payment_status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    provider_reference VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_payments
        PRIMARY KEY (payment_id),
    CONSTRAINT fk_payments_order
        FOREIGN KEY (order_id)
        REFERENCES sales_demo.orders(order_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_payments_amount
        CHECK (amount > 0),
    CONSTRAINT ck_payments_method
        CHECK (
            payment_method IN (
                'CARD', 'BANK_TRANSFER', 'CASH', 'WALLET'
            )
        ),
    CONSTRAINT ck_payments_status
        CHECK (
            payment_status IN (
                'PENDING', 'SUCCEEDED', 'FAILED', 'REFUNDED'
            )
        )
);
~~~

Một đơn có thể có nhiều payment attempt, nên payment_id là khóa riêng và order_id không UNIQUE. Bảng này mô tả các lần thanh toán; nếu nghiệp vụ có hoàn tiền từng phần, nên mô hình hóa refund thành sự kiện/bảng riêng thay vì chỉ đổi trạng thái payment thành REFUNDED.

Trong ví dụ, currency của payment được hiểu là currency của order. Nếu cổng thanh toán có thể thu bằng tiền tệ khác, cần lưu payment_currency, exchange rate, số tiền gốc và quy tắc làm tròn rõ ràng.

## 10. Tạo index cho khóa ngoại và truy vấn phổ biến

Primary key và UNIQUE thường tạo index tương ứng. Nhưng nhiều hệ **không tự tạo index ở phía cột tham chiếu của foreign key**. PostgreSQL không tự tạo index trên các cột FK phía con; SQL Server và Oracle cũng cần cân nhắc riêng. InnoDB của MySQL thường tạo index cần thiết cho FK nếu chưa có index phù hợp. SQLite không tự tạo mọi index phục vụ truy vấn join.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX ix_products_category
ON sales_demo.products(category_id);

CREATE INDEX ix_orders_customer_placed
ON sales_demo.orders(customer_id, placed_at DESC);

CREATE INDEX ix_orders_shipping_address
ON sales_demo.orders(customer_id, shipping_address_id);

CREATE INDEX ix_order_items_product
ON sales_demo.order_items(product_id);

CREATE INDEX ix_payments_order
ON sales_demo.payments(order_id);
~~~

Lưu ý:

- PK(customer_id,address_id) đã có index với customer_id đứng đầu, nên không cần tạo thêm một index customer_id đơn lẻ nếu chưa có workload cụ thể chứng minh cần thiết.
- PK(order_id,line_no) hỗ trợ truy vấn order_items theo order_id; không tự hỗ trợ tốt truy vấn theo product_id, vì vậy ix_order_items_product hữu ích cho chiều truy vấn đó.
- FK của orders tới customer_addresses dùng cặp customer_id,shipping_address_id; index phù hợp hỗ trợ kiểm tra/xóa/cập nhật liên quan.
- Không tạo index trên mọi cột chỉ vì cột xuất hiện trong FK hoặc WHERE. Index làm tăng dung lượng và chi phí ghi.

Xem kế hoạch thực thi bằng EXPLAIN trên dữ liệu đại diện. Với bảng nhỏ, planner có thể chọn scan toàn bảng dù index tồn tại.

## 11. Nạp dữ liệu mẫu theo khóa nghiệp vụ

Các bảng dùng identity tự sinh, vì vậy ta lấy ID bằng cách truy vấn mã nghiệp vụ thay vì giả định IDENTITY luôn bắt đầu từ 1.

### 11.1. Customers

~~~sql
INSERT INTO sales_demo.customers
    (customer_code, full_name, email, phone)
VALUES
    ('CUST-001', 'An Nguyen', 'an@example.test', '0900000001'),
    ('CUST-002', 'Binh Tran', 'binh@example.test', '0900000002');
~~~

### 11.2. Addresses

~~~sql
INSERT INTO sales_demo.customer_addresses
    (customer_id, address_id, address_label,
     recipient_name, address_line, city, province, is_default)
SELECT
    customer_id, 1, 'HOME',
    full_name, '12 Nguyen Trai', 'Ho Chi Minh City',
    'Ho Chi Minh City', TRUE
FROM sales_demo.customers
WHERE customer_code = 'CUST-001';

INSERT INTO sales_demo.customer_addresses
    (customer_id, address_id, address_label,
     recipient_name, address_line, city, province, is_default)
SELECT
    customer_id, 2, 'HOME',
    full_name, '25 Le Loi', 'Da Nang',
    'Da Nang', TRUE
FROM sales_demo.customers
WHERE customer_code = 'CUST-002';
~~~

address_id của khách thứ hai là 2 chỉ để làm rõ rằng address_id có phạm vi theo customer; nó không cần liên tục trong từng khách.

### 11.3. Categories và products

~~~sql
INSERT INTO sales_demo.categories(category_code, category_name)
VALUES
    ('ACCESSORY', 'Accessories'),
    ('OFFICE', 'Office equipment');

INSERT INTO sales_demo.products
    (sku, category_id, product_name, unit_price)
SELECT
    'KB-001', category_id, 'Mechanical Keyboard', 850000
FROM sales_demo.categories
WHERE category_code = 'ACCESSORY';

INSERT INTO sales_demo.products
    (sku, category_id, product_name, unit_price)
SELECT
    'MS-001', category_id, 'Wireless Mouse', 350000
FROM sales_demo.categories
WHERE category_code = 'ACCESSORY';

INSERT INTO sales_demo.products
    (sku, category_id, product_name, unit_price)
SELECT
    'DSK-001', category_id, 'Office Desk', 2500000
FROM sales_demo.categories
WHERE category_code = 'OFFICE';
~~~

### 11.4. Orders

~~~sql
INSERT INTO sales_demo.orders
    (order_no, customer_id, shipping_address_id,
     shipping_recipient_snapshot, shipping_address_snapshot,
     order_status, currency_code)
SELECT
    'SO-2026-001',
    c.customer_id,
    a.address_id,
    a.recipient_name,
    a.address_line || ', ' || a.city,
    'PAID',
    'VND'
FROM sales_demo.customers AS c
JOIN sales_demo.customer_addresses AS a
    ON a.customer_id = c.customer_id
WHERE c.customer_code = 'CUST-001'
  AND a.address_label = 'HOME';

INSERT INTO sales_demo.orders
    (order_no, customer_id, order_status, currency_code)
SELECT
    'SO-2026-002',
    customer_id,
    'PLACED',
    'VND'
FROM sales_demo.customers
WHERE customer_code = 'CUST-002';
~~~

Đơn thứ hai không chọn địa chỉ giao hàng trong ví dụ; cả hai shipping snapshot để NULL. Nếu hệ thống yêu cầu mọi đơn giao tận nơi phải có địa chỉ, hãy bổ sung cột fulfillment_method và CHECK tương ứng.

### 11.5. Order items

~~~sql
INSERT INTO sales_demo.order_items
    (order_id, line_no, product_id,
     sku_snapshot, product_name_snapshot,
     quantity, unit_price, discount_amount)
SELECT
    o.order_id, 1, p.product_id,
    p.sku, p.product_name,
    1, p.unit_price, 0
FROM sales_demo.orders AS o
CROSS JOIN sales_demo.products AS p
WHERE o.order_no = 'SO-2026-001'
  AND p.sku = 'KB-001';

INSERT INTO sales_demo.order_items
    (order_id, line_no, product_id,
     sku_snapshot, product_name_snapshot,
     quantity, unit_price, discount_amount)
SELECT
    o.order_id, 2, p.product_id,
    p.sku, p.product_name,
    2, p.unit_price, 50000
FROM sales_demo.orders AS o
CROSS JOIN sales_demo.products AS p
WHERE o.order_no = 'SO-2026-001'
  AND p.sku = 'MS-001';

INSERT INTO sales_demo.order_items
    (order_id, line_no, product_id,
     sku_snapshot, product_name_snapshot,
     quantity, unit_price, discount_amount)
SELECT
    o.order_id, 1, p.product_id,
    p.sku, p.product_name,
    1, p.unit_price, 0
FROM sales_demo.orders AS o
CROSS JOIN sales_demo.products AS p
WHERE o.order_no = 'SO-2026-002'
  AND p.sku = 'DSK-001';
~~~

Giá snapshot được lấy từ products tại thời điểm INSERT. Trong ứng dụng thực, thao tác đọc giá và tạo đơn cần nằm trong transaction với quy tắc khóa/giá áp dụng phù hợp để tránh giá đổi giữa hai bước.

### 11.6. Payments

~~~sql
INSERT INTO sales_demo.payments
    (order_id, amount, payment_method, payment_status)
SELECT order_id, 1500000, 'CARD', 'SUCCEEDED'
FROM sales_demo.orders
WHERE order_no = 'SO-2026-001';

INSERT INTO sales_demo.payments
    (order_id, amount, payment_method, payment_status)
SELECT order_id, 1000000, 'BANK_TRANSFER', 'PENDING'
FROM sales_demo.orders
WHERE order_no = 'SO-2026-002';
~~~

Đơn 001 có hai dòng hàng: bàn phím 850.000 và hai chuột 700.000 trừ chiết khấu 50.000, tổng 1.500.000. Payment thành công 1.500.000. Đơn 002 có một bàn 2.500.000 và một khoản đang chờ 1.000.000.

## 12. Tính tổng đơn và thanh toán đúng grain

Tổng tiền dòng:

~~~sql
quantity * unit_price - discount_amount
~~~

Tổng đơn là SUM của các dòng. Tổng thanh toán là SUM của các payment. Không JOIN trực tiếp order_items với payments rồi cộng cả hai nếu một đơn có nhiều dòng và nhiều lần thanh toán, vì hai quan hệ 1:N có thể nhân số hàng.

### 12.1. Truy vấn tổng hợp an toàn

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - discount_amount) AS order_total
    FROM sales_demo.order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) FILTER (
            WHERE payment_status = 'SUCCEEDED'
        ) AS paid_total
    FROM sales_demo.payments
    GROUP BY order_id
)
SELECT
    o.order_no,
    o.order_status,
    COALESCE(it.order_total, 0) AS order_total,
    COALESCE(pt.paid_total, 0) AS paid_total
FROM sales_demo.orders AS o
LEFT JOIN item_totals AS it
    ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
    ON pt.order_id = o.order_id
ORDER BY o.order_no;
~~~

FILTER là cú pháp PostgreSQL. Trên hệ không hỗ trợ aggregate FILTER, có thể dùng SUM(CASE WHEN payment_status = 'SUCCEEDED' THEN amount ELSE 0 END).

### 12.2. Expected result

| order_no | order_status | order_total | paid_total |
| --- | --- | ---: | ---: |
| SO-2026-001 | PAID | 1,500,000 | 1,500,000 |
| SO-2026-002 | PLACED | 2,500,000 | 0 |

Khoản 1.000.000 đang PENDING không được tính vào paid_total. Nếu JOIN trực tiếp item và payment, đơn 001 có 2 item và 1 payment; khi có thêm nhiều payment attempt, tổng có thể bị nhân bản.

### 12.3. Vì sao không lưu order_total ngay?

Có thể lưu tổng tiền trên orders để tăng tốc hoặc đóng băng số tiền đã chốt, nhưng khi đó cần quy tắc đồng bộ:

- Tính lại khi thêm/sửa/xóa order_item.
- Xử lý transaction đồng thời.
- Phân biệt tổng trước thuế, thuế, phí vận chuyển, giảm giá và số phải trả.
- Lưu currency và rounding policy.
- Có quy trình đối soát để phát hiện tổng lưu lệch với dòng chi tiết.

Trong schema cơ bản này, tổng được tính từ order_items để tránh hai nguồn dữ liệu mâu thuẫn. Khi đơn được chốt, hệ thống có thể lưu snapshot tổng đã xác nhận theo một thiết kế có kiểm soát.

## 13. Kiểm thử ràng buộc: dữ liệu hợp lệ và không hợp lệ

Một schema chỉ thực sự có ích khi test cả hai chiều:

- Dữ liệu hợp lệ phải INSERT được.
- Dữ liệu vi phạm phải bị database từ chối.

### 13.1. Test SKU trùng

~~~sql
INSERT INTO sales_demo.products
    (sku, product_name, unit_price)
VALUES
    ('KB-001', 'Another Keyboard', 700000);
~~~

Kỳ vọng: lỗi UNIQUE trên uq_products_sku.

### 13.2. Test giá âm

~~~sql
INSERT INTO sales_demo.products
    (sku, product_name, unit_price)
VALUES
    ('BAD-PRICE', 'Invalid Product', -1);
~~~

Kỳ vọng: lỗi CHECK trên ck_products_price.

### 13.3. Test số lượng bằng 0

~~~sql
INSERT INTO sales_demo.order_items
    (order_id, line_no, product_id,
     sku_snapshot, product_name_snapshot,
     quantity, unit_price, discount_amount)
SELECT
    o.order_id, 9, p.product_id,
    p.sku, p.product_name,
    0, p.unit_price, 0
FROM sales_demo.orders AS o
CROSS JOIN sales_demo.products AS p
WHERE o.order_no = 'SO-2026-001'
  AND p.sku = 'KB-001';
~~~

Kỳ vọng: lỗi CHECK quantity > 0.

### 13.4. Test chiết khấu lớn hơn giá trị dòng

~~~sql
INSERT INTO sales_demo.order_items
    (order_id, line_no, product_id,
     sku_snapshot, product_name_snapshot,
     quantity, unit_price, discount_amount)
SELECT
    o.order_id, 10, p.product_id,
    p.sku, p.product_name,
    1, p.unit_price, p.unit_price + 1
FROM sales_demo.orders AS o
CROSS JOIN sales_demo.products AS p
WHERE o.order_no = 'SO-2026-001'
  AND p.sku = 'KB-001';
~~~

Kỳ vọng: lỗi ck_order_items_discount.

### 13.5. Test FK tham chiếu khách không tồn tại

~~~sql
INSERT INTO sales_demo.orders(order_no, customer_id)
VALUES ('SO-INVALID-CUSTOMER', 999999);
~~~

Kỳ vọng: lỗi foreign key fk_orders_customer.

### 13.6. Test địa chỉ thuộc khách khác

Giả sử CUST-001 có address_id = 1 và CUST-002 có address_id = 2:

~~~sql
INSERT INTO sales_demo.orders
    (order_no, customer_id, shipping_address_id)
SELECT
    'SO-INVALID-ADDRESS',
    c1.customer_id,
    a2.address_id
FROM sales_demo.customers AS c1
CROSS JOIN sales_demo.customer_addresses AS a2
JOIN sales_demo.customers AS c2
    ON c2.customer_id = a2.customer_id
WHERE c1.customer_code = 'CUST-001'
  AND c2.customer_code = 'CUST-002';
~~~

Kỳ vọng: lỗi fk_orders_shipping_address vì cặp (customer CUST-001, address 2) không tồn tại, dù address 2 tồn tại cho CUST-002.

### 13.7. Test line_no trùng trong cùng đơn

Chèn thêm một dòng có cùng order_id và line_no = 1 của đơn SO-2026-001. Kỳ vọng lỗi PRIMARY KEY pk_order_items. Cùng line_no = 1 ở đơn SO-2026-002 lại hợp lệ vì order_id khác.

## 14. NULL, UNIQUE và CHECK: các bẫy cần hiểu

### 14.1. CHECK không tự thay NOT NULL

~~~sql
quantity INTEGER CHECK (quantity > 0)
~~~

Nếu quantity NULL, biểu thức quantity > 0 là UNKNOWN. Trong nhiều RDBMS, CHECK không từ chối UNKNOWN. Vì vậy, cột bắt buộc phải có giá trị cần khai báo:

~~~sql
quantity INTEGER NOT NULL CHECK (quantity > 0)
~~~

### 14.2. UNIQUE và NULL khác nhau theo hệ

Không giả định UNIQUE(email) có cùng hành vi NULL ở mọi engine:

- PostgreSQL mặc định cho phép nhiều NULL trong unique constraint; có tùy chọn NULLS NOT DISTINCT trên phiên bản hỗ trợ.
- MySQL thường cho phép nhiều NULL trong UNIQUE index.
- SQL Server unique constraint/index thông thường chỉ cho một giá trị NULL trong một cột đơn; có thể dùng filtered unique index khi muốn bỏ qua NULL.
- Oracle cho phép nhiều hàng NULL trong unique key theo quy tắc Oracle; khóa ghép có các chi tiết riêng.
- SQLite cho phép nhiều NULL trong UNIQUE.

Nếu email là tùy chọn nhưng các email đã nhập phải duy nhất, thiết kế cần kiểm tra engine cụ thể. Trên SQL Server có thể dùng:

~~~sql
CREATE UNIQUE INDEX uq_customers_email_not_null
ON dbo.Customers(email)
WHERE email IS NOT NULL;
~~~

Đây là filtered index, không phải cú pháp portable.

### 14.3. Chuỗi rỗng

PostgreSQL, MySQL, SQL Server và SQLite phân biệt NULL với chuỗi rỗng theo cách thông dụng. Oracle coi chuỗi ký tự rỗng như NULL trong nhiều ngữ cảnh SQL. Nếu trường mã bắt buộc không được rỗng, NOT NULL một mình có thể chưa đủ trên những hệ coi chuỗi chỉ có khoảng trắng hoặc chuỗi rỗng là giá trị hợp lệ; cần CHECK/validation phù hợp.

## 15. Ràng buộc nhiều cột và quy tắc nghiệp vụ

CHECK có thể xét nhiều cột trong cùng một hàng:

~~~sql
CHECK (discount_amount <= quantity * unit_price)
~~~

Ví dụ khác:

~~~sql
CHECK (
    (shipping_recipient_snapshot IS NULL
     AND shipping_address_snapshot IS NULL)
    OR
    (shipping_recipient_snapshot IS NOT NULL
     AND shipping_address_snapshot IS NOT NULL)
)
~~~

Điều này bảo đảm snapshot người nhận và địa chỉ hoặc cùng có, hoặc cùng vắng mặt.

### 15.1. CHECK không phải truy vấn liên bảng

Không nên viết CHECK với mục tiêu đọc bảng khác, ví dụ “tổng payment không vượt order_total” nếu engine không hỗ trợ hoặc không bảo đảm tính nhất quán của cross-table check. PostgreSQL CHECK được thiết kế cho điều kiện trên hàng hiện tại và không bảo đảm theo dõi thay đổi ở hàng khác.

Các quy tắc liên bảng thường cần:

- Transaction và locking phù hợp.
- Trigger khi thực sự cần ở database.
- Stored procedure làm đường ghi duy nhất.
- Một mô hình ledger/aggregate có invariant rõ.

### 15.2. Một số quy tắc không thể diễn đạt chỉ bằng FK

Ví dụ:

- Đơn PAID phải có ít nhất một payment SUCCEEDED.
- Không được refund nhiều hơn số đã thanh toán.
- Không cho chuyển CANCELLED sang FULFILLED.
- Mỗi khách chỉ có một địa chỉ mặc định.
- Tổng số lượng tồn không âm sau nhiều giao dịch đồng thời.

Một số quy tắc có thể dùng partial unique index, trigger hoặc deferred constraint; một số cần transaction và locking. Đừng cố nhét mọi nghiệp vụ vào một CHECK đơn giản.

## 16. DEFERRABLE constraints và thứ tự ghi

Một số hệ cho phép trì hoãn kiểm tra một số ràng buộc tới cuối transaction:

~~~sql
CONSTRAINT fk_example
FOREIGN KEY (parent_id)
REFERENCES parent_table(parent_id)
DEFERRABLE INITIALLY DEFERRED
~~~

Với PostgreSQL, có thể dùng SET CONSTRAINTS để đổi thời điểm kiểm tra trong transaction đối với constraint DEFERRABLE.

Điều này hữu ích khi phải tạo/cập nhật một nhóm bản ghi có tham chiếu lẫn nhau mà trạng thái cuối transaction mới hợp lệ. Không nên bật deferred cho mọi FK vì nó làm thay đổi thời điểm lỗi và tăng độ phức tạp kiểm thử.

Khả năng trì hoãn khác nhau theo RDBMS:

- PostgreSQL hỗ trợ deferrable cho một số loại constraint.
- Oracle hỗ trợ DEFERRABLE/INITIALLY DEFERRED cho một số constraint.
- SQLite hỗ trợ deferred foreign key.
- MySQL InnoDB không hỗ trợ deferred FK theo cách tương đương.
- SQL Server không có cú pháp DEFERRABLE constraint tổng quát tương đương.

## 17. Quy tắc xóa dữ liệu trong lược đồ bán hàng

Hãy lập ma trận trước khi chọn ON DELETE:

| Quan hệ | Hành vi trong ví dụ | Lý do |
| --- | --- | --- |
| customers → customer_addresses | RESTRICT | Không xóa khách còn địa chỉ phụ thuộc |
| customers → orders | RESTRICT | Giữ lịch sử đơn |
| customer_addresses → orders | RESTRICT | Giữ địa chỉ tham chiếu và snapshot |
| categories → products | SET NULL | Sản phẩm còn tồn tại khi danh mục bị xóa |
| orders → order_items | RESTRICT | Không xóa nhầm chi tiết đơn lịch sử |
| products → order_items | RESTRICT | Không xóa sản phẩm đã được bán |
| orders → payments | RESTRICT | Bảo vệ lịch sử giao dịch |

Trong thực tế, có thể chọn CASCADE cho order_items nếu chỉ cho xóa đơn DRAFT và có quy trình xóa rõ ràng. Nhưng khi đã phát sinh thanh toán hoặc hóa đơn, xóa cascade thường không phù hợp.

### 17.1. Không xóa lịch sử để “dọn catalog”

Để ngừng bán:

~~~sql
UPDATE sales_demo.products
SET is_active = FALSE
WHERE sku = 'KB-001';
~~~

Để khóa khách:

~~~sql
UPDATE sales_demo.customers
SET customer_status = 'INACTIVE'
WHERE customer_code = 'CUST-001';
~~~

Dữ liệu giao dịch vẫn giữ FK hợp lệ.

## 18. Chuẩn hóa và những snapshot có chủ đích

Lược đồ trên tách:

- Thông tin khách khỏi đơn hàng.
- Danh mục khỏi sản phẩm.
- Phần đầu đơn khỏi các dòng hàng.
- Lần thanh toán khỏi đơn hàng.

Điều này tránh lặp thông tin hiện tại ở mọi đơn. Tuy nhiên, order_items lưu tên/SKU/giá snapshot và orders lưu địa chỉ snapshot. Đây là sự lặp có chủ đích để giữ lịch sử.

### 18.1. Vì sao không chỉ JOIN products để hiển thị tên?

Nếu sản phẩm đổi tên từ “Mechanical Keyboard” thành “Keyboard Pro”, JOIN products sẽ hiển thị tên mới cho đơn cũ. Snapshot giữ tên đã bán tại thời điểm đặt hàng.

### 18.2. Vì sao không chỉ JOIN customer_addresses?

Nếu khách sửa địa chỉ hoặc chuyển nhà, đơn cũ vẫn phải thể hiện địa chỉ nhận hàng lúc đặt. Snapshot trong orders giữ bằng chứng nghiệp vụ; FK address giúp xác định địa chỉ nguồn khi cần.

### 18.3. Khi nào snapshot cần bất biến?

Sau khi đơn được chốt, các snapshot quan trọng thường không được sửa tùy tiện. Có thể kiểm soát bằng quyền UPDATE, stored procedure hoặc trigger. Schema cơ bản không tự bảo đảm bất biến lịch sử chỉ bằng các FK/CHECK.

## 19. Thay đổi schema an toàn bằng migration

Giả sử bảng orders đang chạy thật và cần thêm order_status NOT NULL.

Không phải lúc nào cũng có thể thêm cột NOT NULL ngay khi bảng đã có dữ liệu. Một lộ trình migration thường là:

1. Thêm cột cho phép NULL hoặc có DEFAULT phù hợp.
2. Backfill dữ liệu cũ theo quy tắc nghiệp vụ.
3. Kiểm tra không còn NULL/giá trị sai.
4. Thêm CHECK/NOT NULL/UNIQUE/FK theo chiến lược ít khóa phù hợp.
5. Cập nhật ứng dụng đọc/ghi cột mới.
6. Theo dõi lỗi và xác minh constraint được validate.

PostgreSQL có các lựa chọn như ADD CONSTRAINT NOT VALID rồi VALIDATE CONSTRAINT cho một số FK/CHECK, giúp tách việc tạo constraint khỏi validate toàn bộ dữ liệu cũ. Unique constraint thường cần chiến lược index riêng, chẳng hạn CREATE UNIQUE INDEX CONCURRENTLY rồi gắn constraint khi phù hợp.

### 19.1. Migration phải kiểm tra dữ liệu cũ

Trước khi thêm UNIQUE:

~~~sql
SELECT sku, COUNT(*)
FROM products
GROUP BY sku
HAVING COUNT(*) > 1;
~~~

Trước khi thêm FK:

~~~sql
SELECT o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

Trước khi thêm CHECK quantity > 0:

~~~sql
SELECT *
FROM order_items
WHERE quantity <= 0
   OR quantity IS NULL;
~~~

Phải xử lý dữ liệu vi phạm trước khi validate constraint. Không xóa hoặc tự sửa dữ liệu production mà chưa có quy tắc nghiệp vụ.

## 20. Khác biệt giữa các hệ quản trị

Schema ở phần 9 là PostgreSQL. Khi chuyển sang hệ khác, phải đổi cú pháp và hiểu cả semantics.

### 20.1. Identity / auto-generated key

| Hệ | Cách thường dùng |
| --- | --- |
| PostgreSQL | GENERATED ALWAYS AS IDENTITY |
| MySQL | AUTO_INCREMENT |
| SQL Server | IDENTITY(1,1) |
| Oracle | GENERATED BY DEFAULT AS IDENTITY |
| SQLite | INTEGER PRIMARY KEY; AUTOINCREMENT chỉ dùng khi thật sự cần quy tắc không tái sử dụng rowid |

Identity/auto increment không bảo đảm số liên tục. Rollback, cache, lỗi insert hoặc concurrent transaction có thể tạo khoảng trống. Không dùng ID làm số hóa đơn cần liên tục theo luật/nghiệp vụ nếu không có bộ cấp số riêng.

### 20.2. Kiểu boolean

| Hệ | Kiểu thường dùng |
| --- | --- |
| PostgreSQL | BOOLEAN |
| MySQL | BOOLEAN/BOOL là alias TINYINT(1) |
| SQL Server | BIT |
| Oracle | Không có SQL BOOLEAN cho cột bảng theo cách phổ biến; thường dùng NUMBER(1) hoặc CHAR với CHECK |
| SQLite | Thường dùng INTEGER 0/1 theo quy ước hoặc STRICT table phù hợp |

### 20.3. Kiểu thời gian

PostgreSQL có TIMESTAMP WITH TIME ZONE/TIMESTAMPTZ; MySQL có TIMESTAMP/DATETIME với semantics khác; SQL Server có datetime2/datetimeoffset; Oracle có TIMESTAMP WITH TIME ZONE; SQLite không có kiểu datetime storage class riêng mà lưu TEXT/REAL/INTEGER theo quy ước.

Đối với sự kiện xảy ra tại một thời điểm, lưu instant có timezone/UTC theo chính sách rõ. Đối với ngày nghiệp vụ không có giờ, dùng DATE. Đừng lưu ngày sinh hoặc ngày hóa đơn như timestamp tùy tiện.

### 20.4. CHECK

MySQL chỉ thực thi CHECK constraint trên các phiên bản hiện đại từ 8.0.16; các bản cũ hơn có thể parse nhưng bỏ qua constraint. SQL Server, Oracle, PostgreSQL và SQLite có CHECK với chi tiết khác nhau.

### 20.5. ON DELETE

PostgreSQL/MySQL/SQLite hỗ trợ RESTRICT/NO ACTION theo quy tắc riêng. SQL Server và Oracle thường dùng NO ACTION hoặc hành vi mặc định thay vì cú pháp ON DELETE RESTRICT. MySQL InnoDB hỗ trợ CASCADE, SET NULL, RESTRICT/NO ACTION theo engine. Hãy kiểm tra phiên bản và engine thực tế.

### 20.6. Deferred constraints

Không chuyển DEFERRABLE INITIALLY DEFERRED nguyên văn sang mọi RDBMS. PostgreSQL, Oracle và SQLite có hỗ trợ trong phạm vi nhất định; MySQL InnoDB và SQL Server không có semantics deferred FK tương đương.

## 21. Ví dụ DDL khung theo từng hệ

Các ví dụ sau chỉ minh họa cách khai báo identity, khóa và một số kiểu dữ liệu; chúng không phải toàn bộ schema bán hàng có thể copy nguyên văn qua các engine.

### 21.1. MySQL 8.0+

~~~sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    customer_code VARCHAR(30) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    customer_status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_code (customer_code),
    CONSTRAINT ck_customers_status
        CHECK (customer_status IN ('ACTIVE', 'INACTIVE', 'BLOCKED'))
) ENGINE = InnoDB;
~~~

Chọn InnoDB để có transaction và FK. Kiểm tra MySQL version để bảo đảm CHECK được thực thi.

### 21.2. SQL Server

~~~sql
CREATE TABLE dbo.Customers (
    CustomerId BIGINT IDENTITY(1,1) NOT NULL,
    CustomerCode VARCHAR(30) NOT NULL,
    FullName NVARCHAR(150) NOT NULL,
    CustomerStatus VARCHAR(16) NOT NULL
        CONSTRAINT df_customers_status DEFAULT 'ACTIVE',
    CONSTRAINT pk_customers PRIMARY KEY (CustomerId),
    CONSTRAINT uq_customers_code UNIQUE (CustomerCode),
    CONSTRAINT ck_customers_status
        CHECK (CustomerStatus IN ('ACTIVE', 'INACTIVE', 'BLOCKED'))
);
~~~

SQL Server dùng NVARCHAR cho Unicode theo mô hình UTF-16 truyền thống; varchar có thể dùng UTF-8 khi collation hỗ trợ.

### 21.3. Oracle

~~~sql
CREATE TABLE customers (
    customer_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_code VARCHAR2(30 CHAR) NOT NULL,
    full_name VARCHAR2(150 CHAR) NOT NULL,
    customer_status VARCHAR2(16 CHAR) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT pk_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_code UNIQUE (customer_code),
    CONSTRAINT ck_customers_status
        CHECK (customer_status IN ('ACTIVE', 'INACTIVE', 'BLOCKED'))
);
~~~

Oracle dùng VARCHAR2 và NUMBER; cần chọn CHAR/BYTE semantics phù hợp với giới hạn dữ liệu đa byte.

### 21.4. SQLite

~~~sql
PRAGMA foreign_keys = ON;

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    customer_code TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    customer_status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (customer_status IN ('ACTIVE', 'INACTIVE', 'BLOCKED'))
);
~~~

Trong SQLite, INTEGER PRIMARY KEY gắn với rowid theo quy tắc đặc biệt. Bật PRAGMA foreign_keys = ON cho mỗi connection nếu cần thực thi FK; đừng giả định mọi connection tự bật.

## 22. Kiểm tra schema và dữ liệu

Sau khi tạo bảng và seed dữ liệu, hãy kiểm tra:

### 22.1. Số lượng bản ghi

~~~sql
SELECT 'customers' AS table_name, COUNT(*) AS row_count
FROM sales_demo.customers
UNION ALL
SELECT 'orders', COUNT(*)
FROM sales_demo.orders
UNION ALL
SELECT 'order_items', COUNT(*)
FROM sales_demo.order_items
UNION ALL
SELECT 'payments', COUNT(*)
FROM sales_demo.payments;
~~~

Expected:

| table_name | row_count |
| --- | ---: |
| customers | 2 |
| orders | 2 |
| order_items | 3 |
| payments | 2 |

### 22.2. Kiểm tra đơn không có dòng hàng

~~~sql
SELECT o.order_no
FROM sales_demo.orders AS o
LEFT JOIN sales_demo.order_items AS i
    ON i.order_id = o.order_id
WHERE i.order_id IS NULL;
~~~

Với fixture mẫu, không có kết quả vì cả hai đơn đều có ít nhất một dòng.

### 22.3. Kiểm tra địa chỉ giao hàng không thuộc khách

FK đã ngăn dữ liệu sai, nhưng có thể dùng truy vấn audit nếu migrate dữ liệu cũ:

~~~sql
SELECT
    o.order_no,
    o.customer_id,
    o.shipping_address_id
FROM sales_demo.orders AS o
LEFT JOIN sales_demo.customer_addresses AS a
    ON a.customer_id = o.customer_id
   AND a.address_id = o.shipping_address_id
WHERE o.shipping_address_id IS NOT NULL
  AND a.address_id IS NULL;
~~~

Kết quả rỗng là trạng thái mong muốn.

### 22.4. Kiểm tra sản phẩm có SKU trùng

~~~sql
SELECT sku, COUNT(*)
FROM sales_demo.products
GROUP BY sku
HAVING COUNT(*) > 1;
~~~

Kết quả rỗng. UNIQUE constraint bảo vệ dữ liệu mới; truy vấn audit hữu ích khi chuẩn bị migration hoặc xác minh dữ liệu import.

## 23. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng email làm PK | Email đổi làm thay đổi quan hệ | Dùng surrogate key và UNIQUE theo nghiệp vụ |
| Không có UNIQUE cho SKU/order_no | Mã nghiệp vụ bị trùng | Thêm alternate key |
| FK cho phép NULL ngoài ý muốn | Hàng con không có quan hệ | NOT NULL khi quan hệ bắt buộc |
| CHECK mà quên NOT NULL | NULL có thể qua CHECK | Kết hợp NOT NULL |
| Dùng FLOAT cho tiền | Sai số làm tròn | NUMERIC/DECIMAL |
| Lưu giá hiện tại rồi JOIN cho đơn cũ | Lịch sử đơn thay đổi theo catalog | Lưu unit_price snapshot |
| Lưu mỗi customer_id và address_id FK riêng | Địa chỉ có thể thuộc khách khác | FK ghép (customer_id,address_id) |
| Dùng CASCADE trên orders/payments | Xóa mất lịch sử giao dịch | RESTRICT/soft delete |
| UNIQUE trên email tùy chọn mà không xem NULL semantics | Kết quả khác giữa RDBMS | Test NULL và collation theo hệ |
| Không index cột FK phía con | JOIN/xóa cha có thể tốn kém | Xem index hiện có, thêm khi cần |
| UNIQUE(order_id,product_id) không đúng nghiệp vụ | Không cho sản phẩm xuất hiện ở nhiều dòng | Chỉ thêm nếu thực sự cấm |
| JOIN items và payments rồi SUM cùng lúc | Fan-out nhân tổng | Aggregate mỗi nhánh trước |
| CHECK cố đọc bảng khác | Không bảo đảm invariant liên bảng | Transaction/trigger/procedure |
| Dùng IDENTITY làm số hóa đơn liên tục | Có gap và khó đáp ứng quy tắc nghiệp vụ | Bộ cấp số nghiệp vụ riêng |
| Xóa sản phẩm đã bán | Mất liên kết lịch sử | Ngừng bán bằng is_active |
| Dùng một bảng trộn order header và lines | Lặp thông tin khách/đơn | Tách orders/order_items |
| Chọn VARCHAR(n) mà không rõ đơn vị | Lỗi giới hạn Unicode | Xác định byte/character semantics |
| Thêm constraint khi dữ liệu cũ chưa sạch | Migration thất bại | Audit và backfill trước |

## 24. Bài tập thực hành

Hãy triển khai schema trên một database học tập. Trước mỗi thay đổi, dự đoán constraint nào sẽ chấp nhận hoặc từ chối.

1. Vẽ ERD cho customers, customer_addresses, categories, products, orders, order_items và payments.
2. Nêu grain của từng bảng.
3. Giải thích vì sao customers có cả customer_id và customer_code.
4. Tạo PK và UNIQUE cho customers.
5. Tạo khóa ghép (customer_id,address_id) cho customer_addresses.
6. Tạo UNIQUE(customer_id,address_label).
7. Tạo FK từ địa chỉ về khách hàng với ON DELETE RESTRICT.
8. Tạo products với SKU duy nhất và giá NUMERIC.
9. Tạo FK category_id với ON DELETE SET NULL.
10. Tạo orders với order_no duy nhất và FK customer_id.
11. Tạo FK ghép để shipping_address thuộc đúng customer.
12. Thử dùng địa chỉ khách B cho đơn khách A và xác nhận lỗi.
13. Tạo order_items với PK ghép (order_id,line_no).
14. Thử line_no <= 0 và quantity = 0.
15. Thử discount_amount lớn hơn giá trị dòng.
16. Lưu product_name_snapshot, sku_snapshot và unit_price snapshot.
17. Đổi tên/giá sản phẩm sau khi tạo đơn; kiểm tra snapshot không đổi.
18. Tạo payments cho một đơn với hai lần thanh toán.
19. Thử amount thanh toán bằng 0 và âm.
20. Viết truy vấn tính order_total từ order_items.
21. Viết truy vấn tính paid_total chỉ từ payment SUCCEEDED.
22. Cố tình JOIN order_items và payments trực tiếp; giải thích fan-out.
23. Sửa truy vấn bằng hai CTE aggregate riêng.
24. Lập ma trận ON DELETE cho từng quan hệ và giải thích lựa chọn.
25. Thử xóa customer đã có order; xác nhận RESTRICT.
26. Thử xóa category đang được product tham chiếu; xác nhận category_id thành NULL.
27. Tạo partial unique index bảo đảm mỗi khách chỉ có một địa chỉ default trên PostgreSQL.
28. Kiểm tra sự khác nhau giữa UNIQUE và UNIQUE + NOT NULL.
29. Thử CHECK trên cột nullable và giải thích UNKNOWN.
30. Viết migration thêm NOT NULL vào bảng đã có dữ liệu.
31. Tạo index cho FK product_id trong order_items và dùng EXPLAIN.
32. So sánh identity syntax giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite.
33. Viết DDL customers tương đương trên MySQL InnoDB.
34. Viết DDL customers tương đương trên SQL Server.
35. Viết DDL customers tương đương trên Oracle.
36. Viết DDL customers tương đương trên SQLite và bật foreign_keys.
37. Kiểm tra UNIQUE với nhiều NULL trên từng hệ.
38. Thiết kế bảng refunds cho hoàn tiền từng phần.
39. Đề xuất cách bảo vệ order snapshot sau khi đơn chuyển sang PAID.
40. Viết bộ test negative cho PK, FK, UNIQUE, NOT NULL, CHECK và DEFAULT.

### Câu hỏi tự kiểm tra

**Câu 1.** PRIMARY KEY và UNIQUE có giống nhau hoàn toàn không?

**Đáp án:** Không. Một bảng có một định nghĩa primary key; UNIQUE có thể có nhiều ràng buộc và semantics NULL tùy hệ. Primary key luôn không NULL.

**Câu 2.** Có surrogate key thì có cần UNIQUE trên SKU không?

**Đáp án:** Có, nếu SKU phải duy nhất theo nghiệp vụ. ID kỹ thuật không thay thế alternate key.

**Câu 3.** CHECK(quantity > 0) có tự từ chối NULL không?

**Đáp án:** Không phải trong nhiều hệ; kết hợp NOT NULL nếu bắt buộc.

**Câu 4.** Vì sao orders cần FK ghép tới customer_addresses?

**Đáp án:** Để bảo đảm địa chỉ tham chiếu thuộc đúng customer của đơn, không chỉ tồn tại ở một khách bất kỳ.

**Câu 5.** Vì sao lưu unit_price trong order_items?

**Đáp án:** Để giữ giá bán tại thời điểm mua khi giá catalog thay đổi.

**Câu 6.** Có nên CASCADE xóa customers xuống orders và payments không?

**Đáp án:** Thông thường không với dữ liệu giao dịch lịch sử; dùng RESTRICT/soft delete theo chính sách.

**Câu 7.** Có nên dùng FLOAT cho tiền không?

**Đáp án:** Không; dùng DECIMAL/NUMERIC hoặc integer theo đơn vị tiền đã xác định.

**Câu 8.** PostgreSQL tự tạo index ở phía cột tham chiếu của mọi FK không?

**Đáp án:** Không. Cần kiểm tra và tạo index phù hợp khi truy vấn/maintenance cần.

**Câu 9.** SUM(DISTINCT amount) có sửa lỗi fan-out khi JOIN nhiều dòng item không?

**Đáp án:** Không. Hai đơn khác nhau có cùng amount sẽ bị gộp; aggregate theo đúng grain.

**Câu 10.** CHECK có thể bảo đảm tổng payments không vượt order_total khi dữ liệu nằm ở hai bảng không?

**Đáp án:** Không bằng CHECK trên một hàng đơn giản; cần transaction/trigger/procedure và kiểm soát đồng thời.

## 25. Ghi nhớ cốt lõi

Một lược đồ bán hàng tốt bắt đầu từ **grain và quan hệ**, sau đó mới chọn khóa:

- Dùng **surrogate primary key** ổn định cho các thực thể chính.
- Bảo vệ mã nghiệp vụ bằng **UNIQUE + NOT NULL**.
- Dùng **foreign key** để giữ quan hệ hợp lệ.
- Dùng **khóa ghép** khi tính duy nhất nằm trong một phạm vi, như địa chỉ của khách hoặc dòng của đơn.
- Dùng **CHECK** cho điều kiện trên hàng, **NOT NULL** cho giá trị bắt buộc và **DEFAULT** cho giá trị mặc định.
- Chọn **ON DELETE** theo vòng đời dữ liệu; bảo vệ lịch sử giao dịch thay vì cascade xóa tùy tiện.
- Lưu **snapshot giá, tên sản phẩm và địa chỉ** khi cần giữ nguyên sự kiện tại thời điểm mua.
- Dùng **NUMERIC/DECIMAL** cho tiền và index theo truy vấn thật.

Trong schema thực hành, customers, customer_addresses, categories, products, orders, order_items và payments được tách theo đúng grain. Khóa ghép (customer_id,shipping_address_id) ngăn đơn tham chiếu địa chỉ của khách khác; PK (order_id,line_no) định danh dòng trong đơn; snapshot giữ lịch sử giá và tên; các FK/UNIQUE/CHECK bảo vệ dữ liệu ngay cả khi nhiều ứng dụng cùng ghi.

Cuối cùng, **khóa và ràng buộc không thay thế toàn bộ logic nghiệp vụ**. CHECK không tự kiểm tra tổng ở bảng khác, FK không bảo đảm trạng thái đơn hợp lệ, identity không cấp số hóa đơn liên tục, và index phía cha không tự giải quyết mọi truy vấn phía con. Hãy kết hợp schema, transaction, quyền ghi, kiểm thử negative và migration có kế hoạch. Khi chuyển giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite, hãy kiểm tra lại semantics chứ không chỉ đổi tên kiểu dữ liệu.
