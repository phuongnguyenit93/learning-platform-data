# JDBC: Phân biệt đóng tài nguyên với commit hoặc rollback giao dịch

## 1. Ba thao tác phục vụ ba mục đích khác nhau

Trong JDBC, **đóng tài nguyên** là giải phóng những đối tượng dùng để truy cập cơ sở dữ liệu; **commit** là chấp nhận các thay đổi của một giao dịch; **rollback** là hủy các thay đổi chưa được commit của giao dịch đó. Chúng liên quan trong vòng đời một thao tác dữ liệu nhưng **không thể dùng thay thế cho nhau**.

- **Đóng tài nguyên**: gọi **ResultSet.close()**, **Statement.close()**, **PreparedStatement.close()** hoặc **Connection.close()** (thường tự động bằng **try-with-resources**) để giải phóng cursor, statement, kết nối hoặc trả kết nối về pool.
- **Commit**: gọi **Connection.commit()** khi **autoCommit=false**, xác nhận giao dịch thành công và làm các thay đổi thuộc giao dịch đó có hiệu lực bền vững theo bảo đảm của database.
- **Rollback**: gọi **Connection.rollback()** khi **autoCommit=false**, hoàn tác các thay đổi thuộc giao dịch hiện tại chưa commit; không hoàn tác các giao dịch đã commit trước đó.

| Thao tác | Giải quyết vấn đề gì? | Có kết thúc giao dịch thủ công đang mở không? | Tài nguyên JDBC có tự đóng không? |
| --- | --- | --- | --- |
| **ResultSet.close()** | Giải phóng kết quả/cursor | Không quyết định commit hay rollback | Đóng ResultSet, không mặc định đóng Connection |
| **Statement.close()** / **PreparedStatement.close()** | Giải phóng statement và ResultSet hiện tại của statement | Không quyết định commit hay rollback | Đóng statement, không mặc định đóng Connection |
| **Connection.commit()** | Xác nhận giao dịch hiện tại | Có: commit | Không; Connection vẫn có thể dùng tiếp |
| **Connection.rollback()** | Hủy các thay đổi chưa commit | Có: rollback | Không; Connection vẫn có thể dùng tiếp |
| **Connection.close()** | Giải phóng logical connection và tài nguyên liên quan | **Không bảo đảm một kết quả giao dịch cụ thể** nếu còn giao dịch đang mở | Có, đối với connection mà ứng dụng đang nắm giữ |

**Quy tắc cốt lõi:** Trong giao dịch thủ công, **quyết định commit hoặc rollback trước; sau đó đóng tài nguyên**, kể cả khi mã dùng try-with-resources. Đóng connection khi còn giao dịch hoạt động có kết quả **phụ thuộc cách triển khai** theo đặc tả JDBC, vì vậy không được viết logic dựa trên giả định “đóng là rollback” hoặc “đóng là commit”.

## 2. Auto-commit quyết định khi nào cần commit/rollback tường minh

### Auto-commit bật (mặc định với kết nối JDBC mới)

- Theo giao diện JDBC, kết nối mới mặc định có **autoCommit=true**; kiểm tra thực tế bằng **connection.getAutoCommit()**.
- Mỗi SQL statement được xử lý như một giao dịch riêng và tự commit **khi statement hoàn tất**. Với INSERT/UPDATE/DELETE thông thường, thời điểm đó thường là khi việc thực thi hoàn thành.
- Với **SELECT**, một statement được xem là hoàn tất khi ResultSet gắn với nó được đóng; statement có nhiều kết quả chỉ hoàn tất sau khi tiêu thụ/đóng đầy đủ các kết quả liên quan. Vì thế, đóng ResultSet **có thể gián tiếp cho phép auto-commit xảy ra**, nhưng điều này **không biến ResultSet.close() thành lệnh commit**.
- **Connection.commit()** và **Connection.rollback()** dùng cho chế độ thủ công; gọi khi auto-commit đang bật có thể ném **SQLException** theo hợp đồng JDBC. Không gọi chúng “cho chắc” sau mỗi statement đã auto-commit.
- Nếu cần hai hoặc nhiều câu SQL cùng thành công/thất bại như một đơn vị, auto-commit mặc định thường không đủ.

