# Quy định hành vi cập nhật, xóa và tính toàn vẹn dữ liệu

Một lược đồ quan hệ không chỉ trả lời “có những bảng nào, nối với nhau bằng khóa gì?” mà còn phải trả lời **điều gì được phép xảy ra khi dữ liệu thay đổi**. Khi một khách hàng bị xóa, đơn hàng cũ có bị xóa theo không? Khi đổi mã phòng ban, các nhân viên thuộc phòng đó có cần được cập nhật không? Khi hủy một đơn hàng, có được xóa các dòng hàng đã dùng để lập hóa đơn không? Nếu hai người cùng sửa một số dư, làm sao bảo đảm dữ liệu không bị âm?

Các câu hỏi này liên quan trực tiếp đến **hành vi cập nhật và xóa (update/delete behavior)**, **toàn vẹn tham chiếu (referential integrity)**, **toàn vẹn miền giá trị**, **toàn vẹn thực thể** và **bất biến nghiệp vụ**. Chúng phải được quy định từ lúc mô hình hóa, không đợi đến khi viết API mới quyết định.

Trong chương **Mô hình quan hệ** của module **DATABASE_DATA_MODELING**, mục tiêu là chuyển yêu cầu nghiệp vụ thành các bảng, khóa, chỉ mục và quy tắc kiểm chứng có thể thực thi; hiểu giới hạn của từng cơ chế và lựa chọn mô hình phù hợp với lịch sử, hiệu năng, tính đồng thời cũng như khả năng phát triển của hệ thống.

## 1. Các loại toàn vẹn cần phân biệt

Giả sử một hệ thống bán hàng có **Customer**, **Order**, **OrderLine** và **Product**:

~~~text
Customer 1 ─── N Order 1 ─── N OrderLine N ─── 1 Product
                   |
                   └── trạng thái DRAFT / CONFIRMED / CANCELLED
~~~

Để mô hình này đúng, phải bảo vệ nhiều lớp quy tắc khác nhau:

| Lớp toàn vẹn | Câu hỏi | Cơ chế quan hệ thường dùng |
| --- | --- | --- |
| **Thực thể** | Mỗi bản ghi có định danh duy nhất, không nhập nhằng? | PRIMARY KEY, UNIQUE, NOT NULL |
| **Miền giá trị** | Số lượng có dương, trạng thái có nằm trong tập hợp hợp lệ? | Kiểu dữ liệu, NOT NULL, CHECK, domain |
| **Tham chiếu** | Order có trỏ tới Customer tồn tại? OrderLine có trỏ tới Order/Product tồn tại? | FOREIGN KEY và hành vi ON DELETE/ON UPDATE |
| **Bội số/quan hệ** | Một Order phải có ít nhất một dòng khi xác nhận? Một khách hàng có tối đa một email chính? | UNIQUE/partial unique index; kiểm tra xuyên hàng khi cần |
| **Nghiệp vụ** | Không sửa số tiền của đơn đã đối soát? Không bán khi hết tồn kho? | Giao dịch, ràng buộc, trigger/procedure, quy trình ghi |
| **Thời gian/lịch sử** | Có giữ được địa chỉ giao hàng và giá tại thời điểm mua? | Snapshot, bảng phiên bản, ngày hiệu lực, quy tắc bất biến |
| **Đồng thời** | Hai giao dịch có thể cùng làm một trạng thái hợp lệ trở thành sai? | Khóa, isolation, thao tác nguyên tử, retry |

**Bất biến (invariant)** là một mệnh đề phải luôn đúng tại những thời điểm hệ thống quy định, ví dụ “mọi dòng hàng đã lưu phải trỏ tới đơn tồn tại” hoặc “số lượng tồn kho không âm”. Cần nói rõ **thời điểm kiểm tra**: cuối mỗi câu lệnh, cuối giao dịch, khi chuyển trạng thái nghiệp vụ hay tại một thời điểm lịch sử.

Một khóa ngoại chỉ bảo vệ **sự tồn tại của bản ghi được tham chiếu**. Nó không biết một khách hàng có còn hoạt động, một sản phẩm có còn được bán hay một đơn hàng đã được khóa sổ hay chưa.

## 2. Hành vi khi hàng cha được cập nhật hoặc xóa

Trong cơ sở dữ liệu quan hệ, **khóa ngoại** có thể quy định điều xảy ra với **hàng con** khi **khóa được tham chiếu của hàng cha thay đổi** hoặc **hàng cha bị xóa**. Hai hướng cần phân biệt:

- **ON DELETE:** điều gì xảy ra khi xóa bản ghi được tham chiếu?
- **ON UPDATE:** điều gì xảy ra khi cập nhật **giá trị khóa được tham chiếu**?

Cập nhật một thuộc tính bình thường của hàng cha như tên hoặc mô tả **không kích hoạt ON UPDATE** của FK nếu giá trị khóa được tham chiếu không đổi.

### 2.1. Bảng so sánh các hành động tham chiếu

| Hành động | Ý nghĩa | Khi nào cân nhắc | Cảnh báo |
| --- | --- | --- | --- |
| **NO ACTION** | Không tự xử lý hàng con; từ chối nếu FK không hợp lệ ở thời điểm kiểm tra | Cần bảo vệ tham chiếu, quản lý thay đổi có chủ đích | Trong PostgreSQL có thể trì hoãn kiểm tra nếu constraint là DEFERRABLE |
| **RESTRICT** | Ngăn xóa/đổi khóa cha nếu vẫn còn hàng con tham chiếu | Chứng từ lịch sử, dữ liệu không được xóa dây chuyền | PostgreSQL không trì hoãn được bản thân hành động RESTRICT |
| **CASCADE** | Xóa hàng con khi cha bị xóa; đổi giá trị FK con khi khóa cha được cập nhật | Thành phần thực sự phụ thuộc vòng đời hoặc khóa tự nhiên cần đổi đồng bộ | Có thể ảnh hưởng số lượng bản ghi lớn; phải xét các quan hệ dây chuyền |
| **SET NULL** | Gỡ quan hệ bằng cách đặt FK con thành NULL | Liên kết tùy chọn, hàng con vẫn có ý nghĩa độc lập | Cột FK phải cho NULL; mất tham chiếu nếu không có dữ liệu lịch sử |
| **SET DEFAULT** | Đặt FK con về giá trị DEFAULT khi cha bị xóa/đổi khóa | Có đối tượng mặc định hợp lệ theo chính sách | DEFAULT phải thỏa FK (hoặc NULL nếu hợp lệ), không tự biến thành ngoại lệ |

Trong PostgreSQL, **NO ACTION** là hành động mặc định nếu không ghi rõ. Nó thường kiểm tra ở cuối câu lệnh, hoặc cuối giao dịch khi FK được khai báo **DEFERRABLE** và thực sự chuyển sang chế độ trì hoãn. **RESTRICT** ngăn thao tác tham chiếu ngay và không cho trì hoãn chính thao tác hạn chế đó. Hai hành động có thể cho kết quả giống nhau trong nhiều thao tác thông thường, nhưng khác nhau trong giao dịch cần tạm thời làm thay đổi quan hệ rồi khôi phục trước khi kiểm tra cuối giao dịch.

**CASCADE không đồng nghĩa cập nhật mọi dữ liệu thuộc hàng con.** ON UPDATE CASCADE chỉ cập nhật **các cột FK tương ứng** với khóa cha thay đổi; không tự tính lại giá bán, quyền truy cập hoặc trạng thái nghiệp vụ.

### 2.2. Chọn hành động từ ngữ nghĩa vòng đời

Hãy phân loại từng quan hệ theo các câu hỏi:

1. Hàng con có thể **tồn tại độc lập** sau khi hàng cha biến mất không?
2. Hàng con có phải **chứng từ/lịch sử bắt buộc giữ** không?
3. Xóa bản ghi cha có mang ý nghĩa **xóa vật lý** hay chỉ là **ngừng hoạt động**?
4. Liên kết tới cha là **bắt buộc** hay có thể rỗng?
5. Khóa cha có thực sự **được phép đổi** không, hay định danh phải bất biến?
6. Có được chuyển quan hệ của hàng con sang cha khác, và ai được thực hiện?
7. Có luật pháp, nghĩa vụ hợp đồng hoặc chính sách lưu trữ nào chi phối việc xóa không?

