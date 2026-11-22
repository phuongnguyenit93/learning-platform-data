# Event-driven consumer và polling consumer

## 1. Vấn đề cần giải quyết

Trong một **message flow** của Spring Integration, producer tạo hoặc gửi thông điệp vào **MessageChannel**, còn endpoint phía nhận lấy thông điệp để chạy một hành động: xử lý nghiệp vụ, lọc, biến đổi, định tuyến, ghi dữ liệu hoặc chuyển sang hệ thống bên ngoài. Hai cách kích hoạt một endpoint tiêu thụ thông điệp là **event-driven consumer** và **polling consumer**.

Chúng giải quyết cùng một câu hỏi: *Khi nào và bằng cách nào handler nhận được message từ channel?* Tuy vậy, chúng có cơ chế thực thi khác nhau:

- **Event-driven consumer** đăng ký nhận thông điệp từ một channel hỗ trợ cơ chế subscribe. Khi có message được gửi, channel gọi subscriber phù hợp.
- **Polling consumer** chủ động gọi nhận message từ một channel hỗ trợ lấy dữ liệu theo yêu cầu, dựa trên lịch do **poller** quản lý.

Trong module **SPRING_INTEGRATION_PATTERN**, hai cách tiêu thụ này là nền tảng để thực hành **Enterprise Integration Patterns (EIP)** với **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry, error channel và correlation**. Việc chọn đúng consumer ảnh hưởng đến độ trễ, thông lượng, xử lý lỗi, tính thứ tự, sức chứa hàng chờ và khả năng mở rộng.

**Kết quả mong đợi:** sau bài này, bạn có thể phân biệt hai loại consumer, chọn đúng channel, tạo endpoint bằng annotation hoặc Java DSL, điều chỉnh poller, kiểm thử đường đi message, và xác định những bảo đảm nào thật sự có khi chuyển sang xử lý bất đồng bộ.

## 2. Vị trí consumer trong kiến trúc Spring Integration

Một flow đơn giản có dạng:

~~~mermaid
flowchart LR
    A[Producer hoặc Gateway] --> B[MessageChannel]
    B --> C[Consumer endpoint]
    C --> D[MessageHandler]
    D --> E[Hệ thống nghiệp vụ / channel tiếp theo]
~~~

Trong sơ đồ, **MessageChannel** là ranh giới trao đổi thông điệp; **consumer endpoint** quyết định cách kích hoạt việc nhận; **MessageHandler** thực hiện công việc sau khi thông điệp đã được chuyển tới. Không nên đồng nhất consumer với handler: cùng một handler có thể được nối vào channel theo những cơ chế tiêu thụ khác nhau.

Hai giao diện channel liên quan trực tiếp:

| Giao diện | Hoạt động chính | Consumer thường sử dụng |
|---|---|---|
| `SubscribableChannel` | Cho phép handler **subscribe/unsubscribe** để nhận message do channel phân phối | **Event-driven consumer** |
| `PollableChannel` | Cho phép consumer gọi `receive()` hoặc `receive(timeout)` để lấy message | **Polling consumer** |

Một số hiện thực quen thuộc:

- `DirectChannel`: channel có subscriber, thường gọi handler ngay trong thread của bên gửi.
- `PublishSubscribeChannel`: channel phát tới các subscriber theo cấu hình; không phải hàng đợi cho mỗi consumer tự `receive()`.
- `ExecutorChannel`: channel có subscriber nhưng chuyển việc qua `Executor`; vì thế việc xử lý có thể diễn ra ở thread khác.
- `QueueChannel`: channel có thể `receive()`; message được giữ trong queue cho đến khi consumer nhận, trong giới hạn cấu hình.
- `PriorityChannel`: một dạng channel có thể poll, nơi chính sách ưu tiên có thể ảnh hưởng thứ tự lấy message.

Điểm cốt lõi: **loại consumer dựa vào giao diện channel mà nó nhận dữ liệu**, không dựa riêng vào việc người dùng gọi endpoint bằng HTTP hay message có xuất phát từ hệ thống bên ngoài.

## 3. Event-driven consumer: nhận khi channel phát thông điệp

