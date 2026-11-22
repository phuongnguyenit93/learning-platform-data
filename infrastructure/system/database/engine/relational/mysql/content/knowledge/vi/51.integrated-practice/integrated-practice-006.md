# Đóng gói stored procedure với hợp đồng lỗi và kiểm thử

Stored procedure có thể gom một quy trình dữ liệu thành một điểm gọi ổn định: kiểm tra đầu vào, khóa hàng, cập nhật dữ liệu và trả kết quả. Tuy nhiên, một procedure chỉ dễ tích hợp khi ứng dụng biết rõ tham số nào bắt buộc, kết quả được trả bằng cách nào, lỗi nghiệp vụ khác lỗi hệ thống ra sao, ai sở hữu transaction và quyền nào được dùng khi procedure chạy.

Bài thực hành này xây dựng procedure `reserve_inventory` để giữ chỗ tồn kho. Procedure nhận mã hàng và số lượng, khóa bản ghi tồn kho, từ chối yêu cầu không hợp lệ hoặc không đủ hàng, cập nhật số lượng và trả tồn kho còn lại. Phần sau kiểm thử cả thành công, lỗi, rollback, concurrency và quyền truy cập từ ứng dụng Java.

## 1. Thiết kế hợp đồng trước khi viết SQL

Hợp đồng procedure là giao diện giữa database và caller. Nó cần ổn định như một API:

| Thành phần | Hợp đồng của `reserve_inventory` |
|---|---|
| Tên | `reserve_inventory` |
| Input `p_sku_id` | Mã hàng bắt buộc, dương, tham chiếu tới một hàng inventory |
| Input `p_quantity` | Số lượng cần giữ, bắt buộc và lớn hơn 0 |
| Output `p_remaining` | Số lượng còn lại sau khi giữ thành công |
| Thành công | Procedure kết thúc bình thường và output có giá trị |
| SKU không tồn tại | SQLSTATE `45000`, mã lỗi ứng dụng `30002` |
| Số lượng không hợp lệ | SQLSTATE `45000`, mã lỗi ứng dụng `30001` |
| Không đủ hàng | SQLSTATE `45000`, mã lỗi ứng dụng `30003` |
| Lỗi SQL bất ngờ | Giữ nguyên SQLSTATE và mã lỗi gốc để caller xử lý |
| Transaction | Caller sở hữu transaction; procedure không tự `COMMIT` hoặc `ROLLBACK` |
| Quyền | `SQL SECURITY INVOKER`; caller cần quyền thực thi và quyền trên bảng |

Phân biệt lỗi nghiệp vụ với lỗi hạ tầng. `INSUFFICIENT_STOCK` là kết quả nghiệp vụ dự kiến; deadlock, mất kết nối hoặc lỗi disk là sự cố cần chính sách retry/alert khác. Không dùng một thông báo chung “operation failed” cho tất cả trường hợp.

### Quy ước mã lỗi

MySQL cho phép procedure phát lỗi do ứng dụng định nghĩa bằng `SIGNAL SQLSTATE '45000'`. Có thể gắn `MYSQL_ERRNO` để caller phân biệt các trường hợp:

| MYSQL_ERRNO | SQLSTATE | Mã nghiệp vụ | Ý nghĩa |
|---:|---|---|---|
| 30001 | `45000` | `INVALID_QUANTITY` | Số lượng NULL hoặc không dương |
| 30002 | `45000` | `SKU_NOT_FOUND` | Không có mã hàng tương ứng |
| 30003 | `45000` | `INSUFFICIENT_STOCK` | Tồn kho thấp hơn số lượng yêu cầu |

Chọn dải mã riêng của ứng dụng, ghi vào tài liệu và không dùng trùng với mã lỗi MySQL đang được hệ thống xử lý. Ứng dụng nên dựa vào SQLSTATE và vendor error code; `MESSAGE_TEXT` phục vụ chẩn đoán và không nên là khóa phân nhánh duy nhất vì câu chữ có thể thay đổi.

## 2. Tạo schema thực hành

Ta dùng InnoDB để có transaction và row-level locking. Bảng inventory có một hàng cho mỗi SKU:

```sql
CREATE DATABASE IF NOT EXISTS warehouse_demo;
USE warehouse_demo;

CREATE TABLE inventory (
  sku_id BIGINT UNSIGNED NOT NULL,
  available_qty BIGINT NOT NULL,
  updated_at TIMESTAMP(6) NOT NULL
    DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (sku_id),
  CONSTRAINT chk_inventory_nonnegative
    CHECK (available_qty >= 0)
) ENGINE=InnoDB;

INSERT INTO inventory (sku_id, available_qty)
VALUES (1001, 12), (1002, 0), (1003, 4);
```

