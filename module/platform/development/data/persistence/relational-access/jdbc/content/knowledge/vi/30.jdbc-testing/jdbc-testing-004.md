# Kiểm thử CRUD, khóa sinh và số dòng bị ảnh hưởng trong JDBC

## Mục tiêu học tập

Khi ứng dụng Java dùng **JDBC** để kết nối cơ sở dữ liệu quan hệ qua driver, `DataSource`, `Connection`, `PreparedStatement` và `ResultSet`, một thao tác SQL **không ném ngoại lệ** vẫn chưa đủ để khẳng định nghiệp vụ hoạt động đúng. Ví dụ: lệnh `UPDATE` có thể chạy bình thường nhưng sửa **0 hàng** do khóa không tồn tại; `INSERT` có thể tạo bản ghi nhưng ứng dụng đọc sai **khóa chính do DBMS sinh**; `DELETE` có thể tác động quá nhiều hàng nếu điều kiện `WHERE` thiếu hoặc sai.

Bài thuộc chương **Kiểm thử JDBC** tập trung vào cách kiểm thử đúng **CRUD (Create, Read, Update, Delete)**, **generated keys** và **affected-row counts** bằng các API JDBC tiêu chuẩn. Ta sẽ tách việc một câu lệnh được **thực thi** khỏi việc dữ liệu **thật sự thay đổi**, được **đọc lại chính xác** và cuối cùng được **commit**.

Sau bài, bạn có thể:

- Thiết kế ca kiểm thử tích hợp CRUD có dữ liệu đầu vào, kết quả và bước dọn dẹp rõ ràng.
- Dùng `PreparedStatement.executeUpdate()` và `executeLargeUpdate()` để kiểm tra số dòng ảnh hưởng.
- Lấy khóa được sinh bằng `Statement.RETURN_GENERATED_KEYS` và `PreparedStatement.getGeneratedKeys()`.
- Đọc lại hàng vừa ghi qua `ResultSet` để xác minh trạng thái database, thay vì chỉ tin giá trị trả về.
- Kiểm tra trường hợp **không có hàng**, **trùng khóa**, **cập nhật có điều kiện** và **xóa hai lần**.
- Phân biệt kết quả của `executeBatch()`, `SUCCESS_NO_INFO`, `EXECUTE_FAILED` với một update count thông thường.
- Xây test transaction có rollback, xác minh commit bằng connection độc lập và tránh các giả định không di động giữa DBMS/driver.

## 1. Kiểm thử JDBC cần kiểm tra điều gì?

Một test repository không nên chỉ xác nhận rằng Java gọi đúng tên phương thức. Nó cần kiểm chứng **hợp đồng dữ liệu** trên một database có cấu hình đại diện.

| Thao tác | Lời gọi JDBC | Câu hỏi chính | Bằng chứng nên kiểm tra |
| --- | --- | --- | --- |
| **CREATE** | `executeUpdate()` | Đã thêm đúng hàng chưa? Khóa được sinh là gì? | Update count, `getGeneratedKeys()` và `SELECT` lại bằng khóa |
| **READ** | `executeQuery()` | Hàng và kiểu dữ liệu được ánh xạ đúng chưa? | Giá trị `ResultSet`, số hàng, `NULL`, thứ tự nếu có `ORDER BY` |
| **UPDATE** | `executeUpdate()` | Có sửa đúng hàng đã định, không sửa hàng khác? | Update count, `SELECT` lại, kiểm tra version/điều kiện |
| **DELETE** | `executeUpdate()` | Đã xóa đúng hàng và hàng khác còn nguyên? | Update count và query xác nhận không còn bản ghi |
| **TRANSACTION** | `commit()/rollback()` | Thay đổi đã được xác nhận hay hủy đúng chưa? | Đọc lại trên connection thích hợp, nhất là sau commit |
| **BATCH** | `executeBatch()` | Mỗi phần tử được báo kết quả nào? | Mảng update counts, `BatchUpdateException` và trạng thái transaction |

Ví dụ một test chỉ viết:

```java
repository.updateStatus(42L, "DONE");
// Test kết thúc, không có assertion nào.
```

không chứng minh được rằng hàng `42` tồn tại, rằng `status` đã đổi, hoặc rằng câu SQL không sửa nhầm hàng khác. **Một test tốt có kỳ vọng quan sát được và phép đối soát dữ liệu độc lập với đường ghi**.

### Các tầng kiểm thử nên phối hợp

- **Unit test:** kiểm tra logic Java thuần, nhánh xử lý số dòng ảnh hưởng, exception mapping hoặc SQL builder qua stub/fake khi thích hợp. Nhanh, nhưng thường **không kiểm chứng được** cách driver/DBMS thực thi SQL.
- **Integration test JDBC:** kết nối database thử nghiệm, chạy `INSERT/SELECT/UPDATE/DELETE` thực, kiểm tra khóa sinh, constraint, transaction và kiểu dữ liệu. Đây là tầng quan trọng nhất của chủ đề.
- **End-to-end test:** đi từ API/job qua service/repository tới database, kiểm tra nghiệp vụ và quyền truy cập. Chậm hơn và khó cô lập nguyên nhân lỗi.
- **Contract test trên nhiều DBMS/driver:** dùng khi ứng dụng tuyên bố hỗ trợ nhiều hệ quản trị hoặc nhiều phiên bản driver; cùng một hợp đồng có thể cần adapter/schema khác nhau.

Không dùng mock `ResultSet` để kết luận rằng database thật hỗ trợ `RETURN_GENERATED_KEYS` hoặc báo affected rows giống giả định: mock chỉ trả những gì bạn đã lập trình cho nó.

## 2. Chuẩn bị schema và fixture dành riêng cho test

Giả sử repository quản lý bảng `jdbc_test_accounts` với các cột:

| Cột | Vai trò | Điều kiện mong đợi |
| --- | --- | --- |
| `account_id` | Khóa chính do DBMS sinh | `BIGINT` hoặc kiểu số tương đương; uniqueness |
| `external_ref` | Mã nghiệp vụ định danh test | Chuỗi không null và duy nhất |
| `display_name` | Dữ liệu cần đọc/sửa | Chuỗi có thể chứa Unicode, dấu nháy |
| `version` | Phiên bản dùng cho optimistic locking | Số nguyên không null, ban đầu 0 |

Một khai báo SQL **mang tính ý tưởng**:

```sql
-- DDL chỉ minh họa, phải điều chỉnh cú pháp IDENTITY/SEQUENCE
-- theo DBMS dùng trong integration test.
CREATE TABLE jdbc_test_accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_ref VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
```

