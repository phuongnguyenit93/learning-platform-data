# SQL, khóa chính, khóa ngoại và ràng buộc dữ liệu cần biết

## 1. Vì sao cần hiểu các khái niệm này khi dùng Spring Data Relational R2DBC?

Spring Data Relational R2DBC giúp ứng dụng Java đọc và ghi dữ liệu trong cơ sở dữ liệu quan hệ theo mô hình reactive. R2DBC thay đổi cách ứng dụng giao tiếp bất đồng bộ với database; nó không thay thế SQL và cũng không tự bảo đảm rằng dữ liệu được lưu luôn hợp lệ.

Tính đúng đắn của dữ liệu trước hết được quyết định bởi cấu trúc bảng, kiểu dữ liệu, khóa và các ràng buộc mà database thực thi. Annotation trong Spring Data Relational mô tả cách ánh xạ đối tượng Java sang bảng và cột; chúng không tự động thay thế constraint trong schema SQL.

Ví dụ, một đối tượng Java có trường customerId kiểu Long không đủ để bảo đảm khách hàng đó tồn tại. Muốn database từ chối đơn hàng tham chiếu đến khách hàng không có thật, bảng đơn hàng cần có foreign key trỏ đến bảng khách hàng. Tương tự, kiểm tra email ở giao diện không ngăn được một tiến trình khác ghi trùng email trực tiếp vào database; constraint UNIQUE mới bảo vệ được quy tắc đó ở cấp dữ liệu.

Sau bài này, bạn cần có thể đọc câu lệnh tạo bảng, giải thích vai trò của primary key và foreign key, chọn constraint phù hợp, và hiểu cách những quy tắc đó phối hợp với code Spring Data Relational R2DBC.

## 2. Bảng, hàng, cột và kiểu dữ liệu trong SQL

Cơ sở dữ liệu quan hệ tổ chức dữ liệu thành các bảng. Một bảng thường biểu diễn một loại thực thể hoặc một tập hợp dữ liệu có cùng cấu trúc.

- **Bảng (table):** tập hợp các bản ghi, ví dụ customers hoặc orders.
- **Hàng (row):** một bản ghi cụ thể, ví dụ khách hàng có mã 101.
- **Cột (column):** một thuộc tính của bản ghi, ví dụ email hoặc created_at.
- **Kiểu dữ liệu (data type):** giới hạn dạng giá trị mà cột có thể lưu, ví dụ BIGINT, VARCHAR, DATE, TIMESTAMP, BOOLEAN hoặc DECIMAL.

Kiểu dữ liệu là lớp bảo vệ đầu tiên. Hãy chọn kiểu dựa trên ý nghĩa và miền giá trị của dữ liệu:

| Nhu cầu | Kiểu thường dùng | Lưu ý |
|---|---|---|
| Mã số nguyên lớn | BIGINT | Phù hợp với ID dạng số có thể tăng theo thời gian |
| Chuỗi có độ dài giới hạn | VARCHAR(n) | Chọn giới hạn hợp lý theo quy tắc nghiệp vụ |
| Nội dung văn bản dài | TEXT | Cú pháp và giới hạn cụ thể tùy hệ quản trị |
| Tiền hoặc số thập phân cần chính xác | DECIMAL(p, s) / NUMERIC(p, s) | Tránh dùng số dấu phẩy động cho phép tính tiền |
| Ngày | DATE | Không chứa thời điểm trong ngày |
| Thời điểm | TIMESTAMP hoặc kiểu tương đương | Thống nhất quy ước múi giờ của hệ thống |
| Đúng/sai | BOOLEAN | Một số hệ quản trị biểu diễn theo cách riêng |

DECIMAL(12, 2) có thể biểu diễn số có tối đa 12 chữ số, trong đó 2 chữ số ở phần thập phân. Ví dụ, giá 125000.50 phù hợp với kiểu này. Không nên chọn FLOAT hoặc DOUBLE cho số tiền nếu nghiệp vụ đòi hỏi kết quả thập phân chính xác, vì chúng là kiểu dấu phẩy động nhị phân và có thể có sai số biểu diễn.

SQL có khái niệm NULL, biểu thị giá trị chưa biết hoặc không được cung cấp. NULL không giống chuỗi rỗng (''), số 0, hay false. Các phép so sánh với NULL thường không trả về đúng/sai thông thường mà tạo ra trạng thái chưa xác định; vì vậy cần dùng IS NULL hoặc IS NOT NULL, không dùng = NULL.

Ví dụ:

~~~sql
SELECT id, email
FROM customers
WHERE deleted_at IS NULL;
~~~

Nếu một thuộc tính bắt buộc phải có, hãy khai báo NOT NULL. Việc chỉ kiểm tra ở Java không đủ để bảo vệ dữ liệu trước các luồng ghi khác.

