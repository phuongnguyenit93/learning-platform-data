# TransactionAwareDataSourceProxy cho mã JDBC cần thích nghi

## 1. Vấn đề thực tế và mục tiêu

Khi đưa một thư viện JDBC cũ hoặc một DAO thuần Java vào ứng dụng Spring Framework, bạn có thể gặp đoạn mã hoàn toàn không biết Spring:

```java
// Ví dụ trong một method của DAO cũ; dataSource đã được truyền vào.
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
    statement.setInt(1, delta);
    statement.setLong(2, accountId);
    statement.executeUpdate();
}
```

DAO này tự gọi `DataSource.getConnection()` và `Connection.close()` theo JDBC chuẩn. Trong khi đó, service Spring lại muốn gộp nhiều lời gọi DAO vào **một transaction**. Nếu truyền trực tiếp một `DataSource` thông thường vào DAO, lời gọi `getConnection()` có thể trả về connection mới, độc lập với connection Spring đã gắn cho transaction hiện tại. Thao tác trong DAO có thể tự commit và không rollback cùng service. Vấn đề không nằm ở cú pháp `UPDATE` mà ở **cách lấy và giải phóng connection**.

`TransactionAwareDataSourceProxy`, trong package `org.springframework.jdbc.datasource`, là lớp adapter cho tình huống ấy: nó thực thi interface JDBC chuẩn `javax.sql.DataSource`, nhưng làm cho những lời gọi JDBC trực tiếp qua proxy **tham gia transaction do Spring quản lý**, khi transaction tương ứng đang hoạt động.

Sau bài này, bạn cần:

1. Giải thích khi nào cần `TransactionAwareDataSourceProxy` và khi nào không.
2. Vẽ đúng hai đường: transaction manager dùng **target DataSource**, mã JDBC cần tương thích dùng **transaction-aware proxy**.
3. Hiểu cách proxy lấy connection, xử lý `close()` và áp dụng timeout cho JDBC `Statement`.
4. Tạo ứng dụng Java 17+ chạy được, chứng minh rollback vẫn có hiệu lực dù DAO gọi `getConnection()`/`close()` chuẩn.
5. Nhận ra giới hạn: proxy không tự mở transaction, không sửa được DAO chủ động `commit()` và không tự truyền transaction sang thread khác.
6. Phân biệt proxy này với `DataSourceUtils`, `JdbcTemplate` và `LazyConnectionDataSourceProxy`.

**Phạm vi:** tích hợp mã JDBC cần thích nghi vào Spring transaction. Bài không thay thế kiến thức quản lý transaction, connection pool hay SQL isolation, nhưng dùng các khái niệm đó để giải thích đúng cơ chế.

## 2. Điều gì xảy ra nếu không có proxy?

Trong Spring JDBC, `DataSourceTransactionManager` hoặc `JdbcTransactionManager` thường quản lý một `DataSource` cụ thể. Khi bắt đầu transaction, Spring lấy connection từ nguồn ấy, cấu hình transaction và gắn một `ConnectionHolder` vào ngữ cảnh transaction của luồng hiện tại. Các API như `JdbcTemplate` và `DataSourceUtils.getConnection(targetDataSource)` biết cách tìm connection đã được ràng buộc với luồng.

Mã JDBC thuần chỉ dùng:

```java
Connection connection = targetDataSource.getConnection();
```

không tự động gọi `DataSourceUtils`. Với implementation trả connection mới mỗi lần (ví dụ `DriverManagerDataSource`), connection này có thể nằm ngoài transaction hiện có; với pool, nó có thể mượn một connection khác từ pool. Nếu DAO thực hiện một câu ghi rồi đóng connection, kết quả có thể đã commit độc lập trong chế độ auto-commit.

Ví dụ luồng chuyển số dư:

```text
Spring service bắt đầu transaction T1
  ├─ DAO cũ: trừ tài khoản A qua targetDataSource.getConnection()
  │     └─ Connection C2, nằm ngoài T1, có thể auto-commit
  ├─ DAO cũ: cộng tài khoản B gặp lỗi
  └─ Spring rollback T1
       └─ Không thể rollback thay đổi đã commit trên C2
```

