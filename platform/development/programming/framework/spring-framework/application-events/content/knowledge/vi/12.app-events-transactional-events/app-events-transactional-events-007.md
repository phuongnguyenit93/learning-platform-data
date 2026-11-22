# Event không có transaction trong Spring Framework

Spring application event có thể được publish khi một transaction đang hoạt động hoặc khi không có transaction nào. Sự khác biệt này đặc biệt quan trọng với **@TransactionalEventListener**.

Khi event được publish ngoài transaction, listener thông thường dùng **@EventListener** vẫn được gọi theo cơ chế dispatch của ApplicationContext. Ngược lại, **@TransactionalEventListener** mặc định không chạy vì không có transaction synchronization để đăng ký callback. Thuộc tính **fallbackExecution=true** cho phép listener xử lý event ngay tại thời điểm publish khi không tìm thấy transaction phù hợp.

Điểm cốt lõi: **publishEvent(...) không tự mở transaction**. Nếu nghiệp vụ cần listener chạy sau commit, publisher phải phát event trong một transaction đang hoạt động. Nếu xử lý ngay cả khi không có transaction là hợp lệ, mới bật fallbackExecution.

## 1. Điều gì xảy ra khi publish event ngoài transaction?

Giả sử một service phát OrderSubmittedEvent:

```java
publisher.publishEvent(new OrderSubmittedEvent("ORD-1001"));
```

Nếu lời gọi diễn ra ngoài transaction, Spring vẫn đưa event qua ApplicationEventMulticaster. Các listener thông thường phù hợp với event vẫn được gọi.

Với transactional listener, Spring cần một transaction synchronization đang hoạt động để đăng ký callback ở phase đã chọn. Nếu không có synchronization:

- **fallbackExecution=false:** listener bị bỏ qua. Đây là giá trị mặc định.
- **fallbackExecution=true:** listener được gọi ngay trong luồng xử lý event hiện tại.

Event không bị xóa khỏi ApplicationContext. Chỉ transactional listener không có fallback mới không thực hiện xử lý trong lần publish đó.

## 2. So sánh @EventListener và @TransactionalEventListener

Hai annotation đều đăng ký method làm event listener, nhưng khác nhau về thời điểm gọi.

| Đặc điểm | @EventListener | @TransactionalEventListener |
|---|---|---|
| Có transaction hay không | Không yêu cầu transaction | Mặc định cần transaction synchronization |
| Khi publish ngoài transaction | Được gọi ngay | Bị bỏ qua nếu fallbackExecution=false |
| Khi publish ngoài transaction với fallback | Không cần fallback | Chạy ngay nếu fallbackExecution=true |
| Khi publish trong transaction | Thường chạy ngay trong luồng publish | Chờ phase đã chọn |
| Phase commit/rollback | Không có | BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, AFTER_COMPLETION |
| Tự tạo transaction | Không | Không |
| Lưu event bền vững | Không | Không |

Listener thông thường:

```java
@EventListener
public void onOrderSubmitted(OrderSubmittedEvent event) {
    System.out.println("Nhận event: " + event.orderId());
}
```

Listener này được gọi dù publisher có transaction hay không. Nếu publish bên trong transaction, nó thường chạy trước khi transaction commit. Vì vậy, side effect bên ngoài database có thể xảy ra dù transaction sau đó rollback.

Transactional listener:

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void afterCommit(OrderSubmittedEvent event) {
    System.out.println("Đơn đã commit: " + event.orderId());
}
```

Listener này chỉ chạy sau commit nếu event được publish trong transaction synchronization đang hoạt động. Nếu không có transaction, listener bị bỏ qua theo mặc định.

## 3. fallbackExecution mặc định là false

Thuộc tính **fallbackExecution** xác định cách transactional listener xử lý event khi không có transaction phù hợp.

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = false
)
public void afterCommit(OrderSubmittedEvent event) {
    // Chỉ chạy khi có transaction synchronization.
}
```

Đây là hành vi mặc định khi không khai báo fallbackExecution.

