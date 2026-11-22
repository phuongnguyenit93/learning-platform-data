# Giao dịch, CREATE/DROP TEMPORARY TABLE và giới hạn rollback

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bảng tạm thường được dùng để gom dữ liệu trung gian, chuẩn hóa kết quả nhiều bước, tạo tập khóa cần xử lý hoặc chuẩn bị dữ liệu cho báo cáo. Khi kết hợp bảng tạm với transaction, cần phân biệt vòng đời của bảng, khả năng rollback của dữ liệu và ranh giới commit do từng câu lệnh SQL tạo ra.

Trong MySQL, transaction InnoDB có thể rollback các thay đổi dữ liệu transactional, nhưng không thể rollback việc tạo hoặc xóa một temporary table. Điểm dễ nhầm là CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE không gây implicit commit, nhưng bản thân thao tác tạo/xóa bảng tạm vẫn không thể được hoàn tác bằng ROLLBACK. Dữ liệu DML bên trong bảng tạm InnoDB có thể rollback như dữ liệu InnoDB thông thường. Muốn thiết kế quy trình an toàn, phải hiểu riêng ba lớp: transaction, object tạm theo session và storage engine của bảng.

## 1. Transaction trong MySQL và phạm vi rollback

Transaction là một nhóm thao tác dữ liệu được xử lý như một đơn vị logic. Với InnoDB, transaction cung cấp các đặc tính ACID:

- **Atomicity:** các thay đổi transactional được commit cùng nhau hoặc rollback cùng nhau.
- **Consistency:** ứng dụng và ràng buộc dữ liệu phải đưa database từ trạng thái hợp lệ này sang trạng thái hợp lệ khác.
- **Isolation:** các transaction đồng thời quan sát và tác động dữ liệu theo isolation level.
- **Durability:** thay đổi đã commit được bảo vệ theo cấu hình durability của MySQL và hệ thống lưu trữ.

Ví dụ chuyển tiền giữa hai tài khoản:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 500000
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 500000
WHERE account_id = 202;

COMMIT;
~~~

Nếu thao tác thứ hai thất bại vì một lỗi được ứng dụng xử lý, ứng dụng có thể ROLLBACK để hoàn tác thao tác trừ tiền đầu tiên. Transaction chỉ bảo vệ các thay đổi thuộc storage engine transactional và còn nằm trong transaction hiện tại.

### 1.1. Autocommit

MySQL thường bật autocommit theo session:

~~~sql
SELECT @@SESSION.autocommit;
~~~

Khi autocommit = 1, mỗi statement transactional độc lập được commit khi statement hoàn tất thành công nếu không có transaction tường minh đang mở. Khi cần gom nhiều statement, mở transaction:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 501;

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (9001, 501, 1);

COMMIT;
~~~

START TRANSACTION bắt đầu transaction tường minh. COMMIT xác nhận thay đổi; ROLLBACK hủy các thay đổi transactional chưa commit. Không nên nhầm việc tạo temporary table với việc bắt đầu hoặc kết thúc transaction.

### 1.2. COMMIT và ROLLBACK

~~~sql
START TRANSACTION;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 9001;

ROLLBACK;
~~~

Sau ROLLBACK, thay đổi status trong transaction InnoDB chưa commit được hoàn tác. Nếu dùng COMMIT thay cho ROLLBACK, thay đổi trở thành dữ liệu đã xác nhận.

Một transaction có thể kết thúc vì:

- Ứng dụng gửi COMMIT hoặc ROLLBACK.
- Một statement gây implicit commit.
- Session kết thúc hoặc kết nối bị đóng; transaction chưa commit thường bị rollback bởi server.
- Server gặp sự cố; InnoDB recovery khôi phục trạng thái transactional theo redo/undo và trạng thái commit.

Ứng dụng vẫn phải xử lý lỗi kết nối không rõ kết quả commit: nếu mất kết nối ngay sau khi gửi COMMIT, client có thể không biết server đã commit hay chưa. Cần thiết kế retry idempotent hoặc tra cứu trạng thái nghiệp vụ.

## 2. Temporary table là object theo session

Temporary table trong MySQL được tạo bằng CREATE TEMPORARY TABLE. Bảng chỉ nhìn thấy trong session đã tạo nó và tự biến mất khi session kết thúc.

~~~sql
CREATE TEMPORARY TABLE tmp_selected_orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_tmp_customer (customer_id)
) ENGINE = InnoDB;
~~~

Các đặc điểm cần nhớ:

- Session tạo bảng có thể đọc và ghi bảng đó.
- Session khác không nhìn thấy temporary table này, kể cả khi dùng cùng database.
- Hai session có thể tạo temporary table cùng tên mà không xung đột vì mỗi bảng thuộc session riêng.
- Bảng được tự động xóa khi session đóng.
- Bảng tạm có thể tồn tại qua nhiều transaction trong cùng session.
- Việc COMMIT hoặc ROLLBACK không tự động kết thúc vòng đời của temporary table.

