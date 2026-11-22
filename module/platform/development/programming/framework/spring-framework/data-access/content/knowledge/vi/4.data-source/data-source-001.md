# DataSource là nguồn cung cấp Connection

> **Nguyên tắc cốt lõi:** Trong JDBC, `javax.sql.DataSource` là **nguồn cấp kết nối** (*connection factory*); `java.sql.Connection` là **đối tượng ứng dụng nhận được để thực hiện công việc với database**. Spring thường quản lý một bean `DataSource` dùng chung, trong khi các `Connection` được mượn và giải phóng theo mỗi công việc hoặc theo phạm vi giao dịch. Không đánh đồng một `DataSource` với một kết nối vật lý duy nhất.

Bài học giải thích hợp đồng `DataSource → Connection`, sự khác biệt giữa kết nối trực tiếp và connection pool, cách `JdbcTemplate` sử dụng nguồn kết nối, và các quy tắc lấy/trả connection trong giao dịch Spring.

## 1. Hiểu đúng vai trò của hai giao diện JDBC

Hai kiểu quan trọng của Java:

```java
import javax.sql.DataSource;
import java.sql.Connection;
```

`javax.sql.DataSource` thuộc chuẩn JDBC trong Java SE, kể cả khi chương trình sử dụng Spring Framework 6, Spring Boot 3 và các thư viện Jakarta khác. **Không có kiểu chuẩn `jakarta.sql.DataSource` thay thế nó.**

| Thành phần | Vai trò | Vòng đời thường gặp |
| --- | --- | --- |
| `DataSource` | Cấu hình/định tuyến đến nguồn DB và cung cấp `Connection` khi được yêu cầu | Bean dùng chung cho ứng dụng; có thể quản lý pool |
| `Connection` | Handle cho phiên làm việc JDBC: tạo statement, thiết lập transaction, `commit`/`rollback` | Mượn theo đơn vị công việc hoặc transaction, rồi trả/đóng |
| `PreparedStatement` | Gửi câu SQL có các tham số được bind qua một `Connection` | Dùng cho câu lệnh rồi đóng |
| `ResultSet` | Đọc các hàng kết quả do statement trả về | Dùng trong lúc duyệt rồi đóng |
| `JdbcTemplate` | API Spring JDBC dùng `DataSource` để thực thi SQL và quản lý nhiều resource | Thường inject thành bean dùng chung |

Luồng hoạt động:

```text
Ứng dụng / Repository / JdbcTemplate
                |
                | yêu cầu kết nối DB
                v
             DataSource
                |
                | getConnection()
                v
             Connection
                |
                +--> PreparedStatement --> SQL --> ResultSet
                |
                +--> commit / rollback nếu sở hữu transaction
                |
                +--> close / release
                       |
                       +--> có pool: thường trả connection cho pool
                       +--> không pool: thường đóng kết nối vật lý
```

`DataSource` không có API `executeQuery`. Muốn gửi SQL, ứng dụng cần dùng `Connection` và statement, hoặc sử dụng một lớp cao hơn như `JdbcTemplate` để Spring thực hiện phần đó.

### Hợp đồng `getConnection()`

```java
Connection connection = dataSource.getConnection();
```

Phương thức chuẩn `DataSource.getConnection()` trả một `Connection` và có thể ném `SQLException` nếu DB không thể truy cập, pool cạn hoặc cấu hình sai. Giao diện còn có biến thể `getConnection(String username, String password)`, nhưng trong Spring thông thường thông tin xác thực được đặt tại cấu hình `DataSource`, không truyền đi lặp lại trong mỗi DAO.

**Điều `getConnection()` không hứa:** mỗi lời gọi luôn tạo một socket hoặc database session vật lý mới. Nó có thể trả một handle đại diện cho kết nối đã được tái sử dụng từ pool. Việc tạo, giữ, kiểm tra và giải phóng kết nối phụ thuộc implementation.

## 2. Vì sao cần abstraction `DataSource`?

JDBC truyền thống có thể dùng `DriverManager`:

```java
import java.sql.Connection;
import java.sql.DriverManager;

Connection connection = DriverManager.getConnection(
    "jdbc:postgresql://localhost:5432/app",
    "app_user",
    "secret"
);
```

