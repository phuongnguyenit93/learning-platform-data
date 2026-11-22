# from PollableChannel

## Mục tiêu và phạm vi

Trong chương **Java DSL** của **SPRING_INTEGRATION_CORE**, bài này trình bày cách bắt đầu một `IntegrationFlow` từ `PollableChannel`. Đây là cách nối một hàng đợi thông điệp đã có với các endpoint xử lý bằng Java DSL.

Sau bài học, bạn có thể:

- Phân biệt khai báo channel đầu vào với cấu hình endpoint lấy thông điệp.
- Đặt poller đúng vị trí khi endpoint đầu tiên là transformer, filter hoặc service activator.
- Giải thích ý nghĩa của nhịp polling, giới hạn số thông điệp và thời gian chờ nhận.
- Theo dõi thông điệp hợp lệ, thông điệp bị loại và lỗi xử lý trên các đường riêng.
- Viết kiểm thử có thời gian chờ giới hạn cho luồng xử lý bất đồng bộ.

Ví dụ sử dụng Java 17+ và API Spring Integration 6.5. Các tên lớp chính thuộc `spring-integration-core`; Java DSL được cung cấp trong thư viện này. Với Spring Boot, có thể dùng `spring-boot-starter-integration` và để dependency management của dự án quản lý phiên bản. Trong tài liệu cũ, bạn có thể gặp `IntegrationFlows.from(...)`; ví dụ ở đây dùng `IntegrationFlow.from(...)`.

## 1. PollableChannel cung cấp khả năng gì?

`PollableChannel` mở rộng `MessageChannel` bằng khả năng nhận thông điệp:

~~~java
public interface PollableChannel extends MessageChannel {

    Message<?> receive();

    Message<?> receive(long timeout);
}
~~~

`MessageChannel` cung cấp thao tác gửi; `PollableChannel` bổ sung thao tác nhận theo cơ chế bên tiêu thụ chủ động lấy dữ liệu. Khi không nhận được thông điệp trong khoảng thời gian cho phép, `receive(long)` trả về `null`. Tham số timeout được tính bằng mili giây. Xem [hợp đồng PollableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html).

`QueueChannel` là triển khai thường dùng: producer đưa thông điệp vào queue, consumer lấy chúng ra sau đó. Một thông điệp trong queue được giao cho một consumer; thêm consumer không biến queue thành cơ chế phát cùng một thông điệp đến mọi bên nhận. Các triển khai khác như `PriorityChannel` và `RendezvousChannel` có quy tắc xếp hàng hoặc bàn giao khác. Xem [các triển khai MessageChannel](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

Ví dụ tạo một queue có giới hạn:

~~~java
QueueChannel input = new QueueChannel(100);
~~~

Con số `100` là sức chứa thông điệp đang đợi. Nó không quy định số thread xử lý, số lần thử lại hay số thông điệp mỗi lần polling. Có thể quan sát `getQueueSize()` và `getRemainingCapacity()` trên `QueueChannel` để hiểu tình trạng bộ đệm. Xem [QueueChannel API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/channel/QueueChannel.html).

## 2. from(queue) khai báo đầu vào, endpoint mới thực hiện polling

Xét một chuỗi khai báo:

~~~java
IntegrationFlow.from(orderQueue)
        .transform(...)
        .filter(...)
        .channel(acceptedOrders)
        .get();
~~~

`from(orderQueue)` đưa channel đầu vào vào cấu trúc luồng. Phương thức này không tự gọi `receive()` ngay khi Java chạy đến dòng khai báo, cũng không tự tạo ra đơn hàng. Một producer khác vẫn phải gửi `Message<?>` vào queue.

Trong cấu hình consumer thông thường, loại channel đầu vào quyết định cách endpoint tiếp nhận thông điệp:

| Channel của endpoint | Cách tiếp nhận | Endpoint thường được tạo |
|---|---|---|
| `DirectChannel` | Được gọi khi có thông điệp gửi đến | `EventDrivenConsumer` |
| `QueueChannel`, một `PollableChannel` | Lấy thông điệp theo lịch | `PollingConsumer` |

Đây là cơ chế lựa chọn endpoint của [ConsumerEndpointFactoryBean](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/config/ConsumerEndpointFactoryBean.html). Bài này xét cơ chế consumer thông thường, không cấu hình consumer reactive.

Với queue đầu vào, poller phải thuộc endpoint đầu tiên **thực sự tiêu thụ queue đó**. Nếu transformer đứng đầu, cấu hình poller trên transformer. Nếu filter hay `handle` đứng đầu, cấu hình trên endpoint tương ứng. Các phương thức `poller(...)`, `id(...)` và `autoStartup(...)` là tùy chọn của endpoint; xem [ConsumerEndpointSpec API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html).

Ví dụ tối giản, với hai biến channel đã được cung cấp:

~~~java
return IntegrationFlow.from(orderQueue)
        .<String, String>transform(
                String::trim,
                endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(200))
                                .maxMessagesPerPoll(10)
                                .receiveTimeout(0)))
        .channel(acceptedOrders)
        .get();
