# PublishSubscribeChannel và nhiều subscriber

Trong **Spring Integration**, `PublishSubscribeChannel` triển khai mẫu **Publish–Subscribe Channel** của Enterprise Integration Patterns (EIP): một message được gửi đến channel có thể được **phát tới tất cả các handler đã subscribe**. Mẫu này phù hợp khi một sự kiện nghiệp vụ cần kích hoạt nhiều nhánh xử lý độc lập: ghi audit, cập nhật thống kê, gửi thông báo, đồng bộ dữ liệu hoặc theo dõi vận hành.

Bài thuộc chương **Message channel** của module **SPRING_INTEGRATION_PATTERN**. Mục tiêu của module là xây dựng các luồng thông điệp ít phụ thuộc, dễ mở rộng với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation. Ở đây, trọng tâm là cách một channel broadcast tới **nhiều subscriber**, ý nghĩa của xử lý đồng bộ/bất đồng bộ và các hệ quả đối với lỗi, thứ tự, metadata, kiểm thử.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa `PublishSubscribeChannel`, `DirectChannel` và `QueueChannel` khi có nhiều consumer.
2. Tạo channel và đăng ký hai hoặc nhiều `MessageHandler` bằng Java thuần hoặc cấu hình Spring Integration.
3. Phân biệt chế độ **đồng bộ mặc định** với chế độ dùng `Executor` và hiểu ảnh hưởng đến thời gian trả về, lỗi và thread.
4. Xử lý các tình huống **không có subscriber**, subscriber lỗi và giới hạn năng lực xử lý.
5. Dùng `applySequence` khi cần fan-out rồi gom lại bằng Aggregator.
6. Viết kiểm thử chứng minh một message tới nhiều handler và kiểm thử bất đồng bộ bằng `CountDownLatch`.
7. Thiết kế fan-out an toàn khi payload hoặc header chứa dữ liệu mutable.

## 2. Tư duy Publish–Subscribe

Giả sử dịch vụ checkout đã xác nhận đơn hàng `ORDER-1001`. Một sự kiện `OrderPlaced` cần đến ba nơi:

- **Audit handler**: lưu lịch sử thao tác.
- **Notification handler**: gửi email hoặc thông báo.
- **Analytics handler**: cập nhật chỉ số bán hàng.

Nếu mỗi nơi subscribe vào cùng một `PublishSubscribeChannel`, một lệnh `send(message)` sẽ phân phối sự kiện cho các handler này.

~~~mermaid
flowchart LR
    P["Checkout: OrderPlaced"] --> C(("PublishSubscribeChannel"))
    C --> A["Subscriber 1: Audit"]
    C --> N["Subscriber 2: Notify"]
    C --> S["Subscriber 3: Analytics"]
~~~

Đây là **fan-out/broadcast**: mỗi subscriber nhận một thông điệp để xử lý phần việc riêng. Cách thiết kế không buộc checkout gọi trực tiếp cả ba service, nhờ đó có thể thêm subscriber mà không phải viết lại nguồn phát sự kiện.

Một chi tiết quan trọng: `PublishSubscribeChannel` là channel **trong ứng dụng Spring Integration**, hoạt động với các handler đang subscribe. Bản thân channel này **không phải message broker bền vững** và không lưu message chờ subscriber xuất hiện. Muốn có persistence, replay, phân phối xuyên tiến trình hoặc bảo đảm giao hàng khi hệ thống tắt, cần thêm hạ tầng tương ứng như Kafka, RabbitMQ, JMS hay cơ chế outbox, với các bảo đảm riêng.

### 2.1. So sánh các channel thường dùng

| Thuộc tính | `DirectChannel` | `PublishSubscribeChannel` | `QueueChannel` |
|---|---|---|---|
| Cơ chế | Unicast: chọn một handler cho mỗi message | Broadcast: gửi tới tất cả handler đang subscribe | Lưu message trong hàng đợi để consumer poll |
| Có nhiều handler | Mặc định có thể load-balance/failover giữa handlers | Mọi subscriber có cơ hội nhận | Consumer tranh lấy message từ queue |
| Cách consumer nhận | Handler được gọi khi send | Handler được gọi khi send | `receive()` / polling |
| Đồng bộ mặc định | Có | Có | Sender và receiver tách qua queue |
| Phù hợp | Một nhánh xử lý hoặc chia tải | Sự kiện cần nhiều tác vụ độc lập | Giảm coupling thời gian, buffering |
| Tự bảo đảm lưu bền vững | Không | Không | Queue mặc định in-memory; độ bền tùy triển khai |

**Không nhầm fan-out với load-balancing.** Hai subscriber của `DirectChannel` không mặc nhiên mỗi người nhận bản sao; ở `PublishSubscribeChannel`, đích thiết kế chính là phân phối tới tất cả.

### 2.2. Các interface liên quan

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;

// MessageChannel: producer gọi send(message)
// SubscribableChannel: thêm subscribe(handler), unsubscribe(handler)
// MessageHandler: consumer triển khai handleMessage(message)
~~~

