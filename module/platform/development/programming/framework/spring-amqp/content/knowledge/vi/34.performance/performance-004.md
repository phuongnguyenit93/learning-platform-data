# Tối ưu channel cache, connection và executor

Một dịch vụ dùng **Spring AMQP** có thể publish hàng nghìn message bằng `RabbitTemplate`, đồng thời có nhiều `@RabbitListener` xử lý từ RabbitMQ qua exchange, queue và binding. Khi tải tăng, nhiều người lập tức nâng `concurrency` hoặc `channelCacheSize` với kỳ vọng thông lượng tăng tuyến tính. Nhưng nếu hệ thống bị giới hạn bởi **số channel, thread nhận delivery, pool kết nối database, thời gian chờ publisher confirms hay tốc độ broker**, việc tăng sai một tham số có thể làm độ trễ cao hơn, tăng bộ nhớ, gây timeout và khiến retry tạo thêm tải.

Bài học thuộc chương **Hiệu năng** của module **SPRING_AMQP**. Chúng ta sẽ phân biệt **TCP connection**, **AMQP channel**, **channel cache** và **các executor** trong Spring AMQP 0-9-1; tối ưu `CachingConnectionFactory`, lựa chọn SMLC/DMLC và cấu hình thực tế; cuối cùng đo throughput, p95/p99 latency, backpressure, ACK/NACK và các tác động của retry, dead-letter, transaction và phục hồi kết nối.

**Nguyên tắc chính:** bắt đầu từ workload và chỉ số đo được; chỉ tăng tài nguyên sau khi xác định đúng điểm nghẽn. Channel cache không phải “số worker”, executor không phải “số consumer”, và tăng số connection không mặc nhiên khiến RabbitMQ phục vụ nhanh hơn.

## 1. Sơ đồ tài nguyên: connection khác channel, thread khác consumer

~~~mermaid
flowchart LR
    API["HTTP/API threads"] --> RT["RabbitTemplate"]
    RT --> CCF["CachingConnectionFactory"]
    CCF --> CON["TCP connection"]
    CON --> CH1["AMQP channel publish"]
    CON --> CH2["AMQP channel consumer A"]
    CON --> CH3["AMQP channel consumer B"]
    CH1 --> BR["RabbitMQ broker"]
    BR --> CH2
    BR --> CH3
    CH2 --> SMLC["SMLC: hàng đợi nội bộ"]
    CH3 --> DMLC["DMLC: callback trực tiếp"]
    SMLC --> EX1["Listener TaskExecutor"]
    DMLC --> EX2["RabbitMQ client executor"]
    EX1 --> DB["Business logic / Database"]
    EX2 --> DB
~~~

Sơ đồ minh họa **hai kiểu container khác nhau**, không có nghĩa một consumer vừa chạy trong SMLC vừa chạy trong DMLC. Các khái niệm:

| Tài nguyên | Vai trò | Chi phí chính | Sai lầm phổ biến |
|---|---|---|---|
| **TCP connection** | Kết nối mạng giữa client JVM và broker | Socket, heartbeat, I/O threads, broker memory | Một connection cho mỗi message |
| **AMQP channel** | Luồng logic multiplex trên connection, mang publish/delivery/ACK | Broker/client channel state, mở/đóng channel | Coi channel cache là số consumer hoặc số connection |
| **Channel cache** | Giữ channel đã dùng để tái sử dụng, tránh tạo/hủy liên tục | Bộ nhớ, idle channel và số channel mở trên broker | Tăng vô hạn để “tăng throughput” |
| **Consumer** | Một subscription đang nhận delivery từ queue | Channel dài hạn, callback và unacked deliveries | Đặt nhiều consumer hơn khả năng DB xử lý |
| **Client executor** | RabbitMQ Java client dispatch delivery/callback | Thread và CPU | Nghĩ `SMLC.taskExecutor` điều khiển luôn client callbacks |
| **Listener task executor** | Với SMLC, chạy vòng nhận và invoke listener; với DMLC chủ yếu monitor | Thread, queue task, context switching | Tăng `taskExecutor` của DMLC để mở thêm listener threads |
| **Business executor** | Nếu listener tự offload công việc sang thread pool | Hàng chờ, memory, thời điểm completion | ACK khi vừa submit task, trước khi nghiệp vụ commit |

Trong Spring AMQP truyền thống, `CachingConnectionFactory` thường chia sẻ **một connection** cho nhiều channel ở chế độ mặc định. `RabbitTemplate` có thể được dùng chung giữa các thread nhưng không có nghĩa tất cả thread publish trên **cùng channel**. Các consumer dài hạn cũng giữ channel riêng.

### 1.1. Xác định “đang nghẽn ở đâu”

Trước khi đổi tham số, thu thập:

- **Ở producer:** tốc độ publish, số confirms đang chờ, tỷ lệ timeout/NACK/returns, p95/p99 thời gian `convertAndSend` hoặc thời gian chờ confirm, số lần checkout channel bị chặn.
- **Ở consumer:** `messages_ready`/`messages_unacknowledged`, consumer count, delivery rate, redelivery rate, p95 thời gian xử lý listener, số task đang chờ.
- **Ở broker:** số connection/channel mở, channel churn, CPU, disk I/O, memory/disk alarms, flow control và queue type.
- **Ở ứng dụng:** heap/GC, runnable/blocked threads, executor active count/queue depth/rejection, DB connection pool saturation.

Ví dụ: nếu broker còn rảnh nhưng `HikariCP` hết connection và listener chờ SQL, nâng `channelCacheSize` không giúp gì. Nếu queue backlog tăng và mỗi consumer đang xử lý liên tục trong khi CPU/DB còn dư năng lực, điều chỉnh consumer concurrency có thể hợp lý hơn.

## 2. CachingConnectionFactory: cache channel hay cache connection?

`CachingConnectionFactory` của `spring-rabbit` là lựa chọn thông dụng cho RabbitMQ AMQP 0-9-1. Nó hỗ trợ hai chế độ:

| Đặc điểm | `CacheMode.CHANNEL` | `CacheMode.CONNECTION` |
|---|---|---|
| Mặc định? | **Có** | Không |
| Tài nguyên được dùng lại | Một connection proxy chia sẻ; cache channel trên connection | Cache **các connection nhàn rỗi**, mỗi connection có channel cache riêng |
| `channelCacheSize` | Số channel nhàn rỗi được giữ lại, hoặc giới hạn khi bật checkout timeout | Cache channel **trên từng connection** |
| `connectionCacheSize` | Không phải tham số chính | Số connection nhàn rỗi được giữ lại |
| `connectionLimit` | Thường không dùng để điều chỉnh chế độ này | Giới hạn tổng số connection khi được cấu hình |
| Khi phù hợp | **Phần lớn ứng dụng Spring AMQP** | Cần nhiều connection thật, ví dụ kết nối qua load balancer hoặc chia tải tới các node |
| Chi phí | Ít socket và client executor hơn | Nhiều socket, client I/O threads, cache channel theo từng connection |
| Auto-declaration với `RabbitAdmin` | Hỗ trợ theo cấu hình thường dùng | **Automatic declaration không được hỗ trợ** theo tài liệu Spring AMQP |

