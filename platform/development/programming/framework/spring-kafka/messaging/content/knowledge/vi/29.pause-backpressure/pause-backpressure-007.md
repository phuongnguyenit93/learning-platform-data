# Khác nhau giữa pause và stop

Khi downstream xử lý chậm hoặc ứng dụng cần tạm ngừng nhận thêm record, Spring Kafka cung cấp hai thao tác dễ bị nhầm lẫn: `pause()` và `stop()`. Cả hai đều làm listener ngừng xử lý record mới trong một khoảng thời gian, nhưng chúng có tác động rất khác nhau đến Kafka consumer, poll loop, consumer group và quá trình tiếp tục xử lý.

`pause()` tạm dừng việc lấy record từ partition nhưng giữ listener container và consumer đang hoạt động. Container tiếp tục poll để duy trì hoạt động của consumer group. `stop()` dừng container và đóng consumer; consumer rời group, có thể gây rebalance. Vì vậy, pause phù hợp với backpressure tạm thời, còn stop phù hợp với việc kết thúc hoặc tái cấu hình vòng đời listener.

## 1. Phân biệt pause và stop

| Tiêu chí | `pause()` | `stop()` |
| --- | --- | --- |
| Mục đích | Tạm ngừng nhận record mới | Dừng listener container |
| Kafka consumer | Vẫn tồn tại và tiếp tục poll | Được đóng khi container dừng |
| Consumer group | Consumer vẫn duy trì membership nếu hoạt động bình thường | Consumer rời group; có thể xảy ra rebalance |
| Partition assignment | Thường được giữ nguyên trong lúc pause | Có thể được phân công lại cho consumer khác |
| Offset | Không tự commit chỉ vì pause; tiếp tục theo AckMode hiện tại | Offset đã commit được giữ; record chưa commit có thể được giao lại khi khởi động |
| Tiếp tục | Gọi `resume()` | Gọi `start()` để tạo/khởi động consumer lại |
| Trường hợp phù hợp | Queue downstream gần đầy, hệ thống phụ thuộc quá tải ngắn hạn | Tắt subscription, bảo trì, thay đổi cấu hình hoặc kết thúc ứng dụng |

Pause là trạng thái tạm thời của consumer đang chạy. Stop là thay đổi lifecycle của container. Không nên dùng stop/start như một cách điều tiết tải thường xuyên vì việc rời và tham gia lại consumer group có thể gây rebalance, thay đổi partition assignment và làm tăng độ trễ.

## 2. Pause giữ poll loop hoạt động

Khi gọi `pause()`, Spring Kafka yêu cầu container tạm dừng các partition đang tiêu thụ. Việc pause được áp dụng trong luồng consumer ở thời điểm container xử lý poll tiếp theo; nó không hủy lời gọi listener đang chạy và không thể thu hồi record đã được giao cho listener.

Trong lúc pause, container vẫn tiếp tục gọi `poll()` để duy trì consumer hoạt động và xử lý các sự kiện điều phối của Kafka. Các partition đã pause không trả về record mới cho listener, nhưng consumer vẫn duy trì kết nối và membership trong group nếu poll/heartbeat hoạt động bình thường.

Điều này rất quan trọng với backpressure. Nếu listener chỉ cần nghỉ để queue nội bộ được xử lý bớt, pause cho phép consumer giữ assignment hiện tại. Khi tải giảm, `resume()` cho phép container tiếp tục nhận record từ các partition đó.

```text
RUNNING
   |
   | downstream queue gần đầy
   v
PAUSE REQUESTED
   |
   | container áp dụng pause trước poll tiếp theo
   v
PAUSED (consumer vẫn poll, không giao record mới)
   |
   | queue giảm xuống ngưỡng thấp
   v
RESUME REQUESTED
   |
   | container áp dụng resume
   v
RUNNING
```

Pause không phải một hàng đợi lưu trữ mới. Kafka vẫn giữ record trong topic theo retention; consumer chỉ tạm ngừng nhận record mới từ các partition đã pause. Nếu pause quá lâu, consumer vẫn phải duy trì poll theo cấu hình và hệ thống vẫn cần theo dõi lag, retention cùng tình trạng downstream.

## 3. Gọi pause và resume qua listener container

Với listener khai báo bằng `@KafkaListener`, có thể lấy container từ `KafkaListenerEndpointRegistry` rồi điều khiển lifecycle:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
class OrderListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    OrderListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");
        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");
        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
