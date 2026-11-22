# Ảnh hưởng của event multicaster đến transaction trong Spring Framework

## 1. Vấn đề: phát event trong transaction có nghĩa là gì?

Giả sử ứng dụng đang tạo hóa đơn trong một phương thức được Spring quản lý bằng `@Transactional`. Ngay sau lệnh ghi dữ liệu, phương thức gọi `ApplicationEventPublisher.publishEvent(new InvoiceCreated(...))`. Có hai câu hỏi độc lập:

1. **Listener chạy ở đâu và lúc nào?** Việc này phụ thuộc vào `ApplicationEventMulticaster` và các annotation như `@Async`.
2. **Listener chạy trong bối cảnh giao dịch nào?** Việc này phụ thuộc vào transaction đang gắn với thread nào, listener thuộc loại nào, và listener có được ràng buộc với pha giao dịch hay không.

`ApplicationEventMulticaster` có nhiệm vụ chọn và phân phối event cho các listener thích hợp; nó **không phải transaction manager**, không tự mở, commit hoặc rollback một transaction cho từng listener. Đổi cấu hình multicaster có thể khiến một listener từ chỗ được gọi trong transaction của publisher chuyển sang chạy ở thread khác **không có transaction đó**. Sự khác biệt này ảnh hưởng trực tiếp tới độ nhất quán dữ liệu, xử lý lỗi và thời điểm gửi thông báo ra hệ thống bên ngoài.

Bài này tập trung vào Spring Framework 6.1+ với **transaction kiểu imperative** qua `PlatformTransactionManager` (ví dụ JDBC/JPA), đồng thời chỉ rõ điểm khác khi dùng reactive transaction.

## 2. Mặc định: `SimpleApplicationEventMulticaster` gọi đồng bộ

Nếu ứng dụng không định nghĩa bean đặc biệt có tên `applicationEventMulticaster`, `ApplicationContext` thường sử dụng `SimpleApplicationEventMulticaster` ở chế độ đồng bộ. Với `@EventListener` thông thường:

- Publisher gọi `publishEvent(event)` ngay trong thread hiện tại.
- Multicaster tìm các listener tương ứng rồi gọi trực tiếp trong thread đó.
- `publishEvent(...)` thường chỉ trở về sau khi các listener đồng bộ chạy xong.
- Nếu thread của publisher đang được Spring gắn với một transaction, listener đồng bộ thường nhìn thấy **cùng transaction thread-bound** và cùng những resource được quản lý theo transaction đó.
- Listener không tự có transaction mới: nó đang chạy bên trong phạm vi transaction vốn đã tồn tại của publisher, trừ khi có cấu hình propagation khác được áp dụng qua proxy giao dịch.

Ví dụ minh họa trong một service được gọi **qua Spring proxy**:

```java
@Service
public class InvoiceService {
    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher publisher;

    public InvoiceService(JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
        this.jdbc = jdbc;
        this.publisher = publisher;
    }

    @Transactional
    public void issueInvoice(long invoiceId) {
        jdbc.update("INSERT INTO invoices (id) VALUES (?)", invoiceId);
        publisher.publishEvent(new InvoiceCreated(invoiceId));
        // Transaction thường chỉ commit sau khi method kết thúc thành công.
    }
}
```

Đây là **đoạn tích hợp**, giả định có bảng `invoices`, record `InvoiceCreated`, bean `JdbcTemplate` và transaction manager phù hợp. Nếu listener đồng bộ cập nhật thêm bảng khác bằng cùng JDBC transaction, thay đổi của cả publisher và listener có thể cùng commit hoặc rollback. Tuy nhiên, gửi HTTP, email hay publish tới một broker ở listener đồng bộ **không tự động được database transaction hoàn tác**. Nếu transaction DB rollback sau khi email đã gửi, email vẫn có thể tồn tại.

### Exception và rollback ở chế độ đồng bộ

Với cấu hình multicaster mặc định không có `ErrorHandler` riêng, exception từ một listener đồng bộ có thể truyền ngược qua `publishEvent(...)` đến publisher. Nếu đó là unchecked exception thoát khỏi phương thức `@Transactional`, Spring mặc định đánh dấu rollback đối với `RuntimeException` và `Error`. Đây là hiệu ứng của **ranh giới transaction**, không phải multicaster tự rollback.

