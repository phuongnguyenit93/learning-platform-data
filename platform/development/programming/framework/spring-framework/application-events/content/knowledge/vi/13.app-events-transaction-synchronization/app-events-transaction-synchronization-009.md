# Rollback và event phụ thuộc transaction trong Spring Framework

## 1. Event phụ thuộc transaction là gì?

Khi một ứng dụng Spring phát sự kiện bằng `ApplicationEventPublisher.publishEvent(...)` bên trong phương thức `@Transactional`, thường có hai yêu cầu rất khác nhau:

1. **Phản ứng ngay khi sự kiện được phát:** chẳng hạn cập nhật một bảng khác trong cùng transaction. `@EventListener` đồng bộ mặc định chạy ngay khi multicaster phân phối sự kiện, kể cả khi transaction gốc sau đó rollback.
2. **Phản ứng theo kết quả transaction:** chỉ gửi xác nhận khi **commit thành công**, hoặc chỉ ghi nhận sự cố khi transaction **rollback**. `@TransactionalEventListener` gắn lời gọi listener với một pha transaction (`TransactionPhase`) phù hợp.

Một event được phát **không có nghĩa thay đổi dữ liệu đã commit**. Sự kiện có thể đã được tạo, listener thường đã chạy, nhưng transaction về sau vẫn rollback. Tương tự, rollback không tự tạo event mới: `@TransactionalEventListener(AFTER_ROLLBACK)` chỉ được gọi nếu event tương ứng đã được phát và được đăng ký với transaction trước khi transaction hoàn tất.

Bài này tập trung vào transaction kiểu **imperative** do `PlatformTransactionManager` quản lý, chẳng hạn `DataSourceTransactionManager` hoặc `JpaTransactionManager`. Trong Spring reactive, transaction được quản lý qua Reactor Context và cách gắn sự kiện với transaction có khác biệt.

## 2. Cơ chế gắn listener với kết quả commit/rollback

Spring hỗ trợ bốn `TransactionPhase`:

| Pha | Khi nào listener được thực thi? | Tình huống điển hình |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trong callback trước khi cố gắng commit, khi transaction vẫn có thể bị rollback | Kiểm tra, flush hoặc cập nhật dữ liệu phải thuộc transaction chính |
| `AFTER_COMMIT` | Sau khi transaction commit thành công | Gửi thông báo xác nhận, kích hoạt xử lý hậu commit |
| `AFTER_ROLLBACK` | Sau khi transaction đã rollback | Dọn tài nguyên tạm, ghi nhận một lần xử lý thất bại |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất, dù commit hay rollback | Dọn dẹp chung, thống kê hoặc giám sát kết thúc |

`@TransactionalEventListener` **mặc định là `AFTER_COMMIT`**, không phải chạy ngay như `@EventListener`.

Luồng minh họa:

```text
@Transactional service
    |
    +-- bắt đầu transaction T1
    +-- thay đổi dữ liệu
    +-- publishEvent(OrderAttempted)
    |      |
    |      +-- @EventListener: xử lý ngay (nếu đồng bộ)
    |      |
    |      +-- @TransactionalEventListener:
    |             đăng ký callback tương ứng với T1
    |
    +-- service kết thúc
           |
           +-- T1 commit thành công
           |      +-- AFTER_COMMIT
           |      +-- AFTER_COMPLETION
           |
           +-- T1 rollback
                  +-- AFTER_ROLLBACK
                  +-- AFTER_COMPLETION
```

`BEFORE_COMMIT` nằm trước bước commit và **không phải bằng chứng chắc chắn sẽ commit**; lỗi tại chính pha này vẫn có thể dẫn đến rollback. `AFTER_COMPLETION` cho biết callback chạy ở cả hai kết quả, nhưng phương thức listener nhận event thông thường **không được truyền trực tiếp mã kết quả commit/rollback**. Nếu cần phân biệt rõ hai nhánh, dùng hai listener theo pha; nếu cần mã trạng thái thấp hơn, có thể dùng `TransactionSynchronization.afterCompletion(int status)`.

