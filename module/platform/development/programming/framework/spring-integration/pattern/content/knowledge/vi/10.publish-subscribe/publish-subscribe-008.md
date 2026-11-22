# Xử lý subscriber đăng ký hoặc hủy

Trong mẫu **Publish–Subscribe** của Enterprise Integration Patterns (EIP), một message được phát tới nhiều bên quan tâm mà producer không cần gọi trực tiếp từng bên. Trong **Spring Integration**, `PublishSubscribeChannel` thực hiện việc này bằng cách quản lý danh sách các `MessageHandler` đã đăng ký (*subscribers*). Khi producer gửi message, channel chuyển nó tới những handler thuộc danh sách phân phối tại thời điểm xử lý.

Một hệ thống có thể cần **đăng ký subscriber mới**, **tạm ngừng subscriber** hoặc **hủy đăng ký** khi tính năng được bật/tắt, ứng dụng thay đổi cấu hình hay một thành phần bước vào trạng thái bảo trì. Các thao tác này trông đơn giản nhưng có nhiều hệ quả: handler nào nhận message mới, message đã giao có còn chạy không, nếu danh sách rỗng thì `send()` trả gì, và ứng dụng cần kiểm thử điều đó như thế nào.

Bài thuộc chương **Publish subscribe** của module **SPRING_INTEGRATION_PATTERN**. Module học cách triển khai Enterprise Integration Patterns với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi các nhánh xử lý để xây dựng hệ thống ít phụ thuộc, dễ mở rộng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Hiểu quan hệ giữa `SubscribableChannel`, `PublishSubscribeChannel` và `MessageHandler`.
2. Dùng `subscribe(handler)` và `unsubscribe(handler)`, kiểm tra kết quả `boolean` và số lượng subscriber.
3. Đăng ký nhiều handler; quan sát sự thay đổi trước và sau khi thêm/hủy một subscriber.
4. Phân biệt đăng ký **thủ công** với endpoint được Spring quản lý qua `@ServiceActivator` hoặc `EventDrivenConsumer`.
5. Giải thích ranh giới đồng bộ/bất đồng bộ, xử lý lỗi và ý nghĩa khi unsubscribe trong lúc message đang được xử lý.
6. Chọn chính sách khi **không có subscriber** bằng `requireSubscribers` và `minSubscribers`.
7. Kiểm thử subscription lifecycle, trùng đăng ký, hủy lặp, không có subscriber và một message đang được xử lý.
8. Kết hợp subscriber với Router, Filter, Transformer, correlation, retry và giám sát vận hành.

## 2. Nguyên lý Publish–Subscribe

Giả sử khi có đơn hàng mới, hệ thống phát sự kiện `OrderPlaced` đến ba nhánh độc lập:

- **Audit:** ghi nhận lịch sử hoạt động.
- **Notification:** gửi thông báo cho khách.
- **Analytics:** cập nhật số liệu kinh doanh.

~~~mermaid
flowchart LR
    P["Producer: OrderPlaced"] --> C(("PublishSubscribeChannel"))
    C --> A["Subscriber A: Audit"]
    C --> N["Subscriber B: Notification"]
    C --> M["Subscriber C: Analytics"]
~~~

Nếu chỉ có A và B đã subscribe ở thời điểm gửi `event-1`, C **không được phát lại event-1** khi đăng ký sau đó. C chỉ có cơ hội nhận các message được phát sau khi quá trình đăng ký của C đã có hiệu lực.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as PublishSubscribeChannel
    participant A as Audit
    participant N as Notification
    P->>C: send(event-1)
    C->>A: handleMessage(event-1)
    Note over C,N: Notification chưa subscribe
    N->>C: subscribe(notificationHandler)
    P->>C: send(event-2)
    C->>A: handleMessage(event-2)
    C->>N: handleMessage(event-2)
    N->>C: unsubscribe(notificationHandler)
    P->>C: send(event-3)
    C->>A: handleMessage(event-3)
~~~

**Điểm cần nhớ:** `PublishSubscribeChannel` là cơ chế phân phối trong ứng dụng. Nó không phải một broker có lưu trữ lịch sử để replay event. Khi muốn subscriber mới nhận lại sự kiện cũ hoặc hệ thống phải tiếp tục phát sau khi ứng dụng dừng, hãy dùng hạ tầng lưu bền vững, chẳng hạn broker, outbox hay event log phù hợp.

### So sánh với các channel khác

| Channel | Khi có nhiều consumer | Cách tiêu thụ | Hệ quả khi thêm consumer |
|---|---|---|---|
| `PublishSubscribeChannel` | Broadcast tới mọi subscriber | Handler được gọi | Consumer mới tham gia những lần phân phối tiếp theo |
| `DirectChannel` | Thông thường chọn **một** handler cho một message | Handler được gọi | Có thể thay đổi việc chia tải/failover, không biến thành broadcast |
| `QueueChannel` | Consumer tranh lấy message từ queue | `receive()` hoặc poller | Consumer mới có thể poll những message còn trong queue |
| Broker publish–subscribe | Phụ thuộc topic/subscription, retention, ack | Broker/client riêng | Replay và durability phụ thuộc broker, subscription và chính sách retention |

`PublishSubscribeChannel` triển khai `SubscribableChannel`, **không** triển khai `PollableChannel`. Do đó không gọi `receive()` trực tiếp trên channel này để chờ một message.

## 3. API đăng ký và hủy đăng ký

Interface `org.springframework.messaging.SubscribableChannel` cung cấp:

~~~java
import org.springframework.messaging.MessageHandler;

public interface SubscribableChannel extends MessageChannel {
    boolean subscribe(MessageHandler handler);
    boolean unsubscribe(MessageHandler handler);
}
~~~

Mô tả ở trên chỉ trích hai phương thức liên quan; nó không phải một source file để biên dịch độc lập.

Ý nghĩa giá trị trả về được Spring Framework quy định:

| Lời gọi | `true` | `false` |
|---|---|---|
| `subscribe(handler)` | Handler được thêm vào danh sách đăng ký | Handler đã đăng ký trước đó |
| `unsubscribe(handler)` | Handler được gỡ khỏi danh sách đăng ký | Không có handler tương ứng đang được đăng ký |

Cả hai phương thức nhận một object `MessageHandler`. Để hủy chính xác, ứng dụng cần **giữ lại tham chiếu tới handler đã dùng khi subscribe**. Tạo một lambda mới với cùng phần thân không được coi là cách đáng tin để hủy lambda trước.

`PublishSubscribeChannel` kế thừa `getSubscriberCount()` từ `AbstractSubscribableChannel` để kiểm tra số handler hiện đang đăng ký. Số lượng này hữu ích để quan sát cấu hình và cảnh báo, nhưng **không** phải số message đã xử lý xong.

### 3.1. Ví dụ hoàn chỉnh: thêm rồi hủy một handler

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

public class SubscriptionLifecycleDemo {

