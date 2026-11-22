# Transaction phase AFTER_COMPLETION

`TransactionPhase.AFTER_COMPLETION` là phase của `@TransactionalEventListener` dùng khi listener cần chạy sau khi transaction kết thúc, bất kể transaction commit hay rollback. Đây là phase tổng hợp cả hai kết quả. Nó phù hợp với công việc cần thực hiện khi transaction đã hoàn tất, chẳng hạn giải phóng tài nguyên phụ, ghi nhận trạng thái xử lý hoặc dọn dữ liệu tạm.

`AFTER_COMPLETION` khác với `AFTER_COMMIT` và `AFTER_ROLLBACK` ở phạm vi điều kiện. `AFTER_COMMIT` chỉ chạy khi commit thành công; `AFTER_ROLLBACK` chỉ chạy khi rollback; còn `AFTER_COMPLETION` chạy sau cả hai trường hợp. Listener phase này không nhận trực tiếp mã trạng thái commit/rollback qua tham số method. Nếu cần xử lý riêng từng kết quả, hãy dùng hai phase chuyên biệt hoặc đăng ký transaction synchronization ở mức thấp hơn.

Một điểm cần đặc biệt chú ý: tại thời điểm callback chạy, transaction gốc đã hoàn tất. Resource như JDBC connection có thể vẫn còn được bind và truy cập trong quá trình cleanup, nhưng thay đổi dữ liệu phát sinh ở phase này sẽ không được commit vào transaction gốc. Nếu listener cần ghi dữ liệu mới, hãy mở transaction riêng, thường bằng `Propagation.REQUIRES_NEW`.

Sau bài học, bạn có thể:

- Giải thích chính xác thời điểm `AFTER_COMPLETION` được gọi.
- Phân biệt `AFTER_COMPLETION` với `AFTER_COMMIT` và `AFTER_ROLLBACK`.
- Đăng ký listener bằng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)`.
- Hiểu hành vi khi event được phát ngoài transaction và vai trò của `fallbackExecution`.
- Tránh ghi dữ liệu vào transaction đã hoàn tất và biết khi nào cần `REQUIRES_NEW`.
- Kiểm thử listener với cả transaction commit và rollback.
- Hiểu các lưu ý khi dùng transaction event với reactive transaction.

## 1. AFTER_COMPLETION là gì?

Spring cung cấp `@TransactionalEventListener` để gắn việc xử lý event với một phase của transaction. Thuộc tính `phase` nhận một giá trị `TransactionPhase`.

Các phase hợp lệ:

| Phase | Khi listener được gọi | Trường hợp sử dụng |
|---|---|---|
| `BEFORE_COMMIT` | Trước khi transaction commit | Kiểm tra hoặc bổ sung công việc cần hoàn tất trước commit. |
| `AFTER_COMMIT` | Sau khi transaction commit thành công | Gửi thông báo hoặc thực hiện side effect chỉ hợp lệ khi dữ liệu đã commit. |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Ghi nhận hoặc dọn dẹp riêng cho trường hợp rollback. |
| **`AFTER_COMPLETION`** | Sau khi transaction hoàn tất, dù commit hay rollback | Cleanup hoặc xử lý chung cho mọi kết quả hoàn tất. |

`AFTER_COMPLETION` bao quát cả commit và rollback. Vì vậy, listener được đăng ký với phase này sẽ được gọi sau khi transaction kết thúc ở một trong hai trạng thái.

Ví dụ khai báo:

~~~java
@Component
public class OrderCompletionListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderCreatedEvent event) {
        System.out.println("Transaction completed for " + event.orderId());
    }
}
~~~

Nếu event được phát trong một transaction đang hoạt động, Spring đăng ký việc gọi listener với transaction synchronization. Method không được thực thi ngay tại dòng `publishEvent`; nó được gọi khi transaction đi đến phase đã chọn.

## 2. Vị trí của AFTER_COMPLETION trong vòng đời transaction

Với transaction imperative được quản lý bởi `PlatformTransactionManager`, trình tự tổng quát là:

~~~mermaid
flowchart TD
    A["Bắt đầu transaction"] --> B["Publisher phát event"]
    B --> C["Spring đăng ký transactional listener"]
    C --> D{"Transaction kết thúc thế nào?"}
    D -->|Commit| E["Commit resource"]
    D -->|Rollback| F["Rollback resource"]
    E --> G["AFTER_COMPLETION callback"]
    F --> G
    G --> H["Cleanup transaction resources"]
~~~

Ở cả hai nhánh, callback `AFTER_COMPLETION` được gọi sau khi kết quả transaction đã được quyết định.

Ví dụ với commit:

1. Service bắt đầu transaction.
2. Service thay đổi dữ liệu.
3. Service phát event.
4. Method transactional kết thúc bình thường.
5. Transaction manager commit.
6. Listener `AFTER_COMPLETION` được gọi.
7. Spring dọn transaction resources.

Ví dụ với rollback:

1. Service bắt đầu transaction.
2. Service thay đổi dữ liệu.
3. Service phát event.
4. Method transactional ném exception phù hợp rollback rules.
5. Transaction manager rollback.
6. Listener `AFTER_COMPLETION` vẫn được gọi.
7. Spring dọn transaction resources.

Điểm quan trọng là event đã được đăng ký trong transaction vẫn có thể được xử lý sau rollback. `AFTER_COMPLETION` không có nghĩa transaction thành công; nó chỉ có nghĩa transaction đã kết thúc.

## 3. So sánh AFTER_COMPLETION với AFTER_COMMIT và AFTER_ROLLBACK

Ba phase đều chạy sau khi transaction đã hoàn tất, nhưng điều kiện kích hoạt khác nhau.

~~~java
@Component
public class OrderTransactionListeners {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterCommit(OrderCreatedEvent event) {
        // Chỉ chạy nếu transaction commit thành công.
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK
    )
    public void afterRollback(OrderCreatedEvent event) {
        // Chỉ chạy nếu transaction rollback.
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderCreatedEvent event) {
        // Chạy sau cả commit và rollback.
    }
}
~~~

Bảng lựa chọn:

| Nhu cầu | Phase nên dùng |
|---|---|
| Chỉ xử lý khi dữ liệu đã commit | `AFTER_COMMIT` |
| Chỉ xử lý khi transaction thất bại và rollback | `AFTER_ROLLBACK` |
| Luôn chạy cleanup sau khi transaction kết thúc | `AFTER_COMPLETION` |
| Kiểm tra hoặc bổ sung dữ liệu trước commit | `BEFORE_COMMIT` |

`AFTER_COMMIT` và `AFTER_ROLLBACK` là các trường hợp chuyên biệt của `AFTER_COMPLETION` và chạy trong cùng chuỗi transaction completion. Nếu đăng ký nhiều listener cho cùng event, hãy khai báo rõ trách nhiệm để tránh thực hiện trùng một side effect.

### AFTER_COMPLETION không cung cấp transaction status cho method

Method listener thường nhận event payload:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMPLETION
)
public void afterCompletion(OrderCreatedEvent event) {
    // Chỉ nhận event; không có tham số status commit/rollback.
}
~~~

Annotation không tự truyền một tham số kiểu `int status` hoặc `TransactionStatus` vào method. Nếu listener cần biết chính xác commit hay rollback để rẽ nhánh:

- Dùng `AFTER_COMMIT` cho nhánh commit.
- Dùng `AFTER_ROLLBACK` cho nhánh rollback.
- Hoặc dùng `TransactionSynchronization.afterCompletion(int status)` khi cần callback mức thấp có status `STATUS_COMMITTED`, `STATUS_ROLLED_BACK` hoặc `STATUS_UNKNOWN`.

Không nên suy đoán kết quả transaction từ việc method listener đã được gọi: với `AFTER_COMPLETION`, cả hai kết quả đều hợp lệ.

## 4. Đăng ký event và listener

Publisher phát event bên trong transaction:

~~~java
@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Transactional
    public void create(String orderId) {
        // Lưu đơn hàng trong transaction.
        publisher.publishEvent(new OrderCreatedEvent(orderId));
    }
}
~~~

Event payload có thể là record:

~~~java
public record OrderCreatedEvent(String orderId) {}
~~~

Listener đăng ký với phase mong muốn:

~~~java
@Component
public class OrderCompletionListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderCreatedEvent event) {
        System.out.println("Completed: " + event.orderId());
    }
}
~~~

Spring đăng ký method listener như một transaction-bound listener. Khi event được phát trong transaction, việc thực thi method được trì hoãn đến completion phase.

`@TransactionalEventListener` có phase mặc định là `AFTER_COMMIT`. Nếu muốn chạy sau cả commit và rollback, phải chỉ định `AFTER_COMPLETION` rõ ràng để người đọc code hiểu ý định.

## 5. Khi không có transaction đang hoạt động

Mặc định, nếu event được phát khi không có transaction đang hoạt động, `@TransactionalEventListener` không được gọi. Spring không thể thực hiện ngữ nghĩa transaction phase nếu không có transaction để gắn listener.

Ví dụ:

~~~java
publisher.publishEvent(new OrderCreatedEvent("ORD-8001"));
~~~

Nếu dòng này chạy ngoài transaction, listener `AFTER_COMPLETION` mặc định sẽ không được thực thi.

Có thể bật `fallbackExecution = true`:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMPLETION,
    fallbackExecution = true
)
public void afterCompletion(OrderCreatedEvent event) {
    // Được gọi cả khi event không nằm trong transaction.
}
~~~

Khi không có transaction, listener được thực thi theo fallback thay vì chờ một completion phase thực sự. Vì vậy, bật fallback làm thay đổi ý nghĩa của listener: method có thể chạy ngay cả khi không có transaction nào hoàn tất.

Chỉ bật fallback khi nghiệp vụ chấp nhận xử lý event ngoài transaction. Nếu yêu cầu là “chỉ chạy sau khi transaction kết thúc”, hãy giữ mặc định `fallbackExecution = false`.

## 6. Lưu ý quan trọng: resource vẫn có thể truy cập sau completion

Javadoc của Spring cảnh báo rằng ở các phase `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`, transaction đã commit hoặc rollback, nhưng transactional resource có thể vẫn còn hoạt động và truy cập được trong lúc Spring cleanup.

Điều này tạo ra một tình huống dễ hiểu nhầm:

- Listener gọi repository hoặc `JdbcTemplate`.
- Lệnh truy cập dữ liệu có thể vẫn dùng resource đang được bind với transaction cũ.
- Vì transaction gốc đã hoàn tất, thay đổi mới sẽ không được commit vào resource đó.

Ví dụ không nên dựa vào việc ghi sau completion để lưu một bản ghi audit:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMPLETION
)
public void afterCompletion(OrderCreatedEvent event) {
    // Không nên mặc định rằng lệnh save này sẽ được commit.
    auditRepository.save(new AuditEntry(event.orderId()));
}
~~~

Nếu cần ghi dữ liệu mới sau completion, hãy gọi một service mở transaction riêng:

~~~java
@Service
public class AuditWriter {

    private final AuditRepository auditRepository;

    public AuditWriter(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordCompletion(String orderId) {
        auditRepository.save(new AuditEntry(orderId));
    }
}
~~~

Listener gọi service:

~~~java
@Component
public class OrderCompletionListener {

    private final AuditWriter auditWriter;

    public OrderCompletionListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderCreatedEvent event) {
        auditWriter.recordCompletion(event.orderId());
    }
}
~~~

`REQUIRES_NEW` yêu cầu transaction độc lập cho thao tác ghi. Method phải được gọi qua Spring proxy của bean khác để transaction propagation được áp dụng đúng; self-invocation trong cùng bean không đi qua proxy theo cách thông thường.

Nếu listener chỉ cần cleanup tài nguyên hoặc ghi metric bên ngoài transaction, không nhất thiết phải mở transaction mới. Chọn cơ chế theo loại side effect.

## 7. Exception và độ tin cậy của callback

Khi `AFTER_COMPLETION` được gọi, transaction gốc đã hoàn tất. Exception trong listener không thể khiến transaction đó quay lại trạng thái chưa commit hoặc tự rollback dữ liệu đã commit.

Theo hợp đồng `TransactionSynchronization.afterCompletion(int)` của Spring, `RuntimeException` từ callback completion được ghi log và không truyền ngược như một exception trong thân phương thức transactional thông thường. Vì vậy, publisher không nên coi việc `publishEvent` trả về là bằng chứng side effect sau completion đã thành công.

Nếu tác vụ sau completion quan trọng:

- Ghi log và metric riêng cho listener.
- Thiết kế retry có kiểm soát.
- Dùng idempotency key nếu có thể xử lý lặp.
- Dùng outbox hoặc message broker khi cần delivery bền vững qua sự cố tiến trình.
- Không nuốt exception mà không để lại dấu vết vận hành.

`AFTER_COMPLETION` là callback gắn với vòng đời transaction trong process hiện tại. Nó không phải hàng đợi bền vững và không tự lưu event để phát lại sau khi ứng dụng bị dừng đột ngột.

## 8. Reactive transaction và AFTER_COMPLETION

Từ Spring Framework 6.1, `@TransactionalEventListener` hỗ trợ cả transaction imperative được quản lý bởi `PlatformTransactionManager` và reactive transaction được quản lý bởi `ReactiveTransactionManager`.

Hai mô hình lưu transaction context khác nhau:

- Imperative transaction dùng context gắn với thread.
- Reactive transaction dùng Reactor Context thay cho ThreadLocal.

Khi phát event trong reactive transaction, transaction context cần được đưa vào event instance làm event source. Spring cung cấp `TransactionalEventPublisher` để hỗ trợ việc này.

Ví dụ khái quát:

~~~java
@Service
public class ReactiveOrderService {

    private final OrderRepository repository;
    private final TransactionalEventPublisher eventPublisher;

    public ReactiveOrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.eventPublisher = new TransactionalEventPublisher(publisher);
    }

    @Transactional
    public Mono<Void> create(Order order) {
        return repository.save(order)
            .then(eventPublisher.publishEvent(
                new OrderCreatedEvent(order.id())
            ));
    }
}
~~~

Listener vẫn có thể chọn phase:

~~~java
@Component
public class ReactiveCompletionListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderCreatedEvent event) {
        // Được gắn với completion của reactive transaction.
    }
}
~~~

Ví dụ yêu cầu repository trả về reactive type và ứng dụng cấu hình `ReactiveTransactionManager` phù hợp. Không gọi trực tiếp `ApplicationEventPublisher.publishEvent(payload)` rồi trông chờ Spring tìm transaction reactive từ ThreadLocal; hãy dùng `TransactionalEventPublisher` để chuyển context đúng cách.

## 9. Ví dụ hoàn chỉnh: listener chạy sau commit và rollback

Ví dụ dùng Java 17, Spring Framework 6.2.0, Spring JDBC và H2. Service tạo một đơn hàng rồi phát event trong transaction. Một lần gọi commit bình thường; lần thứ hai phát event rồi ném exception để transaction rollback. Listener `AFTER_COMPLETION` sẽ được gọi sau cả hai lần.

Cấu trúc thư mục:

~~~text
after-completion-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AfterCompletionDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>after-completion-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.0</version>
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
                <configuration>
                    <mainClass>demo.AfterCompletionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/AfterCompletionDemo.java

~~~java
package demo;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class AfterCompletionDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                CREATE TABLE orders (
                    order_id VARCHAR(40) PRIMARY KEY
                )
                """);

            OrderService service = context.getBean(OrderService.class);

            service.createAndCommit("ORD-8001");

            try {
                service.createAndRollback("ORD-8002");
            } catch (IllegalStateException expected) {
                System.out.println(
                    "Publisher caught: " + expected.getMessage()
                );
            }

            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders",
                Integer.class
            );

            System.out.println("Persisted orders: " + count);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    static class AppConfig {

        @Bean
        JdbcDataSource dataSource() {
            JdbcDataSource dataSource = new JdbcDataSource();
            dataSource.setURL("jdbc:h2:mem:after-completion;DB_CLOSE_DELAY=-1");
            dataSource.setUser("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        JdbcTemplate jdbcTemplate(JdbcDataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                JdbcDataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        OrderCompletionListener orderCompletionListener() {
            return new OrderCompletionListener();
        }
    }

    record OrderCreatedEvent(String orderId) {}

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void createAndCommit(String orderId) {
            jdbc.update(
                "INSERT INTO orders(order_id) VALUES (?)",
                orderId
            );
            publisher.publishEvent(new OrderCreatedEvent(orderId));
        }

        @Transactional
        public void createAndRollback(String orderId) {
            jdbc.update(
                "INSERT INTO orders(order_id) VALUES (?)",
                orderId
            );
            publisher.publishEvent(new OrderCreatedEvent(orderId));
            throw new IllegalStateException("simulated rollback");
        }
    }

    static class OrderCompletionListener {

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMPLETION
        )
        public void afterCompletion(OrderCreatedEvent event) {
            System.out.println(
                "AFTER_COMPLETION: " + event.orderId()
            );
        }
    }
}
~~~

Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Kết quả stdout:

~~~text
AFTER_COMPLETION: ORD-8001
AFTER_COMPLETION: ORD-8002
Publisher caught: simulated rollback
Persisted orders: 1
~~~

Giải thích:

- `ORD-8001` được insert và transaction commit. Listener nhận event sau completion.
- `ORD-8002` được insert và event được phát khi transaction còn hoạt động. Sau đó exception làm transaction rollback. Listener vẫn nhận event sau completion.
- Chỉ `ORD-8001` còn trong bảng vì transaction thứ hai đã rollback.
- Dòng `Publisher caught` xuất hiện sau callback rollback vì transaction interceptor hoàn tất rollback và synchronization trước khi trả quyền điều khiển về caller.

Ví dụ chỉ ghi nhận callback và truy vấn số bản ghi sau khi các transaction kết thúc. Listener không cố ghi dữ liệu mới vào resource của transaction đã hoàn tất. Nếu muốn ghi audit hoặc cập nhật bảng khác trong callback, hãy gọi một service dùng transaction riêng như `REQUIRES_NEW`.

## 10. Kiểm thử các tình huống quan trọng

Một bộ kiểm thử cho `AFTER_COMPLETION` nên xác nhận cả commit lẫn rollback:

| Tình huống | Kết quả mong đợi |
|---|---|
| Event phát trong transaction commit | Listener được gọi một lần sau commit. |
| Event phát trong transaction rollback | Listener được gọi một lần sau rollback. |
| Event phát ngoài transaction, fallback mặc định | Listener không được gọi. |
| Event phát ngoài transaction, fallback bật | Listener được gọi theo fallback, không chờ completion. |
| Listener ghi dữ liệu mới bằng transaction gốc | Không được giả định thay đổi sẽ commit. |
| Listener gọi service `REQUIRES_NEW` | Thao tác có transaction độc lập. |
| Listener phát sinh exception sau completion | Transaction gốc không thể bị rollback lại; cần log và chính sách retry. |

Khi test bằng Spring context, nên dùng một bean service được lấy từ context để lời gọi đi qua transaction proxy. Gọi trực tiếp object được tạo bằng `new` sẽ bỏ qua transaction interceptor.

Nếu test callback bất đồng bộ hoặc listener được cấu hình async, hãy dùng future/latch có timeout. Không dùng `Thread.sleep` để phỏng đoán thời điểm callback hoàn tất.

## 11. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ AFTER_COMPLETION chỉ chạy khi commit | Bỏ lỡ event sau rollback. | Phase này chạy sau cả commit và rollback. |
| Dùng AFTER_COMPLETION khi chỉ muốn gửi thông báo sau commit | Có thể gửi thông báo cả khi dữ liệu đã rollback. | Dùng `AFTER_COMMIT`. |
| Dùng AFTER_COMPLETION khi chỉ muốn xử lý rollback | Listener cũng chạy khi commit. | Dùng `AFTER_ROLLBACK`. |
| Cho rằng method nhận transaction status | Không biết trực tiếp kết quả commit/rollback. | Dùng phase chuyên biệt hoặc `TransactionSynchronization`. |
| Phát event ngoài transaction và mong listener chờ completion | Không có transaction để đăng ký synchronization. | Giữ fallback mặc định hoặc bật fallback khi thực sự chấp nhận. |
| Ghi database trong AFTER_COMPLETION bằng transaction cũ | Thay đổi mới không được commit vào resource gốc. | Gọi service dùng `REQUIRES_NEW`. |
| Cho rằng exception callback rollback được transaction đã hoàn tất | Dữ liệu đã commit/rollback không thể đảo ngược bởi callback. | Log, retry hoặc dùng outbox cho side effect quan trọng. |
| Tự gọi method REQUIRES_NEW trong cùng bean | Lời gọi có thể không đi qua proxy transaction. | Đưa thao tác sang bean service khác hoặc dùng cơ chế transaction tường minh. |
| Dùng application event như hàng đợi bền vững | Event có thể mất nếu tiến trình dừng. | Dùng outbox hoặc message broker khi cần delivery bền vững. |

## 12. Checklist sử dụng AFTER_COMPLETION

Trước khi triển khai, hãy kiểm tra:

1. Listener có thật sự cần chạy sau cả commit lẫn rollback không?
2. Nếu chỉ quan tâm commit hoặc rollback, phase chuyên biệt có phù hợp hơn không?
3. Event có được phát trong transaction đang hoạt động không?
4. `fallbackExecution` có nên giữ mặc định là false không?
5. Listener có đang giả định rằng method nhận được transaction status không?
6. Listener có ghi dữ liệu sau completion không, và nếu có đã dùng transaction mới chưa?
7. Side effect có cần idempotency, retry hoặc outbox không?
8. Exception sau completion có được ghi nhận và giám sát không?
9. Reactive transaction có dùng `TransactionalEventPublisher` để truyền Reactor context không?
10. Test đã xác nhận callback chạy ở cả commit và rollback chưa?

`TransactionPhase.AFTER_COMPLETION` chạy sau khi transaction kết thúc, dù commit hay rollback. Đây là lựa chọn phù hợp cho cleanup và công việc chung cần thực hiện ở mọi kết quả hoàn tất. Nếu chỉ xử lý một kết quả cụ thể, dùng `AFTER_COMMIT` hoặc `AFTER_ROLLBACK`. Hãy nhớ transaction gốc đã hoàn tất khi callback chạy; mọi thay đổi dữ liệu mới cần được commit phải dùng transaction độc lập, thường là `REQUIRES_NEW`.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): cách đăng ký listener theo transaction phase và hành vi khi không có transaction.
- [TransactionPhase — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionPhase.html): định nghĩa chính xác của `AFTER_COMPLETION`, `AFTER_COMMIT` và `AFTER_ROLLBACK`.
- [TransactionalEventListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): phase, fallback execution và lưu ý về resource sau completion.
- [TransactionSynchronization — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): callback `afterCompletion(int status)` và quy tắc xử lý exception.
