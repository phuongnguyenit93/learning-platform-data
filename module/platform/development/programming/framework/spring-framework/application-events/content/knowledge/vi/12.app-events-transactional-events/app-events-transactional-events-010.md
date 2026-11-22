# Tài nguyên transaction ở thời điểm listener chạy

## 1. Tài nguyên transaction được gắn với thread

Spring transaction management thường gắn tài nguyên đang sử dụng với thread hiện tại thông qua `TransactionSynchronizationManager`. Ví dụ, `DataSourceTransactionManager` gắn `ConnectionHolder` của `DataSource`; JPA transaction manager có thể gắn `EntityManagerHolder` của `EntityManagerFactory`. Nhờ đó, `JdbcTemplate` hoặc `EntityManager` lấy đúng tài nguyên đang tham gia transaction mà không cần truyền connection qua từng lời gọi method.

Trạng thái này có phạm vi theo thread. Một thread có thể có transaction đang hoạt động, transaction synchronization đang được đăng ký và các resource holder tương ứng. Khi transaction hoàn tất, Spring gọi các synchronization callback rồi mới dọn resource khỏi thread.

Điều đó ảnh hưởng trực tiếp tới `@TransactionalEventListener`: listener chạy ở phase nào thì cần hiểu transaction và resource đang ở trạng thái nào tại phase đó. Đặc biệt, sau commit hoặc rollback, resource có thể vẫn còn được gắn với thread trong lúc callback chạy, dù kết quả transaction đã được quyết định.

## 2. Resource ở từng phase

`@TransactionalEventListener` hỗ trợ bốn phase. Resource holder có thể vẫn được bind trong suốt quá trình callback; điều quan trọng là transaction đã ở trạng thái nào và còn có lần commit nào tiếp theo hay không.

| Phase | Trạng thái transaction | Cách dùng resource phù hợp |
|---|---|---|
| `BEFORE_COMMIT` | Transaction vẫn đang hoạt động, chưa commit. | Có thể dùng JDBC/JPA để tham gia transaction hiện tại. Thay đổi được commit hoặc rollback cùng transaction gốc. |
| `AFTER_COMMIT` | Commit đã thành công; Spring vẫn có thể giữ resource gắn với thread cho tới khi callback hoàn tất và cleanup chạy. | Đọc dữ liệu đã commit được. Nếu cần ghi dữ liệu mới, mở transaction độc lập như `REQUIRES_NEW`. |
| `AFTER_ROLLBACK` | Transaction đã rollback; resource có thể vẫn được bind trong callback trước cleanup. | Không ghi qua resource của transaction đã rollback với kỳ vọng dữ liệu sẽ được commit. Mở transaction mới nếu cần lưu kết quả xử lý. |
| `AFTER_COMPLETION` | Transaction đã kết thúc, bất kể commit hay rollback; cleanup resource diễn ra sau callback. | Dùng để quan sát hoặc dọn dẹp. Nếu cần ghi database, dùng transaction mới. |

`AFTER_COMMIT` là phase mặc định. Một điểm dễ nhầm là resource còn bind không có nghĩa transaction vẫn có thể commit thêm lần nữa. Khi callback sau commit chạy, transaction gốc đã kết thúc về mặt kết quả. Các lệnh ghi dùng resource cũ có thể chạy trên connection đó nhưng không có lần commit tiếp theo để lưu thay đổi.

## 3. TransactionSynchronizationManager dùng để kiểm tra điều gì?

`TransactionSynchronizationManager` cung cấp các phương thức chẩn đoán trạng thái trên thread hiện tại:

| Phương thức | Ý nghĩa |
|---|---|
| `isActualTransactionActive()` | Thread hiện tại đang được đánh dấu có transaction thực tế hay không. |
| `isSynchronizationActive()` | Có transaction synchronization đang hoạt động để đăng ký callback hay không. |
| `hasResource(key)` | Có resource holder đang bind với key, ví dụ một `DataSource`, hay không. |
| `getResource(key)` | Lấy resource holder đang bind với key. Chỉ nên dùng trong tích hợp hạ tầng khi hiểu rõ vòng đời holder. |
| `getResourceMap()` | Xem các resource đang bind trên thread; hữu ích khi chẩn đoán, nhưng không nên log toàn bộ object holder vào log ứng dụng. |

Ví dụ kiểm tra một `DataSource` cụ thể:

```java
boolean active = TransactionSynchronizationManager.isActualTransactionActive();
boolean synchronization = TransactionSynchronizationManager.isSynchronizationActive();
boolean bound = TransactionSynchronizationManager.hasResource(dataSource);

System.out.printf(
    "active=%s, synchronization=%s, dataSourceBound=%s%n",
    active, synchronization, bound
);
```

Đây là thông tin của thread đang gọi đoạn code. Nó không phải trạng thái toàn cục của ứng dụng. `hasResource(dataSource)` cũng cần đúng key mà transaction manager sử dụng; truyền một wrapper hoặc một `DataSource` instance khác có thể trả về `false` dù ứng dụng đang có transaction trên datasource được quản lý.

