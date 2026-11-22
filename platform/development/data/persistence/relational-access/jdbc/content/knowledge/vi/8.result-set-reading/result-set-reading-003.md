# Đọc cột theo chỉ số và theo nhãn

Khi ứng dụng Java thực thi câu lệnh `SELECT` bằng **JDBC (Java Database Connectivity)**, JDBC driver trả kết quả dưới dạng `java.sql.ResultSet`. Mỗi hàng có các cột theo **thứ tự mà câu truy vấn trả về**. Để đọc giá trị, lập trình viên thường sử dụng một trong hai dạng phương thức:

- **Theo chỉ số:** `resultSet.getLong(1)`, `resultSet.getString(2)`, `resultSet.getBigDecimal(3)`.
- **Theo nhãn:** `resultSet.getLong("order_id")`, `resultSet.getString("customer_name")`, `resultSet.getBigDecimal("total_amount")`.

Cả hai cách đều gọi những phương thức `getXxx(...)` trên cùng một `ResultSet`. Khác biệt nằm ở **cách xác định cột cần đọc**, không nằm ở việc hai cách thực thi hai truy vấn riêng. Chọn đúng cách giúp mã rõ nghĩa, giảm lỗi khi chỉnh sửa `SELECT` và ánh xạ dữ liệu SQL sang đối tượng Java chính xác.

## 1. Phải di chuyển con trỏ trước khi đọc cột

Ngay sau `executeQuery()`, con trỏ của `ResultSet` thông thường ở vị trí **trước hàng đầu tiên**. Cần gọi `next()` để chuyển đến hàng hợp lệ; `next()` trả `true` khi có hàng mới và `false` khi không còn hàng.

```java
String sql = "SELECT id, full_name FROM customers ORDER BY id";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql);
     ResultSet rows = statement.executeQuery()) {

    while (rows.next()) {
        long id = rows.getLong(1);
        String name = rows.getString(2);
        System.out.println(id + ": " + name);
    }
}
```

Đoạn mã giả định `dataSource` đã được cấu hình và bảng `customers` tồn tại. Nếu không có hàng nào, vòng lặp không thực hiện lần nào. Không gọi `getString(...)` trước `next()` đầu tiên hoặc sau khi `next()` trả `false`; hành vi đọc cột khi con trỏ ở vị trí không hợp lệ có thể gây `SQLException`.

Sơ đồ vị trí con trỏ:

```text
Vừa tạo ResultSet        next() = true         next() = true        next() = false
   trước hàng 1      -->     hàng 1       -->      hàng 2      -->   sau hàng cuối
   chưa đọc được             đọc cột được        đọc cột được         chưa đọc được
```

Khi truy vấn có thể trả đúng một hàng, dùng `if (rows.next())`. Khi cần đọc tất cả các hàng, dùng `while (rows.next())`. Việc chọn **chỉ số hay nhãn** chỉ có ý nghĩa khi con trỏ đang đứng trên một hàng có thể đọc.

## 2. Đọc theo chỉ số: `getXxx(int columnIndex)`

Trong JDBC, **chỉ số cột bắt đầu từ 1**, không bắt đầu từ 0 như phần lớn mảng Java:

```sql
SELECT id, full_name, loyalty_points
FROM customers;
```

| Cột trong kết quả | Chỉ số JDBC | Phương thức đọc ví dụ |
|---|---:|---|
| `id` | 1 | `rows.getLong(1)` |
| `full_name` | 2 | `rows.getString(2)` |
| `loyalty_points` | 3 | `rows.getInt(3)` |

```java
if (rows.next()) {
    long id = rows.getLong(1);
    String fullName = rows.getString(2);
    int points = rows.getInt(3);
}
```

**Chỉ số tương ứng với vị trí trong danh sách cột được `SELECT` trả về**, không phải thứ tự cột được khai báo trong bảng. Ví dụ:

```sql
SELECT full_name, id, loyalty_points
FROM customers;
```

