# Thông báo email sau khi tạo đơn với Spring Framework Application Events

## 1. Bài toán và kết quả cần đạt

Trong nhóm **Mẫu triển khai** của **Spring Framework Application Events**, tình huống phổ biến là: người dùng đặt hàng thành công, ứng dụng cần gửi email xác nhận. Nếu xử lý email ngay trong logic đặt đơn, ta dễ vô tình làm request chậm vì SMTP/HTTP call, gửi thư cho một đơn vừa bị rollback, hoặc khiến lỗi email làm thất bại cả quy trình đã có những thay đổi khác.

Một thiết kế tốt phải trả lời **hai câu hỏi độc lập**:

1. **Khi nào được phép gửi email?** Thông thường, sau khi dữ liệu đặt đơn đã được **commit thành công** và người nhận/nội dung đã được xác định theo chính sách.
2. **Gửi email có thể thất bại thì phục hồi thế nào?** Có thể chấp nhận best-effort notification, hay phải có record bền vững, retry, giới hạn duplicate và cảnh báo?

Với Spring Application Events, lựa chọn đơn giản là publish một `OrderCreatedEvent` từ service tạo đơn rồi xử lý qua `@TransactionalEventListener(phase = AFTER_COMMIT)`. Khi yêu cầu cao hơn, cùng một **business fact** nên được ghi thành một outbox/job durable trong transaction và một worker thực hiện email với retry/idempotency.

Mục tiêu của bài:
- Xây dựng luồng **tạo đơn → commit → thông báo email** có ranh giới rõ.
- Hiểu `@EventListener`, `@TransactionalEventListener`, `@Async` và hạn chế của mỗi cơ chế.
- Thiết kế event payload bất biến, chỉ chứa dữ liệu cần thiết.
- Chạy một ví dụ Java 17+ sử dụng Spring Context, Spring JDBC, H2 và fake mail gateway, kiểm chứng commit/rollback.
- Biết cách kết nối `JavaMailSender`/SMTP trong Spring Boot ở mức tích hợp.
- Thiết kế outbox, idempotency, retry, duplicate prevention, logging và kiểm thử.

**Lưu ý quan trọng:** "Đã publish event" không đồng nghĩa "email đã gửi thành công". Kể cả `@TransactionalEventListener(AFTER_COMMIT)` cũng **không phải** bảo đảm gửi bền vững qua crash/restart.

## 2. Ba trạng thái không được đánh đồng

Hãy phân biệt ba mốc:

```text
HTTP POST /orders
      |
      v
PlaceOrderService
      |
      +--> Kiểm tra quyền, tồn kho, giá và dữ liệu khách hàng
      +--> INSERT orders, order_items trong transaction
      +--> publishEvent(OrderCreatedEvent)
      |
      v
Transaction COMMIT thành công
      |
      v
@TransactionalEventListener(AFTER_COMMIT)
      |
      +--> Chuẩn bị email và gọi mail gateway
      |
      v
Mail provider ACCEPTED / ERROR
      |
      v
Người nhận thực sự nhận email (không luôn quan sát được tức thời)
```

Có ít nhất ba loại “thành công”:

| Trạng thái | Ý nghĩa | Không chứng minh |
| --- | --- | --- |
| **ORDER_COMMITTED** | Đơn đã được lưu trong DB theo business transaction | Email đã được provider nhận |
| **EMAIL_SUBMITTED** | Ứng dụng đã gọi sender hoặc đặt job vào queue | SMTP/provider đã chấp nhận/đã gửi đi |
| **EMAIL_ACCEPTED** | SMTP/provider báo chấp nhận request gửi | Thư tới inbox, được đọc, không bị lọc spam |

Trong hệ thống thật, **provider accepted** và **delivered** là hai kết quả khác nhau. Một HTTP 202 của email API thường chỉ nói nhà cung cấp đã nhận job. Nếu muốn theo dõi delivery/bounce, cần webhook/status API, xác thực webhook và lưu lifecycle riêng.

Không lấy độ trễ `publishEvent()` làm thời gian gửi email khi handler chạy async. Không dùng log “send requested” để tuyên bố người dùng đã nhận thư.

## 3. Thiết kế đơn hàng và event payload

Trong ứng dụng nghiệp vụ, việc đặt hàng là **command**, còn `OrderCreatedEvent` diễn tả **fact** đã được service chấp nhận:

```java
public record OrderCreatedEvent(
    String eventId,
    String orderId,
    String recipientEmail,
    String customerDisplayName,
    String correlationId
) {}
```

Đây là **record minh họa**, không phải file độc lập. Những trường nên cân nhắc:

- `eventId`: định danh một event logic, ổn định nếu retry/replay chính event ấy.
- `orderId`: định danh đơn, dùng tạo email template và link tới trang đơn.
- `recipientEmail`: địa chỉ người nhận đã được chọn/kiểm tra theo policy; có thể không đưa vào event nếu dữ liệu này phải được truy vấn tại thời điểm gửi.
- `customerDisplayName`: thông tin hiển thị tối thiểu; không cần toàn bộ `CustomerEntity`.
- `correlationId`: nối log/request/event flow; không dùng làm idempotency key cho nhiều events.

**Không đưa JPA managed entity thẳng vào event**: entity mutable, có lazy associations, gắn persistence context và có thể làm lộ dữ liệu nhạy cảm. `record` chỉ làm immutable các field reference; nếu field là `List` mutable hoặc object mutable thì vẫn phải copy/snapshot.

### Email address nên snapshot hay truy vấn lại?

Có hai thiết kế hợp lệ, tùy nghiệp vụ:

1. **Snapshot trong event/outbox:** đơn được xác nhận gửi tới email đã được người dùng phê duyệt ở thời điểm đặt hàng. Hữu ích khi cần lịch sử/replay nhất quán; phải bảo vệ PII trong payload, outbox và log.
2. **ID-only rồi load lại:** event chỉ mang `orderId`; worker truy vấn email hiện hành theo policy, phù hợp nếu phải dùng địa chỉ mới nhất. Nhưng một đơn có thể bị thay đổi/xóa hoặc tenant đã đổi; cần định nghĩa rõ business contract.

Không nên tùy tiện dùng email từ request body chưa validate. Application service phải lấy principal đã xác thực, kiểm tra quyền với đơn/tenant và chọn địa chỉ nhận hợp lệ trước khi tạo fact.

