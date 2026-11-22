# Đọc SQLSTATE, mã lỗi MySQL và thông báo lỗi từ client

Khi một câu lệnh SQL thất bại, MySQL thường trả về mã lỗi, SQLSTATE và thông báo mô tả nguyên nhân. Ví dụ, khi ứng dụng thêm một email đã tồn tại vào bảng có ràng buộc `UNIQUE`, mysql client có thể hiển thị `ERROR 1062 (23000): Duplicate entry ...`. Ba phần này cung cấp các lớp thông tin khác nhau: mã `1062` nhận diện lỗi cụ thể của MySQL, SQLSTATE `23000` cho biết đây là vi phạm ràng buộc toàn vẹn, còn thông báo giải thích giá trị hoặc khóa bị trùng.

Đọc đúng các thông tin này giúp phân biệt lỗi cú pháp, lỗi dữ liệu, lỗi quyền, xung đột transaction và lỗi kết nối. Nhờ đó, ứng dụng có thể xử lý lỗi có chủ đích, người vận hành tìm đúng lớp gây sự cố và nhóm phát triển tránh phụ thuộc vào một câu thông báo có thể thay đổi giữa các phiên bản.

## 1. Ba thành phần cần đọc trong một lỗi MySQL

### 1.1. Mã lỗi MySQL

Mã lỗi MySQL (MySQL error number) là số nguyên nhận diện một điều kiện lỗi cụ thể do MySQL hoặc client library định nghĩa. Ví dụ:

- `1062`: giá trị trùng với khóa `PRIMARY KEY` hoặc `UNIQUE`.
- `1064`: lỗi cú pháp SQL.
- `1045`: xác thực tài khoản thất bại hoặc không được phép đăng nhập theo danh tính kết nối.
- `1146`: bảng hoặc view được tham chiếu không tồn tại.
- `1213`: InnoDB phát hiện deadlock và hủy một transaction.

Mã số có tính đặc thù của MySQL. Nó hữu ích khi tra tài liệu, log và mã xử lý theo driver, nhưng không phải mã chuẩn chung cho mọi hệ quản trị cơ sở dữ liệu.

### 1.2. SQLSTATE

SQLSTATE là mã trạng thái gồm đúng năm ký tự chữ và số, được thiết kế để phân loại điều kiện theo chuẩn SQL. Hai ký tự đầu biểu thị **class** (nhóm lỗi hoặc trạng thái); ba ký tự cuối biểu thị **subclass** (trạng thái cụ thể trong nhóm đó).

Một số class thường gặp:

| Class | Ý nghĩa | Ví dụ tình huống |
|---|---|---|
| `00` | Hoàn tất thành công | Câu lệnh hoàn tất bình thường (`00000`) |
| `01` | Cảnh báo | Dữ liệu bị chuyển đổi hoặc cắt cụt nhưng câu lệnh vẫn hoàn tất trong chế độ cho phép |
| `02` | Không tìm thấy dữ liệu | Đọc cursor hoặc thao tác không tìm được hàng phù hợp |
| `08` | Ngoại lệ kết nối | Kết nối hoặc đường truyền gặp sự cố |
| `0A` | Tính năng không được hỗ trợ | Yêu cầu một tính năng mà hệ thống/driver không hỗ trợ |
| `22` | Ngoại lệ dữ liệu | Giá trị sai định dạng, quá dài hoặc ngoài phạm vi |
| `23` | Vi phạm ràng buộc toàn vẹn | Trùng khóa, vi phạm khóa ngoại hoặc `NOT NULL` |
| `24` | Trạng thái cursor không hợp lệ | Thao tác cursor không đúng trạng thái |
| `25` | Trạng thái transaction không hợp lệ | Thao tác không phù hợp với trạng thái transaction |
| `28` | Lỗi xác thực hoặc quyền truy cập | Tài khoản không được xác thực |
| `40` | Transaction bị rollback | Deadlock hoặc xung đột cần rollback |
| `42` | Lỗi cú pháp hoặc quy tắc truy cập | Câu SQL sai hoặc tham chiếu đối tượng không hợp lệ |
| `HY` | Ngoại lệ chung do triển khai/driver báo cáo | Một số lỗi MySQL không có class cụ thể hơn |

