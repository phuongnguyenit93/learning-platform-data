# Restart khi message đang chờ trong Spring Integration Delayer

## 1. Một message đang chờ sẽ ra sao nếu ứng dụng restart?

Trong Spring Integration, **Delayer** là endpoint của Enterprise Integration Patterns (EIP) cho phép trì hoãn việc chuyển từng message tới bước kế tiếp. Khi delay dương, `DelayHandler` giữ message trong một `MessageGroupStore` và dùng `TaskScheduler` để lên lịch phát sau khoảng chờ.

Ví dụ dịch vụ bán hàng nhận sự kiện tạo đơn lúc **09:00** và cần gửi lời nhắc thanh toán sau **30 phút**. Đến 09:10, ứng dụng bắt đầu triển khai phiên bản mới. Hệ thống cần trả lời:

- Message còn chờ có tồn tại sau khi tiến trình cũ dừng không?
- Khi phiên bản mới chạy, deadline vẫn là 09:30 hay bị tính lại thành 09:42?
- Nếu ứng dụng chỉ khởi động lại lúc 10:00, message quá hạn được xử lý thế nào?
- Nếu message từng được phát đến consumer ngay trước khi tiến trình chết, có nguy cơ xử lý lặp không?
- Nếu hai instance khởi động cùng lúc và nhìn thấy cùng message, bên nào được phát?

Đây là vấn đề **restart recovery**, bao gồm lưu trữ, thời gian, khởi tạo flow, nhận diện message, ranh giới giao dịch và hành vi consumer. Trong module **SPRING_INTEGRATION_PATTERN**, nó gắn với việc xây dựng các luồng ít phụ thuộc bằng Filter, Router, Transformer, Gateway, retry, error channel và correlation, đồng thời kiểm thử và giám sát các nhánh xử lý.

**Mục tiêu bài này:** thiết kế và kiểm chứng được chu kỳ **nhận → chờ → dừng → khởi động lại → phát** của một message, kể cả khi downtime kéo dài qua thời điểm hẹn.

## 2. Ba mốc thời gian phải theo dõi

| Mốc | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `receivedAt` | Thời điểm Delayer nhận message lần đầu | 09:00 |
| `dueAt` | Thời điểm message đủ điều kiện được phát | 09:30 |
| `releasedAt` | Thời điểm thực tế message đến đầu ra sau Delayer | 09:30:01 hoặc muộn hơn |

Với delay tương đối 30 phút:

\[
\text{dueAt} = \text{receivedAt} + \text{delayMs}
\]

Với delay tuyệt đối được truyền dưới dạng `java.util.Date`, `dueAt` chính là mốc thời gian mà message yêu cầu.

**Restart không nên tự kéo dài deadline của một message đang chờ.** Khi sử dụng persistent store, Spring Integration có cơ chế khôi phục lịch từ dữ liệu message đã lưu. Cách diễn giải thời gian của ứng dụng và cách lưu header cần được kiểm chứng với phiên bản Spring Integration đang triển khai, nhất là khi thay đổi cấu hình hoặc serializer.

~~~mermaid
gantt
    title Ví dụ restart trước khi hết thời gian
    dateFormat HH:mm
    axisFormat %H:%M
    section Message
    Chờ đến hạn                 :active, 09:00, 30m
    section Ứng dụng
    Phiên bản A hoạt động      :09:00, 10m
    Dừng để triển khai          :crit, 09:10, 2m
    Phiên bản B hoạt động       :09:12, 18m
~~~

Sơ đồ biểu thị một lịch giả định. Mốc phát thực tế còn phụ thuộc thời gian khởi động, scheduler và consumer.

## 3. Restart với store trong bộ nhớ và store bền vững

