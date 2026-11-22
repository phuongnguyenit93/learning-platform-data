# Persistence của delayed message trong Spring Integration

## 1. Vì sao Delayer cần lưu trữ bền vững?

**Delayer** là Enterprise Integration Pattern (EIP) trì hoãn việc chuyển message sang bước tiếp theo. Sau khi nhận message, nó tính thời điểm phát, giữ message đang chờ và sử dụng `TaskScheduler` để phát message khi đến hạn. Với delay dương, producer không phải giữ thread chờ đến hết thời gian.

Điều gì xảy ra nếu ứng dụng dừng trong lúc message còn chờ? Nếu dùng store trong bộ nhớ, message có thể biến mất cùng tiến trình. Khi dùng **persistent message store**, message được lưu ngoài tiến trình để Delayer có thể tìm lại và lên lịch phát sau khi ứng dụng khởi động.

Ví dụ một hệ thống thương mại điện tử:

- Lúc 09:00, nhận sự kiện `eventId=reminder-501` cần chờ 30 phút.
- Lúc 09:10, ứng dụng dừng để triển khai phiên bản mới.
- Lúc 09:12, ứng dụng chạy lại và tìm message đang chờ trong database.
- Nếu vận hành bình thường, message đủ điều kiện phát khoảng 09:30; nếu chỉ khởi động lại sau 09:30, message đã quá hạn có thể được phát trong quá trình phục hồi.

Trong module **SPRING_INTEGRATION_PATTERN**, persistence giúp thiết kế luồng message ít phụ thuộc khi kết hợp Delayer với Filter, Transformer, Router, Gateway, retry, error channel, correlation và các nhánh nghiệp vụ. Hệ thống cần phân biệt rõ **đã nhận để chờ**, **đã phát sang downstream** và **đã hoàn thành nghiệp vụ**.

> Persistence giúp khôi phục message còn chờ qua restart. Nó không tự bảo đảm exactly-once hoặc phát đúng từng mili giây, và cũng không ghi nhận thay kết quả nghiệp vụ của consumer.

## 2. SimpleMessageStore và JdbcMessageStore

| Tiêu chí | `SimpleMessageStore` | `JdbcMessageStore` |
| --- | --- | --- |
| Nơi lưu | Bộ nhớ JVM | Bảng dữ liệu trong database |
| Tắt tiến trình | Message còn chờ có thể mất | Message đã commit vẫn tồn tại |
| Thiết lập | Dễ, hợp cho demo/test | Cần `DataSource`, schema, quyền truy cập |
| Chi phí | Thấp | Có I/O, lock, transaction, độ trễ database |
| Restart | Không phục hồi dữ liệu chỉ nằm trong RAM | Có thể reschedule message đã lưu |
| Rủi ro | Mất message khi dừng | Lỗi database, serialization, schema, concurrency |
| Trường hợp dùng | Message có thể tạo lại | Reminder và các tác vụ chờ quan trọng |

Thông thường Delayer sử dụng `SimpleMessageStore` khi không cấu hình store riêng. Giá trị delay dài **không tự biến store bộ nhớ thành persistent store**. Nếu chấp nhận được phát lại sau restart và cần bảo toàn message, hãy cấu hình một `MessageGroupStore` bền vững phù hợp.

## 3. Cấu trúc lưu trữ và định danh

~~~mermaid
flowchart LR
    P[Producer] --> I[Input Channel]
    I --> D["DelayHandler<br/>messageGroupId=reminders.delay.v1"]
    D --> S[("JdbcMessageStore")]
    D --> T[TaskScheduler]
    S -. "Đọc message chờ" .-> D
    T --> R[Release khi đến hạn]
    D --> R
    R --> F{Filter: đơn còn chưa thanh toán?}
    F -->|Có| C[Consumer]
    F -->|Không| X[Bỏ qua có ghi nhận]
~~~

`DelayHandler` quản lý message chờ theo một **message group** trong `MessageGroupStore`. `TaskScheduler` chịu trách nhiệm gọi tác vụ khi đến hạn. Khi có persistence, dữ liệu trong store có thể được dùng để khôi phục lịch nếu tiến trình trước đó đã dừng.