Không tự gọi `unbindResource`, `releaseConnection` hoặc đóng connection mà Spring đang quản lý. Transaction manager chịu trách nhiệm bind, commit/rollback và cleanup. Tự tháo holder hoặc đóng connection có thể làm hỏng transaction hiện tại.

## 4. Ví dụ chạy được với Java 17

Ví dụ sử dụng Spring Context, Spring JDBC và H2. Service ghi đơn hàng và phát event trong `TransactionTemplate`. Listener quan sát trạng thái transaction và việc `DataSource` đang được bind ở `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Sau khi transaction kết thúc, chương trình kiểm tra lại trạng thái trên thread gọi.

### Cấu trúc thư mục

```text
transaction-resource-lifecycle/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── App.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-resource-lifecycle</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.0</spring-framework.version>
        <h2.version>2.3.232</h2.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>${h2.version}</version>
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
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### src/main/java/demo/App.java

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class App {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            var jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("create table orders (id varchar(40) primary key)");

            var service = context.getBean(OrderService.class);
            service.create("ORD-COMMIT", false);
            service.create("ORD-ROLLBACK", true);

            printState("AFTER_TRANSACTION", context.getBean(DataSource.class));

            Integer count = jdbc.queryForObject(
                "select count(*) from orders", Integer.class
            );
            System.out.println("committed orders=" + count);
        }
    }

    static void printState(String label, DataSource dataSource) {
        System.out.printf(
            "%s active=%s synchronization=%s resourceBound=%s%n",
            label,
            TransactionSynchronizationManager.isActualTransactionActive(),
            TransactionSynchronizationManager.isSynchronizationActive(),
            TransactionSynchronizationManager.hasResource(dataSource)
        );
    }

    @Configuration
    static class AppConfig {

        @Bean
        DataSource dataSource() {
            var dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl("jdbc:h2:mem:txresources;DB_CLOSE_DELAY=-1");
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
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                TransactionTemplate transaction,
                ApplicationEventPublisher publisher,
                DataSource dataSource) {
            return new OrderService(jdbc, transaction, publisher, dataSource);
        }

        @Bean
        ResourceListener resourceListener(DataSource dataSource) {
            return new ResourceListener(dataSource);
        }
    }

    static class OrderService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transaction;
        private final ApplicationEventPublisher publisher;
        private final DataSource dataSource;

        OrderService(
                JdbcTemplate jdbc,
                TransactionTemplate transaction,
                ApplicationEventPublisher publisher,
                DataSource dataSource) {
            this.jdbc = jdbc;
            this.transaction = transaction;
            this.publisher = publisher;
            this.dataSource = dataSource;
        }

        void create(String id, boolean rollback) {
            transaction.execute(status -> {
                jdbc.update("insert into orders(id) values (?)", id);
                printState("INSIDE_TRANSACTION " + id, dataSource);
                publisher.publishEvent(new OrderChanged(id));
                if (rollback) {
                    status.setRollbackOnly();
                }
                return null;
            });
        }

    }

    static class ResourceListener {
        private final DataSource dataSource;

        ResourceListener(DataSource dataSource) {
            this.dataSource = dataSource;
        }

        private void inspect(String phase, OrderChanged event) {
            System.out.printf(
                "%s %s active=%s synchronization=%s resourceBound=%s%n",
                phase,
                event.orderId(),
                TransactionSynchronizationManager.isActualTransactionActive(),
                TransactionSynchronizationManager.isSynchronizationActive(),
                TransactionSynchronizationManager.hasResource(dataSource)
            );
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void beforeCommit(OrderChanged event) {
            inspect("BEFORE_COMMIT", event);
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderChanged event) {
            inspect("AFTER_COMMIT", event);
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderChanged event) {
            inspect("AFTER_ROLLBACK", event);
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void afterCompletion(OrderChanged event) {
            inspect("AFTER_COMPLETION", event);
        }
    }

    public record OrderChanged(String orderId) {
    }
}
```

Trong ví dụ, `DataSource` được inject trực tiếp vào `OrderService` và dùng làm key khi kiểm tra `TransactionSynchronizationManager.hasResource(dataSource)`. Vì vậy, phần kiểm tra sử dụng đúng datasource mà `DataSourceTransactionManager` đang quản lý.

### Chạy chương trình

Đứng tại thư mục chứa `pom.xml` và chạy:

```bash
mvn -q compile exec:java
```

Trong mỗi callback phase, `resourceBound` có thể vẫn là `true` vì Spring chỉ cleanup resource sau khi hoàn tất các synchronization callback. Với `AFTER_COMMIT`, transaction đã commit dù holder còn bind. Sau khi `TransactionTemplate.execute` trả về, Spring đã cleanup và trạng thái thread trở về không có transaction.

## 5. Vì sao ghi trong AFTER_COMMIT cần transaction mới?

Spring gọi `AFTER_COMMIT` sau khi commit của transaction gốc đã hoàn tất, nhưng trước khi cleanup resource khỏi thread. Vì vậy, một lệnh JDBC/JPA trong callback có thể tìm thấy connection/entity manager đang bind. Sự hiện diện của resource chỉ cho biết holder vẫn còn trong thread; nó không mở lại transaction gốc và không tạo một lần commit tiếp theo.

Nếu listener cần ghi dữ liệu mới, hãy gọi một service riêng dùng `PROPAGATION_REQUIRES_NEW`:

```java
@Service
public class AuditWriter {
    private final AuditRepository repository;

    public AuditWriter(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId) {
        repository.insert(orderId, "ORDER_CREATED");
    }
}

@Component
public class OrderListener {
    private final AuditWriter auditWriter;

    public OrderListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderChanged event) {
        auditWriter.record(event.orderId());
    }
}
```

Service `AuditWriter` là bean riêng để lời gọi đi qua proxy transaction của Spring. Không gọi `this.record(...)` từ cùng object vì self-invocation không kích hoạt proxy. Transaction mới có thể commit độc lập; nếu nó thất bại, transaction nghiệp vụ ban đầu vẫn đã commit và cần xử lý lỗi theo chính sách riêng.

## 6. Resource không tự truyền sang thread bất đồng bộ

Transaction resource của Spring thường được lưu trong `ThreadLocal`. Vì vậy, khi một listener chạy qua `@Async` trên executor, thread worker không kế thừa resource holder hay transaction synchronization của thread phát event.

Không nên lấy `ConnectionHolder`, `EntityManagerHolder` hoặc transaction context từ thread phát event rồi chuyển sang thread khác. Nếu công việc async cần truy cập database, hãy để worker gọi một service mở transaction phù hợp trên chính thread worker. Ví dụ, một phương thức `@Transactional` trong bean riêng sẽ bắt đầu transaction mới khi được gọi qua proxy.

```java
@Component
public class AsyncOrderListener {
    private final OrderReadService readService;

