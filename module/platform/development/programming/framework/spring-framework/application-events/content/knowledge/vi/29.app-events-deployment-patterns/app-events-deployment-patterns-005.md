# Phát sự kiện sau commit trong Spring Framework Application Events

## 1. Bài toán: tại sao phải chờ transaction commit?

Trong ứng dụng Spring, một service có thể cập nhật database rồi phát sự kiện để gửi email, cập nhật chỉ mục tìm kiếm, làm mới cache, tạo job hoặc gọi hệ thống ngoài. Nếu hoạt động đó được thực hiện quá sớm, **transaction database có thể rollback nhưng side effect bên ngoài đã xảy ra**.

~~~java
@Transactional
public void placeOrder(long id) {
    orderRepository.insert(id);
    publisher.publishEvent(new OrderPlaced(id));
    // Một exception tại đây có thể làm rollback INSERT.
}
~~~

Đây là mã tích hợp, cần định nghĩa `orderRepository`, `publisher`, event `OrderPlaced` và Spring transaction manager. Theo cấu hình multicaster mặc định, phương thức `@EventListener` thường được gọi **đồng bộ ngay lúc `publishEvent`**, tức khi transaction có thể chưa commit.

~~~text
BEGIN T1
  INSERT orders(id=328)
  publishEvent(OrderPlaced)
      |
      +-- @EventListener -> gửi email thành công
  throw RuntimeException
ROLLBACK T1

Email đã gửi, nhưng database không còn order 328.
~~~

Một **mẫu phát sự kiện sau commit** đảm bảo công việc hậu kỳ chỉ được kích hoạt sau khi transaction tạo dữ liệu đã commit thành công. Tuy nhiên, cụm từ này thường chỉ **hai cơ chế khác nhau** trong Spring:

- **Mẫu A — publish trong transaction, listener xử lý sau commit.** Service gọi `ApplicationEventPublisher.publishEvent(event)` khi T1 còn mở, còn consumer sử dụng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. Hành động **publish xảy ra trước commit**; chỉ listener transaction-bound được trì hoãn.
- **Mẫu B — chỉ publish event sau commit thật sự.** Service đăng ký `TransactionSynchronization.afterCommit()` trong T1, rồi gọi `publisher.publishEvent(event)` bên trong callback. Lúc này **bản thân publication xảy ra sau commit**, nên một `@EventListener` thông thường cũng chỉ nhìn thấy event đó sau khi transaction thành công.

Hai cách có cùng mục tiêu nghiệp vụ trong nhiều trường hợp, nhưng khác nhau về semantic, các listener khác nhìn thấy event lúc nào, quản lý exception và cách tổ chức code.

**Quan trọng:** cả hai là cơ chế **in-process**, không tự trở thành durable event queue. Nếu JVM crash sau commit nhưng trước khi hậu xử lý hoàn tất, event/tác vụ vẫn có thể mất. Để không mất event trong tình huống đó, cần transactional outbox hoặc giải pháp durable tương ứng.

## 2. Cơ chế Spring Application Events và transaction phase

Spring Framework hỗ trợ:

~~~java
ApplicationEventPublisher publisher;
publisher.publishEvent(new OrderPlaced(328L));
~~~

Đây là mã minh họa; record `OrderPlaced` do ứng dụng định nghĩa. Event có thể là `ApplicationEvent` subclass hoặc POJO/record payload. Với `@EventListener`, Spring chọn method theo event type và dispatch theo `ApplicationEventMulticaster`.

### @EventListener bình thường

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationGateway.send(event.orderId());
}
~~~

Method này thường chạy ngay khi event được publish nếu multicaster mặc định đồng bộ. Nếu listener có `@Async` hoặc multicaster dùng executor khác, nó có thể chạy trên thread khác; nhưng điều đó **không** làm nó tự chờ commit.

### @TransactionalEventListener

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    notificationGateway.send(event.orderId());
}
~~~

Khi event được publish trong transaction phù hợp, Spring **đăng ký transaction synchronization** để gọi listener ở phase tương ứng. `AFTER_COMMIT` là phase mặc định:

~~~java
@TransactionalEventListener
public void on(OrderPlaced event) {
    // Mặc định AFTER_COMMIT.
}
~~~

Các phase:

| Phase | Khi chạy | Phù hợp khi |
|---|---|---|
| `BEFORE_COMMIT` | Trước lúc commit | Kiểm tra ràng buộc trước khi transaction được commit |
| `AFTER_COMMIT` | Sau khi commit thành công | Gửi thông báo hoặc kích hoạt công việc hậu commit |
| `AFTER_ROLLBACK` | Sau rollback | Ghi nhận lỗi, compensation được thiết kế rõ |
| `AFTER_COMPLETION` | Sau commit hoặc rollback | Cleanup/metrics không phụ thuộc outcome |