Cú pháp tạo ID được sinh khác nhau giữa PostgreSQL, MySQL, Oracle, SQL Server và những DBMS khác. Không giả định toàn bộ các hệ thống đều nhận chính xác đoạn DDL trên. Test cần có **migration dành cho môi trường thử nghiệm** đã được chạy và xác nhận trước.

**Không thực hiện DDL bên trong transaction rollback của từng test** nếu chưa kiểm tra DBMS: một số lệnh DDL có thể commit ngầm hoặc không hỗ trợ rollback. Tạo schema ở bước setup riêng, còn dữ liệu test được tạo và dọn trong phạm vi kiểm thử.

### Yêu cầu với môi trường test

1. Sử dụng **database/schema dành riêng**; không chạy test xóa dữ liệu trên production.
2. Cấu hình `DataSource` và credential ngoài mã nguồn, cấp quyền tối thiểu cần thiết.
3. Mỗi ca test tạo `external_ref` độc nhất, ví dụ `"it-" + UUID.randomUUID()`.
4. Biết chính xác trạng thái transaction, isolation và `autoCommit`.
5. Không phụ thuộc số lượng ID sequence/identity phải liên tiếp.
6. Nếu chạy song song, không dùng chung hàng cố định mà nhiều test cùng sửa trừ khi đang kiểm thử concurrency có chủ đích.
7. Khi một test đã commit dữ liệu, phải có chiến lược cleanup độc lập và xử lý lỗi cleanup.

**Không dùng `SELECT MAX(account_id)` để tìm khóa của lần INSERT vừa chạy.** Một worker khác có thể chèn hàng sau bạn. Hơn nữa, một hàng không được commit vẫn có thể đã được cấp sequence/identity ID; giá trị lớn nhất không nói lên chủ sở hữu hay trạng thái commit. Dùng `getGeneratedKeys()` từ **chính PreparedStatement vừa thực thi** hoặc cơ chế khóa sinh riêng đã được DBMS/driver xác nhận.

## 3. Hiểu đúng số dòng bị ảnh hưởng

Với DML thông thường, `PreparedStatement.executeUpdate()` trả một `int` mô tả **số dòng được tác động** theo hợp đồng JDBC và cách DBMS/driver báo. Đối với câu lệnh thuộc loại không trả row count, kết quả có thể là `0` theo quy tắc JDBC của thao tác đó.

Ví dụ:

```java
String sql = """
    UPDATE jdbc_test_accounts
       SET display_name = ?
     WHERE account_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "Tên mới");
    ps.setLong(2, accountId);

    int affectedRows = ps.executeUpdate();
    if (affectedRows != 1) {
        throw new SQLException(
            "Dự kiến sửa đúng 1 hàng, thực tế=" + affectedRows
        );
    }
}
```

Các tình huống cần test:

| Giá trị | Diễn giải phổ biến với UPDATE/DELETE có điều kiện | Việc nên làm |
| ---: | --- | --- |
| `0` | Không có hàng khớp điều kiện, hoặc DBMS/driver có ngữ nghĩa update count riêng | Kiểm tra hàng tồn tại, version và cấu hình DBMS |
| `1` | Một hàng được báo là đã bị tác động | Đọc lại để xác minh cột cần thay đổi |
| `> 1` | Nhiều hàng được báo là bị tác động | Kiểm tra điều kiện `WHERE` nếu nghiệp vụ chỉ được sửa một hàng |

**Không so sánh update count một cách máy móc trong mọi loại SQL.** Ví dụ cập nhật một hàng bằng **chính giá trị cũ** có thể được một DBMS/driver báo theo số hàng *matched*, nơi khác theo số hàng *changed*, tùy cấu hình. Câu `UPSERT`/`MERGE`, câu lệnh có trigger, cascade hoặc SQL đặc thù cũng có quy tắc riêng. Với test cần bảo đảm `affectedRows == 1`, hãy chọn dữ liệu đầu vào khiến giá trị **thực sự thay đổi** và ghi rõ tổ hợp DBMS/driver đã xác minh.

### Một số điều update count không nói lên

- `affectedRows == 1` **không tự chứng minh** dữ liệu đã commit khi `autoCommit=false`.
- Nó **không tự chứng minh** trigger hay cascade đã ghi bao nhiêu hàng khác; số hàng báo về thường nói về statement chính theo DBMS/driver.
- Nó **không có nghĩa** giá trị cột đã giống yêu cầu nếu trigger hoặc logic database có thể biến đổi dữ liệu.
- Nó **không thay thế** kiểm tra điều kiện nghiệp vụ, ví dụ tài khoản còn quyền cập nhật hay giao dịch có thể rollback không.

Với số hàng có thể vượt giới hạn `int`, JDBC hỗ trợ `Statement.executeLargeUpdate()` trả `long`. Cần kiểm tra driver có hỗ trợ và dùng khi thực sự cần, thay vì giả định mọi `int` là đủ cho các lệnh tác động hàng tỷ hàng.

## 4. Kiểm thử INSERT và lấy generated key

Thao tác `INSERT` thường cần trả về ID mới để thực hiện bước tiếp theo. JDBC cung cấp hai phần quan trọng:

- Chuẩn bị statement để **yêu cầu driver trả generated keys**.
- Sau khi thực thi, đọc `ResultSet` từ `getGeneratedKeys()`.

Ví dụ:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

