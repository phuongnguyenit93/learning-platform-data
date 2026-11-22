# Phân biệt độ trễ broker, hàng đợi và xử lý nghiệp vụ

> Phạm vi: đo đúng từng chặng trong vòng đời message, phân biệt thời gian gửi tới broker, thời gian message chờ trong queue và thời gian consumer xử lý nghiệp vụ; áp dụng với Spring Framework, Spring Integration, JMS, Spring AMQP và kiến trúc RSocket.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Xác định ranh giới bắt đầu và kết thúc của từng loại latency.
- Phân biệt broker publish latency, broker queue residence, local queue wait, consumer processing và end-to-end latency.
- Đọc queue depth, oldest message age, consumer lag, throughput và in-flight messages cùng nhau.
- Dùng Micrometer Observation, metrics và distributed tracing trong Spring.
- Hiểu các observation có sẵn của Spring JMS, Spring AMQP và Spring Integration.
- Tự instrument phần xử lý nghiệp vụ mà không đo nhầm cả thời gian chờ queue vào business duration.
- Khoanh vùng nghẽn bằng p50/p95/p99, tốc độ vào/ra và trace theo message.

## 2. Một message đi qua những chặng nào?

Trong một hệ thống messaging bất đồng bộ, message thường đi qua các bước:

1. Producer tạo message và gọi API gửi.
2. Client library serialize message và gửi tới broker.
3. Broker xác nhận hoặc từ chối publish theo semantics của protocol và cấu hình.
4. Broker định tuyến và lưu message trong queue hoặc log.
5. Consumer nhận message khi có capacity và điều kiện delivery phù hợp.
6. Message có thể nằm trong queue nội bộ hoặc executor của ứng dụng trước khi handler bắt đầu.
7. Handler chạy logic nghiệp vụ, có thể gọi database hoặc service khác.
8. Consumer ACK/commit hoặc trả kết quả; broker cập nhật trạng thái delivery.

Mỗi bước có thể có độ trễ riêng. Một biểu đồ chỉ có `message duration = 2 seconds` không đủ để biết hai giây đó nằm ở producer, broker, queue, consumer hay database.

### 2.1. Các loại thời gian cần tách

| Chỉ số | Điểm bắt đầu | Điểm kết thúc | Nó cho biết điều gì? |
| --- | --- | --- | --- |
| Producer send duration | Ứng dụng gọi send/publish | API gửi hoàn tất hoặc publisher confirm nhận được | Client và đường publish tới broker mất bao lâu theo semantics của API |
| Broker queue residence | Broker nhận/enqueue message | Broker giao message cho consumer | Message ở lại broker bao lâu trước khi được giao |
| Local queue wait | Ứng dụng enqueue vào channel/executor | Worker lấy message khỏi queue | Thời gian chờ trong queue nội bộ của service |
| Consumer delivery-to-handler delay | Client nhận delivery | Handler bắt đầu xử lý | Thời gian dispatch, decode, scheduling và các bước trước handler |
| Business processing duration | Handler bắt đầu logic nghiệp vụ | Logic nghiệp vụ hoàn tất hoặc thất bại | Thời gian xử lý thực tế trong ứng dụng |
| ACK/commit duration | Handler hoàn tất | ACK/commit được gửi và hoàn tất theo API | Thời gian chốt delivery sau xử lý |
| End-to-end age | Producer tạo message | Kết quả nghiệp vụ hoàn tất | Tuổi tổng thể của message hoặc command |

Tên gọi giữa các broker và thư viện có thể khác nhau. Hãy ghi rõ ranh giới trong dashboard và tài liệu metric. `send()` hoàn tất không nhất thiết có nghĩa message đã được consumer xử lý; publisher confirm, transaction commit và consumer ACK là các sự kiện khác nhau.

### 2.2. Công thức phân rã

Với một luồng tuần tự đơn giản, có thể mô hình hóa:

```text
End-to-end latency
  = producer preparation and publish
  + broker residence and delivery
  + consumer-side queue/scheduling
  + business processing
  + acknowledgement or result propagation
```

Đây là mô hình tư duy, không phải công thức luôn cộng được từ các histogram. Retry, batching, prefetch, concurrency và các thao tác song song có thể làm các khoảng thời gian chồng lấn. Muốn phân rã chính xác cần đo các span hoặc timestamp tại từng ranh giới.

## 3. Phân biệt broker latency và queue wait

### 3.1. Producer-to-broker publish duration

Đây là thời gian producer gửi message tới broker theo semantics của client API. Khoảng thời gian có thể bao gồm serialization, network, broker nhận và xử lý publish, routing, ghi dữ liệu hoặc chờ publisher confirm tùy cấu hình.

Một publish timer không tự động đo thời gian message nằm trong queue. Nếu producer API chỉ xác nhận đã ghi vào socket hoặc buffer client, timer đó còn chưa chắc chứng minh broker đã nhận message. Cần xác định rõ ứng dụng đang đo thời điểm API return, broker ACK, publisher confirm hay transaction commit.

### 3.2. Broker queue residence / queue wait

Queue residence là thời gian từ lúc broker đưa message vào queue tới lúc broker giao message cho consumer. Nó tăng khi consumer không đủ capacity, consumer bị dừng, prefetch/in-flight limit chạm ngưỡng, routing đưa message vào queue không có consumer hoặc tốc độ publish lớn hơn tốc độ xử lý.

Để đo riêng queue residence, cần timestamp enqueue do broker cung cấp hoặc một cơ chế quan sát broker tương đương. Timestamp do producer tự ghi vào message chỉ đo được khoảng producer-created-to-consumer-received; khoảng đó còn bao gồm publish network và delivery network, nên không thể gọi chính xác là queue wait.

Nếu broker không cung cấp enqueue timestamp đủ tin cậy, theo dõi các chỉ số gần đúng như oldest ready message age, queue depth, consumer lag và tốc độ publish/deliver. Những chỉ số này giúp chẩn đoán backlog nhưng không thay thế một phép đo latency trực tiếp.

### 3.3. Local queue wait

Nhiều ứng dụng có queue thứ hai sau khi message đã được broker giao: `QueueChannel`, executor, worker pool, scheduler hoặc hàng đợi nội bộ của pipeline. Đây là thời gian message chờ trong process.

Ví dụ broker giao message nhanh nhưng listener đưa công việc vào một executor có queue dài. Broker queue có thể gần bằng 0 trong khi local queue wait tăng mạnh. Nếu chỉ nhìn dashboard broker, hệ thống có vẻ khỏe dù người dùng vẫn chờ lâu.

Với queue nội bộ trong cùng process, có thể ghi `System.nanoTime()` lúc enqueue và lúc dequeue để tính duration. Không dùng `System.currentTimeMillis()` để đo duration cục bộ vì đồng hồ wall-clock có thể bị điều chỉnh.

### 3.4. Business processing duration

Business duration bắt đầu khi handler/service thực sự bắt đầu xử lý message và kết thúc khi công việc nghiệp vụ hoàn tất hoặc thất bại. Tùy định nghĩa, cần quyết định có tính database commit, gọi API downstream và ghi kết quả hay không.

Nên đo riêng các dependency quan trọng như database query, HTTP/RPC downstream, lock wait và transaction commit. Khi business duration cao, trace con sẽ giúp xác định thời gian nằm ở code CPU, connection pool, database hay dịch vụ khác.

## 4. Queue depth, queue age và throughput

Không nên dùng queue depth đơn lẻ làm thước đo latency. Một queue có 10.000 message nhưng consumer xử lý 20.000 message/giây có thể hết nhanh; queue có 10 message nhưng message cũ nhất đã chờ 20 phút lại là dấu hiệu nghiêm trọng.