## 3. Khóa chính (PRIMARY KEY)

### 3.1. Khái niệm và mục đích

Primary key (khóa chính) là một cột hoặc một nhóm cột dùng để định danh duy nhất mỗi hàng trong bảng. Một khóa chính phải thỏa mãn hai tính chất:

1. **Duy nhất:** không có hai hàng có cùng giá trị khóa chính.
2. **Không rỗng:** các cột thuộc khóa chính không được nhận NULL.

Mỗi bảng có tối đa một ràng buộc primary key. Ràng buộc đó có thể gồm nhiều cột, gọi là khóa chính ghép (composite primary key).

Ví dụ:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL
);
~~~

Ở đây, id xác định một khách hàng. Hai khách hàng không thể có cùng id, và một hàng khách hàng không thể thiếu id.

### 3.2. Khóa thay thế và khóa tự nhiên

Một khóa có thể là:

- **Khóa tự nhiên (natural key):** thuộc tính vốn có ý nghĩa nghiệp vụ và có thể định danh, ví dụ mã quốc gia hoặc mã sản phẩm do doanh nghiệp quản lý.
- **Khóa thay thế (surrogate key):** giá trị được tạo riêng để định danh bản ghi, ví dụ id dạng BIGINT hoặc UUID.

Trong nhiều ứng dụng, khóa thay thế giúp quan hệ giữa các bảng ổn định hơn. Email, số điện thoại hoặc tên có thể thay đổi, nên thường không phù hợp làm khóa chính dù có thể cần constraint UNIQUE để bảo đảm không trùng theo quy tắc nghiệp vụ.

Không nên giả định rằng một giá trị có vẻ duy nhất hôm nay sẽ luôn là định danh tốt. Hãy xem xét khả năng thay đổi, tính nhạy cảm, quy tắc chuẩn hóa và phạm vi duy nhất của dữ liệu trước khi chọn khóa.

### 3.3. Khóa chính ghép

Khóa chính ghép dùng nhiều cột để định danh một hàng. Ví dụ, một sản phẩm chỉ xuất hiện một lần trong mỗi đơn hàng:

~~~sql
CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
~~~

Cặp (order_id, product_id) phải duy nhất. order_id riêng lẻ có thể lặp lại vì một đơn hàng có nhiều sản phẩm; product_id riêng lẻ cũng có thể lặp lại vì một sản phẩm xuất hiện trong nhiều đơn hàng.

Khóa ghép phù hợp khi bản thân tổ hợp cột là định danh tự nhiên của hàng. Nếu các bảng khác cần tham chiếu đến hàng này, hãy cân nhắc độ phức tạp khi phải mang theo nhiều cột khóa. Một khóa thay thế đơn giản có thể giúp việc tham chiếu dễ hơn, nhưng vẫn cần UNIQUE(order_id, product_id) để giữ quy tắc nghiệp vụ.

### 3.4. Sinh giá trị khóa

ID có thể được tạo bởi ứng dụng, sequence, identity/auto-increment của database hoặc bộ sinh UUID. Cách khai báo cụ thể phụ thuộc hệ quản trị.

Ví dụ theo cú pháp PostgreSQL:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);
~~~

Trong Spring Data Relational, @Id đánh dấu thuộc tính định danh trong ánh xạ Java. Annotation này không tự tạo primary key trong database và cũng không thay thế cơ chế sinh ID của schema.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private Long id;

    private String fullName;
}
~~~

Hãy bảo đảm kiểu Java tương thích với kiểu cột và cơ chế sinh ID đã chọn. Với UUID, dùng kiểu Java và kiểu cột được driver/hệ quản trị hỗ trợ tương ứng.

## 4. Khóa ngoại (FOREIGN KEY)

### 4.1. Khái niệm và mục đích

Foreign key (khóa ngoại) là một ràng buộc yêu cầu giá trị ở một cột hoặc nhóm cột của bảng phải tham chiếu đến một khóa được phép trong bảng khác, thường là primary key hoặc một tập cột có ràng buộc unique.

Khóa ngoại bảo vệ **toàn vẹn tham chiếu (referential integrity)**. Nó ngăn dữ liệu tạo ra liên kết đến một hàng không tồn tại, đồng thời quy định cách xử lý khi hàng được tham chiếu bị xóa hoặc cập nhật.

Ví dụ, mỗi đơn hàng thuộc về một khách hàng:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);
~~~

orders.customer_id phải khớp với một customers.id đang tồn tại. Vì customer_id còn được khai báo NOT NULL, mọi đơn hàng đều phải có khách hàng. Nếu bỏ NOT NULL, database có thể cho phép đơn hàng chưa gắn khách hàng bằng cách lưu NULL; foreign key không cấm trường hợp đó.

