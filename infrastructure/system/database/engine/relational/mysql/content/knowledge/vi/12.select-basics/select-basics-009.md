# Biến bind và phân biệt dữ liệu đầu vào với tên đối tượng

Khi ứng dụng tạo câu SELECT từ dữ liệu người dùng, cần phân biệt hai loại đầu vào:

- **Giá trị dữ liệu**: mã khách hàng, trạng thái đơn hàng, từ khóa tìm kiếm, ngày bắt đầu và số lượng kết quả.
- **Cấu trúc SQL**: tên schema, tên bảng, tên cột, hướng sắp xếp, biểu thức hoặc phần cú pháp được chọn.

Biến bind (parameter binding) dùng để truyền giá trị dữ liệu vào câu SQL đã xác định cấu trúc. Cơ chế này giúp database xử lý giá trị tách biệt khỏi cú pháp câu lệnh, tránh việc nội dung người dùng bị diễn giải thành một phần SQL và thường cho phép tái sử dụng câu lệnh đã chuẩn bị.

Placeholder không phải biến thay thế cho mọi thành phần SQL. Trong MySQL prepared statement, dấu hỏi chấm đại diện cho một giá trị ở vị trí biểu thức phù hợp; nó không thể thay tên bảng, tên cột, từ khóa ASC/DESC hoặc cả một đoạn điều kiện. Khi cần lựa chọn cấu trúc truy vấn động, ứng dụng phải chọn từ danh sách được cho phép, sau đó mới ghép tên đối tượng đã kiểm soát vào SQL.

Bài viết tập trung vào MySQL và cách xây dựng truy vấn SELECT an toàn trong ứng dụng. Các ví dụ dùng SQL prepared statement, Java JDBC và Python connector để làm rõ khác biệt giữa bind value và dynamic identifier.

## 1. Dữ liệu đầu vào và cấu trúc SQL là hai thứ khác nhau

Giả sử màn hình tìm đơn hàng có các chức năng:

- Tìm theo mã khách hàng.
- Lọc theo trạng thái.
- Chọn cột dùng để sắp xếp.
- Chọn thứ tự tăng dần hoặc giảm dần.
- Chọn số hàng hiển thị.

Trong yêu cầu này, customer_id, status và page_size là giá trị dữ liệu. Chúng có thể thay đổi giữa các lần chạy nhưng không làm thay đổi cấu trúc câu SQL.

Ngược lại, created_at hoặc total được chọn làm cột sắp xếp là tên cột. ASC hoặc DESC là từ khóa cú pháp. Chúng làm thay đổi cấu trúc câu lệnh và không thể được truyền vào một placeholder giá trị thông thường.

| Đầu vào | Loại | Cách xử lý |
|---|---|---|
| customer_id = 42 | Giá trị dữ liệu | Bind parameter |
| status = 'PAID' | Giá trị dữ liệu | Bind parameter |
| Ngày bắt đầu/kết thúc | Giá trị dữ liệu | Bind parameter |
| Số hàng LIMIT | Giá trị dữ liệu | Bind nếu driver và câu lệnh hỗ trợ |
| Tên bảng orders | Identifier | Chọn từ allowlist, sau đó quote đúng cú pháp |
| Tên cột created_at | Identifier | Chọn từ allowlist, sau đó quote đúng cú pháp |
| ASC hoặc DESC | Cấu trúc SQL | Chọn từ tập giá trị cố định |
| AND status = ? | Đoạn cấu trúc SQL | Chỉ thêm từ nhánh logic do ứng dụng kiểm soát |

Quy tắc này là nền tảng để vừa tránh SQL injection vừa giữ cho truy vấn dễ đọc, dễ kiểm thử và dễ bảo trì.

## 2. Bind parameter hoạt động như thế nào?

### 2.1. Câu SQL có cấu trúc cố định

Thay vì nối giá trị trực tiếp vào chuỗi SQL:

~~~sql
SELECT order_id, customer_id, status, total
FROM orders
WHERE customer_id = 42
  AND status = 'PAID';
~~~

Ứng dụng chuẩn bị một câu lệnh có placeholder:

~~~sql
SELECT order_id, customer_id, status, total
FROM orders
WHERE customer_id = ?
  AND status = ?;
~~~

Sau đó truyền hai giá trị theo đúng thứ tự:

~~~text
parameter 1 = 42
parameter 2 = "PAID"
~~~