Không nên kết luận rằng mọi `getConnection()` ngoài Spring đều chắc chắn auto-commit: đó là hành vi phụ thuộc `DataSource`, driver, container và cấu hình. Điều quan trọng là **không có bảo đảm tham gia connection gắn với transaction của Spring** chỉ bằng việc gọi API JDBC thường trên target.

## 3. TransactionAwareDataSourceProxy hoạt động như thế nào?

`TransactionAwareDataSourceProxy` bao lấy một `DataSource` khác, gọi là **target DataSource**. Nó trả về một JDBC `Connection` proxy khi mã gọi `getConnection()`. Connection proxy đó phối hợp với `DataSourceUtils`:

- Trong một Spring transaction đang hoạt động và được đồng bộ trên cùng target, nó tìm và dùng connection đã gắn với transaction.
- Khi DAO gọi `close()` trên connection proxy, Spring xử lý giải phóng qua `DataSourceUtils.releaseConnection(...)`. Connection thuộc transaction đang hoạt động **không bị đóng vật lý sớm**; transaction manager hoàn tất việc commit/rollback rồi mới giải phóng.
- Ngoài transaction, thao tác lấy và giải phóng connection trở về hành vi truy cập JDBC thông thường của target (đóng vật lý hoặc trả về pool, tùy implementation).
- Các JDBC `Statement`, `PreparedStatement` và `CallableStatement` tạo qua connection proxy có thể nhận **thời gian còn lại của Spring transaction timeout** theo cơ chế Spring hỗ trợ.
- Connection trả về là **wrapped handle**, không mặc định chính là object connection native. `Connection.unwrap(...)` hoặc interface `ConnectionProxy` giúp truy cập connection đích khi thật sự cần, nhưng truy cập trực tiếp native connection có thể bỏ qua ý nghĩa của proxy.

Minh họa đúng:

```text
                  Spring-managed transaction T1
                               │
                 (transaction manager)
                               │
                               ▼
                    target DataSource ◄─────────────── JdbcTemplate
                               ▲                        (đã biết DataSourceUtils)
                               │
             TransactionAwareDataSourceProxy
                               ▲
                               │ getConnection(), close()
                       LegacyJdbcDao
                               ▲
                               │
                         Spring service
```

Spring transaction synchronization gắn với ngữ cảnh thực thi tương ứng (thường là thread-bound trong transaction JDBC đồng bộ). Proxy **không tạo transaction**, **không biến một JDBC driver thành XA/JTA**, và **không bảo đảm truyền ngữ cảnh transaction sang `@Async`, `CompletableFuture` hoặc luồng khác**. Để nhiều tài nguyên độc lập cùng commit nguyên tử phải có giải pháp transaction tương ứng; riêng proxy không đủ.

### Chính xác về hai lớp proxy

`TransactionAwareDataSourceProxy` không phải là connection pool. Bạn có thể dùng nó bao `HikariDataSource` hoặc implementation khác. Hãy phân biệt:

- **DataSource proxy:** object dùng chung trong application context, tương thích interface `DataSource`.
- **Connection proxy:** handle trả về cho mã JDBC legacy; nó định tuyến thao tác tới connection phù hợp với ngữ cảnh transaction.
- **Physical JDBC connection:** socket/session thật do driver/pool quản lý. Đóng handle không đồng nghĩa luôn đóng physical connection.

Trong Spring Framework 6.1.2+ có tùy chọn `setLazyTransactionalConnections(boolean)`, mặc định `true`: việc gọi `getConnection()` trên proxy không nhất thiết lập tức mở physical connection; có thể trì hoãn đến thao tác thực tế. Tùy chọn `setReobtainTransactionalConnections(boolean)` mặc định `false` và chỉ nên điều chỉnh khi hiểu kỹ hành vi transaction/container liên quan. Không tự bật các cờ này theo suy đoán.

## 4. Wiring bắt buộc: target cho transaction manager, proxy cho DAO cũ

Thường cần **hai bean có vai trò khác nhau nhưng cùng một target**:

```java
@Configuration
public class JdbcConfiguration {
    @Bean("targetDataSource")
    public DataSource targetDataSource() {
        // Tạo hoặc lấy implementation thật: pool, JNDI, ...
        return createConfiguredDataSource();
    }

    @Bean("legacyDataSource")
    public DataSource legacyDataSource(
            @Qualifier("targetDataSource") DataSource target) {
        return new TransactionAwareDataSourceProxy(target);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            @Qualifier("targetDataSource") DataSource target) {
        return new DataSourceTransactionManager(target);
    }
}
```

Đây là **snippet minh họa**, vì `createConfiguredDataSource()` đại diện cho factory thực tế và phải được thay bằng implementation phù hợp; phần 6 cung cấp project chạy độc lập.

Sơ đồ dependency cần giữ:

```text
targetDataSource: Hikari / DriverManager / JNDI DataSource
 ├─► DataSourceTransactionManager(targetDataSource)
 ├─► JdbcTemplate(targetDataSource)
 └─► TransactionAwareDataSourceProxy(targetDataSource)
         └─► LegacyJdbcDao(legacyDataSource)
```

**Quy tắc quan trọng:** transaction manager quản lý **target**, không dùng bean transaction-aware proxy làm datasource cấu hình chính. Ở một số phiên bản, `DataSourceTransactionManager` có thể tự unwrap nếu vô tình nhận `TransactionAwareDataSourceProxy`; đó là hành vi bảo vệ, không phải mô hình nên dựa vào. `JdbcTemplate` tự hỗ trợ Spring transaction nên nên dùng target trực tiếp, tránh quấn proxy không cần thiết.

Khi có nhiều bean cùng kiểu `DataSource`, inject bằng `@Qualifier("targetDataSource")` và `@Qualifier("legacyDataSource")`, hoặc đặt tên chính xác theo cấu hình. Nếu chỉ inject trần `DataSource`, Spring có thể không biết nên chọn bean nào (hoặc chọn bean `@Primary` ngoài ý muốn). Tên bean, kiểu bean và danh sách transaction manager phải được xác minh tại runtime.

### Kết hợp LazyConnectionDataSourceProxy

Nếu ứng dụng có `LazyConnectionDataSourceProxy`, thứ tự wrapper theo javadoc Spring là:

```text
Legacy DAO
    ↓
TransactionAwareDataSourceProxy      ← ngoài cùng
    ↓
LazyConnectionDataSourceProxy       ← tùy chọn
    ↓
Connection pool / target thật
    ↓
Database
```

Transaction manager khi đó cần quản lý cùng **`LazyConnectionDataSourceProxy`** mà transaction-aware proxy đang bao, để thống nhất khóa tài nguyên gắn với transaction. Đừng để transaction manager dùng một datasource khác so với target được Spring dùng để đồng bộ connection. `LazyConnectionDataSourceProxy` tối ưu thời điểm lấy connection; `TransactionAwareDataSourceProxy` giải bài toán tương thích với JDBC thuần. Chúng giải quyết hai vấn đề khác nhau.

## 5. Cách chọn giải pháp cho mã mới và mã cần tương thích

| Bạn có thể sửa mã không? | Cách phù hợp | Vì sao? |
| --- | --- | --- |
| Mã mới dùng Spring JDBC | `JdbcTemplate`, `NamedParameterJdbcTemplate` | Có quản lý connection, statement, exception và tham gia transaction sẵn |
| Mã JDBC mới nhưng cần dùng API `Connection` trực tiếp | `DataSourceUtils.getConnection(target)` và `releaseConnection(...)` trong `finally` | Rõ ràng dùng transaction synchronization của Spring |
| Thư viện/DAO cũ chỉ nhận `javax.sql.DataSource`, gọi `getConnection()` và `close()` | Truyền `TransactionAwareDataSourceProxy` | Không cần sửa contract JDBC trong mã cũ |
| Mã cũ tự gọi `commit()`, `rollback()`, đổi `autoCommit` không kiểm soát | Phân tích và sửa cách định nghĩa transaction trong mã cũ | Proxy không sửa được logic tự quản transaction tùy tiện |
| Ứng dụng reactive R2DBC | Reactive connection factory và reactive transaction manager | JDBC thread-bound proxy không thay cho transaction reactive |

