# from MessageSource

Trong chương **Java DSL** của module **SPRING_INTEGRATION_CORE**, bài này trình bày cách dùng `IntegrationFlow.from(MessageSource<?>)` để khởi tạo luồng thông điệp từ một nguồn được thăm dò định kỳ. Đây là điểm nối giữa thao tác lấy dữ liệu ở bên ngoài và các thành phần cốt lõi như `Message`, `MessageChannel`, endpoint, filter và transformer.

Tình huống xuyên suốt là một hệ thống lấy đơn hàng đang chờ xử lý: nguồn tạo message có thông tin truy vết, poller điều khiển lịch lấy dữ liệu, còn flow kiểm tra và chuẩn hóa đơn hàng. Cách khởi tạo này phù hợp khi ứng dụng phải chủ động hỏi nguồn dữ liệu xem có phần tử mới hay chưa.

## 1. Mục tiêu và phạm vi

Sau bài học, bạn có thể:

- Cài đặt `MessageSource<T>` và giải thích đúng ý nghĩa của `receive()` trả về message hoặc `null`.
- Khai báo nguồn và `IntegrationFlow` bằng Java DSL, cấu hình poller và vòng đời endpoint.
- Phân biệt nguồn được poll với channel đầu vào, `Supplier` và adapter nhận sự kiện.
- Dự đoán số message trong một chu kỳ poll, vị trí thực thi downstream và cách lỗi được chuyển sang error channel.
- Thiết kế kiểm thử cho nguồn và luồng mà không phụ thuộc vào một khoảng `Thread.sleep()` tùy ý.

Ví dụ sử dụng Java 17 và API Spring Integration 6.x theo phong cách `IntegrationFlow.from(...)`. Môi trường chạy cần `spring-integration-core` cùng các thư viện Spring tương thích; phần kiểm thử dùng JUnit Jupiter. Hãy quản lý phiên bản bằng BOM hoặc cơ chế quản lý dependency của dự án.

Các ví dụ cấu hình dùng Spring thuần với `@EnableIntegration`, không yêu cầu Spring Boot. Những đoạn mã được ghi là “thay thế” là lựa chọn khác cho cùng vị trí cấu hình, không phải các flow cần chạy đồng thời.

## 2. MessageSource là nguồn được ứng dụng chủ động hỏi

`MessageSource<T>` thuộc package:

~~~java
import org.springframework.integration.core.MessageSource;
~~~

Hợp đồng nghiệp vụ chính của interface có dạng:

~~~java
Message<T> receive();
~~~

`T` là kiểu **payload**. Ví dụ, `MessageSource<Order>` nhận về `Message<Order>`; không khai báo thành `MessageSource<Message<Order>>` chỉ vì phương thức trả về một message.

Mỗi lần được gọi, nguồn có ba khả năng:

| Kết quả | Ý nghĩa | Hành vi mong đợi |
|---|---|---|
| Một `Message<T>` | Có dữ liệu để đưa vào luồng | Adapter gửi message sang channel tiếp theo |
| `null` | Lần thăm dò này chưa có dữ liệu | Không gửi message và kết thúc chu kỳ poll hiện tại |
| Ném exception | Thao tác lấy dữ liệu thất bại | Lỗi đi vào cơ chế xử lý lỗi của tác vụ polling |

Việc trả về `null` không đóng nguồn vĩnh viễn. Poller vẫn có thể gọi lại nguồn trong chu kỳ sau. Nguồn cũng không nên biến lỗi kết nối thành `null`, vì khi đó không còn phân biệt được “nguồn trống” với “không đọc được nguồn”. Hợp đồng trả về message hoặc `null` được mô tả trong [Javadoc MessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/core/MessageSource.html).

Interface này khác `org.springframework.context.MessageSource`, vốn dùng để tra cứu chuỗi thông báo và quốc tế hóa giao diện.

### 2.1. Tạo Message thay vì chỉ trả payload

~~~java
MessageSource<String> source = () ->
        MessageBuilder.withPayload("ORDER-101")
                .setHeader("sourceSystem", "legacy-order-system")
                .build();
~~~

Đoạn này cần import `org.springframework.integration.support.MessageBuilder`. Nó luôn tạo ra dữ liệu ở mọi lần gọi, nên cần giới hạn số message trong mỗi chu kỳ poll khi dùng thực tế.

Lợi ích của `MessageSource` là bạn kiểm soát cả payload lẫn header ngay tại biên vào hệ thống. Với nguồn đơn hàng, header có thể chứa tên hệ thống nguồn, khóa nghiệp vụ và mã đối soát. Dùng khóa nghiệp vụ ổn định để phát hiện xử lý trùng; không xem `MessageHeaders.ID` là khóa nghiệp vụ bền vững qua các lần đọc lại dữ liệu.

