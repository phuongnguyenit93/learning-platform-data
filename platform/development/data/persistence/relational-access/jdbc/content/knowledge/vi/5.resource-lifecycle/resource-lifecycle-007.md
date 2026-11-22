# Xử lý ngoại lệ phát sinh trong lúc đóng tài nguyên

Trong **JDBC (Java Database Connectivity)**, công việc với cơ sở dữ liệu quan hệ không kết thúc ngay khi câu SQL chạy xong. Ứng dụng còn phải giải phóng những tài nguyên đã mở, thường gồm `ResultSet`, `Statement`/`PreparedStatement` và `Connection`. Các thao tác `close()` này **cũng có thể ném `SQLException`**. Nếu xử lý không đúng, ngoại lệ lúc đóng có thể che lấp lỗi SQL ban đầu, bị bỏ qua khiến khó điều tra, hoặc khiến chương trình báo sai trạng thái giao dịch.

Ví dụ, một lệnh `INSERT` thất bại vì vi phạm ràng buộc, rồi `Connection.close()` lại thất bại do sự cố mạng. Nhà phát triển cần biết **cả hai vấn đề**, nhưng thường phải ưu tiên giữ nguyên **lỗi `INSERT`** vì đó là nguyên nhân trực tiếp khiến công việc không hoàn thành.

Bài này thuộc chương **Vòng đời tài nguyên**, tập trung vào cách xử lý lỗi khi đóng tài nguyên JDBC, cơ chế **try-with-resources**, ngoại lệ **suppressed**, thứ tự đóng và những điểm cần chú ý khi kết hợp `rollback()` với việc trả kết nối về pool.

## 1. Tại sao `close()` có thể thất bại?

`ResultSet`, `Statement` và `Connection` là các giao diện JDBC có phương thức `close()` khai báo `throws SQLException`. Tùy DBMS và JDBC driver, thao tác đóng có thể liên quan đến việc hủy con trỏ trên server, giải phóng trạng thái statement, hoàn tất trao đổi giao thức, trả kết nối về pool hoặc xử lý phiên kết nối vật lý.

Một số nguyên nhân có thể gặp:

- **Lỗi mạng hoặc máy chủ:** kết nối mất trong lúc driver gửi hoặc nhận thông điệp liên quan đến việc đóng.
- **Trạng thái tài nguyên hoặc giao dịch không hợp lệ:** driver hoặc hạ tầng quản lý kết nối phát hiện phiên đang ở trạng thái không thể hoàn tất thao tác như mong đợi.
- **Pool không thể thu hồi kết nối an toàn:** lớp bọc connection có thể phát hiện kết nối hỏng hoặc không khôi phục được trạng thái phiên.
- **Driver/DBMS gặp lỗi nội bộ:** việc dọn dẹp con trỏ, statement hoặc kết nối có thể phát sinh `SQLException`.

Không phải mọi lần đóng đều phát sinh trao đổi mạng, và không phải mọi driver đóng tài nguyên theo cùng cách. **Hợp đồng API cho phép `close()` báo lỗi**, nên mã ứng dụng cần có đường xử lý dù việc đóng thường thành công.

### Những tài nguyên nào cần được đóng?

| Tài nguyên | Ai thường tạo? | Cách đóng | Điều cần nhớ |
|---|---|---|---|
| `Connection` | `DataSource` hoặc `DriverManager` | `connection.close()` | Với pool, thường trả connection logic về pool; không đồng nghĩa luôn đóng socket vật lý. |
| `Statement` | `Connection#createStatement()` | `statement.close()` | Có thể giữ tài nguyên phía driver/DBMS; nên đóng sau khi dùng. |
| `PreparedStatement` | `Connection#prepareStatement(...)` | `statement.close()` | Cũng là một `Statement`; đóng khi hết phạm vi thực thi. |
| `CallableStatement` | `Connection#prepareCall(...)` | `statement.close()` | Có thể gắn với lời gọi stored procedure và tài nguyên liên quan. |
| `ResultSet` | `Statement#executeQuery()` và các API tương tự | `resultSet.close()` | Đóng sau khi đọc xong; không để `ResultSet` sống ngoài scope của statement/connection sở hữu nó. |
| `Blob`, `Clob`, `NClob`, `SQLXML`, `Array` | Driver hoặc DBMS | `free()` theo hợp đồng từng loại | Đây không phải toàn bộ là `AutoCloseable`; `free()` có thể ném `SQLException`, nên cần xử lý riêng. |

