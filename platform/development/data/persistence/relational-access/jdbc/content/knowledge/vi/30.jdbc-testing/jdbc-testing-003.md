# Quản lý dữ liệu mẫu và cô lập giữa các bài kiểm thử JDBC

Một bài kiểm thử truy cập cơ sở dữ liệu có thể chạy đúng khi đứng một mình nhưng thất bại khi chạy cùng toàn bộ test suite. Nguyên nhân thường không nằm ở `PreparedStatement` hay `ResultSet` mà ở **trạng thái cơ sở dữ liệu được chia sẻ**: bài thử trước đã chèn một hàng có cùng khóa, cập nhật dữ liệu mẫu, để lại transaction chưa kết thúc hoặc thay đổi schema. Kết quả là kiểm thử bị phụ thuộc vào thứ tự chạy, khó tái hiện và dễ tạo những lỗi giả (*flaky tests*).

Trong chương **Kiểm thử JDBC**, bài này hướng dẫn xây dựng **test fixture** (dữ liệu nền và dữ liệu riêng cho một ca kiểm thử), lựa chọn chiến lược cô lập, dọn dẹp có kiểm soát và xác minh rằng một bài thử không làm thay đổi kết quả của bài khác. Các ví dụ dùng API JDBC chuẩn: `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`, transaction, `SQLException` và `try-with-resources`. Framework kiểm thử như JUnit có thể hỗ trợ vòng đời test, nhưng **không thay thế quy tắc transaction và khả năng cô lập thật của DBMS**.

Sau bài học, bạn có thể:

- Phân biệt **dữ liệu mẫu cố định**, **dữ liệu được tạo cho từng test** và **dữ liệu do hệ thống đang được kiểm thử sinh ra**.
- Thiết kế các ca kiểm thử **độc lập, lặp lại được, không phụ thuộc thứ tự**.
- Dùng `setAutoCommit(false)` và `rollback()` để cô lập một bài thử khi toàn bộ SQL dùng **cùng `Connection`**.
- Chọn giữa rollback, dọn dữ liệu theo khóa, schema riêng và database riêng theo tình huống.
- Dọn dữ liệu đúng thứ tự quan hệ cha–con, không xóa nhầm dữ liệu của bài khác.
- Kiểm thử xử lý lỗi, transaction, khóa sinh, concurrency và thao tác đa kết nối mà không đưa ra các giả định sai về DB/driver.
- Thiết kế môi trường CI có quyền truy cập hạn chế và tránh dùng cơ sở dữ liệu sản xuất làm nơi chạy thử.

## 1. Một bài kiểm thử JDBC đáng tin cậy cần những gì?

Giả sử phương thức nghiệp vụ `createAccountWithNotes(...)` tạo tài khoản và hai ghi chú. Một ca kiểm thử tốt cần kiểm tra cả **kết quả của phương thức** lẫn **trạng thái dữ liệu** mà JDBC thực sự ghi xuống DB.

Các đặc tính quan trọng:

| Đặc tính | Ý nghĩa trong bài kiểm thử JDBC |
| --- | --- |
| **Có thể lặp lại** | Chạy lần thứ nhất, lần thứ hai hoặc hàng trăm lần vẫn cho kết quả như nhau |
| **Độc lập** | Không cần một test khác chạy trước để tạo dữ liệu và không dựa vào thứ tự test |
| **Cô lập** | Thay đổi của test A không ảnh hưởng dữ liệu mà test B dùng |
| **Có tính đại diện** | Schema, khóa, constraint, kiểu SQL và cơ chế transaction phù hợp hành vi cần kiểm chứng |
| **Có thể chẩn đoán** | Khi thất bại, xác định được dữ liệu ban đầu, SQL/ca nghiệp vụ và điều kiện đã kiểm tra |
| **Có cleanup rõ ràng** | Kể cả khi assertion hoặc SQL ném lỗi, tài nguyên và dữ liệu tạm được xử lý phù hợp |

Một bài kiểm thử chỉ kiểm tra “`executeUpdate()` trả về `1`” có thể bỏ sót việc ghi nhầm hàng, commit ngoài ý muốn hoặc dữ liệu từ test trước vẫn tồn tại. Ngược lại, một test chỉ quan sát bảng cuối cùng mà không xác định dữ liệu đã có sẵn trước đó cũng dễ đưa ra kết luận sai.

### Fixture, baseline và thay đổi của hệ thống

```text
Database test đã tạo schema bằng migration
                 |
                 v
Baseline: các bảng, ràng buộc và dữ liệu tham chiếu ít thay đổi
                 |
            Trước mỗi test
                 |
                 v
Fixture riêng: account_key, note_no, dữ liệu đầu vào đã biết
                 |
                 v
         Chạy repository/service JDBC
                 |
                 v
  Assert kết quả Java + trạng thái dữ liệu DB
                 |
                 v
      Rollback hoặc cleanup theo chiến lược
                 |
                 v
   Trạng thái dành cho test tiếp theo không bị nhiễm
```

**Baseline** có thể là bảng tra cứu trạng thái, mã quốc gia hoặc những ràng buộc schema cần thiết cho mọi test. **Fixture riêng** là dữ liệu cụ thể để thực hiện một ca kiểm thử: ví dụ một tài khoản đang hoạt động với hai ghi chú. **Thay đổi của hệ thống** là dữ liệu do phương thức dưới test tạo hoặc sửa. Phân biệt ba loại này giúp không xóa nhầm dữ liệu nền khi cleanup.

## 2. Lựa chọn dữ liệu mẫu nhỏ, rõ ràng và có khóa riêng

Giả sử cơ sở dữ liệu kiểm thử có hai bảng:

```sql
CREATE TABLE test_account (
    account_key VARCHAR(64) PRIMARY KEY,
    email       VARCHAR(255) NOT NULL UNIQUE,
    status      VARCHAR(20) NOT NULL
);

CREATE TABLE test_note (
    account_key VARCHAR(64) NOT NULL,
    note_no     INTEGER NOT NULL,
    note_text   VARCHAR(200) NOT NULL,
    PRIMARY KEY (account_key, note_no),
    FOREIGN KEY (account_key)
        REFERENCES test_account(account_key)
);
```

