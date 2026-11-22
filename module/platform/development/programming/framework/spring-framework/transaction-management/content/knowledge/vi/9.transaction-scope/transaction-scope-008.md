# Phân biệt giao dịch đang hoạt động với đồng bộ hóa tài nguyên trong Spring Framework

## 1. Câu hỏi cốt lõi

Trong Spring Transaction Management, có hai điều rất dễ bị đánh đồng:

1. **Có giao dịch thực sự đang hoạt động không?** Tức thread hiện tại đang được Spring transaction manager gắn với một *actual transaction* của tài nguyên, chẳng hạn JDBC transaction có thể được commit/rollback.
2. **Có cơ chế đồng bộ hóa tài nguyên đang hoạt động không?** Tức Spring đã mở một *transaction synchronization scope* cho thread, để quản lý việc gắn tài nguyên, chia sẻ Connection/Session và gọi các `TransactionSynchronization` callbacks.

Hai trạng thái này liên quan nhưng **không tương đương**. Một lời gọi `@Transactional(propagation = Propagation.SUPPORTS)` không có transaction bên ngoài có thể có **synchronization đang active**, dù **không hề có transaction JDBC vật lý**. Đây là trường hợp quan trọng nhất để hiểu đúng chủ đề.

Spring cung cấp hai phép kiểm tra riêng trên lớp `org.springframework.transaction.support.TransactionSynchronizationManager` (dành cho luồng imperative):

```java
boolean synchronizationActive =
        TransactionSynchronizationManager.isSynchronizationActive();

boolean actualTransactionActive =
        TransactionSynchronizationManager.isActualTransactionActive();
```

**Diễn giải đúng:**

- `isSynchronizationActive()` cho biết hạ tầng **synchronization** đã được kích hoạt trên thread; khi true, mã quản lý tài nguyên có thể đăng ký synchronization callback.
- `isActualTransactionActive()` cho biết Spring đang đánh dấu thread này là liên kết với **actual transaction**, thay vì chỉ có synchronization.
- Không phép kiểm tra nào tự xác nhận **transaction đã commit thành công**; chúng là tín hiệu trạng thái *tại thời điểm gọi*, không phải biên bản commit.

Phạm vi bài: Spring Framework quản lý transaction imperative với JDBC/JPA theo thread, Spring AOP proxy và `PlatformTransactionManager`. Reactive transaction có cơ chế context khác, được nhắc ở cuối.

## 2. Phân biệt ba thứ: giao dịch, synchronization và resource binding

Để không hiểu sai hai boolean, cần tách rõ **ba khái niệm**.

### 2.1. Actual transaction: ranh giới commit/rollback

Một transaction thực sự có lifecycle của tài nguyên: bắt đầu, thực hiện thao tác, cuối cùng commit hoặc rollback. Với `JdbcTransactionManager`, Spring dùng JDBC connection, thường đưa `autoCommit` về `false` trong transaction mới và phát lệnh `commit()` hoặc `rollback()` khi cần.

`@Transactional` với `Propagation.REQUIRED` và **không có transaction ngoài** thường mở actual transaction mới. Nếu `REQUIRED` tham gia transaction ngoài, nó không tạo transaction vật lý riêng nhưng vẫn đang chạy trong actual transaction đã tồn tại.

### 2.2. Transaction synchronization: scope đồng bộ hóa

Synchronization là hạ tầng Spring quản lý theo thread, có thể phục vụ:

- Đăng ký `TransactionSynchronization` và các callback như `beforeCommit`, `beforeCompletion`, `afterCommit`, `afterCompletion`.
- Gắn tài nguyên như JDBC `ConnectionHolder` hoặc ORM `SessionHolder` vào thread và chia sẻ chúng trong một scope.
- Tháo/buộc lại tài nguyên khi suspend/resume transaction.
- Đóng, giải phóng tài nguyên và dọn trạng thái khi scope kết thúc.

**Synchronization không nhất thiết đi cùng actual transaction.** Một transaction manager kiểu `AbstractPlatformTransactionManager` mặc định dùng chính sách `SYNCHRONIZATION_ALWAYS`, cho phép bật synchronization ngay cả trong **empty transaction scope** của `SUPPORTS` khi không có physical transaction.

Từ "transaction synchronization" ở đây là **cơ chế Spring quản lý resource và callback**; nó không đồng nghĩa với giao dịch phân tán, đồng bộ dữ liệu giữa hai hệ thống hay khóa DB.

