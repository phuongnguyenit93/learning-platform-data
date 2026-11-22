# Kiểm thử channel đầy và send timeout trong Spring Integration

## 1. Bối cảnh: producer nhanh hơn consumer

Trong một luồng Spring Integration, producer có thể tạo message nhanh hơn consumer xử lý. Ví dụ một API nhận 1.000 yêu cầu mỗi giây, nhưng dịch vụ xuất hóa đơn chỉ xử lý được 100 yêu cầu mỗi giây. Nếu dùng hàng đợi trong bộ nhớ không giới hạn, backlog tăng và có thể gây thiếu bộ nhớ. Nếu dùng hàng đợi có giới hạn, sẽ có lúc channel **đầy** và producer phải chờ, thất bại có kiểm soát, hoặc chọn đường dự phòng.

Giả sử `QueueChannel` có sức chứa **1 message**:

~~~text
Queue capacity = 1

Producer gửi A -> queue: [A] -> send(A, 0) = true
Producer gửi B -> queue: [A] -> send(B, 0) = false
Consumer nhận A -> queue: []
Producer gửi B -> queue: [B] -> send(B, timeout) = true
~~~

Trong module **SPRING_INTEGRATION_PATTERN**, kiểm thử tình huống này giúp thiết kế Enterprise Integration Patterns với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation. Mục tiêu là chứng minh các điểm **backpressure**, **timeout**, **không mất message một cách âm thầm**, và **không nhầm timeout của channel với timeout nghiệp vụ**.

### Mục tiêu học tập

1. Phân biệt `QueueChannel` có dung lượng giới hạn với channel không đệm hoặc đệm ở nơi khác.
2. Kiểm tra `send(message, timeout)` thành công hay trả `false` khi channel đầy.
3. Kiểm thử một producer đang chờ có thể hoàn thành khi consumer lấy bớt message, **không dùng `Thread.sleep(...)` tùy ý**.
4. Hiểu ranh giới của send timeout với lỗi downstream, retry, Gateway timeout và error channel.
5. Thiết kế test bảo đảm cô lập, dọn tài nguyên, không phụ thuộc tốc độ máy CI.

> **Nguyên tắc:** `send(...) == true` có nghĩa channel đã nhận message theo hợp đồng của chính nó. Điều đó **không chứng minh** consumer đã xử lý xong, broker đã ACK, hoặc transaction nghiệp vụ đã commit.

## 2. Hợp đồng `MessageChannel.send(...)`

Spring Messaging định nghĩa hai dạng gửi message chính:

~~~java
boolean send(Message<?> message);
boolean send(Message<?> message, long timeout);
~~~

Đối với **bounded `QueueChannel`**, `timeout` được hiểu bằng **mili giây**:

| Lời gọi | Ý nghĩa khi hàng đợi đầy | Kết quả cần kiểm tra |
| --- | --- | --- |
| `send(message, 0)` | Thử gửi ngay, không chờ chỗ trống | Thường trả `false` nếu queue đã đầy |
| `send(message, 200)` | Có thể đợi tối đa khoảng 200 ms để có chỗ | Trả `true` nếu gửi được, `false` khi hết thời gian |
| `send(message)` | Dùng chính sách timeout mặc định của channel | Không nên dùng trong test có nguy cơ chờ vô hạn |
| `send(message, -1)` | Với cơ chế queue hỗ trợ, biểu thị đợi không giới hạn | Chỉ dùng nếu có consumer/lifecycle bảo đảm giải phóng |

Con số timeout quy định thời gian **đợi nhận vào channel**, không phải thời gian cho phép consumer xử lý. Một message có thể được đưa vào queue thành công và nằm ở đó rất lâu.

**Không áp dụng kết luận trên cho mọi `MessageChannel`:** một `DirectChannel` không có hàng đợi hữu hạn để chờ slot; `ExecutorChannel` phụ thuộc executor và chính sách từ chối tác vụ; broker adapter có cơ chế ACK/buffer khác. Bài test channel đầy phải sử dụng đúng loại channel và capacity mà yêu cầu muốn kiểm chứng.

### Trả `false` không giống ném exception

`MessageChannel.send(...)` trả `boolean` theo hợp đồng của channel. Với queue đầy và timeout hết, `QueueChannel` có thể trả **`false`**. Nhưng lỗi khác, chẳng hạn downstream handler ném exception trên `DirectChannel` hoặc adapter thất bại, có thể biểu hiện bằng **exception**.

Một sender không được bỏ qua kết quả:

~~~java
boolean accepted = channel.send(message, 250L);
if (!accepted) {
    // Đây là thất bại khi bàn giao message vào channel.
    // Chọn chính sách: trả lỗi, ghi outbox, retry có giới hạn,
    // hoặc đưa sang một hàng đợi khác có bảo đảm.
}
~~~

