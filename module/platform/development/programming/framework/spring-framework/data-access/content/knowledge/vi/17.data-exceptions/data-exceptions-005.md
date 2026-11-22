# DuplicateKeyException, DataIntegrityViolationException và lỗi ràng buộc trong Spring Data Access

> **Phạm vi:** Spring Framework Data Access → Ngoại lệ dữ liệu. Bài này tập trung vào hai loại ngoại lệ Spring `DuplicateKeyException` và `DataIntegrityViolationException`, quan hệ kế thừa của chúng, lỗi `UNIQUE`/`PRIMARY KEY`/`FOREIGN KEY`/`NOT NULL`/`CHECK`, cơ chế dịch `SQLException`, transaction và cách xử lý đúng trong ứng dụng. Ví dụ dùng Spring JDBC, PostgreSQL thật và Java 17+.

## 1. Hiểu đúng hai exception trước khi bắt lỗi

Trong Java JDBC thuần, một lệnh `INSERT` hoặc `UPDATE` vi phạm ràng buộc có thể ném `SQLException` hay lớp con của nó. `JdbcTemplate` của Spring dịch lỗi ở tầng JDBC thành hệ ngoại lệ thống nhất, không phụ thuộc trực tiếp vào một driver, tên là `DataAccessException`.

Cây kế thừa rút gọn:

```text
RuntimeException
  └─ NestedRuntimeException
       └─ DataAccessException
            └─ NonTransientDataAccessException
                 └─ DataIntegrityViolationException
                      └─ DuplicateKeyException
```

Điểm quyết định: **`DuplicateKeyException` là một dạng cụ thể của `DataIntegrityViolationException`**.

- `DataIntegrityViolationException`: một ràng buộc hoặc quy tắc toàn vẹn dữ liệu bị vi phạm, ví dụ `NOT NULL`, `FOREIGN KEY`, `CHECK`, một số lỗi khóa duy nhất và ràng buộc khác. Không phải mọi lỗi SQL đều thuộc nhóm này.
- `DuplicateKeyException`: trường hợp cụ thể bị **trùng giá trị của primary key, unique constraint hoặc unique index** khi Spring nhận diện được nguyên nhân. Nó thường xảy ra lúc tạo bản ghi mới với `email` đã tồn tại, hoặc dùng lại khóa `id`.
- `NonTransientDataAccessException`: nghĩa là **không kỳ vọng cùng một thao tác với dữ liệu y hệt sẽ tự thành công chỉ vì thử lại ngay**, khác với lỗi mất kết nối tạm thời, deadlock hay tranh chấp serialization. Đây là phân loại kỹ thuật; quy tắc nghiệp vụ có thể sửa dữ liệu rồi thử lại.

**Bẫy thứ tự `catch`:** luôn bắt lớp cụ thể trước:

```java
try {
    jdbc.update("INSERT INTO account(id, email) VALUES (?, ?)",
                id, email);
} catch (DuplicateKeyException ex) {
    // Khóa duy nhất/primary key bị trùng, có thể ánh xạ thành business conflict.
} catch (DataIntegrityViolationException ex) {
    // Các vi phạm toàn vẹn dữ liệu còn lại.
}
```

Nếu đặt `catch (DataIntegrityViolationException)` trước `catch (DuplicateKeyException)`, khối sau **không thể tới được** và Java báo lỗi biên dịch. Không nên dùng `catch (DataAccessException)` cho tất cả lỗi rồi mặc định đó là “trùng dữ liệu”.

## 2. Những ràng buộc thật ở cơ sở dữ liệu

| Ràng buộc | Dữ liệu gây lỗi | Kỳ vọng với PostgreSQL và Spring JDBC đã cấu hình chuẩn | SQLSTATE PostgreSQL |
| --- | --- | --- | --- |
| `PRIMARY KEY` | Chèn `id=1` lần thứ hai | `DuplicateKeyException` | `23505` |
| `UNIQUE(email)` | Hai bản ghi dùng cùng `email` | `DuplicateKeyException` | `23505` |
| `FOREIGN KEY` | `purchase.customer_id` không tồn tại trong bảng cha | `DataIntegrityViolationException` | `23503` |
| `NOT NULL` | `email=NULL` khi cột cấm NULL | `DataIntegrityViolationException` | `23502` |
| `CHECK` | `status='UNKNOWN'` khi chỉ chấp nhận hai trạng thái | `DataIntegrityViolationException` | `23514` |

Các mã trên thuộc **SQLSTATE Class 23 — Integrity Constraint Violation** của PostgreSQL. `23505` dùng cho cả trùng primary key và unique key, vì vậy **chỉ từ loại `DuplicateKeyException` hoặc SQLSTATE không biết được ràng buộc nào bị trùng**. Muốn phân biệt `email` với `id`, cần biết lệnh SQL, tên constraint đáng tin từ DB hoặc trạng thái nghiệp vụ.

