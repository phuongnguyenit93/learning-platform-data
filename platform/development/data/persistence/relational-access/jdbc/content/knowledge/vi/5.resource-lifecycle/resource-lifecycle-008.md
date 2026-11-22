# Đọc ngoại lệ bị giữ lại qua getSuppressed trong JDBC

Trong JDBC (*Java Database Connectivity*), mã Java thường mở nhiều tài nguyên theo thứ tự: `Connection`, `PreparedStatement`, rồi `ResultSet`. Tài nguyên phải được đóng dù truy vấn chạy thành công hay thất bại. Tuy nhiên, **chính thao tác đóng tài nguyên cũng có thể ném ngoại lệ**. Nếu một truy vấn đã lỗi mà `close()` cũng lỗi, làm sao giữ được cả hai thông tin để chẩn đoán?

Đó là vai trò của **suppressed exceptions** (ngoại lệ bị giữ lại). Với `try-with-resources`, Java ưu tiên ngoại lệ phát sinh trong quá trình xử lý chính và gắn những ngoại lệ phụ xảy ra khi đóng tài nguyên vào ngoại lệ đó. Phương thức **`Throwable.getSuppressed()`** cho phép đọc lại các ngoại lệ đã được giữ lại.

Bài thuộc chương **Vòng đời tài nguyên**, tập trung vào cách hình thành, đọc và diễn giải chuỗi lỗi này trong ứng dụng JDBC truy cập cơ sở dữ liệu quan hệ. Người học sẽ biết:

- Vì sao Java cần giữ ngoại lệ phát sinh khi `close()`.
- Phân biệt **ngoại lệ chính**, **ngoại lệ bị giữ lại** và **nguyên nhân** (`cause`).
- Dự đoán thứ tự đóng nhiều tài nguyên JDBC và thứ tự ngoại lệ được lưu.
- Đọc `getSuppressed()`, in stack trace và kiểm tra thông tin `SQLException`.
- Sử dụng `addSuppressed()` khi rollback hoặc dọn dẹp thủ công cũng thất bại.
- Phân tích các trường hợp không có suppressed exception mà vẫn xuất hiện lỗi khi đóng.

## 1. Vấn đề: truy vấn lỗi, rồi đóng kết nối cũng lỗi

Giả sử ứng dụng đang đọc đơn hàng:

1. `ResultSet.next()` hoặc một getter phát sinh `SQLException` do mất kết nối.
2. Ứng dụng bắt đầu dọn dẹp `ResultSet`, `PreparedStatement` và `Connection`.
3. Driver báo lỗi thêm trong `ResultSet.close()` hoặc `Connection.close()`.

Trong mẫu `try/finally` viết thiếu cẩn thận, ngoại lệ từ `close()` có thể **thay thế** ngoại lệ gốc đang được truyền ra ngoài:

```java
Connection connection = dataSource.getConnection();
try {
    // Thao tác SQL có thể ném SQLException.
    performQuery(connection);
} finally {
    // Nếu close() cũng ném SQLException,
    // caller có thể chỉ nhận lỗi từ close().
    connection.close();
}
```

Các biến `dataSource` và phương thức `performQuery` trong đoạn rút gọn là thành phần giả định của ứng dụng. Ví dụ thể hiện **rủi ro che mất lỗi chính**, không phải cách khuyến nghị để quản lý JDBC.

Từ Java 7, `try-with-resources` giải quyết trường hợp này bằng quy tắc:

- Nếu phần thân `try` ném ngoại lệ **A**, A là **ngoại lệ chính**.
- Nếu `close()` sau đó ném ngoại lệ **B**, B được **gắn vào A**, không thay A.
- `catch` ở ngoài nhận A và có thể gọi `A.getSuppressed()` để lấy B.

Nhờ vậy, người trực vận hành thấy **nguyên nhân đầu tiên** của thất bại, đồng thời không mất thông tin về việc dọn dẹp tài nguyên gặp vấn đề.

## 2. Cơ chế try-with-resources và getSuppressed()

### 2.1. Đọc ví dụ tối thiểu