Nếu chỉ gọi `channel.send(message, 0)` rồi không kiểm tra `boolean`, message không được nhận khi channel đầy có thể biến mất khỏi luồng nghiệp vụ mà không để lại dấu vết đáng tin cậy.

## 3. Phân biệt channel đầy với consumer đang bận

~~~mermaid
flowchart LR
    A[Producer] --> B{"QueueChannel<br/>capacity = 2"}
    B --> C["Buffered: A, B"]
    C --> D[Poller / Consumer]
    D --> E[Handler / External API]
    B -->|Queue đầy| F["send timeout / false"]
    F --> G[Retry / Reject / Durable fallback]
~~~

Capacity của queue chủ yếu giới hạn **số message đang chờ trong buffer**, không trực tiếp giới hạn số message đã được consumer lấy ra và đang xử lý.

Ví dụ:

- Queue capacity = 2.
- Một consumer đã lấy message A và đang gọi REST API trong 10 giây.
- Buffer vẫn có thể chứa B và C.
- Producer gửi D lúc này mới có thể bị từ chối hoặc phải đợi.

Vì thế muốn kiểm thử **tổng số công việc đang bay (in-flight)**, không đủ chỉ quan sát queue size: cần thêm probe ở handler, concurrency limit hoặc một bulkhead ở tầng consumer.

### Một `QueueChannel` trống không nói lên điều gì?

`QueueChannel.receive(0) == null` chỉ chứng minh tại thời điểm poll không có message sẵn sàng trong queue. Nó không chứng minh:

- Handler không đang xử lý một message đã lấy ra.
- Không có message đang được relay/adapter giữ ở bước sau.
- Scheduler không chuẩn bị phát một message từ Delayer.
- Không có message đến muộn sau lần poll.

Khi test luồng bất đồng bộ, hãy xác định **điểm quan sát phù hợp** với câu hỏi cần trả lời.

## 4. Ví dụ cơ bản: bounded `QueueChannel` dung lượng 1

Kiểm thử channel trực tiếp là phương pháp tốt nhất để chứng minh hành vi capacity, không cần thêm IntegrationFlow hoặc poller có thể vô tình làm queue rỗng.

### 4.1. Tạo message có định danh nghiệp vụ

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class Messages {
    private Messages() {
    }

    public static Message<String> event(String payload, String eventId) {
        return MessageBuilder.withPayload(payload)
                .setHeader("eventId", eventId)
                .setHeader("correlationId", "order-501")
                .build();
    }
}
~~~

`eventId` giúp kiểm tra message nào thực sự vào queue. `MessageHeaders.ID` do framework tạo không nên là định danh duy nhất của một thao tác nghiệp vụ khi cần retry/replay qua nhiều message instance.

### 4.2. Kiểm thử channel đầy và gửi không chờ

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class BoundedQueueSendTest {

    @Test
    void returnsFalseImmediatelyWhenQueueIsFull() {
        QueueChannel queue = new QueueChannel(1);

        assertTrue(queue.send(Messages.event("A", "event-A"), 0));
        assertFalse(queue.send(Messages.event("B", "event-B"), 0),
                "Queue capacity=1 đã chứa A");

        Message<?> received = queue.receive(0);
        assertNotNull(received);
        assertEquals("A", received.getPayload());
        assertEquals("event-A", received.getHeaders().get("eventId"));

        assertNull(queue.receive(0),
                "Message B không được nhận khi send() trả false");
    }
}
~~~

**Giải thích:**

1. `new QueueChannel(1)` tạo channel có bộ đệm tối đa một message.
2. Lần gửi `A` được chấp nhận.
3. Lần gửi `B` trả `false` vì không có chỗ và `timeout=0`.
4. `receive(0)` lấy `A` ra khỏi queue.
5. Sau khi nhận `A`, queue trống; `B` không tự nằm trong queue và cũng không được framework tự thử lại.

Kiểm thử này không cần sleep, executor hay Spring context. Nó chứng minh rõ hợp đồng channel, không trộn với chính sách của consumer.

### 4.3. Kiểm thử timeout dương khi vẫn không có consumer

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class BoundedQueueTimeoutTest {

    @Test
    @Timeout(5)
    void returnsFalseAfterBoundedWaitAndPreservesFirstMessage() {
        QueueChannel queue = new QueueChannel(1);

        assertTrue(queue.send(Messages.event("A", "event-A"), 0));
        assertFalse(queue.send(Messages.event("B", "event-B"), 100),
                "Không có consumer giải phóng slot trong thời hạn");

        Message<?> onlyMessage = queue.receive(0);
        assertNotNull(onlyMessage);
        assertEquals("A", onlyMessage.getPayload());
        assertNull(queue.receive(0));
    }
}
~~~

Hành vi cần xác nhận là **`false` và A còn nguyên**, không phải đòi lời gọi kết thúc chính xác ở mili giây thứ 100. `@Timeout(5)` là hàng rào để bài test không treo do thay đổi ngoài ý muốn.

