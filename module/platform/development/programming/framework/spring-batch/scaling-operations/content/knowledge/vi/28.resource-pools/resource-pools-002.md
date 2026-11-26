# Connection pool của middleware khi mở rộng Spring Batch

## 1. Vì sao cần quan tâm đến pool kết nối?

Một job Spring Batch xử lý hàng triệu bản ghi có thể đọc dữ liệu từ database, gửi sự kiện sang RabbitMQ/Kafka, cập nhật Redis, gọi HTTP API hoặc nhận công việc từ một message broker. Khi tăng từ một worker lên nhiều thread, partition hoặc máy xử lý, số thao tác tới **middleware** cũng tăng. Nếu không quản lý kết nối, job có thể mất thời gian tạo kết nối liên tục, chạm giới hạn broker hoặc chờ tài nguyên lâu hơn thời gian xử lý dữ liệu.

Trong chương **Resource pool** của module `SPRING_BATCH_SCALING_OPERATIONS`, bài học này tập trung vào **connection pool của middleware**: cách tái sử dụng kết nối hoặc tài nguyên phiên làm việc, tính giới hạn concurrency, đo điểm nghẽn và bảo đảm retry/restart an toàn khi scale Spring Batch. Phạm vi bao gồm multi-threaded step, parallel steps, partitioning cục bộ và các kiến trúc batch phân tán.

Sau bài học, bạn có thể:

- Nhận biết middleware nào dùng pool kết nối TCP, middleware nào chủ yếu tái sử dụng channel/session hoặc dùng client có kết nối nội bộ.
- Ước lượng quy mô pool từ số worker đồng thời, số request đang bay và giới hạn của phía server.
- Cấu hình ví dụ pool channel với Spring AMQP và hiểu tại sao `cache size` khác `hard limit`.
- Phân biệt timeout chờ lấy kết nối với timeout gửi/nhận, đồng thời xử lý quá tải bằng backpressure.
- Phân tích tác động của pool lên transaction, retry, restart, idempotency và metric vận hành.

> **Khái niệm:** Pool là cơ chế giữ và cho mượn lại tài nguyên đắt đỏ như connection, channel, session hoặc HTTP connection. Không phải thư viện middleware nào cũng có khái niệm `borrow/return` giống HikariCP của JDBC. Phải hiểu đúng client đang quản lý tài nguyên nào.

## 2. Phân biệt TCP connection, channel, session và client

Khi nói “tăng pool lên 32”, cần trả lời trước: **32 tài nguyên gì?**

| Middleware/client | Đơn vị thường được quản lý | Lưu ý về concurrency |
|---|---|---|
| **RabbitMQ với Spring AMQP** | Một hoặc vài TCP connection được tái sử dụng; `CachingConnectionFactory` cache các AMQP **channel** | `RabbitTemplate` thường được chia sẻ; channel không nên dùng đồng thời bởi nhiều thread. Channel cache không luôn là giới hạn tối đa. |
| **JMS** | Physical connection, `Session`, producer/consumer tùy provider | `Session` nói chung không thread-safe; Spring JMS có `CachingConnectionFactory` cache session theo chế độ sử dụng. |
| **Kafka Java client** | Producer/consumer tự quản lý kết nối đến broker | `KafkaProducer` hỗ trợ gọi từ nhiều thread; `KafkaConsumer` không thread-safe. Không tạo “pool KafkaProducer/Consumer” theo thói quen JDBC. |
| **Redis (Lettuce/Jedis)** | Lettuce có thể chia sẻ native connection cho lệnh thường; Jedis thường borrow connection từ pool | Lệnh blocking, transaction hoặc thao tác có trạng thái có thể cần connection riêng. |
| **HTTP client** | Pool kết nối keep-alive tới từng host/route | Cần xét cả `max total`, `max per route`, thời gian chờ borrow và timeout request. |

Ví dụ, 12 AMQP channel trên **một TCP connection** không tương đương 12 TCP connection. Chỉ số cần giám sát ở RabbitMQ gồm cả số connections và số channels; với HTTP có thể phải xem số connection tới từng hostname.

