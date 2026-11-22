# PRIMARY KEY, NOT NULL và CHECK trong thiết kế giao dịch

Một transaction có thể được viết đúng về mặt thứ tự đọc và ghi nhưng vẫn tạo ra dữ liệu không hợp lệ nếu ứng dụng không bảo vệ các quy tắc nghiệp vụ ở nơi dữ liệu được lưu. Ví dụ, hai yêu cầu cùng tạo một khách hàng có chung mã, một lần cập nhật làm số lượng tồn kho âm, hoặc một hàng chứa khoảng thời gian kết thúc trước thời điểm bắt đầu.

`PRIMARY KEY`, `NOT NULL` và `CHECK` là các constraint cơ bản để cơ sở dữ liệu bảo vệ những quy tắc này. Chúng có vai trò khác nhau: khóa chính định danh duy nhất một hàng, `NOT NULL` yêu cầu một giá trị phải hiện diện, còn `CHECK` xác nhận biểu thức trên hàng sau khi ghi thỏa điều kiện. Khi được đặt đúng chỗ, constraint bảo vệ dữ liệu từ mọi đường ghi và phối hợp với cơ chế transaction của hệ quản trị.

Bài học này giải thích cách chọn ba loại constraint, cách chúng hoạt động khi nhiều transaction chạy đồng thời, những giới hạn của `CHECK` và cách kết hợp constraint với cập nhật nguyên tử.

## 1. Constraint bảo vệ dữ liệu ở đâu?

Một ứng dụng thường kiểm tra dữ liệu trước khi gửi câu lệnh SQL. Ví dụ, màn hình có thể yêu cầu mã khách hàng chưa tồn tại, số lượng phải lớn hơn 0 và ngày kết thúc phải sau ngày bắt đầu. Những kiểm tra này giúp người dùng nhận phản hồi sớm, nhưng chúng không đủ để bảo đảm tính đúng đắn khi có nhiều ứng dụng hoặc transaction cùng ghi.

Hãy xem quy trình tạo tài khoản:

```sql
-- T1
SELECT customer_id
FROM customer
WHERE email = 'mai@example.com';
-- Không có hàng

-- T2 chạy đồng thời và cũng không tìm thấy hàng
SELECT customer_id
FROM customer
WHERE email = 'mai@example.com';

-- Cả hai ứng dụng đều quyết định email còn trống
INSERT INTO customer(email) VALUES ('mai@example.com');
```

Hai lần kiểm tra có thể cùng trả về kết quả rỗng vì mỗi transaction chưa nhìn thấy thay đổi chưa commit của transaction kia. Nếu chỉ dựa vào câu `SELECT` trước `INSERT`, cả hai có thể cùng thử tạo dữ liệu trùng.

Constraint đặt trong schema để cơ sở dữ liệu kiểm tra tại nơi ghi. Vì vậy, quy tắc vẫn được áp dụng dù dữ liệu đến từ ứng dụng web, batch job, câu SQL thủ công hay một dịch vụ khác. Ứng dụng vẫn nên kiểm tra sớm để đưa ra thông báo dễ hiểu, nhưng constraint mới là hàng rào cuối cùng tại nơi dữ liệu được lưu.

## 2. PRIMARY KEY: định danh duy nhất một hàng

`PRIMARY KEY` xác định một hàng trong bảng. Giá trị khóa chính phải duy nhất và không được `NULL`. Một bảng chỉ có một constraint primary key, nhưng khóa đó có thể gồm một cột hoặc nhiều cột.