### 4.2. Quy tắc khi xóa hoặc cập nhật hàng được tham chiếu

Khi khai báo foreign key, có thể chỉ định hành vi khi bản ghi cha bị xóa hoặc khóa được tham chiếu bị cập nhật:

| Hành vi | Ý nghĩa | Trường hợp cân nhắc |
|---|---|---|
| RESTRICT / NO ACTION | Không cho thao tác làm hỏng tham chiếu; chi tiết thời điểm kiểm tra phụ thuộc hệ quản trị và cấu hình constraint | Dữ liệu con cần được giữ lại hoặc xử lý rõ ràng |
| CASCADE | Xóa/cập nhật hàng con tương ứng theo thao tác trên hàng cha | Hàng con không có ý nghĩa độc lập ngoài hàng cha |
| SET NULL | Đặt cột khóa ngoại thành NULL | Quan hệ là tùy chọn và cột cho phép NULL |
| SET DEFAULT | Đặt cột về giá trị mặc định | Chỉ dùng khi giá trị mặc định vẫn thỏa mãn constraint và mô hình nghiệp vụ |

Ví dụ:

~~~sql
CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers(id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE
~~~

ON DELETE CASCADE có thể thuận tiện khi xóa một bản ghi cha thì toàn bộ hàng con phụ thuộc phải biến mất. Tuy nhiên, đặt cascade thiếu cân nhắc có thể xóa một lượng dữ liệu lớn ngoài dự kiến. Với dữ liệu đơn hàng, hóa đơn hoặc lịch sử giao dịch, thường cần giữ lịch sử và dùng quy trình nghiệp vụ riêng thay vì xóa dây chuyền.

Hãy chọn hành vi dựa trên vòng đời dữ liệu. Đừng dùng CASCADE chỉ vì nó làm câu lệnh xóa dễ viết hơn. Nếu một khách hàng không thể bị xóa khi còn đơn hàng, RESTRICT hoặc hành vi mặc định phù hợp hơn. Nếu khách hàng có thể bị xóa nhưng đơn hàng vẫn được giữ, có thể cần thiết kế lưu thông tin lịch sử hoặc trạng thái ẩn danh thay vì đặt customer_id thành NULL một cách máy móc.

### 4.3. Khóa ngoại ghép

Khóa ngoại cũng có thể gồm nhiều cột. Số lượng, thứ tự và kiểu dữ liệu của các cột tham chiếu phải tương thích với khóa được tham chiếu.

~~~sql
CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_item_order
        FOREIGN KEY (order_id) REFERENCES orders(id),
    CONSTRAINT fk_item_product
        FOREIGN KEY (product_id) REFERENCES products(id)
);
~~~

Trong ví dụ này, mỗi dòng chi tiết phải thuộc một đơn hàng và một sản phẩm có thật. Nếu bảng đích dùng khóa ghép, phần REFERENCES phải nêu đầy đủ các cột khóa tương ứng.

### 4.4. Khóa ngoại không tự động có nghĩa là quan hệ đối tượng hai chiều

Trong mô hình quan hệ, foreign key là quy tắc ở database. Trong code Java, việc bạn có trường customerId, có đối tượng Customer, hay có collection các Order là quyết định về mô hình ứng dụng và cách ánh xạ.

Spring Data Relational R2DBC không hoạt động như JPA với cơ chế tự động tải quan hệ lazy/eager qua các proxy. Mô hình của Spring Data Relational tập trung vào aggregate: thường tải và lưu một aggregate root cùng các thành phần thuộc aggregate đó. Một foreign key trong SQL không tự động khiến Spring Data R2DBC dựng toàn bộ object graph.

Ví dụ, có thể ánh xạ cột customer_id thành một trường ID đơn giản:

~~~java
@Table("orders")
public class Order {
    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;
}
~~~

Trường customerId chỉ chứa giá trị khóa ngoại. Khi cần thông tin khách hàng, ứng dụng có thể truy vấn Customer riêng hoặc dùng một truy vấn join phù hợp. Database vẫn kiểm tra foreign key khi ghi dữ liệu.

## 5. Các ràng buộc dữ liệu quan trọng khác

Primary key và foreign key giải quyết định danh và liên kết. Một schema thực tế thường cần thêm các constraint sau.

### 5.1. NOT NULL

NOT NULL yêu cầu cột phải có giá trị. Dùng cho các thuộc tính bắt buộc như tên sản phẩm, thời điểm tạo hoặc khóa ngoại của một quan hệ bắt buộc.

~~~sql
full_name VARCHAR(150) NOT NULL
~~~