### Một event có thể có nhiều listener

```text
OrderCreatedEvent
   |
   +--> AuditListener
   +--> InventoryProjectionListener
   +--> EmailConfirmationListener
   +--> AnalyticsListener
```

Mỗi listener có trách nhiệm riêng. **Một listener gửi email thất bại không nên tự động khiến email được gửi trùng vì toàn bộ lệnh tạo đơn bị retry.** Nếu retry event, các listener khác cũng có thể bị gọi lại và cần idempotency riêng. Với nghiệp vụ quan trọng, theo dõi kết quả theo consumer/handler hoặc tạo durable job riêng cho email.

## 4. @EventListener thường so với @TransactionalEventListener(AFTER_COMMIT)

### 4.1. @EventListener đồng bộ: dễ gửi trước khi commit

Một listener thường:

```java
@Component
public class EmailConfirmationListener {
    private final MailGateway mail;

    public EmailConfirmationListener(MailGateway mail) {
        this.mail = mail;
    }

    @EventListener
    public void on(OrderCreatedEvent event) {
        mail.sendConfirmation(event.orderId(), event.recipientEmail());
    }
}
```

Đây là **mã tích hợp**, cần `MailGateway`, imports và cấu hình khác. Với `SimpleApplicationEventMulticaster` mặc định, listener đồng bộ chạy ngay trên thread gọi `publishEvent`. Nếu publisher đang ở trong `@Transactional`, email có thể được gửi **trước khi transaction commit**. Sau đó database rollback nhưng email vẫn đã đi, dẫn tới thư xác nhận cho một đơn không tồn tại.

SMTP/provider bên ngoài không tham gia transaction DB theo mặc định. Một `@Transactional` quanh service không thể “rollback email”.

### 4.2. @TransactionalEventListener(AFTER_COMMIT)

Tại listener email, dùng:

```java
@Component
public class EmailConfirmationListener {
    private final MailGateway mail;

    public EmailConfirmationListener(MailGateway mail) {
        this.mail = mail;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderCreatedEvent event) {
        mail.sendConfirmation(event.orderId(), event.recipientEmail());
    }
}
```

Đây vẫn là **mã tích hợp**, không phải file hoàn chỉnh. Listener được đăng ký để callback khi transaction hiện hành **commit thành công**. Với Spring Framework 6.1, mặc định phase là `AFTER_COMMIT`; khai báo tường minh giúp dễ đọc.

| Tình huống | `@EventListener` đồng bộ | `@TransactionalEventListener(AFTER_COMMIT)` |
| --- | --- | --- |
| Publish trong transaction, sau đó commit | Thường xử lý ngay lúc publish | Chạy callback sau commit thành công |
| Publish trong transaction, sau đó rollback | Có thể đã gửi email | Không chạy callback AFTER_COMMIT |
| Publish ngoài transaction | Vẫn được gọi theo multicaster | Mặc định **không được gọi** |
| Process crash ngay sau commit | Có thể đã gửi hoặc chưa | Callback vẫn có thể **mất** |
| SMTP/provider lỗi | Có thể ảnh hưởng transaction/publisher theo timing | DB gốc đã commit; phải xử lý lỗi email độc lập |
| Event được lưu bền vững | Không tự có | Không tự có |

**`fallbackExecution=false` là mặc định.** Nếu không có transaction tương ứng, `@TransactionalEventListener` thường bỏ qua event. Có thể bật `fallbackExecution=true`, nhưng làm vậy thay đổi contract “chỉ gửi sau commit”; đừng bật chỉ vì test không gọi được listener.

### 4.3. AFTER_COMMIT không tự chạy trên thread khác

Callback `AFTER_COMMIT` có thể chạy **trong thread hoàn tất transaction**, vì đó là một phase callback, không đồng nghĩa async. Nếu gọi SMTP blocking ngay tại callback, request vẫn có thể chậm trong lúc transaction commit trả về caller.

Muốn tách thời gian chờ I/O, có thể chuyển xử lý email sang executor hoặc durable worker. Nhưng `@Async` đơn lẻ chỉ là chuyển thread, không có persistence/retry bền vững. Cần quyết định đánh đổi tốc độ/độ tin cậy theo mức quan trọng của thư.

### 4.4. Transaction cũ không phục vụ việc ghi mới sau commit

Một callback AFTER_COMMIT có thể được gọi khi tài nguyên transaction trước đó chưa được cleanup hoàn toàn. Nếu listener cần tạo một `EmailDelivery` record trong DB sau commit, phải mở **transaction mới** thích hợp, ví dụ method qua Spring bean proxy với `@Transactional(propagation = REQUIRES_NEW)`. Không giả định các ghi DB trong callback được commit như một phần của transaction nguồn vốn đã hoàn tất.

Đây cũng là lý do outbox được chèn **bên trong transaction tạo đơn**, chứ không đợi tới AFTER_COMMIT mới ghi bản ghi outbox: nếu process chết giữa commit và callback, intent gửi thư có thể chưa từng được lưu.

## 5. Ví dụ Java 17+ chạy được: tạo đơn, commit, rollback và fake email sender

Demo sau kiểm chứng chính xác:
- Có một database H2 in-memory và bảng `orders`.
- `OrderService` dùng Spring `TransactionTemplate` để thực hiện lưu đơn và publish `OrderCreatedEvent` bên trong transaction.
- `OrderEmailListener` dùng `@TransactionalEventListener(AFTER_COMMIT)`.
- `RecordingMailer` thay SMTP thật bằng một fake sender; chương trình **không gửi email ra ngoài**.
- Đơn `ORD-1` commit thì có một email giả được ghi nhận.
- Đơn `ORD-2` rollback thì không có email.
- Event publish ngoài transaction bị bỏ qua bởi listener transaction-bound mặc định.

Demo không dùng Spring Boot hay server HTTP; nhờ vậy có thể tập trung vào hành vi của Spring Context + Spring Transaction. Nó **không chứng minh gửi email bền vững qua restart**, vì fake mailer dùng RAM.

### 5.1. Cấu trúc

```text
order-created-email-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/OrderCreatedEmailDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'order-created-email-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
    implementation 'org.springframework:spring-jdbc:6.1.21'
    implementation 'org.springframework:spring-tx:6.1.21'
    implementation 'com.h2database:h2:2.2.224'
}

application {
    mainClass = 'demo.OrderCreatedEmailDemo'
}
```

