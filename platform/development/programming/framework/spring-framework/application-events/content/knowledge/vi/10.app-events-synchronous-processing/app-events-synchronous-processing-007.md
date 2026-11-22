# Đảm bảo tính nhất quán trong cùng use case với Spring Application Events đồng bộ

## 1. Từ một nghiệp vụ đến yêu cầu nhất quán

Giả sử use case **tạo đơn hàng** gồm hai bước: ghi đơn hàng vào cơ sở dữ liệu và giữ trước số lượng hàng trong kho. Quy tắc nghiệp vụ là **không được có đơn hàng thành công nếu việc giữ hàng bắt buộc bị từ chối**. Một cách tổ chức là use case lưu đơn, phát sự kiện `OrderCreated` và để một listener thực hiện việc giữ hàng.

~~~text
OrderUseCase.createOrder(...)
    |
    +-- INSERT orders
    |
    +-- publishEvent(OrderCreated)
    |       |
    |       +-- InventoryListener.reserve(...)
    |               |
    |               +-- INSERT reservations / throw nếu thiếu hàng
    |
    +-- hoàn tất use case và transaction
~~~

Với xử lý đồng bộ, `publishEvent(...)` trở về sau khi listener thông thường đã hoàn tất. Nếu listener ném lỗi mà lỗi không bị nuốt, use case có thể thất bại. Tuy nhiên, **đồng bộ không tự tạo transaction**: nếu từng lệnh ghi dữ liệu đã autocommit thì lỗi muộn hơn không tự hoàn tác bản ghi trước đó.

Cần phân biệt ba mức bảo đảm:

1. **Trình tự:** tác vụ listener chạy xong trước khi use case trả thành công.
2. **Lỗi được truyền về:** lỗi listener bắt buộc đến được người điều phối use case.
3. **Nguyên tử dữ liệu:** các thao tác dữ liệu liên quan cùng commit hoặc cùng rollback trong một transaction thực tế.

Hai mức đầu là vấn đề **cách phát và xử lý event**; mức thứ ba đòi hỏi **ranh giới giao dịch, tài nguyên và quy tắc rollback** phù hợp.

## 2. Spring xử lý event đồng bộ như thế nào?

`ApplicationEventPublisher.publishEvent(Object)` phát một sự kiện trong phạm vi `ApplicationContext`. Với cấu hình mặc định, `SimpleApplicationEventMulticaster` gọi listener thông thường trên chính luồng phát sự kiện. Spring nhận diện phương thức có `@EventListener` từ các bean trong context; payload có thể là POJO hoặc Java record, không bắt buộc kế thừa `ApplicationEvent`.

~~~java
public record OrderCreated(long orderId, int quantity) { }

@EventListener
public void onOrderCreated(OrderCreated event) {
    // Phần xử lý đồng bộ theo cấu hình multicaster mặc định.
}
~~~

Đoạn mã trên minh họa một phương thức trong bean listener đã được đăng ký. Đối với một event tương thích kiểu, Spring sẽ gọi listener; sau khi listener trả về, `publishEvent` mới kết thúc. Nếu listener ném `RuntimeException` và không có `ErrorHandler` xử lý để tiếp tục, exception truyền ra ngoài lời gọi `publishEvent`. Các listener được xếp sau trong lần multicast có thể không được gọi.

Đây là hành vi **mặc định**, cần xem xét lại nếu ứng dụng:

- đánh dấu listener `@Async` hoặc cấu hình `TaskExecutor` cho multicaster;
- đặt `ErrorHandler` để ghi nhận và nuốt exception;
- dùng loại listener xử lý theo pha giao dịch như `@TransactionalEventListener`;
- gọi dịch vụ ngoài hoặc tạo luồng mới bên trong listener.

Khi chuyển sang bất đồng bộ, listener có thể chạy sau khi `publishEvent` đã trả về; lỗi của nó không còn tự truyền tới lời gọi ban đầu, và transaction gắn với luồng gốc không tự đi theo.

## 3. Tại sao cần cùng transaction?

Transaction cục bộ trong Spring thường gắn tài nguyên (như JDBC `Connection`) vào luồng đang thực thi. Nếu use case mở transaction trước khi phát event, và listener đồng bộ dùng **cùng transaction manager / DataSource** theo cơ chế của Spring, các câu lệnh JDBC có thể tham gia cùng transaction.

~~~text
BEGIN
  INSERT orders
  publishEvent(...)
      listener: INSERT reservations
  -- tất cả thành công
COMMIT