### Ví dụ cú pháp listener

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollback(OrderAttempted event) {
    // Chỉ gọi sau rollback của transaction đã đăng ký event.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommit(OrderAttempted event) {
    // Chỉ gọi sau commit thành công.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void onCompleted(OrderAttempted event) {
    // Chạy sau khi transaction hoàn tất theo một trong hai kết quả.
}
```

Đây là **các phương thức minh họa**, phải nằm trong bean được Spring quản lý; `OrderAttempted` là loại event do ứng dụng định nghĩa. Cần import `TransactionalEventListener` và `TransactionPhase` thuộc Spring Transaction.

## 3. Điều gì khiến một transaction rollback?

Không nên đồng nhất **“có exception”** với **“chắc chắn rollback”**. Kết quả phụ thuộc transaction manager, ranh giới proxy, propagation và chính sách rollback.

### 3.1. Quy tắc mặc định của `@Transactional`

Với thiết lập declarative transaction thông thường:

- Exception kế thừa `RuntimeException` hoặc `Error` **thoát ra qua ranh giới `@Transactional`** thường kích hoạt rollback.
- Checked exception (ví dụ `IOException`) **mặc định không** kích hoạt rollback, trừ khi khai báo `rollbackFor`, sử dụng quy tắc rollback phù hợp hoặc đã cấu hình default rollback rules khác.
- Nếu exception **được bắt và xử lý hoàn toàn trong phương thức transactional**, interceptor có thể nhìn thấy kết thúc bình thường và cố commit.
- Có thể chủ động đánh dấu transaction là **rollback-only**, bất kể phương thức trả về bình thường.

Ví dụ, với một checked exception trong phương thức service:

```java
@Transactional(rollbackFor = IOException.class)
public void importOrders() throws IOException {
    // Nếu IOException thoát khỏi phương thức,
    // transaction sẽ rollback theo rollbackFor.
}
```

Đây là đoạn mã minh họa; cần import `java.io.IOException` và `org.springframework.transaction.annotation.Transactional`. Không nên chọn `rollbackFor = Exception.class` cho toàn bộ ứng dụng mà không xem xét ý nghĩa nghiệp vụ của từng exception.

Đánh dấu rollback-only trong ngữ cảnh transaction đang được Spring quản lý:

```java
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
```

Câu lệnh này chỉ phù hợp khi đang thực thi trong transaction context mà Spring transaction aspect quản lý; cần import `org.springframework.transaction.interceptor.TransactionAspectSupport`. Nó không tự phát event. Một transaction bị đánh dấu rollback-only có thể rollback tại ranh giới hoàn tất dù phương thức Java không ném exception.

### 3.2. `REQUIRED` và lỗi `UnexpectedRollbackException`

Trong cấu trúc gọi lồng nhau, một phương thức `@Transactional(propagation = REQUIRED)` tham gia transaction vật lý bên ngoài. Nếu phạm vi bên trong đánh dấu transaction chung là rollback-only nhưng caller bên ngoài bắt exception và vẫn cố commit, Spring có thể ném `UnexpectedRollbackException` ở ranh giới commit ngoài: caller cần biết rằng commit được yêu cầu nhưng thực tế đã rollback.

**Điều cần nhớ:** Listener `AFTER_ROLLBACK` dựa vào **kết quả hoàn tất transaction thực tế**, không phụ thuộc việc caller có nhìn thấy exception cụ thể nào. `AFTER_ROLLBACK` có thể chạy với rollback-only, timeout, lỗi commit dẫn đến rollback hoặc quyết định rollback khác của transaction manager.

### 3.3. Transaction lồng nhau và savepoint

`Propagation.NESTED` có thể sử dụng savepoint bên trong **cùng transaction vật lý**, tùy transaction manager hỗ trợ. Rollback về một savepoint **không nhất thiết** là rollback hoàn toàn của transaction bên ngoài.

Ví dụ, một thao tác nhỏ rollback về savepoint nhưng transaction T1 ngoài vẫn commit. Nếu event được đăng ký với sự hoàn tất của T1, không được mặc định cho rằng listener `AFTER_ROLLBACK` của T1 sẽ chạy chỉ vì một savepoint đã rollback. Khi cần quan sát savepoint, Spring 6.2 có `TransactionSynchronization.savepoint(...)` và `savepointRollback(...)` cho tình huống thích hợp; đó là cơ chế khác với `@TransactionalEventListener(AFTER_ROLLBACK)`.

Ngược lại, `Propagation.REQUIRES_NEW` mở một transaction vật lý riêng: rollback của transaction con mới **không tự làm rollback transaction ngoài**. Event gắn với transaction nào phải được xem theo ngữ cảnh đang hoạt động ở thời điểm `publishEvent()`.

## 4. Ví dụ Java 17+ chạy được: event sau commit và event sau rollback

Ví dụ Spring Framework thuần dùng `Spring JDBC` và H2 in-memory, không cần Spring Boot. Nó minh họa:

1. Tạo đơn hàng `ok-1` thành công: chỉ listener `AFTER_COMMIT` chạy.
2. Tạo đơn hàng `bad-1` rồi ném `IllegalStateException`: transaction tạo đơn hàng rollback, chỉ listener `AFTER_ROLLBACK` chạy.
3. Listener rollback ghi một dòng vào bảng `rollback_audit` thông qua **transaction mới** với `Propagation.REQUIRES_NEW`. Bản ghi audit tồn tại dù bản ghi đơn hàng thất bại đã rollback.

Cấu trúc dự án:

```text
transaction-rollback-events/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/RollbackEventDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'transaction-rollback-events'
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
    mainClass = 'demo.RollbackEventDemo'
}
```

`src/main/java/demo/RollbackEventDemo.java`:

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

public class RollbackEventDemo {

    public record OrderAttempted(String orderId) {}

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
        public void place(String orderId, boolean reject) {
            jdbc.update("insert into orders (id) values (?)", orderId);
            System.out.println("publisher: inserted " + orderId);

            publisher.publishEvent(new OrderAttempted(orderId));
            System.out.println("publisher: after publish " + orderId);

            if (reject) {
                throw new IllegalStateException("rejected " + orderId);
            }
        }
    }

    public static class RollbackAuditWriter {
        private final JdbcTemplate jdbc;

        public RollbackAuditWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void recordFailure(String orderId) {
            jdbc.update(
                    "insert into rollback_audit (order_id) values (?)",
                    orderId);
            System.out.println("audit writer: recorded " + orderId);
        }
    }

    public static class LifecycleListener {
        private final RollbackAuditWriter writer;

        public LifecycleListener(RollbackAuditWriter writer) {
            this.writer = writer;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void committed(OrderAttempted event) {
            System.out.println("commit listener: " + event.orderId());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBack(OrderAttempted event) {
            System.out.println("rollback listener: " + event.orderId());
            writer.recordFailure(event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:rollback_events;DB_CLOSE_DELAY=-1");
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
        OrderService orderService(
                JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        RollbackAuditWriter rollbackAuditWriter(JdbcTemplate jdbc) {
            return new RollbackAuditWriter(jdbc);
        }

        @Bean
        LifecycleListener lifecycleListener(RollbackAuditWriter writer) {
            return new LifecycleListener(writer);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService service = context.getBean(OrderService.class);

            jdbc.execute("create table orders (id varchar(40) primary key)");
            jdbc.execute(
                    "create table rollback_audit (order_id varchar(40) primary key)");

            service.place("ok-1", false);
            System.out.println("success: orders=" + count(jdbc, "orders")
                    + ", rollback_audit=" + count(jdbc, "rollback_audit"));

            try {
                service.place("bad-1", true);
            } catch (IllegalStateException ex) {
                System.out.println("caught: " + ex.getMessage());
            }

            System.out.println("failure: orders=" + count(jdbc, "orders")
                    + ", rollback_audit=" + count(jdbc, "rollback_audit"));
        }
    }

    private static int count(JdbcTemplate jdbc, String tableName) {
        // tableName chỉ là các hằng "orders"/"rollback_audit" trong demo.
        return jdbc.queryForObject(
                "select count(*) from " + tableName, Integer.class);
    }
}
```

