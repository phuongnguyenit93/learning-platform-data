# Trả nhiều tập kết quả và hợp đồng gọi từ ứng dụng

Stored procedure của MySQL có thể trả nhiều result set trong một lần gọi `CALL`. Mỗi câu `SELECT` trong procedure mà không dùng `INTO` để gán biến sẽ gửi một tập kết quả tới client. Cách này hữu ích khi một thao tác nghiệp vụ cần trả đồng thời phần tổng quan và danh sách chi tiết, hoặc cần trả nhiều nhóm dữ liệu liên quan mà không bắt ứng dụng gửi nhiều request riêng.

Khi procedure trở thành API cho ứng dụng, thứ tự result set, tên cột, kiểu dữ liệu, ý nghĩa `NULL`, quy tắc lọc, tham số vào/ra và cách xử lý lỗi đều là một phần của hợp đồng. Ứng dụng phải đọc hết các kết quả theo đúng thứ tự và xử lý cả update count hoặc lỗi phát sinh giữa các result set. Nếu procedure thêm một câu `SELECT` debug hoặc đổi thứ tự hai SELECT, code client có thể đọc nhầm dữ liệu dù câu lệnh SQL vẫn chạy thành công.

Bài học thuộc module `DATABASE_MYSQL`, tập trung vào thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là thiết kế stored procedure trả nhiều tập kết quả có cấu trúc ổn định và gọi nó an toàn từ ứng dụng, đặc biệt với Java/JDBC.

Sau bài học, bạn có thể:

- Phân biệt result set được gửi tới client với giá trị trả qua `OUT`/`INOUT` parameter.
- Tạo procedure trả summary và detail trong cùng một lệnh `CALL`.
- Giải thích thứ tự result set và metadata cột là một phần của API contract.
- Phân biệt `SELECT` thông thường với `SELECT ... INTO` trong stored program.
- Dùng `CallableStatement.execute()` và `getMoreResults()` để đọc tất cả kết quả.
- Xử lý update count, result set rỗng và lỗi phát sinh giữa chừng.
- Quy định transaction, quyền thực thi và tính nhất quán dữ liệu cho lời gọi.
- Thiết kế versioning, kiểm thử contract và tránh phá vỡ client cũ.

## 1. Một CALL có thể trả nhiều result set

Một stored procedure có thể chứa nhiều câu SELECT trả dữ liệu:

Trong ví dụ, `DELIMITER` là lệnh của MySQL command-line client để đổi ký tự kết thúc statement khi nhập phần thân procedure có dấu `;`. Nó không phải câu lệnh SQL gửi tới server; với migration tool hoặc driver, hãy dùng cách gửi toàn bộ câu `CREATE PROCEDURE` theo API của công cụ đó.

```sql
DELIMITER //

CREATE PROCEDURE sp_demo_multiple_results(IN p_customer_id BIGINT UNSIGNED)
BEGIN
    SELECT customer_id, customer_name
    FROM customers
    WHERE customer_id = p_customer_id;

    SELECT order_id, order_date, total_amount
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_date DESC, order_id DESC;
END//

DELIMITER ;
```

Gọi procedure:

```sql
CALL sp_demo_multiple_results(42);
```

Client nhận lần lượt:

1. Result set thứ nhất: thông tin khách hàng.
2. Result set thứ hai: danh sách đơn hàng.

Nếu khách hàng tồn tại nhưng chưa có đơn hàng, result set thứ hai vẫn tồn tại về mặt cấu trúc nhưng có 0 hàng. Đây khác với việc procedure không phát ra result set thứ hai. Ứng dụng cần phân biệt “result set rỗng” với “không có result set ở vị trí mong đợi”.

`CALL` là một statement có thể tạo nhiều kết quả. Client/server protocol và driver cần hỗ trợ multiple results. Connector/J hỗ trợ đọc các result set của stored procedure qua JDBC; không cần bật tùy chọn cho phép nhiều statement phân tách bằng dấu chấm phẩy chỉ vì procedure trả nhiều result set.

## 2. SELECT trả result set và SELECT ... INTO không trả result set

