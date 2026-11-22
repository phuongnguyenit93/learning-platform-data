# Đặt bí danh để tránh cột trùng tên khi nối bảng trong JDBC

## 1. Vấn đề khi truy vấn nhiều bảng

**JDBC (Java Database Connectivity)** là API Java để truy cập cơ sở dữ liệu quan hệ. Sau khi thực thi câu `SELECT`, ứng dụng thường dùng `java.sql.ResultSet` để đọc từng hàng bằng `getLong(...)`, `getString(...)`, `getBigDecimal(...)` và các phương thức tương ứng.

Với truy vấn từ một bảng, tên cột như `id`, `name` hoặc `status` thường đủ rõ ràng. Nhưng khi nối bảng bằng `JOIN`, nhiều bảng có thể có **cột trùng tên**. Ví dụ bảng `customers` và `orders` đều có cột `id`, `created_at`, `status`. Khi cả hai cột `id` xuất hiện trong cùng kết quả, lời gọi `rs.getLong("id")` sẽ trỏ đến cột nào?

JDBC cho phép đọc theo **chỉ số cột** hoặc **nhãn cột (column label)**. Theo hợp đồng của `ResultSet`, nếu nhiều cột mang cùng một nhãn/tên được dùng cho getter, **cột khớp đầu tiên** được trả về. Vì thế, việc gọi `getLong("id")` với kết quả có hai cột `id` có thể không ném lỗi nhưng vẫn đọc nhầm ID.

Giải pháp dễ đọc, dễ bảo trì là **đặt bí danh cột SQL bằng `AS`**, bảo đảm mỗi cột được sử dụng có một tên đầu ra riêng, rồi gọi getter của JDBC bằng đúng tên bí danh.

Mục tiêu của bài trong chương **Đọc ResultSet**:

- Phân biệt **tên bảng**, **bí danh bảng**, **tên cột gốc** và **nhãn cột trong kết quả**.
- Giải thích vì sao `SELECT *` và `JOIN` dễ tạo cột trùng nhãn.
- Ánh xạ an toàn kết quả nhiều bảng sang Java DTO/record bằng bí danh rõ ràng.
- Sử dụng `ResultSetMetaData` để kiểm tra danh sách nhãn cột khi cần.
- Hiểu những giới hạn của alias: tránh nhầm cột nhưng không tự xử lý quan hệ một-nhiều, `NULL` hay cấu trúc đối tượng.

## 2. Ví dụ: `customers` và `orders` đều có `id`

Giả sử cơ sở dữ liệu có hai bảng:

~~~sql
CREATE TABLE customers (
    id         BIGINT PRIMARY KEY,
    full_name  VARCHAR(150) NOT NULL,
    status     VARCHAR(20) NOT NULL
);