Ví dụ sau chạy được bằng Java 17 mà **không cần database**. `FailingResource` mô phỏng một đối tượng JDBC đóng bị lỗi:

```java
import java.sql.SQLException;

public final class SuppressedDemo {
    private static final class FailingResource implements AutoCloseable {
        private final String name;

        FailingResource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws SQLException {
            throw new SQLException("Không đóng được " + name);
        }
    }

    public static void main(String[] args) {
        try (FailingResource connection = new FailingResource("Connection");
             FailingResource statement = new FailingResource("Statement");
             FailingResource result = new FailingResource("ResultSet")) {

            throw new SQLException("Truy vấn thất bại");
        } catch (SQLException primary) {
            System.out.println("Chính: " + primary.getMessage());

            for (Throwable suppressed : primary.getSuppressed()) {
                System.out.println("Giữ lại: " + suppressed.getMessage());
            }
        }
    }
}
```

Kết quả dự kiến:

```text
Chính: Truy vấn thất bại
Giữ lại: Không đóng được ResultSet
Giữ lại: Không đóng được Statement
Giữ lại: Không đóng được Connection
```

Hãy chú ý hai điểm:

1. `primary` vẫn là `SQLException("Truy vấn thất bại")`, **không bị ngoại lệ đóng tài nguyên thay thế**.
2. `getSuppressed()` trả về một mảng `Throwable[]` chứa các ngoại lệ được giữ lại. Các tài nguyên trong `try-with-resources` được đóng **theo thứ tự ngược với khai báo**: `ResultSet → Statement → Connection`.

`getSuppressed()` trả về **mảng rỗng** nếu không có ngoại lệ nào bị giữ lại, không trả `null`. Mỗi phần tử là một `Throwable`; ngoại lệ bị giữ lại có thể là `SQLException`, `IOException`, `RuntimeException` hoặc loại khác tùy tài nguyên.

### 2.2. Nhìn rõ sơ đồ ngoại lệ

```text
try-with-resources
  |
  +-- phần thân try ném SQLException A
  |
  +-- close(ResultSet)       ném SQLException B
  +-- close(Statement)       ném SQLException C
  +-- close(Connection)      ném SQLException D
  |
  v
catch nhận A
  A.getSuppressed() = [B, C, D]
```

Với ứng dụng JDBC thật, một số hoặc tất cả thao tác đóng có thể diễn ra bình thường; khi đó mảng suppressed sẽ có ít phần tử hơn hoặc rỗng. Chỉ sự tồn tại của `try-with-resources` **không có nghĩa** luôn phát sinh suppressed exception.

### 2.3. Thứ tự ưu tiên trong các tình huống khác nhau

| Phần thân `try` | `close()` | Ngoại lệ ra ngoài | `getSuppressed()` |
|---|---|---|---|
| Thành công | Thành công | Không có lỗi | Không áp dụng |
| Thất bại với A | Thành công | A | Mảng rỗng |
| Thành công | Một `close()` thất bại với B | B | Thường rỗng |
| Thất bại với A | `close()` thất bại với B | A | Chứa B |
| Thành công | Nhiều `close()` thất bại B, C | B từ tài nguyên đóng lỗi đầu tiên | Chứa C và các lỗi đóng tiếp theo |
| Thất bại với A | Nhiều `close()` thất bại B, C | A | Chứa B, C theo thứ tự phát sinh |

Khi **thân `try` không ném lỗi**, lỗi đầu tiên phát sinh trong quá trình đóng **trở thành lỗi chính**. Các lỗi đóng tiếp theo sẽ bị giữ lại trên lỗi đó. Vì vậy, không được kết luận “ngoại lệ chính luôn đến từ truy vấn SQL”; đôi khi nó đến từ `close()`.

Một điểm khác: nếu **khởi tạo tài nguyên sau thất bại** (ví dụ `statement.executeQuery()` ném lỗi trong phần khai báo `ResultSet`), Java vẫn đóng những tài nguyên **đã tạo thành công trước đó**. Ngoại lệ khi đóng các tài nguyên trước đó sẽ được giữ lại trên lỗi khởi tạo. Tài nguyên chưa tạo xong không có gì để đóng.

