# Exception trong listener sau commit của Spring Framework: điều gì xảy ra với transaction đã hoàn tất?

## 1. Vấn đề cốt lõi

Giả sử service tạo đơn hàng trong một transaction và phát event:

```java
@Transactional
public void placeOrder(String id) {
    orderRepository.save(new Order(id));
    publisher.publishEvent(new OrderPlaced(id));
}
```

Một listener gửi email xác nhận sau commit:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendConfirmation(OrderPlaced event) {
    emailService.send(event.orderId());
}
```

Đây là các **đoạn minh họa**, chưa phải chương trình độc lập; `Order`, `OrderPlaced`, repository và email service do ứng dụng định nghĩa.

**Câu hỏi:** Nếu `emailService.send(...)` ném `RuntimeException` thì dòng đơn hàng trong DB có bị rollback? Caller có nhận được exception không? Có thể retry bằng cách gọi lại `placeOrder()` không?

Ba ý quan trọng:

1. **Transaction chính đã commit** trước khi listener `AFTER_COMMIT` chạy. Exception trong listener **không quay ngược được commit**.
2. Với `@TransactionalEventListener(AFTER_COMMIT)` trong cơ chế transaction synchronization imperative thông thường của Spring Framework, handler được kích hoạt tại pha **`afterCompletion(STATUS_COMMITTED)`**. Exception trong `afterCompletion` được Spring **ghi log nhưng không truyền lại caller** qua đường callback này. Do đó caller có thể thấy phương thức service kết thúc bình thường trong khi hậu xử lý đã thất bại.
3. Điều trên **khác** callback trực tiếp `TransactionSynchronization.afterCommit()`: exception từ `afterCommit()` trực tiếp **được truyền về caller của commit** theo API, nhưng dữ liệu chính đã commit và **vẫn không thể rollback nữa**.

Vì vậy, tuyệt đối không thiết kế quy tắc "nếu caller không thấy lỗi thì email chắc chắn đã gửi thành công". Cũng không nên gọi lại toàn bộ nghiệp vụ tạo đơn hàng khi chỉ phần hậu commit thất bại: cách đó dễ tạo duplicate order hoặc side effect trùng.

Bài này tập trung vào **Spring Framework Application Events** và transaction imperative quản lý bởi `PlatformTransactionManager`, ví dụ Spring JDBC/JPA. Với reactive transaction (`ReactiveTransactionManager`), transaction context và đường callback khác; cần áp dụng tài liệu reactive tương ứng.

## 2. Vòng đời transaction và vị trí của exception

Sự kiện `OrderPlaced` được phát *bên trong* transaction, nhưng listener gắn `AFTER_COMMIT` không lập tức xử lý:

```text
Caller
  |
  v
@Transactional OrderService.placeOrder()
  |
  +-- BEGIN T1
  +-- INSERT order
  +-- publishEvent(OrderPlaced)
  |      |
  |      +-- đăng ký TransactionalEventListener cho T1
  |
  +-- return từ phần thân method
  |
  +-- COMMIT T1 thành công
  |
  +-- callback hoàn tất T1 với STATUS_COMMITTED
  |      |
  |      +-- @TransactionalEventListener(AFTER_COMMIT)
  |             |
  |             +-- gửi email / gọi API / ghi audit
  |             |
  |             +-- có thể NÉM EXCEPTION
  |                    |
  |                    +-- được ghi log trong đường afterCompletion
  |                    +-- KHÔNG rollback T1
  |
  +-- cleanup transaction resources
  |
  v
