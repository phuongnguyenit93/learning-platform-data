# Delay group và message identity trong Spring Integration

## 1. Bài toán: nhiều message đang chờ được quản lý thế nào?

Giả sử hệ thống thương mại điện tử nhận các sự kiện:

- `reminder-101`: chờ 30 giây rồi nhắc khách thanh toán đơn hàng `order-101`.
- `reminder-102`: chờ 30 giây rồi nhắc khách thanh toán đơn hàng `order-102`.
- `fraud-101`: chờ 5 giây rồi chuyển cảnh báo rủi ro của `order-101` sang bộ phận kiểm soát.

Hai sự kiện nhắc thanh toán đi qua cùng một **Delayer** và được giữ trong cùng **delay group** của endpoint đó. Cảnh báo rủi ro đi qua một Delayer khác, có group riêng. Mỗi message vẫn có danh tính riêng để theo dõi và xử lý trùng. Sự kiện của cùng đơn hàng cũng cần một khóa tương quan nghiệp vụ để truy vết xuyên qua các nhánh.

Đây là một phần quan trọng trong module **SPRING_INTEGRATION_PATTERN**: triển khai Enterprise Integration Patterns (EIP) với Spring Integration để kết nối Router, Filter, Transformer, Splitter, Aggregator, Gateway và các nhánh retry/error channel một cách ít phụ thuộc, dễ theo dõi và mở rộng.

Mục tiêu bài học là phân biệt rõ:

1. **Delay group**: tập message đang chờ do một Delayer quản lý trong `MessageGroupStore`.
2. **Message identity**: định danh một đối tượng `Message`, thể hiện ở header `MessageHeaders.ID`.
3. **Correlation identity**: khóa liên hệ nhiều message cùng một giao dịch hoặc quy trình.
4. **Business identity/idempotency key**: định danh một sự kiện nghiệp vụ ổn định qua chuyển đổi, retry và phát lại.

~~~mermaid
flowchart TB
    P[Producer: các sự kiện] --> R{Router theo loại}
    R -->|Nhắc thanh toán| D1["Delayer A<br/>messageGroupId=payment.reminders.v1"]
    R -->|Cảnh báo rủi ro| D2["Delayer B<br/>messageGroupId=fraud.alerts.v1"]
    D1 --> S[(MessageGroupStore)]
    D2 --> S
    S -. "Hai nhóm độc lập" .-> X[Kho lưu message chờ]
    D1 --> C1[Consumer nhắc thanh toán]
    D2 --> C2[Consumer kiểm soát rủi ro]
~~~

> **Điểm dễ nhầm:** một delay group *không* tương ứng với một khách hàng hay đơn hàng, trừ khi chính bạn thiết kế các Delayer chuyên biệt như vậy. Trong cấu hình Java DSL thông thường, `messageGroupId` là **một chuỗi cố định cho mỗi Delayer**, dùng làm khóa quản lý nhóm message của endpoint trong store.

## 2. Bốn loại ID cần phân biệt

| Khái niệm | Ví dụ | Ai tạo / quản lý? | Dùng để làm gì? |
| --- | --- | --- | --- |
| `messageGroupId` của Delayer | `payment.reminders.delay.v1` | Cấu hình endpoint | Tìm nhóm message đang chờ của Delayer trong `MessageGroupStore`, nhất là khi restart |
| `MessageHeaders.ID` | UUID do Spring tạo | Framework khi tạo message | Nhận diện một **message instance** của Spring |
| `correlationId` | `order-101` | Luồng tích hợp hoặc framework tùy EIP | Liên hệ các message của cùng một nghiệp vụ qua Splitter/Aggregator, Router và logging |
| `eventId` / `idempotencyKey` | `reminder-101` | Producer/hệ thống nghiệp vụ | Nhận diện sự kiện logic, phát hiện xử lý trùng qua retry, restart hoặc nguồn gửi lại |

Ví dụ, hai sự kiện khác nhau của cùng một đơn hàng:

