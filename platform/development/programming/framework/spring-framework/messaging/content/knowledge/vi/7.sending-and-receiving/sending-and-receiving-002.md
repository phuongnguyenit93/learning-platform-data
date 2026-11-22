# Đăng ký, hủy đăng ký và nhiều bộ xử lý trên cùng kênh trong Spring Messaging

## 1. Subscription giải quyết vấn đề gì?

Một channel là điểm giao tiếp giữa nơi gửi message và nơi nhận message. Với channel có thể đăng ký subscriber, ứng dụng có thể gắn một hoặc nhiều `MessageHandler` để xử lý message được gửi tới channel.

Trong Spring Messaging, abstraction quan trọng là `SubscribableChannel`. Interface này cho phép đăng ký và hủy đăng ký handler:

- `subscribe(handler)` thêm một handler vào danh sách subscriber.
- `unsubscribe(handler)` loại bỏ một handler đã đăng ký.

Cần phân biệt **có nhiều subscriber** với **một message được gửi tới tất cả subscriber**. Cách phân phối phụ thuộc implementation của channel. Có implementation broadcast message tới mọi subscriber; có implementation chọn một subscriber để xử lý mỗi message theo mô hình competing consumers.

Sự khác biệt này quyết định cách thiết kế. Nếu các handler làm những việc độc lập như ghi audit, cập nhật metric và gửi thông báo thì thường cần broadcast. Nếu nhiều worker cùng xử lý một loại công việc và mỗi message chỉ cần một worker nhận thì cần mô hình competing consumers.

Sau bài học, bạn cần có thể:

- Đọc được quan hệ giữa MessageChannel, SubscribableChannel và MessageHandler.
- Đăng ký, hủy đăng ký handler bằng đúng instance đã dùng.
- Phân biệt broadcast với competing consumers và polling.
- Hiểu lifecycle subscription, dispatch đồng bộ/bất đồng bộ và tác động của exception.
- Chọn implementation phù hợp và kiểm thử việc phân phối message.

## 2. Các abstraction cần hiểu

### 2.1 MessageChannel

`MessageChannel` là abstraction gửi message. Phương thức `send(Message<?>)` chuyển message tới channel. Người gửi chỉ cần biết channel đích, không cần gọi trực tiếp từng handler.

Channel có thể dispatch đồng bộ hoặc bất đồng bộ tùy implementation và cấu hình executor. Điều này ảnh hưởng đến thread thực thi, thứ tự hoàn tất, backpressure và cách exception được truyền về.

### 2.2 SubscribableChannel

`SubscribableChannel` mở rộng `MessageChannel` và cung cấp hai thao tác quản lý subscriber:

~~~java
boolean subscribe(MessageHandler handler);

boolean unsubscribe(MessageHandler handler);
~~~

Giá trị trả về cho biết thao tác đăng ký hoặc hủy đăng ký có được thực hiện hay không theo implementation. Khi đăng ký là điều kiện bắt buộc của ứng dụng, hãy kiểm tra kết quả thay vì mặc định subscription luôn thành công.

Subscriber là một `MessageHandler`. Handler nhận một `Message<?>` và xử lý qua phương thức `handleMessage`.

**Interface chỉ xác định khả năng đăng ký.** Nó không quy định mọi implementation phải broadcast cho tất cả subscriber. Cần xem semantics của channel cụ thể trước khi dựa vào số lượng handler.

### 2.3 PollableChannel

`PollableChannel` là mô hình nhận chủ động. Consumer gọi `receive()` hoặc `receive(timeout)` để lấy message. Nó không dùng subscription theo cách của `SubscribableChannel`.

Ví dụ, `QueueChannel` của Spring Integration thường được dùng khi producer đưa message vào hàng đợi và consumer chủ động lấy message ra. Vì vậy, không gọi `subscribe` trên một channel chỉ hỗ trợ polling.

## 3. Đăng ký nhiều handler với ExecutorSubscribableChannel

`ExecutorSubscribableChannel` thuộc Spring Messaging. Implementation này gửi message tới các subscriber đã đăng ký. Nếu không truyền executor, việc gọi handler diễn ra trực tiếp trên luồng gửi; nếu cấu hình executor, việc dispatch có thể diễn ra trên các thread do executor quản lý.

Ví dụ dưới đây dùng dispatch đồng bộ để kết quả dễ quan sát:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class SubscriptionDemo {

    public static void main(String[] args) {
        ExecutorSubscribableChannel channel =
                new ExecutorSubscribableChannel();

        MessageHandler auditHandler = message ->
                System.out.println("audit: " + message.getPayload());

        MessageHandler metricsHandler = message ->
                System.out.println("metrics: " + message.getPayload());

        channel.subscribe(auditHandler);
        channel.subscribe(metricsHandler);

        Message<String> event = MessageBuilder
                .withPayload("order.created")
                .build();

        channel.send(event);

        channel.unsubscribe(metricsHandler);
        channel.send(event);
    }
}
~~~