Theo dõi tối thiểu:

| Chỉ số | Cách hiểu | Khi tăng bất thường |
| --- | --- | --- |
| Queue depth / messages ready | Số message đang chờ delivery | Consumer chậm, không đủ consumer, burst traffic hoặc routing sai |
| Oldest message age | Tuổi của message chờ lâu nhất | Có message bị đói, backlog không được xử lý hoặc consumer ngừng |
| In-flight / unacked | Message đã giao nhưng chưa ACK/commit | Handler chậm, prefetch lớn, consumer bị treo hoặc ACK bị trì hoãn |
| Publish rate | Message được gửi mỗi giây | Đầu vào tăng hoặc producer retry |
| Delivery/consume rate | Message được giao hoặc consumer nhận mỗi giây | Năng lực consumer và broker dispatch |
| Completion rate | Message xử lý nghiệp vụ thành công mỗi giây | Năng lực xử lý thực tế |
| Redelivery/retry rate | Message được giao lại hoặc retry | Lỗi xử lý, timeout, ACK sai hoặc poison message |
| Dead-letter rate | Message chuyển sang DLQ | Message không xử lý được hoặc policy retry đã hết |
| Queue capacity remaining | Dung lượng queue còn lại | Gần 0 là nguy cơ backpressure hoặc reject/block producer |

### 4.1. Arrival rate và service rate

Gọi `λ` là tốc độ message đến queue và `μ` là tốc độ consumer xử lý hoàn tất. Nếu `λ` liên tục lớn hơn `μ`, backlog sẽ tăng. Tăng số consumer chỉ có ích nếu bottleneck nằm ở năng lực consumer và dependency phía sau còn capacity.

Định luật Little cho một hệ thống ổn định:

```text
L = λ × W
```

Trong đó `L` là số phần tử trung bình trong hệ thống, `λ` là throughput trung bình và `W` là thời gian trung bình một phần tử ở trong hệ thống. Có thể dùng để kiểm tra tính hợp lý của số liệu queue/latency trong trạng thái ổn định. Không áp dụng máy móc khi backlog đang tăng, workload burst mạnh hoặc các số liệu lấy từ những ranh giới khác nhau.

### 4.2. Đọc các chỉ số cùng nhau

- Queue depth tăng, oldest age tăng, consumer completion rate giảm: nghi ngờ consumer hoặc dependency downstream bị chậm.
- Queue depth tăng nhưng handler duration ổn định: kiểm tra số consumer, prefetch, scheduler, consumer capacity và thời điểm message được giao.
- Broker queue thấp nhưng local queue depth tăng: bottleneck nằm trong process sau khi nhận message.
- Publish duration tăng nhưng queue vẫn thấp: kiểm tra network, broker overload, disk I/O, confirm latency hoặc routing.
- Handler duration tăng cùng database span: kiểm tra query, lock, connection pool và transaction.
- Unacked tăng mạnh nhưng queue ready giảm: message đã được giao nhưng consumer chưa ACK; xem handler hoặc ACK path.
- Redelivery và DLQ tăng: điều tra lỗi xử lý, poison message, retry policy và idempotency.

## 5. Micrometer Observation trong Spring

### 5.1. Observation, metric và trace

Spring Boot sử dụng Micrometer Observation để kết nối metrics và tracing. Một `Observation` mô tả một hoạt động có ranh giới bắt đầu/kết thúc và metadata. Các `ObservationHandler` có thể chuyển nó thành timer, counter hoặc span tùy cấu hình.

Ba pillar bổ trợ nhau:

- **Metrics:** cho biết xu hướng, phân vị, throughput, error rate và backlog trên toàn hệ thống.
- **Traces:** cho thấy một message cụ thể đi qua producer, broker, consumer và dependency nào.
- **Logs:** cung cấp chi tiết sự kiện và lỗi; nên có trace id/message id để tìm cùng một luồng.