Chạy với JDK 17+ và Gradle đã cài:

```bash
gradle -q run
```

Các dòng `System.out.println` của chương trình, theo đúng thứ tự:

```text
publisher: inserted ok-1
publisher: after publish ok-1
commit listener: ok-1
success: orders=1, rollback_audit=0
publisher: inserted bad-1
publisher: after publish bad-1
rollback listener: bad-1
audit writer: recorded bad-1
caught: rejected bad-1
failure: orders=1, rollback_audit=1
```

### Phân tích kết quả

**Nhánh thành công (`ok-1`):**

- `OrderService.place(...)` được gọi qua bean từ Spring context, vì vậy transaction proxy bắt đầu T1.
- Dòng đơn hàng được INSERT và event được phát trong T1. Listener theo transaction chỉ đăng ký callback, nên `publisher: after publish ok-1` xuất hiện trước listener.
- T1 commit. `committed(...)` thuộc `AFTER_COMMIT` chạy, còn `rolledBack(...)` không chạy.
- Database có một đơn hàng, chưa có dòng rollback audit.

**Nhánh thất bại (`bad-1`):**

- Dòng đơn hàng được INSERT trong T2 và event được phát khi T2 còn hoạt động.
- `IllegalStateException` thoát qua proxy của phương thức `@Transactional`, nên T2 rollback theo quy tắc mặc định.
- Sau rollback, listener `rolledBack(...)` được gọi. `writer.recordFailure(...)` đi qua một bean Spring khác có `@Transactional(REQUIRES_NEW)`, tạo transaction T3 độc lập để INSERT `rollback_audit` và commit.
- Đơn hàng `bad-1` không tồn tại sau rollback; dòng audit `bad-1` vẫn tồn tại vì nó được commit bằng T3.
- Exception gốc được bắt bên ngoài phương thức service, sau khi transaction interceptor đã hoàn tất rollback và callback. Vì vậy dòng `caught: ...` xuất hiện sau dòng listener và writer.