| Thuộc tính | Message A | Message B |
| --- | --- | --- |
| `eventId` | `reminder-101-first` | `reminder-101-final` |
| `correlationId` | `order-101` | `order-101` |
| `MessageHeaders.ID` | UUID A | UUID B |
| Delayer nhận | Payment Reminder Delayer | Payment Reminder Delayer |
| `messageGroupId` | `payment.reminders.delay.v1` | `payment.reminders.delay.v1` |

Như vậy, **hai message khác ID vẫn có thể thuộc cùng delay group**; và **hai message cùng correlationId không nhất thiết phải nằm trong cùng group** nếu được định tuyến qua hai Delayer khác nhau.

### `MessageHeaders.ID` có ổn định suốt luồng không?

Không nên coi header `id` là khóa nghiệp vụ vĩnh viễn. Spring tạo `MessageHeaders.ID` (thường là UUID) khi xây dựng một message. Khi một bước tạo **message mới** sau biến đổi payload hoặc header, ID có thể thay đổi. Thay đổi đó hợp lý vì đây là định danh của đối tượng message, không phải định danh bất biến của sự kiện trong thế giới thực.

`MessageHeaders.ID` và `MessageHeaders.TIMESTAMP` là header chỉ đọc; không dùng `MessageBuilder.setHeader("id", ...)` để ép chúng thành khóa nghiệp vụ. Nếu cần khóa ổn định, đặt một header riêng như `eventId` do hệ thống sinh và quản lý.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> first = MessageBuilder.withPayload("raw-order")
        .setHeader("eventId", "evt-101")
        .setHeader("correlationId", "order-101")
        .build();

Message<String> transformed = MessageBuilder.fromMessage(first)
        .setPayload("normalized-order")
        .build();

// Khi xây dựng message mới, ID hệ thống có thể đổi.
System.out.println(first.getHeaders().getId());
System.out.println(transformed.getHeaders().getId());

// eventId và correlationId được copy nếu không bị lọc hoặc ghi đè.
System.out.println(transformed.getHeaders().get("eventId")); // evt-101
~~~

`MessageBuilder.fromMessage(...)` minh họa cách copy headers khi xây dựng message mới. Trong luồng thực tế, một Transformer trả về message hoàn chỉnh có thể tự quyết định header đầu ra; cần kiểm tra việc lan truyền `eventId` và `correlationId`, không mặc định mọi endpoint đều giữ nguyên tất cả metadata.

## 3. Delay group hình thành và tồn tại ra sao?

Khi Delayer nhận message có độ trễ dương:

1. `DelayHandler` xác định thời hạn phát bằng `defaultDelay`, biểu thức hoặc hàm delay.
2. Message được lưu vào **nhóm có khóa `messageGroupId`** trong `MessageGroupStore`.
3. `TaskScheduler` được yêu cầu lên lịch tác vụ phát message đến đầu ra khi đến hạn.
4. Đến hạn, Delayer tìm và loại message khỏi nhóm lưu trữ ngay trước khi chuyển nó cho endpoint kế tiếp.

Đây là nhóm **message đang chờ**. Nó không có ngữ nghĩa “gom đủ N phần rồi giải phóng” của Aggregator và cũng không tự thiết lập correlation theo đơn hàng. Delayer lập lịch **từng message**; các message có thể có thời hạn khác nhau, cùng nằm trong một delay group.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as DelayHandler
    participant M as MessageGroupStore
    participant T as TaskScheduler
    participant C as Consumer
    P->>D: Message(eventId=evt-101, delay=3s)
    D->>M: Lưu vào group payment.reminders.delay.v1
    D->>T: Lên lịch theo deadline
    D-->>P: Trả quyền điều khiển
    Note over D,T: Message được giữ để chờ phát
    T->>D: Đến hạn
    D->>M: Lấy và loại message khỏi nhóm
    D->>C: Gửi message sang bước tiếp theo
~~~

Với delay bằng `0` hoặc âm, Delayer chuyển tiếp ngay trên thread của bên gọi; message không đi qua cơ chế chờ có lịch như trường hợp delay dương.

