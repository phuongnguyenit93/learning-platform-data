# Đọc khóa sinh bằng `getGeneratedKeys()` trong JDBC

Trong một ứng dụng Java sử dụng **JDBC** để thao tác với cơ sở dữ liệu quan hệ, thao tác `INSERT` thường không cung cấp trước giá trị khóa chính của bản ghi mới. Cơ sở dữ liệu có thể tự sinh giá trị đó bằng cột `IDENTITY`, `AUTO_INCREMENT`, sequence hoặc cơ chế tương đương. API **`Statement.getGeneratedKeys()`** giúp ứng dụng nhận lại khóa được sinh sau khi thực hiện lệnh ghi, để tiếp tục xử lý mà không phải suy đoán ID.

Bài học thuộc chủ đề **CRUD và khóa sinh**; tập trung vào cách kết hợp `DataSource`, `PreparedStatement`, `executeUpdate()` và `ResultSet` để đọc khóa vừa sinh, kiểm tra lỗi và sử dụng khóa trong transaction.

## 1. Khi nào cần đọc khóa vừa sinh?

Giả sử có hai bảng khách hàng và địa chỉ:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL
);

CREATE TABLE customer_addresses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    city VARCHAR(100) NOT NULL
);
```

> Đây là ví dụ cú pháp SQL theo chuẩn cho cột identity. Cú pháp tạo cột tự sinh có thể khác giữa PostgreSQL, MySQL, SQL Server, H2 và các hệ quản trị khác; chọn cú pháp DDL phù hợp với cơ sở dữ liệu đang sử dụng.

Khi tạo khách hàng, Java chỉ cung cấp `name` và `email`:

```sql
INSERT INTO customers (name, email) VALUES (?, ?);
```

Sau đó ứng dụng cần khóa `customers.id` để thêm một hàng vào `customer_addresses.customer_id`, trả ID cho API hoặc ghi nhận mối liên hệ với các bản ghi khác. Lúc này, `getGeneratedKeys()` cho phép nhận giá trị ID mà chính lệnh `INSERT` vừa tạo ra.

**Không dùng `SELECT MAX(id)` để tìm bản ghi vừa chèn.** Khi có nhiều kết nối ghi đồng thời, giá trị lớn nhất trong bảng có thể thuộc về một giao dịch khác. Cũng không nên đoán ID tiếp theo từ ID trước đó: sequence/identity có thể có khoảng trống do rollback, cấp phát trước hoặc những lệnh ghi khác.

## 2. Luồng thao tác chuẩn

Để lấy khóa sinh khi chèn **một** hàng bằng JDBC, thực hiện theo thứ tự:

1. Lấy `Connection` từ `DataSource`.
2. Tạo `PreparedStatement` với tùy chọn `Statement.RETURN_GENERATED_KEYS` (hoặc yêu cầu cụ thể các cột muốn trả về).
3. Gán tham số bằng các phương thức `setXxx(...)`, sau đó gọi `executeUpdate()` để thực thi `INSERT`.
4. Gọi `preparedStatement.getGeneratedKeys()`. Kết quả là một `ResultSet`, có con trỏ ban đầu nằm **trước** dòng đầu tiên.
5. Gọi `keys.next()` để kiểm tra có khóa được trả về, đọc giá trị và đóng `ResultSet`, `PreparedStatement`, `Connection` theo đúng vòng đời.

```text
DataSource
   │ getConnection()
   ▼
Connection
   │ prepareStatement(sql, RETURN_GENERATED_KEYS)
   ▼
PreparedStatement ── setXxx(...) ── executeUpdate()
   │                                      │
   │ getGeneratedKeys()                   └─ Số hàng chịu tác động
   ▼
ResultSet ── next() ── getLong(1) / getString(1) / getObject(...)
   │
   └─ Khóa của hàng vừa được chèn (nếu driver và lệnh SQL hỗ trợ)
