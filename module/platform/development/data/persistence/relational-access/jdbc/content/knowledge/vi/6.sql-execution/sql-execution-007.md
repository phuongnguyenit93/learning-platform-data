# Thực thi DDL và kiểm tra ảnh hưởng đến giao dịch theo hệ quản trị

Trong chương **Thực thi SQL**, một câu hỏi dễ gây nhầm lẫn là: **nếu ứng dụng gọi `Connection.setAutoCommit(false)`, thực thi `CREATE TABLE` hoặc `ALTER TABLE` rồi gọi `rollback()`, thay đổi cấu trúc cơ sở dữ liệu có được hoàn tác không?** Câu trả lời phụ thuộc vào hệ quản trị cơ sở dữ liệu (DBMS), lệnh DDL cụ thể và cấu hình phiên kết nối.

**JDBC (Java Database Connectivity)** là API Java để truy cập cơ sở dữ liệu quan hệ. JDBC cho phép gửi các câu lệnh định nghĩa cấu trúc qua `Statement` và `Connection`, nhưng **không áp đặt một hành vi transaction giống nhau cho DDL của tất cả DBMS**. Vì vậy, cần hiểu rõ implicit commit, khả năng rollback của DDL, metadata do driver công bố và phương pháp kiểm thử trên máy chủ mục tiêu trước khi thiết kế migration hoặc thay đổi schema.

## 1. DDL là gì, và vì sao tác động đến giao dịch?

**DDL (Data Definition Language)** là nhóm câu SQL định nghĩa hoặc thay đổi cấu trúc dữ liệu. Những lệnh thông dụng:

| Lệnh | Mục đích | Ví dụ |
|---|---|---|
| `CREATE TABLE` | Tạo bảng | `CREATE TABLE ...` |
| `ALTER TABLE` | Thêm, sửa hoặc xóa cột/ràng buộc | `ALTER TABLE ... ADD ...` |
| `DROP TABLE` | Xóa bảng cùng định nghĩa của nó | `DROP TABLE ...` |
| `CREATE INDEX` | Tạo chỉ mục | `CREATE INDEX ... ON ...` |
| `DROP INDEX` | Xóa chỉ mục | Cú pháp tùy DBMS |
| `CREATE VIEW` / `DROP VIEW` | Tạo/xóa view | `CREATE VIEW ... AS SELECT ...` |

Ví dụ DDL:

```sql
CREATE TABLE inventory_items (
    item_id INTEGER PRIMARY KEY,
    quantity INTEGER NOT NULL
);

ALTER TABLE inventory_items ADD note VARCHAR(100);
```

Ngược lại, **DML (Data Manipulation Language)** thường nói đến `INSERT`, `UPDATE` và `DELETE`, tức các thao tác thay đổi dòng dữ liệu. DDL có thể thay đổi *schema*, quyền tham chiếu, chỉ mục hoặc các tài nguyên được DBMS quản lý, nên một số hệ quản trị áp dụng quy tắc commit khác với DML.

Một thay đổi DDL không chỉ tác động tới ứng dụng chạy lệnh: nó có thể khiến truy vấn đang chạy phải chờ khóa metadata, làm thay đổi cách trình tối ưu hóa chọn kế hoạch thực thi, hoặc khiến ứng dụng khác không còn tìm thấy cột/bảng như trước.

## 2. Ba khái niệm phải phân biệt: commit, rollback và atomic DDL

