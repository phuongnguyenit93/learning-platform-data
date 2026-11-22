# SQLState, mã lỗi nhà cung cấp và các translator tương ứng trong Spring JDBC

## 1. Vấn đề cần giải quyết

Khi cơ sở dữ liệu từ chối một câu lệnh, JDBC driver thường ném `SQLException`. Cùng một lỗi trùng khóa có thể mang **SQLState** và **vendor error code** khác nhau giữa PostgreSQL, MySQL, Oracle và SQL Server. Nếu service kiểm tra trực tiếp các số của từng vendor, logic nghiệp vụ sẽ phụ thuộc vào driver và khó bảo trì.

Spring Data Access dùng `SQLExceptionTranslator` để ánh xạ lỗi JDBC sang cây `DataAccessException` (unchecked). Các API như `JdbcTemplate` thực hiện bước dịch này khi xử lý JDBC. Service có thể phân biệt lỗi trùng khóa, lỗi ràng buộc, câu SQL sai hoặc lỗi tài nguyên mà không phải viết bảng mã cho mọi database.

~~~text
JdbcTemplate thực thi SQL
          |
          v
JDBC driver -> SQLException
               |-- getSQLState()      : "23505", "23000", "42000", ...
               |-- getErrorCode()     : 1062, 1, 2627, 0, ...
               |-- Java subclass     : SQLSyntaxErrorException, ...
               |-- cause/nextException (nếu có)
          |
          v
SQLExceptionTranslator
          |
          v
DataAccessException
    |-- DuplicateKeyException
    |-- DataIntegrityViolationException
    |-- BadSqlGrammarException
    |-- CannotAcquireLockException
    |-- ...
          |
          v
Service quyết định phản hồi, rollback hoặc retry theo nghiệp vụ
~~~

Bài này tập trung vào ba tín hiệu chẩn đoán của JDBC, các translator tương ứng, thứ tự fallback trong Spring 6.x và cách kiểm thử kết quả dịch lỗi. **Không có ánh xạ 1-1 cố định cho mọi driver**: loại Spring exception cuối cùng phụ thuộc tín hiệu driver cung cấp, translator được chọn và cấu hình.

## 2. `SQLException` cung cấp những thông tin nào?

Các API cốt lõi:

~~~java
// Mảnh minh họa; ex là SQLException do JDBC driver ném.
String state = ex.getSQLState();
int vendorCode = ex.getErrorCode();
String message = ex.getMessage();
Throwable cause = ex.getCause();
SQLException next = ex.getNextException();
~~~

- `getSQLState()`: trạng thái SQL thường gồm **5 ký tự**. Hai ký tự đầu là nhóm/class lỗi; ba ký tự sau là subclass. Có thể trả `null`.
- `getErrorCode()`: số nguyên do nhà cung cấp driver/database quy định; `0` **không đồng nghĩa thành công**.
- Java subclass của `SQLException`: từ JDBC 4, nhiều driver báo các loại cụ thể hơn, chẳng hạn `SQLSyntaxErrorException`.
- `getMessage()`: văn bản hữu ích cho con người nhưng có thể thay đổi theo phiên bản, ngôn ngữ, driver; không parse message bằng regex để làm logic chính.
- `getCause()` và `getNextException()`: có thể chứa lỗi gốc hoặc chuỗi lỗi khác, đặc biệt khi batch/driver gói exception nhiều tầng.

### SQLState: class và subclass

| SQLState/class | Ý nghĩa thường gặp | Ví dụ |
| --- | --- | --- |
| `08` | Connection exception | Lỗi kết nối DB |
| `22` | Data exception | Tràn dữ liệu/chuyển kiểu sai |
| `23` | Integrity constraint violation | UNIQUE, NOT NULL, FOREIGN KEY, CHECK |
| `28` | Invalid authorization | Không được phép truy cập |
| `40` | Transaction rollback | Serialization failure, deadlock tùy DB |
| `42` | Syntax error/access rule violation | Sai SQL, bảng/cột không tồn tại |
| `HY` | Nhóm trạng thái driver dùng rộng rãi | `HY000`: lỗi tổng quát |

Ví dụ PostgreSQL thường báo `23505` cho UNIQUE, `23503` cho FOREIGN KEY, `23502` cho NOT NULL, `40001` cho serialization failure và `40P01` cho deadlock. Những mã này là **ví dụ theo DB**, không phải lời hứa rằng mọi hệ quản trị phát cùng mã.

