# ON DELETE/ON UPDATE, CASCADE, SET NULL và RESTRICT

Khóa ngoại (foreign key) giữ cho quan hệ giữa bảng cha và bảng con luôn hợp lệ. Khi một hàng ở bảng cha bị xóa hoặc khóa được tham chiếu bị cập nhật, MySQL cần một quy tắc xác định điều gì xảy ra với các hàng con. Hai mệnh đề `ON DELETE` và `ON UPDATE` khai báo quy tắc đó. Các lựa chọn thường gặp là `CASCADE`, `SET NULL`, `RESTRICT` và `NO ACTION`.

Chọn đúng hành vi tham chiếu giúp bảo vệ dữ liệu nghiệp vụ, tránh xóa nhầm dây chuyền và làm rõ trách nhiệm của ứng dụng khi thay đổi dữ liệu. Trong module `DATABASE_MYSQL`, đây là phần quan trọng của thiết kế bảng, khóa, transaction và vận hành dữ liệu quan hệ. Bài học tập trung vào InnoDB trên MySQL 8.x.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích thời điểm và phạm vi tác động của `ON DELETE` và `ON UPDATE`.
- Phân biệt `CASCADE`, `SET NULL`, `RESTRICT` và `NO ACTION`.
- Chọn hành vi phù hợp theo vòng đời dữ liệu nghiệp vụ.
- Thiết kế cột khóa ngoại nullable hoặc NOT NULL đúng với hành động tham chiếu.
- Nhận biết ảnh hưởng của cascade nhiều cấp, transaction, lock và trigger.
- Kiểm tra ràng buộc, xử lý lỗi xóa/cập nhật và triển khai migration an toàn.

## 1. Quan hệ cha-con và khóa ngoại

