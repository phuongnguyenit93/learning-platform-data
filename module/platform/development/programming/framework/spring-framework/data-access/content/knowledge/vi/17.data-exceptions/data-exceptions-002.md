# Dịch SQLException mà vẫn giữ nguyên nhân gốc trong Spring Framework

> **Ngữ cảnh:** Spring Framework – Data Access, nhóm **Ngoại lệ dữ liệu**. Bài học tập trung vào cách chuyển lỗi JDBC `SQLException` sang hệ phân loại `DataAccessException` của Spring **mà không đánh mất `SQLException` ban đầu**, chuỗi nguyên nhân, SQLState và mã lỗi của nhà cung cấp database.

## 1. Vì sao cần dịch ngoại lệ nhưng vẫn giữ nguyên nhân?

Khi thực hiện SQL trực tiếp bằng JDBC, driver có thể ném `SQLException` hoặc một lớp con của nó. Lỗi thường chứa những chi tiết đặc thù: `SQLState`, `vendorCode`, thông điệp gốc và đôi khi một chuỗi `SQLException` bổ sung. Nếu tầng service phải xử lý riêng từng mã của PostgreSQL, MySQL, Oracle, SQL Server, H2, mã ứng dụng sẽ bị phụ thuộc vào database.

Spring JDBC dùng `SQLExceptionTranslator` để chuyển lỗi kỹ thuật đó thành các lớp con **không phải checked exception** của `org.springframework.dao.DataAccessException`, chẳng hạn `DataIntegrityViolationException` hoặc `BadSqlGrammarException`. Nhờ vậy code phía trên có thể xử lý theo **bản chất lỗi** thay vì tên driver.

Nhưng quá trình chuyển đổi **không được xóa thông tin gốc**. Hai tầng thông tin cần tồn tại đồng thời:

```text
Tầng dịch vụ
    |
    +-- DataIntegrityViolationException (phân loại Spring)
            |
            +-- getCause() -> SQLException của JDBC driver
                    |
                    +-- getSQLState(): "23505"
                    +-- getErrorCode(): mã riêng của DB/driver
                    +-- getMessage(): mô tả kỹ thuật
                    +-- getNextException(): SQLException bổ sung (nếu có)
```

Với một lỗi trùng khóa duy nhất, service thường chỉ cần biết đây là lỗi **toàn vẹn dữ liệu**; đội vận hành cần biết *ràng buộc nào* bị vi phạm, phiên bản driver, SQLState và các chi tiết gốc để chẩn đoán. **Dịch loại lỗi và giữ nguyên nguyên nhân phục vụ hai mục tiêu khác nhau, bổ sung cho nhau.**

### Mục tiêu cần đạt

- Giữ được ngoại lệ gốc trong `cause` khi tạo ngoại lệ mới; thông tin gốc vẫn truy xuất được.
- Dùng kiểu ngoại lệ Spring cho logic nghiệp vụ và ranh giới transaction.
- Đọc được `SQLState`/vendor code khi cần điều tra; không phụ thuộc vào `getMessage()` để phân loại.
- Hiểu giới hạn của `getRootCause()`: không phải mọi `DataAccessException` đều bắt nguồn từ JDBC.
- Không mất chuỗi `getNextException()`, đặc biệt khi driver trả `BatchUpdateException`.
- Không để chi tiết SQL, mật khẩu hay giá trị dữ liệu nhạy cảm tràn ra phản hồi API.

## 2. Đọc đúng dữ liệu trên SQLException

Một `SQLException` có thể cung cấp:

| Thuộc tính | API | Cần hiểu |
| --- | --- | --- |
| Thông điệp | `getMessage()` | Chuỗi do driver tạo; hữu ích khi debug, có thể chứa SQL/tên bảng/dữ liệu; không ổn định để so khớp bằng chuỗi. |
| SQLState | `getSQLState()` | Thường là mã 5 ký tự theo SQL standard hoặc X/Open; có thể `null`; ý nghĩa chi tiết tùy database. |
| Mã nhà cung cấp | `getErrorCode()` | Số nguyên do DB/driver định nghĩa, có thể bằng `0` hoặc khác giữa các DBMS. |
| Nguyên nhân Java | `getCause()` | Liên kết `Throwable` thông thường, dùng cho stack trace và ngoại lệ bọc. |
| SQLException tiếp theo | `getNextException()` | Chuỗi **riêng** của JDBC, không đồng nghĩa với `getCause()`; có thể chứa lỗi SQL tiếp theo hoặc lỗi gốc cụ thể hơn. |
| Lỗi bị suppress | `getSuppressed()` | Ví dụ lỗi đóng tài nguyên trong `try-with-resources`; không đồng nhất với `getNextException()`. |
| Kết quả batch | `BatchUpdateException.getUpdateCounts()` | Các count hoặc mã trạng thái của lệnh trong batch; phải diễn giải theo driver và giao dịch. |