Caller tiếp tục; không nhất thiết nhận lỗi hậu commit
```

**Lưu ý:** Không nên gọi chính xác `@TransactionalEventListener(AFTER_COMMIT)` là "Spring gọi `TransactionSynchronization.afterCommit()`". Về **ý nghĩa nghiệp vụ**, cả hai diễn ra sau commit thành công, nhưng **đường callback và quy tắc lan truyền exception khác nhau**. Spring sử dụng `TransactionalApplicationListenerSynchronization` để xử lý các pha event; với pha `AFTER_COMMIT` của listener annotation, event được xử lý tương ứng trạng thái `STATUS_COMMITTED` trong `afterCompletion(...)`.

Sự khác biệt này giải thích vì sao code kiểm thử hoặc logging có thể cho kết quả bất ngờ: bạn thấy một stack trace từ listener trong log, nhưng method `placeOrder()` vẫn trở về bình thường.

## 3. So sánh exception giữa các pha của transaction

| Nơi xảy ra exception | Dữ liệu T1 đã commit chưa? | Tác động thường gặp |
| --- | --- | --- |
| Trong phần thân `@Transactional` trước commit | Chưa | Unchecked exception thoát qua proxy thường khiến T1 rollback theo quy tắc mặc định |
| `@EventListener` đồng bộ được gọi khi publish event bên trong T1 | Chưa | Nếu exception thoát đến ranh giới `@Transactional`, T1 có thể rollback |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Chưa | Exception được truyền trong commit path; có thể ngăn commit và khiến rollback |
| `@TransactionalEventListener(AFTER_COMMIT)` | **Đã commit** | T1 không rollback; trong cơ chế after-completion thông thường exception được log, không propagate tới caller |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | T1 đã rollback | Exception không hoàn tác kết quả rollback, thường được log ở completion callback |
| `@TransactionalEventListener(AFTER_COMPLETION)` | T1 đã hoàn tất | Không thể đổi kết quả transaction; exception xử lý theo completion callback |
| **Trực tiếp** `TransactionSynchronization.afterCommit()` | **Đã commit** | Runtime exception có thể **propagate tới caller của commit**, nhưng không rollback T1 |
| Trực tiếp `TransactionSynchronization.afterCompletion(...)` | Đã hoàn tất | Runtime exception được ghi log, không propagate qua cơ chế callback chuẩn |

**Điểm phân biệt:** `AFTER_COMMIT` là thời điểm tương đối với transaction; không có nghĩa "lỗi lúc này sẽ rollback". Quy tắc propagation của exception còn phụ thuộc vào **API callback chính xác** đang được dùng.

Tài liệu `TransactionSynchronization` nói rõ:
- `afterCommit()` có thể truyền `RuntimeException` về caller.
- `afterCompletion(int)` log `RuntimeException` mà không truyền về caller.
- Sau commit/rollback, tài nguyên transaction có thể vẫn còn truy cập được; nếu cần ghi DB mới thì dùng transaction độc lập, thường là `PROPAGATION_REQUIRES_NEW`.

## 4. Ví dụ tối thiểu: một listener ném exception

```java
@Component
class OrderEvents {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void whenOrderCommitted(OrderPlaced event) {
        System.out.println("after commit listener invoked");
        throw new IllegalStateException("mail server unavailable");
    }
}
```

Đây là **mã minh họa**, yêu cầu `OrderPlaced`, Spring-managed bean và một event đã phát trong transaction.

Khi service được gọi qua transaction proxy, nó commit T1 thành công rồi Spring xử lý callback. Một triển khai chuẩn của Spring Framework có thể ghi log mức `ERROR` với thông tin tương tự:

```text
TransactionSynchronization.afterCompletion threw exception
java.lang.IllegalStateException: mail server unavailable
```

Đây là **dạng log minh họa**, không phải chuỗi output bắt buộc chính xác: logger, phiên bản, cấu hình và stack trace có thể khác nhau.

**Không đọc log để kết luận T1 rollback.** Cần truy vấn dữ liệu sau transaction để xác minh T1 có được commit hay không. Với lỗi hậu commit, có thể tồn tại đồng thời:

```text
orders có bản ghi mới = true
email đã gửi thành công = false
caller nhận exception = false
```

Trạng thái thứ ba phụ thuộc callback cụ thể; đối với `@TransactionalEventListener(AFTER_COMMIT)` tiêu chuẩn chạy qua completion callback đồng bộ, lỗi thường được log và không truyền tới caller. Nếu ứng dụng dùng listener fallback, executor hoặc event infrastructure tùy biến, phải kiểm tra đường xử lý thực tế.

## 5. Ví dụ Java 17+ chạy được: lỗi bị log và lỗi được ghi nhận bằng transaction mới

Ví dụ đầy đủ dưới đây dùng **Spring Framework 6.2.12**, **Spring JDBC**, H2 in-memory và Gradle; không dùng Spring Boot. Nó mô phỏng external notification thất bại trong cả hai đơn hàng:

- **Đơn A:** listener ném `IllegalStateException` khỏi phương thức `AFTER_COMMIT`. Spring log exception qua đường `afterCompletion`; transaction tạo đơn hàng đã commit, caller vẫn kết thúc bình thường trong cấu hình này.
- **Đơn B:** listener bắt exception, gọi `FailureAuditWriter` qua Spring bean proxy với `@Transactional(REQUIRES_NEW)`, lưu một bản ghi `failure_audit` trong transaction thứ hai, rồi hoàn tất callback bình thường.
- Kết quả được kiểm tra bằng truy vấn DB sau mỗi lời gọi; không suy luận từ việc exception được ném ở một thread nào đó.

### 5.1. Cấu trúc thư mục

```text
after-commit-errors-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AfterCommitErrorsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'after-commit-errors-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.AfterCommitErrorsDemo'
}
```

Yêu cầu JDK 17+ và Gradle đã cài. `DriverManagerDataSource` được dùng cho bài thực hành ngắn; trong môi trường production cần connection pool có giới hạn, timeout và quan sát mức sử dụng.

### 5.2. `src/main/java/demo/AfterCommitErrorsDemo.java`

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class AfterCommitErrorsDemo {

    public record OrderPlaced(String orderId, boolean recordFailure) {}

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
        public void place(String id, boolean recordFailure) {
            jdbc.update("insert into orders (id) values (?)", id);
            publisher.publishEvent(new OrderPlaced(id, recordFailure));
        }
    }

    public static class FailureAuditWriter {
        private final JdbcTemplate jdbc;

        public FailureAuditWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void saveFailure(String orderId, String reason) {
            jdbc.update(
                    "insert into failure_audit (order_id, reason) values (?, ?)",
                    orderId, reason);
        }
    }

    public static class NotificationListener {
        private final FailureAuditWriter auditWriter;

        public NotificationListener(FailureAuditWriter auditWriter) {
            this.auditWriter = auditWriter;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("listener attempted: " + event.orderId());

            try {
                // Mô phỏng hệ thống gửi notification đang gặp lỗi.
                throw new IllegalStateException("notification unavailable");
            } catch (IllegalStateException ex) {
                if (event.recordFailure()) {
                    // T2: transaction mới sau khi đơn hàng T1 đã commit.
                    auditWriter.saveFailure(
                            event.orderId(), ex.getMessage());
                    return;
                }

                // Trường hợp A: cho exception thoát khỏi listener.
                throw ex;
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                    "jdbc:h2:mem:after_commit_errors;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        FailureAuditWriter failureAuditWriter(JdbcTemplate jdbc) {
            return new FailureAuditWriter(jdbc);
        }

        @Bean
        NotificationListener notificationListener(
                FailureAuditWriter auditWriter) {
            return new NotificationListener(auditWriter);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService orders = context.getBean(OrderService.class);

            jdbc.execute(
                    "create table orders (id varchar(40) primary key)");
            jdbc.execute(
                    "create table failure_audit ("
                    + "order_id varchar(40) primary key, "
                    + "reason varchar(100) not null)");

            // A: listener ném exception trong AFTER_COMMIT.
            orders.place("A", false);
            System.out.println("service A returned");
            System.out.println("after A: orders=" + count(jdbc, "orders")
                    + ", audits=" + count(jdbc, "failure_audit"));

            // B: listener bắt lỗi và ghi audit qua REQUIRES_NEW.
            orders.place("B", true);
            System.out.println("service B returned");
            System.out.println("after B: orders=" + count(jdbc, "orders")
                    + ", audits=" + count(jdbc, "failure_audit"));
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        // table chỉ nhận hai tên hằng trong main(), không nhận input user.
        return jdbc.queryForObject(
                "select count(*) from " + table, Integer.class);
    }
}
```