### Nhóm trong Delayer và nhóm trong Aggregator

| Thuộc tính | Delayer | Aggregator |
| --- | --- | --- |
| Mục tiêu | Đợi đến thời điểm phát từng message | Gom các message có liên hệ thành kết quả chung |
| Khóa nhóm | `messageGroupId` cấu hình cho endpoint | Correlation key do chiến lược tương quan quyết định |
| Thời điểm giải phóng | Deadline của từng message | Release strategy, timeout, điều kiện hoàn tất |
| Có cần `correlationId` để tính group? | Không, với Delayer thông thường | Thường có hoặc cần cơ chế tương quan tương đương |
| Kết quả | Message được chuyển tiếp sau khi chờ | Một kết quả tổng hợp hoặc luồng giải phóng theo cấu hình |

Nếu luồng là `Splitter → Delayer → Aggregator`, hãy giữ **hai loại nhóm** tách biệt về ý nghĩa. Delay group để lưu message chờ của Delayer; Aggregator group được tính theo khóa tương quan của từng lô/chủ thể.

## 4. Quy tắc đặt `messageGroupId`

Một `messageGroupId` tốt cần:

- **Cố định và tường minh** trong cấu hình: ví dụ `billing.payment-reminders.delay.v1`.
- **Khác nhau giữa các Delayer độc lập** nếu chúng dùng chung `MessageGroupStore`.
- **Ổn định qua restart và triển khai** nếu muốn khôi phục message đang chờ.
- **Có quy ước tên để quản trị**: ngữ cảnh nghiệp vụ, tên flow, vai trò của Delayer và phiên bản khi cần chuyển đổi có kế hoạch.

Ví dụ:

~~~java
.delay(d -> d
        .messageGroupId("billing.payment-reminders.delay.v1")
        .defaultDelay(30_000L)
        .messageStore(delayedMessageStore))
~~~

Từ Spring Integration 6.2, Java DSL yêu cầu `DelayerEndpointSpec.messageGroupId(String)` cho Delayer. Không phụ thuộc tên bean được framework sinh ra: sau restart tên sinh tự động có thể thay đổi, làm Delayer mới không đọc đúng các message đang chờ trong store.

**Cảnh báo quan trọng khi dùng chung store:** nếu hai *Delayer logic khác nhau* cùng trỏ đến một `messageGroupId`, chúng có thể tranh lấy message của nhau (*work stealing*) hoặc phát sang nhánh sai. Ngược lại, nhiều instance được triển khai như **cùng một Delayer logic** có thể dùng cùng group theo thiết kế, nhưng phải đánh giá cơ chế khóa, transaction, lịch phát và cạnh tranh xử lý của hệ thống phân tán. Trùng group ID không tự động mang lại exactly-once.

Không nên đặt group ID bằng `orderId` riêng của từng message trong cấu hình Delayer thông thường; đó là trách nhiệm của correlation/business headers. Nếu một thiết kế thực sự cần phân vùng xử lý theo đơn hàng, hãy dùng Router, hàng đợi có partition key hoặc cơ chế điều phối phù hợp.

## 5. Ví dụ hoàn chỉnh: hai Delayer, một MessageGroupStore

Ví dụ Spring Integration Java DSL này dùng **hai Delayer độc lập**, cùng chia sẻ một store trong bộ nhớ để quan sát sự tách biệt giữa các nhóm. Producer chỉ cần gửi message vào channel được định danh; consumer có thể xử lý bất đồng bộ sau khi thời gian chờ kết thúc.

