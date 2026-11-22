# Exception trong listener đồng bộ: lỗi lan truyền và rollback trong Spring Application Events

Trong Spring Framework Application Events, một method `@EventListener` **đồng bộ** không hoạt động như một message consumer được tách biệt khỏi caller. Với cấu hình mặc định, `ApplicationEventPublisher.publishEvent(...)` kích hoạt các listener trên **cùng thread**, trước khi lời gọi `publishEvent` kết thúc. Nếu listener ném exception và không có cơ chế xử lý lỗi nào chặn lại, exception có thể đi ngược về nơi phát event. Điều này đặc biệt quan trọng nếu event được publish **bên trong một database transaction**: lỗi của một listener có thể làm nghiệp vụ chính rollback.

Bài học tập trung vào câu hỏi: exception của listener đồng bộ đi đâu, có chặn listener khác không, khi nào DB rollback, điều gì xảy ra nếu bắt lỗi hoặc cấu hình `ErrorHandler`, và làm sao kiểm thử chính xác kết quả.

## 1. Mô hình thực thi mặc định

Trong một `ApplicationContext` Spring điển hình, bộ phát sự kiện là `SimpleApplicationEventMulticaster`. Theo mặc định, nó thực thi listener đồng bộ trong caller thread và **không có `ErrorHandler`**.

~~~text
OrderService.createOrder()
    |
    +-- INSERT order                       [transaction có thể đang mở]
    |
    +-- applicationEventPublisher.publishEvent(OrderCreated)
           |
           +-- listener A @EventListener   [cùng thread]
           |      +-- thao tác nghiệp vụ
           |      +-- throw IllegalStateException(...)
           |
           +-- listener B                   [thường không được gọi
           |                                  nếu lỗi A chưa xử lý]
           |
           +-- exception đi ngược về publishEvent()
    |
    +-- exception có thể đi tiếp ra transaction interceptor
           |
           +-- quyết định commit/rollback theo rollback rules
~~~

Điểm cần nhớ: `publishEvent` **không có nghĩa “bỏ vào hàng đợi và trả về ngay”** ở cấu hình mặc định. Nếu một listener chạy chậm, publisher bị chậm. Nếu listener đồng bộ ném unchecked exception, publisher có thể nhận chính exception đó.

Khi nói “listener sau không chạy”, đó là ngữ nghĩa của **cùng một lần multicast đồng bộ với cấu hình mặc định, lỗi chưa được xử lý**. Không suy diễn nó sang hệ thống đã cấu hình executor, `ErrorHandler`, hoặc nhiều context có topology khác nhau.

| Thuộc tính | Mặc định thường gặp | Ý nghĩa |
| --- | --- | --- |
| `ApplicationEventPublisher.publishEvent(event)` | Gọi multicaster của context | Không trả kết quả từ các listener |
| `SimpleApplicationEventMulticaster` | Đồng bộ nếu không cấu hình `TaskExecutor` | Publisher và listener dùng cùng thread |
| `ErrorHandler` | Không có | Exception chưa xử lý làm dừng lần multicast và lan về publisher |
| `@EventListener` | Method của Spring-managed bean | Có thể trả event khác, nhưng điều này không thay thế xử lý lỗi |
| `@Order` | Không áp đặt thứ tự nghiệp vụ cụ thể nếu chưa khai báo | Có thể chủ động sắp invocation khi cần, không tạo transaction boundary |

## 2. Exception lan truyền theo đường nào?

Giả sử một service publish event:

~~~java
@Service
class OrderService {
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void submit(String id) {
        publisher.publishEvent(new OrderSubmitted(id));
        System.out.println("publish returned");
    }
}

record OrderSubmitted(String id) {}

@Component
class ValidationListener {
    @EventListener
    void onSubmit(OrderSubmitted event) {
        throw new IllegalStateException("invalid order: " + event.id());
    }
}
~~~

Đây là **trích đoạn trong Spring application**, cần import `@Service`, `@Component`, `ApplicationEventPublisher` và `@EventListener`. Với listener đồng bộ mặc định, `submit` bị ngắt ở lời gọi `publishEvent`; dòng `publish returned` **không in ra** vì `IllegalStateException` không được bắt. Caller của `submit` có thể bắt exception giống như bắt lỗi từ lời gọi service thông thường.