Khi **không có transaction** lúc publication, `@TransactionalEventListener` mặc định **bỏ qua event**. Có thể bật `fallbackExecution = true` để thực thi ngay trong đường non-transactional, nhưng **không có commit để chờ**.

## 3. Mẫu A: publish bên trong transaction và xử lý bằng @TransactionalEventListener

Đây là cách khai báo thường đơn giản nhất khi ứng dụng có một số subscriber cần chạy sau commit.

~~~java
public record OrderPlaced(long orderId) {}

@Service
public class OrderService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher events;

    public OrderService(OrderRepository repository,
                        ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void create(long id) {
        repository.insert(id);
        events.publishEvent(new OrderPlaced(id));
    }
}

@Component
public class ReceiptListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void sendReceipt(OrderPlaced event) {
        emailService.send(event.orderId());
    }
}
~~~

Đây là **mã tích hợp**, cần bean `OrderRepository`, `emailService` và các imports. Spring sẽ xử lý:

~~~text
HTTP / command
   |
   v
OrderService.create()
   |
   +-- BEGIN T1
   +-- INSERT orders
   +-- publishEvent(OrderPlaced)
   |      |
   |      +-- @EventListener thông thường có thể chạy ngay
   |      +-- @TransactionalEventListener AFTER_COMMIT đăng ký callback
   |
   +-- RETURN khỏi service body
   +-- COMMIT T1
          |
          +-- thành công -> sendReceipt()
          |
          +-- rollback -> KHÔNG gọi sendReceipt()
~~~

**Đừng nói `OrderPlaced` chỉ “được publish sau commit” trong mẫu này.** Event đã được publish trong T1; chỉ phương thức `sendReceipt` được chạy sau commit. Nếu có listener khác:

~~~java
@EventListener
public void auditImmediately(OrderPlaced event) {
    // Vẫn có thể chạy TRƯỚC commit.
}
~~~

nó có thể thấy event trước commit. Nếu toàn bộ các listener phải nhìn thấy event chỉ sau commit, cần dùng **mẫu B**, một event hậu commit riêng hoặc giải pháp durable.

### Vị trí publication phải nằm trong T1

Sai lầm:

~~~java
public void checkout(long id) {
    orderService.saveWithinTransaction(id); // T1 commit rồi mới return.
    publisher.publishEvent(new OrderPlaced(id)); // Có thể ngoài T1.
}
~~~

Nếu publisher gọi sau khi transaction service đã kết thúc, transactional listener mặc định có thể bỏ event vì không còn transaction active để đăng ký callback. **Đặt lệnh publish trong phương thức thật sự chạy trong T1**, không chỉ trong controller gọi một service transactional trước đó.

## 4. Mẫu B: đăng ký TransactionSynchronization.afterCommit để mới publish

Nếu tên event mang nghĩa “thay đổi đã được commit”, publisher có thể hoãn toàn bộ publication.

~~~java
@Transactional
public void create(long id) {
    orderRepository.insert(id);

    if (!TransactionSynchronizationManager.isActualTransactionActive()
            || !TransactionSynchronizationManager.isSynchronizationActive()) {
        throw new IllegalStateException("Expected an active transaction");
    }

    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                publisher.publishEvent(new OrderCommitted(id));
            }
        }
    );
}
~~~

Đây là **mã tích hợp**, cần các import:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
~~~

và kiểu `OrderCommitted`, Spring-managed service/repository. `afterCommit()` là callback được kích hoạt **chỉ khi commit thực sự thành công**.

Một listener thông thường nhận event mới:

~~~java
@EventListener
public void onCommitted(OrderCommitted event) {
    notificationGateway.send(event.id());
}
~~~

Ở mẫu B, chính lệnh `publishEvent(new OrderCommitted(id))` chưa được thực hiện trước commit, nên mọi listener nhận **event này** chỉ có thể được trigger sau khi callback hậu commit chạy.

### So sánh trực tiếp

| Đặc điểm | Mẫu A: `@TransactionalEventListener` | Mẫu B: `afterCommit()` publish |
|---|---|---|
| Publication của event | Trước commit, trong T1 | Sau commit, trong callback |
| Ai chọn phase? | Từng listener | Publisher |
| `@EventListener` thường của cùng event | Có thể chạy trước commit | Chỉ chạy khi event được publish hậu commit |
| T1 rollback | Listener AFTER_COMMIT không chạy | Callback không publish |
| Không có T1 | Transaction listener mặc định bỏ qua | Không thể đăng ký callback hợp lệ |
| Coupling | Publisher độc lập với transaction phase | Publisher biết đến transaction synchronization |
| Độ bền qua JVM crash | Không bảo đảm | Không bảo đảm |