Không có một quy tắc “mọi khóa ngoại nên CASCADE” hoặc “mọi bảng nên RESTRICT”. Lựa chọn chỉ đúng khi diễn tả chính xác vòng đời của từng cặp thực thể.

## 3. Ví dụ PostgreSQL: đơn hàng, dòng hàng và giỏ tạm

Giả sử doanh nghiệp quy định:

- Customer có thể đặt nhiều Order.
- Order đã được tạo phải giữ tham chiếu tới Customer hợp lệ trong dữ liệu nghiệp vụ.
- OrderLine thuộc Order và tham chiếu Product; các dòng của đơn đã xác nhận là chứng từ phải bảo toàn.
- Giá ở OrderLine là **giá đã chốt tại giao dịch**, không thay đổi theo giá Product hiện tại.
- Giỏ hàng tạm có thể xóa hoàn toàn cùng các dòng giỏ vì chưa tạo chứng từ.
- Product không được xóa vật lý nếu còn OrderLine tham chiếu; có thể **ngừng bán** thay vì xóa.

### 3.1. Lược đồ minh họa

~~~sql
-- PostgreSQL; dùng BY DEFAULT để ví dụ học tập có thể chỉ định ID.
CREATE TABLE customers (
    customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name   TEXT NOT NULL CHECK (btrim(full_name) <> ''),
    status      TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
);

CREATE TABLE products (
    product_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku        TEXT NOT NULL UNIQUE,
    title      TEXT NOT NULL,
    list_price NUMERIC(14, 2) NOT NULL CHECK (list_price >= 0),
    archived_at TIMESTAMPTZ
);

CREATE TABLE sales_orders (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT'
           CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    shipping_address_text TEXT NOT NULL,
    CONSTRAINT fk_order_customer FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_line_order FOREIGN KEY (order_id)
        REFERENCES sales_orders(order_id) ON DELETE RESTRICT,
    CONSTRAINT fk_line_product FOREIGN KEY (product_id)
        REFERENCES products(product_id) ON DELETE RESTRICT
);

CREATE TABLE shopping_carts (
    cart_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id) ON DELETE CASCADE
);

CREATE TABLE shopping_cart_items (
    cart_id BIGINT NOT NULL
        REFERENCES shopping_carts(cart_id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL
        REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (cart_id, product_id)
);
~~~

Trong ví dụ, **OrderLine** là thành phần của Order, nhưng không tự xóa theo Order. Do nghiệp vụ coi các dòng hàng là chứng từ, **RESTRICT** được chọn để chống xóa vật lý không chủ ý. Ngược lại, **shopping_cart_items** được xóa cùng giỏ tạm vì chúng chưa có trách nhiệm lưu trữ độc lập.

Bảng **sales_orders** lưu chuỗi địa chỉ giao nhận tại thời điểm đặt đơn. Đây là ví dụ đơn giản về **snapshot giao dịch**: khi Customer sửa địa chỉ hiện tại, địa chỉ giao nhận của đơn cũ không bị thay đổi theo. Hệ thống thật có thể cần cấu trúc địa chỉ nhiều trường, phiên bản và thông tin kiểm toán chi tiết hơn.

### 3.2. Dữ liệu và thử hành vi xóa

~~~sql
INSERT INTO customers(customer_id, full_name)
VALUES (101, 'Nguyễn Thị Lan');

INSERT INTO products(product_id, sku, title, list_price)
VALUES (501, 'BOOK-001', 'Sách thiết kế dữ liệu', 180000);

INSERT INTO sales_orders(order_id, customer_id, status, shipping_address_text)
VALUES (1001, 101, 'CONFIRMED', '12 Nguyễn Huệ, TP.HCM');

INSERT INTO order_lines(order_id, line_no, product_id, quantity, unit_price)
VALUES (1001, 1, 501, 2, 175000);

INSERT INTO shopping_carts(cart_id, customer_id)
VALUES (701, 101);

INSERT INTO shopping_cart_items(cart_id, product_id, quantity)
VALUES (701, 501, 1);
~~~

Khi xóa giỏ tạm:

~~~sql
DELETE FROM shopping_carts WHERE cart_id = 701;
-- shopping_cart_items của giỏ 701 bị xóa nhờ ON DELETE CASCADE.
~~~

Khi xóa Customer 101, cơ sở dữ liệu sẽ từ chối bởi Order 1001 vẫn tham chiếu Customer:

~~~sql
DELETE FROM customers WHERE customer_id = 101;
-- Bị từ chối: fk_order_customer với ON DELETE RESTRICT.
~~~

Lệnh DELETE thất bại **không** tự cho phép xóa Customer chỉ vì có các giỏ tạm được cấu hình CASCADE. Khi một cha có nhiều quan hệ phụ thuộc, thao tác phải thỏa **toàn bộ** ràng buộc; một FK RESTRICT có thể chặn việc xóa cho dù FK khác có CASCADE.

Tương tự:

~~~sql
DELETE FROM products WHERE product_id = 501;
-- Bị từ chối vì order_lines còn tham chiếu Product 501.
~~~

Thay vì xóa sản phẩm đã tham gia giao dịch, có thể **ngừng bán**:

~~~sql
UPDATE products
SET archived_at = CURRENT_TIMESTAMP
WHERE product_id = 501
  AND archived_at IS NULL;
~~~

Việc đánh dấu ngừng bán không làm mất lịch sử liên kết từ OrderLine sang Product. Nhưng **khóa ngoại không tự chặn** tạo OrderLine mới trỏ tới Product đã archive: nếu nghiệp vụ yêu cầu chỉ bán sản phẩm đang hoạt động, cần kiểm tra riêng tại thời điểm tạo/duyệt đơn.

### 3.3. Vì sao không nên CASCADE lên chứng từ?

Nếu thay fk_line_order thành ON DELETE CASCADE, chỉ một lệnh xóa Order có thể làm mất toàn bộ OrderLine. Trong hệ thống có thanh toán, thuế, hoàn trả, kiểm toán và hỗ trợ khách hàng, xóa dây chuyền có thể phá hủy dữ liệu cần lưu.

Với chứng từ, các lựa chọn thường đáng xem xét là:

- **RESTRICT hoặc NO ACTION** để chặn xóa hàng đang được tham chiếu.
- **Trạng thái hủy** thay vì DELETE vật lý.
- **Bản ghi điều chỉnh/đảo ngược** thay vì sửa trực tiếp dữ liệu đã khóa sổ.
- **Lưu trữ/ẩn danh có kiểm soát** theo chính sách thời hạn lưu giữ.

Cần xác định rõ trạng thái **DRAFT** có thể xóa vật lý hay không. Nếu cùng một bảng Order chứa cả bản nháp và chứng từ, FK đơn thuần không phân biệt được “xóa bản nháp được phép, xóa đơn đã xác nhận bị cấm” theo trạng thái; thiết kế phải bổ sung quy tắc nghiệp vụ hoặc tách vòng đời phù hợp.

## 4. ON UPDATE CASCADE, SET NULL và SET DEFAULT

### 4.1. ON UPDATE CASCADE khi đổi khóa tham chiếu

Giả sử **department_code** là một mã nghiệp vụ được tham chiếu. Khi thay đổi mã từ ENG sang DEV, doanh nghiệp muốn các nhân viên đang thuộc phòng đó vẫn tham chiếu **đúng cùng phòng**:

~~~sql
CREATE TABLE departments (
    department_code TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL,
    department_code TEXT,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_code)
        REFERENCES departments(department_code)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);

INSERT INTO departments(department_code, name)
VALUES ('ENG', 'Engineering');

INSERT INTO employees(employee_id, full_name, department_code)
VALUES (8, 'Minh', 'ENG');

UPDATE departments
SET department_code = 'DEV'
WHERE department_code = 'ENG';

-- employees.department_code của Minh được cập nhật từ ENG thành DEV.
~~~

