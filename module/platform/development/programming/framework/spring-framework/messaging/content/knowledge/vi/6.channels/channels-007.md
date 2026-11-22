# Đăng ký, hủy đăng ký và nhiều bộ xử lý trên cùng kênh trong Spring Messaging

## 1. Vai trò của subscription trong messaging

Một channel là điểm giao tiếp giữa nơi gửi message và nơi nhận message. Với channel có thể đăng ký subscriber, ứng dụng có thể gắn một hoặc nhiều `MessageHandler` để xử lý message được gửi tới channel.

Trong Spring Messaging, abstraction quan trọng là `SubscribableChannel`. Interface này cho phép đăng ký và hủy đăng ký handler:

- `subscribe(handler)` thêm một handler vào danh sách subscriber.
- `unsubscribe(handler)` loại bỏ một handler đã đăng ký.

Cần phân biệt việc **có nhiều subscriber** với việc **một message được gửi tới tất cả subscriber**. Cách phân phối phụ thuộc implementation của channel. Có implementation broadcast message tới mọi subscriber; có implementation chọn một subscriber để xử lý mỗi message theo mô hình competing consumers.

Đây là điểm quyết định khi thiết kế: nếu các handler làm những công việc độc lập như ghi audit, cập nhật metric và gửi thông báo thì thường cần broadcast. Nếu nhiều worker cùng xử lý một loại công việc và mỗi message chỉ cần một worker nhận thì cần mô hình competing consumers.

## 2. Các abstraction cần hiểu

### 2.1 MessageChannel

`MessageChannel` là abstraction gửi message. Phương thức `send(Message<?>)` chuyển message tới channel. Người gửi chỉ cần biết channel đích, không cần gọi trực tiếp từng handler.

Một channel có thể đồng bộ hoặc bất đồng bộ tùy implementation và cấu hình executor. Điều này ảnh hưởng đến thread thực thi, thứ tự hoàn tất, backpressure và cách xử lý exception.

### 2.2 SubscribableChannel

`SubscribableChannel` mở rộng `MessageChannel` và cung cấp hai thao tác quản lý subscriber:

~~~java
boolean subscribe(MessageHandler handler);

boolean unsubscribe(MessageHandler handler);
~~~

Giá trị trả về cho biết thao tác đăng ký hoặc hủy đăng ký có được thực hiện hay không theo implementation. Hãy kiểm tra kết quả khi việc đăng ký là điều kiện bắt buộc của ứng dụng.

Subscriber là một `MessageHandler`. Handler nhận một `Message<?>` và xử lý qua phương thức `handleMessage`.

### 2.3 PollableChannel

`PollableChannel` là mô hình nhận chủ động. Consumer gọi `receive()` hoặc `receive(timeout)` để lấy message. Nó không dùng subscription theo cách của `SubscribableChannel`.

Ví dụ, `QueueChannel` của Spring Integration thường được dùng khi producer đưa message vào hàng đợi và consumer chủ động lấy message ra. Vì vậy, không nên cố gọi `subscribe` trên một channel chỉ hỗ trợ polling.

## 3. Đăng ký nhiều handler

Ví dụ sau sử dụng `ExecutorSubscribableChannel` thuộc Spring Messaging. Implementation này phân phối message tới các subscriber của channel. Khi không truyền executor, việc gọi handler diễn ra trực tiếp trên luồng gửi.

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
    }
}
~~~

Với implementation mặc định chạy trực tiếp và hai subscriber được đăng ký theo thứ tự trên, kết quả là:

~~~text
audit: order.created
metrics: order.created
~~~

Hai handler nhận cùng một message. Mỗi handler có thể thực hiện một trách nhiệm riêng: audit lưu dấu vết, metrics ghi nhận số liệu, còn một handler khác có thể phát thông báo hoặc cập nhật projection.

Ví dụ sử dụng `spring-messaging` của Spring Framework. Nếu dùng Spring Boot, để dependency management của phiên bản Boot quản lý phiên bản Spring tương thích.

