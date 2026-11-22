# Delayer: trì hoãn message trong một khoảng thời gian

## 1. Delayer giải quyết vấn đề gì?

Trong một hệ thống tích hợp doanh nghiệp, không phải message nào cũng nên được xử lý ngay khi đến. Ví dụ:

- Đơn hàng vừa được tạo nhưng chỉ gửi lời nhắc thanh toán sau 15 phút nếu khách chưa thanh toán.
- Một dịch vụ đối tác vừa thông báo quá tải; hệ thống cần chờ một khoảng thời gian trước khi thử xử lý lại.
- Sự kiện cần được phát cho bước tiếp theo tại một thời điểm trong tương lai, chẳng hạn thời điểm bắt đầu một chiến dịch.

**Delayer** là một *Enterprise Integration Pattern* (EIP) cho phép đặt một khoảng chờ giữa hai bước của luồng xử lý message. Trong Spring Integration, endpoint Delayer sử dụng `DelayHandler` và `TaskScheduler`: khi nhận message có độ trễ dương, nó lên lịch phát message sang bước tiếp theo rồi trả quyền điều khiển cho bên gửi. Bên gửi không phải giữ một thread ngủ trong suốt khoảng chờ.

Điều này phù hợp với mục tiêu của module **SPRING_INTEGRATION_PATTERN**: ghép các thành phần xử lý message ít phụ thuộc, có thể thay đổi từng bước độc lập, mở rộng và theo dõi các nhánh xử lý.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as Delayer
    participant S as MessageStore
    participant T as TaskScheduler
    participant C as Consumer
    P->>D: Message + delayMs
    D->>S: Lưu message đang chờ
    D->>T: Lên lịch phát lại
    D-->>P: Trả quyền điều khiển
    Note over D,T: Khoảng chờ đã cấu hình
    T->>D: Đến thời điểm phát
    D->>S: Lấy / loại message khỏi nhóm chờ
    D->>C: Chuyển message đến bước tiếp theo
~~~

> **Phân biệt hai thời điểm:** `send()` trả về khi endpoint đã nhận và lên lịch thành công theo ngữ cảnh hiện tại; điều đó **không** có nghĩa consumer phía sau đã xử lý xong. Delay 5.000 ms nghĩa là thời điểm *sớm nhất* để phát khoảng 5 giây sau khi Delayer nhận message, không phải cam kết hoàn thành chính xác ở mốc 5 giây.

## 2. Cơ chế hoạt động

Một Delayer có ba thành phần chính:

| Thành phần | Trách nhiệm |
| --- | --- |
| `DelayHandler` | Đánh giá độ trễ, giữ message trong nhóm chờ và điều phối việc phát lại |
| `TaskScheduler` | Chạy tác vụ phát message khi đến hạn, thường trên thread thuộc pool của scheduler |
| `MessageGroupStore` | Lưu các message đang chờ; mặc định lưu trong bộ nhớ, có thể thay bằng kho lưu trữ bền vững |

Diễn biến khi `delayMs = 3000`:

1. Tại `t0`, message đi vào Delayer và thời hạn phát được tính.
2. Message được giữ lại; Delayer đăng ký công việc với scheduler. Thread gửi message được giải phóng.
3. Sớm nhất tại `t0 + 3 giây`, scheduler gọi tác vụ phát lại. Nếu pool đang bận hoặc ứng dụng chịu tải lớn, thời điểm thực tế có thể muộn hơn.
4. Message rời Delayer để tới Filter, Transformer, Router, Service Activator hoặc endpoint kế tiếp.

Với độ trễ bằng `0` hoặc âm, Spring Integration chuyển message **ngay trên thread của bên gọi** thay vì tạo tác vụ chờ. Đây là khác biệt đáng lưu ý khi quan sát thread và xử lý lỗi.

### Độ trễ được xác định như thế nào?

Delayer nhận một `defaultDelay`, đồng thời có thể đánh giá biểu thức SpEL hoặc hàm để lấy thời gian riêng cho từng message. Kết quả từ biểu thức, nếu hợp lệ và khác `null`, được ưu tiên so với giá trị mặc định.

