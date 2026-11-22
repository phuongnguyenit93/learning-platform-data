# Delay period cố định và động trong Spring Integration

## 1. Vì sao phải chọn cách tính thời gian trì hoãn?

Trong Enterprise Integration Patterns (EIP), **Delayer** tiếp nhận một message, giữ message lại trong khoảng thời gian được chỉ định rồi mới chuyển nó sang endpoint tiếp theo. Với Spring Integration, đây là cách tách **thời điểm nhận sự kiện** khỏi **thời điểm xử lý tiếp** mà không cần cho thread của producer ngủ chờ.

Một hệ thống thường gặp hai yêu cầu:

- **Cố định:** mọi sự kiện đặt hàng phải chờ 2 giây trước khi được gửi tới bộ xử lý tiếp theo.
- **Động:** đơn hàng thường chờ 2 giây, nhưng đơn hàng cần ưu tiên chỉ chờ 500 ms; một lời nhắc thanh toán có thể chờ 15 phút; một thông báo khác cần phát đúng một mốc thời gian cho trước.

Trong module **SPRING_INTEGRATION_PATTERN**, việc chọn delay period là một quyết định thiết kế luồng message: nó ảnh hưởng đến Router, Filter, Transformer, Gateway, xử lý lỗi, correlation và cách quan sát từng nhánh. Bài này tập trung vào **cách cấu hình và kiểm thử delay cố định so với delay động**, cùng giới hạn vận hành của từng cách.

### Mô hình tổng quát

~~~mermaid
flowchart LR
    P[Producer] --> D{Cách xác định thời gian chờ}
    D -->|Cố định| F["defaultDelay: 2.000 ms"]
    D -->|Theo message| H["headers['delayMs']"]
    D -->|Mốc tuyệt đối| A["headers['deliverAt']: Date"]
    F --> S[Delayer lên lịch]
    H --> S
    A --> S
    S --> Q[Endpoint tiếp theo]
~~~

Delay dương được phát theo `TaskScheduler`. Thời điểm message thực sự đến consumer có thể muộn hơn hạn phát do scheduler, CPU, message store hoặc consumer đang bận. **Delay period đặt thời điểm đủ điều kiện phát**, không bảo đảm toàn bộ nghiệp vụ đã hoàn thành chính xác tại thời điểm đó.

## 2. Phân biệt delay cố định và delay động

| Tiêu chí | Cố định | Động theo message |
| --- | --- | --- |
| Nguồn thời gian | Một `defaultDelay` cho endpoint | Header, payload hoặc kết quả biểu thức/hàm |
| Đơn vị của giá trị số | Mili giây | Mili giây |
| Mức linh hoạt | Đơn giản, dễ kiểm soát | Mỗi message có thể có thời gian riêng |
| Cấu hình thường gặp | `.delay(d -> d.defaultDelay(2000L))` | `.delay(d -> d.defaultDelay(2000L).delayExpression("headers['delayMs']"))` |
| Rủi ro chính | Chậm mọi message, kể cả trường hợp ưu tiên | Header sai hoặc bị lạm dụng, thời gian chờ khó dự đoán |
| Phù hợp | Khoảng nghỉ chung, xử lý giãn cách đơn giản | Thông báo theo ưu tiên, lịch hẹn, thời điểm hết hạn |

**Điểm quan trọng:** khi dùng biểu thức động, `defaultDelay` vẫn hữu ích làm giá trị dự phòng. Hai cơ chế có thể cùng tồn tại trong một Delayer.

## 3. Delay cố định với `defaultDelay`

Một Delayer có thể được cấu hình để phát mọi message sau khoảng 2.000 ms:

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.fixed.delay.v1")
        .defaultDelay(2_000L))
~~~

Khi không chỉ định biểu thức delay riêng, từng message nhận cùng khoảng chờ mặc định. Giá trị `2_000L` tính bằng **mili giây**, tức khoảng 2 giây.

Giả sử ba message đến lúc:

| Message | Thời điểm Delayer nhận | Delay | Thời điểm sớm nhất có thể phát |
| --- | --- | --- | --- |
| A | 10:00:00.000 | 2.000 ms | 10:00:02.000 |
| B | 10:00:00.300 | 2.000 ms | 10:00:02.300 |
| C | 10:00:01.000 | 2.000 ms | 10:00:03.000 |

