# Không dùng ApplicationEvent làm hàng đợi bền vững trong Spring Framework

## 1. Mục tiêu bài học

Spring Framework Application Events là cơ chế thông báo **nội bộ trong một ApplicationContext**. Nó phù hợp để giảm phụ thuộc giữa các thành phần cùng ứng dụng: một service phát sự kiện, nhiều listener phản ứng mà publisher không phải trực tiếp gọi từng listener.

Nhưng **ApplicationEvent không phải một durable message queue**. Trong cấu hình Spring Framework thuần, `ApplicationEventPublisher.publishEvent(...)` không tự ghi message vào database hay broker; cũng không có xác nhận xử lý bền vững, retry sau khi process chết, dead-letter queue, consumer offset hoặc lịch sử có thể phát lại.

Điều này đặc biệt quan trọng ở nhóm **Tích hợp ngoài ứng dụng**: gửi thông điệp tới hệ thống khác, gọi cổng thanh toán, gửi email giao dịch, cập nhật kho, chuyển dữ liệu cho ERP/CRM hoặc phát event cho các microservices. Các tác vụ đó thường đòi hỏi **khả năng khôi phục sau crash**, không chỉ gọi một callback khi JVM đang sống.

Kết thúc bài, bạn sẽ biết:

1. Phân biệt **event dispatch nội bộ** và **durable message delivery**.
2. Vì sao cả listener đồng bộ, `@Async` và `@TransactionalEventListener(AFTER_COMMIT)` đều có giới hạn độ bền.
3. Phân tích các **failure windows** giữa database commit, event publication, broker ACK và consumer side effect.
4. Thiết kế **transactional outbox, relay, message broker, idempotent inbox** theo hướng at-least-once.
5. Chọn giữa Kafka, RabbitMQ, durable job table và **Spring Modulith Event Publication Registry** khi phù hợp.
6. Chạy ví dụ Java 17+ cho thấy listener thuần mất trạng thái khi tạo lại context, còn outbox lưu trong database vẫn có record để xử lý.
7. Kiểm thử crash, duplicate, redrive, ordering, observability và bảo mật trước khi triển khai.

**Thông điệp cốt lõi:** `publishEvent(...)` là thao tác thông báo/handoff trong ứng dụng, **không phải cam kết “message đã được lưu bền và chắc chắn sẽ được xử lý”**.

## 2. Cơ chế Spring Application Events thực sự làm gì?

Các thành phần cơ bản:

| Thành phần | Trách nhiệm |
| --- | --- |
| `ApplicationEventPublisher` | API phát một event từ code ứng dụng |
| `ApplicationEventMulticaster` | Quyết định cách phân phối event tới listeners |
| `SimpleApplicationEventMulticaster` | Implementation mặc định; gọi listener đồng bộ nếu không cấu hình executor |
| `@EventListener` | Đăng ký method xử lý event trong Spring bean |
| `@Async @EventListener` | Schedule method listener qua executor nếu async support được bật |
| `@TransactionalEventListener` | Gắn callback với phase của transaction có sẵn |
| Message broker | Hạ tầng riêng có log/queue, consumer, ACK/offset và cấu hình lưu bền |
| Transactional outbox | Bản ghi message lưu trong cùng DB transaction với dữ liệu nghiệp vụ |

Ví dụ Spring bean:

~~~java
// Minh họa, cần OrderPlaced và Spring-managed bean.
public void placeOrder(long orderId) {
    repository.saveOrder(orderId);
    publisher.publishEvent(new OrderPlaced(orderId));
}

@EventListener
public void notifyCustomer(OrderPlaced event) {
    mailClient.sendOrderConfirmation(event.orderId());
}
~~~

Với **SimpleApplicationEventMulticaster mặc định**, listener đồng bộ thực thi trên thread gọi publish. Nếu listener gửi email thành công rồi method sau đó ném exception, database có thể rollback trong khi email bên ngoài không thể “rollback”. Nếu JVM dừng ở một thời điểm bất lợi, không có record Spring Framework mặc định nào để tự phát lại email.

Sơ đồ:

~~~text
OrderService / publisher thread
     |
     +-- ApplicationEventPublisher.publishEvent(OrderPlaced)
                    |
                    +-- SimpleApplicationEventMulticaster
                           |
                           +-- @EventListener A
                           +-- @EventListener B
                           +-- ...
     |
     +-- caller tiếp tục (sau các listener đồng bộ)
~~~

Event object có thể là một subclass của `ApplicationEvent` hoặc POJO/record. Với POJO, Spring có thể dùng `PayloadApplicationEvent` cho dispatch. **Không kiểu event nào trong số này mặc nhiên được persist** chỉ nhờ được publish.

### 2.1. Đồng bộ không có nghĩa bền vững

Đúng là publisher mặc định **chờ các listener đồng bộ hoàn tất**. Điều đó có thể giúp caller phát hiện một số lỗi ngay, nhưng không cho bạn:

- **atomicity** với side effect ngoài transaction, ví dụ API thanh toán/email;
- retry tự động qua JVM restart;
- consumer checkpoint/offset;
- lịch sử message có thể đọc lại;
- DLQ hoặc redrive;
- đảm bảo delivery khi publisher hoặc consumer process chết;
- độc lập giữa các ứng dụng khác nhau.

Một lời gọi đồng bộ có thể hữu ích cho validation/invariant trong cùng ứng dụng, nhưng nó không tự trở thành message queue.

### 2.2. Async không có nghĩa bền vững

~~~java
// Minh họa trong Spring bean, cần @EnableAsync.
@Async("notificationExecutor")
@EventListener
public void sendReceipt(OrderPlaced event) {
    mailClient.sendOrderConfirmation(event.orderId());
}
~~~