Spring Boot tự cấu hình Observation infrastructure khi có các dependency observability phù hợp. Có thể inject `ObservationRegistry` để instrument phần nghiệp vụ riêng.

### 5.2. Instrument phần xử lý nghiệp vụ

Ví dụ đo một đoạn xử lý đồng bộ:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class OrderProcessor {

    private final ObservationRegistry registry;

    OrderProcessor(ObservationRegistry registry) {
        this.registry = registry;
    }

    OrderResult process(OrderMessage message) {
        return Observation.createNotStarted(
                        "orders.business.process", registry)
                .lowCardinalityKeyValue("messaging.destination.name", "orders")
                .lowCardinalityKeyValue("operation", "process")
                .observe(() -> performBusinessWork(message));
    }

    private OrderResult performBusinessWork(OrderMessage message) {
        // Validate, update domain state and commit the business operation.
        return new OrderResult(message.orderId(), "processed");
    }
}
```

Observation bắt đầu ngay trước `performBusinessWork` và kết thúc khi phương thức đó return hoặc ném exception. Nếu handler có cả decode, queue wait, ACK và business logic, đặt Observation ở đúng service boundary để timer chỉ đo phần cần đo.

Với reactive method trả `Mono` hoặc `Flux`, không dùng `observe(() -> publisher)` một cách máy móc: supplier có thể return publisher ngay lập tức trong khi công việc thật chỉ chạy khi subscribe. Hãy dùng instrumentation tương thích Reactor/Micrometer Observation để giữ context và kết thúc observation khi publisher complete, error hoặc cancel. Kiểm thử rõ trường hợp cancel để timer không bị bỏ dở.

### 5.3. Cardinality của tags

Dùng low-cardinality tags cho các chiều có tập giá trị nhỏ, ổn định như operation, result, component, queue group hoặc message type. Tránh đưa `messageId`, `correlationId`, user id, order id hoặc raw exception message vào metric tags vì mỗi giá trị có thể tạo một time series mới.

Thông tin định danh duy nhất có thể phù hợp trong trace hoặc log với chính sách bảo vệ dữ liệu phù hợp. Metrics cần được giữ ở cardinality có thể kiểm soát.

## 6. Instrumentation có sẵn trong hệ sinh thái Spring

### 6.1. Spring Framework và JMS

Spring Framework sử dụng Jakarta JMS instrumentation của Micrometer khi dependency `io.micrometer:micrometer-jakarta9` có trên classpath. Các observation chính gồm:

| Observation | Đo khoảng nào? |
| --- | --- |
| `jms.message.publish` | Thời gian gửi JMS message tới destination/broker, thường qua `JmsTemplate` |
| `jms.message.process` | Thời gian ứng dụng xử lý message đã được consumer nhận, thường qua `MessageListener` hoặc `@JmsListener` |

Spring Framework hiện không tạo observation `jms.message.receive` cho thời gian chờ nhận message. Vì vậy, `jms.message.process` không đo thời gian message nằm trong broker queue. Muốn đo queue wait, cần broker metrics hoặc timestamp enqueue/delivery có ranh giới rõ.

Các observation này cũng có thể mang correlation id, destination name và message id vào trace theo convention. Những giá trị định danh cao cardinality nên ở trace, không nên biến thành metric labels.

### 6.2. Spring AMQP và RabbitMQ

Spring AMQP hỗ trợ Micrometer Observation cho `RabbitTemplate` và listener containers. Bật `observationEnabled` trên template và container hoặc container factory phù hợp; với annotated listener, cấu hình ở factory. Khi Observation được bật, các timer Micrometer cũ được quản lý thông qua observation tương ứng để tránh ghi hai lần cùng một hoạt động.

Các observation phổ biến:

- `spring.rabbit.template`: hoạt động gửi qua `RabbitTemplate`.
- `spring.rabbit.listener`: xử lý message của Rabbit listener.
- `spring.rabbit.stream.template` và `spring.rabbit.stream.listener`: các hoạt động tương ứng với Rabbit Stream API.

Listener observation có thông tin queue và listener id; template observation có thông tin exchange, routing key và template name theo convention. Những observation này đo thời gian ở client/template hoặc listener boundary. Chúng không thay thế metric nội bộ của RabbitMQ về queue depth, ready/unacked, oldest message age, consumer capacity hoặc publisher confirm.

### 6.3. Spring Integration

Spring Integration cung cấp metric cho channel, handler và source. Một số metric legacy/standard gồm:

| Metric | Ý nghĩa |
| --- | --- |
| `spring.integration.send` với `type=channel` | Thời gian send qua message channel |
| `spring.integration.send` với `type=handler` | Thời gian xử lý tại message handler |
| `spring.integration.receive` | Số lần nhận message ở pollable channel hoặc source |
| `spring.integration.channel.queue.size` | Số message đang nằm trong `QueueChannel` |
| `spring.integration.channel.queue.remaining.capacity` | Dung lượng còn lại của `QueueChannel` |

Từ Spring Integration 6.0, Observation có thể cung cấp metrics và tracing cho producer, handler và gateway. Cần có `ObservationRegistry` và bật `@EnableIntegrationManagement`; `observationPatterns` dùng để chọn component cần instrument. Mặc định không phải mọi component đều tự động được instrument chỉ vì registry tồn tại.

Các metric queue size và remaining capacity đặc biệt hữu ích để nhận ra nghẽn trong queue nội bộ. Chúng không đo trực tiếp thời gian một message đã chờ; nếu cần local queue wait chính xác, thêm timestamp enqueue/dequeue hoặc instrumentation tại channel boundary.

## 7. Đo queue wait chính xác

### 7.1. Queue nội bộ cùng process

Với queue trong một JVM, có thể đo bằng monotonic clock:

```java
record QueuedMessage<T>(T payload, long enqueuedNanos) {}