CREATE TABLE orders (
    id          BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total       DECIMAL(15, 2) NOT NULL,
    status      VARCHAR(20) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

Ví dụ dữ liệu:

**Bảng `customers`**

| id | full_name | status |
|---:|---|---|
| 101 | Nguyễn An | ACTIVE |
| 102 | Trần Bình | ACTIVE |

**Bảng `orders`**

| id | customer_id | total | status |
|---:|---:|---:|---|
| 501 | 101 | 250000.00 | PAID |
| 502 | 101 | 130000.00 | PENDING |
| 503 | 102 | 400000.00 | PAID |

Khóa ngoại `orders.customer_id` tham chiếu `customers.id`. Trường `customers.id` là ID khách hàng, còn `orders.id` là ID đơn hàng. Hai cột này **cùng tên `id` nhưng có ý nghĩa hoàn toàn khác nhau**.

Nếu chạy:

~~~sql
SELECT c.id, c.full_name, c.status,
       o.id, o.total, o.status
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id
ORDER BY c.id, o.id;
~~~

Danh sách cột trả về có thể được nhìn như sau:

| Vị trí cột trong `ResultSet` | Cột nguồn | Nhãn cột mặc định |
|---:|---|---|
| 1 | `c.id` | `id` |
| 2 | `c.full_name` | `full_name` |
| 3 | `c.status` | `status` |
| 4 | `o.id` | `id` |
| 5 | `o.total` | `total` |
| 6 | `o.status` | `status` |

Điều kiện `ON o.customer_id = c.id` xác định **cách nối hàng**, nhưng không đổi tên các cột trong kết quả. Phần tiền tố `c.` và `o.` giúp SQL xác định cột nguồn; nó **không tự trở thành một phần của nhãn cột** để truyền cho getter JDBC.

### Rủi ro của nhãn trùng nhau

~~~java
long customerId = rs.getLong("id");
long orderId    = rs.getLong("id"); // Cũng chọn cột "id" khớp đầu tiên!
String status   = rs.getString("status"); // Không rõ ý định là status nào.
~~~

Trong ví dụ trên, `customerId` và `orderId` có thể cùng đọc giá trị **101** ở hàng đầu, mặc dù ID đơn hàng thực tế là **501**. Đây là loại lỗi nguy hiểm vì chương trình có thể chạy bình thường, nhưng dữ liệu sai về mặt nghiệp vụ.

## 3. Bí danh bảng và bí danh cột có nhiệm vụ khác nhau

Hai loại alias thường xuất hiện cùng nhau:

~~~sql
SELECT
    c.id   AS customer_id,
    o.id   AS order_id
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id;
~~~

- **`customers AS c`** và **`orders AS o`** đặt bí danh **bảng**. Trong câu SQL, ta dùng `c.id` và `o.id` để chỉ đúng cột nguồn.
- **`c.id AS customer_id`** đặt bí danh **cột kết quả**. Khi đọc `ResultSet`, ta dùng `getLong("customer_id")` để truy cập cột được trình bày dưới nhãn đó.

~~~mermaid
flowchart LR
    subgraph T["Bảng nguồn trong SQL"]
      C["customers AS c<br/>c.id"]
      O["orders AS o<br/>o.id"]
    end
    C -->|"AS customer_id"| R["ResultSet:<br/>customer_id, order_id"]
    O -->|"AS order_id"| R
    R --> J["Java mapping:<br/>getLong(\"customer_id\")<br/>getLong(\"order_id\")"]
~~~

Nên phân biệt:

| Cú pháp | Thuộc tầng nào? | Được dùng ở đâu? |
|---|---|---|
| `c` trong `customers AS c` | Bí danh bảng của SQL | `SELECT c.id`, `JOIN`, `WHERE`, `ORDER BY` |
| `c.id` | Tham chiếu cột nguồn đã định danh bảng | Các biểu thức SQL |
| `customer_id` trong `c.id AS customer_id` | Nhãn cột kết quả | SQL theo quy tắc của DB; `ResultSet.getLong("customer_id")` |
| `customerId` trong Java DTO | Tên thuộc tính Java | Hàm tạo/getter/record component, không tự gắn với SQL |

Đặt alias **không đổi schema**: sau khi chạy `SELECT c.id AS customer_id`, tên cột lưu trong bảng vẫn là `id`. Bí danh chỉ thuộc ngữ cảnh câu truy vấn/kết quả.

## 4. Viết lại câu truy vấn với các nhãn duy nhất

Phiên bản rõ nghĩa hơn:

~~~sql
SELECT c.id        AS customer_id,
       c.full_name AS customer_name,
       c.status    AS customer_status,
       o.id        AS order_id,
       o.total     AS order_total,
       o.status    AS order_status
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id
ORDER BY c.id, o.id;
~~~

Các nhãn đầu ra:

| Nhãn cột trong kết quả | Giá trị minh họa ở hàng đầu | Getter JDBC tương ứng |
|---|---|---|
| `customer_id` | 101 | `getLong("customer_id")` |
| `customer_name` | Nguyễn An | `getString("customer_name")` |
| `customer_status` | ACTIVE | `getString("customer_status")` |
| `order_id` | 501 | `getLong("order_id")` |
| `order_total` | 250000.00 | `getBigDecimal("order_total")` |
| `order_status` | PAID | `getString("order_status")` |

Việc chọn bí danh theo **vai trò nghiệp vụ** giúp người đọc Java không phải nhớ rằng cột thứ nhất là ID khách hàng và cột thứ tư là ID đơn hàng.

Một quy ước dễ dùng là `<vai_tro>_<ten_thuoc_tinh>`: `customer_id`, `order_id`, `customer_status`, `order_status`. Với bảng nối nhiều lần đến cùng một bảng, chọn tên theo vai trò như `buyer_id` và `seller_id` thay vì chỉ tên vật lý của bảng.

Không bắt buộc alias **mọi** cột trong mọi truy vấn. Nhưng khi truy vấn có nhiều bảng, biểu thức tính toán hoặc khả năng trùng nhãn, việc đặt alias **cho tất cả cột được ánh xạ** tạo một hợp đồng kết quả ổn định và dễ kiểm tra.

## 5. Ví dụ JDBC đầy đủ: ánh xạ hai bảng sang DTO

Giả sử ứng dụng cần liệt kê đơn hàng cùng thông tin khách hàng. Dùng `record` Java 17+ để biểu diễn **một hàng kết quả đã nối**:

~~~java
import java.math.BigDecimal;

public record OrderWithCustomer(
        long orderId,
        BigDecimal orderTotal,
        String orderStatus,
        long customerId,
        String customerName,
        String customerStatus
) {}
~~~

Repository thực thi SQL và ánh xạ theo **nhãn cột**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<OrderWithCustomer> findByCustomer(long customerId)
            throws SQLException {
        String sql = """
                SELECT o.id        AS order_id,
                       o.total     AS order_total,
                       o.status    AS order_status,
                       c.id        AS customer_id,
                       c.full_name AS customer_name,
                       c.status    AS customer_status
                FROM orders AS o
                JOIN customers AS c ON c.id = o.customer_id
                WHERE c.id = ?
                ORDER BY o.id
                """;

        List<OrderWithCustomer> rows = new ArrayList<>();
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);
            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    rows.add(new OrderWithCustomer(
                            rs.getLong("order_id"),
                            rs.getBigDecimal("order_total"),
                            rs.getString("order_status"),
                            rs.getLong("customer_id"),
                            rs.getString("customer_name"),
                            rs.getString("customer_status")
                    ));
                }
            }
        }
        return rows;
    }
}
~~~

