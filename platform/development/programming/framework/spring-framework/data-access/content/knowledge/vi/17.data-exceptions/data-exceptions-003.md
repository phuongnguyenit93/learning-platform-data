# SQLExceptionTranslator và lựa chọn cách phân loại ngoại lệ dữ liệu

## 1. Mục tiêu: từ lỗi JDBC sang lỗi có ý nghĩa với ứng dụng

Trong Spring Framework – Data Access, thao tác JDBC có thể phát sinh `java.sql.SQLException`. Ngoại lệ này cung cấp thông tin từ trình điều khiển và cơ sở dữ liệu, nhưng tên lớp, mã lỗi và thông điệp không thống nhất hoàn toàn giữa PostgreSQL, MySQL, Oracle, SQL Server hay các JDBC driver. Nếu tầng service phải hiểu từng mã lỗi của từng database, mã nghiệp vụ sẽ phụ thuộc chặt vào hạ tầng và dễ sai khi thay driver.

`org.springframework.jdbc.support.SQLExceptionTranslator` là **chiến lược phân loại**: nhận `SQLException` và chuyển thành một ngoại lệ trong hệ phân cấp `org.springframework.dao.DataAccessException`. `JdbcTemplate` và các thành phần liên quan dùng cơ chế này để trình bày lỗi truy cập dữ liệu theo cách nhất quán hơn.

Cần hiểu ba câu hỏi tách biệt:

1. **Lỗi JDBC thực tế là gì?** Đọc `SQLException`, `SQLState`, vendor code, chuỗi nguyên nhân và thông tin driver.
2. **Spring phân loại lỗi này thành gì?** Ví dụ `DuplicateKeyException`, `DataIntegrityViolationException`, `BadSqlGrammarException`, `CannotAcquireLockException` hoặc `UncategorizedSQLException`.
3. **Ứng dụng phải làm gì?** Sửa đầu vào, xử lý xung đột, rollback, retry có kiểm soát hay báo lỗi hạ tầng. Translator **không tự retry, không commit/rollback thay transaction manager và không quyết định HTTP status**.

Bài học tập trung vào Spring JDBC 6.x và Java 17+. Với module dùng Spring Framework phiên bản khác, hãy kiểm tra lại translator mặc định và bảng ánh xạ của đúng phiên bản đó.

## 2. Đường đi của một SQLException trong Spring JDBC

~~~text
SQL + tham số
    |
    v
JdbcTemplate.query/update/batchUpdate/execute
    |
    v
JDBC driver + database
    |
    +-- thành công --> giá trị/danh sách được ánh xạ
    |
    +-- SQLException
            |
            v
       SQLExceptionTranslator
            |
            +-- khớp subclass / SQLState / vendor code --> DataAccessException cụ thể
            |
            +-- không khớp --> fallback; nếu vẫn không phân loại được:
                                 UncategorizedSQLException tại tầng JdbcTemplate
            |
            v
       Repository -> Service -> ranh giới giao dịch / API
~~~

Ví dụ một lệnh `INSERT` vi phạm khóa duy nhất có thể được Spring phân loại thành `DuplicateKeyException`. Tuy nhiên, kết quả **không phải lời hứa tuyệt đối**: loại `SQLException` do driver phát ra, `SQLState`, mã vendor, chiến lược translator và phiên bản Spring đều ảnh hưởng kết quả.

`DataAccessException` là ngoại lệ **unchecked** (kế thừa `RuntimeException`), giúp tầng gọi không phải khai báo `throws SQLException` cho mỗi thao tác `JdbcTemplate`. Điều đó **không** có nghĩa mọi lỗi đều tạm thời hoặc có thể retry.

## 3. Hợp đồng của SQLExceptionTranslator

Interface cốt lõi:

~~~java
package org.springframework.jdbc.support;

import java.sql.SQLException;
import org.springframework.dao.DataAccessException;

@FunctionalInterface
public interface SQLExceptionTranslator {
    DataAccessException translate(
        String task, String sql, SQLException ex);
}
~~~

Đây là **chữ ký được rút gọn để học**, không phải mã cần tạo lại trong dự án. Ý nghĩa tham số:

| Tham số | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `task` | Mô tả thao tác, ví dụ `"insert employee"` | Cung cấp ngữ cảnh cho thông điệp/log |
| `sql` | Câu SQL liên quan; có thể `null` | Không giả sử luôn có SQL đầy đủ; tránh để lộ dữ liệu nhạy cảm |
| `ex` | `SQLException` gốc | Chứa SQLState, vendor code, type, cause và next-exception chain |
| Giá trị trả về | `DataAccessException` được phân loại, **hoặc `null`** | `null` nghĩa là translator chưa nhận diện được, không có nghĩa SQL thành công |

Điểm dễ nhầm: gọi `translator.translate(...)` **trực tiếp** có thể nhận `null`. Ngược lại, trong luồng xử lý của `JdbcTemplate`, nếu không translator nào nhận diện được lỗi, template có cơ chế phát ra `UncategorizedSQLException`. Không viết:

~~~java
DataAccessException result = translator.translate(task, sql, ex);
// Sai nếu mặc định result luôn khác null:
throw result;
~~~

Thay vào đó, nếu **tự gọi translator trong một JDBC adapter**, cần quyết định fallback:

~~~java
DataAccessException translated =
    translator.translate("load report", sql, originalSqlException);

if (translated != null) {
    throw translated;
}
throw new org.springframework.jdbc.UncategorizedSQLException(
    "load report", sql, originalSqlException);
~~~

Đoạn trên là **mảnh mã** với biến `translator`, `sql` và `originalSqlException` được cấp từ tầng gọi, không phải một chương trình độc lập. Ưu tiên để `JdbcTemplate` xử lý tài nguyên và translation khi có thể.

Một translator tùy biến nên **giữ `SQLException` gốc trong chuỗi cause** để còn điều tra `SQLState` và mã driver. Khi không nhận diện mã lỗi riêng, hãy trả `null` để cho fallback hoạt động; đừng gán mọi lỗi lạ vào một subtype quá cụ thể.

## 4. Ba tín hiệu đầu vào: loại exception, SQLState và mã vendor

`SQLException` có nhiều nguồn thông tin bổ sung nhau:

| Tín hiệu | Ví dụ | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| Java subclass | `SQLIntegrityConstraintViolationException`, `SQLSyntaxErrorException`, `SQLTimeoutException` | Driver JDBC hiện đại có thể phân loại trực tiếp | Driver có thể trả `SQLException` chung hoặc subclass chưa đủ cụ thể |
| `getSQLState()` | `"23505"`, `"42000"`, `"40001"` | Chuẩn SQLState có ý nghĩa liên hệ giữa các hệ quản trị | Mức độ tuân thủ, mã mở rộng và ý nghĩa chi tiết khác nhau; đôi khi `null` |
| `getErrorCode()` | MySQL `1062`, Oracle `1` (ví dụ duplicate key) | Có thể phân biệt trường hợp rất cụ thể của nhà cung cấp | Không portable: một số mã giống nhau nhưng ý nghĩa khác ở DB khác |
| `getNextException()` / `getCause()` | Lỗi ràng buộc lồng trong lỗi batch | Chẩn đoán chính xác hơn khi lỗi tổng quát bọc lỗi cụ thể | Không phải mọi translator/driver đều duyệt mọi phần tử giống nhau |

**SQLState** thường có 5 ký tự; hai ký tự đầu biểu thị *class*. Ví dụ minh họa phổ biến:

| SQLState class | Diễn giải ở mức khái quát |
| --- | --- |
| `08` | Lỗi liên quan connection |
| `22` | Dữ liệu/giá trị không hợp lệ |
| `23` | Vi phạm ràng buộc dữ liệu |
| `40` | Transaction rollback/serialization/deadlock theo quy định của DB |
| `42` | SQL syntax hoặc lỗi quyền/truy cập đối tượng theo một số driver |
| `HY` | Mã trạng thái do nhà cung cấp/ODBC quy ước, không có cùng ngữ nghĩa chuẩn ở mọi DB |

Ví dụ `23505` thường biểu thị **unique violation**, `23503` thường là **foreign-key violation**, `40001` thường liên quan serialization failure. Nhưng việc Spring trả về chính xác `DuplicateKeyException` hay subtype khác **phụ thuộc translator**. Không xử lý chỉ bằng `sqlState.startsWith("23")` nếu yêu cầu nghiệp vụ là “trùng khóa duy nhất”, vì lớp 23 còn chứa foreign key, NOT NULL và check constraint.

Tham số `sql` truyền cho translator hỗ trợ thông điệp điều tra, không phải nguồn sự thật để đoán lỗi thông qua việc tìm chuỗi `"INSERT"`/`"UPDATE"`. Đặc biệt không kiểm tra text thông điệp driver như `"duplicate entry"` để quyết định logic ổn định.

## 5. DataAccessException: phân loại có ý nghĩa gì với tầng gọi?

Hệ phân cấp Spring có nhiều subtype. Những subtype quan trọng trong lớp Data Access:

| Nhóm / exception | Ý nghĩa thường gặp | Cách xử lý phù hợp |
| --- | --- | --- |
| `DuplicateKeyException` | Vi phạm unique/primary key được nhận diện cụ thể | Xử lý ID trùng, idempotency hoặc thông báo conflict |
| `DataIntegrityViolationException` | Vi phạm ràng buộc/dữ liệu, bao gồm cả unique nếu chưa nhận diện chi tiết | Kiểm tra dữ liệu, ràng buộc và nghiệp vụ; **không retry mù quáng** |
| `BadSqlGrammarException` | SQL/cấu trúc truy vấn không phù hợp DB, ví dụ syntax/sai tên cột/bảng | Sửa SQL, schema, migration; không coi là lỗi đầu vào người dùng mặc định |
| `QueryTimeoutException` | Thao tác bị timeout theo cơ chế driver/DB/framework | Kiểm tra thời gian, transaction và trạng thái kết quả trước khi retry |
| `CannotAcquireLockException` | Không lấy được khóa theo loại lỗi đã được nhận diện | Cân nhắc retry transaction mới có backoff, nếu thao tác an toàn |
| `PessimisticLockingFailureException` | Thất bại khóa theo nhánh phân loại rộng hơn | Kiểm tra lock contention, deadlock, isolation |
| `CannotSerializeTransactionException` | Không thể serialize transaction | Retry **toàn bộ transaction** khi có idempotency |
| `DataAccessResourceFailureException` | Tài nguyên DB/connection không truy cập được | Giám sát hạ tầng, cấu hình, network |
| `UncategorizedSQLException` | JDBC có lỗi nhưng không phân loại cụ thể | Giữ SQLState/vendor code, quan sát và bổ sung case phù hợp |

