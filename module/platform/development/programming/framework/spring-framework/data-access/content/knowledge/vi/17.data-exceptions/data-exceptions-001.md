# DataAccessException: gốc của hệ ngoại lệ truy cập dữ liệu trong Spring

`DataAccessException` là **lớp gốc (root exception)** của hệ ngoại lệ truy cập dữ liệu do Spring Framework cung cấp. Khi dùng Spring JDBC, JPA/Hibernate tích hợp Spring hoặc các thành phần hỗ trợ truy cập dữ liệu khác, nhiều lỗi đặc thù của driver và công nghệ lưu trữ được chuyển thành những **subclass của `org.springframework.dao.DataAccessException`**. Nhờ vậy, tầng service có thể phản ứng theo *ý nghĩa của lỗi* — vi phạm ràng buộc, sai câu truy vấn, lỗi khóa đồng thời, mất kết nối — thay vì phụ thuộc vào mã lỗi của một nhà cung cấp database cụ thể.

Điểm cốt lõi: `DataAccessException` là **abstract class**, kế thừa `org.springframework.core.NestedRuntimeException` và gián tiếp kế thừa `RuntimeException`. Nó là gốc của **hệ ngoại lệ dữ liệu Spring**, **không phải** gốc của mọi exception Java hay mọi lỗi có thể phát sinh trong database. Ứng dụng không cần khai báo `throws DataAccessException` ở mỗi phương thức vì đây là *unchecked exception*.

## 1. Vấn đề mà DataAccessException giải quyết

Nếu làm việc trực tiếp với JDBC, nhiều thao tác ném `java.sql.SQLException` (checked exception). Chương trình thường phải xét SQLState, vendor error code hoặc lớp exception riêng của driver để biết nguyên nhân:

```java
try {
    // connection.prepareStatement(...), executeUpdate(), ...
} catch (java.sql.SQLException ex) {
    String sqlState = ex.getSQLState();
    int vendorCode = ex.getErrorCode();
    // Cách diễn giải hai giá trị này còn tùy database và driver.
}
```

Đây là **đoạn minh họa** của JDBC thuần, không phải chương trình Java độc lập. Chỉ nhìn `SQLException` chung chưa cho biết chắc lỗi là trùng khóa, timeout hay cú pháp SQL. Nếu code ở service phụ thuộc trực tiếp SQLState của một DB, việc thay công nghệ hoặc driver sẽ khó khăn hơn.

Spring cung cấp **exception translation** (chuyển đổi ngoại lệ): lớp truy cập dữ liệu nhận lỗi của công nghệ bên dưới, phân loại và tạo một exception có ý nghĩa theo hệ của Spring, thường vẫn giữ nguyên nguyên nhân gốc.

```text
JDBC / JPA / Hibernate / driver
       |
       | SQLException hoặc persistence exception
       v
Spring JDBC template / ORM exception translator
       |
       v
org.springframework.dao.DataAccessException
       |
       +-- DataIntegrityViolationException
       +-- BadSqlGrammarException
       +-- EmptyResultDataAccessException
       +-- QueryTimeoutException
       +-- OptimisticLockingFailureException
       +-- ...
       |
       v
Service xử lý theo chính sách nghiệp vụ
```

**Lợi ích thực tế:**

1. **Một hợp đồng exception chung**: service có thể bắt `DataIntegrityViolationException` dù DAO được triển khai bằng JDBC hoặc ORM, miễn đường truy cập đó đã áp dụng exception translation phù hợp.
2. **Phân loại có ý nghĩa**: có thể phân biệt lỗi cần sửa dữ liệu, lỗi cần sửa SQL, lỗi cạnh tranh hay lỗi hạ tầng.
3. **Giảm boilerplate**: không phải bắt và chuyển `SQLException` ở mỗi phương thức dùng `JdbcTemplate`.
4. **Giữ thông tin gốc**: thường tra được exception bên dưới qua `getCause()`/`getMostSpecificCause()` để chẩn đoán.
5. **Phù hợp transaction**: mặc định lỗi unchecked ném ra khỏi một phương thức `@Transactional` được Spring quản lý sẽ khiến giao dịch rollback.

Đừng hiểu “không phụ thuộc database” là Spring luôn dịch cùng một lỗi thành chính xác một subclass trên mọi driver. Phân loại phụ thuộc loại exception gốc, SQLState/vendor code, cấu hình translator và API truy cập; test với stack thực tế vẫn quan trọng.

## 2. Vị trí của DataAccessException trong hệ phân cấp Java

```text
java.lang.Throwable
  └── java.lang.Exception
      └── java.lang.RuntimeException
          └── org.springframework.core.NestedRuntimeException
              └── org.springframework.dao.DataAccessException (abstract)
                  ├── NonTransientDataAccessException (abstract)
                  ├── TransientDataAccessException (abstract)
                  ├── RecoverableDataAccessException
                  └── một số nhánh chuyên biệt khác, ví dụ ScriptException
```

