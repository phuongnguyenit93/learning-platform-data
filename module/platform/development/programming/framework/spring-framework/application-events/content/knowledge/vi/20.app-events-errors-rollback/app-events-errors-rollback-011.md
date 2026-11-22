# Phân biệt lỗi nghiệp vụ và lỗi hạ tầng khi xử lý Spring Application Events

## 1. Vì sao cần phân biệt hai nhóm lỗi?

Khi một service gọi `ApplicationEventPublisher.publishEvent(event)`, nhiều thành phần có thể tham gia: mã domain kiểm tra quy tắc, repository ghi dữ liệu, `ApplicationEventMulticaster` chọn listener, listener gọi email/API/broker và transaction manager commit hoặc rollback. Nếu chỉ ghi log "event failed" hoặc bắt mọi `Exception` rồi retry, hệ thống dễ biến một lệnh **không được phép theo nghiệp vụ** thành hàng loạt thử lại vô ích, hoặc ngược lại coi một lỗi kết nối tạm thời như từ chối nghiệp vụ vĩnh viễn.

**Lỗi nghiệp vụ (business/domain error)** là kết quả không đáp ứng một quy tắc, trạng thái hoặc chính sách của miền nghiệp vụ. Ví dụ: không đủ số dư, đơn hàng đã thanh toán, không thể hủy đơn đã giao, hạn mức cho phép đã bị vượt. Kết quả này thường **dự đoán được từ command và trạng thái domain hợp lệ**.

**Lỗi hạ tầng (infrastructure/technical error)** là việc hệ thống không thực hiện được thao tác cần thiết do tài nguyên hoặc cơ chế kỹ thuật: database không kết nối, HTTP timeout, broker tạm ngừng, pool cạn, executor từ chối task, lỗi hệ thống tệp, hoặc cấu hình dịch vụ không hợp lệ.

Phân biệt này **không chỉ dựa trên tên class exception**. Một lỗi unique constraint của DB có thể biểu hiện "đơn đã tồn tại" (quy tắc nghiệp vụ) hoặc là dấu hiệu race condition/hạ tầng tùy trường hợp; một HTTP 409 có thể là xung đột domain hoặc lỗi đồng bộ của một hệ thống khác. Phải đặt lỗi trong **ngữ cảnh của operation, aggregate, transaction và hợp đồng tích hợp**.

| Tiêu chí | Lỗi nghiệp vụ | Lỗi hạ tầng |
| --- | --- | --- |
| Nguyên nhân chủ yếu | Command vi phạm invariant/policy hoặc trạng thái không cho phép | Dependency, network, storage, scheduling hoặc cấu hình |
| Ví dụ | `OrderAlreadyPaid`, `InsufficientBalance` | `DataAccessResourceFailureException`, timeout, broker unavailable |
| Retry cùng input và trạng thái | Thường **không giúp ích** | Có thể hữu ích nếu lỗi tạm thời và operation an toàn |
| Hành động thường gặp | Trả kết quả từ chối rõ ràng; hướng dẫn thay đổi input/trạng thái | Retry có giới hạn, fallback, circuit breaker, cảnh báo |
| Có rollback không? | **Tùy trạng thái cần lưu và chính sách transaction** | Thường rollback phần chưa commit; không undo side effect đã xảy ra |
| Quan sát vận hành | Business outcome/denial rate; không mặc định là incident | Error rate, dependency health, timeout, retry, DLQ |
| Có thể tạo domain event? | Có, nếu việc **bị từ chối** là sự thật nghiệp vụ cần lưu | Thường tạo technical failure signal/telemetry, không giả mạo domain fact |

Mục tiêu không phải "mọi business exception đều commit" hoặc "mọi technical exception đều rollback", mà là **mỗi loại lỗi có ý nghĩa, ranh giới transaction và chính sách xử lý riêng**.

## 2. Ba lớp cần phân biệt: lỗi, kết quả nghiệp vụ và domain event

Một quy tắc domain có thể được biểu diễn theo hai cách hợp lý:

**Cách A — từ chối bằng kết quả có kiểu**: `PaymentResult.Rejected("INSUFFICIENT_FUNDS")`. Hữu ích khi từ chối là điều bình thường của nghiệp vụ và caller cần trình bày lý do. Không bắt buộc ném exception cho mọi quyết định từ chối.

**Cách B — từ chối bằng exception rõ loại**: `BusinessRuleViolationException("ORDER_ALREADY_PAID")`. Hữu ích khi hành vi không thể tiếp tục và tầng gọi cần rollback/đưa ra response thông qua exception mapping.

Ngược lại, `PaymentGatewayUnavailableException` hoặc `DatabaseUnavailableException` đại diện cho lỗi hệ thống phụ thuộc, không nên bị chuyển thành "khách hàng không đủ tiền". Một exception hạ tầng có thể chứa nguyên nhân kỹ thuật bên trong (`cause`), nhưng không được lộ stack trace, connection string hoặc bí mật của dependency cho người dùng cuối.

