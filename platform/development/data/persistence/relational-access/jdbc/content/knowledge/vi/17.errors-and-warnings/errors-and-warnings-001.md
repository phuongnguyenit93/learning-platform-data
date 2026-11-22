# Đọc message, SQLState và mã lỗi riêng của nhà cung cấp

## 1. Vì sao cần đọc đúng thông tin lỗi JDBC?

Trong **JDBC (Java Database Connectivity)**, API Java để truy cập cơ sở dữ liệu quan hệ, các thao tác như mở kết nối, thực thi `INSERT`, `UPDATE`, `SELECT` hoặc đọc `ResultSet` có thể thất bại. JDBC biểu diễn phần lớn lỗi truy cập cơ sở dữ liệu bằng `java.sql.SQLException`.

Thông báo lỗi hiển thị cho người đọc chỉ là một phần của thông tin chẩn đoán. Một `SQLException` có ba thuộc tính đặc biệt hữu ích:

1. **Message** từ `getMessage()`: mô tả lỗi bằng văn bản.
2. **SQLState** từ `getSQLState()`: mã phân loại lỗi bằng chuỗi, thường có năm ký tự.
3. **Vendor error code** từ `getErrorCode()`: số nguyên do hệ quản trị cơ sở dữ liệu hoặc trình điều khiển JDBC quy định.

Ba thuộc tính trả lời ba câu hỏi khác nhau: *chuyện gì được báo là đã xảy ra*, *lỗi thuộc nhóm nào*, và *hệ thống cơ sở dữ liệu cụ thể nhận diện lỗi ra sao*. Không nên chỉ dựa vào message để quyết định xử lý nghiệp vụ, vì câu chữ có thể thay đổi giữa các phiên bản và trình điều khiển, hoặc chứa thông tin nhạy cảm.

Ví dụ, một ứng dụng thêm khách hàng có `id` đã tồn tại. PostgreSQL có thể trả SQLState `23505` (vi phạm ràng buộc duy nhất), trong khi MySQL thường trả SQLState `23000` và mã lỗi nhà cung cấp `1062` cho tình huống khóa trùng. Đây là những **ví dụ theo hệ quản trị/driver**, không phải bộ mã có thể áp dụng nguyên xi cho mọi cơ sở dữ liệu.

## 2. Đọc ba thuộc tính trực tiếp từ `SQLException`

```java
import java.sql.SQLException;

public class JdbcErrorInfo {
    public static void print(SQLException exception) {
        System.err.println("Message     : " + exception.getMessage());
        System.err.println("SQLState    : " + exception.getSQLState());
        System.err.println("Vendor code : " + exception.getErrorCode());
    }
}
```

| Phương thức | Kiểu dữ liệu | Dùng để làm gì? | Giới hạn cần nhớ |
|---|---|---|---|
| `getMessage()` | `String` | Hiển thị mô tả do driver/cơ sở dữ liệu cung cấp, hỗ trợ chẩn đoán | Có thể `null`; văn bản có thể thay đổi và có thể chứa thông tin cần bảo vệ |
| `getSQLState()` | `String` | Phân loại lỗi theo quy ước SQLState | Có thể `null`; mã cụ thể và mức độ tuân thủ phụ thuộc driver |
| `getErrorCode()` | `int` | Tra cứu mã lỗi trong tài liệu của hệ quản trị/driver đang dùng | Không có ý nghĩa thống nhất giữa các nhà cung cấp; `0` có thể là chưa có mã cụ thể |

Giả sử driver trả thông tin sau:

```text
Message     : Duplicate entry '101' for key 'PRIMARY'
SQLState    : 23000
Vendor code : 1062
```

Ta có thể giải thích: cơ sở dữ liệu thông báo một giá trị bị trùng; SQLState thuộc **lớp `23` (vi phạm ràng buộc toàn vẹn)**; mã `1062` giúp tra cứu chính xác lỗi trong ngữ cảnh **MySQL**. Dòng message chỉ minh họa, vì nội dung thực tế phụ thuộc phiên bản, ngôn ngữ và driver.

