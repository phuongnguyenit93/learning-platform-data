# Lỗi trong @TransactionalEventListener

## 1. Vì sao lỗi trong transaction-bound listener nguy hiểm?

`@TransactionalEventListener` gắn việc xử lý **application event** với một *phase* của transaction đã công bố event. Điều này rất hữu ích để thực hiện logic trước commit hoặc sau khi kết quả giao dịch đã rõ, nhưng **một exception trong listener không phải lúc nào cũng có cùng hậu quả**.

Ví dụ, `OrderService` ghi đơn hàng trong transaction T1 và phát `OrderPlaced`. Sau đó:

- Listener `BEFORE_COMMIT` kiểm tra một điều kiện bắt buộc rồi ném lỗi: **T1 có thể bị rollback** vì lỗi xảy ra trước commit.
- Listener `AFTER_COMMIT` gửi thông báo rồi ném lỗi: **T1 đã commit, không thể rollback T1 chỉ vì listener lỗi**.
- Listener `AFTER_ROLLBACK` ghi log thất bại nhưng chính nó lỗi: T1 **đã rollback**; không thể “rollback lần nữa” hay khôi phục giao dịch gốc.
- Nếu event được phát **ngoài transaction** và `fallbackExecution = false` (mặc định), listener **không chạy**, nên không có lỗi từ method listener đó trong lần phát event ấy.

Sơ đồ:

~~~text
@Transactional OrderService.create()
    |
    +-- BEGIN T1
    +-- INSERT orders
    +-- publishEvent(OrderPlaced)
    |      (đăng ký transaction synchronization)
    |
    +-- BEFORE_COMMIT listener
    |      +-- thành công ------------------------------+
    |      +-- ném RuntimeException -> rollback T1     |
    |                                                   |
    +-- COMMIT T1 <-------------------------------------+
    |      |
    |      +-- AFTER_COMMIT listener
    |              +-- lỗi ở đây KHÔNG đảo ngược commit T1
    |
    +-- ROLLBACK T1 (nếu transaction thất bại)
           |
           +-- AFTER_ROLLBACK listener
                   +-- lỗi ở đây KHÔNG làm T1 rollback thêm
~~~

**Mục tiêu học tập:** phân biệt lỗi có ảnh hưởng đến quyết định commit với lỗi xảy ra khi giao dịch đã hoàn tất; hiểu đường đi của exception ở Spring Framework; thiết kế xử lý lỗi hậu commit mà không tạo cảm giác an toàn giả.

## 2. Bốn phase và ảnh hưởng của exception

| Phase của `@TransactionalEventListener` | Thời điểm chạy | Nếu listener ném RuntimeException trong transaction imperative chuẩn |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trong callback `TransactionSynchronization.beforeCommit(...)`, trước khi commit | Exception có thể được truyền đến tiến trình commit, khiến T1 **rollback**; caller có thể thấy lỗi |
| `AFTER_COMMIT` (**mặc định**) | Trong callback `afterCompletion(STATUS_COMMITTED)` của cơ chế transactional event | **T1 đã commit**. Exception được transaction synchronization utility ghi log, thông thường **không truyền ngược lên caller** |
| `AFTER_ROLLBACK` | Trong callback `afterCompletion(STATUS_ROLLED_BACK)` | **T1 đã rollback**; lỗi handler được ghi log, không biến rollback thành commit |
| `AFTER_COMPLETION` | Trong `afterCompletion(...)` khi transaction hoàn tất, dù commit/rollback | Kết quả transaction đã được xác định; lỗi handler được ghi log, không làm thay đổi kết quả ấy |

Đây là hành vi của **Spring Framework 6.2 với transaction imperative tiêu chuẩn**, ví dụ `DataSourceTransactionManager`. Nó dựa trên cách Spring triển khai `TransactionalApplicationListenerSynchronization` và gọi các callback `TransactionSynchronization`.

