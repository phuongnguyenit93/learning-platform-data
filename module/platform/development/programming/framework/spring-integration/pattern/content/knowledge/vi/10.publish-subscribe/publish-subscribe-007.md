# Một subscriber chậm ảnh hưởng publisher thế nào?

## 1. Bài toán: một sự kiện được nhiều bên quan tâm

Một ứng dụng thương mại điện tử phát sự kiện `OrderPlaced`. Ba thành phần độc lập đều muốn nhận:

- **Audit**: lưu dấu vết đơn hàng, thường xử lý nhanh.
- **Analytics**: tính toán số liệu và gọi một dịch vụ ngoài, đôi khi mất vài trăm mili-giây.
- **Notification**: gửi thông báo cho khách hàng, có thể gặp lỗi mạng.

Nếu publisher chỉ gửi **một** message vào một **Publish-Subscribe Channel**, framework sẽ phân phối nó cho các subscriber đã đăng ký. Vấn đề nảy sinh khi Analytics chậm: publisher có phải chờ không, Audit có bị ảnh hưởng không, và liệu việc đổi sang bất đồng bộ có làm vấn đề biến mất?

**Câu trả lời ngắn:** với `PublishSubscribeChannel` mặc định **không cấu hình Executor**, việc phân phối thường diễn ra **đồng bộ trên thread gửi**; một subscriber chậm có thể kéo dài lời gọi `send()` và trì hoãn những subscriber khác. Khi cấu hình `Executor`, publisher thường chỉ cần giao công việc vào executor, nhưng subscriber chậm vẫn có thể làm **nghẽn hàng đợi, bão hòa thread pool, gây từ chối tác vụ và tác động trở lại publisher**. Độ trễ chỉ được chuyển sang một ranh giới khác, không tự biến mất.

Trong module **SPRING_INTEGRATION_PATTERN**, vấn đề này gắn với mục tiêu học **Enterprise Integration Patterns** để xây dựng message flow ít phụ thuộc, dễ mở rộng bằng **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và quan sát từng nhánh xử lý.

Sau bài này, bạn sẽ phân tích được tác động của subscriber chậm theo cơ chế dispatch, thiết kế mức độ cách ly phù hợp và kiểm thử cả latency, lỗi, backlog, thứ tự và khả năng phục hồi.

## 2. Publish-Subscribe là fan-out, không phải tranh nhau lấy message

**Publish-Subscribe Channel** trong Spring Integration là một `SubscribableChannel`: mỗi subscriber được đăng ký có thể nhận thông điệp được phát vào channel đó theo chính sách dispatch. Đây là mô hình **fan-out** trong tiến trình ứng dụng, không phải một queue có các consumer tranh nhau lấy từng message.

~~~mermaid
flowchart LR
    P["Publisher / Gateway"] --> C["PublishSubscribeChannel"]
    C --> A["Audit subscriber"]
    C --> B["Analytics subscriber"]
    C --> N["Notification subscriber"]
~~~

So sánh để tránh nhầm:

| Thành phần | Ý nghĩa đối với một message |
|---|---|
| `PublishSubscribeChannel` | Phân phối tới các subscriber theo cơ chế broadcast của channel |
| `DirectChannel` | Chọn một handler trong các subscriber theo chiến lược dispatcher của point-to-point channel |
| `QueueChannel` | Lưu message để consumer chủ động `receive()`; thường một lần nhận lấy ra message khỏi queue |
| Broker topic / fanout exchange | Cơ chế pub/sub **bên ngoài tiến trình**, có quy tắc lưu trữ, xác nhận và consumer group riêng |

Không suy ra rằng ba subscriber tạo thành ba bản sao **bền vững** chỉ vì dùng PublishSubscribeChannel. Trong một tiến trình Java, channel này tự thân **không phải broker có replay, durable subscription hay exactly-once**.

Một cách hình dung:

~~~text
PublishSubscribeChannel:
event E1 ──┬── Audit nhận E1
           ├── Analytics nhận E1
           └── Notification nhận E1

QueueChannel với các worker cạnh tranh:
event E1 ─────────> một worker lấy E1 ra để xử lý
~~~

**Đọc kỹ yêu cầu:** “mọi subscriber đều cần E1” khác với “bất kỳ một worker nào xử lý E1 là đủ”. Hai yêu cầu dẫn đến thiết kế channel và recovery hoàn toàn khác nhau.

## 3. Chế độ mặc định: dispatch đồng bộ trên thread publisher

Khi tạo `new PublishSubscribeChannel()` **không truyền Executor**, các subscriber được gọi trong quá trình publisher gửi message. Luồng xử lý có thể hình dung như sau:

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant C as PublishSubscribeChannel
    participant A as Audit
    participant B as Analytics (chậm)
    participant N as Notification
    P->>C: send(OrderPlaced)
    C->>A: handleMessage(E1)
    A-->>C: hoàn tất nhanh
    C->>B: handleMessage(E1)
    Note over B,C: Analytics gọi API chậm
    B-->>C: hoàn tất
    C->>N: handleMessage(E1)
    N-->>C: hoàn tất
    C-->>P: send() kết thúc
~~~

**Trong đường dispatch đồng bộ:**