**Domain event** như `PaymentAccepted` hoặc `OrderRejected` là một sự thật đã được mô hình xác nhận. Không tạo `PaymentAccepted` chỉ vì `publishEvent(...)` được gọi; event cần có **ngữ nghĩa chính xác** về thời điểm giao dịch và tính bền vững. Ví dụ `OrderRecorded` đang được phát bên trong transaction nghĩa là hành vi ghi đã được yêu cầu, **không chứng minh commit đã thành công**.

Một thiết kế tốt phân biệt:

```text
Command: "Thanh toán đơn X"
    |
    +-- kiểm tra domain -> "Rejected: ORDER_ALREADY_PAID"
    |                      (không retry máy móc)
    |
    +-- domain chấp nhận -> lưu trong transaction
            |
            +-- DB lỗi trước commit -> TechnicalFailure
            |                        (rollback, xem xét retry)
            |
            +-- publish in-process event
                    |
                    +-- listener đồng bộ lỗi -> có thể lan exception
                    |                          về publisher, rollback
                    |
                    +-- commit thành công
                            |
                            +-- AFTER_COMMIT listener lỗi
                                  -> **commit không thể bị hoàn tác**
                                  -> retry/outbox/compensation nếu cần
```

## 3. Lỗi trong Spring application events được truyền ra sao?

### 3.1. @EventListener đồng bộ (mặc định)

Spring Framework mặc định dùng `SimpleApplicationEventMulticaster` để gọi listener đồng bộ trong publisher thread. Khi `@EventListener` đồng bộ ném unchecked exception, exception có thể truyền ngược qua `publishEvent(...)` vào service. Nếu publisher đang nằm trong transaction và exception thoát qua transaction boundary, transaction manager có thể rollback.

Ví dụ một listener đồng bộ gọi API gửi email, API timeout và listener ném `RuntimeException`: cập nhật database vừa thực hiện trong cùng transaction có thể bị rollback, **dù thao tác gửi email là một dependency không thuộc transaction database**.

Nguy hiểm hơn, nếu listener trước đó đã gửi email thành công rồi listener sau thất bại, transaction database rollback cũng không thu hồi email đã gửi. Spring event in-process không biến nhiều tác dụng phụ thành một distributed transaction nguyên tử.

### 3.2. @TransactionalEventListener gắn phase

`@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)` được gọi trước khi commit; unchecked exception từ logic đó có thể khiến commit không xảy ra.

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` chạy sau commit thành công. Lỗi của listener lúc này **không thể rollback transaction đã commit**. Với listener annotation này, `AFTER_COMMIT` được xử lý trong chuỗi `afterCompletion`; không nên giả định exception luôn truyền lại cho publisher như một `@EventListener` đồng bộ bình thường.

`AFTER_ROLLBACK` chạy sau rollback; lỗi ở đó không thể biến rollback thành commit. `AFTER_COMPLETION` chạy sau khi transaction kết thúc và phù hợp cho cleanup/metrics nhưng không tự phân biệt kết quả.

Mặc định, `@TransactionalEventListener` **không chạy khi không có transaction đang hoạt động**, trừ khi bật `fallbackExecution = true` và chấp nhận ngữ nghĩa fallback.

### 3.3. Listener bất đồng bộ

Với `@Async` hoặc multicaster dùng executor, listener có thể chạy ở thread khác. Exception phát sinh sau đó thường **không quay lại lời gọi `publishEvent(...)`**. Cần kênh quan sát lỗi, `AsyncUncaughtExceptionHandler` (cho phương thức `void` dạng `@Async`), future/completion nếu có, retry policy hoặc queue/outbox theo yêu cầu.

Đối với transaction imperative, context giao dịch thường gắn với thread. Không giả định worker async có `TransactionSynchronizationManager` hoặc `SecurityContextHolder` giống publisher. Listener transactional phải đăng ký synchronization trong ngữ cảnh transaction phù hợp; việc tự gửi event từ thread không có transaction có thể khiến listener transactional bị bỏ qua.

### 3.4. ErrorHandler của event multicaster

`SimpleApplicationEventMulticaster#setErrorHandler(...)` có thể thay đổi cách xử lý exception của listener đồng bộ; ví dụ handler ghi lỗi rồi **nuốt exception** thì publisher có thể tiếp tục, và transaction có thể không rollback. Vì thế **rollback không chỉ phụ thuộc exception type, mà còn vào nơi exception bị bắt và chính sách multicaster**. Không cấu hình swallow-all chỉ để giảm lỗi log nếu nó che giấu thất bại có tác động nghiệp vụ.