Nhánh chính có ý nghĩa xử lý như sau:

| Nhánh | Ý nghĩa | Có nên tự động retry? |
| --- | --- | --- |
| `NonTransientDataAccessException` | Thao tác tương tự thường sẽ thất bại nếu không sửa nguyên nhân: SQL sai, vi phạm ràng buộc, dữ liệu trả về không đúng kỳ vọng... | **Không** retry mù quáng |
| `TransientDataAccessException` | Lỗi được xem là có thể biến mất, chẳng hạn một số timeout hoặc xung đột cạnh tranh | **Có thể cân nhắc** retry có giới hạn, sau khi xác nhận an toàn/idempotent |
| `RecoverableDataAccessException` | Có thể phục hồi sau **hành động khôi phục** của ứng dụng; ít nhất có thể phải đóng kết nối cũ và lấy kết nối mới | Không retry nguyên trạng trên tài nguyên lỗi; cần quy trình recovery |
| `DataAccessException` (gốc) | Kiểu chung để bắt hoặc khai báo lỗi dữ liệu xuyên tầng | Chưa đủ thông tin để quyết định chính sách |

`DataAccessException` thuộc namespace `org.springframework.dao`. Dù tên gói là `dao`, nó không chỉ phục vụ DAO theo mẫu cũ; các template JDBC và cơ chế tích hợp ORM của Spring cũng sử dụng hệ này.

### Cây subclass tiêu biểu (rút gọn, không liệt kê toàn bộ API)

```text
DataAccessException
├── NonTransientDataAccessException
│   ├── DataIntegrityViolationException
│   │   └── DuplicateKeyException
│   ├── InvalidDataAccessResourceUsageException
│   │   └── BadSqlGrammarException
│   ├── DataRetrievalFailureException
│   │   └── IncorrectResultSizeDataAccessException
│   │       └── EmptyResultDataAccessException
│   ├── InvalidDataAccessApiUsageException
│   ├── NonTransientDataAccessResourceException
│   │   └── DataAccessResourceFailureException
│   └── UncategorizedDataAccessException
├── TransientDataAccessException
│   ├── ConcurrencyFailureException
│   │   ├── OptimisticLockingFailureException
│   │   └── PessimisticLockingFailureException
│   │       └── CannotAcquireLockException
│   ├── QueryTimeoutException
│   └── TransientDataAccessResourceException
└── RecoverableDataAccessException
```

Các cạnh trong sơ đồ là quan hệ kế thừa tiêu biểu của Spring Framework; còn một số subclass ít gặp khác không được vẽ. Một ví dụ quan trọng:

```java
try {
    // Gọi DAO / JdbcTemplate ...
} catch (org.springframework.dao.DuplicateKeyException ex) {
    // DuplicateKeyException là subclass của DataIntegrityViolationException,
    // NonTransientDataAccessException và DataAccessException.
}
```

Đoạn trên là **minh họa catch**, không có chương trình khởi chạy độc lập. Nếu cần bắt lỗi trùng/vi phạm ràng buộc một cách tổng quát hơn, cân nhắc bắt `DataIntegrityViolationException` thay vì chỉ một subclass, vì độ chi tiết của exception được dịch có thể khác nhau.

## 3. Những subclass cần nhận diện trong ứng dụng Spring

| Exception cụ thể | Tình huống phổ biến | Phản ứng phù hợp |
| --- | --- | --- |
| `DuplicateKeyException` | INSERT/UPDATE vi phạm PRIMARY KEY hoặc UNIQUE | Phản hồi trùng dữ liệu, tránh retry nguyên yêu cầu |
| `DataIntegrityViolationException` | Vi phạm UNIQUE, FOREIGN KEY, NOT NULL hoặc ràng buộc khác | Kiểm tra quy tắc nghiệp vụ và dữ liệu đầu vào |
| `BadSqlGrammarException` | SQL không hợp lệ, tên bảng/cột không tồn tại, cú pháp sai | Sửa mã/migration/schema, không retry y nguyên |
| `EmptyResultDataAccessException` | API kỳ vọng một bản ghi nhưng truy vấn trả 0 | Xử lý “không tìm thấy” theo hợp đồng hàm/API |
| `IncorrectResultSizeDataAccessException` | API yêu cầu số dòng nhất định nhưng có số khác | Kiểm tra query và giả định cardinality |
| `OptimisticLockingFailureException` | Version của entity không còn khớp, phát hiện concurrent update | Cho client tải lại dữ liệu/giải quyết xung đột |
| `CannotAcquireLockException` | Database không cấp được lock theo điều kiện và thời hạn đang áp dụng | Chẩn đoán contention; retry có giới hạn nếu an toàn |
| `QueryTimeoutException` | Truy vấn vượt timeout hoặc bị dừng do timeout | Kiểm tra SQL, tải, timeout và khả năng retry |
| `DataAccessResourceFailureException` | Không thể truy cập tài nguyên dữ liệu, ví dụ lỗi kết nối | Kiểm tra DB, pool, mạng, credentials, trạng thái dịch vụ |
| `InvalidDataAccessApiUsageException` | Gọi sai API/framework contract, thiếu tham số hoặc thao tác không hợp lệ | Sửa code gọi API |
| `UncategorizedDataAccessException` | Spring không phân loại chi tiết hơn được | Xem nguyên nhân, SQLState/vendor code và logging |