1. Publisher gọi `send()`, channel bắt đầu chuyển message đến các subscriber.
2. Một subscriber chiếm thread lâu sẽ làm lời gọi gửi còn đang thực thi.
3. Subscriber chưa được dispatch trong lượt đó có thể phải chờ subscriber chậm hoàn tất.
4. Sau khi channel kết thúc dispatch, publisher mới tiếp tục phần công việc tiếp theo.

Thứ tự subscriber thực tế phụ thuộc đăng ký và chính sách sắp xếp/ưu tiên của dispatcher; **không thiết kế nghiệp vụ phụ thuộc vào một thứ tự ngầm định**. Nếu có quy tắc “phải audit trước khi gửi thông báo”, cần biểu diễn quan hệ nhân quả bằng các endpoint nối tiếp hoặc cơ chế phối hợp rõ ràng, thay vì trông chờ fan-out.

**Event-driven không đồng nghĩa asynchronous.** PublishSubscribeChannel mặc định nhận sự kiện theo kiểu subscribe, nhưng việc xử lý thường diễn ra trên thread của bên gửi, tương tự nhiều pipeline sử dụng `DirectChannel`.

## 4. Tính độ trễ khi một subscriber chậm

Giả sử cùng một publisher phát message lần lượt, các subscriber đồng bộ có thời gian xử lý:

| Subscriber | Thời gian xử lý trung bình giả định |
|---|---:|
| Audit | 5 ms |
| Analytics | 400 ms |
| Notification | 5 ms |

Nếu không có đoạn xử lý khác hoặc overhead đáng kể, thời gian của một lượt dispatch xấp xỉ:

\[
T_{\text{send}} \approx T_{\text{audit}} + T_{\text{analytics}} + T_{\text{notification}} = 410\text{ ms}
\]

Thông lượng tối đa **xấp xỉ** của **một publisher tuần tự** khi mọi lần gửi có chi phí như vậy:

\[
\frac{1000}{410} \approx 2.44\text{ message/giây}
\]

Đây chỉ là mô hình minh họa, **không phải benchmark Spring Integration**: thực tế còn phụ thuộc I/O, thread scheduling, contention, exception và nhiều producer đồng thời. Với một subscriber bị kẹt 10 giây, một lần `send()` đồng bộ cũng có thể bị kéo dài tương ứng.

Ảnh hưởng lan truyền:

~~~mermaid
flowchart TD
    S["Analytics xử lý chậm"] --> H["Dispatch thread bị giữ lâu"]
    H --> P["Publisher.send() tăng latency"]
    P --> G["Gateway / HTTP request chờ"]
    P --> T["Thread pool upstream bị chiếm"]
    T --> Q["Tăng timeout và backlog đầu vào"]
    Q --> R["Nguy cơ retry hoặc quá tải dây chuyền"]
~~~

Nếu publisher là một HTTP endpoint đang trả kết quả đồng bộ, người gọi có thể timeout dù một số subscriber đã làm xong. Nếu publisher là listener từ broker, việc xử lý kéo dài có thể ảnh hưởng thời điểm ack, sức chứa consumer và chính sách redelivery. **Timeout ở caller không chứng minh rằng tất cả subscriber đều chưa thực hiện side effect.**

## 5. Ví dụ Java: fan-out đồng bộ có ba subscriber

Định nghĩa payload không phụ thuộc transport:

~~~java
public record OrderPlaced(
    String eventId,
    String orderId,
    long totalAmount
) {}
~~~

Tạo một PublishSubscribeChannel mặc định:

~~~java
@Configuration
@EnableIntegration
class FanoutChannels {

    @Bean(name = "orders.events")
    PublishSubscribeChannel orderEventsChannel() {
        return new PublishSubscribeChannel();
    }
}
~~~

Mỗi method sau được đăng ký như một subscriber của cùng channel. Các import được lược bỏ; đây là ví dụ Java/Spring Integration dùng để hiểu dispatch, không bao gồm cấu hình database hoặc HTTP thật.

~~~java
interface AnalyticsService {
    void record(OrderPlaced event);
}

interface NotificationService {
    void notifyOrder(OrderPlaced event);
}

@Component
class OrderEventSubscribers {

    private final AnalyticsService analyticsService;
    private final NotificationService notificationService;

    OrderEventSubscribers(AnalyticsService analyticsService,
                          NotificationService notificationService) {
        this.analyticsService = analyticsService;
        this.notificationService = notificationService;
    }

    @ServiceActivator(inputChannel = "orders.events")
    public void audit(OrderPlaced event) {
        System.out.println("AUDIT: " + event.eventId());
    }

    @ServiceActivator(inputChannel = "orders.events")
    public void analytics(OrderPlaced event) {
        // Tượng trưng cho một thao tác I/O có thể chậm:
        analyticsService.record(event);
    }

    @ServiceActivator(inputChannel = "orders.events")
    public void notification(OrderPlaced event) {
        notificationService.notifyOrder(event);
    }
}
~~~

Đoạn mã trên giả định có các bean triển khai hai interface `AnalyticsService` và `NotificationService` để Spring inject vào component; cần bổ sung chúng khi triển khai ứng dụng thực. Để gọi channel:

~~~java
MessageChannel events = context.getBean(
    "orders.events", MessageChannel.class);

Message<OrderPlaced> message = MessageBuilder
    .withPayload(new OrderPlaced("EV-101", "ORD-101", 120_000))
    .setHeader("traceId", "trace-101")
    .build();