Các class giúp phân loại ở mức khái quát. Không nên suy ra mọi chi tiết xử lý chỉ từ hai ký tự đầu; hãy kết hợp SQLSTATE đầy đủ, mã lỗi MySQL và ngữ cảnh câu lệnh.

### 1.3. Thông báo lỗi

Thông báo lỗi (message text) là phần văn bản giúp con người hiểu tình huống cụ thể, thường chứa tên bảng, cột, constraint, giá trị hoặc thao tác bị từ chối. Ví dụ `Duplicate entry 'alice@example.com' for key 'users.email'` cho biết giá trị email bị trùng trên khóa nào.

Thông báo có thể thay đổi theo phiên bản MySQL, driver, ngôn ngữ, cấu hình và nội dung dữ liệu. Vì vậy, hãy dùng mã lỗi và SQLSTATE để phân loại trong chương trình; dùng message để ghi log, hỗ trợ chẩn đoán và hiển thị thông tin đã được kiểm soát cho người vận hành.

## 2. Đọc cấu trúc thông báo từ mysql client

Một lỗi do server trả về thường được mysql client hiển thị theo dạng:

```text
ERROR 1062 (23000) at line 8: Duplicate entry 'alice@example.com' for key 'users.email'
```

Có thể đọc từng phần như sau:

| Thành phần | Giá trị ví dụ | Ý nghĩa |
|---|---|---|
| Mức thông báo | `ERROR` | Câu lệnh thất bại |
| Mã lỗi | `1062` | Mã lỗi cụ thể của MySQL |
| SQLSTATE | `(23000)` | Nhóm vi phạm ràng buộc toàn vẹn |
| Vị trí | `at line 8` | Dòng trong file đầu vào mà client đang thực thi; phần này không phải lúc nào cũng xuất hiện |
| Nội dung | `Duplicate entry ...` | Mô tả cụ thể về giá trị và khóa bị trùng |

Nếu câu lệnh được gửi trực tiếp ở dấu nhắc tương tác, thông báo thường không có phần `at line`. Khi client đọc file SQL, vị trí dòng giúp tìm câu lệnh cần kiểm tra. Với script có nhiều lệnh, hãy đối chiếu cả dòng lỗi và câu lệnh thực tế; một lỗi ở một dòng có thể xuất phát từ schema hoặc dữ liệu được tạo ở bước trước.

Ví dụ khác:

```text
ERROR 1064 (42000): You have an error in your SQL syntax; check the manual...
ERROR 1146 (42S02): Table 'shop.order_items' doesn't exist
ERROR 1045 (28000): Access denied for user 'app_user'@'10.0.0.12'
```

Trong ví dụ đầu, `42000` thuộc nhóm cú pháp hoặc quy tắc truy cập. Ví dụ thứ hai cho biết không tìm thấy bảng (`42S02`). Ví dụ thứ ba thuộc nhóm xác thực (`28000`). Message vẫn cần được đọc để biết chính xác bảng hoặc danh tính kết nối liên quan.

Không phải mọi thông báo in trên terminal đều là lỗi SQL do server gửi. Lỗi phân giải DNS, không mở được socket, file đầu vào không tồn tại, TLS handshake hoặc tùy chọn command line sai có thể phát sinh ngay ở client hay hệ điều hành. Chúng có thể không có SQLSTATE do server cấp, vì server chưa nhận được câu SQL nào.

## 3. Phân biệt lỗi server, client và kết nối