Hai ký tự đầu của `SQLState` có thể gợi ý nhóm lỗi: `23` thường liên quan ràng buộc toàn vẹn; `42` thường liên quan cú pháp hoặc truy cập tài nguyên SQL; `08` thường liên quan kết nối; `40` liên quan rollback giao dịch. Tuy nhiên không thể luôn suy ra **loại Spring exception chính xác** chỉ từ hai ký tự. Ví dụ `23505` thường là khóa trùng, nhưng driver và phiên bản Spring quyết định cách ánh xạ cuối cùng.

**Nguyên tắc:** ghi nhận *loại Spring* để ra quyết định ứng dụng; ghi nhận *SQLState + vendor code + exception class* để tìm nguyên nhân. Khi có `SQLException` lồng nhau, phải giữ lại chính đối tượng đã bắt được thay vì dựng một `SQLException` mới chỉ từ message.

## 3. Spring phân loại SQLException như thế nào?

### 3.1. Hệ phân cấp DataAccessException

`DataAccessException` là `RuntimeException`, thuộc hệ ngoại lệ không phụ thuộc trực tiếp vào JDBC. Một số loại hay gặp:

| Lớp Spring | Ý nghĩa điển hình | Hướng xử lý |
| --- | --- | --- |
| `DataIntegrityViolationException` | Lỗi ràng buộc dữ liệu: khóa, `NOT NULL`, khóa ngoại... | Kiểm tra dữ liệu và ràng buộc; không retry vô điều kiện. |
| `DuplicateKeyException` | Một trường hợp cụ thể của `DataIntegrityViolationException`: trùng khóa duy nhất | Xử lý quy tắc trùng dữ liệu; nên catch lớp cha nếu cần tương thích nhiều DB. |
| `BadSqlGrammarException` | SQL sai cú pháp, sai tên bảng/cột... | Sửa SQL hoặc schema, không tự retry. |
| `CannotAcquireLockException` | Không lấy được lock hoặc lỗi concurrency tương ứng theo phép dịch | Có thể cân nhắc retry **cả giao dịch**, tùy tình huống. |
| `QueryTimeoutException` | Truy vấn vượt thời gian cho phép khi driver nhận diện được | Tìm nguyên nhân chậm, điều chỉnh timeout/tải; retry có kiểm soát. |
| `DataAccessResourceFailureException` | Sự cố nghiêm trọng về tài nguyên/kết nối dữ liệu | Kiểm tra DB, mạng, pool và phạm vi tác động. |
| `UncategorizedSQLException` | Không phân loại được vào nhóm cụ thể | Vẫn giữ `SQLException`, SQL liên quan và task; điều tra mã/driver. |

Tên lớp trong bảng là **ví dụ phân loại**, không phải bảng tra mã cố định cho mọi hệ quản trị. `DuplicateKeyException` kế thừa `DataIntegrityViolationException`; bắt lớp cha thường ổn định hơn khi đổi vendor. `TransientDataAccessException` thể hiện lỗi có thể thành công nếu thử lại *trong điều kiện phù hợp*, không có nghĩa là được phép retry mọi thao tác không idempotent.

Ngoài JDBC, Spring còn có thể tạo `DataAccessException` từ công nghệ truy cập dữ liệu khác. Vì vậy, một `DataAccessException` **không luôn có `SQLException` ở sâu trong cause**.

### 3.2. SQLExceptionTranslator và lựa chọn mặc định

`org.springframework.jdbc.support.SQLExceptionTranslator` có chữ ký:

```java
DataAccessException translate(String task, String sql, SQLException ex);
```

Trong API, kết quả có thể là `null` nếu translator không khớp. `task` là mô tả thao tác; `sql` là câu SQL nếu biết (có thể `null`); `ex` phải là lỗi JDBC gốc. Khi đã dịch được, ngoại lệ Spring trả về **cần giữ `ex` trong cause**.

