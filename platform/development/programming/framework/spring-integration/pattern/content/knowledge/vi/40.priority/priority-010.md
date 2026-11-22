# Kiểm thử nhiều mức ưu tiên trong Spring Integration

## 1. Vì sao kiểm thử priority phải vượt qua một phép so sánh số?

Trong hệ thống xử lý đơn hàng, doanh nghiệp muốn ưu tiên thông điệp phát hiện gian lận trước thông điệp cập nhật báo cáo. Một kiểm thử đơn giản gửi `priority=9` và `priority=1` vào `PriorityChannel` rồi xác nhận thông điệp 9 được lấy trước. Phép thử ấy có ích, nhưng **chưa đủ** để kết luận luồng hoạt động đúng ở production.

Khi thực tế có **HIGH/NORMAL/LOW**, message có thể đi qua Gateway, Transformer, Filter, Router, Splitter, Aggregator, polling endpoint, retry, error channel và một broker. Những tình huống sau vẫn có thể xảy ra dù phép thử hai message thành công:

- Transformer tạo `Message` mới nhưng làm mất `priority` hoặc thay đổi kiểu `Integer` thành `String`.
- HIGH đến sau khi LOW đã được lấy khỏi queue, nên không thể giành quyền xử lý lại.
- Nhiều message cùng priority có thứ tự khác FIFO, trong khi test vô tình giả định thứ tự ổn định.
- HIGH liên tục đến khiến LOW chờ vô thời hạn (**priority starvation**).
- Error flow retry HIGH không giới hạn, chiếm capacity của các tác vụ hợp lệ.
- Listener dùng `ExecutorChannel` hoặc nhiều worker, khiến **thứ tự hoàn tất** khác thứ tự dequeue.
- JMS/RabbitMQ chưa map header ưu tiên đúng; Kafka giữ record theo offset thay vì custom priority.
- Message đã được ACK nhưng database chưa commit, hoặc database đã commit rồi message được redeliver, gây xử lý trùng.

**Kiểm thử nhiều mức ưu tiên** là kiểm tra một **hợp đồng xuyên luồng**: phân loại đúng, giữ metadata đúng, chọn lượt đúng trong những điều kiện xác định, không để công việc hợp lệ bị bỏ đói ngoài chính sách, và vẫn phục hồi được khi lỗi.

Bài học thuộc chương **Priority** trong module `SPRING_INTEGRATION_PATTERN`, phục vụ mục tiêu triển khai Enterprise Integration Patterns với Spring Integration theo hướng ít phụ thuộc, dễ mở rộng, có thể kiểm thử và theo dõi từng nhánh xử lý.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Thiết kế **test matrix** cho HIGH/NORMAL/LOW, cùng mức ưu tiên, priority không hợp lệ và message đến muộn.
2. Viết unit test JUnit 5 kiểm tra `PriorityChannel`, comparator, thứ tự lấy message và invariants quan trọng.
3. Phân biệt test **ordering** với test **fairness, throughput, SLA và durability**.
4. Kiểm tra `priority` sau Transformer, Router, Filter, Splitter, Aggregator và Gateway.
5. Kiểm thử retry, error channel, dead-letter, redelivery, concurrency và idempotency.
6. Phân tách kiểm thử thuần Java, Spring context integration test và kiểm thử broker thật.
7. Đưa kiểm thử vào CI với tiêu chí có thể đo lường, không lệ thuộc `Thread.sleep` hoặc thứ tự thread ngẫu nhiên.

## 2. Định nghĩa hợp đồng ưu tiên trước khi viết test

Đầu tiên, quyết định priority là **chính sách nghiệp vụ** hay **con số kỹ thuật** của scheduler. Ta sử dụng ba lớp:

| Lớp | Header `priority` nội bộ | Ví dụ nghiệp vụ | Chính sách |
| --- | ---: | --- | --- |
| HIGH | `9` | Chặn giao dịch rủi ro, hủy đơn khẩn | Được ưu tiên khi còn nằm trong hàng đợi. |
| NORMAL | `5` | Xác nhận thanh toán, cập nhật trạng thái | Không được mất cơ hội xử lý vì HIGH vô hạn. |
| LOW | `1` | Đồng bộ báo cáo, thống kê định kỳ | Có quota/lượt xử lý nếu yêu cầu fairness. |

Đây là **quy ước của ví dụ**, không phải ba giá trị bắt buộc của Spring Integration. Với `PriorityChannel` mặc định, mức số cao hơn thường được ưu tiên hơn khi **lấy** message đang chờ.

Phải công bố:

- **Miền giá trị:** ví dụ số nguyên `0..9`, không chấp nhận chuỗi `"9"` nếu chưa qua decoder chuẩn hóa.
- **Nguồn quyền hạn:** chỉ policy của backend được quyết định HIGH; client không đáng tin không được tự nâng cấp.
- **Ý nghĩa của thiếu header:** reject, quarantine, hay dùng default NORMAL/LOW có ghi metric.
- **Định danh:** `eventId` ổn định để chống trùng; `MessageHeaders.ID` có thể đổi khi dựng message mới.
- **Tie-breaking:** thông điệp cùng priority có phải FIFO theo `enqueueSequence`/thời điểm không?
- **Fairness:** có đảm bảo tiến triển của NORMAL/LOW dưới HIGH liên tục không? Nếu có, bằng WRR, aging, deadline hay reserved worker?
- **SLA/SLO:** độ trễ tính từ lúc nào, đến lúc bắt đầu xử lý hay đến khi nghiệp vụ commit?

### Fixture Java dùng trong các kiểm thử

Các snippet dưới đây dùng Java 17+, Spring Integration, Spring Messaging và JUnit Jupiter. Khi ghép thành dự án, đặt class/hàm trong những file Java thích hợp và bổ sung import cần thiết.

~~~java
enum WorkClass {
    HIGH(9), NORMAL(5), LOW(1);

    private final int priority;

    WorkClass(int priority) {
        this.priority = priority;
    }

    int value() {
        return priority;
    }
}

record WorkEvent(String eventId, String type) {}

final class PriorityContract {
    static final String PRIORITY = "priority";
    static final String EVENT_ID = "businessEventId";
    static final String ENQUEUED_AT = "originalEnqueuedAt";

    private PriorityContract() {}

    static Message<WorkEvent> message(
            String eventId, WorkClass workClass) {
        return MessageBuilder.withPayload(
                    new WorkEvent(eventId, workClass.name()))
                .setHeader(PRIORITY, workClass.value())
                .setHeader(EVENT_ID, eventId)
                .build();
    }

    static int requirePriority(Message<?> message) {
        Object value = message.getHeaders().get(PRIORITY);
        if (!(value instanceof Integer priority)
                || priority < 0 || priority > 9) {
            throw new IllegalArgumentException(
                    "priority must be Integer in range 0..9");
        }
        return priority;
    }
}
~~~

Ví dụ sử dụng header chuỗi `priority` để người học dễ quan sát. Tại ranh giới HTTP/JMS/AMQP/Kafka, adapter có thể sử dụng **header hoặc property khác**; các kiểm thử mapping phải xem xét đích thật, không chỉ so sánh chuỗi này.

## 3. Ma trận kiểm thử trước khi viết mã