QueuedMessage<OrderMessage> queued =
        new QueuedMessage<>(message, System.nanoTime());

// At dequeue, immediately before dispatching to the handler:
long queueWaitNanos = System.nanoTime() - queued.enqueuedNanos();
```

Đưa `queueWaitNanos` vào timer `message.queue.wait` với tags low cardinality như channel name và outcome. Không dùng message id làm tag. Khi enqueue/dequeue ở các process khác nhau, `System.nanoTime()` không thể so sánh xuyên máy; cần timestamp wall-clock đồng bộ hoặc distributed tracing.

### 7.2. Broker queue

Đối với broker, ưu tiên native metric/API của broker:

- Số message ready và unacked/in-flight.
- Tuổi message cũ nhất hoặc consumer lag.
- Publish, deliver, ACK/commit và redelivery rate.
- Consumer count, consumer capacity, prefetch và flow control.
- Disk/memory pressure, connection/channel errors và throttling.

Nếu tự gắn timestamp vào message lúc producer publish, metric `consumer_received_at - producer_created_at` là producer-to-consumer age. Nó gồm publish path, broker residence và delivery path. Chỉ gọi đó là broker queue wait khi timestamp bắt đầu thực sự tại thời điểm broker enqueue hoặc khi broker cung cấp một mốc tương đương.

Nếu producer và consumer nằm ở các máy khác nhau, đồng hồ phải được đồng bộ. Sai lệch clock có thể tạo latency âm hoặc sai phân vị. Với duration trong cùng process, ưu tiên monotonic clock; với trace phân tán, dùng tracing SDK và clock synchronization phù hợp.

### 7.3. Consumer processing và ACK

Đo hai khoảng riêng:

1. `consumer.processing`: từ khi handler bắt đầu đến khi logic xử lý hoàn tất.
2. `consumer.ack`: từ lúc handler hoàn tất đến khi ACK/commit hoàn tất theo semantics client.

Nếu handler thực hiện side effect rồi ACK thất bại, message có thể được giao lại. Khi đó processing time có thể thấp nhưng redelivery tăng. Cần thiết kế handler idempotent và đo retry/duplicate riêng.

## 8. Distributed tracing qua messaging

Một trace hữu ích có thể có cấu trúc:

```text
HTTP/API request
  └─ producer.publish
       └─ broker publish/confirm
            └─ consumer.receive
                 └─ local.queue.wait
                      └─ business.process
                           ├─ database.query
                           └─ downstream.call
                 └─ consumer.ack
