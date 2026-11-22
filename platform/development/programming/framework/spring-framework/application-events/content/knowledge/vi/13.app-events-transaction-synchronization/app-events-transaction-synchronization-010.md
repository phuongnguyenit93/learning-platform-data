# Tính idempotent của listener hậu commit trong Spring Framework Application Events

## 1. Bài toán: đã commit rồi, vì sao vẫn phải chống xử lý trùng?

Một hệ thống thanh toán cập nhật đơn hàng sang trạng thái `PAID` trong transaction, phát sự kiện `PaymentCaptured`, rồi có listener gửi yêu cầu phát hành hóa đơn hoặc thông báo cho khách. Listener được gắn `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` để chỉ xử lý khi transaction nguồn đã commit thành công.

Nhưng điều kiện **“chạy sau commit” không đồng nghĩa với “mỗi sự kiện chỉ chạy đúng một lần”**. Các tình huống thực tế:

- Cùng một sự kiện có thể bị `publishEvent(...)` hai lần do lỗi logic hoặc do một luồng nghiệp vụ được gọi lặp.
- Worker đọc lại một bản ghi outbox chưa được đánh dấu hoàn thành sau khi tiến trình khởi động lại.
- Một hệ thống bên ngoài đã xử lý yêu cầu nhưng client timeout, khiến ứng dụng không biết kết quả và phải retry.
- Nhiều instance ứng dụng hoặc nhiều worker cùng xử lý một định danh sự kiện.
- Người dùng gửi lại cùng một yêu cầu thanh toán, khiến các thành phần khác nhau tạo hoặc nhận trùng thông tin.

**Idempotent** nghĩa là thực hiện cùng một thao tác nhiều lần với **cùng định danh nghiệp vụ hợp lệ** vẫn dẫn đến **hiệu ứng quan sát được tương đương một lần**. Trong listener hậu commit, mục tiêu thường là không tạo trùng hóa đơn, bản ghi outbox, quyền lợi hay yêu cầu gửi thông báo cho **cùng một sự kiện/ý định nghiệp vụ**.

Cần phân biệt:

- **At-most-once**: có thể mất tác vụ, nhưng không chạy lại.
- **At-least-once**: cho phép retry để giảm mất tác vụ, vì vậy có thể nhận trùng.
- **Idempotent effect**: nhận trùng nhưng các tác dụng phụ được bảo vệ để không sinh kết quả trùng.
- **Exactly-once end-to-end**: yêu cầu mạnh hơn, đặc biệt khó với HTTP/email và các hệ thống khác nhau; chỉ gắn `@TransactionalEventListener` không cung cấp bảo đảm này.

## 2. `AFTER_COMMIT` thực sự bảo đảm điều gì?