Database nhận câu lệnh và giá trị theo cơ chế của prepared statement/driver. Giá trị PAID được xử lý như dữ liệu của biểu thức, không được phân tích lại như cú pháp SQL.

### 2.2. Placeholder có vị trí và kiểu dữ liệu

Trong prepared statement của MySQL, dấu hỏi chấm là parameter marker. Các marker được gán theo thứ tự xuất hiện, bắt đầu từ vị trí đầu tiên.

~~~sql
SELECT order_id, total
FROM orders
WHERE customer_id = ?
  AND created_at >= ?
  AND status IN (?, ?);
~~~

Thứ tự bind:

1. Mã khách hàng.
2. Thời điểm bắt đầu.
3. Trạng thái thứ nhất.
4. Trạng thái thứ hai.

Số lượng giá trị bind phải khớp số placeholder và thứ tự phải chính xác. Nếu truyền sai thứ tự, câu lệnh có thể vẫn chạy nhưng trả dữ liệu sai hoặc gặp lỗi chuyển kiểu.

### 2.3. Bind không có nghĩa là tự động kiểm tra nghiệp vụ

Parameter binding bảo vệ ranh giới giữa cú pháp và giá trị, nhưng không tự xác thực:

- Người dùng có quyền xem customer_id đó hay không.
- Ngày bắt đầu có trước ngày kết thúc không.
- Số lượng kết quả có vượt giới hạn ứng dụng không.
- Trạng thái có nằm trong tập trạng thái hợp lệ không.
- Chuỗi tìm kiếm có quá dài hoặc chứa nội dung không phù hợp nghiệp vụ không.

Ứng dụng vẫn cần validate kiểu, miền giá trị và quyền truy cập trước khi thực thi. Prepared statement là biện pháp bảo vệ SQL syntax, không thay thế xác thực và phân quyền nghiệp vụ.

## 3. Vì sao không nên nối chuỗi dữ liệu vào SQL?

Giả sử ứng dụng ghép trực tiếp nội dung tìm kiếm:

~~~java
String sql =
    "SELECT order_id, status FROM orders " +
    "WHERE status = '" + userStatus + "'";
~~~

Nếu đầu vào là:

~~~text
PAID' OR '1'='1
~~~

SQL sau khi ghép có thể trở thành:

~~~sql
SELECT order_id, status
FROM orders
WHERE status = 'PAID' OR '1'='1';
~~~

Điều kiện luôn đúng khiến truy vấn có thể trả về nhiều hàng hơn dự kiến. Các payload khác có thể thay đổi logic truy vấn hoặc gây lỗi cú pháp.

Dùng placeholder:

~~~java
String sql =
    "SELECT order_id, status FROM orders WHERE status = ?";

PreparedStatement statement = connection.prepareStatement(sql);
statement.setString(1, userStatus);
~~~

Lúc này chuỗi PAID' OR '1'='1 được truyền như một giá trị duy nhất. Nó không thể tự đóng literal rồi chèn thêm toán tử SQL.

Không nên tự escape chuỗi bằng cách thay dấu nháy hoặc xóa ký tự đặc biệt rồi tiếp tục nối SQL. Quy tắc escape phụ thuộc character set, SQL mode và ngữ cảnh cú pháp; parameter binding xử lý ranh giới đó đáng tin cậy hơn.

## 4. Placeholder không thay thế tên bảng hoặc tên cột

### 4.1. Cách viết sai thường gặp

Đây không phải cách dùng hợp lệ để chọn bảng:

~~~sql
SELECT *
FROM ?
WHERE customer_id = ?;
~~~

Tương tự, không thể dùng một placeholder thông thường để thay tên cột:

~~~sql
SELECT ?
FROM orders;
~~~

Trong câu lệnh thứ hai, marker là một biểu thức giá trị. Nếu bind chuỗi total, kết quả thường là giá trị literal total lặp lại cho từng hàng, không phải dữ liệu của cột có tên total.

Không thể dùng placeholder để thay:

- Tên database, schema, table hoặc column.
- Tên index trong các vị trí cú pháp yêu cầu identifier.
- Từ khóa ASC, DESC, JOIN, GROUP BY.
- Toán tử như =, >, LIKE.
- Một đoạn SQL hoàn chỉnh như WHERE ... ORDER BY ....

### 4.2. Identifier là thành phần cú pháp

