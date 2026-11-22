# READ COMMITTED và ảnh chụp mới theo câu lệnh

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích READ COMMITTED trong InnoDB và cách MVCC tạo read view cho một câu SELECT.
- Phân biệt snapshot theo câu lệnh của READ COMMITTED với snapshot theo transaction của REPEATABLE READ.
- Dự đoán kết quả khi hai session đọc và ghi cùng một hàng.
- Phân biệt consistent nonlocking read với locking read như SELECT ... FOR SHARE và SELECT ... FOR UPDATE.
- Nhận diện non-repeatable read và phantom read có thể xảy ra trong READ COMMITTED.
- Hiểu tác động của READ COMMITTED đến gap lock, UPDATE, DELETE và replication.
- Chọn isolation level phù hợp với báo cáo, luồng nghiệp vụ và mức độ đồng thời.
- Cấu hình, kiểm tra isolation level ở phạm vi session hoặc transaction.

Trong InnoDB, một câu SELECT thông thường thường không khóa các hàng mà nó đọc. Thay vào đó, MVCC (Multi-Version Concurrency Control) cho phép truy vấn nhìn thấy một phiên bản dữ liệu phù hợp với một thời điểm nhất định. Cơ chế này giúp giao dịch đọc và ghi có thể tiến hành đồng thời mà không phải chặn nhau chỉ vì một truy vấn đang đọc.

Điểm đặc trưng của READ COMMITTED là mỗi câu đọc nhất quán (consistent read) nhận một read view mới. Nếu transaction khác commit dữ liệu sau câu SELECT thứ nhất, câu SELECT thứ hai trong cùng transaction có thể nhìn thấy dữ liệu mới đó. Bài học tập trung vào cách hoạt động, hệ quả và cách sử dụng hành vi này trong ứng dụng MySQL.

## 1. READ COMMITTED là gì?

READ COMMITTED là một mức cô lập giao dịch được InnoDB hỗ trợ. Với câu SELECT thông thường không có mệnh đề khóa, InnoDB tạo một ảnh chụp logic (snapshot/read view) cho câu đọc.

Snapshot của câu đọc cho phép truy vấn:

- Nhìn thấy các thay đổi đã COMMIT trước thời điểm read view được tạo.
- Không nhìn thấy thay đổi chưa COMMIT của transaction khác.
- Không nhìn thấy thay đổi của transaction khác được COMMIT sau thời điểm read view được tạo.
- Nhìn thấy các thay đổi do chính transaction hiện tại thực hiện ở những câu lệnh trước đó.

Với READ COMMITTED, mỗi consistent read tạo một snapshot mới, kể cả khi các câu SELECT nằm trong cùng một transaction.

Ví dụ, transaction A thực hiện hai câu SELECT:

1. SELECT thứ nhất đọc số lượng tồn kho là 10.
2. Transaction B cập nhật tồn kho thành 8 và COMMIT.
3. SELECT thứ hai của A đọc được dữ liệu mới là 8.

Cả hai SELECT đều thuộc cùng transaction A. Kết quả khác nhau vì mỗi câu đọc dùng một read view riêng.

### 1.1. Không phải READ UNCOMMITTED

READ COMMITTED không cho phép đọc dữ liệu chưa commit của transaction khác. Nếu B đang UPDATE nhưng chưa COMMIT, SELECT thông thường của A vẫn đọc phiên bản đã commit trước đó.

READ UNCOMMITTED có thể đọc phiên bản chưa commit và vì thế có nguy cơ dirty read. READ COMMITTED loại bỏ dirty read bằng cách chỉ cung cấp phiên bản đã commit phù hợp với read view.

### 1.2. InnoDB mặc định là REPEATABLE READ

Mức cô lập mặc định của InnoDB là REPEATABLE READ. Ở mức này, các consistent read trong cùng transaction dùng chung snapshot được tạo bởi lần consistent read đầu tiên.

Vì vậy, nếu muốn quan sát hành vi snapshot mới theo từng câu lệnh, cần đặt isolation level thành READ COMMITTED cho session hoặc transaction trước khi bắt đầu kiểm thử.

Khi autocommit đang bật và không có transaction tường minh, mỗi câu lệnh là một transaction riêng. Khác biệt giữa READ COMMITTED và REPEATABLE READ thể hiện rõ nhất khi ứng dụng mở một transaction bằng START TRANSACTION rồi chạy nhiều câu SELECT trước khi COMMIT.

## 2. MVCC và read view theo câu lệnh

MVCC duy trì nhiều phiên bản logic của một hàng để các transaction có thể đọc phiên bản phù hợp mà không nhất thiết phải chờ transaction ghi kết thúc.

Khi một transaction cập nhật hàng InnoDB, phiên bản cũ được bảo tồn thông qua undo log trong thời gian còn cần thiết cho consistent read và rollback. Khi một câu SELECT tạo read view, InnoDB xác định transaction nào đã commit trước thời điểm đó và phiên bản hàng nào được phép hiển thị.

Trong READ COMMITTED:

- Mỗi consistent read tạo read view mới.
- Read view mới có thể bao gồm các transaction vừa commit kể từ câu đọc trước.
- Các transaction chưa commit tại thời điểm tạo read view vẫn bị loại khỏi góc nhìn của câu SELECT.
- Một transaction có thể nhìn thấy các thay đổi đã commit của session khác giữa hai câu SELECT.