`@TransactionalEventListener` là listener ràng buộc với **pha của transaction phát sự kiện**:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onPaymentCaptured(PaymentCaptured event) {
    // Xử lý khi transaction đã commit thành công.
}
```

Các pha:

| Pha | Khi nào callback được thực hiện? | Có phù hợp để phát tác dụng phụ hậu commit? |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit, có khả năng transaction sau đó không commit | Không phải hậu commit |
| `AFTER_COMMIT` | Sau khi transaction commit thành công; đây là pha mặc định | Phù hợp để bắt đầu xử lý sau commit |
| `AFTER_ROLLBACK` | Sau rollback | Phù hợp cho phản ứng với thất bại |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất bất kể kết quả | Dành cho công việc quan sát/dọn dẹp chung |

Theo mặc định, khi phát event **không có transaction đang hoạt động**, `@TransactionalEventListener` **không thực thi**, vì `fallbackExecution` mặc định là `false`. Nếu bật `fallbackExecution = true`, event phát ngoài transaction cũng có thể được xử lý; điều này thay đổi ngữ nghĩa mong đợi của một listener “chỉ sau commit”, nên cần quyết định có chủ đích.

`AFTER_COMMIT` bảo vệ **thời điểm**: không xử lý sự kiện cho transaction đã rollback. Nó **không** tự khử trùng, retry, persist event, đồng bộ giữa nhiều instance hay kiểm soát độ tin cậy của dịch vụ ngoài.

### Cạm bẫy khi ghi database từ listener hậu commit

Sau khi commit, một số tài nguyên transaction cũ vẫn có thể còn được gắn với luồng trong lúc callback chạy. Theo tài liệu `TransactionSynchronization`, truy cập dữ liệu lúc này có thể còn tham gia vào ngữ cảnh cũ **mà không có một lần commit tiếp theo**. Vì vậy, nếu listener cần ghi bảng `processed_events` hay `outbox`, phải chủ động tạo **transaction mới** (thường dùng `PROPAGATION_REQUIRES_NEW`).

Không nên đặt một lệnh `repository.save(...)` tùy ý trong callback rồi mặc nhiên cho rằng dữ liệu vừa ghi sẽ được commit. Cũng không nên dùng `@Transactional(REQUIRES_NEW)` trên một method gọi bằng `this.method()` cùng bean và kỳ vọng proxy Spring sẽ can thiệp; self-invocation có thể bỏ qua transaction advice.

## 3. Thiết kế khóa idempotency đúng phạm vi

Một sự kiện nên có định danh ổn định, được gán khi nghiệp vụ tạo sự kiện. Ví dụ:

```java
public record PaymentCaptured(
        String eventId,
        String paymentId,
        String orderId,
        long amountInCents
) {}
```

- `eventId` định danh **cùng một lần phát sinh nghiệp vụ** và được giữ **nguyên** qua retry/replay. Không sinh UUID mới ở mỗi lần xử lý lại cùng event.
- `paymentId` liên hệ giao dịch thanh toán cụ thể.
- `orderId` giúp liên hệ đối tượng nghiệp vụ.
- `amountInCents` là snapshot dữ liệu quan trọng; dùng số nguyên để tránh sai số tiền tệ từ `double`.

Nếu một event được tiêu thụ bởi nhiều thành phần, khóa `eventId` đơn lẻ có thể quá rộng. Ví dụ, cả `invoice-service` và `email-service` đều được phép xử lý một event. Khóa idempotency thường là:

```text
(consumer_name, event_id)
```

Hoặc, khi nghiệp vụ thực sự là “mỗi đơn chỉ có một hóa đơn”, có thể dùng `(invoice_type, order_id)` để bảo vệ bất biến đó. **Khóa sự kiện** và **khóa bất biến nghiệp vụ** giải quyết hai vấn đề liên quan nhưng khác nhau; hệ thống quan trọng thường cần cả hai.

Ví dụ thiết kế bảng:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Unique constraint/primary key ở database là nguồn bảo vệ **khi xử lý đồng thời**. Một `HashSet` hoặc `ConcurrentHashMap` trong RAM có thể hữu ích cho thử nghiệm nhưng **không bảo đảm chống trùng** qua restart, qua nhiều instance hay khi xảy ra race giữa kiểm tra và ghi.

### Vì sao “check rồi insert” chưa đủ?

```text
Worker A                         Worker B
--------                         --------
SELECT: chưa có event           SELECT: chưa có event
gửi thông báo                    gửi thông báo
INSERT marker                    INSERT marker
```

Cả A và B đều có thể thấy “chưa có” trước khi một bên ghi. Việc `SELECT` trước không biến thao tác thành nguyên tử. Phải để database quyết định duy nhất qua **ràng buộc unique**, và đặt thao tác ghi marker cùng với tác dụng phụ **có thể giao dịch chung** trong một transaction.

## 4. Mẫu an toàn: ghi marker và outbox cùng transaction mới

Với công việc liên quan cơ sở dữ liệu, giải pháp phổ biến:

1. Transaction nghiệp vụ cập nhật trạng thái và commit.
2. Listener `AFTER_COMMIT` nhận event.
3. Listener mở transaction **mới**.
4. Thử `INSERT` khóa `(consumer_name, event_id)` vào `processed_events`.
5. Nếu insert thành công, trong **cùng transaction mới** ghi một bản ghi `notification_outbox` hoặc một hiệu ứng database khác.
6. Commit transaction mới. Nếu khóa đã tồn tại, coi đây là delivery trùng và bỏ qua theo chính sách đã định.
7. Worker riêng gửi outbox đến hệ thống ngoài với retry và idempotency phù hợp.

Điều kiện quan trọng là **marker và outbox cùng commit hoặc cùng rollback**. Nếu chỉ ghi marker trước rồi gọi email bên ngoài, ứng dụng có thể chết sau marker nhưng trước email: lần retry sẽ bị chặn và email bị mất. Nếu gửi email trước marker, ứng dụng có thể chết sau email nhưng trước marker: lần retry gửi trùng. Với email/HTTP không cùng database transaction, chỉ một marker nội bộ **không bảo đảm đúng một lần end-to-end**.

```text
Transaction nghiệp vụ                 Transaction mới sau commit
---------------------                --------------------------
Cập nhật Order = PAID
publishEvent(PaymentCaptured)
COMMIT -------------------------------> INSERT processed_events
                                         INSERT notification_outbox
                                         COMMIT
                                               |
                                               v
                                         Worker gửi bên ngoài
                                         (retry + idempotency)