Với mã mới, cách dùng trực tiếp Spring utilities (đoạn code trong một method, không phải chương trình độc lập):

```java
Connection connection = DataSourceUtils.getConnection(targetDataSource);
try {
    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT COUNT(*) FROM accounts")) {
        try (ResultSet result = statement.executeQuery()) {
            if (result.next()) {
                System.out.println(result.getInt(1));
            }
        }
    }
} finally {
    DataSourceUtils.releaseConnection(connection, targetDataSource);
}
```

Đừng sử dụng `connection.close()` trực tiếp trong đoạn dùng `DataSourceUtils` trên target mà bỏ qua `releaseConnection`: Spring cần biết connection có gắn transaction hay không. Với mã legacy nhận transaction-aware proxy, lời gọi `connection.close()` là đúng vì proxy đã xử lý giúp.

## 6. Ví dụ Java 17 chạy được: DAO legacy vẫn rollback cùng Spring

Ví dụ dùng **Spring Framework 6.2.14**, **H2 2.3.232** và Java 17+, minh họa quy tắc mà không cần Spring Boot hay cơ sở dữ liệu cài bên ngoài. `DriverManagerDataSource` chỉ phục vụ demo: nó **không pooling**. Trong production, thay bằng pool được quản lý đúng vòng đời.

### 6.1. Tạo project

```text
transaction-aware-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/TransactionAwareDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'transaction-aware-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.TransactionAwareDemo'
}
```

`src/main/java/demo/TransactionAwareDemo.java`:

```java
package demo;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.TransactionAwareDataSourceProxy;
import org.springframework.transaction.support.TransactionTemplate;

public class TransactionAwareDemo {

    @Configuration
    static class Config {
        // Target được transaction manager và JdbcTemplate sử dụng.
        @Bean("targetDataSource")
        DataSource targetDataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:txaware;DB_CLOSE_DELAY=-1", "sa", "");
        }

        // Proxy chỉ cấp cho DAO JDBC thuần cần tương thích.
        @Bean("legacyDataSource")
        DataSource legacyDataSource(
                @Qualifier("targetDataSource") DataSource target) {
            return new TransactionAwareDataSourceProxy(target);
        }

        @Bean
        JdbcTemplate jdbcTemplate(
                @Qualifier("targetDataSource") DataSource target) {
            return new JdbcTemplate(target);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                @Qualifier("targetDataSource") DataSource target) {
            return new TransactionTemplate(
                    new DataSourceTransactionManager(target));
        }

        @Bean
        LegacyAccountDao legacyAccountDao(
                @Qualifier("legacyDataSource") DataSource legacy) {
            return new LegacyAccountDao(legacy);
        }
    }

    // DAO chỉ biết API JDBC tiêu chuẩn, không import thư viện Spring.
    static class LegacyAccountDao {
        private final DataSource dataSource;

        LegacyAccountDao(DataSource dataSource) {
            this.dataSource = dataSource;
        }

        void addToBalance(long accountId, int delta) {
            String sql = """
                    UPDATE accounts
                    SET balance = balance + ?
                    WHERE id = ?
                    """;
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement statement =
                         connection.prepareStatement(sql)) {

                statement.setInt(1, delta);
                statement.setLong(2, accountId);
                int updated = statement.executeUpdate();
                if (updated != 1) {
                    throw new IllegalStateException(
                            "Account not found: " + accountId);
                }
            } catch (SQLException e) {
                throw new IllegalStateException("JDBC failed", e);
            }
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate tx = context.getBean(TransactionTemplate.class);
            LegacyAccountDao dao = context.getBean(LegacyAccountDao.class);

            jdbc.execute("""
                    CREATE TABLE accounts (
                        id BIGINT PRIMARY KEY,
                        balance INT NOT NULL CHECK (balance >= 0)
                    )
                    """);
            jdbc.update("INSERT INTO accounts VALUES (?, ?)", 1L, 100);
            jdbc.update("INSERT INTO accounts VALUES (?, ?)", 2L, 60);

            // Hai getConnection()/close() của DAO cùng tham gia T1.
            tx.executeWithoutResult(status -> {
                dao.addToBalance(1L, -25);
                dao.addToBalance(2L, 25);
            });
            System.out.println("after commit: " + balances(jdbc));

            // Lỗi phát ra khỏi callback => rollback lần giảm 10.
            try {
                tx.executeWithoutResult(status -> {
                    dao.addToBalance(1L, -10);
                    throw new IllegalStateException("simulate failure");
                });
            } catch (IllegalStateException expected) {
                // Chỉ bỏ qua lỗi cố ý tạo ra để minh họa rollback.
            }
            System.out.println("after rollback: " + balances(jdbc));
        }
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer first = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, 1L);
        Integer second = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, 2L);
        return first + "," + second;
    }
}
```

