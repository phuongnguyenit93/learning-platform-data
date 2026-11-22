# Đối chiếu dữ liệu bằng kết nối độc lập sau khi hoàn tất

## 1. Mục tiêu bài học

Trong Spring Framework, một phương thức có `@Transactional` có thể đọc được dữ liệu nó vừa ghi, dù transaction **chưa commit**. Vì thế, việc gọi lại `repository.findById(...)` hoặc `JdbcTemplate.queryForObject(...)` ngay bên trong phương thức đó chưa chứng minh dữ liệu đã được commit và có thể nhìn thấy từ một kết nối khác.

Bài này hướng dẫn cách **đối chiếu trạng thái database bằng kết nối JDBC độc lập, sau khi ranh giới transaction thực sự hoàn tất**. Sau bài học, bạn có thể:

- Phân biệt dữ liệu đang nằm trong transaction với dữ liệu đã commit.
- Xác định đúng thời điểm Spring hoàn tất commit/rollback khi gọi `@Transactional` qua proxy.
- Đọc lại dữ liệu bằng một kết nối JDBC mới không tham gia transaction của bên ghi.
- Kiểm chứng hai kết quả: commit thành công thì dữ liệu mới được nhìn thấy; rollback thì dữ liệu mới không còn.
- Viết integration test tránh nhầm lẫn giữa transaction của application và transaction do framework test quản lý.
- Nhận diện các nguyên nhân khiến kiểm chứng sai: truy vấn trong cùng transaction, self-invocation, outer transaction chưa kết thúc, mức cô lập, replica lag, sai schema hoặc cache.

**Phạm vi:** Ví dụ tập trung vào transaction JDBC đồng bộ, một database, Spring Boot/Spring JDBC và H2. Các nguyên tắc về ranh giới commit cũng hữu ích khi dùng JPA, nhưng với JPA cần chú ý thêm `flush` và persistence context.

## 2. Vì sao đọc lại ngay trong phương thức chưa đủ?

Giả sử một phương thức được Spring quản lý transaction:

```java
@Transactional
public void save(long id) {
    jdbcTemplate.update(
        "INSERT INTO ledger_entry(id, description) VALUES (?, ?)",
        id, "new-value");

    // Đoạn này đọc trong cùng transaction.
    String value = jdbcTemplate.queryForObject(
        "SELECT description FROM ledger_entry WHERE id = ?",
        String.class, id);
}
```

Đây là **đoạn minh họa**, không phải một chương trình độc lập. `JdbcTemplate` thường dùng JDBC connection đã gắn với transaction của thread hiện tại. Connection này có quyền **read your own writes**: nó nhìn thấy thay đổi của chính mình trước `COMMIT`. Vì thế, kết quả `"new-value"` ở đây chỉ cho biết câu lệnh INSERT đang có hiệu lực trong transaction hiện hành; chưa chứng minh connection khác nhìn thấy giá trị đó.

Với mức cô lập `READ_COMMITTED` thông thường:

| Thời điểm | Connection A đang ghi | Connection B độc lập |
| --- | --- | --- |
| A bắt đầu transaction | Không có dữ liệu mới | Không có dữ liệu mới |
| A INSERT nhưng chưa commit | A nhìn thấy bản ghi mới | B chưa nhìn thấy bản ghi mới |
| A commit thành công | Bản ghi đã được xác nhận | B mở truy vấn mới và thấy bản ghi |
| Nếu A rollback thay vì commit | Thay đổi của A bị hủy | B không thấy bản ghi do A vừa ghi |

Một transaction đọc độc lập đã mở **trước** thời điểm commit có thể tiếp tục thấy snapshot cũ dưới các mức cô lập như `REPEATABLE_READ` hoặc `SERIALIZABLE`. Để kiểm tra rõ ràng, hãy mở **kết nối/transaction đọc mới sau khi commit/rollback đã kết thúc**. Truy vấn nguồn dữ liệu chính (primary) cùng database, schema và tenant, thay vì một read replica có thể trễ.

## 3. "Sau khi hoàn tất" là thời điểm nào trong Spring?

Trong cơ chế declarative transaction thông thường, lời gọi phải đi qua Spring AOP proxy:

```text
Caller
  |
  | gọi bean proxy
  v
TransactionInterceptor
  |  mở/tham gia transaction
  v
@Transactional service method
  |  INSERT / UPDATE / DELETE
  |  return hoặc throw
  v
TransactionInterceptor
  |  COMMIT hoặc ROLLBACK khi sở hữu transaction vật lý
  v
Caller nhận kết quả hoặc exception
  |
  v
Mở một connection độc lập -> SELECT đối chiếu
```

Với trường hợp **không có outer transaction**, gọi đúng Spring proxy, transaction manager thực hiện commit/rollback trong interceptor trước khi caller nhận lại quyền điều khiển. Khi đó, có thể kiểm tra ngay sau khi lời gọi kết thúc:

```java
service.save(42L);        // Lời gọi qua Spring proxy; commit đã hoàn tất nếu trả về thành công.
verifyUsingNewConnection(); // Query độc lập ngoài transaction vừa hoàn tất.
```

Đây chỉ là ý tưởng tổ chức luồng gọi, chưa phải đoạn code độc lập.

Các ngoại lệ quan trọng:

1. Nếu service tham gia transaction ngoài bằng `Propagation.REQUIRED`, việc **inner method trả về không đồng nghĩa outer transaction đã commit**. Chỉ xác nhận sau khi boundary ngoài cùng kết thúc.
2. Gọi `this.save(...)` bên trong cùng bean có thể bỏ qua AOP proxy ở proxy mode; annotation `@Transactional` trên phương thức đích khi đó không được áp dụng như mong muốn.
3. Phương thức nghiệp vụ có thể chạy xong nhưng **commit thất bại** (ví dụ lỗi constraint khi flush/commit, timeout hoặc transaction bị đánh dấu rollback-only). Chỉ coi đã commit khi lời gọi qua proxy trả về thành công và transaction vật lý thực sự kết thúc; nếu có exception, điều tra kết quả trước khi kết luận.
4. Với reactive transaction, kết quả `Publisher` hoàn tất theo cơ chế khác; không dùng quy tắc thời điểm của phương thức JDBC đồng bộ để suy luận cho reactive pipeline.

## 4. Thiết kế phép đối chiếu đáng tin cậy

Quy trình cho một transaction JDBC đơn giản:

1. **Chuẩn bị trạng thái ban đầu** đã biết, ví dụ ID chưa tồn tại.
2. **Gọi service có `@Transactional` qua bean Spring**; trong service ghi bản ghi bằng `JdbcTemplate`.
3. Nếu muốn quan sát sự khác biệt **trước commit**, vẫn trong service hãy truy vấn bằng connection đang tham gia transaction và bằng một connection JDBC hoàn toàn khác; với `READ_COMMITTED`, connection hiện tại thấy thay đổi, connection khác chưa thấy.
4. Để service kết thúc; proxy commit nếu thành công hoặc rollback nếu exception thỏa rollback rule.
5. **Mở một connection độc lập mới sau khi bước 4 hoàn tất**, thực hiện `SELECT` bằng khóa/ID xác định; so sánh *cả sự tồn tại và giá trị cột* với kết quả mong đợi.
6. Đóng `ResultSet`, `PreparedStatement` và `Connection` bằng `try-with-resources`.
7. Với trường hợp lỗi, bắt exception **ở caller sau khi qua proxy** rồi đọc bằng connection độc lập để xác nhận dữ liệu không được commit.

Ở môi trường production, thường dùng connection pool của ứng dụng và truy vấn sau khi transaction đã kết thúc. Ví dụ dưới đây dùng `DriverManager.getConnection(...)` trực tiếp để **chứng minh rõ ràng** connection đối chiếu hoàn toàn độc lập với transaction-bound connection do Spring quản lý. Cách tạo connection trực tiếp này hợp lý cho bài thực hành; ở hệ thống thật cần cân nhắc pool, cấu hình SSL, credential, multi-tenancy và routing.

## 5. Ví dụ Spring Boot chạy được: nhìn thấy commit và không thấy rollback