    public static void main(String[] args) {
        PublishSubscribeChannel events = new PublishSubscribeChannel();

        AtomicInteger auditCount = new AtomicInteger();
        AtomicInteger notificationCount = new AtomicInteger();

        MessageHandler audit = message -> {
            auditCount.incrementAndGet();
            System.out.println("AUDIT " + message.getPayload());
        };

        MessageHandler notification = message -> {
            notificationCount.incrementAndGet();
            System.out.println("NOTIFY " + message.getPayload());
        };

        boolean firstAuditSubscription = events.subscribe(audit);
        boolean duplicateAuditSubscription = events.subscribe(audit);

        System.out.printf("first=%s, duplicate=%s, count=%d%n",
                firstAuditSubscription,
                duplicateAuditSubscription,
                events.getSubscriberCount());
        // first=true, duplicate=false, count=1

        events.send(MessageBuilder.withPayload("event-1").build());

        events.subscribe(notification);
        events.send(MessageBuilder.withPayload("event-2").build());

        boolean removed = events.unsubscribe(audit);
        boolean removedAgain = events.unsubscribe(audit);
        events.send(MessageBuilder.withPayload("event-3").build());

        System.out.printf(
                "removed=%s, removedAgain=%s, audit=%d, notification=%d%n",
                removed, removedAgain,
                auditCount.get(), notificationCount.get());

        // Đồng bộ, các handler không ném lỗi:
        // removed=true, removedAgain=false, audit=2, notification=2
    }
}
~~~

Thứ tự trạng thái trong ví dụ:

| Sự kiện | Subscriber đang đăng ký | Audit nhận | Notification nhận |
|---|---|---:|---:|
| `event-1` | Audit | Có | Không |
| `event-2` | Audit, Notification | Có | Có |
| `event-3` | Notification | Không | Có |

Ở ví dụ không có `Executor`, việc gửi và gọi handler là **đồng bộ**. Do đó khi `send()` trả về bình thường, các handler được dispatch trong lần gửi đã chạy xong. Không suy ra kết quả đó cho channel có executor hoặc một subscriber tự khởi động việc bất đồng bộ bên trong.

### 3.2. Đăng ký trùng không có nghĩa hai bản sao

Gọi `subscribe(audit)` lần thứ hai với **cùng handler** trả `false` và không biến một subscription đó thành hai subscription riêng. Nếu một người muốn Audit xử lý hai lần một event, cách đúng là biểu diễn **hai trách nhiệm khác nhau**, không lạm dụng subscribe trùng.

Ngược lại, đăng ký **hai object handler khác nhau** mà bên trong cùng gọi một dịch vụ có thể dẫn đến **hai side effect**. Channel không biết chúng tương đương về nghiệp vụ. Việc chống thao tác trùng ở database/email/payment cần nằm tại consumer hoặc cơ chế idempotency.

### 3.3. Đúng handler khi unsubscribe

~~~java
MessageHandler handler = message ->
        System.out.println(message.getPayload());

events.subscribe(handler);

// Hợp lệ: tham chiếu đã lưu
events.unsubscribe(handler);
~~~

Không nên viết:

~~~java
events.subscribe(message -> process(message));

// Sai về ý định: lambda mới không phải subscription đã lưu.
events.unsubscribe(message -> process(message));
~~~

Đây là anti-pattern minh họa; `process(...)` là method ứng dụng. Một lambda mới có thể tạo handler object khác, vì thế `unsubscribe(...)` có thể trả `false` và handler cũ vẫn đăng ký.

## 4. Đăng ký động hay khai báo tĩnh qua Spring?

Có **hai cách tổ chức** subscriber, tùy mức độ thay đổi mà hệ thống cần.

### 4.1. Khai báo endpoint bằng `@ServiceActivator`

Nếu một nhánh luôn tồn tại suốt vòng đời ứng dụng, ưu tiên để Spring quản lý:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Configuration
class OrderEventChannelConfiguration {
    @Bean(name = "orderEvents")
    PublishSubscribeChannel orderEvents() {
        return new PublishSubscribeChannel();
    }
}

@Component
class AuditSubscriber {
    @ServiceActivator(inputChannel = "orderEvents")
    public void onOrder(String orderId) {
        System.out.println("AUDIT: " + orderId);
    }
}

@Component
class NotificationSubscriber {
    @ServiceActivator(inputChannel = "orderEvents")
    public void onOrder(String orderId) {
        System.out.println("NOTIFY: " + orderId);
    }
}
~~~

Các `@ServiceActivator` tạo những consuming endpoints. Khi endpoint event-driven được Spring khởi động, nó subscribe vào input channel; khi endpoint được dừng, framework quản lý việc ngừng subscription tương ứng.

**Không vừa dùng `@ServiceActivator` vừa tự `events.subscribe(...)` cho cùng chức năng** nếu không chủ ý tạo nhiều consuming endpoints: có thể gây xử lý trùng và làm vòng đời khó kiểm soát.

### 4.2. Endpoint quản lý vòng đời với `EventDrivenConsumer`

Khi nhánh cần bật/tắt tại runtime, có thể dùng `EventDrivenConsumer`. Endpoint này nối một `SubscribableChannel` với một `MessageHandler` và có lifecycle `start()/stop()`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.endpoint.EventDrivenConsumer;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;

@Configuration
class OptionalAnalyticsConfiguration {

    @Bean(name = "optionalOrderEvents")
    PublishSubscribeChannel optionalOrderEvents() {
        return new PublishSubscribeChannel();
    }

    @Bean(name = "analyticsHandler")
    MessageHandler analyticsHandler() {
        return message ->
                System.out.println("ANALYTICS " + message.getPayload());
    }

    @Bean(name = "analyticsEndpoint")
    EventDrivenConsumer analyticsEndpoint(
            @Qualifier("optionalOrderEvents")
            SubscribableChannel channel,
            @Qualifier("analyticsHandler")
            MessageHandler handler) {

        EventDrivenConsumer endpoint =
                new EventDrivenConsumer(channel, handler);

        // Chỉ bật endpoint khi ứng dụng quyết định.
        endpoint.setAutoStartup(false);
        return endpoint;
    }
}
~~~

Sau khi application context đã khởi tạo xong, một thành phần quản lý có thể nhận bean `analyticsEndpoint` và gọi:

~~~java
analyticsEndpoint.start(); // kích hoạt endpoint và subscription
analyticsEndpoint.stop();  // dừng endpoint và gỡ subscription
~~~

Các lệnh này là ví dụ sử dụng bean đã được Spring khởi tạo, không phải chương trình độc lập. Cần áp dụng chính sách phân quyền/điều phối phù hợp nếu đưa việc bật/tắt endpoint ra API quản trị.

`EventDrivenConsumer` và các endpoint do framework tạo tuân theo cơ chế lifecycle của Spring. Cần để chúng quản lý subscribe/unsubscribe của **chính mình**, thay vì gỡ trực tiếp handler nội bộ khỏi channel rồi vẫn giữ endpoint ở trạng thái “running”.

### 4.3. Khi nào dùng thao tác trực tiếp?