Event-driven consumer thường được tạo khi endpoint có `inputChannel` là `SubscribableChannel`. Khi ứng dụng khởi tạo, endpoint đăng ký một `MessageHandler` với channel. Khi producer gửi message tới channel, channel phân phối message tới handler theo cơ chế của chính channel đó.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as DirectChannel
    participant E as EventDrivenConsumer
    participant H as Handler
    P->>C: send(Message)
    C->>E: dispatch tới subscriber
    E->>H: handleMessage(Message)
    H-->>E: hoàn tất hoặc ném exception
    E-->>C: trả điều khiển
    C-->>P: send hoàn tất hoặc lỗi
~~~

Với `DirectChannel`, đường đi thường **đồng bộ**: handler chạy trên thread đã gọi `send()`; xử lý chậm sẽ khiến bên gửi chờ lâu hơn. Nếu handler ném exception, lỗi có thể truyền ngược qua lời gọi gửi và đi tới Gateway/caller. Lúc này, event-driven **không có nghĩa là chạy nền**.

Ngược lại, `ExecutorChannel` cũng thuộc nhóm channel có subscriber. Nhưng nó có thể giao xử lý cho thread pool và thay đổi thời điểm ngoại lệ xuất hiện. Vì vậy cần tách hai câu hỏi:

1. **Ai kích hoạt consumer?** Channel chủ động dispatch hay một poller gọi `receive()`?
2. **Handler chạy ở đâu?** Trên thread bên gửi, thread executor hay thread của scheduler?

Event-driven consumer phù hợp với xử lý ngắn trong cùng tiến trình, các flow cần độ trễ thấp, hoặc các pipeline EIP có các bước liên tiếp như **Filter → Transformer → Router** mà chưa cần đặt hàng đợi.

### Minh họa với Filter và Router

~~~mermaid
flowchart LR
    G[Gateway] --> D[DirectChannel]
    D --> F{Filter hợp lệ?}
    F -->|Có| T[Transformer]
    F -->|Không| X[Rejected channel]
    T --> R{Router theo khu vực}
    R -->|VN| VN[Consumer VN]
    R -->|Khác| OS[Consumer khác]
~~~

Mỗi endpoint trong pipeline có thể dùng một input channel với subscriber. Nếu chuỗi đều dùng `DirectChannel`, lỗi hay thời gian xử lý của một handler có thể tác động trực tiếp tới producer. Khi cần cách ly tốc độ của các chặng, hãy cân nhắc một ranh giới bất đồng bộ hoặc channel có queue, nhưng phải đánh giá thêm giới hạn tải và độ bền dữ liệu.

## 4. Polling consumer: nhận message theo nhịp poller

**Polling consumer** nhận thông điệp từ `PollableChannel`. Thay vì subscribe, một bộ lập lịch (*poller*) kích hoạt việc kiểm tra channel, sau đó gọi handler nếu nhận được message.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as QueueChannel
    participant T as Poller / Scheduler
    participant E as PollingConsumer
    participant H as Handler
    P->>Q: send(Message A)
    Note over Q: Message A đang chờ
    T->>E: kích hoạt theo lịch
    E->>Q: receive(timeout)
    Q-->>E: Message A
    E->>H: handleMessage(A)
    H-->>E: hoàn tất hoặc lỗi
    Note over T,E: Lần poll sau phụ thuộc cấu hình trigger
~~~

Một lần poll có thể xử lý **nhiều message**, tùy thuộc cấu hình `maxMessagesPerPoll`. Nếu queue rỗng, lần poll có thể không xử lý thông điệp nào. Poller là bộ phận **lập lịch/điều phối nhận**, không phải một broker bền vững.

Các thành phần cần phân biệt:

| Thành phần | Vai trò |
|---|---|
| `QueueChannel` | Lưu tạm message chờ được `receive()` |
| `PollingConsumer` | Endpoint lấy message từ channel rồi gọi `MessageHandler` |
| `PollerMetadata` | Cấu hình lịch, số message tối đa mỗi lần poll và các tùy chọn điều phối |
| `TaskScheduler` / trigger | Quyết định khi nào lần poll tiếp theo được kích hoạt |
| `MessageStore` (nếu cấu hình) | Quyết định cách lưu message; có thể là bộ nhớ hoặc kho bền vững tùy hiện thực |

Polling consumer hữu ích khi dữ liệu đến nhanh hơn khả năng xử lý, khi muốn tiêu thụ từng đợt có giới hạn hoặc khi công việc phù hợp với mô hình queue và lịch xử lý. Tuy nhiên, **thêm QueueChannel không tự tạo durability**: queue mặc định trong bộ nhớ có thể mất dữ liệu khi ứng dụng dừng.

## 5. Bảng so sánh hai cơ chế

