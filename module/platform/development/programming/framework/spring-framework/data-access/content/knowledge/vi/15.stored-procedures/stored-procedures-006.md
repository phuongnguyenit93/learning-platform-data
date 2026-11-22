# Đọc nhiều kết quả, giá trị OUT và con trỏ từ thủ tục/hàm với Spring JDBC

> **Phạm vi:** Spring Framework – Data Access / **Thủ tục và hàm**. Bài này giải thích cách thu thập nhiều tập kết quả (`ResultSet`), số dòng bị ảnh hưởng (`update count`), tham số `OUT`/`INOUT` và con trỏ (`REF_CURSOR`) khi gọi stored procedure/function. Điểm quyết định là **khả năng thực tế của cặp hệ quản trị cơ sở dữ liệu và JDBC driver**, không chỉ tên API của Spring.

## 1. Một lần gọi có thể trả về những gì?

Thủ tục lưu trữ không nhất thiết trả về một giá trị duy nhất. Một lời gọi có thể tạo ra một **chuỗi kết quả**, ví dụ:

```text
CALL báo_cáo(?)
    ├─ UPDATE COUNT: 2 hàng đã cập nhật
    ├─ RESULT SET #1: danh sách nhân viên
    ├─ RESULT SET #2: bảng tổng hợp
    └─ OUT "matched": 2
```

Đây là bốn khái niệm liên quan nhưng khác nhau:

| Kênh kết quả | Bản chất | Cách nhận ở JDBC | Cách nhận ở Spring JDBC |
| --- | --- | --- | --- |
| `ResultSet` thứ nhất, thứ hai, ... | Các hàng/cột do thủ tục trả trong dòng kết quả của lệnh gọi | `execute()`, `getResultSet()`, `getMoreResults()` | `SimpleJdbcCall.returningResultSet(name, rowMapper)`, hoặc callback `JdbcTemplate` |
| `update count` | Số dòng bị tác động bởi một lệnh DML nằm trong thủ tục (nếu driver phát ra) | `getUpdateCount()` sau mỗi bước | `JdbcTemplate` có thể xử lý/trả các count; không nhầm chúng với `ResultSet` |
| `OUT`/`INOUT` | Giá trị gắn với tham số thủ tục | `registerOutParameter(...)` rồi `getXxx(...)` | `SqlOutParameter`, `SqlInOutParameter`; lấy từ `Map` của `SimpleJdbcCall.execute(...)` |
| `REF_CURSOR` | Tham số `OUT` trỏ tới một tập kết quả ở phía DB, khi DB/driver hỗ trợ | Đăng ký kiểu cursor, `getObject(...)` và xử lý đối tượng được driver trả về | `returningResultSet` theo đúng tên cursor, hoặc `SqlOutParameter` với mapper thích hợp |

**Không nhầm:** tập kết quả mà thủ tục phát trực tiếp trong quá trình chạy không nhất thiết là một tham số `OUT`; ngược lại, một tham số `OUT` kiểu cursor có thể là *nguồn* của `ResultSet`. Một hàm còn có **giá trị trả về** bằng cú pháp `{? = call ten_ham(?)}`; vị trí `?` đầu tiên là giá trị trả về, nên các vị trí tham số tiếp theo dịch sang phải.

Vì SQL cho thủ tục, cách trả cursor và tên tham số thay đổi theo DBMS, hãy phân tích chữ ký thủ tục và cấu hình driver trước khi viết bộ đọc kết quả.

## 2. Quy tắc JDBC để không bỏ sót tập kết quả

`CallableStatement` kế thừa `Statement` và hỗ trợ chuỗi xen kẽ **ResultSet / update count**:

1. Tạo `CallableStatement` bằng `Connection.prepareCall("{call ...}")`; dùng `setXxx` cho `IN` và `INOUT`, đăng ký **tất cả `OUT`/`INOUT`** bằng `registerOutParameter` **trước khi chạy**.
2. Gọi **`execute()`** khi có thể nhận nhiều kết quả. Giá trị trả về `true` nghĩa là **kết quả hiện tại là `ResultSet`**; `false` nghĩa là kết quả hiện tại là **update count hoặc chưa có kết quả**. `false` **không có nghĩa là đã hết**.
3. Nếu `true`, lấy `getResultSet()` và đọc toàn bộ hàng cần dùng. Nếu `false`, lấy `getUpdateCount()`; số `0` cũng là **một update count hợp lệ**.
4. Chỉ kết thúc khi kết quả hiện tại **không phải `ResultSet` và `getUpdateCount() == -1`**. Sau mỗi phần tử, gọi `getMoreResults()` để chuyển sang phần tiếp theo.
5. Với tính tương thích cao nhất, đọc xong **mọi `ResultSet` và update count trước khi lấy các tham số `OUT`**. Một số driver chỉ cung cấp OUT đầy đủ sau khi kết thúc dòng kết quả.
6. Đóng các `ResultSet`, `CallableStatement` và `Connection`; trong Spring, dùng callback/template để Spring quản lý connection và transaction.