| Nhóm | Input | Invariant cần chứng minh | Cấp kiểm thử |
| --- | --- | --- | --- |
| **Ba lớp** | LOW, HIGH, NORMAL, HIGH đã enqueue hết | HIGH được dequeue trước NORMAL, NORMAL trước LOW khi các priority phân biệt. | Unit |
| **Cùng lớp** | HIGH-A, HIGH-B | Không mất/nhân đôi message; chỉ assert FIFO nếu contract có tie-breaker rõ. | Unit |
| **Thiếu header** | Không có `priority` | Bị reject/chuẩn hóa theo ingress policy, không tự thành HIGH. | Unit + integration |
| **Sai kiểu** | `priority="9"`, null hoặc ngoài miền | Validator từ chối hoặc decoder xử lý đúng quy tắc. | Unit |
| **Đến muộn** | LOW đã dequeue, sau đó HIGH đến | Không đòi preemption của công việc đang chạy. | Unit + integration |
| **Qua EIP** | Message HIGH qua Transformer, Router, Filter, Splitter | Header giữ hoặc được tính lại đúng contract. | Spring integration |
| **Aggregator** | Nhiều message con priority 1, 5, 9 | Priority kết quả tuân theo MAX/parent/deadline policy đã định. | Unit + integration |
| **Fairness** | HIGH không ngừng đến, LOW luôn backlog | LOW vẫn được dispatch trong ngân sách đã công bố. | Deterministic unit + load |
| **Retry** | HIGH bị lỗi ba lần | Không retry vô hạn; định danh/priority giữ qua retry, error path đúng. | Integration |
| **Concurrency** | Nhiều producer/consumer | Không mất/duplicate ở phạm vi được cam kết; không assert completion order toàn cục. | Integration + stress |
| **Broker** | Hai message priority khác nhau | JMS/AMQP property thật đúng; Kafka header decode đúng nhưng không mặc định reorder. | Broker integration |
| **Crash/rollback** | Lỗi trước/sau DB commit, trước ACK | Xử lý lặp an toàn hoặc redelivery đúng cơ chế nguồn. | Failure injection |

**Một điều kiện phải luôn ghi rõ trong tên/thiết lập test:** message đã có trong queue **trước** lúc poll hay HIGH đến sau khi LOW đã được lấy? Hai bài toán này khác nhau.

## 4. Unit test đầu tiên: ba mức HIGH > NORMAL > LOW

`PriorityChannel` là `PollableChannel` có logic chọn message theo priority. Để test ổn định, **enqueue toàn bộ message trước khi receive** và dùng một thread:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;

class PriorityChannelOrderingTest {

    @Test
    void dequeuesAllHigherPrioritiesBeforeLowerPriorities() {
        PriorityChannel channel = new PriorityChannel(20);

        channel.send(PriorityContract.message("L-1", WorkClass.LOW));
        channel.send(PriorityContract.message("H-1", WorkClass.HIGH));
        channel.send(PriorityContract.message("N-1", WorkClass.NORMAL));

        Message<?> first = channel.receive(0);
        Message<?> second = channel.receive(0);
        Message<?> third = channel.receive(0);

        assertNotNull(first);
        assertNotNull(second);
        assertNotNull(third);

        assertEquals(9, PriorityContract.requirePriority(first));
        assertEquals(5, PriorityContract.requirePriority(second));
        assertEquals(1, PriorityContract.requirePriority(third));

        assertNull(channel.receive(0));
    }
}
~~~

Đây là **unit test ordering**, không phải kiểm thử transaction, fairness hoặc SLA. Nó xác nhận thứ tự **lấy message** trong một channel đơn lẻ đã có dữ liệu sẵn.

### Nên kiểm tra payload/event ID cùng lúc

Chỉ kiểm tra priority sequence 9–5–1 vẫn chưa chứng minh không mất/nhân đôi message. Có thể bổ sung:

~~~java
Set<String> actualIds = List.of(first, second, third).stream()
        .map(message -> (String) message.getHeaders()
                .get(PriorityContract.EVENT_ID))
        .collect(Collectors.toSet());

assertEquals(Set.of("L-1", "H-1", "N-1"), actualIds);
~~~

Nếu thêm message thứ tư, nên assert cả **số lượng message** và **tập `eventId`**. Dùng business ID, không dùng `MessageHeaders.ID` để suy luận xử lý một lần trong những lần retry/rebuild message.

## 5. Unit test nhiều message, cùng priority và tie-breaking

### 5.1. Khi không có yêu cầu FIFO trong cùng mức

Priority queue sử dụng comparator có thể không bảo đảm FIFO giữa những message được xem là bằng nhau. Đừng viết test phụ thuộc thứ tự HIGH-A, HIGH-B nếu chưa cấu hình thứ tự phụ.

~~~java
@Test
void messagesWithSamePriorityAreAllPresent() {
    PriorityChannel queue = new PriorityChannel(16);

    queue.send(PriorityContract.message("H-A", WorkClass.HIGH));
    queue.send(PriorityContract.message("H-B", WorkClass.HIGH));
    queue.send(PriorityContract.message("L-C", WorkClass.LOW));

    Message<?> first = queue.receive(0);
    Message<?> second = queue.receive(0);
    Message<?> third = queue.receive(0);

    assertEquals(9, PriorityContract.requirePriority(first));
    assertEquals(9, PriorityContract.requirePriority(second));
    assertEquals(1, PriorityContract.requirePriority(third));

    Set<Object> ids = Set.of(
            first.getHeaders().get(PriorityContract.EVENT_ID),
            second.getHeaders().get(PriorityContract.EVENT_ID));
    assertEquals(Set.of("H-A", "H-B"), ids);
}
~~~

### 5.2. Nếu nghiệp vụ bắt buộc FIFO trong cùng mức

Phải đưa tie-breaker vào **hợp đồng**, ví dụ một `enqueueSequence` tăng dần tại điểm enqueue có trật tự xác định:

~~~java
Comparator<Message<?>> priorityThenSequence = (left, right) -> {
    int byPriority = Integer.compare(
            PriorityContract.requirePriority(right),
            PriorityContract.requirePriority(left));
    if (byPriority != 0) {
        return byPriority;
    }

    long leftSequence =
            ((Number) left.getHeaders().get("enqueueSequence")).longValue();
    long rightSequence =
            ((Number) right.getHeaders().get("enqueueSequence")).longValue();
    return Long.compare(leftSequence, rightSequence);
};

PriorityChannel queue =
        new PriorityChannel(32, priorityThenSequence);
~~~

Test:

~~~java
@Test
void customComparatorUsesSequenceWithinSamePriority() {
    PriorityChannel queue = new PriorityChannel(
            32, priorityThenSequence);

    queue.send(MessageBuilder.withPayload("H-2")
            .setHeader("priority", 9)
            .setHeader("enqueueSequence", 2L).build());
    queue.send(MessageBuilder.withPayload("N-1")
            .setHeader("priority", 5)
            .setHeader("enqueueSequence", 1L).build());
    queue.send(MessageBuilder.withPayload("H-1")
            .setHeader("priority", 9)
            .setHeader("enqueueSequence", 1L).build());

    assertEquals("H-1", queue.receive(0).getPayload());
    assertEquals("H-2", queue.receive(0).getPayload());
    assertEquals("N-1", queue.receive(0).getPayload());
}
~~~