### Auto-commit tắt (giao dịch thủ công)

Gọi **connection.setAutoCommit(false)** trước các thao tác cần gom nhóm. Những câu SQL thuộc cùng kết nối sẽ tham gia giao dịch cho đến khi gọi **commit()** hoặc **rollback()**. Sau một lần commit/rollback, connection vẫn mở và tiếp tục dùng được; các câu lệnh tiếp theo có thể tham gia giao dịch tiếp theo. Việc đóng ResultSet/Statement ở giữa **không quyết định kết quả** giao dịch.

~~~java
connection.setAutoCommit(false);
try {
    // Thực hiện các câu SQL liên quan trên CHÍNH connection này.
    connection.commit();   // Chỉ sau khi các thao tác đều thành công.
} catch (SQLException | RuntimeException error) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        error.addSuppressed(rollbackError);
    }
    throw error;
}
// Connection chưa tự đóng; cần try-with-resources ở phạm vi ngoài.
~~~

Đoạn trên là **mẫu minh họa trong một phương thức đã có biến connection**, không phải chương trình độc lập. Nó cho thấy trách nhiệm ra quyết định giao dịch; ví dụ hoàn chỉnh có thể chạy ở phần 5.

**Lưu ý nguy hiểm:** Khi chuyển **autoCommit=false** sang **true** trong lúc giao dịch đang hoạt động, đặc tả JDBC quy định việc **thay đổi chế độ sẽ commit giao dịch đó**. Do đó, không dùng **setAutoCommit(true)** như cách “kết thúc/thu hồi an toàn”. Hãy commit/rollback tường minh trước khi khôi phục cấu hình; nếu sử dụng pool, tuân theo cách quản lý trạng thái kết nối của pool hoặc framework.

## 3. Try-with-resources đóng tài nguyên nhưng không điều khiển giao dịch

**Connection**, **Statement**, **PreparedStatement** và **ResultSet** đều dùng được với **try-with-resources** vì hỗ trợ **AutoCloseable**. Khi thoát khỏi khối (bình thường, return hoặc do exception), Java gọi **close()** cho những tài nguyên đã mở thành công, theo **thứ tự ngược với khai báo**.

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement("SELECT id FROM account WHERE id = ?")) {
    statement.setInt(1, 1);
    try (ResultSet results = statement.executeQuery()) {
        while (results.next()) {
            System.out.println(results.getInt("id"));
        }
    } // Đóng ResultSet.
} // Đóng PreparedStatement, rồi Connection.
~~~

Đây là **đoạn minh họa**, cần có **DataSource dataSource** và bảng tương ứng. Nó quản lý tài nguyên đúng cách; nếu **connection.setAutoCommit(false)** đã được gọi và có cập nhật dữ liệu, đoạn mã **không hề nêu quyết định commit/rollback**. Thiết kế giao dịch thủ công phải bổ sung quyết định rõ ràng trước khi kết nối rời khối.

Khi lỗi trong thân khối và **close()** cũng lỗi, Java giữ lỗi trong thân khối là lỗi chính, còn lỗi khi đóng thường nằm trong **Throwable.getSuppressed()**. Vì vậy, try-with-resources giúp tránh rò rỉ tài nguyên nhưng không phải cơ chế khôi phục giao dịch. **Commit/rollback có thể thất bại riêng** và cần được theo dõi.

Đóng **Statement** thông thường đóng **ResultSet hiện tại** do nó tạo ra; đóng **Connection** giải phóng tài nguyên của connection. Không nên tiếp tục sử dụng những đối tượng đã đóng hoặc trả về pool. Việc đóng cursor có thể ảnh hưởng đến tài nguyên/khóa do database nắm giữ, nhưng vẫn khác với lệnh commit/rollback.

## 4. Thứ tự xử lý giao dịch đáng tin cậy

1. Lấy **một connection** phù hợp, đặt **autoCommit=false** trước các câu lệnh thuộc giao dịch.
2. Thực thi SQL bằng PreparedStatement; đóng từng ResultSet/Statement khi không còn cần.
3. Nếu **mọi thao tác thành công**, gọi **commit()** đúng một lần tại ranh giới nghiệp vụ.
4. Nếu có **SQLException** hoặc lỗi nghiệp vụ khiến giao dịch phải hủy, gọi **rollback()** khi connection vẫn còn mở; giữ nguyên lỗi gốc và gắn lỗi rollback vào **suppressed exceptions** nếu cần.
5. Đóng connection trong **finally** hoặc try-with-resources. Với kết nối mượn từ pool, thao tác close thường **trả logical connection về pool**, không nhất thiết đóng kết nối vật lý.