Đóng một `Statement` thường đóng cả `ResultSet` hiện tại của nó theo hợp đồng JDBC, nhưng **đóng rõ ràng những tài nguyên mình sở hữu** giúp code dễ hiểu và xử lý lỗi chính xác hơn. Một số tài nguyên được trả ra cho bên gọi có hợp đồng sở hữu khác; không tự đóng tài nguyên của bên ngoài nếu phương thức chỉ đang mượn.

## 2. Hai loại lỗi có thể xảy ra cùng lúc

Giả sử một phương thức đọc dữ liệu:

```text
Mở Connection → Tạo PreparedStatement → Đọc ResultSet → Đóng ResultSet
                                  ↑                              ↑
                           Lỗi khi đọc SQL                  Lỗi khi close()
```

Có ba trường hợp chính:

1. **Thân thao tác thành công, đóng thất bại:** lỗi đóng trở thành lỗi cần báo ra cho bên gọi.
2. **Thân thao tác thất bại, đóng thành công:** lỗi thao tác được truyền ra nguyên vẹn.
3. **Cả thao tác và đóng đều thất bại:** phải giữ lỗi thao tác làm **ngoại lệ chính** và lưu lỗi đóng như **ngoại lệ bổ sung** để không làm mất thông tin.

Java hỗ trợ yêu cầu này bằng cú pháp **`try-with-resources`**, có từ Java 7. Các giao diện tài nguyên JDBC phổ biến như `Connection`, `Statement` và `ResultSet` triển khai `AutoCloseable`; vì vậy chúng có thể được khai báo trực tiếp trong phần tài nguyên của `try`.

## 3. `try-with-resources`: lựa chọn mặc định cho JDBC

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public String findEmail(DataSource dataSource, long customerId)
        throws SQLException {
    String sql = "SELECT email FROM customers WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, customerId);

        try (ResultSet rows = statement.executeQuery()) {
            return rows.next() ? rows.getString("email") : null;
        }
    }
}
```

Đoạn mã giả định `DataSource` đã được cấu hình và bảng `customers` tồn tại. Ngay cả khi `rows.next()` hoặc `rows.getString(...)` ném `SQLException`, Java vẫn cố gọi `close()` cho các tài nguyên đã khởi tạo thành công.

Khi thân `try` và `close()` cùng ném lỗi, Java xử lý theo quy tắc:

- **Giữ ngoại lệ từ thân `try` làm ngoại lệ chính**.
- **Gắn ngoại lệ phát sinh trong `close()` vào ngoại lệ chính** bằng cơ chế `Throwable.addSuppressed(...)`.
- **Đóng các tài nguyên theo thứ tự ngược với thứ tự khai báo**, kể cả khi một thao tác đóng đã thất bại.
- **Nếu không có lỗi từ thân `try`**, lỗi từ `close()` trở thành ngoại lệ chính; lỗi từ các `close()` tiếp theo có thể được gắn vào nó dưới dạng suppressed.

Ví dụ này giúp tránh phải tự viết nhiều khối `finally` và giảm nguy cơ che mất ngoại lệ ban đầu.

### Thứ tự đóng khi nhiều tài nguyên cùng nằm trong `try`

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT id FROM customers");
     ResultSet rows = statement.executeQuery()) {
    while (rows.next()) {
        System.out.println(rows.getLong(1));
    }
}
```

Thứ tự tạo là **`Connection` → `PreparedStatement` → `ResultSet`**. Khi rời khối, Java đóng theo thứ tự **`ResultSet` → `PreparedStatement` → `Connection`**. Nếu `ResultSet.close()` ném lỗi, Java vẫn tiếp tục thử đóng statement và connection.

Điều này quan trọng bởi một tài nguyên cấp cao hơn thường phụ thuộc vào tài nguyên cấp thấp hơn: muốn giải phóng con trỏ của `ResultSet`, connection và statement thường vẫn cần ở trạng thái có thể làm việc.