**Thuật toán cần nhớ:**

```java
// Thuật toán JDBC; giả sử cs đã bind/register tham số.
boolean hasResultSet = cs.execute();
while (true) {
    if (hasResultSet) {
        try (ResultSet rs = cs.getResultSet()) {
            while (rs.next()) {
                // Đọc/mapping từng hàng của ResultSet hiện tại.
            }
        }
    } else {
        int updateCount = cs.getUpdateCount();
        if (updateCount == -1) {
            break; // Chỉ đây mới là điều kiện kết thúc.
        }
        // Xử lý updateCount, kể cả giá trị 0.
    }
    hasResultSet = cs.getMoreResults();
}
// Sau vòng lặp mới đọc cs.getXxx(vị_trí_OUT).
```

`getMoreResults()` mặc định đóng `ResultSet` hiện tại. Nếu cần giữ nhiều `ResultSet` mở đồng thời, JDBC có `getMoreResults(Statement.KEEP_CURRENT_RESULT)`, nhưng chỉ dùng sau khi kiểm tra `DatabaseMetaData.supportsMultipleOpenResults()`; cách đơn giản và dễ bảo trì là **đọc, đóng, rồi chuyển tiếp**.

## 3. Ví dụ cụ thể: SQL Server phát 2 ResultSet, update count và OUT

Ví dụ này cố ý chọn **SQL Server + Microsoft JDBC Driver** vì hệ này hỗ trợ thủ tục phát trực tiếp nhiều `SELECT` cùng tham số `OUT`. Kịch bản dưới đây là **SQL Server T-SQL**, không thể sao chép nguyên xi sang PostgreSQL/MySQL/Oracle. Cần có SQL Server đang chạy, một database thử nghiệm, quyền tạo bảng/thủ tục và driver JDBC tương ứng.

### 3.1. Tạo dữ liệu và thủ tục

Chạy trong SSMS hoặc `sqlcmd` (ở đây `GO` là dấu kết thúc batch của công cụ SQL Server, **không** phải câu SQL gửi qua JDBC):

```sql
CREATE TABLE dbo.demo_employee (
    id        INT           NOT NULL PRIMARY KEY,
    full_name NVARCHAR(100) NOT NULL,
    visits    INT           NOT NULL
);
GO

INSERT INTO dbo.demo_employee (id, full_name, visits) VALUES
(1, N'An',   0),
(2, N'Binh', 0),
(3, N'Chi',  0);
GO

CREATE OR ALTER PROCEDURE dbo.demo_employee_report
    @min_id  INT,
    @matched INT OUTPUT
AS
BEGIN
    -- Cho phép driver nhìn thấy count của UPDATE.
    SET NOCOUNT OFF;

    UPDATE dbo.demo_employee
    SET visits = visits + 1
    WHERE id >= @min_id;

    -- ResultSet 1: các hàng chi tiết
    SELECT id, full_name, visits
    FROM dbo.demo_employee
    WHERE id >= @min_id
    ORDER BY id;

    -- ResultSet 2: một hàng tổng hợp
    SELECT COUNT(*) AS n
    FROM dbo.demo_employee
    WHERE id >= @min_id;

    -- Giá trị OUT: không phải là ResultSet thứ ba.
    SET @matched = (
        SELECT COUNT(*) FROM dbo.demo_employee WHERE id >= @min_id
    );
END;
GO
```

Với `@min_id = 2` sau lần chạy đầu, cập nhật ảnh hưởng đến nhân viên `2` và `3`; tập chi tiết gồm hai hàng, tập tổng hợp cho `n = 2`, còn `@matched = 2`. Gọi thủ tục thêm lần nữa sẽ tiếp tục tăng `visits`, nên đây **không** phải ví dụ idempotent.

