# @TransactionalEventListener trong Spring

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của @TransactionalEventListener trong xử lý event gắn với transaction.
- Phân biệt @EventListener thông thường với listener theo transaction phase.
- Mô tả bốn phase BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION.
- Hiểu hành vi mặc định khi event được phát ngoài transaction và sử dụng fallbackExecution đúng cách.
- Biết ảnh hưởng của propagation, transaction lồng nhau và Spring proxy đến thời điểm listener chạy.
- Xử lý thao tác database sau commit bằng transaction riêng.
- Kết hợp listener hậu commit với worker bất đồng bộ mà không giả định transaction được truyền sang thread khác.
- Kiểm thử các trường hợp commit, rollback và event ngoài transaction.

## 1. Vì sao cần @TransactionalEventListener?

ApplicationEventPublisher cho phép một bean phát event mà không cần biết listener nào sẽ nhận. Với @EventListener thông thường, listener được gọi trong quá trình dispatch event.

Giả sử một service tạo đơn hàng trong transaction rồi phát OrderCreatedEvent:

~~~java
@Transactional
public void createOrder(String orderId) {
    orderRepository.save(new Order(orderId));
    publisher.publishEvent(new OrderCreatedEvent(orderId));
}
~~~

Nếu listener thông thường gửi email ngay khi nhận event, email có thể được gửi trước khi transaction commit. Sau đó một thao tác khác trong service thất bại và transaction rollback. Kết quả là email đã được gửi cho một đơn hàng không tồn tại trong database.

@TransactionalEventListener cho phép gắn listener với một giai đoạn trong vòng đời transaction. Thay vì xử lý ngay lúc event được dispatch, Spring đăng ký listener để gọi ở phase phù hợp.

~~~java
@Component
public class OrderListener {

    @TransactionalEventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Committed order: " + event.orderId());
    }
}
~~~

Khi event được phát trong một transaction đang hoạt động, listener trên mặc định chạy ở AFTER_COMMIT. Nếu transaction rollback, listener này không chạy.

Annotation không tạo transaction và cũng không làm transaction commit. Nó chỉ đăng ký thời điểm gọi listener dựa trên transaction đang chứa event.

## 2. So sánh @EventListener và @TransactionalEventListener

| Đặc điểm | @EventListener | @TransactionalEventListener |
|---|---|---|
| Thời điểm gọi | Khi event được dispatch. | Theo phase của transaction đã phát event. |
| Có cần transaction | Không. | Mặc định cần transaction đang hoạt động khi publish. |
| Mặc định | Gọi trong quá trình dispatch. | AFTER_COMMIT. |
| Khi transaction rollback | Listener có thể đã chạy trước rollback. | Listener AFTER_COMMIT không chạy. |
| Khi event ngoài transaction | Vẫn được gọi. | Bị bỏ qua mặc định; có thể bật fallbackExecution. |
| Mục đích | Phản ứng với event nói chung. | Phản ứng theo kết quả transaction. |

Dùng @EventListener khi listener chỉ cần biết một sự kiện đã xảy ra và không phụ thuộc transaction chứa sự kiện có commit hay không.

Dùng @TransactionalEventListener khi side effect phải gắn với kết quả transaction. Ví dụ, chỉ gửi xác nhận đơn hàng sau khi dữ liệu đơn hàng đã commit.

Không phải mọi event được phát từ service có @Transactional đều cần listener transactional. Hãy xác định listener có cần đợi commit/rollback hay không trước khi chọn annotation.

## 3. Bốn phase của TransactionPhase

Thuộc tính phase nhận một giá trị trong enum TransactionPhase:

| Phase | Thời điểm | Ví dụ phù hợp |
|---|---|---|
| BEFORE_COMMIT | Ngay trước khi transaction commit. | Kiểm tra cuối hoặc ghi dữ liệu phải cùng transaction. |
| AFTER_COMMIT | Sau khi commit thành công; đây là mặc định. | Gửi thông báo hoặc khởi chạy tác vụ hậu commit. |
| AFTER_ROLLBACK | Sau khi transaction rollback. | Ghi nhận rollback hoặc khởi động quy trình bù trừ. |
| AFTER_COMPLETION | Sau khi transaction kết thúc, dù commit hay rollback. | Dọn dẹp hoặc ghi nhận kết quả hoàn tất chung. |