MySQL dùng identifier để đặt tên database, bảng, cột, index và các đối tượng khác. Identifier có thể cần quote bằng backtick:

~~~sql
SELECT order_id, created_at
FROM shop.orders;
~~~

Backtick giúp phân biệt tên đối tượng với từ khóa hoặc ký tự đặc biệt. Nếu identifier chứa backtick, ký tự backtick bên trong phải được escape bằng cách viết hai backtick liên tiếp theo quy tắc MySQL.

Quote identifier không làm cho một tên tùy ý trở nên an toàn về mặt nghiệp vụ. Một tên hợp lệ nhưng không được phép vẫn có thể cho phép người dùng truy cập bảng hoặc cột mà họ không được chọn. Vì vậy cần allowlist trước khi ghép identifier.

## 5. Xây dựng SELECT động bằng allowlist

### 5.1. Chọn cột sắp xếp từ danh sách cố định

Giả sử giao diện cho phép sắp xếp đơn hàng theo thời điểm tạo hoặc tổng tiền. Ứng dụng ánh xạ lựa chọn giao diện sang tên cột được định nghĩa trong code:

~~~java
String orderByColumn;

switch (requestedSort) {
    case "created":
        orderByColumn = "created_at";
        break;
    case "total":
        orderByColumn = "total";
        break;
    default:
        throw new IllegalArgumentException("Unsupported sort field");
}
~~~

Hướng sắp xếp cũng cần được giới hạn:

~~~java
String direction;

if ("asc".equalsIgnoreCase(requestedDirection)) {
    direction = "ASC";
} else if ("desc".equalsIgnoreCase(requestedDirection)) {
    direction = "DESC";
} else {
    throw new IllegalArgumentException("Unsupported sort direction");
}
~~~

Sau khi xác thực cấu trúc, ghép phần đã chọn vào SQL; các giá trị lọc vẫn bind:

~~~java
String sql =
    "SELECT order_id, customer_id, status, total, created_at " +
    "FROM orders " +
    "WHERE customer_id = ? " +
    "ORDER BY " + orderByColumn + " " + direction + " " +
    "LIMIT ?";

PreparedStatement statement = connection.prepareStatement(sql);
statement.setLong(1, customerId);
statement.setInt(2, pageSize);
~~~

Trong ví dụ, chỉ hai thành phần đã được chọn từ tập cố định được ghép vào SQL. customerId và pageSize là giá trị dữ liệu nên được bind.

### 5.2. Allowlist phải ánh xạ giá trị, không chỉ kiểm tra sơ sài

Một cách rõ ràng hơn là dùng map từ khóa giao diện sang identifier:

~~~java
Map<String, String> allowedSortColumns = Map.of(
    "created", "created_at",
    "total", "total",
    "status", "status"
);

String orderByColumn = allowedSortColumns.get(requestedSort);
if (orderByColumn == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}
~~~

Ứng dụng không ghép nguyên văn requestedSort. Nó chỉ lấy identifier từ map do lập trình viên định nghĩa. Nếu người dùng gửi created_at DESC; DROP TABLE orders, giá trị đó không có trong map và bị từ chối.

Không nên dùng cách kiểm tra kiểu “chỉ cho phép ký tự chữ, số và dấu gạch dưới” làm biện pháp duy nhất. Một identifier hợp lệ về cú pháp vẫn có thể là đối tượng ngoài phạm vi mà tính năng được phép truy cập.

### 5.3. Chọn bảng động

Nếu một báo cáo được phép đọc một trong một số bảng định sẵn, hãy ánh xạ tên logic sang tên bảng:

~~~java
Map<String, String> allowedTables = Map.of(
    "current", "orders",
    "archive", "orders_archive"
);

String tableName = allowedTables.get(requestedDataset);
if (tableName == null) {
    throw new IllegalArgumentException("Unsupported dataset");
}

String sql =
    "SELECT order_id, status, created_at FROM " + tableName +
    " WHERE customer_id = ?";

PreparedStatement statement = connection.prepareStatement(sql);
statement.setLong(1, customerId);
~~~

Tên bảng là cấu trúc nên được chọn từ allowlist. customerId vẫn là giá trị nên bind. Nếu hai bảng có schema hoặc quyền truy cập khác nhau, ứng dụng phải kiểm tra quyền tương ứng cho từng lựa chọn.