| Tiêu chí | Event-driven consumer | Polling consumer |
|---|---|---|
| Input channel | `SubscribableChannel` | `PollableChannel` |
| Cơ chế nhận | Channel dispatch tới subscriber | Consumer gọi `receive()` theo poller |
| Kích hoạt | Có message được gửi và channel phân phối | Trigger/lịch poll xảy ra |
| Ví dụ channel | `DirectChannel`, `ExecutorChannel`, `PublishSubscribeChannel` | `QueueChannel`, `PriorityChannel` |
| Độ trễ | Thường thấp nếu handler sẵn sàng, phụ thuộc kiểu channel | Phụ thuộc lịch, tải, thời gian chờ và backlog |
| Khả năng cách ly producer/consumer | Thấp với `DirectChannel`; có thể cao hơn với executor | Có queue đệm, nhưng vẫn phải kiểm soát sức chứa |
| Thread xử lý | Thread bên gửi hoặc executor tùy channel | Thường là thread lập lịch/executor poller |
| Thứ tự | Phụ thuộc kiểu channel và concurrency | Phụ thuộc queue, poller và concurrency |
| Lỗi | Có thể lan ngược bên gửi với luồng đồng bộ | Xảy ra trên luồng poller; cần cơ chế error/recovery cụ thể |
| Retry/durability | Không tự có | Không tự có |
| Phù hợp | Flow ngắn, xử lý ngay, nhánh EIP nội bộ | Buffer, điều tiết công việc, xử lý theo nhịp và batch nhỏ |

**Không có lựa chọn nào mặc định nhanh hơn hoặc đáng tin cậy hơn trong mọi tình huống.** Chẳng hạn, dùng `ExecutorChannel` tạo bất đồng bộ nhưng vẫn là event-driven, trong khi một poller có khoảng lặp ngắn và queue luôn đầy vẫn có thể đạt thông lượng cao.

## 6. Ví dụ Spring Integration: hai endpoint dùng chung kiểu nghiệp vụ

Đoạn mã sau minh họa **một consumer nhận ngay qua `DirectChannel`** và **một consumer lấy message từ `QueueChannel` mỗi khoảng thời gian xác định**. Có thể dùng với Spring Boot đã cấu hình Spring Integration; các import thông thường được lược bỏ để tập trung vào hai cách tiêu thụ.

~~~java
record OrderPlaced(String orderId, String region) {}

@Configuration
@EnableIntegration
class ConsumerChannels {

    @Bean(name = "orders.immediate")
    MessageChannel immediateChannel() {
        return new DirectChannel();
    }

    @Bean(name = "orders.buffered")
    PollableChannel bufferedChannel() {
        return new QueueChannel(100); // Giới hạn 100 message đang chờ.
    }

    @Bean
    OrderConsumers orderConsumers() {
        return new OrderConsumers();
    }
}

class OrderConsumers {

    @ServiceActivator(inputChannel = "orders.immediate")
    public void consumeImmediately(OrderPlaced order) {
        System.out.println("EVENT: " + order.orderId());
    }

    @ServiceActivator(
        inputChannel = "orders.buffered",
        poller = @Poller(fixedDelay = "1000", maxMessagesPerPoll = "5")
    )
    public void consumeFromQueue(OrderPlaced order) {
        System.out.println("POLL: " + order.orderId());
    }
}
~~~

Hai method cùng xử lý payload `OrderPlaced`, nhưng ranh giới nhận message khác nhau:

- `consumeImmediately()` được gọi khi `orders.immediate` dispatch message tới subscriber. Với `DirectChannel`, nó thường chạy ngay trên thread gửi.
- `consumeFromQueue()` được một polling endpoint gọi sau khi lấy message khỏi `orders.buffered`. Poller cấu hình khoảng `fixedDelay = "1000"` tính bằng **mili-giây**, và mỗi lần poll cố gắng xử lý tối đa **5 message**, nếu có.

Ví dụ gửi message từ đoạn mã sử dụng application context:

~~~java
MessageChannel immediate =
    context.getBean("orders.immediate", MessageChannel.class);
MessageChannel buffered =
    context.getBean("orders.buffered", MessageChannel.class);

Message<OrderPlaced> event = MessageBuilder
    .withPayload(new OrderPlaced("ORD-101", "VN"))
    .setHeader("correlationId", "ORD-101")
    .build();

