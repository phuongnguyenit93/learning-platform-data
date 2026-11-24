# Khai báo pollable-source và tạo PollableMessageSource

Spring Cloud Stream thường tiêu thụ message theo mô hình event-driven: binder nhận message từ broker rồi gọi Consumer hoặc Function ngay khi message đến. Trong một số ứng dụng, code cần chủ động quyết định khi nào lấy message, lấy bao nhiêu message trong một khoảng thời gian hoặc chỉ đọc khi hệ thống còn đủ tài nguyên xử lý. Pollable consumer đáp ứng nhu cầu đó bằng PollableMessageSource.

Để tạo pollable input binding theo functional model, khai báo thuộc tính spring.cloud.stream.pollable-source. Spring Cloud Stream tạo binding đầu vào tương ứng và cung cấp một implementation của PollableMessageSource để ứng dụng gọi poll(...). Ứng dụng quản lý lịch polling bằng @Scheduled, TaskScheduler hoặc một vòng lặp có kiểm soát. PollableMessageSource không phải một object mà ta tự tạo bằng new; binder tạo và kết nối nó với destination đã cấu hình.

## 1. Khi nào nên dùng pollable consumer?

Pollable consumer phù hợp khi ứng dụng cần điều khiển nhịp lấy message:

- Chỉ đọc khi một tài nguyên cục bộ còn khả năng xử lý, chẳng hạn worker slot hoặc connection pool.
- Giới hạn số message lấy trong mỗi chu kỳ để tránh làm quá tải database hoặc dịch vụ downstream.
- Kết hợp với một scheduler hoặc bộ điều phối riêng của ứng dụng.
- Chủ động xử lý từng message và quyết định cách xác nhận, từ chối hoặc đưa message trở lại broker.

Mô hình message-driven thông thường phù hợp hơn khi ứng dụng có thể xử lý message ngay khi broker giao đến và không cần điều khiển polling ở tầng ứng dụng. Polling thêm trách nhiệm về lịch, nhịp lấy dữ liệu, lỗi và acknowledgement cho code của ứng dụng. Chỉ chọn pollable consumer khi quyền kiểm soát đó đem lại lợi ích cụ thể.

## 2. Khai báo pollable-source

Giả sử ứng dụng cần chủ động đọc sự kiện đơn hàng từ destination orders.created. Cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      pollable-source: orders
      bindings:
        orders-in-0:
          destination: orders.created
          group: order-poller
          content-type: application/json
~~~

Thuộc tính spring.cloud.stream.pollable-source nhận tên logic của pollable source. Với giá trị orders, Spring Cloud Stream tạo binding có tên orders-in-0, theo quy ước binding của functional model. Binding đó trỏ đến destination orders.created và consumer group order-poller.

Phân biệt ba tên trong cấu hình:

| Giá trị | Vai trò |
|---|---|
| orders | Tên pollable source được khai báo trong spring.cloud.stream.pollable-source |
| orders-in-0 | Tên input binding mà ứng dụng dùng để cấu hình |
| orders.created | Destination vật lý trên broker, ví dụ Kafka topic hoặc tài nguyên tương ứng của binder |

Có thể khai báo nhiều pollable source bằng danh sách phân tách bởi dấu chấm phẩy, ví dụ orders;payments. Mỗi tên tạo binding đầu vào theo quy ước tương ứng, như orders-in-0 và payments-in-0. Khi có nhiều source, cần kiểm tra wiring để mỗi poller nhận đúng source của nó.

Không khai báo spring.cloud.function.definition chỉ để tạo pollable source này. Pollable consumer dùng trực tiếp PollableMessageSource, không cần một bean Consumer để framework tự động gọi theo sự kiện.

## 3. PollableMessageSource được tạo và inject như thế nào?

Sau khi binding được tạo từ cấu hình, binder cung cấp PollableMessageSource. Với một pollable source trong ứng dụng, có thể inject trực tiếp theo kiểu:

~~~java
import org.springframework.cloud.stream.binder.PollableMessageSource;
import org.springframework.stereotype.Component;