Phụ thuộc chính khi dùng Spring Boot: `spring-boot-starter-integration`. Để chạy các ví dụ JUnit ở mục sau, bổ sung `spring-boot-starter-test`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class DelayIdentityFlowConfig {

    public static final String PAYMENT_GROUP =
            "billing.payment-reminders.delay.v1";
    public static final String FRAUD_GROUP =
            "risk.fraud-alerts.delay.v1";

    @Bean
    public MessageGroupStore delayedMessageStore() {
        // Chỉ phục vụ demo: mất dữ liệu chờ khi process dừng.
        return new SimpleMessageStore();
    }

    @Bean("payment.in")
    public MessageChannel paymentIn() {
        return new DirectChannel();
    }

    @Bean("payment.out")
    public PollableChannel paymentOut() {
        return new QueueChannel();
    }

    @Bean("fraud.in")
    public MessageChannel fraudIn() {
        return new DirectChannel();
    }

    @Bean("fraud.out")
    public PollableChannel fraudOut() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow paymentReminderFlow(MessageGroupStore delayedMessageStore) {
        return IntegrationFlow.from("payment.in")
                .delay(d -> d
                        .messageGroupId(PAYMENT_GROUP)
                        .messageStore(delayedMessageStore)
                        .defaultDelay(3_000L))
                .channel("payment.out")
                .get();
    }

    @Bean
    public IntegrationFlow fraudAlertFlow(MessageGroupStore delayedMessageStore) {
        return IntegrationFlow.from("fraud.in")
                .delay(d -> d
                        .messageGroupId(FRAUD_GROUP)
                        .messageStore(delayedMessageStore)
                        .defaultDelay(3_000L))
                .channel("fraud.out")
                .get();
    }
}
~~~

Tất cả message của `paymentReminderFlow` được giữ trong `PAYMENT_GROUP`, dù chúng thuộc các đơn hàng khác nhau. Message của `fraudAlertFlow` được lưu trong `FRAUD_GROUP`, dù có thể cùng `correlationId = order-101` với một reminder.

`SimpleMessageStore` giúp nhìn rõ cơ chế, nhưng **không phải lựa chọn để bảo toàn message qua restart**. Phần 8 giải thích điều kiện khi chuyển sang persistent store.

### Producer gắn identity đúng tầng

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class PaymentEventPublisher {
    private final MessageChannel paymentInput;
    private final MessageChannel fraudInput;

    public PaymentEventPublisher(MessageChannel paymentInput,
                                 MessageChannel fraudInput) {
        this.paymentInput = paymentInput;
        this.fraudInput = fraudInput;
    }

    public void publish() {
        paymentInput.send(MessageBuilder.withPayload("PAYMENT-REMINDER")
                .setHeader("eventId", "reminder-101")
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, "order-101")
                .build());

        paymentInput.send(MessageBuilder.withPayload("PAYMENT-REMINDER")
                .setHeader("eventId", "reminder-102")
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, "order-102")
                .build());

        fraudInput.send(MessageBuilder.withPayload("RISK-ALERT")
                .setHeader("eventId", "fraud-101")
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, "order-101")
                .build());
    }
}
~~~

Ví dụ trên chỉ minh họa producer: khi dùng dependency injection, chỉ định đúng channel `payment.in` và `fraud.in` bằng `@Qualifier`. Mỗi lời gọi tạo một `Message` riêng với header `id` riêng; `eventId` phân biệt sự kiện, còn `correlationId` cho biết chúng thuộc đơn hàng nào. Các header đó **không làm đổi `messageGroupId`** của Delayer.

## 6. Kiểm thử: phân tách group và identity

Kiểm thử dưới đây xác minh những điều thiết yếu: hai message khác ID có thể chờ trong cùng một group, message thứ ba thuộc group khác, và consumer nhận được `eventId` phục vụ truy vết. Dùng khoảng chờ 3 giây để có thời gian kiểm tra store trước khi đến hạn.

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(DelayIdentityFlowConfig.class)
class DelayIdentityFlowTest {

    @Autowired
    @Qualifier("payment.in")
    MessageChannel paymentIn;

    @Autowired
    @Qualifier("payment.out")
    PollableChannel paymentOut;

    @Autowired
    @Qualifier("fraud.in")
    MessageChannel fraudIn;

    @Autowired
    @Qualifier("fraud.out")
    PollableChannel fraudOut;