immediate.send(event); // Gọi subscriber theo cơ chế DirectChannel.
buffered.send(event);  // Đưa vào hàng chờ để poller lấy ra.
~~~

Trong ví dụ này, cùng một đối tượng message chỉ dùng để so sánh hai đường đi. Trong nghiệp vụ thực tế, không gửi cùng một sự kiện qua cả hai nhánh nếu hai nhánh đều tạo cùng một tác dụng phụ, trừ khi có quy tắc idempotency rõ ràng.

Việc `send()` tới `QueueChannel` trả về thành công chỉ cho biết message được **channel chấp nhận** tại thời điểm đó; chưa chứng minh handler đã xử lý xong hoặc message sẽ tồn tại qua restart.

### Cấu hình tương đương bằng Java DSL

Nếu muốn diễn đạt việc nối handler bằng Java DSL, có thể khai báo hai flow dưới đây. Đây là **phương án thay thế** cho hai phương thức gắn `@ServiceActivator` ở trên: chỉ dùng một cách nối consumer cho từng channel trong cùng ví dụ để tránh xử lý trùng.

~~~java
@Bean
IntegrationFlow eventConsumerDsl() {
    return IntegrationFlow.from("orders.immediate")
        .handle(message ->
            System.out.println("EVENT: " + message.getPayload()))
        .get();
}

@Bean
IntegrationFlow pollingConsumerDsl() {
    return IntegrationFlow.from("orders.buffered")
        .handle(
            message -> System.out.println("POLL: " + message.getPayload()),
            endpoint -> endpoint.poller(
                Pollers.fixedDelay(Duration.ofSeconds(1))
                    .maxMessagesPerPoll(5)))
        .get();
}
~~~

Hai channel bean của ví dụ trước vẫn được dùng. Endpoint đầu tiên không cần poller vì channel hỗ trợ subscribe. Endpoint thứ hai **phải có poller** để lấy message từ `PollableChannel`; cấu hình tại endpoint giúp xác định nhịp và khối lượng tiêu thụ.

## 7. Cấu hình poller: tần suất, giới hạn và khả năng quá tải

Một poller cần được cấu hình theo tốc độ vào, tốc độ xử lý, kích thước hàng đợi và yêu cầu độ trễ. Các tham số thường gặp:

| Tham số | Ý nghĩa | Khi nào điều chỉnh |
|---|---|---|
| `fixedDelay` | Chờ một khoảng sau khi lượt poll trước kết thúc rồi lên lịch lượt tiếp | Muốn tránh tạo nhiều chu kỳ quá sát khi xử lý chậm |
| `fixedRate` | Lập lịch theo nhịp thời gian định kỳ | Cần nhịp kích hoạt tương đối đều; phải xem giới hạn thread |
| `maxMessagesPerPoll` | Giới hạn số lần lấy/xử lý message tối đa mỗi lượt | Giới hạn lượng việc một lần poll chiếm dụng |
| `receiveTimeout` | Thời gian chờ khi lấy message từ channel, nếu áp dụng | Tránh poller giữ thread quá lâu khi queue trống |
| `taskExecutor` | Executor được dùng theo cấu hình poller | Điều tiết concurrency khi cần xử lý nhiều message |
| `errorChannel` / error handler | Tuyến nhận lỗi từ công việc polling theo cấu hình | Phân loại lỗi, cảnh báo hoặc chuyển quy trình khôi phục |

**Ví dụ về cách đọc nhịp poll:** cấu hình `fixedDelay = 1000 ms`, `maxMessagesPerPoll = 5` không đồng nghĩa hệ thống luôn xử lý đúng **5 message/giây**. Nếu handler chậm, queue rỗng hoặc scheduler bận, tốc độ thực tế khác rất nhiều. Poller phải chạy xong một lượt thì trigger theo `fixedDelay` mới lên lịch cho lượt tiếp theo.

Giả sử một handler tốn trung bình **200 ms/message**. Với một polling thread và `maxMessagesPerPoll = 5`, năm message có thể chiếm khoảng một giây xử lý, chưa tính I/O và thời gian đợi giữa các lượt. Nếu producer gửi 20 message/giây mà consumer hoàn tất dưới 5 message/giây, queue sẽ tích tụ, bất kể có dùng fixed delay hay không.

Không nên cấu hình poller đọc không giới hạn message trong một lượt khi queue thường xuyên đầy; một lượt quá dài có thể khiến các tác vụ dùng chung scheduler bị chiếm dụng. Giới hạn dương, đủ nhỏ để quan sát và có thể hiệu chỉnh là điểm bắt đầu hợp lý.

