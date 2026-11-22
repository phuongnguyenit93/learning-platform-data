# Cơ chế gắn listener với transaction trong Spring Application Events

## 1. Vấn đề mà transaction-bound listener giải quyết

Khi một nghiệp vụ cập nhật database và phát sự kiện, event có thể được gửi **trước khi transaction commit**. Ví dụ: service lưu đơn hàng, publish `OrderCreated`, rồi phát sinh exception khiến transaction rollback. Nếu một `@EventListener` thông thường gửi email ngay khi nhận sự kiện, khách hàng có thể nhận thông báo về đơn hàng chưa từng được lưu thành công.

`@TransactionalEventListener` của Spring Framework cho phép **gắn thời điểm xử lý event với một pha trong vòng đời transaction**. Mặc định listener chỉ xử lý event **sau khi transaction commit thành công**. Cơ chế này dựa trên *transaction synchronization*: Spring đăng ký callback với transaction đang hoạt động rồi gọi callback vào thời điểm phù hợp.

Cần phân biệt ba câu:

1. **Event đã được publish**: service đã gọi `ApplicationEventPublisher.publishEvent(...)`.
2. **Event đã được đăng ký vào transaction**: Spring đã gắn callback tương ứng với transaction hiện tại.
3. **Listener đã thực thi thành công**: callback đã chạy và tác dụng phụ đã hoàn tất; điều này không tự suy ra từ hai câu trước.

Bài này giải thích cơ chế đăng ký, các pha, ví dụ Java 17+ kiểm chứng commit/rollback, và những giới hạn khi dùng `@Async`, reactive transaction hoặc side effect bên ngoài.

## 2. `@EventListener` và `@TransactionalEventListener` khác nhau

Listener thông thường:

~~~java
// Minh họa phương thức trong một Spring bean.
@EventListener
public void handle(OrderCreated event) {
    sendEmail(event.orderId());
}
~~~

Với multicaster mặc định đồng bộ, `handle` được gọi ngay trong quá trình `publishEvent` (kể cả khi transaction của publisher vẫn đang mở). Một rollback xảy ra sau đó **không hoàn tác email**.

Listener ràng buộc transaction:

~~~java
// Minh họa phương thức trong một Spring bean.
@TransactionalEventListener
public void handleAfterCommit(OrderCreated event) {
    sendEmail(event.orderId());
}
~~~

Khi publish trong transaction hợp lệ, Spring **trì hoãn** việc gọi `handleAfterCommit` đến pha `AFTER_COMMIT`. Nếu transaction rollback, listener này không chạy. `@TransactionalEventListener` không tự tạo transaction; nó quan sát vòng đời transaction mà publisher đang tham gia.

Hai đoạn trên là minh họa; `OrderCreated`, `sendEmail` và các import cần được định nghĩa khi đưa vào ứng dụng.

| Khía cạnh | `@EventListener` thông thường | `@TransactionalEventListener` |
| --- | --- | --- |
| Thời điểm gọi | Khi event được phát, theo chế độ multicaster | Khi đạt `TransactionPhase` đã chọn |
| Cần transaction đang hoạt động | Không | Có theo mặc định |
| Khi rollback | Listener có thể đã chạy trước rollback | Chỉ listener chọn `AFTER_ROLLBACK`/`AFTER_COMPLETION` được gọi trong nhánh rollback |
| Khi phát ngoài transaction | Xử lý bình thường | Bị bỏ qua trừ khi `fallbackExecution=true` |
| Có bảo đảm replay sau crash không | Không | Không |

## 3. Cách Spring liên kết event với transaction

Trong mô hình transaction đồng bộ theo thread (thường do `PlatformTransactionManager` quản lý), các thành phần chính là:

- **`ApplicationEventPublisher`**: điểm phát event, thường do `ApplicationContext` thực hiện.
- **`TransactionalApplicationListenerMethodAdapter`**: adapter Spring tạo cho phương thức `@TransactionalEventListener`; nó nhận event và biết listener muốn chạy ở pha nào.
- **`TransactionSynchronizationManager`**: giữ các resource và callback synchronization được ràng buộc với transaction/thread hiện tại.
- **`TransactionSynchronization`**: giao diện callback như `beforeCommit`, `afterCommit`, `afterCompletion`.
- **`PlatformTransactionManager`**: thực hiện commit/rollback và điều phối các callback.