Đoạn trên chỉ minh họa cách lấy kết nối và **chưa đóng resource**. Nếu đặt URL, mật khẩu và `DriverManager.getConnection(...)` khắp các DAO, ứng dụng sẽ khó cấu hình theo môi trường, tối ưu connection pool, kiểm thử và quản lý transaction tập trung. Trong thực tế không hard-code mật khẩu vào mã nguồn.

Với `DataSource`, DAO chỉ phụ thuộc giao diện:

```java
import javax.sql.DataSource;

public final class CustomerDao {
    private final DataSource dataSource;

    public CustomerDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }
}
```

`CustomerDao` nhận nguồn kết nối qua constructor. Ai cung cấp `DataSource` có thể là Spring container, máy chủ ứng dụng/JNDI hay chương trình khởi tạo thủ công. DAO không cần biết cụ thể database dùng pool HikariCP, cơ chế kết nối trực tiếp hay JDBC driver nào, miễn implementation tuân thủ hợp đồng JDBC.

Các lợi ích:

1. **Tách cấu hình và nghiệp vụ:** code truy vấn không chứa chi tiết môi trường.
2. **Dùng lại pool:** nhiều request cùng truy cập qua một nguồn cấp kết nối, tránh mở socket mới không cần thiết.
3. **Tích hợp giao dịch Spring:** transaction manager có thể xác định `DataSource` nào cung cấp connection cho một giao dịch JDBC.
4. **Thay thế theo môi trường:** cùng DAO nhận data source cho H2 test, PostgreSQL staging hoặc production mà không sửa logic.
5. **Tăng khả năng kiểm soát:** tập trung giới hạn kết nối, timeout, metric, log và quản lý vòng đời.

**`DataSource` chỉ là abstraction.** Pooling, transaction-awareness, routing nhiều DB hay giám sát đều do các implementation, proxy hoặc thành phần hạ tầng liên quan đảm nhiệm.

## 3. Kết nối trực tiếp và connection pool

### 3.1. DataSource không dùng pool

`DriverManagerDataSource` và `SimpleDriverDataSource` của Spring cung cấp kết nối qua driver mà không có connection pool. Với kiểu này, mỗi lần mượn thường tạo một kết nối vật lý mới; `close()` đóng kết nối đó. Chúng tiện cho ví dụ hoặc test nhỏ, nhưng không phải lựa chọn mặc định tốt cho dịch vụ phục vụ nhiều request vì quá trình kết nối tới DB tốn thời gian và tài nguyên.

### 3.2. DataSource có pool

Với `spring-boot-starter-jdbc`, HikariCP thường được đưa vào dependency graph và được Spring Boot ưu tiên làm pool nếu không có cấu hình tùy chỉnh. Đối tượng thực tế có thể là `HikariDataSource`, nhưng DAO nên phụ thuộc kiểu `DataSource`.

Một pool quản lý **nhiều connection vật lý**. Khi mã gọi `getConnection()`, pool cho mượn một handle. Khi mã gọi `close()` trên handle, pool thường thu hồi handle để kết nối vật lý có thể được dùng cho tác vụ khác.

```text
  Spring context
      |
      v
DataSource (pool)
      |
      +--> Connection 1 ----> request A sử dụng ---> close() ---> pool
      |
      +--> Connection 2 ----> request B sử dụng ---> close() ---> pool
      |
      +--> Connection 3 ----> request C sử dụng ---> close() ---> pool
      |
      +--> Request D chờ nếu không còn connection sẵn có
```

**Tại sao `close()` vẫn bắt buộc khi có pool?** Vì `close()` nghĩa là trả lại quyền sử dụng handle. Nếu mã không trả, pool có thể cạn và các request mới bị chặn hoặc lỗi timeout. `Connection.close()` trên handle pooled không nhất thiết đóng kết nối vật lý.

Đừng lưu `Connection` thành trường dùng chung trong singleton `@Repository` rồi đưa cho nhiều luồng. Kết nối mang trạng thái riêng như `autoCommit`, isolation, transaction, session, và không nên được chia sẻ đồng thời giữa request. `DataSource` thường dùng chung; `Connection` được quản lý theo công việc/giao dịch.