DDL mang tính minh họa theo SQL quan hệ thông dụng; cú pháp khóa và constraint cần điều chỉnh theo DBMS cụ thể. **Tạo bảng bằng migration hoặc bước khởi tạo môi trường kiểm thử trước khi test bắt đầu**, không tự chạy `CREATE TABLE` trong từng test khi đang dựa vào rollback để cô lập dữ liệu.

Dữ liệu tối thiểu cho một ca:

```text
test_account
  account_key = "it-<unique-token>"
  email       = "it-<unique-token>@example.invalid"
  status      = "PENDING"

test_note
  (account_key, note_no=1, note_text="Gọi khách vào buổi sáng")
  (account_key, note_no=2, note_text="Xác nhận địa chỉ")
```

Khi test chạy, có thể tạo định danh riêng:

```java
String token = "it-" + java.util.UUID.randomUUID();
String email = token + "@example.invalid";
```

`UUID` giúp giảm nguy cơ va chạm giữa các lượt chạy hoặc giữa hai job CI; nó **không thay thế kiểm tra khóa duy nhất** của DB và không tự tạo cô lập transaction. Nếu bài thử cần so sánh kết quả chính xác, những giá trị **nội dung và quan hệ** vẫn cố định; chỉ định danh kỹ thuật của fixture được tạo riêng cho mỗi lượt.

### Không hardcode khóa dùng chung cho tất cả test

Một anti-pattern:

```sql
INSERT INTO test_account(account_key, email, status)
VALUES ('user-1', 'user-1@example.invalid', 'PENDING');
```

Nếu hai test chạy song song cùng chèn `user-1`, một test có thể gặp lỗi unique constraint hoặc bị chặn do khóa trùng. Nếu test trước thất bại mà chưa dọn hàng, lần chạy tiếp theo lại lỗi ngay tại phần setup.

Có thể dùng khóa cố định **nếu mỗi test có database/schema hoàn toàn riêng hoặc rollback có hiệu lực và không chạy song song tranh chấp cùng khóa**. Ngược lại, tạo định danh theo ca/lượt chạy hoặc tách schema/database là cách an toàn hơn.

### Tập dữ liệu cần đại diện cho tình huống, không nhất thiết lớn

Một fixture hai ghi chú thường đủ để kiểm tra mapping `ResultSet`, tham số SQL, count và foreign key. Tạo 50.000 ghi chú trong mọi test chỉ làm suite chậm hơn, tăng thời gian cleanup và che khuất nguyên nhân lỗi. Hãy tách test chức năng nhỏ khỏi **test hiệu năng/quy mô lớn** có dữ liệu riêng và điều kiện đo rõ ràng.

Không dùng dữ liệu khách hàng thật trong fixture khi không cần thiết. `example.invalid` là miền dùng trong ví dụ, không đại diện cho một địa chỉ email thật.

## 3. Bốn chiến lược cô lập dữ liệu và điều kiện áp dụng

| Chiến lược | Cách vận hành | Phù hợp với | Hạn chế |
| --- | --- | --- | --- |
| **Rollback theo test** | Mở transaction, seed + chạy SUT + assert, sau đó rollback | Repository dùng cùng `Connection` và không tự commit | Không hoàn tác ghi từ kết nối khác hoặc thao tác đã commit riêng |
| **Cleanup theo khóa fixture** | Test tạo dữ liệu có định danh riêng; cuối test xóa theo định danh ấy | SUT tự mở connection/commit hoặc phải kiểm tra dữ liệu đã commit | Cleanup có thể lỗi; phải xóa đúng quan hệ FK |
| **Schema riêng** | Mỗi suite/job hoặc mỗi test sử dụng một schema được tạo riêng | Tăng cách ly khi có nhiều bảng hoặc test chạy song song | Cần quản lý migration, quyền và tên schema an toàn |
| **Database/instance riêng** | Mỗi suite/test dùng database hoặc DB instance tách biệt | Kiểm thử migration, DDL, transaction, cấu hình hoặc cạnh tranh thực | Tốn thời gian và tài nguyên cấp phát/khởi tạo |

Đây là các lựa chọn **bổ sung cho nhau**, không nhất thiết chỉ được chọn một. Ví dụ, CI có thể cấp **một database riêng cho cả test suite**, chạy migration một lần, sau đó dùng **rollback mỗi test** cho các repository và **cleanup theo khóa** cho những test cần quan sát commit.

### Tiêu chí lựa chọn nhanh

- Nếu mọi thao tác test đều dùng **một connection do test sở hữu** và không tự commit: ưu tiên **rollback**.
- Nếu SUT **gọi `DataSource.getConnection()` riêng**, dùng transaction manager khác, chạy job bất đồng bộ hoặc tự commit: rollback ở connection của test **không đủ**; cân nhắc cleanup hoặc database riêng.
- Nếu bài thử cần tạo/xóa bảng, thay đổi index/schema, khởi tạo extension hoặc kiểm tra migration: chọn **schema/database riêng**, vì DDL và transaction khác nhau theo DB.
- Nếu các test chạy **song song** và có cùng dữ liệu tham chiếu có thể sửa: cần tách tài nguyên hoặc áp dụng đồng bộ lịch chạy; UUID của từng fixture không cô lập hàng chung.

Không xem `@Transactional` của một framework kiểm thử là lời bảo đảm tổng quát: nếu code được kiểm thử dùng transaction khác hoặc mở kết nối khác, dữ liệu có thể vẫn commit và để lại dấu vết.

## 4. Transaction rollback: đơn giản nhưng phải đúng ranh giới

Với JDBC, một bài thử có thể mở connection, tắt auto-commit, chèn fixture, chạy câu SQL cần kiểm tra, đối chiếu rồi rollback trong `finally`:

```java
try (Connection connection = testDataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        // Chèn dữ liệu mẫu.
        // Gọi repository/service qua chính connection này.
        // Assert dữ liệu.
    } finally {
        connection.rollback(); // Hoàn tác cả fixture và thay đổi test.
    }
}
```

Điều kiện bắt buộc:

1. **Dùng cùng `Connection`:** mọi `PreparedStatement` và thay đổi cần rollback phải thuộc transaction của connection này.
2. **Không commit giữa chừng:** một phương thức SUT tự gọi `commit()` sẽ làm thay đổi được xác nhận, và rollback cuối test không đảo ngược được.
3. **Bảng/engine phải hỗ trợ transaction:** không phải mọi cơ chế lưu trữ hay thao tác DDL đều có thể rollback giống nhau.
4. **Test vẫn được chạy dù fixture chưa commit:** đọc/ghi từ cùng connection có thể nhìn thấy những thay đổi do transaction của chính nó thực hiện.
5. **Rollback ngay cả khi assertion thất bại:** nếu chỉ gọi rollback sau dòng assert cuối cùng, một exception ở giữa sẽ bỏ qua cleanup.

Với connection pool, `Connection.close()` thường trả logical connection về pool. Dù pool có thể tự reset state, không dựa vào việc đóng kết nối để thay thế rollback khi bài thử cần kiểm soát rõ dữ liệu. Test nên hoàn tất transaction trước khi trả connection.

### Tại sao không mở một connection mới trong repository?

Đoạn sau **không có cùng ranh giới transaction**:

```java
try (Connection testConnection = testDataSource.getConnection()) {
    testConnection.setAutoCommit(false);
    // Seed thông qua testConnection.

    // Repository tự gọi dataSource.getConnection() bên trong:
    service.createRecord(...);

    testConnection.rollback();
}
```

Nếu `service.createRecord` dùng một connection vật lý khác và tự commit, rollback `testConnection` **không** hoàn tác ghi của service. Trong nhiều DB, connection thứ hai còn **không thấy fixture chưa commit** ở connection thứ nhất; test có thể lỗi foreign key hoặc bị chặn khóa. Vì vậy, cần kiểm tra kiến trúc kết nối của code under test trước khi quyết định dùng rollback isolation.

## 5. Ví dụ hoàn chỉnh: repository nhận `Connection` do test sở hữu

Ví dụ này dùng Java 17+ và **chỉ JDBC chuẩn**. Để mục đích cô lập rõ ràng, repository nhận một `Connection` đang mở; nó **không** tự tạo connection và **không** tự `commit`. Tầng gọi hoặc test quyết định transaction.

Tệp minh họa `AccountNoteRepository.java`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;

public final class AccountNoteRepository {
    public void insertAccount(
            Connection connection, String key,
            String email, String status) throws SQLException {

        String sql = """
                INSERT INTO test_account(account_key, email, status)
                VALUES (?, ?, ?)
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, key);
            statement.setString(2, email);
            statement.setString(3, status);
            int count = statement.executeUpdate();
            if (count != 1) {
                throw new SQLException("Expected one inserted account");
            }
        }
    }

    public void insertNote(
            Connection connection, String key,
            int noteNo, String text) throws SQLException {

        String sql = """
                INSERT INTO test_note(account_key, note_no, note_text)
                VALUES (?, ?, ?)
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, key);
            statement.setInt(2, noteNo);
            statement.setString(3, text);
            int count = statement.executeUpdate();
            if (count != 1) {
                throw new SQLException("Expected one inserted note");
            }
        }
    }

    public int updateStatus(
            Connection connection, String key, String newStatus)
            throws SQLException {

        String sql = """
                UPDATE test_account SET status = ?
                WHERE account_key = ?
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, newStatus);
            statement.setString(2, key);
            return statement.executeUpdate();
        }
    }

    public String readStatus(Connection connection, String key)
            throws SQLException {

        String sql = """
                SELECT status FROM test_account WHERE account_key = ?
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, key);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return null; // Không có hàng khớp khóa.
                }
                String value = result.getString(1);
                if (result.next()) {
                    throw new SQLException("Duplicate account key");
                }
                return value;
            }
        }
    }

    public long countNotes(Connection connection, String key)
            throws SQLException {

        String sql = """
                SELECT COUNT(*)
                FROM test_note
                WHERE account_key = ?
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, key);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new SQLException("COUNT returned no row");
                }
                return result.getLong(1);
            }
        }
    }

    public long countAccounts(Connection connection, String key)
            throws SQLException {

        String sql = """
                SELECT COUNT(*)
                FROM test_account
                WHERE account_key = ?
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, key);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new SQLException("COUNT returned no row");
                }
                return result.getLong(1);
            }
        }
    }
}
```

Repository dùng `PreparedStatement` tham số hóa ở mọi câu SQL. Các phương thức đóng statement/result set mà **không đóng `Connection`**, vì connection thuộc tầng gọi. Đây là yếu tố quan trọng để service ghép nhiều thao tác trong một transaction và test có thể rollback tất cả. Ví dụ dùng bảng `test_account`/`test_note` của môi trường kiểm thử; ứng dụng thực tế nên có schema nghiệp vụ tương ứng, không sao chép bảng tên `test_*` sang sản xuất nếu không cần.

## 6. Ví dụ hoàn chỉnh: một ca kiểm thử tự rollback và xác minh không để lại dữ liệu

Tệp `AccountNoteIsolationScenario.java` sau chạy như một scenario JDBC độc lập. Test runner có thể gọi phương thức `run()`; không phụ thuộc thư viện test nào để thực hiện assertion. `DataSource` được môi trường kiểm thử cung cấp, chẳng hạn một pool hoặc DataSource của driver trỏ tới **database dành riêng cho test**.

```java
import java.sql.Connection;
import java.sql.SQLException;
import java.util.Objects;
import java.util.UUID;
import javax.sql.DataSource;

public final class AccountNoteIsolationScenario {
    private final DataSource dataSource;
    private final AccountNoteRepository repository =
            new AccountNoteRepository();