Kết quả với cấu hình mặc định không có executor:

~~~text
audit: order.created
metrics: order.created
audit: order.created
~~~

Hai subscriber đầu tiên cùng nhận message. Sau khi hủy `metricsHandler`, lần gửi tiếp theo chỉ còn `auditHandler` nhận message.

Thứ tự output trong ví dụ đồng bộ phản ánh thứ tự dispatch của implementation hiện tại. Nếu cấu hình executor, không nên phụ thuộc vào thứ tự bắt đầu hoặc hoàn tất của các handler.

Ví dụ dùng package `spring-messaging` của Spring Framework. Trong dự án Spring Boot, hãy để dependency management của phiên bản Boot đang dùng quản lý phiên bản Spring tương thích.

## 4. Hủy đăng ký đúng handler

Khi một handler không còn cần nhận message, gọi `unsubscribe` với chính instance đã đăng ký:

~~~java
MessageHandler handler = message ->
        System.out.println(message.getPayload());

channel.subscribe(handler);

// Khi cần dừng nhận message:
boolean removed = channel.unsubscribe(handler);
System.out.println("removed: " + removed);
~~~

Không tạo lambda mới khi gọi unsubscribe rồi kỳ vọng framework nhận ra đó là subscriber cũ:

~~~java
channel.subscribe(message -> process(message));

// Lambda dưới đây là một object khác:
channel.unsubscribe(message -> process(message));
~~~

Hai lambda có cùng phần thân vẫn là hai object riêng biệt. Hãy giữ tham chiếu handler trong field hoặc biến có vòng đời phù hợp.

Kết quả boolean của `unsubscribe` cũng hữu ích cho việc quan sát lifecycle. Nếu handler chưa được đăng ký hoặc đã bị hủy trước đó, implementation có thể trả về `false`.

## 5. Phân biệt broadcast và competing consumers

Đây là điểm dễ nhầm nhất khi có nhiều handler trên cùng một channel.

| Implementation | Cách phân phối | Một message được xử lý bởi |
|---|---|---|
| `ExecutorSubscribableChannel` (Spring Messaging) | Dispatch tới các subscriber | Tất cả subscriber |
| `DirectChannel` (Spring Integration) | Dispatcher chọn một subscriber theo load-balancing policy | Một subscriber được chọn |
| `PublishSubscribeChannel` (Spring Integration) | Phát tới các subscriber | Tất cả subscriber |
| `QueueChannel` (Spring Integration) | Consumer chủ động polling | Consumer lấy message khỏi queue |

### 5.1 Broadcast: mọi nhánh đều cần sự kiện

`PublishSubscribeChannel` phù hợp khi một sự kiện cần kích hoạt nhiều nhánh độc lập, chẳng hạn:

- Một nhánh ghi audit.
- Một nhánh cập nhật số liệu.
- Một nhánh gửi thông báo.
- Một nhánh cập nhật read model.

Mỗi subscriber nhận message theo chính sách dispatch của channel. Nếu cấu hình executor để chạy bất đồng bộ, thứ tự hoàn tất giữa các subscriber không được bảo đảm theo thứ tự đăng ký. Một subscriber lỗi cũng cần được xử lý theo chính sách exception và cấu hình của channel.

`ExecutorSubscribableChannel` của Spring Messaging cũng là một ví dụ về channel dispatch tới các subscriber đã đăng ký. Đừng suy rộng hành vi này sang mọi channel chỉ vì chúng đều có nhiều handler.

### 5.2 Competing consumers: một worker xử lý mỗi message

`DirectChannel` thuộc Spring Integration. Nó phù hợp với mô hình point-to-point. Nếu có nhiều subscriber, chúng hoạt động như các consumer cạnh tranh. Theo cấu hình mặc định phổ biến, dispatcher dùng chiến lược round-robin để chọn subscriber; chính sách failover cũng ảnh hưởng tới việc thử handler khác khi handler được chọn ném exception.

Ví dụ, ba worker cùng xử lý công việc gửi hóa đơn. Mỗi message chỉ cần một worker thực hiện. DirectChannel có thể phân phối lượt xử lý giữa các subscriber theo load-balancing policy.

### 5.3 Polling: consumer chủ động lấy message

`QueueChannel` thuộc Spring Integration lưu message trong queue nội bộ để consumer lấy ra bằng polling. Cách này tách thời điểm gửi và nhận. Nó không đồng nghĩa với broadcast: một message được lấy khỏi queue bởi consumer, không tự động được nhân bản cho tất cả consumer.