### 3.1. BEFORE_COMMIT

Listener BEFORE_COMMIT được gọi khi transaction vẫn chưa commit:

~~~java
@Component
public class OrderValidationListener {

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void validate(OrderCreatedEvent event) {
        System.out.println("Validate order: " + event.orderId());
    }
}
~~~

Ở phase này, listener có thể đọc hoặc ghi database trong transaction hiện tại nếu tài nguyên và transaction manager cho phép. Nếu listener ném exception, quá trình commit có thể bị hủy và transaction có thể rollback.

BEFORE_COMMIT phù hợp với kiểm tra hoặc cập nhật database cần cùng transaction. Không nên gửi email hoặc gọi API bên ngoài ở phase này vì commit vẫn có thể thất bại sau khi listener hoàn tất.

### 3.2. AFTER_COMMIT

AFTER_COMMIT chỉ chạy khi transaction commit thành công:

~~~java
@Component
public class OrderNotificationListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void notifyCustomer(OrderCreatedEvent event) {
        System.out.println("Notify order: " + event.orderId());
    }
}
~~~

Các tác vụ thường đặt ở phase này:

- Gửi email hoặc notification.
- Làm mới cache dựa trên dữ liệu đã lưu.
- Thông báo cho thành phần khác trong cùng ứng dụng.
- Khởi chạy một tác vụ nền.
- Gửi message ra hệ thống bên ngoài.

Nếu transaction rollback, listener AFTER_COMMIT không được gọi.

AFTER_COMMIT chỉ xác định thời điểm callback. Nó không tự tạo transaction mới và không lưu callback vào hàng đợi bền vững.

### 3.3. AFTER_ROLLBACK

AFTER_ROLLBACK được gọi sau khi transaction rollback:

~~~java
@Component
public class OrderRollbackListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void recordRollback(OrderCreatedEvent event) {
        System.out.println("Order rolled back: " + event.orderId());
    }
}
~~~

Có thể dùng phase này để ghi nhận thất bại, cập nhật metric, giải phóng tài nguyên đã chuẩn bị hoặc khởi động một quy trình bù trừ.

Listener rollback không tự retry phương thức nghiệp vụ. Nếu cần thử lại, hãy xây dựng chính sách retry riêng, có giới hạn và có idempotency.

Nếu listener cần ghi database sau rollback, nên gọi một service có transaction mới, thường dùng REQUIRES_NEW.

### 3.4. AFTER_COMPLETION

AFTER_COMPLETION được gọi khi transaction kết thúc, bất kể commit hay rollback:

~~~java
@Component
public class OrderCompletionListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void completed(OrderCreatedEvent event) {
        System.out.println("Transaction completed: " + event.orderId());
    }
}
~~~

Phase này hữu ích cho công việc dọn dẹp hoặc ghi nhận rằng transaction đã kết thúc mà không cần phân biệt kết quả.

Method nhận event không tự nhận một tham số transaction status. Nếu cần kiểm tra trạng thái commit/rollback ở callback cấp thấp, có thể dùng TransactionSynchronization.afterCompletion(int status).

## 4. Event phát ngoài transaction

ApplicationEventPublisher.publishEvent không yêu cầu transaction. Một scheduler, runner hoặc background worker có thể phát event ngoài transaction.

~~~java
@Component
public class ImportJob {

    private final ApplicationEventPublisher publisher;

    public ImportJob(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void finishImport(String batchId) {
        publisher.publishEvent(new ImportCompletedEvent(batchId));
    }
}
~~~

Nếu finishImport không chạy trong transaction:

- Event vẫn được publish bình thường.
- @EventListener thông thường vẫn được gọi.
- @TransactionalEventListener mặc định không được gọi vì không có transaction phase để đăng ký.

Tình huống này thường gặp trong CommandLineRunner, ApplicationRunner, scheduled job, test không có transaction và worker @Async không mở transaction riêng.

Việc listener không chạy không có nghĩa publisher bị lỗi. Đó là hành vi mặc định của transactional listener.

## 5. fallbackExecution = true

Nếu event có thể được phát cả trong và ngoài transaction, và nghiệp vụ chấp nhận xử lý ngay khi không có transaction, có thể bật fallbackExecution:

~~~java
@Component
public class ImportListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT,
            fallbackExecution = true
    )
    public void onImportCompleted(ImportCompletedEvent event) {
        System.out.println("Handle import: " + event.batchId());
    }
}
~~~