    @Autowired
    MessageGroupStore delayedMessageStore;

    @Test
    void separatesDelayerGroupsWithoutConfusingMessageIdentity() {
        Message<String> reminder1 = event("reminder-101", "order-101");
        Message<String> reminder2 = event("reminder-102", "order-102");
        Message<String> risk = event("fraud-101", "order-101");

        UUID firstMessageId = reminder1.getHeaders().getId();
        UUID secondMessageId = reminder2.getHeaders().getId();
        assertNotEquals(firstMessageId, secondMessageId);

        assertTrue(paymentIn.send(reminder1));
        assertTrue(paymentIn.send(reminder2));
        assertTrue(fraudIn.send(risk));

        // Đọc ngay trong lúc cả ba message còn đang chờ.
        assertEquals(2, delayedMessageStore.getMessageGroup(
                DelayIdentityFlowConfig.PAYMENT_GROUP).size());
        assertEquals(1, delayedMessageStore.getMessageGroup(
                DelayIdentityFlowConfig.FRAUD_GROUP).size());

        Message<?> ready1 = paymentOut.receive(6_000);
        Message<?> ready2 = paymentOut.receive(6_000);
        Message<?> readyRisk = fraudOut.receive(6_000);

        assertNotNull(ready1);
        assertNotNull(ready2);
        assertNotNull(readyRisk);
        assertEquals("fraud-101", readyRisk.getHeaders().get("eventId"));

        // Không buộc thứ tự phát khi các message cùng thời hạn gần nhau.
        assertEquals(
                java.util.Set.of("reminder-101", "reminder-102"),
                java.util.Set.of(
                        ready1.getHeaders().get("eventId"),
                        ready2.getHeaders().get("eventId")));
    }

    private Message<String> event(String eventId, String orderId) {
        return MessageBuilder.withPayload("EVENT")
                .setHeader("eventId", eventId)
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, orderId)
                .build();
    }
}
~~~

Kiểm thử mô tả hành vi của một context đơn và `SimpleMessageStore`. Phần kiểm tra kích thước group cần chạy **trước deadline**; trong một pipeline CI quá tải, nên cho phép khoảng chờ lớn hơn hoặc kiểm soát scheduler để tránh race khi test chạy quá lâu trước khi đọc store.

Để kiểm thử cả lịch phát, có thể bổ sung các khẳng định rằng không có message đầu ra trong 100 ms đầu, sau đó nhận chúng với timeout đủ rộng. Không nên buộc message gửi vào trước phải phát ra trước khi các deadline gần nhau.

## 7. Message identity xuyên qua Transformer, Splitter, Router và Aggregator

Một sự kiện có thể đi qua nhiều EIP:

~~~mermaid
flowchart LR
    I[Inbound Adapter] --> F[Filter]
    F --> T[Transformer]
    T --> S[Splitter]
    S --> D[Delayer]
    D --> R{Router}
    R --> C1[Consumer A]
    R --> C2[Consumer B]
    C1 --> A[Aggregator nếu nghiệp vụ cần]
    C2 --> A
~~~

Mỗi bước cần giữ đúng loại identity:

| Thành phần | Identity cần quan tâm | Lưu ý |
| --- | --- | --- |
| Filter | `eventId` và lý do loại bỏ | Log message bị loại mà không làm lộ dữ liệu nhạy cảm |
| Transformer | `eventId`, `correlationId` | Message mới có thể có UUID mới; bảo toàn headers nghiệp vụ khi cần |
| Splitter | `correlationId`, `sequenceNumber`, `sequenceSize` | Mỗi phần tử có message riêng; nhận diện cả sự kiện gốc và từng phần |
| Delayer | `messageGroupId` cấu hình, `eventId` | Delay group dành cho chờ phát, không phải group cho Aggregator |
| Router | `eventId`, nhánh đích | Log nhánh xử lý được chọn để truy vết |
| Aggregator | Correlation key và release strategy | Gom theo nghiệp vụ, không dùng delay group làm correlation key |
| Retry/error channel | `eventId`, attempt, nguyên nhân lỗi | Phân biệt lỗi phát lại với một sự kiện logic mới |