Không nên hiểu snapshot mới là một bản sao vật lý của toàn bộ database được tạo lại cho mỗi SELECT. Đây là góc nhìn logic được InnoDB dựng từ các phiên bản hàng và metadata transaction.

### 2.1. Chuẩn bị dữ liệu dùng trong bài

Các ví dụ tiếp theo dùng ba bảng InnoDB. Tạo chúng trong một database thực hành:

~~~sql
CREATE TABLE inventory (
    sku VARCHAR(40) NOT NULL,
    available_qty INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (sku)
) ENGINE = InnoDB;

CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(24) NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_order_status_amount (order_status, total_amount),
    CONSTRAINT fk_sales_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
) ENGINE = InnoDB;

INSERT INTO inventory (sku, available_qty, unit_price)
VALUES ('KB-01', 10, 1250000.00);

INSERT INTO customer (customer_id, full_name)
VALUES
    (101, 'Nguyễn An'),
    (102, 'Trần Bình');

INSERT INTO sales_order (
    order_id, customer_id, order_status, total_amount
)
VALUES
    (1001, 101, 'completed', 1250000.00),
    (1002, 101, 'completed', 5200000.00),
    (1003, 101, 'pending',    890000.00),
    (1004, 101, 'completed', 1500000.00),
    (1005, 102, 'completed', 3400000.00);
~~~

Các truy vấn JOIN và đếm đơn ở phần sau sử dụng đúng cấu trúc này. Với điều kiện completed và tổng tiền từ 1 triệu đến dưới 5 triệu, dữ liệu ban đầu có ba đơn phù hợp.

### 2.2. Một câu SELECT có một read view

Một câu SELECT có thể đọc nhiều bảng, JOIN, lọc và tổng hợp. Với consistent nonlocking read, toàn bộ câu lệnh sử dụng một read view nhất quán, thay vì mỗi bảng trong JOIN nhận một thời điểm độc lập.

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    SUM(o.total_amount) AS total_spending
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name;
~~~

Trong READ COMMITTED, câu SELECT này đọc customer và sales_order theo cùng read view của câu lệnh. Nếu transaction khác commit một đơn hàng trong lúc câu SELECT đang chạy, câu SELECT hiện tại không trộn phiên bản trước và sau commit chỉ vì nó đọc hai bảng khác nhau. Một câu SELECT tiếp theo có thể nhận read view mới và thấy đơn hàng vừa commit.

### 2.3. Thay đổi của transaction hiện tại vẫn nhìn thấy được

Quy tắc snapshot không che giấu các thay đổi do chính transaction thực hiện.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_qty = available_qty - 2
WHERE sku = 'KB-01';

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';

COMMIT;
~~~

SELECT nhìn thấy giá trị đã được transaction hiện tại cập nhật, dù transaction chưa COMMIT. Đây là ngoại lệ có chủ đích đối với quy tắc chỉ nhìn thấy thay đổi đã commit của các transaction khác.

Nếu transaction cập nhật một số hàng rồi SELECT một tập hàng rộng hơn, kết quả có thể kết hợp các hàng mới do chính nó ghi với phiên bản cũ của các hàng khác. Đừng xem read view như một bản snapshot vật lý đồng nhất của mọi thay đổi do transaction hiện tại tạo ra.

## 3. Cấu hình READ COMMITTED

Có ba phạm vi cấu hình thường cần phân biệt: session, transaction kế tiếp và global.

### 3.1. Đặt cho toàn bộ transaction tiếp theo trong session

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@autocommit AS autocommit;
~~~

Lệnh trên đặt READ COMMITTED làm isolation level cho các transaction tiếp theo trong session hiện tại. Nó không thay đổi isolation level của các session khác.

Nếu đang có transaction chạy, thay đổi session áp dụng cho các transaction sau, không thay đổi transaction đang hoạt động. Để dễ kiểm thử và tránh nhầm lẫn, nên cấu hình trước START TRANSACTION.

### 3.2. Chỉ đặt cho một transaction kế tiếp

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

SELECT *
FROM inventory
WHERE sku = 'KB-01';

COMMIT;
~~~

Không có từ khóa SESSION hoặc GLOBAL, SET TRANSACTION chỉ áp dụng cho transaction kế tiếp trong session. Sau khi transaction đó kết thúc, các transaction tiếp theo quay lại dùng session isolation level.

Lệnh SET TRANSACTION không có phạm vi không được chạy khi transaction đang hoạt động.

### 3.3. Đặt mặc định cho các session mới

~~~sql
SET GLOBAL TRANSACTION ISOLATION LEVEL READ COMMITTED;
~~~

Thiết lập GLOBAL ảnh hưởng đến các session được tạo sau đó. Các session đang tồn tại không tự động đổi isolation level.

Thao tác này cần quyền quản trị phù hợp, thường là CONNECTION_ADMIN hoặc quyền SUPER cũ đã bị deprecated. Không nên đổi mặc định toàn server chỉ để thử một truy vấn. Trong ứng dụng, cấu hình theo session hoặc theo transaction thường dễ kiểm soát hơn.

### 3.4. Kiểm tra giá trị thực tế

~~~sql
SELECT
    @@GLOBAL.transaction_isolation AS global_isolation,
    @@SESSION.transaction_isolation AS session_isolation,
    @@autocommit AS autocommit;
