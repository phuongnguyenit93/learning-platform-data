# @InboundChannelAdapter

## 1. Mục tiêu và phạm vi

Trong chương **Annotation và XML** của module **SPRING_INTEGRATION_CORE**, `@InboundChannelAdapter` là một cách tạo điểm bắt đầu cho luồng thông điệp bằng Java annotation. Nó phù hợp khi ứng dụng cần chủ động hỏi một nguồn dữ liệu theo lịch rồi đưa dữ liệu thu được vào một `MessageChannel`.

Sau bài học, bạn có thể:

- Phân biệt nguồn dữ liệu được polling với endpoint nhận thông điệp từ một kênh.
- Khai báo phương thức nguồn không có tham số và hiểu cách xử lý giá trị trả về.
- Chọn giữa phương thức POJO, bean `Supplier` và bean `MessageSource`.
- Cấu hình poller, lifecycle và đường xử lý lỗi.
- Viết kiểm thử cho nguồn dữ liệu và endpoint, đồng thời đọc được cấu hình XML/Java DSL tương đương.

Các ví dụ dùng Java 17, API Spring Integration 6.x và JUnit Jupiter. Phiên bản dependency cần theo BOM hoặc nền tảng Spring Boot tương thích của dự án. Phạm vi bài học là adapter gọi phương thức hoặc nguồn Java; từng adapter chuyên dụng như JDBC, file hoặc SFTP có thêm hợp đồng riêng.

## 2. Inbound được hiểu từ phía hệ thống tích hợp

Giả sử ERP cung cấp một API lấy đơn hàng mới. Ứng dụng phải gọi API định kỳ rồi chuyển từng đơn hàng vào luồng xử lý:

```text
ERP hoặc nguồn dữ liệu
        ^
        | gọi lấy dữ liệu theo lịch
        |
phương thức nguồn / MessageSource
        |
        v
SourcePollingChannelAdapter
        |
        v
ordersChannel
        |
        v
filter -> transformer -> router -> xử lý nghiệp vụ
```

“Inbound” nghĩa là dữ liệu đi **vào hệ thống thông điệp của ứng dụng**. Nguồn có thể là dịch vụ bên ngoài, một thư viện Java hoặc đối tượng được ứng dụng quản lý.

Khác với một service activator, phương thức nguồn không chờ một `Message` gửi đến để kích hoạt. Poller chủ động gọi nguồn. Kết quả khác `null` được đưa tới kênh đầu ra.