**Transaction** là đơn vị công việc mà DBMS xác nhận bằng `COMMIT` hoặc hoàn tác bằng `ROLLBACK` theo khả năng hỗ trợ của hệ quản trị. Với JDBC, một luồng thao tác DML thông thường:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (Statement statement = connection.createStatement()) {
        statement.executeUpdate(
                "UPDATE inventory_items SET quantity = quantity + 1 WHERE item_id = 1");
    }

    connection.commit();
}
```

Đoạn mã trên chỉ minh họa đường thành công; mã sản xuất cần rollback khi có lỗi, quản lý cấu hình kết nối và đóng tài nguyên. Khi thêm DDL vào cùng transaction, cần xét:

1. **Transactional DDL**: DDL được thực thi như một phần của transaction, có thể được rollback cùng các thao tác trước đó nếu DBMS/lệnh hỗ trợ.
2. **Implicit commit**: DBMS có thể tự commit khi thực hiện DDL, kể cả khi phía Java đã gọi `setAutoCommit(false)`. Một số DBMS commit **trước** khi xử lý DDL, một số trường hợp còn commit sau khi DDL thành công.
3. **Atomic DDL**: một thao tác DDL được bảo đảm nhất quán khi hoàn tất hoặc khi máy chủ gặp sự cố; điều này **không đồng nghĩa** người dùng có thể gọi `ROLLBACK` để hoàn tác DDL cùng một transaction DML.

Ví dụ, một hệ quản trị có thể cung cấp **atomic DDL** để khôi phục trạng thái nhất quán sau crash nhưng vẫn khiến `ALTER TABLE` kết thúc một transaction và không thể rollback bằng `Connection.rollback()`. Không được dùng hai khái niệm này thay thế nhau.

### 2.1. Tắt auto-commit có đủ không?

`connection.setAutoCommit(false)` yêu cầu JDBC quản lý các transaction thủ công. Lệnh này là điều kiện cần để nhóm nhiều câu DML vào một transaction, nhưng **không thể ghi đè quy tắc implicit commit do DBMS thực hiện khi gặp DDL**.

Đặc biệt, bật lại auto-commit từ `false` sang `true` có thể khiến transaction hiện tại được commit theo hợp đồng JDBC. Bởi vậy, không gọi `setAutoCommit(true)` trước khi xác nhận giao dịch đã kết thúc bằng `commit()` hoặc `rollback()` thành công.

## 3. Hành vi DDL theo các DBMS phổ biến

Bảng dưới mô tả **xu hướng điển hình**, không phải cam kết cho mọi lệnh, phiên bản hoặc driver. Các lệnh như tạo cơ sở dữ liệu, thay đổi một số thuộc tính cấp server, thao tác index đồng thời và DDL trên đối tượng đặc biệt có thể có ngoại lệ.

| Hệ quản trị | DDL trong transaction thủ công | Điều cần kiểm tra |
|---|---|---|
| **PostgreSQL** | Nhiều lệnh `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` thông thường có thể được rollback trong transaction | `CREATE DATABASE` và `CREATE INDEX CONCURRENTLY` không được thực thi trong một transaction block; kiểm tra yêu cầu của từng lệnh |
| **MySQL (InnoDB)** | Nhiều lệnh DDL thường gây implicit commit, nên `rollback()` không hoàn tác thay đổi schema đã thành công | Không nhầm atomic DDL của MySQL với transactional DDL; kiểm tra các trường hợp đặc biệt như bảng temporary |
| **Oracle Database** | Nhiều lệnh DDL thực hiện implicit commit trước, và commit sau khi DDL thành công | Một DDL lỗi vẫn có thể khiến DML trước đó đã được commit; kiểm tra loại DDL và trạng thái transaction |
| **Microsoft SQL Server** | Nhiều thao tác DDL thông thường hỗ trợ transaction và rollback | Một số thao tác, như thay đổi thuộc tính cấp database hoặc thao tác đặc thù, bị hạn chế trong explicit transaction |
| **SQLite** | DDL thông thường có thể rollback khi nằm trong explicit transaction | `VACUUM` có ràng buộc riêng và không được chạy trong một transaction đang hoạt động |
| **H2 và DBMS khác** | Thay đổi theo từng câu lệnh và phiên bản | Đọc tài liệu và thử nghiệm đúng câu DDL thực tế |

### 3.1. PostgreSQL: nhiều DDL có thể rollback

Một ví dụ minh họa khi chạy trong PostgreSQL:

```sql
BEGIN;

CREATE TABLE demo_schema_rollback (
    id INTEGER PRIMARY KEY
);

ROLLBACK;

-- Bảng vừa tạo không tồn tại sau khi rollback.
```

Điểm mạnh là có thể tổ chức một số thay đổi schema thành một đơn vị transaction. Tuy nhiên, không suy ra rằng **mọi** thao tác DDL hoặc công cụ migration đều có thể nằm trong transaction. Ví dụ `CREATE INDEX CONCURRENTLY` được thiết kế để giảm mức khóa khi tạo index và có quy tắc không được chạy trong transaction block.

Nếu một câu SQL trong transaction PostgreSQL gặp lỗi, transaction có thể chuyển sang trạng thái lỗi và từ chối các lệnh tiếp theo cho đến khi rollback (hoặc xử lý bằng savepoint phù hợp). Điều này cần được xét khi ứng dụng thử nhiều câu DDL liên tiếp.

### 3.2. MySQL: implicit commit với nhiều DDL

Giả sử bảng `orders` đã có sẵn và sử dụng engine hỗ trợ transaction:

```sql
START TRANSACTION;

INSERT INTO orders (order_id, status) VALUES (101, 'NEW');