## 4. Ví dụ Java 17 chạy được: ba kết quả trong transaction

Ví dụ dùng **Spring Framework 6.2.8 + H2 + TransactionTemplate**, không cần Spring Boot. Bài mô phỏng:

1. `OK-1`: đơn hợp lệ, listener đồng bộ thành công; transaction commit.
2. `BAD-1`: số tiền không hợp lệ, service ném **business exception** trước khi ghi DB hoặc phát event; transaction rollback và không có event tương ứng.
3. `NET-1`: domain hợp lệ, đã INSERT trong transaction nhưng listener đồng bộ mô phỏng lỗi cổng thông báo; **infrastructure exception** lan ngược đến transaction template và DB rollback.

Một listener `AFTER_COMMIT` và một listener `AFTER_ROLLBACK` quan sát kết quả. Dùng `@Order` để **đăng ký callback transaction trước khi chạy listener có thể ném lỗi**, tránh phụ thuộc vào thứ tự khám phá phương thức.

### 4.1. Cấu trúc Maven

```text
event-error-classification/
├── pom.xml
└── src/main/java/demo/EventErrorDemo.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>event-error-classification</artifactId>
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
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.EventErrorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/EventErrorDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class EventErrorDemo {

    // Event phản ánh thay đổi đang được xử lý trong transaction;
    // tự nó KHÔNG bảo đảm database đã commit.
    public record OrderRecorded(String orderId) {}

    public static final class BusinessViolation extends RuntimeException {
        public BusinessViolation(String code) {
            super(code);
        }
    }

    public static final class InfrastructureFailure extends RuntimeException {
        public InfrastructureFailure(String code) {
            super(code);
        }
    }

    public static final class OrderService {
        private final TransactionTemplate transactions;
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(TransactionTemplate transactions,
                JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            this.transactions = transactions;
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        public void record(String orderId, long amount) {
            transactions.executeWithoutResult(status -> {
                if (amount <= 0) {
                    throw new BusinessViolation("invalid-amount");
                }

                jdbc.update(
                        "insert into orders(id, amount) values (?, ?)",
                        orderId, amount);
                System.out.println("service: inserted " + orderId);

                // Listener đồng bộ chạy trong publisher thread.
                publisher.publishEvent(new OrderRecorded(orderId));
                System.out.println("service: published " + orderId);
            });
        }
    }

    public static final class EventListeners {

        // Đăng ký synchronization sớm hơn listener có thể ném lỗi.
        @Order(0)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void committed(OrderRecorded event) {
            System.out.println("tx: committed " + event.orderId());
        }

        @Order(1)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBack(OrderRecorded event) {
            System.out.println("tx: rolled-back " + event.orderId());
        }

        @Order(10)
        @EventListener
        public void callGateway(OrderRecorded event) {
            // Chỉ là giả lập lỗi: KHÔNG gọi mạng thật.
            if ("NET-1".equals(event.orderId())) {
                System.out.println("listener: gateway-failed NET-1");
                throw new InfrastructureFailure("gateway-unavailable");
            }
            System.out.println("listener: gateway-ok " + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:error_demo;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource source) {
            return new DataSourceTransactionManager(source);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        OrderService orderService(TransactionTemplate template,
                JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            return new OrderService(template, jdbc, publisher);
        }

        @Bean
        EventListeners eventListeners() {
            return new EventListeners();
        }
    }

    private static boolean exists(JdbcTemplate jdbc, String orderId) {
        Integer count = jdbc.queryForObject(
                "select count(*) from orders where id = ?",
                Integer.class, orderId);
        return count != null && count > 0;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("create table orders (" +
                    "id varchar(64) primary key, amount bigint not null)");

            OrderService service = context.getBean(OrderService.class);

            System.out.println("=== SUCCESS ===");
            service.record("OK-1", 100);
            System.out.println("db: OK-1=" + exists(jdbc, "OK-1"));

            System.out.println("=== BUSINESS ERROR ===");
            try {
                service.record("BAD-1", -1);
            } catch (BusinessViolation ex) {
                System.out.println("main: business=" + ex.getMessage());
            }
            System.out.println("db: BAD-1=" + exists(jdbc, "BAD-1"));

            System.out.println("=== INFRASTRUCTURE ERROR ===");
            try {
                service.record("NET-1", 100);
            } catch (InfrastructureFailure ex) {
                System.out.println("main: infrastructure=" + ex.getMessage());
            }
            System.out.println("db: NET-1=" + exists(jdbc, "NET-1"));
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q clean compile exec:java
```

Đầu ra từ `System.out.println(...)` của ứng dụng (không tính log Maven):