`DuplicateKeyException` là subtype của `DataIntegrityViolationException`; vì vậy bắt `DataIntegrityViolationException` cũng bao phủ unique error đã nhận diện, nhưng **không thể suy ngược** mọi `DataIntegrityViolationException` là duplicate key.

Không gắn nhãn “transient” cho cả bảng. Một số nhánh `DataAccessException` phản ánh transient hoặc non-transient, nhưng hành vi ứng dụng vẫn cần xét hiệu ứng ghi dữ liệu, transaction, timeout và cách retry. Ví dụ nhận `QueryTimeoutException` **không đảm bảo** cơ sở dữ liệu chưa thực hiện thao tác, đặc biệt khi connection mất hoặc commit không rõ trạng thái.

## 6. Ba chiến lược phân loại chính và lựa chọn mặc định Spring 6.x

### 6.1. SQLExceptionSubclassTranslator

`org.springframework.jdbc.support.SQLExceptionSubclassTranslator` nhận diện các subclass JDBC 4 như `SQLSyntaxErrorException`, `SQLIntegrityConstraintViolationException`, `SQLTimeoutException` và một số trường hợp bổ sung. Nếu chưa đủ thông tin, nó dùng `SQLStateSQLExceptionTranslator` làm fallback.

**Kể từ Spring Framework 6.0, đây là translator mặc định thông thường** khi không có file cấu hình vendor đặc biệt. Ưu điểm: ít phụ thuộc database, không cần khám phá vendor code qua metadata và thường đủ cho hệ thống JDBC hiện đại.

Cần nhớ: hai driver có thể cùng báo lỗi trùng khóa nhưng dùng subclass/SQLState khác nhau. Khi đó kết quả phân loại có thể khác nhau dù SQL nghiệp vụ giống nhau.

### 6.2. SQLStateSQLExceptionTranslator

`org.springframework.jdbc.support.SQLStateSQLExceptionTranslator` dùng SQLState/class và một số mã đặc biệt đã biết để phân loại. Nó không cần nhận diện database product name và thường được đặt **sau** translator chính.

Phù hợp nếu driver cung cấp SQLState đáng tin cậy hoặc bạn cần fallback portable. Nó không thể ánh xạ chính xác mọi tình huống, vì cùng class SQLState có thể chứa nhiều nguyên nhân khác nhau.

### 6.3. SQLErrorCodeSQLExceptionTranslator

`org.springframework.jdbc.support.SQLErrorCodeSQLExceptionTranslator` dựa vào **vendor-specific error codes** với tập cấu hình `SQLErrorCodes` của database. Spring có `SQLErrorCodesFactory`, lấy tên database từ `DatabaseMetaData.getDatabaseProductName()` để chọn bảng mã lỗi thích hợp.

Chiến lược này có thể phân biệt tốt hơn khi subclass/SQLState không đủ, đổi lại cần xác minh tên database, mã lỗi và cấu hình. `sql-error-codes.xml` được đóng gói trong Spring JDBC, và **file do ứng dụng cung cấp cùng tên tại gốc classpath** có thể làm Spring tự chọn chiến lược vendor-code theo tài liệu 6.x. Khi file tùy chỉnh được đặt vào classpath, cần hiểu phạm vi ghi đè/cấu hình và kiểm thử mọi loại DB mà ứng dụng dùng.

**Không đồng nhất “Spring có sẵn bảng mã vendor” với “Spring 6 mặc định luôn dùng bảng mã vendor”.** Khi không có file cấu hình người dùng hoặc cấu hình translator cụ thể, mặc định thông thường của Spring 6 là `SQLExceptionSubclassTranslator`.

### 6.4. Bảng quyết định

