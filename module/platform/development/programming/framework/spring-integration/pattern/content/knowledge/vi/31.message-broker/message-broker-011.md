# Khác biệt broker semantics với Spring Integration channel

**Chương:** Message broker  
**Bài học:** Khác biệt broker semantics với Spring Integration channel  
**Phạm vi:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns (EIP) bằng Spring Integration, từ Router, Filter, Transformer, Splitter, Aggregator và Gateway tới retry, error channel, correlation, kiểm thử và quan sát luồng thông điệp.

## Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt **message channel** (đường dẫn logic giữa các thành phần tích hợp) và **message broker** (hệ thống trung gian truyền/lưu thông điệp giữa producer và consumer).
2. Đọc đúng ý nghĩa của `send()`, `receive()`, ACK, offset commit, durability, redelivery, ordering và consumer group trong từng tầng.
3. Chọn giữa `DirectChannel`, `ExecutorChannel`, `QueueChannel`, `PublishSubscribeChannel` và broker ngoài theo mức độ tách tiến trình, độ tin cậy và lưu lượng.
4. Thiết kế luồng Spring Integration qua RabbitMQ, JMS hoặc Kafka mà không nhầm lỗi, retry hay correlation của ứng dụng với cam kết của hệ thống truyền thông.
5. Kiểm thử các điểm crash, message trùng, consumer lỗi và áp lực hàng đợi trước khi đưa hệ thống vào vận hành.

## 1. Hai khái niệm ở hai tầng khác nhau

**Spring Integration channel** là một **abstraction bên trong ứng dụng**. Thành phần gửi biết một `MessageChannel` và đẩy `Message<?>` vào đó; thành phần nhận kết nối với channel thông qua endpoint. Channel giúp tách trách nhiệm xử lý theo EIP, nhưng **một channel thông thường không tự đồng nghĩa với một hàng đợi broker bền vững**.

**Message broker** là dịch vụ hoặc hạ tầng truyền thông như RabbitMQ hay JMS provider. Broker tiếp nhận message, quản lý queue/subscription, phân phối cho consumer và áp dụng cơ chế lưu trữ, xác nhận, gửi lại hay hạn mức theo cấu hình. Kafka cung cấp mô hình **distributed log** với topic, partition và offset; không nên diễn giải Kafka như một queue xóa message ngay sau khi đọc.

Hai khái niệm có thể phối hợp trong cùng luồng. Một adapter Spring Integration kết nối tới broker; ở bên trong mỗi ứng dụng, các channel tiếp tục nối Router, Filter, Transformer, Service Activator và handler.

~~~mermaid
flowchart LR
  subgraph A["Ứng dụng A — Spring Integration"]
    G["Gateway"] --> T["Transformer"]
    T --> C1["DirectChannel"]
    C1 --> OUT["Outbound adapter"]
  end
  OUT -->|Publish| B[("Broker: queue / topic / log")]
  B -->|Deliver / consume| IN["Inbound adapter"]
  subgraph W["Ứng dụng B — Spring Integration"]
    IN --> C2["Channel nội bộ"]
    C2 --> R["Router / Filter"]
    R --> H["Service Activator"]
  end
~~~

Adapter là **ranh giới giao thức**. Channel phía trước/sau adapter là thành phần của ứng dụng, còn queue/topic, cơ chế ACK và lưu trữ nằm ở transport/broker tương ứng.

## 2. Semantics là gì và vì sao phải nói rõ?

*Semantics* là những quy tắc quan sát được khi message được gửi, nhận, lỗi hoặc ứng dụng dừng: ai nhận, nhận lúc nào, message còn hay mất, đã hoàn tất hay chưa, có được gửi lại không và thứ tự nào được bảo đảm.

Ví dụ, câu “gửi message thành công” có thể có ít nhất bốn ý nghĩa khác nhau:

1. Message đã được một `MessageChannel` **chấp nhận**.
2. Message đã đến một **outbound adapter** và adapter đã gọi thành công API client.
3. Broker đã xác nhận tiếp nhận hoặc **ghi bền vững** theo cấu hình producer/broker.
4. Consumer đã **commit nghiệp vụ** và xác nhận xử lý.

Bốn mốc này không đồng nhất. Trong thiết kế hệ thống tin cậy, luôn ghi chính xác loại xác nhận mà API hoặc log đang nói đến.

### 2.1 API channel của Spring Integration