| Trường hợp | Cách phù hợp |
|---|---|
| Audit, Notification luôn chạy khi app chạy | `@ServiceActivator` hoặc Java DSL |
| Một nhánh cần dừng/khởi động theo vận hành | `EventDrivenConsumer.start()/stop()` hoặc cơ chế lifecycle tương đương |
| Subscriber mang tính tạm thời trong một phạm vi rất nhỏ | `subscribe` và `unsubscribe` thủ công, giữ đúng handler |
| Thêm nhiều consumer xuyên nhiều process | Broker/topic/subscription bên ngoài; `PublishSubscribeChannel` không chia sẻ registry qua các process |
| Cần phát lại message đã xảy ra trước khi subscribe | Broker/event store với retention/replay, không dựa vào channel in-memory |

**Không đồng nhất** “hủy đăng ký một handler” với “hủy subscription của topic Kafka”. Đây là hai tầng vận chuyển và hai cơ chế lưu trữ khác nhau.

## 5. Thêm/hủy trong lúc producer đang gửi

Đây là phần quan trọng nhất khi ứng dụng thay đổi subscription tại runtime.

Giả sử:

1. Producer bắt đầu `send(event-10)`.
2. Channel đã quyết định phân phối `event-10` đến Notification.
3. Admin gọi `unsubscribe(notificationHandler)`.
4. Handler Notification vẫn đang chạy hoặc một task của nó đã được đưa vào executor.

**Không nên kỳ vọng `unsubscribe` hủy ngược những lời gọi hoặc task đã bắt đầu.** Nó gỡ đăng ký cho các lần phân phối về sau khi thay đổi đã có hiệu lực. Nếu subscribe/unsubscribe và `send` xảy ra đồng thời, phạm vi message ở đúng thời điểm chuyển trạng thái là vấn đề cần thiết kế và kiểm thử với topology thực tế.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as Channel
    participant X as Executor
    participant H as Handler
    P->>C: send(event-10)
    C->>X: xếp task gọi H
    Note over C: Admin unsubscribe(H)
    X->>H: thực thi event-10 đã giao
    P->>C: send(event-11)
    Note over C,H: H không còn được chọn cho lần gửi sau khi hủy có hiệu lực
~~~

Một số kết luận an toàn:

- **Hủy đăng ký không phải lệnh cancel task.** Handler đã bắt đầu có thể hoàn thành hoặc lỗi bình thường.
- **Đăng ký không kéo lại event quá khứ.** Subscriber mới chỉ nhận từ những lần phân phối khi nó có mặt.
- **Đừng đổi registry ở giữa một transaction fan-out quan trọng** rồi giả định có snapshot nghiệp vụ hoàn hảo.
- **Không dựa vào thứ tự hoàn thành giữa các subscriber khi dùng executor.**
- **Trạng thái “không còn subscription” và “không còn công việc đang chạy” là hai điều khác nhau.**

Nếu cần “đã dừng xong mọi tác vụ trước khi bảo trì”, hãy thiết kế thêm cơ chế *drain*: ngăn nhận việc mới, đếm việc đang xử lý, chờ hoàn tất với timeout, rồi mới giải phóng tài nguyên. Đây là trách nhiệm của ứng dụng và hệ thống vận hành, không phải cam kết tự động của `unsubscribe`.

### 5.1. Có cần khóa toàn bộ `send()` và `unsubscribe()` không?

Đừng tự đưa một khóa global vào mọi producer chỉ để đồng bộ việc subscribe/unsubscribe nếu chưa xác định yêu cầu. Điều đó có thể làm nghẽn throughput hoặc gây deadlock khi một handler cố điều chỉnh subscriptions trong lúc đang được gọi.

Nếu hệ thống cần mốc chuyển trạng thái **chính xác**, hãy dùng một quy trình rõ ràng:

1. Chặn nguồn tạo sự kiện mới tại ranh giới thích hợp.
2. Ghi nhận và để những lần xử lý đang chạy hoàn tất.
3. Thay đổi subscription/lifecycle.
4. Cho phép producer gửi lại.
5. Xác minh số subscriber và health trạng thái sau thay đổi.

Trong các hệ thống phân tán có nhiều producer hoặc broker, quá trình này cần cơ chế đồng bộ ở tầng điều phối, không thể chỉ dựa vào một `PublishSubscribeChannel` của một JVM.

## 6. Subscriber rỗng và kết quả `send()`

Một hiểu nhầm phổ biến là:

> Nếu `send()` trả `true`, hẳn đã có subscriber xử lý thành công.

Điều này **không đúng trong mọi cấu hình**. Từ các phiên bản Spring Integration hiện đại, `PublishSubscribeChannel` có `minSubscribers` mặc định **0**: nếu không yêu cầu subscriber tối thiểu, một message gửi vào channel trống có thể vẫn được coi là gửi thành công ở cấp channel.

### 6.1. Cấu hình mặc định

~~~java
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

PublishSubscribeChannel channel = new PublishSubscribeChannel();

boolean accepted = channel.send(
        MessageBuilder.withPayload("ORDER-1001").build());

// Với minSubscribers mặc định = 0, channel trống có thể trả true.
// Không handler nào thực sự xử lý message này.
~~~

`send()==true` không phải biên nhận nghiệp vụ, không phải một cam kết lưu message và không đồng nghĩa notification/email đã được giao.

### 6.2. Yêu cầu ít nhất một subscriber

Nếu message cần phải có consumer, có thể chọn `requireSubscribers`:

~~~java
import org.springframework.integration.MessageDispatchingException;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

// Constructor bật requireSubscribers.
PublishSubscribeChannel strictChannel =
        new PublishSubscribeChannel(true);

// Khi không có subscriber: ném MessageDispatchingException.
strictChannel.send(
        MessageBuilder.withPayload("ORDER-1001").build());
~~~

`requireSubscribers=true` giúp phát hiện trường hợp **không có subscriber**. Nó không bảo đảm mọi subscriber đang chạy, đã hoàn tất hay đã commit side effect; với executor, công việc có thể còn nằm trong queue.

### 6.3. Yêu cầu số subscriber tối thiểu

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
channel.setMinSubscribers(2);
~~~

`minSubscribers` xác định ngưỡng số subscriber được dispatch thành công để `send()` trả `true` theo hợp đồng của channel. Với executor, quyết định ở thời điểm gửi dựa trên số task/subscriber được dispatch, **không thể khẳng định các handler đã hoàn thành**.

| Cấu hình | Không có subscriber | Có 1 subscriber | Có 2 subscriber |
|---|---|---|---|
| Mặc định `minSubscribers=0` | Có thể trả `true` | Gửi tới 1 | Gửi tới 2 |
| `requireSubscribers=true` | Ném exception | Dispatch | Dispatch |
| `minSubscribers=2` | Không đạt ngưỡng | Không đạt ngưỡng | Đủ ngưỡng nếu dispatch đáp ứng điều kiện |