```

## 5. Ví dụ hoàn chỉnh: Java 17, Spring Framework, JDBC, H2

Ví dụ dưới đây **chạy trong một `ApplicationContext` thuần**, dùng Spring Framework 6.2.0, Maven và H2 in-memory. Ta cố ý phát **hai event cùng `eventId`** trong **một transaction đã commit**, rồi phát một event khác trong transaction **bị rollback**.

Listener hậu commit chạy hai lần cho event trùng, nhưng chỉ ghi **một marker** và **một outbox row** nhờ primary key và transaction mới. Event của transaction rollback không có tác dụng hậu commit.

**Cấu trúc:**

```text
idempotent-after-commit/
├── pom.xml
└── src/main/java/example/IdempotentAfterCommitDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>idempotent-after-commit</artifactId>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.IdempotentAfterCommitDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/example/IdempotentAfterCommitDemo.java`:**

```java
package example;

import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class IdempotentAfterCommitDemo {

    public record PaymentCaptured(String eventId, String orderId) {}

    public static class ReceiptListener {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate isolatedTx;
        private final AtomicInteger callbacks = new AtomicInteger();
        private final AtomicInteger created = new AtomicInteger();
        private final AtomicInteger duplicates = new AtomicInteger();

        public ReceiptListener(JdbcTemplate jdbc,
                               PlatformTransactionManager manager) {
            this.jdbc = jdbc;
            this.isolatedTx = new TransactionTemplate(manager);
            this.isolatedTx.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void onCaptured(PaymentCaptured event) {
            callbacks.incrementAndGet();

            try {
                isolatedTx.executeWithoutResult(status -> {
                    // Atomic claim: unique theo consumer + event.
                    jdbc.update(
                        "INSERT INTO processed_events " +
                        "(consumer_name, event_id) VALUES (?, ?)",
                        "receipt", event.eventId());

                    // Cùng transaction: lưu yêu cầu gửi bền vững.
                    jdbc.update(
                        "INSERT INTO notification_outbox " +
                        "(consumer_name, event_id, order_id) " +
                        "VALUES (?, ?, ?)",
                        "receipt", event.eventId(), event.orderId());
                });
                created.incrementAndGet();
            } catch (DuplicateKeyException duplicate) {
                // Trong ví dụ, duplicate là trùng khóa idempotency.
                // Thực tế cần phân loại chính xác constraint bị vi phạm.
                duplicates.incrementAndGet();
            }
        }

        public int callbacks() { return callbacks.get(); }
        public int created() { return created.get(); }
        public int duplicates() { return duplicates.get(); }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:idem_demo;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        public ReceiptListener receiptListener(
                JdbcTemplate jdbc, PlatformTransactionManager manager) {
            return new ReceiptListener(jdbc, manager);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate tx =
                    context.getBean(TransactionTemplate.class);
            ReceiptListener listener =
                    context.getBean(ReceiptListener.class);

            jdbc.execute(
                "CREATE TABLE business_orders (" +
                "order_id VARCHAR(80) PRIMARY KEY, " +
                "status VARCHAR(30) NOT NULL)");
            jdbc.execute(
                "CREATE TABLE processed_events (" +
                "consumer_name VARCHAR(80) NOT NULL, " +
                "event_id VARCHAR(80) NOT NULL, " +
                "PRIMARY KEY (consumer_name, event_id))");
            jdbc.execute(
                "CREATE TABLE notification_outbox (" +
                "consumer_name VARCHAR(80) NOT NULL, " +
                "event_id VARCHAR(80) NOT NULL, " +
                "order_id VARCHAR(80) NOT NULL, " +
                "PRIMARY KEY (consumer_name, event_id))");

            // Transaction 1: commit nhưng publish cùng event hai lần.
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO business_orders " +
                    "(order_id, status) VALUES (?, ?)",
                    "ORD-1", "PAID");
                context.publishEvent(
                    new PaymentCaptured("evt-001", "ORD-1"));
                context.publishEvent(
                    new PaymentCaptured("evt-001", "ORD-1"));
            });

            // Transaction 2: rollback; AFTER_COMMIT không chạy.
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO business_orders " +
                    "(order_id, status) VALUES (?, ?)",
                    "ORD-2", "PAID");
                context.publishEvent(
                    new PaymentCaptured("evt-002", "ORD-2"));
                status.setRollbackOnly();
            });

            Integer one = jdbc.queryForObject(
                "SELECT COUNT(*) FROM notification_outbox " +
                "WHERE event_id = ?", Integer.class, "evt-001");
            Integer rolledBack = jdbc.queryForObject(
                "SELECT COUNT(*) FROM notification_outbox " +
                "WHERE event_id = ?", Integer.class, "evt-002");

            System.out.println(
                "AFTER_COMMIT callbacks: " + listener.callbacks());
            System.out.println(
                "Tác vụ outbox được tạo: " + listener.created());
            System.out.println(
                "Sự kiện trùng được bỏ qua: " + listener.duplicates());
            System.out.println(
                "Outbox cho evt-001: " + one);
            System.out.println(
                "Outbox cho evt-002: " + rolledBack);
        }
    }
}
```

**Chạy** từ thư mục chứa `pom.xml` bằng JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

**Năm dòng do ứng dụng in** (không tính log Maven/Spring nếu có):

```text
AFTER_COMMIT callbacks: 2
Tác vụ outbox được tạo: 1
Sự kiện trùng được bỏ qua: 1
Outbox cho evt-001: 1
Outbox cho evt-002: 0
```

**Giải thích kết quả:**

- Hai lần `publishEvent` cùng `evt-001` đều đăng ký callback hậu commit. Khi transaction 1 commit, listener được gọi **hai lần**.
- Lần đầu, `INSERT processed_events` thành công và `INSERT notification_outbox` ghi một yêu cầu xử lý. Cả hai dòng commit trong transaction `REQUIRES_NEW`.
- Lần thứ hai, primary key `(consumer_name, event_id)` chặn bản ghi marker trùng. Transaction mới này rollback, không thêm outbox thứ hai; `DuplicateKeyException` được bắt ở ngoài `TransactionTemplate`.
- Sự kiện `evt-002` được publish trong transaction 2 nhưng transaction đã rollback, nên callback `AFTER_COMMIT` không chạy; không có outbox cho `evt-002`.
- Ví dụ chạy đồng bộ tại callback hậu commit nên không cần `sleep`. Nó chứng minh **idempotency của thao tác ghi outbox trong database**, chưa gửi email thật và **không** chứng minh exactly-once khi có dịch vụ ngoài.

**Lưu ý về xử lý lỗi:** Trong code minh họa, cả hai bảng chỉ có unique key tương ứng nên `DuplicateKeyException` thể hiện trường hợp trùng khóa. Với schema production, phải xác định **đúng constraint** bị vi phạm. Nếu lỗi duplicate là do bất biến khác hoặc có dữ liệu mâu thuẫn, không được lặng lẽ coi như “đã xử lý”.

Phiên bản dependency được ghim để ví dụ có thể tái lập. Khi áp dụng thực tế, nên dùng các bản vá Spring/H2 đang được duy trì, cùng BOM/chiến lược quản lý phiên bản của dự án.

## 6. Vì sao `REQUIRES_NEW` quan trọng?

Hãy xét đoạn dễ viết nhưng thiếu bảo đảm:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onPaid(PaymentCaptured event) {
    repository.save(new ProcessedEvent(event.eventId()));
}
```

