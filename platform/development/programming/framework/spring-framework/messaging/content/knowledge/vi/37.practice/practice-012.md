# Rà soát lựa chọn công nghệ từ yêu cầu đến kết quả kiểm chứng

> Phạm vi: thực hành ra quyết định công nghệ cho hệ thống messaging trong Spring. Bài học đi từ yêu cầu nghiệp vụ, chọn pattern và transport, đánh giá trade-off, thử nghiệm bằng prototype, đến kiểm chứng bằng số liệu và lưu quyết định có thể rà soát lại.

## 1. Mục tiêu của một lần rà soát công nghệ

Chọn công nghệ không bắt đầu bằng câu hỏi “nên dùng RabbitMQ hay Kafka?”. Nó bắt đầu bằng vấn đề cần giải quyết và bằng chứng cho thấy một lựa chọn đáp ứng vấn đề đó.

Một quyết định có chất lượng phải trả lời được:

1. Hệ thống cần thực hiện hành vi nào và ai sử dụng hành vi đó?
2. Các yêu cầu bắt buộc là gì? Những thuộc tính nào chỉ là ưu tiên?
3. Hệ thống cần kiểu tương tác nào: request/reply, command queue, event stream, broadcast hay streaming hai chiều?
4. Transport và framework nào đáp ứng các yêu cầu với chi phí vận hành chấp nhận được?
5. Giả định nào đã được kiểm tra, giả định nào còn rủi ro?
6. Kết quả prototype và test chứng minh điều gì?
7. Khi nào cần xem xét lại quyết định?

Một lựa chọn công nghệ không được coi là hoàn tất chỉ vì dependency đã được thêm vào hoặc ứng dụng khởi động thành công. Cần chứng minh đường đi message, lỗi, bảo mật, tải, phục hồi và khả năng vận hành đáp ứng tiêu chí đã thống nhất.

## 2. Phân biệt các lớp quyết định

Trong một ứng dụng Spring Messaging, thường có nhiều quyết định liên quan nhưng không đồng nghĩa:

| Lớp | Câu hỏi cần quyết định | Ví dụ |
|---|---|---|
| Hợp đồng message | Message chứa gì, version và ID ra sao? | Event envelope, schema version, correlation ID |
| Interaction pattern | Hai phía trao đổi theo cách nào? | Request-Response, competing consumers, publish-subscribe |
| Transport/protocol | Message đi qua giao thức nào? | AMQP, Kafka protocol, JMS, RSocket, HTTP |
| Broker/platform | Hệ thống nào lưu và phân phối message? | RabbitMQ, Kafka cluster, Artemis |
| Integration framework | Các bước trong ứng dụng được kết nối thế nào? | Spring Integration, Spring Messaging |
| Adapter/client | Ứng dụng giao tiếp với transport bằng API nào? | Spring AMQP, Spring Kafka, Spring JMS, RSocketRequester |
| Vận hành | Ai triển khai, giám sát, backup, nâng cấp và xử lý sự cố? | Cluster topology, metrics, alert, retention, runbook |

**Spring Integration là framework để kết nối các hệ thống và tạo message flow; nó không tự thay thế broker.** Các channel như DirectChannel hoặc QueueChannel có thể chạy trong bộ nhớ của process. Khi cần lưu message bền vững hoặc giao tiếp giữa nhiều process, cần transport/broker hoặc channel được backing bởi hạ tầng phù hợp.

Spring Integration hỗ trợ adapter và gateway cho nhiều hệ thống, trong đó có AMQP, JMS, Kafka, RSocket, HTTP, TCP và file. Spring Boot cũng có các tích hợp messaging riêng cho JMS, AMQP/RabbitMQ, Kafka, Pulsar, RSocket và Spring Integration. Vì vậy, nên chọn riêng lớp transport và lớp điều phối flow, rồi mới quyết định có cần cả hai hay không.

Ví dụ:

- Ứng dụng chỉ cần nhận message từ RabbitMQ và gọi một service có thể dùng Spring AMQP listener trực tiếp.
- Flow cần nhận message, chuẩn hóa, lọc, định tuyến qua nhiều endpoint rồi gửi ra nhiều hệ thống có thể hưởng lợi từ Spring Integration.
- Một pipeline nội bộ trong cùng process có thể chỉ cần Spring Integration với DirectChannel; không cần triển khai broker nếu không có yêu cầu durability hoặc giao tiếp liên process.

## 3. Thu thập yêu cầu trước khi lập danh sách công nghệ

### 3.1. Mô tả luồng nghiệp vụ bằng ngôn ngữ của người dùng

Ghi rõ:

- Ai phát yêu cầu hoặc sự kiện?
- Ai nhận và chịu trách nhiệm xử lý?
- Message biểu diễn một command, một event hay một truy vấn?
- Caller có cần kết quả ngay không?
- Consumer có thể offline trong bao lâu?
- Có bao nhiêu consumer độc lập?
- Message có được xử lý lại, phát lại hoặc lưu lịch sử không?
- Khi message lỗi, ai xử lý và thời hạn khắc phục là bao lâu?

