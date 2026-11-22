# Thời điểm commit của bên gửi và nguy cơ bên nhận đọc dữ liệu chưa hoàn tất

> **Module:** Spring Framework – concurrency  
> **Nhóm:** Giao dịch và sự kiện  
> **Mục tiêu:** Hiểu tại sao một service công bố sự kiện **trước khi giao dịch ghi dữ liệu commit** có thể khiến consumer không tìm thấy hoặc nhìn thấy trạng thái chưa đầy đủ; biết dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` đúng chỗ, phân biệt **thời điểm hiển thị dữ liệu** với **đảm bảo phát sự kiện**, và lựa chọn transactional outbox khi cần độ tin cậy cao.

## 1. Vấn đề cốt lõi

Giả sử service A tạo đơn hàng trong giao dịch DB và gửi sự kiện `OrderCreated(42)` cho service B. Service B nhận event rồi đọc bảng `orders` bằng **một kết nối hoặc một cơ sở dữ liệu khác**.

Nếu A gửi event khi transaction vẫn mở:

~~~text
Service A / Transaction T1                 Service B / Connection T2
--------------------------                 -------------------------
BEGIN
INSERT orders(id=42, status=NEW)
publish OrderCreated(42) ----------------> nhận event
                                          SELECT ... WHERE id=42
                                          -> không thấy row, hoặc thấy bản cũ
COMMIT
                                          event đã được xử lý quá sớm
~~~

Dưới isolation thông dụng như `READ_COMMITTED`, một transaction độc lập **không được thấy dữ liệu chưa commit** của transaction khác. Kết quả là B có thể báo `order not found` dù vài mili giây sau A commit thành công. Nếu A rollback, event đã phát còn có thể mô tả một đơn hàng **chưa bao giờ tồn tại ở trạng thái đã commit**.

Điểm quan trọng không phải message broker nhanh hay chậm. Đây là **lỗi thứ tự và ranh giới transaction**: công bố sự kiện ra ngoài trước khi trạng thái DB trở thành durable/visible đối với reader độc lập.

**Quy tắc:** Khi consumer cần truy vấn trạng thái đã commit của producer, hãy bảo đảm việc xử lý sự kiện chỉ bắt đầu sau khi transaction producer **commit thành công**. Nhưng đừng kết luận rằng “chuyển gửi sự kiện sang after-commit” tự động bảo đảm event sẽ không bao giờ bị mất: đó là một vấn đề thứ hai.

## 2. Phân biệt ba thời điểm

Có ba mốc khác nhau thường bị gộp làm một:

1. **Ghi trong transaction:** `INSERT`/`UPDATE` đã thực hiện qua connection của producer, nhưng chưa hoàn tất commit. Code trong **cùng transaction** thường đọc lại được thay đổi của chính nó; reader transaction khác thường chưa thấy.
2. **Commit thành công:** DB transaction manager yêu cầu commit, DB chấp nhận trạng thái mới. Sau đó, một read mới vào primary với isolation thích hợp thông thường thấy các thay đổi. Điều này không có nghĩa mọi read replica/cache đã cập nhật tức thì.
3. **Event đã được bên nhận xử lý:** message thực sự được broker/consumer nhận và xử lý; phụ thuộc queue, thread pool, retry, mạng, acknowledgement và trạng thái consumer.

`publishEvent(...)` trong Spring là **yêu cầu công bố event trong ứng dụng**, không phải chứng chỉ DB đã commit; `KafkaTemplate.send(...)` cũng không ngầm thực hiện commit của giao dịch SQL trước đó.

Cũng cần phân biệt “producer đã gọi API gửi” với “broker đã lưu bền”, “consumer đã nhận” và “consumer đã xử lý thành công”. Chúng có những mốc xác nhận khác nhau; trả về từ một API gửi asynchronous không chứng minh toàn bộ pipeline thành công.

## 3. Vì sao một consumer có thể đọc thiếu dữ liệu?

Tình huống thường gặp nhất: producer mở transaction, ghi nhiều bảng, gửi event ở giữa hoặc ngay sau câu SQL cuối cùng **nhưng trước commit**. Consumer bắt đầu làm việc sớm hơn producer hoàn tất commit.

Có những kết quả khác nhau theo thiết kế hệ thống:

| Điều kiện consumer | Điều consumer có thể thấy |
| --- | --- |
| Đọc trên connection khác với `READ_COMMITTED` trước commit | Không thấy bản ghi mới; dữ liệu cập nhật cũ còn hiển thị |
| Đọc trong cùng transaction/connection của producer | Có thể thấy thay đổi chưa commit của chính mình; **không đại diện** cho consumer độc lập |
| Đọc sau commit trên primary | Thông thường thấy phiên bản đã commit, nếu query đúng ID/isolation và không bị điều kiện lọc khác |
| Đọc sau commit nhưng transaction reader đang ở snapshot cũ (`REPEATABLE_READ`/MVCC) | Có thể tiếp tục thấy snapshot trước đó cho đến khi transaction reader kết thúc |
| Đọc replica/caches/materialized view sau commit | Có thể thấy trạng thái cũ do replication lag, cache invalidation hoặc projection lag |
| DB isolation cho phép dirty read (một số engine/cấu hình) | Có thể thấy dữ liệu chưa commit, nhưng kết quả có rủi ro rollback/đọc bẩn |

Do đó, câu “chỉ cần publish sau commit thì consumer chắc chắn đọc thấy ngay” **đúng trong một phạm vi hẹp**, không phải mọi database topology. Phải xét primary/replica, transaction reader, cache và độ trễ eventual consistency.

**Dữ liệu chưa hoàn tất** còn có nghĩa nghiệp vụ chưa ổn định: đơn hàng có thể được ghi qua nhiều bảng, một bên chưa cập nhật inventory hoặc transaction sắp rollback. Nếu producer mở **một transaction** bao trùm tất cả thay đổi liên quan, commit giúp chúng trở thành một trạng thái nhất quán với phạm vi atomicity của DB; nhưng thay đổi ở hệ thống bên ngoài **không tự tham gia** transaction đó.

## 4. @EventListener thông thường không tự chờ commit

Trong Spring Framework, `ApplicationEventPublisher.publishEvent(event)` công bố một application event cho listener. Với `SimpleApplicationEventMulticaster` mặc định không cấu hình executor, listener `@EventListener` thông thường chạy **đồng bộ trong thread đang phát sự kiện**.

~~~java
@Transactional
public void createOrder(Command command) {
    orderRepository.save(toOrder(command));
    publisher.publishEvent(new OrderCreated(command.orderId()));
    // Giao dịch có thể vẫn CHƯA commit tại đây.
}

@EventListener
public void onOrderCreated(OrderCreated event) {
    // Có thể được gọi trước khi transaction bên gửi commit.
}
~~~

Đây là **snippet tích hợp**; `Command`, `OrderCreated`, repository và injection thuộc ứng dụng. Sau khi `publishEvent` trả về, method transactional vẫn có thể tiếp tục chạy và chỉ commit **khi rời transaction interceptor**. `@EventListener` không phải cơ chế chờ DB commit.

Có một bẫy khi tự kiểm thử: listener đồng bộ có thể truy cập DB bằng `JdbcTemplate` trên **cùng thread** và tham gia connection đã bind vào transaction của producer. Nó có thể đọc thấy chính row chưa commit, tạo ấn tượng rằng mọi consumer đều thấy được. Để mô phỏng consumer thật, cần **một connection/transaction khác**, như ví dụ mục 6.

Nếu listener được `@Async` hóa, hoặc multicaster được cấu hình gửi listener chạy trên executor, lúc thực thi trên thread khác sẽ có cuộc đua thời gian rõ ràng hơn: consumer có thể chạy **trước hoặc sau commit** tùy scheduling. `@Async` chỉ tạo tính bất đồng bộ, **không** tạo ràng buộc “sau commit”.

## 5. Một trục thời gian gây lỗi trong thực tế

~~~text
Thời điểm      Producer trong @Transactional             Consumer / broker
t0             BEGIN
t1             INSERT order 42
t2             UPDATE order_items...
t3             publish event OrderCreated(42) ----------> enqueue
t4                                                        receive
t5                                                        SELECT order 42
t6                                                        -> not found
t7             COMMIT thành công
t8                                                        đã báo lỗi hoặc retry
~~~

Nguyên nhân gốc ở t3: producer công bố trước khi DB commit. Khi consumer nhận thông điệp nhanh, việc tìm thấy row phụ thuộc tốc độ commit, không còn là một hợp đồng đảm bảo.

**Vòng retry tức thời không phải lời giải đúng.** Nó có thể may mắn chạy lại sau commit trong một số lần, nhưng sẽ thất bại dai dẳng nếu producer rollback, replica chậm, ID sai hoặc transaction reader giữ snapshot cũ. Nó cũng làm tăng tải DB/broker lúc hệ thống đang bận.

Có thể gặp cùng lỗi với email gửi link đến hóa đơn chưa commit, webhook cho bên thứ ba, cập nhật search index từ event, consumer Kafka đọc bảng orders, hoặc một `@Async` task nội bộ chạy truy vấn ngay sau `save()`.

## 6. Ví dụ chạy được: Spring Framework + H2 chứng minh khả năng hiển thị

Ví dụ dùng **Spring Framework 6.2.9**, **H2 2.3.232** và **Java 17+**. Producer chạy trong transaction của `DataSourceTransactionManager`, ghi một order rồi `publishEvent`. Hai listener cùng nhận `OrderCreated` nhưng ở **hai thời điểm** khác nhau:

- `@EventListener`: chạy ngay khi publish; kiểm tra row bằng connection JDBC **độc lập** và thấy `false` vì producer chưa commit.
- `@TransactionalEventListener(phase = AFTER_COMMIT)`: chỉ chạy sau commit thành công; connection JDBC độc lập thấy `true`.

Ví dụ cố ý dùng `DriverManagerDataSource` để mỗi `getConnection()` trả connection mới, **không dùng pool** trong demo. Vì đây là DB H2 in-memory với isolation mặc định `READ_COMMITTED`, kiểm chứng trực tiếp tính visible-to-other-connection.

### Cấu trúc project

~~~text
commit-visibility-demo/
├── pom.xml
└── src/main/java/demo/CommitVisibilityDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>commit-visibility-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.9</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jdbc</artifactId>
      <version>6.2.9</version>
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
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### src/main/java/demo/CommitVisibilityDemo.java

~~~java
package demo;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement
public class CommitVisibilityDemo {
    public record OrderCreated(long id) {}

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource(
            "jdbc:h2:mem:commit_visibility;DB_CLOSE_DELAY=-1", "sa", "");
        ds.setDriverClassName("org.h2.Driver");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean
    DataSourceTransactionManager transactionManager(DataSource ds) {
        return new DataSourceTransactionManager(ds);
    }

    @Bean
    TransactionTemplate transactionTemplate(
            DataSourceTransactionManager manager) {
        return new TransactionTemplate(manager);
    }

    @Bean
    Observer observer(DataSource ds) {
        return new Observer(ds);
    }

    public static class Observer {
        private final DataSource ds;

        public Observer(DataSource ds) {
            this.ds = ds;
        }

        private boolean committedRowVisible(long id) {
            try (Connection connection = ds.getConnection();
                 PreparedStatement stmt = connection.prepareStatement(
                     "select count(*) from orders where id = ?")) {
                stmt.setLong(1, id);
                try (ResultSet rs = stmt.executeQuery()) {
                    rs.next();
                    return rs.getInt(1) == 1;
                }
            } catch (SQLException ex) {
                throw new IllegalStateException(ex);
            }
        }

        @EventListener
        public void onImmediate(OrderCreated event) {
            System.out.println(
                "Immediate listener sees order: " +
                    committedRowVisible(event.id()));
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
        public void onCommitted(OrderCreated event) {
            System.out.println(
                "After-commit listener sees order: " +
                    committedRowVisible(event.id()));
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     CommitVisibilityDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate tx =
                context.getBean(TransactionTemplate.class);
            ApplicationEventPublisher publisher = context;

            jdbc.execute(
                "create table orders (id bigint primary key, " +
                "status varchar(32))");

            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "insert into orders (id, status) values (?, ?)",
                    42L, "NEW");
                publisher.publishEvent(new OrderCreated(42L));
            });

            Integer count = jdbc.queryForObject(
                "select count(*) from orders where id = 42",
                Integer.class);
            System.out.println(
                "After transaction sees order: " + (count == 1));
        }
    }
}
~~~

**Lưu ý quan trọng:** `@EnableTransactionManagement` đăng ký infrastructure transaction và support cho `@TransactionalEventListener` trong ví dụ Spring Framework thuần. Nếu không bật cơ chế transaction management hoặc không có `TransactionalEventListenerFactory`, không được kỳ vọng annotation tự nhiên có tác dụng đúng phase. Một Spring Boot app có transaction auto-configuration thường đã chuẩn bị infrastructure này, nhưng vẫn phải xác minh context thực tế.

Chạy trong thư mục gốc project:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CommitVisibilityDemo
~~~

**Stdout của chương trình:**

~~~text
Immediate listener sees order: false
After-commit listener sees order: true
After transaction sees order: true
~~~

Mã đã được **biên dịch target Java 17 và chạy thực tế** với Spring Framework 6.2.9 + H2 2.3.232 trên JDK mới hơn; ba dòng stdout trên được đối chiếu. `@EventListener` chạy trước commit, trong khi `@TransactionalEventListener` được gọi sau commit. `Observer` dùng một connection mới để **không** đọc qua connection đang bind vào transaction của producer.

Nếu đổi test thành đọc qua `JdbcTemplate` trên cùng thread của listener immediate, kết quả có thể khác vì nó tham gia transaction đang mở. Điều đó **không bác bỏ** nguy cơ consumer bên ngoài không thấy row.

Chương trình không dùng Kafka/RabbitMQ. Nó mô phỏng **thời điểm và isolation DB** trong cùng tiến trình để giải thích race. Với broker thật, callback dispatch có thêm độ trễ và các lỗi giao nhận riêng; không thể dựa vào tốc độ broker để “tình cờ sau commit”.

## 7. @TransactionalEventListener và các giai đoạn transaction

Spring cung cấp `@TransactionalEventListener` để liên kết listener với **phase** của giao dịch chứa lời gọi publish event.

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    // Chỉ xử lý khi transaction đã commit thành công.
}
~~~

Đây là **đoạn tích hợp**, phải có `OrderCreated` và transaction-event infrastructure đúng context. Giá trị `AFTER_COMMIT` là mặc định nếu không truyền `phase`.

| Phase | Thời điểm | Phù hợp với |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction commit | Kiểm tra/thao tác gắn với transaction trước commit; **không** phải tín hiệu DB đã durable |
| `AFTER_COMMIT` | Sau commit thành công | Gửi thông báo hoặc đánh dấu bước tiếp theo cần dựa trên state đã commit |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Quan sát rollback/ghi nhận lỗi theo cơ chế tách biệt |
| `AFTER_COMPLETION` | Sau completion, commit hoặc rollback | Cleanup/telemetry không phụ thuộc kết quả cụ thể, phải tự phân biệt nếu cần |

Khi **không có active transaction** tại thời điểm event được publish, mặc định listener `@TransactionalEventListener` **không chạy**. Có thể đặt `fallbackExecution = true` để chạy ngoài transaction, nhưng lựa chọn đó thay đổi hợp đồng nghiệp vụ; không dùng chỉ để “chữa lỗi không thấy listener chạy”.

Trong transaction rollback, listener `AFTER_COMMIT` không chạy. Vì vậy nó tránh được một lớp **sự kiện sai do rollback** mà `@EventListener` thông thường có thể mắc.

**Đừng nhầm @TransactionalEventListener với @Async.** Listener theo phase, nếu không được cấu hình async riêng, không đương nhiên chuyển sang worker khác. Nếu thêm `@Async`, listener có thể được nộp để chạy sau commit nhưng xảy ra lỗi nộp, shutdown hoặc thiếu concurrency; cần chính sách riêng.

## 8. Cảnh báo khó thấy: tài nguyên transaction sau commit có thể còn được bind

Spring Javadoc nêu một lưu ý quan trọng: tại `AFTER_COMMIT`/`AFTER_ROLLBACK`/`AFTER_COMPLETION`, DB transaction đã kết thúc, **nhưng resource gắn với transaction có thể vẫn còn active/bound với thread** trong giai đoạn callback.

Hệ quả: nếu listener gọi code DB tham gia lại resource cũ, thao tác ghi có thể tưởng vẫn trong transaction và **không được commit như bạn mong** vì commit chính đã xảy ra. Không nên suy luận rằng `AFTER_COMMIT` mặc nhiên tạo một transaction mới cho mọi lời gọi repository.

Nếu callback cần **ghi trạng thái bền vững mới sau commit**, hãy gọi một service bean khác với transaction mới thật sự:

~~~java
@Service
public class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordSent(long orderId) {
        auditRepository.insert(orderId);
    }
}
~~~

Đây là **đoạn tích hợp**, cần `@Service`, `@Transactional`, `Propagation`, `auditRepository` và transaction manager thích hợp. Caller phải gọi **qua Spring-managed proxy của service khác**; gọi `this.recordSent(...)` trong cùng bean thường bỏ qua advice trong proxy mode.

Tuy nhiên `REQUIRES_NEW` chỉ tạo transaction DB mới, **không** giải quyết toàn bộ vấn đề gửi message ra broker đúng một lần. Nếu crash giữa commit order và lần ghi audit/event mới, vẫn có cửa sổ mất thao tác. Những workflow quan trọng nên cân nhắc **transactional outbox**.

Trong demo mục 6, listener hậu commit **chỉ đọc qua connection độc lập** và không ghi trong resource cũ; điều đó cố ý tránh cạm bẫy trên.

## 9. Phân biệt tính đúng thời điểm với tính chắc chắn của giao sự kiện

Có hai câu hỏi hoàn toàn khác:

1. **Consumer có bị chạy trước khi DB commit không?** Sử dụng `AFTER_COMMIT` có thể đảm bảo một **callback trong cùng ứng dụng** được gọi sau commit thành công, giải quyết race nội bộ này.
2. **Event có chắc được lưu/gửi đến consumer sau commit không?** Chưa chắc. Sau khi DB commit nhưng trước khi gửi message bền vững thành công, JVM có thể crash, broker có thể từ chối hoặc network timeout. DB đã có order nhưng không có event tương ứng.

Timeline khác:

~~~text
BEGIN DB transaction
INSERT order 42
COMMIT thành công     <-- dữ liệu đã bền vững
    |
    +-- JVM crash / broker unavailable
    |
    +-- publish event never completed
        --> consumer không bao giờ được thông báo nếu không có recovery
~~~

Do đó, `@TransactionalEventListener(AFTER_COMMIT)` là lựa chọn hữu ích cho **event phụ trợ, xử lý cục bộ hoặc notification chấp nhận mất có thể phục hồi**, nhưng **không phải cơ chế bảo đảm event delivery bền vững giữa DB và broker**.

Ngay cả khi lời gọi send trong callback thành công, vẫn còn các trạng thái “broker đã nhận nhưng ACK bị mất” hoặc “consumer xử lý rồi crash trước khi xác nhận”; thiết kế đúng cần xử lý **trùng lặp** thay vì mặc định exactly-once từ đầu đến cuối.

## 10. Transactional outbox: ghi dữ liệu và ý định phát sự kiện trong một commit

Với nghiệp vụ yêu cầu **khi tạo order thành công phải có event tương ứng**, mẫu phổ biến là **transactional outbox**:

- Trong **cùng một DB transaction**, ghi record nghiệp vụ vào `orders` và ghi một record event vào bảng `outbox_events`.
- **Chỉ sau commit**, một poller hoặc CDC connector lấy outbox record đã commit để gửi đến broker.
- Nếu transaction rollback, cả order và event record đều rollback.
- Nếu app crash sau commit nhưng trước khi gửi broker, record outbox vẫn tồn tại và có thể được gửi lại.
- Vì poller có thể gửi lại khi mất ACK, consumer phải **idempotent**.

Luồng điển hình:

~~~text
Producer transaction T1
   |
   +-- INSERT orders(id=42,...)
   +-- INSERT outbox_events(event_id=E-1, aggregate_id=42,...)
   |
   +-- COMMIT atomically
             |
             v
  Poller/CDC chỉ nhìn thấy outbox đã commit
             |
             v
       Message broker
             |
             v
  Consumer nhận event và đọc state/order
             |
             +-- Dedupe event_id + áp dụng idempotent
~~~

**Outbox giải quyết khoảng trống dual-write**, vì intent phát sự kiện tồn tại cùng transaction với dữ liệu. Nó không bắt Kafka, RabbitMQ hay DB tham gia cùng một global transaction. Tuy nhiên nó **không loại bỏ duplicate**, không tự bảo đảm strict global ordering giữa nhiều aggregate và không giải quyết replication lag ở consumer nếu họ đọc bản sao chậm.

## 11. Ví dụ thiết kế outbox trong Spring

Ví dụ schema **minh họa theo SQL PostgreSQL** (không phải schema di động cho mọi engine):

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(32) NOT NULL
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ NULL
);
~~~

Một phương thức Spring `@Transactional` có thể ghi cả hai bảng:

~~~java
@Service
public class OrderCommandService {
    private final JdbcTemplate jdbc;

    public OrderCommandService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void create(long orderId, String eventJson, UUID eventId) {
        jdbc.update(
            "insert into orders(id, status) values (?, ?)",
            orderId, "NEW");

        jdbc.update(
            "insert into outbox_events" +
            "(event_id, aggregate_id, event_type, payload) " +
            "values (?, ?, ?, ?)",
            eventId, orderId, "OrderCreated", eventJson);
    }
}
~~~

Đây là **snippet tích hợp**: cần imports `JdbcTemplate`, `UUID`, `@Service`, `@Transactional`; datasource, migration và JSON serializer do ứng dụng cung cấp. Không phải một tệp Java chạy độc lập.

Cả hai `jdbc.update` phải dùng **cùng transaction manager và cùng DB transaction thực sự**, gọi method qua Spring transaction proxy. Nếu statement outbox thất bại rồi exception được truyền cho interceptor theo rollback rule, order cũng rollback. Nếu commit thành công, poller có thể đọc cả order lẫn outbox row.

Một schema production còn cần index cho polling, trạng thái lease/retry, số lần giao, last error, tenant/correlation ID, schema version, chính sách retention và bảo mật payload. Không lưu bí mật/PII nhạy cảm vào broker một cách vô kiểm soát.

**Đừng gửi broker bằng cách trực tiếp gọi `broker.send` giữa hai lệnh INSERT trong transaction** rồi coi đó là cùng một atomic commit: broker không tự tham gia DB transaction.

## 12. Poller, CDC và giới hạn của outbox

Có hai cách phổ biến đưa event outbox đi:

**Poller:** worker định kỳ lấy các row chưa gửi, claim/lock có giới hạn, publish message, rồi cập nhật trạng thái. Với nhiều instance, cần một cơ chế lease/lock đúng DB (ví dụ `FOR UPDATE SKIP LOCKED` trong PostgreSQL ở transaction ngắn), tránh các worker đồng thời chọn cùng một row theo cách không kiểm soát.

**CDC (change data capture):** một connector đọc thay đổi đã commit từ transaction log của DB, biến row outbox thành message. Debezium Outbox Event Router là một giải pháp ví dụ.

Cả hai vẫn phải xử lý:

- Broker không phản hồi, poller bị restart, transaction cập nhật `published_at` thất bại.
- Broker **đã nhận** message nhưng ACK mất, poller gửi lại cùng `event_id`.
- Message bị gửi/lưu trữ sai partition; các event cho cùng aggregate có thể bị nhận không theo thứ tự nếu không dùng khóa partition/version đúng.
- Backpressure: consumer xử lý chậm, backlog outbox tăng; cần metric lag, số event pending, retry và dead-letter strategy.
- Purge/retention: không xóa outbox row trước khi bảo đảm nó không còn cần recovery; xác nhận hợp đồng lưu trữ, kiểm soát archive.

Nếu production thực sự cần *exactly-once effect* lên business state, điều này thường phải đạt bằng **idempotent consumer, transaction ở bên nhận và deduplication**, không chỉ bằng kỳ vọng broker sẽ không gửi trùng.

## 13. Consumer sau commit vẫn phải chấp nhận eventual consistency

Thậm chí khi producer ghi outbox và commit trước khi message được gửi, consumer có thể đọc một **read replica chậm**, một cache chưa invalidated hoặc một search projection chưa cập nhật. Sự kiện đã hợp lệ nhưng phần dữ liệu consumer đọc chưa đuổi kịp.

Các chiến lược tùy nhu cầu:

1. **Event chứa đủ snapshot tối thiểu:** nếu consumer chỉ cần `orderId`, `status`, `total` tại thời điểm commit, có thể đặt các field đó (đã chuẩn hóa và kiểm soát privacy) trong payload; không bắt consumer luôn đi đọc lại DB producer.
2. **Read-your-writes/primary read:** với dữ liệu cần mới nhất, consumer có thể gọi API đọc primary (nếu được phép), thay vì read replica có lag.
3. **Version/sequence:** gắn `aggregateVersion` để consumer biết mình đang xử lý trạng thái nào; tránh event cũ ghi đè projection mới.
4. **Bounded retry có jitter:** nếu API đọc chỉ tạm thời chưa thấy row do replication lag, retry có giới hạn và deadline có thể hợp lý. Không biến “not found” thành vòng retry vô hạn.
5. **Reconciliation:** có job đối chiếu dữ liệu producer–consumer để sửa những sự kiện bị lỗi, thất lạc hoặc projection lệch.

Sự kiện “order được tạo” là một **sự thật nghiệp vụ có thời điểm**, không bảo đảm đối tượng sẽ mãi ở trạng thái `NEW`. Đến lúc consumer đọc, order có thể đã chuyển `PAID` hoặc `CANCELLED`. Nếu cần trạng thái “lúc phát event”, hãy gửi payload/version đúng thay vì coi mọi read hiện tại là dữ liệu của thời điểm event.

## 14. Idempotency và thứ tự sự kiện bên nhận

**Idempotency:** với mỗi event, producer nên tạo `eventId` ổn định. Consumer lưu event đã xử lý hoặc dùng unique constraint/business key để hai lần giao cùng event không tạo tác dụng phụ hai lần.

Một flow consumer dựa trên DB transaction:

~~~text
BEGIN
  INSERT processed_events(consumer_id, event_id)
      -- unique(consumer_id, event_id)
  IF duplicate:
      -- bỏ qua business effect trùng
  ELSE:
      UPDATE projection / apply side effect nội bộ
COMMIT
ACK message sau khi DB commit
~~~

Đây là **sơ đồ logic**, không phải SQL chạy nguyên xi. Việc insert dedupe marker và cập nhật business state nên nằm trong **cùng transaction của consumer**. Nếu ACK gửi trước commit, crash giữa hai bước có thể làm consumer bỏ mất effect. Nếu commit xong nhưng ACK mất, broker có thể gửi lại; dedupe xử lý được duplicate.

Với email hoặc thanh toán ở **hệ thống ngoài DB consumer**, một transaction nội bộ không bao trùm được side effect bên ngoài. Cần idempotency key của API bên ngoài, outbox/saga và reconciliation khi kết quả không rõ.

**Thứ tự:** `OrderCreated`, `OrderPaid` và `OrderCancelled` có thể đến lệch do nhiều partition/retry. Nếu trạng thái cần đúng trình tự, đưa event của cùng aggregate vào một key partition phù hợp và kiểm tra `aggregateVersion`, hoặc xây dựng quy tắc xử lý out-of-order. “Publish after commit” không tự bảo đảm order trên một hệ phân tán.

## 15. @Async và transaction context: hai thứ không tự truyền qua thread

Một anti-pattern dễ thấy trong Spring:

~~~java
@Transactional
public void createOrder(Order order) {
    repository.save(order);
    asyncNotifier.notifyCreated(order.getId());
    // Transaction trong caller vẫn có thể chưa commit.
}

@Async
public void notifyCreated(Long orderId) {
    // Đang chạy ở thread khác.
    externalConsumerOrDbRead(orderId);
}
~~~

Đây là **đoạn minh họa tích hợp**, không phải Java class độc lập. Nếu method `@Async` được gọi qua proxy, executor có thể chạy ngay khi được submit, **trước khi transaction trong caller commit**.

Transaction imperative của Spring gắn với thread: worker không tự được chia sẻ transaction đang mở của producer. Đây là lý do việc `@Async` không làm event được “an toàn hơn”; nó thường làm race rõ hơn.

Cũng đừng gửi một Hibernate/JPA entity đang managed hoặc một lazy-loaded proxy vào async event rồi tin rằng consumer sẽ truy cập được mọi property. Session/transaction có thể đóng; trạng thái object có thể mutable, lười tải hoặc không còn nhất quán. Dùng **event payload immutable** chứa ID, version, các field cần thiết, hoặc một DTO snapshot đúng contract.

Nếu muốn xử lý **sau commit nhưng không chặn thread commit**, có thể dùng một listener `@TransactionalEventListener(AFTER_COMMIT)` kích hoạt async task đã giới hạn concurrency. Cách này giải quyết thứ tự bắt đầu task trong nội bộ, nhưng vẫn có các rủi ro **sau commit nhưng chưa enqueue/persist**; với event bắt buộc phải giao, outbox thường phù hợp hơn.

## 16. Exception và rollback: đừng lấy kết quả publish làm kết quả commit

Một method `@Transactional` có thể publish event rồi cuối cùng ném exception:

~~~java
@Transactional
public void createOrder(long id) {
    repository.insert(id);
    publisher.publishEvent(new OrderCreated(id));
    if (businessRuleRejected(id)) {
        throw new IllegalStateException("Rejected");
    }
}
~~~

Đây là snippet mô phỏng, không có class chạy độc lập. Với rollback rule mặc định cho unchecked exception và một transaction manager phù hợp, database insert có thể rollback. Nhưng event thông thường được publish trước đó **không thể thu hồi** nếu consumer đã nhận hoặc message đã được broker ghi.

Khi dùng `@TransactionalEventListener(AFTER_COMMIT)`, callback không chạy nếu producer transaction rollback đúng cách. Tuy nhiên phải hiểu rollback rule thực tế:

- Checked exception không mặc định kích hoạt rollback theo cùng cách với unchecked exception nếu không cấu hình.
- Nếu code bắt exception rồi kết thúc bình thường, transaction có thể commit trừ khi đã `setRollbackOnly()` hoặc có cấu hình khác.
- Việc tham gia transaction sẵn có và `Propagation.REQUIRES_NEW` thay đổi ranh giới commit.
- Self-invocation của `@Transactional` trong proxy mode có thể bỏ qua transaction advice.
- Chỉ có **một transaction thực sự bao trùm** các write thì commit mới cho visibility mong muốn.

Nói “method đã chạy xong” chưa đủ; cần xác minh transaction nào thực sự commit và khi nào. Với `TransactionTemplate`, callback transaction chỉ trả về sau khi commit/rollback của transaction mà template quản lý hoàn tất.

## 17. Test đúng: quan sát từ transaction/connection khác

Các test chỉ assert `repository.save()` hoặc gọi `findById()` trong cùng transaction không chứng minh consumer bên ngoài nhìn thấy dữ liệu đã commit. Một integration test đúng cần:

1. **Primary DB và transaction thật:** test dưới `READ_COMMITTED` hoặc isolation tương ứng, không dựa trên mock `EntityManager`.
2. **Connection độc lập:** producer giữ transaction chưa commit, consumer query qua connection khác hoặc thread khác, xác nhận không thấy row trước commit.
3. **After commit:** commit producer rồi query lại bằng transaction đọc mới, xác nhận row hiển thị.
4. **Rollback:** bắt transaction rollback; listener `AFTER_COMMIT` không chạy và consumer không thấy row chưa commit.
5. **Race có kiểm soát:** dùng `CountDownLatch` để giữ producer trước commit; kích hoạt consumer trước/sau qua latch. Không dựa vào `Thread.sleep(10)` và hy vọng timing đúng.
6. **Spring proxy:** test `@Transactional` và `@Async` qua các Spring-managed beans; `this.method()` có thể vô hiệu hóa advice.
7. **Transaction event factory:** bật `@EnableTransactionManagement` trong Framework test hoặc cấu hình tương đương; xác nhận listener có chạy đúng phase.
8. **Mất event sau commit:** giả lập broker/poller unavailable sau commit; nếu dùng outbox, record vẫn tồn tại và có thể redeliver.
9. **Duplicate:** gửi cùng `eventId` hai lần; consumer không ghi business effect trùng.
10. **Replica lag và out-of-order:** cho consumer nhìn snapshot cũ hoặc nhận version sau trước; xác nhận logic retry/version không ghi đè trạng thái đúng.

Khi dùng `@Transactional` trên **phương thức test** (ví dụ `@Transactional` của Spring Test) và framework tự rollback cuối test, listener `AFTER_COMMIT` có thể **không chạy**. Đây là lý do cần một test điều khiển commit thật bằng `TransactionTemplate` hoặc test transaction API phù hợp.

Trong bài demo mục 6, commit được điều khiển tường minh nên không bị che bởi transaction rollback mặc định của test framework.

## 18. Chẩn đoán production bằng log và metric

Nên có correlation xuyên suốt producer → outbox/broker → consumer:

| Trường | Ý nghĩa |
| --- | --- |
| `eventId` | Khóa duy nhất phục vụ dedupe, truy vết retry |
| `aggregateId` | Order/customer/tài nguyên nghiệp vụ liên quan |
| `aggregateVersion` | Dùng kiểm tra ordering và projection stale |
| `producedAt` | Thời gian logic event được tạo; **không** thay thế commit timestamp |
| `outboxCommittedAt` hoặc `createdAt` | Hỗ trợ ước lượng lag, cần hiểu cách DB/clock ghi nhận |
| `publishedAt` | Thời điểm broker send/ACK được ghi nhận theo policy |
| `consumedAt` | Thời điểm consumer bắt đầu/hoàn tất xử lý |
| `traceId` | Liên kết request và background processing mà không dùng raw PII |

Các metric thiết yếu: event pending trong outbox, **oldest pending age**, publish retries, broker acknowledgement failures, duplicate events, consumer processing latency, row-not-found sau event, replication lag và dead-letter count. Tránh dùng raw eventId/orderId làm metric label có cardinality cao; dùng log hoặc tracing có phân quyền.

Nếu consumer hay gặp `not found` ngay sau event, kiểm tra **thời điểm publish so với commit**, isolation, read replica routing và transaction snapshot của consumer. Tăng số retry có thể chỉ che giấu race và làm DB nóng hơn.

## 19. Ma trận lựa chọn theo độ tin cậy

| Nhu cầu | Cách tiếp cận | Hợp đồng và giới hạn |
| --- | --- | --- |
| Listener nội bộ chỉ cần quan sát event sau commit | `@TransactionalEventListener(AFTER_COMMIT)` | Đúng phase; không tự đảm bảo event surviving crash |
| Async notification không quá quan trọng, có thể tái tạo | `AFTER_COMMIT` rồi submit task tới executor có giới hạn | Có rủi ro crash/rejection sau commit; cần monitor |
| Bắt buộc broker nhận event cho mọi order đã commit | Transactional outbox + poller/CDC | Atomic DB state+intent; consumer idempotent, monitoring retry |
| Consumer đọc replica/projection có lag | Payload/version + read policy + bounded retry/reconciliation | After commit vẫn có eventual consistency |
| Nhiều producer hoặc message broker ordering phức tạp | Aggregate version/partitioning + idempotency | Không suy luận global order từ local commit |
| Cross-service state cập nhật theo nhiều bước | Saga/workflow và compensation, outbox mỗi chặng nếu cần | Không có một local DB transaction cho toàn hệ thống |

Không có giải pháp đơn nhất cho mọi workload. **Chọn trước hợp đồng nghiệp vụ**: chấp nhận event mất hay không, consumer cần payload gì, phải trả lời trong bao lâu, làm sao khôi phục khi crash, và xử lý được duplicate/out-of-order ở mức nào.

## 20. Những hiểu nhầm phổ biến

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`repository.save()` đã trả về thì DB chắc chắn commit.” | Thao tác có thể nằm trong transaction chưa commit. |
| “`publishEvent()` mặc nhiên chờ giao dịch kết thúc.” | Listener thông thường có thể chạy ngay trong transaction đang mở. |
| “Listener đọc được row nghĩa là consumer khác cũng đọc được.” | Listener có thể đang dùng **cùng connection/transaction** của producer. |
| “Đánh dấu `@Async` cho listener sẽ tránh race.” | Async làm scheduling độc lập; có thể chạy trước commit. |
| “`@TransactionalEventListener` chạy ngay cả khi không có transaction.” | Mặc định không chạy; `fallbackExecution=true` mới cho phép. |
| “`AFTER_COMMIT` là một transaction mới.” | Resource cũ có thể còn bound; ghi dữ liệu mới có thể cần `REQUIRES_NEW`. |
| “`AFTER_COMMIT` bảo đảm Kafka luôn có message.” | Có khoảng trống crash giữa DB commit và broker publish. |
| “Outbox nghĩa là consumer không bao giờ nhận trùng.” | Poller/CDC/broker có thể redeliver; cần idempotency. |
| “Sau commit thì replica ngay lập tức cập nhật.” | Replica, cache và projection có thể có lag. |
| “Một event luôn mô tả state hiện tại khi consumer đọc.” | State có thể đã tiến lên version mới. |
| “Transaction của producer truyền qua worker `@Async`.” | Imperative transaction gắn với thread/context, không tự truyền sang worker. |
| “Retry mãi lỗi `not found` là đủ an toàn.” | Có thể rollback, sai ID, thiếu outbox hoặc trùng tác dụng phụ; retry phải hữu hạn. |

## 21. Checklist thiết kế trước khi triển khai

- Tôi biết **giao dịch producer mở ở đâu, commit lúc nào**, có proxy `@Transactional` thực sự và rollback rule đúng.
- Tôi không phát sự kiện ra consumer độc lập trước commit nếu consumer cần state đã commit.
- Tôi phân biệt `@EventListener`, `@TransactionalEventListener(AFTER_COMMIT)` và `@Async`.
- Tôi kiểm tra listener transactional chỉ chạy khi có transaction (hoặc fallback được chọn có chủ đích).
- Tôi hiểu `AFTER_COMMIT` không tự tạo transaction mới; write từ callback cần ranh giới phù hợp.
- Tôi đã xác định **event mất sau DB commit** có chấp nhận được không; nếu không, có outbox/CDC hoặc cơ chế bền vững tương đương.
- Consumer có `eventId`/business key chống duplicate, đủ thông tin để xử lý out-of-order.
- Tôi xác nhận consumer đọc primary, replica hay cache và có phương án xử lý replication lag.
- Tôi giới hạn retry, backpressure, queue concurrency và có dead-letter/reconciliation.
- Tôi kiểm tra event chứa dữ liệu immutable theo contract, không phụ thuộc vào JPA managed entity/lazy session.
- Tôi có integration test trên hai connection với commit/rollback thật, không chỉ mock.
- Tôi theo dõi outbox lag, broker publish failure, consumer processing, duplicate và “row not found” bằng metric/log phù hợp.

**Kết luận:** Khi producer phát event trước khi giao dịch SQL commit, consumer độc lập có thể đọc thấy dữ liệu cũ hoặc chưa tồn tại; event còn có thể mô tả trạng thái bị rollback. `@TransactionalEventListener(AFTER_COMMIT)` giải quyết **thứ tự callback so với commit** trong Spring. Nếu nghiệp vụ còn cần **không mất sự kiện sau commit**, hãy ghi **business state và event intent cùng một DB transaction** (transactional outbox), rồi gửi qua poller/CDC và xử lý duplicate ở consumer. Kể cả sau commit, read replica/cache vẫn cần chính sách eventual consistency.

## Tài liệu tham khảo

- [Spring Framework: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — event gắn với transaction phase, fallbackExecution, imperative/reactive context.
- [Spring Framework 6.2: TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html) — AFTER_COMMIT mặc định, AFTER_ROLLBACK, resource còn bound sau completion.
- [Spring Framework 6.2: TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionPhase.html) — ý nghĩa BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION.
- [Spring Framework: Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — proxy, rollback, transaction boundaries.
- [Spring Framework: Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html) — `ApplicationEventPublisher` và event listener trong Spring context.
- [Spring Framework: TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html) — afterCommit/afterCompletion, cảnh báo dữ liệu mới cần transaction riêng.
- [Debezium: Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html) — một cách chuyển outbox rows thành message qua CDC.