    public AccountNoteIsolationScenario(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public void run() throws SQLException {
        String token = "it-" + UUID.randomUUID();
        String email = token + "@example.invalid";

        // Connection này thuộc ca kiểm thử và chưa được giao cho ai khác.
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            Throwable primaryFailure = null;

            try {
                // Seed fixture riêng cho lần chạy này.
                repository.insertAccount(
                        connection, token, email, "PENDING");
                repository.insertNote(
                        connection, token, 1, "Gọi khách vào buổi sáng");
                repository.insertNote(
                        connection, token, 2, "Xác nhận địa chỉ");

                if (repository.countNotes(connection, token) != 2) {
                    throw new AssertionError("Fixture must have 2 notes");
                }

                // Thao tác JDBC thuộc diện cần kiểm thử.
                int updated = repository.updateStatus(
                        connection, token, "ACTIVE");

                if (updated != 1) {
                    throw new AssertionError("Expected one status change");
                }
                if (!"ACTIVE".equals(
                        repository.readStatus(connection, token))) {
                    throw new AssertionError("Status was not updated");
                }

                // Chưa commit: thành công của assertion không có nghĩa
                // dữ liệu cần được giữ ở DB sau khi test kết thúc.
            } catch (SQLException | RuntimeException | Error failure) {
                primaryFailure = failure;
                throw failure;
            } finally {
                try {
                    // Rollback kể cả khi assert hoặc SQL ở trên thất bại.
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    if (primaryFailure != null) {
                        primaryFailure.addSuppressed(rollbackFailure);
                    } else {
                        throw rollbackFailure;
                    }
                }
            }
        }

        // Kết nối MỚI xác nhận fixture đã bị rollback.
        try (Connection observer = dataSource.getConnection()) {
            if (repository.countAccounts(observer, token) != 0) {
                throw new AssertionError(
                        "Account leaked into the next test");
            }
            if (repository.countNotes(observer, token) != 0) {
                throw new AssertionError(
                        "Notes leaked into the next test");
            }
        }
    }
}
```

Ví dụ gọi trong một test JUnit Jupiter 5 (JUnit là **phụ thuộc kiểm thử bổ sung**, không phải thư viện có sẵn trong Java SE):

```java
import org.junit.jupiter.api.Test;

class AccountNoteRepositoryIT {
    // Được suite cung cấp từ cấu hình test, không dùng DB sản xuất.
    private final javax.sql.DataSource testDataSource =
            TestDatabaseFixture.dataSource();

    @Test
    void updateStatusDoesNotLeakData() throws java.sql.SQLException {
        new AccountNoteIsolationScenario(testDataSource).run();
    }
}
```

`TestDatabaseFixture` là **lớp fixture cần có trong dự án** để cung cấp `DataSource` đã cấu hình đúng; không phải API Java SE hay một thư viện JDBC tự tạo ra. Mã scenario phía trên là phần JDBC độc lập với framework.

### Những điều ví dụ thực sự chứng minh

1. Mọi câu `INSERT`, `SELECT`, `UPDATE` của test đều dùng **cùng `Connection`**.
2. Hai hàng ghi chú tham chiếu tài khoản được thêm trong cùng transaction, bảo đảm test thấy chúng ngay khi query bằng kết nối của chính nó.
3. Tài khoản được đổi `PENDING → ACTIVE`, và kết quả được kiểm tra bằng truy vấn SQL chứ không chỉ qua giá trị trả về của phương thức.
4. `finally` gọi `rollback()` ngay cả khi assertion, SQL hoặc mã Java ném lỗi.
5. Ngoại lệ rollback được gắn vào lỗi gốc qua `addSuppressed`, giúp không mất thông tin lỗi ban đầu.
6. Một kết nối mới được mở **sau rollback** để kiểm tra cả tài khoản và ghi chú đều không còn.
7. Không dùng thứ tự chạy của JUnit, không chia sẻ một khóa cố định và không phụ thuộc hàng mà test khác đã chèn.

Scenario trên giả định DDL đã được khởi tạo, bảng dùng engine hỗ trợ transaction và không có trigger/stored procedure tự commit độc lập. Nếu test mục tiêu là **hành vi commit thật**, rollback-isolation vẫn hữu ích cho những phần khác, nhưng bài thử commit cần dùng một chiến lược cleanup/schema/database thích hợp.

## 7. Dọn dữ liệu theo khóa khi SUT đã commit

Không phải lúc nào cũng có thể dùng rollback của test. Ví dụ SUT mở `Connection` riêng qua `DataSource` và gọi `commit()`; hoặc ứng dụng phát một sự kiện để worker bất đồng bộ ghi dữ liệu sau khi test kết thúc. Khi đó, để kiểm thử trạng thái đã commit, hãy dùng dữ liệu mang **định danh riêng**, rồi cleanup chính các hàng thuộc phạm vi test.

Với hai bảng minh họa, thứ tự dọn thông thường là **con trước, cha sau** để không vi phạm khóa ngoại:

```java
public static void cleanupCommittedFixture(
        DataSource dataSource, String token) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            try (PreparedStatement deleteNotes =
                         connection.prepareStatement(
                                 "DELETE FROM test_note WHERE account_key = ?");
                 PreparedStatement deleteAccount =
                         connection.prepareStatement(
                                 "DELETE FROM test_account WHERE account_key = ?")) {

                deleteNotes.setString(1, token);
                deleteNotes.executeUpdate();

                deleteAccount.setString(1, token);
                deleteAccount.executeUpdate();
            }

            connection.commit();
        } catch (SQLException | RuntimeException failure) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        }
    }
}
```

Đoạn code giả định đã import `java.sql.Connection`, `PreparedStatement`, `SQLException` và `javax.sql.DataSource`, và có thể đặt trong một lớp helper. Mã chỉ xóa hàng khớp `token`, không chạy lệnh xóa trống `WHERE` trên toàn bảng.

### Cleanup phải được gọi kể cả khi test thất bại

```java
String token = "it-" + UUID.randomUUID();