Trong truy vấn mới, `getString(1)` đọc `full_name`, còn `getLong(2)` đọc `id`. Nếu vẫn dùng `getLong(1)`, driver có thể báo lỗi chuyển đổi kiểu hoặc cố chuyển chuỗi thành số theo quy tắc riêng; kết quả không còn đúng với ý định ban đầu.

### Biểu thức và cột tính toán cũng chiếm vị trí

```sql
SELECT id, quantity * unit_price AS line_total, unit_price
FROM order_items;
```

Ở đây, `getBigDecimal(2)` đọc **kết quả biểu thức** `quantity * unit_price`. Cột thứ hai của bảng gốc không liên quan đến vị trí đó. Tương tự, `COUNT(*)`, `CASE ... END` hoặc hàm SQL cũng chiếm một vị trí khi có mặt trong danh sách `SELECT`.

### Khi nào đọc theo chỉ số phù hợp?

Đọc theo chỉ số thuận tiện với truy vấn rất ngắn, cấu trúc kết quả cố định hoặc các hàm tiện ích xử lý cột theo vị trí. Với một truy vấn chỉ trả một cột, ví dụ `SELECT COUNT(*) ...`, `getLong(1)` thường rõ ràng và đơn giản:

```java
try (PreparedStatement statement =
         connection.prepareStatement("SELECT COUNT(*) FROM customers");
     ResultSet rows = statement.executeQuery()) {
    if (rows.next()) {
        long total = rows.getLong(1);
        System.out.println(total);
    }
}
```

Nhược điểm chính là **phụ thuộc vào thứ tự cột**. Nếu thêm, bớt hoặc đảo vị trí cột trong SQL nhưng không sửa mã ánh xạ, ứng dụng có thể đọc nhầm dữ liệu. Chỉ số `0` hoặc lớn hơn số cột của kết quả không hợp lệ và có thể gây `SQLException`.

## 3. Đọc theo nhãn: `getXxx(String columnLabel)`

Tham số `String` trong các phương thức đọc cột JDBC là **nhãn cột của tập kết quả** (`columnLabel`). Nhãn có thể là tên cột được truy vấn trả về hoặc bí danh đặt bằng `AS`.

```sql
SELECT id AS customer_id, full_name AS customer_name, loyalty_points
FROM customers;
```

Các lời gọi tương ứng là:

```java
long id = rows.getLong("customer_id");
String name = rows.getString("customer_name");
int points = rows.getInt("loyalty_points");
```

Sử dụng nhãn giúp người đọc thấy rõ ý nghĩa từng giá trị mà không phải đếm vị trí. Khi cùng truy vấn ấy thay đổi thứ tự cột:

```sql
SELECT loyalty_points, full_name AS customer_name, id AS customer_id
FROM customers;
```

thì các lời gọi `getLong("customer_id")`, `getString("customer_name")` và `getInt("loyalty_points")` **vẫn trỏ đến đúng nhãn**. Tuy nhiên, việc **đổi tên bí danh** hoặc bỏ hẳn một cột khỏi `SELECT` sẽ ảnh hưởng trực tiếp đến mã đọc theo nhãn.

### Cột được đặt `AS` phải đọc bằng nhãn kết quả

```sql
SELECT total_amount AS invoice_total
FROM invoices;
```

```java
BigDecimal total = rows.getBigDecimal("invoice_total"); // Rõ ràng, đúng nhãn.
```

Không nên dựa vào `getBigDecimal("total_amount")` trong trường hợp này: hợp đồng API JDBC tra cứu **column label**, và nhãn của cột đã được đặt thành `invoice_total`. Một số driver có thể có hành vi tìm kiếm mở rộng theo tên cột gốc, nhưng ứng dụng cần viết theo nhãn mà truy vấn công bố để dễ chuyển DBMS.

