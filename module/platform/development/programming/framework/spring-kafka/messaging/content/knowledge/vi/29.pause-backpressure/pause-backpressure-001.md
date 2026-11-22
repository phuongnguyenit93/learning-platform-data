# Pause toàn bộ listener container

Spring Kafka cho phép tạm dừng việc nhận record của một listener container mà không phải dừng hẳn container hoặc đóng Kafka consumer. Khi gọi `pause()`, container yêu cầu các consumer do nó quản lý tạm ngừng nhận record từ những partition đang được gán. Container vẫn tiếp tục poll để duy trì hoạt động trong consumer group; khi gọi `resume()`, việc nhận record được tiếp tục.

Pause toàn bộ container hữu ích khi downstream đang quá tải, ứng dụng cần bảo trì một dependency, hệ thống muốn điều tiết tốc độ xử lý hoặc cần tạm dừng một nhóm listener trong lúc thay đổi trạng thái vận hành. Với listener có concurrency, thao tác pause trên container endpoint áp dụng cho các consumer con của endpoint đó.

## 1. Pause container khác gì stop container?

`pause()` và `stop()` có mục đích khác nhau:

| Hành vi | `pause()` | `stop()` |
| --- | --- | --- |
| Nhận record mới | Tạm ngừng nhận record | Không còn consumer poll vì container đã dừng |
| Kafka consumer | Vẫn được giữ và tiếp tục poll | Consumer được đóng khi quá trình stop hoàn tất |
| Consumer group membership | Consumer tiếp tục duy trì hoạt động trong group | Consumer rời group; partition có thể được gán lại |
| Tiếp tục xử lý | Gọi `resume()` | Gọi `start()` để khởi động lại container |
| Mục đích | Điều tiết tạm thời/backpressure | Dừng listener lifecycle |

Pause không phải thao tác commit offset. Offset vẫn tuân theo `AckMode`, acknowledgement và transaction đang cấu hình. Nếu record đã xử lý nhưng chưa commit, sự cố hoặc shutdown sau đó vẫn có thể khiến record được giao lại.

## 2. Pause một listener container bằng KafkaListenerEndpointRegistry

Với listener khai báo bằng `@KafkaListener`, Spring Kafka đăng ký endpoint vào `KafkaListenerEndpointRegistry`. Có thể lấy container theo `id` rồi gọi `pause()` hoặc `resume()`.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
            id = "orders-listener",
            topics = "orders.created",
            groupId = "orders-projection")
    public void onMessage(String payload) {
        // Xử lý event.
    }
}
```

Điều khiển container theo ID:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null) {
            throw new IllegalArgumentException(
                    "Listener container 'orders-listener' was not found");
        }

        container.pause();
    }

    public void resumeOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null) {
            throw new IllegalArgumentException(
                    "Listener container 'orders-listener' was not found");
        }

        container.resume();
    }
}
```

`id` trong `@KafkaListener` là định danh endpoint dùng để tra cứu container. Nó khác với `groupId`: group ID xác định consumer group trên Kafka, còn listener ID xác định container trong ứng dụng Spring.

## 3. Pause tất cả listener container được registry quản lý

