# fallbackExecution và hành vi dự phòng

`@TransactionalEventListener` gắn việc xử lý application event với một phase của transaction. Mặc định, listener chỉ chạy khi Spring có thể đăng ký callback với transaction hiện tại; phase mặc định là `TransactionPhase.AFTER_COMMIT`. Nếu event được publish ngoài transaction phù hợp, listener bị bỏ qua.

Thuộc tính `fallbackExecution` cho phép chọn hành vi khi không thể đăng ký transaction synchronization. Khi đặt `fallbackExecution = true`, Spring gọi listener ngay trong lần dispatch event. Đây là xử lý ngay khi không có transaction, không phải tạo transaction thay thế và cũng không phải chờ transaction kế tiếp.

Điểm quan trọng: nếu transaction đang hoạt động và Spring đăng ký được synchronization, fallback không được dùng. Listener vẫn chạy theo phase đã khai báo. Bài viết giải thích hành vi này trong Spring Framework 6.2, các trường hợp dễ hiểu nhầm và ví dụ Java 17 kiểm tra publish ngoài transaction, commit và rollback.

## 1. Hành vi mặc định khi không có transaction

~~~java
@TransactionalEventListener
public void handleOrderCreated(OrderCreated event) {
    System.out.println("Order created: " + event.orderId());
}
~~~

Không khai báo `phase` nghĩa là `AFTER_COMMIT`. Spring chỉ gọi method khi event được publish trong transaction mà listener có thể gắn vào. Nếu không có transaction, listener bị bỏ qua.

Ví dụ:

~~~java
applicationEventPublisher.publishEvent(
        new OrderCreated("ORD-133"));
~~~

Nếu lời gọi này diễn ra ngoài transaction, listener ở trên không chạy. Spring không giữ event lại để xử lý khi transaction khác bắt đầu, cũng không tự mở transaction mới.

Theo Javadoc Spring Framework 6.2.0, event publish ngoài active transaction bị discard đối với transactional listener, trừ khi bật `fallbackExecution`. Đây là hành vi riêng của listener này; các `@EventListener` thông thường hoặc listener khác vẫn có thể nhận cùng event.

## 2. fallbackExecution làm gì?

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void handleOrderCreated(OrderCreated event) {
    System.out.println("Order created: " + event.orderId());
}
~~~

Khi Spring không thể đăng ký listener với transaction synchronization, `fallbackExecution = true` cho phép xử lý event ngay trong lần dispatch hiện tại.

| Trạng thái khi dispatch | fallbackExecution | Hành vi |
|---|---:|---|
| Có transaction phù hợp, đăng ký synchronization thành công | false hoặc true | Đăng ký callback và chờ phase |
| Không có transaction phù hợp | false | Bỏ qua listener |
| Không có transaction phù hợp | true | Gọi listener ngay |

`fallbackExecution` không phải cờ “luôn chạy ngay”. Nó chỉ quyết định nhánh xử lý khi Spring không thể gắn event với transaction.

### 2.1. Fallback không tạo transaction

Nếu event được publish ngoài transaction và fallback bật, method listener chạy mà không có transaction của publisher:

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void sendNotification(OrderCreated event) {
    notificationClient.send(event.orderId());
}
~~~

Việc bật fallback không tự tạo transaction cho các thao tác database trong method. Nếu listener cần ghi database trong một transaction riêng, hãy gọi một service có transaction phù hợp. Fallback không tự tạo transaction mới cho listener.

### 2.2. Fallback không phải hàng đợi

Khi fallback tắt, event không được giữ để chạy trong transaction tiếp theo. Khi fallback bật, event được xử lý ngay. Không có trạng thái pending để Spring tự phát lại khi ứng dụng mở transaction.

Nếu cần lưu event để xử lý sau, retry hoặc khôi phục sau process restart, hãy dùng message broker hoặc transactional outbox.

### 2.3. Fallback chỉ tác động listener được đánh dấu

Một event có thể có listener thường và transactional listener:

~~~java
@EventListener
public void updateMetrics(OrderCreated event) {
    // Listener thông thường.
}

@TransactionalEventListener
public void updateAfterCommit(OrderCreated event) {
    // Listener gắn với transaction.
}
~~~