try {
    // Tạo fixture đã commit bằng phương thức test setup.
    // Gọi SUT cần kiểm thử; SUT có thể commit riêng.
    // Đọc lại dữ liệu và assert.
} finally {
    cleanupCommittedFixture(testDataSource, token);
}
```

Đây là mẫu điều khiển **không phải** một test đầy đủ, vì setup/SUT phụ thuộc ứng dụng. `finally` giúp dọn sau `AssertionError`/`SQLException`, nhưng nếu tiến trình JVM hoặc máy CI bị tắt đột ngột thì `finally` không chạy. Vì vậy, nên có thêm **cơ chế dọn dữ liệu cũ** theo test-run ID/TTL hoặc hủy toàn bộ database/schema test sau job, nhất là trong CI.

Nếu cleanup cũng ném exception, đừng im lặng bỏ qua: báo lỗi rõ ràng, giữ thông tin lần chạy và đảm bảo test suite thất bại khi trạng thái môi trường không sạch. Khi cần giữ nguyên lỗi gốc, dùng một helper gắn cleanup exception vào `suppressed exceptions` tương tự ví dụ rollback.

### Vì sao không dùng `DELETE FROM test_account` hoặc `TRUNCATE` vô điều kiện?

Lệnh xóa toàn bộ bảng có thể xóa fixture của test khác đang chạy song song, làm suite khó đoán hoặc khiến các bài kiểm thử bất kỳ bị lỗi. `TRUNCATE` còn có hành vi transaction, reset identity và ràng buộc foreign key khác nhau theo DBMS. Chỉ dùng reset toàn bộ bảng khi **cả database/schema đã được cấp riêng cho đúng test hoặc suite** và chính sách reset được kiểm chứng.

## 8. Khóa tự sinh, sequence và các giới hạn của rollback

Nhiều schema dùng khóa tự sinh thay vì `account_key` do ứng dụng cung cấp:

```sql
-- Cú pháp chỉ mang tính minh họa:
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);
```

Với JDBC, có thể lấy khóa sinh thông qua:

```java
String sql = "INSERT INTO customer(email) VALUES (?)";
try (PreparedStatement statement = connection.prepareStatement(
        sql, java.sql.Statement.RETURN_GENERATED_KEYS)) {
    statement.setString(1, "test-" + UUID.randomUUID()
            + "@example.invalid");
    if (statement.executeUpdate() != 1) {
        throw new SQLException("Expected one inserted customer");
    }

    try (ResultSet generated = statement.getGeneratedKeys()) {
        if (!generated.next()) {
            throw new SQLException("No generated customer key");
        }
        long customerId = generated.getLong(1);
        // Dùng customerId cho các hàng con trong cùng transaction.
    }
}
```

**Không khẳng định identity/sequence quay lại giá trị cũ sau rollback.** Trên nhiều DBMS, việc cấp giá trị từ sequence/identity có thể tạo khoảng trống ngay cả khi transaction bị rollback; đây là hành vi hợp lệ. Vì vậy, test nên kiểm tra **tính duy nhất và quan hệ cha–con**, không yêu cầu lần insert tiếp theo chắc chắn nhận ID bằng `1` hoặc bằng ID của lần trước.

Tránh `SELECT MAX(id)` để xác định khóa vừa chèn: cách này không an toàn khi có insert đồng thời và không gắn đúng với lần insert hiện tại. Nếu dùng khóa sinh, lấy bằng `getGeneratedKeys()` hoặc API tương ứng của driver đã kiểm chứng.

### Rollback không nhất thiết hoàn tác mọi tác động ngoài DB

Một test có thể tạo file, gửi email, gọi HTTP API hoặc phát thông điệp qua broker trong quá trình chạy. `Connection.rollback()` chỉ điều khiển thay đổi thuộc transaction cơ sở dữ liệu; nó **không** thu hồi một email đã gửi hoặc file đã tạo.

Khi cần test một workflow như vậy, hãy thay external side effect bằng fake/test endpoint phù hợp, dùng sandbox riêng cho broker/file hoặc đặt cơ chế cleanup/idempotency cho tài nguyên bên ngoài. Không chạy thử gửi thông báo thực tới người dùng chỉ vì kết nối DB trỏ tới test database.

## 9. Đa kết nối, giao dịch và kiểm thử isolation

Một test về **cạnh tranh đồng thời** hoặc **mức cô lập** thường cần hai kết nối:

```text
Connection A                       Connection B
------------                       ------------
setAutoCommit(false)               setAutoCommit(false)
INSERT/UPDATE một hàng
(chưa commit)
                                   SELECT/UPDATE cùng hàng
                                   (có thể thấy/chờ/không thấy
                                    tùy isolation và DBMS)
ROLLBACK hoặc COMMIT
                                   Quan sát kết quả cuối
                                   ROLLBACK/COMMIT theo kịch bản