## 3. Cách đọc ngoại lệ bị giữ lại trong JDBC

### 3.1. Một phương thức DAO sử dụng try-with-resources

Ví dụ dưới đây dùng bảng `books(id, title)`. `DataSource` do ứng dụng cấu hình bên ngoài, chẳng hạn từ connection pool. Không cần biết driver cụ thể để hiểu vòng đời tài nguyên:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class BookDao {
    private final DataSource dataSource;

    public BookDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findTitle(long id) throws SQLException {
        String sql = "SELECT title FROM books WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, id);

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.ofNullable(rows.getString("title"));
            }
        }
    }
}
```

Trong phương thức này:

- Nếu `rows.next()` hoặc `getString()` lỗi, Java vẫn cố đóng `rows`, `statement` và `connection`.
- Nếu `rows.close()` cũng lỗi, ngoại lệ đóng được gắn vào ngoại lệ phát sinh từ đọc dữ liệu.
- Nếu có thêm lỗi từ `statement.close()` hoặc `connection.close()`, các lỗi đó cũng được giữ lại.
- Nếu việc mở `connection` không thành công, `Connection` chưa được tạo; không thể có lỗi đóng connection ấy. Nếu mở statement/ResultSet không thành công, các tài nguyên đã mở trước đó vẫn được xử lý.

Ví dụ dùng `Optional.ofNullable` để không giả định cột `title` luôn `NOT NULL`. Nếu cột cho phép SQL `NULL`, cách trả `Optional.empty()` sẽ đồng nhất “không có hàng” và “có hàng nhưng title NULL”; API nghiệp vụ nên thiết kế khác nếu cần phân biệt hai trạng thái.

### 3.2. Ghi nhận ngoại lệ chính và các ngoại lệ suppressed

Ở ranh giới xử lý lỗi, bạn có thể xem toàn bộ thông tin:

```java
try {
    Optional<String> title = bookDao.findTitle(42L);
    System.out.println(title.orElse("(không có tiêu đề)"));
} catch (SQLException primary) {
    System.err.println(
            "SQL chính: " + primary.getMessage()
            + ", SQLState=" + primary.getSQLState()
            + ", vendorCode=" + primary.getErrorCode());

    for (Throwable suppressed : primary.getSuppressed()) {
        System.err.println("Lỗi khi dọn tài nguyên: " + suppressed);

        if (suppressed instanceof SQLException sqlError) {
            System.err.println(
                    "  SQLState=" + sqlError.getSQLState()
                    + ", vendorCode=" + sqlError.getErrorCode());
        }
    }

    primary.printStackTrace(); // Bao gồm stack trace của suppressed.
    throw primary;
}
```

Đây là đoạn mã ở **phương thức gọi**, với biến `bookDao` đã được khởi tạo. `SQLException.getSQLState()` và `getErrorCode()` hỗ trợ phân loại lỗi theo SQLState và mã riêng của nhà cung cấp; không nên dựa hoàn toàn vào thông điệp văn bản vì cách diễn đạt thay đổi theo driver/phiên bản.

Trong ứng dụng thực tế, thay `System.err` bằng logger tập trung và truyền **đối tượng ngoại lệ**:

```java
// Ví dụ với một logging API hỗ trợ ghi kèm Throwable:
logger.error("Không thể đọc sách id={}", bookId, primary);
```

Logger thường in stack trace cùng các suppressed exception khi nhận nguyên `Throwable`. Đừng chỉ log `primary.getMessage()`: thông điệp đơn lẻ bỏ mất stack trace, nguyên nhân và lỗi dọn tài nguyên. Cũng không cần ghi riêng mọi suppressed exception thành nhiều sự kiện trùng lặp nếu logger đã thể hiện đầy đủ cấu trúc lỗi.

**Lưu ý an toàn:** tránh ghi password, token, URL chứa credential hoặc giá trị dữ liệu nhạy cảm vào log. Nếu nội dung ngoại lệ có thể chứa SQL và tham số, phải áp dụng chính sách log phù hợp.

## 4. Phân biệt suppressed, cause và SQLException.getNextException()

Ba cơ chế này phục vụ ba mục đích khác nhau:

| Cơ chế | Lệnh đọc | Quan hệ giữa các ngoại lệ |
|---|---|---|
| **Suppressed exceptions** | `throwable.getSuppressed()` | Lỗi phụ được giữ lại, thường trong lúc đóng tài nguyên hoặc rollback |
| **Cause chain** | `throwable.getCause()` | Ngoại lệ này được gây ra hoặc bọc bởi một ngoại lệ khác |
| **SQL next-exception chain** | `sqlException.getNextException()` | Chuỗi ngoại lệ JDBC bổ sung do driver cung cấp |

Một `SQLException` có thể **đồng thời** có cause, suppressed exceptions và next-exception chain. Không nên mặc định chỉ một trong ba cơ chế xuất hiện.

Ví dụ SQL được thực thi thất bại do một nguyên nhân liên quan đến kết nối. Driver có thể cung cấp:

- `primary.getMessage()`: thông điệp của lỗi SQL chính.
- `primary.getCause()`: ngoại lệ mức thấp hơn, chẳng hạn lỗi kết nối mạng.
- `primary.getSuppressed()`: lỗi bổ sung khi đóng `ResultSet`, statement hoặc connection.
- `primary.getNextException()`: chi tiết bổ sung trong chuỗi `SQLException` mà driver ghi nhận.

Hai cách in thường gặp:

```java
SQLException sqlError = primary;