| Định danh | Ví dụ | Vai trò |
| --- | --- | --- |
| `messageGroupId` | `billing.payment-reminders.delay.v1` | Khóa group đang chờ của Delayer trong store |
| `MessageHeaders.ID` | UUID | Định danh một instance message của Spring |
| `correlationId` | `order-501` | Theo dõi các message cùng đơn hàng/quy trình |
| `eventId` | `reminder:order-501:v1` | Định danh sự kiện logic để chống xử lý trùng |

Hai message của hai đơn hàng khác nhau có thể nằm trong cùng một `messageGroupId`. Group này **không phải** nhóm correlation của Aggregator, cũng không nên dùng làm khóa chống xử lý trùng của từng sự kiện.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as DelayHandler
    participant S as JDBC Message Store
    participant T as TaskScheduler
    participant C as Consumer
    P->>D: eventId=reminder-501, delay=30 phút
    D->>S: Lưu message vào group ổn định
    D->>T: Đặt lịch phát
    D-->>P: Trả quyền điều khiển
    Note over D,T: Ứng dụng có thể restart
    T->>D: Đến hạn
    D->>S: Đọc message đang chờ
    D->>C: Release message tới downstream
~~~

Sơ đồ thể hiện logic. Chi tiết thời điểm lấy/loại message khỏi store và rollback phụ thuộc transaction, channel, error handling và cấu hình thực tế; không suy ra bảo đảm exactly-once từ sơ đồ.

## 4. Cấu hình JdbcMessageStore trong Spring Integration Java DSL

Một ứng dụng Spring Boot dùng JDBC Message Store cần:

1. `spring-boot-starter-integration` cho flow và endpoint Spring Integration.
2. `spring-integration-jdbc` cho `JdbcMessageStore`.
3. `spring-boot-starter-jdbc` hoặc cấu hình JDBC tương đương, cùng JDBC driver của database.
4. `DataSource` có thể kết nối; các bảng JDBC Message Store đã được khởi tạo theo đúng phiên bản Spring Integration/database.

Không tự đoán cấu trúc bảng. Sử dụng schema SQL do Spring Integration JDBC cung cấp, áp dụng bằng Flyway, Liquibase hoặc quy trình quản lý DB đang dùng.

### 4.1. Tạo store và channel

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class PersistentReminderChannels {

    @Bean("delayedMessageStore")
    public JdbcMessageStore delayedMessageStore(DataSource dataSource) {
        return new JdbcMessageStore(dataSource);
    }

    @Bean("reminder.in")
    public MessageChannel reminderInput() {
        return new DirectChannel();
    }

    @Bean("reminder.ready")
    public PollableChannel reminderReady() {
        return new QueueChannel();
    }
}
~~~

Ở đây `JdbcMessageStore` nhận `DataSource` do ứng dụng cấu hình. Schema cần sẵn sàng **trước khi Delayer ghi/đọc message**. `QueueChannel` chỉ dùng để quan sát kết quả phát trong ví dụ: nó không bảo đảm dữ liệu đã phát vẫn bền vững sau restart, vì chính channel đầu ra còn dùng bộ nhớ.

### 4.2. Kết nối Delayer với store

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.store.JdbcMessageStore;

@Configuration
public class PersistentReminderFlow {

    @Bean
    public IntegrationFlow paymentReminderFlow(
            @Qualifier("delayedMessageStore") JdbcMessageStore store) {

        return IntegrationFlow.from("reminder.in")
                .delay(delayer -> delayer
                        .messageGroupId("billing.payment-reminders.delay.v1")
                        .messageStore(store)
                        .defaultDelay(30 * 60 * 1_000L)
                        .delayExpression("headers['delayMs']"))
                .channel("reminder.ready")
                .get();
    }
}
~~~

`defaultDelay(30 * 60 * 1_000L)` biểu thị 30 phút. Khi header `delayMs` hợp lệ, giá trị số được hiểu là mili giây và được ưu tiên; thiếu header thì dùng mặc định.

Hai cấu hình quan trọng nhất:

- `messageStore(store)` chọn kho lưu bền vững thay cho mặc định trong RAM.
- `messageGroupId("billing.payment-reminders.delay.v1")` đặt khóa **ổn định** để tiến trình mới tìm lại nhóm message của Delayer.

Nếu hai Delayer **logic khác nhau** dùng chung database, cần group ID khác nhau. Nếu thay đổi group ID qua deploy mà không di chuyển hoặc xử lý hết dữ liệu cũ, message đang chờ có thể bị bỏ lại trong group cũ.

### 4.3. Gửi message với identity nghiệp vụ

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean scheduleReminder(MessageChannel reminderInput) {
    return reminderInput.send(
            MessageBuilder.withPayload("order-501")
                    .setHeader("eventId", "reminder:order-501:v1")
                    .setHeader("correlationId", "order-501")
                    .setHeader("delayMs", 120_000L)
                    .build());
}
~~~

Đoạn ví dụ cần truyền bean `reminder.in` vào `reminderInput`. Giá trị String và Long đơn giản giảm nguy cơ serialization. `eventId` phải ổn định ngay cả khi cùng sự kiện được gửi lại thành một `Message` mới có UUID khác.

### 4.4. Cấu hình database

Ví dụ kết nối PostgreSQL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/integration
spring.datasource.username=integration_app
spring.datasource.password=provided-by-secret-management
~~~

Đây là cấu hình minh họa, không chứa thông tin xác thực thật. Trong thực tế, lấy username/password từ secret manager hoặc môi trường triển khai. Cấu hình DataSource **không thay thế** bước tạo schema JDBC Message Store.

Nếu dùng H2 URL `jdbc:h2:mem:...`, dữ liệu nằm trong bộ nhớ database và không tồn tại sau khi tiến trình dừng hẳn. Muốn kiểm tra persistence qua restart, phải giữ database nằm ngoài vòng đời tiến trình hoặc dùng một database trên đĩa phù hợp.

## 5. Khôi phục delayed message sau restart

Khi Delayer được khởi tạo với persistent store, các message còn tồn tại trong group có thể được đọc lại và **reschedule**. Nếu deadline đã qua lúc ứng dụng tắt, message có thể được phát sau khi quá trình phục hồi hoàn tất; hệ thống không thể phát đúng vào mốc thời gian đã trôi qua.

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng phiên bản A
    participant DB as JDBC Message Store
    participant B as Ứng dụng phiên bản B
    participant C as Consumer
    A->>DB: Ghi reminder-501 trước khi tắt
    Note over A: Dừng lúc 09:10
    Note over DB: Message đã commit vẫn còn
    B->>DB: Khởi động 09:12; đọc group ID ổn định
    DB-->>B: Message còn chờ
    B->>B: Khôi phục lịch đến hạn
    Note over B: Đến 09:30
    B->>C: Release reminder-501
~~~

Hành vi phục hồi cần giữ nguyên ý nghĩa thời gian chờ, không tự tính lại “thêm 30 phút” kể từ mỗi lần restart. Spring Integration hỗ trợ rescheduling delayed message trong store; khi sử dụng ở production, xác minh cơ chế của phiên bản triển khai và dữ liệu thời gian đã được lưu.

| Tình huống | Ví dụ | Điều cần xử lý |
| --- | --- | --- |
| Restart trước deadline | Nhận 09:00, dừng 09:10, chạy lại 09:12, hạn 09:30 | Message tiếp tục chờ đến hạn |
| Restart sau deadline | Nhận 09:00, dừng 09:10, chạy lại 10:00, hạn 09:30 | Message đã quá hạn, có thể phát ngay sau recovery |
| Restart nhiều lần | Dừng/chạy lại liên tiếp trước hạn | Không mất message đã commit, không nhân đôi tác động nghiệp vụ |

Với reminder, message đến hạn có thể trở nên **không còn cần thiết** nếu khách đã thanh toán. Hãy thêm Filter hoặc service check lại trạng thái sau Delayer, rồi quyết định gửi nhắc hay bỏ qua. Persistence giữ ý định xử lý; nó không “đóng băng” trạng thái nghiệp vụ.