-- Nhiều thao tác ALTER TABLE của MySQL thực hiện implicit commit.
ALTER TABLE orders ADD COLUMN internal_note VARCHAR(100);

ROLLBACK;
```

Tùy tình huống và cú pháp thực tế, `ALTER TABLE` có thể **commit thay đổi INSERT trước đó**, đồng thời thay đổi schema tồn tại sau `ROLLBACK`. Do đó, tránh dùng câu DDL ở giữa transaction DML nếu nghiệp vụ kỳ vọng toàn bộ có thể rollback.

Một ngoại lệ cần biết: các thao tác với **temporary table** như `CREATE TEMPORARY TABLE` có thể không gây implicit commit, nhưng thao tác tạo/xóa bảng tạm cũng không nhất thiết rollback được. Điều này cho thấy “không implicit commit” và “có thể rollback” là hai kết luận khác nhau.

### 3.3. Oracle: DDL có thể commit cả phần việc trước nó

Oracle Database thường thực hiện implicit commit trước nhiều câu DDL; khi DDL thành công, hệ thống còn commit sau thao tác đó. Vì vậy:

```sql
-- Ví dụ khái niệm trên Oracle, chỉ chạy ở schema thử nghiệm.
INSERT INTO audit_example (id) VALUES (10);

ALTER TABLE audit_example ADD note VARCHAR2(50);

ROLLBACK;
```

Nếu `audit_example` tồn tại và `ALTER TABLE` được thực thi như DDL thông thường, thay đổi `INSERT` trước DDL có thể đã được commit, và `ROLLBACK` phía sau không còn khả năng hủy dòng đó. Tùy trường hợp, ngay cả DDL thất bại cũng không khôi phục được transaction DML đã bị commit trước đó.

Không viết logic “thử ALTER, nếu lỗi thì rollback toàn bộ DML” như một bảo đảm trên Oracle.

### 3.4. SQL Server và SQLite: thường có thể rollback, nhưng vẫn có ngoại lệ

Với nhiều thao tác bảng thông thường, SQL Server và SQLite cho phép đặt DDL trong explicit transaction và rollback:

```sql
-- Chỉ mô tả ý tưởng; cú pháp BEGIN/transaction cụ thể phụ thuộc DBMS.
BEGIN TRANSACTION;

ALTER TABLE sample_items ADD extra_code INTEGER;

ROLLBACK;
```

Tuy vậy, một số lệnh quản trị cơ sở dữ liệu, công việc bảo trì hoặc thay đổi cấp server không cho phép chạy theo cách này. Luôn tra hỗ trợ của **đúng lệnh DDL** trên **đúng phiên bản**.

## 4. Thực thi DDL trong Java JDBC

JDBC có các phương thức như `Statement.execute(String)`, `executeUpdate(String)` và `executeLargeUpdate(String)`. DDL là câu SQL không trả về tập dòng thông thường; `Statement.execute(...)` là lựa chọn tổng quát khi chưa muốn giả định loại kết quả của SQL.

### 4.1. Ví dụ gửi CREATE TABLE

```java
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

public final class DdlExample {
    public static void createProbeTable(DataSource dataSource)
            throws SQLException {

        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement()) {

            // Chỉ chạy trên schema thử nghiệm do ứng dụng sở hữu.
            statement.execute(
                    "CREATE TABLE ddl_probe_example (id INTEGER PRIMARY KEY)");
        }
    }
}
```

Ví dụ giả định `DataSource` đã được cấu hình và bảng `ddl_probe_example` chưa tồn tại. Trên các DBMS hỗ trợ, có thể dùng `executeUpdate(...)` cho DDL; giá trị trả về không nên được hiểu là “số dòng dữ liệu bị thay đổi” theo cùng nghĩa với `UPDATE`/`DELETE`. Muốn biết bảng có thực sự tồn tại, cần kiểm tra metadata hoặc truy vấn phù hợp.

### 4.2. Vì sao không dùng PreparedStatement để bind tên bảng?

`PreparedStatement` dùng `?` để bind **giá trị**, không dùng để thay tên bảng, tên cột hoặc từ khóa SQL:

```java
// Không hợp lệ: placeholder không đại diện cho tên bảng.
// PreparedStatement bad = connection.prepareStatement("CREATE TABLE ? (...)");