static long insertAccount(
        Connection connection, String ref, String displayName)
        throws SQLException {

    String sql = """
        INSERT INTO jdbc_test_accounts(external_ref, display_name, version)
        VALUES (?, ?, 0)
        """;

    try (PreparedStatement ps = connection.prepareStatement(
            sql, Statement.RETURN_GENERATED_KEYS)) {

        ps.setString(1, ref);
        ps.setString(2, displayName);

        int affected = ps.executeUpdate();
        if (affected != 1) {
            throw new SQLException(
                "INSERT không tác động đúng một hàng: " + affected
            );
        }

        try (ResultSet keys = ps.getGeneratedKeys()) {
            if (!keys.next()) {
                throw new SQLException(
                    "Driver không trả generated key cho INSERT"
                );
            }

            long accountId = keys.getLong(1);
            if (keys.wasNull()) {
                throw new SQLException("Generated key là SQL NULL");
            }

            if (keys.next()) {
                throw new SQLException(
                    "INSERT một hàng nhưng driver trả nhiều key rows"
                );
            }
            return accountId;
        }
    }
}
```

### Những yêu cầu trước khi khẳng định test passed

1. Driver phải hỗ trợ generated keys cho **loại statement và cách sinh khóa** đang dùng.
2. Bảng có cột `account_id` được sinh đúng theo schema test.
3. `RETURN_GENERATED_KEYS` phải được truyền khi **tạo PreparedStatement**, trước lúc gọi `executeUpdate()`.
4. `getGeneratedKeys()` phải được đọc sau khi statement đã chạy và khi statement vẫn còn mở.
5. Với mẫu INSERT đúng một hàng và một khóa, kỳ vọng có một key row. Nếu driver trả thêm cột/định dạng riêng, cần xác minh mapping thật của driver.
6. Sau khi lấy key, vẫn phải `SELECT` lại theo ID và mã `external_ref` để chắc chắn đó là hàng vừa tạo.
7. Một ID được trả về **trước commit** chưa chứng minh INSERT đã bền vững; transaction có thể rollback.

Trong ví dụ, `keys.getLong(1)` giả định trường đầu trong generated-key result là `account_id` dạng số. Một số DBMS/driver trả nhiều cột hoặc yêu cầu nêu tên cột khi tạo statement. Nếu cần làm rõ, có thể thử overload:

```java
PreparedStatement ps = connection.prepareStatement(
    sql,
    new String[] { "account_id" }
);
```

Hỗ trợ tên cột và cú pháp identifier vẫn có thể phụ thuộc driver. Một số hệ quản trị có cơ chế SQL `RETURNING`/`OUTPUT` nhưng cú pháp và cách gọi `executeQuery()` khác nhau; không dùng một câu SQL vendor-specific như quy tắc JDBC chung.

### 4.1. Kiểm tra khả năng hỗ trợ từ metadata

`DatabaseMetaData.supportsGetGeneratedKeys()` cho biết khả năng hỗ trợ mà driver công bố:

```java
try (Connection c = dataSource.getConnection()) {
    boolean advertised =
        c.getMetaData().supportsGetGeneratedKeys();

    System.out.println("Generated keys advertised: " + advertised);
}
```

Thông tin này hữu ích khi thiết kế test, nhưng **không thay thế phép thử INSERT thực**. Driver có thể hỗ trợ API chung nhưng chỉ trả key đối với một số loại bảng, cột hoặc câu lệnh. Nếu môi trường không hỗ trợ, test nên báo **khác biệt contract có chủ đích** hoặc dùng đường tương thích đã kiểm chứng, không tự lặng lẽ chuyển sang `SELECT MAX(id)`.

### 4.2. Không kiểm tra ID phải tăng tuần tự

Đừng viết:

```java
// Không portable và dễ thất bại khi có transaction khác/rollback.
assertEquals(previousId + 1, newId);
```

Sequence/identity có thể cấp trước khi commit, có cache và thường không hoàn tác giá trị đã cấp khi transaction rollback. Concurrency, restart database, replication hoặc cách sinh khóa riêng cũng có thể tạo khoảng trống. Test nên kiểm tra **khóa không null, đúng loại mong đợi, truy vấn được hàng chính xác và không bị trùng**, thay vì “ID mới phải bằng ID cũ cộng 1”.

## 5. Ví dụ kiểm thử tích hợp JUnit 5: CRUD và generated key

Đây là một **contract test** dùng JUnit Jupiter và JDBC tiêu chuẩn. Lớp test được khai báo `abstract` để dự án cung cấp `DataSource` của database test phù hợp, tránh đưa URL/password vào bài học. Nếu dùng Java 17+, đoạn mã có thể biên dịch sau khi thêm JUnit Jupiter vào test dependencies và triển khai subclass trả về test `DataSource`.

Giả định schema ở phần 2 đã tồn tại và `version` bắt đầu bằng `0`. Test sử dụng **một transaction thủ công**, thực thi CRUD rồi gọi `rollback()` để không để lại hàng test. Vì mọi lệnh nằm trên cùng connection, nó kiểm tra thay đổi **trước commit**, không phải tính bền vững sau commit.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;

public abstract class JdbcCrudContractTest {

    protected abstract DataSource dataSource();

    record Account(long id, String ref, String name, long version) {}

    @Test
    void insertReadUpdateDeleteAndGeneratedKey() throws SQLException {
        try (Connection c = dataSource().getConnection()) {
            c.setAutoCommit(false);

            try {
                String ref = "jdbc-it-" + UUID.randomUUID();
                long id = insert(c, ref, "Nguyễn O'Neil");

                Account created = find(c, id);
                assertNotNull(created, "Phải đọc được hàng vừa INSERT");
                assertEquals(id, created.id());
                assertEquals(ref, created.ref());
                assertEquals("Nguyễn O'Neil", created.name());
                assertEquals(0L, created.version());

                // Cập nhật có điều kiện theo phiên bản.
                assertEquals(1, updateName(c, id, 0L, "Tên đã sửa"));
                // Phiên bản cũ không được phép cập nhật nữa.
                assertEquals(0, updateName(c, id, 0L, "Ghi đè cũ"));

                Account updated = find(c, id);
                assertNotNull(updated);
                assertEquals("Tên đã sửa", updated.name());
                assertEquals(1L, updated.version());

                assertEquals(1, delete(c, id));
                assertNull(find(c, id));
                assertEquals(0, delete(c, id));

            } finally {
                // Không cần commit fixture test.
                // Nếu rollback lỗi, lỗi đó cần được báo cho runner.
                c.rollback();
            }
        }
    }

    private static long insert(Connection c, String ref, String name)
            throws SQLException {
        String sql = """
            INSERT INTO jdbc_test_accounts
                (external_ref, display_name, version)
            VALUES (?, ?, 0)
            """;

        try (PreparedStatement ps = c.prepareStatement(
                sql, Statement.RETURN_GENERATED_KEYS)) {

            ps.setString(1, ref);
            ps.setString(2, name);
            assertEquals(1, ps.executeUpdate());

            try (ResultSet keys = ps.getGeneratedKeys()) {
                assertTrue(keys.next(), "Phải có generated key");
                long id = keys.getLong(1);
                assertFalse(keys.wasNull(), "Key không được là NULL");
                assertFalse(keys.next(), "INSERT một hàng: chỉ một key row");
                return id;
            }
        }
    }

    private static Account find(Connection c, long id)
            throws SQLException {
        String sql = """
            SELECT account_id, external_ref, display_name, version
              FROM jdbc_test_accounts
             WHERE account_id = ?
            """;

        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return null;
                }

                Account account = new Account(
                    rs.getLong("account_id"),
                    rs.getString("external_ref"),
                    rs.getString("display_name"),
                    rs.getLong("version")
                );
                assertFalse(rs.next(), "Khóa chính chỉ có một hàng");
                return account;
            }
        }
    }

    private static int updateName(Connection c, long id,
                                  long expectedVersion, String name)
            throws SQLException {
        String sql = """
            UPDATE jdbc_test_accounts
               SET display_name = ?, version = version + 1
             WHERE account_id = ? AND version = ?
            """;

        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, name);
            ps.setLong(2, id);
            ps.setLong(3, expectedVersion);
            return ps.executeUpdate();
        }
    }

    private static int delete(Connection c, long id)
            throws SQLException {
        try (PreparedStatement ps = c.prepareStatement(
                "DELETE FROM jdbc_test_accounts WHERE account_id = ?")) {
            ps.setLong(1, id);
            return ps.executeUpdate();
        }
    }
}
```

