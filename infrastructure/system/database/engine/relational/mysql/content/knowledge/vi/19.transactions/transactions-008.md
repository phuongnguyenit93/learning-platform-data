# Giao dịch chứa bảng không hỗ trợ transaction và thao tác ngoài database

Bài học thuộc chương **Giao dịch** của module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Một giao dịch chỉ có thể bảo đảm rollback cho những thay đổi thuộc các tài nguyên thực sự tham gia cơ chế transaction. Khi câu lệnh chạm đến bảng không hỗ trợ transaction hoặc gọi một hệ thống bên ngoài, ranh giới nguyên tử của giao dịch bị mở rộng vượt quá khả năng của COMMIT và ROLLBACK thông thường.

Sau bài này, bạn có thể nhận diện bảng transactional và nontransactional, dự đoán kết quả khi trộn InnoDB với MyISAM, xử lý cảnh báo rollback không hoàn chỉnh, phát hiện câu lệnh gây implicit commit và thiết kế quy trình phối hợp database với email, message broker, API thanh toán, file hoặc dịch vụ khác bằng Transactional Outbox, Idempotency, Saga hoặc XA khi phù hợp.

## 1. Ranh giới của một transaction MySQL

Một transaction cục bộ của MySQL điều phối thay đổi trên những bảng dùng storage engine hỗ trợ transaction. Với InnoDB, các thay đổi chưa COMMIT có thể được hoàn tác bằng ROLLBACK.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Nếu các bảng liên quan đều được quản lý bởi InnoDB, hai cập nhật thuộc cùng transaction. Nếu câu lệnh thứ hai thất bại và ứng dụng quyết định ROLLBACK, thay đổi của câu lệnh đầu cũng được hoàn tác.

Nhưng một transaction MySQL không tự động bao gồm:

- Bảng dùng storage engine không hỗ trợ transaction.
- Một kết nối database khác nếu không được phối hợp bằng cơ chế distributed transaction.
- Một HTTP request đến dịch vụ bên ngoài.
- Việc gửi email hoặc SMS.
- Việc gửi message đến broker.
- Ghi file, upload object hoặc thao tác trên filesystem.
- Một lệnh gọi đến cổng thanh toán hoặc hệ thống đối tác.

ROLLBACK chỉ yêu cầu MySQL hoàn tác những thay đổi mà transaction engine có thể hoàn tác. Nó không thể thu hồi một email đã gửi hoặc đảo ngược một khoản thanh toán đã được hệ thống khác xác nhận.

## 2. Transactional và nontransactional storage engine

Storage engine quyết định cách MySQL lưu trữ và quản lý dữ liệu của bảng.

| Engine | Hỗ trợ transaction | Có thể rollback DML? | Ghi chú |
|---|---|---|---|
| InnoDB | Có | Có | Engine mặc định phổ biến, hỗ trợ ACID và khóa ngoại |
| MyISAM | Không | Không | Thay đổi được ghi ngay, không tham gia rollback của transaction |
| MEMORY | Không | Không | Dữ liệu nằm trong bộ nhớ, không có transaction |
| NDB | Có | Có | Engine transactional cho MySQL NDB Cluster, có đặc điểm vận hành riêng |

Đừng suy luận khả năng transaction từ cú pháp SQL. Hai bảng có cùng cấu trúc nhưng khác ENGINE có thể có hành vi COMMIT/ROLLBACK hoàn toàn khác.

### Kiểm tra engine của bảng

Dùng SHOW CREATE TABLE:

~~~sql
SHOW CREATE TABLE orders;
~~~

Trong kết quả, tìm phần ENGINE=InnoDB hoặc ENGINE=MyISAM.

Có thể xem nhanh bằng:

~~~sql
SHOW TABLE STATUS LIKE 'orders';
~~~

Cột Engine cho biết storage engine của bảng.

Kiểm tra nhiều bảng trong database hiện tại:

~~~sql
SELECT
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
      'orders',
      'order_items',
      'legacy_audit'
  );
~~~

Kiểm tra các engine server hỗ trợ:

~~~sql
SHOW ENGINES;
~~~

Hãy xác minh engine sau khi tạo bảng hoặc sau khi import/migration. Nếu engine mong muốn không được server hỗ trợ hoặc bị vô hiệu hóa, cấu hình và SQL mode có thể khiến bảng được tạo bằng engine thay thế. Đừng mặc định rằng khai báo ENGINE=InnoDB trong script đồng nghĩa bảng thực tế chắc chắn là InnoDB.

## 3. Điều gì xảy ra khi trộn InnoDB và MyISAM trong cùng transaction?

Giả sử một nghiệp vụ ghi hai nơi:

- Bảng orders dùng InnoDB để lưu đơn hàng.
- Bảng legacy_audit dùng MyISAM để ghi dấu vết.

Một transaction thực hiện:

~~~sql
START TRANSACTION;

INSERT INTO orders (order_id, customer_id, total_amount)
VALUES (1001, 42, 500.00);

INSERT INTO legacy_audit (event_name, reference_id)
VALUES ('ORDER_CREATED', 1001);

ROLLBACK;
~~~

Kết quả:

- Hàng trong orders được rollback vì InnoDB hỗ trợ transaction.
- Hàng trong legacy_audit vẫn tồn tại vì MyISAM không hỗ trợ rollback.
- MySQL có thể phát cảnh báo ER_WARNING_NOT_COMPLETE_ROLLBACK.

Thay đổi trên bảng nontransactional được lưu ngay khi câu lệnh thực thi, bất kể autocommit đang bật hay tắt. Vì vậy, việc đặt câu INSERT MyISAM bên trong START TRANSACTION không biến MyISAM thành bảng transactional.