Nếu một ứng dụng muốn vừa có nghiệp vụ “OrderPlaced nội bộ T1” vừa có notification “OrderCommitted hậu T1”, có thể dùng **hai event type khác nhau** với ý nghĩa rõ ràng, thay vì gọi đi gọi lại một class event.

### Không coi afterCommit() là transaction mới

Khi `TransactionSynchronization.afterCommit()` chạy, T1 đã commit. Callback này **không mở T2**. Một repository write mới cần transaction rõ ràng nếu muốn chắc chắn được commit; xem mục 8.

## 5. Ví dụ Java 17 runnable: cả hai mẫu, commit, rollback và no transaction

Ví dụ sau dùng **Spring Framework 6.2.8**, Java 17+, Maven, `spring-jdbc` và H2 in-memory. Mục tiêu là chứng minh:

1. Khi commit, `OrderCreated` có listener thường xử lý ngay và `@TransactionalEventListener(AFTER_COMMIT)` xử lý sau; đồng thời callback `afterCommit()` phát `OrderCommittedSignal` cho listener thường khác.
2. Khi rollback, listener thường của `OrderCreated` đã chạy, nhưng **cả hai** đường hậu commit đều không chạy.
3. Khi publish ngoài transaction, listener thường vẫn nhận `OrderCreated`, còn transactional listener mặc định bỏ qua.

### 5.1. Cấu trúc

~~~text
after-commit-demo/
├── pom.xml
└── src/main/java/demo/AfterCommitDemo.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>after-commit-demo</artifactId>
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
                <version>3.13.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
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

### 5.3. src/main/java/demo/AfterCommitDemo.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

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
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class AfterCommitDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService service = context.getBean(OrderService.class);
            Counters counters = context.getBean(Counters.class);

            jdbc.execute(
                "CREATE TABLE orders(" +
                "id BIGINT PRIMARY KEY, state VARCHAR(20) NOT NULL)"
            );

            // Thành công: commit kích hoạt hai dạng hậu commit.
            service.create(1L, false);
            counters.print("commit", jdbc);

            // Thất bại: rollback, không có hậu commit.
            try {
                service.create(2L, true);
            } catch (IllegalStateException expected) {
                System.out.println("caught=" + expected.getMessage());
            }
            counters.print("rollback", jdbc);

            // Ngoài transaction: chỉ listener thường nhận sự kiện.
            context.publishEvent(new OrderCreated(3L));
            counters.print("no transaction", jdbc);
        }
    }

    public record OrderCreated(long id) {}
    public record OrderCommittedSignal(long id) {}

    // Không final để Spring có thể tạo class-based proxy.
    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void create(long id, boolean fail) {
            if (!TransactionSynchronizationManager
                    .isActualTransactionActive()
                    || !TransactionSynchronizationManager
                    .isSynchronizationActive()) {
                throw new IllegalStateException("no active transaction");
            }

            jdbc.update(
                "INSERT INTO orders(id, state) VALUES (?, ?)",
                id, "CREATED"
            );

            // Mẫu A: event được publish TRONG transaction.
            publisher.publishEvent(new OrderCreated(id));

            // Mẫu B: event khác chỉ được publish SAU commit.
            TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        publisher.publishEvent(
                            new OrderCommittedSignal(id));
                    }
                }
            );

            if (fail) {
                throw new IllegalStateException("force rollback");
            }
        }
    }

    public static class Counters {
        private final AtomicInteger immediate = new AtomicInteger();
        private final AtomicInteger transactionalCommitted =
            new AtomicInteger();
        private final AtomicInteger transactionalRollback =
            new AtomicInteger();
        private final AtomicInteger explicitPublication =
            new AtomicInteger();

        @EventListener
        public void immediate(OrderCreated event) {
            immediate.incrementAndGet();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderCreated event) {
            transactionalCommitted.incrementAndGet();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderCreated event) {
            transactionalRollback.incrementAndGet();
        }

        @EventListener
        public void onCommittedSignal(OrderCommittedSignal event) {
            explicitPublication.incrementAndGet();
        }

        public void print(String label, JdbcTemplate jdbc) {
            Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders", Integer.class);

            System.out.println(label +
                ": rows=" + rows +
                " immediate=" + immediate.get() +
                " afterCommit=" + transactionalCommitted.get() +
                " afterRollback=" + transactionalRollback.get() +
                " publishedAfterCommit=" + explicitPublication.get());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:after_commit328;DB_CLOSE_DELAY=-1");
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
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        public Counters counters() {
            return new Counters();
        }
    }
}
~~~

