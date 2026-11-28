# Đóng context, kết nối và executor khi kết thúc

Một command Spring Shell có thể kết thúc sau vài giây, nhưng tiến trình Java vẫn còn sống vì connection pool, HTTP client, scheduler hoặc executor chưa được dừng. Ngược lại, nếu đóng `ApplicationContext` quá sớm, command đang chạy có thể mất repository, connection hoặc service mà nó cần để hoàn tất.

Quản lý shutdown đúng nghĩa là xác định ai sở hữu từng tài nguyên, ngừng nhận công việc mới, chờ công việc đang chạy kết thúc trong thời hạn hợp lý rồi đóng tài nguyên theo thứ tự phụ thuộc. Spring Framework cung cấp lifecycle callbacks, `Lifecycle` và `SmartLifecycle`; Spring Boot đăng ký shutdown hook cho application context và hỗ trợ cấu hình executor. Bài viết áp dụng các cơ chế đó cho CLI chạy một lần, REPL tương tác và tác vụ nền.

## 1. Một lần shutdown gồm những giai đoạn nào?

Khi người dùng kết thúc CLI hoặc hệ điều hành gửi tín hiệu dừng, ứng dụng cần thực hiện các bước có thứ tự:

```text
Người dùng gõ quit / process nhận SIGTERM
                 |
                 v
       Ngừng nhận command mới
                 |
                 v
       Ngừng tạo task/schedule mới
                 |
                 v
       Chờ task đang chạy hoàn tất
          hoặc hủy khi hết hạn
                 |
                 v
       Đóng client, connection pool,
       executor và resource của bean
                 |
                 v
       Spring ApplicationContext đóng
                 |
                 v
            JVM kết thúc
```

Không phải mọi CLI đều cần một quy trình shutdown phức tạp. Một command chạy đồng bộ, không tạo thread nền và chỉ dùng các bean Spring-managed thường có thể dựa vào shutdown hook mặc định. Nhưng khi command khởi chạy import/export nền, mở socket, tạo executor hoặc giữ connection pool, cần thiết kế lifecycle rõ ràng.

## 2. Phân biệt context, bean và resource

`ApplicationContext` là container sở hữu các singleton bean. Khi context đóng, Spring gọi các callback hủy bean theo lifecycle. Từng bean có thể sở hữu một hoặc nhiều tài nguyên:

| Đối tượng | Ví dụ | Ai nên đóng? |
|---|---|---|
| `ApplicationContext` | Container của Spring Shell/Spring Boot | Bootstrap code hoặc shutdown hook do Spring đăng ký |
| Connection đang mượn | JDBC `Connection` lấy từ pool | Code mở connection hoặc Spring transaction infrastructure |
| Connection pool | HikariCP `DataSource` | Spring bean sở hữu pool |
| HTTP client/socket | `CloseableHttpClient`, client kết nối broker | Bean tạo và sở hữu client |
| Executor | `ThreadPoolTaskExecutor`, `ExecutorService` | Spring bean hoặc component tạo executor |
| Scheduled task | `ScheduledFuture`, polling loop | Component sở hữu task và scheduler |
| File/stream theo command | `InputStream`, `Reader`, `Writer` | Command/service mở tài nguyên đó |

Nguyên tắc quan trọng là một tài nguyên chỉ có một nơi chịu trách nhiệm đóng. Nếu Spring đã quản lý lifecycle của bean, không đóng cùng bean đó thêm lần nữa từ command hoặc một bean khác.

## 3. Spring Boot đã đăng ký shutdown hook

Với ứng dụng khởi động bằng `SpringApplication.run(...)`, Spring Boot đăng ký shutdown hook cho `ApplicationContext` theo mặc định. Khi JVM đi vào quá trình shutdown bình thường, hook gọi đóng context; Spring sau đó gọi lifecycle stop và destruction callbacks của singleton bean.