**Chú ý quan trọng:** Dòng log `audit writer: recorded ...` in bên trong transaction T3, trước khi proxy của writer commit T3. Bằng chứng audit thực sự được lưu là kết quả truy vấn `rollback_audit=1` sau khi phương thức kết thúc.

Ví dụ dùng `DriverManagerDataSource` để dễ học, không có pool kết nối. Ứng dụng production nên dùng connection pool có giới hạn và theo dõi mức sử dụng, nhất là khi `REQUIRES_NEW` cần một connection khác trong lúc tài nguyên transaction trước còn gắn với thread.

## 5. Vì sao ghi dữ liệu trong listener `AFTER_ROLLBACK` phải mở transaction mới?

Đây là một lỗi quan trọng trong transaction synchronization:

> Transaction đã rollback/commit xong, nhưng tài nguyên transaction có thể vẫn còn truy cập được trong callback hoàn tất. Một lời gọi DB có thể gắn vào ngữ cảnh cũ dù **không còn commit tiếp theo**.

Vì vậy đoạn mã như sau không đáng tin cậy để lưu audit hậu rollback:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollback(OrderAttempted event) {
    jdbc.update(
            "insert into rollback_audit (order_id) values (?)",
            event.orderId());
}
```

Đây là đoạn minh họa, không phải chương trình độc lập. `JdbcTemplate` có thể tìm thấy tài nguyên gắn với transaction vừa rollback và không có một transaction mới để commit thao tác ghi. Trong môi trường JPA, một `EntityManager` còn liên kết với ngữ cảnh cũ cũng có thể gây hiểu nhầm về việc entity đã được persist.

**Cách đúng khi cần một lần commit riêng:** đưa thao tác ghi sang một bean có phương thức:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordFailure(String id) {
    // Insert vào audit với transaction độc lập.
}
```

Rồi gọi nó **qua Spring bean proxy** từ listener. Trong ví dụ đầy đủ, đó là `RollbackAuditWriter`.

`@Transactional` mặc định với propagation `REQUIRED` **không thay thế** yêu cầu mở transaction độc lập ở callback sau hoàn tất; tài nguyên cũ có thể còn gắn với thread. `REQUIRES_NEW` tạm ngưng/tách ràng buộc hiện có rồi tạo transaction vật lý khác. Nếu T3 thất bại thì audit có thể mất, nhưng trạng thái rollback của T2 không bị “hoàn tác” hay đổi thành commit.

Có thể dùng `TransactionTemplate` với `PROPAGATION_REQUIRES_NEW` để tạo transaction theo cách lập trình:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

template.executeWithoutResult(status ->
        jdbc.update("insert into rollback_audit(order_id) values (?)", id));
