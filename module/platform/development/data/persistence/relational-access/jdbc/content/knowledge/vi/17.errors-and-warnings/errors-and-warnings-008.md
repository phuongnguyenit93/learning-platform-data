# Đọc `SQLWarning` trên `Connection`, `Statement` và `ResultSet` trong JDBC

Trong chương **Lỗi và cảnh báo**, một thao tác JDBC có thể hoàn tất thành công nhưng driver hoặc cơ sở dữ liệu vẫn muốn thông báo rằng có điều gì cần chú ý: dữ liệu bị cắt bớt, cách chuyển đổi kiểu có giới hạn, một cấu hình chưa được áp dụng như mong đợi hoặc một thông điệp riêng của hệ quản trị. Nếu ứng dụng Java chỉ bắt `SQLException`, những thông tin này có thể bị bỏ qua.

JDBC cung cấp `java.sql.SQLWarning` cùng phương thức `getWarnings()` trên **`Connection`, `Statement` và `ResultSet`**. Mỗi đối tượng quản lý chuỗi cảnh báo của riêng mình, với thời điểm tự xóa khác nhau. Bài học hướng dẫn đọc đúng phạm vi, duyệt toàn bộ chuỗi, không bỏ lỡ cảnh báo khi dịch con trỏ `ResultSet`, phân biệt cảnh báo với lỗi, và đưa việc quan sát cảnh báo vào các thao tác CRUD dùng `DataSource`, `PreparedStatement` và `ResultSet`.

## 1. `SQLWarning` là gì?

`SQLWarning` kế thừa `SQLException` nhưng được JDBC dùng để biểu diễn **cảnh báo không ngăn thao tác hoàn thành bình thường**. Thông thường, JDBC không ném `SQLWarning` như ngoại lệ của một thao tác thành công; ứng dụng phải **chủ động truy vấn cảnh báo** trên đối tượng liên quan.

Ví dụ khái niệm:

```text
PreparedStatement.executeUpdate()
             |
       +-----+--------------------+
       |                          |
   Thành công                 SQLException
       |                          |
       v                          v
    update count            xử lý lỗi/transaction
       |
       v
  statement.getWarnings()
       |
  null hoặc chuỗi SQLWarning
```

Một câu `INSERT` hoặc `SELECT` thành công **không đồng nghĩa** `getWarnings() == null`. Ngược lại, `getWarnings() == null` chỉ cho biết đối tượng hiện không có cảnh báo trong chuỗi có thể truy xuất; điều đó **không chứng minh** mọi chuyển đổi, tối ưu hay kiểm tra nghiệp vụ đều hoàn hảo.

Ba thông tin thường có ích của mỗi `SQLWarning`:

| Phương thức | Nội dung | Cách sử dụng |
| --- | --- | --- |
| `getMessage()` | Mô tả cảnh báo do driver/DB cung cấp | Đọc để chẩn đoán; kiểm soát dữ liệu nhạy cảm khi ghi log |
| `getSQLState()` | Mã trạng thái SQLState, có thể là `null` | Nhận diện loại vấn đề theo chuẩn và tài liệu DB |
| `getErrorCode()` | Mã lỗi/cảnh báo riêng của nhà cung cấp | Đối chiếu tài liệu driver/DB, thường phải kèm tên và phiên bản |

Trong quy ước SQLState, lớp mã bắt đầu bằng `01` thường thể hiện *warning*, chẳng hạn `01004` liên quan đến cắt ngắn dữ liệu. Tuy nhiên, đừng suy ra mọi driver đều cung cấp mã này hoặc luôn phân loại giống nhau; hãy kiểm tra cả thông điệp và tài liệu của cơ sở dữ liệu đang sử dụng.

## 2. Ba nơi lưu cảnh báo và vòng đời của chúng

JDBC cho phép đọc cảnh báo từ ba loại đối tượng:

| Đối tượng | Phương thức | Cảnh báo thường liên quan đến | Khi nào có nguy cơ mất chuỗi cảnh báo |
| --- | --- | --- | --- |
| `Connection` | `connection.getWarnings()` | Kết nối, phiên làm việc hoặc thao tác có cảnh báo gắn với kết nối | Chuỗi được JDBC mô tả là tự xóa khi bắt đầu transaction mới; có thể chủ động `clearWarnings()` |
| `Statement` / `PreparedStatement` | `statement.getWarnings()` | Thực thi SQL của statement | Tự xóa khi statement được thực thi hoặc thực thi lại |
| `ResultSet` | `resultSet.getWarnings()` | Đọc hàng, cột và chuyển đổi kết quả | Tự xóa khi đọc một hàng mới |

`PreparedStatement` triển khai giao diện `Statement`, vì vậy có thể gọi `getWarnings()` và `clearWarnings()` trực tiếp trên `PreparedStatement`.

**Điều quan trọng nhất:** Không có một lệnh `connection.getWarnings()` nào tự động tổng hợp mọi cảnh báo đã phát sinh trên các `PreparedStatement` và `ResultSet` thuộc kết nối đó. Cần kiểm tra **từng đối tượng liên quan tại thời điểm phù hợp**.

Đối với truy vấn, thời điểm đọc gợi ý như sau:

```text
Connection mở
    |
    v
PreparedStatement.executeQuery()
    |--> Đọc Statement.getWarnings() sau execute
    v
ResultSet
    |--> getWarnings() trước khi đọc hàng đầu nếu cần
    |--> next() -> đọc cột -> getWarnings() của hàng hiện tại
    |--> next() -> đọc cột -> getWarnings() của hàng tiếp theo
    v
Đọc Connection.getWarnings() trước khi đóng
    |
    v
Đóng ResultSet / Statement / Connection
```

Sau khi đóng một `Connection`, `Statement` hoặc `ResultSet`, việc truy vấn cảnh báo không còn hợp lệ; lời gọi có thể ném `SQLException`. Vì vậy, không được chỉ chờ đến sau khi thoát `try-with-resources` mới gọi `getWarnings()`.

## 3. Đọc toàn bộ chuỗi cảnh báo

`getWarnings()` trả về **cảnh báo đầu tiên** hoặc `null`. Khi có nhiều cảnh báo, chúng được nối qua `SQLWarning.getNextWarning()`. Chỉ in cảnh báo đầu tiên sẽ bỏ sót những cảnh báo tiếp theo.

```java
import java.sql.SQLWarning;

public final class JdbcWarningPrinter {
    private JdbcWarningPrinter() {}

    public static void printWarnings(String source, SQLWarning first) {
        int ordinal = 0;
        for (SQLWarning warning = first;
             warning != null;
             warning = warning.getNextWarning()) {
            ordinal++;
            System.out.printf(
                    "[%s] warning #%d: SQLState=%s, vendorCode=%d, message=%s%n",
                    source,
                    ordinal,
                    warning.getSQLState(),
                    warning.getErrorCode(),
                    warning.getMessage());
        }
    }
}
```

Cách dùng:

```java
JdbcWarningPrinter.printWarnings(
        "connection", connection.getWarnings());
JdbcWarningPrinter.printWarnings(
        "statement", statement.getWarnings());
JdbcWarningPrinter.printWarnings(
        "result set", resultSet.getWarnings());
```

Đoạn sử dụng trên giả định cả ba biến đang trỏ đến **đối tượng JDBC còn mở**. Nếu không có cảnh báo, `first == null` và vòng lặp không thực hiện lần nào.

**Phân biệt chuỗi:** `SQLWarning.getNextWarning()` là cách duyệt các cảnh báo đúng kiểu. `SQLException.getNextException()` là cách duyệt chuỗi ngoại lệ SQL khi một thao tác lỗi. Do `SQLWarning` kế thừa `SQLException`, hai khái niệm có quan hệ về kiểu Java, nhưng ứng dụng nên duyệt **chuỗi cảnh báo** và **chuỗi ngoại lệ** theo ngữ cảnh tương ứng.

Ví dụ kiểm tra ngoại lệ riêng:

```java
try {
    statement.executeUpdate();
} catch (java.sql.SQLException first) {
    for (java.sql.SQLException error = first;
         error != null;
         error = error.getNextException()) {
        System.err.printf(
                "SQLState=%s, code=%d, message=%s%n",
                error.getSQLState(),
                error.getErrorCode(),
                error.getMessage());
    }
    throw first;
}
```

Nếu `executeUpdate()` đã ném `SQLException`, đừng cố coi việc lấy warning là cách thay thế xử lý lỗi và rollback. Khi một transaction có bước ghi thất bại, tầng sở hữu transaction phải quyết định có `rollback()`, thử lại hay báo lỗi ra ngoài.

## 4. Ví dụ hoàn chỉnh: truy vấn nhiều hàng và đọc cảnh báo đúng lúc

Giả sử có bảng:

```sql
CREATE TABLE customer (
    id    BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);
```

Repository sau đọc danh sách email bằng SQL tham số hóa. Nó kiểm tra cảnh báo ở `PreparedStatement` ngay sau `executeQuery()`, và kiểm tra `ResultSet` **sau khi đã đọc giá trị của từng hàng**, trước lần gọi `next()` tiếp theo:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLWarning;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class CustomerQueryRepository {
    private final DataSource dataSource;

    public CustomerQueryRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<String> findEmailsFromId(long minId) throws SQLException {
        String sql =
                "SELECT email FROM customer WHERE id >= ? ORDER BY id";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, minId);

            List<String> emails = new ArrayList<>();
            try (ResultSet rs = ps.executeQuery()) {
                logWarnings("PreparedStatement after executeQuery",
                        ps.getWarnings());
                logWarnings("ResultSet after executeQuery",
                        rs.getWarnings());

                int rowNumber = 0;
                while (rs.next()) {
                    rowNumber++;
                    String email = rs.getString("email");
                    emails.add(email);

                    // Phải đọc trước khi next() đi sang hàng kế tiếp.
                    logWarnings("ResultSet row " + rowNumber,
                            rs.getWarnings());
                }
            }

            // Đọc trước khi đóng Connection; tùy driver, các cảnh báo
            // gắn với kết nối có thể khác cảnh báo của Statement.
            logWarnings("Connection", connection.getWarnings());
            return emails;
        }
    }

    private static void logWarnings(String scope, SQLWarning first) {
        for (SQLWarning warning = first;
             warning != null;
             warning = warning.getNextWarning()) {
            System.out.printf(
                    "%s: state=%s, vendorCode=%d, detail=%s%n",
                    scope,
                    warning.getSQLState(),
                    warning.getErrorCode(),
                    warning.getMessage());
        }
    }
}
```

Ví dụ chỉ dùng API JDBC chuẩn và Java cơ bản. `DataSource` cấp kết nối, `PreparedStatement` truyền tham số `minId` bằng `setLong`, `ResultSet` đọc dữ liệu, và `try-with-resources` đóng đối tượng theo thứ tự hợp lý.

Vì cảnh báo của `ResultSet` có thể được xóa khi đọc hàng mới, gọi `rs.getWarnings()` **chỉ một lần sau khi duyệt hết tất cả các hàng** có nguy cơ bỏ lỡ các cảnh báo phát sinh ở những hàng trước. Tương tự, nếu tái thực thi cùng một `PreparedStatement`, nên đọc cảnh báo của lần thực thi trước **trước lần `execute...()` kế tiếp**.

Trong môi trường thực tế, thay `System.out.printf` bằng cơ chế ghi log/giám sát có kiểm soát. Thông điệp của driver có thể chứa câu SQL, giá trị dữ liệu hoặc chi tiết hệ thống; cần tránh ghi lộ dữ liệu cá nhân, tham số đăng nhập và thông tin nhạy cảm.

## 5. Kiểm tra cảnh báo sau thao tác ghi dữ liệu

Các thao tác `INSERT`, `UPDATE` và `DELETE` thường dùng `executeUpdate()`. Một số driver có thể trả update count như mong đợi nhưng vẫn gắn cảnh báo cho statement:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public void updateEmail(DataSource dataSource, long customerId, String newEmail)
        throws SQLException {
    String sql = "UPDATE customer SET email = ? WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setString(1, newEmail);
        statement.setLong(2, customerId);

        int updatedRows = statement.executeUpdate();
        JdbcWarningPrinter.printWarnings(
                "UPDATE statement", statement.getWarnings());
        JdbcWarningPrinter.printWarnings(
                "UPDATE connection", connection.getWarnings());

        if (updatedRows != 1) {
            throw new SQLException(
                    "Cập nhật cần ảnh hưởng đúng một dòng, thực tế: "
                    + updatedRows);
        }
    }
}
```