| Sự kiện | `DataSource` | `Connection` |
| --- | --- | --- |
| Khởi động ứng dụng | Cấu hình bean; pool có thể khởi tạo connection sớm hoặc khi cần | Chưa chắc có một connection được ứng dụng mượn |
| Xử lý query | Cấp hoặc cho mượn handle | Thực thi SQL thông qua statement |
| Hoàn thành query | Tiếp tục phục vụ công việc khác | Được trả pool hoặc đóng tùy implementation |
| Shutdown | Container đóng pool theo vòng đời bean | Không để resource bị mượn mãi |

## 4. JDBC thuần: lấy Connection, sử dụng rồi đóng đúng cách

Đoạn sau là lớp Java 17+ có thể biên dịch bằng JDK. Đây là thành phần thư viện cần được cung cấp `DataSource` lúc chạy và cần bảng `notes(id, title)` trong database; **không phải chương trình có `main` độc lập**.

**`NoteReader.java`:**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class NoteReader {
    private final DataSource dataSource;

    public NoteReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findTitle(long id) throws SQLException {
        String sql = "SELECT title FROM notes WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet result = statement.executeQuery()) {
                return result.next()
                    ? Optional.ofNullable(result.getString("title"))
                    : Optional.empty();
            }
        }
    }
}
```

Lệnh kiểm tra biên dịch:

```bash
javac --release 17 NoteReader.java
```

Không cần Spring trên classpath để biên dịch tệp này vì `DataSource` và `Connection` thuộc JDK. Nhưng để thực sự gọi `findTitle` cần có driver/pool, DB và instance `DataSource` được cấp.

Phân tích:

- `dataSource.getConnection()` mượn một kết nối. Nó có thể chờ pool hoặc truy cập DB và phát sinh `SQLException`.
- `PreparedStatement` dùng `?` và `statement.setLong(1, id)` để bind tham số, thay vì ghép giá trị vào chuỗi SQL.
- `try-with-resources` đảm bảo đóng `ResultSet`, `PreparedStatement`, rồi `Connection` ngay cả khi exception hoặc `return` xảy ra sớm.
- Nếu là pool, `close()` thường trả connection về pool. Nếu không dùng pool, nó thường đóng kết nối vật lý.
- Đây là **JDBC thuần ngoài transaction do Spring quản lý**. Khi cần raw JDBC tham gia giao dịch Spring, xem `DataSourceUtils` ở mục 7.

## 5. Spring Boot có thể cấu hình DataSource tự động

Ví dụ sau dùng **Java 17+, Spring Boot 3.3+ và H2 in-memory** để có thể chạy thực tế mà không cần dựng PostgreSQL. Tạo một ứng dụng Spring Boot Gradle thông thường, có plugin và dependency management Boot. Trong `build.gradle`, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Đây chỉ là khối `dependencies` bổ sung cho một dự án Spring Boot đã thiết lập, không phải toàn bộ tệp `build.gradle`.

**`src/main/resources/application.yml`:**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:datasource_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 5
```

**`src/main/java/example/DataSourceDemoApplication.java`:**

```java
package example;

import java.sql.Connection;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class DataSourceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DataSourceDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DataSource dataSource, JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE notes (
                    id BIGINT PRIMARY KEY,
                    title VARCHAR(100) NOT NULL
                )
                """);
            jdbc.update(
                "INSERT INTO notes (id, title) VALUES (?, ?)",
                1L, "Learn DataSource"
            );

            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM notes", Integer.class
            );
            System.out.println("Rows = " + count);

            try (Connection connection = dataSource.getConnection()) {
                System.out.println(
                    "Connection valid = " + connection.isValid(2)
                );
            }
        };
    }
}
```

Chạy từ dự án:

```bash
./gradlew bootRun
```

Trên Windows, dùng `gradlew.bat bootRun`. Nếu database in-memory là mới và chưa có bộ khởi tạo schema khác, bên cạnh log của Spring/Hikari, chương trình tự in:

```text
Rows = 1
Connection valid = true
```