### Phân biệt `fixedDelay` và `fixedRate`

~~~text
fixedDelay = 1s
[poll + xử lý] --- chờ 1s --- [poll + xử lý] --- chờ 1s --- ...

fixedRate = 1s
|-- mốc lịch 1 --|-- mốc lịch 2 --|-- mốc lịch 3 --|...
    Thời điểm thực thi còn tùy thời gian xử lý và scheduler.
~~~

`fixedRate` không đảm bảo handler chậm sẽ được thực thi đồng thời hoặc mỗi lần kích hoạt đều đúng mili-giây; các hạn chế của scheduler và cấu hình executor quyết định khả năng chạy song song. Cần thử nghiệm bằng số đo thực tế thay vì suy từ giá trị cấu hình.

## 8. Polling consumer không đồng nghĩa với polling inbound adapter

Đây là một nhầm lẫn thường gặp trong Spring Integration.

**Polling consumer** nhận message **từ một `PollableChannel`** rồi đưa vào handler:

~~~text
Producer → QueueChannel → PollingConsumer → Service Activator
~~~

**Source polling inbound channel adapter** lại chủ động hỏi một **MessageSource** như thư mục tệp, JDBC hoặc một hệ thống chỉ có API pull, rồi **phát message vào một channel**. Endpoint loại này đóng vai trò nguồn đưa dữ liệu vào flow:

~~~text
File/JDBC/nguồn có API pull → MessageSource
                               ↑
                            Poller
                               ↓
                      Inbound channel adapter
                               ↓
                        MessageChannel
                               ↓
                        Consumer endpoint
~~~

Ví dụ: dùng File inbound adapter quét thư mục mỗi 5 giây, sau đó phát file vào một `DirectChannel` với consumer xử lý ngay. Toàn bộ flow có hành vi *polling ở đầu vào*, nhưng consumer của `DirectChannel` vẫn là **event-driven consumer**.

Một message broker cũng có thể có API fetch/poll nội bộ trong thư viện client. Điều đó không đủ để kết luận consumer endpoint của **Spring Integration** nhất thiết là `PollingConsumer`: phải xem adapter phát ra kiểu channel nào và cách endpoint được kết nối.

## 9. Threading, thứ tự và mô hình backpressure

Trong thực tế, việc chạy đúng thứ tự hay không phụ thuộc cả channel và mức concurrency:

1. **DirectChannel + handler đồng bộ**: producer chờ handler; có thể dễ theo dõi thứ tự các lời gọi trên một thread, nhưng nhiều producer thread vẫn có thể gửi đồng thời.
2. **ExecutorChannel**: producer giao việc qua executor; thứ tự hoàn tất có thể khác thứ tự gửi.
3. **QueueChannel + một polling consumer tuần tự**: thường lấy theo thứ tự FIFO của queue mặc định, nhưng thứ tự tác dụng phụ cuối cùng có thể khác nếu handler tự tạo công việc song song.
4. **PriorityChannel**: ưu tiên có thể khiến message đến sau được lấy trước.
5. **Nhiều polling consumer / worker**: có thể tăng thông lượng nhưng cũng tăng rủi ro xử lý xen kẽ và thay đổi thứ tự hoàn tất.

Nếu đơn hàng phải xử lý tuần tự theo `orderId`, không nên chỉ dựa vào việc dùng một queue chung. Hãy cân nhắc partition theo khóa, giới hạn xử lý đồng thời theo khóa hoặc một cơ chế tuần tự hóa nghiệp vụ. Với **Splitter/Aggregator**, cần giữ và kiểm tra `correlationId`, `sequenceNumber` và `sequenceSize` khi thông điệp tách ra rồi quay về.

**Backpressure** là khả năng hệ thống xử lý tình huống producer nhanh hơn consumer:

| Cơ chế | Tác dụng | Giới hạn cần hiểu |
|---|---|---|
| Handler đồng bộ qua `DirectChannel` | Tốc độ producer bị ảnh hưởng trực tiếp bởi thời gian handler | Có thể làm tăng latency và chiếm thread bên gọi |
| Queue có giới hạn sức chứa | Giữ message trong backlog hữu hạn | Khi queue đầy, bên gửi phải xử lý kết quả từ chối/chờ |
| Poller với concurrency giới hạn | Giới hạn số tác vụ được lấy hoặc đang chạy | Không tự giới hạn tốc độ producer đầu vào |
| Broker có lưu trữ bền vững | Giảm phụ thuộc vào vòng đời một tiến trình | Cần cấu hình ack, lưu trữ, retry, DLQ và capacity riêng |