Giả định bảng và dữ liệu theo phần 2, `DataSource` đã cấu hình đúng JDBC driver. Với `customerId = 101`, danh sách có thể chứa hai `OrderWithCustomer`: một cho đơn 501, một cho đơn 502. Dữ liệu khách hàng được lặp trong hai **hàng kết quả JOIN** vì khách hàng có hai đơn hàng.

### Vì sao cách ánh xạ này an toàn hơn?

1. Câu SQL dùng bí danh bảng `o` và `c` để xác định rõ nguồn của từng cột.
2. Mỗi cột chọn ra được gán một **nhãn duy nhất** như `order_id` và `customer_id`.
3. Các getter `rs.getLong("order_id")` hoặc `rs.getString("customer_status")` thể hiện ý nghĩa trực tiếp.
4. Giá trị đầu vào `customerId` được bind qua `PreparedStatement`, tránh ghép chuỗi.
5. `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` đúng vòng đời; DTO vẫn sử dụng được sau khi đóng kết nối.

**Lưu ý về kiểu:** ví dụ khai báo `id` là `BIGINT PRIMARY KEY` nên dùng `long`. `total` là `DECIMAL` nên đọc bằng `BigDecimal` để tránh sai số của `double` khi biểu diễn tiền. Nếu schema cho phép `NULL`, phải ánh xạ sang kiểu Java nullable thích hợp.

## 6. Đọc theo chỉ số có tránh được tên trùng không?

JDBC cũng cho phép đọc qua **vị trí cột**, bắt đầu từ **1**:

~~~java
long customerId = rs.getLong(1); // Cột SELECT thứ nhất.
long orderId    = rs.getLong(4); // Cột SELECT thứ tư trong truy vấn ban đầu.
~~~

Đây là cách hợp lệ đối với một `ResultSet` có thứ tự cột được xác định rõ. Tuy nhiên, nếu lập trình viên thêm một cột ở đầu danh sách `SELECT` hoặc thay đổi thứ tự, mã đọc bằng vị trí có thể âm thầm lấy nhầm trường.

So sánh:

| Cách đọc | Điểm mạnh | Rủi ro |
|---|---|---|
| `rs.getLong(4)` | Không cần tên, đôi khi gọn với một số truy vấn chuyên biệt | Phụ thuộc thứ tự cột trong `SELECT` |
| `rs.getLong("order_id")` | Biểu đạt vai trò của giá trị, dễ kiểm tra khi đổi thứ tự cột | Phụ thuộc hợp đồng alias; phải bảo đảm nhãn duy nhất |
| `rs.getLong("id")` khi JOIN hai bảng đều có `id` | Dễ viết | Cột khớp đầu tiên có thể không phải cột mong muốn |
| `rs.getLong("o.id")` | Trông giống tham chiếu SQL | Không hoạt động theo mặc định chỉ vì SQL đã dùng `o.id`; nhãn không tự chứa tiền tố bảng |

Với truy vấn nhiều bảng cần bảo trì lâu dài, đọc theo alias rõ nghĩa thường là lựa chọn tốt. Nếu chọn đọc theo chỉ số để tối ưu một luồng rất đặc thù, hãy giữ danh sách cột ổn định và kiểm tra chặt thứ tự đó.

## 7. Cơ chế `column label` và `column name` trong JDBC

Hai khái niệm dễ nhầm:

- **Tên cột nguồn (column name)** là tên của cột được database định nghĩa, ví dụ `id`.
- **Nhãn cột (column label)** là tên hiển thị cho cột kết quả, thường do `AS` đặt; nếu không chỉ định alias thì mặc định là tên cột theo metadata của JDBC.

Ví dụ:

~~~sql
SELECT c.id AS customer_id,
       o.id AS order_id
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id;
~~~

Các API liên quan:

~~~java
ResultSetMetaData meta = rs.getMetaData();
String label1 = meta.getColumnLabel(1); // "customer_id".
String label2 = meta.getColumnLabel(2); // "order_id".

long customerId = rs.getLong("customer_id");
long orderId = rs.getLong("order_id");
~~~

`ResultSet.getXXX(String)` dùng **nhãn cột** theo hợp đồng API; `ResultSetMetaData.getColumnLabel(int)` trả lại nhãn được đề xuất, thông thường là alias SQL. `ResultSetMetaData.getColumnName(int)` cung cấp tên cột theo metadata và **không nên dùng thay cho `getColumnLabel`** khi mã cần dựa vào alias.

Với các biểu thức SQL như `COUNT(*)`, `SUM(total)`, `CASE ... END` hoặc phép nối chuỗi, tên cột nguồn có thể không tồn tại theo nghĩa một cột vật lý. Alias khi đó càng quan trọng:

~~~sql
SELECT o.customer_id AS customer_id,
       COUNT(*) AS order_count,
       SUM(o.total) AS total_spent
FROM orders AS o
GROUP BY o.customer_id;
~~~

~~~java
long customerId = rs.getLong("customer_id");
long orderCount = rs.getLong("order_count");
java.math.BigDecimal totalSpent = rs.getBigDecimal("total_spent");
~~~

Nếu không có `AS order_count`, một driver có thể cung cấp nhãn kiểu `count` hoặc `count(*)` tùy hệ quản trị/driver. Mã Java dựa vào tên sinh tự động như thế dễ bị ảnh hưởng khi chuyển database.

## 8. `SELECT *` làm tăng nguy cơ trùng nhãn và sai hợp đồng

Ví dụ:

~~~sql
SELECT *
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id;
~~~

Kết quả bao gồm toàn bộ cột của cả hai bảng, trong đó `id` và `status` có thể xuất hiện hai lần. Ngay cả `SELECT c.*, o.*` cũng không giải quyết được vấn đề nhãn trùng, vì danh sách cột được mở rộng mà **không được tự đặt alias riêng theo bảng**.

Các rủi ro của `SELECT *`:

1. Thêm cột vào schema có thể làm thay đổi **thứ tự và số lượng cột kết quả**.
2. Nhiều cột có cùng tên gây ra lookup mơ hồ.
3. Truy vấn có thể tải thêm dữ liệu lớn hoặc nhạy cảm mà chức năng không cần.
4. Mã ánh xạ sang DTO phụ thuộc vào cấu trúc truy vấn không được thể hiện tường minh.

Thay bằng danh sách cột:

~~~sql
SELECT c.id        AS customer_id,
       c.full_name AS customer_name,
       o.id        AS order_id,
       o.total     AS order_total
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id;
~~~

**Nguyên tắc:** liệt kê cột theo nhu cầu của use case và đặt nhãn rõ nghĩa cho từng giá trị trả về. Alias chỉ giải quyết phần **định danh cột trong kết quả**; việc giảm dữ liệu truy vấn còn đến từ chọn đúng cột, điều kiện `WHERE`, phân trang và giới hạn số hàng khi phù hợp.

## 9. JOIN nhiều lần cùng một bảng: alias theo vai trò

Giả sử bảng `transfers` có hai khóa ngoại `sender_id` và `receiver_id` cùng tham chiếu bảng `accounts`. Nếu dùng hai JOIN đến `accounts`, cần hai bí danh bảng và hai nhóm nhãn cột:

~~~sql
SELECT t.id          AS transfer_id,
       sender.id     AS sender_id,
       sender.name   AS sender_name,
       receiver.id   AS receiver_id,
       receiver.name AS receiver_name,
       t.amount      AS transfer_amount
FROM transfers AS t
JOIN accounts AS sender ON sender.id = t.sender_id
JOIN accounts AS receiver ON receiver.id = t.receiver_id
WHERE t.id = ?;
~~~

Mặc dù cả `sender.name` và `receiver.name` đều lấy từ **cùng một tên cột vật lý `accounts.name`**, kết quả có hai nhãn khác nhau là `sender_name` và `receiver_name`.

Mã đọc:

~~~java
String senderName = rs.getString("sender_name");
String receiverName = rs.getString("receiver_name");
~~~

Tên `sender`/`receiver` xuất phát từ **vai trò nghiệp vụ**, dễ hiểu hơn những tên chung chung như `a1_name` và `a2_name`.

### JOIN một-nhiều tạo nhiều hàng, alias không tự nhóm lại

Với khách hàng 101 có hai đơn hàng, kết quả JOIN có hai hàng chứa `customer_id = 101`, dù chỉ có **một khách hàng** trong bảng `customers`.

Nếu muốn đối tượng Java dạng:

~~~text
Customer
  id = 101
  name = "Nguyễn An"
  orders = [
    Order(id = 501, ...),
    Order(id = 502, ...)
  ]
~~~

thì mã phải **gom nhóm theo `customer_id`**, tạo một đối tượng khách hàng cho mỗi ID, rồi thêm các đơn hàng theo `order_id`. Alias giúp biết rõ cột nào được dùng làm khóa nhóm; nó **không tự biến nhiều hàng JOIN thành một object graph** trong JDBC thuần.

## 10. `LEFT JOIN`, `NULL` và getter kiểu nguyên thủy

Với `LEFT JOIN`, vẫn có thể trả một khách hàng chưa có đơn hàng:

~~~sql
SELECT c.id        AS customer_id,
       c.full_name AS customer_name,
       o.id        AS order_id,
       o.total     AS order_total
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
WHERE c.id = ?;
~~~

