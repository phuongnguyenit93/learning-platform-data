# ON DELETE, ON UPDATE và lựa chọn hành động tham chiếu

Trong cơ sở dữ liệu quan hệ, **khóa ngoại** (*foreign key*, FK) bảo vệ mối quan hệ giữa hàng ở bảng con và hàng được tham chiếu ở bảng cha. Tuy nhiên, sau khi tạo quan hệ, ta vẫn phải quyết định điều gì xảy ra khi **hàng cha bị xóa** hoặc **giá trị khóa được tham chiếu bị cập nhật**. SQL cung cấp các điều khoản `ON DELETE` và `ON UPDATE` để diễn đạt các quyết định này ở mức cơ sở dữ liệu.

Chọn hành động tham chiếu đúng giúp ngăn bản ghi mồ côi, tránh xóa dữ liệu ngoài ý muốn và giữ nhất quán dù thao tác được thực hiện từ ứng dụng, tác vụ quản trị hay một chương trình tích hợp khác. Mỗi hành động cần phản ánh **vòng đời nghiệp vụ** của dữ liệu; không có lựa chọn duy nhất phù hợp cho mọi khóa ngoại.

> Bài học sử dụng PostgreSQL cho các ví dụ SQL chính. Các hệ quản trị như MySQL, SQL Server, Oracle và SQLite khác nhau về hành động hỗ trợ, thời điểm kiểm tra ràng buộc và cú pháp. Phần so sánh cuối bài chỉ ra các khác biệt cần lưu ý.

## 1. Khóa ngoại bảo vệ quan hệ gì?

Giả sử có hai bảng:

```text
departments (bảng cha)                 employees (bảng con)
+---------------+--------------+       +-------------+---------------+
| department_id | name         |       | employee_id | department_id |
+---------------+--------------+       +-------------+---------------+
| 10            | Sales        |<------| 1           | 10            |
| 20            | Engineering  |<------| 2           | 20            |
+---------------+--------------+       | 3           | NULL          |
                                       +-------------+---------------+
```

Trong mô hình này, `departments.department_id` là khóa chính (hoặc có thể là khóa duy nhất phù hợp), còn `employees.department_id` là khóa ngoại. Nếu giá trị khóa ngoại khác `NULL`, nó phải trỏ tới một khóa được tham chiếu hợp lệ theo quy tắc của ràng buộc.

Đây là hai tình huống khác nhau:

1. **Thao tác ở bảng con:** chèn nhân viên với `department_id = 99` dù phòng ban 99 chưa tồn tại. Khóa ngoại thông thường ngăn giá trị tham chiếu không hợp lệ. Các điều khoản `ON DELETE` và `ON UPDATE` không biến một khóa ngoại sai thành hợp lệ.
2. **Thao tác ở bảng cha:** xóa phòng ban 10 hoặc đổi `department_id` từ 20 thành 200. Khi đó DBMS phải xác định cách xử lý các nhân viên đang tham chiếu giá trị cũ. Đây chính là vai trò của `ON DELETE` và `ON UPDATE`.

**Góc nhìn luôn từ hàng cha được tham chiếu:** `ON DELETE` nói về việc *xóa hàng cha*; `ON UPDATE` nói về việc *đổi giá trị khóa cha*. Chúng không phải lệnh tự động xóa hoặc cập nhật hàng con bất cứ khi nào bảng con thay đổi.

Một quan hệ không nhất thiết có tên cột giống nhau ở hai phía; điều quan trọng là danh sách cột trong `FOREIGN KEY` tương ứng đúng với danh sách cột được tham chiếu và có kiểu dữ liệu tương thích theo DBMS.

## 2. Cú pháp cơ bản

Cú pháp khai báo khóa ngoại cấp bảng:

```sql
CREATE TABLE parent_table (
    id BIGINT PRIMARY KEY
);

CREATE TABLE child_table (
    id BIGINT PRIMARY KEY,
    parent_id BIGINT,
    CONSTRAINT fk_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES parent_table (id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);
```

Trong ví dụ:

- Nếu hàng `parent_table` bị **xóa**, các hàng con tham chiếu nó được đặt `parent_id = NULL`.
- Nếu khóa `parent_table.id` được **đổi giá trị**, các hàng con tham chiếu được cập nhật `parent_id` sang giá trị mới.
- `parent_id` phải cho phép `NULL` để hành động `SET NULL` thực hiện thành công.
- Nếu một hàng con chèn hoặc cập nhật `parent_id` thành giá trị không có ở bảng cha, FK vẫn từ chối.

Một số DBMS cho phép viết ràng buộc ngay tại định nghĩa cột khi FK chỉ có một cột:

```sql
-- Ví dụ PostgreSQL
CREATE TABLE child_short (
    id BIGINT PRIMARY KEY,
    parent_id BIGINT REFERENCES parent_table(id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);
```

Đặt tên ràng buộc rõ ràng bằng `CONSTRAINT fk_...` thường hữu ích khi cần đọc lỗi, đổi quy tắc hoặc viết migration.

## 3. Năm hành động tham chiếu phổ biến

Các hành động thường gặp trong SQL:

