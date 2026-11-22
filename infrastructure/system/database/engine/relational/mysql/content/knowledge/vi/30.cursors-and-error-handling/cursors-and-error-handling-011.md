# Thiết kế lỗi có mã ổn định và kiểm thử từ JDBC

Một stored procedure có thể phát sinh lỗi vì dữ liệu đầu vào không hợp lệ, bản ghi không tồn tại, trạng thái nghiệp vụ không cho phép, vi phạm khóa duy nhất hoặc lỗi hạ tầng. Nếu ứng dụng chỉ đọc chuỗi thông báo lỗi rồi đoán nguyên nhân, hợp đồng giữa MySQL và Java sẽ rất dễ vỡ khi câu chữ thay đổi, server nâng phiên bản hoặc thông báo được bản địa hóa.

Thiết kế lỗi tốt cần có **mã lỗi ổn định**, **SQLSTATE có ý nghĩa**, thông báo dành cho chẩn đoán và quy tắc transaction rõ ràng. Phía JDBC phải kiểm thử những thuộc tính ổn định đó trực tiếp qua SQLException, đồng thời xác nhận dữ liệu không bị thay đổi dở dang khi routine thất bại.

Trong module DATABASE_MYSQL, bài học này kết nối xử lý lỗi trong stored program với hợp đồng API của ứng dụng Java. Bạn sẽ dùng SIGNAL, RESIGNAL, GET DIAGNOSTICS, MYSQL_ERRNO, SQLSTATE, CallableStatement và test tích hợp để thiết kế, phát hiện và duy trì lỗi nghiệp vụ theo cách có thể kiểm chứng.

## 1. Hợp đồng lỗi giữa MySQL và ứng dụng

Một lỗi được gửi từ stored procedure tới ứng dụng thường có ba thành phần quan trọng:

| Thành phần | Vai trò | Có nên dùng làm khóa phân loại nghiệp vụ? |
|---|---|---|
| MYSQL_ERRNO | Mã lỗi số mà MySQL/driver trả về; có thể đặt mã riêng cho lỗi ứng dụng. | Có. Đây là mã ổn định chính trong hợp đồng ví dụ của bài. |
| RETURNED_SQLSTATE | Mã trạng thái SQL gồm 5 ký tự, biểu thị nhóm lỗi. | Có, để phân loại nhóm và xử lý theo chuẩn SQL. |
| MESSAGE_TEXT | Nội dung mô tả để con người đọc và chẩn đoán. | Không. Câu chữ có thể thay đổi; không parse message để quyết định luồng nghiệp vụ. |

Ví dụ một lỗi nghiệp vụ:

~~~sql
SIGNAL SQLSTATE '45000'
    SET MYSQL_ERRNO = 31004,
        MESSAGE_TEXT = 'Insufficient inventory';
~~~

Ứng dụng có thể nhận:

~~~text
SQLState:   45000
Error code: 31004
Message:    Insufficient inventory
~~~

SQLSTATE 45000 là SQLSTATE phổ biến cho exception do người dùng định nghĩa trong MySQL. MYSQL_ERRNO = 31004 là mã chi tiết do hệ thống ứng dụng quy ước. Message chỉ cung cấp thông tin giải thích.

### Vì sao không phân loại bằng message?

Không nên viết logic như:

~~~java
if (exception.getMessage().contains("Insufficient inventory")) {
    // Xử lý lỗi tồn kho không đủ.
}
~~~

Câu chữ có thể đổi từ “Insufficient inventory” thành “Not enough stock”, được bổ sung mã sản phẩm, hoặc bị driver/framework bọc lại. Khi đó logic nghiệp vụ bị lỗi dù mã lỗi không đổi.

Thay vào đó, hãy kiểm tra:

~~~java
if (exception.getErrorCode() == 31004) {
    // Xử lý lỗi tồn kho không đủ.
}
~~~

Với JDBC, SQLException.getErrorCode() trả vendor-specific error code; getSQLState() trả SQLSTATE. Với MySQL Connector/J, mã số server được đọc qua getErrorCode().

## 2. SQLSTATE và MYSQL_ERRNO

SQLSTATE có 5 ký tự. Hai ký tự đầu chỉ lớp trạng thái; ba ký tự sau mô tả trạng thái cụ thể trong lớp đó.

| SQLSTATE class | Ý nghĩa khái quát | Ví dụ thường gặp |
|---|---|---|
| 00 | Hoàn tất thành công | 00000 |
| 01 | Warning | Warning condition |
| 02 | No data | NOT FOUND trong một số thao tác đọc |
| 22 | Data exception | Giá trị dữ liệu không hợp lệ |
| 23 | Integrity constraint violation | Vi phạm unique/foreign key |
| 40 | Transaction rollback | Deadlock hoặc transaction bị rollback |
| 45 | Exception do người dùng định nghĩa | 45000 |

Không cần tự tạo SQLSTATE cho mọi lỗi nghiệp vụ. Có thể dùng 45000 cho các lỗi do routine chủ động phát ra và phân biệt chi tiết bằng MYSQL_ERRNO.

### Mã lỗi nghiệp vụ cần có namespace

Đặt một dải mã riêng, thống nhất giữa các routine và Java application. Ví dụ:

| MYSQL_ERRNO | Tên ổn định | Ý nghĩa |
|---:|---|---|
| 31001 | INVALID_REQUEST | Thiếu hoặc sai dữ liệu đầu vào. |
| 31002 | PRODUCT_NOT_FOUND | Không tìm thấy sản phẩm cần thao tác. |
| 31003 | DUPLICATE_REQUEST | Request ID đã được sử dụng. |
| 31004 | INSUFFICIENT_INVENTORY | Số lượng tồn kho không đáp ứng yêu cầu. |
| 31005 | INVENTORY_CONFLICT | Điều kiện cập nhật không còn đúng tại thời điểm ghi. |

Các mã trên là quy ước của ví dụ, không phải mã lỗi mặc định của MySQL. Trong dự án thật:

- Chọn dải số do team database/application quản lý và xác nhận không trùng mã server đang dùng.
- Không tái sử dụng mã đã công bố cho ý nghĩa khác.
- Lưu mapping mã ↔ tên lỗi ↔ hành động ứng dụng trong source control.
- Khi thay đổi hợp đồng, version hóa hoặc duy trì tương thích ngược.
- Không đưa thông tin nhạy cảm, SQL text, token hoặc dữ liệu cá nhân vào MESSAGE_TEXT.

## 3. Phát lỗi chủ động bằng SIGNAL

SIGNAL kết thúc luồng hiện tại bằng một condition. Với lỗi nghiệp vụ, dùng SQLSTATE 45000 và gán mã số cùng message rõ ràng.

Ví dụ kiểm tra số lượng:

~~~sql
IF p_quantity IS NULL OR p_quantity = 0 THEN
    SIGNAL SQLSTATE '45000'
        SET MYSQL_ERRNO = 31001,
            MESSAGE_TEXT = 'Quantity must be greater than zero';
END IF;
~~~

Nếu điều kiện sai, các statement phía sau trong block hiện tại không tiếp tục chạy như luồng bình thường. Lỗi được chuyển tới handler phù hợp hoặc trả về caller.

### Có thể dùng condition name

MySQL hỗ trợ khai báo condition có tên để code dễ đọc:

~~~sql
DECLARE invalid_request CONDITION FOR SQLSTATE '45000';
~~~

Condition name chỉ gắn với một SQLSTATE hoặc MySQL error code theo khai báo; nếu cần nhiều mã nghiệp vụ cùng SQLSTATE 45000, ứng dụng vẫn cần đọc MYSQL_ERRNO để phân biệt từng lỗi.

### MESSAGE_TEXT không phải API key

Giữ message ngắn, có thể log và hữu ích cho người vận hành. Nếu ứng dụng cần tham số chi tiết như product_id, nên log ở tầng ứng dụng theo request context hoặc thiết kế output diagnostic riêng có kiểm soát. Không parse message để lấy ID hoặc quyết định retry.

## 4. Chuyển lỗi gốc bằng RESIGNAL

RESIGNAL dùng bên trong handler để phát lại condition đã bắt. Nếu không thay đổi thuộc tính, nó giữ lỗi gốc; nếu cần, có thể đổi SQLSTATE, MYSQL_ERRNO hoặc MESSAGE_TEXT.

Ví dụ chuyển lỗi duplicate key của MySQL thành lỗi nghiệp vụ ổn định:

~~~sql
DECLARE v_mysql_errno INT DEFAULT 0;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET DIAGNOSTICS CONDITION 1
        v_mysql_errno = MYSQL_ERRNO;

    IF v_mysql_errno = 1062 THEN
        RESIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 31003,
                MESSAGE_TEXT = 'Request identifier already exists';
    ELSE
        RESIGNAL;
    END IF;
END;
~~~

1062 là mã lỗi MySQL thường gặp cho duplicate key. Handler đọc mã gốc từ diagnostics area. Nếu đúng lỗi duplicate, routine trả mã nghiệp vụ 31003; các lỗi khác được RESIGNAL nguyên trạng.

Không nên chuyển mọi lỗi thành cùng một mã nghiệp vụ chung. Làm như vậy sẽ che mất deadlock, lỗi kết nối, lỗi quyền hoặc lỗi dữ liệu mà ứng dụng cần xử lý khác nhau.

## 5. GET DIAGNOSTICS để đọc condition

Trong stored program, GET DIAGNOSTICS đọc thông tin từ diagnostics area. Các mục thường dùng gồm:

- RETURNED_SQLSTATE: SQLSTATE của condition.
- MYSQL_ERRNO: mã lỗi số.
- MESSAGE_TEXT: message.
- NUMBER: số condition trong diagnostics area.
- ROW_COUNT: số hàng bị tác động bởi statement gần nhất theo ngữ cảnh diagnostics.

Ví dụ đọc condition đầu tiên trong handler:

~~~sql
DECLARE v_state CHAR(5) DEFAULT '00000';
DECLARE v_errno INT DEFAULT 0;
DECLARE v_message VARCHAR(128) DEFAULT '';

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET DIAGNOSTICS CONDITION 1
        v_state = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;

    -- Có thể dùng các biến này cho quyết định mapping hoặc chẩn đoán.
    RESIGNAL;
END;
~~~

Nếu handler thực hiện thêm statement để ghi log, hãy đọc diagnostics trước khi chạy statement khác vì statement tiếp theo có thể thay đổi diagnostics area. Cũng cần cân nhắc transaction: log được ghi trong cùng transaction có thể bị rollback cùng nghiệp vụ. Trong nhiều hệ thống, log lỗi cuối cùng ở Java/application layer sẽ đáng tin cậy hơn cho việc lưu vết sau rollback.