## 3. Những thành phần thực sự chạy ở đầu flow

Khai báo `from(source)` không có nghĩa bản thân nguồn sẽ tạo thread hoặc tự phát message. Flow cần một endpoint thực thi việc thăm dò:

~~~mermaid
flowchart LR
    T["Trigger và scheduler"] --> A["SourcePollingChannelAdapter"]
    A -->|"gọi receive()"| S["MessageSource"]
    S -->|"Message hoặc null"| A
    A -->|"chỉ gửi khi có Message"| C["MessageChannel"]
    C --> F["Filter"]
    F --> X["Transformer"]
    X --> Q["Channel kết quả"]
~~~

Có bốn trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| `MessageSource` | Biết cách lấy dữ liệu và dựng message |
| `SourcePollingChannelAdapter` | Gọi nguồn và gửi message vào flow |
| Poller | Mô tả lịch, số message tối đa và các tùy chọn polling |
| Các endpoint downstream | Xử lý message sau khi đã đi vào hệ thống |

Vì vậy, nguồn nên tập trung vào việc tiếp cận dữ liệu. Các bước lọc nghiệp vụ, chuẩn hóa, định tuyến hoặc gom nhóm có thể nằm trong flow để nhìn thấy và kiểm thử riêng.

Java DSL hỗ trợ trực tiếp `MessageSource` và cho phép cấu hình adapter qua tham số thứ hai của `from(...)`. Xem [Inbound Channel Adapters trong Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-inbound-adapters.html).

## 4. Cú pháp from(MessageSource)

Hai cách dùng chính là:

~~~java
IntegrationFlow.from(source)
~~~

và:

~~~java
IntegrationFlow.from(source, endpoint -> endpoint
        .id("orderInbound")
        .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                .maxMessagesPerPoll(5)))
~~~

Trong cách thứ hai:

- `source` là đối tượng `MessageSource<?>`.
- `endpoint` là `SourcePollingChannelAdapterSpec`, nơi cấu hình endpoint đầu vào.
- `poller(...)` cung cấp cấu hình thăm dò.
- Các lời gọi tiếp theo như `filter(...)`, `transform(...)` hay `handle(...)` mô tả phần xử lý downstream.
- `get()` hoàn tất builder để tạo đối tượng `IntegrationFlow` được đăng ký trong application context.

Một bean `MessageSource` đứng riêng chưa tự tạo lịch polling. Tương tự, một builder không được đăng ký thành flow trong context chưa tạo ra ứng dụng tích hợp đang hoạt động.

### 4.1. Phân biệt ID của flow và ID của adapter

~~~java
@Bean
IntegrationFlow orderPollingFlow(MessageSource<Order> source) {
    return IntegrationFlow.from(source, endpoint -> endpoint
                    .id("orderInbound")
                    .poller(Pollers.fixedDelay(Duration.ofSeconds(1))))
            .handle(message -> {
                // Xử lý message ở cuối luồng.
            })
            .get();
}
~~~

Bean flow có tên `orderPollingFlow`; endpoint đầu vào có ID `orderInbound`. Khi cần start hoặc stop riêng việc lấy dữ liệu, nên định danh adapter rõ ràng và thao tác với bean `SourcePollingChannelAdapter` tương ứng.

Ở đây, `Order` là kiểu dữ liệu nghiệp vụ được định nghĩa trong ví dụ đầy đủ phía dưới.

## 5. Ví dụ đầy đủ: lấy và chuẩn hóa đơn hàng

Mỗi message chứa một đơn hàng. Flow loại đơn có số lượng không hợp lệ, chuẩn hóa tên sản phẩm rồi đưa kết quả vào một `QueueChannel` để phía nhận hoặc kiểm thử đọc ra.

Các lớp trong ví dụ có thể đặt trong package `demo.integration`.

~~~java
package demo.integration;