ON UPDATE CASCADE điều chỉnh **khóa ngoại** theo khóa cha. Nhân viên vẫn thuộc **cùng thực thể Department** nếu nghiệp vụ chỉ đổi mã định danh. Nếu thay mã đồng thời thay đổi bản chất phòng ban hoặc chia/sáp nhập phòng, đó không còn là một phép đổi khóa đơn giản; cần quy trình nghiệp vụ khác.

**Thiết kế có khóa thay thế (surrogate key) ổn định** thường giúp tránh việc phải cập nhật khóa tham chiếu. Một department_id bất biến và department_code UNIQUE nhưng thay đổi được thường là lựa chọn thích hợp khi mã nghiệp vụ dễ đổi. ON UPDATE CASCADE hữu ích, nhưng không phải lý do để cho phép thay đổi tùy ý mọi khóa chính.

### 4.2. ON DELETE SET NULL khi liên kết là tùy chọn

Trong ví dụ, **employees.department_code** cho phép NULL nên:

~~~sql
DELETE FROM departments
WHERE department_code = 'DEV';

-- Minh vẫn tồn tại; department_code trở thành NULL.
~~~

Cách này hợp lý **chỉ khi nhân viên có thể tạm thời không thuộc phòng ban nào**. Nếu mọi nhân viên đang hoạt động bắt buộc thuộc một phòng, SET NULL có thể phá vỡ quy tắc nghiệp vụ; phải chọn RESTRICT, chuyển nhân viên sang phòng khác trước khi xóa, hoặc tách trạng thái hợp lệ.

Nếu FK là **NOT NULL**, ON DELETE SET NULL thường không hoàn tất được vì vi phạm ràng buộc NOT NULL. Đừng chọn SET NULL nếu mô hình không cho phép “không còn cha”.

Trong PostgreSQL, có thể chỉ định **danh sách cột cần SET NULL** cho một số trường hợp FK ghép khi xóa; cách này cần thiết kế cẩn thận để giữ các cột tenant/định danh không bị làm rỗng. Không nên giả định mọi DBMS hỗ trợ cùng cú pháp.

### 4.3. ON DELETE SET DEFAULT

SET DEFAULT thay giá trị FK của hàng con bằng giá trị mặc định đã khai báo. Nếu DEFAULT trỏ tới một hàng cha không tồn tại, FK vẫn bị vi phạm.

Ví dụ minh họa chính sách có nhóm xử lý chưa phân loại:

~~~sql
CREATE TABLE support_queues (
    queue_id INTEGER PRIMARY KEY,
    queue_name TEXT NOT NULL
);

INSERT INTO support_queues(queue_id, queue_name)
VALUES (0, 'Chưa phân loại'), (10, 'Hỗ trợ kỹ thuật');

CREATE TABLE tickets (
    ticket_id BIGINT PRIMARY KEY,
    queue_id INTEGER NOT NULL DEFAULT 0
        REFERENCES support_queues(queue_id)
        ON DELETE SET DEFAULT
);

INSERT INTO tickets(ticket_id, queue_id) VALUES (9001, 10);

DELETE FROM support_queues WHERE queue_id = 10;
-- Ticket 9001 chuyển queue_id về 0, vì queue 0 đã tồn tại.
~~~

Đây là quy tắc **chuyển hàng con sang nhóm mặc định**, không phải tự hủy ticket. Nó chỉ nên áp dụng nếu “Chưa phân loại” thực sự là trạng thái nghiệp vụ hợp lệ. Dùng hàng giả chỉ để né lỗi FK có thể che khuất sai lệch dữ liệu.

Không thể xóa queue 0 một cách bình thường nếu vẫn có ticket trỏ tới 0 và hành động SET DEFAULT cũng định đặt FK về 0; bản thân hàng mặc định cần có chính sách bảo vệ.

## 5. NO ACTION, RESTRICT và ràng buộc trì hoãn

Một quy tắc không thể được đánh giá chỉ theo **trạng thái giữa chừng của một giao dịch**. Ví dụ hệ thống cần tạm thời thay thế một hàng cha nhưng giữ định danh cuối cùng giống ban đầu.

Trong PostgreSQL, một khóa ngoại có thể được khai báo:

~~~sql
CREATE TABLE parent_records (
    parent_id BIGINT PRIMARY KEY
);

CREATE TABLE child_records (
    child_id BIGINT PRIMARY KEY,
    parent_id BIGINT NOT NULL,
    CONSTRAINT fk_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES parent_records(parent_id)
        ON DELETE NO ACTION
        ON UPDATE NO ACTION
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Theo mặc định, ràng buộc được kiểm tra sau mỗi câu lệnh. Trong một giao dịch cụ thể có thể yêu cầu trì hoãn:

~~~sql
BEGIN;

SET CONSTRAINTS fk_child_parent DEFERRED;

-- Các thao tác được phép tạm thời làm đứt tham chiếu
-- nếu trước COMMIT mọi tham chiếu được khôi phục hợp lệ.

COMMIT;
-- FK được kiểm tra trước khi giao dịch kết thúc thành công.
~~~

Không phải mọi constraint đều có thể DEFERRED và không phải mọi hành động FK đều có ngữ nghĩa trì hoãn như nhau. **RESTRICT trong PostgreSQL không thể bị trì hoãn như NO ACTION**; không nên đổi chúng cho nhau mà chưa xét luồng cập nhật dữ liệu nhiều bước.

Ràng buộc trì hoãn không có nghĩa “cho phép dữ liệu sai được commit”. Nó cho phép một **trạng thái trung gian** có thể tạm sai bên trong giao dịch, nhưng **trạng thái cuối phải hợp lệ**. Cần giới hạn phạm vi dùng và kiểm tra thông báo lỗi khi COMMIT, vì lỗi có thể xuất hiện muộn hơn câu lệnh đã gây ra vấn đề.

## 6. Khóa, UNIQUE, CHECK và các góc khuất của NULL

Toàn vẹn tham chiếu chỉ là một phần của mô hình. Các quy tắc nội bộ của hàng và tập hàng cần các cơ chế khác.

### 6.1. NOT NULL và CHECK cần phối hợp

~~~sql
CREATE TABLE stock_balances (
    product_id BIGINT PRIMARY KEY
        REFERENCES products(product_id) ON DELETE RESTRICT,
    available_quantity INTEGER NOT NULL
        CHECK (available_quantity >= 0),
    reserved_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (reserved_quantity >= 0)
);
~~~

Trong SQL/PostgreSQL, một CHECK được coi là vi phạm nếu biểu thức là **FALSE**; kết quả **UNKNOWN** do NULL thường không bị từ chối. Vì vậy:

~~~sql
quantity INTEGER CHECK (quantity > 0)
~~~

không tự bắt buộc quantity khác NULL. Nếu số lượng phải có, cần:

~~~sql
quantity INTEGER NOT NULL CHECK (quantity > 0)
~~~

Một lỗi phổ biến là viết CHECK tưởng đã bảo đảm giá trị bắt buộc, nhưng lại quên NOT NULL.

### 6.2. UNIQUE phụ thuộc phạm vi

Ví dụ khách hàng có nhiều email nhưng **tối đa một email chính**:

~~~sql
CREATE TABLE customer_emails (
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (customer_id, email)
);

CREATE UNIQUE INDEX uq_customer_primary_email
ON customer_emails(customer_id)
WHERE is_primary;
~~~

Khóa ghép cấm lặp một email ở **cùng khách hàng** nhưng không cấm email đó được sử dụng bởi nhiều khách hàng. Partial unique index cấm có hai email chính của cùng khách hàng.

Tuy nhiên, nó chỉ đảm bảo **tối đa một** email chính; **không đảm bảo luôn có ít nhất một**. Quy tắc số lượng tối thiểu thường cần cơ chế kiểm tra xuyên nhiều hàng.

### 6.3. UNIQUE và NULL không luôn có nghĩa “chỉ được một NULL”

Trong PostgreSQL, ràng buộc UNIQUE thông thường cho phép nhiều NULL vì các giá trị NULL được xử lý là phân biệt theo ngữ nghĩa mặc định. Một số phiên bản PostgreSQL hỗ trợ cấu hình **NULLS NOT DISTINCT** để đối xử NULL như không phân biệt trong UNIQUE.

Không nên coi UNIQUE(email) với email nullable là bằng chứng mọi khách hàng đã khai báo email hợp lệ; những hàng NULL vẫn có thể xuất hiện. Luôn viết rõ quy tắc **bắt buộc/không bắt buộc** tách khỏi quy tắc duy nhất.

### 6.4. FK ghép và NULL

Đối với khóa ngoại gồm nhiều cột, cần xem xét **MATCH SIMPLE** (mặc định trong PostgreSQL) và **MATCH FULL**:

- Với **MATCH SIMPLE**, nếu **bất kỳ** thành phần FK nào NULL, hàng con có thể không cần thỏa điều kiện tham chiếu theo bộ cột đó.
- Với **MATCH FULL**, chỉ khi **tất cả** thành phần FK NULL mới được miễn kiểm tra; hỗn hợp NULL và không NULL là không hợp lệ. Nếu tất cả khác NULL, bộ giá trị phải tồn tại ở bảng cha.

Ví dụ mã nhân viên chỉ duy nhất trong một tenant:

~~~sql
CREATE TABLE tenant_employees (
    tenant_id BIGINT NOT NULL,
    employee_id BIGINT NOT NULL,
    full_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, employee_id)
);