## 6. Ba cấp độ bảo đảm cần phân biệt

~~~mermaid
flowchart LR
    A[Producer] --> B[Store đã commit]
    B --> C[Scheduler đến hạn]
    C --> D[Message được release]
    D --> E[Consumer tạo tác động]
    E --> F[Kết quả được xác nhận]
~~~

Một hệ thống bền vững cần phân biệt:

1. **Đã lưu:** message còn tồn tại trong store sau khi commit và restart.
2. **Đã release:** Delayer chuyển message sang output channel.
3. **Đã hoàn thành nghiệp vụ:** consumer/email/API/database xác nhận kết quả.

| Lỗi xảy ra lúc nào? | Rủi ro | Biện pháp |
| --- | --- | --- |
| Trước commit lưu message | Message chưa bền vững | Producer retry có kiểm soát, outbox, xác nhận |
| Sau commit nhưng trước khi lịch được chạy | Còn trong DB nhưng chưa phát | Startup rescheduling, giám sát backlog |
| Đang chuyển message sang downstream | Retry, rollback hoặc thất lạc tùy cấu hình | Transaction và error channel được kiểm thử |
| Sau khi consumer đã gửi email nhưng chưa ghi nhận xong | Có thể gửi lại cùng email | Consumer idempotent, inbox/outbox, idempotency key |

### Transaction không bao trùm mọi hệ thống

`JdbcMessageStore` có thể tham gia transaction JDBC khi được cấu hình đúng với `DataSource` và transaction manager. Nhưng email, REST API, hoặc broker ngoài database thường **không tự tham gia** giao dịch JDBC.

Giả sử email đã gửi thành công rồi ứng dụng crash: rollback transaction JDBC không thể thu hồi email. Khi khôi phục/retry, cùng `eventId` có thể đi qua consumer một lần nữa.

Vì vậy cần làm rõ ranh giới transaction của đường nhận và đường phát, đồng thời dùng idempotency cho các tác động bên ngoài. Store bền vững là **thành phần lưu message**, không phải một giải pháp exactly-once hoàn chỉnh.

## 7. Serialization và triển khai phiên bản mới

Delayed message có thể nằm trong database trong thời gian nâng cấp ứng dụng. Khi phiên bản mới khôi phục message cũ, hãy kiểm tra:

- Payload có thể được serialize/deserialize bởi cấu hình store đang dùng?
- Class Java được ghi trước đó có còn tồn tại, hoặc có cách chuyển đổi tương thích?
- Header có chứa reference tới object JVM như reply channel tạm thời, connection hay thread?
- Message có mang dữ liệu nghiệp vụ lỗi thời cần cập nhật khi xử lý?

Ví dụ nhẹ và tương đối dễ bảo trì:

~~~java
MessageBuilder.withPayload("order-501")
        .setHeader("eventId", "reminder:order-501:v1")
        .setHeader("correlationId", "order-501")
        .build();
~~~

Consumer tải lại trạng thái đơn hàng theo khóa `order-501` tại thời điểm release. Nếu cần DTO phức tạp, hãy thiết kế schema/version rõ ràng, kiểm tra serializer và thử nâng cấp thực tế với message đã lưu từ phiên bản cũ.

| Dữ liệu | Nguy cơ |
| --- | --- |
| `replyChannel` hoặc `errorChannel` trỏ tới object JVM | Sau restart reference có thể không hợp lệ |
| DTO Java đổi package/tên/shape | Không deserialize được message cũ |
| Header chứa object không serializable | Ghi store hoặc khôi phục lỗi |
| Snapshot trạng thái đơn hàng | Lỗi thời sau thời gian chờ dài |
| Chuỗi thời gian không ghi múi giờ | Deadline bị tính sai khi chuyển môi trường |

Gateway đồng bộ có thể timeout trước khi message được release. Với tác vụ kéo dài qua restart, nên xác nhận **đã tiếp nhận** trước rồi trả kết quả bất đồng bộ dựa trên `eventId` hoặc callback/broker có định danh bền vững.

## 8. Kiểm thử persistence qua restart

