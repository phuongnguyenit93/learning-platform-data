# Kiểm thử restart với message đang chờ trong Spring Integration

## 1. Bài toán: restart khi Delayer chưa phát message

Một hệ thống nhận sự kiện `OrderCreated` và trì hoãn 30 phút trước khi gửi lời nhắc thanh toán. Lúc 09:00, Delayer tiếp nhận message của đơn `order-501` và lên lịch phát lúc 09:30. Ứng dụng được triển khai lại từ 09:10 đến 09:12.

Kiểm thử cần chứng minh:

1. Message đã nhận trước khi tiến trình cũ dừng **vẫn còn** sau restart.
2. Tiến trình mới có thể tìm lại đúng message và tiếp tục lịch đang chờ.
3. Deadline **vẫn là 09:30**, không tự đổi thành 09:42 chỉ vì khởi động lại lúc 09:12.
4. Khi ứng dụng dừng qua thời điểm hẹn (ví dụ 09:10–10:00), message quá hạn có cơ hội được xử lý sau recovery.
5. Không nhầm việc message đã được Delayer release với việc toàn bộ consumer đã hoàn thành tác động nghiệp vụ.

Đây là kiểm thử **khả năng phục hồi message còn chờ** của Enterprise Integration Pattern *Delayer*. Trong module **SPRING_INTEGRATION_PATTERN**, kết quả cần được đối chiếu với các nhánh Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation. Mục tiêu không chỉ là chứng minh ứng dụng khởi động lại được, mà là kiểm chứng **luồng thông điệp, trạng thái lưu trữ và kết quả nghiệp vụ** sau khi một tiến trình biến mất.

### Một test dùng cùng ApplicationContext chưa phải test restart

~~~java
input.send(message);
Thread.sleep(2_000);
assertNotNull(output.receive(0));
~~~

Đoạn trên chỉ chứng minh một message có thể được phát sau delay trong **một vòng đời ứng dụng**. Nó không kiểm tra message được lưu bền vững, scheduler được tái tạo hay tiến trình khác đọc lại dữ liệu.

Thay vào đó, test ít nhất phải có **hai vòng đời tách biệt**:

~~~mermaid
sequenceDiagram
    participant T as Test harness
    participant A as ApplicationContext A
    participant DB as Persistent MessageStore
    participant B as ApplicationContext B
    T->>A: Khởi tạo phiên A
    T->>A: Gửi eventId=evt-501, deadline=09:30
    A->>DB: Lưu pending message
    DB-->>T: Đọc được pending record
    T->>A: Đóng context A trước deadline
    Note over A: Scheduler A ngừng
    T->>B: Khởi tạo phiên B cùng DB/group ID
    B->>DB: Đọc pending message, phục hồi lịch
    Note over B: Đến deadline gốc
    B-->>T: Output có evt-501
    T->>DB: Xác minh trạng thái sau release
~~~

Hai `ApplicationContext` liên tiếp trong **cùng một JVM** là một bài kiểm thử tích hợp rất hữu ích. Tuy nhiên nó chưa chứng minh dữ liệu tồn tại qua việc **tắt toàn bộ JVM/host**; trường hợp đó cần test ở mức hai process/container khác nhau.

## 2. Điều kiện tối thiểu để recovery có ý nghĩa

Delayer dùng `TaskScheduler` để lập lịch phát. Với delay dương, message đang chờ được quản lý bởi một `MessageGroupStore`. Nếu dùng store trong RAM, dữ liệu sẽ mất khi tiến trình bị hủy. Với nhu cầu giữ message qua restart, cấu hình một store **bền vững** như `JdbcMessageStore` và dùng database sống độc lập với context/tiến trình được restart.

| Thành phần | Trong test restart phải làm gì? | Sai lầm cần tránh |
| --- | --- | --- |
| `MessageGroupStore` | Cùng một DB bền vững giữa A và B | Tạo lại `SimpleMessageStore` hoặc H2 in-memory mất dữ liệu |
| `messageGroupId` | Giữ chuỗi ID ổn định giữa A và B | Đổi ID theo build/release khiến nhóm cũ không được tìm lại |
| Payload và headers | Có thể serialize/deserialize qua phiên bản | Chỉ dùng object RAM hoặc thay tên class không tương thích |
| Deadline | Lưu thời điểm gốc, so sánh với mốc phát thực tế | Tính lại toàn bộ delay lúc startup |
| `TaskScheduler` | Scheduler của A dừng; B khởi tạo và phục hồi lịch | Để A còn chạy rồi tuyên bố B đã recover |
| Output channel | Probe riêng cho B, kiểm tra đúng `eventId` | Nhận message từ queue của A thay vì B |
| Transaction | Kiểm tra pending message đã **commit** | Thấy dữ liệu chưa commit trên chính connection của producer |
| Consumer | Có chính sách retry/idempotency phù hợp | Kết luận exactly-once chỉ vì output nhận một lần |

**Điểm cần phân biệt:** `messageGroupId` là ID nhóm message chờ trong một Delayer; `MessageHeaders.ID` định danh một đối tượng `Message`; `correlationId` liên kết các phần của cùng workflow; còn `eventId` nên là khóa nghiệp vụ bền vững để đối soát và chống xử lý trùng.