// Với bài kiểm tra, dùng tên bảng do ứng dụng tự sinh và kiểm soát.
String tableName = "ddl_probe_" + "a1b2c3d4";
String ddl = "CREATE TABLE " + tableName + " (id INTEGER PRIMARY KEY)";
```

Khi phải xây SQL động cho định danh, ứng dụng cần **whitelist định danh, kiểm tra quy tắc tên của DBMS và quote định danh bằng cơ chế phù hợp**. Không nối trực tiếp tên bảng/cột do người dùng nhập vào câu DDL, vì có thể tạo SQL injection hoặc thao tác nhầm đối tượng.

## 5. Kiểm tra khả năng giao dịch DDL bằng DatabaseMetaData

JDBC cung cấp `DatabaseMetaData` để hỏi driver về khả năng transaction. Đây là điểm bắt đầu hữu ích **trước khi thử một lệnh DDL**:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DdlTransactionCapabilities {
    public static void print(DataSource dataSource) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();

            System.out.println("DBMS: "
                    + meta.getDatabaseProductName() + " "
                    + meta.getDatabaseProductVersion());
            System.out.println("Driver: " + meta.getDriverName()
                    + " " + meta.getDriverVersion());

            System.out.println("supportsTransactions: "
                    + meta.supportsTransactions());
            System.out.println("supportsDataDefinitionAndDataManipulationTransactions: "
                    + meta.supportsDataDefinitionAndDataManipulationTransactions());
            System.out.println("supportsDataManipulationTransactionsOnly: "
                    + meta.supportsDataManipulationTransactionsOnly());
            System.out.println("dataDefinitionCausesTransactionCommit: "
                    + meta.dataDefinitionCausesTransactionCommit());
            System.out.println("dataDefinitionIgnoredInTransactions: "
                    + meta.dataDefinitionIgnoredInTransactions());
        }
    }
}
```

Ý nghĩa các phương thức:

| Phương thức | Câu hỏi driver trả lời |
|---|---|
| `supportsTransactions()` | DBMS có hỗ trợ transaction nói chung không? |
| `supportsDataDefinitionAndDataManipulationTransactions()` | DBMS có hỗ trợ cả DDL lẫn DML trong transaction không? |
| `supportsDataManipulationTransactionsOnly()` | Chỉ DML được hỗ trợ trong transaction, còn DDL không theo cùng mô hình? |
| `dataDefinitionCausesTransactionCommit()` | DDL được thực thi trong transaction có khiến transaction commit không? |
| `dataDefinitionIgnoredInTransactions()` | DDL trong transaction có bị DBMS bỏ qua không? |

Các phương thức trên mô tả khả năng **driver công bố**. Không suy ra rằng một giá trị `true` có nghĩa **mọi** câu DDL đều rollback được, hoặc một giá trị `false` đảm bảo mọi thao tác DDL đều không gây commit. Cơ sở dữ liệu có thể phân biệt `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX`, DDL đối tượng tạm và các thao tác cấp database. Nên kiểm tra trực tiếp bằng một phép thử an toàn cho những DDL mà ứng dụng dự định chạy.

## 6. Phép thử có kiểm soát: DML → DDL → rollback

Muốn xác minh hành vi thực tế trên DBMS, cần tạo **đối tượng thử riêng**, thực hiện DML trước DDL, rollback rồi kiểm tra lại **trên một connection mới**. Việc kiểm tra hai loại thay đổi giúp phân biệt implicit commit với transactional DDL.

### 6.1. Chuẩn bị kịch bản và kết quả kỳ vọng

Chạy trên cơ sở dữ liệu/schema thử nghiệm, tài khoản chỉ có quyền trên những đối tượng dùng cho bài tập:

1. Tạo bảng `ddl_probe_<mã>` riêng với cột `id`, rồi commit baseline bằng auto-commit.
2. Mở **connection khác**, gọi `setAutoCommit(false)`.
3. `INSERT` một dòng có `id = 1` vào bảng thử.
4. `ALTER TABLE` để thêm cột `extra_flag`.
5. Gọi `rollback()`.
6. Mở **connection mới**, đếm dòng `id = 1` và kiểm tra sự tồn tại của `extra_flag`.
7. Dọn đúng bảng thử do chương trình vừa tạo.

```text
                  Bảng thử đã tạo và commit trước
                              |
                  BEGIN transaction JDBC
                              |
                    INSERT id = 1
                              |
                  ALTER TABLE ADD COLUMN
                              |
                         ROLLBACK
                              |
                 Connection mới kiểm tra:
                   - Dòng id=1 còn?
                   - Cột extra_flag còn?
```

Kết quả thường gặp:

| Quan sát sau rollback | Cách diễn giải |
|---|---|
| Dòng không còn, cột không còn | DML và DDL đều được rollback trong kịch bản thử |
| Dòng còn, cột còn | DDL có thể đã gây implicit commit; cả phần DML trước đó và thay đổi schema được giữ |
| Dòng không còn, cột còn | DBMS có quy tắc DDL/transaction riêng; cần kiểm tra tài liệu và lệnh cụ thể |
| DDL báo lỗi | Chưa thể kết luận từ phép thử; xem cú pháp, quyền, hạn chế transaction và tình trạng kết nối |

Lưu ý: DML có thể đã được commit **trước khi DDL lỗi** ở một số DBMS. Khi thử lỗi DDL, nên kiểm tra trạng thái sau lỗi trong schema thử; không được giả định gọi rollback trong Java luôn khôi phục trạng thái ban đầu.

### 6.2. Chương trình Java kiểm tra thực tế

Ví dụ sau dùng Java 11+, một driver JDBC có trên runtime classpath và ba biến môi trường `JDBC_URL`, `JDBC_USER`, `JDBC_PASSWORD`. Nó chỉ dùng DDL thông thường và tạo tên bảng từ dữ liệu do chương trình sinh. **Không chạy trong production hoặc schema chứa dữ liệu quan trọng**.

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.UUID;