Nếu `notificationExecutor` là `ThreadPoolTaskExecutor` thông thường, task sẽ nằm trong thread pool/queue của JVM. Khi process chết, các task đang chờ hoặc đang chạy có thể bị mất. Caller cũng không mặc nhiên được thông báo khi async listener thất bại.

Ngay cả khi bạn thiết lập `setWaitForTasksToCompleteOnShutdown(true)`, đó là một chính sách shutdown **có trật tự**; nó không giúp chống process kill, máy mất điện, container bị cưỡng chế dừng hoặc crash trước khi shutdown hook chạy. Queue còn có thể đầy và từ chối task.

### 2.3. Thay multicaster bằng executor cũng không thay đổi bản chất

~~~java
// Snippet cấu hình, cần Executor phù hợp.
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster multicaster(Executor eventExecutor) {
    SimpleApplicationEventMulticaster m =
            new SimpleApplicationEventMulticaster();
    m.setTaskExecutor(eventExecutor);
    return m;
}
~~~

Cách này có thể khiến nhiều listeners được schedule bất đồng bộ. Nhưng đó vẫn là **dispatch in-process**, không tạo broker hay log bền. Một số listeners báo `supportsAsyncExecution()==false`, bao gồm các trường hợp transaction-synchronized, vẫn phải chạy trong publisher thread để giữ semantics. Không nên ép mọi listener sang async và coi là đã có reliability.

## 3. Phân tích các khoảng mất thông điệp (failure windows)

Xem xét nghiệp vụ đặt hàng và gửi thông báo tới một service khác. Có hai cách triển khai ngây thơ, cả hai đều có khoảng rủi ro.

### 3.1. Commit database trước, rồi publish event

~~~text
1. BEGIN TRANSACTION
2. INSERT orders
3. COMMIT                [order tồn tại]
4. publishEvent(...)
5. listener gửi message đi ngoài
~~~

Nếu JVM **crash giữa bước 3 và 4**, order đã được lưu nhưng không ai biết cần gửi thông báo. Không có một record bền vững nào cho việc phát lại.

Ngay cả sau bước 4, listener bất đồng bộ vẫn có thể chưa chạy. Crash ở đó làm mất task đang xếp hàng.

### 3.2. Publish event trước khi commit

~~~text
1. BEGIN TRANSACTION
2. INSERT orders
3. publishEvent(...)
4. listener gọi API đối tác
5. COMMIT hoặc ROLLBACK
~~~

Nếu API đối tác đã nhận message nhưng transaction **rollback** ở bước 5, bên ngoài có side effect của một order không tồn tại. Một callback đồng bộ không có khả năng hoàn tác API ngoài hệ thống.

Nếu listener chạy async, nó có thể đọc database trước lúc transaction commit và chưa thấy dữ liệu. Việc gọi `publishEvent(...)` trong `@Transactional` không làm worker tự dùng transaction cũ.

### 3.3. Sử dụng AFTER_COMMIT

~~~java
// Minh họa một Spring bean.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void publishIntegrationEvent(OrderPlaced event) {
    externalPublisher.send(event);
}
~~~

Cách này giúp tránh phát message khi transaction nguồn rollback, nhưng vẫn có **crash gap giữa COMMIT và lúc callback/send hoàn tất**. `AFTER_COMMIT` không đồng nghĩa message đã persist để tự retry sau restart.

Mặc định, `@TransactionalEventListener` bỏ qua event được publish ngoài transaction (`fallbackExecution=false`). Các phase khác gồm `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`; chúng giải quyết **thời điểm callback**, không thay thế durable queue.

### 3.4. Bảng failure windows

| Thời điểm crash/lỗi | Nếu chỉ ApplicationEvent | Nếu có outbox bền vững |
| --- | --- | --- |
| Trước DB commit | Transaction có thể rollback | Order và outbox cùng rollback |
| Sau commit, trước publish | Thông báo có thể mất vĩnh viễn | Outbox record vẫn tồn tại |
| Sau event được dispatch vào executor nhưng trước worker chạy | Task in-memory có thể mất | Relay có thể đọc lại record chưa gửi |
| Broker nhận message, nhưng ACK về relay bị mất | Không có checkpoint chuẩn của Spring Context | Relay có thể gửi lại, cần idempotency |
| Consumer xử lý thành công rồi crash trước ACK | Không có consumer offset | Message có thể giao lại, consumer chống duplicate |
| Downstream tạm thời unavailable | Lỗi/callback async fail tùy cách viết | Retry policy và DLQ theo broker/consumer |
| Consumer nhận payload không hỗ trợ | Không tự có DLT | Có thể chuyển DLQ để điều tra và redrive |

Chìa khóa là không chỉ hỏi “đã gọi publish chưa?”, mà phải hỏi **“ý định phải phát thông điệp đã được lưu ở đâu, và ai phục hồi nó sau crash?”**.

## 4. Định nghĩa đúng mức độ bảo đảm (delivery semantics)

Có ba khái niệm thường bị nhầm:

**At-most-once:** xử lý tối đa một lần. Có thể mất message nếu failure xảy ra. Một event in-memory không có retry/cơ chế phục hồi thường không đáp ứng nhu cầu phải xử lý cuối cùng.

**At-least-once:** hệ thống có thể giao message lại cho đến khi xác nhận xử lý thành công. Đổi lại, **duplicate** có thể xảy ra. Đây là mô hình thực tế phổ biến khi dùng outbox + broker + consumer idempotent.

