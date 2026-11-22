# Publish event tại application service trong thiết kế domain event (Spring Framework)

## 1. Mục đích

Application service là điểm điều phối một use case trong ứng dụng: nhận command, kiểm tra ranh giới ứng dụng, tải hoặc tạo aggregate, yêu cầu domain model thực hiện hành vi, lưu trạng thái và phản ánh những **sự kiện nghiệp vụ đã xảy ra**. Một cách để phản ánh kết quả mà không phụ thuộc trực tiếp vào tất cả tác vụ phía sau là phát một **domain event**.

Ví dụ, sau khi đơn hàng được chuyển sang trạng thái SUBMITTED, application service có thể phát sự kiện **OrderSubmitted**. Các listener khác có thể ghi audit, cập nhật bộ nhớ đệm, tạo thông báo hoặc khởi động quy trình tích hợp. Nhờ vậy, service không phải gọi trực tiếp từng thành phần phụ trợ, giúp giảm coupling.

Nhưng có ba điều tuyệt đối không được đánh đồng:

1. **Sự kiện nghiệp vụ đã được tạo:** domain model hoặc application service đã xác nhận một fact.
2. **Sự kiện đã được publish:** application service gọi ApplicationEventPublisher.publishEvent.
3. **Database đã commit và subscriber đã xử lý thành công:** là những mốc khác nhau; publishEvent không tự bảo đảm hai điều này.

Bài học tập trung vào vị trí publish, giao dịch, kiểu listener, cách xử lý rollback, độ bền, idempotency và một ví dụ Java 17+ hoàn chỉnh.

## 2. Ranh giới trách nhiệm của application service

Một luồng điển hình:

~~~text
Controller / Message handler
      |
      v
OrderApplicationService.submit(command)
      |
      +-- validate input, kiểm tra quyền
      +-- load/create Order aggregate
      +-- order.submit()          [domain invariant]
      +-- repository.save(order)  [thay đổi trong transaction]
      +-- publish(OrderSubmitted)
      |
      +-- transaction commit hoặc rollback
                |
                +-- AFTER_COMMIT listeners
~~~

**Domain model** quyết định trạng thái có thể chuyển từ DRAFT sang SUBMITTED hay không; **application service** điều phối repository, transaction và việc phát thông báo cho các thành phần khác. Những tác vụ như gửi email, cập nhật chỉ mục hoặc gọi API đối tác thường không thuộc invariant lõi của aggregate.

Đây là một cách tổ chức, không phải quy tắc bắt buộc cho mọi codebase. Trong domain model giàu logic, aggregate có thể ghi nhận một danh sách domain events nội bộ; application service thu thập và phát sau khi thay đổi trạng thái hợp lệ. Việc **ghi nhận** event trong aggregate khác với việc **publish** bằng framework adapter.

Một domain event nên mô tả sự việc ở thì quá khứ: OrderSubmitted, PaymentCaptured, AccountRegistered. Tên SendEmail hoặc UpdateCache thường là command yêu cầu hành động chứ không phải fact của miền nghiệp vụ.

### Event payload nên mang gì?

Java 17 cho phép dùng record:

~~~java
// Đoạn minh họa cần import java.time.Instant.
public record OrderSubmitted(
        String eventId,
        long orderId,
        Instant occurredAt,
        String customerId
) {}
~~~

| Field | Tác dụng |
| --- | --- |
| eventId | Định danh event để tracing, idempotency và phát hiện xử lý trùng |
| orderId | Khóa aggregate, giúp subscriber truy xuất dữ liệu khi cần |
| occurredAt | Thời điểm business fact phát sinh, không nhất thiết bằng thời điểm subscriber xử lý |
| customerId | Dữ liệu nghiệp vụ subscriber thật sự cần, không phải toàn bộ JPA entity |

Nên ưu tiên ID hoặc immutable snapshot và không phát nguyên đối tượng JPA managed/lazy. Đừng đưa password, token hay thông tin nhạy cảm không cần thiết vào event. Record chỉ bất biến nông: nếu chứa danh sách mutable, bên nhận vẫn có thể thay đổi dữ liệu phía trong.

Với event cần chuyển qua service khác, còn phải quan tâm schemaVersion, eventType, tenant/correlation ID, backward compatibility và kiểm soát dữ liệu nhạy cảm.

## 3. Cơ chế Spring Application Events