Không có cơ chế tự động retry, dead-letter queue hoặc replay chỉ vì dùng `ApplicationEventPublisher`. Nếu một listener ném exception, trạng thái của những listener **đã hoàn thành trước đó** không tự được khôi phục. Đặc biệt, tác dụng phụ HTTP/email đã gửi trước exception không thể rollback cùng JDBC transaction.

### Listener sau có còn chạy không?

Với multicast đồng bộ và không có `ErrorHandler`, exception của listener A thường làm lần multicast **dừng tại A**; listener B lẽ ra được gọi sau A không được thực thi. Khi muốn kiểm thử trường hợp này, đặt thứ tự minh bạch:

~~~java
@Component
class OrderedListeners {
    @EventListener
    @Order(0)
    public void first(OrderSubmitted event) {
        throw new IllegalStateException("failed first");
    }

    @EventListener
    @Order(10)
    public void second(OrderSubmitted event) {
        System.out.println("second");
    }
}
~~~

Đây là trích đoạn minh họa. Trong chế độ mặc định, `second` không in ra khi `first` ném exception. `@Order` chỉ xác định **thứ tự gọi listener**, không phải cơ chế cô lập lỗi hay tạo transaction.

## 3. Tại sao listener có thể làm database rollback?

Spring transaction interceptor hoặc `TransactionTemplate` điều khiển transaction **xung quanh đoạn code nghiệp vụ**. Nếu listener đồng bộ chạy bên trong phạm vi này, exception của nó có thể đi ngược về transaction manager.

Ví dụ service mang `@Transactional`:

~~~java
@Transactional
public void placeOrder(CreateOrderCommand command) {
    orderRepository.insert(command);
    publisher.publishEvent(new OrderPlaced(command.id()));
}
~~~

Đây là trích đoạn: repository, command, event và publisher do ứng dụng định nghĩa. Giả sử lời gọi đi **qua Spring proxy**, transaction đã bắt đầu, và một `@EventListener` đồng bộ ném `IllegalStateException` không bị bắt: exception thoát khỏi phương thức `placeOrder`. Với rollback rules mặc định, Spring đánh dấu rollback và các thao tác DB tham gia **cùng transaction** bị hoàn tác.

Không phải “event tự rollback transaction” mà là chuỗi nhân quả:

1. Listener được gọi **trong** `publishEvent`.
2. Listener ném exception; không có handler chặn nó.
3. Exception thoát khỏi service method/transaction callback.
4. Transaction interceptor/manager áp dụng rollback rules.
5. Transaction rollback; thay đổi JDBC/JPA chưa commit của transaction đó bị hủy.

### Rollback rules mặc định

Với `@Transactional` theo cấu hình phổ biến của Spring Framework 6.x:

| Lỗi thoát ra khỏi phương thức transaction | Mặc định | Ghi chú |
| --- | --- | --- |
| `RuntimeException` (ví dụ `IllegalStateException`) | Rollback | Đây là trường hợp listener đồng bộ thường gặp |
| `Error` | Rollback | Không nên dùng `Error` để báo lỗi nghiệp vụ |
| Checked `Exception` được service ném trực tiếp | Thông thường không rollback | Có thể cấu hình `rollbackFor` |
| Exception bị service bắt và không ném tiếp | Transaction có thể commit | Trừ khi đã rollback-only hoặc có lỗi transaction khác |
| Không có transaction tại thời điểm publish | Không có DB transaction chung để rollback | Các thao tác đã autocommit không tự bị hoàn tác |

Từ Spring Framework 6.2, ứng dụng có thể chọn chính sách rollback mặc định rộng hơn bằng cấu hình transaction management, nên hãy kiểm tra **phiên bản và rollback rules thực tế** thay vì tuyệt đối hóa bảng.

Ví dụ khi một *service method* có chủ đích ném checked exception:

~~~java
@Transactional(rollbackFor = BusinessRuleException.class)
public void executeCommand() throws BusinessRuleException {
    // ... thao tác DB
    throw new BusinessRuleException("Rejected");
}
~~~