```

ID `orders-listener` phải khớp với `id` của `@KafkaListener` hoặc endpoint đã đăng ký. `pause()` và `resume()` được gọi trên container; không lấy `KafkaConsumer` rồi gọi trực tiếp từ thread nghiệp vụ khác. Kafka consumer không an toàn khi được điều khiển tùy tiện từ nhiều thread, trong khi container biết cách chuyển yêu cầu về đúng luồng consumer.

Có thể kiểm tra trạng thái yêu cầu pause và trạng thái pause thực tế bằng các API trạng thái của `MessageListenerContainer`, chẳng hạn `isPauseRequested()` và `isContainerPaused()` trong các phiên bản hỗ trợ. Yêu cầu pause vừa gửi không có nghĩa container đã áp dụng xong ngay tại thời điểm phương thức trả về.

## 4. Pause toàn container hay pause một partition?

Nếu chỉ một partition có downstream chậm hoặc một nhóm key cần được điều tiết, có thể pause riêng partition thay vì dừng toàn bộ container. Các API `pausePartition(TopicPartition)` và `resumePartition(TopicPartition)` có trên các phiên bản Spring Kafka hỗ trợ điều khiển partition.

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.MessageListenerContainer;

TopicPartition slowPartition = new TopicPartition("orders", 2);

MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null && container.isRunning()) {
    container.pausePartition(slowPartition);
}

// Khi downstream của partition này đã phục hồi:
if (container != null && container.isRunning()) {
    container.resumePartition(slowPartition);
}
```

Với `ConcurrentMessageListenerContainer`, một endpoint có thể quản lý nhiều child container/consumer. Hãy xác minh cách phiên bản Spring Kafka đang dùng áp dụng pause toàn container và pause partition trên các child consumer. Nếu partition chưa được assign cho container, thao tác pause partition có thể chưa có hiệu lực cho đến khi assignment phù hợp xuất hiện.

Pause một partition giúp các partition khác tiếp tục xử lý. Tuy nhiên, nếu tất cả partition đều bị pause thì kết quả gần giống pause toàn container. Cần theo dõi lag theo partition để tránh một partition bị pause quá lâu mà không được resume.

## 5. Stop đóng consumer và ảnh hưởng consumer group

Khi gọi `stop()`, listener container đi qua lifecycle shutdown. Consumer được đánh thức khỏi poll, container dừng việc xử lý và đóng consumer theo trình tự shutdown của Spring Kafka. Khi consumer rời group, coordinator có thể phân công partition cho consumer còn lại hoặc consumer mới.

```java
public void stopOrders() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");
    if (container != null && container.isRunning()) {
        container.stop();
    }
}

public void startOrders() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");
    if (container != null && !container.isRunning()) {
        container.start();
    }
}
```

`stop()` giữ endpoint/container đã đăng ký trong registry để có thể start lại. Nếu muốn xóa hẳn một listener endpoint động khỏi registry, cần thực hiện unregister theo API tương ứng sau khi dừng container. Việc stop một listener được khai báo bằng `@KafkaListener` không tự xóa bean hoặc annotation khỏi ứng dụng.

Khi start lại với cùng group ID, consumer tham gia group và tiếp tục từ offset đã commit theo cấu hình. Record đã được poll nhưng chưa commit có thể được giao lại. Với group ID mới, consumer không có committed offset riêng và vị trí bắt đầu phụ thuộc `auto.offset.reset`.

Stop có thể gây rebalance và ảnh hưởng các consumer khác trong group. Nếu chỉ cần tạm ngừng nhận record trong khi chờ downstream, pause thường ít xáo trộn hơn.

## 6. Offset và record đang xử lý

Pause không tự xác nhận offset. Record đã được listener xử lý vẫn được commit theo `AckMode`, transaction và thời điểm acknowledgment của container. Record đang nằm trong queue nội bộ cũng cần được xem là chưa xử lý xong nếu ứng dụng mới chỉ nhận vào queue mà chưa lưu bền vững.

Stop cũng không có nghĩa tất cả record đã poll đều được commit. Kết quả phụ thuộc vào record đã hoàn tất hay chưa, acknowledgment mode, transaction và cách container dừng. Nếu record chưa được xác nhận trước khi consumer đóng, Kafka có thể giao lại record sau khi consumer hoặc một thành viên khác của group tiếp tục.

| Trạng thái record | Khi pause | Khi stop rồi start lại |
| --- | --- | --- |
| Đã xử lý và offset đã commit | Không bị đọc lại theo offset đã commit | Tiếp tục sau offset đã commit |
| Đã poll nhưng listener chưa xử lý xong | Không nhận thêm record mới; record hiện tại tiếp tục theo luồng xử lý | Có thể được giao lại nếu offset chưa commit |
| Listener đã xử lý nhưng chưa commit | Commit theo AckMode/transaction hiện tại | Có thể bị giao lại sau restart nếu commit chưa hoàn tất |
| Đã bị pause trước khi poll tiếp | Vẫn nằm trong Kafka | Consumer mới đọc theo offset đã commit |