Khi publish ngoài transaction, listener thường vẫn được gọi theo event multicaster; transactional listener mặc định bị bỏ qua. Bật fallback chỉ thay đổi listener có cấu hình đó, không thay đổi semantics của toàn bộ event multicaster.

## 3. Spring quyết định dùng fallback khi nào?

Method có `@TransactionalEventListener` được Spring chuyển thành transactional listener adapter. Khi adapter nhận event, nó thử đăng ký transaction synchronization trước.

~~~text
publishEvent(event)
       |
       v
transactional listener adapter
       |
       v
đăng ký được transaction synchronization?
       /                       \
     Có                         Không
     |                            |
     v                            v
đăng ký callback             fallbackExecution?
     |                       /             \
     v                    false             true
chờ phase                    |                |
     |                       v                v
     v                    bỏ qua          gọi ngay
gọi đúng phase
~~~

Với imperative transaction, Spring kiểm tra synchronization active và actual transaction active trên thread hiện tại:

~~~java
TransactionSynchronizationManager.isSynchronizationActive()
        && TransactionSynchronizationManager.isActualTransactionActive()
~~~

Chỉ có synchronization active chưa chắc đã có actual transaction. Một số propagation có thể bật synchronization nhưng không có backing resource transaction. Transactional event listener cần actual transaction để bảo đảm semantics của phase.

Với reactive transaction, Spring dùng Reactor Context thay cho ThreadLocal. Event cần mang transaction context làm source, thường qua `TransactionalEventPublisher`. Nếu không tìm thấy context phù hợp, adapter không đăng ký được synchronization và nhánh fallback có thể được áp dụng.

### 3.1. Có transaction thì phase luôn được ưu tiên

Spring đăng ký synchronization trước. Nếu registration thành công, fallback không được dùng; listener vẫn tuân theo `phase` đã khai báo:

- `BEFORE_COMMIT`: trước commit.
- `AFTER_COMMIT`: sau commit thành công.
- `AFTER_ROLLBACK`: sau rollback.
- `AFTER_COMPLETION`: sau commit hoặc rollback.

Fallback chỉ được xét khi registration thất bại. Vì vậy không dùng `fallbackExecution = true` để thay đổi phase hoặc để listener chạy ngay trong transaction.

### 3.2. AFTER_ROLLBACK với fallback=true

Đây là trường hợp dễ gây lỗi nghiệp vụ:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK,
        fallbackExecution = true)
public void compensate(OrderFailed event) {
    paymentGateway.refund(event.paymentId());
}
~~~

Nếu event được publish ngoài transaction, không có rollback nào xảy ra. Tuy nhiên, vì fallback bật, listener vẫn được gọi ngay trong lần dispatch event. Spring 6.2 ghi cảnh báo khi xử lý fallback với phase `AFTER_ROLLBACK`.

Tương tự, `BEFORE_COMMIT` với fallback có thể chạy ngay cả khi không tồn tại commit nào. Khi không có transaction, phase không thể được thực hiện theo nghĩa transaction lifecycle; fallback chỉ là lời gọi ngay.

Nếu nghiệp vụ đòi hỏi “chỉ sau commit” hoặc “chỉ sau rollback”, hãy giữ fallback mặc định là false.

## 4. Fallback không xử lý mọi loại lỗi

`fallbackExecution` chỉ xử lý trường hợp listener không đăng ký được transaction synchronization. Nó không phải cơ chế dự phòng chung:

| Tình huống | Có fallback? | Lý do |
|---|---|---|
| Publish ngoài transaction | Có | Không đăng ký được synchronization |
| Event ở thread không mang transaction hiện tại | Có thể | Adapter không thấy transaction |
| Reactive event thiếu TransactionContext trong source | Có thể | Adapter không tìm thấy reactive transaction |
| Đã đăng ký synchronization rồi transaction rollback | Không | Listener tuân theo phase |
| Listener ném exception | Không | Đây là lỗi xử lý listener |
| Executor từ chối task | Không | Đây là lỗi dispatch/executor |
| SpEL condition không thỏa | Không | Event bị lọc |
| Event không khớp kiểu listener | Không | Listener không được chọn |