Điểm quan trọng là **mã lỗi `1062` không có nghĩa chung trên PostgreSQL, Oracle hay SQL Server**. Cũng không thể khẳng định mọi lỗi thuộc lớp SQLState `23` đều là lỗi trùng khóa: lớp này còn bao gồm các vi phạm khóa ngoại, `NOT NULL`, `CHECK` và nhiều ràng buộc khác.

## 3. Cấu trúc SQLState: đọc từ lớp lỗi đến mã cụ thể

Một SQLState theo quy ước tiêu chuẩn SQL có năm ký tự, thường chia thành:

```text
   23 505
   │  └── 3 ký tự cuối: phân loại cụ thể trong lớp
   └───── 2 ký tự đầu: lớp lỗi (class)
```

Một số lớp thường gặp khi làm việc với JDBC:

| Hai ký tự đầu | Lớp SQLState | Ví dụ tình huống | Hướng xem xét ban đầu |
|---|---|---|---|
| `08` | Connection exception | Kết nối bị ngắt, không thiết lập được kết nối | Kiểm tra mạng, máy chủ, pool kết nối; xem giao dịch đã thực thi đến đâu |
| `22` | Data exception | Dữ liệu vượt giới hạn hoặc không thể chuyển đổi kiểu | Kiểm tra giá trị truyền vào và kiểu/giới hạn cột |
| `23` | Integrity constraint violation | Trùng khóa, vi phạm khóa ngoại hoặc ràng buộc | Kiểm tra quy tắc toàn vẹn và dữ liệu liên quan |
| `28` | Invalid authorization specification | Thông tin xác thực/quyền truy cập không hợp lệ | Kiểm tra thông tin kết nối và cấu hình xác thực |
| `40` | Transaction rollback | Deadlock hoặc lỗi khiến giao dịch phải rollback | Xem nguyên nhân rollback và khả năng chạy lại toàn bộ giao dịch |
| `42` | Syntax error or access rule violation | Câu SQL sai cú pháp hoặc vi phạm quy tắc truy cập | Kiểm tra SQL, đối tượng/schema và quyền truy cập |

Mã đầy đủ có thể cho biết chi tiết hơn. Chẳng hạn, **`23505`** là mã thường dùng trong PostgreSQL để biểu diễn vi phạm tính duy nhất. Nhưng một loại lỗi tương tự trên hệ quản trị khác có thể dùng mã SQLState năm ký tự khác, dù vẫn thuộc lớp `23`.

Một số driver còn trả SQLState thuộc các quy ước mở rộng, chẳng hạn `HY000` (general error trong hệ mã kiểu ODBC). Vì vậy, không được ngầm hiểu rằng mọi SQLState đều thuộc đúng các mã chi tiết tiêu chuẩn hoặc luôn đủ thông tin để xác định nguyên nhân.

Khi cần đọc nhóm lỗi bằng mã:

```java
String state = exception.getSQLState();

if (state != null && state.length() >= 2) {
    String errorClass = state.substring(0, 2);

    switch (errorClass) {
        case "08":
            System.err.println("Nhóm lỗi kết nối");
            break;
        case "23":
            System.err.println("Nhóm vi phạm ràng buộc dữ liệu");
            break;
        case "40":
            System.err.println("Nhóm lỗi rollback giao dịch");
            break;
        default:
            System.err.println("Nhóm SQLState: " + errorClass);
    }
} else {
    System.err.println("Driver không cung cấp SQLState có thể phân loại.");
}
```

Trong đoạn mã trên, `exception` là một `SQLException` vừa được bắt. Phân loại theo **hai ký tự đầu** giúp định hướng kiểm tra; hành động cụ thể vẫn cần dựa trên mã chi tiết, ngữ cảnh câu lệnh, giao dịch và tài liệu của nhà cung cấp.

## 4. Ví dụ đầy đủ: bắt lỗi khi thực thi lệnh SQL