// Tự đọc riêng ngoại lệ bị giữ lại:
for (Throwable issue : sqlError.getSuppressed()) {
    System.err.println("Suppressed: " + issue);
}

// Tự duyệt SQL next-exception chain:
for (SQLException next = sqlError.getNextException();
     next != null;
     next = next.getNextException()) {
    System.err.println("Next SQLException: " + next.getMessage());
}
```

Đoạn này là minh họa trên `primary` đã bắt được. Trong môi trường có driver tùy biến hoặc cấu trúc ngoại lệ phức tạp, nên dùng logger/công cụ phân tích đã được kiểm thử và giới hạn việc duyệt chuỗi để tránh log lặp hoặc vòng tham chiếu bất thường.

Khi `Throwable.printStackTrace()` in suppressed exceptions, chúng thường xuất hiện với nhãn `Suppressed:` và phần stack trace được rút gọn những khung lặp. `printStackTrace()` cũng hiển thị chuỗi `Caused by:`. Tuy vậy, việc in stack trace theo cơ chế Throwable **không phải là lời bảo đảm mọi trường hợp SQL next-exception chain đều được trình bày theo cách bạn cần**; hãy kiểm tra `getNextException()` nếu driver có thể bổ sung lỗi ở đó.

## 5. addSuppressed(): giữ lỗi rollback mà không che lỗi SQL ban đầu

`try-with-resources` tự gắn ngoại lệ phát sinh từ `close()`. Nhưng nhiều thao tác dọn dẹp trong JDBC diễn ra **không qua `close()`**, đặc biệt là `Connection.rollback()` khi giao dịch thất bại.

Tình huống:

1. Lệnh `UPDATE` thứ hai ném ngoại lệ A.
2. Ứng dụng cố `rollback()` nhưng rollback lại ném ngoại lệ B.
3. Ứng dụng phải báo A là lỗi chính, đồng thời giữ B để người vận hành biết trạng thái phục hồi giao dịch gặp trục trặc.

Dùng `Throwable.addSuppressed(Throwable exception)`:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransactionExample {
    private final DataSource dataSource;

    public TransactionExample(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void runTransaction() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                // Các PreparedStatement của giao dịch phải dùng cùng
                // đối tượng connection, và được đóng đúng cách.
                performUpdates(connection);

                connection.commit();
            } catch (SQLException original) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    original.addSuppressed(rollbackFailure);
                }
                throw original;
            }
        }
    }

    private void performUpdates(Connection connection) throws SQLException {
        // Triển khai các cập nhật nghiệp vụ tại đây.
    }
}
```