| Nguồn lỗi | Thời điểm thường xảy ra | Dấu hiệu | Hướng kiểm tra |
|---|---|---|---|
| SQL/server | Server đã nhận câu lệnh | Có mã lỗi MySQL và thường có SQLSTATE; ví dụ `1062`, `1064`, `1146` | Kiểm tra SQL, schema, dữ liệu, quyền và trạng thái transaction |
| Client/tool | Trước hoặc trong khi client xử lý đầu vào | Sai tùy chọn, không đọc được file, sai cú pháp lệnh shell hoặc lỗi giao diện | Kiểm tra câu lệnh chạy client, đường dẫn file, phiên bản và log của công cụ |
| Mạng/kết nối | Trước khi kết nối hoặc trong phiên | Timeout, connection refused, server has gone away, lost connection | Kiểm tra DNS, host/port, firewall, TLS, server restart và timeout |
| Ứng dụng/driver | Khi ánh xạ kết quả hoặc thực thi logic ứng dụng | Exception, lỗi cấu hình pool, lỗi chuyển kiểu hoặc xử lý dữ liệu | Đọc thuộc tính exception, stack trace và log tương quan của ứng dụng |

Ví dụ `ERROR 2003` khi client không thể kết nối tới máy chủ ở host/port chỉ ra vấn đề kết nối; câu SQL chưa được thực thi. Ngược lại, `ERROR 1064` nghĩa là server đã phân tích câu SQL và từ chối cú pháp. Hai tình huống cần cách xử lý hoàn toàn khác nhau.

Các lỗi như `ERROR 2006: MySQL server has gone away` hoặc `ERROR 2013: Lost connection to MySQL server during query` có thể xuất hiện khi server đóng kết nối, mạng bị gián đoạn hoặc thời gian chờ vượt giới hạn. Chúng không tự chứng minh transaction đã rollback. Nếu kết nối mất đúng lúc `COMMIT`, client có thể không biết commit đã thành công hay chưa; cần đối soát trạng thái nghiệp vụ trước khi thử lại.

## 4. Những SQLSTATE và mã lỗi MySQL thường gặp

Bảng dưới đây tập trung vào các tình huống thường gặp khi phát triển và vận hành MySQL. Message cụ thể có thể khác theo phiên bản và ngữ cảnh.

| Mã lỗi MySQL | SQLSTATE thường gặp | Tình huống | Cách xử lý ban đầu |
|---:|---|---|---|
| `1062` | `23000` | Trùng khóa chính hoặc unique key | Kiểm tra dữ liệu hiện có, tính duy nhất nghiệp vụ và chiến lược upsert/idempotency |
| `1048` | `23000` | Gán `NULL` cho cột `NOT NULL` | Kiểm tra dữ liệu đầu vào, giá trị mặc định và hợp đồng dữ liệu |
| `1452` | `23000` | Thêm/cập nhật hàng con nhưng không có hàng cha tham chiếu | Tạo hoặc xác nhận hàng cha trước; kiểm tra đúng khóa ngoại |
| `1451` | `23000` | Xóa/cập nhật hàng cha đang được hàng con tham chiếu | Xác định quy tắc nghiệp vụ, thứ tự xóa hoặc hành vi `ON DELETE` |
| `1064` | `42000` | Cú pháp SQL không hợp lệ | Kiểm tra câu lệnh, dấu nháy, dấu phẩy, từ khóa và phiên bản server |
| `1054` | `42S22` | Không tìm thấy cột được tham chiếu | Kiểm tra tên cột, alias, schema và migration |
| `1146` | `42S02` | Không tìm thấy bảng hoặc view | Kiểm tra schema hiện tại, tên đối tượng và thứ tự migration |
| `1045` | `28000` | Xác thực tài khoản thất bại | Kiểm tra user, host nguồn, thông tin xác thực và plugin xác thực |
| `1213` | `40001` | Deadlock; InnoDB rollback một transaction | Thử lại toàn bộ transaction với giới hạn và backoff; xem thứ tự lấy khóa |
| `1205` | `HY000` | Chờ khóa vượt `innodb_lock_wait_timeout` | Tìm transaction giữ khóa, giảm thời gian transaction và quyết định rollback nghiệp vụ |
| `1406` | `22001` | Giá trị quá dài cho cột | Kiểm tra độ dài dữ liệu và kiểu/cỡ cột; không cắt dữ liệu âm thầm |
| `1264` | `22003` | Giá trị số nằm ngoài phạm vi kiểu dữ liệu | Kiểm tra miền giá trị, kiểu số và phép tính tràn |
| `1292` | `22007` | Giá trị ngày/giờ không hợp lệ hoặc chuyển đổi không đúng | Kiểm tra định dạng, timezone, kiểu cột và SQL mode |
| `1136` | `21S01` | Số giá trị không khớp số cột trong `INSERT` | So sánh danh sách cột với danh sách giá trị |
| `2002` / `2003` | Thường là `HY000` ở client | Không thể mở kết nối/socket hoặc kết nối TCP tới server | Kiểm tra dịch vụ, host, port, socket và firewall |
| `2006` / `2013` | Thường là `HY000` | Server đã đóng kết nối hoặc mất kết nối trong khi truy vấn | Kiểm tra server log, mạng, timeout và trạng thái commit |