### 3.2. Java 17: đọc chính xác thứ tự kết quả

Tạo file **`ReadProcedureResults.java`**:

```java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;

public final class ReadProcedureResults {
    public static void main(String[] args) throws SQLException {
        String url = System.getenv("DB_URL");
        String username = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        if (url == null || username == null || password == null) {
            throw new IllegalStateException(
                "Set DB_URL, DB_USER and DB_PASSWORD first");
        }

        try (Connection connection =
                     DriverManager.getConnection(url, username, password);
             CallableStatement call = connection.prepareCall(
                     "{call dbo.demo_employee_report(?, ?)}")) {

            // SQL Server: @min_id (IN), @matched (OUT)
            call.setInt(1, 2);
            call.registerOutParameter(2, Types.INTEGER);

            boolean hasResultSet = call.execute();
            int resultSetNumber = 0;

            while (true) {
                if (hasResultSet) {
                    resultSetNumber++;

                    try (ResultSet rs = call.getResultSet()) {
                        if (resultSetNumber == 1) {
                            while (rs.next()) {
                                System.out.printf(
                                    "EMPLOYEE id=%d name=%s visits=%d%n",
                                    rs.getInt("id"),
                                    rs.getString("full_name"),
                                    rs.getInt("visits"));
                            }
                        } else if (resultSetNumber == 2) {
                            while (rs.next()) {
                                System.out.println(
                                    "SUMMARY n=" + rs.getInt("n"));
                            }
                        } else {
                            // Quy tắc cho thủ tục mở rộng sau này:
                            // ít nhất phải tiêu thụ kết quả bổ sung.
                            while (rs.next()) {
                                // Có thể xử lý theo ResultSetMetaData.
                            }
                        }
                    }
                } else {
                    int count = call.getUpdateCount();
                    if (count == -1) {
                        break;
                    }
                    System.out.println("UPDATE_COUNT=" + count);
                }

                hasResultSet = call.getMoreResults();
            }

            // Đọc OUT sau toàn bộ chuỗi ResultSet/update count.
            int matched = call.getInt(2);
            System.out.println(
                "OUT matched=" + (call.wasNull() ? "NULL" : matched));
        }
    }
}
```

Chương trình trên dùng **chỉ API `java.sql` của JDK 17** ở thời điểm biên dịch. Khi **chạy**, JVM vẫn cần Microsoft JDBC Driver có trong classpath; tên JAR và phiên bản tùy bộ driver đã cài:

```bash
javac --release 17 -encoding UTF-8 ReadProcedureResults.java

# Windows PowerShell: đổi tên driver JAR thành mssql-jdbc.jar
java -cp ".;mssql-jdbc.jar" ReadProcedureResults

# Linux/macOS dùng dấu ':' thay cho ';' để phân tách classpath:
# java -cp ".:mssql-jdbc.jar" ReadProcedureResults
```

Trước khi chạy, đặt `DB_URL`, `DB_USER`, `DB_PASSWORD` trong biến môi trường. `DB_URL` phải chỉ đến database đã chạy script ở mục 3.1; ví dụ cú pháp URL là `jdbc:sqlserver://localhost:1433;databaseName=your_database`, còn cấu hình TLS/xác thực cần đặt theo môi trường thật.

**Ý nghĩa kết quả lần đầu** (đây là các giá trị logic; thứ tự dòng log hay việc driver phát thêm update count có thể khác theo cấu hình):

```text
UPDATE_COUNT=2
EMPLOYEE id=2 name=Binh visits=1
EMPLOYEE id=3 name=Chi visits=1
SUMMARY n=2
OUT matched=2
```

Điểm quan trọng của đoạn Java không phải số lượng `UPDATE_COUNT` cố định, mà là **vòng lặp không dừng sau một `getMoreResults() == false` nếu còn `getUpdateCount() >= 0`**. Trong SQL Server, `SET NOCOUNT ON` có thể ẩn các count trung gian; thay đổi cấu hình thủ tục có thể thay đổi dòng kết quả mà client nhìn thấy. Chương trình kiểm tra đúng **số thứ tự các `ResultSet`**, không dựa vào việc có bao nhiêu update count.