Mã tập trung minh họa đường lỗi: `performUpdates` là vị trí để triển khai nghiệp vụ thật. Do `try-with-resources` bao quanh connection, nếu `connection.close()` lỗi sau khi `original` bị ném lại, ngoại lệ đóng sẽ **tiếp tục được gắn vào `original`**. Với connection pool, ứng dụng thực tế còn phải xử lý việc khôi phục trạng thái kết nối (chẳng hạn auto-commit) theo hợp đồng của pool/transaction manager, và bảo đảm lỗi khôi phục không vô tình che lỗi chính. Trong hệ thống dùng Spring hoặc JTA, ưu tiên để transaction manager điều phối giao dịch.

Có thể hình dung một lỗi JDBC có hai nguồn suppressed:

```text
SQLException: UPDATE thất bại                   <-- lỗi chính
  Suppressed: SQLException: ROLLBACK thất bại   <-- thêm thủ công
  Suppressed: SQLException: CLOSE thất bại      <-- try-with-resources thêm
```

Các ngoại lệ đó cung cấp những tín hiệu khác nhau. **Rollback thất bại đặc biệt đáng chú ý** vì có thể không xác định được trạng thái giao dịch ở phía server chỉ từ thông điệp ở client. Không tự động chạy lại các thao tác ghi nếu chưa đánh giá idempotency và kết quả có thể đã được commit.

`addSuppressed()` không tự động thay đổi cause, không ném lại ngoại lệ phụ và không đổi loại của ngoại lệ chính. Không gọi `original.addSuppressed(original)`: Java từ chối tự suppression. Truyền `null` cũng không hợp lệ. Thông thường không cần gọi `addSuppressed()` trong `close()` khi đã dùng đúng `try-with-resources`.

## 6. Các trường hợp dễ hiểu nhầm

### 6.1. Không phải mọi lỗi đều có suppressed exceptions

Nếu SQL lỗi nhưng mọi thao tác đóng thành công:

```text
primary: SQLException "syntax error"
primary.getSuppressed().length == 0
```

Điều này hoàn toàn bình thường. `getSuppressed()` giúp **giữ lỗi phụ nếu có**, không phải thước đo xem `try-with-resources` đã hoạt động hay chưa.

Nếu SQL thành công nhưng `Connection.close()` ném lỗi, lỗi đóng có thể trở thành ngoại lệ chính. Lúc đó `getSuppressed()` có thể rỗng. Đặc biệt với `autoCommit=true`, câu lệnh SQL có thể đã được commit trước khi caller nhận lỗi đóng kết nối; không nên suy luận mọi exception ở cuối phương thức đều nghĩa là thao tác ghi chưa xảy ra.

### 6.2. Có nhiều tài nguyên nhưng thứ tự đóng ngược với thứ tự mở