### 5.4. Chạy

Trong thư mục `after-commit-demo`, dùng JDK 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AfterCommitDemo
~~~

Các dòng **do chương trình in**, với multicaster mặc định đồng bộ (log phụ của Maven có thể khác):

~~~text
commit: rows=1 immediate=1 afterCommit=1 afterRollback=0 publishedAfterCommit=1
caught=force rollback
rollback: rows=1 immediate=2 afterCommit=1 afterRollback=1 publishedAfterCommit=1
no transaction: rows=1 immediate=3 afterCommit=1 afterRollback=1 publishedAfterCommit=1
~~~

### 5.5. Phân tích chi tiết từng nhánh

**Nhánh commit (ID 1):**

- `context.getBean(OrderService.class)` lấy **Spring-managed bean proxy**.
- `@Transactional` tạo T1; `INSERT orders(id=1)` nằm trong T1.
- `publisher.publishEvent(new OrderCreated(1))` được gọi trước commit. Listener thường tăng `immediate` lên 1 ngay.
- Transaction listener `AFTER_COMMIT` và `AFTER_ROLLBACK` đăng ký callback cho T1.
- Service đăng ký callback `TransactionSynchronization.afterCommit` để phát `OrderCommittedSignal` sau commit.
- T1 commit thành công: callback `afterCommit` publish signal và listener thường của signal tăng `publishedAfterCommit`; transaction listener `AFTER_COMMIT` tăng counter. `AFTER_ROLLBACK` không chạy.
- Main gọi `counters.print(...)` khi `service.create` đã trả về; số rows = 1.

**Nhánh rollback (ID 2):**

- T2 INSERT ID 2, publish `OrderCreated(2)`. Listener thường đã nhận event; `immediate=2`.
- Method service đăng ký callback hậu commit rồi ném `IllegalStateException("force rollback")`.
- Spring transaction interceptor rollback T2. `AFTER_COMMIT` không chạy; `afterCommit()` cũng không được gọi.
- `AFTER_ROLLBACK` tăng lên 1, DB chỉ còn ID 1. `publishedAfterCommit` vẫn là 1.

**Nhánh no transaction (ID 3):**

- Main gọi `context.publishEvent(new OrderCreated(3))` ở bên ngoài service transactional.
- Listener thường tăng `immediate=3`.
- Vì `@TransactionalEventListener` có `fallbackExecution=false` mặc định, listener transaction-bound không chạy.
- Main không đăng ký `afterCommit()` cho event này; không có signal hậu commit và DB row mới.

Ví dụ cố ý không in trong từng callback `AFTER_COMMIT` và `afterCommit()`, để không dựa vào thứ tự triển khai giữa hai loại callback khi định nghĩa workflow.

## 6. @Transactional có hiệu lực thật ở đâu?

Một lỗi phổ biến là thấy annotation `@Transactional` nhưng event vẫn bị xử lý ngoài transaction.

~~~java
@Service
class CheckoutService {
    public void checkout(long id) {
        this.createInTransaction(id);
    }

    @Transactional
    public void createInTransaction(long id) {
        repository.insert(id);
        publisher.publishEvent(new OrderCreated(id));
    }
}
~~~

Đây là **phản ví dụ** về *self-invocation*. Trong Spring AOP proxy mode mặc định, `this.createInTransaction(id)` không đi qua transactional proxy, do đó có thể **không mở T1**. Nếu vậy, listener `@TransactionalEventListener` mặc định bỏ qua event, dù code trông có vẻ đúng.

Cách sửa:

- Đặt method transactional trong một Spring-managed bean khác và gọi **qua proxy**.
- Hoặc tổ chức external entry point để caller gọi trực tiếp public method transactional trên Spring bean.
- Hoặc dùng `TransactionTemplate` cho một transaction boundary programmatic tường minh.

Các lỗi khác: object được tạo bằng `new`; method không intercept được; class/method `final` không tương thích class-based proxy; transaction manager sai; config thiếu `@EnableTransactionManagement` trong Spring thuần; propagation `SUPPORTS` khi caller không có T1.

### Debug tại đúng điểm phát sự kiện

~~~java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
boolean sync =
    TransactionSynchronizationManager.isSynchronizationActive();