Khi cần tạm dừng toàn bộ listener endpoint được khai báo bằng `@KafkaListener`, duyệt qua `registry.getListenerContainers()` và gọi `pause()` cho từng container:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class AllListenersControlService {

    private final KafkaListenerEndpointRegistry registry;

    public AllListenersControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseAll() {
        registry.getListenerContainers()
                .forEach(MessageListenerContainer::pause);
    }

    public void resumeAll() {
        registry.getListenerContainers()
                .forEach(MessageListenerContainer::resume);
    }
}
```

`getListenerContainers()` trả về các container do registry quản lý. Nếu ứng dụng tự tạo và quản lý container bên ngoài registry, cần giữ reference đến các container đó và pause/resume riêng. Hãy giới hạn phạm vi điều khiển đúng các listener mà thao tác vận hành cần tác động; không mặc định rằng một registry bao gồm mọi container được tạo thủ công.

Nếu một endpoint dùng `concurrency = "3"`, registry trả về container endpoint tương ứng; đó là `ConcurrentMessageListenerContainer` quản lý ba child container. Gọi `pause()` trên container cha sẽ yêu cầu các consumer con pause, không cần tự duyệt từng thread.

## 4. Pause hoạt động bất đồng bộ trên consumer thread

Các phương thức `pause()` và `resume()` được thiết kế để có thể gọi từ thread ứng dụng. Lệnh gọi đặt yêu cầu điều khiển; thao tác pause/resume Kafka consumer thực tế được thực hiện trên consumer thread của container.

Vì vậy, ngay sau khi gọi `pause()`, không nên giả định rằng consumer đã ở trạng thái paused. Có hai trạng thái cần phân biệt:

| API | Ý nghĩa |
| --- | --- |
| `isPauseRequested()` | Container đã nhận yêu cầu pause |
| `isConsumerPaused()` | Consumer đã thực sự chuyển sang trạng thái paused |

Ví dụ kiểm tra trạng thái:

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

container.pause();

boolean requested = container.isPauseRequested();
boolean paused = container.isConsumerPaused();
```

Ngay sau `pause()`, `requested` có thể là `true` trong khi `paused` vẫn là `false`. Ứng dụng quản trị nên chờ trạng thái consumer thực tế hoặc theo dõi sự kiện container thay vì trả về thông báo “đã pause hoàn tất” ngay khi lệnh được gửi.

## 5. Container xử lý record đang có trong poll như thế nào?

Kafka consumer có thể trả về nhiều record trong một lần `poll()`. Khi container nhận yêu cầu pause trong lúc đang xử lý các record của poll hiện tại, hành vi mặc định là xử lý xong các record đã lấy về rồi mới pause trước lần poll tiếp theo.

```text
poll() trả về: R1, R2, R3, R4
                 |
                 v
            Xử lý R1
                 |
           pause() được gọi
                 |
                 v
            Xử lý R2
                 |
                 v
            Xử lý R3
                 |
                 v
            Xử lý R4
                 |
                 v
          Consumer pause
                 |
                 v
        Không nhận record mới
```

Điều này giúp tránh bỏ dở batch record đã được poll, nhưng có nghĩa pause không nhất thiết dừng listener ngay lập tức. Nếu poll trước đó trả về nhiều record hoặc xử lý mỗi record lâu, khoảng thời gian từ lúc yêu cầu pause đến lúc consumer paused có thể đáng kể.

## 6. Dùng pauseImmediate khi cần dừng sớm hơn

Spring Kafka hỗ trợ `pauseImmediate` trên container properties. Khi bật, container pause sau khi xử lý record hiện tại thay vì tiếp tục xử lý toàn bộ record còn lại từ poll trước.

```java
factory.getContainerProperties().setPauseImmediate(true);
```

Thiết lập này hữu ích khi ứng dụng cần phản ứng nhanh với backpressure và không muốn xử lý hết số record còn lại trong poll hiện tại. Với record listener, container có thể giữ các record chưa được gọi listener để giao cho listener sau khi resume. Với batch listener, listener invocation nhận cả batch như một đơn vị; không thể dừng giữa thân phương thức batch như thể mỗi record là một lần gọi riêng.

`pauseImmediate` không hủy công việc đang chạy và không rollback side effect đã thực hiện. Nếu listener đang xử lý record, container phải chờ điểm an toàn của lần xử lý đó trước khi pause. Hãy kiểm thử hành vi với loại listener và AckMode thực tế.

## 7. Resume và tiếp tục nhận record

