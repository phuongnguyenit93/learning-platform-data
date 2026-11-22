# Tất cả subscriber nhận cùng message

## 1. Bài toán: một sự kiện, nhiều bên cùng quan tâm

Trong chương **PublishSubscribeChannel** của module **SPRING_INTEGRATION_CORE**, bài này giải thích cách phát một message tới nhiều subscriber và cách diễn giải đúng chữ “cùng”. Đây là nền tảng để ghép các endpoint thành luồng tích hợp bằng Java configuration và Java DSL.

Giả sử hệ thống bán hàng đã chấp nhận đơn `ORD-1042`. Ba nhu cầu phát sinh từ cùng sự kiện:

- Audit ghi nhận đơn đã được chấp nhận.
- Bộ phận thông báo tạo nội dung xác nhận cho khách.
- Bộ phận thống kê cập nhật số đơn theo ngày.

Nếu cả ba đều cần biết sự kiện, luồng phải phát tới cả ba nhánh. Việc chia mỗi đơn cho một trong ba nhánh sẽ không đáp ứng bài toán.

~~~mermaid
flowchart LR
    P["Producer: OrderAccepted"] --> C["PublishSubscribeChannel"]
    C --> A["Subscriber A: audit"]
    C --> N["Subscriber B: thông báo"]
    C --> S["Subscriber C: thống kê"]
~~~

