# Mở transaction mới cho tác vụ hậu commit trong Spring Framework

## 1. Vì sao tác vụ chạy sau commit vẫn cần transaction mới?

Trong Spring Framework, một nghiệp vụ có thể phát sự kiện bên trong transaction và dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` để thực hiện công việc **chỉ sau khi transaction chính commit thành công**. Tuy nhiên, “đã commit” **không đồng nghĩa** mọi tài nguyên và trạng thái liên quan đến transaction cũ đã được dọn dẹp ngay lập tức.

Ở thời điểm callback hậu commit chạy, tài nguyên giao dịch như JDBC `Connection` hoặc persistence context có thể vẫn đang gắn với thread. Một lời gọi truy cập dữ liệu thông thường có thể tiếp tục tham gia vào ngữ cảnh giao dịch cũ, trong khi **không còn một lần commit tiếp theo** để lưu thay đổi mới. Điều này đặc biệt nguy hiểm khi listener ghi thêm audit log, bản ghi thông báo hoặc trạng thái xử lý mà ứng dụng kỳ vọng được lưu bền vững.

**Cách thực hiện đúng khi cần ghi cơ sở dữ liệu sau commit:** gọi một phương thức của **Spring bean khác** có `@Transactional(propagation = Propagation.REQUIRES_NEW)`. Spring tạo một transaction vật lý độc lập cho tác vụ này; thành công thì commit riêng, thất bại thì rollback riêng. Cơ chế này được Spring khuyến nghị rõ trong Javadoc của `TransactionSynchronization.afterCommit()` và `afterCompletion()`.

Các ý cần tách bạch:

- **`AFTER_COMMIT`** là thời điểm callback được gọi so với transaction gốc.
- **`REQUIRES_NEW`** là chính sách propagation khi bắt đầu một phạm vi công việc có quản lý transaction.
- `AFTER_COMMIT` **không tự động tạo transaction mới**.
- `@Transactional` không ghi rõ propagation sẽ mặc định là `REQUIRED`. Trong ngữ cảnh hậu commit, `REQUIRED` có thể tham gia tài nguyên còn gắn với transaction vừa hoàn tất, gây ra thao tác ghi **không được commit như kỳ vọng**.
- Một transaction mới **không biến hậu commit thành một phần nguyên tử của transaction trước**. Transaction chính đã commit xong; lỗi hậu commit không thể đảo ngược dữ liệu đã commit trước đó.

Bài này tập trung vào mô hình transaction **imperative** của Spring với `PlatformTransactionManager`, Spring JDBC/JPA và event listener chạy đồng bộ theo callback. Với ứng dụng reactive, transaction nằm trong Reactor Context nên cần thiết kế tương ứng thay vì suy luận từ `ThreadLocal`.

## 2. Hiểu đúng vòng đời `@TransactionalEventListener`

Giả sử `OrderService.placeOrder()` được gọi thông qua Spring transaction proxy:

```text
Caller
  |
  v
@Transactional OrderService.placeOrder()
  |
  +-- BEGIN transaction T1
  |
  +-- INSERT đơn hàng
  |
  +-- publishEvent(OrderPlaced)
  |     |
  |     +-- @TransactionalEventListener(AFTER_COMMIT)
  |           đăng ký callback cho transaction T1
  |
  +-- kết thúc phương thức nghiệp vụ
  |
  +-- COMMIT T1 thành công
  |
  +-- chạy callback AFTER_COMMIT
  |     |
  |     +-- AuditService.saveAudit()
  |           @Transactional(REQUIRES_NEW)
  |             |
  |             +-- BEGIN transaction T2 độc lập
  |             +-- INSERT audit
  |             +-- COMMIT T2
  |
  +-- hoàn tất callback / cleanup của T1