> **Phạm vi chạy:** ví dụ `main` là ứng dụng JDBC ngoài Spring để nhìn thấy đầy đủ cơ chế. Trong một ứng dụng Spring đã quản lý transaction, không tự dùng `DriverManager` hay đóng connection do Spring cung cấp; dùng `JdbcTemplate`/`DataSource` của ứng dụng.

## 4. Dùng `SimpleJdbcCall` trong Spring để nhận nhiều ResultSet và OUT

Khi đã biết chữ ký thủ tục và các result set sẽ xuất hiện, `SimpleJdbcCall` là lựa chọn thường ngắn gọn hơn. Nó nhận tham số `IN`, ánh xạ `OUT` và các result set vào một `Map<String, Object>`.

**Ví dụ tích hợp trong ứng dụng Spring JDBC 6.x, dùng thủ tục SQL Server ở mục 3** (lớp DAO này cần `spring-jdbc` và `DataSource` đã cấu hình; đây là thành phần ứng dụng, không phải chương trình `main` độc lập):

```java
import java.sql.Types;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;

public final class EmployeeReportDao {
    public record Employee(int id, String fullName, int visits) {}
    public record Report(
            List<Employee> employees, int total, Integer matched) {}

    private final SimpleJdbcCall procedure;

    public EmployeeReportDao(DataSource dataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setResultsMapCaseInsensitive(true);

        this.procedure = new SimpleJdbcCall(jdbc)
            .withSchemaName("dbo")
            .withProcedureName("demo_employee_report")
            .withoutProcedureColumnMetaDataAccess()
            .declareParameters(
                new SqlParameter("min_id", Types.INTEGER),
                new SqlOutParameter("matched", Types.INTEGER))
            .returningResultSet("employees", (rs, rowNum) ->
                new Employee(
                    rs.getInt("id"),
                    rs.getString("full_name"),
                    rs.getInt("visits")))
            .returningResultSet("summary", (rs, rowNum) ->
                rs.getInt("n"));
    }

    public Report run(int minId) {
        Map<String, Object> out = procedure.execute(
            new MapSqlParameterSource("min_id", minId));

        @SuppressWarnings("unchecked")
        List<Employee> employees =
            (List<Employee>) out.get("employees");

        @SuppressWarnings("unchecked")
        List<Integer> summary =
            (List<Integer>) out.get("summary");

        Number matched = (Number) out.get("matched");

        return new Report(
            employees,
            summary.get(0),
            matched == null ? null : matched.intValue());
    }
}
```

**Tại sao cấu hình như vậy?**

- `withProcedureName("demo_employee_report")` chọn thủ tục; `withSchemaName("dbo")` chọn schema SQL Server.
- `withoutProcedureColumnMetaDataAccess()` tắt suy đoán danh sách tham số bằng metadata; `declareParameters(...)` khai báo tường minh **đúng thứ tự/tham số**. Cách này hữu ích khi metadata không đầy đủ, có overload hoặc driver công bố tên khác mong đợi. Nếu bật tra metadata, Spring có thể suy ra nhiều tham số nhưng phải kiểm tra kết quả thực tế của driver.
- `new SqlParameter("min_id", Types.INTEGER)` biểu diễn `IN`; `new SqlOutParameter("matched", Types.INTEGER)` biểu diễn `OUT`. Với tham số vừa IN vừa OUT, dùng `SqlInOutParameter` và cung cấp cả đầu vào tương ứng.
- Hai `returningResultSet(...)` đăng ký **hai `RowMapper` theo đúng thứ tự các ResultSet không có tên** xuất hiện từ thủ tục; tên `employees`/`summary` là khóa do ứng dụng đặt để lấy kết quả. **Không phải tên cột và không phải tên tham số OUT.**
- `Map` kết quả chứa `employees` và `summary` dưới dạng danh sách được mapper tạo, cùng giá trị `matched`. Không suy ra thứ tự kết quả từ thứ tự duyệt các khóa `Map`.
- `setResultsMapCaseInsensitive(true)` giúp tra cứu key OUT ổn định hơn khi driver/database thay đổi hoa/thường tên tham số. Không vì thế mà có thể đổi tùy ý tên tham số của thủ tục khi tắt metadata.
- `summary.get(0)` giả định thủ tục đã hứa trả đúng một dòng tổng hợp; nếu thủ tục không bảo đảm điều đó, ứng dụng cần kiểm tra danh sách và báo lỗi nghiệp vụ.