| Hành động | Khi xóa/đổi khóa của hàng cha | Điều kiện và ý nghĩa |
|---|---|---|
| `NO ACTION` | Không tự sửa dữ liệu con; nếu còn tham chiếu vi phạm khi kiểm tra ràng buộc, thao tác không được chấp nhận | Thường là **mặc định** khi không ghi hành động; thời điểm kiểm tra có thể được hoãn ở DBMS hỗ trợ ràng buộc trì hoãn |
| `RESTRICT` | Ngăn xóa/đổi khóa cha nếu còn hàng con tham chiếu | Nhấn mạnh không cho phép thao tác khi vẫn có tham chiếu; trong PostgreSQL khác `NO ACTION` ở khả năng trì hoãn kiểm tra |
| `CASCADE` | Xóa hàng con khi xóa cha; cập nhật khóa ngoại ở hàng con khi khóa cha đổi | Phù hợp quan hệ phụ thuộc vòng đời hoặc khi cần đồng bộ khóa |
| `SET NULL` | Đặt cột khóa ngoại liên quan ở hàng con thành `NULL` | Cột phải cho phép `NULL`; quan hệ được ngắt nhưng hàng con vẫn còn |
| `SET DEFAULT` | Đặt cột khóa ngoại ở hàng con về giá trị mặc định đã định nghĩa | Giá trị mặc định vẫn phải hợp lệ theo FK, trừ khi là `NULL` được cho phép; cần một quy tắc “giá trị mặc định” thực sự có nghĩa |

Cùng một hành động có thể mang ý nghĩa rất khác trong hai điều khoản. Ví dụ `ON DELETE CASCADE` là **xóa hàng con**, còn `ON UPDATE CASCADE` là **đổi giá trị FK ở hàng con**, không xóa hàng con.

Ta có thể kết hợp các quy tắc khác nhau cho cùng một quan hệ, chẳng hạn `ON DELETE RESTRICT ON UPDATE CASCADE`. Lựa chọn nên dựa trên nghiệp vụ đối với hai sự kiện độc lập: **xóa cha** và **đổi khóa cha**.

## 4. `ON DELETE RESTRICT` và `ON DELETE NO ACTION`: chặn xóa khi còn tham chiếu

Với các dữ liệu cần giữ để đối soát, lưu lịch sử hoặc bảo vệ thông tin, việc xóa hàng cha khi hàng con còn tồn tại thường là sai. Ví dụ không nên cho xóa một tài khoản khách hàng đang có hóa đơn, trừ khi đã có quy trình lưu trữ hoặc chuyển giao thích hợp.

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE invoices (
    invoice_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL,
    CONSTRAINT fk_invoice_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
);
```

Giả sử `customers` có `customer_id = 10` và `invoices` chứa một hóa đơn tham chiếu 10:

```sql
DELETE FROM customers WHERE customer_id = 10;
```

DBMS từ chối thao tác vì còn hàng con. Chỉ khi xử lý tham chiếu theo đúng nghiệp vụ (ví dụ lưu trữ, tái gán hoặc xóa các bản ghi con hợp lệ) mới có thể xóa cha. Không nên bỏ ràng buộc để “xóa cho nhanh”.

### Phân biệt `NO ACTION` và `RESTRICT`

Trong **PostgreSQL**, hai hành động đều không tự thay đổi hàng con, nhưng khác nhau về **thời điểm kiểm tra**:

- `NO ACTION` là mặc định và có thể được kiểm tra vào thời điểm muộn hơn nếu FK được khai báo `DEFERRABLE` và đang ở chế độ trì hoãn.
- `RESTRICT` ngăn thay đổi đang bị tham chiếu mà không cho phép trì hoãn hành động này để sửa quan hệ ở bước sau.
- Nếu ràng buộc được kiểm tra ngay, kết quả quan sát thường giống nhau: thao tác làm phát sinh tham chiếu sai bị từ chối.

Ví dụ PostgreSQL cho phép thay đổi tạm thời thứ tự thao tác bên trong **một giao dịch** khi FK dùng `NO ACTION DEFERRABLE INITIALLY DEFERRED`:

```sql
CREATE TABLE deferred_parent (
    id INTEGER PRIMARY KEY
);