Chỉ nhìn hai ký tự `23` chưa đủ kết luận “trùng khóa”: cùng class còn có lỗi FK, CHECK và NOT NULL. Để đưa ra phản hồi nghiệp vụ, cần phân loại chi tiết và biết constraint nào bị vi phạm.

### Vendor error code: số của hệ quản trị

| DB/driver | Tín hiệu trùng khóa thường gặp | Ghi chú |
| --- | --- | --- |
| MySQL/MariaDB | Error code `1062`, SQLState thường `23000` | Duplicate entry |
| Oracle | Error code `1` (`ORA-00001`) | Unique constraint violated |
| SQL Server | Error code `2627` hoặc `2601` | Vi phạm primary/unique constraint hoặc unique index |
| PostgreSQL | SQLState `23505` | Nhiều trường hợp vendor code không có ý nghĩa hoặc bằng `0` |

**`getSQLState()` khác hoàn toàn `getErrorCode()`.** Không so sánh một số `23505` với `getErrorCode()` chỉ vì nó trùng với chuỗi SQLState của PostgreSQL. Hãy luôn ghi nhận cả hai trường khi chẩn đoán.

## 3. Java JDBC exception subclasses

JDBC 4 định nghĩa các subclass có nghĩa chuyên biệt:

| JDBC subclass | Gợi ý lỗi |
| --- | --- |
| `SQLSyntaxErrorException` | SQL sai cú pháp hoặc access rule |
| `SQLIntegrityConstraintViolationException` | Ràng buộc toàn vẹn |
| `SQLTransactionRollbackException` | Transaction bị rollback |
| `SQLTransientConnectionException` | Lỗi kết nối được driver phân loại transient |
| `SQLTimeoutException` | Timeout thao tác |

Tuy nhiên, không phải driver nào cũng sử dụng subtype chuyên biệt với độ chi tiết như nhau. Driver có thể dùng `SQLException` tổng quát, thêm mã SQLState hoặc mã vendor. Spring vì vậy có các translator dùng thông tin bổ sung và fallback.

Ví dụ nhận diện thuần Java:

~~~java
// Minh họa một nhánh xử lý SQLException từ JDBC thuần.
if (ex instanceof java.sql.SQLIntegrityConstraintViolationException) {
    // Có vi phạm ràng buộc; chưa chắc là duplicate key.
}
~~~

Trong code Spring thông thường, không cần tự lặp lại kiểm tra trên nếu thao tác đã đi qua `JdbcTemplate`: Spring dịch sang `DataAccessException` trước.

## 4. `DataAccessException`: kết quả dịch có ý nghĩa gì?

`org.springframework.dao.DataAccessException` là root exception unchecked của Spring cho nhiều công nghệ truy cập dữ liệu. Các subclass đáng chú ý:

| Spring exception | Phạm vi ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| `DuplicateKeyException` | Primary key/UNIQUE trùng | Có thể báo xung đột nếu phù hợp nghiệp vụ |
| `DataIntegrityViolationException` | Vi phạm ràng buộc/độ toàn vẹn dữ liệu | Kiểm tra constraint và dữ liệu |
| `BadSqlGrammarException` | SQL hoặc schema không phù hợp | Sửa query/migration |
| `CannotAcquireLockException` | Không lấy được lock/tranh chấp được nhận diện | Cân nhắc retry có điều kiện |
| `QueryTimeoutException` | Query timeout | Điều tra tải và hậu quả thực thi |
| `DataAccessResourceFailureException` | Lỗi tài nguyên/kết nối DB | Kiểm tra hạ tầng |
| `UncategorizedSQLException` | Không phân loại chính xác được | Phân tích SQLException gốc |

`DuplicateKeyException` **kế thừa** `DataIntegrityViolationException`. Khi nghiệp vụ chỉ cần biết dữ liệu vi phạm ràng buộc, bắt lớp cha thường ổn định hơn. Chỉ bắt lớp con khi cần phản hồi chuyên biệt cho trùng khóa.

Ngoại lệ Spring thường giữ `SQLException` ban đầu làm cause; bạn vẫn có thể đọc SQLState/vendor code để điều tra. Đừng biến mọi `DataIntegrityViolationException` thành thông báo “email đã tồn tại”: nó có thể là NOT NULL, FK hoặc CHECK.

