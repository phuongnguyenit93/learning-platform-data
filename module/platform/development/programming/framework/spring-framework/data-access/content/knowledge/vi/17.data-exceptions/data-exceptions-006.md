# BadSqlGrammarException và lỗi SQL trong Spring JDBC

## 1. Học gì từ lỗi BadSqlGrammarException?

Khi ứng dụng gọi cơ sở dữ liệu qua `JdbcTemplate`, có thể xuất hiện thông báo như sau:

```text
org.springframework.jdbc.BadSqlGrammarException:
PreparedStatementCallback; bad SQL grammar
[SELECT missing_column FROM customer WHERE id = ?]
```

Đây là **ví dụ hình thức thông báo**, không phải log cố định của mọi phiên bản Spring hay JDBC driver. Nội dung thực tế còn có thông điệp chi tiết và nguyên nhân `SQLException` do driver trả về.

Điều cần hiểu: `BadSqlGrammarException` thông báo rằng **lệnh SQL bị database/driver từ chối và Spring phân loại lỗi đó vào nhóm SQL không hợp lệ**. Lỗi có thể là sai cú pháp, nhưng cũng có thể do bảng/cột không tồn tại, sai schema, tên định danh hoặc cú pháp không tương thích với hệ quản trị đang dùng. Vì vậy, đọc riêng chữ “grammar” chưa đủ để xác định lỗi.

Sau bài này, bạn có thể:

1. Nhận diện `BadSqlGrammarException` và vị trí của nó trong hệ ngoại lệ `DataAccessException`.
2. Hiểu cơ chế `SQLExceptionTranslator` chuyển lỗi JDBC thành ngoại lệ Spring.
3. Đọc SQL gây lỗi, `SQLException` gốc, `SQLState` và mã lỗi do database cung cấp.
4. Phân biệt lỗi SQL không hợp lệ với lỗi trùng khóa, lỗi không có bản ghi, lỗi kết nối và lỗi API.
5. Sửa lỗi ở đúng tầng, kiểm thử trên database mục tiêu và tránh retry vô ích.

Phạm vi chính là **Spring JDBC**. Một tên ngoại lệ tương tự có thể xuất hiện ở công nghệ dữ liệu khác, nhưng không nên mặc định quá trình dịch lỗi và cách khắc phục giống hệt nhau.

## 2. BadSqlGrammarException là gì, nằm ở đâu trong cây ngoại lệ?

Lớp chính xác là:

```java
org.springframework.jdbc.BadSqlGrammarException
```

Trong Spring Framework 6.x, quan hệ kế thừa cốt lõi là:

```text
java.lang.RuntimeException
  └─ org.springframework.core.NestedRuntimeException
      └─ org.springframework.dao.DataAccessException
          └─ org.springframework.dao.NonTransientDataAccessException
              └─ org.springframework.dao.InvalidDataAccessResourceUsageException
                  └─ org.springframework.jdbc.BadSqlGrammarException
```

Hệ quả quan trọng:

- **Unchecked exception:** `BadSqlGrammarException` là `RuntimeException`, nên ứng dụng không bắt buộc khai báo `throws` hoặc `catch` theo quy tắc checked exception của Java.
- **Độc lập với chiến lược truy cập dữ liệu ở tầng cha:** nghiệp vụ có thể bắt `DataAccessException` để xử lý chung nhiều loại lỗi; nhưng bắt quá rộng sẽ làm mất khả năng phân loại nguyên nhân.
- **Không phải lỗi tạm thời:** lớp này thuộc nhánh `NonTransientDataAccessException`. Chạy lại nguyên lệnh SQL với cùng schema và điều kiện thường vẫn lỗi cho đến khi sửa nguyên nhân. Không áp dụng retry tự động như với một số lỗi kết nối tạm thời.
- **Có nguyên nhân JDBC:** khi Spring tạo `BadSqlGrammarException` từ JDBC, nó giữ `SQLException` gốc để truy vết thông tin do driver cung cấp.

Những API đặc trưng:

