# Giới hạn của async listener với transaction trong Spring Application Events

## 1. Bài toán và mô hình tư duy

Một use case tạo đơn hàng thường lưu bản ghi `orders` trong một transaction rồi phát `OrderCreated`. Để giảm thời gian trả HTTP response, nhóm phát triển thêm listener `@Async` để gửi thông báo, cập nhật chỉ mục tìm kiếm hoặc ghi projection. Câu hỏi quan trọng là: **listener bất đồng bộ có thuộc transaction đang tạo đơn không, có thấy dữ liệu chưa commit không, và nếu listener thất bại thì transaction của use case có rollback không?**

Câu trả lời cho trường hợp Spring Framework sử dụng transaction imperative qua `PlatformTransactionManager` là:

- **Không tự tham gia cùng transaction.** Transaction JDBC/JPA của Spring thường gắn tài nguyên với luồng hiện tại; công việc chạy trên executor thread không tự mang theo tài nguyên ấy.
- **Không bảo đảm chạy sau commit.** Task có thể được lên lịch khi transaction publisher vẫn còn mở và chạy trước, trong hoặc sau thời điểm commit/rollback.
- **Không tự truyền lỗi nghiệp vụ ngược về publisher.** Một exception phát sinh trong thân listener sau khi task đã chạy không làm thay đổi giao dịch nguồn đã kết thúc hoặc đang chạy trên luồng khác.

Ba điểm này dễ nhầm với nhau. `@Async` nói về **thực thi trên luồng khác**; `@Transactional` nói về **ranh giới transaction của lời gọi có proxy phù hợp**; `@TransactionalEventListener` nói về **pha giao dịch cần kích hoạt callback**. Mỗi annotation giải quyết một vấn đề riêng.

~~~text
Request thread (publisher)           Worker thread (listener)
--------------------------------     --------------------------------
BEGIN transaction T1
INSERT orders
publishEvent(OrderCreated)
  \-- schedule async task ---------> @Async listener chạy với thread riêng
tiếp tục xử lý                         không tự có transaction T1
COMMIT / ROLLBACK T1                    đọc DB / gọi API / cập nhật projection
trả kết quả HTTP                        hoàn tất hoặc thất bại độc lập
~~~

Với listener đồng bộ mặc định, `publishEvent` thường đợi listener hoàn tất. Với listener async, nó chỉ cần lên lịch thực thi thành công để có thể trở về; thời điểm kết thúc công việc listener không được bảo đảm đồng thời với use case.

## 2. Vì sao Spring không mang transaction sang luồng mới?

`SimpleApplicationEventMulticaster` mặc định gọi listener thường trên cùng luồng với `ApplicationEventPublisher.publishEvent(...)`. Nếu use case có transaction, listener đồng bộ dùng đúng transaction manager và DataSource có thể tham gia transaction đó. Exception runtime chưa xử lý có thể được truyền qua `publishEvent(...)`.

Ví dụ listener đồng bộ, minh họa trong một bean Spring đã có kiểu `OrderCreated`:

~~~java
@EventListener
public void reserveInventory(OrderCreated event) {
    inventoryRepository.reserve(event.orderId());
}
~~~

Còn với async:

~~~java
@Async("eventExecutor")
@EventListener
public void buildSearchIndex(OrderCreated event) {
    projectionRepository.update(event.orderId());
}
~~~

Lời gọi phương thức thứ hai được Spring async infrastructure gửi sang executor khi `@Async` được kích hoạt và proxy vận hành đúng. Trong hệ thống transaction imperative, `TransactionSynchronizationManager` giữ trạng thái transaction/tài nguyên gắn với thread. Executor thread không tự thừa hưởng transaction đó. Nếu listener dùng `JdbcTemplate`, nó thường mở/lấy một connection khác khi không có transaction tương ứng trên thread hiện tại.

Điều này dẫn đến các tình huống:

| Thời điểm async listener đọc dữ liệu | Điều có thể xảy ra |
| --- | --- |
| Trước khi transaction nguồn commit | Dữ liệu chưa commit có thể không nhìn thấy dưới isolation như `READ_COMMITTED`, hoặc truy vấn có thể chờ lock |
| Sau commit | Có thể đọc dữ liệu đã commit nếu truy vấn, cache và isolation phù hợp |
| Sau rollback | Dữ liệu đã rollback không tồn tại trong dữ liệu đã commit |
| Trong khi các request khác đang cập nhật | Có thể gặp dữ liệu mới hơn hoặc trạng thái bị cạnh tranh; cần version/isolation phù hợp |