**Không phải mọi tình huống “không có dữ liệu” đều là exception.** Ví dụ `JdbcTemplate.query(...)` có thể trả danh sách rỗng bình thường. `queryForObject(...)` yêu cầu đúng một hàng nên có thể ném `EmptyResultDataAccessException`. Tương tự `JdbcTemplate.update(...)` thường trả số hàng bị ảnh hưởng bằng `0` mà không tự ném exception nếu SQL chạy hợp lệ.

Một subclass không nhất thiết chỉ phát sinh bởi một DB engine. Cùng `DataIntegrityViolationException` có thể do nhiều ràng buộc khác nhau; không tự kết luận luôn là UNIQUE/HTTP 409 chỉ từ superclass đó. Cũng không nên suy ra một sự cố database chắc chắn chỉ từ tên exception: có thể là câu lệnh không hợp lệ do code.

## 4. Cơ chế dịch SQLException trong Spring JDBC

`JdbcTemplate` đóng gói các phần việc lặp lại: lấy kết nối qua `DataSource`, chuẩn bị và thực thi SQL, giải phóng tài nguyên phù hợp transaction, sau đó chuyển `SQLException` sang `DataAccessException`. Giao diện dịch lỗi là `org.springframework.jdbc.support.SQLExceptionTranslator`:

```java
public interface SQLExceptionTranslator {
    // Chữ ký thực tế có annotation nullable theo phiên bản Spring.
    DataAccessException translate(String task, String sql, SQLException ex);
}
```

Đây là cách diễn giải chữ ký API để học, không phải file cần tự khai báo trong dự án (Spring đã cung cấp interface). Bộ dịch dùng thông tin từ exception gốc, như:

- Lớp con của `SQLException` (JDBC 4: ví dụ `SQLSyntaxErrorException`, `SQLIntegrityConstraintViolationException`, `SQLTransientException`);
- `SQLState` theo tiêu chuẩn và cách triển khai của database;
- Vendor-specific error code, nếu bộ dịch được cấu hình dùng mã lỗi nhà cung cấp;
- SQL statement và thao tác đang thực hiện, dùng làm thông tin chẩn đoán.

Từ Spring Framework **6.0**, translator mặc định của phần lớn đường JDBC là `SQLExceptionSubclassTranslator`, có fallback sang `SQLStateSQLExceptionTranslator`. `SQLErrorCodeSQLExceptionTranslator` vẫn có thể được dùng khi cấu hình trực tiếp hoặc có file `sql-error-codes.xml` được Spring nhận diện trên classpath; nó dựa trên mã lỗi database. Đừng mặc định mọi ứng dụng đang dùng translator dựa trên vendor code.

Luồng ví dụ:

```text
H2: SQLException về UNIQUE constraint
      |
      v
JdbcTemplate -> SQLExceptionTranslator
      |
      v
DataIntegrityViolationException / DuplicateKeyException
      |
      v
DAO/Service xử lý theo quy tắc không cho email trùng
```

Đường ORM không đi qua `SQLExceptionTranslator` trong mọi trường hợp: JPA/Hibernate có exception riêng, được các thành phần hỗ trợ ORM của Spring hoặc cơ chế `@Repository` translation xử lý khi đã cấu hình đúng.

## 5. Ví dụ Java 17+ chạy được: quan sát DataAccessException với Spring JDBC và H2

Ví dụ này không cần Spring Boot hay server DB riêng. Nó dùng **Spring Framework 6.2.19 + H2 2.3.232** để tạo một database trong bộ nhớ, lần lượt phát sinh lỗi ràng buộc, kết quả rỗng, quá nhiều dòng và lỗi SQL. Cấu trúc file:

```text
dataaccess-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── DataAccessExceptionDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>dataaccess-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
            <version>2.3.232</version>
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
                    <mainClass>demo.DataAccessExceptionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/DataAccessExceptionDemo.java`:

```java
package demo;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;

public final class DataAccessExceptionDemo {
    private DataAccessExceptionDemo() {
    }

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:dao_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE accounts (
                    id BIGINT PRIMARY KEY,
                    email VARCHAR(128) NOT NULL UNIQUE
                )
                """);
        jdbc.update("INSERT INTO accounts (id, email) VALUES (?, ?)",
                1L, "a@example.test");
        jdbc.update("INSERT INTO accounts (id, email) VALUES (?, ?)",
                2L, "b@example.test");

        try {
            jdbc.update("INSERT INTO accounts (id, email) VALUES (?, ?)",
                    3L, "a@example.test");
        } catch (DataIntegrityViolationException ex) {
            System.out.println("constraint=" + (ex instanceof DataAccessException));
        }

        try {
            jdbc.queryForObject(
                    "SELECT email FROM accounts WHERE id = ?",
                    String.class, 999L);
        } catch (EmptyResultDataAccessException ex) {
            System.out.println("empty=" +
                    (ex instanceof IncorrectResultSizeDataAccessException));
        }

        try {
            jdbc.queryForObject("SELECT email FROM accounts", String.class);
        } catch (IncorrectResultSizeDataAccessException ex) {
            System.out.println("too-many=" + ex.getActualSize());
        }

        try {
            jdbc.queryForObject(
                    "SELECT unknown_column FROM accounts",
                    String.class);
        } catch (BadSqlGrammarException ex) {
            System.out.println("bad-sql=" + (ex instanceof DataAccessException));
        }
    }
}
```

Trong terminal tại thư mục `dataaccess-demo`, dùng Java 17+ và Maven:

```bash
java -version
mvn -q compile exec:java
```

Stdout từ **chương trình** khi chạy với các phiên bản dependency và H2 như trên:

```text
constraint=true
empty=true
too-many=2
bad-sql=true
```

Giải thích bốn ca:

1. **Vi phạm UNIQUE**: bảng chỉ cho một email xuất hiện một lần. `JdbcTemplate.update` chuyển lỗi của H2 thành một subclass của `DataIntegrityViolationException`; handler bắt nhóm phù hợp. Biểu thức `instanceof DataAccessException` là `true` vì quan hệ kế thừa.
2. **Không tìm thấy theo `queryForObject`**: truy vấn ID 999 không trả dòng nào, vì vậy ném `EmptyResultDataAccessException`. Đây cũng là subclass của `IncorrectResultSizeDataAccessException`.
3. **Có hai dòng khi chỉ yêu cầu một**: `queryForObject` trên cả bảng ném `IncorrectResultSizeDataAccessException`; `getActualSize()` cho biết `2`.
4. **Tên cột sai**: H2 báo SQL error; bộ dịch JDBC chuyển thành `BadSqlGrammarException`. Đây cũng là `DataAccessException`.

**Lưu ý kiểm thử:** tên subclass chính xác cho một vendor SQL exception có thể phụ thuộc translator/driver, nên ví dụ bắt `DataIntegrityViolationException` thay vì dựa vào việc mọi hệ quản trị luôn phát sinh `DuplicateKeyException`. Các exception về result size do hợp đồng `queryForObject` của Spring xác định, không nhất thiết do database từ chối câu SELECT.

### Đối chiếu với JDBC thuần

Trong JDBC thuần, lệnh INSERT trùng UNIQUE thường làm phương thức `executeUpdate()` ném `SQLException` (checked). Khi dùng `JdbcTemplate`, lỗi được đóng gói và phân loại. **SQL vẫn thất bại như nhau**; Spring chỉ cung cấp kiểu exception thống nhất và hỗ trợ quản lý tài nguyên.

`JdbcTemplate` không tự biến tất cả điều kiện nghiệp vụ sai thành exception. Ví dụ:

```java
int affected = jdbc.update(
        "UPDATE accounts SET email = ? WHERE id = ?",
        "new@example.test", 123456L);
System.out.println(affected); // 0: SQL hợp lệ nhưng không có hàng phù hợp.
```

Đây là **đoạn trích trong phương thức đã có `JdbcTemplate jdbc`**, không chạy độc lập. Nếu nghiệp vụ yêu cầu phải có đúng một hàng được cập nhật, service cần kiểm tra `affected != 1` và quyết định phát sinh domain exception thích hợp. Không thể mặc định rằng mọi trường hợp dữ liệu không tồn tại sẽ tạo `EmptyResultDataAccessException`.

## 6. Xử lý exception theo mức độ cụ thể

Nên xử lý ở **tầng có đủ thông tin để đưa ra quyết định**. DAO chủ yếu báo lỗi dữ liệu; service xác định quy tắc nghiệp vụ; controller/API ánh xạ sang giao thức bên ngoài. Không có quy tắc rằng mọi `DataAccessException` phải được bắt ở DAO.

Ví dụ đoạn code ở service (giả định đã inject `JdbcTemplate jdbc` và có model `Account`):

```java
public void createAccount(long id, String email) {
    try {
        jdbc.update(
                "INSERT INTO accounts (id, email) VALUES (?, ?)",
                id, email);
    } catch (org.springframework.dao.DuplicateKeyException ex) {
        throw new IllegalStateException("Account ID or email already exists", ex);
    }
}
```