~~~

`.get()` hoàn tất việc xây dựng định nghĩa flow. Khi định nghĩa được đăng ký dưới dạng bean và application context khởi động, Spring Integration mới quản lý các thành phần và lifecycle của chúng. Xem [Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl.html).

## 3. Luồng ví dụ: chuẩn hóa và kiểm tra mã đơn hàng

Giả sử một ứng dụng tiếp nhận mã đơn hàng dạng chuỗi:

- `" order:ab-17 "` được chuẩn hóa thành `"ORDER:AB-17"` rồi đi vào nhánh chấp nhận.
- `"invalid"` được chuẩn hóa nhưng không vượt qua filter, nên đi vào nhánh loại bỏ.
- Chuỗi chỉ chứa khoảng trắng gây lỗi chuẩn hóa và đi vào error channel.

Điều kiện bắt đầu bằng `ORDER:` chỉ là quy tắc minh họa. Hệ thống thực tế cần kiểm tra đầy đủ cấu trúc và nội dung mã đơn hàng.

~~~mermaid
flowchart LR
    P["Producer"] -->|"send(message)"| Q["orderQueue: QueueChannel"]
    Q -->|"receive(timeout), theo lịch poller"| T["Transformer: normalizeOrder"]
    T --> F{"Bắt đầu bằng ORDER:?"}
    F -->|"Có"| A["acceptedOrders"]
    F -->|"Không"| R["rejectedOrders"]
    T -.->|"Exception → ErrorMessage"| E["orderFlowErrors"]
~~~

Trong sơ đồ, poller phục vụ endpoint `normalizeOrder`. Transformer và filter tiếp tục xử lý trên thread đang chạy tác vụ polling khi giữa chúng không có điểm chuyển thread.

### 3.1. Cấu hình Java đầy đủ

~~~java
import java.time.Duration;
import java.util.Locale;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class PollableOrderConfig {

    @Bean
    public QueueChannel orderQueue() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel acceptedOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel rejectedOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel orderFlowErrors() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow orderFlow(
            @Qualifier("orderQueue") PollableChannel orderQueue,
            @Qualifier("acceptedOrders") MessageChannel acceptedOrders,
            @Qualifier("rejectedOrders") MessageChannel rejectedOrders,
            @Qualifier("orderFlowErrors") MessageChannel orderFlowErrors) {

        return IntegrationFlow.from(orderQueue)
                .<String, String>transform(
                        PollableOrderConfig::normalize,
                        endpoint -> endpoint
                                .id("normalizeOrder")
                                .poller(
                                        Pollers.fixedDelay(
                                                Duration.ofMillis(200))
                                                .maxMessagesPerPoll(10)
                                                .receiveTimeout(0)
                                                .errorChannel(orderFlowErrors)))
                .<String>filter(
                        payload -> payload.startsWith("ORDER:"),
                        endpoint -> endpoint.discardChannel(rejectedOrders))
                .channel(acceptedOrders)
                .get();
    }

    private static String normalize(String raw) {
        String normalized = raw.strip().toUpperCase(Locale.ROOT);

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Mã đơn hàng rỗng");
        }

        return normalized;
    }
}
~~~