### Chọn delay tương đối hay thời gian tuyệt đối?

| Cấu hình | Ý nghĩa | Điều cần kiểm tra sau restart |
| --- | --- | --- |
| `delayExpression("headers['delayMs']")` trả `Long` | Khoảng chờ tương đối tính từ lúc Delayer nhận message | Không bắt đầu đếm lại đầy đủ từ startup nếu dữ liệu lịch gốc được phục hồi |
| `delayExpression("headers['releaseAt']")` trả `Date` | Thời điểm phát tuyệt đối | Giữ đúng một mốc `Instant` đã định |
| `defaultDelay(10_000L)` | Giá trị thay thế khi không có delay được xác định | Không dùng fallback vô tình khi deadline bị thiếu/hỏng |

Trong các test dưới đây, ta chọn **`Date` tuyệt đối** để deadline dễ quan sát, không phụ thuộc diễn giải lại khoảng chờ tương đối. Một test bổ sung sẽ kiểm tra trường hợp delay số `Long`.

## 3. Chiến lược kiểm thử theo cấp độ

Không nên dùng duy nhất một bài test lớn cho tất cả lỗi. Chia thành các tầng:

| Tầng | Mục tiêu | Công cụ/tiêu chí |
| --- | --- | --- |
| Unit | Chuyển ngày giờ nghiệp vụ thành deadline đúng | `Clock` inject được, `Instant`, assertions thuần |
| Integration một context | Delayer có lưu pending và phát khi đến hạn | `MessageGroupStore`, `PollableChannel.receive(timeout)` |
| Integration hai context | A đóng, B mở lại cùng DB và group | Kiểm chứng pending trước restart, release ở B |
| Process restart | JVM/container A bị kill, JVM/container B đọc DB | Hai process riêng, DB ngoài vòng đời A |
| Failure injection | DB lỗi, crash khi release, consumer lỗi | Fault injection, retry/error channel, đối soát |
| Multi-instance | Hai phiên cùng thấy pending message | Kiểm tra ownership/race, idempotency |

**Nguyên tắc test bất đồng bộ:** đợi **message hoặc trạng thái thực** với timeout có giới hạn, không đoán rằng “ngủ 2 giây chắc đã phục hồi”. Với test **downtime vượt deadline**, đợi đến đúng điều kiện thời gian bằng một công cụ polling/clock phù hợp, không dùng sleep tùy ý không gắn với điều kiện.

## 4. Chuẩn bị môi trường PostgreSQL bên ngoài vòng đời ứng dụng

Ví dụ dùng PostgreSQL vì `JdbcMessageStore` có thể lưu message trên database và Spring Integration cung cấp schema JDBC tương ứng. Trong test JVM restart, container database phải sống **qua cả A và B**.

Các dependency điển hình trong ứng dụng Spring Boot, ngoài dependency quản lý versions tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tùy thế hệ Testcontainers hoặc BOM được dự án sử dụng, artifact coordinates và version có thể khác; hãy dùng dependency đã được dự án quản lý. Đối với PostgreSQL, schema phải có các bảng/constraint mà `JdbcMessageStore` yêu cầu. Trong test có thể chạy script `org/springframework/integration/jdbc/schema-postgresql.sql` từ dependency Spring Integration JDBC **phù hợp cùng phiên bản**.

Ví dụ chuẩn bị DB trong JUnit (phần khởi tạo của bài test):

~~~java
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeAll;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class PendingMessageRestartIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    static DataSource database;

    @BeforeAll
    static void prepareSchema() {
        database = new DriverManagerDataSource(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword());

        var schema = new ResourceDatabasePopulator(
                new ClassPathResource(
                        "org/springframework/integration/jdbc/schema-postgresql.sql"));
        schema.execute(database);
    }

    // Phần cấu hình flow và phương thức @Test xuất hiện bên dưới.
}
~~~

**Lưu ý vận hành test:** `@Container` static giữ PostgreSQL sống suốt vòng đời test class, trong khi `ApplicationContext A` và `B` sẽ được tạo/đóng riêng. Nếu A và B cùng dùng `jdbc:h2:mem:...`, dữ liệu có thể mất khi connection/context bị đóng; đó không phải phép thử đáng tin cho restart qua JVM.

## 5. Cấu hình Spring Integration cho phép khôi phục message

Một config tối thiểu dùng:

- `DirectChannel` làm đầu vào.
- `JdbcMessageStore` lưu message đang chờ.
- `messageGroupId` cố định và không chứa ID deployment.
- `delayExpression` nhận header `releaseAt` kiểu `Date`.
- `QueueChannel` riêng cho output của **mỗi context**, để test nhận và xác minh message do context B phát.
- Một probe ở sau Delayer ghi nhận **thời điểm release**; đây là dấu mốc tốt hơn việc đo lúc test thread nhận kết quả.