Để chạy test, dự án phải cung cấp một lớp con, ví dụ:

```java
// Đây là khung tích hợp: TestDbConfig là thành phần cấu hình
// DataSource dành RIÊNG cho database test của dự án.
final class TargetDatabaseCrudIT extends JdbcCrudContractTest {
    @Override
    protected javax.sql.DataSource dataSource() {
        return TestDbConfig.integrationDataSource();
    }
}
```

`TestDbConfig` chỉ là vị trí tích hợp do dự án cần triển khai, **không phải lớp JDBC chuẩn có sẵn**. Nên để nguồn thông tin xác thực ở runtime/test infrastructure, không hard-code trong test. Lớp abstract cho phép chạy cùng contract trên nhiều DBMS khi mỗi subclass trỏ tới một môi trường tương ứng.

### 5.1. Những thứ test này thật sự xác minh

- `INSERT` thành công và update count là `1` cho một bản ghi.
- `getGeneratedKeys()` trả một khóa không null cho lần insert đó.
- `SELECT` bằng ID trả đúng `external_ref` và chuỗi Unicode chứa dấu nháy đơn, cho thấy code dùng binding tham số không bị ảnh hưởng bởi dấu nháy.
- `UPDATE ... WHERE account_id=? AND version=?` trả `1` khi version đúng.
- UPDATE lần hai với version cũ trả `0` và không ghi đè tên đã sửa.
- `DELETE` lần đầu trả `1`, query tiếp theo không thấy hàng, DELETE lần hai trả `0`.
- `rollback()` cuối test giúp không commit fixture.

### 5.2. Những thứ test chưa chứng minh

- Chưa xác minh dữ liệu đã **commit và thấy được từ connection khác**.
- Chưa test lỗi ràng buộc duy nhất, foreign key, `NULL` hoặc transaction isolation.
- Chưa test SQL batch và cách xử lý `BatchUpdateException`.
- Chưa chứng minh logic có an toàn khi hai transaction chạy thật sự đồng thời.
- Chưa kiểm tra việc khóa sinh hoạt động với multi-row INSERT, stored procedure hay các kiểu identity khác.

**Một test tổng hợp CRUD không thay thế những ca kiểm thử chuyên biệt.** Phần tiếp theo mở rộng contract theo từng nguy cơ.

## 6. Kiểm thử rollback và commit bằng connection độc lập

Rollback trong cùng một transaction là cách dọn fixture hữu ích, nhưng để xác minh **bền vững và tính nhìn thấy sau commit**, phải có test riêng.

### 6.1. Test rollback: dữ liệu không còn sau khi rollback

Quy trình:

1. Lấy connection A, `setAutoCommit(false)`.
2. `INSERT` một hàng có `external_ref` duy nhất; đọc lại trên **chính A** để xác minh insert đã thực thi.
3. Gọi `A.rollback()` và đóng A.
4. Mở connection B mới, `SELECT` theo `external_ref`.
5. Kỳ vọng **không có hàng** nếu bảng/engine và thao tác hỗ trợ transaction như contract.

```mermaid
sequenceDiagram
    participant Test as Test runner
    participant A as Connection A
    participant DB as Database
    participant B as Connection B
    Test->>A: setAutoCommit(false)
    A->>DB: INSERT account(ref=X)
    DB-->>A: affectedRows=1; generatedKey
    Test->>A: rollback()
    Test->>B: getConnection()
    B->>DB: SELECT WHERE external_ref=X
    DB-->>B: Không có hàng (mong đợi)
```

**Tại sao cần B?** Một số assertion trên A có thể đọc được thay đổi chưa commit của chính transaction đó. Test đọc bằng connection độc lập **sau rollback** giúp quan sát kết quả đã hủy.

### 6.2. Test commit: dữ liệu thấy được từ connection mới

Quy trình:

1. Mở A với `autoCommit=false`; INSERT một hàng test.
2. Kiểm tra ID và dữ liệu trên A.
3. Gọi `A.commit()`, chờ xác nhận thành công rồi đóng A.
4. Mở B, SELECT theo ID hoặc `external_ref`; phải thấy dữ liệu đúng.
5. Dọn fixture đã commit bằng một transaction cleanup riêng, xác nhận xóa thành công.

**Chú ý:** nếu `commit()` ném `SQLException` do mất kết nối, **không thể khẳng định transaction chắc chắn rollback**. Test cần dùng `external_ref` duy nhất để đối soát từ connection mới. Một ứng dụng thực tế cũng cần idempotency khi retry nghiệp vụ có tác động.

### 6.3. Dọn dữ liệu test đã commit

Nếu test dùng `rollback()` thì việc dọn fixture thường đơn giản. Nhưng test xác nhận commit phải thật sự commit, nên cần cleanup:

```java
String ref = "jdbc-it-" + java.util.UUID.randomUUID();

// ... Transaction thử nghiệm INSERT và COMMIT đã hoàn tất.

try (Connection cleanup = dataSource.getConnection();
     PreparedStatement ps = cleanup.prepareStatement(
         "DELETE FROM jdbc_test_accounts WHERE external_ref = ?")) {
    ps.setString(1, ref);
    ps.executeUpdate();
}
```

Mã trên là **mảnh minh họa**: phải đặt phần cleanup trong `finally` của test commit, kể cả khi assertion thất bại, và bảo đảm connection cleanup sử dụng chính database/schema test. Nếu kiểm thử cần dọn nhiều bảng có quan hệ FK, thực hiện theo thứ tự an toàn hoặc có cơ chế teardown riêng đã được xác minh.

Không chạy `DELETE FROM jdbc_test_accounts` không có `WHERE` trên môi trường có người dùng khác. Dùng prefix/khóa test duy nhất và bảng test riêng để tránh xóa nhầm dữ liệu.

## 7. Test trường hợp 0 hàng, 1 hàng và nhiều hàng

Một bài test thành công không chỉ dùng ID tồn tại. Ít nhất nên có:

| Tình huống | SQL/điều kiện | Kỳ vọng và cách xác minh |
| --- | --- | --- |
| UPDATE đúng một ID | `WHERE account_id=? AND version=?` | `1` và tên/version đổi |
| UPDATE ID không tồn tại | `WHERE account_id=?` với ID đã xác minh không có | `0` và không thay đổi hàng khác |
| UPDATE stale version | ID tồn tại, version đã tăng | `0`, dữ liệu server còn nguyên |
| DELETE một ID tồn tại | `WHERE account_id=?` | `1`, đọc lại không thấy |
| DELETE ID đó lần hai | Cùng statement điều kiện | `0` |
| DELETE sai ID | ID khác được tạo có kiểm soát | Không được xóa hàng đang thử |
| UPDATE nhiều hàng có chủ đích | `WHERE external_ref LIKE ?` hoặc điều kiện đã giới hạn fixture | Số hàng báo phù hợp số hàng đã seed và kết quả đọc lại |
| UPDATE không điều kiện (phản ví dụ) | Không có `WHERE` | Có nguy cơ sửa nhiều bản ghi; test nên phát hiện qua count |

**Tại sao cần kiểm tra nhiều hàng?** Một repository có contract “update đúng một tài khoản” phải coi `affectedRows > 1` là vấn đề nghiêm trọng, không phải thành công tốt hơn. Ngược lại, một job batch cập nhật nhiều bản ghi hợp lệ có thể mong đợi số hàng lớn hơn một, nhưng test phải seed và đếm đúng tập dữ liệu chịu tác động.

Khi test SQL có `LIKE`, `NULL`, Unicode, collation hoặc nhiều schema, tránh giả định mọi DBMS so sánh chuỗi giống nhau. Với một test “số hàng bằng 3”, seed ba hàng có cùng nhóm test bằng ID/ref cụ thể, rồi đối soát chính ba hàng đó; không dựa vào dữ liệu dùng chung của người khác.

## 8. Kiểm thử lỗi ràng buộc: đừng tiếp tục transaction đã lỗi

Một test cần thử **trùng unique key**:

1. Bắt đầu transaction trên connection test.
2. Chèn hàng có `external_ref` duy nhất; xác minh thành công.
3. Thử chèn hàng khác có **cùng `external_ref`**.
4. Kỳ vọng `SQLException` nếu ràng buộc unique có hiệu lực ngay.
5. Rollback transaction và không dùng tiếp connection đó để chạy các assertion SQL không liên quan trước khi hoàn tất rollback.

Ví dụ JUnit:

```java
@Test
void duplicateExternalReferenceIsRejected() throws SQLException {
    try (Connection c = dataSource().getConnection()) {
        c.setAutoCommit(false);
        try {
            String ref = "jdbc-it-" + java.util.UUID.randomUUID();

            insert(c, ref, "Bản đầu");
            assertThrows(SQLException.class,
                () -> insert(c, ref, "Bản trùng"));
        } finally {
            c.rollback();
        }
    }
}
```

Đoạn trên là phương thức **đặt trong lớp `JdbcCrudContractTest` ở phần 5**, dùng helper `insert(...)` và các import đã có. Nó giả định ràng buộc `UNIQUE(external_ref)` được DBMS kiểm tra tại thời điểm INSERT. Nếu ràng buộc **deferrable** và đang được hoãn đến commit, lỗi có thể chỉ xuất hiện lúc commit; phải điều chỉnh kịch bản test theo schema thật.

**Cẩn thận với PostgreSQL và DBMS có quy tắc transaction tương tự:** sau một `SQLException` do lỗi SQL trong transaction, transaction có thể rơi vào trạng thái lỗi cho tới khi rollback. Không tiếp tục query và kỳ vọng nó còn dùng bình thường. Nếu cần thử nhiều lỗi độc lập, dùng **transaction riêng cho mỗi ca** hoặc savepoint đã được kiểm chứng.

### Xem SQLState nhưng không hard-code message

`SQLException.getSQLState()` có thể cho biết nhóm ràng buộc (thường liên quan lớp `23`), và `getErrorCode()` chứa mã vendor. Tuy nhiên, SQLState cụ thể và thông điệp có thể khác theo DBMS, driver và loại constraint.

Một test di động nên tách:

- **Contract chung:** duplicate unique key bị từ chối; không có hàng thứ hai.
- **Contract riêng DBMS:** SQLState/vendor code đúng với loại ràng buộc cụ thể nếu ứng dụng cần phân loại lỗi.
- **Không dùng:** `exception.getMessage().contains("duplicate")` như điều kiện nghiệp vụ chung.

Nếu test chỉ dùng `assertThrows(SQLException.class, ...)`, hãy bảo đảm thao tác INSERT đầu đã thành công và schema có constraint, để tránh “test pass giả” do lỗi kết nối hoặc SQL sai ngay từ đầu.

## 9. Generated keys: các trường hợp dễ sai

### 9.1. Generated key không đồng nhất với business key

`account_id` do DBMS cấp giúp xác định một hàng trong bảng. `external_ref` do ứng dụng tạo để định danh nghiệp vụ hoặc yêu cầu. Cả hai có vai trò khác nhau:

- Generated ID có thể có khoảng trống, không mang ý nghĩa thứ tự nghiệp vụ.
- Business key có thể hỗ trợ idempotency và đối soát sau lỗi commit.
- Một lần INSERT thất bại vẫn có thể đã tiêu thụ một giá trị sequence.
- Nhiều transaction chạy song song có thể nhận ID xen kẽ; không kết luận từ giá trị lớn nhất.

### 9.2. Không giả định mọi INSERT trả nhiều key theo thứ tự đầu vào

Với INSERT nhiều hàng hoặc `PreparedStatement.executeBatch()`, số lượng và thứ tự generated keys có thể khác nhau tùy driver, cú pháp và cấu hình. Một số driver hỗ trợ lấy nhiều khóa, một số chỉ trả một phần hoặc không hỗ trợ theo cách ứng dụng muốn.

**Cách test phù hợp:**

1. Xác định driver/DBMS có cam kết trả key cho từng hàng trong batch không.
2. Thử trường hợp 1, 2 và nhiều hàng với đầu vào có `external_ref` duy nhất.
3. Đối chiếu mỗi key nhận được với hàng đã lưu theo business key.
4. Không suy đoán mapping bằng `firstId + index`.
5. Nếu không có hợp đồng ổn định, cân nhắc insert từng hàng cần key hoặc dùng cú pháp `RETURNING/OUTPUT` đặc thù đã kiểm chứng.

### 9.3. Cột nhận giá trị NULL và các khóa không phải số