Các điểm cần đọc được từ cấu hình:

1. `@Qualifier` xác định rõ từng queue vì application context có nhiều bean cùng kiểu.
2. `proxyBeanMethods = false` đi cùng cách truyền bean qua tham số; flow sử dụng đúng instance do Spring quản lý.
3. `normalizeOrder` là ID endpoint, giúp định vị thành phần khi quan sát hoặc điều khiển lifecycle.
4. Poller được cấu hình trên transformer vì input của transformer là `orderQueue`.
5. Filter loại thông điệp không đạt điều kiện sang `rejectedOrders`; việc bị loại theo quy tắc nghiệp vụ không đồng nghĩa phát sinh exception.
6. `acceptedOrders` kết thúc flow bằng một queue chứa kết quả. Ví dụ chưa khai báo endpoint tiếp tục đọc queue kết quả này.

`Pollers` cung cấp factory cho trigger như `fixedDelay`, `fixedRate` và `cron`; overload nhận `Duration` giúp thể hiện rõ đơn vị của khoảng thời gian. Xem [Pollers API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/Pollers.html).

### 3.2. Gửi một Message và nhận kết quả

Đoạn sau có thể đặt trong một phương thức chạy thử. Cần các import `AnnotationConfigApplicationContext`, `Message` và `MessageBuilder`:

~~~java
try (var context =
        new org.springframework.context.annotation.AnnotationConfigApplicationContext(
                PollableOrderConfig.class)) {

    var input = context.getBean("orderQueue", MessageChannel.class);
    var output = context.getBean("acceptedOrders", PollableChannel.class);

    var request = org.springframework.messaging.support.MessageBuilder
            .withPayload(" order:ab-17 ")
            .setHeader("traceId", "trace-001")
            .build();

    boolean queued = input.send(request, 500);

    if (!queued) {
        throw new IllegalStateException("Queue đầu vào chưa nhận được thông điệp");
    }

    org.springframework.messaging.Message<?> result = output.receive(3_000);

    if (result == null) {
        throw new IllegalStateException("Chưa nhận được kết quả trong thời gian chờ");
    }

    System.out.println(result.getPayload());               // ORDER:AB-17
    System.out.println(result.getHeaders().get("traceId")); // trace-001
}
~~~

Hai thao tác chờ có ý nghĩa khác nhau:

- `send(request, 500)` chờ tối đa 500 ms để đưa thông điệp vào queue đầu vào.
- `output.receive(3_000)` chờ tối đa 3 giây để lấy một thông điệp kết quả.

`send(...) == true` cho biết channel đã chấp nhận thông điệp. Khi endpoint chạy sau một queue, giá trị đó chưa chứng minh nghiệp vụ đã hoàn thành. Việc kiểm tra kết quả phải dựa vào output, lỗi hoặc tín hiệu hoàn thành phù hợp với thiết kế.

## 4. Đọc đúng cấu hình poller

### 4.1. Nhịp chạy, giới hạn và thời gian chờ

| Tùy chọn | Câu hỏi được trả lời | Ý nghĩa trong ví dụ |
|---|---|---|
| `fixedDelay(200 ms)` | Sau khi tác vụ polling kết thúc, chờ bao lâu để lên lần tiếp theo? | Chờ 200 ms, khi không ủy quyền sang executor riêng |
| `maxMessagesPerPoll(10)` | Một lần thực thi tác vụ polling xử lý tối đa bao nhiêu thông điệp? | Tối đa 10, có thể ít hơn nếu queue hết dữ liệu |
| `receiveTimeout(0)` | Mỗi lần lấy thông điệp sẽ chờ bao lâu nếu queue trống? | Không chờ |
| `errorChannel(orderFlowErrors)` | Lỗi tác vụ polling được gửi mặc định đến đâu? | Queue lỗi của ví dụ |