Trong stored procedure, câu SELECT thông thường gửi dữ liệu về client:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = p_customer_id;
```

Trong khi đó, `SELECT ... INTO` lấy giá trị gán cho biến local hoặc biến đã khai báo phù hợp; nó không gửi một result set dữ liệu tới client:

```sql
BEGIN
    DECLARE v_order_count BIGINT UNSIGNED DEFAULT 0;

    SELECT COUNT(*)
    INTO v_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END;
```

Đoạn trên là phần thân của một procedure có tham số `IN p_customer_id`. Trong cùng khối `BEGIN ... END`, có thể dùng biến local đó ở một result set sau:

```sql
SELECT
    p_customer_id AS customer_id,
    v_order_count AS order_count;
```

Phân biệt này rất quan trọng khi thiết kế contract. Một SELECT dùng để tính toán nội bộ không nên vô tình trở thành result set thứ nhất mà client phải đọc. Nếu không muốn trả dữ liệu, dùng `SELECT ... INTO`, `SET` hoặc câu lệnh phù hợp.

## 3. Thiết kế một procedure trả summary và detail

Ví dụ dưới đây dùng bảng đơn hàng giả định với các cột `order_id`, `customer_id`, `order_date`, `order_status` và `total_amount`.

```sql
DELIMITER //

CREATE PROCEDURE sp_customer_order_report(
    IN p_customer_id BIGINT UNSIGNED,
    IN p_from_date DATE,
    IN p_to_date DATE
)
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    IF p_from_date IS NULL
       OR p_to_date IS NULL
       OR p_from_date >= p_to_date THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid reporting date range';
    END IF;

    -- Result set 1: summary, luôn trả đúng một hàng.
    SELECT
        p_customer_id AS customer_id,
        p_from_date AS period_start,
        p_to_date AS period_end_exclusive,
        COUNT(*) AS order_count,
        COALESCE(
            SUM(CASE WHEN order_status = 'PAID'
                     THEN total_amount ELSE 0 END),
            0
        ) AS paid_total
    FROM orders
    WHERE customer_id = p_customer_id
      AND order_date >= p_from_date
      AND order_date < p_to_date;

    -- Result set 2: detail, có thể chứa 0 hoặc nhiều hàng.
    SELECT
        order_id,
        order_date,
        order_status,
        total_amount
    FROM orders
    WHERE customer_id = p_customer_id
      AND order_date >= p_from_date
      AND order_date < p_to_date
    ORDER BY order_date DESC, order_id DESC;
END//

