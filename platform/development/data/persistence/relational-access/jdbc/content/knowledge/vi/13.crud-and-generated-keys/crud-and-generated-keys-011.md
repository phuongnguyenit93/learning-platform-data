# Phân biệt xóa vật lý, xóa logic và ảnh hưởng đến truy vấn

## 1. Vì sao cần phân biệt hai cách xóa?

Trong CRUD (Create, Read, Update, Delete), thao tác *Delete* không nhất thiết đồng nghĩa với việc dữ liệu biến mất khỏi cơ sở dữ liệu. Với ứng dụng Java dùng **JDBC** để truy cập cơ sở dữ liệu quan hệ, có hai chiến lược phổ biến:

- **Xóa vật lý (hard delete / physical delete):** thực thi lệnh SQL `DELETE` để loại bỏ bản ghi khỏi bảng.
- **Xóa logic (soft delete / logical delete):** thực thi `UPDATE` để đánh dấu bản ghi đã bị xóa về mặt nghiệp vụ, nhưng vẫn lưu bản ghi trong bảng.

Chọn chiến lược nào ảnh hưởng trực tiếp đến kết quả `SELECT`, `JOIN`, `COUNT`, tính toàn vẹn tham chiếu, khả năng khôi phục dữ liệu, hiệu năng và cách viết mã JDBC. Người dùng có thể thấy cùng một hành động “Xóa khách hàng”, nhưng hệ thống thực hiện và đọc dữ liệu theo hai cách khác nhau.

**Sau bài này, bạn có thể:**

1. Giải thích sự khác nhau giữa xóa vật lý và xóa logic ở cấp SQL và nghiệp vụ.
2. Viết truy vấn chỉ lấy bản ghi còn hiệu lực, kể cả khi truy vấn có `JOIN`, phân trang hoặc thống kê.
3. Dùng `PreparedStatement` và `ResultSet` để thao tác hai kiểu xóa an toàn qua JDBC.
4. Nhận diện tác động đến khóa ngoại, ràng buộc duy nhất, transaction và hiệu năng.
5. Chọn chính sách xóa phù hợp với vòng đời dữ liệu.

## 2. Mô hình dữ liệu minh họa

Giả sử ứng dụng quản lý khách hàng và đơn hàng có hai bảng sau:

```sql
CREATE TABLE customers (
    id         BIGINT PRIMARY KEY,
    email      VARCHAR(255) NOT NULL,
    full_name  VARCHAR(200) NOT NULL,
    deleted_at TIMESTAMP NULL
);

CREATE TABLE orders (
    id          BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    amount      DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

Cột `deleted_at` là **dấu hiệu duy nhất** cho biết trạng thái xóa logic:

- `deleted_at IS NULL`: khách hàng còn hiệu lực (*active*).
- `deleted_at IS NOT NULL`: khách hàng đã được xóa logic; giá trị thời gian cho biết thời điểm xóa.

Ví dụ dữ liệu:

| `id` | `email` | `full_name` | `deleted_at` | Trạng thái |
|---|---|---|---|---|
| 101 | `mai@example.com` | Mai | `NULL` | Còn hiệu lực |
| 102 | `an@example.com` | An | `2026-10-12 09:30:00` | Đã xóa logic |
| 103 | `linh@example.com` | Linh | `NULL` | Còn hiệu lực |

Trong ba bản ghi đang lưu, ứng dụng thường chỉ hiển thị **hai khách hàng còn hiệu lực**. Bản ghi của An vẫn có thể được tra cứu trong chức năng quản trị hoặc phục hồi nếu chính sách cho phép.

> Có thể dùng cột `is_deleted BOOLEAN` thay cho `deleted_at`. Khi cần biết thời điểm xóa, `deleted_at` thuận tiện hơn. Tránh lưu cả hai cột làm hai nguồn trạng thái độc lập nếu chưa có cơ chế bảo đảm chúng luôn đồng bộ.

## 3. Xóa vật lý: `DELETE` loại bỏ bản ghi

```sql
DELETE FROM customers
WHERE id = ?;
```

Trong JDBC, dấu `?` được truyền giá trị bằng `PreparedStatement`, không ghép trực tiếp mã SQL với dữ liệu đầu vào. Sau khi lệnh xóa được commit:

- Bản ghi không còn xuất hiện trong các truy vấn thông thường trên `customers`.
- Không thể “khôi phục” bằng một lệnh `UPDATE` đơn giản; cần bản sao lưu, lịch sử hoặc cơ chế phục hồi khác.
- Nếu `orders.customer_id` đang tham chiếu khách hàng này, ràng buộc khóa ngoại như ví dụ sẽ **chặn lệnh xóa**. Nếu lược đồ dùng `ON DELETE CASCADE`, việc xóa khách hàng có thể kéo theo xóa đơn hàng; hành vi phụ thuộc cấu hình khóa ngoại thực tế.
- Transaction chưa commit vẫn có thể rollback. “Xóa vật lý” không có nghĩa dữ liệu được xóa khỏi mọi bản sao lưu, log hoặc vùng lưu trữ ngay tức thì; chi tiết lưu trữ tùy hệ quản trị cơ sở dữ liệu.

Trước khi xóa vật lý dữ liệu có quan hệ, cần xác định rõ chính sách: không cho xóa khi còn bản ghi phụ thuộc, xóa các bản ghi phụ thuộc trong transaction, hoặc sử dụng hành động tham chiếu được cấu hình có chủ đích.

## 4. Xóa logic: `UPDATE` giữ bản ghi nhưng đổi trạng thái

```sql
UPDATE customers
SET deleted_at = CURRENT_TIMESTAMP
WHERE id = ?
  AND deleted_at IS NULL;
