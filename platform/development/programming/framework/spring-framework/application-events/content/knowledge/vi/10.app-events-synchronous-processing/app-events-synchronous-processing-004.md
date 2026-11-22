# Listener đồng bộ trong transaction — Spring Framework Application Events

## 1. Khái niệm và điều kiện hoạt động

Trong Spring Framework, **listener đồng bộ trong transaction** là listener được gọi ngay trên luồng đang phát sự kiện, tại thời điểm một transaction của ứng dụng còn hoạt động. Trường hợp điển hình: một service có `@Transactional` cập nhật cơ sở dữ liệu, gọi `ApplicationEventPublisher.publishEvent(...)`, rồi một `@EventListener` xử lý sự kiện ngay trong quá trình thực thi service.

Điểm cốt lõi:

- `@Transactional` quản lý ranh giới giao dịch của phương thức service (thông qua Spring transaction proxy trong mô hình khai báo thông thường).
- `ApplicationEventPublisher` phát sự kiện; `ApplicationContext` chuyển sự kiện đến `ApplicationEventMulticaster`.
- `SimpleApplicationEventMulticaster` mặc định gọi các listener **đồng bộ trên cùng luồng** với publisher, nếu không cấu hình executor bất đồng bộ.
- `@EventListener` thường **không tự đợi commit** và **không tự mở transaction mới**. Nếu được gọi khi một transaction gắn với thread đang hoạt động, mã listener có thể thao tác với tài nguyên/transaction của thread đó.
- `@TransactionalEventListener` lại có cơ chế riêng: đăng ký xử lý theo *pha* transaction; mặc định là `AFTER_COMMIT`, không chạy ngay ở chỗ gọi `publishEvent()`.

Cần phân biệt hai ý: **đồng bộ** trả lời câu hỏi *listener chạy khi nào/trên luồng nào?*, còn **trong transaction** trả lời câu hỏi *có giao dịch đang hoạt động và thao tác dữ liệu thuộc giao dịch nào?*. Một `@EventListener` đồng bộ vẫn chạy được khi **không** có transaction; khi đó không thể mặc định coi các thao tác của nó là một phần của giao dịch chung.

## 2. Luồng thực thi và ý nghĩa của cùng transaction

Xét lệnh gọi `orderService.createOrder(...)` đi qua Spring proxy:

```text
Caller
  -> proxy của OrderService
     -> BEGIN transaction
        -> OrderService.createOrder(...)
           -> INSERT đơn hàng (chưa commit)
           -> publisher.publishEvent(OrderCreated)
              -> ApplicationContext
                 -> SimpleApplicationEventMulticaster
                    -> @EventListener onOrderCreated(...)
                       -> đọc/ghi DB trong transaction hiện tại
                    <- listener hoàn tất
              <- publishEvent() trả về
           -> xử lý tiếp trong createOrder(...)
     -> COMMIT (hoặc ROLLBACK nếu thất bại theo quy tắc)
  <- Caller
```

Với transaction kiểu imperative do `PlatformTransactionManager` quản lý, Spring gắn các tài nguyên như JDBC `Connection` và trạng thái giao dịch vào thread hiện tại. Nếu listener đồng bộ dùng cùng `DataSource` và `JdbcTemplate`/repository được cấu hình đúng cách, thao tác JDBC của listener thường tham gia **cùng transaction vật lý** với publisher:

- Listener có thể đọc dữ liệu publisher vừa ghi nhưng chưa commit bằng cùng connection/transaction, dù thread khác hoặc connection khác có thể chưa nhìn thấy dữ liệu theo isolation level.
- Thao tác ghi của publisher và listener được commit hoặc rollback cùng nhau nếu chúng thực sự tham gia một transaction.
- Nếu listener ném `RuntimeException` xuyên qua `publishEvent()`, phương thức `@Transactional` có thể thất bại và transaction bị rollback theo quy tắc mặc định.
- Nếu publisher vẫn tiếp tục sau khi listener hoàn tất, transaction chưa nhất thiết đã commit; commit xảy ra khi transaction interceptor hoàn thành lời gọi bên ngoài, hoặc theo ranh giới được cấu hình thực tế.