Lệnh chạy yêu cầu JDK 17+ và Gradle có thể tải dependencies từ Maven Central. H2 ở đây chỉ là DB phục vụ demo, không thay thế RDBMS production.

### 5.2. File Java hoàn chỉnh

`src/main/java/demo/OrderCreatedEmailDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public final class OrderCreatedEmailDemo {

    public record OrderCreatedEvent(
            String eventId, String orderId, String recipientEmail) {}

    public static final class RecordingMailer {
        private final List<String> deliveries = new ArrayList<>();

        public void sendConfirmation(
                String orderId, String recipientEmail) {
            deliveries.add(orderId + "|" + recipientEmail);
            System.out.println(
                "EMAIL_SENT order=" + orderId + " to=" + recipientEmail
            );
        }

        public int count() {
            return deliveries.size();
        }
    }

    public static final class OrderService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transactions;
        private final ApplicationEventPublisher events;

        public OrderService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher events) {
            this.jdbc = jdbc;
            this.transactions = transactions;
            this.events = events;
        }

        public void create(
                String orderId, String email, boolean rollback) {
            transactions.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO orders (id, email) VALUES (?, ?)",
                    orderId, email
                );

                events.publishEvent(new OrderCreatedEvent(
                    "EVT-" + orderId, orderId, email
                ));

                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }
    }

    public static final class OrderEmailListener {
        private final RecordingMailer mailer;

        public OrderEmailListener(RecordingMailer mailer) {
            this.mailer = mailer;
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void onOrderCreated(OrderCreatedEvent event) {
            mailer.sendConfirmation(
                event.orderId(), event.recipientEmail()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds =
                new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:orders_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        public RecordingMailer recordingMailer() {
            return new RecordingMailer();
        }

        @Bean
        public OrderEmailListener orderEmailListener(
                RecordingMailer mailer) {
            return new OrderEmailListener(mailer);
        }

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher events) {
            return new OrderService(jdbc, transactions, events);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService orders = context.getBean(OrderService.class);
            RecordingMailer mailer =
                context.getBean(RecordingMailer.class);

            jdbc.execute(
                "CREATE TABLE orders (" +
                "id VARCHAR(40) PRIMARY KEY, " +
                "email VARCHAR(200) NOT NULL)"
            );

            // 1. Commit: callback AFTER_COMMIT chạy.
            orders.create("ORD-1", "alice@example.test", false);

            // 2. Rollback: callback AFTER_COMMIT không chạy.
            orders.create("ORD-2", "bob@example.test", true);

            // 3. Không có transaction: fallbackExecution=false.
            context.publishEvent(new OrderCreatedEvent(
                "EVT-ORPHAN", "ORD-X", "nobody@example.test"
            ));

            int persistedOrders = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders",
                Integer.class
            );
            System.out.println("ORDERS_COMMITTED=" + persistedOrders);
            System.out.println("EMAILS_SENT=" + mailer.count());
        }
    }
}
```

Chạy:

```bash
gradle run --quiet
```

**Stdout nghiệp vụ kỳ vọng** (bỏ qua thông báo thêm của Gradle/logging nếu có):

```text
EMAIL_SENT order=ORD-1 to=alice@example.test
ORDERS_COMMITTED=1
EMAILS_SENT=1
```

### 5.3. Giải thích vì sao output đúng

1. `AnnotationConfigApplicationContext(Config.class)` tạo bean `TransactionTemplate`, `JdbcTemplate`, `OrderService` và listener. Spring đăng ký `@TransactionalEventListener` thông qua event listener infrastructure của context.
2. `orders.create("ORD-1", ...)` mở transaction bằng `TransactionTemplate`, insert một row và publish `OrderCreatedEvent` khi transaction đang hoạt động. Callback transaction-bound được đăng ký, **chưa gửi email ngay tại lúc publish**.
3. Transaction thứ nhất commit, rồi callback `AFTER_COMMIT` gọi `RecordingMailer` đồng bộ. Fake mailer in dòng `EMAIL_SENT` và ghi một entry trong RAM.
4. `orders.create("ORD-2", ..., true)` insert và publish trong transaction thứ hai, sau đó gọi `status.setRollbackOnly()`. DB rollback, listener AFTER_COMMIT không chạy cho event thứ hai.
5. Một `OrderCreatedEvent` khác được publish **ngoài transaction**. Với `fallbackExecution=false` mặc định, listener này không được gọi.
6. Query bảng `orders` còn duy nhất `ORD-1`; fake mailer chỉ có một delivery. Hai dòng cuối là `ORDERS_COMMITTED=1` và `EMAILS_SENT=1`.
7. Không có executor; listener chạy đồng bộ trong phase commit. Nếu fake mailer bị thay bằng SMTP thật, thời gian commit callback có thể vẫn làm caller chờ dù dữ liệu DB đã commit.
8. Để tránh hiểu sai tên `EMAIL_SENT`, đây chỉ là **log của fake mailer**. Nó không khẳng định email đến inbox thật và không chứng minh crash recovery.

**Tại sao dùng TransactionTemplate thay cho @Transactional trong demo?** Nó tạo một transaction thực mà không phụ thuộc vào AOP method proxy. Trong ứng dụng Spring Boot/service thông thường, `@Transactional` trên public service method được gọi qua Spring proxy là cách phổ biến, nhưng dễ bị vô hiệu do self-invocation nếu gọi nội bộ bằng `this.method()`. Ví dụ dùng template giúp cơ chế commit/rollback rõ ràng và độc lập với lớp web.

### 5.4. Chương trình chưa có security và email thật

Địa chỉ `alice@example.test` và `bob@example.test` là dữ liệu giả, tránh gửi nhầm người thật. Demo không xác thực người dùng, không kiểm tra ownership/order amount và không gửi email thực. Trong production, phải thêm authorization, input validation, giao dịch tạo order/items thực, data classification, template versioning, sender identity, monitoring và recovery.

`RecordingMailer` dùng `ArrayList` không thread-safe; phù hợp vì demo chạy đồng bộ trên một thread. Nếu đổi sang `@Async` hoặc executor nhiều worker, test fake cần collection đồng bộ và signal chờ completion, không đọc count ngay sau publish.

## 6. Tích hợp JavaMailSender hoặc nhà cung cấp email

Với **Spring Boot** và SMTP, thường dùng `spring-boot-starter-mail` và inject `JavaMailSender`. Một adapter đơn giản cho email text:

```java
@Component
public final class SmtpOrderMailGateway {
    private final JavaMailSender mailSender;

    public SmtpOrderMailGateway(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(
            String orderId, String recipientEmail) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("orders@example.com");
        message.setTo(recipientEmail);
        message.setSubject("Xác nhận đơn hàng " + orderId);
        message.setText(
            "Đơn hàng " + orderId +
            " đã được ghi nhận. Vui lòng xem chi tiết trong tài khoản."
        );
        mailSender.send(message);
    }
}
```

Đây là **đoạn tích hợp, không phải file độc lập**. Cần dependency Spring Boot Mail, imports `org.springframework.mail.javamail.JavaMailSender`, `org.springframework.mail.SimpleMailMessage`, `@Component`, cấu hình SMTP và một địa chỉ sender đã xác thực với email provider. Địa chỉ `orders@example.com` chỉ minh họa; không mặc định domain đó có thể gửi mail.

Ví dụ cấu hình **tham khảo** cho Spring Boot (không đưa mật khẩu vào source control):

```yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: "orders-service"
    password: "\${SMTP_PASSWORD}"
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
```

Cấu hình này là **mẫu tham khảo**. SMTP host/username chỉ là placeholder mang tính hạ tầng, không phải server hoạt động. Trong ứng dụng thực hãy cấp credentials bằng secrets manager hoặc environment, bật TLS theo policy của provider và kiểm tra `From` domain/SMTP relay permissions. Không log username/password, full mail body hay token.

### HTML email và template

Nếu cần email HTML, dùng `MimeMessage`, `MimeMessageHelper` và template engine như Thymeleaf/Freemarker đã cấu hình. Email HTML có nguy cơ chèn nội dung không an toàn nếu đưa thẳng `customerDisplayName` hoặc dữ liệu người dùng vào template không escape. Nên:
- Escape dữ liệu động theo HTML context.
- Chỉ dùng link HTTPS đến domain chuẩn hóa; không xây link tùy ý từ `Host` header chưa tin cậy.
- Không đưa thông tin nhạy cảm không cần thiết vào subject/body.
- Định nghĩa ngôn ngữ, timezone, currency và template version.
- Test rendering với ký tự Unicode, tên dài, email quốc tế nếu sản phẩm hỗ trợ.

Nếu gửi qua email provider HTTP API, adapter sẽ gọi HTTP thay SMTP, nhưng **lỗi mơ hồ sau timeout, retry/idempotency và status accepted/delivered vẫn là bài toán tương tự**.

## 7. @Async có giải quyết việc gửi email chậm không?

Ví dụ cấu hình tích hợp:

```java
@Configuration
@EnableAsync
public class EmailAsyncConfig {
    @Bean(name = "emailExecutor")
    public ThreadPoolTaskExecutor emailExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("email-worker-");
        return executor;
    }
}
```

Một method có thể xử lý trên executor:

```java
@Service
public class EmailBackgroundService {
    @Async("emailExecutor")
    public void sendAsync(OrderCreatedEvent event) {
        mailGateway.sendConfirmation(
            event.orderId(), event.recipientEmail()
        );
    }
}
```

Đây là **hai đoạn tích hợp**, cần imports, `@EnableAsync`, bean `mailGateway`, method thực thi qua Spring async proxy và error handler thích hợp. Có thể có một listener AFTER_COMMIT gọi `EmailBackgroundService.sendAsync(...)`. Cách đó chuyển blocking SMTP call khỏi thread hoàn tất transaction, nhưng:

- Executor queue thường nằm trong RAM; process crash sau commit trước khi task xử lý sẽ làm mất email.
- `@Async void` exception không tự propagate về publisher; cần `AsyncUncaughtExceptionHandler`, metrics/logging và retry theo policy.
- Có thể submit task thành công nhưng worker lỗi; "enqueued" khác "sent".
- Bounded queue có thể đầy, sinh rejection. Không cấu hình queue vô hạn rồi bỏ qua memory pressure.
- `SecurityContextHolder` và MDC là thread-bound trong stack imperative; context không tự truyền qua executor. Dùng explicit event metadata hoặc context propagation được cấu hình đúng.
- **Không kết hợp `@Async` và `@TransactionalEventListener` một cách tùy tiện** rồi giả định transaction vẫn được mang theo worker. Listener giao transaction synchronization cần được đăng ký ở context phù hợp; phần task async chạy ngoài transaction nguồn.

### Các cấp độ giải pháp

| Phương án | Không gửi trước rollback? | Request chờ I/O? | Email intent durable qua restart? |
| --- | --- | --- | --- |
| `@EventListener` đồng bộ trong transaction | Không bảo đảm | Có | Không |
| `@TransactionalEventListener(AFTER_COMMIT)` đồng bộ | Có, theo phase commit | Có thể vẫn chờ | Không |
| AFTER_COMMIT gọi `@Async` | Có, theo phase commit | Thường không chờ SMTP | Không |
| Ghi outbox/job trong transaction + worker | Có | Thường không | **Có**, nếu storage/worker/retry được thiết kế và vận hành đúng |

Với email xác nhận đơn hàng có SLA rõ và không chấp nhận mất thông báo, **outbox hoặc durable job** là thiết kế ưu tiên. `@TransactionalEventListener` đơn giản vẫn hữu ích cho tác vụ best-effort hoặc để đánh thức worker đọc outbox; source of truth của việc cần gửi phải nằm trong durable store, không nằm ở event object trong RAM.

## 8. Mẫu triển khai production: transactional outbox cho email

### 8.1. Transaction đặt hàng lưu cả email intent

Trong transaction tạo đơn, ghi:
1. `orders` và `order_items`.
2. Một bản ghi `outbox_events` hoặc `email_jobs` với `eventId`/`messageId`, `orderId`, người nhận hoặc dữ liệu cần truy vấn, template key, trạng thái `PENDING`.
3. Commit cả hai cùng nhau.

```text
@Transactional PlaceOrderService
      |
      +--> INSERT orders (...)
      +--> INSERT order_items (...)
      +--> INSERT email_jobs (
               job_id, order_id, template_key,
               recipient, payload, status='PENDING'
           )
      +--> COMMIT
               |
               v
      Email worker quét/claim PENDING
               |
               +--> send via provider
               +--> ghi provider response / status
               +--> ACK: mark SENT hoặc retry
```