Không bật fallback để che lỗi cấu hình transaction manager, mất thread context hoặc lỗi publish event. Trước tiên hãy xác định vì sao registration không thành công.

## 5. Fallback và bốn transaction phase

| Phase | Khi có transaction | Khi không có transaction và fallback=true |
|---|---|---|
| `BEFORE_COMMIT` | Gọi trước commit | Gọi ngay; không có commit |
| `AFTER_COMMIT` | Gọi sau commit thành công | Gọi ngay; không có commit |
| `AFTER_ROLLBACK` | Gọi sau rollback | Gọi ngay; không có rollback, có cảnh báo |
| `AFTER_COMPLETION` | Gọi sau commit hoặc rollback | Gọi ngay; không có completion |

Phase mặc định là `AFTER_COMMIT`. Vì vậy nếu bật fallback mà không khai báo phase, listener vẫn xử lý ngay khi event publish ngoài transaction.

Nếu cần semantics chặt chẽ, giữ `fallbackExecution = false`. Nếu cần một handler dùng được cả trong và ngoài transaction, có thể bật fallback nhưng phải chấp nhận hai thời điểm xử lý: sau transaction phase khi có transaction, và ngay lúc publish khi không có transaction.

## 6. Ví dụ hoàn chỉnh với Java 17 và Spring Framework 6.2

Ví dụ dùng Spring Context, Spring JDBC, Spring TX và H2. Cùng một event được publish trong ba tình huống:

1. Ngoài transaction: listener mặc định bị bỏ qua, listener có fallback chạy ngay.
2. Trong transaction commit thành công: cả hai listener chạy sau commit.
3. Trong transaction rollback: listener AFTER_COMMIT không chạy; listener AFTER_ROLLBACK chạy.

**Cấu trúc dự án**