Các mã `2002`, `2003`, `2006` và `2013` thường xuất hiện ở lớp client/library hoặc kết nối. SQLSTATE hiển thị có thể phụ thuộc đường đi lỗi và connector. Khi ứng dụng cần xử lý chính xác, hãy lấy trực tiếp thuộc tính từ driver đang sử dụng thay vì giả định mọi client đều ánh xạ giống nhau.

## 5. Đọc warning và diagnostics sau câu lệnh

Không phải mọi điều kiện bất thường đều làm câu lệnh thất bại. MySQL có thể hoàn tất câu lệnh nhưng phát sinh warning, chẳng hạn chuyển đổi giá trị hoặc xử lý dữ liệu theo SQL mode hiện tại. Warning vẫn cần được kiểm tra vì nó có thể báo hiệu dữ liệu bị biến đổi ngoài mong muốn.

### 5.1. Dùng SHOW WARNINGS và SHOW ERRORS

Ví dụ sau dùng `INSERT IGNORE` để minh họa việc một lỗi trùng khóa được chuyển thành warning trong một số tình huống:

```sql
INSERT IGNORE INTO users (email)
VALUES ('alice@example.com');

SHOW WARNINGS;
SHOW COUNT(*) WARNINGS;
SHOW ERRORS;
```

`SHOW WARNINGS` liệt kê các điều kiện warning, error và note của câu lệnh gần nhất; `SHOW ERRORS` chỉ liệt kê error. `SHOW COUNT(*) WARNINGS` trả về số warning được ghi nhận. Hãy chạy các lệnh này ngay sau câu lệnh cần điều tra để tránh nhầm với kết quả của câu lệnh khác.

`INSERT IGNORE` không phải cách sửa mặc định cho lỗi dữ liệu. Nó có thể biến một số lỗi thành warning và cho phép câu lệnh tiếp tục, làm ứng dụng bỏ qua dữ liệu không được chèn. Chỉ dùng khi hành vi bỏ qua đã được thiết kế và kiểm tra rõ ràng.

### 5.2. Dùng GET DIAGNOSTICS

Trong stored program, `GET DIAGNOSTICS` cho phép lấy thông tin từ diagnostics area. Có thể lấy số điều kiện, số hàng bị ảnh hưởng hoặc thông tin của một condition cụ thể.

```sql
GET DIAGNOSTICS
    @condition_count = NUMBER,
    @affected_rows = ROW_COUNT;

SELECT @condition_count, @affected_rows;
```

Để đọc một condition:

```sql
GET DIAGNOSTICS CONDITION 1
    @sqlstate = RETURNED_SQLSTATE,
    @mysql_errno = MYSQL_ERRNO,
    @message = MESSAGE_TEXT;

SELECT @sqlstate, @mysql_errno, @message;
```