public final class DdlRollbackProbe {
    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Thiếu biến môi trường: " + key);
        }
        return value;
    }

    private static Connection connect(String url, String user, String password)
            throws SQLException {
        return DriverManager.getConnection(url, user, password);
    }

    private static void runExperiment(
            String url, String user, String password, String table)
            throws SQLException {

        try (Connection connection = connect(url, user, password)) {
            boolean originalAutoCommit = connection.getAutoCommit();
            boolean transactionFinished = false;
            connection.setAutoCommit(false);

            try {
                try (Statement statement = connection.createStatement()) {
                    statement.executeUpdate(
                            "INSERT INTO " + table + " (id) VALUES (1)");

                    // Dùng cú pháp ADD thông dụng; DBMS có thể cần điều chỉnh.
                    statement.execute(
                            "ALTER TABLE " + table
                                    + " ADD extra_flag INTEGER");
                }

                // Cố ý rollback để đo khả năng hoàn tác DDL và DML.
                connection.rollback();
                transactionFinished = true;
            } catch (SQLException error) {
                try {
                    connection.rollback();
                    transactionFinished = true;
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            } finally {
                // Chỉ bật lại auto-commit nếu transaction đã kết thúc an toàn.
                if (transactionFinished) {
                    connection.setAutoCommit(originalAutoCommit);
                }
            }
        }
    }

    private static void inspect(
            String url, String user, String password, String table)
            throws SQLException {

        // Dùng connection mới: kiểm tra trạng thái đã nhìn thấy sau rollback.
        try (Connection connection = connect(url, user, password);
             Statement statement = connection.createStatement()) {

            try (ResultSet rows = statement.executeQuery(
                    "SELECT COUNT(*) FROM " + table + " WHERE id = 1")) {
                rows.next();
                System.out.println("Số dòng id=1 còn lại: " + rows.getLong(1));
            }

            // SELECT không trả dòng nào, nhưng ResultSetMetaData vẫn có cột.
            try (ResultSet columns = statement.executeQuery(
                    "SELECT * FROM " + table + " WHERE 1 = 0")) {
                ResultSetMetaData meta = columns.getMetaData();
                boolean extraFlagPresent = false;
                for (int i = 1; i <= meta.getColumnCount(); i++) {
                    if ("extra_flag".equalsIgnoreCase(meta.getColumnName(i))) {
                        extraFlagPresent = true;
                    }
                }
                System.out.println("Cột extra_flag còn lại: "
                        + extraFlagPresent);
            }
        }
    }

    public static void main(String[] args) throws SQLException {
        String url = requireEnv("JDBC_URL");
        String user = requireEnv("JDBC_USER");
        String password = System.getenv("JDBC_PASSWORD");
        if (password == null) {
            throw new IllegalArgumentException("Thiếu JDBC_PASSWORD");
        }

        // Chỉ chứa chữ thường, số và dấu gạch dưới;
        // tên ngắn để tương thích nhiều giới hạn định danh DBMS.
        String table = "ddl_probe_"
                + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        boolean created = false;

        try {
            try (Connection setup = connect(url, user, password);
                 Statement statement = setup.createStatement()) {
                setup.setAutoCommit(true); // Baseline có hiệu lực trước phép thử.
                statement.execute(
                        "CREATE TABLE " + table
                                + " (id INTEGER PRIMARY KEY)");
                created = true;
            }

            runExperiment(url, user, password, table);
            inspect(url, user, password, table);
        } finally {
            // Chỉ xóa đối tượng do chương trình tạo thành công.
            if (created) {
                try (Connection cleanup = connect(url, user, password);
                     Statement statement = cleanup.createStatement()) {
                    cleanup.setAutoCommit(true);
                    statement.execute("DROP TABLE " + table);
                } catch (SQLException cleanupError) {
                    System.err.println(
                            "Không dọn được bảng thử " + table + ": "
                                    + cleanupError.getMessage());
                }
            }
        }
    }
}
```

**Cách đọc phép thử:**

- Nếu chương trình in `Số dòng id=1 còn lại: 0` và `Cột extra_flag còn lại: false`, phép thử cho thấy cả DML lẫn DDL đã được hoàn tác.
- Nếu in `1` và `true`, một cách giải thích phổ biến là DDL đã gây implicit commit, khiến dữ liệu thêm trước nó vẫn tồn tại.
- Nếu `ALTER TABLE` không được phép chạy trong transaction hoặc cú pháp không được hỗ trợ, chương trình ném `SQLException` và không thực hiện bước kiểm tra; cần điều chỉnh phép thử theo DBMS và xem xét dữ liệu có thể đã được commit trước lỗi.
- Nếu cleanup thất bại, thông báo chứa **tên bảng thử cụ thể** để người vận hành dọn bằng quyền thích hợp. Chương trình không tự xóa bất kỳ bảng nào khác.

**Giới hạn của chương trình:** phép thử phù hợp với các DBMS hỗ trợ `CREATE TABLE`, `INSERT`, `ALTER TABLE ... ADD <column> <type>` và `DROP TABLE` theo cú pháp minh họa; có thể cần điều chỉnh cú pháp, quyền, schema hoặc đối tượng thử theo hệ quản trị. Kết quả xác nhận **một thao tác cụ thể trên một phiên bản/cấu hình DBMS**, không phải chứng nhận rằng mọi DDL đều có cùng hành vi.

Tài khoản kiểm thử cần có quyền tạo, thay đổi, xóa bảng trong một schema riêng, tránh dùng tên bảng trùng dữ liệu quan trọng. Không đưa `JDBC_PASSWORD` vào lệnh hoặc log công khai. Khi hoạt động với dịch vụ dữ liệu production, hãy dùng môi trường staging/ephemeral database để tránh tác động cấu trúc và khóa đến người dùng thật.

## 7. Đọc kết quả và xử lý lỗi DDL trong JDBC

### 7.1. execute(), executeUpdate() và update count

`Statement.execute(sql)` trả về `true` khi kết quả đầu tiên là `ResultSet`; với DDL thông thường, kết quả đầu tiên thường không phải tập dữ liệu. `Statement.executeUpdate(sql)` được thiết kế cho DML và các SQL không trả về `ResultSet`, trong đó có một số DDL, nhưng số nguyên trả về của DDL không mang ý nghĩa số dòng cập nhật như `UPDATE`.

```java
try (Statement statement = connection.createStatement()) {
    boolean hasResultSet =
            statement.execute("CREATE TABLE ddl_example (id INTEGER)");

    System.out.println("Có ResultSet: " + hasResultSet);
    System.out.println("Update count: " + statement.getUpdateCount());
}
```

Nếu API trả về số hàng `0` hoặc `-1` tùy cách thực thi, **không sử dụng giá trị đó để kết luận bảng đã tạo hoặc đã rollback thành công**. Để xác minh cấu trúc, kiểm tra `DatabaseMetaData.getTables(...)` / `getColumns(...)` hoặc chạy truy vấn an toàn trên kết nối mới, có chú ý cách viết tên schema/case-sensitive của DBMS.

### 7.2. DDL lỗi có hoàn tác DML trước đó không?

Không thể đưa ra một quy tắc duy nhất. Một số DBMS có thể commit DML trước khi cố chạy DDL; trong trường hợp đó, dù DDL lỗi vì cú pháp hoặc đối tượng đã tồn tại, `rollback()` sau lỗi không hủy được DML đã commit. Ngược lại, trên hệ quản trị với transactional DDL, lỗi có thể khiến transaction phải rollback.

Một mẫu xử lý Java hợp lý:

```java
try {
    // Gửi DDL trong điều kiện đã kiểm tra phù hợp với DBMS.
    statement.execute(ddlSql);
    // Nếu DBMS hỗ trợ transaction cho DDL, commit theo kế hoạch.
    connection.commit();
} catch (SQLException error) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        error.addSuppressed(rollbackError);
    }
    throw error;
}
```

Đây là mẫu **xử lý lỗi JDBC**, **không phải cam kết rollback có hiệu lực với mọi DDL**. Với DBMS có implicit commit, hành vi của chính máy chủ quyết định thay đổi nào đã được xác nhận.

Khi phân tích lỗi, đọc `SQLException.getSQLState()`, `getErrorCode()` và thông báo theo tài liệu nhà cung cấp. Không ghi mật khẩu, token hoặc thông tin nhạy cảm trong log lỗi.

### 7.3. Metadata không thay thế integration test

Một driver có thể báo hỗ trợ transaction cho DDL ở mức tổng quát nhưng một lệnh cụ thể vẫn bị hạn chế. Hành vi còn phụ thuộc vào quyền, engine bảng, loại đối tượng, chế độ hoạt động, phiên bản server và công cụ migration.

Vì vậy, xác minh tốt nhất thường gồm **ba lớp chứng cứ**: metadata JDBC, tài liệu DBMS tương ứng với phiên bản đang chạy, và phép thử thực tế trên schema kiểm thử.

## 8. Thiết kế migration và thay đổi schema an toàn

Một migration có thể thêm cột, tạo index, chuyển dữ liệu rồi thay đổi ràng buộc. Cần biết chính xác câu lệnh nào commit và lệnh nào có thể rollback:

```text
Migration:
  1. ALTER TABLE thêm cột
  2. UPDATE dữ liệu chuyển đổi
  3. CREATE INDEX
  4. ALTER TABLE thêm ràng buộc