### Luồng tài nguyên khi một partition gửi dữ liệu ra middleware

~~~mermaid
flowchart LR
    J[Spring Batch job] --> M[Manager hoặc parallel flow]
    M --> W1[Worker 1]
    M --> W2[Worker 2]
    M --> W3[Worker N]
    W1 --> C[Client dùng chung: RabbitTemplate/HTTP]
    W2 --> C
    W3 --> C
    C --> P[Pool/cache: borrow và release]
    P --> B[Broker hoặc API gateway]
    W1 --> D[Database và JobRepository]
    W2 --> D
    W3 --> D
~~~

Mỗi worker có thể giữ tài nguyên từ nhiều hệ thống cùng lúc: connection tới database, AMQP channel, HTTP connection, bộ nhớ chứa chunk và thread thực thi. Khi một thành phần bị bão hòa, các worker có thể chờ dây chuyền. Vì vậy, tăng số thread mà không kiểm tra giới hạn của các pool liên quan có thể khiến job **chậm hơn**.

## 3. Pool hoạt động ra sao và khi nào gây nghẽn?

Một pool thường có ba trạng thái logic:

1. **Idle:** tài nguyên đã tạo và đang rảnh, có thể dùng lại.
2. **In use/active:** tài nguyên được worker hoặc client giữ để thực hiện thao tác.
3. **Pending/waiting:** yêu cầu cần tài nguyên nhưng pool đã chạm giới hạn; caller chờ đến khi có tài nguyên hoặc hết thời gian chờ.

Một request thành công đi qua chuỗi:

~~~text
worker lấy tài nguyên -> thực hiện I/O -> trả tài nguyên
                         |
                         +-- timeout/lỗi mạng -> xử lý lỗi -> đóng/hủy tài nguyên hỏng
~~~

Tùy client, việc mượn và trả có thể được thực hiện bên trong `RabbitTemplate` hoặc HTTP client, chứ không xuất hiện trong code của worker. Ngược lại, khi tự gọi một API cấp tài nguyên dạng `Session` hoặc `Channel`, code phải tôn trọng vòng đời close/return mà thư viện quy định.

Các thời hạn khác nhau cần cấu hình riêng:

| Timeout | Đo khoảng thời gian nào? | Khi hết hạn |
|---|---|---|
| **Pool acquisition/checkout timeout** | Chờ có tài nguyên rảnh trong pool | Fail fast hoặc báo quá tải ở client; không có nghĩa broker đã từ chối message. |
| **Connect timeout** | Thiết lập socket/connection tới server | Chẩn đoán mạng, DNS, firewall hoặc server không sẵn sàng. |
| **Read/response timeout** | Chờ phản hồi sau khi kết nối đã thiết lập | Có thể đã gửi yêu cầu nhưng chưa biết server xử lý thành công hay chưa. |
| **Shutdown/drain timeout** | Đợi các tác vụ đang chạy hoàn thành khi dừng job/app | Cần phối hợp stop step và ứng dụng để tránh bỏ dở công việc. |

**Không dùng timeout cực dài để che dấu thiếu capacity.** Khi mọi worker xếp hàng chờ pool, heap và số thread bị giữ tăng; job mất khả năng phản hồi khi cần stop/restart. Ưu tiên deadline hữu hạn, hàng đợi có giới hạn và tín hiệu lỗi rõ ràng.

## 4. Tính kích thước pool từ workload thực tế

Không có một con số đúng cho mọi hệ thống. Một mô hình bắt đầu dễ dùng là:

- `P`: số worker thực sự chạy đồng thời (có thể nhỏ hơn số partition).
- `K`: số thao tác tới middleware **đồng thời** tối đa trong một worker.
- `R`: lượng tài nguyên dành cho listener, tác vụ quản trị, health check và khoảng dự phòng, tính trong cùng đơn vị.