`CONDITION 1` là condition đầu tiên trong diagnostics area; nếu có nhiều condition, cần xem `NUMBER` và chọn đúng condition. Các biến `@...` trong ví dụ là user-defined session variables. Trong stored procedure, có thể gán vào local variables đã khai báo.

Ví dụ handler bắt exception trong stored procedure:

```sql
DELIMITER //

CREATE PROCEDURE create_user(IN p_email VARCHAR(255))
BEGIN
    DECLARE v_sqlstate CHAR(5);
    DECLARE v_errno INT;
    DECLARE v_message TEXT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            v_sqlstate = RETURNED_SQLSTATE,
            v_errno = MYSQL_ERRNO,
            v_message = MESSAGE_TEXT;

        -- Có thể ghi log nội bộ tại đây nếu thiết kế cho phép.
        -- RESIGNAL giữ nguyên lỗi để caller tiếp tục nhận được lỗi.
        RESIGNAL;
    END;

    INSERT INTO users (email) VALUES (p_email);
END//

DELIMITER ;
```

Các biến được khai báo trước handler theo thứ tự khai báo của stored program. Trong ví dụ, handler đọc diagnostics rồi `RESIGNAL` để không che mất lỗi gốc. Nếu muốn ghi log vào bảng, cần thiết kế rõ transaction và xử lý trường hợp chính thao tác ghi log cũng thất bại.

### 5.3. Chủ động phát sinh lỗi nghiệp vụ

`SIGNAL` cho phép stored program phát sinh condition có SQLSTATE do ứng dụng định nghĩa. SQLSTATE `45000` thường được dùng cho exception do người dùng định nghĩa:

```sql
IF p_quantity <= 0 THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Quantity must be greater than zero';
END IF;
```

`RESIGNAL` trong handler cho phép ném lại lỗi đang được xử lý, hoặc điều chỉnh một số thuộc tính condition khi có chủ đích. Không nên bắt mọi exception rồi trả về thành công; điều đó làm caller tưởng nghiệp vụ đã hoàn tất dù dữ liệu có thể chưa được ghi.

## 6. Lấy mã lỗi và SQLSTATE trong ứng dụng

Ứng dụng không nên phân tích chuỗi message bằng cách tìm các từ như `Duplicate`, `Access denied` hoặc `timeout`. Nội dung có thể thay đổi theo phiên bản, ngôn ngữ hoặc driver. Hãy lấy các trường có cấu trúc mà connector cung cấp.

### 6.1. Java JDBC

Với JDBC, `SQLException` cung cấp SQLSTATE, mã lỗi vendor và message:

```java
try {
    // Thực hiện câu lệnh qua PreparedStatement.
} catch (SQLException ex) {
    String sqlState = ex.getSQLState();
    int vendorCode = ex.getErrorCode();
    String message = ex.getMessage();

    // Ghi log sqlState và vendorCode cùng request/correlation ID.
    // Phân loại lỗi theo mã; không dùng message làm khóa logic.
}
```

Một `SQLException` có thể liên kết với exception kế tiếp qua `getNextException()`, nhất là khi driver báo nhiều lỗi cho batch hoặc nhiều câu lệnh. Nếu cần chẩn đoán đầy đủ, duyệt chuỗi exception và ghi lại thông tin có liên quan mà không lộ dữ liệu nhạy cảm.

### 6.2. MySQL C API

Với MySQL C API, các hàm thường dùng gồm:

```c
unsigned int code = mysql_errno(conn);
const char *state = mysql_sqlstate(conn);
const char *message = mysql_error(conn);
```

Các hàm này đọc thông tin lỗi của kết nối sau thao tác thất bại. Cần sao chép nội dung message nếu muốn giữ lâu hơn thời điểm mà API bảo đảm con trỏ còn hợp lệ; không giả định vùng nhớ trả về thuộc quyền sở hữu của ứng dụng.

### 6.3. Các connector khác

Node.js, Python, PHP và các nền tảng khác có cách đóng gói exception riêng. Tên thuộc tính có thể khác nhau giữa connector hoặc phiên bản. Hãy tra tài liệu driver đang dùng để lấy:

- Mã lỗi MySQL hoặc mã symbolic do driver ánh xạ.
- SQLSTATE nếu connector cung cấp.
- Message phục vụ chẩn đoán.
- Thông tin trạng thái kết nối và nguyên nhân lỗi ở lớp transport nếu có.

Không giả định mọi lỗi đều có đủ cả ba trường. Một lỗi xảy ra trước khi server phản hồi có thể chỉ có mã client hoặc thông tin hệ điều hành.

## 7. Phân loại lỗi để quyết định cách xử lý

Một mã lỗi chỉ có ích khi được gắn với hành động phù hợp. Có thể phân nhóm như sau:

| Nhóm | Ví dụ | Hành động phù hợp |
|---|---|---|
| Lỗi đầu vào/nghiệp vụ | `1062`, `1048`, `1452`, `1406` | Kiểm tra dữ liệu, phản hồi validation hoặc giải quyết xung đột theo nghiệp vụ |
| Lỗi SQL/schema | `1064`, `1054`, `1146` | Sửa SQL, alias, schema hoặc thứ tự migration; thường không retry nguyên trạng |
| Lỗi xác thực/quyền | `1045`, `1142` | Kiểm tra tài khoản, host, grant và cấu hình; không lặp đăng nhập vô hạn |
| Xung đột transaction | `1213`, `1205` | Xem xét rollback, giảm thời gian giữ khóa và retry có giới hạn khi phù hợp |
| Lỗi kết nối | `2002`, `2003`, `2006`, `2013` | Kiểm tra mạng/server và xác định trạng thái commit trước khi gửi lại thao tác |
| Warning/chuyển đổi dữ liệu | SQLSTATE class `01` | Xem `SHOW WARNINGS`, kiểm tra SQL mode và chất lượng dữ liệu |

### 7.1. Khi nào có thể retry?

Deadlock (`1213`, SQLSTATE `40001`) là trường hợp thường có thể retry toàn bộ transaction. InnoDB đã rollback transaction bị chọn làm nạn nhân, vì vậy ứng dụng nên bắt lỗi, đợi một khoảng ngẫu nhiên ngắn (backoff), rồi chạy lại toàn bộ đơn vị nghiệp vụ với giới hạn số lần thử.

Lock wait timeout (`1205`) cần xử lý cẩn thận hơn. Theo cấu hình mặc định `innodb_rollback_on_timeout` tắt, timeout thường chỉ rollback câu lệnh bị timeout, không tự động rollback toàn bộ transaction. Ứng dụng nên chủ động `ROLLBACK` toàn bộ transaction nghiệp vụ khi một bước thất bại, sau đó mới quyết định có retry hay không. Không tiếp tục `COMMIT` một transaction đang ở trạng thái dở dang.

Không retry vô hạn. Retry quá nhiều có thể làm tăng tải và khiến tình trạng tranh chấp nặng hơn. Dùng giới hạn, backoff có jitter, metric số lần retry và log để phát hiện vấn đề kéo dài.

### 7.2. Khi nào không nên retry tự động?

- Lỗi cú pháp (`1064`), sai cột (`1054`) hoặc thiếu bảng (`1146`) thường cần sửa mã hoặc triển khai migration.
- Lỗi xác thực/quyền (`1045`, `1142`) cần điều chỉnh cấu hình hoặc quyền; retry liên tục không giải quyết được nguyên nhân.
- Vi phạm dữ liệu (`1062`, `1452`, `1406`) cần kiểm tra quy tắc nghiệp vụ và payload. Retry cùng dữ liệu thường tạo lại cùng lỗi.
- Mất kết nối lúc commit có thể để lại kết quả không xác định ở phía client. Trước khi gửi lại, hãy truy vấn trạng thái nghiệp vụ bằng mã idempotency hoặc khóa tham chiếu duy nhất.