Đây là **đoạn thành phần**, không có cấu hình Spring hoàn chỉnh. `IllegalStateException` chỉ minh họa việc chuyển thành thông báo/domain error có cause; ứng dụng thực tế nên định nghĩa domain exception nhất quán. **Đừng luôn cho rằng DuplicateKeyException xảy ra vì email**: có thể do `id` trùng. Nếu API cần phản hồi chính xác, phải xác định constraint đã vi phạm theo quy tắc hệ thống, thay vì đoán từ một thông báo lỗi SQL bất kỳ.

Với query không bắt buộc có dữ liệu:

```java
public java.util.Optional<String> findEmail(long id) {
    java.util.List<String> emails = jdbc.queryForList(
            "SELECT email FROM accounts WHERE id = ?",
            String.class, id);
    return emails.stream().findFirst();
}
```

Đây cũng là **đoạn thành phần**; vì ID là khóa chính nên có tối đa một dòng. Nó trả `Optional.empty()` nếu không thấy dữ liệu, giúp biểu đạt “có thể không có” theo contract của phương thức, thay vì yêu cầu caller xử lý exception.

Nếu một luồng thực sự muốn trả 404 khi không tìm thấy, service/API có thể chuyển `EmptyResultDataAccessException` hoặc `Optional.empty()` thành domain “not found”. Nhưng `DataAccessException` **không tự ánh xạ HTTP status**: Spring MVC hay Spring Boot sẽ không tự biến mọi subclass thành 404/409 nếu ứng dụng chưa khai báo cách xử lý thích hợp.

### Trình tự catch quan trọng

Bắt lớp **cụ thể trước**, lớp cha sau:

```java
try {
    // Truy cập dữ liệu qua Spring.
} catch (org.springframework.dao.DuplicateKeyException ex) {
    // Xung đột unique/primary key được translator nhận diện.
} catch (org.springframework.dao.DataIntegrityViolationException ex) {
    // Các dạng vi phạm ràng buộc còn lại.
} catch (org.springframework.dao.DataAccessException ex) {
    // Lỗi truy cập dữ liệu chưa xử lý ở các nhánh trên.
}
```

Đây là đoạn minh họa (phần thân `try` tùy nghiệp vụ). Nếu đặt `catch (DataAccessException)` lên đầu, Java sẽ báo các `catch` subclass phía sau không thể đạt tới (unreachable). Hãy tránh bắt cả gốc rồi trả success vì điều đó che mất lỗi thực sự.

## 7. Quan hệ với @Repository và JPA/Hibernate

Khi dùng `JdbcTemplate`, exception translation nằm ngay trong đường xử lý JDBC. Với code dùng **JPA/Hibernate trực tiếp**, provider có thể ném `jakarta.persistence.PersistenceException`, `OptimisticLockException` hoặc exception của Hibernate. Spring có thể dịch chúng sang hệ `DataAccessException`, nhưng đường dịch cần được tích hợp và cấu hình đúng.

Ví dụ DAO do Spring quản lý:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class AccountJpaDao {
    @PersistenceContext
    private EntityManager entityManager;

    public Object find(long id) {
        return entityManager.find(AccountEntity.class, id);
    }
}
```

Đây là đoạn **minh họa trong ứng dụng có cấu hình JPA**; lớp `AccountEntity` được giả định đã khai báo `@Entity`, và phần build cần JPA provider/transaction manager phù hợp. `@Repository` đánh dấu bean tầng lưu trữ. Khi ứng dụng đăng ký `PersistenceExceptionTranslationPostProcessor` cùng các `PersistenceExceptionTranslator` phù hợp (hoặc dùng auto-configuration hỗ trợ), lỗi persistence có thể được dịch qua proxy của bean `@Repository`.

**Giới hạn quan trọng:**

- Chỉ gắn `@Repository` vào một lớp **không bảo đảm tự động** mọi exception native đều được dịch nếu cơ chế post-processor/translator không hoạt động.
- Exception có thể xuất hiện khi `flush()` hoặc **commit transaction**, sau khi code DAO đã trở về. Khi đó vị trí catch và translation có thể khác với đường gọi repository thông thường.
- `EntityManager.find(...)` theo hợp đồng JPA có thể trả `null` nếu không thấy entity; không tự động sinh `EmptyResultDataAccessException` giống `JdbcTemplate.queryForObject(...)`.
- Một số lỗi Java hay lỗi mapping không phù hợp với `DataAccessException`; không gượng ép tất cả `IllegalArgumentException`/`NullPointerException` thành lỗi database.

**Đọc theo khả năng thay đổi tầng DAO:** Nếu tầng service quan tâm quy tắc “đã bị cập nhật đồng thời”, nó nên xử lý `OptimisticLockingFailureException` hoặc domain exception tương ứng, thay vì phụ thuộc trực tiếp vào tên exception của một phiên bản Hibernate cụ thể.

## 8. DataAccessException và rollback transaction

Vì mọi `DataAccessException` đều là `RuntimeException`, **mặc định** một exception như vậy thoát ra khỏi transaction method được Spring quản lý sẽ đánh dấu transaction rollback.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.jdbc.core.JdbcTemplate;

@Service
public class RegistrationService {
    private final JdbcTemplate jdbc;

    public RegistrationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void register(long accountId, String email) {
        jdbc.update("INSERT INTO accounts (id, email) VALUES (?, ?)",
                accountId, email);
        jdbc.update("INSERT INTO registration_events (account_id) VALUES (?)",
                accountId);
    }
}
```