log.debug("before publish: txActive={}, txSync={}", active, sync);
publisher.publishEvent(new OrderCreated(id));
~~~

Đây là mã tích hợp với logger của ứng dụng. Khi dùng `PlatformTransactionManager` imperative, kiểm tra tại **chính điểm publish** thường hữu ích hơn kiểm tra ở controller. Không suy từ `sync=true` riêng lẻ rằng luôn có transaction business thực sự; xem cả `active` và transaction manager.

## 7. Cần transaction mới khi listener hậu commit ghi DB

Một sắc thái kỹ thuật quan trọng: sau khi commit, **transaction resources có thể vẫn còn gắn trên thread trong lúc callback chạy**, dù database đã commit và **không còn lần commit tiếp theo** cho T1.

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    auditRepository.insertAudit(event.id());
}
~~~

Đoạn này là mã minh họa **không đủ điều kiện khẳng định dữ liệu audit sẽ được commit**. Theo Spring Javadoc, thao tác data access ở callback sau completion có thể tham gia resource transaction cũ, nhưng không có commit mới.

Tách thành bean với transaction độc lập:

~~~java
@Component
public class AuditObserver {
    private final AuditWriter auditWriter;

    public AuditObserver(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderCreated event) {
        auditWriter.write(event.id());
    }
}

@Service
public class AuditWriter {
    private final AuditRepository repository;

    public AuditWriter(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(long id) {
        repository.insertAudit(id);
    }
}
~~~

Đây là **mã tích hợp**, cần `AuditRepository` và imports, và lời gọi sang `AuditWriter` phải qua Spring proxy. `REQUIRES_NEW` mở một transaction T2 riêng. T2 có thể commit hoặc rollback độc lập, nhưng không còn atomic với T1 đã commit.

Nếu audit và đơn hàng **phải luôn được ghi hoặc rollback cùng nhau**, ghi cả hai trong T1; không trì hoãn audit write sang AFTER_COMMIT.

## 8. Exception sau commit không làm rollback T1

Xem callback thủ công:

~~~java
TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            remoteService.notifyOrder(id);
            // Exception ở đây xảy ra sau khi T1 đã COMMIT.
        }
    }
);
~~~

Theo contract của `TransactionSynchronization.afterCommit()`, runtime exception từ callback **có thể lan về caller** của lệnh transactional. Tuy vậy, database **đã commit**, nên caller không được kết luận rằng đơn hàng chưa được tạo.

Trong khi đó, `@TransactionalEventListener(AFTER_COMMIT)` được xử lý theo transaction completion synchronization; Spring phân biệt callback của `afterCompletion` với phương thức `afterCommit` trực tiếp. Exception trong `afterCompletion` thường được **log thay vì lan truyền**. Không dùng một quy tắc chung “mọi exception hậu commit đều lan về HTTP request” hoặc “mọi exception hậu commit đều bị nuốt”.

| Lỗi ở đâu? | Có thể rollback T1? | Lưu ý |
|---|---|---|
| Listener đồng bộ thường ném trong T1 | Có thể, theo rollback rules | Exception cần thoát đúng transaction boundary |
| `BEFORE_COMMIT` listener ném unchecked exception | Có thể | T1 chưa commit |
| `TransactionSynchronization.afterCommit()` ném | **Không** | Caller có thể nhận exception dù DB commit |
| `@TransactionalEventListener(AFTER_COMMIT)` lỗi | **Không** | Callback completion; logging/error policy riêng |
| Worker `@Async` lỗi sau commit | **Không** | Quan sát lỗi qua executor/future/retry |

Vì thế, command tạo đơn cần idempotency key nếu client có thể retry sau timeout/exception. Hậu xử lý cần trạng thái riêng và metrics để biết lỗi, không suy mọi thứ từ HTTP status.

## 9. Phát event sau commit không bảo đảm bền vững

Sơ đồ crash gap:

~~~text
T1 COMMIT order thành công
     |
     +-- JVM crash trước khi listener AFTER_COMMIT hoàn tất
     |
     +-- Email/API/broker chưa được gọi hoặc chưa có ack
     |
     +-- Không có bản ghi durable để replay tự động
~~~

Với cả Mẫu A và Mẫu B, callback sống trong tiến trình. Nếu tác vụ nghiệp vụ bắt buộc phải hoàn tất dù restart, **transactional outbox** phù hợp hơn:

~~~text
BEGIN T1
  INSERT orders(id=328)
  INSERT outbox_events(event_id=E328, type='OrderCreated', status='PENDING')