### Điểm tinh tế: AFTER_COMMIT không đồng nghĩa trực tiếp với afterCommit()

Tên phase `AFTER_COMMIT` dễ khiến ta nghĩ method listener chạy bên trong `TransactionSynchronization.afterCommit()`. Nhưng trong triển khai transactional event của Spring 6.2, Spring đăng ký:

~~~java
// Pseudocode mô tả phần cơ chế dispatch, không phải API public để gọi:
beforeCommit(...) {
    if (phase == BEFORE_COMMIT) processEvent();
}

afterCompletion(status) {
    if (phase == AFTER_COMMIT && status == STATUS_COMMITTED)
        processEvent();
    else if (phase == AFTER_ROLLBACK && status == STATUS_ROLLED_BACK)
        processEvent();
    else if (phase == AFTER_COMPLETION)
        processEvent();
}
~~~

Do đó, cần phân biệt hai API callback:

- `TransactionSynchronization.afterCommit()`: exception dạng `RuntimeException` **có thể truyền tới caller** dù DB đã commit.
- `TransactionSynchronization.afterCompletion(int)`: exception được Spring **ghi log nhưng không truyền tiếp** trong tiến trình callback tiêu chuẩn.

`@TransactionalEventListener(AFTER_COMMIT)` trên đường đi imperative nêu trên thuộc **trường hợp thứ hai**. Tránh viết tài liệu hoặc test khẳng định “exception tại `AFTER_COMMIT` luôn khiến caller nhận lỗi”. Hành vi có thể khác nếu ứng dụng tự viết transaction manager, dispatch, error handler hoặc gọi handler thủ công.

Nguồn gốc trong Spring 6.2: `TransactionalApplicationListenerSynchronization.PlatformSynchronization` và `TransactionSynchronizationUtils.invokeAfterCompletion(...)`, xem đường dẫn tài liệu cuối bài.

### BEFORE_COMMIT không phải bảo đảm commit sẽ thành công

`BEFORE_COMMIT` được gọi **trước** commit nên nó có thể thất bại và khiến transaction rollback. Nhưng **listener chạy thành công không bảo đảm T1 chắc chắn sẽ commit**. Commit vẫn có thể thất bại vì database constraint, network, deadlock, transaction bị đánh dấu rollback-only hoặc lỗi ở bước khác.

Vì thế, **không gửi email, không thanh toán thẻ, không phát message không thể thu hồi từ `BEFORE_COMMIT`** nếu hệ thống cần bảo đảm side effect chỉ xảy ra sau khi giao dịch đã commit.

## 3. Event được phát khi nào, listener thật sự chạy khi nào?

Phân biệt ba mốc:

1. `ApplicationEventPublisher.publishEvent(event)` được gọi **bên trong T1**.
2. Với `@TransactionalEventListener` có transaction phù hợp, Spring **đăng ký synchronization** tại thời điểm phát event. Method listener chưa nhất thiết chạy ngay.
3. Khi T1 đến phase đã cấu hình, Spring gọi method listener.

~~~text
service:
  transaction BEGIN
  INSERT
  publishEvent(event)    -> đăng ký phase callback
  return from method
  transaction interceptor:
      beforeCommit -> commit/rollback -> afterCompletion
           |
           +-- method @TransactionalEventListener được gọi đúng phase
~~~

Do đó, exception trong `BEFORE_COMMIT` có thể xuất hiện **sau khi method service đã chạy hết thân**, ở bước transaction interceptor xử lý commit. Nếu service có:

~~~java
@Transactional
public void placeOrder() {
    repository.save(...);
    publisher.publishEvent(new OrderPlaced(...));
    System.out.println("service body finished");
}
~~~

Dòng “service body finished” có thể đã được in **trước khi** listener `BEFORE_COMMIT` ném lỗi và T1 rollback. Log “service đã chạy đến cuối method” không phải bằng chứng transaction đã commit.