Một ràng buộc khác quan trọng:

- Cột có `UNIQUE` nhưng **không có `NOT NULL`** trong PostgreSQL thông thường vẫn có thể chứa nhiều `NULL`, do các `NULL` không được xem là bằng nhau cho unique constraint mặc định. Nếu email bắt buộc, cần **cả** `NOT NULL` và `UNIQUE`.
- `FOREIGN KEY` kiểm tra tính tồn tại của bản ghi được tham chiếu; lỗi có thể xuất hiện khi chèn/xoá/sửa, tuỳ hành vi `ON DELETE`, `ON UPDATE` và thời điểm kiểm tra constraint.
- `CHECK` chỉ kiểm tra biểu thức đã định nghĩa. Ví dụ `CHECK (amount > 0)` **không tự cấm NULL** trong PostgreSQL; cần thêm `NOT NULL` nếu không cho phép NULL.
- Validation trong Java như `@NotNull`, `@Email` giúp phản hồi sớm nhưng **không thay thế ràng buộc cơ sở dữ liệu**: một tiến trình khác, import dữ liệu hoặc yêu cầu đồng thời vẫn có thể ghi DB.

## 3. Từ lỗi PostgreSQL đến ngoại lệ Spring: đi qua những tầng nào?

```text
Ứng dụng gọi JdbcTemplate.update(...)
          ↓
Spring chuẩn bị và thực thi PreparedStatement
          ↓
PostgreSQL phát hiện UNIQUE/FK/NOT NULL/CHECK bị vi phạm
          ↓
pgJDBC ném SQLException (có SQLSTATE + vendor error code)
          ↓
JdbcTemplate → SQLExceptionTranslator
          ↓
DataAccessException / DataIntegrityViolationException
                          └─ DuplicateKeyException nếu nhận diện trùng khóa
          ↓
Transaction đánh dấu lỗi/rollback và tầng nghiệp vụ xử lý
```

`SQLExceptionTranslator` là giao diện Spring dùng để ánh xạ lỗi của driver thành hệ `DataAccessException`. Có hai cơ chế phổ biến cần phân biệt:

1. **`SQLExceptionSubclassTranslator`**: mặc định của Spring Framework 6.x, dùng các subclass của `SQLException` (JDBC 4) và fallback sang **`SQLStateSQLExceptionTranslator`**. Vì thế PostgreSQL SQLSTATE `23505` thường được nhận diện thành `DuplicateKeyException`, các mã ràng buộc khác như `23503`/`23502`/`23514` thành `DataIntegrityViolationException`.
2. **`SQLErrorCodeSQLExceptionTranslator`**: dịch dựa trên bảng error code riêng từng DBMS; trong Spring 6.x được chọn tự động khi có tệp `sql-error-codes.xml` tại classpath root, hoặc có thể thiết lập minh bạch bằng `JdbcTemplate.setExceptionTranslator(...)`. Các mã của PostgreSQL trong bảng Spring gán `23505` vào nhóm duplicate, `23502`, `23503`, `23514` vào nhóm integrity.

Chính vì kết quả dịch phụ thuộc **driver, DBMS, SQLSTATE/vendor code và translator đang dùng**, không nên hứa rằng mọi cơ sở dữ liệu luôn trả đúng cùng một subclass Spring. Ví dụ MySQL dùng vendor code `1062` cho duplicate key; các DBMS có thể cùng dùng SQLSTATE tổng quát `23000` với mã chi tiết khác. Kiểm chứng trên cấu hình triển khai thật.

`JdbcTemplate` tự xử lý `SQLException` trong lời gọi của nó. Annotation `@Repository` và `PersistenceExceptionTranslationPostProcessor` còn hỗ trợ dịch một số ngoại lệ ở tầng repository/ORM khi có hạ tầng phù hợp; **đừng nhầm** rằng phải có `@Repository` thì `JdbcTemplate` mới dịch lỗi.

### 3.1. Lấy nguyên nhân gốc để chẩn đoán

Ở tầng service/infrastructure, log tên tác vụ, tên constraint nếu được cung cấp an toàn, SQLSTATE và mã vendor, đồng thời giữ stack trace tại nơi phù hợp; **không đưa nguyên văn SQL chứa dữ liệu nhạy cảm vào phản hồi API**.

```java
import java.sql.SQLException;
import org.springframework.dao.DataIntegrityViolationException;

static SQLException findSqlCause(DataIntegrityViolationException ex) {
    for (Throwable cause = ex; cause != null; cause = cause.getCause()) {
        if (cause instanceof SQLException sql) {
            return sql;
        }
    }
    return null;
}
```

