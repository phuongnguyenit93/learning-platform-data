# Độ trễ publish

## Độ trễ publish là gì?

Độ trễ publish (*publish latency*) là khoảng thời gian từ lúc ứng dụng bắt đầu công bố một event đến lúc event đạt được mốc gửi thành công đã định nghĩa. Với event được externalize qua Kafka hoặc RabbitMQ, mốc kết thúc thường là lúc producer nhận được xác nhận từ broker theo cấu hình gửi. Với application event chỉ chạy nội bộ, mốc kết thúc có thể là lúc listener đồng bộ hoàn tất hoặc lúc publication được ghi nhận hoàn tất theo cơ chế của ứng dụng.

Cần xác định rõ đang đo loại độ trễ nào. Một lời gọi `ApplicationEventPublisher.publishEvent(...)` hoàn tất không nhất thiết có nghĩa message đã được broker lưu bền vững. Tương tự, broker xác nhận đã nhận message không có nghĩa consumer đã xử lý xong nghiệp vụ.

Ví dụ, Orders xác nhận đơn hàng rồi externalize `OrderConfirmed`:

~~~mermaid
sequenceDiagram
    participant C as Command
    participant O as Orders module
    participant R as Event Publication Registry
    participant A as Externalization adapter
    participant B as Kafka broker

    C->>O: confirmOrder()
    O->>O: Update aggregate and publish event
    O->>R: Register publication
    O->>O: Commit transaction
    R->>A: Dispatch externalization
    A->>A: Serialize and build record
    A->>B: Send record
    B-->>A: Broker acknowledgement
    A-->>R: Complete publication
~~~

Sơ đồ mô tả các mốc khái niệm. Thứ tự dispatch, thời điểm gửi và cách hoàn tất publication phụ thuộc integration, transaction manager và cấu hình thực tế.

## Phân biệt các mốc thời gian

Một con số end-to-end duy nhất hữu ích cho SLO, nhưng không đủ để tìm nguyên nhân chậm. Hãy ghi nhận các mốc chính:

| Mốc | Ý nghĩa |
|---|---|
| Event created | Event object hoặc envelope được tạo |
| Publish invoked | Ứng dụng gọi API công bố event |
| Publish returned | Lời gọi API công bố trả về |
| Business commit | Transaction nghiệp vụ commit thành công |
| Externalization dispatched | Listener/adapter bắt đầu gửi event ra ngoài |
| Serialization completed | Payload và metadata đã được chuyển thành message bytes |
| Send initiated | Producer bắt đầu gửi message |
| Broker acknowledged | Broker xác nhận theo chế độ acknowledgement đã cấu hình |
| Publication completed | Registry ghi nhận publication hoàn tất theo semantics của integration |

Không phải ứng dụng nào cũng có đủ các mốc trên. Hãy chọn một tập mốc đo được ổn định và ghi rõ ý nghĩa của từng mốc.

Một số khoảng đo thường dùng:

- **Local publish duration:** publish returned trừ publish invoked.
- **Commit-to-dispatch delay:** externalization dispatched trừ business commit.
- **Serialization duration:** serialization completed trừ serialization started.
- **Producer send duration:** broker acknowledged trừ send initiated.
- **End-to-end publish latency:** broker acknowledged trừ mốc bắt đầu đã thống nhất, thường là event created hoặc business commit.

Nếu API gửi message bất đồng bộ, thời điểm hàm send trả về có thể chỉ là lúc producer chấp nhận enqueue request trong bộ đệm cục bộ. Muốn đo thời gian broker nhận, phải quan sát callback/future acknowledgement hoặc API xác nhận tương đương của client.

## Publish latency khác gì với delivery và processing latency?

Ba giai đoạn cần được tách biệt:

| Loại độ trễ | Bắt đầu | Kết thúc |
|---|---|---|
| Publish latency | Ứng dụng bắt đầu công bố event | Broker xác nhận nhận message hoặc mốc publish nội bộ được chọn |
| Delivery latency | Broker nhận message | Consumer nhận được message |
| Processing latency | Consumer bắt đầu xử lý | Consumer commit kết quả và acknowledge/commit offset |