~~~text
Mở connection
  └─ setAutoCommit(false)
       ├─ SQL #1 + đóng statement/resultset tương ứng
       ├─ SQL #2 + đóng statement/resultset tương ứng
       ├─ THÀNH CÔNG  → commit()
       └─ THẤT BẠI    → rollback()
  └─ close() / try-with-resources
~~~

Việc **commit()** không tự động đóng connection; **rollback()** cũng vậy. Hai thao tác kết thúc một đơn vị giao dịch và có thể giải phóng các khóa giao dịch theo database, nhưng ứng dụng vẫn phải quản lý vòng đời tài nguyên. Ngược lại, chỉ đóng connection không chứng minh thay đổi đã được commit.

**Với kết nối do caller hoặc framework sở hữu:** Phải tôn trọng chủ sở hữu giao dịch. Một helper chỉ nhận **Connection** từ bên ngoài thường không được tùy tiện commit, rollback, đổi auto-commit hoặc close nó nếu hợp đồng chưa cho phép; hãy để lớp điều phối quyết định ranh giới giao dịch.

## 5. Ví dụ Java 17+ chạy được: nhìn thấy commit và rollback từ kết nối khác

Ví dụ dùng **H2 JDBC** ở chế độ database trong bộ nhớ để không cần máy chủ database. Mọi thao tác trên account đều dùng API **java.sql** chuẩn; H2 chỉ là JDBC driver phục vụ việc chạy thử. Hai connection độc lập giúp thấy rõ “dữ liệu đã thay đổi trong giao dịch” khác “dữ liệu đã được commit”.

Lưu vào tệp **JdbcResourceVsTransaction.java**:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public class JdbcResourceVsTransaction {
    private static final String URL =
            "jdbc:h2:mem:transaction_demo;DB_CLOSE_DELAY=-1";

    public static void main(String[] args) throws SQLException {
        // Tạo dữ liệu gốc ở chế độ auto-commit mặc định.
        try (Connection setup = DriverManager.getConnection(URL);
             Statement statement = setup.createStatement()) {
            statement.executeUpdate(
                    "CREATE TABLE account (id INT PRIMARY KEY, balance INT NOT NULL)");
            statement.executeUpdate(
                    "INSERT INTO account (id, balance) VALUES (1, 100)");
        }

        System.out.println("Ban dau: " + readFromNewConnection());

        try (Connection transaction = DriverManager.getConnection(URL)) {
            transaction.setAutoCommit(false);

            try {
                updateBalance(transaction, 150);
                System.out.println("Trong transaction: " + readBalance(transaction));
                System.out.println(
                        "Ket noi khac truoc commit: " + readFromNewConnection());
                transaction.commit();
            } catch (SQLException | RuntimeException error) {
                rollbackWithSuppressed(transaction, error);
                throw error;
            }

            System.out.println(
                    "Ket noi khac sau commit: " + readFromNewConnection());

            try {
                updateBalance(transaction, 999);
                System.out.println(
                        "Trong transaction truoc rollback: " + readBalance(transaction));
                transaction.rollback();
            } catch (SQLException | RuntimeException error) {
                rollbackWithSuppressed(transaction, error);
                throw error;
            }

            System.out.println(
                    "Ket noi khac sau rollback: " + readFromNewConnection());
        } // Connection tự đóng sau khi giao dịch đã được quyết định.

        System.out.println("Connection da dong");
    }

    private static void updateBalance(Connection connection, int value)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE account SET balance = ? WHERE id = 1")) {
            statement.setInt(1, value);
            if (statement.executeUpdate() != 1) {
                throw new SQLException("Khong tim thay dung mot tai khoan");
            }
        }
    }

    private static int readBalance(Connection connection) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT balance FROM account WHERE id = 1");
             ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                throw new SQLException("Khong tim thay tai khoan");
            }
            return result.getInt(1);
        }
    }

    private static int readFromNewConnection() throws SQLException {
        try (Connection connection = DriverManager.getConnection(URL)) {
            return readBalance(connection);
        }
    }

    private static void rollbackWithSuppressed(
            Connection connection, Exception original) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            original.addSuppressed(rollbackError);
        }
    }
}
~~~