Nếu cột vừa NOT NULL vừa có DEFAULT, khi câu lệnh insert bỏ qua cột thì database có thể điền giá trị mặc định. Nếu người ghi chủ động truyền NULL, hành vi vẫn bị NOT NULL từ chối.

### 5.2. UNIQUE

UNIQUE yêu cầu giá trị hoặc tổ hợp giá trị không bị trùng. Ví dụ, email đăng nhập có thể cần duy nhất:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

Có thể tạo unique constraint trên nhiều cột:

~~~sql
ALTER TABLE products
ADD CONSTRAINT uq_products_sku_per_store
UNIQUE (store_id, sku);
~~~

Khi đó, cùng một sku có thể xuất hiện ở các cửa hàng khác nhau, nhưng không được lặp trong cùng một cửa hàng.

Lưu ý: cách database xử lý nhiều giá trị NULL trong một unique constraint khác nhau giữa các hệ quản trị và đôi khi có thể tùy chọn cấu hình. Chẳng hạn, PostgreSQL mặc định cho phép nhiều hàng có NULL ở cột unique. Nếu email bắt buộc phải có và duy nhất, thường kết hợp NOT NULL với UNIQUE.

### 5.3. CHECK

CHECK giới hạn giá trị theo một biểu thức logic trên hàng đang được thêm hoặc cập nhật.

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    CONSTRAINT ck_products_price_nonnegative CHECK (price >= 0),
    CONSTRAINT ck_products_stock_nonnegative CHECK (stock_quantity >= 0)
);
~~~

Ví dụ khác:

~~~sql
ALTER TABLE employees
ADD CONSTRAINT ck_employees_valid_dates
CHECK (end_date IS NULL OR end_date >= start_date);
~~~

CHECK phù hợp với quy tắc có thể đánh giá từ dữ liệu của cùng một hàng. Không nên dựa vào CHECK thông thường để kiểm tra tổng số lượng ở nhiều hàng hoặc trạng thái ở bảng khác; quy tắc liên hàng/bảng cần thiết kế khác, chẳng hạn transaction, trigger hoặc cơ chế chuyên biệt của hệ quản trị.

Một điểm dễ nhầm: trong logic SQL, biểu thức CHECK có kết quả UNKNOWN do NULL thường không làm hàng bị từ chối. Vì thế, CHECK (price >= 0) không thay thế NOT NULL nếu giá bắt buộc phải có.

### 5.4. DEFAULT

DEFAULT cung cấp giá trị khi câu lệnh insert không chỉ định cột đó:

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

DEFAULT không tự ép mọi giá trị được ghi phải bằng giá trị mặc định. Nếu ứng dụng truyền một giá trị khác, giá trị đó được dùng miễn là không vi phạm các constraint còn lại. DEFAULT cũng không giống NOT NULL: muốn bắt buộc cột có giá trị, hãy khai báo cả hai khi cần.

### 5.5. Tóm tắt các constraint

| Constraint | Bảo vệ điều gì? | Câu hỏi cần đặt ra? |
|---|---|---|
| PRIMARY KEY | Định danh duy nhất và không rỗng | Một hàng được nhận diện bằng khóa nào? |
| FOREIGN KEY | Liên kết đến hàng hợp lệ | Bản ghi liên quan có thực sự tồn tại không? |
| NOT NULL | Giá trị bắt buộc phải có | Thuộc tính này có được phép thiếu không? |
| UNIQUE | Không cho phép trùng | Giá trị hoặc tổ hợp nào phải duy nhất? |
| CHECK | Giới hạn miền giá trị theo biểu thức | Điều kiện nào phải đúng trên mỗi hàng? |
| DEFAULT | Giá trị dùng khi insert bỏ qua cột | Giá trị khởi tạo hợp lý là gì? |

Các constraint có thể phối hợp. Ví dụ email VARCHAR(255) NOT NULL UNIQUE vừa yêu cầu email phải có, vừa ngăn trùng email.

## 6. Index và mối liên hệ với khóa

Index (chỉ mục) là cấu trúc giúp database tìm kiếm hoặc kết hợp dữ liệu hiệu quả hơn. Primary key và unique constraint thường được hệ quản trị hỗ trợ bằng unique index hoặc cấu trúc tương đương. Foreign key có mục đích toàn vẹn dữ liệu; nó không đồng nghĩa với việc mọi database tự tạo index trên cột tham chiếu.

Ví dụ, truy vấn thường xuyên tìm đơn hàng theo khách hàng:

~~~sql
SELECT id, created_at
FROM orders
WHERE customer_id = 101;
~~~

Một index trên orders.customer_id có thể giúp truy vấn này nhanh hơn khi bảng lớn:

~~~sql
CREATE INDEX ix_orders_customer_id ON orders(customer_id);
~~~