Nếu transaction rollback, job email cũng rollback. Nếu commit rồi JVM chết ngay, bản ghi job vẫn nằm trong DB và worker sau restart có thể tiếp tục.

### 8.2. Schema tham khảo

Pseudo-SQL trung tính về ý tưởng, cần điều chỉnh theo database:

```sql
CREATE TABLE email_jobs (
    job_id          VARCHAR(80) PRIMARY KEY,
    order_id        VARCHAR(80) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    template_version INTEGER NOT NULL,
    recipient       VARCHAR(320) NOT NULL,
    payload_json    TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP,
    last_error_code VARCHAR(100),
    provider_message_id VARCHAR(160),
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
```

Trong production còn cần indexes cho `(status, next_attempt_at)`, tenant scoping, retention, encryption/PII policy, optimistic locking/lease và audit metadata. `recipient` cùng `payload_json` chứa dữ liệu cá nhân, cần access control và retention phù hợp.

Một business rule quan trọng: cùng order không nên tạo **hai job xác nhận giống nhau** do retry command. Có thể dùng unique constraint theo `(order_id, notification_type, template_version)` nếu quy tắc nghiệp vụ đúng là **một email xác nhận cho mỗi phiên bản**. Nhưng nếu đơn có thể được xác nhận lại hợp lệ theo một workflow khác, key đó phải được thiết kế lại. **Đừng tạo event ID mới cho mỗi retry của cùng logical notification.**

### 8.3. Thuật toán dispatcher

Pseudo-code:

```text
loop until stopped:
    claim a bounded batch of due PENDING jobs with a lease
    for each job:
        validate template/schema and recipient policy
        try:
            provider.send(
                idempotencyKey = job.jobId,
                renderedMessage = render(job)
            )
            record provider acknowledgment
            mark job SENT
        catch retryable error:
            attempts += 1
            nextAttemptAt = now + exponentialBackoffWithJitter()
            status = PENDING
        catch permanent error:
            status = FAILED or NEEDS_REVIEW
            emit alert/operational event
    release/renew lease as needed
```

Đây là **thuật toán minh họa**, không phải script chạy độc lập. Cần lưu ý:
- Claim dùng row lock/lease phù hợp, ví dụ `SELECT ... FOR UPDATE SKIP LOCKED` với DB hỗ trợ.
- Không giữ một DB transaction mở xuyên qua SMTP request lâu trừ khi có lý do rõ.
- Lease hết hạn khi worker chết để instance khác nhận lại.
- Retry có giới hạn backoff, jitter và phân loại lỗi tạm thời/vĩnh viễn.
- Metrics tách `pending`, `inflight`, `sent`, `failed` và `oldest pending age`.
- Khi gửi qua API có idempotency key, truyền **cùng key** qua mọi retry.
- Mark `SENT` chỉ sau khi nhận mốc acknowledgment đã định; nếu ACK mất, job sẽ được thử lại.

### 8.4. Vì sao vẫn có thể có email trùng?

Failure window:

```text
Worker gửi email tới provider --> provider chấp nhận
                               |
                               X process crash trước mark SENT
                               |
                               v
                 Worker khác thấy PENDING và gửi lại
```

Outbox giúp **không mất intent**, nhưng sender có thể retry **ít nhất một lần**, dẫn tới duplicate nếu provider không có idempotency theo key. Không tuyên bố "exactly once email" chỉ vì dùng outbox.

Các cách giảm duplicate:
- Provider hỗ trợ idempotency key: dùng `jobId` ổn định; tìm hiểu chính sách TTL/semantic của provider.
- Khi status không rõ (timeout sau khi provider có thể đã nhận), truy vấn provider theo external reference nếu có.
- Đặt unique constraint trong DB để một command không tạo nhiều logical jobs.
- Giữ provider message ID và webhook events để reconciliation.
- Với API ngoài không hỗ trợ dedupe đáng tin, ghi nhận khả năng duplicate và có quy trình xử lý.

**Không đánh dấu SENT trước khi gọi provider** chỉ để tránh duplicate: crash sau mark SENT nhưng trước send sẽ làm mất email vĩnh viễn. Đây là trade-off giữa mất thông điệp và gửi trùng, không thể xóa bằng một `try/catch`.

## 9. Email idempotency là câu hỏi nghiệp vụ

Có ít nhất ba cấp idempotency:

| Cấp | Vấn đề | Cơ chế |
| --- | --- | --- |
| **Command đặt đơn** | Client retry POST tạo nhiều đơn | Idempotency key của command, unique business constraint |
| **Tạo email job** | Cùng order sinh nhiều job giống nhau | Unique notification intent key trong DB transaction |
| **Gửi tới provider** | Worker retry cùng job sau timeout/crash | Provider idempotency key/reconciliation khi hỗ trợ |

Ba cấp này không thay thế nhau. Một order chỉ được tạo một lần không đồng nghĩa email chỉ được gửi một lần. Ngược lại, email được dedupe không chứng minh command tạo đơn đã idempotent.

### Tại sao không dedupe theo correlationId?

Một request có thể phát nhiều event `OrderCreated`, `PaymentConfirmed`, `ShipmentCreated`, rồi gửi ba loại email khác nhau cùng correlation ID. Nếu dùng correlation ID làm key dedupe, ta có thể bỏ nhầm notification hợp lệ. Key phù hợp phải bao gồm identity của **logical notification** (ví dụ `jobId` hoặc `orderId + notificationType + templateVersion` theo policy).

### Một đơn có nhiều người nhận

Nếu đơn cần gửi email tới khách hàng và nhân viên nội bộ, hãy tạo **recipient-specific delivery jobs** hoặc một delivery record per recipient phù hợp. Không dùng cùng marker cho hai recipient rồi coi một thư gửi thành công nghĩa thư còn lại cũng thành công. Policy idempotency và outcome cần tách đúng đơn vị.

## 10. Lỗi SMTP/provider và xử lý exception

Lỗi có thể xảy ra ở các thời điểm khác nhau:

- **Trước khi gửi:** thiếu template, invalid recipient, lỗi render, authorization không hợp lệ.
- **Trong khi gửi:** DNS, TLS handshake, connection timeout, auth failure, SMTP 4xx/5xx, provider 429/5xx.
- **Sau khi provider chấp nhận:** response bị mất, mạng đứt, worker crash trước lưu trạng thái.
- **Sau khi provider nhận:** bounce, complaint, unsubscribe hoặc delivery webhook báo thất bại.

