# Tạo transactional event listener trong Spring Framework Application Events

## 1. Bài thực hành giải quyết vấn đề gì?

Trong một use case Spring, ứng dụng có thể lưu dữ liệu vào database và công bố một domain event để các module khác phản ứng:

~~~text
POST /orders
      |
      v
OrderService.place()
      |
      +-- INSERT order
      |
      +-- publish(OrderPlaced)
                  |
                  +-- SendReceipt
                  +-- UpdateSearchIndex
                  +-- Audit
~~~

Nếu chỉ viết `@EventListener`, phương thức listener thường được gọi **ngay lúc sự kiện được phân phát**. Khi `publishEvent(...)` nằm bên trong một transaction còn mở, listener có thể chạy **trước khi transaction commit**. Nếu transaction rollback về sau, listener vẫn có thể đã gửi email, gọi API hoặc cập nhật hệ thống ngoài về một đơn hàng chưa bao giờ được commit.

`@TransactionalEventListener` giải quyết **vấn đề thời điểm phản ứng theo kết quả transaction**. Thay vì xử lý ngay, Spring đăng ký callback và kích hoạt listener ở giai đoạn transaction được chọn:

- `BEFORE_COMMIT`: trước khi thực hiện commit.
- `AFTER_COMMIT`: sau khi transaction đã commit thành công (**mặc định**).
- `AFTER_ROLLBACK`: sau khi transaction rollback.
- `AFTER_COMPLETION`: sau khi transaction hoàn tất, dù commit hay rollback.

Bài này thuộc nhóm **Thực hành và tổng kết**. Người học sẽ tạo một listener thật với Spring Framework 6.2.8 và Spring JDBC/H2, kiểm tra kết quả commit, rollback và publish ngoài transaction; sau đó phân tích fallback, giao dịch mới, bất đồng bộ, lỗi thường gặp và độ tin cậy.

**Giới hạn cần nhớ từ đầu:** `AFTER_COMMIT` **không tương đương giao tin nhắn bền vững**. Transaction đã commit nhưng process vẫn có thể chết trước hoặc trong lúc handler chạy. Nếu sự kiện cần chắc chắn được giao sang một hệ thống khác, hãy cân nhắc transactional outbox.

## 2. Phân biệt @EventListener và @TransactionalEventListener

### 2.1. @EventListener thông thường

~~~java
@Component
public class ImmediateOrderListener {
    @EventListener
    public void on(OrderPlaced event) {
        // Có thể chạy ngay trong lời gọi publishEvent.
    }
}
~~~

Đây là đoạn minh họa trong một ứng dụng có `OrderPlaced` và các import tương ứng.

Với `SimpleApplicationEventMulticaster` mặc định và không có async executor, handler này thường chạy **đồng bộ trên publisher thread**. Nếu phương thức service đang có transaction, listener được gọi **khi transaction chưa chắc đã commit**.

Thích hợp khi listener cố tình tham gia ngay trong tiến trình command, chẳng hạn kiểm tra một invariant thuộc cùng transaction, hoặc một phản ứng không cần chờ commit. Nhưng không phù hợp nếu listener phải chỉ chạy cho **fact đã commit**.

### 2.2. @TransactionalEventListener

~~~java
@Component
public class CommittedOrderListener {
    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderPlaced event) {
        // Được gọi ở giai đoạn sau commit thành công.
    }
}
~~~

Đoạn trên cũng chỉ minh họa, cần import `TransactionalEventListener`, `TransactionPhase` và các type Spring.

Spring đăng ký phương thức này như một transactional application listener. Khi event được publish trong một transaction đủ điều kiện, callback tương ứng sẽ được gắn với transaction; nó **không thực thi thân handler ngay** tại vị trí `publishEvent`.

### 2.3. Bảng so sánh

| Tiêu chí | `@EventListener` thường | `@TransactionalEventListener(AFTER_COMMIT)` |
| --- | --- | --- |
| Khi nhận event trong transaction | Khi dispatch; có thể trước commit | Chỉ sau commit thành công |
| Nếu transaction rollback sau publish | Handler có thể đã chạy | Handler AFTER_COMMIT không chạy |
| Khi publish ngoài transaction | Có thể chạy bình thường | Mặc định **không chạy** |
| Có tự làm việc async? | Không | Không |
| Có tự lưu event/job bền vững? | Không | Không |
| Có tự tạo transaction mới cho DB write? | Không | Không |
| Có thể chạy bên trong cùng JVM? | Có | Có |
| Thích hợp cho notification sau commit | Chỉ khi chấp nhận ngữ nghĩa sớm | Phù hợp về **thời điểm**, chưa giải quyết durability |

**Không nhầm:** Annotation `@TransactionalEventListener` không phải tên khác của `@Transactional`. Một annotation chọn **khi listener chạy**, annotation kia cấu hình transaction cho method được Spring proxy/intercept.

## 3. Timeline của một transaction và các listener

Giả sử service:

~~~java
@Transactional
public void placeOrder(...) {
    repository.save(order);
    publisher.publishEvent(new OrderPlaced(order.getId()));
}
~~~

Dòng thời gian khái quát khi transaction thành công:

~~~text
BEGIN TRANSACTION
    |
    +-- INSERT/UPDATE order
    +-- publishEvent(OrderPlaced)
    |      |
    |      +-- ordinary @EventListener: có thể xử lý ngay
    |      +-- @TransactionalEventListener: đăng ký synchronization
    |
    +-- BEFORE_COMMIT listeners
    |
    +-- DATABASE COMMIT
    |
    +-- AFTER_COMMIT listeners
    +-- AFTER_COMPLETION listeners
    |
TRANSACTION CLEANUP
    |
method proxy returns to caller
~~~

Khi rollback:

~~~text
BEGIN TRANSACTION
    |
    +-- INSERT/UPDATE order
    +-- publishEvent(OrderPlaced)
    |      |
    |      +-- ordinary listener có thể đã chạy
    |      +-- transactional listener chờ outcome
    |
    +-- exception / rollback-only
    |
    +-- DATABASE ROLLBACK
    |
    +-- AFTER_ROLLBACK listeners
    +-- AFTER_COMPLETION listeners
    |
TRANSACTION CLEANUP
~~~