Ví dụ main thông thường:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogCliApplication.class, args);
    }
}
```

Với cách khởi động này, không cần tự thêm một shutdown hook khác để gọi `context.close()`. Hai hook cùng đóng một context có thể gây khó hiểu về thứ tự và lỗi đóng lặp.

Shutdown hook xử lý việc JVM kết thúc bình thường, chẳng hạn người dùng nhấn Ctrl+C hoặc process nhận tín hiệu dừng mà JVM xử lý. Nó không thể chạy khi process bị kết thúc cưỡng bức như `kill -9`, `Runtime.halt()` hoặc máy mất điện. Vì vậy, dữ liệu quan trọng vẫn phải được ghi/checkpoint thường xuyên; không để tính toàn vẹn của dữ liệu phụ thuộc hoàn toàn vào hook cuối cùng.

## 4. Khi tự tạo ApplicationContext, phải đóng context do mình sở hữu

Nếu tạo Spring context trực tiếp thay vì dùng `SpringApplication.run`, hãy đóng nó bằng `try-with-resources` hoặc đăng ký shutdown hook. Ví dụ dùng `AnnotationConfigApplicationContext`:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class StandaloneCliLauncher {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(CliConfiguration.class)) {
            context.getBean(CliJob.class).run(args);
        }
    }
}
```

`AnnotationConfigApplicationContext` triển khai `AutoCloseable`, nên khi thoát khỏi khối `try`, context được đóng và các bean singleton nhận destruction callback.

Nếu ứng dụng phải sống sau khi `main()` trả về, có thể gọi `context.registerShutdownHook()` thay cho việc đóng ngay. Không dùng cả hai cách một cách máy móc: chọn một bên sở hữu vòng đời context.

Với Spring Boot, nếu launcher cần tự quyết định thời điểm đóng context, có thể tắt hook mặc định và đóng context trong `try`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

public class OneShotLauncher {

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(CatalogCliApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setRegisterShutdownHook(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            // Spring Shell runner hoặc ApplicationRunner xử lý command trong quá trình run.
            // Context sẽ đóng khi launcher thoát khỏi khối try.
        }
    }
}
```

Chỉ dùng cách này khi launcher thực sự sở hữu context. Không tắt shutdown hook nếu không có code khác bảo đảm context sẽ được đóng. Với ứng dụng REPL, context phải sống trong toàn bộ phiên shell và chỉ đóng sau khi phiên kết thúc.

## 5. Không đóng ApplicationContext từ một command thông thường

Một command Spring Shell là một lần thực thi bên trong ứng dụng. Trong interactive mode, sau khi command trả kết quả, shell còn tiếp tục nhận lệnh khác. Nếu command tự gọi `applicationContext.close()`, các bean khác có thể bị hủy trong khi shell vẫn đang chạy.

Ví dụ không nên làm:

```java
@Command
public String importData() {
    importService.run();
    applicationContext.close(); // Đóng toàn bộ ứng dụng từ giữa command
    return "Done";
}
```

Hãy để command trả kết quả và để shell runner/launcher điều khiển thời điểm process kết thúc. Chỉ một thành phần ở tầng bootstrap hoặc lifecycle của ứng dụng mới nên sở hữu thao tác đóng context.

Nếu cần một command `quit`, command đó nên yêu cầu shell dừng vòng lặp theo cơ chế của runner. Sau khi runner kết thúc, JVM/launcher mới đóng context và resource. Không biến một command nghiệp vụ như `import`, `export` hoặc `status` thành nơi quản lý lifecycle toàn ứng dụng.

## 6. Dùng `@PreDestroy` cho cleanup của bean

Spring khuyến nghị `@PreDestroy` cho công việc dọn dẹp vì class không phải implement interface Spring-specific. Khi context đóng, Spring gọi method này cho singleton bean trước khi hoàn tất destruction.

```java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class TemporaryWorkspace {

    private final Path workingDirectory;

    public TemporaryWorkspace(WorkspaceProperties properties) {
        this.workingDirectory = properties.workingDirectory();
    }

    @PreDestroy
    void cleanup() {
        // Xóa file tạm do bean này tạo và sở hữu.
    }
}
```

`@PreDestroy` phù hợp để:

- Hủy subscription hoặc listener do bean đăng ký.
- Dừng polling loop do bean sở hữu.
- Xóa file tạm hoặc giải phóng lock do bean tạo.
- Đóng client ngoài mà bean tự khởi tạo và quản lý.
- Ghi checkpoint cuối cùng nếu thao tác đó có giới hạn thời gian và an toàn.

Không dùng callback này để thực hiện công việc kéo dài, cần người dùng nhập hoặc phụ thuộc vào một bean đã bị đóng. Cleanup nên ngắn, có timeout và có thể chạy an toàn khi khởi động thất bại một phần.

Với Spring Framework 6/7 và Spring Boot 3/4, dùng `jakarta.annotation.PreDestroy`. Dự án Spring cũ dùng `javax.annotation.PreDestroy`; import phải phù hợp với major version đang chạy.

## 7. `@Bean(destroyMethod)` và đóng tài nguyên tự động

Khi khai báo bean bằng Java configuration, Spring mặc định suy luận public method `close()` hoặc `shutdown()` để làm destruction callback. Vì vậy, một bean triển khai `AutoCloseable` hoặc có public `close()` thường được đóng khi context đóng.

Ví dụ client do ứng dụng sở hữu:

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient apiHttpClient() {
        return HttpClients.custom()
                .setConnectionManagerShared(false)
                .build();
    }
}
```

