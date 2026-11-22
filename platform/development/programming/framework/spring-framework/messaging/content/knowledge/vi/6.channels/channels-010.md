# Phân biệt lớp kênh của Spring Framework và Spring Integration

> Mục tiêu: phân biệt abstraction `MessageChannel` của Spring Framework với các channel implementation trong Spring Integration; hiểu kiểu gửi/nhận, cách dispatch, buffering, đồng bộ/bất đồng bộ và biết chọn channel phù hợp cho từng luồng xử lý.

## 1. Vì sao cần phân biệt hai lớp channel?

Trong ứng dụng hướng message, producer cần một nơi để gửi message và consumer cần một cơ chế nhận message. Spring cung cấp abstraction chung để các thành phần trao đổi mà không phải phụ thuộc trực tiếp vào cách một channel được cài đặt.

Spring Framework định nghĩa các interface cốt lõi như `MessageChannel`, `SubscribableChannel` và `PollableChannel`. Chúng mô tả hợp đồng gửi, đăng ký handler hoặc nhận message. Spring Integration sử dụng các abstraction đó và bổ sung nhiều implementation, cấu hình endpoint, adapter, router và DSL để xây dựng luồng tích hợp.

Điểm quan trọng: **`MessageChannel` là hợp đồng giao tiếp; `DirectChannel`, `QueueChannel`, `PublishSubscribeChannel` và các loại khác là những cách triển khai cụ thể.** Một channel trong ứng dụng không mặc nhiên là queue hoặc topic trên broker, cũng không tự tạo ra giao tiếp qua mạng.

## 2. Các abstraction channel trong Spring Framework

### 2.1. MessageChannel

`org.springframework.messaging.MessageChannel` là interface cơ bản để gửi một `Message<?>`. Hợp đồng chính có phương thức `send`, có thể truyền timeout:

```java
boolean send(Message<?> message);
boolean send(Message<?> message, long timeout);
```

Giá trị trả về `true` cho biết channel chấp nhận message theo hợp đồng của implementation. Nó không phải lúc nào cũng chứng minh consumer đã xử lý xong nghiệp vụ. Ý nghĩa cụ thể phụ thuộc channel: một channel đồng bộ có thể gọi handler trước khi `send` trả về; channel bất đồng bộ có thể chỉ xác nhận đã nhận công việc vào executor.

### 2.2. SubscribableChannel

`SubscribableChannel` mở rộng `MessageChannel` và cho phép handler đăng ký nhận message bằng `subscribe(MessageHandler)`. Khi message được gửi, implementation dispatch message đến một hoặc nhiều subscriber theo chính sách của nó.

Các channel kiểu này thường phù hợp với mô hình event-driven, nơi producer gửi message và handler đã đăng ký được gọi khi message đến.

### 2.3. PollableChannel

`PollableChannel` mở rộng `MessageChannel` và cung cấp các phương thức `receive`, bao gồm biến thể có timeout. Consumer chủ động lấy message khỏi channel thay vì được gọi trực tiếp qua subscription.

Mô hình poll phù hợp khi cần đệm message, kiểm soát nhịp tiêu thụ hoặc kết nối với poller. Một channel pollable có thể có giới hạn dung lượng; khi đầy, hành vi `send` phụ thuộc timeout và chính sách của implementation.

### 2.4. Spring Framework có cung cấp mọi channel implementation không?

Không nên đồng nhất interface trong `spring-messaging` với các channel của Spring Integration. Spring Framework cung cấp các hợp đồng cốt lõi và một số implementation phục vụ những module của framework. Spring Integration cung cấp bộ channel implementation và endpoint phong phú để xây dựng integration flow. Khi đọc package hoặc dependency, hãy xác định lớp đến từ `org.springframework.messaging` hay `org.springframework.integration`.

## 3. Spring Integration bổ sung điều gì?

Spring Integration dùng message channel làm điểm nối giữa producer và consumer, rồi bổ sung các thành phần để định tuyến và xử lý message:

- **Channel:** truyền message giữa các endpoint hoặc bean.
- **Message endpoint:** kết nối một handler với channel, ví dụ service activator, transformer, filter hoặc router.
- **Channel adapter:** kết nối luồng message với nguồn hoặc đích bên ngoài, ví dụ inbound adapter nhận message từ broker và outbound adapter gửi message ra ngoài.
- **Gateway:** cung cấp API gọi vào hoặc gọi ra một message flow, có thể hỗ trợ request–reply.
- **Router và filter:** chọn nhánh xử lý hoặc quyết định message có được chuyển tiếp không.
- **Transformer:** chuyển đổi payload hoặc headers.

Channel chỉ là một phần trong integration flow. Muốn kết nối broker, file system, HTTP endpoint hoặc hệ thống khác, ứng dụng cần adapter/gateway tương ứng và cấu hình transport. Đổi `DirectChannel` thành `QueueChannel` không tự động kết nối một broker.

## 4. Các channel implementation thường dùng trong Spring Integration

### 4.1. DirectChannel

`DirectChannel` là `SubscribableChannel` kiểu point-to-point. Khi producer gọi `send`, channel dispatch message đến một subscriber được chọn. Mặc định, việc dispatch diễn ra trong luồng gửi nên handler chạy đồng bộ và exception từ handler có thể truyền ngược về sender.

Đặc điểm:

- Thường chỉ một handler trong nhóm subscriber xử lý mỗi message.
- Nhiều subscriber có thể được dùng để chia tải theo chiến lược dispatch của channel.
- Không tạo hàng đợi lưu trữ message giữa sender và handler.
- Dễ phối hợp các bước xử lý đồng bộ và quan sát exception trong call stack.

Dùng `DirectChannel` khi cần chuyển message đến một handler và muốn xử lý ngay trong luồng gửi.

### 4.2. PublishSubscribeChannel

`PublishSubscribeChannel` phát một message đến nhiều subscriber. Nó phù hợp với mô hình một sự kiện cần kích hoạt nhiều nhánh độc lập, chẳng hạn sau khi đơn hàng được tạo thì gửi thông báo, cập nhật chỉ số và khởi chạy quy trình khác.

Nếu không cấu hình executor, subscriber thường được gọi trong luồng gửi. Khi có `TaskExecutor`, việc dispatch có thể diễn ra bất đồng bộ. Điều đó thay đổi cách exception truyền về sender và ranh giới transaction; cần xác định rõ chính sách lỗi.

Publish–subscribe trong channel này là phân phối trong phạm vi ứng dụng theo subscriber đã đăng ký. Nó không tự cung cấp lưu trữ bền vững hoặc khả năng phát lại như một broker.

### 4.3. QueueChannel

`QueueChannel` là `PollableChannel` có buffer. Sender đưa message vào hàng đợi; consumer gọi `receive` hoặc được poller lấy message ra sau đó.

Đặc điểm:

- Tách thời điểm gửi và nhận trong tiến trình.
- Có thể đặt capacity để giới hạn số message đang chờ.
- `send` có thể chờ đến khi có chỗ trống theo timeout; nếu không thể gửi trong thời gian cho phép, thao tác có thể thất bại.
- Consumer cần poll hoặc có endpoint/poller phù hợp để lấy message.
- Buffer mặc định nằm trong bộ nhớ của tiến trình, không phải kho lưu trữ bền vững qua restart.

Dùng `QueueChannel` khi cần đệm tải cục bộ hoặc tách nhịp producer và consumer trong cùng ứng dụng. Nếu cần message tồn tại sau khi ứng dụng dừng, hãy dùng broker hoặc store bền vững phù hợp.

### 4.4. PriorityChannel

`PriorityChannel` là một dạng queue channel lấy thứ tự ưu tiên làm cơ sở chọn message tiếp theo. Nó hữu ích khi một số message cần được xử lý trước message khác. Cần cung cấp cơ chế so sánh hoặc priority metadata phù hợp; không nên giả định message tự có thứ tự ưu tiên đúng nếu chưa định nghĩa.

Ưu tiên có thể khiến message độ ưu tiên thấp bị chờ lâu nếu message ưu tiên cao liên tục xuất hiện. Hãy cân nhắc fairness và giới hạn thời gian chờ.

### 4.5. RendezvousChannel

