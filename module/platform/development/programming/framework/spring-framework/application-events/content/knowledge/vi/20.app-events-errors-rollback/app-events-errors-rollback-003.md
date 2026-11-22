# Exception listener và rollback transaction trong Spring Framework Application Events

## 1. Câu hỏi cốt lõi: listener ném lỗi thì giao dịch có rollback không?

Spring Framework cho phép phát sự kiện bằng `ApplicationEventPublisher.publishEvent(...)` và tiếp nhận chúng thông qua `@EventListener`, `ApplicationListener` hoặc `@TransactionalEventListener`. Tuy nhiên, **không phải exception nào trong listener cũng làm transaction của publisher rollback**. Kết quả phụ thuộc vào **thời điểm listener chạy**, **nó có đồng bộ với publisher hay không**, **exception có thoát tới transaction interceptor không**, và **quy tắc rollback của transaction**.

Hai trường hợp đối lập:

~~~java
// Trường hợp A: listener đồng bộ, lỗi thoát ra khi T1 vẫn đang mở.
@Transactional
public void placeOrder(long id) {
    repository.insert(id);
    events.publishEvent(new OrderPlaced(id)); // listener ném RuntimeException
    // Exception lan ra khỏi phương thức -> T1 có thể rollback.
}
~~~

~~~java
// Trường hợp B: listener được gọi sau khi T1 commit thành công.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    sendEmail(event.id()); // Lỗi tại đây không thể rollback commit của T1.
}
~~~

Hai đoạn trên là **mã minh họa tích hợp**; `repository`, `events`, `OrderPlaced` và `sendEmail` cần được định nghĩa trong ứng dụng. Ở trường hợp A, một `RuntimeException` thoát khỏi lời gọi `@Transactional` thường làm transaction gốc rollback theo quy tắc mặc định. Ở trường hợp B, giao dịch gốc **đã commit xong trước khi thân listener chạy**; exception có thể gây lỗi hậu xử lý nhưng không có khả năng “hoàn tác” dữ liệu đã commit.

Mục tiêu bài học:

1. Hiểu đường truyền exception giữa publisher, multicaster, listener và transaction interceptor.
2. Biết khi nào `@EventListener` đồng bộ làm T1 rollback, và điều gì thay đổi nếu bắt/nuốt exception.
3. Phân biệt bốn pha `@TransactionalEventListener` và ngữ nghĩa lỗi ở từng pha.
4. Biết vì sao `@Async` và cấu hình `ErrorHandler` thay đổi đường lan truyền exception.
5. Thực hành với Java 17 + JDBC/H2 để nhìn thấy rollback thực sự trong database.
6. Chọn mô hình xử lý phù hợp cho các side effect không thể rollback như email, API ngoài, broker.

## 2. Mô hình lan truyền exception từ event đến transaction

Trong cấu hình mặc định, `SimpleApplicationEventMulticaster` không có executor bất đồng bộ riêng và listener đồng bộ được gọi trên thread của publisher. Khi service đang ở transaction T1:

~~~text
Caller
  |
  v
Spring @Transactional proxy
  |
  +-- BEGIN T1
  |
  +-- OrderService.placeOrder()
  |       |
  |       +-- INSERT orders(...)
  |       |
  |       +-- ApplicationEventPublisher.publishEvent(OrderPlaced)
  |                 |
  |                 +-- SimpleApplicationEventMulticaster
  |                           |
  |                           +-- @EventListener (đồng bộ)
  |                                   |
  |                                   +-- throw IllegalStateException
  |                           |
  |                           +-- exception quay lại publisher
  |
  +-- exception thoát khỏi service
  |
  +-- TransactionInterceptor áp quy tắc rollback
  |       |
  |       +-- ROLLBACK T1 (với RuntimeException mặc định)
  |
  v
Caller nhận exception
~~~

Phân biệt ba thứ:

- **Phát event** không tự commit hoặc rollback; `ApplicationEventPublisher` chỉ phân phối một sự kiện.
- **Exception có lan truyền hay không** là kết quả của cách listener được thực thi và xử lý lỗi.
- **Transaction có rollback không** là quyết định của transaction manager/interceptor dựa trên transaction status, rollback rules và ngữ cảnh exception.

Nếu không có transaction đang hoạt động, exception listener đồng bộ vẫn có thể đi ngược về publisher, nhưng **không có T1 nào để rollback**. Nếu một transaction khác đã commit trước khi event được phát, exception không thể đảo ngược transaction đó.

## 3. @EventListener đồng bộ: RuntimeException thường làm rollback

Giả sử service được gọi qua Spring proxy:

~~~java
@Service
public class OrderService {
    private final ApplicationEventPublisher publisher;
    private final OrderRepository repository;

    public OrderService(
            ApplicationEventPublisher publisher,
            OrderRepository repository) {
        this.publisher = publisher;
        this.repository = repository;
    }

    @Transactional
    public void createOrder(long orderId) {
        repository.insert(orderId);
        publisher.publishEvent(new OrderCreated(orderId));
    }
}
~~~

Listener đồng bộ:

~~~java
@Component
public class OrderValidationListener {

    @EventListener
    public void onCreated(OrderCreated event) {
        if (event.orderId() <= 0) {
            throw new IllegalArgumentException("invalid order ID");
        }
    }
}
~~~

Đây là **cặp class tích hợp**, cần repository, payload và imports phù hợp. Với `SimpleApplicationEventMulticaster` đồng bộ mặc định và không có custom `ErrorHandler` nuốt lỗi, `IllegalArgumentException` thoát khỏi listener vào `publishEvent(...)`, rồi thoát khỏi `createOrder(...)`. Spring transaction interceptor thấy unchecked exception và mặc định đánh dấu rollback/rollback T1.

**Điều kiện quan trọng:**