Tổng thời gian từ nghiệp vụ phát sinh đến khi hệ thống nhận hoàn tất có thể bao gồm cả ba giai đoạn. Nếu dashboard chỉ có một metric "event latency", đội vận hành khó biết sự cố nằm ở publisher, broker hay consumer.

Với application event nội bộ, không có broker delivery latency. Với externalized event, cần tách thời gian ứng dụng chờ sau commit, thời gian gửi tới broker và thời gian broker giữ message trước khi consumer nhận.

## Xác định SLO và percentile

Publish latency thường có phân bố lệch. Phần lớn event có thể được gửi trong vài mili giây, nhưng một số event bị chậm do retry, broker leader thay đổi, network timeout hoặc producer buffer đầy.

Nên theo dõi:

- p50: độ trễ điển hình.
- p95: độ trễ của nhóm event chậm hơn phần lớn.
- p99: phần đuôi phân bố, thường giúp phát hiện sự cố hiếm.
- Max và tuổi event pending lâu nhất: phát hiện publication bị treo.
- Error rate và retry count: bổ sung ngữ cảnh cho latency.

Ví dụ mục tiêu minh họa:

| Chỉ số | Mục tiêu ví dụ |
|---|---:|
| Publish latency p50 | Dưới 20 ms |
| Publish latency p95 | Dưới 100 ms |
| Publish latency p99 | Dưới 500 ms |
| Broker publish success rate | Trên 99.9% |
| Publication pending lâu nhất | Dưới 30 giây |

Các ngưỡng trên không phải mặc định cho Spring Modulith, Kafka hoặc RabbitMQ. Hãy đặt SLO dựa trên broker, tải, durability, network, kích thước payload và yêu cầu nghiệp vụ. Ghi rõ SLO áp dụng cho event type nào, môi trường nào và đo đến acknowledgement ở cấp nào.

Một SLO hữu ích cũng cần xác định cách tính event lỗi. Nếu chỉ tính latency của event thành công, các event retry vô hạn có thể biến mất khỏi percentile và làm dashboard trông tốt giả tạo. Theo dõi riêng tỷ lệ thành công, timeout, pending và tuổi publication chưa hoàn tất.

## Đo thời gian bằng timestamp và tracing

Có thể gắn metadata quan sát vào event hoặc message envelope:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    long aggregateVersion,
    Instant occurredAt,
    Instant publishedAt,
    String correlationId
) {}
~~~

Các mốc cần phân biệt:

- `occurredAt`: thời điểm nghiệp vụ xảy ra.
- `publishedAt`: thời điểm publisher bắt đầu hoặc ghi nhận việc công bố theo quy ước đã chọn.
- `sendStartedAt`: thời điểm producer bắt đầu gửi.
- `brokerAckAt`: thời điểm nhận xác nhận từ broker, thường được ghi trong metric/log chứ không nhất thiết nằm trong payload.

Không nhất thiết phải đưa tất cả timestamp vào event contract. Các mốc kỹ thuật như sendStartedAt và brokerAckAt thường phù hợp hơn với trace hoặc metric vì chúng phụ thuộc lần gửi và hạ tầng.

Nếu producer và broker client chạy ở các máy khác nhau, timestamp từ hai clock có thể lệch. Đo chênh lệch timestamp trực tiếp chỉ đáng tin khi clock được đồng bộ và sai số đã được hiểu. Với thời gian thực thi trong một tiến trình, dùng monotonic clock để đo duration; với tracing phân tán, dùng span timestamps từ hệ thống tracing được cấu hình đồng bộ.

Một trace có thể tạo các span riêng:

~~~text
orders.confirm
  ├─ transaction.commit
  ├─ event.externalization.dispatch
  ├─ event.serialize
  └─ kafka.producer.send
       └─ kafka.broker.ack
~~~

Trace context cần được truyền qua executor và message header nếu muốn nối các chặng. Không dùng event ID làm metric label vì cardinality lớn; event ID phù hợp với log và trace.

## Độ trễ trong Spring Modulith