Chạy:

```bash
gradle -q run
```

Các dòng **do chương trình chủ động in bằng `System.out.println`**, theo thứ tự:

```text
listener attempted: A
service A returned
after A: orders=1, audits=0
listener attempted: B
service B returned
after B: orders=2, audits=1
```

Ngoài sáu dòng trên, console **có thể xuất hiện log lỗi và stack trace** từ Spring khi listener A ném exception:

```text
TransactionSynchronization.afterCompletion threw exception
java.lang.IllegalStateException: notification unavailable
```

Đây là đoạn log đại diện, **không** phải phần stdout có định dạng cố định. Nó không thay đổi sáu dòng `System.out.println` phía trên.

### 5.3. Vì sao cả hai đơn hàng vẫn tồn tại?

**Trường hợp A:**

1. `context.getBean(OrderService.class)` lấy service qua Spring transaction proxy. `place("A", false)` bắt đầu transaction T1.
2. Service INSERT `orders(A)` rồi phát `OrderPlaced("A", false)` trong T1.
3. Listener `AFTER_COMMIT` được đăng ký chờ kết quả T1; nó **không chạy ngay khi publish**.
4. T1 commit thành công. Sau đó listener `onOrderPlaced` chạy, in `listener attempted: A` rồi ném `IllegalStateException`.
5. Spring ghi nhận exception trong completion callback và log lỗi; T1 **đã commit**, không rollback. Với đường này, `orders.place(...)` vẫn trở về và main in `service A returned`.
6. Truy vấn sau đó xác nhận `orders=1`, `audits=0`. Chương trình không tự động có bản ghi audit khi chỉ log exception.