~~~

MySQL thường hiển thị tên isolation level ở dạng có dấu gạch nối, ví dụ READ-COMMITTED hoặc REPEATABLE-READ.

Có thể kiểm tra riêng:

~~~sql
SHOW VARIABLES LIKE 'transaction_isolation';
SHOW SESSION VARIABLES LIKE 'transaction_isolation';
~~~

Đừng nhầm giá trị GLOBAL với giá trị SESSION. Một session có thể dùng READ COMMITTED dù mặc định toàn server vẫn là REPEATABLE READ.

## 4. Thí nghiệm hai session: SELECT thứ hai nhìn thấy commit mới

Bảng inventory đã được tạo ở mục 2.1. Nếu chạy lại thí nghiệm, đưa số lượng về 10 trước khi mở hai session:

~~~sql
UPDATE inventory
SET available_qty = 10
WHERE sku = 'KB-01';

SELECT *
FROM inventory
WHERE sku = 'KB-01';
~~~

Mở hai kết nối MySQL độc lập, gọi là Session A và Session B. Không dùng chung một connection vì cần hai transaction đồng thời.

### 4.1. Session A bắt đầu transaction READ COMMITTED

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

Kết quả:

~~~text
available_qty
--------------
10
~~~

Giữ transaction A mở.

### 4.2. Session B cập nhật và commit

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_qty = 8
WHERE sku = 'KB-01';

COMMIT;
~~~

Session B đã commit giá trị mới là 8.

### 4.3. Session A đọc lại

Quay lại Session A, vẫn trong transaction cũ:

~~~sql
SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

Kết quả:

~~~text
available_qty
--------------
8
~~~

SELECT thứ hai tạo read view mới sau khi B đã commit nên nhìn thấy giá trị 8. Transaction A vẫn là một transaction duy nhất; snapshot được làm mới ở cấp câu SELECT.

Kết thúc:

~~~sql
COMMIT;
~~~

### 4.4. B chưa commit thì A đọc gì?

Lặp lại với giá trị ban đầu là 8.

Session A:

~~~sql
START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

Kết quả ban đầu là 8. Giữ transaction A mở.

Session B:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_qty = 6
WHERE sku = 'KB-01';

-- Chưa COMMIT.
~~~

A chạy SELECT trong lúc B chưa commit:

~~~sql
SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

A vẫn đọc được giá trị đã commit trước đó là 8. A không đọc thấy 6 vì B chưa commit.

Sau khi B chạy COMMIT, A chạy lại:

~~~sql
SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

Kết quả lúc này là 6. Kết thúc transaction A bằng COMMIT.

Thí nghiệm này xác nhận hai đặc điểm riêng biệt:

- READ COMMITTED không đọc dữ liệu chưa commit.
- READ COMMITTED nhận snapshot mới ở mỗi consistent read, vì vậy nhìn thấy commit mới giữa các câu SELECT.

## 5. So sánh với REPEATABLE READ

Lặp lại cùng thí nghiệm nhưng đổi Session A sang REPEATABLE READ.

Đưa dữ liệu về trạng thái 8 trước khi mở hai transaction:

~~~sql
UPDATE inventory
SET available_qty = 8
WHERE sku = 'KB-01';
~~~

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;

START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

Giả sử kết quả là 8. Câu SELECT này tạo snapshot cho các consistent read trong transaction.

Session B:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_qty = 6
WHERE sku = 'KB-01';

COMMIT;
~~~

Session A đọc lại:

~~~sql
SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

A vẫn thấy 8 vì consistent read tiếp theo sử dụng snapshot được tạo ở lần đọc đầu tiên. Sau khi A COMMIT và bắt đầu transaction mới, SELECT sẽ thấy 6.

### 5.1. Bảng so sánh

| Đặc điểm | READ COMMITTED | REPEATABLE READ |
|---|---|---|
| Snapshot của consistent read | Mới cho mỗi câu SELECT | Tạo ở consistent read đầu tiên trong transaction |
| Hai SELECT cùng transaction | Có thể thấy dữ liệu commit mới giữa hai câu | Cùng nhìn snapshot đã thiết lập |
| Dirty read | Không | Không |
| Non-repeatable read | Có thể xảy ra | Không xảy ra giữa các consistent read cùng transaction |
| Phantom với consistent read lặp lại | Có thể xảy ra | Không xuất hiện do snapshot được giữ ổn định |
| Gap lock cho tìm kiếm thông thường | Tắt, ngoại trừ kiểm tra FK và duplicate key | Có thể dùng gap/next-key lock cho các thao tác khóa theo phạm vi |
| Mức mặc định InnoDB | Không | Có |

READ COMMITTED ưu tiên việc mỗi câu đọc nhìn thấy dữ liệu đã commit mới nhất tại thời điểm câu đọc bắt đầu. REPEATABLE READ ưu tiên một góc nhìn ổn định cho nhiều câu đọc nhất quán trong cùng transaction.

Không có mức nào luôn tốt hơn trong mọi trường hợp. Lựa chọn phụ thuộc việc ứng dụng cần dữ liệu mới nhất ở từng lần đọc hay cần nhiều câu đọc cùng nhìn một trạng thái logic ổn định.

## 6. Non-repeatable read và phantom read