Đặt comparator và test trong cùng fixture/class hoặc bean cấu hình riêng; các snippet trên minh họa từng phần của cùng một test. **Không tự suy ra global FIFO trên nhiều producer/nhiều instance**: sequence phải được cấp phát theo một cơ chế có ordering rõ. Khi sử dụng persistent message store, cần kiểm tra loại store có hỗ trợ comparator hoặc thứ tự tương ứng hay không; comparator RAM không mặc định áp dụng cho broker hay database store.

### 5.3. Không dùng clock động làm comparator mặc định

Một comparator đọc `System.currentTimeMillis()` để tự tăng priority theo tuổi chờ thường **không làm heap tự sắp lại theo thời gian**. Đó là bài toán aging cần scheduler cập nhật/promote hoặc chọn lại message ở mỗi lần quyết định; viết test comparator riêng không chứng minh aging thực tế.

## 6. Biên dữ liệu: priority bị thiếu, sai kiểu hoặc vượt miền

Một test tốt không chờ đến khi `PriorityChannel` phát sinh exception mới xác định hệ thống có policy. Nên **validate tại ingress** và test theo hợp đồng riêng của ứng dụng.

~~~java
record IncomingWork(String eventId, String type, Object requestedPriority) {}

final class PriorityPolicy {
    static int fromTrustedType(String type) {
        return switch (type) {
            case "FRAUD_ALERT", "RISK_CANCEL" -> 9;
            case "PAYMENT_CONFIRMED", "ORDER_UPDATED" -> 5;
            case "METRICS_REFRESH", "REPORT_REFRESH" -> 1;
            default -> throw new IllegalArgumentException(
                    "Unknown work type: " + type);
        };
    }

    static Message<WorkEvent> normalize(IncomingWork raw) {
        int priority = fromTrustedType(raw.type());
        return MessageBuilder.withPayload(
                    new WorkEvent(raw.eventId(), raw.type()))
                .setHeader(PriorityContract.PRIORITY, priority)
                .setHeader(PriorityContract.EVENT_ID, raw.eventId())
                .build();
    }
}
~~~

Ở ví dụ này `requestedPriority` không được tin cậy: backend **tự phân loại** dựa trên loại nghiệp vụ đã xác thực. Với yêu cầu có nguồn được quyền đề xuất priority, phải thêm authorization trước khi xét giá trị yêu cầu.

~~~java
@ParameterizedTest
@CsvSource({
        "FRAUD_ALERT, 9",
        "PAYMENT_CONFIRMED, 5",
        "METRICS_REFRESH, 1"
})
void serverPolicyAssignsCorrectPriority(String type, int expected) {
    Message<WorkEvent> output = PriorityPolicy.normalize(
            new IncomingWork("E-100", type, "FORGED_HIGH"));
    assertEquals(expected, PriorityContract.requirePriority(output));
}

@Test
void rejectsUnknownBusinessType() {
    assertThrows(IllegalArgumentException.class,
            () -> PriorityPolicy.normalize(
                    new IncomingWork("E-101", "UNRECOGNIZED", 9)));
}

@Test
void rejectsInvalidPriorityHeadersAtInternalBoundary() {
    Message<String> invalid = MessageBuilder.withPayload("WORK")
            .setHeader("priority", "9")
            .build();
    assertThrows(IllegalArgumentException.class,
            () -> PriorityContract.requirePriority(invalid));
}
~~~

### Ma trận biên cụ thể

| Input | Chính sách nên kiểm thử |
| --- | --- |
| `Integer(9)` | Nhận nếu HIGH hợp lệ và được cấp quyền. |
| `Integer(0)` | Nhận hoặc từ chối theo miền ứng dụng; không tự suy 0 là LOW nếu contract nói LOW=1. |
| `Integer(-1)` / `Integer(10)` | Từ chối theo ví dụ miền 0..9. |
| `String("9")` | Từ chối ở boundary nội bộ, hoặc decode ở adapter có kiểm soát. |
| `null`/thiếu header | Áp default đã công bố hoặc đưa vào error/quarantine. |
| `Long(9)` | Chỉ chấp nhận khi decoder có quy tắc chuyển kiểu rõ, tránh ép kiểu âm thầm. |
| Header client tự gán HIGH | Không cho nâng quyền khi caller không được cấp phép. |
| Retry cùng business event | Giữ `eventId` và priority policy source, không tạo một công việc mới ngoài ý muốn. |

**Không ép kiểu bằng `toString()` một cách vô điều kiện**, nhất là khi header nguồn có thể là một object không được phép serialize hoặc kiểu không tương thích.

## 7. Test Transformer: priority phải còn sau khi payload thay đổi

Trong Spring Integration, Transformer có thể nhận payload hoặc `Message` và tạo output mới. Framework có các quy tắc kế thừa headers của endpoint; custom transformer/adapters có thể viết lại hoặc lọc header. Cách kiểm thử đáng tin cậy là **đọc output của flow**, không chỉ kiểm tra việc caller đã set header.

Ví dụ xử lý có chủ đích:

~~~java
record RawWork(String eventId, String rawType) {}
record NormalizedWork(String eventId, String type) {}

final class NormalizingTransformer {
    Message<NormalizedWork> normalize(Message<RawWork> input) {
        RawWork raw = input.getPayload();
        int priority = PriorityContract.requirePriority(input);

        return MessageBuilder.withPayload(
                    new NormalizedWork(
                            raw.eventId(),
                            raw.rawType().trim().toUpperCase(Locale.ROOT)))
                .copyHeaders(input.getHeaders())
                .setHeader(PriorityContract.PRIORITY, priority)
                .build();
    }
}
~~~

Unit test:

~~~java
@Test
void transformerPreservesPriorityAndBusinessEventId() {
    Message<RawWork> input = MessageBuilder
            .withPayload(new RawWork("E-17", "fraud_alert"))
            .setHeader("priority", 9)
            .setHeader(PriorityContract.EVENT_ID, "E-17")
            .build();

    Message<NormalizedWork> result =
            new NormalizingTransformer().normalize(input);

    assertEquals(9, PriorityContract.requirePriority(result));
    assertEquals("E-17",
            result.getHeaders().get(PriorityContract.EVENT_ID));
    assertEquals("FRAUD_ALERT", result.getPayload().type());
}
~~~

Khi triển khai thêm Transformer endpoint, viết **integration test qua channel** để xác nhận output thật của adapter. Ví dụ, việc tự dựng một `MessageBuilder.withPayload(...)` rồi không copy headers có thể làm mất metadata trong custom code; trong một số endpoint, Spring Integration còn có logic merge/copy reply headers. **Đừng khẳng định mọi Transformer mặc định luôn làm mất header.**

### Test phủ cả nhánh Router và Filter

Cho hai nhánh:

~~~mermaid
flowchart LR
    I["input priority 9/5/1"] --> T["Transformer normalize"]
    T --> R{"Router theo type"}
    R --> H["HIGH route"]
    R --> N["NORMAL/LOW route"]
    H --> Q["PriorityChannel"]
    N --> Q
    Q --> C["Consumer"]
~~~

Các assertion phải bao gồm:

- Cả nhánh HIGH và NORMAL/LOW đều giữ `eventId` và priority đã chuẩn hóa.
- Message bị Filter loại theo business rule **không xuất hiện** trong queue; metric `filtered` khác với `priority_missing`.
- Nếu có discard channel, message được đưa vào nhánh đó phải có metadata đủ để điều tra.
- Router không tự nâng priority chỉ vì một nhánh mang tên `urgent`; nếu có nâng, đó phải là policy được test.
- Không giả định một `DirectChannel` ở nhánh HIGH tự reorder khi hai message đến gần nhau.