```

Mặc định, `@TransactionalEventListener` dùng pha `AFTER_COMMIT`. Nếu sự kiện phát ra khi **không có transaction đang hoạt động**, listener sẽ không chạy, trừ khi cấu hình `fallbackExecution = true`. Với `fallbackExecution = true`, listener có thể chạy ngay khi không có transaction, nên không còn bảo đảm “chỉ sau commit”.

Các pha thường dùng:

| `TransactionPhase` | Khi listener chạy | Lưu ý |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction gốc commit | Vẫn có thể tham gia công việc transaction gốc; không phải pha hậu commit. |
| `AFTER_COMMIT` | Sau khi transaction gốc commit thành công | Dùng transaction mới cho thao tác DB cần commit riêng. |
| `AFTER_ROLLBACK` | Sau khi transaction gốc rollback | Có thể lưu thông tin lỗi/bù trừ trong transaction mới. |
| `AFTER_COMPLETION` | Sau khi transaction gốc hoàn tất, bất kể commit hay rollback | Cần xác định rõ xử lý có nên chạy ở cả hai kết quả. |

**Chi tiết kỹ thuật:** `@TransactionalEventListener(AFTER_COMMIT)` của Spring được xử lý qua transaction synchronization và thường được gọi trong nhánh hoàn tất transaction với trạng thái đã commit. Vì vậy không nên đồng nhất chính xác nó với việc tự triển khai `TransactionSynchronization.afterCommit()`, dù cả hai đều xảy ra sau commit. Tại các callback sau hoàn tất, tài nguyên cũ có thể chưa được giải phóng nên nguyên tắc `REQUIRES_NEW` vẫn cần thiết.

## 3. Vì sao `@Transactional(REQUIRED)` dễ gây sai lệch sau commit?

Xét đoạn code minh họa sau (chưa phải chương trình độc lập):

```java
@Component
class OrderListener {
    private final AuditService auditService;

    OrderListener(AuditService auditService) {
        this.auditService = auditService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void afterCommit(OrderPlaced event) {
        auditService.saveAudit(event.orderId());
    }
}

@Service
class AuditService {
    @Transactional // mặc định REQUIRED: không phải lựa chọn an toàn ở đây
    public void saveAudit(String orderId) {
        // JDBC/JPA insert audit row
    }
}
```

`REQUIRED` có nghĩa: tham gia transaction phù hợp đang tồn tại, hoặc mở mới nếu không có transaction. Trong callback hậu commit, transaction gốc **đã commit**, nhưng Spring vẫn có thể giữ tài nguyên và trạng thái synchronization trong lúc gọi callback. Truy cập DB lúc này có thể “tham gia” tài nguyên cũ và **không có commit mới** cho thao tác vừa thực hiện. Trong JPA, việc thay đổi entity có thể nhìn thấy trong persistence context nhưng không được flush/commit theo cách mong đợi.

Thay bằng:

```java
@Service
class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(String orderId) {
        // JDBC/JPA insert audit row
    }
}
```

Đây cũng là mã minh họa; `OrderPlaced` và thao tác truy cập dữ liệu do ứng dụng định nghĩa. Các annotation cần import từ `org.springframework.stereotype`, `org.springframework.transaction.annotation` và `org.springframework.transaction.event`.

`REQUIRES_NEW` yêu cầu một **transaction vật lý độc lập**; Spring tạm tách/ngưng các tài nguyên của transaction cũ nếu còn ràng buộc, bắt đầu transaction mới cho khối công việc và commit/rollback khối đó khi phương thức thoát. Với JDBC, transaction mới thường cần một connection khác. Vì vậy cần bảo đảm pool kết nối đủ năng lực khi có nhiều tác vụ đồng thời; không coi transaction mới là miễn phí.

## 4. Ví dụ Java 17+ chạy được: transaction T1 của đơn hàng và T2 của audit

Ví dụ dùng **Spring Framework 6.2.12**, **Spring JDBC** và **H2 in-memory**, không dùng Spring Boot. Nó cho thấy:

1. Khi `OrderService` commit thành công, listener `AFTER_COMMIT` được gọi và `AuditWriter` tạo transaction mới để ghi audit.
2. Khi transaction của `OrderService` rollback, listener `AFTER_COMMIT` không chạy và không có bản ghi audit cho đơn hàng thất bại.
3. Cả hai kết quả được kiểm tra bằng truy vấn DB sau khi service hoàn tất.

Tạo cấu trúc:

```text
after-commit-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AfterCommitDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'after-commit-demo'
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
    mainClass = 'demo.AfterCommitDemo'
}
```

`src/main/java/demo/AfterCommitDemo.java`:

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

public class AfterCommitDemo {

    public record OrderPlaced(String orderId) {}

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void place(String orderId, boolean abort) {
            jdbc.update("insert into orders (id) values (?)", orderId);
            System.out.println("publisher: inserted " + orderId);

            publisher.publishEvent(new OrderPlaced(orderId));
            System.out.println("publisher: after publish " + orderId);

            if (abort) {
                throw new IllegalStateException("order aborted");
            }
        }
    }

    public static class AuditWriter {
        private final JdbcTemplate jdbc;

        public AuditWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void persist(String orderId) {
            jdbc.update("insert into audit_log (order_id) values (?)", orderId);
            System.out.println("writer: inserted audit " + orderId);
        }
    }

    public static class PostCommitListener {
        private final AuditWriter writer;

        public PostCommitListener(AuditWriter writer) {
            this.writer = writer;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            System.out.println("listener: AFTER_COMMIT " + event.orderId());
            writer.persist(event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:after_commit_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        OrderService orderService(JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        AuditWriter auditWriter(JdbcTemplate jdbc) {
            return new AuditWriter(jdbc);
        }

        @Bean
        PostCommitListener postCommitListener(AuditWriter writer) {
            return new PostCommitListener(writer);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService service = context.getBean(OrderService.class);

            jdbc.execute("create table orders (id varchar(40) primary key)");
            jdbc.execute(
                    "create table audit_log (order_id varchar(40) primary key)");

            service.place("A-1", false);
            System.out.println("after success: orders="
                    + jdbc.queryForObject(
                            "select count(*) from orders", Integer.class)
                    + ", audit="
                    + jdbc.queryForObject(
                            "select count(*) from audit_log", Integer.class));

            try {
                service.place("B-2", true);
            } catch (IllegalStateException ex) {
                System.out.println("caught: " + ex.getMessage());
            }

            System.out.println("after rollback: orders="
                    + jdbc.queryForObject(
                            "select count(*) from orders", Integer.class)
                    + ", audit="
                    + jdbc.queryForObject(
                            "select count(*) from audit_log", Integer.class));
        }
    }
}
```