Nếu không có `AS`, nhãn thường chính là tên cột. Với biểu thức `COUNT(*)`, `SUM(...)` hoặc phép nối chuỗi, nên đặt bí danh tường minh thay vì dựa vào tên biểu thức do DBMS tạo:

```sql
SELECT COUNT(*) AS customer_count
FROM customers;
```

```java
long totalCustomers = rows.getLong("customer_count");
```

### Nhãn không phải đường dẫn `table.column`

Ở câu truy vấn nhiều bảng, `o.id` trong SQL mô tả cột `id` thuộc bảng/alias `o`. Nhưng chuỗi truyền vào `getLong(String)` thường phải là **nhãn của kết quả**, không phải tên cột được viết kèm alias bảng. Để tránh nhầm lẫn, hãy chủ động đặt:

```sql
SELECT o.id AS order_id, c.id AS customer_id
FROM orders o
JOIN customers c ON c.id = o.customer_id;
```

```java
long orderId = rows.getLong("order_id");
long customerId = rows.getLong("customer_id");
```

Không mặc định rằng `getLong("o.id")` hoặc `getLong("c.id")` có ý nghĩa tương tự cú pháp tham chiếu cột trong SQL.

## 4. Một ví dụ đầy đủ: cùng kết quả, hai cách ánh xạ

Giả sử bảng `orders` chứa `id`, `customer_id`, `total_amount`, `status` và bảng `customers` chứa `id`, `full_name`. Ứng dụng cần đọc đơn hàng đã thanh toán, kèm tên khách hàng.

```sql
SELECT
    o.id           AS order_id,
    c.full_name    AS customer_name,
    o.total_amount AS total_amount
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = ?
ORDER BY o.id;
```

Với danh sách cột này, hai nhóm lời gọi là tương đương về **cột được chọn**:

| Vị trí kết quả | Nhãn | Theo chỉ số | Theo nhãn |
|---:|---|---|---|
| 1 | `order_id` | `rows.getLong(1)` | `rows.getLong("order_id")` |
| 2 | `customer_name` | `rows.getString(2)` | `rows.getString("customer_name")` |
| 3 | `total_amount` | `rows.getBigDecimal(3)` | `rows.getBigDecimal("total_amount")` |

Ví dụ Java 17+ dưới đây sử dụng record để chứa dữ liệu và đọc **theo nhãn**:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderReader {
    public record OrderView(long orderId, String customerName,
                            BigDecimal totalAmount) {}

    private final DataSource dataSource;

    public OrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<OrderView> findPaidOrders() throws SQLException {
        String sql = """
                SELECT o.id AS order_id,
                       c.full_name AS customer_name,
                       o.total_amount AS total_amount
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                WHERE o.status = ?
                ORDER BY o.id
                """;

        List<OrderView> orders = new ArrayList<>();
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, "PAID");

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    long orderId = rows.getLong("order_id");
                    String customerName = rows.getString("customer_name");
                    BigDecimal total = rows.getBigDecimal("total_amount");
                    orders.add(new OrderView(orderId, customerName, total));
                }
            }
        }
        return orders;
    }
}
```

Trong cùng phương thức ấy, ba phép đọc có thể thay bằng:

```java
long orderId = rows.getLong(1);
String customerName = rows.getString(2);
BigDecimal total = rows.getBigDecimal(3);
```

và vẫn cho kết quả tương đương **miễn thứ tự `SELECT` không đổi**. Ví dụ này minh họa khác biệt ở cách nhận diện cột; việc chọn `BigDecimal` cho tiền và `long` cho ID vẫn cần phù hợp với kiểu SQL, miền giá trị và khả năng `NULL` của cột.

## 5. Trùng nhãn khi `JOIN`: nguồn lỗi khó thấy

Khi ghép bảng, nhiều bảng có cột `id`, `name`, `created_at`. Xét truy vấn:

```sql
SELECT o.id, c.id, o.created_at, c.created_at
FROM orders o
JOIN customers c ON c.id = o.customer_id;
```

Nếu driver trả nhãn ngắn là `id` cho cả hai cột đầu, lời gọi `rows.getLong("id")` là **mơ hồ về mặt ý định nghiệp vụ**. Theo hợp đồng JDBC, nếu nhiều cột cùng có nhãn khớp, thao tác tra cứu theo nhãn chọn **cột khớp đầu tiên**; ứng dụng có thể âm thầm đọc ID của đơn hàng trong khi muốn ID khách hàng.

Giải pháp là đặt **nhãn duy nhất, có ý nghĩa**:

```sql
SELECT
    o.id         AS order_id,
    c.id         AS customer_id,
    o.created_at AS order_created_at,
    c.created_at AS customer_created_at