| API | Giá trị | Ý nghĩa khi điều tra |
| --- | --- | --- |
| `ex.getSql()` | `String` | SQL mà Spring ghi nhận đã gây lỗi; thường còn placeholder `?`. |
| `ex.getSQLException()` | `SQLException` gốc | Có thể đọc `getSQLState()`, `getErrorCode()`, `getMessage()` và chuỗi lỗi bổ sung. |
| `ex.getCause()` / `getRootCause()` | `Throwable` | Hỗ trợ đi theo chuỗi nguyên nhân; vẫn kiểm tra kiểu trước khi ép kiểu. |
| `ex.getMessage()` | Chuỗi chẩn đoán | Chứa ngữ cảnh thao tác/SQL/driver, không phải định dạng thông báo ổn định để parse bằng chương trình. |

Không nên đưa riêng `getMessage()` trực tiếp ra HTTP response: thông báo có thể lộ schema, SQL hoặc chi tiết nội bộ và cũng không phải hợp đồng lỗi ổn định cho client.

## 3. Tại sao chương trình nhận BadSqlGrammarException thay vì SQLException?

JDBC thuần thường làm việc với `java.sql.SQLException`, là checked exception. Spring JDBC thực hiện bước chuyển đổi qua `SQLExceptionTranslator`:

```text
Repository / Service
      |
      | gọi JdbcTemplate.query(...), update(...), execute(...)
      v
JdbcTemplate + PreparedStatement / CallableStatement
      |
      | JDBC driver kiểm tra SQL với database
      v
SQLException (SQLState, vendor error code, thông điệp)
      |
      v
SQLExceptionTranslator
      |
      +-- phân loại được: BadSqlGrammarException / loại DataAccessException khác
      |
      +-- không phân loại cụ thể được: UncategorizedSQLException (ví dụ)
      v
Code Java nhận DataAccessException (RuntimeException)
```

Các lớp liên quan:

- `org.springframework.jdbc.support.SQLExceptionTranslator`: interface với phương thức `translate(String task, String sql, SQLException ex)`.
- `SQLExceptionSubclassTranslator`: sử dụng các subclass JDBC 4 (chẳng hạn `SQLSyntaxErrorException`) và khi cần dựa vào translator theo `SQLState`.
- `SQLStateSQLExceptionTranslator`: phân loại theo mã `SQLState` do database cung cấp.
- `SQLErrorCodeSQLExceptionTranslator`: hỗ trợ bảng mapping mã lỗi cụ thể theo vendor, hữu ích khi cần tính tương thích cũ hoặc cách phân loại riêng.

Theo Spring Framework 6.x, `SQLExceptionSubclassTranslator` là hướng dịch mặc định; khi có `sql-error-codes.xml` ở classpath root, hệ thống có thể dùng `SQLErrorCodeSQLExceptionTranslator`. Ứng dụng cũng có thể tự cấu hình translator trên `JdbcTemplate`. Vì vậy **cùng một lỗi từ database không nhất thiết luôn trở thành cùng một subclass của `DataAccessException` trong mọi dự án**.

Ví dụ ý tưởng:

```java
// JDBC thuần: caller thường phải xử lý SQLException.
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT missing_column FROM customer")) {
    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
} catch (SQLException ex) {
    // Kiểm tra SQLState / mã lỗi vendor, tự quyết định cách xử lý.
}
```

Đây chỉ là **đoạn minh họa**, cần `connection` và import `java.sql.*`; không có `main` và không tự chạy. Trong cùng lỗi, đường gọi qua `JdbcTemplate` thường trả về `DataAccessException` do Spring dịch. `@Repository` tự nó không biến mọi đoạn JDBC thuần bắt `SQLException` thành `BadSqlGrammarException`; cần dùng API/translation phù hợp.

### Vì sao tên lỗi không nhất thiết là “thiếu dấu phẩy”?

Tên “bad SQL grammar” khá rộng. Tài liệu Spring xác định lỗi này cho SQL không hợp lệ và đề cập cả các trường hợp *no such table* hoặc *no such column*. Ví dụ:

```sql
-- Câu lệnh sai cú pháp:
SELEC id FROM customer;

-- Câu lệnh đúng ngữ pháp tổng thể nhưng nhắc đến cột không tồn tại:
SELECT missing_column FROM customer;

-- Câu lệnh đúng về cấu trúc nhưng bảng không tồn tại trong schema hiện tại:
SELECT id FROM customer_not_created;
```