### Diagnostics area không thay thế error contract

GET DIAGNOSTICS hữu ích cho handler và logging, nhưng caller JDBC vẫn nên nhận một SQLSTATE và mã số ổn định. Đừng bắt ứng dụng gọi thêm một query để đọc biến session nhằm đoán lỗi vừa xảy ra.

## 6. Handler và ranh giới transaction

Handler xác định cách stored program phản ứng với condition. Hai loại thường dùng:

- CONTINUE: xử lý condition rồi tiếp tục statement kế tiếp trong block.
- EXIT: thoát khỏi block có khai báo handler sau khi handler chạy.

Ví dụ NOT FOUND khi đọc một row:

~~~sql
DECLARE v_product_found BOOLEAN DEFAULT TRUE;
DECLARE v_available BIGINT UNSIGNED DEFAULT NULL;

DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_product_found = FALSE;
~~~

Sau SELECT ... INTO, routine kiểm tra cờ và chủ động SIGNAL mã PRODUCT_NOT_FOUND nếu không có hàng.

### Handler không tự động rollback transaction

Đây là quy tắc quan trọng khi kết nối với JDBC. Bắt exception bằng EXIT HANDLER hoặc phát SIGNAL không tự động rollback mọi thay đổi đã thực hiện trước đó. Transaction boundary phải được xác định rõ:

1. Routine tự sở hữu transaction và tự START TRANSACTION/COMMIT/ROLLBACK; hoặc
2. Caller sở hữu transaction, routine tham gia transaction hiện tại và không tự commit/rollback.

Không trộn hai hợp đồng. Bài thực hành bên dưới dùng mô hình caller-owned transaction: Java đặt autoCommit=false, gọi procedure, commit nếu thành công và rollback nếu có SQLException.

Nếu procedure dùng SIGNAL sau khi đã UPDATE một row, ứng dụng phải rollback transaction để các thay đổi trước đó không bị commit dở dang. Đừng giả định RESIGNAL sẽ rollback.

## 7. Ví dụ schema cho routine đặt chỗ tồn kho

Tạo hai bảng InnoDB:

~~~sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    available_qty BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (product_id),
    CONSTRAINT chk_inventory_nonnegative
        CHECK (available_qty >= 0)
) ENGINE=InnoDB;

CREATE TABLE stock_reservations (
    request_id VARCHAR(64) NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (request_id),
    KEY idx_stock_reservations_product (product_id),
    CONSTRAINT fk_stock_reservations_product
        FOREIGN KEY (product_id) REFERENCES inventory(product_id),
    CONSTRAINT chk_stock_reservations_quantity
        CHECK (quantity > 0)
) ENGINE=InnoDB;

INSERT INTO inventory (product_id, available_qty)
VALUES (1001, 20), (1002, 0);
~~~

MySQL chỉ thực thi CHECK constraint từ phiên bản 8.0.16. Nếu môi trường cũ hơn, không dựa vào CHECK để bảo vệ invariant; cần validation trong routine và xác nhận phiên bản server trước khi triển khai schema.

request_id là khóa duy nhất để chống xử lý trùng request. Nếu một request được gửi lại, routine trả lỗi DUPLICATE_REQUEST; hệ thống có thể chọn cách xử lý idempotent riêng bằng cách đọc reservation đã tồn tại và xác nhận payload có giống lần đầu hay không.

## 8. Stored procedure với error code ổn định

Procedure dưới đây kiểm tra input, khóa hàng tồn kho, phát lỗi nghiệp vụ và ánh xạ duplicate key sang mã ổn định. Procedure **không tự quản lý transaction**; caller phải gọi trong transaction InnoDB và commit/rollback.

~~~sql
DELIMITER //

CREATE PROCEDURE reserve_inventory(
    IN p_request_id VARCHAR(64),
    IN p_product_id BIGINT UNSIGNED,
    IN p_quantity BIGINT UNSIGNED
)
BEGIN
    DECLARE v_available BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE v_mysql_errno INT DEFAULT 0;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_not_found = TRUE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            v_mysql_errno = MYSQL_ERRNO;

        IF v_mysql_errno = 1062 THEN
            RESIGNAL SQLSTATE '45000'
                SET MYSQL_ERRNO = 31003,
                    MESSAGE_TEXT = 'Request identifier already exists';
        ELSE
            RESIGNAL;
        END IF;
    END;

    IF p_request_id IS NULL
       OR CHAR_LENGTH(TRIM(p_request_id)) = 0
       OR p_product_id IS NULL
       OR p_quantity IS NULL
       OR p_quantity = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 31001,
                MESSAGE_TEXT = 'Invalid reservation request';
    END IF;

    SET v_not_found = FALSE;

    SELECT available_qty
      INTO v_available
      FROM inventory
     WHERE product_id = p_product_id
     FOR UPDATE;

    IF v_not_found THEN
        SIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 31002,
                MESSAGE_TEXT = 'Product does not exist';
    END IF;

    IF v_available < p_quantity THEN
        SIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 31004,
                MESSAGE_TEXT = 'Insufficient inventory';
    END IF;

    UPDATE inventory
       SET available_qty = available_qty - p_quantity
     WHERE product_id = p_product_id
       AND available_qty >= p_quantity;

    IF ROW_COUNT() <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 31005,
                MESSAGE_TEXT = 'Inventory changed before reservation';
    END IF;

    INSERT INTO stock_reservations (
        request_id,
        product_id,
        quantity
    )
    VALUES (
        p_request_id,
        p_product_id,
        p_quantity
    );