Một bài test chỉ đợi 3 giây trong cùng JVM chứng minh Delayer phát theo thời gian, **chưa chứng minh dữ liệu tồn tại sau restart**. Bài kiểm thử persistence cần hai application context/tiến trình riêng và **một database giữ nguyên dữ liệu**.

Quy trình kiểm thử:

1. Chuẩn bị database thử nghiệm với JDBC Message Store schema đúng phiên bản.
2. Khởi động `ApplicationContext A`, dùng `messageGroupId=billing.payment-reminders.delay.v1`.
3. Gửi message `eventId=restart-test-001` với delay dài hơn thời gian thực hiện test, ví dụ 30 giây.
4. Xác minh message đã được ghi/commit trong group tương ứng.
5. Đóng hoàn toàn context A **trước deadline**, đảm bảo scheduler cũ không chạy nữa.
6. Giữ database; khởi động context B cùng group ID, serializer và channel/consumer phù hợp.
7. Chờ sau deadline, xác minh context B release đúng `eventId`.
8. Xác minh message không còn chờ trong group và trạng thái tác động nghiệp vụ đúng theo chính sách.
9. Lặp lại với restart **sau deadline**, lỗi downstream và nhiều message đến hạn cùng lúc.

Nếu dùng Testcontainers, container database phải còn nguyên giữa A và B. H2 dạng `mem` trong cùng context không chứng minh ứng dụng chịu được dừng hẳn JVM.

Có thể kiểm tra snapshot của nhóm chờ bằng `MessageGroupStore`:

~~~java
import org.springframework.integration.store.MessageGroupStore;

int pending = messageGroupStore
        .getMessageGroup("billing.payment-reminders.delay.v1")
        .size();

System.out.println("Pending delayed messages: " + pending);
~~~

`pending` chỉ cho biết số message trong group ở **thời điểm đọc**, không đồng nghĩa consumer đã hoàn tất xử lý. Với test trên CI, cần tránh race khi scheduler sắp đến hạn.

### Ma trận kiểm thử failure mode

| Case | Điều kiện | Điều cần xác minh |
| --- | --- | --- |
| Restart sớm | Chưa đến hạn, message đã commit | Context mới tiếp tục chờ rồi release |
| Restart muộn | Deadline đã qua trong downtime | Xử lý overdue đúng chính sách |
| Ghi store thất bại | DB hết kết nối hoặc từ chối ghi | Lỗi được phát hiện, không báo nhận bền vững giả |
| Lỗi khôi phục | DB chưa sẵn sàng khi startup | Có cảnh báo, không âm thầm bỏ backlog |
| Lỗi downstream | Consumer ném exception | Retry, error channel và transaction theo thiết kế |
| Thay đổi DTO | Message lưu từ phiên bản cũ | Đọc được hoặc phát hiện lỗi tương thích |
| Hai instance | Cùng dùng store và group | Có kiểm soát cạnh tranh, tác động không bị nhân đôi |
| Producer gửi lặp `eventId` | Hai message khác UUID | Consumer xử lý idempotent |

## 9. Retry và error channel khi message đến hạn

Với delay dương, producer có thể rời endpoint trước khi downstream thực sự xử lý. Lỗi trong lần phát lại thường không thể trả trực tiếp về lời gọi `send()` ban đầu.

Delayer hỗ trợ các tùy chọn xử lý lỗi phát lại:

~~~java
.delay(delayer -> delayer
        .messageGroupId("billing.payment-reminders.delay.v1")
        .messageStore(store)
        .defaultDelay(60_000L)
        .maxAttempts(3)
        .retryDelay(1_000L)
        .delayedMessageErrorChannel("reminder.delay.errors"))
~~~

Đây là đoạn cấu hình thay thế cho `.delay(...)`, không phải flow độc lập. Khi sử dụng, cần khai báo channel `reminder.delay.errors` và một flow xử lý `ErrorMessage`, log/metric, cảnh báo, dead letter/quarantine nếu cần.

Một lỗi khi gửi email **sau khi email đã thực sự được gửi** có thể làm lần retry gửi trùng. Cần phân loại lỗi có thể thử lại, điều chỉnh `maxAttempts`/`retryDelay` và dùng idempotency key tại dịch vụ nhận.

