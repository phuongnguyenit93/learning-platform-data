# Không có transaction cho transactional listener trong Spring Framework

## 1. Triệu chứng và bản chất lỗi

Một service gọi `ApplicationEventPublisher.publishEvent(...)` thành công nhưng phương thức `@TransactionalEventListener` không được thực thi; thay annotation bằng `@EventListener` thì lại nhận được event. Đây là triệu chứng rất thường gặp của việc **không có transaction tương thích ở đúng thời điểm event được publish**.

~~~java
@Component
class PaymentObserver {
    @TransactionalEventListener
    public void onPaymentCompleted(PaymentCompleted event) {
        System.out.println("Payment committed: " + event.paymentId());
    }
}
~~~

Đây là đoạn mã tích hợp, cần định nghĩa `PaymentCompleted`, import và đăng ký bean tương ứng. Annotation `@TransactionalEventListener` mặc định tương đương:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = false
)
~~~

Spring cần một transaction active để gắn callback theo phase. **Nếu event được phát ngoài transaction, transactional listener bị bỏ qua** (trong cấu hình mặc định), vì không tồn tại commit/rollback để theo dõi. Spring không bắt buộc ném exception chỉ vì bỏ qua callback này.

Bài học tập trung chẩn đoán sáu nguyên nhân:

1. Gọi `publishEvent` ngoài transaction hoặc sau khi service transactional đã trả về.
2. `@Transactional` có trên code nhưng không có hiệu lực do self-invocation, proxy, bean hay cấu hình manager.
3. Transaction propagation không tạo transaction, ví dụ `SUPPORTS` hoặc `NOT_SUPPORTED`.
4. Event được phát trên một thread khác hoặc trong scheduler/`@Async`.
5. Transaction reactive có trong Reactor Context nhưng không được đưa vào event source.
6. Transaction có tồn tại nhưng rollback hoặc listener sai phase, tạo triệu chứng giống như “không có transaction”.

Không nên sửa bằng cách bật fallback ngay. Trước hết phải xác định **contract nghiệp vụ** có thật sự yêu cầu event chỉ được xử lý khi commit thành công hay không.

## 2. Vì sao @EventListener vẫn chạy?

Hai annotation có vai trò khác nhau.

| Tính chất | `@EventListener` thông thường | `@TransactionalEventListener` |
|---|---|---|
| Khi không có transaction | Thường được gọi khi event publish | Mặc định **không** được gọi |
| Khi có transaction | Thường chạy ngay ở thời điểm publish | Gắn callback với một `TransactionPhase` |
| Phase mặc định | Không có phase giao dịch | `AFTER_COMMIT` |
| Điều kiện bổ sung | Bean/type/condition khớp | Cần transaction phù hợp hoặc fallback |
| Có tự tạo transaction không? | Không | Không |
| Có giao hàng bền vững không? | Không | Không |
| Có thể dùng cho hậu xử lý chỉ sau commit? | Cần điều phối ngoài | Có, nếu event đăng ký trong transaction |

Sơ đồ:

~~~text
publisher.publishEvent(OrderPlaced)
    |
    v
ApplicationContext / EventMulticaster
    |
    +-- @EventListener
    |      +-- chạy ngay theo dispatch policy (mặc định đồng bộ)
    |
    +-- @TransactionalEventListener
           |
           +-- Có transaction tương thích?
                  |
                  +-- Có: đăng ký synchronization theo phase
                  |        +-- BEFORE_COMMIT
                  |        +-- AFTER_COMMIT
                  |        +-- AFTER_ROLLBACK
                  |        +-- AFTER_COMPLETION
                  |
                  +-- Không: fallbackExecution?
                            +-- false: bỏ event
                            +-- true: gọi listener ở đường fallback
~~~

Việc gọi `publishEvent(...)` trả về **không chứng minh tất cả các listener đã chạy**, cũng không chứng minh transaction commit, email đã gửi hay message đã được broker tiếp nhận.

### Ba mốc thời gian khác nhau

- **Publication:** lệnh `publishEvent` xuất hiện trong code.
- **Transaction completion:** transaction commit hoặc rollback.
- **Listener execution:** callback thực sự chạy theo phase, hoặc chạy qua fallback khi không có transaction.

Vì vậy, khi event được publish trong transaction mà listener `AFTER_COMMIT` chưa chạy ngay, có thể do transaction vẫn mở. Ngược lại, khi publish ngoài transaction và `fallbackExecution=false`, chờ thêm thời gian **không** làm event bị bỏ được gọi lại.

## 3. fallbackExecution=true thay đổi điều gì?

Spring cho phép:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void onOrderPlaced(OrderPlaced event) {
    notification.send(event.orderId());
}
~~~

Đoạn code minh họa trên cần bean, event và notification service của ứng dụng.

- **Có transaction:** listener tuân theo phase; với `AFTER_COMMIT` nó chạy sau commit thành công.
- **Không có transaction:** listener được phép chạy theo đường fallback **ngay khi event được publish**; không có commit nào để chờ.
- **Không khởi tạo transaction:** fallback không thay thế `@Transactional` hoặc transaction manager.
- **Không đảm bảo exactly-once:** không có durable store, retry hoặc idempotency được bổ sung tự động.