CREATE TABLE optional_assignments (
    assignment_id BIGINT PRIMARY KEY,
    employee_tenant_id BIGINT,
    employee_id BIGINT,
    CONSTRAINT fk_assignment_employee
        FOREIGN KEY (employee_tenant_id, employee_id)
        REFERENCES tenant_employees(tenant_id, employee_id)
        MATCH FULL
);
~~~

Thiết kế này cho phép **cả hai cột NULL** khi chưa phân công, nhưng không cho phép chỉ có tenant_id mà thiếu employee_id hoặc ngược lại. Khi quan hệ được gán, cả hai cột phải tương ứng cùng một nhân viên tồn tại.

**MATCH FULL không thay cho quy tắc cùng tenant của đối tượng chủ.** Nếu Assignment cũng có tenant_id riêng, cần bảo đảm tenant của nhân viên được gán trùng tenant của Assignment bằng cấu trúc FK ghép thích hợp.

## 7. Quy tắc xuyên nhiều hàng hoặc nhiều bảng

Những câu sau thường **không thể** được kiểm soát bằng một CHECK cục bộ đơn giản:

- “Order trạng thái CONFIRMED phải có **ít nhất một** OrderLine.”
- “Customer đang ACTIVE phải có **một số điện thoại đã xác minh**.”
- “Không có hai đặt phòng cho **cùng phòng** với khoảng thời gian chồng lấp.”
- “Số dư tổng của các phân bổ phải bằng số tiền đã phê duyệt.”
- “Nhân viên được giao việc phải đang thuộc nhóm có quyền xử lý.”

### 7.1. Ít nhất một hàng con không được FK thường tự bảo vệ

Khóa ngoại **OrderLine → Order** đảm bảo dòng hàng có đơn hàng tồn tại, nhưng không đảm bảo **Order → tồn tại OrderLine**.

Truy vấn chẩn đoán:

~~~sql
SELECT o.order_id
FROM sales_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM order_lines AS l
      WHERE l.order_id = o.order_id
  );
~~~

Trong hệ thống thỏa quy tắc, truy vấn này phải không trả hàng nào. Nhưng đây là **truy vấn giám sát**, không phải ràng buộc tự động ngăn trạng thái xấu.

Các phương án bảo vệ:

1. **Thiết kế luồng chuyển trạng thái** từ DRAFT sang CONFIRMED trong giao dịch, sau khi xác nhận đã có dòng.
2. **Dùng trigger/constraint trigger phù hợp** để kiểm tra khi tạo/sửa/xóa dòng và khi chuyển trạng thái, cân nhắc kiểm tra cuối giao dịch.
3. **Thiết kế lại cấu trúc** nếu có cách biểu diễn điều kiện bắt buộc trên cùng hàng hoặc theo thực thể khác.
4. **Kiểm soát mọi writer và cập nhật đồng thời**, tránh một giao dịch xác nhận đơn đúng lúc giao dịch khác xóa dòng cuối cùng.

Nếu ứng dụng chỉ kiểm tra “đã có ít nhất một dòng” trước khi UPDATE status nhưng cho phép một API khác DELETE dòng cuối mà không phối hợp khóa, hai thao tác có thể cùng hoàn tất và tạo Order CONFIRMED không có dòng. Một thao tác SELECT thông thường không tự bảo vệ bất biến dưới cạnh tranh.

### 7.2. Tính nguyên tử khi chuyển trạng thái

Ví dụ một quy trình xác nhận đơn có thể bắt đầu bằng:

~~~sql
BEGIN;

-- Khóa Order, với điều kiện các thao tác sửa OrderLine
-- cũng tuân theo cơ chế khóa cùng Order này.
SELECT order_id, status
FROM sales_orders
WHERE order_id = 1001
FOR UPDATE;

-- Kiểm tra tồn tại ít nhất một dòng.
SELECT EXISTS (
    SELECT 1
    FROM order_lines
    WHERE order_id = 1001
) AS has_lines;

-- Ứng dụng/procedure phải dừng và ROLLBACK nếu has_lines = FALSE
-- hoặc trạng thái hiện hành không cho phép xác nhận.
UPDATE sales_orders
SET status = 'CONFIRMED'
WHERE order_id = 1001 AND status = 'DRAFT';

COMMIT;
~~~

Ví dụ trên là **phác thảo quy trình**, không phải bảo đảm toàn vẹn chỉ với các câu lệnh được hiển thị. Luồng gọi phải kiểm tra kết quả của SELECT EXISTS và UPDATE (đúng một hàng), đồng thời các thao tác thêm/xóa/sửa OrderLine phải khóa/kiểm tra trạng thái cùng quy ước. Muốn cưỡng chế hoàn toàn ở database, cần triển khai thủ tục/ràng buộc phù hợp và xử lý mọi đường ghi dữ liệu.

### 7.3. Khoảng thời gian không chồng lấp

Quy tắc “một phòng không được có hai booking có thời gian giao nhau” liên quan tới **nhiều hàng**, không phải một CHECK chỉ xét hàng hiện tại. PostgreSQL hỗ trợ **exclusion constraint** cho một số trường hợp; hoặc ứng dụng có thể phối hợp khóa và kiểm tra, nhưng không nên dựa vào “SELECT không có chồng lấp, rồi INSERT” một cách độc lập trong môi trường concurrent.

Định nghĩa khoảng thời gian phải rõ: khoảng **[start, end)** cho phép booking sau bắt đầu đúng lúc booking trước kết thúc; nếu hai đầu đều đóng, ranh giới có thể bị coi là trùng.

## 8. Giao dịch, cô lập và thao tác cập nhật đồng thời

### 8.1. Cập nhật nguyên tử thay vì đọc–sửa–ghi tách rời

Giả sử tồn kho còn 1. Hai người cùng mua 1 sản phẩm. Nếu mỗi request đều:

1. SELECT available_quantity;
2. thấy giá trị 1;
3. UPDATE available_quantity = 0;

thì cả hai có thể tưởng đã giữ hàng thành công, dù chỉ có một sản phẩm.

Một cách thực hiện an toàn hơn là dùng **UPDATE có điều kiện trên cùng hàng**:

~~~sql
UPDATE stock_balances
SET available_quantity = available_quantity - 1,
    reserved_quantity = reserved_quantity + 1
WHERE product_id = 501
  AND available_quantity >= 1
RETURNING available_quantity, reserved_quantity;
~~~

Nếu số lượng không đủ, UPDATE trả **0 hàng**. Giao dịch chỉ được coi là giữ hàng thành công khi có một hàng được cập nhật. PostgreSQL khóa hàng trong UPDATE và đánh giá điều kiện phù hợp với mức cô lập; thao tác trên **cùng một hàng** như trên tránh nhiều trường hợp đua tranh kiểu đọc–sửa–ghi.

Cách này vẫn phải được kết hợp với giao dịch tạo Order/Reservation và quy tắc xử lý rollback, idempotency, hủy đơn, hoàn tồn. Nó không tự giải quyết mọi bất biến xuyên nhiều sản phẩm hoặc kho.

### 8.2. Optimistic concurrency control