Hàm này đủ cho ví dụ đơn giản. Trong batch, `BatchUpdateException` có thể lưu thêm các lỗi trong `SQLException.getNextException()`, nên khi chẩn đoán thực tế cần kiểm tra cả **chuỗi next-exception**, không chỉ cause chain. Đừng phân loại dựa trên văn bản thông báo lỗi (`message.contains("duplicate")`), bởi message có thể thay đổi theo locale, driver và phiên bản.

## 4. Thực hành đầy đủ: PostgreSQL + Spring JDBC + Java 17

Mục tiêu thực nghiệm: tạo đúng năm kiểu vi phạm dữ liệu, đối chiếu **ngoại lệ Spring + SQLSTATE**, sau đó chứng minh một transaction có hai thao tác sẽ **rollback hoàn toàn** khi thao tác thứ hai trùng khóa. Không dùng H2 thay PostgreSQL trong bài này, bởi cách dịch lỗi phải được quan sát với driver thực tế.

### 4.1. Khởi động PostgreSQL thử nghiệm

Yêu cầu JDK 17+, Maven 3.9+ và Docker. Dùng database/container riêng để không tác động dữ liệu thật.

```bash
docker run --rm -d --name spring-constraint-lab -e POSTGRES_DB=constraint_lab -e POSTGRES_USER=lab -e POSTGRES_PASSWORD=labpass -p 54339:5432 postgres:16

docker exec spring-constraint-lab pg_isready -U lab -d constraint_lab
```

Chỉ chạy chương trình sau khi `pg_isready` báo PostgreSQL nhận kết nối. Trong bài thực hành cục bộ, thông tin `lab/labpass` chỉ là tài khoản tạm. Khi triển khai thật, dùng secret manager, TLS và cấu hình tài khoản riêng đúng quyền hạn.

Tạo cấu trúc:

```text
spring-constraint-lab/
├── pom.xml
└── src/main/java/ConstraintDemo.java
```

### 4.2. Tệp Maven `pom.xml`

Các phiên bản dưới đây là phiên bản cụ thể để bài có thể tái hiện; ứng dụng thực tế nên dùng dependency management/BOM và phiên bản đã được tổ chức kiểm thử.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-constraint-lab</artifactId>
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
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <version>42.7.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
                <configuration>
                    <mainClass>ConstraintDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring JDBC kéo các dependency lõi cần thiết; chương trình này dùng `DriverManagerDataSource` vì đơn giản và không cần Spring Boot. Trong ứng dụng web thật nên dùng connection pool và transaction manager do ứng dụng cấu hình.

### 4.3. Tệp `src/main/java/ConstraintDemo.java`