Sơ đồ giải thích mốc tương đối; Spring transaction infrastructure, transaction manager và các synchronization callbacks có chi tiết triển khai cụ thể. `BEFORE_COMMIT` không phải lời hứa chắc chắn sẽ commit: một transaction vẫn có thể fail/rollback ở thời điểm sau callback đó.

## 4. Chọn TransactionPhase phù hợp

| Phase | Khi nào được gọi? | Tình huống phù hợp | Cần tránh |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Trước commit | Validation/flush hoặc chuẩn bị dữ liệu cần tham gia transaction | Gửi side effect ngoài không thể rollback rồi tưởng đã commit |
| `AFTER_COMMIT` | Sau commit thành công | Cache invalidation, notification best-effort, projection nội bộ có thể phục hồi | Coi là durable queue hoặc ghi DB mới mà không mở transaction mới |
| `AFTER_ROLLBACK` | Sau rollback | Metrics/cleanup phù hợp, xóa tài nguyên tạm có kiểm soát | Tin dữ liệu uncommitted vẫn tồn tại |
| `AFTER_COMPLETION` | Sau commit hoặc rollback | Release/cleanup không phụ thuộc kết quả, metrics kết thúc | Dùng làm tín hiệu chỉ thành công |

### 4.1. Phase mặc định là AFTER_COMMIT

Hai ví dụ sau có cùng phase mặc định:

~~~java
@TransactionalEventListener
public void onOrder(OrderPlaced event) { }
~~~

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void onOrder(OrderPlaced event) { }
~~~

Nên viết `phase = AFTER_COMMIT` tường minh trong tài liệu và code nghiệp vụ quan trọng để người đọc không cần nhớ mặc định.

### 4.2. AFTER_COMPLETION không cho biết thành công hay thất bại qua một tham số tự động

`@TransactionalEventListener(phase = AFTER_COMPLETION)` được kích hoạt sau một transaction kết thúc cả khi commit lẫn rollback. Nếu nghiệp vụ cần hai logic khác nhau, thường nên dùng **hai listener riêng** cho `AFTER_COMMIT` và `AFTER_ROLLBACK`, hoặc cơ chế transaction synchronization có status ở cấp độ thấp. Không suy rằng một tham số `OrderPlaced` trong AFTER_COMPLETION tự mang cờ “committed”.

### 4.3. @Order chỉ điều khiển thứ tự tương đối

Spring hỗ trợ `@Order` để ưu tiên một số listener trong cùng phase. Nhưng điều đó **không tạo ordering xuyên process** và không bảo đảm side effects ở các executor async hoàn tất theo đúng thứ tự. Nếu có yêu cầu theo aggregate, hãy có version/sequence/idempotency.

## 5. Điều kiện để transactional listener hoạt động đúng

Đối với **imperative, thread-bound transactions**, cần:

1. Có Spring-managed `ApplicationContext` và listener bean được đăng ký đúng.
2. Có `PlatformTransactionManager` phù hợp (ví dụ `DataSourceTransactionManager` hoặc transaction manager của JPA).
3. Publisher được gọi khi transaction hiện hành đang **active**, trong thread/transaction context tương ứng.
4. Nếu transaction đến từ `@Transactional`, method cần được gọi **qua Spring proxy**, không phải chỉ qua `this.method()` trong cùng object ở chế độ proxy mặc định.
5. Event type khớp với tham số listener; listener không bị loại bởi condition.
6. Không chạy publish trước khi listener infrastructure được đăng ký trong startup.

Nếu không có transaction hoạt động, `@TransactionalEventListener` **mặc định bỏ qua event**, không tự chọn một transaction mới để xử lý.

### 5.1. TransactionSynchronizationManager không phải công tắc để giả lập transaction

Có thể dùng `TransactionSynchronizationManager.isActualTransactionActive()` cho log chẩn đoán imperative transaction. Nhưng không nên chỉnh sửa ThreadLocal của `TransactionSynchronizationManager` bằng tay để “lừa” listener. Cần transaction manager thật nếu muốn kiểm chứng phase commit/rollback.

### 5.2. Event payload là fact, không phải thực thể JPA sống

Ưu tiên record bất biến, ví dụ:

~~~java
public record OrderPlaced(
    long orderId,
    long totalCents
) { }
~~~

Không gửi nguyên entity JPA mutable/lazy proxy qua event rồi kỳ vọng sau commit mọi lazy relation còn truy cập được. Với listener sau commit, chỉ giữ ID và dữ liệu cần thiết; nếu cần đọc state, hãy chủ động query theo ranh giới transaction phù hợp.

## 6. Thực hành Java 17+ với Spring JDBC và H2

Ví dụ **độc lập, có thể biên dịch/chạy** này sử dụng:

- Java 17+.
- Spring Framework 6.2.8: `spring-context`, `spring-tx` và `spring-jdbc`.
- H2 database 2.3.232 (in-memory) để quan sát commit/rollback.
- Maven để compile và chạy `main`.
- `@EnableTransactionManagement` và `DataSourceTransactionManager` để kích hoạt Spring transaction proxy.
- `@EventListener` (ngay khi publish), `@TransactionalEventListener(AFTER_COMMIT)` và `@TransactionalEventListener(AFTER_ROLLBACK)`.
- Lần publish ngoài transaction để kiểm tra hành vi mặc định của transactional listener.

Không cần Spring Boot, REST server hoặc message broker.

### 6.1. Cấu trúc thư mục

~~~text
transactional-event-listener-demo/
├── pom.xml
└── src
    └── main
        └── java
            └── TransactionalEventDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>transactional-event-listener-demo</artifactId>
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
            <artifactId>spring-tx</artifactId>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>TransactionalEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. src/main/java/TransactionalEventDemo.java