Phân loại lỗi theo contract provider, không quy nạp mọi 4xx/5xx theo một bảng cứng. Thông thường:
- Lỗi kết nối hoặc throttling có thể retry với backoff.
- Recipient không hợp lệ hoặc template schema sai cần sửa/quarantine.
- Provider auth sai là lỗi cấu hình cần alert, không retry storm.
- Timeout có thể là kết quả **không rõ**, phải retry với key ổn định hoặc reconcile.
- Bounce/complaint cần quy trình quản lý recipient/consent, không gửi lại vô hạn.

Với một callback `AFTER_COMMIT` gửi SMTP trực tiếp, nếu mailer ném exception, **đơn hàng đã commit không thể bị rollback do lỗi email**. Exception có thể quay về caller của commit tùy luồng callback và transaction manager, dẫn tới nguy cơ API báo lỗi trong khi đơn đã được tạo. Vì vậy:
- Đừng để kết quả gửi mail best-effort quyết định lại trạng thái của đơn đã commit.
- Nếu việc gửi là bắt buộc, lưu durable intent rồi trả kết quả tạo đơn theo business contract.
- Có structured logs/metrics, retry và bảng trạng thái delivery tách khỏi status của order.
- Không vô tình retry lại cả lệnh `PlaceOrder` chỉ vì callback email fail.

### Một lưu ý về retry trong cùng JVM

Có thể thêm `@Retryable` hoặc một vòng retry quanh mail gateway cho lỗi tạm thời. Nhưng retry trong RAM không cứu được việc process crash. `@Retryable` cũng đòi hỏi cấu hình Spring Retry/AOP tương ứng; bản thân `@TransactionalEventListener` không tự retry. Đừng dùng retry vô hạn gây overload và gửi trùng.

## 11. Transaction và thread: những điểm cần nhớ

### 11.1. Synchronous callback không bảo đảm latency thấp

`AFTER_COMMIT` giúp đúng timing, nhưng callback gọi SMTP blocking có thể kéo dài thời gian trả response. Nếu email được đưa vào async executor, request thường nhanh hơn nhưng lại có khoảng mất job khi crash. Outbox + worker giúp tách latency mà vẫn giữ durable intent.

### 11.2. `@Async` và proxy

Một method annotation `@Async` cần `@EnableAsync` và được gọi qua Spring proxy trong cấu hình thích hợp. Gọi `this.sendAsync(...)` bên trong cùng bean thường bỏ qua advice. Với listener transaction-bound, không đẩy bước đăng ký synchronization sang thread async thiếu transaction context. Thực tế có thể để một listener AFTER_COMMIT đồng bộ **submit một task** cho service async riêng, nhưng nó vẫn là best-effort nếu không có outbox.

### 11.3. SecurityContext và MDC

Executor worker mặc định không có `SecurityContextHolder` của servlet request hoặc MDC correlation ID tương ứng. Truyền ID đã xác minh trong event/job, hoặc dùng context propagation đúng cấu hình khi cần. Không gửi JWT/session/password qua event để “giữ nguyên quyền”; job dài nên dùng service identity hạn chế và policy nhất quán.

### 11.4. Reactive transactions

Trong WebFlux/Reactor, transaction state gắn với Reactor Context. Spring 6.1 hỗ trợ transaction-bound event có `TransactionContext` như event source (thường thông qua `TransactionalEventPublisher`). Không suy luận từ ví dụ `TransactionTemplate` imperative rằng reactive subscription cũng có cùng ThreadLocal transaction. Nếu xử lý reactive, phải nối lifecycle/transaction và completion đúng cách; fire-and-forget `subscribe()` không thay durable job.

## 12. Bảo mật và quyền riêng tư của email event

Email address, tên người nhận, order line items, địa chỉ giao hàng và tổng tiền có thể là **dữ liệu cá nhân hoặc dữ liệu kinh doanh nhạy cảm**. Event nội bộ không phải ranh giới bảo mật. Những thực hành cần cân nhắc:

1. **Chỉ gửi thông tin tối thiểu:** template có thể chỉ cần order ID và tên hiển thị; không gửi full managed entity hoặc payment details.
2. **Quyền trên source:** service phải xác thực actor/tenant và xác minh được phép đặt đơn, không tin `approved=true` do client tự gửi.
3. **Email đúng recipient:** kiểm tra email snapshot hoặc truy vấn authoritative record theo policy; không nhận địa chỉ tùy ý từ event giả không có approved business fact.
4. **Dữ liệu trong outbox:** hạn chế quyền DB, encryption-at-rest nếu cần, retention và quy trình xóa khi policy yêu cầu.
5. **Log tối thiểu:** không log full body, auth header, token hoặc toàn bộ email address nếu không cần; có thể mask recipient.
6. **Link an toàn:** sử dụng HTTPS và host có cấu hình tin cậy; không tạo reset/payment links từ untrusted host hoặc token không được bảo vệ.
7. **HTML escaping:** tránh chèn nội dung không escape vào template, nhất là tên khách hàng hoặc ghi chú đơn.
8. **Consent và preferences:** phân biệt email giao dịch với marketing theo policy sản phẩm và quy định áp dụng; không tự gửi marketing chỉ vì có event đặt hàng.
9. **Replay có kiểm soát:** admin console hoặc DLQ replay có thể gửi lại email thật; phân quyền và audit thao tác replay.
10. **Webhook provider:** validate nguồn/cơ chế xác thực webhook và idempotency event webhook trước khi cập nhật trạng thái delivery.

Đừng tin rằng chỉ có Spring beans nội bộ nên mọi payload là trusted. Nếu một module có thể publish fake `OrderCreatedEvent` và listener có credential gửi email, đó là một dạng confused-deputy risk. Với side effect quan trọng, listener/worker nên gắn event tới record đã được application service ghi nhận hợp lệ hoặc có policy rõ về nguồn và quyền.

## 13. Observability: đo đúng đơn vị

Một bộ metric minh họa:

| Metric | Ý nghĩa |
| --- | --- |
| `orders.created.count` | Số đơn đã tạo theo business transition |
| `email.jobs.pending.count` | Số email jobs đang chờ |
| `email.jobs.oldest.age` | Tuổi job cũ nhất chưa hoàn tất |
| `email.send.attempts` | Số lần thử gửi (có thể lớn hơn số jobs) |
| `email.send.errors` | Lần gửi lỗi theo category hữu hạn |
| `email.send.duration` | Thời gian một lần gọi provider |
| `email.jobs.sent.count` | Jobs được đánh dấu SENT |
| `email.delivery.bounced.count` | Webhooks báo bounce sau khi provider đã nhận |

Các metric này **không tự có** chỉ vì dùng Spring Context/Micrometer; cần instrumentation/binder và exporter phù hợp. Một số đơn có thể có nhiều email jobs, và mỗi job có thể retry nhiều lần. Không dùng attempts làm số đơn đã đặt hoặc số người đã nhận mail.

**Không gắn `orderId`, `eventId`, `email` hoặc `correlationId` vào metric tags** vì cardinality cao. Dùng tag hữu hạn như `template`, `status`, `provider`, `errorCategory`. Các ID riêng nên nằm trong structured logs/traces có access control; nên mask email recipient phù hợp.

Ví dụ log:

```text
INFO  eventId=EVT-42 orderId=ORD-42 notification=ORDER_CONFIRMATION
      jobId=EMAIL-42 status=PENDING attempt=0
WARN  jobId=EMAIL-42 provider=smtp status=RETRY_SCHEDULED
      errorCategory=TIMEOUT attempt=1
INFO  jobId=EMAIL-42 provider=smtp status=ACCEPTED attempt=2
```

Đây là **log minh họa**; không phải stdout của demo. `status=ACCEPTED` thể hiện provider đã chấp nhận attempt, không tự chứng minh thư được nhận. Khi muốn biết final delivery, cần provider status/webhook.

### Trace boundaries

Nếu hệ thống có Micrometer Tracing/OpenTelemetry, có thể tạo span cho:
- `placeOrder`;
- `persistOutbox`;
- `emailWorker.claim`;
- `renderTemplate`;
- `provider.send`;
- `deliveryWebhook.process`.

Với worker chạy nhiều phút sau request, liên kết trace/workflow bằng event ID/correlation ID có policy, không giả định thread-local context request vẫn tồn tại. Tracing hữu ích nhưng không thay thế durable state.

## 14. Kiểm thử ứng dụng: từ happy path tới crash

### 14.1. Unit test nội dung email

Dùng fake mail gateway và renderer:
- Với order ID đúng, subject/body/template/recipient đúng.
- Nội dung Unicode/Vietnamese, tên dài, số tiền/tiền tệ/định dạng ngày đúng.
- Các trường HTML được escape; link chỉ đến domain hợp lệ.
- Không đưa password/token/card data vào mail body.
- Template version đã được ghi nhận trong email job nếu cần replay tái lập.

### 14.2. Integration test transaction

Với H2 hoặc test database có transaction thật:
- **Commit:** insert order + publish event trong transaction; listener AFTER_COMMIT được gọi một lần.
- **Rollback:** insert order rồi rollback; AFTER_COMMIT listener **không** được gọi.
- **Ngoài transaction:** listener với `fallbackExecution=false` không được gọi.
- **Lỗi mail sau commit:** database vẫn còn order; lỗi phải được quan sát và được xử lý theo policy.
- Nếu dùng test method `@Transactional` mà test framework tự rollback cuối test, cần commit thật bằng `TransactionTemplate` hoặc `TestTransaction` để kiểm chứng AFTER_COMMIT.

Ví dụ mục 5 thực hiện ba kịch bản đầu trong một chương trình độc lập.

### 14.3. Kiểm thử @Async không flaky

Đừng viết:

```java
publisher.publishEvent(event);
Thread.sleep(500);
verify(mailGateway).sendConfirmation(...);
```

Đây là **anti-pattern minh họa**, không phải mã runnable. Thay bằng `CountDownLatch`, `CompletableFuture` hoặc Awaitility với timeout hữu hạn và một tín hiệu **sau khi** mail gateway đã đạt mốc cần test. Latch chỉ báo handler đã enqueue chưa đủ để assert provider đã chấp nhận.

Một fake test interface có thể trả future theo `jobId`; test đăng ký expectation trước khi publish, worker hoàn tất khi send thành công hoặc exception. Nếu có nhiều emails cùng lúc, dùng ID riêng cho từng job, không dùng một boolean static chung khiến test khác vô tình làm pass.

### 14.4. Test outbox và retry

Tạo các failure windows:

| Điểm lỗi | Kỳ vọng |
| --- | --- |
| DB rollback trước commit | Không có order/outbox job committed |
| DB commit xong, worker chưa chạy | Job PENDING vẫn còn qua restart |
| SMTP lỗi tạm thời | Job tăng attempt count, retry có backoff |
| Provider accepted, worker crash trước mark SENT | Job retry với **cùng idempotency key** |
| Duplicate job event | Business job uniqueness/dedupe bảo vệ |
| Worker claim song song | Chỉ một claim hợp lệ hoặc safe duplicate handling |
| Recipient invalid | Quarantine/FAILED và cảnh báo, không retry vô hạn |
| Provider bounce webhook lặp | Idempotent webhook processing |
| Unsubscribe/permission thay đổi | Chính sách nhận mail được áp dụng đúng ở execution time |

**Không chỉ mock `emailService.send()`** rồi kết luận retry/durability đúng. Nếu cần chứng minh crash recovery, phải dùng storage bền vững và test process/worker restart hoặc fault injection trước/sau ACK.

### 14.5. Kiểm tra dữ liệu email end-to-end

Một smoke test với sandbox SMTP/email provider có thể kiểm tra:
- SMTP connection/TLS credentials đúng, sender domain được chấp nhận.
- MIME/encoding, subject, HTML/plain-text fallback.
- Recipient test an toàn, tránh gửi thư thật ngoài ý muốn.
- Provider accepted webhook hoạt động và có xác thực.
- Bounce/complaint simulation và dữ liệu PII trong logs/queue được bảo vệ.

Dùng sandbox hoặc test inbox, không gửi hàng loạt đến người dùng thật trong test tự động.

## 15. Những lỗi triển khai phổ biến