Ví dụ một đơn hàng có ba phần tử sau Splitter, cùng `correlationId = order-101` nhưng mỗi message phần tử có `id` riêng. Khi đi qua Delayer, cả ba có thể chờ trong group `billing.payment-reminders.delay.v1`. Sau đó, Aggregator phải gom theo `correlationId` (hoặc một chiến lược tương quan rõ ràng), **không gom theo** `billing.payment-reminders.delay.v1` vì group của Delayer có thể chứa message từ nhiều đơn hàng.

Nếu một nghiệp vụ có nhiều sự kiện con, nên định nghĩa `eventId`/`partId` ở producer hoặc Transformer theo cách ổn định. Một `eventId` chung cho cả lô có thể chưa đủ làm khóa chống xử lý trùng cho **từng phần tử** sau Splitter.

## 8. Persistent store, restart và bảo toàn group

Với `SimpleMessageStore` mặc định, message còn chờ thường tồn tại trong bộ nhớ tiến trình. Khi ứng dụng dừng, dữ liệu chưa đến hạn có nguy cơ mất. Với reminder cần chờ hàng phút hoặc hàng giờ, cấu hình một `MessageGroupStore` bền vững như `JdbcMessageStore`, cùng `messageGroupId` ổn định.

Đoạn thay thế trong flow khi **đã khai báo và cấu hình** bean `JdbcMessageStore`:

~~~java
@Bean
public IntegrationFlow durablePaymentReminderFlow(
        org.springframework.integration.jdbc.store.JdbcMessageStore jdbcMessageStore) {

    return IntegrationFlow.from("durable.payment.in")
            .delay(d -> d
                    .messageGroupId("billing.payment-reminders.delay.v1")
                    .messageStore(jdbcMessageStore)
                    .defaultDelay(60_000L))
            .channel("durable.payment.out")
            .get();
}
~~~

Đoạn này chỉ minh họa phần gắn store, **chưa phải ứng dụng chạy độc lập**: cần `DataSource`, schema JDBC Message Store, bean hai channel và một chiến lược transaction phù hợp. Không ghép nó vào `DelayIdentityFlowConfig` phía trên nếu chưa khai báo các phụ thuộc đó.

Sau restart, `DelayHandler` tìm message trong group của mình và lên lịch lại dựa trên thời điểm nhận ban đầu đối với delay dạng số, hoặc theo `Date` nếu biểu thức trả về mốc tuyệt đối. Message đã quá hạn có thể được phát ngay sau khi ứng dụng khởi động.

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng trước restart
    participant J as JDBC MessageGroupStore
    participant B as Ứng dụng sau restart
    participant C as Consumer
    A->>J: Lưu evt-101 dưới group ổn định
    Note over A: Tiến trình dừng khi còn chờ
    B->>J: Đọc group billing.payment-reminders.delay.v1
    J-->>B: Message còn chờ
    B->>B: Tính lại deadline và đặt lịch
    B->>C: Đến hạn thì phát
~~~

**Đổi tên group ID là một thay đổi dữ liệu** khi dùng store bền vững. Nếu phiên bản mới đổi `billing.payment-reminders.delay.v1` thành `...v2` mà không có kế hoạch chuyển dữ liệu, ứng dụng mới không tự lấy các message của group cũ. Khi cần thay đổi, phải lên kế hoạch drain, migration hoặc quản lý song song các group được chỉ định.

Ngoài group ID, cần quan tâm đến khả năng serialize payload và headers. Một số store JDBC chỉ hỗ trợ dữ liệu `Serializable` theo cấu hình mặc định và có thể bỏ header không thể serialize. Đặc biệt cần kiểm soát header reply/error channel trỏ tới object trong bộ nhớ, vì sau restart đối tượng cũ không còn. Với luồng bất đồng bộ kéo dài, dùng tên channel phù hợp hoặc thiết kế callback riêng có định danh ổn định.