READ COMMITTED ngăn dirty read, nhưng cho phép hai hiện tượng khác vì snapshot được làm mới giữa các câu SELECT.

### 6.1. Non-repeatable read

Non-repeatable read xảy ra khi cùng một câu SELECT được chạy lại trong một transaction nhưng giá trị của một hàng đã thay đổi do transaction khác commit.

Ví dụ:

1. A SELECT số lượng tồn kho của KB-01 và nhận 10.
2. B UPDATE số lượng thành 8 rồi COMMIT.
3. A chạy lại cùng SELECT và nhận 8.

A đọc cùng khóa chính, cùng điều kiện, nhưng nhận giá trị khác nhau.

Đây là hành vi đúng theo READ COMMITTED. Nếu nghiệp vụ cần đọc cùng một giá trị trong nhiều bước của transaction, hãy cân nhắc REPEATABLE READ hoặc một chiến lược khóa phù hợp.

### 6.2. Phantom read

Phantom read xảy ra khi một truy vấn theo điều kiện phạm vi được chạy lại và xuất hiện thêm hoặc mất đi các hàng do transaction khác commit.

Giả sử A đếm các đơn completed có tổng tiền từ 1 triệu đến dưới 5 triệu:

Để chạy lại thí nghiệm, xóa hàng thử nghiệm có order_id = 1006 nếu nó đã được chèn ở lần trước:

~~~sql
DELETE FROM sales_order
WHERE order_id = 1006;
~~~

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

SELECT COUNT(*) AS order_count
FROM sales_order
WHERE order_status = 'completed'
  AND total_amount >= 1000000
  AND total_amount < 5000000;
~~~

Kết quả ban đầu là 3. Session B chèn một đơn mới thỏa điều kiện rồi COMMIT:

~~~sql
START TRANSACTION;

INSERT INTO sales_order (
    order_id, customer_id, order_status, total_amount
)
VALUES (1006, 102, 'completed', 2000000.00);

COMMIT;
~~~

Session A chạy lại cùng SELECT:

~~~sql
SELECT COUNT(*) AS order_count
FROM sales_order
WHERE order_status = 'completed'
  AND total_amount >= 1000000
  AND total_amount < 5000000;
~~~

Kết quả lúc này là 4. Kết thúc transaction A bằng COMMIT.

Hàng mới là phantom đối với lần đọc trước. READ COMMITTED cho phép điều này vì câu SELECT thứ hai nhận read view mới.

### 6.3. Minh họa bằng hai session

~~~mermaid
sequenceDiagram
    participant A as Session A (READ COMMITTED)
    participant B as Session B
    A->>A: SELECT COUNT(*) WHERE total_amount >= 1000000
    Note over A: Kết quả 3
    B->>B: INSERT đơn mới thỏa điều kiện
    B->>B: COMMIT
    A->>A: Chạy lại cùng SELECT
    Note over A: Kết quả 4
~~~

Nếu cần một báo cáo nhiều câu SELECT có cùng góc nhìn dữ liệu, READ COMMITTED có thể không phù hợp. Hãy cân nhắc một transaction REPEATABLE READ cho các consistent read, hoặc gom các phép tính vào một câu SELECT nếu có thể.

## 7. Consistent read và locking read là hai cơ chế khác nhau

Không phải mọi SELECT đều dùng snapshot theo cùng một cách.

### 7.1. Consistent nonlocking read

SELECT thông thường trong InnoDB ở READ COMMITTED là consistent read:

~~~sql
SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

Nó đọc phiên bản phù hợp với read view và không đặt row lock trên hàng được đọc. Transaction khác vẫn có thể UPDATE hoặc DELETE hàng đó trong lúc câu đọc diễn ra.

Cơ chế này phù hợp cho việc hiển thị, báo cáo và đọc dữ liệu không cần giữ quyền khóa hàng sau khi đọc.

### 7.2. Locking read với FOR SHARE

~~~sql
START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01'
FOR SHARE;

-- Thực hiện công việc cần bảo vệ hàng đã đọc.

COMMIT;
~~~

FOR SHARE đặt shared lock trên các hàng được đọc. Session khác có thể đọc, nhưng không thể sửa các hàng đang bị shared lock cho đến khi transaction kết thúc.

Nếu một hàng đang bị transaction khác sửa mà chưa commit, SELECT ... FOR SHARE có thể phải chờ transaction đó kết thúc rồi mới đọc giá trị mới nhất.

### 7.3. Locking read với FOR UPDATE

~~~sql
START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01'
FOR UPDATE;

UPDATE inventory
SET available_qty = available_qty - 1
WHERE sku = 'KB-01';

COMMIT;
~~~

FOR UPDATE khóa các index record mà truy vấn tìm thấy theo cách tương tự thao tác UPDATE. Nó phù hợp với luồng đọc rồi cập nhật cùng một hàng khi cần ngăn session khác thay đổi hàng đó trước khi transaction hiện tại hoàn tất.

Các locking read cần transaction đang mở; với autocommit bật, hãy dùng START TRANSACTION để lock được giữ trong khoảng công việc cần bảo vệ.

### 7.4. So sánh hai loại đọc

