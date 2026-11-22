# Lấy khóa tự sinh bằng LAST_INSERT_ID hoặc cơ chế generated keys

Khi thêm một bản ghi vào bảng có cột `AUTO_INCREMENT`, MySQL cấp một giá trị khóa mới. Ứng dụng thường cần lấy khóa đó ngay sau `INSERT` để tạo các bản ghi liên quan, chẳng hạn lấy `order_id` vừa tạo rồi ghi các dòng hàng vào bảng `order_items`.

Trong MySQL, có hai cách phổ biến để nhận khóa tự sinh:

- Dùng hàm SQL `LAST_INSERT_ID()` trên chính kết nối đã thực hiện câu lệnh `INSERT`.
- Dùng API generated keys của thư viện kết nối cơ sở dữ liệu, ví dụ `Statement.RETURN_GENERATED_KEYS` và `getGeneratedKeys()` trong JDBC.

Hai cách đều dựa trên kết quả của lần ghi dữ liệu vừa thực hiện. Chọn cách phù hợp với nơi bạn đang viết mã: `LAST_INSERT_ID()` thuận tiện trong SQL thuần, còn generated keys giúp mã ứng dụng nhận khóa trực tiếp từ câu lệnh đã chạy.

## 1. Chuẩn bị bảng có khóa `AUTO_INCREMENT`

Ví dụ tạo bảng đơn hàng:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
```

`order_id` là khóa chính và được MySQL tự cấp giá trị khi câu lệnh `INSERT` không truyền cột này:

```sql
INSERT INTO orders (customer_id, total_amount)
VALUES (42, 125000.00);
```

Sau khi câu lệnh thành công, ứng dụng có thể lấy `order_id` vừa được cấp. Không cần truy vấn lại bảng để tìm bản ghi mới.

## 2. Lấy khóa bằng `LAST_INSERT_ID()`

`LAST_INSERT_ID()` không có tham số trả về giá trị `AUTO_INCREMENT` đầu tiên được tạo bởi câu lệnh `INSERT` gần nhất trên **kết nối MySQL hiện tại**:

```sql
INSERT INTO orders (customer_id, total_amount)
VALUES (42, 125000.00);

SELECT LAST_INSERT_ID() AS order_id;
```

Kết quả `order_id` là khóa của đơn hàng vừa thêm. Hai câu lệnh phải chạy trên cùng một kết nối (cùng session). Nếu chạy câu `SELECT` trên một kết nối khác, MySQL sẽ đọc trạng thái `LAST_INSERT_ID()` của kết nối khác đó.

### Vì sao cách này an toàn khi có nhiều người ghi dữ liệu?

MySQL lưu giá trị `LAST_INSERT_ID()` riêng cho từng kết nối. Giả sử hai ứng dụng cùng thêm đơn hàng:

| Kết nối | Câu lệnh `INSERT` | Giá trị đọc được từ `LAST_INSERT_ID()` |
|---|---|---:|
| A | Thêm đơn hàng thứ nhất | Khóa được cấp cho A |
| B | Thêm đơn hàng thứ hai | Khóa được cấp cho B |

Việc B thêm bản ghi không làm thay đổi giá trị mà A đọc được trên kết nối A. Vì vậy, cách này tránh được lỗi lấy nhầm khóa do một kết nối khác vừa ghi dữ liệu.

Tuy nhiên, một câu lệnh `INSERT` tiếp theo trên **cùng kết nối** có thể thay đổi giá trị được lưu. Hãy lấy khóa ngay sau câu lệnh cần lấy khóa, trước khi chạy một lệnh ghi khác có thể sinh `AUTO_INCREMENT`.

### Dùng khóa vừa lấy trong transaction

Một transaction thường cần tạo bản ghi cha trước, rồi dùng khóa của bản ghi cha để tạo các bản ghi con:

```sql
START TRANSACTION;

INSERT INTO orders (customer_id, total_amount)
VALUES (42, 125000.00);

SET @new_order_id = LAST_INSERT_ID();

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (@new_order_id, 9001, 2);