Spring cung cấp giao diện **ApplicationEventPublisher**. Spring bean có thể inject giao diện này vào constructor và gọi:

~~~java
// Minh họa trong một Spring-managed application service.
publisher.publishEvent(new OrderSubmitted(
        UUID.randomUUID().toString(),
        order.getId(),
        Instant.now(),
        order.getCustomerId()
));
~~~

Spring nhận cả POJO/record làm event, không bắt buộc subclass của ApplicationEvent. Phương thức publishEvent trả về **void**, không trả Future, acknowledgment bền vững hay biên nhận broker.

Hệ thống ApplicationEventMulticaster chọn các listener quan tâm đến kiểu event. Với SimpleApplicationEventMulticaster mặc định, listener thông thường được gọi **đồng bộ trên thread đang publish**. Nếu listener không bắt một RuntimeException, nó có thể lan lên publisher; khi publisher đang ở trong transaction, exception còn có thể làm use case rollback.

Hai cách lắng nghe phổ biến là:

~~~java
// Đoạn minh họa trong Spring bean: gọi ngay khi publish mặc định.
@EventListener
public void onOrderSubmitted(OrderSubmitted event) {
    log.info("Order submitted: {}", event.orderId());
}
~~~

~~~java
// Đoạn minh họa trong Spring bean: đợi COMMIT của transaction.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void notifyAfterCommit(OrderSubmitted event) {
    notificationGateway.sendOrderSubmitted(event.orderId());
}
~~~

**EventListener thông thường** chạy ngay trong quá trình publish với cấu hình mặc định. **TransactionalEventListener** đăng ký callback vào transaction và chờ pha đã chọn. AFTER_COMMIT là phase mặc định; các phase khác gồm BEFORE_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION.

Một listener thường phù hợp với tính toán nội bộ nhanh, cần thực hiện ngay trong flow. Listener AFTER_COMMIT phù hợp khi side effect không được khởi động nếu transaction rollback. Nhưng AFTER_COMMIT vẫn chỉ là callback trong tiến trình, chưa phải cơ chế giao hàng bền vững.

## 4. Đặt publishEvent đúng chỗ trong use case

Điểm chính là: **publish khi transaction nghiệp vụ đang hoạt động**, sau khi hành vi domain đã hợp lệ và thay đổi đã được yêu cầu lưu. Chính callback transactional listener sẽ đợi commit.

Một service khai báo @Transactional có thể được viết như sau:

~~~java
// ĐOẠN MINH HỌA: OrderRepository, Order, command chưa định nghĩa ở đây.
@Service
public class OrderApplicationService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public OrderApplicationService(
            OrderRepository repository,
            ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void submit(SubmitOrderCommand command) {
        Order order = repository.findById(command.orderId())
                .orElseThrow();
        order.submit();                     // invariant ở domain
        repository.save(order);             // yêu cầu lưu
        publisher.publishEvent(new OrderSubmitted(
                UUID.randomUUID().toString(),
                order.getId(),
                Instant.now(),
                order.getCustomerId()
        ));
    }
}
~~~

Đây là đoạn code minh họa cần các import và class nghiệp vụ tương ứng, không phải file biên dịch độc lập.

Lời gọi phải đi qua **Spring transaction proxy** thì @Transactional mới được áp dụng ở proxy mode. Khi method submit trả về, transaction interceptor vẫn phải thực hiện commit. Vì vậy **repository.save không có nghĩa commit đã xong**; event được publish trong phần thân method vẫn có thể được phát **trước commit thật**.

### Một sai lầm phổ biến

~~~java
// Minh họa cách sai nếu muốn TransactionalEventListener thấy transaction:
orderService.submit(command); // method này tự commit trước khi trả về
publisher.publishEvent(new OrderSubmitted(...)); // ngoài transaction
~~~

Nếu không có outer transaction, lúc gọi publishEvent không còn transaction. TransactionalEventListener mặc định **không được gọi** vì không có context để đăng ký synchronization.

Điều đúng không phải “publish sau khi @Transactional method trả về”, mà là “**publish trong transaction**, để listener AFTER_COMMIT được kích hoạt **sau commit**”.

### Vì sao không publish ở mọi layer?