long started = System.nanoTime();
boolean accepted = events.send(message);
long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
    System.nanoTime() - started);
~~~

Ở chế độ đồng bộ không có lỗi, `elapsedMs` phản ánh thời gian dispatch/handler của lượt gửi. Khi subscriber thực sự gọi API ngoài, **hết thời gian chờ** hoặc bị treo sẽ kéo dài thời gian publisher cần để hoàn tất lời gọi.

**Giới hạn diễn giải:** `accepted == true` không phải chứng chỉ end-to-end exactly-once, không phải xác nhận commit đồng thời ở ba hệ thống và không chứng minh một bước downstream bất đồng bộ về sau đã xong.

## 6. Chậm khác với lỗi: subscriber ném exception thì sao?

Một subscriber có thể vừa chậm vừa lỗi. Ở đường dispatch đồng bộ, ngoại lệ từ handler có thể truyền ngược qua channel tới publisher. Theo cấu hình mặc định thường gặp, một exception có thể **làm dừng lượt dispatch hiện tại**; một số subscriber đã nhận E1 còn subscriber khác chưa nhận. Không có transaction phân tán tự động gộp ba kết quả thành một thao tác nguyên tử.

~~~text
E1 → Audit: ĐÃ GHI
   → Analytics: NÉM EXCEPTION
   → Notification: CÓ THỂ CHƯA ĐƯỢC GỌI
Publisher: thấy lỗi
~~~

Nếu publisher retry toàn bộ `send(E1)`, Audit có thể nhận lại E1, dù lần trước đã ghi thành công. Đây là lý do **idempotency theo từng subscriber** quan trọng: mỗi handler phải nhận biết sự kiện đã xử lý, ví dụ theo `eventId` cộng với định danh subscriber hoặc loại side effect.

Một số cấu hình cho phép bỏ qua lỗi subscriber để cố tiếp tục fan-out. **Bỏ qua exception không phải bảo đảm delivery**; nó có thể làm publisher không biết một nhánh thất bại. Khi yêu cầu “mọi subscriber phải thành công”, cần thiết kế theo dõi trạng thái và cơ chế retry riêng cho mỗi nhánh.

Phân loại lỗi:

| Sự cố | Ảnh hưởng trong fan-out đồng bộ | Cách xử lý |
|---|---|---|
| Một handler xử lý lâu | Publisher và subscriber phía sau có thể phải chờ | Đặt timeout tại I/O; cân nhắc tách thực thi |
| Một handler ném lỗi | Có thể truyền ngược, các nhánh không nguyên tử | Chọn error policy; idempotency khi retry |
| Một handler bị block vô hạn | Thread gửi có thể mắc kẹt | Timeout, cancellation phù hợp, bulkhead |
| Không có subscriber | Phụ thuộc yêu cầu và cấu hình channel | Giám sát subscriber count và test lúc startup |
| Publisher gửi lại cùng event | Các subscriber có thể thấy lại | Dedupe theo event ID và side effect |

## 7. Đổi sang asynchronous PublishSubscribeChannel

Spring Integration cho phép cung cấp một `Executor` cho `PublishSubscribeChannel`. Thay vì chạy trực tiếp tất cả subscriber trên thread publisher, channel có thể giao các tác vụ xử lý tới executor.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant C as PublishSubscribeChannel
    participant X as Executor / work queue
    participant A as Audit
    participant B as Analytics
    participant N as Notification
    P->>C: send(E1)
    C->>X: submit Audit(E1)
    C->>X: submit Analytics(E1)
    C->>X: submit Notification(E1)
    C-->>P: Hoàn tất bước dispatch/submission
    par Các task được lên lịch
      X->>A: xử lý E1
      X->>B: xử lý E1 (có thể chậm)
      X->>N: xử lý E1
    end
~~~

Cấu hình minh họa, **thay thế** bean `orders.events` ở mục 5 chứ không đăng ký cùng lúc:

~~~java
@Configuration
@EnableIntegration
class AsyncFanoutChannels {

    @Bean
    ThreadPoolTaskExecutor fanoutExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("fanout-");
        return executor;
    }

    @Bean(name = "orders.events")
    PublishSubscribeChannel orderEventsChannel(
            ThreadPoolTaskExecutor fanoutExecutor) {
        return new PublishSubscribeChannel(fanoutExecutor);
    }
}
~~~

Với Spring-managed `ThreadPoolTaskExecutor`, bean được quản lý lifecycle; ứng dụng thực cần xác định rõ thời gian shutdown/graceful drain, rejection policy và các cơ chế theo dõi. Các subscriber `@ServiceActivator` có thể giữ nguyên.

**Điều thay đổi:** publisher không còn nhất thiết chờ handler hoàn tất để `send()` trả về; ba handler có cơ hội chạy đồng thời. **Điều không thay đổi:** công việc thật vẫn phải chạy ở nơi nào đó, vẫn tốn thread/CPU/I/O, vẫn có thể lỗi và vẫn cần chính sách để biết subscriber nào hoàn tất.

Trong trường hợp executor đang quá tải, việc submit task có thể chặn, chạy ngay trên thread gọi hoặc bị từ chối **tùy loại executor và rejection policy**. Vì vậy không được khẳng định `send()` luôn nhanh hoặc luôn thành công chỉ vì đã cấu hình Executor.