Ứng dụng mẫu dùng Java 17+, Maven, Spring Boot 3.5.16, Spring JDBC và H2 in-memory. Nó chạy hai kịch bản:

- `save(1)` ghi id=1 và trở về bình thường: service thấy dữ liệu chưa commit; connection độc lập trước commit không thấy, sau commit thấy đúng giá trị.
- `saveAndFail(2)` ghi id=2 rồi ném `IllegalStateException`: service thấy thay đổi của mình, connection độc lập chưa thấy; sau rollback vẫn không thấy.

Cấu trúc:

```text
transaction-check/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── TransactionCheckApplication.java
    │   │   ├── WriteService.java
    │   │   └── IndependentReader.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── TransactionVisibilityTest.java
```

### 5.1. Maven dependencies

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>transaction-check</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. Cấu hình cùng một database cho cả hai connection

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:transaction_check;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
```

Dùng **H2 in-memory có tên** `transaction_check` để các connection trong cùng JVM cùng trỏ đến một database. `DB_CLOSE_DELAY=-1` giúp H2 không tự hủy database khi connection cuối đóng trong quá trình demo. Không dùng URL in-memory không tên (`jdbc:h2:mem:`), vì connection mới có thể gặp database khác.

### 5.3. Connection đọc độc lập

**`src/main/java/demo/IndependentReader.java`**

```java
package demo;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class IndependentReader {
    private final String jdbcUrl;
    private final String username;
    private final String password;

    public IndependentReader(
            @Value("${spring.datasource.url}") String jdbcUrl,
            @Value("${spring.datasource.username}") String username,
            @Value("${spring.datasource.password:}") String password) {
        this.jdbcUrl = jdbcUrl;
        this.username = username;
        this.password = password;
    }

    public Optional<String> findDescription(long id) {
        String sql = "SELECT description FROM ledger_entry WHERE id = ?";

        try (Connection connection =
                     DriverManager.getConnection(jdbcUrl, username, password);
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, id);
            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.of(rows.getString(1));
            }

        } catch (SQLException ex) {
            throw new IllegalStateException(
                    "Không thể đối chiếu dữ liệu", ex);
        }
    }
}
```

Điểm quan trọng:

- `DriverManager.getConnection(...)` tạo JDBC connection mới mà Spring không gắn vào transaction của `WriteService`. Nó không sử dụng `DataSourceUtils.getConnection(...)` hoặc `JdbcTemplate` vốn có thể tái sử dụng connection đã bind vào thread.
- URL/username/password lấy từ cùng cấu hình nên connection đọc trỏ đến **cùng database**, nhưng có **transaction scope riêng**. H2 ở đây dùng mặc định `READ_COMMITTED`, connection mới thường ở `autoCommit=true`; mỗi `SELECT` thấy trạng thái đã commit tại thời điểm truy vấn.
- `PreparedStatement` dùng tham số `?`, tránh nối ID trực tiếp vào SQL. `Optional.empty()` nghĩa là không có bản ghi; `Optional[value-1]` nghĩa là đọc được giá trị `value-1`.
- Sau mỗi lần đọc, `try-with-resources` đóng tài nguyên. Connection đọc này không commit hay rollback thay cho transaction ghi.

### 5.4. Service ghi qua transaction do Spring quản lý

**`src/main/java/demo/WriteService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WriteService {
    private final JdbcTemplate jdbc;
    private final IndependentReader independentReader;

    public WriteService(
            JdbcTemplate jdbc,
            IndependentReader independentReader) {
        this.jdbc = jdbc;
        this.independentReader = independentReader;
    }

    @Transactional
    public void save(long id) {
        insert(id);

        System.out.println(
                "Cùng transaction, id=" + id + ": " + readInCurrentTransaction(id));
        System.out.println(
                "Kết nối độc lập trước commit, id=" + id + ": "
                        + independentReader.findDescription(id));
    }

    @Transactional
    public void saveAndFail(long id) {
        insert(id);

        System.out.println(
                "Cùng transaction, id=" + id + ": " + readInCurrentTransaction(id));
        System.out.println(
                "Kết nối độc lập trước rollback, id=" + id + ": "
                        + independentReader.findDescription(id));

        throw new IllegalStateException("rollback có chủ đích");
    }

    private void insert(long id) {
        jdbc.update(
                "INSERT INTO ledger_entry(id, description) VALUES (?, ?)",
                id, "value-" + id);
    }

    private String readInCurrentTransaction(long id) {
        return jdbc.queryForObject(
                "SELECT description FROM ledger_entry WHERE id = ?",
                String.class, id);
    }
}
```

`@Transactional` mặc định dùng `Propagation.REQUIRED`. Nếu caller không có transaction ngoài, Spring mở transaction khi đi vào `save(...)` và commit khi phương thức trả về qua interceptor. `JdbcTemplate` bên trong service tham gia connection của transaction đang hoạt động.

Trong `saveAndFail(...)`, `IllegalStateException` là `RuntimeException`; quy tắc rollback mặc định xử lý nó khi exception thoát qua proxy. Lưu ý rằng **câu lệnh `throw` xảy ra sau hai câu lệnh SELECT**, vì vậy hai dòng in trước rollback vẫn mô tả trạng thái *chưa hoàn tất*.

### 5.5. Application tạo bảng và đối chiếu sau khi lời gọi kết thúc

**`src/main/java/demo/TransactionCheckApplication.java`**

```java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TransactionCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransactionCheckApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(
            JdbcTemplate jdbc,
            WriteService writeService,
            IndependentReader independentReader) {

        return args -> {
            jdbc.execute("""
                    CREATE TABLE ledger_entry (
                        id BIGINT PRIMARY KEY,
                        description VARCHAR(80) NOT NULL
                    )
                    """);

            // Không có outer transaction; gọi service qua Spring bean proxy.
            writeService.save(1L);
            System.out.println(
                    "Kết nối độc lập sau commit, id=1: "
                            + independentReader.findDescription(1L));

            try {
                writeService.saveAndFail(2L);
            } catch (IllegalStateException ex) {
                System.out.println("Bắt lỗi: " + ex.getMessage());
            }

            System.out.println(
                    "Kết nối độc lập sau rollback, id=2: "
                            + independentReader.findDescription(2L));
        };
    }
}
```

Ở đây `CommandLineRunner` không mang `@Transactional`, nên không tạo outer transaction bao quanh cả hai lời gọi. `writeService` được Spring inject là bean đi qua transaction proxy. Khi lệnh `writeService.save(1L)` trả quyền điều khiển cho runner mà không ném lỗi, interceptor đã xử lý commit. Tương tự, khi exception từ `saveAndFail(2L)` đến khối `catch`, interceptor đã xử lý rollback.

### 5.6. Chạy và kiểm tra đầu ra

Yêu cầu: JDK 17+ và Maven 3.6.3+. Trong thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Các dòng **do chương trình in ra**, không kể log khởi động của Spring:

```text
Cùng transaction, id=1: value-1
Kết nối độc lập trước commit, id=1: Optional.empty
Kết nối độc lập sau commit, id=1: Optional[value-1]
Cùng transaction, id=2: value-2
Kết nối độc lập trước rollback, id=2: Optional.empty
Bắt lỗi: rollback có chủ đích
Kết nối độc lập sau rollback, id=2: Optional.empty
```

**Giải thích từng mốc:**

| Mốc | Transaction ghi | Connection độc lập | Ý nghĩa |
| --- | --- | --- | --- |
| `save(1)` sau INSERT | Đọc được `value-1` | Chưa thấy id=1 | Cùng connection thấy dữ liệu chưa commit |
| `save(1)` trả về qua proxy | Commit thành công | Đọc được `value-1` | Dữ liệu đã có thể được kết nối mới đọc |
| `saveAndFail(2)` sau INSERT | Đọc được `value-2` | Chưa thấy id=2 | Dữ liệu vẫn chỉ nằm trong transaction ghi |
| Exception thoát khỏi proxy | Transaction rollback | Không thấy id=2 | Thay đổi chưa commit đã bị hủy |

Đây là phép đối chiếu **độc lập theo transaction** vì mỗi truy vấn của `IndependentReader` lấy một connection JDBC mới và phát câu SQL trực tiếp lên database, không dựa vào kết quả trả về từ service hay cache ORM.

## 6. Kiểm chứng tự động bằng integration test

Thêm file sau để kiểm tra commit/rollback mà không cần so console bằng mắt.

**`src/test/java/demo/TransactionVisibilityTest.java`**

```java
package demo;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class TransactionVisibilityTest {
    @Autowired
    private WriteService writeService;

    @Autowired
    private IndependentReader independentReader;

    @Test
    void committedDataIsVisibleThroughFreshConnection() {
        writeService.save(101L);

        assertEquals(
                Optional.of("value-101"),
                independentReader.findDescription(101L));
    }

    @Test
    void rolledBackDataIsNotVisibleThroughFreshConnection() {
        assertThrows(
                IllegalStateException.class,
                () -> writeService.saveAndFail(102L));

        assertEquals(
                Optional.empty(),
                independentReader.findDescription(102L));
    }
}
```

Chạy:

```bash
mvn test
```

Hai test trên sử dụng ID riêng (101 và 102), không đụng các ID 1 và 2 mà runner demo tạo khi application context khởi động. Cả hai test **không có `@Transactional` trên method/class**, nên service tự sở hữu ranh giới transaction của mình; mỗi phép đọc kiểm tra trạng thái sau khi lời gọi service đã kết thúc. Kỳ vọng: cả hai test đều pass.

Nếu muốn xác minh thêm việc lưu **đúng nội dung** thay vì chỉ xác minh hàng tồn tại, so sánh trực tiếp `Optional.of("value-101")` như ví dụ; còn khi kiểm tra các cột khác, có thể trả một DTO/record chứa nhiều giá trị và so khớp toàn bộ trường quan trọng.

### Vì sao `@Transactional` trên test có thể làm phép kiểm chứng sai?

Ví dụ sau là **anti-pattern minh họa**:

```java
@SpringBootTest
@Transactional
class TransactionalTestExample {
    @Autowired WriteService writeService;
    @Autowired IndependentReader independentReader;