```text
=== SUCCESS ===
service: inserted OK-1
listener: gateway-ok OK-1
service: published OK-1
tx: committed OK-1
db: OK-1=true
=== BUSINESS ERROR ===
main: business=invalid-amount
db: BAD-1=false
=== INFRASTRUCTURE ERROR ===
service: inserted NET-1
listener: gateway-failed NET-1
tx: rolled-back NET-1
main: infrastructure=gateway-unavailable
db: NET-1=false
```

### 4.2. Vì sao output có thứ tự như vậy?

- `@Configuration(proxyBeanMethods = false)` tạo context Spring tiêu chuẩn; `JdbcTemplate` và `DataSourceTransactionManager` dùng H2 trong bộ nhớ. Bảng `orders` được tạo ngoài transaction thử nghiệm.
- Với `OK-1`, dữ liệu được insert vào transaction; listener `@EventListener` đồng bộ chạy ngay và in gateway-ok; service in published; sau khi callback của `TransactionTemplate` trả về, database commit, rồi `AFTER_COMMIT` in committed.
- Với `BAD-1`, kiểm tra amount diễn ra **trước insert và publish**. `BusinessViolation` (unchecked) khiến `TransactionTemplate` rollback. Vì chưa có event nào được phát, không có listener after-rollback cho `BAD-1` — dù transaction vẫn rollback.
- Với `NET-1`, insert đã được gọi nhưng chưa commit. Các listener transactional có `@Order(0)`/`@Order(1)` đăng ký callback trước listener `@Order(10)`. Listener gateway mô phỏng lỗi hạ tầng, ném `InfrastructureFailure`; lời gọi `publishEvent` không trả về bình thường, nên dòng `service: published NET-1` không xuất hiện. `TransactionTemplate` rollback, callback `AFTER_ROLLBACK` in thông báo, rồi exception quay về `main`. Truy vấn ngoài transaction xác nhận DB không có `NET-1`.
- Các dòng `db: ...` dùng một connection khác/ngoài transaction hoàn tất, nên phản ánh trạng thái commit hoặc rollback.
- Trong demo không có email, request HTTP hoặc message broker thật. Vì vậy **sự vắng mặt của side effect thực tế** không chứng minh Spring sẽ thu hồi email hoặc HTTP request đã gửi ở một hệ thống thật.

### 4.3. Mục đích của lỗi giả lập

Ở production, lỗi hạ tầng phát sinh từ một `GatewayClient` có `cause` kiểu `IOException`, timeout hoặc lỗi HTTP cụ thể. Mã ví dụ dùng `"NET-1"` để tạo nhánh lỗi tái lập được, **không phải quy tắc nghiệp vụ** và không phải khuyến nghị dùng ID để điều khiển xử lý gateway.

Dù cùng là `RuntimeException`, `BusinessViolation` và `InfrastructureFailure` mang ý nghĩa khác nhau, từ đó dẫn đến chính sách trả response, retry và giám sát khác nhau. Cả hai có thể làm rollback trong ví dụ, nên **kết quả rollback không phải dấu hiệu đáng tin để phân biệt loại lỗi**.

## 5. Rollback trong Spring: ý nghĩa của exception và ranh giới

Trong giao dịch khai báo với `@Transactional`, quy tắc mặc định thường là:

- `RuntimeException` hoặc `Error` thoát ra khỏi method được quản lý bởi transaction interceptor → **rollback**.
- Checked `Exception` → mặc định **không rollback**, trừ khi cấu hình `rollbackFor` hoặc thiết lập quy tắc rollback tổng quát khác.
- Có thể dùng `noRollbackFor` đối với loại exception được định nghĩa rõ nhưng **không nên** sử dụng để che lỗi khiến dữ liệu thiếu nhất quán.
- Spring Framework 6.2 cho phép thay đổi mặc định toàn cục, chẳng hạn cấu hình rollback cho tất cả exceptions. Phải đọc cấu hình thực tế trước khi khẳng định một checked exception sẽ commit.

Một ví dụ chính sách **minh họa**:

```java
@Transactional(
    rollbackFor = ExternalServiceFailure.class,
    noRollbackFor = BusinessRejection.class
)
public void process(Command command) {
    // Chỉ dùng noRollbackFor khi trạng thái được lưu vẫn nhất quán.
}
```

Trích đoạn trên chưa phải chương trình độc lập; `ExternalServiceFailure`, `BusinessRejection` và `Command` phải được định nghĩa phù hợp. `noRollbackFor` có thể hữu ích khi muốn **lưu kết quả từ chối** (ví dụ audit rejection) trong cùng transaction, nhưng không thể vừa cập nhật state thất bại một nửa vừa "commit vì là business error".

Lưu ý proxy semantics: `@Transactional` thường được áp dụng qua proxy Spring. Một lời gọi nội bộ `this.process()` không qua proxy có thể không mở transaction như bạn nghĩ. Kiểm tra transaction boundary, propagation, rollback-only và exception cuối cùng thực sự thoát ra, thay vì chỉ đọc annotation.