Không nên dùng `Thread.sleep(...)` rồi kỳ vọng listener chắc chắn nhìn thấy row. Thời gian scheduling thay đổi theo executor, tải máy, DB, lock và cấu hình transaction.

### Async theo annotation và async theo multicaster

Có hai cách phổ biến:

1. Đánh dấu riêng một listener bằng `@Async` và bật `@EnableAsync`. Spring proxy chuyển lời gọi tới executor.
2. Cấu hình bean `applicationEventMulticaster` với `SimpleApplicationEventMulticaster.setTaskExecutor(...)` để multicast qua executor cho các listener **hỗ trợ** thực thi async.

Hai cách có thể cùng tồn tại, nhưng không tương đương hoàn toàn. Đặc biệt trong Spring 6.2, listener đồng bộ theo pha transaction không hỗ trợ bị multicaster dời sang thread khác ở bước đăng ký synchronization; nó cần bắt sự kiện trên thread transaction. Khi phương thức đích còn có `@Async`, **thân công việc hậu xử lý** lại có thể được lên lịch ở thread khác sau pha giao dịch.

## 3. Lỗi async có làm rollback giao dịch nguồn không?

Hãy tách **lỗi khi lên lịch task** và **lỗi khi thực thi task**.

- Nếu executor từ chối task vì quá tải hoặc đang shutdown, việc lên lịch có thể ném exception ngay trong lời gọi `publishEvent`. Tùy cấu hình, publisher có thể nhận lỗi đó.
- Nếu task đã được lên lịch thành công, một exception phát sinh **sau đó** trong thân listener async không tự quay ngược về call stack của publisher. Với `@Async` trên phương thức `void`, Spring có cơ chế `AsyncUncaughtExceptionHandler`; với API async trả future phù hợp, bên gọi tương ứng có thể quan sát kết quả qua future, nhưng `@EventListener` async không biến việc publish thành API chờ kết quả listener.

Đoạn minh họa (cần các bean và import tương ứng):

~~~java
@Async("eventExecutor")
@EventListener
public void notifyCustomer(OrderCreated event) {
    throw new IllegalStateException("Mail server unavailable");
}
~~~

Nếu transaction tạo đơn commit thành công, lỗi gửi mail không làm `orders` tự rollback. Nếu transaction chưa commit nhưng task đã chạy và ném lỗi, publisher cũng không mặc nhiên nhận exception đó để hủy giao dịch.

Ngược lại, listener **đồng bộ** ném `RuntimeException` chưa được xử lý có thể làm `publishEvent` thất bại; khi transaction nguồn bao quanh và rollback rule áp dụng, use case có thể rollback. Vì thế không nên đổi một listener đang **kiểm tra bất biến bắt buộc** (ví dụ đặt chỗ tồn kho, tính tổng tiền quyết định đơn hợp lệ) sang async mà không thay đổi hợp đồng nghiệp vụ.

Trong Spring, `@EventListener` async cũng **không phát tiếp một event bằng cách trả về một giá trị phương thức** như listener đồng bộ có thể làm. Nếu cần phát sự kiện tiếp theo, inject `ApplicationEventPublisher` rồi gọi `publishEvent(...)` một cách tường minh.

## 4. Ví dụ Java 17+ chạy được: so sánh event sau commit và rollback

Ví dụ này dùng Spring Framework 6.2.8, Spring JDBC và H2 trong bộ nhớ, **không cần Spring Boot**. Use case ghi `orders` và publish một event thông thường. Lần thứ nhất commit, lần thứ hai cố ý rollback. Listener async vẫn nhận thông báo đã được lên lịch trong cả hai lần.

Để `stdout` có thứ tự có thể dự đoán, ví dụ truyền hai `CountDownLatch` cho listener: nó đợi cho đến khi transaction nguồn kết thúc rồi mới đọc DB, và báo cho main biết đã xử lý xong. Đây là kỹ thuật trình diễn/kiểm thử, **không phải thiết kế payload event cho production**.