Đây chỉ là đoạn tích hợp minh họa (thiếu repository/entity). Vì callback chạy sau commit, tài nguyên transaction cũ có thể vẫn còn ràng buộc với luồng, và không có commit kế tiếp cho những thay đổi tham gia ngữ cảnh đó. **Không nên trông đợi `save` trên callback đồng nghĩa dữ liệu được persist thành công.**

Cách thông dụng là ủy quyền cho **service bean khác**:

```java
@Service
public class IdempotencyService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void reserveAndCreateOutbox(PaymentCaptured event) {
        // INSERT marker với unique key;
        // INSERT outbox trong CÙNG transaction mới.
    }
}

@Component
public class PaidListener {
    private final IdempotencyService service;

    public PaidListener(IdempotencyService service) {
        this.service = service;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(PaymentCaptured event) {
        service.reserveAndCreateOutbox(event);
    }
}
```

Đoạn này là mẫu tích hợp, không phải chương trình độc lập: cần entity/repository và import annotation. Gọi qua **bean khác** giúp `@Transactional(REQUIRES_NEW)` được áp dụng qua Spring proxy; gọi `this.reserveAndCreateOutbox(...)` ở cùng bean trong proxy mode thường không kích hoạt advice mong đợi.

Trong ví dụ chạy ở mục 5, `TransactionTemplate` tạo `REQUIRES_NEW` **trực tiếp**, tránh phụ thuộc proxy cho giao dịch mới.