~~~java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class RestartDelayFlowConfig {

    public static final String GROUP = "billing.pending-reminder.delay.v1";

    @Bean
    public JdbcMessageStore delayedMessageStore(DataSource dataSource) {
        return new JdbcMessageStore(dataSource);
    }

    @Bean("restart.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean("restart.out")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public AtomicReference<Instant> releaseObservedAt() {
        return new AtomicReference<>();
    }

    @Bean
    public IntegrationFlow restartAwareDelayFlow(
            JdbcMessageStore store,
            AtomicReference<Instant> releaseObservedAt) {

        return IntegrationFlow.from("restart.in")
                .delay(d -> d
                        .messageGroupId(GROUP)
                        .messageStore(store)
                        .delayExpression("headers['releaseAt']")
                        .defaultDelay(10_000L))
                .handle(String.class, (payload, headers) -> {
                    releaseObservedAt.set(Instant.now());
                    return payload;
                })
                .channel("restart.out")
                .get();
    }
}
~~~

Điểm cần chú ý:

1. `JdbcMessageStore` dùng `DataSource` do bài test cung cấp. Đừng tạo database mới cho context B.
2. `GROUP` giống nhau trong hai context, nếu không message pending trong group cũ có thể không được reschedule.
3. Payload dùng `String` và headers dùng `Date`/`String` để dễ serialize qua restart.
4. `releaseObservedAt` là probe của **context đang chạy**. Nếu message xuất hiện trong output của B, timestamp ghi nhận ở B, không phải A.
5. Trong ứng dụng thực, output có thể đi tới broker hoặc consumer; `QueueChannel` dùng ở đây **chỉ để kiểm thử handoff** và không tự bền vững sau khi message rời Delayer.

## 6. Khởi tạo hai ApplicationContext dùng chung DataSource

Không dùng `@SpringJUnitConfig` cho một context duy nhất rồi thay đổi state để giả lập restart. Test có thể khởi tạo hai Spring context theo thứ tự:

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

static AnnotationConfigApplicationContext openApplication(DataSource database) {
    AnnotationConfigApplicationContext app =
            new AnnotationConfigApplicationContext();

    // Đăng ký cùng DataSource cho cả hai phiên.
    app.getBeanFactory().registerSingleton("dataSource", database);
    app.register(RestartDelayFlowConfig.class);
    app.refresh();
    return app;
}
~~~

Đây là method thêm vào class `PendingMessageRestartIT` ở mục 4. Nó tạo application context mới (bao gồm bean Delayer và scheduler mới) nhưng vẫn dùng cùng `DataSource` trỏ tới PostgreSQL Testcontainers.

**Về phiên bản:** quá trình startup của `DelayHandler` với persistent store có cơ chế reschedule pending messages. Không nên tự gọi `reschedulePersistedMessages()` nhiều lần trong test bình thường nếu không có yêu cầu quản trị rõ ràng; hãy kiểm tra hành vi startup của đúng phiên bản đang dùng. Nếu không thấy recovery, kiểm tra endpoint thực sự đã được khởi động, DB schema và group ID trước khi chỉnh mã.

## 7. Kịch bản chính: restart **trước deadline**

Yêu cầu test:

1. Context A nhận `eventId=restart-before-001` và lưu message vào JDBC store.
2. Trước deadline, test xác minh group chứa một message đang chờ.
3. Đóng A **trước deadline**, để scheduler A không còn tác vụ hoạt động.
4. Mở B với cùng store và group ID.
5. Đợi message ở output của B.
6. Kiểm tra đúng payload, `eventId`, thời điểm release không sớm hơn deadline ban đầu và pending group đã được giải phóng.

~~~mermaid
gantt
    title Một lịch giả định (giờ địa phương để minh họa)
    dateFormat HH:mm
    axisFormat %H:%M
    section Pending message
    Deadline ban đầu 09:30 :milestone, m1, 09:30, 0m
    section Ứng dụng
    Context A hoạt động :09:00, 10m
    Ứng dụng dừng :crit, 09:10, 2m
    Context B hoạt động :09:12, 18m
~~~

Trong code test, ta dùng `Instant` và `Date` để không phụ thuộc timezone mặc định của máy CI.

### JUnit tích hợp: A đóng, B nhận message

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

// Method đặt trong PendingMessageRestartIT (mục 4).
@Test
void restoresPendingMessageAcrossApplicationContexts() {
    // Date giữ độ phân giải mili giây: tránh so sánh lệch nano giây.
    Instant dueAt = Instant.now().plusSeconds(15)
            .truncatedTo(ChronoUnit.MILLIS);

    AnnotationConfigApplicationContext appA = openApplication(database);
    try {
        MessageChannel input =
                appA.getBean("restart.in", MessageChannel.class);

        assertTrue(input.send(
                MessageBuilder.withPayload("ORDER-501")
                        .setHeader("eventId", "restart-before-001")
                        .setHeader("correlationId", "order-501")
                        .setHeader("releaseAt", Date.from(dueAt))
                        .build()));

        JdbcMessageStore store = appA.getBean(JdbcMessageStore.class);
        assertEquals(1, store.getMessageGroup(
                RestartDelayFlowConfig.GROUP).size());
    } finally {
        appA.close();
    }

    assertTrue(Instant.now().isBefore(dueAt),
            "Context A phải đóng trước deadline; nếu CI quá chậm, " +
            "tăng khoảng thời gian test");

    AnnotationConfigApplicationContext appB = openApplication(database);
    try {
        PollableChannel output =
                appB.getBean("restart.out", PollableChannel.class);

        // receive(timeout) trả về ngay khi có message.
        Message<?> recovered = output.receive(20_000);
        assertNotNull(recovered, "Context B không release pending message");
        assertEquals("ORDER-501", recovered.getPayload());
        assertEquals("restart-before-001",
                recovered.getHeaders().get("eventId"));

        AtomicReference<Instant> releaseObservedAt =
                appB.getBean("releaseObservedAt", AtomicReference.class);
        assertNotNull(releaseObservedAt.get());
        assertFalse(releaseObservedAt.get().isBefore(dueAt),
                "Message không được phát sớm hơn deadline đã lưu");

        JdbcMessageStore store = appB.getBean(JdbcMessageStore.class);
        assertEquals(0, store.getMessageGroup(
                RestartDelayFlowConfig.GROUP).size());
    } finally {
        appB.close();
    }
}
~~~