`PublishSubscribeChannel` triển khai `SubscribableChannel`. Subscriber được gọi thông qua `handleMessage(Message<?>)`. Nó không triển khai `PollableChannel` nên không có `receive()` giống `QueueChannel`.

## 3. Ví dụ Java thuần: một sự kiện tới ba handler

Đây là minh họa nhỏ, không cần khởi động toàn bộ Spring application context. Đặt phương thức `main` trong một class Java dùng Spring Integration.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

public class PublishSubscribeDemo {

    public static void main(String[] args) {
        PublishSubscribeChannel events = new PublishSubscribeChannel();

        AtomicInteger auditCalls = new AtomicInteger();
        AtomicInteger emailCalls = new AtomicInteger();
        AtomicInteger analyticsCalls = new AtomicInteger();

        MessageHandler audit = message -> {
            auditCalls.incrementAndGet();
            System.out.println("AUDIT: " + message.getPayload());
        };

        MessageHandler email = message -> {
            emailCalls.incrementAndGet();
            System.out.println("EMAIL: " + message.getPayload());
        };

        MessageHandler analytics = message -> {
            analyticsCalls.incrementAndGet();
            System.out.println("METRICS: " + message.getPayload());
        };

        events.subscribe(audit);
        events.subscribe(email);
        events.subscribe(analytics);

        Message<String> event = MessageBuilder
                .withPayload("ORDER-1001")
                .setHeader("eventType", "OrderPlaced")
                .setHeader("traceId", "trace-1001")
                .build();

        boolean accepted = events.send(event);

        System.out.printf("accepted=%s, audit=%d, email=%d, metrics=%d%n",
                accepted, auditCalls.get(), emailCalls.get(),
                analyticsCalls.get());
        // Với ba handler thành công và không dùng Executor:
        // accepted=true, audit=1, email=1, metrics=1

        events.unsubscribe(email);  // chỉ ngừng nhận các message gửi sau đó
    }
}
~~~

Vì ví dụ dùng constructor không truyền `Executor`, các handler chạy **trên thread gọi `events.send(...)`**. Khi không có lỗi, cả ba handler đã xử lý xong trước khi `send` trả về. Dòng `unsubscribe(email)` ở cuối không ảnh hưởng đến message đã phân phối; lần gửi tiếp theo chỉ tới các subscriber còn đăng ký.

Nếu subscriber đang xử lý chậm, thread gửi sẽ phải chờ. Với giao diện HTTP/Gateway yêu cầu phản hồi nhanh, hãy tính đến thời gian của toàn bộ fan-out hoặc cân nhắc dispatch bất đồng bộ.

## 4. Đăng ký nhiều subscriber trong một Spring application

Trong ứng dụng Spring, thường khai báo channel là bean và để các endpoint tự subscribe theo `inputChannel`. Cách này có cấu trúc rõ hơn so với đăng ký handler thủ công trong mã khởi động.

### 4.1. Tạo channel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;

@Configuration
public class ChannelConfiguration {

    @Bean
    public PublishSubscribeChannel orderEvents() {
        return new PublishSubscribeChannel();
    }
}
~~~

Bean `orderEvents` dùng làm channel chung của nhiều endpoint.

### 4.2. Hai Service Activator cùng nhận sự kiện

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class AuditSubscriber {

    @ServiceActivator(inputChannel = "orderEvents")
    public void onEvent(Message<OrderPlaced> message) {
        System.out.println("Audit order: "
                + message.getPayload().orderId());
    }
}

@Component
public class NotificationSubscriber {

    @ServiceActivator(inputChannel = "orderEvents")
    public void onEvent(Message<OrderPlaced> message) {
        System.out.println("Notify order: "
                + message.getPayload().orderId());
    }
}

// Immutable DTO (Java 17+)
record OrderPlaced(String orderId, String customerId) {}
~~~

Mỗi phương thức `@ServiceActivator(inputChannel = "orderEvents")` trở thành một consuming endpoint subscribe vào channel. Khi cùng một message đi vào `orderEvents`, cả `AuditSubscriber` và `NotificationSubscriber` đều có cơ hội nhận nó. Tùy yêu cầu, có thể có subscriber thứ ba cho analytics hoặc cache invalidation.

### 4.3. Producer gửi message

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class CheckoutPublisher {

    private final MessageChannel orderEvents;

    public CheckoutPublisher(
            @Qualifier("orderEvents") MessageChannel orderEvents) {
        this.orderEvents = orderEvents;
    }

    public boolean publish(String orderId, String customerId) {
        return orderEvents.send(
                MessageBuilder
                        .withPayload(new OrderPlaced(orderId, customerId))
                        .setHeader("eventType", "OrderPlaced")
                        .setHeader("businessCorrelationId", orderId)
                        .build()
        );
    }
}
~~~

Đây là ba đoạn thuộc cùng ví dụ Spring. `record OrderPlaced` chỉ nhằm giúp payload có kiểu rõ ràng; với dự án thực tế cần đặt ở package dùng chung cho producer/subscribers, import tương ứng và cấu hình component scanning. Sự kiện đặt tên ở quá khứ (`OrderPlaced`) thể hiện một điều đã xảy ra, khác với command như `SendEmail`.