`RendezvousChannel` dùng cơ chế bàn giao đồng bộ giữa sender và receiver: sender không thể chỉ đặt message vào một buffer dài hạn rồi tiếp tục ngay; cần có receiver tham gia nhận message. Kiểu này hữu ích cho handoff trực tiếp khi hai phía cần gặp nhau tại thời điểm gửi/nhận, nhưng có thể làm sender bị chặn nếu không có receiver sẵn sàng.

### 4.6. ExecutorChannel

`ExecutorChannel` là channel kiểu subscription dispatch message qua `TaskExecutor`. Sender giao công việc cho executor, còn handler có thể chạy trên thread khác.

Đặc điểm:

- Tách luồng gửi và luồng xử lý.
- Có thể tăng song song, nhưng phải quản lý thread pool và queue capacity.
- Exception trong handler không nhất thiết truyền ngược về sender như `DirectChannel`.
- Thread-local context và transaction của sender không tự động được chuyển sang thread xử lý.

Dùng `ExecutorChannel` khi cần xử lý bất đồng bộ trong cùng ứng dụng và có chính sách executor, lỗi, retry phù hợp. Đừng dùng executor không giới hạn nếu tốc độ gửi có thể vượt tốc độ xử lý.

### 4.7. FluxMessageChannel

`FluxMessageChannel` kết hợp channel abstraction với mô hình reactive dựa trên Reactor `Flux`. Nó phù hợp với luồng message cần tương tác reactive và backpressure. Đây là lựa chọn chuyên biệt khi ứng dụng đã thiết kế theo reactive streams; không nên thay thế mọi channel bằng reactive channel chỉ vì muốn dùng API mới.

## 5. Bảng so sánh các loại channel

| Channel | Hợp đồng thường dùng | Phân phối | Buffer | Tính đồng bộ điển hình |
|---|---|---|---|---|
| `DirectChannel` | `SubscribableChannel` | Một subscriber được chọn | Không | Đồng bộ trên thread gửi |
| `PublishSubscribeChannel` | `SubscribableChannel` | Nhiều subscriber | Không phải queue buffer | Đồng bộ nếu không có executor; có thể async nếu cấu hình executor |
| `QueueChannel` | `PollableChannel` | Consumer poll message | Có | Sender/receiver tách thời điểm |
| `PriorityChannel` | `PollableChannel` | Consumer poll theo ưu tiên | Có | Sender/receiver tách thời điểm |
| `RendezvousChannel` | `PollableChannel` | Một receiver nhận handoff | Không có queue buffer thông thường | Bàn giao đồng bộ |
| `ExecutorChannel` | `SubscribableChannel` | Một subscriber được dispatch qua executor | Phụ thuộc executor | Bất đồng bộ điển hình |
| `FluxMessageChannel` | Reactive channel | Subscriber reactive | Theo reactive flow | Reactive, có thể phối hợp backpressure |

Bảng mô tả hành vi phổ biến. Một số chi tiết như chiến lược load balancing, failover, timeout và xử lý lỗi có thể thay đổi theo phiên bản Spring Integration và cấu hình cụ thể.

## 6. Ví dụ cấu hình channel trong Spring Integration

Có thể khai báo các channel bằng Java configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessageChannel;

import java.util.concurrent.Executors;

@Configuration
class MessagingChannelsConfiguration {
    @Bean
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel orderEvents() {
        return new PublishSubscribeChannel();
    }

    @Bean
    QueueChannel ordersBuffer() {
        return new QueueChannel(100);
    }

    @Bean
    MessageChannel asyncOrders() {
        return new ExecutorChannel(Executors.newFixedThreadPool(4));
    }
}
```

Đây là cấu hình minh họa các loại channel, không phải toàn bộ ứng dụng. Trong ứng dụng production, cần quản lý vòng đời executor bằng bean có lifecycle phù hợp, ví dụ cấu hình `ThreadPoolTaskExecutor` thành bean và inject vào `ExecutorChannel`, thay vì tạo executor không được quản lý.

Ví dụ một service activator nhận message từ channel:

```java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
class OrderHandler {
    @ServiceActivator(inputChannel = "ordersInput")
    public void handle(OrderCreated event) {
        // Xử lý đơn hàng trong handler.
    }
}
```

Trong ví dụ này, `ordersInput` là bean channel được Spring Integration tìm theo tên. Với `DirectChannel`, handler được gọi đồng bộ khi message được gửi vào channel. Cấu hình thực tế cần có dependency Spring Integration và các bean được component scan.

## 7. Gửi và nhận qua PollableChannel

Với `QueueChannel`, producer có thể gửi message vào buffer và consumer chủ động nhận message:

```java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