## 5. Ba translator Spring JDBC và thứ tự fallback

Interface `org.springframework.jdbc.support.SQLExceptionTranslator` có phương thức:

~~~java
// Chữ ký rút gọn để minh họa API; không phải file độc lập.
DataAccessException translate(
        String task, String sql, SQLException ex);
~~~

Với một translator tùy biến, `translate` có thể trả về `null` để cho phép bước khác tiếp tục; những translator chuẩn của Spring có cơ chế fallback.

### `SQLExceptionSubclassTranslator`

- Nhìn vào **subclass JDBC 4** và một số tín hiệu đặc biệt.
- Nếu không phân loại được từ subtype, chuyển sang `SQLStateSQLExceptionTranslator`.
- **Từ Spring Framework 6.0, đây là lựa chọn mặc định thông thường** của Spring JDBC khi không có cấu hình đặc biệt cho vendor codes.

### `SQLStateSQLExceptionTranslator`

- Dùng `SQLException.getSQLState()`, nhất là **hai ký tự class** và một số mã cụ thể.
- Không cần kết nối để nhận diện database product name.
- Portable tương đối nhưng không thể phân biệt mọi lỗi vendor; thường làm **fallback** của subclass hoặc error-code translator.

### `SQLErrorCodeSQLExceptionTranslator`

- Dùng `SQLErrorCodes` chứa mapping theo database, thường dựa trên **vendor code**, chính xác hơn cho sản phẩm đã được biết.
- `SQLErrorCodesFactory` chọn mapping bằng `DatabaseMetaData.getDatabaseProductName()` khi cung cấp `DataSource`.
- Nếu có `sql-error-codes.xml` của ứng dụng tại **root classpath**, Spring JDBC có thể sử dụng strategy error-code này theo quy ước tương thích.
- Có thể bật tường minh trên `JdbcTemplate` bằng `setExceptionTranslator(...)`.
- Khi không match vendor mapping, nó fallback qua subclass rồi SQLState.

~~~text
Mặc định trong Spring 6.x:
    SQLExceptionSubclassTranslator
        |
        +-- nhận dạng JDBC subtype
        |
        +-- fallback -> SQLStateSQLExceptionTranslator
                               |
                               +-- không phân loại được -> lỗi tổng quát

Khi bật vendor mapping:
    SQLErrorCodeSQLExceptionTranslator
        |
        +-- custom translator / custom mappings (nếu có)
        +-- SQLErrorCodes của DB
        +-- fallback -> SQLExceptionSubclassTranslator
                             |
                             +-- fallback -> SQLStateSQLExceptionTranslator
~~~

**Điểm dễ nhầm:** `SQLErrorCodeSQLExceptionTranslator` không phải lúc nào cũng so `getErrorCode()`. `SQLErrorCodes` có thuộc tính `useSqlStateForTranslation`. Ví dụ mapping PostgreSQL trong Spring bật nó để so **SQLState** thay vì số vendor.

Với vendor strategy, các bước ưu tiên thường là custom translator/mapping nếu được cấu hình, mapping nhóm error code và fallback. Các cấu hình tùy biến như `customSqlExceptionTranslator` thuộc `SQLErrorCodes` có thể ảnh hưởng thứ tự giải quyết. Hãy kiểm chứng thứ tự trên version Spring đang dùng thay vì giả định mọi Spring release giống nhau.

## 6. Chương trình Java 17 chạy được: chứng minh ba chiến lược

Ví dụ sau chủ động tạo `SQLException` **giả lập** với SQLState, JDBC subclass và vendor code để minh họa translator. Nó **không kết nối DB**, vì vậy stdout không phụ thuộc driver bên ngoài.

Cấu trúc project:

~~~text
translator-demo/
├── pom.xml
└── src/main/java/demo/TranslatorDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>translator-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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
                    <mainClass>demo.TranslatorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/TranslatorDemo.java**

~~~java
package demo;

import java.sql.SQLException;
import java.sql.SQLSyntaxErrorException;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.support.SQLErrorCodeSQLExceptionTranslator;
import org.springframework.jdbc.support.SQLErrorCodes;
import org.springframework.jdbc.support.SQLExceptionSubclassTranslator;
import org.springframework.jdbc.support.SQLExceptionTranslator;
import org.springframework.jdbc.support.SQLStateSQLExceptionTranslator;