DELIMITER ;
```

Gọi:

```sql
CALL sp_customer_order_report(42, '2026-11-01', '2026-12-01');
```

Khoảng ngày dùng dạng nửa mở: `>= p_from_date` và `< p_to_date`. Vì vậy, ngày kết thúc không bị tính hai lần khi các kỳ báo cáo liền nhau.

### 3.1. Hợp đồng result set của ví dụ

| Thứ tự | Tên logic | Cột theo thứ tự | Cardinality |
| --- | --- | --- | --- |
| 1 | `customer_summary` | `customer_id`, `period_start`, `period_end_exclusive`, `order_count`, `paid_total` | Luôn 1 hàng vì aggregate không có GROUP BY |
| 2 | `order_details` | `order_id`, `order_date`, `order_status`, `total_amount` | 0..N hàng |

Result set thứ nhất dùng aggregate không có GROUP BY nên trả một hàng kể cả khi không có đơn phù hợp. `COUNT(*)` khi không có hàng là 0; `SUM` sẽ là NULL nên được chuẩn hóa về 0 bằng `COALESCE`. Result set thứ hai vẫn được phát ra với metadata cột đầy đủ nhưng có thể không có hàng.

Ứng dụng không nên suy ra ý nghĩa result set chỉ từ số hàng. Hãy dựa vào vị trí và contract đã công bố.

## 4. Thứ tự và metadata là một phần của API contract

Khi ứng dụng gọi procedure, result set thứ nhất không có tên logic được truyền riêng qua protocol theo cách một API JSON thường làm. Client thường nhận các result set theo thứ tự phát ra. Vì vậy, thứ tự SELECT trong procedure là một phần của giao diện.

Contract nên ghi rõ cho từng result set:

- Số thứ tự và tên logic do tài liệu API đặt.
- Tên cột và thứ tự cột.
- Kiểu dữ liệu MySQL/JDBC và khả năng NULL.
- Ý nghĩa của mỗi cột, đơn vị tiền tệ/thời gian và timezone nếu có.
- Cardinality: 0..1, đúng 1, 0..N hoặc 1..N.
- Quy tắc sắp xếp, lọc và phân trang.
- Điều kiện khiến result set có thể rỗng.
- Phiên bản contract và chính sách tương thích.

Ví dụ bảng contract:

| Result set | Cột | Kiểu dự kiến | Nullable | Ý nghĩa |
| --- | --- | --- | --- | --- |
| 1 | `customer_id` | BIGINT UNSIGNED | Không | Khóa khách hàng được yêu cầu |
| 1 | `order_count` | BIGINT | Không | Số đơn trong kỳ |
| 1 | `paid_total` | DECIMAL(14,2) | Không | Tổng tiền đơn PAID, đơn vị theo quy ước hệ thống |
| 2 | `order_id` | BIGINT UNSIGNED | Không | Mã đơn |
| 2 | `order_date` | DATE | Không | Ngày đơn |
| 2 | `order_status` | VARCHAR(20) | Không | Trạng thái nghiệp vụ |
| 2 | `total_amount` | DECIMAL(12,2) | Không | Tổng tiền của đơn |

Đặt alias tường minh để tên cột không thay đổi bất ngờ khi biểu thức SQL được chỉnh sửa. Tránh `SELECT *` trong procedure công khai: thêm một cột vào bảng nguồn có thể làm thay đổi metadata result set và phá client đang đọc theo vị trí.

## 5. Result set rỗng, không có result set và NULL

Ba trường hợp này khác nhau:

1. **Result set có 0 hàng:** procedure đã chạy SELECT; metadata cột vẫn được gửi, nhưng không có record nào.
2. **Không có result set:** statement hiện tại không tạo tập kết quả, ví dụ procedure chỉ chạy UPDATE hoặc SELECT ... INTO.
3. **Result set có hàng chứa NULL:** có record, nhưng một hoặc nhiều giá trị trong record là NULL.

Client phải xử lý đúng từng trường hợp. Ví dụ, không tìm thấy đơn hàng có thể được biểu diễn bằng result set detail rỗng, trong khi summary vẫn có một hàng với `order_count = 0` và `paid_total = 0`.

Không dùng một result set bất ngờ chỉ để trả thông báo debug. Nếu cần status nghiệp vụ, đưa status vào summary result set hoặc OUT parameter đã được định nghĩa trong contract.

## 6. OUT và INOUT parameter là kênh dữ liệu riêng

Stored procedure có thể trả dữ liệu bằng result set, `OUT` parameter hoặc `INOUT` parameter. Đây là các cơ chế riêng biệt:

- Result set phù hợp với 0..N hàng và nhiều cột.
- OUT parameter phù hợp với một giá trị đầu ra có tên và kiểu đã biết.
- INOUT parameter nhận giá trị đầu vào và trả giá trị đã cập nhật.

Ví dụ procedure dùng OUT parameter:

```sql
DELIMITER //

CREATE PROCEDURE sp_count_customer_orders(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count BIGINT UNSIGNED
)
READS SQL DATA
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
```

Gọi từ SQL client:

```sql
CALL sp_count_customer_orders(42, @order_count);
SELECT @order_count AS order_count;
```

Biến `@order_count` là user-defined session variable của kết nối hiện tại. Trong JDBC, đăng ký OUT parameter trên `CallableStatement` thay vì tự quản lý user variable nếu driver hỗ trợ callable parameter mapping.

Không nên trả cùng một thông tin qua cả result set và OUT parameter trừ khi có lý do tương thích rõ ràng. Hai nguồn giá trị trùng nhau làm contract phức tạp và có thể lệch nếu procedure thay đổi một bên.

## 7. Gọi procedure trả nhiều result set bằng Java JDBC

Với JDBC, dùng `CallableStatement` và `execute()` để gọi procedure có thể trả nhiều loại kết quả. Không dùng `executeQuery()` nếu procedure có nhiều result set hoặc có thể xen kẽ update count.

Ví dụ xử lý result set theo thứ tự:

```java
String sql = "{call sp_customer_order_report(?, ?, ?)}";