Trên máy CI, tính thời gian chờ có thể sai lệch vài chục mili giây do scheduler. Tránh `assertEquals(100, elapsedMillis)` vì đây không phải SLA thời gian thực.

## 5. Kiểm thử producer đang chờ được giải phóng khi consumer nhận message

Muốn chứng minh `send(message, timeout)` có thể **đợi slot** rồi thành công, cần điều phối hai thread:

1. Thread chính lấp đầy queue bằng `A`.
2. Thread phụ bắt đầu gửi `B` với timeout đủ rộng.
3. Test xác nhận `B` chưa thể hoàn thành khi queue vẫn đầy.
4. Test lấy `A` ra.
5. Sender đang đợi có slot trống, gửi `B` và trả `true`.

Sử dụng `CountDownLatch`, `Future` và `get(timeout)` thay cho `Thread.sleep`.

~~~mermaid
sequenceDiagram
    participant T as Test thread
    participant Q as QueueChannel capacity=1
    participant W as Sender thread
    T->>Q: send(A, 0) = true
    T->>W: Submit send(B, 5000)
    W-->>T: started.countDown()
    W->>Q: send(B, 5000) đang chờ slot
    T->>T: Future.get(100ms) -> TimeoutException
    T->>Q: receive(0) -> A
    Q-->>W: Slot được giải phóng
    W->>Q: B được đưa vào queue
    W-->>T: Future trả true
    T->>Q: receive(0) -> B
~~~

### Ví dụ JUnit có dọn thread bằng `finally`

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class BlockingQueueSendTest {

    @Test
    @Timeout(10)
    void blockedSendSucceedsWhenConsumerFreesCapacity() throws Exception {
        QueueChannel queue = new QueueChannel(1);
        assertTrue(queue.send(Messages.event("A", "event-A"), 0));

        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch senderStarted = new CountDownLatch(1);

        Future<Boolean> pending = executor.submit(() -> {
            senderStarted.countDown();
            return queue.send(Messages.event("B", "event-B"), 5_000);
        });

        try {
            assertTrue(senderStarted.await(2, TimeUnit.SECONDS),
                    "Sender chưa bắt đầu công việc");

            // Đây là kiểm tra bounded waiting trên Future, không sleep.
            // Khi queue vẫn đầy, sender không thể chấp nhận B.
            assertThrows(TimeoutException.class,
                    () -> pending.get(100, TimeUnit.MILLISECONDS));

            Message<?> first = queue.receive(0);
            assertNotNull(first);
            assertEquals("A", first.getPayload());

            assertTrue(pending.get(3, TimeUnit.SECONDS),
                    "Sender cần hoàn thành khi có slot");

            Message<?> second = queue.receive(0);
            assertNotNull(second);
            assertEquals("B", second.getPayload());
            assertEquals("event-B", second.getHeaders().get("eventId"));
            assertNull(queue.receive(0));
        } finally {
            pending.cancel(true);
            executor.shutdownNow();
        }
    }
}
~~~

**Vì sao ví dụ này không dùng sleep tùy ý?** Test không chờ “100 ms để hy vọng worker đã bắt đầu”. Nó dùng latch để biết worker đã chạy đến đoạn gửi, và dùng `Future.get(timeout)` làm một khẳng định về **hợp đồng bị chặn khi queue đầy**. Sau khi consumer lấy `A`, `Future` là tín hiệu sender thực sự gửi xong `B`.

Lưu ý: `senderStarted.countDown()` xảy ra **ngay trước** lời gọi `send`. Về mặt lập lịch, test không xác nhận chính xác CPU đã vào nội bộ `send` trước dòng `Future.get`, nhưng do queue vẫn đầy nên một lời gọi `send` đúng không thể hoàn tất thành công trong trạng thái đó. `get(timeout)` giúp phát hiện lỗi kết thúc sai mà không đoán thời gian producer/consumer.

Nếu test thất bại sớm, `finally` ngắt sender đang chờ và shutdown executor để tránh treo bộ kiểm thử. Trong production, interrupt/cancellation và retry phải có chính sách riêng, không được mặc nhiên coi task bị hủy là message đã được xử lý.

## 6. Kiểm thử một slot được giải phóng và thứ tự FIFO

`QueueChannel` mặc định lưu message theo thứ tự hàng đợi. Trong một test đơn luồng và chỉ có một producer, có thể kiểm tra:

~~~java
QueueChannel queue = new QueueChannel(2);

assertTrue(queue.send(Messages.event("A", "event-A"), 0));
assertTrue(queue.send(Messages.event("B", "event-B"), 0));
assertFalse(queue.send(Messages.event("C", "event-C"), 0));

assertEquals("A", queue.receive(0).getPayload());
assertTrue(queue.send(Messages.event("C", "event-C"), 0));
assertEquals("B", queue.receive(0).getPayload());
assertEquals("C", queue.receive(0).getPayload());
assertNull(queue.receive(0));
~~~