Spring Modulith cho phép module phát application event bằng `ApplicationEventPublisher`, theo dõi publication của listener bằng Event Publication Registry và externalize event được chọn thông qua integration tương ứng.

Cần hiểu riêng các phần:

- `publishEvent(...)` công bố event vào ApplicationContext. Với cấu hình mặc định của Spring event multicaster, listener đồng bộ có thể chạy ngay trong luồng gọi; nếu cấu hình async, thời điểm trả về và thời điểm listener chạy sẽ khác.
- Transaction nghiệp vụ xác định lúc dữ liệu nguồn trở nên bền vững.
- Event Publication Registry ghi nhận publication cho listener được theo dõi và trạng thái xử lý của publication theo implementation.
- Externalization adapter chuyển event thành message và gửi tới broker.
- Broker acknowledgement xác nhận theo semantics của producer client và cấu hình broker.

Đối với event cần externalize, hãy đo riêng thời gian từ commit đến khi adapter bắt đầu gửi, thời gian serialize, thời gian send/ack và thời gian publication pending. Không suy ra broker publish latency chỉ từ thời gian `publishEvent` trả về.

Với listener transaction-bound hoặc `@ApplicationModuleListener`, thời điểm xử lý phụ thuộc phase và executor mà annotation/cấu hình sử dụng. Listener chạy sau commit có thể khiến command đã commit trước khi externalization bắt đầu. Đây là khoảng chờ cần đo nếu SLO tính từ commit.

Event Publication Registry có thể giúp quan sát publication chưa hoàn tất và hỗ trợ phục hồi theo persistence implementation đã cấu hình. Registry không thay thế metric của producer client hoặc broker. Một publication được đánh dấu hoàn tất cũng cần được hiểu theo adapter: thường là bước externalization đã hoàn thành theo callback/semantics mà integration sử dụng, không phải consumer downstream đã xử lý nghiệp vụ.

## Các nguyên nhân phổ biến làm publish chậm

### Transaction commit và dispatch bị trì hoãn

Nếu externalization chỉ được thực hiện sau commit, thời gian commit-to-dispatch phụ thuộc transaction duration, callback và executor. Transaction dài có thể khiến event phải đợi dù broker đang khỏe.

Giữ transaction nghiệp vụ ngắn: tránh gọi HTTP, thực hiện tính toán nặng hoặc chờ tài nguyên bên ngoài khi transaction đang mở. Chỉ phát event sau khi trạng thái nghiệp vụ đã được xác định và transaction manager có thể ghi nhận publication đúng ranh giới.

### Executor hoặc publication backlog

Nếu externalization/listener chạy bất đồng bộ, executor có thể không có đủ worker hoặc queue bị đầy. Khi tốc độ event đến cao hơn tốc độ dispatch, publication chờ lâu trước khi producer gọi broker.

Theo dõi:

- Active thread và pool utilization.
- Queue size, queue wait và task rejection.
- Số publication incomplete.
- Tuổi publication pending lâu nhất.
- Tốc độ publication được tạo và tốc độ hoàn tất.

Đặt giới hạn queue và concurrency. Queue vô hạn có thể che dấu thiếu năng lực xử lý trong thời gian ngắn nhưng cuối cùng làm bộ nhớ tăng. Không tăng thread vô hạn vì producer, database và broker client đều có giới hạn tài nguyên.

### Serialization và payload lớn

Serialize payload lớn, object graph sâu hoặc dữ liệu có nhiều field có thể tiêu tốn CPU và allocation. Payload lớn cũng làm tăng thời gian truyền và chi phí lưu trữ của broker.

Có thể giảm chi phí bằng cách:

- Chỉ đưa dữ liệu consumer thực sự cần vào event.
- Tránh gửi entity ORM, lazy proxy và object graph lớn.
- Chọn serializer phù hợp và đo bằng payload thực tế.
- Tránh nén payload nhỏ nếu chi phí CPU lớn hơn lợi ích băng thông.
- Đặt giới hạn kích thước event và theo dõi phân bố payload size.

Không loại bỏ field nghiệp vụ cần thiết chỉ để đạt latency thấp. Hãy thiết kế contract gọn, ổn định và có version.

### Network và broker không sẵn sàng