Gọi `resume()` để yêu cầu container tiếp tục nhận record từ các partition đã được gán:

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null && container.isPauseRequested()) {
    container.resume();
}
```

`resume()` cũng là yêu cầu được áp dụng trên consumer thread. Khi consumer đã resume, lần poll tiếp theo có thể trả về record đang chờ trên Kafka. Nếu listener có concurrency, việc resume container cha áp dụng cho các consumer con tương ứng.

Resume không đảm bảo backlog được xử lý ngay lập tức. Tốc độ tiếp tục phụ thuộc partition assignment, poll interval, listener processing time, consumer lag và năng lực downstream.

## 8. Pause toàn bộ container khi downstream quá tải

Một tình huống phổ biến là listener đọc Kafka nhanh hơn khả năng ghi database. Nếu tiếp tục nhận record, ứng dụng có thể tích lũy công việc chờ, cạn connection pool hoặc tăng heap.

Có thể pause container khi chỉ số downstream vượt ngưỡng:

```text
Database pool usage / queue depth / latency
                 |
                 v
        Vượt ngưỡng HIGH
                 |
                 v
        pauseAllListeners()
                 |
                 v
       Downstream phục hồi
                 |
                 v
        Xuống dưới LOW
                 |
                 v
       resumeAllListeners()