**Exactly-once:** cần nói chính xác *đúng một lần trong phạm vi nào*. Một số broker/stream processor cung cấp tính năng exactly-once trong phạm vi transaction/log cụ thể, nhưng không vì vậy bảo đảm một lần duy nhất cho mọi database, HTTP API, email, cổng thanh toán xuyên hệ thống.

Ví dụ broker nhận message, consumer gọi API thanh toán thành công, rồi consumer crash trước khi ghi ACK. Khi message được giao lại, API thanh toán có thể được gọi lần nữa. Để tránh double-charge, consumer cần **idempotency key** ổn định, xử lý trạng thái kết quả mơ hồ và/hoặc cơ chế reconcile.

Không hứa “exactly-once end-to-end” chỉ nhờ thêm `@Transactional`, Kafka transactions hoặc một unique constraint cục bộ.

## 5. Kiến trúc nên dùng cho tích hợp ngoài ứng dụng

Một mô hình phổ biến:

~~~text
OrderService
   |
   +-- BEGIN DB TRANSACTION
   |       +-- INSERT/UPDATE orders
   |       +-- INSERT outbox_events (eventId, payload, status=NEW)
   |   COMMIT
   |
   +-- Relay / CDC
           |
           +-- broker (Kafka / RabbitMQ / dịch vụ messaging)
                   |
                   +-- consumer A
                   |       +-- inbox/processed_events
                   |       +-- DB/API side effect
                   |       +-- ACK đúng lúc
                   |
                   +-- consumer B
                           +-- idempotent processing
                           +-- retry / DLQ
~~~

Các thành phần:

1. **Producer transaction** ghi dữ liệu nghiệp vụ và bản ghi outbox **trong cùng database transaction**.
2. **Outbox relay** đọc những bản ghi chưa gửi, publish tới broker, xử lý ACK/failure và cập nhật trạng thái gửi.
3. **Broker** giữ message theo cấu hình durability/retention/replication; tách producer với consumer.
4. **Consumer** xử lý, lưu processed marker/inbox và xác nhận message đúng ranh giới.
5. **Retry + dead-letter** giải quyết lỗi transient/permanent; quan sát, giới hạn số lần, tránh loop.
6. **Reconciliation/compensation** khắc phục business state nếu side effect cuối cùng không thể hoàn tất.

Đây không phải một annotation đơn lẻ trong Spring Framework; cần storage schema, jobs, transactions, broker configuration, monitoring và kiểm thử failure windows.

## 6. Transactional outbox: atomic intent

Giả sử một đơn hàng chuyển sang trạng thái CREATED. Thay vì chỉ publish một event trong bộ nhớ, **ghi đồng thời bản ghi outbox**:

~~~sql
-- SQL minh họa, chi tiết kiểu dữ liệu tùy hệ quản trị.
CREATE TABLE orders (
    order_id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE outbox_events (
    event_id VARCHAR(80) PRIMARY KEY,
    aggregate_id VARCHAR(80) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(120) NOT NULL,
    schema_version INT NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt_count INT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    next_attempt_at TIMESTAMP,
    leased_until TIMESTAMP
);

CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ưu điểm: nếu transaction **rollback**, cả order và outbox đều không tồn tại; nếu **commit**, cả hai tồn tại. Nhờ đó không còn khoảng “order commit xong nhưng chưa lưu ý định phát message”.

### Lưu ý về tính nguyên tử

- Không dùng hai transactions riêng cho orders và outbox; như vậy vẫn có dual-write gap.
- Không gọi broker trước commit rồi mong broker rollback cùng DB.
- Không ghi outbox từ `@TransactionalEventListener(AFTER_COMMIT)` trong transaction mới và gọi đó là atomic với order gốc: khi process chết sau commit order nhưng trước callback, vẫn mất bản ghi outbox.
- Nếu cần outbox trong transaction hiện tại, ghi trực tiếp qua repository hoặc cơ chế bảo đảm chạy trước commit với đúng transaction semantics; kiểm thử cả rollback.
- Tránh payload chứa live JPA entity, `HttpServletRequest`, security token hoặc object không có schema rõ ràng; serialize integration event thành DTO versioned.

### Event envelope

~~~java
// Snippet Java: dữ liệu phải được serialize và persist rõ ràng.
public record IntegrationEvent(
        String eventId,
        String eventType,
        int schemaVersion,
        String aggregateId,
        long aggregateVersion,
        String correlationId,
        String causationId,
        String occurredAt,
        String payloadJson
) {}
~~~

**eventId** ổn định khi retry/redelivery; **aggregateId** dùng làm message key/partitioning nếu cần ordering theo aggregate; **schemaVersion** giúp consumer thay đổi dần; correlation/causation phục vụ trace.

Hạn chế dùng full entity snapshot nếu chỉ cần vài business facts. Một integration event là **hợp đồng giữa các hệ thống**, cần versioning, data minimization và chính sách backward compatibility.

## 7. Outbox relay: polling hoặc CDC

Có hai cách triển khai phổ biến.

### 7.1. Polling relay

Worker định kỳ chọn một batch outbox có trạng thái NEW hoặc đến thời điểm retry. Khi có nhiều instances, cần **claim/lease** an toàn để không tạo quá nhiều duplicate đồng thời.

Luồng cơ bản:

~~~text
poll NEW / retryable records
    |
    +-- claim batch an toàn (lease + owner + deadline)
    +-- publish tới broker với eventId/key
    +-- chờ broker acknowledgment theo chính sách
    +-- mark SENT hoặc PUBLISHED
    |
    +-- lỗi -> tăng attempt, backoff, giữ record để retry
~~~

Một mẫu SQL như `SELECT ... FOR UPDATE SKIP LOCKED` có thể hữu ích ở các database hỗ trợ, nhưng không được copy nguyên câu lệnh sang mọi DB mà không kiểm tra semantics. Một relay crash giữa broker ACK và mark SENT sẽ khiến event **được gửi lại**. Do đó at-least-once + consumer idempotency vẫn cần thiết.

**Không mark SENT trước khi xác nhận broker đã nhận theo hợp đồng.** Nếu process crash sau mark SENT nhưng trước khi thực sự publish, record có thể bị mất không phục hồi.

Cần giới hạn batch, timeout, queue, backoff và retention. Nếu không, outbox có thể tăng vô hạn khi broker unavailable.

### 7.2. CDC / change data capture

Một công cụ như Debezium có thể đọc log thay đổi của database và phát các outbox records tới broker. Điều này tránh polling liên tục và giảm công việc tự viết relay, nhưng vẫn cần:

- DB transaction cho dữ liệu nghiệp vụ và outbox.
- Connector deployment, checkpoint/offset, schema mapping.
- Theo dõi replication slot/log retention và consumer lag.
- Idempotent consumer khi có duplicate/restart.
- Kế hoạch thay đổi schema/partition key và replay.

CDC không “tự biến @EventListener thành Kafka event”. Dữ liệu được CDC theo dõi phải được persist theo cấu trúc phù hợp trong database.

## 8. Idempotent consumer và inbox

Kể cả khi outbox bảo đảm không mất **ý định phát**, broker/relay có thể giao trùng. Consumer phải chịu được.

~~~text
receive(eventId=evt-101)
    |
    +-- BEGIN consumer DB transaction
    |       +-- INSERT processed_events(consumer, evt-101)
    |       +-- UPDATE local business state
    |   COMMIT
    |
    +-- ACK message
~~~

Unique constraint theo `(consumer_name, event_id)` giúp phát hiện duplicate. Đừng chỉ `SELECT` kiểm tra chưa xử lý rồi gọi side effect trước khi INSERT marker: hai workers có thể nhìn thấy chưa xử lý và cùng làm việc. Cần transaction, unique constraint và thiết kế cụ thể cho external side effects.

Với một API thanh toán ngoài DB transaction, ghi dấu “đã xử lý” **trước** khi call có thể làm mất job nếu crash; ghi dấu **sau** call có thể gọi lại khi kết quả mơ hồ. Cần external idempotency key ổn định và/hoặc query outcome/reconciliation.

### Idempotency không có nghĩa bỏ qua mọi event cùng aggregate

Khóa chống duplicate nên dựa trên **event ID và consumer**, không phải chỉ `orderId`. Một đơn hàng hợp pháp có nhiều events khác nhau (`OrderCreated`, `OrderPaid`, `OrderShipped`). Nếu dedup toàn bộ theo orderId, consumer sẽ bỏ nhầm các bước hợp lệ.

Nếu consumer xử lý sự kiện phụ thuộc thứ tự, cần aggregate version, optimistic lock hoặc partition theo aggregate key; unique eventId chỉ chặn duplicate, **không bảo đảm ordering**.

## 9. Java 17+ demo: event in-memory và outbox bền qua context recreation

Ví dụ sau cố ý không có Kafka/RabbitMQ để tập trung vào bài học: **sự kiện nội bộ không được Spring lưu lại**, trong khi một record outbox được ghi vào **H2 file database** và còn sau khi đóng/tạo lại `ApplicationContext`.

Môi trường:

- Java 17+, Maven.
- Spring Framework **6.2.12** (`spring-context`, `spring-jdbc`).
- H2 **2.3.232**, ở chế độ **file-backed** (không phải `jdbc:h2:mem`).
- TransactionTemplate để ghi **orders + outbox** trong một local DB transaction.
- `@EventListener` thuần chỉ tăng bộ đếm in-memory.
- Mock relay/consumer đọc outbox sau khi tạo lại context và xử lý duplicate với khóa unique.

**Giới hạn minh bạch:** demo tái tạo Spring ApplicationContext **trong cùng JVM** để quan sát vòng đời, không mô phỏng mất điện hay kiểm thử fsync của một hệ thống production. Mock consumer chỉ ghi processed marker trong cùng H2 database, không gửi tới broker/API thật. Trong production, cần relay, ACK, retention, schema, monitoring và side-effect transaction phù hợp.

### 9.1. Cấu trúc thư mục

~~~text
application-event-not-a-queue/
├── pom.xml
└── src/main/java/demo/NotAQueueDemo.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>application-event-not-a-queue</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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

### 9.3. src/main/java/demo/NotAQueueDemo.java

~~~java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class NotAQueueDemo {

    public record OrderCreated(String eventId, String orderId) {}
    public record OutboxRow(String eventId, String orderId) {}

    public static final class LocalListener {
        private final AtomicInteger received = new AtomicInteger();

        @EventListener
        public void on(OrderCreated event) {
            received.incrementAndGet();
        }

        public int count() {
            return received.get();
        }
    }

    public static final class OrderService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.tx = tx;
            this.publisher = publisher;
        }

        public void place(String orderId, String eventId) {
            // Order + outbox: một local transaction, commit hoặc rollback cùng nhau.
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO orders (order_id, status) VALUES (?, ?)",
                    orderId, "CREATED");
                jdbc.update(
                    "INSERT INTO outbox_events "
                        + "(event_id, order_id, delivered) VALUES (?, ?, FALSE)",
                    eventId, orderId);
            });

            // Chỉ thông báo in-process; không phải durable handoff.
            // Nếu crash ngay trước dòng này, outbox vẫn còn để relay.
            publisher.publishEvent(new OrderCreated(eventId, orderId));
        }
    }

    public static final class OutboxRelay {
        private final JdbcTemplate jdbc;

        public OutboxRelay(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public int pending() {
            return jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox_events WHERE delivered = FALSE",
                    Integer.class);
        }

        public OutboxRow firstPending() {
            List<OutboxRow> rows = jdbc.query(
                "SELECT event_id, order_id FROM outbox_events "
                    + "WHERE delivered = FALSE ORDER BY event_id",
                (rs, i) -> new OutboxRow(
                    rs.getString("event_id"),
                    rs.getString("order_id")));

            if (rows.size() != 1) {
                throw new IllegalStateException(
                    "Expected one pending outbox record");
            }
            return rows.get(0);
        }

        public void markDelivered(String eventId) {
            int changed = jdbc.update(
                "UPDATE outbox_events SET delivered = TRUE WHERE event_id = ?",
                eventId);
            if (changed != 1) {
                throw new IllegalStateException("Outbox update failed");
            }
        }
    }

    public static final class MockConsumer {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;

        public MockConsumer(JdbcTemplate jdbc, TransactionTemplate tx) {
            this.jdbc = jdbc;
            this.tx = tx;
        }

        // Chỉ mô phỏng một local consumer DB transaction.
        public boolean processOnce(OutboxRow event) {
            try {
                return Boolean.TRUE.equals(tx.execute(status -> {
                    jdbc.update(
                        "INSERT INTO processed_events (event_id, order_id) "
                            + "VALUES (?, ?)",
                        event.eventId(), event.orderId());
                    return true;
                }));
            } catch (DuplicateKeyException duplicate) {
                return false;
            }
        }

        public int processedRows() {
            return jdbc.queryForObject(
                    "SELECT COUNT(*) FROM processed_events",
                    Integer.class);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource dataSource =
                    new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl(
                "jdbc:h2:file:./target/events-outbox-db;"
                    + "DB_CLOSE_ON_EXIT=FALSE");
            dataSource.setUsername("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        public LocalListener localListener() {
            return new LocalListener();
        }

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc,
                TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, tx, publisher);
        }

        @Bean
        public OutboxRelay outboxRelay(JdbcTemplate jdbc) {
            return new OutboxRelay(jdbc);
        }

        @Bean
        public MockConsumer mockConsumer(
                JdbcTemplate jdbc,
                TransactionTemplate tx) {
            return new MockConsumer(jdbc, tx);
        }
    }

    private static void resetDemoTables(JdbcTemplate jdbc) {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS orders ("
                + "order_id VARCHAR(80) PRIMARY KEY, "
                + "status VARCHAR(30) NOT NULL)");
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS outbox_events ("
                + "event_id VARCHAR(80) PRIMARY KEY, "
                + "order_id VARCHAR(80) NOT NULL, "
                + "delivered BOOLEAN NOT NULL)");
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS processed_events ("
                + "event_id VARCHAR(80) PRIMARY KEY, "
                + "order_id VARCHAR(80) NOT NULL)");

        // Chỉ dành cho demo tất định. Không xóa bảng production!
        jdbc.update("DELETE FROM processed_events");
        jdbc.update("DELETE FROM outbox_events");
        jdbc.update("DELETE FROM orders");
    }

    public static void main(String[] args) {
        // Pha 1: lưu order + outbox, dispatch event thuần in-process.
        try (var first =
                new AnnotationConfigApplicationContext(Config.class)) {
            resetDemoTables(first.getBean(JdbcTemplate.class));

            first.getBean(OrderService.class).place("order-101", "evt-101");

            System.out.println(
                "memory-listener-before-close="
                    + first.getBean(LocalListener.class).count());
            System.out.println(
                "outbox-before-close="
                    + first.getBean(OutboxRelay.class).pending());
        }

        // Pha 2: Spring ApplicationContext khác, cùng H2 file database.
        try (var second =
                new AnnotationConfigApplicationContext(Config.class)) {
            LocalListener listener = second.getBean(LocalListener.class);
            OutboxRelay relay = second.getBean(OutboxRelay.class);
            MockConsumer consumer = second.getBean(MockConsumer.class);

            System.out.println(
                "memory-listener-after-reopen=" + listener.count());
            System.out.println(
                "outbox-after-reopen=" + relay.pending());

            OutboxRow record = relay.firstPending();

            boolean firstDelivery = consumer.processOnce(record);
            boolean secondDelivery = consumer.processOnce(record);

            // Chỉ mark sau khi mock consumer xác nhận.
            relay.markDelivered(record.eventId());

            System.out.println("mock-consumer-first=" + firstDelivery);
            System.out.println(
                "mock-consumer-duplicate-skipped=" + !secondDelivery);
            System.out.println(
                "outbox-after-mock-relay=" + relay.pending());
            System.out.println(
                "processed-event-rows=" + consumer.processedRows());
        }
    }
}
~~~

