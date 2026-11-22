# Queue capacity của Priority Channel trong Spring Integration

## 1. Tại sao hàng đợi ưu tiên vẫn cần giới hạn sức chứa?

**Priority Channel** là một Enterprise Integration Pattern cho phép lấy các message đang chờ theo mức ưu tiên, thay vì luôn theo thứ tự FIFO. Trong Spring Integration, \`PriorityChannel\` là một \`PollableChannel\`: producer gửi message vào queue và consumer hoặc poller lấy message ra để xử lý.

Giả sử hệ thống tiếp nhận yêu cầu xử lý đơn hàng:

- Message \`NORMAL\` được gắn \`priority=1\`.
- Message \`URGENT\` được gắn \`priority=9\`.
- Handler chỉ xử lý được một lượng message nhất định trong mỗi giây.

Khi producer gửi nhanh hơn khả năng tiêu thụ, backlog sẽ tăng. Dù Priority Channel biết nên lấy message nào trước, nó vẫn cần một chính sách **queue capacity** để bảo vệ tài nguyên và tạo tín hiệu **backpressure** (áp lực ngược) khi nhận quá nhiều công việc.

Bài học **“Queue capacity của priority channel”** thuộc chương **Priority** của module **SPRING_INTEGRATION_PATTERN**. Module tập trung triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; phối hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, kiểm thử và theo dõi các nhánh xử lý. Capacity là điểm giao giữa **định tuyến**, **độ ưu tiên** và **bảo vệ hệ thống khi quá tải**.

Sau bài này, bạn có thể:

1. Phân biệt giới hạn số message đang chờ với thứ tự ưu tiên lấy message.
2. Cấu hình \`PriorityChannel\` có capacity hữu hạn bằng Java hoặc XML.
3. Hiểu các trường hợp \`send(message)\`, \`send(message, 0)\` và \`send(message, timeout)\`.
4. Kiểm chứng rằng message priority cao **không tự thay thế** message priority thấp khi queue đầy.
5. Viết JUnit test cho trạng thái queue đầy, giải phóng slot và kết quả polling.
6. Lựa chọn chính sách quá tải, kích thước queue, metric và cơ chế recovery phù hợp.

## 2. Capacity và priority là hai bài toán khác nhau

**Capacity** trả lời: *Có thể giữ tối đa bao nhiêu message chưa được consumer lấy?*

**Priority** trả lời: *Trong những message đã được chấp nhận và còn đang chờ, message nào được lấy ra tiếp theo?*

~~~mermaid
flowchart LR
    P["Producer"] -->|"send"| A{"Còn capacity?"}
    A -->|"Có"| Q["PriorityChannel\nqueue có giới hạn"]
    A -->|"Không"| B["Chờ chỗ trống / timeout / từ chối"]
    Q -->|"Ưu tiên cao lấy trước"| C["Consumer / Poller"]
    C --> O["Handler"]
~~~

Thử ví dụ với \`capacity=2\`:

| Thời điểm | Hành động | Queue sau hành động | Kết quả |
| --- | --- | --- | --- |
| 1 | Gửi \`LOW\`, priority 1 | \`[LOW]\` | Chấp nhận |
| 2 | Gửi \`MEDIUM\`, priority 5 | \`[LOW, MEDIUM]\` | Chấp nhận, queue đầy |
| 3 | Gửi \`URGENT\`, priority 9 với timeout 0 | Không đổi | Không còn chỗ nên gửi không thành công |
| 4 | Consumer lấy một message | Còn \`LOW\` | \`MEDIUM\` được lấy trước vì priority 5 lớn hơn 1 |
| 5 | Producer gửi lại \`URGENT\` | \`[LOW, URGENT]\` | Chấp nhận vì có slot trống |
| 6 | Consumer lấy tiếp | Còn \`LOW\` | \`URGENT\` được lấy trước |

**Kết luận quan trọng:** \`priority=9\` không phải “quyền chen vào queue đang đầy”. Capacity áp dụng tại **thời điểm gửi**, trước khi message được đưa vào tập các message đang chờ; comparator quyết định thứ tự trong tập đã được chấp nhận.

### Những điều capacity không bảo đảm

Capacity hữu hạn **không tự**:

- Phát hiện message khẩn và đẩy message bình thường khỏi hàng đợi.
- Giữ riêng một phần chỗ trống cho priority cao.
- Ngăn starvation của priority thấp.
- Giới hạn số tác vụ **đang được handler xử lý**, vì message đã được lấy khỏi queue không còn chiếm slot.
- Lưu message bền vững qua sự cố tiến trình nếu queue chỉ nằm trong bộ nhớ.
- Bảo đảm exactly-once, xử lý thành công hoặc có reply từ Gateway.

Những bảo đảm này cần các cơ chế khác ngoài \`PriorityChannel\`.

## 3. Cấu hình capacity của PriorityChannel

Spring Integration hỗ trợ các constructor phổ biến:

| Java API | Ý nghĩa |
| --- | --- |
| \`new PriorityChannel()\` | Queue không giới hạn capacity do ứng dụng chỉ định |
| \`new PriorityChannel(100)\` | Queue có sức chứa tối đa 100 message |
| \`new PriorityChannel(comparator)\` | Queue không giới hạn với comparator tùy biến |
| \`new PriorityChannel(100, comparator)\` | Queue giới hạn 100 message và sắp xếp theo comparator |

Trong API Spring Integration 6.x, với constructor \`(int capacity, Comparator<Message<?>>)\`, **capacity không dương** dẫn tới queue **không giới hạn**. Vì vậy đừng đặt \`capacity=0\` với suy nghĩ nó sẽ chặn mọi message. Đối với một queue cần giới hạn rõ ràng, hãy dùng số nguyên **dương**.

### Cấu hình Java

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PriorityChannel;

@Configuration
class ChannelConfiguration {

    @Bean("orders.priority")
    PriorityChannel priorityOrders() {
        // Tối đa 100 message đang chờ; ordering mặc định theo priority.
        return new PriorityChannel(100);
    }
}
~~~

### Cấu hình XML

~~~xml
<int:channel id="ordersPriority">
    <int:priority-queue capacity="100"/>
</int:channel>
~~~

Với comparator tùy biến, capacity vẫn có thể được đặt riêng:

~~~java
import java.util.Comparator;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;

Comparator<Message<?>> ordering = Comparator
        .<Message<?>>comparingInt(message ->
                (Integer) message.getHeaders().get("businessUrgency"))
        .reversed();

PriorityChannel channel = new PriorityChannel(100, ordering);
~~~

Comparator quyết định **message nào được lấy trước**, không sửa quy tắc queue có bao nhiêu slot. Nếu comparator chỉ đọc header \`businessUrgency\`, phải bảo đảm header này hiện diện và đúng kiểu trước khi gửi vào queue.

### Queue không giới hạn có thật sự an toàn?

Không đặt capacity không có nghĩa bộ nhớ vô hạn. Queue trong bộ nhớ có thể tăng đến khi hết tài nguyên hoặc tạo áp lực garbage collection, khiến toàn bộ ứng dụng suy giảm. Với payload lớn hoặc tốc độ đến cao, nên chọn capacity có chủ đích và chính sách quá tải rõ ràng.

Giới hạn **số message** cũng không tương đương giới hạn **số byte**: một queue chứa 100 payload vài byte khác rất nhiều với 100 payload hàng megabyte.

## 4. Hành vi của send và receive khi queue đầy

\`PriorityChannel\` triển khai giao diện gửi/nhận message. Hành vi phụ thuộc vào **thời gian chờ** được truyền vào:

| Lời gọi | Khi queue có chỗ | Khi queue đầy |
| --- | --- | --- |
| \`send(message, 0)\` | Trả \`true\` sau khi enqueue | Trả \`false\` ngay, không chờ slot |
| \`send(message, 500)\` | Trả \`true\` khi chấp nhận trong thời hạn | Đợi tối đa khoảng 500 ms; hết hạn thì trả \`false\` |
| \`send(message)\` | Enqueue bình thường | Theo semantics timeout mặc định của channel, có thể chờ vô hạn để có slot |
| \`receive(0)\` | Trả message đứng đầu theo ưu tiên | Trả \`null\` nếu queue rỗng |
| \`receive(500)\` | Trả message nếu có trong thời hạn | Trả \`null\` nếu hết hạn chưa có message |

Đơn vị timeout trong các ví dụ là **mili giây**. Lời gọi không có timeout cần được xem xét kỹ ở các endpoint yêu cầu thời gian đáp ứng hữu hạn: một producer có thể bị giữ lại lâu chỉ vì consumer không lấy message.

Ví dụ:

~~~java
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

PriorityChannel queue = new PriorityChannel(2);

Message<String> first = MessageBuilder.withPayload("A").build();
Message<String> second = MessageBuilder.withPayload("B").build();
Message<String> third = MessageBuilder.withPayload("C").build();

queue.send(first, 0);          // true
queue.send(second, 0);         // true
boolean accepted = queue.send(third, 0);
// accepted == false: không có slot thứ ba.
~~~

**Luôn kiểm tra giá trị trả về** nếu gửi qua \`send\` có timeout. Trả \`false\` có nghĩa channel **không chấp nhận lần gửi này**; nó không đồng nghĩa message đã được lưu để hệ thống tự retry về sau.

Một số endpoint, Gateway, channel adapter và \`MessagingTemplate\` có thể diễn giải lỗi gửi khác nhau, hoặc ném exception khi việc gửi thất bại. Hãy kiểm tra hành vi thực tế của **đường gọi** đang sử dụng; đừng giả định mọi trường hợp đều trả Boolean cho tầng nghiệp vụ.

## 5. Bài test cơ bản: capacity độc lập với priority

Ví dụ dưới đây sử dụng **Java 17, Spring Integration 6.x, JUnit 5 và AssertJ**. Các test chỉ tương tác với queue trong bộ nhớ, không tạo Spring context, broker hoặc poller; vì thế kết quả có tính xác định.

Tạo file \`src/test/java/example/PriorityCapacityTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Comparator;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PriorityCapacityTest {

    private static Message<String> work(String name, int priority) {
        return MessageBuilder.withPayload(name)
                .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("requestId", "req-" + name)
                .build();
    }

    private static Message<?> next(PriorityChannel queue) {
        Message<?> result = queue.receive(1_000);
        assertThat(result).isNotNull();
        return result;
    }

    @Test
    void high_priority_cannot_displace_messages_when_queue_is_full() {
        PriorityChannel queue = new PriorityChannel(2);

        assertThat(queue.send(work("low", 1), 0)).isTrue();
        assertThat(queue.send(work("medium", 5), 0)).isTrue();
        assertThat(queue.getRemainingCapacity()).isZero();

        // URGENT được ưu tiên hơn cả hai, nhưng queue đã đầy.
        assertThat(queue.send(work("urgent", 9), 0)).isFalse();

        assertThat(next(queue).getPayload()).isEqualTo("medium");
        assertThat(next(queue).getPayload()).isEqualTo("low");
        assertThat(queue.receive(0)).isNull();
    }

    @Test
    void released_slot_allows_high_priority_to_enter_and_be_polled_first() {
        PriorityChannel queue = new PriorityChannel(2);

        queue.send(work("low", 1), 0);
        queue.send(work("medium", 5), 0);

        // Lấy MEDIUM để tạo một slot trống, LOW vẫn đang chờ.
        assertThat(next(queue).getPayload()).isEqualTo("medium");
        assertThat(queue.getRemainingCapacity()).isEqualTo(1);

        assertThat(queue.send(work("urgent", 9), 0)).isTrue();
        assertThat(queue.getRemainingCapacity()).isZero();

        assertThat(next(queue).getPayload()).isEqualTo("urgent");
        assertThat(next(queue).getPayload()).isEqualTo("low");
        assertThat(queue.receive(0)).isNull();
    }

    @Test
    void capacity_is_still_enforced_with_a_custom_comparator() {
        Comparator<Message<?>> byPriority = Comparator
                .<Message<?>>comparingInt(m ->
                        (Integer) m.getHeaders().get(
                                IntegrationMessageHeaderAccessor.PRIORITY))
                .reversed();
        PriorityChannel queue = new PriorityChannel(1, byPriority);

        assertThat(queue.send(work("normal", 1), 0)).isTrue();
        assertThat(queue.send(work("urgent", 9), 0)).isFalse();
        assertThat(next(queue).getPayload()).isEqualTo("normal");
    }

    @Test
    void timed_send_succeeds_after_consumer_frees_one_slot()
            throws Exception {
        PriorityChannel queue = new PriorityChannel(1);
        assertThat(queue.send(work("already-queued", 1), 0)).isTrue();

        ExecutorService sender = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        try {
            Future<Boolean> pending = sender.submit(() -> {
                started.countDown();
                return queue.send(work("waiting", 9), 3_000);
            });
            assertThat(started.await(1, TimeUnit.SECONDS)).isTrue();

            // Message đầu tiên đã chiếm slot; lấy ra để cấp chỗ trống.
            assertThat(next(queue).getPayload())
                    .isEqualTo("already-queued");
            assertThat(pending.get(2, TimeUnit.SECONDS)).isTrue();
            assertThat(next(queue).getPayload()).isEqualTo("waiting");
            assertThat(queue.receive(0)).isNull();
        } finally {
            sender.shutdownNow();
        }
    }

    @Test
    void priority_order_applies_only_to_accepted_backlog() {
        PriorityChannel queue = new PriorityChannel(3);

        queue.send(work("low", 1), 0);
        queue.send(work("high", 9), 0);
        queue.send(work("medium", 5), 0);

        Message<?> first = next(queue);
        assertThat(first.getPayload()).isEqualTo("high");
        assertThat(first.getHeaders().get("requestId"))
                .isEqualTo("req-high");
        assertThat(next(queue).getPayload()).isEqualTo("medium");
        assertThat(next(queue).getPayload()).isEqualTo("low");
        assertThat(queue.receive(0)).isNull();
    }
}
~~~

### Đọc kết quả từng phép thử

1. **Queue đầy:** Test gửi hai message priority thấp/trung bình vào queue capacity 2, sau đó chứng minh \`URGENT\` không được nhận vào mặc dù priority cao nhất.
2. **Giải phóng slot:** Sau khi lấy message \`MEDIUM\`, queue còn một slot; gửi \`URGENT\` thành công, rồi poll \`URGENT\` trước \`LOW\`.
3. **Comparator tùy biến:** Comparator chỉ ảnh hưởng thứ tự; capacity 1 vẫn từ chối lần gửi thứ hai khi chưa có slot.
4. **Gửi có thời hạn:** Một thread producer đang gửi vào queue capacity 1 có thể hoàn tất khi consumer lấy message hiện hữu và giải phóng slot.
5. **Đúng thứ tự backlog:** Khi cả ba message đã được chấp nhận trước lần poll đầu, kết quả lấy là \`HIGH\`, \`MEDIUM\`, \`LOW\`.

Test gửi có thời hạn dùng **timeout hữu hạn** và dừng executor trong \`finally\`, tránh tạo một thread chờ vô hạn sau khi test kết thúc. Đây là test cho việc giải phóng chỗ trống, không phải kiểm thử hiệu năng dưới tải thực tế.

## 6. Phân biệt send timeout với thời gian xử lý nghiệp vụ

Một producer có thể phải trải qua nhiều khoảng thời gian:

~~~mermaid
flowchart LR
    P["Producer gửi"] --> A["Đợi slot nếu queue đầy"]
    A --> Q["Message được enqueue"]
    Q --> B["Đợi poll theo priority"]
    B --> H["Handler xử lý"]
    H --> O["Output / Reply"]
~~~

Ba loại thời gian cần phân biệt:

- **Admission wait:** Thời gian producer chờ queue có slot để chấp nhận message.
- **Queue wait:** Thời gian message đã được enqueue nhưng chưa được lấy.
- **Processing time:** Thời gian handler thực thi sau khi nhận message.

\`send(message, 500)\` chỉ đặt giới hạn cho **thao tác gửi vào channel**, không phải một SLA “xử lý xong trong 500 ms”. Một message được gửi thành công vẫn có thể chờ lâu trong queue vì nhiều message priority cao hơn đang đến.

Ngược lại, nếu producer đang đợi slot, không có nghĩa message đã có mặt trong queue hay đã được đặt vào thứ tự ưu tiên. **Không được ACK nghiệp vụ như thể công việc đã được chấp nhận** trước khi có kết quả gửi hoặc lưu trữ đáng tin cậy.

## 7. Khi queue đầy: chọn chính sách backpressure

Một hệ thống tốt cần trả lời trước: **Ai chịu trách nhiệm khi queue không còn capacity?** Có nhiều lựa chọn, mỗi lựa chọn phù hợp với tình huống khác nhau.

| Chính sách | Hành vi | Khi phù hợp | Rủi ro |
| --- | --- | --- | --- |
| **Chờ có giới hạn** | \`send(message, timeout)\` | Producer chịu được trễ ngắn | Tăng latency, có thể hết hạn |
| **Từ chối nhanh** | \`send(message, 0)\` rồi trả lỗi/quá tải | API cần phản hồi sớm | Caller phải xử lý retry |
| **Retry + backoff** | Chờ rồi gửi lại có giới hạn | Công việc tạm thời không vào được queue | Retry storm nếu không jitter/rate limit |
| **Admission control** | Hạn chế tốc độ producer trước queue | Lưu lượng đột biến, kiểm soát đầu vào | Cần thiết kế quota |
| **Queue riêng theo lớp ưu tiên** | Tách urgent/normal và đặt capacity riêng | Cần bảo đảm chỗ cho urgent | Phức tạp hơn, mỗi queue vẫn có thể đầy |
| **Lưu bền vững** | Dùng broker/store phù hợp khi cần giữ công việc | Không muốn mất request khi ứng dụng restart | Cần xét cơ chế xác nhận, dedup và giới hạn của store |
| **Loại bớt công việc** | Chủ động bỏ message ít quan trọng theo policy | Telemetry có thể sampling/drop | Không phù hợp dữ liệu nghiệp vụ bắt buộc |

Không có chính sách “đúng nhất” độc lập với yêu cầu nghiệp vụ. Hệ thống thanh toán thường không được lặng lẽ bỏ giao dịch; một luồng metric tần suất cao có thể chấp nhận sampling khi quá tải.

### Ví dụ xử lý gửi bị từ chối

~~~java
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;

static boolean tryEnqueue(
        PriorityChannel queue, Message<?> message) {
    boolean accepted = queue.send(message, 100);
    if (!accepted) {
        // Trả tín hiệu quá tải hoặc chuyển sang cơ chế recovery
        // được quản lý; không ghi nhận như đã xử lý thành công.
        return false;
    }
    return true;
}
~~~

Trong ứng dụng HTTP, bạn có thể chuyển trạng thái quá tải thành phản hồi phù hợp (ví dụ HTTP 429 hoặc 503, tùy hợp đồng), kèm chỉ dẫn retry nếu an toàn. Trong một luồng nhắn tin bất đồng bộ, có thể cần **negative acknowledgment**, retry có giới hạn hoặc dead-letter theo adapter. **Đừng coi một lệnh chuyển sang dead-letter là thành công nếu chính dead-letter channel cũng có thể đầy.**

### Tách luồng ưu tiên cao khi capacity bị cạnh tranh

Với một queue có capacity 100, 100 message \`NORMAL\` đến trước có thể chiếm hết slot, khiến \`URGENT\` mới không được chấp nhận. Nếu đây là rủi ro không thể chấp nhận, có thể dùng Router phân chia:

~~~mermaid
flowchart LR
    IN["Input"] --> R{"Router theo class"}
    R -->|"URGENT"| HQ["Urgent Queue\ncapacity 20"]
    R -->|"NORMAL"| NQ["Normal Queue\ncapacity 80"]
    HQ --> HC["Urgent Worker / Scheduler"]
    NQ --> NC["Normal Worker / Scheduler"]
    HC --> OUT["Kết quả"]
    NC --> OUT
~~~

Các con số 20 và 80 chỉ là **ví dụ về quota tài nguyên**, không phải quy định của Spring Integration. Tách queue tạo ra chỗ dành riêng, nhưng cũng yêu cầu:

- Có đủ consumer hoặc chính sách scheduling để luồng urgent thực sự được lấy.
- Có chính sách rõ khi **urgent queue cũng đầy**.
- Không mặc định có thứ tự toàn cục giữa hai queue.
- Theo dõi starvation của normal khi urgent thường xuyên có backlog.

## 8. Kích thước queue nên chọn bao nhiêu?

Không có một capacity cố định phù hợp với mọi dịch vụ. Hãy bắt đầu bằng tốc độ đến, khả năng xử lý, thời gian burst và bộ nhớ khả dụng.

Giả sử:

- Producer có thể gửi **70 message/giây** trong một đợt tăng tải.
- Consumer xử lý được **50 message/giây** trong đợt đó.
- Đợt tăng tải kéo dài **12 giây**.
- Ban đầu queue rỗng, các message có kích thước gần như nhau.

Trong mô hình gần đúng:

\[
\Delta Q \approx \max(0, \lambda_{\mathrm{in}}-\mu_{\mathrm{out}})\times T
\]

Thay số:

\[
\Delta Q \approx (70-50)\times12 = 240\ \text{message}
\]

Queue có capacity **nhỏ hơn 240** có nguy cơ đầy trong khoảng burst giả định, nếu không giảm tốc độ producer hoặc tăng năng lực xử lý. Một capacity lớn hơn (ví dụ 300) tạo khoảng dự phòng trong **mô hình minh họa**, nhưng vẫn cần kiểm tra payload size, peak concurrency, retry và thời gian phục hồi backlog.

### Dung lượng bộ nhớ là giới hạn khác

Giả sử mỗi message chiếm trung bình \`S\` byte gồm payload, headers và overhead đối tượng. Mức bộ nhớ tương ứng có thể ước lượng:

\[
M_{\mathrm{queue}} \approx N_{\mathrm{queued}}\times S
\]

Ước lượng này thường **thiếu** overhead thực tế của Java object, metadata, references, buffering ngoài queue và biến thiên payload. Hãy đo bằng profile/heap tại tải thực. Capacity 300 message rất nhỏ nếu mỗi payload vài KB, nhưng có thể rất lớn nếu mỗi payload giữ một object graph hàng MB.

### Trade-off của capacity

| Capacity | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Quá nhỏ | Backpressure xuất hiện sớm, giới hạn bộ nhớ | Dễ từ chối burst ngắn có thể hấp thụ |
| Vừa đủ | Giữ burst hữu hạn, bảo vệ consumer | Cần điều chỉnh theo tải thực |
| Quá lớn | Producer ít bị từ chối trong ngắn hạn | Che lấp quá tải, queue wait dài, dùng nhiều RAM |
| Không giới hạn | Không có ngưỡng admission hữu hạn do cấu hình | Rủi ro OOM/GC và độ trễ queue tăng không kiểm soát |

**Capacity là cơ chế điều tiết áp lực, không phải cách chữa thiếu năng lực xử lý kéo dài.** Nếu input rate luôn vượt service rate, mọi queue hữu hạn cuối cùng cũng sẽ đầy.

## 9. PriorityChannel trong IntegrationFlow có poller

PriorityChannel là một \`PollableChannel\`, do đó consumer trong Java DSL thường được gắn với poller:

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
class PriorityCapacityFlowConfig {

    @Bean("work.priority")
    PriorityChannel priorityQueue() {
        return new PriorityChannel(100);
    }

    @Bean("work.done")
    QueueChannel doneQueue() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow workerFlow() {
        return IntegrationFlow.from("work.priority", source ->
                    source.poller(Pollers.fixedDelay(250)
                            .maxMessagesPerPoll(1)))
                .handle(String.class,
                        (payload, headers) -> "processed:" + payload)
                .channel("work.done")
                .get();
    }
}
~~~

Ví dụ trên dùng poller cố định để minh họa consumer, không phải cấu hình được khuyến nghị mặc định cho mọi hệ thống. Với poller chỉ lấy một message mỗi chu kỳ, backlog có thể tăng nhanh nếu arrival rate cao. Cần cân chỉnh \`fixedDelay\`, \`maxMessagesPerPoll\`, concurrency và thời gian handler theo thực tế.

**Bẫy khi test thứ tự:** Khi poller chạy đồng thời với producer, message \`LOW\` có thể được lấy trước khi \`URGENT\` được gửi vào. Đây không phải lỗi comparator. Muốn kiểm tra chính xác priority ordering, hãy **enqueue toàn bộ backlog trước khi có consumer** hoặc kiểm soát poller, như unit test ở mục 5.

## 10. Capacity, thread và giao dịch

### Một queue có capacity không giới hạn số handler đồng thời

Consumer lấy message khỏi queue thì slot tương ứng được giải phóng. Sau đó message có thể vẫn đang được xử lý:

~~~text
Queue capacity: 100
Message đang nằm trong queue: 80
Message đã được lấy, handler đang xử lý: 20

=> Không được kết luận hệ thống chỉ có tối đa 100 công việc tồn tại.
~~~

Nếu muốn giới hạn **in-flight processing**, cần thêm giới hạn worker/concurrency hoặc semaphore phù hợp. Capacity và max worker là hai loại giới hạn bổ sung cho nhau.

### Producer bị block có thể gây nghẽn dây chuyền

Nếu producer đang giữ một tài nguyên quan trọng trong lúc \`send(message)\` chờ slot (ví dụ lock, transaction hoặc thread HTTP), việc chờ quá lâu có thể làm lan truyền tắc nghẽn đến các thành phần khác.

Khi đặt PriorityChannel giữa các endpoint đồng bộ, đặc biệt sau Gateway, hãy kiểm tra:

1. Đường gửi có timeout rõ ràng không?
2. Producer có chặn thread phục vụ request khi queue đầy không?
3. Nếu timeout, caller có nhận biết và retry một cách an toàn không?
4. Nếu message đã được chấp nhận nhưng handler thất bại, exception đi qua đường nào?
5. Transaction có bị giữ quá lâu trong lúc chờ chỗ trống không?

Không tự coi \`send()\` thành công là đồng nghĩa **giao dịch nghiệp vụ đã hoàn tất**. Nó chỉ phản ánh channel đã chấp nhận message theo semantics tương ứng.

## 11. Capacity với retry, error channel và correlation

### Retry có thể làm quá tải nặng hơn

Khi queue đầy, nhiều producer đồng thời retry ngay lập tức có thể tạo **retry storm**. Chọn retry với số lần giới hạn, exponential backoff và jitter phù hợp thay vì vòng lặp vô hạn:

~~~text
Queue đầy
   |
   +-- Thông báo overload
   |
   +-- Retry có giới hạn + backoff
   |
   +-- Nếu hết lượt: recovery / dead-letter / trả lỗi
~~~

Phân biệt retry **gửi vào queue** với retry **xử lý message sau khi đã được consumer lấy**. Hai cơ chế nằm ở hai ranh giới khác nhau và có thể gây trùng hoặc tăng backlog theo cách khác nhau.

### Error channel không tự cấp thêm capacity

Một error channel giúp quan sát hoặc xử lý thất bại, nhưng không làm queue chính rộng thêm. Nếu recovery flow chuyển message tới một queue khác, queue đó cũng cần giới hạn, độ bền và chính sách quá tải tương ứng.

Đối với hệ thống không được mất message, cần xác định **điểm xác nhận đã lưu bền vững**, quy tắc retry và idempotency. Queue trong bộ nhớ không bảo đảm giữ message qua việc tiến trình bị dừng đột ngột.

### Splitter, Aggregator và correlation

Một message lớn có thể được Splitter tách thành nhiều fragment. Nếu queue đặt **sau Splitter**, một request đầu vào có thể tiêu thụ nhiều slot. Ví dụ một request tạo 50 fragment có thể gần như chiếm hết queue capacity 60, dù producer ban đầu chỉ gửi một request.

Khi queue đầy giữa chừng:

- Một số fragment có thể đã được enqueue, một số fragment gửi sau thất bại.
- Aggregator nhận các fragment thiếu có thể không release nhóm dựa trên \`sequenceSize\`.
- \`correlationId\`, \`requestId\` và sequence headers cần được giữ để phát hiện nhóm thiếu.
- Retry fragment không có idempotency có thể dẫn đến trùng message.

Vì vậy capacity phải được thiết kế theo **số message tại vị trí đặt queue**, không chỉ theo số request ở đầu hệ thống.

### Router và ưu tiên

Router có thể chọn luồng urgent/normal trước khi enqueue. Trong một PriorityChannel dùng chung, message normal có thể chiếm slot trước khi urgent đến. Nếu cần giữ capacity riêng cho urgent, có thể dùng hai queue như mục 7; chỉ tăng priority header không giải quyết trường hợp admission đã đầy.

## 12. Theo dõi queue capacity trong vận hành

Không nên chỉ cảnh báo khi queue đã đầy. Theo dõi cả tốc độ tăng backlog, thời gian chờ và tỉ lệ gửi thất bại.

| Metric gợi ý | Ý nghĩa | Câu hỏi |
| --- | --- | --- |
| \`queue_depth\` | Số message đang chờ | Backlog đang lớn đến đâu? |
| \`remaining_capacity\` | Số slot còn trống nếu có giới hạn | Sắp hết chỗ chưa? |
| \`queue_utilization\` | \`queue_depth / capacity\` | Queue thường ở gần ngưỡng hay chỉ burst ngắn? |
| \`send_failure_count\` | Lượt gửi không được chấp nhận | Có bao nhiêu yêu cầu bị backpressure? |
| \`send_wait_duration\` | Thời gian chờ slot | Producer có đang bị block? |
| \`queue_wait_duration\` | Thời gian từ enqueue đến receive | Message bị chờ do backlog/priority? |
| \`oldest_message_age\` | Tuổi message cũ nhất | Nhóm thấp có bị starvation? |
| \`consumer_rate\` | Tốc độ xử lý/lấy message | Có theo kịp tốc độ đến không? |
| \`retry_count\`, \`error_count\` | Lỗi và lần thử lại | Retry có góp phần tạo quá tải không? |

\`PriorityChannel\` cung cấp API như \`getRemainingCapacity()\` để quan sát phần sức chứa còn lại. Metric cụ thể và cách tích hợp Micrometer/management phụ thuộc phiên bản Spring Integration, nên cần kiểm tra cấu hình thực tế trước khi đặt tên metric trong dashboard.

### Đừng che khuất starvation bằng chỉ số tổng

Một queue có depth 10 vẫn có thể chứa message priority thấp đã chờ rất lâu nếu priority cao liên tục được thêm và lấy. Nên gắn nhãn/class cho metric thời gian chờ theo priority hoặc nhóm nghiệp vụ; tránh đặt metric có cardinality quá lớn theo từng \`requestId\`.

## 13. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng \`PriorityChannel()\` nhưng tưởng có giới hạn | Queue tăng không kiểm soát | Đặt capacity dương |
| Đặt \`capacity=0\` rồi nghĩ “không nhận message” | Có thể tạo queue không giới hạn | Hiểu đúng semantics của constructor |
| Nghĩ priority cao luôn được enqueue | Message khẩn bị từ chối khi queue đầy | Tách admission khỏi ordering |
| Không kiểm tra \`send(message, 0)\` trả \`false\` | Mất công việc một cách im lặng | Xử lý overload/recovery rõ ràng |
| Dùng \`send(message)\` ở thread HTTP nhạy latency | Request có thể bị block lâu | Dùng timeout hữu hạn |
| Chỉ tăng capacity khi consumer quá chậm | Che lấp quá tải và tăng queue wait | Đo rate, tối ưu handler, thêm capacity xử lý |
| Test thứ tự khi poller đã chạy | Test flaky vì message đầu được lấy sớm | Enqueue backlog trước lần poll |
| Không đo payload size | Đánh giá thiếu RAM cần thiết | Profile heap theo tải |
| Xem queue bền vững và queue bộ nhớ như nhau | Sai kỳ vọng khi restart | Thiết kế message store/broker phù hợp |
| Không test retry khi queue đầy | Retry storm, trùng message | Backoff, giới hạn và idempotency |
| Không xét queue sau Splitter | Một request tạo quá nhiều fragment | Tính capacity theo message sau split |
| Nhầm capacity với giới hạn in-flight | Quá nhiều handler chạy đồng thời | Giới hạn concurrency riêng |

## 14. Bài thực hành

### Bài A — Message khẩn có được chen vào queue đầy?

Tạo \`PriorityChannel(2)\`. Gửi \`LOW\` và \`MEDIUM\`, sau đó gửi \`URGENT\` với \`timeout=0\`. Xác minh lần gửi thứ ba không được chấp nhận, hai message cũ vẫn được lấy theo priority. Giải thích vì sao đây là hành vi **capacity**, không phải lỗi comparator.

### Bài B — Giải phóng slot và thứ tự polling

Tiếp tục bài A: lấy \`MEDIUM\` ra, sau đó gửi lại \`URGENT\`. Xác minh \`URGENT\` vào được queue và được lấy trước \`LOW\`. Kiểm tra \`getRemainingCapacity()\` ở các mốc.

### Bài C — Producer chờ có giới hạn

Tạo queue capacity 1, enqueue một message. Từ thread khác gửi message thứ hai với timeout hữu hạn; thread consumer lấy message đầu để giải phóng chỗ. Dùng \`Future\`, \`CountDownLatch\` và timeout khi đợi để bảo đảm test không treo. Kiểm tra lần gửi thứ hai thành công và message còn nguyên payload/header.

### Bài D — Burst và sizing

Giả sử tốc độ đến trong burst là 70 message/giây, tốc độ xử lý là 50 message/giây, burst kéo dài 12 giây. Tính backlog phát sinh và đề xuất capacity với khoảng dự phòng. Sau đó tăng kích thước payload gấp nhiều lần; phân tích tại sao kết luận về RAM phải thay đổi dù số message không đổi.

### Bài E — Splitter trước queue

Cho một request tách thành 20 fragment; đặt PriorityChannel capacity 10 phía sau Splitter. Thiết kế đường xử lý khi một số fragment được chấp nhận trước khi queue đầy, và kiểm tra Aggregator không release một nhóm thiếu fragment ngoài dự kiến. Nêu recovery hoặc cơ chế admission theo nhóm cần thiết.

### Bài F — Tách capacity theo mức ưu tiên

Thay queue dùng chung capacity 100 bằng hai queue: urgent capacity 20, normal capacity 80. Dùng Router phân luồng và test trường hợp normal đầy nhưng urgent vẫn có slot. Kiểm tra riêng đường quá tải khi urgent cũng đầy. Thảo luận điều kiện để hai queue được phục vụ công bằng.

## 15. Checklist trước khi triển khai

1. Queue có capacity **dương, hữu hạn** nếu muốn giới hạn RAM và backlog chưa?
2. Đã phân biệt rõ **admission vào queue** với **polling theo priority** chưa?
3. Producer có timeout gửi hợp lý thay vì chờ vô hạn trong đường nhạy latency không?
4. Khi \`send\` thất bại, hệ thống có phản hồi/recovery rõ, không mất message âm thầm không?
5. Có test cho message priority cao bị từ chối vì queue đang đầy không?
6. Có test giải phóng slot và xác minh message mới được chấp nhận không?
7. Đã ước lượng burst rate, service rate, kích thước payload và budget RAM chưa?
8. Có kiểm soát retry, backoff và idempotency khi quá tải không?
9. Queue sau Splitter, Router hoặc các nhánh khác đã được sizing theo **message thực tế** chưa?
10. Capacity của channel chính, recovery channel và broker/store có được xem xét cùng nhau không?
11. Metrics có quan sát được queue depth, send failures, queue wait và starvation theo priority không?
12. Đã phân biệt queue capacity với max số handler đang xử lý đồng thời chưa?

**Kết luận:** \`PriorityChannel\` giúp quyết định **message nào trong backlog được lấy trước**, còn **queue capacity** quyết định **có thể nhận thêm message hay không**. Không nên mặc định message khẩn được quyền chen vào queue đã đầy. Khi có capacity hữu hạn, timeout gửi, chính sách backpressure, kiểm thử gửi/nhận và metrics phù hợp, bạn có thể triển khai Priority Channel trong Spring Integration vừa bảo vệ tài nguyên, vừa giữ được hành vi ưu tiên đúng như hợp đồng nghiệp vụ.

### Tài liệu tham khảo

- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): cấu hình \`PriorityChannel\` và \`capacity\`.
- [Spring Integration API — PriorityChannel (6.4.2)](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/channel/PriorityChannel.html): constructors, \`doSend\`, \`doReceive\` và \`getRemainingCapacity\`.