BEGIN
  INSERT orders
  publishEvent(...)
      listener: throw IllegalStateException
  -- lỗi truyền ra khỏi use case
ROLLBACK
~~~

**Những điều phải đúng để rollback toàn bộ:** transaction bao quanh thao tác phát sự kiện; listener thực sự chạy đồng bộ; các thao tác dữ liệu tham gia cùng transaction vật lý; lỗi không bị nuốt; quy tắc rollback áp dụng cho lỗi. Một listener đồng bộ ghi vào **một DataSource khác không tham gia transaction** vẫn có thể commit độc lập.

Với `@Transactional` mặc định trong Spring, `RuntimeException` và `Error` kích hoạt rollback; checked exception không tự kích hoạt rollback nếu không cấu hình thêm. Với `TransactionTemplate`, exception runtime thoát ra khỏi callback khiến transaction rollback. Phân biệt `PROPAGATION_REQUIRED` (thường tham gia transaction đã có) với `REQUIRES_NEW` (transaction vật lý độc lập, có thể commit riêng).

## 4. Ví dụ Java 17 chạy được: commit và rollback với listener đồng bộ

Chương trình sử dụng **Spring Framework 6.2.8**, Spring JDBC và H2 in-memory; **không cần Spring Boot**. Transaction được tạo bằng `TransactionTemplate` ngay trong use case để ranh giới rõ ràng. Listener dùng `JdbcTemplate` chung DataSource. Một đơn hợp lệ sẽ commit cả hai bảng; một đơn không đủ hàng sẽ rollback cả hai thao tác của lần đó.

### 4.1. Cấu trúc và dependency

~~~text
spring-event-consistency/
├── pom.xml
└── src/main/java/UseCaseConsistencyDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>spring-event-consistency</artifactId>
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
          <mainClass>UseCaseConsistencyDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 4.2. Mã nguồn hoàn chỉnh

Tệp `src/main/java/UseCaseConsistencyDemo.java`:

~~~java
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
import org.springframework.transaction.support.TransactionTemplate;

public final class UseCaseConsistencyDemo {

    public record OrderCreated(long orderId, int quantity) { }

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

        public void createOrder(long id, int quantity) {
            transactions.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO orders (id, qty) VALUES (?, ?)",
                    id, quantity
                );