- **Controller:** thường chỉ điều phối request/response; publish sau khi service đã commit có thể làm mất transaction context và đặt quyết định domain sai tầng.
- **Repository:** chịu trách nhiệm persistence; tự động phát event mỗi lần save dễ tạo event trùng hoặc nhầm save với một business transition.
- **Aggregate thuần:** có thể ghi nhận events mà không phụ thuộc Spring; để adapter/application service thực hiện publish sẽ giữ domain model độc lập hơn.
- **Application service:** hiểu use case và transaction boundary, là nơi dễ đặt quyết định phát event khi hành vi hoàn tất đúng.

Nếu kiến trúc dùng Spring Data domain events hoặc unit-of-work adapter, cơ chế có thể khác; vẫn phải đảm bảo event thật sự đại diện cho một business fact và ranh giới giao dịch nhất quán.

## 5. Ví dụ Java 17+ hoàn chỉnh: commit và rollback

Ví dụ chạy bằng Spring Framework 6.2.12, Spring JDBC, H2 in-memory và Maven, **không cần Spring Boot**. Sử dụng TransactionTemplate để thấy rõ toàn bộ transaction. Service INSERT một đơn hàng rồi publish OrderSubmitted. Sau đó service cho transaction commit hoặc đánh dấu rollback-only.

Ba listener ghi lại quan sát vào list trong bộ nhớ:

- **@EventListener:** thêm now:ID ngay khi publish.
- **@TransactionalEventListener(AFTER_COMMIT):** thêm commit:ID chỉ khi commit thành công.
- **@TransactionalEventListener(AFTER_ROLLBACK):** thêm rollback:ID khi rollback.

Không có listener nào ghi thêm database sau commit, nên ví dụ tách được semantics của sự kiện khỏi rủi ro data access sau transaction.

Tạo thư mục:

~~~text
domain-event-service/
├── pom.xml
└── src/main/java/demo/DomainEventFromServiceDemo.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>domain-event-service</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. src/main/java/demo/DomainEventFromServiceDemo.java

~~~java
package demo;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class DomainEventFromServiceDemo {

    public record OrderSubmitted(
            String eventId,
            long orderId,
            Instant occurredAt) {}

    public static final class EventTrace {
        private final List<String> history = new CopyOnWriteArrayList<>();

        public void add(String value) {
            history.add(value);
        }

        public String snapshot() {
            return String.join(" > ", history);
        }
    }

    public static final class OrderApplicationService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        public OrderApplicationService(
                JdbcTemplate jdbc,
                TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.tx = tx;
            this.publisher = publisher;
        }

        public void submit(long id, boolean rollback) {
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO purchase_orders(id, state) VALUES (?, ?)",
                    id, "SUBMITTED");

                // Publish trong transaction, trước commit thật.
                publisher.publishEvent(new OrderSubmitted(
                    UUID.randomUUID().toString(), id, Instant.now()));

                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }
    }

    public static final class OrderListeners {
        private final EventTrace trace;

        public OrderListeners(EventTrace trace) {
            this.trace = trace;
        }

        @EventListener
        public void immediately(OrderSubmitted event) {
            trace.add("now:" + event.orderId());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderSubmitted event) {
            trace.add("commit:" + event.orderId());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderSubmitted event) {
            trace.add("rollback:" + event.orderId());
        }
    }

    @Configuration
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:domain_service;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
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
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager txManager) {
            return new TransactionTemplate(txManager);
        }

        @Bean
        public EventTrace eventTrace() {
            return new EventTrace();
        }

        @Bean
        public OrderApplicationService orderApplicationService(
                JdbcTemplate jdbc,
                TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            return new OrderApplicationService(jdbc, tx, publisher);
        }

        @Bean
        public OrderListeners orderListeners(EventTrace trace) {
            return new OrderListeners(trace);
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            EventTrace trace = context.getBean(EventTrace.class);
            OrderApplicationService service =
                    context.getBean(OrderApplicationService.class);

            jdbc.execute("""
                CREATE TABLE purchase_orders (
                    id BIGINT PRIMARY KEY,
                    state VARCHAR(20) NOT NULL
                )
                """);

            service.submit(1L, false);
            int one = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_orders WHERE id = 1",
                Integer.class);
            System.out.println(
                "after-commit db=" + one + " trace=" + trace.snapshot());

            service.submit(2L, true);
            int two = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_orders WHERE id = 2",
                Integer.class);
            System.out.println(
                "after-rollback db=" + two + " trace=" + trace.snapshot());
        }
    }
}
~~~

Chạy ở thư mục chứa pom.xml với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.DomainEventFromServiceDemo
~~~

Hai dòng do chương trình tự in:

~~~text
after-commit db=1 trace=now:1 > commit:1
after-rollback db=0 trace=now:1 > commit:1 > now:2 > rollback:2
~~~

Nếu thư viện hoặc Maven in thêm log thì vẫn chỉ có hai dòng do code chương trình in ở trên. UUID và Instant được tạo cho metadata event nhưng không in, nên stdout dự đoán không phụ thuộc thời gian hoặc randomness.

### 5.3. Diễn giải nhánh commit

1. TransactionTemplate mở transaction JDBC.
2. Service INSERT order 1, chưa commit.
3. Service gọi publishEvent với OrderSubmitted.
4. Listener thông thường ghi now:1 ngay lập tức.
5. Listener AFTER_COMMIT đăng ký synchronization với transaction hiện tại.
6. Lambda của TransactionTemplate kết thúc, transaction manager commit thành công.
7. Spring kích hoạt listener AFTER_COMMIT; trace bổ sung commit:1.
8. Query sau khi service trở về trả db=1.

### 5.4. Diễn giải nhánh rollback

1. Transaction thứ hai INSERT order 2.
2. Service publish event, listener thông thường thêm now:2.
3. status.setRollbackOnly yêu cầu rollback transaction.
4. Transaction manager rollback; listener AFTER_COMMIT không chạy.
5. Listener AFTER_ROLLBACK thêm rollback:2.
6. Query sau transaction trả db=0, nhưng now:2 vẫn trong list vì thay đổi ở bộ nhớ này **không thuộc JDBC transaction**.

Đây là lý do không thực hiện các side effect không thể hoàn tác như gửi email hoặc gọi API thanh toán tại một listener thông thường nếu chúng chỉ được phép xảy ra sau khi database commit.

## 6. Bốn phase khi cần đồng bộ theo transaction

| TransactionPhase | Ý nghĩa | Trường hợp |
| --- | --- | --- |
| BEFORE_COMMIT | Listener chạy trước commit thật | Kiểm tra và chuẩn bị dữ liệu; vẫn có khả năng rollback |
| AFTER_COMMIT | Listener chỉ chạy nếu commit thành công | Notification hoặc workflow chỉ nên bắt đầu sau commit |
| AFTER_ROLLBACK | Listener chạy nếu transaction rollback | Dọn resource tạm và quan sát thất bại |
| AFTER_COMPLETION | Listener chạy khi transaction kết thúc, dù commit hay rollback | Cleanup và metrics chung |

AFTER_COMMIT của TransactionalEventListener là trường hợp đặc biệt trong pha afterCompletion với trạng thái committed; không đồng nhất hoàn toàn với hook TransactionSynchronization.afterCommit(). Không nên thiết kế thứ tự giữa các hook khác nhau bằng suy đoán từ tên.

Khi event được phát **ngoài transaction**, listener transactional mặc định không xử lý; fallbackExecution=true cho phép chạy ngay theo đường fallback. Đây là thay đổi hành vi có chủ đích, không phải cách sửa lỗi transaction boundary bị mất.

## 7. Ranh giới lỗi và tình huống cần tránh

### 7.1. Publish bên trong transaction khác với publish sau commit

Trong @Transactional method, lời gọi publishEvent diễn ra trước khi transaction interceptor hoàn tất commit. Nếu không có transaction ngoài, việc đặt publishEvent **sau khi gọi một service đã commit** sẽ khiến TransactionalEventListener không có transaction để theo dõi.

Nếu dùng PROPAGATION_REQUIRED, một service con có thể tham gia transaction bao ngoài; callback AFTER_COMMIT đợi đến khi transaction vật lý ngoài cùng commit. Với REQUIRES_NEW, transaction con commit riêng nên event có thể được xử lý ngay sau inner commit dù outer transaction sau đó rollback.

### 7.2. Đừng ghi dữ liệu mới trực tiếp sau commit mà không có transaction mới

Theo Spring Framework, callback AFTER_COMMIT xảy ra sau khi transaction đã commit, nhưng resource cũ như JDBC Connection có thể còn bound trong lúc callback chạy. Lời gọi data access tại thời điểm này có thể tham gia resource đó mà **không còn lần commit tiếp theo**.

Muốn lưu audit bằng giao dịch độc lập sau commit, dùng một Spring service khác được gọi qua proxy với:

~~~java
// Minh họa, không phải chương trình độc lập.
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAudit(String eventId) {
    auditRepository.save(new AuditRecord(eventId));
}
~~~