Đây là trích đoạn, cần định nghĩa `BusinessRuleException extends Exception` và method thực sự được transaction interceptor xử lý. `rollbackFor` chỉ rõ policy đối với exception đó. **Không áp dụng máy móc quy tắc checked exception của service trực tiếp cho một method `@EventListener`**, vì Spring event adapter có bước chuyển exception riêng.

## 4. Trường hợp tinh tế: checked exception trong @EventListener

Spring cho phép method `@EventListener` khai báo checked exception, nhưng **checked exception phát sinh từ listener được bọc thành `java.lang.reflect.UndeclaredThrowableException`** vì `ApplicationEventPublisher` làm việc với runtime exceptions.

Ví dụ:

~~~java
@EventListener
public void onOrder(OrderSubmitted event) throws IOException {
    throw new IOException("external system unavailable");
}
~~~

Đây là trích đoạn (cần import `java.io.IOException`). Trong lời gọi qua listener adapter của Spring, exception lan về publisher có thể là một `UndeclaredThrowableException` với cause là `IOException`. Lớp wrapper là **unchecked**, nên nếu nó thoát ra khỏi transaction interceptor, rollback mặc định có thể xảy ra ngay cả khi exception gốc là checked.

Do đó cần phân biệt:

- **Checked exception do chính service `@Transactional` ném**: theo rollback rules mặc định của Spring 6.x, thông thường không gây rollback.
- **Checked exception do method `@EventListener` ném qua Spring listener adapter**: được bọc thành `UndeclaredThrowableException`, là runtime exception; kết quả rollback có thể khác.
- **Exception bị `ErrorHandler` hoặc caller bắt lại**: wrapper có thể không thoát ra transaction boundary; kết quả còn tùy trạng thái transaction và các xử lý khác.

Đừng viết kiểm thử chỉ `assertThrows(IOException.class, ...)` cho toàn bộ luồng `publishEvent` rồi mặc định nó luôn đúng. Kiểm tra **exception thực tế quan sát ở publisher** cùng cause.

## 5. Bắt exception trong service làm thay đổi kết quả

Giả sử listener ném lỗi nhưng application service quyết định tiếp tục:

~~~java
@Transactional
public void placeOrder(CreateOrderCommand command) {
    orderRepository.insert(command);

    try {
        publisher.publishEvent(new OrderPlaced(command.id()));
    } catch (IllegalStateException ex) {
        log.warn("Optional listener failed", ex);
    }
}
~~~

Đây là trích đoạn, cần `log`, repository và class nghiệp vụ. Nếu không có thành phần nào khác đánh dấu `rollbackOnly`, transaction có thể **commit** dù một listener thất bại. Nhưng do multicast mặc định bị ngắt ở listener ném exception, **những listener sau vẫn có thể chưa được gọi**. Catch ở caller không quay ngược thời gian để chạy tiếp listener B.

### Khi nghiệp vụ yêu cầu rollback dù đã bắt exception

Dùng rollback-only đúng phạm vi khi muốn thu thập lỗi nhưng không cho commit:

~~~java
@Transactional
public void placeOrder(CreateOrderCommand command) {
    orderRepository.insert(command);

    try {
        publisher.publishEvent(new OrderPlaced(command.id()));
    } catch (IllegalStateException ex) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        log.warn("Transaction must not commit", ex);
    }
}
~~~

Đây là trích đoạn phụ thuộc transaction interceptor hiện hành và `TransactionAspectSupport`. `currentTransactionStatus()` chỉ dùng được khi có transaction status do Spring quản lý trong ngữ cảnh phù hợp; không gọi tùy tiện ngoài transaction. Một lựa chọn rõ hơn khi dùng `TransactionTemplate` là `status.setRollbackOnly()`.

**Cảnh báo nested transactions:** một transaction tham gia transaction ngoài có thể đã bị đánh dấu rollback-only ở một lớp khác. Catch exception ở lớp ngoài không nhất thiết khiến commit thành công; có thể gặp `UnexpectedRollbackException`. Việc catch một exception không xóa trạng thái rollback-only đã được đặt.