try (CallableStatement call = connection.prepareCall(sql)) {
    call.setLong(1, customerId);
    call.setDate(2, java.sql.Date.valueOf(fromDate));
    call.setDate(3, java.sql.Date.valueOf(toDate));

    boolean hasResultSet = call.execute();
    int resultSetNumber = 0;

    while (true) {
        if (hasResultSet) {
            resultSetNumber++;

            try (ResultSet rs = call.getResultSet()) {
                if (resultSetNumber == 1) {
                    while (rs.next()) {
                        long id = rs.getLong("customer_id");
                        long count = rs.getLong("order_count");
                        BigDecimal paidTotal = rs.getBigDecimal("paid_total");
                        // Map thành CustomerSummary.
                    }
                } else if (resultSetNumber == 2) {
                    while (rs.next()) {
                        long orderId = rs.getLong("order_id");
                        java.sql.Date orderDate = rs.getDate("order_date");
                        String status = rs.getString("order_status");
                        BigDecimal amount = rs.getBigDecimal("total_amount");
                        // Map thành OrderDetail.
                    }
                } else {
                    throw new SQLException("Unexpected result set: " + resultSetNumber);
                }
            }
        } else {
            int updateCount = call.getUpdateCount();
            if (updateCount == -1) {
                break; // Không còn result set hoặc update count.
            }
            // Xử lý hoặc ghi log update count nếu contract có quy định.
        }

        hasResultSet = call.getMoreResults(Statement.CLOSE_CURRENT_RESULT);
    }

    if (resultSetNumber != 2) {
        throw new SQLException("Expected 2 result sets, got " + resultSetNumber);
    }
}
```

Vòng lặp xử lý cả hai dạng kết quả:

- `hasResultSet == true`: lấy `ResultSet` hiện tại và đọc hết hàng.
- `hasResultSet == false`: kiểm tra `getUpdateCount()`. Giá trị `-1` cho biết không còn kết quả.

`getMoreResults(Statement.CLOSE_CURRENT_RESULT)` chuyển tới kết quả tiếp theo và đóng result set hiện tại. Ví dụ trên dùng tên cột để mapping để dễ đọc; contract vẫn cần giữ metadata ổn định. Nếu xử lý theo index, thay đổi thứ tự cột có thể làm client đọc sai dữ liệu mà không có lỗi kiểu.

### 7.1. Không dừng sau result set đầu tiên

Một lỗi phổ biến là gọi `execute()`, lấy `getResultSet()` rồi đóng `CallableStatement` ngay sau khi đọc summary. Khi đó detail result set chưa được tiêu thụ. Tùy driver và cách connection được quản lý, việc bỏ dở kết quả có thể làm statement/connection không sẵn sàng cho câu tiếp theo hoặc gây tốn tài nguyên.

Luôn duyệt hết result sets và update counts theo contract trước khi trả connection về pool. Nếu ứng dụng không cần detail, vẫn phải tiêu thụ hoặc đóng các kết quả còn lại theo API của driver.

### 7.2. Phân biệt nhiều result set với nhiều statement

Một procedure có nhiều SELECT trả nhiều result set qua một `CALL`. Đây không đồng nghĩa client gửi một chuỗi nhiều statement như `SELECT ...; SELECT ...;`. Cấu hình driver cho phép multi-query thường kiểm soát việc gửi nhiều statement riêng trong một request; không bật tùy chọn đó chỉ vì procedure trả nhiều result set.

## 8. Đọc OUT parameter bằng JDBC

Ví dụ:

```java
try (CallableStatement call = connection.prepareCall(
        "{call sp_count_customer_orders(?, ?)}")) {
    call.setLong(1, customerId);
    call.registerOutParameter(2, Types.BIGINT);

    call.execute();

    long orderCount = call.getLong(2);
    if (call.wasNull()) {
        // Xử lý NULL nếu contract cho phép.
    }
}
```

Với procedure có cả result sets và OUT parameters, đăng ký OUT parameter trước khi execute. Đọc và tiêu thụ các result sets theo hướng dẫn driver; sau đó lấy OUT value khi driver bảo đảm đã hoàn tất xử lý kết quả. Kiểm thử hành vi với đúng phiên bản MySQL Connector/J mà ứng dụng triển khai.

Kiểu SQL và JDBC phải tương thích. Ví dụ `BIGINT UNSIGNED` có miền lớn hơn `BIGINT` signed của Java `long`; nếu giá trị có thể vượt `Long.MAX_VALUE`, cần mapping sang `BigInteger` hoặc kiểu phù hợp thay vì giả định `getLong()` luôn an toàn.

## 9. Update count và các statement không trả hàng

Stored procedure có thể xen kẽ SELECT với INSERT/UPDATE/DELETE:

```sql
DELIMITER //