**Phân biệt:** `requireSubscribers` nhấn mạnh trường hợp không có người nhận; `minSubscribers` có thể dùng cho yêu cầu tối thiểu nhiều người nhận. Không dùng hai thuộc tính như một cơ chế xác nhận **đủ 2 nghiệp vụ đã commit**.

### 6.4. Khi một subscriber bị hủy

Nếu một channel có `minSubscribers=2` với Audit và Notification, sau khi `unsubscribe(notification)` thành công, channel còn một subscriber. Bước tiếp theo cần phải dự liệu rằng các lần gửi sau **không còn đạt ngưỡng 2**. Đây là lý do thay đổi subscription có thể ảnh hưởng contract của producer dù phía producer không sửa code.

Một chính sách vận hành hợp lý là kiểm tra số subscriber trước khi thay đổi, theo dõi tình trạng sau thay đổi và khôi phục subscription nếu quy trình nghiệp vụ bắt buộc hai nhánh.

## 7. Đồng bộ và bất đồng bộ khi lifecycle thay đổi

`PublishSubscribeChannel` mặc định gọi subscriber trên thread đang gửi. Nếu cung cấp `Executor`, mỗi lần dispatch có thể được thực hiện trên thread khác.

~~~mermaid
flowchart TB
    subgraph SYNC["Mặc định: đồng bộ"]
        S1["send(event)"] --> H1["Handler A"]
        H1 --> H2["Handler B"]
        H2 --> R1["send() trả về"]
    end
    subgraph ASYNC["Có Executor"]
        S2["send(event)"] --> E["Executor nhận task"]
        E --> H3["Worker A"]
        E --> H4["Worker B"]
        E --> R2["send() có thể trả về trước handlers"]
    end
~~~

### 7.1. Ví dụ cấu hình Executor

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncOrderEventConfiguration {

    @Bean
    ThreadPoolTaskExecutor orderEventExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-event-");
        return executor;
    }

    @Bean(name = "asyncOrderEvents")
    PublishSubscribeChannel asyncOrderEvents(
            ThreadPoolTaskExecutor orderEventExecutor) {
        return new PublishSubscribeChannel(orderEventExecutor);
    }
}
~~~

Đây là ví dụ về pool hữu hạn; giá trị `2/4/100` cần được điều chỉnh theo throughput, latency, memory và chính sách quá tải. Khi đã hủy subscription, những task trước đó còn nằm trong pool vẫn có thể chạy.

### 7.2. Ảnh hưởng tới lỗi

| Tình huống | Đồng bộ, không executor | Bất đồng bộ, có executor |
|---|---|---|
| Handler ném exception | Có thể lan về caller của `send()` | Xử lý qua `ErrorHandler` của task/channel |
| Message đã được dispatch | Handler được gọi trên sender thread | Task có thể mới chỉ được submit |
| `send()` trả về | Thông thường sau khi handler hoàn tất bình thường | Có thể trước khi nghiệp vụ xong |
| Thứ tự hoàn thành | Thực thi trong sender thread, nhưng không nên xây nghiệp vụ dựa trên thứ tự không được cấu hình | Không bảo đảm thứ tự hoàn thành giữa các handler |
| Khi unsubscribe | Không hủy handler đang thực thi | Không hủy task đã được submit |
| Transaction/thread-local | Cùng thread nhưng vẫn phụ thuộc cấu hình transaction | Không tự chuyển transaction/thread-local của caller sang worker |

Trong mode async, Spring Integration có thể dùng `MessagePublishingErrorHandler` để phát `ErrorMessage` tới header `errorChannel` hoặc global error channel theo cấu hình. Nếu **không có executor**, cơ chế error handler của channel không thay thế việc exception nổi lên trực tiếp trên sender thread.

### 7.3. Một handler lỗi có ảnh hưởng handler khác không?

Trong mode sync, nếu một subscriber ném exception, dispatch có thể bị gián đoạn và những subscriber tiếp theo có thể chưa chạy. Không dựa vào khả năng “mọi handler chắc chắn được gọi dù có lỗi” khi chưa cấu hình chính sách phù hợp.

`setIgnoreFailures(true)` có thể được dùng cho kiểu phát best-effort, nhưng phải hiểu nó **bỏ qua lỗi** chứ không retry tự động hay tạo xác nhận nghiệp vụ cho những nhánh thất bại. Trong mode async, lỗi xảy ra ở các task khác thread cần được quan sát bằng error flow phù hợp.

## 8. Subscription, metadata và tính bất biến

Mặc định `applySequence=false`, nên một `PublishSubscribeChannel` có thể chuyển **cùng message instance** cho nhiều handler. `MessageHeaders` không cho sửa cấu trúc map trực tiếp, nhưng payload và object nằm trong header có thể mutable.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

List<String> mutable = new ArrayList<>(List.of("new"));

Message<List<String>> message = MessageBuilder
        .withPayload(mutable)
        .build();

PublishSubscribeChannel channel = new PublishSubscribeChannel();

// Không nên: hai nhánh cùng chia sẻ List có thể sửa.
channel.subscribe(m -> {
    @SuppressWarnings("unchecked")
    List<String> items = (List<String>) m.getPayload();
    items.add("audit");
});

channel.subscribe(m -> System.out.println(m.getPayload()));
channel.send(message);
~~~

Nếu handler chạy bất đồng bộ, đây còn là race condition. Hãy dùng DTO bất biến hoặc bản sao phòng vệ:

~~~java
Message<List<String>> safe = MessageBuilder
        .withPayload(List.copyOf(mutable))
        .build();
~~~

`List.copyOf` tạo snapshot collection, nhưng không deep-copy các object mutable bên trong. Dù subscriber có được subscribe hay unsubscribe động, nguyên tắc “không mutate input chung” vẫn cần được giữ.

### 8.1. Correlation, sequence và số subscriber thay đổi

Nếu cần fan-out rồi fan-in vào `Aggregator`, `PublishSubscribeChannel` có `setApplySequence(true)` để bổ sung correlation/sequence metadata cho các message phân phối.

~~~java
PublishSubscribeChannel events = new PublishSubscribeChannel();
events.setApplySequence(true);
~~~

Với ba subscriber tại thời điểm một lần phát, `sequenceSize` có thể là 3; nếu một subscriber được hủy trước **lần phát tiếp theo**, số subscriber của lần đó có thể chỉ còn 2. Đây là một thay đổi về **hình dạng nhóm fan-in**.

| Lần gửi | Số subscriber được phân phối | Sequence size của lần fan-out | Điều cần kiểm tra |
|---|---:|---:|---|
| `event-1` | 3 | 3 | Aggregator chờ ba kết quả nếu mọi nhánh phản hồi |
| `event-2` sau khi unsubscribe C | 2 | 2 | Aggregator phải hiểu hai kết quả là nhóm đầy đủ |
| `event-3` khi thêm D | 3 | 3 | D có xử lý và trả kết quả theo hợp đồng không? |