```

Đây là đoạn minh họa cần các biến `transactionManager`, `jdbc`, `id` và import `TransactionTemplate`, `TransactionDefinition`. Ưu điểm là không phụ thuộc việc gọi sang một bean khác để áp dụng transactional advice. Với `@Transactional` trên method, tránh self-invocation như `this.recordFailure(...)`, vì proxy transaction có thể bị bỏ qua.

## 6. `@EventListener` thông thường có bị “thu hồi” khi rollback không?

**Không.** Một `@EventListener` được gọi đồng bộ tại lúc `publishEvent()` diễn ra. Spring không tự “quay lại quá khứ” để hủy các side effect listener đã thực hiện.

Ví dụ:

```java
@EventListener
public void onOrderAttempted(OrderAttempted event) {
    emailClient.sendMessage(event.orderId());
}
```

Đây là mã minh họa: `emailClient` do ứng dụng định nghĩa. Nếu email được gửi **trước** khi DB rollback thì rollback không thể thu hồi email. Tương tự, HTTP call hoặc thông điệp đã gửi ra broker không tự bị rollback bởi transaction JDBC. Do đó một listener đồng bộ thông thường chỉ nên thực hiện thao tác ngoài hệ thống trước commit khi thực sự chấp nhận được hệ quả đó.

Ngược lại, nếu `@EventListener` đồng bộ dùng **cùng JDBC transaction** để ghi một bảng nội bộ, thao tác ghi ấy có thể rollback cùng publisher. Đây là khác biệt giữa **side effect tham gia cùng transaction** và **side effect bên ngoài transaction**.

| Tình huống | Event/listener | Hệ quả khi T1 rollback |
| --- | --- | --- |
| Listener đồng bộ dùng cùng JDBC transaction | `@EventListener` | Ghi DB thuộc T1 rollback cùng T1 |
| Listener đồng bộ gọi dịch vụ bên ngoài | `@EventListener` | HTTP/email đã gửi không tự được hoàn tác |
| Listener đăng ký sau commit | `@TransactionalEventListener(AFTER_COMMIT)` | Không chạy khi T1 rollback |
| Listener đăng ký sau rollback | `@TransactionalEventListener(AFTER_ROLLBACK)` | Chạy khi transaction gắn event rollback |
| Listener chạy ở cả hai kết quả | `@TransactionalEventListener(AFTER_COMPLETION)` | Chạy sau khi T1 hoàn tất |
| Listener hậu rollback ghi DB qua T3 | `@Transactional(REQUIRES_NEW)` trong bean khác | T3 commit/rollback độc lập với T1 |

## 7. Điều kiện đăng ký: phải phát event khi có transaction phù hợp

`@TransactionalEventListener` chỉ có ý nghĩa khi sự kiện được phát trong ngữ cảnh transaction đang hoạt động phù hợp. Không có transaction thì mặc định listener **không chạy**.

Ví dụ, lời gọi này ở ngoài transaction:

```java
publisher.publishEvent(new OrderAttempted("no-tx"));
```

Nếu không có transaction và listener dùng cấu hình mặc định, cả `AFTER_COMMIT` lẫn `AFTER_ROLLBACK` đều không được gọi. Muốn cho phép fallback:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK,
        fallbackExecution = true)
public void handle(OrderAttempted event) {
    // Có thể chạy cả khi không có transaction; khi đó
    // không có rollback thực tế để chờ hoặc bảo đảm.
}
```

Đây chỉ là mã minh họa: `OrderAttempted` do ứng dụng định nghĩa. `fallbackExecution = true` thay đổi ngữ nghĩa nghiệp vụ: khi không có transaction, callback có thể được thực hiện theo đường fallback, **không có bằng chứng rollback**. Với tác vụ bắt buộc chỉ chạy nếu rollback thật, thường giữ mặc định `false` và bảo đảm publisher thực sự chạy trong transaction.

Các tình huống khiến bạn tưởng mình đang phát trong transaction nhưng thực ra không có transaction mong đợi:

- Phương thức `@Transactional` được gọi bằng `this.method()` trong cùng bean, bỏ qua proxy.
- Bean được tạo bằng `new` thay vì do Spring quản lý.
- Transaction chỉ tồn tại ở **thread khác**, ví dụ event được publish từ một method `@Async` hoặc `Executor` khác. Transaction imperative gắn với thread không tự truyền sang thread mới.
- Phương thức không có transaction thực tế do cấu hình transaction manager/proxy sai hoặc đã chạy ngoài ranh giới transaction.

Từ Spring 6.1, `@TransactionalEventListener` còn hỗ trợ reactive transaction, nhưng transaction reactive nằm trong **Reactor Context**. Khi dùng `ReactiveTransactionManager`, cần đưa ngữ cảnh transaction vào nguồn event theo API được Spring hỗ trợ, chẳng hạn `TransactionalEventPublisher`, thay vì dựa vào `TransactionSynchronizationManager` kiểu thread-bound. Ví dụ JDBC ở mục 4 **không dùng reactive transaction**.