## 7. Idempotency và tính nguyên tử ở ranh giới external API

Database có thể bảo đảm duy nhất một bản ghi marker/outbox, nhưng không thể rollback một email đã rời server hoặc một request HTTP mà đối tác đã xử lý. Phân tích các điểm hỏng:

| Thứ tự thao tác | Điểm crash | Hậu quả nếu chỉ dùng marker |
| --- | --- | --- |
| Ghi `processed_events` rồi gửi email | Sau marker, trước email | Retry bị bỏ qua, **mất email** |
| Gửi email rồi ghi `processed_events` | Sau email, trước marker | Retry có thể **gửi email trùng** |
| Ghi marker và outbox cùng DB transaction | Trong transaction trước commit | Cả hai rollback, có thể retry an toàn bước tạo outbox |
| Worker lấy outbox rồi gửi HTTP/email | Sau khi nhà cung cấp đã nhận nhưng trước khi đánh dấu đã gửi | Worker có thể gửi lại; cần idempotency ở phía nhận hoặc chính sách trùng chấp nhận được |

Mẫu outbox thường có các trạng thái như `PENDING`, `IN_PROGRESS`, `SENT`, `FAILED` và timestamp/lease để reclaim công việc bị treo. Worker nên **claim nguyên tử** (ví dụ cập nhật có điều kiện hoặc row locking phù hợp database), gửi với khóa idempotency được đối tác hỗ trợ và đánh dấu hoàn thành sau khi có kết quả rõ ràng.

Nếu nhà cung cấp hỗ trợ header/khóa idempotency, truyền cùng một khóa ổn định trong mọi lần retry. Nếu nhà cung cấp không hỗ trợ, phải thừa nhận khả năng tác dụng phụ lặp hoặc thiết kế thêm cơ chế kiểm tra trạng thái đối tác. Không được tuyên bố “exactly once” chỉ vì đã tạo một hàng outbox duy nhất.

## 8. Trạng thái xử lý và chiến lược retry

Một số hệ thống cần nhiều hơn bản ghi marker đơn giản vì listener thực hiện công việc kéo dài:

| Trạng thái | Ý nghĩa | Hành động khi nhận lại cùng event |
| --- | --- | --- |
| `NEW` / chưa có marker | Chưa nhận việc | Claim nguyên tử |
| `PROCESSING` | Một worker đang giữ lease | Không chạy song song, hoặc reclaim nếu lease hết hạn |
| `DONE` | Hiệu ứng idempotent đã hoàn tất | Trả kết quả cũ/bỏ qua |
| `FAILED_RETRYABLE` | Lỗi tạm thời | Retry có giới hạn/backoff |
| `FAILED_PERMANENT` | Lỗi không thể tự khôi phục | Ghi nhận để xử lý vận hành |