Giá trị false phù hợp khi listener chỉ có ý nghĩa nếu transaction nguồn thực sự tồn tại. Ví dụ, gửi email xác nhận đơn hàng chỉ sau khi dữ liệu đơn hàng được commit. Nếu publisher quên mở transaction, bỏ qua listener giúp tránh gửi thông báo về một thay đổi chưa được commit.

Khi event được publish ngoài transaction, Spring không tự tạo transaction để chạy listener và cũng không tự chuyển event sang một hàng đợi khác. Listener không được gọi trong lần publish đó.

### Khi nào bật fallbackExecution=true?

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void handleOrder(OrderSubmittedEvent event) {
    // Xử lý sau commit nếu có transaction;
    // xử lý ngay nếu không có transaction.
}
```

Khi có transaction synchronization, listener vẫn được đăng ký ở phase AFTER_COMMIT. Khi không có transaction, fallback cho phép listener chạy ngay.

**fallbackExecution=true không tạo transaction và không làm cho event trở thành AFTER_COMMIT khi không có transaction.** Không có commit nào để chờ, nên fallback thực hiện listener ngay trong đường xử lý hiện tại.

Bật fallback chỉ khi cùng một hành động có ý nghĩa ở cả hai trường hợp: publish trong transaction và publish ngoài transaction. Nếu listener phải bảo đảm dữ liệu đã commit, hãy giữ fallbackExecution=false và sửa nơi publish để có transaction thực sự.

## 4. Transaction synchronization là điều kiện quan trọng

Transactional event listener đăng ký callback với transaction synchronization. Trong ứng dụng Spring thông thường, synchronization được kích hoạt khi transaction manager bắt đầu transaction và quản lý vòng đời của nó.

Các cách phổ biến để có transaction:

- Gọi một phương thức được Spring quản lý transaction bằng **@Transactional**.
- Dùng **TransactionTemplate** để bao quanh đoạn code cần transaction.
- Dùng transaction manager tương ứng với JDBC, JPA hoặc công nghệ lưu trữ của ứng dụng.

Ví dụ với annotation:

```java
@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;
    private final OrderRepository repository;

    public OrderService(
            ApplicationEventPublisher publisher,
            OrderRepository repository
    ) {
        this.publisher = publisher;
        this.repository = repository;
    }

    @Transactional
    public void submit(Order order) {
        repository.save(order);
        publisher.publishEvent(
                new OrderSubmittedEvent(order.getId())
        );
    }
}
```

Event được publish bên trong transaction của phương thức. Listener AFTER_COMMIT được gọi sau khi transaction commit thành công. Nếu transaction rollback, listener AFTER_COMMIT không được gọi.

Để @Transactional có hiệu lực, ứng dụng cần cấu hình transaction management và transaction manager phù hợp. Trong Spring Framework thuần, có thể dùng @EnableTransactionManagement cùng một PlatformTransactionManager. Trong Spring Boot, cấu hình thường được auto-configure khi có dependency và datasource tương ứng.

### Những trường hợp tưởng có transaction nhưng thực tế không có

- Phương thức gọi publishEvent không có @Transactional và không nằm trong transaction do bên gọi mở.
- Phương thức có @Transactional nhưng được gọi bằng self-invocation trong cùng object, khiến proxy transaction không được kích hoạt ở chế độ proxy mặc định.
- Ứng dụng chưa cấu hình transaction manager phù hợp.
- Transaction đã bị suspend hoặc kết thúc trước khi publish event, chẳng hạn qua propagation NOT_SUPPORTED.
- Event được publish trong callback hoặc thread khác không mang transaction synchronization của thread ban đầu.

Không chỉ nhìn annotation để kết luận có transaction. Hãy xác định lời gọi thực tế có đi qua transaction boundary và event được publish khi synchronization còn hoạt động hay không.

## 5. Ví dụ hoàn chỉnh: cùng event ngoài và trong transaction

Ví dụ dùng Java 17 và Spring Framework 6.2. Chương trình publish cùng loại POJO event theo hai cách:

1. Ngoài transaction: listener thường chạy, transactional listener mặc định bị bỏ qua, listener có fallback chạy ngay.
2. Trong TransactionTemplate: listener thường chạy khi publish, còn hai transactional listener được gọi sau khi commit.

Ví dụ dùng một transaction manager nhỏ chỉ mô phỏng transaction synchronization, không kết nối database. Nó giúp quan sát callback mà không cần cài database. Trong ứng dụng thực tế, hãy dùng transaction manager của hệ thống.

### 5.1. Cấu trúc dự án

```text
spring-event-without-transaction/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── example/
                    └── notransaction/
                        └── Application.java