Ví dụ khóa chính đơn:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    email       VARCHAR(320) NOT NULL,
    full_name   VARCHAR(200) NOT NULL
);
```

Ở đây `customer_id` định danh từng khách hàng. Cơ sở dữ liệu từ chối việc chèn hai hàng có cùng `customer_id`, kể cả khi hai lệnh INSERT đến từ hai transaction đồng thời.

### Khóa chính ghép

Khi một hàng chỉ có ý nghĩa duy nhất trong phạm vi một nhóm, có thể dùng nhiều cột làm khóa chính:

```sql
CREATE TABLE course_enrollment (
    course_id  BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (course_id, student_id)
);
```

Khóa chính ghép bảo đảm một sinh viên chỉ có một hàng đăng ký cho một khóa học. Hai hàng có thể dùng cùng `course_id` hoặc cùng `student_id`, nhưng cặp giá trị phải khác nhau.

### PRIMARY KEY khác UNIQUE như thế nào?

`PRIMARY KEY` và `UNIQUE` đều bảo vệ tính duy nhất, nhưng ý nghĩa thiết kế khác nhau:

| Đặc điểm | PRIMARY KEY | UNIQUE |
| --- | --- | --- |
| Số constraint trên một bảng | Một | Có thể có nhiều |
| Giá trị trùng nhau | Không được phép | Không được phép theo quy tắc của constraint |
| NULL | Không được phép | Cách xử lý NULL khác nhau giữa các hệ quản trị và dạng chỉ mục |
| Vai trò thường gặp | Định danh chính của hàng | Bảo vệ các khóa nghiệp vụ bổ sung |

Ví dụ, `customer_id` có thể là primary key còn `email` có unique constraint. Nếu email là thông tin định danh nghiệp vụ cần duy nhất, hãy khai báo constraint thay vì chỉ kiểm tra ở tầng ứng dụng:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    email       VARCHAR(320) NOT NULL UNIQUE,
    full_name   VARCHAR(200) NOT NULL
);
```

Hành vi của `UNIQUE` khi có nhiều giá trị `NULL` không giống nhau ở mọi hệ quản trị. Nếu yêu cầu nghiệp vụ là mỗi hàng phải có email và email không được trùng, kết hợp `NOT NULL` với `UNIQUE` để diễn đạt đầy đủ quy tắc.

### Chọn khóa tự nhiên hay khóa thay thế

Khóa tự nhiên dùng dữ liệu có ý nghĩa nghiệp vụ, ví dụ mã quốc gia hoặc mã sản phẩm do tổ chức quy định. Khóa thay thế (surrogate key) là giá trị được tạo chủ yếu để định danh, ví dụ số nguyên tăng dần hoặc UUID.

Một khóa chính tốt nên ổn định, không phụ thuộc vào thông tin có thể thay đổi thường xuyên và thuận tiện cho các bảng khác tham chiếu. Email thường có thể thay đổi nên thường phù hợp làm unique key hơn là primary key. Có thể dùng `customer_id` làm khóa chính và giữ `email` bằng unique constraint.

Không nên thay đổi primary key tùy tiện sau khi tạo dữ liệu tham chiếu. Nếu khóa chính thay đổi, các khóa ngoại và những hệ thống tích hợp có thể phải cập nhật theo. Một định danh ổn định giúp transaction và quan hệ giữa các bảng dễ quản lý hơn.

## 3. NOT NULL: giá trị bắt buộc phải hiện diện

`NOT NULL` yêu cầu một cột phải có giá trị trong mọi hàng. Nó phù hợp với dữ liệu mà thiếu giá trị sẽ làm hàng không có ý nghĩa hoặc khiến quy tắc nghiệp vụ không thể được xác định.

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    quantity   INTEGER NOT NULL,
    version    BIGINT NOT NULL DEFAULT 0
);
```

Trong ví dụ này, mỗi hàng tồn kho phải có mã sản phẩm, số lượng và phiên bản. `DEFAULT 0` cung cấp giá trị khi INSERT bỏ qua cột `version`; `NOT NULL` bảo đảm kết quả cuối cùng không thể là NULL.

### NULL không giống 0 hoặc chuỗi rỗng

`NULL` biểu thị giá trị chưa biết, không được cung cấp hoặc không áp dụng tùy ngữ cảnh. Nó khác với:

- `0`: một giá trị số đã biết.
- `''`: chuỗi rỗng.
- `FALSE`: giá trị Boolean sai.
- Một giá trị mặc định như `0` hoặc `'PENDING'`.

Nếu số lượng tồn kho không được phép thiếu, dùng `NOT NULL`. Nếu nghiệp vụ cho phép chưa biết số lượng, cần xác định rõ cách các phép tính và câu truy vấn xử lý NULL.

### DEFAULT không thay thế NOT NULL

`DEFAULT` được dùng khi câu INSERT không cung cấp cột hoặc yêu cầu dùng giá trị mặc định. Nó không nhất thiết thay thế một giá trị NULL được truyền tường minh.

```sql
CREATE TABLE task (
    task_id BIGINT PRIMARY KEY,
    status  VARCHAR(20) NOT NULL DEFAULT 'PENDING'
);
```

Hai lệnh sau có ý nghĩa khác nhau:

```sql
-- Bỏ qua status: cơ sở dữ liệu dùng DEFAULT 'PENDING'.
INSERT INTO task(task_id) VALUES (1);