### 3.1. Luồng xử lý với `AFTER_COMMIT`

1. Spring mở hoặc tham gia một transaction, chẳng hạn khi service chạy qua proxy `@Transactional` hoặc `TransactionTemplate`.
2. Business logic ghi dữ liệu rồi gọi `publishEvent(new OrderCreated(id))` **trong ngữ cảnh transaction đó**.
3. Multicaster phân phối event tới adapter của `@TransactionalEventListener`. Adapter nhận event và đăng ký một synchronization thay vì lập tức chạy thân phương thức listener.
4. Khi code nghiệp vụ kết thúc, transaction manager thực hiện các bước chuẩn bị commit, commit/rollback và completion callback.
5. Nếu transaction **commit thành công**, callback tương ứng `AFTER_COMMIT` chạy. Nếu transaction **rollback**, callback `AFTER_COMMIT` không chạy; callback `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION` sẽ được chọn theo cấu hình.

~~~text
@Transactional service
    |
    +-- INSERT dữ liệu
    |
    +-- publishEvent(OrderCreated)
    |       |
    |       +-- Transactional listener adapter
    |               |
    |               +-- register synchronization với transaction hiện tại
    |
    +-- business method kết thúc
            |
      Transaction manager
            |
            +-- beforeCommit / beforeCompletion
            +-- COMMIT hoặc ROLLBACK
            +-- completion callback
                    |
                    +-- gọi listener phù hợp phase và trạng thái
~~~

**Phân biệt hook:** Trong Spring, `TransactionPhase.AFTER_COMMIT` của `@TransactionalEventListener` được xử lý như một trường hợp đặc biệt của chuỗi **`TransactionSynchronization.afterCompletion(STATUS_COMMITTED)`**, không tương đương trực tiếp với phương thức `TransactionSynchronization.afterCommit()`. Vì thế không nên suy luận thứ tự thực hiện của các listener và callback khác nhau chỉ dựa vào chữ “after commit”.

Đây là cơ chế **đăng ký trong bộ nhớ** gắn với transaction hiện tại. Nó không tự lưu event thành thông điệp bền vững để phát lại sau khi process chết.

### 3.2. Điều kiện để đăng ký synchronization

Với transaction thread-bound, Spring cần có synchronization hoạt động **và transaction thực sự đang chạy** trong ngữ cảnh phát event. Gọi `publishEvent` không mở transaction; chạy một đoạn code trên thread khác cũng không tự thừa hưởng transaction của thread ban đầu.

Nếu không có transaction phù hợp, listener mặc định **không chạy**. Không có cơ chế “chờ đến transaction tiếp theo”.

## 4. Bốn `TransactionPhase` và thời điểm kích hoạt

| Pha | Thời điểm | Tình huống dùng hợp lý | Điều không được suy ra |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction thực sự commit | Kiểm tra tính nhất quán, hoàn thiện dữ liệu trong transaction | Không bảo đảm commit sau đó sẽ thành công |
| `AFTER_COMMIT` (mặc định) | Khi transaction đã commit thành công | Phản ứng với dữ liệu đã được xác nhận, cập nhật cache hoặc kích hoạt tác vụ khác | Không bảo đảm side effect được lưu/retry nếu process gặp sự cố |
| `AFTER_ROLLBACK` | Khi transaction đã rollback | Quan sát thất bại, cleanup tài nguyên tạm | Không có giao dịch cũ để tiếp tục ghi rồi commit |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc bằng commit hoặc rollback | Cleanup chung, metrics cho cả hai nhánh | Không tự biểu đạt status qua tham số event; cần logic bổ sung nếu muốn phân biệt |