```

`executeUpdate()` trả về **số hàng bị tác động**, không phải khóa chính. `getGeneratedKeys()` mới trả về tập kết quả chứa khóa sinh. Hai giá trị này phục vụ hai mục đích riêng và cần được kiểm tra độc lập.

## 3. Ví dụ Java đầy đủ: chèn khách hàng và nhận ID

Giả sử `customers.id` là số nguyên kiểu `BIGINT` do cơ sở dữ liệu tự sinh. Một repository đơn giản có thể được viết như sau:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long insert(String name, String email) throws SQLException {
        String sql = "INSERT INTO customers (name, email) VALUES (?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     sql, Statement.RETURN_GENERATED_KEYS)) {

            statement.setString(1, name);
            statement.setString(2, email);

            int affectedRows = statement.executeUpdate();
            if (affectedRows != 1) {
                throw new SQLException(
                        "Expected one inserted customer, got " + affectedRows);
            }

            try (ResultSet keys = statement.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException(
                            "Customer inserted, but no generated key was returned");
                }

                long customerId = keys.getLong(1);
                if (keys.wasNull()) {
                    throw new SQLException("Generated customer ID is SQL NULL");
                }

                return customerId;
            }
        }
    }
}
```

Lời gọi từ tầng nghiệp vụ:

```java
long customerId = customerRepository.insert("Lan", "lan@example.com");
System.out.println("ID khách hàng mới: " + customerId);
```

Giá trị in ra do cơ sở dữ liệu quyết định, chẳng hạn `42`; **không có bảo đảm** rằng lần chèn tiếp theo sẽ là `43`.

Các chi tiết cần hiểu trong ví dụ:

- `?` là **placeholder** cho dữ liệu, được gán bằng `setString(...)`. Việc tham số hóa giúp tránh ghép chuỗi dữ liệu đầu vào trực tiếp vào SQL và giảm rủi ro SQL injection.
- `Statement.RETURN_GENERATED_KEYS` yêu cầu JDBC driver cung cấp khóa sinh cho lệnh `INSERT`. Nếu tạo statement mà không bật yêu cầu này, không thể mặc định rằng driver sẽ trả khóa.
- `affectedRows != 1` là kiểm tra phù hợp với **lệnh chèn đúng một hàng** của ví dụ. Với lệnh ghi nhiều hàng hoặc cú pháp đặc biệt, cần dùng tiêu chí khác.
- `keys.next()` là bắt buộc trước khi đọc dòng đầu tiên. `getLong(1)` đọc cột thứ nhất của `ResultSet` khóa sinh; số `1` là **chỉ số cột trong kết quả trả về**, không mặc định là thứ tự cột của bảng.
- `getLong(...)` trả `0` khi giá trị SQL là `NULL`; gọi `wasNull()` ngay sau khi đọc giúp phân biệt `NULL` với số `0`. Với identity thông thường, ID `NULL` là tình huống cần báo lỗi.
- `try-with-resources` đóng `ResultSet`, `PreparedStatement`, `Connection` cả khi xảy ra `SQLException`. Với `DataSource` dùng connection pool, `close()` thường trả kết nối về pool để tái sử dụng.

Phương thức trên giả định mỗi lần gọi tự sử dụng một kết nối ở chế độ transaction do cấu hình kết nối quyết định (thường là `autoCommit=true`). Khi cần nhiều lệnh ghi nguyên tử, phải dùng **cùng một `Connection`** và quản lý transaction như phần sau.

## 4. Hiểu đúng `ResultSet` do `getGeneratedKeys()` trả về

Về cách sử dụng, đây vẫn là `java.sql.ResultSet`:

```java
try (ResultSet keys = statement.getGeneratedKeys()) {
    if (keys.next()) {
        long id = keys.getLong(1);
        // Xử lý id vừa nhận
    } else {
        // Không có khóa nào được trả về
    }
}
```

Tuy nhiên, **cấu trúc và số lượng khóa phụ thuộc lệnh SQL, hệ quản trị và JDBC driver**:

| Tình huống | Cách xử lý đúng |
| --- | --- |
| Chèn một hàng có identity `BIGINT` | Thường đọc `keys.next()` và `keys.getLong(1)`; luôn kiểm tra có dòng. |
| Cột khóa là chuỗi hoặc UUID | Dùng `getString(...)` hoặc `getObject(...)` với kiểu phù hợp, theo khả năng của driver; không ép mọi ID về `long`. |
| Nhiều cột được sinh tự động | Yêu cầu rõ cột cần lấy và kiểm tra metadata của kết quả; không tự suy ra tên/thứ tự cột. |
| `keys.next()` trả `false` | Không có khóa được trả về. Kiểm tra cấu hình statement, SQL, kiểu cột và khả năng hỗ trợ của driver. |
| `INSERT` nhiều hàng hoặc batch | Có thể nhận nhiều dòng khóa, nhưng số lượng, thứ tự và việc hỗ trợ không đồng nhất giữa các driver. |

Đừng mặc định `keys.getLong("id")` luôn hoạt động. Một số driver trả nhãn cột như `GENERATED_KEY`, hoặc dùng nhãn khác với tên `id` trong bảng. Đọc theo vị trí `1` là cách phổ biến cho **một khóa được yêu cầu**, nhưng vẫn cần biết driver đang trả cột nào. Khi cần tên cột cụ thể, hãy thử biến thể ở phần 5 và xác minh trên hệ quản trị thực tế.

## 5. Chỉ định cột khóa muốn nhận

JDBC cung cấp nhiều overload của `Connection.prepareStatement(...)`:

```java
// Yêu cầu driver trả các khóa tự sinh mà driver chọn.
PreparedStatement byFlag = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS);

// Yêu cầu lấy cột có tên "id".
PreparedStatement byName = connection.prepareStatement(
        sql, new String[] {"id"});

// Yêu cầu lấy cột ở vị trí 1 trong bảng đích.
PreparedStatement byIndex = connection.prepareStatement(
        sql, new int[] {1});
```

Đây là **ba cách tạo statement thay thế nhau**, không phải ba statement cần tạo đồng thời. Với các đối tượng tạo ra, vẫn dùng quy trình `setXxx(...)` → `executeUpdate()` → `getGeneratedKeys()` và phải đóng statement đúng cách.

Khi chọn theo tên, chữ hoa/chữ thường và cách diễn giải tên cột có thể khác nhau giữa driver. Khi chọn theo `int[]`, các số là **vị trí cột của bảng đích** theo API, khác với vị trí cột khi gọi `keys.getLong(1)`. Hãy ưu tiên cách mà driver và cơ sở dữ liệu đang dùng hỗ trợ rõ ràng; đừng giả định overload nào cũng hoạt động ở mọi hệ quản trị.

Có thể kiểm tra khả năng hỗ trợ tổng quát từ metadata của kết nối:

```java
boolean supported = connection.getMetaData().supportsGetGeneratedKeys();
```

Nếu trả `false`, không nên xây dựng luồng phụ thuộc `getGeneratedKeys()` cho driver đó. Nếu trả `true`, vẫn cần thử với **cú pháp `INSERT` và loại khóa cụ thể** vì hỗ trợ thực tế có thể khác giữa các lệnh và phiên bản driver. Một số hệ quản trị còn có cú pháp riêng như `INSERT ... RETURNING id`; cú pháp đó thường được đọc bằng `executeQuery()` và không phải thay thế SQL có tính di động tuyệt đối.

## 6. Dùng khóa vừa sinh trong cùng transaction

Một tình huống thường gặp là tạo khách hàng rồi tạo địa chỉ tham chiếu đến khách hàng đó. Nếu chèn khách hàng thành công nhưng chèn địa chỉ thất bại, nghiệp vụ có thể muốn **rollback cả hai thao tác**. Chỉ việc nhận được ID từ `getGeneratedKeys()` không đồng nghĩa bản ghi đã được commit; hai vấn đề này độc lập.

Ví dụ dưới đây dùng cùng `Connection` cho cả hai lệnh, tắt `autoCommit`, nhận khóa ngay sau `INSERT` đầu tiên rồi mới chèn địa chỉ:

```java
public long insertCustomerWithAddress(
        DataSource dataSource, String name, String email, String city)
        throws SQLException {

    String customerSql = "INSERT INTO customers (name, email) VALUES (?, ?)";
    String addressSql =
            "INSERT INTO customer_addresses (customer_id, city) VALUES (?, ?)";

    try (Connection connection = dataSource.getConnection()) {
        boolean oldAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);

        try {
            long customerId;

            try (PreparedStatement customer = connection.prepareStatement(
                    customerSql, Statement.RETURN_GENERATED_KEYS)) {
                customer.setString(1, name);
                customer.setString(2, email);

                if (customer.executeUpdate() != 1) {
                    throw new SQLException("Cannot insert customer");
                }

                try (ResultSet keys = customer.getGeneratedKeys()) {
                    if (!keys.next()) {
                        throw new SQLException("No generated customer ID");
                    }
                    customerId = keys.getLong(1);
                    if (keys.wasNull()) {
                        throw new SQLException("Generated customer ID is NULL");
                    }
                }
            }

            try (PreparedStatement address =
                    connection.prepareStatement(addressSql)) {
                address.setLong(1, customerId);
                address.setString(2, city);

                if (address.executeUpdate() != 1) {
                    throw new SQLException("Cannot insert customer address");
                }
            }

            connection.commit();
            return customerId;
        } catch (SQLException | RuntimeException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }
            throw error;
        } finally {
            connection.setAutoCommit(oldAutoCommit);
        }
    }
}
```

Điểm cốt lõi của ví dụ là **cùng một kết nối, cùng một transaction**. Khi `autoCommit=false`, ứng dụng thường có thể đọc khóa ngay sau `executeUpdate()` mà chưa cần `commit()`, và dùng khóa đó cho câu lệnh tiếp theo trong cùng transaction. Nếu lỗi xảy ra trước commit, `rollback()` hủy những thay đổi chưa commit của transaction. ID đã được cấp phát có thể **không được tái sử dụng** sau rollback; không nên suy từ các giá trị ID ra số lượng bản ghi đã lưu.

Trong dự án thực tế, nên đóng gói phần `INSERT` khách hàng dùng `Connection` được truyền vào thành một helper để tái sử dụng giữa nghiệp vụ đơn lẻ và nghiệp vụ nhiều bước. Helper đó không nên tự mở kết nối mới khi đang tham gia transaction của bên gọi.

## 7. Điều gì thay đổi với insert nhiều hàng và batching?

`PreparedStatement.addBatch()` và `executeBatch()` giúp gửi nhiều lệnh ghi theo nhóm, nhưng **không có quy tắc chung bảo đảm** rằng mọi driver đều trả về đúng một khóa, theo đúng thứ tự, cho mỗi phần tử của batch. Khả năng trả khóa còn chịu ảnh hưởng của cú pháp `INSERT`, hệ quản trị, kiểu cột và cấu hình driver.

Nếu cần ánh xạ chính xác từng bản ghi đầu vào sang ID đã sinh:

- Kiểm tra tài liệu JDBC driver về `getGeneratedKeys()` sau `executeBatch()` hoặc `INSERT` nhiều hàng.
- Thử thực tế trường hợp nhiều hàng, trường hợp thất bại giữa batch và lệnh có điều kiện; xác nhận **số lượng lẫn thứ tự** của các khóa trả về.
- Nếu cần bảo đảm ánh xạ mà driver không cung cấp, cân nhắc chèn từng hàng trong cùng transaction hoặc dùng cú pháp trả khóa phù hợp riêng với hệ quản trị, chẳng hạn `RETURNING`, kèm thiết kế ánh xạ rõ ràng.

Không lấy một `ResultSet` có nhiều khóa rồi mặc định khóa thứ `i` luôn tương ứng với đầu vào thứ `i` nếu tài liệu driver chưa cam kết điều đó.