Có thể bỏ `destroyMethod = "close"` nếu muốn dùng cơ chế suy luận mặc định, nhưng khai báo rõ giúp người đọc thấy bean này sở hữu client và phải đóng nó.

Nếu resource được quản lý bên ngoài, không để Spring đóng nhầm. Ví dụ một `DataSource` lấy từ JNDI có vòng đời do application server quản lý:

```java
@Bean(destroyMethod = "")
DataSource dataSource() throws NamingException {
    return (DataSource) new InitialContext().lookup("java:comp/env/jdbc/catalog");
}
```

`destroyMethod = ""` tắt cơ chế suy luận `close()`/`shutdown()`. Dùng nó cho resource có lifecycle do container bên ngoài sở hữu; không áp dụng cho connection pool do chính ứng dụng tạo.

Không cấu hình cả `@PreDestroy` gọi `client.close()` và `@Bean(destroyMethod = "close")` cho cùng một object nếu cả hai callback cùng thực hiện một lần đóng. Chọn một cơ chế duy nhất.

## 8. Quản lý JDBC Connection và DataSource đúng phạm vi

`DataSource` là connection factory, thường bao bọc connection pool. Nó có vòng đời dài bằng application context. Một JDBC `Connection` được mượn từ pool lại có vòng đời ngắn: thường chỉ trong một thao tác hoặc transaction.

Khi dùng JDBC thuần ngoài Spring transaction, đóng connection bằng try-with-resources:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "select count(*) from customer")) {
    try (ResultSet resultSet = statement.executeQuery()) {
        resultSet.next();
        return resultSet.getLong(1);
    }
}
```

Với `JdbcTemplate` hoặc Spring Data, để framework quản lý việc lấy/trả connection. `JdbcTemplate` và `DataSourceUtils` phối hợp với transaction manager, giữ connection gắn với transaction và giải phóng đúng lúc.

Nếu phải dùng `DataSourceUtils` trực tiếp, gọi `releaseConnection()` trong `finally`:

```java
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    // Thực hiện JDBC operation; connection có thể đang gắn với transaction.
}
finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

Không gọi `connection.close()` tùy tiện trên connection do `DataSourceUtils` lấy trong transaction. `releaseConnection()` biết connection có đang được transaction giữ hay không.

Không giữ `Connection` trong field của singleton bean hoặc mở connection trong constructor rồi giữ đến khi context đóng. Cách đó làm cạn pool, gây rò connection khi command lỗi và phá vỡ quản lý transaction.

## 9. Đóng connection pool khi context đóng

Nếu dùng HikariCP hoặc pool khác do ứng dụng tạo, để pool là Spring bean. Spring Boot auto-configured `DataSource` sẽ được quản lý cùng application context. Khi context đóng, pool đóng và giải phóng các physical connection.