## 9. Phát lại, duplicate và idempotency

Persistent store giúp khôi phục message còn chờ, nhưng **không biến hệ thống thành exactly-once**. Ví dụ:

1. Message `reminder-101` đến hạn và được gửi sang consumer.
2. Consumer đã gọi dịch vụ gửi email thành công.
3. Tiến trình gặp lỗi trước khi toàn bộ trạng thái được xác nhận.
4. Sau retry hoặc khôi phục, cùng sự kiện nghiệp vụ có thể được xử lý lần nữa.

Nếu chỉ nhìn `MessageHeaders.ID`, một message được tạo lại từ cùng sự kiện có thể mang UUID khác và đi qua được kiểm tra trùng. Hãy dùng khóa nghiệp vụ ổn định, ví dụ `eventId = reminder-101`, kết hợp ràng buộc uniqueness hoặc một `MetadataStore` dùng cho Idempotent Receiver.

Mô hình tối giản:

~~~java
public void processReminder(String eventId, String orderId) {
    // Pseudocode: thao tác này cần atomic và được lưu bền vững.
    if (alreadyProcessed(eventId)) {
        return;
    }

    sendReminder(orderId);
    markProcessed(eventId);
}
~~~

Đoạn trên chỉ là **pseudocode để giải thích ý tưởng**: kiểm tra rồi đánh dấu tách rời có race, và giao dịch database không thể tự rollback email đã gửi. Trong ứng dụng thực, dùng khóa unique/claim atomic và cân nhắc outbox, inbox, idempotency key phía dịch vụ nhận, hoặc cơ chế phối hợp phù hợp với tác động bên ngoài.

Đừng sử dụng `messageGroupId` làm khóa idempotency: mọi reminder cùng Delayer có thể chia sẻ một group ID, nên làm thế sẽ vô tình xem các sự kiện khác nhau là trùng. Cũng đừng coi `correlationId` mặc định là khóa chống trùng; một đơn hàng có thể có nhiều sự kiện hợp lệ cùng correlation ID.

## 10. Điều phối nhiều instance và chia sẻ store

Trong môi trường triển khai nhiều instance, có hai trường hợp cần phân biệt:

1. **Hai Delayer logic khác nhau** cùng dùng store: mỗi Delayer cần `messageGroupId` riêng. Nếu trùng ID, message có thể bị lấy nhầm hoặc phát vào flow không mong muốn.
2. **Nhiều instance của cùng một Delayer logic** cùng nhìn vào một store: có thể cùng sử dụng một group, nhưng lúc đó phải kiểm tra khả năng xử lý cạnh tranh, khóa store, transaction, rescheduling và tính idempotent. Không mặc định “chỉ một instance sẽ phát một message” chỉ vì cấu hình chung ID.

Một số triển khai `MessageGroupStore` hỗ trợ cơ chế khóa để bảo vệ thao tác nhóm, nhưng khóa nhóm không thay thế toàn bộ bài toán phân phối lịch và bảo đảm tác động downstream. Giám sát concurrency, số lần xử lý lại và độ trễ phát là bắt buộc khi ứng dụng chạy phân tán.

Nên ưu tiên quản lý group ID như một **định danh triển khai ổn định**, và quản lý `eventId` như một **định danh nghiệp vụ ổn định**. Cả hai đều có đời sống dài hơn việc tạo một instance Java trong bộ nhớ.

## 11. Quan sát và xử lý sự cố

Khi log hoặc trace mỗi message, một tập metadata hữu ích là:

~~~text
flow=paymentReminderFlow
delayGroup=billing.payment-reminders.delay.v1
eventId=reminder-101
correlationId=order-101
messageId=<UUID của Message tại bước đang quan sát>
scheduledAt=...
dueAt=...
releasedAt=...
attempt=...
outcome=SUCCESS|FAILED|RETRIED
~~~