**Không dùng `CacheMode.CONNECTION` chỉ để “có thêm channel”.** Một TCP connection có thể chứa nhiều channel. Chuyển chế độ cần có lý do về topology, network, flow control hoặc phân phối connection, đồng thời phải giải quyết vấn đề `RabbitAdmin` không auto-declare như khi dùng CHANNEL.

### 2.1. Sự khác biệt giữa “cache size” và “hard limit”

Hai tình huống dễ gây hiểu nhầm:

~~~text
Case A — channelCacheSize = 10, channelCheckoutTimeout = 0
  40 threads cùng lúc có thể sử dụng nhiều hơn 10 channels.
  Khi trả channel về, tối đa 10 channel idle được cache.
  Những channel dư có thể bị đóng.

Case B — channelCacheSize = 10, channelCheckoutTimeout = 2_000 ms
  Giới hạn tổng channel trên một connection là 10.
  Threads tiếp theo chờ channel rảnh tối đa 2 giây.
  Hết thời gian: AmqpTimeoutException.
~~~

Trong **Case A**, cache tránh chi phí tạo/hủy channel lặp lại, nhưng **không áp giới hạn cứng** số channel đang hoạt động. Nếu burst publish cao, channel count có thể tăng ngoài cache size và bị đóng khi trả lại.

Trong **Case B**, `channelCheckoutTimeout > 0` biến `channelCacheSize` thành **giới hạn số channel trên connection**, tạo một cơ chế backpressure ngay ở bước lấy channel. Điều này có thể bảo vệ broker khỏi bùng nổ channel, nhưng cũng khiến request thread bị chặn hoặc ném timeout nếu cấu hình quá thấp.

| Tham số | Nghĩa đúng | Hệ quả khi tăng quá mức |
|---|---|---|
| `channelCacheSize` | Cache idle, hoặc cap khi bật checkout timeout | Tăng channel giữ trên broker, memory/FD overhead |
| `channelCheckoutTimeout` = 0 | Mặc định không cap channel bằng cache size | Burst có thể tạo nhiều channel |
| `channelCheckoutTimeout` > 0 | Đợi channel khi chạm cap, rồi timeout | Chặn request, tăng tail latency khi thiếu channel |
| `connectionCacheSize` | Số **idle connection** được cache trong CONNECTION mode | Nhiều socket/threads idle, không phải connection limit |
| `connectionLimit` | Cap tổng connection trong CONNECTION mode | Thiếu connection có thể khiến thread chờ/timeout |

Cache mặc định của `CachingConnectionFactory` từ lâu là **25 channel**; đây chỉ là điểm khởi đầu của thư viện, không phải công thức cho mọi workload. Cần quan sát số channel thực sử dụng và **high-water mark**, thay vì nâng 25 → 200 theo cảm tính.

### 2.2. Channel transactional và non-transactional được cache riêng

`CachingConnectionFactory` duy trì các cache riêng cho channel transactional và non-transactional. Nếu một service vừa dùng `channelTransacted=true` vừa publish bình thường, đo từng nhóm channel; không giả định cache non-transactional rảnh nghĩa là không có áp lực ở nhóm transactional.

Đừng bật channel transaction chỉ để tăng độ tin cậy của publish. RabbitMQ transaction có chi phí commit, không làm database + broker thành một giao dịch nguyên tử. Với publish độc lập, thường nên cân nhắc **publisher confirms**; với DB + event cần bền vững, cân nhắc **transactional outbox**, rồi benchmark các thiết kế trên cùng tải.

## 3. Tối ưu cache theo loại traffic

### 3.1. Producer gửi ngắn hạn với RabbitTemplate

Một lệnh publish ngắn thường checkout channel, publish rồi trả channel về cache. Cache quá nhỏ dẫn đến **channel churn**: liên tục tạo `channel.open`/`channel.close`, tốn round-trip và quản lý tài nguyên. Cache lớn hơn có thể giảm churn, nhưng sau một ngưỡng lợi ích giảm dần.

Ví dụ chiến lược:

1. Bắt đầu với cache mặc định hoặc giá trị vừa phải.
2. Tạo tải theo concurrency và burst giống production.
3. Đo idle-channel high-water, số channel mở trên broker, p95/p99 thời gian publish.
4. Tăng `channelCacheSize` từng bước khi có churn rõ ràng và broker còn năng lực.
5. Nếu cần giới hạn bùng nổ tài nguyên, đặt `channelCheckoutTimeout` dương và **xử lý timeout có kiểm soát**, tránh retry tức thời không giới hạn.

**Không hiểu nhầm `RabbitTemplate` thread-safe** thành RabbitMQ native `Channel` thread-safe. Nếu tự lấy `com.rabbitmq.client.Channel` rồi publish đồng thời trên cùng channel, bạn phải tuân theo quy tắc đồng bộ của Java client. Để tránh lỗi, ưu tiên dùng template và factory do Spring quản lý.

### 3.2. Consumer giữ channel dài hạn

Mỗi consumer đang chạy thường giữ một channel trong toàn bộ vòng đời đăng ký. Ví dụ SMLC có `concurrentConsumers=8` thường cần ít nhất **8 consumer channels**, chưa kể producer, `RabbitAdmin`, direct-reply-to hoặc container khác.

Nếu bật channel cap và dành toàn bộ budget cho consumer, `RabbitTemplate` có thể không lấy được channel để publish dù CPU còn rảnh. Đây là lý do kích thước cap phải xét **tổng các đường sử dụng cùng connection factory**, không chỉ số request HTTP.

Với DMLC, tổng số consumer có thể xấp xỉ `số queue × consumersPerQueue`, và **mỗi consumer cho mỗi queue giữ channel riêng**. Với SMLC, mỗi consumer sử dụng một channel và có thể consume nhiều queue theo cấu hình container.

### 3.3. Request/reply và publisher confirm

Request/reply, đặc biệt khi có nhiều request đang in-flight, có thể **giữ tài nguyên channel/reply consumer trong suốt thời gian chờ phản hồi**. Vì vậy channel cap chỉ dựa trên tốc độ publish ngắn hạn có thể thiếu. Publisher confirms cũng cần được theo dõi đến kết quả; không được dùng cache quá nhỏ rồi bỏ qua future/callback hoặc xem timeout là chắc chắn broker không nhận.