```

Đây là sơ đồ span đề xuất; span cụ thể phụ thuộc thư viện và instrumentation đang dùng. Khi message qua broker, tracing context phải được inject vào message headers lúc publish và extract lúc consume để tạo trace liên kết. Spring Integration có cơ chế producer/consumer Observation cho phép propagator ghi trace context vào message headers và consumer khôi phục context.

Dùng:

- `traceId` để theo dõi toàn bộ luồng qua nhiều service.
- `spanId` để xác định từng chặng.
- `correlationId` để liên kết các message cùng nghiệp vụ hoặc request/reply.
- `messageId` để nhận diện một message cụ thể và điều tra duplicate/redelivery.

Không mặc định `correlationId` bằng `traceId`: một nghiệp vụ có thể tạo nhiều trace hoặc một trace chứa nhiều message. Cần quy định ý nghĩa từng ID.

## 9. RSocket và khái niệm broker

RSocket protocol mô tả requester và responder giao tiếp qua một connection; bản thân RSocket không yêu cầu một message broker hay queue broker ở giữa. Một service có thể triển khai gateway, router hoặc intermediary, nhưng đó là thành phần của kiến trúc ứng dụng.

Vì vậy, với RSocket thuần:

- Không gọi thời gian từ requester gửi tới responder là broker latency nếu không có broker.
- Đo request round-trip, connection/transport behavior và handler duration ở hai đầu.
- Đo local scheduler/executor queue nếu server dispatch công việc qua queue nội bộ.
- Nếu gateway chuyển tiếp tới một broker hoặc service khác, instrument từng hop và đặt span rõ ràng.

RSocket request-response latency là thời gian từ lúc client bắt đầu request tới lúc nhận response; nó bao gồm network, server dispatch, xử lý và response path. Nó không tự cho biết riêng business duration. Cần trace hoặc instrument handler để phân rã.

## 10. Dashboard và cảnh báo

Một dashboard vận hành nên có bốn khu vực:

1. **Producer/broker:** publish duration p50/p95/p99, publish failure, confirm latency, broker resource pressure.
2. **Queue:** depth/ready, oldest age, unacked, consumer lag, arrival rate và completion rate.
3. **Consumer:** handler duration p50/p95/p99, active handlers, concurrency, retry, redelivery, DLQ và ACK latency.
4. **Business outcome:** end-to-end age, success rate, timeout, business rejection và downstream dependency latency.

Ví dụ cảnh báo cần điều chỉnh theo SLO và tải thực tế:

- Oldest message age vượt ngưỡng trong nhiều cửa sổ liên tiếp.
- Queue depth tăng liên tục trong khi completion rate thấp hơn publish rate.
- Queue remaining capacity gần 0 hoặc broker bắt đầu reject/block publish.
- Consumer processing p99 vượt ngân sách latency nghiệp vụ.
- Redelivery/DLQ rate tăng bất thường.
- End-to-end latency vi phạm SLO dù publish duration vẫn bình thường.

Không cảnh báo chỉ dựa trên một điểm queue depth tuyệt đối nếu traffic có tính chu kỳ. Dùng rate-of-change, oldest age, throughput và SLO để giảm cảnh báo giả.

## 11. Ví dụ phân tích sự cố

Giả sử dashboard ghi nhận:

| Chỉ số | Bình thường | Hiện tại |
| --- | ---: | ---: |
| Publish p95 | 15 ms | 18 ms |
| Oldest queue age | 100 ms | 42 s |
| Ready messages | 120 | 48,000 |
| Handler p95 | 35 ms | 38 ms |
| Completion rate | 4,000 msg/s | 1,100 msg/s |

Handler duration gần như không đổi và publish vẫn nhanh, nhưng queue age/depth tăng mạnh và completion rate giảm. Hướng điều tra đầu tiên là consumer capacity, số consumer, prefetch, scheduling và dependency trước khi handler được gọi. Tăng thời gian xử lý nghiệp vụ không giải thích được dữ liệu này.

Ngược lại, nếu queue age thấp, queue depth ổn định nhưng handler p99 tăng từ 40 ms lên 2 s và trace cho thấy database span chiếm 1.8 s, bottleneck nằm ở database hoặc transaction. Tăng số consumer có thể làm database quá tải hơn.

Nếu publish p95 tăng mạnh, queue chưa tăng và broker resource pressure cao, điều tra broker disk/network/confirm path hoặc producer connection pool. Không điều chỉnh consumer concurrency trước khi xác định bottleneck.

## 12. Checklist instrument và vận hành

- [ ] Mỗi timer có điểm bắt đầu và kết thúc được mô tả rõ.
- [ ] Publish duration phân biệt API return, broker confirm và transaction commit.
- [ ] Broker queue residence được đo bằng mốc enqueue/delivery đáng tin hoặc broker-native metric.
- [ ] Producer timestamp không bị gọi nhầm là broker enqueue timestamp.
- [ ] Local queue wait được đo riêng với broker queue wait.
- [ ] Business processing bắt đầu tại handler/service boundary và không bao gồm thời gian chờ queue.
- [ ] ACK/commit latency và redelivery được quan sát riêng.
- [ ] Có queue depth, oldest age, ready/unacked, throughput và consumer capacity.
- [ ] Có p50/p95/p99 và error rate, không chỉ average.
- [ ] Trace context được truyền qua message headers và khôi phục ở consumer.
- [ ] Metric tags có cardinality thấp; ID duy nhất chỉ nằm trong trace/log khi cần.
- [ ] Reactive observation kết thúc khi publisher complete/error/cancel, không phải lúc tạo publisher.
- [ ] RSocket trực tiếp không bị gán nhãn broker latency khi không có broker.
- [ ] Dashboard và alert gắn với SLO, backlog age và tốc độ xử lý.

## 13. Tài liệu tham khảo

- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Micrometer Observation, metrics, traces và context propagation.
- [Spring Framework — Observability Support](https://www.springframework.org/spring/reference/integration/observability.html): JMS publish/process observations và cách Spring tích hợp Micrometer.
- [Spring Integration — Metrics and Management](https://www.springframework.org/spring-integration/reference/metrics.html): send/handler timers, QueueChannel size/capacity gauges và producer/consumer observations.
- [Spring Integration — QueueChannel](https://springframework.org/spring-integration/reference/7.2/channel/implementations.html): semantics của queue nội bộ, capacity và hành vi send/receive.
- [Spring AMQP — Micrometer Observation](https://docs.spring.io/spring-amqp/reference/appendix/micrometer.html): RabbitTemplate/listener observations và metric/span conventions.
- [Spring AMQP — Enabling Micrometer Observation](https://docs.spring.io/spring-amqp/reference/4.2/amqp/receiving-messages/micrometer-observation.html): bật observation trên template và listener container.

Tên metric và hành vi instrumentation có thể thay đổi theo phiên bản Spring Framework, Spring Integration, Spring AMQP, Micrometer và broker client. Đối chiếu tài liệu của đúng phiên bản dependency đang chạy trước khi dùng tên metric trong dashboard hoặc alert.