Lưu ý: `SimpleJdbcCall` giúp **thu thập và chuyển đổi** kết quả, nhưng nếu một `ResultSet` lớn được ánh xạ thành `List` thì bộ nhớ vẫn tăng theo số hàng. Với hàng triệu hàng, hãy xem mục 7 về xử lý tuần tự.

### Khi nào dùng `JdbcTemplate` thay vì `SimpleJdbcCall`?

`JdbcTemplate.execute(callString, CallableStatementCallback<T>)` cho phép tự điều khiển `CallableStatement` trong một callback, xử lý từng `ResultSet` và update count theo thuật toán mục 2, kể cả khi số lượng/tên/khuôn dạng của các tập trả về chỉ được biết khi chạy. `JdbcTemplate.call(CallableStatementCreator, List<SqlParameter>)` cũng hỗ trợ khai báo kết quả; `SqlReturnResultSet` có thể dùng `RowMapper`, `ResultSetExtractor` hoặc `RowCallbackHandler`.

Điều này hữu ích khi cần giải mã một loạt tập kết quả có cấu trúc động hoặc ghi từng hàng sang đích khác. Các callback của `JdbcTemplate` được thực thi trong connection của Spring, tham gia giao dịch hiện có và chuyển `SQLException` thành `DataAccessException`. Không giữ `ResultSet` để đọc sau khi callback đã trả về.

## 5. REF_CURSOR: nhận con trỏ như một OUT parameter

Một số hệ quản trị trả kết quả qua tham số `OUT` kiểu **cursor** thay vì phát trực tiếp `SELECT` trong chuỗi `getMoreResults()`. Với JDBC hỗ trợ chuẩn, có thể đăng ký:

```java
// Minh họa: chỉ dùng khi chữ ký DB và JDBC driver hỗ trợ REF_CURSOR.
try (CallableStatement call =
         connection.prepareCall("{call open_employees(?, ?)}")) {
    call.setInt(1, minId);
    call.registerOutParameter(2, Types.REF_CURSOR);
    call.execute();

    Object value = call.getObject(2);
    if (!(value instanceof ResultSet)) {
        throw new SQLException("Driver did not return a ResultSet cursor");
    }

    try (ResultSet rs = (ResultSet) value) {
        while (rs.next()) {
            // Dùng dữ liệu khi cursor, statement, connection còn sống.
        }
    }
}
```

Ví dụ trên là **mã tích hợp, không độc lập**: thủ tục `open_employees`, cú pháp call, kiểu cursor và khả năng `getObject` trả `ResultSet` phải được xác minh với DB/driver. Không đánh đồng `Types.REF_CURSOR` với `Types.REF`; đây là hai mã kiểu JDBC khác nhau. Một driver có thể yêu cầu kiểu riêng, ví dụ một số đường gọi PostgreSQL đăng ký `Types.OTHER`.

### 5.1. PostgreSQL qua pgJDBC: khác với ví dụ SQL Server

PostgreSQL cho phép hàm trả `SETOF` hoặc `refcursor`. **Hàm trả `SETOF`** thường nên truy vấn bằng `SELECT * FROM ten_ham(?)` với `PreparedStatement`/`JdbcTemplate.query(...)`, không ép thành `CallableStatement`. Với hàm trả `refcursor`, tài liệu pgJDBC hướng dẫn đặt `autoCommit = false` và đăng ký return parameter kiểu `Types.OTHER`.

Ví dụ minh họa cho một **hàm PostgreSQL có sẵn** tên `open_employees(min_id integer) RETURNS refcursor`, được định nghĩa để mở con trỏ tới bảng tương ứng:

```java
// Mã tích hợp PostgreSQL, dùng ngoài transaction do Spring quản lý.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (CallableStatement call = connection.prepareCall(
            "{? = call open_employees(?)}")) {
        call.registerOutParameter(1, Types.OTHER);
        call.setInt(2, 2);
        call.execute();

        try (ResultSet cursor = (ResultSet) call.getObject(1)) {
            while (cursor.next()) {
                System.out.println(cursor.getString("full_name"));
            }
        }
    }
    connection.commit();
}
```

**Hai ràng buộc rất dễ bỏ qua:**