Điều này kiểm tra **FIFO ở buffer** khi cùng một producer và không có các bước phân nhánh/sắp xếp lại. Không suy rộng thành “mọi tác động downstream đều hoàn thành theo thứ tự FIFO” nếu có nhiều consumer, executor hoặc retry.

### Test đồng thời cần kiểm tra identity thay vì đoán thứ tự

Với nhiều producer/consumer chạy song song, hai message có thể tới queue theo thứ tự phụ thuộc scheduling. Khi ứng dụng không yêu cầu thứ tự nghiêm ngặt, nên so sánh **tập `eventId` nhận được** và bảo đảm không thiếu/trùng, thay vì bắt buộc so sánh một danh sách theo thứ tự gửi dự đoán.

## 7. Tích hợp bounded channel vào Spring Integration

Một bounded channel cũng có thể được tạo thành bean của Spring:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class BoundedChannelConfig {

    @Bean("orders.bounded")
    public PollableChannel boundedOrders() {
        return new QueueChannel(1);
    }
}
~~~

Producer nhận bean này và gửi trực tiếp với timeout:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@Component
public class OrderQueuePublisher {

    private final MessageChannel queue;

    public OrderQueuePublisher(
            @Qualifier("orders.bounded") MessageChannel queue) {
        this.queue = queue;
    }

    public boolean enqueue(String eventId, String orderId) {
        return queue.send(MessageBuilder.withPayload(orderId)
                .setHeader("eventId", eventId)
                .build(), 250L);
    }
}
~~~

`send(..., 250L)` ở đây được gọi **trực tiếp lên bounded queue**, nên test có thể dự đoán rõ vì sao kết quả là `false`. Nếu producer gửi vào một `DirectChannel` nằm **trước** queue, thời gian chờ có thể thuộc về bridge/handler chuyển tiếp, không nhất thiết dùng lại `timeout` mà producer đã truyền vào `DirectChannel`.

### Minh họa đường đi qua một IntegrationFlow

~~~mermaid
flowchart LR
    A[API / Gateway] --> B[DirectChannel orders.in]
    B --> C[Bridge / Router / Transformer]
    C --> D["QueueChannel orders.bounded<br/>capacity=1"]
    D --> E[Poller]
    E --> F[Consumer]
~~~

Với flow này, phải đặt timeout tại **endpoint đang gửi vào `orders.bounded`**, hoặc dùng chính sách riêng của publisher/bridge ở điểm đó. Không lấy `send(message, 100)` trên `orders.in` làm bằng chứng rằng toàn bộ các bước phía sau chỉ được chờ 100 ms.

Một số endpoint có thuộc tính `sendTimeout` riêng khi gửi output, một số thành phần điều phối theo thread khác. Cần xem đúng cấu hình endpoint và version đang dùng để biết exception, kết quả gửi và error channel xuất hiện ở đâu.

### Vì sao test direct channel đơn giản thường tốt hơn?

Khi muốn chứng minh **capacity và send timeout**, giữ test ở `QueueChannel` với **không có consumer chạy song song** giúp cô lập đúng hợp đồng. Sau đó mới viết integration test có poller/handler để kiểm chứng chính sách toàn flow. Trộn poller vào test capacity có thể khiến consumer lấy message quá nhanh, làm queue không còn đầy tại thời điểm assert.

## 8. `QueueChannel`, `DirectChannel`, `ExecutorChannel` và `RendezvousChannel`

| Channel | Đặc tính chính | Vấn đề khi quá tải |
| --- | --- | --- |
| `QueueChannel(capacity)` | Có buffer, consumer poll | Buffer đầy; `send(..., timeout)` có thể đợi slot rồi trả `false` |
| `DirectChannel` | Dispatcher gọi subscriber trong thread sender | Handler chậm hoặc exception ảnh hưởng trực tiếp producer; không có buffer để kiểm tra “queue đầy” |
| `ExecutorChannel` | Bàn giao tới executor/thread khác | Pool/queue của executor có thể từ chối task; không mặc nhiên giống `QueueChannel` trả `false` |
| `RendezvousChannel` | Handoff trực tiếp, không có buffer lưu message | Producer có thể phải chờ consumer sẵn sàng nhận; timeout là timeout handoff |
| `PublishSubscribeChannel` | Phát tới subscriber theo cấu hình | Hành vi khi subscriber chậm/lỗi phụ thuộc đồng bộ, executor và error handler |

Nếu muốn test **RendezvousChannel**, phải tạo một consumer thực sự chờ nhận để producer giao message thành công. Không nên coi `RendezvousChannel` là một `QueueChannel(0)` có thể lưu message sau khi sender trả về.

### Một ví dụ handoff cơ bản

~~~java
import org.springframework.integration.channel.RendezvousChannel;

RendezvousChannel channel = new RendezvousChannel();

// Nếu không có receiver sẵn sàng:
boolean delivered = channel.send(Messages.event("A", "event-A"), 0);
// delivered có thể false: không có buffer để chứa A.
~~~