QueueChannel mặc định thường là queue trong bộ nhớ. Nếu cần persistence qua restart hoặc phân phối qua nhiều tiến trình, hãy chọn broker và adapter phù hợp.

### 5.4 Chọn theo yêu cầu nghiệp vụ

Hãy trả lời câu hỏi: “Một message phải kích hoạt tất cả nhánh hay chỉ một nhánh?” trước khi chọn channel.

- Sự kiện cần nhiều hệ thống nội bộ cùng quan sát: broadcast.
- Công việc chỉ cần một worker thực hiện: competing consumers.
- Producer và consumer cần tách thời điểm bằng queue: polling hoặc broker queue.
- Nhiều instance cần giao nhận bền vững: broker chuyên dụng với semantics đã được xác định.

Không chọn channel chỉ dựa trên số lượng handler hoặc tên gọi.

## 6. Khai báo channel trong Spring Integration

Spring Integration cung cấp các channel implementation với semantics khác nhau. Có thể khai báo channel qua bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ChannelConfiguration {

    @Bean
    public MessageChannel orderWorkChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel orderEventsChannel() {
        return new PublishSubscribeChannel();
    }
}
~~~

`orderWorkChannel` dùng cho công việc cần một subscriber được chọn. `orderEventsChannel` dùng cho sự kiện cần nhiều subscriber cùng nhận.

Endpoint có thể đăng ký vào channel bằng annotation hoặc Java DSL. Ví dụ:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class OrderWorker {

    @ServiceActivator(inputChannel = "orderWorkChannel")
    public void process(OrderCommand command) {
        // Gọi service nghiệp vụ để xử lý một đơn hàng.
    }
}
~~~

`OrderCommand` là kiểu payload thuộc ứng dụng. Method trên là phần minh họa endpoint; trong dự án thực tế, hãy inject service nghiệp vụ để xử lý lệnh.

Spring Integration tạo endpoint và quản lý subscription theo lifecycle của application context. Với endpoint do framework quản lý, không tự đăng ký thêm cùng handler nếu không có chủ đích, vì có thể khiến một message được xử lý lặp.

## 7. Quản lý lifecycle của subscriber

Một subscription thủ công cần có chủ sở hữu rõ ràng:

1. Tạo handler một lần.
2. Đăng ký khi component bắt đầu hoạt động.
3. Không đăng ký lại trong mỗi request hoặc mỗi lần xử lý message.
4. Khi component dừng, unsubscribe bằng đúng handler instance.
5. Nếu dispatch bất đồng bộ, cho task đang chạy thời gian hoàn tất phù hợp trước khi đóng executor hoặc tài nguyên liên quan.

Với bean có vòng đời cố định, có thể đăng ký ở giai đoạn khởi tạo và hủy ở giai đoạn shutdown bằng lifecycle callback phù hợp. Nếu component có thể start/stop nhiều lần, hãy bảo đảm mỗi lần start không tạo subscription trùng và mỗi lần stop chỉ hủy subscription do component đó sở hữu.

Unsubscribe thường ngăn các lần dispatch tiếp theo sau khi handler bị loại khỏi subscriber list. Nếu một message đã được submit vào executor, task đó có thể vẫn tiếp tục chạy. Không xem unsubscribe là thao tác hủy mọi công việc đang thực thi.

## 8. Dispatch đồng bộ và bất đồng bộ

### 8.1 Dispatch đồng bộ

Nếu channel gọi handler ngay trên thread gửi, producer có thể bị giữ lại cho tới khi handler hoàn tất. Điều này giúp luồng điều khiển dễ theo dõi và có thể đơn giản hóa việc truyền lỗi, nhưng một handler chậm sẽ làm chậm producer và các handler chạy sau nó.

Phù hợp khi:

- Công việc nhỏ và thời gian xử lý ổn định.
- Cần kết quả xử lý ngay trong cùng luồng.
- Cần thứ tự thực thi rõ ràng.
- Không cần tách tải sang executor.

### 8.2 Dispatch qua executor

Khi channel được cấu hình executor, việc gọi handler có thể diễn ra trên thread khác. Điều này có thể tăng throughput hoặc tách producer khỏi công việc xử lý, nhưng cần quản lý:

- Thứ tự bắt đầu và hoàn tất giữa các handler.
- Executor queue, thread count và rejection policy.
- Exception phát sinh ở thread xử lý.
- Shutdown và task đang chạy.
- Dữ liệu message được chia sẻ giữa các handler.

Không sửa payload hoặc headers sau khi message đã dispatch. Không mặc định bất đồng bộ luôn nhanh hơn; hãy đo độ trễ, throughput và số task tồn đọng.

## 9. Exception và độ tin cậy khi có nhiều subscriber