Không phải mọi generated key là `BIGINT`; một số schema dùng UUID, chuỗi hoặc khóa tổng hợp. `getLong(1)` chỉ phù hợp khi schema test **thật sự sinh khóa số**. Với UUID hoặc string, có thể cần `getObject()` hoặc `getString()` và adapter theo driver.

Trong test, kiểm tra `keys.wasNull()` sau getter kiểu nguyên thủy; nếu không, giá trị SQL `NULL` có thể bị hiểu nhầm thành 0. Với khóa tổng hợp, không giả định result set chỉ có một cột.

## 10. Batch testing: affected rows không giống kết quả commit

Một `PreparedStatement` có thể gom nhiều bộ tham số bằng `addBatch()` và gọi `executeBatch()`. Kết quả thường là một `int[]` với update count tương ứng từng phần tử theo quy tắc JDBC. Nếu có lỗi, driver có thể ném `BatchUpdateException`.

```java
String sql = """
    UPDATE jdbc_test_accounts
       SET display_name = ?
     WHERE account_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "A");
    ps.setLong(2, firstId);
    ps.addBatch();

    ps.setString(1, "B");
    ps.setLong(2, secondId);
    ps.addBatch();

    int[] counts = ps.executeBatch();
    // Dùng assertion phù hợp driver và dữ liệu fixture.
}
```

Bảng quy ước:

| Giá trị trong `int[]` | Nghĩa |
| --- | --- |
| `0` hoặc số dương | Số hàng tác động do driver báo cáo cho phần tử |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Thực thi thành công nhưng không biết chính xác số hàng |
| `Statement.EXECUTE_FAILED` (`-3`) | Phần tử batch thất bại trong cách driver báo lỗi |

Khi `executeBatch()` ném lỗi:

```java
import java.sql.BatchUpdateException;
import java.sql.SQLException;
import java.sql.Statement;

try {
    int[] counts = ps.executeBatch();
    // Xem từng kết quả.
} catch (BatchUpdateException error) {
    int[] counts = error.getUpdateCounts();

    for (int i = 0; i < counts.length; i++) {
        if (counts[i] == Statement.EXECUTE_FAILED) {
            System.err.println("Batch entry " + i + " thất bại");
        } else if (counts[i] == Statement.SUCCESS_NO_INFO) {
            System.err.println("Batch entry " + i + " thành công, chưa rõ count");
        }
    }

    for (SQLException current = error;
         current != null;
         current = current.getNextException()) {
        System.err.printf(
            "sqlState=%s, vendorCode=%d%n",
            current.getSQLState(), current.getErrorCode()
        );
    }
    throw error;
}
```

Đây là đoạn mã **nằm trong phạm vi đã khai báo `PreparedStatement ps`**. Trong production, thay `System.err` bằng logging được kiểm soát, tránh in tham số SQL hoặc dữ liệu nhạy cảm.

Một số driver dừng ngay khi phần tử lỗi; số khác tiếp tục xử lý. Độ dài `getUpdateCounts()` và cách đánh dấu `EXECUTE_FAILED` phải được giải thích theo JDBC và hành vi driver. Với batch kích thước rất lớn, `executeLargeBatch()` và `getLargeUpdateCounts()` cung cấp biến thể dùng `long`.

**Quan trọng:** kể cả một phần tử được báo thành công, khi `autoCommit=false` dữ liệu vẫn có thể rollback. Nếu batch có lỗi, không chỉ nhìn update counts để quyết định những hàng đã commit; cần xem ranh giới transaction và đối soát trạng thái database.

## 11. Kiểm thử transaction và ranh giới commit

Một test CRUD có thể thành công khi chạy mỗi câu SQL riêng lẻ nhưng thất bại nếu service cần nhiều DML trong một transaction.

Ví dụ nghiệp vụ tạo order và order items:

```text
BEGIN (autoCommit=false)
  INSERT orders -> generated order_id
  INSERT order_items dùng order_id
  UPDATE inventory
COMMIT
```

Các phép thử nên có:

| Kịch bản | Bằng chứng |
| --- | --- |
| Tất cả statement thành công rồi commit | Order, items và inventory đồng bộ trên connection mới |
| Statement cuối bị lỗi trước commit | Rollback làm mất toàn bộ DML transactional chưa commit |
| Constraint phát lỗi giữa chuỗi | Service không commit phần đầu ngoài ý muốn |
| `commit()` trả về thành công | Dữ liệu được đọc trên connection mới |
| Lỗi kết nối trong `commit()` | Không tự kết luận transaction thất bại; đối soát theo business key |
| `rollback()` cũng ném lỗi | Giữ ngoại lệ gốc và ghi nhận lỗi rollback như suppressed |
| Nhiều service dùng các connection khác nhau | Không mặc định chung một local transaction |

Một mẫu quản lý transaction:

```java
try (Connection c = dataSource.getConnection()) {
    c.setAutoCommit(false);
    try {
        insertOrder(c);
        insertOrderItems(c);
        updateInventory(c);
    } catch (SQLException | RuntimeException error) {
        try {
            c.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }

    // Đặt ngoài catch rollback của bước trước.
    c.commit();
}
```

Đây là **khung minh họa**: `insertOrder`, `insertOrderItems` và `updateInventory` là các phương thức giả định và tất cả phải dùng **cùng Connection**. Nếu `c.commit()` ném `SQLException`, trạng thái commit có thể chưa xác định; không tự động tạo yêu cầu mới để “chắc ăn”.

Không dùng một test rollback để kết luận DDL hay side effect ngoài database cũng rollback được. Trong nhiều DBMS, DDL có thể implicit commit; sequence/identity và thao tác ngoại hệ thống có vòng đời riêng. Test transaction phải giới hạn đúng phạm vi được DBMS đảm bảo.

## 12. Thử nghiệm concurrency và optimistic locking

Test tuần tự `UPDATE ... WHERE version=?` có thể chứng minh version cũ không sửa được **sau khi version đã tăng**. Nhưng còn một nguy cơ khác: hai connection cùng đọc version 0 và cùng muốn cập nhật.

Một test concurrency nên có hai phiên độc lập:

```mermaid
sequenceDiagram
    participant A as Connection A
    participant B as Connection B
    participant DB as DBMS
    A->>DB: SELECT version=0
    B->>DB: SELECT version=0
    A->>DB: UPDATE ... WHERE version=0
    DB-->>A: affectedRows=1
    A->>DB: COMMIT
    B->>DB: UPDATE ... WHERE version=0
    DB-->>B: affectedRows=0 hoặc lỗi concurrency phù hợp
    Note over A,B: B phải đọc lại hoặc báo xung đột; không ghi đè mù quáng
```