**Giới hạn quan trọng:** fan-out trong tiến trình không biến ba side effect thành một giao dịch nguyên tử. Nếu audit thành công nhưng notification lỗi, hệ thống phải có chiến lược xử lý từng subscriber hoặc bảo đảm bù trừ/idempotency tùy nghiệp vụ.

## 5. Đồng bộ mặc định và bất đồng bộ với Executor

`PublishSubscribeChannel` mặc định gọi subscriber trong thread của người gửi. Constructor có `Executor` cho phép dispatch các handler bằng executor thay vì thực thi nối tiếp trên thread gửi.

~~~mermaid
flowchart TB
    subgraph sync["Mặc định: không có Executor"]
        S1["Sender thread"] --> H1["Handler A"]
        H1 --> H2["Handler B"]
        H2 --> H3["Handler C"]
        H3 --> R1["send() trả về"]
    end
    subgraph async["Có Executor"]
        S2["Sender thread"] --> Q["Executor / task scheduling"]
        Q --> R2["send() có thể trả về trước"]
        Q --> A["Worker: Handler A"]
        Q --> B["Worker: Handler B"]
        Q --> D["Worker: Handler C"]
    end
~~~

| Vấn đề | Không `Executor` | Có `Executor` |
|---|---|---|
| Thread xử lý | Thread của caller | Các thread do executor cấp |
| `send()` trả về | Sau khi các handler được gọi và hoàn thành bình thường | Có thể trước khi handler xử lý xong |
| Tốc độ producer | Bị ảnh hưởng bởi handler chậm | Ít bị chặn bởi thời gian handler, nhưng vẫn chịu việc submit task và áp lực executor |
| Thứ tự thực thi | Có trình tự dispatch trong một thread; không tự suy diễn thứ tự nghiệp vụ nếu không cấu hình | Không bảo đảm thứ tự hoàn thành giữa các handler |
| Exception từ handler | Có thể truyền ngược tới caller | Được xử lý qua cơ chế error handling của task, không đơn thuần ném ngược tới caller |
| Context theo thread / transaction | Tiếp tục cùng thread, nhưng ranh giới transaction vẫn phụ thuộc cấu hình | Transaction/thread-local của caller không tự truyền sang worker |
| Thời điểm kiểm thử | Có thể assert ngay sau `send()` | Cần đồng bộ hóa, latch, future hoặc cơ chế chờ được kiểm soát |

### 5.1. Cấu hình executor có giới hạn

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncChannelConfiguration {

    @Bean
    public ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-event-");
        return executor;
    }

    @Bean
    public PublishSubscribeChannel asyncOrderEvents(
            ThreadPoolTaskExecutor eventExecutor) {
        return new PublishSubscribeChannel(eventExecutor);
    }
}
~~~

Các con số `2 / 4 / 100` chỉ là ví dụ để thấy cấu hình hữu hạn; cần hiệu chỉnh theo thời gian xử lý subscriber, tỷ lệ sự kiện, bộ nhớ và chính sách quá tải. Spring quản lý vòng đời executor bean trong application context. Không dùng bộ thực thi không giới hạn theo thói quen khi handler có thể bị chậm vì mạng hoặc database.

**Lưu ý tên bean:** ví dụ `asyncOrderEvents` là một channel khác với `orderEvents` ở mục trước. Muốn chuyển các subscriber sang bất đồng bộ, hãy trỏ `inputChannel` của các endpoint tới `asyncOrderEvents` hoặc thay thế cấu hình channel theo quyết định kiến trúc, tránh có hai bean cùng tên.

### 5.2. Điều gì xảy ra khi có một subscriber chậm?

Nếu subscriber gửi email mất 2 giây, trong cấu hình đồng bộ, `send()` của producer có thể bị chậm theo. Trong cấu hình bất đồng bộ, sender có thể trả về nhanh hơn vì công việc được giao cho executor. Nhưng nếu queue đầy hoặc pool bị từ chối nhiệm vụ, quá trình submit vẫn có thể thất bại. Một `send()` thành công trong chế độ async **không chứng minh email đã gửi thành công**.

Cũng không được giả định `A` hoàn thành trước `B` dù `A` được đăng ký trước. Nếu nghiệp vụ yêu cầu xử lý tuần tự bắt buộc, hãy dùng luồng có quan hệ phụ thuộc rõ ràng thay vì dựa vào thứ tự fan-out.

## 6. Subscriber lỗi: hai mô hình xử lý khác nhau

Khi một handler ném exception, cách xử lý phụ thuộc vào channel có dùng executor hay không.

### 6.1. Đồng bộ: lỗi có thể quay về caller

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();

channel.subscribe(message -> {
    throw new IllegalStateException("Audit storage unavailable");
});

channel.send(MessageBuilder.withPayload("ORDER-1001").build());
// Mặc định lỗi của subscriber có thể nổi lên từ lời gọi send().
~~~

Không nên giả định các subscriber phía sau chắc chắn đã nhận message khi một handler trước đó lỗi. Hãy xác định nhu cầu: dừng xử lý và báo lỗi ngay, hay tiếp tục phát tới những subscriber khác.