## 8. Test Splitter và Aggregator: priority của message con và kết quả nhóm

Splitter tạo ra nhiều thông điệp từ một message gốc. Một `Aggregator` có thể gom các kết quả theo `correlationId`. Hai EIP này đặt ra câu hỏi **priority mới được tính như thế nào**.

### Chính sách ví dụ

- Message con **thừa kế** priority của parent nếu không có quy tắc nâng riêng.
- Nếu một item đặc biệt quan trọng, priority của item có thể là `max(parentPriority, itemPriority)` theo policy.
- Aggregator output chọn **priority lớn nhất** trong các message thuộc nhóm; alternative là giữ parent priority nếu cần semantics đó.

Ví dụ kiểm thử hàm business cho Aggregator:

~~~java
static int aggregatePriority(Collection<Message<?>> messages) {
    if (messages.isEmpty()) {
        throw new IllegalArgumentException("Cannot aggregate empty group");
    }
    return messages.stream()
            .mapToInt(PriorityContract::requirePriority)
            .max()
            .orElseThrow();
}

@Test
void aggregatedPriorityUsesMaximumOfChildren() {
    List<Message<?>> parts = List.of(
            PriorityContract.message("C-1", WorkClass.NORMAL),
            PriorityContract.message("C-2", WorkClass.HIGH),
            PriorityContract.message("C-3", WorkClass.LOW));

    assertEquals(9, aggregatePriority(parts));
}
~~~

Trong bài thực hành, khi áp dụng vào một `@Aggregator` hoặc Java DSL thật, cần test thêm:

| Kịch bản | Tiêu chí |
| --- | --- |
| Ba message con 1, 5, 9 đến đủ | Output priority theo MAX = 9, payload ghép đúng. |
| Các message đến thứ tự đảo ngược | Output priority không phụ thuộc message đến đầu/cuối. |
| Một message con bị redeliver | Không làm tăng số item nghiệp vụ hoặc thay đổi kết quả tùy ý. |
| Group timeout/partial release | Output dùng policy rõ cho **những message hiện có** hoặc parent metadata đã lưu. |
| Aggregator lưu state bền vững rồi restart | Priority/correlation và thông tin cần thiết còn sau serialization. |
| Message đến trễ sau release | Có policy discard/reopen/reconcile rõ, không tạo event sai. |

`correlationId` và `sequenceNumber` giúp aggregation; chúng không thay thế business event ID. Khi test Splitter, cần kiểm tra cả priority và các correlation headers mà endpoint thực sự thêm vào output.

## 9. Test Gateway và request–reply

Gateway đồng bộ cho phép gửi message vào một flow và nhận response. Cần kiểm thử **request priority** tại đầu vào, đồng thời xác định reply có cần giữ priority hay có policy riêng.

~~~java
@MessagingGateway(defaultRequestChannel = "priorityIngress")
interface PriorityGateway {
    void submit(Message<WorkEvent> work);
}
~~~

Gửi:

~~~java
gateway.submit(PriorityContract.message("E-900", WorkClass.HIGH));
~~~

Các test tích hợp nên kiểm tra:

1. Message thật tại `priorityIngress` có `priority=9` và đúng event ID.
2. Nếu flow tiếp tục vào `PriorityChannel`, giá trị này vẫn đúng trước khi enqueue.
3. Nếu Gateway chỉ nhận payload mà không có header, phải có **Header Enricher/policy** nội bộ, không chờ header tự xuất hiện.
4. Với Gateway có reply, request timeout và reply metadata phải được test **độc lập**; reply đến sau khi request đã timeout không được coi là thành công của request gốc.
5. Nếu handler trả về `Message` mới, reply/error-channel headers không được lọc nhầm.

Priority 9 trong request **không** chứng minh response sẽ hoàn tất nhanh nếu handler còn chờ lock, downstream hoặc broker.

## 10. Unit test fairness: LOW vẫn tiến triển khi HIGH luôn có backlog

Strict priority và fairness là **hai chính sách khác nhau**. `PriorityChannel` có thể hoạt động đúng theo comparator nhưng vẫn khiến LOW chờ quá lâu khi HIGH liên tục. Nếu doanh nghiệp yêu cầu LOW có **suất xử lý tối thiểu**, phải kiểm thử thuật toán khác như weighted round-robin (WRR), aging hay reserved capacity.

### Scheduler mẫu 4:2:1

Ví dụ sau sử dụng ba `PollableChannel` riêng, mỗi kênh FIFO, với lịch 4 HIGH, 2 NORMAL, 1 LOW. Đây là bộ chọn message minh họa **cho bài kiểm thử**, chưa có durability, transaction hoặc ACK.

~~~java
final class WeightedSelector {
    private static final int[] SLOTS = {0, 0, 0, 0, 1, 1, 2};

    private final PollableChannel[] queues;
    private int nextSlot;

    WeightedSelector(
            PollableChannel high,
            PollableChannel normal,
            PollableChannel low) {
        this.queues = new PollableChannel[]{high, normal, low};
    }

    synchronized Message<?> next() {
        for (int offset = 0; offset < SLOTS.length; offset++) {
            int index = (nextSlot + offset) % SLOTS.length;
            Message<?> value = queues[SLOTS[index]].receive(0);
            if (value != null) {
                nextSlot = (index + 1) % SLOTS.length;
                return value;
            }
        }
        nextSlot = (nextSlot + 1) % SLOTS.length;
        return null;
    }
}
~~~

Để test 4:2:1, **enqueue đủ backlog cho mọi lớp trước khi gọi `next()`**:

~~~java
@Test
void lowMakesProgressEvenWithContinuousHighBacklog() {
    QueueChannel high = new QueueChannel(100);
    QueueChannel normal = new QueueChannel(100);
    QueueChannel low = new QueueChannel(100);

    for (int i = 0; i < 30; i++) {
        high.send(PriorityContract.message(
                "H-" + i, WorkClass.HIGH));
    }
    for (int i = 0; i < 20; i++) {
        normal.send(PriorityContract.message(
                "N-" + i, WorkClass.NORMAL));
    }
    for (int i = 0; i < 10; i++) {
        low.send(PriorityContract.message(
                "L-" + i, WorkClass.LOW));
    }

    WeightedSelector selector = new WeightedSelector(high, normal, low);
    List<Integer> actual = new ArrayList<>();

    for (int i = 0; i < 14; i++) {
        Message<?> message = selector.next();
        assertNotNull(message);
        actual.add(PriorityContract.requirePriority(message));
    }

    assertEquals(8, Collections.frequency(actual, 9));
    assertEquals(4, Collections.frequency(actual, 5));
    assertEquals(2, Collections.frequency(actual, 1));
    assertTrue(actual.subList(0, 7).contains(1));
    assertTrue(actual.subList(7, 14).contains(1));
}
~~~

Đây là **kiểm thử quota theo số lượt chọn**, không phải bằng chứng một message LOW chắc chắn hoàn tất trong một số giây. Nó giả định `next()` tiếp tục được gọi và downstream hoàn tất trong thời gian hữu hạn.