### 2.3. Resource binding: có tài nguyên được gắn với thread

`TransactionSynchronizationManager.hasResource(key)` hỏi xem một tài nguyên đã gắn với một key như `DataSource` hay chưa. Đó là trạng thái thứ ba, độc lập với việc synchronization có active hay actual transaction có tồn tại hay không.

```java
boolean resourceBound =
        TransactionSynchronizationManager.hasResource(dataSource);

Object resource =
        TransactionSynchronizationManager.getResource(dataSource);
```

Đây là đoạn API minh họa, giả định `dataSource` được cung cấp. `hasResource(dataSource) == true` có thể xảy ra khi:

- Transaction manager đã bắt đầu JDBC transaction và gắn connection holder.
- Một scope `SUPPORTS` **không có actual transaction** nhưng `DataSourceUtils` mở connection và gắn resource vì synchronization đang bật.
- Một hạ tầng quản lý tài nguyên khác gắn holder có lifecycle riêng.

Vì vậy, **có resource bound không chứng minh DB transaction đang mở**. Ngược lại, synchronization active không bắt buộc phải có resource được lấy ra ngay từ đầu scope.

## 3. Bảng trạng thái quan trọng

Với `JdbcTransactionManager` hoặc `DataSourceTransactionManager` sử dụng chính sách mặc định `SYNCHRONIZATION_ALWAYS`:

| Ngữ cảnh lúc quan sát | `isSynchronizationActive()` | `isActualTransactionActive()` | Có transaction DB mà Spring đang quản lý? |
| --- | --- | --- | --- |
| Ngoài mọi Spring transactional scope | `false` | `false` | Không có từ context đang quan sát |
| `@Transactional(REQUIRED)` tạo transaction mới | `true` | `true` | Có |
| `@Transactional(SUPPORTS)` nhưng caller không có transaction | `true` | `false` | **Không**, dù có synchronization |
| `@Transactional(SUPPORTS)` tham gia transaction `REQUIRED` bên ngoài | `true` | `true` | Có, dùng transaction ngoài |
| `NOT_SUPPORTED` tạm treo actual transaction | Tùy policy/manager, có thể `true` | `false` trong scope bị tạm treo | Không có transaction vật lý đang tham gia trong scope đó |

Đây là bảng cho **một cấu hình cụ thể**, không phải định luật mọi framework. Khi transaction manager được cấu hình `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION`, một `SUPPORTS` không có actual transaction sẽ **không** tạo synchronization. Chính sách `SYNCHRONIZATION_NEVER` còn vô hiệu hóa hạ tầng synchronization. Ở các cấu hình tùy biến hoặc transaction được quản lý ngoài Spring, thread-local flags có thể không phản ánh toàn bộ trạng thái connection bên dưới.

**Tuyệt đối không suy ra `synchronizationActive == true` nghĩa là `commit` hoặc `rollback` sẽ xảy ra ở DB.** Đây là lỗi phổ biến nhất của bài.

## 4. Vì sao `PROPAGATION_SUPPORTS` vẫn bật synchronization?

`Propagation.SUPPORTS` có nghĩa: *có transaction thì tham gia, không có thì chạy không có transaction vật lý*. Nhưng "chạy không có transaction vật lý" không bắt buộc phải là "không có hạ tầng resource synchronization".

Luồng khi **không có transaction ngoài** và policy `SYNCHRONIZATION_ALWAYS`:

```text
Caller không có transaction
  |
  v
Spring proxy của method @Transactional(SUPPORTS)
  |-- Không tạo physical transaction mới
  |-- Mở synchronization scope cho thread
  |     isSynchronizationActive()  = true
  |     isActualTransactionActive() = false
  |
  |-- Method chạy
  |     |-- Có thể lấy JDBC Connection qua DataSourceUtils
  |     |-- Connection có thể được bind, reuse và cleanup theo scope
  |     '-- SQL trên Connection autoCommit=true có thể commit ngay
  |
  |-- Hoàn tất logical/empty scope, thực hiện synchronization/cleanup phù hợp
  '-- Trả quyền điều khiển cho caller
```

**Kết luận:** "đồng bộ hóa tài nguyên" mô tả khả năng phối hợp lifecycle connection/callback theo thread; nó **không tạo ra tính nguyên tử/rollback** cho nhiều câu SQL nếu không có transaction DB tương ứng.