1. Cursor PostgreSQL cần transaction còn sống. Nếu đóng/commit giao dịch quá sớm, con trỏ phía server có thể không còn truy cập được. Trong ứng dụng Spring, dùng `@Transactional` và bộ đọc có cùng phạm vi transaction; tránh tùy tiện gọi `setAutoCommit(false)`/`commit()` trên connection do Spring quản lý.
2. **pgJDBC hiện mô tả giới hạn riêng:** khi đọc `refcursor` dưới dạng `ResultSet`, driver có thể tải và cache **toàn bộ hàng ở client**, và `fetchSize` không giúp giảm bộ nhớ với đường xử lý này. Vì thế, “cursor” không tự động đồng nghĩa với streaming ít RAM. Nếu mục tiêu là đọc rất nhiều hàng, đánh giá truy vấn `SELECT` + cursor/fetch-size do driver hỗ trợ hoặc phân trang.

Ngoài ra, pgJDBC có thuộc tính `escapeSyntaxCallMode`: chế độ mặc định ưu tiên hàm; `callIfNoReturn` thường cần khi gọi **procedure** không có vị trí return. Không nên áp cùng cú pháp `{call ...}` lên mọi DB mà không kiểm tra mapping của driver.

### 5.2. Oracle và các driver khác

Oracle thường dùng `SYS_REFCURSOR`/cursor OUT theo chữ ký PL/SQL; driver Oracle có thể hỗ trợ `Types.REF_CURSOR` hoặc đường gọi dùng hằng số kiểu Oracle. Cần đối chiếu phiên bản driver, kiểu được đăng ký và cách ánh xạ `ResultSet`. Còn SQL Server thường trả các `SELECT` trực tiếp theo chuỗi nhiều kết quả, không yêu cầu giả lập chúng thành tham số `REF_CURSOR`. Đây là **các mô hình thường gặp**, không phải quy tắc cho mọi thủ tục hay mọi bản driver.

Trong Spring, `SimpleJdbcCall.returningResultSet("p_cursor", mapper)` có thể ánh xạ một cursor OUT **nếu driver và Spring hỗ trợ**, nhưng **tên `p_cursor` phải khớp tên tham số cursor của thủ tục**. Với một số driver/kiểu cursor, có thể phải khai báo tường minh `SqlOutParameter` kèm `RowMapper`/`SqlReturnType`. Tránh đăng ký hai lần cùng một cursor bằng hai con đường mà không hiểu metadata; kiểm tra `Map` nhận được với thủ tục thật.

## 6. Đánh giá khả năng driver trước khi chọn cách gọi