Khi nhiều người có thể sửa một bản ghi cấu hình, dùng **cột version** để tránh ghi đè cập nhật của người khác:

~~~sql
CREATE TABLE product_descriptions (
    product_id BIGINT PRIMARY KEY
        REFERENCES products(product_id) ON DELETE RESTRICT,
    description TEXT NOT NULL,
    version_no INTEGER NOT NULL DEFAULT 1
               CHECK (version_no > 0)
);

-- Client đã đọc version_no = 3:
UPDATE product_descriptions
SET description = 'Nội dung đã được chỉnh sửa',
    version_no = version_no + 1
WHERE product_id = 501
  AND version_no = 3
RETURNING version_no;
~~~

Nếu UPDATE trả 0 hàng, bản ghi có thể đã bị người khác sửa hoặc không tồn tại. Ứng dụng cần đọc lại, giải quyết xung đột hoặc yêu cầu người dùng xác nhận; không tự động ghi đè.

**Version** giúp phát hiện xung đột trên một hàng, nhưng không thay thế FK, CHECK hoặc các khóa cần thiết cho bất biến nhiều hàng.

### 8.3. SERIALIZABLE và retry

Với quy tắc xuyên nhiều hàng, mức cô lập **SERIALIZABLE** có thể giúp phát hiện các lịch giao dịch không tuần tự hóa được. Trong PostgreSQL, giao dịch có thể bị hủy với lỗi serialization, nên ứng dụng phải **thử lại toàn bộ giao dịch** từ đầu theo chiến lược có giới hạn.

Không nên tuyên bố “dùng transaction là hết race condition”: một giao dịch ở mức mặc định vẫn có thể gặp hiện tượng đọc–ghi cạnh tranh. Cần phối hợp **cấu trúc ràng buộc**, **mức cô lập**, **khóa thích hợp**, **thời điểm kiểm tra** và **retry**.

### 8.4. Deadlock và thứ tự khóa

Hai giao dịch sửa nhiều bảng theo hai thứ tự khác nhau có thể khóa chéo. Ví dụ T1 khóa Order rồi Stock, T2 khóa Stock rồi Order. Cơ sở dữ liệu có cơ chế phát hiện deadlock và hủy một giao dịch, nhưng hệ thống nên giảm nguy cơ bằng:

- Quy định **thứ tự khóa** nhất quán khi cập nhật các thực thể liên quan.
- Giữ giao dịch ngắn, tránh gọi dịch vụ bên ngoài trong lúc giữ khóa lâu.
- Dùng khóa ở **đúng phạm vi nghiệp vụ** thay vì khóa quá rộng.
- Xử lý lỗi deadlock/serialization và retry an toàn, có idempotency cho tác động ngoài DB.

## 9. Xóa vật lý, xóa mềm, lưu trữ và lịch sử

Một lệnh DELETE không phải lúc nào cũng là hành động đúng với ý nghĩa “người dùng không còn nhìn thấy bản ghi”.

| Hành động | Bản ghi vật lý | Quan hệ FK | Trường hợp điển hình |
| --- | --- | --- | --- |
| **Hard delete** | Bị xóa khỏi bảng | FK áp dụng các hành động đã khai báo | Dữ liệu tạm, dữ liệu hết hạn được phép xóa |
| **Soft delete** | Giữ lại với deleted_at/status | FK vẫn thấy hàng tồn tại | Tài khoản ngừng hoạt động, phục hồi khi cần |
| **Archive** | Giữ lại nhưng không dùng cho thao tác mới | FK thường vẫn hợp lệ | Product đã từng bán, hợp đồng hết hiệu lực |
| **Anonymize/pseudonymize** | Giữ bản ghi giao dịch nhưng xử lý dữ liệu định danh theo chính sách | Cần duy trì định danh tham chiếu nhất quán | Lưu chứng từ mà giảm dữ liệu cá nhân |
| **Version/history** | Lưu nhiều phiên bản hoặc sự kiện thay đổi | Có thể FK tới phiên bản hoặc snapshot | Audit, báo cáo theo thời điểm |

### 9.1. Soft delete không kích hoạt ON DELETE

Ví dụ:

~~~sql
ALTER TABLE products
ADD COLUMN deletion_requested_at TIMESTAMPTZ;

UPDATE products
SET deletion_requested_at = CURRENT_TIMESTAMP
WHERE product_id = 501;
~~~

Đây là UPDATE, không phải DELETE. Các FK ON DELETE CASCADE, SET NULL hoặc RESTRICT **không chạy** chỉ vì cột này được gán. Người truy vấn phải hiểu các bộ lọc đối tượng còn hiệu lực và không cho tạo tham chiếu mới tới sản phẩm đã bị loại khỏi danh mục.

Để tên sản phẩm có thể được sử dụng lại sau khi soft delete, có thể thiết kế **partial unique index** trên bản ghi đang hoạt động. Nhưng cần xác định chính sách trùng tên/sku, khả năng khôi phục và tương thích với khóa ngoại.

**Lưu ý PostgreSQL:** một partial unique index không phải lúc nào cũng dùng được làm mục tiêu khóa ngoại; FK thông thường cần tham chiếu khóa chính hoặc UNIQUE thích hợp, không chỉ một tập con hàng theo điều kiện. Không thể coi “chỉ Product ACTIVE mới có thể được FK tham chiếu” là điều FK thường tự kiểm tra.

### 9.2. Quy tắc xóa không đồng nghĩa quyền truy cập

Nếu Customer đóng tài khoản, có thể cần:

1. Ngừng cho phép đặt đơn mới.
2. Thu hồi phiên đăng nhập và quyền thao tác.
3. Giữ Order đã phát sinh theo chính sách.
4. Xử lý dữ liệu liên hệ và định danh theo quy định áp dụng.
5. Ghi nhận ai yêu cầu, ai phê duyệt và khi nào tác vụ hoàn tất.

Đây là **quy trình nghiệp vụ nhiều bước**, không nên được thay bằng một ON DELETE CASCADE từ Customer xuống toàn bộ dữ liệu. Ngược lại, không nên giữ vô thời hạn mọi dữ liệu cá nhân chỉ vì đặt ON DELETE RESTRICT; thiết kế phải đồng thời đáp ứng chính sách bảo mật và thời hạn lưu trữ hợp lệ.

### 9.3. Địa chỉ và đơn giá phải giữ đúng lịch sử

Nếu Customer thay đổi địa chỉ và Product đổi giá, Order cũ vẫn phải hiển thị **địa chỉ giao thực tế** và **đơn giá đã chốt**. Hai phương án phổ biến:

- **Snapshot:** chép các thành phần nghiệp vụ cần giữ sang Order/OrderLine tại thời điểm chốt.
- **Versioned reference:** tham chiếu tới phiên bản bất biến của địa chỉ/giá đã hiệu lực.

Không nên đặt ON UPDATE CASCADE lên một quan hệ mà thay đổi ở cha thực chất làm **thay đổi sự thật lịch sử** của hàng con. ON UPDATE CASCADE phục vụ **đổi khóa tham chiếu**, không phải chính sách đồng bộ tất cả thông tin nghiệp vụ.

## 10. Chỉ mục và chi phí của hành vi cập nhật/xóa

Ràng buộc và chỉ mục hỗ trợ đọc nhưng cũng tạo chi phí khi ghi.

### 10.1. Chỉ mục ở phía khóa ngoại

Trong PostgreSQL, tạo FK **không tự tạo chỉ mục** trên cột FK ở bảng con. Khi xóa/đổi khóa cha, DBMS có thể cần tìm các hàng con tham chiếu; thiếu chỉ mục phù hợp có thể khiến kiểm tra rất tốn kém.

~~~sql
CREATE INDEX idx_sales_orders_customer
ON sales_orders (customer_id);

CREATE INDEX idx_order_lines_product
ON order_lines (product_id);

CREATE INDEX idx_shopping_carts_customer
ON shopping_carts (customer_id);
~~~

Với bảng **order_lines**, khóa chính **(order_id, line_no)** đã có chỉ mục bắt đầu bằng **order_id**, nên thường không cần thêm một chỉ mục đơn chỉ để lọc OrderLine theo order_id. Trong khi đó, product_id không nằm đầu khóa chính ghép nên chỉ mục riêng có thể hữu ích nếu thường tra cứu sản phẩm được sử dụng ở những dòng hàng nào.