## 6. Bind giá trị trong các điều kiện SELECT

### 6.1. Điều kiện bằng

~~~sql
SELECT order_id, total
FROM orders
WHERE customer_id = ?;
~~~

Dùng bind cho khóa tìm kiếm giúp cùng câu SQL có thể chạy với nhiều customer_id.

### 6.2. Khoảng giá trị

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE created_at >= ?
  AND created_at < ?
ORDER BY created_at;
~~~

Hai mốc thời gian là dữ liệu. Hãy truyền đúng kiểu thời gian từ ứng dụng, tránh format thành chuỗi SQL bằng nối thủ công.

### 6.3. LIKE và ký tự đại diện

Có thể bind pattern cho LIKE:

~~~sql
SELECT customer_id, full_name
FROM customers
WHERE full_name LIKE ?;
~~~

Nếu muốn tìm chuỗi con, ứng dụng có thể tạo pattern %keyword% rồi bind như một giá trị:

~~~text
parameter = "%An%"
~~~

Binding ngăn nội dung keyword trở thành cú pháp SQL, nhưng % và _ vẫn có ý nghĩa wildcard của LIKE. Nếu yêu cầu tìm đúng ký tự % hoặc _ theo nghĩa literal, phải escape wildcard theo quy tắc LIKE và khai báo mệnh đề ESCAPE phù hợp.

Ví dụ dùng dấu ! làm ký tự escape:

~~~sql
SELECT customer_id, full_name
FROM customers
WHERE full_name LIKE ? ESCAPE '!';
~~~

Ứng dụng cần biến đổi ! thành !!, % thành !% và _ thành !_ trước khi thêm wildcard tìm kiếm theo quy tắc đã chọn. Đây là xử lý ngữ nghĩa pattern, khác với xử lý SQL injection.

### 6.4. NULL

Để tìm giá trị NULL, dùng IS NULL:

~~~sql
SELECT order_id
FROM orders
WHERE shipped_at IS NULL;
~~~

Không dùng shipped_at = ? rồi bind NULL nếu mục tiêu là kiểm tra NULL. Phép so sánh bằng với NULL cho kết quả UNKNOWN; SQL cần IS NULL hoặc IS NOT NULL.

Nếu điều kiện có thể tùy chọn, ứng dụng có thể chọn giữa hai câu SQL cố định:

~~~sql
-- Khi không lọc theo shipped_at
SELECT order_id
FROM orders;

-- Khi chỉ lấy hàng chưa giao
SELECT order_id
FROM orders
WHERE shipped_at IS NULL;
~~~

Không cần cố biến NULL thành một identifier hoặc toán tử thông qua placeholder.

## 7. Danh sách IN và số lượng placeholder

Một placeholder đại diện cho một giá trị, không phải danh sách nhiều giá trị:

~~~sql
-- Không có nghĩa là một danh sách được bind
SELECT order_id
FROM orders
WHERE status IN (?);
~~~

Nếu bind chuỗi PAID,SHIPPED, MySQL xem đó là một giá trị duy nhất, không tự tách thành hai phần tử.

Khi danh sách có số phần tử thay đổi, ứng dụng tạo đúng số placeholder rồi bind từng giá trị. Số lượng placeholder được tạo từ độ dài danh sách, còn nội dung từng phần tử vẫn bind:

~~~java
List<String> statuses = List.of("PAID", "SHIPPED");

String placeholders = String.join(
    ", ",
    Collections.nCopies(statuses.size(), "?")
);

String sql =
    "SELECT order_id, status FROM orders " +
    "WHERE status IN (" + placeholders + ")";

PreparedStatement statement = connection.prepareStatement(sql);
for (int i = 0; i < statuses.size(); i++) {
    statement.setString(i + 1, statuses.get(i));
}
~~~

Danh sách rỗng cần được xử lý riêng. Không tạo IN (); hãy trả kết quả rỗng ở tầng ứng dụng hoặc dùng một câu SQL cố định luôn sai như WHERE 1 = 0, tùy thiết kế.

Với danh sách rất lớn, hàng trăm hoặc hàng nghìn phần tử, cân nhắc bảng tạm, bảng staging hoặc một phương thức truyền tập giá trị phù hợp thay vì tạo câu SQL với quá nhiều marker.

## 8. LIMIT và OFFSET

LIMIT điều khiển số hàng trả về:

~~~sql
SELECT order_id, status
FROM orders
ORDER BY created_at DESC
LIMIT ? OFFSET ?;
~~~

Trong prepared statement của MySQL, marker có thể dùng cho giá trị LIMIT/OFFSET. Driver và API có thể áp dụng quy tắc kiểu dữ liệu riêng; hãy truyền số nguyên và kiểm tra hỗ trợ của connector.

Ứng dụng nên xác thực:

- page_size là số nguyên dương.
- page_size không vượt giới hạn tối đa được phép.
- offset không âm và không vượt giới hạn nghiệp vụ.

Bind parameter không ngăn người dùng yêu cầu LIMIT 2000000000. Nó ngăn giá trị đó thay đổi cú pháp; validation vẫn cần để kiểm soát chi phí truy vấn.

OFFSET lớn có thể khiến MySQL phải đọc và bỏ qua nhiều hàng trước khi trả trang. Với bảng lớn, cân nhắc keyset pagination:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
~~~

Các giá trị cursor và page size đều là dữ liệu nên bind. Cần có index phù hợp với thứ tự lọc/sắp xếp và dùng cặp cột tạo thứ tự ổn định, chẳng hạn created_at kết hợp khóa chính.

## 9. Prepared statement trong MySQL

### 9.1. SQL PREPARE, EXECUTE và DEALLOCATE

MySQL hỗ trợ prepared statement ở cấp SQL:

~~~sql
PREPARE find_orders FROM
    'SELECT order_id, status, total
     FROM orders
     WHERE customer_id = ?
       AND status = ?';

SET @customer_id = 42;
SET @status = 'PAID';

EXECUTE find_orders USING @customer_id, @status;

DEALLOCATE PREPARE find_orders;
~~~

Các bước:

1. PREPARE phân tích và chuẩn bị câu SQL có marker.
2. SET gán giá trị cho user variables dùng khi thực thi.
3. EXECUTE truyền giá trị theo thứ tự marker.
4. DEALLOCATE PREPARE giải phóng prepared statement có tên đó.

User variable trong ví dụ là biến session, có tiền tố @. Chúng khác với local variable trong stored procedure.

### 9.2. Prepared statement trong driver

Trong ứng dụng, nên dùng API prepared statement của driver. Driver quản lý việc gửi statement, kiểu dữ liệu và giá trị bind theo giao thức mà nó hỗ trợ.

Ví dụ JDBC:

~~~java
String sql = """
    SELECT order_id, status, total
    FROM orders
    WHERE customer_id = ?
      AND status = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setString(2, status);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            String orderStatus = resultSet.getString("status");
            BigDecimal total = resultSet.getBigDecimal("total");
        }
    }
}
~~~

JDBC dùng chỉ số bắt đầu từ 1. Các setter như setLong, setString, setBigDecimal và setTimestamp giúp driver truyền giá trị theo kiểu phù hợp. Dùng try-with-resources để đóng statement và result set.

Ví dụ Python với mysql-connector-python:

~~~python
sql = """
    SELECT order_id, status, total
    FROM orders
    WHERE customer_id = %s
      AND status = %s