**Trường hợp B:**

1. Tạo `orders(B)` trong transaction mới T1-B, rồi phát event với `recordFailure=true`.
2. T1-B commit. Listener hậu commit mô phỏng lỗi notification.
3. Listener **bắt** lỗi và gọi **một bean khác** `FailureAuditWriter.saveFailure(...)`, có `@Transactional(REQUIRES_NEW)`. Spring tạo transaction mới T2 để INSERT `failure_audit(B, reason)`.
4. T2 commit độc lập; listener return bình thường. Sau khi caller trở về, truy vấn DB xác nhận `orders=2`, `audits=1`.
5. Hai đơn hàng `A` và `B` tồn tại vì **cả hai transaction tạo đơn đều commit**; chỉ đơn B có bản ghi lỗi audit vì nó được xử lý và lưu bền vững qua T2.

**Giới hạn của ví dụ:** `REQUIRES_NEW` chứng minh lưu một **bản ghi lỗi DB** sau commit. Nó **không bảo đảm** tác vụ notification được retry hoặc hoàn thành. Muốn có retry, cần thêm worker, trạng thái và cơ chế thực thi lại. Nếu DB của T2 cũng thất bại, phải có chính sách lỗi riêng; không thể lặng lẽ coi notification đã hoàn tất.

## 6. Đừng nhầm `afterCommit()` trực tiếp với `@TransactionalEventListener(AFTER_COMMIT)`

Hai đường thường bị gộp chung trong giải thích sơ lược:

### 6.1. Callback trực tiếp từ `TransactionSynchronization`

```java
TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            throw new IllegalStateException("direct callback error");
        }
    });
```

Đây là **mã minh họa**, phải được gọi khi transaction synchronization đang hoạt động; cần import `TransactionSynchronization` và `TransactionSynchronizationManager`.

Theo hợp đồng của `TransactionSynchronization.afterCommit()`, runtime exception từ callback trực tiếp **được propagate** về caller của commit. Thậm chí nếu caller nhìn thấy exception, dữ liệu chính có thể **đã commit**. Nếu caller vô điều kiện retry toàn bộ command vì thấy exception, có nguy cơ tạo dữ liệu trùng.

### 6.2. Listener `@TransactionalEventListener`

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    throw new IllegalStateException("listener callback error");
}
```

Đây là **mã minh họa**. Trong cơ chế implementation tiêu chuẩn của Spring Framework sử dụng `afterCompletion(STATUS_COMMITTED)`, exception do listener ném thường **được log và không propagate** tới caller. Kết quả T1 vẫn commit.

### 6.3. Kết luận thực hành

| API | Callback chạy khi nào? | Exception runtime đi đâu? | T1 có rollback được không? |
| --- | --- | --- | --- |
| Trực tiếp `TransactionSynchronization.afterCommit()` | Sau commit | Có thể propagate tới commit caller | **Không**, T1 đã commit |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit, qua completion callback | Được log, không propagate trong đường callback chuẩn | **Không**, T1 đã commit |
| Trực tiếp `TransactionSynchronization.afterCompletion(status)` | Sau commit/rollback | Log, không propagate trong helper chuẩn | **Không**, transaction đã hoàn tất |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Trước commit | Có thể propagate và làm thất bại commit | **Có thể**, vì T1 chưa commit |

Điểm cốt lõi không phải caller có nhìn thấy exception hay không. **Sự thật dữ liệu là transaction đã commit**, do đó việc phát lại/bù trừ phải được thiết kế như một **nghiệp vụ riêng**, không phải rollback tự động.

## 7. Vì sao `@Transactional(REQUIRED)` chưa đủ khi ghi DB sau commit?

Một sai lầm phổ biến là cho rằng listener hậu commit cứ gọi repository với `@Transactional` mặc định thì Spring sẽ tự mở một giao dịch mới:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    auditRepository.save(...);
}
```

Đây là đoạn minh họa, không phải chương trình độc lập. Sau commit, tài nguyên như JDBC `Connection`/JPA persistence context có thể **vẫn gắn với thread** cho tới khi cleanup. Spring Javadoc cảnh báo code truy cập DB lúc này có thể tham gia tài nguyên transaction cũ trong khi **không còn commit theo sau**, nên thao tác ghi mới **không được lưu đúng kỳ vọng**.