```java
import java.sql.SQLException;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class ConstraintDemo {
    private static final String INSERT_CUSTOMER =
            "INSERT INTO demo_customer(id, email, status) VALUES (?, ?, ?)";
    private static final String INSERT_PURCHASE =
            "INSERT INTO demo_purchase(id, customer_id, amount) VALUES (?, ?, ?)";

    private static SQLException sqlCause(Throwable error) {
        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            if (cause instanceof SQLException sql) {
                return sql;
            }
        }
        throw new IllegalStateException("No nested SQLException", error);
    }

    // Một lỗi được coi là đúng nếu cả Spring exception type lẫn
    // SQLSTATE của PostgreSQL đều khớp với dự đoán.
    private static void expectViolation(
            String label,
            String expectedState,
            Class<? extends DataIntegrityViolationException> expectedType,
            Runnable action) {
        try {
            action.run();
        } catch (DataIntegrityViolationException ex) {
            if (!expectedType.isInstance(ex)) {
                throw new IllegalStateException(
                        "Unexpected Spring type for " + label, ex);
            }
            SQLException sql = sqlCause(ex);
            if (!expectedState.equals(sql.getSQLState())) {
                throw new IllegalStateException(
                        "Unexpected SQLSTATE for " + label
                                + ": " + sql.getSQLState(), ex);
            }
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName()
                    + " / SQLSTATE=" + sql.getSQLState());
            return;
        }
        throw new IllegalStateException(
                "Expected constraint violation: " + label);
    }

    public static void main(String[] args) throws Exception {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.postgresql.Driver");
        ds.setUrl(System.getenv().getOrDefault(
                "DB_URL",
                "jdbc:postgresql://localhost:54339/constraint_lab"));
        ds.setUsername(System.getenv().getOrDefault("DB_USER", "lab"));
        ds.setPassword(System.getenv().getOrDefault(
                "DB_PASSWORD", "labpass"));

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        TransactionTemplate tx = new TransactionTemplate(
                new DataSourceTransactionManager(ds));

        // Chỉ dùng schema/bảng test này; chương trình xóa và tạo lại.
        jdbc.execute("DROP TABLE IF EXISTS demo_purchase");
        jdbc.execute("DROP TABLE IF EXISTS demo_customer");
        jdbc.execute("""
                CREATE TABLE demo_customer (
                    id INTEGER PRIMARY KEY,
                    email VARCHAR(120) NOT NULL UNIQUE,
                    status VARCHAR(20) NOT NULL
                        CONSTRAINT chk_demo_customer_status
                        CHECK (status IN ('ACTIVE', 'SUSPENDED'))
                )
                """);
        jdbc.execute("""
                CREATE TABLE demo_purchase (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER NOT NULL
                        REFERENCES demo_customer(id),
                    amount INTEGER NOT NULL
                        CHECK (amount > 0)
                )
                """);
        jdbc.update(INSERT_CUSTOMER, 1, "owner@example.test", "ACTIVE");

        expectViolation(
                "UNIQUE_EMAIL", "23505", DuplicateKeyException.class,
                () -> jdbc.update(
                        INSERT_CUSTOMER,
                        2, "owner@example.test", "ACTIVE"));

        expectViolation(
                "PRIMARY_KEY", "23505", DuplicateKeyException.class,
                () -> jdbc.update(
                        INSERT_CUSTOMER,
                        1, "second@example.test", "ACTIVE"));

        expectViolation(
                "FOREIGN_KEY", "23503", DataIntegrityViolationException.class,
                () -> jdbc.update(INSERT_PURCHASE, 1, 999, 100));

        expectViolation(
                "NOT_NULL", "23502", DataIntegrityViolationException.class,
                () -> jdbc.update(
                        INSERT_CUSTOMER, 3, null, "ACTIVE"));

        expectViolation(
                "CHECK", "23514", DataIntegrityViolationException.class,
                () -> jdbc.update(
                        INSERT_CUSTOMER,
                        4, "status@example.test", "UNKNOWN"));

        // Hai INSERT thuộc CÙNG transaction; lệnh thứ hai gây lỗi.
        try {
            tx.executeWithoutResult(status -> {
                jdbc.update(
                        INSERT_CUSTOMER, 10, "pending@example.test", "ACTIVE");
                jdbc.update(
                        INSERT_CUSTOMER, 11, "owner@example.test", "ACTIVE");
            });
            throw new IllegalStateException(
                    "Expected duplicate-key failure in transaction");
        } catch (DuplicateKeyException ex) {
            if (!"23505".equals(sqlCause(ex).getSQLState())) {
                throw new IllegalStateException(
                        "Transaction did not fail as expected", ex);
            }
        }

        Integer pending = jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_customer WHERE id = ?",
                Integer.class, 10);
        if (pending == null || pending != 0) {
            throw new IllegalStateException("Transaction was not rolled back");
        }
        System.out.println("TRANSACTION_ROLLBACK -> pending=0");

        // Chỉ bỏ qua xung đột trên email, không bỏ qua mọi lỗi dữ liệu.
        int inserted = jdbc.update(
                """
                INSERT INTO demo_customer(id, email, status)
                VALUES (?, ?, ?)
                ON CONFLICT (email) DO NOTHING
                """,
                2, "owner@example.test", "ACTIVE");
        if (inserted != 0) {
            throw new IllegalStateException("Expected conflict to skip insert");
        }
        System.out.println("ON_CONFLICT_INSERTED -> 0");

        Integer remaining = jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_customer",
                Integer.class);
        if (remaining == null || remaining != 1) {
            throw new IllegalStateException("Unexpected final row count");
        }
        System.out.println("CUSTOMERS_LEFT -> 1");
    }
}
```

**Giải thích các điểm quan trọng trong code:**

- Mỗi lần thử lỗi dùng một `jdbc.update(...)` độc lập; PostgreSQL trả SQLSTATE tương ứng, Spring dịch thành exception. Bài kiểm tra không chấp nhận “có lỗi bất kỳ là PASS”: cả **kiểu exception và SQLSTATE** phải khớp.
- `PRIMARY_KEY` và `UNIQUE_EMAIL` đều ra `23505`; loại ngoại lệ chưa đủ phân biệt lỗi nào. Test phân biệt dựa vào trường hợp đầu vào.
- Khi `NOT NULL`, tham số `null` được truyền qua JDBC PreparedStatement. Kết quả là lỗi DB do **constraint**, không phải `NullPointerException` của Java.
- `TransactionTemplate` và `JdbcTemplate` dùng **cùng DataSource**; Spring gắn connection vào transaction hiện tại, vì vậy bản ghi `id=10` phải được rollback khi bản ghi `id=11` gây duplicate.
- `ON CONFLICT (email) DO NOTHING` là cú pháp **PostgreSQL**, không phải hành vi của `JdbcTemplate`. Chỉ trường hợp xung đột email được bỏ qua có chủ đích; các lỗi `NOT NULL`, `CHECK`, `FOREIGN KEY` khác vẫn có thể làm câu lệnh thất bại.