**Phạm vi của code:** đây là các phần ghép thành một test class theo mục 4–7, không phải một file Java duy nhất được sao chép nguyên xi: cần đặt `@Test` vào class `PendingMessageRestartIT`, method `openApplication` trong class, và `RestartDelayFlowConfig` ở một class cấu hình riêng. Chạy trên PostgreSQL có schema đúng, với dependency và version tương thích.

### Vì sao cách assert này có ý nghĩa?

- `store.getMessageGroup(...).size() == 1` chứng minh có pending message **ở store** trước khi A đóng, không chỉ một task nằm trong RAM của scheduler.
- `appA.close()` dừng lifecycle của A; B có scheduler/endpoint mới.
- `output.receive(20_000)` là **event-driven waiting**, không chờ 15 giây một cách mù quáng.
- Probe `releaseObservedAt` đặt **trong flow phía sau Delayer** giúp biết thời điểm phát tại endpoint, thay vì timestamp lúc JUnit thread thức dậy.
- `size() == 0` sau release giúp phát hiện message không còn thuộc group đang chờ; không chứng minh consumer cuối cùng đã hoàn tất nghiệp vụ.

**Giới hạn timing:** nếu môi trường CI quá chậm, A có thể đóng **sau** deadline và test phải fail với thông báo tiền điều kiện thay vì cho rằng đang thử restart trước hạn. Hãy chọn deadline và timeout có dư. Không giảm độ tin cậy bằng cách thay điều kiện thành `Thread.sleep(...)`.

## 8. Kịch bản restart **sau deadline**

Trường hợp khác: A nhận lúc 09:00, deadline 09:30, A dừng lúc 09:10 và B chỉ khởi động lúc 10:00. Message đã **quá hạn** trong thời gian dừng.

~~~mermaid
flowchart TD
    A[A nhận message với dueAt cố định] --> B[DB commit pending message]
    B --> C[A dừng trước deadline]
    C --> D[Deadline trôi qua khi ứng dụng tắt]
    D --> E[B khởi động cùng MessageStore]
    E --> F[Reschedule/recover message quá hạn]
    F --> G[Release sau khi B hoạt động]
    G --> H{Điều kiện nghiệp vụ còn hợp lệ?}
    H -->|Có| I[Consumer xử lý]
    H -->|Không| J[Discard có audit]
~~~

Để tạo test:

1. Gửi message với `releaseAt = Instant.now().plusSeconds(5)` vào A; đóng A ngay sau khi xác nhận pending đã lưu.
2. Đợi đồng hồ vượt `releaseAt` bằng một **điều kiện rõ ràng**, ví dụ Awaitility `until(() -> !Instant.now().isBefore(releaseAt))`; không dùng sleep một khoảng tùy ý.
3. Mở B; đợi message ở output B bằng `receive(timeout)`.
4. Assert đúng `eventId` và chỉ phát sau khi B khởi động; không mong B đợi thêm 5 giây tính từ startup.
5. Nếu nghiệp vụ là gửi reminder, consumer phải kiểm tra lại trạng thái đơn hàng để tránh gửi lời nhắc khi khách đã thanh toán trong downtime.

Một phần minh họa chờ deadline có điều kiện:

~~~java
import java.time.Duration;
import java.time.Instant;
import static org.awaitility.Awaitility.await;

Instant releaseAt = Instant.now().plusSeconds(5);

// Sau khi A đóng và pending data đã commit:
await().atMost(Duration.ofSeconds(10))
        .until(() -> !Instant.now().isBefore(releaseAt));

// Bắt đầu ApplicationContext B rồi output.receive(timeout).
~~~

Đoạn này minh họa **test harness** cần thư viện Awaitility. Việc đợi deadline đi qua là có chủ đích cho case **overdue**; nó khác hẳn việc thêm `Thread.sleep(5000)` vào mọi test chỉ để “hy vọng” scheduler đã xử lý xong. Để chạy test nhanh, có thể dùng fake clock/scheduler ở **unit test** logic thời gian, nhưng integration test recovery thật vẫn cần kiểm tra lifecycle và scheduler thực.

## 9. Điều gì xảy ra nếu chỉ dùng store trong RAM?

Một **negative/control test** nên chứng minh ranh giới của cấu hình:

1. Dùng store bộ nhớ (ví dụ `SimpleMessageStore`) trong A, đặt delay đủ dài.
2. Xác minh message đang chờ trong store của A.
3. Đóng A; tạo B với **một store RAM mới**.
4. Kiểm tra B không có pending message đó.