### 4.1. Cấu trúc

~~~text
async-event-transaction/
├── pom.xml
└── src/main/java/AsyncTransactionDemo.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-event-transaction</artifactId>
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
                    <mainClass>AsyncTransactionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Mã nguồn `src/main/java/AsyncTransactionDemo.java`

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class AsyncTransactionDemo {

    // Hai latch chỉ phục vụ việc trình diễn thứ tự trong ví dụ.
    public record OrderSubmitted(
            long id,
            CountDownLatch releaseListener,
            CountDownLatch listenerDone
    ) { }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timeout waiting for listener");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }
    }

    public static final class OrderUseCase {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transactions;
        private final ApplicationEventPublisher events;

        public OrderUseCase(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher events
        ) {
            this.jdbc = jdbc;
            this.transactions = transactions;
            this.events = events;
        }

        public void execute(long id, boolean rollback) {
            CountDownLatch release = new CountDownLatch(1);
            CountDownLatch done = new CountDownLatch(1);
            try {
                try {
                    transactions.executeWithoutResult(status -> {
                        jdbc.update(
                            "INSERT INTO orders (id) VALUES (?)", id
                        );
                        events.publishEvent(
                            new OrderSubmitted(id, release, done)
                        );
                        if (rollback) {
                            throw new IllegalStateException("force rollback");
                        }
                    });
                    System.out.println("USE_CASE id=" + id + " COMMIT");
                } catch (IllegalStateException ex) {
                    if (!"force rollback".equals(ex.getMessage())) {
                        throw ex;
                    }
                    System.out.println("USE_CASE id=" + id + " ROLLBACK");
                }
            } finally {
                // TransactionTemplate đã commit/rollback trước khi tới đây.
                release.countDown();
                await(done);
            }
        }
    }

    // KHÔNG khai báo final: Spring cần tạo proxy cho @Async.
    public static class AsyncOrderObserver {
        private final JdbcTemplate jdbc;

        public AsyncOrderObserver(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Async("eventExecutor")
        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            try {
                await(event.releaseListener());
                boolean active =
                    TransactionSynchronizationManager
                        .isActualTransactionActive();
                int rows = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders WHERE id = ?",
                    Integer.class, event.id()
                );
                System.out.println(
                    "ASYNC id=" + event.id()
                    + " tx=" + active
                    + " rows=" + rows
                );
            } finally {
                event.listenerDone().countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            executor.initialize();
            return executor;
        }

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:async_tx_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbc(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactions(PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        OrderUseCase orderUseCase(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher events
        ) {
            return new OrderUseCase(jdbc, transactions, events);
        }

        @Bean
        AsyncOrderObserver asyncOrderObserver(JdbcTemplate jdbc) {
            return new AsyncOrderObserver(jdbc);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("CREATE TABLE orders (id BIGINT PRIMARY KEY)");

            OrderUseCase useCase = context.getBean(OrderUseCase.class);
            useCase.execute(1L, false);
            useCase.execute(2L, true);

            System.out.println(
                "FINAL rows=" + jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders", Integer.class
                )
            );
        }
    }
}
~~~

Chạy bằng JDK 17+ và Maven từ thư mục dự án:

~~~bash
mvn -q compile exec:java
~~~

Các dòng tự in ra `stdout`, không tính log phụ của Maven:

~~~text
USE_CASE id=1 COMMIT
ASYNC id=1 tx=false rows=1
USE_CASE id=2 ROLLBACK
ASYNC id=2 tx=false rows=0
FINAL rows=1
~~~

### 4.3. Giải thích kết quả

- **Đơn 1:** `TransactionTemplate` chèn `orders(id=1)`, lên lịch event rồi commit. Use case in `COMMIT`, mở latch; lúc đó listener mới đọc DB và thấy một bản ghi. `tx=false` cho thấy thread listener không có transaction thực tế đang hoạt động ở điểm kiểm tra.
- **Đơn 2:** `TransactionTemplate` chèn `orders(id=2)` và lên lịch event, sau đó ném `IllegalStateException("force rollback")`. Transaction bị rollback. Use case in `ROLLBACK` rồi mở latch. Listener đã được lên lịch vẫn chạy, nhưng truy vấn không thấy đơn `2` đã rollback.
- **Kết luận từ phép thử:** `@Async @EventListener` không có cơ chế mặc định thu hồi task khi publisher rollback; việc listener được gọi không phải bằng chứng dữ liệu gốc đã commit. `FINAL rows=1` xác nhận kết quả cuối cùng của hai transaction.