### Nếu tạo tài nguyên thứ hai bị lỗi?

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement("SELECT 1")) {
    // ...
}
```

Nếu `getConnection()` thành công nhưng `prepareStatement(...)` ném `SQLException`, Java vẫn đóng `connection` đã tạo. Nếu thao tác đóng connection cũng ném lỗi, lỗi đóng được thêm vào ngoại lệ khởi tạo statement. Nếu chính `getConnection()` thất bại trước khi trả về một `Connection`, không có đối tượng connection nào được khai báo thành công trong khối để Java đóng.

## 4. Hiểu ngoại lệ *primary* và *suppressed*

Để thấy rõ cơ chế của Java, hãy xem ví dụ `AutoCloseable` độc lập với DBMS:

```java
public class SuppressedDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws Exception {
            throw new Exception("Không đóng được " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("A");
             Resource second = new Resource("B")) {
            throw new Exception("Lỗi khi thực thi công việc");
        } catch (Exception error) {
            System.out.println("Primary: " + error.getMessage());
            for (Throwable suppressed : error.getSuppressed()) {
                System.out.println("Suppressed: " + suppressed.getMessage());
            }
        }
    }
}
```

Kết quả theo thứ tự:

```text
Primary: Lỗi khi thực thi công việc
Suppressed: Không đóng được B
Suppressed: Không đóng được A
```

`B` được đóng trước vì nó khai báo sau `A`. Khi thân `try` đã ném lỗi, hai lỗi đóng được đính kèm vào lỗi đó. **Ngoại lệ suppressed không phải là `cause`**: `getCause()` trả về nguyên nhân theo chuỗi *causal chain*, còn `getSuppressed()` trả về những ngoại lệ phụ xảy ra trong lúc giải phóng tài nguyên hoặc được thêm tường minh.

| Tình huống | Ngoại lệ được ném ra ngoài | Thông tin bổ sung |
|---|---|---|
| Thân `try` lỗi, không có lỗi đóng | Lỗi từ thân `try` | Không có suppressed do `close()` |
| Thân `try` thành công, `close()` cuối cùng lỗi | Lỗi đóng | Không nhất thiết có suppressed |
| Thân `try` lỗi, hai `close()` cũng lỗi | Lỗi từ thân `try` | Hai lỗi đóng nằm trong `getSuppressed()` |
| Thân `try` thành công, nhiều `close()` lỗi | Lỗi đóng đầu tiên theo thứ tự đóng ngược | Các lỗi đóng tiếp theo được suppressed vào lỗi chính |
| Khởi tạo một tài nguyên lỗi, các tài nguyên đã tạo trước đó cũng không đóng được | Lỗi khởi tạo | Lỗi đóng được suppressed vào lỗi khởi tạo |

### Xem suppressed exceptions trong code JDBC

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT id FROM customers");
     ResultSet rows = statement.executeQuery()) {

    while (rows.next()) {
        System.out.println(rows.getLong(1));
    }
} catch (SQLException primary) {
    System.err.println("JDBC primary: " + primary.getMessage());

    for (Throwable extra : primary.getSuppressed()) {
        System.err.println("JDBC suppressed: " + extra.getMessage());
    }
    throw primary;
}
```

Đây là ví dụ hiển thị để học; trong sản phẩm thật nên dùng hệ thống logging tập trung. Nhiều framework logging khi nhận cả đối tượng `Throwable` sẽ in stack trace và phần suppressed; tuy nhiên điều đó phụ thuộc cấu hình trình ghi log. Nếu cần phân tích sự cố, **đừng chỉ lưu `exception.getMessage()`** rồi bỏ đi đối tượng ngoại lệ hoặc stack trace.

## 5. Vì sao `finally` thủ công dễ che mất lỗi?

Trong code cũ, người ta thường gặp mẫu sau:

```java
Connection connection = dataSource.getConnection();
try {
    executeBusinessSql(connection); // Có thể ném SQLException
} finally {
    connection.close();             // Cũng có thể ném SQLException
}
```