Ngược lại, `AFTER_COMMIT` có thể chạy sau khi DB commit nhưng trước khi transaction manager hoàn tất cleanup. Một exception trong method listener ở thời điểm này không làm dữ liệu đã commit tự quay trở lại trạng thái cũ.

## 4. Ví dụ Java 17+ chạy được: ba loại lỗi, hai kết quả DB

Ví dụ sử dụng **Spring Framework 6.2.19**, Spring JDBC và H2 in-memory. Không cần Spring Boot. Bốn scenario được chạy tuần tự:

1. Đơn 101: các listener thành công -> T1 commit.
2. Đơn 102: listener `BEFORE_COMMIT` ném lỗi -> T1 rollback; caller bắt exception.
3. Đơn 103: listener `AFTER_COMMIT` ném lỗi -> T1 đã commit; lỗi được Spring log; caller không bắt được lỗi theo đường đi `afterCompletion` tiêu chuẩn.
4. Đơn 104: chính service ném lỗi -> T1 rollback; listener `AFTER_ROLLBACK` vẫn chạy.

### Cấu trúc dự án

~~~text
transactional-event-errors/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/TransactionEventErrorDemo.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'transactional-event-errors'
~~~

Tệp `build.gradle`:

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
    mainClass = 'demo.TransactionEventErrorDemo'
}
~~~

Tệp `src/main/java/demo/TransactionEventErrorDemo.java`:

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
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Configuration
@EnableTransactionManagement
@ComponentScan(basePackageClasses = TransactionEventErrorDemo.class)
public class TransactionEventErrorDemo {

    @Bean
    DataSource dataSource() {
        var ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:listener_errors;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource ds) {
        return new DataSourceTransactionManager(ds);
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                TransactionEventErrorDemo.class)) {

            JdbcTemplate db = ctx.getBean(JdbcTemplate.class);
            db.execute("CREATE TABLE orders (id BIGINT PRIMARY KEY)");

            OrderService service = ctx.getBean(OrderService.class);

            // A: T1 commit bình thường.
            service.place(101L, Scenario.OK);

            // B: BEFORE_COMMIT lỗi, caller nhận exception.
            try {
                service.place(102L, Scenario.FAIL_BEFORE_COMMIT);
            } catch (IllegalStateException ex) {
                System.out.println("caller caught before 102");
            }

            // C: AFTER_COMMIT lỗi, DB đã commit.
            // Với default Spring synchronization callback,
            // exception được log; dòng này không cần catch.
            service.place(103L, Scenario.FAIL_AFTER_COMMIT);

            // D: chính service yêu cầu rollback.
            try {
                service.place(104L, Scenario.FAIL_IN_SERVICE);
            } catch (IllegalArgumentException ex) {
                System.out.println("caller caught service 104");
            }

            Integer count = db.queryForObject(
                "SELECT COUNT(*) FROM orders", Integer.class);
            System.out.println("committed orders=" + count);
        }
    }
}

enum Scenario {
    OK,
    FAIL_BEFORE_COMMIT,
    FAIL_AFTER_COMMIT,
    FAIL_IN_SERVICE
}

record OrderPlaced(long orderId, Scenario scenario) {}

@Component
class OrderService {
    private final JdbcTemplate db;
    private final ApplicationEventPublisher publisher;

    OrderService(JdbcTemplate db, ApplicationEventPublisher publisher) {
        this.db = db;
        this.publisher = publisher;
    }

    @Transactional
    public void place(long id, Scenario scenario) {
        db.update("INSERT INTO orders (id) VALUES (?)", id);
        publisher.publishEvent(new OrderPlaced(id, scenario));

        if (scenario == Scenario.FAIL_IN_SERVICE) {
            throw new IllegalArgumentException("service failed");
        }
    }
}

@Component
class OrderListeners {