| Tiêu chí | SELECT thông thường | SELECT ... FOR SHARE / FOR UPDATE |
|---|---|---|
| Cơ chế | Consistent read qua MVCC | Locking read, đọc trạng thái hiện hành |
| Row lock | Không đặt row lock | Có đặt shared hoặc exclusive lock |
| Có thể chờ writer? | Thường không chờ row lock của writer | Có thể chờ transaction đang giữ lock xung đột |
| Mục đích | Đọc không cần khóa hàng | Đọc và bảo vệ hàng cho thao tác tiếp theo |
| Thời gian giữ lock | Không có row lock từ consistent read | Đến COMMIT hoặc ROLLBACK |

Đừng thêm FOR UPDATE chỉ để “đọc dữ liệu mới nhất”. Nó làm thay đổi hành vi đồng thời vì có khóa và có thể khiến session khác phải chờ. Với nhu cầu đọc snapshot mới ở từng SELECT, READ COMMITTED đã cung cấp hành vi đó cho consistent read.

## 8. Gap lock và phantom trong READ COMMITTED

Trong READ COMMITTED, InnoDB tắt gap locking cho các thao tác tìm kiếm và quét index thông thường. Với locking reads, UPDATE và DELETE, InnoDB khóa index record thay vì khóa cả khoảng trống trước record. Gap lock vẫn được sử dụng cho kiểm tra foreign key và duplicate key.

Điều này có một hệ quả quan trọng: transaction khác có thể chèn hàng mới vào khoảng trống mà một truy vấn phạm vi đang quan tâm. Vì thế phantom row có thể xuất hiện giữa hai câu SELECT.

Ví dụ Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

SELECT *
FROM sales_order
WHERE order_status = 'completed'
  AND total_amount >= 1000000
  AND total_amount < 2000000
FOR UPDATE;
~~~

Session B có thể chèn một hàng mới có total_amount = 1500000 nếu không có ràng buộc hoặc khóa xung đột khác ngăn việc đó. A không giữ gap lock cho khoảng giá trị đó chỉ vì isolation level là READ COMMITTED.

Điều này không có nghĩa READ COMMITTED không dùng lock. Các hàng phù hợp được UPDATE/DELETE hoặc được locking read tìm thấy vẫn có thể bị khóa. Điểm khác biệt là các khoảng trống giữa index record không được khóa như ở cơ chế next-key locking thường gặp trong REPEATABLE READ.

Nếu nghiệp vụ cần ngăn chèn mới vào một khoảng dữ liệu, hãy đánh giá lại isolation level, loại truy vấn khóa, index và constraint. Không giả định rằng FOR UPDATE trong READ COMMITTED sẽ ngăn mọi phantom insert.

## 9. READ COMMITTED ảnh hưởng UPDATE và DELETE

READ COMMITTED không chỉ thay đổi consistent read của SELECT. Nó còn ảnh hưởng cách InnoDB giữ row lock trong UPDATE và DELETE.

### 9.1. Lock các hàng thực sự bị thay đổi

Với UPDATE hoặc DELETE, InnoDB giữ lock cho các hàng được cập nhật hoặc xóa. Record lock trên hàng không thỏa điều kiện WHERE được giải phóng sau khi MySQL đánh giá điều kiện.

Điều này có thể giảm số lock được giữ và giảm khả năng deadlock so với REPEATABLE READ trong một số workload. Tuy nhiên, deadlock vẫn có thể xảy ra nếu các transaction khóa nhiều hàng theo thứ tự khác nhau.

### 9.2. Semi-consistent read trong UPDATE

Khi UPDATE gặp một hàng đang bị transaction khác khóa, InnoDB có thể thực hiện semi-consistent read ở READ COMMITTED. Nó cung cấp phiên bản đã commit mới nhất cho MySQL để đánh giá hàng có thỏa WHERE hay không.

- Nếu hàng không thỏa WHERE, InnoDB có thể bỏ qua và không giữ lock trên hàng đó.
- Nếu hàng thỏa WHERE, MySQL đọc lại hàng và InnoDB lấy lock cần thiết hoặc chờ lock.

Đây là chi tiết nội bộ quan trọng khi phân tích UPDATE đồng thời. Nó không có nghĩa UPDATE được phép ghi đè dữ liệu chưa commit hoặc bỏ qua kiểm soát khóa.

### 9.3. UPDATE và DELETE không phải consistent read thông thường

Không nên suy luận rằng UPDATE/DELETE sẽ dùng cùng snapshot với một SELECT thông thường trước đó trong transaction. Các câu lệnh DML cần xác định hàng hiện hành và lấy lock để sửa dữ liệu.

Ví dụ:

~~~sql
START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';

-- Một transaction khác có thể cập nhật và COMMIT tại đây.

UPDATE inventory
SET available_qty = available_qty - 1
WHERE sku = 'KB-01';

COMMIT;
~~~

SELECT và UPDATE không phải một thao tác kiểm tra rồi ghi được bảo vệ tự động. Nếu logic nghiệp vụ phụ thuộc giá trị đọc ban đầu, hãy dùng locking read hoặc viết UPDATE có điều kiện nguyên tử:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 1
WHERE sku = 'KB-01'
  AND available_qty >= 1;
~~~

Sau đó kiểm tra số hàng bị ảnh hưởng. Nếu không có hàng nào được cập nhật, không đủ tồn kho hoặc điều kiện không còn đúng tại thời điểm UPDATE. Cách này tránh khoảng hở giữa SELECT kiểm tra và UPDATE ghi.