**Tại sao?** Spring Boot đọc `spring.datasource.*`, dùng H2 và HikariCP trên classpath để tạo bean `DataSource` theo điều kiện auto-configuration. Bean `JdbcTemplate` được cấu hình cùng nguồn dữ liệu. `CommandLineRunner` chạy sau khi context khởi động; `JdbcTemplate` lần lượt tạo bảng, thêm một dòng và truy vấn số dòng. Lần gọi `dataSource.getConnection()` ở cuối lấy một connection handle; `isValid(2)` kiểm tra kết nối trong tối đa hai giây, rồi `try-with-resources` trả handle.

Nếu tự định nghĩa `@Bean DataSource`, quy tắc auto-configuration của Spring Boot có thể nhường chỗ cho bean tùy chỉnh. Trong Spring Framework thuần, `DataSource` không tự xuất hiện chỉ vì đã thêm Spring Core: bạn phải định nghĩa bean hoặc cấu hình provider phù hợp.

Ở môi trường production, thay H2 URL/driver bằng database thực tế và dùng credential từ môi trường hoặc secret manager; kết quả demo không chứng minh được mọi DB đều sẵn sàng.

## 6. JdbcTemplate dùng DataSource như thế nào?

Trong Spring JDBC, cách thường được khuyến khích là inject `JdbcTemplate`, để nó tự quản lý kết nối, statement, result set và chuyển nhiều `SQLException` thành các subclass của `DataAccessException`.

Ví dụ trong cùng dự án có bảng `notes`:

**`NoteRepository.java`:**

```java
package example;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NoteRepository {
    private final JdbcTemplate jdbc;

    public NoteRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<String> findTitles() {
        return jdbc.query(
            "SELECT title FROM notes ORDER BY id",
            (rs, rowNum) -> rs.getString("title")
        );
    }

    public int rename(long id, String title) {
        return jdbc.update(
            "UPDATE notes SET title = ? WHERE id = ?",
            title, id
        );
    }
}
```

Đây là một component của ứng dụng Spring có `JdbcTemplate` được cấu hình, không có `main` riêng. Phía dưới `JdbcTemplate` vẫn nhận connection từ `DataSource`:

```text
NoteRepository
     |
     v
JdbcTemplate --> DataSourceUtils --> DataSource --> Connection
     |
     +--> SQL, ResultSet, RowMapper, cleanup resources
```

Khởi tạo thủ công cũng được khi đã có biến `dataSource`:

```java
JdbcTemplate jdbc = new JdbcTemplate(dataSource);
```

Đây là mảnh mã trong một method/constructor có biến `dataSource`; Spring container thường tự tạo và inject bean khi đã cấu hình đúng.

**Điểm mấu chốt:** việc code không trực tiếp gọi `getConnection()` không có nghĩa `JdbcTemplate` bỏ qua `DataSource`. Spring thực hiện những lời gọi cần thiết ở lớp bên dưới, giúp code truy vấn ít lỗi đóng tài nguyên hơn.

## 7. Transaction của Spring: DataSource là nguồn cấp, Connection là tài nguyên giao dịch

Transaction JDBC vận hành trên một `Connection`. Khi dùng `DataSourceTransactionManager` hoặc `JdbcTransactionManager`, Spring lấy connection từ đúng `DataSource` và có thể ràng buộc nó với thread đang xử lý transaction.

```text
Call vào @Transactional service thông qua Spring proxy
                       |
            bắt đầu JDBC transaction
                       |
             DataSource -> Connection
                       |
      JdbcTemplate.update(...) dùng Connection đang bound
      JdbcTemplate.update(...) dùng Connection đang bound
                       |
         thành công -> commit
         lỗi cần rollback -> rollback
                       |
             unbind / release Connection
```

Ví dụ service:

**`NoteWriteService.java`:**

```java
package example;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NoteWriteService {
    private final JdbcTemplate jdbc;

    public NoteWriteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void addPair(long firstId, long secondId) {
        jdbc.update(
            "INSERT INTO notes (id, title) VALUES (?, ?)",
            firstId, "First"
        );
        jdbc.update(
            "INSERT INTO notes (id, title) VALUES (?, ?)",
            secondId, "Second"
        );
    }
}
```

Khi phương thức được gọi **qua Spring proxy**, transaction manager được cấu hình đúng cho cùng `DataSource` và không có thay đổi propagation đặc biệt, hai lần gọi `jdbc.update` tham gia giao dịch chung. Nếu lệnh thứ hai vi phạm primary key và ném runtime exception, Spring theo rollback rule mặc định sẽ rollback cả lệnh đầu.

