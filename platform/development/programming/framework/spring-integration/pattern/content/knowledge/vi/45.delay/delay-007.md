# Timeout hoặc lỗi trong delayed flow với Spring Integration

## 1. Bài toán: message đã được nhận nhưng kết quả đến quá muộn

Trong một hệ thống tích hợp doanh nghiệp, việc **Delayer giữ message theo lịch** và việc **consumer xử lý thành công** là hai sự kiện khác nhau. Giả sử đơn hàng vừa được tạo và ứng dụng chờ 10 giây trước khi gọi đối tác:

- Tại `t = 0`, producer gửi message thành công vào Delayer.
- Tại `t = 10 giây`, Delayer dự kiến chuyển message đến consumer.
- Tại `t = 10,2 giây`, consumer gọi REST API và nhận HTTP 503.
- Nếu request ban đầu đi qua Gateway có thời gian chờ phản hồi 5 giây, caller đã timeout **trước khi Delayer phát message**.

Kịch bản này có ít nhất ba vấn đề độc lập: **thời gian trì hoãn**, **timeout của bên đợi phản hồi** và **lỗi lúc phát/xử lý message**. Muốn thiết kế flow đúng, cần xác định lỗi thuộc giai đoạn nào, ai còn đang chờ và cơ chế nào chịu trách nhiệm xử lý tiếp.

Trong module **SPRING_INTEGRATION_PATTERN**, các quyết định này giúp ghép Delayer với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation để tạo luồng message ít phụ thuộc, dễ mở rộng và quan sát được các nhánh.

Mục tiêu của bài:

1. Phân biệt delay period với timeout ở các thành phần khác.
2. Biết cách xử lý lỗi **trước**, **trong** và **sau** lúc Delayer phát message.
3. Sử dụng `maxAttempts`, `retryDelay` và `delayedMessageErrorChannel` đúng ý nghĩa.
4. Tránh mất message hoặc xử lý trùng khi timeout, retry và restart.
5. Viết kiểm thử xác minh message không biến mất chỉ vì một thao tác chờ ngắn đã timeout.

## 2. “Timeout” trong delayed flow có thể chỉ điều gì?

| Khái niệm | Chủ thể đợi | Hết thời gian thì sao? |
| --- | --- | --- |
| **Delay period** | Message đang nằm ở Delayer | Message đủ điều kiện **được phát**; chưa nói consumer thành công |
| `PollableChannel.receive(timeout)` | Một thread đang đợi message ở queue | Có thể trả `null`; message chưa đến hạn **không tự bị hủy** |
| `MessageChannel.send(message, timeout)` | Thread gửi vào một channel có thể chờ nhận | Thời gian chờ gửi vào channel; không đặt deadline xử lý của Delayer |
| Gateway `replyTimeout` | Caller đợi phản hồi từ luồng request/reply | Caller có thể hết thời gian chờ trong khi công việc bất đồng bộ vẫn đang chạy |
| HTTP/client read timeout | Consumer đợi dịch vụ bên ngoài | Lời gọi mạng lỗi/không rõ kết quả; có thể cần retry hoặc đối soát |
| Thời hạn nghiệp vụ (`expiresAt`) | Chính sách nghiệp vụ | Cần một bước Filter/Service Activator kiểm tra và quyết định bỏ qua |
| Retry backoff (`retryDelay`) | Cơ chế phát lại sau lỗi | Đợi giữa các lần **thử phát lại**; không thay thế delay ban đầu |

**Một thao tác `receive(100)` trả `null` không có nghĩa message bị mất.** Nó chỉ nói rằng trong 100 ms chờ đó chưa có message sẵn sàng trên channel đang được poll. Message có thể vẫn nằm trong Delayer và được release muộn hơn.

**Timeout không đồng nghĩa cancellation.** Ví dụ Gateway thôi chờ reply sau 5 giây không có nghĩa tự động hủy tác vụ Delayer đang có deadline 10 giây. Nếu muốn hủy/cập nhật lịch, ứng dụng phải có thiết kế riêng để theo dõi và điều phối trạng thái công việc.