Ghi `messageGroupId` ở cấu hình/metric của endpoint; nó không tự nhiên trở thành một header nghiệp vụ trong mọi message. Có thể lấy `eventId` và `correlationId` từ headers đã được producer/Transformer chuẩn bị. Dùng cùng trace ID để nối log ở nhiều bước nhưng không ghi payload nhạy cảm.

Đối với Delayer có persistence, `DelayHandler` có các thao tác quản trị như `getDelayedMessageCount()` và `reschedulePersistedMessages()`; việc gọi reschedule cần kiểm soát để tránh ảnh hưởng đến message đang xử lý. Nhìn vào store chỉ giúp biết message nào **đang chờ**; message đã rời store nhưng downstream lỗi cần được theo dõi ở error channel, retry và hệ thống đích.

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Sau restart không thấy reminder chờ | Group ID đã đổi; store in-memory; store/schema sai | Khôi phục group ID ổn định, kiểm tra persistence và khởi tạo |
| Nhánh fraud nhận message reminder | Hai Delayer khác logic trùng `messageGroupId` trong cùng store | Tách group ID và xử lý dữ liệu cũ |
| Một đơn hàng có nhiều message chờ | Có nhiều sự kiện hợp lệ cùng `correlationId` | Kiểm tra `eventId`, định nghĩa nghiệp vụ, không dedupe theo correlation đơn thuần |
| UUID ở consumer khác UUID của producer | Một bước đã xây dựng message mới | Theo dõi `eventId`/trace ID ổn định |
| Consumer gửi email hai lần | Retry/phát lại, source gửi lại hoặc lỗi trước khi xác nhận | Idempotent consumer, inbox/outbox, đánh dấu atomic |
| Group tồn tại nhưng message không phát | Scheduler dừng, lỗi startup, cấu hình delay, cạnh tranh store | Kiểm tra scheduler, metric, log và cơ chế reschedule |
| Message không còn trong group nhưng nghiệp vụ lỗi | Message đã được lấy ra để phát, lỗi downstream | Xem retry/error channel, audit và kết quả consumer |

## 12. Bài thực hành và câu hỏi tự kiểm tra

1. Thay `PAYMENT_GROUP` bằng một giá trị khác rồi khởi động lại ứng dụng dùng persistent store. Điều gì xảy ra với message còn chờ trong group cũ? Cần kế hoạch migration nào?
2. Cho hai sự kiện `reminder-101-first` và `reminder-101-final` cùng `correlationId = order-101` vào một Delayer. Vì sao chúng đều hợp lệ và không nên bị dedupe chỉ theo correlation ID?
3. Đặt một Transformer trả về payload mới giữa producer và Delayer. Quan sát `MessageHeaders.ID`, `eventId` và `correlationId` trước/sau Transformer.
4. Thiết kế luồng `Splitter → Delayer → Aggregator` cho ba dòng hàng của cùng đơn. Nêu rõ group dùng để chờ và group dùng để ghép kết quả.
5. Cấu hình hai Delayer logic khác nhau nhưng cố tình cho trùng `messageGroupId` trên cùng store thử nghiệm. Hãy mô tả rủi ro, sau đó sửa cấu hình.
6. Thử một restart với `JdbcMessageStore` và kiểm chứng message còn chờ được lên lịch lại. Đo `dueAt` và `releasedAt` để nhận diện phát muộn.
7. Giả lập consumer lỗi rồi retry. Thiết kế một idempotency key có thể nhận ra **cùng sự kiện nghiệp vụ** ngay cả khi producer tạo một `Message` mới với UUID khác.

## Tài liệu tham khảo

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): `messageGroupId`, `MessageGroupStore`, lịch phát và khôi phục sau restart.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): `MessageHeaders.ID`, `TIMESTAMP`, correlation headers và cơ chế tạo message.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): `MessageGroupStore`, lưu trữ trong bộ nhớ, persistence và serialization.
- [Spring Integration API — DelayHandler](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/DelayHandler.html): ý nghĩa và ràng buộc `messageGroupId`.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): chiến lược hạn chế xử lý trùng tại consumer.