    @TransactionalEventListener(
        phase = TransactionPhase.BEFORE_COMMIT)
    public void beforeCommit(OrderPlaced event) {
        System.out.println("before commit " + event.orderId());

        if (event.scenario() == Scenario.FAIL_BEFORE_COMMIT) {
            throw new IllegalStateException("before listener failed");
        }
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderPlaced event) {
        System.out.println("after commit " + event.orderId());

        if (event.scenario() == Scenario.FAIL_AFTER_COMMIT) {
            throw new IllegalStateException("after listener failed");
        }
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(OrderPlaced event) {
        System.out.println("after rollback " + event.orderId());
    }
}
~~~

Chạy trong thư mục dự án với JDK 17+ và Gradle; nếu đã có Gradle Wrapper có thể dùng wrapper:

~~~bash
gradle run --quiet
# Linux/macOS: ./gradlew run --quiet
# Windows: gradlew.bat run --quiet
~~~

**Những dòng do chương trình chủ động in ra qua `System.out`** (log ERROR từ Spring ở tình huống 103 có thể xuất hiện xen giữa, thậm chí gồm stack trace):

~~~text
before commit 101
after commit 101
before commit 102
after rollback 102
caller caught before 102
before commit 103
after commit 103
after rollback 104
caller caught service 104
committed orders=2
~~~

Giải thích từng scenario:

| Đơn | Listener nào chạy? | Kết quả DB | Caller nhìn thấy gì? |
| --- | --- | --- | --- |
| 101 | BEFORE_COMMIT, AFTER_COMMIT | Commit | Return bình thường |
| 102 | BEFORE_COMMIT ném lỗi; AFTER_ROLLBACK | Rollback | `IllegalStateException` (được bắt) |
| 103 | BEFORE_COMMIT; AFTER_COMMIT ném lỗi | **Đã commit** | Trên callback `afterCompletion` tiêu chuẩn, Spring **log lỗi**; caller không nhận exception từ listener này |
| 104 | AFTER_ROLLBACK; không chạy BEFORE_COMMIT | Rollback | `IllegalArgumentException` từ service (được bắt) |

**Điểm dễ kiểm tra bằng dữ liệu:** cuối chương trình `committed orders=2`, gồm đơn **101 và 103**. Lỗi listener sau commit **không làm đơn 103 biến mất**. Đơn 102 và 104 không tồn tại vì T1 của chúng rollback.

**Cảnh báo về stdout:** demo không ấn định cấu hình logging. Stack trace lỗi `after listener failed` do Spring ghi ra có thể dài và tùy môi trường. Các dòng trong khối output là các dòng tự in bởi demo, không phải toàn bộ console output.

## 5. Vì sao exception AFTER_COMMIT có thể chỉ xuất hiện trong log?

Trong triển khai imperative Spring 6.2:

1. `@TransactionalEventListener(AFTER_COMMIT)` đăng ký `TransactionSynchronization`.
2. Sau khi commit thực tế, Spring gọi `afterCompletion(STATUS_COMMITTED)`.
3. Synchronization của transactional event gọi listener; listener ném exception.
4. `TransactionSynchronizationUtils.invokeAfterCompletion(...)` bắt `Throwable` từ mỗi callback và **ghi log ERROR**; tiến trình cleanup vẫn tiếp tục.
5. Kết quả commit chính của T1 vẫn là thành công.

Điều này có hai hệ quả:

- **Không dùng `try/catch` quanh `service.place()` như cơ chế duy nhất để biết mọi hậu xử lý `AFTER_COMMIT` thất bại.** Trong demo, caller không thấy lỗi hậu commit 103 qua exception.
- **Không coi “service return thành công” là “mọi listener đã hoàn thành thành công”.** Thành công của T1 và thành công của side effect sau T1 là hai trạng thái riêng.

### Ngoại lệ đối với những đường thực thi khác

Bảng trên không đồng nghĩa mọi exception của mọi loại listener Spring đều bị nuốt:

- Một `@EventListener` **thông thường** chạy đồng bộ trong `publishEvent(...)` có thể ném lỗi ngay ở thời điểm publish; nếu lỗi lan khỏi service, transaction đang hoạt động có thể bị rollback.
- Với `fallbackExecution = true` khi **không có transaction**, transactional listener có thể được gọi ngay; lúc ấy nó không còn là callback `afterCompletion` của một T1, nên cơ chế lan lỗi phụ thuộc đường dispatch và cấu hình multicaster.
- `TransactionSynchronization.afterCommit()` viết **trực tiếp** là API khác; exception ở callback đó có thể truyền cho caller dù commit đã hoàn tất.
- Một listener có `@Async`, custom multicaster/executor hoặc error handler sẽ có cơ chế xử lý lỗi riêng; lỗi async không thể được giả định truyền về thread đã gọi publish.
- Trong **reactive transaction** (Spring 6.1+), transaction context nằm trong Reactor Context và phase callback có thể chạy qua `Mono`. Exception có thể ảnh hưởng đến tín hiệu reactive khác với đường imperative; cần kiểm chứng với `ReactiveTransactionManager` và cách subscribe cụ thể, không áp quy tắc nuốt lỗi của `TransactionSynchronizationUtils` (imperative) một cách máy móc.

Với hệ thống production, cần phân biệt và test **loại transaction manager**, **phase**, **cách listener chạy**, **đường xử lý exception**.

## 6. Lỗi BEFORE_COMMIT có ý nghĩa khác lỗi AFTER_COMMIT

Chọn `BEFORE_COMMIT` khi thao tác của listener **phải là một phần của quyết định giao dịch**:

~~~java
@Component
class InvariantCheckListener {