CREATE PROCEDURE sp_refresh_customer_flag(IN p_customer_id BIGINT UNSIGNED)
MODIFIES SQL DATA
BEGIN
    UPDATE customers
    SET has_recent_order = EXISTS (
        SELECT 1
        FROM orders
        WHERE customer_id = p_customer_id
          AND order_date >= CURRENT_DATE - INTERVAL 30 DAY
    )
    WHERE customer_id = p_customer_id;

    SELECT customer_id, has_recent_order
    FROM customers
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
```

Driver có thể báo update count giữa các result sets. Client không được giả định mọi lần `getMoreResults()` đều trả true. Cần duyệt trạng thái kết quả theo mẫu vòng lặp và không bỏ qua update count nếu nó là một phần của contract.

Nếu ứng dụng chỉ cần kết quả cuối cùng, cân nhắc thiết kế procedure sao cho các statement DML nội bộ không tạo output không cần thiết; đồng thời kiểm thử hành vi update count thực tế với driver.

## 10. Lỗi và kết quả một phần

Giả sử procedure thực hiện:

1. SELECT summary.
2. SELECT detail.
3. Thực hiện một thao tác khác có thể phát sinh lỗi.

Nếu lỗi xảy ra sau khi một result set đã được gửi, client có thể đã đọc được dữ liệu một phần trước khi nhận exception. Ứng dụng không nên coi một phần payload là phản hồi thành công đầy đủ.

Hợp đồng lỗi nên quy định:

- SQLSTATE/error code được dùng cho lỗi đầu vào, lỗi nghiệp vụ và lỗi hệ thống.
- Procedure có `SIGNAL`/`RESIGNAL` hay trả status result set cho trường hợp nghiệp vụ nào.
- Client phải bỏ toàn bộ payload nếu lời gọi kết thúc bằng SQLException.
- Có retry hay không, và retry có an toàn/idempotent hay không.
- Transaction được rollback ở đâu nếu procedure có thay đổi dữ liệu.

Ví dụ lỗi đầu vào:

```sql
IF p_customer_id IS NULL THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'customer_id is required';
END IF;
```

Không nên trộn hai kiểu báo lỗi mà không có quy ước. Lỗi kỹ thuật thường nên được ném thành exception để ứng dụng xử lý; kết quả nghiệp vụ như “không có đơn hàng” thường phù hợp với result set rỗng hoặc status field đã định nghĩa.

## 11. Transaction và tính nhất quán giữa các result set

Nhiều result set có thể được đọc ở các thời điểm khác nhau nếu transaction boundary không được xác định rõ. Ví dụ summary được tính trước, sau đó một transaction khác thêm đơn hàng, rồi detail được đọc sau đó. Nếu hai SELECT không cùng một consistent snapshot, summary và detail có thể không khớp.

Khi yêu cầu tất cả result sets phản ánh cùng một trạng thái dữ liệu:

- Xác định transaction do caller hay procedure sở hữu.
- Nếu caller sở hữu, mở transaction trên cùng connection trước khi `CALL` và không để procedure tự COMMIT ngoài ý muốn.
- Chọn isolation level phù hợp. Với InnoDB `REPEATABLE READ`, các consistent reads trong cùng transaction thường dùng cùng read view; `READ COMMITTED` tạo snapshot mới cho từng consistent read.
- Không dùng locking read cho một phần và consistent read cho phần khác mà không hiểu khác biệt snapshot/lock.
- Kết thúc transaction sau khi đã đọc hết result sets và hoàn tất công việc liên quan.

Không nhúng `START TRANSACTION`, `COMMIT` hoặc `ROLLBACK` tùy tiện vào một procedure dùng chung. Việc procedure tự quản lý transaction có thể xung đột với transaction mà ứng dụng đang mở. Nếu routine thực sự sở hữu transaction, ghi rõ điều đó trong contract và kiểm thử các đường lỗi.

## 12. Quyền thực thi và SQL SECURITY

Ứng dụng thường cần quyền `EXECUTE` trên procedure. Quyền truy cập bảng bên trong còn phụ thuộc thuộc tính `SQL SECURITY`:

- `SQL SECURITY DEFINER`: routine chạy với quyền của definer; đây là mặc định nếu không khai báo khác.
- `SQL SECURITY INVOKER`: routine chạy với quyền của caller; caller cần các quyền cần thiết trên object được truy cập.

Ví dụ cấp quyền gọi:

```sql
GRANT EXECUTE
ON PROCEDURE reporting_db.sp_customer_order_report
TO 'report_app'@'%';
```

Chọn DEFINER hay INVOKER theo mô hình phân quyền. Với DEFINER, quản lý tài khoản definer và quyền của routine cẩn thận; không dùng tài khoản có quyền cao không cần thiết. Với INVOKER, bảo đảm caller được cấp đúng quyền bảng.

Hợp đồng ứng dụng cần ghi rõ routine được gọi bởi role nào, schema nào, có yêu cầu session variable hoặc SQL mode đặc biệt không, và cách triển khai definer trên môi trường staging/production.

## 13. Thiết kế contract ổn định và tương thích phiên bản

Stored procedure là một giao diện có client phụ thuộc. Thay đổi procedure có thể phá client ngay cả khi không thay đổi tên routine.

### 13.1. Những thay đổi có thể phá tương thích

- Đổi thứ tự result sets.
- Thêm một result set mới vào giữa các result set hiện có.
- Đổi tên hoặc đổi thứ tự cột.
- Đổi kiểu dữ liệu, độ chính xác DECIMAL hoặc khả năng NULL.
- Đổi semantics của NULL, giá trị mặc định hoặc đơn vị đo.
- Đổi quy tắc sort, filter, pagination hoặc timezone.
- Thay result set rỗng bằng việc bỏ hẳn SELECT.
- Thêm một SELECT debug hoặc SELECT trong error handler.
- Đổi số lượng/thứ tự tham số hoặc kiểu IN/OUT/INOUT.
- Thay SQL SECURITY hoặc quyền thực thi theo cách làm caller hiện tại mất quyền.

### 13.2. Cách mở rộng an toàn

- Giữ nguyên thứ tự và schema các result sets hiện có.
- Nếu cần thêm dữ liệu, cân nhắc thêm cột nullable ở cuối result set nếu client mapping tương thích; vẫn phải kiểm thử tất cả consumer.
- Với thay đổi lớn về thứ tự, cấu trúc hoặc semantics, tạo routine version mới như `sp_customer_order_report_v2`.
- Công bố contract version và thời gian hỗ trợ phiên bản cũ.
- Dùng alias rõ ràng và kiểu dữ liệu tường minh.
- Không trả cột phụ thuộc debug, server variable hoặc trạng thái nội bộ không thuộc API.
- Duy trì integration test với đúng driver và MySQL version production.

Không nên dựa vào thứ tự vật lý của cột trong bảng nguồn hoặc dùng `SELECT *`. Procedure nên định nghĩa output độc lập với những thay đổi không liên quan trong schema nội bộ.

## 14. Phân trang và giới hạn kích thước result set

Một procedure trả detail 0..N hàng có thể vô tình gửi hàng triệu dòng qua mạng. Contract cần giới hạn lượng dữ liệu:

- Thêm `IN p_limit` và `IN p_offset` hoặc cursor/keyset pagination theo khóa ổn định.
- Quy định `ORDER BY` xác định, có tie-breaker duy nhất như `order_id`.
- Trả thông tin tổng số hàng nếu ứng dụng thật sự cần; tránh COUNT toàn bộ chỉ để hiển thị trang.
- Đặt giới hạn tối đa cho page size.
- Cân nhắc result set summary riêng với result set detail có phân trang.

Ví dụ:

```sql
SELECT order_id, order_date, order_status, total_amount
FROM orders
WHERE customer_id = p_customer_id
  AND order_date >= p_from_date
  AND order_date < p_to_date