### Không gọi external system trước commit chỉ vì listener đồng bộ

Nếu listener đã gửi email hoặc HTTP request trước khi lỗi phát sinh và transaction rollback, email/request vẫn có thể tồn tại. Nếu side effect phải chờ commit, dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`; nếu không được mất ý định gửi sau crash, dùng transactional outbox hoặc cơ chế ghi nhận publication bền vững.

## 6. Tùy biến SimpleApplicationEventMulticaster ErrorHandler

Spring hỗ trợ cung cấp bean tên `applicationEventMulticaster` để cấu hình riêng cách xử lý listener. Khi không cấu hình `ErrorHandler`, exception chưa xử lý lan đến publisher và có thể dừng việc gọi các listener tiếp theo.

Một cấu hình **minh họa** dùng handler ghi lỗi rồi **không ném lại**:

~~~java
@Configuration
class EventMulticasterConfiguration {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(error ->
            System.err.println(
                "Listener failed: " + error.getClass().getSimpleName()
            )
        );

        return multicaster;
    }
}
~~~

Đây là trích đoạn cấu hình trong Spring, cần import `@Configuration`, `@Bean`, `ApplicationEventMulticaster` và `SimpleApplicationEventMulticaster`. Trong production hãy dùng logging/metrics có ngữ cảnh; `System.err` chỉ giúp nhìn rõ ví dụ.

Khi handler **suppress** exception và trả về bình thường, multicaster có thể tiếp tục mời listener kế tiếp. `publishEvent` cũng có thể trở về bình thường, nên transaction **không tự rollback chỉ vì lỗi đã bị suppress**.

Ngược lại, handler có thể **log rồi ném lại** exception; khi đó propagation và rollback có thể diễn ra như không có handler. Spring cũng cung cấp các ErrorHandler tiện ích như `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` và `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` trong những trường hợp phù hợp.

| Chính sách | Exception đến publisher? | Listener tiếp theo? | Rủi ro |
| --- | --- | --- | --- |
| Mặc định, không `ErrorHandler` | Có, trong dispatch đồng bộ | Thường dừng tại listener lỗi | Nghiệp vụ chính có thể rollback vì lỗi phụ |
| Handler log và suppress | Không, nếu handler tự xử lý xong | Có thể tiếp tục | Ẩn lỗi nghiêm trọng và làm transaction commit |
| Handler log và rethrow | Có | Dừng khi lỗi thoát | Vẫn coupling với nghiệp vụ chính |
| Dispatch bất đồng bộ qua executor | Không thể giả định exception về caller | Tùy executor/handler | Cần theo dõi lỗi và context riêng |

**Không bật global suppress chỉ để “cho qua lỗi”**. Nó ảnh hưởng mọi listener đi qua multicaster đó, bao gồm listener mà lỗi có thể phản ánh một bất biến dữ liệu không được phép bỏ qua. Nếu chỉ một listener là best-effort, cân nhắc xử lý cục bộ bên trong listener hoặc chuyển tác vụ sang cơ chế bất đồng bộ/durable phù hợp.

## 7. Listener đồng bộ khác listener async ở ranh giới lỗi

Với `@Async @EventListener` hoặc multicaster có executor, listener có thể chạy trên thread khác. Khi đó exception của listener bất đồng bộ **không được truyền trực tiếp** về caller của `publishEvent`. Cơ chế xử lý exception tùy `AsyncUncaughtExceptionHandler`, returned `Future`, executor và cấu hình.

~~~java
@Async
@EventListener
public void onOrderCreated(OrderCreated event) {
    notificationSender.send(event.orderId());
}
~~~

Đây là trích đoạn, cần bật `@EnableAsync` và cung cấp bean/đối tượng `notificationSender`. Không dùng nó làm bằng chứng rằng email chắc chắn đã gửi khi `publishEvent` trả về.

**Hệ quả về transaction:** transaction JDBC thường gắn với thread gọi. Task async trên thread khác không tự tham gia transaction của publisher. Exception async không tự làm rollback transaction gốc; ngược lại, dữ liệu mà async listener nhìn thấy có thể chưa commit vào lúc nó chạy. Nếu yêu cầu chỉ chạy sau commit, dùng transaction-bound listener phù hợp và thiết kế cơ chế thực thi async **sau commit** nếu cần.

`@TransactionalEventListener(AFTER_COMMIT)` khác `@EventListener` đồng bộ thông thường: nó đăng ký xử lý theo kết quả transaction. Khi transaction đã commit, exception xảy ra ở công việc after-commit **không thể hoàn tác commit đã thành công**; hành vi báo lỗi cho caller và logging còn phụ thuộc transaction synchronization và cấu hình. Vì thế side effect quan trọng cần retry, idempotency và quan sát lỗi riêng.

Không dùng `@Async` như một mẹo đơn giản để chữa lỗi rollback. Nó thay đổi tính nhất quán, thứ tự completion và ranh giới quan sát lỗi.

## 8. Ví dụ tích hợp Java 17+: kiểm chứng propagation, rollback, catch và no transaction

Bộ kiểm thử sau dùng **Spring Context + Spring Test + Spring JDBC + H2 + JUnit 5**. Mọi thao tác JDBC quan trọng và lệnh publish chạy trong `TransactionTemplate` khi cần transaction; test không tự mang `@Transactional` để tránh test transaction bị rollback cuối method.

Mục tiêu:

1. Không có lỗi: `@Order(0)` và `@Order(10)` đều chạy, `publishEvent` trả về, DB commit.
2. Listener đầu ném `IllegalStateException` trong transaction: publisher nhận lỗi, listener sau không chạy, cả dữ liệu của service lẫn listener rollback.
3. Không có transaction: lỗi vẫn đến caller, nhưng lệnh INSERT của listener có thể đã **autocommit** và không được hoàn tác.
4. Service bắt exception trong transaction: transaction không bị rollback chỉ vì một lỗi đã bắt, nếu chưa đánh dấu rollback-only.
5. Service bắt lỗi nhưng đặt rollback-only: database rollback dù exception không được ném tiếp.

### 8.1. build.gradle

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-jdbc'
    testImplementation 'org.springframework:spring-tx'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
    testRuntimeOnly 'com.h2database:h2:2.3.232'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Trên dự án Spring Boot đã có BOM/dependency management, ưu tiên phiên bản được Boot quản lý để tránh trộn Spring Framework modules không tương thích. Ví dụ test dùng Java 17; cấu hình Gradle wrapper do project cung cấp.

### 8.2. src/test/java/example/events/SyncListenerExceptionTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;

import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.support.TransactionTemplate;

@SpringJUnitConfig(SyncListenerExceptionTest.Config.class)
class SyncListenerExceptionTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired JdbcTemplate jdbc;
    @Autowired TransactionTemplate tx;
    @Autowired Trace trace;

    @BeforeEach
    void prepare() {
        jdbc.execute("CREATE TABLE IF NOT EXISTS orders (" +
            "id VARCHAR(50) PRIMARY KEY)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS audit (" +
            "id VARCHAR(50) PRIMARY KEY)");
        jdbc.update("DELETE FROM audit");
        jdbc.update("DELETE FROM orders");
        trace.clear();
    }

    @Test
    void successCallsBothListenersAndCommits() {
        tx.executeWithoutResult(status -> {
            insertOrder("OK");
            publisher.publishEvent(new OrderCreated("OK", false));
            trace.add("returned:OK");
        });

        assertEquals(
            List.of("first:OK", "second:OK", "returned:OK"),
            trace.snapshot()
        );
        assertEquals(1, orders("OK"));
        assertEquals(1, audit("OK"));
    }

    @Test
    void failureStopsMulticastAndRollsBack() {
        IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> tx.executeWithoutResult(status -> {
                insertOrder("FAIL");
                publisher.publishEvent(
                    new OrderCreated("FAIL", true));
                trace.add("returned:FAIL");
            })
        );

        assertEquals("blocked:FAIL", error.getMessage());
        assertEquals(List.of("first:FAIL"), trace.snapshot());
        assertEquals(0, orders("FAIL"));
        assertEquals(0, audit("FAIL"));
    }

    @Test
    void failureOutsideTransactionCannotUndoAutocommit() {
        assertThrows(
            IllegalStateException.class,
            () -> publisher.publishEvent(
                new OrderCreated("OUT", true))
        );

        assertEquals(List.of("first:OUT"), trace.snapshot());
        assertEquals(1, audit("OUT"));
    }

    @Test
    void catchingExceptionAllowsCommit() {
        tx.executeWithoutResult(status -> {
            insertOrder("CATCH");
            try {
                publisher.publishEvent(
                    new OrderCreated("CATCH", true));
            } catch (IllegalStateException expected) {
                trace.add("caught:CATCH");
            }
        });

        assertEquals(
            List.of("first:CATCH", "caught:CATCH"),
            trace.snapshot()
        );
        assertEquals(1, orders("CATCH"));
        assertEquals(1, audit("CATCH"));
    }

    @Test
    void rollbackOnlyWorksEvenWhenExceptionIsCaught() {
        tx.executeWithoutResult(status -> {
            insertOrder("MARK");
            try {
                publisher.publishEvent(
                    new OrderCreated("MARK", true));
            } catch (IllegalStateException expected) {
                status.setRollbackOnly();
                trace.add("marked:MARK");
            }
        });

        assertEquals(
            List.of("first:MARK", "marked:MARK"),
            trace.snapshot()
        );
        assertEquals(0, orders("MARK"));
        assertEquals(0, audit("MARK"));
    }

    private void insertOrder(String id) {
        jdbc.update("INSERT INTO orders(id) VALUES (?)", id);
    }

    private int orders(String id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM orders WHERE id = ?",
            Integer.class, id
        );
    }

    private int audit(String id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit WHERE id = ?",
            Integer.class, id
        );
    }

    record OrderCreated(String id, boolean fail) { }

    static final class Trace {
        private final List<String> lines = new ArrayList<>();

        void add(String line) {
            lines.add(line);
        }

        List<String> snapshot() {
            return List.copyOf(lines);
        }

        void clear() {
            lines.clear();
        }
    }

    static final class OrderedListeners {
        private final JdbcTemplate jdbc;
        private final Trace trace;

        OrderedListeners(JdbcTemplate jdbc, Trace trace) {
            this.jdbc = jdbc;
            this.trace = trace;
        }

        @EventListener
        @Order(0)
        public void first(OrderCreated event) {
            trace.add("first:" + event.id());
            jdbc.update("INSERT INTO audit(id) VALUES (?)",
                event.id());

            if (event.fail()) {
                throw new IllegalStateException(
                    "blocked:" + event.id());
            }
        }

        @EventListener
        @Order(10)
        public void second(OrderCreated event) {
            trace.add("second:" + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                "jdbc:h2:mem:listener_exception;DB_CLOSE_DELAY=-1",
                "sa", ""
            );
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        DataSourceTransactionManager transactionManager(
                DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                DataSourceTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        OrderedListeners listeners(JdbcTemplate jdbc, Trace trace) {
            return new OrderedListeners(jdbc, trace);
        }
    }
}
~~~

### 8.3. Cách chạy và hiểu kết quả

Trong project có Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.SyncListenerExceptionTest"
~~~

Trên Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.SyncListenerExceptionTest"
~~~

Các chuỗi trong `Trace` được kiểm tra qua assertion, **không phải toàn bộ stdout của Gradle**. Khi test pass, ta có kết quả về mặt quan sát:

| Test | Trace mong đợi | orders | audit |
| --- | --- | --- | --- |
| `successCallsBothListenersAndCommits` | `first:OK`, `second:OK`, `returned:OK` | OK = 1 | OK = 1 |
| `failureStopsMulticastAndRollsBack` | Chỉ `first:FAIL` | FAIL = 0 | FAIL = 0 |
| `failureOutsideTransactionCannotUndoAutocommit` | Chỉ `first:OUT` | Không ghi order | OUT = 1 |
| `catchingExceptionAllowsCommit` | `first:CATCH`, `caught:CATCH` | CATCH = 1 | CATCH = 1 |
| `rollbackOnlyWorksEvenWhenExceptionIsCaught` | `first:MARK`, `marked:MARK` | MARK = 0 | MARK = 0 |

**Tại sao cả audit insert cũng rollback trong test FAIL?** `JdbcTemplate` trong listener chạy cùng thread, cùng `DataSourceTransactionManager` và tham gia JDBC transaction mà service đã mở. Nếu listener ghi một database khác hoặc gọi API bên ngoài, đừng suy rằng side effect đó tự tham gia transaction gốc.

**Tại sao trace không rollback?** `Trace` là danh sách Java trong bộ nhớ, không phải một phần của JDBC transaction. Nó cố tình giữ dấu vết rằng listener từng chạy, dù các lệnh SQL sau đó bị rollback.

**Tại sao dùng `TransactionTemplate` thay cho `@Transactional` trong test?** Để làm rõ thời điểm commit/rollback và kiểm tra trực tiếp sau mỗi transaction. Với ứng dụng dùng `@Transactional`, kết quả tương tự nếu interceptor thật sự bao transaction, lời gọi đi qua proxy và rollback rules phù hợp. Không nên gắn `@Transactional` lên toàn bộ JUnit test rồi mong `AFTER_COMMIT` chạy ở giữa test; Spring TestContext có cơ chế rollback test transaction mặc định.

Mẫu test dùng `ApplicationEventPublisher` thực của Spring context, không tự gọi trực tiếp `OrderedListeners.first(...)`. Vì thế test kiểm tra cả việc Spring đăng ký và gọi `@EventListener` lẫn hành vi `SimpleApplicationEventMulticaster`.

## 9. Diagnostic: khi nào lỗi rollback, khi nào không?

| Tình huống | Publisher có thấy lỗi? | Transaction có rollback? | Điều cần kiểm tra |
| --- | --- | --- | --- |
| Listener sync ném `IllegalStateException` trong `@Transactional` và lỗi thoát ra | Có | Thường có, theo rollback rules | Service có đi qua proxy? |
| Listener sync ném lỗi ngoài transaction | Có | Không có transaction chung để rollback | Side effect autocommit đã xảy ra chưa? |
| Caller catch lỗi, không rollback-only | Caller bắt được | Có thể commit | Có transaction nào đã tự mark rollback-only không? |
| Caller catch và set rollback-only | Caller bắt được | Có | Status được đánh dấu trong transaction đúng |
| Global `ErrorHandler` suppress | Thường không | Không chỉ vì lỗi suppress | Có vô tình bỏ qua lỗi quan trọng không? |
| Listener `@Async` ném lỗi | Thường không theo đường sync | Không trực tiếp làm rollback transaction gốc | `AsyncUncaughtExceptionHandler`/executor/metrics |
| `@TransactionalEventListener(AFTER_COMMIT)` ném lỗi | Tùy callback/synchronization | **Không hoàn tác commit đã hoàn tất** | Retry/compensation và quan sát lỗi |

### Ghi log và theo dõi đủ ngữ cảnh

Khi debug, ghi `eventType`, `eventId`, `aggregateId`, listener class/method, loại exception, trạng thái transaction và correlation ID. **Không log payload nhạy cảm** không cần thiết. Nếu đang dùng proxy hoặc async, log cả thread và điểm publish để xác định ranh giới xử lý.

Với exception có thể làm rollback, kiểm thử cả:

- giá trị DB sau khi transaction kết thúc (readback từ một transaction/connection độc lập);
- listener đã được gọi và listener nào chưa được gọi;
- ngoại lệ thực sự đến caller, kể cả wrapper `UndeclaredThrowableException`;
- tác dụng phụ bên ngoài nếu có (mock gateway, outbox record);
- trường hợp lỗi đã bị bắt hoặc ErrorHandler suppress, tránh cho rằng transaction vẫn rollback.

## 10. Thiết kế hệ thống: không để listener ẩn quyết định nghiệp vụ lõi

Một event listener thích hợp khi một nhóm tác vụ độc lập **phản ứng** với sự kiện miền. Nhưng nếu “thất bại của bước B phải huỷ bước A” là bất biến bắt buộc, dùng một application service gọi B tường minh trong cùng transaction thường dễ đọc và dễ bảo trì hơn việc phụ thuộc vào một listener ẩn.

Ví dụ:

~~~java
@Transactional
public void confirmOrder(String id) {
    inventoryService.reserve(id);   // bước bắt buộc
    orderRepository.confirm(id);
    publisher.publishEvent(new OrderConfirmed(id)); // notification
}
~~~

Đây là trích đoạn, không phải file độc lập. Khi event chỉ để cập nhật metric hoặc gửi thông báo, hãy cân nhắc cách xử lý best-effort hay after-commit phù hợp. Với tác vụ phải được giao bền vững ra ngoài process, **transactional outbox** ghi dữ liệu nghiệp vụ và ý định gửi trong cùng transaction, rồi giao nhận bằng worker với retry và idempotency; không coi `ApplicationEventPublisher` mặc định là một durable message queue.

### Checklist trước khi triển khai

1. Listener hiện tại là **sync**, `@Async` hay do custom multicaster chạy executor?
2. Có `ErrorHandler` không? Nó log/suppress hay log/rethrow?
3. Event được publish **trước, trong, hay sau** transaction?
4. Khi listener lỗi, có buộc nghiệp vụ chính rollback không? Rollback rules có đúng?
5. Caller bắt exception ở đâu? Transaction đã bị rollback-only ở điểm nào?
6. Nếu listener thực thi trước commit, có side effect không rollback được không?
7. Integration test đã kiểm tra cả success, exception, catch, rollback-only và outside transaction chưa?
8. Nếu muốn retry/durability, cơ chế lưu sự kiện và idempotency nằm ở đâu?

## 11. Câu hỏi tự kiểm tra

**Câu 1:** Trong cấu hình mặc định, `@EventListener` đồng bộ ném `IllegalStateException` thì `publishEvent` có thể trả về bình thường không?

Thông thường **không**: exception đi ngược đến publisher và lần multicast hiện tại dừng. Chỉ khi có code catch hoặc `ErrorHandler` phù hợp thì đường lan truyền mới khác.

**Câu 2:** Exception của listener luôn làm database rollback?

**Không.** Phải có transaction đang bao lời publish, lỗi cần thoát đến boundary/transaction manager theo rollback rules hoặc transaction phải được đánh dấu rollback-only. Nếu lỗi bị bắt hoặc event phát ngoài transaction, kết quả khác.

**Câu 3:** Checked exception trong method `@EventListener` có giống checked exception ném trực tiếp từ service `@Transactional`?

Không hoàn toàn. Listener adapter của Spring bọc checked exception thành `UndeclaredThrowableException` unchecked khi lan về publisher, nên rollback rules có thể đánh giá loại wrapper, không chỉ loại gốc.

**Câu 4:** Đặt `@Order(0)` và `@Order(10)` có làm listener thứ hai vẫn chạy khi listener đầu ném exception?

Không ở cấu hình đồng bộ mặc định không xử lý lỗi. `@Order` chỉ sắp thứ tự invocation, không bắt exception. Một `ErrorHandler` suppress có thể thay đổi chuyện tiếp tục gọi listener.

**Câu 5:** Dùng `@Async` cho listener có đảm bảo lỗi không ảnh hưởng transaction mà vẫn xử lý chắc chắn?

Không. Async tách đường lan truyền exception khỏi caller, nhưng không bảo đảm listener đã hoàn tất, retry hay durability. Hệ thống phải theo dõi lỗi và thiết kế xử lý phù hợp.

**Ghi nhớ:** exception của `@EventListener` đồng bộ **thường lan ngược về `publishEvent` và làm gián đoạn multicast**. Rollback chỉ xảy ra khi transaction boundary và rollback rules tạo ra kết quả đó. Hiểu cách catch lỗi, `ErrorHandler`, checked-exception wrapper và async dispatch là điều kiện để thiết kế event an toàn.

## Tài liệu tham khảo

- [Spring Framework – ApplicationContext: Event Listeners, Asynchronous Listeners và Multicaster](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework – SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework – EventListener API: Exception Handling](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework – @Transactional và rollback rules](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