Khi khách hàng tồn tại nhưng không có bản ghi tương ứng trong `orders`, các cột phía `o` nhận SQL `NULL`. Nếu dùng:

~~~java
long orderId = rs.getLong("order_id");
~~~

thì giá trị SQL `NULL` được ánh xạ qua getter primitive thành **0**. Muốn phân biệt **không có đơn hàng** với **đơn hàng có ID 0**, phải gọi `wasNull()` ngay sau getter:

~~~java
long rawOrderId = rs.getLong("order_id");
Long orderId = rs.wasNull() ? null : rawOrderId;
java.math.BigDecimal orderTotal = rs.getBigDecimal("order_total");
~~~

`getBigDecimal` trả `null` khi giá trị SQL là `NULL`, nhưng `getLong` cần kiểm tra `wasNull` khi cột có thể thiếu. Đặt alias đúng là điều kiện cần để đọc **đúng cột**, còn xử lý `NULL` là điều kiện riêng để hiểu **đúng giá trị**.

Khi lọc trong `LEFT JOIN`, để ý vị trí điều kiện:

~~~sql
-- Giữ khách hàng không có đơn được thanh toán:
LEFT JOIN orders AS o
  ON o.customer_id = c.id AND o.status = 'PAID'
~~~

Nếu chuyển `o.status = 'PAID'` xuống `WHERE` thì hàng không có đơn với `o.status IS NULL` thường bị loại và ngữ nghĩa có thể gần với `INNER JOIN`. Đây là vấn đề **ngữ nghĩa JOIN**, alias không tự sửa được.

## 11. Kiểm tra nhãn cột bằng `ResultSetMetaData`

Nếu ứng dụng đọc truy vấn do nhiều nhóm viết hoặc cần QA hợp đồng dữ liệu đầu ra, có thể kiểm tra nhãn của các cột trong `ResultSet`:

~~~java
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

public final class ColumnLabelValidator {
    public static void requireUniqueLabels(ResultSet rs)
            throws SQLException {
        ResultSetMetaData meta = rs.getMetaData();
        Set<String> seen = new HashSet<>();

        for (int column = 1; column <= meta.getColumnCount(); column++) {
            String label = meta.getColumnLabel(column);
            if (label == null || label.isBlank()) {
                throw new SQLException("Nhãn cột rỗng ở vị trí " + column);
            }
            String normalized = label.toLowerCase(Locale.ROOT);
            if (!seen.add(normalized)) {
                throw new SQLException("Nhãn cột bị trùng: " + label);
            }
        }
    }
}
~~~

Ví dụ này minh họa kiểm tra các nhãn trùng nhau **không phân biệt hoa/thường**, phù hợp với cách getter JDBC tra cứu column label không phân biệt hoa/thường. Với các hệ quản trị có quy tắc identifier/Unicode đặc biệt, cần xem lại quy ước alias và đặc tính driver. Việc kiểm tra nên dùng như bước xác minh hợp đồng, không nhất thiết phải lặp lại trên mọi lần đọc hàng trong môi trường production.

Để chẩn đoán cấu trúc truy vấn, có thể in **metadata nhãn cột** trong môi trường phát triển:

~~~java
ResultSetMetaData meta = rs.getMetaData();
for (int i = 1; i <= meta.getColumnCount(); i++) {
    System.out.printf("%d: label=%s, type=%s%n",
            i,
            meta.getColumnLabel(i),
            meta.getColumnTypeName(i));
}
~~~

Không đưa dữ liệu nhạy cảm từ giá trị cột vào log. Metadata giúp phát hiện `id` xuất hiện hai lần, nhưng định nghĩa alias ngay trong SQL vẫn là cách rõ ràng nhất.

## 12. Một số lỗi thường gặp khi dùng alias

### 12.1. Chỉ đặt bí danh bảng, bỏ qua bí danh cột

~~~sql
-- Vẫn tạo ra hai cột cùng nhãn "id".
SELECT c.id, o.id
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id;
~~~

**Sửa:** `SELECT c.id AS customer_id, o.id AS order_id ...`.