| Tình huống | `SimpleMessageStore` trong JVM | `JdbcMessageStore` với DB bền vững |
| --- | --- | --- |
| Message chưa đến hạn, tiến trình bị tắt | Có nguy cơ mất message và lịch | Message đã ghi/commit có thể còn trong DB |
| Khởi động tiến trình mới | Không có dữ liệu RAM của tiến trình cũ | Delayer có thể đọc group chờ và lên lịch lại |
| Downtime vượt deadline | Không có message để khôi phục nếu RAM đã mất | Có thể phát message quá hạn sau khi startup |
| Gặp lỗi serialize payload | Không bị ràng buộc lưu ngoài tiến trình như JDBC | Có thể không ghi/đọc được message |
| Hai instance cùng truy cập | Mỗi instance có bộ nhớ riêng | Cần đánh giá cạnh tranh, khóa và idempotency |

**Điều kiện cần để phục hồi:** message còn chờ phải nằm trong một store tồn tại độc lập với tiến trình bị dừng. Việc chỉ cấu hình `defaultDelay(30_000L)` không cung cấp persistence. Thay `QueueChannel` đầu ra bằng database cũng không giải quyết yêu cầu lưu message **trước thời điểm phát** nếu Delayer vẫn giữ pending message trong RAM.

### Vòng đời ở hai tiến trình

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant A as Delayer A
    participant DB as Persistent MessageStore
    participant B as Delayer B
    participant C as Consumer
    P->>A: eventId=reminder-501, chờ 30 phút
    A->>DB: Lưu message vào group
    Note over A: A dừng khi chưa đến hạn
    Note over DB: Message đã commit được giữ lại
    B->>DB: Khởi tạo với cùng messageGroupId
    DB-->>B: Các message còn chờ
    B->>B: Lên lịch lại theo deadline
    Note over B: Đến hạn hoặc đã quá hạn
    B->>C: Release message
~~~

Sơ đồ cho thấy mục đích của recovery. Thao tác ghi, loại khỏi group và retry có thể nằm trong những transaction khác nhau tùy cấu hình; từ sơ đồ này không thể kết luận mỗi tác động downstream chỉ xảy ra đúng một lần.

## 4. Những thứ phải giữ ổn định qua restart

Một lần triển khai mới có thể thay đổi tên bean, cấu trúc package, version ứng dụng và số instance. Với message đang chờ, cần đặc biệt chú ý:

| Thành phần | Yêu cầu |
| --- | --- |
| `messageGroupId` của Delayer | Giữ ổn định để phiên bản mới đọc đúng group chứa message chờ |
| `MessageGroupStore` | Cùng nguồn dữ liệu bền vững, cùng schema và thông tin kết nối |
| Serializer/payload | Phiên bản mới giải mã được message của phiên bản trước |
| Headers nghiệp vụ | Giữ `eventId`, `correlationId`, thông tin deadline cần thiết |
| Output channel/consumer | Vẫn có đích xử lý hợp lệ khi message được phát |
| Transaction/error handling | Có chính sách rõ ràng nếu phát thất bại sau restart |
| Đồng hồ và múi giờ | Dùng UTC/`Instant` khi trao đổi mốc tuyệt đối |

`messageGroupId` được đặt trong cấu hình của một Delayer, ví dụ `billing.reminders.delay.v1`. Nó là **khóa nhóm message đang chờ**, không phải ID của từng message hay từng đơn hàng. Đổi thành `billing.reminders.delay.v2` mà không có kế hoạch xử lý nhóm cũ có thể khiến message tồn tại trong DB nhưng không được flow mới khôi phục.

Mỗi sự kiện nên có **`eventId` bền vững** do nghiệp vụ tạo, ví dụ `reminder:order-501:payment:v1`. `MessageHeaders.ID` là UUID gắn với một instance message của Spring; khi một sự kiện được tạo lại thành message mới, UUID có thể khác. `correlationId` có thể nối các thông điệp cùng đơn hàng, còn `eventId` phục vụ nhận biết một hành động logic cụ thể.

## 5. Ví dụ Spring Integration Java DSL có thể khôi phục lịch

Ví dụ xây dựng flow đơn giản:

~~~text
reminder.in -> Delayer (JDBC store) -> reminder.ready
~~~

`reminder.ready` là `QueueChannel` dùng cho minh họa và kiểm thử; ứng dụng thực cần consumer xử lý message ở đầu ra và chiến lược xác nhận phù hợp.