`PublishSubscribeChannel` thực hiện broadcast tới các `MessageHandler` đang subscribe. Đây là channel đẩy message tới handler, không phải channel để consumer gọi `receive()` lấy message. [Tài liệu Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Sau bài học, bạn có thể:

1. Chọn broadcast khi nhiều chức năng cần cùng một sự kiện.
2. Phân biệt cùng sự kiện, cùng đối tượng `Message` và cùng đối tượng payload.
3. Đăng ký nhiều endpoint vào một channel bằng annotation hoặc Java DSL.
4. Giải thích giới hạn khi một subscriber lỗi, chạy chậm hoặc xử lý bất đồng bộ.
5. Viết kiểm thử quan sát được message tại từng nhánh.

## 2. “Tất cả subscriber” có nghĩa gì?

Một lần gọi `send(message)` tạo ra một lần phân phối tới tập subscriber của channel khi việc dispatch diễn ra. Subscriber là handler được nối trực tiếp với channel; một nhánh phía sau handler đó có thể chứa nhiều bước khác.

Trong ví dụ đơn hàng:

| Thành phần | Vai trò |
| --- | --- |
| Producer | Tạo message chứa sự kiện `OrderAccepted` |
| Channel | Phân phối sự kiện tới các subscriber |
| Endpoint audit | Nối channel với logic ghi audit |
| Endpoint thông báo | Nối channel với logic tạo thông báo |
| Endpoint thống kê | Nối channel với logic cập nhật thống kê |

Có ba điều cần phân biệt:

- **Đã được dispatch:** channel đã chuyển message cho handler hoặc giao tác vụ cho executor.
- **Đã xử lý xong:** logic của nhánh đã hoàn thành.
- **Đã tạo hiệu ứng nghiệp vụ:** chẳng hạn bản ghi audit đã commit hoặc email đã được hệ thống ngoài chấp nhận.

Ba mốc này có thể khác nhau. Khi thiết kế luồng, cần chỉ rõ mốc nào là điều kiện thành công của ca sử dụng.

Ví dụ, yêu cầu “đơn được chấp nhận sau khi ghi audit thành công” khác với “đơn được chấp nhận rồi hệ thống thông báo xử lý sau”. Từ sơ đồ broadcast đơn thuần chưa thể suy ra chính sách thành công cho cả hai yêu cầu.

## 3. Broadcast và phân chia công việc

`DirectChannel` có ngữ nghĩa point-to-point: mỗi message được xử lý bởi một subscriber được chọn, dù channel có nhiều subscriber. `QueueChannel` cũng phân phối mỗi message cho một consumer lấy được nó. Ngược lại, `PublishSubscribeChannel` dành cho việc nhiều handler cùng nhận một thông điệp. [So sánh các loại channel](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

| Tình huống thiết kế | Cách nối phù hợp |
| --- | --- |
| Audit, thông báo, thống kê cùng cần mọi sự kiện đơn hàng | Publish-subscribe |
| Ba worker làm cùng một loại việc để chia tải | Point-to-point |
| Sự kiện cần qua bước A, sau đó kết quả A đưa sang B | Chuỗi endpoint |
| Chọn nhánh xử lý theo loại đơn hoặc vùng giao hàng | Router |

Nếu ba worker cùng thực hiện “gửi email xác nhận”, broadcast có thể tạo ra ba email cho một đơn. Nếu ba chức năng khác nhau cùng cần biết sự kiện, việc chia tải lại làm thiếu chức năng.

Một topology kết hợp thường dễ diễn đạt hơn:

~~~text
                         -> audit
OrderAccepted -> pub-sub -> hàng đợi thông báo -> các worker gửi thông báo
                         -> thống kê
~~~

Ở thiết kế này, nhánh thông báo chỉ nhận một bản phân phối từ điểm broadcast. Việc chia tải giữa các worker được thực hiện phía sau ranh giới đó.

## 4. “Cùng message” có ba mức nghĩa

### 4.1. Cùng sự kiện nghiệp vụ

Audit và thống kê có thể cùng xử lý sự kiện `EVT-7301` dù message đã đi qua các transformer khác nhau. Vì thế, ví dụ xuyên suốt bài dùng `eventId` để định danh sự kiện nghiệp vụ.

`orderId` định danh đơn hàng; một đơn có thể phát sinh nhiều sự kiện. Do đó, dùng riêng `orderId` để chống xử lý lặp mọi loại sự kiện có thể loại nhầm các cập nhật hợp lệ.

### 4.2. Cùng đối tượng Message và cùng payload

Theo cấu hình mặc định `applySequence=false`, channel có thể đưa chính cùng đối tượng `Message` tới các subscriber. Khi bật `applySequence=true`, channel tạo các message có header sequence riêng cho từng subscriber nhưng vẫn dùng chung tham chiếu payload. Đây không phải thao tác deep copy dữ liệu nghiệp vụ. [Cấu hình PublishSubscribeChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html)

| Điều muốn kiểm tra | Phép kiểm tra minh họa |
| --- | --- |
| Hai nhánh xử lý cùng sự kiện nghiệp vụ | So sánh `eventId` |
| Hai biến trỏ tới cùng message | `assertSame(first, second)` |
| Hai message dùng chung payload | `assertSame(first.getPayload(), second.getPayload())` |

Kiểm tra identity của message thích hợp để học cơ chế dispatch trong một cấu hình cụ thể. Kiểm thử nghiệp vụ nên ưu tiên `eventId` và kết quả mong đợi của từng nhánh.

### 4.3. Message bất biến không làm toàn bộ dữ liệu bất biến

`GenericMessage` và cấu trúc `MessageHeaders` thông thường không cho thay payload hay sửa trực tiếp map header sau khi tạo. Tuy nhiên, đối tượng payload hoặc một giá trị header vẫn có thể là đối tượng mutable. Ứng dụng phải quyết định và bảo vệ tính bất biến của các đối tượng đó. [Hợp đồng Message và MessageBuilder](https://docs.spring.io/spring-integration/reference/7.0/message.html)

Ví dụ không nên dùng làm hợp đồng giữa các nhánh:

~~~java
// Giả sử payload là một Map mutable dùng chung.
payload.put("notificationStatus", "SENT");
~~~

Audit có thể nhìn thấy dữ liệu đã bị nhánh thông báo thay đổi. Nếu các nhánh chạy đồng thời, kết quả còn phụ thuộc thời điểm đọc và ghi.

Ví dụ dưới đây dùng record với các trường `String` và `BigDecimal`:

~~~java
import java.math.BigDecimal;

public record OrderAccepted(
        String eventId,
        String orderId,
        BigDecimal total) {
}
~~~

Lựa chọn kiểu dữ liệu này giúp ba nhánh cùng đọc sự kiện mà không cần chỉnh sửa nó. Nếu bổ sung collection vào record, cần cân nhắc bản sao và tính bất biến của cả phần tử bên trong; record không tự thực hiện deep copy.

Một transformer ở nhánh thông báo nên tạo payload đầu ra riêng, chẳng hạn chuỗi nội dung email. Audit và thống kê tiếp tục làm việc với sự kiện đầu vào của chúng.

## 5. Quan sát broadcast bằng Java thuần

Ví dụ này dùng `PublishSubscribeChannel` trực tiếp để nhìn thấy đối tượng message nhận tại từng handler. Giả sử project đã có `spring-integration-core`; record `OrderAccepted` ở phần trước nằm trong cùng package. Các ví dụ dùng cú pháp Java 17 trở lên.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class BroadcastDemo {

    public static void main(String[] args) {
        PublishSubscribeChannel events =
                new PublishSubscribeChannel(true);

        List<Message<?>> auditInbox = new ArrayList<>();
        List<Message<?>> notificationInbox = new ArrayList<>();
        List<Message<?>> statisticsInbox = new ArrayList<>();

        events.subscribe(message -> auditInbox.add(message));
        events.subscribe(message -> notificationInbox.add(message));
        events.subscribe(message -> statisticsInbox.add(message));

        OrderAccepted event = new OrderAccepted(
                "EVT-7301", "ORD-1042", new BigDecimal("350000"));

        Message<OrderAccepted> sent = MessageBuilder.withPayload(event)
                .setHeader("eventType", "OrderAccepted")
                .build();

        boolean accepted = events.send(sent);

        System.out.println("send=" + accepted);
        System.out.println("audit=" + auditInbox.size());
        System.out.println("notification=" + notificationInbox.size());
        System.out.println("statistics=" + statisticsInbox.size());

        System.out.println(
                "sameMessage=" + (
                        auditInbox.get(0) == sent
                        && notificationInbox.get(0) == sent
                        && statisticsInbox.get(0) == sent));
    }
}
~~~

Kết quả mong đợi:

~~~text
send=true
audit=1
notification=1
statistics=1
sameMessage=true
~~~

Ví dụ không truyền executor nên các handler thực thi trên thread gửi. Vì thế, sau khi `send` trả về bình thường, ba danh sách đã được cập nhật. Constructor nhận `true` bật `requireSubscribers`, giúp phát hiện trường hợp không có subscriber; tùy chọn này có từ Spring Integration 5.4.3. [API PublishSubscribeChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html)

Các danh sách trong ví dụ chỉ đóng vai trò hộp nhận để quan sát. Chúng không đại diện cho kho lưu sự kiện hay cơ chế giao nhận bền vững.

## 6. Nối ba endpoint bằng Java configuration

Trong ứng dụng Spring, endpoint đảm nhiệm việc đăng ký handler và gọi phương thức nghiệp vụ. Cấu hình sau minh họa ba service activator dùng chung một channel:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.channel.PublishSubscribeChannel;

@Configuration
@EnableIntegration
public class OrderEventsConfiguration {

    @Bean
    public PublishSubscribeChannel orderAcceptedEvents() {
        return new PublishSubscribeChannel(true);
    }

    @ServiceActivator(inputChannel = "orderAcceptedEvents")
    public void audit(OrderAccepted event) {
        System.out.println(
                "AUDIT: " + event.eventId() + " / " + event.orderId());
    }

    @ServiceActivator(inputChannel = "orderAcceptedEvents")
    public void notifyCustomer(OrderAccepted event) {
        System.out.println(
                "NOTIFY: đơn " + event.orderId() + " đã được chấp nhận");
    }

    @ServiceActivator(inputChannel = "orderAcceptedEvents")
    public void updateStatistics(OrderAccepted event) {
        System.out.println(
                "STATISTICS: cộng đơn có tổng tiền " + event.total());
    }
}
~~~

Ví dụ producer chạy sau khi application context đã khởi động:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class OrderEventPublisher {

    private final MessageChannel events;

    public OrderEventPublisher(
            @Qualifier("orderAcceptedEvents") MessageChannel events) {
        this.events = events;
    }

    public boolean publish(OrderAccepted event) {
        return events.send(
                MessageBuilder.withPayload(event).build());
    }
}
~~~

Đăng ký `OrderEventPublisher` thành bean nếu muốn Spring inject dependency. Các lệnh in chỉ biểu diễn điểm gọi logic nghiệp vụ; ứng dụng thực tế sẽ gọi dịch vụ audit, thông báo và thống kê tương ứng.

Các consumer ở đây trả về `void` vì ví dụ chỉ phát sự kiện. Nếu producer cần nhận một kết quả tổng hợp từ nhiều nhánh, hãy thiết kế rõ các reply, nơi gom và điều kiện hoàn tất thay vì suy ra kết quả từ việc gửi thành công.

Có thể đặt messaging gateway phía trước channel để lớp nghiệp vụ chỉ gọi một interface. Dạng phương thức `void publish(OrderAccepted event)` phù hợp với ý định phát sự kiện; bản thân gateway không thay thế cơ chế tổng hợp phản hồi.

## 7. Diễn đạt các nhánh bằng Java DSL

Ví dụ độc lập sau mô tả một flow có hai subscriber con và một nhánh tiếp tục sau điểm publish-subscribe. Chọn cấu hình này thay cho ví dụ annotation khi thực hành cùng một topology để tránh vô tình đăng ký thêm consumer.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderEventDslConfiguration {

    @Bean
    public IntegrationFlow orderAcceptedFlow() {
        return IntegrationFlow.from("orderAcceptedInput")
                .publishSubscribeChannel(subscribers -> subscribers
                        .subscribe(audit -> audit
                                .handle(message -> System.out.println(
                                        "AUDIT: " + message.getPayload())))
                        .subscribe(notification -> notification
                                .<OrderAccepted, String>transform(event ->
                                        "Đã nhận đơn " + event.orderId())
                                .handle(message -> System.out.println(
                                        "NOTIFY: " + message.getPayload()))))
                .handle(message -> System.out.println(
                        "STATISTICS: " + message.getPayload()))
                .get();
    }
}
~~~

Gửi message vào channel `orderAcceptedInput` sau khi context khởi động. Trong flow này:

1. Nhánh audit nhận sự kiện và kết thúc tại handler.
2. Nhánh thông báo biến sự kiện thành chuỗi rồi kết thúc tại handler của nó.
3. Handler thống kê nối sau `publishSubscribeChannel(...)` cũng nhận message qua điểm broadcast.

Nhánh tiếp tục đó không phải bước đợi hai nhánh con hoàn thành rồi gom kết quả. Cấu trúc subflow và nhánh tiếp tục được minh họa trong [tài liệu Java DSL về subflows](https://docs.spring.io/spring-integration/reference/dsl/java-subflows.html).

Transformer của nhánh thông báo phục vụ hợp đồng đầu ra riêng của nhánh đó. Không nên dùng sự thay đổi trong nhánh thông báo như cách truyền dữ liệu ngầm cho thống kê.

Nếu muốn ba nhánh hiện rõ dưới dạng ba lời gọi `subscribe(...)`, có thể đưa thống kê thành subscriber con thứ ba và kết thúc flow tại điểm publish-subscribe.

## 8. Đồng bộ, bất đồng bộ và lỗi

### 8.1. Broadcast đồng bộ vẫn có thể bị chặn giữa chừng

Với channel không có executor, các handler chạy lần lượt trên thread gửi. Theo mặc định `ignoreFailures=false`, lỗi từ một handler làm dispatch ném exception; những handler chưa được gọi có thể không nhận message. `setIgnoreFailures(true)` cho phép dispatcher tiếp tục khi handler lỗi, nhưng không sửa hay tự retry nghiệp vụ thất bại. [API về ignoreFailures](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html)

Giả sử trong một lần chạy, audit được gọi trước thông báo và thống kê:

~~~text
audit: thành công
thông báo: ném exception
thống kê: có thể chưa được gọi
~~~

Do đó, câu “tất cả subscriber nhận cùng message” mô tả ý định broadcast, có điều kiện thực thi. Nó không phải cam kết rằng mọi nhánh luôn thành công dù các nhánh khác lỗi.

Trong bài toán bán hàng, hãy xác định chính sách cho từng nhánh:

| Nhánh | Câu hỏi cần trả lời khi thiết kế |
| --- | --- |
| Audit | Nếu không ghi được audit, có được coi đơn đã chấp nhận không? |
| Thông báo | Có thể retry riêng nhánh này sau vài phút không? |
| Thống kê | Có thể tính lại từ nguồn dữ liệu nghiệp vụ không? |

Nếu cần quy trình bắt buộc “ghi audit xong mới gửi thông báo”, hãy biểu diễn thành các bước nối tiếp hoặc một quy trình điều phối. Không dựa vào thứ tự subscribe để mô tả phụ thuộc nghiệp vụ.

### 8.2. Executor thay đổi thời điểm quan sát

Có thể cấp một executor do Spring quản lý:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

// Các phương thức này đặt trong một lớp @Configuration.
@Bean
public ThreadPoolTaskExecutor orderEventExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(3);
    executor.setMaxPoolSize(6);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("order-event-");
    return executor;
}

@Bean
public PublishSubscribeChannel asyncOrderEvents(
        ThreadPoolTaskExecutor orderEventExecutor) {
    return new PublishSubscribeChannel(orderEventExecutor, true);
}
~~~

Đăng ký các consumer vào `asyncOrderEvents` khi dùng cấu hình này. Khi executor thực thi trên các worker thread, thời điểm `send` trả về không phải thời điểm mọi nhánh xử lý xong. Thứ tự hoàn thành giữa các nhánh cũng có thể khác nhau.

Đối với kiểm thử, thay `ArrayList` bằng cấu trúc an toàn khi truy cập đồng thời và chờ điều kiện hoàn tất có timeout. Không suy luận rằng nhánh đã thành công chỉ vì thread gửi đã đi qua câu lệnh tiếp theo.

Executor cũng cần chính sách khi đầy. Một message tạo công việc cho nhiều nhánh, nên cần tính tải theo tổng số tác vụ phát sinh và thời gian xử lý của từng nhánh. Với executor có chính sách chạy tác vụ trên thread gọi khi quá tải, không thể giả định mọi handler luôn chạy ở thread khác.

### 8.3. Quan sát lỗi bất đồng bộ

Trong cấu hình Spring thông thường dùng executor, `MessagePublishingErrorHandler` chuyển lỗi thành message tới channel trong header `errorChannel`, hoặc tới bean toàn cục `errorChannel` nếu header không có. Không có executor thì `ErrorHandler` của channel không thay thế việc exception quay về thread gọi. [Cấu hình xử lý lỗi của channel](https://docs.spring.io/spring-integration/reference/channel/configuration.html)

Ví dụ thiết kế vận hành cho nhánh thông báo:

~~~text
OrderAccepted
    -> nhánh thông báo
        -> gửi thành công: ghi nhận eventId đã xử lý
        -> gửi thất bại: lưu eventId, tên nhánh, nguyên nhân để retry
~~~

Để retry không tạo thông báo lặp, có thể dùng khóa nghiệp vụ `(eventId, tênNhánh)`. Cần xác định cách ghi nhận khóa phù hợp với hệ thống ngoài; việc kiểm tra khóa rồi gửi email không tự trở thành một giao dịch nguyên tử.

Nếu audit đã thành công trước khi thông báo lỗi, retry toàn bộ lần gửi có thể chạy audit thêm lần nữa. Vì thế, phạm vi retry cũng là một quyết định của thiết kế, không chỉ là thao tác gọi lại `send`.

## 9. Không có subscriber và ý nghĩa của send()

Mặc định `minSubscribers=0` cho phép một lần gửi không có subscriber vẫn được xem là thành công. `requireSubscribers=true` giúp phát hiện trường hợp channel không có handler. Còn `minSubscribers` diễn đạt ngưỡng số subscriber tối thiểu; khi dùng executor, kết quả này không chứng minh các tác vụ nghiệp vụ đã hoàn tất. [Ngữ nghĩa send và minSubscribers](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Ví dụ các mức yêu cầu khác nhau:

~~~java
// Phải có ít nhất một subscriber.
PublishSubscribeChannel events =
        new PublishSubscribeChannel(true);

// Đặt ngưỡng số lượng subscriber cho việc đánh giá lần dispatch.
events.setMinSubscribers(3);
~~~

Ngưỡng `3` không xác nhận đó chính là audit, thông báo và thống kê. Nếu cấu hình nhầm hai consumer thông báo và một consumer audit, đủ số lượng vẫn chưa đáp ứng yêu cầu nghiệp vụ.

Vì vậy, khi ứng dụng khởi động và trong kiểm thử tích hợp, cần kiểm tra topology bằng hành vi: phát một sự kiện có `eventId` xác định, rồi quan sát đầu ra của từng chức năng mong đợi.

## 10. Sequence header và việc gom kết quả

Nếu thiết kế yêu cầu gom kết quả từ các nhánh, có thể bật:

~~~java
PublishSubscribeChannel requests =
        new PublishSubscribeChannel(true);

requests.setApplySequence(true);
~~~

Channel bổ sung thông tin correlation và các header `sequenceNumber`, `sequenceSize` để các message của một lần phân phối có thể được liên hệ khi gom. Từng subscriber nhận message với số thứ tự riêng. [Cấu hình applySequence](https://docs.spring.io/spring-integration/reference/channel/configuration.html)

Ví dụ kiểm tra rủi ro trước khi chấp nhận đơn:

~~~text
OrderRiskRequest -> publish-subscribe
                     -> kiểm tra hạn mức -> RiskResult
                     -> kiểm tra địa chỉ -> RiskResult
                     -> kiểm tra gian lận -> RiskResult
                                             |
                                             v
                                   kênh kết quả chung
                                             |
                                             v
                                         aggregator
~~~

Để sơ đồ này có ý nghĩa trong ứng dụng, cần quyết định:

- Mỗi nhánh tạo bao nhiêu kết quả.
- Header liên hệ được giữ lại qua các bước biến đổi như thế nào.
- Kết quả lỗi có tham gia quyết định hay dẫn sang luồng xử lý riêng.
- Sau bao lâu thì một nhóm bị coi là thiếu kết quả.
- Nhóm thiếu dữ liệu được từ chối, chấp nhận một phần hay chuyển sang xử lý thủ công.

Nếu một filter loại message ở một nhánh mà không tạo kết quả thay thế, kỳ vọng “ba nhánh thì có ba kết quả” sẽ không còn đúng với đơn đó. Việc bật `applySequence` không tự tạo ra kết quả bị thiếu hoặc cấu hình aggregator.

Đối với ví dụ chỉ ghi audit, gửi thông báo và thống kê độc lập, không cần thêm aggregator chỉ để làm cho sơ đồ có bước kết thúc chung.

## 11. Kiểm thử minh họa ngữ nghĩa broadcast

Các kiểm thử JUnit 5 dưới đây tập trung vào hành vi tại ranh giới channel. Chúng là ví dụ để người học đưa vào project có `spring-integration-core` và JUnit Jupiter.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

import static org.junit.jupiter.api.Assertions.*;

class PublishSubscribeChannelTest {

    @Test
    void everySubscriberReceivesTheOriginalMessageByDefault() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel(true);

        List<Message<?>> first = new ArrayList<>();
        List<Message<?>> second = new ArrayList<>();
        List<Message<?>> third = new ArrayList<>();

        channel.subscribe(message -> first.add(message));
        channel.subscribe(message -> second.add(message));
        channel.subscribe(message -> third.add(message));

        Message<String> sent = new GenericMessage<>("EVT-7301");

        assertTrue(channel.send(sent));

        assertEquals(1, first.size());
        assertEquals(1, second.size());
        assertEquals(1, third.size());

        assertSame(sent, first.get(0));
        assertSame(sent, second.get(0));
        assertSame(sent, third.get(0));
    }

    @Test
    void sequenceCreatesSeparateEnvelopesWithTheSamePayload() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel(true);
        channel.setApplySequence(true);

        List<Message<?>> received = new ArrayList<>();
        channel.subscribe(message -> received.add(message));
        channel.subscribe(message -> received.add(message));

        Message<String> sent = new GenericMessage<>("EVT-7301");

        assertTrue(channel.send(sent));
        assertEquals(2, received.size());

        Message<?> first = received.get(0);
        Message<?> second = received.get(1);

        assertNotSame(sent, first);
        assertNotSame(sent, second);
        assertNotSame(first, second);

        assertSame(sent.getPayload(), first.getPayload());
        assertSame(sent.getPayload(), second.getPayload());

        assertEquals(2, first.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE));
        assertEquals(2, second.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE));

        assertNotEquals(
                first.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER),
                second.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER));

        assertNotNull(first.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID));
        assertEquals(
                first.getHeaders().get(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID),
                second.getHeaders().get(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID));
    }
}
~~~