Khi `SUPPORTS` được gọi trong một `REQUIRED` đã có transaction ngoài, nó tham gia actual transaction đó. Cùng một phương thức `SUPPORTS` có thể nhìn thấy `actual=false` trong trường hợp thứ nhất và `actual=true` trong trường hợp thứ hai.

## 5. Ví dụ chạy được với Java 17+, Spring Framework và H2

Ví dụ dưới đây cố ý kiểm tra **cả ba trạng thái**: synchronization, actual transaction và resource đã bind. Nó cũng cho thấy cùng một unchecked exception có thể khiến SQL rollback trong `REQUIRED` nhưng **không thể rollback SQL auto-commit** trong `SUPPORTS` không có transaction.

Yêu cầu: Java 17+, Maven, Spring Framework **6.2.5**, H2 **2.2.224**. Không cần Spring Boot hoặc database server.

Cấu trúc:

```text
transaction-state-demo/
  pom.xml
  src/main/java/demo/TransactionStateDemo.java
```

### 5.1. Tạo `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>transaction-state-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là ứng dụng Java SE dùng Spring container thuần, không dùng Spring Boot auto-configuration. `DriverManagerDataSource` thích hợp để minh họa; production nên dùng connection pool phù hợp.

### 5.2. Tạo `src/main/java/demo/TransactionStateDemo.java`

```java
package demo;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransactionStateDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            DataSource dataSource = context.getBean(DataSource.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            ProbeService probe = context.getBean(ProbeService.class);
            CallerService caller = context.getBean(CallerService.class);

            jdbc.execute("CREATE TABLE log_entry "
                    + "(id INT PRIMARY KEY, label VARCHAR(30))");

            state("OUTSIDE", dataSource);
            probe.supportsInspect("SUPPORTS_NO_TX");
            state("AFTER_SUPPORTS", dataSource);

            probe.requiredInsert(1, false);
            System.out.println("AFTER_REQUIRED_ROWS=" + count(jdbc));

            try {
                probe.supportsInsertThenFail(2);
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT_SUPPORTS=" + ex.getMessage());
            }
            System.out.println("AFTER_SUPPORTS_FAILURE_ROWS=" + count(jdbc));

            try {
                probe.requiredInsert(3, true);
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT_REQUIRED=" + ex.getMessage());
            }
            System.out.println("AFTER_REQUIRED_FAILURE_ROWS=" + count(jdbc));

            caller.requiredCallsSupports();
            state("AFTER_OUTER", dataSource);
        }
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM log_entry", Integer.class);
    }

    static void state(String label, DataSource dataSource) {
        System.out.printf("%s sync=%s actual=%s bound=%s%n",
                label,
                TransactionSynchronizationManager.isSynchronizationActive(),
                TransactionSynchronizationManager.isActualTransactionActive(),
                TransactionSynchronizationManager.hasResource(dataSource));
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        DataSource dataSource() {
            var dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl("jdbc:h2:mem:sync_demo;DB_CLOSE_DELAY=-1");
            dataSource.setUsername("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            var manager = new JdbcTransactionManager(dataSource);
            manager.setTransactionSynchronization(
                    AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS);
            return manager;
        }

        @Bean
        ProbeService probeService(DataSource dataSource, JdbcTemplate jdbc) {
            return new ProbeService(dataSource, jdbc);
        }

        @Bean
        CallerService callerService(ProbeService probe, DataSource dataSource) {
            return new CallerService(probe, dataSource);
        }
    }

    public static class ProbeService {
        private final DataSource dataSource;
        private final JdbcTemplate jdbc;

        public ProbeService(DataSource dataSource, JdbcTemplate jdbc) {
            this.dataSource = dataSource;
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.SUPPORTS)
        public void supportsInspect(String label) {
            state(label + "_BEFORE", dataSource);

            Connection connection = DataSourceUtils.getConnection(dataSource);
            try {
                state(label + "_AFTER", dataSource);
                System.out.println(label + "_AUTOCOMMIT="
                        + connection.getAutoCommit());
            } catch (SQLException ex) {
                throw new IllegalStateException("Cannot inspect connection", ex);
            } finally {
                DataSourceUtils.releaseConnection(connection, dataSource);
            }
        }

        @Transactional
        public void requiredInsert(int id, boolean failAfterInsert) {
            state("REQUIRED_INSERT", dataSource);
            jdbc.update(
                    "INSERT INTO log_entry (id, label) VALUES (?, ?)",
                    id, "required");
            if (failAfterInsert) {
                throw new IllegalStateException("required failure");
            }
        }

        @Transactional(propagation = Propagation.SUPPORTS)
        public void supportsInsertThenFail(int id) {
            state("SUPPORTS_WRITE", dataSource);
            jdbc.update(
                    "INSERT INTO log_entry (id, label) VALUES (?, ?)",
                    id, "supports");
            throw new IllegalStateException("supports failure");
        }
    }

    public static class CallerService {
        private final ProbeService probe;
        private final DataSource dataSource;

        public CallerService(ProbeService probe, DataSource dataSource) {
            this.probe = probe;
            this.dataSource = dataSource;
        }

        @Transactional
        public void requiredCallsSupports() {
            state("OUTER_REQUIRED", dataSource);
            probe.supportsInspect("SUPPORTS_JOINED");
            state("OUTER_AFTER_SUPPORTS", dataSource);
        }
    }
}
```