Đây là minh họa điều kiện receiver chưa sẵn sàng; muốn kiểm tra thành công cần một thread `receive(timeout)` đang chờ, được điều phối bằng latch/future.

## 9. Khi queue đầy, chọn chính sách xử lý nào?

Trả `false` chỉ là **tín hiệu**. Ứng dụng phải quyết định nghiệp vụ sẽ làm gì tiếp:

~~~mermaid
flowchart TD
    P[Producer gửi message với timeout] --> A{send trả true?}
    A -->|Có| B[Đã bàn giao vào channel]
    A -->|Không| C{Message quan trọng?}
    C -->|Có| D[Durable outbox / broker / báo lỗi nguồn]
    C -->|Không| E[Drop có chủ đích + metric]
    D --> F[Retry có giới hạn và backoff]
    E --> G[Ack theo hợp đồng đã định]
    B --> H[Consumer xử lý riêng]
~~~

| Chính sách | Phù hợp khi | Rủi ro cần quản lý |
| --- | --- | --- |
| Trả lỗi/HTTP 429 hoặc 503 | Caller có thể gửi lại có idempotency key | Retry storm nếu quá nhiều client cùng thử |
| Retry ngắn có giới hạn | Tắc nghẽn tạm, message nhỏ | Giữ thread nếu dùng backoff blocking |
| Lưu outbox/queue bền vững | Message không được mất khi overload/restart | Cần relay, retry, monitoring và dedupe |
| Dead-letter/quarantine | Có lỗi dữ liệu hoặc đã hết retry | Cần lưu dữ liệu lỗi và replay có kiểm soát |
| Drop có ghi nhận | Dữ liệu có thể bỏ (ví dụ một số telemetry) | Phải có policy rõ ràng, không áp dụng cho nghiệp vụ quan trọng |
| Rate limiter/bulkhead | Giảm tải đầu vào và kiểm soát concurrency | Không thay lưu trữ bền vững |

Với đơn hàng/thanh toán, không nên “`send == false` thì ghi log rồi return success” nếu yêu cầu phải xử lý đủ mọi sự kiện. Một phương án đáng tin cậy hơn có thể là đưa message vào outbox trong cùng transaction business, rồi relay sang broker/transport có retry và idempotency.

### Wrapper chuyển `false` thành lỗi có nghĩa

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageDeliveryException;

public final class FailFastPublisher {
    private final MessageChannel destination;

    public FailFastPublisher(MessageChannel destination) {
        this.destination = destination;
    }

    public void publish(Message<?> message) {
        if (!destination.send(message, 250)) {
            throw new MessageDeliveryException(
                    message, "Destination channel full after 250 ms");
        }
    }
}
~~~

Lớp này **chủ động** ném exception khi kênh không nhận. Spring Integration không tự suy ra chính sách nghiệp vụ từ giá trị `false` của một lời gọi `send` trực tiếp trong code ứng dụng.

## 10. Kiểm thử publisher không “thành công giả”

Một bài test nên chứng minh khi queue đầy, publisher báo lỗi thay vì lặng lẽ bỏ message:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessageDeliveryException;

import static org.junit.jupiter.api.Assertions.*;

class FailFastPublisherTest {

    @Test
    void throwsOnFullQueueWithoutDroppingAlreadyQueuedEvent() {
        QueueChannel queue = new QueueChannel(1);
        FailFastPublisher publisher = new FailFastPublisher(queue);

        publisher.publish(Messages.event("A", "event-A"));

        assertThrows(MessageDeliveryException.class,
                () -> publisher.publish(Messages.event("B", "event-B")));

        assertEquals("A", queue.receive(0).getPayload());
        assertNull(queue.receive(0));
    }
}
~~~

Chú ý wrapper cố ý dùng `250 ms`; test có thể phải đợi hết khoảng này rồi mới nhận exception. Không cần thêm `Thread.sleep`: lời gọi `publish` chỉ kết thúc khi đã có kết quả gửi hoặc đã hết timeout.

**Điểm cần kiểm tra riêng:** nếu producer thấy exception rồi retry `B`, phải bảo đảm nó **không tạo hai side effect nghiệp vụ** khi một lần gửi trước đó có kết quả không chắc chắn. Với bounded queue thuần túy, `send == false` cho biết message không được nhận vào queue; nhưng ở bước broker/adapter, timeout mạng có thể không đủ để kết luận phía nhận chưa xử lý.

## 11. Send timeout và các timeout khác trong EIP