COMMIT;
```

`@new_order_id` là biến người dùng có phạm vi theo session. Việc lưu khóa vào biến ngay sau `INSERT` giúp câu lệnh thêm dòng hàng vẫn dùng đúng `order_id`, kể cả khi bảng `order_items` cũng có cột `AUTO_INCREMENT`.

Trong ứng dụng, bạn cũng có thể đọc khóa bằng API của driver rồi truyền khóa đó làm tham số cho câu lệnh tiếp theo. Hãy giữ các thao tác trong cùng transaction và cùng kết nối khi chúng cần thành công hoặc thất bại cùng nhau.

## 3. Lấy khóa bằng generated keys trong JDBC

Khi viết ứng dụng Java, JDBC cho phép yêu cầu driver trả về các khóa được tạo bởi câu lệnh. Với MySQL Connector/J, có thể dùng `Statement.RETURN_GENERATED_KEYS` khi tạo `PreparedStatement`, sau đó đọc kết quả bằng `getGeneratedKeys()`:

```java
String sql = "INSERT INTO orders (customer_id, total_amount) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {

    statement.setLong(1, 42L);
    statement.setBigDecimal(2, new BigDecimal("125000.00"));

    int affectedRows = statement.executeUpdate();
    if (affectedRows != 1) {
        throw new SQLException("Không thêm được đơn hàng");
    }

    try (ResultSet generatedKeys = statement.getGeneratedKeys()) {
        if (!generatedKeys.next()) {
            throw new SQLException("MySQL không trả về khóa tự sinh");
        }

        long orderId = generatedKeys.getLong(1);
        // Dùng orderId để thêm các dòng hàng hoặc trả kết quả cho tầng gọi.
    }
}
```

Các điểm cần chú ý:

1. Truyền `Statement.RETURN_GENERATED_KEYS` khi tạo statement để yêu cầu driver trả về khóa.
2. Gọi `executeUpdate()` để thực hiện `INSERT`.
3. Đọc `ResultSet` do `getGeneratedKeys()` trả về và kiểm tra `next()` trước khi lấy giá trị.
4. Đọc khóa từ đúng statement vừa thực hiện thao tác ghi.

Generated keys là cơ chế của JDBC và driver. Ứng dụng không cần tự ghép thêm câu `SELECT LAST_INSERT_ID()` để lấy khóa cho trường hợp này. Nếu cần tạo bản ghi con trong cùng transaction, hãy dùng `orderId` vừa đọc trên cùng `Connection` trước khi commit.

Với câu lệnh thêm nhiều bản ghi hoặc batch insert, số lượng và cách sắp xếp khóa được trả về có thể phụ thuộc driver và phiên bản. Hãy kiểm tra tài liệu của driver đang dùng và xác minh hành vi bằng trường hợp thực tế; không mặc định rằng mọi batch đều trả về đầy đủ khóa theo thứ tự mong muốn.

## 4. Kết hợp `LAST_INSERT_ID(expr)` với `ON DUPLICATE KEY UPDATE`

`LAST_INSERT_ID()` còn có dạng nhận một biểu thức: `LAST_INSERT_ID(expr)`. Dạng này trả về `expr` và đặt giá trị `LAST_INSERT_ID` của kết nối hiện tại thành giá trị đó.

Một ứng dụng có thể cần thao tác upsert: thêm khách hàng nếu chưa tồn tại, hoặc cập nhật khách hàng nếu email đã có. Nếu muốn lấy `customer_id` trong cả hai trường hợp, có thể dùng mẫu sau trên MySQL 8.0.19 trở lên:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB;

INSERT INTO customers (email, display_name)
VALUES ('linh@example.com', 'Linh') AS incoming
ON DUPLICATE KEY UPDATE
    customer_id = LAST_INSERT_ID(customer_id),
    display_name = incoming.display_name;

SELECT LAST_INSERT_ID() AS customer_id;
```

Kết quả hoạt động như sau:

- Nếu email chưa tồn tại, MySQL thêm hàng mới và `LAST_INSERT_ID()` trả về `customer_id` vừa được cấp.
- Nếu email đã tồn tại, nhánh `ON DUPLICATE KEY UPDATE` chạy. Biểu thức `LAST_INSERT_ID(customer_id)` đặt giá trị cần trả về thành khóa của hàng đang được cập nhật.

Nhờ vậy, câu `SELECT` cuối có thể lấy khóa của hàng liên quan trong cả hai nhánh. Mẫu này hữu ích khi cần thao tác upsert và tiếp tục xử lý bản ghi theo khóa. Hãy dùng đúng cột khóa của hàng bị trùng trong biểu thức `LAST_INSERT_ID(customer_id)`.

## 5. Những lỗi thường gặp

### Chạy câu lấy khóa trên một kết nối khác