Nếu dùng `PooledChannelConnectionFactory`, pool mặc định còn có giới hạn riêng; các request/reply có thể block dài khi pool hết channel. `PooledChannelConnectionFactory` không được khuyến nghị cho consumers giữ channel lâu dài, và nó **không hỗ trợ correlated publisher confirms** như `CachingConnectionFactory`. Chỉ đổi factory sau khi hiểu rõ tính năng mình đang dùng.

## 4. Connection: khi nào một connection là đủ, khi nào cần tách?

Một connection có thể multiplex nhiều channel, vì thế nhiều dịch vụ chỉ cần `CacheMode.CHANNEL`. Nhưng khi **producer và consumer cùng chung connection**, tài nguyên của broker hoặc flow control có thể tạo sự phụ thuộc khó chịu.

### 4.1. Tách publisher và consumer để giảm tương tác bất lợi

RabbitMQ có cơ chế **connection.blocked** khi broker gặp memory/disk alarms. Nếu producer và consumer cùng dùng một connection bị block, ứng dụng có thể rơi vào tình huống producer không publish được, trong khi consumer cũng không có đường hoạt động bình thường để giải phóng áp lực. Spring AMQP hỗ trợ `RabbitTemplate.setUsePublisherConnection(true)` để publish qua **publisher connection factory riêng** của connection factory chính khi có thể.

~~~java
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PublisherConnectionConfiguration {
    @Bean("outboundRabbitTemplate")
    RabbitTemplate outboundRabbitTemplate(
            CachingConnectionFactory connectionFactory) {

        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setUsePublisherConnection(true);
        return template;
    }
}
~~~

Đây là ví dụ bean **đặt tên riêng**; nếu Spring Boot đã tạo `RabbitTemplate`, cần quyết định bean nào được injection qua `@Qualifier` để không gây mơ hồ. Publisher connection có thể có cấu hình cache riêng; hãy đo trên kết nối publish lẫn consume.

**Giới hạn:** khi publisher đang tham gia **transaction của consumer**, việc tách connection có thể phá mối liên hệ transaction mong đợi. Spring AMQP cũng không sử dụng separate publisher connection trong trường hợp cần chia sẻ consumer channel/transaction tương ứng. Nếu bắt buộc đồng bộ DB state và event, đánh giá transactional outbox thay vì lạm dụng connection-level tricks.

### 4.2. CacheMode.CONNECTION cần tính cả thread và RabbitAdmin

`CacheMode.CONNECTION` có thể hữu ích nếu muốn các connection đến các node broker khác nhau, ví dụ thông qua load balancer. Nhưng:

- `connectionCacheSize` là số **idle connections** có thể giữ trong cache, **không giới hạn** số connection đang mở.
- `setConnectionLimit(n)` (khi dùng) mới giới hạn tổng connection; thiếu connection sẽ chờ theo `channelCheckoutTimeout` rồi có thể ném `AmqpTimeoutException`.
- Mỗi connection có thể dùng executor riêng của RabbitMQ Java client nếu không cấu hình executor chia sẻ; số lượng connection tăng có thể nhân số thread.
- **Spring AMQP không hỗ trợ automatic declaration của exchange/queue/binding trong CONNECTION cache mode** theo tài liệu. Có thể phải tách `RabbitAdmin`/connection factory hoặc quản trị topology ngoài tiến trình.

Nếu không có lý do vận hành rõ ràng, tránh chuyển chế độ này chỉ vì hàng đợi có backlog. Thay đổi cache mode tác động cả số connection, cache channel, lifecycle và quyền khai báo topology.

### 4.3. Quản lý connection ngoài cache

Một số kiểu factory khác đáng biết:

- **`PooledChannelConnectionFactory`:** pool channel có giới hạn và đợi khi hết; không hỗ trợ correlated confirms, không phù hợp làm factory chính cho listener giữ channel lâu dài. Muốn dùng phải hiểu Apache Commons Pool2 và giới hạn của pool.
- **`ThreadChannelConnectionFactory`:** giữ channel theo thread nhằm phục vụ bài toán thứ tự publish. Có rủi ro giữ tài nguyên nếu dùng nhiều thread ngắn hạn; phải giải phóng bằng `closeThreadChannel()` theo quy trình phù hợp.
- **`CachingConnectionFactory`:** mặc định dễ vận hành cho producer/consumer kết hợp và hỗ trợ phần lớn Spring AMQP features, nên là điểm xuất phát cho tuning.

Không có một loại factory nào tự giải quyết mọi yêu cầu **thứ tự, confirm, transaction và backpressure**. Chọn theo ngữ nghĩa nghiệp vụ trước, rồi mới benchmark.

## 5. Ba lớp executor: nơi nào thực sự chạy listener?

Điểm thường xuyên gây tuning sai là tưởng rằng **tăng pool của listener** luôn tăng tốc độ tiêu thụ. Cần xét kiểu container:

| Đường thực thi | SMLC | DMLC |
|---|---|---|
| RabbitMQ Java client nhận delivery từ broker | Client executor nhận callback, đưa message vào queue nội bộ của container | Client executor trực tiếp gọi listener |
| `container.taskExecutor` | **Chạy listener invoker**, cần đủ thread cho số concurrent consumers | Chủ yếu phục vụ monitor/consumer management task, **không** phải nơi thực thi listener chính |
| `CachingConnectionFactory.setExecutor` | Cấp executor cho RabbitMQ client delivery dispatch trước khi SMLC handoff | **Quyết định tài nguyên thread thực thi listener** ở phía client |
| Concurrency | `concurrentConsumers` và `maxConcurrentConsumers` | `consumersPerQueue` cho mỗi queue |
| Kiến trúc | Có handoff qua queue nội bộ | Không có bước handoff listener như SMLC |
| Rủi ro khi pool thiếu thread | Consumer invocation không khởi tạo/không được chạy đủ | Callback client bị nghẽn; tất cả listener dùng factory chịu ảnh hưởng |

### 5.1. SMLC: listener TaskExecutor gắn với concurrency

SMLC dùng thread từ `TaskExecutor` để chạy `MessageListener`. Mỗi consumer lâu dài chiếm thread; nếu `maxConcurrentConsumers=8` mà executor chỉ có tối đa **4 active threads**, tăng max concurrency sẽ không giúp ích. Tùy thiết lập executor, task có thể bị xếp hàng hoặc bị từ chối.

Spring AMQP dùng `SimpleAsyncTaskExecutor` nếu bạn không cung cấp executor. Đây không phải fixed-size thread pool kiểu thông thường. Với production muốn kiểm soát tài nguyên rõ ràng, dùng `ThreadPoolTaskExecutor` và **đặt tên thread** để log/thread dump dễ phân tích.