Dùng latch ở đây để tạo **thứ tự quan sát xác định**. Nếu bỏ latch, listener có thể query trước commit; kết quả nhìn thấy hàng phụ thuộc isolation/cơ sở dữ liệu và thời điểm thực thi. Đây không phải thiết kế event nên dùng trong production: payload chỉ nên mang dữ liệu nghiệp vụ và định danh cần thiết, không gắn đối tượng đồng bộ luồng vào hợp đồng domain.

Lưu ý Maven/Java của ví dụ cần tải dependency khi chưa có trong cache. Bài minh họa dùng một executor với một worker và chờ từng event hoàn tất trước khi tiếp tục; không mô tả thứ tự hoàn thành được bảo đảm trong mọi ứng dụng có pool nhiều thread.

## 5. `@Transactional` trên async listener tạo ra transaction nào?

Một cách sửa thường thấy là thêm `@Transactional` vào listener async:

~~~java
@Async("eventExecutor")
@Transactional
@EventListener
public void updateProjection(OrderCreated event) {
    // Nếu transaction proxy được áp dụng, transaction ở thread executor.
}
~~~

Đây là đoạn minh họa trong một bean Spring có sẵn kiểu event. Annotation transaction có thể mở transaction **mới cho công việc ở worker thread** nếu proxy hoạt động và các bean được cấu hình phù hợp. Nó **không tái sử dụng transaction T1** của use case publisher. Nếu T1 rollback, T2 không tự rollback; nếu T2 lỗi, T1 không tự bị đảo ngược.

Cần phân biệt:

- `Propagation.REQUIRED` nghĩa là tham gia transaction **đã có trên thread được gọi**, hoặc mở mới nếu không có. Worker thread không tự có transaction T1.
- `Propagation.REQUIRES_NEW` chủ động dùng transaction độc lập; trong async worker vốn đã tách thread, nó càng không làm T2 gắn vào T1.
- `@Transactional` và `@Async` thường dựa vào proxy; self-invocation hoặc class/phương thức `final` làm proxy class-based không hoạt động như mong đợi. Với Spring AOP proxy class-based, đừng đặt `final` lên một class không có interface mà cần `@Async`.
- Transaction manager của worker chỉ quản lý resource trong phạm vi transaction của worker. Gửi email, gọi HTTP hoặc message broker không tự trở thành thao tác rollback được bởi JDBC transaction.

Với một **bước bắt buộc** phải làm use case thất bại nếu không thành công (ví dụ kiểm tra tồn kho để quyết định tạo đơn), gọi service đồng bộ bên trong transaction của use case sẽ có hợp đồng rõ hơn. Async listener phù hợp với hậu xử lý có thể retry, chạy chậm hoặc chấp nhận eventual consistency.

## 6. Chỉ chạy sau commit: `@TransactionalEventListener`

Khi listener chỉ được phép xử lý **đơn đã commit**, giải pháp đơn giản là nghe theo pha giao dịch:

~~~java
@Component
public class ProjectionListener {
    @Async("eventExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCommitted(OrderCreated event) {
        // Truy cập dữ liệu đã commit và cập nhật projection riêng.
    }
}
~~~

Đây là **đoạn minh họa** (cần `OrderCreated`, executor và import `Component`, `Async`, `TransactionalEventListener`, `TransactionPhase`). Khi use case publish event **bên trong transaction đang hoạt động**, Spring đăng ký callback. Với `AFTER_COMMIT`, callback chỉ được kích hoạt khi transaction commit thành công. Nếu transaction rollback, listener `AFTER_COMMIT` không được kích hoạt cho event đó.

Bảng pha:

| Phase | Khi nào chạy | Hợp với |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước commit | Kiểm tra/công việc cần xảy ra sát commit, hiểu rõ ranh giới |
| `AFTER_COMMIT` (mặc định) | Sau commit thành công | Notification, projection, hậu xử lý chỉ dựa trên dữ liệu đã commit |
| `AFTER_ROLLBACK` | Sau rollback | Theo dõi thất bại hoặc lên kế hoạch xử lý bù |
| `AFTER_COMPLETION` | Sau khi giao dịch kết thúc, commit hoặc rollback | Theo dõi kết quả hoàn tất |

**Những điểm quan trọng:**

1. Nếu publish event **ngoài transaction**, mặc định `@TransactionalEventListener` không gọi handler; có thể dùng `fallbackExecution=true` khi thực sự chấp nhận xử lý không có transaction.
2. `@TransactionalEventListener` chọn **thời điểm kích hoạt**, còn `@Async` chọn **cơ chế thực thi thân phương thức**. Một callback đã được gắn vào pha transaction có thể gửi tác vụ async sang executor sau commit.
3. Trong Spring Framework 6.2, listener dạng transaction-synchronized cần được multicaster gọi trên thread transaction để đăng ký synchronization. Vì thế không suy luận rằng cấu hình async executor ở cấp multicaster sẽ đẩy mọi transactional listener sang thread khác.
4. `AFTER_COMMIT` không đưa transaction T1 sang worker thread. Nếu listener cần ghi DB, dùng transaction mới có chủ đích cho các cập nhật đó.
5. Transaction đã commit thì exception xảy ra ở listener sau commit **không làm rollback dữ liệu đã commit**.
6. Sau commit, một số resource giao dịch có thể còn tạm gắn trên thread callback nhưng transaction đã hoàn tất; đừng nhầm rằng các thao tác DB tại thời điểm ấy sẽ tự có lần commit tiếp theo. Nên thiết lập transaction mới rõ ràng khi ghi DB hậu xử lý.

Đối với **reactive transaction**, Spring 6.1+ còn hỗ trợ listener theo giao dịch Reactor, nhưng Reactor context khác với ThreadLocal của JDBC/JPA imperative; sự kiện cần mang thông tin transaction theo cơ chế được hỗ trợ, ví dụ `TransactionalEventPublisher`. Không áp nguyên xi ví dụ thread-bound cho reactive flow.

## 7. Vấn đề còn lại: tính bền vững và retry

`@TransactionalEventListener(AFTER_COMMIT)` tránh xử lý event của transaction rollback, nhưng **không phải hàng đợi bền vững**. Tình huống mất event vẫn có thể xảy ra:

~~~text
COMMIT đơn hàng thành công
    |
    +-- ứng dụng chết trước khi callback được lên lịch
    |
    +-- executor từ chối task vì quá tải
    |
    +-- task đã nhận nhưng thất bại và không có retry bền vững
~~~

Nếu đồng bộ tìm kiếm có thể tái dựng hoặc email phụ trợ được phép thất bại tạm thời, xử lý sau commit cùng giám sát có thể đủ. Nhưng nếu thông điệp tích hợp **không được phép mất** sau commit, cần cơ chế ghi nhận ý định bền vững, ví dụ **transactional outbox**.

Luồng outbox:

1. Trong cùng transaction tạo đơn, ghi `orders` và một bản ghi `outbox` mô tả event, có event ID.
2. Khi transaction rollback, cả đơn và bản ghi outbox rollback; khi commit, cả hai tồn tại.
3. Một dispatcher riêng đọc outbox đã commit, phát message và lưu trạng thái xử lý/retry.
4. Consumer xử lý idempotent theo event ID vì thông điệp có thể bị gửi lặp khi retry.

Outbox thường hướng đến **at-least-once delivery**, không phải bảo đảm toàn hệ thống “exactly once” một cách tự động. Cần theo dõi số lần retry, dead letter, độ trễ, idempotency, việc dọn bản ghi và trường hợp hai dispatcher cạnh tranh cùng bản ghi.

## 8. Payload và context khi đổi luồng

Đối với async listener, nên truyền **định danh hoặc DTO bất biến**:

~~~java
public record OrderCreated(long orderId, String customerId) { }
~~~