### Minh họa bằng bảng

| Thời điểm | InnoDB: orders | MyISAM: legacy_audit |
|---|---|---|
| Trước transaction | Không có đơn 1001 | Không có sự kiện |
| Sau INSERT đầu tiên | Có thay đổi chưa COMMIT | Chưa có thay đổi |
| Sau INSERT thứ hai | Vẫn chưa COMMIT | Sự kiện đã được ghi ngay |
| Sau ROLLBACK | Đơn 1001 biến mất | Sự kiện vẫn tồn tại |

Đây là trạng thái không nhất quán về nghiệp vụ: audit nói đơn hàng đã được tạo, nhưng bảng đơn hàng không có đơn đó.

### ROLLBACK không có nghĩa mọi thứ đã được hoàn tác

Thông báo cảnh báo điển hình:

~~~text
Warning: Some non-transactional changed tables couldn't be rolled back
~~~

Cảnh báo này có ý nghĩa thực tế: có một hoặc nhiều bảng trong transaction không hỗ trợ transaction nên MySQL không thể hoàn tác các thay đổi ở đó.

Nếu ứng dụng chỉ kiểm tra rằng lệnh ROLLBACK đã được gửi mà bỏ qua Warning, nó có thể báo thất bại toàn bộ nghiệp vụ trong khi dữ liệu phụ vẫn được ghi.

Sau ROLLBACK, hãy kiểm tra Warning trước khi chạy câu SQL thông thường khác:

~~~sql
ROLLBACK;
SHOW WARNINGS;
~~~

Sau đó mới kiểm tra dữ liệu:

~~~sql
SELECT * FROM orders WHERE order_id = 1001;
SELECT * FROM legacy_audit WHERE reference_id = 1001;
~~~

Kết quả mong đợi: truy vấn orders không có hàng, còn legacy_audit có sự kiện.

## 4. Bài thực hành: quan sát rollback không hoàn chỉnh

Tạo database lab và hai bảng có engine khác nhau:

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_mixed_transaction_lab;
USE mysql_mixed_transaction_lab;