```

### 5.2. Dependency Maven

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>spring-event-without-transaction</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.6</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.example.notransaction.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. Mã nguồn

Tạo file src/main/java/dev/example/notransaction/Application.java:

```java
package dev.example.notransaction;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.EnableTransactionManagement;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

public class Application {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderPublisher publisher = context.getBean(OrderPublisher.class);

            System.out.println("=== OUTSIDE TRANSACTION ===");
            publisher.publishOutsideTransaction("ORD-1001");

            System.out.println("=== INSIDE TRANSACTION ===");
            publisher.publishInsideTransaction("ORD-1002");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        public PlatformTransactionManager transactionManager() {
            return new DemoTransactionManager();
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager transactionManager
        ) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        public OrderPublisher orderPublisher(
                ApplicationEventPublisher publisher,
                TransactionTemplate transactionTemplate
        ) {
            return new OrderPublisher(publisher, transactionTemplate);
        }

        @Bean
        public EveryPublicationListener everyPublicationListener() {
            return new EveryPublicationListener();
        }

        @Bean
        public AfterCommitListener afterCommitListener() {
            return new AfterCommitListener();
        }

        @Bean
        public FallbackListener fallbackListener() {
            return new FallbackListener();
        }
    }

    public record OrderSubmittedEvent(String orderId) {}

    public static class OrderPublisher {
        private final ApplicationEventPublisher publisher;
        private final TransactionTemplate transactionTemplate;

        public OrderPublisher(
                ApplicationEventPublisher publisher,
                TransactionTemplate transactionTemplate
        ) {
            this.publisher = publisher;
            this.transactionTemplate = transactionTemplate;
        }

        public void publishOutsideTransaction(String orderId) {
            System.out.println("Publisher: publish " + orderId);
            publisher.publishEvent(new OrderSubmittedEvent(orderId));
            System.out.println("Publisher: publishEvent returned");
        }

        public void publishInsideTransaction(String orderId) {
            transactionTemplate.executeWithoutResult(status -> {
                System.out.println("Publisher: publish " + orderId);
                publisher.publishEvent(new OrderSubmittedEvent(orderId));
                System.out.println(
                        "Publisher: publishEvent returned inside transaction"
                );
            });

            System.out.println("Publisher: transaction completed");
        }
    }

    @Order(1)
    public static class EveryPublicationListener {

        @EventListener
        public void onOrderSubmitted(OrderSubmittedEvent event) {
            System.out.println(
                    "EventListener: " + event.orderId()
            );
        }
    }

    @Order(2)
    public static class AfterCommitListener {

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT
        )
        public void afterCommit(OrderSubmittedEvent event) {
            System.out.println(
                    "After-commit listener: " + event.orderId()
            );
        }
    }

    @Order(3)
    public static class FallbackListener {

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT,
                fallbackExecution = true
        )
        public void withFallback(OrderSubmittedEvent event) {
            System.out.println(
                    "Fallback listener: " + event.orderId()
            );
        }
    }

    // Chỉ kích hoạt transaction synchronization để minh họa callback.
    // Không thực hiện commit/rollback trên database.
    public static class DemoTransactionManager
            extends AbstractPlatformTransactionManager {

        @Override
        protected Object doGetTransaction() {
            return new Object();
        }

        @Override
        protected void doBegin(
                Object transaction,
                TransactionDefinition definition
        ) {
            // Không có database resource trong ví dụ.
        }

        @Override
        protected void doCommit(DefaultTransactionStatus status) {
            // AbstractPlatformTransactionManager gọi afterCommit
            // và afterCompletion sau bước này.
        }

        @Override
        protected void doRollback(DefaultTransactionStatus status) {
            // Minh họa rollback synchronization, không ghi database.
        }
    }
}
```

### 5.4. Chạy chương trình

Tại thư mục chứa pom.xml, chạy:

```bash
mvn -q compile exec:java
```

Stdout mong đợi:

```text
=== OUTSIDE TRANSACTION ===
Publisher: publish ORD-1001
EventListener: ORD-1001
Fallback listener: ORD-1001
Publisher: publishEvent returned
=== INSIDE TRANSACTION ===
Publisher: publish ORD-1002
EventListener: ORD-1002
Publisher: publishEvent returned inside transaction
After-commit listener: ORD-1002
Fallback listener: ORD-1002
Publisher: transaction completed
```

Kết quả cho thấy:

- Với ORD-1001, không có transaction. EventListener chạy ngay. AfterCommitListener bị bỏ qua vì fallbackExecution mặc định là false. FallbackListener chạy ngay trong lần publish.
- Với ORD-1002, event được publish trong TransactionTemplate. EventListener chạy ngay trong transaction. Hai transactional listener được đăng ký và chỉ chạy sau khi transaction commit.
- fallbackExecution=true không làm listener chạy sớm khi transaction đang hoạt động; nó chỉ là đường dự phòng khi không có transaction.

Transaction manager trong ví dụ chỉ mô phỏng transaction synchronization. Nó không ghi dữ liệu và không chứng minh tính nguyên tử của database. Khi áp dụng thực tế, thay bằng DataSourceTransactionManager, JpaTransactionManager hoặc transaction manager phù hợp.

## 6. Nên chọn cách nào khi không có transaction?

### Chỉ cần xử lý event bất kể transaction

Dùng **@EventListener**:

```java
@EventListener
public void recordActivity(UserLoggedInEvent event) {
    activityLog.record(event.userId());
}
```

Đây là lựa chọn rõ ràng khi listener luôn cần chạy và không phụ thuộc vào việc một transaction có commit hay không.

### Chỉ xử lý khi transaction commit

Dùng **@TransactionalEventListener** với fallback mặc định false:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendConfirmation(OrderSubmittedEvent event) {
    notificationService.send(event.orderId());
}
```