Trong Spring Framework **6.x**:

1. `JdbcTemplate` bắt `SQLException` khi thực thi JDBC và dùng translator để chuyển thành `DataAccessException`.
2. Từ Spring 6.0, lựa chọn JDBC mặc định thường là `SQLExceptionSubclassTranslator`: nhận diện lớp con JDBC 4 (ví dụ `SQLIntegrityConstraintViolationException`), rồi fallback sang `SQLStateSQLExceptionTranslator` nếu cần.
3. `SQLStateSQLExceptionTranslator` dựa trên `SQLState` và những trường hợp phổ biến. Đây là cơ chế fallback, không cần kiểm tra tên vendor.
4. `SQLErrorCodeSQLExceptionTranslator` dựa trên bảng mã của database trong `sql-error-codes.xml`, xác định bằng metadata của `DataSource`; có thể phân loại chi tiết hơn. Với file `sql-error-codes.xml` do ứng dụng đặt ở **root của classpath**, chiến lược dùng error code có thể được chọn mặc định.
5. Nếu tất cả translator không nhận diện được, `JdbcTemplate` có thể ném `UncategorizedSQLException`, **vẫn chứa SQLException gốc**. Việc không xác định được loại không có nghĩa được phép bỏ lỗi.

Những chi tiết này mô tả nhánh 6.x; khi dùng Spring 7.x hoặc cấu hình framework khác, kiểm tra API và hành vi thực tế trong version được triển khai. Nếu đang dùng Spring Boot, ưu tiên để dependency management của Boot quản lý phiên bản Spring.

### 3.3. Vì sao vẫn cần SQLException ban đầu?

`DataAccessException.getCause()` trả trực tiếp ngoại lệ được lưu làm nguyên nhân. Spring còn có:

- `getRootCause()`: tìm nguyên nhân *sâu nhất*, có thể trả `null` nếu không có nguyên nhân lồng nhau.
- `getMostSpecificCause()`: nguyên nhân sâu nhất nếu có, nếu không thì chính exception hiện tại.
- `contains(SQLException.class)`: kiểm tra cause chain có chứa kiểu này không.

Đừng mặc định ép kiểu `(SQLException) ex.getCause()` trong mọi tầng ứng dụng: một service có thể đã bọc thêm `RuntimeException`, và dữ liệu có thể đến từ nguồn không phải JDBC. Nếu chắc chắn dùng JDBC, hãy tìm dọc `Throwable.getCause()` hoặc dùng accessor chuyên dụng như `UncategorizedSQLException.getSQLException()`; khi đọc chi tiết mã, kiểm tra `instanceof SQLException` trước.

## 4. Ví dụ chạy được: Spring JDBC + H2 giữ lại SQLException thật

Ví dụ dùng **Java 17**, **Spring JDBC 6.2.19** và **H2 2.5.252**. Ta tạo bảng có ràng buộc `UNIQUE`, cố tình insert email trùng, rồi bắt `DataIntegrityViolationException`. Spring làm công việc dịch ngoại lệ; chương trình chứng minh `SQLException` gốc vẫn truy cập được. Ví dụ còn minh họa một translator tùy chỉnh giữ **cùng đối tượng cause**, không chỉ cùng message.

Cấu trúc dự án:

```text
sql-exception-demo/
├── pom.xml
└── src/main/java/SqlExceptionDemo.java
```

### 4.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>sql-exception-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.5.252</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>SqlExceptionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.2. src/main/java/SqlExceptionDemo.java