Nếu listener đưa record vào queue trong bộ nhớ rồi trả về bình thường, container có thể commit offset trước khi worker xử lý xong. Pause/stop không tự khắc phục được vấn đề này. Hãy chỉ xác nhận sau khi công việc được lưu bền vững, hoặc dùng inbox/outbox, durable queue và idempotency phù hợp.

## 7. Dùng pause để tạo backpressure

Backpressure là cách điều tiết tốc độ producer/consumer khi thành phần phía sau không thể xử lý tải hiện tại. Một mẫu phổ biến là dùng queue có giới hạn và hai ngưỡng:

- **High watermark:** khi queue đạt ngưỡng cao, yêu cầu pause consumer.
- **Low watermark:** khi queue giảm xuống ngưỡng thấp, yêu cầu resume consumer.

Hai ngưỡng tách biệt tạo hysteresis, tránh trạng thái pause/resume liên tục khi queue dao động quanh một điểm.

```java
import java.util.concurrent.BlockingQueue;
import org.springframework.kafka.listener.MessageListenerContainer;

class QueueBackpressureController {

    private final BlockingQueue<OrderCreated> queue;
    private final MessageListenerContainer container;
    private final int highWatermark;
    private final int lowWatermark;

    QueueBackpressureController(
            BlockingQueue<OrderCreated> queue,
            MessageListenerContainer container,
            int highWatermark,
            int lowWatermark) {
        this.queue = queue;
        this.container = container;
        this.highWatermark = highWatermark;
        this.lowWatermark = lowWatermark;
    }

    public void afterEnqueue() {
        if (queue.size() >= highWatermark && container.isRunning()) {
            container.pause();
        }
    }

    public void afterWorkCompleted() {
        if (queue.size() <= lowWatermark
                && container.isRunning()
                && container.isPauseRequested()) {
            container.resume();
        }
    }
}
```

Đây là ví dụ minh họa; trong ứng dụng thật, controller nên quản lý container theo ID hoặc được inject trực tiếp, đồng thời đồng bộ hóa quyết định pause/resume nếu nhiều worker cùng cập nhật queue. Listener chỉ gọi `afterEnqueue()` sau khi record đã được chấp nhận vào queue. Nếu `queue.offer()` thất bại, listener phải giữ được record bằng một cơ chế retry/recovery hoặc ném exception để container xử lý; không được trả về bình thường và làm mất record.

Ngưỡng cần dựa trên dung lượng queue, tốc độ xử lý trung bình, số consumer và thời gian downstream phục hồi. Theo dõi cả queue depth lẫn Kafka lag: queue giảm không nhất thiết có nghĩa Kafka lag đã giảm, và ngược lại.

## 8. Tránh các lỗi thường gặp khi pause/resume

1. **Gọi pause rồi chờ ngay lập tức container đã paused.** Pause là yêu cầu được áp dụng trong luồng consumer; hãy quan sát trạng thái pause thực tế hoặc event tương ứng.
2. **Gọi resume từ một điều kiện không có hysteresis.** Queue dao động quanh một ngưỡng có thể gây pause/resume liên tục.
3. **Pause nhưng vẫn để queue tăng vô hạn.** Pause chỉ ngăn nhận thêm record mới; công việc đã đưa vào queue vẫn cần được xử lý và queue phải có giới hạn.
4. **Dùng stop để điều tiết tải thường xuyên.** Stop làm consumer rời group và có thể gây rebalance.
5. **Gọi KafkaConsumer.pause() từ thread nghiệp vụ.** Hãy điều khiển qua `MessageListenerContainer` để container thực hiện trên consumer thread.
6. **Cho rằng pause sẽ hủy record đang chạy.** Listener invocation hiện tại không bị thu hồi chỉ vì gọi pause.
7. **Trả về listener sau khi đẩy tác vụ bất đồng bộ nhưng chưa lưu bền vững.** Offset có thể được commit trước khi công việc hoàn tất.
8. **Không có cơ chế resume khi ứng dụng lỗi.** Cần giám sát trạng thái pause và có quy trình phục hồi nếu controller dừng giữa chừng.

Không nên dùng `Thread.sleep()` trong listener để giả lập pause. Thread listener bị chặn có thể làm chậm poll, vượt `max.poll.interval.ms` và khiến consumer bị xem là không còn hoạt động. Hãy dùng API pause của container cho backpressure.

## 9. Lifecycle event và quan sát trạng thái