| Dữ liệu đầu vào | Kết quả |
| --- | --- |
| Không có header `delayMs`, `defaultDelay = 2000` | Chờ khoảng 2 giây |
| Header `delayMs = 5000L` | Chờ ít nhất 5 giây |
| Header `delayMs = 0L` hoặc số âm | Chuyển ngay trên thread gọi |
| Biểu thức trả về `java.util.Date` trong tương lai | Chờ đến thời điểm tuyệt đối đó |
| Biểu thức trả về `Date` trong quá khứ | Chuyển ngay |
| Biểu thức trả về giá trị không thể diễn giải thành số mili giây hoặc `Date` | Dùng `defaultDelay` |
| SpEL ném lỗi đánh giá | Mặc định ghi nhận ở mức DEBUG và dùng `defaultDelay`; cấu hình `ignoreExpressionFailures(false)` để báo lỗi về bên gọi |

Giá trị delay dạng số được hiểu là **mili giây**, không phải giây. Biểu thức `headers['delayMs']` là cách truy cập header nên dùng khi header có thể vắng mặt: nó trả về `null` và cho phép fallback. Cú pháp `headers.delayMs` có thể ném lỗi truy cập thuộc tính nếu header không tồn tại.

## 3. Thực hành: trì hoãn thông báo theo từng message

Ví dụ sử dụng Spring Boot, Spring Integration Java DSL và một `QueueChannel` ở đầu ra để quan sát message. Một message thông báo có thể có header `delayMs` hoặc để Delayer tự lấy độ trễ mặc định. Các tên channel được giữ ổn định để có thể thay producer, consumer độc lập với logic trì hoãn.

Phần phụ thuộc chính cần có: `spring-boot-starter-integration`; để chạy bài kiểm thử bên dưới, thêm `spring-boot-starter-test`. Ví dụ sử dụng Java và các API Spring Integration hiện đại với `IntegrationFlow.from(...)`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class DelayFlowConfig {

    @Bean("notifications.input")
    public MessageChannel notificationsInput() {
        return new DirectChannel();
    }

    @Bean("notifications.ready")
    public PollableChannel notificationsReady() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow notificationDelayFlow() {
        return IntegrationFlow.from("notifications.input")
                .delay(spec -> spec
                        .messageGroupId("notifications.delay.v1")
                        .defaultDelay(2_000L)
                        .delayExpression("headers['delayMs']"))
                .channel("notifications.ready")
                .get();
    }
}
~~~

Giải thích cấu hình:

- `DirectChannel` nhận message từ producer và gọi endpoint kế tiếp trong cùng lượt gửi; khi delay dương, Delayer lên lịch rồi trả quyền điều khiển.
- `messageGroupId("notifications.delay.v1")` nhận diện **nhóm message** của Delayer; giữ tên ổn định, đặc biệt nếu sau này dùng message store bền vững.
- `defaultDelay(2_000L)` đặt thời gian chờ mặc định là 2 giây.
- `delayExpression("headers['delayMs']")` ưu tiên header theo từng message, cho phép nhiều độ trễ trong cùng một flow.
- `QueueChannel` ở cuối ví dụ giữ message đã phát để bài kiểm thử nhận bằng `receive(timeout)`. Trong hệ thống thực, có thể thay bằng `.handle(...)` để gọi một service, hoặc chuyển tiếp tới các bước EIP khác.

Producer có thể gửi ba message với cách tính thời gian khác nhau:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

void publishExamples(MessageChannel input) {
    input.send(MessageBuilder.withPayload("ORDER-1001")
            .setHeader("delayMs", 5_000L)
            .build()); // Sau ít nhất khoảng 5 giây

    input.send(MessageBuilder.withPayload("ORDER-1002")
            .build()); // Không có header: dùng mặc định 2 giây

    input.send(MessageBuilder.withPayload("ORDER-1003")
            .setHeader("delayMs", 0L)
            .build()); // Chuyển ngay
}
~~~

Lưu ý: method `publishExamples` minh họa phía producer; truyền vào bean channel `notifications.input` do Spring quản lý. Khi dùng `QueueChannel`, consumer phải chủ động nhận message. Nếu đổi channel đầu ra thành `DirectChannel`, cần có subscriber xử lý message tương ứng.