Trong ví dụ chạy được, `TransactionTemplate` chủ động tạo transaction. Callback ném unchecked exception làm rollback. Nó không minh họa quy tắc checked exception của proxy `@Transactional`; hai cơ chế cùng dùng Spring transaction manager nhưng API và chính sách bắt exception cần phân biệt.

## 6. Ma trận lỗi theo giai đoạn phát event

| Vị trí lỗi | Trạng thái DB có thể xảy ra | Event/listener | Hướng xử lý |
| --- | --- | --- | --- |
| Validation/domain từ chối **trước publish** | Chưa ghi hoặc rollback theo policy | Không publish success event | Trả business result; không retry máy móc |
| Repository lỗi trước commit | Transaction có thể rollback | Event đã phát trước đó có thể gây side effect | Sửa thứ tự hoặc after-commit/outbox; phân loại lỗi |
| `@EventListener` đồng bộ ném unchecked trong transaction | Có thể rollback nếu exception thoát transaction boundary | Listener trước đó có thể đã chạy | Tránh I/O không thể rollback trong luồng đồng bộ |
| `@TransactionalEventListener(BEFORE_COMMIT)` ném exception | Có thể ngăn commit | Không đạt AFTER_COMMIT | Sửa lỗi/đảm bảo invariant; tránh side effect vĩnh viễn |
| `@TransactionalEventListener(AFTER_COMMIT)` lỗi | **Đã commit**, không thể rollback transaction đó | Delivery/tác dụng phụ có thể thất bại | Retry/outbox/compensation, theo dõi độc lập |
| `@TransactionalEventListener(AFTER_ROLLBACK)` lỗi | **Đã rollback** | Cleanup/compensation có thể thất bại | Theo dõi và cơ chế retry riêng |
| Listener `@Async` lỗi | Publisher có thể đã hoàn tất/commit | Exception không tự quay về publisher | Async error handler, future, queue/retry |
| Broker relay lỗi sau DB commit | Dữ liệu DB đã commit | Message có thể chưa tới consumer | Outbox có lưu durable, retry + idempotency |
| Consumer xử lý trùng event | DB nguồn không bị undo | Side effect có thể lặp | Event ID, unique constraint/dedup |

**Không bao giờ dùng kết luận "listener lỗi nên DB rollback" cho mọi trường hợp.** Kết quả phụ thuộc việc listener chạy trong hay sau transaction, synchronous hay asynchronous, exception có được truyền ra hay bị error handler nuốt, propagation và cấu hình rollback.

## 7. Thiết kế phân loại exception rõ ràng

Nên có **error taxonomy** ở tầng application, thay vì bắt `Exception` rồi trả chung "invalid request".

Ví dụ gợi ý:

```java
// Trích đoạn thiết kế, không phải một chương trình độc lập.
sealed interface AppFailure
        permits BusinessFailure, InfrastructureFailure {}

record BusinessFailure(
        String code, String safeMessage) implements AppFailure {}

record InfrastructureFailure(
        String code, boolean retryable, String traceId)
        implements AppFailure {}
```

Các nguyên tắc:

1. **Mã lỗi ổn định**: `ORDER_ALREADY_PAID`, `INVALID_AMOUNT`, `PAYMENT_GATEWAY_TIMEOUT`. Không dùng raw exception class name làm hợp đồng API cho client.
2. **Message an toàn**: người dùng nhận thông tin đủ hành động; log nội bộ có thể giữ `cause`, nhưng loại token, password, connection string, PII.
3. **Không làm mất nguyên nhân**: khi chuyển `SocketTimeoutException` thành `GatewayUnavailableException`, lưu `cause` để điều tra, không ghi đè ý nghĩa bằng `IllegalArgumentException` chung.
4. **Retryable là quyết định theo operation**: timeout kỹ thuật không có nghĩa request chưa được phía ngoài xử lý. Cần idempotency key hoặc query trạng thái trước khi retry.
5. **Phân quyền phân loại**: module domain trả mã business; infrastructure adapter dịch lỗi HTTP/JDBC/broker; application service quyết định policy ở use case.
6. **Không biến lỗi kỹ thuật thành quyết định domain**: ví dụ "không kết nối được tới hệ thống tài khoản" không chứng minh khách hàng "không đủ số dư".

Tại boundary HTTP, một lỗi business có thể được biểu diễn bằng 400/409/422 tùy giao thức và semantics; lỗi hạ tầng có thể thành 503 hoặc 500 và một `Retry-After` thích hợp. **Không có ánh xạ HTTP duy nhất** cho mọi domain, và không nên lộ exception/stack trace thẳng ra client. Trong message consumer, có thể quyết định ack/retry/DLQ theo error code, retry budget và idempotency.

