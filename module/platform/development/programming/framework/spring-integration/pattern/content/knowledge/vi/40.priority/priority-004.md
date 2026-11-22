# Tie-breaker khi cùng priority trong Spring Integration

## 1. Bài toán: hai message quan trọng như nhau, lấy message nào trước?

Khi dùng **Priority Channel** trong Enterprise Integration Patterns, ta thường muốn message có mức khẩn cao hơn được xử lý trước. Nhưng chuyện gì xảy ra nếu **hai hoặc nhiều message có cùng priority**? Ví dụ, hai đơn hàng đều được đánh dấu \`priority=9\`, hoặc hàng trăm sự kiện đều thuộc nhóm \`NORMAL\`.

Nếu không quy định **tie-breaker** (tiêu chí phá hòa), thứ tự lấy message khi cùng priority không phải là một hợp đồng mà ứng dụng nên phụ thuộc vào. Một message đến trước có thể không được lấy trước nếu cấu trúc hàng đợi hoặc comparator không cam kết tính ổn định của thứ tự.

Bài này thuộc chương **Priority** của module **SPRING_INTEGRATION_PATTERN**. Module hướng tới triển khai Enterprise Integration Patterns bằng Spring Integration để xây dựng luồng message ít phụ thuộc, dễ mở rộng với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation. Tie-breaker bổ sung một quy tắc **xác định được và kiểm thử được** cho việc lấy message khỏi hàng đợi khi nhiều message cùng mức ưu tiên.

Sau bài này, bạn có thể:

1. Phân biệt thứ tự theo priority với FIFO và thứ tự hoàn thành nghiệp vụ.
2. Giải thích vì sao comparator chỉ so sánh priority chưa đủ khi bằng nhau.
3. Thiết kế \`Comparator<Message<?>>\` với khóa thứ hai, như một sequence tăng dần.
4. Chọn đúng điểm cấp sequence để phản ánh thứ tự cần cam kết.
5. Kiểm thử thứ tự ở nhiều mức priority và ở cùng một mức.
6. Phân tích trường hợp timestamp trùng, nhiều producer, xử lý song song và retry.

## 2. Khi comparator trả về 0 thì sao?

Trong Java, \`Comparator.compare(a, b)\` trả về:

| Kết quả | Ý nghĩa đối với hàng đợi ưu tiên |
| --- | --- |
| Số âm | \`a\` đứng trước \`b\` |
| Số 0 | Comparator xem \`a\` và \`b\` tương đương về **thứ tự** |
| Số dương | \`a\` đứng sau \`b\` |

Nếu chỉ dựa vào \`priority\`, hai message \`priority=9\` sẽ có kết quả so sánh bằng 0. Kết quả 0 **không có nghĩa** queue bắt buộc lấy theo thứ tự enqueue.

~~~text
Thứ tự gửi      Message      Priority
-----------     --------     --------
1               A            9
2               B            9
3               C            5

Điều được bảo đảm theo mức ưu tiên:
  A và B được ưu tiên trước C, nếu cả ba đã nằm trong queue.

Điều chưa được cam kết nếu không có tie-breaker:
  A nhất thiết phải được lấy trước B.
~~~

Trong Spring Integration, \`PriorityChannel\` là một \`PollableChannel\` có thể nhận comparator do ứng dụng cấu hình. Khi chỉ dùng so sánh theo header \`priority\`, đừng xây logic nghiệp vụ phụ thuộc vào FIFO giữa các message cùng mức, trừ khi đã kiểm chứng một cơ chế ổn định khác và biến nó thành hợp đồng rõ ràng.

### Vì sao lỗi này khó phát hiện?

Một test gửi A rồi B và tình cờ nhận A rồi B có thể **vẫn pass** dù không có cam kết thứ tự. Khi nâng phiên bản, đổi cách triển khai, tăng tải, chạy nhiều thread hoặc đưa thêm message mức ưu tiên khác vào queue, thứ tự quan sát được có thể thay đổi. Test nên buộc thuật toán bộc lộ rõ quy tắc phá hòa thay vì chỉ khẳng định hành vi ngẫu nhiên của một lần chạy.

## 3. Phân biệt ba loại thứ tự

~~~mermaid
flowchart LR
    P["Producer"] -->|"Thời điểm send()"| Q["PriorityChannel"]
    Q -->|"Thứ tự poll / receive"| H["Consumer / Handler"]
    H -->|"Thứ tự hoàn tất"| O["Output"]
~~~

| Loại thứ tự | Điểm quan sát | PriorityChannel có tự bảo đảm không? |
| --- | --- | --- |
| **Thứ tự gửi** | Producer gọi \`send()\` | Do producer hoặc cơ chế phối hợp nhiều producer quyết định |
| **Thứ tự lấy** | Consumer gọi \`receive()\` | Theo comparator giữa các message đang đợi |
| **Thứ tự hoàn tất** | Handler phát kết quả | Không được bảo đảm bởi comparator của queue |

Một tie-breaker theo FIFO thường có nghĩa: **trong những message cùng priority đã vào queue, message được ghi nhận vào queue trước phải được lấy trước**. Đây là hợp đồng về *thứ tự lấy*, không phải cam kết mọi tác vụ hoàn thành theo cùng thứ tự.

Nếu handler xử lý song song, message A có thể được lấy trước B nhưng hoàn tất sau B. Với các luồng cần thứ tự hoàn tất, bạn còn phải kiểm soát concurrency hoặc sử dụng cơ chế resequencing, correlation và xử lý kết quả phù hợp.

## 4. Các cách chọn tie-breaker

Không có một khóa thứ hai tốt nhất cho mọi trường hợp. Điều cần thiết là tiêu chí phải **phù hợp nghĩa nghiệp vụ** và tồn tại ổn định trong thời gian message nằm trong queue.

| Khóa tie-break | Quy tắc | Khi phù hợp | Lưu ý |
| --- | --- | --- | --- |
| **Sequence tăng dần tại điểm enqueue** | Sequence nhỏ được lấy trước | Muốn FIFO trong cùng priority tại một queue | Phải cấp sequence ở đúng ranh giới, không trùng |
| **Timestamp tại điểm enqueue** | Thời điểm sớm hơn được lấy trước | Quan tâm tuổi message | Đồng hồ và độ phân giải có thể khiến trùng; cần khóa thứ ba |
| **Deadline** | Hạn xử lý gần hơn được lấy trước | SLA có deadline cụ thể | Không đồng nghĩa FIFO |
| **Business sequence** | Số thứ tự sự kiện nhỏ được lấy trước | Cần thứ tự nghiệp vụ theo aggregate/tenant | Phải rõ phạm vi sequence và trường hợp thiếu |
| **Request ID / UUID** | So sánh chuỗi để có thứ tự xác định | Chỉ muốn kết quả nhất quán khi các khóa khác bằng nhau | Không phản ánh thứ tự đến |
| **Tenant weight hoặc aging** | Tiêu chí công bằng bổ sung | Cần hạn chế starvation giữa các nhóm | Có thể cần scheduler riêng, không chỉ comparator |

**Không lấy UUID của message làm bằng chứng FIFO.** Header \`id\` nhận dạng message, nhưng thứ tự so sánh UUID không tương ứng thời điểm vào queue.

**Không coi timestamp mặc định là enqueue time.** Timestamp của message thường gắn với lúc message được tạo; message có thể đi qua Gateway, Router, Filter hoặc chờ ở một channel khác trước khi đến PriorityChannel.

## 5. Thiết kế comparator hai khóa: priority giảm dần, sequence tăng dần

Một chính sách minh bạch:

1. \`priority\` càng lớn càng được lấy trước.
2. Khi cùng \`priority\`, \`enqueueSequence\` càng nhỏ càng được lấy trước.

Ví dụ:

| Payload | Priority | Enqueue sequence | Thứ tự lấy |
| --- | --- | --- | --- |
| \`A\` | 9 | 20 | 1 |
| \`B\` | 5 | 1 | 4 |
| \`C\` | 9 | 21 | 2 |
| \`D\` | 9 | 22 | 3 |

\`B\` đến rất sớm nhưng thuộc mức 5, nên vẫn đứng sau tất cả message mức 9 **đang nằm trong queue**. Trong nhóm mức 9, sequence 20, 21, 22 quyết định thứ tự.

~~~mermaid
flowchart TD
    IN["Nhiều message đang chờ"] --> P{"So sánh priority"}
    P -->|"Khác"| PK["Priority lớn đứng trước"]
    P -->|"Bằng"| S{"So sánh enqueueSequence"}
    S -->|"Khác"| SK["Sequence nhỏ đứng trước"]
    S -->|"Trùng"| T["Thiếu tie-break đầy đủ: bổ sung khóa hoặc từ chối"]
~~~

### Comparator dùng Java

~~~java
import java.util.Comparator;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

static Comparator<Message<?>> priorityThenSequence() {
    return Comparator
            .<Message<?>>comparingInt(m ->
                    (Integer) m.getHeaders()
                            .get(IntegrationMessageHeaderAccessor.PRIORITY))
            .reversed()
            .thenComparingLong(m ->
                    (Long) m.getHeaders().get("enqueueSequence"));
}
~~~

Với comparator trên:

- Nếu \`a.priority=9\` và \`b.priority=5\`, thì \`a\` đứng trước.
- Nếu cả hai priority bằng 9 nhưng \`a.enqueueSequence=20\`, \`b.enqueueSequence=21\`, thì \`a\` đứng trước.
- Nếu cả hai khóa đều bằng nhau, comparator trả 0: thứ tự vẫn chưa được phân biệt.

Hãy bảo đảm **cả hai header có kiểu đúng** trước khi message vào queue. \`priority\` trong ví dụ là \`Integer\`, \`enqueueSequence\` là \`Long\`; một chuỗi \`"20"\` không thể ép kiểu trực tiếp thành \`Long\`.

## 6. Ví dụ JUnit 5 đầy đủ: kiểm thử thứ tự và tie-breaker

Đoạn sau dùng **Java 17**, **JUnit 5**, **AssertJ**, **Spring Messaging** và **Spring Integration 6.x**. Với Spring Boot, các dependency có thể gồm \`spring-boot-starter-integration\` và \`spring-boot-starter-test\` của phiên bản tương thích. Test không cần Spring context, message broker hay poller, vì mục tiêu là kiểm tra **thứ tự trong queue**.

Tạo \`src/test/java/example/PriorityTieBreakerTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Comparator;
import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PriorityTieBreakerTest {

    private static Message<String> work(
            String name, int priority, long sequence) {
        return MessageBuilder.withPayload(name)
                .setHeader(
                        IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("enqueueSequence", sequence)
                .setHeader("requestId", "request-" + name)
                .build();
    }

    private static Comparator<Message<?>> priorityThenSequence() {
        return Comparator
                .<Message<?>>comparingInt(message ->
                        (Integer) message.getHeaders().get(
                                IntegrationMessageHeaderAccessor.PRIORITY))
                .reversed()
                .thenComparingLong(message ->
                        (Long) message.getHeaders().get("enqueueSequence"));
    }

    private static Message<?> next(PriorityChannel channel) {
        Message<?> message = channel.receive(1_000);
        assertThat(message).isNotNull();
        return message;
    }

    @Test
    void higher_priority_still_wins_over_earlier_sequence() {
        PriorityChannel channel =
                new PriorityChannel(10, priorityThenSequence());

        // Gửi đủ message trước lần receive đầu tiên.
        channel.send(work("normal", 5, 1L));
        channel.send(work("urgent", 9, 2L));
        channel.send(work("background", 1, 3L));

        assertThat(next(channel).getPayload()).isEqualTo("urgent");
        assertThat(next(channel).getPayload()).isEqualTo("normal");
        assertThat(next(channel).getPayload()).isEqualTo("background");
        assertThat(channel.receive(0)).isNull();
    }

    @Test
    void equal_priority_is_sorted_by_sequence() {
        PriorityChannel channel =
                new PriorityChannel(10, priorityThenSequence());

        // Thứ tự send cố ý đảo so với sequence để test khóa thứ hai.
        channel.send(work("third", 9, 3L));
        channel.send(work("first", 9, 1L));
        channel.send(work("second", 9, 2L));

        assertThat(next(channel).getPayload()).isEqualTo("first");
        assertThat(next(channel).getPayload()).isEqualTo("second");
        assertThat(next(channel).getPayload()).isEqualTo("third");
        assertThat(channel.receive(0)).isNull();
    }

    @Test
    void message_payload_and_business_headers_are_preserved() {
        PriorityChannel channel =
                new PriorityChannel(10, priorityThenSequence());
        channel.send(work("A", 9, 11L));

        Message<?> actual = next(channel);
        assertThat(actual.getPayload()).isEqualTo("A");
        assertThat(actual.getHeaders().get("requestId"))
                .isEqualTo("request-A");
        assertThat(actual.getHeaders().get(
                IntegrationMessageHeaderAccessor.PRIORITY))
                .isEqualTo(9);
        assertThat(actual.getHeaders().get("enqueueSequence"))
                .isEqualTo(11L);
    }

    @Test
    void comparator_has_expected_signs_for_both_keys() {
        Comparator<Message<?>> comparator = priorityThenSequence();

        Message<?> highEarly = work("high-early", 9, 10L);
        Message<?> highLate = work("high-late", 9, 11L);
        Message<?> lowEarly = work("low-early", 1, 1L);

        assertThat(comparator.compare(highEarly, lowEarly))
                .isLessThan(0); // Priority lớn đứng trước.
        assertThat(comparator.compare(highEarly, highLate))
                .isLessThan(0); // Cùng priority, sequence nhỏ trước.
        assertThat(comparator.compare(highLate, highEarly))
                .isGreaterThan(0);
    }
}
~~~

### Hai ý quan trọng khi đọc test

**Test \`equal_priority_is_sorted_by_sequence\`** cố ý gửi \`third\` trước \`first\`. Vì thế, nó chứng minh comparator sắp theo khóa \`enqueueSequence\`, **không** chứng minh FIFO theo *thứ tự gửi thực tế* trong test đó. Để triển khai FIFO thật, phải cấp sequence tại đúng điểm xác lập thứ tự enqueue.

**Test \`higher_priority_still_wins_over_earlier_sequence\`** chứng minh sequence là **khóa phụ**. Dù \`normal\` có sequence nhỏ hơn, \`urgent\` vẫn đi trước vì priority được so sánh trước.

Đừng viết một test kỳ vọng thứ tự cụ thể cho các message **cùng priority và cùng sequence** trừ khi đã có khóa phân biệt thứ ba. Nếu cả hai khóa bằng nhau, comparator coi chúng tương đương.

## 7. Cấp enqueue sequence ở đâu để thật sự có FIFO?

Ví dụ trên truyền sequence thủ công cho test. Trong ứng dụng, cần biết **ai cấp số** và **ở thời điểm nào**.

Giả sử hai producer chạy song song:

~~~text
Producer A lấy sequence=100, nhưng tạm dừng trước send().
Producer B lấy sequence=101 rồi send() thành công.
Producer A mới send() thành công.

Thứ tự queue thực nhận:  B trước A.
Thứ tự theo sequence:   A trước B.
~~~

Comparator theo sequence trong tình huống này cho kết quả xác định, nhưng **không tương đương thứ tự enqueue thực**. Muốn diễn tả đúng “đến queue trước”, việc gán sequence và enqueue cần được **tuần tự hóa cùng nhau**, hoặc bạn phải chấp nhận một hợp đồng khác: “theo thứ tự phân bổ sequence”, không phải “theo thứ tự đến”.

### Phương án đơn giản: một điểm enqueue tuần tự

Trong một instance, một thành phần gateway/dispatcher có thể sở hữu queue và cấp số theo thứ tự. Dưới đây là **mô hình Java đơn giản** cho trường hợp một tiến trình; phương thức \`enqueue\` được đồng bộ để tránh hai producer lấy sequence và gửi sai thứ tự:

~~~java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class SequencedEnqueue {
    private final PriorityChannel channel;
    private final AtomicLong nextSequence = new AtomicLong();

    SequencedEnqueue(PriorityChannel channel) {
        this.channel = channel;
    }

    // Một instance, các producer đều phải đi qua phương thức này.
    synchronized boolean enqueue(String payload, int priority) {
        long sequence = nextSequence.incrementAndGet();
        Message<String> message = MessageBuilder.withPayload(payload)
                .setHeader(
                        IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("enqueueSequence", sequence)
                .build();
        return channel.send(message, 0);
    }
}
~~~

Với **cùng một \`SequencedEnqueue\`** và các message được chấp nhận thành công, sequence tăng theo thứ tự gọi \`send\` trong vùng \`synchronized\`. Tuy nhiên, khi queue đầy, \`send(..., 0)\` có thể trả \`false\`; số sequence bị bỏ qua là bình thường, miễn không có giả định rằng sequence phải liên tục. Nếu cần retry khi enqueue thất bại, phải quy định giữ sequence cũ hay cấp lại sequence khi gửi lại.

**Giới hạn của ví dụ:**

- \`AtomicLong\` chỉ bảo đảm tăng trong một tiến trình. Khi restart, bộ đếm có thể bắt đầu lại, gây trùng khóa nếu queue hoặc message store vẫn giữ message cũ.
- Mỗi instance có bộ đếm riêng; không tạo được thứ tự toàn cục giữa nhiều replica.
- Tất cả producer phải đi qua cùng điểm enqueue để chính sách có ý nghĩa.
- Nếu xử lý nhiều message ở nhiều queue, “thứ tự toàn cục” có thể vừa tốn kém vừa không cần thiết; thường nên xác định thứ tự theo từng queue, aggregate hoặc tenant.

Với broker và phân vùng, cần xác định thứ tự được cam kết theo **partition**, **key** hay toàn hệ thống. Không nên hứa FIFO toàn cục nếu hạ tầng chỉ bảo đảm thứ tự trong từng partition.

## 8. Timestamp làm tie-breaker: khi nào ổn, khi nào không?

Một lựa chọn dễ nghĩ tới là dùng \`createdAt\` hoặc \`enqueuedAt\` làm khóa thứ hai:

~~~java
Comparator<Message<?>> byPriorityThenTime = Comparator
        .<Message<?>>comparingInt(m ->
                (Integer) m.getHeaders()
                        .get(IntegrationMessageHeaderAccessor.PRIORITY))
        .reversed()
        .thenComparingLong(m ->
                (Long) m.getHeaders().get("enqueuedAtMillis"));
~~~

Cách này sắp xếp theo thời gian ghi nhận **nếu timestamps đáng tin**. Nhưng có nhiều bẫy:

1. Hai message có thể được ghi nhận cùng một mili giây, khiến comparator vẫn trả 0.
2. Đồng hồ trên nhiều máy có thể lệch, thậm chí được chỉnh lại.
3. \`createdAt\` trên producer chưa chắc phản ánh thời điểm message được enqueue vào PriorityChannel.
4. Timestamp có thể bị copy qua các bước xử lý hoặc retry, trong khi thứ tự enqueue đã thay đổi.

Nếu cần thứ tự hoàn toàn xác định, có thể kết hợp **priority → enqueue time → sequence duy nhất**:

~~~java
Comparator<Message<?>> ordered = Comparator
        .<Message<?>>comparingInt(m ->
                (Integer) m.getHeaders()
                        .get(IntegrationMessageHeaderAccessor.PRIORITY))
        .reversed()
        .thenComparingLong(m ->
                (Long) m.getHeaders().get("enqueuedAtMillis"))
        .thenComparingLong(m ->
                (Long) m.getHeaders().get("enqueueSequence"));
~~~

Việc thêm sequence chỉ giải quyết trường hợp timestamp trùng **nếu sequence thực sự duy nhất và có nghĩa trong phạm vi queue**. Không nên dùng UUID ngẫu nhiên làm khóa thứ ba rồi gọi đó là FIFO.

## 9. Header thiếu, sai kiểu và sequence bị trùng

Comparator nhận \`Message<?>\`, nhưng các giá trị được trích xuất từ \`MessageHeaders\` thường là \`Object\`. Cast trực tiếp tiện cho ví dụ đã chuẩn hóa dữ liệu; trong production, nên xác thực trước khi vào queue.

Một chính sách mẫu:

| Tình huống | Hành vi được khuyến nghị trong ví dụ |
| --- | --- |
| Không có \`priority\` | Gắn mức mặc định ở bước nhận hoặc từ chối theo contract |
| \`priority="9"\` là String | Chuyển đổi có kiểm soát hoặc từ chối; không để comparator cast sai |
| Không có \`enqueueSequence\` | Gán tại dispatcher trước enqueue |
| \`enqueueSequence\` là String | Chuẩn hóa thành Long hoặc từ chối |
| Hai message có cùng sequence | Phát hiện lỗi cấp sequence hoặc có khóa phụ bổ sung |
| Sequence bị âm hoặc quá phạm vi | Xác thực theo contract, không tự suy ra nghiệp vụ |

Một hàm kiểm tra header:

~~~java
static void validateOrderingHeaders(Message<?> message) {
    Object priority = message.getHeaders()
            .get(IntegrationMessageHeaderAccessor.PRIORITY);
    Object sequence = message.getHeaders().get("enqueueSequence");

    if (!(priority instanceof Integer)) {
        throw new IllegalArgumentException(
                "priority must be an Integer");
    }
    if (!(sequence instanceof Long)) {
        throw new IllegalArgumentException(
                "enqueueSequence must be a Long");
    }
}
~~~

Đây là kiểm tra **kiểu**. Nếu priority phải nằm trong 1–9, hoặc sequence phải dương, hãy thêm các giới hạn vào chính sách của ứng dụng. Không tự coi những giới hạn đó là quy tắc bắt buộc của Spring Integration.

Lưu ý rằng comparator Java không được kỳ vọng xử lý an toàn việc headers thay đổi sau khi message đã được đưa vào queue. \`MessageHeaders\` không cho sửa trực tiếp, nhưng payload có thể chứa object mutable; đừng dùng khóa lấy từ payload mutable để so sánh nếu giá trị có thể thay đổi khi đang xếp hàng.

## 10. Tie-breaker không phải giải pháp chống starvation

Thêm sequence giúp **các message cùng priority** được chọn theo một thứ tự nhất quán. Nó **không** bảo đảm message priority thấp sẽ được lấy trước dòng message priority cao đến liên tục.

~~~text
Queue đã có:
  LOW-A:  priority=1, sequence=1

Mỗi lần consumer chuẩn bị poll:
  HIGH-1: priority=9, sequence=2
  HIGH-2: priority=9, sequence=3
  HIGH-3: priority=9, sequence=4
  ...

Priority vẫn là khóa chính.
LOW-A có sequence rất nhỏ nhưng vẫn thua từng HIGH.
~~~

Nếu cần bảo đảm tiến độ cho nhóm priority thấp, hãy thiết kế **fairness** hoặc cơ chế điều phối riêng: queue phân tầng có quota, reserved worker, deadline-aware scheduling hay aging có tái đánh giá đúng cách. Comparator theo priority và sequence chỉ giải quyết bài toán **công bằng trong cùng mức**, không thay thế chính sách công bằng giữa các mức.

### Vì sao aging không chỉ là \`System.currentTimeMillis()\` trong comparator?

Một priority queue giữ thứ tự theo quá trình thêm/lấy phần tử. Nếu khóa so sánh tự thay đổi theo thời gian, queue **không nhất thiết tái tổ chức toàn bộ** chỉ vì đồng hồ trôi qua. Comparator đọc giờ hiện tại cho mỗi lần so sánh còn có thể vi phạm tính nhất quán. Aging thực tế cần scheduler tính lại quyền ưu tiên và sắp xếp lại, hoặc chuyển message qua các queue/nhóm điều phối phù hợp.

## 11. Khi đặt trong Router, Splitter, Aggregator và Gateway

Priority và tie-breaker thường chỉ là **một đoạn** của flow:

~~~mermaid
flowchart LR
    IN["Gateway / Input"] --> R{"Router"}
    R --> V["Header Enricher\npriority + sequence"]
    V --> Q["PriorityChannel"]
    Q --> P["Poller"]
    P --> H["Service Activator / Transformer"]
    H --> OUT["Output"]
    H -.-> E["Error handling"]
~~~

Khi kiểm thử flow như trên, hãy tách hai câu hỏi:

- **Ordering test:** Sau khi tất cả message đã nằm trong queue, \`receive()\` có tuân thủ priority và tie-breaker không?
- **Integration test:** Router, Header Enricher, Poller và handler có truyền đúng payload, headers và đường lỗi không?

### Router và Filter

Router có thể gửi nhiều loại message đến cùng một PriorityChannel. Các nhánh cần thống nhất cách gán priority và sequence. Filter có thể loại message trước queue; message bị loại không được tính như một phần tử đang chờ được lấy.

### Splitter và Aggregator

Splitter tạo nhiều fragment cho một request. Nếu mỗi fragment có cùng priority, tie-breaker theo sequence của **thứ tự enqueue** có thể quyết định thứ tự lấy, nhưng không thay thế \`sequenceNumber\` của **nhóm aggregation**.

Phân biệt:

| Header | Mục đích |
| --- | --- |
| \`enqueueSequence\` | Khóa để xếp thứ tự trong PriorityChannel theo hợp đồng ứng dụng |
| \`correlationId\` | Khóa nhóm của Splitter/Aggregator |
| \`sequenceNumber\` | Vị trí fragment trong nhóm |
| \`sequenceSize\` | Kích thước nhóm dự kiến |

Đừng dùng \`sequenceNumber\` của Splitter làm khóa tie-break **toàn cục** nếu có nhiều nhóm xen kẽ: nhiều nhóm đều có fragment số 1, số 2. Nếu cần thứ tự trong từng nhóm, hãy xác định phạm vi và kiểm tra correlation cùng thứ tự riêng.

### Gateway và reply

Gateway đồng bộ có thể chờ reply trong khi message nằm ở PriorityChannel. Tie-breaker không bảo đảm thứ tự caller nhận reply nếu các handler xử lý không đồng đều. Đặt timeout hữu hạn và kiểm tra hành vi khi request không được phục vụ kịp.

### Retry và error channel

Khi handler lỗi và message được retry, nó có thể bị xử lý lại mà không cần quay trở lại queue; hoặc một luồng recovery có thể enqueue lại thành message mới. Trong trường hợp enqueue lại, hãy quy định có giữ \`enqueueSequence\` cũ hay cấp mới. Hai lựa chọn có ý nghĩa khác nhau:

- **Giữ sequence:** Ưu tiên thứ tự lần gửi ban đầu; có thể làm request retry vượt message mới cùng priority.
- **Cấp mới:** Đưa message retry về cuối nhóm cùng priority theo thứ tự enqueue mới.

Hãy kiểm tra cả \`requestId\`, correlation và khóa idempotency; tie-breaker không tự ngăn tác dụng phụ lặp khi retry.

## 12. Kiểm thử nhiều producer và các điều kiện biên

Đối với một queue trong bộ nhớ, test đơn luồng có thể xác nhận comparator. Nhưng nếu hệ thống có nhiều producer, nhiều process hoặc message broker, cần mở rộng kiểm tra.

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Hai message cùng priority, sequence khác nhau | Sequence nhỏ lấy trước |
| Priority khác nhau, sequence đảo ngược | Priority cao vẫn lấy trước |
| Nhiều message cùng priority | Thứ tự theo chuỗi sequence được cam kết |
| Hai message cùng priority và cùng sequence | Có cảnh báo/từ chối hoặc khóa phụ rõ ràng |
| Header sai kiểu hoặc thiếu | Validation xử lý trước queue |
| Producer cấp sequence rồi gửi chậm | Test phân biệt thứ tự cấp số với thứ tự queue thực nhận |
| Queue đầy | Không mặc định message quan trọng hơn sẽ thay message cũ |
| Hai consumer xử lý song song | Thứ tự poll có thể đúng dù thứ tự hoàn tất khác |
| Retry đưa message vào queue lần nữa | Sequence và idempotency tuân thủ chính sách |
| Nhiều replica có state riêng | Không tuyên bố thứ tự toàn cục nếu thiếu bộ cấp sequence phối hợp |

### Tránh test flaky

- Enqueue **toàn bộ backlog** trước lần \`receive\` đầu khi kiểm tra comparator.
- Dùng một \`PriorityChannel\` mới cho mỗi test; tiêu thụ hết message.
- Không bật poller chạy song song khi mục tiêu là xác định chính xác thứ tự lấy.
- Kiểm tra header nghiệp vụ và payload, tránh so sánh UUID/timestamp tự sinh.
- Với flow bất đồng bộ, dùng timeout hữu hạn và điều kiện hoàn tất phù hợp; không dùng \`Thread.sleep\` cố định như bằng chứng ordering.
- Nếu kiểm tra thứ tự theo enqueue thực, phải xác định trước ranh giới nào được xem là **thời điểm enqueue**.

## 13. Bài thực hành

### Bài A — Thêm tiêu chí phá hòa

Tạo \`PriorityChannel\` có comparator chỉ so sánh \`priority\`. Gửi ba message cùng mức 9. Giải thích vì sao kết quả quan sát được của một lần chạy không đủ chứng minh FIFO. Sau đó thêm \`enqueueSequence\` và viết test với sequence 3, 1, 2; assert thứ tự lấy là 1, 2, 3.

### Bài B — Kết hợp priority và deadline

Xây comparator với hai khóa: priority giảm dần, deadline tăng dần. Gửi hai message cùng priority có deadline khác nhau và một message priority thấp nhưng deadline sớm hơn. Kiểm tra priority vẫn là khóa chính, còn deadline chỉ quyết định thứ tự khi priority bằng nhau. Thảo luận nếu nghiệp vụ muốn deadline được ưu tiên hơn priority thì phải thay đổi thứ tự các khóa.

### Bài C — Phát hiện lỗi dữ liệu

Tạo message có \`priority="9"\` dạng String, một message thiếu \`enqueueSequence\` và hai message trùng sequence. Viết validation hoặc chính sách bổ sung để các dữ liệu này không làm thứ tự queue trở nên mơ hồ.

### Bài D — Producer chạy song song

Mô phỏng producer A lấy sequence trước nhưng gửi sau producer B. So sánh hai hợp đồng: **theo thứ tự phân bổ số** và **theo thứ tự enqueue thực tế**. Chọn một hợp đồng, thiết kế điểm đồng bộ phù hợp và viết test xác nhận.

### Bài E — Retry trong cùng priority

Tạo một message priority 9 bị lỗi và enqueue lại, cùng lúc có hai message priority 9 khác đang chờ. Thử hai chính sách giữ sequence và cấp sequence mới. Ghi rõ thứ tự nhận mong đợi và hệ quả với fairness/idempotency.

## 14. Checklist và kết luận

Trước khi đưa comparator tùy biến vào một luồng Spring Integration, hãy xác nhận:

1. Priority nào cao hơn: số lớn hơn hay nhỏ hơn, và comparator có đúng chiều?
2. Khi priority bằng nhau, tie-breaker là gì: enqueue sequence, deadline hay khóa nghiệp vụ?
3. Tie-breaker có **duy nhất, ổn định và đúng phạm vi** không?
4. Nếu dùng sequence, nó được cấp khi nào và có cùng điểm tuần tự hóa với enqueue không?
5. Timestamp có thể trùng hoặc lệch đồng hồ không?
6. Có validation cho header thiếu/sai kiểu hoặc khóa trùng không?
7. Test có phân biệt thứ tự lấy và thứ tự hoàn tất không?
8. Retry, nhiều producer và nhiều replica có thay đổi semantics của thứ tự không?
9. Nếu mục tiêu là chống starvation giữa các mức priority, đã có fairness policy riêng chưa?
10. Có ghi lại được \`requestId\`, correlation và metadata cần thiết để giải thích vì sao một message được chọn trước không?

**Kết luận:** Tie-breaker biến tình huống “hai message cùng priority” từ một thứ tự không có cam kết thành một **quy tắc rõ ràng và kiểm thử được**. Trong Spring Integration, ưu tiên nên được định nghĩa thành comparator có khóa chính và khóa phụ ổn định, còn cơ chế cấp khóa cần phù hợp với phạm vi mà hệ thống muốn bảo đảm. Khi phân biệt đúng thứ tự enqueue, thứ tự lấy và thứ tự hoàn tất, bạn có thể mở rộng luồng có Router, Splitter/Aggregator, Gateway, retry và error channel mà không vô tình phụ thuộc vào thứ tự ngẫu nhiên của hàng đợi.