public final class TranslatorDemo {
    public static void main(String[] args) {
        SQLException stateError =
                new SQLException("unique violation", "23505", 0);

        SQLException subclassError =
                new SQLSyntaxErrorException("bad SQL", "42000", 0);

        SQLException vendorError =
                new SQLException("duplicate entry", "HY000", 1062);

        SQLErrorCodes vendorCodes = new SQLErrorCodes();
        vendorCodes.setDuplicateKeyCodes("1062");

        SQLExceptionTranslator stateTranslator =
                new SQLStateSQLExceptionTranslator();
        SQLExceptionTranslator subclassTranslator =
                new SQLExceptionSubclassTranslator();
        SQLExceptionTranslator vendorTranslator =
                new SQLErrorCodeSQLExceptionTranslator(vendorCodes);

        print("SQLState 23505", stateTranslator, stateError);
        print("JDBC subclass", subclassTranslator, subclassError);
        print("Vendor 1062", vendorTranslator, vendorError);
    }

    private static void print(
            String label,
            SQLExceptionTranslator translator,
            SQLException original) {
        DataAccessException mapped = translator.translate(
                "demo", "INSERT INTO sample (id) VALUES (?)", original);

        if (mapped == null) {
            throw new IllegalStateException(
                    "Could not translate: " + label);
        }

        System.out.println(
                label + ": " + mapped.getClass().getSimpleName());
    }
}
~~~

Tại thư mục `translator-demo/`, cần JDK 17+ và Maven 3.9+, chạy:

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến từ chương trình** (không kể log riêng của Maven):

~~~text
SQLState 23505: DuplicateKeyException
JDBC subclass: BadSqlGrammarException
Vendor 1062: DuplicateKeyException
~~~

Giải thích:

1. SQLState translator dùng trạng thái `23505` để phân loại duplicate key.
2. JDBC subclass translator nhận `SQLSyntaxErrorException` và phân loại `BadSqlGrammarException`.
3. Vendor translator được cấp `SQLErrorCodes` có `duplicateKeyCodes=1062`, nên ánh xạ số vendor `1062` thành `DuplicateKeyException` dù SQLState mô phỏng là `HY000`.

**Đây là test dịch exception, không phải integration test database.** Với DB thật, hãy lấy SQLState/errorCode thực tế từ driver, rồi kiểm tra loại `DataAccessException` mà cấu hình `JdbcTemplate` đang tạo.

## 7. Lỗi thật qua `JdbcTemplate`

Tầng DAO dùng `JdbcTemplate` không cần bắt checked `SQLException` cho mỗi query:

~~~java
// Mảnh mã đặt trong DAO có JdbcTemplate jdbcTemplate.
jdbcTemplate.update(
        "INSERT INTO account (id, email) VALUES (?, ?)",
        id, email);
~~~

Khi database từ chối câu lệnh, `JdbcTemplate` gọi translator của nó và ném `DataAccessException`. Code service có thể bắt loại phù hợp:

~~~java
// Mảnh mã nghiệp vụ, chưa phải một class Java độc lập.
try {
    accountDao.create(id, email);
} catch (org.springframework.dao.DuplicateKeyException ex) {
    throw new AccountAlreadyExistsException(email, ex);
}
~~~

`AccountAlreadyExistsException` là **exception ứng dụng tự định nghĩa** trong ví dụ này. Chỉ dùng phản hồi “account đã tồn tại” khi đã xác minh ràng buộc trùng khóa đúng với nghiệp vụ; không suy diễn từ bất kỳ lỗi integrity nào.

Chỉ bắt `DataAccessException` tại tầng có khả năng quyết định cách xử lý. Đừng bắt tất cả rồi trả cùng một mã HTTP. Lỗi kết nối, SQL sai và dữ liệu trùng có tính chất khác nhau.

## 8. Khi nào bật vendor-code translator?

Trong một ứng dụng dùng Spring 6.x, subclass + SQLState fallback thường đủ cho những lỗi phổ biến. Bật `SQLErrorCodeSQLExceptionTranslator` khi có lỗi driver cụ thể cần phân loại chính xác bằng vendor code hoặc mapping chưa đáp ứng yêu cầu.

Có thể cấu hình tường minh:

~~~java
// Mảnh mã @Bean tích hợp Spring; cần import DataSource,
// JdbcTemplate, SQLErrorCodeSQLExceptionTranslator và @Bean.
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    JdbcTemplate template = new JdbcTemplate(dataSource);
    template.setExceptionTranslator(
            new SQLErrorCodeSQLExceptionTranslator(dataSource));
    return template;
}
~~~

Khi tạo từ `DataSource`, translator có thể truy cập `DatabaseMetaData` để biết database product name. Cần đảm bảo khả năng kết nối và vòng đời khởi tạo. Nếu chưa cần mapping vendor cụ thể, để mặc định thường đơn giản hơn.

Spring mang theo cấu hình `org/springframework/jdbc/support/sql-error-codes.xml` cho các database quen thuộc. Các nhóm mã có thể gồm `duplicateKeyCodes`, `badSqlGrammarCodes`, `dataIntegrityViolationCodes`, `cannotAcquireLockCodes`, `deadlockLoserCodes`, `dataAccessResourceFailureCodes` và những nhóm khác.

### `sql-error-codes.xml` tùy chỉnh ở root classpath

Ứng dụng có thể đặt `sql-error-codes.xml` ở root classpath (chẳng hạn `src/main/resources/sql-error-codes.xml` của một ứng dụng Maven/Gradle) để khai báo mapping riêng. Việc xuất hiện file này cũng là tín hiệu khiến Spring JDBC chọn error-code strategy theo quy ước.

Ví dụ cấu trúc tối giản cho MySQL:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
                           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="MySQL"
          class="org.springframework.jdbc.support.SQLErrorCodes">
        <property name="duplicateKeyCodes" value="1062"/>
    </bean>
</beans>
~~~

Đây là ví dụ học cú pháp; **không nên dùng thay nguyên bộ mapping production** chỉ để nhận diện `1062`, vì file custom có thể ảnh hưởng các nhóm lỗi khác. Hãy dùng mapping tích hợp sẵn trước, rồi chỉ tùy biến khi có chứng cứ từ driver/database thực.

Ngoài cách khai báo XML, `SQLErrorCodes` có thể được tạo trực tiếp, như chương trình runnable ở phần 6. Cách đó phù hợp với unit test hoặc mapping cần kiểm soát đặc biệt.

## 9. Custom translator và fallback

Khi cần quy tắc đặc thù, Spring 6.1+ hỗ trợ `setCustomTranslator(...)` trên các translator kế thừa `AbstractFallbackSQLExceptionTranslator`. Cách này được ưu tiên hơn việc override `customTranslate(...)` đã deprecated từ Spring 6.1.

Ví dụ khi ứng dụng chỉ dùng PostgreSQL và đã xác minh `40P01` tương ứng deadlock:

~~~java
// Mảnh mã cấu hình, dataSource và jdbcTemplate đã được tạo.
SQLErrorCodeSQLExceptionTranslator translator =
        new SQLErrorCodeSQLExceptionTranslator(dataSource);

translator.setCustomTranslator((task, sql, exception) -> {
    if ("40P01".equals(exception.getSQLState())) {
        return new org.springframework.dao.CannotAcquireLockException(
                "Deadlock while " + task, exception);
    }
    return null; // Các lỗi khác tiếp tục qua mapping và fallback.
});

jdbcTemplate.setExceptionTranslator(translator);
~~~

Lưu ý không tự map mọi loại transaction failure vào `CannotAcquireLockException`: chọn mapping theo đúng semantics driver và phiên bản Spring. Mapping trên có mục đích minh họa cơ chế custom; Spring đã có các mapping PostgreSQL cho deadlock và có thể dùng loại exception tương ứng.

Ngoài custom translator được gắn trực tiếp, `SQLErrorCodes` còn hỗ trợ **`customSqlExceptionTranslator` và custom translations**. Tùy phiên bản/cấu hình, các bước custom được thử trước bảng mã lỗi chung, sau đó mới đến fallback. Trả `null` từ custom translator nghĩa là nó chưa xử lý trường hợp này; đừng trả về một exception chung cho mọi input nếu không muốn xóa phân loại sẵn có.

Luôn kiểm thử cả mã **trúng custom rule** lẫn mã **không trúng** để bảo đảm fallback vẫn hoạt động. Nếu không có nhu cầu thực tế, giữ translator mặc định giúp hệ thống ít cấu hình hơn.

