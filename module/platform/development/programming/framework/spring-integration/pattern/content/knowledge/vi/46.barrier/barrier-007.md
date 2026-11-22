# Duplicate trigger và duplicate barrier trong Spring Integration

## 1. Bài toán: một sự kiện được gửi hai lần

Trong hệ thống tích hợp, sự kiện **đánh thức luồng đang chờ** có thể xuất hiện nhiều lần: broker giao lại sau khi mất acknowledgment, adapter retry, producer gửi lại vì timeout hoặc hai listener cùng nhận một sự kiện. Nếu không thiết kế rõ, một **duplicate trigger** có thể bị diễn giải như tín hiệu hoàn tất cho một lượt xử lý khác. Tương tự, hai request đồng thời đi vào **cùng một barrier với cùng correlation** tạo ra xung đột: cả hai đều muốn sở hữu vị trí chờ của một khóa.

Bài **“Duplicate trigger và duplicate barrier”** thuộc chương **Barrier** của module **SPRING_INTEGRATION_PATTERN**. Module này học cách triển khai Enterprise Integration Patterns bằng Spring Integration, kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation để tạo những luồng message ít phụ thuộc, dễ mở rộng, có thể kiểm thử và theo dõi. Ở đây chúng ta xem xét cụ thể **Thread Barrier** và khả năng chống tác động của message trùng.

Sau bài học, bạn có thể:

1. Giải thích cách \`BarrierMessageHandler\` khớp request với trigger theo correlation.
2. Phân biệt **duplicate request**, **duplicate trigger** và **duplicate barrier endpoint**.
3. Hiểu giới hạn “một request đang chờ trên mỗi correlation tại một thời điểm”.
4. Phân tích trigger đến trước, trigger đến muộn, timeout và việc tái sử dụng correlation.
5. Viết test với Java, JUnit 5, \`ExecutorService\` và các channel trong bộ nhớ.
6. Thiết kế deduplication, \`attemptId\`, idempotency và cơ chế theo dõi kết quả mà không nhầm chúng với khả năng mặc định của Barrier.

## 2. Thread Barrier hoạt động như thế nào?

Trong Spring Integration, **\`BarrierMessageHandler\`** là một \`MessageHandler\` đồng thời triển khai **\`MessageTriggerAction\`**. Khi request đi vào barrier, thread xử lý request có thể bị treo để đợi một trigger có **correlation key tương ứng**. Khi trigger đến và ghép cặp thành công, barrier cho phép thread tiếp tục và tạo output.

~~~mermaid
sequenceDiagram
    participant R as Request thread
    participant B as BarrierMessageHandler
    participant T as Trigger thread
    participant O as Output
    R->>B: request(correlation=A)
    Note over R,B: Request chờ tối đa requestTimeout
    T->>B: trigger(correlation=A)
    B-->>R: giải phóng request A
    B-->>O: kết quả ghép request + trigger
~~~

Các thành phần cần hiểu:

| Thành phần | Chức năng | Điểm kiểm thử |
| --- | --- | --- |
| Request input | Luồng cần đợi điều kiện bên ngoài | Có đang chờ đúng correlation? |
| \`BarrierMessageHandler\` | Ghép request–trigger và đánh thức luồng | Chỉ giải phóng khi khóa khớp |
| Trigger input | Tín hiệu hoàn tất/acknowledgment | Có thể trùng, sớm hoặc muộn |
| \`CorrelationStrategy\` | Xác định khóa từ message | Request và trigger có cùng khóa? |
| \`requestTimeout\` | Thời hạn request chờ trigger | Quá hạn xử lý theo policy |
| \`triggerTimeout\` | Thời hạn trigger chờ request | Không giữ thread trigger vô hạn |
| Discard channel | Nhận trigger quá hạn hoặc request không tới kịp, theo cấu hình | Có ghi nhận late/orphan trigger không? |
| Output processor | Tạo kết quả sau khi ghép cặp | Có đúng dữ liệu từ request và trigger không? |

**Mặc định**, correlation được xác định qua header \`IntegrationMessageHeaderAccessor.CORRELATION_ID\`. Nếu dùng tên header nghiệp vụ khác, cần cấu hình một \`CorrelationStrategy\` phù hợp cho **cả request và trigger**.

Theo tài liệu Spring Integration, payload của output mặc định là một **collection chứa payload request và payload trigger**, với headers được hợp nhất theo \`DefaultAggregatingMessageGroupProcessor\`. Đây là ghép **một request với một trigger**, không phải Aggregator tổng hợp số lượng fragment tùy ý.

## 3. Ba loại trùng cần tách biệt

~~~mermaid
flowchart TD
    IN["Sự kiện lặp"] --> D{"Lặp loại gì?"}
    D -->|"Request lặp cùng correlation"| R["Duplicate request / pending barrier"]
    D -->|"ACK/trigger lặp"| T["Duplicate trigger"]
    D -->|"Hai Barrier endpoint độc lập"| B["Duplicate barrier instance"]
    R --> ER["Xung đột một slot chờ"]
    T --> ET["Có thể thành trigger orphan/late"]
    B --> EB["Hai lần release hoặc side effect ở hai flow"]
~~~

### A. Duplicate request vào cùng barrier

~~~text
Thread-1: request(key=order-7) -> đã vào barrier, đang chờ.
Thread-2: request(key=order-7) -> cũng cố vào barrier.

Barrier chỉ cho phép một request đang chờ tại cùng key.
Request thứ hai bị từ chối bằng exception khi trùng correlation đồng thời.
~~~

**Đây là hành vi được tài liệu Spring Integration công bố:** chỉ có một thread đang treo cho một correlation tại một thời điểm; một request đồng thời khác dùng cùng khóa có thể phát sinh exception. Correlation đó **có thể được dùng lại sau này**, khi không còn request đang chờ. Vì vậy, giới hạn này **không phải idempotency vĩnh viễn**.

### B. Duplicate trigger cho một request

~~~text
Request A đang chờ.
Trigger A lần 1 -> giải phóng Request A.
Trigger A lần 2 -> không còn Request A để giải phóng.
~~~

Đừng giả định trigger lần hai sẽ tự động bị ghi nhận là duplicate. Nó có thể rơi vào nhánh **trigger đến trước** của một lần ghép cặp mới, đợi tới \`triggerTimeout\` hoặc được đưa tới discard channel theo cấu hình và thời điểm xảy ra. Mặc định barrier **không thay thế** một hệ thống lưu dấu những ACK nghiệp vụ đã xử lý.

### C. Hai barrier instance hoặc hai flow cùng xử lý một yêu cầu

~~~text
Barrier instance A nhận request order-7 và trigger order-7.
Barrier instance B nhận cùng request order-7 và trigger order-7.

Nếu cả hai flow hoạt động độc lập, cả hai đều có thể phát output.
~~~

Giới hạn một pending correlation thuộc về **cơ chế quản lý trạng thái của từng handler**, không đương nhiên bảo đảm “một lần xử lý duy nhất” trên **toàn bộ ứng dụng, mọi replica và mọi broker consumer**. Khi triển khai nhiều instance, phải có owner rõ ràng, phân vùng theo key hoặc cơ chế idempotency ở ranh giới tác dụng phụ.

## 4. Ma trận hành vi và hợp đồng mong đợi

| Tình huống | Sequence sự kiện | Điều cần quan sát |
| --- | --- | --- |
| Bình thường | Request A → Trigger A | Một kết quả cho A |
| Trigger không khớp | Request A → Trigger B | A chưa được release bởi B |
| Duplicate request đồng thời | Request A → Request A nữa | Một pending A; request trùng bị báo lỗi |
| Duplicate trigger sau hoàn tất | Request A → Trigger A → Trigger A lần hai | Không có output nghiệp vụ thứ hai cho A |
| Trigger đến trước | Trigger A → Request A | Có thể ghép nếu request đến trong \`triggerTimeout\` |
| Trigger đến sớm nhưng không có request | Trigger A → hết \`triggerTimeout\` | Trigger được xử lý hết hạn/discard theo cấu hình |
| Request timeout trước trigger | Request A → hết \`requestTimeout\` → Trigger A | A đã timeout không tự hồi sinh thành success |
| Tái dùng correlation cho attempt mới | A/attempt-1 hoàn tất → A/attempt-2 | Trigger cũ không mở nhầm attempt mới |
| Hai barrier instance | A và B đều nhận cùng request/trigger | Không tạo side effect kép ngoài chính sách |
| Retry/re-delivery | ACK bị giao lại | Dedup hoặc idempotency hoạt động |

Phân biệt **hành vi framework** và **yêu cầu nghiệp vụ**: mặc định Barrier quản lý ghép cặp trong một khoảng chờ; việc bảo đảm một đơn hàng chỉ được xử lý một lần phải được thiết kế thêm.

## 5. Hai timeout độc lập và một nguy cơ khó thấy

Từ Spring Integration 5.4, Barrier hỗ trợ **\`requestTimeout\`** và **\`triggerTimeout\`** riêng:

- \`requestTimeout\`: request thread chờ trigger bao lâu.
- \`triggerTimeout\`: trigger thread chờ request bao lâu nếu trigger đến trước hoặc đến khi request đã timeout.

~~~mermaid
sequenceDiagram
    participant T as Trigger thread
    participant B as Barrier
    participant R as Request thread
    T->>B: trigger(A)
    Note over T,B: Chờ tối đa triggerTimeout
    alt Request A đến kịp
        R->>B: request(A)
        B-->>R: release
    else Không có request
        Note over T,B: Hết triggerTimeout
        B-->>T: kết thúc chờ
        Note over B: discard trigger nếu có discard channel
    end
~~~

**Điểm nguy hiểm:** Một trigger dư của attempt cũ có thể còn đang chờ. Nếu attempt mới dùng **cùng correlation** trong khi trigger cũ chưa hết hạn, nó có nguy cơ ghép cặp sai. Cách an toàn hơn là dùng khóa ghép theo **mỗi lần thử** hoặc **mỗi operation**:

~~~text
Không đủ an toàn khi retry:
  correlationId = "tenant-a:order-7"

Phân biệt từng lần thử:
  correlationId = "tenant-a:order-7:attempt-1"
  correlationId = "tenant-a:order-7:attempt-2"
~~~

Khi sử dụng \`attemptId\`, request và trigger của **cùng attempt** phải sử dụng cùng key; trigger đến từ attempt cũ không được tạo output cho attempt mới. Đồng thời vẫn cần một **idempotency key nghiệp vụ** độc lập (ví dụ \`tenantId + orderId\`) để tránh tạo đơn hàng hai lần giữa các attempt.

## 6. Cấu hình Barrier với hai đường request và trigger

Ví dụ sau sử dụng **Spring Integration 6.x**, Java 17 và các channel trong bộ nhớ. Hai đường request và trigger được cấu hình tách biệt nhưng cùng sử dụng **một \`BarrierMessageHandler\`**.

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.aggregator.BarrierMessageHandler;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageHandler;
import org.springframework.beans.factory.annotation.Qualifier;

@Configuration
@EnableIntegration
public class BarrierConfiguration {

    @Bean("barrier.requests")
    DirectChannel requestChannel() {
        return new DirectChannel();
    }

    @Bean("barrier.triggers")
    DirectChannel triggerChannel() {
        return new DirectChannel();
    }

    @Bean("barrier.released")
    QueueChannel releasedChannel() {
        return new QueueChannel();
    }

    @Bean("barrier.discard")
    QueueChannel discardedTriggers() {
        return new QueueChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "barrier.requests")
    BarrierMessageHandler barrierHandler(
            @Qualifier("barrier.released") QueueChannel released,
            @Qualifier("barrier.discard") QueueChannel discarded) {
        // Request đợi tối đa 3 giây; trigger đến trước đợi 250 ms.
        BarrierMessageHandler barrier =
                new BarrierMessageHandler(3_000L, 250L);
        barrier.setOutputChannel(released);
        barrier.setDiscardChannel(discarded);
        return barrier;
    }

    @Bean
    @ServiceActivator(inputChannel = "barrier.triggers")
    MessageHandler triggerHandler(BarrierMessageHandler barrierHandler) {
        return barrierHandler::trigger;
    }
}
~~~

Khi gọi \`send()\` vào \`barrier.requests\`, **thread gửi có thể bị block** tới khi trigger khớp hoặc hết \`requestTimeout\`. Vì thế không nên viết một test gọi \`requests.send(...)\` trên thread JUnit rồi mới gọi \`triggers.send(...)\` trên **cùng thread**: test sẽ mắc kẹt tại request và chưa tới câu lệnh trigger. Phải dùng các thread khác nhau hoặc cấu trúc bất đồng bộ phù hợp.

Nếu muốn dùng XML, mô hình tương đương có dạng:

~~~xml
<int:barrier id="myBarrier"
             input-channel="barrierRequests"
             output-channel="barrierReleased"
             correlation-strategy-expression="headers['correlationId']"
             discard-channel="barrierDiscard"
             request-timeout="3000"
             trigger-timeout="250"/>

<int:outbound-channel-adapter input-channel="barrierTriggers"
                              ref="myBarrier.handler"
                              method="trigger"/>
~~~

Đây là **sơ đồ cấu hình XML minh họa**; khi dùng XML thực tế, thêm namespace/schema và xác minh thuộc tính timeout tương thích phiên bản Spring Integration của dự án. Với Java configuration ở trên, khóa mặc định dùng \`IntegrationMessageHeaderAccessor.CORRELATION_ID\`.

## 7. Gắn correlation và tạo message tối thiểu

Hai message khác payload nhưng cùng correlation:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

static Message<String> request(String key) {
    return MessageBuilder.withPayload("work:" + key)
            .setHeader(
                    IntegrationMessageHeaderAccessor.CORRELATION_ID, key)
            .setHeader("requestId", key)
            .build();
}

static Message<String> trigger(String key) {
    return MessageBuilder.withPayload("ack:" + key)
            .setHeader(
                    IntegrationMessageHeaderAccessor.CORRELATION_ID, key)
            .setHeader("eventType", "ACK")
            .build();
}
~~~

\`requestId\` là header theo dõi nghiệp vụ; \`correlationId\` là khóa Barrier dùng để ghép cặp. Trong ví dụ này, ta cố ý đặt chúng có cùng giá trị để dễ đọc, nhưng **không bắt buộc phải giống nhau**.

Nếu đưa \`tenantId\` hay \`attemptId\` vào khóa, hãy làm nhất quán tại cả request và trigger. Cần tránh trường hợp request có String \`"7"\` còn trigger có Integer \`7\`: nhìn log có thể giống nhau, nhưng hai khóa không nhất thiết so sánh bằng nhau.

## 8. Ví dụ JUnit 5: kiểm thử duplicate request và duplicate trigger

Các test dưới đây tạo **Spring context** thực, chạy request qua \`DirectChannel\` và đọc kết quả ở \`QueueChannel\`. Có thể dùng dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Trong dự án thật, đặt cấu hình \`BarrierConfiguration\` từ mục 6 ở package phù hợp và tạo lớp \`BarrierDuplicateTest\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Collection;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(BarrierConfiguration.class)
class BarrierDuplicateTest {

    @Autowired
    @Qualifier("barrier.requests")
    MessageChannel requests;

    @Autowired
    @Qualifier("barrier.triggers")
    MessageChannel triggers;

    @Autowired
    @Qualifier("barrier.released")
    QueueChannel released;

    @Autowired
    @Qualifier("barrier.discard")
    QueueChannel discard;

    private final ExecutorService workers =
            Executors.newFixedThreadPool(3);

    @AfterEach
    void shutdown() {
        workers.shutdownNow();
    }

    static Message<String> msg(String payload, String correlation) {
        return MessageBuilder.withPayload(payload)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        correlation)
                .build();
    }

    @Test
    void one_request_and_one_trigger_produce_one_result()
            throws Exception {
        Future<Boolean> pending = workers.submit(() ->
                requests.send(msg("work-A", "job-A")));

        // Trigger có thể đến trước khi request thực sự treo;
        // triggerTimeout cho phép hai bên gặp nhau trong hạn.
        assertThat(triggers.send(msg("ack-A", "job-A"))).isTrue();
        assertThat(pending.get(2, TimeUnit.SECONDS)).isTrue();

        Message<?> output = released.receive(1_000);
        assertThat(output).isNotNull();
        assertThat(output.getPayload()).isInstanceOf(Collection.class);
        assertThat(((Collection<?>) output.getPayload()).stream()
                .map(Object::toString).toList())
                .contains("work-A", "ack-A");
        assertThat(released.receive(0)).isNull();
        assertThat(discard.receive(0)).isNull();
    }

    @Test
    void duplicate_trigger_after_completion_does_not_release_again()
            throws Exception {
        Future<Boolean> pending = workers.submit(() ->
                requests.send(msg("work-D", "job-D")));
        assertThat(triggers.send(msg("ack-D", "job-D"))).isTrue();
        assertThat(pending.get(2, TimeUnit.SECONDS)).isTrue();

        assertThat(released.receive(1_000)).isNotNull();
        // Không còn request D đang chờ, trigger thứ hai không phải
        // là một sự kiện hoàn tất mới của request đã kết thúc.
        triggers.send(msg("ack-D-again", "job-D"));

        // Cấu hình có discard channel và triggerTimeout hữu hạn.
        Message<?> discarded = discard.receive(1_000);
        assertThat(discarded).isNotNull();
        assertThat(discarded.getPayload()).isEqualTo("ack-D-again");
        assertThat(released.receive(0)).isNull();
    }

    @Test
    void simultaneous_duplicate_requests_cannot_both_wait()
            throws Exception {
        ExecutorCompletionService<Throwable> completions =
                new ExecutorCompletionService<>(workers);
        CountDownLatch start = new CountDownLatch(1);

        for (int i = 0; i < 2; i++) {
            completions.submit(() -> {
                start.await();
                try {
                    requests.send(msg("work-X", "job-X"));
                    return null;
                } catch (RuntimeException failure) {
                    return failure;
                }
            });
        }

        start.countDown();
        // Một trong hai lời gọi kết thúc trước khi có trigger.
        // Theo hợp đồng Barrier, lời gọi này phải báo lỗi trùng key.
        Future<Throwable> first = completions.poll(
                1_500, TimeUnit.MILLISECONDS);
        assertThat(first).isNotNull();
        assertThat(first.get()).isNotNull();

        // Giải phóng request hợp lệ còn đang chờ.
        assertThat(triggers.send(msg("ack-X", "job-X"))).isTrue();
        Future<Throwable> second = completions.poll(
                2, TimeUnit.SECONDS);
        assertThat(second).isNotNull();
        assertThat(second.get()).isNull();
        assertThat(released.receive(1_000)).isNotNull();
        assertThat(released.receive(0)).isNull();
    }
}
~~~

### Diễn giải bài test

- **Happy path:** Một request và một trigger cùng correlation tạo một output. Test kiểm tra cả payload request và trigger, nhưng không ràng buộc thứ tự phần tử trong collection nếu đó không phải hợp đồng nghiệp vụ.
- **Duplicate trigger:** Chỉ gửi trigger thứ hai sau khi request đầu đã hoàn tất. Với \`discardChannel\` và \`triggerTimeout\` đã khai báo, test theo dõi nó ở đường discard và đảm bảo không có release thứ hai.
- **Duplicate request:** Hai request được khởi động đồng thời với cùng correlation; một sẽ bị báo lỗi theo giới hạn chỉ một pending thread, sau đó trigger giải phóng request còn lại.

**Giới hạn của test:** Đây là bài minh họa với timeout đủ ngắn để chạy trong test nhưng có thể bị ảnh hưởng bởi máy CI quá tải hoặc phiên bản thư viện. Tránh assert **thông điệp exception chính xác**; ưu tiên kiểm tra trạng thái, tổng số output và loại lỗi khi đã biết contract cụ thể. Nếu test concurrency nhạy timing, bổ sung hook kiểm soát thời điểm request vào handler trước khi kiểm tra exception.

## 9. Kiểm thử correlation và trigger đến trước

Không phải duplicate nào cũng có cùng ý nghĩa thời gian. Xét hai trường hợp:

### Trigger sai correlation

~~~text
Request: correlation=order-11:attempt-1
Trigger: correlation=order-12:attempt-1

Kỳ vọng: trigger của order-12 không giải phóng request order-11.
~~~

Trong test có thể gửi request A trên một thread; trigger B trên thread khác. Trigger B có thể đợi đến \`triggerTimeout\` rồi đi vào discard channel, trong khi A tiếp tục chờ. Sau đó gửi trigger A và xác minh A có output. Không được dùng \`receive(0) == null\` duy nhất như chứng cứ cuối cùng khi cả hai phía đang chạy bất đồng bộ; cần đợi tới các mốc xử lý được kiểm soát.

### Trigger đến trước request

~~~text
t0: Trigger A đến trước, bắt đầu chờ tới triggerTimeout.
t1: Request A tới trong hạn.
t2: Hai phía được ghép và request được giải phóng.
~~~

Việc trigger đến trước có thể **hợp lệ** nếu protocol cho phép. Nhưng với hệ thống dùng trigger như ACK sau khi request được gửi, trigger đến trước đôi khi là dấu hiệu message cũ hoặc duplicate. Khi đó policy có thể **từ chối trigger sớm** thay vì cho Barrier giữ nó, hoặc chỉ nhận nếu có trạng thái request hợp lệ đã được đăng ký.

## 10. Tại sao chỉ dựa vào correlationId là chưa đủ?

Đây là kịch bản dễ gây sai lệch:

~~~mermaid
sequenceDiagram
    participant R as Request flow
    participant B as Barrier
    participant T as Trigger source
    R->>B: order-7, attempt=1
    T->>B: ACK attempt=1
    B-->>R: release attempt=1
    T->>B: ACK attempt=1 bị gửi lại
    Note over T,B: Trigger dư còn chờ một thời gian
    R->>B: order-7, attempt=2 (dùng lại key cũ)
    Note over B: Có nguy cơ ghép trigger cũ vào request mới
~~~

Giải pháp không phải chỉ tăng \`requestTimeout\`. Hãy định nghĩa hai loại khóa:

| Khóa | Phạm vi | Mục đích |
| --- | --- | --- |
| \`operationKey\` | Một thao tác nghiệp vụ xuyên các lần retry | Idempotency, tránh side effect lặp |
| \`correlationId\` | Một lượt request/trigger cụ thể | Ghép đúng request và ACK |
| \`attemptId\` | Một lần thử trong operation | Ngăn trigger cũ ghép attempt mới |
| \`eventId\` | Một sự kiện ACK logic | Nhận diện bản redelivery của cùng ACK |

Ví dụ:

~~~text
operationKey = tenant-a/order-7
attemptId    = 2
correlationId = tenant-a/order-7/attempt-2
eventId      = broker-ack-event-813
~~~

Khi retry, **operationKey giữ nguyên**, nhưng **correlationId đổi** theo attempt nếu protocol tạo ACK cho từng attempt. Hệ thống cần biết ACK của \`attempt-1\` không đủ điều kiện mở \`attempt-2\`.

Không có quy ước nào được Spring Integration tự tạo cho những khóa này. Các producer, adapter, Router/Transformer và consumer phải thống nhất và truyền đầy đủ headers.

## 11. Chặn trigger trùng trước Barrier

**Idempotent Receiver** là một Enterprise Integration Pattern dành cho trường hợp message được gửi lại. Spring Integration hỗ trợ cơ chế như \`IdempotentReceiverInterceptor\`, \`MetadataStoreSelector\` và \`ConcurrentMetadataStore\` để lựa chọn message đã gặp hay chưa.

Đối với ACK/trigger, một khóa dedup phù hợp thường là:

~~~text
tenantId + operationKey + attemptId + logicalAckType
~~~

Đừng chọn **message ID ngẫu nhiên của mỗi bản giao lại** nếu broker tạo message mới cho mỗi retry: hai bản của cùng một ACK nghiệp vụ có thể nhận ID mới và không bị coi là trùng.

Ví dụ mô hình Java thuần kiểm tra ACK trước khi chuyển đến trigger channel:

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

final class AckAdmission {

    private final Set<String> accepted =
            ConcurrentHashMap.newKeySet();

    boolean accept(
            String tenantId,
            String operationId,
            int attemptId,
            String ackType) {
        String key = tenantId + "/" + operationId + "/"
                + attemptId + "/" + ackType;
        return accepted.add(key);
    }
}
~~~

Và unit test:

~~~java
@Test
void duplicate_ack_for_same_attempt_is_rejected() {
    AckAdmission admission = new AckAdmission();

    assertThat(admission.accept("t1", "order-7", 1, "BROKER_ACK"))
            .isTrue();
    assertThat(admission.accept("t1", "order-7", 1, "BROKER_ACK"))
            .isFalse();
    assertThat(admission.accept("t1", "order-7", 2, "BROKER_ACK"))
            .isTrue();
}
~~~

**Rất quan trọng:** Đây chỉ là **mô hình dedup trong một JVM**, không phải giải pháp production hoàn chỉnh. Nó còn các giới hạn:

1. Không chia sẻ state giữa nhiều replica hoặc qua restart.
2. Không có TTL, khiến tập \`accepted\` tăng vô hạn.
3. Đánh dấu đã nhận **trước khi gọi \`trigger()\`** có thể làm mất cơ hội retry nếu trigger thất bại hoặc hết \`triggerTimeout\`.
4. Không có trạng thái phân biệt \`RECEIVED\`, \`MATCHED\`, \`COMPLETED\`, \`EXPIRED\`.
5. Việc ghép khóa bằng chuỗi dấu \`/\` có thể gây trùng nếu giá trị thành phần không được chuẩn hóa; nên dùng cấu trúc khóa có kiểu hoặc encoding an toàn.

Trong sản phẩm thật, nên xác định **thời điểm commit dedup state** và atomicity với side effect. Tùy hạ tầng, dùng metadata store bền vững, transaction, outbox/inbox hoặc state machine rõ ràng. Một bản ghi dedup ở trước barrier có thể chỉ là \`RECEIVED\`; khi Barrier ghép thành công mới chuyển thành \`COMPLETED\`. Xử lý lỗi/timeout phải có cơ chế recovery thay vì khóa vĩnh viễn.

## 12. Hai barrier instance độc lập: một loại duplicate khác

Giả sử hai service replica cùng xử lý message từ publish-subscribe:

~~~mermaid
flowchart TD
    REQ["Request order-7"] --> A["Barrier A"]
    REQ --> B["Barrier B"]
    ACK["ACK order-7"] --> A
    ACK --> B
    A --> OA["Release A"]
    B --> OB["Release B"]
    OA --> E["Side effect"]
    OB --> E
~~~

Mỗi Barrier có thể tự ghép request và trigger riêng. **Không có bảo đảm one-time toàn cục chỉ vì correlation ID trùng nhau.** Tùy yêu cầu, có thể:

- Chọn **một owner** cho mỗi operation/correlation.
- Chia partition theo correlation để mọi message cùng operation đi đến một consumer phù hợp.
- Dùng competing consumers khi muốn phân chia việc, không broadcast cùng công việc tới mọi instance.
- Lưu trạng thái nghiệp vụ với khóa duy nhất và kiểm tra idempotency trước side effect.
- Kiểm thử khi scale từ một sang nhiều replica, failover và redelivery.

Một hiểu nhầm cần tránh: **duplicate barrier instance** không nhất thiết là “hai lần gọi tới một \`BarrierMessageHandler\`”. Đó có thể là hai handler riêng biệt ở hai Spring contexts hoặc một flow vô tình đăng ký endpoint tương đương hai lần. Cần kiểm tra cả wiring và số subscriber, không chỉ test một bean.

## 13. Retry, timeout và đường lỗi

Barrier có thể kết thúc chờ vì timeout hoặc vì trigger. Theo tài liệu, thuộc tính \`requiresReply\` quyết định khi **request timeout**:

- \`requiresReply=false\` (mặc định): handler có thể không tạo reply và luồng kết thúc tại đó.
- \`requiresReply=true\`: có thể ném \`ReplyRequiredException\`.

Trigger đến quá muộn có thể được chuyển vào **discard channel** nếu cấu hình. Nhưng discard không đồng nghĩa message bị ghi bền vững hoặc đã được xử lý nghiệp vụ. Nếu discard channel cũng thất bại, cần có policy riêng.

~~~text
Request A -> Barrier -> timeout
                         |
                         +--> no reply hoặc exception theo requiresReply

Trigger A đến sau       -> chờ triggerTimeout nếu không có request
                         |
                         +--> discard channel nếu cấu hình
~~~

Lưu ý **timeout của Barrier khác replyTimeout của Gateway**. Gateway có thể timeout trước, trong khi request thread ở Barrier vẫn tiếp tục chờ; hoặc Barrier timeout rồi Gateway không nhận được reply. Test cần xác định timeout budget toàn luồng và chính sách late result, không đánh đồng hai mốc.

### Retry khi Barrier đã giải phóng

Một trigger trùng không nhất thiết tạo output lần hai từ **cùng request đã hoàn tất**. Tuy nhiên, nếu retry tạo request mới với cùng correlation, trigger dư hoặc trigger phát lại có thể ghép vào request mới. Vì vậy nên:

1. Tách \`operationId\` và \`attemptId\`.
2. Dedup ACK logic theo attempt hoặc sự kiện đã định nghĩa.
3. Có trạng thái kết thúc rõ ràng cho operation.
4. Đảm bảo side effect idempotent dù Gateway hoặc worker bị retry.
5. Có metrics và log cho duplicate/late/orphan trigger.

## 14. Những bẫy về đồng thời và kiểm thử

| Sai lầm | Vì sao nguy hiểm | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Gửi request rồi trigger tuần tự trên cùng thread DirectChannel | Thread đang block tại Barrier, chưa tới trigger | Gửi từ thread khác |
| Dùng \`Thread.sleep\` để đoán request đã vào barrier | Test phụ thuộc scheduler | Dùng latch, channel điều khiển được, timeout hữu hạn |
| Mặc định trigger trùng tự bị bỏ | Có thể chờ hoặc gặp request attempt mới | Dedup và correlation theo attempt |
| Chỉ test một request/trigger happy path | Không phát hiện duplicate hoặc cross-correlation | Test double trigger/double request |
| So sánh toàn bộ headers output với request | Framework hợp nhất metadata | Assert khóa nghiệp vụ và payload cần thiết |
| Dùng correlation bằng orderId qua mọi retry | Trigger cũ có thể ảnh hưởng retry mới | Thêm attempt/version vào correlation |
| Chỉ dựa vào một handler để bảo đảm exactly-once | Nhiều instance vẫn có state riêng | Idempotent side effect và owner rõ |
| Bỏ qua \`triggerTimeout\` | Trigger đến trước có thể giữ thread | Đặt timeout riêng, worker pool có giới hạn |
| Chỉ theo dõi success count | Không thấy duplicate/orphan | Metrics và discard channel |
| Không dọn executor và pending state | Test tiếp theo bị ảnh hưởng | \`shutdownNow()\`, correlation duy nhất, cleanup |

## 15. Metric và trace cần bổ sung

Một số chỉ số hữu ích:

| Metric | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| \`barrier_pending_requests\` | Số request đang chờ trigger | Cảnh báo backlog/blocked threads |
| \`barrier_request_timeout_total\` | Request quá hạn | Theo flow và nhóm nghiệp vụ |
| \`barrier_trigger_timeout_total\` | Trigger không gặp request đúng hạn | Phát hiện trigger cũ/orphan |
| \`barrier_duplicate_request_total\` | Request cùng key đến đồng thời | Kiểm tra producer retry/race |
| \`barrier_duplicate_trigger_total\` | ACK bị giao lặp | Kiểm tra broker, retry, adapter |
| \`barrier_late_trigger_total\` | Trigger quá hạn/discard | Đối soát thời gian chờ |
| \`barrier_release_total\` | Số lần barrier ghép cặp thành công | Kiểm tra tỷ lệ hoàn thành |
| \`barrier_wait_seconds\` | Độ trễ chờ release | Đánh giá SLA và thread utilization |

Đây là **tên metric gợi ý**, không khẳng định Spring Integration tự xuất đúng các tên này. Đặt nhãn theo endpoint/route/loại lỗi với cardinality hợp lý; không dùng \`requestId\` hoặc \`correlationId\` cho mỗi event làm label metric. Thay vào đó, ghi các khóa này trong **structured logs/traces** để truy vết.

Đối với log lỗi, nên ghi \`operationId\`, \`attemptId\`, \`correlationId\`, trạng thái và nguyên nhân; tránh log payload nhạy cảm hoặc token.

## 16. Các bài thực hành

### Bài A — Tái hiện duplicate trigger

Tạo Barrier có \`requestTimeout=3_000\`, \`triggerTimeout=250\` và discard channel. Gửi một request A và trigger A, xác nhận đúng một output. Sau khi request hoàn tất, gửi lại trigger A. Kiểm tra không có output thứ hai và trigger dư được quan sát theo discard/error policy thực tế.

### Bài B — Hai request đồng thời cùng correlation

Tạo hai producer thread, cùng gửi request với correlation \`"job-17"\` vào cùng handler. Test phải cho thấy chỉ có một request được treo; request còn lại bị báo lỗi theo giới hạn của Barrier. Gửi đúng một trigger để giải phóng request hợp lệ. Giới hạn thời gian của tất cả futures.

### Bài C — Trigger cũ và retry attempt mới

Cho operation \`order-7\` có attempt 1 và attempt 2. Sau khi attempt 1 hoàn tất, gửi lại ACK attempt 1; rồi bắt đầu request attempt 2. Thiết kế correlation chứa attempt ID, xác nhận ACK cũ không giải phóng attempt 2. Chỉ ACK attempt 2 mới tạo output hợp lệ.

### Bài D — Trigger đến trước

Cho trigger \`"job-21"\` đến trước request. Với \`triggerTimeout\` hữu hạn, test hai trường hợp: request đến kịp và hai phía ghép cặp; request không đến khiến trigger đi vào discard channel hoặc đường xử lý quá hạn tương ứng.

### Bài E — Barrier nhân đôi ở hai instance

Dựng hai cấu hình Barrier độc lập, giả lập cùng request/ACK được broadcast tới cả hai. Xác minh cả hai có khả năng release nếu không có owner/idempotency toàn cục. Sau đó thêm cơ chế sở hữu operation hoặc dedup side effect để tổng số lần thực hiện nghiệp vụ đúng hợp đồng.

### Bài F — Dedup bền vững

Đưa ACK qua một \`MetadataStoreSelector\` hoặc cơ chế inbox bền vững theo khóa \`tenant + operation + attempt + ACK type\`. Kiểm thử redelivery cùng ACK, retry khi trạng thái chưa hoàn tất, và dọn bản ghi đã hết hạn mà không cho phép trigger cũ mở một attempt mới.

## 17. Tiêu chí hoàn thành

Một luồng dùng Barrier được kiểm thử đầy đủ về duplicate khi có thể chứng minh:

1. Request và trigger có cùng correlation ghép thành **một kết quả hợp lệ**.
2. Trigger khác correlation không giải phóng nhầm request.
3. Hai request đồng thời cùng correlation không cùng chiếm trạng thái chờ.
4. Duplicate trigger không tạo thêm kết quả nghiệp vụ trái contract.
5. Trigger đến trước hoặc quá hạn được xử lý theo \`triggerTimeout\`/discard policy.
6. Retry dùng attempt/version để trigger cũ không mở nhầm request mới.
7. Hai handler/replica không tạo tác dụng phụ lặp nếu nghiệp vụ yêu cầu exactly-once ở tầng ứng dụng.
8. Test có timeout hữu hạn, quản lý thread đúng cách và có log/metric để tra cứu duplicate.

**Kết luận:** \`BarrierMessageHandler\` quản lý ghép cặp và chờ tín hiệu theo correlation; nó **không tự trở thành một bộ khử trùng lặp phân tán**. Sự khác biệt giữa duplicate request đang chờ, duplicate trigger sau hoàn tất và duplicate barrier instance quyết định cách xử lý đúng. Khi bổ sung correlation theo attempt, dedup có trạng thái, idempotency ở side effect, timeout/discard rõ ràng và kiểm thử concurrency, luồng Spring Integration có thể tiếp tục an toàn ngay cả khi broker, Gateway hoặc adapter phát lại message.

### Tài liệu tham khảo

- [Spring Integration Reference — Thread Barrier](https://docs.spring.io/spring-integration/reference/6.5/barrier.html): cơ chế request/trigger, correlation, timeout, discard và giới hạn một pending request cho mỗi correlation.
- [Spring Integration API — BarrierMessageHandler (6.4.x)](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/aggregator/BarrierMessageHandler.html): các constructor, \`trigger()\`, \`setDiscardChannel()\` và output processor.
- [Spring Integration API — MessageTriggerAction](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/handler/MessageTriggerAction.html): interface của trigger.