MySQL thực thi `CHECK` constraint từ phiên bản 8.0.16. Dù có constraint, procedure vẫn phải kiểm tra điều kiện nghiệp vụ và cập nhật nguyên tử. Constraint là lớp bảo vệ cuối cùng cho dữ liệu, không thay thế validation ở API.

Kiểm tra dữ liệu ban đầu:

```sql
SELECT sku_id, available_qty
FROM inventory
ORDER BY sku_id;
```

## 3. Viết procedure với SIGNAL, handler và RESIGNAL

Procedure sử dụng `SELECT ... FOR UPDATE` để khóa hàng inventory trong transaction của caller. `NOT FOUND` handler giúp phát hiện SKU không tồn tại. Các SQL exception khác tự truyền về caller; phần sau trình bày cách dùng `GET DIAGNOSTICS` và `RESIGNAL` khi routine cần handler để cleanup.

Trong MySQL command-line client, `DELIMITER` là lệnh của client dùng để thay dấu kết thúc câu lệnh khi định nghĩa routine có nhiều dấu `;`. Nó không phải câu SQL gửi tới server. Các GUI hoặc migration tool có thể cần cách gửi script khác; không thêm `DELIMITER` vào JDBC statement.

```sql
DELIMITER //

CREATE PROCEDURE reserve_inventory(
  IN p_sku_id BIGINT,
  IN p_quantity BIGINT,
  OUT p_remaining BIGINT
)
SQL SECURITY INVOKER
MODIFIES SQL DATA
BEGIN
  DECLARE v_available BIGINT DEFAULT NULL;
  DECLARE v_not_found BOOLEAN DEFAULT FALSE;

  DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_not_found = TRUE;

  SET p_remaining = NULL;

  IF p_sku_id IS NULL OR p_sku_id <= 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MYSQL_ERRNO = 30002,
          MESSAGE_TEXT = 'SKU_NOT_FOUND';
  END IF;

  IF p_quantity IS NULL OR p_quantity <= 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MYSQL_ERRNO = 30001,
          MESSAGE_TEXT = 'INVALID_QUANTITY';
  END IF;

  SELECT available_qty
    INTO v_available
  FROM inventory
  WHERE sku_id = p_sku_id
  FOR UPDATE;

  IF v_not_found THEN
    SIGNAL SQLSTATE '45000'
      SET MYSQL_ERRNO = 30002,
          MESSAGE_TEXT = 'SKU_NOT_FOUND';
  END IF;

  IF v_available < p_quantity THEN
    SIGNAL SQLSTATE '45000'
      SET MYSQL_ERRNO = 30003,
          MESSAGE_TEXT = 'INSUFFICIENT_STOCK';
  END IF;

  UPDATE inventory
  SET available_qty = available_qty - p_quantity
  WHERE sku_id = p_sku_id;

  SET p_remaining = v_available - p_quantity;
END//

DELIMITER ;
```

Các biến local phải được khai báo trước handler và câu lệnh thực thi. `CONTINUE HANDLER FOR NOT FOUND` chỉ đánh dấu trường hợp không tìm thấy hàng; procedure chủ động phát lỗi nghiệp vụ sau khi kiểm tra cờ. Các SQL exception khác tự truyền về caller vì procedure không bắt chúng.

Không ghi thông báo lỗi vào bảng audit trong cùng transaction rồi cho caller rollback mà kỳ vọng bản ghi audit vẫn tồn tại: thao tác insert audit đó cũng có thể bị rollback. Nếu cần audit bền vững, dùng cơ chế logging ngoài transaction hoặc một thiết kế ghi nhận riêng có ranh giới transaction rõ ràng.

## 4. Vì sao procedure yêu cầu transaction của caller?

`SELECT ... FOR UPDATE` khóa hàng để ngăn hai transaction cùng đọc một số lượng tồn kho cũ rồi cùng trừ hàng. Khóa chỉ được giữ trong transaction. Nếu caller đang dùng autocommit và procedure không mở transaction, khóa của câu `SELECT` có thể được giải phóng khi statement kết thúc trước câu `UPDATE` tiếp theo.

Vì vậy, hợp đồng của procedure yêu cầu caller bắt đầu transaction trước khi gọi và commit chỉ khi procedure thành công:

```sql
START TRANSACTION;
CALL reserve_inventory(1001, 3, @remaining);
SELECT @remaining AS remaining_qty;
COMMIT;
```

Nếu `CALL` phát lỗi, caller phải `ROLLBACK` transaction thay vì commit. Trong SQL client, thực hiện `ROLLBACK` sau khi nhận lỗi; trong Java, đặt rollback trong nhánh exception. Ví dụ trên là luồng thành công, không phải script xử lý tự động cả hai nhánh.