import java.time.Duration;
import java.util.Locale;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.support.MessageBuilder;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class OrderPollingConfig {

    public record Order(String id, String product, int quantity) {
    }

    public static final class OrderInbox {

        private final Queue<Order> orders = new ConcurrentLinkedQueue<>();

        public void add(Order order) {
            orders.add(order);
        }

        public Order poll() {
            return orders.poll();
        }
    }

    @Bean
    OrderInbox orderInbox() {
        return new OrderInbox();
    }

    @Bean
    MessageSource<Order> orderMessageSource(OrderInbox inbox) {
        return () -> {
            Order order = inbox.poll();

            if (order == null) {
                return null;
            }

            return MessageBuilder.withPayload(order)
                    .setHeader("sourceSystem", "demo-orders")
                    .setHeader("businessKey", order.id())
                    .build();
        };
    }

    @Bean
    QueueChannel acceptedOrders() {
        return new QueueChannel(20);
    }

    @Bean
    QueueChannel orderPollingErrors() {
        return new QueueChannel(20);
    }

    @Bean
    IntegrationFlow orderPollingFlow(
            MessageSource<Order> orderMessageSource,
            @Qualifier("acceptedOrders") QueueChannel acceptedOrders) {

        return IntegrationFlow.from(orderMessageSource, endpoint -> endpoint
                        .id("orderInbound")
                        .autoStartup(false)
                        .poller(Pollers.fixedDelay(Duration.ofMillis(100))
                                .maxMessagesPerPoll(2)
                                .errorChannel("orderPollingErrors")))
                .<Order>filter(order -> order.quantity() > 0)
                .<Order, Order>transform(order -> new Order(
                        order.id(),
                        order.product().strip().toUpperCase(Locale.ROOT),
                        order.quantity()))
                .channel(acceptedOrders)
                .get();
    }
}
~~~

### 5.1. Tại sao cấu hình được viết như vậy?

`OrderInbox` là nơi chứa các đối tượng nghiệp vụ chưa đi vào hệ thống messaging. Nó dùng `ConcurrentLinkedQueue` để thao tác thêm và lấy an toàn giữa thread của bài kiểm thử và thread polling.

`orderMessageSource` chuyển một `Order` thành `Message<Order>`. Khi inbox rỗng, nó trả `null` ngay. Nguồn không cần biết filter hoặc transformer nào đang đứng sau mình.

`acceptedOrders` là `QueueChannel` chứa **message đã xử lý**. Nó khác queue trong `OrderInbox`, vốn chứa **đối tượng nghiệp vụ chưa được bọc thành message**.

Hai bean channel cùng kiểu `QueueChannel` nên tham số đầu ra có `@Qualifier` để chọn chính xác channel cần dùng. Việc truyền dependency qua tham số `@Bean` cũng tránh phụ thuộc vào lời gọi nội bộ giữa các phương thức cấu hình.

`autoStartup(false)` giữ adapter ở trạng thái dừng sau khi context được tạo, giúp nạp dữ liệu trước khi chạy kiểm thử. Khi muốn ứng dụng tự polling lúc khởi động, bỏ tùy chọn này hoặc đặt thành `true`.

`filter(...)` mặc định loại message không thỏa điều kiện mà không ném exception. Trong ví dụ, đơn bị loại đã được lấy khỏi inbox. Nếu cần đối soát đơn bị từ chối, hãy bổ sung discard channel và xử lý riêng thay vì coi chúng là lỗi kỹ thuật.