Cú pháp của bốn pha:

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void before(OrderCreated event) { /* ... */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void committed(OrderCreated event) { /* ... */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void rolledBack(OrderCreated event) { /* ... */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void completed(OrderCreated event) { /* ... */ }
~~~

Chúng là đoạn minh họa cho các phương thức thuộc một Spring bean. Muốn dùng trong code thực, cần định nghĩa kiểu event, import và bean sở hữu phương thức.

### `BEFORE_COMMIT` và lỗi

`BEFORE_COMMIT` được kích hoạt trước thao tác commit thật. Listener có thể ném exception khiến transaction rollback; ngay cả khi listener thành công thì việc commit ở database vẫn có thể lỗi. Vì thế gửi một email hoặc gọi API thanh toán không thể hoàn tác tại pha này là nguy hiểm: side effect có thể xảy ra dù dữ liệu bị rollback.

### `AFTER_COMMIT` và data access

Theo hợp đồng Spring, khi chạy callback ở `AFTER_COMMIT`, `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION`, transaction đã commit/rollback, **nhưng resource vẫn có thể đang bound và còn truy cập được**. Một lời gọi repository/JDBC bên trong callback có thể vẫn tham gia resource giao dịch cũ, trong khi **không có lần commit tiếp theo**. Do đó không được mặc định một thay đổi dữ liệu thực hiện trong `AFTER_COMMIT` sẽ được lưu.

Nếu cần ghi dữ liệu sau commit, dùng một **transaction độc lập**, ví dụ gọi một Spring service khác có `@Transactional(propagation = Propagation.REQUIRES_NEW)` **qua proxy** hoặc cấu hình `TransactionTemplate` với `PROPAGATION_REQUIRES_NEW`.

## 5. Ví dụ Java 17+ chạy được: commit, rollback và outside transaction

Ví dụ dùng Spring Framework 6.2.12, H2 và `DataSourceTransactionManager`. Không cần Spring Boot. `TransactionTemplate` mở transaction rõ ràng, và bốn listener tăng bộ đếm theo phase. Ta in **sau khi transaction kết thúc** để không phụ thuộc vào thứ tự callback cùng một giai đoạn.

Cấu trúc:

~~~text
transaction-event-demo/
├── pom.xml
└── src/main/java/demo/TransactionEventDemo.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-event-demo</artifactId>
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

### 5.2. `src/main/java/demo/TransactionEventDemo.java`

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class TransactionEventDemo {
    public record TicketCreated(long ticketId) {}

    public static class Observations {
        final AtomicInteger before = new AtomicInteger();
        final AtomicInteger committed = new AtomicInteger();
        final AtomicInteger rolledBack = new AtomicInteger();
        final AtomicInteger completed = new AtomicInteger();
    }

    @Configuration
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:txevents;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public TransactionTemplate transactionTemplate(PlatformTransactionManager tm) {
            return new TransactionTemplate(tm);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public Observations observations() {
            return new Observations();
        }

        @Bean
        public PhaseListeners phaseListeners(Observations obs) {
            return new PhaseListeners(obs);
        }
    }

    public static class PhaseListeners {
        private final Observations obs;

        public PhaseListeners(Observations obs) {
            this.obs = obs;
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void before(TicketCreated event) {
            obs.before.incrementAndGet();
        }

        // AFTER_COMMIT là phase mặc định.
        @TransactionalEventListener
        public void afterCommit(TicketCreated event) {
            obs.committed.incrementAndGet();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(TicketCreated event) {
            obs.rolledBack.incrementAndGet();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void afterCompletion(TicketCreated event) {
            obs.completed.incrementAndGet();
        }
    }

    private static void show(String label, Observations o) {
        System.out.printf(
            "%s: before=%d commit=%d rollback=%d completion=%d%n",
            label, o.before.get(), o.committed.get(),
            o.rolledBack.get(), o.completed.get());
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            TransactionTemplate tx = ctx.getBean(TransactionTemplate.class);
            Observations obs = ctx.getBean(Observations.class);

            jdbc.execute("CREATE TABLE tickets (id BIGINT PRIMARY KEY, title VARCHAR(60))");

            tx.executeWithoutResult(status -> {
                jdbc.update("INSERT INTO tickets (id, title) VALUES (?, ?)",
                        101L, "created");
                ctx.publishEvent(new TicketCreated(101L));
                show("inside-commit", obs);
            });
            show("after-commit", obs);
            System.out.println("ticket-101=" + jdbc.queryForObject(
                "SELECT COUNT(*) FROM tickets WHERE id = 101", Integer.class));

            tx.executeWithoutResult(status -> {
                jdbc.update("INSERT INTO tickets (id, title) VALUES (?, ?)",
                        102L, "will-rollback");
                ctx.publishEvent(new TicketCreated(102L));
                status.setRollbackOnly();
                show("inside-rollback", obs);
            });
            show("after-rollback", obs);
            System.out.println("ticket-102=" + jdbc.queryForObject(
                "SELECT COUNT(*) FROM tickets WHERE id = 102", Integer.class));

            // Event ngoài transaction: fallbackExecution=false mặc định.
            ctx.publishEvent(new TicketCreated(103L));
            show("outside-tx", obs);
        }
    }
}
~~~

Chạy trong thư mục chứa `pom.xml` (JDK 17+ và Maven):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.TransactionEventDemo
~~~

Các dòng `stdout` của chương trình:

~~~text
inside-commit: before=0 commit=0 rollback=0 completion=0
after-commit: before=1 commit=1 rollback=0 completion=1
ticket-101=1
inside-rollback: before=1 commit=1 rollback=0 completion=1
after-rollback: before=1 commit=1 rollback=1 completion=2
ticket-102=0
outside-tx: before=1 commit=1 rollback=1 completion=2
~~~

**Giải thích cụ thể:**

- **`inside-commit`**: event được phát khi đang ở giữa transaction, nhưng listener transactional mới được đăng ký; chưa đến phase nào nên các bộ đếm vẫn bằng 0.
- **`after-commit`**: `BEFORE_COMMIT`, `AFTER_COMMIT` và `AFTER_COMPLETION` đã chạy; `AFTER_ROLLBACK` không chạy. Bản ghi `ticket-101=1` còn tồn tại sau commit.
- **`inside-rollback`**: callback của event thứ hai vẫn đang chờ transaction kết thúc.
- **`after-rollback`**: vì `status.setRollbackOnly()`, bộ đếm `AFTER_ROLLBACK` và `AFTER_COMPLETION` tăng; `BEFORE_COMMIT` không tăng. Bản ghi `ticket-102=0` đã bị rollback.
- **`outside-tx`**: publish event thứ ba ngoài transaction; cả bốn listener không chạy do `fallbackExecution` mặc định là `false`.

Ví dụ không cần `@EnableTransactionManagement` vì dùng `TransactionTemplate` trực tiếp, không dựa vào AOP `@Transactional` trên service. Với ứng dụng thực dùng `@Transactional`, cần bật transaction management theo cấu hình framework/Spring Boot và gọi qua Spring proxy.

## 6. Không có transaction thì listener làm gì?

Mặc định `@TransactionalEventListener` bỏ qua event được publish ngoài transaction. Để cho phép chạy cả lúc không có transaction, dùng `fallbackExecution=true`:

~~~java
// Đoạn minh họa cho Spring bean.
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void onCreated(OrderCreated event) {
    process(event);
}
~~~

Khi có transaction, listener vẫn đợi commit. Khi **không có transaction**, nó chạy trong lần phát event theo nhánh fallback: lúc này không hề tồn tại commit để chờ. Đó là một **thay đổi ngữ nghĩa nghiệp vụ**, không đơn thuần là cấu hình “để tránh mất event”.

Nếu listener bất ngờ không chạy, nên kiểm tra transaction boundary, proxy AOP, propagation và thread trước khi bật fallback.

## 7. Khi cần ghi dữ liệu sau commit: mở transaction mới

Sau commit, resource cũ có thể vẫn được gắn trong lúc callback chạy. Để ghi audit hoặc cập nhật bảng khác một cách bền vững sau commit, gọi một service riêng có propagation `REQUIRES_NEW`:

~~~java
// Minh họa ý tưởng trên hai Spring bean riêng (không độc lập).
@Service
public class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void persist(String orderId) {
        // auditRepository.save(new Audit(...));
    }
}

@Component
public class AuditListener {
    private final AuditWriter auditWriter;

    public AuditListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onCreated(OrderCreated event) {
        auditWriter.persist(event.orderId());
    }
}
~~~

Cần tách thành bean riêng để lời gọi đến `persist` đi qua Spring AOP proxy. Gọi `this.persist()` trong cùng bean theo proxy mode thông thường sẽ bỏ qua advice. Ví dụ trên dùng `OrderCreated` và repository như tên khái niệm; cần khai báo các class và import thực tế trong ứng dụng.

Chú ý: một giao dịch `REQUIRES_NEW` thành công **không bảo đảm tính nguyên tử** với giao dịch nghiệp vụ đã commit trước đó. Nếu bản ghi audit phải được ghi nguyên tử với thay đổi đơn hàng, hãy ghi audit **trong giao dịch chính**, hoặc dùng bản ghi outbox trong cùng transaction.

## 8. `@Async`, transaction context và reactive transaction

### 8.1. Khi có `@Async`

Với `PlatformTransactionManager`, ngữ cảnh transaction thường gắn với thread. Việc đẩy đoạn `publishEvent` sang một executor khác không tự mang transaction từ thread gốc sang. Nếu event được publish từ thread không có transaction, listener transactional có thể bị bỏ qua.

Đối với `@TransactionalEventListener` kết hợp `@Async`, phần thân listener có thể được schedule chạy sau khi phase đã được kích hoạt. Tuy nhiên, thread chạy callback bất đồng bộ **không tự thừa hưởng transaction cũ**. Do đó không suy ra rằng listener đã chạy xong lúc `TransactionTemplate.execute` trả về, và không dùng `@Order` như bảo đảm thứ tự hoàn thành của các task async.

Cấu hình event multicaster với executor cũng không phải cách hợp lệ để tự chuyển thread-bound transaction sang thread khác. Transactional listener có cơ chế đăng ký synchronization phù hợp với transaction context; cần hiểu rõ cách cấu hình executor tương tác với từng loại listener.

### 8.2. Reactive transaction

Từ Spring Framework 6.1, `@TransactionalEventListener` hỗ trợ cả transaction do `ReactiveTransactionManager` quản lý. Transaction reactive nằm trong **Reactor Context** thay vì `ThreadLocal`. Khi phát event reactive, ngữ cảnh transaction cần được đưa vào `source` của event theo hợp đồng API.

Spring cung cấp `org.springframework.transaction.reactive.TransactionalEventPublisher` để hỗ trợ mang `TransactionContext` vào event phù hợp. Không áp dụng nguyên xi cách truy cập `TransactionSynchronizationManager` thread-bound vào reactive pipeline. Cần bảo đảm pipeline thật sự được subscribe trong ranh giới transaction reactive và event có nguồn context chính xác.

### 8.3. Propagation, nested transaction, nhiều publisher

- `PROPAGATION_REQUIRED` thường tham gia transaction hiện có; event sẽ đợi completion của **transaction vật lý** đang dùng chung, không đợi một lần trả về của phương thức con nếu transaction ngoài vẫn mở.
- `PROPAGATION_REQUIRES_NEW` mở transaction độc lập; event gắn với giao dịch bên trong, có thể được xử lý sau inner commit dù outer transaction về sau rollback.
- Với savepoint/`NESTED`, không mặc định event đã đăng ký sẽ tự bị loại bỏ khi rollback về savepoint; hãy kiểm chứng semantics của transaction manager và thiết kế callback riêng nếu nghiệp vụ phụ thuộc.
- Với nhiều publisher/thread, thời điểm publish và thứ tự completion không tự được đồng bộ hóa toàn cục. `@Order` chỉ hỗ trợ ưu tiên listener trong phạm vi cơ chế dispatch/synchronization phù hợp.

## 9. Độ tin cậy: sau commit không đồng nghĩa đã gửi thành công

Giả sử transaction lưu đơn hàng commit thành công, nhưng process chết **trước khi callback gửi message ra broker hoàn tất**. Database vẫn có đơn hàng, trong khi message có thể không tồn tại. `@TransactionalEventListener(AFTER_COMMIT)` không có cơ chế replay bền vững sẵn có.

Với tích hợp cần retry qua crash, cân nhắc **transactional outbox**:

1. Trong **cùng một transaction**, lưu dữ liệu nghiệp vụ và một bản ghi outbox đại diện cho sự kiện cần gửi.
2. Sau commit, worker/relay đọc outbox, gửi đến broker hoặc hệ thống ngoài.
3. Nếu gửi lỗi, worker retry; khi gửi thành công thì đánh dấu đã xử lý theo quy tắc idempotency.
4. Consumer cũng cần idempotency/deduplication, vì retry có thể làm thông điệp được xử lý nhiều lần.

Outbox không tự đảm bảo exactly-once end-to-end; nó cải thiện độ bền và khả năng phục hồi với thiết kế retry, khóa và idempotency phù hợp.

## 10. Exception, thứ tự và thử nghiệm

- Nếu `BEFORE_COMMIT` ném exception, transaction có thể rollback; không thực hiện side effect bên ngoài không thể thu hồi ở pha này.
- Nếu callback sau commit/rollback thất bại, transaction đã hoàn tất và không thể bị “undo” vì lỗi callback. Hành vi ném/log lỗi cụ thể tùy transaction manager và callback hook; cần logging, metrics và đường retry riêng.
- `@Order` có thể ưu tiên transactional listener, nhưng không tạo thứ tự hoàn thành khi người viết chủ động dùng `@Async` hoặc nhiều transaction khác nhau.
- Không nên dùng listener sau commit để lưu các dữ liệu **bắt buộc nguyên tử** với transaction chính; ghi chúng trong transaction hoặc trong outbox.
- Trong kiểm thử, xác minh cả event publish trước commit, commit thành công, rollback, publish ngoài transaction, lỗi `BEFORE_COMMIT`, `fallbackExecution`, propagation `REQUIRES_NEW` và crash/retry khi có side effect ngoài tiến trình.

### Các lỗi phổ biến

| Sai lầm | Kết quả | Cách xử lý |
| --- | --- | --- |
| Coi `@EventListener` thông thường là after-commit | Tác dụng phụ xảy ra dù DB rollback | Chọn `@TransactionalEventListener(AFTER_COMMIT)` |
| Publish ngoài transaction, không kiểm tra `fallbackExecution` | Event không được listener transactional nhận | Kiểm tra boundary hoặc bật fallback theo chủ đích |
| Sử dụng `BEFORE_COMMIT` để xác nhận nghiệp vụ đã bền vững | Commit sau đó vẫn có thể thất bại | Phân biệt “sắp commit” và “đã commit” |
| Ghi database trong `AFTER_COMMIT` mà không có giao dịch mới | Thao tác có thể không được commit | Dùng `REQUIRES_NEW` qua proxy khi phù hợp |
| Dùng `@Async` và mặc định transaction tự đi theo thread mới | Mất context hoặc sai thời điểm xử lý | Thiết kế lại ranh giới thread và transaction |
| Xem after-commit callback là message queue đáng tin cậy | Có thể mất event sau crash | Outbox, retry, idempotency |
| Trông đợi `@Order` sắp thứ tự hoàn tất async | Callback có thể chạy song song | Dùng workflow/hàng đợi có kiểm soát |

## 11. Checklist lựa chọn thiết kế

1. Listener cần chạy **trước commit**, **sau commit**, **chỉ khi rollback** hay **ở mọi kết cục**?
2. Event đã được publish bên trong **transaction thật** chưa, và có đúng thread/context không?
3. Event ngoài transaction nên bị bỏ qua hay phải xử lý theo `fallbackExecution`?
4. Listener có cần ghi dữ liệu bền vững sau commit không? Nếu có, phải có giao dịch mới hoặc đổi thiết kế.
5. Có bất kỳ side effect nào phải chịu được crash/retry không? Khi đó cân nhắc transactional outbox.
6. Có `@Async`, reactive pipeline, propagation `REQUIRES_NEW` hoặc savepoint không? Cần kiểm thử các ranh giới riêng.
7. Lỗi callback có được ghi log/metrics và có cơ chế phục hồi phù hợp không?

**Ghi nhớ:** `@TransactionalEventListener` không “mang transaction vào listener”; nó **đăng ký một hành động để chạy ở pha cụ thể của transaction hiện tại**. `AFTER_COMMIT` mặc định giúp xử lý sau commit thành công, nhưng không bảo đảm có transaction mới cho thao tác ghi dữ liệu trong callback và không tự tạo độ bền cho việc truyền event ra ngoài.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework — `@TransactionalEventListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework — `TransactionPhase` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Spring Framework — `TransactionSynchronization` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — `TransactionalEventPublisher` (reactive): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html
