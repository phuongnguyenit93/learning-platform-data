# ON DELETE, ON UPDATE và lựa chọn hành vi lan truyền trong PostgreSQL

Khi hai bảng liên hệ bằng **khóa ngoại (foreign key)**, PostgreSQL không chỉ kiểm tra rằng bản ghi con đang tham chiếu một bản ghi cha hợp lệ. Hệ quản trị còn cần quy tắc xử lý khi bản ghi cha **bị xóa** hoặc **giá trị khóa được tham chiếu bị cập nhật**.

Giả sử bảng `orders` chứa `customer_id` trỏ tới `customers.customer_id`:

- Nếu xóa một khách hàng đang có đơn, có nên xóa luôn các đơn?
- Nếu khách hàng bị xóa, có nên giữ đơn nhưng bỏ liên kết tới khách hàng?
- Nếu mã khách hàng đổi từ 10 sang 20, khóa ngoại trong `orders` có tự đổi không?
- Nếu phải giữ đơn để tuân thủ kế toán, làm thế nào ngăn xóa nhầm?

Trong PostgreSQL, các mệnh đề **`ON DELETE`** và **`ON UPDATE`** thuộc định nghĩa `FOREIGN KEY` cho phép chọn hành vi tương ứng. Những lựa chọn phổ biến là `NO ACTION`, `RESTRICT`, `CASCADE`, `SET NULL` và `SET DEFAULT`.

Việc lựa chọn không đơn thuần là cú pháp SQL. Nó phản ánh **vòng đời dữ liệu và quy tắc nghiệp vụ**: bản ghi con có được tồn tại độc lập hay không, khóa có được thay đổi hay không, dữ liệu lịch sử có phải giữ lại hay không, và một thao tác có thể gây thay đổi dây chuyền tới bao nhiêu bảng.

## 1. Ôn lại quan hệ cha – con và khóa ngoại

Một khóa ngoại nối các giá trị ở **bảng tham chiếu (referencing table, thường gọi là bảng con)** đến khóa duy nhất hợp lệ ở **bảng được tham chiếu (referenced table, thường gọi là bảng cha)**.

Ví dụ:

~~~sql
CREATE TABLE customers (
    customer_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
~~~

Ở đây:

| Thành phần | Giá trị trong ví dụ |
| --- | --- |
| Bảng cha | `customers` |
| Khóa được tham chiếu | `customers.customer_id` |
| Bảng con | `orders` |
| Cột khóa ngoại | `orders.customer_id` |
| Ràng buộc | `fk_orders_customer` |

PostgreSQL đảm bảo mỗi `orders.customer_id` không `NULL` khớp với một `customers.customer_id` đang tồn tại. Trong ví dụ, `NOT NULL` còn yêu cầu mọi đơn hàng có một khách hàng.

~~~mermaid
flowchart LR
    P["customers: customer_id PRIMARY KEY"] -->|"Được tham chiếu bởi"| C["orders: customer_id FOREIGN KEY"]
    P --> D{"Xóa hoặc đổi khóa ở customers?"}
    D --> R["ON DELETE / ON UPDATE quyết định"]
    R --> A["Ngăn, lan truyền hoặc thay FK"]
~~~

Một thao tác `INSERT` hoặc `UPDATE` ở **bảng con** vẫn phải thỏa khóa ngoại. Mệnh đề `ON UPDATE` **không** có nghĩa mọi lần cập nhật cột FK ở bảng con sẽ tự thay đổi bảng cha; nó quy định **hành vi khi khóa được tham chiếu ở bảng cha thay đổi**.

## 2. Cú pháp tổng quát

Một khóa ngoại có thể khai báo hành động cho hai hướng:

~~~sql
CREATE TABLE child_table (
    child_id bigint PRIMARY KEY,
    parent_id bigint NOT NULL,

    CONSTRAINT fk_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES parent_table(parent_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);
~~~

Câu trên giả định `parent_table(parent_id)` đã tồn tại và có khóa chính hoặc ràng buộc duy nhất phù hợp.

Có thể khai báo inline với khóa ngoại một cột:

~~~sql
parent_id bigint
    REFERENCES parent_table(parent_id)
    ON DELETE SET NULL
    ON UPDATE CASCADE
~~~

Với khóa ngoại nhiều cột, khai báo `FOREIGN KEY (...) REFERENCES ...` tường minh thường dễ đọc và kiểm soát hơn.

**Hai mệnh đề độc lập:** `ON DELETE` xử lý khi **xóa hàng cha**; `ON UPDATE` xử lý khi **giá trị khóa được tham chiếu của hàng cha thay đổi**. Bạn có thể chọn `ON DELETE RESTRICT ON UPDATE CASCADE` trên cùng một ràng buộc.

Nếu không chỉ định, PostgreSQL mặc định là:

~~~sql
ON DELETE NO ACTION
ON UPDATE NO ACTION
~~~

## 3. Bảng so sánh năm hành động

| Hành động | Khi xóa hàng cha (`ON DELETE`) | Khi sửa khóa cha (`ON UPDATE`) | Cần lưu ý |
| --- | --- | --- | --- |
| **`NO ACTION`** | Không cho trạng thái cuối vi phạm FK; phép kiểm tra có thể được hoãn nếu constraint `DEFERRABLE` | Tương tự | Mặc định; khác `RESTRICT` ở khả năng trì hoãn kiểm tra |
| **`RESTRICT`** | Chặn xóa khi hàng cha vẫn bị tham chiếu | Chặn đổi khóa nếu vi phạm quy tắc restrict | Không thể hoãn kiểm tra hành động này như `NO ACTION` |
| **`CASCADE`** | Xóa những hàng con đang tham chiếu | Thay giá trị FK ở hàng con theo khóa cha mới | Có thể tác động nhiều hàng/bảng theo chuỗi |
| **`SET NULL`** | Đặt cột FK ở hàng con thành `NULL` | Đặt cột FK thành `NULL` | Cột phải cho phép NULL; với FK nhiều cột có lưu ý riêng |
| **`SET DEFAULT`** | Đưa cột FK về giá trị mặc định khai báo | Đưa FK về mặc định khi khóa cha đổi | Giá trị mặc định phải tiếp tục thỏa FK và các constraint khác |

Có thể hình dung bằng một cây quyết định:

~~~mermaid
flowchart TD
    A["Cha bị DELETE hoặc khóa được UPDATE"] --> B{"Con phải phản ứng ra sao?"}
    B -->|"Giữ liên kết và ngăn thao tác vi phạm"| C["NO ACTION / RESTRICT"]
    B -->|"Con cùng vòng đời hoặc FK cần đổi theo"| D["CASCADE"]
    B -->|"Con vẫn tồn tại nhưng quan hệ thành tùy chọn"| E["SET NULL"]
    B -->|"Con chuyển về đối tượng mặc định hợp lệ"| F["SET DEFAULT"]
    C --> G["Kiểm tra khả năng DEFERRABLE"]
    D --> H["Đánh giá phạm vi thay đổi dây chuyền"]
    E --> I["Kiểm tra NOT NULL và FK ghép"]
    F --> J["Kiểm tra DEFAULT có cha hợp lệ"]
~~~

Cây này hỗ trợ suy nghĩ, không tự đưa ra quyết định cho một nghiệp vụ. Một lựa chọn hợp lệ về mặt cú pháp có thể **sai nghiêm trọng về mặt lưu trữ dữ liệu**.

## 4. NO ACTION: hành vi mặc định

`NO ACTION` thường có nghĩa: nếu một thao tác ở bảng cha khiến hàng con trở thành tham chiếu không hợp lệ, PostgreSQL sẽ báo lỗi khi ràng buộc được kiểm tra.

Ví dụ:

~~~sql
CREATE TABLE departments_na (
    department_id integer PRIMARY KEY,
    department_name text NOT NULL
);

CREATE TABLE employees_na (
    employee_id integer PRIMARY KEY,
    department_id integer NOT NULL,
    CONSTRAINT fk_employee_department_na
        FOREIGN KEY (department_id)
        REFERENCES departments_na(department_id)
        ON DELETE NO ACTION
        ON UPDATE NO ACTION
);
~~~

Nạp dữ liệu:

~~~sql
INSERT INTO departments_na
    (department_id, department_name)
VALUES (10, 'Engineering');

INSERT INTO employees_na
    (employee_id, department_id)
VALUES (100, 10);
~~~

Nếu thử xóa phòng ban 10:

~~~sql
DELETE FROM departments_na
WHERE department_id = 10;
~~~

PostgreSQL từ chối vì nhân viên 100 vẫn tham chiếu phòng ban 10. Lỗi thường thuộc SQLSTATE **`23503`**, tức vi phạm khóa ngoại.

**Không có `ON DELETE` được ghi rõ cũng vẫn là `NO ACTION`.** Đừng hiểu việc bỏ mệnh đề là PostgreSQL sẽ xóa hàng con hay tự đặt NULL.

### NO ACTION không có nghĩa “không làm gì và cứ cho xóa”

Tên gọi dễ gây hiểu nhầm. PostgreSQL **không bỏ qua tính toàn vẹn tham chiếu**. Nó chỉ không tự thay đổi hàng con bằng một hành động như `CASCADE` hoặc `SET NULL`. Nếu không còn hàng cha cho một FK bắt buộc, thao tác sẽ bị chặn theo thời điểm kiểm tra constraint.

## 5. RESTRICT: chặn thay đổi khi còn tham chiếu

`RESTRICT` cũng ngăn xóa hoặc sửa khóa cha khi vẫn tồn tại các hàng con không còn hợp lệ.

~~~sql
CREATE TABLE customers_restrict (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE orders_restrict (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES customers_restrict(customer_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
);
~~~

Ví dụ này phù hợp để diễn đạt rằng **không thể xóa khách hàng đang có đơn**. Nhưng hành vi quản lý dữ liệu thật có thể cần soft delete, ẩn danh dữ liệu hoặc chính sách lưu hồ sơ; `RESTRICT` không tự giải quyết tất cả những yêu cầu đó.

### RESTRICT khác NO ACTION ở điểm nào?

Trong tình huống đơn giản, hai hành động **trông giống nhau**: xóa khách hàng đang có đơn đều báo lỗi.

Sự khác biệt quan trọng nằm ở **thời điểm có thể trì hoãn kiểm tra**:

- `NO ACTION` cho phép kiểm tra tính hợp lệ **ở cuối transaction** nếu ràng buộc được khai báo `DEFERRABLE` và đã chuyển sang chế độ deferred.
- `RESTRICT` **không thể được trì hoãn theo cách đó**. Việc thao tác ngay lúc này còn hàng con tham chiếu vẫn bị ngăn, dù dự định sửa hàng con ở câu SQL sau.

Ví dụ cần đổi mã cha trước, sau đó mới cập nhật mã con trong một transaction: `NO ACTION DEFERRABLE` có thể đáp ứng, trong khi `RESTRICT` không phù hợp cho quy trình đó.

Ngoài tính trì hoãn, PostgreSQL còn có khác biệt chi tiết giữa `NO ACTION` và `RESTRICT` ở một số phép cập nhật giá trị khóa dưới quy tắc so sánh/collation đặc biệt. Khi chọn, hãy dựa vào ngữ nghĩa cần bảo đảm thay vì coi chúng tuyệt đối đồng nhất.

## 6. DEFERRABLE và bài toán thay đổi khóa theo hai bước

Theo mặc định, đa số FK được kiểm tra ngay theo ngữ nghĩa constraint không trì hoãn. PostgreSQL cho phép khai báo một số ràng buộc là `DEFERRABLE` và quyết định thời điểm kiểm tra.

Thí nghiệm dưới đây tạo hai bảng độc lập:

~~~sql
CREATE TABLE parent_codes (
    code integer PRIMARY KEY
);

CREATE TABLE child_codes (
    child_id integer PRIMARY KEY,
    parent_code integer NOT NULL,
    CONSTRAINT fk_child_parent_codes
        FOREIGN KEY (parent_code)
        REFERENCES parent_codes(code)
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
        DEFERRABLE INITIALLY IMMEDIATE
);

INSERT INTO parent_codes (code) VALUES (10);
INSERT INTO child_codes (child_id, parent_code)
VALUES (1, 10);
~~~

Nếu chạy:

~~~sql
UPDATE parent_codes
SET code = 20
WHERE code = 10;
~~~

mà không đồng thời cập nhật con, ràng buộc mặc định đang kiểm tra ngay sẽ từ chối.

Nhưng có thể thực hiện trong **một transaction có kiểm soát**:

~~~sql
BEGIN;

SET CONSTRAINTS fk_child_parent_codes DEFERRED;

UPDATE parent_codes
SET code = 20
WHERE code = 10;

UPDATE child_codes
SET parent_code = 20
WHERE parent_code = 10;

COMMIT;
~~~

Khi commit, mọi FK lại hợp lệ. Hai bước trung gian có thể được cho phép do kiểm tra `NO ACTION` đã được hoãn. Nếu câu cập nhật con không chạy hoặc còn hàng tham chiếu cũ, `COMMIT` sẽ báo lỗi.

**Lưu ý:** `SET CONSTRAINTS ... DEFERRED` chỉ áp dụng cho constraint thực sự khai báo `DEFERRABLE`. `RESTRICT` không cho phép hoãn riêng hành động restrict. Với `CASCADE`, `SET NULL` hoặc `SET DEFAULT`, hành động trên hàng con được thực hiện khi sự kiện ở cha diễn ra; không nên coi chúng sẽ được hoãn chỉ vì FK được khai báo deferrable.

### Khi nào cần dùng DEFERRABLE?

Thường là các bài toán có phụ thuộc vòng, tái đánh số khóa theo nhiều bước hoặc thao tác nhập/chuyển đổi dữ liệu cần bảo toàn tính toàn vẹn **ở cuối transaction**.

Trong thiết kế ứng dụng thông thường, tốt hơn là **không thay đổi khóa chính thường xuyên**. Nếu mã nghiệp vụ cần được sửa, hãy cân nhắc tách **khóa định danh ổn định** khỏi **mã nghiệp vụ có thể thay đổi**. Điều này giúp giảm nhu cầu hoãn FK.

## 7. CASCADE: xóa hoặc cập nhật theo quan hệ

`CASCADE` khiến PostgreSQL tự xử lý các hàng con tham chiếu khi một hàng cha bị thay đổi.

### 7.1. ON DELETE CASCADE

~~~sql
CREATE TABLE carts (
    cart_id bigint PRIMARY KEY
);

CREATE TABLE cart_items (
    cart_id bigint NOT NULL
        REFERENCES carts(cart_id)
        ON DELETE CASCADE,
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (cart_id, product_code)
);
~~~

Nạp dữ liệu:

~~~sql
INSERT INTO carts (cart_id) VALUES (1);

INSERT INTO cart_items (cart_id, product_code, quantity)
VALUES
    (1, 'MOUSE', 2),
    (1, 'CABLE', 1);
~~~

Khi thực hiện:

~~~sql
DELETE FROM carts
WHERE cart_id = 1;
~~~

PostgreSQL xóa giỏ hàng 1 **và** hai dòng `cart_items` đang phụ thuộc. Hai dòng hàng con không còn tồn tại sau khi transaction commit thành công.

Quan hệ giỏ hàng–dòng hàng thường có vòng đời gắn chặt: xóa giỏ nháp thì dòng hàng không có ý nghĩa tồn tại độc lập. Đây là ví dụ thích hợp cho `ON DELETE CASCADE`.

### 7.2. ON UPDATE CASCADE

Giả sử khóa định danh trong bảng cha có thể thay đổi:

~~~sql
CREATE TABLE product_codes (
    product_code text PRIMARY KEY,
    product_name text NOT NULL
);

CREATE TABLE stock_by_product (
    stock_id integer PRIMARY KEY,
    product_code text NOT NULL
        REFERENCES product_codes(product_code)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    quantity integer NOT NULL
);

INSERT INTO product_codes
    (product_code, product_name)
VALUES ('SKU-OLD', 'Mouse');

INSERT INTO stock_by_product
    (stock_id, product_code, quantity)
VALUES (1, 'SKU-OLD', 15);
~~~

Đổi mã cha:

~~~sql
UPDATE product_codes
SET product_code = 'SKU-NEW'
WHERE product_code = 'SKU-OLD';
~~~

PostgreSQL sẽ tự cập nhật `stock_by_product.product_code` đang tham chiếu `SKU-OLD` thành `SKU-NEW`.

Đây là **lan truyền khóa tham chiếu**, không phải tự cập nhật các cột khác như `product_name` hoặc `quantity`. Nếu thay `product_name` nhưng không thay khóa `product_code`, `ON UPDATE CASCADE` không tự sửa nội dung ở bảng con.

### 7.3. Lan truyền có thể đi nhiều tầng

~~~mermaid
flowchart TD
    A["DELETE order"] --> B["ON DELETE CASCADE: order_items"]
    B --> C{"order_items còn bị bảng khác tham chiếu?"}
    C -->|"Có cascade phù hợp"| D["Tiếp tục thay đổi bảng phụ thuộc"]
    C -->|"Có RESTRICT hoặc NO ACTION"| E["Thao tác có thể bị từ chối"]
    C -->|"Không"| F["Kết thúc trong transaction"]
    D --> F
~~~

Nếu một hàng con lại là cha của bảng khác, các thao tác do cascade tạo ra có thể tiếp tục kích hoạt ràng buộc ở các tầng sau. Vì vậy, một câu `DELETE FROM orders WHERE ...` có thể tác động nhiều bảng.

**CASCADE không có nghĩa chỉ xóa “những hàng con trực tiếp mà người viết nhớ tới”.** Trước khi bật ở hệ thống thực tế, hãy khảo sát toàn bộ đồ thị FK và vòng đời nghiệp vụ của dữ liệu.

## 8. SET NULL: giữ hàng con nhưng bỏ liên kết

`SET NULL` phù hợp khi bản ghi con vẫn có ý nghĩa sau khi đối tượng được tham chiếu biến mất và quan hệ có thể là tùy chọn.

Ví dụ nhiệm vụ được giao cho nhân viên:

~~~sql
CREATE TABLE employees (
    employee_id integer PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE tasks (
    task_id integer PRIMARY KEY,
    assignee_id integer NULL
        REFERENCES employees(employee_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE,
    title text NOT NULL
);

INSERT INTO employees
    (employee_id, full_name)
VALUES (11, 'An');

INSERT INTO tasks
    (task_id, assignee_id, title)
VALUES
    (701, 11, 'Xu ly yeu cau'),
    (702, NULL, 'Chua phan cong');
~~~

Khi xóa nhân viên 11:

~~~sql
DELETE FROM employees
WHERE employee_id = 11;
~~~

Nhiệm vụ 701 **không bị xóa** mà `assignee_id` trở thành `NULL`. Nhiệm vụ 702 vốn chưa có người phụ trách vẫn tồn tại.

### NOT NULL có tương thích với SET NULL không?

Không, nếu thực sự cần đặt cột đó thành NULL:

~~~sql
-- Thiết kế không tương thích về mặt hành vi xóa:
assignee_id integer NOT NULL
    REFERENCES employees(employee_id)
    ON DELETE SET NULL
~~~

PostgreSQL có thể cho tạo định nghĩa như trên, nhưng khi xóa hàng cha đang có hàng con, hành động cố đặt `assignee_id = NULL` sẽ va vào `NOT NULL` và câu xóa thất bại.

Vì vậy:

- Nếu con được phép không còn cha, dùng cột nullable với `SET NULL`.
- Nếu con **bắt buộc luôn có cha**, cân nhắc `RESTRICT`/`NO ACTION` hoặc một cơ chế tái gán trước khi xóa.
- Nếu cả cha và con phải biến mất cùng nhau, cân nhắc `CASCADE` sau khi đánh giá vòng đời.

### ON UPDATE SET NULL có ý nghĩa gì?

Nếu đặt `ON UPDATE SET NULL` rồi đổi **khóa cha**, PostgreSQL sẽ bỏ liên kết ở con thay vì cập nhật con theo khóa mới. Điều đó thường không mong muốn khi chỉ “đổi mã nhân viên”.

Vì vậy ví dụ dùng **`ON DELETE SET NULL ON UPDATE CASCADE`**: xóa nhân viên thì giữ task chưa gán; đổi mã nhân viên thì task tiếp tục theo người đó.

## 9. SET DEFAULT: chuyển hàng con sang giá trị mặc định hợp lệ

`SET DEFAULT` đặt cột khóa ngoại ở bảng con về biểu thức `DEFAULT` đã khai báo. Hành động này **không bỏ qua ràng buộc khóa ngoại**.

Giả sử sản phẩm thuộc một danh mục, và khi xóa danh mục nghiệp vụ muốn chuyển sản phẩm về danh mục “Chưa phân loại”.

~~~sql
CREATE TABLE categories (
    category_id integer PRIMARY KEY,
    category_name text NOT NULL
);

-- ID 0 là một hàng cha thực sự, được bảo vệ theo nghiệp vụ.
INSERT INTO categories
    (category_id, category_name)
VALUES
    (0, 'Chua phan loai'),
    (10, 'Phu kien');

CREATE TABLE products (
    product_id integer PRIMARY KEY,
    category_id integer NOT NULL DEFAULT 0
        REFERENCES categories(category_id)
        ON DELETE SET DEFAULT
        ON UPDATE CASCADE,
    product_name text NOT NULL
);

INSERT INTO products
    (product_id, category_id, product_name)
VALUES (501, 10, 'Mouse');
~~~

Khi xóa danh mục 10:

~~~sql
DELETE FROM categories
WHERE category_id = 10;
~~~

Sản phẩm 501 vẫn còn, nhưng `category_id` thành `0`, tham chiếu tới hàng danh mục “Chưa phân loại”.

### Vì sao cần hàng cha có ID mặc định?

Nếu `products.category_id DEFAULT 0` mà bảng `categories` **không có hàng 0**, hành động `SET DEFAULT` tạo một giá trị FK không hợp lệ và câu xóa có thể bị từ chối.

Tương tự, một default là `NULL` chỉ hợp lệ nếu cột và các ràng buộc khác cho phép `NULL`. `SET DEFAULT` **không tự tạo bản ghi cha** hoặc bỏ qua tính toàn vẹn tham chiếu.

### Nên bảo vệ hàng “Chưa phân loại”

Trong ví dụ, danh mục 0 là một **sentinel row** được hệ thống dùng làm đích chuyển. Nếu ai đó xóa chính hàng 0 trong khi nhiều sản phẩm tham chiếu đến nó, `SET DEFAULT 0` không giải quyết được vấn đề: sau khi xóa, không còn hàng cha 0 hợp lệ.

Trong môi trường thật, cần chính sách bảo vệ sentinel row và không dựa vào việc nó “chắc chắn không bao giờ bị xóa” nếu không có cơ chế kiểm soát.

### ON UPDATE SET DEFAULT có thường hữu ích?

Ít phổ biến hơn `ON UPDATE CASCADE`. Nếu khóa cha đổi, `SET DEFAULT` bỏ quan hệ cũ và đưa con về giá trị mặc định, **không giữ nguyên liên kết nghiệp vụ**. Chỉ chọn khi đó chính là mong muốn được mô tả rõ.

## 10. Bài lab tổng hợp trong một schema riêng

Để so sánh hành vi của cùng một hệ thống, ta sẽ tạo database **riêng cho thực hành**, ví dụ `fk_actions_lab`, rồi thực hiện toàn bộ ví dụ trong schema `lab_fk`.

**Cảnh báo:** đoạn chuẩn bị có `DROP SCHEMA ... CASCADE`. Chỉ chạy trên database lab bạn sở hữu sau khi xác nhận không có dữ liệu cần giữ.

### 10.1. Tạo schema và bảng

~~~sql
BEGIN;

DROP SCHEMA IF EXISTS lab_fk CASCADE;
CREATE SCHEMA lab_fk;

-- Khách hàng: cha của đơn hàng.
CREATE TABLE lab_fk.customers (
    customer_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

-- Đơn hàng: khách hàng không được xóa nếu còn đơn.
CREATE TABLE lab_fk.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_fk.customers(customer_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

-- Danh mục sản phẩm, có sentinel category_id = 0.
CREATE TABLE lab_fk.categories (
    category_id bigint PRIMARY KEY,
    category_name text NOT NULL
);

-- Khi xóa danh mục, sản phẩm chuyển về category_id 0.
CREATE TABLE lab_fk.products (
    product_id bigint PRIMARY KEY,
    category_id bigint NOT NULL DEFAULT 0,
    product_name text NOT NULL,
    CONSTRAINT fk_products_category
        FOREIGN KEY (category_id)
        REFERENCES lab_fk.categories(category_id)
        ON DELETE SET DEFAULT
        ON UPDATE CASCADE
);

-- Bảng liên kết đơn hàng - sản phẩm.
CREATE TABLE lab_fk.order_items (
    order_id bigint NOT NULL,
    product_id bigint NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id),

    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES lab_fk.orders(order_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES lab_fk.products(product_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

-- Nhân viên và task: task tồn tại khi nhân viên bị xóa.
CREATE TABLE lab_fk.employees (
    employee_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE lab_fk.tasks (
    task_id bigint PRIMARY KEY,
    assignee_id bigint NULL,
    title text NOT NULL,
    CONSTRAINT fk_tasks_assignee
        FOREIGN KEY (assignee_id)
        REFERENCES lab_fk.employees(employee_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

COMMIT;
~~~

Trong schema này có đủ bốn hành vi dễ quan sát:

| Quan hệ | ON DELETE | ON UPDATE | Giải thích nghiệp vụ |
| --- | --- | --- | --- |
| customers → orders | `RESTRICT` | `CASCADE` | Giữ đơn hàng, không cho xóa khách đang có đơn; cho đổi mã |
| orders → order_items | `CASCADE` | `CASCADE` | Dòng hàng gắn trực tiếp với đơn |
| products → order_items | `RESTRICT` | `CASCADE` | Không xóa sản phẩm đã được dùng trong đơn |
| categories → products | `SET DEFAULT` | `CASCADE` | Xóa danh mục thì chuyển về “Chưa phân loại” |
| employees → tasks | `SET NULL` | `CASCADE` | Task vẫn tồn tại khi người phụ trách bị xóa |

`NO ACTION` là mặc định và sẽ được minh họa ở một bảng khác về constraint deferrable; không cần gắn đồng thời tất cả hành động vào một khóa ngoại.

### 10.2. Nạp dữ liệu mẫu

~~~sql
BEGIN;

INSERT INTO lab_fk.customers
    (customer_id, full_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi');

INSERT INTO lab_fk.orders
    (order_id, customer_id, status)
VALUES
    (1001, 1, 'paid'),
    (1002, 2, 'pending');

INSERT INTO lab_fk.categories
    (category_id, category_name)
VALUES
    (0, 'Chua phan loai'),
    (10, 'Phu kien'),
    (20, 'Cap noi');

INSERT INTO lab_fk.products
    (product_id, category_id, product_name)
VALUES
    (501, 10, 'Mouse'),
    (502, 20, 'Cable'),
    (503, 10, 'Keyboard');

INSERT INTO lab_fk.order_items
    (order_id, product_id, quantity)
VALUES
    (1001, 501, 2),
    (1001, 502, 1),
    (1002, 501, 1);

INSERT INTO lab_fk.employees
    (employee_id, full_name)
VALUES
    (11, 'Lan'),
    (12, 'Minh');

INSERT INTO lab_fk.tasks
    (task_id, assignee_id, title)
VALUES
    (701, 11, 'Duyet tai lieu'),
    (702, NULL, 'Cho phan cong');

COMMIT;
~~~

Dữ liệu sau seed:

- Khách hàng 1 có đơn 1001; khách hàng 2 có đơn 1002; khách hàng 3 chưa có đơn.
- Đơn 1001 có hai dòng hàng (sản phẩm 501, 502); đơn 1002 có một dòng (sản phẩm 501).
- Sản phẩm 501 và 503 thuộc danh mục 10; sản phẩm 502 thuộc danh mục 20.
- Nhân viên 11 đang phụ trách task 701; task 702 chưa được phân công.
- Danh mục 0 tồn tại để dùng cho hành vi `SET DEFAULT`.

### 10.3. Minh họa ON DELETE CASCADE trong transaction có ROLLBACK

~~~sql
BEGIN;

DELETE FROM lab_fk.orders
WHERE order_id = 1001;

SELECT order_id, product_id, quantity
FROM lab_fk.order_items
ORDER BY order_id, product_id;

ROLLBACK;
~~~

Trong phạm vi transaction trước khi `ROLLBACK`, hai dòng item của đơn 1001 đã biến mất do `ON DELETE CASCADE`. Dòng của đơn 1002 vẫn còn. Sau `ROLLBACK`, cả đơn 1001 và hai dòng item được khôi phục về trạng thái trước transaction.

Điều đó chứng minh cascade là **thao tác dữ liệu thuộc transaction**, không phải một công việc nền nằm ngoài transaction mà không thể hoàn tác.

### 10.4. Minh họa ON DELETE SET NULL

~~~sql
BEGIN;

DELETE FROM lab_fk.employees
WHERE employee_id = 11;

SELECT task_id, assignee_id, title
FROM lab_fk.tasks
ORDER BY task_id;

ROLLBACK;
~~~

Trong transaction, task 701 có `assignee_id IS NULL`; task 702 cũng `NULL` như từ đầu. Sau rollback, task 701 lại tham chiếu nhân viên 11.

### 10.5. Minh họa ON DELETE SET DEFAULT

~~~sql
BEGIN;

DELETE FROM lab_fk.categories
WHERE category_id = 10;

SELECT product_id, category_id, product_name
FROM lab_fk.products
ORDER BY product_id;

ROLLBACK;
~~~

Trong transaction, sản phẩm 501 và 503 có `category_id = 0`; sản phẩm 502 vẫn ở danh mục 20. Sau rollback, danh mục 10 và các liên kết ban đầu quay lại.

### 10.6. Minh họa ON UPDATE CASCADE

~~~sql
BEGIN;

UPDATE lab_fk.products
SET product_id = 601
WHERE product_id = 501;

SELECT order_id, product_id, quantity
FROM lab_fk.order_items
ORDER BY order_id, product_id;

ROLLBACK;
~~~

Trong transaction, các dòng từng dùng `product_id = 501` giờ tham chiếu `601`. Sau rollback, ID gốc 501 được phục hồi.

**Trong thiết kế thực tế, không nên đổi khóa chính bất biến chỉ để kiểm tra CASCADE.** Đây là một tình huống lab nhằm minh họa semantics; có thể giữ ID ổn định và đổi mã sản phẩm nghiệp vụ ở cột riêng.

### 10.7. Minh họa RESTRICT mà không làm hỏng bộ lab

Thử xóa khách hàng 1 vẫn có đơn:

~~~sql
-- Lệnh này CỐ Ý phát sinh lỗi khóa ngoại.
DELETE FROM lab_fk.customers
WHERE customer_id = 1;
~~~

PostgreSQL sẽ không xóa khách hàng vì `fk_orders_customer ON DELETE RESTRICT`. Tương tự:

~~~sql
-- Sản phẩm 501 đang được sử dụng trong order_items.
-- Lệnh này CỐ Ý phát sinh lỗi khóa ngoại.
DELETE FROM lab_fk.products
WHERE product_id = 501;
~~~

Để thử trên terminal, hãy chạy **tách biệt khỏi chuỗi chuẩn bị có `ON_ERROR_STOP`**. Nếu đang ở transaction và gặp lỗi, transaction sẽ ở trạng thái aborted; cần `ROLLBACK` hoặc dùng `SAVEPOINT` rồi `ROLLBACK TO SAVEPOINT` trước khi tiếp tục.

Một ví dụ dùng savepoint cho thí nghiệm lỗi:

~~~sql
BEGIN;

SAVEPOINT before_attempt;

-- Dự kiến báo lỗi do RESTRICT:
DELETE FROM lab_fk.customers WHERE customer_id = 1;

-- Sau lỗi, quay lại savepoint:
ROLLBACK TO SAVEPOINT before_attempt;

SELECT customer_id, full_name
FROM lab_fk.customers
WHERE customer_id = 1;

ROLLBACK;
~~~

Trong môi trường `psql` có `ON_ERROR_STOP=1`, script sẽ dừng ở câu DELETE lỗi; hãy dùng phiên tương tác thích hợp hoặc tách kịch bản kiểm thử lỗi vào công cụ test có cơ chế bắt expected failure.

## 11. Đánh giá kết quả DELETE và UPDATE bằng bảng trạng thái

Từ bộ dữ liệu seed, mỗi thao tác dưới đây được giả định thực hiện **riêng** và không commit (để không ảnh hưởng thao tác tiếp theo):

| Thao tác ở bảng cha | Quan hệ | Quan sát dự kiến trước rollback |
| --- | --- | --- |
| Xóa `orders.order_id = 1001` | ON DELETE CASCADE tới items | Hai dòng item của đơn 1001 bị xóa |
| Xóa `employees.employee_id = 11` | ON DELETE SET NULL tới tasks | Task 701 còn, assignee_id thành NULL |
| Xóa `categories.category_id = 10` | ON DELETE SET DEFAULT tới products | Product 501 và 503 trỏ category 0 |
| Xóa `customers.customer_id = 1` | ON DELETE RESTRICT tới orders | Lỗi FK, không xóa customer |
| Xóa `products.product_id = 501` | ON DELETE RESTRICT tới items | Lỗi FK, không xóa product |
| Đổi `products.product_id 501 → 601` | ON UPDATE CASCADE tới items | Các dòng item tham chiếu ID 601 |
| Đổi `customers.customer_id 1 → 10` | ON UPDATE CASCADE tới orders | Order 1001 chuyển customer_id thành 10 |

Bảng cho thấy **cùng một lần UPDATE hoặc DELETE ở cha có thể tác động khác nhau tới các quan hệ khác nhau**. Quyết định nằm ở mỗi foreign key, không phải ở một thiết lập chung cho toàn database.

## 12. SET NULL với khóa ngoại nhiều cột: chỉ đặt một số cột về NULL

Khóa ngoại ghép thường gặp trong hệ thống có tenant. Giả sử mỗi người dùng được xác định trong phạm vi một tenant bằng cặp `(tenant_id, user_id)`. Một bài viết có thể giữ `tenant_id` khi tác giả bị xóa.

~~~sql
CREATE TABLE lab_fk.tenants (
    tenant_id bigint PRIMARY KEY,
    tenant_name text NOT NULL
);

CREATE TABLE lab_fk.tenant_users (
    tenant_id bigint NOT NULL
        REFERENCES lab_fk.tenants(tenant_id),
    user_id bigint NOT NULL,
    user_name text NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE lab_fk.posts (
    tenant_id bigint NOT NULL
        REFERENCES lab_fk.tenants(tenant_id),
    post_id bigint NOT NULL,
    author_id bigint NULL,
    title text NOT NULL,
    PRIMARY KEY (tenant_id, post_id),

    CONSTRAINT fk_posts_author
        FOREIGN KEY (tenant_id, author_id)
        REFERENCES lab_fk.tenant_users(tenant_id, user_id)
        ON DELETE SET NULL (author_id)
);
~~~

Điểm đặc biệt:

~~~sql
ON DELETE SET NULL (author_id)
~~~

Đối với PostgreSQL hỗ trợ danh sách cột ở hành động `ON DELETE SET NULL`, câu này chỉ đặt **`author_id`** thành NULL, giữ **`tenant_id`** vì `tenant_id` là một phần khóa chính của bài viết và không thể NULL.

Nếu không chỉ định danh sách cột, hành động `SET NULL` trên khóa ngoại ghép mặc định nhắm tới **mọi cột tham chiếu** trong khóa ngoại. Điều này có thể xung đột với `NOT NULL` hoặc `PRIMARY KEY` trên `tenant_id`.

### Khi nào danh sách cột đặc biệt quan trọng?

- Khóa ngoại ghép chứa cột tenant hoặc scope luôn bắt buộc.
- Chỉ một thành phần quan hệ là tùy chọn, ví dụ author, assignee, reviewer.
- Người viết muốn giữ dữ liệu trong đúng tenant sau khi xóa thực thể phụ thuộc.

**Lưu ý về cú pháp:** PostgreSQL hỗ trợ danh sách cột cho `ON DELETE SET NULL` và `ON DELETE SET DEFAULT`, nhưng không áp dụng cách liệt kê cột này cho `ON UPDATE SET NULL` / `ON UPDATE SET DEFAULT`. Nếu thiết kế phải cập nhật khóa cha, cần xem hành vi toàn bộ FK cho cập nhật.

Ví dụ trên dùng ngữ nghĩa `MATCH SIMPLE` mặc định: khi một thành phần FK là NULL, phép kiểm tra tồn tại cha cho khóa ghép có điều kiện bỏ qua. Vì `tenant_id` vẫn có khóa ngoại độc lập tới bảng `tenants`, bài viết vẫn giữ ràng buộc tenant ngay cả khi không có tác giả.

## 13. MATCH SIMPLE, MATCH FULL và tính hợp lệ của NULL

Với khóa ngoại một cột, giá trị NULL thường biểu diễn liên kết không bắt buộc. Nhưng với FK nhiều cột, vấn đề tinh tế hơn.

Giả sử:

~~~sql
FOREIGN KEY (tenant_id, author_id)
REFERENCES tenant_users (tenant_id, user_id)
~~~

Theo **`MATCH SIMPLE`** (mặc định), nếu bất kỳ cột tham chiếu nào là NULL, kiểm tra tồn tại hàng cha cho khóa ghép không bắt buộc tìm một cặp tương ứng.

Với **`MATCH FULL`**, chỉ hợp lệ khi:

- **Tất cả** cột trong khóa ngoại đều NULL; hoặc
- **Không cột nào** là NULL và toàn bộ cặp khớp hàng cha.

Một phần NULL, một phần có giá trị sẽ không được chấp nhận theo `MATCH FULL`.

| Giá trị FK ghép | MATCH SIMPLE | MATCH FULL |
| --- | --- | --- |
| (tenant=10, author=501), cha tồn tại | Hợp lệ | Hợp lệ |
| (tenant=10, author=999), cha không tồn tại | Không hợp lệ | Không hợp lệ |
| (tenant=10, author=NULL) | Hợp lệ cho FK ghép | Không hợp lệ |
| (tenant=NULL, author=NULL) | Hợp lệ cho FK ghép, nếu cột khác cho phép | Hợp lệ cho FK ghép |

Vì vậy **`ON DELETE SET NULL (author_id)`** ở ví dụ tenant kết hợp với mặc định `MATCH SIMPLE` là có chủ đích. Nếu chuyển sang `MATCH FULL`, việc chỉ đặt `author_id` NULL trong khi `tenant_id` còn giá trị sẽ xung đột ngữ nghĩa.

Điều này minh họa: chọn hành động `ON DELETE` không thể tách rời các ràng buộc `NOT NULL`, `MATCH` và khóa chính/unique trên các cột liên quan.

## 14. Hành động ở khóa ngoại ghép và ON UPDATE CASCADE

Một khóa ngoại có thể tham chiếu tổ hợp nhiều cột:

~~~sql
CREATE TABLE lab_fk.region_accounts (
    region_code text NOT NULL,
    account_no text NOT NULL,
    account_name text NOT NULL,
    PRIMARY KEY (region_code, account_no)
);

CREATE TABLE lab_fk.region_transactions (
    transaction_id bigint PRIMARY KEY,
    region_code text NOT NULL,
    account_no text NOT NULL,

    CONSTRAINT fk_transactions_account
        FOREIGN KEY (region_code, account_no)
        REFERENCES lab_fk.region_accounts(region_code, account_no)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);
~~~

Nếu đổi `region_code` hoặc `account_no` ở hàng cha, `ON UPDATE CASCADE` sẽ cập nhật **các thành phần khóa ngoại cần thiết** ở các hàng con tham chiếu.

Cần hiểu rằng một khóa ghép thể hiện định danh của hàng cha; một phần thay đổi có thể tác động nhiều bảng. Nếu `region_code` chỉ là thuộc tính nghiệp vụ dễ đổi, thiết kế `account_id bigint PRIMARY KEY` ổn định và `UNIQUE(region_code,account_no)` riêng có thể giúp tránh cascade khóa FK rộng.

Trong PostgreSQL, FK có thể tham chiếu một khóa chính, một ràng buộc unique phù hợp hoặc những cột có unique index hợp lệ theo quy tắc hệ thống. Không thể tham chiếu một tổ hợp không duy nhất rồi mong CASCADE tìm đúng một hàng cha.

## 15. Tác động của ON DELETE CASCADE lên transaction và trigger

Hành động cascade là một phần của **cùng giao dịch** đang thay đổi hàng cha:

~~~sql
BEGIN;

DELETE FROM lab_fk.orders WHERE order_id = 1002;

-- Những item của order 1002 đã bị xóa trong transaction.
SELECT * FROM lab_fk.order_items WHERE order_id = 1002;

ROLLBACK;
~~~

Sau rollback, cả đơn và các dòng item đều được phục hồi về trạng thái trước transaction.

PostgreSQL triển khai ràng buộc FK thông qua các cơ chế/trigger nội bộ, và các thay đổi hàng con do hành động tham chiếu tạo ra có thể tương tác với trigger, constraint và logic dữ liệu khác. Vì vậy:

- Nếu một cascade đi qua nhiều bảng, một constraint ở một nhánh khác có thể khiến **toàn bộ câu lệnh/transaction thất bại**.
- Trigger nghiệp vụ trên bảng con có thể chịu ảnh hưởng bởi các thay đổi do cascade, cần được tính đến trong thiết kế audit.
- Một phép xóa cha lớn có thể sinh lượng ghi/WAL và lock đáng kể trên các bảng con.
- Không nên coi cascade là cơ chế xóa bất đồng bộ, “eventually consistent” hoặc một công việc nền.

Nếu một transaction đã commit thì rollback sau đó không thể tự đảo ngược hành động. Cần backup/PITR hoặc cơ chế khôi phục riêng khi xóa nhầm dữ liệu đã commit.

## 16. TRUNCATE khác DELETE: đừng nhầm hành động lan truyền

`TRUNCATE` không thực hiện `DELETE` từng hàng theo cùng cơ chế, nên **không sử dụng các `ON DELETE` actions như một câu `DELETE` thông thường**.

Ví dụ, với bảng có hàng con tham chiếu:

~~~sql
TRUNCATE TABLE lab_fk.customers;
~~~

PostgreSQL thường từ chối truncate bảng cha khi vẫn có bảng khác tham chiếu bằng FK mà không cùng được xử lý trong tập truncate, ngay cả nếu khóa ngoại khai báo `ON DELETE CASCADE`.

Có thể thấy cú pháp:

~~~sql
-- NGUY HIỂM: chỉ minh họa; không chạy trên dữ liệu cần giữ.
TRUNCATE TABLE lab_fk.customers CASCADE;
~~~

`TRUNCATE ... CASCADE` là **cơ chế riêng**, có thể mở rộng phạm vi truncate sang **toàn bộ bảng phụ thuộc**, không phải chỉ các hàng có FK khớp với từng hàng cha. Phạm vi tác động có thể lớn hơn người viết tưởng tượng.

**Đừng dùng `TRUNCATE CASCADE` thay cho `DELETE ... ON DELETE CASCADE`** để xóa vài bản ghi hoặc xóa dữ liệu nghiệp vụ. Cần biết rõ sự khác biệt về toàn bảng, trigger và ràng buộc.

## 17. Chọn ON DELETE theo vòng đời nghiệp vụ

Một số mối quan hệ thường có lựa chọn ban đầu như sau. Đây là **gợi ý phân tích**, không phải mặc định bắt buộc:

| Quan hệ | Hướng chọn thường thấy | Vì sao |
| --- | --- | --- |
| Đơn hàng → dòng hàng | `ON DELETE CASCADE` đối với đơn nháp có thể xóa | Dòng hàng không có ý nghĩa khi không có đơn |
| Khách hàng → đơn hàng đã thanh toán | `RESTRICT` hoặc `NO ACTION` | Tránh mất lịch sử giao dịch/hóa đơn |
| Nhân viên → nhiệm vụ | `SET NULL` nếu task được phép chưa phân công | Giữ nhiệm vụ khi nhân viên rời hệ thống |
| Danh mục → sản phẩm | `SET NULL`, `SET DEFAULT` hoặc `RESTRICT` | Tùy sản phẩm được phép mất danh mục hay không |
| Sản phẩm → dòng hàng lịch sử | Thường `RESTRICT`, giữ bản ghi sản phẩm hoặc snapshot đủ dữ liệu | Đảm bảo tham chiếu và lịch sử giá |
| Nhóm quyền → liên kết user-role | Thường `CASCADE` khi xóa nhóm có chủ đích | Liên kết phân quyền không còn ý nghĩa nếu nhóm không tồn tại |
| Quốc gia/vùng mã hóa → địa chỉ | Thường `RESTRICT` | Không muốn xóa bộ mã đang được dữ liệu tham chiếu |
| Người viết → bài đăng | `SET NULL` nếu bài có thể tồn tại vô danh, hoặc `RESTRICT` theo chính sách | Ranh giới sở hữu, bảo tồn nội dung |

### Câu hỏi quan trọng trước khi chọn CASCADE

1. Hàng con có **tồn tại độc lập** sau khi cha mất không?
2. Việc xóa cha có được phép theo nghiệp vụ không, hay chỉ nên **vô hiệu hóa** cha?
3. Hàng con chứa lịch sử cần giữ để báo cáo/kiểm toán không?
4. Cascade có kéo theo những bảng khác hoặc dữ liệu bên thứ ba không?
5. Có trigger, CDC, audit log hoặc hệ thống cache phải cập nhật không?
6. Lượng dữ liệu liên kết lớn tới mức thao tác gây lock/WAL kéo dài không?

Một lựa chọn xóa nguy hiểm thường không phải vì SQL viết sai, mà vì **không xét đầy đủ vòng đời và độ lan rộng của dữ liệu**.

## 18. Chọn ON UPDATE theo chính sách khóa định danh

Trước khi chọn `ON UPDATE`, hãy hỏi: **khóa được tham chiếu có thật sự cần thay đổi không?**

Nếu khóa là `bigint GENERATED ... AS IDENTITY`, UUID, hoặc một ID kỹ thuật ổn định, thông thường ứng dụng **không cần đổi khóa chính**. Khi đó `NO ACTION`/`RESTRICT` đã đủ ngăn thay đổi làm mất tính toàn vẹn tham chiếu.

Nếu khóa dùng mã nghiệp vụ có thể đổi, ví dụ mã sản phẩm, mã phòng ban hoặc mã vùng, `ON UPDATE CASCADE` có thể giữ các hàng con tham chiếu đúng đối tượng sau khi đổi mã.

~~~sql
CREATE TABLE lab_fk.skus (
    sku text PRIMARY KEY,
    label text NOT NULL
);

CREATE TABLE lab_fk.sku_inventory (
    warehouse_id integer NOT NULL,
    sku text NOT NULL REFERENCES lab_fk.skus(sku)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    stock_count integer NOT NULL CHECK (stock_count >= 0),
    PRIMARY KEY (warehouse_id, sku)
);
~~~

Tuy vậy, nếu mã SKU được dùng trong API ngoài, hợp đồng, cache hoặc message queue, cascade trong **một database** chỉ cập nhật FK mà PostgreSQL quản lý. Nó **không tự cập nhật tất cả file, thông điệp và hệ thống bên ngoài**.

Một thiết kế thay thế:

~~~sql
CREATE TABLE lab_fk.stable_products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    name text NOT NULL
);
~~~

Các bảng con tham chiếu `product_id` ổn định; khi mã `sku` đổi, không cần cascade các FK nội bộ. Đây thường là lựa chọn đơn giản hơn cho hệ thống có mã nghiệp vụ hay đổi.

## 19. Soft delete không kích hoạt ON DELETE CASCADE

Nhiều ứng dụng không xóa vật lý hàng cha mà chỉ đánh dấu:

~~~sql
UPDATE lab_fk.customers
SET full_name = full_name
WHERE customer_id = 1;
~~~

Ví dụ trên là cập nhật không đổi khóa, nên không kích hoạt `ON UPDATE` FK. Tương tự, một hệ thống có cột:

~~~sql
deleted_at timestamptz
~~~

khi chạy:

~~~sql
UPDATE some_table
SET deleted_at = now()
WHERE id = 1;
~~~

thì đây là **UPDATE một thuộc tính không phải khóa tham chiếu**, không phải DELETE. `ON DELETE CASCADE` không tự xóa các hàng con.

Nếu dùng soft deletion, cần tự định nghĩa:

- Hàng con có được hiển thị khi cha đã soft-delete không?
- Có chặn tạo liên kết mới tới cha đã soft-delete không?
- Query và index nào loại bản ghi đã xóa?
- Khi nào xóa vật lý, và hành vi FK lúc purge là gì?
- Cách bảo đảm dữ liệu không mồ côi về mặt nghiệp vụ dù FK vẫn hợp lệ?

Không dùng `ON DELETE` làm giải pháp thay thế cho chính sách soft delete. Đây là hai tầng hành vi khác nhau.

## 20. Tối ưu index phía bảng con

PostgreSQL tạo index phù hợp với `PRIMARY KEY` và `UNIQUE` ở bảng cha, nhưng **không tự tạo index trên mọi cột FK ở bảng con**.

Giả sử có một khách hàng với hàng triệu đơn. Khi xóa hoặc đổi `customers.customer_id`, PostgreSQL cần xác định các hàng `orders` nào đang tham chiếu khóa đó. Nếu không có index phù hợp ở `orders.customer_id`, việc tìm hàng con có thể trở nên tốn kém.

Trong lab có thể thêm:

~~~sql
CREATE INDEX idx_lab_fk_orders_customer
    ON lab_fk.orders(customer_id);

CREATE INDEX idx_lab_fk_products_category
    ON lab_fk.products(category_id);

CREATE INDEX idx_lab_fk_tasks_assignee
    ON lab_fk.tasks(assignee_id);

CREATE INDEX idx_lab_fk_items_product
    ON lab_fk.order_items(product_id);
~~~

`order_items` có primary key `(order_id,product_id)` nên index của khóa chính đã hỗ trợ nhiều truy vấn lọc theo **`order_id` đứng đầu**. Tuy nhiên truy vấn lọc riêng theo `product_id` thường cần cân nhắc index riêng.

### Khi nào index là cần thiết?

Không phải mọi FK đều bắt buộc có một index riêng. Hãy xem:

- Số lượng hàng cha/con và độ chọn lọc của khóa.
- Tần suất xóa/sửa khóa ở bảng cha.
- Truy vấn lọc/JOIN theo FK ở bảng con.
- Chi phí duy trì index khi ghi dữ liệu.
- Các index tổ hợp hiện có đã hỗ trợ đường truy cập hay chưa.

Dùng `EXPLAIN` hoặc `EXPLAIN (ANALYZE, BUFFERS)` trên truy vấn đọc thích hợp để quan sát kế hoạch. `EXPLAIN ANALYZE` thực sự thực thi câu SQL; không tùy tiện chạy trên câu `DELETE`/`UPDATE` dữ liệu production.

## 21. Lock, hiệu năng và phạm vi giao dịch

Các hành động tham chiếu không miễn phí. Khi xóa hoặc đổi khóa cha:

- PostgreSQL phải kiểm tra/tìm các hàng con liên quan.
- Với `CASCADE`, `SET NULL`, `SET DEFAULT`, nó có thể phải cập nhật hoặc xóa nhiều hàng con.
- Các cập nhật đó tạo WAL, ảnh hưởng index, trigger và MVCC.
- Một giao dịch dài có thể giữ khóa lâu, làm tăng lock waits ở phiên khác.
- Nếu hai phiên cùng thao tác trên các bảng cha/con theo thứ tự khác nhau, có thể gặp deadlock.

Ví dụ một lệnh:

~~~sql
DELETE FROM lab_fk.categories
WHERE category_id = 10;
~~~

nếu danh mục có hàng triệu sản phẩm, `SET DEFAULT` phải cập nhật rất nhiều dòng sản phẩm. Không thể mặc định thao tác hoàn tất nhanh chỉ vì câu SQL rất ngắn.

### Cách tiếp cận an toàn với dữ liệu lớn

1. Đếm hoặc ước lượng số hàng con liên quan.
2. Kiểm tra index trên FK.
3. Xác định trigger và bảng phụ thuộc tiếp theo.
4. Chọn thời điểm thực hiện phù hợp, hoặc thiết kế migration/purge theo batch nếu nghiệp vụ cho phép.
5. Theo dõi lock, WAL, I/O và khả năng replication bắt kịp.
6. Có backup, kế hoạch khôi phục và điểm dừng rõ ràng trước khi thay đổi dữ liệu quan trọng.

**Không tự giả định có thể thay một cascade rất lớn bằng vài lệnh DELETE batch mà không thay đổi ngữ nghĩa nghiệp vụ.** Nếu dọn dẹp theo batch, phải tự duy trì tính nhất quán, xử lý bản ghi mới phát sinh đồng thời và quy tắc cuối cùng của khóa ngoại.

## 22. Đọc ràng buộc đang có trong PostgreSQL

Trước khi sửa hành vi `ON DELETE`/`ON UPDATE`, hãy đọc constraint thực tế thay vì chỉ tin vào mô tả trong code.

Trong `psql`:

~~~text
\d lab_fk.orders
\d lab_fk.order_items
\d lab_fk.products
~~~

Lệnh `\d` hiển thị thông tin bảng, index và foreign keys. Đây là meta-command của `psql`, không phải SQL chuẩn chạy qua JDBC.

### Dùng pg_constraint

~~~sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    c.conname AS fk_name,
    pg_get_constraintdef(c.oid) AS fk_definition
FROM pg_constraint AS c
JOIN pg_class AS t
    ON t.oid = c.conrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'lab_fk'
  AND c.contype = 'f'
ORDER BY t.relname, c.conname;
~~~

`pg_get_constraintdef` trả định nghĩa ràng buộc theo PostgreSQL, ví dụ:

~~~text
FOREIGN KEY (customer_id) REFERENCES lab_fk.customers(customer_id)
ON UPDATE CASCADE ON DELETE RESTRICT
~~~

Để xem mã hành động được lưu trong catalog:

~~~sql
SELECT
    conname,
    confdeltype,
    confupdtype,
    condeferrable,
    condeferred
FROM pg_constraint
WHERE contype = 'f'
  AND connamespace = 'lab_fk'::regnamespace
ORDER BY conname;
~~~

Trong `pg_constraint`, các mã hành động thường là:

| Mã | Hành động |
| --- | --- |
| `a` | NO ACTION |
| `r` | RESTRICT |
| `c` | CASCADE |
| `n` | SET NULL |
| `d` | SET DEFAULT |

`condeferrable` thể hiện FK có thể được trì hoãn kiểm tra hay không; `condeferred` thể hiện chế độ ban đầu là deferred hay immediate. Không suy từ mã hành động mà bỏ qua các thuộc tính khác của constraint.

## 23. Thay đổi ON DELETE hoặc ON UPDATE của FK đang tồn tại

Không nên giả định có một câu `ALTER FOREIGN KEY ... ON DELETE ...` trực tiếp để đổi mọi hành động. Thông thường, muốn đổi từ `NO ACTION` sang `CASCADE` hoặc `SET NULL`, cần **xóa và tạo lại foreign key constraint** với định nghĩa mới.

Ví dụ thay hành động trên `lab_fk.tasks` từ `SET NULL` sang `RESTRICT`:

~~~sql
-- CHỈ minh họa trong schema lab, không chạy vào production
-- nếu chưa có kế hoạch migration và đánh giá dữ liệu.
BEGIN;

ALTER TABLE lab_fk.tasks
    DROP CONSTRAINT fk_tasks_assignee;

ALTER TABLE lab_fk.tasks
    ADD CONSTRAINT fk_tasks_assignee
    FOREIGN KEY (assignee_id)
    REFERENCES lab_fk.employees(employee_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

COMMIT;
~~~

Sau thay đổi, việc xóa nhân viên có task tham chiếu sẽ bị từ chối, thay vì bỏ gán người phụ trách.

**Điểm cần xem trước khi làm thật:**

- Constraint mới có hợp lệ với dữ liệu hiện có không?
- Ứng dụng có phụ thuộc vào hành động cũ không?
- Có job đang xóa cha hoặc sửa khóa cùng thời điểm không?
- Các trigger/audit/CDC có giả định về hành vi lan truyền không?
- Việc drop/add constraint cần lock nào và bao lâu ở bảng lớn?
- Có rollback/forward-fix và giám sát migration không?

Đổi một FK từ `RESTRICT` sang `CASCADE` là **thay đổi hành vi nghiệp vụ**, có thể khiến những thao tác xóa trước đây thất bại giờ trở thành thao tác xóa dữ liệu dây chuyền. Phải review tương tự một migration quan trọng, không chỉ như sửa cú pháp.

### Thêm FK vào bảng lớn bằng NOT VALID

PostgreSQL có thể hỗ trợ thêm ràng buộc FK mà chưa quét toàn bộ dữ liệu cũ ngay tại bước tạo, rồi kiểm tra riêng:

~~~sql
-- Ví dụ cú pháp khi bổ sung một FK mới:
ALTER TABLE lab_fk.tasks
    ADD CONSTRAINT fk_tasks_assignee_new
    FOREIGN KEY (assignee_id)
    REFERENCES lab_fk.employees(employee_id)
    ON DELETE SET NULL
    ON UPDATE CASCADE
    NOT VALID;
~~~

Tiếp theo:

~~~sql
ALTER TABLE lab_fk.tasks
    VALIDATE CONSTRAINT fk_tasks_assignee_new;
~~~

`NOT VALID` không có nghĩa cho phép mọi dữ liệu mới tùy ý vi phạm FK: nó chủ yếu cho phép trì hoãn bước **xác minh dữ liệu đã có trước khi thêm**. Các thay đổi mới vẫn phải đáp ứng ràng buộc theo cơ chế PostgreSQL.

Ví dụ trên tạo **một constraint bổ sung** tên `fk_tasks_assignee_new`, không tự thay thế constraint cũ. Trong migration thực tế cần chọn đúng thứ tự drop/add, quyền, mức lock và xử lý validation; không thêm trùng chỉ để “thử xem”. Việc validation ở bảng lớn vẫn tiêu thụ tài nguyên và cần lên lịch phù hợp.

## 24. Các lỗi thường gặp khi dùng hành động lan truyền

### 24.1. Nhầm CASCADE là hành vi mặc định

Mặc định là `NO ACTION`. PostgreSQL không xóa hàng con chỉ vì có foreign key.

### 24.2. Coi NO ACTION và RESTRICT hoàn toàn giống nhau

Chúng thường có cùng kết quả trong DELETE đơn giản, nhưng `NO ACTION` có thể hoãn kiểm tra với constraint deferrable, còn `RESTRICT` không được trì hoãn như vậy.

### 24.3. Dùng ON DELETE CASCADE với dữ liệu cần giữ lâu dài

Xóa customer có thể làm mất đơn hoặc hóa đơn nếu cấu hình cascade thiếu thận trọng. Cần mô hình lưu trữ/soft delete và chính sách dữ liệu rõ ràng.

### 24.4. Dùng SET NULL trên FK NOT NULL

Nếu hành động cố đặt FK thành NULL, constraint NOT NULL sẽ từ chối. Chọn nullability nhất quán với vòng đời quan hệ.

### 24.5. Dùng SET DEFAULT nhưng default không tham chiếu hàng cha nào

Giá trị mặc định vẫn phải thỏa foreign key. `SET DEFAULT` không tự tạo cha hoặc bỏ qua constraint.

### 24.6. Cho rằng ON UPDATE CASCADE cập nhật mọi thuộc tính

Nó xử lý **giá trị khóa được tham chiếu**, không cập nhật tùy ý tên, địa chỉ, trạng thái hay mọi cột có tên giống ở bảng con.

### 24.7. Coi foreign key là cách đảm bảo không có bất biến nghiệp vụ bị vi phạm

FK kiểm tra tham chiếu, nhưng không tự bảo đảm những điều kiện như “chỉ đơn nháp được xóa”, “hóa đơn đã xuất không được hủy” hoặc “nhân viên chỉ thuộc đúng một phòng ban đang hoạt động”. Các quy tắc đó cần thêm constraint, transaction hoặc logic thích hợp.

### 24.8. Quên bảng con không có index FK

Truy vấn và thao tác cha có thể chậm khi số hàng lớn. Kiểm tra index phía con, nhất là cột được dùng để tìm các bản ghi tham chiếu.

### 24.9. Nhầm TRUNCATE CASCADE với ON DELETE CASCADE

`TRUNCATE CASCADE` có thể xóa toàn bộ những bảng phụ thuộc, không chạy cùng logic theo từng hàng như `DELETE`.

### 24.10. Quên ROLLBACK khi đang làm bài test

Một ví dụ `DELETE` thành công và commit sẽ làm dữ liệu mẫu thay đổi, khiến bài tiếp theo trả kết quả khác. Dùng database riêng và bọc thao tác thử trong transaction rồi rollback.

### 24.11. Không xử lý transaction aborted sau lỗi FK

Trong transaction, một lệnh vi phạm constraint làm transaction ở trạng thái lỗi; cần `ROLLBACK` hoặc quay lại `SAVEPOINT` trước khi thực hiện lệnh tiếp. Đừng chạy tiếp và hiểu các lỗi sau là do PostgreSQL “không còn nhận SQL”.

### 24.12. Chỉ xem bảng cha mà không xem đồ thị phụ thuộc

Một cascade có thể đi tiếp qua bảng con là cha của các bảng khác, hoặc bị một FK ở nhánh khác chặn. Cần khảo sát toàn bộ constraint.

### 24.13. Đặt ON UPDATE CASCADE để che thiết kế khóa không ổn định

Nếu khóa nghiệp vụ liên tục đổi, có thể tốt hơn khi dùng một khóa nội bộ bền vững và giữ mã nghiệp vụ ở cột unique riêng.

### 24.14. Chỉ cấp quyền UI mà quên hành vi ở database

Một thao tác xóa qua SQL, job nền hoặc công cụ quản trị vẫn chịu hành động FK. Quy tắc vận hành không chỉ nằm ở nút “Delete” của giao diện.

## 25. Bài tập ôn tập có đáp án

Các bài sau dùng schema `lab_fk` được tạo và seed ở mục 10, giả định chưa commit những thay đổi từ các ví dụ thử nghiệm.

### Bài 1: Tại sao xóa khách hàng An thất bại?

~~~sql
DELETE FROM lab_fk.customers WHERE customer_id = 1;
~~~

**Đáp án:** Đơn 1001 tham chiếu khách hàng 1 và FK `fk_orders_customer` dùng `ON DELETE RESTRICT`. PostgreSQL chặn xóa, báo lỗi FK.

### Bài 2: Xóa đơn 1001 thì còn những item nào?

~~~sql
BEGIN;
DELETE FROM lab_fk.orders WHERE order_id = 1001;

SELECT order_id, product_id
FROM lab_fk.order_items
ORDER BY order_id, product_id;
ROLLBACK;
~~~

**Đáp án:** Trong transaction, chỉ còn item của đơn 1002 (sản phẩm 501). Hai item thuộc đơn 1001 bị xóa theo `ON DELETE CASCADE`. Sau rollback, dữ liệu ban đầu trở lại.

### Bài 3: Xóa nhân viên Lan có xóa nhiệm vụ không?

~~~sql
BEGIN;
DELETE FROM lab_fk.employees WHERE employee_id = 11;

SELECT task_id, assignee_id
FROM lab_fk.tasks
ORDER BY task_id;
ROLLBACK;
~~~

**Đáp án:** Không. Task 701 còn tồn tại nhưng `assignee_id = NULL` vì `ON DELETE SET NULL`; task 702 vẫn `NULL`.

### Bài 4: Xóa danh mục 10 làm gì với sản phẩm 501?

~~~sql
BEGIN;
DELETE FROM lab_fk.categories WHERE category_id = 10;

SELECT product_id, category_id
FROM lab_fk.products
ORDER BY product_id;
ROLLBACK;
~~~

**Đáp án:** Product 501 và 503 chuyển `category_id` về 0. Đây là giá trị `DEFAULT` hợp lệ vì danh mục 0 tồn tại.

### Bài 5: Đổi mã sản phẩm 501 thành 601

~~~sql
BEGIN;
UPDATE lab_fk.products
SET product_id = 601
WHERE product_id = 501;

SELECT order_id, product_id
FROM lab_fk.order_items
ORDER BY order_id, product_id;
ROLLBACK;
~~~

**Đáp án:** Các dòng item tham chiếu sản phẩm 501 đổi sang 601 nhờ `ON UPDATE CASCADE`. Sau rollback, quay về 501.

### Bài 6: Thay NO ACTION bằng RESTRICT có phải luôn tương đương?

**Đáp án:** Không. Khi muốn sửa khóa cha và con theo nhiều bước trong một transaction, FK `NO ACTION DEFERRABLE` có thể cho hoãn kiểm tra tới commit; `RESTRICT` không hỗ trợ hoãn hành động tương ứng.

### Bài 7: Có nên để ON DELETE CASCADE cho customers → invoices không?

**Đáp án gợi ý:** Thường phải rất thận trọng vì hóa đơn/chứng từ có thể phải giữ lâu dài. Có thể dùng `RESTRICT`/`NO ACTION`, vô hiệu hóa khách hàng và chính sách lưu/ẩn danh phù hợp. Không có một hành động mặc định đúng cho mọi luật và nghiệp vụ.

### Bài 8: Vì sao SET NULL thất bại trên cột bắt buộc?

**Đáp án:** `ON DELETE SET NULL` cố ghi NULL vào FK, trong khi `NOT NULL` từ chối. Thiết kế cần cho phép con không có cha hoặc chọn hành động khác.

### Bài 9: Vì sao SET DEFAULT 0 có thể thất bại?

**Đáp án:** Nếu bảng cha không có khóa 0 (hoặc có constraint khác không thỏa), giá trị được ghi ở con vi phạm FK. Cần hàng mặc định thực sự và được bảo vệ theo nghiệp vụ.

### Bài 10: Hành vi khi dùng TRUNCATE?

**Đáp án:** `TRUNCATE` không diễn giải `ON DELETE CASCADE` theo từng hàng. Nó có cơ chế kiểm tra và `TRUNCATE ... CASCADE` riêng, có thể ảnh hưởng toàn bộ bảng phụ thuộc.

### Bài 11: Có nên tạo index trên orders.customer_id?

**Đáp án:** Nên cân nhắc khi lọc đơn theo khách hàng hoặc khi xóa/sửa khóa khách hàng trên bảng lớn. PostgreSQL không mặc định tạo index trên mọi FK phía con. Nhưng chỉ mục cụ thể phụ thuộc workload và các index đã có.

### Bài 12: Thiết kế cho mã phòng ban đổi thường xuyên

**Đáp án gợi ý:** Nếu `department_code` là mã nghiệp vụ có thể đổi, có thể dùng `department_id` ổn định làm PK và để `department_code UNIQUE`. Các nhân viên tham chiếu `department_id` nên không cần cập nhật FK mỗi lần mã đổi.

## 26. Quy trình chọn ON DELETE / ON UPDATE

Khi thiết kế một foreign key mới, có thể dùng checklist ra quyết định sau:

1. **Xác định quan hệ thật:** cha và con là gì? Bản ghi con có thể tồn tại độc lập không?
2. **Tìm điều kiện tối thiểu:** con có bắt buộc có cha không? FK nên `NOT NULL` hay nullable?
3. **Xác định thao tác xóa được phép:** xóa cha có hợp lệ nghiệp vụ không? Có cần giữ lịch sử?
4. **Chọn hành động xóa:** chặn (`NO ACTION`/`RESTRICT`), xóa theo (`CASCADE`), bỏ liên kết (`SET NULL`), chuyển sang cha mặc định (`SET DEFAULT`).
5. **Xác định khóa cha có thay đổi không:** nếu bất biến, thường không cần cascade; nếu có thể đổi, cân nhắc `ON UPDATE CASCADE` hoặc khóa kỹ thuật ổn định.
6. **Đối chiếu ràng buộc:** `NOT NULL`, `DEFAULT`, composite FK, `MATCH` và uniqueness có tương thích với hành động không?
7. **Xem khả năng trì hoãn:** cần sửa nhiều khóa trong một transaction không? Nếu có, đánh giá `NO ACTION DEFERRABLE`.
8. **Khảo sát đồ thị phụ thuộc:** một hành động có kéo theo các bảng khác hoặc trigger/CDC/audit không?
9. **Đánh giá tải:** số hàng con, index FK, khóa, WAL và replication có chấp nhận được không?
10. **Thử nghiệm trên database lab:** dùng transaction và rollback, kiểm tra cả thao tác hợp lệ lẫn thao tác dự kiến bị từ chối.
11. **Ghi lại trong migration/runbook:** tên constraint, lý do chọn hành động và cách thay đổi/rollback nếu nghiệp vụ đổi.

Nếu không có một lý do nghiệp vụ rõ ràng để tự xóa hoặc sửa hàng con, **đừng chọn `CASCADE` chỉ để giảm số dòng SQL**. Trước hết hãy mô tả chính xác trạng thái dữ liệu nào được phép tồn tại sau khi cha thay đổi.

## 27. Tổng kết

`ON DELETE` và `ON UPDATE` là cách PostgreSQL thực thi một phần **quy tắc vòng đời quan hệ** ngay tại database.

- **`NO ACTION`:** mặc định; ngăn trạng thái FK không hợp lệ, có thể hoãn kiểm tra khi constraint `DEFERRABLE`.
- **`RESTRICT`:** chặn thao tác cha đang bị tham chiếu, không cho trì hoãn hành động như `NO ACTION`.
- **`CASCADE`:** xóa hàng con hoặc cập nhật giá trị FK theo thay đổi khóa cha.
- **`SET NULL`:** giữ hàng con và bỏ liên kết, chỉ hợp lý khi các cột/ràng buộc cho phép.
- **`SET DEFAULT`:** chuyển FK về giá trị mặc định **vẫn phải hợp lệ** theo khóa ngoại.

Đối với `ON DELETE`, quyết định thường xoay quanh việc **dữ liệu con có cần sống cùng cha hay cần bảo tồn độc lập**. Đối với `ON UPDATE`, quyết định xoay quanh **khóa tham chiếu có được phép đổi và có cần giữ nguyên liên kết**.

Thiết kế tốt luôn phối hợp hành động FK với `NOT NULL`, `UNIQUE`, transaction, index, quyền và quy tắc nghiệp vụ. Nhờ đó, ngay cả khi nhiều ứng dụng cùng thao tác hoặc có lỗi trong luồng ghi, PostgreSQL vẫn duy trì được những bất biến tham chiếu mà hệ thống đã chủ động định nghĩa.