Tránh bắt đầu từ tên sản phẩm. Hãy mô tả luồng bằng động từ và kết quả nghiệp vụ, ví dụ: “Checkout xác nhận đơn; hệ thống phải giao lệnh fulfillment cho worker ngay cả khi worker đang khởi động lại; mỗi đơn chỉ được tạo shipment một lần; nhóm vận hành phải xem được message lỗi và phát lại sau khi sửa dữ liệu.”

### 3.2. Chuyển yêu cầu thành tiêu chí có thể đo

Một yêu cầu như “nhanh”, “ổn định” hoặc “chịu tải cao” không thể kiểm chứng nếu không có con số hoặc điều kiện cụ thể.

| Thuộc tính | Câu hỏi cần trả lời | Cách đo |
|---|---|---|
| Throughput | Bao nhiêu message/giây ở tải bình thường và đỉnh? | Message/second, số consumer, batch size |
| Latency | Producer gửi đến lúc consumer bắt đầu/hoàn tất xử lý mất bao lâu? | p50, p95, p99 |
| Durability | Message đã được xác nhận có sống sót qua loại sự cố nào? | Restart process, restart broker, node failure |
| Delivery semantics | Có thể giao lặp, mất hoặc xử lý trùng không? | Redelivery, acknowledgement, idempotency |
| Ordering | Cần thứ tự toàn cục hay chỉ theo một key? | Thứ tự theo orderId/partition/queue |
| Fan-out | Có bao nhiêu nhóm consumer độc lập cần cùng nhận event? | Số subscription/consumer group |
| Replay/retention | Có cần đọc lại dữ liệu cũ và trong bao lâu? | Retention, offset/sequence, replay test |
| Availability | Downtime tối đa và RTO/RPO là bao nhiêu? | Failover và recovery exercise |
| Security | Ai được publish, consume, route và xem dữ liệu? | TLS, authentication, authorization, audit |
| Operability | Đội vận hành có thể giám sát và khôi phục thế nào? | Dashboard, alert, runbook, backup/restore |
| Compatibility | Producer/consumer có thể nâng cấp độc lập không? | Contract fixtures, schema evolution test |
| Cost | Chi phí hạ tầng, vận hành và phát triển là bao nhiêu? | CPU, RAM, storage, license, on-call effort |

Phân biệt **yêu cầu bắt buộc** với **ưu tiên**. Ví dụ “message đã được broker xác nhận phải tồn tại qua restart một node” có thể là hard gate. “Dễ viết code hơn” thường là tiêu chí ưu tiên. Một lựa chọn có điểm tổng cao vẫn phải bị loại nếu vi phạm hard gate.

### 3.3. Viết quality-attribute scenario

Dùng cấu trúc: *bối cảnh → kích thích/sự cố → phản ứng mong đợi → thước đo*.

Ví dụ:

- Bối cảnh: 1.000 message/giây được publish vào queue fulfillment.
- Sự cố: một consumer process dừng khi đang xử lý message.
- Phản ứng: message chưa được acknowledge được giao lại; consumer mới tiếp tục xử lý.
- Đo lường: không mất message đã được broker xác nhận; redelivery được nhận diện; xử lý trùng không tạo shipment thứ hai.

Một ví dụ khác:

- Bối cảnh: consumer phân tích dữ liệu cần đọc lại event của 14 ngày trước.
- Sự cố: consumer được triển khai lại và cần dựng lại projection.
- Phản ứng: consumer đọc lại từ offset phù hợp trong retention window.
- Đo lường: projection sau replay khớp với dữ liệu kiểm soát và thời gian rebuild nằm trong SLA.

Các scenario này dẫn đến lựa chọn khác nhau. Queue phục vụ công việc và log sự kiện có retention/replay là hai nhu cầu khác nhau, dù cả hai đều gọi là “message queue” trong hội thoại hàng ngày.

## 4. Chọn interaction pattern trước khi chọn transport

| Nhu cầu | Pattern phù hợp | Điểm cần kiểm chứng |
|---|---|---|
| Gửi một request và cần một response | Request-Response / Gateway | Timeout, correlation, reply routing, lỗi khi caller ngắt kết nối |
| Gửi command để một worker xử lý | Point-to-Point / Competing Consumers | Durability, acknowledgement, retry, dead-letter, idempotency |
| Phát event cho nhiều hệ thống độc lập | Publish-Subscribe | Mỗi consumer có subscription riêng, fan-out, retention/replay |
| Gửi một luồng event liên tục | Event Stream | Partition key, offset, retention, consumer lag |
| Trao đổi hai chiều theo phiên kết nối | Channel / Bidirectional Streaming | Backpressure, cancellation, keepalive, reconnect |
| Chuyển đổi và định tuyến giữa nhiều hệ thống | Integration Flow | Adapter, transformer, filter, router, error flow |
| Lấy dữ liệu theo chu kỳ | Polling / MessageSource | Poll interval, concurrency, lock/claim, duplicate processing |

Không dùng request/reply chỉ vì API gateway đang thuận tiện nếu nghiệp vụ thực sự cần xử lý bất đồng bộ. Ngược lại, không dựng broker cho một truy vấn đơn giản cần response tức thời nếu HTTP/WebClient đã đáp ứng SLA và mô hình lỗi.

## 5. Các lựa chọn thường gặp trong hệ sinh thái Spring