### 4.4. Biên dịch, chạy, đọc output

Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Trên PostgreSQL thử nghiệm với dependency được nêu, khi mọi kiểm tra đi qua, các dòng do chương trình in ra là:

```text
UNIQUE_EMAIL -> DuplicateKeyException / SQLSTATE=23505
PRIMARY_KEY -> DuplicateKeyException / SQLSTATE=23505
FOREIGN_KEY -> DataIntegrityViolationException / SQLSTATE=23503
NOT_NULL -> DataIntegrityViolationException / SQLSTATE=23502
CHECK -> DataIntegrityViolationException / SQLSTATE=23514
TRANSACTION_ROLLBACK -> pending=0
ON_CONFLICT_INSERTED -> 0
CUSTOMERS_LEFT -> 1
```

Nếu phiên bản Spring/driver, cấu hình translator hoặc DBMS thay đổi khiến kiểu được dịch khác, chương trình cố ý thất bại để bạn điều tra, thay vì in kết quả đẹp nhưng sai. Log riêng của Maven/driver không được tính vào stdout dự kiến trên.

Dọn tài nguyên khi xong:

```bash
docker stop spring-constraint-lab
```

## 5. Transaction quyết định dữ liệu còn lại sau lỗi

### 5.1. Hai lệnh, một transaction

Trong mã trên:

```text
BEGIN
  INSERT id=10, email=pending@example.test   → thành công tạm thời
  INSERT id=11, email=owner@example.test      → 23505
ROLLBACK                                        → id=10 cũng không tồn tại
```

Một ngoại lệ `DataAccessException` (bao gồm `DuplicateKeyException`) là **unchecked exception**; với `@Transactional` mặc định, nó thường dẫn tới rollback. `TransactionTemplate` cũng rollback khi callback ném runtime exception. Cần đảm bảo cả hai lệnh cùng tham gia transaction: cùng `DataSource` và cùng transaction manager, không tự mở connection bên ngoài.

Đối với Spring AOP `@Transactional`, lời gọi **tự gọi một phương thức trong chính bean** có thể không đi qua proxy, do đó transaction interceptor không chạy. Đừng suy rằng chỉ cần annotation là toàn bộ thao tác đã nằm trong transaction: xác nhận bằng integration test.

### 5.2. PostgreSQL: lỗi làm transaction hiện tại ở trạng thái aborted

Nếu một statement gây `23505` trong transaction PostgreSQL thông thường, những statement tiếp theo trên transaction đó có thể nhận `25P02` (**in_failed_sql_transaction**) cho đến khi rollback. Vì vậy **không** xử lý bằng cách bắt `DuplicateKeyException` giữa transaction rồi tiếp tục update như thể chưa có gì xảy ra.

```java
// PHẢN VÍ DỤ: không nên làm như sau trên PostgreSQL.
@Transactional
public void saveTwo() {
    try {
        jdbc.update("INSERT INTO demo_customer VALUES (?, ?, ?)",
                    1, "owner@example.test", "ACTIVE"); // trùng PK
    } catch (DuplicateKeyException ignored) {
        // Bắt lỗi ở đây không đưa transaction PostgreSQL về trạng thái hợp lệ.
    }
    jdbc.update("INSERT INTO demo_customer VALUES (?, ?, ?)",
                20, "next@example.test", "ACTIVE"); // có thể nhận 25P02
}
```

Đoạn trên chỉ minh họa **đường sai**; không tự chạy như một chương trình độc lập. Cách đúng thường là để exception thoát khỏi ranh giới transaction, rollback toàn đơn vị công việc, sau đó xử lý nghiệp vụ ở tầng gọi bên ngoài. Khi nghiệp vụ thật sự cần giữ lại phần việc trước lỗi, phải thiết kế savepoint/`PROPAGATION_NESTED` theo driver, transaction manager và các ràng buộc cụ thể, rồi kiểm chứng; không dùng try/catch thuần như savepoint.

Một số ràng buộc PostgreSQL có thể được định nghĩa `DEFERRABLE` và kiểm tra vào **lúc COMMIT**. Khi đó lỗi không nhất thiết xuất hiện tại `jdbc.update()` mà có thể xuất hiện tại ranh giới commit, với lớp wrapper/exception khác. Đường xử lý lỗi cần bao quanh **toàn bộ transaction** và giữ được nguyên nhân DB, không bắt duy nhất một lệnh ghi.