### 5.2. DMLC: listener chạy trực tiếp trên client dispatch threads

DMLC gọi listener **trên RabbitMQ Java client thread**, trong khi `taskExecutor` của DMLC chủ yếu dành cho monitor task. Nếu bạn tạo một pool `listenerTaskExecutor` 64 threads rồi gắn vào DMLC, **không có nghĩa 64 threads đó sẽ chạy business listener**.

Đối với DMLC, phải cấp **RabbitMQ client executor** qua `CachingConnectionFactory.setExecutor(...)` đủ rộng theo tổng desired concurrency của các container dùng chung factory. Client mặc định có internal thread pool; tài liệu Spring mô tả kích thước ở thời điểm viết thường dựa trên `availableProcessors() * 2` **cho mỗi connection**. Đây là thông tin phiên bản, không phải giới hạn cố định bất biến của mọi RabbitMQ Java client.

Nếu công việc trong listener tốn nhiều thời gian hoặc block DB/API, DMLC sẽ chiếm client callback threads lâu hơn. Trong một workload như vậy, SMLC có thể dễ cô lập business listener thread pool hơn. Không chọn DMLC chỉ vì tên “direct” nghe nhanh hơn; benchmark và quan sát thread dump mới cho biết lợi ích.

### 5.3. Executor thứ ba: nghiệp vụ do ứng dụng tự tạo

Ví dụ một listener nhận message rồi `executor.submit(() -> chargeOrder(...))` và return ngay. Nếu container ở ACK AUTO, có thể ACK delivery **trước khi task thật sự ghi database**; khi task thất bại sau đó, message đã rời queue. Đây là lỗi độ tin cậy, không phải tối ưu hiệu năng.

Nếu cần xử lý async, dùng kiểu async listener được Spring AMQP hỗ trợ (ví dụ `CompletableFuture` hoặc Reactor `Mono` ở phiên bản tương ứng) và bảo đảm adapter xử lý ACK/exception theo completion; hoặc chuyển tác vụ vào database/outbox bền vững trước khi ACK. **Không tăng concurrency bằng cách tách task mà bỏ qua semantics ACK.**

## 6. Ví dụ Spring Boot: bắt đầu bằng cấu hình có thể đo được

Ví dụ sau là **baseline thử nghiệm**, không phải giá trị khuyến nghị chung cho production:

~~~yaml
spring:
  rabbitmq:
    addresses: rabbitmq-1.internal:5672,rabbitmq-2.internal:5672
    connection-timeout: 5s
    cache:
      connection:
        mode: channel
      channel:
        size: 64
        checkout-timeout: 2s
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      type: simple
      simple:
        concurrency: 4
        max-concurrency: 8
        prefetch: 32
        acknowledge-mode: auto
~~~

**Giải thích cụ thể:**

| Thuộc tính | Ý nghĩa | Vì sao không tăng bừa |
|---|---|---|
| `cache.connection.mode: channel` | Một shared connection proxy, tái sử dụng channel | CONNECTION mode thêm socket/client threads và hạn chế auto-declaration |
| `cache.channel.size: 64` | Kích thước cache; do timeout dương nên cũng là channel cap | Cần đủ cho consumer channels, concurrent publishers và các template khác |
| `cache.channel.checkout-timeout: 2s` | Chờ lấy channel tối đa 2 giây | Thời gian chờ làm tăng tail latency; phải bắt timeout đúng cách |
| `listener.simple.concurrency: 4` | SMLC có ít nhất 4 consumers | Mỗi consumer giữ channel và thread |
| `listener.simple.max-concurrency: 8` | Mức trần co giãn consumers | Đừng vượt DB/CPU capacity |
| `listener.simple.prefetch: 32` | Số delivery chưa ACK có thể được cấp cho mỗi consumer theo broker semantics | Quá lớn giữ nhiều payload ở client và làm fairness kém |
| `publisher-confirm-type: correlated` | Cho phép theo dõi kết quả publish qua correlation data | Không có nghĩa consumer đã ACK |
| `publisher-returns: true` + `mandatory` | Phát hiện message không route tới queue | Cần xử lý callback/returned result thay vì bỏ qua |

Khi dùng `spring.rabbitmq.addresses`, giá trị `host/port` riêng thường không còn hiệu lực theo cách cấu hình client; nên kiểm tra Spring Boot properties đúng phiên bản. Nếu yêu cầu TLS, chuyển sang AMQPS và cấu hình trust/hostname verification, không đổi cổng rồi bỏ qua xác thực chứng chỉ.

**Tác động khi thay cấu hình:** đổi channel cap của `CachingConnectionFactory` đang dùng không nhất thiết có hiệu lực với connection hiện tại ngay lập tức. Theo Javadoc, thay `channelCacheSize` trên bounded cache có thể cần tạo **connection mới** để áp dụng giới hạn. Tuning nên qua rollout/restart có kiểm soát thay vì assume một runtime setter làm đổi hành vi mọi channel đang chạy.

## 7. Java Configuration: tách client executor khỏi SMLC executor

Ví dụ tạo các bean riêng cho môi trường test/ứng dụng Spring không để Boot auto-config toàn bộ. Nếu dự án **đã có** `CachingConnectionFactory` do Spring Boot tạo, hãy customizer/điều chỉnh bean hiện có theo cách tương thích với cấu hình dự án, **không khai báo thêm factory trùng** rồi vô tình có hai bộ connection.

~~~java
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class RabbitPerformanceConfiguration {

    @Bean("rabbitClientExecutor")
    ThreadPoolTaskExecutor rabbitClientExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("rabbit-client-");
        executor.setCorePoolSize(16);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(1_000);
        return executor;
    }

    @Bean
    CachingConnectionFactory connectionFactory(
            @Qualifier("rabbitClientExecutor") ThreadPoolTaskExecutor rabbitClientExecutor) {

        var factory = new CachingConnectionFactory("localhost");
        // Host/credentials ở đây chỉ để minh họa; dùng secret/TLS production.
        factory.setChannelCacheSize(64);
        factory.setChannelCheckoutTimeout(2_000L);
        factory.setExecutor(rabbitClientExecutor);
        factory.setConnectionNameStrategy(cf -> "orders-service");
        return factory;
    }

    @Bean("smlcExecutor")
    ThreadPoolTaskExecutor smlcExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("orders-listener-");
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(0);
        return executor;
    }

    @Bean("ordersListenerFactory")
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            CachingConnectionFactory connectionFactory,
            @Qualifier("smlcExecutor") ThreadPoolTaskExecutor smlcExecutor) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setTaskExecutor(smlcExecutor);
        factory.setConcurrentConsumers(4);
        factory.setMaxConcurrentConsumers(8);
        factory.setPrefetchCount(32);
        return factory;
    }
}
~~~