**Lưu ý:** `applySequence` không tạo Aggregator, không đợi subscriber, không bảo đảm kết quả từ nhánh và không tự giải quyết một nhánh lỗi. Hãy định nghĩa correlation strategy, release strategy, timeout và cách xử lý nhóm thiếu phần. Thay đổi subscriber trong lúc một lượt fan-out đang diễn ra càng cần cẩn thận vì không có cam kết nghiệp vụ rằng mọi nhánh sẽ đồng thời chuyển trạng thái.

### 8.2. Message ID không phải event ID nghiệp vụ

Một handler có thể được thêm vào, hủy đi rồi subscribe lại. Khi producer replay cùng một sự kiện nghiệp vụ, nó có thể được đóng gói trong message mới với `MessageHeaders.ID` mới. Nếu subscriber cần idempotency, hãy dùng một `eventId` ổn định theo nghiệp vụ hoặc khóa idempotency do nguồn cung cấp, không chỉ dựa vào ID instance của Spring message.

## 9. Một pattern quản lý đăng ký thủ công có kiểm soát

Trong thành phần nhỏ hoặc công cụ test, có thể đóng gói subscribe/unsubscribe trong một object quản lý phạm vi. Điều này giúp không quên unsubscribe khi bỏ tính năng.

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;

public final class SubscriberRegistration implements AutoCloseable {

    private final SubscribableChannel channel;
    private final MessageHandler handler;
    private final AtomicBoolean active = new AtomicBoolean();

    public SubscriberRegistration(
            SubscribableChannel channel,
            MessageHandler handler) {
        this.channel = java.util.Objects.requireNonNull(channel);
        this.handler = java.util.Objects.requireNonNull(handler);
    }

    public void start() {
        if (!active.compareAndSet(false, true)) {
            return; // đã start trong registration này
        }

        if (!channel.subscribe(handler)) {
            active.set(false);
            throw new IllegalStateException(
                    "Handler is already subscribed elsewhere");
        }
    }

    @Override
    public void close() {
        if (active.compareAndSet(true, false)) {
            channel.unsubscribe(handler);
        }
    }
}
~~~

Cách dùng:

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
MessageHandler temporary = message ->
        System.out.println("TEMP: " + message.getPayload());

try (SubscriberRegistration registration =
             new SubscriberRegistration(channel, temporary)) {
    registration.start();
    channel.send(MessageBuilder.withPayload("event").build());
}

// Kết thúc phạm vi: tự động unsubscribe handler.
~~~

Đây là mô hình tối giản minh họa **quyền sở hữu subscription**. Nó giả định mỗi handler chỉ do **một registration** này quản lý trên channel đó, không có thành phần bên ngoài cùng đăng ký/gỡ handler trong khi scope đang chạy. Trong hệ thống concurrent có nhiều controller, cần thêm chính sách đồng bộ/lifecycle; với ứng dụng Spring đầy đủ, thường nên ưu tiên endpoint do container quản lý thay vì tự xây một registry song song.

Đặc biệt, `close()` không chờ các task async đã giao hoàn tất. Nếu cần graceful shutdown, hãy bổ sung theo dõi số task đang chạy và drain có timeout.

## 10. Kiểm thử bằng JUnit 5: thêm và hủy subscriber

Kiểm thử tại mức channel giúp xác nhận không phụ thuộc vào HTTP server hay broker. Những bài test đồng bộ dưới đây không cần khởi động toàn bộ Spring context.

### 10.1. Subscribe, duplicate và unsubscribe

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

class SubscriberRegistrationTest {

    @Test
    void registerThenUnregisterSameHandler() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel();

        AtomicInteger calls = new AtomicInteger();
        MessageHandler subscriber =
                message -> calls.incrementAndGet();

        assertTrue(channel.subscribe(subscriber));
        assertFalse(channel.subscribe(subscriber));
        assertEquals(1, channel.getSubscriberCount());

        assertTrue(channel.send(
                MessageBuilder.withPayload("event-1").build()));
        assertEquals(1, calls.get());

        assertTrue(channel.unsubscribe(subscriber));
        assertFalse(channel.unsubscribe(subscriber));
        assertEquals(0, channel.getSubscriberCount());

        // minSubscribers mặc định bằng 0:
        assertTrue(channel.send(
                MessageBuilder.withPayload("event-2").build()));
        assertEquals(1, calls.get());
    }
}
~~~

Test này nêu một điều quan trọng: **gửi vào channel trống vẫn có thể thành công ở cấp API** nhưng handler đã unsubscribe không xử lý message thứ hai.

### 10.2. Subscriber mới chỉ nhận message về sau

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

class LateSubscriberTest {

    @Test
    void newlyRegisteredSubscriberOnlyGetsLaterEvents() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel();

        AtomicInteger audit = new AtomicInteger();
        AtomicInteger notify = new AtomicInteger();

        MessageHandler auditHandler =
                message -> audit.incrementAndGet();
        MessageHandler notifyHandler =
                message -> notify.incrementAndGet();

        channel.subscribe(auditHandler);
        channel.send(MessageBuilder.withPayload("event-1").build());

        channel.subscribe(notifyHandler);
        channel.send(MessageBuilder.withPayload("event-2").build());

        channel.unsubscribe(auditHandler);
        channel.send(MessageBuilder.withPayload("event-3").build());

        assertEquals(2, audit.get());
        assertEquals(2, notify.get());
        assertEquals(1, channel.getSubscriberCount());
    }
}
~~~

Đây là kiểm thử ổn định vì subscriber mặc định chạy đồng bộ, các thao tác thêm/hủy diễn ra **giữa** những lần gửi, không tạo race không cần thiết.

### 10.3. Không có subscriber khi yêu cầu bắt buộc

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.MessageDispatchingException;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

class RequireSubscribersTest {

    @Test
    void strictChannelRejectsWhenNobodySubscribed() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel(true);

        assertThrows(MessageDispatchingException.class,
                () -> channel.send(
                        MessageBuilder.withPayload("event").build()));
    }
}
~~~

Ví dụ dùng constructor `PublishSubscribeChannel(true)` được hỗ trợ trong những bản Spring Integration hiện đại. Khi dự án dùng phiên bản cũ, cần kiểm tra API tương ứng.

## 11. Kiểm thử tác vụ đã dispatch vẫn có thể chạy sau unsubscribe

Test này không cố tạo race giữa thao tác chọn subscriber và hủy đăng ký. Thay vào đó, nó thiết lập một tình huống xác định: handler đã **bắt đầu** xử lý message trước khi `unsubscribe`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

class UnsubscribeInFlightTest {