`QueueChannel(20)` chỉ dùng làm nơi quan sát kết quả và lỗi trong ví dụ hữu hạn. Ứng dụng chạy lâu phải có consumer đọc các channel này; nếu không, queue đầy có thể làm việc gửi bị chặn. Cách `QueueChannel` lưu message và hành vi chặn được mô tả tại [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

### 5.2. Diễn tiến một lần chạy

Giả sử inbox có thứ tự:

| Thứ tự | ID | Product | Quantity |
|---|---|---|---|
| 1 | `O-101` | `" keyboard "` | 2 |
| 2 | `O-102` | `"mouse"` | 0 |
| 3 | `O-103` | `" monitor "` | 1 |

Với `maxMessagesPerPoll(2)`:

1. Chu kỳ đầu lấy `O-101`, filter cho qua và transformer tạo sản phẩm `KEYBOARD`.
2. Trong cùng chu kỳ, nguồn được gọi lần nữa để lấy `O-102`. Filter loại message này.
3. Đã đạt hai message nhận được, nên chu kỳ đó kết thúc.
4. Chu kỳ tiếp theo lấy `O-103` và tạo sản phẩm `MONITOR`.
5. Lần gọi tiếp theo trả `null`, nên chu kỳ kết thúc sớm.
6. Những chu kỳ sau vẫn có thể chạy và nhận `null` nếu chưa có đơn mới.

Message bị filter loại vẫn được tính vào giới hạn nhận message của poller. Giới hạn này không phải số đơn hợp lệ cuối cùng phải xuất hiện ở channel kết quả.

## 6. Đọc đúng cấu hình poller

### 6.1. Chu kỳ poll khác với một lần receive()

Một chu kỳ poll có thể chứa nhiều lần gọi `receive()`. Với giới hạn dương, có thể hình dung luồng điều khiển bằng mã giả:

~~~text
khi trigger kích hoạt:
    lặp tối đa maxMessagesPerPoll lần:
        message = source.receive()
        nếu message == null:
            kết thúc chu kỳ hiện tại
        gửi message vào channel đầu tiên
~~~

Đây là mô hình giải thích trường hợp thông thường, bỏ qua advice, transaction và xử lý exception.

Trong `SourcePollingChannelAdapter`, giới hạn mặc định là một message mỗi chu kỳ nếu không bị cấu hình ghi đè. Giá trị âm cho phép tiếp tục nhận đến khi nguồn trả `null`; giá trị `0` khiến adapter bỏ qua việc gọi nguồn. Không nhầm mặc định của adapter này với `PollingConsumer` đọc từ channel. Xem [Channel Adapter: cấu hình poller](https://docs.spring.io/spring-integration/reference/6.5/channel-adapter.html).

| Giá trị | Khi nào nên cân nhắc | Điểm cần kiểm soát |
|---|---|---|
| `1` | Nguồn chậm hoặc muốn tải đều | Khả năng giải phóng tồn đọng có thể thấp |
| Một số dương hữu hạn | Muốn lấy nhiều message nhưng vẫn chặn kích thước mỗi lượt | Thời gian xử lý cả lượt tăng theo số message |
| Số âm | Muốn vét một nguồn chắc chắn có thời điểm hết dữ liệu | Nguồn luôn sinh message có thể giữ chu kỳ chạy rất lâu |
| `0` | Tạm ngưng nhận bằng cấu hình giới hạn | Không thay thế toàn bộ quản lý lifecycle |

Một nguồn như `() -> new GenericMessage<>("tick")` không bao giờ trả `null`. Nếu ghép với giới hạn âm, poller có thể liên tục tạo message trong cùng chu kỳ. Chọn giới hạn hữu hạn là quyết định quan trọng với loại nguồn này.

### 6.2. fixedDelay, fixedRate và cron

Các cấu hình sau là những lựa chọn thay thế:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(2))
        .maxMessagesPerPoll(10)
~~~

~~~java
Pollers.fixedRate(Duration.ofSeconds(2))
        .maxMessagesPerPoll(10)
~~~

~~~java
Pollers.cron("0 */5 * * * *")
        .maxMessagesPerPoll(10)
~~~

| Cách lập lịch | Cách hiểu |
|---|---|
| `fixedDelay` | Đặt khoảng chờ từ lúc tác vụ polling hoàn tất đến lượt tiếp theo trong cấu hình chạy trực tiếp, không chuyển tác vụ sang executor riêng |
| `fixedRate` | Tính nhịp theo các thời điểm bắt đầu dự kiến |
| `cron` | Chạy theo biểu thức lịch; ví dụ trên là mỗi năm phút ở giây thứ 0 |

Nên dùng `Duration` để thấy đơn vị ngay trong mã. Các overload nhận một `long` của `Pollers.fixedDelay` và `Pollers.fixedRate` sử dụng mili giây. Cách tính lịch được mô tả tại [Javadoc Pollers](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/Pollers.html).

`fixedRate` không tự tạo nhiều thread xử lý song song. Khi thêm `TaskExecutor` hoặc đổi scheduler, cần đánh giá lại khả năng tác vụ bị xếp hàng hoặc chồng lấn, tính an toàn của nguồn và thứ tự message.

### 6.3. Ước lượng thông lượng

Với nguồn luôn đủ dữ liệu, một poller chạy tuần tự, không executor riêng và downstream đồng bộ:

~~~text
thời gian một lượt ≈ tổng thời gian nhận và xử lý các message
chu kỳ thực tế ≈ thời gian một lượt + fixedDelay
thông lượng ≈ số message nhận được / chu kỳ thực tế
~~~

Ví dụ tự tính: mỗi lượt nhận 10 message; tổng thời gian đọc và xử lý là 800 ms; fixed delay là 1 giây. Thông lượng xấp xỉ:

~~~text
10 / (0,8 + 1) ≈ 5,56 message/giây
~~~

Do đó, không suy ra “10 message mỗi giây” chỉ từ `maxMessagesPerPoll(10)` và `fixedDelay(1 giây)`. Đây là phép ước lượng để lập giả thuyết đo đạc; dữ liệu trống, I/O, queue đầy và lỗi đều làm kết quả thay đổi.

### 6.4. Không dùng receiveTimeout để giới hạn một nguồn tùy ý

`MessageSource.receive()` không có tham số timeout. Nếu implementation gọi HTTP hoặc truy vấn database và bị kẹt, việc đổi khoảng poll không tạo ra deadline cho lời gọi đó.

Hãy cấu hình connect timeout, read timeout, query timeout hoặc cơ chế hủy phù hợp ở thư viện tiếp cận nguồn. `receiveTimeout` của polling consumer đọc channel và `sendTimeout` khi gửi sang channel là những khái niệm khác.

## 7. Poller riêng và poller mặc định

Cấu hình poller ngay trong `from(source, endpoint -> ...)` giúp nhìn thấy lịch lấy dữ liệu tại đúng flow sở hữu nguồn.

Nếu dùng overload chỉ nhận nguồn:

~~~java
IntegrationFlow.from(source)
~~~

thì context phải có default poller phù hợp. Không mặc định rằng flow này tự có lịch một giây khi context chưa khai báo poller mặc định.

Ví dụ cấu hình chung, cần import `PollerSpec`, `Pollers` và `org.springframework.integration.scheduling.PollerMetadata`:

~~~java
@Bean(name = PollerMetadata.DEFAULT_POLLER)
PollerSpec defaultPoller() {
    return Pollers.fixedDelay(Duration.ofSeconds(1))
            .maxMessagesPerPoll(3);
}
~~~

Đây là một `FactoryBean` tạo metadata poller. Khi khai báo `PollerSpec` bằng `@Bean`, trả về spec trực tiếp, không gọi `getObject()` trong phương thức bean. Xem [Java DSL: Pollers](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-pollers.html).

Default poller phù hợp khi nhiều endpoint có cùng chính sách. Với nguồn có hạn mức truy cập hoặc đặc tính tải riêng, nên cấu hình poller riêng để việc đổi cấu hình chung không vô tình thay đổi tải lên nguồn đó.

## 8. Một message không nhất thiết là một bản ghi

Nguồn trong ví dụ chọn mỗi lần `receive()` trả một `Order`. Một adapter khác có thể trả một message chứa cả `List<Order>`.

Giả sử nguồn trả:

~~~text
Message<List<Order>> với payload gồm 50 đơn hàng
~~~

Khi đó:

- `maxMessagesPerPoll(1)` chỉ giới hạn một message từ nguồn.
- Message ấy vẫn chứa 50 bản ghi.
- Các bước xử lý từng đơn cần một splitter trước khi filter hoặc transformer theo kiểu `Order`.

Ví dụ phần downstream trong trường hợp **payload đã là danh sách**:

~~~java
IntegrationFlow.from(batchSource, endpoint -> endpoint
                .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                        .maxMessagesPerPoll(1)))
        .split()
        .<Order>filter(order -> order.quantity() > 0)
        .channel("individualOrders")
        .get();