~~~text
fallback-execution-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── FallbackExecutionDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>fallback-execution-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.0</version>
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
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.FallbackExecutionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/FallbackExecutionDemo.java**

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class FallbackExecutionDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    create table orders (
                        id varchar(40) primary key
                    )
                    """);

            ApplicationEventPublisher publisher = context;
            OrderService service = context.getBean(OrderService.class);

            publisher.publishEvent(new OrderCreated("ORD-OUTSIDE"));
            service.createAndCommit("ORD-COMMIT");

            try {
                service.createAndRollback("ORD-ROLLBACK");
            }
            catch (IllegalStateException expected) {
                System.out.println("Rollback requested");
            }

            Integer committedRows =
                    jdbc.queryForObject(
                            "select count(*) from orders",
                            Integer.class);
            System.out.println("Committed rows: " + committedRows);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        public DriverManagerDataSource dataSource() {
            var dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl("jdbc:h2:mem:fallback;DB_CLOSE_DELAY=-1");
            dataSource.setUsername("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DriverManagerDataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DriverManagerDataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        public OrderListeners orderListeners() {
            return new OrderListeners();
        }
    }

    public record OrderCreated(String orderId) {
    }

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
        public void createAndCommit(String orderId) {
            jdbc.update("insert into orders(id) values (?)", orderId);
            System.out.println("published: " + orderId);
            publisher.publishEvent(new OrderCreated(orderId));
        }

        @Transactional
        public void createAndRollback(String orderId) {
            jdbc.update("insert into orders(id) values (?)", orderId);
            System.out.println("published: " + orderId);
            publisher.publishEvent(new OrderCreated(orderId));
            throw new IllegalStateException("Simulate rollback");
        }
    }

    public static class OrderListeners {

        @Order(10)
        @TransactionalEventListener
        public void afterCommitDefault(OrderCreated event) {
            System.out.println("default AFTER_COMMIT: " + event.orderId());
        }

        @Order(20)
        @TransactionalEventListener(fallbackExecution = true)
        public void afterCommitWithFallback(OrderCreated event) {
            System.out.println("fallback AFTER_COMMIT: " + event.orderId());
        }

        @Order(30)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderCreated event) {
            System.out.println("AFTER_ROLLBACK: " + event.orderId());
        }
    }
}
~~~

**Chạy chương trình**

Từ thư mục chứa `pom.xml`, chạy:

~~~bash
mvn -q compile exec:java
~~~

Output:

~~~text
fallback AFTER_COMMIT: ORD-OUTSIDE
published: ORD-COMMIT
default AFTER_COMMIT: ORD-COMMIT
fallback AFTER_COMMIT: ORD-COMMIT
published: ORD-ROLLBACK
AFTER_ROLLBACK: ORD-ROLLBACK
Rollback requested
Committed rows: 1
~~~

**Giải thích kết quả**

1. `ORD-OUTSIDE` được publish ngoài transaction. Listener mặc định không chạy. Listener có `fallbackExecution=true` được gọi ngay, dù phase vẫn ghi là `AFTER_COMMIT`.
2. `ORD-COMMIT` được publish trong transaction. Spring đăng ký cả hai listener AFTER_COMMIT vào synchronization. Fallback không được dùng; cả hai chạy sau commit.
3. `ORD-ROLLBACK` được publish trong transaction rồi service ném RuntimeException. Transaction rollback. Hai listener AFTER_COMMIT không chạy; listener AFTER_ROLLBACK được gọi.
4. Truy vấn cuối chỉ thấy một row đã commit.

Ví dụ dùng record Java thông thường làm event payload. Spring 4.2+ hỗ trợ publish POJO qua `ApplicationEventPublisher.publishEvent(Object)`; không cần event kế thừa `ApplicationEvent`.

## 7. Dùng fallback với AFTER_ROLLBACK có nguy hiểm không?

Có thể nguy hiểm nếu hiểu fallback là “chỉ chạy khi rollback”. Khi event được publish trong transaction thật, method chạy sau rollback. Nhưng nếu publisher phát event ngoài transaction, method chạy ngay do fallback. Khi đó có thể hoàn tiền dù chưa có transaction nào rollback.

Với handler có side effect như hoàn tiền, hủy booking hoặc gửi thông báo thất bại, hãy giữ fallback tắt hoặc tách hai use case thành hai listener/command rõ ràng. Không dùng fallback để thay thế điều kiện nghiệp vụ “đã rollback”.

## 8. Imperative và reactive transaction

Với transaction imperative, Spring giữ transaction state và synchronization trong thread hiện tại. Listener có thể không tìm thấy transaction khi event được publish trước/sau transaction, từ một thread khác, qua lời gọi không đi qua proxy `@Transactional`, hoặc khi synchronization active nhưng không có actual transaction.

Nếu fallback bật, các tình huống trên có thể khiến listener chạy ngay. Fallback có thể che một lỗi kiến trúc: code đáng lẽ publish trong transaction nhưng thực tế đã chạy ngoài transaction.

Từ Spring 6.1, `@TransactionalEventListener` cũng hỗ trợ reactive transaction. Reactive transaction dùng Reactor Context thay cho ThreadLocal. Event cần mang transaction context làm source, thường qua `TransactionalEventPublisher`:

~~~java
return databaseOperation
        .then(transactionalEventPublisher.publishEvent(
                new OrderCreated("ORD-REACTIVE")))
        .as(transactionalOperator::transactional);
~~~

Nếu dùng `applicationEventPublisher.publishEvent(new OrderCreated(...))` trực tiếp, event không tự mang reactive transaction context. Khi đó adapter không đăng ký được reactive synchronization; fallback có thể gọi listener ngay và che lỗi thiếu context.

Với reactive transaction, compose Mono trả về từ `TransactionalEventPublisher` vào cùng pipeline. Không dùng fallback để thay thế việc truyền đúng Reactor Context.

## 9. Annotation attributes, exception và tài nguyên

`@TransactionalEventListener` còn hỗ trợ `condition` (SpEL), `id` và `classes`/`value`. Fallback không bỏ qua SpEL condition. Trong Spring 6.2, `fallbackExecution` là alias cho `EventListener.defaultExecution`.

Với multicaster mặc định đồng bộ, fallback gọi method ngay trong lần dispatch; exception có thể truyền ngược về publisher. Không có transaction publisher để rollback side effect đã thực hiện trước khi lỗi.

Khi transaction registration thành công, listener chạy theo phase. Exception ở `BEFORE_COMMIT` có thể ảnh hưởng commit; exception ở phase sau completion không thể rollback một transaction đã commit.

Ở `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`, resource có thể còn được bind trong cleanup. Nếu listener cần ghi dữ liệu mới, hãy gọi service mở transaction độc lập, thường dùng `Propagation.REQUIRES_NEW`. Fallback ngoài transaction cũng cần transaction riêng nếu thao tác ghi yêu cầu tính nguyên tử.

## 10. Khi nào nên bật fallbackExecution?

| Nhu cầu | Khuyến nghị |
|---|---|
| Chỉ xử lý sau khi transaction commit | Giữ `false` |
| Chỉ xử lý khi transaction rollback | Giữ `false` |
| Event hợp lệ cả trong và ngoài transaction; ngoài transaction cần xử lý ngay | Có thể bật `true` |
| Muốn tự mở transaction khi không có transaction | Fallback không đáp ứng; cấu hình transaction riêng |
| Muốn retry event sau commit | Dùng outbox hoặc message broker |
| Muốn che việc mất transaction context | Sửa transaction boundary/context |
| Dùng `AFTER_ROLLBACK` để hoàn tiền nhưng event có thể publish ngoài transaction | Giữ fallback tắt hoặc tách luồng xử lý |

Bật fallback chỉ khi handler có ý nghĩa nghiệp vụ rõ ràng trong cả hai trường hợp — event được gắn với transaction và event được publish ngoài transaction.

## 11. Kiểm thử và lỗi thường gặp

Integration test nên kiểm tra ba đường:

1. Không có transaction, fallback=false: listener không được gọi.
2. Không có transaction, fallback=true: listener được gọi ngay.
3. Có transaction: fallback không được dùng; listener chạy theo phase sau commit hoặc rollback.

Không chỉ gọi trực tiếp method listener trong test, vì cách đó bỏ qua adapter, transaction synchronization và nhánh fallback. Với Spring Test, chú ý test method có thể được framework bọc trong transaction rồi rollback khi kết thúc; muốn kiểm tra ngoài transaction, publish từ code thật sự không nằm trong test transaction.

Các lỗi hay gặp:

- Cho rằng fallback=true luôn gọi listener ngay; khi registration thành công, listener vẫn chờ phase.
- Cho rằng fallback mở transaction mới hoặc lưu event để chạy sau.
- Bật fallback cho AFTER_ROLLBACK và vô tình chạy compensation khi chưa có rollback.
- Dùng fallback để che lỗi proxy, thread hoặc Reactor Context.
- Cho rằng listener thường cũng bị bỏ qua khi transactional listener bị skip.
- Dùng fallback để bảo đảm retry hoặc delivery sau process crash.
- Ghi database trong fallback và nghĩ transaction của publisher bảo vệ thao tác đó.

## 12. Ghi nhớ

`fallbackExecution` mặc định là `false`. Khi Spring không thể đăng ký transactional listener với transaction synchronization, false bỏ qua listener; true gọi listener ngay trong lần dispatch event.

Nếu transaction đang hoạt động và registration thành công, listener vẫn chạy theo `phase` đã khai báo dù fallback bật. Khi không có transaction, phase không được thực hiện theo nghĩa transaction lifecycle: `AFTER_COMMIT` không chờ commit, `AFTER_ROLLBACK` không chờ rollback và `BEFORE_COMMIT` không có commit nào phía sau.

Fallback không mở transaction, không lưu event để xử lý sau, không retry và không bảo đảm delivery sau process crash. Hãy bật nó chỉ khi xử lý ngay ngoài transaction là hành vi nghiệp vụ có chủ đích.

## Tài liệu tham khảo — Spring Framework 6.2

- [Transaction-bound Events — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [TransactionalEventListener Javadoc — Spring Framework 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [TransactionalApplicationListenerMethodAdapter source — Spring Framework 6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-tx/src/main/java/org/springframework/transaction/event/TransactionalApplicationListenerMethodAdapter.java)
- [TransactionalApplicationListenerSynchronization source — Spring Framework 6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-tx/src/main/java/org/springframework/transaction/event/TransactionalApplicationListenerSynchronization.java)
- [TransactionSynchronizationManager Javadoc — Spring Framework 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [TransactionPhase Javadoc — Spring Framework 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [TransactionalEventPublisher Javadoc — Spring Framework 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