Chỉ mục cần được lựa chọn theo **truy vấn thực tế, số lượng hàng, tần suất cập nhật và kế hoạch EXPLAIN**. Không nên tạo thêm chỉ mục trùng công dụng chỉ vì mỗi FK trông giống một ứng viên.

### 10.2. ON DELETE CASCADE có thể tạo nhiều thao tác ghi

Nếu hàng cha có rất nhiều con, xóa một hàng cha có thể phát sinh số lượng lớn DELETE trên nhiều bảng, kích hoạt trigger, ghi WAL/log và giữ khóa. Hiệu ứng này cần được đánh giá trước khi cho phép xóa bằng một request API thông thường.

Với khối dữ liệu lớn, có thể cần tiến trình xóa theo đợt, trạng thái chờ xóa, kiểm soát tải và lưu vết thao tác. Nhưng phải bảo đảm không để lại trạng thái bất hợp lệ giữa các đợt; xóa nhiều giao dịch riêng không có cùng ngữ nghĩa nguyên tử với một lệnh CASCADE.

### 10.3. ON UPDATE CASCADE trên khóa được tham chiếu rộng

Đổi khóa cha đang được rất nhiều hàng con dùng có thể gây cập nhật lớn, khóa kéo dài và ghi log nhiều. Hạn chế đổi khóa định danh hoặc ưu tiên khóa thay thế bất biến nếu nghiệp vụ cho phép. Khi buộc phải thay mã khóa có ý nghĩa, đánh giá khối lượng ảnh hưởng và lập kế hoạch thay đổi.

## 11. Truy vết và kiểm chứng sau cập nhật

Hệ thống cần có **truy vấn kiểm kê** đi cùng các ràng buộc. Truy vấn giám sát không thay constraint, nhưng giúp phát hiện sai dữ liệu từ nhập liệu cũ, quá trình di trú hoặc các luồng ghi đặc biệt.

### 11.1. Kiểm tra bản ghi không có cha

Nếu hệ thống đã bật FK hợp lệ, không nên có Order trỏ tới Customer không tồn tại. Truy vấn vẫn hữu ích khi rà soát dữ liệu trước khi thêm FK:

~~~sql
SELECT o.order_id, o.customer_id
FROM sales_orders AS o
LEFT JOIN customers AS c ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

Với các mô hình cho phép customer_id NULL, cần tách “không có cha vì tùy chọn” khỏi “tham chiếu mồ côi”: truy vấn nên thêm **o.customer_id IS NOT NULL** khi chỉ muốn tìm FK hỏng.

### 11.2. Kiểm kê bản ghi đã ngừng hoạt động nhưng vẫn có quan hệ

~~~sql
SELECT p.product_id, p.sku, COUNT(l.order_id) AS historical_line_count
FROM products AS p
LEFT JOIN order_lines AS l ON l.product_id = p.product_id
WHERE p.archived_at IS NOT NULL
GROUP BY p.product_id, p.sku
ORDER BY p.product_id;
~~~

Có OrderLine lịch sử tham chiếu sản phẩm đã archive **không phải lỗi**. Nhưng một OrderLine mới được tạo sau thời điểm archive có thể vi phạm quy tắc “không bán sản phẩm đã ngừng”; để kết luận cần có thời điểm tạo dòng/đơn và chính sách hiệu lực cụ thể.

### 11.3. Phân biệt lỗi toàn vẹn và thay đổi trạng thái hợp lệ

Hãy ghi trong tài liệu mô hình:

- Cặp trạng thái nào được chuyển đổi: DRAFT → CONFIRMED, CONFIRMED → CANCELLED?
- Ai có quyền thực hiện, khi nào?
- Những hàng phụ thuộc nào phải có, phải không có hoặc được giữ nguyên khi chuyển?
- Việc hủy có làm “hoàn tồn kho”, “phát sinh khoản hoàn tiền” hay chỉ thay trạng thái?
- Có cần giữ lịch sử sự kiện và không cho UPDATE trực tiếp trường nào sau khi hoàn tất?

Một số quy tắc không nên gói vào CHECK nếu chúng đòi biết **giá trị cũ** hoặc **hệ thống bên ngoài**. Trigger, stored procedure, workflow ứng dụng và event log có thể bổ trợ lẫn nhau, nhưng phải có nguồn sự thật và khả năng kiểm chứng rõ ràng.

## 12. Thiết kế và di trú ràng buộc trên dữ liệu có sẵn

Khi cơ sở dữ liệu đã có dữ liệu, việc thêm ràng buộc cần kế hoạch thay vì ALTER TABLE tùy tiện.

### 12.1. Quy trình an toàn

1. **Định nghĩa bất biến** từ nghiệp vụ, kể cả ngoại lệ và trạng thái lịch sử.
2. **Đo dữ liệu hiện tại:** giá trị NULL, FK mồ côi, khóa trùng, trạng thái sai, các hàng con không có cha.
3. **Dọn hoặc phân loại dữ liệu bất thường:** sửa theo nguồn dữ liệu đáng tin, không gán giá trị giả tùy tiện.
4. **Chọn hành vi xóa/cập nhật:** RESTRICT, NO ACTION, CASCADE, SET NULL hay SET DEFAULT cho từng quan hệ.
5. **Tạo chỉ mục và ràng buộc** theo kế hoạch giảm thời gian khóa nếu hệ quản trị hỗ trợ.
6. **Bảo đảm mọi writer được cập nhật:** ứng dụng, script nhập liệu, job nền, tích hợp ngoài.
7. **Kiểm tra trên môi trường đại diện:** dữ liệu lớn, giao dịch đồng thời, rollback, deadlock và migration thất bại.
8. **Giám sát sau triển khai:** lỗi constraint, truy vấn kiểm kê, số bản ghi archive và các thao tác xóa hàng loạt.

### 12.2. PostgreSQL: NOT VALID và VALIDATE CONSTRAINT

Với một số ràng buộc như FK và CHECK, PostgreSQL hỗ trợ tạo constraint bằng **NOT VALID** để chưa phải quét xác minh ngay toàn bộ dữ liệu cũ, nhưng các thao tác ghi mới vẫn chịu ràng buộc tương ứng:

~~~sql
-- Minh họa trên một bảng đã tồn tại và có customer_id.
ALTER TABLE legacy_orders
ADD CONSTRAINT fk_legacy_order_customer
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id)
NOT VALID;

-- Khi dữ liệu cũ đã được kiểm tra/sửa:
ALTER TABLE legacy_orders
VALIDATE CONSTRAINT fk_legacy_order_customer;
~~~

Ví dụ giả định **legacy_orders** đã tồn tại, cùng kiểu dữ liệu phù hợp. Hành vi chặn/khóa trong lúc thêm và xác minh constraint còn phụ thuộc PostgreSQL phiên bản, số hàng, chỉ mục và thao tác đồng thời; cần thử theo môi trường thực tế. Không suy rộng rằng **mọi loại constraint** đều hỗ trợ NOT VALID.

### 12.3. Khi đổi từ CASCADE sang RESTRICT

Đổi một chính sách FK đang dùng cần xác nhận không chỉ cú pháp mà cả tác động lên ứng dụng:

- Luồng xóa cũ dựa vào CASCADE có thể bắt đầu thất bại.
- Dữ liệu con trước đây tự biến mất có thể được giữ lại, làm thay đổi dung lượng và cách đọc.
- Các job dọn dữ liệu có thể phải chuyển sang quản lý trạng thái/ngày lưu trữ.
- Cần đo tốc độ xóa, lock timeout và xử lý lỗi phía người dùng.

Tương tự, đổi RESTRICT sang CASCADE có thể là **thay đổi phá hủy dữ liệu**, phải được đánh giá như một quyết định nghiệp vụ quan trọng, không chỉ là tối ưu vận hành.

## 13. Quan hệ với document, đồ thị và mô hình phân tích

Quy tắc toàn vẹn là **ngữ nghĩa nghiệp vụ**. Chọn công nghệ khác chỉ làm thay đổi cơ chế thực thi.