Chạy bằng **JDK 17+** và Gradle đã được cài:

```bash
gradle -q run
```

Các dòng `System.out.println` trong ứng dụng, theo thứ tự:

```text
publisher: inserted A-1
publisher: after publish A-1
listener: AFTER_COMMIT A-1
writer: inserted audit A-1
after success: orders=1, audit=1
publisher: inserted B-2
publisher: after publish B-2
caught: order aborted
after rollback: orders=1, audit=1
```

Giải thích:

1. `context.getBean(OrderService.class)` lấy đối tượng qua Spring, cho phép transaction proxy áp dụng `@Transactional` của phương thức `place`. Không nên tự `new OrderService(...)` trong chương trình thực rồi mong annotation tự tạo giao dịch.
2. `publishEvent(...)` xảy ra khi transaction T1 của đơn hàng còn hoạt động. Listener `AFTER_COMMIT` **chưa xử lý ngay tại điểm phát sự kiện**, nên dòng `publisher: after publish ...` xuất hiện trước dòng listener.
3. Với `A-1`, T1 commit thành công. Spring kích hoạt callback `AFTER_COMMIT`, listener gọi `writer.persist(...)` qua **một bean khác** có transaction proxy, mở transaction T2 mới. `audit_log` được commit độc lập khi `persist` kết thúc. Vì thế DB có `orders=1, audit=1`.
4. Với `B-2`, `IllegalStateException` đi ra khỏi phương thức `@Transactional`. Quy tắc mặc định rollback với unchecked exception làm T1 rollback. Listener `AFTER_COMMIT` không chạy cho event `B-2`; DB vẫn có một bản ghi mỗi bảng.
5. Dòng `writer: inserted audit A-1` xuất hiện **bên trong** transaction T2, trước thời điểm proxy thực hiện commit của T2. Chính kết quả truy vấn `audit=1` sau khi lời gọi service kết thúc mới cho thấy dữ liệu được lưu bền vững trong demo.
6. `DriverManagerDataSource` được dùng cho ví dụ ngắn; ứng dụng production thường dùng connection pool như HikariCP, với monitoring và giới hạn tài nguyên phù hợp.