`receiveTimeout` có đơn vị mili giây và mặc định là 1.000 ms trong API 6.5. Nó không giới hạn thời gian chạy transformer hoặc HTTP call bên trong handler. Xem [PollerSpec API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/PollerSpec.html).

Với 25 thông điệp có sẵn, không có producer bổ sung, không có lỗi và consumer xử lý tuần tự, giới hạn 10 cho phép ba lần polling lấy lần lượt 10, 10 và 5 thông điệp. Các thông điệp vẫn đi qua transformer và filter riêng lẻ. `maxMessagesPerPoll` không tạo `List` chứa cả nhóm; muốn gom nhóm theo nghiệp vụ cần thiết kế aggregator riêng.

Với polling consumer, cấu hình không giới hạn có thể tiếp tục lấy cho đến khi receive trả về `null`. Queue liên tục có dữ liệu có thể khiến một tác vụ giữ thread lâu; dùng giới hạn dương giúp thời lượng mỗi lần chạy dễ dự đoán hơn. Xem [Polling Consumer](https://docs.spring.io/spring-integration/reference/6.5/endpoint.html#polling-consumer).

### 4.2. Một ước lượng để hiểu thông lượng

Giả sử:

- Mỗi thông điệp mất trung bình 30 ms cho toàn bộ đoạn xử lý đồng bộ.
- Mỗi lần polling lấy đủ 10 thông điệp.
- Fixed delay là 200 ms.
- Không có executor riêng, thời gian chờ queue và chi phí khác được bỏ qua.

Một lần xử lý mất khoảng `10 × 30 = 300 ms`; cộng khoảng nghỉ, chu kỳ đạt khoảng 500 ms. Thông lượng ước lượng là:

~~~text
10 / (0,300 + 0,200) = 20 thông điệp/giây
~~~

Đây là phép tính minh họa từ các giả định trên. Trong tình huống này, suy ra 50 thông điệp/giây chỉ từ `10 / 0,200` sẽ bỏ qua 300 ms xử lý. Tăng giới hạn mỗi lần polling chỉ giảm tỷ trọng thời gian nghỉ, không tự làm handler chạy nhanh hơn.

### 4.3. Chọn receiveTimeout có chủ đích

`receiveTimeout(0)` phù hợp để minh họa việc thử nhận rồi nhường thread khi queue trống. Đổi thành một số dương cho phép tác vụ chờ thông điệp đến, đổi lại thread bị giữ trong thời gian chờ.

Ví dụ `fixedDelay(200 ms)` kết hợp `receiveTimeout(1.000)` không có nghĩa một lần polling luôn kết thúc sau 200 ms. Nếu queue trống, riêng thao tác nhận đã có thể đợi một giây. Đặc biệt, một lần polling có nhiều lần receive có thể chờ ở lần receive sau khi đã xử lý những thông điệp trước.

## 5. Poller cục bộ và poller mặc định

Cách cấu hình trong `PollableOrderConfig` là poller cục bộ: thông số nằm ngay cạnh endpoint sử dụng chúng.

Một lựa chọn khác là khai báo global default poller. Endpoint có input là `PollableChannel` và không có poller riêng sẽ dùng cấu hình này. Bean cần mang tên `PollerMetadata.DEFAULT_POLLER`. Xem [Global Default Poller](https://docs.spring.io/spring-integration/reference/6.5/endpoint.html#global-default-poller).

Ví dụ phương thức bean thay thế trong một lớp cấu hình; cần import thêm `PollerMetadata` và `PeriodicTrigger`:

~~~java
@Bean(name = PollerMetadata.DEFAULT_POLLER)
public PollerMetadata defaultPoller() {
    PollerMetadata metadata = new PollerMetadata();
    metadata.setTrigger(new PeriodicTrigger(Duration.ofMillis(200)));
    metadata.setMaxMessagesPerPoll(10);
    metadata.setReceiveTimeout(0);
    return metadata;
}
~~~

Khi đó một flow đơn giản có thể viết:

~~~java
return IntegrationFlow.from(orderQueue)
        .<String, String>transform(String::trim)
        .channel(acceptedOrders)
        .get();
~~~

Đây là phương án cấu hình thay thế, không phải yêu cầu xóa poller trong ví dụ chính. Nếu bỏ poller cục bộ của ví dụ chính, bạn cũng bỏ cấu hình error channel cục bộ; cần xác định lại đường xử lý lỗi mong muốn.

Poller riêng được dùng cho endpoint có cấu hình riêng; default poller là phương án dự phòng cho các endpoint còn lại. Chỉ nên có một default poller trong cùng application context. Việc thiếu cả poller riêng lẫn default poller có thể làm context khởi động thất bại với thông báo thiếu poller.

## 6. Chọn đúng overload của from

| Cách viết | Ý nghĩa |
|---|---|
| `IntegrationFlow.from(queueBean)` | Dùng instance channel được truyền vào |
| `IntegrationFlow.from("orderQueue")` | Tham chiếu channel bean theo tên; nếu tên chưa tồn tại, DSL có thể tạo `DirectChannel` |
| `IntegrationFlow.from(MessageChannels.queue("orderQueue", 100))` | Khai báo channel bằng queue spec trong flow |
| `IntegrationFlow.from(messageSource, endpointConfigurer)` | Khởi đầu từ `MessageSource`, cấu hình inbound adapter của nguồn |

Các overload được mô tả trong [IntegrationFlow API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/IntegrationFlow.html).

Khi bài toán yêu cầu một queue đã có, truyền bean kiểu `PollableChannel` giúp kiểm tra được giả định này ngay tại điểm nhận dependency. Cách truyền tên vẫn hợp lệ nếu bean được khai báo đúng, nhưng tên `"orderQueue"` tự nó không bảo đảm channel thuộc kiểu queue.

Một lỗi dễ gặp là sao chép cấu hình inbound adapter sang channel:

~~~java
// Không có overload nhận MessageChannel và lambda cấu hình endpoint như thế này.
IntegrationFlow.from(orderQueue,
        endpoint -> endpoint.poller(Pollers.fixedDelay(200)));
~~~

Với channel, hãy đặt cấu hình trên bước tiêu thụ:

~~~java
IntegrationFlow.from(orderQueue)
        .<String>handle(
                (payload, headers) -> payload.toUpperCase(Locale.ROOT),
                endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(200))
                                .maxMessagesPerPoll(10)
                                .receiveTimeout(0)))
        .channel(acceptedOrders)
        .get();