Tùy isolation và DBMS, connection B có thể chờ khóa, nhận `0` hoặc nhận ngoại lệ serialization/deadlock thay vì kết quả giống nhau ở mọi môi trường. **Điều cần chứng minh là không làm mất cập nhật đã xác nhận**, không phải bắt buộc tất cả driver trả cùng một chuỗi mã lỗi.

### Điều kiện để test concurrency không flake

- Dùng đồng bộ hóa rõ ràng giữa hai luồng test để tạo giao điểm; tránh chỉ dùng `Thread.sleep()` rồi kỳ vọng đúng thứ tự.
- Đặt timeout hữu hạn để test không treo khi khóa bị giữ.
- Sau khi cả hai transaction kết thúc, đọc lại **server** và kiểm tra bất biến nghiệp vụ.
- Không chia sẻ cùng `Connection` giữa hai luồng; mỗi luồng mượn connection riêng.
- Không để các test cạnh tranh với cùng fixture của test khác.
- Cấu hình isolation được xác nhận; một số DBMS phản hồi bằng lỗi thay vì `affectedRows=0`.

Test concurrency có thể tốn thời gian hơn test CRUD cơ bản; chạy ở bộ integration test có môi trường DBMS thật và có chiến lược lặp để phát hiện lỗi không ổn định.

## 13. Test CRUD với SQL NULL, kiểu số và dữ liệu thực tế

Ngay cả khi số hàng ảnh hưởng đúng, mapping có thể sai ở dữ liệu biên.

### 13.1. SQL NULL khác với giá trị mặc định Java

Với `ResultSet.getInt(...)`, khi cột là SQL `NULL`, getter primitive có thể trả 0; phải gọi `rs.wasNull()` ngay sau getter nếu cần phân biệt NULL với 0.

```java
int quantity = rs.getInt("quantity");
boolean missingQuantity = rs.wasNull();
```

Với `ResultSet.getString(...)`, SQL NULL được trả thành `null`. Với `PreparedStatement.setNull(...)`, cung cấp mã SQL type phù hợp với cột; không mặc định `setObject(index, null)` luôn được driver suy luận đúng trong mọi ngữ cảnh.

### 13.2. DECIMAL và BigDecimal

Nếu bảng có `DECIMAL(19, 2)`, test nên so sánh giá trị số học theo nhu cầu:

```java
java.math.BigDecimal actual = rs.getBigDecimal("amount");
java.math.BigDecimal expected = new java.math.BigDecimal("10.00");

assertNotNull(actual);
assertEquals(0, expected.compareTo(actual));
```

`BigDecimal.equals(...)` phân biệt scale nên `10.0` và `10.00` có thể không bằng nhau dù giá trị số học tương đương. Nếu **scale** là một phần hợp đồng, test riêng scale và quy tắc làm tròn của DBMS, không dùng `compareTo` để che những khác biệt đó.

### 13.3. Dữ liệu chuỗi và Unicode

Nên có fixture chứa:

- Tiếng Việt có dấu, ví dụ `"Đơn hàng Nguyễn Ánh"`.
- Dấu nháy đơn, ví dụ `"O'Neil"`.
- Chuỗi rỗng, nếu DBMS phân biệt với SQL NULL.
- Ký tự ngoài BMP khi ứng dụng hỗ trợ Unicode đầy đủ.
- Giá trị cận độ dài cột và dữ liệu không hợp lệ.

Một số DBMS có quy tắc collation, độ dài theo byte/ký tự hoặc hành vi đặc biệt với chuỗi rỗng. **Chọn assertion đúng với hợp đồng schema**, không áp dụng kỳ vọng một DBMS lên mọi database.

## 14. Tránh các test “xanh giả” và lỗi không ổn định

| Sai lầm | Vì sao nguy hiểm? | Cách sửa |
| --- | --- | --- |
| Mock `executeUpdate()` trả 1 rồi khẳng định SQL đúng | Mock không chạy DBMS thật | Dùng integration test để xác minh SQL |
| Không `SELECT` sau INSERT/UPDATE | Có thể đọc sai key, trigger đổi dữ liệu, sai WHERE | Đọc lại theo khóa/ref |
| Dùng `SELECT MAX(id)` tìm generated key | Race giữa các kết nối; sequence không phản ánh commit | `getGeneratedKeys()` |
| Kiểm tra ID phải tăng liên tiếp | Rollback, cache và concurrency tạo khoảng trống | Kiểm tra tính đúng/sự duy nhất, không kiểm tra liên tiếp |
| Chỉ assert `executeUpdate() >= 0` | UPDATE 0 hàng vẫn pass | Kỳ vọng chính xác theo contract |
| Coi `executeUpdate()==1` là đã commit | Transaction còn có thể rollback | Test commit bằng connection mới |
| Test trên dữ liệu dùng chung | Order/identity và update counts bị nhiễu | Schema riêng và mã ref duy nhất |
| Tạo DDL trong transaction rollback | DDL có thể commit ngầm | Migration setup độc lập |
| Bắt mọi `SQLException` và coi là trùng key | Lỗi kết nối/SQL sai vẫn làm test pass | Chỉ kiểm tra lỗi cụ thể sau khi fixture hợp lệ |
| Tiếp tục query sau unique violation | Transaction có thể đã aborted | Rollback hoặc dùng transaction/savepoint phù hợp |
| Test concurrency bằng `Thread.sleep()` | Không bảo đảm thứ tự scheduler/lock | Barrier/latch và timeout |
| Dọn fixture bằng DELETE không WHERE | Có nguy cơ xóa dữ liệu ngoài test | Unique ref và bảng test riêng |
| Tự tăng timeout để bỏ qua test chậm | Che query chậm, pool contention hoặc deadlock | Điều tra latency/lock và kiểm soát tải |
| Log toàn JDBC URL/password khi lỗi | Rò rỉ credential trong CI/test report | Chỉ log metadata an toàn |
| Không test driver/DBMS version thật | Chỉ phát hiện khác biệt khi deploy | Contract test trên tổ hợp được hỗ trợ |

### 14.1. Cách quan sát một test thất bại

Khi assertion sai, thông tin chẩn đoán nên gồm:

- Tên test, loại thao tác và ID/ref của **fixture test an toàn**.
- SQLState và mã lỗi vendor khi có `SQLException`.
- Số dòng **dự kiến** và **thực tế**.
- Giá trị cột có thể công bố trong môi trường kiểm thử, sau khi kiểm tra quyền/logging policy.
- Driver version và DBMS version khi cần phân tích khác biệt.
- Trạng thái transaction đã commit, rollback hay chưa rõ.

Tránh in tham số nhạy cảm, chuỗi kết nối có credential và toàn bộ dữ liệu thật. Chạy test nên đủ lặp lại, nhưng log không được trở thành nơi lưu bí mật.