-- Truyền NULL tường minh: vi phạm NOT NULL.
INSERT INTO task(task_id, status) VALUES (2, NULL);
```

Ứng dụng không nên nghĩ rằng có DEFAULT thì cột sẽ không bao giờ nhận NULL. `NOT NULL` mới là constraint diễn đạt yêu cầu bắt buộc.

### NOT NULL trong khóa ghép và khóa ngoại

Các cột trong primary key luôn không được NULL. Với khóa ngoại, việc có cho phép NULL hay không là quyết định riêng của thiết kế. Nếu một đơn hàng bắt buộc phải thuộc về khách hàng, cột `customer_id` nên là `NOT NULL` và đồng thời tham chiếu đến khóa của bảng customer:

```sql
CREATE TABLE orders (
    order_id    BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(customer_id)
);
```

Foreign key bảo đảm giá trị được tham chiếu tồn tại theo quy tắc của constraint; `NOT NULL` bảo đảm quan hệ đó không bị bỏ trống. Hai constraint giải quyết hai điều kiện khác nhau.

## 4. CHECK: kiểm tra điều kiện trên một hàng

`CHECK` yêu cầu một biểu thức điều kiện không được đánh giá là FALSE đối với hàng được thêm hoặc cập nhật. Nó thường phù hợp với các quy tắc có thể xác định từ các cột của chính hàng đó.

Ví dụ:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    quantity   INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT ck_inventory_quantity CHECK (quantity >= 0),
    CONSTRAINT ck_inventory_price CHECK (unit_price >= 0)
);
```

Các constraint trên bảo vệ hai quy tắc:

- Số lượng tồn kho không được âm.
- Đơn giá không được âm.

Khi ứng dụng gửi `UPDATE` đặt `quantity = -5`, cơ sở dữ liệu từ chối thay đổi vì hàng mới vi phạm `CHECK (quantity >= 0)`.

### CHECK trên nhiều cột của cùng một hàng

Một constraint có thể kết hợp nhiều cột:

```sql
CREATE TABLE reservation (
    reservation_id BIGINT PRIMARY KEY,
    start_time     TIMESTAMP NOT NULL,
    end_time       TIMESTAMP NOT NULL,
    guest_count    INTEGER NOT NULL,
    CONSTRAINT ck_reservation_time CHECK (start_time < end_time),
    CONSTRAINT ck_reservation_guests CHECK (guest_count > 0)
);
```

`CHECK (start_time < end_time)` bảo đảm thời điểm kết thúc sau thời điểm bắt đầu. `CHECK (guest_count > 0)` bảo đảm số khách là số dương.

Có thể dùng biểu thức `IN`, so sánh, `BETWEEN`, toán tử số học hoặc kết hợp các điều kiện:

```sql
CREATE TABLE payment (
    payment_id BIGINT PRIMARY KEY,
    amount     DECIMAL(12, 2) NOT NULL,
    status     VARCHAR(20) NOT NULL,
    CONSTRAINT ck_payment_amount CHECK (amount > 0),
    CONSTRAINT ck_payment_status
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
);
```