~~~java
import java.util.concurrent.atomic.AtomicInteger;
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
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public final class TransactionalEventDemo {

    // Domain fact: payload bất biến và nhỏ.
    public record OrderPlaced(long orderId, long totalCents) { }

    // Không final: Spring tạo proxy dựa trên class để intercept
    // @Transactional khi lấy bean từ ApplicationContext.
    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher
        ) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void place(
                long orderId,
                long totalCents,
                boolean failAfterPublish
        ) {
            if (orderId <= 0 || totalCents <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }

            jdbc.update(
                "INSERT INTO orders(id, total_cents) VALUES (?, ?)",
                orderId, totalCents
            );

            publisher.publishEvent(
                new OrderPlaced(orderId, totalCents)
            );

            System.out.println(
                "METHOD_BODY_END order=" + orderId
            );

            if (failAfterPublish) {
                throw new IllegalStateException(
                    "Forced rollback after event publish"
                );
            }
        }
    }

    public static class OrderObservers {
        private final AtomicInteger immediate = new AtomicInteger();
        private final AtomicInteger committed = new AtomicInteger();
        private final AtomicInteger rolledBack = new AtomicInteger();

        // Không đợi transaction kết thúc.
        @EventListener
        public void onImmediate(OrderPlaced event) {
            immediate.incrementAndGet();
            System.out.println(
                "IMMEDIATE order=" + event.orderId()
            );
        }

        // Đợi transaction commit thành công.
        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void onCommit(OrderPlaced event) {
            committed.incrementAndGet();
            System.out.println(
                "AFTER_COMMIT order=" + event.orderId()
            );
        }

        // Chỉ nhận khi transaction gắn với event rollback.
        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK
        )
        public void onRollback(OrderPlaced event) {
            rolledBack.incrementAndGet();
            System.out.println(
                "AFTER_ROLLBACK order=" + event.orderId()
            );
        }

        public int immediateCount() {
            return immediate.get();
        }

        public int committedCount() {
            return committed.get();
        }

        public int rollbackCount() {
            return rolledBack.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds =
                new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                "jdbc:h2:mem:transactional_events;DB_CLOSE_DELAY=-1"
            );
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource
        ) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher
        ) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        OrderObservers orderObservers() {
            return new OrderObservers();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(
                JdbcTemplate.class
            );

            jdbc.execute(
                "CREATE TABLE orders (" +
                "id BIGINT PRIMARY KEY, " +
                "total_cents BIGINT NOT NULL)"
            );

            // QUAN TRỌNG: lấy Spring bean đã được proxy,
            // không new OrderService(...) rồi gọi @Transactional.
            OrderService service = context.getBean(
                OrderService.class
            );

            OrderObservers observers = context.getBean(
                OrderObservers.class
            );

            System.out.println("CASE=COMMIT");
            service.place(101L, 8500L, false);
            System.out.println(
                "ROWS_AFTER_COMMIT=" +
                jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders",
                    Integer.class
                )
            );

            System.out.println("CASE=ROLLBACK");
            try {
                service.place(102L, 9900L, true);
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT_ROLLBACK");
            }

            System.out.println(
                "ROWS_AFTER_ROLLBACK=" +
                jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders",
                    Integer.class
                )
            );

            // Không gắn với transaction nào.
            System.out.println("CASE=NO_TX");
            context.publishEvent(new OrderPlaced(103L, 7000L));

            System.out.println(
                "COUNTS immediate=" + observers.immediateCount()
                + " commit=" + observers.committedCount()
                + " rollback=" + observers.rollbackCount()
            );
        }
    }
}
~~~

### 6.4. Lệnh chạy

Đứng trong thư mục `transactional-event-listener-demo` với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Đầu ra kỳ vọng **của những dòng System.out.println do chương trình in** (không tính log framework/Maven), khi chạy bình thường:

~~~text
CASE=COMMIT
IMMEDIATE order=101
METHOD_BODY_END order=101
AFTER_COMMIT order=101
ROWS_AFTER_COMMIT=1
CASE=ROLLBACK
IMMEDIATE order=102
METHOD_BODY_END order=102
AFTER_ROLLBACK order=102
CAUGHT_ROLLBACK
ROWS_AFTER_ROLLBACK=1
CASE=NO_TX
IMMEDIATE order=103
COUNTS immediate=3 commit=1 rollback=1
~~~

### 6.5. Giải thích output

**CASE=COMMIT:** `OrderService.place(101, ..., false)` ghi row rồi publish event. `@EventListener` thông thường in `IMMEDIATE` khi đang ở trong method. Service in `METHOD_BODY_END` và trả về cho transaction interceptor. Transaction manager commit, rồi transactional listener `AFTER_COMMIT` mới in dòng tương ứng. Query ngoài transaction cho thấy `ROWS_AFTER_COMMIT=1`.

**CASE=ROLLBACK:** Service ghi thử order 102 và publish event 102. Listener immediate **đã chạy**. Sau đó service ném `IllegalStateException`, transaction interceptor đánh dấu rollback/rollback, nên callback `AFTER_COMMIT` không được gọi; thay vào đó `AFTER_ROLLBACK` in dòng event 102. Exception truyền về caller và được bắt, in `CAUGHT_ROLLBACK`. Query DB vẫn thấy **chỉ một row**, chứng minh order 102 không commit.

**CASE=NO_TX:** `context.publishEvent(...)` được gọi trực tiếp ngoài bất kỳ transaction đang hoạt động nào; listener `@EventListener` thường vẫn nhận event. Hai listener transactional có `fallbackExecution=false` mặc định nên **không chạy**. Tổng cộng: immediate nhận 3 event (commit, rollback, no transaction), after-commit nhận 1, after-rollback nhận 1.

**Giới hạn của ví dụ:** H2 in-memory không sống qua process restart; các counter cũng nằm trong RAM. Demo kiểm chứng **phase và rollback**, không kiểm chứng durable delivery, broker, retry hay tính bền vững sau crash. Mã và output được thiết kế để chạy được nhưng chưa phải kết quả build/test thực tế trong tài liệu này.

## 7. fallbackExecution: event ngoài transaction được xử lý thế nào?

Mặc định:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void on(OrderPlaced event) { }
~~~

Không có transaction đang hoạt động tại thời điểm publish thì handler không được gọi. Cơ chế này có chủ đích: Spring không thể thực hiện lời hứa “sau commit” khi không có transaction để commit.

Khi thật sự chấp nhận xử lý cả trường hợp không có transaction, có thể chọn:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void on(OrderPlaced event) {
    // Sẽ xử lý khi được publish trong một transaction
    // đã commit, hoặc theo fallback khi không có transaction.
}
~~~

Đây là snippet cần class/import phù hợp, **không nằm trong demo runnable**.

**Cảnh báo:** `fallbackExecution=true` **không tạo transaction**, cũng không biến một event ngoài transaction thành event “đã commit”. Nó chỉ cho phép handler chạy trong tình huống không có transaction để đồng bộ phase. Điều này có thể hợp lý cho cache invalidation hoặc metric nhưng nguy hiểm nếu logic chỉ được phép phản ứng sau khi business state có transaction commit.