- `@Transactional` phải thực sự hoạt động: thường là lời gọi qua **Spring proxy** tới bean được Spring quản lý.
- Listener phải chạy **đồng bộ trong đường phát sự kiện**; khi chạy trên worker thread riêng, exception trong worker không tự quay ngược về T1.
- Exception phải **thoát khỏi ranh giới phương thức transactional** hoặc transaction đã được đánh dấu rollback-only.
- Transaction manager phải thực sự quản lý các thao tác cần rollback (ví dụ `DataSourceTransactionManager` quản lý cùng datasource JDBC).
- Nếu listener đã thực hiện side effect ngoài transaction như gửi email, rollback database **không thể thu hồi email ấy**.

### Checked exception trong listener

Javadoc `@EventListener` nêu rằng checked exception do listener ném sẽ được bao trong `UndeclaredThrowableException`, bởi event publisher không thể biểu diễn checked exception trong chữ ký API tương ứng. Lỗi wrapper là unchecked exception và có thể kích hoạt rollback nếu nó thoát khỏi transaction interceptor.

Điều này **khác** với quy tắc mặc định khi một phương thức `@Transactional` tự ném checked exception ra ngoài: trừ cấu hình rollback riêng, Spring truyền thống mặc định rollback cho `RuntimeException` và `Error`, **không tự động rollback cho mọi checked exception**.

Đừng suy đoán “checked exception luôn commit” nếu lỗi được Spring bọc thành runtime trên đường đi; hãy kiểm tra **exception thực sự rời ranh giới transaction** và cấu hình rollback rules của ứng dụng.

## 4. @Transactional rollback rules: lỗi nào làm rollback?

Quy tắc mặc định trong mô hình transaction declarative thông thường:

| Trường hợp | Kết quả mặc định khi exception thoát khỏi transaction interceptor |
|---|---|
| `RuntimeException` (gồm `IllegalStateException`, `IllegalArgumentException`) | Rollback |
| `Error` | Rollback |
| Checked exception như `IOException` | Không rollback mặc định theo quy tắc truyền thống |
| Checked exception với `rollbackFor = IOException.class` | Rollback |
| `RuntimeException` khớp `noRollbackFor` cụ thể | Có thể commit dù có exception, tùy rule thực tế |
| Transaction đã bị đánh dấu rollback-only | Không thể commit thành công; kết thúc bằng rollback, có thể xuất hiện `UnexpectedRollbackException` |

Ví dụ yêu cầu rollback với checked exception:

~~~java
@Transactional(rollbackFor = IOException.class)
public void process() throws IOException {
    updateDatabase();
    throw new IOException("external dependency failed");
}
~~~

Ví dụ chủ động **không** rollback khi gặp một loại exception:

~~~java
@Transactional(noRollbackFor = BusinessWarningException.class)
public void process() {
    updateDatabase();
    throw new BusinessWarningException("business warning");
}
~~~

Đây là **mã minh họa**; các class `IOException`, `BusinessWarningException` và `updateDatabase` cần được khai báo/nhập. Chỉ cấu hình `noRollbackFor` khi exception đúng là tình huống nghiệp vụ mà transaction được phép commit; không dùng nó để che lỗi lưu dữ liệu hoặc vi phạm tính nhất quán.

Một điểm phiên bản: những tùy chọn quy tắc rollback toàn cục có thể thay đổi theo cấu hình/phiên bản Spring; bài này trình bày **quy tắc mặc định phổ biến**, không khẳng định ứng dụng đã custom `RollbackRuleAttribute` hay chính sách khác sẽ có kết quả y hệt.

## 5. Bắt exception bên trong transaction có thể làm thay đổi kết quả

Xét đoạn:

~~~java
@Transactional
public void createOrder(long id) {
    repository.insert(id);

    try {
        events.publishEvent(new OrderCreated(id));
    } catch (IllegalStateException ex) {
        log.warn("Listener failed", ex);
    }

    // Không còn exception thoát ra từ phương thức này.
}
~~~

Nếu listener ném `IllegalStateException` và `catch` đã nuốt lỗi, transaction interceptor có thể thấy method hoàn thành **bình thường** và cố commit. Vì vậy, **bắt exception rồi không ném lại có thể khiến transaction commit**, trái với mong đợi của người viết.

Nhưng không được suy diễn rằng `try/catch` luôn cứu transaction: một inner transactional participant hoặc thao tác resource có thể đã đánh dấu transaction **rollback-only**. Khi outer method cố commit, Spring có thể ném `UnexpectedRollbackException` hoặc báo lỗi transaction tùy cấu trúc và transaction manager.

Các lựa chọn hợp lệ:

- Muốn rollback: **ném lại** exception, hoặc đánh dấu rollback-only một cách có chủ đích.
- Muốn tiếp tục nhưng vẫn bảo toàn lỗi: dùng loại exception nghiệp vụ phù hợp và log/metrics, nếu hợp đồng cho phép commit.
- Muốn xử lý lỗi riêng mà không làm rollback T1: chuyển thao tác đó sang pha hậu commit hoặc transaction riêng, hiểu rằng side effect có thể thất bại độc lập.

Ví dụ đánh dấu transaction hiện tại rollback-only:

~~~java
try {
    events.publishEvent(new OrderCreated(id));
} catch (RuntimeException ex) {
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    log.error("Event processing failed; transaction will rollback", ex);
}
~~~

Đây là **mã tích hợp**; `TransactionAspectSupport` thuộc `org.springframework.transaction.interceptor`. Chỉ dùng khi đang thực sự trong transaction do Spring AOP quản lý; việc trả về bình thường dù transaction đã rollback có thể gây hiểu nhầm cho caller, nên thường rõ ràng hơn là ném một exception nghiệp vụ có ý nghĩa.

### Self-invocation và @Transactional

~~~java
public void outer() {
    this.createOrder(42L); // Gọi nội bộ, thường bỏ qua Spring transaction proxy.
}
~~~

Nếu `outer` được gọi trong cùng instance, `this.createOrder(...)` không đi qua proxy theo chế độ AOP mặc định. Dù `createOrder` có `@Transactional`, giao dịch dự định có thể **không bắt đầu**. Khi đó listener ném lỗi không thể rollback một transaction chưa hề tồn tại. Hãy gọi qua Spring-managed bean/proxy hoặc tách boundary service đúng cách.