Hành vi:

- Có transaction: listener được gọi tại phase đã chọn.
- Không có transaction: listener được gọi ngay theo cơ chế fallback.

fallbackExecution không mở transaction mới, không tạo commit giả, không chờ transaction bắt đầu trong tương lai và không chứng minh dữ liệu đã commit.

Với AFTER_COMMIT, event ngoài transaction sẽ kích hoạt listener ngay trong quá trình dispatch. Chỉ bật fallback nếu hành động có ý nghĩa hợp lệ trong cả hai trường hợp. Nếu listener bắt buộc phải chạy sau commit thực sự, giữ fallbackExecution mặc định là false.

## 6. Spring đăng ký listener theo transaction synchronization

Khi event được phát trong transaction, Spring đăng ký listener như một transaction synchronization. Transaction manager sẽ gọi callback tại phase tương ứng.

Luồng khái quát:

~~~text
@Transactional service
        |
        v
Bắt đầu transaction
        |
        v
Ghi dữ liệu nghiệp vụ
        |
        v
publishEvent(event)
        |
        v
Đăng ký transactional listener
        |
        v
Transaction manager commit hoặc rollback
        |
        +---- BEFORE_COMMIT
        |
        +---- Commit thành công ---> AFTER_COMMIT
        |
        +---- Rollback -----------> AFTER_ROLLBACK
        |
        +---- Kết thúc -----------> AFTER_COMPLETION
~~~

ApplicationEventPublisher không cần biết listener nào chọn phase nào. Spring giữ thông tin event và gọi listener ở thời điểm tương ứng.

Trong ứng dụng thông thường, nên dùng @TransactionalEventListener. API TransactionSynchronization cấp thấp chỉ cần thiết khi muốn đăng ký callback transaction tùy chỉnh.

## 7. Ảnh hưởng của propagation

@TransactionalEventListener gắn với transaction đang hoạt động tại thời điểm publishEvent. Vì vậy, transaction propagation có thể làm thay đổi transaction mà event được gắn vào.

| Propagation | Hành vi | Ảnh hưởng |
|---|---|---|
| REQUIRED | Tham gia transaction hiện tại hoặc tạo transaction mới nếu chưa có. | Listener gắn với transaction được tham gia hoặc tạo. |
| REQUIRES_NEW | Tạm dừng transaction hiện tại và tạo transaction mới. | Listener của transaction trong có thể chạy khi transaction trong commit, dù transaction ngoài còn tiếp tục. |
| SUPPORTS | Tham gia transaction nếu có; nếu không thì chạy không transaction. | Không có transaction thì listener mặc định bị bỏ qua. |
| NOT_SUPPORTED | Tạm dừng transaction hiện tại và chạy không transaction. | Event phát trong đoạn này không có phase để chờ. |
| MANDATORY | Yêu cầu phải có transaction hiện tại. | Ném exception nếu không có transaction. |
| NEVER | Yêu cầu không có transaction. | Không có transaction để listener gắn vào. |

Ví dụ, một phương thức REQUIRES_NEW phát event rồi commit transaction riêng. Listener AFTER_COMMIT của event đó có thể chạy ngay sau commit của transaction trong, dù transaction ngoài vẫn đang tiếp tục và có thể rollback sau đó.

Không giả định rollback của transaction ngoài sẽ đảo ngược dữ liệu hoặc side effect gắn với transaction REQUIRES_NEW đã commit.

Với NESTED dùng savepoint, việc hoàn tất savepoint không đồng nghĩa transaction vật lý bên ngoài đã commit. Listener thường vẫn gắn với transaction bên ngoài và chờ kết quả hoàn tất của transaction đó.

## 8. Ghi database trong listener AFTER_COMMIT

Sau commit, transaction ban đầu đã hoàn tất. Trong callback hậu commit, một số tài nguyên transaction có thể vẫn được giữ cho đến khi cleanup kết thúc. Nếu listener ghi database đồng bộ, thao tác đó có thể truy cập tài nguyên cũ nhưng không được commit như một transaction mới.

Hãy gọi một service riêng có propagation REQUIRES_NEW:

~~~java
@Service
public class AuditWriter {