Đây là **ví dụ phương thức** có thể đặt trong một lớp Java; `JdbcWarningPrinter` là lớp tiện ích đã định nghĩa ở phần 3. Ví dụ giả định `DataSource` cung cấp kết nối mới với `autoCommit=true` và yêu cầu cập nhật đúng một dòng.

**Update count và warning là hai thông tin độc lập:**

- `executeUpdate()` trả số dòng bị ảnh hưởng theo hợp đồng JDBC và cách DB/driver diễn giải câu lệnh.
- `getWarnings()` trả các cảnh báo không làm `executeUpdate()` thất bại theo đường thông thường.
- `updatedRows == 1` không tự đảm bảo giá trị ghi **đúng về nghiệp vụ**, không bị cắt/chuẩn hóa ngoài mong đợi hoặc đáp ứng mọi ràng buộc ứng dụng.

Nếu ứng dụng phải **dừng giao dịch khi có cảnh báo nghiêm trọng**, cần định nghĩa chính sách đánh giá cảnh báo và kiểm tra nó **trước `commit()`** trong transaction do ứng dụng sở hữu. Không thể trông cậy vào cảnh báo để tự rollback một thao tác đã chạy trong `autoCommit=true`.

## 6. `clearWarnings()` dùng để làm gì?

Mỗi đối tượng JDBC trong ba loại trên đều cung cấp `clearWarnings()` để **xóa chuỗi cảnh báo hiện tại trên đối tượng ấy**:

```java
SQLWarning current = statement.getWarnings();
JdbcWarningPrinter.printWarnings("before clear", current);

statement.clearWarnings(); // Xóa các warning gắn với statement.
SQLWarning afterClear = statement.getWarnings(); // Thông thường là null.
```

Tương tự có thể gọi `connection.clearWarnings()` và `resultSet.clearWarnings()` trong thời gian chúng còn mở. Xóa warning trên `Statement` **không đồng nghĩa** xóa warning của `Connection` hoặc `ResultSet`.

Cần phân biệt:

- **Đọc:** `getWarnings()` không có ý nghĩa xác nhận đã xử lý và không được xem là thao tác tự xóa warning.
- **Xóa có chủ đích:** `clearWarnings()` chỉ xóa thông tin chẩn đoán; nó không sửa dữ liệu, rollback, commit hoặc khôi phục một chuyển đổi bị mất thông tin.
- **Tự xóa theo vòng đời:** JDBC mô tả warning của `Statement` được xóa khi thực thi lại statement, warning của `ResultSet` được xóa khi đọc hàng mới và warning của `Connection` được xóa khi bắt đầu transaction mới.
- **Đối tượng đóng:** không đợi `try-with-resources` đã đóng tài nguyên rồi mới gọi `getWarnings()` hoặc `clearWarnings()`.

Một mẫu đọc rồi xóa giúp tránh ghi log lặp:

```java
JdbcWarningPrinter.printWarnings("statement", statement.getWarnings());
statement.clearWarnings();
```

Chỉ xóa sau khi đã xử lý hoặc chuyển cảnh báo tới lớp chẩn đoán thích hợp. Trong ứng dụng sử dụng connection pool hoặc framework quản lý transaction, không tự ý xóa cảnh báo của kết nối đang được tầng khác sở hữu nếu điều đó khiến tầng giám sát bỏ lỡ thông tin.

## 7. Các cảnh báo đáng chú ý và khác biệt giữa driver

### Cảnh báo dữ liệu bị cắt bớt