```

Lệnh này chỉ đánh dấu khách hàng đang còn hiệu lực. Điều kiện `AND deleted_at IS NULL` tránh ghi đè thời điểm xóa trong lần gọi tiếp theo. Sau khi commit:

- Bản ghi vẫn nằm trong `customers`; khóa chính và khóa ngoại hiện hữu không thay đổi.
- Truy vấn `SELECT * FROM customers` **vẫn trả về** bản ghi đã xóa logic. Cần thêm điều kiện lọc trong những truy vấn dành cho người dùng.
- Ứng dụng có thể phục hồi bằng cách đưa `deleted_at` về `NULL`, nhưng phải kiểm tra quy tắc nghiệp vụ và các ràng buộc hiện tại.
- Xóa logic không tự kích hoạt hành động `ON DELETE CASCADE` của khóa ngoại, vì SQL thực tế là `UPDATE` trên cột trạng thái.
- Dữ liệu nhạy cảm vẫn được lưu: xóa logic không đồng nghĩa với xóa dữ liệu vĩnh viễn theo yêu cầu lưu giữ hoặc quyền được xóa dữ liệu.

Khôi phục cơ bản:

```sql
UPDATE customers
SET deleted_at = NULL
WHERE id = ?
  AND deleted_at IS NOT NULL;
```

Không nên cho phép khôi phục vô điều kiện: bản ghi có thể xung đột với email đã được cấp lại, phụ thuộc vào dữ liệu liên quan đã bị dọn dẹp, hoặc vi phạm chính sách phân quyền.

### Bảng so sánh

| Tiêu chí | Xóa vật lý | Xóa logic |
|---|---|---|
| SQL chủ đạo | `DELETE FROM ...` | `UPDATE ... SET deleted_at = ...` |
| Bản ghi còn trong bảng? | Không, sau khi commit | Có |
| `SELECT` không lọc trạng thái | Không thấy bản ghi đã xóa | Vẫn thấy bản ghi đã xóa |
| Khôi phục | Cần phương án lưu lịch sử hoặc bản sao | Có thể cập nhật lại trạng thái nếu hợp lệ |
| Khóa ngoại | Có thể bị chặn hoặc gây hành động tham chiếu | Khóa ngoại vẫn giữ nguyên |
| Ràng buộc duy nhất | Giá trị của hàng đã xóa không còn chiếm chỗ | Hàng đã xóa vẫn có thể chiếm giá trị duy nhất |
| Chi phí vận hành | Cần quản lý tác động khi xóa thực sự | Cần lọc trạng thái, lưu trữ và dọn dẹp định kỳ |
| Trường hợp thường gặp | Dữ liệu tạm, bản ghi được phép xóa hẳn | Tài khoản, danh mục hoặc hồ sơ cần phục hồi/lịch sử |

## 5. Ảnh hưởng đến `SELECT`, tìm kiếm và thống kê

**Quy tắc quan trọng:** nếu một bảng hỗ trợ xóa logic, mọi đường đọc dữ liệu phải xác định rõ đang cần **bản ghi còn hiệu lực**, **bản ghi đã xóa** hay **toàn bộ bản ghi**.

### 5.1. Danh sách và tra cứu theo ID

```sql
-- Danh sách hiển thị cho người dùng: chỉ khách hàng còn hiệu lực
SELECT id, email, full_name
FROM customers
WHERE deleted_at IS NULL
ORDER BY id;