Procedure không gọi `START TRANSACTION`, `COMMIT` hoặc `ROLLBACK`, nên nó có thể được ghép vào transaction lớn hơn của đơn hàng. Caller có thể kiểm tra giá, ghi order, reserve inventory và ghi order item trong cùng transaction. Nếu một bước thất bại, caller rollback toàn bộ đơn vị công việc.

Không gọi `COMMIT` bên trong procedure dùng chung nếu hợp đồng yêu cầu caller quản lý transaction. `COMMIT` trong routine có thể commit cả transaction mà caller đã mở, làm phá vỡ tính nguyên tử của nghiệp vụ bên ngoài.

### Phạm vi rollback

Rollback chỉ hoàn tác thay đổi transactional của InnoDB trong transaction hiện tại. DDL như `CREATE TABLE` hoặc `ALTER TABLE` có quy tắc implicit commit; thay đổi trên non-transactional table và side effect bên ngoài cũng không được hoàn tác theo cách caller mong đợi. Procedure nghiệp vụ nên tập trung DML và tránh trộn DDL vào transaction xử lý đơn hàng.

## 5. SIGNAL, RESIGNAL và các loại handler

### SIGNAL: phát lỗi nghiệp vụ có chủ đích

`SIGNAL` kết thúc luồng xử lý bằng một condition. Ví dụ:

```sql
SIGNAL SQLSTATE '45000'
  SET MYSQL_ERRNO = 30003,
      MESSAGE_TEXT = 'INSUFFICIENT_STOCK';
```

`45000` là SQLSTATE dùng cho exception do người dùng định nghĩa. `MYSQL_ERRNO` và `MESSAGE_TEXT` cung cấp mã và nội dung để ứng dụng phân loại. Không trả thông tin nội bộ như tên host, SQL chứa dữ liệu nhạy cảm hoặc secret trong message.

### RESIGNAL: giữ hoặc bổ sung lỗi đang xử lý

`RESIGNAL` chỉ dùng trong handler để phát lại condition đang được handler xử lý. Dạng đơn giản:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
  RESIGNAL;
END;
```

Dùng `RESIGNAL` thay vì `SIGNAL SQLSTATE '45000'` mới nếu muốn giữ nguyên lỗi gốc như duplicate key, deadlock hoặc lỗi constraint. Nếu phát một lỗi chung mới, caller sẽ mất SQLSTATE và mã lỗi gốc cần thiết để quyết định retry hay báo lỗi.

Khi routine cần cleanup hoặc bổ sung thông tin chẩn đoán trước khi trả lỗi, có thể dùng mẫu sau. Các biến local phải được khai báo trước handler trong block thực tế:

```sql
DECLARE v_state CHAR(5);
DECLARE v_errno INT;
DECLARE v_message TEXT;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
  GET DIAGNOSTICS CONDITION 1
    v_state = RETURNED_SQLSTATE,
    v_errno = MYSQL_ERRNO,
    v_message = MESSAGE_TEXT;

  -- Thực hiện cleanup thuộc quyền sở hữu của routine tại đây.
  -- Sau đó phát lại condition gốc để caller vẫn phân loại được lỗi.
  RESIGNAL;
END;
```

Không thêm handler chỉ để bọc lại mọi lỗi thành một mã chung. Nếu routine không cần cleanup, cứ để lỗi SQL truyền về caller; nếu cần audit bền vững, lưu ý bản ghi trong cùng transaction có thể bị rollback cùng dữ liệu nghiệp vụ.

### EXIT và CONTINUE

| Handler | Hành vi |
|---|---|
| `CONTINUE` | Xử lý condition rồi tiếp tục thực thi tại câu lệnh sau câu đã phát condition |
| `EXIT` | Kết thúc block `BEGIN ... END` nơi handler được khai báo |

`NOT FOUND` thường xuất hiện khi `SELECT ... INTO` không trả hàng hoặc cursor đã hết dữ liệu. Với cursor loop, đặt cờ trong `CONTINUE HANDLER FOR NOT FOUND` rồi thoát loop khi cờ được bật. `SQLEXCEPTION` không bao gồm class SQLSTATE `00`, `01` và `02`; vì vậy cần hiểu riêng `SQLWARNING` và `NOT FOUND` nếu procedure dựa vào chúng.

### GET DIAGNOSTICS

`GET DIAGNOSTICS` đọc thông tin condition trong diagnostics area, ví dụ SQLSTATE, mã lỗi và message:

```sql
GET DIAGNOSTICS CONDITION 1
  v_sqlstate = RETURNED_SQLSTATE,
  v_mysql_errno = MYSQL_ERRNO,
  v_message = MESSAGE_TEXT;