COMMIT T1
      |
      +-- Outbox relay đọc rows đã commit
      +-- Gửi broker / API
      +-- Retry khi lỗi
      +-- Consumer idempotent dựa trên eventId
~~~

Nếu T1 rollback, business và outbox cùng rollback. Nếu commit rồi JVM crash, outbox vẫn còn để gửi. Nhưng nếu relay gửi thành công rồi crash trước khi đánh dấu SENT, message có thể được gửi lại. **At-least-once delivery cần consumer idempotency**; outbox không tự tạo exactly-once end-to-end.

Một lỗi thiết kế:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void saveOutbox(OrderCreated event) {
    outboxRepository.insert(event);
}
~~~

Nếu mục tiêu là **atomic outbox**, đây là vị trí sai: T1 đã commit trước khi outbox insert, nên outbox không nằm cùng transaction business. Mở T2 bằng `REQUIRES_NEW` giúp ghi được outbox sau commit, nhưng vẫn tồn tại crash gap giữa T1 và T2. Ghi bản outbox đầu tiên **trong T1**.

Nếu chỉ cần reliable publication **giữa các module trong cùng ứng dụng**, có thể xem Spring Modulith Event Publication Registry và incomplete-publication resubmission, theo đúng phiên bản. Không coi nó tự động là Kafka outbox hoặc broker delivery.

## 10. Async listener: có chờ commit nhưng không tự có transaction T1

Một mẫu thường gặp:

~~~java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    emailGateway.send(event.id());
}
~~~

Đây là mã tích hợp cần `@EnableAsync`, bean `eventExecutor` và Spring-managed listener. Spring đăng ký transactional synchronization tại publication; khi T1 commit xong, công việc listener có thể được chuyển tới executor qua `@Async`.

Các điều cần hiểu:

- JDBC transaction T1 được quản lý trong publisher thread, **không được tự copy sang worker thread**.
- `@Async` không làm event bền; process crash vẫn có thể mất task.
- Exception từ worker không tự rollback T1 đã commit.
- Tracing/MDC context propagation không tương đương transaction propagation.
- Nếu cần DB write trong worker, mở transaction T2 riêng phù hợp.
- Lệnh submit task có thể bị executor từ chối; cần quan sát rejection/queue saturation.
- Test listener async phải **await completion có timeout**, không assert ngay sau `publishEvent`.

### Publish từ async worker là chuyện khác

Nếu service đang giữ T1 ở thread A nhưng gọi một `@Async` publisher ở thread B, chính lệnh `publishEvent` có thể chạy **không có transaction T1**. `@TransactionalEventListener` mặc định khi ấy có thể bỏ event. Phải thiết kế **publication trong T1** hoặc mở transaction thích hợp ở worker, không dựa vào truyền ThreadLocal.

## 11. Reactive transaction và event sau commit

Các ví dụ trên là imperative JDBC (`PlatformTransactionManager`), transaction gắn với thread. Spring Framework 6.1+ cũng hỗ trợ `@TransactionalEventListener` với `ReactiveTransactionManager`, nhưng transaction reactive sống trong **Reactor Context**.

Để listener transaction-bound nhận biết transaction reactive, Spring yêu cầu đưa `TransactionContext` vào **event source**. `TransactionalEventPublisher` cung cấp API hỗ trợ:

~~~java
return databaseClient.sql("INSERT INTO orders(id) VALUES (:id)")
    .bind("id", id)
    .fetch()
    .rowsUpdated()
    .then(transactionalEventPublisher.publishEvent(context ->
        new PayloadApplicationEvent<>(
            context,
            new OrderCreated(id)
        )))
    .as(transactionalOperator::transactional);
~~~

Đây là **mã tích hợp reactive**, cần `DatabaseClient`, `TransactionalEventPublisher`, `TransactionalOperator` và event type. Nó minh họa publication trong reactive transaction để `@TransactionalEventListener(AFTER_COMMIT)` có thể được gắn với phase commit. Nó **không** phải ví dụ publish sau commit thật sự.

Trong reactive pipelines:

- Chỉ tạo `Mono` chưa làm SQL/event chạy; phải có subscription.
- Dùng `StepVerifier` hoặc integration test subscriber-aware.
- Không dùng imperative `TransactionSynchronizationManager.isActualTransactionActive()` làm bằng chứng duy nhất về transaction reactive.
- Tránh tự gọi `subscribe()` tách rời transaction pipeline.
- Để phát event thật sự sau commit reactive, cần boundary/callback transaction completion phù hợp; outbox trong cùng reactive DB transaction vẫn tốt hơn nếu mục tiêu là durability.