## 6. @TransactionalEventListener: pha quyết định liệu còn kịp rollback hay không

`@TransactionalEventListener` đăng ký xử lý event gắn với một pha của transaction. Các pha:

| Pha | Listener thực sự chạy | Exception trong listener có thể khiến T1 rollback? |
|---|---|---|
| `BEFORE_COMMIT` | Trước khi transaction T1 commit | **Có**, với unchecked exception lan truyền theo contract callback |
| `AFTER_COMMIT` (mặc định) | Sau khi T1 commit thành công | **Không**, commit đã hoàn tất |
| `AFTER_ROLLBACK` | Sau khi T1 rollback | **Không**, T1 đã rollback |
| `AFTER_COMPLETION` | Sau khi T1 commit hoặc rollback | **Không**, transaction đã kết thúc |

Khi event được publish trong transaction, annotation mặc định dùng `AFTER_COMMIT`. **Không có transaction** thì listener giao dịch mặc định **không được gọi**, trừ `fallbackExecution = true`.

### BEFORE_COMMIT

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void checkBeforeCommit(OrderCreated event) {
    if (event.mustReject()) {
        throw new IllegalStateException("before commit validation failed");
    }
}
~~~

Listener này thực thi ở bước trước commit, không phải ngay trong `publishEvent`. Đó là cơ hội kiểm tra điều kiện transaction trước khi transaction manager commit. `TransactionSynchronization.beforeCommit(...)` cho phép runtime exception lan truyền và làm transaction rollback. Nếu listener chưa được đăng ký do event không được publish trong transaction, callback này không có mặt để kiểm tra.

**Quan trọng:** `BEFORE_COMMIT` không có nghĩa commit chắc chắn sẽ xảy ra; transaction vẫn có thể rollback vì lỗi sau đó.

### AFTER_COMMIT

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendOrderNotification(OrderCreated event) {
    notifier.send(event.orderId());
}
~~~

Nếu `notifier.send(...)` ném lỗi, **T1 đã commit trước đó**. Không thể đảo ngược dữ liệu của T1 bằng cách ném exception ở pha này. Cần có logging/metrics, retry hoặc cơ chế bền vững nếu việc gửi thông báo quan trọng.

Một khác biệt kỹ thuật dễ nhầm: `TransactionPhase.AFTER_COMMIT` của `@TransactionalEventListener` là trường hợp chuyên biệt của **`AFTER_COMPLETION`**, xử lý trong cùng chuỗi callback transaction completion; nó **không phải** lời gọi `TransactionSynchronization.afterCommit()`.

Spring mô tả `TransactionSynchronization.afterCompletion(int)` như callback mà exception phát sinh được **ghi log chứ không lan truyền** theo cơ chế callback thông thường. Trong khi đó, exception từ `TransactionSynchronization.afterCommit()` có thể **lan truyền tới caller dù dữ liệu đã commit**. Vì vậy đừng viết quy tắc “mọi after-commit exception luôn được ném về service” hoặc “mọi after-commit exception đều bị nuốt” mà không chỉ rõ **loại callback và cách phát event**. Dù lỗi được truyền đi hay log, cả hai đều **không thể rollback commit đã hoàn thành**.

### AFTER_ROLLBACK

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollback(OrderCreated event) {
    metrics.incrementRollbackCount();
}
~~~

Đây là một điểm hợp lý để ghi log, metrics hoặc kích hoạt **compensation logic** đã được thiết kế riêng. Nó không khôi phục T1 (vì T1 đã rollback) và cũng không tạo transaction mới mặc định. Nếu cần ghi một audit row bền vững về thất bại, dùng transaction mới hoặc outbox/khối xử lý thích hợp, không dựa vào resource transaction đã rollback.

### AFTER_COMPLETION

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void cleanup(OrderCreated event) {
    temporaryState.remove(event.orderId());
}
~~~

Chạy sau cả commit lẫn rollback; phù hợp tác vụ cleanup không phụ thuộc kết quả. Nếu cần phân biệt thành công hay thất bại, dùng phase riêng hoặc contract transaction synchronization phù hợp.

Các đoạn này đều là **mã tích hợp**, cần class event, collaborator, import và bean configuration tương ứng. Không đặt toàn bộ chúng vào một chương trình mà không xác định chính sách tương tác giữa các listener.

## 7. Ví dụ chạy được Java 17: lỗi listener thường và BEFORE_COMMIT đều rollback

Ví dụ sau dùng:

- Java 17+, Maven.
- Spring Framework **6.2.8**, `spring-context` và `spring-jdbc`.
- H2 **2.3.232** làm database trong bộ nhớ.
- `DataSourceTransactionManager` để điều khiển transaction JDBC.
- `@EnableTransactionManagement` để Spring tạo transaction proxy.
- Ba lần gọi service: thành công, lỗi ở `@EventListener` đồng bộ, lỗi ở `BEFORE_COMMIT`.

Ta chủ động đặt `@Order(0)` trên các transactional listener để **đăng ký synchronization trước** listener thường, và `@Order(100)` trên listener thường. Việc này giúp pha `AFTER_ROLLBACK` có callback được đăng ký trước khi listener thường ném lỗi.

Cấu trúc:

~~~text
event-rollback-demo/
├── pom.xml
└── src/main/java/demo/EventRollbackDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-rollback-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/EventRollbackDemo.java