    @Test
    void misleadingCheck() {
        writeService.save(201L);

        // Connection mới có thể chưa thấy id=201 vì test transaction
        // vẫn đang hoạt động và chưa commit.
        assertEquals(
                Optional.of("value-201"),
                independentReader.findDescription(201L));
    }
}
```

Code trên chưa gồm import và không phải ví dụ test được khuyến nghị. Mặc định Spring TestContext mở **test-managed transaction** khi test được đánh dấu `@Transactional`, rồi rollback transaction đó sau test. Lời gọi service `Propagation.REQUIRED` tham gia transaction test đang hoạt động. Vì vậy, service trả về **không commit**; connection độc lập sẽ không thấy id=201 trong khi test transaction còn mở dưới `READ_COMMITTED`.

Có ba cách kiểm chứng đúng:

1. **Ưu tiên** test không gắn `@Transactional` khi muốn quan sát trạng thái sau commit của service; đây là cách dùng trong `TransactionVisibilityTest`.
2. Nếu test bắt buộc nằm trong test-managed transaction, có thể sử dụng `TestTransaction.flagForCommit()` rồi `TestTransaction.end()` để kết thúc và commit transaction của test, **sau đó** mới mở connection độc lập đối chiếu. Việc này ghi dữ liệu thật vào database kiểm thử và cần dọn dẹp/isolating phù hợp.
3. Với Spring TestContext, `@AfterTransaction` có thể kiểm tra trạng thái sau khi test transaction kết thúc; nếu test được cấu hình rollback mặc định, kết quả đúng phải phản ánh **rollback**, không phải commit. `@Commit`/`@Rollback(false)` là lựa chọn có chủ đích khi cần commit test transaction.

Ví dụ **đoạn method bổ sung trong lớp test hỗ trợ Spring TestContext**, chỉ chạy trên database thử nghiệm:

```java
@Test
@Transactional
void verifyAfterTestManagedCommit() {
    writeService.save(301L);

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertEquals(
            Optional.of("value-301"),
            independentReader.findDescription(301L));
}
```

Cần import `org.springframework.transaction.annotation.Transactional` và `org.springframework.test.context.transaction.TestTransaction` cùng các thành phần test ở trên. `TestTransaction.end()` kết thúc transaction do test quản lý; không dùng cách này tùy tiện trong test cần đảm bảo dọn sạch dữ liệu sau mỗi lượt chạy.

## 7. Khi nào phép đối chiếu được xem là đúng?

Một đối chiếu thành công cần đồng thời xác minh các điều kiện sau:

| Yếu tố | Kiểm tra cần thực hiện |
| --- | --- |
| Ranh giới ghi | Caller đã ra khỏi **transaction vật lý ngoài cùng**, không còn outer/test transaction đang chờ commit |
| Ranh giới đọc | Connection đọc mới, không cùng transaction/persistence context của bên ghi |
| Nguồn dữ liệu | Cùng primary database, đúng schema/catalog/tenant; không đọc nhầm H2 memory DB hoặc replica trễ |
| Thời điểm | SELECT bắt đầu **sau** khi commit hoặc rollback được xác nhận; không truy vấn trong snapshot cũ |
| Isolation | Hiểu `READ_COMMITTED`/`REPEATABLE_READ`; tránh kết luận sai từ dirty read hoặc snapshot cũ |
| Dữ liệu so sánh | Dùng ID duy nhất/correlation key, kiểm tra trường dữ liệu và giá trị mong đợi thay vì chỉ kiểm tra method không ném lỗi |
| Lỗi | Khi transaction thất bại, kỳ vọng bản ghi mới không tồn tại; kiểm tra exception và dữ liệu cùng nhau |
| Tài nguyên | Đóng connection/statement/result set, tránh rò rỉ connection hoặc giữ transaction đọc quá lâu |

**Không cần mở một database khác.** Kết nối "độc lập" có nghĩa transaction và JDBC connection độc lập nhưng đọc **cùng dữ liệu đích**. Nếu dùng một database khác, kết quả không chứng minh commit của transaction ban đầu.

Trong ví dụ H2, mỗi lần `findDescription` chạy, `DriverManager` mở connection mới rồi đóng ngay. Ở production, có thể lấy connection từ `DataSource`/pool **sau khi transaction ghi thật sự kết thúc**; điều quan trọng là connection đọc không bị ràng buộc vào transaction ghi đang hoạt động. `DataSourceUtils.getConnection` trong cùng thread khi transaction đang chạy có thể trả chính connection đã bind, vì vậy không dùng nó làm bằng chứng về kết nối độc lập trước commit.

## 8. Những tình huống làm kết quả dễ gây hiểu nhầm

### 8.1. Inner service đã trả về, outer vẫn còn transaction

```text
@Transactional outer()
  ├── writeService.save(42)   // REQUIRED tham gia outer
  ├── save() trả về           // CHƯA có commit vật lý
  ├── independent SELECT      // thường chưa thấy thay đổi
  └── outer() trả về          // proxy ngoài cùng mới commit