Phụ thuộc cần có trong ứng dụng Spring Boot:

- `spring-boot-starter-integration`;
- `spring-integration-jdbc`;
- `spring-boot-starter-jdbc` cùng JDBC driver tương ứng;
- database và schema JDBC Message Store phù hợp với phiên bản Spring Integration.

### 5.1. Khai báo channel và persistent store

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
public class RestartAwareDelayChannels {

    @Bean("restartDelayedStore")
    public JdbcMessageStore restartDelayedStore(DataSource dataSource) {
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

`JdbcMessageStore` lưu message bằng `DataSource`. Chỉ có bean Java là chưa đủ: database phải còn tồn tại khi tiến trình tắt, và các bảng JDBC Message Store phải được tạo bằng schema tương thích. Dùng các script SQL đi kèm Spring Integration JDBC và quản lý migration bằng công cụ phù hợp như Flyway/Liquibase.

### 5.2. Đặt tên group cố định trong Delayer

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.store.JdbcMessageStore;

@Configuration
public class RestartAwareDelayFlow {

    public static final String DELAY_GROUP =
            "billing.reminders.delay.v1";

    @Bean
    public IntegrationFlow reminderDelayFlow(
            @Qualifier("restartDelayedStore") JdbcMessageStore store) {

        return IntegrationFlow.from("reminder.in")
                .delay(spec -> spec
                        .messageGroupId(DELAY_GROUP)
                        .messageStore(store)
                        .defaultDelay(60_000L)
                        .delayExpression("headers['delayMs']"))
                .channel("reminder.ready")
                .get();
    }
}
~~~

Trong ví dụ, giá trị mặc định là một phút. Header `delayMs` cho phép đặt độ trễ riêng từng message; nếu không có header, biểu thức trả về `null` và Delayer dùng `defaultDelay`. Thời gian kiểu số được hiểu là **mili giây**. Để gửi vào flow:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean scheduleReminder(MessageChannel input) {
    return input.send(MessageBuilder.withPayload("order-501")
            .setHeader("eventId", "reminder:order-501:payment:v1")
            .setHeader("correlationId", "order-501")
            .setHeader("delayMs", 120_000L)
            .build());
}
~~~

Tham số `input` phải nhận đúng bean `reminder.in`. Với delay dương, việc gửi thành công có nghĩa Delayer đã tiếp nhận và xử lý bước lên lịch theo ngữ cảnh hiện tại; nó **không chứng minh** reminder đã được gửi tới khách hoặc transaction business đã hoàn tất.

**Chú ý về ví dụ:** `QueueChannel` mặc định ở đầu ra không tự bền vững khi restart. Nếu yêu cầu bảo đảm cả message *đã release nhưng consumer chưa nhận*, phải thiết kế persistence/handoff của **đầu ra** hoặc consumer tương ứng, chẳng hạn broker hoặc outbox. Lưu ở Delayer chỉ giải quyết message còn nằm **trong giai đoạn chờ**.

## 6. Trường hợp restart trước deadline

Giả sử:

| Mốc | Hoạt động |
| --- | --- |
| 09:00 | Delayer A nhận message, delay 30 phút và lưu vào JDBC store |
| 09:10 | A dừng để nâng cấp, message chưa đến hạn |
| 09:12 | Delayer B khởi động cùng database và `messageGroupId` |
| 09:30 | Deadline ban đầu đến |
| 09:30:00.xxx | Message có thể được release khi scheduler thực thi |

Các điểm cần xác minh:

1. Message đã **commit vào DB** trước khi A dừng. Nếu giao dịch ghi chưa commit, không được giả định dữ liệu tồn tại.
2. B có cùng group ID và serializer tương thích nên tìm được message còn chờ.
3. B khôi phục lịch từ dữ liệu đã lưu. Nếu delay số được xử lý đúng theo thời điểm gốc, message không bị chờ thêm 30 phút kể từ khi B khởi động.
4. Consumer nhận đúng `eventId`. Không dùng UUID message làm bằng chứng duy nhất vì một sự kiện logic có thể được tái tạo trong quá trình xử lý.
5. Sau khi xử lý, trạng thái group không còn message chờ đó theo semantics của store/transaction được cấu hình.

Kiểm chứng không chỉ nhìn một dòng log "application started". Cần quan sát **đầu ra thực**, dữ liệu pending trong store và dấu vết sự kiện.

## 7. Trường hợp restart sau deadline

Nếu A nhận message lúc 09:00, đặt hạn 09:30, rồi dừng từ 09:10 đến 10:00, lúc B khởi động message đã **quá hạn**:

~~~mermaid
flowchart TD
    A[Startup B lúc 10:00] --> B[Đọc message pending]
    B --> C{Deadline đã qua?}
    C -->|Chưa| D[Đặt lịch theo hạn còn lại]
    C -->|Rồi| E[Đủ điều kiện phát ngay sau recovery]
    D --> F[Release đến downstream]
    E --> F
    F --> G{Đơn hàng còn cần nhắc?}
    G -->|Có| H[Gửi reminder]
    G -->|Không| I[Bỏ qua có ghi nhận]
~~~

Đối với reminder, một message quá hạn không nhất thiết nên tạo tác động ngay. Khách có thể đã thanh toán trong khi hệ thống dừng, hoặc hạn của chương trình khuyến mãi đã kết thúc. Đặt một **Filter hoặc Service Activator sau Delayer** để đọc trạng thái nghiệp vụ mới nhất, rồi quyết định gửi, bỏ qua hay chuyển sang nhánh xử lý thủ công.

Ví dụ logic business sau thời điểm release:

~~~java
// Minh họa xử lý nghiệp vụ, không phải mã tích hợp DB hoàn chỉnh.
public void afterRelease(String orderId, String eventId) {
    if (paymentRepository.isAlreadyPaid(orderId)) {
        auditService.recordSkipped(eventId, "ORDER_ALREADY_PAID");
        return;
    }
    reminderService.send(eventId, orderId);
}
~~~

Trạng thái đơn hàng và thao tác gửi có thể chạy song song với các tiến trình khác. Trong ứng dụng thực, cần cơ chế idempotency, transaction/outbox hoặc một hợp đồng nghiệp vụ để tránh race nếu vừa có thanh toán vừa có phát reminder.

## 8. Các cửa sổ lỗi khi dừng và khởi động lại

Sự cố có thể xảy ra ở nhiều vị trí:

~~~mermaid
flowchart LR
    A[Producer] --> B[Nhận vào Delayer]
    B --> C[Commit message chờ]
    C --> D[Lên lịch]
    D --> E[Release]
    E --> F[Consumer gây side effect]
    F --> G[Đánh dấu hoàn tất]
~~~

| Vị trí lỗi | Rủi ro | Hướng xử lý/kiểm chứng |
| --- | --- | --- |
| Trước khi ghi/commit message chờ | Message chưa có trong persistent store | Producer retry/outbox và xác nhận tiếp nhận đúng ngữ nghĩa |
| Đã commit nhưng chưa đăng ký lịch xong | Message có trong DB nhưng chưa có tác vụ chạy | Startup recovery/reschedule phải tìm được pending message |
| Sau khi đăng ký lịch, trước deadline | Scheduler mất theo tiến trình cũ | Lịch phải được khôi phục từ store bền vững |
| Trong lúc release xuống output channel | Transaction có thể rollback hoặc handler có thể retry | Kiểm thử lỗi downstream, chính sách retry và error channel |
| Sau khi consumer tạo side effect nhưng trước xác nhận | Có thể xử lý lặp sau retry/recovery | Idempotent consumer, inbox/outbox, khóa `eventId` ổn định |
| Sau release vào hàng đợi RAM, trước khi consumer lấy | Message đã rời Delayer nhưng đầu ra chưa bền vững | Thiết kế handoff bền vững ở downstream khi cần |

`JdbcMessageStore` giúp lưu message còn chờ, nhưng JDBC transaction **không rollback được** một email đã gửi hoặc một HTTP request đã thành công. Cần tránh kết luận “đã có database là exactly-once”.

### Cách thiết kế idempotent consumer

~~~java
// Pseudocode: claim phải atomic trên một durable store.
void handleReminder(String eventId, String orderId) {
    if (!idempotencyStore.tryClaim(eventId)) {
        return;
    }

    if (orderRepository.isUnpaid(orderId)) {
        reminderClient.sendWithIdempotencyKey(eventId, orderId);
    }

    idempotencyStore.markCompleted(eventId);
}
~~~

Đây là **giả mã**, chưa xử lý toàn bộ lỗi production. Nếu tiến trình chết sau `tryClaim` nhưng trước `markCompleted`, sự kiện có thể bị kẹt hoặc side effect bị lặp. Một thiết kế hoàn chỉnh cần trạng thái `PROCESSING/COMPLETED`, lease, retry, transaction và sự hỗ trợ idempotency ở dịch vụ đích khi có thể.

## 9. Quy trình restart an toàn khi triển khai

Một runbook đơn giản cho hệ thống có Delayer và message chờ quan trọng:

1. **Kiểm tra trước deploy:** xác nhận database và schema hoạt động, kiểm tra backlog theo `messageGroupId`, tuổi pending message và lỗi gần nhất. Đảm bảo phiên bản mới vẫn đọc được payload/header lưu từ phiên bản cũ.
2. **Xác định quyền sở hữu lịch:** với nhiều instance, biết rõ instance nào được phép reschedule/release. Nếu cơ chế phân tán chưa được chứng minh, chọn cách vận hành chỉ một owner tại một thời điểm.
3. **Dừng nhận mới có kiểm soát:** tùy kiến trúc, ngừng producer hoặc ngắt đầu vào của flow để hạn chế message được nhận trong lúc chuyển đổi.
4. **Dừng phiên bản cũ:** để nó hoàn thành hoặc ghi nhận các tác vụ đang diễn ra theo quy tắc của ứng dụng; đừng giả định shutdown sẽ đợi mọi deadline dài hàng giờ.
5. **Khởi động phiên bản mới:** dùng cùng group ID và persistent database, kiểm tra migration, serializer và health của `TaskScheduler`.
6. **Kiểm tra recovery:** so sánh pending count, message quá hạn, các lần release và log lỗi. Với message quá hạn, kiểm tra chính sách nghiệp vụ trước khi tạo side effect.
7. **Mở lại đầu vào:** sau khi xác nhận flow khôi phục được lịch và consumer hoạt động, quan sát backlog đến khi trở về mức bình thường.

Đây là quy trình tham khảo; thao tác dừng nhận và chuyển owner phụ thuộc khả năng vận hành của ứng dụng. Nếu sử dụng rolling deployment để phiên bản A và B hoạt động đồng thời, phải kiểm tra nguy cơ cả hai cùng phát một message. Chia sẻ database và `messageGroupId` **không tự cung cấp bảo đảm phân phối lịch duy nhất**.

### Đổi group ID là một thay đổi dữ liệu

Khi nâng cấp từ `billing.reminders.delay.v1` sang `...v2`, message cũ vẫn mang khóa nhóm cũ. Phải có kế hoạch: cho group cũ chạy hết, chủ động chuyển dữ liệu/lịch với quy trình được kiểm soát, hoặc duy trì một flow tương thích chuyên xử lý group cũ. Không đổi chuỗi group ID theo build number ngẫu nhiên mỗi lần triển khai.

## 10. Kiểm thử restart thật sự với hai ApplicationContext

Một test chỉ dùng `Thread.sleep(3000)` trong một context chứng minh delay hoạt động, **chưa chứng minh phục hồi sau restart**. Cần tạo hai vòng đời ứng dụng tách biệt và dùng **cùng database bền vững**.

### Quy trình kiểm thử

1. Khởi tạo database thử nghiệm (PostgreSQL/Testcontainers hoặc H2 file) cùng schema JDBC Message Store.
2. Tạo `ApplicationContext A` với cấu hình ở mục 5, gửi một message có `eventId=restart-test-001` và delay đủ dài, ví dụ 15 giây.
3. Đợi thao tác ghi store hoàn tất, rồi kiểm tra message đang thuộc `billing.reminders.delay.v1`.
4. **Đóng hoàn toàn context A trước deadline.** Kiểm tra scheduler của A đã ngừng.
5. Khởi tạo `ApplicationContext B` với cùng database, group ID và cấu hình message serialization.
6. Chờ deadline ban đầu qua, nhận message từ output `reminder.ready` của B.
7. Kiểm tra `eventId` và payload đúng, thời điểm phát không sớm hơn deadline ban đầu.
8. Đọc lại message group để biết còn pending hay không và kiểm tra kết quả xử lý nghiệp vụ.

Một đoạn test harness mô tả cách mở/đóng hai context, với giả định `dataSourceForSameDatabase()` cung cấp kết nối đến **cùng database bền vững** trong suốt test:

~~~java
// Pseudocode tích hợp: cấu hình DataSource/schema và quản lý thời gian
// phải được triển khai riêng trong test thực tế.
var contextA = startContext(dataSourceForSameDatabase());

try {
    MessageChannel input = contextA.getBean(
            "reminder.in", MessageChannel.class);
    input.send(MessageBuilder.withPayload("order-501")
            .setHeader("eventId", "restart-test-001")
            .setHeader("delayMs", 15_000L)
            .build());

    assertPendingInStore(contextA, "billing.reminders.delay.v1", 1);
} finally {
    contextA.close(); // Đóng trước thời hạn phát.
}

var contextB = startContext(dataSourceForSameDatabase());
try {
    PollableChannel output = contextB.getBean(
            "reminder.ready", PollableChannel.class);
    Message<?> restored = output.receive(20_000);
    assertNotNull(restored);
    assertEquals("restart-test-001",
            restored.getHeaders().get("eventId"));
} finally {
    contextB.close();
}
~~~

Đoạn trên là **pseudocode** nhằm nêu thứ tự kiểm thử, chưa phải class JUnit chạy độc lập; cần định nghĩa `startContext`, hàm chờ dữ liệu đã commit, schema, assertions và xử lý thời điểm. Trong test thật, cân nhắc đồng hồ/scheduler có thể điều khiển để giảm flakiness, đồng thời xác minh context B sử dụng database bên ngoài vòng đời của context A.

### Ma trận kiểm thử quan trọng

| Test case | Thiết lập | Tiêu chí cần chứng minh |
| --- | --- | --- |
| Restart trước hạn | Dừng A khi còn thời gian chờ | B phát theo deadline gốc |
| Restart sau hạn | Dừng qua deadline | Message được xử lý theo chính sách overdue |
| Message store không bền vững | Dùng RAM store rồi dừng JVM | Thấy rõ giới hạn không có recovery |
| DB lỗi lúc ghi | Giả lập mất kết nối | Không báo nhận bền vững nếu chưa commit |
| DB lỗi lúc startup | Store tạm thời không truy cập được | Có lỗi/giám sát, không âm thầm bỏ backlog |
| Header/payload không deserialize | Triển khai phiên bản mới không tương thích | Phát hiện và xử lý lỗi có kiểm soát |
| Message đã release, consumer lỗi | Cho consumer ném exception | Retry/error channel và transaction theo thiết kế |
| Hai instance cùng khởi động | Cùng store và group ID | Đánh giá race và hiệu lực của idempotency |
| Đổi group ID | Chạy B với group khác | Nhận diện message bị bỏ lại và quy trình migration |

**Chú ý:** Testcontainers được phép sử dụng, nhưng container chứa database phải được giữ qua cả context A và B. Một H2 database dạng `jdbc:h2:mem:...` không chứng minh dữ liệu tồn tại qua việc tắt **toàn bộ JVM**.

## 11. Quan sát quá trình recovery và release

Một hệ thống có restart định kỳ cần phân biệt message **đang chờ**, **đã quá hạn**, **đã release** và **đã hoàn tất nghiệp vụ**.

| Chỉ số | Cách hiểu |
| --- | --- |
| `pendingCount` | Số message trong group đang chờ tại thời điểm đọc |
| `oldestPendingAge` | Tuổi của message pending lâu nhất |
| `overdueCount` | Số message pending có deadline đã qua |
| `recoveryDuration` | Thời gian từ lúc khởi động đến khi đã phục hồi được lịch cần thiết |
| `releaseLagMs` | Độ trễ giữa thời điểm phát thực tế và deadline |
| `retryCount` | Số lần thử lại theo cơ chế xử lý lỗi |
| `businessOutcome` | Kết quả nghiệp vụ thành công, bị bỏ qua hoặc lỗi |

Các metric như `overdueCount` và `releaseLagMs` đòi hỏi ứng dụng đo/ghi nhận thời gian phù hợp; không mặc định mọi trường đều được Spring Integration tự xuất sẵn.

Ví dụ log có cấu trúc:

~~~text
flow=paymentReminderFlow
delayGroup=billing.reminders.delay.v1
eventId=reminder:order-501:payment:v1
correlationId=order-501
receivedAt=2026-11-21T09:00:00Z
dueAt=2026-11-21T09:30:00Z
recoveryAt=2026-11-21T09:12:00Z
releasedAt=2026-11-21T09:30:00.650Z
releaseLagMs=650
outcome=RELEASED
~~~

Đây là log minh họa do ứng dụng chủ động thêm, không phải log mặc định. Dùng `Instant`/UTC cho mốc tuyệt đối khi triển khai nhiều máy và lưu `eventId` xuyên suốt Filter, Router, error channel để liên kết các bước.

Có thể xem số message đang chờ thông qua `MessageGroupStore`:

~~~java
int count = messageGroupStore
        .getMessageGroup("billing.reminders.delay.v1")
        .size();
~~~

`count` chỉ là snapshot pending trong group, không cho biết tất cả tác động phía consumer đã thành công. Một message có thể đã rời Delayer nhưng vẫn nằm trong queue/broker phía sau hoặc đang được retry.

### Khi thấy lỗi sau restart

| Triệu chứng | Điều cần kiểm tra trước |
| --- | --- |
| Không thấy pending message | Cùng DB/schema? Group ID có đổi? Dữ liệu đã commit chưa? |
| Message còn trong DB nhưng không phát | Delayer đã khởi tạo? Recovery/rescheduling chạy chưa? Scheduler và logs có lỗi? |
| Message phát muộn nhiều | Downtime, scheduler quá tải, DB chậm, backlog lớn |
| Message bị lỗi khi đọc lại | Serializer, package/class payload, header không tương thích |
| Hai consumer xử lý cùng event | Retry hoặc hai instance cạnh tranh; kiểm tra `eventId`/idempotency |
| Gateway bị timeout | Reply đến sau thời gian caller chờ; cân nhắc contract bất đồng bộ |
| Nhắc thanh toán sai đối tượng | Consumer không đọc lại trạng thái nghiệp vụ lúc release |

Không xóa thủ công message trong persistent store chỉ vì thấy backlog. Cần xác định message còn có tác vụ đang chạy, có transaction chưa kết thúc và side effect đã xảy ra hay chưa.

## 12. Phân biệt restart recovery với retry

**Restart recovery** trả lời: “Message chưa đến hạn trong lần chạy trước có được tìm lại và phát sau khi ứng dụng khởi động không?”

**Retry** trả lời: “Khi một lần phát/xử lý bị lỗi, có nên thử lại và thử bao nhiêu lần?”

Hai cơ chế có thể xuất hiện cùng lúc. Delayer có các lựa chọn `maxAttempts`, `retryDelay` và `delayedMessageErrorChannel` cho lỗi phát lại:

~~~java
.delay(spec -> spec
        .messageGroupId("billing.reminders.delay.v1")
        .messageStore(store)
        .defaultDelay(60_000L)
        .maxAttempts(3)
        .retryDelay(1_000L)
        .delayedMessageErrorChannel("reminder.delay.errors"))
~~~

Đoạn này minh họa **phần cấu hình Delayer thay thế**, không phải toàn bộ flow chạy độc lập. Cần khai báo channel `reminder.delay.errors` và một error flow nhận `ErrorMessage`, lưu log/metric, phân loại lỗi và có chính sách dead-letter/quarantine thích hợp.

Lỗi release và lỗi side effect ở downstream có thể mang ý nghĩa khác nhau. Sau một lỗi, message có thể bị thử lại, còn trong store, hoặc phải được reschedule thủ công tùy transaction và cơ chế xử lý. Hãy kiểm thử trường hợp consumer ném exception và tiến trình dừng ở từng thời điểm trước khi quy định chính sách phục hồi production.

## 13. Khi nào nên dùng Delayer có recovery?

Phù hợp khi cần trì hoãn **từng message** với deadline tương đối hoặc tuyệt đối, ứng dụng có thể được triển khai lại trong lúc chờ và nghiệp vụ có thể xử lý phát muộn có kiểm soát.

Với lịch dài ngày cần sửa/hủy thường xuyên, lịch cron phức tạp hoặc yêu cầu phân tán rất lớn, cần cân nhắc scheduler nghiệp vụ, workflow engine hay broker hỗ trợ delayed delivery. Delayer không tự thay thế rate limiter: nhiều message cùng deadline có thể đồng loạt phát sau restart và tạo đỉnh tải downstream.

Thiết kế cuối cùng cần bảo vệ cả **pending messages trong Delayer**, **message đã bàn giao ra downstream** và **tác động nghiệp vụ**. Persistence, recovery, error handling, observability và idempotency phải được kiểm chứng cùng nhau.

## 14. Bài tập thực hành và câu hỏi tự kiểm tra

1. Dùng `JdbcMessageStore` để lưu message delay 20 giây; restart ứng dụng sau 5 giây và đo deadline sau khi khởi động lại.
2. Cho ứng dụng dừng quá hạn phát. Dùng một Filter sau Delayer để bỏ reminder của đơn hàng đã thanh toán.
3. Cố tình đổi `messageGroupId` giữa hai phiên bản, quan sát backlog bị bỏ lại và đưa ra kế hoạch migration.
4. Cho producer gửi lại cùng `eventId` dưới hai UUID Spring Message khác nhau; kiểm tra consumer idempotent.
5. Cấu hình một consumer ném exception sau khi message đến hạn; quan sát retry, error channel và trạng thái lưu trữ.
6. Khởi động hai instance dùng chung JDBC store; kiểm tra race khi cùng đến hạn và hiệu lực của chiến lược sở hữu lịch.
7. Thử shutdown khi message vừa được release vào `QueueChannel` bộ nhớ nhưng consumer chưa poll; giải thích vì sao persistence ở Delayer chưa đủ.
8. Đo `pendingCount`, `overdueCount`, `releaseLagMs` sau một đợt downtime giả lập và xác định ngưỡng cảnh báo theo SLA.

**Câu hỏi tự kiểm tra:** Vì sao restart không nên tính lại toàn bộ delay từ thời điểm startup? Điều gì cần giữ ổn định để đọc đúng group? Restart sau deadline khác restart trước deadline ở đâu? `eventId` và `messageGroupId` có trách nhiệm khác nhau thế nào? Tại sao JDBC transaction không thể tự thu hồi email đã gửi? Những bằng chứng nào đủ để nói recovery hoạt động thay vì chỉ thấy service đã khởi động?

## Tài liệu tham khảo

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): cách Delayer trì hoãn message, message store và khôi phục lịch.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): lựa chọn lưu trữ message trong bộ nhớ hoặc ngoài tiến trình.
- [Spring Integration Reference — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): cấu hình hỗ trợ JDBC và schema message store.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): error channel, exception trong flow bất đồng bộ.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): nguyên tắc bảo vệ consumer trước các lần xử lý lặp.