| Mô hình lưu trữ | Biểu diễn quan hệ | Cập nhật/xóa | Điều cần kiểm chứng |
| --- | --- | --- | --- |
| **CSDL quan hệ** | PK/FK, bảng cha–con, bảng nối | ON DELETE/UPDATE và giao dịch | Miền giá trị, ràng buộc xuyên hàng, đồng thời |
| **Document** | Nhúng dữ liệu con hoặc lưu ID tham chiếu | Cập nhật/xóa document, quy trình đồng bộ tham chiếu | Schema, phần tử mồ côi, cập nhật nhiều document, lịch sử |
| **Đồ thị** | Node và relationship có kiểu | Xóa node/cạnh theo quy tắc DB và ứng dụng | Loại cạnh hợp lệ, nút mồ côi, chu trình, bội số và thời gian |
| **Kho dữ liệu phân tích** | Fact, dimension, bridge, phiên bản | Nạp tăng dần, xử lý thay đổi/xóa nguồn | Tính đúng lịch sử, hạt dữ liệu, tổng hợp không trùng |

### 13.1. Document: nhúng hay tham chiếu quyết định vòng đời

Một **giỏ hàng** document có thể nhúng các cart item vì chúng thường được đọc, sửa và xóa cùng nhau:

~~~json
{
  "cartId": 701,
  "customerId": 101,
  "items": [
    {"productId": 501, "quantity": 1}
  ]
}
~~~

Nếu xóa document giỏ hàng, các item nhúng mất theo một cách tự nhiên. Điều đó gần với **composition** hoặc ON DELETE CASCADE trong RDBMS.

Ngược lại, nếu document Order chỉ có customerId tham chiếu tới document Customer độc lập, xóa Customer có thể để lại Order tham chiếu không tồn tại nếu database không hỗ trợ FK xuyên document. Hệ thống phải chọn quy tắc xóa, phiên bản/snapshot, giao dịch đa tài liệu nếu có và kiểm tra tham chiếu ứng dụng phù hợp. Không nên mặc định “document database tự động CASCADE như FK” khi chỉ lưu một ID.

### 13.2. Đồ thị: quan hệ và xóa node

Một node Customer có thể nối với các node Order bằng cạnh PLACED. Nếu xóa Customer, cần quyết định có xóa cạnh, có giữ Order, có chuyển các Order sang tài khoản lưu trữ hay không. Một hệ quản trị đồ thị có thể có yêu cầu kỹ thuật khác nhau đối với xóa node còn cạnh, nhưng **không thể thay thế chính sách lưu chứng từ**.

Cạnh có thể có thời hạn hiệu lực, loại quan hệ và dữ liệu riêng; cần bảo vệ số lượng, chu trình nếu là quan hệ phân cấp, trạng thái của node và quyền ghi.

### 13.3. Warehouse: cập nhật nguồn không có nghĩa sửa lịch sử

Khi Customer đổi tên hoặc chuyển khu vực, báo cáo có thể muốn:

- **Type 1:** thay thuộc tính dimension hiện hành, diễn giải lại lịch sử theo giá trị mới.
- **Type 2:** tạo phiên bản dimension mới, giữ thuộc tính đúng thời điểm phát sinh giao dịch.

Hai phương án phản ánh hai yêu cầu phân tích khác nhau. Khi Product ngừng bán hoặc bị xóa mềm ở nguồn, không nên xóa fact doanh thu cũ chỉ vì dimension đã chuyển trạng thái.

Một thao tác CASCADE tại hệ giao dịch có thể gây khó khăn cho kho phân tích nếu dữ liệu nguồn bị xóa không còn phục hồi được. Cần thiết kế chính sách lưu trữ, CDC, tombstone và xử lý xóa theo phạm vi dữ liệu phù hợp.

## 14. Ma trận kiểm thử hành vi cập nhật và xóa

Không chỉ kiểm thử **INSERT hợp lệ**. Hãy thử các thao tác làm dữ liệu thay đổi theo nhiều hướng:

| Tình huống | Kỳ vọng ví dụ | Cơ chế cần kiểm tra |
| --- | --- | --- |
| Tạo Order với customer_id không tồn tại | Từ chối | FK |
| Tạo OrderLine với quantity = 0 | Từ chối | CHECK + NOT NULL |
| Xóa Customer còn Order | Từ chối | ON DELETE RESTRICT |
| Xóa giỏ tạm có các dòng giỏ | Xóa giỏ và dòng tương ứng | ON DELETE CASCADE |
| Xóa Product đã có trong OrderLine | Từ chối | FK Product |
| Ngừng bán Product còn đơn cũ | Cho phép archive, vẫn đọc lịch sử | UPDATE trạng thái, truy vấn nghiệp vụ |
| Thêm OrderLine mới cho Product archive | Từ chối theo chính sách (chưa có trong DDL minh họa) | Logic nghiệp vụ/trigger |
| Xóa OrderLine cuối của Order đã CONFIRMED | Từ chối theo chính sách (chưa có trong DDL minh họa) | Kiểm tra xuyên hàng/trạng thái |
| Đổi mã Department có nhân viên | Cập nhật FK nhân viên | ON UPDATE CASCADE |
| Xóa Department trong mô hình liên kết tùy chọn | Nhân viên giữ lại với department_code NULL | ON DELETE SET NULL |
| Hai giao dịch cùng giữ một đơn vị tồn kho cuối cùng | Chỉ một giao dịch giữ thành công | UPDATE có điều kiện, khóa hàng |
| Hai phiên cùng sửa mô tả cũ | Phiên thứ hai phát hiện xung đột | Version/optimistic concurrency |
| Chuyển số điện thoại chính | Không có hai số chính, không tự mất số chính bắt buộc | Partial UNIQUE, giao dịch và kiểm tra hàng |
| Xóa dữ liệu khi còn nghĩa vụ lưu lịch sử | Theo quy trình lưu trữ/ẩn danh thay vì xóa tràn lan | Chính sách dữ liệu và audit |

Các trường hợp được ghi là “chưa có trong DDL minh họa” **không** được ngầm hiểu là cơ sở dữ liệu hiện đã chặn. Đó là khoảng trống thiết kế cần lấp bằng cơ chế phù hợp trước khi triển khai thật.

### Những tiêu chí kiểm thử bổ sung

- Khi lệnh xóa bị từ chối, các bước trong **cùng giao dịch** có rollback đúng không?
- Nếu xóa chuỗi nhiều bảng, có tránh mất bản ghi không nằm trong phạm vi được phép xóa không?
- Nếu ràng buộc trì hoãn, lỗi xuất hiện ở **COMMIT** có được xử lý an toàn không?
- Khi hai giao dịch cập nhật cùng đối tượng, có phát hiện conflict, deadlock hoặc serialization failure không?
- Khi thực thi từ import/job không qua API, constraint vẫn bảo vệ đúng mức nào?
- Dữ liệu từ tenant A có thể tham chiếu nhầm tenant B không?
- Có thể khôi phục dữ liệu đã soft delete mà không vi phạm UNIQUE của những bản ghi mới không?
- Các bản ghi lịch sử có còn diễn giải đúng địa chỉ, đơn giá và trạng thái tại thời điểm giao dịch không?