Trong thư mục dự án có Gradle, chạy:

```bash
gradle run
```

Nếu bạn có Gradle Wrapper: Linux/macOS dùng `./gradlew run`, Windows dùng `gradlew.bat run`. Hai dòng **do `System.out.println` tạo ra** là:

```text
after commit: 75,85
after rollback: 75,85
```

Log của Gradle hoặc framework có thể xuất hiện thêm. Giải thích số liệu:

- Ban đầu tài khoản 1 có 100, tài khoản 2 có 60.
- Transaction đầu gọi DAO hai lần: tài khoản 1 giảm 25 còn 75, tài khoản 2 tăng 25 thành 85; callback hoàn tất thì commit.
- Transaction thứ hai giảm tài khoản 1 thêm 10, rồi ném unchecked exception. `TransactionTemplate` rollback; kết quả vẫn là 75 và 85.
- DAO **không import Spring**, chỉ biết `DataSource`, `Connection`, `PreparedStatement` và `SQLException`. Lệnh `try-with-resources` đóng connection *proxy handle*, còn Spring giữ connection thật đến khi transaction kết thúc.
- Nếu đưa nhầm bean `targetDataSource` vào DAO dùng JDBC thuần, ví dụ với `DriverManagerDataSource` có thể sử dụng connection khác ngoài transaction; kiểm thử rollback sẽ lộ lỗi.

Đây là chương trình dùng transaction **theo cách lập trình** (`TransactionTemplate`) để tập trung quan sát hành vi của proxy. Trong ứng dụng thực tế, transaction cũng có thể được mở bởi `@Transactional` thông qua Spring AOP: cơ chế proxy JDBC bên trong vẫn như trên.

### 6.2. Với @Transactional thì thay đổi gì?

Ở service do Spring quản lý và có `@EnableTransactionManagement` hoặc cấu hình transaction tương ứng, bạn có thể viết:

```java
// Snippet minh họa, không phải phần bổ sung có thể copy nguyên
// vào chương trình độc lập ở trên; cần bean/service và imports.
@Service
public class TransferService {
    private final LegacyAccountDao dao;

    public TransferService(LegacyAccountDao dao) {
        this.dao = dao;
    }

    @Transactional
    public void transfer(long from, long to, int amount) {
        dao.addToBalance(from, -amount);
        dao.addToBalance(to, amount);
    }
}
```

Transaction interceptor phải thực sự chạy khi gọi bean, và cần transaction manager cấu hình với **target DataSource**. Trong proxy mode thường dùng, self-invocation (method gọi method khác có `@Transactional` bên trong cùng object) không qua proxy nên không nhận semantics bạn có thể mong đợi. Không nên kết luận “có annotation là có transaction” nếu chưa có integration test rollback qua Spring-managed service.

## 7. Phân tích chi tiết getConnection(), close() và transaction timeout

### 7.1. Khi đang có Spring transaction

1. Transaction manager tạo/gắn connection cho target DataSource vào transaction hiện hành.
2. DAO gọi `transactionAwareDataSource.getConnection()`; nó nhận JDBC connection handle có khả năng resolve connection transaction qua `DataSourceUtils`.
3. DAO tạo `PreparedStatement`, bind tham số và chạy SQL. SQL thực thi trên connection gắn với transaction.
4. DAO gọi `connection.close()`, thường do `try-with-resources`. Proxy release handle; connection transaction vẫn được Spring giữ.
5. Service kết thúc thành công thì manager commit; nếu lỗi phù hợp quy tắc rollback thì manager rollback, sau đó trả/đóng connection.