Ví dụ tự khai báo Hikari pool:

```java
@Configuration(proxyBeanMethods = false)
public class DatabaseConfiguration {

    @Bean(destroyMethod = "close")
    HikariDataSource dataSource(DataSourceProperties properties) {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(properties.getUrl());
        config.setUsername(properties.getUsername());
        config.setPassword(properties.getPassword());
        config.setMaximumPoolSize(8);
        config.setPoolName("catalog-cli-pool");
        return new HikariDataSource(config);
    }
}
```

Trong ứng dụng thực tế, nên dùng cấu hình `spring.datasource.*` và auto-configuration của Spring Boot nếu không có yêu cầu đặc biệt. Ví dụ trên minh họa ownership: bean tạo pool, nên bean/context đóng pool.

Đừng gọi `dataSource.close()` sau mỗi command. Đóng pool khi toàn bộ ứng dụng kết thúc, không phải khi một command hoặc một transaction kết thúc. Với JNDI DataSource, lifecycle thuộc application server và cần tắt destroy inference như phần trước.

## 10. Đóng HTTP client, broker client và file resource

Các client kết nối bên ngoài cũng nên được khai báo thành bean nếu dùng xuyên suốt nhiều command. Khi đó, một bean sở hữu client và Spring đóng nó lúc context shutdown.

Ví dụ client có `close()`:

```java
@Configuration(proxyBeanMethods = false)
public class RemoteClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient partnerClient() {
        return HttpClients.createDefault();
    }
}
```

Nếu command chỉ mở file hoặc stream trong một lần chạy, dùng try-with-resources trong command/service thay vì giữ resource đến khi context đóng:

```java
public ImportSummary importFile(Path file) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(file)) {
        return importService.importRows(reader);
    }
}
```

Phân biệt rõ:

- Resource ngắn hạn của một command: đóng khi command kết thúc.
- Client/pool dùng chung của ứng dụng: đóng khi context kết thúc.
- Resource do application server hoặc container khác sở hữu: không tự đóng nếu hợp đồng lifecycle không giao quyền cho ứng dụng.

## 11. Dừng Executor trước khi đóng các dependency

Executor có thể còn task đang chạy khi người dùng yêu cầu thoát. Nếu đóng database pool hoặc HTTP client trước khi task hoàn tất, task đang chạy có thể thất bại khi truy cập dependency đã đóng.

Một trình tự hợp lý:

1. Ngừng nhận command hoặc job mới.
2. Ngừng scheduler/poller phát sinh task mới.
3. Gọi `shutdown()` để executor từ chối task mới nhưng cho task đã nhận chạy tiếp.
4. Chờ trong thời hạn xác định.
5. Nếu hết hạn, gọi `shutdownNow()` để gửi interrupt tới task đang chạy và lấy các task còn trong queue.
6. Sau khi worker dừng, đóng HTTP client, connection pool và resource mà worker sử dụng.

Task nền phải có điểm kiểm tra interrupt và timeout cho I/O. `shutdownNow()` chỉ gửi interrupt; nó không thể buộc một task bỏ qua interrupt hoặc đang mắc kẹt trong native call phải kết thúc ngay lập tức.

## 12. Dùng ThreadPoolTaskExecutor do Spring quản lý

Với task executor dùng chung, ưu tiên `ThreadPoolTaskExecutor` được khai báo thành bean. Spring quản lý khởi tạo và shutdown của executor.

```java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class CliExecutorConfiguration {

    @Bean("cliWorkerExecutor")
    ThreadPoolTaskExecutor cliWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("cli-worker-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
```

Không gọi `initialize()` trong factory method: Spring gọi lifecycle initialization cho bean sau khi tạo. Cũng không cần thêm `@PreDestroy` gọi `shutdown()` lần nữa; `ThreadPoolTaskExecutor` đã có lifecycle management.

`setWaitForTasksToCompleteOnShutdown(true)` yêu cầu executor chờ task đã nhận hoàn tất trong giai đoạn shutdown. `setAwaitTerminationSeconds(20)` giới hạn thời gian chờ. Chọn timeout dựa trên thời lượng task và thời gian process manager cho phép; không để một tác vụ không giới hạn giữ process mãi mãi.

