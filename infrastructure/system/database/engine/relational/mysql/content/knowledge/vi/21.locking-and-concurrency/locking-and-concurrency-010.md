# Deadlock, thứ tự lấy khóa và cách InnoDB chọn giao dịch bị hủy

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Khi nhiều transaction cùng đọc và ghi dữ liệu, InnoDB dùng khóa để bảo vệ các thay đổi. Nếu các transaction giữ khóa mà transaction khác cần, chúng có thể phải chờ. Khi quan hệ chờ tạo thành một vòng khép kín, hệ thống rơi vào **deadlock**.

InnoDB phát hiện deadlock và chọn một transaction làm nạn nhân để rollback, giải phóng khóa cho transaction còn lại tiếp tục. Ứng dụng phải nhận diện lỗi, rollback hoặc làm sạch trạng thái transaction, rồi thử lại **toàn bộ giao dịch nghiệp vụ** khi phù hợp. Thiết kế thứ tự lấy khóa nhất quán, rút ngắn transaction và tạo index phù hợp giúp giảm khả năng deadlock, nhưng không thể bảo đảm loại bỏ hoàn toàn deadlock trong hệ thống đồng thời.

## 1. Deadlock là gì?

Deadlock (bế tắc) xảy ra khi hai hoặc nhiều transaction tạo thành một chu trình chờ khóa: mỗi transaction đang giữ ít nhất một khóa mà transaction khác cần, đồng thời chờ một khóa do transaction khác đang giữ.

Ví dụ với hai tài khoản:

- Transaction A khóa hàng tài khoản 1 và cần khóa tài khoản 2.
- Transaction B khóa hàng tài khoản 2 và cần khóa tài khoản 1.
- A phải chờ B nhả khóa tài khoản 2.
- B phải chờ A nhả khóa tài khoản 1.

Không transaction nào có thể tiếp tục nếu không có một transaction bị hủy. Đây là deadlock, khác với tình huống một transaction chỉ phải chờ một transaction khác kết thúc.

### 1.1. Wait-for graph

Có thể mô hình hóa các transaction bằng đồ thị chờ:

- Mỗi nút là một transaction.
- Cạnh A → B nghĩa là A đang chờ khóa do B giữ.
- Nếu đồ thị có chu trình, tồn tại deadlock.

Ví dụ:

~~~text
Transaction A giữ khóa hàng 1, chờ khóa hàng 2
Transaction B giữ khóa hàng 2, chờ khóa hàng 1

A  ───── waits for ─────>  B
^                         |
|                         |
└──────── waits for ──────┘
~~~

Deadlock không nhất thiết chỉ có hai transaction. Chu trình có thể gồm ba hoặc nhiều transaction, nhiều bảng, nhiều index và nhiều loại khóa.

### 1.2. Chờ khóa không phải lúc nào cũng là deadlock

Nếu A giữ khóa và B chỉ chờ A, nhưng A không chờ một khóa do B hoặc chuỗi transaction liên quan giữ, đồ thị không có chu trình. B chỉ đang bị block. Khi A commit hoặc rollback, B có thể tiếp tục.

| Tình huống | Đặc điểm | Kết quả thường gặp |
|---|---|---|
| Lock wait thông thường | Có transaction chờ nhưng không có chu trình | Chờ đến khi khóa được nhả hoặc hết thời gian chờ |
| Deadlock | Có chu trình chờ khóa | InnoDB phát hiện và rollback một transaction làm nạn nhân |
| Lock wait timeout | Một lần chờ vượt thời gian cấu hình | Câu lệnh đang chờ thường bị rollback theo mặc định; transaction có thể vẫn mở |

Không nên kết luận có deadlock chỉ vì ứng dụng nhận thấy truy vấn chậm hoặc đang chờ khóa.

## 2. Tạo deadlock với hai session

Ví dụ sau dùng InnoDB và hai hàng trong cùng bảng. Mở hai kết nối MySQL độc lập, gọi là Session A và Session B.

### 2.1. Chuẩn bị dữ liệu lab

Chạy một lần trước khi mở hai session:

~~~sql
CREATE TABLE lab_accounts (
    account_id INT NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

INSERT INTO lab_accounts (account_id, balance)
VALUES
    (1, 1000.00),
    (2, 1000.00);
~~~

### 2.2. Session A khóa hàng thứ nhất

Trong Session A:

~~~sql
START TRANSACTION;

UPDATE lab_accounts
SET balance = balance - 10.00
WHERE account_id = 1;
~~~

Session A giữ khóa cần thiết trên hàng account_id = 1 cho đến khi transaction kết thúc.

### 2.3. Session B khóa hàng thứ hai

Trong Session B:

~~~sql
START TRANSACTION;

UPDATE lab_accounts
SET balance = balance - 20.00
WHERE account_id = 2;
~~~

Session B giữ khóa trên hàng account_id = 2.

### 2.4. Session B chờ khóa hàng thứ nhất

Vẫn trong Session B:

~~~sql
UPDATE lab_accounts
SET balance = balance + 20.00
WHERE account_id = 1;
~~~

Câu lệnh này bị block vì Session A đang giữ khóa hàng 1. Session B vẫn giữ khóa hàng 2 trong khi chờ.

### 2.5. Session A yêu cầu khóa hàng thứ hai

Trong Session A:

~~~sql
UPDATE lab_accounts
SET balance = balance + 10.00
WHERE account_id = 2;
~~~

Session A cần khóa hàng 2 do Session B giữ. Lúc này:

- A giữ hàng 1 và chờ hàng 2.
- B giữ hàng 2 và chờ hàng 1.

InnoDB phát hiện chu trình deadlock và rollback một transaction. Session được chọn làm nạn nhân nhận lỗi deadlock, thường là error 1213 với SQLSTATE 40001. Transaction còn lại có thể tiếp tục sau khi khóa của transaction nạn nhân được giải phóng.

Không giả định Session A hay Session B luôn là nạn nhân. Kết quả phụ thuộc trạng thái và trọng lượng của các transaction tại thời điểm phát hiện.

### 2.6. Kiểm tra dữ liệu sau deadlock

Trong session còn sống, kiểm tra:

~~~sql
SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;
~~~

Transaction bị chọn làm nạn nhân đã bị rollback toàn bộ. Transaction còn lại vẫn có thể đang mở; hãy kiểm tra kết quả, hoàn tất hoặc rollback nó theo mục tiêu của bài lab.

Kết thúc transaction còn lại nếu vẫn mở:

~~~sql
ROLLBACK;
~~~

Sau đó kiểm tra dữ liệu trở về giá trị ban đầu:

~~~sql
SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;
~~~

**Lưu ý khi thực hành:** cần gửi các câu lệnh đúng thứ tự giữa hai session. Sau khi Session B bị block ở bước 2.4, phải chạy bước 2.5 trên Session A để tạo chu trình. Nếu chạy tuần tự hết một session trước khi mở session kia, deadlock sẽ không xuất hiện.

## 3. Cách InnoDB phát hiện deadlock

InnoDB theo dõi các quan hệ chờ khóa. Khi deadlock detection được bật, engine kiểm tra chu trình trong wait-for graph. Khi phát hiện deadlock, InnoDB chọn một transaction để rollback nhằm phá chu trình và giải phóng khóa.

Biến innodb_deadlock_detect điều khiển chức năng phát hiện:

~~~sql
SELECT @@GLOBAL.innodb_deadlock_detect;
~~~

Trong cấu hình thông thường, deadlock detection được bật. Khi bật, InnoDB có thể phát hiện deadlock ngay thay vì chờ hết innodb_lock_wait_timeout.

### 3.1. Khi tắt deadlock detection

Trong hệ thống có tranh chấp khóa cực lớn, việc kiểm tra deadlock có thể tiêu tốn CPU. MySQL cho phép DBA cân nhắc tắt innodb_deadlock_detect trong một số tình huống đặc biệt, nhưng khi tắt, deadlock có thể không được phát hiện ngay và các transaction phải chờ timeout để được giải phóng.

Đây là quyết định vận hành cần đo đạc và thử nghiệm tải. Không tắt deadlock detection chỉ để che lỗi ứng dụng hoặc thay thế việc sửa thứ tự lấy khóa.

### 3.2. Deadlock được phát hiện khác timeout

- Deadlock detection tìm được chu trình và chọn victim để rollback toàn transaction.
- Lock wait timeout chỉ cho biết một lần chờ đã vượt giới hạn; nó không chứng minh có chu trình.
- Nếu deadlock detection bị tắt, một chu trình có thể tồn tại cho đến khi một transaction gặp timeout.

innodb_lock_wait_timeout điều khiển thời gian chờ khóa InnoDB; nó không phải cơ chế ưu tiên chọn transaction nạn nhân khi deadlock đã được phát hiện.

## 4. InnoDB chọn transaction nạn nhân như thế nào?

Khi phát hiện deadlock, InnoDB không đơn giản luôn hủy transaction đến sau, transaction trẻ nhất hay transaction giữ khóa đầu tiên. Engine cố gắng chọn transaction có **trọng lượng nhỏ hơn** để rollback, nhằm giảm lượng công việc phải làm lại.

Trọng lượng transaction có liên quan đến lượng dữ liệu transaction đã thay đổi và khóa, chẳng hạn số hàng được insert, update, delete hoặc đang bị khóa. Đây là quyết định nội bộ của InnoDB; ứng dụng không nên phụ thuộc vào một quy tắc chọn victim tuyệt đối theo thời gian bắt đầu hoặc thứ tự câu lệnh.

### 4.1. Vì sao chọn transaction nhỏ hơn?

Giả sử:

- Transaction A đã cập nhật hàng trăm bản ghi và đang giữ nhiều khóa.
- Transaction B mới cập nhật một hàng.
- Hai transaction tạo thành chu trình chờ.

Rollback B thường đòi hỏi ít công việc phục hồi hơn rollback A. InnoDB vì thế có xu hướng chọn transaction nhẹ hơn. Tuy nhiên, đây là xu hướng dựa trên trọng lượng, không phải lời hứa rằng transaction ít câu SQL nhất hoặc bắt đầu muộn nhất chắc chắn bị hủy.

### 4.2. Quan sát transaction đang hoạt động

Có thể xem các transaction InnoDB:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_weight,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx;
~~~

Các trường này giúp xác định transaction đang chạy, thời điểm bắt đầu, trọng lượng transaction, số hàng bị khóa hoặc thay đổi và câu SQL hiện tại nếu có. Bản ghi chỉ phản ánh trạng thái đang tồn tại; transaction nạn nhân có thể đã biến mất sau khi deadlock được giải quyết.

Không dùng trx_rows_modified đơn lẻ để dự đoán chính xác victim. Hãy coi đây là dữ liệu hỗ trợ điều tra.

### 4.3. Ứng dụng phải chấp nhận bất kỳ transaction nào có thể bị hủy

Transaction đang xử lý nghiệp vụ quan trọng vẫn có thể là victim. Không giả định transaction "quan trọng hơn" hoặc transaction bắt đầu trước sẽ luôn được giữ lại. Hãy thiết kế cả hai phía có thể retry an toàn và không để side effect bên ngoài xảy ra trước khi biết kết quả commit.

## 5. Nguyên nhân deadlock thường gặp

### 5.1. Lấy khóa theo thứ tự ngược nhau

Đây là mẫu phổ biến:

~~~sql
-- Transaction A
UPDATE accounts SET balance = balance - 10 WHERE account_id = 1;
UPDATE accounts SET balance = balance + 10 WHERE account_id = 2;

-- Transaction B
UPDATE accounts SET balance = balance - 20 WHERE account_id = 2;
UPDATE accounts SET balance = balance + 20 WHERE account_id = 1;
~~~

A lấy khóa 1 rồi 2; B lấy khóa 2 rồi 1. Khi hai transaction xen kẽ, chúng có thể tạo chu trình.

### 5.2. Cùng thứ tự bảng nhưng khác thứ tự hàng

Deadlock không chỉ xảy ra khi truy cập nhiều bảng. Hai transaction có thể cập nhật cùng một bảng nhưng theo thứ tự hàng khác nhau, như ví dụ hai tài khoản ở trên.

### 5.3. Range scan và next-key lock

Ở mức cô lập REPEATABLE READ mặc định của InnoDB, một số locking read, UPDATE hoặc DELETE trên phạm vi index có thể lấy next-key lock, kết hợp record lock và gap lock để bảo vệ khoảng dữ liệu.

Các loại khóa thường gặp trong điều tra:

- Record lock khóa một bản ghi index cụ thể.
- Gap lock khóa khoảng nằm giữa các bản ghi index, ngăn thao tác chèn vào khoảng đó trong những trường hợp áp dụng.
- Next-key lock kết hợp record lock với khoảng index liền trước record.
- Insert intention lock thể hiện ý định chèn một bản ghi vào một khoảng index; nó có thể phải chờ các khóa đang bảo vệ khoảng đó.

Đây là các khái niệm về khóa index của InnoDB. Một truy vấn range có thể khóa nhiều khoảng hơn người đọc suy ra từ danh sách hàng được trả về, tùy index, isolation level và execution plan.

Hai transaction cập nhật các phạm vi chồng lấn hoặc chèn vào khoảng đang bị khóa có thể xung đột dù chúng không nhắm tới cùng một giá trị khóa chính rõ ràng.

Ví dụ:

~~~sql
START TRANSACTION;

SELECT *
FROM orders
WHERE order_id BETWEEN 100 AND 200
FOR UPDATE;
~~~

Truy vấn này có thể khóa các bản ghi và khoảng index liên quan theo isolation level, index và execution plan. Cần đọc lock data thực tế thay vì giả định chỉ những hàng được trả về mới có thể gây xung đột.

### 5.4. Index phụ và nhiều đường truy cập

InnoDB quản lý khóa trên index record và bản ghi clustered index liên quan. Một UPDATE có thể cần thay đổi nhiều index nếu sửa cột được đánh index. Hai transaction cập nhật các hàng theo thứ tự khác nhau có thể xung đột trên index phụ dù điều kiện nghiệp vụ nhìn có vẻ độc lập.

Thiếu index cũng có thể làm truy vấn quét nhiều record hơn cần thiết và giữ nhiều khóa lâu hơn, tăng xác suất giao nhau với transaction khác.

### 5.5. Foreign key và kiểm tra unique

Khi insert hoặc update dữ liệu có foreign key, InnoDB cần kiểm tra bản ghi được tham chiếu. Khi thêm giá trị vào unique index, engine cần kiểm tra xung đột khóa. Các bước kiểm tra này cũng có thể cần khóa và tạo thêm quan hệ chờ giữa transaction.

Vì vậy, một deadlock có thể xuất hiện trong INSERT hoặc UPDATE dù ứng dụng không viết câu SELECT ... FOR UPDATE tường minh.

### 5.6. Transaction dài

Transaction giữ khóa càng lâu, cửa sổ xung đột càng lớn. Những nguyên nhân kéo dài transaction gồm:

- Đọc hoặc ghi quá nhiều hàng trong một lần.
- Chờ người dùng hoặc dịch vụ mạng trong khi transaction còn mở.
- Chạy truy vấn chậm do thiếu index.
- Thực hiện nhiều bước không liên quan trong cùng transaction.
- Quên COMMIT hoặc ROLLBACK trước khi trả connection về pool.

Rút ngắn transaction giúp giảm thời gian giữ khóa và xác suất tạo chu trình.

## 6. Nguyên tắc thứ tự lấy khóa nhất quán

Giải pháp quan trọng để giảm deadlock là thống nhất thứ tự lấy khóa ở mọi luồng nghiệp vụ có thể chạm cùng dữ liệu.

### 6.1. Thứ tự theo khóa chính tăng dần

Nếu một transaction cần cập nhật account 1 và account 2, mọi luồng nên khóa account 1 trước rồi account 2, bất kể tài khoản nào là bên gửi hay bên nhận.

Một cách thể hiện rõ ràng trong ứng dụng là lấy khóa theo từng ID đã sắp tăng dần:

~~~sql
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

SELECT account_id, balance
FROM accounts
WHERE account_id = 2
FOR UPDATE;

-- Thực hiện các cập nhật sau khi đã khóa theo thứ tự thống nhất.
COMMIT;
~~~

Nếu transaction khác cũng cần hai tài khoản này, nó phải tuân theo cùng thứ tự. Khi A đã khóa account 1, B sẽ chờ ngay tại account 1 và chưa giữ account 2; vì vậy mẫu deadlock do đảo thứ tự này không hình thành.

Với danh sách nhiều ID, ứng dụng có thể sắp xếp ID trước khi lấy khóa. Nếu dùng một câu SELECT WHERE id IN (...) ORDER BY id FOR UPDATE, hãy kiểm tra access path để bảo đảm thứ tự truy cập thực tế phù hợp; không giả định thứ tự literal trong IN quyết định thứ tự khóa.

### 6.2. Thống nhất thứ tự giữa các bảng

Nếu một quy trình cập nhật cả customers, orders và inventory, các luồng có thể xung đột cần lấy khóa theo cùng thứ tự bảng và cùng thứ tự khóa trong mỗi bảng.

Ví dụ quy ước:

1. Khóa hàng customer.
2. Khóa hàng order.
3. Khóa hàng inventory theo product_id tăng dần.

Mọi đường code cần tuân thủ quy ước đó. Nếu một luồng khóa inventory trước customer còn luồng khác khóa customer trước inventory, deadlock vẫn có thể xảy ra.

### 6.3. Khóa hàng theo cùng một tiêu chí nghiệp vụ

Không nên để thứ tự khóa phụ thuộc vào dữ liệu đầu vào tùy tiện. Ví dụ chuyển tiền từ A sang B và chuyển tiền từ B sang A phải cùng khóa tài khoản có ID nhỏ hơn trước. Thứ tự khóa dựa trên vai trò "người gửi" và "người nhận" sẽ đảo chiều giữa hai giao dịch.

### 6.4. Thứ tự khóa giảm rủi ro, không loại bỏ mọi deadlock

Thứ tự nhất quán giải quyết nhiều deadlock do các luồng khóa cùng tài nguyên theo hướng ngược nhau. Tuy nhiên, deadlock vẫn có thể đến từ:

- Khóa record và gap/next-key lock trên các range giao nhau.
- Unique index hoặc foreign key.
- Nhiều index bị cập nhật trong cùng statement.
- Trigger hoặc cascade phát sinh thêm thao tác.
- Các câu lệnh khác nhau có execution plan và thứ tự truy cập khác nhau.

Do đó, vẫn cần bắt lỗi 1213 và retry transaction an toàn.

## 7. Index và phạm vi khóa

Index không chỉ ảnh hưởng tốc độ truy vấn; nó còn ảnh hưởng số record InnoDB phải duyệt và khóa.

### 7.1. Điều kiện có index phù hợp

Giả sử:

~~~sql
UPDATE orders
SET status = 'PROCESSING'
WHERE customer_id = 100
  AND order_id = 500;
~~~

Nếu có index phù hợp, InnoDB có thể tìm hàng đích trực tiếp thay vì quét phạm vi lớn. Khóa thường tập trung hơn vào các record liên quan.

~~~sql
CREATE INDEX ix_orders_customer_order
ON orders (customer_id, order_id);
~~~

Đây chỉ là ví dụ về thứ tự cột cần đánh giá; nếu order_id đã là primary key và điều kiện đã chọn được một hàng qua khóa chính, index mới có thể không cần thiết. Kiểm tra index hiện tại và EXPLAIN trước khi tạo.

### 7.2. Range scan và gap lock

Ở REPEATABLE READ, range locking có thể lấy next-key lock trên khoảng index. Nếu truy vấn không có index phù hợp, phạm vi scan có thể rộng và khóa nhiều record hơn dự kiến.

Index phù hợp có thể thu hẹp phạm vi truy cập và giảm thời gian giữ khóa. Tuy nhiên, index mới cũng làm tăng chi phí ghi và có thể thêm index record cần duy trì. Hãy thiết kế index dựa trên truy vấn thực tế.

### 7.3. Dùng EXPLAIN để kiểm tra đường truy cập

~~~sql
EXPLAIN
UPDATE orders
SET status = 'PROCESSING'
WHERE customer_id = 100
  AND order_id = 500;
~~~

Kiểm tra:

- key: index được chọn.
- type hoặc access method: truy cập bằng const, eq_ref, ref, range hay ALL.
- rows: số hàng ước lượng phải đọc.
- Điều kiện nào được dùng để tìm record và điều kiện nào chỉ được lọc sau khi đọc.

Một plan quét toàn bảng có thể làm tăng lượng record cần kiểm tra và khả năng giữ khóa trong thao tác ghi. Tuy vậy, không phải mọi access type ALL đều sai; phải đánh giá kích thước bảng và số hàng thực tế.

## 8. Chẩn đoán deadlock

Khi ứng dụng nhận lỗi deadlock, cần lấy bằng chứng từ MySQL để tìm hai transaction, các khóa đang giữ và câu lệnh tạo chu trình.

### 8.1. SHOW ENGINE INNODB STATUS

Trong MySQL client:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Trong công cụ GUI không hỗ trợ dấu \G, dùng:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Tìm phần LATEST DETECTED DEADLOCK. Phần này thường mô tả:

- Transaction tham gia deadlock.
- Trạng thái và câu lệnh đang chạy.
- Lock mà mỗi transaction đang giữ.
- Lock mà mỗi transaction đang chờ.
- Record hoặc index liên quan.
- Transaction được chọn làm victim.

Phần latest chỉ giữ thông tin deadlock gần nhất được ghi nhận, nên một deadlock mới có thể thay thế bằng chứng cũ.

### 8.2. Ghi mọi deadlock vào error log

Biến innodb_print_all_deadlocks cho phép ghi chi tiết các deadlock vào MySQL error log:

~~~sql
SELECT @@GLOBAL.innodb_print_all_deadlocks;
~~~

DBA có thể bật trong lúc điều tra:

~~~sql
SET GLOBAL innodb_print_all_deadlocks = ON;
~~~

Thay đổi GLOBAL cần quyền phù hợp và có phạm vi vận hành toàn server. Thiết lập bằng SET GLOBAL thường không tự tồn tại sau khi server restart; nếu cần lâu dài, DBA phải cấu hình theo chính sách triển khai. Error log có thể chứa SQL và thông tin dữ liệu nhạy cảm, cần được bảo vệ theo quyền truy cập log.

### 8.3. Xem lock wait hiện tại bằng Performance Schema

Trên MySQL 8.0, performance_schema.data_locks và performance_schema.data_lock_waits cho phép quan sát lock và quan hệ chờ đang tồn tại:

~~~sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
    r.OBJECT_SCHEMA,
    r.OBJECT_NAME,
    r.INDEX_NAME,
    r.LOCK_TYPE,
    r.LOCK_MODE AS waiting_lock_mode,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
    b.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

Truy vấn này cho thấy các lock wait đang hoạt động tại thời điểm chạy. Deadlock thường được giải quyết rất nhanh sau khi InnoDB chọn victim, vì vậy truy vấn có thể không còn hàng để hiển thị sau khi lỗi đã xảy ra. Muốn điều tra deadlock đã kết thúc, dùng LATEST DETECTED DEADLOCK hoặc error log.

### 8.4. Ghép với thông tin transaction

Có thể xem transaction đang hoạt động:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx;
~~~

Ghép thread ID với connection/process list để tìm session thuộc ứng dụng hoặc worker nào. Cần quyền đọc Performance Schema và Information Schema phù hợp.

### 8.5. Quy trình đọc một deadlock report

1. Tìm hai hoặc nhiều transaction tham gia.
2. Xác định mỗi transaction đã chạy câu SQL nào.
3. Đọc lock đang chờ và lock đang giữ của từng transaction.
4. Xác định bảng, index, record hoặc khoảng index liên quan.
5. Dựng lại thứ tự lấy khóa của từng transaction.
6. Tìm điểm mà thứ tự khóa bị đảo hoặc phạm vi khóa giao nhau.
7. Kiểm tra index và execution plan của câu lệnh.
8. Sửa thứ tự truy cập, phạm vi scan hoặc thời lượng transaction.
9. Theo dõi lại deadlock rate sau khi triển khai.

Không chỉ nhìn câu lệnh nhận lỗi 1213. Câu lệnh đó là nơi engine thông báo victim; nguyên nhân có thể nằm ở chuỗi thao tác trước đó của cả hai transaction.

## 9. Phân biệt lỗi deadlock và lock wait timeout

| Thuộc tính | Deadlock | Lock wait timeout |
|---|---|---|
| Error code thường gặp | 1213 | 1205 |
| SQLSTATE thường gặp | 40001 | HY000 |
| Điều kiện | Có chu trình chờ khóa | Một lần chờ vượt thời gian cho phép |
| Hành vi mặc định của InnoDB | Rollback toàn transaction nạn nhân | Rollback statement đang chờ; transaction thường vẫn mở |
| Cách xử lý | Retry toàn bộ transaction nếu an toàn | Đánh giá transaction còn mở; thường rollback toàn bộ nghiệp vụ rồi mới retry |

Biến innodb_rollback_on_timeout có thể làm lock wait timeout rollback toàn transaction:

~~~sql
SELECT @@GLOBAL.innodb_rollback_on_timeout;
~~~

Không đổi biến này chỉ để che vấn đề. Ứng dụng cần xử lý rõ cả hai trường hợp và không giả định mọi lỗi 1205 có cùng trạng thái transaction trong mọi cấu hình.

## 10. Retry transaction sau deadlock

Deadlock là lỗi có thể phục hồi trong nhiều hệ thống giao dịch. Sau khi InnoDB rollback victim, ứng dụng có thể chạy lại nghiệp vụ trong transaction mới.

### 10.1. Retry toàn bộ transaction

Quy trình khuyến nghị:

1. Nhận lỗi 1213 / SQLSTATE 40001.
2. Kết thúc hoặc làm sạch trạng thái transaction/connection theo driver.
3. Chờ một khoảng ngắn có jitter để giảm khả năng các transaction va chạm lại cùng lúc.
4. Bắt đầu transaction mới.
5. Chạy lại tất cả bước đọc, kiểm tra và ghi của nghiệp vụ.
6. Commit nếu toàn bộ bước thành công.
7. Giới hạn số lần retry; nếu vẫn lỗi, trả lỗi phù hợp cho tầng gọi.

Không retry riêng câu SQL cuối bị lỗi. InnoDB đã rollback toàn bộ transaction nạn nhân, nên những thay đổi trước đó cũng không còn.

### 10.2. Pseudocode

~~~text
for attempt in 1..MAX_RETRIES:
    begin transaction
    try:
        read and lock required rows
        validate business conditions
        execute all required writes
        commit
        return success
    catch error:
        if transaction is still active:
            rollback

        if error is deadlock and attempt < MAX_RETRIES:
            wait with bounded backoff and jitter
            continue

        raise error
~~~

Driver và framework có thể tự rollback hoặc đánh dấu transaction không còn hợp lệ sau deadlock. Vì vậy, nhánh cleanup cần tuân theo API của driver; không tiếp tục dùng transaction cũ.

### 10.3. Retry phải idempotent

Một lần retry có thể lặp lại thao tác đã tạo side effect bên ngoài MySQL nếu ứng dụng gửi email, gọi API hoặc ghi file trước khi transaction kết thúc. Hãy:

- Giữ side effect ngoài database sau khi commit nếu có thể.
- Dùng idempotency key hoặc mã nghiệp vụ duy nhất.
- Ghi sự kiện vào transactional outbox trong cùng transaction, rồi gửi qua worker sau commit.
- Không retry vô hạn hoặc retry mọi loại lỗi.

Lỗi constraint như duplicate key thường không tự hết khi chạy lại; cần xử lý theo ý nghĩa nghiệp vụ thay vì xem như deadlock.

## 11. Các cách giảm deadlock

### 11.1. Lấy khóa theo thứ tự thống nhất

Chuẩn hóa thứ tự bảng, khóa chính và ID trong tất cả luồng có thể cập nhật cùng tài nguyên. Đây là biện pháp trực tiếp nhất cho deadlock do thứ tự khóa ngược.

### 11.2. Giữ transaction ngắn

Chỉ đưa các thao tác cần atomicity vào transaction. Không gọi HTTP, không chờ người dùng, không chạy báo cáo dài và không thực hiện công việc không liên quan khi vẫn đang giữ khóa.

### 11.3. Tạo index đúng cho điều kiện khóa

Index phù hợp giúp InnoDB tìm đúng record nhanh hơn, giảm số record phải quét và có thể giảm phạm vi khóa. Dùng EXPLAIN để kiểm chứng; tránh index thừa làm tăng chi phí ghi và số index cần duy trì.

### 11.4. Cập nhật ít hàng hơn

Chia batch lớn thành batch nhỏ nếu nghiệp vụ cho phép. Tuy nhiên, chia batch làm thay đổi ranh giới atomicity: nếu toàn bộ batch phải thành công hoặc thất bại cùng nhau, không được tự chia thành nhiều transaction độc lập.

### 11.5. Khóa sớm khi đã biết tài nguyên cần thiết

Nếu cần đọc giá trị rồi mới quyết định cập nhật, dùng locking read như SELECT ... FOR UPDATE trong cùng transaction để tránh đọc rồi ghi theo một trạng thái đã thay đổi. Lấy các khóa theo thứ tự thống nhất.

### 11.6. Giảm phạm vi truy vấn range

Tránh UPDATE/DELETE trên điều kiện quá rộng hoặc thiếu index. Dùng điều kiện có tính chọn lọc, index phù hợp và batch có giới hạn. Kiểm tra next-key/gap lock khi deadlock report chỉ ra xung đột trên khoảng index.

### 11.7. Đánh giá isolation level theo yêu cầu dữ liệu

Isolation level ảnh hưởng loại và phạm vi khóa, đặc biệt với range access trong REPEATABLE READ. READ COMMITTED có thể giảm một số gap lock nhưng cũng thay đổi semantics đọc và không loại bỏ mọi deadlock. Chỉ thay đổi isolation sau khi đánh giá yêu cầu nhất quán và kiểm thử các anomaly có thể xuất hiện.

## 12. Bài thực hành: sửa deadlock bằng thứ tự khóa

Tiếp tục dùng bảng lab_accounts ở mục 2. Nếu đã dọn bảng, tạo lại:

~~~sql
CREATE TABLE lab_accounts (
    account_id INT NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

INSERT INTO lab_accounts (account_id, balance)
VALUES (1, 1000.00), (2, 1000.00);
~~~

### 12.1. Bước 1 — Tái hiện deadlock

Lặp lại trình tự ở mục 2: Session A khóa hàng 1; Session B khóa hàng 2; B yêu cầu hàng 1; A yêu cầu hàng 2. Ghi lại session nhận lỗi 1213.

### 12.2. Bước 2 — Chuẩn hóa thứ tự khóa

Quy ước mọi transaction cần hai tài khoản đều khóa account_id nhỏ hơn trước:

Trong Session A:

~~~sql
START TRANSACTION;

SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 1
FOR UPDATE;

SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 2
FOR UPDATE;
~~~

Giữ transaction A mở. Chưa chạy COMMIT.

Trong Session B:

~~~sql
START TRANSACTION;

-- B sẽ chờ tại đây vì A đang giữ khóa hàng 1.
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 1
FOR UPDATE;
~~~

Khi B đang chờ, quay lại Session A và hoàn tất:

~~~sql
UPDATE lab_accounts
SET balance = balance - 10.00
WHERE account_id = 1;

UPDATE lab_accounts
SET balance = balance + 10.00
WHERE account_id = 2;

COMMIT;
~~~

Sau khi A commit, câu SELECT đang chờ của B tiếp tục. B lấy khóa hàng 2 theo cùng thứ tự rồi mới cập nhật theo nghiệp vụ chiều ngược lại:

~~~sql
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 2
FOR UPDATE;

UPDATE lab_accounts
SET balance = balance - 20.00
WHERE account_id = 2;

UPDATE lab_accounts
SET balance = balance + 20.00
WHERE account_id = 1;

COMMIT;
~~~

Vì cả hai transaction đều khóa hàng 1 rồi hàng 2, B chờ trước khi giữ hàng 2. Khi A commit, B tiếp tục theo cùng thứ tự; chu trình do hai hàng này bị khóa ngược chiều không hình thành.

### 12.3. Bước 3 — Đọc deadlock report

Sau khi tái hiện deadlock ở bước 1:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Tìm LATEST DETECTED DEADLOCK, ghi lại transaction id, câu SQL, index và lock đang chờ/đang giữ. So sánh với thứ tự khóa đã chạy trong hai session.

### 12.4. Bước 4 — Kiểm tra lock wait đang hoạt động

Khi một session đang bị block, chạy truy vấn Performance Schema ở mục 8.3 từ một session khác có quyền phù hợp. Xác định transaction đang yêu cầu khóa và transaction đang chặn nó.

### 12.5. Bước 5 — Kiểm tra dữ liệu và dọn lab

~~~sql
SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;

DROP TABLE lab_accounts;
~~~

Chỉ dọn bảng lab sau khi mọi transaction trong hai session đã được commit hoặc rollback.

**Kết quả cần đạt:** tái hiện được chu trình chờ khóa; phân biệt deadlock với lock wait thông thường; xác định transaction victim; đọc được deadlock report; sửa mẫu deadlock hai hàng bằng thứ tự khóa nhất quán.

## 13. Checklist điều tra sự cố deadlock

Khi deadlock xuất hiện trong môi trường thật:

1. Thu thập error code, SQLSTATE, thời điểm và tần suất.
2. Lưu deadlock report từ InnoDB status hoặc error log.
3. Xác định transaction nào bị rollback và câu lệnh nào nhận lỗi.
4. Đọc lock mode, index, record hoặc range liên quan.
5. Dựng lại trình tự câu lệnh của tất cả transaction trong chu trình.
6. Kiểm tra access path, index và isolation level.
7. Tìm thứ tự khóa không nhất quán, transaction quá dài hoặc range scan rộng.
8. Sửa thứ tự truy cập hoặc thu hẹp phạm vi khóa.
9. Bổ sung retry toàn transaction có giới hạn và idempotency.
10. Theo dõi tỷ lệ deadlock, lock wait time và thời gian transaction sau khi thay đổi.

Một số deadlock lẻ tẻ có thể là hệ quả bình thường của tải đồng thời. Mục tiêu vận hành là giữ tỷ lệ trong giới hạn chấp nhận được, bảo đảm ứng dụng phục hồi đúng và xử lý các mẫu deadlock lặp lại có nguyên nhân rõ.

## 14. Những lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Cách sửa |
|---|---|---|
| Mỗi luồng khóa hàng theo thứ tự đầu vào riêng | Hai luồng có thể khóa cùng hàng theo hướng ngược nhau | Sắp xếp ID và dùng thứ tự khóa chung |
| Chỉ retry câu SQL nhận lỗi 1213 | Transaction nạn nhân đã bị rollback toàn bộ | Retry toàn bộ transaction từ đầu |
| Cho rằng transaction cũ luôn còn mở sau deadlock | InnoDB đã rollback transaction victim | Bắt đầu transaction mới |
| Coi mọi lock wait là deadlock | Có thể chẩn đoán sai và thay đổi cấu hình không cần thiết | Kiểm tra chu trình hoặc deadlock report |
| Tăng innodb_lock_wait_timeout để chữa deadlock | Timeout không sửa thứ tự khóa; thời gian chờ có thể dài hơn | Sửa lock order và access path |
| Bỏ index để giảm chi phí ghi mà không đánh giá khóa | Truy vấn có thể scan và khóa nhiều record hơn | Đo trade-off bằng EXPLAIN và workload |
| Giữ transaction trong lúc gọi dịch vụ ngoài | Khóa tồn tại lâu, tăng xác suất deadlock | Đưa side effect ra sau commit hoặc dùng outbox |
| Giảm isolation level chỉ để hết deadlock | Có thể tạo anomaly dữ liệu mới | Chọn isolation theo semantics nghiệp vụ |
| Giả định InnoDB luôn hủy transaction nhỏ nhất theo số câu SQL | Victim dựa trên trọng lượng nội bộ, không phải số câu lệnh đơn giản | Thiết kế mọi transaction có thể bị hủy và retry an toàn |
| Retry vô hạn | Có thể tạo vòng lặp tải và làm nghẽn hệ thống | Giới hạn retry, backoff và quan sát tỷ lệ lỗi |

## 15. Nguyên tắc cần ghi nhớ

- Deadlock là chu trình chờ khóa; một transaction đơn thuần chờ transaction khác chưa chắc là deadlock.
- InnoDB phát hiện deadlock và rollback toàn bộ transaction được chọn làm victim.
- InnoDB có xu hướng chọn transaction có trọng lượng nhỏ hơn để giảm chi phí rollback; không dựa vào tuổi transaction hoặc thứ tự đến để đoán victim.
- Ứng dụng phải xử lý lỗi 1213 / SQLSTATE 40001 và retry toàn bộ transaction trong một transaction mới nếu thao tác có thể retry an toàn.
- Lock wait timeout thường là lỗi 1205; theo mặc định chỉ statement chờ bị rollback, còn cấu hình innodb_rollback_on_timeout có thể thay đổi phạm vi.
- Lấy khóa theo cùng thứ tự bảng và khóa chính ở mọi luồng giúp giảm deadlock do thứ tự ngược.
- Index phù hợp giúp thu hẹp phạm vi scan và khóa; range scan ở REPEATABLE READ có thể liên quan gap lock và next-key lock.
- Foreign key, unique index, trigger và index phụ cũng có thể tham gia vào chuỗi khóa.
- Transaction ngắn, batch hợp lý và không chờ mạng trong transaction giúp giảm thời gian giữ khóa.
- SHOW ENGINE INNODB STATUS hiển thị deadlock gần nhất; innodb_print_all_deadlocks có thể ghi mọi deadlock vào error log.
- Performance Schema data_locks và data_lock_waits hỗ trợ xem lock wait đang tồn tại; deadlock đã giải quyết có thể không còn trong các bảng này.
- Thứ tự khóa nhất quán giảm rủi ro nhưng không loại bỏ mọi deadlock; retry và idempotency vẫn cần thiết.

Deadlock là vấn đề cần được xử lý ở cả hai phía: thiết kế transaction để giảm xung đột và logic ứng dụng để phục hồi khi InnoDB chọn transaction làm nạn nhân. Khi hiểu wait-for cycle, trọng lượng transaction, index và thứ tự lấy khóa, bạn có thể đọc đúng bằng chứng và sửa nguyên nhân thay vì chỉ tăng timeout hoặc retry một câu lệnh riêng lẻ.