## 15. Ma trận kiểm thử tối thiểu trước khi chấp nhận repository

| Nhóm test | Ca kiểm thử | Kỳ vọng cốt lõi |
| --- | --- | --- |
| CREATE | INSERT một hàng hợp lệ | Count 1; generated key hợp lệ; SELECT lại đúng |
| CREATE | INSERT trùng business key | DB từ chối theo constraint; không thêm hàng thứ hai |
| CREATE | INSERT với Unicode và dấu nháy | Tham số được lưu/đọc đúng |
| READ | Tìm theo ID tồn tại | Đúng một hàng; mapping đúng |
| READ | Tìm theo ID không tồn tại | Không có hàng; contract trả đúng |
| UPDATE | Đổi một cột theo ID/version | Count 1; giá trị mới và version đúng |
| UPDATE | Version stale | Count 0 hoặc conflict theo contract; không lost update |
| UPDATE | WHERE nhầm/hàng khác | Hàng không được chọn vẫn không thay đổi |
| DELETE | Xóa ID có tồn tại | Count 1; không còn hàng |
| DELETE | Xóa lại ID đã xóa | Count 0 |
| DELETE | Xóa ID khác | Hàng fixture chính còn nguyên |
| TRANSACTION | Rollback INSERT/UPDATE | Dữ liệu không được commit sau rollback |
| TRANSACTION | Commit INSERT | Connection mới thấy dữ liệu chính xác |
| BATCH | Tất cả phần tử hợp lệ | Counts phù hợp driver và dữ liệu đã commit |
| BATCH | Một phần tử lỗi | Phân tích `BatchUpdateException`, rollback/partial theo contract |
| KEY | INSERT nhiều hàng/batch | Mapping generated keys được chứng minh hoặc fallback |
| CONCURRENCY | Hai writer cạnh tranh | Không ghi đè bản đã commit ngoài chính sách |
| ERROR | Lỗi connection trong commit | Trạng thái được đối soát/idempotency, không retry mù quáng |

Một test suite tốt cần nêu rõ **DBMS/driver nào được hỗ trợ**, isolation/transaction mode và cách reset dữ liệu. “Pass trên database nhúng” chưa đủ nếu production dùng DBMS khác với ngữ nghĩa generated keys, type mapping hoặc update counts khác.

## 16. Bài luyện tập

**Bài 1 — UPDATE 0 hàng.** `executeUpdate()` trả `0` với câu `UPDATE ... WHERE account_id=?`. Có thể khẳng định SQL đã thất bại không?

*Đáp án:* Không. Câu SQL có thể chạy bình thường nhưng không có hàng khớp. Cần kiểm tra contract và dữ liệu; với UPDATE cùng giá trị cũ còn cần hiểu cách driver/DBMS báo count.

**Bài 2 — Generated key.** Hai request cùng INSERT vào bảng có identity. Tại sao `SELECT MAX(account_id)` không phải cách an toàn để lấy ID của request A?

*Đáp án:* Request B có thể insert cùng thời điểm; sequence/identity có thể cấp ID trước commit. Phải đọc `getGeneratedKeys()` của chính statement A hoặc cơ chế DBMS đã kiểm chứng.

**Bài 3 — Rollback test.** Test INSERT trên connection A, đọc lại được hàng trên chính A, rồi rollback. Nó có chứng minh INSERT đã commit không?

*Đáp án:* Không. A có thể thấy thay đổi chưa commit của mình; cần test commit riêng và connection B độc lập để xác minh tính bền vững.

**Bài 4 — Version stale.** Test UPDATE theo `id` và `version=0` trả `1`, sau đó thử lại version 0 trả `0`. Điều gì được chứng minh?

*Đáp án:* Một lần cập nhật đã tăng version và cập nhật lần hai với version cũ bị từ chối theo điều kiện SQL. Vẫn cần test cạnh tranh thật nếu contract yêu cầu an toàn concurrency.

**Bài 5 — DELETE hai lần.** DELETE ID tồn tại trả `1`, DELETE cùng ID lần hai trả `0`. Có nên coi lệnh thứ hai là thành công theo nghĩa “đảm bảo hàng không còn tồn tại” không?

*Đáp án:* Có thể, nếu hợp đồng nghiệp vụ idempotent cho phép. Nhưng nếu contract đòi “đã xóa chính xác một hàng tồn tại”, `0` là kết quả cần phân loại rõ.

**Bài 6 — Batch counts.** `executeBatch()` trả `Statement.SUCCESS_NO_INFO` cho một phần tử. Có thể coi phần tử đó thất bại không?

*Đáp án:* Không; hằng này nghĩa là thành công nhưng chưa có số hàng cụ thể. Trạng thái commit vẫn cần xét riêng.

**Bài 7 — Constraint test.** Tại sao test `assertThrows(SQLException.class, () -> insertDuplicate())` có thể là “xanh giả”?

*Đáp án:* Nếu kết nối lỗi hoặc SQL sai, test cũng có thể ném `SQLException`. Hãy đảm bảo insert gốc thành công, constraint tồn tại và kiểm tra loại lỗi theo phạm vi driver/DBMS.

**Bài 8 — Lỗi commit.** `getGeneratedKeys()` đã trả ID, nhưng `commit()` ném lỗi mạng. Có thể kết luận hàng không tồn tại và thử lại bằng business key mới không?

*Đáp án:* Không. Kết quả commit có thể chưa xác định; dùng business key ổn định để đối soát và tránh tạo trùng dữ liệu.

## Kết luận

**Kiểm thử CRUD trong JDBC phải xác minh cả số hàng bị tác động, khóa sinh và trạng thái dữ liệu thật, không chỉ kiểm tra rằng SQL không ném lỗi.** Dùng `PreparedStatement` với tham số để tạo, đọc, sửa, xóa; so sánh update count theo hợp đồng; lấy ID bằng `RETURN_GENERATED_KEYS`/`getGeneratedKeys()` rồi SELECT lại bằng khóa; kiểm tra rõ trường hợp 0, 1 và nhiều hàng. Với transaction, phân biệt việc DML đã chạy với dữ liệu đã commit, dùng rollback để cô lập fixture và connection mới để xác nhận commit. Các kiểm thử constraint, batch, version và concurrency giúp phát hiện lỗi mà CRUD happy path không thể thấy. Cuối cùng, luôn chạy các contract quan trọng trên **DBMS, JDBC driver và schema thực tế được hỗ trợ**, bởi ngữ nghĩa generated keys, update counts và xử lý transaction không hoàn toàn giống nhau giữa mọi môi trường.