    private final JdbcTemplate jdbcTemplate;

    public AuditWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordOrder(String orderId) {
        jdbcTemplate.update(
                "insert into order_audit(order_id) values (?)",
                orderId
        );
    }
}
~~~

Listener:

~~~java
@Component
public class OrderAuditListener {

    private final AuditWriter auditWriter;

    public OrderAuditListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        auditWriter.recordOrder(event.orderId());
    }
}
~~~

AuditWriter là bean riêng nên lời gọi đi qua Spring proxy. REQUIRES_NEW mở transaction độc lập cho thao tác ghi.

Không gọi method @Transactional của chính class listener bằng self-invocation rồi kỳ vọng proxy áp dụng propagation. Hãy tách service hoặc gọi qua bean Spring khác.

## 9. Kết hợp AFTER_COMMIT với @Async

Khi tác vụ hậu commit tốn thời gian, listener có thể điều phối công việc sang một bean async riêng:

~~~java
@Component
public class OrderAfterCommitListener {

    private final AsyncOrderNotifier notifier;

    public OrderAfterCommitListener(AsyncOrderNotifier notifier) {
        this.notifier = notifier;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        notifier.notifyCustomer(event.orderId());
    }
}
~~~

~~~java
@Service
public class AsyncOrderNotifier {

    private final OrderQueryService queryService;

    public AsyncOrderNotifier(OrderQueryService queryService) {
        this.queryService = queryService;
    }

    @Async
    public void notifyCustomer(String orderId) {
        int count = queryService.countById(orderId);
        System.out.println("Committed order " + orderId + ", rows=" + count);
    }
}
~~~

~~~java
@Service
public class OrderQueryService {

    private final JdbcTemplate jdbcTemplate;

    public OrderQueryService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(readOnly = true)
    public int countById(String orderId) {
        return jdbcTemplate.queryForObject(
                "select count(*) from orders where order_id = ?",
                Integer.class,
                orderId
        );
    }
}
~~~

Cần bật @EnableAsync và cấu hình TaskExecutor phù hợp.

Trong mẫu này:

- Listener chỉ được gọi sau commit thành công.
- Listener chuyển orderId sang worker.
- Worker chạy trên thread khác và không kế thừa transaction của publisher.
- OrderQueryService mở transaction đọc riêng trên worker thread.
- Publisher không chờ worker hoàn tất.

Tách listener và worker thành bean riêng giúp lời gọi @Async đi qua Spring proxy. Nếu một method trong cùng class tự gọi method @Async khác, self-invocation thường bỏ qua proxy và không chuyển lời gọi sang executor.

Không chuyển JDBC Connection, EntityManager hoặc JPA entity đang được quản lý sang worker. Hãy truyền ID hoặc immutable DTO để worker truy vấn lại trong transaction riêng.

## 10. Exception và kết quả transaction

Exception có ý nghĩa khác nhau tùy phase:

| Phase | Khi listener ném exception |
|---|---|
| BEFORE_COMMIT | Có thể làm commit thất bại và transaction rollback. |
| AFTER_COMMIT | Transaction đã commit; exception không đảo ngược dữ liệu đã commit. |
| AFTER_ROLLBACK | Transaction đã rollback; exception không thể biến rollback thành commit. |
| AFTER_COMPLETION | Transaction đã hoàn tất; exception không thay đổi kết quả transaction. |

Với listener đồng bộ, exception có thể truyền qua đường gọi callback và khiến caller thấy lỗi dù transaction đã commit. Vì vậy, lỗi AFTER_COMMIT phải được xử lý như lỗi hậu commit, không phải lỗi có thể rollback transaction gốc.

Với @Async method trả về void, exception xảy ra trên worker thread và không quay lại publisher. Spring mặc định ghi log lỗi async; có thể cấu hình AsyncUncaughtExceptionHandler. Nếu method trả về Future hoặc CompletableFuture, caller có thể quan sát lỗi khi giữ và kiểm tra future.

Không dùng exception trong AFTER_COMMIT như một cơ chế rollback. Nếu side effect thất bại, cần retry hoặc lưu trạng thái công việc riêng.

## 11. Kiểm thử transactional listener

Một integration test cần chú ý transaction do test framework tạo ra. Nếu test method có @Transactional, transaction thường rollback khi test kết thúc nên listener AFTER_COMMIT không chạy theo cách test mong đợi.