**Không tự đánh dấu `DONE` quá sớm.** Nếu đánh dấu hoàn tất trước khi tác dụng phụ quan trọng được lưu bền vững, hệ thống có thể mất việc. Ngược lại, nếu tác dụng phụ ở hệ thống khác hoàn tất trước khi `DONE` được commit, phải giả định có retry và bảo vệ phía nhận.

Cần phân biệt lỗi:

- **Duplicate expected:** unique violation đúng khóa idempotency; có thể bỏ qua hoặc trả trạng thái đã xử lý.
- **Transient:** mất kết nối, deadlock, queue đầy; retry có giới hạn và backoff.
- **Business conflict:** cùng `eventId` nhưng nội dung quan trọng khác nhau; không nên coi là trùng hợp lệ, phải phát hiện và báo lỗi.
- **Permanent:** schema không tương thích, dữ liệu bất hợp lệ; dừng retry mù, đưa vào luồng xử lý lỗi.

Đối với event mang số tiền, currency hoặc version, có thể lưu fingerprint của payload cùng marker để phát hiện **cùng khóa nhưng dữ liệu khác**. Hash payload phải có quy tắc canonicalization ổn định; tuyệt đối không dựa vào thứ tự serialization ngẫu nhiên.

## 9. Đặc biệt lưu ý khi dùng `@Async` cùng listener hậu commit

Một listener có thể khai báo:

```java
@Async("billingExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(PaymentCaptured event) {
    // Công việc được chuyển tới executor sau điều kiện phase.
}
```

Đây là đoạn minh họa cần `@EnableAsync`, executor bean và transaction management hoạt động. Việc chạy trên worker có một số hệ quả:

- Context transaction gốc không tự theo `ThreadLocal` sang worker.
- Thứ tự các callback, thời điểm hoàn thành và exception khác với bản đồng bộ.
- Nếu pool từ chối task, việc đã commit transaction nguồn không đồng nghĩa xử lý tiếp thành công.
- Một task đang chờ trong memory executor có thể mất khi process chết.
- **Khóa idempotency trong DB và transaction mới vẫn cần**, vì async không làm event tự nhiên chỉ có một lần.

Không dựa vào `@Order` để bảo đảm thứ tự **hoàn thành** của các công việc async. Nếu B cần kết quả A, diễn tả phụ thuộc trong workflow hoặc job có trạng thái bền vững.

## 10. Kiểm thử tính idempotent đúng cách

Một bài kiểm thử cần phân biệt **số callback** với **số tác dụng phụ**. Ma trận:

| Kịch bản | Callback hậu commit | Hiệu ứng mong đợi |
| --- | --- | --- |
| Publish một event và commit | 1 | 1 marker, 1 outbox row |
| Publish cùng `eventId` hai lần rồi commit | 2 | Vẫn 1 marker và 1 outbox row |
| Publish rồi rollback | 0 | Không có marker/outbox |
| Hai worker xử lý trùng khóa đồng thời | Có thể hơn 1 lần thử | Unique constraint chỉ cho một claim thành công |
| Gửi event khác `eventId` cùng consumer | Thêm callback | Thêm hiệu ứng nếu nghiệp vụ cho phép |
| Cùng event cho consumer `receipt` và `analytics` | Hai loại xử lý độc lập | Mỗi consumer có marker riêng |
| Replay sau khi restart | Có lần xử lý mới | Không tăng số hiệu ứng đã hoàn tất |
| Crash sau commit nghiệp vụ nhưng trước callback | Có thể mất callback | Cần outbox được lưu trong transaction nghiệp vụ nếu không được phép mất event |

Các kiểm tra thực tế nên bao gồm:

1. **Commit/rollback thật:** test với `PlatformTransactionManager` hoặc test tích hợp thích hợp; không chỉ gọi trực tiếp phương thức listener.
2. **Đếm effect trong database:** khẳng định số dòng hoặc trạng thái nghiệp vụ, không chỉ đếm log/callback.
3. **Concurrency:** hai connection/worker cùng cố ghi khóa duy nhất, xác minh chỉ một transaction thành công.
4. **Retry và crash window:** mô phỏng lỗi sau khi tạo outbox, lỗi gửi ngoài, và lỗi trước khi đánh dấu hoàn thành.
5. **Key stability:** retry dùng lại `eventId` ban đầu; cùng khóa nhưng payload khác được phát hiện.
6. **Rollback riêng transaction hậu commit:** nếu ghi outbox lỗi sau khi marker được insert, toàn bộ transaction mới phải rollback để lần retry có thể xử lý tiếp.