| Phase | Có transaction | Không có transaction, fallback=false | Không có transaction, fallback=true |
|---|---|---|---|
| `BEFORE_COMMIT` | Trước commit | Bỏ qua | Xử lý fallback ngay |
| `AFTER_COMMIT` | Sau commit thành công | Bỏ qua | Xử lý fallback ngay |
| `AFTER_ROLLBACK` | Sau rollback | Bỏ qua | Xử lý fallback ngay, **dù không có rollback** |
| `AFTER_COMPLETION` | Sau commit hoặc rollback | Bỏ qua | Xử lý fallback ngay |

Trường hợp `AFTER_ROLLBACK` đặc biệt quan trọng: bật fallback có thể kích hoạt một listener tên `onRollback` **mà không hề có transaction bị rollback**. Nếu listener làm compensation hoặc ghi lỗi nghiệp vụ, điều đó có thể sai logic.

### Nên bật fallback khi nào?

Phù hợp hơn với logging, metrics hoặc event có ý nghĩa độc lập với transaction. Cần ghi rõ contract “sau commit khi có transaction, xử lý ngay khi không có transaction”.

Không nên bật fallback chỉ để làm email thanh toán, đơn hàng hoặc cập nhật hệ thống ngoài chạy được trong khi yêu cầu thật sự là “chỉ chạy sau commit của thay đổi DB”. Trong trường hợp đó, hãy **sửa ranh giới publication**.

## 4. Demo Java 17 chạy được: ngoài transaction, commit và rollback

Ví dụ sử dụng Spring Framework **6.2.8**, Java 17+, Maven, `spring-context`, `spring-jdbc` và cơ sở dữ liệu H2 trong bộ nhớ. Nó phân biệt ba trường hợp trong **cùng một chương trình** và đọc lại số bản ghi thật của database, không giả lập transaction bằng biến boolean.

Cấu trúc dự án:

~~~text
no-transaction-event-demo/
├── pom.xml
└── src/main/java/demo/NoTransactionEventDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>no-transaction-event-demo</artifactId>
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

### src/main/java/demo/NoTransactionEventDemo.java

~~~java
package demo;