DNS lookup, TLS handshake, connection establishment, network congestion, broker leader election hoặc broker overload có thể làm tăng thời gian gửi.

Dùng connection/client được tái sử dụng, pool phù hợp và TLS session reuse theo khả năng thư viện. Theo dõi DNS, connection errors, request latency, broker throttle và network retransmission. Không tạo producer/client mới cho mỗi event nếu integration được thiết kế để tái sử dụng client.

### Acknowledgement và durability

Producer có thể chờ broker xác nhận theo chế độ durability. Kafka producer với `acks=all` có thể chờ các replica trong ISR xác nhận; cấu hình này tăng độ tin cậy nhưng có thể tăng latency so với mức xác nhận yếu hơn. RabbitMQ publisher confirms cũng có chi phí và semantics riêng.

Không giảm mức acknowledgement chỉ để làm metric nhanh hơn mà không đánh giá rủi ro mất message. Chọn durability theo yêu cầu dữ liệu và replication. Theo dõi latency riêng theo acknowledgement mode để hiểu trade-off.

### Retry và timeout

Timeout ngắn có thể làm một request bị retry dù broker đã nhận message nhưng acknowledgement bị trễ. Khi đó, producer có thể gửi lại và tạo duplicate delivery. Retry nhiều lần cũng làm tăng tail latency và tải broker.

Cần cấu hình timeout phù hợp với latency phân vị của broker, retry có backoff và jitter, giới hạn số lần thử hoặc thời gian tổng. Kết hợp event ID và idempotency ở consumer để xử lý duplicate delivery an toàn.

Không retry mọi lỗi như nhau. Lỗi xác thực, quyền publish hoặc payload không hợp lệ thường cần xử lý cấu hình/quarantine thay vì lặp lại vô hạn.

## Tối ưu producer và adapter

### Tái sử dụng producer client

Producer client thường duy trì connection, metadata, buffer và thread nội bộ. Tái sử dụng client giúp tránh chi phí khởi tạo và bắt tay kết nối trên từng event. Vòng đời client nên gắn với application context và được đóng đúng khi ứng dụng shutdown.

### Gửi bất đồng bộ và xác nhận rõ ràng

API producer bất đồng bộ có thể trả về nhanh khi message được nhận vào buffer. Cần theo dõi callback/future để biết kết quả gửi thực tế. Nếu ứng dụng đánh dấu publication hoàn tất trước khi broker xác nhận theo policy đã chọn, có nguy cơ mất dấu một lần gửi thất bại.

Hãy phân biệt:
- Enqueued locally: producer client nhận yêu cầu gửi.
- Send completed: client hoàn thành thao tác gửi.
- Broker acknowledged: broker xác nhận theo cấu hình.
- Consumer processed: consumer đã xử lý nghiệp vụ.

Chọn mốc phù hợp cho metric và publication completion.

### Batch và linger

Kafka producer có thể gom nhiều record thành batch để giảm số request mạng. Cấu hình `batch.size` và `linger.ms` tạo trade-off: batch lớn hơn có thể tăng throughput và giảm overhead trên mỗi record, nhưng record đầu tiên trong batch có thể phải chờ lâu hơn.

Nếu ưu tiên latency thấp, giữ linger nhỏ và quan sát batch utilization. Nếu tải cao và chấp nhận thêm một khoảng chờ nhỏ, batching có thể cải thiện throughput tổng thể. Đo p95/p99 cùng throughput, không chỉ nhìn average.

Với RabbitMQ, batching không có semantics giống Kafka producer batch; có thể publish nhiều message trên channel nhưng cần hiểu publisher confirms và flow control của client/broker.

### Compression

Compression giảm bytes truyền và có thể hữu ích với payload lớn hoặc network giới hạn. Tuy nhiên, nén làm tăng CPU và có thể tăng latency cho message nhỏ. Chọn codec và mức nén dựa trên benchmark với payload thực tế, không bật mức nén cao nhất theo mặc định.

### Partitioning và routing

Kafka key ảnh hưởng đến partition. Dùng aggregate ID làm key có thể giữ các event của cùng aggregate trên một partition, nhưng key nóng có thể tạo partition skew và làm tăng queueing latency ở partition đó.