```

Nên dùng hai ngưỡng HIGH và LOW khác nhau (hysteresis) để tránh pause/resume liên tục khi metric dao động quanh một ngưỡng. Ví dụ pause khi connection pool đạt 90%, chỉ resume khi giảm xuống dưới 65% và latency ổn định trong một khoảng thời gian.

Pseudo-code điều phối:

```java
public void onDownstreamPressure(DownstreamMetrics metrics) {
    if (metrics.poolUsage() >= 0.90 || metrics.queueDepth() >= 1_000) {
        listenerControl.pauseAll();
        return;
    }

    if (metrics.poolUsage() <= 0.65 && metrics.queueDepth() < 300) {
        listenerControl.resumeAll();
    }
}
```

Đây là logic minh họa. Trong ứng dụng thật, cần debounce/thời gian ổn định, bảo đảm chỉ một thành phần chịu trách nhiệm điều khiển trạng thái, và có cơ chế xử lý khi service restart trong lúc đang pause.

## 9. Pause không làm Kafka ngừng nhận dữ liệu

Pause listener container chỉ dừng việc consumer lấy record để giao cho listener. Producer và broker vẫn hoạt động; record mới tiếp tục được ghi vào topic nếu producer gửi.

Do đó, khi pause kéo dài:

- Consumer lag tăng vì offset đọc không tiến.
- Kafka giữ record theo retention và cleanup policy của topic.
- Dung lượng broker tiếp tục được sử dụng bởi dữ liệu mới.
- Khi resume, consumer phải xử lý backlog tích lũy.

Pause là backpressure ở phía consumer, không phải flow control xuyên suốt toàn hệ thống. Nếu cần giảm tốc độ phát sinh event, có thể phải điều tiết producer, giới hạn request đầu vào hoặc áp dụng quota/rate limit ở upstream.

## 10. Pause và consumer group membership

Trong lúc paused, Spring Kafka tiếp tục poll consumer để duy trì hoạt động trong group. Consumer không nhận record mới từ partition đang pause nhưng vẫn tham gia group và giữ assignment trong điều kiện bình thường.

Điều này khác với stop container, đóng consumer hoặc để consumer không poll trong thời gian quá dài. Các tình huống đó có thể khiến member rời group hoặc bị xem là không hoạt động, dẫn đến rebalance.

Pause không ngăn mọi loại rebalance. Rebalance vẫn có thể xảy ra khi topic partition thay đổi, member khác tham gia/rời group, subscription thay đổi hoặc lỗi hạ tầng. Sau rebalance, container tiếp tục điều phối pause/resume theo trạng thái và assignment mới; hãy xác minh hành vi trong phiên bản Spring Kafka đang chạy.

## 11. Pause tất cả endpoint có phạm vi rộng: cần kiểm soát quyền

Nếu cung cấp chức năng pause/resume qua REST hoặc giao diện quản trị, đây là thao tác ảnh hưởng trực tiếp đến tiến độ xử lý event. Chỉ expose endpoint cho operator hoặc hệ thống điều phối đáng tin cậy.

Một API quản trị nên:

- Có xác thực và phân quyền riêng cho pause/resume.
- Ghi audit người gọi, thời điểm, lý do và phạm vi listener.
- Trả về trạng thái yêu cầu và trạng thái consumer thực tế.
- Có cảnh báo khi container bị pause quá thời gian cho phép.
- Có cơ chế resume có kiểm soát sau bảo trì hoặc khi downstream phục hồi.
- Tránh cho nhiều hệ thống cùng điều khiển một container mà không có state owner rõ ràng.

Không nên tự động resume chỉ vì ứng dụng vừa khởi động nếu trạng thái pause được điều phối bởi một quy trình bảo trì bên ngoài. Ngược lại, nếu pause chỉ là trạng thái tạm thời trong memory, hãy có chính sách khôi phục rõ ràng sau restart vì container mới có thể bắt đầu ở trạng thái running.

## 12. Pause container và pause partition

Pause toàn bộ container tác động đến mọi partition được consumer trong container quản lý. Nếu chỉ một partition bị hot hoặc downstream xử lý riêng theo partition, có thể cần pause partition thay vì cả container.

| Phạm vi | API/ý tưởng | Khi dùng |
| --- | --- | --- |
| Toàn bộ endpoint | `MessageListenerContainer.pause()` | Tạm ngừng tất cả partition được endpoint quản lý |
| Tiếp tục toàn endpoint | `MessageListenerContainer.resume()` | Cho endpoint nhận record trở lại |
| Một partition | `pausePartition(TopicPartition)` | Điều tiết một partition cụ thể |
| Tiếp tục một partition | `resumePartition(TopicPartition)` | Mở lại partition cụ thể |

Pause partition có thêm yêu cầu xác định partition đang được consumer nào sở hữu và cách xử lý khi rebalance. Nếu mục tiêu là tạm dừng cả listener endpoint, dùng `pause()` đơn giản và nhất quán hơn.

## 13. Monitoring trạng thái pause

Không chỉ ghi nhận lệnh pause đã được gọi. Nên quan sát cả yêu cầu và trạng thái thực tế:

| Thông tin | Mục đích |
| --- | --- |
| Listener ID | Biết endpoint nào đang pause |
| `isPauseRequested()` | Biết container đã nhận yêu cầu pause |
| `isConsumerPaused()` | Xác nhận consumer đã thực sự pause |
| Pause duration | Phát hiện container bị pause quá lâu |
| Consumer lag | Đo backlog tích lũy trong lúc pause |
| Downstream health | Xác định điều kiện để resume |
| Rebalance events | Phát hiện assignment thay đổi trong thời gian pause |

Spring Kafka có các application event liên quan tới consumer pause/resume ở các phiên bản hỗ trợ. Có thể dùng event listener để ghi nhận trạng thái, nhưng trạng thái vận hành quan trọng vẫn nên được kiểm tra từ container và metric của ứng dụng.

## 14. Kiểm thử pause/resume

Integration test nên xác minh consumer thực sự ngừng giao record mới và tiếp tục sau resume.

Một kịch bản với Embedded Kafka:

1. Tạo topic test và listener có `id` cố định.
2. Gửi một record và xác nhận listener nhận được.
3. Gọi `pause()` qua `KafkaListenerEndpointRegistry`.
4. Chờ đến khi `isConsumerPaused()` trả về `true`.
5. Gửi thêm record trong lúc paused.
6. Xác nhận listener không nhận các record mới trong khoảng quan sát đã kiểm soát.
7. Gọi `resume()` và chờ consumer nhận backlog.
8. Xác nhận tất cả record được xử lý sau resume.

Với listener concurrency lớn hơn một, kiểm tra trạng thái pause của container endpoint và bảo đảm các consumer con đều không giao record mới. Không chỉ kiểm tra `isPauseRequested()` vì yêu cầu có thể chưa được áp dụng.

Nên kiểm thử thêm:

- Pause được gọi trong khi listener đang xử lý record.
- `pauseImmediate=true` với record listener và batch listener.
- Pause/resume nhiều lần và gọi resume khi container chưa pause.
- Container restart hoặc rebalance trong lúc pause.
- Backpressure controller có hysteresis, không pause/resume liên tục.
- Offset/acknowledgement không bị commit ngoài ý muốn.

Dùng `BlockingQueue`, `CountDownLatch` hoặc Awaitility để đồng bộ test. Tránh dùng `Thread.sleep` ngắn làm bằng chứng consumer đã pause; chờ trạng thái thực tế với timeout.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Vẫn nhận thêm vài record sau khi gọi pause | Yêu cầu pause được áp dụng trên consumer thread sau khi xử lý record đã poll | Chờ `isConsumerPaused()`; cân nhắc `pauseImmediate` |
| `isPauseRequested()` true nhưng consumer chưa paused | Consumer thread chưa xử lý yêu cầu | Theo dõi `isConsumerPaused()` và thời gian áp dụng |
| Một số listener vẫn chạy | Chỉ pause một endpoint hoặc bỏ sót container ngoài registry | Duyệt toàn bộ container thuộc phạm vi quản lý |
| Pause tất cả nhưng vẫn thấy backlog tăng | Producer/broker vẫn tiếp tục nhận record | Điều tiết upstream hoặc chấp nhận lag tăng trong thời gian pause |
| Consumer bị rebalance khi pause lâu | Container bị stop, poll loop không còn hoạt động hoặc có thay đổi group | Phân biệt pause với stop và kiểm tra poll/rebalance logs |
| Resume không thấy record ngay | Consumer chưa áp dụng resume hoặc partition chưa có record mới | Chờ trạng thái resume, kiểm tra assignment và lag |
| Pause/resume liên tục | Ngưỡng backpressure dao động quanh một giá trị | Dùng HIGH/LOW threshold, debounce và thời gian ổn định |
| Container restart rồi nhận record dù trước đó đã pause | Pause state là trạng thái runtime, không phải durable configuration | Lưu trạng thái điều phối bên ngoài nếu cần khôi phục sau restart |

## 16. Checklist vận hành

- [ ] Mỗi `@KafkaListener` cần điều khiển có `id` ổn định.
- [ ] Xác định đúng phạm vi container cần pause; không nhầm `id` với `groupId`.
- [ ] Dùng `KafkaListenerEndpointRegistry` cho endpoint được quản lý bằng annotation.
- [ ] Dùng `pause()`/`resume()` thay vì `stop()`/`start()` cho điều tiết tạm thời.
- [ ] Phân biệt `isPauseRequested()` và `isConsumerPaused()`.
- [ ] Hiểu record đã poll có thể tiếp tục được xử lý trước khi pause hoàn tất.
- [ ] Chỉ bật `pauseImmediate` khi semantics với record/batch listener đã được kiểm thử.
- [ ] Theo dõi consumer lag và thời gian pause.
- [ ] Có ngưỡng HIGH/LOW để tránh dao động trạng thái.
- [ ] Có quyền quản trị, audit và chính sách resume.
- [ ] Có integration test với concurrency thực tế.

## 17. Kết luận

Pause toàn bộ listener container cho phép tạm ngừng nhận record từ các partition mà endpoint quản lý, đồng thời giữ consumer hoạt động trong group và tiếp tục poll. Dùng `KafkaListenerEndpointRegistry` để lấy container theo listener ID hoặc duyệt `getListenerContainers()` để pause/resume tất cả endpoint được registry quản lý. Với `ConcurrentMessageListenerContainer`, yêu cầu pause trên container cha áp dụng cho các consumer con.

Lệnh pause/resume là yêu cầu thread-safe và được thực hiện trên consumer thread; hãy phân biệt `isPauseRequested()` với `isConsumerPaused()`. Mặc định, container xử lý xong record của poll hiện tại trước khi pause; `pauseImmediate` cho phép dừng sau record hiện tại với record listener. Pause không commit offset, không dừng producer và không ngăn backlog tăng trên broker. Hãy dùng nó như một cơ chế backpressure có giám sát, kết hợp metric, ngưỡng hysteresis, quyền điều khiển và kiểm thử để resume an toàn.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — KafkaListenerEndpointRegistry API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/config/KafkaListenerEndpointRegistry.html)
- [Spring for Apache Kafka — MessageListenerContainer API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/MessageListenerContainer.html)
- [Apache Kafka — KafkaConsumer pause/resume](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)