-- Tra cứu một khách hàng còn hiệu lực
SELECT id, email, full_name
FROM customers
WHERE id = ?
  AND deleted_at IS NULL;

-- Thùng rác hoặc màn hình quản trị các bản ghi đã xóa
SELECT id, email, full_name, deleted_at
FROM customers
WHERE deleted_at IS NOT NULL
ORDER BY deleted_at DESC;
```

Với dữ liệu ví dụ, truy vấn đầu trả về `101` và `103`; truy vấn “thùng rác” trả về `102`. Truy vấn theo ID nên lọc `deleted_at` ngay trong SQL thay vì tải bản ghi rồi mới loại bỏ ở Java, để giảm dữ liệu đọc và tránh lộ bản ghi qua các nhánh xử lý khác.

### 5.2. `COUNT`, báo cáo và phân trang

```sql
-- Tổng số hàng đang lưu, bao gồm cả bản ghi đã xóa logic
SELECT COUNT(*) FROM customers;

-- Tổng số khách hàng còn hiệu lực
SELECT COUNT(*) FROM customers
WHERE deleted_at IS NULL;

-- Tổng số khách hàng đã xóa logic
SELECT COUNT(*) FROM customers
WHERE deleted_at IS NOT NULL;
```

Với dữ liệu ví dụ, ba kết quả lần lượt là **3, 2 và 1**. Nếu API trả về danh sách đã lọc nhưng lại tính tổng số bản ghi không lọc, giao diện phân trang sẽ báo sai số trang và tổng kết quả.

Áp dụng **cùng một điều kiện** cho cả truy vấn dữ liệu lẫn truy vấn đếm:

```sql
-- Một trang danh sách khách hàng còn hiệu lực (ví dụ cú pháp phổ biến)
SELECT id, email, full_name
FROM customers
WHERE deleted_at IS NULL
ORDER BY id
LIMIT ? OFFSET ?;

SELECT COUNT(*)
FROM customers
WHERE deleted_at IS NULL;
```

`LIMIT/OFFSET` được nhiều hệ cơ sở dữ liệu hỗ trợ nhưng không phải cú pháp thống nhất của mọi driver; có thể phải dùng phân trang theo cú pháp của hệ quản trị đang sử dụng. Dù viết thế nào, **bộ lọc trạng thái và các điều kiện tìm kiếm phải đồng nhất** giữa dữ liệu trang và tổng số bản ghi.

### 5.3. `JOIN` với bảng có bản ghi đã xóa logic

Giả sử đơn hàng `501` thuộc khách hàng `102` (An, đã xóa logic). Vì An vẫn còn trong bảng, câu truy vấn sau vẫn trả về đơn hàng `501`:

```sql
SELECT o.id, o.amount, c.full_name
FROM orders o
JOIN customers c ON c.id = o.customer_id;
```

Nếu nghiệp vụ chỉ muốn đơn hàng của **khách hàng còn hiệu lực**, thêm điều kiện rõ ràng:

```sql
SELECT o.id, o.amount, c.full_name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE c.deleted_at IS NULL;
```

Ngược lại, màn hình quản trị đơn hàng có thể cần giữ **mọi đơn hàng**, kể cả khi khách hàng đã xóa logic. Khi đó có thể dùng `LEFT JOIN` và đưa điều kiện “khách hàng còn hiệu lực” vào `ON`:

```sql
SELECT o.id, o.amount, c.full_name AS active_customer_name
FROM orders o
LEFT JOIN customers c
  ON c.id = o.customer_id
 AND c.deleted_at IS NULL;