Nếu audit hay outbox phải được lưu nguyên tử với đơn hàng thì nên INSERT chúng ngay **trong transaction gốc**, không đợi listener sau commit.

### 7.3. Exception và async

- Listener thông thường đồng bộ có thể ném exception về publisher, dẫn đến rollback theo quy tắc transaction hiện tại.
- Listener AFTER_COMMIT có thể thất bại **sau khi DB đã commit**. Lỗi callback không thể đảo ngược transaction cũ; cần log, metrics, retry hoặc workflow khác.
- Listener dùng @Async có thể chạy ở thread khác, publishEvent không có nghĩa công việc nền đã hoàn thành; @Order không bảo đảm thứ tự hoàn tất khi chạy song song.
- Transaction theo PlatformTransactionManager thường ràng buộc với thread. Nếu việc publish bị chuyển sang task executor mà không có transaction trong thread mới, listener transactional có thể bị bỏ qua.
- Với ReactiveTransactionManager, ngữ cảnh nằm trong Reactor Context; Spring 6.1+ hỗ trợ transactional events khi context được mang đúng theo event, ví dụ qua TransactionalEventPublisher.

Không coi publishEvent là một broker có acknowledgment, replay hoặc retry mặc định.

## 8. Khi nào dùng transactional outbox?

TransactionalEventListener(AFTER_COMMIT) chỉ giải quyết **thời điểm**, chưa giải quyết **độ bền**. Tình huống crash:

~~~text
BEGIN transaction
  INSERT purchase_orders
COMMIT
[process crash trước khi gửi broker]
database có đơn hàng nhưng thông điệp có thể chưa được gửi
~~~

Để tránh mất ý định gửi integration event, dùng **transactional outbox**:

1. Trong cùng transaction nghiệp vụ, ghi dữ liệu đơn hàng.
2. INSERT một bản ghi outbox có eventId, aggregateId, eventType, payload và createdAt.
3. Commit cùng lúc: đơn hàng và outbox cùng tồn tại hoặc cùng rollback.
4. Relay/worker đọc outbox theo batch, gửi broker và ghi trạng thái đã xử lý.
5. Khi gửi lỗi, retry; dùng eventId và idempotency ở consumer để giảm hậu quả duplicate.
6. Theo dõi backlog, dead-letter hoặc các trạng thái cần vận hành.

Ví dụ schema tối giản (SQL minh họa, cần điều chỉnh cho hệ quản trị DB thực):

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(50) PRIMARY KEY,
    aggregate_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload_json CLOB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP
);
~~~

Quan trọng: bản ghi outbox phải được tạo **trước commit trong transaction của application service**. Không chuyển việc ghi outbox sang listener AFTER_COMMIT và nghĩ rằng nó còn nguyên tử với transaction chính.

Có thể dùng callback after commit để đánh thức relay giúp giảm latency, nhưng relay vẫn phải có cơ chế đọc lại outbox định kỳ vì callback đánh thức có thể bị mất khi process crash.

Outbox không tự tạo exactly-once end-to-end; broker có thể giao lại, relay có thể retry sau khi gửi nhưng trước khi đánh dấu đã gửi, vì vậy consumer cần idempotency/deduplication.

## 9. Domain event khác integration event

**Domain event** nói về fact trong bounded context hiện tại; có thể chỉ cần phân phối in-process bằng Spring.

**Integration event** là hợp đồng với các hệ thống khác: cần schema rõ ràng, version, bảo mật, tương thích ngược, tenant/correlation và cơ chế chuyển giao. Không nên serialize nguyên aggregate chứa trạng thái nội bộ để thành payload công khai.

Có thể tổ chức:

~~~text
OrderApplicationService
  |-- order.submit()                     [domain]
  |-- publish/record OrderSubmitted      [domain event]
  |-- map thành OrderSubmittedV1         [integration contract]
  |-- INSERT outbox record               [cùng transaction]
  +-- COMMIT
        |
        +-- relay -> broker -> idempotent consumer
~~~

Nếu integration event bắt buộc đi cùng dữ liệu nghiệp vụ, application service hoặc một adapter chạy **trong cùng transaction** cần chịu trách nhiệm ghi outbox. Nếu event chỉ phục vụ bộ nhớ đệm, metrics không quan trọng hoặc tác vụ có thể được tái dựng, in-process event sau commit có thể đã đủ.