~~~

`PollableChannel` và `MessageSource` đều liên quan đến thao tác nhận, nhưng chúng là hai abstraction khác nhau. Với queue đã tồn tại, dùng trực tiếp channel làm input giúp flow thể hiện rõ điểm nối với producer.

## 7. Thêm queue giữa flow sẽ tạo thêm điểm polling

Ví dụ một đoạn flow với các channel đã được quản lý trong context:

~~~java
return IntegrationFlow.from(orderQueue)
        .<String, String>transform(
                String::trim,
                endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(200))
                                .maxMessagesPerPoll(10)
                                .receiveTimeout(0)))
        .channel(stagingQueue)
        .<String>handle(
                (payload, headers) -> payload.toUpperCase(Locale.ROOT),
                endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(500))
                                .maxMessagesPerPoll(5)
                                .receiveTimeout(0)))
        .channel(acceptedOrders)
        .get();
~~~

Ở đây, giả sử `stagingQueue` cũng là `QueueChannel`:

- Transformer cần poller để nhận từ `orderQueue`.
- Service activator cần poller để nhận từ `stagingQueue`.
- `acceptedOrders` chỉ là đích chứa kết quả của đoạn flow, chưa có endpoint phía sau.

Poller của transformer không tự phục vụ queue ở phía sau. Khi cần thêm router, filter hay aggregator, hãy xác định channel đầu vào của từng endpoint trước khi quyết định vị trí poller. `PollingConsumer` chính là thành phần nối một handler với một `PollableChannel`; xem [PollingConsumer API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/endpoint/PollingConsumer.html).