### 7.1. Bài toán không có transaction nhưng người viết tưởng có

Một số nguyên nhân thường gặp:

- Service object được tạo bằng `new` thay vì lấy từ Spring context.
- Method `@Transactional` được gọi bởi `this.method()` bên trong chính bean, bỏ qua Spring proxy.
- Method không được proxy/intercept vì kiến trúc/proxy configuration.
- Publisher được gọi trước hoặc sau ranh giới transaction mong đợi.
- Đường code async chạy trong một thread khác, không mang imperative transaction của publisher.
- Gọi publisher trong test không khởi tạo transaction manager hoặc không mở transaction.
- Có nhiều `PlatformTransactionManager` nhưng annotation/phạm vi chọn nhầm manager.

**Không nên sửa các lỗi trên bằng cách bật fallback một cách mù quáng.** Hãy đo đúng transaction boundary, rồi mới quyết định phase hay fallback policy.

### 7.2. Chẩn đoán bằng TransactionSynchronizationManager

Trong imperative application, có thể log tại producer:

~~~java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
System.out.println("TX_ACTIVE=" + active);
~~~

Đây là snippet; cần import `org.springframework.transaction.support.TransactionSynchronizationManager`. `isActualTransactionActive()` cho biết có transaction thực sự active trong **thread hiện tại**; không thay thế việc kiểm tra transaction manager, rollback rule, event type hay listener registration. Với reactive transactions, thread-local không đại diện cho Reactor context.

## 8. Lưu ý quan trọng: ghi database tại AFTER_COMMIT cần transaction mới

Đây là lỗi rất dễ gặp dù mọi code có vẻ hợp lý:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void on(OrderPlaced event) {
    auditRepository.save(new AuditRecord(event.orderId()));
}
~~~

Đoạn trên minh họa. Vấn đề là: theo **Javadoc Spring**, ở các phase `AFTER_COMMIT`, `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION`, **database transaction đã hoàn tất nhưng transaction resources có thể vẫn được gắn với thread và còn truy cập được** trong giai đoạn cleanup. Một DB operation tưởng như tham gia transaction cũ có thể **không có commit mới tiếp theo**.

Không nên suy từ việc `save(...)` trả về mà khẳng định row audit đã commit.

### 8.1. Cách đúng khi thật sự cần ghi DB sau commit

Đưa việc ghi vào một Spring service **khác** với một method `@Transactional(propagation = Propagation.REQUIRES_NEW)`:

~~~java
@Service
public class CommittedAuditService {
    private final JdbcTemplate jdbc;

    public CommittedAuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeCommittedAudit(long orderId) {
        jdbc.update(
            "INSERT INTO committed_audit(order_id) VALUES (?)",
            orderId
        );
    }
}
~~~

Và listener:

~~~java
@Component
public class CommitAuditListener {
    private final CommittedAuditService audit;

    public CommitAuditListener(CommittedAuditService audit) {
        this.audit = audit;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderPlaced event) {
        audit.writeCommittedAudit(event.orderId());
    }
}
~~~

Hai đoạn là **mã minh họa mở rộng**, cần import `Service`, `Component`, `JdbcTemplate`, `Transactional`, `Propagation`, `TransactionalEventListener` và bảng `committed_audit`. Chúng không thuộc file demo `TransactionalEventDemo.java` ở mục 6.

Lời gọi từ listener vào **Spring bean proxy khác** giúp `REQUIRES_NEW` được intercept thật sự, mở transaction mới độc lập để commit bản ghi audit. **Không dùng `this.writeCommittedAudit(...)` từ cùng một object** rồi mong annotation method được intercept theo proxy mặc định.

**Chi phí:** `REQUIRES_NEW` cần transaction/connection mới, có thể tăng pool pressure. Không dùng nó như thuốc chữa mọi vấn đề. Nếu công việc phải được giao bền vững tới service ngoài, **outbox ghi trong transaction nguồn** thường phù hợp hơn một listener sau commit ghi intent.

### 8.2. Tại sao không dùng REQUIRES_NEW để thay outbox?

Một listener `AFTER_COMMIT` vẫn có thể **không được gọi nếu process chết sau source commit**, dù method đích mở transaction mới. `REQUIRES_NEW` giải quyết việc **commit của DB operation đã được chạy**, không giải quyết cửa sổ mất event giữa source commit và listener invocation.

Outbox đúng phải ghi `OrderPlaced` intent **trong cùng transaction nguồn** với Order, trước commit, không đợi callback sau commit mới insert.

## 9. BEFORE_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION trong thực tế

### 9.1. BEFORE_COMMIT không đảm bảo commit chắc chắn

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.BEFORE_COMMIT
)
public void beforeCommit(OrderPlaced event) {
    // Ví dụ: một bước xử lý cục bộ còn cần transaction nguồn.
}
~~~

Handler được gọi trước khi transaction manager hoàn tất commit, nhưng một rollback vẫn có thể xảy ra sau đó. Không gọi API thanh toán không có cơ chế rollback chỉ vì tên phase nghe có vẻ chắc chắn.

Một exception từ `BEFORE_COMMIT` có thể làm commit thất bại hoặc transaction rollback, tùy transaction manager và error handling. Nếu cần validation trực tiếp quyết định use case, lời gọi service rõ ràng trong transaction thường dễ hiểu hơn một event listener giấu workflow.

### 9.2. AFTER_ROLLBACK chỉ thích hợp với những phản ứng chịu được rollback

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_ROLLBACK
)
public void afterRollback(OrderPlaced event) {
    // Ví dụ: ghi metric thất bại / cleanup bên ngoài có policy.
}
~~~

Khi rollback, row Order vừa insert có thể đã bị hoàn tác. Listener không nên giả định có thể query row đó rồi xử lý như fact đã commit. Event payload có thể vẫn còn trong RAM, nên hãy phân biệt “command được thử” với “OrderPlaced thật sự đã tồn tại bền vững”.

Với nghiệp vụ, có thể chọn tên event khác như `OrderPlacementFailed` hoặc cấu trúc failure signal rõ ràng hơn nếu người nhận cần hiểu rằng transaction không thành công. Listener rollback đang nhìn một **attempted fact** được tạo trong transaction chưa commit, không nên phát nó như successful fact tới hệ thống ngoài.