### 5.1. Channel trong cùng process

**DirectChannel** dispatch message đồng bộ đến một subscriber. Đây là lựa chọn phù hợp cho flow nội bộ đơn giản, nơi producer và consumer cùng chạy trong một process.

**QueueChannel** giữ message trong queue nội bộ để producer và consumer tách nhau về thời điểm. Queue này không tự trở thành durable storage; process dừng có thể làm mất message còn trong bộ nhớ.

**PublishSubscribeChannel** gửi message đến nhiều subscriber trong cùng ứng dụng. Nó phục vụ fan-out nội bộ, không tự tạo bản sao bền vững qua restart.

Chọn channel nội bộ khi:
- Message chỉ cần tồn tại trong vòng đời process.
- Không cần consumer độc lập ở service khác.
- Không cần replay sau khi ứng dụng restart.
- Độ trễ và sự đơn giản trong process là ưu tiên.

Không dùng channel nội bộ để đáp ứng yêu cầu durable queue giữa nhiều service.

### 5.2. RabbitMQ/AMQP với Spring AMQP và Spring Integration

RabbitMQ thường phù hợp với command/work queue, routing qua exchange, competing consumers, request/reply qua gateway và fan-out bằng exchange/queue binding.

Spring AMQP cung cấp các abstraction như RabbitTemplate, listener container và message converter. Spring Integration có inbound/outbound channel adapter và gateway để nối AMQP vào flow.

Ưu điểm thường gặp:
- Routing linh hoạt bằng exchange, routing key và binding.
- Queue phù hợp cho competing consumers.
- Acknowledgement, publisher confirms và dead-letter/retry có thể cấu hình.
- Hợp với luồng command và công việc cần xử lý rồi acknowledge.

Điểm cần kiểm chứng:
- Durable queue và persistent message có được cấu hình đúng không?
- Publisher có chờ confirm trước khi coi message là accepted không?
- Consumer ack sau khi xử lý thành công hay trước khi side effect hoàn tất?
- Retry có giới hạn và có dead-letter policy không?
- Queue type, replication và topology có đáp ứng failure model không?
- Routing có gửi message không match vào alternate exchange hoặc xử lý lỗi rõ ràng không?

**Publisher confirm và consumer acknowledgement là hai cơ chế độc lập.** Confirm xác nhận phía broker đã nhận publish theo semantics cấu hình; consumer ack cho broker biết delivery đã được xử lý để broker có thể loại bỏ message. Bật một cơ chế không thay thế cơ chế còn lại. Cấu hình durable queue một mình cũng không chứng minh toàn bộ đường đi không mất dữ liệu.

Spring Integration có AMQP-backed channel, nhưng tài liệu phân biệt channel persistence với phân phối công việc cho peer application. Khi cần nhiều ứng dụng cùng consume queue, dùng channel adapters/listener containers hoặc Spring AMQP listener phù hợp thay vì nhầm AMQP-backed channel nội bộ với cơ chế work distribution.

### 5.3. Apache Kafka với Spring for Apache Kafka

Kafka phù hợp khi dữ liệu là log sự kiện có thứ tự theo partition, cần retention, nhiều consumer group độc lập, replay và khả năng dựng lại projection.

Spring for Apache Kafka cung cấp:
- KafkaTemplate để publish.
- @KafkaListener và listener container để consume.
- Offset management, retry/error handling và transaction support.
- Serialization, deserialization và message header mapping.
- Test support để kiểm thử producer/consumer.

Điểm cần kiểm chứng:
- Partition key có giữ thứ tự cho cùng aggregate không?
- Số partition có đủ cho throughput và concurrency?
- Consumer lag có dashboard và alert không?
- Retention có đủ dài cho replay?
- Offset commit/acknowledgement được chọn phù hợp với side effect không?
- Consumer có idempotent khi record được giao lại không?
- Schema evolution và payload compatibility được quản lý thế nào?

Kafka không tự bảo đảm thứ tự toàn cục giữa mọi partition. Nếu cần thứ tự theo orderId, chọn key để các event cùng orderId đi vào cùng partition và kiểm tra concurrency ở consumer.

### 5.4. JMS với broker như ActiveMQ Artemis

JMS là API messaging chuẩn Java. Spring JMS cung cấp cách gửi/nhận thông qua JmsTemplate/JmsClient và listener container; Spring Integration có adapter/gateway JMS.

JMS đáng xem xét khi:
- Tổ chức đã có broker JMS và quy trình vận hành ổn định.
- Cần portability ở tầng API giữa các provider JMS tương thích.
- Hệ thống dùng queue/topic, listener, transaction và acknowledgement theo mô hình JMS.
- Các hệ thống enterprise hiện hữu đã tích hợp JMS.

Điểm cần kiểm chứng:
- Provider cụ thể và phiên bản broker có tương thích với runtime không?
- Destination, durable subscription và acknowledgement mode được cấu hình thế nào?
- Transaction boundary có bao phủ resource nào?
- Tính năng đặc thù của vendor có làm giảm portability thực tế không?

JMS là API/contract, không phải tên của một broker. Cần ghi rõ broker/provider thực tế trong quyết định.

### 5.5. RSocket