Với broadcast channel, một message có thể đi tới nhiều handler. Nếu một handler lỗi, những handler khác có thể đã chạy xong hoặc vẫn đang chạy. Không nên giả định toàn bộ broadcast là một transaction nguyên tử.

Thiết kế từng subscriber sao cho có thể phục hồi:

- **Idempotency:** cùng một sự kiện được xử lý lại không tạo tác dụng phụ lặp ngoài ý muốn.
- **Retry có giới hạn:** đặt số lần thử, khoảng chờ và điều kiện dừng.
- **Error flow hoặc dead-letter:** lưu message lỗi để phân tích và xử lý lại khi phù hợp.
- **Correlation ID:** liên kết log, trace và các message của cùng nghiệp vụ.
- **Timeout:** ngăn handler chờ tài nguyên vô hạn.
- **Isolation:** lỗi ở nhánh audit không nên vô tình làm mất dữ liệu ở nhánh nghiệp vụ quan trọng.

Với broker bên ngoài, semantics acknowledgement, retry, redelivery và dead-letter phụ thuộc broker và adapter. Channel trong bộ nhớ không tự cung cấp bảo đảm giao nhận bền vững.

## 10. Kiểm thử đăng ký và phân phối

Nên kiểm thử riêng các hành vi:

- Handler đăng ký thành công và nhận message.
- Hai subscriber của broadcast channel đều nhận cùng một message.
- Unsubscribe một handler khiến message gửi sau đó không còn được chuyển tới handler đó.
- DirectChannel chỉ chọn một subscriber cho mỗi message theo load-balancing policy.
- PublishSubscribeChannel phân phối tới mọi subscriber.
- Exception được xử lý theo chính sách đã cấu hình.
- Dispatch bất đồng bộ không khiến test giả định sai về thứ tự hoàn tất.
- Shutdown không để lại subscription hoặc task ngoài dự kiến.

Với test bất đồng bộ, dùng latch, future hoặc cơ chế đồng bộ của test thay vì sleep một khoảng thời gian tùy ý. Với Spring Integration, có thể khởi tạo application context để xác minh endpoint thực sự được đăng ký vào channel.

## 11. Các lỗi thường gặp

- **Tưởng nhiều subscriber luôn là broadcast:** DirectChannel của Spring Integration chọn một subscriber cho mỗi message.
- **Đăng ký handler lặp lại:** một component vô tình nhận cùng message nhiều lần.
- **Unsubscribe bằng lambda mới:** không loại bỏ đúng handler đã đăng ký.
- **Không quản lý lifecycle:** handler vẫn nhận message sau khi component cần dừng.
- **Cho rằng unsubscribe hủy task đang chạy:** task đã dispatch bất đồng bộ có thể tiếp tục hoàn tất.
- **Dùng broadcast cho công việc chỉ cần một worker:** cùng một nghiệp vụ có thể bị thực hiện nhiều lần.
- **Dùng DirectChannel khi mọi nhánh đều cần sự kiện:** chỉ một handler được chọn, các nhánh khác không nhận message.
- **Không kiểm soát exception:** lỗi một handler làm producer hoặc các nhánh khác bị ảnh hưởng ngoài dự kiến.
- **Không thiết kế idempotency:** retry hoặc redelivery tạo tác dụng phụ trùng lặp.
- **Giả định thứ tự subscriber:** executor có thể làm thay đổi thứ tự bắt đầu và hoàn tất.
- **Dùng channel trong bộ nhớ như broker bền vững:** message không tự tồn tại qua restart hoặc được phân phối giữa các tiến trình.

## 12. Checklist thiết kế

Trước khi triển khai nhiều handler trên cùng channel, hãy trả lời:

- Một message cần tới tất cả handler hay chỉ một handler?
- Implementation đang dùng là ExecutorSubscribableChannel, DirectChannel hay PublishSubscribeChannel?
- Handler có được đăng ký đúng một lần theo lifecycle không?
- Ứng dụng có giữ đúng tham chiếu để unsubscribe không?
- Handler có xử lý được message lặp và exception không?
- Dispatch đồng bộ hay bất đồng bộ? Thread và executor được quản lý ra sao?
- Các nhánh có cần thứ tự hoặc phụ thuộc kết quả của nhau không?
- Có correlation ID và log đủ để theo dõi từng nhánh không?
- Có kiểm thử cho đăng ký, hủy đăng ký, broadcast, competing consumers và shutdown không?
- Nếu cần durability hoặc phân phối qua nhiều instance, đã chọn broker phù hợp chưa?

Khi hiểu rõ subscription và semantics của từng implementation, bạn có thể thiết kế channel với nhiều handler mà vẫn kiểm soát được phạm vi xử lý, tải, lỗi và vòng đời của từng subscriber.