## 13. Khi tự tạo ExecutorService trong một bean

Nếu bean tự tạo executor riêng và không chia sẻ nó với Spring executor khác, bean đó phải tự đóng executor của mình. Ví dụ:

```java
import jakarta.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

@Component
public class LocalExportWorker {

    private final ExecutorService executor = Executors.newFixedThreadPool(2);

    public void submit(Runnable task) {
        executor.submit(task);
    }

    @PreDestroy
    void shutdown() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(20, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
        catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

`shutdown()` ngừng nhận task mới nhưng vẫn cho task đã submit hoàn tất. Nếu hết 20 giây, `shutdownNow()` yêu cầu interrupt. Khi thread gọi shutdown bị interrupt, code khôi phục interrupt flag sau khi gửi yêu cầu dừng.

Nếu executor là bean riêng, có thể để Spring suy luận `shutdown()` làm destroy method hoặc khai báo `@Bean(destroyMethod = "shutdown")`. Khi cần chờ task hoàn tất, dùng một abstraction hỗ trợ await termination như `ThreadPoolTaskExecutor` hoặc một bean lifecycle riêng. Không để hai bean cùng sở hữu một `ExecutorService` rồi cùng đóng nó.

## 14. SmartLifecycle cho worker cần dừng theo phase

`@PreDestroy` phù hợp với cleanup ngắn sau khi context bắt đầu hủy bean. Với một worker chạy nền cần ngừng nhận việc, hoàn tất công việc đang xử lý và báo lại khi đã dừng, `SmartLifecycle` cung cấp giao thức stop bất đồng bộ:

- `isAutoStartup()` xác định worker có tự khởi động khi context refresh hay không.
- `start()` bắt đầu worker.
- `stop(Runnable callback)` yêu cầu worker dừng và gọi callback sau khi thực sự dừng.
- `getPhase()` quy định thứ tự start/stop tương đối với các bean lifecycle khác.

Phase nhỏ được start trước và stop sau; phase lớn được start sau và stop trước. Ví dụ scheduler tạo task cho worker: scheduler nên dừng nhận lịch mới trước, sau đó worker hoàn tất queue, cuối cùng connection pool được đóng.

Trong `stop(Runnable callback)`, không gọi callback ngay khi mới gửi tín hiệu dừng nếu worker vẫn còn đang chạy. Chỉ gọi callback sau khi worker đã hoàn tất hoặc đã hủy theo chính sách. Lifecycle processor chờ callback trong thời hạn cho mỗi phase; nếu callback không được gọi, shutdown sẽ phải chờ đến timeout.

`Lifecycle` thông thường chỉ cung cấp `start()`/`stop()` đồng bộ và không tự động start ở thời điểm refresh. Dùng `SmartLifecycle` khi cần auto-start, phase ordering và stop có thời hạn. Không triển khai `SmartLifecycle` chỉ để đóng một file đơn giản; `@PreDestroy` hoặc `@Bean(destroyMethod=...)` là đủ.

## 15. Cấu hình timeout shutdown

Spring Framework `DefaultLifecycleProcessor` chờ các `SmartLifecycle` bean trong từng phase. Spring Boot cho phép cấu hình timeout:

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Timeout này áp dụng cho mỗi shutdown phase, không phải một giới hạn tổng duy nhất cho toàn bộ shutdown. Nếu có nhiều phase, thời gian chờ cộng dồn có thể dài hơn một giá trị timeout.

Spring Boot còn có graceful shutdown cho embedded web server. Cơ chế đó dành cho ứng dụng web: ngừng nhận request mới và chờ request đang xử lý trong grace period. CLI non-web không có web server để drain request; cần tập trung vào shell session, worker, executor và tài nguyên mà ứng dụng tự tạo.

Hãy phối hợp timeout của Spring với timeout của systemd, container orchestrator hoặc service manager. Nếu process manager chỉ cho 10 giây nhưng Spring chờ 30 giây, process có thể bị kill trước khi cleanup hoàn tất.

## 16. Xử lý lệnh quit và tín hiệu dừng trong CLI

Trong interactive shell, lệnh `quit`/`exit` yêu cầu shell kết thúc vòng lặp. Sau khi runner kết thúc, ứng dụng mới bước vào giai đoạn đóng context. Không nên đóng connection pool hoặc executor ngay trong command `quit` nếu shell còn cần các bean đó để ghi thông báo cuối hoặc hoàn tất runner.

Với CLI non-interactive chạy một command rồi thoát, `SpringApplication.run(...)` thường trả context sau khi runner hoàn tất. Khi `main()` trả về và JVM shutdown, hook mặc định đóng context. Nếu có non-daemon thread nền, JVM vẫn có thể sống; khi đó phải dừng worker hoặc chọn chế độ một lần có quyền sở hữu context rõ ràng.

Khi nhận `SIGTERM`, nên ngừng nhận việc mới và chạy lifecycle shutdown. Tránh bắt signal rồi gọi `Runtime.halt()` hoặc `System.exit()` từ một thread worker trước khi Spring hoàn tất cleanup. `System.exit()` khởi động quá trình JVM shutdown và hook có thể chạy; `Runtime.halt()` bỏ qua shutdown hook và destruction callbacks.

## 17. Kiểm thử việc đóng context và resource

Nên kiểm thử callback cleanup ở mức Spring context, không chỉ kiểm tra command in ra “Goodbye”.

Ví dụ xác nhận `@PreDestroy` được gọi khi context đóng:

```java
import jakarta.annotation.PreDestroy;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ContextShutdownTests {

    @Test
    void callsDestroyCallbackWhenContextCloses() {
        try (var context = new AnnotationConfigApplicationContext(TestConfig.class)) {
            CleanupProbe probe = context.getBean(CleanupProbe.class);
            assertThat(probe.isClosed()).isFalse();
        }
        // Context đã đóng sau khi thoát try-with-resources.
        assertThat(CleanupProbe.closed.get()).isTrue();
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {
        @Bean
        CleanupProbe cleanupProbe() {
            return new CleanupProbe();
        }
    }

    static class CleanupProbe {
        static final AtomicBoolean closed = new AtomicBoolean();

        @PreDestroy
        void close() {
            closed.set(true);
        }

        boolean isClosed() {
            return closed.get();
        }
    }
}
```

Trong test suite thực tế, reset static state trước mỗi test hoặc dùng probe instance được giữ lại để tránh test phụ thuộc thứ tự.

Ma trận kiểm thử nên gồm:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Đóng context bình thường | `@PreDestroy` và destroy method được gọi |
| Command đang chạy khi nhận quit | Command được kết thúc hoặc hủy theo timeout |
| Executor có queue | Task đã nhận được xử lý hoặc được báo là bị hủy |
| Task không kết thúc đúng hạn | Timeout được kích hoạt và interrupt được gửi |
| DataSource pool | Pool đóng một lần sau khi worker đã dừng |
| JNDI DataSource | Spring không đóng resource do container ngoài sở hữu |
| HTTP/broker client | Client được đóng sau khi task không còn dùng |
| Context test cache | Test không tự đóng context do Spring TestContext quản lý |
| SIGTERM | Shutdown hook/lifecycle chạy và process thoát trong grace period |
| SIGKILL hoặc process crash | Không giả định cleanup callback sẽ chạy; checkpoint bảo vệ dữ liệu |

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| JVM không thoát sau khi command hoàn tất | Executor, scheduler hoặc thread non-daemon vẫn chạy | Dừng worker và đóng executor khi context shutdown |
| Command kế tiếp lỗi sau khi chạy `quit` | Command nghiệp vụ đã đóng context quá sớm | Chỉ launcher/runner sở hữu thao tác đóng context |
| Connection pool đóng hai lần | `@PreDestroy` và destroy method cùng đóng một pool | Chọn một lifecycle owner và một callback |
| Connection bị rò | Mở JDBC connection nhưng không release trong mọi nhánh | Dùng JdbcTemplate hoặc try-with-resources đúng phạm vi |
| Transaction lỗi sau khi đóng connection | Đóng connection do transaction manager đang giữ | Dùng `DataSourceUtils.releaseConnection()` hoặc JdbcTemplate |
| Worker mất kết nối khi đang hoàn tất | Pool/client đóng trước executor | Dừng producer, chờ worker, rồi đóng dependency |
| Shutdown chờ vô hạn | Task block I/O không có timeout hoặc bỏ qua interrupt | Đặt timeout I/O, kiểm tra interrupt và giới hạn thời gian chờ |
| Task bị mất khi thoát | `shutdownNow()` hủy task đang queue mà không lưu checkpoint | Dùng `shutdown()` trước, checkpoint và xử lý task bị hủy rõ ràng |
| JNDI DataSource bị đóng ngoài ý muốn | Spring suy luận `close()` cho resource do server quản lý | Khai báo `@Bean(destroyMethod = "")` |
| Cleanup không chạy khi kill process | Process bị kết thúc cưỡng bức | Dùng shutdown bình thường và lưu tiến độ định kỳ |
| `SmartLifecycle` shutdown timeout | `stop(Runnable)` không gọi callback | Gọi callback sau khi worker thực sự dừng |
| Test đóng nhầm context dùng chung | Tự gọi `close()` trên context do test framework cache | Để Spring TestContext quản lý hoặc dùng `@DirtiesContext` đúng phạm vi |

## 19. Checklist trước khi phát hành CLI

- [ ] Đã xác định thành phần nào sở hữu `ApplicationContext`.
- [ ] Spring Boot shutdown hook được giữ bật nếu launcher không tự đóng context.
- [ ] Không command nghiệp vụ nào tự đóng context dùng chung.
- [ ] Mỗi resource có đúng một nơi chịu trách nhiệm đóng.
- [ ] `@PreDestroy` hoặc `@Bean(destroyMethod)` được dùng cho bean cần cleanup.
- [ ] Resource do JNDI/application server quản lý không bị Spring đóng nhầm.
- [ ] JDBC connection được trả về pool sau từng operation/transaction.
- [ ] DataSource pool chỉ đóng khi context kết thúc.
- [ ] HTTP/broker client được đóng sau khi task sử dụng chúng đã dừng.
- [ ] Scheduler ngừng phát task mới trước khi executor kết thúc.
- [ ] Executor có chính sách chờ, timeout và xử lý interrupt rõ ràng.
- [ ] Worker dài hạn dùng `SmartLifecycle` nếu cần phase ordering và async stop.
- [ ] Timeout Spring phù hợp với timeout của service manager/container.
- [ ] Có test xác nhận callback destroy, executor termination và pool lifecycle.
- [ ] Có checkpoint để bảo vệ dữ liệu khi process bị kill đột ngột.

## Tài liệu tham khảo

1. [Spring Framework – Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html) – `@PreDestroy`, destroy method inference, `Lifecycle`, `SmartLifecycle` và shutdown hook.
2. [Spring Framework – Using the `@Bean` Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html) – lifecycle callbacks và `destroyMethod`.
3. [Spring Framework – Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html) – `DataSource`, `DataSourceUtils`, connection pool và transaction-aware connection.
4. [Spring Boot – Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html) – executor/scheduler auto-configuration và `ThreadPoolTaskExecutor`.
5. [Spring Boot – `SpringApplication` API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/SpringApplication.html) – `setRegisterShutdownHook` và shutdown hook mặc định.
6. [Spring Boot – Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html) – graceful shutdown của embedded web server và timeout theo phase.

Một CLI kết thúc an toàn khi mọi công việc mới đã được chặn, task đang chạy đã hoàn tất hoặc được hủy có kiểm soát, rồi resource được đóng theo đúng thứ tự sở hữu và phụ thuộc. Hãy để Spring quản lý lifecycle của bean, đóng connection theo từng operation, chờ executor trong giới hạn thời gian và chỉ để launcher hoặc shutdown hook đóng `ApplicationContext`.
