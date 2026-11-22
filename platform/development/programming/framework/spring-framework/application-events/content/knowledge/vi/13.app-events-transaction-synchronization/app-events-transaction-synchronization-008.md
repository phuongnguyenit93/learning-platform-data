# REQUIRES_NEW khi listener cần ghi dữ liệu

## 1. Vì sao ghi dữ liệu trong listener sau commit cần chú ý?

Giả sử `OrderService` lưu đơn hàng trong transaction **T1**, sau đó công bố `OrderCreatedEvent`. Ứng dụng dùng `@TransactionalEventListener` để chỉ ghi nhật ký (audit), cập nhật bảng thông báo hoặc tạo bản ghi tích hợp khi đơn hàng **đã commit thành công**.

~~~text
OrderService.createOrder()
    ├─ BEGIN T1
    ├─ INSERT orders
    ├─ publishEvent(OrderCreatedEvent)
    │      └─ đăng ký xử lý event theo transaction hiện tại
    └─ COMMIT T1 thành công
           └─ @TransactionalEventListener(AFTER_COMMIT)
                  └─ cần INSERT audit_log bằng transaction mới T2
                         ├─ BEGIN T2
                         ├─ INSERT audit_log
                         └─ COMMIT T2
~~~

**Bẫy:** tại thời điểm listener `AFTER_COMMIT` chạy, transaction T1 đã được commit, nhưng tài nguyên giao dịch (chẳng hạn JDBC connection hoặc persistence context) **có thể vẫn còn được gắn với thread** trước khi Spring hoàn tất dọn dẹp. Lệnh ghi dữ liệu gọi ngay trong callback có thể tiếp tục "tham gia" tài nguyên của giao dịch vừa kết thúc, **trong khi không còn lần commit tiếp theo** cho tài nguyên đó. Vì vậy, việc `save()` hoặc `jdbcTemplate.update()` chạy không báo lỗi **không bảo đảm dữ liệu sẽ được commit**.

Đây là cảnh báo trực tiếp trong Javadoc của `TransactionalEventListener` và `TransactionSynchronization`. Khi listener sau commit cần ghi dữ liệu một cách bền vững, phải bảo đảm thao tác ghi thực sự chạy trong **giao dịch độc lập, có commit riêng**, thường bằng `Propagation.REQUIRES_NEW`.

## 2. Phân biệt thời điểm xử lý event và propagation

`@TransactionalEventListener` chọn **thời điểm callback** so với transaction công bố event. `@Transactional(propagation = ...)` chọn **cách thiết lập transaction** cho phương thức thực hiện nghiệp vụ.

| Cấu hình | Ý nghĩa | Liên hệ với thao tác ghi |
| --- | --- | --- |
| `@EventListener` | Xử lý ngay khi event được phát, theo hành vi thông thường của multicaster | Nếu phát ngay trong T1 và listener chạy cùng thread, lệnh ghi có thể tham gia T1; nếu T1 rollback thì cùng rollback |
| `@TransactionalEventListener(phase = BEFORE_COMMIT)` | Xử lý trước khi commit T1 | Phù hợp khi muốn dữ liệu được ghi **trong T1** và thất bại phải khiến T1 không commit |
| `@TransactionalEventListener(phase = AFTER_COMMIT)` | Xử lý sau khi T1 commit thành công; đây là **mặc định** | Muốn ghi DB mới thì mở T2 bằng `REQUIRES_NEW` |
| `@TransactionalEventListener(phase = AFTER_ROLLBACK)` | Xử lý sau khi T1 rollback | Muốn ghi nhật ký thất bại còn tồn tại phải dùng giao dịch mới |
| `@TransactionalEventListener(phase = AFTER_COMPLETION)` | Xử lý sau khi T1 hoàn tất dù commit hoặc rollback | Nếu có ghi DB thì phải cân nhắc giao dịch độc lập và phân biệt trạng thái nghiệp vụ |

**Không nhầm:** `AFTER_COMMIT` **không tự tạo transaction mới**. `REQUIRES_NEW` **không khiến event đợi tới sau commit**. Hai hành vi đáp ứng hai yêu cầu khác nhau.

### REQUIRED và REQUIRES_NEW

- `Propagation.REQUIRED` (mặc định của `@Transactional`) sẽ tham gia transaction hiện có nếu Spring thấy một transaction phù hợp; trong callback sau commit, tài nguyên giao dịch cũ có thể vẫn còn được gắn với thread. Chỉ bọc lời gọi ghi bằng `@Transactional` mặc định **không phải** cách sửa an toàn.
- `Propagation.REQUIRES_NEW` tạo transaction vật lý mới, độc lập. Spring tạm ngưng ngữ cảnh giao dịch đang gắn với thread (nếu có), lấy tài nguyên cho transaction mới, rồi tự commit/rollback giao dịch đó.
- `Propagation.NESTED` dùng savepoint trong transaction vật lý hiện tại khi được hỗ trợ; nó không thay thế được yêu cầu **commit độc lập sau khi T1 đã commit**.