```java
import java.sql.SQLException;
import java.sql.SQLSyntaxErrorException;

import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.SQLExceptionSubclassTranslator;

public final class SqlExceptionDemo {

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:sqlerrors;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("CREATE TABLE person (" +
                "id BIGINT PRIMARY KEY, " +
                "email VARCHAR(120) NOT NULL UNIQUE)");

        jdbc.update("INSERT INTO person (id, email) VALUES (?, ?)",
                1L, "same@example.test");

        try {
            // Vi phạm UNIQUE(email), H2 ném SQLException SQLState 23505.
            jdbc.update("INSERT INTO person (id, email) VALUES (?, ?)",
                    2L, "same@example.test");
            throw new AssertionError("Expected a duplicate-key failure");
        } catch (DataIntegrityViolationException ex) {
            SQLException sqlCause = firstSqlCause(ex);
            if (sqlCause == null) {
                throw new IllegalStateException(
                        "Original SQLException is missing", ex);
            }

            System.out.println("Caught integrity violation: true");
            System.out.println("SQLException preserved: " +
                    ex.contains(SQLException.class));
            System.out.println("SQLState: " + sqlCause.getSQLState());
            System.out.println("Vendor code: " + sqlCause.getErrorCode());
        }

        // Custom rule: vendor code giả lập 70001.
        // Mọi lỗi khác tiếp tục do Spring phân loại.
        SQLExceptionSubclassTranslator translator =
                new SQLExceptionSubclassTranslator();

        translator.setCustomTranslator((task, sql, original) -> {
            if (original.getErrorCode() == 70001) {
                return new DataIntegrityViolationException(
                        "Custom integrity rule failed during " + task,
                        original); // QUAN TRỌNG: giữ nguyên đối tượng gốc
            }
            return null; // trả quyền xử lý cho translator mặc định
        });

        SQLException original =
                new SQLException("Synthetic database rule", "HY000", 70001);
        DataAccessException custom =
                translator.translate("save person", null, original);

        System.out.println("Custom translation: " +
                (custom instanceof DataIntegrityViolationException));
        System.out.println("Same original cause: " +
                (custom != null && custom.getCause() == original));

        SQLException syntaxError =
                new SQLSyntaxErrorException("Invalid SQL", "42000", 0);
        DataAccessException fallback =
                translator.translate("query", "SELECT bad", syntaxError);

        System.out.println("Fallback recognized: " +
                (fallback instanceof BadSqlGrammarException));
    }

    private static SQLException firstSqlCause(Throwable failure) {
        for (Throwable current = failure;
             current != null;
             current = current.getCause()) {
            if (current instanceof SQLException sql) {
                return sql;
            }
        }
        return null;
    }
}
```

Ở thư mục chứa `pom.xml`, chạy (cần JDK 17+ và Maven, lần đầu Maven phải tải dependency):

```bash
mvn -q compile exec:java
```

Đầu ra mong đợi với đúng các dependency đã khai báo:

```text
Caught integrity violation: true
SQLException preserved: true
SQLState: 23505
Vendor code: 23505
Custom translation: true
Same original cause: true
Fallback recognized: true
```

**Đọc kết quả:**

1. `JdbcTemplate.update(...)` ném một ngoại lệ thuộc `DataIntegrityViolationException` (có thể là lớp con `DuplicateKeyException`); code chỉ bắt lớp cha để tránh phụ thuộc vào mức chi tiết của phép dịch.
2. `ex.contains(SQLException.class)` chứng minh original JDBC error còn nằm trên `cause chain`; `firstSqlCause(...)` cho phép đọc `SQLState` và `vendorCode` mà không đoán độ sâu lồng nhau.
3. Trong phần custom, `original` được truyền **nguyên đối tượng** vào constructor `DataIntegrityViolationException(message, original)`; phép so sánh tham chiếu `custom.getCause() == original` minh chứng không đánh mất lỗi ban đầu.
4. Lỗi `SQLSyntaxErrorException` không khớp code custom; trả `null` khiến translator cơ sở tiếp tục ánh xạ sang `BadSqlGrammarException`. Nếu trả một ngoại lệ tùy ý thay vì `null`, fallback sẽ bị chặn.
5. Không sử dụng `getMessage()` của ngoại lệ để tìm từ “duplicate”; message của H2 và các phiên bản khác có thể thay đổi.

> Ví dụ này thực thi thật SQL trên H2 in-memory, khác với việc tự `new SQLException(...)` rồi khẳng định JDBC đã chạy. Phần synthetic chỉ kiểm thử đường **custom translation** độc lập với database. `DriverManagerDataSource` phù hợp cho ví dụ; trong ứng dụng thật, dùng connection pool và cấu hình transaction phù hợp.

## 5. Tự dịch lỗi đúng cách khi không dùng JdbcTemplate

`JdbcTemplate` thường đã thực hiện việc dịch ngoại lệ. Chỉ khi dùng JDBC thô, custom callback hoặc tầng data access riêng, bạn mới cần gọi translator trực tiếp:

```java
// Mã minh họa trong một phương thức có sẵn:
// task/sql là ngữ cảnh, caught là SQLException vừa bắt.
SQLExceptionTranslator translator = new SQLExceptionSubclassTranslator();

DataAccessException mapped =
        translator.translate("update customer", sql, caught);

throw mapped != null
        ? mapped
        : new UncategorizedSQLException("update customer", sql, caught);
```

Các import cần thiết: `org.springframework.jdbc.support.SQLExceptionTranslator`, `SQLExceptionSubclassTranslator`, `org.springframework.dao.DataAccessException`, `org.springframework.jdbc.UncategorizedSQLException`. Đoạn này là **fragment tích hợp**, không phải lớp độc lập: biến `sql` và `caught` phải được khai báo ở chỗ xử lý JDBC.

**Vì sao cần nhánh `mapped == null`?** Hợp đồng `SQLExceptionTranslator.translate(...)` cho phép trả `null` khi không tìm thấy ánh xạ. Không được coi `null` là “không có lỗi” để tiếp tục ghi dữ liệu; `UncategorizedSQLException` biểu thị chưa phân loại được và giữ cause gốc qua constructor.

**Chú ý về ngữ cảnh:** `task` nên là tên thao tác ngắn, `sql` chỉ là câu lệnh liên quan nếu biết. Không ghép secret hoặc dữ liệu người dùng vào message của exception để phục vụ log; hãy dùng tham số hóa SQL và log những trường được cho phép.

### Khi nào nên cấu hình translator riêng?

Nếu driver trả mã riêng mà mặc định không nhận diện đúng, tạo custom translator và cài vào đúng instance `JdbcTemplate` đang sử dụng:

```java
// Fragment tích hợp vào cấu hình DataSource/JdbcTemplate.
JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
SQLExceptionSubclassTranslator translator =
        new SQLExceptionSubclassTranslator();

translator.setCustomTranslator((task, sql, ex) -> {
    if (ex.getErrorCode() == 70001) {
        return new DataIntegrityViolationException(
                "Vendor integrity rule in " + task, ex);
    }
    return null;
});

jdbcTemplate.setExceptionTranslator(translator);
```

Cách dùng `setCustomTranslator(...)` trên `AbstractFallbackSQLExceptionTranslator` có từ Spring 6.1. Nếu dùng `SQLErrorCodeSQLExceptionTranslator`, có thể đặt `DataSource` để tra mã theo tên database và tùy biến translator; không nên chỉ dựa vào bảng mã được sao chép từ DB khác. Lớp `SQLErrorCodeSQLExceptionTranslator.customTranslate(...)` trong tài liệu cũ đã được đánh dấu deprecated từ Spring 6.1, nên tránh chọn làm API mở rộng mới nếu có `setCustomTranslator(...)`.

**Bất biến phải giữ trong mọi implementation:** ngoại lệ Spring trả về luôn giữ `ex` làm `cause`. Một custom mapper chỉ nên xử lý **mã mà nó thật sự hiểu**; các lỗi khác trả `null` cho bước fallback. Không biến mọi `SQLException` thành `DataIntegrityViolationException`, vì có thể khiến logic retry, thống kê và HTTP mapping đưa ra quyết định sai.

## 6. Vì sao getRootCause() không đủ để chẩn đoán tất cả lỗi?

Giả sử tầng service bọc thêm bối cảnh nghiệp vụ:

```java
// Fragment minh họa trong service, không phải ứng dụng độc lập.
try {
    repository.saveCustomer(customer);
} catch (DataAccessException ex) {
    throw new CustomerWriteException(
            "Could not save customer " + customer.id(), ex);
}
```

Ở đây `CustomerWriteException` được thiết kế có constructor nhận `Throwable cause`; do đó toàn bộ chain:

```text
CustomerWriteException
    -> DataIntegrityViolationException
        -> SQLException (driver)
```

vẫn còn nguyên. Nhưng nếu viết:

```java
// Sai: làm mất đối tượng gốc, stack trace và thông tin vendor.
throw new CustomerWriteException(ex.getMessage());

// Đúng: giữ cause gốc cùng bối cảnh nghiệp vụ.
throw new CustomerWriteException("Could not save customer", ex);
```

thì hai trường hợp khác nhau về chất lượng chẩn đoán. Constructor một tham số kiểu message có thể thuận tiện, nhưng nó **không tự động lưu `ex`** vào cause.

Nếu chỉ cần biết một lỗi có bắt nguồn từ JDBC hay không, có thể kiểm tra:

```java
// Sử dụng trên DataAccessException đã bắt được:
boolean fromJdbc = ex.contains(SQLException.class);
Throwable deepest = ex.getRootCause();        // có thể null
Throwable specific = ex.getMostSpecificCause(); // không null
```

Không nên mặc định `deepest` luôn là `SQLException`: bản thân `SQLException` có thể có `Throwable.getCause()` sâu hơn, hoặc nguyên nhân nằm ở tầng khác. Trong `UncategorizedSQLException` có `getSQLException()` để truy xuất SQLException được bọc trực tiếp, và `getSql()` để lấy câu SQL nếu có. Đối với `DataAccessException` phát sinh từ JPA hoặc truy cập dữ liệu khác, có thể không có `SQLException` nào.

Một cách tìm `SQLException` theo cause chain trong hệ thống JDBC là hàm `firstSqlCause(...)` ở ví dụ hoàn chỉnh. Nó cố ý trả `null` nếu không tìm thấy, buộc nơi gọi xử lý trường hợp không phải JDBC thay vì ép kiểu gây `ClassCastException`.

## 7. BatchUpdateException: nhiều lỗi và nhiều kết quả

Khi cập nhật theo lô, driver có thể ném `java.sql.BatchUpdateException`. Ngoài `SQLException.getSQLState()` và `getErrorCode()` của đối tượng batch, lỗi chi tiết có thể nằm trong chuỗi `getNextException()`. `BatchUpdateException.getUpdateCounts()` còn phản ánh trạng thái các câu lệnh mà driver đã xử lý. Nếu chỉ log `e.getMessage()`, bạn có thể bỏ qua **lỗi SQL nằm ở phần tử lô cụ thể**.

Ví dụ minh họa cách duyệt chuỗi JDBC (không phải chương trình độc lập):

```java
import java.sql.SQLException;

static void inspectSqlChain(SQLException first) {
    for (SQLException current = first;
         current != null;
         current = current.getNextException()) {

        System.out.println("SQLState=" + current.getSQLState()
                + " vendor=" + current.getErrorCode()
                + " type=" + current.getClass().getSimpleName());
    }
}
```

Đây là **chuỗi `nextException`**, khác với `Throwable.getCause()`. Nếu cần đầy đủ, trước hết đi qua chuỗi cause để tìm `SQLException`, sau đó đọc các phần tử `getNextException()` cho từng SQLException liên quan; hệ thống log thực tế nên giới hạn số phần tử và tránh dữ liệu nhạy cảm để không tạo log vô hạn hoặc quá lớn.

Với batch exception:

```java
// Minh họa: "batch" là BatchUpdateException vừa được bắt.
int[] counts = batch.getUpdateCounts();
for (int i = 0; i < counts.length; i++) {
    int count = counts[i];
    if (count == java.sql.Statement.EXECUTE_FAILED) {
        // Driver cho biết lệnh tại vị trí i thất bại.
    } else if (count == java.sql.Statement.SUCCESS_NO_INFO) {
        // Thành công nhưng driver không biết số hàng bị ảnh hưởng.
    } else {
        // count >= 0: số hàng bị ảnh hưởng được driver báo.
    }
}
```

**Không được kết luận** mọi bản ghi ngoài `counts` đã rollback hoặc chưa chạy. Tùy database, driver và việc còn transaction, một số câu lệnh đã thành công có thể vẫn cần rollback. Phạm vi transaction phải được xác định rõ. Một số phiên bản Spring translator (ví dụ Spring 6.2.12+) có xử lý thêm `BatchUpdateException.getNextException()` để phân loại chính xác hơn, nhưng **cause gốc và chuỗi SQLException vẫn cần được giữ** để phân tích.

Nếu cần chuyển một batch exception sang kiểu Spring, hãy đặt **toàn bộ đối tượng `BatchUpdateException` gốc** làm cause, không chỉ chọn một `getNextException()` rồi vứt bỏ đối tượng batch vốn chứa `updateCounts`. Khi custom translator trả null, hãy để translator mặc định/fallback xử lý.

## 8. Xử lý tại repository, service và HTTP API

### Repository / DAO