## 8. Callback lỗi, rollback-only và thứ tự xử lý

### 8.1. Exception trong `BEFORE_COMMIT`

Listener `BEFORE_COMMIT` chạy trước commit; một runtime exception phù hợp có thể được truyền ra caller của commit và dẫn đến rollback. Nếu logic cần ngăn transaction commit, đây có thể là vị trí cần xem xét, nhưng vẫn phải thiết kế lỗi theo quy tắc transaction và thời điểm callback.

Một exception trong `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION` xảy ra **sau khi** kết quả của transaction đã được quyết định. Trong cơ chế `TransactionSynchronization.afterCompletion(...)`, runtime exception được Spring log, **không bảo đảm truyền lại caller**. Vì vậy không dùng việc exception có tới caller hay không để suy luận listener hậu rollback đã hoàn thành thành công.

### 8.2. Callback sau rollback không rollback thêm lần nữa

Khi T1 đã rollback, lỗi của listener `AFTER_ROLLBACK` **không thể rollback T1 một lần nữa**. Nếu listener tạo transaction T3 để ghi audit mà T3 thất bại, chỉ có T3 rollback; T1 vẫn rollback theo kết quả trước đó.

Vì vậy, nếu audit rollback là dữ liệu quan trọng, cần có monitoring, retry và lưu yêu cầu công việc theo cách bền vững. Callback trong bộ nhớ không bảo đảm chạy thành công trong trường hợp ứng dụng crash hoặc tiến trình bị kill đúng lúc.

### 8.3. `@Order` và nhiều listener

`@Order` có thể điều chỉnh thứ tự callback/listener tương ứng trong Spring, nhưng không biến nhiều listener thành một transaction nguyên tử. Một listener bị lỗi có thể ảnh hưởng listener khác khác nhau tùy pha và cơ chế gọi; đừng dựa vào thứ tự ngầm định hoặc tính “tất cả cùng thành công”. Nếu các bước phải commit cùng nhau, nên viết chúng trong **một transaction rõ ràng** hoặc một luồng xử lý có điều phối và kiểm soát lỗi.

### 8.4. Rollback transaction không phải mọi rollback lồng nhau

Nếu một hoạt động nằm trong `REQUIRES_NEW`, callback gắn với transaction mới được xử lý theo kết quả transaction mới ấy. Nếu nghiệp vụ trong transaction ngoài rollback nhưng transaction trong đã commit độc lập, callback AFTER_COMMIT cho transaction trong có thể đã chạy. Với `NESTED`, rollback về savepoint không nhất thiết hoàn tất transaction ngoài. Để bảo đảm ngữ nghĩa, hãy ghi nhận rõ *transaction nào sở hữu event* và *scope nào bắt đầu/kết thúc transaction*.

## 9. Phân biệt `@Async` với listener theo pha transaction

`@Async` giải quyết **thread thực thi**, còn `@TransactionalEventListener` giải quyết **thời điểm so với kết quả transaction**.

Ví dụ minh họa:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void notifyAfterCommit(OrderAttempted event) {
    // Khi callback hậu commit được kích hoạt, @Async có thể
    // đưa phần xử lý sang executor đã đặt tên.
}
```

Cần `@EnableAsync`, bean executor `eventExecutor` và listener thuộc Spring-managed bean. Đoạn mã này không tự bảo đảm giao hàng bền vững: khi task chưa chạy mà process chết, công việc có thể mất.

Với `AFTER_ROLLBACK`, nếu cần xử lý bất đồng bộ nhưng phải lưu audit:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollbackAsync(OrderAttempted event) {
    auditWriter.recordFailure(event.orderId());
}
```

Đây là đoạn minh họa, giả định `auditWriter` là bean riêng có phương thức `@Transactional(REQUIRES_NEW)`. `@Async` không tự tạo transaction; worker thread không thừa hưởng JDBC transaction của thread publisher. Khi xử lý hậu rollback trên thread khác, transaction mới vẫn nên được khai báo tại service làm việc với database.