import javax.sql.DataSource;
import java.util.concurrent.atomic.AtomicInteger;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class NoTransactionEventDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            OrderService service = ctx.getBean(OrderService.class);
            Counters counts = ctx.getBean(Counters.class);

            jdbc.execute(
                "CREATE TABLE demo_orders (" +
                "id BIGINT PRIMARY KEY, status VARCHAR(30) NOT NULL)"
            );

            // 1. Publication ngoài Spring transaction.
            if (TransactionSynchronizationManager.isActualTransactionActive()) {
                throw new AssertionError("main should have no transaction");
            }
            ctx.publishEvent(new OrderCreated(100L));
            counts.print("outside", jdbc);

            // 2. Transaction được commit khi service proxy trả về.
            service.createAndCommit(200L);
            counts.print("commit", jdbc);

            // 3. RuntimeException làm transaction rollback.
            try {
                service.createAndRollback(300L);
            } catch (IllegalStateException ex) {
                System.out.println("rollback cause=" + ex.getMessage());
            }
            counts.print("rollback", jdbc);
        }
    }

    public record OrderCreated(long orderId) {}

    // Class không final để Spring tạo class-based transaction proxy.
    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher events;

        public OrderService(JdbcTemplate jdbc,
                ApplicationEventPublisher events) {
            this.jdbc = jdbc;
            this.events = events;
        }

        @Transactional
        public void createAndCommit(long id) {
            assertTransaction();
            jdbc.update(
                "INSERT INTO demo_orders (id, status) VALUES (?, ?)",
                id, "CREATED"
            );
            events.publishEvent(new OrderCreated(id));
        }

        @Transactional
        public void createAndRollback(long id) {
            assertTransaction();
            jdbc.update(
                "INSERT INTO demo_orders (id, status) VALUES (?, ?)",
                id, "CREATED"
            );
            events.publishEvent(new OrderCreated(id));
            throw new IllegalStateException("force rollback");
        }

        private void assertTransaction() {
            if (!TransactionSynchronizationManager
                    .isActualTransactionActive()) {
                throw new AssertionError("transaction proxy not active");
            }
        }
    }

    public static final class Counters {
        private final AtomicInteger ordinary = new AtomicInteger();
        private final AtomicInteger afterCommit = new AtomicInteger();
        private final AtomicInteger fallback = new AtomicInteger();
        private final AtomicInteger afterRollback = new AtomicInteger();

        @EventListener
        public void regular(OrderCreated event) {
            ordinary.incrementAndGet();
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void committed(OrderCreated event) {
            afterCommit.incrementAndGet();
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT,
            fallbackExecution = true
        )
        public void committedOrFallback(OrderCreated event) {
            fallback.incrementAndGet();
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK
        )
        public void rolledBack(OrderCreated event) {
            afterRollback.incrementAndGet();
        }

        public void print(String label, JdbcTemplate jdbc) {
            Long rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_orders", Long.class
            );
            System.out.println(
                label +
                ": ordinary=" + ordinary.get() +
                " afterCommit=" + afterCommit.get() +
                " fallback=" + fallback.get() +
                " afterRollback=" + afterRollback.get() +
                " rows=" + rows
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:event273;DB_CLOSE_DELAY=-1");
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
        public Counters counters() {
            return new Counters();
        }
    }
}
~~~

### Cách chạy

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.NoTransactionEventDemo
~~~

Các dòng do chương trình in theo thứ tự, với cấu hình đồng bộ mặc định:

~~~text
outside: ordinary=1 afterCommit=0 fallback=1 afterRollback=0 rows=0
commit: ordinary=2 afterCommit=1 fallback=2 afterRollback=0 rows=1
rollback cause=force rollback
rollback: ordinary=3 afterCommit=1 fallback=2 afterRollback=1 rows=1
~~~

Maven và Spring có thể in log kỹ thuật khác. Bốn dòng trên là output do code ứng dụng chủ động in.

### Giải thích từng nhánh

**Nhánh outside:** `ctx.publishEvent(new OrderCreated(100L))` nằm ở main, không qua service transactional. Listener thường được gọi, fallback listener được gọi, nhưng `AFTER_COMMIT` mặc định và `AFTER_ROLLBACK` không được gọi. DB chưa có dữ liệu.

**Nhánh commit:** `service.createAndCommit(200L)` được gọi qua **Spring bean proxy**. Transaction JDBC bắt đầu, INSERT ID 200, publish event trong transaction, listener thường tăng counter ngay. Hai listener có phase `AFTER_COMMIT` đăng ký callback; sau commit, cả hai tăng counter. Ở nhánh này, listener bật fallback vẫn dùng **đường transactional**, không phải fallback, vì transaction tồn tại.

**Nhánh rollback:** `service.createAndRollback(300L)` INSERT ID 300 rồi publish event, sau đó ném unchecked exception. Listener thường đã được gọi; phase `AFTER_COMMIT` không chạy vì rollback; `AFTER_ROLLBACK` chạy. Row 300 bị rollback, nên sau ba nhánh chỉ còn một row được commit.

Ví dụ tạo transaction thật bằng `DataSourceTransactionManager`; khi demo chạy thành công, assertion ngầm về thời điểm commit/rollback được chứng minh bằng DB row count. Ví dụ **không** kiểm chứng delivery bền vững sau process crash, message broker hoặc transaction reactive.

## 5. Chẩn đoán tại điểm publish, không chỉ nhìn annotation

Cách đáng tin hơn việc hỏi “method có `@Transactional` không?” là kiểm tra **trạng thái transaction ngay trước `publishEvent`**.

~~~java
boolean actual =
    TransactionSynchronizationManager.isActualTransactionActive();
boolean sync =
    TransactionSynchronizationManager.isSynchronizationActive();

log.info("Publishing OrderPlaced: txActive={}, sync={}",
    actual, sync);

publisher.publishEvent(new OrderPlaced(orderId));
~~~

Đây là code minh họa imperative với logger, `OrderPlaced` và publisher của ứng dụng. Kết quả giúp phân biệt:

- `actual=true` và `sync=true`: thường có transaction và synchronization thích hợp cho đăng ký callback, nhưng **chưa chắc commit thành công**.
- `actual=false`: có thể không có transaction thực tế; cần xem call graph/propagation.
- `sync=true`, `actual=false`: synchronization scope không tự chứng minh có transaction mà listener cần.
- `actual=true`, `sync=false`: cấu hình đặc biệt; cần kiểm tra transaction manager/synchronization activation.

**Cảnh báo:** `TransactionSynchronizationManager` trong đoạn này là API imperative dùng ThreadLocal. Trong transaction reactive, `ReactiveTransactionManager` gắn trạng thái với **Reactor Context**; kiểm tra ThreadLocal imperative bằng false **không đủ để chứng minh reactive transaction vắng mặt**.

## 6. Nguyên nhân phổ biến: self-invocation làm @Transactional bị bỏ qua

~~~java
@Service
public class CheckoutService {

    public void checkout(long id) {
        this.saveAndPublish(id);
    }

    @Transactional
    public void saveAndPublish(long id) {
        repository.insert(id);
        publisher.publishEvent(new OrderCreated(id));
    }
}
~~~

Đây là mã minh họa (cần repository, publisher, imports và bean). Với **Spring AOP proxy mode** mặc định, lời gọi `this.saveAndPublish(id)` không đi qua Spring transactional proxy. Method có annotation nhưng **transaction dự định có thể không được bắt đầu**. Khi publish event, transactional listener mặc định bị bỏ qua.

Cách xử lý thường rõ nhất là tách boundary sang bean khác:

~~~java
@Service
public class CheckoutWorkflow {
    private final TransactionalOrderService orders;

    public CheckoutWorkflow(TransactionalOrderService orders) {
        this.orders = orders;
    }

    public void checkout(long id) {
        orders.saveAndPublish(id); // Đi qua proxy của bean khác.
    }
}

@Service
public class TransactionalOrderService {
    @Transactional
    public void saveAndPublish(long id) {
        repository.insert(id);
        publisher.publishEvent(new OrderCreated(id));
    }
}
~~~

Đây là các class tích hợp cần collaborator tương ứng. Không dùng `new TransactionalOrderService()` rồi gọi trực tiếp: object tự tạo không được Spring tạo transaction proxy. Khi dùng AspectJ weaving hoặc programmatic transactions, đường interception khác với proxy mặc định; bài này tập trung vào cách Spring AOP thường gặp.

Những dấu hiệu khác làm `@Transactional` không áp dụng:

- Lời gọi tới method `private`/không intercept được qua proxy, hoặc class/method `final` không tương thích class-based proxy.
- Object không phải Spring-managed bean.
- Chưa bật `@EnableTransactionManagement` ở Spring Framework thuần hoặc cấu hình transaction infrastructure sai.
- Có nhiều transaction manager nhưng method chọn nhầm manager hoặc tài nguyên.
- Một method init/lifecycle được gọi trước khi proxy sẵn sàng.
- Method transactional đã trả về trước khi lời gọi `publishEvent` thực sự xảy ra.

Đừng dùng `fallbackExecution=true` làm “cách sửa” self-invocation; nó có thể khiến event được xử lý nhưng **không bảo đảm write DB nằm trong transaction**.

## 7. Propagation: @Transactional không phải lúc nào cũng mở transaction

Các propagation mode ảnh hưởng trực tiếp đến việc có transaction active tại điểm publish.

| Propagation | Khi caller không có transaction | Tác động đến listener |
|---|---|---|
| `REQUIRED` mặc định | Bắt đầu transaction mới | Có thể đăng ký callback |
| `REQUIRES_NEW` | Bắt đầu transaction riêng | Callback gắn với transaction mới |
| `SUPPORTS` | Tiếp tục không có transaction | Default listener có thể bị bỏ |
| `NOT_SUPPORTED` | Chạy không transaction, suspend transaction ngoài nếu có | Default listener có thể bị bỏ |
| `MANDATORY` | Ném exception nếu không có transaction | Không phát event theo đường thành công |
| `NEVER` | Chạy khi không có transaction, ném lỗi nếu có | Default listener có thể bị bỏ |

Ví dụ:

~~~java
@Transactional(propagation = Propagation.SUPPORTS)
public void emit(String orderId) {
    publisher.publishEvent(new OrderCreated(orderId));
}
~~~

Đây là mẫu minh họa với event type có trường `orderId` dạng `String`. `SUPPORTS` không tạo transaction vật lý mới khi caller không có T1. Vì thế, **có annotation vẫn chưa đủ** để bảo đảm `@TransactionalEventListener` được gọi.

`@Transactional(readOnly=true)` với `REQUIRED` vẫn có thể tạo transaction; `readOnly` là một thuộc tính/hint và **không đồng nghĩa vắng transaction**. Chọn propagation theo nghiệp vụ thật sự, không chọn chỉ để “làm callback chạy”.

## 8. Publication bị đặt sau transaction boundary

Một bẫy khác:

~~~java
public void checkout(String id) {
    OrderSaved saved = orderService.save(id);
    publisher.publishEvent(new OrderCreated(saved.id()));
}

@Service
class OrderService {
    @Transactional
    public OrderSaved save(String id) {
        // Lưu dữ liệu; transaction commit khi lời gọi qua proxy kết thúc.
    }
}
~~~

Đây là code kiến trúc minh họa, cần định nghĩa `OrderSaved`, `OrderCreated`, bean và các thành phần lưu trữ. Lệnh publish xảy ra **sau khi `orderService.save(id)` trả về**, thường là sau khi transaction của service đã commit. Vì vậy trong `checkout` **có thể không còn transaction**.

Nếu contract yêu cầu event gắn với commit của chính thay đổi DB ấy, đặt publication vào method transactional:

~~~java
@Transactional
public void saveAndPublish(String id) {
    repository.save(...);
    publisher.publishEvent(new OrderCreated(id));
}
~~~

Đây là đoạn tích hợp. Nếu transaction commit thành công, listener `AFTER_COMMIT` có thể được gọi đúng phase. Nếu transaction rollback, listener `AFTER_COMMIT` không chạy.

**Không mở một transaction rỗng sau khi DB đã commit chỉ để tạo “phase AFTER_COMMIT”.** Transaction mới đó không phải transaction gốc của thay đổi. Khi cần phát event chắc chắn sau commit, xem xét transactional outbox.

## 9. Async, scheduler và ThreadLocal transaction

Trong transaction imperative của Spring (JDBC/JPA), trạng thái transaction gắn với thread. Một worker `@Async` không tự nhận transaction T1 từ thread gọi:

~~~java
@Service
public class AsyncPublisher {
    private final ApplicationEventPublisher events;

    public AsyncPublisher(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Async("taskExecutor")
    public void publishLater(OrderCreated event) {
        events.publishEvent(event);
    }
}
~~~

Đây là code tích hợp: cần `@EnableAsync`, bean executor, proxy và imports. Nếu một HTTP request giữ transaction T1 ở thread A, rồi dispatch `publishLater` sang worker B, worker B **không có cùng ThreadLocal transaction** chỉ vì được tạo trong đường gọi ban đầu. Event phát ở B có thể bị transactional listener bỏ qua.

Phân biệt:

1. **Publisher chạy async:** event được phát từ thread không có transaction của caller, nên registration có thể thất bại.
2. **Listener được đánh dấu `@Async`:** registration của `@TransactionalEventListener` gắn với publication trong transaction; sau phase, phần thân có thể chạy trong executor, nhưng worker không tự có transaction JDBC gốc.

Spring Framework 6.1+ cung cấp khả năng để transactional listener yêu cầu việc đăng ký synchronization diễn ra trên thread gốc thay vì executor tùy ý chuyển dispatch. Tuy nhiên, điều đó **không** làm transaction context có thể chia sẻ tự do giữa threads.

Nếu công việc ở worker cần đọc/ghi DB, hãy mở **transaction riêng trong worker** (qua proxy hoặc `TransactionTemplate`) với ranh giới rõ ràng; tránh copy ThreadLocal transaction bằng tay. Chuyển tracing context/MDC cũng không tương đương chuyển transaction.

## 10. Transaction reactive nằm trong Reactor Context, không phải ThreadLocal

Từ Spring Framework **6.1**, `@TransactionalEventListener` hỗ trợ cả imperative transactions (qua `PlatformTransactionManager`) và reactive transactions (qua `ReactiveTransactionManager`), nhưng reactive có cơ chế liên kết khác.

| Imperative | Reactive |
|---|---|
| Thread-bound transaction | Transaction trong Reactor subscriber Context |
| Có thể kiểm tra bằng imperative `TransactionSynchronizationManager` | Không dùng ThreadLocal imperative làm bằng chứng duy nhất |
| Publisher thường chạy đồng bộ trong cùng thread | Publisher chạy trong pipeline/subscription |
| Listener có thể thấy transaction gắn với thread | Event cần có `TransactionContext` làm **source** |

Nếu publish bằng `ApplicationEventPublisher` thông thường trong một reactive flow:

~~~java
publisher.publishEvent(new OrderCreated(orderId));
~~~

đoạn này **không tự đặt `TransactionContext` vào event source**, nên transactional listener có thể không liên kết được với transaction reactive.

Spring cung cấp `TransactionalEventPublisher`:

~~~java
// Mẫu tích hợp: chạy bên trong reactive transaction pipeline.
return transactionalEventPublisher.publishEvent(context ->
    new PayloadApplicationEvent<>(
        context,
        new OrderCreated(orderId)
    )
);
~~~

Đoạn trên cần `TransactionalEventPublisher`, `PayloadApplicationEvent`, event payload và `TransactionalOperator` hoặc một transaction reactive boundary thích hợp. API `publishEvent(Function<TransactionContext, ApplicationEvent>)` cho phép **đặt TransactionContext làm source**. Đây không phải một chương trình độc lập; không được dùng với kỳ vọng transaction reactive tự xuất hiện nếu pipeline chưa được subscribe hoặc không có transaction.

Tránh:

~~~java
// Phản ví dụ: subscription tách khỏi flow đang được quản lý.
someReactivePublisher.subscribe();
~~~

Lời gọi `subscribe()` thủ công có thể tạo một đường subscription riêng, không giữ context transaction như kỳ vọng. Ưu tiên compose bằng `flatMap`, `then` trong cùng pipeline rồi kiểm thử bằng `StepVerifier`. `fallbackExecution=true` **không thay thế** việc đưa reactive transaction context vào event source.

## 11. Không có transaction và transaction rollback là hai nguyên nhân khác nhau

Cùng một listener `AFTER_COMMIT` im lặng có thể do hai tình huống:

~~~text
A. Publish ngoài transaction
   -> Không thể đăng ký callback
   -> fallback=false: event bị bỏ qua đối với listener

B. Publish trong T1
   -> Callback AFTER_COMMIT được đăng ký
   -> T1 rollback
   -> AFTER_COMMIT không chạy vì không có commit thành công
~~~

Muốn phát hiện đường B, dùng phase khác:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollback(OrderCreated event) {
    metrics.recordRollback(event.orderId());
}
~~~

Đoạn này chỉ chạy khi transaction rollback và callback đã được đăng ký thành công. Nếu listener thường ném exception trước khi adapter transactional kịp đăng ký synchronization, kết quả có thể khác; khi điều tra cần kiểm tra `@Order`/`ErrorHandler` và thứ tự dispatch.

**Không phải cứ thiếu log AFTER_COMMIT là lỗi transaction manager**. Có thể đó là một rollback hợp lệ, một sai lệch event type, một filter `condition` không match hoặc callback thất bại ở bước xử lý.

## 12. Kiểm tra Spring beans và ApplicationContext trước khi kết luận

Một số vấn đề không liên quan transaction nhưng biểu hiện giống nhau:

- Listener không được Spring scan/đăng ký dưới dạng bean.
- Publisher và listener ở các `ApplicationContext` khác nhau, không có quan hệ truyền event mong đợi.
- Tham số method listener không đúng event type.
- Có `condition` SpEL khiến listener bị bỏ qua.
- Spring Test slice không nạp bean observer.
- Custom multicaster hoặc proxy thay đổi chính sách dispatch.
- Event phát trước khi listener được đăng ký, ví dụ trong giai đoạn bootstrap sớm.

Chiến lược khoanh vùng:

~~~java
@EventListener
public void verifyDelivery(OrderCreated event) {
    log.debug("OrderCreated reached this context");
}
~~~

Nếu listener thường **cũng không** nhận event, hãy kiểm tra wiring/context/type trước. Nếu listener thường nhận nhưng transactional listener không nhận, chuyển sang kiểm tra transaction tại điểm publish.

Không nên tự đọc hoặc sửa toàn bộ cấu hình ứng dụng chỉ vì một listener im lặng; bắt đầu từ một lần publication cụ thể có thể tái hiện được.

## 13. Vì sao đặt @Transactional trên listener không đủ?

Một cách sửa không giải quyết gốc:

~~~java
@TransactionalEventListener
@Transactional
public void onOrderCreated(OrderCreated event) {
    repository.saveAudit(event.orderId());
}
~~~

Vấn đề: nếu publication xảy ra ngoài transaction và `fallbackExecution=false`, Spring bỏ qua event **trước khi gọi method listener**. Transaction interceptor trên method đó **không có cơ hội khởi tạo transaction** để cứu event đã bị bỏ.

Khi listener đúng là hậu commit và cần ghi database, còn một lưu ý khác: Spring Javadoc cảnh báo resource transaction gốc có thể vẫn gắn với thread trong callback completion, khiến thao tác DB tham gia resource cũ mà **không được commit thêm**. Có thể tách công việc ghi DB sang bean khác:

~~~java
@Component
public class OrderObserver {
    private final AuditWriter writer;

    public OrderObserver(AuditWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreated event) {
        writer.persist(event.orderId());
    }
}

@Service
public class AuditWriter {
    private final AuditRepository repository;

    public AuditWriter(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void persist(long orderId) {
        repository.insertAudit(orderId);
    }
}
~~~

Đây là hai class minh họa tích hợp với `AuditRepository` của ứng dụng và imports tương ứng. Lời gọi sang bean `AuditWriter` đi qua Spring proxy, nên `REQUIRES_NEW` tạo một transaction riêng cho công việc DB. **Nó không làm event đã bị bỏ được xử lý**; chỉ giải quyết ranh giới lưu DB sau khi listener đã thực sự được gọi.

## 14. Debug logs cho transaction và event routing

Với ứng dụng Spring Boot có logging backend được cấu hình, có thể tạm tăng mức log:

~~~properties
logging.level.org.springframework.transaction=DEBUG
logging.level.org.springframework.transaction.event=TRACE
logging.level.org.springframework.context.event=DEBUG
~~~

Đây là cấu hình tham khảo, không cam kết mọi phiên bản đều in một chuỗi log cố định. Các bước kiểm tra:

1. Service entry point có đi qua Spring proxy?
2. Transaction manager nào bắt đầu transaction?
3. `publishEvent` xảy ra ở thread nào?
4. Ngay trước publish, `actualTx`/`sync` là gì?
5. Event có được đúng `ApplicationContext` dispatch?
6. Listener transaction có đúng `phase`/`fallbackExecution`?
7. Transaction cuối cùng commit hay rollback?
8. Nếu method callback đã chạy mà side effect thiếu, việc ghi DB hay gọi API ngoài có thật sự thành công?

Không log credentials, token, email, toàn bộ event payload nhạy cảm hoặc thông tin tài chính ra debug logs. Hạ mức log sau khi xác định nguyên nhân.

## 15. Kiểm thử đúng: ngoài transaction, commit, rollback

Với `spring-test` và JUnit Jupiter, nên có ít nhất ba integration tests.

**Test ngoài transaction:** một test method không có `@Transactional` gọi publish trực tiếp. Assert listener thường nhận, listener default `AFTER_COMMIT` không nhận, listener fallback nhận. Nếu test có transaction do một base class hoặc meta-annotation khai báo, kết quả sẽ khác.

~~~java
@Test
void outsideTransactionDropsDefaultListener() {
    publisher.publishEvent(new OrderCreated(273L));
    assertEquals(0, counters.afterCommit());
    assertEquals(1, counters.fallback());
}
~~~

**Test commit:** gọi một Spring service bean có `@Transactional`, phát event trong method rồi để service trả về/commit; assert AFTER_COMMIT đã xử lý và row DB tồn tại.

~~~java
@Test
void commitRunsAfterCommitListener() {
    transactionalService.saveAndPublish(273L);
    assertEquals(1, counters.afterCommit());
    assertEquals(1, repository.countCommittedRows());
}
~~~

**Test rollback:** service publish rồi ném unchecked exception khiến transaction rollback; assert AFTER_COMMIT không chạy, AFTER_ROLLBACK chạy và DB không chứa row mới.

~~~java
@Test
void rollbackSkipsAfterCommit() {
    assertThrows(IllegalStateException.class,
        () -> transactionalService.saveAndFail(273L));
    assertEquals(0, counters.afterCommit());
    assertEquals(1, counters.afterRollback());
}
~~~

Ba đoạn trên là **mã test minh họa**, cần JUnit, fake counters hoặc context mới cho mỗi test, service và repository tương ứng. Reset bộ đếm và dữ liệu giữa test; không dùng chung state gây flakiness.

### Bẫy test method có @Transactional

Spring TestContext thường rollback transaction do test quản lý ở cuối test:

~~~java
@Test
@Transactional
void thisTestUsuallyRollsBack() {
    transactionalService.saveAndPublish(273L);
    // AFTER_COMMIT chưa chạy ở đây; transaction test còn mở.
}
~~~

Muốn kiểm thử hậu commit, có thể không khai báo `@Transactional` trên test method, hoặc sử dụng:

~~~java
TestTransaction.flagForCommit();
TestTransaction.end();
// Sau khi kết thúc transaction test, mới assert callback AFTER_COMMIT.
~~~

Đây là đoạn test tích hợp, cần `org.springframework.test.context.transaction.TestTransaction` và một test-managed transaction thực sự active. Không gọi `TestTransaction` nếu thiếu TestContext transaction.

### Có thể dùng @RecordApplicationEvents không?

Có, nhưng phân biệt **event đã được publish** với **listener đã chạy**. `ApplicationEvents.stream(OrderCreated.class).count()` có thể lớn hơn 0 ngay cả khi transaction rollback hoặc listener `AFTER_COMMIT` không được gọi. Muốn chứng minh callback chạy, assert collaborator giả, state DB hoặc một tín hiệu hoàn tất riêng; muốn chứng minh publication, kiểm tra `ApplicationEvents`.

## 16. Fallback không thay thế durability

Có transaction và listener `AFTER_COMMIT` chạy đúng phase vẫn không đồng nghĩa message bền vững. Có cửa sổ:

~~~text
T1: COMMIT Order
      |
      +-- JVM crash / service bị kill
      |
      +-- AFTER_COMMIT callback có thể chưa thực hiện
      |
      +-- Không có durable record để phát lại
~~~

Đối với tác vụ quan trọng (email hóa đơn, thông báo thanh toán, tạo tài liệu bắt buộc, đồng bộ liên dịch vụ), cân nhắc **transactional outbox**:

~~~text
BEGIN T1
  INSERT / UPDATE orders(...)
  INSERT outbox_events(event_id, aggregate_id, payload, status='PENDING')
COMMIT T1
        |
        +-- Worker đọc outbox
        +-- Publish message / gọi API ngoài
        +-- Retry với backoff và ghi trạng thái
        +-- Consumer dedupe theo eventId
~~~

Cả thay đổi nghiệp vụ và outbox row nằm trong cùng transaction local nên rollback T1 rollback cả hai. Process chết sau commit vẫn để lại outbox record. Nhưng relay có thể gửi lại message khi crash giữa gửi và đánh dấu hoàn tất; do đó cần idempotency. `@TransactionalEventListener`, `fallbackExecution` và `@Async` đều **không tự tạo exactly-once delivery**.

Nếu event hoàn toàn không gắn với DB transaction (ví dụ tín hiệu lifecycle của ứng dụng hoặc cập nhật in-memory), dùng `@EventListener` thường có thể là lựa chọn trung thực hơn về semantics.

## 17. Bảng triệu chứng – nguyên nhân – cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `@EventListener` chạy nhưng transactional listener im lặng | Thiếu transaction lúc publish | Ghi txActive tại điểm publish; sửa boundary |
| Bật fallback thì listener chạy | Đường publish non-transactional | Xác định có được phép xử lý ngay hay cần AFTER_COMMIT thật |
| `@Transactional` hiện diện nhưng txActive=false | Self-invocation hoặc object không qua proxy | Gọi Spring-managed bean qua proxy |
| `@Transactional(SUPPORTS)` nhưng không có T1 | SUPPORTS không tự mở transaction vật lý | Chọn REQUIRED nếu nghiệp vụ yêu cầu |
| Publish sau service.save() | T1 đã commit rồi | Publish bên trong service transactional hoặc dùng outbox |
| Worker `@Async` publish event | Transaction ThreadLocal không đi qua thread | Tạo boundary transaction trong worker hoặc đổi điểm publish |
| Có R2DBC transaction nhưng listener im lặng | Thiếu TransactionContext ở event source | Dùng TransactionalEventPublisher trong cùng subscription |
| Default AFTER_COMMIT không chạy, AFTER_ROLLBACK chạy | Transaction rollback, không phải thiếu transaction | Điều tra exception và rollback-only |
| AFTER_COMMIT chạy nhưng audit không được commit | Resource cũ ở completion | Gọi REQUIRES_NEW qua proxy bean khác |
| Test method @Transactional không thấy callback | Test thường rollback cuối test | Commit thật hoặc không tạo test transaction |
| Tất cả listeners đều không nhận | Sai event type/bean/context | Kiểm tra wiring và ApplicationContext |
| Muốn tránh mất event sau crash | Event trong JVM không durable | Dùng outbox, queue, retry và idempotency |

## 18. Checklist trước khi kết luận lỗi đã được sửa

1. Biết chính xác **event type** và bean phát nó.
2. Xác nhận bean listener nằm trong đúng context.
3. Xác nhận `@EventListener` đối chứng có thể nhận event.
4. Ghi trạng thái transaction **ngay tại publication**, không chỉ ở đầu request.
5. Kiểm tra call path qua transactional proxy, tránh self-invocation.
6. Kiểm tra propagation, transaction manager, datasource/resource.
7. Xác nhận event phát **trong** hay **sau** method transaction.
8. Xác định thread, executor, scheduler, reactor subscription.
9. Với reactive transaction, kiểm tra event source có TransactionContext.
10. Phân biệt callback đang chờ commit, callback bị bỏ, callback sau rollback.
11. Chọn fallback theo semantics, không theo mong muốn “cho chạy là được”.
12. Tách transaction mới cho thao tác DB sau completion nếu cần.
13. Test ba nhánh outside/commit/rollback bằng transaction manager thật.
14. Nếu xử lý quan trọng, bổ sung durable outbox/queue.
15. Ghi metric/log kết quả callback và tắt debug chi tiết sau chẩn đoán.

## 19. Câu hỏi tự kiểm tra

**1. Vì sao `@TransactionalEventListener` mặc định im lặng nếu publish trong main?** Vì không có transaction để đăng ký callback theo phase, và `fallbackExecution` mặc định false.

**2. Bật `fallbackExecution=true` có tạo transaction?** Không. Nó cho phép chạy ngay ngoài transaction; không có commit/rollback tương ứng.

**3. `@TransactionalEventListener(AFTER_ROLLBACK, fallbackExecution=true)` có thể chạy dù không rollback?** Có, trên đường fallback không có transaction.

**4. `@Transactional(propagation=SUPPORTS)` có bảo đảm transaction tồn tại?** Không. Nếu caller không có transaction, SUPPORTS có thể chạy không transaction.

**5. Đặt `@Transactional` trên listener có cứu event bị bỏ không?** Không, vì method listener có thể không được gọi đến.

**6. Vì sao có reactive transaction nhưng `isActualTransactionActive()` imperative trả false?** Vì reactive transaction nằm trong Reactor Context, không phải ThreadLocal imperative.

**7. Khi publish trong T1 rồi T1 rollback, `AFTER_COMMIT` có chạy không?** Không. Đó là hành vi đúng, khác với trường hợp không có T1.

**8. Vì sao test `@Transactional` không thấy callback `AFTER_COMMIT`?** Test-managed transaction thường chưa commit khi assert và thường rollback khi test kết thúc.

**9. Khi nào nên dùng `@EventListener` thường?** Khi xử lý event không phụ thuộc outcome transaction và không cần phase-bound semantics.

**10. Outbox khác gì fallback?** Outbox lưu event bền cùng thay đổi DB; fallback chỉ điều chỉnh listener có xử lý khi không có transaction hay không.

## 20. Kết luận và nguồn chính thức

**Không có transaction tại thời điểm publish là nguyên nhân trực tiếp khiến `@TransactionalEventListener` mặc định không xử lý event.** Bật `fallbackExecution=true` có thể làm listener chạy ngoài transaction, nhưng không tạo commit, không truyền ThreadLocal sang worker và không bảo đảm durability. Chẩn đoán hiệu quả nhất là tìm đúng publication boundary, transaction proxy/propagation, phase và thread/reactive context; sau đó quyết định nên sửa transaction boundary, chuyển sang `@EventListener` thường hay dùng outbox theo hợp đồng nghiệp vụ.

Tài liệu đối chiếu:

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): phase, fallbackExecution, reactive transaction.
- [Spring Framework 6.2.8 Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): default phase, discarded events, cảnh báo hậu completion.
- [Spring Framework 6.2.8 Javadoc — TransactionPhase](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionPhase.html): BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, AFTER_COMPLETION.
- [Spring Framework 6.2 — Declarative Transactions](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): proxy, @Transactional và propagation.
- [Spring Framework 6.2.8 Javadoc — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): kiểm tra transaction/synchronization imperative.
- [Spring Framework 6.2.8 Javadoc — TransactionalEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html): event source chứa TransactionContext.