## 6. Trùng khóa: phòng ngừa, xử lý có chủ đích và vấn đề đồng thời

### 6.1. Đừng dựa vào “kiểm tra tồn tại trước rồi chèn”

```text
Request A                        Request B
SELECT email='a' → chưa có        SELECT email='a' → chưa có
INSERT email='a' → thành công     INSERT email='a' → 23505
```

Hai request có thể cùng nhìn thấy “chưa tồn tại”. Điều kiện kiểm tra ở service cải thiện thông báo lỗi, nhưng **ràng buộc UNIQUE ở DB mới bảo vệ tính nhất quán khi đồng thời**. Thiết kế thông thường: đặt unique constraint, ghi trong transaction, sau đó xử lý duplicate tại ranh giới nghiệp vụ/API.

Nếu constraint thực sự phản ánh quy tắc nghiệp vụ “mỗi email chỉ đăng ký một lần”, bạn có thể trả phản hồi conflict có chủ đích. Nếu duplicate xuất phát từ lỗi sinh khóa `id`, sequence mất đồng bộ hoặc dữ liệu nội bộ, không nên biến mọi `DuplicateKeyException` thành lời nhắn “email đã tồn tại”.

### 6.2. Chọn giải pháp theo ngữ nghĩa nghiệp vụ

| Nhu cầu | Hướng xử lý | Rủi ro cần xem |
| --- | --- | --- |
| Chèn mới, trùng phải báo người dùng | Giữ unique constraint, bắt `DuplicateKeyException` ở tầng phù hợp | Phải nhận diện **đúng constraint**, không làm lộ thông tin nhạy cảm |
| Gửi lại cùng yêu cầu idempotent | Idempotency key có unique constraint + lưu kết quả/kiểm soát trạng thái | Hai request cạnh tranh; đừng chỉ kiểm tra tồn tại rồi chèn |
| Trùng thì bỏ qua có chủ đích | PostgreSQL `INSERT ... ON CONFLICT (key) DO NOTHING` | Không tạo bản ghi mới; kiểm tra `updateCount=0` |
| Trùng thì cập nhật | `ON CONFLICT (key) DO UPDATE SET ...` với điều kiện rõ | Tránh ghi đè dữ liệu ngoài ý muốn; concurrency vẫn cần kiểm thử |
| Trùng PK do bộ cấp phát khóa | Sửa sequence/identity/logic tạo ID | Retry cùng ID không giải quyết nguyên nhân |
| Trùng do chạy batch nhiều lần | Thiết kế unique key/idempotency và transaction theo đơn vị công việc | Có thể rollback cả batch; phải quản lý phần đã commit |

**Không xóa constraint để “sửa exception”**: nếu constraint đang bảo vệ invariant nghiệp vụ, việc xóa nó có thể tạo dữ liệu không nhất quán lâu dài. Chỉ thay đổi schema khi quy tắc nghiệp vụ thay đổi có chủ đích và đã có kế hoạch migration dữ liệu.

## 7. Foreign key, NOT NULL, CHECK: mỗi loại cần cách sửa khác nhau

**`FOREIGN KEY`:** kiểm tra bản ghi cha có tồn tại và hợp lệ trong cùng transaction, thứ tự insert/delete, chính sách `ON DELETE`/`ON UPDATE`, khóa và tình huống đồng thời. Không tự sửa bằng cách bật/tắt kiểm tra FK trong môi trường production. Ví dụ lỗi FK lúc xóa account có đơn hàng phụ thuộc là khác với lỗi FK lúc chèn order trỏ tới account không có.

**`NOT NULL`:** kiểm tra dữ liệu đầu vào, phép ánh xạ DTO/entity sang SQL, field bắt buộc, default value và cách bind `null`. `DEFAULT` chỉ áp dụng nếu câu `INSERT` bỏ qua cột hoặc dùng `DEFAULT`; nó **không thay** một giá trị `NULL` được truyền tường minh thành giá trị mặc định.

**`CHECK`:** đối chiếu biểu thức ràng buộc trong DB, dữ liệu do API tạo, enum/bộ giá trị hợp lệ và migration. Ví dụ `status='UNKNOWN'` không nằm trong `CHECK(status IN ('ACTIVE','SUSPENDED'))`, vì vậy client phải sửa status hoặc schema phải được thay đổi theo nghiệp vụ. Không tự đoán mọi `23514` đều do enum; nó có thể xuất phát từ bất kỳ biểu thức CHECK nào.