```

Condition 1 là condition đầu tiên trong diagnostics area. Khi có nhiều condition/warning, cần xem số condition và chọn đúng condition cần phân tích. Không dùng message text làm hợp đồng ổn định duy nhất; message có thể khác theo phiên bản hoặc ngôn ngữ.

## 6. Kiểm thử trực tiếp bằng SQL client

Trước khi nối Spring Boot, kiểm tra procedure bằng các tình huống có thể tái lập. Mỗi lần gọi thành công phải nằm trong transaction:

```sql
START TRANSACTION;
CALL reserve_inventory(1001, 2, @remaining);
SELECT @remaining AS remaining_qty;
COMMIT;

SELECT sku_id, available_qty
FROM inventory
WHERE sku_id = 1001;
```

Với dữ liệu ban đầu là 12, kết quả còn lại phải là 10. Kiểm tra cả output parameter lẫn giá trị thật trong bảng sau commit.

Các ca lỗi:

```sql
-- Số lượng không hợp lệ: SQLSTATE 45000, MYSQL_ERRNO 30001
START TRANSACTION;
CALL reserve_inventory(1001, 0, @remaining);
ROLLBACK;

-- SKU không tồn tại: SQLSTATE 45000, MYSQL_ERRNO 30002
START TRANSACTION;
CALL reserve_inventory(999999, 1, @remaining);
ROLLBACK;

-- Không đủ hàng: SQLSTATE 45000, MYSQL_ERRNO 30003
START TRANSACTION;
CALL reserve_inventory(1002, 1, @remaining);
ROLLBACK;
```

Trong một client tương tác, mỗi `CALL` lỗi sẽ trả quyền điều khiển về client; thực hiện `ROLLBACK` cho transaction đã mở trước khi chạy ca tiếp theo. Một số GUI dừng thực thi script tại câu lỗi, nên hãy chạy từng ca riêng hoặc dùng test harness tự động để luôn rollback trong nhánh lỗi.

Kiểm tra procedure và định nghĩa:

```sql
SHOW CREATE PROCEDURE reserve_inventory\G

SELECT
  ROUTINE_NAME,
  SECURITY_TYPE,
  SQL_DATA_ACCESS,
  DEFINER
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'warehouse_demo'
  AND ROUTINE_NAME = 'reserve_inventory';
```

## 7. Kiểm thử hợp đồng lỗi trong Java/JDBC

JDBC nhận lỗi stored procedure qua `SQLException` hoặc lớp con. Với lỗi nghiệp vụ do `SIGNAL`, kiểm tra SQLState và vendor error code thay vì so sánh toàn bộ message.

Ví dụ gọi procedure và quản lý transaction:

```java
long reserveInventory(DataSource dataSource, long skuId, long quantity)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            long remaining;
            try (CallableStatement call = connection.prepareCall(
                    "{call reserve_inventory(?, ?, ?)}")) {
                call.setLong(1, skuId);
                call.setLong(2, quantity);
                call.registerOutParameter(3, Types.BIGINT);
                call.execute();
                remaining = call.getLong(3);
            }

            connection.commit();
            return remaining;
        } catch (SQLException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }
            throw error;
        }
    }
}
```

Ví dụ tập trung vào ranh giới JDBC. Trong Spring, nên để service method có `@Transactional` sở hữu transaction và gọi procedure qua `JdbcTemplate`, `SimpleJdbcCall` hoặc `CallableStatement` dùng cùng transaction-bound connection. Không tự lấy một connection mới bên trong procedure wrapper nếu muốn cùng transaction với JPA.

Kiểm tra lỗi:

```java
SQLException error = assertThrows(SQLException.class, () ->
    reserveInventory(dataSource, 1002L, 1L)
);