Điều này giải thích vì sao **DAO cũ có thể đóng connection sau mỗi method mà không phá transaction nhiều bước**. Tuy vậy, DAO cần tránh tự gọi `commit()`, `rollback()` hoặc can thiệp `autoCommit` tùy tiện; các thao tác như vậy có thể làm sai ranh giới Spring đang sở hữu. Proxy không biến cách quản lý transaction cũ không đúng thành an toàn.

### 7.2. Khi không có Spring transaction

Proxy không tự gọi `beginTransaction`, không chuyển mọi method thành transaction nguyên tử. Nó chỉ ủy nhiệm việc lấy/đóng connection theo hành vi thông thường của target. Với driver mặc định auto-commit, mỗi statement có thể commit riêng. Nếu muốn atomicity nhiều bước, phải tạo transaction bằng `TransactionTemplate`, `@Transactional` hoặc cơ chế phù hợp.

### 7.3. Timeout của transaction

Khi Spring transaction có timeout và mã JDBC legacy tạo `Statement` hoặc `PreparedStatement` qua connection proxy, Spring có thể áp dụng thời gian còn lại của transaction vào query timeout. Ví dụ:

```java
TransactionTemplate tx = new TransactionTemplate(
        new DataSourceTransactionManager(targetDataSource));
tx.setTimeout(5); // giây; chỉ có ý nghĩa khi dùng instance tx này
tx.executeWithoutResult(status -> legacyDao.runDatabaseOperation());
```

Đây là đoạn minh họa; `legacyDao.runDatabaseOperation()` đại diện cho API thực tế. Thời gian chờ lấy connection từ pool, thời gian đọc socket và timeout toàn bộ transaction **không phải cùng một giá trị**; driver và database có thể thực thi timeout khác nhau. Transaction timeout không tự hủy mọi công việc ngoài JDBC hoặc hoàn tác tác dụng phụ ngoài database.

## 8. Các giới hạn bắt buộc phải nhớ

| Trường hợp | Proxy có giúp không? | Ranh giới thực |
| --- | --- | --- |
| DAO dùng `dataSource.getConnection()` và `close()` chuẩn | Có, nếu đúng proxy, target và Spring transaction | Định tuyến sang connection giao dịch |
| DAO cần tham gia Spring transaction nhưng không import Spring | Có | Chỉ phải đổi DataSource được inject |
| Không có transaction hoạt động | Không tự tạo transaction | Theo hành vi mặc định của target |
| DAO tự gọi `commit()`/`rollback()` hoặc đổi `autoCommit` | Không bảo đảm an toàn | Phải điều chỉnh logic transaction của DAO |
| `@Transactional` trên method bị self-invocation | Không giải quyết | Proxy JDBC không sửa Spring AOP invocation |
| Async job trên thread khác | Không tự truyền ngữ cảnh | Thread-bound transaction cần thiết kế truyền/ngắt ranh giới rõ |
| Hai database, hai connection pool độc lập | Không biến thành distributed transaction | Cần transaction architecture phù hợp |
| Mã mới đã dùng `JdbcTemplate` | Không cần thiết | JdbcTemplate đã dùng DataSourceUtils |
| Reactive R2DBC và reactive transaction | Không áp dụng | JDBC proxy đồng bộ, không thay thế R2DBC |
| App bị thiếu connection, SQL chậm hay deadlock | Không tự chữa | Quan sát pool, SQL, locking và timeout |

**Không dùng proxy như công cụ xử lý mọi lỗi transaction.** Nếu thiết kế nghiệp vụ có hai database không tham gia cùng một transaction, nếu code chạm API bên ngoài hoặc tự commit, việc bao DataSource chỉ xử lý được phần lấy connection JDBC.

## 9. Lỗi cấu hình hay gặp và cách chẩn đoán

### 9.1. Proxy và transaction manager trỏ sai target