END//

DELIMITER ;
~~~

### Vì sao procedure dùng SELECT ... FOR UPDATE?

SELECT ... FOR UPDATE khóa record tồn kho được tìm thấy cho tới khi transaction kết thúc. Hai transaction cùng đặt chỗ một sản phẩm sẽ không đồng thời đọc rồi ghi dựa trên cùng một giá trị cũ. Transaction đến sau chờ khóa, sau đó kiểm tra lại số lượng hiện tại.

### Vì sao UPDATE vẫn có điều kiện available_qty >= p_quantity?

Điều kiện ở UPDATE là lớp bảo vệ bổ sung. Nếu trạng thái không còn phù hợp, số hàng bị tác động không bằng 1 và routine phát mã INVENTORY_CONFLICT. ROW_COUNT() phải được kiểm tra ngay sau UPDATE vì statement tiếp theo có thể làm thay đổi số liệu này.

### Vì sao lỗi duplicate được chuyển bằng RESIGNAL?

request_id là primary key. Nếu request đã tồn tại, InnoDB phát duplicate-key error 1062. Handler chuyển lỗi constraint đó thành mã nghiệp vụ 31003, để Java không phải phụ thuộc vào tên index hoặc message mặc định của server.

## 9. Quy ước error catalog trong Java

Phía Java nên tập trung mã lỗi vào một nơi, tránh rải số literal trong service và controller.

~~~java
public enum DatabaseErrorCode {
    INVALID_REQUEST(31001),
    PRODUCT_NOT_FOUND(31002),
    DUPLICATE_REQUEST(31003),
    INSUFFICIENT_INVENTORY(31004),
    INVENTORY_CONFLICT(31005);

    private final int vendorCode;

    DatabaseErrorCode(int vendorCode) {
        this.vendorCode = vendorCode;
    }

    public int vendorCode() {
        return vendorCode;
    }

    public static Optional<DatabaseErrorCode> from(SQLException exception) {
        return Arrays.stream(values())
            .filter(code -> code.vendorCode == exception.getErrorCode())
            .findFirst();
    }
}
~~~

Đoạn code cần các import java.sql.SQLException, java.util.Arrays và java.util.Optional. Trong dự án thật, hãy cân nhắc duyệt cả chuỗi SQLException.getNextException() nếu driver/framework gói nhiều lỗi liên quan.

### Ánh xạ lỗi sang hành vi ứng dụng

| Mã | Hành vi ứng dụng thường phù hợp |
|---:|---|
| 31001 | Trả validation error cho caller; không retry tự động. |
| 31002 | Trả not found; không retry nếu dữ liệu không được tạo thêm. |
| 31003 | Xử lý idempotency hoặc conflict theo request ID; không retry cùng payload mù quáng. |
| 31004 | Trả business conflict/insufficient stock; không retry tức thì. |
| 31005 | Có thể đọc lại trạng thái rồi quyết định retry theo policy. |
| 1213 / SQLSTATE class 40 | Deadlock/transaction rollback; thường retry toàn bộ transaction với giới hạn và backoff. |

Mã lỗi ứng dụng không nên trùng lẫn với mã lỗi native MySQL mà ứng dụng cũng xử lý. Nếu routine chỉ phát 45000 cho lỗi nghiệp vụ và giữ nguyên lỗi native khác, Java có thể phân biệt hai nhóm.

## 10. Gọi stored procedure từ JDBC

JDBC dùng CallableStatement để gọi procedure:

~~~java
String sql = "{call reserve_inventory(?, ?, ?)}";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (CallableStatement statement = connection.prepareCall(sql)) {
        statement.setString(1, requestId);
        statement.setLong(2, productId);
        statement.setLong(3, quantity);

        statement.execute();
        connection.commit();
    } catch (SQLException exception) {
        connection.rollback();
        throw exception;
    }
}
~~~

Transaction do Java sở hữu:

1. setAutoCommit(false) để nhiều statement bên trong procedure cùng thuộc transaction caller.
2. CallableStatement.execute() gọi routine.
3. Nếu thành công, Java commit().
4. Nếu procedure phát lỗi, JDBC ném SQLException; Java rollback().
5. Connection được trả về pool sau khi transaction đã kết thúc.

Không bật autocommit cho ví dụ này. Nếu mỗi statement tự commit, SELECT ... FOR UPDATE, UPDATE tồn kho và INSERT reservation không còn được bảo vệ như một đơn vị công việc nguyên tử.

### Không để connection ở trạng thái transaction dở dang

Trong code production, nên khôi phục trạng thái connection trước khi trả về pool. Một helper có thể ghi nhớ originalAutoCommit, rollback nếu có lỗi và khôi phục trạng thái trong finally. Không gọi setAutoCommit(true) trước khi rollback vì JDBC có thể commit transaction hiện tại khi đổi autocommit từ false sang true.

## 11. Kiểm thử mã lỗi từ JDBC

Test tích hợp cần kiểm tra mã số và SQLSTATE, không chỉ kiểm tra exception có xuất hiện. Ví dụ dùng JUnit 5:

~~~java
@Test
void insufficientInventoryReturnsStableDatabaseError() throws Exception {
    try (Connection connection = dataSource.getConnection()) {
        boolean originalAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);

        try {
            SQLException exception;

            try (CallableStatement statement = connection.prepareCall(
                    "{call reserve_inventory(?, ?, ?)}")) {
                statement.setString(1, "req-insufficient-001");
                statement.setLong(2, 1002L); // available_qty = 0
                statement.setLong(3, 1L);

                exception = assertThrows(
                    SQLException.class,
                    () -> statement.execute()
                );
            }

            assertEquals(31004, exception.getErrorCode());
            assertEquals("45000", exception.getSQLState());
        } finally {
            connection.rollback();
            connection.setAutoCommit(originalAutoCommit);
        }
    }
}
~~~

Test này xác nhận:

- Procedure phát đúng mã 31004.
- SQLSTATE trả về là 45000.
- JDBC nhận lỗi qua SQLException.
- Transaction được rollback trong finally, kể cả khi assertion thất bại.

Không nên assert toàn bộ getMessage() vì message có thể thay đổi khi cải thiện chẩn đoán. Nếu message là một phần contract hiển thị cho người dùng, nên kiểm thử riêng ở lớp mapping API và không phụ thuộc câu chữ server.

## 12. Kiểm thử lỗi duplicate và xác nhận rollback

Một lỗi quan trọng là duplicate request xảy ra sau khi routine đã UPDATE inventory. Test phải chứng minh caller rollback sẽ hoàn tác thay đổi tồn kho.

Ví dụ test:

~~~java
@Test
void duplicateRequestRollsBackInventoryChange() throws Exception {
    String requestId = "req-duplicate-001";
    long productId = 1001L;
    long quantity = 2L;

    try (Connection connection = dataSource.getConnection()) {
        boolean originalAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);

        try {
            try (CallableStatement first = connection.prepareCall(
                    "{call reserve_inventory(?, ?, ?)}")) {
                first.setString(1, requestId);
                first.setLong(2, productId);
                first.setLong(3, quantity);
                first.execute();
            }
            connection.commit();

            long beforeRetry = readAvailableQuantity(connection, productId);

            SQLException exception;
            try (CallableStatement retry = connection.prepareCall(
                    "{call reserve_inventory(?, ?, ?)}")) {
                retry.setString(1, requestId);
                retry.setLong(2, productId);
                retry.setLong(3, quantity);

                exception = assertThrows(
                    SQLException.class,
                    () -> retry.execute()
                );
            }

            assertEquals(31003, exception.getErrorCode());
            assertEquals("45000", exception.getSQLState());

            connection.rollback();
            assertEquals(beforeRetry, readAvailableQuantity(connection, productId));
        } finally {
            connection.rollback();
            connection.setAutoCommit(originalAutoCommit);
        }
    }
}
~~~

readAvailableQuantity là helper test thực hiện SELECT available_qty FROM inventory WHERE product_id = ? trên cùng connection. Bởi vì transaction đã rollback trước khi đọc, giá trị phải bằng trạng thái sau lần đặt chỗ đầu tiên. Test này chứng minh lỗi duplicate không để lại UPDATE tồn kho dở dang khi caller tuân thủ hợp đồng rollback.

Nếu retry cùng request ID là một hành vi bình thường, thiết kế idempotency có thể trả lại reservation cũ thay vì báo duplicate. Khi đó cần kiểm tra payload cũ và payload mới có tương đương không; cùng request ID nhưng khác product/quantity phải được coi là conflict.

## 13. Kiểm thử success path và trạng thái dữ liệu

Không chỉ kiểm thử lỗi. Success path cần xác nhận cả kết quả và side effect:

~~~java
@Test
void reservationDecreasesInventoryAndCreatesReservation() throws Exception {
    String requestId = "req-success-001";
    long productId = 1001L;
    long quantity = 3L;

    try (Connection connection = dataSource.getConnection()) {
        boolean originalAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);

        try {
            long before = readAvailableQuantity(connection, productId);

            try (CallableStatement statement = connection.prepareCall(
                    "{call reserve_inventory(?, ?, ?)}")) {
                statement.setString(1, requestId);
                statement.setLong(2, productId);
                statement.setLong(3, quantity);
                statement.execute();
            }

            long after = readAvailableQuantity(connection, productId);
            assertEquals(before - quantity, after);
            assertEquals(1, countReservations(connection, requestId));

            connection.commit();
        } finally {
            connection.rollback();
            connection.setAutoCommit(originalAutoCommit);
        }
    }
}
~~~

Trong test dùng database riêng, quyết định commit hay rollback tùy chiến lược fixture. Ví dụ trên minh họa success path và commit; finally rollback là cleanup an toàn nếu assertion hoặc statement lỗi trước commit. Sau commit thành công, rollback không đảo ngược dữ liệu đã commit.

Helper countReservations kiểm tra số reservation theo request ID. Không chỉ kiểm tra số dư tồn kho vì có thể số dư đúng nhưng reservation record bị thiếu hoặc bị ghi trùng.

## 14. Test matrix cho error contract

Một test suite nên bao phủ cả lỗi đầu vào, lỗi dữ liệu, lỗi cạnh tranh và lỗi native:

| Scenario | Cách kích hoạt | Kết quả mong đợi |
|---|---|---|
| Request ID rỗng | Truyền chuỗi rỗng | MYSQL_ERRNO=31001, SQLSTATE 45000, không thay đổi dữ liệu. |
| Product ID không tồn tại | Truyền ID không có trong inventory | 31002, không tạo reservation. |
| Duplicate request ID | Gọi lại cùng request ID đã commit | 31003; caller rollback và số tồn kho không giảm lần hai. |
| Tồn kho không đủ | Yêu cầu nhiều hơn available quantity | 31004, không tạo reservation. |
| Conflict khi UPDATE | Điều kiện cập nhật không còn đúng | 31005. |
| Thành công | Số lượng hợp lệ và request mới | Có đúng một reservation; tồn kho giảm đúng số lượng. |
| Deadlock | Tạo hai transaction khóa nhiều sản phẩm theo thứ tự đối nghịch trong test riêng | Lỗi native deadlock/SQLSTATE class 40; retry toàn transaction theo policy. |
| Connection failure | Ngắt kết nối trong lúc gọi | Không giả định transaction đã commit; xác minh trạng thái bằng request ID trước khi retry. |

Mỗi test phải bắt đầu từ fixture xác định. Dọn dữ liệu theo thứ tự phù hợp với foreign key và không dùng chung request ID giữa các test song song.

## 15. Kiểm thử concurrency với hai connection

Kiểm thử đơn luồng không chứng minh routine an toàn trước race condition. Với tồn kho, hãy tạo hai connection cùng đặt số lượng lớn hơn tổng lượng còn lại.

Ví dụ kịch bản:

~~~text
Initial inventory: product 1001 has 5 units

Connection A                         Connection B
-------------                         -------------
BEGIN                                 BEGIN
CALL reserve(..., 4)                  CALL reserve(..., 4)
SELECT ... FOR UPDATE                 waits for row lock
UPDATE available_qty = 1
INSERT reservation
COMMIT
                                      obtains lock
                                      reads available_qty = 1
                                      SIGNAL 31004
                                      ROLLBACK

Expected final state:
- One committed reservation for 4 units
- available_qty = 1
- The other call returns error 31004
~~~

Test cần dùng hai connection riêng và barrier/latch để điều phối thời điểm bắt đầu. Không dùng một connection cho cả hai thread vì transaction và session state thuộc connection.

Ngoài mã lỗi, kiểm tra invariant cuối cùng:

~~~text
initial_quantity
= final_available_quantity
  + SUM(committed reservation quantity)
~~~

Invariant phải đúng sau khi tất cả transaction kết thúc. Nếu cả hai request cùng thành công và làm số dư âm hoặc tổng reservation vượt lượng ban đầu, routine hoặc transaction contract chưa an toàn.

## 16. Phân biệt lỗi nghiệp vụ, lỗi dữ liệu và lỗi hạ tầng

Không phải lỗi nào cũng nên chuyển thành mã nghiệp vụ tùy chỉnh.

| Nhóm | Ví dụ | Hành vi gợi ý |
|---|---|---|
| Validation/business | Quantity bằng 0, không đủ tồn kho | Mã nghiệp vụ ổn định; không retry tự động. |
| Missing resource | Product không tồn tại | Mã not-found; phản hồi phù hợp API. |
| Conflict/idempotency | Request ID trùng, trạng thái đã đổi | Mã conflict hoặc trả kết quả cũ theo chính sách idempotency. |
| Constraint/data integrity | Foreign key, unique key không được ánh xạ | Giữ native code hoặc ánh xạ có chủ đích nếu ý nghĩa ổn định. |
| Concurrency | Deadlock, lock wait timeout | Phân biệt deadlock với timeout; retry có giới hạn nếu transaction có thể chạy lại an toàn. |
| Infrastructure | Connection lost, server unavailable, disk full | Giữ thông tin lỗi gốc; không biến thành validation error. |
| Programming/schema | Unknown column, syntax error, missing table | Cảnh báo triển khai/code; không trả như lỗi người dùng nhập sai. |

Đặc biệt, connection loss trong lúc COMMIT có thể tạo trạng thái không xác định ở phía client: server có thể đã commit nhưng response bị mất. Không retry một thao tác ghi một cách mù quáng. Dùng request ID/idempotency key để truy vấn trạng thái đã ghi trước khi quyết định thực hiện lại.

## 17. Kiểm thử JDBC: các chi tiết cần chú ý

### getErrorCode và getSQLState

Với SQLException:

~~~java
int vendorCode = exception.getErrorCode();
String sqlState = exception.getSQLState();
String diagnosticMessage = exception.getMessage();
~~~

- vendorCode là mã lỗi phía database/driver, dùng đối chiếu error catalog.
- sqlState là mã SQLSTATE 5 ký tự.
- diagnosticMessage dùng cho log/chẩn đoán; không parse để điều khiển nghiệp vụ.

### SQLException có thể được chain hoặc wrap

JDBC cho phép một SQLException chứa lỗi tiếp theo qua getNextException(). Framework cũng có thể wrap exception vào một exception cấp cao hơn. Khi kiểm thử raw JDBC, assert trực tiếp exception từ CallableStatement. Khi kiểm thử qua framework, đi qua cause chain hoặc API exception translation để tìm SQL exception gốc.

Ví dụ duyệt cause chain:

~~~java
static SQLException findSqlException(Throwable error) {
    Throwable current = error;

    while (current != null) {
        if (current instanceof SQLException sqlException) {
            return sqlException;
        }
        current = current.getCause();
    }

    return null;
}
~~~

Nếu driver dùng getNextException(), hãy duyệt thêm chuỗi này. Không giả định exception luôn nằm ở getCause() đầu tiên.

### Không assert exception subclass nếu không cần

Driver có thể ánh xạ SQLSTATE class sang các subclass JDBC như SQLIntegrityConstraintViolationException hoặc SQLTransactionRollbackException. Với SQLSTATE 45000, loại exception cụ thể phụ thuộc driver. Hợp đồng ổn định của bài này là vendor code và SQLSTATE; chỉ assert subclass khi ứng dụng chủ động dựa vào mapping đó và đã khóa phiên bản driver.

### CallableStatement và result set

Nếu procedure trả result set trước khi phát lỗi ở một statement sau, driver có thể đã nhận một phần kết quả trước exception. API nên quy định rõ routine trả result set hay chỉ thực hiện command. Test cần xử lý execute(), getResultSet() và getMoreResults() nếu procedure có nhiều result set; không giả định mọi CALL chỉ có một update count.

## 18. Quản lý transaction trong test

Với caller-owned transaction:

- Bắt đầu bằng connection.setAutoCommit(false).
- Gọi procedure bằng cùng connection.
- Commit khi toàn bộ nghiệp vụ thành công.
- Rollback khi nhận exception hoặc assertion thất bại.
- Khôi phục trạng thái connection trước khi trả về pool.

Không dùng một connection đang có transaction chưa kết thúc cho test khác. Trong test parallel, mỗi test nên có connection riêng và fixture cô lập.

### Test lỗi phải xác nhận trạng thái sau rollback

Một test chỉ assert SQLException là chưa đủ. Cần xác nhận:

1. Đúng vendor error code.
2. Đúng SQLSTATE.
3. Caller rollback thành công.
4. Số dư và reservation không thay đổi ngoài dự kiến.
5. Không có transaction/connection bị bỏ quên.

### Test deadlock và retry

Deadlock là lỗi transaction-level, không phải lỗi nghiệp vụ như insufficient inventory. Nếu retry, phải chạy lại toàn transaction từ đầu, có giới hạn số lần và backoff. Không chỉ chạy lại statement cuối vì các statement trước có thể đã bị rollback cùng transaction.

## 19. Versioning và vận hành error catalog

Mã lỗi là một phần contract giữa database và application. Khi thêm hoặc thay đổi:

1. Đăng ký mã mới trong error catalog.
2. Giữ nguyên ý nghĩa mã đã phát hành.
3. Cập nhật stored procedure và Java enum trong cùng release hoặc theo thứ tự tương thích.
4. Viết integration test xác nhận mã và SQLSTATE.
5. Ghi mapping sang HTTP/API error nếu ứng dụng có REST layer.
6. Log mã lỗi, routine name, request/correlation ID và transaction outcome.
7. Không log dữ liệu nhạy cảm hoặc nguyên chuỗi SQL chứa thông tin người dùng.

Nếu Java được triển khai trước database, Java cần xử lý được cả mã cũ và mã mới chưa phát sinh. Nếu database được triển khai trước Java, routine không nên phát mã mới mà application cũ không hiểu nếu điều đó làm sai hành vi. Có thể dùng rollout tương thích hai pha.

## 20. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Parse MESSAGE_TEXT | Thay đổi câu chữ làm hỏng logic | Phân loại bằng MYSQL_ERRNO và SQLSTATE. |
| Dùng một mã cho mọi exception | Mất khả năng phân biệt validation, conflict và hạ tầng | Duy trì error catalog có namespace. |
| Đổi ý nghĩa mã đã công bố | Client cũ xử lý sai lỗi mới | Không tái sử dụng mã; version hóa contract. |
| Nuốt exception trong handler | Caller tưởng routine thành công | Dùng RESIGNAL khi lỗi cần trả về caller. |
| Nghĩ handler tự rollback | Dữ liệu có thể bị commit dở dang | Xác định transaction owner và rollback đúng nơi. |
| Chỉ assert exception có xuất hiện | Không biết routine trả mã nào | Assert getErrorCode() và getSQLState(). |
| Assert message nguyên văn | Test dễ vỡ khi sửa câu chữ | Chỉ kiểm tra message khi nó là yêu cầu hiển thị cụ thể. |
| Retry mọi SQLException | Lặp lại lỗi validation hoặc thao tác không idempotent | Retry theo mã/SQLSTATE và transaction semantics. |
| Retry sau connection loss mà không kiểm tra | Có thể tạo giao dịch trùng nếu commit đã thành công | Dùng request ID và kiểm tra trạng thái trước retry. |
| Test trên một connection cho concurrency | Không tạo được race condition thật | Dùng ít nhất hai connection độc lập. |
| Chỉ kiểm tra số dư sau success | Bỏ sót reservation thiếu/trùng | Kiểm tra cả row set và invariant tổng. |

## 21. Quy trình thiết kế và kiểm thử lỗi