FROM orders o
JOIN customers c ON c.id = o.customer_id;
```

```java
long orderId = rows.getLong("order_id");
long customerId = rows.getLong("customer_id");
```

**Đừng dùng `SELECT *` trong mã ánh xạ đòi hỏi hợp đồng cột ổn định** nếu có thể liệt kê cột cần dùng. Việc thêm một cột hoặc thay đổi thứ tự bảng trong `JOIN` có thể làm lệch chỉ số, tạo thêm nhãn trùng hoặc làm ứng dụng tải các cột lớn không cần thiết.

Đặt alias rõ ràng cũng hữu ích khi **dùng ORM nhẹ, row mapper, thư viện chuyển `ResultSet` thành JSON** hoặc bất kỳ logic nào xây tên trường từ nhãn cột.

## 6. Xem chỉ số, nhãn và tên cột bằng `ResultSetMetaData`

Không cần đoán cấu trúc một `ResultSet`. JDBC cung cấp `ResultSetMetaData` để đọc số cột và thông tin của từng cột:

```java
try (PreparedStatement statement = connection.prepareStatement(
         "SELECT id AS customer_id, full_name AS customer_name FROM customers");
     ResultSet rows = statement.executeQuery()) {

    ResultSetMetaData meta = rows.getMetaData();

    for (int i = 1; i <= meta.getColumnCount(); i++) {
        System.out.printf(
            "index=%d, label=%s, name=%s, type=%d%n",
            i,
            meta.getColumnLabel(i),
            meta.getColumnName(i),
            meta.getColumnType(i)
        );
    }
}
```

Đoạn mã cần `import java.sql.ResultSetMetaData;`. Tùy DBMS/driver, kết quả có thể tương tự:

```text
index=1, label=customer_id, name=id, type=-5
index=2, label=customer_name, name=full_name, type=12
```

Trong ví dụ minh họa, `-5` là `java.sql.Types.BIGINT`, `12` là `java.sql.Types.VARCHAR`; mã kiểu mà driver thực tế báo có thể khác tùy schema và driver.

| API | Ý nghĩa |
|---|---|
| `getColumnCount()` | Tổng số cột trong tập kết quả |
| `getColumnLabel(i)` | Nhãn dùng để hiển thị và tra cứu bằng `getXxx(String)`; thường là alias `AS` nếu có |
| `getColumnName(i)` | Tên cột theo thông tin mà driver cung cấp; có thể khác nhãn, nhất là khi dùng alias hoặc biểu thức |
| `getColumnType(i)` | Mã kiểu JDBC theo `java.sql.Types` |
| `getColumnTypeName(i)` | Tên kiểu SQL do driver báo |

Với truy vấn chứa biểu thức tính toán hoặc hàm tổng hợp, `getColumnName(i)` có thể phụ thuộc DBMS. **Dùng `getColumnLabel(i)` để kiểm tra nhãn mà API đọc cột mong đợi**, và không viết logic portable phụ thuộc việc driver luôn báo được tên cột gốc của một biểu thức.

### `findColumn(String)`: chuyển nhãn thành chỉ số

`ResultSet#findColumn("customer_name")` tìm vị trí cột theo nhãn và trả về **chỉ số 1-based**:

```java
int nameIndex = rows.findColumn("customer_name");
String name = rows.getString(nameIndex);
```

Phương thức này hữu ích cho mapper hoặc cấu trúc kết quả động. Tuy nhiên, không cần gọi `findColumn()` trước mọi `getString("customer_name")`: nhiều driver đã có cơ chế tra cứu nhãn, và muốn chọn tối ưu nào nên dựa vào phép đo với driver thực tế.

## 7. Đọc theo nhãn không thay thế lựa chọn kiểu Java

Tham số chỉ số/nhãn xác định **cột nào** được đọc; phần `getXxx` xác định **cách chuyển giá trị SQL sang Java**:

| Giá trị cần đọc | Ví dụ theo chỉ số | Ví dụ theo nhãn | Ghi chú |
|---|---|---|---|
| Số nguyên lớn | `getLong(1)` | `getLong("order_id")` | Kiểu `long` nguyên thủy không lưu được Java `null` |
| Chuỗi | `getString(2)` | `getString("customer_name")` | SQL `NULL` thường trở thành Java `null` |
| Số tiền chính xác | `getBigDecimal(3)` | `getBigDecimal("total_amount")` | Nên giữ `BigDecimal` trong tính toán tiền |
| Ngày SQL | `getDate(4)` | `getDate("issued_on")` | `java.sql.Date`; có thể chuyển sang `LocalDate` |
| Giá trị theo kiểu đích | `getObject(4, LocalDate.class)` | `getObject("issued_on", LocalDate.class)` | Yêu cầu driver hỗ trợ ánh xạ kiểu đích tương ứng |

Ví dụ, nếu cột `total_amount` dùng `DECIMAL(15,2)`, việc gọi `getDouble("total_amount")` có thể tạo ra sai số biểu diễn số thực nhị phân, dù cột được xác định đúng. Dùng `getBigDecimal("total_amount")` khi giá trị phải giữ độ chính xác thập phân.

Khi DBMS hoặc driver không hỗ trợ chuyển đổi đã yêu cầu, `getXxx(...)` có thể ném `SQLException`. Không nên đổi sang một kiểu Java không phù hợp chỉ để tránh phải sửa tên cột hoặc thứ tự `SELECT`.

## 8. Cẩn thận với SQL `NULL` và các getter kiểu nguyên thủy

Một cột `loyalty_points` kiểu `INTEGER` có thể nhận `NULL`. Khi dùng:

```java
int points = rows.getInt("loyalty_points");
```

JDBC trả `0` khi giá trị SQL là `NULL`. Như vậy, chỉ nhìn `points` không thể phân biệt **chưa có điểm** và **điểm bằng 0**. Cần gọi `wasNull()` **ngay sau getter cần kiểm tra**:

```java
int rawPoints = rows.getInt("loyalty_points");
Integer points = rows.wasNull() ? null : rawPoints;
```

Quy tắc này áp dụng cả khi đọc theo chỉ số:

```java
int rawPoints = rows.getInt(3);
Integer points = rows.wasNull() ? null : rawPoints;
```

`wasNull()` cho biết **giá trị của cột vừa được đọc** có phải SQL `NULL` hay không. Nếu gọi thêm `rows.getString("customer_name")` rồi mới gọi `wasNull()`, kết quả kiểm tra liên quan đến lần đọc `customer_name`, không còn là `loyalty_points`.

Khi driver hỗ trợ kiểu đích, có thể cân nhắc:

```java
Integer points = rows.getObject("loyalty_points", Integer.class);
```

Đối với `String`, `BigDecimal` và nhiều kiểu tham chiếu khác, getter thông dụng trả Java `null` khi giá trị SQL là `NULL`. Việc lựa chọn index/label **không làm thay đổi các quy tắc NULL này**.

## 9. Chọn chỉ số hay nhãn trong thiết kế repository?