Không đặt queue không giới hạn vào hệ thống có tốc độ vào lớn mà chưa đo bộ nhớ, thời gian chờ và cơ chế cảnh báo. Với `QueueChannel(100)`, cần nêu rõ producer phải xử lý trường hợp gửi thất bại hoặc không có chỗ trong queue, thay vì tin rằng mọi `send()` đều thành công.

## 10. Error channel, retry và hành vi khi handler thất bại

Consumer endpoint thường gọi `MessageHandler`. Nhưng **lỗi được báo về đâu** phụ thuộc ranh giới thực thi:

| Tình huống | Điểm xuất hiện lỗi | Điều cần thiết kế |
|---|---|---|
| `DirectChannel` gọi handler ném exception | Có thể truyền ngược trên thread gửi/Gateway | Bên gọi bắt lỗi và quyết định retry/phản hồi |
| `ExecutorChannel` xử lý trên thread khác | Không còn cùng call stack với producer | Error handling của executor/flow, quan sát và retry |
| Poller lấy từ `QueueChannel`, handler ném exception | Lỗi xảy ra trong tác vụ polling | Error channel/error handler, khôi phục và chính sách message đã lấy |
| Consumer nhận từ broker | Lỗi liên quan cả adapter và broker | Ack/nack, redelivery, retry/DLQ theo cấu hình |

**Đặc biệt với `QueueChannel`:** khi `receive()` đã lấy message khỏi một queue trong bộ nhớ, việc handler ném exception **không mặc định đưa message trở lại queue**. Nếu tác vụ bắt buộc không được thất lạc khi lỗi hoặc restart, cần thiết kế lưu trữ bền vững, transaction/recovery phù hợp, hoặc dùng broker với chính sách nhận và xác nhận rõ ràng.

Retry có giới hạn có thể được áp dụng cho endpoint bằng cơ chế advice khi phù hợp, kết hợp backoff và bộ lọc lỗi có thể thử lại. Tuy nhiên, retry một thao tác đã tạo tác dụng phụ (ghi tiền, tạo hóa đơn) có thể gây trùng dữ liệu. Hãy dùng khóa idempotency và xác định thời điểm nào một message được coi là hoàn tất.

Nếu một message sai cấu trúc vĩnh viễn, không nên retry vô hạn. Có thể chuyển tới kênh từ chối, dead-letter queue hoặc quy trình phân tích lỗi. Với **Filter**, discard channel xử lý trường hợp điều kiện không đạt; với **exception**, đường lỗi là cơ chế khác và phải cấu hình tương ứng.

## 11. Khi nào nên chọn mỗi cách?

Một số tình huống điển hình:

| Tình huống | Gợi ý | Lý do |
|---|---|---|
| Gateway gọi một chuỗi Filter → Transformer → Router trong JVM | `DirectChannel` và event-driven | Ít thành phần, dễ theo dõi và độ trễ thấp |
| Cần chuyển handler sang thread pool, producer không cần chờ kết quả đồng bộ | `ExecutorChannel` và event-driven | Tách thread mà vẫn dùng subscribe |
| Nhiều order đến nhanh, xử lý tồn kho chậm hơn và muốn buffer có giới hạn | `QueueChannel` + polling consumer | Điều tiết việc lấy message và quan sát backlog |
| Quét thư mục để nhập file mới | Polling inbound adapter + channel thích hợp | Poll nguồn ngoài; consumer downstream có thể là event-driven |
| Cần gửi dữ liệu qua hai microservice độc lập và phục hồi sau restart | Adapter/broker có cấu hình lưu trữ, ack và retry | Vượt ranh giới tiến trình; channel in-memory đơn thuần chưa đủ |
| Cần phản hồi ngay cho người gọi khi xử lý nghiệp vụ hoàn tất | Flow đồng bộ được thiết kế rõ reply/error | Dễ liên kết response với lời gọi; phải quản lý timeout |

**Quy trình chọn nhanh:** xác định yêu cầu phản hồi (đồng bộ hay bất đồng bộ), độ trễ chấp nhận được, tốc độ vào/ra, giới hạn bộ nhớ, thứ tự, chính sách lỗi và yêu cầu phục hồi. Sau đó mới chọn loại channel và consumer. Không chọn polling chỉ vì tác vụ “nặng”, hoặc event-driven chỉ vì producer phát “event”.