## 3. Mẫu triển khai khuyến nghị: listener gọi một service khác

Tách trách nhiệm thành ba bean Spring:

1. `OrderService` có `@Transactional`, tạo đơn hàng và phát event.
2. `OrderEventListener` có `@TransactionalEventListener(AFTER_COMMIT)`, xác định thời điểm xử lý.
3. `AuditWriter` có `@Transactional(propagation = Propagation.REQUIRES_NEW)`, thực hiện INSERT audit trong T2.

Mấu chốt là **listener gọi phương thức public trên một bean Spring khác** để lời gọi đi qua transactional proxy. Khi gọi `this.persistAudit(...)` trong cùng bean, ở chế độ proxy thông thường Spring không chặn được self-invocation, nên annotation `@Transactional` trên phương thức được gọi nội bộ có thể không có hiệu lực.

## 4. Ví dụ Java 17+ chạy được: commit tạo audit, rollback thì không

Ví dụ dưới đây dùng **Spring Framework 6.2.19**, Spring JDBC và H2 in-memory. Không cần Spring Boot; dùng `AnnotationConfigApplicationContext` để thấy rõ cấu hình transaction và event. Đây là dự án demo độc lập; các class được đặt cùng file cho tiện sao chép.

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'transactional-listener-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-jdbc:6.2.19'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.DemoApp'
}
~~~

Tạo `src/main/java/demo/DemoApp.java`:

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Configuration
@EnableTransactionManagement
@ComponentScan(basePackageClasses = DemoApp.class)
public class DemoApp {

    @Bean
    DataSource dataSource() {
        var source = new DriverManagerDataSource();
        source.setDriverClassName("org.h2.Driver");
        source.setUrl("jdbc:h2:mem:txevents;DB_CLOSE_DELAY=-1");
        source.setUsername("sa");
        source.setPassword("");
        return source;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(DemoApp.class)) {
            var jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("CREATE TABLE orders (id BIGINT PRIMARY KEY)");
            jdbc.execute(
                "CREATE TABLE audit_log (order_id BIGINT, detail VARCHAR(100))"
            );

            var orderService = context.getBean(OrderService.class);

            // T1 commit: listener AFTER_COMMIT tạo bản ghi audit bằng T2.
            orderService.createOrder(101L, false);

            // T1 rollback: listener AFTER_COMMIT không được gọi.
            try {
                orderService.createOrder(102L, true);
            } catch (IllegalStateException ex) {
                System.out.println("rolled back 102");
            }

            System.out.println("orders=" +
                jdbc.queryForObject("SELECT COUNT(*) FROM orders", Integer.class));
            System.out.println("audit=" +
                jdbc.queryForObject("SELECT COUNT(*) FROM audit_log", Integer.class));
        }
    }
}

// Event chỉ mang ID: listener tự truy vấn khi đã có giao dịch mới.
record OrderCreatedEvent(long orderId) {}

@Component
class OrderService {
    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher publisher;

    OrderService(JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
        this.jdbc = jdbc;
        this.publisher = publisher;
    }

    @Transactional
    public void createOrder(long orderId, boolean forceRollback) {
        jdbc.update("INSERT INTO orders (id) VALUES (?)", orderId);
        publisher.publishEvent(new OrderCreatedEvent(orderId));

        if (forceRollback) {
            throw new IllegalStateException("Simulated rollback");
        }
    }
}

@Component
class OrderEventListener {
    private final AuditWriter writer;

    OrderEventListener(AuditWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterOrderCommitted(OrderCreatedEvent event) {
        writer.writeAudit(event.orderId()); // Đi qua proxy của bean khác.
        System.out.println("audit saved for " + event.orderId());
    }
}

@Component
class AuditWriter {
    private final JdbcTemplate jdbc;

    AuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(long orderId) {
        jdbc.update(
            "INSERT INTO audit_log (order_id, detail) VALUES (?, ?)",
            orderId,
            "CREATED"
        );
    }
}
~~~

Chạy từ thư mục chứa `build.gradle`, với JDK 17+ và Gradle đã được cài, hoặc dùng Gradle Wrapper của dự án:

~~~bash
gradle run --quiet
# Hoặc: ./gradlew run --quiet
# Trên Windows: gradlew.bat run --quiet
~~~

Các dòng do chương trình tự in (có thể có thêm log từ môi trường chạy):

~~~text
audit saved for 101
rolled back 102
orders=1
audit=1
~~~

**Diễn giải kết quả:**

- **Đơn 101:** `OrderService.createOrder(101, false)` INSERT vào `orders` và phát event trong T1. Sau khi T1 commit, `OrderEventListener` mới gọi `AuditWriter`. `REQUIRES_NEW` bắt đầu T2, INSERT vào `audit_log` và commit T2. Kết quả là một đơn hàng và một bản ghi audit.
- **Đơn 102:** phương thức ném `IllegalStateException` trước commit; transaction interceptor rollback T1. Vì listener chỉ đăng ký `AFTER_COMMIT`, nó không xử lý event này. Không có đơn 102 và không có audit 102.
- **Điểm cần quan sát:** chương trình kiểm tra **dữ liệu đã commit bằng truy vấn riêng sau khi service hoàn thành**, thay vì chỉ nhìn thông báo "đã gọi save".

**Cơ chế liên quan:** Spring có thể công bố một object không kế thừa `ApplicationEvent`. Với trường hợp này Spring bao bọc payload để phát qua hạ tầng event; listener có thể nhận tham số đúng kiểu `OrderCreatedEvent`.

## 5. Vì sao viết thẳng vào DB trong AFTER_COMMIT là sai?

Đoạn sau là **ví dụ lỗi về thiết kế**, không đưa đồng thời vào demo ở mục 4:

~~~java
@Component
class UnsafeAuditListener {
    private final JdbcTemplate jdbc;

    UnsafeAuditListener(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @TransactionalEventListener // mặc định AFTER_COMMIT
    public void onOrderCreated(OrderCreatedEvent event) {
        jdbc.update(
            "INSERT INTO audit_log (order_id, detail) VALUES (?, ?)",
            event.orderId(), "CREATED"
        );
    }
}
~~~

Đoạn mã này **có thể chạy qua lệnh UPDATE mà không báo lỗi**, nhưng khi tài nguyên của transaction T1 còn gắn với callback, thao tác ghi có thể tham gia ngữ cảnh không còn lần commit nào. Không nên dựa vào việc một phiên bản JDBC/JPA hoặc một DB nào đó tình cờ làm lộ dữ liệu.

Một biến thể khác cũng dễ gây hiểu nhầm:

~~~java
@TransactionalEventListener
@Transactional // mặc định Propagation.REQUIRED
public void onOrderCreated(OrderCreatedEvent event) {
    repository.save(new AuditLog(event.orderId()));
}
~~~

Với Spring Framework hiện đại, cấu hình `@TransactionalEventListener` sau commit đồng thời dùng `@Transactional` nhưng **không phải** `REQUIRES_NEW` hoặc `NOT_SUPPORTED` còn có thể bị Spring từ chối ngay lúc đăng ký listener. Dù không bị từ chối ở một cấu hình cũ, `REQUIRED` vẫn không phải giao dịch ghi độc lập sau commit.

**Cách sửa:** giữ `AFTER_COMMIT` ở listener, gọi một service có `REQUIRES_NEW` (như ví dụ mục 4). Với thao tác JPA, đặt `repository.save(...)` trong service mới, không dựa vào phiên EntityManager vừa được dùng cho T1.

## 6. Điều kiện để REQUIRES_NEW thực sự có hiệu lực

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Listener gọi `this.saveAudit()` trên chính bean của nó | Self-invocation có thể đi vòng qua Spring proxy; tách service hoặc dùng `TransactionTemplate` |
| Phương thức ghi được gọi trên object tạo bằng `new` ngoài Spring | Không có proxy của Spring để mở transaction; lấy bean từ container |
| Bean/method không phù hợp với cơ chế proxy đang dùng | Dùng phương thức public có thể được intercept; tránh phụ thuộc vào private/final method trong proxy thông thường |
| Annotation chỉ nằm trên interface hoặc cấu hình proxy thay đổi | Xác nhận cách Spring phát hiện transaction metadata và kiểu proxy thực tế |
| Dùng nhiều database / transaction manager | Chọn đúng `PlatformTransactionManager` quản lý nguồn dữ liệu cần ghi; độc lập transaction không đồng nghĩa distributed transaction |
| Event phát ngoài transaction | Mặc định `@TransactionalEventListener` **không được gọi**, vì không có transaction phase để bám vào |
| Listener bị chạy bất đồng bộ | Thread transaction context không tự di chuyển qua thread khác; cần thiết kế ranh giới transaction rõ ràng trong luồng xử lý |

Nếu không muốn phụ thuộc vào proxy, có thể tạo transaction bằng lập trình bên trong listener/service qua `TransactionTemplate`:

~~~java
TransactionTemplate tx = new TransactionTemplate(transactionManager);
tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
tx.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "INSERT INTO audit_log (order_id, detail) VALUES (?, ?)",
        event.orderId(), "CREATED"
    );
});
~~~