Chạy tại thư mục chứa pom.xml với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.NotAQueueDemo
~~~

Tám dòng do **chính chương trình** in ra (log Maven/Spring nếu có là riêng):

~~~text
memory-listener-before-close=1
outbox-before-close=1
memory-listener-after-reopen=0
outbox-after-reopen=1
mock-consumer-first=true
mock-consumer-duplicate-skipped=true
outbox-after-mock-relay=0
processed-event-rows=1
~~~

### 9.4. Tại sao output này hợp lý?

1. `place(...)` gọi `TransactionTemplate.executeWithoutResult(...)`, ghi row orders và outbox trong **cùng transaction**, sau đó commit.
2. `publisher.publishEvent(new OrderCreated(...))` gọi listener đồng bộ mặc định trong context thứ nhất. Bộ đếm `LocalListener.received` tăng lên 1.
3. Khi context thứ nhất đóng, bean `LocalListener` cùng bộ đếm của nó không được Spring persist.
4. Context thứ hai tạo **bean listener mới**, bộ đếm là 0. Spring **không tự replay** `OrderCreated` cho context mới.
5. H2 chạy ở chế độ **file-backed** nên outbox record đã commit vẫn còn; pending=1 ở context thứ hai.
6. Mock consumer xử lý eventId `evt-101` lần đầu: `INSERT processed_events` thành công.
7. Cùng event được xử lý lần hai: khóa chính event_id ngăn duplicate, `DuplicateKeyException` được bắt và kết quả là false.
8. Sau khi mock consumer xác nhận lần xử lý đầu, relay mark delivered=true; pending=0 và processed-event-rows=1.