~~~

`batchSource` ở đây là một `MessageSource<List<Order>>` đã được định nghĩa; đoạn này minh họa cấu trúc thay cho nguồn trả từng đơn.

`maxMessagesPerPoll` không phải giới hạn số dòng SQL, kích thước trang HTTP hoặc số phần tử của payload. Các giới hạn đó thuộc implementation nguồn và thư viện adapter tương ứng.

## 9. Lựa chọn điểm bắt đầu flow

| Cách bắt đầu | Ai quyết định lúc có message? | Có poll nguồn bằng SourcePollingChannelAdapter? | Cách dùng điển hình |
|---|---|---|---|
| `from(MessageSource<?>)` | Lịch polling của ứng dụng | Có | Tự lấy dữ liệu và dựng cả message |
| `fromSupplier(...)` | Lịch polling của ứng dụng | Có | Tạo payload qua `Supplier` |
| `from("inputChannel")` với `DirectChannel` | Bên gửi gọi `send(...)` | Không | Nhận message từ một flow hoặc ứng dụng khác |
| `from(queueChannel)` với `QueueChannel` | Bên gửi đưa message vào queue, consumer lấy ra | Không poll nguồn; downstream dùng `PollingConsumer` | Đệm message đã có trong hệ thống |
| Adapter nhận callback hoặc sự kiện | Hệ thống bên ngoài hoặc client library | Tùy adapter; loại message-driven không poll theo cách này | Nhận message khi phía nguồn đẩy đến |

Phân biệt `PollingConsumer` và `SourcePollingChannelAdapter` giúp xác định đúng nơi cần poller. Hai cơ chế đều thăm dò, nhưng đối tượng được đọc là channel hoặc nguồn bên ngoài. Xem [Poller và Pollable Message Source](https://docs.spring.io/spring-integration/reference/6.5/polling-consumer.html).

### 9.1. Khi nào dùng fromSupplier?

Nếu không cần tự dựng header tại nguồn, một `Supplier` có thể làm mã ngắn hơn:

~~~java
Supplier<Order> nextOrder = inbox::poll;

IntegrationFlow.fromSupplier(nextOrder, endpoint -> endpoint
                .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                        .maxMessagesPerPoll(2)))
        .channel("rawOrders")
        .get();
~~~

Đoạn này cần `java.util.function.Supplier` và một `inbox` tương tự ví dụ trước. Giá trị payload trả về được framework bọc thành message; nếu chưa có dữ liệu, supplier có thể trả `null`. Khi cần dựng message có header ngay tại nguồn, `MessageSource` thể hiện ý định rõ ràng hơn. Cơ chế bọc kết quả supplier được mô tả tại [Inbound Channel Adapters](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-inbound-adapters.html).