| Tiêu chí | Đọc theo chỉ số | Đọc theo nhãn |
|---|---|---|
| Khả năng đọc hiểu | Phải đối chiếu với danh sách `SELECT` | Mục đích của cột thường rõ ngay trong code |
| Đổi thứ tự cột | Cần cập nhật ánh xạ index | Thường không ảnh hưởng nếu giữ nguyên nhãn |
| Đổi alias/tên cột trả về | Thường không ảnh hưởng nếu vị trí và kiểu giữ nguyên | Cần cập nhật chuỗi nhãn tương ứng |
| Truy vấn `COUNT(*)` chỉ một cột | `getLong(1)` gọn và rõ | Cần alias, ví dụ `COUNT(*) AS total` |
| Truy vấn `JOIN` nhiều bảng | Phải theo dõi chính xác từng vị trí | Nên dùng alias duy nhất để tránh nhãn trùng |
| Mapper xử lý schema động | Có thể lặp qua các vị trí metadata | Có thể tra cứu theo nhãn hoặc dùng `findColumn` |
| Hiệu năng | Có thể giảm chi phí tìm nhãn ở một số driver | Driver có thể cache ánh xạ; khác biệt cần đo |

**Khuyến nghị thực hành:** với repository viết SQL rõ ràng và ánh xạ nhiều trường nghiệp vụ, thường nên **dùng nhãn kết hợp alias tường minh, duy nhất**. Với truy vấn đơn giản, projection cố định hoặc thuật toán xử lý dữ liệu theo vị trí, **dùng chỉ số** là lựa chọn hợp lý.

Không nên đưa ra kết luận rằng đọc theo chỉ số **luôn** nhanh hơn đáng kể. Chi phí mạng, DBMS, truy vấn, đọc dữ liệu lớn và ánh xạ đối tượng thường có thể lớn hơn chi phí tìm nhãn. Nếu hiệu năng thực sự là nút thắt, hãy đo trên JDBC driver và workload cụ thể.

### Lưu tên nhãn vào hằng số khi nhiều nơi dùng chung

```java
private static final String COL_ORDER_ID = "order_id";
private static final String COL_TOTAL = "total_amount";

long id = rows.getLong(COL_ORDER_ID);
BigDecimal total = rows.getBigDecimal(COL_TOTAL);
```

Hằng số có thể giảm lỗi gõ nhãn và giúp cập nhật mapping tập trung. Tuy nhiên, một alias vẫn là **hợp đồng giữa câu SQL và mã đọc kết quả**; hằng số Java không tự kiểm tra được sự khớp nhau khi SQL thay đổi.

## 10. Các lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `getString(0)` gây `SQLException` | Nhầm chỉ số cột JDBC là 0-based | Bắt đầu từ 1; kiểm tra `getColumnCount()` |
| `getLong(2)` đọc nhầm ID | Đã đổi thứ tự cột trong `SELECT` | Sửa mapping index hoặc dùng alias/label |
| `getString("display_name")` báo không tìm thấy cột | Câu SQL chưa trả nhãn `display_name` | Thêm `AS display_name` và kiểm tra `getColumnLabel()` |
| `getLong("id")` trả ID của bảng sai trong `JOIN` | Có nhiều cột cùng mang nhãn `id` | Đặt nhãn `order_id` và `customer_id` duy nhất |
| `getLong("o.id")` không tìm được cột | Nhầm tham chiếu SQL `table.column` với nhãn kết quả | Đọc theo `AS order_id` hoặc chỉ số tương ứng |
| Getter cho cột số trả `0` dù dữ liệu thiếu | SQL `NULL` bị chuyển thành giá trị mặc định của kiểu nguyên thủy | Gọi `wasNull()` ngay sau getter |
| Đọc `ResultSet` sau khi đóng `PreparedStatement` | `ResultSet` phụ thuộc statement/connection đang sống | Tiêu thụ kết quả trong `try-with-resources` |
| Chỉ số không đổi nhưng kết quả ánh xạ sai sau `SELECT *` | Projection thay đổi theo schema hoặc JOIN | Liệt kê cột cần thiết và dùng nhãn ổn định |
| `getObject("date_col", LocalDate.class)` bị từ chối | Driver không hỗ trợ hoặc cột không tương thích kiểu đích | Kiểm tra loại cột, driver, phiên bản và mapping thích hợp |