### Kiểm thử khi có queue trống

~~~java
@Test
void idleHighAndNormalDoNotBlockLow() {
    QueueChannel high = new QueueChannel(10);
    QueueChannel normal = new QueueChannel(10);
    QueueChannel low = new QueueChannel(10);

    low.send(PriorityContract.message("L-1", WorkClass.LOW));
    low.send(PriorityContract.message("L-2", WorkClass.LOW));

    WeightedSelector selector = new WeightedSelector(high, normal, low);

    assertEquals("L-1", selector.next()
            .getHeaders().get(PriorityContract.EVENT_ID));
    assertEquals("L-2", selector.next()
            .getHeaders().get(PriorityContract.EVENT_ID));
    assertNull(selector.next());
}
~~~

Kiểm thử này chứng minh scheduler **work-conserving**: không bỏ trống những lượt khi HIGH/NORMAL không có công việc.

**Giới hạn cần tách riêng:** ba `QueueChannel` RAM không hỗ trợ redelivery bền vững theo JDBC transaction. Đối với production, phải thay bằng queue/store/broker phù hợp và đưa ACK/rollback vào cùng thiết kế.

## 11. Aging và deadline: test với thời gian giả, không dùng sleep dài

Nếu LOW phải được ưu tiên thêm sau khi chờ lâu, có thể đặt:

~~~text
effectivePriority = basePriority + floor(waitSeconds / agingStepSeconds)
~~~

Một test dựa trên `Thread.sleep(60_000)` vừa chậm vừa dễ flaky. Nên tách hàm tính priority khỏi nguồn thời gian:

~~~java
record PendingWork(
        String id,
        int basePriority,
        Instant originalEnqueuedAt) {}

static int effectivePriority(PendingWork work, Instant now) {
    long age = Math.max(0L,
            Duration.between(work.originalEnqueuedAt(), now).toSeconds());
    long bonus = age / 10L; // Mỗi 10 giây tăng 1 điểm.
    return (int) Math.min(100L, work.basePriority() + bonus);
}

static PendingWork selectAt(
        List<PendingWork> waiting, Instant now) {
    return waiting.stream()
            .min(Comparator
                    .<PendingWork>comparingInt(
                            w -> -effectivePriority(w, now))
                    .thenComparing(PendingWork::originalEnqueuedAt))
            .orElseThrow();
}
~~~

Test:

~~~java
@Test
void oldLowCanOvertakeNewHighByAgingPolicy() {
    Instant start = Instant.parse("2026-01-01T00:00:00Z");
    PendingWork oldLow = new PendingWork("LOW-1", 1, start);
    PendingWork newHigh = new PendingWork(
            "HIGH-1", 9, start.plusSeconds(90));

    PendingWork selected = selectAt(
            List.of(oldLow, newHigh), start.plusSeconds(100));

    assertEquals("LOW-1", selected.id());
}
~~~

Ở mốc 100 giây, LOW có effective priority 11; HIGH mới đến 10 giây có effective priority 10. **Đây là test thuật toán chọn tại thời điểm `now`**, chưa phải test một `PriorityChannel` dùng heap tự reorder. Heap không tự sắp lại mỗi giây chỉ vì comparator phụ thuộc đồng hồ. Nếu dùng persistent priority queue hoặc scheduled promotion, cần test **thao tác promote/reinsert/claim thực tế**.

### Deadline và SLO

Nếu định nghĩa “LOW chờ tối đa 60 giây”, kiểm thử phải kiểm tra *start processing time* hoặc *business commit time* theo định nghĩa SLO, không chỉ tính priority sau 60 giây. Khi tổng arrival rate lớn hơn capacity kéo dài, **không scheduler nào bảo đảm mọi deadline** nếu không có scaling, admission control hoặc degrade policy.

## 12. Kiểm thử nhiều producer/consumer và concurrency

Priority queue quyết định thứ tự lựa chọn message tại một điểm, còn **thứ tự hoàn tất** phụ thuộc worker/thread, thời gian xử lý và các resource bị chờ.

Ví dụ:

~~~text
Worker A: dequeues HIGH-1 -> xử lý 2 giây
Worker B: dequeues NORMAL-1 -> xử lý 20 ms

Thứ tự dequeue: HIGH-1 rồi NORMAL-1
Thứ tự completion: NORMAL-1 rồi HIGH-1
~~~

Vì vậy, test concurrency **không nên assert tất cả HIGH hoàn tất trước NORMAL** trừ khi chính kiến trúc áp đặt processing/commit order đó.

### Những invariant phù hợp hơn

- Mỗi business event ID được ghi nhận theo idempotency policy (nếu nguồn at-least-once, có thể nhận lặp nhưng **không double effect**).
- Không mất message đã được lưu bền vững và ACK đúng contract.
- Số message hoàn tất + pending + dead-letter + đang xử lý phản ánh được toàn bộ đầu vào theo mô hình trạng thái xác định.
- HIGH có queue-wait p95/p99 đáp ứng SLO khi tải nằm trong điều kiện kiểm thử.
- LOW có tiến triển và quota khi các queue liên tục có việc.
- Không có handler bị giữ vô hạn do lock/timeout hoặc poison message.

### Phối hợp test bằng latch thay vì sleep tùy ý

~~~java
CountDownLatch highEntered = new CountDownLatch(1);
CountDownLatch allowHighToFinish = new CountDownLatch(1);

// Trong fake handler HIGH:
highEntered.countDown();
if (!allowHighToFinish.await(2, TimeUnit.SECONDS)) {
    throw new AssertionError("Timeout waiting for test signal");
}

// Trong test:
assertTrue(highEntered.await(2, TimeUnit.SECONDS));
// Bây giờ kiểm tra message khác có được dequeue/xử lý
// theo chính sách concurrency của hệ thống.
allowHighToFinish.countDown();
~~~

Khi dùng latch, phải có timeout để CI không treo mãi. Dùng `try/finally` trong test để release latch ngay cả khi assertion lỗi. Đoạn trên minh họa cách điều khiển lịch thực thi, không tự suy rằng Spring Integration có sẵn worker pool với cấu hình nào.

## 13. Retry, redelivery, error channel và DLQ dưới nhiều mức ưu tiên

Một HIGH lỗi liên tục có thể bị redeliver hoặc retry, lấn át NORMAL/LOW. Vì thế kiểm thử priority phải bao gồm **đường lỗi**:

~~~mermaid
flowchart TD
    A["Nhận message HIGH/NORMAL/LOW"] --> B["Validate"]
    B --> C{"Message hợp lệ?"}
    C -->|"Không"| D["Quarantine / DLQ"]
    C -->|"Có"| E["Business handler"]
    E --> F{"Thành công?"}
    F -->|"Có"| G["Commit/ACK theo source"]
    F -->|"Lỗi tạm thời"| H["Bounded retry + backoff"]
    H --> I{"Còn retry budget?"}
    I -->|"Có"| E
    I -->|"Không"| D
~~~

### Test matrix đường lỗi