    @TransactionalEventListener(
        phase = TransactionPhase.BEFORE_COMMIT)
    public void validate(OrderPlaced event) {
        if (violatesBusinessInvariant(event)) {
            throw new IllegalStateException("Cannot commit order");
        }
    }

    private boolean violatesBusinessInvariant(OrderPlaced event) {
        // Pseudocode: logic thực phải dựa trên nghiệp vụ của ứng dụng.
        return false;
    }
}
~~~

Đây là **đoạn minh họa bean**, không phải file chạy độc lập. Nó làm rõ ý nghĩa phase chứ không thay thế việc kiểm tra business invariant trong aggregate/service.

**Tại sao không đưa hết business validation vào event listener?** Quy tắc cốt lõi thường nên được thực thi **trước hoặc trong lúc cập nhật aggregate**, nơi luồng nghiệp vụ dễ kiểm soát. Dùng listener `BEFORE_COMMIT` cho cross-cutting validation hoặc thao tác bổ sung phải cùng transaction khi thực sự phù hợp; tránh chuyển bất biến domain sang một callback khó nhìn thấy.

Nếu một listener `BEFORE_COMMIT` ghi dữ liệu trong cùng T1 rồi ném lỗi, những thay đổi đó cũng có thể rollback theo T1 khi dùng cùng transaction resource. Nhưng nếu listener đã gọi **HTTP API, gửi email, hoặc mở `REQUIRES_NEW` để commit độc lập** trước khi ném lỗi, rollback T1 **không tự hoàn tác** các side effect bên ngoài đó.

## 7. Ghi audit hoặc log lỗi ở AFTER_ROLLBACK cần transaction mới

Ví dụ: đặt hàng thất bại, ứng dụng muốn lưu `order_failure_log` để điều tra. Listener `AFTER_ROLLBACK` là một hook hợp lý về thời điểm, nhưng transaction gốc **đã kết thúc**. Trong quá trình callback, tài nguyên transaction cũ có thể vẫn còn gắn với thread; thao tác `save()` trực tiếp không bảo đảm có commit mới.

Mẫu khuyến nghị:

~~~java
@Component
class FailureListener {
    private final FailureAuditWriter writer;