Khi không chắc một câu SQL thực sự trả về những cột gì, hãy in tạm **`getColumnCount()` và từng `getColumnLabel(i)`** trong môi trường phát triển; không nên phỏng đoán cấu trúc result set từ tên bảng hoặc code cũ.

## 11. Tình huống vận dụng

**Tình huống 1 — Thay đổi projection:** Ban đầu câu SQL là `SELECT id, name, price FROM products`, mapper đọc `getLong(1)`, `getString(2)`, `getBigDecimal(3)`. Sau này SQL đổi thành `SELECT name, id, price`. Điều gì cần sửa? → Các chỉ số của `id` và `name` phải đảo lại. Nếu mapper đọc theo nhãn `id` và `name`, đổi thứ tự không ảnh hưởng khi nhãn vẫn giữ nguyên.

**Tình huống 2 — Hai bảng đều có `id`:** `SELECT o.id, c.id FROM orders o JOIN customers c ...`. `getLong("id")` có chắc đọc ID khách hàng? → Không. Theo quy tắc tìm nhãn trùng, nó chọn cột khớp đầu tiên. Hãy dùng `AS order_id`, `AS customer_id` và đọc đúng nhãn.

**Tình huống 3 — Hàm tổng hợp:** `SELECT COUNT(*) FROM orders`. Muốn đọc nhanh kết quả cần cách nào? → `getLong(1)` gọn vì chỉ một cột. Nếu muốn đọc theo nhãn, thêm `AS order_count` rồi gọi `getLong("order_count")`.

**Tình huống 4 — SQL NULL:** `getInt("discount_percent")` trả `0`. Có thể khẳng định giá trị trong DB là số 0? → Không. Phải gọi `wasNull()` ngay sau `getInt(...)` hoặc dùng `getObject(..., Integer.class)` nếu driver hỗ trợ.

**Tình huống 5 — Metadata:** Truy vấn `SELECT total * quantity AS line_total FROM order_items`. Muốn biết chuỗi nào dùng cho `getBigDecimal(String)` thì xem API nào? → `ResultSetMetaData#getColumnLabel(i)` cho nhãn `line_total`; `getColumnName(i)` không bảo đảm cung cấp tên cột gốc rõ ràng cho biểu thức.

**Tình huống 6 — Tối ưu ánh xạ:** Một vòng lặp đọc 100.000 hàng có nhiều lần `getString("customer_name")`. Có bắt buộc đổi hết sang `getString(2)`? → Không. Trước hết xác định bottleneck và đo trên driver thực tế; mã đọc theo nhãn có ưu điểm giữ được ý nghĩa nghiệp vụ, còn nhiều driver tối ưu việc tra cứu nhãn.

## Ghi nhớ

Trong JDBC, **đọc theo chỉ số `getXxx(int)` xác định cột theo vị trí 1-based của tập kết quả**, còn **đọc theo nhãn `getXxx(String)` xác định cột theo nhãn mà SQL trả về, thường là bí danh `AS`**. Cả hai cần con trỏ `ResultSet` đứng trên một hàng hợp lệ, kiểu getter phù hợp và cách xử lý SQL `NULL` đúng. Với truy vấn có nhiều cột hoặc `JOIN`, hãy đặt alias duy nhất, rõ nghĩa và kiểm tra `ResultSetMetaData` khi cần; với truy vấn đơn giản, chỉ số có thể đủ gọn. Quan trọng nhất là giữ **hợp đồng nhất quán giữa danh sách cột SQL và mã Java ánh xạ kết quả**.