### 2.1. Transaction và session là hai phạm vi khác nhau

Một session có thể thực hiện nhiều transaction liên tiếp nhưng vẫn giữ cùng temporary table:

~~~sql
CREATE TEMPORARY TABLE tmp_work (
    item_id BIGINT NOT NULL PRIMARY KEY,
    state VARCHAR(20) NOT NULL
) ENGINE = InnoDB;

START TRANSACTION;
INSERT INTO tmp_work (item_id, state)
VALUES (1, 'READY');
COMMIT;

START TRANSACTION;
UPDATE tmp_work
SET state = 'DONE'
WHERE item_id = 1;
ROLLBACK;

SELECT item_id, state
FROM tmp_work;
~~~

Kết quả cuối vẫn có hàng (1, 'READY'): transaction thứ nhất đã commit; transaction thứ hai đã rollback; temporary table vẫn còn trong session.

### 2.2. Temporary table có thể che khuất bảng thường cùng tên

Nếu session tạo temporary table trùng tên với một permanent table, trong session đó tên bảng sẽ trỏ đến temporary table. Các session khác vẫn nhìn thấy permanent table.

Ví dụ, nếu schema đã có bảng thường orders, session có thể tạo:

~~~sql
CREATE TEMPORARY TABLE orders (
    order_id BIGINT NOT NULL PRIMARY KEY,
    note VARCHAR(100)
) ENGINE = InnoDB;
~~~

Sau đó, câu SELECT * FROM orders trong session hiện tại đọc temporary table. Cách đặt tên này dễ gây nhầm lẫn khi debug và có thể khiến câu lệnh vô tình thao tác nhầm object. Nên dùng tiền tố rõ ràng như tmp_ hoặc work_, không dùng tên trùng bảng nghiệp vụ.

### 2.3. DROP TEMPORARY TABLE

Xóa đúng bảng tạm bằng:

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_selected_orders;
~~~

Từ khóa TEMPORARY giới hạn thao tác vào temporary table. Dùng IF EXISTS giúp cleanup an toàn khi bảng có thể chưa được tạo hoặc đã được xóa ở nhánh xử lý trước.

Không nên dựa vào việc đóng kết nối để cleanup trong ứng dụng dùng connection pool. Connection có thể được tái sử dụng cho request khác trước khi session thực sự bị đóng. Hãy chủ động xóa bảng tạm ở nhánh thành công và nhánh lỗi.

## 3. Storage engine quyết định rollback DML

Temporary table là object tạm theo session; khả năng rollback dữ liệu bên trong phụ thuộc storage engine.

### 3.1. InnoDB

Khai báo rõ ENGINE = InnoDB khi cần DML transactional:

~~~sql
CREATE TEMPORARY TABLE tmp_batch (
    row_id BIGINT NOT NULL PRIMARY KEY,
    result_value DECIMAL(14,2) NOT NULL
) ENGINE = InnoDB;

START TRANSACTION;

INSERT INTO tmp_batch (row_id, result_value)
VALUES (1, 10.00), (2, 20.00);

ROLLBACK;

SELECT COUNT(*) AS remaining_rows
FROM tmp_batch;
~~~

Kết quả remaining_rows là 0 vì INSERT thuộc transaction InnoDB đã rollback. Bảng tmp_batch vẫn tồn tại vì thao tác tạo bảng tạm không được rollback.

### 3.2. MEMORY

Temporary table cũng có thể dùng MEMORY:

~~~sql
CREATE TEMPORARY TABLE tmp_lookup (
    lookup_id BIGINT NOT NULL PRIMARY KEY,
    lookup_value VARCHAR(100) NOT NULL
) ENGINE = MEMORY;
~~~

MEMORY không cung cấp transaction rollback như InnoDB. DML trên bảng MEMORY không được hoàn tác bằng ROLLBACK. Bảng MEMORY lưu dữ liệu trong bộ nhớ và có giới hạn về kích thước, kiểu dữ liệu, index cùng hành vi khi server dừng. Chỉ dùng khi workload phù hợp và dữ liệu có thể tạo lại.

### 3.3. Không để engine mặc định quyết định semantics ngoài ý muốn

Nếu bài toán phụ thuộc vào rollback, hãy chỉ định InnoDB rõ ràng thay vì giả định default storage engine hoặc cấu hình server luôn giống nhau. Kiểm tra engine:

~~~sql
SHOW CREATE TABLE tmp_batch;
~~~

Một quy trình có thể đúng với temporary table InnoDB nhưng cho kết quả khác với temporary table MEMORY. Engine là một phần của thiết kế transaction.

## 4. CREATE/DROP TEMPORARY TABLE và implicit commit

Đây là quy tắc quan trọng nhất của bài:

**CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE không gây implicit commit, nhưng thao tác tạo/xóa temporary table không thể rollback.**

Ngoại lệ này khác với CREATE TABLE hoặc DROP TABLE thông thường. Các statement DDL thông thường có thể gây implicit commit và làm thay đổi ranh giới transaction.