Index trên cột foreign key cũng có thể giúp database xử lý join, đồng thời kiểm tra hoặc xóa hàng cha thuận lợi hơn. Tuy vậy, index làm tăng dung lượng lưu trữ và chi phí ghi/cập nhật, vì vậy cần dựa vào truy vấn thực tế và execution plan để quyết định.

Hãy phân biệt:

- **Constraint** xác định dữ liệu nào được phép tồn tại.
- **Index** hỗ trợ cách database tìm và sắp xếp dữ liệu.
- **Unique index** vừa có tác dụng tăng tốc tra cứu, vừa bảo đảm tính duy nhất theo quy tắc của database.

Không tạo index trùng lặp với index mà primary key hoặc unique constraint đã tạo. Cũng không nên tạo index cho mọi cột theo thói quen.

## 7. Ví dụ schema hoàn chỉnh cho khách hàng, đơn hàng và sản phẩm

Ví dụ sau dùng cú pháp PostgreSQL để minh họa. Tên kiểu identity và một số chi tiết cú pháp có thể khác ở MySQL, SQL Server, Oracle hoặc H2; hãy điều chỉnh theo hệ quản trị mà dự án đang dùng.

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_customers PRIMARY KEY (id),
    CONSTRAINT uq_customers_email UNIQUE (email)
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    sku VARCHAR(60) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT pk_products PRIMARY KEY (id),
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT ck_products_price CHECK (price >= 0),
    CONSTRAINT ck_products_stock CHECK (stock_quantity >= 0)
);

CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_orders PRIMARY KEY (id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
        ON DELETE RESTRICT
);

CREATE TABLE order_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT pk_order_items PRIMARY KEY (id),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_order_items_order_product UNIQUE (order_id, product_id),
    CONSTRAINT ck_order_items_quantity CHECK (quantity > 0),
    CONSTRAINT ck_order_items_unit_price CHECK (unit_price >= 0)
);

CREATE INDEX ix_orders_customer_id ON orders(customer_id);
CREATE INDEX ix_order_items_product_id ON order_items(product_id);
~~~

Các quy tắc thể hiện trong schema:

- customers.id, products.id, orders.id và order_items.id là khóa chính.
- Mỗi email khách hàng và SKU sản phẩm là duy nhất.
- Một đơn hàng phải tham chiếu đến khách hàng có thật.
- Một dòng chi tiết phải tham chiếu đến đơn hàng và sản phẩm có thật.
- Một sản phẩm chỉ xuất hiện tối đa một lần trong một đơn hàng; nếu cần thêm số lượng thì cập nhật quantity của dòng đó.
- Số lượng phải lớn hơn 0, giá và đơn giá không được âm.
- Xóa đơn hàng sẽ xóa các dòng chi tiết thuộc đơn hàng; xóa sản phẩm đang được tham chiếu bị từ chối.

Trong ví dụ, unit_price được lưu tại dòng chi tiết để ghi nhận giá tại thời điểm mua. Nếu chỉ join đến giá hiện tại trong products, lịch sử đơn hàng có thể thay đổi khi giá sản phẩm được cập nhật. Đây là quyết định mô hình dữ liệu theo nghiệp vụ, không chỉ là quyết định về kiểu cột.

## 8. Sử dụng schema SQL cùng Spring Data Relational R2DBC

### 8.1. Annotation ánh xạ không thay thế constraint

Một entity đơn giản có thể được ánh xạ như sau:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    private String email;
}
~~~

Các annotation chính:

- @Table("customers") chỉ định bảng được ánh xạ.
- @Id đánh dấu thuộc tính ID của entity.
- @Column("full_name") chỉ định tên cột khi tên thuộc tính Java khác tên cột.

Những annotation này không có nghĩa database đã có PRIMARY KEY, NOT NULL hay UNIQUE. Schema phải được tạo và quản lý riêng. Nếu email cần duy nhất, hãy có unique constraint trong database, kể cả khi ứng dụng đã kiểm tra trước khi lưu.

### 8.2. Repository reactive không bỏ qua quy tắc của database

Repository có thể khai báo như sau:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

Các thao tác lưu qua repository cuối cùng vẫn gửi lệnh đến database. Nếu lệnh insert/update vi phạm primary key, foreign key, unique, not-null hoặc check constraint, database sẽ từ chối thao tác. Trong luồng reactive, lỗi xuất hiện như một tín hiệu lỗi của publisher; nó có thể được xử lý bằng các toán tử như onErrorMap hoặc onErrorResume ở đúng ranh giới ứng dụng.

Ví dụ minh họa cách xử lý lỗi ở tầng dịch vụ:

~~~java
public Mono<Customer> createCustomer(Customer customer) {
    return customerRepository.save(customer)
            .onErrorMap(this::translatePersistenceError);
}
~~~

translatePersistenceError là logic do ứng dụng định nghĩa để chuyển lỗi lưu trữ thành lỗi nghiệp vụ/API phù hợp. Không nên trả nguyên thông báo SQL hoặc thông tin nội bộ của database cho client. Cũng không nên coi việc bắt lỗi là thay thế cho constraint; constraint mới là nơi bảo vệ dữ liệu trước mọi luồng ghi.

### 8.3. Mô hình aggregate và collection con

Spring Data Relational tổ chức việc lưu dữ liệu quanh aggregate root. Một aggregate root có thể chứa các đối tượng con được ánh xạ bằng @MappedCollection. Ví dụ khái niệm:

~~~java
@Table("orders")
public class Order {
    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderItem> items = new HashSet<>();
}
~~~

Trong ví dụ, order_items.order_id là cột liên kết các dòng con với aggregate root orders. Foreign key trong schema vẫn cần được khai báo để bảo đảm mỗi order_id tham chiếu đến một đơn hàng có thật. @MappedCollection mô tả cách Spring Data Relational ánh xạ collection; nó không thay thế foreign key SQL.

Không nên xem @MappedCollection như @OneToMany/@ManyToOne của JPA. Spring Data Relational không cung cấp cơ chế quan hệ đối tượng đầy đủ với lazy-loading proxy. Hãy thiết kế ranh giới aggregate dựa trên tính nhất quán nghiệp vụ, rồi quyết định truy vấn dữ liệu liên quan bằng repository, R2dbcEntityTemplate hoặc DatabaseClient.

### 8.4. Tạo và thay đổi schema bằng migration

Schema cần được quản lý có phiên bản. Thông thường, dự án lưu các tập lệnh migration trong source control, ví dụ:

~~~text
src/main/resources/db/migration/
    V1__create_customers.sql
    V2__create_orders.sql
    V3__add_customer_email_unique.sql
~~~

Mỗi migration ghi nhận một thay đổi có chủ đích: tạo bảng, thêm cột, thêm constraint hoặc tạo index. Khi triển khai, công cụ migration áp dụng các thay đổi theo thứ tự và ghi nhận phiên bản đã chạy. Chọn công cụ và cách cấu hình phù hợp với hệ quản trị, môi trường và driver của dự án; một số công cụ migration truyền thống sử dụng JDBC ngay cả khi ứng dụng chính truy cập dữ liệu qua R2DBC.

Không nên dựa vào việc ứng dụng tự suy đoán hoặc tự tạo schema trong môi trường production. Migration giúp thay đổi cấu trúc có thể xem xét, lặp lại và triển khai nhất quán giữa các môi trường.

## 9. Kiểm tra dữ liệu ở Java và ở database

Kiểm tra ở Java và constraint SQL phục vụ hai mục đích liên quan nhưng khác nhau.

**Validation ở tầng ứng dụng** giúp phản hồi sớm và thân thiện. Ví dụ, Bean Validation có thể kiểm tra trường bắt buộc, định dạng email hoặc số lượng dương trước khi gọi repository:

~~~java
public record CreateProductRequest(
        @NotBlank String name,
        @PositiveOrZero BigDecimal price,
        @PositiveOrZero Integer stockQuantity
) {}
~~~

**Constraint ở database** là hàng rào cuối cùng bảo vệ dữ liệu. Nó áp dụng với mọi lệnh ghi: từ API, tác vụ nền, script quản trị, ứng dụng khác hoặc truy vấn SQL trực tiếp.

Nếu chỉ kiểm tra trước khi ghi, hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra rồi cùng cố lưu một email. Unique constraint sẽ giải quyết cuộc đua đó: chỉ một thao tác có thể thành công. Vì vậy, với quy tắc duy nhất, ứng dụng nên kiểm tra trước để đưa ra thông báo dễ hiểu, nhưng vẫn phải bắt và xử lý trường hợp database từ chối do trùng.

Một số quy tắc thực hành:

- Dùng validation Java để kiểm tra dữ liệu đầu vào và tạo thông báo thân thiện.
- Dùng NOT NULL, UNIQUE, FOREIGN KEY và CHECK cho các bất biến dữ liệu mà database có thể bảo vệ.
- Dùng transaction khi nhiều thao tác phải thành công hoặc thất bại cùng nhau.
- Xử lý lỗi constraint tại ranh giới phù hợp; phân biệt lỗi dữ liệu người dùng với lỗi hệ thống.
- Không dựa vào một truy vấn SELECT kiểm tra trước để bảo đảm duy nhất hoặc tồn tại trong lúc có ghi đồng thời.

## 10. Transaction và các thao tác đồng thời