`java.sql.DataTruncation` là lớp con của `SQLWarning`, cung cấp thông tin về việc dữ liệu đã bị cắt:

```java
import java.sql.DataTruncation;
import java.sql.SQLWarning;

for (SQLWarning warning = statement.getWarnings();
     warning != null;
     warning = warning.getNextWarning()) {
    if (warning instanceof DataTruncation) {
        DataTruncation truncated = (DataTruncation) warning;
        System.err.printf(
                "Truncation: index=%d, dataSize=%d, transferSize=%d%n",
                truncated.getIndex(),
                truncated.getDataSize(),
                truncated.getTransferSize());
    }
}
```

Các trường của `DataTruncation` mô tả vị trí liên quan và độ dài dữ liệu trước/sau chuyển đổi theo hợp đồng JDBC. Không phải mọi trường hợp dữ liệu bị rút ngắn đều được driver trả dưới dạng một `DataTruncation` có thể truy cập từ `getWarnings()`: tùy chiều đọc/ghi, DB có thể **ném exception** hoặc áp dụng quy tắc SQL riêng. Vì thế, phải kiểm tra cả ngoại lệ, ràng buộc cột, kiểu tham số và hành vi của driver.

### Nhóm cảnh báo nên xử lý ra sao?

| Dạng cảnh báo quan sát được | Hành động gợi ý |
| --- | --- |
| Cắt ngắn, mất độ chính xác hoặc chuyển đổi kiểu | Xác minh dữ liệu trước/sau; cân nhắc coi là lỗi nghiệp vụ và rollback nếu còn trong transaction |
| Cảnh báo về cú pháp, khả năng tương thích hay tính năng DB | Đối chiếu tài liệu driver/DB; xem lại SQL và phiên bản |
| Cảnh báo về cấu hình hoặc tối ưu | Ghi nhận kèm môi trường, đo hiệu năng thực tế nếu cần |
| Thông điệp vendor-specific không rõ ý nghĩa | Lưu SQLState, vendor code, driver version; điều tra trước khi tự động bỏ qua hoặc retry |

Không nên hard-code quy tắc “có bất kỳ `SQLWarning` nào thì luôn rollback”. Một số cảnh báo chỉ mang tính thông tin; một số khác ảnh hưởng trực tiếp đến tính đúng đắn. **Chính sách xử lý phải dựa vào loại cảnh báo và yêu cầu nghiệp vụ**.

Driver và DB cũng có thể không cung cấp toàn bộ thông điệp máy chủ qua JDBC hoặc gắn một cảnh báo vào phạm vi khác với dự đoán. Vì vậy, việc triển khai ghi nhận warning cần kiểm thử với đúng phiên bản driver, DB và câu SQL, thay vì dựa vào một ví dụ mà mọi môi trường đều phải phát sinh warning.

## 8. Những lỗi thường gặp khi làm việc với `SQLWarning`

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ bắt `SQLException` và không bao giờ gọi `getWarnings()` | Bỏ sót cảnh báo khi thao tác vẫn thành công | Kiểm tra warning ở những điểm có ý nghĩa |
| Chỉ gọi `connection.getWarnings()` | Không thấy warning riêng của `PreparedStatement` hay `ResultSet` | Đọc từng phạm vi liên quan |
| Chỉ xem cảnh báo đầu tiên | Không thấy các warning tiếp theo trong chuỗi | Duyệt `getNextWarning()` tới `null` |
| Đọc warning của `ResultSet` sau khi đã gọi `next()` sang hàng mới | Warning của hàng trước có thể đã bị xóa | Đọc sau các getter của **hàng hiện tại** |
| Thực thi lại statement trước khi đọc warning | Chuỗi warning của lần chạy trước có thể mất | Đọc ngay sau `executeQuery/executeUpdate/execute` |
| Gọi `getWarnings()` sau khi tài nguyên đã đóng | Có thể gặp `SQLException` | Đọc trong khối `try-with-resources` khi đối tượng còn mở |
| Gọi `clearWarnings()` để “xử lý lỗi” | Chỉ xóa thông tin, không sửa dữ liệu | Phân loại và xử lý nguyên nhân trước khi clear |
| Dùng duy nhất chuỗi `getMessage()` để phân nhánh nghiệp vụ | Thông điệp có thể thay đổi theo driver/phiên bản/ngôn ngữ | Xem SQLState, vendor code, loại warning, ngữ cảnh |
| Ghi nguyên thông điệp cảnh báo vào log công khai | Có thể lộ SQL hoặc dữ liệu nhạy cảm | Giới hạn truy cập log, che dữ liệu cần bảo vệ |
| Cho rằng không có warning tức là không mất dữ liệu | Driver có thể không phát mọi cảnh báo mong đợi | Xác thực dữ liệu, schema và điều kiện nghiệp vụ độc lập |