**Khóa duy nhất:** xác định chính xác tập cột được unique. `UNIQUE(email)` khác `UNIQUE(tenant_id,email)`; ở hệ thống đa tenant, thiếu `tenant_id` có thể vô tình cấm cùng một email ở hai tenant. Tên constraint ổn định, đặt tên rõ ràng trong migration giúp chẩn đoán và viết test dễ hơn.

Cùng một `DataIntegrityViolationException` nên **không** dẫn đến cùng một phương án khắc phục cho mọi lỗi.

## 8. Xử lý ở service/API và giữ thông tin chẩn đoán

Một mô hình tổ chức hợp lý:

```text
Controller/API
  └─ Service @Transactional (ghi + xác nhận nghiệp vụ)
       └─ DAO/Repository với JdbcTemplate (SQL có tham số)
            └─ DB constraint (bảo vệ invariant cuối cùng)
                → SQLException
                → DataAccessException
  ← Transaction rollback
  ← Tầng API chuyển một lỗi nghiệp vụ đã nhận diện thành phản hồi phù hợp
```

Ở tầng API, **có thể** dùng HTTP `409 Conflict` cho trường hợp duplicate dự kiến (ví dụ email đã đăng ký) khi thông tin này được phép tiết lộ; một số validation error có thể biểu diễn bằng `400` hoặc `422` theo hợp đồng API. **Không** có quy tắc toàn cục rằng mọi `DataIntegrityViolationException` đều phải trả `409`. FK bị lỗi do bug nội bộ hoặc schema chưa đồng bộ không nhất thiết là lỗi người dùng, và không nên để lộ cấu trúc bảng qua response.

Ví dụ ánh xạ theo nghiệp vụ, **đoạn minh họa không phải controller độc lập**:

```java
try {
    accountService.createAccount(command);
} catch (DuplicateKeyException ex) {
    // Chỉ trả thông báo này nếu bạn đã xác định lỗi thuộc
    // đúng unique constraint của email và chính sách API cho phép.
    throw new AccountAlreadyExistsException("Email is already registered", ex);
}
```

Với nhiều unique constraint, đừng dựa duy nhất vào loại `DuplicateKeyException` để quyết định thông điệp. Có thể dựa trên tên constraint lấy qua API hỗ trợ của driver (ví dụ thông tin server error trong pgJDBC), kết hợp ngữ cảnh lệnh ghi và test tích hợp; tránh so khớp substring trong message ngôn ngữ tự nhiên. Khi có nhiều DBMS, bọc logic phân loại vendor-specific trong adapter hạ tầng thay vì rải SQLSTATE hard-coded khắp service.

Log phục vụ chẩn đoán: tên thao tác, mã ứng dụng, SQLSTATE, vendor code, tên constraint (nếu có), correlation id/transaction id; hạn chế log giá trị cột nhạy cảm (email, token, PII). Phản hồi client nên ổn định theo hợp đồng và không chứa nguyên câu SQL, stack trace hoặc mật khẩu DB.

## 9. Lỗi ràng buộc trong `batchUpdate()`

`JdbcTemplate.batchUpdate()` dùng khả năng batch của JDBC driver. Nếu một entry trùng key/FK/CHECK, JDBC có thể ném `BatchUpdateException`, chứa `getUpdateCounts()` và đôi khi chuỗi `getNextException()`; Spring sẽ dịch lỗi phù hợp. Không suy luận rằng mọi phần tử sau phần tử lỗi đều được áp dụng, vì driver có thể dừng hoặc tiếp tục theo cách riêng.

- `Statement.SUCCESS_NO_INFO = -2`: lệnh có thể đã thành công nhưng driver không có số dòng chính xác.
- `Statement.EXECUTE_FAILED = -3`: đánh dấu phần tử thất bại trong bảng counts nếu driver cung cấp.
- `getUpdateCounts()` không bảo đảm giao dịch **đã commit**. Nếu batch nằm trong transaction và có lỗi, quyết định rollback hay retry cần đặt ở ranh giới transaction.
- Nếu dùng `INSERT ... ON CONFLICT`, hãy xác định yêu cầu nghiệp vụ của từng phần tử (skip, update hay fail), đo số bản ghi thực tế sau commit và kiểm tra tính idempotent.

Đối với việc retry cả batch, dùng khóa/idempotency ổn định và hiểu rõ dữ liệu đã commit ở những transaction trước; không lặp vô điều kiện cùng một batch vừa gây `DuplicateKeyException`. Với lỗi kết nối không rõ server đã commit hay chưa, phải kiểm tra trạng thái nghiệp vụ trước khi chạy lại.