## 10. Log và chẩn đoán lỗi đúng cách

Một `DataAccessException` thường giữ `SQLException` ở cây cause. Có thể lần theo để lấy mã gốc:

~~~java
// Mảnh mã khi đang xử lý DataAccessException ex;
// log là logger của ứng dụng, không phải biến được định nghĩa ở đây.
Throwable cursor = ex;
while (cursor != null) {
    if (cursor instanceof java.sql.SQLException sqlEx) {
        log.warn("dbFailure state={} code={}",
                sqlEx.getSQLState(),
                sqlEx.getErrorCode());
        break;
    }
    cursor = cursor.getCause();
}
~~~

Đoạn trên dừng ở `SQLException` đầu tiên trong cause chain. Với `BatchUpdateException`, cần kiểm tra thêm `getNextException()`, `getUpdateCounts()` hoặc `getLargeUpdateCounts()`; một driver có thể gói lỗi chi tiết ở những nơi này. Kết quả count cũng phụ thuộc driver, không luôn nói được chính xác mục nào thất bại.

Thực hành tốt khi quan sát production:

- Ghi **loại Spring exception, SQLState đầy đủ, vendor code, tên thao tác, database product/driver version và trace ID**; không chỉ dựa vào message.
- Không log password, token, dữ liệu cá nhân hay SQL chứa literal nhạy cảm; chỉ giữ thông tin cần thiết và tuân thủ quy tắc bảo mật ứng dụng.
- Nếu cần lấy class từ SQLState, kiểm tra khác `null` và độ dài ít nhất 2 trước `substring(0, 2)`.
- Không parse `SQLException.getMessage()` làm hợp đồng ổn định: thông điệp có thể thay đổi theo phiên bản hoặc locale.
- Nếu dịch lỗi chưa đúng, so sánh mã thật trên **DB triển khai**, không chỉ H2/in-memory test.
- Giữ cause khi bọc thêm exception; đừng tạo một `RuntimeException("DB error")` bỏ hết ngữ cảnh.

## 11. Phản hồi nghiệp vụ, rollback và retry

**Translator chỉ phân loại lỗi.** Nó không tự quyết định retry hay transaction boundary.

- `DuplicateKeyException`, nhiều `DataIntegrityViolationException` và `BadSqlGrammarException`: thường cần sửa dữ liệu/query hoặc thông báo xung đột; retry nguyên xi ít có ích.
- Lỗi lock, serialization failure hoặc resource tạm thời: có thể retry sau khi biết transaction đã rollback đúng, thao tác an toàn khi chạy lại, có backoff và giới hạn số lần thử.
- Timeout: không tự kết luận DB chưa commit. Phải xem transaction outcome, khả năng idempotent và hậu quả của side effect trước khi retry.

Khi `@Transactional` đang áp dụng đúng qua Spring proxy, `DataAccessException` là runtime exception, nên nếu nó thoát khỏi method thì thường kích hoạt rollback theo quy tắc mặc định. Nếu service bắt exception và không ném lại, transaction **có thể** vẫn commit những thay đổi khác tùy trạng thái rollback-only. Điều đó độc lập với translator được dùng.

Không tự động đổi mọi `DataAccessException` thành HTTP 409. UNIQUE trùng có thể mang nghĩa xung đột, nhưng connection failure hoặc SQL grammar sai thường là lỗi hệ thống; quyết định cuối cùng phụ thuộc bối cảnh dịch vụ.

## 12. Tình huống trước – sau

### A. Di chuyển MySQL sang PostgreSQL

**Trước:** service đọc `getErrorCode() == 1062` để báo duplicate key. Sau migration, PostgreSQL thường báo `23505` ở SQLState nên logic bỏ sót.

**Sau:** dùng Spring `DuplicateKeyException`/`DataIntegrityViolationException`, giữ SQLState/vendor code cho log, và test integration với PostgreSQL thật. Service không cần một bảng switch theo vendor.

### B. Nhận SQLState `23000`

**Sai:** `23000` nghĩa là “email trùng”.

**Đúng:** `23` là class integrity; `23000` còn quá tổng quát. Cần vendor code, mapping, tên constraint hay dữ liệu nghiệp vụ để phân biệt UNIQUE và FK/NOT NULL.

### C. Thêm file `sql-error-codes.xml`