assertEquals("45000", error.getSQLState());
assertEquals(30003, error.getErrorCode());
```

Trong một số tầng framework, lỗi có thể được bọc trong `DataAccessException` hoặc exception khác. Khi đó, tìm `SQLException` gốc trong cause chain và kiểm tra SQLState/vendor code ở đó. Driver hoặc framework có thể biểu diễn lỗi theo kiểu exception khác nhau; bài test cần cố định phiên bản connector và xác minh hành vi thực tế.

Không assert toàn bộ `getMessage()` vì message có thể chứa tên bảng, câu SQL hoặc khác biệt theo phiên bản. Với custom error, có thể kiểm tra một token ngắn nếu đó là phần message đã cam kết trong hợp đồng.

### Kết quả COMMIT không xác định và idempotency

Nếu connection mất đúng lúc `COMMIT`, ứng dụng có thể không biết transaction đã commit trên server hay chưa. Gọi lại procedure ngay với request mới có thể trừ tồn kho lần thứ hai. `rollback()` trên socket đã mất không chứng minh transaction chưa commit.

Với quy trình checkout, lưu một idempotency key ổn định cùng order trong chính transaction chứa lời gọi procedure:

```sql
CREATE TABLE orders (
  order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  request_id BINARY(16) NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (order_id),
  UNIQUE KEY uq_orders_request_id (request_id)
) ENGINE=InnoDB;
```

Khi nhận lại cùng request, ứng dụng tra cứu `request_id` trên connection mới. Nếu order đã tồn tại, trả lại kết quả đã lưu; nếu chưa tồn tại, mới chạy transaction với cùng key. Xử lý duplicate key phải xác minh request payload tương ứng, không chỉ bỏ qua lỗi. Vì order và thay đổi inventory commit trong cùng transaction InnoDB, key này giúp caller nhận ra lần thực hiện trước đã hoàn tất.

## 8. Kiểm thử rollback và tính nguyên tử

Tạo một transaction gồm nhiều bước: cập nhật một bản ghi đơn hàng, gọi `reserve_inventory`, rồi cố ý phát sinh lỗi ở bước tiếp theo. Sau rollback, kiểm tra cả đơn hàng và tồn kho đều trở về trạng thái trước transaction.

Kịch bản:

1. Đọc tồn kho ban đầu của SKU 1001.
2. Mở transaction.
3. Ghi một hàng order ở trạng thái pending.
4. Gọi procedure để trừ tồn kho.
5. Gây lỗi có chủ đích ở bước ghi order item, hoặc rollback từ caller.
6. Xác nhận order không tồn tại và tồn kho không đổi.

Đây là lý do procedure không tự commit. Nếu procedure commit sau khi trừ tồn kho, transaction ngoài không thể rollback toàn bộ đơn hàng một cách nguyên tử.

Kiểm thử thêm trường hợp procedure phát lỗi trước khi cập nhật. Caller rollback vẫn phải an toàn; không có thay đổi dở dang trong bảng inventory.

## 9. Kiểm thử concurrency và khóa hàng

Giả sử SKU 1001 có 10 đơn vị. Hai request đồng thời cùng giữ 7 đơn vị. Kết quả đúng là chỉ một request thành công; request còn lại phải nhận `INSUFFICIENT_STOCK`, và tồn kho cuối cùng không âm.

Thiết kế test:

1. Tạo hai JDBC connection độc lập.
2. Mỗi connection bắt đầu transaction riêng.
3. Dùng barrier/latch ở test harness để hai worker gọi procedure gần như đồng thời.
4. Worker đầu tiên lấy row lock; worker còn lại phải chờ.
5. Worker đầu tiên trừ 7 và commit.
6. Worker thứ hai tiếp tục, đọc số lượng mới là 3 và nhận lỗi không đủ hàng.
7. Caller thứ hai rollback.
8. Kiểm tra tồn kho còn 3, không âm và chỉ có một reservation thành công.

Không dùng `Thread.sleep()` làm cơ chế đồng bộ chính. Dùng `CountDownLatch`, `CyclicBarrier` hoặc cơ chế đồng bộ tương đương để kiểm soát thời điểm hai transaction bắt đầu.

`SELECT ... FOR UPDATE` chỉ bảo vệ đúng khi hai worker dùng transaction riêng và transaction đầu tiên chưa commit trước khi worker thứ hai thực hiện locking read. Nếu test vô tình chạy cả hai lời gọi trên cùng connection hoặc autocommit, nó không còn mô phỏng đúng concurrency cần kiểm tra.

### Deadlock và lock wait timeout

Khi một transaction khóa nhiều SKU theo thứ tự khác transaction khác, có thể tạo deadlock. MySQL chọn một transaction làm victim và trả lỗi; ứng dụng phải rollback transaction đó và có thể retry toàn bộ đơn vị công việc với giới hạn.

Lock wait timeout khác deadlock. Theo cấu hình mặc định phổ biến của InnoDB, lock wait timeout thường rollback statement bị timeout chứ không nhất thiết rollback toàn bộ transaction; ứng dụng cần rollback transaction theo hợp đồng trước khi retry. Kiểm tra `innodb_rollback_on_timeout` và hành vi phiên bản/cấu hình thực tế.

Không retry riêng câu `UPDATE` sau deadlock rồi tiếp tục phần transaction cũ. Retry phải bắt đầu transaction mới và chạy lại toàn bộ logic nghiệp vụ có tính nguyên tử.

## 10. Quyền EXECUTE và SQL SECURITY

Stored procedure có hai mô hình bảo mật chính:

| Chế độ | Quyền được dùng khi procedure chạy | Caller cần |
|---|---|---|
| `SQL SECURITY INVOKER` | Quyền của account gọi procedure | `EXECUTE` và quyền trên bảng/view mà routine truy cập |
| `SQL SECURITY DEFINER` | Quyền của account được khai báo làm definer | Thường cần `EXECUTE`; routine thực hiện thao tác bằng quyền definer |

Ví dụ procedure hiện tại dùng `SQL SECURITY INVOKER`. Caller phải có quyền cần thiết trên `warehouse_demo.inventory`:

```sql
GRANT EXECUTE
ON PROCEDURE warehouse_demo.reserve_inventory
TO 'orders_app'@'10.20.%';