1. **Gửi email ngay trong `@EventListener` trước commit:** có thể gửi cho order rollback.
2. **Gắn `@TransactionalEventListener` nhưng publish ngoài transaction:** callback không chạy vì fallback mặc định false.
3. **Cho rằng AFTER_COMMIT = asynchronous:** callback có thể block thread commit khi SMTP chậm.
4. **Cho rằng AFTER_COMMIT = durable:** process crash sau commit trước callback vẫn mất intent.
5. **Bắt exception mail rồi bỏ qua:** không có retry/alert, khách không được thông báo.
6. **Ném exception email sau commit rồi retry cả PlaceOrder:** tạo đơn/phụ phí/sự kiện trùng.
7. **Đánh dấu email SENT trước khi gửi:** crash trước request làm mất notification.
8. **Đánh dấu SENT sau gửi mà không có idempotency:** crash giữa hai bước có thể gửi email trùng.
9. **Dùng correlation ID làm email dedupe key:** nhiều email khác nhau trong workflow bị loại nhầm.
10. **Đưa JPA entity vào event:** mutable/lazy-loading, dữ liệu cũ và overexposure.
11. **Gửi email raw từ request input:** dễ sai recipient, thiếu ownership/tenant validation.
12. **Coi JavaMailSender.send là inbox delivered:** provider acceptance khác delivery.
13. **Đọc SecurityContext của request trong worker async:** context có thể vắng hoặc stale.
14. **Chỉ thêm `@Async` mà không có `@EnableAsync`/proxy:** method có thể không chạy async như mong đợi.
15. **Dùng queue executor không giới hạn:** có thể cạn memory khi provider chậm.
16. **Retry mọi SMTP 4xx/5xx giống nhau:** phân loại lỗi theo provider và policy.
17. **Không idempotent khi webhook lặp:** delivery status dễ cập nhật sai/nhân đôi effect.
18. **Không test rollback và crash window:** happy-path test che mất lỗ hổng thiết kế.
19. **Ghi full email body/recipient vào metrics/logs:** rủi ro PII và cardinality.
20. **Không định nghĩa business outcome:** dashboard “sent” có thể chỉ là accepted, không phải delivered.

## 16. Lựa chọn kiến trúc theo yêu cầu

| Yêu cầu | Giải pháp gợi ý | Giới hạn cần công bố |
| --- | --- | --- |
| Email phụ, có thể bỏ qua đôi lúc | AFTER_COMMIT listener trực tiếp | Có thể mất khi process crash/SMTP lỗi |
| Cần response nhanh, chấp nhận mất thông báo hiếm | AFTER_COMMIT → `@Async` | Executor queue trong RAM, cần error handling |
| Email xác nhận quan trọng, cần retry sau restart | Order + email outbox/job cùng transaction | Phải vận hành worker, lease, retry, dedupe |
| Nhiều service và email provider | Transactional outbox + broker/worker + provider adapter | At-least-once có thể gửi duplicate |
| Cần biết mail đã tới hộp thư | Provider delivery webhooks/status tracking | Accepted ≠ delivered; bounce/spam có hạn chế |
| Quyền/consent thay đổi trong thời gian chờ | Revalidation trong worker theo policy | Có thể từ chối email đã được lên lịch |
| Có retry command đặt đơn | Command-level idempotency + notification intent dedupe | Khác với provider-level idempotency |

Không có con số “luôn dùng async” hoặc “luôn dùng Kafka” đúng cho mọi sản phẩm. Chọn theo độ quan trọng, tính nhất quán, thời gian chờ, tài nguyên vận hành và mục tiêu phục hồi.

### Quy tắc thiết kế một câu

**Transaction tạo đơn quyết định business fact và ghi nhận ý định cần gửi; worker chịu trách nhiệm thực thi email với retry, idempotency và giám sát; kết quả email không được giả vờ là một phần atomic của transaction đặt đơn.**

## 17. Checklist triển khai thực tế

- [ ] Application service kiểm tra authentication, ownership/tenant, business invariant trước khi tạo đơn.
- [ ] Event `OrderCreatedEvent` mang ID và snapshot cần thiết, không chứa managed JPA entity.
- [ ] Biết rõ `@EventListener` thường có thể chạy trước commit.
- [ ] Nếu dùng `@TransactionalEventListener(AFTER_COMMIT)`, publish trong transaction thật.
- [ ] Đã test rollback thì email không gửi; ngoài transaction callback không chạy theo mặc định.
- [ ] Không nhầm AFTER_COMMIT với async hoặc durable delivery.
- [ ] Nếu dùng `@Async`, executor/`@EnableAsync`/proxy/error handling được cấu hình và kiểm thử.
- [ ] Nếu email quan trọng, lưu durable email job/outbox **cùng transaction** với đơn.
- [ ] Job có identity ổn định, unique constraint theo contract và trạng thái rõ ràng.
- [ ] Worker claim an toàn, retry/backoff/jitter, giới hạn attempts, quarantine và alert.
- [ ] Khi provider timeout không rõ kết quả, dùng cùng idempotency key hoặc reconciliation.
- [ ] Không hứa exactly-once email khi provider không hỗ trợ dedupe.
- [ ] Template chỉ dùng dữ liệu cần thiết, escape HTML và không lộ secrets.
- [ ] SMTP/provider credentials nằm trong secrets, không trong source/event/log.
- [ ] Consent/preferences và recipient được chọn theo policy nghiệp vụ.
- [ ] Logs/metrics/traces phân biệt order committed, send attempts, accepted và delivered.
- [ ] Test gồm commit, rollback, async completion, crash windows, duplicate, retry và provider webhooks.
- [ ] Có runbook xử lý job PENDING lâu, lỗi cấu hình, bounce và replay được cấp quyền.

**Kết luận:** Spring Framework Application Events là công cụ hữu ích để tách **tác vụ email** khỏi logic tạo đơn, đặc biệt khi dùng `@TransactionalEventListener(AFTER_COMMIT)` để tránh email cho transaction rollback. Nhưng để thông báo email **đáng tin cậy**, chỉ event in-memory hoặc `@Async` là chưa đủ: cần một **durable intent/outbox**, worker có retry, idempotency và observability. Thiết kế phải phân biệt rõ **đơn đã commit**, **mail provider đã nhận** và **người nhận đã nhận email**.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework 6.1.21 — TransactionalEventListener API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework 6.1.21 — TransactionTemplate API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework 6.1.21 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Boot — Sending Email](https://docs.spring.io/spring-boot/reference/io/email.html)
- [Spring Framework — Email Integration](https://docs.spring.io/spring-framework/reference/integration/email.html)
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html)
- [Idempotent Consumer Pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