`setIgnoreFailures(true)` cho phép channel bỏ qua exception từ subscriber trong quá trình dispatch thay vì làm lời gọi thất bại bởi các exception đó. Chỉ dùng khi việc bỏ qua lỗi có chủ đích và vẫn có khả năng quan sát lỗi. Nếu handler đóng vai trò bắt buộc trong nghiệp vụ, việc tắt tiếng lỗi có thể tạo ấn tượng sai rằng toàn bộ công việc đã thành công.

~~~java
PublishSubscribeChannel bestEffortEvents = new PublishSubscribeChannel();
bestEffortEvents.setIgnoreFailures(true);

// Cấu hình kiểu best-effort chỉ phù hợp với subscriber
// mà thất bại của nó có thể được chấp nhận và được giám sát.
~~~

### 6.2. Bất đồng bộ: ErrorHandler và error channel

Khi cung cấp `Executor`, `PublishSubscribeChannel` dùng cơ chế `ErrorHandler` để xử lý lỗi phát sinh ở các task subscriber. Mặc định Spring Integration sử dụng `MessagePublishingErrorHandler` để phát error message tới channel trong header `errorChannel` nếu được khai báo, hoặc error channel toàn cục khi phù hợp.

Nếu **không** cấu hình executor, `ErrorHandler` của channel không xử lý exception theo con đường này; exception đi trực tiếp trên caller thread. Cần nhớ khác biệt này khi chuyển từ sync sang async.

Gợi ý thiết kế:

- Đặt `errorChannel` hoặc endpoint xử lý lỗi ở nơi thích hợp với luồng.
- Log kèm message ID, correlation ID nghiệp vụ, tên subscriber và exception, đồng thời tránh ghi dữ liệu nhạy cảm.
- Dùng retry có giới hạn cho lỗi tạm thời; kết hợp idempotency để không gửi email hay ghi side effect trùng lặp.
- Với tác vụ bắt buộc phải đến đích, cân nhắc broker hoặc outbox thay vì chỉ dựa vào dispatch in-memory.

**Một event gửi cho ba subscriber không có nghĩa ba kết quả được commit cùng lúc.** Ví dụ audit thành công, analytics thành công nhưng notification lỗi: trạng thái partial success cần được thiết kế rõ.

## 7. Trường hợp không có subscriber: minSubscribers và requireSubscribers

Mặc định `minSubscribers` là `0`. Vì vậy `send()` có thể trả về `true` dù channel chưa có subscriber nào, theo hành vi được tài liệu Spring Integration mô tả. Nếu message quan trọng, đừng xem `true` là bằng chứng đã có consumer xử lý.

Có hai cơ chế liên quan nhưng cần phân biệt:

| Cấu hình | Ý nghĩa |
|---|---|
| `setMinSubscribers(n)` | Yêu cầu đạt ngưỡng tối thiểu subscriber nhận được message để `send()` trả về `true`; mặc định 0 |
| `requireSubscribers=true` | Khi không có subscriber, phát sinh `MessageDispatchingException` thay vì âm thầm coi như thành công |

Ví dụ sync:

~~~java
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

PublishSubscribeChannel defaultChannel = new PublishSubscribeChannel();
Message<String> event = MessageBuilder.withPayload("ORDER-1001").build();

boolean accepted = defaultChannel.send(event);
// Theo mặc định, có thể là true ngay cả khi không có subscriber.

PublishSubscribeChannel strictChannel = new PublishSubscribeChannel(true);
// strictChannel.send(event) sẽ ném MessageDispatchingException
// khi hoàn toàn không có subscriber.

PublishSubscribeChannel twoRequired = new PublishSubscribeChannel();
twoRequired.setMinSubscribers(2);
// Với 1 subscriber thành công, send không đáp ứng ngưỡng 2.
~~~

Constructor `PublishSubscribeChannel(true)` dùng để bật yêu cầu có subscriber (API từ phiên bản được Spring hỗ trợ). `minSubscribers` và `requireSubscribers` giải quyết **vấn đề số lượng/không có subscriber**; cả hai không biến việc xử lý thành giao dịch nguyên tử hay xác nhận thành công nghiệp vụ ở chế độ async.

Trong Spring application, thời điểm endpoint đăng ký phụ thuộc vòng đời/startup. Có thể gặp trường hợp channel đã tồn tại nhưng endpoint chưa start hoặc bị stop. Khi yêu cầu nghiêm ngặt, cần kiểm tra cấu hình start và số subscriber thực tế.

## 8. Khi nào cần applySequence?

Mặc định `applySequence=false`. Channel có thể phát **cùng một Message instance** đến nhiều subscriber. Khi đặt `applySequence=true`, framework tạo message mới cho các nhánh, mang metadata sequence và correlation để hỗ trợ việc gom lại.

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
channel.setApplySequence(true);

channel.subscribe(message -> handleA(message));
channel.subscribe(message -> handleB(message));