## 10. Idempotency, thứ tự và quan sát hệ thống

- **Idempotency:** đặt eventId duy nhất cho một business occurrence. Subscriber thực hiện các side effect quan trọng nên dùng eventId/business key để ngăn xử lý trùng khi retry.
- **Ordering:** trong một JVM, listener có thể được ưu tiên bằng @Order, nhưng khi @Async hoặc broker nhiều partition, không có bảo đảm thứ tự hoàn tất toàn cục; nếu cần thứ tự theo aggregate, định nghĩa partition key, version hoặc workflow.
- **Observability:** log eventId, aggregateId và correlation ID; đo số event được phát, callback thất bại, outbox backlog và thời gian xử lý.
- **Testing:** test cả nhánh commit, rollback sau publish, failure trong listener, transaction propagation, duplicate event và crash/retry.
- **Ownership:** mỗi subscriber cần một hợp đồng rõ nó xử lý fact nào và điều kiện nào được coi là hoàn tất; publisher không nên coi việc gọi void publishEvent là bảo đảm mọi side effect thành công.

## 11. Lỗi phổ biến

| Lỗi | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| Publish từ controller sau khi service đã commit rồi dùng listener transactional | Không có transaction để đăng ký callback | Publish trong use case transaction, để listener đợi AFTER_COMMIT |
| Gửi email trong regular EventListener dù nghiệp vụ có thể rollback | Side effect ngoài DB không rollback theo | AFTER_COMMIT hoặc outbox khi cần độ bền |
| Nghĩ repository.save đã commit | save có thể chưa flush/commit | Phân biệt persistence request với commit thật |
| Truyền cả JPA entity/lazy object | Payload mutable, phụ thuộc session | Truyền ID và snapshot cần thiết |
| Ghi DB ngay trong AFTER_COMMIT mà không mở giao dịch mới | Resource cũ có thể không còn commit | REQUIRES_NEW khi phù hợp hoặc ghi trong transaction gốc |
| Coi Spring event in-memory là message queue bền vững | Process crash có thể làm mất side effect | Transactional outbox, retry, idempotency |
| Không đặt eventId và không kiểm tra duplicate | Retry có thể cộng tiền/gửi email hai lần | Dùng khóa idempotency và trạng thái xử lý |
| Bỏ qua exception từ listener đồng bộ | Use case có thể rollback ngoài dự kiến | Thiết kế ranh giới và chính sách lỗi |
| Cho rằng @Async giữ transaction context | Thread mới không tự nhận transaction | Publish trong đúng context hoặc đổi thiết kế |

## 12. Checklist trước khi hoàn thành thiết kế

1. Fact nghiệp vụ được xác nhận ở đâu? Tên event có ở thì quá khứ và payload có rõ ràng không?
2. Application service có chịu trách nhiệm transaction của use case không? Lời gọi có đi qua Spring proxy nếu dùng @Transactional không?
3. Publish có diễn ra **trước khi transaction kết thúc**, sau khi domain operation hợp lệ không?
4. Listener nào cần chạy **ngay**, listener nào phải đợi **AFTER_COMMIT** hoặc **AFTER_ROLLBACK**?
5. Nếu rollback xảy ra **sau publish** thì có side effect nào không thể đảo ngược đã thực hiện không?
6. Callback sau commit có cần ghi database không, và transaction mới đã được mở đúng chưa?
7. Nếu process chết sau commit nhưng trước khi gửi notification/broker, hệ thống phục hồi bằng cách nào?
8. Event payload có chứa PII/lazy entity/mutable collection không?
9. Có eventId, correlation, retry, idempotency và monitoring phù hợp không?
10. Unit/integration tests đã kiểm tra đúng cả commit, rollback và thứ tự callback cần thiết chưa?

**Kết luận:** Publish domain event tại application service làm rõ kết quả nghiệp vụ ở ranh giới use case và giảm coupling. Hãy **publish trong transaction đang hoạt động** khi cần transactional event listener, nhưng nhớ rằng chỉ callback AFTER_COMMIT mới chờ commit. Với các tác vụ tích hợp cần bền vững qua crash, hãy ghi **outbox trong cùng transaction** và thiết kế relay/consumer idempotent.

## Tài liệu chính thức

- Spring Framework 6.2 — ApplicationContext events: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework — ApplicationEventPublisher Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework — TransactionalEventListener Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework — TransactionSynchronization Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