Đây là **lớp thành phần của ứng dụng Spring**, giả định bảng `accounts` và `registration_events` tồn tại, có `DataSource`/transaction manager phù hợp và Spring gọi phương thức qua transactional proxy. Nếu lệnh INSERT thứ hai thất bại và `DataAccessException` thoát khỏi `register`, Spring rollback toàn bộ những thay đổi thuộc cùng transaction.

Những điểm dễ nhầm:

1. `@Transactional` chỉ có hiệu lực khi lời gọi đi qua cơ chế transaction interception đang hoạt động. Gọi `new RegistrationService(...)` thủ công hoặc self-invocation không đi qua proxy có thể bỏ qua transaction.
2. Mặc định Spring rollback với `RuntimeException` và `Error`. Checked exception không tự động rollback trừ khi cấu hình `rollbackFor` (hoặc quy tắc khác).
3. Nếu bắt `DataAccessException` **bên trong** transaction rồi vẫn trả thành công, mã quản lý transaction có thể không còn nhận tín hiệu lỗi; tùy công nghệ DB, transaction cũng có thể đã bị đánh dấu rollback-only. Đừng nuốt lỗi.
4. `@Transactional(noRollbackFor = SomeDataAccessException.class)` có thể đổi mặc định. Chỉ dùng khi có thiết kế rõ ràng, vì commit sau lỗi truy cập dữ liệu rất dễ làm hỏng bất biến.
5. Với JPA, lỗi vi phạm ràng buộc có thể lộ ra tại flush hoặc commit; chỗ phát sinh lỗi quan sát được không nhất thiết là dòng gọi `save(...)`.

**Không bắt một lỗi trong transaction và chạy lại ngay câu SQL trên cùng persistence context/connection** nếu DB đã đặt transaction vào trạng thái lỗi hoặc persistence context không còn nhất quán. Hãy đánh giá rollback và khởi tạo một giao dịch mới ở boundary phù hợp.

## 9. Phân loại lỗi để chọn cách khắc phục

Không nên có một `catch (DataAccessException) { retry(); }` chung cho toàn bộ hệ. Chiến lược tùy subclass và nghiệp vụ:

| Nhóm lỗi | Ví dụ | Chính sách thường hợp lý |
| --- | --- | --- |
| Non-transient | `BadSqlGrammarException` | Sửa câu SQL, schema hoặc migration |
| Non-transient | `DataIntegrityViolationException` | Kiểm tra dữ liệu/constraint; trả lỗi nghiệp vụ phù hợp |
| Non-transient | `EmptyResultDataAccessException` | Xác định contract: không tìm thấy có hợp lệ không? |
| Transient | `QueryTimeoutException` | Kiểm tra tải, timeout, hiệu năng và retry có giới hạn nếu an toàn |
| Transient | `CannotAcquireLockException` | Cân nhắc retry toàn bộ transaction với backoff và giới hạn số lần |
| Transient | `OptimisticLockingFailureException` | Tải lại bản mới và hòa giải; không âm thầm ghi đè version mới |
| Recoverable | `RecoverableDataAccessException` | Phục hồi connection/tài nguyên, rồi thử lại toàn bộ thao tác khi an toàn |
| Resource failure | `DataAccessResourceFailureException` | Xác định hạ tầng sẵn sàng, trạng thái connection pool, circuit breaker |

**“Transient” không có nghĩa có thể retry tùy ý.** Chỉ retry khi thao tác an toàn để chạy lại: idempotent, không gây gửi email/thanh toán hai lần, hiểu rõ tình trạng commit, có timeout và backoff. Thường phải retry **cả transaction trong một lần gọi mới**, thay vì chỉ retry một câu SQL giữa transaction đã thất bại. Các lỗi optimistic locking đòi hỏi giải quyết dữ liệu cạnh tranh; tự động tăng version rồi ghi lại giá trị cũ dễ tạo *lost update*.

Nếu không xác định chắc commit đã thành công hay chưa sau một lỗi mạng, retry ghi mà không có idempotency key hoặc khóa chống trùng có thể tạo tác dụng phụ lặp lại. Cần thiết kế API/transaction đúng, không suy ra từ riêng exception class.

## 10. Xem nguyên nhân gốc khi chẩn đoán