Trong cách dùng trên phương thức POJO, Spring Integration tạo `MethodInvokingMessageSource` để gọi phương thức, rồi đặt nguồn đó trong `SourcePollingChannelAdapter`. Xem [Using the @InboundChannelAdapter Annotation](https://docs.spring.io/spring-integration/reference/configuration/annotations.html#using-the-inboundchanneladapter-annotation).

### So sánh nhanh các vai trò

| Thành phần | Nhận kích hoạt từ đâu? | Công việc chính |
| --- | --- | --- |
| `@InboundChannelAdapter` | Poller gọi nguồn theo lịch | Đưa dữ liệu nguồn vào kênh |
| `@ServiceActivator` | Thông điệp có sẵn trên kênh đầu vào | Gọi nghiệp vụ xử lý thông điệp |
| `@BridgeFrom` | Thông điệp ở kênh nguồn | Chuyển tiếp sang kênh khác |
| Messaging gateway | Lời gọi qua hợp đồng gateway | Cung cấp giao diện đi vào/ra luồng, có thể request-reply |

Một bridge không thay nguồn ERP thành dữ liệu mới. Nó chỉ chuyển tiếp thông điệp đã có. Một inbound channel adapter là nơi bạn có thể bắt đầu tạo thông điệp từ kết quả đọc nguồn.

## 3. Cú pháp và hợp đồng của phương thức nguồn

Một phương thức nguồn tối giản:

```java
@InboundChannelAdapter(
    channel = "ordersChannel",
    poller = @Poller(fixedDelay = "1000")
)
public String nextOrderId() {
    return fetchNextOrderId();
}
```

Đoạn này giả định đối tượng chứa phương thức là bean do Spring quản lý và `fetchNextOrderId()` là thao tác đọc nguồn do ứng dụng cung cấp.

Ba điểm cần đọc đúng:

1. `channel` là tên **kênh đầu ra**, nơi adapter gửi thông điệp.
2. Phương thức nguồn POJO không nhận tham số và không có kiểu trả về `void`.
3. `poller` điều khiển việc gọi nguồn, kể cả khi kênh đầu ra là `DirectChannel`.

`value` và `channel` là hai alias của cùng thuộc tính. Có thể viết `@InboundChannelAdapter("ordersChannel")` khi dùng default poller, nhưng không khai báo hai alias với giá trị khác nhau.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `channel` / `value` | Tên bean kênh nhận thông điệp nguồn |
| `poller` | Lịch gọi nguồn và các tùy chọn polling |
| `autoStartup` | Cho endpoint tự chạy khi context khởi động; mặc định `"true"` |
| `phase` | Thứ tự lifecycle khi bắt đầu/dừng endpoint |

Định nghĩa annotation nằm trong [Javadoc của InboundChannelAdapter](https://docs.spring.io/spring-integration/docs/6.0.x/api/org/springframework/integration/annotation/InboundChannelAdapter.html).

### Vì sao phương thức nguồn không có tham số?

Tại thời điểm nguồn được gọi, chưa có thông điệp đầu vào để ánh xạ payload hoặc headers vào tham số. Vì vậy, đây không phải chỗ dùng `@Payload` hoặc `@Header` để nhận dữ liệu yêu cầu.

Các dependency như client ERP, repository hoặc cấu hình truy vấn cần được inject vào đối tượng nguồn bằng constructor hoặc cơ chế dependency injection thích hợp.

Quy tắc không có tham số áp dụng cho **phương thức POJO được polling**. Phương thức `@Bean` tạo một `Supplier` hoặc `MessageSource` có thể nhận dependency do container cung cấp; factory tạo bean và thao tác đọc nguồn là hai bước khác nhau.

## 4. Giá trị trả về quyết định thông điệp được phát

| Kết quả đọc nguồn | Hành vi |
| --- | --- |
| Một POJO khác `null`, chẳng hạn `String` hoặc `Order` | Tạo `Message` có đối tượng đó làm payload |
| Một `Message<?>` | Dùng thông điệp đã được nguồn xây dựng |
| `null` | Không gửi thông điệp cho lần nhận này; kết thúc việc lấy thêm trong lượt poll hiện tại |
| Một `List<Order>` khác `null` | Phát một thông điệp có payload là danh sách |
| Ném exception | Lượt polling thất bại và đi theo cấu hình xử lý lỗi |

`null` biểu thị “hiện không có dữ liệu”. Nó không tự dừng adapter vĩnh viễn. Đến lịch tiếp theo, poller vẫn có thể gọi nguồn.

Không trả về `Optional.empty()` để thay cho `null` với kỳ vọng framework tự bỏ qua. Trong hợp đồng nguồn thông thường, `Optional.empty()` vẫn là một đối tượng khác `null`. Tương tự, danh sách rỗng cũng chưa phải tín hiệu hết dữ liệu.

### Khi nào cần trả về Message?

Nếu chỉ cần mã đơn hàng, trả về `String` là đủ. Nếu muốn thêm metadata tại điểm nhập dữ liệu, hãy xây `Message`:

```java
return MessageBuilder
    .withPayload(orderId)
    .setHeader("sourceSystem", "erp")
    .setHeader("businessEventId", eventId)
    .build();
```

`businessEventId` là khóa nghiệp vụ do ứng dụng thiết kế, hữu ích khi cần đối chiếu hoặc chống xử lý trùng. Không mặc nhiên dùng header `id` được sinh cho từng message làm khóa nhận diện cùng một sự kiện qua nhiều lần đọc lại.

Nếu nguồn trả về danh sách và mỗi phần tử cần đi vào một nhánh riêng, hãy thêm splitter. Việc tăng `maxMessagesPerPoll` không tự tách danh sách thành nhiều thông điệp.

## 5. Ví dụ hoàn chỉnh với nguồn POJO

Ví dụ dùng bộ đệm trong bộ nhớ để mô phỏng nguồn đơn hàng. Nó cho phép kiểm thử mà không gọi ERP thật.

Tạo `OrderEventSource.java`:

```java
package example.integration;

import java.util.Objects;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.integration.annotation.EndpointId;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class OrderEventSource {

    private final Queue<String> pendingOrders =
        new ConcurrentLinkedQueue<>();

    public void offer(String orderId) {
        pendingOrders.add(Objects.requireNonNull(orderId));
    }

    @EndpointId("ordersInbound")
    @InboundChannelAdapter(
        channel = "ordersChannel",
        autoStartup = "false",
        poller = @Poller(
            fixedDelay = "100",
            maxMessagesPerPoll = "1"
        )
    )
    public Message<String> nextOrder() {
        String orderId = pendingOrders.poll();

        if (orderId == null) {
            return null;
        }

        return MessageBuilder
            .withPayload(orderId)
            .setHeader("sourceSystem", "demo-erp")
            .setHeader("businessEventId", "created:" + orderId)
            .build();
    }
}
```

Tạo `InboundOrderConfiguration.java`:

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class InboundOrderConfiguration {

    @Bean
    public QueueChannel ordersChannel() {
        return new QueueChannel(20);
    }

    @Bean
    public OrderEventSource orderEventSource() {
        return new OrderEventSource();
    }
}
```

`OrderEventSource` không cần `@Component` vì nó đã được đăng ký bằng `@Bean`. `@EnableIntegration` bật hạ tầng Integration cho ví dụ Java Configuration thuần. Dependency chính là `org.springframework.integration:spring-integration-core`.

Adapter được đặt `autoStartup = "false"` để người chạy chủ động thêm dữ liệu rồi khởi động endpoint. Vì vậy, chỉ tạo context sẽ chưa phát thông điệp. Trong ứng dụng muốn polling ngay khi khởi động, có thể bỏ thuộc tính này hoặc đặt thành `"true"`.

`@EndpointId("ordersInbound")` đặt tên cho endpoint polling, giúp điều khiển lifecycle mà không phải đoán tên được sinh tự động. Nó không đổi tên bean `orderEventSource` hoặc bean `ordersChannel`. Xem [Javadoc của EndpointId](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/EndpointId.html).

### Khởi động có kiểm soát

Sau khi context đã được tạo và refresh, có thể thao tác:

```java
OrderEventSource source = context.getBean(OrderEventSource.class);
source.offer("ORDER-1001");

SourcePollingChannelAdapter adapter = context.getBean(
    "ordersInbound",
    SourcePollingChannelAdapter.class
);

adapter.start();
```

Đoạn này cần import `org.springframework.integration.endpoint.SourcePollingChannelAdapter` và giả định `context` là application context của cấu hình trên.

Endpoint bắt đầu gọi `nextOrder()` theo lịch. Nó phát đơn hàng đầu tiên rồi nhận `null` khi bộ đệm hết dữ liệu. Endpoint vẫn hoạt động để nhận đơn hàng mới được thêm về sau.

Bộ đệm này chỉ phục vụ minh họa. Một lệnh `poll()` đã lấy phần tử khỏi bộ nhớ; nếu gửi tiếp thất bại thì ví dụ không tự phục hồi phần tử đó.

## 6. Poller: lịch gọi và số lần nhận trong một lượt

Với nguồn đọc chủ động, cần có poller riêng hoặc default poller được đăng ký trong context. Không thể bỏ poller chỉ vì kênh đầu ra là `DirectChannel`.

### fixedDelay, fixedRate và cron

| Cách đặt lịch | Ý nghĩa sử dụng |
| --- | --- |
| `fixedDelay = "1000"` | Nghỉ 1.000 mili giây sau khi lượt trước hoàn tất rồi chạy lượt tiếp |
| `fixedRate = "1000"` | Đặt chu kỳ theo các thời điểm bắt đầu được lập lịch |
| `cron = "0 */5 * * * *"` | Lập lịch tại giây 0, mỗi năm phút theo biểu thức cron của Spring |

Chọn một cơ chế lập lịch cho một poller. Không đặt đồng thời `fixedDelay`, `fixedRate` và `cron` để cố cộng gộp các lịch.

Nếu một lượt đọc và gửi mất 300 ms, cấu hình `fixedDelay = "1000"` tạo khoảng cách giữa hai lần bắt đầu xấp xỉ 1.300 ms trong điều kiện lý tưởng. Với lịch cron, cần xác định múi giờ vận hành khi yêu cầu nghiệp vụ gắn với giờ địa phương.

`fixedRate` không tự bảo đảm các lần gọi chạy song song hoặc đáp ứng đúng chu kỳ khi nguồn chậm. Scheduler, executor và thời gian thực thi vẫn ảnh hưởng lịch thực tế.

### maxMessagesPerPoll

Đối với `SourcePollingChannelAdapter`, mặc định thông thường là **một** lần nhận trong một lượt. Điều này khác với mặc định của một `PollingConsumer` đọc thông điệp từ kênh hàng đợi.

```java
poller = @Poller(
    fixedDelay = "1000",
    maxMessagesPerPoll = "5"
)
```

Với cấu hình này, một lượt có thể gọi nguồn tối đa năm lần. Nếu lần thứ ba trả `null`, lượt đó dừng lấy thêm thay vì tiếp tục đủ năm lần.

Có thể hình dung:

```text
lượt 1: ORDER-1, ORDER-2, null
nghỉ theo fixedDelay
lượt 2: ORDER-3, null
nghỉ theo fixedDelay
...
```

Nếu phương thức nguồn luôn trả dữ liệu, ví dụ luôn tạo heartbeat, không nên dùng `maxMessagesPerPoll = "-1"` một cách tùy tiện. Một lượt có thể lặp mãi thay vì nhường về lịch polling. Giá trị `0` có ý nghĩa bỏ qua việc nhận trong phiên bản hỗ trợ; nó không phải chế độ đọc không giới hạn.

Các quy tắc này được trình bày trong phần [Important: Poller Configuration](https://docs.spring.io/spring-integration/reference/channel-adapter.html#channel-adapter-inbound).

### Số lần đọc khác số bản ghi nghiệp vụ

Nếu mỗi lần đọc trả một `List<Order>` chứa 200 bản ghi, `maxMessagesPerPoll = "5"` có thể tạo tối đa năm message chứa danh sách trong một lượt. Nó không giới hạn tổng số đơn hàng nghiệp vụ ở mức năm.

Do đó, cần xem đồng thời:

- Kích thước dữ liệu mỗi lần truy vấn.
- Số lần nhận mỗi lượt.
- Khả năng xử lý của các bước phía sau.
- Kích thước thông điệp và mức sử dụng bộ nhớ.

### receiveTimeout không thay thế timeout của nguồn

`receiveTimeout` chủ yếu dành cho polling consumer đọc từ một `PollableChannel`. Nó không tự áp đặt thời hạn cho lời gọi HTTP, JDBC hoặc một phương thức Java tùy ý bên trong nguồn.

Khi đọc ERP qua HTTP, cấu hình connect/read timeout trên HTTP client. Nếu truy vấn cơ sở dữ liệu, dùng các cơ chế giới hạn thời gian phù hợp của tầng truy cập dữ liệu. Xem [Javadoc của Poller](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/Poller.html).

### Property placeholder và poller dùng chung

Có thể tách tham số lịch ra cấu hình:

```java
@InboundChannelAdapter(
    channel = "ordersChannel",
    autoStartup = "${orders.inbound.enabled:true}",
    poller = @Poller(
        fixedDelay = "${orders.inbound.delay-ms:1000}",
        maxMessagesPerPoll = "${orders.inbound.max-messages:1}"
    )
)
```

Đây là phần annotation thay thế trên phương thức nguồn. Ứng dụng cần có cơ chế phân giải placeholder; cấu hình Spring Boot thông thường cung cấp hạ tầng này.

Nếu muốn dùng một bean poller có tên:

```java
@InboundChannelAdapter(
    channel = "ordersChannel",
    poller = @Poller("ordersPoller")
)
```

Phải đăng ký `ordersPoller` dưới dạng `PollerMetadata` phù hợp. Khi tham chiếu theo tên, đặt lịch, executor hoặc advice trên bean metadata, không trộn thêm các thuộc tính lịch trong cùng `@Poller`.

Default poller là lựa chọn khác. Ví dụ:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.scheduling.PollerMetadata;
import org.springframework.scheduling.support.PeriodicTrigger;

@Bean(name = PollerMetadata.DEFAULT_POLLER)
public PollerMetadata defaultPoller() {
    PollerMetadata metadata = new PollerMetadata();
    metadata.setTrigger(
        new PeriodicTrigger(Duration.ofSeconds(1))
    );
    metadata.setMaxMessagesPerPoll(1);
    return metadata;
}
```

Đặt phương thức này trong lớp `@Configuration` rồi có thể dùng `@InboundChannelAdapter(channel = "ordersChannel")`. Default poller ảnh hưởng những endpoint khác cũng dựa vào nó; poller riêng thường giúp chính sách của một nguồn dễ thấy hơn.

## 7. Bean Supplier: factory được gọi khác với nguồn được polling

Bạn có thể gắn annotation lên phương thức `@Bean` trả về `Supplier`. Ví dụ sau là một cấu hình độc lập:

```java
package example.integration;

import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class SupplierInboundConfiguration {

    @Bean
    public Queue<String> pendingOrderIds() {
        Queue<String> queue = new ConcurrentLinkedQueue<>();
        queue.add("ORDER-S1");
        queue.add("ORDER-S2");
        return queue;
    }

    @Bean
    public QueueChannel supplierOrders() {
        return new QueueChannel(20);
    }

    @Bean
    @InboundChannelAdapter(
        channel = "supplierOrders",
        poller = @Poller(
            fixedDelay = "100",
            maxMessagesPerPoll = "1"
        )
    )
    public Supplier<String> orderIdSupplier(
            Queue<String> pendingOrderIds) {
        return pendingOrderIds::poll;
    }
}
```

Có hai thời điểm khác nhau:

- Container gọi `orderIdSupplier(...)` để tạo bean, đồng thời truyền dependency `pendingOrderIds`.
- Khi polling, adapter gọi `Supplier.get()` trên bean đã tạo.

Đối tượng trả về từ factory là một `Supplier<String>`. Dữ liệu được phát là kết quả `String` do supplier cung cấp. Khi queue cạn, `get()` trả `null` nên không phát thêm thông điệp.

Không đặt `@Bean` lên phương thức trả về trực tiếp một đơn hàng rồi mặc định rằng phương thức factory sẽ được gọi cho mỗi lượt poll. Nếu dùng kiểu khai báo nguồn bằng bean, hãy trả về abstraction nguồn phù hợp như `Supplier` hoặc `MessageSource`.

Supplier cũng có thể trả về `Message<String>` khi cần headers. Khả năng cấu hình trên phương thức `@Bean` được mô tả trong [Annotations on @Bean Methods](https://docs.spring.io/spring-integration/reference/configuration/meta-annotations.html#annotations-on-bean-methods).

## 8. Bean MessageSource: làm việc trực tiếp với Message

`MessageSource<T>` có thao tác `receive()` trả về `Message<T>` hoặc `null`. Tham số kiểu `T` là kiểu **payload**, không phải kiểu bao ngoài `Message<T>`.

Để chuyển ví dụ Supplier sang MessageSource, giữ hai bean `pendingOrderIds` và `supplierOrders`, thay bean `orderIdSupplier` bằng:

```java
@Bean
@InboundChannelAdapter(
    channel = "supplierOrders",
    poller = @Poller(
        fixedDelay = "100",
        maxMessagesPerPoll = "1"
    )
)
public MessageSource<String> orderMessageSource(
        Queue<String> pendingOrderIds) {

    return () -> {
        String orderId = pendingOrderIds.poll();

        if (orderId == null) {
            return null;
        }

        return MessageBuilder
            .withPayload(orderId)
            .setHeader("sourceSystem", "demo-erp")
            .build();
    };
}
```

Các import bổ sung:

```java
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.support.MessageBuilder;
```

Chỉ giữ một trong hai bean nguồn nếu không muốn tạo hai adapter cùng đọc một queue. Khi cả hai cùng tồn tại, chúng có thể lấy các phần tử khác nhau; đó không phải cơ chế nhân bản sự kiện.

| Dạng nguồn | Thao tác được gọi mỗi lần nhận | Khi thích hợp |
| --- | --- | --- |
| Phương thức POJO | Phương thức không tham số được chỉ định bằng annotation | Tái sử dụng logic đọc nguồn Java |
| `Supplier<T>` | `get()` | Nguồn đơn giản trả payload hoặc message |
| `MessageSource<T>` | `receive()` | Tích hợp với abstraction nguồn hoặc adapter sẵn có |

Hợp đồng `receive()` và ý nghĩa của `null` nằm trong [Javadoc của MessageSource](https://docs.spring.io/spring-integration/docs/6.0.x/api/org/springframework/integration/core/MessageSource.html).

## 9. Kênh đầu ra và luồng thực thi

Đích của inbound adapter là một kênh. Kiểu kênh này quyết định điều gì xảy ra sau khi nguồn đã tạo message.

### Đầu ra là DirectChannel

```text
polling task -> gọi nguồn -> DirectChannel -> handler đồng bộ
```

Handler phía sau chạy trên luồng của tác vụ polling cho đến khi gặp ranh giới bất đồng bộ khác. Nếu handler chậm, lượt polling cũng kéo dài. Nếu không có subscriber, gửi vào `DirectChannel` có thể thất bại.

Đây vẫn là adapter có poller. Đầu ra subscribable không làm nó thành event-driven source.

### Đầu ra là QueueChannel

```text
polling task -> gọi nguồn -> QueueChannel
                                |
                       consumer đọc về sau
```

Việc đưa message vào queue tách thời điểm tiếp nhận và xử lý nghiệp vụ. Một lần gửi thành công vào queue chưa chứng minh consumer đã xử lý xong.

Queue có sức chứa hữu hạn giúp giới hạn vùng đệm, nhưng khi đầy có thể khiến thao tác gửi chờ hoặc thất bại tùy cấu hình timeout. Queue không giới hạn có thể làm bộ nhớ tăng nếu nguồn nhanh hơn consumer trong thời gian dài.

Các queue trong ví dụ nằm trong bộ nhớ. Nếu ứng dụng cần lưu dữ liệu qua lần khởi động lại, phải chọn message store hoặc broker/cơ chế lưu bền phù hợp.

## 10. XML tương đương

Để dùng XML làm phương án thay thế cho ví dụ phần 5, giữ logic của `OrderEventSource` nhưng **gỡ `@InboundChannelAdapter` và `@EndpointId` khỏi `nextOrder()`**. XML sẽ chịu trách nhiệm tạo endpoint:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           https://www.springframework.org/schema/integration/spring-integration.xsd">

    <bean id="orderEventSource"
          class="example.integration.OrderEventSource"/>

    <int:channel id="ordersChannel">
        <int:queue capacity="20"/>
    </int:channel>

    <int:inbound-channel-adapter
            id="ordersInbound"
            ref="orderEventSource"
            method="nextOrder"
            channel="ordersChannel"
            auto-startup="false">
        <int:poller fixed-delay="100"
                    max-messages-per-poll="1"/>
    </int:inbound-channel-adapter>
</beans>
```

`ref` trỏ tới bean chứa logic đọc nguồn. `method` chọn phương thức không tham số. `channel` là nơi nhận message, còn `id` đặt tên endpoint.

Nạp XML vào application context thay cho `InboundOrderConfiguration` để tránh đăng ký trùng bean. Sau đó vẫn cần thêm dữ liệu vào nguồn và gọi `start()` trên endpoint vì `auto-startup` đang là `false`.

## 11. Java DSL tương đương

Java DSL có thể mô tả rõ nguồn và phần luồng phía sau trong cùng một bean flow. Giữ `ordersChannel` cùng bean `orderEventSource`, gỡ hai annotation endpoint khỏi `nextOrder()` như ở phương án XML, rồi thêm:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Bean
public IntegrationFlow ordersInboundFlow(
        OrderEventSource orderEventSource) {

    return IntegrationFlow.fromSupplier(
            orderEventSource::nextOrder,
            endpoint -> endpoint
                .id("ordersInbound")
                .autoStartup(false)
                .poller(
                    Pollers.fixedDelay(Duration.ofMillis(100))
                        .maxMessagesPerPoll(1)
                )
        )
        .channel("ordersChannel")
        .get();
}
```

Đặt phương thức trong lớp `@Configuration` có hạ tầng Integration. `fromSupplier(...)` xác định nguồn cần polling; `.channel(...)` xác định đích gửi.

Không dùng `IntegrationFlow.from("ordersChannel")` như một cách thay thế trực tiếp: overload nhận tên kênh bắt đầu từ thông điệp **đã có trên kênh**, còn bài toán này cần gọi nguồn để tạo thông điệp mới. Các overload nằm trong [Javadoc của IntegrationFlow](https://docs.spring.io/spring-integration/docs/6.1.2/api/org/springframework/integration/dsl/IntegrationFlow.html).

Các phương án annotation, XML và DSL ở đây là cách khai báo thay thế cho cùng một endpoint. Kết hợp cả ba mà không điều chỉnh sẽ tạo thêm endpoint hoặc xung đột tên, chứ không làm polling chính xác hơn.

## 12. Lỗi polling và ErrorMessage

Nguồn có thể thất bại trước khi tạo được message, chẳng hạn HTTP client không kết nối được ERP. Lỗi cũng có thể xuất hiện khi adapter gửi message vào kênh hoặc khi handler đồng bộ phía sau xử lý.

Poller chạy dưới hạ tầng lập lịch, nên lỗi của tác vụ không được trả về một lời gọi nghiệp vụ request-reply đang chờ. Có thể cấu hình kênh lỗi riêng:

```java
@InboundChannelAdapter(
    channel = "ordersChannel",
    poller = @Poller(
        fixedDelay = "1000",
        maxMessagesPerPoll = "1",
        errorChannel = "ordersPollingErrors"
    )
)
```

Đăng ký thêm bean `ordersPollingErrors` rồi nối consumer xử lý lỗi với kênh đó. Trong hạ tầng chuẩn, error handler phát `ErrorMessage` có exception làm payload. Header `errorChannel` của message, khi đã có message và error handler sử dụng được header đó, có thể ảnh hưởng đích lỗi; thuộc tính của poller xác định kênh mặc định cho handler.

Nếu nguồn ném lỗi trước khi tạo thông điệp, có thể chưa có message nghiệp vụ để đặt vào thông tin lỗi. Đừng giả định mọi lỗi nguồn đều chứa đầy đủ mã đơn hàng.

Cơ chế chung được mô tả tại [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

### Cấu hình lỗi độc lập để thực hành

Ví dụ sau luôn ném exception khi đọc nguồn và chủ động chờ lệnh khởi động. Nó dùng cho kiểm thử đường lỗi, không phải nguồn đơn hàng thực:

```java
package example.integration;

import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EndpointId;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class FailingInboundConfiguration {

    @Bean
    public QueueChannel failureOutput() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel ordersPollingErrors() {
        return new QueueChannel(20);
    }

    @Bean
    @EndpointId("failingInbound")
    @InboundChannelAdapter(
        channel = "failureOutput",
        autoStartup = "false",
        poller = @Poller(
            fixedDelay = "100",
            maxMessagesPerPoll = "1",
            errorChannel = "ordersPollingErrors"
        )
    )
    public Supplier<String> failingSource() {
        return () -> {
            throw new IllegalStateException(
                "Không thể đọc dữ liệu nguồn"
            );
        };
    }
}
```

Một `QueueChannel` lỗi chỉ lưu thông điệp để consumer đọc. Nó không tự retry, ghi log hoặc đưa dữ liệu về nguồn.

Phân biệt hai tình huống:

- Lần poll sau thử gọi lại nguồn sau sự cố kết nối.
- Retry một đơn hàng đã được lấy khỏi nguồn nhưng xử lý thất bại.

Hai việc này có thể cần chính sách khác nhau. Một adapter tiếp tục được lập lịch không mặc nhiên bảo đảm đơn hàng đã lấy ra sẽ được gửi lại.

## 13. Kiểm thử nguồn và endpoint

Các ví dụ kiểm thử dưới đây đặt trong package `example.integration`. Chúng sử dụng ba lớp đã trình bày: `OrderEventSource`, `InboundOrderConfiguration` và `FailingInboundConfiguration`.

### 13.1. Kiểm thử hợp đồng nguồn mà không tạo context

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class OrderEventSourceTest {

    @Test
    void returnsOneMessageThenNullWhenSourceIsEmpty() {
        OrderEventSource source = new OrderEventSource();

        assertNull(source.nextOrder());

        source.offer("ORDER-1001");

        Message<String> message = source.nextOrder();
        assertNotNull(message);
        assertEquals("ORDER-1001", message.getPayload());
        assertEquals(
            "demo-erp",
            message.getHeaders().get("sourceSystem")
        );
        assertEquals(
            "created:ORDER-1001",
            message.getHeaders().get("businessEventId")
        );

        assertNull(source.nextOrder());
    }
}
```

Bài kiểm thử này xác minh logic đọc nguồn và headers. Gọi trực tiếp một phương thức có annotation vẫn là lời gọi Java thông thường; nó không tạo lịch polling hay tự gửi kết quả vào kênh.

### 13.2. Kiểm thử polling, lifecycle và trường hợp nguồn rỗng

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.endpoint.SourcePollingChannelAdapter;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class InboundChannelAdapterTest {

    @Test
    void pollsOnlyAfterAdapterIsStarted() {
        try (var context = new AnnotationConfigApplicationContext(
                InboundOrderConfiguration.class)) {

            OrderEventSource source =
                context.getBean(OrderEventSource.class);
            QueueChannel output = context.getBean(
                "ordersChannel", QueueChannel.class);
            SourcePollingChannelAdapter adapter = context.getBean(
                "ordersInbound",
                SourcePollingChannelAdapter.class
            );

            source.offer("ORDER-A");
            source.offer("ORDER-B");

            assertFalse(adapter.isRunning());
            assertNull(output.receive(0));

            adapter.start();
            assertTrue(adapter.isRunning());

            Message<?> first = output.receive(3_000);
            Message<?> second = output.receive(3_000);

            assertNotNull(first);
            assertNotNull(second);
            assertEquals("ORDER-A", first.getPayload());
            assertEquals("ORDER-B", second.getPayload());
            assertEquals(
                "demo-erp",
                first.getHeaders().get("sourceSystem")
            );

            adapter.stop();
            assertFalse(adapter.isRunning());
        }
    }

    @Test
    void canReceiveNewDataAfterSourceWasEmpty() {
        try (var context = new AnnotationConfigApplicationContext(
                InboundOrderConfiguration.class)) {

            OrderEventSource source =
                context.getBean(OrderEventSource.class);
            QueueChannel output = context.getBean(
                "ordersChannel", QueueChannel.class);
            SourcePollingChannelAdapter adapter = context.getBean(
                "ordersInbound",
                SourcePollingChannelAdapter.class
            );

            adapter.start();

            assertNull(output.receive(250));

            source.offer("ORDER-LATER");

            Message<?> received = output.receive(3_000);
            assertNotNull(received);
            assertEquals("ORDER-LATER", received.getPayload());

            adapter.stop();
        }
    }

    @Test
    void routesSourceFailureToConfiguredErrorChannel() {
        try (var context = new AnnotationConfigApplicationContext(
                FailingInboundConfiguration.class)) {

            SourcePollingChannelAdapter adapter = context.getBean(
                "failingInbound",
                SourcePollingChannelAdapter.class
            );
            QueueChannel errors = context.getBean(
                "ordersPollingErrors", QueueChannel.class);
            QueueChannel output = context.getBean(
                "failureOutput", QueueChannel.class);

            adapter.start();

            Message<?> error = errors.receive(3_000);

            adapter.stop();

            assertNotNull(error);
            assertTrue(error instanceof ErrorMessage);
            assertTrue(error.getPayload() instanceof Throwable);
            assertNull(output.receive(0));
        }
    }
}
```

Các bài kiểm thử dùng `receive(timeout)` để chờ kết quả thay vì `Thread.sleep(...)`. Khi dữ liệu đến sớm, thao tác nhận trả về ngay; khi có lỗi cấu hình, thời gian chờ vẫn được giới hạn.

`try-with-resources` đóng context để dừng tài nguyên lập lịch sau kiểm thử. Việc khởi động adapter sau khi chuẩn bị dữ liệu giúp tách rõ giai đoạn sắp xếp và giai đoạn thực thi.

Bài kiểm thử nguồn rỗng quan sát không có dữ liệu trong một khoảng chờ rồi thêm dữ liệu để kiểm tra adapter vẫn có thể phát message. Nó không đo chính xác số lần gọi nguồn hoặc độ chính xác từng mốc thời gian.

Các bài này cũng chưa chứng minh đặc tính chịu tải, tính nguyên tử của đọc-và-gửi hoặc khả năng phục hồi sau khi tiến trình dừng. Nếu nguồn thực dùng ERP hay database, cần thêm kiểm thử cho hợp đồng của tầng đó.

## 14. Chẩn đoán các lỗi thường gặp

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Annotation có mặt nhưng không thấy polling | Đối tượng chưa là bean, cấu hình chưa được nạp hoặc hạ tầng annotation chưa bật | Kiểm tra đăng ký bean và Integration configuration |
| Adapter chưa khởi động được | Không có poller riêng hoặc default poller hợp lệ | Khai báo lịch polling rõ ràng |
| Phương thức nguồn bị từ chối | Có tham số hoặc trả về `void` | Đưa dependency vào đối tượng nguồn; trả dữ liệu hoặc message |
| Không có dữ liệu dù context đã tạo | `autoStartup` đang là `false`, nguồn trả `null` hoặc giới hạn nhận là `0` | Kiểm tra trạng thái endpoint và kết quả đọc nguồn |
| Queue đầu ra rỗng khi kiểm thử | Kiểm tra trước khi poller chạy hoặc đang đọc sai kênh | Dùng `receive(timeout)` trên đúng đầu ra |
| Phát ra một danh sách thay vì từng đơn hàng | Nguồn trả về collection | Thêm splitter nếu hợp đồng yêu cầu mỗi phần tử là một message |
| Lượt poll không kết thúc | Số lần nhận không giới hạn trong khi nguồn không trả `null` | Đặt giới hạn hữu hạn hoặc sửa hợp đồng kết thúc lượt |
| Tần suất thấp hơn dự kiến | Nguồn hoặc handler đồng bộ chậm; queue đích đầy | Đo thời gian đọc, gửi và xử lý thay vì chỉ giảm delay |
| Gửi vào DirectChannel thất bại | Không có subscriber ở đầu ra | Đăng ký và khởi động consumer |
| Dữ liệu bị đọc nhiều lần giữa các instance | Nhiều tiến trình cùng polling mà không có cơ chế phối hợp | Thiết kế claim/lock/phân vùng cùng chiến lược chống trùng |

### Lifecycle không phải khóa phân tán

`autoStartup` điều khiển một endpoint trong một application context. `phase` điều khiển thứ tự bắt đầu và dừng giữa các thành phần lifecycle.

Hai thuộc tính này không bầu một instance duy nhất được đọc ERP. Nếu ứng dụng chạy ba replica và cả ba adapter đều khởi động, cả ba có thể polling cùng nguồn.

Tùy bài toán, cần thiết kế cơ chế claim bản ghi, khóa có thời hạn, leader election hoặc phân chia nguồn. Logic xử lý phía sau vẫn cần tính đến sự kiện trùng khi nguồn hoặc hạ tầng có thể gửi lại.

### Theo dõi đúng ba giai đoạn

Khi điều tra mất dữ liệu, hãy phân biệt:

1. Nguồn đã trả dữ liệu nào và có làm thay đổi trạng thái nguồn không?
2. Adapter đã gửi được message vào kênh chưa?
3. Consumer nghiệp vụ đã xử lý thành công chưa?

Một log “đã đọc 100 đơn hàng” chỉ chứng minh giai đoạn đầu. Một lần gửi thành công vào queue chỉ chứng minh message được chấp nhận tại ranh giới queue. Cần dấu vết nghiệp vụ để kết nối các giai đoạn.

## 15. Thiết kế nguồn cho ứng dụng thực tế

Ví dụ `OrderEventSource` dùng `poll()` để loại phần tử khỏi bộ đệm trước khi gửi. Đây là cách đơn giản để học hợp đồng API, nhưng để đảm bảo dữ liệu trong hệ thống thật cần xác định thời điểm đánh dấu hoàn tất.

Chẳng hạn, nếu đọc bảng `pending_order_events`:

```text
chọn/claim sự kiện
       |
       v
tạo message kèm businessEventId
       |
       v
đưa vào luồng tích hợp
       |
       v
xử lý và ghi nhận kết quả theo hợp đồng đã thiết kế
```

Nếu đánh dấu sự kiện là “đã xử lý” ngay khi đọc nhưng tiến trình dừng trước khi gửi, dữ liệu có thể bị bỏ sót. Nếu chỉ đánh dấu sau cùng, cần tính đến khả năng đọc lại hoặc xử lý lại.

Các yêu cầu cần được thể hiện bằng cơ chế cụ thể:

- Timeout cho truy vấn và kết nối nguồn.
- Cách đánh dấu, claim hoặc checkpoint.
- Lưu bền ở ranh giới cần bảo vệ dữ liệu.
- Retry có giới hạn và đường xử lý lỗi sau khi vượt giới hạn.
- Khóa nghiệp vụ ổn định để consumer phát hiện sự kiện đã xử lý.
- Giới hạn số lượng, kích thước dữ liệu và khả năng xử lý đồng thời.

`@InboundChannelAdapter` không tự cung cấp giao dịch phân tán hoặc đảm bảo exactly-once. Nếu dùng transaction advice cho poller, vẫn phải xác định tài nguyên nào thực sự tham gia transaction. Một cuộc gọi HTTP hoặc queue trong bộ nhớ không tự trở thành tài nguyên giao dịch của database.

Khi nguồn có adapter chuyên dụng của Spring Integration, hãy đánh giá hợp đồng đọc và xác nhận của adapter đó thay vì mặc định mọi nguồn giống phương thức Java trong bài.

Trong luồng đầy đủ, inbound adapter chịu trách nhiệm đưa dữ liệu nguồn thành message. Filter, transformer, router, aggregator và handler nghiệp vụ tiếp tục thực hiện từng vai trò sau điểm nhập dữ liệu. Đọc cấu hình theo chuỗi **poller -> nguồn -> message -> kênh đầu ra -> các endpoint xử lý** sẽ giúp xác định đúng nơi đặt lịch, nơi đổi dữ liệu và nơi xử lý lỗi.