### 9.3. AFTER_COMPLETION để cleanup chung

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMPLETION
)
public void cleanup(OrderPlaced event) {
    // Cleanup/metrics áp dụng cả commit và rollback.
}
~~~

Không dựa vào method này để kết luận đã commit. Khi cần theo dõi riêng từng outcome, dùng phases chuyên biệt hoặc transaction synchronization API phù hợp.

## 10. @Async và transactional event listener: hiểu hai ranh giới

Có thể kết hợp:

~~~java
@Component
public class AsyncNotificationListener {
    @Async("notificationsExecutor")
    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderPlaced event) {
        // Gửi notification trên executor sau khi commit.
    }
}
~~~

Đây là snippet, chưa có `@EnableAsync`, `notificationsExecutor` và dependency thực; không thuộc demo runnable.

Cần phân biệt **hai việc**:

1. Transactional event infrastructure nhận event trong transaction publisher và gắn callback cho phase tương ứng.
2. Khi phase đến, handler có thể được dispatch qua Spring async proxy/executor, nếu cấu hình đúng.

Do đó, `@Async` **không làm cho transaction nguồn tự chảy sang thread worker**. Spring imperative transaction thường gắn với thread, không tự được chuyển sang executor. Listener nên nhận **event DTO bất biến**, chỉ giữ ID/payload cần thiết, và tự mở transaction mới khi muốn ghi DB.

### 10.1. Những rủi ro của async

- Queue trong RAM có thể mất khi process chết.
- Executor có thể đầy và từ chối task (`TaskRejectedException`).
- Lỗi trong `@Async void` thường cần `AsyncUncaughtExceptionHandler` hoặc instrumentation riêng; không tự truyền về request.
- Completion order của nhiều event có thể bị đảo.
- Listener async có thể chạy sau khi dependency của request/transaction đã đóng.
- Event listener sai proxy configuration có thể chạy đồng bộ mà developer không nhận ra.
- `AFTER_COMMIT` không biến một background task thành durable delivery.

Khi cần không mất job, không chỉ thêm `@Async`; hãy ghi job/outbox trong transaction nguồn và có worker retry/ack rõ ràng.

### 10.2. Global multicaster async không giống @Async chọn lọc

`SimpleApplicationEventMulticaster.setTaskExecutor(...)` ảnh hưởng cách multicaster phân phát listener nói chung. Spring có `ApplicationListener.supportsAsyncExecution()` để một số listener transaction-bound vẫn được kích hoạt trên publisher thread nhằm đăng ký synchronization đúng ngữ cảnh; đừng tự suy luận rằng mọi listener đều được đưa sang executor theo cách giống nhau.

Vì vậy cấu hình executor ở multicaster là một **thay đổi có phạm vi toàn context**, cần đánh giá transaction, lifecycle và listener không hỗ trợ async. Dùng `@Async` có chọn lọc hoặc một job system riêng có thể dễ kiểm soát hơn.

## 11. Event sau commit không đồng nghĩa durable delivery

Timeline lỗi:

~~~text
T1 BEGIN
  INSERT order
  publishEvent(OrderPlaced)       [listener AFTER_COMMIT đã đăng ký]
T1 COMMIT                         [order bền vững trong DB]
  |
  +-- process crash
  |
  X  @TransactionalEventListener chưa gửi notification
~~~

Ứng dụng có thể không bao giờ biết mình đã bỏ lỡ công việc. `AFTER_COMMIT` đảm bảo **thời điểm callback khi process còn sống và callback thực thi**, không cam kết retry sau restart.

### 11.1. Khi nào AFTER_COMMIT là đủ?

Thường phù hợp với side effects **best-effort hoặc tự phục hồi được**:

- Invalidate cache khi cache có TTL/refresh.
- Ghi metric/tracing bổ trợ không phải source of truth.
- Trigger cập nhật projection có thể rebuild từ database.
- Gửi notification nếu nghiệp vụ chấp nhận khả năng mất/được bù bằng job reconciliation.

Cần đặt kỳ vọng đúng; “email gửi sau commit” không đồng nghĩa “email chắc chắn được gửi”.

### 11.2. Khi nào cần transactional outbox?

Nếu event `OrderPlaced` cần chắc chắn được giao sang billing hoặc fulfillment, dùng một transaction nguồn:

~~~text
OrderService @Transactional:
    INSERT orders
    INSERT outbox(eventId, type, payload, status=PENDING)
    COMMIT
         |
         v
Outbox relay process
    |
    +-- poll/claim hoặc CDC
    +-- broker publish + ack
    +-- retry/backoff
         |
         v
Consumer
    +-- deduplicate stable eventId
    +-- process idempotently
~~~

Ghi outbox cùng transaction tạo Order bảo đảm **business state và ý định giao event commit/rollback cùng nhau**. Relay có thể retry khi app restart. Nếu broker đã nhận nhưng relay chết trước khi mark SENT, event có thể được gửi lại, vì thế consumer phải idempotent.

### 11.3. AFTER_COMMIT và outbox có thể cùng tồn tại

Một ứng dụng có thể:

- Ghi `OrderPlaced` outbox cho integration ngoài process.
- Phát `@TransactionalEventListener(AFTER_COMMIT)` cho cache/metrics nội bộ **không bắt buộc giao đủ**.

Không cần thay mọi listener thành broker. Điều quan trọng là phân loại **durability requirement** và **business criticality** của mỗi consumer.

## 12. Testing đúng transaction boundary

Đừng chỉ mock `ApplicationEventPublisher` rồi kết luận listener phase đúng. Mockito verify có thể chứng minh service **gọi publishEvent**, nhưng không thực thi transaction synchronization hoặc listener Spring.

### 12.1. Ma trận kiểm thử bắt buộc