Với RabbitMQ, exchange, routing key, binding và queue depth ảnh hưởng đến nơi message được chuyển tới. Queue có consumer chậm có thể tích backlog dù publisher gửi nhanh.

Định tuyến đúng là điều kiện để consumer nhận message, nhưng publish latency tới broker và delivery latency tới consumer vẫn là hai metric khác nhau.

## Backpressure và kiểm soát backlog

Gọi \(\lambda\) là tốc độ event đến và \(\mu\) là tốc độ adapter/producer hoàn tất publish. Nếu \(\lambda > \mu\) trong thời gian dài, hàng đợi publication tăng. Khi đó, latency end-to-end tăng dù thời gian gửi một message riêng lẻ không đổi.

Ví dụ minh họa:

| Đại lượng | Giá trị |
|---|---:|
| Event đến | 2.000 event/giây |
| Publish hoàn tất | 1.700 event/giây |
| Backlog tăng | 300 event/giây |
| Backlog sau 5 phút | Khoảng 90.000 event |

Đây là phép tính đơn giản, chưa tính retry và biến động tải. Nó cho thấy cần theo dõi tốc độ tạo publication, tốc độ hoàn tất và số lượng pending cùng lúc.

Các biện pháp:
- Giới hạn concurrency và queue của executor.
- Điều chỉnh batch, producer buffer và connection pool.
- Tăng năng lực broker/partition khi có bằng chứng bottleneck nằm ở broker.
- Giảm kích thước payload và tối ưu serialization.
- Điều tiết producer nếu hệ thống cho phép.
- Tách luồng event có mức ưu tiên hoặc SLO khác nhau khi topology hỗ trợ.

Không bỏ event để giảm backlog. Nếu queue đầy, cần giữ publication ở trạng thái có thể phục hồi hoặc áp dụng backpressure có kiểm soát.

## Retry, duplicate và tác động đến latency

Retry giúp tăng xác suất publish thành công nhưng làm tăng thời gian hoàn tất của event. Một event chỉ thành công sau ba lần gửi có thể có publish latency cao hơn nhiều so với p99 của lần gửi đơn lẻ.

Theo dõi cả:
- Latency của lần gửi đầu.
- Tổng thời gian từ lần thử đầu đến khi thành công.
- Số lần retry trên mỗi event.
- Tỷ lệ timeout và lỗi broker.
- Tuổi publication chưa hoàn tất.
- Số duplicate có thể phát sinh do acknowledgement không rõ ràng.

Khi timeout xảy ra, không luôn biết broker đã nhận message hay chưa. Retry có thể tạo duplicate. Event ID ổn định và consumer idempotent giúp giữ tính đúng đắn khi delivery at-least-once.

Không tạo event ID mới cho mỗi lần retry. Nếu event ID thay đổi, consumer không thể nhận diện các lần gửi là cùng một sự kiện.

## Đo lường và quan sát publish pipeline

Một dashboard publish latency nên kết hợp metric ứng dụng, producer client và broker:

| Metric | Mục đích |
|---|---|
| event_publish_duration | Thời gian publish theo mốc đã định nghĩa |
| event_commit_to_dispatch_delay | Độ trễ từ commit đến lúc adapter bắt đầu |
| event_serialization_duration | Chi phí serialize |
| producer_send_duration | Thời gian từ send đến completion/ack |
| publish_success_total | Số lần publish thành công |
| publish_failure_total | Số lần publish thất bại |
| publish_retry_total | Số lần retry |
| publication_pending | Số publication chưa hoàn tất |
| publication_oldest_age | Tuổi publication pending lâu nhất |
| producer_buffer_available | Dung lượng buffer còn lại nếu client cung cấp |
| broker_request_latency | Latency request broker |
| payload_size_bytes | Kích thước payload |

Metric label nên giới hạn ở event type, destination, producer và kết quả. Không dùng event ID, aggregate ID hoặc correlation ID làm label vì cardinality tăng không giới hạn. Các ID này phù hợp với log và trace.