Hãy xác minh ranh giới transaction cho từng bước theo DBMS.
```

Những nguyên tắc quan trọng:

1. **Xác định DBMS và phiên bản thực tế.** Cùng một script có thể rollback toàn bộ ở hệ quản trị này nhưng commit từng mốc ở hệ khác.
2. **Tách giao dịch nghiệp vụ khỏi DDL khi cần.** Trên hệ có implicit commit, không đặt DDL giữa một transaction DML mà nghiệp vụ yêu cầu tính nguyên tử.
3. **Đặt tên migration và ghi lịch sử chạy.** Dùng công cụ như Flyway/Liquibase theo cấu hình được hỗ trợ, không giả định công cụ có thể làm DDL transactional trên DBMS vốn không hỗ trợ.
4. **Chuẩn bị phương án tiến/lùi.** Với DDL không rollback được, cần lập migration sửa đổi hoặc thao tác bù (*compensating migration*) để khôi phục schema, thường phải có backup và quy trình được phê duyệt.
5. **Giảm thời gian khóa.** DDL có thể giữ metadata/schema locks. Thử trên dữ liệu gần thực tế, ước lượng thời gian và có cửa sổ triển khai phù hợp.
6. **Kiểm tra tương thích ứng dụng.** Thêm/xóa/đổi tên cột có thể tác động đến phiên bản ứng dụng đang hoạt động. Cân nhắc cách triển khai mở rộng schema trước rồi mới thu hẹp.
7. **Không dùng tên định danh từ đầu vào tùy ý.** Với DDL sinh động, whitelist schema/bảng/cột và xác minh quyền để tránh SQL injection hoặc thao tác nhầm tài nguyên.
8. **Có bằng chứng sau chạy.** Kiểm tra bảng, cột, index, ràng buộc bằng metadata và truy vấn đơn giản; không chỉ dựa vào việc một lời gọi JDBC không ném lỗi.

### Lưu ý khi dùng savepoint

`Savepoint` cho phép đánh dấu vị trí rollback bên trong transaction được hỗ trợ, ví dụ:

```java
connection.setAutoCommit(false);
Savepoint beforeChange = connection.setSavepoint("before_schema_change");