Với middleware có cơ chế mượn tài nguyên theo mỗi thao tác, ước lượng đỉnh ban đầu:

\[
C_{\text{candidate}} \approx P \times K + R
\]

Ví dụ, manager chia 24 partition nhưng executor chỉ chạy tối đa 8 worker. Nếu mỗi worker gọi `RabbitTemplate` **tuần tự** trong một vòng lặp, `K = 1`; thêm 4 channel dự phòng, có thể thử cấu hình giới hạn **12–16 channel** rồi đo. `chunk(500)` không có nghĩa cần 500 channel: 500 item trong một chunk vẫn có thể được gửi tuần tự từ một thread.

Nếu worker tự mở nhiều thao tác bất đồng bộ cùng lúc, `K` sẽ lớn hơn 1; phải đo số operation *in-flight* thực tế thay vì giả định một channel cho mỗi worker trong mọi trường hợp.

### Dùng Little's Law để kiểm tra chéo

Với hệ thống tương đối ổn định, mức concurrency trung bình xấp xỉ:

\[
L = \lambda \times W
\]

Trong đó `λ` là số yêu cầu hoàn thành mỗi giây và `W` là thời gian trung bình một yêu cầu giữ tài nguyên (giây). Nếu throughput 120 request/giây và thời gian giữ channel trung bình 0,05 giây, ta có `L ≈ 6` request in-flight. Đây chỉ là **trung bình**, chưa phản ánh burst, đuôi p95/p99, retry hoặc thời gian dừng broker. Không chọn giới hạn pool chỉ dựa trên `L`.

### Giới hạn phải tính trên toàn cụm

Giả sử có ba instance ứng dụng, mỗi instance giữ tối đa 16 channel, thì toàn cụm có thể dùng tới **48 channel** cho chức năng đó (chưa tính listener và ứng dụng khác). Nếu mặc định mỗi instance dùng một shared AMQP TCP connection, điều đó vẫn không đồng nghĩa 48 connection TCP.

Hãy lập ngân sách theo **đúng loại tài nguyên mà server giới hạn**: số TCP connection, channel trên mỗi connection, số session/consumer, request in-flight, throughput hay quota API. Từ ngân sách server, trừ tài nguyên mà các dịch vụ khác và công việc vận hành cần sử dụng trước khi chia phần cho các batch instance.

## 5. Ví dụ Spring AMQP: cache channel phục vụ nhiều worker

Giả sử một Spring Batch job chia đơn hàng thành nhiều partition và mỗi worker phát sự kiện tới RabbitMQ. Với Spring Boot 3.x và Spring AMQP, có thể cấu hình qua `application.yml`:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5672
    username: batch-publisher
    password: ${RABBIT_PASSWORD}
    cache:
      channel:
        size: 16
        checkout-timeout: 2s
~~~

Các thuộc tính trên cấu hình `CachingConnectionFactory` do Spring Boot tạo khi dùng starter AMQP phù hợp. Ở chế độ mặc định `CacheMode.CHANNEL`:

- Client thường sử dụng một shared physical connection và quản lý cache các AMQP channel.
- `size: 16` quy định kích thước channel cache. **Nếu không có checkout timeout dương**, đây chủ yếu là số channel nhàn rỗi được giữ lại; client vẫn có thể tạo thêm channel vượt giá trị cache khi cần.
- `checkout-timeout: 2s` làm kích thước cache hoạt động như **giới hạn channel được cấp đồng thời trên một connection** trong chế độ này; caller có thể chờ rồi nhận lỗi nếu hết thời hạn.
- Cấu hình giới hạn channel phải được đối chiếu với hạn mức của broker, cấu hình publisher/consumer, cache mode và số instance ứng dụng.

> Nếu ứng dụng dùng nhiều connection, publisher connection chuyên biệt hoặc cache mode khác, số giới hạn phải tính cho từng nhóm tài nguyên tương ứng. Không suy rằng mọi ứng dụng Spring AMQP đều có duy nhất một TCP connection.