**Quan trọng:** demo này chỉ chứng minh sự khác biệt giữa **state in-memory gắn lifecycle của context** và **bản ghi dữ liệu được commit vào H2 file database**. Nó không chứng minh một message broker đã nhận được event. Mock consumer dùng cùng DB nên không có ranh giới network và crash của hai service. Production cần tách rõ ACK, transaction và idempotency.

### 9.5. Ranh giới chịu lỗi của demo

- Khi chạy lại toàn bộ `main`, hàm `resetDemoTables` **cố ý xóa dữ liệu demo** để stdout giống nhau. Đây là test fixture, không phải hành vi của outbox production.
- File H2 được tạo dưới `target/` nhờ URL `jdbc:h2:file:./target/events-outbox-db`. Maven tạo `target` trong build; chương trình cần có quyền ghi thư mục dự án.
- Đóng/tạo lại context **không đồng nghĩa giết JVM đột ngột**; test crash thật còn cần chạy hai tiến trình, kill ở điểm định trước, rồi kiểm tra DB và relay.
- `markDelivered` trong demo xảy ra sau mock consumer. Khi gửi broker thật, relay phải đợi **broker ACK theo policy** thay vì đợi consumer đã hoàn thành end-to-end; consumer xử lý và ACK độc lập.
- Transaction unique constraint ở consumer chỉ chặn duplicate trong database demo. Để tránh side effect trùng ở API bên ngoài, cần external idempotency key và xử lý outcome không rõ ràng.

## 10. Spring Kafka và RabbitMQ giải quyết gì?

### Spring for Apache Kafka

Kafka giữ log theo topic/partition với retention và replication do cluster cấu hình. Spring Kafka cung cấp `KafkaTemplate`, `@KafkaListener`, container error handlers, retry/backoff và dead-letter publishing. Ví dụ ý tưởng (snippet, không thuộc demo Maven mục 9):

~~~java
// Cần spring-kafka và KafkaTemplate đã cấu hình.
@Bean
DefaultErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    // 1 lần đầu + 2 retries = tối đa 3 attempts.
    return new DefaultErrorHandler(
            recoverer, new FixedBackOff(1_000L, 2L));
}
~~~

Phải gắn handler với listener container factory thực tế, kiểm tra offset commit/ACK và xác nhận DLT publish. DeadLetterPublishingRecoverer mặc định có quy tắc destination tùy cấu hình/phiên bản (thường topic hậu tố -dlt); DLT cần được tạo và có partition phù hợp.

**Kafka không tự làm database write và broker publish thành một local transaction nguyên tử** chỉ vì bạn có `@Transactional`. Khi order được lưu ở database khác Kafka, outbox hoặc cơ chế dual-write consistency tương đương vẫn cần được xem xét.

### Spring AMQP / RabbitMQ

RabbitMQ có durable queues, persistent messages, publisher confirms, consumer acknowledgments, retry topology và dead-letter exchanges. Các tính năng đó phải **được cấu hình phù hợp**, không tự bật chỉ vì dùng Spring AMQP.

Những câu hỏi cần trả lời:

- Queue có durable không, message có được publish với delivery mode/confirm phù hợp không?
- ACK được gửi **sau khi** consumer hoàn thành side effect chưa?
- Khi consumer crash trước ACK, message được redeliver thế nào?
- Queue đầy/broker unavailable thì producer làm gì?
- Có DLX/DLQ, bounded retry, TTL/retention và replay policy không?
- Có replication/availability theo SLA cần thiết không?

Một broker giúp lưu/giao message, nhưng vẫn cần idempotent consumer, timeout, monitoring và đôi khi transactional outbox ở producer.

## 11. Spring Modulith Event Publication Registry: ngoại lệ có chủ đích

Một lưu ý quan trọng để không tuyệt đối hóa bài học: **Spring Modulith** là dự án bổ sung có **Event Publication Registry**, có thể ghi nhận các event publications cho transactional listeners trong storage hỗ trợ transaction và đánh dấu khi xử lý hoàn tất. Nó còn có cơ chế truy vấn/resubmit publications chưa hoàn tất hoặc thất bại tùy version/configuration.

Điều này **không phải hành vi mặc định của Spring Framework ApplicationEventPublisher**. Muốn có nó, ứng dụng phải thêm dependencies Spring Modulith, chọn repository backend phù hợp (JDBC/JPA/MongoDB...), thiết lập schema/transaction và chính sách resubmission.

Cách hiểu đúng:

- **Spring Framework thuần:** chỉ ApplicationEventPublisher + @EventListener không tạo durable queue.
- **Spring Modulith Registry được cấu hình:** có persistent publication log cho phạm vi listeners mà registry hỗ trợ; xử lý retry/resubmit phải theo cấu hình và phiên bản.
- **External broker integration:** cần externalization/publishing adapter, broker semantics, mapping payload và consumer behavior; registry không tự biến mọi local event thành hợp đồng phân tán cho mọi consumers.
- **Cross-service delivery:** vẫn phải kiểm tra trạng thái broker, ACK và idempotency ngoài ứng dụng.