GRANT SELECT, UPDATE
ON warehouse_demo.inventory
TO 'orders_app'@'10.20.%';
```

Nếu muốn che quyền truy cập bảng và chỉ cho caller gọi một thao tác đã kiểm soát, có thể cân nhắc `SQL SECURITY DEFINER`. Khi đó:

- Dùng một account definer chuyên dụng với quyền tối thiểu cần cho routine.
- Không dùng account cá nhân hoặc account quản trị toàn quyền làm definer.
- Giữ definer tồn tại qua migration, restore và môi trường DR.
- Kiểm tra `SHOW CREATE PROCEDURE` và `DEFINER` sau deploy.
- Cẩn thận với dynamic SQL và mọi input có thể ảnh hưởng câu lệnh được thực thi.

Routine `DEFINER` có thể trở thành đường nâng quyền nếu người gọi được truyền dữ liệu điều khiển câu SQL ngoài dự kiến. Với managed MySQL, provider cũng có thể giới hạn việc đặt definer hoặc yêu cầu account đặc biệt; xác minh trước khi chọn mô hình.

## 11. SQL động và phòng tránh injection

Không nối trực tiếp input từ caller vào SQL động. Với giá trị, dùng parameter binding. Với tên bảng/cột hoặc hướng sắp xếp, parameter marker không thay thế identifier; phải kiểm tra input bằng whitelist rồi mới ghép vào câu lệnh.

Ví dụ không an toàn:

```sql
-- Không làm như sau với input không tin cậy
SET @sql = CONCAT(
  'SELECT * FROM orders WHERE customer_id = ',
  p_customer_id
);
```

Nếu thật sự cần dynamic SQL, whitelist identifier và bind value qua placeholder. Stored program dùng prepared statement có một số giới hạn về phạm vi biến local; thường phải chuyển giá trị sang user variable trước khi `EXECUTE ... USING`. User variable thuộc session nên cần quản lý tên và trạng thái cẩn thận khi dùng connection pool.

Nếu procedure chỉ thao tác trên một bảng và một tập cột cố định như `reserve_inventory`, không cần dynamic SQL. SQL tĩnh dễ kiểm thử, dễ phân quyền và ít rủi ro hơn.

## 12. Quy tắc trả kết quả ổn định

Stored procedure có thể trả dữ liệu qua OUT/INOUT parameter hoặc result set. Chọn một hợp đồng rõ ràng cho từng routine:

- OUT parameter phù hợp với số lượng kết quả nhỏ, có cấu trúc cố định.
- Result set phù hợp khi trả nhiều hàng hoặc dữ liệu truy vấn.
- Không phát thêm các `SELECT` dùng để debug vì chúng tạo result set phụ và có thể làm JDBC caller đọc nhầm.
- Đặt tên, kiểu dữ liệu, thứ tự cột và nullability rõ ràng nếu trả result set.
- Không thay đổi signature hoặc ý nghĩa output mà không phối hợp version ứng dụng.

MySQL không hỗ trợ overload procedure chỉ bằng cách tạo nhiều procedure cùng tên với signature khác nhau. Khi cần thay đổi hợp đồng không tương thích, có thể tạo tên phiên bản mới như `reserve_inventory_v2`, triển khai caller mới rồi loại bỏ phiên bản cũ theo lịch.

Không dùng output parameter để trả lỗi đồng thời với SQL exception nếu caller không có quy ước rõ ràng. Với lỗi, phát exception; với thành công, trả output. Cách này tránh trạng thái nửa thành công/nửa lỗi khó diễn giải.

## 13. Kiểm thử quyền bằng account thực tế

Test bằng DBA account có thể che lỗi permission. Cần tạo account gần giống runtime và chạy procedure bằng chính account đó.

Các kiểm tra:

1. Account runtime gọi được procedure khi có `EXECUTE`.
2. Với `SQL SECURITY INVOKER`, account có đủ quyền SELECT/UPDATE cần thiết.
3. Thu hồi `UPDATE` phải làm test quyền thất bại như dự kiến.
4. Account runtime không có `CREATE`, `ALTER`, `DROP` nếu không cần.
5. Nếu dùng `DEFINER`, caller không thể truy cập bảng ngoài phạm vi routine chỉ nhờ quyền của definer.
6. Sau restore hoặc deploy sang staging, definer và grant vẫn hợp lệ.

Kiểm tra:

```sql
SHOW GRANTS FOR 'orders_app'@'10.20.%';
SHOW CREATE PROCEDURE warehouse_demo.reserve_inventory\G
```

Đừng dùng `GRANT ALL ON *.*` cho account test chỉ để làm test chạy. Hãy làm test theo đúng least privilege, nếu không test không phát hiện được lỗi phân quyền khi deploy production.

## 14. Bộ test cần có

| Nhóm | Trường hợp | Kết quả mong đợi |
|---|---|---|
| Thành công | SKU tồn tại, quantity dương, đủ hàng | OUT trả tồn kho mới; dữ liệu chỉ thay đổi sau commit |
| Validation | Quantity bằng 0 hoặc âm | SQLSTATE `45000`, mã `30001` |
| Validation | SKU NULL hoặc bằng 0 | SQLSTATE `45000`, mã `30002` |
| Không tìm thấy | SKU không có trong bảng | SQLSTATE `45000`, mã `30002` |
| Nghiệp vụ | Tồn kho thấp hơn quantity | SQLSTATE `45000`, mã `30003`; không trừ hàng |
| Rollback | Caller rollback sau procedure thành công | Tồn kho trở về giá trị ban đầu |
| Atomicity | Bước tiếp theo của order thất bại | Cả order và inventory rollback |
| Concurrency | Hai transaction cùng giữ nhiều hơn lượng tồn kho | Chỉ số lượng request hợp lệ thành công; tồn kho không âm |
| Lock | Transaction khác giữ row lock quá lâu | Timeout được phân loại và transaction được rollback |
| Deadlock | Hai transaction khóa nhiều hàng theo thứ tự khác nhau | Một transaction có thể bị chọn làm victim; retry toàn transaction có giới hạn |
| Permission | Caller thiếu `EXECUTE` hoặc quyền bảng | Bị từ chối theo SQL SECURITY đã chọn |
| Compatibility | Caller dùng JDBC và driver production | OUT parameter và SQLState/vendor code được đọc đúng |

Chạy test với MySQL cùng phiên bản mục tiêu, InnoDB và schema migration thực tế. H2 hoặc mock có thể dùng cho unit test logic bên ngoài, nhưng không chứng minh semantics của `SIGNAL`, row lock, MySQL diagnostics hay stored procedure.

## 15. Chẩn đoán khi test thất bại

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Procedure không tạo được | Sai thứ tự khai báo, cú pháp handler hoặc delimiter của client | Đọc lỗi DDL, kiểm tra `DECLARE` đứng trước statement thực thi |
| Caller nhận lỗi chung thay vì lỗi gốc | Handler phát `SIGNAL` mới và làm mất condition ban đầu | Dùng `RESIGNAL` khi cần giữ SQLSTATE/vendor code gốc |
| SKU tồn tại nhưng báo NOT FOUND | Schema/parameter mapping sai hoặc truy vấn dùng điều kiện khác | Kiểm tra kiểu khóa, schema hiện hành và dữ liệu fixture |
| Hai request cùng giữ vượt tồn kho | Thiếu transaction hoặc locking read không giữ khóa tới commit | Kiểm tra autocommit, connection riêng và `FOR UPDATE` |
| Rollback order nhưng tồn kho vẫn giảm | Procedure đã tự commit hoặc dùng connection khác | Đưa transaction ownership về caller và dùng cùng connection |
| Test quyền chạy được với DBA nhưng lỗi runtime | Account test có quyền rộng hơn ứng dụng | Chạy bằng account runtime và kiểm tra `SHOW GRANTS` |
| JDBC không đọc OUT parameter | Sai vị trí/thứ tự register, kiểu JDBC hoặc nhiều result set | Kiểm tra signature và `CallableStatement`; loại bỏ SELECT debug |
| Error audit biến mất sau rollback | Log được ghi trong cùng transaction bị rollback | Dùng logging ngoài transaction hoặc thiết kế audit riêng |
| Retry tạo reservation trùng | Retry không có idempotency key hoặc transaction outcome chưa được xác minh | Dùng request ID duy nhất và tra cứu trước khi chạy lại |

Khi điều tra, giữ lại `SHOW CREATE PROCEDURE`, SQLSTATE, vendor code, transaction isolation, autocommit, grants và log của hai connection trong test concurrency. Không chỉ lưu message text vì message không đủ để tái hiện nguyên nhân.

## 16. Quy trình triển khai routine

Stored procedure là database API, vì vậy cần đi qua pipeline migration giống schema:

1. Review signature, input validation, output và error code contract.
2. Review transaction ownership và mọi đường `COMMIT`/`ROLLBACK`.
3. Review SQL SECURITY, definer, grants và dynamic SQL.
4. Tạo routine bằng migration có version; không sửa thủ công production rồi quên cập nhật repository.
5. Chạy test trên MySQL thật cho success, error, rollback, permission và concurrency.
6. Deploy routine tương thích trước khi deploy caller mới nếu cần giữ backward compatibility.
7. Theo dõi lỗi SQLSTATE/vendor code và thời gian thực thi sau deploy.
8. Chỉ loại bỏ procedure cũ sau khi xác nhận không còn caller sử dụng.

Lưu ý: thay đổi routine bằng `DROP PROCEDURE` rồi `CREATE PROCEDURE` có thể tạo khoảng thời gian caller không gọi được procedure và DDL có quy tắc implicit commit. Chọn cách triển khai, cửa sổ và thứ tự rollout phù hợp với công cụ migration và khả năng tương thích của dịch vụ MySQL.

## 17. Tình huống thực hành end-to-end

Một checkout service cần tạo đơn và giữ hàng. Yêu cầu là hai request không thể cùng giữ nhiều hơn tồn kho, lỗi nghiệp vụ phải được trả về dưới dạng mã ổn định và mọi thay đổi phải rollback nếu ghi order item thất bại.

**Bước 1 — Chuẩn bị schema.** Tạo `inventory` với primary key trên `sku_id`, InnoDB và constraint không âm. Nạp SKU có 12 đơn vị.

**Bước 2 — Tạo procedure.** Định nghĩa `reserve_inventory` với hai input, một output, `SIGNAL` cho ba lỗi nghiệp vụ và handler `NOT FOUND`; các SQL exception khác tự truyền về caller.

**Bước 3 — Quy định transaction.** Service mở transaction, ghi order pending, gọi procedure trên cùng connection, ghi order item và commit. Nếu bất kỳ bước nào lỗi, service rollback toàn transaction.

**Bước 4 — Kiểm thử hợp đồng.** Gọi procedure qua JDBC; xác nhận success trả OUT parameter, lỗi invalid quantity/missing SKU/insufficient stock có SQLSTATE và vendor code đúng.

**Bước 5 — Kiểm thử rollback.** Cố ý làm bước ghi order item thất bại sau khi reserve; xác nhận order và tồn kho đều không thay đổi sau rollback.

**Bước 6 — Kiểm thử đồng thời.** Dùng hai connection giữ 7 đơn vị từ cùng SKU có 10 đơn vị. Chỉ một transaction được commit; transaction còn lại nhận insufficient stock; tồn kho cuối cùng bằng 3.

**Bước 7 — Kiểm thử quyền.** Chạy bằng runtime account có đúng `EXECUTE`, `SELECT`, `UPDATE`; xác nhận không cần quyền DDL hoặc global privilege.

**Bước 8 — Triển khai và quan sát.** Đưa migration procedure vào pipeline, theo dõi tần suất lỗi theo mã, deadlock, lock wait, latency và số lần retry.

## 18. Checklist trước production

- [ ] Signature, kiểu tham số, nullability và output được tài liệu hóa.
- [ ] Lỗi nghiệp vụ có SQLSTATE và `MYSQL_ERRNO` ổn định.
- [ ] `SIGNAL` dùng cho lỗi dự kiến; `RESIGNAL` giữ lỗi SQL bất ngờ khi cần.
- [ ] `NOT FOUND`, `SQLWARNING` và `SQLEXCEPTION` được xử lý đúng ngữ nghĩa.
- [ ] Handler không nuốt lỗi hoặc trả kết quả thành công giả.
- [ ] Transaction ownership rõ ràng; procedure không commit transaction của caller ngoài hợp đồng.
- [ ] Các locking read chạy trong transaction có phạm vi giữ lock đúng.
- [ ] Rollback được kiểm thử qua toàn bộ quy trình nghiệp vụ.
- [ ] Concurrency test dùng connection và transaction độc lập.
- [ ] Deadlock/lock timeout được phân loại; retry toàn transaction có giới hạn.
- [ ] Runtime account có quyền tối thiểu; SQL SECURITY và definer được review.
- [ ] Dynamic SQL được loại bỏ hoặc whitelist identifier và bind value an toàn.
- [ ] Result set/OUT parameter không có debug output ngoài hợp đồng.
- [ ] JDBC test kiểm tra SQLState/vendor code thay vì phụ thuộc toàn bộ message.
- [ ] Migration có version, thứ tự rollout và phương án tương thích caller.
- [ ] Audit/logging có ranh giới transaction rõ ràng và không làm lộ dữ liệu nhạy cảm.

Stored procedure đáng tin cậy cần được thiết kế như một API có hợp đồng: tham số rõ, kết quả ổn định, lỗi phân loại được, transaction thuộc về một chủ thể và quyền thực thi được giới hạn. Kết hợp `SIGNAL`, `RESIGNAL`, diagnostics, locking read và kiểm thử trên MySQL thật giúp ứng dụng xử lý đúng cả lỗi nghiệp vụ lẫn sự cố đồng thời mà không để dữ liệu dở dang.