Nếu `executeBusinessSql(...)` ném lỗi và `connection.close()` cũng ném lỗi, exception từ `finally` **có thể thay thế** exception gốc được truyền ra ngoài. Khi đó log chỉ còn lỗi đóng kết nối, còn lỗi truy vấn bị che khuất. Đây là khác biệt quan trọng so với `try-with-resources`.

Một cách khác tưởng như đơn giản cũng có vấn đề:

```java
finally {
    try {
        connection.close();
    } catch (SQLException ignored) {
        // Sai: âm thầm mất tín hiệu lỗi khi giải phóng tài nguyên.
    }
}
```

Việc nuốt lỗi đóng làm người vận hành không biết tài nguyên có được giải phóng an toàn hay không. Chỉ ghi log lỗi đóng rồi bỏ qua lỗi nghiệp vụ gốc cũng có thể làm kết quả xử lý trở nên khó hiểu.

### Trường hợp buộc phải dọn dẹp thủ công

Khi một tài nguyên không triển khai `AutoCloseable`, hoặc cần logic dọn dẹp riêng, hãy chủ động bảo vệ ngoại lệ chính. Ví dụ sau dùng một phương thức `release()` có thể ném `SQLException`:

```java
SQLException primary = null;

try {
    performSqlWork();
} catch (SQLException error) {
    primary = error;
    throw error;
} finally {
    try {
        release();
    } catch (SQLException closeError) {
        if (primary != null) {
            primary.addSuppressed(closeError);
        } else {
            throw closeError;
        }
    }
}
```

Ví dụ chỉ xử lý tình huống `performSqlWork()` ném **`SQLException`** và giả định hai phương thức minh họa đã tồn tại; nếu thân thao tác cũng có thể ném `RuntimeException` hoặc `Error`, cách giữ exception chính phải bao quát các trường hợp ấy. Với tài nguyên JDBC chuẩn, **dùng `try-with-resources` thường đúng và dễ bảo trì hơn** việc tự xây lại toàn bộ cơ chế suppressed.

## 6. Phân biệt lỗi `rollback()` với lỗi `close()`

`rollback()` và `close()` là **hai thao tác có mục đích khác nhau**:

- `rollback()` yêu cầu DBMS hủy công việc chưa được commit trong giao dịch hiện tại.
- `close()` giải phóng hoặc trả connection logic sau khi phần việc đã kết thúc.