- `MessageChannel.send(message)` gửi message đến channel và trả về kết quả theo hợp đồng của channel. Giá trị `true` không phải một chứng chỉ “nghiệp vụ ở dịch vụ khác đã xử lý xong”.
- `SubscribableChannel` cung cấp mô hình đăng ký handler để channel đẩy message tới người nhận, ví dụ `DirectChannel`.
- `PollableChannel` cho phép consumer gọi `receive()` hoặc poller lấy message, ví dụ `QueueChannel`.
- Một flow có thể dùng channel dù **không có network, broker hay lưu trữ ngoài tiến trình**.

### 2.2 API ở broker

- **Publish/send:** producer gửi tới exchange, destination, topic hoặc queue theo protocol.
- **Delivery/fetch:** broker chuyển message cho consumer, hoặc consumer đọc bản ghi theo vị trí.
- **ACK/negative ACK/transaction/offset commit:** cơ chế xác định lần giao đã được xử lý hoặc vị trí tiêu thụ đã tiến tới đâu.
- **Retention, persistence, replication:** cơ chế quyết định message tồn tại và phục hồi như thế nào; khác nhau giữa queue broker và distributed log.

Một lần `send()` thành công trong Spring Integration không tự động tạo ACK của RabbitMQ, commit JMS session hay commit Kafka offset.

## 3. Bốn channel thường gặp và ý nghĩa thực tế

| Channel | Cách chuyển message | Đồng bộ và phạm vi | Durability/redelivery mặc định |
|---|---|---|---|
| `DirectChannel` | Gọi handler/subscriber trực tiếp theo cơ chế dispatch của channel. | Thường xử lý **ngay trên thread gọi send**; không tạo ranh giới tiến trình. | Không lưu bền vững; exception đồng bộ có thể truyền về phía gửi. |
| `ExecutorChannel` | Giao xử lý cho `TaskExecutor`. | Tách thread; chịu quy tắc scheduling và giới hạn executor. | Không tự có durable queue hay ACK broker; phải cấu hình error handling phù hợp. |
| `QueueChannel` | Giữ message để poller/consumer kéo ra. | Tách thời điểm enqueue và dequeue; thông thường vẫn nằm trong một ứng dụng. | Mặc định lưu trong bộ nhớ; cần persistent `MessageStore` phù hợp để chịu restart. |
| `PublishSubscribeChannel` | Phát cho các subscriber đã đăng ký. | Mặc định có thể gọi đồng bộ; nếu gắn executor thì xử lý bất đồng bộ. | Không tự tạo các subscription bền vững như broker; lỗi từng subscriber tùy cấu hình. |

**Điểm quan trọng:** Tên gọi `QueueChannel` không có nghĩa đó là “RabbitMQ queue thu nhỏ” với mọi cam kết ACK, TTL, DLQ hay khả năng phục hồi giống broker. Tương tự, `PublishSubscribeChannel` không mặc nhiên có fan-out bền vững đến ứng dụng khác.

### 3.1 Synchronous không có nghĩa bền vững

Ví dụ, dùng `DirectChannel` đưa `OrderCreated` tới một Service Activator. Khi handler ném exception trong lời gọi đồng bộ, phía gửi có thể nhận lỗi ngay. Tuy nhiên nếu tiến trình chết trước khi nghiệp vụ commit, channel không giữ một bản sao để tự khởi chạy lại sau restart.

Khi thay bằng `ExecutorChannel`, xử lý đi sang thread khác. Việc `send()` chấp nhận task **không bảo đảm** worker sẽ hoàn thành; lỗi xảy ra sau đó có thể được chuyển qua `errorChannel` hoặc đường xử lý lỗi của executor, tùy cách cấu hình.

### 3.2 QueueChannel có thể lưu bền vững, nhưng phải cấu hình

`QueueChannel` có thể dùng persistent store, ví dụ `JdbcChannelMessageStore`, thay vì queue bộ nhớ. Khi đó message được lưu trong database có thể phục hồi sau restart nếu giao dịch và storage được cấu hình đúng. Tuy nhiên:

- Việc **lấy message** và **xử lý nghiệp vụ** cần ranh giới transaction rõ ràng.
- Lưu message bền vững **không tự ngăn được duplicate business effect**.
- Nếu store là database chung, throughput, lock contention, schema, serialization và sao lưu là trách nhiệm vận hành của hệ thống.
- Persistent channel vẫn là thành phần ứng dụng Spring Integration; nó không tự tạo topology, consumer group hay protocol của một broker ngoài.