Nếu hệ thống là modular monolith và muốn đáng tin cậy hơn giữa các module trong cùng ứng dụng, Spring Modulith có thể đáng cân nhắc. Nếu hệ thống phải giao messages tới nhiều service độc lập, hãy đánh giá rõ externalization, broker và outbox trước khi chọn công cụ.

## 12. Retrying và dead-letter phải có ranh giới

Một durable queue đúng nghĩa thường cần:

- Giới hạn attempts, exponential backoff và jitter;
- timeout per attempt và global deadline;
- phân biệt lỗi transient/permanent/ambiguous;
- chính sách không nhận task mới khi quá tải;
- DLQ/DLT chứa original event, consumer, error code và attempts;
- runbook redrive có approval/rate limit;
- retention, archiving và dữ liệu nhạy cảm;
- metrics queue age/oldest outstanding;
- compensation/saga khi lỗi tạo hậu quả nghiệp vụ.

**DLQ không tự thực hiện compensation.** Một email gửi lỗi không có nghĩa đơn hàng cần hoàn tiền. Ngược lại, một sự cố payment có thể cần workflow bù tồn kho trước khi có người xử lý DLQ.

Nếu một message redrive sau khi order đã CANCELLED, consumer phải đối chiếu state/version để không vô tình phát lại nghiệp vụ cũ. Retry giữ original eventId; nếu tạo một command mới, nó phải có ID riêng và causation link phù hợp.

## 13. Đo độ tin cậy và trạng thái backlog

Các metrics hữu ích:

| Metric gợi ý | Mục đích |
| --- | --- |
| `outbox.pending` | Số bản ghi chưa phát |
| `outbox.oldest_age` | Tuổi record lâu nhất chưa gửi |
| `relay.publish.duration` | Latency relay đến broker ACK |
| `relay.failures` | Số publish thất bại |
| `broker.consumer.lag` | Độ trễ tiêu thụ theo broker |
| `consumer.processing.errors` | Lỗi xử lý theo consumer/event type |
| `consumer.duplicate.skipped` | Duplicate được chặn |
| `dlq.depth` / `dlq.oldest_age` | Message cần điều tra/redrive |
| `business.completion.latency` | Từ event phát sinh đến khi tác vụ nghiệp vụ hoàn tất |

Đây là **tên metric minh họa**, không có nghĩa Spring Framework tự xuất đầy đủ chúng. Đặt IDs chi tiết vào structured logs/traces; tránh dùng eventId/orderId làm high-cardinality metric tags.

Alert không chỉ dựa vào tổng pending: một outbox có 5 message nhưng record lâu nhất đã 2 ngày có thể đáng lo hơn 500 message vừa được tạo và đang xử lý bình thường.

### Observability không thay thế replay

Correlation ID và trace giúp debug sự cố, nhưng một trace đẹp không phải một durable log. Nếu job biến mất sau process crash và không có outbox/broker record, logging/tracing thường không đủ để tái tạo chính xác payload và trạng thái cần gửi.

## 14. Checklist kiểm thử crash và duplicate

### Producer

1. Transaction orders + outbox commit thành công: cả hai rows tồn tại.
2. Business transaction rollback: cả hai rows biến mất.
3. Process chết **sau commit nhưng trước in-process publish**: outbox vẫn tồn tại cho relay.
4. Relay crash trước broker ACK: không mark SENT nhầm.
5. Relay crash sau broker ACK nhưng trước mark SENT: message có thể được gửi lại; consumer phải idempotent.
6. Broker unavailable lâu: pending outbox tăng nhưng không bị xóa; có cảnh báo và retry bounds.
7. Hệ thống nhiều relay instances: claim/lease không gây publish storm; kiểm tra lease expiration.

### Consumer

1. Duplicate cùng eventId: business side effect không nhân đôi.
2. Một aggregate có nhiều eventIds khác nhau: không bị dedup sai theo orderId.
3. Consumer crash sau DB commit nhưng trước message ACK: redelivery không chạy lại local transaction side effect.
4. External API timeout có kết quả mơ hồ: query trạng thái/giữ idempotency key.
5. Schema cũ/mới: deserialize/transform đúng và lỗi đưa vào DLQ.
6. Message lệch thứ tự: aggregate version/state guard xử lý rõ.
7. DLQ redrive sau một compensation đã hoàn tất: không vô tình charge lại một order đã hủy.

### Spring-specific

1. `@EventListener` đồng bộ: lỗi có thể lan về publisher và callback giữ publisher thread.
2. `@Async @EventListener`: task in-memory mất khi process crash; không nhầm shutdown bình thường với abrupt kill.
3. `@TransactionalEventListener(AFTER_COMMIT)`: callback không chạy khi transaction rollback, nhưng vẫn có crash gap sau commit.
4. Spring Modulith registry: chỉ test durable/resubmission sau khi thật sự cài và cấu hình storage/registry.
5. Integration broker: chạy test với Kafka/RabbitMQ thực hoặc test container, kiểm tra ACK, retry, DLT/DLX, retention và redrive thật, không dựa vào mock in-memory.

**Quan trọng:** trong test, dùng `CountDownLatch`/Future có timeout để chờ async completion; không dùng `Thread.sleep` cố định để tuyên bố đã xử lý xong.

## 15. Những sai lầm thường gặp