**Triệu chứng:** hai DAO có thể chạy SQL bình thường nhưng rollback không đồng bộ.

**Kiểm tra:** xác nhận bean được Spring inject tại DAO, `JdbcTemplate` và transaction manager; kiểm tra kiểu/names `DataSource`, `@Qualifier`, pool, đối tượng target. Nếu tạo một target/pool mới cho mỗi nơi, connection binding sẽ không đồng nhất.

### 9.2. Bean DataSource mơ hồ

**Triệu chứng:** `NoUniqueBeanDefinitionException` vì cả target và transaction-aware proxy đều implement `DataSource`.

**Giải pháp:** đặt tên rõ, dùng qualifier tại các điểm inject; không mặc định rằng `@Primary` ngẫu nhiên sẽ chọn đúng bean. Với Spring Boot, kiểm tra cả auto-configuration và các bean do ứng dụng tự tạo để tránh xung đột.

### 9.3. DAO nhận target thay vì proxy

**Triệu chứng:** DAO vẫn chạy được, nhưng không rollback cùng transaction trong demo. Đây là lỗi nguy hiểm vì test chỉ kiểm tra thành công có thể vẫn PASS.

**Giải pháp:** thử case cố tình ném exception *sau một lệnh UPDATE* và kiểm tra DB không đổi; assert đúng bean được cấp cho DAO.

### 9.4. DAO tự điều khiển transaction

**Triệu chứng:** có `commit()` hoặc `setAutoCommit(true)` trong DAO; hành vi không khớp ranh giới service.

**Giải pháp:** tìm và loại bỏ hoặc chuyển phần điều phối transaction lên service/transaction manager; giữ DAO chỉ quản lý tài nguyên JDBC theo hợp đồng đã thống nhất. Không trông chờ transaction-aware proxy chặn mọi thao tác của API `Connection`.

### 9.5. Connection được giữ quá lâu

**Triệu chứng:** pool cạn, timeout hoặc thao tác concurrent chờ đợi dù đã có proxy.

**Giải pháp:** luôn đóng handle theo scope; không giữ connection/statement ở field singleton hoặc vượt quá vòng đời callback. Không chạy HTTP call dài bên trong transaction nếu không cần; điều tra thời gian query, khóa và connection pool metrics.

### 9.6. Lỗi xảy ra sau khi chuyển thread

**Triệu chứng:** đoạn chạy qua `CompletableFuture` hoặc `@Async` dùng connection khác và không rollback cùng transaction gọi ban đầu.

**Giải pháp:** hiểu transaction JDBC đồng bộ được ràng buộc với execution context; xác lập transaction mới ở nơi chạy async khi phù hợp, hoặc thiết kế workflow phân tán. Proxy không tự truyền `ThreadLocal` sang thread khác.

### 9.7. Timeout không như mong đợi

**Triệu chứng:** query vẫn chạy quá lâu hoặc connection pool báo timeout khác với Spring transaction timeout.

**Giải pháp:** phân biệt timeout JDBC statement, timeout transaction, timeout lấy connection từ pool và network timeout. Quan sát cấu hình driver, transaction manager và SQL thực tế; ghi log có ngữ cảnh nhưng không lộ credential.

## 10. Khi nào nên bỏ adapter và chuyển sang Spring JDBC?

`TransactionAwareDataSourceProxy` phù hợp khi **phải giữ lại hợp đồng JDBC của mã có sẵn**; nó giúp tích hợp dần mà không buộc thay code của thư viện/DAO cũ. Tuy nhiên, mã mới thường nên chọn:

- `JdbcTemplate`: điều phối connection, statement, mapping, chuyển đổi ngoại lệ và tham gia transaction mà không cần transaction-aware proxy.
- `NamedParameterJdbcTemplate`: SQL có tham số tên, hữu ích cho nhiều giá trị.
- `DataSourceUtils`: khi vẫn cần dùng JDBC thủ công nhưng có thể viết code biết về Spring.
- `TransactionTemplate`/`@Transactional`: định nghĩa ranh giới transaction của **nghiệp vụ**, không giao cho một method CRUD đơn lẻ quyết định.

Ví dụ so sánh mục đích:

```java
// DAO cũ: cần DataSource proxy nếu muốn tham gia Spring transaction.
Connection c = legacyDataSource.getConnection();

// DAO mới: JdbcTemplate vốn tự dùng resource coordination của Spring.
jdbcTemplate.update("UPDATE accounts SET balance = ? WHERE id = ?",
        newBalance, id);
```

Đây là **hai đoạn minh họa trong ngữ cảnh đã có bean/biến tương ứng**; không phải file Java độc lập. Mã mới không cần tạo một `TransactionAwareDataSourceProxy` chỉ vì có `@Transactional`.

## 11. Bài tập thực hành và tiêu chí đạt

**Bài 1 — Chứng minh adapter hoạt động:** chạy project ở phần 6, xác minh hai dòng stdout. Chỉ đổi bean được inject vào `LegacyAccountDao` từ `legacyDataSource` sang `targetDataSource`, sau đó lặp lại case rollback. Với `DriverManagerDataSource` như demo, quan sát nguy cơ lệnh UPDATE của DAO commit độc lập. Sau đó khôi phục injection đúng. Đây là phép thử để hiểu, **không phải cấu hình production**.

**Bài 2 — Tách lớp có chủ đích:** thêm một `JdbcTemplate` repository cùng dùng `targetDataSource` và phối hợp một UPDATE từ DAO legacy với một UPDATE từ `JdbcTemplate` trong cùng `TransactionTemplate`. Cố tình ném exception rồi assert cả hai thao tác rollback. Bạn cần giải thích vì sao hai cách truy cập vẫn dùng cùng connection transaction.

**Bài 3 — Thay H2 demo bằng pool:** dùng HikariCP hoặc pool được hạ tầng quản lý thay `DriverManagerDataSource`. Vẫn chỉ có một target pool; transaction manager và JdbcTemplate dùng target, DAO cũ dùng wrapper ngoài cùng. Bổ sung integration test kiểm tra rollback và connection được trả pool.

**Bài 4 — Kiểm tra thread boundary:** từ một transaction, gọi tác vụ qua executor rồi dùng DAO cũ ở worker thread. Giải thích vì sao connection có thể khác, không mặc định cùng transaction. Thay vì cố chia sẻ một JDBC connection giữa nhiều thread, thiết kế lại ranh giới giao dịch hoặc cơ chế công việc.

**Bạn đạt yêu cầu khi có thể tự trả lời:**

1. `TransactionAwareDataSourceProxy` có tự bắt đầu transaction không? **Không.**
2. Transaction manager nên nhận target hay transaction-aware proxy? **Target.**
3. Vì sao DAO gọi `close()` nhưng transaction vẫn rollback được? **Vì đóng proxy handle được phối hợp qua DataSourceUtils; connection gốc trong transaction được giữ đến kết thúc.**
4. Có nên dùng proxy này cho mọi `JdbcTemplate`? **Không cần; JdbcTemplate đã hỗ trợ Spring transaction.**
5. Vì sao mã JDBC trực tiếp trên target có thể không rollback cùng Spring? **Vì getConnection() không mặc nhiên tìm connection đang được Spring bind.**
6. Có thể bọc `LazyConnectionDataSourceProxy` không? **Có, với TransactionAwareDataSourceProxy ngoài cùng và transaction manager quản lý cùng lazy target.**
7. Vì sao hai DataSource khác nhau hoặc hai thread không tự trở thành cùng một transaction? **Vì đồng bộ tài nguyên cần đúng đối tượng/ngữ cảnh và loại transaction phù hợp.**

## 12. Tài liệu tham khảo chính thống

- Spring Framework — Controlling Database Connections: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework 6.2 API — `TransactionAwareDataSourceProxy`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/datasource/TransactionAwareDataSourceProxy.html
- Spring Framework — Synchronizing Resources with Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html
- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework 6.2 API — `DataSourceUtils`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html

Tóm lại trong phạm vi cơ chế: **transaction manager giữ target DataSource; code JDBC legacy lấy transaction-aware proxy; Spring điều phối connection thật đến khi commit/rollback**. Đó là mục đích sử dụng thích hợp của adapter này.