**Tại sao code này được Spring intercept?** `ProbeService` và `CallerService` đều là bean do `@Bean` tạo. `main` lấy các bean qua `context.getBean(...)`, còn `CallerService` gọi sang một bean khác. Các phương thức `@Transactional` là `public`, nên lời gọi đi qua Spring proxy; không phải self-invocation `this.method()`.

**Vì sao phải dùng `DataSourceUtils` trong `supportsInspect`?** Nó kiểm tra resource đã gắn với thread; nếu synchronization active, nó có thể lấy và **bind connection** ngay cả khi actual transaction không hoạt động. Sau đó `releaseConnection` sẽ phối hợp với Spring cleanup; không đóng bừa connection đang được một transaction bên ngoài dùng.

`SYNCHRONIZATION_ALWAYS` được ghi tường minh để làm rõ điều kiện của thí nghiệm. Đây cũng là giá trị mặc định của `AbstractPlatformTransactionManager` trong cấu hình chuẩn.

### 5.3. Chạy và kết quả

Trong thư mục `transaction-state-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TransactionStateDemo
```

Các dòng `System.out` của chương trình, bỏ qua log Maven/Spring:

```text
OUTSIDE sync=false actual=false bound=false
SUPPORTS_NO_TX_BEFORE sync=true actual=false bound=false
SUPPORTS_NO_TX_AFTER sync=true actual=false bound=true
SUPPORTS_NO_TX_AUTOCOMMIT=true
AFTER_SUPPORTS sync=false actual=false bound=false
REQUIRED_INSERT sync=true actual=true bound=true
AFTER_REQUIRED_ROWS=1
SUPPORTS_WRITE sync=true actual=false bound=false
CAUGHT_SUPPORTS=supports failure
AFTER_SUPPORTS_FAILURE_ROWS=2
REQUIRED_INSERT sync=true actual=true bound=true
CAUGHT_REQUIRED=required failure
AFTER_REQUIRED_FAILURE_ROWS=2
OUTER_REQUIRED sync=true actual=true bound=true
SUPPORTS_JOINED_BEFORE sync=true actual=true bound=true
SUPPORTS_JOINED_AFTER sync=true actual=true bound=true
SUPPORTS_JOINED_AUTOCOMMIT=false
OUTER_AFTER_SUPPORTS sync=true actual=true bound=true
AFTER_OUTER sync=false actual=false bound=false
```

### 5.4. Giải thích từng nhóm kết quả

**Nhóm A — ngoài transaction:** `OUTSIDE` và `AFTER_SUPPORTS` đều có ba flag false. Spring đã dọn thread-bound synchronization và connection sau khi scope kết thúc.

**Nhóm B — `SUPPORTS` không có actual transaction:** ngay đầu method, `sync=true`, `actual=false` và `bound=false`. Sau `DataSourceUtils.getConnection`, `bound=true` dù `actual` vẫn false. Connection H2 mới có `autoCommit=true`; đồng bộ hóa tài nguyên không tự làm cho connection thành một transaction JDBC có thể rollback nhiều SQL.

**Nhóm C — `REQUIRED`:** `sync=true`, `actual=true`, `bound=true` trước khi `JdbcTemplate` làm việc, vì transaction manager đã mở và bind JDBC connection. Thao tác insert đầu tiên commit, nên số hàng là 1.

**Nhóm D — lỗi trong `SUPPORTS` không có transaction:** `supportsInsertThenFail` gửi `INSERT` vào connection auto-commit, rồi ném runtime exception. Spring có thể xử lý kết thúc logical transaction scope, nhưng **không có physical transaction để rollback SQL đã auto-commit**. Số hàng vẫn tăng lên 2. Điều này chứng minh `synchronization=true` **không đảm bảo atomicity**.