### Minh họa bằng thời gian

Giả sử cả ba message được gửi gần như đồng thời tại `10:00:00`, với scheduler không quá tải:

| Message | Delay | Thời điểm dự kiến có thể lấy từ đầu ra |
| --- | ---: | --- |
| ORDER-1001 | 5.000 ms | Khoảng 10:00:05 hoặc muộn hơn |
| ORDER-1002 | 2.000 ms | Khoảng 10:00:02 hoặc muộn hơn |
| ORDER-1003 | 0 ms | Ngay trong lượt gửi |

**Thứ tự phát không nhất thiết trùng thứ tự nhận.** Nếu hệ thống cần đảm bảo thứ tự giữa các message cùng khóa nghiệp vụ, phải thiết kế thêm cơ chế sắp thứ tự, phân vùng hoặc điều phối phù hợp; Delayer tự nó không hứa bảo toàn thứ tự theo lúc nhận.

## 4. Kiểm thử hành vi trì hoãn

Kiểm thử nên kiểm tra *không phát quá sớm* và *cuối cùng có phát trong một khoảng timeout hợp lý*. Tránh khẳng định thời điểm phải đúng tuyệt đối đến từng mili giây vì việc lập lịch phụ thuộc CPU, scheduler và tải máy.

~~~java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(DelayFlowConfig.class)
class DelayFlowTest {

    @Autowired
    @Qualifier("notifications.input")
    MessageChannel input;

    @Autowired
    @Qualifier("notifications.ready")
    PollableChannel ready;

    @Test
    void releasesMessageAfterConfiguredDelay() {
        long started = System.nanoTime();
        assertTrue(input.send(MessageBuilder.withPayload("ORDER-1001")
                .setHeader("delayMs", 500L)
                .build()));

        assertNull(ready.receive(100), "Message không được ra quá sớm");

        Message<?> delivered = ready.receive(2_000);
        assertNotNull(delivered, "Message phải được phát trong timeout thử nghiệm");
        assertEquals("ORDER-1001", delivered.getPayload());

        long elapsedMs = TimeUnit.NANOSECONDS
                .toMillis(System.nanoTime() - started);
        assertTrue(elapsedMs >= 500L);
    }
}
~~~

Nên bổ sung các ca kiểm thử độc lập cho: thiếu header (fallback), `delayMs = 0` (phát ngay), thời điểm `Date` trong tương lai, header sai kiểu, consumer ném exception và việc khởi động lại ứng dụng với message store bền vững. Với các ca kiểm tra sát ranh giới thời gian, dùng khoảng chờ đủ dư để tránh kiểm thử thất thường trên CI.

## 5. Tồn tại qua restart: MessageStore và messageGroupId

Theo mặc định, message đang chờ thường nằm trong `SimpleMessageStore` **trong bộ nhớ**. Nếu tiến trình bị dừng trước hạn, message đang chờ có thể mất. Khi thời gian chờ dài hoặc mất message gây hậu quả nghiệp vụ, cấu hình `MessageGroupStore` bền vững như `JdbcMessageStore`.

Ví dụ phần cấu hình Delayer khi ứng dụng **đã có** một bean `JdbcMessageStore` phù hợp:

~~~java
@Bean
public IntegrationFlow durableNotificationFlow(JdbcMessageStore jdbcMessageStore) {
    return IntegrationFlow.from("durable.notifications.input")
            .delay(spec -> spec
                    .messageGroupId("durable.notifications.delay.v1")
                    .messageStore(jdbcMessageStore)
                    .defaultDelay(60_000L)
                    .delayExpression("headers['delayMs']"))
            .channel("durable.notifications.ready")
            .get();
}
~~~

Đoạn trên chỉ thể hiện cách gắn store; cần cấu hình `DataSource`, schema lưu trữ message và hai channel tương ứng trước khi sử dụng trong ứng dụng thực tế. Không gắn đồng thời flow này vào ví dụ `DelayFlowConfig` ở mục 3 nếu chưa khai báo các bean đó.