## 8. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Việc nên kiểm tra |
| --- | --- | --- |
| `executeUpdate()` trả `1` nhưng `keys.next()` là `false` | Không yêu cầu trả khóa, cột không được sinh, SQL/driver không hỗ trợ | Kiểm tra `RETURN_GENERATED_KEYS` hoặc mảng tên cột, DDL và `supportsGetGeneratedKeys()`; thử với driver đang dùng. |
| `SQLFeatureNotSupportedException` hoặc lỗi JDBC khi lấy khóa | Driver không hỗ trợ API hay biến thể đang gọi | Xem tài liệu và phiên bản driver; cân nhắc cú pháp trả khóa của hệ quản trị. |
| Đọc bằng `getLong("id")` báo không tìm thấy cột | Nhãn cột trong `ResultSet` khác `id` | Kiểm tra `ResultSetMetaData`, dùng `getLong(1)` cho một khóa đã xác minh, hoặc chỉ định cột rõ ràng. |
| ID là UUID/chuỗi nhưng mã đọc bằng `getLong(1)` | Kiểu Java không tương ứng kiểu SQL | Đọc bằng `getString(1)` / `getObject(1)` với kiểu phù hợp; kiểm tra dữ liệu thực trả về. |
| Có hàng được tạo nhưng khóa đã lấy không dùng được sau lỗi | Transaction đã rollback hoặc thao tác tiếp theo dùng kết nối/transaction khác | Kiểm tra transaction và phạm vi sử dụng `Connection`; đừng coi khóa nhận được là bằng chứng commit thành công. |
| Số khóa trả về ít hơn số phần tử batch | Hỗ trợ batch generated keys khác nhau tùy driver | Không suy đoán ánh xạ; kiểm tra tài liệu driver và cách thực hiện batch. |

Khi chẩn đoán, nên ghi log ngoại lệ SQL cùng `SQLState`, mã lỗi của nhà cung cấp (`getErrorCode()`), loại câu lệnh và số hàng tác động. Tránh log thông tin nhạy cảm của khách hàng hoặc nội dung tham số chưa được che phù hợp.

## 9. Những nguyên tắc cần nhớ

1. **Yêu cầu khóa trước khi chạy `INSERT`** bằng `RETURN_GENERATED_KEYS` hoặc overload chỉ định cột.
2. **Chỉ đọc sau khi lệnh ghi thành công**, dùng `getGeneratedKeys()` và kiểm tra `keys.next()` trước khi `getXxx(...)`.
3. **Đọc đúng kiểu dữ liệu** của khóa và không nhầm số hàng do `executeUpdate()` trả về với ID.
4. **Quản lý tài nguyên** bằng `try-with-resources`; không dùng `ResultSet` sau khi statement/kết nối liên quan đã đóng.
5. **Giữ nguyên kết nối khi thao tác thuộc cùng transaction** và chỉ báo thành công nghiệp vụ sau khi `commit()` thành công.
6. **Xác minh khác biệt giữa driver** khi đọc nhiều khóa, batch hoặc nhiều cột sinh tự động.

### Tự thực hành

Tạo bảng `books` có `id` tự sinh và các cột `title`, `author`. Viết phương thức `long createBook(DataSource dataSource, String title, String author)` sử dụng `PreparedStatement` tham số hóa, kiểm tra đúng một hàng được chèn và trả về khóa qua `getGeneratedKeys()`. Sau đó thử hai thay đổi: (a) bỏ `RETURN_GENERATED_KEYS`, (b) đổi kiểu khóa thành một kiểu không phải số nguyên. Quan sát driver trả về gì và sửa cách đọc khóa tương ứng. Nếu thử nghiệm với batch, hãy kiểm chứng số lượng và thứ tự khóa thay vì dựa vào giả định.

**Kết luận:** `getGeneratedKeys()` nối kết thao tác **Create** của CRUD với các thao tác cần khóa chính sau đó. Mã JDBC đáng tin cậy phải yêu cầu khóa đúng cách, xử lý `ResultSet` cẩn thận, đọc đúng kiểu dữ liệu và quản lý transaction phù hợp với yêu cầu nghiệp vụ.