**Chạy thử:** Tải một bản **H2 JDBC JAR** còn được duy trì từ Maven Central và đặt cạnh tệp Java với tên **h2.jar**. Trên Java 17+:

~~~bash
javac JdbcResourceVsTransaction.java
java -cp ".;h2.jar" JdbcResourceVsTransaction
~~~

Dòng **java -cp** trên dành cho **Windows**; trên Linux/macOS thay **.;h2.jar** bằng **.:h2.jar**. Không cần đưa driver vào classpath khi biên dịch vì mã chỉ import **java.sql**; phải đưa H2 vào classpath khi chạy để **DriverManager** tìm được driver.

**Kết quả chuẩn của ví dụ khi chạy với H2 mặc định:**

~~~text
Ban dau: 100
Trong transaction: 150
Ket noi khac truoc commit: 100
Ket noi khac sau commit: 150
Trong transaction truoc rollback: 999
Ket noi khac sau rollback: 150
Connection da dong
~~~

**Giải thích từng thời điểm:**

- Ban đầu **100** đã được insert và tự commit qua kết nối setup.
- Sau UPDATE đầu tiên, **transaction** của chính nó đọc thấy **150**, còn connection mới vẫn thấy giá trị đã commit **100** (H2 mặc định dùng mức cô lập READ COMMITTED).
- Sau **transaction.commit()**, connection khác đọc được **150**. PreparedStatement của UPDATE đã đóng **trước** commit, cho thấy đóng statement không đồng nghĩa commit.
- UPDATE thứ hai thay **150** thành **999** trong giao dịch mới; **rollback()** hủy thay đổi này nên connection khác vẫn thấy **150**.
- Dòng cuối chỉ xác nhận luồng điều khiển đã ra khỏi try-with-resources, **không phải bằng chứng về commit/rollback**.

**Giới hạn của ví dụ:** **DB_CLOSE_DELAY=-1** giữ H2 in-memory database tồn tại trong vòng đời JVM để các connection cùng nhìn thấy dữ liệu; đây là thiết lập thử nghiệm. Hành vi cách ly/khóa và DDL có thể khác với PostgreSQL, MySQL hoặc SQL Server. Không dựa vào việc đóng một connection chưa kết thúc giao dịch để kiểm tra commit/rollback, vì kết quả đó không được JDBC chuẩn hóa.

## 6. Các bẫy thường gặp và cách sửa

| Cách hiểu / cách làm sai | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Thoát try-with-resources là commit” | try-with-resources chỉ gọi close() | Gọi commit() sau khi thành công |
| “Gặp lỗi thì close() chắc chắn rollback” | Kết quả giao dịch đang hoạt động tại close() do driver/database quyết định | Gọi rollback() tường minh khi vẫn còn connection |
| “Đã close PreparedStatement nên dữ liệu được lưu” | Statement đóng chỉ giải phóng tài nguyên; trong autoCommit=false transaction vẫn mở | Commit tại ranh giới nghiệp vụ |
| “Commit xong không cần đóng connection” | Commit kết thúc giao dịch, không giải phóng logical connection | Dùng try-with-resources/finally |
| “Rollback có thể hủy lần commit trước” | Rollback chỉ tác động giao dịch hiện tại, hoặc từ savepoint nếu dùng rollback(savepoint) | Xác định ranh giới giao dịch trước khi gọi |
| “Tắt rồi bật auto-commit là tương đương rollback” | Chuyển từ false sang true trong transaction đang hoạt động có thể commit theo đặc tả | Commit/rollback trước khi đổi chế độ |
| “Hai câu SQL trên hai connection là một transaction” | Transaction JDBC gắn với connection, trừ khi dùng hạ tầng giao dịch phân tán được quản lý riêng | Dùng cùng connection cho một transaction cục bộ |
| “Close một pooled connection là đóng socket/database session” | Nhiều DataSource trả logical connection về pool và reset trạng thái | Theo hợp đồng pool/framework, kết thúc giao dịch rõ ràng trước close |
| “SQLException ở commit nghĩa là chắc chắn chưa commit” | Lỗi mạng/timeout có thể khiến kết quả commit ở server không xác định | Đối soát trạng thái và dùng idempotency trước khi retry thao tác có tác động |
| “Rollback chắc chắn undo cả CREATE TABLE” | Một số database có DDL tự commit hoặc giao dịch DDL khác nhau | Kiểm tra ngữ nghĩa DDL của hệ quản trị; đừng suy diễn từ DML |