Giả sử có bảng `customers` với cột `id` là khóa chính và cột `full_name`. Chương trình dưới đây sử dụng `DataSource` đã được cấu hình bên ngoài để chèn một khách hàng và in dữ liệu chẩn đoán khi JDBC ném lỗi:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insert(long id, String fullName) throws SQLException {
        String sql = "INSERT INTO customers (id, full_name) VALUES (?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, id);
            statement.setString(2, fullName);
            statement.executeUpdate();

        } catch (SQLException exception) {
            logSqlExceptionChain(exception);
            throw exception; // Bảo toàn lỗi để tầng gọi xử lý tiếp.
        }
    }

    private static void logSqlExceptionChain(SQLException exception) {
        int index = 1;

        for (SQLException current = exception;
             current != null;
             current = current.getNextException()) {

            System.err.printf(
                "JDBC error #%d: message=%s, SQLState=%s, vendorCode=%d%n",
                index++,
                current.getMessage(),
                current.getSQLState(),
                current.getErrorCode()
            );
        }
    }
}
```

Luồng xử lý quan trọng ở đây là: lệnh `executeUpdate()` có thể ném `SQLException`; khối `catch` đọc thông tin lỗi; sau đó `throw exception` chuyển nguyên ngoại lệ lên tầng ứng dụng để quyết định trả thông báo, rollback hay báo lỗi. Khối `try-with-resources` vẫn đóng `PreparedStatement` và `Connection` khi thoát.

Trong ví dụ học tập, lỗi được in bằng `System.err`. Trong ứng dụng thực tế, nên sử dụng hệ thống logging có cấu trúc và **kiểm soát việc ghi message**: thông báo của cơ sở dữ liệu có thể chứa tên bảng, câu SQL hoặc dữ liệu đầu vào. Không đẩy trực tiếp thông tin nhạy cảm vào log hay phản hồi HTTP cho người dùng cuối.

Nếu `getSQLState()` trả về `null` hoặc `getErrorCode()` trả `0`, **vẫn cần giữ message, nguyên ngoại lệ và ngữ cảnh thao tác**. Không tự gán một SQLState hay mã vendor giả chỉ để phục vụ phân loại.

## 5. Một lần thất bại có thể chứa nhiều `SQLException`

`SQLException` cung cấp `getNextException()` để liên kết các ngoại lệ SQL tiếp theo. Một trình điều khiển có thể dùng chuỗi này khi cần báo nhiều chi tiết, đặc biệt trong các thao tác như batch hoặc khi nhận nhiều lỗi từ cơ sở dữ liệu.

```text
SQLException ban đầu
  ├── getMessage() / getSQLState() / getErrorCode()
  │
  └── getNextException()
          ├── SQLException tiếp theo
          │      └── getNextException()
          └── ...
```

Chỉ đọc ngoại lệ đầu tiên có thể bỏ qua những thông tin quan trọng do driver kèm theo. Có thể lần theo chuỗi:

```java
try {
    statement.executeUpdate();
} catch (SQLException exception) {
    for (SQLException current = exception;
         current != null;
         current = current.getNextException()) {

        System.err.println("SQLState: " + current.getSQLState());
        System.err.println("Vendor code: " + current.getErrorCode());
        System.err.println("Message: " + current.getMessage());
    }
    throw exception;
}
```

`getNextException()` **khác** với `getCause()`:

| Cơ chế | Mục đích |
|---|---|
| `getNextException()` | Đi đến ngoại lệ SQL tiếp theo do driver xâu chuỗi |
| `getCause()` | Tìm nguyên nhân (*cause*) chung của ngoại lệ Java, ví dụ lỗi mạng hoặc lỗi I/O |
| `getSuppressed()` | Đọc ngoại lệ phụ bị giữ lại, chẳng hạn lỗi phát sinh khi đóng tài nguyên bằng `try-with-resources` |

Khi điều tra sự cố phức tạp, nên giữ nguyên đối tượng ngoại lệ hoặc stack trace để không mất các quan hệ này. Không được coi chuỗi `nextException` và chuỗi `cause` là một.

## 6. Cảnh báo `SQLWarning`: cũng có message, SQLState và vendor code

Ngoài lỗi khiến thao tác thất bại, JDBC có **`java.sql.SQLWarning`**, lớp kế thừa `SQLException`, dùng để cung cấp cảnh báo về cơ sở dữ liệu hoặc thao tác JDBC. Cảnh báo **thường không được ném như lỗi thông thường**; chương trình lấy qua `getWarnings()` của `Connection`, `Statement`/`PreparedStatement`, hoặc `ResultSet` khi thích hợp.

Ví dụ đọc chuỗi cảnh báo của một statement sau khi lệnh thực thi thành công:

```java
import java.sql.PreparedStatement;
import java.sql.SQLWarning;