## 8. Subscriber chậm trong executor: hết chặn trực tiếp, nhưng vẫn gây nghẽn gián tiếp

Executor không tạo thêm năng lực vô hạn. Giả sử publisher phát **100 sự kiện/giây**, mỗi sự kiện có ba subscriber:

- Audit mất khoảng 5 ms/sự kiện.
- Analytics mất khoảng 400 ms/sự kiện.
- Notification mất khoảng 5 ms/sự kiện.

Với ba tác vụ trên mỗi sự kiện, executor có thể phải nhận **300 task/giây**. Riêng Analytics đã cần khoảng **40 giây-thread xử lý cho mỗi giây thực** nếu muốn theo kịp 100 sự kiện/giây; Audit và Notification cũng tiêu tốn tài nguyên. Một pool tối đa 8 thread rõ ràng khó theo kịp tải giả định nếu các con số này giữ nguyên.

Khi backlog tăng:

~~~mermaid
flowchart TD
    IN["Publisher gửi nhanh"] --> POOL["Executor nhận task"]
    POOL --> W["Worker threads"]
    W --> S["Subscriber chậm giữ thread"]
    S --> Q["Task chờ trong queue tăng"]
    Q --> FULL{"Queue đầy?"}
    FULL -->|"Chưa"| Q
    FULL -->|"Rồi"| REJ["Rejection / CallerRuns / chặn theo policy"]
    REJ --> IMPACT["Publisher tăng latency hoặc gặp lỗi submit"]
~~~

Hậu quả thực tế có thể gồm:

1. **Queue latency:** event đến Analytics muộn dù publisher đã trả về từ lâu.
2. **Thread starvation:** subscriber nhanh phải đợi vì tất cả thread đang bị tác vụ chậm chiếm.
3. **Rejection:** executor hết capacity không nhận thêm task; publisher có thể nhìn thấy lỗi.
4. **Caller-runs:** nếu cấu hình policy kiểu `CallerRunsPolicy`, tác vụ có thể được chạy trên thread gửi, tái tạo backpressure và làm `send()` chậm.
5. **Không còn thứ tự hoàn tất:** Analytics của E1 có thể xong sau Audit của E2; subscriber cũng có thể xử lý nhiều event đồng thời.

**Đổi sang asynchronous giải phóng thread publisher khi còn capacity, không giải quyết tận gốc bottleneck.** Hãy đo được tốc độ vào, tốc độ hoàn tất, kích thước queue, tuổi task chờ và số task bị reject.

## 9. Shared executor hay executor riêng cho từng subscriber?

Nếu mọi subscriber dùng **cùng một executor**, một subscriber thường xuyên chờ mạng có thể dùng nhiều thread và chỗ trong queue, khiến subscriber khác cũng bị trì hoãn. Mô hình này tiện nhưng ít cách ly.

| Thiết kế | Lợi ích | Rủi ro |
|---|---|---|
| Fan-out đồng bộ | Đơn giản, lỗi có thể truyền ngược ngay | Subscriber chậm giữ thread publisher |
| Fan-out với một executor chung | Publisher thường không chờ handler; có concurrency | Một nhánh chiếm thread/queue của nhánh khác |
| Mỗi nhánh có executor/queue riêng | Cách ly capacity và chính sách retry tốt hơn | Nhiều cấu hình, cần giới hạn queue và shutdown |
| Broker/queue bền vững cho từng nhánh | Tách vòng đời, hỗ trợ recovery sau restart theo cấu hình | Phức tạp vận hành, phải xử lý ack/redelivery/DLQ |

Muốn cách ly sâu, có thể để Publish-Subscribe fan-out **chuyển sang các channel đệm tách biệt**, mỗi channel có consumer/poller hoặc worker riêng:

~~~mermaid
flowchart LR
    P["Order publisher"] --> B["PublishSubscribeChannel"]
    B --> AIN["audit.queue (bounded)"]
    B --> XIN["analytics.queue (bounded)"]
    B --> NIN["notification.queue (bounded)"]
    AIN --> AW["Audit worker"]
    XIN --> XW["Analytics worker"]
    NIN --> NW["Notification worker"]
~~~

Ở đây **mỗi queue phải có owner và chính sách capacity/error/retry**. Ví dụ:

~~~java
@Bean(name = "analytics.queue")
PollableChannel analyticsQueue() {
    return new QueueChannel(500);
}

@Bean
IntegrationFlow publishToAnalyticsQueue() {
    return IntegrationFlow.from("orders.events")
        .channel("analytics.queue")
        .get();
}

@Bean
IntegrationFlow analyticsWorker(AnalyticsService service) {
    return IntegrationFlow.from("analytics.queue")
        .handle(OrderPlaced.class,
            (event, headers) -> {
                service.record(event);
                return null;
            },
            endpoint -> endpoint.poller(
                Pollers.fixedDelay(Duration.ofMillis(200))
                    .maxMessagesPerPoll(10)))
        .get();
}
~~~

Đây là **một nhánh minh họa**, cần tạo các nhánh audit/notification tương tự nếu thực hành sơ đồ đầy đủ. `IntegrationFlow.from("orders.events")` gắn một subscriber tới channel phát, còn `analytics.queue` được tiêu thụ bằng poller.