### Savepoint, lỗi close và giao dịch do framework quản lý

- **Savepoint**: với **autoCommit=false**, có thể tạo **Savepoint** rồi gọi **rollback(savepoint)** để hoàn tác **một phần** giao dịch. Phần còn lại vẫn cần commit hoặc rollback toàn bộ; hỗ trợ savepoint tùy driver/database.
- **Lỗi khi đóng**: **close()** có thể ném **SQLException**; Java đưa lỗi đóng vào suppressed nếu khối try đã ném lỗi. Quan sát cả lỗi gốc và lỗi suppressed, nhưng không nhầm lỗi đóng với kết quả giao dịch.
- **Connection pool**: thường reset auto-commit, isolation hoặc rollback khi connection trả về pool, nhưng **không có một hành vi reset duy nhất áp dụng cho mọi pool**. Ứng dụng vẫn cần quyết định giao dịch trước khi trả connection.
- **Spring/JTA hoặc transaction manager**: nếu giao dịch được quản lý bởi framework, framework chịu trách nhiệm commit/rollback theo cấu hình. Trong Spring **@Transactional**, mặc định runtime exception và Error thường gây rollback, checked exception không tự động gây rollback trừ khi cấu hình thêm. Tránh tự gọi JDBC **commit()**, **rollback()** hay **close()** trên kết nối mà transaction manager đang quản lý, trừ khi API/thiết kế cho phép.
- **Thời điểm SELECT hoàn tất trong auto-commit** và quy tắc DDL là các điểm phụ thuộc ngữ nghĩa JDBC/database; bài tập nghiệp vụ gồm nhiều bước nên chủ động dùng giao dịch thủ công.

## 7. Câu hỏi tự kiểm tra

1. **UPDATE thành công; PreparedStatement đã đóng; autoCommit=false; chưa commit. Dữ liệu đã chắc chắn được lưu chưa?** Chưa. Giao dịch vẫn đang chờ quyết định; connection khác thường chưa thấy thay đổi chưa commit theo mức cô lập thông dụng.
2. **Gọi commit() rồi giữ Connection mở có sai không?** Không. Commit kết thúc giao dịch, không đóng tài nguyên; cần đóng connection khi hết nhu cầu dùng.
3. **Lỗi ở SQL thứ hai trong chuỗi hai UPDATE thì làm gì?** Thử rollback trên cùng connection trước khi đóng, bảo toàn lỗi gốc và ghi nhận lỗi rollback nếu phát sinh.
4. **Chỉ gọi Connection.close() khi giao dịch còn mở có thể dự đoán rollback không?** Không. JDBC khuyến nghị commit/rollback trước close, vì kết quả khi còn giao dịch hoạt động là implementation-defined.
5. **Đóng ResultSet có bao giờ liên quan đến auto-commit không?** Có: với chế độ auto-commit, SELECT có thể được coi là hoàn tất khi ResultSet đóng, từ đó statement được tự commit. Đây không phải lệnh commit thủ công.
6. **Nếu rollback() thành công sau một lần commit() trước đó thì dữ liệu đã commit có bị hủy không?** Không; rollback chỉ ảnh hưởng giao dịch hiện tại.

**Ghi nhớ:** **commit()/rollback() quyết định số phận giao dịch; close() quản lý vòng đời tài nguyên**. Với JDBC hiện đại, hãy dùng try-with-resources để đóng an toàn và giao dịch tường minh (hoặc transaction manager) để bảo đảm tính đúng đắn của dữ liệu.

**Tài liệu chuẩn để tra cứu:** [Java SE API — java.sql.Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html), đặc biệt các phương thức **setAutoCommit**, **commit**, **rollback** và **close**.