Kiểm thử thứ nhất xác nhận đủ ba nhánh nhận message. Chỉ kiểm tra `send()==true` sẽ không chứng minh được điều đó.

Kiểm thử thứ hai xác nhận các message bọc riêng nhưng payload dùng chung. Nó không giả định nhánh nghiệp vụ nào phải nhận `sequenceNumber=1`.

Để kiểm thử luồng thực tế, thay các hộp nhận bằng đầu ra quan sát được của audit, thông báo và thống kê. Nên bổ sung các tình huống:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Một sự kiện hợp lệ | Mỗi chức năng tạo kết quả đúng cho cùng `eventId` |
| Một nhánh ném exception | Chính sách tiếp tục hoặc dừng đúng với yêu cầu |
| Không có subscriber | Cấu hình bắt buộc subscriber phát hiện lỗi |
| Gửi lại cùng sự kiện | Hiệu ứng nghiệp vụ lặp được kiểm soát |
| Có executor | Chờ đủ kết quả bằng điều kiện và timeout |
| Một nhánh lọc bỏ dữ liệu | Chính sách gom thiếu kết quả vẫn xác định được |

Các ví dụ này không cần Spring context để minh họa dispatcher đồng bộ. Kiểm thử annotation, DSL, gateway và vòng đời endpoint lại cần context tương ứng.