```

Đây là một test đặc biệt: **không thể** gom A và B thành một connection rồi vẫn chứng minh được hành vi hai transaction độc lập. Cần kiểm tra một cách có kiểm soát bằng transaction riêng, đồng bộ thread rõ ràng và timeout đủ để tránh test bị treo. Với `READ_COMMITTED`, dữ liệu chưa commit từ A thường không hiển thị cho B; cơ chế khóa và MVCC có thể khác nhau giữa các DB.

Khi thử deadlock hoặc lock timeout:

- Chỉ chạy trong **database test** có dữ liệu riêng, không dùng production.
- Dùng các khóa riêng của lượt chạy để không khóa hàng của test khác.
- Có timeout và cơ chế hủy, tránh chờ vô hạn.
- Không dựa vào `Thread.sleep(...)` như một phương pháp đồng bộ đáng tin cậy; ưu tiên `CountDownLatch`/barrier trong Java hoặc cơ chế điều phối test.
- Bảo đảm cả hai connection được đóng trong `finally`/`try-with-resources`, kể cả khi một thread thất bại.
- Phân biệt **deadlock**, **lock timeout**, **serialization failure** và **lỗi assertion**; thông báo SQLState/mã lỗi có thể khác theo DBMS.

Một số connection pool giới hạn số connection đang mượn. Nếu một test cần hai connection mà pool chỉ cho phép tối đa một connection, nó có thể timeout vì **cạn pool**, không phải vì lỗi isolation của DB. Cấu hình test pool phải phù hợp số transaction đồng thời cần mô phỏng.

## 10. Chạy test song song mà không làm nhiễm dữ liệu

Giả sử JUnit chạy nhiều ca kiểm thử song song, hoặc hai pipeline CI dùng cùng DB test. Một số nguồn va chạm phổ biến:

| Tài nguyên chia sẻ | Rủi ro | Cách cô lập |
| --- | --- | --- |
| Khóa chính/unique email cố định | Vi phạm unique constraint, lock wait | ID/token riêng mỗi test hoặc schema riêng |
| Bản ghi danh mục chung có thể sửa | Test A làm thay đổi giả định của B | Dữ liệu tham chiếu bất biến hoặc copy riêng |
| Một bảng test bị `TRUNCATE` | Xóa dữ liệu test khác | Không truncate khi chia sẻ schema |
| Sequence/identity toàn cục | ID không liên tiếp, ID test khác chen giữa | Không assert ID tuyệt đối hay reset sequence không kiểm soát |
| DDL/schema migration | Test khác đọc metadata khi schema đang thay đổi | Migration một lần trước suite hoặc DB/schema riêng |
| Các bảng điều khiển job/queue | Worker của test khác tiêu thụ bản ghi | Namespace/job ID riêng, worker test chuyên biệt |
| Connection pool nhỏ | Thread chờ connection, timeout ngẫu nhiên | Giới hạn parallelism và đặt pool size phù hợp |
| Đồng hồ hệ thống và dữ liệu thời gian | Test qua ngày/giờ/timeout bị biến động | Dùng clock có thể điều khiển ở tầng nghiệp vụ, thời gian cụ thể |

**UUID chỉ giải quyết một phần vấn đề.** Nó không cô lập những hàng chung mà hai test cùng sửa, không ngăn `TRUNCATE` toàn bảng, cũng không ngăn một job nền xử lý nhầm bản ghi nếu job không lọc theo test-run ID.

### Một test riêng, một database hay một schema riêng?

Với test cần tạo/dừng DB, migration hoặc kiểm tra lock đặc thù, một instance/database riêng theo suite thường đáng tin cậy hơn dùng rollback trên DB chia sẻ. Công cụ như **Testcontainers** có thể giúp cấp cơ sở dữ liệu thật trong container ở môi trường hỗ trợ, nhưng đây là **thư viện bổ sung**, không phải API JDBC chuẩn và không bắt buộc cho mọi dự án. Có thể dùng DB test được provision sẵn hoặc cơ chế tương đương theo hạ tầng nhóm.

Không giả định một DB in-memory như H2 có ngữ nghĩa đồng nhất với PostgreSQL, SQL Server, MySQL hay Oracle về SQL dialect, transaction, DDL, locking và cách JDBC driver báo lỗi. In-memory DB có thể phù hợp kiểm tra mapping và câu SQL đơn giản; các hành vi vendor-specific phải thử trên đúng hệ quản trị mục tiêu.

## 11. Cấu trúc test suite và môi trường CI

Một quy trình có thể duy trì lâu dài thường phân chia rõ trách nhiệm:

```text
CI job / local test profile
      |
      +-- Tạo database test riêng (hoặc schema riêng)
      |
      +-- Chạy migration tạo bảng, index, FK
      |
      +-- Nạp baseline bất biến nếu cần
      |
      +-- Test A: seed riêng -> SUT -> assert -> rollback/cleanup
      +-- Test B: seed riêng -> SUT -> assert -> rollback/cleanup
      +-- Test C: seed riêng -> SUT -> assert -> rollback/cleanup
      |
      +-- Xác minh không còn dữ liệu tạm ngoài dự kiến
      |
      +-- Hủy database/schema test hoặc giữ để debug có kiểm soát