Một số cách kiểm thử:

- Không mở transaction ở test method; gọi service @Transactional qua Spring proxy.
- Dùng @Commit khi muốn transaction của test commit.
- Dùng TestTransaction.flagForCommit() và TestTransaction.end() để kết thúc transaction test với commit.
- Dùng spy, counter hoặc bảng audit để quan sát side effect của listener.
- Với listener async, dùng latch hoặc Awaitility có timeout thay vì Thread.sleep tùy tiện.

Ví dụ:

~~~java
@SpringBootTest
class OrderEventListenerTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void orderIsCommitted() {
        orderService.placeOrder("ORD-TEST");

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from orders where order_id = ?",
                Integer.class,
                "ORD-TEST"
        );

        assertEquals(1, count);
    }
}
~~~

Test trên xác nhận dữ liệu đã commit. Nếu muốn xác nhận side effect của listener, hãy kiểm tra collaborator hoặc bản ghi mà listener tạo ra. Không suy luận listener chạy chỉ từ việc publisher trả về.

## 12. Ví dụ hoàn chỉnh với Java 17, Spring Boot và H2

Ví dụ thể hiện ba trường hợp:

1. Đơn hàng ORD-126 commit thành công: BEFORE_COMMIT, AFTER_COMMIT và AFTER_COMPLETION chạy.
2. Đơn hàng ORD-127 rollback: AFTER_ROLLBACK và AFTER_COMPLETION chạy; AFTER_COMMIT không chạy.
3. JOB-126 được phát ngoài transaction: listener có fallbackExecution=true chạy ngay.

### Cấu trúc thư mục

~~~text
spring-transactional-event-listener/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/events/
        │   ├── TransactionalEventApplication.java
        │   ├── OrderCreatedEvent.java
        │   ├── JobCompletedEvent.java
        │   ├── OrderService.java
        │   ├── OrderPhaseListeners.java
        │   └── JobFallbackListener.java
        └── resources/
            ├── application.properties
            └── schema.sql
~~~

### 12.1. Dependency

File pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-transactional-event-listener</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 12.2. Database

File application.properties:

~~~properties
spring.datasource.url=jdbc:h2:mem:transactional-event-demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.main.web-application-type=none
~~~

File schema.sql:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(50) PRIMARY KEY
);
~~~

### 12.3. Event types

File OrderCreatedEvent.java:

~~~java
package com.example.events;

public record OrderCreatedEvent(String orderId) {
}
~~~

File JobCompletedEvent.java:

~~~java
package com.example.events;

public record JobCompletedEvent(String jobId) {
}
~~~

### 12.4. Transactional publisher

File OrderService.java:

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final JdbcTemplate jdbcTemplate;
    private final ApplicationEventPublisher publisher;

    public OrderService(
            JdbcTemplate jdbcTemplate,
            ApplicationEventPublisher publisher
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.publisher = publisher;
    }

    @Transactional
    public void placeOrder(String orderId) {
        jdbcTemplate.update(
                "insert into orders(order_id) values (?)",
                orderId
        );

        publisher.publishEvent(new OrderCreatedEvent(orderId));

        System.out.println(
                "OrderService: event published for " + orderId
        );
    }

    @Transactional
    public void placeOrderAndRollback(String orderId) {
        jdbcTemplate.update(
                "insert into orders(order_id) values (?)",
                orderId
        );

        publisher.publishEvent(new OrderCreatedEvent(orderId));

        System.out.println(
                "OrderService: event published for " + orderId
        );

        throw new IllegalStateException("Simulate transaction rollback");
    }
}
~~~

Cả hai phương thức phát event khi transaction đang hoạt động. Phương thức thứ hai cố ý ném exception để transaction rollback.

### 12.5. Listener cho từng phase

File OrderPhaseListeners.java:

~~~java
package com.example.events;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderPhaseListeners {

    @Order(10)
    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void beforeCommit(OrderCreatedEvent event) {
        System.out.println("BEFORE_COMMIT: validate " + event.orderId());
    }

    @Order(20)
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        System.out.println("AFTER_COMMIT: send receipt " + event.orderId());
    }

    @Order(30)
    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(OrderCreatedEvent event) {
        System.out.println("AFTER_ROLLBACK: rollback " + event.orderId());
    }

    @Order(40)
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void afterCompletion(OrderCreatedEvent event) {
        System.out.println("AFTER_COMPLETION: completed " + event.orderId());
    }
}
~~~