Không nên suy rộng hành vi broadcast của ví dụ này cho mọi implementation của `SubscribableChannel`. Interface xác định khả năng đăng ký; implementation quyết định cách dispatch.

## 4. Hủy đăng ký handler

Khi một handler không còn cần nhận message, gọi `unsubscribe` với chính handler đã đăng ký:

~~~java
boolean removed = channel.unsubscribe(metricsHandler);
System.out.println("removed: " + removed);

channel.send(event);
~~~

Kết quả của lần gửi sau khi hủy `metricsHandler`:

~~~text
audit: order.created
~~~

Hãy giữ tham chiếu tới handler đã đăng ký. Với lambda, không nên viết một lambda mới ở lời gọi unsubscribe rồi kỳ vọng framework nhận ra đó là cùng một subscriber:

~~~java
MessageHandler handler = message ->
        System.out.println(message.getPayload());

channel.subscribe(handler);

// Khi cần hủy, dùng đúng biến handler:
channel.unsubscribe(handler);
~~~

Một lambda mới có cùng phần thân vẫn là một object khác. Nếu không giữ tham chiếu handler, ứng dụng có thể không hủy được đúng subscription.

### 4.1 Khi nào cần unsubscribe?

Các trường hợp thường gặp:

- Một thành phần tạm thời chỉ cần nhận message trong một khoảng thời gian.
- Một listener được đăng ký thủ công khi component bắt đầu hoạt động.
- Một plugin hoặc module được nạp và tháo khỏi ứng dụng trong runtime.
- Một tài nguyên cần dừng nhận message trước khi ứng dụng shutdown.

Với bean Spring có vòng đời cố định, nên đăng ký một lần khi component được khởi tạo hoặc bắt đầu hoạt động, sau đó hủy khi component dừng. Không đăng ký lại handler trong mỗi lần gọi request hoặc mỗi lần xử lý message.

Nếu dùng Spring Integration endpoint như `@ServiceActivator(inputChannel = "...")`, framework quản lý lifecycle subscription của endpoint. Không tự đăng ký thêm cùng handler nếu không có chủ đích, vì một message có thể bị xử lý lặp.

## 5. Nhiều subscriber không đồng nghĩa với broadcast ở mọi channel

Đây là khác biệt quan trọng giữa các implementation trong hệ sinh thái Spring.

| Channel implementation | Nhiều subscriber được dùng thế nào? | Kết quả cho một message |
|---|---|---|
| `ExecutorSubscribableChannel` (Spring Messaging) | Dispatch tới các subscriber | Tất cả subscriber được gọi |
| `DirectChannel` (Spring Integration) | Các subscriber cạnh tranh nhận message; load balancer chọn một | Một subscriber được chọn |
| `PublishSubscribeChannel` (Spring Integration) | Phát message tới các subscriber | Tất cả subscriber được gọi |
| `QueueChannel` (Spring Integration) | Consumer chủ động polling | Consumer lấy message từ queue |

### 5.1 DirectChannel: một message cho một handler

`DirectChannel` thuộc Spring Integration. Nó phù hợp với mô hình point-to-point. Nếu có nhiều subscriber, các subscriber hoạt động như những consumer cạnh tranh. Theo cấu hình mặc định phổ biến, load balancer phân phối lượt xử lý giữa các subscriber; không phải mỗi message đều được gửi tới tất cả.

Ví dụ, ba worker cùng xử lý tác vụ gửi hóa đơn. Mỗi message chỉ cần một worker thực hiện. DirectChannel giúp phân phối công việc theo cấu hình load balancing và failover của channel.

### 5.2 PublishSubscribeChannel: broadcast

`PublishSubscribeChannel` cũng thuộc Spring Integration. Nó phù hợp khi một sự kiện cần kích hoạt nhiều nhánh độc lập, chẳng hạn:

- Một nhánh ghi audit.
- Một nhánh cập nhật số liệu.
- Một nhánh gửi thông báo.
- Một nhánh cập nhật read model.