| Kịch bản | Điều cần quan sát |
| --- | --- |
| HIGH lỗi vĩnh viễn vì sai schema | Không retry vô hạn; DLQ lưu nguyên business event ID, priority gốc và lý do. |
| HIGH lỗi tạm thời hai lần rồi thành công | Số attempt đúng, không lặp side effect, không thay event ID. |
| NORMAL bị rollback và redeliver | Priority được khôi phục/validate đúng, không biến thành LOW/HIGH không chủ đích. |
| ErrorMessage được gửi đến `errorChannel` | Failed message gốc truy xuất đúng khi cần; error payload thường là exception, không phải business payload. |
| Retry loop HIGH trong một queue strict priority | LOW vẫn có tiến triển nếu fairness/retry budget là yêu cầu. |
| Handler catch exception rồi return | Source/poller có thể coi là thành công; test phải xác định ACK/rollback thật, không chỉ log lỗi. |
| DB commit thành công nhưng broker chưa ACK | Redelivery có thể xảy ra; consumer idempotent, không tăng side effect thêm. |
| Source ACK trước khi business commit rồi crash | Có nguy cơ mất công việc; test phải phát hiện hoặc chấp nhận rõ ràng. |

### Giữ metadata qua retry

~~~java
static Message<WorkEvent> retryCopy(
        Message<WorkEvent> failed, int nextAttempt) {
    int priority = PriorityContract.requirePriority(failed);
    String eventId = (String) failed.getHeaders()
            .get(PriorityContract.EVENT_ID);

    return MessageBuilder.withPayload(failed.getPayload())
            .setHeader(PriorityContract.PRIORITY, priority)
            .setHeader(PriorityContract.EVENT_ID, eventId)
            .setHeader("attempt", nextAttempt)
            .build();
}
~~~

Test:

~~~java
@Test
void retryKeepsBusinessEventIdAndPriority() {
    Message<WorkEvent> original =
            PriorityContract.message("E-17", WorkClass.HIGH);

    Message<WorkEvent> retried = retryCopy(original, 2);
    assertEquals(9, PriorityContract.requirePriority(retried));
    assertEquals("E-17",
            retried.getHeaders().get(PriorityContract.EVENT_ID));
    assertEquals(2, retried.getHeaders().get("attempt"));
}
~~~

Ví dụ này chỉ sao chép hai metadata cần thiết cho invariant đang kiểm thử. Trong flow thật, còn có `correlationId`, thời điểm enqueue đầu tiên, headers bảo mật và các thuộc tính adapter cần được đưa vào **allowlist có version**. Không copy tất cả header nội bộ qua broker/HTTP một cách vô điều kiện.

## 14. JMS, RabbitMQ và Kafka: kiểm thử đúng thứ mà nguồn hỗ trợ

### JMS

JMS có `JMSPriority` trong miền thông dụng 0..9; đây là một **thuộc tính JMS message**. Header `priority` của Spring message không tự chứng minh producer thật đã đặt `JMSPriority` đúng. Test:

1. Gửi message với priority HIGH và LOW qua outbound adapter thật.
2. Đọc thuộc tính `JMSPriority` của JMS message tại phía broker/consumer.
3. Đưa message inbound qua Spring Integration adapter và kiểm tra mapping về priority nội bộ.
4. Nếu cần test thứ tự, enqueue **cả hai trước khi consumer bắt đầu**; phân biệt broker ordering với consumer prefetch, concurrency và session transaction.

### RabbitMQ / AMQP

RabbitMQ dùng property `BasicProperties.priority`, và priority ordering cần queue/kiểu queue được cấu hình hỗ trợ priority (chẳng hạn classic priority queue với `x-max-priority` phù hợp).

Test:

- Outbound mapper tạo **property priority** thực tế, không chỉ application header string `priority`.
- Queue đã được khai báo đúng chính sách priority.
- Message HIGH/LOW chờ trong queue **trước** khi consumer lấy.
- Prefetch phù hợp để broker còn quyền chọn từ những message đang pending.
- Khi retry/NACK/requeue, metadata priority và event ID vẫn theo contract.

Nếu consumer đã prefetch LOW trước lúc HIGH đến, việc LOW hoàn tất trước HIGH **không chứng minh mapping priority sai**.

### Kafka

Kafka lưu record theo partition/offset. Custom header `priority` chỉ là metadata; **Kafka không tự sắp lại record trong partition theo số này**.

Test cần tách:

1. **Header propagation:** producer serialize priority thành bytes theo wire contract; consumer decode về `Integer` đúng policy.
2. **Partition ordering:** kiểm tra thứ tự offset/key khi nghiệp vụ yêu cầu.
3. **Application scheduling:** nếu cần HIGH được xử lý trước, test một scheduler/queue/consumer pool riêng; không viết test kỳ vọng Kafka ưu tiên record vì có header HIGH.
4. **Offset/transaction:** DB commit và Kafka offset commit có failure window; cần redelivery test và idempotent consumer.

| Kết quả kiểm thử | Có thể kết luận | Không thể kết luận |
| --- | --- | --- |
| `JMSPriority=9` ở message JMS | Mapper/JMS producer đã gán priority đúng. | Consumer chắc chắn hoàn tất trước mọi priority thấp. |
| AMQP property priority đúng và queue hỗ trợ | Broker có khả năng áp priority cho pending deliveries. | Message đang được xử lý có thể bị ngắt ngay lập tức. |
| Kafka header `priority=9` qua encode/decode | Metadata truyền đúng qua Kafka. | Kafka tự reorder offset theo priority. |
| `PriorityChannel` lấy 9 trước 1 | Local priority selection đúng với trạng thái queue test. | End-to-end fairness, durability hay exactly-once. |

## 15. Kiểm thử giao dịch và idempotency ở handler ưu tiên