## 12. Kiểm thử consumer theo từng loại

Để kiểm tra endpoint, cần quan sát được message tới handler nào, vào lúc nào, có bị lỗi hoặc tồn đọng không. Spring Integration hỗ trợ kiểm thử flow và mocking endpoint; khi làm bài tập cũng có thể dùng các handler ghi nhận thông điệp vào collection thread-safe và đồng bộ kết quả bằng latch.

| Kiểm thử | Thiết lập | Kết quả kỳ vọng |
|---|---|---|
| Event-driven với `DirectChannel` | Gửi một `OrderPlaced` hợp lệ | Handler được gọi trước khi lời gửi đồng bộ kết thúc |
| Event-driven ném lỗi | Handler chủ động ném exception | Bên gửi quan sát lỗi theo đường gọi đã cấu hình |
| Poller queue rỗng | Không đưa message vào `QueueChannel` | Không xử lý nghiệp vụ giả; endpoint vẫn hoạt động |
| Poller có backlog | Gửi hơn `maxMessagesPerPoll` message | Nhiều lượt poll cần thiết; tất cả message hợp lệ cuối cùng được xử lý |
| Queue đầy | Capacity nhỏ, producer gửi vượt sức chứa | Kết quả gửi/chờ/từ chối phù hợp với timeout và chính sách producer |
| Handler chậm | Thêm độ trễ có kiểm soát | Đo được backlog và throughput, không suy sai tốc độ từ `fixedDelay` |
| Handler polling ném lỗi | Giả lập lỗi trong một lần nhận | Lỗi được ghi nhận; xác định rõ message có được retry hay bị mất |
| Concurrency cao | Tăng số worker/threads | Phát hiện thay đổi thứ tự hoàn tất và dữ liệu dùng chung |
| Correlation | Hai đơn hàng tách/gộp xen kẽ | Không có kết quả của order này lọt sang order kia |

Với polling consumer, không nên kiểm tra bằng cách `Thread.sleep()` một khoảng cố định rồi giả định mọi message đã được xử lý. Hãy dùng điều kiện hoàn tất và timeout có giới hạn, ghi thời điểm bắt đầu/kết thúc, kích thước queue và số lần handler đã chạy. Khi cần hành vi xác định, có thể kiểm soát scheduler hoặc kích hoạt poll trong môi trường test phù hợp.

Khi dùng `ExecutorChannel`, kiểm tra tác dụng phụ và exception trên thread của executor. Khi dùng broker, bổ sung integration test cho tình huống worker tắt, restart, redelivery, retry và idempotency.

## 13. Quan sát và vận hành

Chọn cơ chế consumer không đủ để vận hành flow ổn định. Cần quan sát:

- **Ingress rate**: số message đi vào mỗi channel theo đơn vị thời gian.
- **Processing rate và thời gian xử lý**: số message hoàn tất, latency trung bình và p95/p99 tại handler.
- **Queue depth / backlog age**: có bao nhiêu message chờ và message lâu nhất đã chờ bao lâu.
- **Poll activity**: lượt poll có message, lượt poll rỗng, số message được xử lý mỗi lượt.
- **Failures, retries và DLQ**: tỉ lệ lỗi, loại lỗi, số lần thử lại và số message cần xử lý thủ công.
- **Correlation/tracing**: `messageId`, `correlationId`, `orderId` và trace context cần thiết để theo dõi qua Gateway, Router, Splitter và Aggregator.

Micrometer và các cơ chế observability của Spring có thể giúp thu metric/tracing khi đã cấu hình đúng. Nên dùng tên channel/endpoint nhất quán, giảm ghi log payload nhạy cảm và tạo cảnh báo theo backlog, age, lỗi hoặc độ trễ. Với polling consumer, metric queue tăng liên tục là dấu hiệu producer đang vượt quá khả năng xử lý hoặc consumer đang lỗi.

Trong một hệ phân tán, một message có thể bị giao lại sau lỗi hoặc mất phản hồi; đừng dùng riêng `messageId` của message mới tạo để chống trùng nghiệp vụ. Cần khóa nghiệp vụ ổn định, chẳng hạn `eventId`/idempotency key, và quy trình ghi nhận xử lý an toàn.

## 14. Bài thực hành: chuyển một luồng xử lý đơn hàng từ push sang poll