Spring Kafka phát các event liên quan đến việc pause/resume consumer như `ConsumerPausedEvent` và `ConsumerResumedEvent` ở các phiên bản hỗ trợ. Có thể dùng event listener để cập nhật metric hoặc trạng thái vận hành. Khi theo dõi, phân biệt yêu cầu pause với thời điểm tất cả consumer/partition thực sự đã pause.

Các số liệu nên có:

- Trạng thái container: running, pause requested, paused hoặc stopped.
- Thời lượng pause và số lần pause/resume trong một khoảng thời gian.
- Queue depth, queue capacity và thời gian xử lý downstream.
- Consumer lag theo topic/partition.
- Số record đang xử lý và số record chờ trong queue nội bộ.
- Số lần rebalance, consumer restart và lỗi khi start/stop.

Nếu container bị pause quá ngưỡng vận hành, phát cảnh báo và kiểm tra downstream, queue worker, lỗi resume hoặc sự cố điều phối. Không nên tự động resume chỉ dựa trên timer nếu downstream vẫn quá tải.

## 10. Khi nào nên pause, khi nào nên stop?

| Tình huống | Lựa chọn | Lý do |
| --- | --- | --- |
| Queue xử lý nội bộ gần đầy | Pause | Giữ consumer trong group và tạm ngừng nhận thêm record |
| Dịch vụ downstream quá tải trong thời gian ngắn | Pause | Có thể tiếp tục trên cùng assignment sau khi phục hồi |
| Chỉ một partition bị nghẽn | Pause partition | Các partition khác vẫn có thể tiếp tục xử lý |
| Tắt subscription của tenant | Stop hoặc unregister | Kết thúc hoạt động của container theo lifecycle |
| Bảo trì hoặc thay đổi consumer configuration | Stop rồi start lại | Consumer cần được tạo lại với cấu hình mới |
| Ứng dụng shutdown | Stop theo lifecycle | Đóng consumer và giải phóng tài nguyên |
| Cần retry record lỗi | Error handler/retry topic | Pause toàn container không thay thế chính sách retry theo record |

Nếu muốn dừng hẳn một subscription động, dừng container rồi unregister endpoint khi không cần khởi động lại. Nếu chỉ muốn chờ hệ thống phục hồi, pause/resume là lựa chọn phù hợp hơn.

## 11. Kiểm thử pause và stop

Kiểm thử tích hợp với Kafka nên xác minh cả hành vi listener, offset và consumer group:

1. Gửi nhiều record, gọi pause và xác minh listener không nhận thêm record sau khi pause được áp dụng.
2. Trong lúc pause, xác minh consumer vẫn duy trì hoạt động/poll và không tạo rebalance chỉ vì thao tác pause.
3. Gọi resume và xác minh listener tiếp tục nhận record từ assignment hiện tại.
4. Gọi stop và xác minh container dừng, consumer rời group và có thể xuất hiện rebalance.
5. Start lại cùng group ID; xác minh consumer tiếp tục từ offset đã commit và record chưa commit có thể được giao lại.
6. Kiểm tra `AckMode` và transaction để xác minh record nào được commit khi pause/stop xảy ra trong lúc có công việc đang chạy.
7. Mô phỏng queue vượt high watermark rồi giảm dưới low watermark; xác minh pause/resume chỉ được yêu cầu tại đúng ngưỡng.
8. Làm worker downstream lỗi hoặc không thể enqueue; xác minh record không bị xác nhận khi chưa được lưu an toàn.

## 12. Checklist triển khai

- [ ] Dùng `pause()`/`resume()` cho backpressure tạm thời và `stop()`/`start()` cho lifecycle.
- [ ] Điều khiển qua `MessageListenerContainer` hoặc registry, không thao tác trực tiếp consumer từ thread khác.
- [ ] Hiểu rằng pause được áp dụng trong luồng consumer và không hủy listener invocation đang chạy.
- [ ] Có high/low watermark để tránh pause/resume liên tục.
- [ ] Queue downstream có giới hạn và có cách xử lý khi enqueue thất bại.
- [ ] Offset chỉ được xác nhận khi công việc đã hoàn tất hoặc được lưu bền vững theo thiết kế.
- [ ] Theo dõi thời lượng pause, queue depth, Kafka lag và rebalance.
- [ ] Có quy trình phục hồi nếu container bị pause lâu hoặc không resume được.
- [ ] Kiểm thử pause/resume, stop/start, redelivery và acknowledgment với cấu hình thực tế.

Pause giữ consumer và poll loop hoạt động trong khi tạm ngừng nhận record; stop kết thúc consumer và làm thay đổi membership của group. Phân biệt đúng hai thao tác giúp ứng dụng kiểm soát backpressure mà không tạo rebalance không cần thiết, đồng thời bảo toàn offset và xử lý record đang chạy theo chính sách đã cấu hình.