## 12. Bài tập áp dụng

Thiết kế luồng nhận `OrderAccepted` với ba nhánh:

1. Audit ghi `eventId` và `orderId`.
2. Thông báo chuyển sự kiện thành nội dung xác nhận.
3. Thống kê chỉ nhận đơn có `total >= 100000`.

Thực hiện hai lần gửi: đơn `50000` và đơn `350000`. Kết quả mong đợi:

| Nhánh | Đơn 50000 | Đơn 350000 |
| --- | --- | --- |
| Audit | Nhận sự kiện | Nhận sự kiện |
| Thông báo | Tạo thông báo | Tạo thông báo |
| Thống kê | Filter loại tại nhánh | Cập nhật thống kê |

Điểm cần giải thích là subscriber ở đầu nhánh thống kê vẫn có thể nhận sự kiện, sau đó filter bên trong nhánh mới loại nó. Điều đó không phủ nhận cơ chế broadcast của channel phía trước.

Tiếp theo, chủ động gây lỗi ở nhánh thông báo và mô tả kết quả với hai cấu hình:

- Channel đồng bộ, `ignoreFailures=false`.
- Channel dùng executor, có consumer xử lý lỗi.

Với mỗi cấu hình, ghi rõ producer quan sát được gì, nhánh nào đã hoàn thành và cách xử lý phần việc còn thiếu. Nếu yêu cầu nâng lên thành “chỉ chấp nhận đơn khi đủ kết quả từ ba kiểm tra”, hãy vẽ thêm luồng phản hồi và aggregator với chính sách timeout cụ thể.