```

Kết quả vẫn giữ đơn hàng `501`, nhưng `active_customer_name` của hàng đó là `NULL`. Điều này hữu ích khi muốn bảo toàn lịch sử đơn hàng mà không công khai thông tin khách hàng đã ngừng hoạt động.

**Cẩn thận với vị trí điều kiện của `LEFT JOIN`:** đặt `c.deleted_at IS NULL` trong `WHERE` có thể cho kết quả khác, vì các hàng không có bản ghi ghép cũng tạo giá trị `NULL`. Hãy quyết định xem muốn lọc **đơn hàng** hay chỉ muốn ẩn **thông tin khách hàng** rồi đặt điều kiện vào `WHERE` hoặc `ON` tương ứng.

### 5.4. Các đường truy cập khác cũng cần lọc

Lỗi bỏ sót lọc trạng thái không chỉ nằm ở danh sách chính:

- Tìm kiếm theo email, truy vấn chi tiết, xuất CSV và báo cáo phải xác định trạng thái được phép xem.
- Các truy vấn con (`EXISTS`, `IN`), `JOIN` qua nhiều bảng và truy vấn tổng hợp phải xét trạng thái xóa của **mỗi bảng liên quan**, nếu các bảng ấy cũng dùng soft delete.
- Các lệnh `UPDATE` nghiệp vụ thường cần `WHERE deleted_at IS NULL` để tránh sửa một bản ghi không còn hiệu lực.
- Bộ nhớ đệm, kết quả tìm kiếm đã lập chỉ mục và các API khác có thể cần được cập nhật hoặc vô hiệu hóa sau khi xóa.

Không nên chỉ ẩn hàng ở giao diện: yêu cầu lọc phải có mặt tại tầng truy cập dữ liệu theo đúng quyền truy cập và ngữ cảnh nghiệp vụ.

## 6. Thao tác qua JDBC bằng `DataSource` và `PreparedStatement`

Ví dụ sau dùng API JDBC chuẩn, giả sử ứng dụng đã cấu hình một `DataSource` và driver cho cơ sở dữ liệu. Mỗi phương thức quản lý kết nối với `try-with-resources`; các câu SQL dùng tham số `?`.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public int hardDelete(long id) throws SQLException {
        String sql = "DELETE FROM customers WHERE id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            return statement.executeUpdate();
        }
    }

    public boolean softDelete(long id) throws SQLException {
        String sql = "UPDATE customers "
                + "SET deleted_at = CURRENT_TIMESTAMP "
                + "WHERE id = ? AND deleted_at IS NULL";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            return statement.executeUpdate() == 1;
        }
    }

    public boolean restore(long id) throws SQLException {
        String sql = "UPDATE customers "
                + "SET deleted_at = NULL "
                + "WHERE id = ? AND deleted_at IS NOT NULL";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            return statement.executeUpdate() == 1;
        }
    }

    public Optional<Customer> findActiveById(long id) throws SQLException {
        String sql = "SELECT id, email, full_name FROM customers "
                + "WHERE id = ? AND deleted_at IS NULL";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Customer(
                        result.getLong("id"),
                        result.getString("email"),
                        result.getString("full_name")
                ));
            }
        }
    }

    public long countActive() throws SQLException {
        String sql = "SELECT COUNT(*) FROM customers WHERE deleted_at IS NULL";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql);
             ResultSet result = statement.executeQuery()) {
            result.next();
            return result.getLong(1);
        }
    }

    public record Customer(long id, String email, String fullName) {}
}
```

Điểm cần hiểu trong đoạn mã:

- `executeUpdate()` trả về **số hàng chịu tác động**. Với `softDelete`, kết quả `true` cho biết đã chuyển một hàng từ trạng thái còn hiệu lực sang đã xóa; `false` có thể nghĩa là không tìm thấy ID hoặc hàng đã được xóa logic trước đó.
- `executeQuery()` trả về `ResultSet` để đọc dữ liệu; `findActiveById` trả `Optional.empty()` nếu không tồn tại khách hàng còn hiệu lực mang ID đó.
- `PreparedStatement#setLong` ràng buộc giá trị ID và tránh ghép chuỗi dữ liệu đầu vào vào SQL. Không dùng `Statement` với SQL nối chuỗi từ người dùng.
- `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` kể cả khi phát sinh `SQLException`. Khi dùng connection pool, thao tác `close()` thông thường trả kết nối cho pool theo cách triển khai `DataSource`.
- Với từng lệnh đơn lẻ, hành vi commit phụ thuộc cấu hình `autoCommit` của kết nối. Nếu việc xóa cần kèm các thao tác khác, hãy dùng **cùng một `Connection`** và quản lý transaction tường minh.