## 9. Thực hành với `DataSource` và hai loại truy vấn

Thử nghiệm trên cơ sở dữ liệu và driver mà dự án sử dụng:

1. **Khởi tạo môi trường:** Tạo bảng `customer(id, email)` như ví dụ; ghi lại tên và phiên bản DB/driver từ `Connection.getMetaData()` để đối chiếu kết quả.
2. **Truy vấn nhiều hàng:** Chèn vài bản ghi, gọi phương thức `findEmailsFromId(...)`. Xác nhận thứ tự gọi `getWarnings()` sau `executeQuery()` và sau khi đọc từng hàng, rồi trước khi kết thúc `try-with-resources`.
3. **Thao tác ghi:** Thực hiện `UPDATE` bằng `PreparedStatement`, ghi cả `executeUpdate()` và chuỗi warning của statement/kết nối. Kiểm tra `SQLState` và `vendorCode` nếu có.
4. **Xóa warning có chủ đích:** Đọc warning hiện tại, gọi `clearWarnings()` và quan sát kết quả. Nhớ rằng kết quả có thể là `null` ngay từ đầu nếu DB không phát cảnh báo.
5. **Thử tình huống có thể tạo warning:** Tham khảo tài liệu driver để chọn một trường hợp an toàn, chẳng hạn chuyển đổi kiểu có cảnh báo hoặc truy vấn đưa ra thông báo chẩn đoán. **Không ép dữ liệu thật bị cắt** chỉ để tạo warning. Một số trường hợp sẽ ném `SQLException` thay vì tạo `SQLWarning`.
6. **Quan sát việc tự xóa:** Với môi trường có phát warning, kiểm tra sự khác biệt trước/sau khi thực thi lại statement, đọc hàng tiếp theo hoặc bắt đầu transaction mới.
7. **Phân loại:** Xác định cảnh báo nào chỉ cần log, cảnh báo nào cần coi là lỗi nghiệp vụ và rollback trước commit khi ứng dụng quản lý transaction.

**Tự kiểm tra:**

- Vì sao `executeUpdate()` trả `1` không có nghĩa là kết quả hoàn toàn không có cảnh báo?
- Vì sao chỉ gọi `connection.getWarnings()` vẫn có thể bỏ sót cảnh báo từ `ResultSet`?
- Khi nào một warning phát sinh lúc đọc hàng thứ nhất bị mất, dù `ResultSet` chưa đóng?
- `SQLWarning.getNextWarning()` và `SQLException.getNextException()` khác nhau trong tình huống sử dụng nào?
- `clearWarnings()` có làm thay đổi kết quả `INSERT` hay hoàn tác transaction không?
- Vì sao không thể dựa vào một SQLState/vendor code cứng để xử lý mọi loại DB?

**Ghi nhớ:** Trong JDBC, cảnh báo có thể tồn tại dù lệnh SQL thành công. Đọc `getWarnings()` trên đúng **`Connection`, `Statement`/`PreparedStatement` hoặc `ResultSet`** khi đối tượng còn mở; duyệt toàn bộ chuỗi qua `getNextWarning()`; chú ý vòng đời tự xóa của từng đối tượng. Sau khi quan sát, phân loại cảnh báo theo mức ảnh hưởng nghiệp vụ; `clearWarnings()` chỉ xóa thông tin chẩn đoán, không thay thế kiểm tra dữ liệu hoặc xử lý `SQLException` và transaction.