Các biểu thức trên kiểm tra từng hàng. Chúng không thể tự bảo đảm rằng tổng tiền của mọi payment thuộc một đơn hàng không vượt tổng giá trị đơn hàng; đó là quy tắc trên nhiều hàng và cần thiết kế đồng bộ hóa khác.

## 5. CHECK và NULL: điểm rất dễ bỏ sót

SQL dùng logic ba giá trị: TRUE, FALSE và UNKNOWN. Khi một biểu thức so sánh với NULL, kết quả thường là UNKNOWN. Trong nhiều hệ quản trị, một `CHECK` chỉ từ chối hàng khi biểu thức là FALSE; TRUE và UNKNOWN được chấp nhận.

Ví dụ:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    quantity INTEGER,
    CONSTRAINT ck_quantity_nonnegative CHECK (quantity >= 0)
);
```

Với `quantity = -1`, biểu thức là FALSE nên hàng bị từ chối. Với `quantity = 5`, biểu thức là TRUE nên hàng được chấp nhận. Nhưng với `quantity = NULL`, biểu thức `NULL >= 0` là UNKNOWN; trong các hệ quản trị phổ biến, CHECK không từ chối giá trị này.

Nếu quantity bắt buộc phải có, hãy kết hợp cả hai constraint:

```sql
quantity INTEGER NOT NULL,
CONSTRAINT ck_quantity_nonnegative CHECK (quantity >= 0)
```

Điều tương tự xảy ra với trạng thái:

```sql
CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
```

Nếu `status` là NULL, biểu thức có thể là UNKNOWN và CHECK không thay thế được `NOT NULL`. Vì vậy, hãy tách hai yêu cầu thành hai constraint rõ ràng:

```sql
status VARCHAR(20) NOT NULL,
CONSTRAINT ck_status CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
```

Khi thiết kế CHECK có thể gặp NULL, hãy tự hỏi ba trường hợp: biểu thức trả TRUE thì sao, FALSE thì sao, UNKNOWN thì sao? Nếu UNKNOWN không hợp lệ theo nghiệp vụ, cần thêm `NOT NULL` hoặc viết biểu thức xử lý NULL một cách tường minh.

## 6. Constraint được kiểm tra khi nào trong transaction?

Constraint được kiểm tra trong quá trình ghi dữ liệu. Tùy loại constraint và hệ quản trị, việc kiểm tra có thể diễn ra ngay khi câu lệnh thay đổi hàng hoặc được trì hoãn đến cuối transaction nếu constraint và engine hỗ trợ deferrable.

### Constraint kiểm tra ngay

Phần lớn `NOT NULL` và `CHECK` được kiểm tra khi câu INSERT/UPDATE thực hiện. Ví dụ:

```sql
BEGIN;

UPDATE inventory
SET quantity = -1
WHERE product_id = 501;
-- CHECK (quantity >= 0) bị vi phạm.

ROLLBACK;
```

Nếu giá trị mới vi phạm constraint, database báo lỗi. Transaction không thể coi câu lệnh đó là một cập nhật thành công. Cách transaction tiếp tục sau lỗi phụ thuộc hệ quản trị; một số hệ thống đánh dấu transaction ở trạng thái lỗi cho đến khi rollback, một số hệ thống cho phép xử lý ở phạm vi statement hoặc savepoint. Ứng dụng cần xử lý theo driver và database cụ thể.

### Constraint trì hoãn

Một số hệ quản trị cho phép khai báo một số loại constraint là `DEFERRABLE`, để kiểm tra ở cuối transaction thay vì ngay tại từng statement. Điều này hữu ích khi một transaction phải đi qua trạng thái trung gian tạm thời vi phạm quy tắc nhưng trạng thái cuối cùng hợp lệ. Khả năng trì hoãn và những loại constraint được phép trì hoãn khác nhau giữa các sản phẩm; không nên giả định mọi `PRIMARY KEY`, `NOT NULL` hoặc `CHECK` đều có thể deferred.

Ví dụ minh họa với một unique constraint deferrable trên hệ quản trị hỗ trợ cú pháp này:

```sql
-- Cú pháp minh họa kiểu PostgreSQL.
CREATE TABLE display_order (
    item_id BIGINT PRIMARY KEY,
    position INTEGER NOT NULL,
    CONSTRAINT uq_display_position
        UNIQUE (position)
        DEFERRABLE INITIALLY DEFERRED
);