CREATE TABLE orders_innodb (
    order_id INT NOT NULL PRIMARY KEY,
    customer_id INT NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE audit_myisam (
    audit_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(50) NOT NULL,
    reference_id INT NOT NULL
) ENGINE=MyISAM;
~~~

Xác nhận engine:

~~~sql
SHOW TABLE STATUS LIKE 'orders_innodb';
SHOW TABLE STATUS LIKE 'audit_myisam';
~~~

Thực hiện transaction:

~~~sql
START TRANSACTION;

INSERT INTO orders_innodb
    (order_id, customer_id, total_amount)
VALUES
    (1001, 42, 500.00);

INSERT INTO audit_myisam
    (event_name, reference_id)
VALUES
    ('ORDER_CREATED', 1001);

ROLLBACK;
SHOW WARNINGS;
~~~

Kiểm tra dữ liệu:

~~~sql
SELECT * FROM orders_innodb;
SELECT * FROM audit_myisam;
~~~

Kết quả kỳ vọng:

- orders_innodb không còn hàng 1001.
- audit_myisam vẫn còn sự kiện ORDER_CREATED.
- ROLLBACK có thể trả Warning về thay đổi nontransactional không thể hoàn tác.

### So sánh với transaction chỉ dùng InnoDB

~~~sql
CREATE TABLE audit_innodb (
    audit_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(50) NOT NULL,
    reference_id INT NOT NULL
) ENGINE=InnoDB;

START TRANSACTION;

INSERT INTO orders_innodb
    (order_id, customer_id, total_amount)
VALUES
    (1002, 42, 300.00);

INSERT INTO audit_innodb
    (event_name, reference_id)
VALUES
    ('ORDER_CREATED', 1002);

ROLLBACK;

SELECT * FROM orders_innodb WHERE order_id = 1002;
SELECT * FROM audit_innodb WHERE reference_id = 1002;
~~~

Cả hai truy vấn đều không trả hàng. Vì cả hai bảng dùng InnoDB, transaction có thể hoàn tác cả thay đổi nghiệp vụ lẫn audit.

### Dọn dẹp

~~~sql
DROP DATABASE mysql_mixed_transaction_lab;
~~~

Chỉ chạy trên database lab vừa tạo. Lệnh này xóa các bảng và dữ liệu thực hành.

## 5. autocommit không biến bảng nontransactional thành transactional

MySQL thường chạy với:

~~~sql
SELECT @@SESSION.autocommit;
~~~

Khi autocommit = 1, mỗi câu lệnh độc lập được commit tự động nếu thành công.

Có thể tắt autocommit trong session:

~~~sql
SET autocommit = 0;
~~~

Với bảng transactional như InnoDB, thay đổi chưa được commit có thể được rollback.

Nhưng với bảng nontransactional như MyISAM, thay đổi vẫn được ghi ngay. Ví dụ:

~~~sql
SET autocommit = 0;

INSERT INTO audit_myisam (event_name, reference_id)
VALUES ('IMPORT_STARTED', 500);

ROLLBACK;

SELECT *
FROM audit_myisam
WHERE reference_id = 500;

SET autocommit = 1;
~~~

Hàng MyISAM vẫn tồn tại. autocommit = 0 chỉ ảnh hưởng cách quản lý transaction của các engine có hỗ trợ transaction; nó không thêm khả năng rollback cho engine khác.

### Phạm vi session

autocommit là biến theo session. Một connection trong connection pool có thể giữ trạng thái khác connection khác. Ứng dụng cần quản lý transaction và trạng thái session trên đúng connection.

Các bước START TRANSACTION, DML, COMMIT/ROLLBACK phải chạy trên cùng connection. Nếu ứng dụng mở connection thứ hai để thực hiện một câu lệnh, thay đổi ở connection đó không tự tham gia transaction của connection đầu.

## 6. Không nên trộn nhiều storage engine trong một nghiệp vụ cần tính nguyên tử

Cách an toàn nhất cho một transaction nghiệp vụ là dùng các bảng thuộc cùng một transaction-safe storage engine, thường là InnoDB.

Ví dụ:

~~~sql
START TRANSACTION;

INSERT INTO orders_innodb
    (order_id, customer_id, total_amount)
VALUES
    (1003, 42, 800.00);

INSERT INTO audit_innodb
    (event_name, reference_id)
VALUES
    ('ORDER_CREATED', 1003);

COMMIT;
~~~

Nếu một câu lệnh thất bại và ứng dụng rollback, cả hai thay đổi đều có thể được hoàn tác.

MySQL cũng khuyến nghị transaction nên thao tác trên các bảng do một transaction-safe storage engine quản lý. Ngay cả khi dùng nhiều engine đều hỗ trợ transaction, việc trộn engine có thể có các giới hạn về tính nguyên tử và khả năng quan sát thay đổi tùy isolation level. Không nên suy ra rằng nhiều engine transactional luôn tương đương một transaction đơn giản trên một engine.

MySQL lưu ý thêm: khi một transaction dùng nhiều transaction-safe engine và isolation level không phải SERIALIZABLE, một transaction khác có thể quan sát một phần thay đổi đã được commit của transaction thứ nhất. Nếu phải dùng nhiều engine transactional, cần đánh giá isolation level và mô hình truy cập đồng thời theo tài liệu MySQL; lựa chọn đơn giản hơn vẫn là giữ các bảng nghiệp vụ trong cùng engine.

### Nếu bắt buộc giữ bảng legacy MyISAM?

Có ba hướng thường gặp:

1. **Chuyển bảng sang InnoDB:** lựa chọn tốt nhất nếu bảng là dữ liệu nghiệp vụ cần rollback, khóa ngoại hoặc tính nhất quán.
2. **Tách dữ liệu phụ khỏi transaction chính:** ghi ý định xử lý vào bảng outbox InnoDB rồi để worker cập nhật hệ thống legacy sau khi commit.
3. **Chấp nhận tính nhất quán cuối cùng:** nếu bảng phụ chỉ là thống kê/cache, thiết kế job đồng bộ và quy trình sửa lệch dữ liệu.

Không dùng MyISAM làm nơi lưu audit nghiệp vụ bắt buộc phải đồng bộ nguyên tử với dữ liệu chính.

## 7. DDL có thể COMMIT ngầm transaction

Một lỗi khác là nghĩ rằng mọi câu SQL nằm giữa START TRANSACTION và ROLLBACK đều có thể hoàn tác.

Nhiều câu lệnh DDL gây implicit commit. Điều đó có nghĩa MySQL kết thúc transaction hiện tại như thể đã COMMIT trước khi thực thi câu lệnh DDL. Phần lớn các câu lệnh này còn commit sau khi chạy xong.

Các lệnh cần chú ý gồm:

- CREATE TABLE
- ALTER TABLE
- DROP TABLE
- TRUNCATE TABLE
- CREATE INDEX
- DROP INDEX
- CREATE DATABASE
- DROP DATABASE
- CREATE VIEW, DROP VIEW

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

ALTER TABLE accounts
ADD COLUMN note VARCHAR(100) NULL;

ROLLBACK;
~~~

Không được giả định rằng UPDATE sẽ được rollback. ALTER TABLE gây implicit commit trước khi chạy, nên thay đổi tài khoản có thể đã được commit trước khi câu ALTER được thực hiện.

### CREATE TEMPORARY TABLE là ngoại lệ có giới hạn

CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE không gây implicit commit theo quy tắc thông thường. Nhưng thao tác tạo hoặc xóa bảng tạm vẫn không được rollback. Nếu tạo bảng tạm trong transaction rồi ROLLBACK, bảng tạm vẫn tồn tại trong session.

Do đó, ngoại lệ này không có nghĩa DDL trở nên transactional.

### Quy tắc thực hành

- Không chạy DDL giữa các bước DML cần rollback cùng nhau.
- Tách migration/schema change khỏi transaction nghiệp vụ.
- Kiểm tra danh sách statement có implicit commit trước khi viết script quản trị.
- Không dùng ROLLBACK để thử hoàn tác CREATE/ALTER/DROP trên môi trường thật.

## 8. Thao tác ngoài database: vì sao ROLLBACK không đủ?

Một ứng dụng thường phối hợp MySQL với nhiều hệ thống khác:

- Gửi email xác nhận đơn.
- Gửi SMS hoặc push notification.
- Gọi cổng thanh toán.
- Đẩy message vào Kafka, RabbitMQ hoặc một message broker khác.
- Upload ảnh hoặc tài liệu lên object storage.
- Ghi file trên máy chủ.
- Gọi một dịch vụ quản lý kho hoặc vận chuyển.

Các hệ thống này không tự động tham gia transaction cục bộ của MySQL. Một lệnh ROLLBACK không thể yêu cầu chúng xóa tác động đã thực hiện.

### Gọi dịch vụ ngoài trước COMMIT

Ví dụ:

~~~text
BEGIN TRANSACTION
  cập nhật tồn kho
  gọi API thanh toán thành công
  INSERT đơn hàng thất bại
ROLLBACK
~~~

Kết quả:

- Tồn kho được rollback.
- Đơn hàng không được tạo.
- Khoản thanh toán vẫn có thể đã được thu.

Đây là tình huống nguy hiểm: hệ thống đã thu tiền nhưng database không có đơn hàng tương ứng.

### Gọi dịch vụ ngoài sau COMMIT

Ví dụ:

~~~text
BEGIN TRANSACTION
  tạo đơn hàng
  giảm tồn kho
COMMIT

gửi email xác nhận
~~~

Nếu tiến trình bị dừng ngay sau COMMIT nhưng trước khi gửi email, database có đơn hàng nhưng khách hàng không nhận được email.

Nếu gửi email thành công nhưng ứng dụng mất kết nối trước khi ghi nhận trạng thái gửi, lần retry có thể gửi email lần thứ hai.

### Hai khoảng trống lỗi

| Thứ tự | Lỗi có thể xảy ra | Kết quả |
|---|---|---|
| Gọi ngoài trước COMMIT | Dịch vụ ngoài thành công, COMMIT thất bại | Tác động ngoài tồn tại nhưng database rollback |
| COMMIT trước, gọi ngoài sau | Database thành công, dịch vụ ngoài thất bại | Dữ liệu đã commit nhưng tác động ngoài chưa xảy ra |
| Dịch vụ ngoài thành công, ứng dụng crash trước khi ghi nhận | Worker hoặc ứng dụng retry | Có thể gửi/trừ tiền/xử lý trùng |

Đây là vấn đề phối hợp nhiều tài nguyên, không thể giải quyết chỉ bằng cách đặt thêm ROLLBACK trong catch block.

## 9. Mẫu dễ lỗi trong ứng dụng

Ví dụ giả mã:

~~~java
connection.setAutoCommit(false);

try {
    insertOrder(connection, order);

    // Lời gọi HTTP nằm trong transaction MySQL
    paymentGateway.charge(order.payment());

    connection.commit();
} catch (Exception ex) {
    connection.rollback();
    throw ex;
}
~~~

Có hai vấn đề:

1. Nếu cổng thanh toán đã thu tiền rồi COMMIT thất bại, ROLLBACK không hoàn lại tiền.
2. Kết nối và khóa database có thể bị giữ trong suốt thời gian chờ HTTP, làm tăng độ trễ và tranh chấp.

Không nên giữ transaction MySQL mở trong khi chờ một dịch vụ mạng chậm nếu không có lý do rất rõ ràng. Thời gian chờ có thể kéo dài, timeout hoặc không xác định.

Một biến thể gọi HTTP sau COMMIT tránh giữ transaction trong lúc chờ mạng, nhưng vẫn có khoảng trống crash giữa COMMIT và HTTP. Cần một cơ chế lưu ý định gửi và retry.

## 10. Transactional Outbox: ghi ý định gửi cùng transaction

Transactional Outbox giải quyết khoảng trống giữa việc commit dữ liệu nghiệp vụ và việc yêu cầu một hệ thống ngoài xử lý sự kiện.

Ý tưởng:

1. Ghi dữ liệu nghiệp vụ vào bảng InnoDB.
2. Ghi một sự kiện cần phát vào bảng outbox InnoDB trong cùng transaction.
3. COMMIT một lần cho cả hai.
4. Một worker đọc outbox sau khi commit.
5. Worker gửi sự kiện đến hệ thống ngoài.
6. Worker ghi nhận trạng thái gửi và retry khi cần.

Nếu transaction rollback, cả dữ liệu nghiệp vụ và sự kiện outbox đều biến mất. Nếu transaction commit, cả hai cùng tồn tại để worker có thể xử lý.

### Sơ đồ luồng

~~~mermaid
flowchart TD
    A[Ứng dụng nhận yêu cầu] --> B[START TRANSACTION]
    B --> C[Thay đổi dữ liệu nghiệp vụ InnoDB]
    C --> D[INSERT sự kiện vào outbox InnoDB]
    D --> E{COMMIT thành công?}
    E -->|Không| F[ROLLBACK: cả hai thay đổi biến mất]
    E -->|Có| G[Worker đọc outbox]
    G --> H[Gửi message/API bên ngoài]
    H --> I{Đã nhận thành công?}
    I -->|Có| J[Đánh dấu SENT]
    I -->|Không| K[Lên lịch retry hoặc FAILED]
    K --> G
~~~

Outbox không khiến message broker hoặc API trở thành một phần của transaction MySQL. Nó bảo đảm rằng ý định phát sự kiện được lưu bền vững cùng dữ liệu nghiệp vụ, sau đó worker chịu trách nhiệm giao sự kiện.

### Tạo bảng nghiệp vụ và outbox

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE outbox_events (
    event_id CHAR(36) NOT NULL PRIMARY KEY,
    aggregate_type VARCHAR(50) NOT NULL,
    aggregate_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    status ENUM('PENDING', 'PROCESSING', 'SENT', 'FAILED')
        NOT NULL DEFAULT 'PENDING',
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    available_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    lease_until DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    sent_at DATETIME(6) NULL,
    KEY idx_outbox_dispatch (status, available_at, created_at)
) ENGINE=InnoDB;
~~~

Điểm bắt buộc: bảng nghiệp vụ và bảng outbox phải cùng nằm trong phạm vi transaction có thể commit/rollback. Nếu outbox dùng MyISAM, lỗi rollback lại xuất hiện.

### Ghi dữ liệu và sự kiện trong cùng transaction

~~~sql
START TRANSACTION;

INSERT INTO orders
    (customer_id, total_amount, status)
VALUES
    (42, 500.00, 'PENDING');

SET @new_order_id = LAST_INSERT_ID();

INSERT INTO outbox_events
    (
        event_id,
        aggregate_type,
        aggregate_id,
        event_type,
        payload
    )
VALUES
    (
        UUID(),
        'ORDER',
        @new_order_id,
        'OrderCreated',
        JSON_OBJECT(
            'orderId', @new_order_id,
            'customerId', 42,
            'totalAmount', 500.00
        )
    );

COMMIT;
~~~

Nếu INSERT outbox thất bại, ứng dụng rollback và đơn hàng cũng không được tạo. Nếu COMMIT thành công, worker có thể tìm thấy sự kiện OrderCreated.

### Worker lấy sự kiện cần gửi

Worker nên lấy một sự kiện, đánh dấu đang xử lý trong transaction ngắn rồi commit trước khi gọi mạng.

Ví dụ theo mô hình một worker lấy một sự kiện:

~~~sql
START TRANSACTION;

SELECT
    event_id,
    event_type,
    payload
FROM outbox_events
WHERE status = 'PENDING'
  AND available_at <= CURRENT_TIMESTAMP(6)
ORDER BY created_at, event_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
~~~

Ứng dụng đọc event_id của hàng được chọn. Nếu có hàng, cập nhật trạng thái trong cùng transaction:

~~~sql
UPDATE outbox_events
SET
    status = 'PROCESSING',
    attempts = attempts + 1,
    lease_until = CURRENT_TIMESTAMP(6) + INTERVAL 1 MINUTE
WHERE event_id = ?;

COMMIT;
~~~

Nếu SELECT không trả hàng, worker kết thúc transaction ngắn và chờ lần polling tiếp theo.

FOR UPDATE SKIP LOCKED giúp nhiều worker lấy các hàng khác nhau mà không phải chờ hàng đang bị worker khác khóa. Tính năng này phù hợp cho mô hình hàng đợi; không dùng SKIP LOCKED như một cách đọc nhất quán tổng quát. Cú pháp này cần phiên bản MySQL hỗ trợ locking read với SKIP LOCKED.

Sau COMMIT, worker gọi message broker hoặc API bằng payload đã đọc. Không giữ transaction và row lock trong suốt thời gian chờ mạng.

### Ghi nhận kết quả gửi

Nếu gửi thành công:

~~~sql
UPDATE outbox_events
SET
    status = 'SENT',
    sent_at = CURRENT_TIMESTAMP(6),
    lease_until = NULL
WHERE event_id = ?
  AND status = 'PROCESSING';
~~~

Nếu gửi thất bại tạm thời, đặt lại PENDING với thời điểm thử tiếp:

~~~sql
UPDATE outbox_events
SET
    status = 'PENDING',
    available_at = CURRENT_TIMESTAMP(6) + INTERVAL 30 SECOND,
    lease_until = NULL
WHERE event_id = ?
  AND status = 'PROCESSING';
~~~

Sau một số lần thử nhất định, chuyển sang FAILED và phát cảnh báo để người vận hành điều tra. Không retry vô hạn mà không có giới hạn, backoff hoặc giám sát.

Nếu worker chết khi trạng thái PROCESSING, một worker khác có thể nhận lại hàng sau khi lease_until hết hạn. Cơ chế lease cần được thiết kế cẩn thận để không hai worker cùng xử lý một sự kiện trong điều kiện bình thường.

Trong thiết kế này, worker hoặc một tiến trình recovery cần đưa các lease hết hạn trở lại hàng đợi trước khi truy vấn chỉ lấy PENDING:

~~~sql
UPDATE outbox_events
SET
    status = 'PENDING',
    available_at = CURRENT_TIMESTAMP(6),
    lease_until = NULL
WHERE status = 'PROCESSING'
  AND lease_until < CURRENT_TIMESTAMP(6);
~~~

Chỉ thực hiện recovery sau khi lease hết hạn. Nếu worker cũ vẫn đang gửi chậm, worker mới có thể gửi lại cùng event; vì vậy cần lease đủ dài, gia hạn lease khi xử lý lâu và luôn giữ idempotency ở phía nhận.

### Vì sao Outbox vẫn có thể gửi trùng?

Giả sử:

1. Worker gửi message thành công.
2. Broker đã nhận message.
3. Worker bị crash trước khi cập nhật trạng thái SENT.
4. Lease hết hạn và worker khác gửi lại cùng event.

Message có thể được giao hai lần. Vì vậy, Outbox thường cung cấp mô hình giao ít nhất một lần (at-least-once), không tự bảo đảm exactly-once cho tác động bên ngoài.

Dùng event_id làm idempotency key. Dịch vụ nhận cần có khả năng nhận diện và bỏ qua yêu cầu đã xử lý.

## 11. Idempotency: retry mà không lặp tác động nghiệp vụ

Một thao tác idempotent có thể được thực hiện nhiều lần mà kết quả nghiệp vụ tương đương thực hiện một lần.

Ví dụ:

- Tạo đơn với một request_id duy nhất.
- Gửi sự kiện với event_id duy nhất.
- Yêu cầu thanh toán kèm idempotency key được cổng thanh toán hỗ trợ.
- Consumer lưu event_id đã xử lý trong cùng transaction với thay đổi nghiệp vụ của nó.

### Bảng chống xử lý trùng ở consumer

~~~sql
CREATE TABLE processed_messages (
    event_id CHAR(36) NOT NULL PRIMARY KEY,
    processed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;
~~~

Consumer có thể xử lý message theo transaction:

~~~sql
START TRANSACTION;

INSERT INTO processed_messages (event_id)
VALUES ('f8a8a2d0-7f00-4c12-9f51-6eecf16d12a1');

-- Chỉ khi INSERT thành công, tiếp tục cập nhật dữ liệu nghiệp vụ.
UPDATE shipment_requests
SET status = 'READY'
WHERE order_id = 1001;

COMMIT;
~~~

Nếu cùng event được gửi lại, INSERT gặp duplicate primary key. Consumer bắt lỗi duplicate và bỏ qua sự kiện đã xử lý theo quy tắc ứng dụng.

Khi INSERT báo duplicate, consumer không chạy câu UPDATE nghiệp vụ tiếp theo trong nhánh đó. Nó kết thúc transaction hiện tại và xác nhận message đã được xử lý trước đó. Các lỗi khác duplicate phải được xử lý như lỗi thực sự, không được coi là message đã hoàn tất.

Cần bảo đảm việc ghi processed_messages và cập nhật nghiệp vụ nằm trong cùng transaction InnoDB. Nếu ghi dấu đã xử lý trước, rồi cập nhật nghiệp vụ thất bại mà hai việc không cùng transaction, lần retry có thể bị bỏ qua dù nghiệp vụ chưa hoàn tất.

Với API thanh toán hoặc dịch vụ ngoài, bảng deduplication trong database của ứng dụng không thể tự ngăn dịch vụ kia thu tiền lần hai. Phải truyền idempotency key mà dịch vụ đó hiểu và hỗ trợ.

## 12. Saga: phối hợp nghiệp vụ nhiều bước bằng hành động bù

Không phải dịch vụ nào cũng hỗ trợ XA hoặc idempotency đầy đủ. Với workflow dài gồm nhiều dịch vụ, có thể dùng Saga.

Saga chia nghiệp vụ thành các transaction cục bộ. Nếu một bước sau thất bại, hệ thống thực hiện hành động bù cho các bước đã hoàn tất.

Ví dụ đặt hàng:

| Bước | Hành động | Hành động bù |
|---|---|---|
| 1 | Tạo đơn ở trạng thái PENDING | Hủy đơn |
| 2 | Giữ hàng trong kho | Giải phóng hàng đã giữ |
| 3 | Thu tiền | Hoàn tiền |
| 4 | Tạo yêu cầu giao hàng | Hủy yêu cầu giao |

Saga không phải rollback nguyên tử. Hành động bù là một thao tác nghiệp vụ mới, có thể thất bại và cũng cần retry, idempotency, audit.

Ví dụ, hoàn tiền không xóa lịch sử khoản thanh toán đã thu. Nó tạo một giao dịch hoàn tiền riêng. Vì vậy, trạng thái workflow cần thể hiện rõ đang chờ, đã hoàn tất, đang bù hoặc cần can thiệp.

Saga phù hợp khi:

- Workflow kéo dài qua nhiều dịch vụ.
- Không thể giữ một transaction phân tán trong thời gian dài.
- Các hệ thống có API nghiệp vụ để bù.
- Chấp nhận trạng thái trung gian và eventual consistency.

## 13. XA và distributed transaction

XA là giao thức transaction phân tán cho phép nhiều tài nguyên transactional tham gia một global transaction dưới sự điều phối của Transaction Manager.

Trong mô hình này:

- **Resource Manager (RM):** tài nguyên có khả năng transaction, ví dụ một database.
- **Transaction Manager (TM):** điều phối commit hoặc rollback trên các resource manager.
- **Global transaction:** nghiệp vụ bao gồm nhiều nhánh transaction cục bộ.

MySQL hỗ trợ XA theo giao thức two-phase commit:

1. **Prepare:** các resource manager chuẩn bị và xác nhận có thể commit.
2. **Commit hoặc Rollback:** transaction manager quyết định hoàn tất hoặc hủy các nhánh.

Với MySQL, XA support bị giới hạn ở InnoDB. Bảng MyISAM không thể tham gia XA như một transactional resource.

Các lệnh XA ở mức khái niệm:

~~~sql
XA START 'xid-1001';

-- DML trên bảng InnoDB

XA END 'xid-1001';
XA PREPARE 'xid-1001';

-- Transaction Manager quyết định:
XA COMMIT 'xid-1001';
-- hoặc:
-- XA ROLLBACK 'xid-1001';
~~~

Không tự chạy các lệnh này như một transaction thông thường nếu không có Transaction Manager quản lý XID, trạng thái PREPARED, timeout và recovery.

### Khi nào XA phù hợp?

XA có thể phù hợp khi:

- Mọi resource tham gia đều hỗ trợ XA.
- Có Transaction Manager đáng tin cậy.
- Nghiệp vụ thực sự cần atomic commit qua nhiều transactional resource.
- Đội vận hành có quy trình xử lý transaction bị kẹt ở trạng thái PREPARED.

### Khi nào không nên dùng XA?

- API HTTP thông thường không cung cấp XA resource manager.
- Email hoặc SMS không thể tham gia XA theo cách mặc định.
- Filesystem hoặc object storage thường không phải XA resource.
- Bảng MyISAM không hỗ trợ transaction.
- Workflow dài và có nhiều bước nghiệp vụ thường phù hợp Saga/Outbox hơn.

XA có chi phí điều phối và vận hành. Transaction PREPARED có thể giữ tài nguyên cho đến khi được commit/rollback. Cần giám sát và recovery; không xem XA là cách thêm COMMIT vào cuối một đoạn code là xong.

## 14. Phân biệt các chiến lược phối hợp

| Tình huống | Cách tiếp cận phù hợp |
|---|---|
| Nhiều bảng InnoDB trong một database | Transaction cục bộ |
| Bảng nghiệp vụ InnoDB và bảng phụ MyISAM | Chuyển sang InnoDB hoặc tách ghi phụ qua outbox |
| Database và email/message broker | Transactional Outbox + retry + idempotency |
| Hai database hỗ trợ XA, cần atomic commit | XA với Transaction Manager |
| Workflow dài qua nhiều dịch vụ, có bước bù | Saga |
| API ngoài không có idempotency | Thiết kế reconciliation và cơ chế đối soát; không giả định retry là an toàn |
| Ghi file hoặc object storage | Lưu metadata/ý định trong DB, xử lý upload riêng, retry và dọn orphan |

Không có một mẫu duy nhất cho mọi hệ thống. Chọn theo khả năng transaction của từng tài nguyên, yêu cầu nhất quán, thời gian workflow và khả năng bù.

## 15. Kiểm tra và xử lý khi ROLLBACK không hoàn chỉnh

Khi ứng dụng báo transaction đã rollback nhưng dữ liệu vẫn xuất hiện, thực hiện theo thứ tự:

### Bước 1: xác minh engine của tất cả bảng

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
      'orders',
      'order_items',
      'audit_log'
  );
~~~

Không chỉ kiểm tra bảng chính. Một bảng audit, staging hoặc bảng lịch sử có thể đang dùng engine khác.

### Bước 2: đọc định nghĩa thực tế

~~~sql
SHOW CREATE TABLE orders;
SHOW CREATE TABLE audit_log;
~~~

Xác minh ENGINE và các ràng buộc.

### Bước 3: kiểm tra server hỗ trợ engine nào

~~~sql
SHOW ENGINES;
~~~

Nếu bảng dự kiến dùng InnoDB nhưng thực tế là MyISAM, kiểm tra cấu hình server, engine bị vô hiệu hóa và cảnh báo lúc tạo bảng.

### Bước 4: đọc Warning ngay sau ROLLBACK

~~~sql
ROLLBACK;
SHOW WARNINGS;
~~~

Tìm thông báo nontransactional changes couldn't be rolled back. Đừng chạy SELECT hoặc câu SQL thông thường trước khi đọc diagnostics nếu cần giữ thông báo của ROLLBACK.

### Bước 5: kiểm tra dữ liệu còn sót

~~~sql
SELECT * FROM orders WHERE order_id = 1001;
SELECT * FROM audit_log WHERE reference_id = 1001;
~~~

Xác định hàng nào đã được rollback, hàng nào vẫn tồn tại.

### Bước 6: đối soát theo khóa nghiệp vụ

Không xóa hàng còn sót một cách tự động nếu chưa xác định được nghiệp vụ. Có thể hàng nontransactional ghi một sự kiện hợp lệ hoặc một hành động ngoài database đã xảy ra.

Tạo báo cáo đối soát theo request ID, order ID hoặc idempotency key để xác định:

- Dữ liệu chính đã commit hay chưa.
- Dữ liệu phụ đã ghi hay chưa.
- API bên ngoài đã nhận yêu cầu hay chưa.
- Message đã được broker nhận hay chưa.
- Có thể retry hay cần hành động bù.

## 16. Bài thực hành: mô phỏng transaction và outbox

Bài lab này giúp phân biệt thay đổi không rollback được và cách lưu ý định gửi sự kiện.

### Phần A: rollback bảng MyISAM

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_external_workflow_lab;
USE mysql_external_workflow_lab;

CREATE TABLE business_records (
    record_id INT NOT NULL PRIMARY KEY,
    description VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE legacy_events (
    event_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    record_id INT NOT NULL,
    event_name VARCHAR(50) NOT NULL
) ENGINE=MyISAM;

START TRANSACTION;

INSERT INTO business_records (record_id, description)
VALUES (1, 'Record one');

INSERT INTO legacy_events (record_id, event_name)
VALUES (1, 'RECORD_CREATED');

ROLLBACK;
SHOW WARNINGS;

SELECT * FROM business_records;
SELECT * FROM legacy_events;
~~~

Ghi lại sự khác nhau giữa hai kết quả và giải thích vì sao autocommit không quyết định khả năng rollback của MyISAM.

### Phần B: lưu sự kiện trong outbox InnoDB

~~~sql
CREATE TABLE outbox_events (
    event_id CHAR(36) NOT NULL PRIMARY KEY,
    aggregate_id INT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;

START TRANSACTION;

INSERT INTO business_records (record_id, description)
VALUES (2, 'Record two');

INSERT INTO outbox_events
    (event_id, aggregate_id, event_type, payload)
VALUES
    (
        UUID(),
        2,
        'RecordCreated',
        JSON_OBJECT('recordId', 2, 'description', 'Record two')
    );

COMMIT;

SELECT * FROM business_records WHERE record_id = 2;
SELECT * FROM outbox_events WHERE aggregate_id = 2;
~~~

Cả bản ghi nghiệp vụ và ý định phát sự kiện cùng tồn tại sau COMMIT.

### Phần C: chứng minh cả hai cùng rollback

~~~sql
START TRANSACTION;

INSERT INTO business_records (record_id, description)
VALUES (3, 'Record three');

INSERT INTO outbox_events
    (event_id, aggregate_id, event_type, payload)
VALUES
    (
        UUID(),
        3,
        'RecordCreated',
        JSON_OBJECT('recordId', 3, 'description', 'Record three')
    );

ROLLBACK;

SELECT * FROM business_records WHERE record_id = 3;
SELECT * FROM outbox_events WHERE aggregate_id = 3;
~~~

Cả hai truy vấn không trả hàng vì hai bảng cùng dùng InnoDB.

### Phần D: mô phỏng worker và idempotency

Tạo bảng ghi nhận sự kiện đã xử lý:

~~~sql
CREATE TABLE processed_events (
    event_id CHAR(36) NOT NULL PRIMARY KEY,
    processed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;
~~~

Chọn một event từ outbox:

~~~sql
SELECT
    event_id,
    event_type,
    payload
FROM outbox_events
WHERE status = 'PENDING'
ORDER BY created_at
LIMIT 10;
~~~

Trong ứng dụng, với từng event:

1. Dùng event_id làm idempotency key.
2. Gọi dịch vụ nhận sự kiện.
3. Nếu dịch vụ xác nhận thành công, cập nhật trạng thái SENT.
4. Nếu timeout hoặc lỗi tạm thời, lên lịch retry.
5. Nếu gửi lại cùng event_id, phía nhận phải nhận diện và bỏ qua tác động đã xử lý.

Mô phỏng consumer lưu dấu đã xử lý trong transaction:

~~~sql
START TRANSACTION;

INSERT INTO processed_events (event_id)
VALUES ('f8a8a2d0-7f00-4c12-9f51-6eecf16d12a1');

COMMIT;
~~~

Thử INSERT lại cùng event_id. Khóa chính ngăn tạo bản ghi xử lý trùng. Trong ứng dụng, bắt lỗi duplicate theo đúng loại lỗi và coi đó là sự kiện đã xử lý; không bỏ qua các lỗi database khác.

### Dọn dẹp

~~~sql
DROP DATABASE mysql_external_workflow_lab;
~~~

Chỉ chạy trên database lab vừa tạo.

## 17. Checklist thiết kế transaction có nhiều tài nguyên

- [ ] Đã xác minh ENGINE của mọi bảng được DML trong transaction.
- [ ] Các bảng cần atomic rollback đều dùng engine transactional, thường là InnoDB.
- [ ] Không dựa vào ROLLBACK để hoàn tác MyISAM hoặc engine nontransactional.
- [ ] Đã kiểm tra Warning sau rollback khi có bảng nontransactional.
- [ ] Không để DDL gây implicit commit xen giữa transaction nghiệp vụ.
- [ ] Các thao tác transaction chạy trên cùng database connection.
- [ ] Không giữ transaction mở trong lúc chờ HTTP hoặc message broker nếu không cần thiết.
- [ ] Đã xác định thứ tự lỗi có thể xảy ra giữa COMMIT và external call.
- [ ] Có outbox hoặc cơ chế lưu ý định gửi bền vững khi cần phát sự kiện sau commit.
- [ ] Outbox và dữ liệu nghiệp vụ cùng dùng transaction-safe engine.
- [ ] Worker có retry, backoff, lease/timeout và trạng thái lỗi cuối.
- [ ] Sự kiện có ID ổn định để làm idempotency key.
- [ ] Consumer hoặc API bên ngoài có cơ chế chống xử lý trùng.
- [ ] Có quy trình đối soát và xử lý sự kiện FAILED.
- [ ] Chỉ dùng XA khi mọi resource thực sự hỗ trợ XA và có Transaction Manager.
- [ ] Dùng Saga khi workflow dài cần hành động bù thay vì một transaction phân tán kéo dài.

## 18. Nguyên tắc cần ghi nhớ

1. START TRANSACTION không biến bảng nontransactional thành transactional.
2. Thay đổi trên MyISAM được ghi ngay và không thể hoàn tác bằng ROLLBACK.
3. Khi rollback transaction trộn InnoDB và MyISAM, thay đổi InnoDB được hoàn tác còn thay đổi MyISAM vẫn tồn tại.
4. Cảnh báo ER_WARNING_NOT_COMPLETE_ROLLBACK là tín hiệu phải điều tra dữ liệu còn sót.
5. Dùng một transaction-safe storage engine cho các bảng cần atomicity.
6. DDL như CREATE, ALTER, DROP và TRUNCATE có thể gây implicit commit.
7. ROLLBACK không thể hoàn tác email, HTTP request, message, file hoặc thanh toán đã xảy ra ở hệ thống khác.
8. Gọi external service trước COMMIT có nguy cơ tạo tác động ngoài dù database rollback.
9. Gọi external service sau COMMIT có nguy cơ database đã commit nhưng sự kiện chưa được gửi.
10. Transactional Outbox lưu dữ liệu nghiệp vụ và ý định phát sự kiện trong cùng transaction.
11. Outbox thường giao ít nhất một lần; cần idempotency để xử lý message trùng.
12. Saga dùng hành động bù cho workflow nhiều bước; đó không phải rollback nguyên tử.
13. XA cần các resource manager hỗ trợ XA và một Transaction Manager; MySQL XA chỉ hỗ trợ InnoDB.
14. Thiết kế quy trình đối soát và recovery là một phần của tính nhất quán hệ thống.

## Tài liệu tham khảo chính thức

Các hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual** tại ngày **19-11-2026**:

1. [START TRANSACTION, COMMIT, and ROLLBACK Statements](https://dev.mysql.com/doc/refman/9.7/en/commit.html): transaction cục bộ, autocommit, giới hạn khi trộn transactional và nontransactional tables, warning rollback không hoàn chỉnh và binary log.
2. [Rollback Failure for Nontransactional Tables](https://dev.mysql.com/doc/refman/9.7/en/nontransactional-tables.html): thông báo rollback không hoàn chỉnh và cách kiểm tra storage engine.
3. [Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/9.7/en/implicit-commit.html): DDL, câu lệnh quản trị và các trường hợp implicit commit.
4. [XA Transactions](https://dev.mysql.com/doc/refman/9.7/en/xa.html): giao dịch phân tán, Resource Manager và Transaction Manager.
5. [Restrictions on XA Transactions](https://dev.mysql.com/doc/refman/9.7/en/xa-restrictions.html): giới hạn XA và hỗ trợ InnoDB.
6. [SHOW ENGINES Statement](https://dev.mysql.com/doc/refman/9.7/en/show-engines.html): kiểm tra storage engine server hỗ trợ.
7. [INFORMATION_SCHEMA TABLES](https://dev.mysql.com/doc/refman/9.7/en/information-schema-tables-table.html): kiểm tra engine của bảng qua metadata.