**Nhóm E — lỗi trong `REQUIRED`:** `requiredInsert(3, true)` ném runtime exception trong actual JDBC transaction. Interceptor rollback, số hàng vẫn bằng 2. Việc hai method cùng ném `IllegalStateException` nhưng có kết quả DB khác nhau xuất phát từ **có hay không có transaction vật lý**.

**Nhóm F — `SUPPORTS` tham gia outer `REQUIRED`:** `CallerService.requiredCallsSupports()` mở transaction trước, rồi gọi `supportsInspect` thông qua bean proxy. Bên trong SUPPORTS, `sync=true`, `actual=true`, `bound=true` và JDBC connection có `autoCommit=false`. Cùng một annotation SUPPORTS, nhưng lúc này nó đang dùng transaction bên ngoài. Sau khi outer method hoàn tất, các flag trở về false.

**Ghi chú về tính tái lập:** Các giá trị `autoCommit` trên đây thuộc driver H2 và cách Spring JDBC manager điều chỉnh connection trong demo. Cấu hình pool/driver/transaction manager khác có thể đưa ra trạng thái khác; hãy kiểm tra chính manager của dự án.

## 6. Cách `TransactionSynchronizationManager` quản lý resource

Trong Spring imperative, `TransactionSynchronizationManager` dùng **thread-local** để giữ:

- Bản đồ resource key → resource holder (ví dụ `DataSource` → `ConnectionHolder`).
- Bộ `TransactionSynchronization` callbacks đã đăng ký khi synchronization active.
- Một số thông tin do manager công bố, gồm tên transaction, read-only, isolation và actual-transaction flag.

Các API cần nhớ:

| API | Nó trả lời câu hỏi gì? |
| --- | --- |
| `isSynchronizationActive()` | Có scope synchronization để đăng ký callbacks không? |
| `isActualTransactionActive()` | Thread hiện tại được Spring đánh dấu gắn với actual transaction không? |
| `hasResource(dataSource)` | Có resource holder nào gắn với key `dataSource` trên thread không? |
| `getResource(dataSource)` | Lấy holder đã bind cho key tương ứng; có thể null nếu chưa có |
| `getResourceMap()` | Snapshot các resource hiện đang bind, hữu ích khi debug (không phải chứng cứ commit) |
| `getSynchronizations()` | Snapshot callbacks đăng ký; chỉ gọi khi synchronization active |
| `registerSynchronization(callback)` | Đăng ký callback vào scope hiện tại; chỉ hợp lệ khi synchronization active |
| `isCurrentTransactionReadOnly()` | Đọc metadata read-only do manager công bố, không chứng minh DB cấm ghi |
| `getCurrentTransactionIsolationLevel()` | Đọc isolation metadata mà Spring công bố; không nhất thiết là mọi trạng thái native của DB |

**Đừng tự gọi** `initSynchronization()`, `clearSynchronization()`, `bindResource()`, `unbindResource()` hay `setActualTransactionActive()` trong service nghiệp vụ thông thường. Đó là API thấp tầng dành cho transaction manager, resource manager và hạ tầng tích hợp. Tự chỉnh flags hoặc unbind nhầm holder của bên khác có thể làm hỏng lifecycle, leak connection hoặc mất ngữ cảnh transaction.

### Vì sao `getResource` không đủ để kết luận commit/rollback?

Một `ConnectionHolder` có thể được bind khi synchronization active để cùng thread sử dụng lại connection. Việc **bind** chỉ nói rằng Spring đang quản lý vòng đời tài nguyên; nó không nói connection có đang `autoCommit=false` hay tham gia transaction nào. Để xác định khả năng rollback, phải xét transaction manager, propagation, loại connection và ranh giới cuối cùng.

Ngoài ra, `hasResource(dataSource)` có thể false **trước khi method chạm đến DB**, dù synchronization đã active; demo đã in `SUPPORTS_NO_TX_BEFORE bound=false`. Resource thường được bind **lazily** khi có lời gọi thực sự lấy connection.

## 7. Cấu hình policy synchronization của transaction manager

`AbstractPlatformTransactionManager` có ba chế độ đáng biết:

| Policy | Hành vi |
| --- | --- |
| `SYNCHRONIZATION_ALWAYS` | Mở synchronization ngay cả cho scope "empty" như `SUPPORTS` không có transaction; **mặc định** |
| `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` | Chỉ mở synchronization cho các scope có actual transaction, bỏ qua empty SUPPORTS |
| `SYNCHRONIZATION_NEVER` | Không kích hoạt hạ tầng synchronization qua manager này |

Ví dụ khi cố ý chỉ muốn synchronization với actual transaction:

```java
JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
manager.setTransactionSynchronization(
        AbstractPlatformTransactionManager.SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
```

Đây là **đoạn minh họa cấu hình**, không phải một chương trình độc lập. Khi thay policy trên transaction manager **trong bản sao demo**, `@Transactional(SUPPORTS)` không có transaction ngoài sẽ có `sync=false`; lúc đó `DataSourceUtils` không bind connection chỉ vì synchronization scope.

**Không tùy tiện thay policy chỉ để khiến hai boolean luôn bằng nhau.** Một số thư viện/hạ tầng kỳ vọng resource synchronization để phối hợp connection lifecycle. Cần kiểm tra phạm vi ảnh hưởng trên các repository và transaction callbacks của dự án.

Ngoài ra, `SYNCHRONIZATION_NEVER` có thể khiến thread-local metadata do manager công bố khác đi dù manager vẫn xử lý một transaction thực sự. Do đó hai API trên là **tín hiệu trong Spring thread context**, không phải giao thức để kiểm tra trực tiếp trạng thái vật lý của mọi DB connection ngoài hệ sinh thái Spring.

## 8. `TransactionSynchronization` callbacks có phải bằng chứng commit?

Một đoạn code có thể muốn đăng ký tác vụ tại cuối transaction:

```java
if (TransactionSynchronizationManager.isSynchronizationActive()
        && TransactionSynchronizationManager.isActualTransactionActive()) {
    TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    // Chạy sau commit thành công của transaction tương ứng.
                }
            });
}
```

Đây là **mã minh họa** trong Spring-managed service; cần import `TransactionSynchronization` và `TransactionSynchronizationManager`. Hai phép kiểm tra cùng true là một **điều kiện thận trọng** khi nghiệp vụ yêu cầu có actual transaction trước khi đăng ký callback sau commit. Trong ví dụ SUPPORTS không có actual transaction, điều kiện thứ hai sẽ false; không giả định có commit DB chỉ vì `registerSynchronization` có thể thực hiện.

Các điểm quan trọng:

1. `registerSynchronization(...)` chỉ yêu cầu synchronization **active** để hợp lệ về mặt API. Điều đó không bắt buộc đồng thời có physical transaction.
2. Với empty synchronization scope, việc xử lý callbacks phụ thuộc transaction manager; **không nên coi tên callback `afterCommit` là bằng chứng luôn có một DB commit thật**. Chọn ranh giới actual transaction phù hợp trước khi đăng ký tác vụ cần tính bền vững.
3. `afterCommit` của một **actual transaction** chạy khi manager đã thực hiện commit thành công theo cơ chế của nó; nhưng callback này không bảo đảm các hệ thống khác (email, queue, HTTP) đã nhận dữ liệu.
4. Các thao tác DB mới thực hiện trong `afterCommit` đôi khi vẫn thấy resource còn được gắn với thread; nếu cần ghi một giao dịch độc lập, đặt logic trong service khác với `Propagation.REQUIRES_NEW`.
5. Muốn gửi sự kiện/notification **bền vững** qua việc ứng dụng chết sau DB commit, cân nhắc **transactional outbox**: ghi bản ghi nghiệp vụ và outbox trong cùng actual transaction, worker gửi lại với cơ chế idempotency.