Ở ví dụ này listener chạy **đồng bộ trong callback hậu commit**, vì không có `@Async` hay executor tại event multicaster. `REQUIRES_NEW` tạo transaction mới nhưng **không tạo thread mới**: hai khái niệm độc lập.

## 5. Vì sao cần gọi sang bean khác thay vì `this.saveAudit()`?

Spring mặc định áp dụng `@Transactional` thông qua proxy (ví dụ JDK proxy hoặc CGLIB proxy). Lời gọi nội bộ từ một phương thức đến phương thức khác trong **cùng instance**, như `this.saveAudit()`, thường **bỏ qua transaction interceptor**.

Ví dụ mắc lỗi:

```java
@Component
class WrongPostCommitListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void afterCommit(OrderPlaced event) {
        this.saveAudit(event.orderId());
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(String orderId) {
        // Có annotation nhưng self-invocation không kích hoạt proxy.
    }
}
```

Đây chỉ là code minh họa với `OrderPlaced` do ứng dụng định nghĩa và các import Spring tương ứng. `this.saveAudit(...)` là lời gọi Java trực tiếp trên target, không đi qua advice của proxy. Vì vậy **không thể kết luận T2 đã được mở** dù annotation `REQUIRES_NEW` xuất hiện trong mã.

Cách đáng tin cậy là tách hai trách nhiệm:

```text
OrderService @Transactional(T1)
      |
      +-- publish event
             |
             +-- PostCommitListener.afterCommit(...)
                    |
                    +-- auditWriter.persist(...)
                           Spring proxy của AuditWriter
                               |
                               +-- @Transactional(REQUIRES_NEW) -> T2
```

Inject `AuditWriter` qua constructor như ví dụ đầy đủ. Đặt phương thức được transactional interception ở mức `public`, trong Spring-managed bean có thể proxy, và gọi nó **qua bean proxy**. Với AspectJ transaction weaving, quy tắc self-invocation có thể khác; bài này dùng chế độ proxy phổ biến.

## 6. `REQUIRES_NEW` khác gì với `REQUIRED`, `NESTED` và `@Async`?

| Cơ chế | Ý nghĩa | Phù hợp cho ghi DB sau commit? |
| --- | --- | --- |
| `Propagation.REQUIRED` | Tham gia transaction đang tồn tại nếu có, nếu không thì mở mới. | **Không nên dựa vào** trong callback hậu commit khi tài nguyên cũ chưa cleanup. |
| `Propagation.REQUIRES_NEW` | Luôn tạo transaction vật lý độc lập, tạm tách transaction hiện có. | **Có**, khi cần một lần commit riêng được quản lý rõ ràng. |
| `Propagation.NESTED` | Dùng nested scope/savepoint nếu transaction manager hỗ trợ, vẫn nằm trong transaction vật lý bên ngoài. | Không thay thế transaction vật lý độc lập hậu commit. |
| `@Async` | Chuyển execution sang executor/thread khác khi async proxy áp dụng. | Không tự định nghĩa transaction; thường kết hợp một service giao dịch riêng. |
| `@TransactionalEventListener(AFTER_COMMIT)` | Chỉ định callback sau commit thành công. | Quy định thời điểm, nhưng tự nó không tạo transaction mới. |

Một số hệ quả:

- `REQUIRES_NEW` có transaction status, timeout, isolation và rollback rules riêng theo cách cấu hình. Khi transaction T2 đã commit, nó không bị rollback chỉ vì T1 từng thất bại hoặc ngược lại.
- Trong bài toán hậu commit, T1 đã commit thành công trước khi callback T2 bắt đầu. Nếu T2 thất bại, **T1 vẫn đã commit**; yêu cầu nghiệp vụ phải quyết định có retry, cảnh báo, bù trừ hay lưu công việc cần làm.
- Trong những lời gọi `REQUIRES_NEW` *bên trong* một transaction T1 vẫn đang mở, có thể cần một connection thứ hai khi T1 đang giữ connection thứ nhất. Pool quá nhỏ dưới tải đồng thời có thể cạn kết nối hoặc gây deadlock; phải tính toán giới hạn kết nối và concurrency.
- `@Async` chạy trên thread khác sẽ không tự mang theo JDBC transaction, `EntityManager`, security context hoặc MDC của thread phát sự kiện. Không dùng việc đổi thread như một “mẹo” thay cho thiết kế propagation chính thức.