ORDER BY order_date DESC, order_id DESC
LIMIT p_limit OFFSET p_offset;
```

Với offset lớn, keyset pagination có thể hiệu quả hơn nếu có index phù hợp. Contract phải mô tả page token/cursor nếu dùng keyset, cũng như hành vi khi dữ liệu thay đổi giữa các lần gọi.

## 15. Streaming, tiêu thụ kết quả và vòng đời connection

Result set lớn có thể được driver buffer toàn bộ hoặc stream từng phần tùy API/cấu hình. Streaming giảm bộ nhớ phía ứng dụng nhưng giữ statement và connection bận cho tới khi result set được tiêu thụ hoặc đóng.

Các quy tắc vận hành:

- Đọc và đóng từng `ResultSet` trước khi chuyển sang result tiếp theo theo contract driver.
- Không trả connection về pool khi còn result set chưa đọc.
- Không giữ transaction mở lâu chỉ vì client xử lý từng hàng chậm; cân nhắc phân trang hoặc lưu kết quả theo batch.
- Đặt query timeout và giới hạn kích thước kết quả.
- Nếu client ngắt giữa chừng, đóng statement/connection đúng cách và để pool loại connection nếu trạng thái protocol không còn an toàn.
- Kiểm thử chế độ streaming với Connector/J version thực tế; cách bật streaming phụ thuộc driver.

Một procedure trả nhiều result sets không có nghĩa ứng dụng có thể đọc song song mọi tập trên cùng một connection. Protocol có thứ tự; thông thường phải tiêu thụ hoặc đóng kết quả hiện tại trước khi lấy kết quả tiếp theo.

## 16. Kiểm thử hợp đồng procedure

Một bài test contract nên kiểm tra cả SQL output và hành vi driver.

| Nhóm kiểm thử | Điều cần xác nhận |
| --- | --- |
| Số result sets | Có đúng số lượng và thứ tự như contract |
| Metadata | Tên, thứ tự, SQL type, precision/scale và nullable đúng |
| Cardinality | Summary đúng 1 hàng; detail đúng 0..N hàng |
| Empty case | Không có detail vẫn trả result set thứ hai rỗng |
| Boundary | Ngày bắt đầu được tính, ngày kết thúc loại trừ |
| NULL | Giá trị NULL được map đúng, không nhầm với 0/empty string |
| OUT parameter | Đúng kiểu và giá trị sau CALL |
| Update count | Client xử lý đúng kết quả xen giữa nếu có |
| Error path | SQLSTATE/message đúng; client bỏ payload một phần |
| Transaction | Các result sets có snapshot nhất quán theo yêu cầu |
| Security | Role ứng dụng có EXECUTE và đúng quyền object |
| Compatibility | Consumer cũ vẫn hoạt động khi triển khai thay đổi |

### 16.1. Kiểm tra metadata bằng JDBC

`ResultSetMetaData` cho phép xác minh output schema:

```java
ResultSetMetaData meta = rs.getMetaData();
int columnCount = meta.getColumnCount();