Cả ba có thể được driver báo trong nhóm lỗi SQL, rồi được Spring dịch thành `BadSqlGrammarException`. Tuy nhiên **cách phân loại chính xác phụ thuộc driver và translator**; không xem một tên exception là bằng chứng duy nhất cho nguyên nhân.

## 4. Các lỗi SQL thường gặp và nơi cần kiểm tra

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra đầu tiên |
| --- | --- | --- |
| `syntax error near ...` | Sai từ khóa, dấu phẩy, dấu ngoặc, alias, thứ tự mệnh đề. | SQL đầy đủ, vị trí lỗi do driver chỉ ra, cú pháp theo dialect. |
| `table ... not found` / `relation does not exist` | Chưa chạy migration, sai schema, kết nối nhầm database, tên bảng khác case. | DataSource/URL, schema hiện tại, migration, tên bảng thực. |
| `column ... not found` | Sai cột, alias, thay đổi schema, mapping DTO khác tên SQL. | DDL, projection, tên cột thực tế, alias và viết hoa/thường. |
| `unknown function` | Gọi function không có trong DB, sai schema hoặc cú pháp của vendor khác. | Phiên bản DB, chữ ký function, dialect, quyền thực thi. |
| `invalid identifier` / lỗi tên có dấu quote | Tên định danh thuộc từ khóa SQL hoặc cách quote/case không đúng. | Quy tắc quote/case của RDBMS; SQL thực gửi đi. |
| SQL chạy ở H2 nhưng lỗi ở PostgreSQL/MySQL | Dialect khác nhau, kiểu dữ liệu/`RETURNING`/`LIMIT`/`UPSERT` không đồng nhất. | Thử lại bằng integration test trên cùng loại database production. |
| SQL có `?` nhưng tham số truyền không khớp | Sai số lượng hoặc kiểu bind, hoặc code truyền args sai. | Overload `JdbcTemplate`, danh sách tham số; **không mặc định** lỗi luôn là `BadSqlGrammarException`. |

**Phân biệt ba lớp nguyên nhân:** SQL *syntax* (cấu trúc câu lệnh), *schema* (các object mà SQL tham chiếu), *environment* (DB URL, schema search path, migration version, quyền). Một câu SQL biên dịch ở môi trường A vẫn có thể lỗi ở B nếu schema khác.

### Ví dụ lỗi định danh dễ bị bỏ sót

```sql
SELECT c.email
FROM customer AS c
WHERE customer.id = ?;
```

Trong nhiều RDBMS, khi đã đặt alias `c`, tham chiếu `customer.id` trong cùng query có thể không hợp lệ; thường phải dùng `c.id`. Một vấn đề giống “SQL grammar” thực ra có thể chỉ là lỗi alias.

Cũng nên để ý các cột đặt tên như `order` hoặc `user`, vốn có thể trùng từ khóa tùy DB. Cách quote không đồng nhất: có hệ quản trị dùng dấu ngoặc kép, một số dùng backtick hoặc ngoặc vuông. Đừng thay ký tự quote bằng mẹo chung cho mọi RDBMS.

## 5. Đọc thông tin chuẩn từ exception để khoanh vùng lỗi

Trong xử lý lỗi Spring JDBC, nên bắt `BadSqlGrammarException` ở tầng cần chẩn đoán hoặc mapping lỗi; sau đó lấy thông tin từ chính exception và nguyên nhân JDBC.

```java
import java.sql.SQLException;
import org.springframework.jdbc.BadSqlGrammarException;

try {
    jdbcTemplate.queryForObject(
            "SELECT missing_column FROM customer WHERE id = ?",
            String.class, customerId);
} catch (BadSqlGrammarException ex) {
    // SQL mà JdbcTemplate báo là đang thực thi:
    String sql = ex.getSql();

    // Lỗi gốc từ JDBC driver:
    SQLException jdbcError = ex.getSQLException();

    String state = jdbcError == null ? null : jdbcError.getSQLState();
    Integer vendorCode =
            jdbcError == null ? null : jdbcError.getErrorCode();

    // Hãy dùng hệ thống log tập trung của ứng dụng; ví dụ ở đây
    // chỉ minh họa dữ liệu chẩn đoán cần ghi nhận.
    System.err.println("SQLState=" + state + ", vendorCode=" + vendorCode);
    System.err.println("SQL=" + sql);

    throw ex;
}
```