@Component
public class OrderPoller {
    private final PollableMessageSource source;

    public OrderPoller(PollableMessageSource source) {
        this.source = source;
    }
}
~~~

Ứng dụng không tự tạo implementation, không tự mở kết nối đến Kafka/RabbitMQ/Pulsar trong lớp này và cũng không cần tạo @Bean PollableMessageSource. Binder đảm nhiệm kết nối và cung cấp abstraction để ứng dụng gọi poll.

Nếu ứng dụng có nhiều pollable source, cần phân biệt từng binding khi inject để poller không đọc nhầm destination. Tên binding và cách qualifier được đăng ký có thể phụ thuộc phiên bản/framework configuration; hãy kiểm tra bean wiring trong context của ứng dụng và kiểm thử từng source riêng.

## 4. Gọi poll và xử lý một message

PollableMessageSource cung cấp phương thức:

~~~java
boolean poll(MessageHandler handler);
~~~

MessageHandler nhận một Spring Message. Kết quả true cho biết một message đã được nhận và xử lý thành công; false cho biết lần poll không lấy được message để xử lý. Callback được gọi đồng bộ trong quá trình poll.

Ví dụ xử lý một message:

~~~java
source.poll(message -> {
    OrderCreated event = (OrderCreated) message.getPayload();
    orderService.process(event);
});
~~~

Trong callback, ứng dụng đọc payload và gọi logic nghiệp vụ. Khi callback kết thúc bình thường, poll được xem là xử lý thành công và cơ chế acknowledgement mặc định sẽ xác nhận message theo binder. Nếu callback ném exception, lỗi được chuyển theo cơ chế error channel của pollable source; cách broker reject hoặc redeliver còn phụ thuộc binder và cấu hình lỗi.

### Gợi ý kiểu dữ liệu khi chuyển đổi payload

Có overload nhận ParameterizedTypeReference:

~~~java
boolean poll(MessageHandler handler, ParameterizedTypeReference<?> type);
~~~

Tham số type là conversion hint để message converter chuyển payload sang kiểu Java mong muốn. Ví dụ:

~~~java
source.poll(message -> {
    OrderCreated event = (OrderCreated) message.getPayload();
    orderService.process(event);
}, new ParameterizedTypeReference<OrderCreated>() {});
~~~

Với payload có generic lồng nhau, ParameterizedTypeReference giữ được thông tin kiểu đầy đủ:

~~~java
source.poll(message -> {
    Map<String, OrderLine> lines =
        (Map<String, OrderLine>) message.getPayload();
    orderService.processLines(lines);
}, new ParameterizedTypeReference<Map<String, OrderLine>>() {});
~~~

Hãy bảo đảm content-type của binding và định dạng message do producer phát ra tương thích với converter. Nếu consumer nhận dữ liệu thô hoặc dùng native deserializer của binder, conversion hint không thay thế cấu hình serializer/deserializer native.

## 5. Lên lịch polling bằng @Scheduled

Không nên gọi poll trong một vòng lặp không có thời gian chờ, vì khi broker không có message, ứng dụng sẽ liên tục hỏi broker và tiêu thụ CPU. Cách tích hợp Spring phổ biến là dùng @Scheduled:

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.cloud.stream.binder.PollableMessageSource;

@Component
public class OrderPoller {
    private final PollableMessageSource source;
    private final OrderService orderService;

    public OrderPoller(
            PollableMessageSource source,
            OrderService orderService) {
        this.source = source;
        this.orderService = orderService;
    }

    @Scheduled(fixedDelay = 500)
    public void pollOne() {
        source.poll(message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            orderService.process(event);
        }, new ParameterizedTypeReference<OrderCreated>() {});
    }
}
~~~

Bật scheduling trong ứng dụng:

~~~java
@SpringBootApplication
@EnableScheduling
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

fixedDelay tính thời gian chờ sau khi lần thực thi trước hoàn tất. Nếu xử lý message mất 200 ms và delay là 500 ms, lần poll kế tiếp bắt đầu sau khoảng 500 ms kể từ khi lần trước kết thúc. Khi lần poll không có message, scheduler vẫn chờ đến chu kỳ tiếp theo, không tạo busy loop.