## 12. Tránh publish loop và đừng dựa vào callback quá muộn

Một phản ví dụ:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public OrderCreated afterCommit(OrderCreated event) {
    return event; // Có thể gây event chain/lặp hoặc registration khó kiểm soát.
}
~~~

Đây là **phản ví dụ**, không sử dụng trong production. `@EventListener` có thể publish object trả về như event mới; nhưng ở phase completion, việc tiếp tục tạo sự kiện mới có thể gặp vấn đề transaction lifecycle hoặc vòng lặp không kết thúc. Hãy định nghĩa **event type khác**, ý nghĩa rõ ràng, và nếu cần publish sau commit thì gọi `publisher.publishEvent(new EventType(...))` theo boundary phù hợp.

Đặc biệt, khi gọi `publishEvent(...)` **ngay trong `TransactionSynchronization.afterCommit()`**, đừng giả định một `@TransactionalEventListener(AFTER_COMMIT)` khác sẽ có một transaction mới để đăng ký callback. T1 đang trong completion; synchronization mới đăng ký quá muộn có thể có hành vi không phù hợp kỳ vọng. Với event được publish sau commit, sử dụng `@EventListener` thường hoặc tạo T2 thật khi có nhu cầu transaction mới.

**Không dùng `@Order` như một workflow engine.** Thứ tự listener khác với thứ tự hoàn thành side effect trong hệ async/broker. Khi B phụ thuộc A hoàn thành, dùng orchestrator, state machine hoặc event “ACompleted” có contract riêng.

## 13. Kiểm thử đúng commit, rollback, callback và side effect

Một bộ test tốt kiểm chứng ít nhất:

| Ca | Thiết lập | Kỳ vọng |
|---|---|---|
| Commit | Service `@Transactional` INSERT + publish | DB commit và callback AFTER_COMMIT chạy |
| Rollback | INSERT + publish rồi ném RuntimeException | DB rollback; callback AFTER_COMMIT không chạy |
| Publish ngoài transaction | Context publish trực tiếp | `@EventListener` thường nhận; transactional listener mặc định không chạy |
| Publish từ `afterCommit()` | Service commit | Event mới chỉ được publish khi commit thành công |
| `fallbackExecution=true` | Publish ngoài T1 | Listener fallback chạy ngay; không có commit |
| Lỗi hậu commit | Callback ném exception | DB vẫn committed, lỗi được quan sát riêng |
| Async | Listener `@Async` | Assert sau khi chờ signal hoàn tất |
| Outbox | Ghi business/outbox trong T1 | Hai rows commit/rollback cùng nhau |

### Bẫy @Transactional test

Trong Spring TestContext, một test method có `@Transactional` thường **rollback ở cuối test**. Test gọi service rồi assert ngay `AFTER_COMMIT` được gọi là sai nếu transaction chưa commit:

~~~java
@Test
@Transactional
void shouldInvokeAfterCommit() {
    service.create(328L);

    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Đến đây mới assert callback đồng bộ AFTER_COMMIT.
}
~~~

Đây là **mã test minh họa**, cần `spring-test`, JUnit Jupiter, test transaction manager, imports và service được Spring quản lý. Một cách dễ hơn: không đánh dấu chính test method `@Transactional`, để transactional service commit trước khi assertion.

### Recorder chỉ xác minh publication

`@RecordApplicationEvents`/`ApplicationEvents.stream(EventType.class)` hữu ích để xem event được **publish** trong test. Với **Mẫu A**, recorder có thể thấy `OrderCreated` trước commit; điều đó không chứng minh listener AFTER_COMMIT chạy. Kiểm chứng callback qua fake collaborator/counter hoặc side effect DB sau commit thật.

Trong **Mẫu B**, test có thể assert event hậu commit xuất hiện sau khi service trả về và commit, và không xuất hiện sau rollback. Nếu callback async, đợi completion.

### Không phụ thuộc thời gian chính xác

Thời gian, thread scheduling và database connection có thể khác trên CI; đừng assert “sau đúng 10ms”. Sử dụng latch/await condition với timeout và assertions về count, payload, commit outcome và idempotency key.