Với:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql);
     ResultSet result = statement.executeQuery()) {
    // Dùng ResultSet.
}
```

Thứ tự đóng là **`result → statement → connection`**, kể cả khi thân `try` đang ném lỗi. Java đóng những tài nguyên đã được khởi tạo thành công; một lỗi đóng không ngăn việc thử đóng các tài nguyên còn lại theo cơ chế try-with-resources.

Có thể đặt nhiều block `try-with-resources` lồng nhau cho dễ đọc; nguyên tắc giữ ngoại lệ và đóng tài nguyên vẫn áp dụng. Khi phân tích stack trace có nhiều mức lồng, xem `getSuppressed()` trên **đúng đối tượng ngoại lệ chính** được truyền ra ranh giới xử lý.

### 6.3. Nuốt mất ngoại lệ phụ khi tự viết catch/finally

Các mẫu sau làm mất thông tin chẩn đoán:

```java
catch (SQLException failure) {
    throw new RuntimeException(failure.getMessage());
}
```

Đoạn này tạo ngoại lệ mới nhưng **không giữ cause**, khiến suppressed exceptions của lỗi cũ không còn nằm trong cấu trúc exception chain. Thay bằng:

```java
catch (SQLException failure) {
    throw new IllegalStateException("Truy cập cơ sở dữ liệu thất bại", failure);
}
```

Lúc này có thể tìm lại `failure` qua `getCause()`, rồi đọc `failure.getSuppressed()`. Đừng sao chép mảng suppressed sang ngoại lệ mới một cách tùy tiện nếu đã lưu cause, vì có thể tạo thông tin trùng và gây khó đọc.

### 6.4. Suppressed exceptions khác lỗi đã bị “bắt và bỏ qua”

Nếu mã viết:

```java
try {
    connection.close();
} catch (SQLException ignored) {
    // Bỏ qua mà không lưu/ghi lại gì.
}
```

Ngoại lệ `ignored` **không tự động** xuất hiện trong `getSuppressed()` của một exception khác. Cơ chế suppression tự động chỉ áp dụng theo quy tắc của `try-with-resources` (hoặc khi lập trình viên chủ động gọi `addSuppressed()`). Vì thế, đừng nhầm việc “đã catch” với việc “đã được giữ lại”.

### 6.5. Suppression có thể bị tắt trong một số lớp Throwable đặc biệt

`Throwable` có constructor cho phép vô hiệu hóa suppression. Khi suppression bị tắt, `addSuppressed()` không có tác dụng và `getSuppressed()` vẫn trả mảng rỗng. Đây không phải tình huống thường gặp với `SQLException` của JDBC, nhưng giải thích vì sao không nên xem mảng suppressed là nhật ký toàn bộ lỗi từng xảy ra.

Ngoài ra, một driver hoặc thư viện có thể ghi log rồi nuốt lỗi trong phương thức đóng. Một ngoại lệ không được ném ra hoặc không được gắn vào exception khác sẽ không được `getSuppressed()` phát hiện.

## 7. Quy trình chẩn đoán khi nhận SQLException

Khi một tác vụ JDBC thất bại và log chứa nhiều ngoại lệ, hãy thực hiện theo thứ tự:

1. **Xác định ngoại lệ chính.** Đọc loại lỗi, thông điệp, `SQLState`, mã vendor và stack trace để biết lỗi xuất hiện khi mở connection, thực thi statement, xử lý kết quả hay đóng tài nguyên.
2. **Đọc `getSuppressed()`.** Nếu có lỗi `close()`, chú ý tài nguyên nào gặp sự cố và điều đó có báo hiệu connection đã hỏng hoặc dọn dẹp không hoàn chỉnh hay không.
3. **Xem `getCause()` và `getNextException()`.** Các cơ chế này có thể chứa chi tiết mạng, driver hoặc nhiều lỗi SQL; không đồng nhất chúng với suppressed exceptions.
4. **Kiểm tra ranh giới transaction.** Có commit trước lỗi hay chưa? Rollback có thất bại không? Có trả connection về pool? Có nguy cơ trạng thái giao dịch chưa rõ?
5. **Đối chiếu log server và driver.** Dùng timestamp, correlation ID, request ID hoặc định danh session nếu có; không cần log bí mật hay dữ liệu cá nhân để làm việc này.
6. **Sửa nguyên nhân có ý nghĩa nghiệp vụ trước.** Lỗi syntax/constraint/timeout khi thao tác SQL thường quan trọng hơn lỗi phụ khi dọn tài nguyên; song lỗi close lặp lại có thể chỉ ra driver, pool hoặc mạng cần xử lý riêng.

Ví dụ log:

```text
java.sql.SQLException: Truy vấn bị hủy do timeout
    ...
    Suppressed: java.sql.SQLException: Lỗi khi đóng ResultSet
        ...
    Suppressed: java.sql.SQLException: Không trả được Connection về pool
        ...