RSocket là protocol messaging bất đồng bộ trên byte stream transport, hỗ trợ các interaction model như Request-Response, Request-Stream, Fire-and-Forget và Channel. Spring Messaging cung cấp requester/responder và Spring Boot có thể tự cấu hình codec và handler.

RSocket phù hợp khi hai phía cần giao tiếp hai chiều, stream dữ liệu, backpressure và cancellation qua kết nối đang hoạt động.

Không chọn RSocket chỉ để thay durable broker. Protocol kết nối không tự cung cấp retention log hoặc hàng đợi bền vững cho consumer offline. Nếu message phải sống qua thời gian service mất kết nối, cần persistence/broker hoặc cơ chế lưu trữ riêng.

### 5.6. HTTP/REST và WebClient

HTTP phù hợp với request/reply, resource-oriented API và các tương tác cần phản hồi rõ ràng ngay trong request. WebClient hỗ trợ reactive HTTP.

HTTP có thể là lựa chọn đơn giản nếu caller cần kết quả ngay và không cần broker retention, replay hay decoupled consumer. Nếu cần công việc chạy sau khi response trả về, có thể API nhận command, lưu command/outbox bền vững rồi trả accepted; phần xử lý tiếp tục qua messaging.

Đừng xem HTTP request timeout là bằng chứng server chưa thực hiện side effect. Nếu response bị mất sau khi server đã xử lý, client retry có thể gửi lệnh trùng. Cần idempotency key khi thao tác không được lặp.

## 6. Ma trận so sánh có điều kiện

Bảng sau chỉ là định hướng ban đầu; nó không thay thế benchmark và xác nhận topology cụ thể.

| Lựa chọn | Work queue/routing | Event replay | Request/reply | Streaming hai chiều | Độ bền liên process |
|---|---|---|---|---|---|
| DirectChannel | Không, chỉ trong process | Không | Có thể qua gateway nội bộ | Không phải mục đích chính | Không |
| QueueChannel | Queue nội bộ | Không | Có thể qua flow | Không phải mục đích chính | Không tự durable |
| RabbitMQ/AMQP | Rất phù hợp | Hạn chế theo queue/stream và retention cấu hình | Có gateway/request-reply | Không phải lựa chọn chính | Có, nếu cấu hình topology/persistence đúng |
| Kafka | Có thể dùng, nhưng mô hình chính là log/partition | Rất phù hợp | Không phải mô hình request/reply chính | Không phải mô hình chính | Có, theo replication/retention/acks |
| JMS/Artemis | Phù hợp | Tùy provider/cơ chế lưu trữ | Phù hợp | Không phải mô hình chính | Có, theo broker/provider |
| RSocket | Không phải durable work queue | Không | Rất phù hợp | Rất phù hợp | Kết nối protocol; cần persistence riêng |
| HTTP/WebClient | Không tự có queue | Không | Rất phù hợp | Streaming HTTP có thể dùng cho một số tình huống | Không tự durable |

Không so sánh công nghệ chỉ bằng số lượng tính năng. Một tính năng có trong broker nhưng không được cấu hình, giám sát và test thì không phải năng lực mà hệ thống có thể dựa vào.

## 7. Lọc hard constraints trước khi chấm điểm

Tạo danh sách điều kiện loại trừ. Ví dụ:

- Phải giữ message đã accepted qua restart process.
- Consumer có thể dừng 10 phút mà producer vẫn publish.
- Có ít nhất hai consumer group độc lập cần đọc cùng event.
- Phải replay message lịch sử trong 14 ngày.
- Hệ thống chỉ được triển khai trong một vùng dữ liệu được phê duyệt.
- Chỉ dùng phiên bản thư viện còn được hỗ trợ và tương thích với Java/Spring hiện tại.

Nếu requirement bắt buộc replay 14 ngày, DirectChannel, QueueChannel và RSocket đơn lẻ bị loại ngay. Không cho điểm cao về tốc độ phát triển để bù một hard constraint bị vi phạm.

Mỗi hard gate nên có:
- Nguồn yêu cầu hoặc người chịu trách nhiệm xác nhận.
- Cách kiểm tra.
- Bằng chứng pass/fail.
- Phương án xử lý nếu chưa đáp ứng.

## 8. Chấm điểm trade-off có trọng số

Sau khi lọc hard gate, chấm các ứng viên còn lại theo cùng thang điểm.

Thang điểm gợi ý:

- 1: không phù hợp hoặc cần nhiều workaround.
- 2: đáp ứng một phần, có rủi ro đáng kể.
- 3: đáp ứng yêu cầu với một số điều kiện.
- 4: phù hợp tốt, rủi ro kiểm soát được.
- 5: phù hợp trực tiếp, có bằng chứng và đội ngũ vận hành được.

Công thức:

\[
Score = \frac{\sum (weight_i \times rating_i)}{5}
\]

Tổng trọng số bằng 100 nên kết quả nằm trong thang 0–100. Điểm chỉ có ý nghĩa khi ghi rõ giả định và bằng chứng cho từng rating. Nếu thiếu bằng chứng, đánh dấu “unknown” và thực hiện spike; đừng tự cho điểm 4 hoặc 5.