| Trường hợp | Kỳ vọng |
| --- | --- |
| Event publish trong transaction, commit thành công | `AFTER_COMMIT` chạy một lần |
| Event publish trong transaction rồi rollback | `AFTER_COMMIT` không chạy; `AFTER_ROLLBACK` có thể chạy |
| Event publish ngoài transaction, fallback mặc định | Transactional listener không chạy |
| Event publish ngoài transaction, `fallbackExecution=true` | Listener được thực thi theo fallback |
| Exception sau publish trước commit | Không có after-commit success side effect |
| Listener sync thông thường | Có thể chạy trước commit và cả đường rollback |
| `BEFORE_COMMIT` handler lỗi | Kiểm tra commit bị ảnh hưởng theo policy |
| AFTER_COMMIT ghi DB bằng `REQUIRES_NEW` qua bean proxy | Ghi mới được commit độc lập |
| AFTER_COMMIT ghi DB sai transaction | Test phải phát hiện thiếu commit/thay đổi không bền |
| `@Async` AFTER_COMMIT | Đợi outcome của worker có timeout |
| Transaction manager sai hoặc self-invocation | Test phải bộc lộ không có transaction đúng |
| Process crash sau commit trước listener | Chứng minh không có durable retry nếu chỉ dùng event bus |
| Outbox ghi trong source transaction | Commit/rollback atomic giữa business và intent |
| Context chưa đăng ký listener | Không tự replay event cũ |

### 12.2. Test @Transactional mặc định rollback là bẫy

Trong Spring TestContext, một test method có `@Transactional` thường **rollback ở cuối test**. Nếu test mong `AFTER_COMMIT` tự chạy ngay sau `publisher.publishEvent(...)`, assertion có thể fail vì transaction chưa commit và sau đó lại rollback.

Ví dụ test sai ý định:

~~~java
// Minh họa một test dễ hiểu nhầm.
@Test
@Transactional
void afterCommitShouldRun() {
    publisher.publishEvent(new OrderPlaced(1L, 100L));
    assertEquals(1, listener.committedCount());
}
~~~

Ở vị trí assertion, transaction của test thường **vẫn đang active**; listener after-commit chưa chạy. Hãy thay đổi cách test để thực hiện **commit thật** trước khi assert.

### 12.3. Cách kiểm thử có commit rõ ràng

Một số lựa chọn:

- Gọi một Spring service `@Transactional` từ test **không** bọc toàn method trong transaction; khi method proxy trả về, commit đã hoàn tất.
- Sử dụng `TransactionTemplate` để đóng transaction trước assertion.
- Trong Spring TestContext có transaction test-managed, dùng `TestTransaction.flagForCommit()` rồi `TestTransaction.end()` khi điều kiện phù hợp.

Ví dụ dùng `TransactionTemplate` (snippet, cần bean manager/publisher):

~~~java
TransactionTemplate transaction = new TransactionTemplate(txManager);
transaction.executeWithoutResult(status -> {
    repository.save(order);
    publisher.publishEvent(new OrderPlaced(1L, 100L));
});

// Tới đây executeWithoutResult đã kết thúc transaction.
// Kiểm tra state do AFTER_COMMIT listener ghi nhận.
assertEquals(1, listener.committedCount());
~~~

Đây là **snippet minh họa**, không phải một file test hoàn chỉnh và không thuộc Maven demo mục 6. Nó cho thấy mốc commit rõ hơn việc assert trong cùng một method test transactional chưa kết thúc.

### 12.4. @RecordApplicationEvents chỉ chứng minh phần publication

Spring TestContext có `@RecordApplicationEvents` và `ApplicationEvents` để ghi nhận những event được publish trong phạm vi test. Nhưng:

- Một event đã được ghi nhận **không chứng minh** mọi transactional listener chạy thành công.
- Với event publish nhưng transaction rollback, recorder vẫn có thể ghi publication.
- Với listener async, publish/record không chứng minh worker đã hoàn tất.

Khi test transaction phase, phải quan sát **outcome của đúng handler** sau commit/rollback, không chỉ đếm event đã publish.

### 12.5. Test có phản hồi xác định

Dùng in-memory counters/list (như demo) để test phase đồng bộ; với async, dùng `CountDownLatch` hoặc trạng thái kết quả có timeout. Tránh `Thread.sleep(100)` rồi suy đoán worker đã chạy, vì dễ flaky theo tải của CI.

## 13. Các lỗi thường gặp và hướng chẩn đoán

| Dấu hiệu | Nguyên nhân khả dĩ | Bước kiểm tra |
| --- | --- | --- |
| Không thấy AFTER_COMMIT dù producer đã gọi publish | Không có transaction active | Log `TransactionSynchronizationManager.isActualTransactionActive()` |
| @EventListener chạy nhưng transactional listener im lặng | Publisher ngoài transaction hoặc rollback | So sánh transaction boundary và phase |
| Không có transaction dù @Transactional | Self-invocation/proxy không intercept | Gọi bean từ context qua proxy |
| AFTER_COMMIT không chạy trong test | Test transaction chưa commit/đang tự rollback | Dùng TransactionTemplate/TestTransaction |
| Dữ liệu ghi từ AFTER_COMMIT không tồn tại | Không có transaction mới khi resource cũ còn bound | Dùng service khác có `REQUIRES_NEW` |
| Event rollback không được nhận | Event được publish ngoài transaction hoặc thiếu listener phase | Kiểm tra phase và registration |
| Async listener không có kết quả ngay | Task chưa chạy xong hoặc bị reject | Đo queue/rejection và đợi outcome |
| Event type sai | Listener argument/condition không khớp | Log runtime event type, test wiring |
| Listener đã đăng ký quá muộn | Event phát lúc context khởi động | Dời publish hoặc đăng ký sớm |
| Dùng reactive transaction nhưng listener không chạy | Không chuyển được Reactor transaction context | Dùng `TransactionalEventPublisher` phù hợp |
| Sau commit, network lỗi gây mất notification | Không có durable intent/retry | Transactional outbox/worker |
| Listener chạy hai lần hoặc side effect trùng | Duplicate publication/retry hoặc nhiều listener/context | Event ID, idempotency, kiểm tra bean registrations |
| Handler BEFORE_COMMIT ném exception | Có thể abort commit | Kiểm tra business rules và error propagation |
| Có nhiều transaction managers | Manager sai được chọn | Dùng qualifier/transactionManager name rõ |
| Cache update xảy ra trước commit | Dùng ordinary @EventListener | Dời sang AFTER_COMMIT nếu cần |

### 13.1. Debug transaction theo trật tự