Đây là **đoạn minh họa nhúng trong phương thức**; cần có biến `transactionManager`, `jdbcTemplate`, `event` thích hợp và import `org.springframework.transaction.support.TransactionTemplate` cùng `org.springframework.transaction.TransactionDefinition`. Nó không phải file Java chạy độc lập. Cách này đặc biệt hữu ích khi phải kiểm soát chính xác ranh giới transaction ngay trong callback.

## 7. Khi nào không nên dùng AFTER_COMMIT + REQUIRES_NEW?

**Yêu cầu nghiệp vụ phải cùng thành công hoặc cùng thất bại:** nếu bản ghi audit là phần bắt buộc của cùng một thao tác lưu đơn, muốn cả hai cùng rollback khi lỗi, hãy ghi audit **trong T1** (chẳng hạn trực tiếp từ service hoặc qua listener `BEFORE_COMMIT` với transaction phù hợp). `AFTER_COMMIT + REQUIRES_NEW` không bảo đảm tính nguyên tử giữa hai lệnh commit.

**Muốn ghi lại lỗi sau rollback:** dùng `AFTER_ROLLBACK` và mở transaction riêng để lưu failure log, nhưng cân nhắc không cho lỗi ghi log che mất nguyên nhân gốc.

**Muốn bảo đảm việc tích hợp được xử lý kể cả process chết:** callback `AFTER_COMMIT` là cơ chế trong bộ nhớ của process. T1 có thể đã commit rồi ứng dụng crash trước khi T2 hoàn thành; event và tác vụ audit/integration có thể mất. Với yêu cầu chuyển event sang hệ thống ngoài đáng tin cậy, hãy cân nhắc **transactional outbox**: ghi bản ghi outbox **trong T1**, sau đó worker độc lập đọc, giao tiếp và retry. `REQUIRES_NEW` không tự biến local event thành hàng đợi bền vững.

**Sợ xử lý lặp:** listener hoặc job retry có thể bị gọi lại; thiết kế lưu audit/inbox/outbox với khóa nghiệp vụ duy nhất hoặc thao tác idempotent nếu cần. `REQUIRES_NEW` chỉ bảo đảm transaction mới, **không bảo đảm exactly-once**.

**Bị giới hạn connection pool:** `REQUIRES_NEW` cần tài nguyên độc lập. Khi một giao dịch ngoài còn giữ connection và giao dịch trong phải lấy connection khác, pool quá nhỏ có thể hết connection hoặc gây chờ lẫn nhau. Tài liệu Spring khuyến nghị pool có dư ít nhất một connection so với số thread đồng thời trong mô hình đó. Demo dùng `DriverManagerDataSource` đơn giản, không dùng connection pool để tiện quan sát.

## 8. Checklist debug khi listener báo đã save nhưng DB không có dòng

1. Xác nhận method listener có thật sự chạy sau **commit thành công**: kiểm tra `phase` và xem transaction phát event có rollback không.
2. Kiểm tra event có được phát từ **transaction do Spring quản lý** không. Nếu không có transaction, listener mặc định bị bỏ qua; `fallbackExecution = true` đổi hành vi và phải được cân nhắc rõ.
3. Tìm log transaction (DEBUG cho `org.springframework.transaction`) để xem có mở **new transaction** và commit riêng ở phương thức ghi không. Log phụ thuộc transaction manager và cấu hình logging.
4. Xác nhận phương thức `REQUIRES_NEW` được gọi **qua proxy Spring**, chọn đúng transaction manager, không dùng self-invocation.
5. Đọc DB bằng transaction/connection khác **sau khi callback đã hoàn tất**. Đừng lấy log "repository.save() returned" làm bằng chứng commit.
6. Nếu thấy exception hoặc mất audit trong một phần request, nhớ rằng T1 đã commit thì lỗi T2 **không đảo ngược được T1**. Quyết định retry/ghi lỗi/cảnh báo theo yêu cầu nghiệp vụ.
7. Với JPA, kiểm tra `flush` và commit thực tế; `save` và `flush` không đồng nghĩa đã có commit độc lập.

### Tổng kết hành vi

~~~text
@Transactional publisher
    + @TransactionalEventListener(AFTER_COMMIT)
    + @Transactional service(REQUIRES_NEW)
    = Chạy listener sau khi T1 commit;
      thao tác ghi của listener có một T2 độc lập để commit.

AFTER_COMMIT không tự mở T2.
REQUIRES_NEW không đổi thời điểm kích hoạt listener.
Commit T2 không thể rollback hoặc "gộp lại" commit T1.
~~~

### Tài liệu chính thức

- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – Transaction Propagation, REQUIRES_NEW](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Javadoc – TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Javadoc – TransactionSynchronization.afterCompletion](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