Mã này là **cấu hình minh họa**, không phải benchmark recommendation. `rabbitClientExecutor` có queue hữu hạn; nếu callback delivery bị đẩy đến khi queue và max threads đều đầy, executor có thể từ chối task, gây gián đoạn. Cần đo executor metrics và điều chỉnh pool/queue capacity theo tải thật; **không coi queue 1.000 là nơi lưu bền vững cho RabbitMQ messages**. Bên phía SMLC, `smlcExecutor` được cho dư thread so với `maxConcurrentConsumers=8` để tránh đặt trần thiếu; `queueCapacity=0` nghĩa là ưu tiên direct handoff và task có thể bị reject nếu vượt pool max.

Listener:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class OrdersConsumer {
    private final OrdersService service;

    OrdersConsumer(OrdersService service) {
        this.service = service;
    }

    @RabbitListener(
            queues = "orders.created.q",
            containerFactory = "ordersListenerFactory")
    public void onMessage(OrderCreated event) {
        service.applyIdempotently(event); // Ghi DB, rồi method trả về.
    }
}
~~~

`OrdersService`, `OrderCreated` và message converter là thành phần nghiệp vụ ứng dụng cần cung cấp. Nếu consumer xử lý JSON object, phải cấu hình converter phù hợp; không mặc định listener nhận trực tiếp class từ byte[] khi chưa thiết lập serialization.

## 8. Java Configuration: DMLC không dùng listener executor theo cùng cách

Với DMLC, ưu tiên đo **client executor** và số consumer cho từng queue:

~~~java
import org.springframework.amqp.rabbit.config.DirectRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.context.annotation.Bean;

@Bean("directOrdersFactory")
DirectRabbitListenerContainerFactory directOrdersFactory(
        CachingConnectionFactory connectionFactory) {

    var factory = new DirectRabbitListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setConsumersPerQueue(2);
    factory.setPrefetchCount(32);
    return factory;
}
~~~

Ở cấu hình này, `CachingConnectionFactory` phải có **client executor đủ khả năng chạy callback của mọi DMLC listener dùng nó**. Nếu DMLC đang listen 4 queues, `consumersPerQueue=2` nghĩa là có thể có **8 consumer registrations/channels** riêng, chưa kể container khác. `setTaskExecutor` ở DMLC không phải đòn bẩy chính để tạo thêm thread chạy listener.

Với `@RabbitListener`, thuộc tính `concurrency` có ý nghĩa tùy container:

~~~java
// SMLC: số consumer tối thiểu - tối đa, tăng động theo workload.
@RabbitListener(queues = "orders.created.q",
                containerFactory = "ordersListenerFactory",
                concurrency = "4-8")
public void receiveSimple(OrderCreated event) { /* ... */ }

// DMLC: chỉ nhận một số, nghĩa là consumersPerQueue.
@RabbitListener(queues = "orders.audit.q",
                containerFactory = "directOrdersFactory",
                concurrency = "2")
public void receiveDirect(OrderCreated event) { /* ... */ }
~~~

**Không dùng `concurrency="4-8"` với DMLC** như SMLC. Trên DMLC, concurrency là số nguyên cho `consumersPerQueue`. Annotation này cũng override cấu hình concurrency trong factory, nên khi debug phải nhìn **cả annotation và factory**, không chỉ `application.yml`.

## 9. Điều chỉnh prefetch, concurrency và backpressure cùng nhau

Cache và executor là **tài nguyên phía client**. Nhưng tốc độ thực tế còn phụ thuộc consumer xử lý bao lâu và broker được phép giao bao nhiêu delivery chưa ACK.

### 9.1. Prefetch là số delivery chưa ACK, không phải số thread

RabbitMQ có thể giao nhiều message tới consumer trước khi nhận ACK theo `prefetchCount`. Với Spring AMQP hiện đại, giá trị mặc định được tài liệu mô tả là **250** từ phiên bản 2.0; nhưng đây **không phải** giá trị tối ưu cho mọi hệ thống, đặc biệt khi payload lớn hoặc xử lý chậm.

| Workload | Điểm xuất phát để thử nghiệm | Rủi ro cần quan sát |
|---|---|---|
| Payload nhỏ, listener nhanh, downstream đủ năng lực | Prefetch vừa đến cao, tăng từng bước | Unacked tăng, fairness giữa consumer giảm |
| Payload lớn vài MB | Prefetch thấp | Heap và GC do nhiều message đang giữ ở client |
| Listener gọi API chậm hoặc database có pool nhỏ | Prefetch thấp–vừa, concurrency theo capacity downstream | Thread chờ I/O, DB pool cạn, retry gây bão |
| Cần thứ tự nghiêm ngặt với một active consumer | Thử `prefetch=1` và một consumer đồng bộ | Throughput thấp; requeue/retry vẫn cần xem xét |
| Nhiều consumer nhưng traffic thấp | Prefetch nhỏ để phân phối đều hơn | Đổi lấy thêm round trips |

Một ước lượng đơn giản về **delivery chưa ACK có thể đang được giữ** khi broker cấp đầy đủ credit:

~~~text
Unacked upper bound xấp xỉ
  số consumers đang hoạt động × prefetch

Ví dụ:
  12 consumers × prefetch 64
  ≈ 768 deliveries có thể chưa ACK cùng lúc.
~~~

Đây là **ước lượng thiết kế**, không phải số unacked lúc nào cũng đạt được. RabbitMQ áp dụng prefetch theo semantics cụ thể; listener container, transactions, multiple consumers và queue type cũng ảnh hưởng thực tế. Kích thước payload cùng object conversion có thể khiến 768 delivery ngốn rất nhiều heap.

### 9.2. Ước lượng concurrency từ thời gian xử lý

Định luật Little cung cấp phép ước lượng tối thiểu cho một hệ xử lý ổn định:

\[
\text{Số tác vụ đang xử lý trung bình} \approx
\text{Throughput mục tiêu (message/s)} \times
\text{Thời gian xử lý trung bình (s/message)}
\]

Ví dụ nếu mục tiêu 100 message/giây và mỗi message mất trung bình 0,15 giây, cần khoảng **15 tác vụ đang xử lý** để đạt mục tiêu *trong điều kiện đủ tài nguyên*. Đây không phải bảo đảm 15 consumers là đủ ở p99 latency, vì service time biến thiên, overhead/queueing, redelivery và database contention.

Hãy so **concurrency tiêu thụ** với:

- Số CPU cores và kiểu tác vụ (CPU-bound vs I/O-bound).
- Connection pool database và transaction duration.
- Rate limit của downstream HTTP services.
- Memory và prefetch × payload size.
- Số channels tối đa từ cache cap và broker.
- Chi phí publisher confirms, retry, dead-letter.