Tránh truyền JPA entity đang managed rồi giả định worker sẽ có cùng persistence context. Entity có lazy association có thể gây `LazyInitializationException` khi transaction/session gốc đã đóng, hoặc trạng thái dữ liệu đã thay đổi giữa lúc publish và lúc xử lý. Sau `AFTER_COMMIT`, worker có thể mở transaction mới để đọc lại dữ liệu theo ID. Nếu cần **snapshot lúc publish**, đưa những trường cần thiết vào event hoặc bản ghi outbox.

Ngoài transaction, các context khác như logging MDC, security context, request scope, tracing và custom `ThreadLocal` cũng không mặc nhiên theo mọi executor. Có thể dùng `TaskDecorator` hoặc thư viện context propagation để mang **những dữ liệu context an toàn** sang worker; đó **không phải** cách đưa JDBC connection, EntityManager hay transaction nguồn qua thread. Tự sao chép `TransactionSynchronizationManager` sang thread khác có thể vi phạm vòng đời connection/session và an toàn đồng thời.

**Thứ tự:** khi executor có nhiều worker, thứ tự hoàn thành của các event không đồng nghĩa thứ tự publish. Nếu projection cần thứ tự, dùng sequence/version, phân vùng theo khóa nghiệp vụ hoặc một cơ chế xử lý có hợp đồng ordering rõ; thêm idempotency để chống ghi lùi trạng thái.

## 9. Cách chọn cơ chế theo yêu cầu

| Yêu cầu nghiệp vụ | Cơ chế nên cân nhắc |
| --- | --- |
| Không được tạo đơn nếu chưa giữ được hàng | Gọi service đồng bộ bên trong cùng transaction |
| Gửi notification chỉ khi đơn commit; có thể chấp nhận mất task nếu process chết | `@TransactionalEventListener(AFTER_COMMIT)`, có thể kết hợp `@Async` |
| Cập nhật projection độc lập, có thể retry | Sau commit, transaction riêng cho worker, giám sát và idempotency |
| Gửi message sang hệ thống khác không được phép mất | Transactional outbox + dispatcher + retry + consumer idempotent |
| Quan sát lý do rollback | `@TransactionalEventListener(AFTER_ROLLBACK)` hoặc observability ở transaction boundary |
| Thực hiện một phép tính bắt buộc ảnh hưởng kết quả giao dịch | Xử lý đồng bộ; không dựa vào async listener để rollback publisher |

Khi kết hợp nhiều listener, đừng giả định `@Order` trên các listener biến quá trình async thành một chuỗi có thể rollback đồng loạt. `@Order` chỉ điều khiển một phần trật tự gọi listener trong những cấu hình hỗ trợ; nó không tạo transaction xuyên thread, không hủy side effect đã xảy ra và không bảo đảm delivery.

## 10. Kiểm thử và chẩn đoán lỗi

Một bộ kiểm thử nên bao gồm cả **commit, rollback, lỗi task và process restart**. Quan sát trạng thái sau khi transaction đã hoàn tất, không chỉ đếm số lần phương thức listener được gọi.

| Ca | Điều cần xác nhận |
| --- | --- |
| Publish trong transaction commit, listener async thông thường | Task không tự có transaction T1; dữ liệu chỉ đọc ổn định khi đã commit |
| Publish rồi rollback, `@Async @EventListener` | Task vẫn có thể chạy dù dữ liệu rollback |
| Publish rồi rollback, `@TransactionalEventListener(AFTER_COMMIT)` | Không gọi listener sau commit cho transaction bị rollback |
| Listener async ném `RuntimeException` | Publisher không tự rollback bởi exception ở thân task |
| Executor từ chối task | Phân biệt scheduling failure với execution failure; có chính sách backpressure |
| Listener `@Transactional` ở worker | Giao dịch của worker độc lập với transaction publisher |
| Hệ thống chết sau commit trước gửi notification | Xác nhận replay/outbox nếu delivery là yêu cầu bắt buộc |
| Nhiều event cập nhật cùng entity | Kiểm tra thứ tự, sequence/version, idempotency |
| Listener đọc JPA entity lazy sau request | Không phụ thuộc session của publisher |