**Trước:** default Spring 6.x dùng subclass + SQLState fallback.

**Sau:** nếu có file custom root classpath, strategy mặc định có thể chuyển sang vendor codes. Cần test mapping quan trọng và fallback, không sao chép một XML tối giản rồi vô tình mất các nhóm mã khác.

### D. Batch thất bại

**Sai:** chỉ đọc wrapper message rồi tự động retry toàn batch.

**Đúng:** phân tích `BatchUpdateException`, update counts và next exception, bảo đảm transaction/rollback và idempotency trước khi retry.

## 13. Lỗi phổ biến và bài tập

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nhầm SQLState và vendor code | Match sai trên DB khác | Đọc hai API riêng |
| Dựa vào class `23` để kết luận duplicate | Bỏ qua FK/NOT NULL/CHECK | Phân loại kỹ constraint |
| Nghĩ Spring 6.x luôn ưu tiên vendor-code translator | Hiểu sai behavior mặc định | Kiểm tra subclass/SQLState fallback và cấu hình |
| Nghĩ `SQLErrorCodeSQLExceptionTranslator` luôn dùng số vendor | Không hiểu PostgreSQL mapping | Kiểm tra `useSqlStateForTranslation` |
| Bắt mọi integrity error và trả một thông điệp | Báo lỗi nghiệp vụ sai | Xác minh loại constraint |
| Nuốt `DataAccessException` trong transaction | Có thể commit phần việc còn lại | Để exception lan ra hoặc xử lý rollback chủ động |
| Retry timeout/lock vô hạn | Tạo tải, tác động lặp | Giới hạn retry, backoff, idempotency |
| Mất cause khi bọc exception | Không chẩn đoán được | Giữ original exception làm cause |

Tự kiểm tra:

1. `SQLState=23505`, `errorCode=0`: tín hiệu chính cho duplicate là **SQLState**, không phải số `0`.
2. `SQLState=HY000`, `errorCode=1062` từ MySQL: **vendor-code translator có mapping 1062** có lợi thế.
3. `SQLSyntaxErrorException` trong Spring 6.x mặc định: **`SQLExceptionSubclassTranslator`** có thể dịch sang `BadSqlGrammarException`.
4. `SQLState=23503` từ PostgreSQL: thường là **foreign-key violation**, không phải “email trùng”.
5. Lỗi lock muốn retry: kiểm tra **transaction outcome, idempotency, retry budget** trước.
6. Mã lỗi vendor mới không được nhận diện: kiểm tra subclass/SQLState/cause rồi chỉ thêm **mapping có kiểm chứng**, giữ fallback.

## 14. Ghi nhớ

- **SQLState**: chuỗi trạng thái thường 5 ký tự; hai ký tự đầu là class.
- **Vendor error code**: số của database/driver; có thể `0` ngay cả khi có lỗi.
- **JDBC subclass**: tín hiệu loại lỗi trong `SQLException` khi driver triển khai phù hợp.
- **Spring 6.x mặc định**: `SQLExceptionSubclassTranslator` và `SQLStateSQLExceptionTranslator` fallback.
- **Vendor strategy**: `SQLErrorCodeSQLExceptionTranslator` dùng `SQLErrorCodes` theo database, custom mapping và fallback. Một số DB có thể match bằng SQLState thay số vendor.
- **`DataAccessException`** giúp service ít phụ thuộc driver hơn; vẫn phải dựa trên nghiệp vụ để quyết định phản hồi, rollback và retry.

**Tài liệu tham khảo:**

- [Spring Framework — JDBC Core, Using SQLExceptionTranslator](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html)
- [Spring Framework — DAO Support and Exception Hierarchy](https://docs.spring.io/spring-framework/reference/6.2/data-access/dao.html)
- [Spring Framework — SQLStateSQLExceptionTranslator API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/support/SQLStateSQLExceptionTranslator.html)
- [Spring Framework — SQLExceptionSubclassTranslator API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/support/SQLExceptionSubclassTranslator.html)
- [Spring Framework — SQLErrorCodeSQLExceptionTranslator API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/support/SQLErrorCodeSQLExceptionTranslator.html)
- [Spring Framework — Vendor code mappings](https://github.com/spring-projects/spring-framework/blob/6.2.x/spring-jdbc/src/main/resources/org/springframework/jdbc/support/sql-error-codes.xml)