Trong ví dụ, mỗi lần chạy chỉ gọi poll một lần nên tối đa một message được xử lý trong mỗi chu kỳ. Đây là cách đơn giản để giới hạn tốc độ tiêu thụ. Nếu cần tăng thông lượng, có thể gọi poll nhiều lần trong một lượt scheduler nhưng phải đặt giới hạn số message hoặc thời gian xử lý.

## 6. Lấy nhiều message trong một chu kỳ có giới hạn

Một poller có thể tiếp tục gọi poll trong khi còn message, nhưng nên đặt giới hạn để một lần chạy không chiếm scheduler vô thời hạn:

~~~java
@Scheduled(fixedDelay = 500)
public void pollBatch() {
    int processed = 0;
    int maxMessages = 20;

    while (processed < maxMessages) {
        boolean received = source.poll(message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            orderService.process(event);
        }, new ParameterizedTypeReference<OrderCreated>() {});

        if (!received) {
            break;
        }
        processed++;
    }
}
~~~

Giới hạn maxMessages giúp cân bằng giữa thông lượng và độ công bằng với các tác vụ khác. Nếu xử lý một message mất nhiều thời gian, cần cân nhắc thêm giới hạn tổng thời gian của một lượt polling. Không chạy vòng lặp vô hạn khi luôn có message, vì scheduler có thể không bao giờ hoàn thành lượt hiện tại.

Với message-driven consumer, binder chủ động đẩy message đến handler. Với pollable consumer, ứng dụng quyết định thời điểm gọi poll. Đây là khác biệt chính về quyền điều khiển; nó không có nghĩa pollable source tự động bảo đảm backpressure hoặc giới hạn mọi tài nguyên downstream.

## 7. Dùng ApplicationRunner thay cho scheduler

ApplicationRunner có thể dùng để khởi động một tác vụ polling do ứng dụng quản lý. Nếu chọn cách này, runner nên gửi công việc sang một executor có lifecycle do Spring quản lý rồi trả về; không chạy vòng lặp polling vô hạn trực tiếp trên thread của ApplicationRunner vì sẽ kéo dài giai đoạn hoàn tất startup.

Vòng lặp trên executor cần dừng khi ứng dụng shutdown, tôn trọng interrupt, chờ khi poll không có message và giới hạn số message trong mỗi lượt. Cũng cần ghi nhận lỗi để một exception không kết thúc tác vụ polling mà không ai biết. Với phần lớn ứng dụng, @Scheduled hoặc TaskScheduler dễ tích hợp, quan sát và quản lý lifecycle hơn một vòng lặp tự viết.

## 8. Acknowledgement mặc định và xử lý bất đồng bộ

Thông thường, poll xác nhận message khi MessageHandler kết thúc bình thường. Nếu callback kết thúc bất thường, message bị reject theo hành vi mặc định; message không nhất thiết được đưa lại queue. Hành vi redelivery và requeue phụ thuộc binder, broker và cấu hình error handling.

Nếu callback chỉ gọi xử lý đồng bộ:

~~~java
source.poll(message -> {
    OrderCreated event = (OrderCreated) message.getPayload();
    orderService.process(event); // Chỉ trở về khi nghiệp vụ đã hoàn tất
});
~~~

thì acknowledgement mặc định gắn với thời điểm callback kết thúc. Không nên khởi chạy công việc ở thread khác rồi trả callback ngay nếu công việc đó chưa hoàn tất; message có thể được ack trước khi nghiệp vụ thực sự thành công.

Nếu cần chuyển message sang thread khác hoặc xử lý bất đồng bộ, ứng dụng có thể chủ động quản lý acknowledgement thông qua callback trong header:

~~~java
source.poll(message -> {
    AcknowledgmentCallback acknowledgment =
        StaticMessageHeaderAccessor.getAcknowledgmentCallback(message);

    acknowledgment.noAutoAck();

    executor.execute(() -> {
        try {
            orderService.process((OrderCreated) message.getPayload());
            acknowledgment.acknowledge(AcknowledgmentCallback.Status.ACCEPT);
        }
        catch (Exception ex) {
            acknowledgment.acknowledge(AcknowledgmentCallback.Status.REQUEUE);
        }
    });
});
~~~

Đây là mẫu minh họa cho binder hỗ trợ acknowledgement callback tương ứng. Khi tắt auto-ack, ứng dụng bắt buộc phải ack hoặc nack/requeue sau khi xử lý; nếu quên, tài nguyên giao nhận có thể bị giữ lại và message không tiến triển. Kiểm tra semantics của ACCEPT, REJECT và REQUEUE theo binder cụ thể. Với Kafka, offset là tiến độ của log; requeue một message cũ có thể khiến các message đã ack sau đó được giao lại tùy cách binder quản lý offset.

Không dùng manual acknowledgement nếu xử lý đồng bộ đơn giản đã đáp ứng yêu cầu. Nó làm tăng độ phức tạp và cần xử lý trường hợp ứng dụng shutdown trong lúc công việc đang chạy.

## 9. Error channel và RequeueCurrentMessageException

Pollable source có error channel mặc định. Nếu callback ném exception, một ErrorMessage được gửi đến error channel theo tên dạng &lt;destination&gt;.&lt;group&gt;.errors; error channel này cũng được nối với Spring Integration errorChannel.

Có thể đăng ký @ServiceActivator để xử lý lỗi:

~~~java
@ServiceActivator(inputChannel = "orders.created.order-poller.errors")
public void handlePollingError(ErrorMessage errorMessage) {
    Throwable cause = errorMessage.getPayload();
    log.error("Cannot process a polled order message", cause);
}
~~~

Tên channel ví dụ dựa trên destination orders.created và group order-poller; hãy kiểm tra tên error channel thực tế do binder tạo. Nếu không có subscriber cho error channel, lỗi mặc định được ghi log và message có thể được xác nhận như xử lý thành công. Vì vậy, không nên mặc định rằng chỉ cần ném exception là broker sẽ tự redeliver.

Nếu error handler ném RequeueCurrentMessageException, message được đưa lại broker để lần poll sau có thể lấy lại. Listener cũng có thể ném trực tiếp exception này để yêu cầu requeue và bỏ qua error channel theo cơ chế được tài liệu hóa. Chỉ requeue lỗi có khả năng khắc phục; message sai schema hoặc dữ liệu nghiệp vụ không hợp lệ có thể tạo vòng lặp giao nhận liên tục. Với lỗi không thể xử lý, hãy dùng retry có giới hạn, DLQ hoặc parking-lot flow theo binder.

## 10. Pollable consumer và cấu hình binder

PollableMessageSource là abstraction chung, nhưng cách binder thực hiện poll và acknowledgement phụ thuộc broker:

| Binder | Điều cần lưu ý |
|---|---|
| Kafka | Poll lấy record từ consumer; offset/acknowledgement có quan hệ với thứ tự record trong partition và commit offset. Requeue một record có thể ảnh hưởng đến việc giao lại các record tiếp theo đã được xử lý. |
| RabbitMQ | Poll lấy message từ queue; ack, reject và requeue gắn với delivery của AMQP. Kiểm tra prefetch, dead-letter exchange và cấu hình retry của Rabbit binder. |
| Pulsar | Poll lấy message từ subscription; acknowledgement và redelivery phụ thuộc subscription, acknowledgement timeout và cấu hình client/binder. |

Không suy ra rằng một lệnh requeue hoặc một trạng thái acknowledgement có hành vi giống nhau trên mọi broker. Kiểm thử bằng binder thực tế trước khi dựa vào hành vi đó trong quy trình nghiệp vụ.

Các thuộc tính binding như destination, group, content-type, consumer.concurrency và các thuộc tính mở rộng của binder vẫn có vai trò. Tuy nhiên, PollableMessageSource để ứng dụng gọi poll; không nhầm nó với cấu hình poller của Supplier.