~~~java
package demo;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public final class EventRollbackDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            OrderService service = ctx.getBean(OrderService.class);

            jdbc.execute(
                "CREATE TABLE orders (" +
                "id BIGINT PRIMARY KEY, status VARCHAR(30) NOT NULL)"
            );

            // 1. Đường thành công.
            service.create(1L, FailureMode.NONE);
            System.out.println("rows after success=" + count(jdbc));

            // 2. RuntimeException trong listener thường.
            try {
                service.create(2L, FailureMode.IN_REGULAR_LISTENER);
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }
            System.out.println("rows after regular failure=" + count(jdbc));

            // 3. RuntimeException tại thời điểm BEFORE_COMMIT.
            try {
                service.create(3L, FailureMode.BEFORE_COMMIT);
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }
            System.out.println("rows after before-commit failure=" + count(jdbc));
        }
    }

    private static long count(JdbcTemplate jdbc) {
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM orders",
            Long.class
        );
        return count == null ? -1L : count;
    }

    public enum FailureMode {
        NONE,
        IN_REGULAR_LISTENER,
        BEFORE_COMMIT
    }

    public record OrderCreated(long orderId, FailureMode failureMode) {}

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:eventrollback;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc, ApplicationEventPublisher events) {
            return new OrderService(jdbc, events);
        }

        @Bean
        public OrderObservers orderObservers() {
            return new OrderObservers();
        }
    }

    // Cần không phải final để Spring có thể tạo class-based proxy.
    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher events;

        public OrderService(
                JdbcTemplate jdbc, ApplicationEventPublisher events) {
            this.jdbc = jdbc;
            this.events = events;
        }

        @Transactional
        public void create(long id, FailureMode failureMode) {
            jdbc.update(
                "INSERT INTO orders (id, status) VALUES (?, ?)",
                id, "CREATED"
            );
            events.publishEvent(new OrderCreated(id, failureMode));
        }
    }

    public static class OrderObservers {

        // Synchronizations được đăng ký trước listener thường.
        @Order(0)
        @TransactionalEventListener(
            phase = TransactionPhase.BEFORE_COMMIT
        )
        public void beforeCommit(OrderCreated event) {
            System.out.println("BEFORE_COMMIT id=" + event.orderId());
            if (event.failureMode() == FailureMode.BEFORE_COMMIT) {
                throw new IllegalStateException("before commit failed");
            }
        }

        @Order(0)
        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void afterCommit(OrderCreated event) {
            System.out.println("AFTER_COMMIT id=" + event.orderId());
        }

        @Order(0)
        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK
        )
        public void afterRollback(OrderCreated event) {
            System.out.println("AFTER_ROLLBACK id=" + event.orderId());
        }

        @Order(100)
        @EventListener
        public void immediate(OrderCreated event) {
            System.out.println("REGULAR id=" + event.orderId());
            if (event.failureMode() == FailureMode.IN_REGULAR_LISTENER) {
                throw new IllegalStateException("regular listener failed");
            }
        }
    }
}
~~~