Mỗi message có **mốc bắt đầu riêng** tính theo lúc Delayer nhận nó; Delayer không gom tất cả message lại để phát thành một lô ở cuối chu kỳ 2 giây.

Một số tình huống phù hợp với delay cố định:

- Tạo một khoảng chờ ngắn để hệ thống khác kịp hoàn tất cập nhật dữ liệu trước khi đọc.
- Làm chậm một bước nghiệp vụ vốn luôn yêu cầu chờ tối thiểu.
- Mô phỏng điều kiện bất đồng bộ trong bài thực hành tích hợp và kiểm thử.

Không dùng Delayer cố định như công cụ giới hạn số request mỗi giây: 1.000 message cùng vào với delay 2 giây vẫn có thể **cùng đến hạn sau khoảng 2 giây**, gây tải tăng đột biến. Rate limiting và điều khiển lưu lượng cần cơ chế riêng.

## 4. Delay động theo header hoặc biểu thức

Với delay động, producer hoặc một bước Transformer trước Delayer cung cấp thời gian chờ riêng cho từng message:

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.dynamic.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("headers['delayMs']"))
~~~

Biểu thức SpEL `headers['delayMs']` đọc giá trị header `delayMs`. Nếu header vắng mặt và biểu thức trả về `null`, Delayer dùng `defaultDelay`. Khi biểu thức trả về một giá trị thời gian hợp lệ, giá trị đó được ưu tiên.

Ví dụ các message đi vào cùng Delayer:

| Message | Header `delayMs` | Delay được sử dụng | Ý nghĩa |
| --- | ---: | ---: | --- |
| Thông báo thường | Không có | 2.000 ms | Fallback về mặc định |
| Thông báo ưu tiên | `500L` | 500 ms | Chờ ngắn hơn |
| Nhắc thanh toán | `900_000L` | 900.000 ms | Chờ 15 phút |
| Sự kiện cần chuyển ngay | `0L` | 0 ms | Không đặt lịch chờ |

Giá trị số bằng `0` hoặc âm làm message được chuyển tiếp ngay, thường trên thread của bên gửi. Nếu ứng dụng cần luôn xử lý bất đồng bộ, phải thiết kế channel/đường thực thi tương ứng thay vì giả định Delayer tự tạo thread cho mọi message.

### Header không phải nguồn duy nhất

Khi thời gian chờ do nghiệp vụ tính từ payload, có thể dùng SpEL:

~~~java
.delay(delayer -> delayer
        .messageGroupId("orders.priority.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("payload.priority == 'HIGH' ? 500L : 5000L"))
~~~

Biểu thức trên chỉ có ý nghĩa nếu payload thực sự có thuộc tính `priority`, ví dụ một Java record có accessor tương ứng. Trong ứng dụng thực tế, một bước **Transformer** có thể chuẩn hóa dữ liệu đầu vào thành header delay được kiểm tra kiểu, giúp Delayer ít phụ thuộc vào cấu trúc payload.

Giới hạn thiết kế cần nhớ: thời gian động phụ thuộc **giá trị của chính message khi đi qua endpoint**. Nếu doanh nghiệp thay đổi quy tắc ưu tiên sau khi message đã lên lịch, thay đổi đó không tự động cập nhật tất cả lịch đã tạo.

### Thời điểm tuyệt đối với `java.util.Date`

Một yêu cầu khác là “phát khi đến 09:00 ngày mai” thay vì “phát sau 10 phút”. Biểu thức Delayer có thể cung cấp một đối tượng `java.util.Date` chỉ **mốc phát tuyệt đối**:

~~~java
.delay(delayer -> delayer
        .messageGroupId("reminders.absolute.delay.v1")
        .defaultDelay(1_000L)
        .delayExpression("headers['deliverAt']"))
~~~

Producer:

~~~java
import java.time.Instant;
import java.util.Date;
import org.springframework.messaging.support.MessageBuilder;

var message = MessageBuilder.withPayload("REMINDER-42")
        .setHeader("deliverAt", Date.from(Instant.now().plusSeconds(30)))
        .build();
~~~

Nếu `deliverAt` cách thời điểm nhận message khoảng 30 giây, Delayer sẽ lên lịch phát tại thời điểm đó. Nếu thời điểm nằm trong quá khứ, message đã đến hạn và được chuyển ngay. Khi header không có, `defaultDelay` áp dụng.

**Phân biệt kiểu dữ liệu:** một `Long` như `30_000L` biểu thị **khoảng chờ 30 giây**, trong khi `Date` biểu thị **thời điểm trên đồng hồ**. Không gửi Unix epoch millisecond dưới dạng `Long` rồi mong Delayer tự hiểu đó là mốc tuyệt đối; hãy chuyển nó thành `Date` ở lớp chuẩn hóa dữ liệu.

## 5. Ví dụ Java DSL hoàn chỉnh: hai luồng độc lập

Ví dụ dưới đây khai báo hai luồng trong cùng một cấu hình để so sánh. Mỗi luồng có channel vào, Delayer, và `QueueChannel` ra để kiểm thử dễ dàng. Trong hệ thống thực, đầu ra có thể là một Service Activator, Router, Gateway hoặc adapter.

**Phụ thuộc:** Spring Integration và `spring-boot-starter-integration` nếu dùng Spring Boot; các import sau minh họa với Java DSL của Spring Integration.

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
public class DelayPeriodConfig {

    @Bean("fixed.in")
    public MessageChannel fixedIn() {
        return new DirectChannel();
    }

    @Bean("fixed.out")
    public PollableChannel fixedOut() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow fixedDelayFlow() {
        return IntegrationFlow.from("fixed.in")
                .delay(delayer -> delayer
                        .messageGroupId("demo.fixed.delay.v1")
                        .defaultDelay(1_000L))
                .channel("fixed.out")
                .get();
    }

    @Bean("dynamic.in")
    public MessageChannel dynamicIn() {
        return new DirectChannel();
    }

    @Bean("dynamic.out")
    public PollableChannel dynamicOut() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow dynamicDelayFlow() {
        return IntegrationFlow.from("dynamic.in")
                .delay(delayer -> delayer
                        .messageGroupId("demo.dynamic.delay.v1")
                        .defaultDelay(1_500L)
                        .delayExpression("headers['delayMs']"))
                .channel("dynamic.out")
                .get();
    }
}
~~~

**Giải thích từng lựa chọn:**

1. `fixedDelayFlow()` dùng `defaultDelay(1_000L)` cho tất cả message. Không có biểu thức override.
2. `dynamicDelayFlow()` dùng header `delayMs` nếu hiện diện, ngược lại dùng 1.500 ms.
3. Hai `messageGroupId` khác nhau để phân biệt các nhóm message chờ. Điều này đặc biệt quan trọng khi chuyển sang `MessageGroupStore` dùng chung.
4. `DirectChannel` nhận message từ producer; các delay dương được phát tiếp qua scheduler về sau.
5. `QueueChannel` là endpoint kiểm thử có thể `receive(timeout)`. Nó không tự xử lý nghiệp vụ.

### Gửi message qua hai flow

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class DelayPublisher {
    private final MessageChannel fixedIn;
    private final MessageChannel dynamicIn;

    public DelayPublisher(MessageChannel fixedIn, MessageChannel dynamicIn) {
        this.fixedIn = fixedIn;
        this.dynamicIn = dynamicIn;
    }

    public void publish() {
        fixedIn.send(MessageBuilder.withPayload("FIXED-A").build());
        fixedIn.send(MessageBuilder.withPayload("FIXED-B").build());

        dynamicIn.send(MessageBuilder.withPayload("DEFAULT").build());
        dynamicIn.send(MessageBuilder.withPayload("URGENT")
                .setHeader("delayMs", 250L).build());
        dynamicIn.send(MessageBuilder.withPayload("LATER")
                .setHeader("delayMs", 3_000L).build());
    }
}
~~~

`DelayPublisher` chỉ là lớp minh họa; khi sử dụng trong ứng dụng, cần tiêm đúng bean channel `fixed.in` và `dynamic.in`, ví dụ bằng `@Qualifier`. Nếu cả năm message đến gần cùng thời điểm, `URGENT` có thể ra trước `DEFAULT`, `FIXED-A` và `LATER`. Delayer không bảo đảm thứ tự phát trùng thứ tự message đến khi các thời gian chờ khác nhau.

## 6. Kiểm thử khoảng chờ và cơ chế fallback

Đo thời gian bằng `System.nanoTime()` để so sánh khoảng chờ thực tế trong cùng tiến trình. Dùng `receive(timeout)` để tránh treo kiểm thử mãi mãi; không khẳng định message phải ra đúng ở một mili giây cụ thể.

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

@SpringJUnitConfig(DelayPeriodConfig.class)
class DelayPeriodTest {

    @Autowired
    @Qualifier("fixed.in")
    MessageChannel fixedIn;

    @Autowired
    @Qualifier("fixed.out")
    PollableChannel fixedOut;

    @Autowired
    @Qualifier("dynamic.in")
    MessageChannel dynamicIn;

    @Autowired
    @Qualifier("dynamic.out")
    PollableChannel dynamicOut;

    @Test
    void fixedPeriodAppliesToEveryMessage() {
        long start = System.nanoTime();
        assertTrue(fixedIn.send(MessageBuilder.withPayload("F1").build()));

        assertNull(fixedOut.receive(100), "Chưa được phát trước hạn 1 giây");
        Message<?> result = fixedOut.receive(3_000);

        assertNotNull(result);
        assertEquals("F1", result.getPayload());
        assertTrue(elapsedMs(start) >= 1_000L);
    }

    @Test
    void messageHeaderOverridesDefaultPeriod() {
        long start = System.nanoTime();
        assertTrue(dynamicIn.send(MessageBuilder.withPayload("URGENT")
                .setHeader("delayMs", 650L).build()));

        assertNull(dynamicOut.receive(100));
        Message<?> result = dynamicOut.receive(2_500);

        assertNotNull(result);
        assertEquals("URGENT", result.getPayload());
        assertTrue(elapsedMs(start) >= 650L);
    }

    @Test
    void absentHeaderUsesDynamicFlowsDefault() {
        long start = System.nanoTime();
        assertTrue(dynamicIn.send(MessageBuilder.withPayload("DEFAULT").build()));

        assertNull(dynamicOut.receive(100));
        Message<?> result = dynamicOut.receive(3_000);

        assertNotNull(result);
        assertEquals("DEFAULT", result.getPayload());
        assertTrue(elapsedMs(start) >= 1_500L);
    }

    private static long elapsedMs(long startNanos) {
        return TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startNanos);
    }
}
~~~

Chạy các kiểm thử cùng scheduler thực nghĩa là kết quả có thể đến **muộn hơn** số mili giây đã cấu hình. Khi CI chịu tải cao, hãy tăng timeout cho `receive(...)`, nhưng không giảm điều kiện kiểm tra “không đến trước hạn”. Không dùng `Thread.sleep(650)` rồi đòi chính xác tuyệt đối; kiểm tra hành vi ở đầu ra là bằng chứng phù hợp hơn.

Các ca kiểm thử cần mở rộng trong dự án thật:

- Header bằng `0L`: message đi qua ngay; kiểm tra tương tác với channel đồng bộ.
- Header âm: xác minh chính sách nghiệp vụ (chuyển ngay hoặc bị từ chối trước Delayer).
- Header bị thiếu: fallback về `defaultDelay`.
- Header có kiểu không hợp lệ: kiểm tra cách xử lý biểu thức và dữ liệu chuẩn hóa.
- `Date` trong tương lai và quá khứ: kiểm tra mốc tuyệt đối.
- Nhiều message cùng thời gian chờ: kiểm tra tải, thứ tự, metric và xử lý khi scheduler bận.
- Restart ứng dụng khi có message còn chờ: kiểm tra tính bền vững và khả năng phát lại.

## 7. Xử lý dữ liệu động an toàn

Nếu thời gian chờ đến từ API, message broker hoặc một hệ thống khác, không nên tin trực tiếp mọi giá trị header. Giá trị quá lớn khiến message bị giữ lâu ngoài dự kiến; kiểu dữ liệu sai có thể gây lỗi xử lý biểu thức; giá trị âm có thể làm mất bước chờ.

Đặt chính sách nghiệp vụ **trước Delayer**:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public boolean sendWithValidatedDelay(
        MessageChannel input, String payload, long requestedMs) {

    final long maximumMs = 15 * 60 * 1_000L;

    if (requestedMs < 0L || requestedMs > maximumMs) {
        throw new IllegalArgumentException("delayMs ngoài khoảng được phép");
    }

    return input.send(MessageBuilder.withPayload(payload)
            .setHeader("delayMs", requestedMs)
            .build());
}
~~~

Đoạn code ví dụ cho phép khoảng từ 0 đến 15 phút; hệ thống thực có thể đặt giới hạn theo loại sự kiện, SLA hoặc phân quyền. Nếu cần quy tắc *ưu tiên*, hãy đặt giá trị sau khi xác thực:

| Loại sự kiện | Delay được phép | Lý do |
| --- | --- | --- |
| Cảnh báo quan trọng | 0–500 ms | Không giữ cảnh báo quá lâu |
| Thông báo thường | 1.000–5.000 ms | Trì hoãn ngắn có kiểm soát |
| Nhắc thanh toán | Theo chính sách nghiệp vụ, có thể nhiều phút | Cần theo dõi trạng thái đơn hàng trước khi gửi |
| Lịch hẹn gửi đúng giờ | `Date` tuyệt đối đã chuẩn hóa | Phải xác định rõ múi giờ khi tạo lịch |

Với `Date`, chuyển thời gian địa phương có múi giờ thành một `Instant` rõ ràng rồi mới tạo `Date`. Tránh parse chuỗi “09:00” mà không biết ngày, múi giờ và quy tắc giờ mùa hè; các quyết định đó thuộc về lớp nghiệp vụ trước Delayer.

### Fallback không thay thế validation

`defaultDelay` là giá trị dự phòng khi biểu thức không cung cấp được độ trễ hợp lệ theo quy tắc của Delayer. Nó **không** có nhiệm vụ chặn payload độc hại, kiểm tra SLA hay sửa mọi dữ liệu lỗi. Hãy bảo đảm producer/Transformer tạo header có kiểu được chấp nhận, và có kiểm thử cho giá trị vắng mặt, sai kiểu, số rất lớn.

Nếu một lỗi đánh giá biểu thức được Spring Integration cấu hình bỏ qua, Delayer có thể dùng giá trị mặc định và ghi nhận lỗi ở log. Nếu ứng dụng cần thất bại rõ ràng khi dữ liệu delay không hợp lệ, có thể dùng `ignoreExpressionFailures(false)` và xử lý lỗi trước hoặc tại endpoint. Cách chọn phải nhất quán với yêu cầu nghiệp vụ; không được âm thầm fallback đối với message mà thời điểm phát là một cam kết.

## 8. Quan sát và vận hành

Một hệ thống ít phụ thuộc và dễ mở rộng cần theo dõi được **vì sao message được phát ở thời điểm đó**. Nên bổ sung các trường nghiệp vụ:

- `eventId`, `correlationId`: truy vết một message qua Filter, Transformer, Delayer và Router.
- `requestedDelayMs` hoặc `deliverAt`: thời gian chờ được yêu cầu sau validation.
- `receivedAt`: thời điểm nhận vào luồng (UTC).
- `releasedAt`: thời điểm bước sau Delayer thực sự thấy message.

Đo `actualWaitMs = releasedAt - receivedAt`, và nếu có mốc dự kiến, đo `scheduleLagMs = releasedAt - expectedReleaseAt`. Thời gian trễ giữa “đến hạn” và “thực sự phát” giúp nhận diện scheduler quá tải hoặc store chậm.

~~~mermaid
flowchart LR
    A[Nhận message] --> B[Filter + validate]
    B --> C[Transformer tính delay]
    C --> D[Delayer cố định hoặc động]
    D --> E{Router loại sự kiện}
    E --> F[Email handler]
    E --> G[Webhook handler]
    F --> H[Metric, log, tracing]
    G --> H
~~~

### Message store và restart

Nếu Delayer sử dụng store trong bộ nhớ, message còn chờ có thể mất khi ứng dụng dừng. Với thông báo quan trọng hoặc delay kéo dài, cân nhắc `JdbcMessageStore` (hay `MessageGroupStore` bền vững phù hợp), gắn cùng `messageGroupId` ổn định và kiểm tra việc khôi phục message sau restart.

Store bền vững không tự cung cấp bảo đảm *exactly once*. Consumer cần xử lý idempotent theo `eventId` hoặc khóa nghiệp vụ. Khi chạy nhiều instance, cần thiết kế cơ chế phối hợp thay vì mặc định rằng dùng chung một database là đủ để tránh phát message trùng.

### Lỗi khi phát và retry

Với delay dương, lỗi từ consumer xảy ra **sau** thời điểm producer đã gửi. Do đó producer có thể nhận kết quả gửi thành công trong khi bước downstream sau này thất bại. Hãy thiết kế error channel, chính sách retry và quan sát lỗi tại nhánh phát lại; không suy rằng `send() == true` đồng nghĩa nghiệp vụ hoàn thành.

Để phân biệt các vấn đề khi vận hành:

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Message đến ngay dù muốn chờ | Header `delayMs` có giá trị 0/âm, biểu thức sai hoặc message không đi qua Delayer |
| Mọi message đều chờ cùng thời gian | `delayExpression` chưa gắn đúng, header thiếu hoặc fallback luôn được áp dụng |
| Message đến muộn hơn lịch | Scheduler quá tải, xử lý downstream chậm, store chậm, ứng dụng vừa restart |
| Message mất sau restart | Đang dùng store trong bộ nhớ hoặc chưa cấu hình phục hồi |
| Một message được xử lý hai lần | Retry/phát lại sau lỗi hoặc cơ chế phân tán; kiểm tra idempotency |
| Gateway đồng bộ bị timeout | Response được Delayer phát sau timeout; cần thiết kế phản hồi bất đồng bộ hoặc điều chỉnh timeout theo nghiệp vụ |

## 9. Khi nào chọn từng cách?

Hãy dùng **cố định** khi toàn bộ message trong một endpoint tuân theo một chính sách thời gian như nhau. Cách này dễ giải thích, ít dữ liệu cần kiểm tra và hữu ích khi chỉ cần một khoảng chờ chung.

Hãy dùng **động theo header** khi mỗi message mang mức ưu tiên, SLA hoặc loại sự kiện khác nhau. Chuẩn hóa và giới hạn header trước khi đưa vào Delayer, rồi giữ `defaultDelay` làm fallback có chủ đích.

Hãy dùng **động theo mốc tuyệt đối `Date`** khi nghiệp vụ nói “phát tại thời điểm X”. Mốc này phải được tính bằng thời gian chuẩn hóa rõ ràng; nếu chính sách có thể thay đổi liên tục, cần thiết kế thêm cơ chế hủy/cập nhật lịch.

**Cả ba cách chỉ quyết định thời điểm phát từng message.** Nếu yêu cầu là hạn chế tốc độ, xử lý công việc định kỳ, hay giữ một workflow chờ phản hồi trong nhiều ngày, cần xem xét thêm rate limiter, scheduler nghiệp vụ, message broker, saga/workflow engine hoặc thành phần điều phối thích hợp.

## 10. Bài tập thực hành và câu hỏi tự kiểm tra

1. Cấu hình flow đầu tiên có delay cố định 800 ms; chứng minh bằng test rằng message không phát trước hạn.
2. Mở rộng flow động với các mức `NORMAL = 2000`, `HIGH = 200` và `DEFERRED = 10000`; đặt Transformer trước Delayer để sinh header `delayMs`.
3. Gửi một message có `delayMs = 0`, một message thiếu header và một message `delayMs = 3_000L`. Giải thích thứ tự phát có thể xảy ra.
4. Tạo một `Date` đại diện cho 30 giây trong tương lai từ `Instant`; gửi qua Delayer dùng `headers['deliverAt']` và đo độ lệch phát.
5. Giả lập scheduler chịu tải cao: độ trễ thực tế lớn hơn yêu cầu có nghĩa Delayer sai hay chỉ là phát muộn?
6. Thay store bằng một triển khai bền vững, cho ứng dụng restart khi đang có message chờ, và xác minh tác dụng phụ của consumer không bị nhân đôi.
7. Từ luồng `Filter → Transformer → Delayer → Router`, xác định vị trí nên kiểm tra input, tạo `correlationId`, đo `scheduleLagMs` và xử lý error channel.

## Tài liệu tham khảo

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): cấu hình độ trễ mặc định, biểu thức, thời gian tuyệt đối, scheduler và lưu trữ message.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): khai báo `IntegrationFlow` và endpoint bằng Java DSL.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): lưu trữ message đang chờ và các lựa chọn persistence.