Để cần một commit DB mới, sử dụng:

```java
@Service
public class AuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId, String errorMessage) {
        // Insert audit row / update trạng thái retry.
    }
}
```

Đây là mã minh họa. Gọi `auditWriter.record(...)` **qua Spring-managed bean khác** để đi qua transaction proxy. `REQUIRES_NEW` tạo một transaction vật lý độc lập, tự commit hoặc rollback. Không dùng `this.record(...)` trong cùng bean nếu đang dùng chế độ proxy mặc định: self-invocation bỏ qua transactional advice.

Một lựa chọn tương đương ở mức lập trình là `TransactionTemplate` cấu hình `TransactionDefinition.PROPAGATION_REQUIRES_NEW`. Đây là cách hữu ích khi cần kiểm soát transaction tường minh từ callback mà không muốn dùng proxy riêng.

**Quan trọng:** Nếu listener đã hoàn tất T1 nhưng chưa cleanup tài nguyên, `REQUIRES_NEW` có thể cần một JDBC connection khác. Connection pool production phải được sizing theo concurrency; không xem việc mở transaction mới là miễn phí.

## 8. Bắt exception trong listener có đủ để bảo đảm công việc không mất?

**Không.** `try/catch` chỉ giúp bạn quyết định **làm gì tại thời điểm lỗi xuất hiện**. Nó không tự bảo đảm lỗi sẽ được lưu, task sẽ được retry, hoặc process sống đủ lâu để xử lý.

Mẫu thích hợp cho tác vụ hậu commit best-effort:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handle(OrderPlaced event) {
    try {
        mailClient.sendOrderConfirmation(event.orderId());
    } catch (RuntimeException ex) {
        metrics.counter("order.notification.failed").increment();
        log.error("Notification failed for order {}", event.orderId(), ex);
    }
}
```

Đây là đoạn mã minh họa; `mailClient`, `metrics`, `log` là dependency ứng dụng. Nó giúp **quan sát** lỗi nhưng không tạo bản ghi công việc để phục hồi. Nếu listener nuốt exception mà không log/metric, failure sẽ trở nên vô hình.

Mẫu có lưu yêu cầu retry sau lỗi:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handle(OrderPlaced event) {
    try {
        mailClient.sendOrderConfirmation(event.orderId());
    } catch (RuntimeException ex) {
        retryWriter.recordForRetry(
                event.orderId(), ex.getClass().getSimpleName());
    }
}
```

Đây cũng là mã minh họa; `retryWriter` là **một bean khác** có `@Transactional(REQUIRES_NEW)`, dùng để lưu công việc cần retry. Ngoài ra cần có một worker đọc bảng retry, thực thi lại với backoff, đánh dấu thành công/thất bại và tránh xử lý trùng.

**Cửa sổ lỗi vẫn tồn tại:** Nếu JVM chết sau T1 commit nhưng trước khi listener hoặc `retryWriter` chạy, **không có bản ghi retry**. Vì vậy mẫu bắt lỗi + T2 **chỉ cải thiện khả năng phục hồi khi lỗi thực sự được quan sát**, không bảo đảm chống mất công việc trong mọi trường hợp.

## 9. Transactional outbox: khi lỗi hậu commit không được phép làm mất tác vụ

Với công việc quan trọng (gửi thông báo pháp lý, đồng bộ kế toán, phát sự kiện sang broker, lập hóa đơn), transaction chính cần commit cùng **ý định thực hiện công việc**. Một cách thường dùng là **transactional outbox**:

```text
BEGIN transaction T1
  |
  +-- INSERT đơn hàng
  +-- INSERT outbox(orderId, eventId, payload, status=NEW)
  |
COMMIT T1
  |
  +-- worker riêng đọc outbox đã commit
       |
       +-- gọi email / broker / external service
       |
       +-- thành công -> đánh dấu DONE
       +-- thất bại  -> lưu retry_count, next_attempt_at
       |
       +-- retry với backoff, idempotency và dead-letter
```

Outbox bảo đảm **bản ghi nghiệp vụ và bản ghi yêu cầu xử lý tiếp** được commit hoặc rollback cùng nhau. Khi process chết sau commit, worker vẫn có thể tiếp tục từ bản ghi outbox. Cơ chế này không tự bảo đảm exactly-once delivery; ngoại vi có thể đã nhận side effect trước khi worker kịp đánh dấu DONE, nên retries có thể gửi trùng.

Cần thiết kế:

- `eventId`/idempotency key gửi kèm request nếu hệ thống ngoài hỗ trợ.
- Unique constraint hoặc trạng thái đã xử lý để tránh tạo tác vụ trùng.
- Retry chỉ với lỗi tạm thời; backoff và giới hạn số lần.
- Dead-letter/quarantine cho lỗi cấu hình hoặc payload không hợp lệ.
- Monitoring số pending/failed, tuổi lớn nhất của tác vụ, độ trễ và retry rate.
- Chiến lược xử lý khi hệ thống ngoài đã thành công nhưng cập nhật trạng thái local thất bại.

**Outbox khác `@TransactionalEventListener(AFTER_COMMIT)`**: callback chỉ có lịch chạy trong tiến trình; outbox có **bản ghi DB đã commit** để phục hồi qua crash. Có thể kết hợp cả hai (callback kích worker xử lý sớm), nhưng worker vẫn phải đọc outbox bền vững chứ không coi callback là nguồn chân lý.

## 10. Không retry toàn bộ service chỉ vì lỗi hậu commit

Giả sử T1 đã commit `orders(O-7)` nhưng gửi email thất bại. Nếu hệ thống gọi lại:

```java
orderService.place("O-7");
```

thì có thể gặp duplicate key hoặc tạo thêm một đơn hàng thứ hai nếu ID được sinh mới. Ngay cả khi service idempotent, những side effect khác có thể lặp.

**Hãy retry tác vụ bị lỗi**, không mặc định retry command gốc. Ví dụ:

```text
Order service: COMMITTED order O-7
Notification: FAILED to send for O-7

Retry target:
  sendNotification(orderId="O-7", notificationId="...")
not:
  createOrderAgain(...)
```

Khi thiết kế API:

- Tách trạng thái **đơn hàng đã tạo** và **notification đang chờ/đã gửi/thất bại**.
- Nếu API trả 200 sau khi T1 commit, đừng hứa thông báo đã gửi trừ khi có bằng chứng hoàn tất.
- Nếu API phải thể hiện lỗi phần phụ, trả hoặc cung cấp trạng thái async rõ ràng (ví dụ `notificationStatus=PENDING`), không đổi một transaction đã commit thành "transaction failed".
- Nếu callback trực tiếp `TransactionSynchronization.afterCommit()` ném exception làm request nhận lỗi, caller vẫn cần idempotency và phân biệt trạng thái DB thực tế trước khi retry.
- Dùng correlation ID nối giữa request, transaction, outbox task và external request.

Việc tái gửi email/HTTP có thể thành công ở hệ thống ngoài nhưng client gặp timeout. Khi retry, dùng idempotency key hoặc kiểm tra trạng thái, tránh gửi trùng.

## 11. `@Async` làm đường exception khác đi

Một listener có thể đồng thời là async và transaction-bound:

```java
@Async("notificationExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handle(OrderPlaced event) {
    mailClient.sendOrderConfirmation(event.orderId());
}
```

Đây là đoạn minh họa, cần `@EnableAsync`, bean executor phù hợp và Spring-managed listener. Spring đăng ký callback theo transaction ở thread publisher; sau commit, async advice có thể đưa phần xử lý sang worker thread.

Khi listener async `void` ném exception:

- Exception xảy ra trong **worker thread**, không phải stack gọi ban đầu của publisher.
- `AsyncUncaughtExceptionHandler` hoặc logging là kênh quan sát thông thường cho uncaught exception.
- Không tự truyền exception về transaction gốc để rollback.
- Không nên kỳ vọng `TransactionSynchronization.afterCompletion` bắt được exception xảy ra **sau** khi executor nhận task; callback transaction có thể đã hoàn tất phần scheduling.
- Executor rejection **ngay lúc submit** cũng là một loại lỗi cần giám sát riêng.
- Thread worker không tự thừa hưởng JDBC/JPA transaction của publisher. Nếu ghi DB từ worker, mở transaction phù hợp trong một service được proxy.
- `@Async` không làm event bền vững; task có thể mất do shutdown/crash nếu không có persistent queue.

Ví dụ cấu hình handler bất đồng bộ (mã minh họa):

```java
@Configuration
@EnableAsync
public class AsyncErrorConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (error, method, args) ->
                System.err.println(
                        "async failure: " + method.getName()
                                + ": " + error.getMessage());
    }
}
```

Cần import `Configuration`, `EnableAsync`, `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`. Trong production, thay `System.err` bằng structured logs, metrics, tracing và recovery có kiểm soát.

**Cẩn thận với tên lỗi:** "listener bị lỗi sau commit" có thể chỉ exception trong **callback đồng bộ** hoặc exception trong **worker async** được lên lịch sau commit. Hai đường báo lỗi khác nhau nhưng đều **không thể rollback dữ liệu T1 đã commit**.