- Sử dụng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` để tận dụng tài nguyên và exception translation của Spring.
- Không bắt `DataAccessException` chỉ để bọc thành `new RuntimeException(ex.getMessage())`.
- Nếu cần bổ sung thông tin nghiệp vụ, tạo exception có constructor `(String message, Throwable cause)` và truyền **cả cause**.
- Không dùng chuỗi thông báo tiếng Anh của database làm điều kiện phân nhánh. Hãy dựa vào kiểu `DataAccessException`, SQLState hoặc vendor code đã kiểm chứng.

### Service và giao dịch

`DataAccessException` là unchecked exception. Với Spring declarative transaction thông thường, unchecked exception thoát ra khỏi phương thức `@Transactional` sẽ kích hoạt rollback theo mặc định. Nếu catch ngoại lệ rồi trả một giá trị “thành công” hoặc bỏ qua lỗi, transaction có thể commit tùy cấu hình. Vì vậy, nếu xử lý lỗi tại service, hãy quyết định rõ nên **rethrow**, rollback hay phục hồi.

Chỉ retry khi xác định lỗi thực sự tạm thời, giao dịch đã rollback xong và thao tác có thể chạy lại an toàn. Ví dụ xử lý lock contention có thể cần retry **toàn bộ transaction**; một lỗi vi phạm unique key thường cần sửa dữ liệu, không nên retry mù.

### API

Có thể chuyển lỗi ràng buộc **đã xác định là trùng khóa nghiệp vụ** thành phản hồi HTTP `409 Conflict`; những lỗi integrity khác có thể cần `400`, `422` hoặc `500` tùy hợp đồng API. Không trả trực tiếp `SQLState`, tên bảng, SQL gốc và vendor message ra public API. Thông tin chẩn đoán có thể được ghi trong log/tracing có kiểm soát truy cập cùng `correlationId` để hỗ trợ đối soát.

Một response thân thiện có thể chỉ gồm mã nghiệp vụ như `CUSTOMER_EMAIL_ALREADY_EXISTS` và ID yêu cầu; exception chain ban đầu vẫn tồn tại trong log phía server. Không cần sửa hoặc xóa cause để có response an toàn.

### Logging

Nếu dùng logging framework, ghi **exception object** để giữ stack trace và cause chain:

```java
// Fragment ứng dụng: logger là SLF4J Logger đã cấu hình.
logger.error("Save customer failed: requestId={}", requestId, ex);
```

Tránh:

```java
// Chỉ có message, bỏ stack trace/cause và có thể chứa SQL nhạy cảm.
logger.error(ex.getMessage());
```

Không log lặp cùng một exception ở mọi tầng nếu không có ích; cấu trúc log nên giữ type, trace và các metadata đã được cho phép, không ghi nguyên vẹn tham số nhạy cảm. Việc Spring giữ `cause` **không** đồng nghĩa ứng dụng phải xuất chi tiết cause cho người dùng cuối.

## 9. Những lỗi thực hành thường gặp

| Cách làm sai | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| `throw new RuntimeException(e.getMessage())` | Mất `SQLException`, stack trace và chain | `throw new RuntimeException("context", e)` |
| `throw new DataIntegrityViolationException("error")` | Bỏ cause gốc; dễ che lỗi sai nhóm | Dùng constructor `(message, SQLException)` khi thật sự thuộc nhóm |
| `catch (SQLException e)` quanh lệnh `JdbcTemplate.update` | API đã dịch thành `DataAccessException`, catch này không xử lý đường lỗi mong muốn | Catch kiểu Spring phù hợp |
| `((SQLException) dae.getCause()).getSQLState()` không kiểm tra | Cause có thể không phải SQLException trực tiếp | Dùng `instanceof` hoặc duyệt cause |
| Phân loại lỗi bằng `message.contains("duplicate")` | Message thay đổi theo driver, locale, phiên bản | Sử dụng lớp Spring / SQLState / vendor code |
| Custom translator luôn trả một loại lỗi | Mọi sự cố bị phân loại sai, fallback không chạy | Chỉ map trường hợp chắc chắn; còn lại `return null` |
| Translator trả `null` rồi bỏ qua lỗi | Lỗi không được báo và tác vụ có thể tiếp tục sai | Tạo `UncategorizedSQLException` hoặc để `JdbcTemplate` xử lý |
| Chỉ xem `getCause()` trên `BatchUpdateException` | Có thể bỏ mất `getNextException()` và update counts | Giữ đối tượng batch gốc; kiểm tra chuỗi JDBC riêng |
| Nuốt exception trong `@Transactional` | Có thể commit thay vì rollback | Rethrow hoặc đánh dấu rollback theo thiết kế |
| Đưa `SQLException.getMessage()` vào HTTP response | Lộ chi tiết hệ thống hoặc dữ liệu | Trả error code nghiệp vụ; log hạn chế ở server |
| Retry mọi `TransientDataAccessException` ngay tại DAO | Có thể retry từng statement sau transaction đã lỗi | Phục hồi/rollback rồi retry đúng phạm vi nghiệp vụ |

## 10. Kiểm thử bản dịch và khả năng giữ nguyên nhân

**Kiểm thử translator bằng lỗi mô phỏng:**

1. Tạo `SQLException` có `SQLState` và `vendorCode` đã biết.
2. Gọi translator với task/sql rõ ràng; xác nhận loại `DataAccessException` mong đợi.
3. Với custom mapper, dùng `assertSame(original, translated.getCause())` để chứng minh giữ **chính đối tượng** SQLException gốc.
4. Với mã không thuộc custom mapping, xác nhận fallback vẫn chạy (hoặc trả `null` khi không có translator phù hợp).
5. Tạo `SQLException` có `setNextException(...)` rồi bảo đảm bản được bọc vẫn cho phép đọc chuỗi đó.
6. Tạo `BatchUpdateException` và kiểm tra giữ được `getUpdateCounts()`, lỗi chi tiết và cách transaction rollback.

**Kiểm thử tích hợp với database thật:**

- Tạo một lỗi `UNIQUE` và một lỗi `FOREIGN KEY`; loại Spring exception có thể giống ở cấp cha nhưng SQLState/vendor code khác.
- Tạo lỗi SQL sai cú pháp và lỗi kết nối để kiểm tra cách translator/driver phân loại.
- Đối chiếu phiên bản Spring và driver thực tế, nhất là khi hệ thống đổi database.
- Tạo một transaction có nhiều thao tác: gây lỗi giữa chừng và xác minh rollback thật sự, không chỉ kiểm tra exception class.
- Quan sát log để chắc chắn stack trace/cause vẫn có nhưng dữ liệu nhạy cảm không bị đưa vào HTTP response.

**Checklist trước khi đưa vào production:**

- [ ] Dùng đúng `DataAccessException`/các lớp con để thể hiện chính xác nhóm lỗi.
- [ ] Nếu tạo wrapper, constructor phải nhận và lưu `Throwable cause`.
- [ ] Không phụ thuộc vào message string; dùng loại exception/mã lỗi đã xác minh.
- [ ] Khi cần chẩn đoán JDBC, truy xuất an toàn `SQLException` trong cause chain.
- [ ] Với batch, bảo toàn cả `BatchUpdateException`, `nextException` và update counts.
- [ ] Custom translator xử lý mã được nhận diện rồi trả `null` cho lỗi còn lại.
- [ ] Có phương án cho lỗi chưa phân loại (`UncategorizedSQLException`).
- [ ] Ranh giới transaction/rollback/retry rõ ràng, không nuốt ngoại lệ.
- [ ] Logging có stack trace và correlation ID; public API không lộ SQL/secret.

**Ghi nhớ:** ngoại lệ được dịch có giá trị vì **cho phép tầng nghiệp vụ hiểu đúng loại lỗi**. Ngoại lệ gốc được giữ có giá trị vì **cho phép tìm chính xác nguyên nhân kỹ thuật**. Việc tạo `DataAccessException` với `SQLException` nguyên bản làm cause, cùng cách duyệt đúng `cause` và `nextException`, bảo toàn cả hai khả năng đó.

### Tài liệu tham khảo

- Spring Framework 6.2 – JDBC error handling và `SQLExceptionTranslator`: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html
- Spring JDBC – `SQLExceptionTranslator` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jdbc/support/SQLExceptionTranslator.html
- Spring – `SQLExceptionSubclassTranslator` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jdbc/support/SQLExceptionSubclassTranslator.html
- Spring – `SQLErrorCodeSQLExceptionTranslator`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jdbc/support/SQLErrorCodeSQLExceptionTranslator.html
- Spring – `DataAccessException` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/dao/DataAccessException.html
- Spring – `UncategorizedSQLException`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jdbc/UncategorizedSQLException.html
- Java SE 17 – `SQLException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html
- Java SE 17 – `BatchUpdateException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html