BEGIN;

-- Có thể đổi vị trí hai item trong cùng transaction.
UPDATE display_order SET position = 2 WHERE item_id = 1;
UPDATE display_order SET position = 1 WHERE item_id = 2;

COMMIT;
```

Trong ví dụ, constraint unique được kiểm tra vào cuối transaction theo cấu hình deferred, cho phép các bước trung gian tạm thời trùng vị trí. Cú pháp này không phải SQL dùng được trên mọi hệ quản trị. Nếu hệ thống không hỗ trợ deferred constraint cho loại quy tắc cần dùng, phải thiết kế thứ tự cập nhật hoặc cách đánh số trung gian phù hợp.

### Kiểm tra constraint khi COMMIT

Nếu một constraint deferred bị vi phạm tại thời điểm commit, commit thất bại. Ứng dụng phải xử lý lỗi như một transaction không hoàn tất; không được trả về thành công cho người dùng chỉ vì các câu lệnh trước đó đã chạy xong.

## 7. Constraint và transaction khi nhiều người ghi đồng thời

Constraint không chỉ kiểm tra dữ liệu tuần tự. Hệ quản trị phải phối hợp việc kiểm tra với cơ chế khóa, chỉ mục và kiểm soát đồng thời để bảo vệ tính duy nhất và tính hợp lệ khi nhiều transaction cùng ghi.

### Hai transaction cùng chèn một primary key

Giả sử `customer_id = 900` chưa tồn tại. T1 và T2 cùng thử INSERT:

```sql
-- T1
BEGIN;
INSERT INTO customer(customer_id, email, full_name)
VALUES (900, 'a@example.com', 'An');

-- T2 chạy đồng thời
BEGIN;
INSERT INTO customer(customer_id, email, full_name)
VALUES (900, 'b@example.com', 'Binh');
```

Database phải ngăn hai hàng cùng có primary key 900. Một transaction có thể chờ kết quả của transaction kia. Nếu T1 commit, T2 sẽ bị từ chối vì trùng khóa; nếu T1 rollback, T2 có thể tiếp tục và chèn thành công tùy cách xử lý của engine.

Điều quan trọng là không cần dựa vào câu `SELECT` kiểm tra ID trước INSERT để bảo vệ tính duy nhất. Primary key và unique index của database điều phối cả những transaction chưa nhìn thấy thay đổi của nhau.

### Hai transaction cùng cập nhật một hàng với CHECK

Giả sử tồn kho không được âm:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL,
    CONSTRAINT ck_inventory_quantity CHECK (quantity >= 0)
);
```

Hai transaction cùng muốn trừ hàng tồn. Một cách viết an toàn là đưa điều kiện số lượng vào chính câu UPDATE:

```sql
UPDATE inventory
SET quantity = quantity - :requested
WHERE product_id = :product_id
  AND quantity >= :requested;
```

Nếu số lượng hiện tại không đủ, câu lệnh không cập nhật hàng. `CHECK (quantity >= 0)` là lớp bảo vệ bổ sung để mọi đường ghi đều không thể lưu số lượng âm. Vì hai transaction cùng cập nhật một hàng, cơ chế đồng thời của database sẽ điều phối xung đột ghi; hành vi chờ hoặc báo lỗi cụ thể phụ thuộc engine và isolation level.

Ứng dụng vẫn cần kiểm tra số hàng được cập nhật. Nếu bằng 0, có thể sản phẩm không tồn tại hoặc không đủ hàng. Nếu cần phân biệt hai trường hợp, hãy đọc lại trong transaction phù hợp hoặc trả kết quả nghiệp vụ rõ ràng.

## 8. CHECK không thay thế constraint nhiều hàng

`CHECK` thường được thiết kế để xác nhận một biểu thức trên chính hàng đang được INSERT hoặc UPDATE. Không nên dùng nó như thể nó tự khóa hoặc kiểm tra an toàn các hàng khác trong bảng.