Nếu publisher bắt rồi nuốt exception, nếu multicaster được cấu hình một `ErrorHandler` để xử lý lỗi, hoặc nếu transaction có rollback rules tùy biến, kết quả có thể khác. Không nên viết nghiệp vụ dựa trên giả định rằng mọi lỗi listener luôn khiến database rollback.

## 3. Đổi multicaster sang bất đồng bộ: transaction không tự đi theo thread

Có thể đăng ký một bean `applicationEventMulticaster` và gắn `TaskExecutor`:

```java
@Configuration
class EventDispatchConfig {
    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") TaskExecutor eventExecutor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(eventExecutor);
        return multicaster;
    }
}
```

Đoạn cấu hình này cần sẵn các import của Spring và một bean `TaskExecutor` tên `eventExecutor`, ví dụ `ThreadPoolTaskExecutor`. Nó thay đổi cơ chế dispatch của những listener **cho phép** chạy bất đồng bộ.

Khi một `@EventListener` thông thường chạy qua executor ở thread khác:

1. Thread phát event có thể tiếp tục và hoàn tất transaction trước khi listener bắt đầu hoặc kết thúc.
2. Với transaction JDBC/JPA kiểu imperative, ngữ cảnh Spring transaction mặc định được quản lý bằng `ThreadLocal`, nên không tự xuất hiện trên thread của executor.
3. `TransactionSynchronizationManager.isActualTransactionActive()` thường trả về `false` trên thread listener bất đồng bộ, dù publisher đang ở trong transaction.
4. Nếu listener tự gọi một service `@Transactional`, service đó có thể bắt đầu **transaction riêng** theo propagation của nó; đây không phải transaction gốc của publisher.
5. Việc đọc row publisher vừa ghi nhưng chưa commit có thể không thấy dữ liệu, tùy isolation/DB. Nếu publisher rollback sau đó, listener vẫn có thể đã chạy và tạo side effect bên ngoài.
6. Exception ở tác vụ bất đồng bộ không tự truyền ngược để rollback transaction đã xử lý trên thread publisher.

**Không nên** cố chuyển một JDBC transaction đang mở sang thread khác bằng cách sao chép `ThreadLocal`. Transaction gắn với resource/connection và lifecycle cụ thể. Context propagation cho tracing, MDC hay security không đồng nghĩa với việc chuyển một transaction hợp lệ.

`@Async` đặt trên một `@EventListener` cũng có thể khiến thân listener thực thi bất đồng bộ khi `@EnableAsync` và proxy/executor đã được cấu hình. Cần đánh giá cả **executor của multicaster** lẫn **`@Async` trên phương thức**; chỉ kiểm tra một trong hai có thể bỏ sót việc đổi thread.

## 4. Ngoại lệ quan trọng: `@TransactionalEventListener`

`@TransactionalEventListener` được thiết kế để đăng ký callback với vòng đời transaction tại thời điểm event được phát. Mặc định, listener được gọi ở pha `AFTER_COMMIT`, tức là sau khi transaction commit thành công; nếu rollback thì callback `AFTER_COMMIT` không chạy.

Trong Spring Framework 6.1+, `TransactionalApplicationListener` (kể cả adapter cho `@TransactionalEventListener`) khai báo **không hỗ trợ dispatch bất đồng bộ ở tầng multicaster** thông qua `supportsAsyncExecution()`. Do đó, với `SimpleApplicationEventMulticaster.setTaskExecutor(...)`:

- Listener `@EventListener` thông thường có thể được executor chạy trên thread khác.
- Adapter `@TransactionalEventListener` vẫn được multicaster **gọi ở thread phát event để đăng ký transaction synchronization**. Phần xử lý do annotation khai báo sẽ được gọi đúng pha transaction tương ứng sau đó.
- Không vì cấu hình executor cho multicaster mà mặc nhiên kết luận transactional listener bị mất transaction registration hoặc bị chạy ngay trên worker thread.

**Phân biệt:** việc adapter đăng ký đồng bộ không có nghĩa là *thân phương thức* luôn chạy đồng bộ nếu bạn chủ động thêm `@Async` vào phương thức `@TransactionalEventListener`. Khi đó callback của pha giao dịch có thể kích hoạt tác vụ bất đồng bộ và phần xử lý thực tế chạy ở thread khác, sau thời điểm pha đã xảy ra. Cần quản lý giao dịch riêng cho những thao tác DB thực hiện trên thread đó.