## 8. Thread xử lý, lỗi và kết quả nghiệp vụ

### 8.1. Queue tạo điểm bàn giao

Producer chạy `send` trên thread gọi. Sau đó endpoint lấy thông điệp bằng tác vụ polling và chạy phần xử lý tiếp theo. Vì vậy:

- Producer có thể hoàn thành việc gửi trước khi transformer chạy.
- Trong ví dụ chính, transformer và filter tiếp tục xử lý đồng bộ trong tác vụ polling.
- Thêm `maxMessagesPerPoll` không tạo xử lý song song.
- Một messaging gateway gửi request vào queue vẫn có thể đợi reply nếu chữ ký và cấu hình gateway yêu cầu; có queue không tự biến lời gọi thành fire-and-forget.

Khi thêm `taskExecutor` cho poller, lịch kích hoạt và tác vụ thực tế có thêm một lớp ủy quyền. Cần thiết kế số thread, queue của executor và chính sách từ chối cùng nhau; không áp dụng nguyên xi ước lượng tuần tự ở mục 4.2.

### 8.2. Lỗi không tự quay lại lời gọi send đã hoàn tất

Trong ví dụ, chuỗi rỗng sau chuẩn hóa khiến transformer ném exception. Lỗi xảy ra trong tác vụ polling, sau thời điểm producer đã đưa thông điệp vào queue.

Với cơ chế error handling tiêu chuẩn, exception từ tác vụ polling được chuyển thành `ErrorMessage`. Header `errorChannel` của thông điệp, khi có, có thể chọn đích nhận lỗi; nếu không có, error handler dùng đích mặc định được cấu hình. Ví dụ đặt đích đó là `orderFlowErrors`. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

Do đó, ba kết quả cần được quan sát riêng:

| Đầu vào | Nơi quan sát | Điều được xác nhận |
|---|---|---|
| `" order:ab-17 "` | `acceptedOrders` | Payload đã chuẩn hóa và vượt filter |
| `"invalid"` | `rejectedOrders` | Filter chủ động loại theo quy tắc |
| `"   "` | `orderFlowErrors` | Xảy ra lỗi trong xử lý |

Có thông điệp trong error channel chưa có nghĩa hệ thống đã retry hoặc phục hồi thành công. Cần một consumer hoặc cơ chế vận hành tiếp tục xử lý queue lỗi.

Với `QueueChannel` trong bộ nhớ, thông điệp đã được lấy khỏi queue trước khi handler thực thi xong. Handler thất bại không tự đưa thông điệp trở lại queue. Khi thiết kế retry hoặc phát lại lỗi, hãy xác định thao tác nghiệp vụ nào có thể lặp lại và dùng khóa định danh đơn hàng để tránh tác dụng phụ trùng.

## 9. Sức chứa, thứ tự và độ bền

### 9.1. Queue đầy gây áp lực lên producer

Giả sử `orderQueue` có capacity 100 và phía xử lý chậm hơn phía gửi. Queue sẽ tăng dần đến giới hạn. Producer cần xử lý kết quả trả về của `send(message, timeout)`:

~~~java
boolean accepted = orderQueue.send(message, 500);

if (!accepted) {
    // Ví dụ: trả trạng thái bận cho bên gọi hoặc dùng cơ chế nhận lại đã thiết kế.
}
~~~