## 10. READ COMMITTED và WITH CONSISTENT SNAPSHOT

MySQL hỗ trợ:

~~~sql
START TRANSACTION WITH CONSISTENT SNAPSHOT;
~~~

Tùy chọn này chỉ có tác dụng tạo consistent snapshot với InnoDB khi isolation level hiện tại là REPEATABLE READ. Nó không thay đổi isolation level.

Nếu đang dùng READ COMMITTED, mệnh đề WITH CONSISTENT SNAPSHOT bị bỏ qua và MySQL phát cảnh báo. Nó không biến các câu SELECT trong transaction thành một snapshot chung.

Ví dụ:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION WITH CONSISTENT SNAPSHOT;

SHOW WARNINGS;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';

COMMIT;
~~~

Để có snapshot ổn định cho nhiều consistent read, dùng REPEATABLE READ và tạo read view theo cách phù hợp. Đừng dựa vào WITH CONSISTENT SNAPSHOT khi transaction đang ở READ COMMITTED.

## 11. READ COMMITTED và binary log/replication

Khi dùng READ COMMITTED với InnoDB và binary logging, MySQL chỉ hỗ trợ row-based binary logging.

Nếu cấu hình binlog_format là MIXED, server tự động sử dụng row-based logging cho READ COMMITTED. Statement-based logging không được hỗ trợ cho isolation level này.

Kiểm tra cấu hình:

~~~sql
SELECT
    @@GLOBAL.log_bin AS log_bin,
    @@GLOBAL.binlog_format AS global_binlog_format,
    @@SESSION.binlog_format AS session_binlog_format;
~~~

Trong MySQL 8.4, binlog_format đã được đánh dấu deprecated và row-based logging là lựa chọn nên dùng cho replication mới. Khi thay đổi isolation level trong môi trường có replication, hãy kiểm tra cấu hình source/replica, binlog format và quy trình vận hành trước khi triển khai.

Không nên chỉ đổi isolation level trên một server rồi bỏ qua khả năng tương thích của binary log. Việc cấu hình replication cần nhất quán với phiên bản và chính sách logging của hệ thống.

## 12. Khi nào nên chọn READ COMMITTED?

READ COMMITTED có ích khi ứng dụng muốn mỗi câu đọc nhìn thấy các thay đổi đã commit mới nhất mà không cần duy trì cùng snapshot cho nhiều câu SELECT trong một transaction.

Một số trường hợp có thể cân nhắc:

- Các transaction ngắn, đọc dữ liệu nhiều lần và muốn thấy commit mới giữa các lần đọc.
- Workload có nhiều UPDATE/DELETE và muốn giảm thời gian giữ lock trên các hàng không thỏa điều kiện.
- Các truy vấn hiển thị trạng thái cần cập nhật theo từng request hoặc từng câu lệnh.
- Hệ thống chấp nhận non-repeatable read và phantom read theo yêu cầu nghiệp vụ.

Cần thận trọng với:

- Báo cáo nhiều câu SELECT cần cùng một góc nhìn dữ liệu.
- Quy trình kiểm tra nhiều hàng rồi mới quyết định cập nhật.
- Tác vụ cần ngăn phantom insert vào khoảng dữ liệu.
- Luồng nghiệp vụ phụ thuộc một giá trị đã đọc trước đó trong transaction.

### 12.1. Báo cáo nhiều bước

Giả sử một báo cáo chạy hai câu SELECT:

~~~sql
START TRANSACTION;

SELECT SUM(total_amount) AS revenue
FROM sales_order
WHERE order_status = 'completed';

SELECT COUNT(*) AS order_count
FROM sales_order
WHERE order_status = 'completed';

COMMIT;
~~~

Nếu đang ở READ COMMITTED, một transaction khác có thể commit đơn completed giữa hai câu SELECT. revenue và order_count có thể được tính trên hai tập dữ liệu khác nhau.

Nếu yêu cầu báo cáo là hai chỉ số phải phản ánh cùng một thời điểm, có thể gộp chúng vào một SELECT:

~~~sql
SELECT
    SUM(total_amount) AS revenue,
    COUNT(*) AS order_count
FROM sales_order
WHERE order_status = 'completed';
~~~

Hoặc dùng REPEATABLE READ cho transaction đọc nhiều bước cần cùng snapshot. Chọn giải pháp dựa trên yêu cầu nhất quán của báo cáo.

### 12.2. Quy trình đọc rồi ghi

Nếu ứng dụng làm theo mô hình:

1. SELECT số lượng tồn kho.
2. Kiểm tra số lượng có đủ không.
3. UPDATE trừ tồn kho.

thì READ COMMITTED không tự khóa hàng sau SELECT. Một transaction khác có thể thay đổi số lượng trước bước UPDATE.

Có hai cách phổ biến:

- Dùng SELECT ... FOR UPDATE trong transaction để khóa hàng cần kiểm tra và cập nhật.
- Dùng UPDATE có điều kiện trong một câu lệnh và kiểm tra affected rows.

Ví dụ:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 2
WHERE sku = 'KB-01'
  AND available_qty >= 2;
~~~

Câu UPDATE chỉ trừ tồn kho khi điều kiện vẫn đúng tại thời điểm thực thi. Nếu số hàng bị ảnh hưởng bằng 0, ứng dụng xử lý trường hợp không đủ tồn kho hoặc SKU không tồn tại.