1. Xác nhận producer gọi `publishEvent(...)` thật.
2. Xác nhận method `@Transactional` được gọi qua Spring-managed proxy.
3. Kiểm tra `PlatformTransactionManager` và DataSource/entity manager đúng.
4. Ghi nhận `TX_ACTIVE` tại thời điểm publish.
5. Xác nhận event type/parameter/condition và listener bean registration.
6. Xác định transaction thực tế commit, rollback hay mark rollback-only.
7. Kiểm tra phase listener mong đợi và `fallbackExecution`.
8. Nếu async, kiểm tra executor, rejection, error handler và completion.
9. Nếu side effect là database write, xác minh transaction mới/affected row.
10. Nếu yêu cầu delivery qua crash, chuyển sang outbox thay vì sửa annotation đơn thuần.

### 13.2. @TransactionalEventListener không sửa được transaction sai

Nếu service đang publish sự kiện trước khi business invariant được xác nhận, hoặc gọi một transaction không chính xác, việc đổi listener từ `@EventListener` sang `AFTER_COMMIT` không tự sửa validation, optimistic locking, transaction ownership hoặc duplicate commands.

Trước hết phải biết event **đại diện cho fact nào** và **fact đó đã được commit trong transaction nào**.

## 14. Reactive transactions (Spring 6.1+) khác thread-bound transactions

Từ Spring Framework 6.1, transactional event listeners hỗ trợ cả:

- Transaction imperative do `PlatformTransactionManager` quản lý, thường ràng buộc bằng ThreadLocal.
- Transaction reactive do `ReactiveTransactionManager` quản lý, với context nằm trong Reactor context, không phải ThreadLocal như imperative.

Với reactive transaction, đơn giản gọi một imperative publisher và trông đợi listener nhìn thấy transaction bằng ThreadLocal có thể sai. Spring có `org.springframework.transaction.reactive.TransactionalEventPublisher` để truyền transaction context thích hợp vào event source, giúp cơ chế transactional listener có ngữ cảnh cần thiết.

Đây là **chủ đề mở rộng**, không nằm trong runnable demo sử dụng Spring JDBC imperative. Không copy đoạn `@TransactionalEventListener` trong demo JDBC sang WebFlux/R2DBC rồi mặc định hoạt động hệt như nhau; cần theo hướng dẫn reference phù hợp với reactive APIs và kiểm thử với `ReactiveTransactionManager` thật.

## 15. Bảo mật, dữ liệu và độ tin cậy

### 15.1. Không lạm dụng payload mutable

Một listener chạy sau commit có thể giữ event object lâu hơn method tạo event. Nếu payload tham chiếu entity hoặc request mutable, nội dung có thể bị thay đổi trước lúc handler xử lý (đặc biệt khi async). Dùng record/value object bất biến với `eventId`, `aggregateId`, `aggregateVersion` và dữ liệu tối thiểu.

### 15.2. Không log thông tin nhạy cảm

Tránh publish/log nguyên `Authentication`, token, session cookie, full customer profile hoặc JPA entity có graph lớn. `record.toString()` có thể in toàn bộ component. Event ID/correlation ID nên có quyền truy cập phù hợp, tránh đặt chúng làm metric labels có cardinality cao.

### 15.3. Idempotency vẫn quan trọng

Ngay cả với AFTER_COMMIT, event có thể được publish lặp do command retry hoặc có nhiều listener/context. Khi consumer thực thi side effect ngoài, dùng idempotency key nếu API hỗ trợ và kiểm tra duplicate; nếu có durable queue/broker thì duplicate delivery là tình huống phải thiết kế từ đầu.

### 15.4. Monitoring theo phase và kết quả

Có thể tự định nghĩa các metric:

~~~text
app_event_published_total{type="OrderPlaced"}
app_event_after_commit_started_total{listener="SearchListener"}
app_event_after_commit_failed_total{listener="SearchListener"}
app_event_after_rollback_total{listener="CleanupListener"}
app_event_async_rejected_total{pool="notification"}
app_outbox_oldest_pending_age_seconds
~~~

Đây là **metric gợi ý do ứng dụng tự instrument**, không phải tên metric mặc định có sẵn của Spring. Phân biệt event published với handler started/completed và side effect đã được ghi bền vững.

## 16. Các sai lầm phổ biến

1. **Dùng @EventListener rồi tưởng chỉ chạy sau commit:** listener thường có thể chạy ngay.
2. **Quên rằng AFTER_COMMIT là phase mặc định:** annotation không có phase vẫn đợi commit.
3. **Bật fallbackExecution=true để chữa mọi lỗi:** có thể làm event ngoài transaction bị xử lý như fact đã commit.
4. **Self-invocation gọi @Transactional:** mặc định bỏ qua proxy nên không có transaction mới như mong đợi.
5. **Tự new OrderService và mong @Transactional hoạt động:** cần Spring proxy/interception.
6. **Chỉ mock ApplicationEventPublisher để test phase:** mock không dispatch transactional synchronization.
7. **Assert ngay trong @Transactional test:** transaction chưa commit hoặc test rollback mặc định.
8. **Ghi DB trong AFTER_COMMIT mà không có REQUIRES_NEW:** resource cũ còn bound, update có thể không được commit.
9. **Gọi @Transactional(REQUIRES_NEW) qua this:** self-invocation bỏ qua proxy.
10. **Dùng AFTER_COMMIT như outbox:** process crash vẫn có thể mất event.
11. **Dùng @Async và tưởng đã giao job bền vững:** queue RAM không hồi phục sau crash.
12. **Không kiểm tra executor rejection và lỗi @Async void:** side effect thất bại âm thầm.
13. **Tin @Order đảm bảo async completion order:** thứ tự dispatch khác thứ tự hoàn tất.
14. **Publish ngoài transaction rồi thắc mắc listener không chạy:** đó là mặc định đúng.
15. **Dùng AFTER_COMPLETION như tín hiệu thành công:** chạy cho cả commit và rollback.
16. **Đưa full JPA entity vào event:** có thể lỗi lazy loading hoặc lộ dữ liệu.
17. **Dùng rollback listener như bằng chứng một domain fact đã tồn tại:** transaction có thể đã hoàn tác.
18. **Đặt annotation đúng nhưng sai event type/condition:** listener không được chọn.
19. **Phát event trong constructor/@PostConstruct quá sớm:** listener infrastructure có thể chưa đăng ký.
20. **Trộn transaction managers không cùng resource:** phase không bảo vệ được business write mong muốn.
21. **Không phân biệt reactive và imperative context:** transaction binding khác nhau.
22. **Không định nghĩa retry/idempotency cho side effect quan trọng:** failure/retry có thể gây duplicate.
23. **Coi lỗi sau commit có thể rollback business đã commit:** phase AFTER_COMMIT không quay ngược thời gian.
24. **Không kiểm tra transaction commit thật trong integration test:** nội dung test có thể xanh mà không xác nhận được ngữ nghĩa phase.
25. **Không cân nhắc shutdown/restart:** listener chạy trong process có thể bị mất khi deployment đóng.