```

Một số nguyên tắc về môi trường:

1. **Phân biệt cấu hình test với production** bằng cơ chế bí mật và thông số kết nối riêng; không lấy URL sản xuất làm default khi thiếu biến môi trường.
2. Tài khoản DB của test chỉ có quyền cần thiết trên **database/schema test**. Với migration, có thể dùng một tài khoản setup riêng được cấp quyền DDL phù hợp.
3. **Fail fast** nếu không tìm được DB test hoặc DB không khớp nhận diện môi trường dự kiến; không “tạm dùng” production để chạy tiếp.
4. DDL và schema phải được tạo từ **migration thật hoặc một bộ script đã quản lý phiên bản**, tránh test tự suy diễn schema không giống ứng dụng.
5. Fixture nên có tên và mục đích rõ ràng; tránh một file SQL khổng lồ chứa hàng nghìn hàng không liên quan tới test.
6. Cleanup lỗi phải được báo ra CI. Nếu DB test được cấp riêng theo job, việc hủy database/container sau job có thể là lớp bảo vệ bổ sung.
7. Không log mật khẩu DB hoặc dữ liệu nhạy cảm khi in `SQLException`, SQL và các giá trị bind để debug.

### Nên seed ở đâu?

| Phạm vi | Nên chứa | Cần tránh |
| --- | --- | --- |
| **Một lần cho suite** | Schema, index, dữ liệu tham chiếu bất biến | Hàng có thể bị test sửa chung |
| **`@BeforeEach` / fixture per-test** | Dữ liệu riêng cho một kịch bản, khóa/token riêng | Giả định test trước đã chạy |
| **Bên trong transaction test** | Dữ liệu sẽ được rollback cùng thay đổi SUT | Gọi một repository tự commit qua connection khác |
| **`@AfterEach` / `finally`** | Cleanup theo token, giải phóng tài nguyên | Lệnh xóa toàn bộ bảng trong DB chia sẻ |

Nếu dùng JUnit 5, `@BeforeEach` và `@AfterEach` chỉ là các hook tổ chức vòng đời; chúng **không mặc định** mở transaction, rollback hay xóa dữ liệu. Chính test code hoặc extension/transaction manager đã cấu hình phải thực hiện các bước đó.

### Thử cả trường hợp cleanup thất bại

Hãy thử cố tình khiến một test ném `AssertionError` sau khi đã seed dữ liệu. Kiểm tra rằng:

- `rollback()` vẫn chạy, hoặc cleanup vẫn được gọi theo `finally`.
- Connection/statement/result set đã đóng.
- Trạng thái DB sau test đúng kỳ vọng.
- Thông báo lỗi gốc còn nguyên, lỗi rollback/cleanup được đính kèm khi thích hợp.
- Test kế tiếp vẫn chạy được nếu môi trường cho phép tiếp tục sau lỗi.

Chỉ chạy đường thành công không đủ chứng minh test suite có cô lập thật.

## 12. Các lỗi phổ biến khi quản lý dữ liệu mẫu

| Cách làm sai | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Seed dữ liệu một lần rồi để các test sửa cùng hàng | Test phụ thuộc thứ tự và kết quả của test trước | Dữ liệu riêng từng test hoặc baseline bất biến |
| Tất cả test dùng `account_key = 'test-1'` | Va chạm khóa, nhất là khi chạy song song | Token riêng hoặc DB/schema riêng |
| Tưởng `rollback()` trên A hoàn tác SQL của B | Connection B có transaction riêng | Truyền cùng connection hoặc cleanup ngoài |
| SUT tự gọi `commit()` giữa test rollback | Các thay đổi trước commit đã được giữ lại | Refactor ranh giới transaction hoặc chọn chiến lược khác |
| Chỉ rollback nếu tất cả assertion thành công | Test lỗi để lại dữ liệu và khóa | `finally` hoặc test lifecycle có cleanup chắc chắn |
| Dùng `DELETE FROM table` không có `WHERE` | Xóa dữ liệu test khác/baseline | Cleanup theo khóa fixture, hoặc chỉ reset trên DB test riêng |
| Xóa bảng cha trước bảng con có FK | Vi phạm ràng buộc, cleanup thất bại | Xóa con trước cha, kiểm tra cascade thực tế |
| Dùng `TRUNCATE` trong transaction và tin rằng luôn rollback được | DDL/transaction khác nhau theo DB | Kiểm chứng DB/driver, không dùng thay cho rollback phổ quát |
| Assert generated key luôn bằng `1` | Sequence/identity có thể không rollback | Assert quan hệ, tính duy nhất, lấy bằng `getGeneratedKeys()` |
| Test SQL trên H2 rồi kết luận hành vi PostgreSQL giống hệt | Khác dialect, lock, DDL, isolation | Integration test trên DBMS mục tiêu |
| Gọi API bên ngoài trong test nhưng chỉ rollback DB | Side effect ngoài DB còn tồn tại | Dùng fake/sandbox, cleanup và idempotency |
| Dùng sleep tùy ý để đồng bộ hai transaction | Flaky/race, khó tái hiện deadlock | Barrier/latch và timeout |
| Không giới hạn pool cho test song song | Kết nối cạn, test timeout | Tính kích thước pool theo workload |
| Bỏ qua exception khi cleanup | Suite để lại dữ liệu nhưng vẫn báo xanh | Fail test/CI, giữ lỗi gốc và thông tin cleanup |
| Chạy test trên DB không xác nhận là DB test | Rủi ro thay đổi dữ liệu quan trọng | Fail fast, tách thông tin kết nối và quyền |

## 13. Ma trận kiểm thử thực tế

Các bài integration test nên bao gồm cả **đường thành công** và **đường lỗi**, kiểm tra DB sau mỗi giai đoạn:

| Tình huống | Setup và hành động | Điều cần xác minh |
| --- | --- | --- |
| Một test rollback thành công | Chèn tài khoản, hai ghi chú, cập nhật trạng thái | Dữ liệu nhìn thấy trong transaction; kết nối mới sau rollback không thấy fixture |
| Assertion lỗi giữa chừng | Chèn fixture rồi cố ném `AssertionError` | `finally` rollback, không còn hàng |
| Vi phạm unique constraint | Chèn hai email giống nhau trong cùng transaction | `SQLException` được báo; dữ liệu tạm không còn sau rollback |
| Vi phạm foreign key | Chèn ghi chú trước khi có tài khoản cha | Constraint được thực thi hoặc báo khác biệt cấu hình DB |
| Test có SUT tự commit | Gọi service sử dụng connection riêng | Không kỳ vọng rollback connection test; cleanup/DB riêng xử lý đúng |
| Cleanup có nhiều bảng | Xóa theo token, con trước cha | Không xóa dữ liệu fixture khác; không còn hàng test |
| Two-connection visibility | A insert chưa commit, B đọc dưới isolation đã định | Quan sát đúng cơ chế DB đích; không dựa vào connection A để đại diện B |
| Hai test song song | Tạo token khác nhau và chạy đồng thời | Không va chạm khóa, không xóa nhầm hàng |
| Baseline bất biến | Nạp dữ liệu tham chiếu trước suite | Dữ liệu không bị test thay đổi |
| Generated keys | Insert bằng `RETURN_GENERATED_KEYS` rồi rollback | Không assert ID liên tiếp; quan hệ khóa đúng |
| Migration/DDL | Chạy setup trên database test riêng | Schema hợp lệ, không có tác động lên DB khác |
| Test bị hủy đột ngột | Mô phỏng job mất tiến trình sau seed đã commit | Có cleanup theo test-run hoặc hủy DB test sau job |
| Kết nối pool bị thiếu | Test concurrency mượn nhiều connection hơn pool cho phép | Có timeout chẩn đoán rõ, không nhầm là DB deadlock |
| DB/driver nâng cấp | Chạy lại cùng suite | Phát hiện thay đổi constraint, isolation, SQLState hoặc transaction |

### Nên kiểm tra bằng query sau rollback/cleanup

```sql
SELECT COUNT(*)
FROM test_account
WHERE account_key = ?;