Chạy từ thư mục `event-rollback-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.EventRollbackDemo
~~~

Các dòng do **chương trình** in khi chạy thành công, theo thứ tự dự kiến với dispatcher đồng bộ mặc định và cấu hình như trên (bỏ qua log phụ của Maven/Spring):

~~~text
REGULAR id=1
BEFORE_COMMIT id=1
AFTER_COMMIT id=1
rows after success=1
REGULAR id=2
AFTER_ROLLBACK id=2
caught=regular listener failed
rows after regular failure=1
REGULAR id=3
BEFORE_COMMIT id=3
AFTER_ROLLBACK id=3
caught=before commit failed
rows after before-commit failure=1
~~~

### Vì sao kết quả như vậy?

**Lần 1 — thành công:**

1. Transaction proxy bắt đầu T1 rồi INSERT ID 1.
2. `publishEvent` gọi regular listener, in `REGULAR id=1`. Ba listener giao dịch đã đăng ký callbacks theo phase.
3. Service method kết thúc bình thường; transaction manager gọi `BEFORE_COMMIT`, in mốc 1.
4. Database commit thành công.
5. Listener `AFTER_COMMIT` chạy, in mốc 1.
6. `count(jdbc)` chạy ngoài T1 trả về một row.

**Lần 2 — lỗi trong regular listener:**

1. Transaction T2 INSERT ID 2 và phát event.
2. Vì các transactional listener `@Order(0)` được đăng ký trước, `AFTER_ROLLBACK` đã có synchronization theo T2.
3. Regular listener `@Order(100)` in `REGULAR id=2`, rồi ném `IllegalStateException`.
4. Exception thoát ra khỏi `publishEvent` và service method; transaction interceptor rollback T2.
5. `AFTER_ROLLBACK` in ID 2, caller nhận thông báo `regular listener failed`. Row ID 2 không tồn tại trong database.

**Lần 3 — lỗi ở BEFORE_COMMIT:**

1. Transaction T3 INSERT ID 3; regular listener xử lý bình thường.
2. Service method trả về, Spring chuẩn bị commit T3.
3. Callback `BEFORE_COMMIT` in ID 3 rồi ném `IllegalStateException`.
4. Transaction manager rollback T3; listener `AFTER_ROLLBACK` được gọi; caller nhận exception `before commit failed`.
5. Row ID 3 không tồn tại. Tổng số rows vẫn bằng một.

Ví dụ dùng database transaction thật, vì vậy khác với demo chỉ thay đổi một `Map` trong bộ nhớ. Toàn bộ logic transaction đi qua Spring proxy, không tự gọi `new OrderService(...).create(...)` ở ngoài container.

### Điều gì chưa được ví dụ chứng minh?

- Nó không thực hiện gửi email hoặc gọi REST API; những side effect đó **không tự rollback** cùng SQL transaction.
- Nó không chứng minh hành vi khi cấu hình async executor hoặc custom `ErrorHandler`.
- Nó không ném lỗi trong `AFTER_COMMIT`, nhằm giữ stdout xác định và không làm lẫn chuyện “call trả exception” với kết quả commit DB.
- Nó không có JPA persistence context hoặc reactive transaction; các chủ đề ấy có thêm ranh giới cần phân tích riêng.

## 8. AFTER_COMMIT ném exception: DB đã commit thì xử lý thế nào?

Tình huống thường gặp:

~~~text
T1: BEGIN
  UPDATE orders SET status = 'PAID' ...
  publish OrderPaid
T1: COMMIT thành công
  -> @TransactionalEventListener(AFTER_COMMIT)
       -> gọi Email API
       -> Email API timeout/throw
T1: dữ liệu DB vẫn ở trạng thái PAID
~~~

Không gọi `throw new RuntimeException(...)` trong callback hậu commit rồi mong transaction gốc rollback. Nếu cần ghi thêm DB từ callback, tài nguyên transaction gốc vẫn có thể tạm còn gắn với thread cho đến khi cleanup. Spring khuyến nghị mở **transaction mới** cho công việc DB thực sự cần commit sau completion.

Ví dụ kiến trúc:

~~~java
@Component
public class PaymentListener {
    private final AuditWriter auditWriter;

    public PaymentListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onPaid(OrderPaid event) {
        auditWriter.record(event.paymentId());
    }
}

@Service
public class AuditWriter {
    private final AuditRepository repository;

    public AuditWriter(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(long paymentId) {
        repository.insertAudit(paymentId);
    }
}
~~~

Đây là **code tích hợp**: các loại `OrderPaid`, `AuditRepository` và imports cần định nghĩa. `REQUIRES_NEW` mở transaction vật lý độc lập qua transaction manager tương ứng, gọi qua Spring proxy của bean `AuditWriter`. Nếu transaction mới thất bại, **transaction gốc không bị rollback**. Nếu phải ghi audit và payment **nguyên tử**, hai bản ghi nên được tạo trong cùng transaction ban đầu hoặc dùng transactional outbox theo yêu cầu.

Đừng đặt `@Transactional(propagation = REQUIRES_NEW)` trên method tự gọi bằng `this.record(...)` trong cùng bean theo proxy mode mặc định: self-invocation bỏ qua proxy và không đảm bảo mở transaction mới.

### Một API gửi email có rollback theo DB không?

Không. Dù bạn gọi email trong `@Transactional` trước commit, database rollback **không tự thu hồi email**. Nếu gửi trong `AFTER_COMMIT`, email chỉ được gửi sau khi DB commit, giảm nguy cơ gửi email cho thay đổi bị rollback, nhưng vẫn có cửa sổ mất tác vụ khi process crash sau commit và trước khi gửi. Với yêu cầu giao hàng chắc chắn, cần durable outbox/queue, retry và idempotency.

## 9. @Async và exception: vì sao rollback không lan qua thread?

Đặt `@Async` trên một `@EventListener`:

~~~java
@Async("eventsExecutor")
@EventListener
public void onOrderCreated(OrderCreated event) {
    sendNotification(event.orderId());
    // RuntimeException nếu có xảy ra ở executor worker.
}
~~~

Đoạn này là **mã tích hợp**, cần `@EnableAsync`, bean `eventsExecutor` và bean listener đi qua async proxy. Khi hoạt động đúng, phần thân listener chạy trên executor worker. Exception ném trong worker **thường không lan ngược về caller `publishEvent(...)`**; nó không tự kích hoạt rollback transaction T1 của publisher.

Những hệ quả:

- Worker có thể chạy **trước khi T1 commit**, nên lệnh SELECT theo ID chưa chắc thấy dữ liệu của T1.
- T1 có thể commit dù việc gửi thông báo đã thất bại; exception trong worker không phải điều kiện để rollback T1.
- Với phương thức `@Async void`, có thể cấu hình `AsyncUncaughtExceptionHandler` để log/ghi nhận exception. Với phương thức trả về future được hỗ trợ, cần quan sát kết quả exceptional từ future.
- Lỗi khi **submit task** hoặc executor từ chối task có thể xảy ra trên đường gọi publish và có ngữ nghĩa khác với exception từ phần thân worker. Không tuyên bố “mọi lỗi liên quan async đều tuyệt đối không thể ảnh hưởng T1”.
- ThreadLocal transaction, security context và logging MDC của publisher không được bảo đảm tự mang sang worker nếu không cấu hình propagation tương ứng.

### @Async kết hợp AFTER_COMMIT

~~~java
@Async("eventsExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onPaid(OrderPaid event) {
    notificationService.send(event.paymentId());
}
~~~

Mục tiêu là kích hoạt xử lý async **sau khi T1 commit**. Transaction binding/đăng ký synchronization vẫn phải diễn ra trong transaction context của publisher; phần thân công việc có thể chạy ở worker thread sau completion. Lỗi xảy ra tại worker không thể rollback T1. Nếu worker cần DB transaction, mở transaction mới rõ ràng trong worker.

Từ Spring Framework 6.1, transactional listeners có hợp đồng thực thi khác listeners thông thường với executor của `SimpleApplicationEventMulticaster`: không được mặc định mọi listener transaction sẽ được tùy tiện chuyển sang executor trước khi đăng ký transaction synchronization. Dù vậy, tự gắn `@Async` cho phần xử lý listener có thể làm phần thân chạy riêng khi cấu hình proxy đúng.

**Để xử lý retry bền vững**, `@Async` không đủ. Process có thể chết sau commit trước khi task chạy xong. Dùng outbox, queue hoặc job store khi nghiệp vụ cần chắc chắn.

## 10. ErrorHandler của SimpleApplicationEventMulticaster ảnh hưởng rollback ra sao?

Không chỉ `@Async` mới làm exception không tới transaction proxy. Một ứng dụng có thể định nghĩa custom `ApplicationEventMulticaster` với `ErrorHandler`.

Mẫu cấu hình minh họa:

~~~java
@Bean(name = "applicationEventMulticaster")
public SimpleApplicationEventMulticaster applicationEventMulticaster() {
    SimpleApplicationEventMulticaster m =
        new SimpleApplicationEventMulticaster();

    m.setErrorHandler(ex -> {
        logger.error("Event listener failed", ex);
        // Không rethrow -> lỗi được xử lý theo chính sách handler.
    });

    return m;
}
~~~

Đây là **đoạn cấu hình**, cần `logger`, imports và bean setup phù hợp. `SimpleApplicationEventMulticaster` không mặc định có `ErrorHandler` chuyên nuốt lỗi. Khi callback được thực thi đồng bộ nhưng `ErrorHandler` nuốt exception, đường gọi `publishEvent(...)` có thể hoàn thành bình thường và transaction T1 có thể commit.

Nếu error handler chọn **ném lại** exception, lỗi vẫn có thể quay về publisher và dẫn đến rollback như mô hình thường. Với executor bất đồng bộ, lỗi có thể được xử lý trong worker thay vì thread publisher.

Do đó, khi debug “listener đã throw mà database vẫn commit”, hãy kiểm tra:

1. Listener có chạy đồng bộ hay không?
2. Spring event multicaster có custom `TaskExecutor`/`ErrorHandler`?
3. Exception bị catch trong listener hay service?
4. Transaction interceptor có thực sự bao phủ lời gọi publish không?
5. Transaction có bị đánh dấu rollback-only hay được cấu hình `noRollbackFor`?
6. Event có được xử lý **sau commit** thay vì khi T1 còn mở?

### Một nguy cơ thiết kế

Nuốt mọi exception của listener giúp publisher tiếp tục, nhưng cũng có thể làm mất một tín hiệu nghiệp vụ bắt buộc. Nếu listener thực hiện kiểm tra để quyết định transaction có được phép commit, không nên dựa vào một cơ chế dispatch được thiết kế để có thể cấu hình “log and continue”. Kiểm tra tính hợp lệ cốt lõi nên nằm trong service/domain validation trực tiếp, với transaction boundary rõ ràng.

## 11. Transaction propagation và exception giữa nhiều service

Mô hình gồm một outer service T1 và inner service T2 có thể khiến rollback phức tạp hơn.

### REQUIRED (mặc định) — cùng transaction vật lý

~~~java
@Service
class InnerService {
    @Transactional // PROPAGATION_REQUIRED
    public void validateAndStore() {
        throw new IllegalStateException("inner failure");
    }
}

@Service
class OuterService {
    private final InnerService inner;

    @Transactional
    public void placeOrder() {
        try {
            inner.validateAndStore();
        } catch (IllegalStateException ex) {
            // Đã bắt exception, nhưng T1 có thể bị marked rollback-only.
        }
    }
}
~~~

Đây là **mẫu tích hợp** cần inject bean qua proxy. Khi inner transactional proxy tham gia cùng transaction vật lý và gặp runtime exception, Spring có thể đánh dấu transaction chung rollback-only. Outer catch không xóa được cờ này; lúc outer commit có thể ném `UnexpectedRollbackException`. Quyết định cụ thể phụ thuộc transaction manager và cấu hình `globalRollbackOnParticipationFailure`, nhưng không nên dựa vào việc catch để ép commit.

### REQUIRES_NEW — transaction độc lập

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAudit(long orderId) {
    auditRepository.insert(orderId);
}
~~~

Khi lời gọi đi qua proxy và có transaction manager phù hợp, Spring tạm gác transaction ngoài, mở transaction mới cho phần audit. Nếu transaction mới rollback vì listener error, **không tự kéo transaction ngoài rollback**, trừ khi exception tiếp tục thoát lên outer interceptor hoặc outer quyết định rollback.

Ngược lại, nếu T2 commit rồi T1 rollback, dữ liệu T2 đã commit có thể còn lại. Đó là một lựa chọn nghiệp vụ cần suy nghĩ kỹ, đặc biệt với audit, compensation và notification.

### NESTED — savepoint thay vì transaction vật lý riêng

`Propagation.NESTED` có thể dùng savepoint trên cùng resource/transaction khi transaction manager hỗ trợ, đặc biệt trong JDBC. Rollback tới savepoint không có nghĩa đã mở một transaction hoàn toàn độc lập; nếu outer transaction rollback sau đó, toàn bộ thay đổi đã commit logic trong savepoint vẫn bị rollback theo outer. Không dùng `NESTED` như cách bảo đảm audit sống sót sau rollback của transaction gốc.

## 12. Exception trong AFTER_ROLLBACK/AFTER_COMPLETION không thể làm gì?

Sau rollback, không còn commit gốc nào để đảo ngược. Lỗi trong callback `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION` chỉ là **lỗi hậu xử lý**, không thể tạo ra một rollback mới cho T1. Với Spring transaction synchronization thông thường, exception ở `afterCompletion` được ghi log và không được lan truyền theo cơ chế callback như `beforeCommit`.

Một phản ví dụ:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void recordFailure(OrderCreated event) {
    auditRepository.save(new AuditRecord(event.orderId()));
    // Không nên tin rằng save() này được commit bởi T1.
}
~~~

Tài nguyên transaction có thể vẫn bị ràng buộc tạm với thread trong callback; Spring Javadoc cảnh báo thao tác dữ liệu có thể “tham gia” resource transaction cũ dù **không còn commit tiếp theo**. Cách rõ ràng để ghi audit về thất bại là gọi một bean khác với `@Transactional(propagation = REQUIRES_NEW)`, hoặc đưa lỗi vào một hệ thống xử lý bền vững có transaction phù hợp.

Nếu quy trình khôi phục cần **không làm mất dấu lỗi**, log tại callback là chưa đủ: cần audit durable, event failure store hoặc outbox/job store có bảo đảm tương ứng.

## 13. Reactive transactions: ngoại lệ về nơi lưu transaction context

Các ví dụ trên dùng thread-bound transaction với `PlatformTransactionManager`, phù hợp JDBC/JPA imperative.

Trong Spring reactive (R2DBC, `ReactiveTransactionManager`), transaction state gắn với **Reactor Context**, không phải ThreadLocal. Từ Spring 6.1, `@TransactionalEventListener` hỗ trợ reactive transaction khi **event source chứa transaction context**, thường qua `TransactionalEventPublisher`. Một listener được gọi trong một subscribe riêng không tự thừa hưởng transaction của publisher.

Ví dụ dạng ý tưởng:

~~~java
return database.sql("INSERT INTO orders(id) VALUES (:id)")
    .bind("id", orderId)
    .fetch()
    .rowsUpdated()
    .then(transactionalEventPublisher.publishEvent(
        new OrderCreated(orderId, FailureMode.NONE)))
    .as(transactionalOperator::transactional);
~~~

Đây là **mẫu tích hợp**, cần `DatabaseClient`, `TransactionalEventPublisher` và `TransactionalOperator`. Trong reactive pipeline, exception từ publisher (tín hiệu `onError`) nằm trong transaction có thể kích hoạt rollback theo operator; một async listener hoặc công việc tách khỏi subscription không tự mang cùng transaction context.

Không sao chép Java JDBC demo ở trên và kỳ vọng tương tác R2DBC cũng giống ThreadLocal. Cần kiểm thử bằng `StepVerifier` hoặc integration test reactive theo đúng subscription boundary.

## 14. Kiểm thử rollback của listener cho đúng

Một bài test nên xác minh **trạng thái database** và **sự kiện listener** đồng thời, không chỉ xác minh exception được ném.

### Danh sách ca kiểm thử

| Ca | Phương thức gây lỗi | Kỳ vọng database | Kỳ vọng listener |
|---|---|---|---|
| Thành công | Không có lỗi | Row đã commit | `AFTER_COMMIT` chạy |
| Đồng bộ ném `RuntimeException` | `@EventListener` | Row rollback | `AFTER_ROLLBACK` chạy nếu đã đăng ký |
| `BEFORE_COMMIT` ném `RuntimeException` | `@TransactionalEventListener` | Row rollback | `AFTER_ROLLBACK` chạy |
| `AFTER_COMMIT` thất bại | Hậu commit | Row T1 vẫn commit | Ghi nhận lỗi và retry độc lập |
| Async worker thất bại | `@Async @EventListener` | T1 không tự rollback vì lỗi worker | Error handler/log ở worker |
| Exception bị catch và nuốt | Service/listener | Có thể commit | Phải kiểm tra rollback-only thực tế |
| `noRollbackFor` được áp dụng | Transaction interceptor | Có thể commit theo rule | Exception vẫn có thể đến caller |
| Không có transaction | Plain publish | Không có T1 để rollback | Transaction listener mặc định không chạy |

### Bẫy: @Transactional test mặc định rollback

Trong Spring Test, test method có `@Transactional` thường được framework rollback khi test kết thúc. Nếu muốn kiểm tra listener `AFTER_COMMIT`, đừng chỉ gọi service rồi assert ngay trong test transaction chưa commit:

~~~java
@Test
@Transactional
void verifiesAfterCommit() {
    service.create(10L, FailureMode.NONE);

    TestTransaction.flagForCommit();
    TestTransaction.end(); // Transaction của test thật sự commit.

    // Assert AFTER_COMMIT tại đây cho listener đồng bộ.
}
~~~

Đây là **mã test minh họa**, cần `spring-test`, JUnit, dữ liệu và cấu hình test transaction; không phải phần của chương trình `EventRollbackDemo.java`. Một cách đơn giản khác là **không** đặt `@Transactional` trên chính test method, rồi gọi Spring service proxy có `@Transactional` riêng như demo.

Kiểm thử cần đảm bảo:

- Các bean/transaction manager nằm trong cùng test context.
- Lời gọi transactional thực sự đi qua proxy.
- Exception không bị multicaster/error handler nuốt ngoài ý muốn.
- Khi dùng `@Async`, dùng await/latch có timeout; không assert ngay sau publication.
- Với `BEFORE_COMMIT`, so sánh thay đổi trong DB **sau khi service call kết thúc/throw**, không chỉ giá trị entity trong bộ nhớ.
- Khi event gửi email hoặc HTTP, dùng fake/mock có thể điều khiển lỗi; không giả định rollback của DB phục hồi side effect bên ngoài.

## 15. Bảo đảm nghiệp vụ khi hậu xử lý thất bại: outbox và idempotency

Nếu muốn “đơn hàng commit thành công thì nhất định phải có yêu cầu gửi email”, một listener `AFTER_COMMIT` đơn thuần không đủ để bảo đảm durability. Có cửa sổ:

~~~text
T1 COMMIT order
      |
      | JVM crash hoặc process bị dừng
      v
AFTER_COMMIT listener chưa kịp gửi email
      |
      v
Không có event nào tồn tại bền vững để replay
~~~

Một phương án là **transactional outbox**:

~~~text
BEGIN T1
  INSERT orders(...)
  INSERT outbox_events(event_id, order_id, event_type, payload, status='PENDING')
COMMIT T1
       |
       v
Worker đọc PENDING
       |
       +-- gửi email / publish broker
       +-- cập nhật trạng thái, ghi lỗi, retry có giới hạn
       |
       v
Consumer sử dụng eventId/idempotency key tránh xử lý trùng
~~~

Outbox row và thay đổi orders được ghi trong **cùng transaction local**. Nếu T1 rollback, cả hai rollback. Nếu process chết sau commit, outbox còn tồn tại để worker xử lý sau. Nhưng outbox thường hỗ trợ **at-least-once delivery**, không tự đảm bảo exactly-once end-to-end: worker có thể gửi thành công rồi chết trước khi đánh dấu, tạo duplicate.

Một số chính sách quan trọng:

- **eventId** duy nhất cho một occurrence; retry giữ nguyên eventId.
- **aggregateId/orderId** xác định đối tượng nghiệp vụ; không dùng làm dedupe toàn bộ events.
- **Số lần thử, backoff, timeout:** tránh spam hệ thống đích khi lỗi kéo dài.
- **Idempotency:** gửi request với idempotency key nếu API hỗ trợ, hoặc lưu `processed_events` theo consumer.
- **DLQ/job store:** tách các lỗi vĩnh viễn cần con người xử lý.
- **Observability:** đo số pending, thất bại, độ trễ từ commit đến xử lý xong.
- **Transaction boundary:** audit/kết quả xử lý tiếp theo cần transaction riêng; không mặc định được commit bởi T1.

Đây là giải pháp cho yêu cầu **không mất event sau crash**, khác với câu hỏi “exception có làm rollback transaction hiện tại không”.

## 16. Checklist chẩn đoán lỗi thực tế

### Tình huống A — Listener throw nhưng database vẫn commit

1. Kiểm tra listener đang dùng `@TransactionalEventListener(AFTER_COMMIT)` hay `@EventListener` thường.
2. Kiểm tra `@Async`, custom executor, custom `ErrorHandler`.
3. Tìm `try/catch` nuốt exception ở listener, publisher hoặc service.
4. Kiểm tra `@Transactional(noRollbackFor = ...)` và global rollback rules.
5. Xác nhận method transactional được gọi qua proxy và transaction manager bao phủ đúng datasource.
6. Xác nhận thông tin `COMMIT/ROLLBACK` từ DB/transaction logs, không chỉ nhìn dòng Java object thay đổi.
7. Kiểm tra resource nào đã được commit bởi transaction khác trước khi lỗi xuất hiện.

### Tình huống B — Service catch exception nhưng vẫn bị rollback

1. Kiểm tra inner `@Transactional(REQUIRED)` đã đặt rollback-only.
2. Quan sát `UnexpectedRollbackException` tại thời điểm commit.
3. Kiểm tra lỗi DB đã khiến transaction không còn khả năng commit.
4. Nếu cần isolation, xem xét `REQUIRES_NEW` với ranh giới bean/proxy đúng; hiểu rằng side effect của transaction mới có thể sống sót ngoài outer rollback.
5. Không dùng `noRollbackFor` để làm transaction đã bị DB đánh dấu thất bại trở nên hợp lệ.

### Tình huống C — AFTER_ROLLBACK không chạy

1. Event có được publish khi transaction đang active?
2. Listener đã được Spring đăng ký trước khi publish?
3. Một `@EventListener` khác có ném lỗi **trước khi** listener transaction kịp đăng ký synchronization?
4. Event được phát trong thread nào? Có bị chuyển qua executor trước khi đăng ký?
5. Transaction manager có thực sự rollback hay chỉ trả về lỗi ở một thao tác ngoài transaction?
6. Có `fallbackExecution` hoặc custom cấu hình khiến cách xử lý khác với mặc định?

### Tình huống D — AFTER_COMMIT ném lỗi, client báo thất bại nhưng dữ liệu vẫn có

Đừng tự động retry toàn bộ lệnh tạo đơn chỉ vì client thấy lỗi: transaction có thể **đã commit thành công**. Với callback transaction completion, hành vi exception có thể tùy loại callback, nhưng DB không tự rollback. Thiết kế command có idempotency key, API trả kết quả phù hợp với transaction outcome và logic xử lý hậu kỳ theo trạng thái riêng.

### Tình huống E — Lỗi xảy ra nhưng rollback không thể thu hồi email

Đây không phải lỗi của transaction manager: email/API call nằm ngoài local DB transaction. Chuyển side effect sang xử lý sau commit hoặc transactional outbox, định nghĩa retry/compensation/idempotency theo nghiệp vụ.

## 17. Bảng ghi nhớ về exception và transaction phase

| Kiểu listener / callback | Thời điểm | Đường exception điển hình | Có thể rollback T1? |
|---|---|---|---|
| `@EventListener` đồng bộ | Trong `publishEvent` | Lan về publisher nếu không bị bắt | **Có** nếu chưa commit và rollback rule khớp |
| `@EventListener` với `@Async` | Worker thread riêng | Error handler/future của worker | **Không tự động** |
| Custom multicaster `ErrorHandler` nuốt lỗi | Bất kỳ dispatch nào handler kiểm soát | Được handler ghi log/xử lý | **Có thể không rollback** vì exception không thoát |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Trước commit | Callback exception đi tới transaction manager | **Có** |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit | Hậu completion, log/lỗi hậu xử lý | **Không** |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Sau rollback | Hậu completion | **Không** |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Sau commit hoặc rollback | Hậu completion | **Không** |
| `TransactionSynchronization.afterCommit()` trực tiếp | Sau commit | Exception có thể lan về caller | **Không** |
| Listener trong `REQUIRES_NEW` riêng | Trong transaction T2 | T2 theo rollback rule riêng | Có thể rollback **T2**, T1 tùy đường lỗi/thời điểm |

**Hai nguyên tắc quan trọng nhất:**

1. **Rollback cần một transaction còn khả năng rollback** và một lỗi/quyết định rollback nằm đúng transaction boundary.
2. **Exception hậu commit là lỗi của hậu xử lý**, không phải cách đảo ngược dữ liệu đã commit.

## 18. Kết luận

Exception từ `@EventListener` **đồng bộ** trong lời gọi `@Transactional` thường lan qua `ApplicationEventPublisher` và làm transaction gốc rollback nếu nó không bị chặn và khớp rollback rules. Trong khi đó, `@TransactionalEventListener(BEFORE_COMMIT)` có thể ngăn commit thành công bằng exception tại callback trước commit; `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION` chạy **sau khi transaction đã kết thúc**, nên không thể rollback transaction gốc dù lỗi xuất hiện.

Đừng đánh đồng “exception xuất hiện” với “database rollback”. Hãy xác định **thread, phase, proxy, propagation, ErrorHandler, rollback rules và trạng thái thực tế của transaction**. Dùng một workflow/transaction rõ ràng cho invariant nghiệp vụ quan trọng; dùng outbox/queue và idempotency khi side effect sau commit cần được thực hiện chắc chắn.

### Tài liệu chính thức

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html) — `@EventListener`, xử lý lỗi, async và ordering.
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html) — `@TransactionalEventListener` và các phase.
- [Spring Framework Javadoc 6.2.8 — EventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListener.html) — checked exception wrapping và listener async.
- [Spring Framework Javadoc 6.2.8 — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html) — hành vi khi không có transaction và tài nguyên sau completion.
- [Spring Framework Javadoc 6.2.8 — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html) — ngoại lệ trong `beforeCommit`, `afterCommit`, `afterCompletion`.
- [Spring Framework 6.2 — Transaction Rollback](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html) — rollback rules và checked/unchecked exceptions.
- [Spring Framework 6.2 — Transaction Propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html) — `REQUIRED`, `REQUIRES_NEW`, `NESTED`.