Mỗi subscriber nhận message theo chính sách dispatch của channel. Nếu cấu hình executor để chạy bất đồng bộ, thứ tự hoàn tất giữa các subscriber không được bảo đảm theo thứ tự đăng ký. Một subscriber lỗi cũng cần được xử lý theo chính sách exception và cấu hình của channel.

### 5.3 Chọn theo ý nghĩa nghiệp vụ

Dùng broadcast khi mọi handler đều cần quan sát cùng một sự kiện. Dùng competing consumers khi một công việc chỉ cần được một worker xử lý.

Không chọn channel chỉ dựa trên số lượng handler. Hãy trả lời câu hỏi: “Một message phải kích hoạt tất cả nhánh hay chỉ một nhánh?” Sau đó mới chọn implementation phù hợp.

## 6. Ví dụ cấu hình channel trong Spring Integration

Khi dùng Spring Integration, có thể khai báo hai channel với semantics khác nhau:

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

`orderWorkChannel` dành cho công việc cần một consumer được chọn. `orderEventsChannel` dành cho sự kiện cần nhiều subscriber cùng nhận.

Các endpoint Spring Integration có thể đăng ký vào channel theo cấu hình annotation hoặc Java DSL. Ví dụ:

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

Method trên là phần minh họa endpoint. Trong ứng dụng thực tế, hãy dùng payload type và service nghiệp vụ đã định nghĩa. Spring Integration tạo endpoint và quản lý subscription theo lifecycle của application context.

Với channel broadcast, có thể có nhiều endpoint cùng đăng ký vào `orderEventsChannel`. Mỗi endpoint xử lý một trách nhiệm độc lập. Cần bảo đảm handler có thể xử lý việc cùng một sự kiện được phát tới nhiều nhánh.

## 7. Subscription và xử lý bất đồng bộ

### 7.1 Dispatch đồng bộ

Nếu channel gọi handler ngay trên thread gửi, producer có thể bị giữ lại cho tới khi handler hoàn tất. Điều này giúp luồng điều khiển dễ theo dõi và có thể đơn giản hóa việc truyền lỗi, nhưng một handler chậm sẽ làm chậm producer và các handler chạy sau nó.

Dùng dispatch đồng bộ khi:

- Công việc nhỏ và thời gian xử lý ổn định.
- Cần kết quả xử lý ngay trong cùng luồng.
- Muốn kiểm soát thứ tự thực thi một cách rõ ràng.
- Không cần tách tải sang executor khác.

### 7.2 Dispatch qua executor

Một số channel cho phép cấu hình executor để dispatch handler trên thread khác. Điều này có thể tăng throughput hoặc tách producer khỏi công việc xử lý, nhưng kéo theo các vấn đề:

- Thứ tự bắt đầu và hoàn tất giữa handler có thể khác nhau.
- Exception xảy ra ở thread khác không nhất thiết quay lại producer theo cách đồng bộ.
- Executor có thể đầy hoặc từ chối task.
- Cần giới hạn số thread, hàng đợi và thời gian shutdown.
- Dữ liệu message được chia sẻ giữa các handler; không sửa payload hoặc headers sau khi đã dispatch.

Không mặc định rằng bất đồng bộ đồng nghĩa với nhanh hơn. Hãy đo độ trễ, throughput, số task tồn đọng và khả năng chịu tải trước khi thay đổi executor.

## 8. Lỗi, retry và khả năng xử lý lặp

Với broadcast channel, một message có thể đi tới nhiều handler. Nếu một handler lỗi, những handler khác có thể đã chạy xong hoặc vẫn đang chạy. Không nên giả định toàn bộ broadcast là một transaction nguyên tử.

Thiết kế từng subscriber sao cho có thể phục hồi:

- **Idempotency:** cùng một sự kiện được xử lý lại không tạo tác dụng phụ lặp ngoài ý muốn.
- **Retry có giới hạn:** đặt số lần thử, khoảng chờ và điều kiện dừng.
- **Dead-letter hoặc error flow:** lưu message lỗi để phân tích và xử lý lại khi phù hợp.
- **Correlation ID:** liên kết log, trace và các message của cùng nghiệp vụ.
- **Timeout:** ngăn handler chờ tài nguyên vô hạn.
- **Isolation:** lỗi ở nhánh audit không nên vô tình làm mất dữ liệu ở nhánh nghiệp vụ quan trọng.