Khi downstream bão hòa, tăng consumers thường chỉ tăng **hàng đợi chờ, transaction lock và timeout**. Lúc này cần **backpressure**, giới hạn concurrency và xử lý lỗi có backoff.

### 9.3. Batch và ACK ảnh hưởng throughput nhưng thay đổi ranh giới lỗi

Trong SMLC, `batchSize` có thể tác động việc gom ACK/transaction khi phù hợp; DMLC hỗ trợ `messagesPerAck` và `ackTimeout` để giảm số ACK gửi riêng lẻ. Nhưng tối ưu ACK cần kiểm tra **độ trễ, phạm vi redelivery, retry và idempotency**. Một message thất bại có thể khiến nhiều delivery liên quan bị xử lý lại tùy mô hình.

Gom nhiều publish hoặc ACK có thể giảm overhead trong tải lớn, nhưng không làm delivery trở thành exactly-once. Với nghiệp vụ quan trọng, giữ `eventId` ổn định, ACK sau DB commit, dùng inbox/outbox hoặc unique key để bảo đảm tác dụng nghiệp vụ không bị nhân đôi.

## 10. Quan sát channel cache đúng cách

`CachingConnectionFactory` cung cấp `getCacheProperties()` để đọc thống kê runtime. Với `CacheMode.CHANNEL`, các trường hữu ích gồm:

| Property | Cách hiểu | Quyết định có thể đưa ra |
|---|---|---|
| `channelCacheSize` | Cấu hình cache hiện tại | Kiểm tra giá trị thực, không chỉ giá trị YAML |
| `idleChannelsNotTx` | Số non-transactional channels rảnh | Có thể dư tài nguyên nếu thường xuyên cao khi workload thấp |
| `idleChannelsNotTxHighWater` | Mức cao nhất channel non-TX rảnh đã ghi nhận | Khi chạm cache size có thể cần điều tra churn |
| `idleChannelsTx` | Số transactional channels rảnh | Phân biệt TX path và non-TX path |
| `idleChannelsTxHighWater` | High-water mark nhóm TX | Không suy ra từ non-TX high-water |
| `connectionName` / `localPort` | Liên kết connection với broker Management UI | Truy vết connection/channel churn |

Với `CacheMode.CONNECTION` còn có `openConnections`, `idleConnections`, `idleConnectionsHighWater` và thuộc tính channel theo từng connection/port.

Ví dụ logging từ ứng dụng:

~~~java
import java.util.Properties;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;

public void logCacheSnapshot(CachingConnectionFactory factory) {
    Properties p = factory.getCacheProperties();
    // Ở production, xuất metric/gauge có nhãn ổn định hoặc log có kiểm soát.
    System.out.println("cacheMode=" + p.getProperty("cacheMode"));
    System.out.println("channelCacheSize=" + p.getProperty("channelCacheSize"));
    System.out.println("idleChannelsNotTx=" + p.getProperty("idleChannelsNotTx"));
    System.out.println(
            "idleChannelsNotTxHighWater=" +
            p.getProperty("idleChannelsNotTxHighWater"));
}
~~~

Đây là **snapshot** để chẩn đoán, không nên tạo log mỗi message. Đừng suy luận “high-water mark chạm cache size” là bằng chứng duy nhất cần tăng cache: có thể chính xác là lượng cache vừa đủ, trong khi broker bị nghẽn ở disk hoặc listener đang chờ DB. Hãy kết hợp với **channel opened/closed rate**, số channel active, checkout timeout và latency publish.

### 10.1. Những chỉ số cần tương quan

| Nguồn | Chỉ số cần xem | Ý nghĩa |
|---|---|---|
| RabbitMQ Management/Prometheus | Connections/channels theo connection; channel open/close churn | Chẩn đoán cache quá nhỏ hoặc channel leak |
| Spring `CachingConnectionFactory` | Cache properties/high-water marks | Hiểu kích thước cache đã dùng |
| Micrometer/Actuator hoặc metrics riêng | Executor active threads, pool size, queued tasks, rejects | Phát hiện client callback hoặc SMLC executor thiếu thread |
| RabbitMQ queue | `messages_ready`, `messages_unacknowledged`, consumer count, redeliver rate | Phát hiện backlog và ACK chậm |
| Producer | Confirm latency, NACK, returns, in-flight attempts | Phát hiện broker/route/publisher bottleneck |
| Business layer | DB pool wait time, SQL p99, external API timeout | Phát hiện nghẽn downstream, không phải RabbitMQ |
| JVM | CPU, GC pause, heap, blocked threads | Tìm nguyên nhân chung làm mọi callback chậm |

Không public RabbitMQ Management hoặc metrics endpoint ra Internet chỉ để thu số liệu; giới hạn trong mạng monitor, dùng TLS/quyền thích hợp và truy cập theo vai trò.

## 11. Ma trận dấu hiệu – nguyên nhân – hành động

| Dấu hiệu | Nguyên nhân thường gặp | Cách xác minh | Biện pháp thử |
|---|---|---|---|
| Channel count tăng/giảm liên tục | Cache quá nhỏ so với burst hoặc channel đóng bất thường | Broker channel churn, cache high-water, logs | Tăng cache có đo đạc; kiểm tra exceptions khiến channel đóng |
| `AmqpTimeoutException` lúc publish | Hard cap channel đang hết | Checkout timeout > 0, số consumer/channel active | Tách publisher connection hoặc tăng cap phù hợp; giới hạn producer concurrency |
| Channel limit phía broker | Tổng channels quá nhiều hoặc leak channel | Channel count per connection, broker limit | Giảm concurrency, đóng channel thủ công đúng cách |
| `AmqpResourceNotAvailableException` | Không tạo được channel, ví dụ broker channel_max | Broker limits và Spring logs | Backoff/retry hữu hạn, điều chỉnh resources |
| SMLC không tăng throughput dù max concurrency cao | SMLC executor thiếu thread hoặc DB quá tải | Thread pool, consumer count, DB pool wait | Cấp đủ executor threads; giới hạn xuống theo DB |
| DMLC listener chậm dù tăng taskExecutor | DMLC dùng Rabbit client threads cho callback | Client executor threads, blocked stack traces | Điều chỉnh client executor hoặc chọn SMLC |
| Nhiều connections/threads không cần thiết | Đang dùng CacheMode.CONNECTION | `openConnections`, thread dump, broker metrics | Quay về CHANNEL nếu không cần nhiều connection |
| p99 publish tăng khi bật confirm | Đợi từng confirm tuần tự, broker I/O cao | Outstanding confirms và latency | Pipeline/batch confirm có giới hạn; không bỏ ACK |
| Queue backlog tăng nhưng channel ổn định | Listener/DB/API xử lý chậm | p95 xử lý, DB wait, redelivery | Tối ưu nghiệp vụ, tăng consumer theo capacity |
| Unacked tăng, heap/GC cao | Prefetch quá lớn với payload nặng | Unacked × payload, heap profile | Hạ prefetch, giảm concurrency, phân luồng payload lớn |
| Publisher và consumer cùng dừng khi broker blocked | Dùng chung connection có flow control | ConnectionBlockedEvent, broker alarms | Giảm áp lực broker; xem xét separate publisher connection |
| Queue message được xử lý trùng sau reconnect | ACK chưa đến broker hoặc publish confirm mất | Event ID, redelivered logs, outbox state | Idempotency và retry có backoff, không chỉ cache tuning |