Priority không thay thế transaction. Với consumer ghi DB, cần kiểm thử xử lý lặp trên business event ID ổn định.

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE work_effects (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_priority INTEGER NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Handler:

~~~java
@Service
class IdempotentWorkHandler {
    private final JdbcTemplate jdbc;

    IdempotentWorkHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void process(Message<WorkEvent> message) {
        int priority = PriorityContract.requirePriority(message);
        String eventId = (String) message.getHeaders()
                .get(PriorityContract.EVENT_ID);

        int inserted = jdbc.update("""
                INSERT INTO work_effects(event_id, processed_priority)
                VALUES (?, ?)
                ON CONFLICT (event_id) DO NOTHING
                """, eventId, priority);

        if (inserted == 0) {
            return; // Cùng event đã được commit từ delivery trước.
        }

        // Thực hiện side effect JDBC bổ sung ở đây,
        // trong CÙNG transaction với marker chống trùng.
    }
}
~~~

Integration test:

~~~java
@Test
void repeatedHighDeliveryProducesOnlyOneBusinessRow() {
    Message<WorkEvent> high =
            PriorityContract.message("E-200", WorkClass.HIGH);

    handler.process(high);
    handler.process(high); // Mô phỏng redelivery.

    Integer count = jdbc.queryForObject("""
            SELECT COUNT(*) FROM work_effects WHERE event_id = ?
            """, Integer.class, "E-200");

    assertEquals(1, count);
}
~~~

Đây chỉ chứng minh một invariant trên **database** nếu test dùng đúng Spring proxy/transaction manager và database phù hợp. Nó không chứng minh broker đã redeliver hoặc message store có durable ACK. Với thao tác HTTP/email, rollback DB không tự thu hồi side effect; cân nhắc transactional outbox/inbox và idempotency ở điểm tích hợp.

## 16. Load/stress test: nhiều priority cùng đến theo tỷ lệ khác nhau

Một unit test ordering nhỏ thường bỏ qua hiện tượng chỉ xuất hiện dưới tải: backlog dài, retry storm, prefetch, downstream lock và task có thời gian xử lý khác nhau.

### Kịch bản tải đề xuất

| Kịch bản | Phân phối input | Mục tiêu |
| --- | --- | --- |
| Cân bằng | HIGH:NORMAL:LOW = 1:1:1 | Ordering và progress cơ bản, không lớp nào bị thiếu bất thường. |
| HIGH áp đảo | 80:15:5 | NORMAL/LOW có tiến triển theo fairness policy; quan sát oldest age. |
| LOW backlog lớn | 10:20:70 | HIGH vẫn có độ trễ thấp, LOW không bị drop ngoài policy. |
| Tải bùng nổ | 100% HIGH trong 20 giây rồi quay về bình thường | Thời gian hồi phục và backlog theo class. |
| Retry storm | 10% HIGH luôn lỗi tạm thời | Retry budget, DLQ và tiến triển của message hợp lệ. |
| Payload nặng | HIGH xử lý lâu hơn LOW 10 lần | WRR theo số message có đủ đáp ứng SLO không? |
| Multi-tenant | Một tenant phát 90% HIGH | Tenant khác có quota/lượt xử lý tối thiểu. |
| Restart | Đang backlog rồi dừng/khởi động lại consumer | Durability, redelivery và business idempotency. |

### Các đại lượng cần đo

- `enqueued_total{class}`, `dequeued_total{class}`, `completed_total{class}`.
- `queue_depth{class}` và `oldest_pending_age_seconds{class}`.
- `queue_wait_seconds{class}` p50/p95/p99.
- `end_to_end_latency_seconds{class}` theo định nghĩa SLO.
- `retry_total{class,reason}`, `dead_letter_total{class}`.
- `duplicate_suppressed_total{class}`.
- `rejected_total{class}`, `worker_active{class}` và connection-pool saturation.

**Không dùng số message đã dequeue làm đại diện cho hoàn tất nghiệp vụ.** Completion có thể xảy ra chậm hơn, thất bại hoặc rollback; cần theo dõi những mốc riêng.

### Một cảnh báo toán học quan trọng

Nếu HIGH liên tục tiêu thụ toàn bộ năng lực xử lý của strict priority scheduler, LOW có thể starve. Nếu dùng WRR 4:2:1 nhưng tốc độ đến LOW lớn hơn năng lực dành cho **một phần bảy số lượt** trong thời gian dài, LOW vẫn có thể bị backlog tăng vô hạn, dù nó có tiến triển. Fairness theo lượt và **backlog ổn định** là hai tiêu chí khác nhau; test tải phải đo cả hai.

## 17. Quan sát lỗi test: vì sao test ưu tiên thường flaky?

| Anti-pattern | Tại sao flaky/sai | Cách thay thế |
| --- | --- | --- |
| Gửi LOW rồi HIGH khi consumer đã chạy và assert HIGH luôn nhận trước. | LOW có thể được dequeue trước khi HIGH đến. | Đóng cổng consumer; enqueue hết rồi mới poll. |
| Assert HIGH hoàn tất trước LOW với nhiều worker. | Dequeue order và completion order khác nhau. | Assert invariant/correlation và đo latency riêng. |
| Assert FIFO cho hai message cùng priority nhưng không có tie-breaker. | Comparator có thể coi chúng bằng nhau. | Assert đủ event ID hoặc cấu hình sequence comparator. |
| Test aging bằng `Thread.sleep` phút. | Test chậm, phụ thuộc scheduler OS/CI. | Inject `Clock` hoặc truyền `Instant` vào hàm chọn. |
| Dùng `PriorityChannel` RAM để kết luận crash/restart an toàn. | Queue RAM không durable. | Test broker/persistent store và ACK/transaction. |
| Chỉ mock adapter outbound mà không quan sát broker property. | Mapping wire chưa được kiểm chứng. | Broker integration test, kiểm tra JMS/AMQP property. |
| Giả định Kafka reorder theo priority header. | Kafka vẫn có offset/partition ordering. | Test record header riêng với application scheduler. |
| Dùng fixed delay làm điều kiện test “hoàn thành”. | CI có jitter và hệ thống tải khác nhau. | Latch, bounded await, condition-based assertion. |
| Dùng cùng queue/test data cho nhiều test song song. | Dữ liệu test tương tác, thứ tự không xác định. | Mỗi test có queue/ID/store group riêng. |
| Chỉ assert số attempt retry, bỏ qua business effect. | Có thể commit trùng dù attempt count đúng. | Unique event ID và assert trạng thái DB cuối. |

### Quy tắc tổ chức test

**Lớp 1 — Unit:** test comparator, policy, scheduler, aggregatePriority; thuần JVM, không cần Spring context.

**Lớp 2 — Spring Integration test:** test Header Enricher/Transformer, route, Gateway, channel dispatch, poller boundary bằng các bean và channel đã cấu hình. Tránh poller tự chạy khi đang kiểm tra thứ tự queue một cách deterministic.

**Lớp 3 — Broker/store test:** chạy trên broker hoặc persistent store thật (có thể dùng Testcontainers nếu dự án đã dùng). Kiểm tra wire mapping, ACK, redelivery, restart và transaction.

**Lớp 4 — Load/failure injection:** đo latency, fairness, retry, chaos/crash và các ranh giới concurrency dưới điều kiện kiểm soát.

Không đưa tất cả bài kiểm tra broker dài vào mỗi lần sửa nhỏ nếu CI cần nhanh; có thể phân nhóm test theo mức độ chi phí, nhưng vẫn phải chạy lớp broker/failure trước release.

## 18. Debug khi nhiều mức ưu tiên không đúng kỳ vọng

Nếu HIGH chờ sau LOW, hãy điều tra **theo đường đi của event ID**:

~~~text
1. Producer có gán business priority đúng policy không?
2. Header tại ingress đúng tên/kiểu/giá trị Integer chưa?
3. Transformer có tạo Message mới hoặc ghi đè header không?
4. Router chọn đúng nhánh priority-aware chưa?
5. Splitter/Aggregator có tính priority output rõ ràng không?
6. Queue thực sự là PriorityChannel hay QueueChannel FIFO?
7. Comparator có chiều so sánh đúng, có tie-breaker không?
8. HIGH đã nằm trong queue trước lần dequeue LOW chưa?
9. Một worker đã giữ LOW trong lúc HIGH đến phải không?
10. JMS/AMQP property có map đúng và queue hỗ trợ không?
11. Kafka chỉ mang priority header hay có scheduler riêng?
12. Có retry storm, starvation, backpressure, prefetch hoặc DB lock không?
13. Số liệu đang nhìn là dequeue order hay completion order?
14. Priority gốc/effective có thay đổi do aging/tenant quota không?
~~~

Việc theo dõi `priority_assigned`, `priority_enqueued`, `priority_dequeued` và `priority_processed` riêng biệt giúp biết metadata bị mất ở đâu, và tránh đổ lỗi cho channel khi nguyên nhân là worker hoặc downstream.

## 19. Bài tập và câu hỏi phỏng vấn

### Bài tập 1 — Test từ hai mức lên ba mức

Viết thêm `PriorityChannelOrderingTest` có ít nhất ba message mỗi lớp, enqueue ngẫu nhiên rồi kiểm tra **dãy priority được dequeue không tăng** (theo HIGH=9, NORMAL=5, LOW=1), đồng thời bảo toàn tập event ID. Không assert thứ tự các message bằng priority nếu chưa có tie-breaker.

### Bài tập 2 — Comparator cho cùng mức ưu tiên

Gắn header `enqueueSequence` cho mọi message. Viết comparator priority giảm dần, sequence tăng dần. Kiểm thử HIGH cùng priority nhưng được gửi thứ tự ngược với sequence, rồi giải thích vì sao sequence cấp phát tại nhiều instance là vấn đề phân tán.

### Bài tập 3 — Pipeline qua EIP

Tạo Gateway → Transformer → Router → Filter → PriorityChannel → Service Activator. Mỗi mức HIGH/NORMAL/LOW có event ID riêng. Test input, output của từng endpoint và dữ liệu cuối; cố tình tạo một Transformer làm mất header để test phát hiện lỗi.

### Bài tập 4 — Splitter và Aggregator

Chia một đơn hàng thành các item priority 9, 5, 1. Dùng aggregator policy MAX. Test ba thứ tự đến khác nhau, duplicate và timeout release; giải thích kết quả khi item HIGH đến muộn.

### Bài tập 5 — Chống starvation

So sánh strict `PriorityChannel` với scheduler WRR 4:2:1 dưới HIGH liên tục. Chứng minh LOW không tiến triển trong một chuỗi poll strict priority, nhưng có ít nhất một lượt mỗi chu kỳ WRR khi queue LOW luôn backlog.

### Bài tập 6 — Aging không dùng đồng hồ thực

Viết test có `Instant` giả cho LOW chờ 100 giây và HIGH chờ 10 giây. Dùng hàm effective priority với bước 10 giây, rồi tích hợp thành promotion job thực tế; kiểm tra message được **requeue/claim** đúng thay vì chỉ tính toán một con số.

### Bài tập 7 — Retry và DLQ

HIGH lỗi ba lần trước khi thành công, NORMAL thành công, LOW lỗi vĩnh viễn. Đo attempt count, event ID, độ trễ và trạng thái DLQ. Đảm bảo retry không tự tăng mức ưu tiên vô hạn.

### Bài tập 8 — Từ local sang broker

Chuyển ví dụ sang JMS hoặc RabbitMQ. Đọc **property priority thật** của message, test prefetch và retry. Nếu dùng Kafka, chứng minh header được truyền đúng nhưng offset order không đổi.

### Bài tập 9 — Test idempotency khi crash

Consumer nhận HIGH, ghi DB commit rồi sập trước ACK. Sau khi redeliver cùng event ID, kiểm tra business effect chỉ có một lần; nêu rõ dữ liệu thuộc transaction nào.

### Câu hỏi tự đánh giá

**1. Vì sao test “send LOW rồi HIGH” có thể thất bại dù PriorityChannel đúng?** Vì consumer có thể đã lấy LOW trước khi HIGH được enqueue. Phải khống chế thời điểm poll.

**2. Có nên test FIFO mặc định giữa hai message priority=9 không?** Không, trừ khi cấu hình/contract nêu rõ tie-breaking.

**3. WRR 4:2:1 chứng minh điều gì?** Phân bổ suất chọn giữa ba queue trong điều kiện tất cả backlog và scheduler tiến triển; không tự chứng minh thời hạn xử lý tính theo giây.

**4. Tại sao cần fake clock khi kiểm thử aging?** Để kiểm tra các mốc thời gian một cách nhanh, lặp lại và không phụ thuộc độ trễ của CI.

**5. Kafka record có priority header 9 sẽ được đọc trước record offset thấp hơn không?** Không. Kafka không dùng custom priority header để reorder trong một partition.

**6. Vì sao phải test DB state ngoài thứ tự dequeue?** Một message có thể được nhận và xử lý lại sau rollback/ACK lỗi; chỉ dữ liệu commit thực tế mới chứng minh side effect đúng.

## 20. Checklist trước khi kết luận kiểm thử đạt

- [ ] Đã công bố contract HIGH/NORMAL/LOW, miền giá trị, kiểu header và nguồn tin cậy.
- [ ] Test queue ordering có **tất cả message sẵn trước khi poll** và chỉ một consumer khi xác minh thứ tự.
- [ ] Test đủ ba mức, nhiều message, cùng mức, thiếu/sai kiểu và priority ngoài miền.
- [ ] Không assert FIFO cho cùng mức nếu không có comparator tie-breaker.
- [ ] Kiểm tra không mất/duplicate message theo `businessEventId`, không chỉ thứ tự giá trị priority.
- [ ] Có test Transformer/Router/Filter, Gateway, Splitter/Aggregator cho header priority và correlation.
- [ ] Phân biệt ordering của `PriorityChannel` với execution của `DirectChannel` và `ExecutorChannel`.
- [ ] Nếu cần fairness, có test HIGH liên tục và quota cho NORMAL/LOW.
- [ ] Nếu dùng aging, có fake clock và xác minh scheduler/store thực sự đánh giá lại thứ tự.
- [ ] Có test khi queue rỗng, queue đầy, backpressure và worker chậm.
- [ ] Có retry hữu hạn, backoff, DLQ và kiểm tra priority/event ID qua error path.
- [ ] Có test concurrency với invariant thích hợp; không nhầm dequeue order với completion order.
- [ ] Có test broker thực tế cho JMS/AMQP property hoặc Kafka header encode/decode.
- [ ] Với nghiệp vụ quan trọng, có integration test transaction/ACK/redelivery và idempotency.
- [ ] CI dùng queue/ID cô lập, latch/timeouts hữu hạn và không dựa vào sleep tùy ý.
- [ ] Theo dõi oldest queue age, p95/p99 wait, class progress, retry và deadline misses dưới tải.
- [ ] Phân biệt fairness theo lượt, backlog ổn định và SLO latency; có phương án capacity khi tổng tải quá cao.

**Ghi nhớ:** **Kiểm thử priority đúng phải kiểm tra cả *giá trị metadata*, *thứ tự chọn message*, *tiến triển của các mức ưu tiên*, và *kết quả nghiệp vụ khi có lỗi*.** `PriorityChannel` giải quyết ordering cục bộ của message còn chờ; hệ thống Spring Integration nhiều Router, Transformer, Splitter, Aggregator, Gateway và broker cần thêm hợp đồng header, fairness, transaction, retry và quan sát end-to-end. Một test thành công ở queue đơn lẻ không thay thế được kiểm thử cả luồng.

### Tài liệu đọc thêm

- Spring Integration Reference: Message Channel Implementations, Message Channels và PriorityChannel.
- Spring Integration Reference: Transformer, Router, Filter, Splitter, Aggregator và Gateway.
- Spring Integration Reference: Error Handling, Transaction Support và Polling Consumer.
- Tài liệu của broker đang sử dụng: JMS message priority, RabbitMQ Priority Queues hoặc Kafka partition/offset/header semantics.

*Các đoạn Java minh họa các phần kiểm thử và phải được đặt vào fixture/class phù hợp. Trước khi sử dụng ở dự án, cần kiểm tra API với phiên bản Spring Integration và broker thực tế; chưa thay thế vòng Content QA chuyên môn hoặc test trên môi trường triển khai.*