Ví dụ quy tắc “tổng số chỗ đã đặt không vượt sức chứa” có thể được kiểm tra bằng:

```sql
SELECT SUM(guest_count)
FROM reservation
WHERE room_id = 7;
```

Nhưng hai transaction có thể cùng đọc tổng cũ rồi chèn hai hàng mới khác nhau. Một CHECK trên từng hàng reservation không biết tổng của các hàng khác, nên không tự bảo vệ được sức chứa.

Tương tự, `CHECK (start_time < end_time)` bảo vệ thứ tự thời gian của từng reservation, nhưng không ngăn hai reservation khác nhau có khoảng thời gian giao nhau. `CHECK (on_call IN (TRUE, FALSE))` kiểm tra giá trị trạng thái của một bác sĩ, nhưng không bảo đảm luôn còn ít nhất một bác sĩ đang trực.

Với bất biến nhiều hàng, hãy cân nhắc:

- `UNIQUE` hoặc khóa chính nếu quy tắc thực chất là tính duy nhất của một khóa nghiệp vụ.
- Exclusion constraint nếu hệ quản trị hỗ trợ ràng buộc không giao nhau cho các khoảng giá trị.
- Một hàng tổng hợp hoặc hàng guard mà mọi transaction liên quan đều cập nhật trong cùng transaction.
- Khóa phạm vi/predicate hoặc isolation level `SERIALIZABLE` khi quy tắc phụ thuộc vào một tập hàng và không thể biểu diễn bằng constraint đơn giản.

Trigger cũng không tự động giải quyết được vấn đề đồng thời. Nếu trigger tính tổng từ snapshot rồi cho phép hai transaction cùng chèn, nó có thể gặp cùng race condition. Cần thiết kế khóa hoặc isolation phù hợp bên trong cơ chế đó.

## 9. Thiết kế transaction kết hợp constraint

Một transaction tốt thường có ba lớp bảo vệ:

1. **Kiểm tra đầu vào ở ứng dụng:** đưa ra thông báo sớm và thân thiện.
2. **Câu lệnh có điều kiện:** giảm race condition bằng cách đưa điều kiện nghiệp vụ đơn giản vào `WHERE` hoặc thao tác nguyên tử.
3. **Constraint ở database:** bảo vệ trạng thái đã lưu dù có đường ghi khác hoặc lỗi trong ứng dụng.

Ví dụ xử lý đơn hàng:

```sql
CREATE TABLE order_line (
    order_line_id BIGINT PRIMARY KEY,
    order_id      BIGINT NOT NULL,
    product_id    BIGINT NOT NULL,
    quantity      INTEGER NOT NULL,
    unit_price    DECIMAL(12, 2) NOT NULL,
    CONSTRAINT ck_order_line_quantity CHECK (quantity > 0),
    CONSTRAINT ck_order_line_price CHECK (unit_price >= 0)
);
```

Transaction tạo đơn hàng có thể thực hiện:

```sql
BEGIN;

INSERT INTO orders(order_id, customer_id, status)
VALUES (:order_id, :customer_id, 'PENDING');

UPDATE inventory
SET quantity = quantity - :requested
WHERE product_id = :product_id
  AND quantity >= :requested;

-- Nếu không cập nhật đúng 1 hàng: rollback vì thiếu hàng.

INSERT INTO order_line(
    order_line_id, order_id, product_id, quantity, unit_price
)
VALUES (
    :line_id, :order_id, :product_id, :requested, :unit_price
);

COMMIT;
```

Trong thực tế cần có thêm primary key, foreign key, NOT NULL và CHECK phù hợp cho các bảng `orders` và `inventory`. Nếu bất kỳ thao tác nào thất bại, ứng dụng rollback transaction để không tạo đơn hàng mà không trừ kho, hoặc trừ kho mà không có chi tiết đơn hàng.