Đây là **đoạn code minh họa trong repository**, cần các biến `jdbcTemplate` và `customerId`; không phải chương trình chạy độc lập. Với production, nên dùng logger và mã tương quan request; không in SQL/parameter chứa dữ liệu nhạy cảm ra nơi công khai.

Ý nghĩa từng trường:

1. **`getSql()`:** giúp biết câu lệnh nào bị lỗi, đặc biệt khi có nhiều nhánh query. Nó có thể còn `?` và không bắt buộc chứa giá trị đã bind. Vì thế không nên cố thay `?` bằng cách nối chuỗi giá trị thủ công để “tái tạo” SQL.
2. **`getSQLException().getSQLState()`:** mã dạng chuỗi do driver trả theo chuẩn SQLState hoặc mở rộng vendor. Hai ký tự đầu thường cho biết nhóm lỗi; không có nghĩa mọi database luôn trả mã đầy đủ/hữu ích.
3. **`getSQLException().getErrorCode()`:** mã số vendor-specific; chỉ diễn giải bằng tài liệu của đúng hệ quản trị và driver.
4. **`getSQLException().getMessage()`:** thông điệp từ database, có thể nêu object bị thiếu hoặc vị trí lỗi. Không dựa vào substring thông điệp đã bản địa hóa để xây logic nghiệp vụ.
5. **`getSQLException().getNextException()`:** một số driver cung cấp chuỗi lỗi JDBC bổ sung; hữu ích khi root message không đủ.
6. **`getRootCause()` và stack trace:** cho thấy nơi gọi Spring/JDBC và ngoại lệ gốc. Nên giữ nguyên cause khi bọc ngoại lệ.

Ví dụ trong H2, lỗi “column not found” thường có `SQLState = 42S22`; lớp `42` chỉ nhóm cú pháp/quy tắc truy cập SQL, còn phần `S22` là mã cụ thể. Với PostgreSQL, mã “undefined column” thường là `42703`. **Không hard-code** một mã để nhận diện lỗi trên tất cả RDBMS.

## 6. Demo Java 17+ chạy được: cố tình tạo lỗi SQL rồi chẩn đoán

Bài demo dùng **Spring JDBC + H2 in-memory**, hoàn toàn riêng biệt với mã của ứng dụng thật. Chương trình tạo bảng có cột `full_name`, chèn một bản ghi hợp lệ, rồi cố truy vấn `missing_column` để kích hoạt lỗi SQL. Cuối cùng, chương trình truy vấn lại bảng đúng để chứng minh lỗi SQL sai không biến dữ liệu hợp lệ thành lỗi.

Cấu trúc:

```text
bad-sql-grammar-demo/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── Demo.java
```

`build.gradle` (Gradle Groovy DSL, với JDK 17+):

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'Demo'
}
```

`src/main/java/Demo.java`:

```java
import java.sql.SQLException;