Mỗi method được đăng ký ở một phase riêng. Khi commit, Spring gọi BEFORE_COMMIT, AFTER_COMMIT rồi AFTER_COMPLETION. Khi rollback, AFTER_ROLLBACK và AFTER_COMPLETION được gọi.

### 12.6. Listener fallback

File JobFallbackListener.java:

~~~java
package com.example.events;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class JobFallbackListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT,
            fallbackExecution = true
    )
    public void onJobCompleted(JobCompletedEvent event) {
        System.out.println(
                "FALLBACK: handled " + event.jobId()
                        + " without transaction"
        );
    }
}
~~~

Listener nhận JobCompletedEvent khi event được phát trong transaction hoặc ngoài transaction. Với event ngoài transaction, fallback chạy ngay và không tạo transaction.

### 12.7. Khởi chạy ứng dụng

File TransactionalEventApplication.java:

~~~java
package com.example.events;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TransactionalEventApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransactionalEventApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(
            OrderService orderService,
            ApplicationEventPublisher publisher,
            JdbcTemplate jdbcTemplate
    ) {
        return args -> {
            orderService.placeOrder("ORD-126");

            try {
                orderService.placeOrderAndRollback("ORD-127");
            } catch (IllegalStateException expected) {
                System.out.println("Runner: caught rollback for ORD-127");
            }

            publisher.publishEvent(new JobCompletedEvent("JOB-126"));

            Integer committedOrders = jdbcTemplate.queryForObject(
                    "select count(*) from orders",
                    Integer.class
            );

            System.out.println("Committed orders: " + committedOrders);
        };
    }
}
~~~

ApplicationRunner chạy sau khi ApplicationContext refresh và trước ApplicationReadyEvent. Các lời gọi OrderService đi qua bean Spring nên @Transactional được áp dụng.

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Bỏ qua log khởi động của Spring Boot, output do ứng dụng in ra:

~~~text
OrderService: event published for ORD-126
BEFORE_COMMIT: validate ORD-126
AFTER_COMMIT: send receipt ORD-126
AFTER_COMPLETION: completed ORD-126
OrderService: event published for ORD-127
AFTER_ROLLBACK: rollback ORD-127
AFTER_COMPLETION: completed ORD-127
Runner: caught rollback for ORD-127
FALLBACK: handled JOB-126 without transaction
Committed orders: 1
~~~

Kết quả:

- ORD-126 commit nên BEFORE_COMMIT, AFTER_COMMIT và AFTER_COMPLETION chạy.
- ORD-127 rollback nên AFTER_COMMIT không chạy; AFTER_ROLLBACK và AFTER_COMPLETION chạy.
- JOB-126 được phát ngoài transaction nên listener fallback chạy ngay.
- Database chỉ giữ một đơn hàng đã commit.

## 13. Giới hạn về độ tin cậy và transactional outbox

@TransactionalEventListener gắn callback với transaction, nhưng callback vẫn nằm trong bộ nhớ của process. Nếu database commit xong và process dừng trước khi listener hoặc worker hoàn tất, event không tự được khôi phục khi ứng dụng khởi động lại.

Nếu yêu cầu mọi thay đổi nghiệp vụ phải được gửi đi đáng tin cậy, hãy cân nhắc transactional outbox:

1. Trong cùng transaction, ghi dữ liệu nghiệp vụ.
2. Cũng trong transaction đó, ghi một bản ghi outbox với event ID và payload.
3. Worker đọc các bản ghi chưa gửi và phát message.
4. Cập nhật trạng thái gửi; nếu lỗi thì retry theo chính sách.
5. Consumer dùng idempotency để xử lý an toàn khi message được giao lại.