Constraint ở `order_line` bảo vệ các hàng chi tiết; transaction bảo đảm các thay đổi liên quan cùng thành công hoặc cùng bị hủy. Nếu có nhiều dòng sản phẩm, ứng dụng cần cập nhật tồn kho cho từng sản phẩm trong cùng transaction và xử lý xung đột theo quy tắc nhất quán.

## 10. Đặt tên và quản lý constraint

Nên đặt tên constraint có ý nghĩa để lỗi từ database dễ xác định hơn:

```sql
CREATE TABLE payment (
    payment_id BIGINT PRIMARY KEY,
    order_id   BIGINT NOT NULL,
    amount     DECIMAL(12, 2) NOT NULL,
    status     VARCHAR(20) NOT NULL,
    CONSTRAINT ck_payment_amount_positive CHECK (amount > 0),
    CONSTRAINT ck_payment_status_allowed
        CHECK (status IN ('PENDING', 'PAID', 'FAILED'))
);
```

Tên như `ck_payment_amount_positive` cho biết constraint nào bị vi phạm. Khi ứng dụng xử lý lỗi, nên dựa vào mã lỗi hoặc tên constraint do driver/database cung cấp thay vì phân tích chuỗi thông báo tự do nếu có thể.

Khi thêm constraint vào bảng đã có dữ liệu, các hàng cũ có thể không thỏa quy tắc mới. Migration cần kiểm tra dữ liệu hiện tại, sửa hoặc loại bỏ dữ liệu không hợp lệ theo quyết định nghiệp vụ, rồi mới bật constraint. Một số hệ quản trị có tùy chọn kiểm tra hoặc xác thực constraint theo từng giai đoạn; cú pháp và mức khóa khi ALTER TABLE khác nhau giữa các engine.

Không nên xóa constraint chỉ để một migration hoặc batch job chạy qua. Nếu quy tắc nghiệp vụ thay đổi, hãy sửa constraint theo phiên bản schema mới và cập nhật các luồng ghi liên quan trong một quy trình có kiểm soát.

## 11. Khác biệt giữa các hệ quản trị cần lưu ý

Ba loại constraint có mặt ở hầu hết hệ quản trị quan hệ, nhưng cú pháp tạo khóa tự sinh, cách xử lý NULL trong unique constraint, thời điểm kiểm tra và khả năng trì hoãn constraint có thể khác nhau.

| Nội dung | Điều cần kiểm tra |
| --- | --- |
| PRIMARY KEY | Cách tạo giá trị tự sinh (`IDENTITY`, sequence, auto-increment hoặc cơ chế khác); giới hạn kiểu dữ liệu và chỉ mục |
| UNIQUE | Cách xử lý nhiều giá trị NULL; hỗ trợ unique index có điều kiện/filtered index hay không |
| NOT NULL | Cách migration thêm constraint vào cột đã có NULL; mức khóa khi thay đổi schema |
| CHECK | Phiên bản có thực thi CHECK hay chỉ phân tích cú pháp; biểu thức được hỗ trợ; cách UNKNOWN/NULL được đánh giá |
| Deferrable constraints | Loại constraint nào được trì hoãn và cú pháp kiểm tra tại commit |
| Lỗi constraint | Mã lỗi, tên constraint và trạng thái transaction sau khi statement thất bại |

Ví dụ, MySQL chỉ thực thi CHECK constraint từ các phiên bản hỗ trợ thực thi đầy đủ (MySQL 8.0.16 trở đi); những phiên bản cũ hơn có thể phân tích nhưng bỏ qua CHECK. Nếu ứng dụng chạy trên nhiều phiên bản hoặc nhiều engine, hãy xác nhận constraint thực sự được thực thi bằng tài liệu và kiểm thử tích hợp.

## 12. Quy trình kiểm thử constraint và transaction

Kiểm thử nên xác nhận cả trường hợp dữ liệu hợp lệ, dữ liệu không hợp lệ và hai transaction cạnh tranh.

### Kiểm tra PRIMARY KEY và UNIQUE