```

Cách sửa: gọi đối chiếu sau khi **outermost proxy invocation** kết thúc; hoặc dùng API callback đúng phase khi cần hook. Đừng nhầm thời điểm Java method trả về với thời điểm transaction vật lý kết thúc.

### 8.2. Kiểm tra bằng cùng `JdbcTemplate` trong service

Câu truy vấn này có thể tái dùng transaction-bound connection, nhìn thấy uncommitted writes. Đó là phép kiểm tra **logic đang chạy trong transaction**, không phải bằng chứng dữ liệu đã commit. Hãy chuyển đọc đối chiếu sang caller sau boundary, với connection độc lập.

### 8.3. Connection độc lập được mở sớm và giữ snapshot cũ

Ở `REPEATABLE_READ`, một transaction đọc dài có thể tiếp tục thấy snapshot trước commit, ngay cả khi writer đã commit sau đó. Hãy kết thúc transaction đọc cũ và bắt đầu một transaction/connection đọc mới; hiểu rõ isolation và MVCC của database sử dụng.

### 8.4. Đọc từ read replica

Replica có thể áp dụng thay đổi trễ hơn primary. Kết quả "chưa thấy" sau commit tại replica không đồng nghĩa primary rollback. Nếu mục tiêu là xác minh commit ngay lập tức, đối chiếu từ primary hoặc dùng cơ chế consistency/read-after-write của hệ thống.

### 8.5. Đọc từ JPA persistence context/cache

`EntityManager.find()` có thể trả về entity đã có trong first-level cache mà không phát SQL mới; `flush()` chỉ đồng bộ SQL xuống database trong transaction, **không tương đương commit**. Để kiểm chứng trạng thái commit, đọc qua transaction và persistence context độc lập sau hoàn tất; khi cần, xác minh SQL thật tới database.

### 8.6. Database có trigger, default, generated value

Giá trị bền vững có thể khác object Java trước khi commit (ví dụ DB default, trigger hoặc generated column). Đối chiếu phải SELECT lại **giá trị thực** và xác định các cột quan trọng, thay vì giả định object trả về từ save đã phản ánh toàn bộ dữ liệu cuối.

### 8.7. Commit báo lỗi hoặc trạng thái không chắc chắn

Không được kết luận "đã rollback" chỉ vì caller nhận exception trong mọi trường hợp; lỗi mạng tại thời điểm commit có thể khiến ứng dụng **không chắc** database đã commit hay chưa. Với hệ thống quan trọng, cần ID nghiệp vụ/idempotency key, truy vấn đối chiếu từ nguồn chính và quy trình xử lý kết quả bất định. Trong bài demo, exception chủ động ném *trước commit* và Spring rollback theo quy tắc, nên kết quả xác định.

### 8.8. Kiểm chứng quá sớm trong callback

`TransactionSynchronization.afterCompletion(...)` hoặc `@TransactionalEventListener(phase = AFTER_COMMIT)` có thể dùng cho công việc sau transaction, nhưng một số resource có thể còn bound cho đến khi Spring dọn dẹp xong. Không dùng lại connection/persistence context cũ trong callback để tuyên bố đã đối chiếu độc lập. Khi cần ghi thêm transaction mới từ callback, thường phải mở boundary `REQUIRES_NEW`; không mặc định rằng thao tác DB trong callback sẽ được commit riêng.

### 8.9. Kiểm chứng bằng số lượng hàng chung

`SELECT COUNT(*) FROM ledger_entry` có thể tăng/giảm vì transaction khác. Dùng ID/correlation key chỉ thuộc thao tác cần kiểm tra, thêm điều kiện tenant/schema và so sánh từng trường quan trọng. Nếu kiểm tra dưới tải đồng thời, cần thiết kế tránh race với các transaction khác có thể sửa cùng bản ghi.

## 9. Quy trình gỡ lỗi khi kết quả không như mong đợi

Nếu connection độc lập **đã thấy bản ghi trước commit**, hãy kiểm tra:

- Có thật `@Transactional` được áp dụng qua Spring proxy không? Có đang self-invocation hoặc cấu hình thiếu transaction manager?
- JDBC connection của lệnh INSERT có bật `autoCommit` ngoài ý muốn không?
- Connection "độc lập" có thực sự khác connection đang bind không, hay do `JdbcTemplate`/`DataSourceUtils` tham gia cùng transaction?
- Isolation có phải `READ_UNCOMMITTED`/dirty read không? Driver/database có hành vi đặc biệt không?
- Bản ghi có tồn tại từ lượt chạy trước không? Đã dùng ID riêng và reset dữ liệu đúng chưa?

Nếu **sau commit vẫn không thấy bản ghi**, hãy kiểm tra:

- Inner service chỉ mới kết thúc, còn outer transaction/test-managed transaction chưa commit?
- Lệnh INSERT thực sự chạy và có lỗi commit/constraint/rollback-only sau khi method kết thúc?
- URL, schema, username, tenant hoặc datasource routing của reader có đúng primary DB không?
- Reader có giữ snapshot từ trước commit, hoặc đang đọc replica/caching không?
- Có transaction đồng thời xóa/cập nhật lại bản ghi không?

Nếu **sau rollback vẫn thấy bản ghi**, hãy kiểm tra:

- ID đó đã tồn tại trước transaction hay do transaction khác commit?
- Ngoại lệ có thoát ra qua interceptor không, hay bị bắt/nuốt ngay trong method?
- Có dùng checked exception không được cấu hình `rollbackFor`? Mặc định `@Transactional` rollback với `RuntimeException` và `Error`.
- Một phần công việc có chạy trong `REQUIRES_NEW` hoặc connection tự commit riêng không? Những thay đổi đã commit độc lập không bị outer rollback hủy.

Có thể bật log ở môi trường thực hành:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Các log transaction giúp quan sát bắt đầu, tham gia, commit và rollback. Nhưng log không thay thế bằng chứng SQL được thực thi **qua connection độc lập sau hoàn tất**.

## 10. Bài tập áp dụng

**Bài 1 — Commit:** Thay `writeService.save(1L)` thành `save(10L)` và đổi đối chiếu sau commit thành id=10. Dự đoán ba kết quả cho cùng transaction, độc lập trước commit và độc lập sau commit.

**Đáp án:** lần lượt là `value-10`, `Optional.empty` và `Optional[value-10]`, trong cùng điều kiện H2 `READ_COMMITTED`.

**Bài 2 — Rollback:** Bỏ dòng `throw new IllegalStateException(...)` trong `saveAndFail` và giữ caller như cũ. Dự đoán kết quả truy vấn sau khi lời gọi trở về.

**Đáp án:** phương thức kết thúc bình thường, transaction commit; vì vậy connection độc lập sau lời gọi sẽ đọc được `Optional[value-2]`. Khối `catch` không chạy.

**Bài 3 — Test transaction:** Thêm `@Transactional` vào test `committedDataIsVisibleThroughFreshConnection`. Vì sao assertion có thể không còn đúng?

**Đáp án:** service `REQUIRED` tham gia transaction do test giữ; sau khi service trả về, transaction test chưa commit. Connection độc lập chưa thấy thay đổi. TestContext mặc định rollback test transaction cuối test.

**Bài 4 — Snapshot:** Connection đọc B mở transaction `REPEATABLE_READ` và thực hiện SELECT trước khi A commit. Sau khi A commit, B có chắc thấy dữ liệu ngay trên cùng transaction đọc không?

**Đáp án:** không. B có thể tiếp tục đọc snapshot cũ; cần kết thúc transaction đọc và bắt đầu phép đọc mới theo isolation/database thực tế.

**Bài 5 — Trường hợp thực tế:** Sau khi service commit, bạn đối chiếu bằng read replica nhưng chưa thấy dữ liệu. Có thể kết luận Spring rollback không?

**Đáp án:** không. Replica có thể chậm đồng bộ; kiểm tra primary cùng ID, schema và tenant trước khi kết luận về kết quả commit.

## 11. Những điều cần ghi nhớ

- **Đọc được trong transaction không chứng minh đã commit.** Kết nối ghi có thể nhìn thấy chính các thay đổi chưa commit.
- **Thời điểm đối chiếu phải sau transaction vật lý ngoài cùng đã hoàn tất.** Inner `REQUIRED` trả về chưa đủ nếu outer còn hoạt động.
- **Dùng một kết nối/transaction đọc độc lập, bắt đầu sau commit hoặc rollback**, nhắm tới cùng primary database và đúng phạm vi dữ liệu.
- **Commit:** đối chiếu được bản ghi cùng giá trị mong đợi. **Rollback:** không có những thay đổi mới do transaction thất bại tạo ra.
- **Test `@Transactional` mặc định rollback** và có thể làm sai phép đối chiếu trạng thái sau service; test nên xác định ranh giới hoàn tất rõ ràng.
- **Đối chiếu nên dựa trên ID và giá trị thực, không chỉ lời gọi method thành công hoặc một `SELECT` trong cùng connection.**

## 12. Tài liệu tham khảo

- Spring Framework — Cách declarative transaction hoạt động qua proxy: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — `@Transactional` settings, propagation và rollback defaults: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — JDBC connection và transaction-aware resource access: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — TestContext transactions, rollback mặc định và `TestTransaction`: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- H2 Database — Reference documentation (JDBC connection, isolation, in-memory DB): https://h2database.com/html/features.html