try {
    statement.execute(ddlSql);
} catch (SQLException error) {
    connection.rollback(beforeChange);
    throw error;
}
```

**Không dùng mẫu này nếu DBMS có thể implicit commit khi thực thi DDL.** Khi transaction đã bị commit, savepoint có thể không còn hợp lệ; `rollback(beforeChange)` có thể thất bại. Savepoint chỉ có ý nghĩa theo khả năng transaction và hành vi DDL thực tế của DBMS.

## 9. Những ngộ nhận thường gặp

| Ngộ nhận | Kiến thức đúng |
|---|---|
| “`setAutoCommit(false)` làm mọi DDL rollback được.” | Quy tắc implicit commit của DBMS vẫn có hiệu lực. |
| “`CREATE TABLE` và `ALTER TABLE` có hành vi giống nhau ở mọi DBMS.” | Mỗi DBMS và từng loại DDL có quy định riêng. |
| “Atomic DDL đồng nghĩa transactional DDL.” | Atomic DDL có thể bảo đảm khôi phục sau crash nhưng không cho rollback theo yêu cầu của client. |
| “DDL lỗi thì DML trước nó chắc chắn chưa commit.” | Trên DBMS implicit commit trước DDL, DML trước đó có thể đã được xác nhận dù DDL thất bại. |
| “`supportsTransactions() = true` nghĩa là DDL có thể rollback.” | Phương thức này nói về transaction nói chung; cần kiểm tra các phương thức metadata liên quan DDL và chạy thử. |
| “`executeUpdate()` trả 0 tức CREATE thất bại.” | Số dòng tác động không phải cách xác minh cấu trúc sau DDL. |
| “Rollback trên connection cũ là đủ để chứng minh schema không thay đổi.” | Nên xác minh độc lập trên connection khác và đọc metadata/trạng thái thực tế. |
| “Migration tool bảo đảm toàn bộ script atomic ở mọi DBMS.” | Khả năng rollback phụ thuộc máy chủ, câu DDL và cấu hình migration. |

## 10. Bài tập thực hành và tự kiểm tra

**Bài 1.** Vì sao `Connection.setAutoCommit(false)` không đủ để đảm bảo `ALTER TABLE` rollback được trên mọi DBMS?

**Gợi ý đáp án:** JDBC chỉ điều khiển transaction theo hợp đồng kết nối; DBMS có thể thực hiện implicit commit riêng khi xử lý DDL.

**Bài 2.** Đoạn thử nghiệm `INSERT → ALTER TABLE → rollback()` cho kết quả “dòng vẫn còn, cột mới vẫn còn”. Kết luận phù hợp nhất là gì?

**Gợi ý đáp án:** Trong phép thử, thay đổi đã được xác nhận và không bị rollback; hành vi này phù hợp với DBMS gây implicit commit trong quá trình DDL. Cần đối chiếu tài liệu của đúng hệ quản trị.

**Bài 3.** Phương thức `DatabaseMetaData` nào trực tiếp hỏi DDL có gây commit giao dịch không?

**Đáp án:** `dataDefinitionCausesTransactionCommit()`.

**Bài 4.** Có thể dùng `PreparedStatement` với `CREATE TABLE ? (id INTEGER)` và bind tên bảng vào `?` không?

**Đáp án:** Không. Placeholder trong JDBC dùng cho giá trị, không thay định danh SQL. Tên bảng phải do ứng dụng kiểm soát và tạo câu lệnh theo quy tắc định danh DBMS.

**Bài 5.** Vì sao nên mở connection mới để kiểm tra schema sau `rollback()`?

**Gợi ý đáp án:** Việc quan sát từ một phiên độc lập giúp xác nhận trạng thái mà kết nối khác nhìn thấy sau khi transaction kết thúc, giảm nhầm lẫn với trạng thái phiên/cursor còn lưu trong connection thử.

**Bài 6.** Khi nâng phiên bản MySQL và công cụ migration báo “atomic DDL”, có thể bỏ quy trình kiểm thử rollback DDL không?

**Đáp án:** Không. Atomic DDL và DDL có thể rollback theo transaction là hai tính chất khác nhau; cần xem tài liệu và kiểm chứng trên bản máy chủ cụ thể.

**Bài 7.** Một migration chạy tốt trên PostgreSQL nhưng bị commit từng bước khi chuyển sang DBMS khác. Cần thay đổi điều gì?

**Gợi ý đáp án:** Đánh giá lại giao dịch cho từng DDL, tách những bước không thể rollback, thiết kế migration bù/khôi phục và xác minh cấu trúc sau triển khai trên DBMS mới.

## 11. Ghi nhớ

Trong JDBC, **thực thi DDL** là gửi câu SQL định nghĩa schema qua `Statement`/`Connection`; **ảnh hưởng đến giao dịch** lại do DBMS và từng câu DDL quyết định. Hãy ghi nhận tên/phiên bản server bằng `DatabaseMetaData`, hỏi khả năng transaction DDL, đối chiếu tài liệu chính thức và thử `DML → DDL → rollback()` trên bảng riêng. Khi hiểu rõ điểm nào thực sự commit, bạn mới có thể thiết kế migration, xử lý lỗi và khôi phục cơ sở dữ liệu một cách có căn cứ.