Đặc biệt với transaction, khi đã hết số lần retry, message có thể không còn lịch tự động dù vẫn còn dữ liệu trong store. Cần kiểm thử hành vi khi transaction rollback, reschedule hoặc restart. Không xóa thủ công message chưa xử lý khi chưa biết tình trạng side effect.

## 10. Idempotency ở consumer

`MessageHeaders.ID` là ID của message do Spring tạo; một sự kiện được gửi lại có thể nhận UUID khác. Vì thế, dùng khóa nghiệp vụ ổn định:

~~~java
void handleReminder(String eventId, String orderId) {
    // Giả mã: việc claim cần atomic trên durable store.
    if (!idempotencyStore.tryClaim(eventId)) {
        return;
    }

    if (orderRepository.isUnpaid(orderId)) {
        reminderClient.send(eventId, orderId);
    }

    idempotencyStore.markCompleted(eventId);
}
~~~

**Đây là giả mã thiết kế, không phải implementation production hoàn chỉnh.** Nếu process crash sau `tryClaim` nhưng trước hoặc sau lời gọi API, cần lease/timeout, trạng thái `PROCESSING`/`COMPLETED`, retry, transaction và idempotency phía nhận để tránh kẹt message hay side effect lặp.

Không dedupe theo `messageGroupId`: một Delayer có thể giữ hàng nghìn sự kiện khác nhau trong cùng group. Cũng không mặc định dedupe theo `correlationId`: một đơn hàng có thể hợp lệ có nhiều reminder khác nhau.

## 11. Multi-instance và chia sẻ database

Nhiều instance cùng dùng `JdbcMessageStore` **không tự chứng minh mỗi message chỉ được release đúng một lần**. Các instance có thể cùng phát hiện message đang chờ và đặt lịch, cạnh tranh khi đến hạn hoặc xử lý lại sau restart.

| Kiến trúc | Điều cần thiết |
| --- | --- |
| Một instance sở hữu Delayer | Cơ chế leader/owner, health check và chuyển quyền |
| Nhiều instance chạy cùng một Delayer logic | Locking, transaction, duplicate detection được kiểm thử |
| Nhiều Delayer độc lập dùng chung store | Group ID riêng, không lấy nhầm message của nhau |
| Thay đổi group ID khi deploy | Drain/migration dữ liệu cũ trước khi bỏ ID trước đó |

Có thể xem xét leader election, distributed lock, partitioning hoặc một scheduler/broker hỗ trợ delayed delivery nếu bài toán phân tán phức tạp. `JdbcMessageStore` chủ yếu giải quyết **lưu trữ message**, còn quyền sở hữu lịch phát là quyết định kiến trúc.

Không đặt group ID theo số build tự sinh nếu vẫn cần khôi phục backlog của phiên bản trước. Với group cũ còn dữ liệu, việc đổi ID mà không migration có thể khiến ứng dụng mới không tìm lại message.

## 12. Giám sát, vận hành và xử lý sự cố

Các metric tối thiểu:

| Nhóm | Chỉ số | Cách sử dụng |
| --- | --- | --- |
| Backlog | `pendingCount`, tuổi message chờ lâu nhất | Phát hiện store tích tụ hoặc scheduler ngừng |
| Đúng hạn | `dueAt`, `releasedAt`, `releaseLagMs` | Đo thời gian release trễ so với deadline |
| Kết quả | `eventId`, `attempt`, `processedAt`, `outcome` | Phân biệt đã release và đã hoàn thành nghiệp vụ |

Một log ứng dụng có thể thiết kế như sau:

~~~text
flow=paymentReminderFlow
delayGroup=billing.payment-reminders.delay.v1
eventId=reminder:order-501:v1
correlationId=order-501
receivedAt=2026-11-21T09:00:00Z
dueAt=2026-11-21T09:30:00Z
releasedAt=2026-11-21T09:30:01.100Z
releaseLagMs=1100
outcome=RELEASED
~~~