for (int i = 1; i <= columnCount; i++) {
    System.out.printf(
        "%d: %s, jdbcType=%d, typeName=%s, nullable=%d%n",
        i,
        meta.getColumnLabel(i),
        meta.getColumnType(i),
        meta.getColumnTypeName(i),
        meta.isNullable(i)
    );
}
```

Chạy test metadata trong CI hoặc integration test sau mỗi migration thay đổi procedure. So sánh cả column label lẫn type/precision/scale; chỉ kiểm tra tên cột là chưa đủ.

## 17. Checklist thiết kế và gọi procedure trả nhiều kết quả

- [ ] Đã xác định rõ số lượng và thứ tự result sets.
- [ ] Mỗi result set có tên logic, schema cột và cardinality được tài liệu hóa.
- [ ] Dùng SELECT thường chỉ khi muốn gửi result set; dùng SELECT ... INTO cho tính toán nội bộ.
- [ ] Không có SELECT debug hoặc SELECT ngoài contract trong procedure/handler.
- [ ] Đã định nghĩa rõ cách dùng OUT/INOUT parameter và không lặp dữ liệu vô ích.
- [ ] Client dùng `execute()` và duyệt hết result sets/update counts.
- [ ] Client xử lý result set rỗng khác với thiếu result set.
- [ ] Client đóng ResultSet/CallableStatement và không trả connection khi còn kết quả chưa đọc.
- [ ] Đã xác định transaction owner và isolation level cho tính nhất quán giữa các result sets.
- [ ] Đã thống nhất SQL SECURITY và quyền EXECUTE.
- [ ] Đã giới hạn kích thước detail result set và quy tắc phân trang.
- [ ] Đã kiểm thử SQLSTATE, lỗi giữa chừng và partial result handling.
- [ ] Đã kiểm thử metadata bằng đúng MySQL Connector/J version.
- [ ] Có chiến lược versioning cho thay đổi phá tương thích.

## 18. Bài tập thực hành

1. Tạo `sp_customer_order_report` trả summary và detail. Gọi bằng SQL client và ghi lại thứ tự hai result sets.
2. Thử một customer có đơn và một customer không có đơn. Xác nhận result set detail rỗng vẫn tồn tại.
3. Chuyển một SELECT tính count thành SELECT ... INTO; xác nhận client không còn nhận result set phụ.
4. Tạo `sp_count_customer_orders` với OUT parameter. Gọi qua user variable và qua JDBC `registerOutParameter`.
5. Viết Java `CallableStatement` duyệt nhiều result sets bằng `getMoreResults()`; thêm kiểm tra số result sets mong đợi.
6. Thêm một UPDATE giữa hai SELECT và quan sát update count mà driver trả về.
7. Cố ý phát sinh SIGNAL sau result set đầu; xác định client nhận exception ở thời điểm nào và bảo đảm bỏ payload một phần.
8. Chạy CALL trong transaction `REPEATABLE READ` và `READ COMMITTED`, mô phỏng một session khác thêm đơn hàng giữa hai truy vấn để quan sát snapshot.
9. Dùng ResultSetMetaData ghi lại tên cột, kiểu JDBC, precision/scale và nullable cho từng result set.
10. Thay đổi một cột output trong procedure ở môi trường lab; viết contract test phát hiện thay đổi.
11. Thêm phân trang cho detail result set và kiểm tra thứ tự ổn định khi nhiều đơn cùng ngày.
12. Thiết kế `sp_customer_order_report_v2` cho một thay đổi phá tương thích và mô tả kế hoạch chuyển client.

## 19. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể tạo một stored procedure trả ít nhất hai result sets có mục đích riêng, mô tả chính xác thứ tự/schema/cardinality của chúng, phân biệt result set với OUT parameter, gọi và tiêu thụ toàn bộ kết quả bằng JDBC, xử lý update count và lỗi giữa chừng, đồng thời bảo đảm transaction/security/connection lifecycle phù hợp. Bạn cũng cần có contract test phát hiện thay đổi metadata hoặc thứ tự có thể phá ứng dụng.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — CALL Statement](https://dev.mysql.com/doc/refman/8.4/en/call.html)
- [MySQL 8.4 Reference Manual — CREATE PROCEDURE and CREATE FUNCTION](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL 8.4 Reference Manual — Stored Routine Syntax](https://dev.mysql.com/doc/refman/8.4/en/stored-programs-defining.html)
- [MySQL Connector/J Developer Guide — Stored Procedures](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-statements-callable.html)
- [Java JDBC API — CallableStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/CallableStatement.html)