"""

cursor.execute(sql, (customer_id, status))
rows = cursor.fetchall()
~~~

Connector Python này dùng %s làm placeholder ở API của driver; đây không phải cú pháp parameter marker của SQL PREPARE phía MySQL. Placeholder cụ thể phụ thuộc thư viện. Luôn đọc tài liệu connector và truyền tham số qua đối số riêng của execute; không tự thay %s bằng format string.

### 9.3. Server-side và client-side prepared statement

Một số driver có thể hỗ trợ prepared statement phía server qua giao thức nhị phân; một số chế độ có thể mô phỏng hoặc chuẩn bị ở phía client. Chi tiết phụ thuộc connector, cấu hình và phiên bản.

Dù cơ chế triển khai khác nhau, ứng dụng vẫn nên dùng API bind parameter chính thức. Không tự nối chuỗi hoặc tự quote giá trị để giả lập binding. Khi cần xác nhận server-side prepare có được sử dụng, hãy kiểm tra cấu hình và tài liệu driver, hoặc quan sát thống kê prepared statement trên server.

## 10. Kiểu dữ liệu của parameter và chuyển đổi

Bind parameter theo đúng kiểu giúp MySQL xử lý biểu thức rõ ràng hơn:

| Giá trị ứng dụng | Kiểu bind gợi ý |
|---|---|
| Khóa BIGINT | setLong trong JDBC |
| INT | setInt |
| VARCHAR | setString |
| DECIMAL | setBigDecimal |
| DATE | setDate |
| DATETIME/TIMESTAMP | setTimestamp hoặc kiểu thời gian phù hợp với driver |
| Boolean | setBoolean nếu ánh xạ phù hợp với schema |

MySQL có thể chuyển đổi kiểu trong biểu thức. Tuy nhiên, bind chuỗi 42 cho cột số có thể khiến server phải chuyển đổi; truyền số nguyên đúng kiểu thường rõ ràng hơn.

Đặc biệt với ngày giờ, hãy hiểu timezone behavior của driver và session. JDBC Timestamp có thể chịu ảnh hưởng timezone của JVM/Calendar và cấu hình driver; nếu lưu TIMESTAMP hoặc DATETIME theo UTC, cần thống nhất chính sách chuyển đổi ở cả ứng dụng lẫn session.

Với DECIMAL, dùng kiểu thập phân chính xác ở ứng dụng như BigDecimal thay vì double khi xử lý tiền tệ. Binding đúng kiểu không thay thế việc chọn precision/scale phù hợp cho cột.

## 11. Dynamic SQL an toàn cho nhiều điều kiện lọc

Không phải mọi truy vấn động đều nguy hiểm. Vấn đề nằm ở nguồn của đoạn SQL được ghép.

Một cách triển khai an toàn là xây câu lệnh từ các mảnh cấu trúc cố định do chương trình định nghĩa, còn mọi giá trị đều bind:

~~~java
StringBuilder sql = new StringBuilder(
    "SELECT order_id, customer_id, status, total " +
    "FROM orders WHERE 1 = 1"
);

List<Object> parameters = new ArrayList<>();

if (customerId != null) {
    sql.append(" AND customer_id = ?");
    parameters.add(customerId);
}

if (status != null) {
    sql.append(" AND status = ?");
    parameters.add(status);
}

if (createdAfter != null) {
    sql.append(" AND created_at >= ?");
    parameters.add(createdAfter);
}
~~~

Các đoạn AND ... = ? được viết cố định trong code; chỉ quyết định có thêm đoạn nào. Giá trị tương ứng được đưa vào danh sách parameters. Khi tạo PreparedStatement, ứng dụng bind từng giá trị theo thứ tự đã thêm.

Không ghép trực tiếp nội dung người dùng vào sql.append(...). Nếu có trường hợp chọn cột, bảng hoặc hướng sắp xếp, phải dùng allowlist như phần trước.

## 12. Dynamic SQL trong stored procedure

Stored procedure có thể dùng SQL động với PREPARE. Ví dụ dưới đây cho phép chọn một trong hai cột sắp xếp:

~~~sql
DELIMITER //

CREATE PROCEDURE list_orders(
    IN p_customer_id BIGINT,
    IN p_sort_key VARCHAR(20),
    IN p_sort_direction VARCHAR(4)
)
BEGIN
    DECLARE v_order_clause VARCHAR(80);
    DECLARE v_sql TEXT;

    IF p_sort_key = 'created' THEN
        SET v_order_clause = 'created_at';
    ELSEIF p_sort_key = 'total' THEN
        SET v_order_clause = 'total';
    ELSE
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Unsupported sort field';
    END IF;

    IF UPPER(p_sort_direction) = 'ASC' THEN
        SET v_order_clause = CONCAT(v_order_clause, ' ASC');
    ELSEIF UPPER(p_sort_direction) = 'DESC' THEN
        SET v_order_clause = CONCAT(v_order_clause, ' DESC');
    ELSE
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Unsupported sort direction';
    END IF;

    SET v_sql = CONCAT(
        'SELECT order_id, customer_id, status, total, created_at ',
        'FROM orders WHERE customer_id = ? ORDER BY ',
        v_order_clause
    );

    SET @sql = v_sql;
    SET @bound_customer_id = p_customer_id;
    PREPARE order_stmt FROM @sql;
    EXECUTE order_stmt USING @bound_customer_id;
    DEALLOCATE PREPARE order_stmt;
END//

DELIMITER ;
~~~

Ví dụ minh họa các nguyên tắc:

- p_customer_id là giá trị dữ liệu nên được bind bằng marker.
- p_sort_key được ánh xạ sang một identifier cố định.
- p_sort_direction được kiểm tra và chỉ chấp nhận ASC hoặc DESC.
- Dữ liệu người gọi không được ghép nguyên văn vào câu SQL.

Trong stored program, PREPARE nhận câu lệnh từ string literal hoặc user variable; vì vậy ví dụ sao chép local variable v_sql sang user variable @sql trước khi PREPARE. EXECUTE USING cũng dùng user variables, không dùng trực tiếp local routine variable. Prepared statement tạo trong stored procedure cần được deallocate sau khi dùng. SQL prepared statement không được dùng theo cách này trong stored function hoặc trigger.

Nếu procedure có thể thoát sớm do lỗi sau PREPARE, nên thiết kế handler để bảo đảm statement được giải phóng phù hợp. Ví dụ trên tập trung minh họa binding và allowlist; triển khai sản xuất cần bổ sung xử lý lỗi theo chuẩn dự án.

## 13. Identifier quoting và các giới hạn của nó

MySQL quote identifier bằng backtick:

~~~sql
SELECT order_id
FROM shop.orders;
~~~

Nếu identifier chứa backtick, cần nhân đôi backtick bên trong identifier khi quote. Tuy nhiên, không nên tự viết một hàm quote identifier đơn giản rồi dùng nó cho mọi đầu vào người dùng.

Quy trình đúng:

1. Xác định tính năng được phép chọn đối tượng nào.
2. Ánh xạ lựa chọn logic sang identifier do ứng dụng định nghĩa.
3. Quote identifier theo cú pháp MySQL nếu cần.
4. Ghép identifier đã kiểm soát vào SQL.
5. Bind mọi giá trị dữ liệu còn lại.

Quote chỉ bảo vệ cách parser nhận diện ranh giới identifier. Nó không thay thế allowlist, authorization hoặc kiểm tra schema.

## 14. Các lỗi thiết kế phổ biến

### 14.1. Đặt placeholder trong dấu nháy

Sai:

~~~sql
SELECT order_id
FROM orders
WHERE status = '?';
~~~

Ở đây dấu hỏi chấm nằm trong literal chuỗi nên không phải parameter marker. Placeholder phải xuất hiện ở vị trí biểu thức:

~~~sql
SELECT order_id
FROM orders
WHERE status = ?;
~~~

Không tự thêm dấu nháy quanh placeholder. Driver sẽ truyền giá trị theo giao thức và kiểu dữ liệu.

### 14.2. Bind tên cột rồi mong MySQL hiểu là identifier

Sai về mục tiêu:

~~~sql
SELECT ?
FROM orders;
~~~

Nếu bind total, kết quả là biểu thức giá trị chuỗi, không phải cột total. Hãy chọn identifier từ allowlist và ghép vào cấu trúc SQL.

### 14.3. Bind cả mệnh đề ORDER BY

Sai:

~~~sql
SELECT order_id, total
FROM orders
ORDER BY ?;
~~~

Marker ở đây là biểu thức giá trị. Nó không thể thay cho total DESC. Chọn cột và hướng sắp xếp bằng allowlist.

### 14.4. Bind một danh sách bằng một tham số

Sai về ý nghĩa:

~~~sql
SELECT order_id
FROM orders
WHERE status IN (?);
~~~

Bind PAID,SHIPPED không tạo ra hai phần tử. Tạo một marker cho mỗi phần tử và bind từng giá trị.

### 14.5. Nối chuỗi rồi tự escape

Tự thay dấu nháy hoặc xóa ký tự đặc biệt dễ sai khi có nhiều character set, SQL mode và ngữ cảnh literal khác nhau. Dùng prepared statement cho giá trị; dùng allowlist cho cấu trúc.

### 14.6. Nghĩ rằng bind parameter thay thế authorization

Một truy vấn bind đúng vẫn có thể cho phép người dùng đọc đơn hàng của khách hàng khác nếu ứng dụng không kiểm tra quyền. Hãy đưa điều kiện tenant, owner hoặc phạm vi truy cập vào logic truy vấn và kiểm thử phân quyền riêng.

## 15. Checklist xây SELECT an toàn

Trước khi đưa một truy vấn vào ứng dụng, kiểm tra:

1. Câu SQL có cấu trúc cố định ở mức tối đa có thể không?
2. Mọi giá trị dữ liệu đã được truyền bằng API bind parameter chưa?
3. Có placeholder nào bị đặt trong dấu nháy hoặc dùng để thay identifier không?
4. Tên bảng/cột, sort direction và đoạn cú pháp động có được chọn từ allowlist không?
5. Danh sách IN có số placeholder khớp số giá trị và xử lý danh sách rỗng không?
6. LIKE wildcard có được xử lý đúng với yêu cầu tìm kiếm literal hay pattern không?
7. NULL được kiểm tra bằng IS NULL/IS NOT NULL khi cần không?
8. LIMIT/OFFSET có được validate để tránh truy vấn quá lớn không?
9. Kiểu bind có tương thích với kiểu cột không?
10. Ứng dụng có kiểm tra authorization và giới hạn tenant/owner không?
11. Statement, result set và connection có được quản lý vòng đời đúng không?
12. Có kiểm thử đầu vào chứa dấu nháy, comment marker, ký tự Unicode và payload SQL injection không?

## 16. Ví dụ tổng hợp: tìm đơn hàng với bộ lọc và sắp xếp

Yêu cầu: tìm đơn hàng theo khách hàng, có thể lọc trạng thái, chọn cách sắp xếp và phân trang.

Phần cấu trúc được chọn:

~~~java
Map<String, String> sortColumns = Map.of(
    "created", "created_at",
    "total", "total"
);

String orderBy = sortColumns.get(sortKey);
if (orderBy == null) {
    throw new IllegalArgumentException("Invalid sort key");
}

String direction;
if ("asc".equalsIgnoreCase(sortDirection)) {
    direction = "ASC";
} else if ("desc".equalsIgnoreCase(sortDirection)) {
    direction = "DESC";
} else {
    throw new IllegalArgumentException("Invalid sort direction");
}
~~~

Tạo câu lệnh và bind giá trị:

~~~java
StringBuilder sql = new StringBuilder(
    "SELECT order_id, customer_id, status, total, created_at " +
    "FROM orders WHERE customer_id = ?"
);

List<Object> values = new ArrayList<>();
values.add(customerId);

if (status != null) {
    sql.append(" AND status = ?");
    values.add(status);
}

sql.append(" ORDER BY ")
   .append(orderBy)
   .append(" ")
   .append(direction)
   .append(", order_id DESC LIMIT ?");

values.add(pageSize);

try (PreparedStatement statement = connection.prepareStatement(sql.toString())) {
    for (int i = 0; i < values.size(); i++) {
        Object value = values.get(i);
        if (value instanceof Long) {
            statement.setLong(i + 1, (Long) value);
        } else if (value instanceof String) {
            statement.setString(i + 1, (String) value);
        } else if (value instanceof Integer) {
            statement.setInt(i + 1, (Integer) value);
        }
    }

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            // Map hàng kết quả sang đối tượng của ứng dụng.
        }
    }
}
~~~

Trong code sản xuất, nên dùng lớp truy cập dữ liệu hoặc helper có kiểu rõ ràng thay vì danh sách Object và nhánh instanceof chung. Ví dụ trên minh họa thứ tự parameter: customerId, status nếu có, rồi pageSize. Hãy validate pageSize trước khi bind.

Điểm cần nhớ:

- customerId, status và pageSize là dữ liệu được bind.
- orderBy và direction là cấu trúc đã được allowlist.
- Tên bảng được cố định trong SQL.
- Không có đầu vào người dùng nào được ghép trực tiếp thành đoạn SQL chưa kiểm soát.

## Kết luận

Bind parameter dành cho giá trị dữ liệu trong câu SQL: mã định danh, chuỗi tìm kiếm, ngày giờ, số tiền và giới hạn phân trang. Placeholder không thể thay tên bảng, tên cột, từ khóa hoặc một đoạn cú pháp SQL. Khi cần SQL động, hãy chọn cấu trúc từ allowlist, quote identifier đúng cú pháp rồi bind mọi giá trị còn lại.

Kết hợp prepared statement, allowlist, kiểm tra kiểu và phân quyền giúp câu SELECT an toàn trước SQL injection và dễ bảo trì. Hãy luôn phân biệt dữ liệu người dùng cung cấp với cấu trúc mà ứng dụng cho phép lựa chọn; đây là ranh giới quan trọng nhất khi xây dựng truy vấn động trong MySQL.