## 8. Retry: lỗi hạ tầng không đồng nghĩa có thể retry vô hạn

Một số lỗi hạ tầng **tạm thời** (timeout, 503, deadlock, queue overload). Một số **cố định hoặc cần can thiệp** (credentials sai, schema migration chưa chạy, payload không tương thích, topic không tồn tại, permission denied). Retry vô hạn chỉ tăng tải và che nguyên nhân.

Một retry policy an toàn nên xác định:

- **Có thực sự retryable?** Từ hợp đồng dependency, HTTP status/error code, trạng thái DB, tình hình queue.
- **Operation có idempotent?** Retry charge tiền hoặc gửi email có thể lặp tác dụng phụ; dùng idempotency key/event ID ổn định và dedup.
- **Budget**: số lần tối đa, deadline, exponential backoff và jitter.
- **Circuit breaker/bulkhead**: ngăn làm quá tải dependency đang lỗi; tránh giữ transaction mở qua các lần sleep/retry lâu.
- **Fallback**: chỉ dùng khi kết quả thay thế vẫn đáp ứng yêu cầu nghiệp vụ. Không báo "payment succeeded" chỉ vì tạm không kiểm tra được cổng thanh toán.
- **Dead-letter/parking**: lưu event lỗi để điều tra và replay có kiểm soát, không để mất dữ liệu qua crash.
- **Observability**: tách số lần retry, lỗi có thể phục hồi, lỗi vĩnh viễn và pending backlog.
- **Thứ tự sự kiện**: retry có thể làm event sau vượt event trước nếu không bảo đảm ordering theo aggregate/partition.

Đối với lỗi nghiệp vụ như `ORDER_ALREADY_PAID`, gửi lại **cùng command** thường không tạo giá trị. Có thể hiển thị kết quả hiện tại hoặc yêu cầu sửa input. Tuy nhiên nếu một chính sách domain phụ thuộc trạng thái ngoài thay đổi theo thời gian, việc thử lại **sau khi điều kiện thực sự thay đổi** có thể hợp lệ; đó là một command mới có điều kiện mới, không phải máy móc retry cùng request.

### Timeout là trạng thái "chưa biết", không phải mặc định "chưa làm"

Nếu HTTP request tới cổng thanh toán timeout, phía cổng **có thể đã nhận và thực hiện**. Việc đơn giản retry `charge()` có thể trừ tiền hai lần. Cần idempotency key và API tra cứu trạng thái trước khi gửi lại, hoặc một quy trình reconciliation chính thức. Một lỗi kỹ thuật không cho phép kết luận business operation thất bại về mặt nghiệp vụ.

## 9. Khi nào cần tách listener khỏi transaction?

Trong ví dụ, `@EventListener` gửi thông báo bên trong transaction DB. Đây là một **anti-pattern cố ý để minh họa**: nếu dependency không ổn, việc ghi đơn hàng có thể rollback dù trạng thái domain hợp lệ. Mặt khác, nếu gateway đã gửi email rồi commit sau đó lỗi, email cũng không được tự thu hồi.

Một thiết kế tách biệt hợp lý:

```text
@Transactional application service
  |
  +-- domain validate
  +-- update aggregate
  +-- publish domain event trong transaction
         |
         +-- @TransactionalEventListener(AFTER_COMMIT)
                -> bắt đầu tác vụ sau khi DB đã commit
                -> gọi service/worker có retry, idempotency
```

Ví dụ annotation minh họa:

```java
@Component
class ReceiptListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCommitted(OrderRecorded event) {
        // Chỉ chạy sau DB commit.
        // Lỗi ở đây KHÔNG undo transaction vừa commit.
    }
}
```

Trích đoạn không độc lập: cần import annotation, định nghĩa `OrderRecorded` và bean. Một listener after-commit cần **ghi thêm DB** có thể phải mở transaction mới, ví dụ ở service khác dùng `@Transactional(propagation = Propagation.REQUIRES_NEW)` qua Spring proxy; tài nguyên transaction cũ có thể còn bind với thread nhưng không còn commit tiếp theo.

**Giới hạn:** `AFTER_COMMIT` chỉ chọn đúng *thời điểm xử lý*, không bảo đảm durable delivery. Nếu process chết sau DB commit trước khi callback chạy, event in-memory có thể mất. Nó không tương đương outbox.

### Transactional outbox cho tác vụ cần bảo đảm phục hồi sau crash

```text
BEGIN TRANSACTION
  UPDATE orders SET status = 'PAID' WHERE id = ?
  INSERT INTO outbox(event_id, aggregate_id, type, payload, status)
COMMIT

Relay/worker:
  read outbox chưa giao
  -> publish tới broker / gọi integration
  -> xác nhận thành công
  -> đánh dấu trạng thái, retry theo chính sách
```