## 4. Bảng đối chiếu channel semantics và broker semantics

| Câu hỏi thiết kế | Spring Integration channel | Broker ngoài |
|---|---|---|
| **Định tuyến** | `Router` và các channel nội bộ quyết định handler/nhánh. | Exchange, binding, destination, topic, subscription hoặc partition quyết định đích truyền. |
| **Phạm vi** | Mặc định bên trong một Spring `ApplicationContext`/tiến trình. | Các ứng dụng, máy chủ hoặc nhóm consumer có thể kết nối từ xa. |
| **Lưu trữ** | Phụ thuộc loại channel và `MessageStore`; nhiều channel hoàn toàn không lưu. | Phụ thuộc broker, chính sách queue/topic, loại message, replication và cấu hình durability. |
| **Nhận message** | Gọi handler trực tiếp, executor dispatch hoặc poll `QueueChannel`. | Broker delivery/listener hoặc đọc log bằng consumer. |
| **Xác nhận hoàn tất** | Không có cơ chế ACK broker chung cho mọi channel. | RabbitMQ ACK/NACK, JMS session acknowledgment/transaction, Kafka offset commit: các mô hình khác nhau. |
| **Retry/redelivery** | Advice, retry interceptor, poller transaction, error flow do ứng dụng cấu hình. | Tùy broker và client: requeue/redelivery/seek/offset hoặc retry topic; không hoàn toàn tự động. |
| **Thứ tự** | Phụ thuộc loại channel, thread, poller và số handler. | Phụ thuộc queue/consumer, partition, prefetch, redelivery và cấu hình concurrency. |
| **Fan-out** | `PublishSubscribeChannel` phát tới subscriber trong ứng dụng. | Subscription/queue hoặc consumer group độc lập cho từng nhóm nhận. |
| **Backpressure** | Capacity của queue, executor rejection, poller rate. | Queue depth/retention, consumer lag, prefetch, flow control, quotas. |
| **Theo dõi lỗi** | `ErrorMessage`, `errorChannel`, logging/Micrometer/tracing. | DLQ, broker metrics, consumer lag, unacked count, failed publishes; cần nối với tracing ứng dụng. |
| **Giao dịch** | Có thể bao quanh các bước xử lý nội bộ/tài nguyên hỗ trợ transaction. | Có transaction/session/offset/ACK theo từng broker, không đồng nghĩa transaction chung với mọi database/API. |
| **Request–reply** | Gateway có thể dùng reply channel nội bộ. | Cần reply destination, correlation, timeout, xử lý reply muộn/trùng nếu đi qua broker. |

Bảng so sánh các hợp đồng **điển hình**, không khẳng định mọi channel hay mọi broker đều có cùng cấu hình. Khi lựa chọn, hãy xác minh hành vi chính xác của adapter và phiên bản thư viện đang dùng.

## 5. Phân biệt rõ RabbitMQ, JMS và Kafka

**RabbitMQ** thường triển khai work queue hoặc publish/subscribe qua exchange và binding. Với consumer push, ứng dụng chọn cơ chế acknowledgment; nếu consumer dừng trước ACK, message có thể được giao lại theo quy tắc broker. Queue khai báo durable và message persistent là hai yêu cầu riêng; khi cần độ tin cậy đầu gửi, phải xem thêm publisher confirms cùng cấu hình broker tương ứng.

**JMS** là API/specification, còn provider đảm nhiệm thực thi. Persistent delivery mode, acknowledgment mode và transacted session tác động tới khả năng phục hồi cũng như redelivery. Không suy ra một cam kết chính xác chỉ từ việc có `Jms.messageDrivenChannelAdapter` trong flow.

**Kafka** lưu record vào partitioned log; consumer group phối hợp phân công partition và mỗi group theo dõi offset riêng. Commit offset có nghĩa là ghi nhận vị trí đọc, **không xóa** record khỏi topic. Retention policy quyết định dữ liệu còn được giữ bao lâu. Thứ tự được bảo đảm **trong một partition**, không phải tổng thể toàn bộ topic khi có nhiều partition.

| Công nghệ | Đơn vị phân phối | Khi consumer hoàn tất | Lưu ý semantics |
|---|---|---|---|
| RabbitMQ | Queue/exchange và consumer | ACK hoặc cơ chế xác nhận theo chế độ listener | NACK/requeue, prefetch, DLX/DLQ và durability cần kiểm tra cấu hình. |
| JMS | Destination (queue/topic) và subscription | Acknowledge/commit session theo mode | Hành vi redelivery và durable subscription phụ thuộc provider/cấu hình. |
| Kafka | Topic partition và consumer group | Offset commit hoặc transaction theo phạm vi hỗ trợ | Record vẫn tồn tại theo retention; có thể replay; cần tránh tác động nghiệp vụ trùng. |