| Timeout | Đối tượng đang chờ | Kết luận đúng |
| --- | --- | --- |
| `QueueChannel.send(message, 200)` | Producer chờ slot trong buffer | Hết hạn có thể `false`; chưa bao gồm xử lý consumer |
| `QueueChannel.receive(200)` | Consumer chờ message sẵn sàng | Hết hạn trả `null`; producer không nhất thiết đã thất bại |
| Gateway `requestTimeout` | Gateway chờ gửi request theo cấu hình | Không đồng nghĩa reply business sẽ đến |
| Gateway `replyTimeout` | Caller chờ reply | Caller timeout có thể xảy ra trước khi downstream hoàn tất |
| HTTP connect/read timeout | Handler chờ kết nối/phản hồi dịch vụ | Kết quả side effect có thể chưa rõ, cần idempotency |
| Delayer `defaultDelay` | Message được giữ trước khi phát | Delay kết thúc không bảo đảm consumer thành công |
| Retry `backoff` | Thành phần xử lý lỗi chờ trước lần thử tiếp | Là một phần retry budget, không tự là send timeout |

**Ví dụ:** Gateway gửi yêu cầu tới một flow có queue capacity=1. Nếu Gateway hết `requestTimeout` khi không thể đưa message vào queue, vấn đề là **bàn giao đầu vào**. Nếu đã đưa vào queue nhưng hết `replyTimeout` khi consumer xử lý chậm, vấn đề là **không có phản hồi trong thời hạn chờ**. Hai tình huống cần assert và xử lý khác nhau.

### Không giả định timeout tự hủy message

Một Gateway caller thôi chờ không nhất thiết hủy message đã vào queue. Message còn có thể được consumer lấy và xử lý sau đó. Khi bài test xác minh trường hợp timeout, hãy dùng `eventId` và probe ở downstream để quan sát liệu tác động nghiệp vụ có diễn ra không.

## 12. Retry và error channel khi queue không nhận

Nếu gọi `send(...)` trực tiếp và nhận `false`, ứng dụng có thể chuyển thành exception hoặc một event thất bại để xử lý. Trong một IntegrationFlow, việc gửi lỗi sang `errorChannel` phụ thuộc loại endpoint, ranh giới thread và error publisher được cấu hình.

~~~mermaid
flowchart LR
    A[Producer] --> B["Bounded QueueChannel"]
    B -->|accepted| C[Consumer]
    B -->|timeout / false| D[Publisher handles failure]
    D --> E[Retry / ErrorMessage / Durable fallback]
    E --> F[Audit / Alert]
~~~

**Phân biệt:**

- Queue đầy và `send(...) == false` không tự là một `ErrorMessage`.
- Exception trên `DirectChannel` có thể truyền về caller đồng bộ.
- Exception trong consumer chạy bằng poller/executor có thể được chuyển tới error channel của thành phần xử lý bất đồng bộ.
- Retry của một handler đã nhận message **không tự giải quyết** việc producer chưa đưa được message vào queue.

Không cấu hình cùng lúc retry ở producer, relay, handler và broker mà không tính ngân sách số lần thử tổng; điều đó có thể làm quá tải nhanh hơn khi downstream đang nghẽn.

### Bài test đường lỗi

Với một `FailFastPublisher` như mục 9:

1. Lấp đầy queue bằng event A.
2. Gửi event B và xác minh `MessageDeliveryException` được ném.
3. Quan sát bộ đếm `sendRejectedCount` hoặc một error flow được ứng dụng chủ động cấu hình.
4. Xác minh A vẫn trong queue và không có B.
5. Giải phóng slot, retry B có kiểm soát và xác minh B được nhận đúng một lần.

Một `ErrorMessage` ở tầng async chỉ là bằng chứng lỗi đã được công bố; còn cần xác nhận nó được ghi nhận/khắc phục và không bị mất khi process restart nếu nghiệp vụ yêu cầu độ bền.

## 13. Bài test có poller: tại sao rất dễ tạo race?

Giả sử `QueueChannel(capacity=1)` có một poller chạy mỗi 10 ms. Khi test gửi `A`, poller có thể lấy `A` ra **trước** khi test thử gửi `B`. Kết quả là `send(B, 0)` bất ngờ trả `true` dù người viết test nghĩ queue “đã đầy”.

~~~text
Test thread:    send(A) -------- send(B, 0)
Poller thread:           receive(A)
Queue content:   [A] -> [] -> [B]
~~~

Đây không phải lỗi `QueueChannel`, mà là **race của thiết kế test**.

### Ba cách kiểm soát

1. **Unit test channel độc lập** khi chỉ cần xác minh capacity và timeout (ưu tiên).
2. **Tắt/kiểm soát poller** trong giai đoạn lấp đầy buffer, sau đó chủ động cho nó chạy và kiểm tra kết quả.
3. **Dùng latch/gate trong handler** để điều phối một message đã được poll, rồi lấp đầy buffer bằng message khác; quan sát rõ số phần tử in-flight và số phần tử buffered.

Nếu dùng cách 3, cần phân biệt: message mà handler đã lấy ra **không còn chiếm slot queue**, dù handler chưa xử lý xong. Đừng assert sai rằng một message in-flight vẫn làm capacity queue giảm.

### Ma trận test thực tế