Khi Delayer khởi động lại với store bền vững, nó đọc message còn chờ trong nhóm và lên lịch lại: delay số được tính theo thời điểm nhận gốc, còn delay dạng `Date` theo thời điểm tuyệt đối. Message đã quá hạn có thể được phát ngay sau khi ứng dụng trở lại. `messageGroupId` cần ổn định và phân biệt giữa các Delayer khác nhau để tránh lấy nhầm nhóm message.

Store bền vững giúp giảm rủi ro thất lạc khi restart nhưng **không tự bảo đảm exactly-once**. Chẳng hạn nếu consumer thực hiện xong tác động bên ngoài nhưng hệ thống gặp lỗi trước khi ghi nhận kết quả, lần phát lại có thể tạo tác động trùng. Hãy dùng mã nghiệp vụ như `orderId` hoặc `eventId` để xử lý idempotent, cùng transaction và outbox khi bài toán đòi hỏi.

## 6. Lỗi, retry và error channel

Cần phân biệt hai tình huống:

1. **Lỗi trước hoặc trong lúc nhận message:** xảy ra ở đường đi của producer hoặc khi đánh giá cấu hình. Với delay dương, Delayer thường trả quyền điều khiển sau khi lên lịch; lỗi của consumer về sau không xảy ra trên thread gửi ban đầu.
2. **Lỗi khi phát message đã đến hạn:** chạy từ scheduler; cần chính sách retry, error channel, quan sát và cách xử lý cuối cùng riêng.

Delayer có tùy chọn `maxAttempts` (mặc định **5**) và `retryDelay` (mặc định **1.000 ms**) cho lỗi khi *phát message đã đến hạn* xuống downstream. Có thể khai báo:

~~~java
.delay(spec -> spec
        .messageGroupId("notifications.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("headers['delayMs']")
        .maxAttempts(3)
        .retryDelay(1_000L)
        .delayedMessageErrorChannel("notifications.delay.errors"))
~~~

Đây là đoạn cấu hình thay thế cho phần `.delay(...)` ở ví dụ chính; khi dùng, phải tạo channel `notifications.delay.errors` và một error flow xử lý `ErrorMessage`. Error message có thể chứa ngoại lệ, thông tin message gốc và số lần đã thử phát. Theo cơ chế Delayer, nếu error flow xử lý thành công và kết thúc bình thường, lỗi có thể được xem là đã xử lý; nếu error flow ném ngoại lệ, Delayer tiếp tục thử phát cho tới ngưỡng cấu hình.

Nếu hết lần thử, khi phát không có transaction, message có thể bị loại bỏ. Với phát có transaction, message có thể còn trong persistent store nhưng **không còn lịch phát tự động** cho tới lúc reschedule hoặc restart. Do đó, cần quy định cụ thể việc ghi log, cảnh báo, lưu dead letter/quarantine, thao tác reschedule và biện pháp tránh xử lý trùng. `delayedMessageErrorChannel` dành riêng cho lỗi phát lại; đừng nhầm nó với một retry tổng quát của toàn bộ flow hay với channel `errorChannel` mặc định.

Khi dùng retry để gọi dịch vụ bên ngoài, hãy tách rõ **chờ trước lần xử lý đầu tiên** (Delayer) với **retry có backoff sau lỗi** (ví dụ retry advice hoặc một luồng retry chuyên biệt). Delayer không tự xác định lỗi nào đáng thử lại; ứng dụng phải đặt chính sách theo nghiệp vụ.

## 7. Thiết kế và vận hành luồng message

Một luồng tích hợp thực tế có thể ghép nhiều EIP:

~~~mermaid
flowchart LR
    A[Nhận sự kiện] --> B{Filter hợp lệ?}
    B -->|Không| X[Ghi nhận và dừng]
    B -->|Có| C[Transformer chuẩn hóa]
    C --> D[Delayer]
    D --> E{Router theo loại}
    E --> F[Email adapter]
    E --> G[Webhook adapter]
    F --> H[Quan sát kết quả]
    G --> H
~~~

**Correlation:** gắn `correlationId`, `eventId` và khóa nghiệp vụ vào headers hoặc payload trước Delayer để theo dõi message đi qua Router, Splitter, Aggregator và các nhánh xử lý. Delayer giữ message đang chờ nhưng không tự tạo ra quy tắc tương quan nghiệp vụ.

**Thông số cần theo dõi:** số lượng message đang chờ, tuổi của message cũ nhất, độ lệch giữa thời gian dự kiến và thời gian phát thực tế, số lần retry, lỗi tại consumer và dung lượng store. `DelayHandler` cung cấp các thao tác quản trị như `getDelayedMessageCount()` và `reschedulePersistedMessages()` qua cơ chế quản trị phù hợp; chỉ gọi reschedule khi hiểu rõ trạng thái store và tác động của phát lại.

**Giới hạn và quyết định thiết kế:**

| Nhu cầu | Hướng xử lý |
| --- | --- |
| Chờ vài giây đến phút giữa hai bước EIP | Delayer với scheduler và store thích hợp |
| Lịch nhắc quan trọng kéo dài qua nhiều lần triển khai | Delayer kèm persistent store, định danh ổn định, giám sát và idempotency; cân nhắc hệ thống scheduler bền vững khi cần lịch nghiệp vụ phức tạp |
| Giới hạn số request mỗi giây | Rate limiter/throttling chuyên dụng; Delayer không tự áp chính sách tốc độ |
| Thử lại sau lỗi mạng | Retry với backoff và phân loại lỗi; có thể kết hợp Delayer |
| Xếp hàng chờ consumer chủ động lấy | `QueueChannel` hoặc message broker phù hợp; Delayer giải quyết **thời điểm phát**, không thay thế mọi cơ chế hàng đợi |
| Chạy công việc định kỳ theo cron | Scheduler/`@Scheduled`; Delayer áp dụng cho **mỗi message** đi qua flow |

Với hệ thống có nhiều instance, cần thiết kế sở hữu message group và cạnh tranh truy cập store; không mặc định rằng chia sẻ một store giữa nhiều instance sẽ tạo thành bộ lập lịch phân tán có bảo đảm duy nhất. Với header do client gửi, kiểm tra kiểu dữ liệu và giới hạn giá trị delay để tránh lịch chờ vô hạn hoặc chiếm quá nhiều bộ nhớ.

Đối với gateway đồng bộ chờ một reply, Delayer có thể làm reply đến muộn hơn timeout của gateway. Nếu ý nghĩa nghiệp vụ là "tiếp nhận yêu cầu và xử lý sau", hãy thiết kế phản hồi xác nhận tiếp nhận trước, rồi theo dõi kết quả bất đồng bộ bằng id sự kiện.

## 8. Câu hỏi tự kiểm tra

1. Vì sao Delayer với delay dương không cần giữ thread của producer chờ hết thời gian?
2. Với `defaultDelay = 2000` và `headers['delayMs'] = 7500L`, message sẽ được phát sớm nhất sau bao lâu?
3. Khi header `delayMs` bị thiếu, tại sao `headers['delayMs']` an toàn hơn `headers.delayMs`?
4. Cần làm gì để message chờ không bị mất đơn giản chỉ vì ứng dụng restart?
5. Vì sao phải cấu hình `messageGroupId` ổn định và bảo đảm consumer xử lý idempotent?
6. Nếu consumer ném lỗi trong lúc scheduler phát message, nên theo dõi lỗi và quyết định retry ở đâu?

**Bài thực hành mở rộng:** thay `notifications.ready` bằng một consumer giả lập thất bại hai lần rồi thành công ở lần thứ ba. Quan sát thứ tự thời gian, số lần phát lại và nội dung error channel; sau đó thử trường hợp ứng dụng restart với `JdbcMessageStore` và so sánh kết quả.

## Tài liệu tham khảo

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): `DelayHandler`, tính toán độ trễ, scheduler, lưu trữ và xử lý lỗi khi phát lại.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): rủi ro của lưu trữ trong bộ nhớ và các lựa chọn persistence.
- [Spring Integration API — DelayerEndpointSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/DelayerEndpointSpec.html): các tùy chọn Java DSL như `messageGroupId`, `delayExpression`, `messageStore`, `maxAttempts` và `retryDelay`.