| Điều kiện quan sát | Chiến lược đề xuất | Kiểm chứng |
| --- | --- | --- |
| Dự án Spring 6, driver JDBC hiện đại; không có vấn đề phân loại cụ thể | Giữ mặc định `SQLExceptionSubclassTranslator` và fallback SQLState | Integration test các lỗi thực tế |
| Driver trả `SQLException` chung nhưng SQLState có giá trị chuẩn | Dựa vào SQLState fallback; chỉ tùy biến nếu kết quả chưa đạt nghiệp vụ | Thử constraint, timeout và khóa |
| Một vendor code cụ thể cần ánh xạ chính xác hơn | Chọn `SQLErrorCodeSQLExceptionTranslator` / `SQLErrorCodes` cho DB đó | Kiểm tra product name, code, fallback |
| Cần chính sách ngoại lệ chuyên biệt nhưng phạm vi nhỏ | Dùng `setCustomTranslator(...)` cho đúng `JdbcTemplate` | Chỉ trả ngoại lệ ở case khớp, còn lại `null` |
| Ứng dụng dùng nhiều loại database | Ưu tiên phân loại chung; tùy biến **có điều kiện theo DB** nếu cần | Ma trận kiểm thử theo từng driver/version |
| Lỗi chưa biết, chưa có bằng chứng đủ | Giữ `UncategorizedSQLException` hoặc loại rộng phù hợp, bổ sung telemetry | Không tự đoán là retryable |

## 7. Fallback, độ ưu tiên và tình huống không khớp

Một tầng `AbstractFallbackSQLExceptionTranslator` có thể thử translator tùy biến trước, sau đó chiến lược chính, rồi fallback. Với Spring 6.1+, `setCustomTranslator(...)` là cách chủ động chỉ định một translator override.

Chuỗi khái quát trong cấu hình dùng vendor code:

~~~text
custom override (nếu có)
        |
        +-- không nhận diện / trả null
        v
bảng SQLErrorCodes / mã vendor
        |
        +-- không nhận diện
        v
SQLExceptionSubclassTranslator
        |
        +-- không nhận diện
        v
SQLStateSQLExceptionTranslator
        |
        +-- không nhận diện
        v
null từ translator
        |
        v
JdbcTemplate phát UncategorizedSQLException
~~~

Một số cấu hình `SQLErrorCodeSQLExceptionTranslator` còn có custom translator gắn với `SQLErrorCodes` và `CustomSQLErrorCodesTranslation`; thứ tự cụ thể theo tài liệu của phiên bản Spring đang dùng. Hình trên là sơ đồ học tập, không biểu diễn chi tiết mọi nhánh và mọi trường hợp `BatchUpdateException`.

Nguyên tắc thực thi: **chỉ override ngoại lệ bạn nhận diện có bằng chứng**, giữ fallback để không làm mất hành vi chuẩn. Nếu viết custom translator luôn trả `DataIntegrityViolationException` cho mọi `SQLException`, lỗi network hoặc syntax cũng bị phân loại thành ràng buộc dữ liệu.

## 8. Ví dụ Java 17 có thể chạy: quan sát chiến lược phân loại

Ví dụ sau tạo `SQLException` giả lập, **không kết nối DB**. Nó giúp thấy sự khác biệt giữa subclass/SQLState và mã vendor do chính ta khai báo. Kết quả phụ thuộc Spring JDBC được khóa ở **6.2.14**, không đại diện cho mọi driver thật.

Tạo cấu trúc:

~~~text
sql-translation-demo/
  pom.xml
  src/main/java/example/SqlTranslationDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>sql-translation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.14</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/example/SqlTranslationDemo.java`:

~~~java
package example;

import java.sql.SQLException;
import java.sql.SQLIntegrityConstraintViolationException;
import java.sql.SQLSyntaxErrorException;
import java.sql.SQLTimeoutException;

import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.support.SQLExceptionSubclassTranslator;
import org.springframework.jdbc.support.SQLExceptionTranslator;
import org.springframework.jdbc.support.SQLErrorCodeSQLExceptionTranslator;
import org.springframework.jdbc.support.SQLErrorCodes;

public class SqlTranslationDemo {

    private static void printCategory(
            String label,
            SQLExceptionTranslator translator,
            SQLException original) {

        DataAccessException translated =
            translator.translate("sample operation", "SELECT 1", original);

        String category = translated == null
            ? "null"
            : translated.getClass().getSimpleName();

        System.out.println(label + " -> " + category);
    }

    public static void main(String[] args) {
        SQLExceptionTranslator standard =
            new SQLExceptionSubclassTranslator();

        printCategory("unique", standard,
            new SQLIntegrityConstraintViolationException(
                "duplicate key", "23505", 0));

        printCategory("syntax", standard,
            new SQLSyntaxErrorException("invalid SQL", "42000", 0));

        printCategory("timeout", standard,
            new SQLTimeoutException("request timed out", "HYT00", 0));

        printCategory("unknown", standard,
            new SQLException("unrecognized", "ZZ999", 0));

        SQLErrorCodes vendorCodes = new SQLErrorCodes();
        vendorCodes.setDuplicateKeyCodes("7777");

        SQLExceptionTranslator vendor =
            new SQLErrorCodeSQLExceptionTranslator(vendorCodes);

        printCategory("vendor", vendor,
            new SQLException("simulated vendor violation", "HY000", 7777));
    }
}
~~~

Chạy tại thư mục dự án bằng **JDK 17+ và Maven 3.x** (Maven tải thư viện nếu máy chưa cache):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.SqlTranslationDemo
~~~

Kết quả kỳ vọng với Spring JDBC 6.2.14:

~~~text
unique -> DuplicateKeyException
syntax -> BadSqlGrammarException
timeout -> QueryTimeoutException
unknown -> null
vendor -> DuplicateKeyException
~~~

Giải thích:

- `unique`: subclass constraint violation cùng SQLState `23505` đủ để nhận diện duplicate key theo Spring.
- `syntax`: JDBC subclass syntax error được phân loại thành `BadSqlGrammarException`.
- `timeout`: JDBC `SQLTimeoutException` được phân loại thành `QueryTimeoutException`.
- `unknown`: gọi trực tiếp translator nhận `null` vì không có tín hiệu nhận diện phù hợp; nếu đi qua `JdbcTemplate` thì tầng template sẽ tạo ngoại lệ chưa phân loại.
- `vendor`: mã **7777 hoàn toàn giả lập cho bài học**. Cấu hình `SQLErrorCodes` tùy chỉnh mới khiến lỗi đó thành `DuplicateKeyException`. Không đưa mã này vào production nếu không có tài liệu DB chứng minh ý nghĩa.

Dù chương trình chạy được, **đây chỉ là kiểm thử hành vi translator**, không thể chứng minh một JDBC driver thật sẽ phát loại `SQLException`/SQLState/mã vendor như mô phỏng.

## 9. Áp dụng translator trên JdbcTemplate trong ứng dụng Spring

Phần lớn ứng dụng dùng `JdbcTemplate` không cần tự gọi `SQLExceptionTranslator`. Lời gọi `jdbcTemplate.update(...)` sẽ chuyển `SQLException` thành `DataAccessException`:

~~~java
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class EmployeeRepository {
    private final JdbcTemplate jdbc;

    public EmployeeRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void addEmployee(long id, String name) {
        jdbc.update(
            "INSERT INTO employee(id, full_name) VALUES (?, ?)",
            id, name
        );
    }
}
~~~

Đây là **thành phần Spring JDBC**, cần `JdbcTemplate` bean, `DataSource`, driver và bảng `employee` có thật. Không thể chạy class đơn lẻ bằng `javac` nếu chưa khai báo Spring dependencies. Khi xảy ra lỗi JDBC, caller có thể bắt subtype `DataAccessException` tương ứng; không mặc định repository này luôn ném một subtype duy nhất trên mọi DB.

### Cấu hình vendor-code translator cho một JdbcTemplate

Khi có bằng chứng cần ánh xạ theo mã vendor:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.SQLErrorCodeSQLExceptionTranslator;

@Configuration
public class JdbcTranslationConfig {
    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        JdbcTemplate template = new JdbcTemplate(dataSource);
        template.setExceptionTranslator(
            new SQLErrorCodeSQLExceptionTranslator(dataSource)
        );
        return template;
    }
}
~~~

- `SQLErrorCodeSQLExceptionTranslator(dataSource)` dùng metadata để tìm database product name và bảng mã; thao tác này có thể mở connection khi khởi tạo translator. Khi không muốn truy cập metadata, có thể dùng constructor với đúng tên database như `"PostgreSQL"` (nếu đã xác minh tên và mapping).
- `template.setExceptionTranslator(...)` **chỉ áp dụng cho instance `JdbcTemplate` đó**. Những `JdbcTemplate` khác được khởi tạo riêng hoặc do cấu hình khác quản lý không tự nhận chính sách này.
- Ví dụ khai báo một bean `JdbcTemplate`; trong Spring Boot, cần xem bean auto-configuration hiện có và cấu hình DI để các repository nhận đúng instance. Không tạo nhiều template trái chủ đích.
- Không đổi translator chỉ để cố “hết lỗi”. Translator **chỉ đổi cách diễn giải**, không sửa câu SQL, schema, deadlock hay dữ liệu vi phạm ràng buộc.

## 10. Tùy biến có giới hạn và không làm mất fallback

### 10.1. Custom translator bằng setCustomTranslator (Spring 6.1+)

Giả sử database có mã vendor được **tài liệu chính thức xác nhận** đại diện cho một lỗi constraint đặc thù; ta có thể thêm ngoại lệ custom. Đoạn sau dùng mã giả `7777` nhằm minh họa cú pháp:

~~~java
import java.sql.SQLException;

import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.support.SQLErrorCodeSQLExceptionTranslator;

SQLErrorCodeSQLExceptionTranslator translator =
    new SQLErrorCodeSQLExceptionTranslator(dataSource);

translator.setCustomTranslator(
    (String task, String sql, SQLException exception) -> {
        if (exception.getErrorCode() == 7777) {
            return new DataIntegrityViolationException(
                task + ": custom constraint", exception);
        }
        return null; // Cho phép vendor mapping và fallback tiếp tục.
    }
);

jdbcTemplate.setExceptionTranslator(translator);
~~~

Đây là **mảnh mã cấu hình** trong ngữ cảnh đã có `dataSource` và `jdbcTemplate`, không phải một class Java độc lập. Cần kiểm tra cả **database product name** trước khi dùng một mã vendor trong ứng dụng đa DB; cùng mã số có thể đại diện sự cố khác.

Nếu có thể cấu hình đủ bằng `SQLErrorCodes`, cách gán mã vào đúng danh mục có thể đơn giản hơn custom callback. Nhưng **không tái sử dụng bảng mã cho database khác** chỉ vì tên exception mong muốn giống nhau.

### 10.2. Tùy chỉnh bằng SQLErrorCodes

Ví dụ unit test không kết nối DB:

~~~java
SQLErrorCodes codes = new SQLErrorCodes();
codes.setDuplicateKeyCodes("7777");

SQLErrorCodeSQLExceptionTranslator translator =
    new SQLErrorCodeSQLExceptionTranslator(codes);
~~~

Tương tự ví dụ ở mục 8, đây là mã giả lập. Trong production, mã vendor phải được xác minh từ DB/driver và cập nhật cùng quy trình quản lý phiên bản. File `sql-error-codes.xml` nằm tại root classpath có thể khai báo mã theo database, nhưng cần kiểm tra chính xác cấu trúc và phạm vi thay thế mặc định; không tự chép file cũ từ một phiên bản Spring sang phiên bản mới nếu chưa kiểm tra thay đổi trong bảng mã.

### 10.3. Tránh hook customTranslate cũ khi viết mới

Một số ví dụ Spring cũ override `SQLErrorCodeSQLExceptionTranslator.customTranslate(...)`. **Phương thức này đã deprecated từ Spring 6.1**; với mã mới trên Spring 6.1+, ưu tiên `setCustomTranslator(...)` (hoặc cung cấp implementation có fallback rõ ràng). Nếu bảo trì ứng dụng cũ, xem đúng Javadoc phiên bản đang chạy trước khi thay cách mở rộng.

## 11. Phân loại là dữ liệu kỹ thuật, không phải kết luận nghiệp vụ

Cùng một ngoại lệ có thể cần chính sách ứng dụng khác nhau:

- Nếu `DuplicateKeyException` ở thao tác tạo tài nguyên mới: có thể trả conflict hoặc thông báo tên/ID đã tồn tại.
- Nếu duplicate key xảy ra ở idempotency key của request đã xử lý: có thể phải **đọc kết quả lần trước** và trả cùng kết quả, tùy hợp đồng API; không mặc định là lỗi người dùng.
- Nếu `DataIntegrityViolationException` đến từ foreign key: có thể là quan hệ không tồn tại, hoặc bug về thứ tự ghi dữ liệu; cần xem constraint thực tế.
- Nếu `CannotAcquireLockException`: có thể retry transaction **mới** có backoff, jitter và giới hạn số lần, nhưng chỉ sau khi xác minh tính idempotent và trạng thái của thao tác.
- Nếu `QueryTimeoutException`: timeout không có nghĩa write chắc chắn chưa đến DB hoặc chưa commit. Với timeout/đứt kết nối ở thời điểm commit, trạng thái có thể **không chắc chắn**.
- Nếu `BadSqlGrammarException`: thường là lỗi ứng dụng/migration; không nên trả nguyên SQL, stack trace và chi tiết schema cho client.

Một tầng service có thể xử lý theo nhóm rộng:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;

public void perform() {
    try {
        repository.save();
    } catch (DataIntegrityViolationException ex) {
        // Nghiệp vụ: kiểm tra loại constraint và phản hồi phù hợp.
        throw ex; // Giữ nguyên lỗi trong ví dụ này.
    } catch (DataAccessException ex) {
        // Hạ tầng/loại khác: ghi telemetry phù hợp, truyền tiếp.
        throw ex;
    }
}
~~~

Đây là **mảnh mã minh họa** trong lớp có `repository.save()` phù hợp. Bắt loại cụ thể trước loại cha, vì `DataIntegrityViolationException` kế thừa `DataAccessException`. Không đưa mọi `DataAccessException` thành HTTP 409; việc mapping sang response nên có chính sách rõ tại API boundary.

### Transaction và rollback

Trong cấu hình `@Transactional` qua Spring proxy, `DataAccessException` unchecked **được rollback mặc định khi thoát qua transaction interceptor**. Nếu bắt exception rồi chỉ ghi log và return bình thường, transaction interceptor có thể không thấy lỗi; hành vi commit/rollback còn chịu ảnh hưởng trạng thái DB, tình trạng transaction và cách đánh dấu rollback.

- Khi muốn **all-or-nothing**, thông thường để exception thoát khỏi phương thức `@Transactional`.
- Khi muốn retry do deadlock/serialization, thông thường rollback transaction lỗi rồi thử lại **toàn bộ đơn vị công việc** trong transaction mới.
- Khi muốn chấp nhận partial success, phải thiết kế các transaction/chunk, trạng thái và retry/idempotency riêng. Translator không giải quyết các lựa chọn này.

## 12. Xem lỗi gốc để xác minh phân loại

Chỉ nhìn tên Spring exception thường chưa đủ khi điều tra sự cố. Ví dụ với batch update, `BatchUpdateException` có thể bọc một `SQLException` khác trong `getNextException()`, kèm mảng update counts; nhiều driver đặt SQLState/vendor code hữu ích ở exception bên trong.

Các thông tin nên thu thập trong log nội bộ (đã che dữ liệu nhạy cảm):

| Trường | Vì sao cần |
| --- | --- |
| Tên DB và version driver | Giải thích khác biệt phân loại giữa môi trường |
| Loại `DataAccessException` | Kết quả của strategy đang dùng |
| `SQLException` subtype | Tín hiệu Java JDBC có sẵn |
| `getSQLState()`, `getErrorCode()` | Tìm mã chuẩn/vender thực tế |
| Cause + next-exception chain | Lỗi gốc có thể bị bọc |
| Tên thao tác, request/correlation ID, transaction ID | Nối log để điều tra |
| Dấu hiệu retry/rollback và trạng thái commit | Ngăn lặp thao tác khi DB có thể đã ghi |

Ví dụ hàm tiện ích Java 17 tìm các exception JDBC sâu bên dưới (phục vụ **chẩn đoán**, không tự chọn category):

~~~java
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.Set;

public final class SqlFailureInspector {
    private SqlFailureInspector() {}

    public static void inspect(Throwable failure) {
        if (failure == null) {
            return;
        }

        Deque<Throwable> queue = new ArrayDeque<>();
        Set<Throwable> seen =
            Collections.newSetFromMap(new IdentityHashMap<>());
        queue.add(failure);

        while (!queue.isEmpty()) {
            Throwable current = queue.removeFirst();
            if (!seen.add(current)) {
                continue;
            }

            if (current instanceof SQLException sql) {
                System.out.printf(
                    "%s SQLState=%s vendorCode=%d%n",
                    sql.getClass().getSimpleName(),
                    sql.getSQLState(),
                    sql.getErrorCode()
                );
                if (sql.getNextException() != null) {
                    queue.addLast(sql.getNextException());
                }
            }

            if (current.getCause() != null) {
                queue.addLast(current.getCause());
            }
        }
    }
}
~~~

Hàm này chỉ in metadata cơ bản; không in SQL hoặc thông điệp JDBC chứa dữ liệu người dùng. Với production, dùng logger có correlation ID và kiểm soát quyền truy cập log. `IdentityHashMap` giúp tránh lặp vô hạn nếu các chuỗi cause/next bị trỏ vòng. **Không gọi `getNextException()` thay cho `getCause()`**: đó là hai quan hệ khác nhau.

Một số phiên bản Spring xử lý ngoại lệ lồng trong `BatchUpdateException` khác nhau; vì vậy với batch, kiểm tra trên đúng Spring minor version, driver và database, thay vì tuyên bố mọi nested exception đều tự động được translator duyệt hết.

## 13. Kiểm thử chiến lược và quyết định thay đổi cấu hình

Nên có **hai lớp kiểm thử**:

**Unit test cho translator (không cần database):** tạo `SQLException` với subtype, SQLState và vendor code có kiểm soát; gọi `translate(...)` và kiểm tra subtype/việc trả `null`, cause, ưu tiên custom và fallback. Demo ở mục 8 là ví dụ dễ hiểu. Nếu có custom mapping, kiểm tra cả **mã khớp và mã không khớp** để đảm bảo không vô hiệu hóa fallback.

**Integration test với DB thật:** tạo tình huống đúng ở môi trường kiểm thử có schema/driver tương thích production rồi chạy qua `JdbcTemplate`:

| Thao tác thử | Điều cần xác nhận |
| --- | --- |
| `INSERT` trùng unique/primary key | Subtype thực tế, SQLState, vendor code, ràng buộc nào bị vi phạm |
| `INSERT` vi phạm foreign key/NOT NULL | Có phân biệt được với unique conflict không? |
| SQL tham chiếu cột/bảng không tồn tại | Có được phân loại thành `BadSqlGrammarException` hay nhánh rộng hơn? |
| Deadlock hoặc serialization conflict có chủ đích | Loại exception và tình trạng transaction trước retry |
| Database/connection không thể truy cập | Resource failure và thời gian timeout |
| Batch có một phần tử lỗi | Exception ngoài, `BatchUpdateException` bên trong và mảng counts |
| Unknown vendor code/SQLState | Fallback vẫn hoạt động và không che giấu lỗi |

Với database thật, không hardcode giả định “MySQL 1062 luôn thành `DuplicateKeyException`” cho mọi phiên bản và mọi chiến lược. Test trên đúng môi trường thay vì dựa vào tên lỗi mà driver in ra.

Nếu đổi translator mặc định:
1. Ghi lại **vấn đề thực tế** (SQLState, vendor code, expected category).
2. Chỉ điều chỉnh strategy/override đúng phạm vi, có fallback.
3. Viết unit test cho mã cần override và integration test cho các lỗi lân cận.
4. Kiểm tra bean `JdbcTemplate` mà repository thực sự nhận qua DI.
5. Đo khác biệt trong transaction/retry/HTTP mapping sau nâng cấp Spring hoặc driver.

## 14. Sai lầm phổ biến

- **“Tất cả Spring 6 vẫn mặc định dùng SQLErrorCodeSQLExceptionTranslator.”** Sai: mặc định thông thường từ Spring 6.0 là subclass translator, trừ khi có cấu hình vendor đặc biệt.
- **“Mọi lỗi có SQLState 23 đều là duplicate key.”** Sai: còn foreign key, CHECK, NOT NULL...
- **“getErrorCode() có ý nghĩa toàn cục.”** Sai: đây là mã nhà cung cấp; phải biết DB và version.
- **“translate(...) luôn trả DataAccessException.”** Sai: gọi trực tiếp có thể nhận `null`; `JdbcTemplate` có fallback ngoại lệ chưa phân loại.
- **“Custom translator nên bắt tất cả để ứng dụng dễ xử lý.”** Sai: mất thông tin và khiến retry/HTTP mapping không chính xác.
- **“Đổi translator sẽ sửa deadlock hoặc unique violation.”** Sai: nó đổi phân loại, còn nguyên nhân ở dữ liệu/transaction/DB.
- **“Cứ DataAccessException là retry an toàn.”** Sai: mỗi subtype và trạng thái commit cần được đánh giá; mã nghiệp vụ phải idempotent.
- **“Có thể đọc toàn bộ SQL và tham số trực tiếp ra log.”** Nguy cơ lộ dữ liệu; log mã lỗi và context đã tối thiểu hóa.
- **“@Repository và JdbcTemplate bắt buộc có cùng cơ chế exception translation.”** Trong `JdbcTemplate`, SQLException được dịch tại điểm JDBC access. Cơ chế `@Repository` + `PersistenceExceptionTranslationPostProcessor` dùng cho các API persistence framework/DAO tương ứng, không thay việc chọn `SQLExceptionTranslator` của một `JdbcTemplate`.
- **“SQLState trong cause nào cũng được translator tự tìm ra.”** Không bảo đảm với mọi implementation/version; xác minh `BatchUpdateException` và next-exception thực tế.

## 15. Quy trình chọn strategy trong dự án

**Bước 1 — Giữ strategy mặc định nếu chưa có bằng chứng cần thay:** bắt đầu bằng `SQLExceptionSubclassTranslator` của Spring 6.x. Kiểm thử các lỗi thật và ghi nhận subtype Spring đang nhận.

**Bước 2 — Đối chiếu bằng chứng từ driver:** với lỗi bị phân loại sai, ghi `SQLException` class, `getSQLState()`, `getErrorCode()`, next exception, product name, driver version và Spring version.

**Bước 3 — Chọn mức tùy biến nhỏ nhất:** nếu SQLState đủ để phân loại, không nhất thiết bổ sung vendor code; nếu chỉ một vendor code cần chính xác, dùng `SQLErrorCodeSQLExceptionTranslator` hoặc custom override có guard; nếu toàn hệ thống dùng nhiều DB, kiểm thử từng DB.

**Bước 4 — Duy trì nguyên nhân và fallback:** custom translator chỉ match case đã kiểm chứng, trả `null` ở case khác, giữ root cause; đừng nuốt lỗi chưa biết.

**Bước 5 — Quy định chính sách nghiệp vụ riêng:** mapper từ `DataAccessException` sang conflict, retry hoặc lỗi server là trách nhiệm tầng service/API và transaction design. Xử lý duplicate key khác deadlock; retry chỉ khi idempotent và sau rollback phù hợp.

**Bước 6 — Kiểm thử lại khi nâng Spring/driver:** việc thêm nhận diện JDBC subclass hoặc điều chỉnh bảng mã có thể làm thay đổi subtype được trả ra, dù SQL trong ứng dụng không đổi.

## Tài liệu tham khảo

- [Spring Framework 6.2 — JDBC Core: SQLExceptionTranslator](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html) — chiến lược dịch lỗi, mặc định từ Spring 6.0, vendor mapping và custom fallback.
- [Spring Framework 6.2 — SQLExceptionTranslator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/support/SQLExceptionTranslator.html) — contract `translate(...)` và khả năng trả `null`.
- [Spring Framework 6.2 — JdbcAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/support/JdbcAccessor.html) — `getExceptionTranslator()`, `setExceptionTranslator(...)` và lazy init.
- [Spring Framework 6.2 — SQLErrorCodeSQLExceptionTranslator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/support/SQLErrorCodeSQLExceptionTranslator.html) — vendor codes và cách cấu hình.
- [Spring Framework 6.2 — AbstractFallbackSQLExceptionTranslator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/support/AbstractFallbackSQLExceptionTranslator.html) — custom translator và fallback.
- [Java SE 17 — SQLException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html) — SQLState, vendor code, cause và next-exception chain.