## 12. Listener chưa chắc chạy nếu không có transaction

`@TransactionalEventListener` mặc định là `AFTER_COMMIT`, nhưng chỉ đăng ký theo transaction khi sự kiện được phát trong ngữ cảnh transaction phù hợp. Khi không có transaction:

- Mặc định `fallbackExecution=false`: listener **bị bỏ qua**.
- `fallbackExecution=true`: listener có thể chạy theo đường fallback **không gắn commit thật**.

Ví dụ:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void handle(OrderPlaced event) {
    // Có thể chạy không có transaction.
}
```

Đây là mã minh họa, không phải mã đầy đủ. Nếu listener chạy bằng fallback trong khi **không có transaction**, không được tiếp tục giả định exception của nó được xử lý giống hệt một `afterCompletion(STATUS_COMMITTED)` của transaction thật. Do đó bài kiểm thử phải phân biệt hai đường này.

Một số nguyên nhân event tưởng ở trong transaction nhưng thực ra không:

- Gọi method `@Transactional` từ chính cùng bean bằng `this.method()` nên bỏ qua transaction proxy.
- Tạo bean bằng `new` thay vì Spring quản lý.
- Publish event từ thread async khác trước commit: thread mới không tự thừa hưởng context transaction imperative.
- Test chưa thực sự commit hoặc dùng transaction manager không đúng.

Với application reactive, transaction ở Reactor Context; cần dùng API publisher/context theo tài liệu Spring reactive thay vì giả định `ThreadLocal`.

## 13. Kiểm thử và xác minh exception sau commit

### 13.1. Những test nên có

1. **T1 commit, listener ném exception:** xác minh order vẫn tồn tại trong DB sau lời gọi.
2. **Quan sát caller:** với listener `@TransactionalEventListener(AFTER_COMMIT)` chuẩn, xác minh caller có thể hoàn thành bình thường dù framework log lỗi trong completion callback; không kiểm tra log bằng chuỗi message quá cụ thể.
3. **Callback trực tiếp `afterCommit()`:** kiểm tra exception có thể lan tới caller nhưng T1 vẫn commit. Không được nhầm hai API.
4. **T1 rollback trước commit:** listener `AFTER_COMMIT` không chạy.
5. **Listener bắt lỗi:** khi handler bắt exception và gọi `REQUIRES_NEW`, bản ghi lỗi được commit độc lập.
6. **Lỗi khi ghi audit T2:** gây rollback T2; xác minh T1 đã commit và hệ thống theo dõi lỗi audit.
7. **Async listener:** dùng `CountDownLatch`/future/Awaitility với timeout để chờ; không dựa vào `Thread.sleep()` ngẫu nhiên.
8. **No transaction / fallback:** kiểm tra `fallbackExecution=false` bỏ qua event; kiểm thử riêng `fallbackExecution=true`.
9. **Process crash / retry:** test tích hợp outbox để xác minh worker khôi phục công việc chưa xử lý sau restart.
10. **Idempotency:** phát lại cùng một event; không tạo bản ghi audit/notification trùng hoặc tạo đơn hàng mới.

### 13.2. Tránh test `@Transactional` chỉ rollback tự động

Trong Spring Test, method test `@Transactional` thường bị rollback vào cuối test theo mặc định. Nếu một test phát event bên trong transaction rồi assert ngay sau publish, `AFTER_COMMIT` **chưa chạy**; nếu transaction test cuối cùng rollback, listener **không chạy**.

Có thể dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` trong một test được Spring quản lý transaction để chủ động commit rồi assert:

```java
TestTransaction.flagForCommit();
TestTransaction.end();

// Sau khi commit, kiểm tra DB và kết quả hậu commit.
```

Đây là **đoạn minh họa**, cần Spring Test và import `org.springframework.test.context.transaction.TestTransaction`. Ngoài ra có thể viết integration test không bao phương thức test bằng một transaction mặc định, để lời gọi service của bạn tự commit trước khi assert.

**Bằng chứng đúng:** kiểm tra dữ liệu persisted trong database/quan sát trạng thái task, không chỉ dựa vào việc có log exception, method return hoặc một biến boolean còn nằm trong thread khác.