### Các pha transaction

| Pha của `@TransactionalEventListener` | Thời điểm | Ý nghĩa thực tế |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit, transaction còn có thể rollback | Phù hợp cho kiểm tra/chuẩn bị công việc cần gắn với commit, nhưng vẫn phải xử lý khả năng commit thất bại sau đó |
| `AFTER_COMMIT` *(mặc định)* | Sau khi commit thành công | Phù hợp để kích hoạt hành động chỉ nên xảy ra sau khi dữ liệu DB đã commit |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Dùng cho logging, bù trừ hoặc dọn dẹp thích hợp |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, dù commit hay rollback | Dùng cho hành vi cần biết một transaction đã hoàn tất |

Ví dụ:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(InvoiceCreated event) {
    notificationService.enqueueNotification(event.id());
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void afterRollback(InvoiceCreated event) {
    auditLogger.noteCanceledInvoice(event.id());
}
```

Đây là **đoạn minh họa**, cần các service tương ứng. Cấu hình phase thuộc về transactional listener; `@Order` hoặc thứ tự gọi của multicaster không thể biến một callback `AFTER_COMMIT` thành xử lý *trước commit*.

Nếu event được phát mà **không có transaction đang hoạt động**, `@TransactionalEventListener` mặc định **không chạy** vì không có pha transaction để gắn vào. Có thể chỉ định `fallbackExecution = true` nếu muốn listener vẫn xử lý trong trường hợp không có transaction:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void handle(InvoiceCreated event) {
    // Có transaction: chạy theo phase; không có: được phép chạy fallback.
}
```

Không nên bật fallback chỉ để "sửa" một sự kiện bị mất transaction do cấu hình bất đồng bộ sai: lúc đó ý nghĩa "chỉ xử lý sau commit" không còn được đảm bảo cho nhánh fallback.

### Lưu ý rất dễ sai khi ghi DB ở `AFTER_COMMIT`

Ở pha `AFTER_COMMIT`/`AFTER_ROLLBACK`/`AFTER_COMPLETION`, transaction đã hoàn thành nhưng resource (connection, session) đôi lúc vẫn còn được ràng buộc trong giai đoạn callback. Tài liệu Spring cảnh báo rằng lời gọi truy cập dữ liệu tại thời điểm này **có thể vẫn tham gia resource của transaction cũ mà thay đổi mới không được commit**.

Nếu cần ghi thêm một bản ghi DB sau commit, nên mở transaction mới thực sự, thường bằng `PROPAGATION_REQUIRES_NEW` trên phương thức public của **một Spring bean khác**, được gọi qua proxy:

```java
@Service
public class DeliveryAuditService {
    private final JdbcTemplate jdbc;

    public DeliveryAuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordDeliveryRequest(long invoiceId) {
        jdbc.update(
            "INSERT INTO delivery_audit (invoice_id) VALUES (?)",
            invoiceId
        );
    }
}
```

Listener `AFTER_COMMIT` có thể gọi `deliveryAuditService.recordDeliveryRequest(event.id())`. Ví dụ giả định đã có bảng `delivery_audit` và các import phù hợp. Gọi nội bộ `this.recordDeliveryRequest(...)` trong cùng bean thường không đi qua transaction proxy nên không có bảo đảm mở transaction mới. Transaction riêng sau commit **không làm các thao tác ngoài DB trở thành atomic với transaction gốc**.

## 5. Ví dụ chạy được: cùng một event, hai multicaster, khác bối cảnh transaction

Ví dụ sau chạy bằng Java 17+, Spring Framework 6.2.x và H2 in-memory. Nó sử dụng `TransactionTemplate` để nhìn rõ hai giao dịch: hóa đơn 1 được commit, hóa đơn 2 bị rollback. Với cùng một mã listener, chạy chế độ đồng bộ và chế độ executor bất đồng bộ sẽ cho thấy bối cảnh giao dịch của `@EventListener` khác nhau, trong khi `@TransactionalEventListener` vẫn quan sát đúng pha.

Cấu trúc thư mục:

```text
multicaster-transaction-demo/
├── pom.xml
└── src/main/java/MulticasterTransactionDemo.java
```

### `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>multicaster-transaction-demo</artifactId>
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
                <configuration>
                    <mainClass>MulticasterTransactionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/java/MulticasterTransactionDemo.java`

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;

import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class MulticasterTransactionDemo {

    public record InvoiceCreated(int id) {}

    @Configuration
    public static class DbConfig {

        @Bean
        public DataSource dataSource() {
            var ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:events;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }
    }

    public static class Handlers {
        private final Queue<String> lines;
        private final CountDownLatch done;

        public Handlers(Queue<String> lines, CountDownLatch done) {
            this.lines = lines;
            this.done = done;
        }

        @EventListener
        public void ordinary(InvoiceCreated event) {
            boolean active =
                    TransactionSynchronizationManager.isActualTransactionActive();
            lines.add("PLAIN " + event.id() + " txActive=" + active);
            done.countDown();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void onCommit(InvoiceCreated event) {
            lines.add("AFTER_COMMIT " + event.id());
            done.countDown();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void onRollback(InvoiceCreated event) {
            lines.add("AFTER_ROLLBACK " + event.id());
            done.countDown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        boolean async = args.length > 0 && args[0].equals("async");
        Queue<String> lines = new ConcurrentLinkedQueue<>();
        CountDownLatch done = new CountDownLatch(4);
        ExecutorService executor =
                async ? Executors.newSingleThreadExecutor() : null;

        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(DbConfig.class);
            context.registerBean(
                    Handlers.class,
                    () -> new Handlers(lines, done)
            );

            if (async) {
                context.registerBean(
                        "applicationEventMulticaster",
                        ApplicationEventMulticaster.class,
                        () -> {
                            var multicaster =
                                    new SimpleApplicationEventMulticaster();
                            multicaster.setTaskExecutor(executor);
                            return multicaster;
                        }
                );
            }

            context.refresh();

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("CREATE TABLE invoices (id INT PRIMARY KEY)");

            TransactionTemplate tx = new TransactionTemplate(
                    context.getBean(PlatformTransactionManager.class)
            );

            // Transaction thứ nhất: commit.
            tx.executeWithoutResult(status -> {
                jdbc.update("INSERT INTO invoices (id) VALUES (?)", 1);
                context.publishEvent(new InvoiceCreated(1));
            });

            // Transaction thứ hai: rollback chủ động.
            tx.executeWithoutResult(status -> {
                jdbc.update("INSERT INTO invoices (id) VALUES (?)", 2);
                context.publishEvent(new InvoiceCreated(2));
                status.setRollbackOnly();
            });

            if (!done.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Missing listener callbacks");
            }

            var output = new ArrayList<>(lines);
            Collections.sort(output); // Ổn định stdout, không giả định thời gian chạy.
            output.forEach(System.out::println);
            System.out.println(
                    "Persisted IDs: " +
                    jdbc.queryForList(
                            "SELECT id FROM invoices ORDER BY id",
                            Integer.class
                    )
            );
        } finally {
            if (executor != null) {
                executor.shutdown();
            }
        }
    }
}
```

Hai transactional listener chỉ đếm khi pha tương ứng thật sự xảy ra: `AFTER_COMMIT` nhận hóa đơn 1, còn `AFTER_ROLLBACK` nhận hóa đơn 2. Hai lời gọi `@EventListener` thông thường luôn được dispatch, bất kể giao dịch về sau commit hay rollback. `CountDownLatch` giúp chờ listener bất đồng bộ và `Collections.sort` giúp hiển thị kết quả theo thứ tự cố định; **thứ tự dòng stdout không đại diện cho thứ tự chạy thực tế**.

### Chạy theo chế độ đồng bộ mặc định

```bash
mvn -q compile exec:java
```

Kết quả từ các dòng `System.out.println` của chương trình:

```text
AFTER_COMMIT 1
AFTER_ROLLBACK 2
PLAIN 1 txActive=true
PLAIN 2 txActive=true
Persisted IDs: [1]
```

`@EventListener` được chạy trên thread phát event, khi transaction còn hoạt động nên `txActive=true`. Dù listener `PLAIN 2` được gọi, dòng database có `id=2` đã rollback. Listener `AFTER_COMMIT` không xử lý hóa đơn 2.

### Chạy với multicaster dùng executor

```bash
mvn -q compile exec:java -Dexec.args=async
```

Kết quả từ các dòng `System.out.println` của chương trình:

```text
AFTER_COMMIT 1
AFTER_ROLLBACK 2
PLAIN 1 txActive=false
PLAIN 2 txActive=false
Persisted IDs: [1]
```

`@EventListener` thông thường đã chuyển sang thread của executor và không còn thấy transaction của thread gọi `publishEvent`. Trong khi đó, transactional listener vẫn được đăng ký trên thread gốc và nhận callback theo commit/rollback. Dù listener bất đồng bộ in dòng `PLAIN 1` ở cuối danh sách đã sắp xếp, đừng suy ra rằng nó **được thực thi** sau commit: code đã cố ý sắp xếp chuỗi log để so sánh.

Nếu thay phần ghi log trong `ordinary(...)` bằng truy vấn DB, thời điểm truy vấn có thể nằm trước hoặc sau commit, nên kết quả truy vấn dưới async mode có thể khác với synchronous mode. Đây chính là nguy cơ khi biến một listener phụ thuộc trạng thái transaction thành tác vụ bất đồng bộ.

## 6. Bảng so sánh để chọn cấu hình phù hợp

| Cơ chế | Thread/lúc xử lý thông thường | Có dùng transaction gốc của publisher không? | Nếu publisher rollback |
| --- | --- | --- | --- |
| `@EventListener` + multicaster mặc định đồng bộ | Ngay khi `publishEvent` gọi listener, cùng thread | Có thể dùng cùng transaction thread-bound đang hoạt động | Listener đã chạy; các ghi DB cùng transaction sẽ rollback, nhưng side effect ngoài DB có thể đã xảy ra |
| `@EventListener` + multicaster executor | Thread executor, thời điểm không cố định so với commit | **Không** tự kế thừa transaction của publisher | Listener vẫn có thể chạy và tạo tác dụng ngoài transaction gốc |
| `@TransactionalEventListener(AFTER_COMMIT)` | Callback sau commit thành công | Không còn một transaction đang hoạt động để ghi tiếp như trước commit; resource cũ có thể còn tạm thời | Không chạy callback `AFTER_COMMIT` khi rollback |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Callback sau rollback | Transaction đã kết thúc | Chạy callback `AFTER_ROLLBACK` |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Callback trước commit khi transaction còn đang kết thúc | Còn ở ngữ cảnh transaction trước khi commit | Không bảo đảm callback này đã chạy nếu transaction rollback trước khi tới giai đoạn commit |

Cần tránh diễn giải bảng thành một bảo đảm giao hàng: `@TransactionalEventListener(AFTER_COMMIT)` xử lý callback **sau commit**, nhưng chưa phải hàng đợi bền vững. Process có thể chết giữa lúc database commit và lúc gửi message/email. Nếu cần chắc chắn chuyển sự kiện tới hệ thống khác, một lựa chọn là **transactional outbox**: ghi event vào bảng outbox trong cùng transaction với dữ liệu nghiệp vụ, rồi có worker riêng đọc, gửi và retry với khóa idempotency.

## 7. Thứ tự xử lý, lỗi và tính nhất quán

- **`@Order` không định nghĩa thời điểm commit.** Nó chỉ điều chỉnh độ ưu tiên gọi các listener phù hợp. Khi có executor, thứ tự dispatch không bảo đảm thứ tự hoàn tất. Với transactional listener, pha `BEFORE_COMMIT`/`AFTER_COMMIT` vẫn quyết định thời điểm callback.
- **Không trộn lẫn "đã gọi listener" và "đã ghi DB thành công".** Listener thông thường có thể được gọi trước rollback. Một hệ thống nhận notification có thể chứng kiến "đã tạo hóa đơn" trong khi DB không có hóa đơn đó.
- **Không coi event multicaster là event broker bền vững.** Cơ chế in-process của Spring không tự bảo đảm replay, retry, exactly-once hoặc transaction phân tán.
- **Cấu hình `ErrorHandler` làm thay đổi cách lan truyền lỗi.** Nếu handler xử lý hoặc nuốt exception, publisher có thể không biết listener thất bại. Với executor, exception thuộc tác vụ chạy trên worker thread.
- **Đừng dựa vào transaction context trên thread khác.** Với JDBC/JPA, event bất đồng bộ nên mang dữ liệu đã ổn định hoặc khóa định danh để listener đọc lại trong transaction riêng sau commit.
- **Chú ý phản hồi HTTP.** Với multicaster async, API có thể trả thành công sau khi DB commit mà tác vụ event vẫn đang chạy; phải có chiến lược ghi nhận lỗi và retry nếu side effect là bắt buộc.
- **Đừng dựa vào `@Transactional` khi gọi cùng một bean bằng `this.method()`.** Proxy-based transaction thường không áp dụng cho self-invocation; cần gọi qua bean/proxy thích hợp.
- **Đừng đặt kỳ vọng rollback DB vào callback `AFTER_COMMIT`.** Tới thời điểm đó transaction đã commit; callback thất bại không tự hoàn tác giao dịch đã hoàn thành.

### Nếu ứng dụng dùng reactive transaction

Từ Spring 6.1, `@TransactionalEventListener` hỗ trợ cả transaction quản lý bởi `ReactiveTransactionManager`. Tuy nhiên transaction reactive gắn với **Reactor Context**, không dùng quy tắc `ThreadLocal` kiểu JDBC/JPA. Khi phát event trong reactive transaction, cần truyền transaction context đúng cách (ví dụ qua `TransactionalEventPublisher` và đưa context vào nguồn event) để listener được gắn với pha transaction. Không thể lấy các kết luận về `isActualTransactionActive()` hoặc thread của JDBC rồi áp dụng nguyên xi cho reactive pipeline.

## 8. Cách kiểm thử trước khi đổi multicaster trong dự án

Với một event phát trong giao dịch nghiệp vụ thật, nên kiểm tra các trường hợp sau:

1. **Commit thành công:** `@EventListener` nhận event; `@TransactionalEventListener(AFTER_COMMIT)` chạy đúng sau commit; dữ liệu DB đã được ghi.
2. **Rollback:** `@EventListener` có thể đã chạy; `AFTER_COMMIT` không chạy; `AFTER_ROLLBACK` chạy; dữ liệu DB do publisher ghi bị rollback.
3. **Không có transaction:** `@TransactionalEventListener` mặc định không chạy; chỉ cho chạy fallback nếu có chủ ý rõ ràng.
4. **Có executor:** kiểm tra listener thông thường không dựa vào transaction của publisher; kiểm tra transactional listener vẫn nhận đúng callback; dùng `CountDownLatch`/barrier thay vì `Thread.sleep` để kiểm soát bất đồng bộ.
5. **Listener lỗi:** xác minh cách exception ảnh hưởng tới rollback, phản hồi API, log và cơ chế retry; thử cả đồng bộ và async.
6. **Tác vụ cần ghi DB sau commit:** dùng một service mở transaction mới, kiểm tra bản ghi thực sự persisted; với message gửi ra ngoài, kiểm tra tính idempotent và kịch bản retry/crash.

## 9. Ghi nhớ khi thiết kế

Một chuỗi nghiệp vụ cần **cùng transaction và rollback cùng nhau** thường nên được điều phối rõ ràng trong cùng service/transaction, hoặc dùng listener đồng bộ khi sự phụ thuộc là có chủ đích và được kiểm thử. Một hành động chỉ được thực hiện **sau khi DB commit thành công** phù hợp với `@TransactionalEventListener(AFTER_COMMIT)`. Một tác vụ **bất đồng bộ cần chắc chắn được giao và retry** nên có cơ chế lưu trữ bền vững như outbox, thay vì chỉ dựa vào executor của multicaster.

Điểm kiểm tra đầu tiên khi thấy listener "không nhìn thấy dữ liệu", "không rollback cùng publisher" hoặc "chạy dù giao dịch thất bại" là: multicaster hiện tại có `TaskExecutor` không, listener thuộc `@EventListener` hay `@TransactionalEventListener`, có `@Async` không, và transaction gốc đang ở phase nào khi event được phát?

## Tài liệu tham khảo

- [Spring Reference – Application events và SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Reference – Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Javadoc – SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Javadoc – TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Javadoc – TransactionalApplicationListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html)