## 15. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách tiếp cận tốt hơn |
| --- | --- | --- |
| Dùng CASCADE cho mọi FK | Có thể xóa mất cả chứng từ và lịch sử | Chọn theo vòng đời cụ thể |
| Cho rằng RESTRICT và NO ACTION luôn giống nhau | Thời điểm kiểm tra có thể khác khi constraint trì hoãn | Xác định yêu cầu giao dịch và DBMS |
| Chọn SET NULL cho FK NOT NULL | Có thể gây lỗi NOT NULL | Chỉ dùng với quan hệ tùy chọn hoặc thiết kế lại |
| Nghĩ SET DEFAULT luôn thành công | Giá trị mặc định vẫn phải thỏa FK | Bảo đảm parent mặc định thật sự tồn tại |
| Coi FK đã kiểm tra mọi điều kiện nghiệp vụ | FK không biết trạng thái ACTIVE, quyền hoặc ngày hiệu lực | Bổ sung điều kiện nghiệp vụ và cơ chế ghi |
| Viết CHECK nhưng không NOT NULL | CHECK có thể chấp nhận UNKNOWN | Tách quy tắc bắt buộc khỏi so sánh miền |
| Cho rằng UNIQUE có nghĩa luôn tồn tại một hàng con | UNIQUE chỉ giới hạn tối đa/trùng | Kiểm tra điều kiện tối thiểu riêng |
| Kiểm tra rồi INSERT/DELETE bằng hai thao tác không đồng bộ | Có race condition | Giao dịch, khóa và ràng buộc phù hợp |
| Soft delete nhưng mong ON DELETE chạy | Soft delete là UPDATE | Có logic theo trạng thái riêng |
| Sửa thuộc tính hiện tại rồi kỳ vọng báo cáo quá khứ đúng | Lịch sử có thể bị diễn giải lại sai | Snapshot hoặc version theo nghiệp vụ |
| Bỏ qua chỉ mục FK ở bảng con | Kiểm tra xóa/đổi khóa cha có thể tốn quét | Tạo index theo tải và EXPLAIN |
| Dùng DELETE để thể hiện hủy giao dịch | Mất vết nghiệp vụ và dữ liệu liên quan | Chuyển trạng thái hoặc bút toán điều chỉnh |

## 16. Bài tập tình huống có gợi ý giải

### Bài 1. Xóa đơn hàng và giỏ hàng

**Đề bài:** Customer có giỏ hàng tạm và có Order đã thanh toán. Khi Customer yêu cầu đóng tài khoản, nhóm phát triển muốn dùng ON DELETE CASCADE từ Customer tới mọi bảng.

**Gợi ý giải:** Giỏ tạm có thể phù hợp CASCADE nếu chính sách cho phép xóa. Order và OrderLine đã thanh toán thường cần giữ lịch sử; không nên CASCADE xóa chứng từ. Hãy phân biệt **đóng tài khoản/khóa truy cập** với **xóa vật lý** và thiết kế quy trình xử lý dữ liệu định danh theo chính sách hợp lệ.

### Bài 2. Cập nhật mã phòng ban

**Đề bài:** Department có mã ENG và được Employee tham chiếu. Doanh nghiệp đổi mã thành DEV nhưng giữ nguyên danh tính phòng. Hành động FK nào có thể giúp?

**Gợi ý giải:** **ON UPDATE CASCADE** có thể cập nhật giá trị khóa ngoại đồng bộ. Tuy nhiên, nếu mã phòng thường xuyên thay đổi, một khóa **department_id bất biến** làm PK còn mã là UNIQUE thường thuận tiện hơn và giảm số FK phải sửa khi đổi mã.

### Bài 3. Thao tác SET NULL thất bại

**Đề bài:** Bảng Task có assignee_id NOT NULL và FK ON DELETE SET NULL tới Employee. Xóa Employee đang được giao Task có thành công không?

**Gợi ý giải:** Không, vì SET NULL mâu thuẫn với NOT NULL. Cần **RESTRICT** việc xóa Employee, chuyển giao Task trước khi xóa, hoặc cho phép Task chưa được giao nếu đúng nghiệp vụ.

### Bài 4. Tối đa một và đúng một

**Đề bài:** Một Customer có nhiều email nhưng được yêu cầu có **đúng một email chính** khi trạng thái ACTIVE. Có đủ nếu thêm UNIQUE(customer_id) WHERE is_primary không?

**Gợi ý giải:** Chưa đủ. Index chỉ bảo đảm **tối đa một**. Phải bảo đảm **ít nhất một** email chính ở trạng thái ACTIVE, kể cả khi xóa/chuyển email hoặc khi hai giao dịch đồng thời thay đổi. Cần quy trình và cơ chế kiểm tra xuyên bảng.

### Bài 5. Tồn kho dưới cạnh tranh

**Đề bài:** Còn một sản phẩm, hai request đều đọc available = 1 rồi muốn mua. Vì sao SELECT rồi UPDATE không đủ?

**Gợi ý giải:** Hai request có thể cùng dựa trên dữ liệu cũ. Một **UPDATE có điều kiện** (available >= 1) trên cùng hàng, kèm kiểm tra số hàng cập nhật, là cách trực tiếp để đảm bảo chỉ một request giữ hàng thành công. Phải thực hiện cùng giao dịch với các thay đổi đơn hàng/tồn kho liên quan.

### Bài 6. Địa chỉ lịch sử

**Đề bài:** Order 1001 đã giao đến địa chỉ A. Customer sau đó sửa địa chỉ hiện hành thành B. Nếu Order chỉ tham chiếu địa chỉ hiện hành của Customer, báo cáo giao nhận năm trước có thể hiển thị gì?

**Gợi ý giải:** Có thể hiển thị B sai lịch sử. Order cần snapshot thông tin giao hàng hoặc tham chiếu phiên bản địa chỉ bất biến đã dùng tại thời điểm đặt/giao.

### Bài 7. Nhập dữ liệu cũ và bổ sung FK

**Đề bài:** Bảng legacy_orders có vài customer_id không tồn tại trong customers. Có nên xóa tất cả Order mồ côi rồi thêm FK?

**Gợi ý giải:** Không tự động. Phải truy nguồn, phân loại theo chính sách, quyết định sửa tham chiếu, khôi phục Customer bị thiếu, lưu trạng thái ngoại lệ hoặc xử lý dữ liệu không hợp lệ theo yêu cầu. PostgreSQL có thể thêm FK NOT VALID rồi làm sạch dữ liệu cũ và VALIDATE sau đó, nhưng dữ liệu mới phải được kiểm soát.

### Bài 8. Cập nhật đa bước và NO ACTION

**Đề bài:** Giao dịch cần tạm thay thế một hàng cha rồi khôi phục tham chiếu hợp lệ trước COMMIT. Tại sao NO ACTION DEFERRABLE có thể phù hợp hơn RESTRICT?

**Gợi ý giải:** Khi được đặt DEFERRED, NO ACTION có thể kiểm tra ở cuối giao dịch và cho phép trạng thái trung gian tạm thời không thỏa FK. RESTRICT không cho trì hoãn hành động hạn chế tương ứng trong PostgreSQL. Cuối giao dịch vẫn phải hợp lệ; xử lý lỗi ở COMMIT là bắt buộc.

## 17. Ghi nhớ

**Hành vi cập nhật và xóa là một phần của mô hình dữ liệu, không chỉ là tùy chọn cú pháp FOREIGN KEY.** Với mỗi quan hệ, hãy trả lời rõ: hàng con có được tồn tại độc lập không, có cần giữ lịch sử không, khóa cha có thể đổi không, xóa là vật lý hay thay đổi trạng thái, và liệu những giao dịch đồng thời có thể phá vỡ bất biến hay không.

- **RESTRICT/NO ACTION** bảo vệ sự tồn tại của tham chiếu với ngữ nghĩa thời điểm kiểm tra khác nhau.
- **CASCADE** thực hiện thay đổi dây chuyền; thích hợp với thành phần phụ thuộc vòng đời đã xác nhận, nhưng rủi ro với chứng từ.
- **SET NULL/SET DEFAULT** thay đổi liên kết, chỉ hợp lệ khi giá trị mới tuân theo mô hình và chính sách.
- **PK, FK, UNIQUE, NOT NULL, CHECK** giải quyết các lớp toàn vẹn khác nhau; không một loại ràng buộc đơn lẻ thay thế được toàn bộ chính sách nghiệp vụ.
- **Giao dịch, khóa, isolation và cơ chế retry** là điều kiện cần cân nhắc khi bảo vệ quy tắc xuyên nhiều hàng hoặc cập nhật đồng thời.
- **Snapshot, trạng thái, lịch sử và thời hạn lưu giữ** phải được thiết kế ngay từ đầu để các thao tác cập nhật/xóa không làm mất ý nghĩa dữ liệu quá khứ.

Một lược đồ vững chắc cho phép cập nhật khi cần, **chặn thay đổi sai ở đúng ranh giới**, và vẫn duy trì được tính toàn vẹn trong dữ liệu quan hệ, document, đồ thị lẫn kho phân tích khi hệ thống phát triển.