`LAST_INSERT_ID()` có phạm vi theo kết nối. Với connection pool, hãy lấy khóa trước khi trả connection về pool và không chuyển câu `SELECT` sang một connection khác. Khi dùng JDBC generated keys, đọc `ResultSet` từ chính `PreparedStatement` đã thực hiện `INSERT`.

### Dùng `MAX(id)` để đoán khóa vừa tạo

Không nên làm như sau:

```sql
INSERT INTO orders (customer_id, total_amount)
VALUES (42, 125000.00);

SELECT MAX(order_id) FROM orders;
```

Giữa hai câu lệnh, một kết nối khác có thể thêm đơn hàng mới. Khi đó `MAX(order_id)` có thể là khóa của bản ghi do kết nối khác tạo ra. `LAST_INSERT_ID()` hoặc generated keys gắn kết quả với thao tác ghi của chính kết nối/statement hiện tại.

### Giả định khóa luôn liên tiếp

Giá trị `AUTO_INCREMENT` có thể có khoảng trống do transaction rollback, câu lệnh thất bại, bản ghi bị bỏ qua hoặc cách InnoDB cấp phát khóa khi có nhiều thao tác đồng thời. Khóa tự sinh dùng để định danh bản ghi, không phải bộ đếm số lượng bản ghi và không bảo đảm dãy số liên tục.

### Tự tính khóa của các hàng trong một lần insert nhiều dòng

Với một câu lệnh `INSERT` thêm nhiều hàng, `LAST_INSERT_ID()` trả về giá trị `AUTO_INCREMENT` đầu tiên được tạo bởi câu lệnh đó. Không nên lấy khóa đầu tiên rồi mặc định cộng `1`, `2`, ... để suy ra mọi khóa còn lại: cách cấp phát có thể chịu ảnh hưởng của cấu hình, engine, chế độ insert và thao tác đồng thời. Nếu cần từng khóa, hãy dùng generated keys có hỗ trợ rõ ràng từ driver hoặc thiết kế cách ghi và nhận khóa phù hợp đã được kiểm chứng.

### Đọc khóa sau một câu lệnh ghi thất bại

Chỉ xử lý khóa sau khi xác nhận `INSERT` thành công. Nếu câu lệnh lỗi hoặc không tạo bản ghi mới như dự kiến, đừng sử dụng một giá trị `LAST_INSERT_ID()` cũ hoặc coi kết quả generated keys là khóa hợp lệ cho thao tác hiện tại.

## 6. Chọn cách lấy khóa phù hợp

| Tình huống | Cách nên dùng | Lưu ý |
|---|---|---|
| Viết script SQL hoặc xử lý hoàn toàn trong một session MySQL | `LAST_INSERT_ID()` | Chạy ngay sau `INSERT` trên cùng kết nối |
| Ứng dụng Java dùng JDBC | `RETURN_GENERATED_KEYS` và `getGeneratedKeys()` | Kiểm tra driver trả về khóa và đọc từ statement vừa chạy |
| Upsert cần trả về khóa của hàng được thêm hoặc cập nhật | `LAST_INSERT_ID(id)` trong `ON DUPLICATE KEY UPDATE` | Dùng đúng khóa của hàng bị trùng và đọc kết quả trên cùng session |
| Batch hoặc insert nhiều hàng cần từng khóa | Generated keys theo khả năng driver | Xác minh số lượng, thứ tự và hành vi của phiên bản driver |

Không dùng `SELECT MAX(id)` để lấy khóa vừa tạo và không giả định các giá trị `AUTO_INCREMENT` luôn liên tiếp. Nếu ứng dụng cần khóa để tạo dữ liệu liên quan, hãy lấy khóa ngay sau thao tác ghi và truyền nó tường minh qua các bước tiếp theo.

## 7. Tự kiểm tra

1. Vì sao hai kết nối MySQL cùng gọi `LAST_INSERT_ID()` có thể nhận hai giá trị khác nhau mà không ghi đè kết quả của nhau?
2. Trong JDBC, cần truyền tùy chọn nào khi tạo `PreparedStatement` để nhận generated keys?
3. Vì sao `SELECT MAX(order_id)` không an toàn khi nhiều ứng dụng cùng thêm đơn hàng?
4. Khi một câu lệnh `INSERT` thêm nhiều hàng, `LAST_INSERT_ID()` trả về khóa nào?
5. Trong mẫu upsert, `LAST_INSERT_ID(customer_id)` giải quyết trường hợp nào?