### 8.1. Ví dụ: queue xử lý lệnh fulfillment

Giả sử yêu cầu mẫu là:
- Lệnh fulfillment phải được lưu bền vững khi consumer tạm dừng.
- Nhiều worker cùng consume một queue để chia tải.
- Cần routing theo loại lệnh và priority.
- Cần retry có giới hạn, dead-letter và redelivery.
- Không cần replay toàn bộ event trong nhiều tuần.
- Đội vận hành đã có kinh nghiệm RabbitMQ và Artemis.

Hard gate loại channel nội bộ và RSocket đơn lẻ vì chúng không đáp ứng durable work queue. Ba ứng viên còn lại được chấm như sau:

| Tiêu chí | Trọng số | RabbitMQ | Kafka | JMS/Artemis |
|---|---:|---:|---:|---:|
| Durable delivery | 25 | 5 | 5 | 5 |
| Routing và competing consumers | 20 | 5 | 4 | 4 |
| Retry và dead-letter | 15 | 5 | 4 | 4 |
| Replay/retention cho use case này | 10 | 3 | 5 | 3 |
| Ordering theo key | 10 | 4 | 3 | 4 |
| Tích hợp Spring | 10 | 5 | 5 | 4 |
| Kinh nghiệm vận hành hiện có | 10 | 5 | 3 | 3 |
| **Tổng điểm mẫu** | **100** | **94** | **85** | **81** |

Các điểm trên là đánh giá minh họa theo yêu cầu giả định, không phải benchmark sản phẩm. Nếu use case chuyển sang event log cần replay dài hạn cho nhiều consumer group, trọng số replay tăng và Kafka có thể trở thành lựa chọn phù hợp hơn. Nếu tổ chức đã vận hành JMS provider ở quy mô lớn và cần interoperability với hệ thống hiện hữu, điểm vận hành/JMS compatibility cũng thay đổi.

## 9. Prototype phải kiểm tra rủi ro lớn nhất

Không cần xây toàn bộ sản phẩm để đánh giá công nghệ. Hãy xây một vertical slice nhỏ có thể làm lộ giả định rủi ro.

Một prototype messaging tối thiểu nên có:

1. Producer gửi payload đại diện, có message ID, schema version và correlation ID.
2. Transport/broker thật với topology gần production.
3. Consumer thật chạy với concurrency dự kiến.
4. Validation, idempotency và error handling.
5. Metrics/log/tracing đủ để quan sát.
6. Test restart, redelivery, duplicate, malformed payload và timeout.
7. Load test với payload và phân bố key gần thực tế.

Không chỉ benchmark một producer gửi một chuỗi ngắn vào broker trên laptop. Kết quả đó không chứng minh hệ thống production có thể đạt throughput, latency hoặc durability cần thiết.

### 9.1. Kiểm tra theo loại lựa chọn

**RabbitMQ/AMQP**
- Tạo durable exchange/queue và binding theo topology dự kiến.
- Publish persistent message và bật publisher confirms theo yêu cầu.
- Consumer ack sau khi side effect hoàn tất theo transaction boundary.
- Dừng consumer khi đang xử lý để xác nhận redelivery.
- Kiểm tra retry limit, DLQ, routing không match và publisher return.
- Kiểm tra queue type/replication khi node failure.

**Kafka**
- Chọn topic partition và key đúng với ordering requirement.
- Kiểm tra consumer group, offset commit và consumer lag.
- Restart consumer trước và sau commit để quan sát redelivery.
- Replay từ offset cũ và xác minh projection.
- Kiểm tra retention, rebalance, partition expansion và retry/DLT policy.

**JMS**
- Kiểm tra queue/topic và durable subscription.
- Kiểm tra acknowledgement mode và transaction rollback.
- Restart consumer/broker theo failure model.
- Kiểm tra provider-specific behavior và compatibility.
- Xác minh redelivery count, DLQ và listener concurrency.

**RSocket**
- Kiểm tra requester/responder interaction model.
- Đo latency và throughput với payload thực.
- Kiểm tra cancellation, backpressure, timeout, reconnect và keepalive.
- Chứng minh cách lưu message khi receiver offline nếu nghiệp vụ yêu cầu.
- Kiểm tra auth metadata, codec và error mapping.

**Spring Integration**
- Kiểm tra flow từ adapter qua channel, transformer/filter/router đến handler.
- Xác minh channel type đúng với threading và durability.
- Kiểm tra poller interval, concurrency và backlog.
- Kiểm tra error channel, retry advice và shutdown lifecycle.
- Dùng mock endpoint cho unit/flow tests và transport thật cho integration tests.

## 10. Xác định acceptance criteria trước khi chạy prototype

Các con số sau là ví dụ để minh họa cách viết tiêu chí. Khi làm dự án thật, thay bằng SLA và tải đã được owner xác nhận.