    public AsyncOrderListener(OrderReadService readService) {
        this.readService = readService;
    }

    @Async("applicationEventExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderChanged event) {
        readService.loadCommittedOrder(event.orderId());
    }
}

@Service
public class OrderReadService {
    @Transactional(readOnly = true)
    public Order loadCommittedOrder(String orderId) {
        // Đọc bằng transaction trên thread executor.
        return repository.findById(orderId).orElseThrow();
    }
}
```

Trong ví dụ này, callback transaction-bound được kích hoạt sau commit; `@Async` chuyển phần thực thi listener sang executor. `OrderReadService` mở transaction đọc riêng trên thread worker. Cấu hình `@EnableAsync`, transaction management và executor phải được bật trong context phù hợp.

## 7. `fallbackExecution` và trường hợp không có transaction

Mặc định, `@TransactionalEventListener` chỉ đăng ký khi event được phát trong transaction đang hoạt động. Nếu không có transaction, listener không được gọi.

Khi bật `fallbackExecution = true`, listener có thể chạy ngay cả khi không có transaction:

```java
@TransactionalEventListener(fallbackExecution = true)
public void handleWithoutTransaction(OrderChanged event) {
    // Không có transaction: chạy ngay theo fallback.
}
```

Trong trường hợp fallback, không có transaction resource holder của transaction phát event để kiểm tra hoặc tái sử dụng. Nếu listener cần ghi database, hãy mở transaction riêng theo nhu cầu.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân và cách xử lý |
|---|---|
| `hasResource(dataSource)` trả về `false` | Đang kiểm tra sai key/DataSource instance, callback không chạy trên thread có transaction, hoặc event được phát ngoài transaction. |
| Resource vẫn bind sau commit | Đây là hành vi trong giai đoạn callback trước cleanup. Không suy luận rằng transaction gốc còn có thể commit thêm. |
| Ghi database trong `AFTER_COMMIT` nhưng dữ liệu không được commit | Resource còn bind nhưng transaction gốc đã hoàn tất. Dùng `REQUIRES_NEW` cho thao tác ghi mới. |
| Resource không xuất hiện trong listener `@Async` | Transaction context gắn với thread phát event không truyền sang executor. Mở transaction riêng trên thread worker. |
| Listener tự unbind hoặc đóng connection | Làm hỏng vòng đời tài nguyên do transaction manager quản lý. Để Spring thực hiện cleanup. |
| Listener chạy ngoài transaction khi dùng fallback | `fallbackExecution=true` cho phép chạy ngay, nên không có resource của transaction gốc. |
| Parent hoặc child context có trạng thái khác nhau | Resource và synchronization thuộc thread/context và transaction manager cụ thể; xác định đúng datasource/entity manager factory đang được quản lý. |

## 9. Ghi nhớ

- Spring thường bind JDBC/JPA resource vào thread hiện tại bằng `TransactionSynchronizationManager`.
- `BEFORE_COMMIT` chạy khi transaction còn hoạt động; thao tác ghi tham gia transaction gốc.
- `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION` có thể chạy khi resource vẫn bind, trước cleanup.
- Resource còn bind sau commit không có nghĩa transaction gốc có thể commit thêm.
- Dùng `REQUIRES_NEW` khi listener sau commit cần ghi dữ liệu mới.
- Transaction resource không tự truyền sang thread `@Async`; worker cần transaction riêng nếu truy cập database.
- Không tự unbind hoặc đóng resource do Spring transaction manager quản lý.