Có thể sử dụng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` ở tầng ứng dụng, nhưng cũng phải hiểu việc phát event có gắn với transaction/synchronization thực sự hay không, và xử lý các tình huống ngoài transaction theo semantics của Spring.

## 9. `SUPPORTS`, `NOT_SUPPORTED` và transaction được tạm treo

Có ba tình huống cần phân biệt:

**Tình huống A: `SUPPORTS` không có outer transaction.** Với policy `SYNCHRONIZATION_ALWAYS`, synchronization active nhưng actual=false. Các thao tác SQL có thể auto-commit; mã nghiệp vụ cần atomicity không nên dựa vào SUPPORTS trong trường hợp này.

**Tình huống B: `SUPPORTS` có outer transaction.** Method con tham gia actual transaction của outer. Điều đó cũng nghĩa là **method con trả về không phải commit cuối cùng**; outer có thể rollback sau đó.

**Tình huống C: `NOT_SUPPORTED` được gọi khi đang có transaction.** Transaction manager cố tạm treo transaction và resource/synchronization gắn với nó; phần xử lý `NOT_SUPPORTED` không tham gia actual transaction đã tạm treo. Tùy policy manager, một synchronization scope "empty" có thể được tạo trong phần NOT_SUPPORTED. Khi kết thúc, transaction outer được resume. Không dùng một giá trị `isSynchronizationActive()` để kết luận transaction outer đã mất hay đã commit.

Các propagation khác cũng cần ngữ cảnh: `REQUIRES_NEW` mở transaction vật lý độc lập; `NESTED` thường dùng savepoint cùng transaction vật lý; `MANDATORY` đòi transaction có sẵn. Chủ đề của bài vẫn là phân biệt **thread synchronization** và **actual transaction**, không biến bảng flag thành một cách thay thế toàn bộ semantics propagation.

## 10. Khi nào kiểm tra từng trạng thái trong code?

| Nhu cầu | Cách kiểm tra phù hợp | Không nên suy luận |
| --- | --- | --- |
| Viết lớp tích hợp cần đăng ký synchronization callback | `isSynchronizationActive()` trước `registerSynchronization` | Callback được phép đăng ký tức DB transaction đang tồn tại |
| Chỉ thực hiện một tác vụ khi Spring báo có actual transaction | `isActualTransactionActive()` trong cùng thread | Transaction đã commit hoặc chắc chắn sẽ commit |
| Kiểm tra JDBC resource đã được bind | `hasResource(dataSource)`/`getResource(dataSource)` | Connection bound nghĩa là `autoCommit=false` |
| Thẩm định commit cuối cùng | Quan sát sau outer transaction hoặc dùng after-commit hook phù hợp | `save()`, `flush()` hoặc các boolean tại giữa method đã đủ |
| Xác nhận rollback nghiệp vụ | Integration test ghi SQL rồi ném exception, kiểm tra DB sau scope | `isSynchronizationActive() == true` đủ để rollback |
| Xử lý dữ liệu ở thread mới, `@Async` | Đặt ranh giới transaction rõ tại thread thực thi | Thread-local Spring transaction tự truyền sang worker thread |
| Giao dịch reactive | Dùng API `org.springframework.transaction.reactive.TransactionSynchronizationManager`, Reactor context và reactive transaction manager | Dùng trực tiếp static thread-local imperative API cho reactive pipeline |

**Gợi ý thiết kế:** khi mục tiêu là *đảm bảo atomicity*, hãy thiết kế transaction boundary rõ ràng với `@Transactional(REQUIRED)`/`REQUIRES_NEW` theo yêu cầu nghiệp vụ. Không dùng logic kiểu `if (isSynchronizationActive())` để quyết định "đã có transaction an toàn", vì kiểm tra đó không phân biệt SUPPORTS không có physical transaction.

## 11. Lỗi phổ biến và cách sửa

| Lỗi | Điều gì sai? | Cách xử lý |
| --- | --- | --- |
| `isSynchronizationActive() == true` được coi là có DB transaction | Synchronization có thể active trong empty `SUPPORTS` | Kiểm tra `isActualTransactionActive()` và transaction boundary |
| `hasResource(dataSource) == true` được coi là SQL rollback được | Holder cũng có thể bind trong scope không có actual transaction | Kiểm tra manager, connection và propagation; viết rollback test |
| `SUPPORTS` ném runtime exception, kỳ vọng SQL đã auto-commit rollback | Không có transaction vật lý để undo các SQL đã commit | Dùng `REQUIRED` khi nghiệp vụ cần atomicity |
| `isActualTransactionActive() == true` được coi là commit thành công | Nó chỉ báo transaction đang active **hiện tại** | Kiểm tra sau boundary, callback và DB state |
| Tự bind/unbind resource trong service | Có thể phá holder mà transaction manager quản lý | Dùng `JdbcTemplate`/`DataSourceUtils`/API transaction chuẩn |
| Dùng `dataSource.getConnection()` trực tiếp mà đòi Spring JDBC quản lý như `DataSourceUtils` | Connection trực tiếp có thể không tham gia thread-bound transaction | Dùng `JdbcTemplate` hoặc `DataSourceUtils` khi thao tác JDBC |
| Gọi `getSynchronizations()` khi sync=false | Có thể ném `IllegalStateException` | Kiểm tra `isSynchronizationActive()` trước |
| Tự gọi method `this.supportsMethod()` rồi suy luận từ annotation | Trong proxy mode, lời gọi nội bộ thường bỏ qua transaction interceptor của method con | Gọi qua Spring bean/proxy |
| Gọi sang `@Async` rồi kỳ vọng hai flags giữ nguyên | Thread-local không tự lan truyền | Tạo boundary phù hợp trong worker thread |
| Đọc metadata trong Spring test `@Transactional` rồi coi là commit | TestContext thường rollback transaction test | Dùng test về commit/rollback đúng vòng đời, `TestTransaction` khi cần |
| Dựa vào flags trong JTA/reactive hoặc code quản lý transaction ngoài Spring | Thread-bound flags không thay thế native transaction API | Kiểm tra đúng manager/runtime và context |

## 12. Bài tập tự kiểm tra

**Câu 1.** Một service `@Transactional(SUPPORTS)` được gọi từ controller không có transaction, `isSynchronizationActive() == true` và `isActualTransactionActive() == false`. Có mâu thuẫn không?

**Đáp án:** Không. Với policy mặc định `SYNCHRONIZATION_ALWAYS`, Spring có thể mở synchronization scope "empty" mà không mở actual transaction.

**Câu 2.** Trong scope `SUPPORTS` trên, `DataSourceUtils.getConnection(...)` làm `hasResource(dataSource)` chuyển từ false sang true. Có thể kết luận `autoCommit=false` không?

**Đáp án:** Không. Trong ví dụ H2, connection vẫn có `autoCommit=true`. Binding chỉ phục vụ lifecycle/resource reuse của thread.

**Câu 3.** Hai service cùng ném `IllegalStateException` sau `JdbcTemplate.update`. Service A dùng `SUPPORTS` không có outer tx; service B dùng `REQUIRED` tạo tx mới. Có thể cùng rollback SQL không?

**Đáp án:** Không mặc định. Với H2 auto-commit, A có thể đã commit SQL ngay và không thể rollback; B rollback thay đổi trong transaction vật lý.

**Câu 4.** Vì sao `isActualTransactionActive() == true` trong method con `REQUIRED` không đảm bảo row tồn tại sau khi method con return?

**Đáp án:** Method con có thể tham gia transaction ngoài; outer có thể rollback sau đó. Boolean chỉ phản ánh trạng thái hiện tại, không dự báo kết quả cuối.

**Câu 5.** Nếu đặt `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION`, lần gọi `SUPPORTS` không có outer tx có còn `sync=true` không?

**Đáp án:** Không theo chính sách này. Manager chỉ khởi tạo synchronization khi có actual transaction tương ứng.

**Câu 6.** Chỉ nhìn `getResourceMap()` thấy một `ConnectionHolder`, có chắc hàng đã insert được commit thành công không?

**Đáp án:** Không. Resource binding và transaction commit là hai khái niệm khác; cần quan sát sau ranh giới actual transaction và DB state.

## Ghi nhớ

- **`isSynchronizationActive()` hỏi về hạ tầng đồng bộ hóa; `isActualTransactionActive()` hỏi về actual transaction mà Spring đang công bố trên thread.**
- **`SUPPORTS` + không có outer transaction + `SYNCHRONIZATION_ALWAYS`** là ví dụ chuẩn của `sync=true, actual=false`.
- Resource `bound=true` có thể xuất hiện chỉ vì đồng bộ hóa đang active, dù không có DB transaction có thể rollback.
- `REQUIRED` thường có actual transaction; `SUPPORTS` tham gia outer transaction thì cũng có actual transaction.
- Hai boolean **không chứng minh commit**, và không thay thế transaction boundary hoặc integration test.
- Trong imperative Spring, các trạng thái ở trên gắn với **thread**. Reactive transaction dùng **Reactor context** và API riêng.

## Tài liệu tham khảo chính thức

1. Spring Framework — [`TransactionSynchronizationManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): phân biệt `isSynchronizationActive` và `isActualTransactionActive`.
2. Spring Framework — [`AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): ba transaction synchronization policies.
3. Spring Framework — [`DataSourceUtils` Javadoc](https://www.springframework.org/spring/docs/6.2.5/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html): lấy và bind JDBC connection khi synchronization active.
4. Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logic transaction vật lý vs logical transaction.
5. Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): cách dùng transaction manager và transaction template.
6. Spring Framework — [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): lifecycle và thời điểm callback.