| Mục tiêu mẫu | Phương pháp kiểm chứng | Pass khi |
|---|---|---|
| 1.000 message/giây trong 15 phút | Load test với payload đại diện | Throughput ổn định, không tăng backlog liên tục |
| p95 enqueue-to-handler dưới 300 ms | Timestamp ở producer và consumer | p95 nằm trong ngưỡng ở tải mục tiêu |
| Không mất message đã được broker xác nhận trong restart test | Publish, chờ confirm, restart theo kịch bản, kiểm tra ID | Mọi ID accepted đều được xử lý hoặc nằm trong trạng thái recoverable |
| Redelivery khi consumer chết trước ack | Kill consumer giữa handler và ack | Message được giao lại và không tạo side effect trùng |
| Retry có giới hạn | Gây lỗi có chủ đích | Đúng số lần thử, backoff và chuyển DLQ |
| Schema cũ/mới tương thích | Chạy fixture contract tests | Các version được hỗ trợ đọc đúng; version không hỗ trợ bị từ chối |
| Bảo mật | Token sai, principal sai quyền, TLS sai cấu hình | Không truy cập trái phép; không lộ secret trong log |
| Khôi phục backlog | Dừng consumer rồi tạo backlog xác định | Backlog được xử lý hết trong thời hạn đã thống nhất |

Định nghĩa chính xác “accepted message” và “processed successfully”. Với RabbitMQ, cần phân biệt publisher confirm với consumer ack. Với Kafka, cần phân biệt publish acknowledgement với offset commit. Với JMS, cần nêu rõ transaction/acknowledgement mode. Nếu không định nghĩa các mốc này, test “không mất message” không có ý nghĩa.

## 11. Đọc kết quả và ra quyết định

Sau prototype, ghi kết quả theo từng tiêu chí:

| Tiêu chí | Mục tiêu | Kết quả đo | Pass/Fail | Bằng chứng |
|---|---|---|---|---|
| Throughput | 1.000 msg/s | 1.120 msg/s | Pass | Load test run 03 |
| p95 latency | <300 ms | 245 ms | Pass | Metrics export |
| Restart recovery | Không mất accepted ID | 10.000/10.000 được recover | Pass | Restart test report |
| Duplicate handling | Không tạo shipment trùng | 1 shipment/ID | Pass | DB assertion |
| DLQ | Retry tối đa 3 lần | 3 lần rồi DLQ | Pass | Broker trace |
| Ops readiness | Dashboard và alert | Thiếu alert queue age | Fail | Ops review |

Không bỏ qua một tiêu chí fail chỉ vì tổng điểm vẫn cao. Có thể:
- Sửa cấu hình và chạy lại test.
- Thay đổi kiến trúc để đáp ứng requirement.
- Chọn ứng viên khác.
- Xin owner thay đổi requirement với lý do và ảnh hưởng được ghi lại.

Kết quả prototype chỉ có giá trị trong điều kiện đã thử. Ghi rõ broker version, topology, hardware, payload size, concurrency, network, JVM flags, Spring versions và test duration. Nếu các điều kiện khác production, ghi giới hạn đó trong kết luận.

## 12. Từ kết quả kiểm chứng đến cấu hình Spring

Giả sử prototype chọn RabbitMQ cho work queue và Spring Integration điều phối flow.

Phân chia trách nhiệm:

- Spring Integration: nhận message vào flow, transform, validate, route và gọi handler.
- Spring AMQP: kết nối RabbitMQ, convert payload, publish và consume.
- RabbitMQ: exchange, queue, binding, delivery, ack/confirm và broker-side routing.
- Domain service: idempotency, transaction và quy tắc nghiệp vụ.
- Observability: đo publish confirm, queue depth/age, redelivery, DLQ và handler latency.

Ví dụ flow dưới đây là cấu hình minh họa; cần có ConnectionFactory, AmqpTemplate, exchange, routing key và topology được khai báo trước:

~~~java
@Bean
IntegrationFlow publishFulfillment(AmqpTemplate amqpTemplate) {
    return IntegrationFlow.from("orders.ready")
        .filter(OrderReady.class, order -> order.orderId() != null)
        .handle(Amqp.outboundAdapter(amqpTemplate)
            .exchangeName("orders.events")
            .routingKey("orders.fulfillment"))
        .get();
}
~~~

Consumer có thể dùng inbound channel adapter hoặc Spring AMQP listener để nhận queue, rồi chuyển vào flow nội bộ. Chọn adapter hay listener trực tiếp dựa trên mức độ phức tạp của flow. Nếu chỉ có một handler, không cần thêm tầng integration flow chỉ để có thêm abstraction.

Khi triển khai thật:
- Khai báo exchange, queue, binding và policy bằng infrastructure as code.
- Đặt persistent delivery mode, publisher confirms/returns và consumer acknowledgement phù hợp.
- Cấu hình prefetch/concurrency theo throughput và thời gian xử lý.
- Đặt retry limit, backoff, DLQ và alert.
- Giữ message ID ổn định qua retry và xử lý idempotent.
- Không coi transaction database và broker tự động là một distributed transaction nguyên tử.
- Dùng outbox/inbox khi cần tránh khoảng trống giữa commit database và publish/consume.

## 13. Kiểm thử kết quả bằng Java 17: weighted decision scorer

Ví dụ độc lập sau tính điểm có trọng số từ các rating đã được nhóm đánh giá. Nó không benchmark broker; nó làm cho cách chấm điểm minh bạch và lặp lại được.

Tạo file **TechnologyDecisionDemo.java**:

~~~java
import java.util.List;