### 4.1. CREATE TEMPORARY TABLE không commit transaction đang mở

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

CREATE TEMPORARY TABLE tmp_transaction_probe (
    probe_id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

ROLLBACK;
~~~

CREATE TEMPORARY TABLE không tự commit thay đổi trên accounts. ROLLBACK vẫn có thể hoàn tác UPDATE. Tuy nhiên, temporary table đã được tạo và vẫn tồn tại trong session sau ROLLBACK.

### 4.2. DROP TEMPORARY TABLE không commit transaction đang mở

~~~sql
CREATE TEMPORARY TABLE tmp_drop_probe (
    probe_id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

START TRANSACTION;

INSERT INTO tmp_drop_probe (probe_id)
VALUES (1);

DROP TEMPORARY TABLE tmp_drop_probe;

ROLLBACK;
~~~

DROP TEMPORARY TABLE không gây implicit commit, nhưng thao tác xóa bảng không thể rollback. Sau ROLLBACK, bảng vẫn đã bị xóa; không thể khôi phục object chỉ bằng ROLLBACK.

### 4.3. CREATE TABLE thông thường có implicit commit

So sánh:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

CREATE TABLE permanent_probe (
    probe_id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

ROLLBACK;
~~~

CREATE TABLE thông thường gây implicit commit. Thay đổi UPDATE trước DDL có thể đã được commit trước khi CREATE TABLE chạy. ROLLBACK phía sau không thể hoàn tác thay đổi đã commit và cũng không xóa bảng permanent vừa tạo.

Không đặt DDL permanent ở giữa một transaction nghiệp vụ nếu ứng dụng kỳ vọng rollback toàn bộ các thay đổi trước đó.

### 4.4. Các DDL khác vẫn có thể tạo implicit commit

Ngoại lệ của CREATE/DROP TEMPORARY TABLE không biến mọi DDL liên quan temporary table thành transactional. Các statement như ALTER TABLE, CREATE INDEX, DROP INDEX và TRUNCATE TABLE thuộc nhóm cần chú ý về implicit commit theo quy tắc MySQL.

Trước khi đưa DDL vào transaction, hãy kiểm tra semantics của đúng statement và phiên bản MySQL. Không suy luận rằng một thao tác an toàn với temporary table chỉ vì thao tác CREATE/DROP TEMPORARY TABLE không implicit commit.

### 4.5. Atomic DDL không đồng nghĩa rollback theo transaction người dùng

MySQL hỗ trợ atomic DDL cho các thao tác và storage engine được hỗ trợ, nhằm bảo đảm DDL hoàn tất nguyên vẹn hoặc được phục hồi sau crash. Điều đó không có nghĩa người dùng có thể đưa CREATE TABLE hoặc ALTER TABLE vào transaction rồi dùng ROLLBACK để hoàn tác DDL. Atomic DDL và transaction rollback là hai cơ chế khác nhau.

## 5. Ma trận hành vi cần phân biệt

| Thao tác | Implicit commit? | ROLLBACK hoàn tác object? | Ghi chú |
|---|---|---|---|
| INSERT vào temporary InnoDB | Không, nếu transaction đang mở | Không áp dụng | DML được rollback |
| UPDATE temporary InnoDB | Không, nếu transaction đang mở | Không áp dụng | DML được rollback |
| DELETE từ temporary InnoDB | Không, nếu transaction đang mở | Không áp dụng | DML được rollback |
| CREATE TEMPORARY TABLE | Không | Không | Bảng vẫn tồn tại sau rollback |
| DROP TEMPORARY TABLE | Không | Không | Bảng vẫn bị xóa sau rollback |
| CREATE TABLE thường | Có | Không | DDL và ranh giới commit |
| DROP TABLE thường | Có | Không | DDL và ranh giới commit |
| ALTER TABLE | Có | Không | Kiểm tra statement cụ thể |
| CREATE INDEX / DROP INDEX | Có | Không | Không xem như DML |
| TRUNCATE TABLE | Có | Không | Không dùng như DELETE transactional |
| INSERT vào bảng MEMORY | Không theo nghĩa commit DML transactional | Không | Engine không hỗ trợ rollback DML |

Ma trận này là cách ghi nhớ nhanh. Khi thiết kế migration hoặc transaction phức tạp, cần đối chiếu danh sách implicit commit của phiên bản MySQL đang chạy và engine thực tế.

## 6. Tạo bảng tạm từ dữ liệu truy vấn

Temporary table thường dùng để lưu kết quả trung gian qua nhiều statement.

### 6.1. Tạo cấu trúc rồi INSERT

~~~sql
CREATE TEMPORARY TABLE tmp_customer_totals (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    order_count BIGINT NOT NULL,
    revenue DECIMAL(18,2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_customer_totals (
    customer_id,
    order_count,
    revenue
)
SELECT
    customer_id,
    COUNT(*),
    SUM(total_amount)
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

Cách này cho phép định nghĩa kiểu dữ liệu, khóa và index rõ ràng trước khi nạp dữ liệu.

### 6.2. CREATE TEMPORARY TABLE ... AS SELECT

Có thể tạo bảng tạm từ kết quả SELECT:

~~~sql
CREATE TEMPORARY TABLE tmp_paid_orders
ENGINE = InnoDB
AS
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
WHERE status = 'PAID';
~~~

Cách này ngắn gọn để materialize một tập kết quả. Không giả định bảng được tạo sẽ tự có primary key hoặc index tối ưu cho các bước sau. Nếu truy vấn tiếp theo join theo customer_id, có thể cần bổ sung index:

~~~sql
ALTER TABLE tmp_paid_orders
ADD PRIMARY KEY (order_id),
ADD KEY ix_tmp_paid_customer (customer_id);
~~~

Lưu ý: ALTER TABLE và các DDL tương tự có semantics implicit commit riêng. Không đặt chúng giữa một transaction nghiệp vụ đang cần rollback nếu chưa đánh giá tác động.

### 6.3. CREATE TEMPORARY TABLE LIKE

Có thể sao chép cấu trúc bảng:

~~~sql
CREATE TEMPORARY TABLE tmp_orders LIKE orders;
~~~

LIKE giúp lấy cấu trúc và index của bảng nguồn theo quy tắc MySQL. Nó không sao chép các hàng dữ liệu. Bảng tạm vẫn thuộc session hiện tại.

Không dùng LIKE một cách mù quáng nếu bảng nguồn có cấu trúc phức tạp, generated columns, partitioning hoặc các thuộc tính mà bảng tạm không hỗ trợ giống hệt. Kiểm tra SHOW CREATE TABLE khi cần xác nhận.

## 7. Quy trình xử lý batch với temporary table

Một mẫu phổ biến là tạo tập khóa cần xử lý, kiểm tra dữ liệu, rồi cập nhật bảng chính trong transaction.

### 7.1. Chuẩn bị tập khóa

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_order_batch;

CREATE TEMPORARY TABLE tmp_order_batch (
    order_id BIGINT NOT NULL PRIMARY KEY,
    expected_status VARCHAR(20) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_order_batch (order_id, expected_status)
VALUES
    (9001, 'PENDING'),
    (9002, 'PENDING'),
    (9003, 'PENDING');
~~~

Tập batch có primary key để tránh trùng order_id. Nếu dữ liệu batch đến từ file hoặc staging table, có thể nạp bằng INSERT ... SELECT và kiểm tra số hàng trước khi xử lý.

### 7.2. Kiểm tra trước khi cập nhật

~~~sql
SELECT
    b.order_id,
    b.expected_status,
    o.status AS current_status
FROM tmp_order_batch AS b
LEFT JOIN orders AS o
  ON o.order_id = b.order_id;
~~~

Kiểm tra khóa không tồn tại, status không đúng hoặc dữ liệu không đáp ứng điều kiện nghiệp vụ. Nếu batch không hợp lệ, dừng trước khi cập nhật.

### 7.3. Cập nhật có điều kiện trong transaction

~~~sql
START TRANSACTION;

UPDATE orders AS o
JOIN tmp_order_batch AS b
  ON b.order_id = o.order_id
SET o.status = 'PROCESSING'
WHERE o.status = b.expected_status;

COMMIT;
~~~

Điều kiện status cũ giúp tránh cập nhật một hàng đã thay đổi từ lúc batch được chuẩn bị. Ứng dụng cần kiểm tra số hàng affected và xác định chính sách nếu số hàng cập nhật ít hơn số hàng trong batch.

### 7.4. Dọn dẹp

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_order_batch;
~~~

Thực hiện cleanup sau khi hoàn tất. Nếu có lỗi, cleanup trong nhánh finally của ứng dụng hoặc trong handler phù hợp. Đừng để temporary table tồn tại trong connection pool rồi vô tình được request tiếp theo sử dụng.

## 8. Temporary table và SAVEPOINT

SAVEPOINT cho phép rollback một phần thay đổi transactional trong cùng transaction:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 501;

SAVEPOINT after_inventory;

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (9001, 501, 1);

ROLLBACK TO SAVEPOINT after_inventory;

COMMIT;
~~~

Sau ROLLBACK TO SAVEPOINT, thao tác INSERT sau savepoint bị hoàn tác; thao tác UPDATE trước savepoint vẫn được commit. SAVEPOINT chỉ điều khiển thay đổi transactional. Nó không thể phục hồi temporary table đã DROP hoặc xóa temporary table được tạo sau savepoint.

### 8.1. Ví dụ kết hợp SAVEPOINT và bảng tạm

~~~sql
CREATE TEMPORARY TABLE tmp_savepoint_demo (
    id INT NOT NULL PRIMARY KEY,
    value_text VARCHAR(30) NOT NULL
) ENGINE = InnoDB;

START TRANSACTION;

INSERT INTO tmp_savepoint_demo VALUES (1, 'before');
SAVEPOINT sp_one;
INSERT INTO tmp_savepoint_demo VALUES (2, 'after');

ROLLBACK TO SAVEPOINT sp_one;
COMMIT;

SELECT * FROM tmp_savepoint_demo;
~~~

Kết quả có hàng id 1, không có hàng id 2. Temporary table vẫn tồn tại vì SAVEPOINT và COMMIT không xóa object.

## 9. Isolation và khả năng nhìn thấy temporary table

Isolation level điều khiển cách transaction quan sát dữ liệu transactional giữa các session. Nó không thay đổi quy tắc session scope của temporary table.

### 9.1. Session tạo bảng mới nhìn thấy bảng

Session A:

~~~sql
CREATE TEMPORARY TABLE tmp_private_data (
    id INT NOT NULL PRIMARY KEY,
    note VARCHAR(50) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_private_data VALUES (1, 'session A');
SELECT * FROM tmp_private_data;
~~~

Session A đọc được hàng đã tạo.

### 9.2. Session khác không nhìn thấy bảng tạm

Session B:

~~~sql
SELECT * FROM tmp_private_data;
~~~

Session B không nhìn thấy temporary table của Session A. Nếu trong schema có permanent table cùng tên, Session B có thể đọc permanent table đó. Vì vậy, cùng một câu SQL có thể truy cập object khác nhau ở hai session.

### 9.3. Temporary table không phải cơ chế chia sẻ dữ liệu giữa worker

Nếu hai connection của ứng dụng cần chia sẻ một tập dữ liệu, temporary table không phù hợp vì mỗi session có bản riêng. Hãy cân nhắc permanent staging table có batch_id, bảng hàng đợi hoặc cơ chế chia sẻ khác với khóa và quyền phù hợp.

### 9.4. Transaction isolation vẫn áp dụng cho bảng InnoDB

DML trên temporary InnoDB vẫn tham gia transaction của session. Đối với permanent InnoDB table, consistent read và locking read tuân theo isolation level đang dùng. Temporary table không làm các transaction khác nhìn thấy dữ liệu riêng trong session.

Kiểm tra isolation level:

~~~sql
SELECT @@SESSION.transaction_isolation;
~~~

Không dùng temporary table để thay thế khóa, ràng buộc hoặc isolation khi nhiều session cùng cập nhật một dữ liệu nghiệp vụ.

## 10. Lỗi thường gặp khi kết hợp transaction và temporary table

### 10.1. Nghĩ ROLLBACK sẽ xóa bảng vừa tạo

~~~sql
START TRANSACTION;
CREATE TEMPORARY TABLE tmp_example (id INT) ENGINE = InnoDB;
ROLLBACK;
~~~

Bảng tmp_example vẫn tồn tại trong session. Nếu muốn xóa, gọi DROP TEMPORARY TABLE rõ ràng.

### 10.2. Nghĩ DROP TEMPORARY TABLE có thể khôi phục

~~~sql
START TRANSACTION;
DROP TEMPORARY TABLE tmp_example;
ROLLBACK;
~~~

ROLLBACK không khôi phục bảng đã bị xóa. Nếu cần giữ dữ liệu tạm để retry, hãy trì hoãn DROP đến khi quy trình hoàn tất.

### 10.3. Dùng MEMORY rồi mong đợi rollback

Nếu bảng tạm dùng MEMORY, rollback DML không khôi phục trạng thái dữ liệu như InnoDB. Chọn engine theo yêu cầu transaction, không chỉ theo tên gọi "bảng tạm".

### 10.4. Dùng CREATE TABLE thường trong transaction nghiệp vụ

DDL permanent có thể commit transaction đang mở. Một câu CREATE TABLE có thể làm thay đổi đã thực hiện trước đó trở thành committed, khiến ROLLBACK phía sau không còn tác dụng với các thay đổi ấy.

### 10.5. Dùng TRUNCATE để dọn dữ liệu giữa transaction

TRUNCATE TABLE có semantics DDL và gây implicit commit theo quy tắc MySQL. Nếu cần xóa dữ liệu trong một temporary InnoDB table và vẫn muốn rollback, dùng DELETE trong transaction thay vì giả định TRUNCATE là thao tác DML.

~~~sql
START TRANSACTION;
DELETE FROM tmp_order_batch;
ROLLBACK;
~~~

Với InnoDB, các hàng bị DELETE được khôi phục sau ROLLBACK.

### 10.6. CREATE TEMPORARY TABLE IF NOT EXISTS không làm sạch bảng cũ

Nếu bảng cùng tên đã tồn tại trong session, CREATE TEMPORARY TABLE IF NOT EXISTS không tạo lại cấu trúc mới và không xóa dữ liệu cũ. Nó có thể khiến request tiếp theo dùng nhầm dữ liệu từ lần trước.

Mẫu an toàn hơn:

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_request_items;

CREATE TEMPORARY TABLE tmp_request_items (
    request_item_id BIGINT NOT NULL PRIMARY KEY,
    quantity INT NOT NULL
) ENGINE = InnoDB;
~~~

Chỉ dùng mẫu này khi session hiện tại sở hữu đúng temporary table có tên đó và ứng dụng kiểm soát vòng đời connection.

### 10.7. Connection pool tái sử dụng session

Temporary table gắn với connection vật lý, không gắn với request logic. Nếu request A tạo bảng rồi trả connection về pool mà không cleanup, request B có thể nhận đúng session đó và nhìn thấy bảng cũ.

Biện pháp:

- Tạo tên tạm có quy ước riêng và tránh trùng tên bảng nghiệp vụ.
- Xóa bảng trước khi tạo nếu quy trình đảm bảo quyền sở hữu tên.
- Dùng cleanup trong finally, kể cả khi transaction rollback hoặc có exception.
- Không giả định trả connection về pool đồng nghĩa đóng session.
- Xác định rõ pool có reset session hay không; vẫn nên cleanup chủ động.

## 11. Xử lý lỗi trong stored procedure và ứng dụng

Một quy trình có bảng tạm thường gồm nhiều statement. Nếu một statement thất bại, cần rollback DML và cleanup object theo đúng thứ tự.

### 11.1. Mẫu xử lý ở ứng dụng

Pseudo-code:

~~~text
borrow one physical connection
try:
    DROP TEMPORARY TABLE IF EXISTS tmp_job_rows
    CREATE TEMPORARY TABLE tmp_job_rows (...) ENGINE=InnoDB
    load rows into tmp_job_rows

    START TRANSACTION
    validate and update permanent InnoDB tables
    COMMIT
catch error:
    if transaction is active:
        ROLLBACK
    rethrow or map the error
finally:
    DROP TEMPORARY TABLE IF EXISTS tmp_job_rows
    return connection to pool
~~~

Cleanup phải chạy trên cùng physical connection đã tạo bảng. Nếu connection bị mất, session kết thúc và temporary table tự bị xóa; tuy nhiên, ứng dụng vẫn cần xác định kết quả commit có chắc chắn hay không trước khi retry nghiệp vụ.

### 11.2. Handler trong stored procedure

Một stored procedure có thể dùng EXIT HANDLER để rollback transaction khi lỗi:

~~~sql
DELIMITER //

CREATE PROCEDURE process_order_batch()
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        DROP TEMPORARY TABLE IF EXISTS tmp_order_batch;
        RESIGNAL;
    END;

    DROP TEMPORARY TABLE IF EXISTS tmp_order_batch;

    CREATE TEMPORARY TABLE tmp_order_batch (
        order_id BIGINT NOT NULL PRIMARY KEY
    ) ENGINE = InnoDB;

    INSERT INTO tmp_order_batch (order_id)
    SELECT order_id
    FROM orders
    WHERE status = 'PENDING';

    START TRANSACTION;

    UPDATE orders AS o
    JOIN tmp_order_batch AS b
      ON b.order_id = o.order_id
    SET o.status = 'PROCESSING'
    WHERE o.status = 'PENDING';

    COMMIT;

    DROP TEMPORARY TABLE IF EXISTS tmp_order_batch;
END//

DELIMITER ;
~~~

Ví dụ minh họa cấu trúc xử lý lỗi; procedure thực tế cần xác định rõ quyền, transaction ownership, khả năng gọi lồng và việc session có transaction do caller mở hay không. Procedure không nên tùy tiện COMMIT/ROLLBACK transaction mà caller đang quản lý.

### 11.3. Không nuốt lỗi sau ROLLBACK

Handler nên dùng RESIGNAL khi cần chuyển lỗi cho caller. Nếu chỉ rollback rồi trả về như thành công, ứng dụng có thể nghĩ batch đã được xử lý trong khi dữ liệu chưa commit.

## 12. Lock, deadlock và retry

Temporary table không loại bỏ tranh chấp trên permanent tables. Hai session vẫn có thể cập nhật cùng một hàng orders hoặc inventory.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 501
  AND available_quantity > 0;

COMMIT;
~~~

Nếu nhiều transaction cập nhật các hàng theo thứ tự khác nhau, deadlock có thể xảy ra. InnoDB chọn một transaction làm victim và rollback transaction đó. Ứng dụng cần:

1. Nhận diện lỗi deadlock hoặc lock wait timeout.
2. Rollback transaction còn lại nếu session vẫn đang mở.
3. Retry toàn bộ đơn vị nghiệp vụ với giới hạn số lần và backoff.
4. Bảo đảm thao tác retry idempotent hoặc có khóa nghiệp vụ.
5. Cleanup temporary table trên cùng connection trước khi tái sử dụng.

Không retry riêng statement cuối nếu các bước trước đã rollback hoặc kết quả commit chưa rõ.

## 13. Quy trình thiết kế an toàn

Khi kết hợp temporary table và transaction, dùng checklist sau:

1. Xác định bảng nào là temporary, bảng nào là permanent.
2. Xác định session vật lý sở hữu temporary table.
3. Chọn engine InnoDB nếu cần rollback DML.
4. Tạo temporary table trước transaction nghiệp vụ khi có thể để tách phần chuẩn bị dữ liệu khỏi phần cập nhật.
5. Nếu tạo hoặc drop bảng tạm bên trong transaction, nhớ rằng object change không thể rollback dù không gây implicit commit.
6. Tránh permanent DDL trong transaction nghiệp vụ đang mở.
7. Kiểm tra mọi statement có implicit commit, đặc biệt ALTER, CREATE/DROP INDEX và TRUNCATE.
8. Dùng SAVEPOINT chỉ cho DML transactional; không dùng nó để kỳ vọng phục hồi object.
9. Kiểm tra dữ liệu trung gian và số hàng trước khi cập nhật bảng chính.
10. Commit khi toàn bộ điều kiện nghiệp vụ đã đạt; rollback khi có lỗi.
11. Cleanup temporary table trong nhánh thành công và nhánh lỗi.
12. Kiểm tra connection pool không trả session còn bảng tạm hoặc transaction chưa kết thúc.
13. Thiết kế retry cho deadlock, timeout và kết nối mất ngay sau COMMIT.

## 14. Bài thực hành: quan sát giới hạn rollback

Thực hiện trên MySQL 8.0 trong database lab. Bài tập dùng bảng tạm riêng; không chạy trên bảng nghiệp vụ production.

### 14.1. Tạo temporary table InnoDB

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_rollback_lab;

CREATE TEMPORARY TABLE tmp_rollback_lab (
    row_id INT NOT NULL PRIMARY KEY,
    row_value VARCHAR(40) NOT NULL
) ENGINE = InnoDB;
~~~

### 14.2. Rollback dữ liệu nhưng giữ lại bảng

~~~sql
START TRANSACTION;

INSERT INTO tmp_rollback_lab (row_id, row_value)
VALUES (1, 'inserted in transaction');

ROLLBACK;

SELECT COUNT(*) AS row_count
FROM tmp_rollback_lab;

SHOW CREATE TABLE tmp_rollback_lab;
~~~

Quan sát:

- row_count bằng 0 vì INSERT đã rollback.
- SHOW CREATE TABLE vẫn đọc được cấu trúc vì temporary table vẫn tồn tại.

### 14.3. Commit một phần dữ liệu rồi rollback phần tiếp theo

~~~sql
START TRANSACTION;
INSERT INTO tmp_rollback_lab VALUES (2, 'committed row');
COMMIT;

START TRANSACTION;
INSERT INTO tmp_rollback_lab VALUES (3, 'rolled back row');
ROLLBACK;

SELECT *
FROM tmp_rollback_lab
ORDER BY row_id;
~~~

Kết quả có row_id 2 và không có row_id 3. Transaction không xóa temporary table sau mỗi lần kết thúc.

### 14.4. Tạo bảng tạm bên trong transaction rồi rollback

~~~sql
START TRANSACTION;

CREATE TEMPORARY TABLE tmp_created_inside_tx (
    id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

INSERT INTO tmp_created_inside_tx VALUES (10);

ROLLBACK;

SHOW CREATE TABLE tmp_created_inside_tx;
SELECT COUNT(*) AS row_count
FROM tmp_created_inside_tx;
~~~

Quan sát:

- Temporary table vẫn tồn tại sau ROLLBACK.
- Hàng INSERT transactional bị rollback nên row_count bằng 0.

Đây là phép thử trực tiếp để tách object lifecycle khỏi DML rollback.

### 14.5. DROP bảng tạm trong transaction rồi rollback

~~~sql
START TRANSACTION;
DROP TEMPORARY TABLE tmp_created_inside_tx;
ROLLBACK;

SHOW TABLES LIKE 'tmp_created_inside_tx';
~~~

SHOW TABLES không phải phép kiểm tra đáng tin cậy cho temporary table trong mọi ngữ cảnh. Hãy xác nhận bằng cách thử truy cập:

~~~sql
SELECT *
FROM tmp_created_inside_tx;
~~~

Truy vấn sẽ báo không tồn tại vì DROP TEMPORARY TABLE không thể rollback. Dùng một tên bảng lab mới nếu cần chạy lại bước này.

### 14.6. So sánh CREATE TABLE thường

Chỉ thực hiện trong schema lab:

~~~sql
CREATE TABLE lab_permanent_ddl_probe (
    id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

START TRANSACTION;

INSERT INTO lab_permanent_ddl_probe (id)
VALUES (1);

CREATE TABLE lab_ddl_commit_probe (
    id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

ROLLBACK;

SELECT *
FROM lab_permanent_ddl_probe;

SHOW TABLES LIKE 'lab_ddl_commit_probe';
~~~

Quan sát hàng id 1 vẫn còn vì CREATE TABLE thường gây implicit commit trước DDL. Bảng lab_ddl_commit_probe cũng vẫn tồn tại sau ROLLBACK.

### 14.7. Dọn dữ liệu lab

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_rollback_lab;
DROP TEMPORARY TABLE IF EXISTS tmp_created_inside_tx;
DROP TABLE IF EXISTS lab_ddl_commit_probe;
DROP TABLE IF EXISTS lab_permanent_ddl_probe;
~~~

Chỉ chạy phần DROP permanent table nếu chính bạn đã tạo hai bảng lab đó trong schema lab.

### 14.8. Câu hỏi tự kiểm tra

1. Vì sao ROLLBACK hoàn tác INSERT vào temporary InnoDB nhưng không xóa temporary table?
2. CREATE TEMPORARY TABLE có implicit commit không?
3. DROP TEMPORARY TABLE có thể được khôi phục bằng ROLLBACK không?
4. Điều gì thay đổi nếu temporary table dùng MEMORY?
5. Vì sao CREATE TABLE thường ở giữa transaction có thể commit DML trước đó?
6. Vì sao connection pool cần cleanup temporary table trước khi trả connection?
7. SAVEPOINT có thể phục hồi temporary table đã bị DROP không?
8. Khi mất kết nối ngay sau COMMIT, ứng dụng nên xác định kết quả nghiệp vụ như thế nào trước khi retry?

## 15. Bảng phân biệt nhanh

| Khái niệm | Phạm vi | Kết thúc khi nào? | ROLLBACK tác động |
|---|---|---|---|
| Session | Một kết nối vật lý | Kết nối đóng | Không xóa object ngoài semantics của session |
| Transaction | Một đơn vị thay đổi dữ liệu | COMMIT, ROLLBACK hoặc implicit commit | Hoàn tác DML transactional chưa commit |
| Temporary table | Session tạo bảng | DROP TEMPORARY TABLE hoặc session đóng | Không hoàn tác CREATE/DROP object |
| InnoDB temporary table | Dữ liệu tạm trong session | Object bị drop/session đóng | DML transactional có thể rollback |
| MEMORY temporary table | Dữ liệu tạm trong session và RAM | Drop/session đóng hoặc server restart | DML không có rollback transactional |
| Permanent table | Schema database | DDL hoặc quản trị schema | DDL không được ROLLBACK theo transaction người dùng |

## 16. Nguyên tắc cần ghi nhớ

- Transaction và session là hai phạm vi khác nhau. Transaction kết thúc không làm temporary table biến mất.
- Temporary table chỉ nhìn thấy trong session tạo ra nó và tự xóa khi session kết thúc.
- Temporary table có thể che bảng permanent cùng tên trong session; dùng tiền tố riêng như tmp_ để tránh nhầm lẫn.
- CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE không gây implicit commit, nhưng bản thân thao tác tạo/xóa không thể rollback.
- DML trên temporary InnoDB có thể rollback; DML trên MEMORY không có transaction rollback như InnoDB.
- Chỉ định ENGINE = InnoDB nếu quy trình phụ thuộc vào khả năng rollback dữ liệu tạm.
- CREATE TABLE và DROP TABLE thường có implicit commit; không đặt permanent DDL giữa transaction nghiệp vụ nếu cần rollback toàn bộ.
- ALTER TABLE, CREATE/DROP INDEX và TRUNCATE TABLE cần được xem xét theo quy tắc implicit commit riêng.
- SAVEPOINT chỉ điều khiển thay đổi transactional, không phục hồi temporary table đã bị drop hoặc xóa object được tạo sau savepoint.
- CREATE TEMPORARY TABLE IF NOT EXISTS không tự làm sạch dữ liệu cũ trong session.
- Connection pool tái sử dụng session vật lý; cleanup bảng tạm trong finally và không giả định trả connection về pool là đóng session.
- Kiểm tra số hàng, trạng thái hiện tại và điều kiện nghiệp vụ trước khi cập nhật permanent tables.
- Xử lý deadlock, lock timeout và kết nối mất bằng retry idempotent; xác định kết quả COMMIT trước khi chạy lại nghiệp vụ.
- Atomic DDL bảo vệ tính nguyên vẹn của thao tác DDL khi crash, không biến DDL thành thao tác có thể rollback theo transaction người dùng.

Khi thiết kế quy trình có bảng tạm, hãy quyết định rõ dữ liệu nào cần rollback, object nào cần tồn tại qua nhiều transaction và session nào sở hữu bảng. Dùng InnoDB cho DML cần rollback, đặt DDL permanent ngoài transaction nghiệp vụ, hiểu ngoại lệ implicit commit của CREATE/DROP TEMPORARY TABLE và luôn cleanup trên đúng connection. Nhờ vậy, bảng tạm có thể hỗ trợ xử lý batch nhiều bước mà không tạo ra giả định sai về tính nguyên tử của dữ liệu và cấu trúc bảng.