```

Cách đọc đúng: **truy vấn bị timeout là lỗi chính**; việc đóng result set và xử lý connection còn phát sinh thêm lỗi. Không nên ghi nhận ba lỗi này như ba yêu cầu thất bại độc lập, nhưng cũng không được bỏ qua tác động của lỗi connection đến pool.

## 8. Bài tập thực hành có thể chạy không cần database

Dùng lại lớp `SuppressedDemo` ở phần 2 và tự thử:

**Bài tập 1 — Thân try thành công.** Xóa lệnh `throw new SQLException("Truy vấn thất bại")` trong thân `try` và in lỗi trong `catch`. Lỗi nào trở thành lỗi chính? Các lỗi còn lại xuất hiện ở đâu?

*Đáp án định hướng:* `ResultSet.close()` thất bại đầu tiên khi đóng theo thứ tự ngược, nên trở thành lỗi chính; lỗi từ `Statement.close()` và `Connection.close()` trở thành suppressed của lỗi đó.

**Bài tập 2 — Chỉ một tài nguyên lỗi.** Đổi `close()` để chỉ ném lỗi với tài nguyên tên `"Connection"`; các tài nguyên khác đóng thành công. Khi phần thân `try` ném lỗi SQL, mảng suppressed chứa bao nhiêu phần tử?

*Đáp án định hướng:* Một phần tử là lỗi đóng connection.

**Bài tập 3 — SQL lỗi nhưng close không lỗi.** Sửa `close()` thành phương thức không ném ngoại lệ, giữ nguyên lỗi trong thân `try`. `getSuppressed().length` là bao nhiêu?

*Đáp án định hướng:* Bằng 0; lỗi chính vẫn là lỗi truy vấn.

**Bài tập 4 — Rollback thất bại.** Trong ví dụ giao dịch, giả định `performUpdates` ném `SQLException("UPDATE failed")` và `rollback()` ném `SQLException("ROLLBACK failed")`. Giải thích vai trò của `addSuppressed()` và tại sao chỉ ném lỗi rollback sẽ gây khó chẩn đoán.

**Bài tập 5 — Phân biệt các chuỗi lỗi.** Cho một `SQLException` có `cause` là `IOException`, một suppressed exception là lỗi đóng statement và một next exception do driver thêm vào. Hãy nêu API đọc từng loại và lý do không thể thay cả ba bằng `getMessage()`.

### Tự kiểm tra nhanh

| Câu hỏi | Kết luận cần nhớ |
|---|---|
| `getSuppressed()` trả gì? | Mảng `Throwable[]`, có thể rỗng và không trả `null` |
| Khi lỗi SQL và lỗi `close()` cùng xảy ra? | Lỗi SQL thường là chính; lỗi đóng được giữ lại |
| Tài nguyên nào đóng trước? | Tài nguyên được khai báo **sau** đóng **trước** |
| Nếu chỉ `close()` lỗi thì sao? | Lỗi đóng đầu tiên có thể là ngoại lệ chính |
| Lỗi rollback có tự động bị suppressed không? | Không; cần quản lý thủ công, ví dụ `addSuppressed()` |
| `getSuppressed()` có tương đương `getCause()`? | Không; hai quan hệ khác nhau |
| In stack trace có hữu ích không? | Có; `printStackTrace()` hiển thị suppressed và cause theo cấu trúc |
| Có nên chỉ log `getMessage()`? | Không; sẽ mất stack trace và các ngoại lệ phụ |

## 9. Kết luận

`try-with-resources` là cách mặc định nên dùng để đóng `ResultSet`, `Statement` và `Connection` trong JDBC. Khi mã xử lý chính đã lỗi, Java giữ ngoại lệ ấy làm **lỗi chính** và gắn lỗi phát sinh trong `close()` vào `getSuppressed()`; nhiều tài nguyên được đóng theo thứ tự ngược với thứ tự khai báo.

Trong các tình huống dọn dẹp thủ công như `rollback()`, `addSuppressed()` giúp giữ lỗi phụ mà không che lỗi SQL ban đầu. Khi xử lý sự cố, hãy xem đồng thời **ngoại lệ chính**, **suppressed exceptions**, **cause** và khi cần **next SQLException**, rồi kết hợp thông tin transaction/connection pool để đánh giá chính xác tác động của lỗi.