public class TechnologyDecisionDemo {

    record Criterion(String name, int weight) {}

    record Candidate(String name, List<Integer> ratings) {}

    public static void main(String[] args) {
        List<Criterion> criteria = List.of(
            new Criterion("Durable delivery", 25),
            new Criterion("Routing and workers", 20),
            new Criterion("Retry and dead-letter", 15),
            new Criterion("Replay fit", 10),
            new Criterion("Ordering by key", 10),
            new Criterion("Spring integration", 10),
            new Criterion("Operations fit", 10)
        );

        List<Candidate> candidates = List.of(
            new Candidate("RabbitMQ / Spring AMQP",
                List.of(5, 5, 5, 3, 4, 5, 5)),
            new Candidate("Kafka / Spring Kafka",
                List.of(5, 4, 4, 5, 3, 5, 3)),
            new Candidate("JMS / Artemis",
                List.of(5, 4, 4, 3, 4, 4, 3))
        );

        int totalWeight = criteria.stream()
            .mapToInt(Criterion::weight)
            .sum();

        if (totalWeight != 100) {
            throw new IllegalStateException("Weights must sum to 100");
        }

        for (Candidate candidate : candidates) {
            if (candidate.ratings().size() != criteria.size()) {
                throw new IllegalArgumentException("Rating count mismatch");
            }

            int weightedTotal = 0;
            for (int i = 0; i < criteria.size(); i++) {
                int rating = candidate.ratings().get(i);
                if (rating < 1 || rating > 5) {
                    throw new IllegalArgumentException("Rating must be 1..5");
                }
                weightedTotal += criteria.get(i).weight() * rating;
            }

            int score = weightedTotal / 5;
            System.out.println(candidate.name() + " = " + score + "/100");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TechnologyDecisionDemo.java
java TechnologyDecisionDemo
~~~

Output:

~~~text
RabbitMQ / Spring AMQP = 94/100
Kafka / Spring Kafka = 85/100
JMS / Artemis = 81/100
~~~

Chương trình kiểm tra tổng trọng số bằng 100 và rating nằm trong khoảng 1–5. Nó chưa thực hiện hard gate; hard gate phải được đánh giá trước khi đưa ứng viên vào danh sách. Điểm số là hỗ trợ thảo luận, không phải bằng chứng hiệu năng hoặc bảo đảm chất lượng.

## 14. Ghi quyết định bằng Architecture Decision Record (ADR)

Mỗi quyết định quan trọng nên có một ADR ngắn, đủ để người khác hiểu tại sao chọn và điều gì khiến quyết định thay đổi.

Mẫu:

~~~markdown
# ADR-00X: Chọn transport cho luồng fulfillment

- Status: Proposed / Accepted / Superseded
- Date:
- Owners:
- Related requirements:
- Review date:

## Context
Mô tả vấn đề, tải, SLA, failure model, consumer và hệ thống liên quan.

## Decision drivers
Liệt kê hard constraints và tiêu chí có trọng số.

## Options considered
RabbitMQ, Kafka, JMS/Artemis, RSocket hoặc lựa chọn khác.

## Decision
Nêu transport, broker, Spring adapter/framework và interaction pattern.

## Evidence
Link prototype, load test, restart test, security test, contract test và ops review.

## Consequences
Chi phí vận hành, retry semantics, retention, ordering, security và giới hạn còn lại.

## Revisit when
Điều kiện làm quyết định cần được đánh giá lại.
~~~

ADR không phải tài liệu quảng bá công nghệ. Ghi cả nhược điểm và rủi ro còn tồn tại. Nếu quyết định thay đổi, tạo ADR mới và liên kết ADR cũ; không viết lại lịch sử như thể lựa chọn hiện tại luôn là lựa chọn ban đầu.

## 15. Triển khai có kiểm soát và xác minh sau phát hành

Sau khi prototype pass, vẫn cần rollout có kiểm soát:

1. Hoàn thiện infrastructure as code, secret, TLS, queue/topic policy và alert.
2. Deploy consumer trước nếu consumer cần hiểu schema mới.
3. Bật producer theo canary hoặc traffic nhỏ.
4. Theo dõi publish error, confirm latency, consumer lag/queue age, redelivery, DLQ, handler p95/p99 và resource usage.
5. Tăng traffic theo từng bước khi số liệu ổn định.
6. Kiểm thử restart/failover và replay theo runbook đã duyệt.
7. Xác minh business outcome, ví dụ số shipment tạo thành công và số order bị trùng.
8. Lưu số liệu thực tế để so với acceptance criteria.

Nếu phải migrate giữa hai transport, định nghĩa cách tránh dual-write không nhất quán. Transactional outbox, bridge có idempotency hoặc một giai đoạn cutover có kiểm soát thường an toàn hơn việc publish độc lập sang hai broker từ hai đoạn code khác nhau.

### 15.1. Dấu hiệu cần xem xét lại lựa chọn

- Queue age hoặc consumer lag tăng liên tục dù đã scale hợp lý.
- Chi phí retention/storage vượt kế hoạch.
- Cần replay thường xuyên nhưng transport hiện tại không hỗ trợ thuận tiện.
- Nhiều hệ thống phải tự xây workaround cho routing, retry hoặc ordering.
- Broker hoặc thư viện hết thời gian hỗ trợ.
- Sự cố vận hành thường xuyên vượt khả năng của đội ngũ.
- Requirement bảo mật, vùng dữ liệu hoặc compliance thay đổi.
- Workload thực tế khác xa tải prototype.

Không thay công nghệ chỉ vì có sản phẩm mới. Cần xác định requirement nào đã thay đổi và bằng chứng nào cho thấy lựa chọn cũ không còn phù hợp.

## 16. Lỗi thường gặp khi rà soát công nghệ

1. **Chọn sản phẩm trước khi mô tả yêu cầu.** Dễ biến mọi bài toán thành use case phù hợp với công nghệ quen thuộc.
2. **Nhầm framework với broker.** Spring Integration điều phối flow; broker đảm nhận lưu trữ/phân phối theo semantics riêng.
3. **Chấm điểm trước hard gate.** Một lựa chọn điểm cao nhưng không đáp ứng durability/security vẫn phải bị loại.
4. **Dùng benchmark không đại diện.** Payload nhỏ, một producer và một consumer không phản ánh workload production.
5. **Không test lỗi.** Happy path không chứng minh redelivery, recovery, idempotency hoặc DLQ.
6. **Dựa vào từ “exactly-once”.** Phải định nghĩa phạm vi, transaction và side effect; message ID đơn lẻ không tạo exactly-once.
7. **Bỏ qua ordering.** Queue/partition/concurrency/redelivery có thể làm thứ tự quan sát khác mong đợi.
8. **Không đo vận hành.** Thiếu queue age, lag, retry count và DLQ alert làm hệ thống khó phục hồi.
9. **Chọn version không tương thích.** Cần kiểm tra ma trận Java, Spring Boot, Spring Integration, Spring AMQP/Kafka/JMS và broker.
10. **Không ghi lại giả định.** Người đọc ADR sau này không biết điểm số được chấm dựa trên workload nào.
11. **Không xác minh sau rollout.** Prototype pass không bảo đảm production behavior khi topology, network và tải khác nhau.

## 17. Checklist rà soát từ yêu cầu đến kết quả

### Yêu cầu
- [ ] Có owner xác nhận functional và non-functional requirements.
- [ ] Có throughput, latency, retention, availability và recovery target.
- [ ] Có interaction model, consumer topology và ordering requirement.
- [ ] Phân biệt hard constraints với preferences.

### Kiến trúc và lựa chọn
- [ ] Phân biệt message contract, pattern, transport, broker và integration framework.
- [ ] Đã chọn shortlist phù hợp và ghi lý do loại các ứng viên khác.
- [ ] Hard gates đã được kiểm tra trước weighted score.
- [ ] Có compatibility check cho Java, Spring và broker/client version.

### Prototype và kiểm chứng
- [ ] Prototype dùng payload, topology và concurrency gần production.
- [ ] Có test happy path, timeout, restart, redelivery, duplicate và malformed message.
- [ ] Có load test, security test và schema/contract test.
- [ ] Có metrics/log/trace để chứng minh kết quả.
- [ ] Mọi acceptance criteria có pass/fail và evidence link.

### Quyết định và vận hành
- [ ] ADR ghi context, options, decision, consequences và revisit conditions.
- [ ] Có runbook cho retry, DLQ, replay, restart và failover.
- [ ] Có dashboard/alert cho backlog, lag, errors và latency.
- [ ] Có kế hoạch rollout/cutover và kiểm chứng business outcome sau phát hành.

## Tài liệu tham khảo

- [Spring Boot — Messaging](https://docs.spring.io/spring-boot/reference/messaging/index.html): các tích hợp JMS, AMQP/RabbitMQ, Kafka, Pulsar và STOMP.
- [Spring Boot — Spring Integration](https://docs.spring.io/spring-boot/reference/messaging/spring-integration.html): starter, auto-configuration, poller và các module transport của Spring Integration.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-flows.html): xây dựng IntegrationFlow và kết nối các flow qua MessageChannel.
- [Spring Integration — AMQP Support](https://docs.spring.io/spring-integration/reference/7.1/amqp.html): inbound/outbound channel adapter, gateway và AMQP-backed channel.
- [Spring Integration — AMQP-backed Channels](https://docs.spring.io/spring-integration/reference/7.1-SNAPSHOT/amqp/channels.html): phân biệt point-to-point, publish-subscribe và mục đích persistence của channel.
- [Spring for Apache Kafka — Reference](https://docs.spring.io/spring-kafka/reference/kafka.html): producer, listener, partition/offset, transactions, serialization, monitoring và error handling.
- [Spring for Apache Kafka — Project and Compatibility](https://spring.io/projects/spring-kafka): tính năng và ma trận tương thích Spring Kafka, Spring Integration for Kafka, Kafka client và Spring Boot.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): interaction model, codec, RSocketRequester và server auto-configuration.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): hai cơ chế xác nhận độc lập và các giới hạn cần hiểu khi kiểm chứng delivery.
- [Spring AMQP — Request/Reply](https://docs.spring.io/spring-amqp/reference/amqp/request-reply.html): request/reply và publisher confirms trong Spring AMQP.