## 13. Kiểm tra và chẩn đoán khi triển khai

Trước khi thay đổi isolation level, hãy kiểm tra giá trị hiện tại:

~~~sql
SELECT
    @@GLOBAL.transaction_isolation,
    @@SESSION.transaction_isolation,
    @@autocommit;
~~~

Kiểm tra binary logging nếu có sử dụng:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
~~~

Kiểm tra các transaction đang chạy và thời gian tồn tại của chúng:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Nếu cần xem lock đang chờ, có thể kiểm tra Performance Schema:

~~~sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
ORDER BY OBJECT_SCHEMA, OBJECT_NAME, LOCK_STATUS;
~~~

Các truy vấn chẩn đoán cần quyền đọc metadata tương ứng. Không kết luận một transaction bị treo chỉ từ thời gian bắt đầu; cần đối chiếu query, trạng thái chờ, ứng dụng sở hữu connection và lock liên quan.

### 13.1. Kiểm tra session thực tế của connection pool

Ứng dụng thường dùng connection pool. Isolation level là đặc tính của session, nên mỗi connection có thể giữ session setting riêng.

Nếu ứng dụng chỉ cấu hình một connection nhưng pool tạo nhiều connection, các request có thể chạy ở isolation level khác nhau. Hãy cấu hình lúc khởi tạo từng connection hoặc đặt transaction characteristic rõ ràng trước mỗi transaction theo chính sách ứng dụng.

Không giả định việc thay đổi GLOBAL sẽ sửa các connection pool đang mở. Các session hiện tại giữ giá trị session của chúng cho đến khi được thay đổi rõ ràng hoặc kết nối được tạo lại.

## 14. Các lỗi và hiểu nhầm thường gặp

| Hiểu nhầm hoặc lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ READ COMMITTED chỉ tạo một snapshot khi START TRANSACTION | Bỏ qua việc snapshot mới ở từng SELECT | Nhớ rằng mỗi consistent read có read view riêng |
| Nghĩ SELECT thứ hai phải trả cùng kết quả SELECT thứ nhất | Không nhận diện non-repeatable read | Xác định transaction khác có commit giữa hai câu không |
| Nghĩ READ COMMITTED cho phép dirty read | Hiểu sai dữ liệu chưa commit | READ COMMITTED chỉ đọc phiên bản đã commit phù hợp |
| Nghĩ SELECT thông thường khóa hàng | Kỳ vọng writer phải chờ reader | Consistent read không đặt row lock |
| Dùng FOR UPDATE chỉ để đọc mới nhất | Tạo lock không cần thiết và giảm concurrency | Dùng READ COMMITTED cho snapshot mới; chỉ locking read khi cần bảo vệ hàng |
| Nghĩ FOR UPDATE ngăn mọi phantom ở READ COMMITTED | Có thể bỏ sót insert vào gap | Gap lock cho tìm kiếm thông thường bị tắt ở READ COMMITTED |
| Đặt isolation level sau khi transaction đã chạy và nghĩ nó đổi transaction hiện tại | Kết quả kiểm thử không như mong đợi | Đặt trước START TRANSACTION; SESSION setting chỉ áp dụng transaction sau |
| Dùng WITH CONSISTENT SNAPSHOT trong READ COMMITTED | Nhận warning và không có snapshot transaction-wide | Dùng REPEATABLE READ nếu cần snapshot chung |
| Chỉ đổi isolation level mà không kiểm tra binlog | Có thể không tương thích statement-based logging | Kiểm tra row-based logging và replication |
| Cho rằng READ COMMITTED không dùng lock | Đánh giá thấp xung đột UPDATE/DELETE | DML và locking read vẫn lấy record lock |
| Dùng nhiều SELECT để tạo báo cáo nhất quán | Các chỉ số có thể nhìn các snapshot khác nhau | Gộp vào một SELECT hoặc dùng REPEATABLE READ |

## 15. Quy trình kiểm thử READ COMMITTED

Khi cần xác nhận hành vi trên một MySQL instance, thực hiện theo trình tự:

1. Tạo bảng InnoDB nhỏ có một hàng được hai session cùng truy cập.
2. Xác nhận isolation level của từng session bằng @@SESSION.transaction_isolation.
3. Đặt Session A ở READ COMMITTED và bắt đầu transaction.
4. A SELECT một hàng để ghi nhận giá trị ban đầu.
5. B UPDATE cùng hàng nhưng chưa COMMIT.
6. A SELECT lại để xác nhận không đọc dữ liệu chưa commit.
7. B COMMIT.
8. A SELECT lần nữa để xác nhận snapshot mới nhìn thấy commit.
9. Lặp lại với REPEATABLE READ để so sánh.
10. Thử INSERT một hàng mới thỏa điều kiện phạm vi và quan sát phantom.
11. Thử SELECT ... FOR UPDATE trong transaction riêng để quan sát locking read.
12. Kết thúc tất cả transaction và khôi phục dữ liệu thực hành.

Có thể dùng sơ đồ sau để ghi nhớ lựa chọn:

~~~mermaid
flowchart TD
    A[Ứng dụng cần đọc dữ liệu] --> B{Nhiều câu SELECT phải cùng snapshot?}
    B -->|Có| C[REPEATABLE READ hoặc một SELECT]
    B -->|Không| D{Có cần khóa hàng trước khi ghi?}
    D -->|Có| E[READ COMMITTED kết hợp locking read hoặc UPDATE có điều kiện]
    D -->|Không| F[READ COMMITTED consistent read]
    C --> G[Kiểm tra tính nhất quán nghiệp vụ]
    E --> G
    F --> G
~~~

## 16. Bài tập thực hành

### Bài 1: Đặt isolation level theo session

Đặt session thành READ COMMITTED. Truy vấn @@SESSION.transaction_isolation và xác nhận giá trị. Tạo transaction mới rồi thực hiện SELECT.

### Bài 2: Quan sát snapshot mới

Mở hai session. A đọc số lượng tồn kho; B cập nhật và COMMIT; A đọc lại trong transaction cũ. Ghi lại hai kết quả và giải thích read view mới.

### Bài 3: Không đọc dirty data

B cập nhật một hàng nhưng chưa COMMIT. A chạy SELECT thông thường. Xác nhận A vẫn thấy giá trị đã commit trước đó. Sau đó B ROLLBACK và kiểm tra lại.

### Bài 4: So sánh REPEATABLE READ

Chạy lại Bài 2 với REPEATABLE READ. Xác nhận hai SELECT trong cùng transaction dùng cùng snapshot. COMMIT A rồi mở transaction mới để thấy giá trị mới.

### Bài 5: Quan sát non-repeatable read

A đọc cùng một hàng hai lần. B cập nhật giá trị giữa hai lần đọc và COMMIT. Giải thích vì sao kết quả khác nhau nhưng không phải dirty read.

### Bài 6: Quan sát phantom read

A đếm các đơn trong một khoảng total_amount. B chèn một đơn mới thỏa điều kiện rồi COMMIT. A chạy lại truy vấn và ghi nhận số hàng thay đổi.

### Bài 7: So sánh consistent read và locking read

A chạy SELECT thông thường, sau đó B UPDATE cùng hàng và COMMIT. Lặp lại bằng SELECT ... FOR SHARE trong transaction. Quan sát sự khác nhau về lock và thời điểm đọc.

### Bài 8: Kiểm tra gap lock

Trong READ COMMITTED, A chạy SELECT ... FOR UPDATE trên một khoảng giá trị. B thử INSERT một hàng vào khoảng trống đó. Quan sát rằng gap locking cho tìm kiếm thông thường đã bị tắt, đồng thời kiểm tra constraint và index có thể tạo ra các lock khác.

### Bài 9: Cập nhật tồn kho an toàn

Viết hai phương án: SELECT ... FOR UPDATE rồi UPDATE; và UPDATE có điều kiện available_qty >= quantity. So sánh số hàng bị ảnh hưởng và khả năng xử lý hai request đồng thời.

### Bài 10: Báo cáo nhiều câu SELECT

Tạo transaction đọc SUM và COUNT ở hai câu SELECT. Cho session khác commit một đơn giữa hai câu. Quan sát hai chỉ số có thể lệch snapshot. Viết lại thành một SELECT trả về cả SUM và COUNT.

### Bài 11: Kiểm tra cấu hình replication

Truy vấn log_bin và binlog_format. Giải thích vì sao READ COMMITTED yêu cầu row-based logging và cách MIXED được xử lý.

### Bài 12: Đánh giá isolation level cho ứng dụng

Chọn một luồng nghiệp vụ thực tế. Xác định nó cần snapshot mới ở mỗi câu đọc, snapshot ổn định trong transaction hay khóa hàng trước khi ghi. Đề xuất isolation level và cách khóa phù hợp, giải thích các anomaly có thể chấp nhận.

## Kết luận

READ COMMITTED dùng MVCC để mỗi consistent read nhận một read view mới. Một transaction có thể nhìn thấy các thay đổi đã commit giữa hai câu SELECT, nhưng vẫn không đọc được dữ liệu chưa commit. Hành vi này phù hợp với ứng dụng cần dữ liệu mới theo từng câu lệnh và có thể chấp nhận non-repeatable read hoặc phantom read.

Khi cần nhiều câu đọc cùng nhìn một trạng thái dữ liệu ổn định, REPEATABLE READ thường phù hợp hơn. Khi cần bảo vệ hàng để đọc rồi cập nhật, hãy dùng locking read hoặc một câu UPDATE có điều kiện. READ COMMITTED vẫn sử dụng record lock cho thao tác ghi và locking read; nó chỉ tắt gap locking cho tìm kiếm thông thường, ngoại trừ kiểm tra foreign key và duplicate key. Cuối cùng, hãy kiểm tra session isolation level và row-based binary logging trước khi triển khai trong môi trường có replication.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — InnoDB Transaction Isolation Levels: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html
- MySQL 8.4 Reference Manual — Consistent Nonlocking Reads: https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html
- MySQL 8.4 Reference Manual — Locking Reads: https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html
- MySQL 8.4 Reference Manual — SET TRANSACTION Statement: https://dev.mysql.com/doc/refman/8.4/en/set-transaction.html
- MySQL 8.4 Reference Manual — START TRANSACTION, COMMIT, and ROLLBACK: https://dev.mysql.com/doc/refman/8.4/en/commit.html
- MySQL 8.4 Reference Manual — Binary Logging Options and Variables: https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html
- MySQL 8.4 Reference Manual — InnoDB Locking: https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html

