# Priority header và comparator trong Spring Integration

## 1. Priority giải quyết bài toán gì?

Trong một hệ thống xử lý thông điệp, không phải yêu cầu nào cũng cần được xử lý theo đúng thứ tự nhận vào. Chẳng hạn, một message thông báo sự cố có thể cần được lấy khỏi hàng đợi trước message đồng bộ báo cáo định kỳ. **Priority Channel** là Enterprise Integration Pattern dành cho tình huống đó: các message **đang chờ trong hàng đợi** được lựa chọn theo mức ưu tiên.

Trong Spring Integration, \`PriorityChannel\` cung cấp một \`PollableChannel\` có khả năng sắp thứ tự lấy message dựa trên **header \`priority\` mặc định** hoặc một \`Comparator<Message<?>>\` do ứng dụng cung cấp.

Bài **“Priority header và comparator”** thuộc chương **Priority** của module **SPRING_INTEGRATION_PATTERN**. Module hướng đến xây dựng luồng message ít phụ thuộc, dễ mở rộng bằng Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation; Priority Channel bổ sung cơ chế lựa chọn *message nào được lấy ra tiếp theo* khi có nhiều message đang đợi xử lý.

Sau bài học, bạn có thể:

1. Gắn và đọc header \`priority\` đúng kiểu dữ liệu.
2. Phân biệt thứ tự theo priority với FIFO và thứ tự hoàn tất nghiệp vụ.
3. Viết \`Comparator<Message<?>>\` để sắp xếp theo quy tắc riêng.
4. Định nghĩa cách xử lý khi hai message có cùng mức ưu tiên.
5. Kiểm thử Priority Channel bằng các message nhỏ, có kết quả xác định.
6. Nhận biết các giới hạn về starvation, capacity, retry và xử lý song song.

## 2. Priority Channel sắp xếp cái gì?

Hãy xét ba message đã được đưa vào hàng đợi trước khi consumer bắt đầu lấy:

| Thứ tự gửi | Payload | Header \`priority\` | Thứ tự lấy mong đợi |
| --- | --- | --- | --- |
| 1 | \`"report"\` | 1 | 3 |
| 2 | \`"order"\` | 5 | 2 |
| 3 | \`"incident"\` | 9 | 1 |

Với comparator mặc định của \`PriorityChannel\`, message có **priority cao hơn** được lấy ra trước message có priority thấp hơn.

~~~mermaid
flowchart LR
    P["Producer"] -->|"report: 1"| Q["PriorityChannel"]
    P -->|"order: 5"| Q
    P -->|"incident: 9"| Q
    Q -->|"1. incident (9)"| C["Consumer / Poller"]
    Q -->|"2. order (5)"| C
    Q -->|"3. report (1)"| C
~~~

Điều này có ba giới hạn quan trọng:

- **Ưu tiên áp dụng cho message còn đang nằm trong queue.** Nếu consumer đã lấy \`"report"\` trước khi \`"incident"\` đến, message mới không thể thu hồi công việc đang chạy.
- **Priority Channel không quyết định route.** Router chọn *kênh nào nhận message*; Priority Channel quyết định *message nào trong hàng đợi của kênh được lấy tiếp*.
- **Thứ tự lấy khác thứ tự hoàn tất.** Khi consumer xử lý song song, message được lấy trước vẫn có thể hoàn tất sau message khác.

Đối chiếu với \`QueueChannel\` thông thường:

| Loại channel | Thứ tự lấy message | Khi nào nên chọn |
| --- | --- | --- |
| \`QueueChannel\` | FIFO (theo thứ tự vào queue) | Cần xử lý theo thứ tự nhận |
| \`PriorityChannel\` | Theo mức ưu tiên hoặc comparator | Muốn tác vụ khẩn được lấy trước từ backlog |
| \`DirectChannel\` | Giao trực tiếp cho subscriber | Cần chuyển tiếp đồng bộ, không có queue ưu tiên |
| \`ExecutorChannel\` | Giao việc qua executor | Cần xử lý bất đồng bộ; thứ tự hoàn tất tùy executor |

## 3. Header \`priority\`: biểu diễn và sử dụng

Spring Integration nhận diện tên header \`priority\` thông qua \`IntegrationMessageHeaderAccessor.PRIORITY\`. Header này có kiểu **\`Integer\`**, ví dụ:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> urgent = MessageBuilder.withPayload("incident-42")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 9)
        .setHeader("requestId", "req-42")
        .build();

Integer priority = (Integer) urgent.getHeaders()
        .get(IntegrationMessageHeaderAccessor.PRIORITY);
// priority == 9
~~~

Trên message vừa tạo, \`priority=9\` là metadata về thứ tự xử lý, còn \`requestId\` phục vụ truy vết nghiệp vụ. Spring Integration không tự biến message thành tác vụ khẩn chỉ vì payload chứa từ \`"urgent"\`; nếu dùng comparator mặc định, phải thiết lập header tương ứng trước khi message vào \`PriorityChannel\`.

### Chọn thang priority nhất quán

Framework không tự định nghĩa các mức “Thấp”, “Cao”, “Khẩn cấp” cho nghiệp vụ của bạn. Ứng dụng nên công bố một quy ước, chẳng hạn:

| Mức nghiệp vụ | Giá trị \`priority\` |
| --- | --- |
| Đồng bộ nền | 1 |
| Xử lý thông thường | 5 |
| Sự cố cần xử lý gấp | 9 |

Ở bảng này, **số càng lớn càng được lấy trước**. Quy ước có thể dùng số khác, nhưng cần nhất quán tại mọi producer và qua mọi Transformer, Gateway hoặc adapter. Không nhầm với cơ chế ưu tiên nơi **số nhỏ nghĩa là mức khẩn cao hơn**, ví dụ một vài hệ thống đánh số P1 là nghiêm trọng nhất. Nếu nghiệp vụ dùng P1/P2/P3, hãy **ánh xạ sang số sắp xếp** hoặc dùng comparator phù hợp.

### Missing hoặc sai kiểu header

Hãy xác định chính sách tại điểm vào queue:

- **Thiếu \`priority\`:** Có dùng mức mặc định do ứng dụng quy định không? Nếu có, nên gắn giá trị đó bằng bước chuẩn hóa header trước khi vào queue để kiểm thử rõ ràng.
- **\`priority="9"\` là String:** Khác \`priority=9\` là Integer. Đừng giả định \`PriorityChannel\` tự ép chuỗi thành số. Kiểm tra kiểu và chuyển đổi có chủ đích.
- **Giá trị ngoài phạm vi nghiệp vụ:** Nếu hệ thống chỉ cho phép 1–9, hãy xác thực các giá trị \`-10\`, \`0\`, \`1000\` trước khi enqueue; đây là quy tắc của ứng dụng.

Ví dụ hàm xác thực header trước khi dùng:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

static int validatedPriority(Message<?> message) {
    Object raw = message.getHeaders()
            .get(IntegrationMessageHeaderAccessor.PRIORITY);

    if (!(raw instanceof Integer value) || value < 1 || value > 9) {
        throw new IllegalArgumentException(
                "priority must be an Integer from 1 to 9");
    }
    return value;
}
~~~

Hàm trên biểu diễn **chính sách nghiệp vụ mẫu**, không phải giới hạn bắt buộc của Spring Integration. Tách bước xác thực khỏi việc sắp hàng đợi giúp báo lỗi rõ ràng và tránh để comparator gặp kiểu dữ liệu không phù hợp trong lúc queue đang thao tác.

## 4. Comparator mặc định của PriorityChannel

Spring Integration cung cấp constructor \`new PriorityChannel()\` hoặc \`new PriorityChannel(capacity)\`. Khi không truyền comparator tùy biến, channel sử dụng cơ chế so sánh theo header \`priority\`.

~~~java
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

PriorityChannel channel = new PriorityChannel(10);

channel.send(MessageBuilder.withPayload("low")
        .setHeader("priority", 1)
        .build());
channel.send(MessageBuilder.withPayload("medium")
        .setHeader("priority", 5)
        .build());
channel.send(MessageBuilder.withPayload("high")
        .setHeader("priority", 9)
        .build());

Message<?> first = channel.receive(0);  // "high"
Message<?> second = channel.receive(0); // "medium"
Message<?> third = channel.receive(0);  // "low"
~~~

**Điểm mấu chốt:** Cả ba message đã nằm trong queue **trước** lần \`receive\` đầu tiên. Đây là điều kiện để phép thử chứng minh thứ tự lấy từ backlog. Nếu test vừa gửi vừa có poller đang chạy, message priority thấp có thể đã được lấy ra trước khi message priority cao đến.

### Khi hai message có cùng priority

Ví dụ:

~~~text
Input:
  A: priority=9
  B: priority=9
  C: priority=1

Kỳ vọng chắc chắn theo mức ưu tiên:
  {A, B} được lấy trước C.

Chưa có hợp đồng tie-break:
  không được mặc định A luôn đứng trước B.
~~~

\`PriorityChannel\` không phải là queue FIFO ổn định cho các message có khóa so sánh bằng nhau. Nếu cần thứ tự xác định giữa hai message cùng priority, phải thiết kế **tiêu chí thứ hai** trong comparator (ví dụ số thứ tự enqueue do ứng dụng cấp).

## 5. Ví dụ kiểm thử có thể chạy: priority header

Đoạn sau là một lớp **JUnit 5** độc lập; phần kiểm thử comparator mặc định không cần khởi tạo Spring Boot context hoặc một poller thực tế. Cần dependency Spring Integration và JUnit/AssertJ tương thích.

Tạo \`src/test/java/example/PriorityHeaderComparatorTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Comparator;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

class PriorityHeaderComparatorTest {

    private static Message<String> message(String payload, int priority) {
        return MessageBuilder.withPayload(payload)
                .setHeader(
                        IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("requestId", "test-" + payload)
                .build();
    }

    private static String nextPayload(PollableChannel channel) {
        Message<?> result = channel.receive(1_000);
        assertThat(result).isNotNull();
        return (String) result.getPayload();
    }

    @Test
    void higher_priority_is_polled_first() {
        PriorityChannel channel = new PriorityChannel(10);

        assertThat(channel.send(message("report", 1))).isTrue();
        assertThat(channel.send(message("order", 5))).isTrue();
        assertThat(channel.send(message("incident", 9))).isTrue();

        assertThat(nextPayload(channel)).isEqualTo("incident");
        assertThat(nextPayload(channel)).isEqualTo("order");
        assertThat(nextPayload(channel)).isEqualTo("report");
        assertThat(channel.receive(0)).isNull();
    }

    @Test
    void each_priority_is_kept_in_the_message_header() {
        PriorityChannel channel = new PriorityChannel(10);

        channel.send(message("low", 1));
        channel.send(message("high", 9));

        Message<?> first = channel.receive(1_000);
        Message<?> second = channel.receive(1_000);

        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.getPayload()).isEqualTo("high");
        assertThat(first.getHeaders().get(
                IntegrationMessageHeaderAccessor.PRIORITY)).isEqualTo(9);
        assertThat(second.getPayload()).isEqualTo("low");
        assertThat(second.getHeaders().get(
                IntegrationMessageHeaderAccessor.PRIORITY)).isEqualTo(1);
        assertThat(first.getHeaders().get("requestId"))
                .isEqualTo("test-high");
    }

    @Test
    void high_priority_arriving_after_enqueue_can_overtake_low() {
        PriorityChannel channel = new PriorityChannel(10);

        channel.send(message("low-first", 1));
        channel.send(message("high-later", 9));

        // Chưa có consumer lấy "low-first", nên ưu tiên được áp dụng.
        assertThat(nextPayload(channel)).isEqualTo("high-later");
        assertThat(nextPayload(channel)).isEqualTo("low-first");
    }

    private static Message<String> businessMessage(
            String payload, int urgency, long enqueueOrder) {
        return MessageBuilder.withPayload(payload)
                .setHeader("businessUrgency", urgency)
                .setHeader("enqueueOrder", enqueueOrder)
                .build();
    }

    private static Comparator<Message<?>> businessComparator() {
        return Comparator
                .<Message<?>>comparingInt(m ->
                        (Integer) m.getHeaders().get("businessUrgency"))
                .reversed()
                .thenComparingLong(m ->
                        (Long) m.getHeaders().get("enqueueOrder"));
    }

    @Test
    void custom_comparator_breaks_ties_by_enqueue_order() {
        PriorityChannel channel =
                new PriorityChannel(10, businessComparator());

        // Thứ tự send cố ý khác thứ tự khóa enqueueOrder.
        channel.send(businessMessage("urgent-later", 9, 3L));
        channel.send(businessMessage("background", 1, 1L));
        channel.send(businessMessage("urgent-earlier", 9, 2L));

        assertThat(nextPayload(channel)).isEqualTo("urgent-earlier");
        assertThat(nextPayload(channel)).isEqualTo("urgent-later");
        assertThat(nextPayload(channel)).isEqualTo("background");
        assertThat(channel.receive(0)).isNull();
    }
}
~~~

**Đọc kết quả:**

- \`higher_priority_is_polled_first\`: ba message gửi theo thứ tự **1 → 5 → 9**, được lấy theo thứ tự **9 → 5 → 1**.
- \`each_priority_is_kept_in_the_message_header\`: priority chỉ tác động thứ tự queue; message còn giữ payload và header nghiệp vụ cần thiết.
- \`high_priority_arriving_after_enqueue_can_overtake_low\`: message đến sau có thể vượt lên **nếu** message trước chưa được lấy ra.
- \`custom_comparator_breaks_ties_by_enqueue_order\`: cùng mức khẩn 9 thì \`enqueueOrder\` nhỏ hơn đứng trước; mức khẩn 1 vẫn xếp sau.

Các test này tự tạo và tiêu thụ queue riêng, không phụ thuộc lịch poller, thread khác hoặc dữ liệu tồn dư từ test trước. Nếu cần kiểm tra cả wiring trong \`IntegrationFlow\`, dùng flow test riêng ở phần sau.

## 6. Comparator tùy biến: cách đọc thứ tự cho đúng

Constructor \`PriorityChannel(int capacity, Comparator<Message<?>> comparator)\` cho phép tự xác định thứ tự. Comparator tuân theo hợp đồng Java:

| Kết quả \`compare(a, b)\` | Ý nghĩa trong hàng đợi ưu tiên |
| --- | --- |
| Số âm | \`a\` đứng trước \`b\` |
| Số 0 | Hai message bằng nhau về mặt thứ tự do comparator quy định |
| Số dương | \`a\` đứng sau \`b\` |

Do đó, nếu **priority cao đứng trước**, comparator phải trả số âm khi so sánh message có \`priority=9\` với message có \`priority=1\`. \`Comparator.comparingInt(...).reversed()\` thể hiện chính sách này rõ ràng.

### Comparator theo hai tiêu chí

Một quy tắc nghiệp vụ dễ hiểu:

1. **Mức khẩn cao hơn** được lấy trước.
2. Trong cùng mức khẩn, **số thứ tự enqueue nhỏ hơn** được lấy trước.

~~~java
Comparator<Message<?>> ordering = Comparator
        .<Message<?>>comparingInt(message ->
                (Integer) message.getHeaders().get("businessUrgency"))
        .reversed()
        .thenComparingLong(message ->
                (Long) message.getHeaders().get("enqueueOrder"));

PriorityChannel channel = new PriorityChannel(100, ordering);
~~~

\`businessUrgency\` và \`enqueueOrder\` là **header do ứng dụng tự định nghĩa**. Khi truyền comparator riêng, \`PriorityChannel\` dùng tiêu chí của comparator; header \`priority\` mặc định sẽ **không tự động** được kết hợp vào thứ tự nếu bạn không đưa nó vào hàm so sánh.

Không dùng \`message.getHeaders().getId()\` để thay cho thứ tự enqueue: UUID không phản ánh một trình tự gửi tăng dần. Tương tự, \`timestamp\` của message có thể trùng hoặc phản ánh thời điểm tạo message ở producer, không phải thứ tự nhận vào queue. Nếu cần FIFO trong cùng priority, hãy cấp số thứ tự đơn điệu ở đúng ranh giới enqueue, có cơ chế xử lý trùng khóa hoặc nhiều producer.

### Quy tắc thiết kế comparator an toàn

- **Nhất quán:** Cùng hai message thì comparator nên cho cùng kết quả trong suốt thời gian chúng nằm trong queue.
- **Bắc cầu:** Nếu A trước B và B trước C thì A phải trước C; tránh logic đặc biệt khiến thứ tự mâu thuẫn.
- **Không gây side effect:** Đừng ghi database, gọi API, thay đổi payload hoặc headers trong \`compare\`.
- **Không dựa trực tiếp vào giờ hiện tại để “tăng priority”:** Priority queue không tự sắp xếp lại toàn bộ phần tử chỉ vì thời gian trôi qua.
- **Không giả định header luôn hợp lệ:** Xác thực kiểu, dải giá trị và sự hiện diện ở bước nhập liệu; xử lý default một cách có chủ đích.
- **Có tie-breaker khi cần:** Comparator trả 0 cho hai message không bảo đảm FIFO giữa chúng.

Ví dụ comparator sai về ý định:

~~~java
// SAI nếu muốn "số lớn hơn thì ưu tiên hơn":
Comparator<Message<?>> wrong = Comparator.comparingInt(
        message -> (Integer) message.getHeaders().get("priority"));

// ĐÚNG cho cùng chính sách:
Comparator<Message<?>> correct =
        Comparator.<Message<?>>comparingInt(message ->
                (Integer) message.getHeaders().get("priority"))
                .reversed();
~~~

Comparator \`wrong\` đặt số nhỏ trước số lớn. Test dùng **hai message với priority khác nhau** sẽ bắt được lỗi đảo chiều này.

## 7. Tích hợp PriorityChannel vào IntegrationFlow

\`PriorityChannel\` là **PollableChannel**, vì vậy consumer trong Spring Integration thường cần **poller** để lấy message. Ví dụ minh họa cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
class PriorityFlowConfiguration {

    @Bean("work.priority")
    PriorityChannel priorityWork() {
        return new PriorityChannel(100);
    }

    @Bean("work.done")
    QueueChannel done() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow priorityConsumer() {
        return IntegrationFlow.from("work.priority",
                        source -> source.poller(
                                Pollers.fixedDelay(500)
                                        .maxMessagesPerPoll(1)))
                .handle(String.class,
                        (payload, headers) -> "processed:" + payload)
                .channel("work.done")
                .get();
    }
}
~~~

Với cấu hình trên, producer gửi message vào \`work.priority\`; poller định kỳ lấy message tiếp theo, handler xử lý payload và phát reply tới \`work.done\`. Giá trị \`500\` là thời gian giữa các lần kích hoạt poller trong ví dụ, **không** phải thời hạn nghiệp vụ hoặc cam kết độ trễ.

~~~mermaid
flowchart LR
    IN["Gateway / Transformer / Router"] --> Q["PriorityChannel\nqueue theo priority"]
    CLOCK["Poller"] --> Q
    Q --> H["Service Activator"]
    H --> OUT["Output Channel"]
    H -. "Exception" .-> ERR["Error flow theo cấu hình"]
~~~

**Vì sao không dùng flow trên để assert chính xác ba message luôn ra theo 9, 5, 1?** Poller đang chạy có thể lấy message đầu tiên trước khi hai message còn lại được enqueue. Khi kiểm thử chính sách **thứ tự trong queue**, cách xác định nhất là **gửi đủ backlog trước khi bắt đầu \`receive\`**, như các unit test ở mục 5. Khi kiểm thử **wiring và xử lý nghiệp vụ**, dùng context, output channel, tín hiệu hoàn tất và thời gian chờ hữu hạn.

Nếu muốn kiểm thử poller một cách xác định, cần chủ động kiểm soát thời điểm kích hoạt (ví dụ khởi động endpoint sau khi tạo backlog hoặc điều khiển trigger/poller trong môi trường test). Không nên dựa vào \`Thread.sleep\` để hy vọng queue đã đầy trước khi poller chạy.

## 8. Capacity, backpressure và giới hạn của ưu tiên

Một \`PriorityChannel\` có thể được cấu hình giới hạn dung lượng, ví dụ \`new PriorityChannel(100)\`. Khi queue đã đầy, việc gửi có thể phải đợi chỗ trống hoặc thất bại theo timeout/cấu hình của channel.

Điều quan trọng: **priority cao không có nghĩa được quyền chen vào queue đã đầy** bằng cách tự động đẩy một message priority thấp ra ngoài. Đây là hai chính sách khác nhau:

1. **Admission/backpressure:** Khi queue đầy, có chấp nhận message mới hay không?
2. **Ordering:** Trong các message đã nằm trong queue, message nào sẽ được lấy trước?

Ví dụ test một queue có sức chứa 2:

~~~java
@Test
void full_priority_queue_cannot_accept_unlimited_messages() {
    PriorityChannel channel = new PriorityChannel(2);

    assertThat(channel.send(message("low", 1))).isTrue();
    assertThat(channel.send(message("medium", 5))).isTrue();

    // Timeout 0: không chờ có chỗ trống.
    assertThat(channel.send(message("urgent", 9), 0)).isFalse();

    assertThat(nextPayload(channel)).isEqualTo("medium");
    assertThat(nextPayload(channel)).isEqualTo("low");
}
~~~

Đoạn test này có thể thêm vào lớp \`PriorityHeaderComparatorTest\` ở mục 5. Nó cho thấy **queue đầy là một điều kiện độc lập với mức ưu tiên**. Nếu nghiệp vụ muốn dành chỗ riêng cho yêu cầu khẩn, hãy thiết kế thêm capacity riêng, phân tách queue, admission control hoặc chính sách loại bỏ rõ ràng; \`PriorityChannel\` mặc định không tự thay message cũ bằng message khẩn mới.

### Starvation

Nếu liên tục có message \`priority=9\`, message \`priority=1\` có thể chờ rất lâu. Đây là **starvation**: một loại công việc bị trì hoãn vì loại khác luôn được ưu tiên.

Các cách kiểm soát theo yêu cầu vận hành gồm:

- Giới hạn lượng việc của từng mức ưu tiên trong mỗi chu kỳ xử lý.
- Chia luồng theo nhóm ưu tiên và cấp tài nguyên/consumer riêng.
- Có SLA hoặc giới hạn thời gian chờ tối đa để điều phối lại.
- Dùng cơ chế **aging** có thiết kế: tăng quyền ưu tiên của message theo thời gian qua bước sắp xếp lại hoặc tái đưa vào queue, không kỳ vọng comparator đọc đồng hồ tự cập nhật heap.

Kiểm thử starvation cần workload dài hơn kiểm thử thứ tự queue đơn lẻ: phát một luồng message priority cao trong khi có message thấp đang chờ, rồi xác minh chính sách đảm bảo tiến độ của message thấp.

## 9. Quan hệ với Router, Filter, retry và correlation

Priority Channel thường là một phần của pipeline lớn hơn:

~~~mermaid
flowchart TD
    A["Input"] --> B{"Router"}
    B -->|"online"| C["Header Enricher\npriority=9"]
    B -->|"batch"| D["Header Enricher\npriority=1"]
    C --> E["PriorityChannel"]
    D --> E
    E --> P["Poller + Service Activator"]
    P --> OUT["Output"]
    P -. "Lỗi sau nhiều lần thử" .-> ERR["Error channel / recovery"]
~~~

### Router và Filter

Router quyết định đường đi; Filter loại message theo điều kiện; PriorityChannel xếp thứ tự các message **đã được chấp nhận vào cùng một queue**. Nếu Filter loại một message priority cao, nó không tham gia thứ tự trong queue. Vì vậy test nên phân biệt:

- **Routing/filtering:** Message có được phép vào \`work.priority\` hay không?
- **Ordering:** Khi nhiều message đã vào, thứ tự lấy đúng không?

### Transformer và Header Enricher

Nếu priority được tính từ payload (chẳng hạn \`severity="CRITICAL"\`), bạn có thể dùng Header Enricher trước PriorityChannel để biến dữ liệu nghiệp vụ thành \`priority\` số. Test cần xác minh header đúng **trước khi enqueue**, vì sửa priority sau khi message đã nằm trong queue không tự làm queue sắp xếp lại.

### Retry và error channel

Một message priority cao được lấy ra trước nhưng handler có thể thất bại và được retry. Các lần retry có thể giữ worker lâu, gây ảnh hưởng đến message khác. Chính sách retry quyết định thời gian chiếm tài nguyên, còn PriorityChannel chỉ quyết định thứ tự lấy message khi chúng đang chờ.

Nếu lỗi được xử lý bằng cách đưa message trở lại queue, hãy định nghĩa rõ:

- Priority gốc có được giữ không?
- Có cần giảm ưu tiên hoặc thêm thời gian trì hoãn để tránh retry liên tục không?
- Message có giữ \`requestId\`, correlation và khóa idempotency không?
- Khi retry hết lượt, message đi đến error channel/dead-letter đúng chính sách nào?

Không giả định chỉ cần header \`priority\` là hệ thống tự bảo đảm **exactly-once**, thứ tự hoàn tất hoặc retry an toàn.

### Splitter, Aggregator và correlation

Khi Splitter tạo nhiều fragment, ưu tiên có thể gắn lên message con. Nhưng nếu fragment cùng nhóm được lấy với tốc độ khác nhau, Aggregator vẫn phải dựa vào \`correlationId\`, \`sequenceNumber\`, \`sequenceSize\` hoặc release strategy được cấu hình để ghép nhóm.

Nếu tất cả fragment có \`priority=9\`, điều này **không** có nghĩa chúng sẽ tự được lấy liên tục như một nhóm. Message của nhóm khác cũng có thể cùng mức ưu tiên. Test cần kiểm tra riêng **ordering của queue** và **độ đúng của grouping**.

## 10. Ma trận kiểm thử Priority header và comparator

| Tình huống | Dữ liệu tối thiểu | Assertion quan trọng |
| --- | --- | --- |
| Mức cao lấy trước | Hai message priority 1 và 9 | Nhận 9 trước 1 khi cả hai đã nằm trong queue |
| Nhiều mức | Ba message priority 1, 5, 9 | Nhận 9, 5, 1 |
| Đảo thứ tự gửi | Gửi 1 rồi 9 | Nhận 9 rồi 1 nếu chưa có consumer lấy |
| Giữ payload/header | Message priority 9, có \`requestId\` | Payload và header nghiệp vụ không đổi |
| Hai message đồng priority | Hai message priority 9 | Không dựa vào FIFO mặc định; nếu cần, bổ sung comparator phụ |
| Comparator theo nghiệp vụ | \`businessUrgency\` và \`enqueueOrder\` | Khẩn cao trước; cùng khẩn thì order nhỏ trước |
| Sai chiều comparator | Priority 1 và 9 | Test fail nếu comparator trả 1 trước 9 |
| Thiếu header | Message không có priority | Chính sách default/validation đúng yêu cầu |
| Header sai kiểu | Priority là String \`"9"\` | Được từ chối hoặc chuẩn hóa có chủ đích trước queue |
| Queue đầy | Capacity 2, gửi 3 message | Gửi thứ ba theo timeout/capacity policy |
| Consumer đã nhận việc | Gửi thấp, consumer lấy, sau đó gửi cao | Không giả định cao có thể hủy thấp đang chạy |
| Retry hoặc lỗi handler | Một message được chọn rồi handler lỗi | Retry/error handling đúng chính sách; không nhầm ordering với delivery |

## 11. Bài thực hành

### Bài A — Mức ưu tiên theo SLA

Định nghĩa mức \`CRITICAL=9\`, \`NORMAL=5\`, \`BACKGROUND=1\`. Gửi ba message theo thứ tự BACKGROUND, NORMAL, CRITICAL vào \`PriorityChannel\` khi chưa có consumer. Viết JUnit test khẳng định thứ tự lấy là CRITICAL, NORMAL, BACKGROUND, đồng thời payload và \`requestId\` không bị thay đổi.

### Bài B — Comparator cho P1/P2/P3

Hệ thống hỗ trợ mức \`P1\` nghiêm trọng nhất, \`P3\` ít nghiêm trọng nhất. Viết comparator đọc header nghiệp vụ \`incidentLevel\` và sắp xếp đúng thứ tự P1 → P2 → P3. Thêm test với hai message P1 khác nhau và một quy tắc tie-break cụ thể. Nếu dùng \`String\`, không so sánh bằng thứ tự từ điển khi cách đặt tên cấp độ có thể thay đổi.

### Bài C — Header sai kiểu hoặc thiếu

Gửi một message thiếu priority và một message có \`priority="9"\` dưới dạng String qua bước validation ở trước queue. Chọn chính sách rõ ràng: gắn mặc định, chuẩn hóa hoặc từ chối. Test phải chứng minh không có message dữ liệu sai lọt vào queue trước khi được chuẩn hóa.

### Bài D — Khi queue đầy

Tạo \`PriorityChannel(2)\`; gửi hai message mức 1 và 5, rồi gửi một message mức 9 với timeout 0. Giải thích vì sao message mức 9 không nhất thiết được chấp nhận. Đề xuất một chính sách backpressure phù hợp và viết test chứng minh.

### Bài E — Chèn poller và xử lý song song

Từ cấu hình \`PriorityFlowConfiguration\`, tạo backlog trước khi cho consumer chạy, kiểm tra thứ tự message được **lấy**. Sau đó cho phép xử lý song song với hai thời gian xử lý khác nhau và so sánh thứ tự **hoàn tất**. Ghi rõ mức bảo đảm thứ tự mà ứng dụng thực sự cần.

## 12. Checklist trước khi đưa vào luồng thực tế

1. Producer có gắn \`priority\` đúng kiểu \`Integer\` và đúng thang nghiệp vụ không?
2. Comparator có trả số âm khi message **nên được lấy trước** không?
3. Có cần thứ tự ổn định cho hai message đồng mức ưu tiên không? Nếu có, tiêu chí phụ là gì?
4. Comparator có thuần, nhất quán và không phụ thuộc dữ liệu mutable hoặc đồng hồ thay đổi trong queue không?
5. Queue có capacity và timeout phù hợp với lưu lượng lớn không?
6. Có kế hoạch cho starvation hoặc message priority thấp chờ quá lâu không?
7. Test thứ tự có enqueue đủ backlog **trước khi** polling bắt đầu không?
8. Có phân biệt thứ tự poll với thứ tự hoàn tất khi dùng nhiều consumer không?
9. Header nghiệp vụ, correlation và cơ chế retry/error vẫn giữ đúng hợp đồng không?
10. Mỗi bài test có thể chạy độc lập, không bị ảnh hưởng bởi queue còn dư từ test khác không?

**Kết quả cần đạt:** Khi nhìn vào một \`PriorityChannel\`, bạn phải xác định được **giá trị nào quyết định priority**, **comparator đặt message nào trước**, **điều gì xảy ra khi bằng nhau** và **thứ tự này còn hiệu lực đến đâu trong pipeline**. Kiểm thử từng điều đó giúp thêm cơ chế ưu tiên vào Spring Integration mà vẫn giữ được khả năng mở rộng và quan sát luồng xử lý.

### Tham khảo

- Spring Integration Reference — [PriorityChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html).
- Spring Integration API — [PriorityChannel](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/channel/PriorityChannel.html).