**Cảnh báo:** Nếu bản thân việc `publishEvent()` diễn ra ở một thread khác trước khi transaction gốc hoàn tất, listener phụ thuộc transaction có thể không được đăng ký vì thread mới không có context của transaction gốc. Hãy phân biệt rõ “đưa listener sang async sau khi callback được đăng ký” với “đưa publisher sang thread khác”.

## 10. Thiết kế đáng tin cậy khi phản ứng với rollback

Không phải tất cả công việc hậu rollback đều nên đặt vào `@TransactionalEventListener`.

**Phù hợp với callback trong bộ nhớ:**

- Dọn dẹp bộ nhớ hoặc tài nguyên tạm chỉ cần best-effort.
- Ghi metric hoặc log hỗ trợ debug; chấp nhận sự kiện có thể mất nếu process chết.
- Cập nhật trạng thái kiểm thử hoặc telemetry không ảnh hưởng tính đúng đắn nghiệp vụ.
- Ghi audit đơn giản bằng transaction mới khi chấp nhận chính sách lỗi/giám sát và giới hạn của callback.

**Cần cơ chế bền vững hơn:**

- Gửi email/notification bắt buộc không được mất.
- Ghi nhận một lần thanh toán/thất bại quan trọng phục vụ đối soát.
- Đồng bộ với hệ thống ngoài cần retry, backoff và idempotency.
- Chạy công việc lâu, có yêu cầu SLA hoặc cần xử lý lại qua restart.

Một `transactional outbox` thường ghi bản ghi cần gửi trong **cùng transaction với thay đổi nghiệp vụ**. Nếu transaction rollback thì **bản ghi outbox cũng rollback**, do đó outbox không tự ghi nhận được mọi lần thất bại/rollback đã xảy ra. Muốn lưu dấu một rollback quan trọng, cần thiết kế transaction độc lập, một nguồn sự kiện bền vững bên ngoài, hoặc mô hình quản lý trạng thái nghiệp vụ để phản ánh thất bại trước/sau transaction tùy yêu cầu. Không dùng outbox như lời giải mặc định cho việc “lưu lại chính transaction đã rollback”.

Nếu cần log một lần giao dịch thất bại vào DB nhưng không muốn phụ thuộc callback, có thể bắt lỗi tại tầng điều phối **ngoài transaction T1** rồi gọi một service audit có transaction mới. Cần bảo đảm transaction T1 thực sự đã hoàn tất trước khi ghi audit, và định nghĩa rõ xử lý khi audit cũng thất bại.

## 11. Kiểm thử `AFTER_ROLLBACK` đúng nghĩa

Kiểm thử nên tập trung vào **trạng thái thực tế sau transaction**, không chỉ kiểm tra method listener đã được gọi.

1. **Commit thành công:** phát event bên trong T1, hoàn tất commit; `AFTER_COMMIT` chạy và `AFTER_ROLLBACK` không chạy.
2. **Rollback do unchecked exception:** phát event, ném `RuntimeException` ra khỏi `@Transactional`; kiểm tra thay đổi DB gốc biến mất và listener rollback được gọi.
3. **Rollback-only:** đánh dấu transaction rollback-only qua API Spring, kết thúc transaction; kiểm tra callback rollback mà không dựa vào exception gốc.
4. **Checked exception:** so sánh có/không có `rollbackFor`; xác minh kết quả commit/rollback thực, không giả định checked exception luôn rollback.
5. **Không có transaction:** phát event ngoài T1; listener có `fallbackExecution=false` không chạy.
6. **Audit bằng `REQUIRES_NEW`:** listener rollback ghi audit độc lập; khi audit thành công, kết quả được commit dù T1 rollback.
7. **Lỗi trong audit T3:** xác minh T3 rollback và T1 không thay đổi kết quả; kiểm tra log, metrics và cơ chế phục hồi.
8. **Nhiều transaction/lồng nhau:** test `REQUIRES_NEW` và `NESTED` riêng theo transaction manager, nhất là trường hợp rollback savepoint.

### Cẩn thận với `@Transactional` trên test

Trong Spring Test, test method gắn `@Transactional` thông thường được rollback tự động khi test kết thúc. Nếu bạn chỉ phát event rồi assert ngay trong test, callback `AFTER_ROLLBACK` **chưa chắc đã chạy**, vì transaction chưa hoàn tất. Tương tự, `AFTER_COMMIT` sẽ không chạy nếu test rollback thay vì commit.

