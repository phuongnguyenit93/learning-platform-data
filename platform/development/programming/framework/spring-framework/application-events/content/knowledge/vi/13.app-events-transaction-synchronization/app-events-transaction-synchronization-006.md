# Đọc lại dữ liệu trong AFTER_COMMIT của Spring Framework

## 1. Vấn đề: đã commit rồi, vì sao đọc dữ liệu vẫn cần cẩn thận?

Khi ứng dụng phát một sự kiện trong phương thức `@Transactional`, đôi khi listener phải **đọc lại dữ liệu đã lưu từ cơ sở dữ liệu, nhưng chỉ sau khi giao dịch gốc commit thành công**. Ví dụ: đơn hàng được chuyển sang trạng thái `CONFIRMED`; sau commit, hệ thống cần đọc bản ghi mới nhất để dựng payload thông báo hoặc cập nhật chỉ mục tìm kiếm.

Spring hỗ trợ tình huống này bằng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. Tuy nhiên, có một chi tiết quan trọng: **giao dịch đã commit, nhưng tài nguyên gắn với giao dịch cũ có thể vẫn đang được Spring giữ trong quá trình gọi callback**. Một lệnh đọc hoặc ghi trực tiếp trong callback có thể sử dụng connection/`EntityManager` vẫn còn được ràng buộc với luồng cũ. Vì vậy:

- `AFTER_COMMIT` xác định **thời điểm listener được kích hoạt**, không tự tạo một giao dịch đọc mới.
- Đọc trực tiếp có thể trả về dữ liệu trong một số hoàn cảnh, nhưng không đồng nghĩa đó luôn là một lượt đọc độc lập, với persistence context mới và ngữ nghĩa nhất quán mong muốn.
- Ghi tiếp vào tài nguyên giao dịch cũ đặc biệt nguy hiểm: **không còn một commit tiếp theo của giao dịch gốc** để lưu các thay đổi đó.
- Khi cần **đọc lại từ database theo ranh giới giao dịch mới**, cách rõ ràng là chuyển thao tác đọc sang một Spring bean khác với `@Transactional(propagation = Propagation.REQUIRES_NEW, readOnly = true)`.

Bài này tập trung vào luồng đọc lại dữ liệu sau commit, thời điểm callback thực thi, persistence context, cách thiết kế giao dịch mới và cách kiểm chứng dữ liệu thực sự đến từ database.

## 2. Diễn tiến của giao dịch và TransactionPhase.AFTER_COMMIT

Giả sử `OrderService.confirmOrder(id)` được gọi qua Spring transaction proxy:

~~~text
Luồng xử lý yêu cầu
   |
   | @Transactional bắt đầu transaction T1
   v
UPDATE orders SET status = 'CONFIRMED' WHERE id = 42
   |
   | publisher.publishEvent(new OrderConfirmed(42))
   | -- @TransactionalEventListener đăng ký xử lý theo pha
   | -- chưa xử lý phần thân AFTER_COMMIT
   v
Method @Transactional kết thúc bình thường
   |
   | Transaction manager tiến hành commit T1
   v
COMMIT thành công
   |
   | Transaction synchronization gọi listener AFTER_COMMIT
   |       |
   |       +--> gọi bean đọc lại với REQUIRES_NEW
   |                |
   |                +--> tạm gác resource của T1
   |                +--> bắt đầu transaction T2 độc lập
   |                +--> SELECT ... WHERE id = 42
   |                +--> hoàn tất T2
   |
   v
Spring dọn dẹp resource/synchronization của T1
   |
   v
Luồng bên ngoài tiếp tục
~~~

Nếu T1 rollback, listener đăng ký với `AFTER_COMMIT` **không được thực thi**. Khi không có giao dịch đang hoạt động lúc sự kiện được phát, `@TransactionalEventListener` mặc định cũng không chạy, trừ khi bật `fallbackExecution = true`.

Các pha thường dùng:

| Pha | Thời điểm | Ý nghĩa đối với đọc lại dữ liệu |
|---|---|---|
| `BEFORE_COMMIT` | Trước thao tác commit của T1 | Chưa thể khẳng định thay đổi đã commit |
| `AFTER_COMMIT` | T1 đã commit thành công | Phù hợp để kích hoạt một lượt đọc độc lập sau commit |
| `AFTER_ROLLBACK` | T1 đã rollback | Dùng cho xử lý khi thất bại; không đọc với kỳ vọng thay đổi của T1 đã lưu |
| `AFTER_COMPLETION` | Kết thúc sau commit hoặc rollback | Cần phân biệt kết quả nếu hành vi phụ thuộc commit thành công |

**Một điểm dễ nhầm:** Trong Spring Framework, `TransactionPhase.AFTER_COMMIT` là trường hợp chuyên biệt của `AFTER_COMPLETION`, được xử lý trong chuỗi callback `TransactionSynchronization.afterCompletion(...)` tương ứng trạng thái commit thành công; nó **không đồng nhất** với callback `TransactionSynchronization.afterCommit()`. Dù tên chứa cùng cụm `AFTER_COMMIT`, không được suy đoán thứ tự chính xác giữa những kiểu callback khác nhau mà không đối chiếu contract và `@Order`.

## 3. Vì sao tài nguyên của transaction cũ có thể vẫn hiện diện?

Spring thường ràng buộc tài nguyên giao dịch với luồng bằng `TransactionSynchronizationManager`. Tùy stack:

- Với JDBC: có thể còn `ConnectionHolder`/connection dùng trong T1 cho đến khi transaction manager hoàn tất dọn dẹp.
- Với JPA/Hibernate: có thể còn `EntityManager`/persistence context gắn vào transaction đã commit.
- Với listener đồng bộ: callback chạy khi Spring đang xử lý transaction completion, **trước khi toàn bộ cleanup đã hoàn tất**.

Javadoc của Spring về `@TransactionalEventListener` lưu ý rằng tại `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`, transaction đã kết thúc nhưng tài nguyên có thể còn khả dụng. Truy cập dữ liệu lúc đó có thể tiếp tục “tham gia” vào resource giao dịch cũ, dù **không có commit tương ứng ở cuối callback**.

### Phân biệt ba điều thường bị gộp làm một

1. **Transaction T1 đã COMMIT:** công việc được ghi thành công theo transaction manager.
2. **Tài nguyên của T1 đã bị gỡ khỏi thread:** đây là bước cleanup riêng, có thể diễn ra sau callback.
3. **Một lượt SELECT dùng connection/EntityManager mới:** đây là ranh giới đọc độc lập mà chương trình phải thiết kế; nó không tự suy ra từ (1).

Ví dụ lỗi thiết kế:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderConfirmed event) {
    Order order = orderRepository.findById(event.orderId())
        .orElseThrow();
    order.setAuditStatus("DONE");
    // Không được mặc định rằng thao tác này sẽ có một commit mới.
}
~~~

Đoạn trên là **minh họa vấn đề**, không phải chương trình chạy độc lập. Một entity còn managed hoặc một phương thức repository tham gia resource cũ có thể khiến thay đổi nhìn thấy trong bộ nhớ nhưng không được commit theo kỳ vọng. Thậm chí một lượt `findById` có thể trả về entity đã có trong first-level cache, làm người đọc tưởng rằng đang lấy lại dữ liệu từ database.

**Không kết luận rằng mọi SELECT trực tiếp ở AFTER_COMMIT đều trả dữ liệu cũ.** Nhiều trường hợp đọc trực tiếp vẫn thấy giá trị mới vừa commit. Vấn đề là thiếu một ranh giới transaction/persistence context mới có thể kiểm chứng, nên hành vi có thể phụ thuộc resource và cách tích hợp cụ thể.

## 4. Cách thực hiện an toàn: tách một dịch vụ đọc với REQUIRES_NEW

Giả sử service phát sự kiện chỉ chuyển một ID:

~~~java
public record OrderConfirmed(long orderId) {}
~~~

Listener nhận sự kiện rồi gọi sang bean chuyên đọc:

~~~java
@Component
public class OrderConfirmedListener {

    private final CommittedOrderReader reader;

    public OrderConfirmedListener(CommittedOrderReader reader) {
        this.reader = reader;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmed event) {
        OrderView view = reader.load(event.orderId());
        // Dùng bản dữ liệu vừa đọc cho bước hậu xử lý.
    }
}
~~~

Bean độc lập mở transaction mới:

~~~java
@Service
public class CommittedOrderReader {

    private final OrderRepository repository;

    public CommittedOrderReader(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW, readOnly = true)
    public OrderView load(long orderId) {
        Order order = repository.findById(orderId).orElseThrow();
        return new OrderView(order.getId(), order.getStatus());
    }
}
~~~

Các đoạn trên là **mẫu kiến trúc tích hợp**: `OrderRepository`, `Order` và `OrderView` phải được định nghĩa theo ứng dụng. `REQUIRES_NEW` khiến Spring tạo một transaction vật lý độc lập (với transaction manager hỗ trợ), tạm gác transaction/resource hiện tại trong phạm vi lời gọi. Với cấu hình JPA thông thường, nó giúp thao tác qua một persistence context của transaction mới; `readOnly = true` thể hiện ý định đọc và có thể cho phép tối ưu hóa, **không phải một cơ chế bảo đảm dữ liệu bất biến**.

Lý do đặt `@Transactional(REQUIRES_NEW)` trên **bean khác**: cơ chế proxy-based của Spring chỉ chặn lời gọi đi qua proxy. Nếu listener tự gọi `this.load(...)` trong cùng instance, annotation có thể không có hiệu lực (*self-invocation*).

### Có thể dùng @Transactional(REQUIRED) hay chỉ @Transactional(readOnly=true) không?

`@Transactional` mặc định dùng `Propagation.REQUIRED`. Trong callback `AFTER_COMMIT`, resource cũ có thể vẫn được xem là tham gia giao dịch; vì vậy chỉ thêm `@Transactional(readOnly = true)` mà không chỉ định propagation **không phải cách rõ ràng để yêu cầu transaction độc lập**. Chọn `REQUIRES_NEW` khi mục tiêu là một lượt đọc riêng sau commit.

### Có thể dùng NOT_SUPPORTED không?

`@Transactional(propagation = Propagation.NOT_SUPPORTED)` tạm ngưng transaction hiện hành, rồi thực hiện logic không thuộc Spring transaction. Với một số dạng đọc JDBC đơn giản, đây có thể là lựa chọn có chủ đích. Nhưng nếu yêu cầu nhất quán của lượt đọc cần một transaction xác định, hoặc cần dùng JPA nhất quán, `REQUIRES_NEW` dễ suy luận và kiểm thử hơn. Không coi `NOT_SUPPORTED` và `REQUIRES_NEW` là tương đương.

## 5. Ví dụ hoàn chỉnh Java 17: commit thấy dữ liệu mới, rollback không kích hoạt listener

Ví dụ dưới đây dùng **Spring Framework 6.2.8**, Spring JDBC và H2 trong bộ nhớ. Nó cho thấy:

1. Một phương thức `@Transactional` cập nhật bản ghi và phát event.
2. `@TransactionalEventListener(AFTER_COMMIT)` chỉ xử lý khi commit thành công.
3. Listener gọi một bean `REQUIRES_NEW` để SELECT sau commit.
4. Khi một transaction khác rollback, listener không chạy và dữ liệu vẫn giữ giá trị cũ.

Cấu trúc:

~~~text
after-commit-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AfterCommitReadDemo.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>after-commit-demo</artifactId>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `src/main/java/demo/AfterCommitReadDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class AfterCommitReadDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE orders (id BIGINT PRIMARY KEY, status VARCHAR(30) NOT NULL)"
            );
            jdbc.update("INSERT INTO orders (id, status) VALUES (?, ?)", 1L, "PENDING");
            jdbc.update("INSERT INTO orders (id, status) VALUES (?, ?)", 2L, "PENDING");

            OrderService service = context.getBean(OrderService.class);
            AuditListener listener = context.getBean(AuditListener.class);

            // Transaction T1 sẽ commit.
            service.confirm(1L);

            System.out.println("order 1 after service: " +
                jdbc.queryForObject(
                    "SELECT status FROM orders WHERE id = ?",
                    String.class, 1L
                )
            );

            // Transaction T2 sẽ rollback do RuntimeException.
            try {
                service.confirmThenFail(2L);
            } catch (IllegalStateException expected) {
                System.out.println("rolled back: " + expected.getMessage());
            }

            System.out.println("order 2 after rollback: " +
                jdbc.queryForObject(
                    "SELECT status FROM orders WHERE id = ?",
                    String.class, 2L
                )
            );
            System.out.println("listener calls: " + listener.handledCount());
        }
    }

    public record OrderConfirmed(long orderId) {}

    @Configuration
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:orders;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
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

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        public CommittedOrderReader committedOrderReader(JdbcTemplate jdbc) {
            return new CommittedOrderReader(jdbc);
        }

        @Bean
        public AuditListener auditListener(CommittedOrderReader reader) {
            return new AuditListener(reader);
        }
    }

    public static class OrderService {

        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void confirm(long orderId) {
            jdbc.update(
                "UPDATE orders SET status = ? WHERE id = ?",
                "CONFIRMED", orderId
            );
            publisher.publishEvent(new OrderConfirmed(orderId));
        }

        @Transactional
        public void confirmThenFail(long orderId) {
            jdbc.update(
                "UPDATE orders SET status = ? WHERE id = ?",
                "CONFIRMED", orderId
            );
            publisher.publishEvent(new OrderConfirmed(orderId));
            throw new IllegalStateException("simulated failure");
        }
    }

    public static class CommittedOrderReader {

        private final JdbcTemplate jdbc;

        public CommittedOrderReader(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(
            propagation = Propagation.REQUIRES_NEW,
            readOnly = true
        )
        public String readStatus(long orderId) {
            return jdbc.queryForObject(
                "SELECT status FROM orders WHERE id = ?",
                String.class, orderId
            );
        }
    }

    public static class AuditListener {

        private final CommittedOrderReader reader;
        private final List<Long> handledIds = new ArrayList<>();

        public AuditListener(CommittedOrderReader reader) {
            this.reader = reader;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterOrderCommitted(OrderConfirmed event) {
            String status = reader.readStatus(event.orderId());
            handledIds.add(event.orderId());
            System.out.println(
                "AFTER_COMMIT fresh read: " + event.orderId() + " = " + status
            );
        }

        public int handledCount() {
            return handledIds.size();
        }
    }
}
~~~

Chạy từ thư mục `after-commit-demo` bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AfterCommitReadDemo
~~~

Các dòng do chương trình in khi chạy thành công (bỏ qua log phụ của công cụ nếu có):

~~~text
AFTER_COMMIT fresh read: 1 = CONFIRMED
order 1 after service: CONFIRMED
rolled back: simulated failure
order 2 after rollback: PENDING
listener calls: 1
~~~

**Giải thích kết quả:**

- Với ID 1, thay đổi được commit trước khi `afterOrderCommitted` chạy. Bean `CommittedOrderReader` được gọi qua Spring proxy và tạo transaction đọc mới, vì thế SELECT nhận trạng thái `CONFIRMED` đã commit.
- `service.confirm(1L)` là lời gọi đi qua transaction proxy. Listener đồng bộ của `AFTER_COMMIT` hoàn thành trong bước transaction completion trước khi lời gọi service trả về, nên dòng listener xuất hiện trước dòng `order 1 after service`.
- Với ID 2, `RuntimeException` làm transaction rollback; sự kiện đã phát trong transaction không kích hoạt listener `AFTER_COMMIT`. Trạng thái trên database vẫn là `PENDING` và số lần listener được gọi là một.
- `handledIds` dùng `ArrayList` ở đây vì demo chạy đồng bộ trên một luồng gọi và không có listener async. Nếu đổi sang xử lý nhiều luồng, không nên tiếp tục dùng cấu trúc này như bộ đếm dùng chung mà thiếu đồng bộ.

Ví dụ chủ động dùng JDBC để làm rõ ranh giới transaction. Với JPA/Hibernate, phải lưu ý thêm first-level cache, entity state và lazy loading.

## 6. Với JPA/Hibernate: đọc entity từ cache khác với tải mới từ database

Trong JPA, `EntityManager` quản lý persistence context (first-level cache). Trong cùng một persistence context, việc gọi `find` theo khóa của một entity đã managed thường trả về instance đang quản lý. Điều đó không chứng minh một câu `SELECT` mới vừa chạy.

Ví dụ tình huống cần chú ý:

~~~java
@Transactional
public void confirm(long id) {
    Order order = repository.findById(id).orElseThrow();
    order.setStatus(Status.CONFIRMED);
    events.publishEvent(new OrderConfirmed(id));
}
~~~

Nếu sự kiện mang cả entity `Order` và listener dùng lại object ấy, listener sẽ nhìn thấy trạng thái trong **object** đang cầm, nhưng không nhất thiết phản ánh một lượt nạp từ database. Nếu callback còn bám vào `EntityManager` cũ, ngay cả gọi repository lại cũng có nguy cơ đi qua persistence context cũ.

Cách tổ chức ưu tiên:

1. **Phát ID hoặc payload bất biến:** ví dụ `new OrderConfirmed(id)`; tránh truyền managed entity và dựa vào lazy association sau transaction.
2. **Đọc qua bean khác có transaction mới:** `@Transactional(propagation = REQUIRES_NEW, readOnly = true)` để có ranh giới đọc độc lập.
3. **Chuyển sang DTO trước khi rời transaction mới:** chỉ mang dữ liệu cần thiết ra bước gửi email, đồng bộ chỉ mục hoặc cập nhật cache.
4. **Không dựa vào `flush()` như thay thế commit:** flush chỉ đồng bộ thay đổi xuống database trong phạm vi transaction; nếu transaction rollback thì thay đổi vẫn bị hoàn tác.

Mã minh họa mapping ra DTO:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW, readOnly = true)
public OrderSnapshot loadSnapshot(long id) {
    Order order = repository.findById(id).orElseThrow();
    return new OrderSnapshot(
        order.getId(),
        order.getStatus(),
        order.getVersion()
    );
}
~~~

`OrderSnapshot` và entity `Order` ở đây là các kiểu minh họa cần định nghĩa trong ứng dụng thực. Nếu phải đọc thêm quan hệ lazy, hãy fetch đầy đủ trong transaction đọc mới, bằng fetch join/entity graph/projection phù hợp, trước khi trả DTO.

**Giới hạn cần biết:** transaction mới không có nghĩa chắc chắn đọc được đúng *phiên bản tại thời điểm commit của T1* khi ứng dụng có nhiều writer. Sau T1 commit, một transaction T3 khác có thể cập nhật cùng bản ghi trước khi T2 SELECT. Khi cần bản ghi ứng với chính xác một phiên bản sự kiện, đính kèm version/ID bất biến, dùng điều kiện version khi đọc, hoặc dùng outbox/snapshot theo yêu cầu nghiệp vụ. Nếu đọc qua read replica, độ trễ replication có thể khiến lần đọc mới chưa thấy commit của primary.

## 7. Vì sao ghi tiếp trong AFTER_COMMIT phải đặc biệt cẩn thận?

Giả sử listener có nhiệm vụ tạo một audit record:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderConfirmed event) {
    auditRepository.save(new AuditRecord(event.orderId(), "CONFIRMED"));
}
~~~

Đây là **đoạn mã minh họa dễ sai**. Nếu lời gọi repository vẫn tham gia tài nguyên T1 đang được giữ lại trong callback, không có commit T1 thứ hai để bảo đảm ghi audit. Vì vậy không nên nhìn một giá trị thay đổi trong object, một lệnh `save()` trả về bình thường hoặc log SQL rồi kết luận đã lưu thành công.

Đối với ghi hậu xử lý cần được commit độc lập:

~~~java
@Service
public class AuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(long orderId) {
        // Ghi audit trong transaction T2 mới, có commit của riêng T2.
    }
}
~~~

Listener chỉ gọi `auditWriter.writeAudit(event.orderId())`. Lưu ý: T1 đã commit, nên nếu T2 thất bại thì việc đó **không thể rollback T1**. Nếu cần tính nguyên tử giữa thay đổi đơn hàng và bản ghi audit, hãy ghi chúng trong **cùng transaction ban đầu**, hoặc sử dụng transactional outbox: ghi outbox cùng T1 rồi xử lý hậu kỳ từ outbox theo cơ chế retry.

## 8. AFTER_COMMIT + @Async: ranh giới luồng vẫn cần thiết kế rõ

`@TransactionalEventListener(phase = AFTER_COMMIT)` và `@Async` có thể được kết hợp:

~~~java
@Component
public class NotificationListener {

    private final CommittedOrderReader reader;

    public NotificationListener(CommittedOrderReader reader) {
        this.reader = reader;
    }

    @Async("notificationsExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void notifyAfterCommit(OrderConfirmed event) {
        var snapshot = reader.loadSnapshot(event.orderId());
        // Gửi thông báo dựa trên snapshot đã nạp sau commit.
    }
}
~~~

Đoạn này là **cấu hình minh họa**; cần bật `@EnableAsync`, có bean `notificationsExecutor`, và định nghĩa `CommittedOrderReader`/`OrderSnapshot` phù hợp. Khi hoạt động đúng, callback theo transaction sẽ lên lịch phần thân listener để chạy ở worker thread **sau commit**. Transaction T1 của publisher không tự truyền sang worker. Nếu worker cần đọc/ghi có ranh giới transaction rõ ràng, vẫn nên gọi bean mở transaction phù hợp, chẳng hạn `REQUIRES_NEW`.

Các lưu ý:

- `@Async` làm cho việc xử lý sau commit có thể hoàn thành **sau khi service phát sự kiện đã trả về**.
- Exception phát sinh trong worker không tự quay lại lời gọi `publishEvent`; phải có log, metrics, `AsyncUncaughtExceptionHandler` hoặc xử lý lỗi ứng dụng phù hợp.
- ThreadLocal, security context, MDC, persistence context và transaction context không tự bảo toàn qua thread.
- Khi executor quá tải/từ chối task, cần hiểu chính sách lỗi; việc transaction gốc đã commit không bảo đảm task sau commit đã được enqueue hoặc xử lý.
- `@Async` chỉ chạy trong JVM hiện tại; nếu tiến trình chết ngay sau T1 commit nhưng trước khi worker hoàn tất, không có retry bền vững mặc định.

Đừng nhầm cách này với việc đặt executor trên `SimpleApplicationEventMulticaster` rồi giả định mọi listener transaction tự chạy async. Từ Spring Framework 6.1, listener có thể chỉ định `supportsAsyncExecution() = false` để yêu cầu thực thi trong luồng gốc, vì việc đăng ký transaction synchronization phụ thuộc đúng ngữ cảnh luồng.

## 9. Khi nào nên dùng snapshot trong event, khi nào nên đọc lại?

Hai chiến lược phục vụ nhu cầu khác nhau:

| Chiến lược | Ưu điểm | Rủi ro cần quản lý |
|---|---|---|
| Event mang snapshot bất biến | Biết dữ liệu tại thời điểm ứng dụng phát sự kiện | Snapshot được dựng trước commit và có thể không phản ánh thay đổi bởi trigger/transaction khác |
| Event chỉ mang ID; AFTER_COMMIT đọc lại | Lấy trạng thái đã commit theo lượt đọc mới | Có độ trễ/query bổ sung, và có thể thấy cập nhật mới hơn nếu concurrent writer |
| Transactional outbox lưu payload cùng T1 | Hỗ trợ tái xử lý bền vững và tách worker | Cần table, publisher/consumer, giám sát và idempotency |

Chọn snapshot nếu nhu cầu là “xử lý đúng dữ kiện tại thời điểm phát event” và payload đã được xác định đúng. Chọn đọc lại nếu hậu xử lý cần trạng thái database đã commit. Nếu cần bảo đảm xử lý sau crash hoặc gửi tới hệ thống khác, cân nhắc outbox thay vì chỉ dựa vào listener trong bộ nhớ.

### Ví dụ race condition khi đọc lại

- T1 cập nhật đơn hàng từ `PENDING` thành `CONFIRMED`, rồi commit.
- T3 cập nhật cùng đơn sang `CANCELLED` và commit ngay sau đó.
- Listener `AFTER_COMMIT` của T1 mở T2 và SELECT, thấy `CANCELLED`.

Đây không nhất thiết là lỗi transaction; đó là kết quả hợp lệ nếu T2 đọc **trạng thái mới nhất ở thời điểm đọc**. Với nghiệp vụ “thông báo xác nhận đơn hàng của phiên bản đã commit”, nên gắn version hoặc loại sự kiện trong payload, kiểm tra version trước khi phát thông báo hoặc dùng outbox có snapshot/sequence.

## 10. Giao dịch ngoài luồng và ReactiveTransactionManager

Những ví dụ trên dùng **thread-bound transaction** của `PlatformTransactionManager`, phù hợp với Spring JDBC/JPA kiểu imperative.

Từ Spring Framework 6.1, `@TransactionalEventListener` cũng có thể làm việc với reactive transaction, nhưng transaction reactive dùng **Reactor Context** thay vì ThreadLocal. Vì vậy việc gắn listener với đúng transaction đòi hỏi truyền transaction context trong source của event thông qua cơ chế như `TransactionalEventPublisher`. Không sao chép nguyên ví dụ JDBC imperative và kỳ vọng nó giữ đúng ngữ nghĩa khi thay bằng Reactor/R2DBC.

Với ứng dụng đa datasource/đa transaction manager, tên transaction manager cũng cần được chỉ định nhất quán; `REQUIRES_NEW` trên một manager khác không tự bảo đảm đang đọc từ nơi đã commit dữ liệu.

## 11. Kiểm thử: chứng minh đã commit và đã đọc từ transaction mới

Một kiểm thử đúng yêu cầu cần chứng minh **cả thời điểm xử lý lẫn ranh giới đọc**:

1. Tạo dữ liệu ban đầu (ví dụ `PENDING`) bằng thao tác đã commit.
2. Gọi service `@Transactional` qua Spring bean proxy; cập nhật, phát event, cho transaction commit.
3. Xác minh listener `AFTER_COMMIT` được gọi và bean đọc lại dùng `REQUIRES_NEW`; assert dữ liệu trả về là `CONFIRMED`.
4. Thực hiện nhánh service ném `RuntimeException` để rollback; assert event của nhánh rollback không làm chạy listener `AFTER_COMMIT` và database không có thay đổi.
5. Nếu có @Async, đồng bộ kiểm thử bằng latch/await condition có timeout rõ ràng trước khi assert; không dựa vào `Thread.sleep`.

### Bẫy thường gặp trong @Transactional test

Một integration test có `@Transactional` ở **chính phương thức test** thường được Spring Test mặc định rollback khi test kết thúc. Vì vậy listener `AFTER_COMMIT` có thể không bao giờ chạy, khiến test thất bại dù ứng dụng chạy đúng.

Ví dụ giải pháp khi dùng `spring-test`:

~~~java
@Test
@Transactional
void confirmsAfterCommit() {
    service.confirm(42L);

    // Đưa test transaction tới commit thật sự trước khi assert callback.
    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Tại đây mới assert kết quả của AFTER_COMMIT đồng bộ.
}
~~~

Đoạn trên **minh họa trong môi trường Spring Test**, cần cấu hình test runner, database và dữ liệu ID 42; các import `org.junit.jupiter.api.Test`, `org.springframework.transaction.annotation.Transactional` và `org.springframework.test.context.transaction.TestTransaction` tương ứng. Chỉ dùng `TestTransaction` khi test được chạy dưới cơ chế transaction của Spring Test. Ngoài ra có thể tổ chức test method không tự mở transaction và gọi service `@Transactional` riêng như chương trình Maven ở trên.

### Log/chỉ số nên thu thập

- `eventId`, `orderId`, transaction phase, tên listener và tên thread.
- Thời điểm T1 bắt đầu, commit thành công; thời điểm callback bắt đầu.
- Tên datasource/transaction manager của T2, thời gian SELECT, version bản ghi.
- Với async: thời điểm enqueue, bắt đầu, hoàn tất, thất bại và retry.
- Với lỗi đọc: loại exception, transaction propagation, timeout, trạng thái kết nối.

Không dùng giá trị trả về của `publishEvent` làm “xác nhận dữ liệu đã được đọc sau commit”.

## 12. Checklist lỗi thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
|---|---|---|
| Listener không chạy | Không có transaction, rollback, listener chưa là Spring bean | Kiểm tra `@Transactional` thực sự được proxy, `fallbackExecution` và pha |
| Listener chạy nhưng đọc không đúng ý | Dùng entity đang giữ từ T1, first-level cache, concurrent writer | Truyền ID; đọc trong bean `REQUIRES_NEW`; kiểm tra version |
| `save()` trong listener không bền vững | Resource T1 vẫn còn được tham gia, không có commit sau callback | Ghi trong transaction mới hoặc chuyển logic sang T1/outbox |
| Đã thêm `@Transactional(readOnly=true)` nhưng không có ranh giới mới | `REQUIRED` có thể tham gia resource hiện tại | Dùng `Propagation.REQUIRES_NEW` và lời gọi qua proxy |
| Đã khai báo `REQUIRES_NEW` nhưng không hoạt động | Self-invocation hoặc bean không do Spring quản lý | Tách bean, kiểm tra proxy và transaction manager |
| Test không thấy AFTER_COMMIT | Test transaction tự rollback | Cho commit thật bằng Spring Test hoặc test khác có transaction riêng |
| Listener async đọc khi tưởng đang trong T1 | ThreadLocal transaction không được chuyển qua worker | Bắt đầu transaction đúng tại worker, truyền ID/DTO |
| SELECT qua replica thấy giá trị cũ | Replication lag hoặc định tuyến datasource | Cân nhắc đọc primary/đòi hỏi consistency rõ ràng |
| SELECT thấy phiên bản mới hơn kỳ vọng | Có writer khác commit trước khi T2 đọc | Đính kèm version/snapshot hoặc outbox |
| Gặp lỗi vì kết nối bị giữ trong T1 khi mở T2 | Pool thiếu connection, timeout | Tính sức chứa pool và kiểm tra chính sách kết nối |

## 13. Kết luận kiến thức

`@TransactionalEventListener(AFTER_COMMIT)` là công cụ phù hợp để **trì hoãn việc kích hoạt listener cho đến khi transaction commit thành công**. Nhưng callback có thể được gọi **trước lúc Spring dọn xong tài nguyên của transaction gốc**. Vì thế, nếu mục tiêu là **đọc lại dữ liệu đã commit bằng một lượt đọc độc lập**, hãy chuyển thao tác SELECT vào Spring bean khác và áp dụng `@Transactional(propagation = REQUIRES_NEW, readOnly = true)`, bảo đảm lời gọi đi qua transaction proxy. Dùng event mang ID/immutable payload, hiểu tác động của JPA first-level cache, và kiểm tra cả nhánh commit lẫn rollback.

`REQUIRES_NEW` thiết lập transaction mới, chứ không thay thế được các hợp đồng nghiệp vụ về snapshot, version, race condition, retry hay độ bền sau crash. Khi cần bảo đảm những điều đó, phối hợp với locking/versioning hoặc transactional outbox.

### Tài liệu chính thức

- [Spring Framework Reference 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework Javadoc 6.2.8 — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework Javadoc 6.2.8 — TransactionPhase](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [Spring Framework Javadoc 6.2.8 — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework Reference — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