### 12.2. Gọi getter bằng `c.id` thay vì nhãn đầu ra

~~~java
// Không có lý do để nhãn tự động là "c.id".
long customerId = rs.getLong("c.id");
~~~

**Sửa:** nếu SQL có `c.id AS customer_id`, hãy đọc bằng `rs.getLong("customer_id")`. Một số driver có thể nhận thêm các dạng tên trong trường hợp riêng, nhưng mã portable phải dựa trên nhãn cột đã khai báo.

### 12.3. Alias bị trùng do copy/paste

~~~sql
SELECT c.id AS entity_id,
       o.id AS entity_id
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id;
~~~

Vẫn trùng nhãn `entity_id`. Việc có từ khóa `AS` **chưa đủ**; phải bảo đảm tên alias **duy nhất** trong tập kết quả hoặc ít nhất giữa các cột mà ứng dụng muốn phân biệt.

### 12.4. Getter dùng tên cột gốc sau khi đã đổi alias

~~~sql
SELECT o.id AS order_id FROM orders AS o;
~~~

~~~java
long id = rs.getLong("id"); // Không khớp hợp đồng nhãn "order_id".
~~~

**Sửa:** dùng `rs.getLong("order_id")`. Mã mapping và câu SQL cần được thay đổi cùng nhau khi đổi alias.

### 12.5. Dùng `SELECT *` để tiết kiệm thời gian

`SELECT *` làm hợp đồng cột kết quả phụ thuộc vào schema và danh sách bảng tham gia. Hãy liệt kê các cột cần thiết, đặc biệt ở các truy vấn JOIN dùng trong repository.

### 12.6. Lạm dụng tên alias dài hoặc có ký tự đặc biệt

Ví dụ `AS "Tên đầy đủ của khách hàng"` có thể hợp lệ ở một số database, nhưng buộc ứng dụng phải xử lý khoảng trắng, ký tự có dấu và quy tắc quote identifier. Cú pháp dấu quote và cách gấp chữ hoa/thường khác nhau giữa database.

Với API JDBC phục vụ Java, alias ngắn gọn dạng `customer_name`, `order_total`, `last_updated_at` thường dễ chuyển hệ quản trị và dễ bảo trì hơn. Khi cần đặt alias động theo dữ liệu người dùng, không chèn trực tiếp input vào SQL: placeholder `?` chỉ bind **giá trị**, không bind tên cột hoặc alias. Hãy dùng danh sách tên hợp lệ được kiểm soát nếu phải chọn identifier động.

### 12.7. Dùng nhãn cột để suy ra định danh hàng

Alias `customer_id` chỉ đặt **tên** cho một giá trị trong kết quả. Nó không biến kết quả của phép JOIN thành một hàng khách hàng duy nhất, cũng không xác minh ràng buộc khóa chính. Để nhóm dữ liệu, cần dựa vào các khóa và quy tắc nghiệp vụ thực tế.

## 13. Quy ước alias khi thiết kế repository

Một quy trình ngắn giúp giảm sai sót:

1. **Xác định dữ liệu đầu ra**: API muốn DTO gồm những trường nào, từ những bảng nào?
2. **Đặt bí danh bảng** theo vai trò SQL: `c`, `o`, `sender`, `receiver`; dùng tiền tố bảng khi tham chiếu cột trong `SELECT`, `JOIN`, `WHERE` và `ORDER BY`.
3. **Liệt kê cột tường minh**, tránh `SELECT *` với JOIN. Chọn đúng cột cần dùng.
4. **Đặt alias duy nhất** cho các cột đầu ra: `customer_id`, `order_id`, `customer_status`, `order_status`.
5. **Ánh xạ theo nhãn**: dùng `getLong("order_id")` thay vì dựa vào thứ tự cột hoặc tên gốc mơ hồ.
6. **Kiểm tra `NULL`** cho các cột tùy chọn, đặc biệt bên phải `LEFT JOIN`.
7. **Kiểm tra số hàng và quan hệ**: JOIN một-nhiều có thể lặp dữ liệu gốc; nhóm đối tượng khi cần.
8. **Xác nhận metadata/hợp đồng** khi query phức tạp hoặc kết quả thay đổi: `getColumnLabel` giúp phát hiện nhãn trùng.