Ví dụ transaction khi xóa logic phải đi cùng một thay đổi khác (như ghi nhật ký kiểm toán): gọi `connection.setAutoCommit(false)`, chạy cả hai `PreparedStatement` trên **cùng kết nối**, `commit()` khi tất cả thành công; nếu một bước thất bại thì `rollback()`. Không mở hai kết nối độc lập cho hai bước rồi mong một lệnh rollback hoàn tác cả hai.

## 7. Những ràng buộc và tình huống dễ sai

### 7.1. Khóa ngoại và dữ liệu lịch sử

Xóa vật lý khách hàng còn đơn hàng có thể gây lỗi ràng buộc hoặc làm mất dữ liệu phụ thuộc nếu đã cấu hình cascade. Xóa logic giữ nguyên liên kết `orders.customer_id`, nhưng ứng dụng cần quyết định việc gì xảy ra với đơn hàng:

- Đơn hàng lịch sử vẫn được lưu và người quản trị có quyền xem?
- Đơn hàng mới có bị chặn khi khách hàng đã bị xóa logic?
- Khi tra cứu đơn hàng, thông tin khách hàng đã xóa logic cần ẩn hay hiển thị theo quyền?

Không có một lựa chọn `JOIN` hay cascade đúng cho mọi nghiệp vụ. Khóa ngoại bảo đảm sự tồn tại vật lý của hàng tham chiếu; nó **không tự bảo đảm** rằng khách hàng đang còn hiệu lực về mặt nghiệp vụ.

### 7.2. Ràng buộc `UNIQUE` khi tạo lại bản ghi

Giả sử có ràng buộc `UNIQUE(email)`. Xóa logic khách hàng `an@example.com` **không giải phóng** giá trị email, vì hàng cũ vẫn tồn tại. Lệnh tạo khách hàng mới cùng email có thể bị từ chối dù giao diện không còn hiển thị khách hàng cũ.

Tùy nhu cầu, có thể chọn khôi phục khách hàng cũ, giữ email duy nhất trên toàn bộ lịch sử, hoặc chỉ yêu cầu duy nhất giữa các hàng còn hiệu lực. Với PostgreSQL, một cách hiện thực lựa chọn cuối là **partial unique index**:

```sql
-- PostgreSQL; không phải cú pháp có thể dùng nguyên vẹn trên mọi RDBMS
CREATE UNIQUE INDEX uq_customers_active_email
ON customers (email)
WHERE deleted_at IS NULL;
```

Đây là lựa chọn thiết kế thay cho ràng buộc `UNIQUE(email)` toàn bảng nếu muốn tái sử dụng email sau khi soft delete. Các hệ quản trị khác có cơ chế khác; cần kiểm tra hỗ trợ của hệ đang dùng. Bài toán chữ hoa/chữ thường của email và quy tắc khôi phục vẫn cần được xử lý riêng.

### 7.3. Tính đồng thời và xóa lặp lại

Điều kiện `WHERE id = ? AND deleted_at IS NULL` giúp một lần soft delete tiếp theo không thay đổi lại thời điểm xóa. Tuy nhiên, việc “đọc trước, kiểm tra rồi cập nhật” bằng nhiều câu lệnh có thể chịu ảnh hưởng của thao tác đồng thời. Nếu hệ thống cần phát hiện cập nhật cạnh tranh, có thể thêm cột `version` và ràng buộc `WHERE version = ?` vào lệnh cập nhật, sau đó kiểm tra số hàng được cập nhật.

Nếu nhiều thao tác phải cùng thành công hoặc cùng thất bại, sử dụng transaction. Các vấn đề tranh chấp khóa, mức cô lập và khả năng nhìn thấy thay đổi trước commit còn phụ thuộc hệ quản trị và cấu hình kết nối.

### 7.4. Hiệu năng truy vấn và chi phí lưu trữ