| Test case | Setup | Kỳ vọng |
| --- | --- | --- |
| Không đầy | Capacity 1, queue rỗng | `send(A, 0) == true` |
| Đầy, không chờ | Capacity 1, chứa A | `send(B, 0) == false` |
| Đầy, chờ có hạn | Capacity 1, chứa A, không có receiver | `send(B, 100) == false`; A còn nguyên |
| Đầy, consumer giải phóng kịp | Capacity 1, chứa A; receiver lấy A trước timeout | `send(B, timeout) == true` |
| FIFO buffer | Capacity 2, gửi A/B; C tạm bị từ chối; nhận A rồi gửi C | Nhận B rồi C |
| Producer bỏ qua `false` | Capacity đầy | Phát hiện nguy cơ mất B; phải sửa publisher |
| Publisher chuyển `false` thành exception | Queue đầy | Nhận `MessageDeliveryException` |
| Poller chạy đồng thời | Capacity 1; consumer poll sớm | Không kết luận đầy chỉ dựa vào `send(A)` trước đó |
| Consumer xử lý rất chậm | Consumer đã lấy A; queue chứa B | Phân biệt in-flight và buffered |
| Multi-producer | Nhiều sender cạnh tranh một slot | Không mặc định thứ tự khi không có hợp đồng FIFO toàn hệ thống |

## 14. CI ổn định: timeout có căn cứ và dọn tài nguyên

Một bài test chất lượng không dựa vào việc “máy này thường chạy trong 50 ms”. Dùng timeout để bảo vệ và điều kiện quan sát để xác nhận:

- `send(message, 0)` để kiểm tra tức thì khi đầy.
- `send(message, 100)` để kiểm tra bounded blocking khi không có receiver.
- `CountDownLatch.await(timeout)` khi cần biết sender/consumer đã bắt đầu.
- `Future.get(timeout)` để đợi thao tác gửi hoàn thành.
- `QueueChannel.receive(timeout)` để đợi đúng message ở đầu ra.
- JUnit `@Timeout` làm hàng rào chống test treo.

### Thói quen tránh flaky

| Vấn đề | Tác hại | Cách làm tốt |
| --- | --- | --- |
| `Thread.sleep(500)` rồi assert queue rỗng | Lệ thuộc lịch chạy thread | Đợi latch hoặc message cụ thể |
| Chờ vô hạn trên queue đầy | CI có thể treo mãi | Dùng `send(..., timeout)`, `@Timeout` |
| Không shutdown executor | Task cũ ảnh hưởng test sau | `finally` với `shutdownNow()`/cancel |
| Dùng chung queue giữa test | Message chen lẫn, assert sai | Queue/context mới theo test |
| Assert khoảng thời gian chính xác tuyệt đối | Máy chậm làm test fail | Assert kết quả và khoảng giới hạn có dư |
| Chỉ assert `send(...) == true` | Không biết consumer làm gì | Quan sát đầu ra/side effect riêng |
| Bỏ qua `send(...) == false` | Dữ liệu có thể mất | Chuyển thành policy retry/reject/fallback |

### Không nhầm “test chạy nhanh” với “test đúng”

Test nhanh nhưng không có xác nhận message đã vào queue hoặc đã xử lý thành công là một test yếu. Ngược lại, một test có timeout 5 giây có thể chạy chỉ trong vài mili giây nếu tín hiệu cần quan sát xuất hiện ngay.

## 15. Production: queue đầy là tín hiệu backpressure

Trong thực tế, cần giám sát **dung lượng đệm** và **năng lực tiêu thụ**, không chỉ số lỗi:

| Metric | Ý nghĩa |
| --- | --- |
| `sendAcceptedCount` | Số message channel nhận thành công |
| `sendRejectedCount` | Số lần gửi không được nhận trong timeout |
| `sendWaitMs` | Thời gian producer đợi slot |
| `queueDepth` | Số message đang ở buffer |
| `consumerInFlight` | Số message đã được lấy khỏi queue nhưng còn đang xử lý |
| `consumerProcessingMs` | Thời gian handler xử lý |
| `deadLetterCount` | Số message được đưa sang nhánh lỗi bền vững |
| `eventAgeMs` | Tuổi của message khi bắt đầu xử lý |

Đây là danh sách metric **ứng dụng có thể đo hoặc cấu hình instrumentation**, không mặc định mọi field có sẵn ở mọi loại channel và mọi phiên bản Spring Integration.

### Log có thể dùng để đối soát

~~~text
flow=orderProcessing
channel=orders.bounded
eventId=order-501-created-v1
correlationId=order-501
capacity=1
sendTimeoutMs=250
sendAccepted=false
failureReason=CHANNEL_FULL
fallback=OUTBOX
outcome=QUEUED_FOR_RETRY
~~~

Một trường `sendAccepted=false` không đủ để kết luận request nghiệp vụ bị hủy; cần quan sát cả **fallback**. Nếu outbox đã ghi thành công, API có thể báo “đã tiếp nhận để xử lý sau” theo hợp đồng phù hợp, nhưng không được nói consumer đã hoàn thành.