Để kiểm tra transaction imperative đang hoạt động trên thread, có thể log `TransactionSynchronizationManager.isActualTransactionActive()` tại điểm publish và trong listener. Tuy nhiên `true` không chứng minh mọi resource trong hệ thống đều thuộc cùng transaction vật lý: còn phải kiểm tra transaction manager, DataSource, propagation và chính kết quả commit/rollback.

Trong integration test, tránh bọc toàn bộ test bằng một transaction chưa commit rồi kỳ vọng async worker đọc được dữ liệu; điều đó có thể tạo hành vi khác production và che giấu lỗi. Dùng latch/future hoặc công cụ chờ có timeout để chốt thời điểm; đừng chờ bằng một giấc ngủ cố định. Kiểm thử hậu xử lý nên quan sát cả task thất bại, retry và shutdown executor.

## 11. Lỗi thường gặp

1. **Tưởng `@Async` kế thừa transaction nguồn:** transaction imperative không tự theo `ThreadLocal` sang worker.
2. **Tưởng publish trong `@Transactional` đồng nghĩa event chạy sau commit:** async listener thường có thể được lên lịch trước commit.
3. **Dùng async để kiểm tra bất biến bắt buộc:** exception từ worker không phải một hợp đồng rollback cho use case.
4. **Thêm `@Transactional` vào worker rồi cho rằng là T1:** worker có thể bắt đầu T2 độc lập.
5. **Dùng `sleep` đoán thời điểm commit:** gây lỗi không ổn định; chọn transaction phase hoặc đồng bộ đúng cơ chế.
6. **Quên cấu hình `@EnableAsync`/proxy hoặc dùng bean `final` không thể proxied:** `@Async` có thể không có tác dụng như mong muốn.
7. **Truyền mutable entity/persistence context:** dữ liệu và vòng đời session có thể khác khi worker xử lý.
8. **Không xử lý lỗi của task:** cần handler, metrics, retry và cách cảnh báo phù hợp.
9. **Nhầm after-commit với bảo đảm không mất event:** crash giữa commit và schedule vẫn có thể mất công việc.
10. **Dùng transaction context propagation tùy tiện:** connection/EntityManager không được thiết kế để dùng như đối tượng chia sẻ xuyên thread.
11. **Bỏ qua thứ tự event và idempotency:** worker pool có thể xử lý lệch thứ tự, retry có thể gây tác động trùng.

## 12. Bài tập tự kiểm tra

1. `@Transactional` tạo đơn, publish event, rồi chủ động rollback. `@Async @EventListener` có tự bị hủy không? Vì sao?
2. Trong demo, nếu bỏ hai latch, tại sao câu SELECT của async listener có thể không nhìn thấy dữ liệu ngay cả với đơn cuối cùng sẽ commit?
3. Đặt `@Transactional` trên listener async có làm giao dịch của listener trở thành transaction của publisher không?
4. Khi nào dùng `@TransactionalEventListener(AFTER_COMMIT)`, và vì sao vẫn cần outbox cho thông điệp quan trọng?
5. Vì sao `@TransactionalEventListener(BEFORE_COMMIT)` kết hợp `@Async` không thể được coi là “chờ async task hoàn tất trước khi commit”?
6. Nếu listener async ném exception, cần thiết kế cơ chế nào để không âm thầm mất công việc?
7. Tại sao cần truyền `orderId` hoặc DTO bất biến thay vì entity managed, và nên làm gì nếu worker cần đọc lại dữ liệu?
8. Nếu có hai event cập nhật projection cùng đơn, bạn sẽ tránh trạng thái bị ghi lùi bằng cách nào?

**Định hướng:** (1) không; task thông thường có thể đã được lên lịch trước rollback; (2) thread worker không ở cùng transaction, dữ liệu chưa commit có thể chưa thấy; (3) không, thường là một transaction mới ở worker; (4) chỉ sau commit, nhưng không bền vững khi crash, nên cần outbox/retry; (5) phase đăng ký callback và thân task bất đồng bộ là hai việc khác nhau; (6) giám sát, retry, idempotency/dead-letter; (7) mở transaction mới ở worker, query theo ID hoặc mang snapshot; (8) sequence/version, ordering theo khóa và idempotency.

## Tài liệu tham khảo

- Spring Framework Reference, *Application Events / Asynchronous Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference, *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2.8 Javadoc, *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2.8 Javadoc, *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