Nếu event được publish ngoài transaction, listener bị bỏ qua. Nếu đây là nghiệp vụ bắt buộc, hãy sửa publisher để phát event bên trong transaction thay vì bật fallback để che việc thiếu transaction.

### Xử lý cả trong và ngoài transaction

Dùng fallbackExecution=true khi cùng một hành động hợp lệ ở cả hai trường hợp:

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void updateExternalIndex(OrderSubmittedEvent event) {
    searchIndex.update(event.orderId());
}
```

Khi có transaction, listener chạy sau commit. Khi không có transaction, listener chạy ngay. Hãy kiểm tra xem việc chạy ngay có thể nhìn thấy dữ liệu chưa được lưu hoặc chưa đồng bộ hay không.

### Cần ghi database từ listener ngoài transaction

Nếu listener cần ghi dữ liệu và yêu cầu commit rõ ràng, hãy gọi một service có transaction riêng:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAudit(OrderSubmittedEvent event) {
    auditRepository.save(new AuditRecord(event.orderId()));
}
```

REQUIRES_NEW chỉ có tác dụng khi lời gọi đi qua Spring transaction proxy và có transaction manager phù hợp. Nếu listener được gọi ngoài transaction, Spring mở một transaction mới cho service này.

## 7. Những lỗi thường gặp khiến transactional listener không chạy

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| @TransactionalEventListener không được gọi | Event được publish ngoài transaction synchronization | Publish trong transaction hoặc bật fallback nếu phù hợp |
| @EventListener chạy nhưng transactional listener không chạy | Hai annotation có quy tắc kích hoạt khác nhau | Kiểm tra transaction và fallbackExecution |
| Có @Transactional nhưng vẫn bị bỏ qua | Lời gọi không đi qua proxy, self-invocation hoặc transaction không thực sự hoạt động | Kiểm tra proxy và transaction manager |
| Listener chạy ngay dù phase là AFTER_COMMIT | fallbackExecution=true và không có transaction | Hiểu fallback là xử lý ngay, không phải chờ commit |
| Listener chạy khi dữ liệu chưa commit | Dùng @EventListener thông thường trong transaction | Chuyển sang AFTER_COMMIT nếu cần dữ liệu đã commit |
| Bật fallback rồi vẫn không có transaction | fallback không tạo transaction | Mở transaction ở publisher hoặc service cần transaction |
| Listener chạy hai lần | Cùng logic được đăng ký bằng nhiều listener hoặc publish lặp | Kiểm tra đăng ký và bảo đảm idempotency |
| Event bị mất sau khi process dừng | Application event chỉ nằm trong bộ nhớ | Dùng transactional outbox hoặc message broker khi cần độ bền |