## 3. Vòng đời và các vị trí có thể phát sinh lỗi

~~~mermaid
flowchart LR
    A[Producer] --> B[Input channel]
    B --> C["Delayer: tính delay"]
    C --> D["MessageStore + TaskScheduler"]
    D --> E["Đến hạn: release"]
    E --> F{Router / Filter}
    F --> G[REST/DB consumer]
    C -. "Lỗi biểu thức" .-> X[Đường lỗi khi tiếp nhận]
    D -. "Lỗi lưu trữ hoặc lập lịch" .-> X
    E -. "Lỗi phát" .-> Y[Retry hoặc delayedMessageErrorChannel]
    F -. "Lỗi downstream" .-> Y
    G -. "Timeout mạng" .-> Y
~~~

Mọi lỗi đều cần xem xét **thread đang xử lý** và loại channel.

### Giai đoạn A — Producer đưa message vào Delayer

Nếu input là `DirectChannel`, thao tác nhận đầu vào chạy theo thread của producer. Lỗi đánh giá biểu thức (nếu được cấu hình phải báo lỗi), lỗi message store hoặc lỗi khác lúc tiếp nhận có thể truyền về bên gửi.

Ví dụ:

~~~java
boolean accepted = input.send(MessageBuilder.withPayload("ORDER-101")
        .setHeader("delayMs", 10_000L)
        .build());
~~~

`accepted == true` cho biết việc gửi message vào channel hoàn tất theo ngữ nghĩa của channel. Nó **không phải** xác nhận rằng tác vụ downstream sau 10 giây đã thành công. Nếu message được ghi vào persistent store trong transaction, cần xét thời điểm commit trước khi kết luận nó đã tồn tại bền vững.

### Giai đoạn B — Delayer giữ message và lên lịch

Với delay dương, Delayer sử dụng `TaskScheduler` để thực thi tác vụ phát sau đó, thông thường ở một thread khác. Message đang chờ được quản lý trong `MessageGroupStore` theo `messageGroupId`.

Nếu một transaction vẫn còn hoạt động khi message được ghi vào store, Spring Integration hiện đại lên lịch tác vụ phát sau commit để tránh race giữa scheduler và bản ghi chưa commit. Khi có DB lỗi hoặc transaction rollback, không nên báo đã lên lịch bền vững một cách giả định; hãy kiểm thử đường lưu trữ và transaction thực tế.

### Giai đoạn C — Scheduler release và downstream thất bại

Sau khi delay kết thúc, scheduler kích hoạt phát message. Nếu bước tiếp theo ném exception, lỗi thường xảy ra **sau** khi producer đã rời flow. Lỗi này cần được xử lý trong tác vụ release, retry, error channel hoặc log của scheduler.

Nếu delay bằng `0` hoặc âm, Spring Integration có thể chuyển message ngay trong thread người gọi. Khi đó lỗi downstream đồng bộ có thể xuất hiện trực tiếp trong lần gọi `send()`. Vì vậy cùng một flow có thể quan sát lỗi khác nhau khi thay đổi delay từ `0L` sang một giá trị dương.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as Delayer
    participant S as TaskScheduler
    participant C as Consumer
    P->>D: send(eventId=evt-101, delay=10s)
    D->>S: schedule release
    D-->>P: Lần send ban đầu kết thúc
    Note over P,C: Producer không tiếp tục chờ 10 giây
    S->>C: Sau khi đến hạn, gọi downstream
    C--xS: HTTP 503 / exception
    S->>S: Áp dụng retry hoặc error flow
~~~

## 4. Delay expression sai và cơ chế fallback

Delayer có thể lấy delay từ biểu thức như:

~~~java
.delay(d -> d
        .messageGroupId("orders.timeout.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("headers['delayMs']"))
~~~

Các trường hợp quan trọng:

| Giá trị biểu thức | Hành vi |
| --- | --- |
| `5000L` | Delay khoảng 5 giây |
| `java.util.Date` trong tương lai | Phát không sớm hơn mốc tuyệt đối đó |
| `0L`, số âm hoặc `Date` trong quá khứ | Chuyển tiếp ngay |
| `null` vì thiếu header | Dùng `defaultDelay` |
| Giá trị không thể diễn giải thành số mili giây hoặc `Date` | Dùng `defaultDelay` |
| Biểu thức ném lỗi khi đánh giá | Mặc định bỏ qua lỗi và fallback; có thể yêu cầu báo lỗi |

`headers['delayMs']` là cách truy cập header thường được khuyên dùng khi header có thể vắng mặt. `headers.delayMs` có thể ném lỗi đánh giá khi key không tồn tại.

Mặc định Delayer bỏ qua lỗi khi **đánh giá biểu thức** (ghi log mức DEBUG) và dùng `defaultDelay`. Nếu dữ liệu delay sai là một vi phạm nghiệp vụ, có thể cấu hình:

~~~java
.delay(d -> d
        .messageGroupId("orders.strict.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("headers['delayMs']")
        .ignoreExpressionFailures(false))
~~~

Khi đó exception đánh giá biểu thức được báo lên caller ở giai đoạn tiếp nhận. Điều này khác với một lỗi xảy ra trong tác vụ release chạy sau.

**Fallback không thay thế validation.** Với header đến từ client, cần kiểm tra kiểu, giá trị âm và thời gian chờ tối đa trước khi đưa vào Delayer. Nếu ứng dụng cam kết phát đúng một deadline nghiệp vụ, không nên âm thầm chuyển message sang delay mặc định khi deadline bị hỏng.

## 5. Xử lý lỗi lúc release: retry và error channel

Spring Integration có các thuộc tính riêng cho lỗi phát delayed message:

| Tùy chọn | Giá trị mặc định được tài liệu nêu | Ý nghĩa |
| --- | --- | --- |
| `maxAttempts` | `5` | Giới hạn số lần thử phát khi downstream ném lỗi |
| `retryDelay` | `1_000 ms` | Khoảng chờ trước lần thử lại sau lỗi |
| `delayedMessageErrorChannel` | Không bắt buộc cấu hình | Kênh nhận `ErrorMessage` khi release thất bại |

Ví dụ thay thế phần `.delay(...)` trong một flow:

~~~java
.delay(d -> d
        .messageGroupId("orders.release.retry.v1")
        .defaultDelay(1_000L)
        .delayExpression("headers['delayMs']")
        .maxAttempts(3)
        .retryDelay(500L))
~~~

**Trường hợp không có `delayedMessageErrorChannel` xử lý thành công:** nếu downstream thất bại, Delayer thử phát lại theo `retryDelay` cho đến khi đạt giới hạn `maxAttempts`. Đây là **retry phát sang downstream**, không nhất thiết là retry của toàn bộ nghiệp vụ ở hệ thống đối tác.

### 5.1. Nếu cấu hình `delayedMessageErrorChannel`

~~~java
.delay(d -> d
        .messageGroupId("orders.release.retry.v1")
        .defaultDelay(1_000L)
        .maxAttempts(3)
        .retryDelay(500L)
        .delayedMessageErrorChannel("orders.delay.errors"))
~~~

Khi phát thất bại, Delayer gửi một `ErrorMessage` tới channel `orders.delay.errors`. Payload của message lỗi là exception, phần `originalMessage` liên hệ message gốc, và header `IntegrationMessageHeaderAccessor.DELIVERY_ATTEMPT` thể hiện số lần thử phát hiện tại.

Có hai hành vi quan trọng:

1. **Error flow nhận lỗi và kết thúc bình thường:** lỗi được xem là đã được xử lý; Delayer không tiếp tục retry chỉ vì đã cấu hình `maxAttempts(3)`. Nếu release có transaction, transaction có thể commit và message được loại khỏi store.
2. **Error flow ném exception trở lại:** việc phát được xem là thất bại và Delayer có thể tiếp tục thử lại theo `retryDelay`, đến giới hạn `maxAttempts`.

Vì vậy một handler chỉ gọi `logger.error(...)` rồi return có thể khiến message không được thử lại nữa. Nếu chính sách là lưu vào dead-letter/quarantine và dừng retry thì đây có thể là chủ ý, nhưng bước ghi dead letter phải có độ tin cậy phù hợp.

Ví dụ một **error flow xử lý dứt điểm**; phần lưu vào kho lỗi cần được triển khai bởi ứng dụng:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;

public class DelayFailureHandler {

    @ServiceActivator(inputChannel = "orders.delay.errors")
    public void handle(ErrorMessage error) {
        Throwable cause = error.getPayload();
        Object original = error.getOriginalMessage();

        // Thực tế: lưu eventId, original message và cause vào
        // bảng lỗi / dead-letter store bền vững; phát cảnh báo.
        System.err.println("Delayed release failed: " + cause);
        System.err.println("Original message: " + original);

        // Kết thúc bình thường => lỗi được coi là đã xử lý.
    }
}
~~~

Cần đăng ký handler trên như một bean của Spring (ví dụ `@Component` trên class), khai báo channel `orders.delay.errors` và gắn đoạn cấu hình Delayer ở trên. Đoạn in log phục vụ minh họa; production không nên xem một dòng log là một dead-letter store bền vững.

Nếu muốn báo lỗi để Delayer tiếp tục retry, error flow phải truyền exception theo chính sách đã chọn. Không nên ném lỗi vô điều kiện đến vô hạn; số lần thử, loại lỗi và điểm kết thúc cần được thiết kế và kiểm thử.

### 5.2. Điều gì xảy ra khi retry hết lần?

Theo cơ chế Delayer:

- Khi release **không có transaction**, nếu phát thất bại cho đến giới hạn, message có thể bị loại bỏ khỏi quá trình phát.
- Khi release có transaction và thao tác phát rollback, message có thể **vẫn nằm trong persistent store**, nhưng **không còn tác vụ phát đã được lên lịch** sau khi hết retry; nó có thể cần restart hoặc gọi `reschedulePersistedMessages()` để được lên lịch lại.

Không suy rằng “còn row trong database” nghĩa message chắc chắn sẽ tự phát lại sau vài giây. Cần giám sát cả backlog store và việc scheduler hoạt động.

Việc retry có thể gây tác động trùng: consumer gửi email thành công nhưng timeout trước khi trả lời, sau đó Delayer thử phát lại. Phải dùng `eventId`/idempotency key để giới hạn side effect trùng.

## 6. Ví dụ cấu hình flow và quan sát timeout của người nhận

Ví dụ sau dùng `DirectChannel` ở đầu vào và `QueueChannel` ở đầu ra. Đây là một flow hoàn chỉnh để quan sát message **chưa sẵn sàng trong một khoảng chờ ngắn** rồi xuất hiện khi deadline đến.

Phụ thuộc: `spring-boot-starter-integration`; kiểm thử JUnit dùng `spring-boot-starter-test`.

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
public class DelayTimeoutConfig {

    @Bean("timeout.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean("timeout.ready")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow timeoutDemoFlow() {
        return IntegrationFlow.from("timeout.in")
                .delay(d -> d
                        .messageGroupId("examples.timeout.delay.v1")
                        .defaultDelay(800L)
                        .delayExpression("headers['delayMs']")
                        .maxAttempts(3)
                        .retryDelay(200L))
                .channel("timeout.ready")
                .get();
    }
}
~~~

Producer:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean enqueue(MessageChannel input) {
    return input.send(MessageBuilder.withPayload("ORDER-101")
            .setHeader("eventId", "order-101-notification-v1")
            .setHeader("correlationId", "order-101")
            .setHeader("delayMs", 800L)
            .build());
}
~~~

Ở ví dụ này, không có lỗi downstream được cố ý tạo ra; `maxAttempts` và `retryDelay` chỉ có tác dụng khi bước phát sang output thất bại. `QueueChannel` dùng để kiểm tra việc **release**, chưa đại diện cho consumer cuối cùng đã xử lý nghiệp vụ.

### 6.1. Kiểm thử: timeout khi poll không hủy message

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

@SpringJUnitConfig(DelayTimeoutConfig.class)
class DelayTimeoutTest {

    @Autowired
    @Qualifier("timeout.in")
    MessageChannel input;

    @Autowired
    @Qualifier("timeout.ready")
    PollableChannel output;

    @Test
    void shortReceiveTimeoutDoesNotCancelDelayedMessage() {
        long startedAt = System.nanoTime();

        assertTrue(input.send(MessageBuilder.withPayload("ORDER-101")
                .setHeader("eventId", "event-order-101")
                .setHeader("delayMs", 800L)
                .build()));

        assertNull(output.receive(100),
                "Đầu ra chưa có message trong 100 ms đầu");

        Message<?> released = output.receive(3_000);
        assertNotNull(released, "Message vẫn được release sau hạn");
        assertEquals("ORDER-101", released.getPayload());
        assertEquals("event-order-101",
                released.getHeaders().get("eventId"));

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedAt);
        assertTrue(elapsedMs >= 800L);
    }

    @Test
    void zeroDelayDoesNotWaitForScheduler() {
        assertTrue(input.send(MessageBuilder.withPayload("NOW")
                .setHeader("delayMs", 0L)
                .build()));

        Message<?> released = output.receive(1_000);
        assertNotNull(released);
        assertEquals("NOW", released.getPayload());
    }
}
~~~

Mỗi test gửi message riêng và lấy kết quả từ output. Khi chạy test song song trong cùng context, nên tách channel/test context hoặc kiểm tra `eventId` để tránh một test nhận nhầm message của test khác. Timeout test cần đủ dư cho scheduler bận trên CI.

## 7. Ví dụ kiểm thử lỗi khi release rồi retry thành công

Để kiểm tra lỗi ở **thời điểm phát** thay vì lỗi lúc producer gửi, tạo một handler phía sau Delayer cố ý thất bại trong hai lần đầu, sau đó trả về kết quả.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

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
public class DelayRetryDemoConfig {

    @Bean("retry.in")
    public MessageChannel retryInput() {
        return new DirectChannel();
    }

    @Bean("retry.out")
    public PollableChannel retryOutput() {
        return new QueueChannel();
    }

    @Bean
    public AtomicInteger retryAttempts() {
        return new AtomicInteger();
    }

    @Bean
    public IntegrationFlow retryFlow(AtomicInteger retryAttempts) {
        return IntegrationFlow.from("retry.in")
                .delay(d -> d
                        .messageGroupId("examples.retry.delay.v1")
                        .defaultDelay(200L)
                        .maxAttempts(3)
                        .retryDelay(150L))
                .handle(String.class, (payload, headers) -> {
                    int attempt = retryAttempts.incrementAndGet();
                    if (attempt < 3) {
                        throw new IllegalStateException("Temporary downstream failure");
                    }
                    return payload;
                })
                .channel("retry.out")
                .get();
    }
}
~~~

Với **một message trong context kiểm thử mới**, dự kiến:

1. Producer gửi message vào `retry.in`, rồi kết thúc lần gửi ban đầu.
2. Sau khoảng 200 ms, Delayer phát lần đầu; handler ném lỗi và bộ đếm thành `1`.
3. Sau khoảng 150 ms, Delayer thử phát lần hai; handler tiếp tục ném lỗi.
4. Sau khoảng 150 ms nữa, lần thử thứ ba thành công và output nhận payload.

Lệnh kiểm tra JUnit có thể viết:

~~~java
@SpringJUnitConfig(DelayRetryDemoConfig.class)
class DelayRetryDemoTest {
    @Autowired
    @Qualifier("retry.in")
    MessageChannel input;

    @Autowired
    @Qualifier("retry.out")
    PollableChannel output;

    @Autowired
    AtomicInteger retryAttempts;

    @Test
    void retriesTheScheduledRelease() {
        assertTrue(input.send(
                MessageBuilder.withPayload("RETRY-101").build()));

        Message<?> released = output.receive(5_000);
        assertNotNull(released);
        assertEquals("RETRY-101", released.getPayload());
        assertEquals(3, retryAttempts.get());
    }
}
~~~

Đoạn test dùng các import JUnit, Spring và messaging giống mục 6.1, cộng `@Autowired`, `@Qualifier`, `AtomicInteger`. Trong test thực, mỗi lần chạy phải tạo context và bộ đếm riêng để tránh các message khác làm thay đổi số lần thử. Nếu thay handler demo bằng một HTTP client, chỉ retry khi đã phân loại lỗi; timeout mạng không luôn chứng minh request chưa gây tác động phía đối tác.

## 8. Gateway timeout khi message vẫn còn ở Delayer

Gateway thực hiện request/reply có thể đợi trên một reply channel tạm thời. Giả sử:

~~~mermaid
sequenceDiagram
    participant U as Caller
    participant G as Gateway (replyTimeout 5s)
    participant D as Delayer (delay 10s)
    participant C as Consumer
    U->>G: request(order-101)
    G->>D: Gửi request message
    Note over G,D: Gateway chờ reply
    Note over G: T+5s: hết hạn chờ
    G-->>U: Timeout / null / exception theo cấu hình
    Note over D: T+10s: message đến hạn
    D->>C: Xử lý tiếp
    C-->>G: Reply quá muộn với caller
~~~

Trong luồng thật, Gateway có thể trả `null` khi không nhận reply đúng hạn, hoặc ném `MessageTimeoutException` nếu cấu hình `errorOnTimeout` phù hợp. Timeout **không tự hủy** message đã vào Delayer.

Một điểm tinh tế: Gateway `replyTimeout` giúp giới hạn thời gian **đợi reply trong luồng bất đồng bộ**; nó không bảo đảm cắt ngang một handler đồng bộ đang chặn thread trong một luồng hoàn toàn dùng `DirectChannel`. Vì Delayer delay dương tách thời điểm phát sang thread scheduler, tình huống chờ reply sau Delayer là một trường hợp cần cân nhắc timeout rõ ràng.

Nếu nghiệp vụ thật sự là “tiếp nhận và xử lý sau”, dùng mẫu sau thường dễ kiểm soát hơn:

~~~mermaid
flowchart LR
    A[Caller] --> B[Gateway/API]
    B --> C[Lưu yêu cầu + eventId bền vững]
    C --> D[Trả ACK đã tiếp nhận]
    C --> E[Delayer]
    E --> F[Consumer]
    F --> G[Result Store / Event]
    G --> H[Callback hoặc client truy vấn trạng thái]
~~~

ACK chỉ xác nhận đã nhận yêu cầu theo mức bảo đảm được thiết kế, **không thông báo đã hoàn thành**. Consumer ghi kết quả riêng theo `eventId`; caller có thể truy vấn, nhận event hoặc callback. Với delayed message kéo dài qua restart, tránh phụ thuộc vào reply channel tạm thời của một Gateway đã timeout hoặc không còn tồn tại.

## 9. Persistence, transaction và lỗi sau restart

Với Delayer sử dụng `SimpleMessageStore` trong bộ nhớ, message còn chờ có thể mất khi ứng dụng dừng. Khi cần giữ message qua restart, sử dụng một `MessageGroupStore` bền vững, như `JdbcMessageStore`, cùng `messageGroupId` ổn định:

~~~java
.delay(d -> d
        .messageGroupId("orders.durable.delay.v1")
        .messageStore(jdbcMessageStore)
        .defaultDelay(10_000L)
        .maxAttempts(3)
        .retryDelay(1_000L))
~~~

Đoạn này giả định `jdbcMessageStore` đã được cấu hình với `DataSource` và schema tương ứng; nó chỉ là phần cấu hình Delayer trong một flow.

Sau restart, Delayer tìm message đang chờ trong group và lên lịch lại dựa trên thời điểm nhận gốc (với delay số), hoặc mốc `Date` được lưu. Message đã quá hạn có thể được phát khi phục hồi. Tuy nhiên:

- Nếu message đã **rời store** nhưng downstream chưa xử lý xong, persistence ở Delayer không bảo đảm giữ nó thêm lần nữa.
- Nếu release có transaction và downstream lỗi làm rollback, message có thể **vẫn còn trong store** nhưng không còn lịch tự động khi retry đã hết.
- Nếu consumer đã gửi email thành công rồi hệ thống crash, retry/recovery có thể tạo side effect lặp.
- Nếu group ID đổi mà không migration, phiên bản mới có thể không tìm lại được pending message.

Với hệ thống có nhiều instance, dùng chung JDBC store không tự đảm bảo chỉ một instance phát một message. Cần cơ chế sở hữu, khóa/transaction phù hợp và consumer idempotent.

### Idempotency là trách nhiệm của tầng nghiệp vụ

Nên gắn `eventId` ổn định từ producer và giữ qua Router, Transformer, Delayer, error flow:

~~~java
MessageBuilder.withPayload("order-101")
        .setHeader("eventId", "notify:order-101:v1")
        .setHeader("correlationId", "order-101")
        .build();
~~~

Đầu consumer cần phát hiện cùng một `eventId` đã được xử lý hoặc đang xử lý để hạn chế tác động trùng. `MessageHeaders.ID` có thể đổi khi tạo một message mới; `messageGroupId` là khóa nhóm chờ của Delayer, không phải khóa chống trùng.

## 10. Thiết kế chính sách timeout theo nghiệp vụ

Timeout xảy ra trong delayed flow không phải lúc nào cũng nên retry.

| Tình huống | Quyết định gợi ý | Lý do |
| --- | --- | --- |
| HTTP 503 tạm thời, request có idempotency key | Retry giới hạn với backoff | Có thể phục hồi nếu đối tác trở lại |
| HTTP 400 do payload sai | Ghi lỗi và dừng retry | Gửi lại payload không sửa thường không ích |
| HTTP timeout, không biết đối tác đã xử lý chưa | Kiểm tra trạng thái hoặc retry bằng idempotency key | Tránh tác động trùng |
| Gateway hết thời gian đợi reply, công việc vẫn đang chờ | Trả trạng thái đã tiếp nhận, tra cứu kết quả sau | Timeout của caller không quyết định kết quả nghiệp vụ |
| Reminder đến hạn nhưng đơn hàng đã thanh toán | Filter loại bỏ có audit | Không cần retry thông báo đã lỗi thời |
| Message trong persistent store quá hạn sau downtime | Xem lại điều kiện nghiệp vụ rồi xử lý | Deadline quá khứ không đảm bảo tác động còn hợp lệ |
| Retry hết số lần | Lưu lỗi bền vững, cảnh báo, quy trình replay có kiểm soát | Tránh im lặng làm mất tác vụ |

Trong nhiều hệ thống, **retry với exponential backoff và jitter** ở lớp thích hợp sẽ an toàn hơn nhiều message cùng retry ở một nhịp cố định. `retryDelay` của Delayer biểu diễn khoảng chờ cố định giữa các lần retry release; nếu cần chính sách backoff phong phú, cân nhắc retry advice, hàng đợi hoặc cơ chế điều phối chuyên biệt.

## 11. Observability: biết timeout ở đâu

Thông tin tối thiểu để truy vết:

~~~text
eventId=notify:order-101:v1
correlationId=order-101
delayGroup=orders.durable.delay.v1
receivedAt=2026-11-21T10:00:00Z
dueAt=2026-11-21T10:00:10Z
releasedAt=2026-11-21T10:00:10.130Z
consumerStartedAt=2026-11-21T10:00:10.150Z
consumerEndedAt=2026-11-21T10:00:12.200Z
gatewayTimeoutMs=5000
deliveryAttempt=2
outcome=RETRIED_SUCCESS
~~~

Đây là **dữ liệu log minh họa do ứng dụng cần chủ động tạo**, không phải mọi field do Spring Integration tự ghi ra. Lưu timestamps bằng UTC/`Instant` khi chạy nhiều instance.

Các chỉ số nên theo dõi:

- `pendingCount`: số message còn chờ trong Delayer.
- `releaseLagMs = releasedAt - dueAt`: mức phát muộn của scheduler.
- `deliveryAttempts` và tỉ lệ release thất bại.
- `gatewayTimeoutCount`: số caller ngừng chờ trước khi có reply.
- `downstreamTimeoutCount`: số lần timeout khi consumer gọi dịch vụ bên ngoài.
- `deadLetterCount`, `oldestPendingAge` và số message quá hạn.

| Triệu chứng | Nơi cần kiểm tra |
| --- | --- |
| Producer báo gửi thành công nhưng không có kết quả | Scheduler, message store, đường phát, error channel |
| Gateway timeout trước khi Delayer đến hạn | `replyTimeout`, delay period, thiết kế async ACK |
| `QueueChannel.receive(...)` trả `null` | Message có đến hạn chưa, timeout poll đã đủ dài chưa |
| Message cứ được thử lại | Lỗi downstream, `maxAttempts`, hành vi của error flow |
| Có message trong DB nhưng không chạy | Release transaction rollback, retry exhausted, reschedule |
| Message bị xử lý hai lần | Retry/restart/multi-instance; khóa `eventId` và idempotency |
| Lỗi chỉ xảy ra khi delay bằng 0 | Thread đồng bộ, exception propagation, khác đường release scheduler |

Khi cần reschedule message còn chờ, Spring Integration cung cấp thao tác quản trị `reschedulePersistedMessages()` trên `DelayHandler`. Đây là thao tác vận hành có tác động lên lịch phát; phải kiểm tra ownership, transaction, backlog và nguy cơ phát lại trước khi sử dụng.

## 12. Bài tập và câu hỏi tự kiểm tra

1. Tạo Delayer có `defaultDelay(2_000L)` rồi gọi `receive(100)`. Vì sao kết quả `null` không đồng nghĩa message bị xóa?
2. Cấu hình `maxAttempts(3)`, `retryDelay(200L)` và một downstream handler thất bại hai lần rồi thành công. Quan sát số lần gọi handler và thời gian phát.
3. Gắn `delayedMessageErrorChannel`, cho error handler return bình thường. Kết quả retry khác gì so với khi error handler ném exception?
4. Dùng Gateway chờ reply 500 ms, trong khi Delayer đợi 2 giây. Kiểm tra điều gì xảy ra với request sau khi Gateway đã timeout.
5. Cho `delayMs` là một giá trị sai kiểu và bật `ignoreExpressionFailures(false)`. Chỉ ra lỗi xảy ra trên thread nào.
6. Tạo một message có `eventId` ổn định, giả lập HTTP timeout sau khi side effect đã thành công, rồi thiết kế consumer tránh gửi tác động hai lần.
7. Dùng `JdbcMessageStore`, làm downstream lỗi trong release transaction, để retry hết lần. Kiểm tra group còn message hay không và cách reschedule sau restart.
8. Tạo Filter sau Delayer để loại reminder khi đơn đã thanh toán, kể cả khi message được khôi phục muộn sau một đợt downtime.
9. Thiết kế log/metric để phân biệt: delay quá dài, scheduler phát trễ, Gateway timeout và consumer timeout.

**Tự kiểm tra:** `delayPeriod` có phải timeout không? Vì sao gửi thành công trước delay không chứng minh downstream thành công? `delayedMessageErrorChannel` được gọi khi nào? Vì sao error flow kết thúc bình thường có thể dừng retry? Sau khi Gateway timeout, điều gì giữ Delayer khỏi tạo tác động trùng? Khi nào một message còn trong store nhưng không còn lịch phát?

## Tài liệu tham khảo

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): delay, `TaskScheduler`, `ignoreExpressionFailures`, retry khi release, error channel và persistence.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): lỗi đồng bộ/bất đồng bộ, `ErrorMessage` và `errorChannel`.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): `replyTimeout`, hành vi khi không có reply, `errorOnTimeout` và luồng bất đồng bộ.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): lưu message chờ, transaction và khôi phục.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): hạn chế tác động trùng khi message được phát lại.