## 7. Hậu commit thất bại: tại sao không thể rollback transaction gốc?

Giả sử T1 tạo đơn hàng và đã commit. Sau đó callback gọi T2 để ghi audit nhưng DB báo lỗi:

```text
T1: INSERT orders('A-1')  -> COMMIT thành công
                             |
                             v
                  AFTER_COMMIT listener
                             |
                             v
                  T2: INSERT audit_log
                             |
                             x-- lỗi / ROLLBACK T2
```

Đơn hàng `A-1` vẫn tồn tại vì T1 đã commit trước lỗi T2. Không có cơ chế tự động biến chúng thành một transaction nguyên tử xuyên qua thời gian commit. Kể cả exception từ callback được ném ra và làm caller thấy lỗi, điều đó **không hoàn tác được commit của T1**. Đường đi/báo cáo exception phụ thuộc callback cụ thể; ví dụ `@TransactionalEventListener(AFTER_COMMIT)` được kích hoạt trong cơ chế hoàn tất transaction, lỗi listener có thể được Spring ghi log mà không truyền về nơi phát sự kiện. Vì vậy không dùng exception của callback làm bảo đảm phát lại công việc.

Cần thiết kế hành vi thất bại cho tác vụ hậu commit:

- **Idempotency:** dùng khóa nghiệp vụ hoặc unique constraint (như `audit_log.order_id` ở ví dụ) để chạy lại mà không tạo bản ghi trùng; khi retry, phân biệt “đã xử lý” và lỗi khác.
- **Observability:** ghi log theo `eventId`/`orderId`, metric số tác vụ lỗi, thời gian xử lý và cảnh báo.
- **Retry có giới hạn:** xử lý lỗi tạm thời bằng backoff; không retry vô hạn trên thread request hoặc trong callback transaction.
- **Persisted work queue / transactional outbox:** khi hậu commit không được phép thất lạc, ghi bản ghi outbox **trong chính T1** rồi worker độc lập đọc và gửi/ghi kết quả. Outbox bảo đảm dữ liệu nghiệp vụ và yêu cầu xử lý tiếp được commit cùng nhau. Việc phân phối/đánh dấu hoàn tất vẫn cần idempotency và retry.
- **Bù trừ có chủ đích:** nếu nghiệp vụ bắt buộc phải sửa trạng thái đơn hàng khi bước hậu commit lỗi, tạo transaction mới rõ ràng cho hành động bù trừ; đừng mặc định rollback ngược thời gian.

`REQUIRES_NEW` giải quyết **ranh giới commit mới**, không giải quyết crash, retry hay giao hàng đúng một lần. Sự kiện Spring Application Events là thông báo trong bộ nhớ, không thay thế message broker bền vững.

## 8. Khi nào dùng `TransactionTemplate` thay cho annotation?

Một số trường hợp cần transaction mới bên trong callback mà không muốn thêm bean riêng, có thể dùng `TransactionTemplate` với propagation `REQUIRES_NEW`. Cách này gọi thẳng transaction manager nên không phụ thuộc vào việc lời gọi đi qua AOP proxy.

Ví dụ **đoạn minh họa** (các dependency và event do ứng dụng định nghĩa):

```java
@Component
class PostCommitAuditHandler {

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactionTemplate;

    PostCommitAuditHandler(JdbcTemplate jdbc,
            PlatformTransactionManager transactionManager) {
        this.jdbc = jdbc;
        this.transactionTemplate =
                new TransactionTemplate(transactionManager);
        this.transactionTemplate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderPlaced event) {
        transactionTemplate.executeWithoutResult(status ->
                jdbc.update(
                        "insert into audit_log(order_id) values (?)",
                        event.orderId()));
    }
}
```