1. Chèn một hàng với khóa chính mới và xác nhận thành công.
2. Chèn lại cùng khóa chính và xác nhận database từ chối.
3. Nếu có unique constraint trên email, thử chèn hai hàng có cùng email.
4. Mở hai transaction để đồng thời chèn cùng khóa nghiệp vụ; xác nhận cuối cùng chỉ một transaction có thể tạo giá trị duy nhất.
5. Kiểm tra ứng dụng chuyển lỗi duplicate/unique thành phản hồi phù hợp.

### Kiểm tra NOT NULL

1. Chèn hàng có đủ giá trị bắt buộc.
2. Bỏ qua cột có DEFAULT và xác nhận giá trị mặc định được dùng.
3. Truyền NULL tường minh vào cột NOT NULL và xác nhận bị từ chối.
4. Thử cập nhật một cột bắt buộc thành NULL.

### Kiểm tra CHECK

1. Chèn hàng có giá trị biên hợp lệ, ví dụ `quantity = 0` nếu quy tắc cho phép.
2. Chèn giá trị vi phạm, ví dụ `quantity = -1`, và xác nhận bị từ chối.
3. Thử truyền NULL để xác nhận kết hợp NOT NULL có đúng như thiết kế.
4. Cập nhật một hàng hợp lệ thành giá trị không hợp lệ.
5. Kiểm tra biểu thức trên nhiều cột, ví dụ `start_time < end_time`.

### Kiểm tra transaction khi có lỗi constraint

1. Bắt đầu transaction.
2. Thực hiện một thay đổi hợp lệ.
3. Thực hiện thay đổi tiếp theo cố ý vi phạm constraint.
4. Quan sát trạng thái transaction theo engine và driver.
5. Rollback hoặc rollback về savepoint theo thiết kế.
6. Đọc lại dữ liệu bằng transaction mới để xác nhận không còn thay đổi dở dang.

### Kiểm tra race condition

1. Mở hai connection độc lập.
2. Cho cả hai cùng kiểm tra một khóa nghiệp vụ chưa tồn tại.
3. Cho cả hai cùng INSERT cùng khóa.
4. Điều khiển thời điểm commit/rollback của từng transaction.
5. Xác nhận constraint ngăn trạng thái trùng, bất kể thứ tự chạy.

Không chỉ kiểm thử bằng một connection chạy tuần tự. Những lỗi do transaction đồng thời thường chỉ xuất hiện khi hai connection cùng thực hiện thao tác gần như một thời điểm.

## 13. Những điểm cần ghi nhớ

- `PRIMARY KEY` định danh duy nhất một hàng, đồng thời không cho phép NULL; khóa chính có thể gồm nhiều cột.
- `UNIQUE` bảo vệ các khóa nghiệp vụ bổ sung; cách xử lý NULL khác nhau giữa các hệ quản trị, nên kết hợp `NOT NULL` khi giá trị bắt buộc.
- `NOT NULL` yêu cầu cột có giá trị. `DEFAULT` chỉ cung cấp giá trị khi cột bị bỏ qua; nó không thay thế `NOT NULL`.
- `CHECK` bảo vệ biểu thức trên hàng đang được ghi. Với logic ba giá trị SQL, UNKNOWN do NULL thường không bị CHECK từ chối, nên phải dùng NOT NULL khi cần giá trị bắt buộc.
- Constraint được kiểm tra trong quá trình ghi hoặc tại commit nếu loại constraint và hệ quản trị hỗ trợ trì hoãn.
- Database phối hợp kiểm tra primary key/unique với cơ chế đồng thời để ngăn hai transaction cùng tạo giá trị trùng.
- CHECK trên một hàng không tự bảo vệ tổng `COUNT`, `SUM`, khoảng giao nhau hoặc bất biến phụ thuộc nhiều hàng.
- Transaction kết hợp nhiều thay đổi liên quan; nếu một thao tác vi phạm constraint, ứng dụng phải xử lý lỗi và rollback theo semantics của hệ quản trị.
- Kiểm tra đầu vào ở ứng dụng cải thiện trải nghiệm, còn constraint ở database bảo vệ dữ liệu từ mọi đường ghi.