QueueChannel queue = new QueueChannel(10);

queue.send(MessageBuilder.withPayload("order-created").build());

Message<?> received = queue.receive(1000);
if (received != null) {
    System.out.println(received.getPayload());
}
```

Ví dụ này minh họa buffer trong bộ nhớ. Với message đã được gửi thành công và nhận trong thời gian chờ, stdout là:

```text
order-created
```

Nếu không có message trong thời gian timeout, `receive` trả về `null`. Nếu queue đầy, `send` có thể thất bại hoặc chờ tùy overload và timeout được dùng. Trong ứng dụng nhiều thread, sender và receiver cần phối hợp theo lifecycle thực tế; đoạn mã trên chỉ minh họa API.

## 8. Channel và broker destination là hai lớp khác nhau

Một channel của Spring Integration thường là điểm nối trong integration flow của một application context. Broker destination là tài nguyên thuộc hệ thống messaging bên ngoài, chẳng hạn JMS queue, RabbitMQ queue/exchange hoặc Kafka topic.

Adapter kết nối hai thế giới:

- **Inbound adapter:** nhận dữ liệu từ broker hoặc hệ thống bên ngoài rồi đưa vào channel trong ứng dụng.
- **Outbound adapter:** lấy message từ channel và gửi ra broker hoặc hệ thống bên ngoài.
- **Gateway:** có thể cung cấp request–reply qua ranh giới transport.

Ví dụ luồng: RabbitMQ inbound adapter → `DirectChannel` → service activator. Channel ở giữa giúp tách logic xử lý khỏi chi tiết nhận message từ RabbitMQ. Thay adapter bằng JMS hoặc một nguồn khác có thể giữ nguyên phần lớn handler nếu hợp đồng payload và headers được bảo toàn.

Tuy nhiên, channel nội bộ không tự cung cấp durability, acknowledgement của broker, consumer group, partition hoặc khả năng phát lại. Những đặc tính đó thuộc transport hoặc integration adapter và phải được cấu hình ở đúng lớp.

## 9. Chọn channel theo yêu cầu

Hãy bắt đầu từ câu hỏi về cách dispatch và vòng đời message:

- **Cần gọi một handler ngay trong luồng gửi:** chọn `DirectChannel`.
- **Cần phát một sự kiện đến nhiều handler trong ứng dụng:** chọn `PublishSubscribeChannel`.
- **Cần đệm message và để consumer poll khi sẵn sàng:** chọn `QueueChannel` hoặc `PriorityChannel`.
- **Cần handoff đồng bộ giữa sender và receiver:** cân nhắc `RendezvousChannel`.
- **Cần dispatch sang thread khác:** chọn `ExecutorChannel` và cấu hình executor có giới hạn.
- **Cần reactive streams và backpressure:** cân nhắc `FluxMessageChannel`.
- **Cần lưu message bền vững, giao tiếp qua tiến trình hoặc nhiều instance:** kết nối broker qua adapter phù hợp thay vì dựa vào channel in-memory.

Không chọn channel chỉ theo tên gọi. Hãy xem ai nhận message, có bao nhiêu subscriber, message có được buffer không, `send` có thể block không, exception đi đâu và message có còn sau khi tiến trình dừng không.

## 10. Những lưu ý về transaction, lỗi và tài nguyên

### Transaction

Với `DirectChannel`, handler chạy trong luồng gửi nên có thể tham gia transaction của luồng đó nếu các thành phần dùng cùng transaction manager và cấu hình phù hợp. Với `ExecutorChannel`, handler chạy trên thread khác nên transaction thread-bound của sender không tự động truyền sang. Với broker, transaction/acknowledgement cần cấu hình theo integration và broker.

### Exception

Ở channel đồng bộ, exception từ subscriber có thể truyền ngược về caller. Ở channel bất đồng bộ, sender thường không nhận exception phát sinh sau khi task đã được executor nhận. Cần error handler hoặc error channel để quan sát lỗi xử lý nền.

### Backpressure và dung lượng

`QueueChannel` có capacity; executor cũng có queue và giới hạn thread riêng. Nếu producer nhanh hơn consumer, buffer tăng đến giới hạn. Khi đó cần quyết định chờ, từ chối, giảm tốc độ gửi hoặc chuyển sang hạ tầng có khả năng lưu trữ phù hợp.

### Ordering

Thứ tự xử lý phụ thuộc channel và mức song song. Một `DirectChannel` gọi handler theo lần gửi; một executor có nhiều thread hoặc publish–subscribe nhiều subscriber có thể khiến thời điểm hoàn tất khác thứ tự gửi. Nếu thứ tự nghiệp vụ quan trọng, cần thiết kế khóa phân vùng, tuần tự hóa hoặc kiểm tra version trạng thái.

## 11. Lỗi thường gặp

- **Coi `MessageChannel` là một broker:** đây là abstraction gửi message trong ứng dụng, không nhất thiết có network hoặc persistence.
- **Coi mọi channel là queue:** `DirectChannel` và `PublishSubscribeChannel` là các kiểu dispatch subscriber, không phải buffer pollable.
- **Dùng `PublishSubscribeChannel` khi chỉ một consumer nên xử lý command:** nhiều subscriber có thể cùng nhận message và tạo side effect trùng.
- **Dùng `QueueChannel` rồi kỳ vọng message tồn tại sau restart:** queue channel mặc định là buffer trong bộ nhớ.
- **Dùng `ExecutorChannel` mà không giới hạn executor:** có thể tạo quá nhiều thread hoặc queue task không giới hạn.
- **Cho rằng exception luôn trả về sender:** điều này không đúng khi handler chạy bất đồng bộ.
- **Cho rằng transaction tự truyền qua executor:** transaction thread-bound không tự động đi theo task sang thread khác.
- **Quên cấu hình poller cho channel pollable:** message có thể nằm trong queue mà không có consumer lấy ra.
- **Nhầm channel nội bộ với queue/topic bên ngoài:** cần adapter để nối channel với broker.
- **Bỏ qua ordering và capacity:** tăng song song hoặc buffer mà không theo dõi tải có thể gây trễ và cạn tài nguyên.

## 12. Quy trình thiết kế một integration flow

1. Xác định producer, consumer và ranh giới giữa các thành phần.
2. Chọn hợp đồng channel phù hợp: `SubscribableChannel` hay `PollableChannel`.
3. Chọn dispatch model: unicast, publish–subscribe, queue/poll, executor hoặc reactive.
4. Quy định buffer capacity, timeout, executor, concurrency và chính sách khi quá tải.
5. Xác định exception đồng bộ hay bất đồng bộ và nơi nhận error message.
6. Nếu cần broker, chọn inbound/outbound adapter hoặc gateway tương ứng.
7. Kiểm thử số subscriber, thứ tự, timeout, channel đầy, handler lỗi và dừng ứng dụng.
8. Theo dõi throughput, queue depth, latency, thread pool và tỷ lệ lỗi trong vận hành.

## 13. Kết luận

Spring Framework cung cấp các abstraction channel như `MessageChannel`, `SubscribableChannel` và `PollableChannel` để định nghĩa hợp đồng gửi và nhận message. Spring Integration triển khai các channel cụ thể như `DirectChannel`, `PublishSubscribeChannel`, `QueueChannel`, `PriorityChannel`, `RendezvousChannel`, `ExecutorChannel` và `FluxMessageChannel`, đồng thời bổ sung endpoint và adapter để ghép thành integration flow.

Hãy chọn channel dựa trên cách dispatch, buffering, đồng bộ/bất đồng bộ, transaction, ordering và giới hạn tài nguyên. Khi cần giao tiếp liên tiến trình hoặc lưu message bền vững, kết nối broker qua adapter đúng công nghệ; channel nội bộ chỉ là một mắt xích trong luồng đó.