Ví dụ, API tạo thanh toán nên nhận một `idempotency_key` duy nhất. Nếu client mất kết nối sau khi gửi yêu cầu, lần gửi lại có thể tra cứu kết quả theo khóa này thay vì tạo thêm một giao dịch thanh toán.

## 8. Đọc lỗi transaction và khóa của InnoDB

Khi gặp lỗi `1213` hoặc `1205`, cần xác định transaction nào giữ khóa và câu lệnh nào đang chờ. Những bước điều tra hữu ích gồm:

```sql
SHOW ENGINE INNODB STATUS\G
```

Phần `LATEST DETECTED DEADLOCK` thường cho biết các transaction tham gia, câu lệnh, index record và transaction bị rollback gần nhất. Thông tin này có thể bị thay thế khi deadlock mới xảy ra, nên cần thu thập gần thời điểm sự cố.

Trên các phiên bản MySQL phù hợp, Performance Schema và các view trong `sys` có thể hỗ trợ xem transaction đang chờ, lock wait và statement digest. Ví dụ, có thể bắt đầu từ các view `sys.innodb_lock_waits` và `sys.schema_table_lock_waits` nếu chúng có trong bản cài đặt.

Các biện pháp giảm deadlock và lock wait:

- Giữ transaction ngắn; không chờ người dùng hoặc gọi dịch vụ ngoài trong khi đang giữ khóa.
- Cập nhật nhiều hàng theo một thứ tự nhất quán giữa các luồng.
- Tạo chỉ mục phù hợp để câu `UPDATE`/`DELETE` khóa phạm vi cần thiết thay vì quét quá rộng.
- Không để transaction đọc/ghi mở lâu hơn yêu cầu nghiệp vụ.
- Retry transaction bị deadlock có giới hạn và ghi metric để theo dõi.

## 9. Log lỗi và thông tin cần lưu khi chẩn đoán

Thông báo trên client chỉ là một phần của bằng chứng. Với lỗi vận hành, hãy đối chiếu thời điểm client gặp lỗi với error log của MySQL Server, log ứng dụng và metric hệ thống.

Một bản ghi chẩn đoán hữu ích nên có:

- Thời điểm và timezone, cùng request ID hoặc correlation ID.
- Tên môi trường, host logic và tên dịch vụ; tránh ghi mật khẩu hoặc chuỗi kết nối chứa secret.
- Mã lỗi MySQL, SQLSTATE, message và loại thao tác.
- Tên statement hoặc fingerprint/digest của SQL; che giá trị nhạy cảm thay vì ghi nguyên payload.
- Trạng thái transaction: đã bắt đầu, câu lệnh nào thành công, đã gọi `COMMIT` hay `ROLLBACK`, và client có nhận xác nhận commit hay không.
- Số lần retry, thời gian chờ, thời lượng truy vấn và trạng thái connection pool.
- Phiên bản MySQL Server, connector và ứng dụng khi cần điều tra khác biệt phiên bản.

Không ghi toàn bộ dữ liệu cá nhân, token, mật khẩu hoặc thông tin thanh toán vào log. Nếu cần đối chiếu một giá trị gây lỗi, hãy dùng mã tham chiếu hoặc dạng đã che dữ liệu.

## 10. Quy trình đọc và xử lý một lỗi thực tế

Giả sử API tạo tài khoản trả về lỗi khi thêm email `alice@example.com`. mysql client hiển thị:

```text
ERROR 1062 (23000): Duplicate entry 'alice@example.com' for key 'users.email'
```

Có thể điều tra theo trình tự:

1. **Đọc cấu trúc:** `1062` là mã MySQL cho duplicate key; `23000` là class vi phạm ràng buộc toàn vẹn.
2. **Xác định constraint:** message nêu khóa `users.email`; kiểm tra `SHOW CREATE TABLE users` hoặc `SHOW INDEX FROM users` để xác nhận unique index.
3. **Xác định nghiệp vụ:** email đã được đăng ký hay hai yêu cầu tạo tài khoản chạy đồng thời? Không chỉ dựa vào một lần `SELECT` trước `INSERT`, vì race condition vẫn có thể xảy ra.
4. **Chọn phản hồi:** nếu email đã tồn tại, trả lỗi nghiệp vụ phù hợp hoặc dùng luồng đăng nhập/khôi phục tài khoản. Không đổi unique constraint chỉ để bỏ qua xung đột.
5. **Xem xét tính lặp an toàn:** nếu request có thể được gửi lại, dùng khóa idempotency hoặc cơ chế xác định kết quả đã tạo để tránh sinh dữ liệu trùng.
6. **Ghi log:** lưu SQLSTATE, mã lỗi, constraint, request ID và thông tin cần thiết đã được che dữ liệu.

Quy trình tương tự áp dụng cho lỗi khác: đọc mã và SQLSTATE, xác định nguồn lỗi, đối chiếu message với câu lệnh và trạng thái transaction, rồi chọn sửa dữ liệu, sửa SQL, điều chỉnh quyền, retry hoặc điều tra kết nối.

## 11. Những sai lầm thường gặp

- **Phân tích message bằng chuỗi cố định:** message có thể thay đổi; dùng `errno` và SQLSTATE để phân loại.
- **Coi mọi lỗi đều có thể retry:** lỗi schema, quyền và dữ liệu cần sửa nguyên nhân; retry chỉ tăng tải.
- **Coi timeout là transaction đã rollback:** lock wait timeout mặc định có thể chỉ rollback statement; mất kết nối lúc commit còn có thể khiến kết quả không rõ ở client.
- **Bỏ qua warning:** warning có thể báo dữ liệu bị chuyển đổi hoặc cắt cụt; hãy đọc ngay bằng `SHOW WARNINGS`.
- **Ẩn lỗi bằng `INSERT IGNORE`:** câu lệnh có thể tiếp tục trong khi một số hàng không được ghi như mong đợi.
- **Chỉ lưu message mà không lưu SQLSTATE/mã lỗi:** khiến việc nhóm lỗi và theo dõi xu hướng khó khăn.
- **Ghi log nguyên payload:** có thể làm lộ dữ liệu nhạy cảm; hãy dùng fingerprint, mã tham chiếu và che giá trị.
- **Thử lại thao tác sau khi mất kết nối mà không đối soát:** có thể tạo bản ghi hoặc giao dịch trùng nếu commit trước đó đã thành công.

## 12. Checklist khi nhận được lỗi từ MySQL

- Mã lỗi MySQL là gì? SQLSTATE đầy đủ là gì?
- Thông báo đến từ server, client, driver hay lớp mạng/hệ điều hành?
- Câu SQL nào đang chạy, trên host/schema nào và bằng tài khoản nào?
- Message nhắc đến bảng, cột, index, constraint hoặc giá trị nào?
- Câu lệnh thất bại hay chỉ phát sinh warning? `SHOW WARNINGS` có thông tin gì?
- Transaction đã rollback, vẫn còn mở hay trạng thái commit chưa xác định?
- Lỗi có thể giải quyết bằng sửa dữ liệu, SQL, schema, quyền hoặc kết nối không?
- Có an toàn để retry toàn bộ transaction không? Có cần idempotency key không?
- Log có đủ thời điểm, request ID, mã lỗi và phiên bản nhưng đã che secret chưa?

## Kết luận

Mã lỗi MySQL cho biết điều kiện cụ thể theo cách triển khai của MySQL; SQLSTATE phân loại trạng thái theo nhóm chuẩn; message cung cấp ngữ cảnh để con người điều tra. Khi đọc lỗi từ mysql client hoặc connector, hãy xác định lỗi đến từ server hay từ client/kết nối, đối chiếu cả ba thành phần và kiểm tra trạng thái transaction. Trong ứng dụng, dùng mã và SQLSTATE để phân loại, chỉ retry những transaction có thể chạy lại an toàn, đồng thời ghi log đủ chẩn đoán mà không làm lộ dữ liệu nhạy cảm.