| Nhận định sai | Rủi ro | Cách đúng |
| --- | --- | --- |
| “@EventListener đã là message queue” | Không có durable storage | Dùng outbox/broker khi cần |
| “publishEvent trả về = downstream đã xử lý” | Async callback/worker có thể chưa chạy | Phân biệt dispatch và business completion |
| “Thêm @Async sẽ không mất event” | Executor queue in-memory mất khi crash | Durable queue/outbox |
| “AFTER_COMMIT bảo đảm gửi message” | Crash gap sau commit còn tồn tại | Atomic outbox intent |
| “Lưu order rồi gửi Kafka ở method sau là atomic” | Dual-write inconsistency | Same-DB transaction outbox |
| “Broker gửi thành công thì consumer xử lý đúng một lần” | Redelivery/duplicate | Idempotent consumer/inbox |
| “Kafka exactly-once bao trùm mọi API bên ngoài” | Double-charge/email | Scope EOS rõ và external idempotency |
| “Outbox relay mark SENT trước khi publish cũng được” | Crash làm mất message | Chờ broker ACK, xử lý duplicate |
| “Một unique eventId toàn cục cho mọi consumers” | Chặn nhầm consumer khác | Khóa (consumer, eventId) |
| “Outbox không cần dọn” | Bảng tăng không giới hạn | Retention/cleanup/archive |
| “Dùng H2 in-memory là kiểm thử persistence” | Dữ liệu mất khi context/JVM dừng | H2 file DB hoặc DB thật |
| “Có Spring Modulith nghĩa mọi local event tự externalize” | Cấu hình sai, thiếu broker | Hiểu phạm vi registry/externalization |
| “DLQ tức event được khắc phục” | Backlog lặng lẽ tích tụ | Owner, runbook, alerts, redrive |
| “Retry tạo eventId mới mỗi lần” | Dedup không hiệu quả | Giữ ID original event |
| “Mọi event phải đưa ra broker” | Overengineering, tăng latency/coupling | Local invariants nên giữ trong service/tx |

## 16. Chọn phương án theo yêu cầu

| Yêu cầu thực tế | Giải pháp thường phù hợp |
| --- | --- |
| Phản ứng nhanh trong cùng ApplicationContext, không cần replay | `@EventListener` đồng bộ |
| Tác vụ phụ có thể mất khi process chết, không quyết định nghiệp vụ | `@Async @EventListener` với executor được quản trị |
| Side effect chỉ nên chạy sau commit nhưng không yêu cầu durable replay | `@TransactionalEventListener(AFTER_COMMIT)` |
| Thông báo phải sống qua restart, cùng ứng dụng modular monolith | Durable publication/outbox; cân nhắc Spring Modulith Registry |
| Integration event cho nhiều services, yêu cầu retry/replay | Transactional outbox + Kafka/RabbitMQ + idempotent consumer |
| Một job nội bộ phải chạy lại sau crash, không cần event fan-out | Durable job table + worker có lease/attempts |
| Business workflow nhiều bước cần bù khi thất bại | Saga/process manager + durable messages + compensation |
| Event sourcing/audit toàn bộ lịch sử | Event store chuyên dụng, thiết kế aggregate/version/replay riêng |

Không chọn giải pháp chỉ theo từ khóa “async” hay “event-driven”. Trước tiên viết rõ: **mất message có chấp nhận được không**, **có yêu cầu khôi phục sau crash không**, **ai ACK**, **duplicate được xử lý ra sao**, **business success được xác nhận khi nào**.

## 17. Checklist triển khai thực tế

1. Publisher và consumer ở cùng JVM hay khác service/process?
2. Nếu JVM chết sau DB commit, event intent còn ở đâu?
3. DB business và outbox có nằm **trong cùng transaction** không?
4. Có record event ID, aggregate ID, schema version, correlation ID không?
5. Relay dùng polling hay CDC? Claim/lease/offset được quản lý thế nào?
6. Khi broker publish thất bại, outbox có giữ message để retry không?
7. Nếu broker nhận nhưng ACK về relay bị mất, duplicate sẽ được xử lý ra sao?
8. Consumer ACK sau khi local transaction đã commit chưa?
9. External API có idempotency key/reconciliation không?
10. Retry/DLQ/redrive có giới hạn và runbook không?
11. Có metrics oldest pending, consumer lag, duplicate và business completion không?
12. Đã kiểm thử process crash, rollback, duplicate, out-of-order và schema upgrades chưa?

**Kết luận:** Spring Application Events phù hợp cho **decoupling nội bộ**, nhưng `ApplicationEventPublisher` không phải một hàng đợi bền vững. Listener đồng bộ không làm message sống qua crash; `@Async` chỉ chuyển việc sang thread khác; `@TransactionalEventListener` điều khiển thời điểm callback chứ không xóa crash gap. Khi tích hợp ngoài ứng dụng cần độ tin cậy, hãy **persist intent trong cùng transaction**, dùng **relay/broker**, hỗ trợ **at-least-once và idempotent consumer**, đồng thời vận hành retry, DLQ, redrive và metrics thực tế. Spring Modulith có thể bổ sung persistent event publication cho những use case phù hợp nhưng cần cấu hình riêng.

## Tài liệu chính thức và đọc thêm

- Spring Framework — ApplicationContext Events và default multicaster: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — ApplicationEventPublisher Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework — Async execution: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Modulith — Working with Application Events / Event Publication Registry: https://docs.spring.io/spring-modulith/reference/events.html
- Spring Kafka — Handling Exceptions, DefaultErrorHandler và DeadLetterPublishingRecoverer: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring AMQP — Messaging và listener containers: https://docs.spring.io/spring-amqp/reference/