    FailureListener(FailureAuditWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK)
    public void onFailure(OrderPlaced event) {
        writer.persistFailure(event.orderId());
    }
}

@Component
class FailureAuditWriter {
    private final FailureLogRepository repository;

    FailureAuditWriter(FailureLogRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void persistFailure(long orderId) {
        repository.save(new FailureLog(orderId));
    }
}
~~~

Đoạn này **không chạy độc lập**, vì `FailureLogRepository` và `FailureLog` là kiểu phụ thuộc vào ứng dụng và cần import `Propagation`, `Transactional`, các stereotype annotation. Điểm chính là listener gọi một **bean khác qua Spring proxy** để `REQUIRES_NEW` thực sự mở T2.

Lưu ý:

- T2 có commit/rollback riêng. Nếu T2 thất bại, rollback T1 **không đổi**, và lỗi có thể được Spring log trong callback `afterCompletion`.
- `this.persistFailure()` gọi ngay trong cùng bean thường bỏ qua proxy transaction; đừng dùng self-invocation để trông đợi `REQUIRES_NEW`.
- Nếu cần audit **đảm bảo tồn tại ngay cả khi hệ thống crash**, một callback sau rollback vẫn có thể mất. Nên xác định thêm nguồn lỗi bền vững, transaction riêng, hàng đợi hoặc cơ chế lưu audit phù hợp. Outbox ghi *trong T1* cũng sẽ rollback cùng T1, vì vậy nó **không tự ghi lại một lỗi transaction đã rollback**.

## 8. Có nên catch exception ngay trong listener?

Không có một cách catch chung cho mọi nghiệp vụ. Hãy bắt lỗi **khi listener thật sự có chính sách phục hồi**. Ví dụ:

~~~java
// Minh họa: có cấu hình retry/monitoring thực tế trong ứng dụng.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommitted(OrderPlaced event) {
    try {
        notificationGateway.enqueue(event.orderId());
    } catch (TransientGatewayException ex) {
        metrics.counter("order_notification_failure").increment();
        errorReporter.report(event.orderId(), ex);
        // Có thể đánh dấu cần retry ở hệ thống bền vững.
    }
}
~~~

Đoạn mã này minh họa **ngữ cảnh một listener có dependency**, không phải Java độc lập. Nếu `metrics` hoặc `errorReporter` cũng lỗi, vẫn cần chính sách xử lý rõ ràng. Việc ghi metrics hoặc log **không tự tạo lại một thông báo đã thất bại**.

Các lựa chọn:

| Nhu cầu | Chiến lược phù hợp |
| --- | --- |
| Công việc bắt buộc trước commit; lỗi phải rollback T1 | Thực hiện cùng T1, có thể dùng `BEFORE_COMMIT` khi đúng thiết kế |
| Công việc không ảnh hưởng dữ liệu đã commit | `AFTER_COMMIT` và giám sát lỗi rõ ràng |
| Side effect sau commit có thể retry | Chuyển giao cho worker/job hoặc message transport bền vững, idempotent |
| Không được mất event khi process crash | **Transactional outbox** ghi cùng transaction nghiệp vụ |
| Ghi log lỗi sau rollback | T2 độc lập `REQUIRES_NEW` hoặc kênh ghi bền vững khác |
| Muốn rollback cả DB khi email lỗi | Không thể bảo đảm atomicity chỉ bằng callback sau commit; cần thiết kế lại quy trình hoặc cơ chế phân tán phù hợp |

### Vì sao không chỉ retry ngay trong method listener?

Một số lỗi tạm thời (timeout, connection reset) có thể phù hợp với retry có giới hạn, backoff và idempotency. Nhưng retry **đồng bộ bên trong callback** cũng có rủi ro:

- Giữ request/transaction completion lâu hơn cần thiết.
- Gửi cùng side effect nhiều lần nếu timeout xảy ra sau khi hệ thống đích đã thực hiện thành công.
- Vẫn mất toàn bộ công việc còn chờ nếu process chết.
- Trong `AFTER_COMPLETION`, lỗi cuối cùng có thể chỉ được ghi log nên caller không tự biết cần bù trừ.

Với tích hợp đáng tin cậy, outbox + worker retry thường phù hợp hơn “catch rồi gọi lại vài lần trong listener”.

## 9. Nếu nhiều listener cùng xử lý event thì lỗi ảnh hưởng thế nào?

Không nên giả định một event có đúng một handler. Ví dụ `OrderPlaced` có:

~~~text
OrderPlaced
    +-- BEFORE_COMMIT: kiểm tra chính sách
    +-- AFTER_COMMIT : ghi audit
    +-- AFTER_COMMIT : enqueue notification
    +-- AFTER_ROLLBACK: ghi thông tin lỗi
~~~

Các tình huống:

- Lỗi ở một `BEFORE_COMMIT` callback có thể làm quá trình commit dừng, do đó những callback cùng phase chưa chạy **có thể không được gọi** và T1 rollback.
- Lỗi ở một `afterCompletion` callback trong đường imperative tiêu chuẩn được ghi log, và util tiếp tục duyệt các synchronization khác. **Không** nên dựa vào thứ tự listener để bảo đảm nghiệp vụ, trừ khi thiết kế và kiểm thử rõ.
- `@Order` có thể thay đổi thứ tự ưu tiên giữa các listener/synchronization, nhưng **không đổi được thực tế T1 đã commit hay rollback** và không làm exception sau commit có khả năng undo T1.
- Listener lỗi có thể đã thực hiện **một phần side effect** trước khi ném exception. Khi xử lý lại phải thiết kế idempotency (ví dụ unique key theo event ID).
- Nếu dùng custom `applicationEventMulticaster` hoặc listener bất đồng bộ, lifecycle và chính sách exception cần được kiểm chứng trong môi trường thực.

### Lỗi khi publish event ngoài transaction

Mặc định, `fallbackExecution = false`:

~~~java
@TransactionalEventListener
public void onPlaced(OrderPlaced event) { ... }
~~~

Nếu `publishEvent(...)` xảy ra **ngoài transaction phù hợp**, callback transaction-bound bị bỏ qua. Không có exception vì listener không chạy.

Có thể bật:

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void onPlacedEvenWithoutTx(OrderPlaced event) { ... }
~~~

Nhưng khi chạy ngoài transaction, **không thể hiểu đây là after-commit**; listener chạy theo đường fallback. Nếu việc không có transaction là lỗi lập trình, đừng dùng fallback để che khuất nó. Nên đảm bảo publisher nằm trong transaction được quản lý hoặc dùng API công bố trực tiếp khác theo use case.

## 10. Kiểm thử exception và rollback cho @TransactionalEventListener

Một bộ test tốt phải kiểm tra **cả exception quan sát được lẫn dữ liệu commit/rollback thực tế**:

| Test | Cần assert |
| --- | --- |
| BEFORE_COMMIT listener ném `RuntimeException` | Caller có thể nhận lỗi; dòng dữ liệu T1 không tồn tại; AFTER_COMMIT không chạy |
| AFTER_COMMIT listener ném `RuntimeException` | Dữ liệu T1 **vẫn tồn tại**; lỗi handler được phát hiện qua logging/monitoring, không kết luận dựa vào `assertThrows` ở caller |
| Service ném exception trước commit | T1 rollback; AFTER_ROLLBACK được gọi, nếu event đã được publish trong T1 |
| AFTER_ROLLBACK listener ném lỗi | Không đổi kết quả T1; error reporting vẫn phải phát hiện lỗi callback |
| Event phát ngoài transaction | Mặc định listener không chạy; kiểm thử riêng khi bật `fallbackExecution` |
| Listener hậu commit gọi T2 `REQUIRES_NEW` nhưng T2 rollback | T1 vẫn tồn tại; T2 không có dữ liệu; cơ chế retry/alert vận hành |
| Có nhiều callback sau completion | Xác định callback nào được gọi và log lỗi trong cấu hình cụ thể |

**Lưu ý về `@Transactional` trong test:** một bài test `@Transactional` có thể bị framework test rollback mặc định khi kết thúc; callback `AFTER_COMMIT` của test đó sẽ không chạy như kỳ vọng, trừ khi test cấu hình commit. Với integration test, có thể dùng `TestTransaction.flagForCommit()`/`end()` hoặc kiểm soát giao dịch ngoài test và đọc DB sau completion. Đừng lấy việc test luôn rollback làm kết luận listener bị lỗi.

**Ghi log:** trong hệ thống dùng Logback/Log4j2, có thể bật DEBUG cho `org.springframework.transaction` và theo dõi ERROR tại `TransactionSynchronizationUtils`. Log giúp phát hiện exception bị ghi nhận nhưng không truyền về caller; cần kết hợp metric/alert đối với tác vụ quan trọng.

## 11. Checklist chẩn đoán sự cố

Khi thấy “đơn hàng đã lưu nhưng listener báo lỗi”, hãy kiểm tra:

1. **Listener dùng phase nào?** `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` hay `AFTER_COMPLETION`?
2. **Dữ liệu T1 thực sự commit chưa?** Đọc DB bằng connection/transaction độc lập sau khi service hoàn tất.
3. **Exception xảy ra trong thân service, khi publish, trước commit hay sau completion?** Stack trace và timing giúp phân biệt.
4. **Caller có bắt được exception không?** Với AFTER_COMMIT qua afterCompletion imperative, thường không; cần quan sát log/metric.
5. **Event có được phát trong transaction không?** Không có transaction và không bật fallback thì listener không chạy.
6. **Listener có chạy async không?** Nếu có, lỗi ở thread/task khác và transaction context không tự được truyền.
7. **Listener có ghi DB sau commit/rollback không?** Nếu có, kiểm tra transaction mới và proxy `REQUIRES_NEW`, đừng tin chỉ `repository.save()` trả về bình thường.
8. **Nếu handler lỗi, task có được retry không?** Có kênh bền vững, idempotency, dead-letter hoặc cảnh báo phù hợp?
9. **Có nhiều listener không?** Thứ tự `@Order`, ngoại lệ callback trước và sau completion có thể khác nhau.
10. **Transaction manager/kiểu ứng dụng nào?** JDBC/JPA imperative khác R2DBC reactive; cần test đúng implementation.

### Ghi nhớ

~~~text
BEFORE_COMMIT exception
    -> Có thể làm T1 rollback; caller có thể nhận lỗi.

AFTER_COMMIT exception
    -> T1 đã commit; lỗi không tự undo T1.
    -> Với Spring 6.2 imperative @TransactionalEventListener:
       chạy qua afterCompletion, thường được log, không rethrow.

AFTER_ROLLBACK exception
    -> T1 đã rollback; lỗi của handler không thay đổi kết quả.

Muốn đảm bảo hậu xử lý:
    -> Không chỉ rely vào try/catch của caller.
    -> Thiết kế retry/idempotency, outbox hoặc workflow bền vững.
~~~

## Tài liệu chính thức

- [Spring Framework 6.2 – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [TransactionalEventListener – Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [TransactionSynchronization – Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring source – TransactionalApplicationListenerSynchronization](https://github.com/spring-projects/spring-framework/blob/6.2.x/spring-tx/src/main/java/org/springframework/transaction/event/TransactionalApplicationListenerSynchronization.java)
- [Spring source – TransactionSynchronizationUtils](https://github.com/spring-projects/spring-framework/blob/6.2.x/spring-tx/src/main/java/org/springframework/transaction/support/TransactionSynchronizationUtils.java)