State và outbox được commit hoặc rollback **cùng transaction DB**. Sau crash, worker có thể tiếp tục đọc bản ghi. Nhưng nếu broker đã nhận mà worker chưa kịp đánh dấu delivered, nó sẽ gửi lại; downstream **phải idempotent**. Không tuyên bố exactly-once tác dụng phụ chỉ vì có outbox.

Với nghiệp vụ liên dịch vụ nhiều bước, rollback DB cục bộ cũng không thể rollback một giao dịch remote đã commit. Xem xét **Saga và compensating action** rõ ràng (ví dụ refund sau khi charge sai), thay vì kỳ vọng Spring transaction quản lý xuyên hệ thống.

## 10. Logging và giám sát đúng ngữ nghĩa

Nếu log mọi `BusinessViolation` như ERROR hạ tầng, dashboard và cảnh báo có thể bị nhiễu. Ngược lại, nếu biến timeout thành mã `INSUFFICIENT_FUNDS`, bạn sẽ mất tín hiệu của sự cố hệ thống và gây thông điệp sai cho người dùng.

Nên có tối thiểu:

| Trường observability | Gợi ý |
| --- | --- |
| `correlationId` / `traceId` | Liên hệ command → publish → listener → downstream; không dùng PII trực tiếp |
| `eventId`, `eventType` | Dedup, theo dõi thời điểm và loại event |
| `errorCategory` | `BUSINESS` hoặc `INFRASTRUCTURE`; có thể có `UNKNOWN` để điều tra |
| `errorCode` | Mã ổn định; không copy raw exception message chứa secrets |
| `phase` | `PUBLISH`, `BEFORE_COMMIT`, `AFTER_COMMIT`, `ASYNC_CONSUME` |
| `transactionOutcome` | `COMMITTED`, `ROLLED_BACK`, `UNKNOWN`; chỉ ghi khi đã xác định |
| `retryCount` / `nextRetryAt` | Hữu ích cho worker/relay, không dùng làm tag high-cardinality |

Lỗi nghiệp vụ dự đoán được thường là một business outcome; mức log có thể INFO/WARN theo nhu cầu sản phẩm, không mặc định biến thành incident. Lỗi hạ tầng cần metric/error rate và alert theo SLO. Tránh đưa email, token, mã OTP, số thẻ hoặc request body nhạy cảm vào event, log, trace baggage hay DLQ. **Không log nguyên object event nếu schema chưa được đánh giá**.

Trong xử lý bất đồng bộ, kết nối trace không được tự động bảo toàn qua thread: nên truyền context cần thiết bằng cơ chế được hỗ trợ, không sao chép tùy tiện toàn bộ `ThreadLocal`/security context.

## 11. Kiểm thử để chứng minh chính sách

Một nhóm kiểm thử đáng có cho application events:

1. **Business validation**: input sai → từ chối đúng mã, không phát success event, không ghi state không hợp lệ.
2. **Transaction rollback**: listener đồng bộ ném unchecked trước commit → dữ liệu đã insert nhưng chưa commit bị rollback.
3. **After commit**: lỗi listener sau commit không làm rollback transaction đã hoàn thành; alert/retry phát sinh riêng.
4. **After rollback**: listener `AFTER_ROLLBACK` chỉ chạy với event đã được phát trong transaction đó và transaction thực sự rollback.
5. **Exception mapping**: lỗi gateway được phân loại INFRASTRUCTURE, không lộ raw token/SQL trong response.
6. **ErrorHandler**: nếu cấu hình multicaster khác mặc định, assert rõ exception được truyền ra hay bị handler xử lý.
7. **Async**: lỗi task worker đi vào kênh error/queue, không biến mất; publisher không được coi kết quả async là hoàn thành.
8. **Outbox**: state và outbox cùng commit/rollback, crash rồi relay được, duplicate delivery không gây side effect trùng.
9. **Retry safety**: timeout sau khi remote đã thực hiện không gây double charge nhờ idempotency key.
10. **Business rejection persisted**: nếu thiết kế cần ghi nhận từ chối, kiểm thử transaction thực sự commit bản ghi audit hợp lệ thay vì rollback hết.
11. **Concurrent commands**: hai request cùng update aggregate cần optimistic lock hoặc transaction isolation phù hợp; không dịch mọi unique constraint thành lỗi hạ tầng.
12. **Checked exception policy**: test riêng `rollbackFor`/`noRollbackFor` hay default rollback rules theo phiên bản/cấu hình dự án.

### Ví dụ matrix test