### Tránh nhầm với test `@Transactional` mặc định rollback

Một test tự mở transaction rồi rollback lúc kết thúc có thể **không chạy callback `AFTER_COMMIT`**. Vì vậy cần chủ động commit trong test hoặc điều khiển transaction đúng cách. Gọi method annotated trực tiếp chỉ kiểm tra phần thân Java, không chứng minh Spring đã ràng buộc nó với commit phase.

## 11. Những sai lầm phổ biến

1. **Tin rằng `AFTER_COMMIT` đã chống trùng.** Nó chỉ ràng buộc callback với kết quả transaction; mỗi lần publish hợp lệ vẫn có thể tạo callback riêng.
2. **Dùng bộ nhớ local làm nguồn chống trùng duy nhất.** Không đủ cho nhiều instance, restart hoặc race.
3. **Sinh `eventId` mới khi retry.** Hệ thống coi mọi lần retry là event mới, vô hiệu hóa idempotency.
4. **Chọn khóa không đúng phạm vi.** Dùng duy nhất `orderId` có thể vô tình chặn sự kiện thanh toán hợp lệ khác của cùng đơn; dùng duy nhất `eventId` trên toàn bộ consumer có thể chặn subscriber khác.
5. **`SELECT` trước rồi `INSERT` không có unique constraint.** Hai worker đều có thể vượt qua kiểm tra.
6. **Đánh dấu đã xử lý rồi mới gửi email ngoài transaction.** Có cửa sổ mất email khi crash.
7. **Gửi email trước rồi mới đánh dấu đã xử lý.** Có cửa sổ gửi trùng nếu timeout/crash.
8. **Ghi database trong `AFTER_COMMIT` mà không mở transaction mới.** Có nguy cơ tham gia tài nguyên transaction cũ, không được commit thay đổi mới.
9. **Bắt mọi `DuplicateKeyException` rồi bỏ qua.** Có thể che dữ liệu hỏng hoặc unique violation không thuộc khóa idempotency dự kiến.
10. **Nhầm outbox row duy nhất với gửi thành công đúng một lần.** Đối tác bên ngoài vẫn có thể nhận request trùng do retry.
11. **Quên rằng Spring event mặc định nằm trong cùng process.** Crash sau commit nhưng trước callback có thể mất event nếu không lưu outbox ngay trong transaction nghiệp vụ.
12. **Không xem xét `fallbackExecution`.** Bật tùy tiện có thể khiến callback chạy dù không có transaction nào để chứng minh đã commit.

## 12. Checklist thiết kế trước khi đưa vào production

- Event có định danh ổn định qua mọi lần replay/retry.
- Đã chọn khóa idempotency phù hợp với consumer và bất biến nghiệp vụ.
- Marker có ràng buộc unique ở database; không chỉ dựa vào “kiểm tra tồn tại”.
- Marker và thay đổi database liên quan được ghi **trong cùng transaction mới** tại callback hậu commit.
- Đã phân loại duplicate expected và lỗi dữ liệu mâu thuẫn.
- Với external API/email, có outbox/worker và chiến lược retry/idempotency phía nhận.
- Nếu yêu cầu không mất event giữa business commit và callback, outbox phải được tạo **trong transaction nghiệp vụ**, thay vì chỉ đợi callback sau commit.
- Có kiểm thử commit, rollback, duplicate, concurrency, crash và retry.
- Có log/metrics dùng `eventId`, `consumerName`, số lần duplicate và trạng thái cuối.
- Chưa tuyên bố “exactly once end-to-end” nếu còn cửa sổ không kiểm soát ở hệ thống ngoài.

**Ghi nhớ:** `@TransactionalEventListener(AFTER_COMMIT)` giúp listener chỉ xử lý sau commit thành công. **Idempotency** lại đòi hỏi khóa ổn định, unique constraint, thay đổi dữ liệu nguyên tử trong transaction mới, và cơ chế bền vững/retry thích hợp khi có hệ thống bên ngoài. Hai cơ chế bổ sung cho nhau.

## Tài liệu tham khảo

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Javadoc — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