## 17. Checklist trước khi đưa listener vào production

- [ ] Event đại diện đúng **fact** nghiệp vụ, được publish sau validation?
- [ ] Transaction nguồn do Spring quản lý và đúng `PlatformTransactionManager`?
- [ ] Producer được gọi qua Spring bean proxy/transaction context phù hợp?
- [ ] Listener có đúng event class/condition và được đăng ký trước thời điểm publish?
- [ ] Đã chọn phase tường minh theo mục tiêu: before, after commit, rollback, completion?
- [ ] Đã test commit và rollback với database/transaction manager thật?
- [ ] Đã test publish ngoài transaction và chính sách `fallbackExecution`?
- [ ] Nếu AFTER_COMMIT có DB write, đã dùng transaction mới được proxy intercept?
- [ ] Nếu listener gọi external API, có timeout, retry/idempotency, error monitoring?
- [ ] Nếu @Async, executor có bounded queue, rejection policy và shutdown handling?
- [ ] Nếu phải giao đủ job qua crash, có outbox/durable job store?
- [ ] Event DTO bất biến, data minimization, version/schema và correlation phù hợp?
- [ ] Có metrics published/started/succeeded/failed và end-to-end lag?
- [ ] Các test `@Transactional` không vô ý rollback trước khi assert after-commit?
- [ ] Có kiểm thử transaction manager/configuration khi nâng Spring/library version?

## 18. Bài tập thực hành

1. Chạy demo rồi đổi `failAfterPublish` của order 102 từ `true` sang `false`. Những dòng `AFTER_COMMIT`, `AFTER_ROLLBACK` và `ROWS_AFTER_ROLLBACK` thay đổi thế nào?
2. Xóa `@EnableTransactionManagement` và quan sát điều gì xảy ra với timing của listeners. Giải thích vì sao việc thiếu transaction khiến AFTER_COMMIT mặc định bỏ qua event.
3. Đổi `onCommit` sang `@TransactionalEventListener` không có `phase`; kết quả có khác không?
4. Bật `fallbackExecution=true` cho `onCommit`, sau đó publish event 103 ngoài transaction. Counter commit thay đổi thế nào? Điều đó có đồng nghĩa event 103 được commit trong DB không?
5. Thay `@EventListener` của `onImmediate` thành `@TransactionalEventListener(AFTER_COMMIT)`. Tác dụng của event 102 rollback sẽ khác thế nào?
6. Thêm một listener `BEFORE_COMMIT` ghi log; kiểm tra mốc log so với `METHOD_BODY_END` và `AFTER_COMMIT`.
7. Đổi một listener thành `AFTER_COMPLETION` rồi kiểm tra nó chạy ở cả hai case commit/rollback.
8. Thêm bảng audit với một Spring service `REQUIRES_NEW` riêng; chứng minh row audit được commit sau source commit.
9. Đặt method `@Transactional` vào cùng bean rồi gọi bằng `this.place(...)`. Dùng `TransactionSynchronizationManager` giải thích điều khác với gọi qua proxy.
10. Dùng `TransactionTemplate` trong một JUnit integration test; assert sau khi execute callback kết thúc.
11. Thử `@Async` và dùng `CountDownLatch` chờ listener hoàn tất thay vì `Thread.sleep`.
12. Với yêu cầu giao `OrderPlaced` tới billing dù app crash, hãy thiết kế schema outbox và relay; giải thích vì sao chỉ AFTER_COMMIT không đủ.

**Định hướng đáp án:** (1) order 102 commit, listener commit chạy thay rollback, DB có hai row; (2) mất Spring transaction proxy, publisher không có transaction active; (3) không vì default AFTER_COMMIT; (4) listener có thể xử lý theo fallback nhưng không có DB commit cho event 103; (5) không còn in immediate ở đường rollback; (6) chạy trước database commit; (7) hai outcome; (8) gọi qua Spring service proxy khác; (9) self-invocation bỏ qua proxy; (10) assert sau commit thật; (11) chờ outcome có timeout; (12) ghi Order + outbox trong cùng transaction, relay retry, consumer idempotent.

## 19. Tổng kết

**Tạo transactional event listener** không chỉ là thêm annotation. Cần hiểu ranh giới transaction thực tế và kiểm chứng kết quả bằng một transaction manager thật.

- `@EventListener` thường chạy ngay khi dispatch, có thể trước commit.
- `@TransactionalEventListener` cho phép gắn handler với một `TransactionPhase`.
- Phase mặc định là `AFTER_COMMIT`; `AFTER_ROLLBACK` chỉ chạy khi rollback; `AFTER_COMPLETION` chạy với cả hai kết quả.
- Khi publish ngoài transaction, transactional listener mặc định không xử lý; `fallbackExecution=true` thay đổi contract đó nhưng không tạo transaction.
- Phải kích hoạt `@Transactional` qua Spring proxy và đúng manager/resource.
- Ở các phase after-completion, transaction resources có thể còn bound nhưng không còn commit; DB write mới cần transaction riêng như `REQUIRES_NEW` qua một Spring bean được proxy.
- `@Async` không chuyển imperative transaction của publisher sang worker, không bảo đảm durability.
- `AFTER_COMMIT` đảm bảo **thời điểm**, không phải **delivery sau crash**; với event bắt buộc, dùng transactional outbox và idempotent consumer.
- Integration test phải kiểm tra commit/rollback thật, không chỉ Mockito verify hoặc `@RecordApplicationEvents`.

Khi hiểu đúng phase, proxy, transaction boundary và failure window, người học có thể triển khai listener sau commit có ngữ nghĩa rõ ràng, kiểm thử được và không đưa ra cam kết vượt quá khả năng của Spring Application Events.

## Tài liệu tham khảo

- Spring Framework 6.2 — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2.8 Javadoc — *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework 6.2.8 Javadoc — *TransactionPhase*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Spring Framework — *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — *TransactionSynchronization / afterCompletion*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — *Application Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — *Reactive TransactionalEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html
- Spring Framework — *Test-managed Transactions*: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