// Khi dispatch, mỗi nhánh có sequenceNumber riêng,
// sequenceSize phù hợp số subscriber và cùng correlation ID.
~~~

Giả sử có ba subscriber:

| Subscriber | Correlation ID | Sequence number | Sequence size |
|---|---|---:|---:|
| Audit | Cùng một correlation key của lần fan-out | 1 | 3 |
| Notification | Cùng correlation key | 2 | 3 |
| Analytics | Cùng correlation key | 3 | 3 |

Các header này giúp thiết kế `Aggregator` hoặc `Resequencer` ở downstream, **nếu các nhánh thật sự đưa message tương ứng quay về cùng điểm tập hợp**.

~~~mermaid
flowchart LR
    P["Event"] --> C["PubSub: applySequence=true"]
    C --> A["Branch A"]
    C --> B["Branch B"]
    C --> D["Branch C"]
    A --> G["Aggregator"]
    B --> G
    D --> G
    G --> R["Kết quả tổng hợp"]
~~~

Có ba điều phải phân biệt:

1. `applySequence` chỉ chuẩn bị headers để liên kết các nhánh; **nó không tự tạo Aggregator**, không bảo đảm các nhánh trả kết quả và không đợi cho đủ ba kết quả.
2. Nếu một nhánh filter/drop message hoặc lỗi, Aggregator có thể không bao giờ nhận đủ nhóm; cần `releaseStrategy`, timeout và chính sách xử lý nhóm thiếu.
3. Metadata sequence thay đổi theo số subscriber đang có lúc phân phối; không dùng nó làm định danh nghiệp vụ ổn định qua nhiều lần publish.

Với một luồng fan-out chỉ nhằm phát thông báo độc lập, thông thường **không cần** `applySequence=true`. Khi cần fan-out rồi fan-in, hãy thiết kế rõ correlation, trạng thái từng nhánh và cách giải phóng nhóm.

## 9. Tính bất biến và an toàn khi nhiều handler nhận cùng một message

Tính bất biến của `MessageHeaders` chặn thay đổi **cấu trúc map headers** qua API công khai; nó **không tự động deep-copy payload hoặc các object mutable trong header**. Với `applySequence=false`, nhiều subscriber có thể cùng cầm tham chiếu tới chính message và payload.

Ví dụ không an toàn:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

List<String> tags = new ArrayList<>(List.of("new"));
Message<List<String>> event = MessageBuilder.withPayload(tags).build();

PublishSubscribeChannel channel = new PublishSubscribeChannel();

channel.subscribe(message -> {
    @SuppressWarnings("unchecked")
    List<String> received = (List<String>) message.getPayload();
    received.add("audit"); // Mutate payload chung: không nên làm
});

channel.subscribe(message -> {
    System.out.println(message.getPayload());
    // Kết quả phụ thuộc việc handler khác có sửa list không.
});

channel.send(event);
~~~

Với executor, tình huống này còn có race condition; ngay cả sync cũng tạo phụ thuộc ẩn giữa các subscriber. Khuyến nghị:

- Dùng immutable DTO như `record OrderPlaced(String orderId, String customerId)`, với các trường tự thân bất biến.
- Dùng `List.copyOf` / `Map.copyOf` để snapshot collections trước khi publish; lưu ý với cấu trúc lồng nhau phải xử lý deep copy khi cần.
- Subscriber muốn thay đổi dữ liệu thì tạo message hoặc object đầu ra riêng trong nhánh đó; không mutate input.
- Không để subscriber A dựa vào side effect nội bộ của subscriber B để có thể chạy đúng.

Khi `applySequence=true`, framework tạo message mới với headers khác nhau, **nhưng payload reference có thể vẫn chung**. Bật sequence không giải quyết vấn đề mutable payload.

## 10. Tích hợp PublishSubscribeChannel vào Enterprise Integration Patterns

Fan-out là một công cụ phối hợp nhiều pattern khác nhau:

### 10.1. Filter và Router

`Router` giúp chọn một hay nhiều đích tùy điều kiện nghiệp vụ; `PublishSubscribeChannel` phát tới toàn bộ subscriber đang đăng ký. Nếu mỗi subscriber có điều kiện riêng, có thể đặt `Filter` trong từng nhánh sau điểm publish, hoặc dùng Router/Recipient List Router ở tầng trước để chọn nơi phát phù hợp.

~~~mermaid
flowchart LR
    A["Incoming event"] --> F["Validate / Normalize"]
    F --> C["PublishSubscribeChannel"]
    C --> SA["Branch A: Filter -> Audit"]
    C --> SB["Branch B: Filter -> Notification"]
    C --> SC["Branch C: Transform -> Analytics"]
~~~

Điều này giúp mỗi nhánh có logic riêng nhưng dùng chung sự kiện đầu vào. Khi yêu cầu chỉ chọn **một** handler xử lý chính, `DirectChannel` hoặc Router tới một nhánh thường phù hợp hơn.

### 10.2. Transformer và Gateway