Trong Spring Batch 5, một `ItemWriter` có thể gửi message bằng `RabbitTemplate` được Spring quản lý:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.stereotype.Component;

@Component
public class OrderEventWriter implements ItemWriter<Long> {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventWriter(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @Override
    public void write(Chunk<? extends Long> chunk) {
        for (Long orderId : chunk.getItems()) {
            rabbitTemplate.convertAndSend(
                "batch.events",      // exchange đã được khai báo
                "order.processed",   // routing key
                "orderId=" + orderId
            );
        }
    }
}
~~~

Trong ví dụ, `OrderEventWriter` có thể được dùng bởi nhiều `StepExecution` nếu component và client được dùng theo contract thread-safety của Spring. `RabbitTemplate` quản lý việc lấy/trả channel thông qua connection factory; **không lưu một đối tượng `Channel` lấy thủ công vào field singleton rồi chia sẻ cho các thread**.

Để ví dụ có thể gửi thành công, phía broker phải có exchange `batch.events` và binding/queue tương ứng, cùng quyền publish cho tài khoản ứng dụng. Việc định nghĩa exchange, listener và serialization phụ thuộc hệ thống; code trên dùng payload `String` để tránh phụ thuộc cấu hình JSON converter.

**Điểm an toàn dữ liệu:** `convertAndSend` chỉ minh họa thao tác dùng pool. Nó không làm cho transaction của Spring Batch và việc publish lên RabbitMQ trở thành một transaction nguyên tử. Nếu một chunk rollback sau khi message đã gửi, worker có thể gửi lặp khi retry/restart. Đối với event nghiệp vụ quan trọng, nên dùng **transactional outbox**, message ID ổn định, consumer idempotent và cơ chế publisher confirms phù hợp.

### Với remote chunking hoặc worker tiêu thụ từ queue

Khi RabbitMQ còn được dùng để **nhận** công việc, consumer concurrency và prefetch trở thành phần của ngân sách middleware, không chỉ channel publish. Ví dụ:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        concurrency: 4
        max-concurrency: 8
        prefetch: 20
~~~

Đây là cấu hình minh họa cho `SimpleRabbitListenerContainerFactory` khi ứng dụng sử dụng cơ chế listener tương ứng. Với 8 consumer đang hoạt động và prefetch 20, tối đa khoảng **160 message chưa ACK** có thể được phân phối cho nhóm consumer đó, tùy tình trạng hàng đợi và cách broker cấp phát. Điều này ảnh hưởng đến bộ nhớ, độ công bằng và thời gian phục hồi khi một worker lỗi. Prefetch không đồng nghĩa số thread hay số connection.

Trong remote partitioning/remote chunking, cũng cần ngân sách cho consumer ở các worker process khác, retry queue, reply channel và lưu lượng acknowledgment. Không áp đặt một pool size cho cả nơi publish lẫn nơi consume chỉ vì cả hai đều dùng RabbitMQ.

## 6. Cách tiếp cận khác nhau ở JMS, Kafka, Redis và HTTP

### JMS: cache session, không chia sẻ session tùy ý

Một `Connection` JMS thường đắt hơn việc tạo và dùng lại `Session`. Spring JMS cung cấp `CachingConnectionFactory` để tái sử dụng session, producer/consumer theo chính sách cache. `JmsTemplate` là API thuận tiện cho caller; `Session` thông thường không an toàn nếu nhiều thread cùng thao tác trực tiếp.

Ví dụ minh họa cấu hình khi **đã có** bean `vendorJmsConnectionFactory` từ provider:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.connection.CachingConnectionFactory;

@Bean
CachingConnectionFactory batchJmsConnectionFactory(
        @Qualifier("vendorJmsConnectionFactory") ConnectionFactory target) {
    CachingConnectionFactory cached = new CachingConnectionFactory(target);
    cached.setSessionCacheSize(8);
    return cached;
}
~~~

`sessionCacheSize` là số session được **cache theo từng chế độ acknowledge/transaction** của Spring JMS, không nên hiểu giản lược thành số session tồn tại tối đa trong toàn hệ thống. Hành vi thực tế còn phụ thuộc provider và loại listener container. Dùng một session cố định cho nhiều thread hoặc cache consumer tùy tiện với selector/destination động có thể gây vấn đề; cần kiểm tra mô hình nhận message của ứng dụng.

### Kafka: điều chỉnh producer/consumer, không mặc định dựng pool

- `KafkaProducer` được thiết kế để dùng từ nhiều thread, giữ buffer và kết nối mạng bên trong. Nhiều producer instance không tự động tăng throughput; chúng có thể nhân thêm buffer và số connection.
- `KafkaConsumer` không thread-safe, nên listener concurrency thường tạo consumer riêng cho từng luồng xử lý. Số consumer thực sự nhận dữ liệu trong cùng consumer group còn bị giới hạn bởi số partition topic.
- Các tham số như `buffer.memory`, `batch.size`, `linger.ms`, `max.in.flight.requests.per.connection` và `max.poll.records` có mục đích khác nhau; **`max.in.flight.requests.per.connection` không phải kích thước connection pool**.
- Theo dõi producer buffer exhaustion, request latency, consumer lag, rebalance, độ trễ commit offset và số kết nối tới broker. Tăng concurrency khi phân vùng dữ liệu/topic, CPU và network đủ sức.

### Redis: hiểu đặc tính của driver trước khi bật pool

- Với **Lettuce**, kết nối native có thể multiplex nhiều lệnh thông thường, và Spring Data Redis thường tận dụng chia sẻ kết nối trong những trường hợp thích hợp. Việc bật pool cho tất cả thao tác có thể tăng số kết nối mà không cải thiện tốc độ.
- Với **Jedis**, pool connection thường là một phần quan trọng của quản lý concurrency: cần giới hạn max active, max wait và trả connection đúng vòng đời.
- Lệnh blocking, transaction, pub/sub hoặc API yêu cầu trạng thái kết nối riêng cần được xem xét tách biệt với lệnh Redis thường. Theo dõi saturation, latency và cấu hình của Redis server.

### HTTP: pool theo route/host và kiểm soát deadline

Với job gọi REST API theo chunk hoặc partition, HTTP client có keep-alive pool thường tiết kiệm công tạo TCP/TLS connection. Tuy nhiên:

| Thiết lập | Ý nghĩa |
|---|---|
| Max connections total | Giới hạn tổng connection mà HTTP client quản lý. |
| Max connections per route/host | Giới hạn kết nối đồng thời đến cùng đích; một API duy nhất có thể chạm trần này trước trần tổng. |
| Connection-request timeout | Thời gian đợi lấy một connection từ pool. |
| Connect/response timeout | Giới hạn kết nối mạng và chờ phản hồi từ API. |
| Max idle/lifetime/eviction | Giảm sử dụng connection chết hoặc quá cũ khi load balancer/NAT đóng kết nối. |

Nếu API áp quota 100 request/giây, pool 100 connection không cho phép vượt quota đó. Cần thêm **rate limiter**, backoff có jitter, giới hạn request in-flight và xử lý `429 Too Many Requests`/`Retry-After` nếu server cung cấp.

## 7. Pool, transaction và khả năng restart của Spring Batch

### Một chunk có thể giữ nhiều tài nguyên cùng lúc

Hãy tưởng tượng worker đang thực hiện:

1. Mở transaction database để đọc và ghi trạng thái chunk.
2. Gửi một số message hoặc gọi HTTP khi transaction DB vẫn mở.
3. Gặp tình trạng middleware pool cạn, chờ 2 giây để mượn channel.
4. Trong lúc chờ, transaction và connection DB vẫn có thể bị giữ, làm tăng lock wait và áp lực lên DB pool.

Đây là một dạng **giữ chéo tài nguyên**. Tăng pool JDBC không luôn chữa được khi nguyên nhân gốc là middleware nghẽn. Một số hướng xử lý là rút ngắn thời gian giữ transaction, giới hạn đồng thời theo middleware, ghi outbox trong transaction rồi phát message sau, và tách stage khi phù hợp.

### Retry có thể nhân tải đúng lúc hệ thống quá tải

Khi pool hết tài nguyên, tất cả worker cùng retry ngay có thể tạo **retry storm**: thêm yêu cầu vào cùng tài nguyên đang nghẽn. Nên kết hợp:

- Timeout borrow hữu hạn và queue/executor có giới hạn.
- Retry cho lỗi tạm thời, số lần retry giới hạn; exponential backoff kèm jitter nếu các worker có khả năng lỗi đồng thời.
- Phân biệt lỗi timeout **trước khi gửi** và timeout **sau khi gửi**: trường hợp sau có thể không biết broker/API đã nhận công việc hay chưa.
- Message ID/khóa nghiệp vụ cố định khi retry; deduplication hoặc outbox/inbox với tác vụ không thể gửi hai lần.
- Circuit breaker, rate limiter hoặc giảm concurrency khi phía middleware báo quá tải kéo dài.

**Restart của Spring Batch** khôi phục tiến độ theo `JobRepository` và `ExecutionContext` của các step/partition. Nó không tự xác nhận một message đã đến broker hay một HTTP request đã được xử lý. Nếu cần cam kết nghiệp vụ chính xác, phải thiết kế biên giới transaction và cơ chế đối soát riêng.

### Tránh tạo pool theo từng partition

Thông thường nên tạo client, connection factory hoặc HTTP pool dưới dạng **singleton do container Spring quản lý**. Các reader/processor có state theo partition mới là đối tượng cần cân nhắc `@StepScope`. Nếu mỗi trong 100 partition tạo một connection factory và pool 16 tài nguyên, ứng dụng có nguy cơ tạo tới 1.600 tài nguyên thay vì cùng chia sẻ ngân sách theo process.

Quy tắc áp dụng:

- Chia sẻ **client/factory** khi thư viện cho phép và bảo đảm vòng đời qua Spring.
- Tạo riêng **đối tượng không thread-safe hoặc có trạng thái phiên**, như một JMS `Session` hay Kafka `Consumer`, theo cách framework hỗ trợ.
- Không giữ kết nối/channel mượn từ pool xuyên suốt cả job khi chỉ cần dùng trong từng thao tác ngắn.
- Khi dừng ứng dụng, đóng client/pool có kiểm soát sau khi giảm hoặc ngừng nhận công việc mới.

## 8. Đo hiệu năng và phát hiện nút thắt

Với cùng dữ liệu và điều kiện kiểm thử, hãy chạy baseline một worker, sau đó tăng concurrency theo mức 2, 4, 8 rồi so sánh. Cần đo **thời gian hoàn thành job và độ đúng của kết quả**, thay vì chỉ nhìn số lượng thread.

| Phạm vi | Chỉ số nên thu thập | Cách diễn giải |
|---|---|---|
| Spring Batch | Job/step duration, worker active, throughput, `readCount`, `writeCount`, skip/retry/rollback | Throughput không tăng tương ứng khi thêm worker là tín hiệu cần tìm bottleneck. |
| Middleware pool | Active/idle resources, pending requests, p95/p99 acquisition wait, timeout/exhaustion count | Wait tăng dù broker còn khỏe có thể do pool phía client quá nhỏ. |
| RabbitMQ/JMS/Kafka | Connections/channels/sessions, publish latency, confirms/nacks, queue depth, unacked count/consumer lag | Phân biệt broker quá tải với client không đủ tài nguyên. |
| HTTP/Redis | Client in-flight, pool per route, response p95/p99, 429/5xx, server latency | Nếu API đang rate-limit, tăng pool thường làm lỗi nhiều hơn. |
| JVM và executor | CPU, heap, GC pause, active/queued/rejected tasks | Thread đang chờ I/O không đồng nghĩa thiếu CPU. |
| Database | HikariCP active/pending, lock wait, slow SQL, connection timeout | Middleware nghẽn có thể kéo dài thời gian giữ connection DB. |
| Nghiệp vụ | Số item kỳ vọng/đã xử lý, message ID trùng, event bị thiếu | Pool hoạt động “đúng” chưa đủ để khẳng định kết quả batch đúng. |

Ví dụ cách đánh giá:

| Đo được | Khả năng xảy ra | Thử nghiệm tiếp |
|---|---|---|
| Pool pending cao, broker còn nhiều capacity, retry thấp | Pool client có thể là nút thắt | Tăng giới hạn pool từng bước hoặc rút ngắn thời gian giữ tài nguyên. |
| Pool pending thấp, broker CPU/queue/latency tăng mạnh | Broker hoặc downstream bão hòa | Giảm concurrency, tối ưu broker/topology, chia tải. |
| Worker active cao, HikariCP pending tăng, transaction lâu | Giữ connection DB trong khi chờ middleware | Đo thời gian transaction, thử outbox/tách giai đoạn I/O. |
| Tăng pool nhưng throughput đứng yên, timeout tăng | Vượt năng lực server/quota hoặc lỗi mạng | Giữ pool nhỏ hơn, đo p99 và limit thực tế. |
| Partition hoàn thành không đều, middleware pool nhàn | Chia partition lệch tải hoặc nguồn dữ liệu có skew | Cân bằng phân vùng và chi phí mỗi item. |

Một số hệ thống không cung cấp trực tiếp metric “active vs idle” đúng loại tài nguyên. Có thể dùng metric do client/driver hỗ trợ, số liệu broker, `CachingConnectionFactory.getCacheProperties()` (đọc theo phiên bản Spring AMQP) và timer/counter tự instrument quanh thao tác gửi để xác định nơi chờ. **Không đồng nhất “thời gian gửi message” với “thời gian chờ lấy channel”** nếu chưa tách được các thành phần trong đo lường.

## 9. Sự cố thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân hay gặp | Hướng xử lý |
|---|---|---|
| Lỗi chờ mượn channel/session/connection | Pool đã chạm giới hạn, caller giữ tài nguyên quá lâu | Xem active/pending, leak, timeout và số worker; tăng pool có kiểm soát nếu broker còn capacity. |
| Broker báo chạm connection/channel limit | Quá nhiều app instance, pool theo partition, leak hoặc reconnect liên tục | Đếm tổng tài nguyên toàn cụm; dùng singleton factory và giới hạn theo server quota. |
| RabbitMQ channel bị đóng hoặc publish không ổn định | Dùng một raw `Channel` từ nhiều thread hoặc broker đóng channel | Để `RabbitTemplate` quản lý channel; xem exception protocol và channel lifecycle. |
| Restart tạo message trùng | Broker đã nhận event nhưng chunk DB rollback; retry không idempotent | Outbox, message key cố định, consumer deduplication và đối soát. |
| Kafka lag tăng dù thêm consumer | Ít topic partition, thời gian xử lý/poll quá dài hoặc broker nghẽn | Kiểm tra partition count, lag per partition, poll và downstream capacity. |
| HTTP pool có connection idle nhưng request vẫn chờ | Hết giới hạn `per route` hoặc bị rate limiter | Theo dõi pending theo route và quota API; không chỉ nhìn max total. |
| Latency tăng sau khi scale nhiều máy | Tổng connection và in-flight request tăng đột biến | Dùng ngân sách toàn cụm, giới hạn worker và backpressure. |
| Dừng job rất lâu, nhiều worker mắc kẹt | Timeout I/O và shutdown quá dài; request đang chờ pool | Đặt deadline hữu hạn, ngừng cấp việc mới rồi drain tác vụ có kiểm soát. |

### Checklist trước khi vận hành production

- [ ] Đã xác định chính xác đơn vị được pool/cache: TCP connection, AMQP channel, JMS session, HTTP connection hoặc tài nguyên nội bộ của client.
- [ ] Đã đối chiếu giới hạn trên **mỗi ứng dụng và toàn cụm** với hạn mức broker/API và các tác vụ khác.
- [ ] Số worker, request in-flight, channel/session/consumer và connection pool được tính trong cùng một sơ đồ tài nguyên.
- [ ] Có giới hạn acquisition wait, connect/response timeout và số lần retry; không giữ tài nguyên vô hạn.
- [ ] Client được chia sẻ đúng theo contract thread safety; các resource stateful không bị dùng đồng thời trái phép.
- [ ] Đã kiểm tra retry/restart và cơ chế idempotency, nhất là trường hợp publish thành công nhưng chunk rollback.
- [ ] Có metric pending/timeout/latency cùng chỉ số broker, JVM, database và kết quả nghiệp vụ.
- [ ] Đã thử khi middleware khởi động lại, giảm throughput, đóng kết nối đang dùng hoặc broker áp quota.

## 10. Bài tập thực hành

**Bài 1 — Tính ngân sách tài nguyên.** Một job tạo 40 partition, executor tối đa 8 worker; mỗi worker gửi tuần tự một message tại một thời điểm. Có 3 ứng dụng batch chạy đồng thời, cần dự phòng 4 channel mỗi ứng dụng. Hãy tính mức channel candidate cho từng ứng dụng và tổng số channel có thể dùng trên toàn cụm. Giải thích tại sao số TCP connection có thể nhỏ hơn nhiều tổng số channel.

**Bài 2 — Thử nghiệm saturation.** Dùng RabbitMQ và cấu hình `channel.cache.size = 2`, `channel.cache.checkout-timeout = 500ms` với workload publish đồng thời nhiều hơn hai thao tác. Đo số lần checkout timeout và thời gian job. Tăng giới hạn lên 4, 8 và kiểm tra xem throughput có thực sự tăng hay chỉ đẩy áp lực sang broker. Tách riêng metric chờ channel và metric xác nhận publish nếu thư viện/quan sát hỗ trợ.

**Bài 3 — Phục hồi và dữ liệu trùng.** Tạo tình huống gửi được message rồi cố tình làm chunk thất bại trước commit. Restart job, quan sát message trùng. Thiết kế outbox hoặc consumer idempotent và kiểm chứng lại kết quả.

**Bài 4 — Chẩn đoán pool.** Khi tăng từ 4 lên 12 worker, job không chạy nhanh hơn, HTTP pool pending tăng nhưng CPU vẫn thấp. Hãy phân biệt ba khả năng: hết connection `per route`, API áp rate limit, hoặc database giữ lock quá lâu; nêu phép đo cần thiết cho mỗi giả thuyết.

### Câu hỏi tự kiểm tra

1. Tại sao `channelCacheSize = 16` không phải lúc nào cũng giới hạn số channel đang mở ở mức 16?
2. Vì sao `KafkaConsumer` không thể được chia sẻ giữa các worker theo cách chia sẻ `KafkaProducer`?
3. Tăng số partition có làm tăng số TCP connection tới RabbitMQ theo tỷ lệ 1:1 hay không? Điều kiện nào khiến câu trả lời thay đổi?
4. Vì sao retry một yêu cầu timeout có thể tạo dữ liệu trùng dù connection pool hoạt động bình thường?
5. Khi throughput ngừng tăng, vì sao cần xem cả metric của middleware, executor, database và transaction?

**Kết luận:** Connection pool của middleware là một phần của **ngân sách tài nguyên toàn job**, không phải một nút vặn tăng tốc độc lập. Với Spring Batch, cấu hình tốt bắt đầu từ hiểu đúng loại tài nguyên của từng client, giới hạn concurrency, quan sát thời gian chờ và bảo đảm idempotency khi retry/restart. Chỉ tăng pool khi phép đo chứng minh pool đang giới hạn throughput và phía middleware còn khả năng tiếp nhận tải.