## 14. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Coi mọi `@EventListener` là listener hậu commit | Side effect xảy ra trước rollback | Dùng `@TransactionalEventListener(AFTER_COMMIT)` |
| Nghĩ `@TransactionalEventListener` làm publishEvent chạy sau commit | Listener khác vẫn thấy event trước commit | Phân biệt delayed handling và delayed publication |
| Gọi publish sau khi transactional service trả về | Không còn T1 để đăng ký callback | Publish trong T1 hoặc đăng ký afterCommit |
| Bật `fallbackExecution=true` tùy tiện | Listener chạy ngay ngoài T1 | Dùng nếu nghiệp vụ chấp nhận fallback |
| Quên proxy/self-invocation | `@Transactional` không có hiệu lực | Gọi qua Spring bean proxy |
| `@Async` publisher trước commit | Không truyền T1 sang worker | Publish trong T1 hoặc tạo transaction mới rõ ràng |
| `REQUIRED` DB write ở hậu commit | Có thể tham gia resource cũ không còn commit | `REQUIRES_NEW` qua bean proxy riêng |
| Exception hậu commit bị hiểu là rollback | Retry command tạo bản ghi trùng | Phân biệt transaction outcome |
| Kỳ vọng `@Async` là durable queue | JVM crash làm mất task | Transactional outbox/queue |
| Ghi outbox lần đầu trong AFTER_COMMIT | Không atomic với business row | Ghi outbox cùng T1 |
| Chỉ assert event recorder | Chưa chứng minh side effect hoàn tất | Assert DB/adapter sau commit thật |
| Dùng `@Order` làm orchestration | Async/broker hoàn thành không theo thứ tự mong muốn | Workflow/state machine |
| Publish event mới trong completion rồi đăng ký phase T1 | Synchronization quá muộn | Listener thường hoặc T2 thực sự |
| Không kiểm soát duplicate | Retry tạo side effect trùng | eventId và idempotent consumer |
| Không theo dõi lỗi callback | DB đã commit nhưng hậu kỳ thất bại âm thầm | Metrics, logs, retry và alert |

## 15. Checklist triển khai

1. **Ý nghĩa event là gì?** “Đang thay đổi” hay “đã commit thành công”?
2. Event cần xuất hiện sau commit với **mọi listener** hay chỉ một số listeners?
3. Có transaction active ở điểm đăng ký callback không?
4. Lời gọi tới `@Transactional` có qua proxy không?
5. Nếu transaction rollback, có callback nào vẫn gây side effect không?
6. Nếu không có transaction, policy là skip, reject hay fallback?
7. Nếu callback hậu commit thất bại, HTTP/service có trả lỗi gây retry command không?
8. Nếu listener ghi thêm DB, transaction mới có `REQUIRES_NEW` thực sự không?
9. Nếu có async, có chờ/quan sát worker, không nhầm ThreadLocal transaction không?
10. Nếu pipeline reactive, event source có TransactionContext đúng không?
11. Nếu việc không được mất sau crash, có outbox/queue và idempotency không?
12. Test đã phủ commit, rollback, publish ngoài T1, exception và async chưa?
13. Có metrics riêng cho callback completion, errors, retries, backlog không?
14. Event chứa ID, version và dữ liệu tối thiểu, không lộ PII/secret không cần thiết?

## 16. Tổng kết

**Phát sự kiện sau commit** trong Spring có hai mẫu chủ đạo. **Mẫu A** phát event khi T1 còn mở, nhưng dùng `@TransactionalEventListener(AFTER_COMMIT)` để xử lý **sau khi transaction commit**. **Mẫu B** đăng ký `TransactionSynchronization.afterCommit()`, rồi **mới gọi `publishEvent`**, để một event mang ngữ nghĩa hậu commit không được bất kỳ `@EventListener` thường nào nhìn thấy trước đó.

Hai mẫu đều tránh side effect do transaction rollback theo đúng boundary, nhưng **không tự giải quyết độ bền sau crash hoặc duplicate khi retry**. Nếu tác vụ buộc phải được thực hiện, dùng transactional outbox cùng relay/idempotency. Nếu callback hậu commit ghi thêm DB, lưu ý resource cũ có thể còn gắn thread và không còn commit tiếp theo: tạo transaction mới phù hợp như `REQUIRES_NEW` qua proxy.

### Nguồn tham khảo chính thức

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): `@TransactionalEventListener`, phases, fallback và reactive.
- [Spring Framework 6.2.8 Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): contract và cảnh báo DB resources hậu completion.
- [Spring Framework 6.2.8 Javadoc — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): `afterCommit()`, `afterCompletion()` và exceptions.
- [Spring Framework 6.2.8 Javadoc — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): đăng ký synchronization trong transaction imperative.
- [Spring Framework 6.2 — Declarative Transactions](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): proxy, `@Transactional` và self-invocation.
- [Spring Framework 6.2 — Transaction Propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`.
- [Spring Framework 6.2.8 — TransactionalEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html): reactive `TransactionContext` event source.