Không dùng câu “Spring Integration bảo đảm exactly once” cho cả ba transport. Spring Integration phối hợp endpoint và flow, trong khi các delivery guarantees xuất phát từ tổ hợp broker, client, transaction, lưu trữ nghiệp vụ và thiết kế consumer.

## 6. Trường hợp điển hình: xử lý đơn hàng

Yêu cầu: khi đặt hàng thành công, gửi `OrderPlaced(eventId, orderId)`; một worker tạo hóa đơn. Dịch vụ bán hàng và dịch vụ hóa đơn triển khai độc lập, có thể restart bất kỳ lúc nào.

### 6.1 Chỉ nối channel nội bộ

~~~mermaid
flowchart LR
  P["Order handler"] --> D["DirectChannel"]
  D --> T["Transformer"]
  T --> H["Invoice handler"]
~~~

Cấu trúc này đơn giản, ít độ trễ và phù hợp khi cả ba bước ở **cùng ứng dụng**. Nếu `Invoice handler` ném exception trong cùng lời gọi, lỗi có thể propagate ngược về caller. Tuy nhiên toàn bộ luồng phụ thuộc vòng đời chung của tiến trình; không thể cho worker trên máy khác đăng ký trực tiếp vào `DirectChannel`.

### 6.2 Dùng QueueChannel nội bộ

~~~mermaid
flowchart LR
  P["Order handler"] --> Q[["QueueChannel"]]
  Q --> POL["Poller"]
  POL --> H["Invoice handler"]
~~~

Poller tách tốc độ producer và consumer. Cần quyết định dung lượng, cách lưu message, chính sách retry và transaction. `QueueChannel` mặc định chỉ đệm trong bộ nhớ; nếu dùng `JdbcChannelMessageStore`, hành vi nhận lại khi lỗi phải được kiểm thử với transaction manager thực tế.

### 6.3 Dùng broker giữa hai ứng dụng

~~~mermaid
flowchart LR
  subgraph S["Order service"]
    A["Business transaction"] --> O["Outbox / event publisher"]
    O --> SA["Outbound adapter"]
  end
  SA --> B[("Broker queue / topic")]
  B --> IA["Inbound adapter"]
  subgraph I["Invoice service"]
    IA --> F["Filter / Transformer"]
    F --> H["Idempotent invoice handler"]
    H --> D[("Invoice DB")]
  end
~~~

Với thiết kế này, broker là điểm tách **triển khai, vòng đời và tốc độ** giữa hai dịch vụ. Producer cần biết khi nào publish được xác nhận. Consumer cần quyết định khi nào ACK/commit sau nghiệp vụ. Nếu dữ liệu đơn hàng và message được ghi vào hai hệ thống khác nhau, transactional outbox thường giúp giảm “ghi DB thành công nhưng không phát được message”.

Trong thực tế, các adapter Spring Integration kết nối broker có thể dùng channel ở cả trước lẫn sau adapter; adapter không biến channel cục bộ thành broker.

## 7. Ví dụ Java DSL: queue nội bộ không tương đương broker

Ví dụ sau minh họa queue trong ứng dụng. Các import được lược bỏ; cần Spring Integration Java DSL và Spring configuration phù hợp.

~~~java
@Configuration
@EnableIntegration
class LocalOrderFlow {

    @Bean
    MessageChannel orderBuffer() {
        // Giới hạn 100 message chờ; đây là queue trong bộ nhớ.
        return new QueueChannel(100);
    }

    @Bean
    IntegrationFlow invoiceFlow(InvoiceService invoiceService) {
        return IntegrationFlow
                .from("orderBuffer", endpoint -> endpoint.poller(
                        Pollers.fixedDelay(250).maxMessagesPerPoll(10)))
                .handle(OrderPlaced.class, (event, headers) -> {
                    invoiceService.applyOnce(event.eventId(), event.orderId());
                    return null; // Kết thúc flow một chiều.
                })
                .get();
    }
}

record OrderPlaced(String eventId, String orderId) {}

interface InvoiceService {
    void applyOnce(String eventId, String orderId);
}
~~~

Với cấu hình này:

- `orderBuffer().send(message)` tương ứng thao tác **enqueue vào bộ nhớ**; không có publisher confirm từ broker.
- `invoiceFlow` sử dụng poller để lấy message; nếu handler lỗi sau khi đã dequeue, queue bộ nhớ không tự có cơ chế ACK/rollback/redelivery của RabbitMQ.
- Có thể thêm retry advice và error channel, nhưng cần mô tả rõ liệu exception có được ném về poller và message có còn tồn tại hay không.
- Dung lượng `100` là giới hạn queue nội bộ; cần hiểu hành vi chờ hoặc thất bại của `send(message, timeout)` khi đầy.

Nếu thay queue bằng persistent `JdbcChannelMessageStore` và cấu hình transaction, hệ thống có cơ chế lưu message qua restart. Điều này **vẫn không tạo ra** consumer group ngoài tiến trình hay publisher confirm của RabbitMQ.

### 7.1 Ví dụ ranh giới broker qua AMQP adapter

Một hướng kết nối RabbitMQ trong Spring Integration là dùng inbound adapter, sau đó tiếp tục flow bằng các endpoint trong ứng dụng:

~~~java
@Configuration
@EnableIntegration
class BrokerInboundFlow {

    @Bean
    IntegrationFlow invoicesFromRabbit(
            org.springframework.amqp.rabbit.connection.ConnectionFactory connectionFactory,
            InvoiceService invoiceService) {

        return IntegrationFlow
                .from(Amqp.inboundAdapter(connectionFactory, "orders.invoice"))
                .handle(OrderPlaced.class, (event, headers) -> {
                    invoiceService.applyOnce(event.eventId(), event.orderId());
                    return null;
                })
                .get();
    }
}
~~~

Đoạn code **minh họa vị trí nối adapter và handler**; để chạy thực tế phải khai báo queue trên RabbitMQ, cấu hình message converter để chuyển payload thành `OrderPlaced`, listener container, chế độ ACK, chính sách lỗi/requeue và transaction hoặc idempotency thích hợp. Đặc biệt, độ tin cậy không thể được suy ra chỉ từ lời gọi `Amqp.inboundAdapter(...)`.

Đối với Kafka và JMS, thay adapter theo transport; vẫn giữ được các EIP component phía sau adapter, nhưng semantics xác nhận/retention/redelivery phải xét riêng.

## 8. Một bảng sự cố để tránh nhầm ACK và `send()`

| Thời điểm sự cố | Với channel bộ nhớ | Với broker và cơ chế ACK/offset phù hợp |
|---|---|---|
| Producer chết trước khi gửi | Không có message để xử lý. | Cũng không có message nếu chưa publish; cần retry/outbox ở producer. |
| Producer nhận `send() == true` rồi ứng dụng chết | Có thể mất message nếu chỉ ở memory queue. | Nếu đã có xác nhận bền vững hợp lệ từ broker, message có khả năng phục hồi theo cam kết của broker. |
| Consumer lấy message rồi chết trước khi commit nghiệp vụ | Queue bộ nhớ có thể đã loại message; không tự redeliver. | Broker có thể giao lại hoặc giữ vị trí chưa commit, tùy protocol/config. |
| Nghiệp vụ đã commit nhưng consumer chết trước ACK/offset commit | Không có giao thức ACK broker chung. | Có thể nhận lại cùng sự kiện; cần idempotency. |
| Handler throw exception | `DirectChannel` có thể propagate lỗi đồng bộ; async flow cần kênh lỗi phù hợp. | Listener/container quyết định rollback/requeue/seek/DLQ; cấu hình error flow có thể ảnh hưởng ACK. |
| Cần replay lịch sử | Queue memory không cung cấp chức năng này. | Kafka thường cho phép đọc lại trong thời hạn retention; queue broker cần DLQ/archive hoặc lưu bản sao phù hợp. |

**Nguyên tắc thiết kế:** message tồn tại, message được giao, message được xác nhận và nghiệp vụ được commit là **những sự kiện khác nhau**. Mọi sơ đồ tích hợp nên thể hiện ít nhất ranh giới lưu trữ và ranh giới xác nhận của luồng quan trọng.

## 9. At-most-once, at-least-once và exactly-once effect