Constraint thường được kiểm tra khi database thực hiện câu lệnh ghi hoặc tại thời điểm kiểm tra được cấu hình. Khi một lệnh vi phạm constraint, database từ chối lệnh đó. Nếu thao tác nằm trong transaction, ứng dụng cần xử lý trạng thái transaction theo quy tắc của driver và hệ quản trị; thường phải rollback transaction khi có lỗi khiến transaction không thể tiếp tục.

Ví dụ, tạo đơn hàng có thể gồm các bước: ghi hàng orders, ghi các hàng order_items, rồi cập nhật tồn kho. Nếu chỉ một phần thành công, dữ liệu có thể mất nhất quán. Hãy đặt các bước cần tính nguyên tử trong cùng transaction reactive được cấu hình đúng cho R2DBC.

R2DBC là API reactive cho truy cập quan hệ, nên không dùng transaction imperative kiểu JDBC theo cách tùy tiện. Trong Spring, có thể dùng TransactionalOperator hoặc cấu hình transaction manager R2DBC phù hợp để bao bọc publisher. Đảm bảo mọi thao tác trong luồng transaction dùng cùng kết nối/transaction context do framework quản lý.

Constraint cũng không tự giải quyết mọi quy tắc cạnh tranh. Ví dụ, hai giao dịch cùng đọc tồn kho là 1 rồi cùng đặt mua 1 sản phẩm có thể dẫn đến vấn đề nếu chỉ đọc rồi ghi mà không có cơ chế đồng bộ. Có thể cần câu lệnh cập nhật có điều kiện, khóa phù hợp hoặc optimistic locking. Hãy để database thực hiện phép kiểm tra và cập nhật một cách nguyên tử khi có thể, ví dụ:

~~~sql
UPDATE products
SET stock_quantity = stock_quantity - 1
WHERE id = 10
  AND stock_quantity >= 1;
~~~

Ứng dụng kiểm tra số hàng được cập nhật: nếu bằng 0 thì sản phẩm không tồn tại hoặc không còn đủ hàng. Quy tắc cụ thể cần được thiết kế rõ để phân biệt hai trường hợp nếu nghiệp vụ yêu cầu.

## 11. Những lỗi thiết kế thường gặp

### Chỉ khai báo @Id mà quên primary key trong database

@Id giúp Spring Data nhận diện trường định danh. Nếu schema không có primary key hoặc unique constraint phù hợp, database không được bảo vệ theo ý nghĩa mà code đang giả định. Hãy kiểm tra DDL thực tế.

### Chỉ kiểm tra trùng bằng SELECT rồi mới INSERT

Hai request đồng thời có thể cùng thấy email chưa tồn tại. Dùng UNIQUE để database quyết định duy nhất một cách an toàn; ứng dụng có thể kiểm tra trước để cải thiện thông báo.

### Lưu ID tham chiếu nhưng không có foreign key

Một cột customer_id dạng BIGINT chỉ là con số nếu không có foreign key. Dữ liệu có thể trỏ đến khách hàng đã bị xóa hoặc chưa từng tồn tại. Khai báo foreign key nếu quan hệ cần được bảo vệ ở database.

### Dùng ON DELETE CASCADE cho mọi quan hệ

Cascade có thể xóa lịch sử hoặc dữ liệu cần lưu trữ. Xem xét vòng đời và yêu cầu kiểm toán trước khi chọn hành vi xóa.

### Cho phép NULL ngoài ý muốn

NULL có ngữ nghĩa riêng trong SQL và có thể làm điều kiện, unique constraint hoặc check constraint hoạt động khác kỳ vọng. Khai báo NOT NULL cho thuộc tính bắt buộc và kiểm tra các trường hợp NULL trong thiết kế.

### Cho rằng annotation Java tự sinh mọi constraint

Annotation ánh xạ không tự động là DDL. Dùng migration để tạo primary key, foreign key, unique, check và index; kiểm tra schema thật ở từng môi trường.

### Không đặt tên constraint

Nếu không đặt tên, database có thể tự sinh tên khó đọc. Tên rõ ràng như fk_orders_customer hoặc uq_customers_email giúp đọc migration, log và chẩn đoán lỗi dễ hơn. Quy tắc đặt tên cần nhất quán trong dự án.

## 12. Quy trình thiết kế constraint cho một bảng mới

Khi thêm một bảng, có thể đi theo trình tự sau:

1. Xác định một hàng đại diện cho thực thể hoặc sự kiện nào.
2. Chọn kiểu dữ liệu và giới hạn độ dài/độ chính xác cho từng cột.
3. Chọn primary key; cân nhắc khóa tự nhiên, khóa thay thế hoặc khóa ghép.
4. Đánh dấu NOT NULL cho mọi thuộc tính bắt buộc.
5. Xác định các giá trị phải duy nhất và thêm UNIQUE.
6. Xác định quan hệ đến bảng khác và thêm FOREIGN KEY.
7. Xác định miền giá trị và thêm CHECK khi biểu thức có thể được kiểm tra ở cấp hàng.
8. Chọn DEFAULT khi database có giá trị mặc định hợp lý.
9. Xem xét hành vi ON DELETE/ON UPDATE theo vòng đời dữ liệu.
10. Xem các truy vấn thường dùng để quyết định index; tránh tạo chỉ mục trùng lặp.
11. Viết migration, áp dụng trên môi trường phát triển và thử các trường hợp hợp lệ lẫn không hợp lệ.
12. Ánh xạ entity/repository trong Spring Data Relational R2DBC sao cho kiểu Java và tên cột khớp với schema.

## 13. Bài tập tự kiểm tra

### Bài 1: Xác định khóa

Một bảng students có các cột id, student_code, full_name, email. student_code không thay đổi trong suốt vòng đời sinh viên; email có thể thay đổi. Hãy đề xuất primary key và các unique constraint.

Gợi ý: Có thể chọn id làm khóa thay thế và đặt UNIQUE(student_code). Nếu email phải duy nhất trong hệ thống, thêm UNIQUE(email) và NOT NULL nếu email bắt buộc.

### Bài 2: Bảo vệ quan hệ

Bảng payments có order_id. Hãy viết constraint để mọi khoản thanh toán thuộc về một đơn hàng có thật. Xác định điều gì xảy ra khi xóa đơn hàng.

Gợi ý: Dùng order_id NOT NULL và foreign key tham chiếu orders(id). Chọn RESTRICT nếu không được xóa đơn hàng còn thanh toán; nếu dữ liệu thanh toán phải được lưu như lịch sử, thường cần chính sách lưu trữ phù hợp thay vì cascade.

### Bài 3: Giới hạn miền giá trị

Bảng discounts có percentage trong khoảng từ 0 đến 100. Hãy viết kiểu dữ liệu và constraint phù hợp.

Gợi ý:

~~~sql
percentage DECIMAL(5, 2) NOT NULL,
CONSTRAINT ck_discounts_percentage
    CHECK (percentage >= 0 AND percentage <= 100)
~~~

### Bài 4: Phân biệt validation và constraint

API kiểm tra email bằng Bean Validation trước khi gọi save. Vì sao bảng vẫn cần unique constraint?

Gợi ý: Validation cải thiện trải nghiệm và phản hồi sớm, nhưng không loại trừ ghi đồng thời hoặc luồng ghi khác. Unique constraint bảo vệ tính duy nhất ở nơi dữ liệu được lưu.

### Bài 5: Đọc lỗi từ database

Ứng dụng lưu một Order với customerId không tồn tại. Nếu orders.customer_id có foreign key, điều gì xảy ra?

Gợi ý: Database từ chối lệnh ghi vì vi phạm toàn vẹn tham chiếu. Trong reactive pipeline, lỗi đi theo tín hiệu lỗi; tầng ứng dụng cần chuyển lỗi lưu trữ thành phản hồi phù hợp.

## 14. Ghi nhớ khi làm việc với Spring Data Relational R2DBC

- SQL và schema là nền tảng của dữ liệu quan hệ; R2DBC chỉ thay đổi cách ứng dụng giao tiếp với database.
- Primary key định danh hàng; foreign key bảo vệ liên kết giữa các bảng.
- NOT NULL, UNIQUE, CHECK và DEFAULT mô tả các quy tắc dữ liệu khác nhau, có thể phối hợp với nhau.
- Constraint phải được tạo trong database bằng DDL/migration. @Id, @Table, @Column và @MappedCollection phục vụ ánh xạ đối tượng, không thay thế constraint.
- Validation ở Java giúp báo lỗi thân thiện; constraint ở database bảo vệ dữ liệu trước mọi luồng ghi và các tình huống đồng thời.
- Chọn hành vi xóa/cập nhật khóa ngoại theo vòng đời dữ liệu; cân nhắc index theo truy vấn thực tế.
- Với R2DBC, xử lý lỗi và transaction trong reactive pipeline, đồng thời giữ quy tắc toàn vẹn quan trọng ở database.

Khi đọc hoặc thiết kế một entity trong Spring Data Relational R2DBC, hãy luôn đối chiếu ba phần: cấu trúc SQL thực tế, quy tắc nghiệp vụ của dữ liệu và cách entity/repository ánh xạ sang cấu trúc đó. Ba phần này cần nhất quán thì ứng dụng mới lưu trữ dữ liệu đáng tin cậy.