**Quan trọng:** bridge từ PublishSubscribeChannel sang queue có thể vẫn chạy trên thread gửi nếu channel phát đồng bộ; nếu queue đầy, thao tác gửi vào queue có thể chờ/thất bại. Thiết kế queue riêng làm rõ điểm nghẽn, nhưng không tự miễn nhiễm với backpressure và không cung cấp durability nếu chỉ dùng queue trong bộ nhớ.

## 10. Timeout, bounded queue và backpressure

Một chiến lược vận hành phải trả lời được: “Nếu subscriber B chậm hơn tốc độ event đến trong 10 phút, điều gì xảy ra?” Không thể lấy “tăng thread pool” làm câu trả lời duy nhất.

Các giới hạn nên đặt:

| Ranh giới | Cấu hình/chính sách | Ý nghĩa |
|---|---|---|
| I/O ở subscriber | Connection/read timeout, bulkhead | Không chiếm thread vô hạn |
| Executor | Core/max pool, queue capacity, rejection policy | Giới hạn số task đang chạy và chờ |
| Channel queue | Capacity và send timeout | Xác định điều gì xảy ra khi backlog đầy |
| Retry | Số lần, backoff, loại lỗi được retry | Tránh bão retry và xử lý lặp |
| Broker | Ack/nack, retention, DLQ, max in-flight | Xử lý redelivery và phục hồi sau restart |
| Upstream | Rate limiting / admission control | Không cho tốc độ vào vượt năng lực bền vững |

**Backpressure** không phải là lỗi thiết kế tự thân: việc làm producer chậm hoặc từ chối bớt tải có kiểm soát có thể an toàn hơn so với việc hàng đợi tăng vô hạn rồi hết bộ nhớ. Hãy quyết định rõ chính sách:

- **Block/chờ có timeout:** phù hợp khi caller chịu được độ trễ và không muốn bỏ message.
- **Reject/fail fast:** phù hợp khi caller có thể retry về sau bằng key ổn định.
- **Buffer bền vững:** phù hợp khi không được mất sự kiện và cần xử lý sau restart.
- **Drop có chủ đích:** chỉ chấp nhận cho dữ liệu không quan trọng, ví dụ một số loại telemetry; phải đo số lượng bị bỏ.

Không dùng một queue vô hạn làm giải pháp che giấu subscriber chậm; nó chỉ dời thời điểm thất bại tới lúc bộ nhớ hoặc tài nguyên khác cạn.

## 11. Error channel và retry trong chế độ bất đồng bộ

Khi không còn cùng call stack, publisher không thể dựa vào `try/catch` quanh `send()` để bắt mọi exception của subscriber chạy sau đó.

Trong Spring Integration, xử lý lỗi của các task bất đồng bộ có thể sử dụng **error handler/error channel** phù hợp với endpoint/channel và cấu hình thực tế. Các thành phần như `MessagePublishingErrorHandler` có thể phát `ErrorMessage` tới một channel xử lý lỗi. Cần xác minh ranh giới lỗi theo phiên bản và cấu hình, không coi mọi exception đều mặc định gửi tới cùng một channel.

~~~mermaid
flowchart TD
    PUB["Publisher.send()"] --> EX["Fan-out executor"]
    EX --> S1["Audit: OK"]
    EX --> S2["Analytics: exception"]
    EX --> S3["Notification: OK"]
    S2 --> E["Error handler"]
    E --> C["Error channel / retry / DLQ"]
    C --> O["Metric, alert, recovery"]
~~~

Phân biệt ba loại kết quả:

1. **Dispatch accepted:** executor/channel nhận công việc tại thời điểm gọi; chưa có nghĩa handler đã xong.
2. **Subscriber succeeded:** handler đã hoàn tất nghiệp vụ của chính nó.
3. **Whole event completed:** tất cả subscriber bắt buộc đều hoàn tất theo một chính sách tổng hợp được thiết kế riêng.

Nếu cần theo dõi bước (3), thiết kế **processing status per subscriber** hoặc một cơ chế phản hồi/aggregation. Một Boolean từ `send()` không đại diện cho trạng thái của ba nhánh.

Một subscriber lỗi vĩnh viễn do schema không hợp lệ không nên retry vô hạn. Một lỗi timeout mạng có thể retry với backoff, nhưng phải xét liệu thao tác đã tạo side effect trước khi báo lỗi hay chưa. **Idempotency** theo `eventId` là bắt buộc về mặt thiết kế khi có redelivery/retry thực tế.

## 12. Thứ tự message và concurrency

Ở chế độ đồng bộ với **một publisher gửi tuần tự**, mỗi `send()` thông thường hoàn tất dispatch trước khi publisher phát message tiếp theo. Tuy nhiên, nhiều publisher thread có thể cùng gửi nên không được suy ra thứ tự toàn cục.

Trong chế độ executor, các task có thể chạy song song:

~~~text
Publisher:     E1 ------ E2 ------ E3
Audit:         E1 -> E2 -> E3
Analytics:     E1 ------------------ E2 --------- E3
Notification:  E2 -> E1 -> E3     (một khả năng khi song song)
~~~