Soft delete làm số hàng lưu trữ ngày càng lớn. Nếu hầu hết truy vấn đều có `WHERE deleted_at IS NULL`, cần đánh giá chỉ mục phù hợp với mẫu truy cập thực tế, ví dụ kết hợp trường tìm kiếm với trạng thái hoặc dùng partial index trên hệ cơ sở dữ liệu hỗ trợ. Chỉ mục đơn lẻ trên cột trạng thái ít giá trị phân biệt có thể không hiệu quả; đo bằng công cụ `EXPLAIN` và dữ liệu thực thay vì mặc định thêm chỉ mục.

Xóa logic là `UPDATE` và có chi phí ghi, cập nhật chỉ mục tùy hệ cơ sở dữ liệu. Xóa vật lý cũng có chi phí ràng buộc, ghi log và dọn dẹp lưu trữ. Nếu áp dụng chiến lược “soft delete trước, purge sau”, cần chính sách lưu giữ, lịch dọn dẹp theo lô và thứ tự xử lý dữ liệu liên quan để tránh xóa nhầm hoặc tạo giao dịch quá lớn.

### 7.5. Phân quyền và yêu cầu xóa dữ liệu

Một hàng đã xóa logic vẫn có thể được truy xuất bằng SQL hoặc đường API bỏ sót điều kiện lọc. Do đó, ngoài `deleted_at`, phải kiểm tra quyền truy cập của người gọi; với ứng dụng nhiều tenant, truy vấn còn phải ràng buộc đúng `tenant_id` theo lược đồ và ngữ cảnh xác thực.

Việc đáp ứng yêu cầu xóa dữ liệu cá nhân hoặc chính sách giữ dữ liệu có thể đòi hỏi xóa vật lý, ẩn danh hóa và xử lý bản sao khác; chỉ đặt `deleted_at` không đủ. Cũng cần phân biệt xóa phục vụ nghiệp vụ với xóa dữ liệu theo nghĩa bảo mật và tuân thủ.

## 8. Chọn chiến lược và kiểm tra kết quả

**Ưu tiên xóa vật lý** khi bản ghi không cần phục hồi/lưu lịch sử, đã xác định rõ dữ liệu phụ thuộc và chính sách dữ liệu cho phép xóa hẳn. **Ưu tiên xóa logic** khi cần khôi phục, giữ dấu vết nghiệp vụ hoặc bảo toàn liên kết lịch sử, đồng thời đã thiết kế cách lọc các đường đọc. Một số hệ thống dùng cả hai: soft delete trong giai đoạn có thể phục hồi, sau thời hạn lưu giữ thì xóa vật lý theo một quy trình kiểm soát.

Có thể tự kiểm chứng bằng các bước sau trên cơ sở dữ liệu thử nghiệm:

1. Chèn ba khách hàng, trong đó một khách hàng có `deleted_at` khác `NULL`. So sánh `COUNT(*)` với `COUNT(*) WHERE deleted_at IS NULL`.
2. Thực hiện soft delete khách hàng còn hiệu lực bằng `PreparedStatement`; xác nhận truy vấn danh sách không còn thấy người đó nhưng truy vấn quản trị có lọc `deleted_at IS NOT NULL` vẫn thấy.
3. Thêm đơn hàng tham chiếu khách hàng đã xóa logic; so sánh `INNER JOIN` có và không có bộ lọc `c.deleted_at IS NULL`, sau đó thử `LEFT JOIN` với bộ lọc ở `ON`.
4. Thử `DELETE` vật lý trên khách hàng còn đơn hàng với khóa ngoại `fk_orders_customer` ở ví dụ: quan sát `SQLException` vì ràng buộc tham chiếu. Làm việc này trên dữ liệu thử nghiệm và rollback nếu cần.
5. Gọi soft delete hai lần trên cùng một khách hàng; xác nhận lần đầu ảnh hưởng một hàng, lần sau không ảnh hưởng hàng nào và `deleted_at` không bị ghi đè.

### Ghi nhớ

`DELETE` làm bản ghi biến mất khỏi bảng sau commit; soft delete chỉ làm bản ghi **biến mất khỏi góc nhìn nghiệp vụ** nếu mọi truy vấn liên quan đều lọc đúng trạng thái. Trong ứng dụng JDBC, tính đúng đắn phụ thuộc đồng thời vào SQL, `PreparedStatement`/`ResultSet`, transaction và quy tắc truy cập dữ liệu. Hãy coi trạng thái xóa là một phần của điều kiện truy vấn và thiết kế vòng đời dữ liệu ngay từ đầu.