Giả sử một khách hàng có nhiều đơn hàng. Bảng `customers` là bảng cha; bảng `orders` là bảng con. Cột `orders.customer_id` tham chiếu tới `customers.customer_id`.

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_id (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE=InnoDB;
```

Trong ví dụ, khóa ngoại bảo đảm mỗi `orders.customer_id` khác `NULL` phải trỏ tới một khách hàng tồn tại. MySQL/InnoDB yêu cầu cột khóa ngoại có index phù hợp; InnoDB có thể tự tạo index nếu chưa có index đáp ứng. Nên khai báo index tường minh để tên gọi và thứ tự cột được kiểm soát trong schema.

Khi xóa hoặc đổi `customers.customer_id`, ràng buộc cần biết cách xử lý các đơn hàng đang tham chiếu tới khách hàng đó. Nếu không khai báo hành động, hành vi mặc định là từ chối thay đổi làm vi phạm khóa ngoại (tương đương `RESTRICT`/`NO ACTION` trong InnoDB).

## 2. Hai sự kiện kích hoạt hành động tham chiếu

| Mệnh đề | Khi nào được xét? | Ví dụ |
|---|---|---|
| `ON DELETE` | Khi xóa hàng cha đang được khóa ngoại tham chiếu | Xóa khách hàng có đơn hàng |
| `ON UPDATE` | Khi cập nhật giá trị khóa được tham chiếu ở hàng cha | Đổi mã khóa cha từ 100 sang 200 |

Hành động chỉ áp dụng khi thao tác ở phía cha làm thay đổi khóa được tham chiếu và có hàng con liên quan. Xóa hàng con không làm thay đổi hàng cha. Cập nhật một cột không nằm trong khóa được tham chiếu cũng không kích hoạt `ON UPDATE` của khóa ngoại đó.

Với mỗi sự kiện, có thể chọn một trong các hành động:

| Hành động | Khi xóa/cập nhật hàng cha | Kết quả phía bảng con |
|---|---|---|
| `CASCADE` | Cho phép thao tác ở cha | Xóa hàng con tương ứng hoặc cập nhật khóa ngoại con theo giá trị mới |
| `SET NULL` | Cho phép thao tác ở cha | Đặt các cột khóa ngoại con thành `NULL` |
| `RESTRICT` | Từ chối thao tác ở cha nếu có hàng con tham chiếu | Không thay đổi hàng con; câu lệnh ở cha báo lỗi |
| `NO ACTION` | Với InnoDB, tương đương `RESTRICT` và được kiểm tra ngay | Không thay đổi hàng con; câu lệnh ở cha báo lỗi |

`ON DELETE` và `ON UPDATE` có thể dùng hai hành động khác nhau. Ví dụ, xóa khách hàng bị chặn để bảo vệ lịch sử đơn hàng, nhưng nếu mã khách hàng có thể thay đổi thì cập nhật khóa có thể được cascade.

## 3. CASCADE: lan truyền thay đổi sang bảng con

`CASCADE` tự động áp dụng thao tác tương ứng cho các hàng con có khóa ngoại tham chiếu tới hàng cha.

### 3.1. `ON DELETE CASCADE`

Khi xóa một hàng cha, các hàng con tham chiếu tới hàng đó cũng bị xóa. Ví dụ, một đơn hàng có nhiều dòng hàng; khi đơn hàng bị xóa trong mô hình dữ liệu lab, các dòng hàng của nó được xóa theo:

```sql
CREATE TABLE orders_cascade (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_code VARCHAR(40) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

CREATE TABLE order_items_cascade (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (item_id),
    KEY idx_order_items_order_id (order_id),
    CONSTRAINT fk_order_items_order_cascade
        FOREIGN KEY (order_id)
        REFERENCES orders_cascade (order_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB;
```

Chèn dữ liệu thử:

```sql
INSERT INTO orders_cascade (order_code)
VALUES ('ORD-LAB-001');

INSERT INTO order_items_cascade (order_id, product_name, quantity)
VALUES
    (1, 'Keyboard', 1),
    (1, 'Mouse', 2);
```

Xóa đơn hàng:

```sql
DELETE FROM orders_cascade
WHERE order_id = 1;
```

Hai dòng trong `order_items_cascade` được xóa tự động trong cùng thao tác tham chiếu. Với InnoDB, thao tác xóa ở cha và các thay đổi cascade thuộc cùng transaction; nếu câu lệnh thất bại và transaction rollback, các thay đổi transactional được hoàn tác cùng nhau.

`ON DELETE CASCADE` phù hợp khi hàng con không có ý nghĩa độc lập nếu hàng cha bị xóa, chẳng hạn dòng chi tiết của một bản nháp chưa phát hành, token phụ thuộc vào phiên đăng nhập hoặc bảng nối thể hiện quan hệ nhiều-nhiều.

Không nên dùng cascade chỉ để giảm số câu SQL. Nếu hàng con là lịch sử tài chính, hóa đơn, giao dịch, log kiểm toán hoặc dữ liệu cần lưu theo quy định, xóa cha có thể làm mất bằng chứng nghiệp vụ. Với dữ liệu cần giữ, hãy cân nhắc `RESTRICT`, soft delete hoặc mô hình lưu trữ lịch sử.

### 3.2. `ON UPDATE CASCADE`

Khi giá trị khóa được tham chiếu ở cha thay đổi, MySQL cập nhật các cột khóa ngoại tương ứng ở con:

```sql
CREATE TABLE region (
    region_code CHAR(5) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (region_code)
) ENGINE=InnoDB;

CREATE TABLE branch (
    branch_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    region_code CHAR(5) NOT NULL,
    branch_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (branch_id),
    KEY idx_branch_region_code (region_code),
    CONSTRAINT fk_branch_region
        FOREIGN KEY (region_code)
        REFERENCES region (region_code)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE=InnoDB;
```

Nếu mã vùng được đổi:

```sql
UPDATE region
SET region_code = 'N01'
WHERE region_code = 'NORTH';
```

Các hàng `branch` đang dùng `NORTH` sẽ được đổi sang `N01`. Trong thiết kế mới, khóa chính surrogate như `region_id` thường ổn định hơn mã nghiệp vụ; khi mã hiển thị thay đổi, chỉ cần cập nhật cột thuộc tính. `ON UPDATE CASCADE` hữu ích khi khóa được tham chiếu thực sự có thể thay đổi, nhưng không nên xem nó là lý do để chọn khóa chính hay thay đổi ID thường xuyên.

### 3.3. Cascade nhiều cấp

Hành động cascade có thể lan theo chuỗi quan hệ. Ví dụ:

```text
orders
  └── order_items
        └── item_notes
```

Nếu `orders` xóa cascade sang `order_items`, và `order_items` lại xóa cascade sang `item_notes`, thao tác xóa ở đơn hàng có thể xóa các hàng ở cả hai bảng con. Một thao tác tưởng như đơn giản có thể ảnh hưởng tới lượng dữ liệu lớn.

Hãy lập sơ đồ các khóa ngoại trước khi dùng cascade trên bảng có nhiều quan hệ. Kiểm tra số hàng bị ảnh hưởng, index ở phía con, lock và thời gian thực thi. InnoDB giới hạn độ sâu của chuỗi thao tác cascade; không thiết kế cây quan hệ quá sâu hoặc vòng phụ thuộc phức tạp mà không kiểm thử trên đúng phiên bản.

## 4. SET NULL: giữ hàng con nhưng bỏ liên kết

`SET NULL` giữ lại hàng con và đặt cột khóa ngoại thành `NULL` khi hàng cha bị xóa hoặc khóa được tham chiếu được cập nhật. Hành động này phù hợp khi quan hệ là tùy chọn và hàng con vẫn có ý nghĩa độc lập.

Ví dụ bài viết có thể có người biên tập, nhưng bài viết vẫn cần được giữ khi tài khoản người biên tập bị xóa:

```sql
CREATE TABLE editor (
    editor_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    editor_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (editor_id)
) ENGINE=InnoDB;

CREATE TABLE article (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    editor_id BIGINT UNSIGNED NULL,
    title VARCHAR(200) NOT NULL,
    body TEXT,
    PRIMARY KEY (article_id),
    KEY idx_article_editor_id (editor_id),
    CONSTRAINT fk_article_editor
        FOREIGN KEY (editor_id)
        REFERENCES editor (editor_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
) ENGINE=InnoDB;
```

Khi xóa editor:

```sql
DELETE FROM editor
WHERE editor_id = 10;
```

Các bài viết do editor đó phụ trách vẫn còn; `article.editor_id` chuyển thành `NULL`. Ứng dụng có thể hiển thị “Chưa gán người biên tập” hoặc dùng một trạng thái nghiệp vụ riêng.

### 4.1. Cột khóa ngoại phải cho phép NULL

`SET NULL` không thể đặt `NULL` vào cột được khai báo `NOT NULL`. Với ví dụ trên, `article.editor_id` phải là `BIGINT UNSIGNED NULL`. Nếu cột không nullable, thiết kế constraint sẽ bị từ chối hoặc thao tác tham chiếu không thể thực hiện theo yêu cầu.

Với khóa ngoại nhiều cột, các cột con được đặt `NULL` theo hành động; cần thiết kế tất cả cột liên quan có thể nhận `NULL` và hiểu đúng semantics của khóa ngoại composite. Không dùng `0`, chuỗi rỗng hoặc một ID giả để thay cho `NULL` nếu mục đích là biểu thị không còn liên kết.

### 4.2. SET NULL khi cập nhật khóa cha

Có thể khai báo `ON UPDATE SET NULL`, nghĩa là khi giá trị khóa được tham chiếu ở cha thay đổi, liên kết ở con bị xóa bằng cách đặt khóa ngoại thành `NULL`. Trường hợp này ít phổ biến hơn `ON DELETE SET NULL`; nếu mã cha thay đổi mà quan hệ vẫn còn đúng, `ON UPDATE CASCADE` thường diễn đạt đúng ý định hơn.

## 5. RESTRICT và NO ACTION: chặn thay đổi làm mất tính toàn vẹn

`RESTRICT` từ chối xóa hoặc cập nhật khóa cha nếu vẫn còn hàng con tham chiếu. Đây là lựa chọn bảo vệ dữ liệu khi hàng con cần được xử lý trước hoặc quan hệ phải được giữ lại.

Ví dụ, khách hàng có đơn hàng thì không được xóa trực tiếp:

```sql
CREATE TABLE customer_restrict (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE order_restrict (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_order_restrict_customer (customer_id),
    CONSTRAINT fk_order_restrict_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer_restrict (customer_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
) ENGINE=InnoDB;
```

Nếu khách hàng có đơn hàng, câu lệnh:

```sql
DELETE FROM customer_restrict
WHERE customer_id = 1;
```

sẽ bị từ chối với lỗi vi phạm khóa ngoại (thường là lỗi MySQL 1451 khi xóa/cập nhật hàng cha). Ứng dụng cần xử lý các đơn hàng theo quy trình nghiệp vụ hoặc đánh dấu khách hàng không còn hoạt động, thay vì xóa trực tiếp.

### 5.1. NO ACTION trong InnoDB

Với InnoDB, `NO ACTION` có hành vi tương đương `RESTRICT`: kiểm tra khóa ngoại ngay khi statement thực hiện và từ chối thao tác nếu còn hàng con tham chiếu. Nó không có nghĩa là “đợi đến cuối transaction mới kiểm tra”. MySQL/InnoDB không cung cấp deferred foreign key constraint như một số hệ quản trị khác.

Vì vậy, trong schema InnoDB, viết `RESTRICT` thường rõ ý hơn nếu muốn chặn ngay. `NO ACTION` có thể được dùng để diễn đạt chuẩn SQL, nhưng không tạo khác biệt thực thi so với `RESTRICT` trong InnoDB.

### 5.2. Hành vi mặc định

Nếu không khai báo `ON DELETE` hoặc `ON UPDATE`, InnoDB mặc định từ chối thay đổi làm vi phạm quan hệ, tương đương `RESTRICT`/`NO ACTION`. Để schema dễ đọc và ít gây hiểu nhầm, có thể ghi tường minh hành động quan trọng, đặc biệt với quan hệ có rủi ro xóa dây chuyền.

## 6. Chọn hành động theo vòng đời dữ liệu

| Quan hệ nghiệp vụ | Hành động thường cân nhắc | Lý do |
|---|---|---|
| Đơn hàng và dòng hàng của một bản nháp có thể xóa toàn bộ | `ON DELETE CASCADE` | Dòng hàng không có ý nghĩa nếu bản nháp bị xóa |
| Khách hàng và hóa đơn/giao dịch đã phát sinh | `ON DELETE RESTRICT` | Bảo vệ lịch sử và dữ liệu cần kiểm toán |
| Bài viết và người biên tập tùy chọn | `ON DELETE SET NULL` | Bài viết vẫn tồn tại khi người biên tập rời hệ thống |
| Bảng nối user-role | `ON DELETE CASCADE` từ user hoặc role tới hàng nối | Quan hệ gán vai trò mất ý nghĩa khi một đầu mối bị xóa |
| Mã danh mục có thể đổi nhưng bản ghi con vẫn liên kết | `ON UPDATE CASCADE` hoặc dùng surrogate key ổn định | Duy trì liên kết khi khóa được tham chiếu thay đổi |
| Bản ghi lịch sử cần giữ danh tính chủ thể ban đầu | `RESTRICT`, soft delete hoặc lưu snapshot | Không để cascade/SET NULL làm mất ngữ cảnh lịch sử |

Đây là gợi ý thiết kế, không phải quy tắc áp dụng máy móc. Câu hỏi quan trọng là: hàng con có thể tồn tại độc lập không, lịch sử có cần giữ không, và ai có quyền quyết định xóa? Hành động khóa ngoại cần phản ánh chính sách dữ liệu đã thống nhất với nghiệp vụ.

## 7. Hành vi trong transaction và khóa

Các thao tác tham chiếu của InnoDB được thực hiện trong transaction của câu lệnh cha. Khi xóa cascade, InnoDB phải tìm các hàng con liên quan, khóa những hàng cần thiết và áp dụng thay đổi. Index ở cột khóa ngoại giúp tìm hàng con hiệu quả hơn và giảm công việc quét bảng.

Ví dụ transaction xóa một bản nháp:

```sql
START TRANSACTION;

DELETE FROM orders_cascade
WHERE order_id = 1;

-- Có thể kiểm tra trạng thái các bảng liên quan trong transaction.
SELECT COUNT(*)
FROM order_items_cascade
WHERE order_id = 1;

COMMIT;
```

Nếu cần hủy thao tác trước khi commit, `ROLLBACK` sẽ hoàn tác việc xóa cha và các hàng con đã bị cascade, miễn là các bảng dùng transactional engine như InnoDB.

### 7.1. Xóa nhiều hàng cha có thể tạo cascade lớn

```sql
DELETE FROM orders_cascade
WHERE order_id BETWEEN 1000 AND 5000;
```

Một câu lệnh xóa nhiều đơn hàng có thể kéo theo rất nhiều dòng con. Tác động có thể gồm:

- Nhiều row lock và thời gian giữ lock dài.
- Undo log lớn, redo log và I/O tăng.
- Replication hoặc binary log tăng dung lượng và độ trễ áp dụng.
- Các transaction khác bị chờ hoặc gặp deadlock.
- Thời gian rollback tăng nếu thao tác thất bại giữa chừng.

Trước khi chạy trên dữ liệu lớn, hãy ước lượng số hàng con, kiểm tra index, chạy thử trên staging và chia batch theo khóa ổn định nếu nghiệp vụ cho phép. Chia batch cần được thiết kế sao cho không làm lộ trạng thái dữ liệu trung gian trái với yêu cầu nghiệp vụ.

### 7.2. Deadlock và thứ tự thao tác

Nhiều transaction cùng xóa/cập nhật các hàng cha-con theo thứ tự khác nhau có thể tạo deadlock. InnoDB sẽ chọn một transaction làm nạn nhân và rollback transaction đó. Ứng dụng phải có cơ chế retry có giới hạn cho lỗi deadlock/lock timeout, đồng thời giữ transaction ngắn và truy cập các bảng theo thứ tự nhất quán.

Không giả định `CASCADE` miễn phí hoặc luôn nhanh hơn việc ứng dụng tự xóa từng bảng. Cascade giúp bảo đảm quan hệ ở database, nhưng vẫn cần tính chi phí khóa và lượng dữ liệu bị ảnh hưởng.

## 8. Cascade và trigger

Một điểm dễ bị bỏ sót: các thao tác do foreign key cascade thực hiện trong InnoDB không kích hoạt trigger trên bảng con. Ví dụ, nếu xóa một hàng cha làm InnoDB tự động xóa các hàng con bằng `ON DELETE CASCADE`, trigger `AFTER DELETE` được khai báo trên bảng con sẽ không chạy cho các hàng bị xóa do cascade.

Điều này có ý nghĩa với audit log và đồng bộ dữ liệu. Nếu hệ thống dựa vào trigger ở bảng con để ghi lịch sử hoặc phát sự kiện, không thể giả định mọi thao tác cascade đều tạo audit record. Hãy thiết kế audit ở cấp nghiệp vụ hoặc ghi nhận rõ thao tác cha và phạm vi ảnh hưởng. Nếu cần audit từng hàng con, ứng dụng hoặc quy trình database phải chủ động xử lý theo thiết kế được kiểm thử.

Trigger gắn trực tiếp với thao tác SQL được thực hiện trên bảng cha vẫn tuân theo quy tắc trigger của bảng cha; lưu ý ở đây là hành động cascade tự động trên bảng con không kích hoạt trigger con.

## 9. Khóa ngoại composite và hành động tham chiếu

Một khóa ngoại có thể gồm nhiều cột. Khi dùng `CASCADE`, tất cả thành phần khóa ngoại tương ứng được cập nhật theo khóa cha; với `SET NULL`, các cột khóa ngoại phía con được đặt `NULL`.

Ví dụ quan hệ tenant và project dùng khóa ghép:

```sql
CREATE TABLE tenant_project (
    tenant_id BIGINT UNSIGNED NOT NULL,
    project_id BIGINT UNSIGNED NOT NULL,
    project_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (tenant_id, project_id)
) ENGINE=InnoDB;

CREATE TABLE project_task (
    task_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    project_id BIGINT UNSIGNED NOT NULL,
    task_name VARCHAR(200) NOT NULL,
    PRIMARY KEY (task_id),
    KEY idx_project_task_project (tenant_id, project_id),
    CONSTRAINT fk_project_task_project
        FOREIGN KEY (tenant_id, project_id)
        REFERENCES tenant_project (tenant_id, project_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB;
```

Xóa một project trong một tenant sẽ xóa các task của đúng cặp khóa đó. Không chỉ kiểm tra riêng `project_id`, vì cùng một giá trị project có thể tồn tại ở tenant khác trong mô hình multi-tenant.

Với `SET NULL` trên khóa ghép, tất cả cột thành phần phía con cần cho phép `NULL`. Nếu chỉ một cột được phép null, hành động đặt toàn bộ khóa ngoại thành null không thể đáp ứng thiết kế `NOT NULL` còn lại.

## 10. Giới hạn và lưu ý khi thiết kế khóa ngoại

- InnoDB yêu cầu bảng cha và bảng con dùng engine hỗ trợ foreign key tương thích; ví dụ điển hình là cả hai dùng InnoDB.
- Các cột tham chiếu phải có kiểu tương thích; với số nguyên cần khớp kích thước và signedness.
- Cột được tham chiếu nên là `PRIMARY KEY` hoặc `UNIQUE KEY`; tránh dựa vào khóa cha không unique, vì kiểu tham chiếu không chuẩn này bị hạn chế/deprecated trong các phiên bản MySQL mới.
- Cột khóa ngoại phía con cần index phù hợp; nên khai báo index rõ ràng.
- `SET NULL` yêu cầu cột con nullable.
- InnoDB kiểm tra khóa ngoại ngay, không hỗ trợ deferred checking tới cuối transaction.
- `SET DEFAULT` không được InnoDB hỗ trợ cho hành động tham chiếu; không dùng nó thay cho `SET NULL` hoặc giá trị mặc định của ứng dụng.
- Tên constraint cần duy nhất trong phạm vi schema theo quy tắc của MySQL; đặt tên dễ nhận diện để việc xử lý lỗi và migration thuận tiện.

### 10.1. Không tắt foreign_key_checks để thay hành động

MySQL cho phép tắt kiểm tra khóa ngoại trong session:

```sql
SET SESSION foreign_key_checks = 0;
```

Tùy chọn này hữu ích trong một số quy trình import hoặc khôi phục có kiểm soát, nhưng không phải cách sửa lỗi thiết kế. Khi bật lại:

```sql
SET SESSION foreign_key_checks = 1;
```

MySQL không tự quét và xác minh lại toàn bộ dữ liệu đã được nạp trong lúc tắt kiểm tra. Dữ liệu mồ côi có thể còn tồn tại. Chỉ dùng trong quy trình có kế hoạch kiểm tra dữ liệu độc lập, quyền hạn phù hợp và môi trường được kiểm soát.

## 11. Kiểm tra hành động tham chiếu trong schema

Đọc định nghĩa bảng:

```sql
SHOW CREATE TABLE order_items_cascade\G
```

Thông tin chi tiết constraint có thể truy vấn từ `information_schema`:

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
```

Xem các cột thuộc khóa ngoại:

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME,
    ORDINAL_POSITION
FROM information_schema.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;
```

Trước migration, đối chiếu `DELETE_RULE` và `UPDATE_RULE` với yêu cầu nghiệp vụ. Không chỉ đọc tên constraint; tên như `fk_order_customer` không cho biết hành động thực tế.

## 12. Thay đổi hành động tham chiếu

MySQL không cung cấp cú pháp `ALTER CONSTRAINT` riêng để đổi trực tiếp `ON DELETE` hoặc `ON UPDATE` của foreign key. Thông thường cần drop khóa ngoại cũ rồi tạo lại với hành động mong muốn.

Ví dụ:

```sql
ALTER TABLE order_items_cascade
    DROP FOREIGN KEY fk_order_items_order_cascade;

ALTER TABLE order_items_cascade
    ADD CONSTRAINT fk_order_items_order_cascade
    FOREIGN KEY (order_id)
    REFERENCES orders_cascade (order_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;
```

Trước khi drop/recreate:

1. Xác nhận tên constraint và định nghĩa hiện tại bằng `SHOW CREATE TABLE`.
2. Kiểm tra dữ liệu con không mồ côi và kiểu cột tương thích.
3. Đánh giá lock, metadata lock, thời gian DDL và ảnh hưởng tới ứng dụng.
4. Có kế hoạch triển khai và rollback; trong thời gian thay đổi, tránh để ứng dụng ghi dữ liệu vi phạm quan hệ.
5. Sau khi tạo lại, xác minh bằng `SHOW CREATE TABLE` và `information_schema.REFERENTIAL_CONSTRAINTS`.

Nếu thao tác drop/add không nằm trong một quy trình DDL nguyên tử phù hợp với phiên bản/công cụ, có thể xuất hiện khoảng thời gian không có constraint. Hãy thực hiện trong maintenance window hoặc dùng chiến lược migration đã được kiểm thử.

## 13. Bài thực hành

Thực hiện trên schema lab riêng, không dùng dữ liệu production:

1. Tạo cặp bảng cha-con với `ON DELETE CASCADE`; chèn một hàng cha và nhiều hàng con, xóa cha rồi xác minh hàng con đã bị xóa.
2. Tạo quan hệ với `ON DELETE SET NULL`; xóa hàng cha và kiểm tra hàng con còn tồn tại với khóa ngoại `NULL`.
3. Tạo quan hệ `ON DELETE RESTRICT`; thử xóa cha đang được tham chiếu và ghi lại lỗi MySQL.
4. So sánh `RESTRICT` với `NO ACTION` trên InnoDB; xác nhận cả hai từ chối thao tác ngay khi còn hàng con.
5. Tạo một khóa nghiệp vụ có thể thay đổi và thử `ON UPDATE CASCADE`; quan sát giá trị khóa ngoại ở bảng con.
6. Tạo chuỗi ba bảng cha-con-cháu với cascade, xóa hàng ở gốc và đếm số hàng bị ảnh hưởng ở từng cấp.
7. Tạo trigger `AFTER DELETE` trên bảng con trong lab, sau đó xóa hàng cha bằng cascade; kiểm tra trigger con không ghi audit cho hàng bị xóa do cascade.
8. Truy vấn `information_schema.REFERENTIAL_CONSTRAINTS` để lập báo cáo hành động `DELETE_RULE`/`UPDATE_RULE` của từng constraint.
9. Thử thay đổi một foreign key bằng drop/recreate, xác minh lại schema và dữ liệu sau migration.
10. Viết quyết định thiết kế cho ba quan hệ: đơn hàng-dòng hàng, khách hàng-hóa đơn và bài viết-người biên tập; giải thích hành động được chọn dựa trên vòng đời dữ liệu.

Bạn hoàn thành bài khi dự đoán đúng ảnh hưởng của thao tác xóa/cập nhật ở bảng cha, chọn được hành động theo chính sách dữ liệu và kiểm tra được quy tắc thực tế từ metadata của MySQL.

## 14. Nguyên tắc cần ghi nhớ

- `ON DELETE` xử lý khi xóa hàng cha; `ON UPDATE` xử lý khi đổi khóa được tham chiếu ở cha.
- `CASCADE` xóa hoặc cập nhật hàng con theo thay đổi ở cha; cân nhắc kỹ nguy cơ xóa dây chuyền.
- `SET NULL` giữ hàng con nhưng bỏ liên kết; mọi cột khóa ngoại cần cho phép `NULL`.
- `RESTRICT` chặn thao tác ở cha khi còn hàng con; `NO ACTION` tương đương `RESTRICT` và được kiểm tra ngay trong InnoDB.
- Không dùng cascade để xóa dữ liệu lịch sử cần kiểm toán hoặc giữ theo nghiệp vụ.
- Cascade có thể tạo nhiều row lock, undo/redo và độ trễ replication; luôn có index ở phía con.
- Hành động cascade của InnoDB trên bảng con không kích hoạt trigger của bảng con.
- Không tắt `foreign_key_checks` như một cách bỏ qua lỗi thiết kế; bật lại không tự xác minh dữ liệu đã import.
- Kiểm tra `SHOW CREATE TABLE` và `information_schema.REFERENTIAL_CONSTRAINTS` trước/sau migration.
- Thiết kế khóa chính ổn định để giảm nhu cầu `ON UPDATE CASCADE`.