### Bảng chọn tên alias

| Tình huống | Nhãn dễ gây nhầm lẫn | Nhãn nên dùng |
|---|---|---|
| Khách hàng và đơn hàng đều có `id` | `id`, `id` | `customer_id`, `order_id` |
| Hai bảng đều có `status` | `status`, `status` | `customer_status`, `order_status` |
| Hai lần JOIN đến `accounts` | `name`, `name` | `sender_name`, `receiver_name` |
| Truy vấn có `COUNT(*)` | Nhãn do driver/database sinh | `order_count` |
| Truy vấn có `SUM(o.total)` | `sum` hoặc nhãn biểu thức | `total_spent` |
| `CASE WHEN ... END` | Nhãn biểu thức dài/khó đoán | `payment_state` |

**Phân biệt thêm:** trong `WHERE` hoặc `JOIN ON`, tiếp tục dùng tham chiếu cột nguồn như `o.status` để tránh mơ hồ. Mức độ cho phép dùng **alias SELECT** trong `ORDER BY`, `GROUP BY`, `HAVING` hay `WHERE` khác nhau giữa hệ quản trị; đừng dựa vào một quy tắc xuyên mọi database. Đối với mã portable, hãy viết biểu thức theo cú pháp được database đang dùng hỗ trợ.

## 14. Câu hỏi tự kiểm tra

1. Truy vấn `SELECT c.id, o.id` tạo ra hai cột có nhãn mặc định gì? `rs.getLong("id")` chọn cột nào theo hợp đồng JDBC?
2. `customers AS c` giúp giải quyết vấn đề gì trong SQL? Vì sao nó không tự giải quyết cột `id` trùng nhau trong `ResultSet`?
3. Nếu SQL có `o.id AS order_id`, mã Java nên dùng `getLong("order_id")` hay `getLong("o.id")`?
4. Vì sao `rs.getLong(4)` có thể đúng hôm nay nhưng sai sau khi thêm một cột ở đầu danh sách `SELECT`?
5. Với `LEFT JOIN orders`, tại sao phải gọi `wasNull()` ngay sau `getLong("order_id")` nếu không có đơn hàng?
6. Alias có khiến JDBC tự tạo `Customer` chứa `List<Order>` từ các hàng JOIN một-nhiều không?
7. `ResultSetMetaData.getColumnLabel(i)` khác gì về mục đích so với `getColumnName(i)`?
8. Câu `SELECT c.id AS entity_id, o.id AS entity_id` đã xử lý được lỗi trùng tên chưa? Vì sao?

**Ghi nhớ:** JOIN có thể làm **nhiều cột nguồn trùng tên** xuất hiện trong một `ResultSet`. Hãy dùng bí danh **bảng** để xác định cột trong SQL và bí danh **cột** để đặt **nhãn đầu ra duy nhất**. Mã JDBC đọc bằng nhãn đó, ví dụ `rs.getLong("customer_id")` và `rs.getLong("order_id")`. Alias bảo vệ sự rõ ràng của mapping; tính đúng đắn hoàn chỉnh còn cần xử lý `NULL`, số hàng JOIN, vòng đời tài nguyên và kiểu dữ liệu.

### Tài liệu tham khảo chính thức

- [Java SE 21 — `java.sql.ResultSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html)
- [Java SE 21 — `java.sql.ResultSetMetaData`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSetMetaData.html)
- [Java SE 21 — `java.sql.PreparedStatement`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html)
- [PostgreSQL — SELECT và column alias](https://www.postgresql.org/docs/current/sql-select.html)
- [MySQL 8.4 — Column aliases](https://dev.mysql.com/doc/refman/8.4/en/problems-with-alias.html)