- **At-most-once:** có thể mất message khi lỗi, nhưng hệ thống không cố giao lại trong phạm vi bảo đảm; phù hợp các tín hiệu không quan trọng.
- **At-least-once:** có cơ chế giao lại khi chưa được xác nhận; có thể xử lý **hơn một lần**, nên consumer phải chịu duplicate.
- **Exactly-once effect:** trạng thái nghiệp vụ cuối cùng tương đương xử lý một lần. Cần xác định phạm vi, bởi broker không thể tự tạo exactly-once cho một REST API hoặc database bên ngoài chỉ bằng tùy chọn ACK.

Ví dụ consumer tạo hóa đơn. Nếu ghi DB thành công, nhưng process chết trước ACK, broker có thể giao lại `eventId=evt-246`. Khi đó handler cần kiểm tra `eventId` trong một bảng deduplication có unique key và đặt **việc đánh dấu đã xử lý cùng transaction** với cập nhật hóa đơn.

~~~sql
-- Lược đồ minh họa PostgreSQL:
-- processed_event(event_id PRIMARY KEY, processed_at, ...)
BEGIN;

INSERT INTO processed_event(event_id, processed_at)
VALUES (:eventId, CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;

-- Chỉ tạo/cập nhật hóa đơn nếu INSERT phía trên
-- thực sự thêm được một dòng (kiểm tra row count ở ứng dụng).
-- INSERT INTO invoices(...) VALUES (...);

COMMIT;
~~~

Nếu gọi email, thanh toán hoặc HTTP API ngoài transaction của database, cần idempotency key ở hệ thống đích hoặc một outbox riêng để quản lý side effect. Không gộp “deduplicate message nội bộ” với “chống tác động nghiệp vụ trùng” thành một khái niệm.

## 10. Router, Filter, Transformer và Splitter/Aggregator có thay đổi semantics broker không?

Các EIP component giúp tổ chức xử lý trong Spring Integration nhưng không thay đổi hợp đồng transport chỉ bằng cách xuất hiện trong flow.

### Router và Filter

`Router` chọn nhánh theo header, payload hoặc biểu thức; `Filter` quyết định cho phép/bỏ message theo tiêu chí ứng dụng. Nếu broker đã giao message và handler xử lý xong bằng cách bỏ qua theo rule hợp lệ, hệ thống có thể ACK message theo chính sách. Nếu filter từ chối do lỗi dữ liệu cần điều tra, nên định tuyến sang quarantine hoặc error flow và xác định rõ có ACK hay requeue.

### Transformer

`Transformer` thay payload hoặc header phục vụ xử lý; bản thân nó không ghi message vào broker. Khi chuyển đổi làm mất `eventId`, `correlationId` hay trace context, hệ thống có thể khó deduplicate và truy vết. Chủ động bảo tồn các định danh có ý nghĩa nghiệp vụ.

### Splitter và Aggregator

`Splitter` tạo nhiều message con; `Aggregator` nhóm message theo correlation, release strategy và timeout. Việc broker đã lưu **một** message gốc không có nghĩa broker tự quản lý **toàn bộ trạng thái nhóm** bên trong ứng dụng. Với long-running aggregation qua restart, cần xem xét persistent `MessageGroupStore`, correlation strategy, release strategy, thời gian chờ và duplicate child message.

### Gateway và request–reply

`Messaging Gateway` giúp mã nghiệp vụ gọi API quen thuộc để đi vào flow và có thể đợi reply. Với channel nội bộ, `replyChannel` có thể là đối tượng gắn với một tiến trình. Với request–reply qua broker, cần reply destination phù hợp, `correlationId`, timeout và xử lý reply muộn hoặc trùng; không giả định reply nội bộ sẽ còn hợp lệ sau restart.

## 11. Error channel, retry advice và broker redelivery là các cơ chế riêng

Ba lớp cần phân biệt:

1. **Retry trong handler:** interceptor/advice hoặc logic ứng dụng gọi lại thao tác ngay trong cùng lần nhận. Cần backoff và giới hạn số lần thử.
2. **Broker redelivery:** khi consumer chưa ACK, rollback, kết nối mất hoặc offset chưa commit, broker/client có thể giao lại record/message theo cơ chế riêng.
3. **Error channel:** Spring Integration đưa `ErrorMessage` vào đường xử lý lỗi để ghi log, thông báo hoặc định tuyến; không tự tạo cam kết redelivery của transport.

Một error handler **bắt rồi nuốt exception** có thể khiến listener coi lần xử lý là thành công và ACK/commit, tùy cách cấu hình. Nếu muốn rollback hoặc đưa vào DLQ, phải cấu hình mối quan hệ giữa lỗi của flow, advice, listener container và ACK/transaction.

~~~mermaid
flowchart TD
  IN["Broker delivers"] --> HD{"Handler result"}
  HD -->|Success| ACK["ACK / commit theo transport"]
  HD -->|Transient failure| RET["Retry with backoff"]
  RET --> HD
  HD -->|Retries exhausted| POLICY{"Error policy"}
  POLICY -->|Reject / DLQ| DLQ["Dead-letter / quarantine"]
  POLICY -->|Rollback / requeue| BACK["Broker redelivery"]
  POLICY -->|Handler swallows error| ACK
~~~

Sơ đồ mô tả các lựa chọn chính sách, không phải mặc định bắt buộc của mọi adapter. Với Kafka, “rollback/requeue” thường tương ứng với cách quản lý vị trí đọc, seek/retry topic, thay vì NACK một queue item.

## 12. Ordering, fan-out và consumer group

Thứ tự xử lý là một ví dụ khác dễ nhầm giữa hai tầng:

- Trong `DirectChannel` đồng bộ, một lời gọi `send()` đi qua handler trên thread hiện tại; nếu nhiều producer gửi đồng thời, vẫn phải xét concurrency.
- Với `ExecutorChannel`, `QueueChannel` có nhiều poller hoặc nhiều worker, **thứ tự hoàn thành** có thể khác thứ tự gửi.
- RabbitMQ dùng một queue với nhiều consumer để chia việc, có thể có prefetch, unacked, redelivery ảnh hưởng thứ tự quan sát.
- Kafka giữ thứ tự record trong mỗi partition; nhiều partition không có một thứ tự toàn cục. Chọn partition key như `orderId` khi cần tuần tự theo đơn hàng.
- Một `PublishSubscribeChannel` thông thường phát đến subscriber của ứng dụng hiện tại. Trên broker, các group/subscription khác nhau nhận các luồng tiêu thụ độc lập theo quy tắc transport; các consumer **trong cùng group/work queue** thường chia nhau công việc.

Muốn vừa fan-out đến `Billing`, `Shipping`, `Analytics`, vừa xử lý mỗi sự kiện một lần trong mỗi nhóm, hãy khai báo topology broker/subscription và khóa correlation phù hợp; không đặt ba worker cạnh tranh chung một work queue rồi kỳ vọng cả ba đều thấy mọi sự kiện.

## 13. Backpressure và monitoring ở từng tầng

Tốc độ publish nhanh hơn tốc độ xử lý sẽ dẫn đến backlog. Tầng channel và broker cần những chỉ số khác nhau.

| Vị trí | Chỉ số nên theo dõi | Quyết định vận hành |
|---|---|---|
| `QueueChannel` | Queue depth, poll latency, tuổi message, exception từ handler. | Điều chỉnh capacity, poller, transaction và tốc độ xử lý. |
| `ExecutorChannel` | Active threads, queued tasks, rejected tasks, handler latency. | Tăng giới hạn hoặc xử lý sự từ chối có kiểm soát; tránh executor vô hạn. |
| RabbitMQ/JMS | Ready/in-flight/unacked, queue depth, consumer count, redelivery và DLQ. | Đánh giá prefetch, retry, broker capacity, quy tắc ACK. |
| Kafka | Consumer lag theo group/partition, processing latency, rebalance, offset commit lỗi. | Điều chỉnh partition, worker, batch, retention và error handling. |
| Business DB/API | Idempotency hit, số lần commit, giao dịch lỗi, tác vụ phát sinh trùng. | Xác nhận **hiệu quả nghiệp vụ**, ngoài việc message được vận chuyển. |

Gắn `eventId`, business key (`orderId`), `correlationId` và trace context xuyên qua inbound/outbound adapter. Đừng chỉ dựa vào broker message ID để nhận diện cùng một **sự kiện nghiệp vụ** được publish lại sau lỗi. Đặt cảnh báo cho **tuổi message lớn nhất/consumer lag và lỗi xử lý liên tục**, ngoài chiều dài queue.

## 14. Chọn kiến trúc theo yêu cầu

| Nhu cầu | Lựa chọn ban đầu | Điều cần kiểm tra thêm |
|---|---|---|
| Các bước xử lý rất nhanh, cùng thread/process. | `DirectChannel`. | Exception propagation, thời gian block caller, transaction nội bộ. |
| Xử lý nặng cần tách thread, không cần giữ message qua restart. | `ExecutorChannel`. | Executor capacity/rejection, async error flow. |
| Cần đệm giữa các bước trong một ứng dụng. | `QueueChannel` + poller. | Capacity, mất dữ liệu khi restart, dequeue semantics. |
| Cần lưu message trong ứng dụng qua restart. | `QueueChannel` + persistent store. | Schema, serializer, transaction/rollback, lock contention. |
| Hai dịch vụ độc lập cần work queue và ACK/redelivery. | RabbitMQ hoặc JMS provider + SI adapter. | Durability, publish confirms, listener ACK, retry/DLQ. |
| Cần stream giữ lịch sử, nhiều nhóm đọc và replay. | Kafka + SI adapter. | Retention, partition key, consumer lag, offset semantics. |
| Một sự kiện có nhiều nhánh xử lý nghiệp vụ độc lập. | Broker fan-out/subscription hoặc topology phù hợp. | Mỗi nhóm phải có subscription/queue và idempotency riêng. |

Không có giải pháp chung cho mọi trường hợp. Hãy bắt đầu từ **failure model**: chấp nhận mất message nào, cần phục hồi sau bao lâu, duplicate gây hậu quả gì, thứ tự ở mức nào và một consumer cần tách khỏi producer đến đâu.

## 15. Bài thực hành: kiểm chứng bằng sự cố

Tạo sự kiện `OrderPlaced(eventId="evt-246", orderId="order-42")` và thử hai phương án: `QueueChannel` bộ nhớ, sau đó adapter đi qua broker. Ghi lại hành vi và trạng thái DB với các kịch bản:

1. **Không có consumer:** phát 100 sự kiện, đo backlog và tác động của giới hạn buffer.
2. **Restart ứng dụng:** enqueue rồi restart trước khi xử lý; xác nhận khác biệt giữa memory queue, persistent store và broker.
3. **Lỗi sau dequeue:** cho handler ném exception; kiểm tra message còn được xử lý lại hay đã mất theo cấu hình hiện tại.
4. **Lỗi sau business commit:** cố tình giao lại cùng `eventId`; xác nhận hóa đơn chỉ được tạo một lần.
5. **Hai consumer cạnh tranh:** phát nhiều message cùng `orderId`; đo thứ tự nhận, thứ tự hoàn thành và chặn cập nhật ngoài thứ tự.
6. **Poison message:** phát payload không hợp lệ; quan sát retry, error channel, DLQ và cảnh báo.
7. **Publisher disconnect:** ngắt broker giữa lúc publish; phân biệt lời gọi outbound thành công với xác nhận từ broker theo cấu hình.
8. **Replay hoặc late reply:** replay record Kafka nếu có, hoặc gửi reply trễ tới gateway; kiểm tra deduplication, correlation và timeout.

Mỗi test cần trả lời: **message có tồn tại không, ai đã nhận, lúc nào coi là hoàn tất, có thể nhận lại không, kết quả nghiệp vụ có lặp không?** Không chỉ kiểm tra số lần `send()` trả về `true`.

## 16. Checklist trước production

- [ ] Phân biệt rõ channel trong ứng dụng, adapter transport và queue/topic của broker trong sơ đồ triển khai.
- [ ] Ghi lại hợp đồng ACK/offset/transaction ở từng inbound adapter và producer confirm ở outbound adapter nếu cần.
- [ ] Xác định nơi message tồn tại sau crash và trách nhiệm recovery của từng thành phần.
- [ ] Cấu hình retry/backoff hữu hạn, error flow, DLQ/quarantine và quy trình replay.
- [ ] Dùng `eventId` ổn định, idempotency và correlation/trace context end-to-end.
- [ ] Kiểm thử delivery duplicate, crash trước/sau commit, restart và order-sensitive concurrency.
- [ ] Giám sát channel backlog, broker queue/consumer lag, idempotency và kết quả nghiệp vụ.
- [ ] Đặt giới hạn capacity, TTL/retention và chính sách khi đầy để tránh nghẽn lan truyền.
- [ ] Đọc hành vi cụ thể của provider, listener container, converter và phiên bản Spring Integration đang triển khai.

**Ghi nhớ:** Spring Integration channel diễn đạt **cách các thành phần trong luồng trao đổi message**; broker semantics diễn đạt **cách hạ tầng vận chuyển, lưu, phân phối và xác nhận message**. Các adapter nối hai tầng, nhưng độ bền dữ liệu, redelivery và độ chính xác của tác động nghiệp vụ phải được xác định, cấu hình và kiểm thử tại đúng ranh giới của chúng.