    @Test
    void unsubscribeDoesNotCancelAnAlreadyRunningHandler()
            throws InterruptedException {

        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(1);
        AtomicInteger processed = new AtomicInteger();

        try {
            PublishSubscribeChannel channel =
                    new PublishSubscribeChannel(pool);

            MessageHandler subscriber = message -> {
                entered.countDown();
                try {
                    if (!release.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Timed out waiting for release");
                    }
                    processed.incrementAndGet();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(exception);
                } finally {
                    completed.countDown();
                }
            };

            assertTrue(channel.subscribe(subscriber));
            assertTrue(channel.send(
                    MessageBuilder.withPayload("event-1").build()));

            // Đảm bảo callback đã chạy trước khi unsubscribe.
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            assertTrue(channel.unsubscribe(subscriber));

            release.countDown();
            assertTrue(completed.await(5, TimeUnit.SECONDS));

            assertEquals(1, processed.get());
            assertEquals(0, channel.getSubscriberCount());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Test chứng minh rằng hủy subscription **không chấm dứt handler đã được gọi**. Nó không tự khẳng định một cơ chế cụ thể về các task đồng thời đang nằm trong queue của executor, vì kết quả của race ở thời điểm thay đổi registry còn phụ thuộc thứ tự thực thi. Nếu cần bảo đảm không còn task, phải có giao thức drain độc lập.

## 12. Kiểm thử endpoint do Spring quản lý

Một integration test có thể xác minh khi Spring khởi động/dừng `EventDrivenConsumer` thì subscription vào channel thay đổi tương ứng. Ví dụ dùng cấu hình tối giản:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.endpoint.EventDrivenConsumer;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = ManagedEndpointLifecycleTest.Config.class)
class ManagedEndpointLifecycleTest {

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        AtomicInteger calls() {
            return new AtomicInteger();
        }

        @Bean(name = "managedEvents")
        PublishSubscribeChannel managedEvents() {
            return new PublishSubscribeChannel();
        }

        @Bean
        MessageHandler optionalHandler(AtomicInteger calls) {
            return message -> calls.incrementAndGet();
        }

        @Bean
        EventDrivenConsumer optionalEndpoint(
                @Qualifier("managedEvents")
                PublishSubscribeChannel channel,
                MessageHandler optionalHandler) {

            EventDrivenConsumer endpoint =
                    new EventDrivenConsumer(channel, optionalHandler);
            endpoint.setAutoStartup(false);
            return endpoint;
        }
    }

    @Autowired
    PublishSubscribeChannel managedEvents;

    @Autowired
    EventDrivenConsumer optionalEndpoint;

    @Autowired
    AtomicInteger calls;

    @Test
    void startingAndStoppingEndpointChangesSubscription() {
        assertEquals(0, managedEvents.getSubscriberCount());

        try {
            optionalEndpoint.start();
            assertEquals(1, managedEvents.getSubscriberCount());

            managedEvents.send(MessageBuilder
                    .withPayload("event-1").build());
            assertEquals(1, calls.get());

            optionalEndpoint.stop();
            assertEquals(0, managedEvents.getSubscriberCount());

            managedEvents.send(MessageBuilder
                    .withPayload("event-2").build());
            assertEquals(1, calls.get());
        } finally {
            optionalEndpoint.stop();
        }
    }
}
~~~

Trong ứng dụng lớn, nhiều bean khác có thể subscribe vào cùng channel. Khi đó đừng assert `getSubscriberCount()==0` nếu test context không được cô lập. Hãy dùng cấu hình thử nghiệm riêng hoặc xác minh sự thay đổi số subscriber của endpoint được điều khiển.

Kiểm thử này tập trung vào **lifecycle**, không dùng `unsubscribe(handler)` trực tiếp để làm mất đồng bộ giữa endpoint và danh sách subscriber do nó quản lý.

## 13. Rủi ro khi quản lý subscriber theo trạng thái nghiệp vụ

### 13.1. Tắt subscriber không đồng nghĩa tạm dừng dữ liệu

Nếu Notification được unsubscribe trong 10 phút, mọi sự kiện phát qua `PublishSubscribeChannel` trong 10 phút đó **không được channel lưu lại chờ Notification**.

Nếu yêu cầu là “tạm ngừng email nhưng sau đó gửi bù”, cần queue/broker/outbox hoặc dữ liệu pending bền vững. Subscribe lại không khôi phục lịch sử.

### 13.2. Đăng ký nhiều lần qua nhiều controller

Nếu một admin API và một task scheduler cùng tạo hai `MessageHandler` khác nhau cho cùng dịch vụ Notification, có thể phát hai email. `subscribe` chỉ kiểm tra trạng thái của handler đăng ký, không hiểu quy tắc “mỗi tenant tối đa một notification service”.

Một registry ở tầng ứng dụng có thể ánh xạ `subscriberId -> handler / endpoint`, kiểm soát ownership, quyền quản trị và ghi log lifecycle. Nhưng đừng xây registry thứ hai nếu Spring-managed endpoints đã đáp ứng yêu cầu.

### 13.3. Restart ứng dụng và mất trạng thái runtime

Danh sách subscriber thủ công của một channel trong JVM không tự được phục hồi từ database hoặc broker sau restart. Những endpoint đã khai báo trong cấu hình Spring sẽ đăng ký lại theo lifecycle khi application context khởi động. Nếu có tính năng đăng ký động theo cấu hình lưu trong DB, ứng dụng cần khôi phục trạng thái này theo quy trình khởi động có kiểm soát.

### 13.4. Subscriber thay đổi trong lúc aggregator chờ kết quả

Khi dùng `applySequence=true` và downstream Aggregator, thay đổi số subscriber giữa các lần gửi có thể thay đổi sequence size. Một subscriber bị tắt **sau khi đã được tính vào lượt fan-out** vẫn có thể gây nhóm thiếu phần nếu nó không phát kết quả; phải có timeout/release strategy và chính sách xử lý partial results.

### 13.5. Retry lặp message đến nhiều subscriber

Nếu producer gửi lại cùng event vì một nhánh lỗi, các subscriber đã thành công ở lần trước có thể nhận lại event. Đặt một `eventId` ổn định, dùng idempotency cho side effect và giới hạn retry đúng nhánh. Việc hủy/đăng ký không tự giải quyết vấn đề exactly-once.

## 14. Ứng dụng cùng Router, Filter và Transformer

Subscriber có thể là một endpoint đơn giản hoặc cả một flow:

~~~mermaid
flowchart TD
    E["OrderPlaced event"] --> PUB["PublishSubscribeChannel"]
    PUB --> A["Audit handler"]
    PUB --> N["Notification flow"]
    PUB --> M["Analytics flow"]
    N --> F{"Filter: should notify?"}
    F -->|Yes| T["Transformer: email request"]
    T --> G["Gateway / email adapter"]
    F -->|No| D["Discard / monitor"]
    M --> R{"Router: segment"}
    R --> P["Premium metrics"]
    R --> B["Basic metrics"]
~~~

Điều này giúp producer không phụ thuộc các nhánh xử lý cụ thể. Khi một nhánh được bật/tắt, cần xem đó là quyết định ở **cấp subscription**, khác với **Filter** chỉ loại message có điều kiện ở một nhánh đang hoạt động.

| Nhu cầu | Mô hình gợi ý |
|---|---|
| Subscriber luôn nhận event nhưng chỉ xử lý một số loại | Filter trong nhánh đó |
| Tạm tắt hoàn toàn một nhánh, chấp nhận bỏ event khi tắt | Dừng endpoint/unsubscribe |
| Chọn một trong nhiều nhánh | Router trước channel đích |
| Phát mọi event cho nhiều observer | Publish–Subscribe |
| Bật/tắt nhưng phải xử lý bù các event bị bỏ lỡ | Broker/outbox/queue bền vững với quản lý offset/pending |
| Gom kết quả nhiều nhánh | applySequence + Aggregator có correlation/release/timeout rõ |

Một subscriber tự trả message mới qua Transformer cần bảo toàn những headers có liên quan đến `traceId`, `correlationId`, `replyChannel` và `errorChannel` theo hợp đồng. Unsubscribe không thay đổi quy tắc header propagation của những subscriber vẫn đang chạy.

## 15. Giám sát lifecycle và số subscriber

Chỉ theo dõi `getSubscriberCount()` là chưa đủ. Nên xác định ít nhất:

| Quan sát | Câu hỏi trả lời | Lưu ý |
|---|---|---|
| Số subscriber hiện tại | Có đủ nhánh yêu cầu? | Chỉ là một snapshot |
| Sự kiện subscribe/unsubscribe | Ai bật/tắt, lúc nào, vì sao? | Audit quyền thao tác quản trị |
| Tổng message được publish | Producer phát bao nhiêu event? | Không tương đương số xử lý hoàn tất |
| Message xử lý thành công từng subscriber | Nhánh nào hoàn thành? | Cần đo tại consumer |
| Thời gian xử lý và số việc đang chạy | Có thể drain an toàn không? | Đặc biệt quan trọng với executor |
| Lỗi và retry từng nhánh | Subscriber nào cần khắc phục? | Phân biệt lỗi dữ liệu và lỗi hạ tầng |
| Correlation/event ID | Event có bị xử lý trùng không? | Tránh log secret/PII |

Đừng gắn `eventId` hay `orderId` vào label metric có cardinality lớn; hãy đặt các khóa truy vết ở log/trace theo chính sách. Nếu yêu cầu giảm tải, cần cân nhắc đóng admission ở upstream hoặc cấu hình queue/backpressure, không chỉ unsubscribe một nhánh quan trọng rồi để message biến mất.

## 16. Lỗi thường gặp và cách khắc phục

### Lỗi 1 — Hủy bằng một lambda mới

**Triệu chứng:** `unsubscribe(...)` trả `false` dù trước đó đã gọi `subscribe(...)`.

**Nguyên nhân:** handler truyền vào lần hủy không phải handler đã đăng ký.

**Khắc phục:** lưu tham chiếu `MessageHandler` hoặc quản lý qua endpoint lifecycle; kiểm tra giá trị trả về.

### Lỗi 2 — Gọi subscribe lặp vì tưởng mỗi lời gọi thêm một listener

**Triệu chứng:** `subscribe(handler)` lần hai trả `false`, hệ thống vẫn chỉ có một subscription cho handler đó.

**Khắc phục:** thiết kế rõ danh sách trách nhiệm, tách handler khi thực sự có hai chức năng khác nhau; không lạm dụng subscribe trùng.

### Lỗi 3 — Subscriber mới không nhận event quá khứ

**Triệu chứng:** bật Notification lúc 10:00 nhưng không nhận các đơn lúc 09:55.

**Nguyên nhân:** `PublishSubscribeChannel` không lưu lịch sử.

**Khắc phục:** dùng broker/outbox/event store nếu cần replay, với offset và idempotency thích hợp.

### Lỗi 4 — Stop endpoint nhưng task cũ vẫn chạy

**Triệu chứng:** sau khi stop, log của subscriber vẫn xuất hiện thêm một lúc.

**Nguyên nhân:** một lời gọi hoặc task đã được dispatch trước đó.

**Khắc phục:** phân biệt ngừng nhận việc mới với drain/hoàn tất việc đang chạy; có timeout và graceful shutdown khi cần.

### Lỗi 5 — Không có subscriber nhưng `send()==true`

**Triệu chứng:** producer báo thành công dù không có handler.

**Nguyên nhân:** `minSubscribers=0` theo cấu hình mặc định.

**Khắc phục:** dùng `requireSubscribers` hoặc `minSubscribers` theo contract, đồng thời đo kết quả nghiệp vụ riêng.

### Lỗi 6 — Một subscriber lỗi khiến message không đến các nhánh còn lại

**Triệu chứng:** khi Audit ném exception, Notification không chạy như dự kiến.

**Nguyên nhân:** mode sync và chính sách lỗi của dispatcher.

**Khắc phục:** phân loại nhánh bắt buộc/best-effort, chọn error handling và retry theo từng nhánh; kiểm thử partial failure. Không ngầm tin thứ tự gọi handler.

### Lỗi 7 — Đăng ký handler thủ công cạnh endpoint được Spring quản lý

**Triệu chứng:** consumer nhận trùng hoặc số subscriber không đúng sau restart/stop.

**Khắc phục:** chọn một cơ chế ownership, dùng lifecycle endpoint cho bean do Spring quản lý.

### Lỗi 8 — Tắt subscriber quan trọng mà không thông báo producer

**Triệu chứng:** `minSubscribers` không đạt, request–reply chờ quá hạn hoặc sự kiện bị bỏ lỡ.

**Khắc phục:** có quy trình thay đổi subscription, health checks, monitoring và chính sách bảo đảm delivery trước khi tắt.

### Lỗi 9 — Subscriber cùng sửa payload mutable

**Triệu chứng:** analytics thấy dữ liệu bị audit/notification sửa ngoài dự kiến.

**Khắc phục:** dùng immutable DTO/snapshot; một message phát cho nhiều subscriber không đồng nghĩa payload được clone sâu.

### Lỗi 10 — Mong applySequence tự bảo đảm đủ nhánh

**Triệu chứng:** Aggregator treo khi một subscriber bị unsubscribe hoặc thất bại.

**Khắc phục:** định nghĩa correlation/release/timeout; kiểm soát biến động subscription tại điểm fan-out cần đồng nhất.

## 17. Bài thực hành

**Bối cảnh:** một application tạo sự kiện `OrderPlaced` gồm `eventId`, `orderId` và `occurredAt`. Hệ thống có Audit luôn bật, Notification bật/tắt theo quản trị và Analytics chỉ bật trong một số môi trường.

### Bài 1 — Đăng ký và hủy cơ bản

Tạo `PublishSubscribeChannel` và ba handler có counter. Gửi `event-1` khi chỉ Audit đã subscribe, gửi `event-2` sau khi thêm Notification, gửi `event-3` sau khi hủy Audit. Kiểm thử số lần gọi và `getSubscriberCount()` sau mỗi bước.

### Bài 2 — Hành vi lặp

Đăng ký cùng một `MessageHandler` hai lần. Assert lần đầu `true`, lần thứ hai `false`; hủy lần đầu `true`, lần thứ hai `false`. Thử hủy bằng lambda mới và giải thích vì sao không đảm bảo chọn đúng handler.

### Bài 3 — Không có subscriber

Thử ba channel: cấu hình mặc định, `requireSubscribers=true` và `minSubscribers=2`. Kiểm chứng kết quả `send()` khi có 0, 1 và 2 subscriber; giải thích sự khác biệt giữa **dispatch thành công** và **nghiệp vụ hoàn tất**.

### Bài 4 — Chuyển sang Executor

Dùng `ExecutorService` có 2 worker và `CountDownLatch` để kiểm thử. Đưa một handler vào trạng thái đang chờ, gọi `unsubscribe(handler)` và cho phép handler hoàn tất. Assert callback đã chạy không bị hủy bởi unsubscribe. Dọn executor bằng `shutdownNow()` trong `finally`.

### Bài 5 — Managed endpoint lifecycle

Khai báo một `EventDrivenConsumer` với `autoStartup=false`. Sau khi Spring context sẵn sàng, gọi `start()`, gửi event, kiểm tra handler nhận; gọi `stop()`, gửi event tiếp và xác nhận subscriber đó không nhận thêm. So sánh với cấu hình `@ServiceActivator` chạy suốt vòng đời ứng dụng.

### Bài 6 — Fan-out và Aggregator

Bật `applySequence=true`, thiết kế hai nhánh trả kết quả về Aggregator. Thay đổi một subscription **giữa** hai sự kiện; kiểm tra sequence size từng sự kiện, correlation và release strategy. Tạo tình huống một nhánh không trả output và đưa ra timeout phù hợp.

### Bài 7 — Bảo đảm dữ liệu

Giả sử Notification bị tắt 10 phút nhưng vẫn phải gửi bù email sau khi bật lại. Giải thích vì sao channel in-memory không đủ; thiết kế outbox/broker/subscriber với event ID ổn định và idempotency.

### Câu hỏi tự kiểm tra

1. `subscribe(handler)` trả `false` trong tình huống nào?
2. Vì sao hủy một lambda mới có thể không tác động tới subscription cũ?
3. Khi nào nên dùng `@ServiceActivator`, khi nào nên dùng `EventDrivenConsumer` có thể start/stop?
4. `getSubscriberCount()` có nói được đã gửi thành công bao nhiêu email không?
5. Tại sao subscriber thêm sau không tự nhận event trước thời điểm thêm?
6. `unsubscribe` có bảo đảm hủy task đã đưa vào executor không?
7. Điều gì xảy ra khi `minSubscribers=2` nhưng một trong hai subscriber bị hủy?
8. `requireSubscribers` giúp phát hiện điều gì và không bảo đảm điều gì?
9. Vì sao cần idempotency ngay cả khi đã quản lý subscriptions cẩn thận?
10. Nếu dùng Aggregator, thay đổi số subscriber ảnh hưởng `sequenceSize` và timeout như thế nào?
11. Tại sao không nên xem `MessageHeaders.ID` là event ID nghiệp vụ?
12. Cần đo những thông tin nào để bảo đảm tắt subscriber không làm mất dữ liệu bắt buộc?

## 18. Checklist trước khi triển khai

- [ ] Xác định subscriber nào bắt buộc, tùy chọn và có thể tắt.
- [ ] Có cơ chế ownership rõ cho mỗi subscription; không đăng ký trùng ngoài ý muốn.
- [ ] Khi subscribe/unsubscribe thủ công, giữ đúng reference của handler và kiểm tra `boolean` trả về.
- [ ] Với endpoint do Spring quản lý, dùng lifecycle thay vì gỡ trực tiếp handler nội bộ.
- [ ] Quy định message phát trong thời gian không có subscriber được bỏ, báo lỗi hay lưu bền vững.
- [ ] Cấu hình `requireSubscribers` / `minSubscribers` theo yêu cầu dispatch.
- [ ] Phân biệt ngừng nhận message mới với hoàn tất các tác vụ đang chạy.
- [ ] Có chính sách lỗi riêng cho sync và async, kèm retry/idempotency.
- [ ] Payload/header value chia sẻ giữa các subscriber là bất biến hoặc được sao chép phòng vệ.
- [ ] Có `eventId` ổn định và trace/correlation để chẩn đoán.
- [ ] Nếu dùng Aggregator, có sequence/correlation, timeout và release strategy rõ.
- [ ] Kiểm thử thêm, hủy, đăng ký trùng, hủy lặp, no-subscriber và in-flight.
- [ ] Bật monitoring cho số subscriber, lỗi, backlog và số task đang chạy.
- [ ] Với dữ liệu quan trọng, đã thiết kế replay/durability ở broker/outbox thay vì phụ thuộc channel in-memory.

## 19. Tổng kết

Trong Spring Integration, **đăng ký và hủy subscriber** là hai thao tác quản lý registry của `SubscribableChannel`. `subscribe(handler)` đăng ký một handler; `unsubscribe(handler)` gỡ đúng handler đó; giá trị `boolean` cho biết thao tác có làm thay đổi danh sách hay không. `PublishSubscribeChannel` phát những message mới tới các subscriber đang được channel nhận diện khi dispatch, và không tự lưu sự kiện để phát bù sau khi subscriber quay lại.

Đối với ứng dụng đơn giản, có thể đăng ký thủ công. Với ứng dụng Spring thực tế, **endpoint do Spring quản lý** và vòng đời `start()/stop()` thường giúp tránh trùng đăng ký, thất lạc quyền sở hữu và lệch trạng thái. Khi dùng executor, hủy subscription **không** có nghĩa các tác vụ đã dispatch bị cancel. Cần chọn chính sách khi subscriber rỗng, xử lý lỗi từng nhánh, giữ dữ liệu bất biến, theo dõi correlation và xây dựng cơ chế replay/idempotency nếu nghiệp vụ yêu cầu.

Nắm được vòng đời này giúp kết hợp Publish–Subscribe với Router, Filter, Transformer, Gateway, Splitter/Aggregator, retry và error channel trong module **SPRING_INTEGRATION_PATTERN** một cách chủ động, kiểm thử được và dễ vận hành.

### Tài liệu tham khảo

- Spring Framework API — `SubscribableChannel` (`subscribe`, `unsubscribe`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html
- Spring Integration Reference — Message Channel Implementations: https://docs.spring.io/spring-integration/reference/channel/implementations.html
- Spring Integration Reference — Configuring Message Channels: https://docs.spring.io/spring-integration/reference/channel/configuration.html
- Spring Integration Reference — Message Endpoints / Event-driven Consumer: https://docs.spring.io/spring-integration/reference/endpoint.html
- Spring Integration Reference — Service Activator: https://docs.spring.io/spring-integration/reference/service-activator.html
- Spring Integration API — `PublishSubscribeChannel`: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html
- Spring Integration API — `AbstractSubscribableChannel`: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/AbstractSubscribableChannel.html
- Spring Integration API — `EventDrivenConsumer`: https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/EventDrivenConsumer.html