### Persistence và restart

`QueueChannel` dùng bộ nhớ thông thường không tự lưu message bền vững qua restart. Ngay cả khi `send(A) == true`, tiến trình dừng có thể làm mất A nếu A chỉ nằm trong RAM. Với message quan trọng, cân nhắc persistent `MessageStore` được cấu hình đúng, broker hoặc transactional outbox. Khi dùng persistent store, cần kiểm thử startup recovery, transaction và idempotency.

Nếu retry ở producer sau timeout, dùng `eventId` ổn định; nếu trước đó message đã được gửi sang một transport có kết quả không chắc chắn, cần consumer idempotent hoặc một giao thức xác nhận phù hợp. Backpressure và persistence giải quyết **hai bài toán khác nhau**.

## 16. Bài tập thực hành

1. Tạo `QueueChannel(1)`, gửi A bằng `send(A, 0)`, gửi B bằng `send(B, 0)`. Assert đúng `true/false` và chứng minh chỉ có A trong queue.
2. Lấp đầy queue rồi gọi `send(B, 200)` khi không có consumer. Assert `false`; không cần `Thread.sleep(200)`.
3. Dùng `CountDownLatch` và `Future` để tạo sender bị chặn trên queue đầy; giải phóng slot bằng `receive(0)`, xác minh sender hoàn thành `true`.
4. Thêm case sender hết timeout trước khi consumer nhận A; sau đó consumer nhận A và producer phải chủ động retry B. Xác minh B không tự xuất hiện nếu không retry.
5. Dùng `QueueChannel(2)` để kiểm tra FIFO trong một luồng gửi/nhận đơn giản.
6. Cấu hình `FailFastPublisher` chuyển `send == false` thành `MessageDeliveryException`; thử case queue đầy và kiểm tra A không bị mất.
7. Thêm poller lấy A khỏi queue rất nhanh. Tạo test race cố ý, rồi sửa bằng cách cô lập channel hoặc điều phối poller.
8. Cho handler xử lý A chậm nhưng đã lấy khỏi queue. Gửi B/C để phân biệt công việc **in-flight** với message **buffered**.
9. Tạo hai producer cùng gửi một message vào queue capacity=1. Kiểm tra rằng test không giả định thứ tự thắng cuộc khi chưa có hợp đồng sắp xếp.
10. Đưa bounded queue vào giữa Router và consumer, xây policy khi high-priority message không thể được nhận; so sánh retry, reject và durable fallback.
11. Kiểm thử Gateway `requestTimeout` khi bàn giao vào một queue đầy, rồi so sánh với `replyTimeout` khi queue đã nhận request nhưng consumer trả lời chậm.
12. Bổ sung metric `sendRejectedCount`, `queueDepth` và `consumerInFlight`; chạy một đợt tải ngắn và giải thích dấu hiệu backpressure.
13. Dừng JVM khi queue trong bộ nhớ còn A và nêu vì sao kết quả `send(A) == true` không đồng nghĩa tồn tại sau restart.
14. Thiết kế bản thử nghiệm Outbox → bounded channel → consumer, rồi mô tả ranh giới transaction, retry, idempotency và error channel của từng bước.

### Câu hỏi tự kiểm tra

- `send(message, 0)` và `send(message, timeout)` khác nhau thế nào khi queue đầy?
- Khi gửi `B` trả `false`, message `A` đang chờ có bị ảnh hưởng không?
- Vì sao `receive(0)` lấy một message ra có thể khiến sender đang chờ được đánh thức?
- Một consumer đã lấy message khỏi queue nhưng chưa xử lý xong có còn chiếm slot buffer không?
- Vì sao `send(timeout)` trên một `DirectChannel` không chứng minh timeout của mọi endpoint phía sau?
- Hành vi quá tải của `ExecutorChannel` có giống bounded `QueueChannel` không?
- `send == false` có tự động tạo một `ErrorMessage` không?
- Tại sao không dùng `Thread.sleep(...)` để kiểm tra producer đang chờ?
- Khi nào nên trả lỗi caller, khi nào nên lưu outbox, và khi nào được phép drop message?
- Vì sao queue nhận thành công chưa đồng nghĩa tác động nghiệp vụ thành công hoặc dữ liệu bền vững?

## Tài liệu tham khảo

- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `QueueChannel`, `DirectChannel`, `ExecutorChannel`, `RendezvousChannel` và hành vi channel.
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): cách poller nhận message từ `PollableChannel`.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): xử lý exception đồng bộ/bất đồng bộ và `ErrorMessage`.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): xây IntegrationFlow, endpoint và channel.
- [Spring Framework — MessageChannel API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html): `send(message)` và `send(message, timeout)`.
- [Java SE API — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ test bằng `await/countDown`.
- [Java SE API — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)`, cancellation và giới hạn thời gian đợi kết quả.