**Mỗi biện pháp phải đi kèm phép đo sau thay đổi.** Một cấu hình giải quyết channel churn nhưng làm p99 latency xấu đi do checkout blocking không được xem là tối ưu thành công.

## 12. Thiết kế benchmark có thể lặp lại

Để đo xem việc tăng channel cache hoặc executor có thật sự hiệu quả, phải giữ các điều kiện so sánh nhất quán. Không đo “cấu hình A chạy 3 consumers và payload 1 KB” rồi so với “cấu hình B chạy 16 consumers và payload 64 KB”.

### 12.1. Xác định mục tiêu đo

Ví dụ mục tiêu của hệ thống tạo đơn hàng:

| Chỉ số mục tiêu | Cách đo | Vì sao cần |
|---|---|---|
| Publish throughput (message/s) | Số lần publish broker xác nhận hợp lệ mỗi giây | Chỉ tính lệnh publish trả về mà bỏ confirm có thể đánh giá quá cao |
| End-to-end throughput (event/s) | Số sự kiện nghiệp vụ được consumer commit thành công mỗi giây | Phản ánh năng lực thực tế, không chỉ tốc độ enqueue |
| p50/p95/p99 publish latency | Từ bắt đầu publish đến confirm hoặc kết quả theo policy | Phát hiện tail latency khi channel checkout bị block |
| p95/p99 listener processing time | Từ bắt đầu listener đến transaction nghiệp vụ hoàn tất | Phân biệt broker wait với DB/API wait |
| Queue lag | Số ready messages và tuổi message chờ | Đo backlog khi tải vượt năng lực |
| Memory/CPU/GC | JVM và RabbitMQ node metrics | Đánh giá giá phải trả khi tăng threads/prefetch |
| Errors/retries | Channel timeout, NACK, returns, redelivery, DLQ | Tránh tối ưu throughput bằng cách làm mất message |

**Không bỏ qua tính đúng đắn khi benchmark:** xác minh số `eventId` duy nhất được tạo, số được broker nhận, số được consumer ghi DB và số duplicate được dedup. Nếu chỉ thấy rate cao vì message bị ACK trước xử lý, phép đo vô nghĩa.

### 12.2. Ma trận thử nghiệm từng biến

| Run | `channelCacheSize` | `checkoutTimeout` | SMLC concurrency | Prefetch | Mục tiêu |
|---|---:|---|---:|---:|---|
| A – baseline | 25 | 0 | 4 | 32 | Đo hiện trạng, channel churn, p99 |
| B – cache lớn hơn | 64 | 0 | 4 | 32 | Đánh giá lợi ích tái sử dụng channel |
| C – cache bounded | 64 | 2s | 4 | 32 | Quan sát backpressure/checkout timeout |
| D – thêm consumer | 64 | 2s | 8 | 32 | Đo khả năng DB và executor đáp ứng |
| E – prefetch thấp | 64 | 2s | 8 | 8 | Đo heap, fairness, unacked và throughput |
| F – quá tải có kiểm soát | 64 | 2s | 8 | 32 | Đánh giá timeout, retry, broker blocked và phục hồi |

Các con số chỉ dành cho **thử nghiệm minh họa**. Nếu kết quả A đã đạt SLO, không cần thực hiện mọi thay đổi chỉ vì chúng “có thể” cải thiện rate.

### 12.3. Quy trình benchmark

1. Cố định phiên bản **RabbitMQ, Erlang, Spring AMQP, Java Client, JDK**, loại queue (classic/quorum), số replica, TLS, publisher confirms và message durability.
2. Dùng cùng kích thước và kiểu payload, schema conversion, đường exchange/binding và code nghiệp vụ.
3. Tách **warm-up** khỏi giai đoạn ghi số liệu để cache/connections được khởi tạo; cho chạy đủ lâu để thấy steady state.
4. Chạy nhiều lần và so median/p95/p99 theo cùng tải; ghi CPU, memory, GC và DB metrics cùng timestamp.
5. Kiểm tra số message đã commit ở consumer, duplicate và lost-event flags; không bỏ qua retry/DLQ.
6. Thay **một biến chính** mỗi lượt, trừ run có chủ đích đo tương tác giữa các tham số.
7. Tăng tải có kiểm soát đến khi tìm thấy saturation: throughput không tăng nhưng latency/error/backlog tăng.
8. Kiểm tra giai đoạn recovery khi dừng/restart client hoặc broker; một cấu hình nhanh ở steady state có thể rất chậm khi catch-up.

Một kết quả thử nghiệm đầy đủ cần nói rõ **“cấu hình nào tốt hơn theo SLO nào, dưới điều kiện tải nào, với chi phí và rủi ro gì”**, không chỉ ghi “TPS cao hơn 20%”.

## 13. Kiểm thử tình huống thiếu tài nguyên và lỗi kết nối

Tối ưu hiệu năng không được làm yếu đi các bảo đảm đã học về publisher confirms, ACK, retry, dead-letter và giao dịch.