                // Listener chạy trước khi callback transaction hoàn tất.
                events.publishEvent(new OrderCreated(id, quantity));
            });
        }
    }

    public static final class InventoryListener {
        private final JdbcTemplate jdbc;

        public InventoryListener(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @EventListener
        public void reserve(OrderCreated event) {
            if (event.quantity() > 5) {
                throw new IllegalStateException("Insufficient stock");
            }

            jdbc.update(
                "INSERT INTO reservations (order_id, qty) VALUES (?, ?)",
                event.orderId(), event.quantity()
            );
            System.out.println("RESERVED order=" + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:usecase;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbc(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
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
        InventoryListener inventoryListener(JdbcTemplate jdbc) {
            return new InventoryListener(jdbc);
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        // Chỉ dùng với tên bảng cố định trong chương trình demo.
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + table, Integer.class
        );
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE orders (id BIGINT PRIMARY KEY, qty INT NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE reservations (" +
                "order_id BIGINT PRIMARY KEY, qty INT NOT NULL)"
            );

            OrderUseCase useCase = context.getBean(OrderUseCase.class);

            useCase.createOrder(1L, 2);
            System.out.println(
                "AFTER OK: orders=" + count(jdbc, "orders") +
                ", reservations=" + count(jdbc, "reservations")
            );

            try {
                useCase.createOrder(2L, 8);
            } catch (IllegalStateException ex) {
                System.out.println("FAILED: reservation rejected");
            }

            System.out.println(
                "FINAL: orders=" + count(jdbc, "orders") +
                ", reservations=" + count(jdbc, "reservations")
            );
        }
    }
}
~~~

Chạy từ thư mục dự án bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

`stdout` do chính chương trình in ra (không tính thông báo phụ thuộc môi trường của Maven):

~~~text
RESERVED order=1
AFTER OK: orders=1, reservations=1
FAILED: reservation rejected
FINAL: orders=1, reservations=1
~~~

### 4.3. Theo dấu từng transaction

**Đơn 1:** `createOrder(1, 2)` mở transaction. `orders` nhận dòng `id=1`, listener nhận `OrderCreated` đồng bộ, kiểm tra số lượng không vượt 5 rồi ghi `reservations`. `executeWithoutResult` kết thúc bình thường nên transaction commit. Hai bảng đều có một dòng.

**Đơn 2:** `createOrder(2, 8)` mở transaction khác và tạm ghi `orders`. Listener ném `IllegalStateException` trước khi ghi `reservations`. Exception đi ngược qua `publishEvent` tới `TransactionTemplate` và làm transaction rollback. Đơn thứ hai không tồn tại sau rollback; dòng của đơn thứ nhất vẫn tồn tại. Vì vậy số dòng cuối cùng vẫn là `1` ở cả hai bảng.

Trong demo, `JdbcTemplate` của use case và listener cùng `DataSource`. `DataSourceTransactionManager` gắn JDBC Connection transaction vào luồng hiện tại, còn listener chạy trên chính luồng đó. Nếu người lập trình thay bằng DataSource hoặc transaction manager khác mà không thiết kế giao dịch phân tán, kết luận “cùng rollback” không còn mặc nhiên đúng.

**Lưu ý:** dòng `RESERVED order=1` được in trước lúc transaction thực sự commit. In log, gửi email hay gọi HTTP bên ngoài không phải thao tác có thể được rollback cùng DB. Ví dụ cố tình không mô phỏng tồn kho cạnh tranh đồng thời; trong hệ thống thực cần thêm ràng buộc DB, khóa hoặc kiểm tra phiên bản để bảo vệ dữ liệu giữa nhiều request chạy song song.

## 5. Áp dụng với `@Transactional` trong ứng dụng Spring

Ứng dụng thực thường dùng annotation hơn là `TransactionTemplate`:

~~~java
@Service
public class CheckoutService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public CheckoutService(
            OrderRepository orders,
            ApplicationEventPublisher events
    ) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void checkout(CheckoutCommand command) {
        Order order = orders.save(Order.from(command));
        events.publishEvent(
            new OrderCreated(order.getId(), command.quantity())
        );
    }
}
~~~

Đây là **đoạn minh họa phụ thuộc mã ứng dụng**, cần các kiểu `OrderRepository`, `Order`, `CheckoutCommand` và import `Service`, `Transactional`, `ApplicationEventPublisher`. Để bảo đảm listener là một phần transaction, cần xác nhận:

- Có cấu hình quản lý transaction và lời gọi `checkout` đi qua Spring transaction proxy; lời gọi kiểu `this.checkout(...)` bên trong chính bean có thể bỏ qua proxy.
- Phần dữ liệu trong listener dùng transaction manager/tài nguyên tương thích. `Propagation.REQUIRED` là mặc định thường phù hợp; `REQUIRES_NEW` luôn mở transaction vật lý riêng.
- Listener hoàn thành đồng bộ và lỗi quan trọng không bị bắt rồi bỏ qua.
- Rollback rule phù hợp: mặc định rollback khi `RuntimeException`/`Error`; nếu muốn checked exception cũng gây rollback, dùng `rollbackFor` hoặc chính sách tương đương.
- Event được publish **trong** phương thức có transaction, trước khi ranh giới transaction kết thúc. Nếu publish sau khi phương thức `@Transactional` đã trả về, giao dịch có thể đã commit.

Với bước bắt buộc để giữ bất biến cốt lõi, **gọi trực tiếp `InventoryService.reserve(...)` từ use case** cũng là thiết kế tốt và thường dễ theo dõi hơn. Event đồng bộ hữu ích khi sự kiện diễn đạt một sự thật nghiệp vụ và listener là thành phần được phép tham gia quy trình; tránh để người đọc use case không biết một bước sống còn bị giấu sau event.

## 6. Nhiều listener, thứ tự và quy tắc lỗi

Một event có thể có nhiều listener: giữ kho, ghi audit, cập nhật số liệu và gửi thông báo. Hãy phân loại theo ranh giới nhất quán:

| Hành động | Cách tổ chức |
| --- | --- |
| Ghi đơn và giữ kho trong cùng DB, đều bắt buộc | Cùng transaction trong use case, xử lý đồng bộ hoặc gọi service trực tiếp |
| Ghi audit bắt buộc trong cùng DB | Tham gia cùng transaction nếu thiếu audit phải khiến use case rollback |
| Gửi email, HTTP, webhook | Sau commit, có retry/idempotency hoặc outbox nếu yêu cầu bền vững |
| Cập nhật cache/metrics có thể khôi phục | Có thể sau commit hoặc eventual consistency |
| Gửi message tới hệ thống khác | Transactional outbox nếu cần tránh mất message giữa commit và gửi |

### `@Order` không tự tạo tính nguyên tử

`@Order` có thể điều khiển thứ tự gọi các listener theo quy tắc multicaster, nhưng việc Listener A chạy trước B không đồng nghĩa A được rollback nếu B lỗi. Chỉ những thao tác cùng tham gia transaction mới được transaction manager phối hợp commit/rollback. Nếu B gọi dịch vụ ngoài trước khi lỗi, giao dịch DB không thể tự đảo ngược việc gọi đó.

### Cẩn thận khi bắt exception

Nếu listener bắt lỗi giữ kho rồi chỉ log và trả về bình thường, use case có thể commit đơn. Nếu tùy chỉnh `SimpleApplicationEventMulticaster.setErrorHandler(...)` với một handler nuốt lỗi, exception từ listener cũng có thể không đến use case. Đối với bước **bắt buộc**, cần truyền thất bại hoặc đánh dấu rollback phù hợp. Các listener sau một exception chưa được xử lý có thể không được gọi; đừng dùng số lần listener chạy làm cam kết delivery/retry.

### JPA và thời điểm flush

Với JPA, `save(...)` chưa bảo đảm SQL đã được thực thi trước khi publish event; EntityManager có thể flush sau đó. Listener đồng bộ cùng transaction vẫn có thể nhìn persistence context chung, nhưng các câu truy vấn SQL, kiểm tra constraint hoặc listener khác có thể phụ thuộc vào thời điểm flush. Cần hiểu flush mode và ranh giới dữ liệu; không giả định “event chạy sau save” đồng nghĩa “mọi thay đổi đã commit vào DB”.

## 7. `@TransactionalEventListener` là một hợp đồng khác

`@EventListener` đồng bộ và `@TransactionalEventListener` có các thời điểm xử lý khác nhau:

| Annotation | Thời điểm | Tác động lên tính nhất quán |
| --- | --- | --- |
| `@EventListener` đồng bộ mặc định | Ngay trong `publishEvent` | Có thể tham gia transaction hiện tại; exception có thể làm rollback |
| `@TransactionalEventListener(phase = BEFORE_COMMIT)` | Pha trước commit | Chạy sát lúc commit, không đồng nhất với xử lý ngay khi publish |
| `@TransactionalEventListener` mặc định `AFTER_COMMIT` | Sau commit thành công | Thích hợp cho hậu xử lý; lỗi không thể rollback transaction đã commit |
| `@TransactionalEventListener(phase = AFTER_ROLLBACK)` | Sau rollback | Có thể quan sát thất bại hoặc xử lý bù |
| `@Async` listener | Có thể ở luồng riêng | Không tự chia sẻ thread-bound transaction hay exception với publisher |

Ví dụ listener thông báo sau commit:

~~~java
@Component
public class NotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void notifyAfterCommit(OrderCreated event) {
        // Chỉ chạy sau khi transaction phát event commit thành công.
    }
}
~~~

Đây là mã minh họa cần import `Component`, `TransactionalEventListener`, `TransactionPhase` và kiểu event. Theo mặc định, `@TransactionalEventListener` chỉ gắn callback khi có transaction đang hoạt động; event phát ngoài transaction có thể bị bỏ qua trừ khi cấu hình `fallbackExecution`.

**Không dùng `AFTER_COMMIT` để thay cho bước bắt buộc phải rollback cùng đơn hàng**: tại thời điểm đó, dữ liệu đơn hàng đã commit. Nếu callback sau commit cần ghi DB mới, lưu ý tài nguyên transaction cũ có thể còn gắn trên luồng nhưng không có commit tiếp theo cho chúng; nên xác lập transaction mới có chủ đích. Thông báo sau commit cũng chưa phải hàng đợi bền vững: tiến trình có thể chết ngay sau commit nhưng trước khi thông báo gửi đi.

Với giao tiếp ngoài hệ thống cần tin cậy, một giải pháp là **transactional outbox**: ghi bản ghi outbox chung transaction với dữ liệu nghiệp vụ, sau commit có worker riêng đọc và gửi lại khi thất bại. Kết hợp idempotency ở bên nhận để tránh tác động trùng khi retry.

## 8. Kiểm chứng tính nhất quán của use case

Nên kiểm tra **trạng thái sau khi transaction đã kết thúc**, thay vì chỉ xác nhận listener từng được gọi. Những ca quan trọng:

| Ca kiểm thử | Kết quả cần xác nhận |
| --- | --- |
| Tất cả bước thành công | Hai bảng cùng có dữ liệu sau commit |
| Listener ném `RuntimeException` | Không có dữ liệu dở dang của use case lỗi |
| Listener bắt và nuốt lỗi | Test phát hiện nguy cơ commit ngoài ý muốn |
| Listener dùng `REQUIRES_NEW` | Transaction riêng có thể commit hoặc rollback khác transaction cha |
| Listener được gắn `@Async` | Thời điểm và transaction khác; exception không truyền trực tiếp |
| Gửi email trước rollback | Email không được DB rollback, cần thiết kế lại |
| Hai đơn cùng tranh chấp tồn kho | Ràng buộc DB/locking/versioning vẫn bảo vệ số dư |

Nếu dùng test `@Transactional` bao cả phương thức test, test đó có thể che mờ kết quả commit thật của use case. Hãy tạo ca kiểm tra không bị transaction test bọc ngoài hoặc kết thúc transaction rồi mới truy vấn dữ liệu. Đối với chương trình ví dụ, dòng `FINAL: orders=1, reservations=1` là bằng chứng đơn `2` bị rollback, còn đơn `1` đã commit.

Có thể dùng `TransactionSynchronizationManager.isActualTransactionActive()` để quan sát transaction hiện diện trên luồng tại điểm phát và trong listener. Tuy nhiên, giá trị `true` chưa đủ chứng minh **mọi resource** dùng chung một physical transaction; phải kiểm tra cấu hình transaction manager, DataSource, propagation và kết quả dữ liệu thực tế.

## 9. Những lỗi hay gặp và cách tránh

1. **Cho rằng đồng bộ đồng nghĩa nguyên tử:** thêm transaction ở mức use case, kiểm chứng rollback bằng dữ liệu.
2. **Phát event sau khi transaction đã kết thúc:** publish ở trong ranh giới transaction nếu listener cần tham gia.
3. **Nuốt lỗi của bước bắt buộc:** exception phải ảnh hưởng tới kết quả use case hoặc transaction.
4. **Đặt `@Async` ở listener cần rollback cùng use case:** luồng mới thường không chia sẻ transaction cũ.
5. **Dùng `REQUIRES_NEW` tùy tiện:** giao dịch độc lập có thể commit trước khi use case chính rollback.
6. **Gọi hệ thống bên ngoài khi transaction đang mở:** email, HTTP, message có thể đã thực hiện dù database rollback; xem xét after-commit, outbox và xử lý bù.
7. **Nhầm thứ tự listener với một quy trình nghiệp vụ đáng tin:** dùng orchestrator/service nếu bước phụ thuộc chặt và không thể bỏ.
8. **Bỏ qua vấn đề đồng thời giữa nhiều request:** transaction trong một use case không tự loại race condition giữa các use case.
9. **Dùng `AFTER_COMMIT` để kiểm tra điều kiện bắt buộc của commit:** khi callback chạy thì commit đã hoàn tất.
10. **Nhầm event nội bộ với hàng đợi message:** Spring không tự lưu và phát lại mọi event nếu listener thất bại.

## 10. Câu hỏi luyện tập

1. Nếu bỏ `TransactionTemplate` khỏi ví dụ và để `JdbcTemplate.update` autocommit, đơn `2` có thể còn trong DB sau khi listener thất bại không? Vì sao?
2. Nếu đặt `@Async` trên `InventoryListener.reserve`, `try/catch` trong `main` có còn nhận chắc lỗi từ listener không?
3. Khi nào `@EventListener` đồng bộ tham gia cùng transaction với use case, và vì sao “cùng luồng” vẫn chưa đủ nếu listener dùng một DataSource khác?
4. Vì sao `@TransactionalEventListener(AFTER_COMMIT)` phù hợp cho gửi thông báo nhưng không phù hợp cho bước giữ kho bắt buộc phải rollback cùng đơn?
5. Nếu gọi REST API thanh toán bên ngoài giữa transaction, rollback DB có thu hồi được giao dịch phía ngoài không? Nếu không, bạn chọn idempotency, outbox, saga/compensation hay thiết kế khác?

**Gợi ý:** (1) bản ghi đã autocommit không tự rollback; (2) async không truyền trực tiếp exception về publisher; (3) cần cùng transaction manager/resource và propagation phù hợp; (4) dữ liệu đã commit trước khi callback; (5) rollback DB chỉ tác động tới resource thuộc transaction, xử lý ngoài hệ thống cần hợp đồng tin cậy riêng.

## Tài liệu tham khảo

- Spring Framework Reference, *Application Events and Asynchronous Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference, *Transaction Propagation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework Reference, *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework Reference, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Javadoc, *TransactionTemplate*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