Cần lựa chọn hành vi khi hết thời gian chờ phù hợp với hợp đồng của ứng dụng. Bỏ qua `false` có thể khiến phía gọi tưởng yêu cầu đã được tiếp nhận.

Các queue output và error cũng có giới hạn. Trong ví dụ học tập, kiểm thử sẽ lấy thông điệp ra khỏi chúng; khi triển khai dài hạn cần consumer tương ứng để tránh dồn kết quả. Quy tắc chờ khi queue đầy và thao tác timeout được trình bày tại [QueueChannel](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html#queuechannel).

### 9.2. Lấy ra theo thứ tự không bảo đảm hoàn thành theo thứ tự

Một queue FIFO với một tuyến xử lý tuần tự giúp việc theo dõi thứ tự đơn giản. Nếu nhiều consumer cùng đọc hoặc xử lý chạy song song, thông điệp lấy ra trước vẫn có thể hoàn thành sau.

Ví dụ, đơn hàng A gọi dịch vụ mất 2 giây còn B mất 50 ms. Khi hai đơn được xử lý song song, kết quả B có thể xuất hiện trước A. Nếu nghiệp vụ yêu cầu thứ tự theo khách hàng, cần thiết kế cách phân phối và tuần tự hóa theo khóa đó.

### 9.3. Queue trong bộ nhớ không phải lưu trữ bền vững

Các queue mặc định trong ví dụ nằm trong tiến trình. Khi tiến trình kết thúc, thông điệp chưa được xử lý không có bảo đảm được khôi phục.

Cấu hình transaction cho poller cũng không tự biến queue RAM thành tài nguyên có khả năng rollback hoặc lưu bền vững. Khi cần bảo đảm dữ liệu, phải lựa chọn message store hay broker phù hợp và xác định tài nguyên tham gia transaction.

Transaction thông thường gắn với thread; một queue hoặc executor ở giữa flow tạo điểm bàn giao sang quá trình xử lý khác. Cần đánh giá phạm vi commit và rollback tại từng điểm bàn giao. Xem [Transaction Boundaries](https://docs.spring.io/spring-integration/reference/6.5/transactions.html#transaction-boundaries).

## 10. Kiểm thử luồng từ PollableChannel

Kiểm thử nên xác nhận được kết quả quan sát, có thời gian chờ giới hạn và tách trạng thái giữa các trường hợp. Có thể dùng JUnit Jupiter cùng `spring-test`; với dự án Spring Boot, bộ test thường được cung cấp qua `spring-boot-starter-test`.

Lớp dưới đây sử dụng cấu hình `PollableOrderConfig` ở mục 3. Đặt trong cùng package hoặc import lớp cấu hình nếu đặt khác package:

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(PollableOrderConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class PollableOrderFlowTest {

    @Autowired
    @Qualifier("orderQueue")
    private MessageChannel input;

    @Autowired
    @Qualifier("acceptedOrders")
    private PollableChannel accepted;

    @Autowired
    @Qualifier("rejectedOrders")
    private PollableChannel rejected;

    @Autowired
    @Qualifier("orderFlowErrors")
    private PollableChannel errors;

    @Test
    void acceptsNormalizedOrderAndPreservesTraceId() {
        Message<String> request = MessageBuilder
                .withPayload(" order:ab-17 ")
                .setHeader("traceId", "trace-test-001")
                .build();

        assertTrue(input.send(request, 500));

        Message<?> result = accepted.receive(3_000);

        assertNotNull(result);
        assertEquals("ORDER:AB-17", result.getPayload());
        assertEquals(
                "trace-test-001",
                result.getHeaders().get("traceId"));
    }

    @Test
    void discardsPayloadThatFailsBusinessRule() {
        assertTrue(input.send(
                MessageBuilder.withPayload("invalid").build(),
                500));

        Message<?> discarded = rejected.receive(3_000);

        assertNotNull(discarded);
        assertEquals("INVALID", discarded.getPayload());
        assertNull(accepted.receive(0));
    }

    @Test
    void publishesErrorForBlankPayload() {
        assertTrue(input.send(
                MessageBuilder.withPayload("   ").build(),
                500));

        ErrorMessage error = assertInstanceOf(
                ErrorMessage.class,
                errors.receive(3_000));

        MessagingException failure = assertInstanceOf(
                MessagingException.class,
                error.getPayload());

        Message<?> failedMessage = failure.getFailedMessage();

        assertNotNull(failedMessage);
        assertEquals("   ", failedMessage.getPayload());
        assertNull(accepted.receive(0));
    }
}
~~~

Cách đọc các kiểm thử:

- Kết quả ở nhánh thành công xác nhận cả payload và header nghiệp vụ, thay vì chỉ xác nhận `send` trả về `true`.
- Nhánh discard xác nhận filter được thực thi và thông điệp bị loại là payload đã chuẩn hóa.
- Nhánh lỗi đọc `ErrorMessage` rồi kiểm tra thông điệp thất bại; không yêu cầu producer bắt exception nghiệp vụ ngay tại `send`.
- Mỗi phương thức có context riêng sau khi context trước bị đánh dấu dirty, tránh thông điệp của trường hợp trước lọt sang trường hợp sau.
- `receive(3_000)` chờ theo điều kiện có dữ liệu với hạn chót. Không cần `Thread.sleep` hay vòng lặp bận.
- `receive(0)` chỉ kiểm tra tức thời queue output sau khi đã quan sát nhánh cuối tương ứng; không phải bằng chứng tổng quát rằng tương lai sẽ không có thông điệp trùng.

Không gọi `orderQueue.receive(...)` trong test để kiểm tra payload nếu flow đang tiêu thụ chính queue đó. Lời gọi ấy sẽ cạnh tranh với endpoint và có thể lấy mất thông điệp trước khi flow xử lý.

## 11. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Khả năng cần kiểm tra | Hướng xử lý |
|---|---|---|
| Context báo thiếu poller | Endpoint đọc queue không có poller riêng và không có default poller | Cấu hình endpoint tiêu thụ queue hoặc bổ sung default poller |
| Producer gửi được nhưng queue không giảm | Endpoint chưa chạy, sai instance channel hoặc đang tắc downstream | Kiểm tra lifecycle, bean được truyền vào và các queue phía sau |
| Queue giảm nhưng không thấy output | Filter loại thông điệp, handler lỗi hoặc output đang được consumer khác đọc | Kiểm tra discard channel, error channel và toàn bộ consumer |
| Poller giữ thread lâu khi ít dữ liệu | Receive timeout dài hoặc handler thực hiện thao tác chậm | Đo thời gian nhận, thời gian handler; cấu hình timeout đúng thành phần |
| Tăng maxMessagesPerPoll nhưng không thấy song song | Tham số chỉ giới hạn số lần nhận trong tác vụ | Đánh giá kiến trúc thread hoặc executor theo nhu cầu |
| Kết quả đến không đúng thứ tự | Nhiều consumer hoặc có xử lý song song | Xác định yêu cầu thứ tự và điểm phân phối thông điệp |
| Dữ liệu biến mất khi khởi động lại | Queue đang lưu trong bộ nhớ | Thiết kế lưu trữ bền vững phù hợp |
| Test lúc qua lúc lỗi | Đọc cạnh tranh input, dùng sleep cố định hoặc dùng chung queue giữa test | Quan sát output có timeout và cô lập trạng thái test |

Để bắt đầu một flow từ `PollableChannel`, hãy xác định đúng instance channel, endpoint sẽ lấy dữ liệu và cấu hình poller của endpoint đó. Sau đó xác định cách quan sát thành công, loại bỏ và lỗi. Ba quyết định này là nền tảng để nối tiếp transformer, router, filter hoặc aggregator mà vẫn hiểu được lịch xử lý và đường đi của thông điệp.