## 10. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “`DuplicateKeyException` khác hẳn `DataIntegrityViolationException`” | Nó là **lớp con** của `DataIntegrityViolationException`. |
| “`DataIntegrityViolationException` có nghĩa là trùng email” | Đây là **nhóm rộng** của nhiều ràng buộc và integrity errors. |
| “Có `@NotNull` thì không cần `NOT NULL` ở DB” | Validator và DB bảo vệ ở hai tầng khác nhau, có thể bỏ qua validator hoặc race. |
| “Kiểm tra email tồn tại trước khi chèn sẽ không bao giờ trùng” | Hai transaction đồng thời vẫn có thể vượt qua precheck. |
| “`catch` xong thì transaction PostgreSQL vẫn chạy tiếp” | Sau SQL error, transaction có thể ở trạng thái aborted `25P02` tới rollback/savepoint. |
| “Mọi lỗi Class 23 trên mọi DB đều sinh cùng subclass Spring” | Translator có thể khác theo DBMS/driver/version/config; phải kiểm chứng. |
| “Retry ngay cùng dữ liệu sẽ hết duplicate” | Trùng unique thường là lỗi không tạm thời; cần đổi dữ liệu hoặc xử lý conflict đúng. |
| “`ON CONFLICT DO NOTHING` là cách chữa mọi lỗi integrity” | Nó xử lý conflict được chỉ định, không thay thế các constraint khác hay chính sách API. |
| “Thấy `BatchUpdateException` tức là tất cả insert đều thất bại” | Số phần tử được thực thi và rollback/commit phụ thuộc driver và transaction. |

## 11. Checklist kiểm thử tích hợp và câu hỏi ôn tập

Một bộ kiểm thử cho logic lưu dữ liệu nên có **ít nhất**:

1. Chèn dữ liệu hợp lệ, đọc lại đúng.
2. Chèn trùng `PRIMARY KEY`, trùng từng `UNIQUE`; kiểm tra kiểu Spring và SQLSTATE/vendor code theo DB đích.
3. Vi phạm `NOT NULL`, `FOREIGN KEY`, `CHECK`; kiểm tra không ghi sai dữ liệu.
4. Hai lệnh trong một transaction: lệnh đầu thành công, lệnh sau lỗi; xác minh rollback khiến **cả hai không tồn tại**.
5. Thử hai request đồng thời cùng unique key và xác nhận chỉ một bản ghi cuối cùng tồn tại.
6. Kiểm tra `ON CONFLICT`/upsert nếu có; kiểm tra record count và điều kiện không ghi đè.
7. Thử batch có một phần tử lỗi; xác minh chính sách rollback và dữ liệu thực tế.
8. Kiểm tra API mapping không làm lộ SQL, constraint hoặc thông tin cá nhân.

**Câu hỏi tự kiểm tra:**

- Tại sao bắt `DataIntegrityViolationException` trước `DuplicateKeyException` gây lỗi biên dịch?
- PostgreSQL `23505` có đủ để biết email hay id bị trùng không? Cần quan sát thêm gì?
- Vì sao `@Transactional` và một unique constraint tạo ra ranh giới lỗi mạnh hơn precheck `SELECT EXISTS`?
- Vì sao `23503` không nên được xử lý giống `23505`, dù cùng thuộc nhóm lỗi integrity?
- Khi nào `ON CONFLICT DO NOTHING` phù hợp, và khi nào nó có thể che khuất lỗi nghiệp vụ?
- Sau khi một lệnh lỗi trong PostgreSQL transaction, vì sao việc nuốt exception và chạy tiếp có thể dẫn tới `25P02`?

## Tài liệu tham khảo

- Spring Framework, *Using the JDBC Core Classes* (SQLExceptionTranslator): https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework, `DuplicateKeyException` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DuplicateKeyException.html
- Spring Framework, `DataIntegrityViolationException` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html
- Spring Framework, `SQLExceptionSubclassTranslator` và `SQLStateSQLExceptionTranslator`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/SQLExceptionSubclassTranslator.html
- Spring Framework source, `sql-error-codes.xml` (mappings vendor/SQLSTATE): https://github.com/spring-projects/spring-framework/blob/main/spring-jdbc/src/main/resources/org/springframework/jdbc/support/sql-error-codes.xml
- Spring Framework, *Rolling Back a Declarative Transaction*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- PostgreSQL, *Error Codes*: https://www.postgresql.org/docs/current/errcodes-appendix.html
- PostgreSQL, *INSERT* (`ON CONFLICT`): https://www.postgresql.org/docs/current/sql-insert.html
- PostgreSQL, *Constraints*: https://www.postgresql.org/docs/current/ddl-constraints.html
- Java SE, `BatchUpdateException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/BatchUpdateException.html