## 14. Những lỗi phổ biến và cách sửa

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Listener `AFTER_COMMIT` ném exception nhưng order vẫn tồn tại | Transaction T1 đã commit trước khi callback chạy | Đây là ngữ nghĩa đúng; xử lý lỗi hậu commit như tác vụ độc lập |
| Caller không nhận exception dù có stack trace trong log | Handler chạy qua `afterCompletion(STATUS_COMMITTED)`; exception bị log trong callback helper | Dùng metrics/retry/task status, không dựa vào exception caller |
| Callback `afterCommit()` tự viết làm request báo lỗi nhưng DB có record | Callback trực tiếp propagate exception sau commit | Đọc trạng thái thực tế, thiết kế idempotency; không retry blindly |
| Ghi audit trong listener nhưng DB không lưu | Tài nguyên transaction cũ còn bound, không có commit mới | Gọi bean `@Transactional(REQUIRES_NEW)` hoặc `TransactionTemplate` tương đương |
| `REQUIRES_NEW` không có tác dụng | Self-invocation qua `this`, bean không được proxy | Tách service thành Spring bean được inject |
| Listener `AFTER_COMMIT` không chạy | Event không phát trong transaction hoặc T1 rollback | Xác minh transaction thật và mặc định `fallbackExecution=false` |
| Async listener lỗi nhưng publisher không hay biết | Lỗi phát sinh trên executor thread | `AsyncUncaughtExceptionHandler`, logs, metrics và persistent retry |
| `catch` lỗi nhưng notification vẫn mất sau crash | Chưa có persisted work cùng T1 | Transactional outbox hoặc durable queue |
| Email được gửi hai lần khi retry | Không có idempotency key | Dedupe theo event ID/notification ID |
| Worker không hoàn thành sau restart | Chỉ dùng in-memory Application Event | Persisted outbox/task store và worker có checkpoint |
| Test không nhận event after-commit | Test transaction chưa commit hoặc rollback tự động | Chủ động commit/kết thúc transaction test trước assertion |
| Bị cạn connection khi T2 ghi audit | `REQUIRES_NEW` có thể cần connection độc lập | Tính connection pool size, concurrency và timeout |

## 15. Checklist thiết kế listener sau commit

Trước khi triển khai một tác vụ hậu commit, trả lời:

- **T1 đã commit ở mốc nào?** Hiểu rằng `@TransactionalEventListener(AFTER_COMMIT)` không chạy cùng transaction còn có thể rollback.
- **Exception được ai thấy?** `@TransactionalEventListener(AFTER_COMMIT)` chuẩn khác callback trực tiếp `TransactionSynchronization.afterCommit()`.
- **Thành công của T1 có độc lập với side effect hậu commit không?** Nếu có, thể hiện trạng thái riêng như `PENDING`, `SUCCEEDED`, `FAILED`.
- **Lỗi cần lưu ở đâu?** Nếu ghi DB sau commit, mở transaction mới bằng `REQUIRES_NEW`.
- **Process chết sau T1 commit thì sao?** Nếu không được mất công việc, ghi outbox trong chính T1 rồi xử lý bằng worker bền vững.
- **Retry có an toàn không?** Retry **side effect bị lỗi**, không mặc định lặp lại cả command đã commit; có idempotency key.
- **Listener chạy sync hay async?** Chính sách exception, thread, executor, backpressure và shutdown cần tương ứng.
- **Test đã xác minh DB thật chưa?** Không chỉ kiểm tra log hoặc exception caller.

**Kết luận:** Exception trong listener sau commit **không thể rollback transaction đã commit**. Đặc biệt với `@TransactionalEventListener(AFTER_COMMIT)` trong Spring Framework imperative, lỗi được phát sinh qua completion callback thường được ghi log mà **không truyền về caller**, trong khi callback `TransactionSynchronization.afterCommit()` trực tiếp có cơ chế propagation khác. Hãy quản lý tác vụ hậu commit như một **bước độc lập có trạng thái, quan sát lỗi, transaction riêng và cơ chế phục hồi**, thay vì cố gắng áp dụng rollback hoặc retry toàn bộ nghiệp vụ gốc.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — `TransactionSynchronization.afterCommit()` và `afterCompletion()`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework source — `TransactionalApplicationListenerSynchronization`](https://github.com/spring-projects/spring-framework/blob/v6.2.12/spring-tx/src/main/java/org/springframework/transaction/event/TransactionalApplicationListenerSynchronization.java)
- [Spring Framework source — `TransactionSynchronizationUtils`](https://github.com/spring-projects/spring-framework/blob/v6.2.12/spring-tx/src/main/java/org/springframework/transaction/support/TransactionSynchronizationUtils.java)
- [Spring Framework — Transaction Propagation and `REQUIRES_NEW`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Rollback rules](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