## 11. Phân biệt PollableMessageSource với poller của Supplier

Hai khái niệm đều có từ poll, nhưng chiều hoạt động khác nhau:

| Cơ chế | Hành vi |
|---|---|
| PollableMessageSource | Ứng dụng chủ động lấy message từ input destination bằng source.poll(...) |
| Poller của Supplier | Framework định kỳ gọi Supplier.get() để lấy dữ liệu và gửi ra output binding |

Các thuộc tính spring.integration.poller.fixed-delay, max-messages-per-poll và initial-delay điều khiển poller mặc định dùng để kích hoạt Supplier. Chúng không tự động đặt lịch gọi PollableMessageSource.poll(). Với pollable consumer, ứng dụng tự tạo lịch bằng @Scheduled, TaskScheduler hoặc cơ chế điều phối riêng.

## 12. Kiểm thử pollable source

Kiểm thử nên bao phủ cả binding lẫn hành vi polling:

- Khởi động application context với spring.cloud.stream.pollable-source và xác nhận binding &lt;name&gt;-in-0 được tạo.
- Xác nhận binding trỏ đến đúng destination và group.
- Gửi message hợp lệ rồi gọi poll; kiểm tra callback nhận đúng payload.
- Gọi poll khi không có message và xác nhận kết quả false.
- Dùng ParameterizedTypeReference để kiểm tra chuyển đổi DTO hoặc generic payload.
- Làm callback ném exception và xác nhận error channel nhận lỗi.
- Kiểm tra requeue, reject và acknowledgement với binder/broker thật.
- Kiểm tra scheduler không polling quá nhanh khi destination rỗng.
- Kiểm tra shutdown khi poller đang chạy hoặc callback đang xử lý.

Test Binder có thể giúp kiểm tra logic message và binding trong phạm vi ứng dụng. Nó không thay thế integration test với Kafka, RabbitMQ hoặc Pulsar khi cần xác nhận offset commit, ack/requeue, redelivery, DLQ và giới hạn polling thực tế.

## 13. Checklist triển khai

- [ ] Đã khai báo spring.cloud.stream.pollable-source với tên source rõ ràng.
- [ ] Đã cấu hình binding &lt;source-name&gt;-in-0 trỏ đến đúng destination.
- [ ] Đã cấu hình group ổn định nếu ứng dụng cần consumer group/subscription có tên.
- [ ] Đã inject PollableMessageSource do binder cung cấp; không tự tạo implementation.
- [ ] Đã chọn @Scheduled, TaskScheduler hoặc vòng lặp có kiểm soát.
- [ ] Đã xử lý trường hợp poll() trả về false mà không busy-loop.
- [ ] Đã chọn kiểu conversion phù hợp; dùng ParameterizedTypeReference khi cần.
- [ ] Callback chỉ kết thúc sau khi xử lý đồng bộ hoàn tất, hoặc đã quản lý manual acknowledgement đúng cách.
- [ ] Error channel, retry, reject, requeue và DLQ có chính sách rõ ràng.
- [ ] Đã kiểm thử với binder/broker production và xác nhận hành vi shutdown.

spring.cloud.stream.pollable-source tạo input binding cho một pollable consumer, còn PollableMessageSource là abstraction mà ứng dụng dùng để lấy message theo nhịp của mình. Khi khai báo đúng binding, inject source do binder cung cấp, đặt lịch polling có giới hạn và hiểu rõ acknowledgement/error channel, ứng dụng có thể kiểm soát tốc độ tiêu thụ mà vẫn duy trì quy trình giao nhận message có thể quan sát và kiểm thử.

## Tài liệu tham khảo

- [Spring Cloud Stream — Producing and Consuming Messages: Using Polled Consumers](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html#using-polled-consumers)
- [Spring Cloud Stream API — PollableMessageSource](https://docs.spring.io/spring-cloud-stream/docs/current/api/org/springframework/cloud/stream/binder/PollableMessageSource.html)