`DataAccessException` kế thừa các phương thức hỗ trợ truy cập chuỗi nguyên nhân từ `NestedRuntimeException`:

- `getCause()`: exception trực tiếp được bọc, nếu có.
- `getRootCause()`: nguyên nhân ở cuối chuỗi, có thể là `null` nếu không có cause.
- `getMostSpecificCause()`: trả nguyên nhân cụ thể nhất; nếu không có cause thì trả chính exception hiện tại.
- `contains(SomeException.class)`: kiểm tra một kiểu exception có xuất hiện trong chuỗi nguyên nhân hay không.

Đặc biệt, các exception JDBC như `BadSqlGrammarException` còn có `getSQLException()` (và `getSql()`) để xem lỗi SQL bên dưới khi cần. Không phải mọi `DataAccessException` đều có `SQLException` ở phần cause (ví dụ lỗi result size phát sinh từ hợp đồng của Spring).

Ví dụ **phương thức tiện ích** dành cho class xử lý/logging:

```java
import java.sql.SQLException;
import org.springframework.dao.DataAccessException;

public static String describeDataAccessError(DataAccessException ex) {
    Throwable deepest = ex.getMostSpecificCause();
    String category = ex.getClass().getSimpleName();

    if (deepest instanceof SQLException sql) {
        return category + " (SQLState=" + sql.getSQLState()
                + ", vendorCode=" + sql.getErrorCode() + ")";
    }

    return category + " (cause=" + deepest.getClass().getSimpleName() + ")";
}
```

Đây là **phương thức đặt trong một class hợp lệ**, không phải chương trình có `main`. Nó dùng pattern matching `instanceof` có từ Java 16 (phù hợp Java 17+). Việc truy cập SQLState/vendor code giúp điều tra; **không hardcode HTTP status hoặc thông báo nghiệp vụ dựa trên chuỗi SQLState chưa kiểm chứng**.

**Nguyên tắc bảo mật khi log lỗi:** lưu loại lỗi, mã SQLState, trace/correlation ID và thông tin vận hành cần thiết; hạn chế log SQL đầy đủ kèm tham số chứa mật khẩu, token, dữ liệu cá nhân, số thẻ hoặc bí mật. Trả lời API bằng thông điệp an toàn thay vì đẩy trực tiếp `ex.getMessage()` ra ngoài.

## 11. Bảng quyết định ở service và API

| Trường hợp | Loại lỗi Spring có thể gặp | Xử lý ở service | Phản hồi HTTP minh họa khi phù hợp |
| --- | --- | --- | --- |
| Tạo tài khoản có email trùng | `DuplicateKeyException`/`DataIntegrityViolationException` | Chuyển thành domain conflict sau khi biết constraint nào vi phạm | `409 Conflict` |
| Tra cứu ID yêu cầu có nhưng không thấy | `EmptyResultDataAccessException` (với `queryForObject`) | Chuyển thành not-found theo contract | `404 Not Found` |
| Truy vấn trả hai hàng dù cần một | `IncorrectResultSizeDataAccessException` | Kiểm tra invariant, DB/schema và query | Thường là lỗi phía server |
| Người dùng gửi version cũ | `OptimisticLockingFailureException` | Yêu cầu refresh/hòa giải trạng thái | `409 Conflict`, hoặc `412 Precondition Failed` với HTTP `If-Match` |
| DB đang timeout/mất kết nối | `QueryTimeoutException`/exception resource | Xử lý availability, retry có kiểm soát, log vận hành | Có thể `503 Service Unavailable` |
| SQL sai do deploy thiếu migration | `BadSqlGrammarException` | Báo lỗi nội bộ, khắc phục schema/SQL | `500 Internal Server Error` |

Các mã HTTP chỉ là **ví dụ tùy thiết kế API**. Spring `DataAccessException` không tự đặt HTTP status. Đừng chuyển mọi `DataIntegrityViolationException` thành `409` (có thể là foreign key/NOT NULL do bug nội bộ), hay mọi `DataAccessException` thành `404`.

Trong hệ thống có nhiều DAO, service nên dựa trên **thông tin nghiệp vụ và subclass đủ cụ thể**. Ở tầng biên, một handler tổng quát cho `DataAccessException` có thể bảo đảm lỗi không rò ra ngoài nhưng phải log/giữ nguyên nhân để vận hành.

## 12. Kiểm thử hành vi và lỗi thường gặp

Các ca nên có trong integration test (với H2 để học và với DB thật để xác nhận hành vi production):