Outbox bảo đảm ý định phát event được lưu cùng transaction nghiệp vụ. Nó không tự bảo đảm side effect ở hệ thống ngoài chỉ xảy ra đúng một lần.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Listener không chạy | Event phát ngoài transaction và fallbackExecution mặc định false. | Phát event trong transaction hoặc bật fallback nếu phù hợp. |
| Listener chạy trước commit | Dùng @EventListener thông thường. | Dùng AFTER_COMMIT khi side effect cần dữ liệu đã commit. |
| AFTER_COMMIT không chạy khi rollback | Đây là hành vi đúng của phase. | Dùng AFTER_ROLLBACK nếu cần phản ứng với rollback. |
| Tưởng fallback tạo transaction | Hiểu nhầm fallbackExecution. | Fallback gọi listener ngay ngoài transaction. |
| Ghi DB trong AFTER_COMMIT không được commit | Tài nguyên cũ có thể vẫn truy cập được sau khi transaction hoàn tất. | Gọi service REQUIRES_NEW. |
| @Transactional không có hiệu lực | Self-invocation bỏ qua proxy hoặc propagation không tạo transaction. | Gọi qua bean Spring khác và kiểm tra propagation. |
| Worker không thấy transaction gốc | @Async chạy trên thread khác. | Mở transaction riêng trên worker nếu cần database. |
| Exception AFTER_COMMIT làm caller thấy lỗi | Transaction đã commit trước callback. | Xử lý lỗi hậu commit và retry riêng. |
| Test không kích hoạt AFTER_COMMIT | Test transaction mặc định rollback. | Dùng @Commit, TestTransaction hoặc test không bao ngoài transaction. |
| Tác vụ mất khi restart | Callback chỉ ở trong bộ nhớ. | Dùng transactional outbox hoặc broker bền vững. |

## 15. Nguyên tắc thực hành

- Dùng AFTER_COMMIT cho side effect chỉ được bắt đầu sau commit thành công.
- Dùng BEFORE_COMMIT cho kiểm tra hoặc thao tác database phải cùng transaction.
- Dùng AFTER_ROLLBACK để phản ứng với rollback, không coi đó là retry tự động.
- Dùng AFTER_COMPLETION khi cần xử lý sau cả commit và rollback.
- Giữ fallbackExecution=false nếu listener cần một transaction thật.
- Bật fallbackExecution=true chỉ khi xử lý ngay ngoài transaction là hợp lệ.
- Đặt logic nghiệp vụ trong service bean riêng có transaction phù hợp.
- Dùng REQUIRES_NEW khi callback hậu commit cần ghi database trong transaction mới.
- Không giả định @Async kế thừa transaction của publisher.
- Truyền ID hoặc immutable DTO thay vì entity/JPA proxy giữa các thread.
- Thiết kế idempotency và retry cho side effect quan trọng.
- Dùng outbox hoặc message broker khi cần giao nhận bền vững sau restart.
- Kiểm thử cả commit, rollback và trường hợp event ngoài transaction.

## 16. Tự kiểm tra

1. @TransactionalEventListener mặc định chạy ở phase nào?
2. Vì sao @EventListener có thể chạy trước khi transaction publisher commit?
3. BEFORE_COMMIT khác AFTER_COMMIT ở thời điểm nào?
4. Listener AFTER_COMMIT có chạy khi transaction rollback không?
5. AFTER_ROLLBACK và AFTER_COMPLETION khác nhau ra sao?
6. fallbackExecution=true làm gì khi event được phát ngoài transaction?
7. Vì sao fallbackExecution không bảo đảm dữ liệu đã commit?
8. Khi nào nên dùng REQUIRES_NEW trong listener?
9. REQUIRES_NEW có thể khiến listener của transaction trong chạy trước transaction ngoài như thế nào?
10. Vì sao @Async không kế thừa transaction imperative của publisher?
11. Vì sao exception AFTER_COMMIT không thể rollback dữ liệu đã commit?
12. Vì sao test transaction mặc định rollback có thể khiến listener AFTER_COMMIT không chạy?
13. Transactional outbox giải quyết khoảng trống nào giữa database commit và publish?

**Kết quả cần nắm:** @TransactionalEventListener gắn listener với một phase của transaction. Mặc định listener chạy sau commit thành công; có thể chọn BEFORE_COMMIT, AFTER_ROLLBACK hoặc AFTER_COMPLETION. Nếu event phát ngoài transaction, listener mặc định bị bỏ qua; fallbackExecution=true cho phép xử lý ngay nhưng không tạo transaction. Hãy chọn phase theo yêu cầu nghiệp vụ, mở transaction riêng khi cần ghi database sau commit và dùng outbox khi cần giao nhận bền vững.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [Spring Framework 6.2 — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative.html)