**Không đồng nghĩa mọi listener có cùng transaction:** `@Async`, multicaster dùng executor, một transaction manager/DataSource khác, hoặc phương thức được khai báo `REQUIRES_NEW` có thể tạo ranh giới khác. Với mô hình reactive, transaction được truyền qua Reactor Context, không thể suy luận từ thread-local như ví dụ imperative.

## 3. Ví dụ Java 17+ chạy được: commit cùng nhau, lỗi thì rollback cùng nhau

Ví dụ thuần Spring Framework (không cần Spring Boot) dùng H2 in-memory để chứng minh hai việc: một listener đồng bộ nhìn thấy bản ghi chưa commit của publisher và lỗi từ listener có thể rollback cả hai bảng.

Tạo dự án:

```text
transaction-event-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/TransactionEventDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'transaction-event-demo'
```

`build.gradle` — Spring Framework 6.2.12, JDK 17+, Gradle 8+:

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
    mainClass = 'demo.TransactionEventDemo'
}
```

`src/main/java/demo/TransactionEventDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransactionEventDemo {

    public record OrderCreated(String orderId, boolean failInListener) {}

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void create(String orderId, boolean failInListener) {
            jdbc.update("insert into orders(id) values (?)", orderId);
            System.out.println("publisher: inserted " + orderId);

            publisher.publishEvent(new OrderCreated(orderId, failInListener));
            System.out.println("publisher: after event " + orderId);
        }
    }

    public static class AuditListener {
        private final JdbcTemplate jdbc;

        public AuditListener(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @EventListener
        public void onOrderCreated(OrderCreated event) {
            boolean active = TransactionSynchronizationManager
                    .isActualTransactionActive();

            Integer visible = jdbc.queryForObject(
                    "select count(*) from orders where id = ?",
                    Integer.class,
                    event.orderId());

            System.out.println(
                    "listener: " + event.orderId()
                    + ", tx=" + active
                    + ", visible=" + visible);

            if (event.failInListener()) {
                throw new IllegalStateException("audit failed");
            }

            jdbc.update(
                    "insert into audit(order_id) values (?)",
                    event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_events;DB_CLOSE_DELAY=-1");
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
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        AuditListener auditListener(JdbcTemplate jdbc) {
            return new AuditListener(jdbc);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService service = context.getBean(OrderService.class);

            jdbc.execute("create table orders (id varchar(40) primary key)");
            jdbc.execute("create table audit (order_id varchar(40) primary key)");

            service.create("ok-1", false);
            System.out.println("after commit: orders=" + count(jdbc, "orders")
                    + ", audit=" + count(jdbc, "audit"));

            try {
                service.create("bad-1", true);
            } catch (IllegalStateException ex) {
                System.out.println("caught: " + ex.getMessage());
            }

            System.out.println("after rollback: orders=" + count(jdbc, "orders")
                    + ", audit=" + count(jdbc, "audit"));
        }
    }

    private static int count(JdbcTemplate jdbc, String tableName) {
        // tableName chỉ nhận các literal "orders" hoặc "audit" trong ví dụ.
        return jdbc.queryForObject(
                "select count(*) from " + tableName,
                Integer.class);
    }
}
```

Chạy khi có JDK 17+ và Gradle đã cài:

```bash
gradle -q run
```

Các dòng `System.out.println` của ứng dụng cho kết quả theo thứ tự:

```text
publisher: inserted ok-1
listener: ok-1, tx=true, visible=1
publisher: after event ok-1
after commit: orders=1, audit=1
publisher: inserted bad-1
listener: bad-1, tx=true, visible=1
caught: audit failed
after rollback: orders=1, audit=1
```

Giải thích kết quả:

1. `service` được lấy từ Spring context nên lời gọi `create(...)` đi qua transaction proxy do `@EnableTransactionManagement` kích hoạt. Không tự tạo instance `new OrderService(...)` rồi kỳ vọng `@Transactional` hoạt động.
2. `@EventListener` chạy ngay trong `publishEvent()`: dòng `listener: ...` xuất hiện trước `publisher: after event ...` ở lần thành công.
3. `tx=true` cho thấy tại thời điểm listener chạy, transaction imperative đang hoạt động trên thread đó. `visible=1` cho thấy JDBC của listener đọc được bản ghi vừa INSERT trong cùng giao dịch.
4. Ở `ok-1`, cả `orders` và `audit` được commit, mỗi bảng có một dòng.
5. Ở `bad-1`, listener ném `IllegalStateException` trước khi ghi audit. Lỗi đi ngược qua `publishEvent()` và service; transaction interceptor thực hiện rollback. Bản ghi `bad-1` không còn trong `orders`; tổng hai bảng vẫn là `1,1`.
6. Sự kiện `OrderCreated` chỉ là Java record; Spring hỗ trợ `publishEvent` cho object thông thường qua cơ chế payload event. Không cần kế thừa `ApplicationEvent`.

Ví dụ sử dụng JDBC với cùng `DataSourceTransactionManager` để làm rõ tính nguyên tử. Trong dự án JPA, thao tác ghi, flush và lazy loading còn phụ thuộc `EntityManager`, flush mode và ranh giới persistence context; đừng suy diễn rằng mọi SQL được gửi ngay tại lệnh `save()`.

## 4. Lỗi từ listener quyết định rollback như thế nào?

Với multicaster đồng bộ **không cấu hình `ErrorHandler`**, lỗi do listener ném ra có thể lan tới lời gọi `publishEvent()` và làm ngắt việc gọi các listener còn lại. Quy tắc transaction khi phương thức `@Transactional` thoát ra ngoài:

| Tình huống | Kết quả thông thường |
| --- | --- |
| Listener kết thúc bình thường | Publisher tiếp tục; transaction commit khi ranh giới thực sự kết thúc thành công. |
| Listener ném `RuntimeException` hoặc `Error`, không bị chặn | Mặc định transaction interceptor đánh dấu rollback khi lỗi thoát qua ranh giới `@Transactional`. |
| Listener ném checked exception và transaction cho phép lan ra | Mặc định các checked exception không tự kích hoạt rollback, trừ khi có `rollbackFor`/chính sách rollback toàn cục phù hợp. |
| Publisher bắt và xử lý lỗi trước khi thoát khỏi transaction | Không thể mặc định kết luận rollback; cần chủ động xem trạng thái rollback-only hoặc quy tắc khác. |
| `ErrorHandler` của multicaster log rồi nuốt lỗi | Publisher có thể tiếp tục mà không thấy exception; transaction không tự rollback chỉ vì handler đã ghi log. |
| Listener gọi một service khác có `@Transactional(REQUIRES_NEW)` | Transaction mới độc lập có thể commit trước; rollback transaction gốc không tự hoàn tác dữ liệu đã commit trong transaction mới. |

Ví dụ cấu hình rollback cho một checked exception từ một phương thức service:

```java
@Transactional(rollbackFor = BusinessRuleException.class)
public void performOperation() throws BusinessRuleException {
    // Thực hiện nghiệp vụ, phát sự kiện và cho lỗi lan ra ngoài.
}
```

Đây là **mã minh họa một phương thức**, trong đó `BusinessRuleException` là checked exception được định nghĩa trong ứng dụng. Không phải phương thức độc lập để biên dịch; ví dụ Java chạy đầy đủ nằm ở mục 3.

**Lưu ý về rollback-only:** Nếu một phương thức có proxy transaction riêng, tham gia transaction hiện tại bằng `REQUIRED`, đã đánh dấu rollback-only sau lỗi nhưng lớp ngoài bắt lỗi rồi cố commit, Spring có thể ném `UnexpectedRollbackException`. Do đó cần thiết kế rõ ai sở hữu transaction và chính sách lỗi; việc bắt exception không đảm bảo có thể commit tiếp.

**Lưu ý về `ErrorHandler`:** `SimpleApplicationEventMulticaster#setErrorHandler(...)` cho phép handler ghi log, nuốt hoặc ném lại lỗi. Nuốt lỗi khiến listener khác có thể tiếp tục, nhưng không đáp ứng yêu cầu nghiệp vụ nếu lỗi ấy phải làm rollback. Nếu thực sự phải rollback, cho lỗi lan ra ranh giới transaction hoặc dùng chính sách đánh dấu rollback phù hợp.

## 5. `@EventListener` và `@TransactionalEventListener`: hai lịch chạy khác nhau

Hai annotation dễ bị nhầm vì cùng nhận sự kiện và thường đều được gọi trên thread giao dịch trong ứng dụng imperative mặc định.

```java
@EventListener
public void immediately(OrderCreated event) {
    // Chạy ngay khi publishEvent() gọi tới listener.
}

@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void beforeCommit(OrderCreated event) {
    // Chạy ở callback trước commit, không phải ngay khi publishEvent().
}

@TransactionalEventListener // mặc định AFTER_COMMIT
public void afterCommit(OrderCreated event) {
    // Chạy sau khi transaction commit thành công.
}
```

Ba phương thức là **đoạn minh họa**, cần đặt trong bean do Spring quản lý; `OrderCreated` là kiểu sự kiện của ứng dụng. Cần import `EventListener`, `TransactionalEventListener` và `TransactionPhase` từ Spring tương ứng.

| Loại listener | Khi nào thực thi | Có transaction thì điều gì xảy ra? |
| --- | --- | --- |
| `@EventListener` thông thường | Ngay lúc multicaster phân phối sự kiện | Có thể dùng tài nguyên của transaction đang mở trên cùng thread; chưa bảo đảm commit. |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Khi Spring gọi callback trước commit | Có thể thao tác trong phase commit khi transaction còn hoạt động; lỗi ở phase này có thể cản commit. |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit thành công | Chỉ chạy nếu commit; không thể làm rollback lại transaction đã commit. |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Sau rollback | Hữu ích để ghi nhận/bù trừ; đừng giả định có transaction mới để ghi DB. |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Sau khi transaction kết thúc, commit hoặc rollback | Dùng cho công việc kết thúc không phụ thuộc kết quả hoặc cần phân biệt kết quả qua thiết kế riêng. |

Với `@TransactionalEventListener`, việc gọi `publishEvent()` trong transaction chủ yếu đăng ký listener vào cơ chế đồng bộ transaction; phương thức listener được gọi ở pha đã chỉ định. Mặc định khi **không có transaction**, listener dạng này **không được gọi**; có thể cho phép thực thi bằng `fallbackExecution = true` nếu thiết kế chấp nhận.

Sau `AFTER_COMMIT`, tài nguyên transaction có thể vẫn còn gắn vào thread trong thời gian callback chạy. Nếu handler cần tạo **một ghi chép DB mới có commit riêng**, hãy dùng phương thức của **một Spring bean khác** với `@Transactional(propagation = Propagation.REQUIRES_NEW)` khi phù hợp, thay vì trông chờ thao tác trong callback được commit lần nữa bởi transaction đã kết thúc. Dùng phương thức qua proxy; tự gọi `this.method()` trong cùng bean có thể bỏ qua advice.

**Đừng nhầm `BEFORE_COMMIT` với “ngay khi phát event”:** nếu publisher gọi `publishEvent()` nhiều lần trong một phương thức transaction, các listener `BEFORE_COMMIT` được lên lịch cho giai đoạn commit, không chạy tại chỗ phát như `@EventListener`.

## 6. Khi nào xử lý đồng bộ ngay trong transaction là phù hợp?

Chọn listener đồng bộ trong transaction khi **tác vụ cần nhất quán nguyên tử với nghiệp vụ chính**, thời gian thực thi nhỏ, và thất bại của listener phải có khả năng làm thất bại thao tác gốc. Ví dụ: cập nhật một bảng audit nội bộ hoặc projection trên cùng database và cùng transaction manager, với chính sách rollback rõ ràng.

Nếu tác vụ là gửi email, HTTP request, push notification hoặc publish lên broker từ listener đồng bộ, bạn cần cân nhắc:

- Một hệ thống ngoài database không được rollback chỉ vì JDBC transaction rollback. Email đã gửi không thể tự thu hồi; HTTP call thành công vẫn có thể xảy ra trước khi DB rollback.
- Tác vụ I/O chậm kéo dài thời gian giữ lock/connection, tăng nguy cơ timeout hoặc deadlock.
- Một lỗi mạng tạm thời có thể làm rollback thao tác chính nếu exception lan ra; ngược lại, nuốt lỗi có thể đánh mất tác vụ.
- Nếu hành động ngoài chỉ được thực hiện **sau khi commit thành công**, cân nhắc `@TransactionalEventListener(AFTER_COMMIT)`; nếu **phải giao hàng chắc chắn** qua restart/crash, dùng transactional outbox + worker/broker và thiết kế idempotency, retry.

Một cách tách thường gặp là giữ cập nhật dữ liệu cần nguyên tử ở listener đồng bộ, còn gửi notification ở listener sau commit hoặc qua outbox. Điều kiện quan trọng là xác định rõ trạng thái nào phải cùng commit và bước nào được phép thất bại độc lập.

## 7. Kiểm thử và chẩn đoán

Đối với ví dụ có DB, kiểm thử tối thiểu cần xác nhận:

1. **Commit thành công:** sau khi lời gọi service trở về, cả dữ liệu của publisher và listener tồn tại trong database.
2. **Listener thất bại:** một `RuntimeException` không bị chặn làm transaction rollback, và dữ liệu do publisher ghi trong cùng transaction không còn.
3. **Thứ tự:** listener đồng bộ hoàn tất trước khi `publishEvent()` trở về; assertion nên dựa trên trạng thái/call order có kiểm soát thay vì thứ tự xử lý không liên quan.
4. **Gọi ngoài transaction:** listener `@EventListener` vẫn được gọi, nhưng không có ngữ nghĩa transaction chung; `@TransactionalEventListener` mặc định không được gọi.
5. **Cấu hình ngoại lệ:** nếu sử dụng `ErrorHandler`, `rollbackFor`, `REQUIRES_NEW` hoặc listener có transaction proxy riêng, viết test cho hành vi thực tế của từng cấu hình.
6. **Nhiều listener:** nếu listener thứ nhất ném lỗi, kiểm tra listener sau có được gọi hay không theo chính sách multicaster và cách xử lý lỗi đã cấu hình.

Để kiểm tra transaction imperative trong listener:

```java
boolean actualTx =
        TransactionSynchronizationManager.isActualTransactionActive();
```

Giá trị này cho biết Spring coi transaction hiện tại trên **thread đang chạy** là hoạt động, chứ không chứng minh mọi thao tác của mọi datasource đều dùng cùng một giao dịch vật lý. Muốn chứng minh tính nguyên tử, kiểm tra kết quả dữ liệu sau commit/rollback như trong ví dụ.

Các lỗi phổ biến:

- **Tưởng `publishEvent()` mặc định chạy sau commit.** Với `@EventListener` thông thường, listener đồng bộ chạy ngay trong lúc transaction có thể chưa hoàn tất.
- **Gắn `@Transactional` nhưng gọi nội bộ `this.create(...)`.** Với proxy mode mặc định, self-invocation thường bỏ qua transaction interceptor.
- **Dùng `@Async` hoặc executor cho listener mà vẫn kỳ vọng cùng thread/connection/rollback.** Transaction gắn thread không tự truyền sang executor.
- **Cho rằng lỗi listener luôn rollback.** Điều đó còn phụ thuộc ngoại lệ có lan ra, rollback rules, transaction proxy và `ErrorHandler`.
- **Gọi REST API hoặc gửi email ngay trong listener rồi giả định rollback sẽ hủy tác dụng bên ngoài.** Transaction JDBC không có khả năng đó.
- **Dùng `@TransactionalEventListener(AFTER_COMMIT)` để ghi DB nhưng không mở transaction mới.** Callback sau commit không tạo thêm một lần commit cho các ghi mới.
- **Cho rằng `@Order` quyết định commit order.** `@Order` chỉ ảnh hưởng thứ tự listener theo cơ chế dispatch/callback thích hợp; transaction boundary là trách nhiệm của transaction manager.

## 8. Ghi nhớ khi thiết kế

`@EventListener` **đồng bộ** gọi từ `publishEvent()` bên trong service `@Transactional` là một công cụ tốt cho thao tác nội bộ ngắn và cần cùng rollback. Lúc đó, listener đang tham gia thực thi nghiệp vụ **trước commit**. `@TransactionalEventListener` dành cho yêu cầu gắn với **kết quả hoặc pha** transaction như `BEFORE_COMMIT`/`AFTER_COMMIT`. Nếu cần độ bền và giao hàng tới hệ thống khác, sự kiện trong bộ nhớ nên được bổ sung bằng outbox hoặc hệ thống messaging phù hợp.

Tài liệu Spring chính thức:

- [ApplicationContext Events và listener đồng bộ](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Transaction-bound Events và `@TransactionalEventListener`](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [`@Transactional` settings và quy tắc rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Declarative transaction: rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework `SimpleApplicationEventMulticaster`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