try (PreparedStatement statement = connection.prepareStatement(
        "UPDATE customers SET full_name = ? WHERE id = ?")) {

    statement.setString(1, "Minh");
    statement.setLong(2, 101L);
    statement.executeUpdate();

    SQLWarning warning = statement.getWarnings();
    while (warning != null) {
        System.out.println("Warning message: " + warning.getMessage());
        System.out.println("Warning SQLState: " + warning.getSQLState());
        System.out.println("Warning vendor code: " + warning.getErrorCode());
        warning = warning.getNextWarning();
    }
}
```

`getNextWarning()` duyệt chuỗi cảnh báo tương ứng, khác với việc bắt `SQLException` bằng `catch`. Khi cần đọc cảnh báo từ một `ResultSet` hoặc `Connection`, cũng dùng `getWarnings()` trên **đúng đối tượng đã phát sinh cảnh báo**.

Một số lưu ý vận hành:

- Cảnh báo có thể tồn tại dù lệnh đã trả kết quả thành công; không nên mặc định “không ném exception” tức là “không có vấn đề nào được báo”.
- Cảnh báo có thể bị xóa khi đối tượng thực hiện thao tác mới theo hợp đồng JDBC. Vì thế, hãy đọc ngay khi cần, trước khi sử dụng tiếp đối tượng.
- Có thể gọi `clearWarnings()` trên đối tượng thích hợp nếu muốn xóa cảnh báo đã ghi nhận; việc xóa này không khắc phục nguyên nhân cảnh báo.
- Không phải thao tác hay driver nào cũng sinh cảnh báo. `getWarnings()` trả về `null` khi không có cảnh báo đang được ghi nhận.

## 7. Dùng thông tin chẩn đoán để quyết định hướng xử lý

Ví dụ sau minh họa cách phân tích một số trường hợp phổ biến mà không gắn cứng toàn bộ quyết định vào câu chữ message:

| Quan sát | Có thể nghĩ đến | Điều cần xác minh tiếp |
|---|---|---|
| SQLState bắt đầu bằng `08` | Trục trặc kết nối | Mạng, database server, trạng thái transaction và việc lệnh có thể đã được thực thi hay chưa |
| SQLState bắt đầu bằng `23` | Vi phạm tính toàn vẹn | Khóa duy nhất, khóa ngoại, `NOT NULL`, `CHECK`; tra mã chi tiết của driver |
| SQLState bắt đầu bằng `40` | Giao dịch đã bị rollback/cần rollback | Loại tranh chấp, mức isolation, khả năng chạy lại toàn bộ transaction |
| SQLState bắt đầu bằng `42` | SQL sai cú pháp hoặc quy tắc truy cập không hợp lệ | Câu SQL, schema, tên bảng/cột và quyền truy cập |
| SQLState là `null`, mã vendor bằng `0` | Chưa đủ mã máy đọc được để phân loại | Message đã được xử lý an toàn, nguyên ngoại lệ, logs và tài liệu driver |

Phân loại SQLState chỉ là **bước định hướng**. Chẳng hạn, một lỗi nhóm `23` chưa đủ kết luận đó là “khách hàng đã tồn tại”; phải xét mã chi tiết và ràng buộc thực tế. Một lỗi nhóm `08` cũng không có nghĩa luôn an toàn khi gửi lại ngay câu lệnh ghi dữ liệu, vì có thể chưa biết giao dịch đã được máy chủ thực hiện tới đâu.

Tương tự, nếu lỗi nhóm `40` xuất hiện trong một giao dịch nhiều câu lệnh, chỉ cân nhắc chạy lại **toàn bộ giao dịch** sau khi xác định nguyên nhân và đảm bảo thao tác đủ an toàn để lặp. Không thực hiện retry vô hạn hoặc retry đơn lẻ một câu lệnh khi trạng thái giao dịch chưa rõ.

JDBC còn định nghĩa một số lớp ngoại lệ có ý nghĩa phân loại, như `SQLTransientException`, `SQLNonTransientException`, `SQLRecoverableException`, `SQLTimeoutException` hoặc `SQLIntegrityConstraintViolationException`. Những kiểu này có thể hỗ trợ xử lý, nhưng không phải mọi driver đều ánh xạ mọi tình huống theo cùng cách. Khi xây dựng cơ chế xử lý lỗi, hãy xem xét **kiểu ngoại lệ, SQLState, vendor code và ngữ cảnh giao dịch** cùng nhau.

## 8. Những lỗi thường gặp khi đọc thông tin lỗi

| Cách làm dễ sai | Vì sao sai? | Cách làm phù hợp |
|---|---|---|
| Phân tích message bằng `contains("duplicate")` để quyết định lỗi nghiệp vụ | Câu chữ phụ thuộc driver/ngôn ngữ/phiên bản | Phân loại bằng SQLState, mã vendor và ràng buộc của DB đang dùng |
| Dùng `getErrorCode()` như mã lỗi chung cho mọi hệ quản trị | Cùng số có thể mang nghĩa khác ở hệ quản trị khác | Xác định tên và phiên bản hệ quản trị/driver trước khi tra mã |
| Xem mọi SQLState `23xxx` là trùng khóa | Lớp `23` gồm nhiều vi phạm khác nhau | Kiểm tra mã chi tiết và constraint liên quan |
| Giả định SQLState luôn có năm ký tự khác `null` | Driver có thể thiếu thông tin mã hóa lỗi | Kiểm tra `null` và độ dài trước khi lấy tiền tố |
| Chỉ in ngoại lệ đầu tiên | Có thể bỏ sót chuỗi `getNextException()` | Duyệt chuỗi khi cần chẩn đoán đầy đủ |
| Bắt lỗi rồi chỉ in log, không ném lại | Tầng gọi có thể tưởng thao tác thành công | Chủ động quyết định cách phản hồi; ném lại hoặc chuyển thành lỗi nghiệp vụ có nguyên nhân |
| Ghi nguyên message và tham số SQL vào log công khai | Có thể lộ cấu trúc database hoặc dữ liệu nhạy cảm | Áp dụng phân quyền, lọc dữ liệu và logging có cấu trúc |

## 9. Bài tập đọc và diễn giải lỗi

Giả sử ứng dụng nhận được thông tin:

```text
Message     : duplicate key value violates unique constraint "customers_pkey"
SQLState    : 23505
Vendor code : 0
```

Hãy xác định điều có thể kết luận và điều chưa thể kết luận:

1. **Có thể kết luận:** SQLState bắt đầu bằng `23`, liên quan đến vi phạm ràng buộc toàn vẹn; mã chi tiết `23505` cùng message chỉ ra vi phạm tính duy nhất trong ngữ cảnh PostgreSQL.
2. **Không thể kết luận:** mã vendor `0` có thể được dùng để nhận diện cùng lỗi trên mọi hệ quản trị. `0` ở đây không cung cấp mã vendor cụ thể có thể dùng để phân biệt loại lỗi.
3. **Cần làm tiếp:** xác nhận bảng/constraint liên quan, xem dữ liệu nghiệp vụ và quyết định trả phản hồi rõ ràng; không để thông báo lỗi cơ sở dữ liệu thô xuất hiện trước người dùng.

Nếu thay lỗi trên bằng SQLState `40001`, cần chuyển sang hướng điều tra rollback/serialization conflict; điều đó **không tự động cho phép retry**. Quyết định chạy lại phải xét phạm vi giao dịch và tác động có thể lặp.

**Ghi nhớ:** Với lỗi và cảnh báo trong JDBC, hãy đọc `getMessage()` để hiểu mô tả, `getSQLState()` để xác định nhóm, và `getErrorCode()` để tra cứu trong **đúng** hệ quản trị/driver. Kiểm tra cả chuỗi `getNextException()` hoặc `getNextWarning()` khi cần; giữ nguyên ngoại lệ và xử lý thông tin log cẩn trọng để có thể điều tra mà vẫn bảo vệ dữ liệu.