## 13. Các quyết định cần giữ rõ khi dùng PublishSubscribeChannel

`PublishSubscribeChannel` mặc định là thành phần trong tiến trình. Nếu cần lưu sự kiện để consumer ngừng hoạt động có thể xử lý lại sau hoặc cần giao tiếp giữa các dịch vụ, hãy thiết kế thêm cơ chế lưu trữ hay kết nối messaging phù hợp với yêu cầu đó.

Trước khi dùng cho một luồng cụ thể, hãy trả lời:

- Mọi nhánh đều cần sự kiện, hay các worker chỉ đang chia tải cùng một công việc?
- Sự kiện và dữ liệu đính kèm có an toàn khi nhiều nhánh cùng đọc không?
- Một nhánh lỗi thì các nhánh khác phải tiếp tục, dừng hay bù trừ?
- Thành công của producer được định nghĩa tại mốc nào?
- Retry được thực hiện cho cả lần phát hay riêng một nhánh?
- Nếu cần kết quả chung, nơi nào gom và xử lý trường hợp thiếu phản hồi?

Với sự kiện đơn hàng trong bài, một hợp đồng rõ ràng là: producer phát `OrderAccepted`, ba chức năng cùng quan tâm tới `eventId` đó, mỗi chức năng chịu trách nhiệm về kết quả và chính sách lỗi của mình. Khi cần ràng buộc mạnh hơn, hợp đồng luồng phải thể hiện thêm ràng buộc ấy.