Nếu một subscriber dùng Transformer, việc chuyển đổi payload của nhánh đó không được làm thay đổi payload đang quan sát bởi subscriber khác. Gateway có thể là điểm khởi phát message từ service hoặc HTTP request; trong trường hợp cần reply đơn nhất, phải xác định rõ ai là người tạo reply. **Không mặc định dùng fan-out nhiều service activator trả reply cho một Gateway mà chưa có Aggregator/cơ chế phối hợp**, vì có thể sinh nhiều reply cho một request.

### 10.3. Splitter/Aggregator và correlation

Mẫu `Splitter` tách một payload thành nhiều phần; `PublishSubscribeChannel` nhân một message tới nhiều subscriber. Cả hai tạo nhiều nhánh xử lý nhưng khác ý nghĩa:

- Splitter thường phát các phần **khác nhau** của dữ liệu gốc.
- Publish–subscribe thường phát **cùng thông báo sự kiện** cho các consumer khác nhau.
- Aggregator gom theo correlation key và release strategy, phải nhận đủ đầu ra theo hợp đồng.

Nếu mỗi nhánh publish xử lý khác nhau và gửi kết quả đến Aggregator, cần bảo đảm correlation ID, sequence, thất bại từng nhánh và xử lý timeout nhất quán.

### 10.4. Retry, error channel và tracing

Trong hệ thống nhiều subscriber, retry nên được thiết kế theo phạm vi **handler**: một lần retry notification không nhất thiết phải chạy lại audit và analytics. Nếu retry ở producer rồi publish lại toàn bộ event, cả ba subscriber có thể nhận thêm một lần. Hãy định nghĩa event ID nghiệp vụ ổn định, idempotency key và thông tin tracing trước khi triển khai.

## 11. Kiểm thử: broadcast, không có subscriber và async

Các test sau dùng JUnit Jupiter 5 và API `spring-integration-core`. Chúng được viết để chạy ở mức channel, chưa yêu cầu Spring Boot context.

### 11.1. Một message đến tất cả subscriber

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PublishSubscribeChannelTest {

    @Test
    void oneEventReachesEverySubscriber() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();

        AtomicInteger audit = new AtomicInteger();
        AtomicInteger notify = new AtomicInteger();
        AtomicInteger analytics = new AtomicInteger();

        channel.subscribe(message -> audit.incrementAndGet());
        channel.subscribe(message -> notify.incrementAndGet());
        channel.subscribe(message -> analytics.incrementAndGet());

        Message<String> event =
                MessageBuilder.withPayload("ORDER-1001").build();

        assertTrue(channel.send(event));
        assertEquals(1, audit.get());
        assertEquals(1, notify.get());
        assertEquals(1, analytics.get());
        assertEquals(3, channel.getSubscriberCount());
    }

    @Test
    void noSubscriberCanStillBeAcceptedByDefault() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        assertTrue(channel.send(
                MessageBuilder.withPayload("ORDER-1001").build()));
    }

    @Test
    void missingSubscriberCanBeTreatedAsError() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel(true);
        Message<String> event =
                MessageBuilder.withPayload("ORDER-1001").build();

        assertThrows(RuntimeException.class,
                () -> channel.send(event));
    }
}
~~~

Test thứ ba dùng `RuntimeException` nhằm tránh gắn kiểm thử với cách wrap exception quá cụ thể trong ví dụ khởi đầu. Khi viết kiểm thử tích hợp thực tế, nên assert đúng `MessageDispatchingException` và thông điệp lỗi theo phiên bản thư viện đang sử dụng.

### 11.2. Kiểm thử async bằng latch

Không nên viết kiểm thử `assertEquals(2, counter.get())` ngay sau `send()` trong chế độ async, vì các handler có thể chưa kịp chạy. Dùng `CountDownLatch` để chờ một số tín hiệu xác định:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

class AsyncPublishSubscribeTest {

    @Test
    void executorDeliversToTwoSubscribers() throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            PublishSubscribeChannel channel =
                    new PublishSubscribeChannel(executor);

            CountDownLatch delivered = new CountDownLatch(2);
            AtomicInteger completed = new AtomicInteger();

            channel.subscribe(message -> {
                completed.incrementAndGet();
                delivered.countDown();
            });

            channel.subscribe(message -> {
                completed.incrementAndGet();
                delivered.countDown();
            });

            assertTrue(channel.send(
                    MessageBuilder.withPayload("ORDER-1001").build()));