Cần import các loại tương ứng từ `org.springframework.stereotype.Component`, `org.springframework.jdbc.core.JdbcTemplate`, `org.springframework.transaction.PlatformTransactionManager`, `org.springframework.transaction.TransactionDefinition`, `org.springframework.transaction.support.TransactionTemplate` và `org.springframework.transaction.event.*`.

`TransactionTemplate.executeWithoutResult(...)` mở và hoàn tất một transaction mới theo cấu hình; exception ném trong callback có thể khiến transaction mới rollback. Đây là lựa chọn rõ ràng khi bạn muốn điều khiển ranh giới giao dịch bằng code. Tuy vậy, dùng bean `AuditWriter` với `@Transactional(REQUIRES_NEW)` thường dễ đọc, dễ test và dễ tái sử dụng hơn.

## 9. Kết hợp với xử lý bất đồng bộ

Đối với notification, email hoặc indexing, một listener sau commit có thể đồng thời là `@Async`:

```java
@Async("postCommitExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    auditWriter.persist(event.orderId());
    // Tiếp tục xử lý tác vụ khác nếu cần.
}
```

Đây là **đoạn minh họa**, cần `@EnableAsync`, bean executor tên `postCommitExecutor`, Spring-managed listener và `OrderPlaced`/`auditWriter` tương ứng. Spring đăng ký callback theo transaction của publisher trước; khi đến pha sau commit, async proxy có thể submit phần xử lý listener sang executor. Trên worker thread, transaction T1 không được mang theo, vì vậy `auditWriter.persist(...)` vẫn là nơi khai báo transaction cần thiết.

Những điểm không nên bỏ qua:

- `@Async` chỉ có tác dụng nếu lời gọi đi qua async proxy của Spring; self-invocation bỏ qua proxy trong chế độ mặc định.
- Thread pool có thể từ chối task hoặc bị shutdown; event trong bộ nhớ không bảo đảm xử lý thành công qua crash.
- Exceptions của phương thức async trả `void` thường đi vào `AsyncUncaughtExceptionHandler`/log, không quay về publisher như exception đồng bộ.
- Tác vụ async có thể xong sau khi request trả về; test phải dùng latch/future/Awaitility có timeout, không dựa vào `Thread.sleep()` ngẫu nhiên.
- Với `@TransactionalEventListener` dùng transaction imperative, callback đăng ký dựa trên transaction của publisher. Nếu chính thao tác *phát event* bị chuyển sang thread khác **trước commit**, listener có thể không thấy transaction và bị bỏ qua; cần phân biệt async publisher với async processing sau commit.

Vì vậy `AFTER_COMMIT` giải quyết **thời điểm**, `REQUIRES_NEW` giải quyết **transaction cho ghi dữ liệu**, còn `@Async` giải quyết **thread thực thi**. Chúng bổ trợ nhau nhưng không đồng nghĩa.

## 10. Kiểm thử thực tế và dấu hiệu sai

Một bộ kiểm thử cho luồng hậu commit nên bao gồm:

1. **Commit thành công:** bắt đầu T1, phát event, commit; sau đó kiểm tra bản ghi nghiệp vụ và audit cùng tồn tại. Nếu callback đồng bộ, kiểm tra sau lời gọi service là đủ; nếu callback async, chờ tín hiệu hoàn tất có timeout.
2. **Rollback T1:** tạo lỗi trong transaction gốc, xác nhận listener `AFTER_COMMIT` không ghi audit.
3. **Rollback T2:** cố ý tạo lỗi ở `AuditWriter`, xác minh thay đổi T2 không có nhưng bản ghi của T1 đã commit vẫn tồn tại.
4. **Ngữ cảnh không có transaction:** phát event ngoài transaction; mặc định listener `@TransactionalEventListener` không chạy. Kiểm tra riêng nếu sử dụng `fallbackExecution = true`.
5. **Self-invocation:** gọi method `REQUIRES_NEW` bằng `this` để phát hiện việc proxy không chạy; test nên dùng dữ liệu thực tế sau commit thay vì chỉ dựa vào annotation có mặt.
6. **Quá tải/kết nối:** đo hiệu suất dưới concurrency, pool size, timeout và độ trễ callback; không giả định `REQUIRES_NEW` dùng lại miễn phí connection T1.
7. **Lỗi tồn tại lâu:** kiểm tra retry/idempotency hoặc outbox nếu đây là tác vụ bắt buộc phải hoàn thành.