Đây là code để tích hợp trong ứng dụng đã cấu hình transaction, không phải chương trình độc lập có stdout. Gọi nội bộ `this.addPair(...)` từ chính bean trong mô hình AOP proxy thông thường có thể bỏ qua transaction advice; khi đó cần xem lại đường gọi, không đổ lỗi cho `DataSource`.

### 7.1. Vì sao raw `DataSource.getConnection()` có thể sai trong `@Transactional`?

Trong một transaction Spring, nếu dùng data source/pool thông thường rồi gọi:

```java
Connection c = dataSource.getConnection();
```

Bạn **không được tự giả định** handle vừa nhận là connection đang bound với transaction. Để raw JDBC tham gia đúng giao dịch, Spring cung cấp `DataSourceUtils.getConnection(dataSource)` và `DataSourceUtils.releaseConnection(connection, dataSource)`. `JdbcTemplate` đã sử dụng cơ chế tương đương bên trong.

**`TransactionalNoteCount.java`:**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DataSourceUtils;

public final class TransactionalNoteCount {
    private final DataSource dataSource;

    public TransactionalNoteCount(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long count() throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            try (PreparedStatement statement =
                     connection.prepareStatement("SELECT COUNT(*) FROM notes");
                 ResultSet result = statement.executeQuery()) {
                result.next();
                return result.getLong(1);
            }
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
```

Đây là class Java 17+ cần thư viện Spring JDBC và `DataSource` được cấp runtime. `DataSourceUtils.getConnection` nhận kết nối transaction-bound khi có, hoặc lấy kết nối mới khi không có transaction. `releaseConnection` quyết định khi nào có thể thực sự trả/đóng handle. **Không dùng `try (Connection c = DataSourceUtils.getConnection(...))` để tự đóng connection do Spring đang quản lý;** dùng cặp get/release của Spring như trên.

Spring còn có `TransactionAwareDataSourceProxy` dành cho mã legacy buộc gọi API chuẩn `DataSource.getConnection()` nhưng cần tham gia Spring transaction. Với mã mới, `JdbcTemplate` hoặc `DataSourceUtils` thường dễ kiểm soát hơn. `LazyConnectionDataSourceProxy` có mục đích khác: trì hoãn mượn connection vật lý đến khi thực sự cần statement trong cấu hình phù hợp.

### 7.2. Giới hạn transaction cần nhớ

- `@Transactional` không đồng nghĩa mọi `Connection` trong JVM đều thuộc cùng transaction. Transaction manager quản lý **đúng `DataSource` mà nó được cấu hình**.
- Nhiều `DataSource` trỏ đến các DB khác nhau không tự có transaction phân tán nguyên tử chỉ nhờ một annotation; cần thiết kế orchestration/distributed transaction phù hợp.
- Transaction bound theo thread không tự được chuyển sang thread mới của `CompletableFuture`, `new Thread` hoặc `@Async`.
- Không tự gọi `commit()`, `rollback()` hoặc thay đổi `autoCommit` của handle mà Spring transaction manager sở hữu.
- `JdbcTransactionManager` là biến thể JDBC transaction manager có bổ sung dịch lỗi commit/rollback; `DataSourceTransactionManager` cũng quản lý giao dịch JDBC cho một `DataSource`.

## 8. Cấu hình pool: đừng giữ Connection lâu hơn cần thiết

Nếu pool tối đa có năm connection và năm tác vụ cùng giữ chúng, yêu cầu thứ sáu phải chờ (hoặc lỗi khi quá timeout). Tăng pool size thiếu phân tích có thể khiến DB quá tải, nhất là khi có nhiều replica của ứng dụng.

Ví dụ cấu hình HikariCP trong Spring Boot, sử dụng mật khẩu từ môi trường:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.example.internal:5432/app
    username: app_user
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
```

Đây là ví dụ cấu hình, cần PostgreSQL driver và DB tương ứng; `db.example.internal` chỉ là tên host minh họa. `maximum-pool-size` giới hạn số connection của pool, `connection-timeout` là thời gian đợi để mượn connection tính bằng mili-giây (30.000 = 30 giây). Timeout pool khác timeout kết nối mạng, timeout câu SQL và timeout transaction.

Các thói quen quan trọng:

1. **Đóng hoặc release handle đúng cách.** JDBC độc lập: `try-with-resources`; raw JDBC đang transaction Spring: `DataSourceUtils.releaseConnection`; `JdbcTemplate` tự quản lý.
2. **Tránh connection leak.** Nếu exception xuất hiện trước `close()`, pool có thể giữ handle ở trạng thái đang được mượn.
3. **Giảm thời gian chiếm connection.** Không nên chờ API mạng chậm hoặc chờ người dùng nhập dữ liệu trong lúc transaction vẫn giữ connection nếu không có yêu cầu nghiệp vụ.
4. **Tính toàn hệ thống.** Nhiều replica × pool max là tổng nhu cầu connection tiềm năng; tính đến giới hạn connection ở server DB.
5. **Giám sát:** số active/idle/pending, thời gian mượn, timeout, query time và lock contention; không kết luận mọi độ trễ đều do thiếu pool size.
6. **Quản lý shutdown:** để Spring container đóng bean pool khi ứng dụng kết thúc. `DataSource` là interface không có phương thức `close()` chuẩn; không đóng cả pool sau mỗi query.
7. **Không dựa vào trạng thái connection còn sót.** `autoCommit`, isolation, read-only, schema hoặc session settings là trạng thái cần framework/pool kiểm soát; mã không nên tin vào thay đổi từ lượt mượn trước.

Ví dụ *connection leak* do không có `finally`:

```java
Connection c = dataSource.getConnection();
runSomeSql(c);       // Nếu có exception, c.close() có thể không được gọi
c.close();
```

`runSomeSql` ở đây đại diện một hàm nghiệp vụ đã có, **không phải hàm Java chuẩn**. Với JDBC độc lập, hãy dùng:

```java
try (Connection c = dataSource.getConnection()) {
    runSomeSql(c);
}
```

Lưu ý quy tắc riêng cho Spring transaction ở mục 7. Không dựa vào garbage collector để thu hồi connection kịp thời.

## 9. Nhiều DataSource: đúng nguồn và đúng transaction manager

Một ứng dụng có thể có một data source cho DB giao dịch, một data source khác cho DB báo cáo. Mỗi bean vẫn thỏa interface `DataSource`, nhưng chúng cấp connection đến các địa chỉ khác nhau.

Ví dụ component được inject một bean có tên `reportingDataSource`:

```java
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Repository;

@Repository
public final class ReportConnectionProvider {
    private final DataSource reportingDataSource;

    public ReportConnectionProvider(
        @Qualifier("reportingDataSource") DataSource reportingDataSource
    ) {
        this.reportingDataSource = reportingDataSource;
    }
}
```

Class minh họa này đòi hỏi Spring context **đã định nghĩa bean `reportingDataSource`** và không tự cấu hình DB. Khi có nhiều bean, dùng `@Qualifier`, `@Primary` và transaction manager tương ứng để tránh truy vấn sai DB hoặc áp dụng sai giao dịch.

JPA/Hibernate cũng thường được cấu hình dựa trên data source tương ứng, nhưng `EntityManager` và `Connection` là các tầng trừu tượng khác nhau. Việc có một `DataSource` không tự biến nó thành persistence context của JPA.

## 10. Kiểm thử và chẩn đoán đúng lớp

Không nên chỉ test rằng bean `DataSource` tồn tại. Bean có thể khởi tạo thành công trong khi DB chưa thể phục vụ query; một số implementation trì hoãn việc kết nối thực tế.

- **Wiring:** xác minh `JdbcTemplate`/DAO nhận đúng `DataSource` được cấu hình.
- **Connectivity:** lấy và giải phóng `Connection`, gọi `isValid(timeout)` nếu driver hỗ trợ, hoặc chạy một query nhỏ.
- **Resource:** qua nhiều lượt truy vấn, active connections không tăng vô hạn và các handle được trả về pool.
- **Transaction:** với integration test thật, gây lỗi sau một câu update thành công rồi xác nhận rollback đúng; dùng cùng transaction manager và data source.
- **Multiple databases:** xác minh tên bean/`@Qualifier` và transaction manager định tuyến đúng.
- **Timeout:** phân biệt lỗi không mượn được connection trong pool với lỗi kết nối tới DB hoặc lỗi thực thi statement.

Phép kiểm tra kết nối trong một method có `dataSource` đã được inject:

```java
try (Connection connection = dataSource.getConnection()) {
    if (!connection.isValid(2)) {
        throw new IllegalStateException("Connection is not valid");
    }
}
```

Phép thử này xác nhận connection tại thời điểm kiểm tra có vẻ hợp lệ; nó không kiểm tra đầy đủ quyền ghi bảng, migration, schema hay tính đúng của SQL nghiệp vụ.

### Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| "DataSource chính là một connection." | `DataSource` là nguồn cấp; `Connection` là handle được mượn. |
| "Một DataSource bean tức chỉ có một physical connection." | Pool có thể quản lý nhiều connection đồng thời. |
| "Pool sẽ tự lấy lại connection nên khỏi cần close." | Mã vẫn phải đóng/release handle đúng cách. |
| "Mọi lần `getConnection()` đều mở kết nối TCP mới." | Pool có thể tái sử dụng kết nối vật lý. |
| "`JdbcTemplate` không cần DataSource vì code không gọi getConnection." | `JdbcTemplate` truy cập thông qua `DataSource` bên dưới. |
| "`@Transactional` bảo đảm mọi lệnh JDBC tự cùng giao dịch." | Phải dùng đúng transaction manager và transaction-aware connection lookup. |
| "Cứ tăng pool size khi database chậm." | Phải kiểm tra leak, query chậm, lock, timeout và giới hạn DB trước. |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao một singleton `@Repository` nên giữ `DataSource` hoặc `JdbcTemplate` thay vì giữ một `Connection` làm field?

**Đáp án:** `DataSource`/`JdbcTemplate` được thiết kế để dùng lại, còn `Connection` mang trạng thái transaction và có vòng đời mượn/trả ngắn. Giữ connection dùng chung có thể gây truy cập đồng thời sai, stale handle hoặc leak.

**Câu 2.** `Connection.close()` từ HikariCP có luôn đóng socket tới DB không?

**Đáp án:** Không. Thông thường nó giải phóng logical handle để pool có thể dùng lại kết nối vật lý; application vẫn bắt buộc đóng/release handle.

**Câu 3.** Nếu một service `@Transactional` dùng `JdbcTemplate`, connection được chọn từ đâu?

**Đáp án:** Từ `DataSource` được cấu hình cho `JdbcTemplate`/transaction manager. `JdbcTemplate` lấy connection theo cơ chế transaction-aware của Spring để sử dụng connection gắn với giao dịch khi phù hợp.

**Câu 4.** Một lớp JDBC thuần không tham gia transaction Spring nên đóng resource thế nào?

**Đáp án:** Dùng `try-with-resources` cho `Connection`, `PreparedStatement`, `ResultSet`, để bảo đảm chúng được giải phóng cả khi có exception.

**Câu 5.** Vì sao gọi `DataSourceUtils.releaseConnection` khi dùng `DataSourceUtils.getConnection`?

**Đáp án:** Spring cần biết connection đó có được giữ cho transaction đang chạy hay không; tự `close()` không tuân thủ đầy đủ hợp đồng transaction-aware.

## 12. Tài liệu tham khảo

- [Java SE 21 — `javax.sql.DataSource`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/javax/sql/DataSource.html): hợp đồng nguồn cấp `Connection`, các implementation trực tiếp/pooled.
- [Java SE 21 — `java.sql.Connection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html): API statement, transaction, `close`.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSource`, `DataSourceUtils`, transaction manager và proxy.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate` và quản lý tài nguyên JDBC.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): tự cấu hình `DataSource`, connection pool, HikariCP.

**Ghi nhớ:** `DataSource` là **nơi xin Connection**, còn `Connection` là **tài nguyên được dùng rồi giải phóng**. Trong Spring JDBC, để `JdbcTemplate` và transaction infrastructure quản lý việc mượn/trả theo đúng ranh giới transaction; khi viết JDBC thuần, tự đóng connection bằng `try-with-resources`.