## 8. Transactional event không phải message queue

Spring application event là cơ chế thông báo trong một ApplicationContext. Transactional event listener gắn thời điểm xử lý với transaction synchronization, nhưng không tự lưu event vào database.

Nếu publish event ngoài transaction và transactional listener bị bỏ qua, Spring không giữ event để xử lý lại khi một transaction xuất hiện sau đó.

Ngay cả khi publish trong transaction và listener AFTER_COMMIT được gọi, process vẫn có thể dừng sau khi database commit nhưng trước khi listener hoàn thành. Nếu nghiệp vụ yêu cầu giao nhận bền vững, cần cơ chế như transactional outbox hoặc message broker.

Cũng cần thiết kế listener idempotent nếu hệ thống có retry ở tầng khác. Không dựa vào @TransactionalEventListener để cung cấp exactly-once delivery.

## 9. Lưu ý với transaction bất đồng bộ và reactive

Transaction thông thường của Spring thường được gắn với thread hiện tại. Nếu publish event từ một thread không có transaction synchronization, transactional listener sẽ xem như không có transaction và áp dụng fallbackExecution.

Với reactive transaction, transaction context được truyền qua Reactor Context thay vì dựa hoàn toàn vào ThreadLocal. Không nên chuyển việc publish event sang một callback hoặc thread khác rồi kỳ vọng transaction context tự xuất hiện. Spring cung cấp **TransactionalEventPublisher** để publish event có mang reactive transaction context khi cần xử lý transactional event trong reactive flow.

## 10. Checklist khi publish event không có transaction

- Xác định publisher có đang ở trong transaction synchronization hay không.
- Phân biệt listener thông thường với transactional listener.
- Nhớ fallbackExecution mặc định là false.
- Nếu bật fallbackExecution=true, hiểu listener sẽ chạy ngay khi không có transaction.
- Không giả định publishEvent tự tạo transaction.
- Nếu cần AFTER_COMMIT, phát event trong transaction thực sự.
- Kiểm tra @Transactional có đi qua proxy và transaction manager có hoạt động.
- Không dùng fallback để che một transaction bắt buộc bị thiếu.
- Nếu listener ghi database, mở transaction riêng khi cần commit.
- Không coi application event là hàng đợi bền vững hoặc cơ chế retry.
- Dùng outbox hoặc broker nếu cần lưu event qua restart.
- Thiết kế idempotency nếu công việc có thể được retry hoặc phát lặp.

## 11. Tài liệu tham khảo

- [Spring Framework 6.2 Reference — Transaction-bound Events](https://docs.spring.io/spring/reference/6.2/data-access/transaction/event.html)
- [TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)

Khi publish event ngoài transaction, **@EventListener** vẫn xử lý event theo cách thông thường. **@TransactionalEventListener** mặc định bỏ qua event vì không có transaction synchronization; bật **fallbackExecution=true** sẽ cho phép xử lý ngay trong lần publish đó. Hãy chọn fallback khi xử lý ngoài transaction là hợp lệ, và tạo transaction thật ở publisher khi nghiệp vụ yêu cầu callback sau commit.