**Lưu ý về test có `@Transactional`:** Một phương thức test được bao bởi `@Transactional` trong Spring Test thường sẽ rollback khi test kết thúc. Nếu bạn chỉ gọi `publishEvent()` rồi assert ngay, listener `AFTER_COMMIT` có thể **chưa từng chạy**. Muốn kiểm tra chính xác pha sau commit, hãy dùng test không bao transaction mặc định, hoặc dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` trong test được cấu hình phù hợp.

Các lỗi phổ biến:

| Dấu hiệu | Nguyên nhân đáng kiểm tra | Cách sửa |
| --- | --- | --- |
| Listener `AFTER_COMMIT` có log nhưng audit không lưu | Viết bằng `REQUIRED` khi tài nguyên T1 chưa cleanup; không có commit mới | Đưa lệnh ghi qua bean `REQUIRES_NEW` hoặc `TransactionTemplate`. |
| Có annotation `REQUIRES_NEW` nhưng vẫn không mở T2 | `this.method()` bỏ qua proxy | Tách `AuditWriter` thành Spring-managed bean và inject. |
| Event phát khi không có transaction nên không có callback | `@TransactionalEventListener` mặc định bỏ qua | Phát trong transaction thật; chỉ bật `fallbackExecution` nếu chấp nhận ý nghĩa khác. |
| Rollback T1 nhưng callback hậu commit vẫn được kỳ vọng chạy | Nhầm pha transaction | Dùng `AFTER_ROLLBACK` nếu cần xử lý khi rollback. |
| T2 lỗi nhưng T1 vẫn tồn tại | Hai transaction commit độc lập | Thiết kế retry/bù trừ và quan sát lỗi; không kỳ vọng rollback T1. |
| Tăng tải làm thiếu connection | `REQUIRES_NEW` cần connection độc lập khi tài nguyên cũ còn giữ | Tính capacity connection pool và giới hạn concurrency. |
| Test không thấy hậu commit | Test transaction chưa commit, hoặc bị rollback tự động | Hoàn tất transaction thật trước assertion. |
| Tác vụ chạy trùng sau retry | Không có idempotency key | Thêm khóa nghiệp vụ/unique constraint và chiến lược retry. |

## 11. Checklist thiết kế cho tác vụ hậu commit

Trước khi đưa một listener sau commit vào production, hãy trả lời:

- Tác vụ **thực sự cần chạy sau commit** hay phải cùng transaction với thay đổi gốc? Nếu cần tính nguyên tử, hãy thực hiện trước commit trong T1 hoặc ghi outbox cùng T1.
- Nếu tác vụ sau commit ghi DB, ranh giới `REQUIRES_NEW` nằm ở **Spring-managed bean/proxy** nào?
- T2 thất bại thì xử lý ra sao? Có idempotency, retry, monitoring và trạng thái phục hồi chưa?
- Listener chạy đồng bộ hay bất đồng bộ? Có thể làm chậm request hoặc cạn connection/thread pool không?
- Có cần đảm bảo xử lý qua crash? Nếu có, event trong bộ nhớ chỉ là một phần của giải pháp; thường cần outbox và worker bền vững.

**Nguyên tắc áp dụng:** Sau khi T1 commit, muốn ghi dữ liệu hậu commit hãy tạo T2 độc lập bằng `REQUIRES_NEW` (hoặc `TransactionTemplate` tương đương) và gọi qua đúng ranh giới Spring transaction. `AFTER_COMMIT` chỉ chọn thời điểm; T2 có kết quả commit/rollback riêng và cần kế hoạch xử lý thất bại riêng.

## Tài liệu tham khảo

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — `TransactionSynchronization.afterCommit()` và `afterCompletion()`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — Transaction Propagation (`REQUIRED`, `REQUIRES_NEW`, `NESTED`)](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Proxying Mechanisms và self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Declarative transaction rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