JDBC cung cấp `DatabaseMetaData` để khảo sát chức năng mà **driver + database** báo hỗ trợ:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public final class JdbcCapabilities {
    public static void print(Connection connection) throws SQLException {
        DatabaseMetaData m = connection.getMetaData();
        System.out.println("Driver: " + m.getDriverName());
        System.out.println("Driver version: " + m.getDriverVersion());
        System.out.println("Stored procedures: " +
                m.supportsStoredProcedures());
        System.out.println("Multiple result sets: " +
                m.supportsMultipleResultSets());
        System.out.println("Multiple open results: " +
                m.supportsMultipleOpenResults());
        System.out.println("REF_CURSOR: " +
                m.supportsRefCursors());
    }
}
```

**Giải nghĩa:**

- `supportsStoredProcedures()`: driver/database tuyên bố hỗ trợ gọi thủ tục.
- `supportsMultipleResultSets()`: có thể nhận nhiều `ResultSet` từ **một `execute()`**.
- `supportsMultipleOpenResults()`: có thể giữ nhiều `ResultSet` của một lời gọi mở đồng thời; **khác** với khả năng đọc nhiều `ResultSet` *tuần tự*.
- `supportsRefCursors()`: báo hỗ trợ `REF_CURSOR` theo JDBC. Giá trị `false` hoặc `SQLFeatureNotSupportedException` có thể khiến bạn phải chọn chiến lược khác; một số đường gọi kiểu riêng của nhà cung cấp vẫn có thể hoạt động dù chuẩn JDBC không được driver công bố đầy đủ.
- `DatabaseMetaData.getProcedureColumns(...)`, `getProcedures(...)` và các metadata tương ứng cho function có thể hỗ trợ tìm chữ ký, nhưng tên, schema, overload và kiểu `OUT` không phải lúc nào được driver trả đúng đủ. Với trường hợp đó, xác minh trực tiếp trong catalog DB và khai báo rõ trong `SimpleJdbcCall`.

**Metadata chỉ là bước sàng lọc.** Hãy chạy kiểm thử tích hợp với đúng **phiên bản DBMS + JDBC driver + Spring Framework** sử dụng trong production; cập nhật driver có thể thay đổi cách báo update count, tên OUT, tự động load cursor và thứ tự kết quả. Không viết code giả định tất cả DBMS trả nhiều `ResultSet` cùng một cách.

## 7. Quản lý transaction, tài nguyên và bộ nhớ khi đọc kết quả

**Transaction và vòng đời cursor.** `ResultSet` thường phụ thuộc vào `Statement` và `Connection` sinh ra nó. Đọc mọi hàng bên trong `try-with-resources` hoặc callback của Spring; đừng trả thẳng một `ResultSet` từ DAO rồi đóng connection. Một số cursor phía server yêu cầu transaction vẫn mở và có thể bị đóng khi commit tùy holdability.

**Khối lượng dữ liệu.** `SimpleJdbcCall` với `RowMapper` tích lũy kết quả thành `List` cho từng tập. Với dữ liệu lớn, có thể dùng `JdbcTemplate.execute(..., CallableStatementCallback<T>)` và xử lý từng hàng (ghi sang file, đưa qua consumer, tính tổng) khi `ResultSet` còn mở; kiểm tra `fetchSize` và cách driver tải hàng. Nếu driver đã nạp toàn bộ cursor client-side, tự viết vòng lặp cũng không giải quyết bộ nhớ.

**Nhãn/kiểu cột.** Mapper phải dùng chính xác tên cột/alias được thủ tục trả. Hai tập có schema khác nhau cần hai mapper khác nhau; đừng giả định `getInt` cho cột có thể `NULL` nếu không kiểm tra `rs.wasNull()`. Với `OUT INTEGER`, sau `call.getInt(index)` phải gọi `call.wasNull()` ngay để phân biệt `0` với SQL `NULL`.

**Bảo mật và transaction:** người dùng DB chỉ cần quyền gọi thủ tục và quyền cần thiết; truyền giá trị qua `?`/bind parameters, không ghép chuỗi từ input để tạo lệnh call. Nếu thủ tục vừa cập nhật vừa trả dữ liệu, phải xác định transaction isolation, commit/rollback, retry và khả năng chịu lặp; `getMoreResults` không tự commit.

**Lỗi và trạng thái:** `SQLException` có `getSQLState()` và `getErrorCode()` để hỗ trợ phân tích nguyên nhân. Ở một số driver, lỗi ở phần kết quả sau chỉ lộ ra khi bạn gọi `getMoreResults()` hoặc đọc `ResultSet.next()`; do đó, dừng ngay sau tập đầu tiên có thể bỏ sót lỗi. Spring chuyển lỗi JDBC thành `DataAccessException`. Đừng che giấu lỗi bằng cách bỏ qua các tập chưa xử lý hoặc bắt rồi trả danh sách rỗng.

## 8. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `if (!call.execute()) return;` | `false` có thể là update count, kết quả tiếp theo vẫn còn | Dùng vòng lặp kết hợp `getUpdateCount()` và `getMoreResults()` |
| `while (call.getMoreResults())` là toàn bộ thuật toán | Bỏ qua update count xen giữa; dễ dừng trước result set tiếp | Lặp tới khi **không có result set và count = -1** |
| Đọc OUT ngay sau `execute()` | Một số driver chỉ cấp OUT đầy đủ khi đã tiêu thụ mọi kết quả; có thể mất result set chưa đọc | Xử lý toàn bộ result set/count trước |
| Nhầm `OUT` với `ResultSet` đầu tiên | OUT là tham số có tên/vị trí, còn result set trực tiếp đi theo dòng JDBC | Phân biệt cơ chế `registerOutParameter` và `getResultSet` |
| Khai báo sai tên hoặc thứ tự `returningResultSet` | Driver không gắn tên cho các tập trả trực tiếp | Khai báo mapper **theo thứ tự thực tế** |
| Dùng `Types.REF_CURSOR` với mọi DB | Driver có thể chỉ hỗ trợ `Types.OTHER` hoặc kiểu riêng | Dựa vào hướng dẫn driver và kiểm thử tích hợp |
| Commit/đóng connection trước khi đọc cursor | Cursor phụ thuộc transaction/connection | Đọc trong transaction và đóng đúng thứ tự |
| Nghĩ cursor luôn streaming | Driver có thể đệm toàn bộ dữ liệu | Đo heap, thử đường streaming thực sự |
| Coi tên OUT trong `Map` luôn đúng hoa/thường | Metadata/driver đổi kiểu chữ | `setResultsMapCaseInsensitive(true)` nếu phù hợp |
| Dùng `executeQuery()` cho thủ tục có nhiều kết quả | Chỉ nhận một `ResultSet` hoặc không phù hợp với update count/OUT | Dùng `execute()` và duyệt đủ chuỗi kết quả |
| Không đọc lệnh phát lỗi ở result set sau | Lỗi có thể chỉ ném khi chuyển kết quả/đọc hàng | Tiêu thụ đầy đủ khi hợp đồng thủ tục yêu cầu |

## 9. Kiểm thử tích hợp và checklist

Hãy chuẩn bị các thủ tục kiểm thử cụ thể trên **DB/driver thật**:

1. **Chỉ OUT, không result set:** bảo đảm thuật toán kết thúc đúng và giá trị OUT đọc được.
2. **Hai result set liên tiếp:** kiểm tra thứ tự, tên cột/alias và mapper tương ứng.
3. **Update count xen giữa hai result set** (kể cả count bằng `0`): chứng minh vòng lặp không dừng sớm.
4. **OUT = NULL:** phân biệt với số `0`; cả raw `wasNull()` và `Map` Spring.
5. **Thủ tục có thêm một result set:** kiểm tra hợp đồng có cho phép tập bổ sung; cảnh báo khi thứ tự thay đổi.
6. **REF_CURSOR:** xác minh kiểu đăng ký `OUT`, kiểu đối tượng `getObject`, khả năng đọc trong transaction và bộ nhớ với dữ liệu lớn.
7. **Đường lỗi:** lỗi SQL ở kết quả thứ hai, thiếu quyền `EXECUTE`, tham số sai kiểu, timeout, rollback.
8. **Metadata thực tế:** chạy `supportsMultipleResultSets`, `supportsRefCursors`, kiểm tra tên `OUT` và cấu hình `SimpleJdbcCall` trên đúng driver triển khai.

**Checklist áp dụng:**

- [ ] Ghi rõ chữ ký stored procedure/function: `IN`, `OUT`, `INOUT`, return value, result set trực tiếp và cursor.
- [ ] Biết rõ DBMS, JDBC driver/version và các cờ tính năng quan trọng.
- [ ] Dùng `execute()` và duyệt đến đúng điều kiện kết thúc, không coi `false` là hết kết quả.
- [ ] Đọc đủ result set/update count trước OUT; kiểm tra SQL `NULL`.
- [ ] Với `SimpleJdbcCall`, tên cursor OUT đúng và thứ tự mapper cho các result set trực tiếp đúng.
- [ ] Quản lý connection/transaction và đóng cursor đúng thời điểm.
- [ ] Kiểm soát bộ nhớ khi mapper thành `List`; đo thực tế thay vì tin rằng cursor luôn streaming.
- [ ] Kiểm thử end-to-end với driver mục tiêu, nhất là lỗi chỉ phát sinh khi đọc kết quả sau.

**Ghi nhớ:** để đọc đúng một thủ tục/hàm trả nhiều thứ, cần biết **kênh nào phát kết quả gì**, **thứ tự tiêu thụ** và **giới hạn của driver**. `SimpleJdbcCall` giảm mã gán tham số/mapping, nhưng hợp đồng của thủ tục và khả năng JDBC driver vẫn là nguồn sự thật cuối cùng.

### Tài liệu tham khảo chính thức

- Spring Framework – `SimpleJdbcCall`, OUT parameters và `returningResultSet`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html
- Spring Framework – `JdbcTemplate` và callback JDBC: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Java SE 17 – `CallableStatement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/CallableStatement.html
- Java SE 17 – `Statement.getMoreResults`/`getUpdateCount`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
- Java SE 17 – `DatabaseMetaData`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html
- Microsoft JDBC Driver for SQL Server – nhiều `ResultSet`: https://learn.microsoft.com/en-us/sql/connect/jdbc/using-multiple-result-sets
- PostgreSQL JDBC – gọi procedure/function và `refcursor`: https://jdbc.postgresql.org/documentation/callproc/