Nếu lambda gây khó hiểu về overload hoặc kiểu dữ liệu, khai báo một biến `MessageSource<Order>` hoặc `Supplier<Order>` có kiểu rõ ràng rồi truyền biến đó vào API tương ứng.

## 10. Thread, channel và vòng đời

### 10.1. Polling không làm mọi bước downstream bất đồng bộ

Trong flow ví dụ, adapter polling khởi phát xử lý trên thread của tác vụ polling. Các bước filter và transformer nối qua channel đồng bộ nên hoàn tất trên thread đó trước khi gửi kết quả vào queue.

Khi một consumer khác đọc `acceptedOrders`, phần xử lý sau queue có thể chạy trên thread khác. Thời điểm adapter gửi thành công vào queue chỉ cho biết message đã được đưa vào queue, chưa chứng minh consumer sau queue đã xử lý nghiệp vụ xong.

Đặc tính này quyết định nơi đo độ trễ và nơi bắt lỗi. Ví dụ, thời gian chuẩn hóa sản phẩm được tính vào công việc của poller trong flow hiện tại; thời gian xử lý của một consumer đọc kết quả về sau thuộc phần việc khác.

### 10.2. Start và stop adapter

Với `autoStartup(false)`, có thể chủ động khởi động endpoint sau khi context được tạo:

~~~java
SourcePollingChannelAdapter adapter =
        context.getBean("orderInbound", SourcePollingChannelAdapter.class);

adapter.start();

// Khi muốn ngừng các lượt lấy dữ liệu tiếp theo:
adapter.stop();
~~~

Kiểu cần import là `org.springframework.integration.endpoint.SourcePollingChannelAdapter`.

Không giả định `stop()` sẽ cưỡng bức hủy ngay một lời gọi I/O đang chạy. Việc dừng có trật tự vẫn phụ thuộc vào khả năng hoàn tất, timeout hoặc hủy của thao tác lấy dữ liệu.

Việc adapter ngừng nhận thêm cũng không đồng nghĩa mọi message đã nằm trong các channel downstream đều được xử lý hết. Cần theo dõi riêng dữ liệu đang chờ và công việc đang thực thi.

## 11. Xử lý lỗi ở biên polling

Ví dụ đã cấu hình:

~~~java
.poller(Pollers.fixedDelay(Duration.ofMillis(100))
        .maxMessagesPerPoll(2)
        .errorChannel("orderPollingErrors"))
~~~

Cấu hình này đặt channel đích cho cơ chế công bố lỗi của poller. Với luồng ví dụ không đặt header `errorChannel` riêng, lỗi từ tác vụ polling được chuyển tới `orderPollingErrors` dưới dạng `ErrorMessage`.

| Nơi phát sinh | Ví dụ | Điều cần suy luận |
|---|---|---|
| Trong nguồn | Truy vấn thất bại trước khi tạo message | Có thể chưa có message gốc để gắn thông tin đơn hàng |
| Trong filter hoặc transformer đồng bộ | `product` là `null` làm chuẩn hóa thất bại | Lỗi quay lại tác vụ polling |
| Sau khi message đã được consumer khác lấy khỏi queue | Gọi dịch vụ giao hàng thất bại | Phải xử lý ở phạm vi consumer đó |
| Filter trả `false` | Đơn có số lượng bằng 0 | Đây là nhánh loại bỏ đã cấu hình, không tự trở thành lỗi |