Ngay cả trong cùng một subscriber, khi có nhiều task thực thi đồng thời, **thứ tự bắt đầu hoặc hoàn tất** không phải bảo đảm mặc định. Nếu nghiệp vụ yêu cầu “Update của cùng order phải áp dụng theo thứ tự”, hãy dùng partition theo key, một worker tuần tự theo key, hoặc lưu version/checkpoint và từ chối cập nhật cũ.

Đừng giải bài toán thứ tự bằng cách tăng concurrency rồi hy vọng queue tự giữ đúng trình tự end-to-end. Cần kiểm thử với nhiều event cho cùng entity và nhiều producer cùng gửi.

## 13. Correlation, applySequence và Aggregator

Một tình huống khác: một publisher gửi sự kiện tới ba nhánh, rồi cần biết khi nào **cả ba** đã hoàn tất. Khi đó, flow giống bài toán **Scatter-Gather**: fan-out công việc, nhận kết quả và Aggregator chờ đủ kết quả liên quan.

~~~mermaid
flowchart LR
    E["Event E1"] --> P["Publish-Subscribe: 3 nhánh"]
    P --> A["Audit → AuditResult"]
    P --> B["Analytics → AnalyticsResult"]
    P --> N["Notification → NotifyResult"]
    A --> AG["Aggregator theo correlation"]
    B --> AG
    N --> AG
    AG --> DONE["EventProcessingSummary"]
~~~

Một `PublishSubscribeChannel` có thể được cấu hình **applySequence** để bổ sung metadata sequence/correlation cho các bản tin được broadcast. Đây là công cụ hữu ích khi thực sự có bước gom kết quả, nhưng phải xem:

- Mỗi nhánh có phát một result message hay không? Nếu một nhánh chỉ gọi side effect rồi kết thúc, Aggregator không tự biết nhánh đó thành công.
- `correlationId`, `sequenceNumber` và `sequenceSize` có được giữ khi qua Transformer/Router/broker adapter hay không?
- Số subscriber có ổn định ở thời điểm phát, hay thay đổi động?
- Nhánh lỗi hoặc bị drop sẽ tạo failure result hay làm nhóm phải timeout?
- Duplicate result sẽ được xử lý ra sao?

**Không tự coi `applySequence=true` là lời giải hoàn chỉnh cho “mọi subscriber thành công”.** Cần release strategy, group timeout, error path, xử lý thiếu phần, message store phù hợp và chính sách chống trùng.

Nếu không cần gom kết quả, giữ thiết kế pub/sub đơn giản hơn và dùng metric/status riêng để kiểm soát. Correlation và ID vẫn nên được truyền theo hợp đồng để truy vết event qua các nhánh.

## 14. Không có durability tự động: phân biệt in-memory fan-out với broker

Một PublishSubscribeChannel tạo fan-out trong **cùng JVM**. Nếu ứng dụng tắt đột ngột sau khi publisher gửi nhưng trước khi worker bất đồng bộ hoàn tất, các tác vụ còn nằm trong bộ nhớ có thể mất. Đây không phải một cơ chế durable subscription.

Khi yêu cầu business “Audit và Billing bắt buộc được xử lý kể cả sau restart”, cân nhắc một hệ thống lưu trữ/message broker phù hợp:

| Yêu cầu | In-memory PublishSubscribeChannel | Phương án cần xem xét |
|---|---|---|
| Fan-out nhanh trong một JVM | Phù hợp | Không nhất thiết cần broker |
| Subscriber có thể chậm vài giây | Có thể dùng executor/queue có giới hạn | Thiết kế backpressure và giám sát |
| Mỗi subscriber phải nhận sau restart | Không tự bảo đảm | Durable broker routing/subscription, persistent store |
| Có thể replay event cũ | Không có replay tự thân | Broker/log lưu giữ event hoặc event store |
| Mỗi bên cần tốc độ xử lý độc lập | Executor riêng hoặc queue riêng có giới hạn | Topic/group/queue riêng theo semantics broker |
| Xử lý exactly-once nghiệp vụ | Không tự bảo đảm | Idempotency/transaction/outbox theo use case |

Với Kafka, nhiều consumer group có thể đọc cùng topic độc lập theo vị trí của mỗi group; với RabbitMQ, một fanout exchange có thể phân phối tới nhiều queue được bind theo topology tương ứng. **Đây là các mô hình broker riêng**, không suy trực tiếp từ hành vi đồng bộ của `PublishSubscribeChannel` và không đồng nghĩa mọi bước side effect đều exactly-once.

## 15. Kiểm thử tác động của subscriber chậm

Không nên dùng riêng `Thread.sleep(1000)` rồi suy ra publisher luôn chậm 1 giây. Một test tốt cần **đồng bộ bằng latch** để khẳng định subscriber đã bắt đầu và publisher còn/chưa hoàn tất.

Ví dụ Java/JUnit minh họa một PublishSubscribeChannel **đồng bộ**:

~~~java
@Test
void slowSubscriberKeepsSynchronousSendInProgress()
        throws Exception {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    CountDownLatch entered = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    ExecutorService sender = Executors.newSingleThreadExecutor();

    channel.subscribe(message -> {
        entered.countDown();
        try {
            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out in test subscriber");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    });

    try {
        Future<Boolean> sent = sender.submit(
            () -> channel.send(new GenericMessage<>("E1")));

        assertTrue(entered.await(2, TimeUnit.SECONDS));
        assertFalse(sent.isDone());

        release.countDown();
        assertTrue(sent.get(2, TimeUnit.SECONDS));
    } finally {
        release.countDown();
        sender.shutdownNow();
    }
}
~~~

Đây là **test hành vi** của channel trong JVM, không cần HTTP server hay broker. Nó chứng minh một subscriber đang chờ giữ cho lời gửi đồng bộ **chưa kết thúc**. Các giá trị timeout chỉ để test có điểm dừng; nếu máy CI quá tải, cần điều chỉnh có kiểm soát thay vì bỏ timeout.

Đối với **async fan-out**, thực hiện test tương tự với executor có giới hạn, nhưng xác minh rằng:

1. Publisher có thể hoàn tất bước gửi trong khi subscriber vẫn chưa được release, **khi executor còn capacity**.
2. Bằng cách cố tình làm đầy queue/executor, chính sách rejection/caller-runs thực sự xảy ra và được quan sát.
3. Một subscriber chậm không làm lẫn kết quả xử lý của subscriber khác, trừ khi chúng phải chia sẻ tài nguyên theo thiết kế.
4. Nếu một handler ném exception, lỗi có đường xử lý và không bị hiểu nhầm là dispatch thành công end-to-end.
5. Việc shutdown khi đang có backlog tuân theo chính sách đã công bố; không ngầm tuyên bố mọi tác vụ sẽ được phát lại.

### Ma trận kiểm thử tối thiểu

| Tình huống | Điều quan sát |
|---|---|
| Ba subscriber nhanh, dispatch đồng bộ | `send()` hoàn tất sau các handler |
| Một subscriber chậm đồng bộ | Lời gửi chưa kết thúc trong lúc subscriber đang chờ |
| Một subscriber ném lỗi đồng bộ | Lỗi được quan sát; xác định nhánh nào đã/chưa chạy |
| Executor còn capacity | Publisher thường trả về trước khi mọi handler kết thúc |
| Executor queue đầy | Rejection hoặc backpressure theo chính sách cấu hình |
| Một subscriber chậm giữ nhiều thread | Queue age, active threads và latency nhánh nhanh tăng |
| Retry cùng `eventId` | Mỗi subscriber không tạo side effect trùng ngoài ý muốn |
| Nhiều event cùng `orderId` | Kiểm tra điều kiện thứ tự và version |
| Một nhánh bị drop trong Scatter-Gather | Aggregator timeout/failure policy xác định |
| Restart khi còn backlog | Đúng mức bảo đảm lưu trữ/khôi phục đã công bố |

## 16. Quan sát production: biết tắc ở publisher hay subscriber

Khi có cảnh báo “API nhận đơn hàng tăng latency”, cần nhìn theo từng ranh giới:

| Metric / tín hiệu | Diễn giải |
|---|---|
| `publisher.send.duration` | Dispatch đồng bộ đang chậm hay việc submit async đang bị kẹt? |
| `subscriber.handle.duration` theo tên nhánh | Audit, Analytics hay Notification thực sự chậm? |
| Executor active threads / queue depth | Thread và queue có đang bão hòa không? |
| Queue oldest-message age | Message có phải chờ ngày càng lâu không? |
| Task rejected / caller-runs count | Backpressure đã chạm publisher chưa? |
| Retry, DLQ, error-channel message | Một nhánh lỗi hay message bị xử lý lại? |
| Subscriber completion status | Bao nhiêu sự kiện còn thiếu kết quả của một nhánh bắt buộc? |

Trong Spring Integration, có thể bật các cơ chế observability/Micrometer phù hợp để ghi metric ở channel/endpoint và service. Nếu đặt tên metric riêng, giữ tên subscriber là tập nhỏ, ổn định; **không dùng `eventId` hay `orderId` làm metric tag** vì gây cardinality lớn. Dùng tracing/log có kiểm soát để đi sâu theo ID.

Một phương pháp chẩn đoán:

1. Đo riêng thời gian gọi `send()` của publisher.
2. Kiểm tra channel có Executor hay không.
3. Đo latency từng subscriber và số handler đồng thời.
4. Kiểm tra queue, rejection và retry của executor/channel/broker.
5. Đối chiếu các event chậm bằng `eventId`/trace context và xác định nhánh thiếu kết quả.
6. Kiểm tra downstream I/O, connection pool, timeout và locking; bottleneck có thể nằm ngoài Spring Integration.

Không kết luận “publisher bị chậm vì Pub/Sub” chỉ từ một chỉ số; cần phân biệt nghẽn đồng bộ, executor saturation và hệ thống ngoài phản hồi chậm.

## 17. Lựa chọn kiến trúc theo yêu cầu nghiệp vụ

| Nhu cầu | Gợi ý | Điều kiện đi kèm |
|---|---|---|
| Ba handler rất nhanh, cùng JVM, cần đơn giản | `PublishSubscribeChannel` đồng bộ | Handler phải có timeout và thời gian ổn định |
| Publisher không được chờ I/O của subscriber | `PublishSubscribeChannel(Executor)` | Bounded executor, rejection policy, error handling |
| Một nhánh thường xuyên chậm, không muốn ảnh hưởng các nhánh khác | Queue/worker/executor riêng theo nhánh | Cơ chế chặn/từ chối khi queue riêng đầy |
| Subscriber bắt buộc nhận lại event sau restart | Broker hoặc persistent queue riêng | Ack, retry, DLQ, retention, idempotency |
| Publisher phải biết khi nào mọi nhánh thành công | Scatter-Gather/status aggregator | Correlation, timeout, failure results, chống trùng |
| Một worker bất kỳ xử lý event là đủ | Point-to-point channel/competing consumers | Không dùng broadcast nếu không cần fan-out |

**Nguyên tắc chọn:** quyết định theo mức độ bắt buộc của từng subscriber, độ trễ đầu vào, lưu trữ, khả năng retry và thứ tự nghiệp vụ; sau đó mới chọn sync, executor, queue hay broker. Không dùng “asynchronous” như một cách thay thế việc tính capacity.

## 18. Bài thực hành: làm chậm Analytics để quan sát dây chuyền

Hãy xây một flow **OrderPlacedFanout** với `Gateway/producer → PublishSubscribeChannel → Audit, Analytics, Notification`:

1. **Baseline:** dùng channel đồng bộ, cho Audit và Notification mất khoảng 5 ms, Analytics mất khoảng 300–500 ms. Ghi thời gian `send()` và thứ tự log.
2. **Lỗi có chủ đích:** để Analytics ném exception sau khi Audit đã ghi. Kiểm tra publisher quan sát được gì và điều gì xảy ra nếu gửi lại cùng `eventId`.
3. **Async:** đổi channel sang Executor có `core=4`, `max=8`, `queueCapacity=200`; giữ subscriber như cũ. Đo publisher latency, executor queue và thời gian event được xử lý xong.
4. **Áp tải:** tăng tốc độ gửi vượt khả năng của Analytics. Quan sát điểm queue đầy và rejection; thử chính sách phù hợp để biết backpressure trở lại publisher ra sao.
5. **Cách ly:** chuyển Analytics vào queue/worker riêng; so sánh latency của Audit/Notification khi Analytics chậm. Làm đầy queue Analytics để chứng minh giới hạn mới.
6. **Recovery:** thêm lỗi tạm thời và retry có backoff, lưu `eventId` để chống trùng; thử restart và ghi nhận sự khác biệt giữa queue bộ nhớ và phương án durable.
7. **Correlation:** nếu cần chờ đủ cả ba nhánh, phát result riêng và Aggregator theo event ID; kiểm tra tình huống một nhánh không trả về.

**Tiêu chí hoàn thành:** có sơ đồ sync/async, số đo thời gian publisher gửi, thông lượng thực và backlog, test cho subscriber chậm/lỗi, giải thích được hệ quả của rejection policy, chỉ rõ giới hạn durability và mô tả cách giữ correlation khi một event có nhiều nhánh.

## 19. Các hiểu lầm cần tránh

**“Publish-Subscribe luôn chạy song song.”** Sai. Không truyền Executor thì fan-out thường đồng bộ trong thread publisher.

**“Đưa vào Executor là publisher không bao giờ bị ảnh hưởng.”** Sai. Executor có capacity hữu hạn; queue đầy, caller-runs, rejection hay shutdown đều có thể tác động trở lại.

**“Mọi subscriber nhận cùng message nghĩa là mọi subscriber đã lưu thành công.”** Sai. Dispatch và side effect thành công là hai mốc khác nhau; trạng thái tổng hợp cần cơ chế theo dõi riêng.

**“Một subscriber lỗi thì có thể rollback đồng thời các subscriber khác.”** Sai. Không có transaction phân tán mặc định giữa các nhánh fan-out; retry có thể gây xử lý trùng.

**“Pub/Sub đồng nghĩa message broker.”** Sai. PublishSubscribeChannel trong JVM không tự lưu bền vững hay replay như một số cơ chế broker.

**“Queue lớn hơn giải quyết tận gốc subscriber chậm.”** Sai. Queue chỉ dời công việc sang tương lai; nếu tốc độ xử lý thấp hơn tốc độ vào, backlog vẫn tăng.

**“Fan-out đảm bảo thứ tự nghiệp vụ.”** Sai khi có nhiều producer hoặc xử lý song song. Kiểm soát thứ tự theo khóa nghiệp vụ.

**“Có correlation headers là đủ cho Aggregator.”** Sai. Phải có result từ nhánh, release strategy, timeout và xử lý lỗi/thiếu phần.

## 20. Ghi nhớ

**Một subscriber chậm ảnh hưởng publisher trực tiếp trong fan-out đồng bộ**, vì `PublishSubscribeChannel` mặc định xử lý các subscriber trên đường gọi gửi. **Khi thêm Executor**, tác động trực tiếp có thể giảm nhưng thường chuyển thành **áp lực lên thread pool, queue, latency và chính sách rejection**. Subscriber chậm còn có thể làm nhánh nhanh bị ảnh hưởng khi chúng dùng chung tài nguyên.

Thiết kế đúng cần xác định mức độ cách ly từng nhánh, giới hạn capacity, timeout, cách xử lý lỗi và idempotency; nếu bắt buộc durable delivery, sử dụng lưu trữ/broker phù hợp. Khi kết hợp với **Gateway, Router, Filter, Transformer, Splitter, Aggregator, retry, error channel và correlation**, Spring Integration giúp diễn đạt rõ các ranh giới này và kiểm thử được cả đường thành công lẫn tình huống subscriber chậm, lỗi hoặc không phản hồi.