| Thử nghiệm | Cách mô phỏng | Kết quả cần xác minh |
|---|---|---|
| Channel cache thiếu | Giảm cache size, tăng publisher concurrency | Nhìn thấy churn; không có message bị mất do code bỏ qua exception |
| Hard channel cap | `checkoutTimeout > 0`, số request đồng thời vượt cap | Request chờ rồi timeout có kiểm soát; có metric/circuit breaker/backoff |
| Channel bị giữ quá lâu | Request/reply chậm hoặc listener kéo dài | Thread stack rõ ràng; không leak channel; có deadline nghiệp vụ |
| SMLC executor thiếu thread | Max pool thấp hơn desired consumer count trong staging | Consumer không tăng như mong muốn hoặc task bị reject; có alert |
| DMLC client executor bão hòa | Tăng số queues/consumers hoặc giả lập callback chậm | Lag/active threads tăng; không nghĩ taskExecutor monitor giải quyết được |
| Database pool bị nghẽn | Giới hạn DB connections, tăng listener concurrency | Throughput đạt trần, DB wait tăng; backpressure bảo vệ DB |
| Prefetch quá lớn | Payload lớn và consumer chậm | Heap/unacked/GC tăng; giảm prefetch phục hồi |
| Publisher connection blocked | Kích hoạt giới hạn tài nguyên broker trong môi trường riêng | Có sự kiện blocked/unblocked; producer không làm nghẽn consumer ngoài ý muốn |
| Mất connection khi publish | Cắt mạng trước khi confirm đến | Outcome có thể không xác định; outbox giữ event; retry cùng eventId |
| Consumer mất ACK | Dừng consumer sau DB commit, trước ACK broker | Redelivery; idempotent consumer không ghi lặp |
| Broker restart/canary upgrade | Restart node theo test plan | Connection/channel được tạo lại, topology tồn tại, publisher/consumer phục hồi |
| DLQ tăng nhanh | Payload lỗi validation + retry policy | Message lỗi được cách ly, không có retry loop vô hạn |

Những bài test này cần **RabbitMQ thật** (ví dụ Testcontainers hoặc broker staging). Mock `RabbitTemplate` chỉ kiểm tra code gọi method, không tái hiện broker memory alarms, channel limits, network reset hay redelivery.

## 14. Một số giả định sai phổ biến

| Nhận định | Điều đúng |
|---|---|
| “`channelCacheSize=25` nghĩa là chỉ tạo tối đa 25 channels” | Mặc định đó là số **idle channels cached**, trừ khi `checkoutTimeout > 0` |
| “`connectionCacheSize=10` nghĩa là tối đa 10 connections” | Đó là số **idle connections giữ lại**; muốn cap tổng phải xem `connectionLimit` |
| “Mỗi consumer cần một TCP connection” | Một connection có nhiều channel; consumer thường giữ channel riêng |
| “Chuyển sang CONNECTION mode là cách tăng throughput chung” | Thêm socket/threads; có thể không cải thiện và ảnh hưởng auto-declaration |
| “SMLC và DMLC dùng taskExecutor giống nhau” | SMLC invoke listener trên taskExecutor, DMLC trực tiếp trên RabbitMQ client threads |
| “Tăng DMLC taskExecutor là tăng callback listener” | DMLC taskExecutor chủ yếu dành cho monitor; phải xem client executor |
| “Có 32 threads thì luôn xử lý được 32 message đồng thời” | Concurrency còn bị giới hạn bởi consumers, channels, DB pool, I/O và prefetch |
| “Prefetch cao luôn nhanh hơn” | Payload lớn gây heap pressure, unacked backlog và mất cân bằng consumer |
| “Publisher confirm ACK nghĩa là consumer đã xong” | Confirm xác nhận publish, không phải business completion |
| “Tách task async rồi return là tối ưu an toàn” | Có thể ACK trước DB commit; phải giữ lifecycle/settlement đúng |
| “`getCacheProperties` high-water bằng cache size chắc chắn cần tăng cache” | Cần xét channel churn, latency và broker load cùng nhau |
| “Cache, executor và queue depth đủ để bảo đảm exactly-once” | Phải xử lý redelivery, duplicate và idempotent business effects |

## 15. Checklist cấu hình trước production

1. **Xác định workload:** message/giây, kích thước, burst, SLA latency, độ bền, queue type và thời gian xử lý.
2. **Chọn cache mode:** ưu tiên CHANNEL trừ khi có nhu cầu nhiều TCP connections rõ ràng.
3. **Hiểu channel cap:** với `checkoutTimeout = 0`, cache size không phải hard limit; với timeout dương, thiết kế budget channels theo toàn bộ producer/consumer.
4. **Quan sát cache:** đọc cache properties và broker channel open/close churn trước khi tăng size.
5. **Xem xét publisher connection riêng:** đặc biệt khi publish và consume trong cùng service có thể gặp broker blocked; kiểm tra ngoại lệ transaction.
6. **SMLC:** executor đủ cho `maxConcurrentConsumers`, theo dõi active threads/rejections; tránh mở consumer vượt khả năng DB.
7. **DMLC:** RabbitMQ client executor đủ tài nguyên cho callback thực tế; không tối ưu nhầm monitor executor.
8. **Prefetch:** chọn theo payload, số consumer, memory và ordering; đo unacked cùng heap/GC.
9. **Reliability:** publisher confirms/returns, ACK sau commit, retry có backoff, DLQ, idempotency và outbox khi cần.
10. **Backpressure:** đặt giới hạn tài nguyên và xử lý `AmqpTimeoutException`; không retry nóng làm tăng tải hệ thống.
11. **Thread safety:** dùng `RabbitTemplate` đúng cách, tránh chia sẻ native channel đồng thời tùy tiện; đặt tên executor.
12. **Benchmark:** so p95/p99, throughput và error rates dưới cùng điều kiện; đo steady state lẫn phục hồi.
13. **Vận hành:** alerts trên channel churn, broker alarms, unacked/ready, executor queue/rejection, DB wait và redelivery.
14. **Rollout:** thay đổi cấu hình theo canary, kiểm tra restart/recovery, có khả năng rollback và xác minh channel cap mới thật sự có hiệu lực.

### Tài liệu chính thức

- [Spring AMQP — Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): CachingConnectionFactory, channel cache, cache modes, connection limit và cache statistics.
- [Spring AMQP — Threading and Asynchronous Consumers](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/threading.html): client executor so với SMLC/DMLC taskExecutor.
- [Spring AMQP — Choosing a Container](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/choose-container.html): đặc tính SMLC/DMLC.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): concurrency, dynamic scaling, consumersPerQueue.
- [Spring AMQP — Asynchronous Consumer](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): prefetch và listener container.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): các cấu hình `spring.rabbitmq.cache.*` và `spring.rabbitmq.listener.*`.
- [Spring AMQP — RabbitTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html): separate publisher connection, scoped operations và thứ tự publish.

**Kết luận:** Tối ưu hiệu năng Spring AMQP phải đi theo đúng các tầng: **connection** cho socket/I/O, **channel cache** cho tái sử dụng tài nguyên publish/consume, **executor** cho callback và listener invocation, rồi **consumer concurrency + prefetch** để điều tiết tốc độ đưa công việc tới downstream. Đặc biệt, nhớ rằng `channelCacheSize` mặc định không phải hard cap, còn SMLC và DMLC sử dụng executor khác nhau. Khi chọn cấu hình dựa trên high-water marks, broker metrics, p95/p99 latency, DB capacity và bài test quá tải, bạn sẽ tăng thông lượng mà vẫn giữ publisher confirms, ACK/NACK, retry, dead-letter và idempotency đúng cách.