Log/trace nên nối được:
- Event ID và event type.
- Correlation/trace ID.
- Thời điểm commit, dispatch, send và acknowledgement.
- Destination, partition hoặc routing metadata.
- Số lần retry và mã lỗi.
- Publication identifier nếu registry cung cấp.

Không log payload nhạy cảm chỉ để đo latency.

## Kiểm thử publish latency

Kiểm thử nên bao phủ các mốc thời gian và tải khác nhau:

| Loại kiểm thử | Điều cần xác nhận |
|---|---|
| Unit test publisher | Event được tạo đúng và phát đúng một lần theo command |
| Transaction test | Publication được gắn với transaction và không externalize thay đổi rollback |
| Adapter integration test | Mapping, serialization và send result đúng |
| Broker integration test | Broker acknowledgement và destination hoạt động đúng |
| Load test | Throughput, p50/p95/p99 và backlog ở tải dự kiến |
| Burst test | Hệ thống phục hồi backlog sau đợt tải tăng |
| Failure test | Timeout, broker restart và retry được đo/quan sát đúng |
| Recovery test | Publication pending được phục hồi sau restart theo persistence config |

Dùng broker test hoặc container tương đương khi cần xác nhận acknowledgement và latency thực tế. Mock producer chỉ kiểm tra logic gọi API, không đo được network, broker, replication hoặc flow control.

Đo trong điều kiện gần production: TLS, replication, acknowledgement mode, payload size, partition count và tải đồng thời cần tương đồng. Một benchmark chạy trên broker local một node không đại diện cho latency của cluster production.

## Quy trình điều tra khi publish chậm

Khi p95/p99 vượt SLO, lần theo pipeline theo thứ tự:

1. Xác định event type, destination và thời điểm bắt đầu đo.
2. So sánh event created, business commit và externalization dispatch.
3. Kiểm tra publication pending và executor queue.
4. Đo serialization duration và payload size.
5. Kiểm tra producer buffer, connection, retry và timeout.
6. Đối chiếu broker request latency, throttle, replication và leader changes.
7. Xác định backlog tăng do tốc độ event đến vượt tốc độ publish hoàn tất hay không.
8. Thử điều chỉnh một yếu tố có kiểm soát và đo lại p95/p99 cùng throughput.
9. Xác nhận durability/acknowledgement vẫn đáp ứng yêu cầu nghiệp vụ.

Không chỉ tối ưu average latency. Một thay đổi có thể làm p50 tốt hơn nhưng khiến p99 xấu đi do batching, queueing hoặc retry.

## Quy trình thiết kế SLO publish

Khi thêm event externalization, hãy xác định:

1. SLO bắt đầu từ lúc event được tạo hay transaction nghiệp vụ commit?
2. SLO kết thúc khi producer enqueue, broker acknowledge hay publication registry hoàn tất?
3. Event nào cần latency thấp và event nào ưu tiên throughput?
4. Durability/acknowledgement nào là bắt buộc?
5. Payload size, serializer, batching và compression có giới hạn ra sao?
6. Executor, buffer và retry được giới hạn như thế nào?
7. Backlog và publication pending được quan sát bằng metric nào?
8. Khi vượt SLO, hệ thống điều tiết hoặc phục hồi ra sao?

Độ trễ publish chỉ có ý nghĩa khi mốc đo được định nghĩa rõ. Khi tách thời gian commit, dispatch, serialization, gửi và broker acknowledgement; đồng thời theo dõi percentile, backlog và retry, đội phát triển có thể tìm đúng bottleneck và tối ưu hiệu năng mà vẫn giữ yêu cầu durability của giao sự kiện.

## Tài liệu tham khảo

- Spring Modulith Reference — Working with Application Events: https://docs.spring.io/spring-modulith/reference/events.html
- Spring Kafka Reference — KafkaTemplate and Producer Configuration: https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html
- Apache Kafka Documentation — Producer Configs: https://kafka.apache.org/documentation/#producerconfigs
- RabbitMQ Documentation — Publisher Confirms: https://www.rabbitmq.com/docs/confirms
- OpenTelemetry Documentation — Traces: https://opentelemetry.io/docs/concepts/signals/traces/