Xây dựng ứng dụng thử nghiệm với payload:

~~~java
record OrderPlaced(
    String eventId,
    String orderId,
    String region,
    int itemCount
) {}
~~~

**Giai đoạn A — Event-driven:** tạo Gateway phát `OrderPlaced` vào `DirectChannel`; Filter loại `itemCount <= 0`; Transformer chuẩn hóa `region`; Router tách `VN` và `OTHER`; Service Activator ghi nhận order và correlation ID. Đo độ trễ một lần gửi và thử handler ném exception. Ghi lại lỗi có truyền ngược tới Gateway hay không.

**Giai đoạn B — Polling:** thêm một `QueueChannel` sức chứa 100 và polling consumer với `fixedDelay = 1000 ms`, `maxMessagesPerPoll = 5`. Phát 200 message giả lập, cố tình làm chậm handler. Quan sát thời điểm queue đầy, số message được producer gửi thành công, thời gian xử lý hết backlog và hành vi khi handler ném lỗi.

**Giai đoạn C — Khả năng phục hồi:** giữ dữ liệu và nghiệp vụ thử nghiệm nhất quán bằng cách lựa chọn message store/broker thích hợp, mô phỏng restart giữa chừng và thử gửi lại một `eventId`. Kiểm tra idempotency và correlation; ghi lại message nào được lưu trữ, được xử lý, đang chờ hoặc thất bại.

**Tiêu chí hoàn thành:**

1. Giải thích được vì sao `DirectChannel` tạo event-driven consumer và `QueueChannel` tạo polling consumer ở hai endpoint đã cấu hình.
2. Chứng minh rằng event-driven không mặc định bất đồng bộ và polling không mặc định bền vững.
3. Có số đo throughput, queue depth, độ trễ và thời gian drain backlog cho ít nhất hai cấu hình poller.
4. Có kiểm thử Filter/Router, correlation và cả hai đường xử lý lỗi.
5. Nêu được phương án xử lý khi queue đầy, handler lỗi, message được giao lại và worker khởi động lại.

## 15. Những lỗi thiết kế cần tránh

**Nhầm event-driven với asynchronous.** `DirectChannel` dispatch theo subscribe nhưng thường chạy cùng thread bên gửi; chuyển sang `ExecutorChannel` mới thay đổi cách thực thi theo executor.

**Nhầm polling consumer với nguồn được poll.** Polling consumer lấy từ `PollableChannel`; inbound adapter sử dụng `MessageSource` đi lấy dữ liệu bên ngoài rồi phát message vào channel. Hai mô hình có thể cùng xuất hiện trong một flow.

**Coi QueueChannel là broker bền vững.** Hàng đợi trong bộ nhớ chỉ tạo khoảng đệm giữa producer và consumer. Phục hồi qua restart, retry, transaction và redelivery cần được thiết kế riêng.

**Tăng concurrency mà không kiểm tra thứ tự và correlation.** Tốc độ có thể tăng, nhưng những message có liên hệ có thể hoàn tất không theo thứ tự. Điều này đặc biệt quan trọng khi Splitter và Aggregator dùng sequence headers.

**Giả định maxMessagesPerPoll là giới hạn message/giây.** Tham số này điều khiển số message trong mỗi lượt, còn tốc độ thực tế phụ thuộc handler, trigger, scheduler và tình trạng queue.

**Không đo backlog và đường lỗi.** Một flow có thể “chạy bình thường” dù message chờ hàng phút hoặc bị mất sau khi handler polling thất bại. Metric, timeout và idempotency cần đi cùng với thiết kế endpoint.

## 16. Tổng kết kiến thức

**Event-driven consumer** nhận message nhờ cơ chế subscribe của `SubscribableChannel`; **polling consumer** lấy message từ `PollableChannel` theo lịch poller. Sự khác biệt thể hiện ở ai chủ động đưa message tới handler, cách điều phối thực thi, độ trễ và khả năng điều tiết backlog.

Với Spring Integration, hãy bắt đầu bằng hợp đồng message và yêu cầu nghiệp vụ, chọn channel/consumer tương ứng, rồi áp dụng **Filter, Transformer, Router, Splitter, Aggregator, Gateway, retry, error channel và correlation** theo đúng điểm cần thiết. Cuối cùng, kiểm thử các nhánh, đo throughput/latency/backlog và chứng minh được cách xử lý lỗi trước khi đưa message flow lên nhiều tiến trình.