Đây là log minh họa do **ứng dụng chủ động ghi**, không phải tất cả trường được Spring Integration tự cung cấp. Dùng thời gian UTC/`Instant` để thuận lợi khi theo dõi nhiều instance.

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Sau restart không thấy reminder | Store trong RAM, group ID đổi, chưa commit, kết nối DB sai |
| DB có message nhưng chưa được release | Scheduler, khởi động Delayer, recovery/rescheduling, transaction |
| Message đến muộn | Downtime, scheduler bận, database chậm |
| Khôi phục lỗi deserialize | Class DTO/schema/header không tương thích |
| Reminder gửi hai lần | Retry, hai instance cạnh tranh, source gửi lại; kiểm tra idempotency |
| DB lớn dần không giảm | Backlog dài, lỗi kéo dài, retention/cleanup chưa có chính sách |
| Gateway timeout | Reply được phát sau khi caller đã ngừng chờ |

**Không xóa trực tiếp các row JDBC Message Store đang hoạt động** chỉ vì backlog tăng. Phải xác định message đang chờ, transaction chưa kết thúc và kết quả nghiệp vụ trước khi thực hiện thao tác quản trị.

## 13. Chọn Delayer có persistence khi nào?

Phù hợp khi cần trì hoãn **từng message** trong một flow Spring Integration, muốn tồn tại qua restart và chấp nhận sai số phát có kiểm soát. Ví dụ:

- Nhắc thanh toán sau một khoảng thời gian, có kiểm tra trạng thái mới nhất khi release.
- Tạm giữ message trước khi chuyển đến đối tác theo chính sách nghiệp vụ.
- Phát một thông báo tại mốc `Date` trong tương lai.

Nên cân nhắc scheduler nghiệp vụ, workflow engine hoặc broker có cơ chế delayed delivery nếu có hàng triệu lịch dài ngày cần sửa/hủy linh hoạt, có lịch định kỳ phức tạp hoặc cần khả năng điều phối phân tán riêng. Delayer cũng không thay thế rate limiter, vì nhiều message cùng có deadline có thể đồng thời làm tăng tải ở downstream.

## 14. Bài tập thực hành và câu hỏi tự kiểm tra

1. Cấu hình `JdbcMessageStore` trên một database thử nghiệm và chứng minh message delay 30 giây vẫn tồn tại sau khi dừng hẳn ứng dụng.
2. Restart trước deadline và sau deadline. So sánh `dueAt` với `releasedAt`, kiểm tra policy đối với message quá hạn.
3. Cấu hình hai Delayer độc lập dùng cùng store nhưng khác `messageGroupId`; quan sát backlog của từng group.
4. Đổi group ID trong một phiên bản thử nghiệm khi còn dữ liệu, rồi đề xuất kế hoạch migration không bỏ rơi message.
5. Ghi payload bằng phiên bản A rồi đổi class ở phiên bản B. Kiểm tra lỗi deserialize và đề xuất schema versioning.
6. Giả lập consumer gọi API thành công nhưng timeout khi nhận response. Giải thích vì sao JDBC transaction không ngăn được duplicate.
7. Chạy hai instance cùng một group và database, kiểm tra hành vi khi đồng thời restart và thiết kế idempotency theo `eventId`.
8. Xây metrics `pendingCount`, `releaseLagMs`, số lượng retry, rồi đặt cảnh báo khi backlog vượt SLA.

**Tự kiểm tra:** `MessageGroupStore` khác `TaskScheduler` ở điểm nào? Vì sao group ID cần ổn định? Lúc nào message được coi là đã lưu bền vững? Vì sao không thể coi `send() == true` là nghiệp vụ hoàn tất? Vì sao test restart phải giữ database qua hai tiến trình? Cần kiểm tra gì trước khi gửi một reminder đã bị quá hạn?

## Tài liệu tham khảo

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): `messageGroupId`, delayed message, persistence và khôi phục lịch.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): `MessageGroupStore` và các store lưu trữ bền vững.
- [Spring Integration Reference — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): tích hợp JDBC và schema lưu trữ.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): error channel và xử lý lỗi bất đồng bộ.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): chiến lược xử lý message gửi lại.