Có thể dùng `TestTransaction.flagForRollback()` rồi `TestTransaction.end()` để chủ động hoàn tất transaction trong test được cấu hình phù hợp:

```java
TestTransaction.flagForRollback();
TestTransaction.end();

// Sau khi transaction test kết thúc, kiểm tra kết quả rollback.
```

Đây là mã minh họa, yêu cầu Spring Test quản lý transaction test và import `org.springframework.test.context.transaction.TestTransaction`; `spring-test` phải có trên test classpath. Không nên chỉ dùng `Thread.sleep()` để chờ callback async. Nếu listener bất đồng bộ, dùng latch/future/Awaitility có timeout để chờ có kiểm soát.

## 12. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `AFTER_ROLLBACK` không được gọi | Không có transaction khi phát event, event chưa được phát hoặc T1 commit | Xác minh lời gọi qua proxy, thời điểm `publishEvent()` và trạng thái T1 |
| Listener chạy ngay dù muốn chờ kết quả | Đã dùng `@EventListener` thay vì `@TransactionalEventListener` | Chọn `AFTER_COMMIT`, `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION` |
| Audit hậu rollback không lưu được | Thao tác DB dùng tài nguyên transaction cũ đã kết thúc | Mở transaction mới `REQUIRES_NEW` trong bean khác |
| `REQUIRES_NEW` có annotation nhưng không hoạt động | Self-invocation `this.recordFailure()` bỏ qua proxy | Inject service/bean và gọi qua Spring proxy hoặc dùng `TransactionTemplate` |
| Dữ liệu ngoài hệ thống đã gửi dù T1 rollback | `@EventListener` thường hoặc I/O ngoài diễn ra trước commit | Chỉ thực hiện sau commit, hoặc dùng cơ chế bền vững thích hợp |
| Callback lỗi mà caller không nhận exception | Callback sau hoàn tất có thể log lỗi mà không truyền ra | Quan sát lỗi riêng; không suy luận từ kết quả của caller |
| Rollback savepoint nhưng listener rollback không chạy | Transaction ngoài chưa rollback/hoàn tất | Phân biệt `NESTED` savepoint với kết thúc transaction |
| `@Transactional` test không thấy callback | Transaction test vẫn mở hoặc hoàn tất tự động sau assertion | Kết thúc transaction test có kiểm soát trước assertion |
| Listener thấy dữ liệu “còn” nhưng ghi không commit | Tài nguyên cũ vẫn accessible trong callback | Dùng `REQUIRES_NEW` cho thao tác DB mới |
| Process chết làm mất callback | Event Spring chỉ nằm trong bộ nhớ | Thiết kế persisted work/audit hoặc mô hình phục hồi khác |

## 13. Chọn giải pháp theo yêu cầu nghiệp vụ

- **Cần cập nhật DB cùng nguyên tử với nghiệp vụ:** dùng `@EventListener` đồng bộ trong transaction hiện tại hoặc gọi service trực tiếp bên trong T1. Tránh I/O ngoài không rollback được.
- **Chỉ làm việc nếu commit thành công:** dùng `@TransactionalEventListener(AFTER_COMMIT)` và mở transaction mới nếu phải ghi DB sau commit.
- **Chỉ làm việc nếu transaction rollback:** dùng `@TransactionalEventListener(AFTER_ROLLBACK)`; nếu lưu audit, dùng một transaction mới và có kế hoạch xử lý lỗi.
- **Cần biết transaction đã kết thúc bất kể kết quả:** dùng `AFTER_COMPLETION`; khi cần phân biệt status, chọn hai pha riêng hoặc dùng `TransactionSynchronization`.
- **Cần đảm bảo không mất dữ liệu/công việc:** dùng transaction độc lập cho bản ghi lỗi, outbox trong transaction thích hợp, message broker hoặc persistent queue theo đúng ngữ nghĩa nghiệp vụ; bổ sung retry/idempotency/monitoring.

Nguyên tắc cần nhớ: **Event có thể được phát trước khi transaction thành công; rollback chỉ hoàn tác những thay đổi thực sự thuộc transaction.** Hãy chọn pha listener theo kết quả mong muốn, xác định rõ transaction sở hữu event, và tạo transaction mới khi callback sau hoàn tất cần ghi dữ liệu bền vững.

## Tài liệu chính thức

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — `TransactionSynchronization` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — Declarative transaction rollback rules](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Proxying and self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