| Ca | Thao tác | Kết quả cần kiểm tra |
| --- | --- | --- |
| Trùng khóa | INSERT với email đã tồn tại | Bắt `DataIntegrityViolationException` hoặc subclass tương thích |
| Không tìm thấy | `queryForObject` khi không có row | `EmptyResultDataAccessException` |
| Quá nhiều kết quả | `queryForObject` khi có nhiều row | `IncorrectResultSizeDataAccessException` |
| Không có row nhưng API cho phép | `query` với điều kiện không khớp | Danh sách rỗng, không ép exception |
| UPDATE không khớp | `JdbcTemplate.update` với ID vắng mặt | Row count `0`; service tự diễn giải |
| SQL không hợp lệ | Truy vấn tên cột sai | Exception thuộc nhóm sử dụng tài nguyên không hợp lệ, điển hình `BadSqlGrammarException` |
| Giao dịch hai bước | INSERT A thành công, INSERT B vi phạm constraint | Transaction rollback, A không còn sau rollback |
| Optimistic locking | Hai request cùng version | Một cập nhật thắng, request cũ nhận xung đột hoặc exception phù hợp |
| Lỗi tạm thời | Lock/timeout mô phỏng có kiểm soát | Chỉ retry tại boundary an toàn, có giới hạn |
| Exception translation JPA | Repository dùng ORM bị vi phạm constraint | Xác minh cơ chế translation thực sự hoạt động và thời điểm flush/commit |

**Các lỗi thiết kế thường gặp:**

1. **Nhầm `DataAccessException` với `SQLException`.** Đầu tiên là unchecked Spring exception, thứ hai là checked JDBC exception. Không bắt `SQLException` trực tiếp quanh `JdbcTemplate.queryForObject` rồi nghĩ nó sẽ bắt mọi lỗi được dịch.
2. **Cho rằng tất cả lỗi DB đều thành `DataAccessException`.** API dùng JDBC raw hoặc JPA code không qua integration/translator có thể ném loại exception riêng.
3. **Bắt `DataAccessException` trước subclass.** Làm `catch` cụ thể unreachable hoặc mất khả năng xử lý khác nhau.
4. **Nhầm `EmptyResultDataAccessException` với một DB outage.** Nó có thể chỉ là kết quả không phù hợp contract query.
5. **Coi `TransientDataAccessException` là tín hiệu retry bất hạn.** Retry có thể nhân đôi side effects, tăng tải hoặc ghi đè dữ liệu mới.
6. **Nuốt exception trong transaction.** Hệ thống có thể commit một phần hoặc rơi vào trạng thái rollback-only ngoài ý muốn.
7. **Ánh xạ subclass sang HTTP status cứng nhắc.** Cần xác minh constraint, ngữ cảnh nghiệp vụ và API contract.
8. **Không giữ cause.** Khi tạo domain exception hoặc log, hãy giữ `ex` làm nguyên nhân (nếu phù hợp), giúp truy vết JDBC SQLState/driver.
9. **Dùng unit test giả lập exception như bằng chứng mapping thực tế.** Mockito có thể xác minh nhánh catch; integration test mới kiểm chứng translator + driver + schema.
10. **Coi DataAccessException là lỗi do người dùng gây ra.** Có lỗi dữ liệu đầu vào, nhưng cũng có lỗi SQL, migration, connection, transaction hoặc code.

**Checklist áp dụng:**

- Tầng repository đang dùng `JdbcTemplate`, Spring Data repository, hay JPA/Hibernate API trực tiếp? Exception translation có thực sự hoạt động ở đường đó không?
- Service cần nhận loại lỗi **nào** để đưa ra quyết định; nên bắt subclass hay để exception đi lên?
- Trường hợp dữ liệu vắng mặt là kết quả bình thường hay lỗi contract? Chọn `query`/`Optional` hoặc `queryForObject` cho phù hợp.
- Transaction boundary và rollback có đúng khi exception xảy ra ở DAO, flush hoặc commit không?
- Nếu retry: có idempotency, transaction mới, giới hạn số lần và backoff không?
- Có integration test bằng database/driver thực tế và logging an toàn cho tình huống lỗi không?

**Kết luận:** `DataAccessException` là nền tảng để Spring biểu diễn các lỗi truy cập dữ liệu dưới dạng những exception runtime có ngữ nghĩa nhất quán. Giá trị của nó nằm ở việc **phân loại và xử lý đúng subclass**, giữ nguyên nguyên nhân kỹ thuật, kết hợp transaction/rollback và đặt chính sách nghiệp vụ ở tầng phù hợp.

## Tài liệu tham khảo

- Spring Framework, `DataAccessException` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataAccessException.html
- Spring Framework, DAO Support / Consistent Exception Hierarchy: https://docs.spring.io/spring-framework/reference/data-access/dao.html
- Spring Framework, JDBC Core / `SQLExceptionTranslator`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework, `SQLExceptionSubclassTranslator` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/SQLExceptionSubclassTranslator.html
- Spring Framework, ORM Exception Translation: https://docs.spring.io/spring-framework/reference/data-access/orm/general.html
- Spring Framework, Transaction Rollback: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework, `DataIntegrityViolationException` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html
- Spring Framework, `EmptyResultDataAccessException` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/EmptyResultDataAccessException.html