`ErrorMessage` có payload là `Throwable`. Nếu đó là `MessagingException` và có `failedMessage`, có thể lấy thêm dữ liệu phục vụ đối soát; không giả định mọi lỗi đều có message nghiệp vụ. Cơ chế lỗi của tác vụ scheduled và ranh giới thread được trình bày tại [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

Trong ví dụ, test đọc trực tiếp error queue. Ở ứng dụng, hãy gắn một error flow hoặc consumer để ghi nhận nguyên nhân, khóa nghiệp vụ nếu có và quyết định xử lý tiếp.

### 11.1. Poll lần sau không đồng nghĩa retry message vừa lỗi

`inbox.poll()` xóa đơn khỏi queue trước khi filter và transformer chạy. Nếu transformer lỗi:

1. Đơn đã rời khỏi inbox.
2. Poller có thể phát error message.
3. Chu kỳ sau lấy đơn khác hoặc nhận `null`.
4. Đơn lỗi không tự xuất hiện trở lại.

Vì vậy, `errorChannel` cung cấp đường đi cho lỗi; nó không tự tạo cơ chế hoàn tác, lưu bền hoặc retry.

Cũng cần phân biệt retry việc **gọi nguồn lần nữa** với retry việc **xử lý đúng message đã nhận**. Nếu nguồn có tính tiêu thụ dữ liệu, gọi lại nguồn có thể lấy một phần tử khác. Chọn vị trí retry theo thao tác cần lặp, thay vì chỉ thêm retry ở nơi dễ cấu hình.

## 12. Thiết kế nguồn có khả năng phục hồi

Với dữ liệu cần bảo toàn qua lỗi hoặc khởi động lại, phải thiết kế cả hai câu hỏi:

- Khi nào nguồn xem dữ liệu đã được lấy hoặc xử lý thành công?
- Nếu có lỗi giữa lúc nhận và lúc hoàn tất nghiệp vụ, bằng cách nào tìm lại đúng dữ liệu?

Một số hướng thiết kế thường gặp:

| Đặc tính nguồn | Hướng xử lý |
|---|---|
| Database có trạng thái xử lý | Nhận quyền xử lý bản ghi một cách nguyên tử; quản lý trạng thái, retry và thời hạn quyền xử lý |
| API có cursor hoặc checkpoint | Lưu vị trí tiến độ ở mốc thành công phù hợp; chuẩn bị xử lý trùng khi đọc lại |
| Nguồn có acknowledgment | Dùng cơ chế xác nhận hoặc rollback mà adapter hỗ trợ |
| File hoặc đối tượng lưu trữ | Quản lý dấu vết đã xử lý và thời điểm di chuyển, đánh dấu hoặc xóa |
| Nhiều instance cùng đọc | Phân vùng, khóa hoặc cơ chế nhận quyền xử lý để hạn chế tranh chấp |

Đây là các lựa chọn thiết kế cần điều chỉnh theo hệ thống nguồn, không phải tính năng tự có của mọi `MessageSource`.

Transaction của poller có thể bao gồm việc nhận từ một tài nguyên hỗ trợ transaction. Tuy nhiên, thêm transaction không làm `ConcurrentLinkedQueue` trong ví dụ có khả năng rollback. Khi flow chuyển sang thread khác, transaction gắn với thread hiện tại cũng không tự theo sang đó. Xem [Transaction Support](https://docs.spring.io/spring-integration/reference/6.5/transactions.html).

Kết hợp lưu bền, xác nhận và xử lý idempotent thường quan trọng hơn việc chỉ rút ngắn khoảng poll. Một khóa như `businessKey` nên được đối chiếu với trạng thái xử lý được lưu bền nếu nghiệp vụ yêu cầu chống trùng qua các lần khởi động lại.

## 13. Kiểm thử nguồn và flow

Nên tách hai mức kiểm thử:

| Mức | Nội dung cần chứng minh |
|---|---|
| Nguồn độc lập | Trả `null` khi trống; tạo đúng payload và header khi có dữ liệu |
| Flow có context | Adapter chạy, downstream xử lý đúng, lỗi đi tới channel đã chọn |

Các test dưới đây đặt cùng package với `OrderPollingConfig`. Chúng dùng queue có timeout để chờ kết quả và đóng context sau mỗi test. Đây là mã minh họa kiểm thử, không phải kết quả đã chạy của một dự án cụ thể.

~~~java
package demo.integration;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.endpoint.SourcePollingChannelAdapter;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

import demo.integration.OrderPollingConfig.Order;
import demo.integration.OrderPollingConfig.OrderInbox;

import static org.junit.jupiter.api.Assertions.*;

class OrderPollingFlowTest {

    @Test
    void sourceReturnsNullWhenEmptyAndBuildsHeaders() {
        OrderInbox inbox = new OrderInbox();
        MessageSource<Order> source =
                new OrderPollingConfig().orderMessageSource(inbox);

        assertNull(source.receive());

        Order order = new Order("O-101", " keyboard ", 2);
        inbox.add(order);

        Message<Order> message = source.receive();

        assertNotNull(message);
        assertEquals(order, message.getPayload());
        assertEquals("demo-orders", message.getHeaders().get("sourceSystem"));
        assertEquals("O-101", message.getHeaders().get("businessKey"));
        assertNull(source.receive());
    }

    @Test
    void flowFiltersAndTransformsAcrossPollingCycles() {
        try (var context =
                     new AnnotationConfigApplicationContext(OrderPollingConfig.class)) {

            OrderInbox inbox = context.getBean(OrderInbox.class);
            QueueChannel accepted =
                    context.getBean("acceptedOrders", QueueChannel.class);

            inbox.add(new Order("O-101", " keyboard ", 2));
            inbox.add(new Order("O-102", "mouse", 0));
            inbox.add(new Order("O-103", " monitor ", 1));

            SourcePollingChannelAdapter adapter =
                    context.getBean("orderInbound", SourcePollingChannelAdapter.class);

            assertFalse(adapter.isRunning());
            adapter.start();

            Message<?> first = accepted.receive(3000);
            Message<?> second = accepted.receive(3000);

            assertNotNull(first);
            assertNotNull(second);
            assertEquals(new Order("O-101", "KEYBOARD", 2), first.getPayload());
            assertEquals(new Order("O-103", "MONITOR", 1), second.getPayload());
            assertEquals("O-101", first.getHeaders().get("businessKey"));
        }
    }

    @Test
    void transformationFailureIsPublishedToPollingErrorChannel() {
        try (var context =
                     new AnnotationConfigApplicationContext(OrderPollingConfig.class)) {

            OrderInbox inbox = context.getBean(OrderInbox.class);
            QueueChannel errors =
                    context.getBean("orderPollingErrors", QueueChannel.class);

            // quantity hợp lệ nên message đi tới transformer.
            inbox.add(new Order("O-999", null, 1));

            context.getBean("orderInbound", SourcePollingChannelAdapter.class)
                    .start();

            Message<?> failure = errors.receive(3000);

            assertNotNull(failure);
            assertInstanceOf(ErrorMessage.class, failure);
            assertInstanceOf(Throwable.class, failure.getPayload());

            // Nguồn của ví dụ đã lấy đơn ra, không tự đưa lại khi lỗi.
            assertNull(inbox.poll());
        }
    }
}
~~~

Test thứ hai quan sát hai kết quả nghiệp vụ đúng thứ tự. Nó kiểm tra việc flow tiếp tục lấy dữ liệu qua nhiều chu kỳ, không chứng minh chính xác thời gian giữa các chu kỳ.

Test thứ ba dùng dữ liệu sai để tạo lỗi downstream đồng bộ, đồng thời chỉ ra giới hạn phục hồi của nguồn trong bộ nhớ. Với nguồn thật, cần thêm tình huống lỗi ngay trong `receive()`, message bị đọc lại và khởi động lại ứng dụng.

Nếu cần điều khiển chính xác số lượt poll, có thể dùng trigger dành cho kiểm thử như `OnlyOnceTrigger` thay cho lịch định kỳ, cùng giới hạn message phù hợp. Spring Integration cũng cung cấp công cụ mock nguồn và endpoint trong [Testing support](https://docs.spring.io/spring-integration/reference/6.5/testing.html).

## 14. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Điểm kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| Context không khởi tạo được vì thiếu poller | Dùng `from(source)` nhưng chưa có default poller | Khai báo poller tại endpoint hoặc cung cấp default poller |
| Context chạy nhưng không thấy dữ liệu | `autoStartup(false)`, nguồn trống hoặc filter loại hết | Kiểm tra lifecycle, kết quả nhận và nhánh discard |
| CPU cao, nguồn bị gọi liên tục | Giới hạn âm với nguồn không trả `null` | Đặt giới hạn dương và xem lại hành vi nguồn |
| Chỉ có một message dù truy vấn trả nhiều dòng | Payload là một danh sách | Kiểm tra kiểu payload và thêm splitter nếu cần |
| Mất phần tử sau lỗi downstream | Nguồn xóa hoặc đánh dấu dữ liệu quá sớm | Thiết kế nhận quyền xử lý, xác nhận, checkpoint hoặc rollback |
| Chỉ thấy log ở error channel mặc định | Chưa chọn đúng channel hoặc lỗi xảy ra sau ranh giới bất đồng bộ | Xác định thread và consumer thực sự sở hữu lỗi |
| Polling bị đứng khi tải tăng | I/O không timeout hoặc channel đích đã đầy | Đo thời gian nhận, thời gian gửi và tốc độ consumer |
| Message bị xử lý nhiều lần khi chạy nhiều instance | Các instance cùng nhận một dữ liệu nguồn | Dùng khóa, phân vùng hoặc cơ chế nhận quyền xử lý phù hợp |

Để phân biệt nguồn trống với hệ thống bị nghẽn, nên quan sát số lần poll, số lần nhận `null`, số message nhận thành công, số lỗi, độ trễ xử lý và độ sâu queue. Những số đo này cần gắn với nguồn hoặc endpoint cụ thể để có thể truy ra nơi gây chậm.

## 15. Nguyên tắc áp dụng

`from(MessageSource)` phù hợp khi ứng dụng sở hữu nhịp lấy dữ liệu và cần biểu diễn dữ liệu nhận được dưới dạng message có payload, header rõ ràng.

Khi xây dựng flow thực tế, hãy giữ hợp đồng của nguồn đơn giản, cấu hình poller có chủ đích, phân biệt message với bản ghi trong payload và xác định chính xác thời điểm dữ liệu được coi là xử lý xong. Các quyết định về retry, transaction, acknowledgment và chống trùng phải bám vào đặc tính của nguồn cùng ranh giới thực thi của flow.