CREATE TABLE deferred_child (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL,
    CONSTRAINT fk_deferred_child
        FOREIGN KEY (parent_id)
        REFERENCES deferred_parent(id)
        ON DELETE NO ACTION
        DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO deferred_parent (id) VALUES (1);
INSERT INTO deferred_child (id, parent_id) VALUES (101, 1);

BEGIN;

-- Tạm thời còn tham chiếu 1 trong cùng giao dịch.
DELETE FROM deferred_parent WHERE id = 1;

-- Xử lý hàng con trước khi giao dịch kết thúc.
DELETE FROM deferred_child WHERE parent_id = 1;

COMMIT;
```

Khi `COMMIT`, không còn hàng con trỏ tới cha đã xóa nên trạng thái cuối hợp lệ. Nếu bỏ câu lệnh xóa hàng con, `COMMIT` sẽ thất bại vì còn tham chiếu sai. Cơ chế này không có nghĩa là DBMS cho phép **lưu vĩnh viễn** dữ liệu mồ côi.

**Không khái quát hóa điểm khác biệt này cho mọi DBMS.** Chẳng hạn MySQL InnoDB xử lý `NO ACTION` về thực tế như `RESTRICT` vì không hỗ trợ kiểm tra FK trì hoãn theo cách PostgreSQL; một số hệ khác có cơ chế deferred constraints hoặc giới hạn riêng.

## 5. `ON DELETE CASCADE`: hàng con biến mất cùng hàng cha

`CASCADE` hữu ích khi hàng con **chỉ có ý nghĩa khi cha tồn tại**, chẳng hạn các dòng hàng của một giỏ hàng tạm hoặc các bản ghi cấu hình phụ thuộc một đối tượng. Khi xóa cha, DBMS tự xóa các hàng con tham chiếu.

```sql
CREATE TABLE shopping_carts (
    cart_id BIGINT PRIMARY KEY,
    owner_id BIGINT NOT NULL
);

CREATE TABLE cart_items (
    cart_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (cart_id, product_id),
    CONSTRAINT fk_cart_items_cart
        FOREIGN KEY (cart_id)
        REFERENCES shopping_carts(cart_id)
        ON DELETE CASCADE
);
```

Giả sử có giỏ `cart_id = 900` với hai dòng hàng:

```sql
INSERT INTO shopping_carts (cart_id, owner_id)
VALUES (900, 101);

INSERT INTO cart_items (cart_id, product_id, quantity)
VALUES (900, 1, 2), (900, 2, 1);

DELETE FROM shopping_carts WHERE cart_id = 900;
```

Kết quả: giỏ hàng 900 và **cả hai dòng `cart_items`** của giỏ bị xóa. Một lần xóa bảng cha có thể tác động nhiều dòng hoặc lan qua nhiều cấp FK nếu các bảng con cũng có `ON DELETE CASCADE`.

```text
shopping_carts [900]  --DELETE-->
      │
      └── ON DELETE CASCADE
             ├── cart_items [900, 1]  --bị xóa-->
             └── cart_items [900, 2]  --bị xóa-->
```

### Khi nào không nên dùng xóa dây chuyền?

- **Đơn hàng đã thanh toán** và dòng đơn hàng thường cần lưu để đối soát, kiểm toán hoặc hoàn tiền. Không nên suy ra “đơn hàng là cha nên xóa đơn hàng thì xóa hết dòng” khi nghiệp vụ yêu cầu lưu lịch sử.
- **Khách hàng và hóa đơn** không phải quan hệ sở hữu vòng đời theo nghĩa mọi hóa đơn phải bị xóa khi xóa khách hàng. Có thể cần ẩn danh dữ liệu cá nhân, giữ dữ liệu pháp lý, hoặc chặn xóa.
- **Nhật ký/audit** có thể cần giữ ngay cả khi đối tượng nguồn đã bị xóa. Thiết kế giữ bản chụp cần đủ dữ liệu để giải thích sự kiện mà không dựa vào hàng cha tồn tại mãi.

Cascading delete là thao tác dữ liệu thực sự; trong các DBMS có trigger trên bảng con, việc xóa do cascade có thể kích hoạt trigger liên quan. Cần hiểu số hàng ảnh hưởng, thời gian khóa, tác động giao dịch và cách ứng dụng ghi log/cập nhật cache.

**Phân biệt:** `DELETE FROM parent` chịu quy tắc FK; `TRUNCATE` có cơ chế và giới hạn riêng theo DBMS, không nên mặc định nó thực hiện chính xác cùng hành động `ON DELETE CASCADE`.

## 6. `ON DELETE SET NULL`: giữ hàng con, ngắt quan hệ

Giả sử nhân viên vẫn thuộc hệ thống khi phòng ban cũ bị giải thể, và có thể tạm thời chưa được gán phòng ban mới. Khi đó ngắt liên kết, giữ nguyên nhân viên là hành vi hợp lý.

```sql
CREATE TABLE ref_departments (
    department_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE ref_employees (
    employee_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL,
    department_id BIGINT,
    CONSTRAINT fk_ref_employee_department
        FOREIGN KEY (department_id)
        REFERENCES ref_departments(department_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

INSERT INTO ref_departments (department_id, name)
VALUES (10, 'Sales'), (20, 'Engineering');

INSERT INTO ref_employees (employee_id, full_name, department_id)
VALUES
    (1, 'An', 10),
    (2, 'Bình', 10),
    (3, 'Chi', 20),
    (4, 'Dũng', NULL);
```

Khi xóa `Sales`:

```sql
DELETE FROM ref_departments WHERE department_id = 10;

SELECT employee_id, department_id
FROM ref_employees
ORDER BY employee_id;
```

Kết quả:

| employee_id | department_id |
|---:|---:|
| 1 | `NULL` |
| 2 | `NULL` |
| 3 | 20 |
| 4 | `NULL` |

Hai nhân viên cũ của Sales vẫn còn, chỉ liên kết phòng ban được đặt thành `NULL`.

**Điều kiện thiết yếu:** cột đích của `SET NULL` phải cho phép `NULL`. Nếu khai báo `department_id BIGINT NOT NULL`, thao tác xóa cha sẽ thất bại khi cố đặt `NULL` cho hàng con. Việc viết `ON DELETE SET NULL` **không tự gỡ bỏ ràng buộc `NOT NULL`**.

Cũng cần bảo đảm “không còn phòng ban” là trạng thái có ý nghĩa. Nếu mọi nhân viên bắt buộc phải có phòng ban, chọn `RESTRICT` và chuyển họ sang phòng ban khác trước khi xóa phòng ban cũ thường diễn đạt quy tắc tốt hơn.

## 7. `ON DELETE SET DEFAULT`: chuyển sang liên kết mặc định hợp lệ

`SET DEFAULT` yêu cầu DBMS thay khóa ngoại của các hàng con bằng **giá trị mặc định của cột**. Điều này chỉ phù hợp khi ứng dụng có một giá trị thay thế thật sự có nghĩa, ví dụ danh mục “Chưa phân loại”.

Ví dụ PostgreSQL:

```sql
CREATE TABLE product_categories (
    category_id BIGINT PRIMARY KEY,
    category_name TEXT NOT NULL
);

-- Danh mục dự phòng cần tồn tại thực sự trong bảng cha.
INSERT INTO product_categories (category_id, category_name)
VALUES (0, 'Uncategorized'),
       (10, 'Electronics'),
       (20, 'Books');

CREATE TABLE catalog_products (
    product_id BIGINT PRIMARY KEY,
    category_id BIGINT NOT NULL DEFAULT 0,
    product_name TEXT NOT NULL,
    CONSTRAINT fk_catalog_product_category
        FOREIGN KEY (category_id)
        REFERENCES product_categories(category_id)
        ON DELETE SET DEFAULT
        ON UPDATE CASCADE
);

INSERT INTO catalog_products (product_id, category_id, product_name)
VALUES (100, 10, 'Laptop');

DELETE FROM product_categories WHERE category_id = 10;

SELECT product_id, category_id FROM catalog_products;
-- (100, 0)
```

Khi danh mục 10 bị xóa, sản phẩm 100 được chuyển sang danh mục 0, và danh mục 0 đã có trong bảng cha nên FK vẫn hợp lệ.

Nếu `DEFAULT 0` nhưng **không có hàng cha với khóa 0**, việc đặt mặc định sẽ tạo tham chiếu sai và thao tác xóa bị từ chối. Tương tự, khi không có `DEFAULT` rõ ràng, mặc định của cột thường là `NULL`; nếu cột `NOT NULL` thì hành động sẽ không thực hiện được với hàng con đang tham chiếu. `SET DEFAULT` không bỏ qua `NOT NULL` hoặc khóa ngoại.

**Không dùng giá trị giả như 0 chỉ để qua lỗi.** Bản ghi “Chưa phân loại” phải được nghiệp vụ công nhận và có chính sách không cho xóa vô ý. Cũng cần kiểm tra DBMS mục tiêu vì không phải hệ nào cũng hỗ trợ hành động `SET DEFAULT` cho FK; ví dụ MySQL InnoDB không thực hiện `SET DEFAULT` như PostgreSQL.

## 8. `ON UPDATE`: điều gì xảy ra khi khóa được tham chiếu đổi?

`ON UPDATE` có hiệu lực khi **giá trị khóa cha được tham chiếu đổi**, không phải khi cập nhật mọi cột của hàng cha. Ví dụ:

```sql
-- Chỉ sửa tên, không sửa department_id:
UPDATE ref_departments
SET name = 'Product Engineering'
WHERE department_id = 20;
```

Thao tác này không cần áp dụng `ON UPDATE CASCADE`, vì khóa `department_id` vẫn là 20.

Nhưng nếu khóa được đổi:

```sql
UPDATE ref_departments
SET department_id = 200
WHERE department_id = 20;
```

Trong bảng `ref_employees` từ phần trước, ràng buộc được khai báo `ON UPDATE CASCADE`, nên nhân viên có `employee_id = 3` tự động chuyển `department_id` từ 20 sang 200. Nhân viên không thay đổi danh tính, chỉ cập nhật giá trị khóa ngoại để tiếp tục trỏ đúng hàng cha.

| Hành động `ON UPDATE` | Khi khóa cha đổi từ 20 thành 200 |
|---|---|
| `NO ACTION` | Nếu còn tham chiếu 20 ở thời điểm kiểm tra, không cho trạng thái vi phạm; có thể trì hoãn theo cơ chế DBMS |
| `RESTRICT` | Chặn đổi khóa cha khi còn tham chiếu 20 |
| `CASCADE` | Đổi khóa ngoại của các hàng con từ 20 sang 200 |
| `SET NULL` | Đặt khóa ngoại của các hàng con tham chiếu 20 thành `NULL` |
| `SET DEFAULT` | Đặt khóa ngoại của các hàng con tham chiếu 20 về giá trị mặc định hợp lệ |

**Cảnh báo:** `ON UPDATE SET NULL` và `ON UPDATE SET DEFAULT` khiến hàng con **không còn liên kết tới đối tượng cha đã đổi mã**, dù đối tượng cha vẫn tồn tại. Chỉ dùng khi đó là đúng ý nghĩa nghiệp vụ. Với mã tự nhiên được phép đổi nhưng quan hệ phải tiếp tục tồn tại, `ON UPDATE CASCADE` thường rõ ràng hơn. Với khóa chính nhân tạo ổn định không nên đổi, `ON UPDATE RESTRICT` hoặc `NO ACTION` có thể phù hợp.

### Khóa chính nhân tạo và khóa nghiệp vụ

Đối với `order_id` hoặc `customer_id` được sinh làm định danh ổn định, ứng dụng thường không cần cập nhật khóa chính. Vì thế, việc thiết kế `ON UPDATE` không nên là lý do để cho phép đổi các ID mà nghiệp vụ coi là bất biến.

Nếu khóa ngoại tham chiếu mã nghiệp vụ có thể đổi tên, ví dụ `sku`, `username` hay `department_code`, cân nhắc một trong hai hướng:

1. Cho phép đổi mã và dùng `ON UPDATE CASCADE` để giữ các quan hệ.
2. Dùng một khóa chính nhân tạo ổn định để tham chiếu; giữ mã nghiệp vụ dưới `UNIQUE` và cập nhật mã độc lập với khóa ngoại.

Lựa chọn thứ hai thường giảm nhu cầu cập nhật dây chuyền ở bảng con, nhưng vẫn phải xác định chính sách chống trùng mã và tác động tích hợp ngoài DB.

## 9. Ràng buộc khóa ngoại ghép và hành động tham chiếu

Khóa được tham chiếu có thể gồm nhiều cột, chẳng hạn mã tài liệu duy nhất trong từng tổ chức:

```sql
CREATE TABLE tenant_documents (
    tenant_id BIGINT NOT NULL,
    document_code VARCHAR(30) NOT NULL,
    title TEXT NOT NULL,
    PRIMARY KEY (tenant_id, document_code)
);

CREATE TABLE tenant_document_items (
    tenant_id BIGINT NOT NULL,
    document_code VARCHAR(30) NOT NULL,
    line_no INTEGER NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (tenant_id, document_code, line_no),
    CONSTRAINT fk_document_items
        FOREIGN KEY (tenant_id, document_code)
        REFERENCES tenant_documents (tenant_id, document_code)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);
```

Tại đây, **cả `tenant_id` và `document_code` tạo thành khóa được tham chiếu**. Nếu xóa tài liệu `(10, 'DOC-A')`, chỉ các dòng con có đúng tổ hợp đó bị xóa; tài liệu `(20, 'DOC-A')` của tổ chức khác không bị ảnh hưởng. Nếu đổi mã tài liệu từ `DOC-A` thành `DOC-B` trong tenant 10, `ON UPDATE CASCADE` cập nhật **tổ hợp khóa ngoại tương ứng** ở các dòng con.

### Khi hành động `SET NULL` gặp khóa ghép

Với FK ghép, hành động `SET NULL` thông thường đặt các cột khóa ngoại liên quan thành `NULL` theo cú pháp/hành vi của DBMS. Nếu một trong các cột ấy thuộc `PRIMARY KEY` của bảng con hoặc có `NOT NULL`, thao tác không thể gán `NULL` và sẽ thất bại.

Trong PostgreSQL có cú pháp riêng cho phép chỉ định **danh sách cột muốn đặt `NULL` khi `ON DELETE`**, ví dụ muốn giữ nguyên `tenant_id` nhưng bỏ liên kết `document_code`:

```sql
-- Ví dụ riêng theo PostgreSQL:
CREATE TABLE document_notes (
    note_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    document_code VARCHAR(30),
    note_text TEXT NOT NULL,
    CONSTRAINT fk_document_notes
        FOREIGN KEY (tenant_id, document_code)
        REFERENCES tenant_documents (tenant_id, document_code)
        ON DELETE SET NULL (document_code)
);
```

Cách này cho phép giữ phạm vi tenant khi tài liệu bị xóa. Với chế độ kiểm tra FK ghép mặc định `MATCH SIMPLE`, nếu `document_code` là `NULL` thì tổ hợp FK có phần tử `NULL` không bị yêu cầu phải khớp một hàng cha. **Đây là cú pháp đặc thù**, không nên sao chép nguyên sang các DBMS khác.

Nếu dùng `MATCH FULL` theo SQL/PostgreSQL cho khóa ghép, trạng thái chỉ một số cột `NULL` thường không hợp lệ: mọi thành phần phải cùng `NULL` hoặc cùng xác định (và tham chiếu hợp lệ). Vì vậy cần phối hợp chính sách `NULL`, khóa ghép và hành động tham chiếu theo đúng yêu cầu.

## 10. Hành động tham chiếu và tính nguyên tử của giao dịch

Hành động FK được DBMS thực thi như một phần của thao tác và giao dịch liên quan. Một lệnh `DELETE` làm cascade sang nhiều bảng có thể sửa/xóa nhiều dòng. Nếu một quy tắc bắt buộc bị vi phạm, thao tác không được để lại trạng thái quan hệ sai đã được chấp nhận; cách rollback và phạm vi atomicity cụ thể phụ thuộc DBMS, cơ chế lưu trữ và cách sử dụng giao dịch.

Ví dụ, trước khi xóa một cha có nhiều con:

```sql
BEGIN;

-- Xem số hàng con sẽ bị ảnh hưởng.
SELECT COUNT(*) AS cart_item_count
FROM cart_items
WHERE cart_id = 901;

-- Chỉ xóa khi nghiệp vụ đã xác nhận an toàn.
DELETE FROM shopping_carts
WHERE cart_id = 901;

-- Thực hiện COMMIT khi kết quả đúng, hoặc ROLLBACK nếu không.
COMMIT;
```

Truy vấn `COUNT(*)` ở đây chỉ cung cấp thông tin tại thời điểm đọc; nếu có thao tác đồng thời, số hàng có thể thay đổi. Với thao tác quan trọng cần quy trình giao dịch, khóa hoặc mức cô lập phù hợp, thay vì coi `SELECT COUNT(*)` là bảo đảm tuyệt đối.

### Tác động đa cấp

```text
accounts
   └─ON DELETE CASCADE─> projects
                           └─ON DELETE CASCADE─> tasks
                                                   └─ON DELETE CASCADE─> task_comments
```

Một câu lệnh xóa account có thể xóa tất cả projects, tasks và comments nếu tất cả quan hệ trên dùng cascade. Điều này đôi khi đúng cho dữ liệu tạm, nhưng có thể nguy hiểm cho dữ liệu có lịch sử. Đừng lựa chọn `CASCADE` chỉ vì muốn tiện xóa mà chưa hiểu hệ quả toàn đồ thị quan hệ.

Nếu có vòng tham chiếu giữa các bảng, thứ tự thao tác, khả năng hoãn kiểm tra, ràng buộc `NOT NULL` và giới hạn cascading paths của DBMS đều cần được xem xét. Không thể mặc định cascade giải quyết mọi chu trình.

## 11. Khác biệt đáng chú ý giữa các hệ quản trị

| Hệ quản trị | Điểm cần lưu ý khi dùng FK và hành động tham chiếu |
|---|---|
| **PostgreSQL** | Hỗ trợ `NO ACTION`, `RESTRICT`, `CASCADE`, `SET NULL`, `SET DEFAULT` trong `ON DELETE`/`ON UPDATE`. `NO ACTION` có thể trì hoãn nếu khai báo `DEFERRABLE`; `RESTRICT` không theo cùng cơ chế trì hoãn. Có cú pháp chỉ định cột cho `ON DELETE SET NULL/SET DEFAULT` ở các phiên bản phù hợp. |
| **MySQL (InnoDB)** | Hỗ trợ `CASCADE`, `SET NULL`, `RESTRICT` và `NO ACTION`; `NO ACTION` tương đương hành vi kiểm tra ngay với `RESTRICT`. InnoDB không hỗ trợ hành động FK `SET DEFAULT`. Cần dùng storage engine hỗ trợ FK. |
| **SQL Server** | Hỗ trợ `NO ACTION`, `CASCADE`, `SET NULL`, `SET DEFAULT` ở FK theo cú pháp sản phẩm. Có giới hạn với nhiều đường cascade hoặc vòng lặp cascade; cần kiểm tra sơ đồ quan hệ. Không có deferred constraints theo cách PostgreSQL. |
| **SQLite** | Hỗ trợ các hành động FK thông dụng, nhưng kiểm tra khóa ngoại cần được **bật trên từng kết nối** khi cấu hình không tự bật, ví dụ `PRAGMA foreign_keys = ON;`. `RESTRICT` có thể báo lỗi ngay ngay cả khi FK đang được trì hoãn. |
| **Oracle Database** | Thông dụng với `ON DELETE CASCADE` và `ON DELETE SET NULL`; không có cú pháp `ON UPDATE CASCADE` tương ứng trong định nghĩa FK thông thường. Có khả năng khai báo ràng buộc `DEFERRABLE`, nhưng phải thiết kế riêng cho cập nhật khóa cha. |

Đây là mô tả để định hướng, không thay thế tài liệu phiên bản cụ thể. Cú pháp, giới hạn và cơ chế kiểm tra FK còn có thể phụ thuộc phiên bản, edition, storage engine và cấu hình. Ví dụ về `ON UPDATE CASCADE` trong PostgreSQL không nên dùng nguyên xi trong Oracle.

**SQLite:** khi thử ví dụ khóa ngoại, nên bật kiểm tra trước khi tạo/chỉnh sửa dữ liệu liên quan:

```sql
PRAGMA foreign_keys = ON;
```

Nếu không bật, một số môi trường SQLite có thể chấp nhận các bản ghi vi phạm và không thực hiện hành động tham chiếu như mong đợi. Với ứng dụng dùng connection pool, cấu hình kiểm tra FK phải áp dụng đúng cho kết nối liên quan; cần kiểm tra trạng thái thực tế trong môi trường vận hành.

## 12. Hiệu năng, chỉ mục và vận hành

Hành động tham chiếu không chỉ là khai báo ngữ nghĩa; chúng khiến DBMS phải tìm các hàng con liên quan khi cha bị xóa hoặc đổi khóa.

### 12.1. Chỉ mục trên khóa ngoại

Trong PostgreSQL, khi tạo khóa chính/`UNIQUE`, DBMS thường tạo chỉ mục phục vụ ràng buộc phía cha. Nhưng **tạo FK ở bảng con không tự động tạo chỉ mục trên các cột FK**. Nếu bảng con lớn, việc kiểm tra/xóa/cập nhật theo cha có thể tốn kém nếu không có chỉ mục phù hợp.

```sql
-- Hữu ích khi xóa/cập nhật khóa cha hoặc truy vấn nhiều dòng con theo cha.
CREATE INDEX idx_cart_items_cart_id
ON cart_items (cart_id);

CREATE INDEX idx_ref_employees_department_id
ON ref_employees (department_id);
```

Với `cart_items`, đã có `PRIMARY KEY (cart_id, product_id)`; tùy DBMS và cách triển khai, chỉ mục PK này có thể **đã phục vụ** truy vấn theo `cart_id`, nên chỉ mục `idx_cart_items_cart_id` có thể dư thừa. Trước khi thêm, cần xem chỉ mục hiện có và kế hoạch thực thi. Đây là lý do không nên tạo chỉ mục bổ sung một cách máy móc.

Ở các DBMS khác, việc tạo/chính sách yêu cầu chỉ mục cho FK có thể khác. Với khóa ngoại ghép, chú ý thứ tự cột và mẫu truy vấn thực tế.

### 12.2. Chi phí thay đổi dữ liệu

- `ON DELETE CASCADE` có thể phải xóa hàng nghìn hoặc hàng triệu dòng con.
- `ON UPDATE CASCADE` có thể sửa nhiều khóa ngoại và kéo theo cập nhật chỉ mục hoặc các quan hệ khác.
- `SET NULL`/`SET DEFAULT` cũng là thao tác `UPDATE` hàng con và có thể ảnh hưởng trigger, chỉ mục và nhật ký giao dịch.
- `RESTRICT`/`NO ACTION` không tự sửa hàng con, nhưng DBMS vẫn cần kiểm tra tham chiếu, có thể phát sinh khóa và chờ khi có giao dịch đồng thời.

Dùng giao dịch được kiểm soát, kế hoạch vận hành, giám sát số dòng chịu ảnh hưởng và cơ chế bảo vệ dữ liệu phù hợp với khối lượng thực tế.

### 12.3. Ràng buộc và ứng dụng phải thống nhất

Nếu ứng dụng xóa thủ công hàng con rồi xóa cha, trong khi FK cũng khai báo `ON DELETE CASCADE`, cần hiểu và đơn giản hóa luồng xử lý để tránh thao tác trùng, sự kiện ngoài mong muốn hoặc thông báo sai số lượng dòng xóa. Các ORM như Hibernate/JPA cũng có khái niệm *cascade* ở tầng đối tượng; **cascade ORM và hành động FK của DBMS là hai cơ chế khác nhau**. Cần cấu hình nhất quán và hiểu khi nào bản ghi được xóa bởi ứng dụng, khi nào bởi DBMS.

Không nên tắt kiểm tra khóa ngoại để tránh lỗi khi nhập dữ liệu trừ khi có một quy trình migration/khôi phục được kiểm soát, bao gồm kiểm tra toàn vẹn trước khi hoạt động bình thường.

## 13. Thay đổi hành động FK khi nghiệp vụ đổi

Khi một quan hệ ban đầu dùng `ON DELETE RESTRICT` nhưng được phép ngắt liên kết khi xóa cha, ta có thể đổi ràng buộc sang `SET NULL` sau khi bảo đảm cột con cho phép `NULL`.

Ví dụ PostgreSQL, giả sử `ref_employees` đang có ràng buộc `fk_ref_employee_department` từ phần 6:

```sql
ALTER TABLE ref_employees
    DROP CONSTRAINT fk_ref_employee_department;

ALTER TABLE ref_employees
    ADD CONSTRAINT fk_ref_employee_department
    FOREIGN KEY (department_id)
    REFERENCES ref_departments (department_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;
```

Hai lệnh trên minh họa đổi chính sách **sang `RESTRICT`**; tên ràng buộc được giữ nguyên, nhưng quy tắc xóa cha đã thay đổi. Trong hệ thống thật, nên đặt các bước migration trong giao dịch phù hợp nếu DBMS hỗ trợ transactional DDL, xác định trạng thái dữ liệu và kiểm tra quyền trước khi triển khai.

Không thể coi thay đổi `CASCADE` → `RESTRICT` hoặc ngược lại là thao tác thuần cú pháp: nó thay đổi chính sách lưu/xóa dữ liệu. Cần xem luồng ứng dụng, API, job chạy nền, trigger, chiến lược backup và yêu cầu lưu lịch sử.

## 14. Chọn hành động dựa trên nghiệp vụ

Để chọn hành động, trước hết hỏi: **Nếu cha không còn tồn tại, hàng con còn ý nghĩa không?** Sau đó hỏi: **Nếu khóa cha đổi, hàng con có cần tiếp tục trỏ đến đúng đối tượng đó không?**

| Tình huống | Gợi ý `ON DELETE` | Gợi ý `ON UPDATE` | Lý do |
|---|---|---|---|
| Giỏ hàng tạm và các dòng hàng | `CASCADE` | `RESTRICT` hoặc `CASCADE` theo chính sách khóa | Dòng hàng thường không có ý nghĩa nếu giỏ đã bị xóa |
| Khách hàng và hóa đơn cần giữ lịch sử | `RESTRICT`/`NO ACTION` | Thường `RESTRICT` với ID ổn định | Cấm mất hóa đơn khi xóa khách hàng tùy tiện |
| Nhân viên và phòng ban không bắt buộc | `SET NULL` | `CASCADE` nếu mã phòng ban được phép đổi | Giữ nhân viên và có thể tạm chưa gán phòng ban |
| Sản phẩm và danh mục “Chưa phân loại” có thật | `SET DEFAULT` | `CASCADE` nếu khóa danh mục đổi | Giữ sản phẩm, chuyển sang danh mục fallback hợp lệ |
| Bảng liên kết của thực thể tạm | Có thể `CASCADE` ở từng FK | Theo nhu cầu đổi khóa | Hàng liên kết không còn ý nghĩa nếu thực thể bị xóa |
| Nhật ký kiểm toán | Thường `RESTRICT` hoặc lưu snapshot/thiết kế lưu lịch sử riêng | Hạn chế đổi khóa đã dùng | Tránh phá vỡ dấu vết sự kiện |
| Khóa nghiệp vụ có thể đổi | Tùy vòng đời hàng con | `CASCADE` nếu quan hệ cần tiếp tục tồn tại | Đồng bộ FK khi mã cha thay đổi |
| Khóa chính nhân tạo bất biến | Tùy vòng đời hàng con | `NO ACTION`/`RESTRICT` thường đủ | Không cần cập nhật ID vốn không được phép đổi |

Những lựa chọn này là **gợi ý theo giả định nghiệp vụ**, không phải luật cứng. Ví dụ, trong một hệ thống có yêu cầu xóa dữ liệu cá nhân, xóa khách hàng có thể kéo theo nhiều bước ẩn danh, giữ hóa đơn theo quy định và xóa những dữ liệu chỉ phục vụ cá nhân hóa. Chỉ một `ON DELETE CASCADE` có thể không mô tả được toàn bộ quy trình.

### Cây câu hỏi thực tế

```text
Xóa hàng cha có hợp lệ theo nghiệp vụ không?
  ├─ Không → NO ACTION / RESTRICT
  └─ Có
      │
      ├─ Hàng con chỉ tồn tại vì hàng cha?
      │      └─ Có → Cân nhắc ON DELETE CASCADE
      │
      ├─ Hàng con vẫn tồn tại nhưng quan hệ có thể bỏ trống?
      │      └─ Có → Cân nhắc ON DELETE SET NULL
      │
      └─ Có một đối tượng mặc định có thật, phù hợp?
             └─ Có → Cân nhắc ON DELETE SET DEFAULT

Khóa được tham chiếu có thể đổi không?
  ├─ Không → NO ACTION / RESTRICT thường phù hợp
  └─ Có
      ├─ Hàng con phải tiếp tục trỏ cùng đối tượng → ON UPDATE CASCADE
      └─ Quan hệ phải bị ngắt/chuyển mặc định → SET NULL / SET DEFAULT
```

Đừng dùng `SET NULL` nếu cột bắt buộc không `NULL`, và đừng dùng `SET DEFAULT` nếu không có giá trị thay thế hợp lệ. Với mọi phương án, giữ **khóa ngoại** để DBMS vẫn ngăn các tham chiếu sai ở thao tác ghi thông thường.

## 15. Các lỗi thiết kế và cách xử lý

| Sai lầm | Tác động | Hướng xử lý |
|---|---|---|
| Cho rằng `ON DELETE CASCADE` chỉ xóa FK của hàng con | Xóa mất chính các hàng con | Chỉ dùng khi vòng đời con phụ thuộc cha |
| Chọn `CASCADE` cho quan hệ cần giữ lịch sử | Mất bản ghi phục vụ đối soát/kiểm toán | Chặn xóa, lưu trữ/ẩn danh có kiểm soát hoặc thiết kế snapshot |
| Chọn `SET NULL` cho cột `NOT NULL` | Xóa cha thất bại khi có hàng con | Cho phép `NULL` nếu nghiệp vụ chấp nhận hoặc chọn hành động khác |
| Chọn `SET DEFAULT` không có hàng cha mặc định | Tạo FK không hợp lệ, thao tác bị từ chối | Tạo/giữ đối tượng mặc định hợp lệ hoặc đổi chính sách |
| Nghĩ `NO ACTION` luôn khác hoàn toàn `RESTRICT` | Dự đoán sai thời điểm từ chối | Kiểm tra DBMS và `DEFERRABLE` |
| Dùng `ON UPDATE CASCADE` để cập nhật mọi cột của cha | Hiểu sai sự kiện kích hoạt | Chỉ thay đổi giá trị khóa được tham chiếu mới liên quan |
| Bỏ qua chuỗi cascade nhiều cấp | Một lệnh có thể sửa/xóa số lượng lớn bản ghi | Rà soát đồ thị FK và tác động giao dịch |
| Không xem chỉ mục cột FK ở bảng con | Thao tác cha có thể chậm khi con nhiều dòng | Xem chỉ mục hiện có và kế hoạch truy vấn |
| Sao chép cú pháp PostgreSQL sang mọi DBMS | Lỗi tạo bảng hoặc hành vi khác | Kiểm tra sản phẩm, phiên bản, storage engine |
| Nhầm cascade ORM với FK cascade | Hành vi ứng dụng và DB không đồng nhất | Thiết kế chính sách rõ ràng ở từng tầng |

## 16. Bài tập tình huống

### Bài 1: Xóa danh mục, giữ sản phẩm

Một hệ thống quản lý sản phẩm có danh mục không bắt buộc. Khi danh mục bị xóa, sản phẩm phải còn tồn tại và trường danh mục trở thành “chưa được gán”.

**Hỏi:** chọn hành động gì và cột con cần điều kiện nào?

**Gợi ý đáp án:** `ON DELETE SET NULL`; cột `product.category_id` phải cho phép `NULL`. Nếu muốn chuyển sang danh mục “Chưa phân loại” thật sự có bản ghi riêng, có thể chọn `SET DEFAULT` khi DBMS hỗ trợ và mặc định hợp lệ.

### Bài 2: Xóa đơn hàng đã thanh toán

Một đơn hàng đã phát sinh hóa đơn, thanh toán và các dòng hàng. Hệ thống phải lưu lịch sử để kiểm toán.

**Hỏi:** có nên dùng `ON DELETE CASCADE` trên tất cả quan hệ không?

**Gợi ý đáp án:** không nên mặc định như vậy. Cần chính sách giữ dữ liệu. `RESTRICT` hoặc `NO ACTION` có thể chặn xóa khi còn tham chiếu; có thể dùng trạng thái hủy/đóng đơn thay vì xóa vật lý, hoặc thiết kế lưu trữ lịch sử và ẩn danh theo yêu cầu.

### Bài 3: Đổi mã phòng ban

Bảng `departments` dùng `department_code` làm khóa được tham chiếu. Mã đổi từ `ENG` sang `DEV`, nhân viên phải tiếp tục thuộc cùng phòng ban.

**Hỏi:** chọn `ON UPDATE` nào?

**Gợi ý đáp án:** `ON UPDATE CASCADE` nếu nghiệp vụ thực sự cho phép đổi mã cha và DBMS hỗ trợ. Nếu cần tránh cập nhật hàng loạt, có thể tham chiếu một `department_id` ổn định và quản lý `department_code` bằng ràng buộc duy nhất riêng.

### Bài 4: `NO ACTION` và `RESTRICT` trong giao dịch

Tại PostgreSQL, một FK được khai báo `ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`. Giao dịch xóa cha trước, xóa con sau, rồi commit.

**Hỏi:** tại sao giao dịch có thể hợp lệ?

**Gợi ý đáp án:** trạng thái tạm thời vi phạm FK được phép tồn tại trong giao dịch khi kiểm tra bị trì hoãn, nhưng trước khi commit các tham chiếu sai đã được xử lý. Nếu dùng `RESTRICT`, không thể dựa vào cơ chế trì hoãn này để xóa cha đang được tham chiếu.

### Bài 5: Xóa một phần trong khóa ghép

Bảng con có FK `(tenant_id, document_code)` tham chiếu bảng cha; `tenant_id` bắt buộc nhưng `document_code` được phép thiếu. Khi xóa tài liệu, vẫn muốn giữ ghi chú trong tenant cũ.

**Hỏi:** dùng `ON DELETE SET NULL` cho toàn bộ khóa có hợp lý không?

**Gợi ý đáp án:** không nếu nó cố gán `NULL` cho `tenant_id NOT NULL`. Trên PostgreSQL có thể dùng `ON DELETE SET NULL (document_code)` và phối hợp với ngữ nghĩa `MATCH SIMPLE`; trên DBMS khác cần thiết kế/cú pháp tương ứng.

## Kết luận

`ON DELETE` và `ON UPDATE` là một phần của **hợp đồng vòng đời giữa bảng cha và bảng con**. `NO ACTION`/`RESTRICT` dùng khi cần chặn thao tác làm mất tham chiếu; `CASCADE` dùng khi hàng con thực sự phụ thuộc vòng đời cha hoặc cần theo khóa cha mới; `SET NULL` giữ hàng con nhưng ngắt liên kết; `SET DEFAULT` chuyển liên kết về một giá trị mặc định hợp lệ.

Khi chọn hành động, hãy xác định trước yêu cầu lưu lịch sử, khả năng xóa cha, khả năng đổi khóa, tính bắt buộc của FK, chuỗi tác động nhiều cấp và sự hỗ trợ của DBMS đang dùng. Một định nghĩa FK tốt vừa **ngăn dữ liệu mồ côi**, vừa làm cho thao tác xóa/cập nhật phản ánh đúng quy tắc nghiệp vụ và dễ dự đoán trong vận hành.