Với broker bên ngoài, semantics acknowledgement, retry, redelivery và dead-letter phụ thuộc broker và adapter. Một channel trong bộ nhớ không tự cung cấp bảo đảm giao nhận bền vững.

## 9. Quản lý vòng đời subscriber

Một subscription thủ công cần có chủ sở hữu rõ ràng:

1. Tạo handler một lần.
2. Đăng ký handler khi component bắt đầu hoạt động.
3. Không đăng ký trùng trong mỗi request.
4. Khi component dừng, hủy đăng ký bằng đúng handler đã dùng.
5. Nếu dispatch bất đồng bộ, cho các task đang chạy thời gian hoàn tất phù hợp trước khi đóng executor hoặc tài nguyên liên quan.

Nếu unsubscribe xảy ra khi một message đã được dispatch tới executor, task đã được submit có thể vẫn tiếp tục chạy. Hủy đăng ký thường ngăn các lần dispatch tiếp theo sau khi subscriber bị loại bỏ; nó không nên được xem là thao tác hủy mọi công việc đang chạy.

Với endpoint do Spring Integration quản lý, ưu tiên để application context quản lý start/stop của endpoint thay vì tự tạo subscription thủ công.

## 10. Kiểm thử subscription và dispatch

Nên kiểm thử các hành vi sau:

- Handler đăng ký thành công và nhận được message.
- Hai subscriber của broadcast channel đều nhận cùng một message.
- Unsubscribe một handler khiến message gửi sau đó không còn được chuyển tới handler đó.
- DirectChannel chỉ chọn một subscriber cho mỗi message theo load-balancing policy.
- PublishSubscribeChannel phân phối tới mọi subscriber.
- Một handler lỗi được xử lý theo chính sách đã cấu hình.
- Dispatch bất đồng bộ không làm code kiểm thử giả định sai về thứ tự hoàn tất.
- Shutdown không để lại subscription hoặc task không được quản lý.

Khi viết test cho xử lý bất đồng bộ, dùng latch, future hoặc cơ chế đồng bộ của test thay vì sleep một khoảng thời gian tùy ý. Với Spring Integration, có thể kiểm thử flow bằng channel và endpoint trong application context hoặc dùng test support tương ứng với phiên bản đang sử dụng.

## 11. Các lỗi thường gặp

- **Tưởng nhiều subscriber luôn là broadcast:** DirectChannel của Spring Integration chọn một subscriber cho mỗi message.
- **Đăng ký handler lặp lại:** một component vô tình nhận cùng message nhiều lần.
- **Unsubscribe bằng lambda mới:** không loại bỏ đúng handler đã đăng ký.
- **Không quản lý lifecycle:** handler vẫn nhận message sau khi module hoặc component cần dừng.
- **Cho rằng unsubscribe hủy task đang chạy:** task đã dispatch bất đồng bộ có thể tiếp tục hoàn tất.
- **Dùng broadcast cho công việc chỉ cần một worker:** cùng một nghiệp vụ có thể bị thực hiện nhiều lần.
- **Dùng DirectChannel khi mọi nhánh đều cần sự kiện:** chỉ một handler được chọn, các nhánh khác không nhận message.
- **Không kiểm soát exception:** lỗi một handler làm producer hoặc các nhánh khác bị ảnh hưởng ngoài dự kiến.
- **Không thiết kế idempotency:** retry hoặc redelivery tạo tác dụng phụ trùng lặp.
- **Giả định thứ tự subscriber:** executor có thể làm thay đổi thứ tự bắt đầu và hoàn tất.
- **Dùng channel trong bộ nhớ như broker bền vững:** message không tự tồn tại qua restart hoặc được phân phối giữa các tiến trình.

## 12. Checklist chọn và quản lý channel

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