Khi dùng giao dịch cục bộ thủ công, một lỗi SQL có thể làm phát sinh **cả lỗi thực thi, lỗi rollback và lỗi close**. Trong nhiều tình huống, nên giữ lỗi thực thi làm ngoại lệ chính, gắn lỗi rollback làm suppressed; Java sẽ tiếp tục quản lý lỗi close qua `try-with-resources`.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public void updatePrice(DataSource dataSource, long productId, int newPrice)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            String sql = "UPDATE products SET price = ? WHERE id = ?";
            try (PreparedStatement statement = connection.prepareStatement(sql)) {
                statement.setInt(1, newPrice);
                statement.setLong(2, productId);
                if (statement.executeUpdate() != 1) {
                    throw new SQLException("Không tìm thấy sản phẩm");
                }
            }

            connection.commit();
        } catch (SQLException | RuntimeException original) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                original.addSuppressed(rollbackError);
            }
            throw original;
        }
    }
}
```

Trong ví dụ, `Connection` thuộc sở hữu của phương thức và được đóng khi khối `try` ngoài kết thúc. Nếu thao tác SQL thất bại, Java cố rollback; rollback thất bại sẽ được thêm vào ngoại lệ gốc. Nếu sau đó `connection.close()` cũng thất bại, lỗi close được `try-with-resources` thêm vào ngoại lệ chính. Ví dụ giả định `DataSource` cấp connection dành cho giao dịch JDBC cục bộ; **không áp dụng nguyên xi trên kết nối đã được transaction manager/JTA điều phối**.

Mẫu minh họa chưa bao gồm mọi nhánh của quản lý giao dịch production, đặc biệt là phục hồi trạng thái của kết nối trước khi trả pool, retry và lỗi khi `commit()`. Khi dùng Spring/JTA, nên giao việc điều phối transaction cho framework và chỉ đóng những tài nguyên mà mình thực sự sở hữu.

### Nếu `commit()` thành công nhưng `close()` thất bại?

Đây là tình huống quan trọng: **lỗi đóng không tự suy ra giao dịch đã rollback**. Nếu ứng dụng đã nhận được xác nhận `commit()` thành công từ DBMS, sau đó `Connection.close()` ném `SQLException`, cần báo lỗi giải phóng kết nối, nhưng không được tự động mô tả mọi thay đổi là chưa được lưu.

Ngược lại, nếu chính `commit()` ném lỗi mạng, có thể **chưa xác định được** DBMS đã commit hay chưa. Đừng tự động chạy lại một thao tác có tác dụng phụ chỉ dựa vào việc thấy `SQLException`; với các nghiệp vụ như thanh toán hoặc tạo đơn hàng, cần cơ chế idempotency, tra cứu trạng thái, hoặc quy trình đối soát.

Để phân biệt hai trường hợp này trong quan sát vận hành, log nên cho biết lỗi xảy ra ở bước **SQL, `commit`, `rollback` hay `close`**, nhưng không đánh đổi việc giữ lại ngoại lệ gốc và các ngoại lệ suppressed.

## 7. Trả kết nối về pool khi phát sinh lỗi đóng

Với connection pool, `close()` trên connection logic thường có nghĩa là **trả quyền sử dụng về pool**. Pool có thể kiểm tra/khôi phục trạng thái phiên, đánh dấu kết nối hỏng và hủy kết nối vật lý nếu cần. Vì vậy:

1. **Ứng dụng vẫn phải gọi `close()`** sau khi sử dụng, kể cả khi đã gặp ngoại lệ SQL.
2. **Không giả định connection còn tái sử dụng được** nếu `close()` ném lỗi; hạ tầng pool có thể đã hủy hoặc đang xử lý nó.
3. **Không gọi lại `close()` vô hạn** hay giữ một reference để cố tái sử dụng sau khi scope đã kết thúc.
4. **Không nuốt thông tin lỗi đóng** khi đang điều tra tình trạng cạn pool, rò rỉ connection hoặc sự cố mạng.
5. **Đừng tự đóng connection vật lý của pool** bằng API driver đặc thù nếu không thuộc trách nhiệm hạ tầng pool.

Cần lưu ý riêng với giao dịch đang mở: JDBC không bảo đảm rằng mọi implementation sẽ tự giải quyết transaction chưa hoàn tất theo một cách giống nhau khi gọi `close()`. Hãy kết thúc transaction bằng `commit()` hoặc `rollback()` theo đúng owner trước khi trả connection; với transaction do framework quản lý, để framework xác định ranh giới này.

### Đóng `ResultSet`/`Statement` trước connection

Khi một `Connection` bị đóng, driver thường làm các tài nguyên liên quan trở nên không sử dụng được. Tuy nhiên, vẫn nên khai báo `try-with-resources` theo **thứ tự tạo tài nguyên** và để Java đóng theo chiều ngược. Điều này bảo toàn cơ hội nhận diện lỗi của từng thao tác dọn dẹp và giúp code rõ ràng với người bảo trì.

## 8. Phân tích `SQLException` đúng cách

Trong JDBC, một `SQLException` cung cấp nhiều thông tin ngoài message:

| API | Ý nghĩa |
|---|---|
| `getMessage()` | Thông điệp do driver hoặc DBMS cung cấp; thường cần thêm ngữ cảnh để hiểu đầy đủ. |
| `getSQLState()` | Mã trạng thái SQL theo quy ước JDBC/DBMS; hữu ích để phân nhóm lỗi. |
| `getErrorCode()` | Mã lỗi riêng do nhà cung cấp DBMS/driver báo. |
| `getNextException()` | Ngoại lệ SQL tiếp theo trong chuỗi JDBC; thường xuất hiện ở các tình huống có nhiều lỗi liên quan. |
| `getCause()` | Nguyên nhân sâu hơn theo chuỗi exception của Java. |
| `getSuppressed()` | Ngoại lệ bổ sung, thường gồm lỗi xảy ra khi `close()` trong `try-with-resources`. |

**`getNextException()` không thay thế `getSuppressed()`**. Hai cơ chế phục vụ những mối liên hệ khác nhau, nên khi điều tra lỗi phức tạp cần kiểm tra cả hai nếu log mặc định chưa hiển thị đầy đủ.

```java
static void report(SQLException error) {
    System.err.printf("JDBC lỗi: %s, SQLState=%s, VendorCode=%d%n",
        error.getMessage(), error.getSQLState(), error.getErrorCode());

    for (Throwable suppressed : error.getSuppressed()) {
        System.err.println("Suppressed: " + suppressed);
    }

    for (SQLException next = error.getNextException();
         next != null; next = next.getNextException()) {
        System.err.println("Next SQLException: " + next);
    }
}
```

Đây là mã minh họa việc đọc metadata lỗi; trong dịch vụ thật, ghi log có cấu trúc và giới hạn dữ liệu được phép đưa vào log. Tránh ghi mật khẩu, JDBC URL chứa credentials, giá trị nhạy cảm hoặc toàn bộ câu SQL đã ghép dữ liệu người dùng. Khi dùng một hệ thống logging đã tự in stack trace/suppressed, không cần lặp lại toàn bộ exception ở nhiều lớp khiến log khó đọc.

## 9. Những lỗi thiết kế thường gặp

| Cách viết hoặc giả định | Hệ quả | Hướng xử lý |
|---|---|---|
| `connection.close()` trực tiếp trong `finally` mà không bảo vệ ngoại lệ gốc | Lỗi close có thể che lỗi SQL trước đó | Ưu tiên `try-with-resources` để giữ primary/suppressed |
| `catch (SQLException ignored)` khi đóng | Mất thông tin rò rỉ tài nguyên hoặc lỗi driver | Giữ/ghi nhận lỗi phù hợp, ưu tiên suppressed khi đã có lỗi chính |
| `return` trong `finally` | Có thể che cả giá trị trả về hoặc ngoại lệ đang truyền ra | Không dùng `return` trong `finally` để điều khiển kết quả JDBC |
| Chỉ đóng `Connection`, để tài nguyên phụ hoạt động đến cuối scope | Khó xác định lúc giải phóng result set/statement | Đóng `ResultSet`, `Statement` khi hết sử dụng, trước connection |
| Gọi `close()` trên connection do caller cấp | Đóng tài nguyên mà phương thức không sở hữu | Chỉ đóng những tài nguyên do phương thức tạo và sở hữu |
| Có lỗi close sau commit rồi tự động retry toàn bộ `INSERT` | Có thể tạo bản ghi trùng hoặc tác dụng phụ lặp | Xác định trạng thái commit; dùng idempotency và đối soát khi cần |
| Xem mọi lỗi trong `SQLException` là lỗi truy vấn SQL | Khó phân biệt lỗi execute, rollback, close | Lưu ngữ cảnh bước thực thi và giữ exception chain |
| Tắt log suppressed vì “chỉ là lỗi cleanup” | Bỏ sót lỗi tài nguyên, mạng và pool | Giữ suppressed trong log của lỗi chính |

### Cần làm gì nếu có nhiều tầng xử lý ngoại lệ?

Repository nên **giữ nguyên hoặc bọc ngoại lệ có `cause` đúng**, service bổ sung ngữ cảnh nghiệp vụ cần thiết, còn lớp API quyết định thông tin nào được trả cho client. Khi bọc exception, đừng làm mất cause hoặc suppressed ở exception gốc; thông thường:

```java
try {
    repositoryOperation();
} catch (SQLException sqlError) {
    throw new DataAccessException("Không đọc được dữ liệu khách hàng", sqlError);
}
```

Ví dụ giả định `DataAccessException` là kiểu runtime exception do ứng dụng định nghĩa với constructor `(String, Throwable)`. Chuỗi `cause` trỏ về `SQLException` gốc, và các suppressed trên lỗi gốc vẫn có thể được tra cứu qua `getCause()`.

## 10. Checklist khi thiết kế API JDBC

Trước khi hoàn thiện một phương thức làm việc với JDBC, hãy kiểm tra:

1. **Ai sở hữu từng tài nguyên?** Phương thức tự mở thì thường tự đóng; connection truyền từ caller cần giữ hợp đồng mượn rõ ràng.
2. **Dùng `try-with-resources` được không?** Với `Connection`, `Statement`, `ResultSet`, gần như luôn có thể áp dụng.
3. **Thứ tự tạo/đóng đã hợp lý chưa?** Khai báo connection trước, statement sau, result set cuối; Java đóng ngược.
4. **Nếu SQL và close đều lỗi, có giữ được lỗi SQL không?** Kiểm tra suppressed exceptions và hành vi logging.
5. **Nếu transaction thủ công bị lỗi, rollback có được thử và ghi nhận thất bại không?** Lỗi rollback bổ sung không được nuốt hoặc che lỗi ban đầu.
6. **Nếu commit thành công rồi close lỗi, code có báo nhầm là rollback không?** Không tự động retry tác vụ có tác dụng phụ.
7. **Nếu dùng pool/framework, việc đóng connection có đúng owner không?** Không tự đóng tài nguyên ngoài hợp đồng.
8. **Nếu lỗi khi mở statement hoặc result set, các tài nguyên đã mở có được thu hồi không?** Dùng cơ chế khởi tạo tài nguyên trong `try-with-resources`.

### Tình huống tự kiểm tra

**Tình huống A:** `executeQuery()` ném `SQLException("query failed")`; sau đó `ResultSet` chưa khởi tạo nhưng `PreparedStatement.close()` cũng lỗi. Ngoại lệ nào cần ưu tiên? → Ngoại lệ từ `executeQuery()` là **primary**; lỗi đóng statement được **suppressed** khi dùng `try-with-resources`. Connection vẫn được thử đóng.

**Tình huống B:** Thân khối JDBC chạy thành công; `ResultSet.close()` và `Connection.close()` cùng thất bại. Java truyền ngoại lệ nào ra ngoài? → Do thứ tự đóng ngược, lỗi từ `ResultSet.close()` thường trở thành **primary**; lỗi `Connection.close()` được suppressed, giả sử các tài nguyên nằm trong cùng thứ tự khai báo và statement được đóng giữa hai bước này.

**Tình huống C:** Câu `UPDATE` thất bại, `rollback()` cũng ném lỗi, rồi `close()` lại lỗi. Nên giữ thông tin thế nào? → Giữ lỗi `UPDATE` làm ngoại lệ chính; thêm lỗi rollback như suppressed; để try-with-resources thêm lỗi đóng connection. Điều này cho phép người vận hành thấy đầy đủ chuỗi sự cố.

**Tình huống D:** `commit()` đã trả về thành công, nhưng `Connection.close()` ném `SQLException`. Có nên báo với người dùng rằng giao dịch bị hủy? → Không. Cần phân biệt lỗi giải phóng kết nối và kết quả commit đã xác nhận; không tự retry thao tác ghi có tác dụng phụ.

**Tình huống E:** Repository được truyền `Connection` do service sở hữu. Repository có nên đưa connection ấy vào danh sách tài nguyên của `try-with-resources` không? → Không, vì khi thoát khối nó sẽ đóng connection của service. Repository chỉ đóng statement/result set do chính nó tạo.

## Ghi nhớ

Trong JDBC, **đóng tài nguyên là một thao tác có thể thất bại**, vì vậy ngoại lệ trong `close()` phải được xử lý với cùng sự cẩn trọng như ngoại lệ khi thực thi SQL. `try-with-resources` giúp tự đóng đúng thứ tự và **giữ lỗi thao tác làm primary, lỗi dọn dẹp làm suppressed** khi cả hai cùng xảy ra. Khi kết hợp với transaction, cần phân biệt `execute`, `commit`, `rollback` và `close` để không che nguyên nhân hoặc báo sai kết quả lưu dữ liệu. Hãy đóng đúng tài nguyên mình sở hữu, giữ ngữ cảnh ngoại lệ đầy đủ và để transaction manager/pool thực hiện phần việc thuộc trách nhiệm của chúng.