            assertTrue(delivered.await(5, TimeUnit.SECONDS),
                    "Expected both subscribers to complete");
            assertEquals(2, completed.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Thời gian 5 giây ở test chỉ là timeout kiểm thử, không phải SLA sản xuất. `CountDownLatch` đếm callback đã chạy trong ví dụ; nếu cần xác nhận kết quả nghiệp vụ, hãy kiểm tra output/state thực và cơ chế error handling.

### 11.3. Kiểm thử propagation và applySequence

Nếu downstream dùng `Aggregator`, test nên kiểm tra rằng số phần và correlation key nhất quán theo cấu hình, không chỉ kiểm tra các subscriber đã được gọi. Ví dụ ở mức hành vi:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class SequenceHeaderTest {

    @Test
    void fanOutCanAddCorrelationAndSequence() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        channel.setApplySequence(true);

        List<Message<?>> seen = new ArrayList<>();
        channel.subscribe(seen::add);
        channel.subscribe(seen::add);

        assertTrue(channel.send(
                MessageBuilder.withPayload("ORDER-1001").build()));
        assertEquals(2, seen.size());

        IntegrationMessageHeaderAccessor first =
                new IntegrationMessageHeaderAccessor(seen.get(0));
        IntegrationMessageHeaderAccessor second =
                new IntegrationMessageHeaderAccessor(seen.get(1));

        assertEquals(2, first.getSequenceSize());
        assertEquals(2, second.getSequenceSize());
        assertNotNull(first.getCorrelationId());
        assertEquals(first.getCorrelationId(), second.getCorrelationId());
        assertEquals(Set.of(1, 2),
                Set.of(first.getSequenceNumber(), second.getSequenceNumber()));
    }
}
~~~

Test này dùng dispatch đồng bộ và so sánh tập hợp số thứ tự, nhờ vậy không phụ thuộc thứ tự gọi giữa hai subscriber. Nếu thử nghiệm async, dùng collection thread-safe và chờ bằng latch.

## 12. Thiết kế tình huống thực tế: xử lý OrderPlaced

Xây một luồng có Gateway hoặc inbound adapter nhận đơn hàng đã được lưu thành công, sau đó publish `OrderPlaced` đến ba subscriber:

| Nhánh | Trách nhiệm | Thành công được đo bằng | Hướng xử lý lỗi |
|---|---|---|---|
| Audit | Lưu lịch sử | Bản ghi audit được commit | Retry giới hạn; cảnh báo nếu quá số lần |
| Notification | Gửi email | Provider chấp nhận yêu cầu theo hợp đồng | Retry riêng; idempotency bằng event ID |
| Analytics | Cập nhật dashboard | Chỉ số được cập nhật hoặc event được ghi nhận | Cơ chế replay/rebuild nếu cần |

Nên bổ sung `eventId` ổn định qua retry, `traceId` cho việc theo dõi, `occurredAt` trong payload, và `schemaVersion` nếu nhiều consumer cần phát triển độc lập. `MessageHeaders.ID` chỉ là ID của instance message, không đủ làm mã chống xử lý trùng xuyên các lần phát lại.

Một thiết kế giả định:

~~~mermaid
flowchart TB
    A["Checkout xác nhận đơn hàng"] --> B["Tạo OrderPlaced(eventId, orderId)"]
    B --> C["PublishSubscribeChannel"]
    C --> D["Audit handler"]
    C --> E["Notification handler"]
    C --> F["Analytics handler"]
    D --> G["Audit DB"]
    E --> H["Email provider"]
    F --> I["Metrics store"]
    D -. lỗi .-> X["Error / retry policy"]
    E -. lỗi .-> X
    F -. lỗi .-> X
~~~

**Điểm ra quyết định:** nếu tổ chức yêu cầu audit và notification được xử lý ngay cả khi ứng dụng bị dừng giữa chừng, việc chỉ gửi qua `PublishSubscribeChannel` trong tiến trình là không đủ. Hãy tích hợp outbox/broker và xác nhận giao hàng phù hợp, đồng thời giữ logic của từng subscriber độc lập để có thể scale hoặc retry.

## 13. Các lỗi thường gặp và cách chẩn đoán

### Lỗi A — Nhầm PublishSubscribeChannel với hàng đợi

**Triệu chứng:** consumer cố gọi `receive()` trên channel hoặc chờ channel giữ message tới khi subscriber xuất hiện.

**Nguyên nhân:** `PublishSubscribeChannel` chỉ phân phối tới các handler đã subscribe trong lúc dispatch; không phải `PollableChannel`.

**Khắc phục:** dùng `QueueChannel` nếu cần poll/buffering; dùng broker nếu cần lưu bền vững và consumer bên ngoài process.

### Lỗi B — Mong hai subscriber cùng nhận khi đang dùng DirectChannel

**Triệu chứng:** chỉ một handler xử lý mỗi message; số lần gọi không khớp.

**Khắc phục:** kiểm tra loại bean channel. `DirectChannel` có cơ chế phân phối cho một handler; cần `PublishSubscribeChannel` để broadcast.

### Lỗi C — Không có subscriber nhưng producer vẫn báo gửi thành công

**Triệu chứng:** `send()` trả `true`, không thấy log của handler.

**Khắc phục:** kiểm tra subscriber count, trạng thái start của endpoint, tên `inputChannel`, `minSubscribers` và `requireSubscribers`. Đừng xem `send()==true` là xác nhận công việc đã hoàn tất ở mode async.

### Lỗi D — Một handler lỗi làm ảnh hưởng các nhánh khác

**Triệu chứng:** handler cuối không được gọi như dự kiến hoặc sender nhận exception.

**Khắc phục:** làm rõ mục tiêu best-effort hay bắt buộc; cấu hình xử lý lỗi, retry, idempotency theo từng nhánh; bổ sung test cho partial failure. Không che giấu exception chỉ để luồng trông thành công.

### Lỗi E — Async chạy sai thứ tự, đọc dữ liệu không nhất quán

**Triệu chứng:** notification đọc state trước khi giao dịch checkout commit, hoặc analytics nhận trạng thái cũ.

**Khắc phục:** publish sau thời điểm commit thích hợp, tránh phụ thuộc vào ThreadLocal/transaction của caller khi dùng executor; bổ sung correlation và idempotency. Với yêu cầu thứ tự chặt, dùng cơ chế bảo đảm ordering phù hợp.

### Lỗi F — Các subscriber cùng sửa payload

**Triệu chứng:** nhánh A đổi collection, nhánh B quan sát dữ liệu bất ngờ, xảy ra race.

**Khắc phục:** dùng payload bất biến và snapshot các giá trị header mutable. Bản thân channel không clone sâu object được gửi.

### Lỗi G — Bật applySequence mà không có fan-in

**Triệu chứng:** có correlation/sequence headers nhưng không thấy kết quả gộp.

**Khắc phục:** đặt `Aggregator` phù hợp và bảo đảm các nhánh thật sự chuyển kết quả tới cùng nơi. Sequence chỉ cung cấp metadata hỗ trợ; không tự ghép dữ liệu.

## 14. Bài tập thực hành

**Bài 1 — Broadcast cơ bản.** Tạo `PublishSubscribeChannel`, đăng ký ba subscriber ghi `audit`, `notification`, `analytics`. Gửi năm event khác nhau và dùng bộ đếm xác minh mỗi subscriber nhận năm message. Sau đó unsubscribe `analytics`, gửi thêm một event và kiểm tra chỉ hai subscriber còn nhận.

**Bài 2 — Chuyển sang async.** Cấu hình `ExecutorService` có hai worker, thêm `CountDownLatch` để không kiểm thử theo may rủi. Log thread name trong từng handler, quan sát `send()` có thể trả về khi công việc đang chạy.

**Bài 3 — Xử lý lỗi.** Làm cho Notification handler ném lỗi. So sánh việc gọi `send()` trong mode sync với cấu hình async có `ErrorHandler`. Đề xuất retry riêng cho Notification để tránh chạy lại Audit; giải thích vì sao cần event ID ổn định.

**Bài 4 — Fan-out rồi fan-in.** Bật `applySequence`, có ba subscriber trả kết quả về một Aggregator. Kiểm tra số lượng phần được gộp đúng, thử một nhánh không gửi kết quả và bổ sung chính sách timeout. Phân biệt correlation ID với message ID.

**Bài 5 — Tính bất biến.** Gửi payload chứa `ArrayList` tới hai subscriber, chứng minh cách sửa list ở một nhánh ảnh hưởng nhánh kia; thay bằng `List.copyOf` hoặc immutable DTO và viết test ngăn tái diễn.

### Câu hỏi tự kiểm tra

1. Vì sao hai handler cùng subscribe `DirectChannel` không đồng nghĩa cả hai nhận mọi message?
2. Vì sao `PublishSubscribeChannel` không thích hợp để giữ message khi chưa có subscriber?
3. Khi thêm `Executor`, điều gì thay đổi với thời gian trả về của `send()`, exception và transaction?
4. `minSubscribers=0` có ý nghĩa gì? `requireSubscribers=true` giải quyết trường hợp nào?
5. Tại sao `applySequence` hữu ích khi gom nhánh nhưng không đủ để bảo đảm Aggregator hoàn tất?
6. Cần làm gì nếu một subscriber thực hiện side effect thành công nhưng một subscriber khác thất bại?
7. Nếu ba subscriber cùng nhận một `Message<OrderPlaced>`, điều kiện nào giúp chúng xử lý an toàn?

## 15. Ghi nhớ

`PublishSubscribeChannel` hiện thực fan-out trong Spring Integration: khi producer gửi một message, các handler đã subscribe đều được dispatch để xử lý phần việc của mình. Channel chạy **đồng bộ mặc định**; dùng `Executor` để chuyển sang bất đồng bộ, khi đó kết quả `send()` không phản ánh việc các subscriber đã hoàn tất nghiệp vụ. Cần lựa chọn chính sách lỗi, cấu hình số subscriber và xử lý quá tải theo nhu cầu.

Khi dùng nhiều subscriber, ưu tiên event/payload bất biến, từng nhánh độc lập, tracing/correlation rõ ràng và idempotency cho retry. Chỉ bật `applySequence` khi cần metadata hỗ trợ fan-in. Với yêu cầu giao hàng bền vững hoặc xử lý xuyên tiến trình, bổ sung hạ tầng messaging tương ứng.

### Tài liệu tham khảo

- Spring Integration Reference — Message Channel Implementations (`PublishSubscribeChannel`): https://docs.spring.io/spring-integration/reference/channel/implementations.html
- Spring Integration Reference — Configuring Message Channels (Executor, applySequence, error handling, requireSubscribers): https://docs.spring.io/spring-integration/reference/channel/configuration.html
- Spring Integration Java API — `PublishSubscribeChannel`: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html
- Spring Framework Java API — `SubscribableChannel`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html