1. Liệt kê lỗi nghiệp vụ và lỗi kỹ thuật mà routine có thể phát ra.
2. Phân loại lỗi nào là validation, not-found, conflict, concurrency hoặc infrastructure.
3. Gán MYSQL_ERRNO ổn định và chọn SQLSTATE phù hợp.
4. Phát lỗi nghiệp vụ bằng SIGNAL SQLSTATE '45000'.
5. Dùng GET DIAGNOSTICS để đọc lỗi gốc trong handler khi cần mapping.
6. Dùng RESIGNAL để giữ lỗi gốc hoặc chuyển lỗi native có chủ đích.
7. Xác định transaction owner; không để handler rollback nhầm transaction của caller.
8. Viết Java error catalog ánh xạ vendor code.
9. Gọi procedure qua CallableStatement với transaction boundary rõ ràng.
10. Assert vendor code và SQLSTATE trong integration test.
11. Rollback và kiểm tra trạng thái dữ liệu sau lỗi.
12. Test success, duplicate, not-found, invalid input, insufficient inventory và concurrency.
13. Test connection loss/deadlock theo retry policy riêng.
14. Version hóa catalog và triển khai database/application theo thứ tự tương thích.

## 22. Bài tập thực hành

### Bài tập A — Thiết kế error catalog

1. Liệt kê ít nhất năm lỗi nghiệp vụ của một routine đặt hàng.
2. Gán mỗi lỗi một MYSQL_ERRNO không trùng.
3. Dùng SQLSTATE 45000 cho lỗi chủ động do routine phát ra.
4. Viết Java enum tương ứng.
5. Xác định hành vi retry cho từng mã.

### Bài tập B — SIGNAL và RESIGNAL

1. Viết procedure phát lỗi khi quantity bằng 0.
2. Dùng SIGNAL với mã 31001.
3. Tạo unique constraint để có thể phát sinh lỗi 1062.
4. Dùng GET DIAGNOSTICS đọc MYSQL_ERRNO.
5. Dùng RESIGNAL chuyển 1062 thành 31003.

### Bài tập C — Gọi lỗi qua JDBC

1. Gọi procedure bằng CallableStatement.
2. Bắt SQLException.
3. Assert getErrorCode() và getSQLState().
4. Không assert message nguyên văn.
5. Ghi mã lỗi và request ID vào log test.

### Bài tập D — Transaction rollback

1. Đặt autoCommit=false.
2. Gọi procedure có UPDATE trước khi INSERT bị duplicate.
3. Bắt exception và rollback.
4. Đọc lại tồn kho và reservation.
5. Chứng minh không có thay đổi dở dang.

### Bài tập E — Concurrency

1. Tạo fixture có 5 đơn vị tồn kho.
2. Mở hai JDBC connection.
3. Đồng thời đặt mỗi request 4 đơn vị.
4. Xác nhận chỉ một transaction thành công.
5. Xác nhận transaction còn lại nhận mã insufficient inventory và invariant tổng vẫn đúng.

### Bài tập F — Compatibility test

1. Thêm mã lỗi mới vào routine và Java enum.
2. Chạy test với application version cũ và mới trong môi trường staging.
3. Kiểm tra client cũ không hiểu sai mã chưa biết.
4. Kiểm tra log có correlation ID và mã lỗi.
5. Viết migration/release note cho thay đổi error contract.

Bạn hoàn thành bài khi có thể thiết kế mã lỗi không phụ thuộc message, phát và chuyển lỗi bằng SIGNAL/RESIGNAL, đọc diagnostics, gọi procedure từ JDBC, kiểm tra vendor code/SQLSTATE và chứng minh transaction không để lại dữ liệu dở dang sau lỗi.

## 23. Nguyên tắc cần ghi nhớ

- MYSQL_ERRNO là mã số phù hợp để phân loại lỗi nghiệp vụ ổn định; quản lý nó như API contract.
- SQLSTATE phân loại nhóm lỗi; 45000 thường dùng cho exception do routine chủ động phát ra.
- MESSAGE_TEXT phục vụ chẩn đoán, không dùng làm khóa điều khiển nghiệp vụ.
- Dùng SIGNAL để phát lỗi có mã rõ ràng; dùng RESIGNAL để giữ hoặc chuyển lỗi trong handler.
- GET DIAGNOSTICS đọc SQLSTATE, MYSQL_ERRNO và MESSAGE_TEXT của condition.
- Handler không tự động rollback transaction; phải xác định caller hay routine sở hữu transaction.
- Với caller-owned transaction, JDBC phải rollback khi procedure phát lỗi.
- Kiểm thử qua CallableStatement và assert SQLException.getErrorCode() cùng getSQLState().
- Không retry mọi SQLException; phân loại validation, conflict, deadlock và connection failure.
- Kiểm tra trạng thái dữ liệu sau rollback, không chỉ kiểm tra exception.
- Dùng request ID/idempotency key để xử lý retry an toàn khi response bị mất.
- Kiểm thử concurrency bằng nhiều connection và xác nhận invariant nghiệp vụ.
- Không tái sử dụng mã lỗi đã phát hành; version hóa contract giữa stored program và Java.

Khi mã lỗi, SQLSTATE, transaction boundary và JDBC test được thiết kế như một hợp đồng thống nhất, stored procedure có thể trả lỗi rõ ràng và ổn định. Ứng dụng Java sẽ xử lý đúng nguyên nhân, kiểm soát retry và chứng minh dữ liệu vẫn nhất quán sau cả thành công lẫn thất bại.