import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class Demo {

    private static final String WRONG_SQL =
            "SELECT missing_column FROM customer WHERE id = ?";

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:bad_sql_demo;DB_CLOSE_DELAY=-1", "sa", "");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE customer (
                    id BIGINT PRIMARY KEY,
                    full_name VARCHAR(100) NOT NULL
                )
                """);

        jdbc.update(
                "INSERT INTO customer (id, full_name) VALUES (?, ?)",
                1L, "An");

        try {
            jdbc.queryForObject(WRONG_SQL, String.class, 1L);
            throw new AssertionError(
                    "Expected BadSqlGrammarException");
        } catch (BadSqlGrammarException ex) {
            SQLException jdbcError = ex.getSQLException();
            if (jdbcError == null || jdbcError.getSQLState() == null) {
                throw new IllegalStateException(
                        "Expected SQLState from H2", ex);
            }

            String state = jdbcError.getSQLState();
            System.out.println("caught=" + ex.getClass().getSimpleName());
            System.out.println("sqlStateClass=" + state.substring(0, 2));
            System.out.println("sqlMatches=" + WRONG_SQL.equals(ex.getSql()));
        }

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer", Integer.class);
        System.out.println("rows=" + rows);
    }
}
```

Tại thư mục dự án, thực thi:

```bash
gradle run
```

Nếu dự án đã có Gradle Wrapper, có thể chạy `./gradlew run` trên Linux/macOS hoặc `.\gradlew.bat run` trong PowerShell Windows. Cần tải dependency Spring và H2 qua Maven Central nếu local cache chưa có.

**Stdout do `Demo.main()` in ra** (không tính log Gradle và thông tin startup của thư viện):

```text
caught=BadSqlGrammarException
sqlStateClass=42
sqlMatches=true
rows=1
```

Cách đọc kết quả:

- `caught=BadSqlGrammarException`: Spring dịch lỗi driver thành subclass tương ứng.
- `sqlStateClass=42`: H2 báo lỗi thuộc nhóm SQL syntax/access; không cần dựa vào toàn bộ mã vendor-specific.
- `sqlMatches=true`: `getSql()` ghi nhận chính câu query lỗi.
- `rows=1`: câu `INSERT` trước đó hợp lệ; query sai không làm mất dữ liệu đã ghi. Demo không mở transaction bao quanh các thao tác.

Ví dụ dùng `DriverManagerDataSource` để đơn giản hóa môi trường thử nghiệm; đây không phải connection pool production. Đừng lấy output trên làm cam kết cho DB khác hoặc translator do ứng dụng tùy chỉnh.

### Thay câu sai bằng câu đúng

Chỉ cần thay `WRONG_SQL` thành câu truy vấn hợp lệ:

```sql
SELECT full_name FROM customer WHERE id = ?;
```

Lúc đó câu lệnh có thể trả `"An"` theo ví dụ. Phải đồng thời **bỏ đoạn cố tình yêu cầu ném lỗi** trong khối `try`; không chạy phần kiểm thử lỗi khi SQL đã được sửa. Khi lỗi phát sinh từ schema chưa có cột, hướng sửa có thể là migration/schema thật, thay vì đổi SQL một cách tùy tiện.

## 7. Các loại lỗi dữ liệu thường bị nhầm lẫn

Không phải mọi lỗi xảy ra lúc query đều là `BadSqlGrammarException`. Dưới đây là những trường hợp cần phân biệt:

| Tình huống | Ngoại lệ Spring có thể gặp | Ý nghĩa |
| --- | --- | --- |
| SQL sai cú pháp, bảng/cột không tồn tại | `BadSqlGrammarException` | SQL bị driver/database xem là không hợp lệ theo cách translator phân loại. |
| `SELECT` hợp lệ nhưng không có hàng khi dùng `queryForObject` kỳ vọng đúng một hàng | `EmptyResultDataAccessException` | Không có kết quả dữ liệu; bản thân cú pháp SQL vẫn hợp lệ. |
| `queryForObject` kỳ vọng một hàng nhưng query trả nhiều hàng | `IncorrectResultSizeDataAccessException` | Sai số lượng kết quả theo contract ứng dụng. |
| `INSERT` vi phạm unique/primary key | `DuplicateKeyException` hoặc nhóm `DataIntegrityViolationException` | Vi phạm ràng buộc, không phải mặc nhiên sai ngữ pháp SQL. |
| `INSERT` vi phạm NOT NULL/FK/CHECK | `DataIntegrityViolationException` | Dữ liệu không thỏa ràng buộc DB. |
| Không lấy được JDBC connection | `CannotGetJdbcConnectionException` (hoặc nhóm lỗi kết nối khác) | Hệ thống không có kết nối để thực thi query. |
| Driver ném SQL error mà translator chưa phân loại cụ thể | `UncategorizedSQLException` | Cần điều tra `SQLException` và cấu hình translator. |
| Dùng API tham số sai từ phía Java trước khi gửi SQL | Có thể là `InvalidDataAccessApiUsageException` hoặc lỗi khác | Không đồng nhất với SQL grammar của database. |

Đây là **các ví dụ phân loại điển hình, không phải quy tắc tuyệt đối cho mọi driver/translator**. Khi ứng dụng có custom exception translator hoặc dùng ORM/JPA/R2DBC thay cho JDBC, subclass cụ thể có thể khác.

### “Không có dữ liệu” khác “SQL sai”

Giả sử bảng `customer` hợp lệ nhưng không có bản ghi `id=99`:

```java
String name = jdbcTemplate.queryForObject(
        "SELECT full_name FROM customer WHERE id = ?",
        String.class, 99L);
```

Nếu query trả **0 hàng**, vấn đề nằm ở contract của `queryForObject` và thường là `EmptyResultDataAccessException`, không phải `BadSqlGrammarException`. Cần quyết định nghiệp vụ cho tình huống không tìm thấy: trả `Optional.empty()`, 404 tại API, hoặc một kết quả domain có ý nghĩa. Không nên “sửa SQL” khi bảng/cột đã đúng.

### “Trùng khóa” khác “SQL sai”

```sql
INSERT INTO customer (id, full_name) VALUES (1, 'An');
INSERT INTO customer (id, full_name) VALUES (1, 'Binh');
```

Câu thứ hai có **cú pháp hợp lệ** nhưng có thể vi phạm `PRIMARY KEY`. Nó thuộc nhóm lỗi toàn vẹn dữ liệu và không nên được xử lý bằng cách đổi dấu phẩy hay retry nguyên câu lệnh vô hạn.

## 8. Quy trình debug BadSqlGrammarException theo từng bước

### Bước 1 — Xác định SQL thực tế và caller

Từ stack trace, tìm service/repository gọi `JdbcTemplate`, `NamedParameterJdbcTemplate` hoặc API đang tạo SQL. Đọc `ex.getSql()` nếu có. Đừng sửa một câu SQL viết giống trong source nhưng không được gọi ở đường xử lý đang lỗi.

Nếu dùng named parameters, chú ý chuỗi SQL ban đầu có dạng `:customerId` nhưng sau khi Spring xử lý có thể thành `?` ở tầng JDBC. Lỗi do thiếu giá trị named parameter có thể phát sinh **trước khi gửi SQL tới database**, dẫn đến một loại exception khác.

### Bước 2 — Đọc thông điệp gốc và mã do driver trả

Ghi nhận `SQLState`, `errorCode`, message và nếu cần `nextException`. Kiểm tra database, driver version và translator hiện đang hoạt động. Ví dụ “column not found” giúp tập trung vào DDL/alias, trong khi “syntax error near LIMIT” cần kiểm tra SQL dialect.

### Bước 3 — Xác minh đúng môi trường dữ liệu

- Database URL, tên catalog/schema, user và quyền hiện tại.
- Migration đã được chạy đến version nào, cột có đúng tên và kiểu không.
- DDL thực tế so với entity/DAO đang triển khai.
- Case/quoting của tên table và column.
- Có deploy nhiều instance dùng database/schema khác nhau không.

Không lấy thành công ở H2 local làm bằng chứng rằng PostgreSQL, MySQL hay Oracle production chắc chắn chấp nhận cùng câu SQL.

### Bước 4 — Thử truy vấn có kiểm soát

Tái hiện trên một database test có schema tương đương; dùng đúng dialect và những tham số hợp lệ. Với thao tác ghi dữ liệu, làm trong môi trường thử nghiệm hoặc transaction rollback khi thích hợp. Không đưa dữ liệu thật hay thông tin bí mật lên công cụ debug công khai.

Cẩn thận với SQL có placeholder `?`: câu hiển thị trong log chưa chắc chạy trực tiếp trong SQL console nếu không thay bằng literal thử nghiệm an toàn, có kiểu thích hợp. Nên giữ cùng kiểu JDBC bind khi tái hiện qua ứng dụng.

### Bước 5 — Sửa tận gốc và viết test hồi quy

Nếu lỗi do cột sai, sửa code hoặc migration theo **schema nguồn sự thật**. Nếu do gọi sai schema, sửa cấu hình kết nối/search path. Nếu do SQL dialect, chọn đúng cú pháp hoặc query tương thích. Viết integration test trên driver mục tiêu, bao gồm cả đường thực thi đã từng báo lỗi.

Đừng làm “fix” như:

```java
try {
    return jdbcTemplate.queryForList(sql);
} catch (BadSqlGrammarException ignored) {
    return java.util.List.of();
}
```

Đoạn này **che mất lỗi hệ thống và biến lỗi query thành danh sách rỗng**, khiến caller hiểu lầm rằng không có dữ liệu. Mã chỉ để minh họa một phản mẫu; nó cần các biến/import thích hợp, không phải chương trình độc lập.

## 9. Xử lý ngoại lệ đúng tầng và không retry mù quáng

Vì `BadSqlGrammarException` là non-transient, retry cùng SQL mà không sửa schema/dialect/tên cột thường không thay đổi kết quả. Cũng không nên dùng exception này để trả trực tiếp toàn bộ lỗi SQL về client.

Trong repository, thường nên để exception đi lên (hoặc ghi thêm ngữ cảnh hữu ích rồi ném lại) để hệ thống quan sát được lỗi. Tại boundary của API, chuyển nó thành phản hồi **lỗi máy chủ phù hợp** với contract ứng dụng, đồng thời ghi log nội bộ có correlation ID.

```java
// Ví dụ minh họa, không phải class độc lập.
try {
    return jdbcTemplate.queryForObject(
            "SELECT full_name FROM customer WHERE id = ?",
            String.class, customerId);
} catch (BadSqlGrammarException ex) {
    SQLException sqlCause = ex.getSQLException();
    String state = sqlCause == null ? null : sqlCause.getSQLState();

    logger.error(
            "CustomerRepository query failed; SQLState={}", state, ex);
    throw ex;
}
```

Đoạn trên cần `logger`, `jdbcTemplate` và `customerId` đã có. Trong Spring Boot, exception không được xử lý thường đi qua cơ chế error handling của web layer; việc biến nó thành mã HTTP cụ thể phải theo quy tắc ứng dụng. Không mặc định “BadSqlGrammarException = HTTP 400”: SQL sai trong repository thường là lỗi phía server, không chứng minh input của client không hợp lệ.

**Phân biệt lỗi request với lỗi query:** nếu người dùng gửi tham số không hợp lệ, hãy validate input ở boundary. Nếu chính code repository tạo câu SQL sai, nên coi đó là vấn đề triển khai/migration. Cả hai có thể cùng xuất hiện trong một request nhưng cần sửa ở nơi khác nhau.

### Transaction có ảnh hưởng gì?

`BadSqlGrammarException` là `RuntimeException`. Với quy tắc mặc định của `@Transactional` trong Spring, ngoại lệ unchecked thoát ra khỏi phương thức transaction thường làm đánh dấu rollback. Tuy nhiên kết quả thực tế phụ thuộc transaction boundary, cấu hình rollback rules, loại transaction manager, autocommit và các thao tác đã commit trước đó.

Không tự kết luận “mọi lệnh SQL trước lỗi đều đã rollback” nếu chúng chạy ở transaction khác hoặc autocommit. Ngược lại, không nuốt exception để tiếp tục giao dịch khi trạng thái DB/transaction không còn rõ ràng.

## 10. Test và khả năng quan sát

Nên có các kiểm thử sau, theo mục tiêu bài học:

1. **Kiểm thử truy vấn đúng:** với bảng có `id` và `full_name`, `SELECT full_name ...` trả giá trị đúng cho ID đã tồn tại.
2. **Kiểm thử truy vấn sai:** truy vấn cột không tồn tại phải cho thấy đường dịch `SQLException` -> `DataAccessException` và trong cấu hình driver hiện tại là `BadSqlGrammarException`.
3. **Kiểm thử SQLState:** xác minh class `42` với H2 khi dùng cột không tồn tại; không khẳng định mã `42S22` áp dụng trên mọi RDBMS.
4. **Kiểm thử tình huống không có hàng:** với SQL hợp lệ và ID không tồn tại, xử lý đúng `EmptyResultDataAccessException` hoặc mapping sang kết quả nghiệp vụ.
5. **Kiểm thử constraint:** trùng khóa/NOT NULL được phân loại thành nhóm integrity, không bị catch nhầm vào “không có dữ liệu”.
6. **Kiểm thử migration:** CI hoặc integration test phải áp dụng DDL/migration tương đương môi trường đích trước khi chạy repository tests.
7. **Kiểm thử đường transaction:** thao tác ghi có lỗi query sau đó nên có test xác nhận hành vi rollback phù hợp.
8. **Log an toàn:** log task, vị trí repository, SQLState, vendor code, correlation ID và stack trace ở nơi nội bộ; kiểm soát SQL và parameters chứa thông tin nhạy cảm.

`JdbcTemplate` có hỗ trợ cấu hình `SQLExceptionTranslator` riêng; chỉ thay translator khi có nhu cầu rõ ràng và có test cho từng mã lỗi/vendor. **Đổi translator để một lỗi “trông bớt nghiêm trọng” không sửa được SQL sai**.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `BadSqlGrammarException` có phải chỉ dành cho lỗi đánh sai từ khóa SQL không?

Không. Nó có thể đại diện cho SQL không hợp lệ vì bảng/cột không tồn tại, schema sai hoặc cú pháp/dialect không phù hợp. Cần đọc `SQLException` gốc để biết chi tiết.

**Câu 2.** Trong `JdbcTemplate`, tại sao không bắt buộc khai báo `throws SQLException`?

Vì Spring dùng `SQLExceptionTranslator` dịch lỗi JDBC thành các `DataAccessException` là unchecked exception, khi lỗi xảy ra qua đường thực thi được Spring quản lý.

**Câu 3.** Hai thông tin cụ thể nào nên kiểm tra từ nguyên nhân JDBC?

`SQLException.getSQLState()` và `getErrorCode()`, kèm `getMessage()` và SQL gây lỗi; không dựa riêng vào message `bad SQL grammar`.

**Câu 4.** `SELECT` đúng nhưng không có hàng với `queryForObject` thường ném gì?

`EmptyResultDataAccessException`, khác với một câu SQL không hợp lệ.

**Câu 5.** Có nên tự động retry `BadSqlGrammarException` ba lần không?

Thông thường không, vì đây là lỗi non-transient. Nếu SQL/schema/driver không thay đổi, lặp lại cùng query không giải quyết được nguyên nhân.

**Câu 6.** Trùng khóa primary key có nhất thiết là `BadSqlGrammarException` không?

Không. Driver và translator thường xếp vào `DuplicateKeyException` hoặc `DataIntegrityViolationException`. Cú pháp `INSERT` có thể hoàn toàn hợp lệ dù dữ liệu vi phạm constraint.

## 12. Ghi nhớ

```text
JdbcTemplate / Spring JDBC
       |
       v
     SQL query/update
       |
       v
SQLException do driver/database trả
  ├─ SQLState
  ├─ vendor error code
  └─ message / nextException
       |
       v
SQLExceptionTranslator
       |
       v
BadSqlGrammarException (một nhánh DataAccessException)
       |
       v
Đọc getSql() + getSQLException()
       |
       v
Đối chiếu SQL + schema + dialect + môi trường
       |
       v
Sửa gốc lỗi và integration test
```

**Quy tắc cốt lõi:** `BadSqlGrammarException` nói rằng Spring đã phân loại lỗi SQL thành nhóm không hợp lệ; nó **không tự chỉ ra nguyên nhân chính xác**. Hãy đọc SQL đang chạy, kiểm tra `SQLException` gốc, xác minh schema/dialect/connection và sửa nguyên nhân. Không biến lỗi SQL thành kết quả rỗng, không lộ thông tin nhạy cảm và không retry không có cơ sở.

### Tài liệu tham khảo chính thức

- Spring Framework Reference — *Using SQLExceptionTranslator* trong JDBC Core: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html
- Spring Framework Javadoc — `BadSqlGrammarException`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/BadSqlGrammarException.html
- Spring Framework Javadoc — `SQLExceptionTranslator`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/SQLExceptionTranslator.html
- Spring Framework Javadoc — `SQLExceptionSubclassTranslator`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/SQLExceptionSubclassTranslator.html
- Spring Framework Javadoc — `InvalidDataAccessResourceUsageException`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/dao/InvalidDataAccessResourceUsageException.html
- H2 Database — *Error Codes*: https://h2database.com/html/error-codes.html