SELECT COUNT(*)
FROM test_note
WHERE account_key = ?;
```

Hai câu truy vấn trên phải được bind bằng `PreparedStatement`, với token riêng của test. Nếu test đã rollback hoặc cleanup thành công, count dự kiến là `0`. Kiểm tra từ **connection mới** sau rollback giúp xác nhận trạng thái quan sát bên ngoài transaction test, thay vì chỉ đọc lại một đối tượng Java đã cache dữ liệu cũ.

Đối với test isolation, số hàng nhìn thấy trước commit còn phụ thuộc mức cô lập; do đó, khi cần xác minh không rò rỉ dữ liệu, hãy đợi transaction đóng/rollback xong rồi mới kiểm tra từ connection mới.

## 14. Bài tập tự kiểm tra

**Bài 1 — Chọn cách cô lập.** Repository được thiết kế nhận `Connection` từ caller và không tự gọi `commit()`. Test muốn chèn dữ liệu mẫu, chạy hai câu `UPDATE` và kiểm tra kết quả. Chiến lược nào đơn giản nhất?

**Đáp án:** Mở một transaction với `autoCommit = false`, dùng cùng connection cho seed/SUT/assert rồi rollback trong `finally`. Điều kiện: DB và bảng hỗ trợ transaction.

**Bài 2 — Sai ranh giới kết nối.** Test seed trên connection A, service lại mở connection B và commit. Sau đó test gọi `A.rollback()`. Dữ liệu từ B có bị hoàn tác không?

**Đáp án:** Không. Rollback của A không điều khiển transaction trên B. Cần thiết kế lại để dùng cùng transaction hoặc dùng cleanup/schema/database riêng.

**Bài 3 — Khóa chính cố định.** Hai test song song cùng chèn `account_key = 'fixture-1'`. Điều gì có thể xảy ra và cách khắc phục?

**Gợi ý:** Vi phạm unique key hoặc tranh chấp khóa. Tạo token riêng theo test/lượt chạy, hoặc tách database/schema.

**Bài 4 — Cleanup đúng thứ tự.** Bảng `test_note` có foreign key tới `test_account`. Khi xóa dữ liệu đã commit theo một token, nên xóa bảng nào trước?

**Đáp án:** Xóa `test_note` trước rồi `test_account`, trừ khi có cơ chế cascade đã được thiết kế và kiểm chứng.

**Bài 5 — Sequence sau rollback.** Test tạo một hàng `IDENTITY`, rollback, rồi test tiếp theo nhận ID lớn hơn. Có phải JDBC rollback lỗi?

**Đáp án:** Không nhất thiết. Sequence/identity thường không hoàn lại giá trị đã cấp. Test không nên yêu cầu ID liên tiếp hoặc cố định.

**Bài 6 — Trường hợp commit thật.** Một bài thử cần chứng minh dữ liệu đã commit tồn tại khi đọc từ connection thứ hai. Vì sao không thể chỉ dựa vào test transaction luôn rollback?

**Đáp án:** Phải thực sự commit ở một transaction rồi quan sát từ connection khác; sau test cần cleanup theo token hoặc database/schema riêng để không rò rỉ dữ liệu.

**Bài 7 — Test tự tạo bảng.** Một test gọi `CREATE TABLE` trong transaction rồi cuối test rollback. Có thể coi schema chắc chắn biến mất trên mọi DBMS không?

**Đáp án:** Không. Ngữ nghĩa DDL và implicit commit phụ thuộc DB. Test migration/schema nên dùng môi trường tách biệt và cleanup schema/database rõ ràng.

**Bài 8 — Test song song và dữ liệu nền.** Mỗi test có UUID riêng nhưng cả hai cùng cập nhật hàng `system_setting` có ID cố định. UUID có bảo đảm không ảnh hưởng nhau không?

**Đáp án:** Không. Hàng dùng chung vẫn bị tranh chấp hoặc thay đổi; cần test không sửa baseline, tách môi trường hoặc đồng bộ lịch chạy.

**Bài 9 — Chạy ở CI.** Tại sao không nên dùng cùng credentials/database với production cho integration test chỉ vì test có cleanup?

**Đáp án:** Test có thể lỗi, hủy bất thường hoặc dùng DDL/DML ngoài dự kiến; cleanup không phải bảo đảm an toàn. Cần DB test riêng, quyền giới hạn và kiểm tra cấu hình trước khi chạy.

**Bài 10 — Lỗi trong cleanup.** Một test thất bại do `SQLException`, sau đó `rollback()` cũng ném `SQLException`. Báo cáo nên giữ lỗi nào?

**Gợi ý:** Giữ **lỗi gốc** và gắn lỗi rollback qua `addSuppressed` khi có thể; không được im lặng xóa thông tin lỗi đầu tiên.

## Tổng kết

Quản lý dữ liệu mẫu và cô lập giữa các bài kiểm thử JDBC là điều kiện để test **lặp lại được, chạy độc lập và đáng tin cậy**. Hãy tạo fixture nhỏ với khóa riêng, chỉ seed dữ liệu cần thiết và kiểm tra kết quả bằng SQL trên DB thực. Khi toàn bộ công việc nằm trên **cùng `Connection`**, `setAutoCommit(false)` cùng `rollback()` trong `finally` là cách cô lập hiệu quả. Với code tự commit, đa kết nối, worker bất đồng bộ hoặc DDL, hãy chuyển sang cleanup theo token hay schema/database riêng, đồng thời tôn trọng foreign key và các giới hạn sequence/transaction của DBMS. Trong CI, chạy trên **database test được tách biệt**, kiểm soát quyền truy cập, thử cả đường thất bại và xác minh không còn dữ liệu tạm sau khi test kết thúc. Những nguyên tắc này giúp việc kiểm thử SQL tham số hóa, CRUD, transaction, batching và xử lý lỗi JDBC phản ánh hành vi thật mà không gây tác động chéo giữa các ca.