Đừng chạy kiểu negative test này trên chính `JdbcMessageStore` vì dữ liệu đã commit phải được giữ lại. Đừng chỉ kiểm tra “không có output sau 100 ms” rồi kết luận message đã mất mãi mãi; hãy xác nhận **store mới thật sự rỗng** và không có publisher nào đang gửi lại cùng event.

**Bẫy thường gặp:** nếu A và B dùng chung một instance `SimpleMessageStore` trong cùng JVM, message có thể vẫn còn vì chính test giữ object sống qua restart. Điều này giả lập sai ranh giới tiến trình. Test cần tạo **hai instance store RAM độc lập**.

## 10. Transaction boundary: đọc từ DB đã commit

Khi dùng `JdbcMessageStore`, trạng thái “đã nhận message” và “đã được commit bền vững” có thể không trùng nhau nếu send nằm trong một transaction ngoài.

~~~mermaid
sequenceDiagram
    participant P as Producer transaction
    participant D as Delayer
    participant DB as Database
    participant R as Restart test
    P->>D: Gửi message
    D->>DB: Ghi pending trong transaction
    DB-->>P: Câu lệnh ghi thành công
    alt COMMIT
        P->>DB: COMMIT
        R->>DB: Query từ connection độc lập
        DB-->>R: Pending message tồn tại
    else ROLLBACK
        P->>DB: ROLLBACK
        R->>DB: Query từ connection độc lập
        DB-->>R: Không thấy pending message
    end
~~~

Trong test có `@Transactional` trên **chính method JUnit**, Spring Test có thể rollback cuối bài test. Nếu A và B thấy dữ liệu qua một transaction đang mở của test, đó chưa chứng minh message tồn tại sau commit. Cách an toàn hơn:

- Không bọc toàn bộ vòng đời A/B trong một transaction test tự rollback.
- Nếu producer cần local transaction, dùng `TransactionTemplate` hoặc service method `@Transactional` và **đợi transaction commit xong** trước khi đóng A.
- Xác minh pending từ **connection/transaction độc lập** sau commit.
- Kiểm tra trường hợp rollback: message không được phục hồi từ dữ liệu chưa commit.

Với flow Delayer, thời điểm đăng ký lịch và thời điểm transaction commit cần được kiểm tra theo phiên bản/cấu hình Spring Integration thực tế. Không dựa vào việc một SQL insert đã trả về mà suy rằng scheduler của B luôn đọc được bản ghi đó.

## 11. Kiểm thử restart ở mức **JVM/process** thật

Hai `ApplicationContext` trong một JVM là test tích hợp nhanh nhưng chưa chứng minh:

- Classloader, process, heap và scheduler **đều bị hủy**.
- Database không phụ thuộc connection của A.
- Dữ liệu vẫn đọc được sau khi JVM hoàn toàn biến mất.
- Config phiên bản B vẫn deserialize được payload/header của phiên bản A.

Để kiểm chứng end-to-end restart thật, hãy chạy **hai process độc lập** với một DB ngoài:

~~~text
Test harness / CI
 ├─ PostgreSQL (giữ chạy suốt bài test)
 ├─ Process A (writer app)
 │    ├─ START
 │    ├─ SEND eventId=restart-process-001, dueAt=UTC...
 │    ├─ REPORT persisted-and-committed
 │    └─ KILL / STOP trước deadline
 └─ Process B (reader app)
      ├─ START cùng database + group ID
      ├─ OBSERVE recovered pending message
      ├─ OBSERVE release sau deadline
      └─ REPORT eventId và trạng thái nghiệp vụ
~~~

### Runbook có thể tự động hóa

1. Khởi động PostgreSQL Testcontainers hoặc database test độc lập; tạo schema một lần.
2. Start process A với cấu hình connection, `messageGroupId` và serializer cố định.
3. Gửi một message có `eventId` duy nhất và deadline đủ xa; chờ **tín hiệu persisted-and-committed** được đọc từ DB.
4. Stop A có kiểm soát; test khác **kill -9/process termination** để mô phỏng crash thật. Test không được để process A sống tiếp.
5. Xác minh row pending vẫn tồn tại trong PostgreSQL khi A đã chết.
6. Khởi động process B từ cùng binary hoặc phiên bản mới; dùng cùng DB và group ID.
7. Đợi observable của B theo `eventId` với một timeout hữu hạn: output audit, consumer inbox, message broker hoặc test endpoint.
8. Xác minh deadline, số lần xử lý và kết quả trong durable store; cleanup test data/process sau khi xong.

**Không tự gọi `System.exit` trong JVM chạy test JUnit.** Chạy ứng dụng test như **process con** hoặc container riêng; harness có trách nhiệm terminate, chờ process kết thúc và thu thập log/status. Chỉ dùng kill mạnh trong môi trường test được cô lập.

## 12. Restart không chứng minh exactly-once: cửa sổ lỗi khi release

Persistence của Delayer giúp giữ **message còn chờ**. Khi message đến hạn và được phát ra đầu downstream, xảy ra một ranh giới mới:

~~~mermaid
flowchart LR
    A[Pending trong JDBC MessageStore] --> B["Release: chuyển ra output"]
    B --> C["Queue / Broker / Handler"]
    C --> D[Business side effect]
    D --> E[ACK / Ghi hoàn tất]
    B -. "Crash / Retry" .-> F[Duplicate risk]
    D -. "Crash trước ACK" .-> F
~~~

| Cửa sổ lỗi | Điều có thể xảy ra | Kiểm thử cần thêm |
| --- | --- | --- |
| A chết **trước khi ghi pending commit** | Không có dữ liệu chờ | Transaction rollback và producer retry/outbox |
| A chết **sau commit, trước deadline** | Dữ liệu còn trong store | B khôi phục và phát theo deadline gốc |
| B khởi động **sau deadline** | Message quá hạn | Recovery xử lý overdue có kiểm tra trạng thái nghiệp vụ |
| Message đã release vào `QueueChannel` RAM, B chết | Queue đầu ra có thể mất dữ liệu | Handoff bền vững riêng nếu cần |
| Broker đã ACK nhưng handler chưa ghi thành công | Trạng thái nghiệp vụ có thể chưa hoàn tất | Consumer ACK/transaction theo contract |
| Handler làm side effect xong, process chết trước xác nhận | Có thể xử lý lại | Inbox/idempotency theo `eventId` |
| Retry hoặc hai instance cùng phát | Duplicate | Unique constraint, idempotent receiver và fencing/ownership |
| Đổi serializer/payload class | Recovery không đọc được message | Compatibility/migration test qua hai phiên bản |

**Đừng tuyên bố exactly-once** vì test đã nhận đúng một message trong một lần chạy. Một test một lần hiếm khi kích hoạt các cửa sổ crash khó nhất; bảo đảm nghiệp vụ cần đến từ thiết kế idempotency và kiểm thử fault injection lặp lại.

### Consumer inbox tối thiểu

Ví dụ SQL ở database của consumer:

~~~sql
CREATE TABLE processed_event (
    event_id      varchar(128) PRIMARY KEY,
    processed_at  timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Consumer có thể insert `eventId` trong **cùng transaction** với thay đổi nghiệp vụ của nó; duplicate sẽ gặp unique conflict hoặc được bỏ qua theo cách xử lý cụ thể của database. Nếu consumer gọi dịch vụ ngoài không tham gia transaction, còn cần idempotency ở dịch vụ đích hoặc outbox/saga để quản lý side effect.

Đối với một reminder, `eventId=reminder:order-501:v1` cần ổn định kể cả khi Delayer release lại hoặc producer tái tạo một `Message` với UUID Spring khác.

## 13. Khi nào dùng `reschedulePersistedMessages()`?

`DelayHandler` cung cấp chức năng khôi phục/lên lịch lại persisted messages. Trong vòng đời ứng dụng bình thường, cấu hình đúng với persistent store cho phép endpoint phục hồi message khi startup. Một số tình huống quản trị có thể cần kích hoạt reschedule một cách chủ động.

Nhưng trong bài test restart:

- **Ưu tiên kiểm tra hành vi startup tự nhiên của B**, không gọi manual reschedule trước khi biết nó có hoạt động hay không.
- Nếu muốn test thao tác quản trị riêng, tạo một test khác; ghi rõ lúc gọi, số pending trước/sau và owner scheduler.
- Đừng gọi manual reschedule nhiều lần một cách tùy ý trên nhiều instance, vì có thể tạo cạnh tranh phát; phải hiểu concurrency/transaction của phiên bản dùng.
- Nếu retry release đã hết nhưng transaction rollback làm message **vẫn còn trong store**, không kết luận row pending có nghĩa chắc chắn còn tác vụ chạy; kiểm tra scheduling state và chính sách reschedule rõ ràng.

Một thao tác vận hành liên quan đến scheduling không nên được dùng làm “miếng vá” che lỗi cấu hình database/group ID trong integration test.

## 14. Kiểm thử nhiều instance: recovery có cạnh tranh không?

Trong môi trường scale-out, hai instance có thể cùng khởi động và cùng quan sát những message chờ trong shared store.

~~~mermaid
sequenceDiagram
    participant DB as Persistent Store
    participant B as Instance B
    participant C as Instance C
    participant I as Idempotent Consumer
    B->>DB: Đọc pending group
    C->>DB: Đọc pending group
    Note over B,C: Cả hai có thể thấy cùng eventId
    B->>I: Release evt-501
    C->>I: Release evt-501 (tình huống cạnh tranh)
    I->>I: Chỉ tạo side effect một lần theo eventId
~~~

**Chia sẻ `JdbcMessageStore` và group ID không tự chứng minh an toàn cho mọi chiến lược active-active.** Khả năng cùng schedule, claim, transaction và xóa message phụ thuộc implementation/cấu hình. Cần thiết kế owner, lock/lease hoặc cơ chế phân vùng phù hợp và bảo vệ **consumer** trước duplicate.

Test concurrency:

1. Cả B và C bắt đầu từ cùng một snapshot DB có pending message.
2. Start hai instance gần đồng thời bằng `CountDownLatch` ở harness.
3. Đợi đúng số `eventId` được **consumer chấp nhận**; đếm số lần xử lý và số duplicate bị từ chối.
4. Kiểm tra pending group cuối cùng, error logs và transaction failures.
5. Lặp nhiều lần với scheduler/tải khác nhau; không dựa vào một lần chạy thành công.

Nếu yêu cầu “chỉ một instance được quyền phát”, phải có cơ chế sở hữu có thể chứng minh, không chỉ hy vọng DB sẽ tự ngăn mọi race. Nếu thiết kế chấp nhận at-least-once, bài test cần chứng minh idempotent consumer vẫn giữ kết quả nghiệp vụ duy nhất.

## 15. Ma trận kiểm thử restart và failure injection

| Test case | Cấu hình/tình huống | Điều phải chứng minh |
| --- | --- | --- |
| Restart trước hạn | A đóng trước `dueAt`, B mở cùng DB | B thấy pending, phát không trước deadline gốc |
| Restart sau hạn | A đóng rồi downtime vượt `dueAt` | B xử lý overdue, không đợi lại toàn bộ delay |
| Restart ở RAM store | A/B có hai store RAM riêng | Không có khả năng recovery qua lifecycle mới |
| DB rollback | Pending write bị rollback | B không thấy message chưa commit |
| DB tạm lỗi lúc B startup | Store không truy cập được | Phát hiện lỗi/health/alert, không âm thầm bỏ backlog |
| Serializer không tương thích | A lưu payload/header B không giải mã được | Có error quan sát được và kế hoạch migration |
| Đổi `messageGroupId` | B dùng ID khác A | Phát hiện pending bị bỏ lại và kế hoạch xử lý group cũ |
| Restart khi handler lỗi | Release xảy ra nhưng handler ném exception | Retry/error channel và state của store đúng |
| Crash sau side effect | Consumer đã hành động nhưng chưa ACK | Idempotent inbox chặn tác động lặp |
| Two instances | B/C đọc cùng store | Định rõ quyền phát, kiểm chứng duplicate risk |
| Broker/output không bền vững | Message đã rời Delayer nhưng output chưa xử lý | Không tuyên bố Delayer store bảo vệ cả downstream |
| Scheduler bị chậm | Nhiều message cùng đến hạn | Đo release lag và backlog, không giả định deadline là SLA tuyệt đối |

### Từ trạng thái cuối để khoanh vùng lỗi

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| B không tìm thấy message pending | DB/schema cùng hay khác? `messageGroupId` có đổi? A đã commit chưa? |
| Message còn trong store nhưng không release | Delayer có start? Scheduler có task? Rescheduling có lỗi? |
| B release quá muộn | Downtime, scheduler pool, database, backlog và downstream chậm |
| Message được phát lại nhiều lần | Retry/recovery/concurrent instances, transaction và idempotency |
| B không deserialize được | Payload, header, Java class, serializer và schema version |
| Event đã release nhưng business chưa hoàn tất | Output channel/broker/consumer có lỗi hoặc chưa ACK |
| Integration test qua hai context pass, qua hai JVM fail | Dùng tài nguyên trong JVM, config/secret hoặc connection DB không thật sự độc lập |

## 16. Observability để kiểm chứng thay vì phỏng đoán

Một test có thể quan sát message qua `PollableChannel`, database và probe. Trong production cần thêm log/metric:

~~~text
flow=paymentReminder
delayGroup=billing.pending-reminder.delay.v1
eventId=reminder:order-501:v1
correlationId=order-501
receivedAt=2026-11-21T09:00:00Z
dueAt=2026-11-21T09:30:00Z
processInstance=deployment-B
recoveryAt=2026-11-21T09:12:00Z
releasedAt=2026-11-21T09:30:00.450Z
releaseLagMs=450
businessOutcome=SENT
~~~

Các trường này là **log do ứng dụng chủ động thiết kế**, không phải toàn bộ đều được Spring Integration tự sinh.

| Metric | Ý nghĩa |
| --- | --- |
| `pendingMessageCount` | Số message còn chờ trong group |
| `oldestPendingAge` | Tuổi của pending message lớn nhất |
| `overdueCount` | Số message có deadline trong quá khứ nhưng vẫn còn pending |
| `startupRecoveryDuration` | Thời gian từ lúc B start đến khi phục hồi lịch cần thiết |
| `releaseLagMs` | `releasedAt - dueAt`; có thể dương khi scheduler chậm |
| `releaseFailureCount` | Số lần phát ra downstream gặp lỗi |
| `duplicateSuppressedCount` | Số message trùng bị consumer idempotent chặn |
| `businessCompletedCount` | Tác động nghiệp vụ cuối cùng hoàn tất |

Trong test, **không đồng nhất** `pendingMessageCount == 0` với `businessCompletedCount == 1`. Message có thể đã rời Delayer, nhưng vẫn chờ ở queue/broker hoặc consumer đang retry. Đó là hai ranh giới xác nhận riêng biệt.

## 17. Chống flaky test: đợi điều kiện, không đợi tùy ý

### Không dùng `Thread.sleep(...)` chỉ vì “chắc sắp đến hạn”

| Kỹ thuật | Cách dùng trong bài |
| --- | --- |
| `PollableChannel.receive(timeout)` | Đợi message output của B |
| `MessageGroupStore.getMessageGroup(...).size()` | Kiểm tra pending ở store |
| Awaitility `untilAsserted(...)` | Đợi một điều kiện DB/health khi chạy relay bất đồng bộ |
| `CountDownLatch` | Điều phối điểm writer đã commit hoặc worker đã start |
| Probe `Instant.now()` tại release | Ghi thời điểm release ở thread endpoint, giảm sai lệch do JUnit thread |
| `Clock.fixed(...)` | Test phép tính deadline nghiệp vụ thuần, **không tự điều khiển TaskScheduler** |
| JUnit `@Timeout` | Chống bài test treo vô hạn |

### Các quy tắc cô lập test

- Dùng `eventId` riêng cho mỗi case và DB schema/namespace riêng hoặc cleanup có kiểm soát.
- Không để A còn chạy khi B bắt đầu nếu scenario cần restart **không chồng lấn**.
- Không đặt toàn bộ test trong `@Transactional` tự rollback rồi suy ra đã test persistence.
- Đợi context B thật sự `refresh()/start` xong trước khi bắt đầu nhận output; với message overdue, việc phát có thể xảy ra ngay trong startup nên output queue phải được tạo **trước** khi lifecycle chạy.
- Không dùng `QueueChannel` của A làm bằng chứng B đã recover.
- Đóng `ApplicationContext` và PostgreSQL container sau test; không giữ thread scheduler sống giữa các test.
- Với test timestamp, chọn timeout có dư cho CI và kiểm tra **không phát sớm** bằng probe ở endpoint; đừng assert phát “chính xác 15.000 ms”.
- Để chứng minh không có duplicate vĩnh viễn, dùng inbox/side-effect counter bền vững và kiểm soát toàn bộ nguồn phát, không chỉ một lần `receive(0) == null`.

## 18. Bài tập thực hành

1. Triển khai `RestartDelayFlowConfig` dùng `JdbcMessageStore` với PostgreSQL. Gửi message delay 15 giây trong A; đóng A và kiểm tra B phát đúng `eventId`.
2. Thay header `releaseAt` kiểu `Date` bằng `delayMs` kiểu `Long`. Kiểm chứng thời gian nhận ban đầu vẫn được tôn trọng sau restart.
3. Dừng A quá hạn bằng một điều kiện thời gian có kiểm soát. Xác minh B release message overdue sớm sau startup.
4. Đổi từ `JdbcMessageStore` sang store RAM và tạo B với store riêng. Giải thích sự khác biệt.
5. Đặt một transaction rollback sau khi gửi message vào Delayer. Kiểm tra store từ connection khác và kết quả B.
6. Chạy process A và B trong hai JVM/container khác nhau với DB chung; kill A trước hạn và đối chiếu pending row.
7. Đổi `messageGroupId` giữa hai phiên; phát hiện nhóm cũ còn message chưa được reschedule, đề xuất migration.
8. Cho B sử dụng class payload không còn tương thích với message A lưu; thiết kế migration/deserialize test.
9. Khi B release xong, giả lập consumer lỗi; kiểm tra error channel và cách retry/replay theo thiết kế.
10. Cho B và C cùng startup từ một store. Đếm số lần phát và số tác động nghiệp vụ thực sự nhờ consumer inbox.
11. Dùng một outbound `QueueChannel` RAM, tắt B sau release nhưng trước consumer poll. Giải thích vì sao Delayer store chưa đủ để giữ message này.
12. Thu thập `pendingMessageCount`, `overdueCount` và `releaseLagMs` khi restart với 100 message cùng deadline; xác định dấu hiệu scheduler backlog.
13. Thêm Filter sau Delayer để bỏ reminder nếu đơn hàng đã thanh toán trong downtime, rồi kiểm tra nhánh discard có audit.

### Câu hỏi tự kiểm tra

- Tại sao hai `ApplicationContext` nối tiếp nhau là cần thiết nhưng chưa đủ để chứng minh restart **toàn JVM**?
- Vì sao database và `messageGroupId` phải giữ ổn định giữa A và B?
- Vì sao đọc một row chưa commit không đủ để nói message sẽ tồn tại sau restart?
- Vì sao nên đo timestamp ở **endpoint release**, không chỉ ở JUnit thread?
- Restart sau deadline có khác gì restart trước deadline?
- Khi nào `reschedulePersistedMessages()` cần được xem xét và vì sao không nên gọi tùy ý?
- Vì sao một output `QueueChannel` đã nhận message chưa chứng minh consumer hoàn thành?
- Vì sao cần `eventId` ổn định và idempotent consumer trong các kịch bản crash/retry?
- Nếu hai instance cùng nhìn thấy message chờ, làm sao chứng minh không có tác động nghiệp vụ trùng?

## Tài liệu tham khảo

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): lưu message chờ, scheduler, reschedule persisted messages và thời điểm release.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): `MessageGroupStore` và lựa chọn store bền vững.
- [Spring Integration Reference — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): `JdbcMessageStore` và schema database.
- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html): kiểm thử flow và endpoint.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): lỗi khi release và xử lý bất đồng bộ.
- [Testcontainers for Java — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): database container trong integration tests.
- [Awaitility Documentation](https://github.com/awaitility/awaitility/wiki/Usage): đợi một điều kiện đến khi đúng hoặc hết timeout.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): phân biệt commit, rollback và dữ liệu nhìn thấy từ các transaction.