| Trường hợp | Kỳ vọng DB | Kỳ vọng event |
| --- | --- | --- |
| Lệnh hợp lệ, gateway giả lập OK | Có `OK-1` | `@EventListener` chạy, `AFTER_COMMIT` chạy |
| Lệnh `amount <= 0` | Không có `BAD-1` | Không publish, không có phase listener |
| Gateway giả lập lỗi trong listener đồng bộ | Không có `NET-1` | `AFTER_ROLLBACK` chạy; caller nhận technical error |
| Ghi outbox rồi rollback | Không có state/outbox row | Không có event durable để relay |
| Commit rồi worker gửi thông báo thất bại | State vẫn đã commit | Bản ghi outbox/pending retry vẫn tồn tại nếu thiết kế đúng |

Kiểm thử bằng database thật hoặc H2 có transaction giúp thấy commit/rollback, không thể chứng minh rollback bằng cách chỉ in ra log "rollback" trong một repository giả lập.

## 12. Những hiểu lầm hay gặp

**"Business error luôn phải rollback"** — Sai. Có tình huống domain từ chối và không thay đổi state; có tình huống cần lưu một bản ghi `Rejected` hợp lệ. Rollback phụ thuộc consistency cần đạt.

**"Technical error luôn retry được"** — Sai. Sai credentials, invalid schema hay permission denied thường cần sửa cấu hình. Timeout có thể là kết quả chưa xác định, cần reconciliation.

**"Đã gọi save là DB chắc chắn commit"** — Sai. `save` có thể nằm trong transaction chưa commit; flush cũng không đồng nghĩa commit.

**"publishEvent là durable message broker"** — Sai. Spring event in-process mặc định không phải hàng đợi bền vững và không lưu event qua crash.

**"Listener đồng bộ lỗi thì tất cả side effects tự rollback"** — Sai. Transaction DB cục bộ không thu hồi email, HTTP request hoặc message đã gửi ra ngoài.

**"AFTER_COMMIT listener lỗi sẽ rollback"** — Sai. Commit đã xong; cần cơ chế retry/compensation khác.

**"Catch exception rồi tiếp tục là an toàn"** — Không hẳn. Nếu swallowed exception giữ transaction commit với dữ liệu thiếu bước bắt buộc, có thể gây sai invariant.

**"Dùng @Async luôn tăng độ tin cậy"** — Sai. Async chỉ thay đổi thời điểm/thread xử lý; nếu không có durable queue và error handling, còn dễ mất lỗi hơn.

**"Cứ trả HTTP 500 cho mọi exception là tốt"** — Sai. Client cần biết khi nào sửa yêu cầu, khi nào có thể retry và khi nào phải tra cứu trạng thái để tránh tạo tác dụng phụ lặp.

## 13. Checklist trước khi triển khai

- [ ] Định nghĩa business rejection codes và trạng thái hợp lệ trong domain; không ánh xạ bừa technical error thành domain outcome.
- [ ] Chỉ định transaction boundary, rollback policy và phase của từng listener.
- [ ] Xác nhận listener nào chạy đồng bộ, listener nào async, có `ErrorHandler` hay không.
- [ ] Không gọi side effect không thể rollback trong transaction nếu không có thiết kế nhất quán rõ ràng.
- [ ] Dùng `AFTER_COMMIT` hoặc outbox đúng theo yêu cầu timing/durability; không coi chúng tương đương.
- [ ] Mọi retry của thao tác gây side effect phải có idempotency/reconciliation thích hợp.
- [ ] Không retry business error vô điều kiện và không retry technical error vô hạn.
- [ ] Lưu nguyên nhân kỹ thuật trong log nội bộ an toàn; API chỉ trả error code/message thích hợp.
- [ ] Gắn correlation/event ID, metric theo nhóm lỗi và alert hạ tầng theo SLO.
- [ ] Kiểm thử rollback, after-commit failure, async failure, duplicate delivery và trạng thái remote "unknown".
- [ ] Kiểm tra hành vi `@Transactional` qua proxy và default rollback rules trong cấu hình thực tế.
- [ ] Nếu liên dịch vụ, có outbox/Saga/compensation thay vì mong đợi rollback xuyên hệ thống.

**Kết luận:** Phân biệt lỗi nghiệp vụ và lỗi hạ tầng giúp chọn đúng phản ứng: **từ chối/hướng dẫn hợp lệ** cho business rule, **khắc phục/retry có điều kiện** cho dependency failure. Nhưng trong Spring application events, bạn còn phải xét **thời điểm phát, tính đồng bộ, transaction phase, propagation và cơ chế lưu event**. Chỉ khi cả hai chiều này được thiết kế cùng nhau mới tránh được tình huống từ chối sai, rollback bất ngờ, mất event hoặc tác dụng phụ lặp.

## Tài liệu tham khảo

- [Spring Framework — Application Events và @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — @Transactional settings / rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [TransactionalEventListener Javadoc 6.2.8](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [SimpleApplicationEventMulticaster Javadoc 6.2.8](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Programmatic transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
