# Giới hạn CPU, bộ nhớ, connection và channel của ứng dụng

Trong **Spring AMQP**, hệ thống có thể chạy ổn trên máy phát triển nhưng gặp lỗi khi đưa lên Kubernetes: pod liên tục bị `OOMKilled`, listener xử lý chậm do CPU throttling, `RabbitTemplate` không lấy được channel, hoặc số lượng connection tăng đột ngột mỗi khi autoscaling. Các lỗi này liên quan chặt chẽ với nhau: mỗi `@RabbitListener` cần tài nguyên xử lý, `RabbitTemplate` sử dụng channel và connection, còn RabbitMQ phải quản lý socket, delivery chưa ACK và bộ nhớ của broker.

Bài học thuộc chương **Triển khai và vận hành** của module **SPRING_AMQP**. Phạm vi gồm ứng dụng tích hợp RabbitMQ bằng `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, publisher confirms, retry, dead-letter và transaction. Ta sẽ xây dựng **ngân sách tài nguyên theo mỗi pod và toàn hệ thống**, cấu hình CPU/bộ nhớ, giới hạn connection/channel, đánh giá `prefetch × concurrency`, và kiểm thử trước khi triển khai hoặc tăng số replica.

**Tư duy cốt lõi:** một giới hạn chỉ có ý nghĩa khi đồng bộ với các giới hạn còn lại. Giới hạn channel quá nhỏ tạo timeout dù CPU còn rảnh; tăng concurrency vượt pool database chỉ đẩy backlog từ RabbitMQ vào JVM; còn đặt memory limit quá thấp khiến pod bị OOM trong lúc xử lý message lớn.

## 1. Một message đi qua những ngân sách nào?

~~~mermaid
flowchart LR
    PROD["Producer / HTTP requests"] --> RT["RabbitTemplate"]
    RT --> CCF["CachingConnectionFactory"]
    CCF --> CON["TCP connections"]
    CON --> CH["AMQP channels"]
    CH --> BROKER["RabbitMQ exchange → queue"]
    BROKER --> L["SMLC hoặc DMLC"]
    L --> EX["Listener / client executors"]
    EX --> DB["DB / downstream API"]
    CON -.-> CPU["CPU quota & throttling"]
    L -.-> MEM["Heap, native memory, prefetch"]
    BROKER -.-> PRE["Ready & unacked messages"]
~~~

| Tài nguyên | Giới hạn thường đặt ở đâu? | Triệu chứng chạm giới hạn |
|---|---|---|
| **CPU** | Kubernetes `requests.cpu` / `limits.cpu` hoặc VM/container quota | CFS throttling, latency tăng, callback/heartbeat chậm |
| **Bộ nhớ pod** | `limits.memory` / cgroup | GC tăng hoặc container bị OOMKilled |
| **Java heap** | `-Xmx` hoặc `-XX:MaxRAMPercentage` | `OutOfMemoryError: Java heap space`, GC pause |
| **Native/direct/thread memory** | JVM, socket, TLS, threads, direct buffers | Pod OOM dù heap chưa đầy |
| **TCP connection** | Connection factory, số pod, broker/vhost limit, OS sockets | Kết nối bị từ chối, socket/FD cạn, broker overload |
| **AMQP channel** | `CachingConnectionFactory`, broker `channel_max` | Chờ checkout, `AmqpTimeoutException` hoặc broker đóng channel |
| **Consumer concurrency** | SMLC `concurrentConsumers`/`maxConcurrentConsumers`; DMLC `consumersPerQueue` | Thread/DB pool quá tải hoặc queue xử lý không kịp |
| **Prefetch** | Listener container / AMQP QoS | Nhiều unacked deliveries và payload bị giữ trong client |
| **Business executor / DB pool** | Thread pool/connection pool/rate limit của ứng dụng | Task queue dài, SQL timeout, tăng redelivery |

**Đừng nhầm giới hạn client và broker.** `channelCacheSize` thuộc Spring client; `channel_max` là giới hạn negotiated của RabbitMQ cho **mỗi connection**. Tăng giới hạn ở một phía không tự tăng phía còn lại. Giới hạn pod cũng không làm giảm số connection broker phải phục vụ nếu số replica tiếp tục tăng.

## 2. CPU requests, limits và ảnh hưởng tới listener

### 2.1. Requests để scheduler bố trí; limits để kiểm soát trần

Trong Kubernetes:

- `resources.requests.cpu` là mức CPU dùng để scheduler quyết định có đủ sức chứa để xếp pod lên node. Nó cũng là cơ sở cho mức bảo đảm chia sẻ CPU của workload trong điều kiện tranh chấp.
- `resources.limits.cpu` giới hạn lượng CPU container được dùng theo quota/throttling trên hệ thống thực thi tương ứng. Khi ứng dụng muốn dùng vượt hạn mức, nó có thể bị **throttle** thay vì được chạy nhanh hơn.
- `500m` tương đương **0,5 CPU**; `1000m` tương đương **1 CPU** theo cách biểu diễn tài nguyên Kubernetes. Đây không phải số thread Java được phép tạo.

Ví dụ một container được request `500m` và limit `1000m` có thể sử dụng tới khoảng một CPU trong khoảng tính quota; khi tải tăng hoặc quota bị tiêu hết, thread runnable phải chờ. Nếu có nhiều listener làm việc CPU-bound, chỉ tăng concurrency sẽ làm tăng context switching và thời gian chờ chứ không tạo thêm CPU.

### 2.2. CPU throttling ảnh hưởng những việc gì?

| Thành phần | Hậu quả có thể gặp |
|---|---|
| JSON conversion, validation và mã nghiệp vụ | Mỗi message xử lý lâu hơn, queue `ready` tăng |
| RabbitMQ Java client callback executor | Delivery/confirm callback phản hồi chậm, outstanding confirms tăng |
| Listener executor của SMLC | Thời gian ACK bị kéo dài; message ở trạng thái `unacked` lâu hơn |
| Executor của DMLC | Listener chạy trên RabbitMQ client dispatch thread, dễ tranh CPU với callback khác |
| JVM GC | Stop-the-world pause hoặc thiếu CPU cho concurrent GC tăng tail latency |
| Heartbeat/reconnection tasks | Xử lý heartbeat bị trì hoãn nghiêm trọng có thể góp phần vào timeout/reconnect |
| HTTP API và health checks | Readiness timeout, retry hoặc request latency tăng |

Một pod có CPU throttling cao và message lag lớn không phải bằng chứng cần tăng `channelCacheSize`. Hãy đo workload CPU, CPU usage, throttled periods/time, thread dump và thời gian xử lý listener trước.

### 2.3. Chọn số consumer theo CPU hay I/O?

**CPU-bound:** ví dụ ký số, nén hoặc chuyển đổi JSON nặng. Concurrency lớn hơn nhiều lần số CPU thực có thể không tăng throughput.

**I/O-bound:** ví dụ listener gọi database hoặc HTTP API. Có thể cần nhiều consumer hơn CPU cores để che thời gian chờ I/O, nhưng tổng concurrency phải thấp hơn hoặc bằng khả năng phục vụ của database, service downstream, channel pool và bộ nhớ.

Một phép ước lượng ban đầu theo định luật Little:

\[
\text{Số tác vụ đang xử lý trung bình} \approx
\text{Throughput mục tiêu (msg/s)} \times
\text{Thời gian xử lý trung bình (s/msg)}
\]

Ví dụ throughput mục tiêu `80 msg/s`, mỗi message mất trung bình `0,15 s`, cần khoảng **12 tác vụ đang hoạt động** trong điều kiện ổn định. Đây **không phải** công thức đặt chính xác `concurrency=12`: p99, thời gian DB wait, retry, network và giới hạn nguồn lực làm kết quả thực tế khác.

## 3. Bộ nhớ pod không chỉ là Java heap

### 3.1. Thành phần thường bị bỏ quên

~~~mermaid
flowchart TD
    LIMIT["Kubernetes memory limit"] --> JVM["Bộ nhớ tiến trình Java"]
    JVM --> HEAP["Java heap: payload, object, conversion"]
    JVM --> META["Metaspace & code cache"]
    JVM --> STACK["Thread stacks"]
    JVM --> NATIVE["Direct/native buffers, TLS, socket, GC"]
~~~

`-Xmx` chỉ giới hạn **heap**, không giới hạn toàn bộ RSS/cgroup memory. Một ứng dụng có heap 768 MiB và container limit 768 MiB vẫn có thể bị OOM do metaspace, thread stack, native memory, direct buffers và các vùng cấp phát khác.

Phân biệt:

- **`java.lang.OutOfMemoryError: Java heap space`:** heap không đáp ứng cấp phát; có thể cần tối ưu object/payload hoặc điều chỉnh `-Xmx`.
- **`OOMKilled` / exit code 137:** kernel/container runtime có thể đã chấm dứt container khi memory cgroup vượt giới hạn; không nhất thiết có Java stack trace.
- **GC pause dài:** heap pressure có thể làm ACK chậm, tăng unacked deliveries và làm consumer mất nhịp.

Theo dõi **JVM heap committed/used**, native/direct memory, số thread, GC time, và **container memory working set/RSS**. Không dùng duy nhất biểu đồ heap để kết luận pod còn dư RAM.

### 3.2. JVM phải biết giới hạn của container

Các JDK hiện đại hỗ trợ container awareness. Có thể cấu hình heap theo phần trăm RAM JVM nhìn thấy:

~~~text
JAVA_TOOL_OPTIONS:
  -XX:MaxRAMPercentage=55.0
  -XX:+ExitOnOutOfMemoryError
~~~

Đây là **điểm xuất phát thử nghiệm**, không phải quy tắc “55% luôn tối ưu”. `MaxRAMPercentage` không đặt hard limit cho metaspace, direct buffers và thread stacks; phải giữ headroom. `ExitOnOutOfMemoryError` giúp tiến trình kết thúc để supervisor có thể restart khi JVM thực sự phát sinh OOME, nhưng không chặn OOMKill từ kernel và không thay thế điều tra nguyên nhân.

Nếu sử dụng `-Xmx` cố định, bảo đảm Xmx nhỏ hơn memory limit đủ nhiều để chứa native overhead, và không lạm dụng `-Xms`/heap quá lớn với pod nhỏ. Nếu image hoặc version JDK rất cũ không hiểu cgroup/container memory, phải nâng JDK hoặc cấu hình giới hạn rõ ràng.

### 3.3. Prefetch và payload có thể chiếm nhiều heap

Ví dụ service có 12 consumer, `prefetch=32` và message trung bình 128 KiB:

\[
12 \times 32 \times 128\,\text{KiB} = 48\,\text{MiB}
\]

48 MiB chỉ là **ước lượng dữ liệu payload thô** nếu đủ 384 delivery đang unacked. Trong JVM, một message còn có headers, properties, các object sau deserialize, buffer trung gian và kết quả nghiệp vụ. Nếu chuyển thành object graph lớn, bộ nhớ thực tế có thể lớn hơn đáng kể.

| Tác động của prefetch | Điều quan sát | Biện pháp |
|---|---|---|
| Prefetch quá lớn với payload nặng | Heap/GC và `unacked` tăng | Giảm prefetch; giới hạn kích thước payload |
| Prefetch nhỏ, listener nhanh | Tốc độ nhận có thể bị giới hạn vì thiếu delivery in-flight | Tăng có đo đạc nếu downstream còn sức |
| Tăng replica và concurrency đồng thời | Tổng in-flight deliveries toàn hệ thống tăng | Tính ngân sách theo **số pod tối đa** |
| Listener deserialize payload trước khi validate | Message lớn gây burst allocation | Giới hạn payload, kiểm tra schema/size sớm |
| Retry ngay nhiều lần | CPU và memory spikes; message quay vòng | Backoff, giới hạn số lần và parking/DLQ |

**Không dùng prefetch làm giới hạn dung lượng tuyệt đối.** Broker/client còn giữ network buffer, task queue và dữ liệu ứng dụng. Mặt khác, công thức `consumers × prefetch` là upper bound xấp xỉ của unacked deliveries theo thiết lập QoS, không phải đo memory thực tế.

## 4. Tính ngân sách connection và channel theo mỗi pod

### 4.1. TCP connection có thể chứa nhiều AMQP channels

Với giao thức **AMQP 0-9-1**, RabbitMQ multiplex nhiều **channel** trên một TCP connection. Trong Spring AMQP, `CachingConnectionFactory` thường dùng **`CacheMode.CHANNEL`**, giữ một connection chia sẻ và tái sử dụng channel.

| Khái niệm | Cách tính hoặc cấu hình | Chú ý |
|---|---|---|
| `ConnectionFactory` | Bean quản lý connection tới RabbitMQ | Một JVM có thể có nhiều factory |
| `CacheMode.CHANNEL` | Mặc định một shared connection proxy mỗi factory; nhiều channels | Không có nghĩa mỗi listener dùng riêng một TCP connection |
| `CacheMode.CONNECTION` | Cache nhiều idle connections và channel trên từng connection | Thêm socket/thread, ảnh hưởng cơ chế auto-declaration |
| `RabbitTemplate` | Channel checkout/publish/return | Tùy concurrency, transaction và publisher confirm |
| SMLC | Thường một channel cho mỗi consumer | Khi consumer chạy lâu, channel được giữ lâu |
| DMLC | Thường mỗi consumer trên mỗi queue một channel | Tổng subscription tăng theo queue × consumersPerQueue |
| `RabbitAdmin` / health / request-reply | Có thể sử dụng channel khác | Cần headroom ngoài consumer và producer |

Ví dụ có 3 queue với `DirectMessageListenerContainer` và `consumersPerQueue=2`: tổng listener registrations có thể là **6**, tương ứng tối thiểu khoảng 6 consumer channels. Nếu dùng SMLC cho 3 queue cùng một container với 2 consumers, mô hình channel khác; phải kiểm tra container và số listener được khai báo thực tế.

### 4.2. channelCacheSize không phải hard limit theo mặc định

Điểm cấu hình quan trọng nhất của `CachingConnectionFactory`:

~~~text
channelCacheSize = 25
channelCheckoutTimeout = 0

=> Có thể tạo hơn 25 channels khi nhiều thread cần cùng lúc.
=> 25 chỉ là số channel rảnh tối đa có thể được cache
   trên connection (với các cache tương ứng).
~~~

Khi bật checkout timeout:

~~~text
channelCacheSize = 40
channelCheckoutTimeout = 2000 ms

=> Giới hạn số channel trên connection là 40.
=> Nếu đã chạm giới hạn, lần checkout tiếp theo phải chờ
   channel có thể dùng lại, tối đa khoảng 2 giây.
=> Hết hạn có thể ném AmqpTimeoutException.
~~~

**Ý nghĩa vận hành:** Giới hạn cứng giúp tránh mở channel vô hạn khi tải tăng, nhưng nếu không tính các consumer channels dài hạn thì producer có thể bị chặn ngay cả khi CPU/broker chưa quá tải. `channelCacheSize` và `channelCheckoutTimeout` phải được chọn **cùng nhau**.

Với `CacheMode.CONNECTION`, cần phân biệt thêm `connectionCacheSize` (số idle connections được cache) với `connectionLimit` (giới hạn tổng connections khi cấu hình). Chế độ nhiều connection không phải cách chữa backlog phổ quát và cần kiểm tra hỗ trợ auto-declaration của `RabbitAdmin`.

### 4.3. channel_max của broker là giới hạn riêng

RabbitMQ có tham số `channel_max` áp dụng cho mỗi connection (giá trị được thương lượng giữa client và broker). Giá trị broker có thể thay đổi theo phiên bản hoặc cấu hình hạ tầng. Một ứng dụng vẫn có thể bị chặn ở **giới hạn broker** ngay cả khi Spring cho phép mở thêm channel.

Phân biệt hai tình huống:

- **Spring hết channel checkout:** `channelCheckoutTimeout` dương và cache cap đã đầy; ứng dụng chờ rồi có thể ném `AmqpTimeoutException`.
- **RabbitMQ không cho mở thêm channel:** negotiated channel limit hoặc tài nguyên broker đã chạm ngưỡng; client nhận lỗi tạo channel hoặc connection/channel exception tương ứng.

Khi điều tra, hãy đối chiếu **Spring cache metrics, số channel thực trên broker, negotiated limits và logs**, không chỉ tăng một tham số.

### 4.4. Tính budget cho một service

Giả sử một pod có:

- Hai `@RabbitListener` SMLC riêng, mỗi listener tối đa 4 consumers → **8 consumer channels**.
- Một producer `RabbitTemplate` nhận tối đa 16 lời gọi publish đồng thời → **tối đa khoảng 16 publish channels đang dùng** nếu các lời gọi cùng cần channel riêng.
- `RabbitAdmin`, endpoint kiểm tra, request/reply và các thao tác nền khác → dự trù thêm **4 channels** cho ví dụ.
- Dành headroom khoảng 25% cho burst hoặc cấu hình thay đổi.

Ta có ước lượng:

\[
C_{\text{pod}} \approx (8 + 16 + 4) \times 1.25 = 35
\]

Như vậy có thể **thử** `channelCacheSize=40` với `channelCheckoutTimeout=2s` trong môi trường đo tải, thay vì đặt cap 8 rồi khiến producer bị treo. Đây là ví dụ lập ngân sách **giả định**: các channel transactional/nontransactional, connection factory tách biệt, long-lived RPC, publisher confirm và listener startup đều có thể khiến kết quả khác. Cần quan sát mức dùng thực tế và p95/p99 checkout delay.

**Không tính hết mọi channel của nhiều connection vào một cap duy nhất.** Giới hạn Spring trong CHANNEL mode xét theo connection/factory; nếu ứng dụng sử dụng **separate publisher connection**, publisher/consumer có các connection hoặc factory riêng. Phải chia budget theo từng nhóm, đồng thời cộng dồn tài nguyên ở broker.

### 4.5. Nhân ngân sách với replica tối đa

Nếu HorizontalPodAutoscaler (HPA) có `maxReplicas=12`:

~~~text
Một pod:
  1 consumer connection + 1 publisher connection   ≈ 2 TCP connections
  8 consumer channels + 16 publish channels + headroom ≈ 35 channels

Tối đa 12 pods:
  ≈ 24 TCP connections cho hai đường trên
  ≈ 420 channels của các kết nối ứng dụng

Chưa kể:
  RabbitAdmin, health checks, các microservice khác,
  broker monitoring, stream consumers, connection churn.
~~~

Đây là **sizing estimate**, không phải một bảo đảm cố định về số socket. Một số connection factory có thể không tạo publisher connection khi chưa dùng; ngược lại mỗi pod có thể chứa nhiều factories. Số channel thực phụ thuộc tải. Điểm quan trọng là **broker phải chịu được ngân sách toàn bộ deployment tại mức replica tối đa**, không chỉ số đo ở một pod.

## 5. Tách publisher và consumer khi cần

Khi broker gặp memory/disk alarm, RabbitMQ có thể **block connection của publisher**. Một service vừa nhận vừa publish trên chung connection có thể chịu tác động tương tác giữa hai đường. Spring AMQP cho phép `RabbitTemplate.setUsePublisherConnection(true)` để dùng publisher connection riêng khi phù hợp.

~~~java
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PublisherConfig {
    @Bean("outboundRabbitTemplate")
    RabbitTemplate outboundRabbitTemplate(
            CachingConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setUsePublisherConnection(true);
        return template;
    }
}
~~~

**Tác dụng:** giảm khả năng producer và consumer ảnh hưởng lẫn nhau qua cùng một connection. **Chi phí:** có thêm TCP connection, I/O threads và channel cache cần quan sát. Nếu publisher hoạt động trong transaction cần dùng consumer channel, Spring có những điều kiện không thể chuyển sang publisher connection riêng; phải đánh giá theo đường transaction cụ thể.

Tách connection không làm DB + RabbitMQ thành một giao dịch phân tán. Nếu một nghiệp vụ cần commit database rồi phát event chắc chắn, **transactional outbox** vẫn là giải pháp phù hợp; nếu chỉ cần xác nhận broker đã xử lý publish, dùng publisher confirms và mandatory returns theo chính sách routing.

## 6. Executor, consumer concurrency và sức chứa của downstream

### 6.1. SMLC và DMLC sử dụng thread theo cách khác

| Thành phần | `SimpleMessageListenerContainer` (SMLC) | `DirectMessageListenerContainer` (DMLC) |
|---|---|---|
| Nhận delivery từ Rabbit Java client | Client callback đưa message tới queue nội bộ của container | Client callback trực tiếp chạy listener |
| `taskExecutor` của container | Chạy listener consumer threads | Chủ yếu phục vụ monitoring/consumer management |
| Rabbit Java client executor | Dispatch callback rồi handoff | **Quan trọng đối với thời gian chạy listener** |
| Số consumer | `concurrentConsumers`/`maxConcurrentConsumers` | `consumersPerQueue` trên mỗi queue |
| Tác động khi listener chậm | Chiếm SMLC task thread | Có thể chiếm Rabbit client callback thread |

Với SMLC, một consumer có thể chiếm thread dài hạn trong `TaskExecutor`; pool phải đủ lớn so với `maxConcurrentConsumers`. Với DMLC, đừng tăng container task executor rồi kỳ vọng tăng số thread thực thi listener — cần kiểm tra `CachingConnectionFactory.setExecutor` và cấu hình `consumersPerQueue`.

### 6.2. Tối ưu executor mà không ACK sớm

Nếu listener tự đẩy công việc sang một `ExecutorService` rồi return trước khi DB commit, container ở `AcknowledgeMode.AUTO` có thể ACK ngay sau khi method trả về. Khi task nền thất bại, broker đã xem delivery là hoàn tất.

**Giải pháp:** xử lý đồng bộ đến khi commit; hoặc sử dụng kiểu listener bất đồng bộ được phiên bản Spring AMQP hỗ trợ để settlement phụ thuộc completion; hoặc ghi việc cần làm vào nơi lưu bền vững trước khi ACK. Không coi `executor.submit(...)` là một cách tăng concurrency an toàn nếu không thiết kế lại vòng đời ACK.

### 6.3. Downstream thường là giới hạn thật

Giả sử một pod có 16 consumers nhưng database pool chỉ có 8 connections:

~~~text
16 listeners muốn SQL transaction cùng lúc
    |
    +-- 8 listeners lấy được DB connection
    |
    +-- 8 listeners chờ pool, giữ thread + unacked delivery
                    |
              timeout / retry / redelivery
~~~

Nếu database đã bão hòa, tăng `concurrency` lên 32 làm tải xấu hơn. Cần phối hợp:

- Giới hạn consumer concurrency theo DB connection pool và query duration.
- Prefetch vừa đủ; tránh giữ hàng trăm unacked messages trong JVM.
- Timeout/connection pool settings và backoff khi downstream tạm lỗi.
- Rate limit hoặc circuit breaker thích hợp cho API ngoài.
- DLQ/parking-lot cho lỗi vĩnh viễn; không requeue nóng.

## 7. Spring Boot: cấu hình một baseline có thể kiểm thử

Ví dụ dành cho service AMQP **0-9-1**, dùng `CachingConnectionFactory` ở CHANNEL mode, SMLC và publisher confirms:

~~~yaml
# application.yml — giá trị minh họa, cần benchmark trước production
spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
  rabbitmq:
    host: rabbitmq.internal.example
    port: 5672
    virtual-host: orders
    connection-timeout: 5s
    requested-heartbeat: 30s
    cache:
      connection:
        mode: channel
      channel:
        size: 40
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
        prefetch: 16
        acknowledge-mode: auto

server:
  shutdown: graceful
~~~

**Lưu ý về ví dụ:** `5672` minh họa AMQP không TLS cho mạng thử nghiệm. Production thường nên dùng AMQPS/TLS và credentials được quản lý bằng secret; xác minh CA và hostname. Các giá trị 40/2s/4–8/16 là **baseline để thử**, không phải giá trị mặc định tối ưu.

| Thuộc tính | Ý nghĩa | Rủi ro nếu chọn không đúng |
|---|---|---|
| `spring.rabbitmq.cache.connection.mode` | Chọn `channel` thay vì `connection` | CONNECTION mode thêm socket/cache, tác động RabbitAdmin |
| `spring.rabbitmq.cache.channel.size` | Số channel cache hoặc channel cap có điều kiện | Quá thấp gây churn/timeout, quá lớn tăng broker resources |
| `spring.rabbitmq.cache.channel.checkout-timeout` | Đợi lấy channel; khi dương làm cap có hiệu lực | Request có thể chờ hoặc lỗi khi hết channel |
| `spring.rabbitmq.listener.simple.concurrency` | Số consumer SMLC tối thiểu | Tăng threads/channels và DB transactions |
| `spring.rabbitmq.listener.simple.max-concurrency` | Số consumer SMLC tối đa | Autoscale trong pod còn phụ thuộc executor capacity |
| `spring.rabbitmq.listener.simple.prefetch` | Giới hạn unacked deliveries phù hợp mỗi consumer | Payload lớn làm heap tăng |
| `publisher-confirm-type: correlated` | Theo dõi publish accept/nack | Không đồng nghĩa consumer xử lý thành công |
| `publisher-returns: true` + `mandatory` | Phát hiện routing không tới queue | Cần xử lý returned message, không chỉ confirm ACK |
| `server.shutdown` và `timeout-per-shutdown-phase` | Cho Spring thời gian dừng các lifecycle beans | Phải phối hợp timeout pod, listener và downstream |

Spring Boot hỗ trợ external configuration: đừng hardcode password trong repo; đặt connection data trong Kubernetes Secret, secret manager hoặc biến môi trường theo quy chuẩn vận hành.

### 7.1. Java config để giới hạn channel có chủ đích

Nếu dùng Spring Framework thuần hoặc cần tự quản lý bean:

~~~java
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class RabbitConnectionConfiguration {

    @Bean
    CachingConnectionFactory connectionFactory() {
        CachingConnectionFactory factory =
                new CachingConnectionFactory("rabbitmq.internal.example");
        factory.setVirtualHost("orders");
        factory.setChannelCacheSize(40);
        factory.setChannelCheckoutTimeout(2_000L);

        // Trong production bổ sung TLS, secret, reconnect policy
        // và executor phù hợp phiên bản RabbitMQ Java Client.
        return factory;
    }
}
~~~

Đây là **cách thay thế** cho auto-configuration, không nên đồng thời tạo factory thủ công và để Spring Boot tạo factory khác ngoài ý muốn. Nếu thay `channelCacheSize` trên một factory đang chạy có cap dương, có thể cần khởi tạo connection mới để áp dụng giới hạn; nên thực hiện bằng rollout có kiểm soát.

### 7.2. Lập giới hạn cả trên RabbitMQ broker

Broker có thể cấu hình `channel_max` và các giới hạn connection/tài nguyên phù hợp. Nhưng thay broker limit ảnh hưởng **mọi** service sử dụng node đó, nên không dùng như cách chữa hết timeout của một deployment.

Một quy trình an toàn:

1. Tính tổng số connection/channel tại **maxReplicas** của các ứng dụng cùng sử dụng broker/vhost.
2. Kiểm tra giới hạn và số thực tế bằng management/metrics và `rabbitmq-diagnostics` trên broker được phép.
3. Đảm bảo channel cap của client nằm trong giới hạn negotiated của broker.
4. Giữ headroom cho admin, monitoring, consumer failover và rolling updates.
5. Khi chạm broker limit, ưu tiên điều tra channel leaks, cache mode, excessive connections hoặc scaling runaway trước khi tăng limit.

**Không coi max channel per connection là tổng max channel của broker.** Nếu 10 connection mỗi connection có cap 40, tổng channel có thể tới xấp xỉ 400 — chưa tính các connection khác.

## 8. Kubernetes Deployment: requests, limits và shutdown

Ví dụ manifest triển khai **một Spring Boot consumer service**; thay image và endpoint theo hạ tầng thật:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-consumer
  namespace: applications
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: orders-consumer
  template:
    metadata:
      labels:
        app: orders-consumer
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: orders-consumer
          image: registry.example.com/orders-consumer:1.3.0
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "768Mi"
            limits:
              cpu: "1500m"
              memory: "1536Mi"
          env:
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=55.0 -XX:+ExitOnOutOfMemoryError"
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            initialDelaySeconds: 10
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 2
~~~

Manifest này giả định ứng dụng có **Spring Boot Actuator health probes** đang được bật và lắng nghe trên cổng 8080. Với consumer-only không có HTTP server, phải dùng cách probe khác hoặc bổ sung health endpoint có chủ đích. Không expose Actuator nhạy cảm ngoài mạng tin cậy.

**Tại sao requests và limits khác nhau?**

- Request `500m`/`768Mi` giúp scheduler dự trù tài nguyên; thực tế pod có thể dùng nhiều hơn request khi node còn khả năng.
- CPU limit `1500m` tạo trần CPU và có thể throttle nếu tải vượt.
- Memory limit `1536Mi` là hard limit ở cgroup cho container; JVM phải giữ headroom cho heap, native memory và thread stacks.
- Các sidecar khác trong pod **có resource requests/limits riêng** theo cấu hình của chúng; không tự trừ heap Java vào giới hạn memory của một sidecar.

Nếu service rất nhạy latency, phải đo ảnh hưởng của CPU limit/throttling và cân nhắc chính sách quota phù hợp với cluster. **Không bỏ mọi giới hạn một cách máy móc:** thiếu giới hạn hoặc requests phù hợp có thể làm node quá tải và tăng rủi ro gián đoạn nhiều workload.

### 8.1. Readiness không nhất thiết phản ánh consumer thật sự sẵn sàng

Readiness HTTP thành công chỉ cho biết ứng dụng đáp ứng probe đã cấu hình. Nó **không tự chứng minh** `@RabbitListener` đã đăng ký được queue, connection còn tốt hoặc backlog đang được xử lý.

Một consumer-only service có thể sẵn sàng nhận AMQP nhưng không phục vụ HTTP request; khi đó Kubernetes Service readiness và listener health là hai tầng khác nhau. Có thể bổ sung health indicator/metric cho listener registry, nhưng không nên đưa lỗi RabbitMQ tạm thời vào **liveness** khiến tất cả pod cùng restart trong lúc broker đang lỗi.

Mẫu quan sát tốt:

- **Liveness:** tiến trình JVM còn khỏe, không deadlock hoặc không khôi phục được.
- **Readiness:** ứng dụng sẵn sàng nhận traffic thuộc vai trò của nó; nếu là HTTP service, chặn request mới khi đang shutdown.
- **Messaging health:** connection, listener containers, số consumer active, queue lag và publisher confirm errors dưới dạng chỉ số/alert riêng.

### 8.2. Graceful shutdown bảo vệ delivery đang xử lý

Khi deployment scale down hoặc rolling update, Kubernetes gửi `SIGTERM`, chờ `terminationGracePeriodSeconds`, sau đó có thể gửi `SIGKILL` nếu pod chưa thoát.

Thứ tự mong muốn:

~~~mermaid
sequenceDiagram
    participant K as Kubernetes
    participant A as Spring application
    participant L as @RabbitListener
    participant DB as Database
    participant B as RabbitMQ
    K->>A: SIGTERM
    A->>L: Dừng nhận delivery mới theo lifecycle
    L->>DB: Kết thúc transaction đang chạy
    DB-->>L: COMMIT
    L->>B: ACK nếu channel còn mở
    L-->>A: Listener dừng
    A-->>K: Process exit
~~~

Nếu pod bị kill trước khi transaction/ACK hoàn tất, RabbitMQ có thể giao lại unacked delivery khi connection đóng. Điều đó là hành vi **at-least-once**, không phải lý do bỏ ACK; consumer phải idempotent.

Đặt `terminationGracePeriodSeconds` lớn hơn thời gian thực tế cần thiết cho shutdown của listener và lifecycle của Spring, kể cả business transaction. Không đặt thời gian quá dài vô điều kiện; cần timeout nghiệp vụ và đường khôi phục khi một task treo. Với request/reply hoặc listener async, phải quan sát các Future/tác vụ đang chờ.

### 8.3. RollingUpdate còn làm tăng ngân sách tài nguyên tạm thời

Với `maxSurge=1`, nếu deployment đang có 12 replicas thì rollout có thể có **13 pods** tạm thời, chưa tính pod cũ đang termination nhưng chưa giải phóng socket hoàn toàn. Broker cần headroom cho connection/channel churn trong lúc deploy.

Mặt khác `maxUnavailable=0` không tự đảm bảo RabbitMQ có đúng consumer healthy: readiness probe chỉ kiểm tra điều kiện bạn cấu hình. Cần theo dõi **consumer count**, queue lag và các lỗi listener khi rollout.

## 9. Autoscaling: tăng pod cũng tăng connection, channel và unacked

### 9.1. HorizontalPodAutoscaler theo CPU

Ví dụ Kubernetes HPA `autoscaling/v2`:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-consumer
  namespace: applications
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-consumer
  minReplicas: 2
  maxReplicas: 12
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
~~~

HPA CPU utilization được tính **so với CPU request** của container có liên quan, không trực tiếp so với CPU limit. Nếu chỉ đặt limit mà thiếu request phù hợp, metric CPU utilization có thể không đủ dữ liệu để HPA hoạt động như mong muốn.

HPA giúp xử lý tải **CPU-bound** nhưng **không đảm bảo xử lý backlog RabbitMQ nhanh hơn**:

- Nếu service CPU thấp vì đang đợi database/API, HPA theo CPU có thể không scale dù queue backlog lớn.
- Nếu mỗi pod mở thêm 8 consumers, tăng từ 2 lên 12 replicas có thể tăng consumer registrations từ 16 lên 96 cho cùng các listener, làm database chịu áp lực đột ngột.
- Nếu RabbitMQ đang có memory/disk alarm, scale-out consumers có thể giải quyết backlog trong một số trường hợp nhưng cũng có thể làm tăng connection, channel, ACK và I/O load.

### 9.2. Scale theo queue lag/độ trễ thay vì chỉ CPU

Với workload chủ yếu chờ message, có thể cân nhắc **external metrics** hoặc KEDA RabbitMQ scaler theo queue length, message rate hay chỉ số phù hợp với phiên bản/scaler. Nhưng cần định nghĩa rõ:

| Chỉ số | Khi hữu ích | Cẩn trọng |
|---|---|---|
| `messages_ready` | Backlog đang chờ delivery | Không phản ánh message đã giao nhưng đang chờ ACK |
| `messages_unacknowledged` | Số delivery in-flight | Cao có thể do prefetch lớn, không phải luôn thiếu pod |
| Tuổi message lâu nhất | SLO trễ xử lý | Cần metric riêng và clock/retention chính xác |
| End-to-end processing lag | Nhu cầu mở rộng theo thời gian hoàn tất nghiệp vụ | Đòi hỏi instrumentation theo event ID/timestamp |
| CPU/memory saturation | Pod thực sự thiếu compute hoặc heap | Có thể là triệu chứng của lỗi code/GC/retry |
| Database pool wait / downstream 429 | Downstream đang quá tải | Nên **giảm hoặc giới hạn** concurrency thay vì scale-out |

Ví dụ nếu queue có 100.000 messages nhưng database chỉ xử lý được 200 transactions/giây, thêm 50 pod không tạo thêm throughput thật, còn tăng contention. Hãy đặt **maxReplicas dựa trên năng lực broker và downstream**, không chỉ theo độ dài queue.

### 9.3. Phân phối message khi có nhiều replicas

Các pod cùng consume một queue sẽ là **competing consumers**. Đây thường là cách scale-out tự nhiên, nhưng không giữ thứ tự hoàn tất nghiệp vụ khi nhiều consumer xử lý song song. Nếu yêu cầu thứ tự theo `orderId`, cần routing theo shard, single-active-consumer hoặc version guard phù hợp; HPA có thể làm thay đổi cách phân phối consumers.

Khi scale down, các delivery đang unacked có thể được hoàn tất trong grace period hoặc redeliver sau khi channel/connection đóng. Đừng dựa vào “pod chỉ chạy một lần” để đạt exactly-once; giữ `eventId` ổn định và sử dụng inbox/unique business key.

## 10. Bài toán sizing mẫu từ Pod tới RabbitMQ

Giả sử hệ thống đặt hàng có các yêu cầu **minh họa**:

- Peak 600 event/giây trong 10 phút, payload trung bình 128 KiB.
- Thời gian xử lý trung bình 0,12 giây/event, p99 cao hơn do database.
- Chạy 3 pod ban đầu, HPA tới 12 pod và có `maxSurge=1`.
- Mỗi pod có tối đa 8 SMLC consumers, `prefetch=16`.
- Mỗi pod có 1 connection consumer và 1 publisher connection khi đường publisher được dùng.
- Channel cap được sizing 40 trên connection chính; publisher connection có ngân sách riêng.

### 10.1. Ước lượng concurrency

Theo định luật Little:

\[
600\ \text{msg/s} \times 0.12\ \text{s/msg}
= 72\ \text{tasks đang xử lý trung bình}
\]

Với 12 pod × 8 consumers = **96 consumer slots** ở mức tối đa. Đây là năng lực song song danh nghĩa, **không bảo đảm đạt 600 msg/s** nếu DB pool/CPU/network không đủ; cần test steady state và tail latency. Với chỉ 3 pod × 8 = 24 slots, ước lượng lý tưởng khoảng 200 msg/s nếu thời gian xử lý 0,12s giữ nguyên.

### 10.2. Ước lượng unacked và bộ nhớ payload

Tại maxReplicas 12:

\[
12\ \text{pods} \times 8\ \text{consumers/pod} \times 16\ \text{prefetch}
= 1536\ \text{deliveries}
\]

Nếu mỗi delivery chứa payload thô 128 KiB thì tối đa theo phép tính xấp xỉ:

\[
1536 \times 128\ \text{KiB} = 192\ \text{MiB payload thô}
\]

Khi rolling update có thêm 1 pod, con số có thể là **13 × 8 × 16 = 1664 deliveries**, tương ứng **208 MiB payload thô** toàn deployment. Đây chưa tính object deserialization, headers, GC và dữ liệu nghiệp vụ. Không thể lấy 208 MiB chia đều bất kỳ để đặt memory limit: mỗi pod có thể tải khác nhau và heap/native memory còn nhiều khoản khác.

### 10.3. Ước lượng connection/channel

~~~text
Steady state với 12 pods:
  12 consumer connections + tối đa khoảng 12 publisher connections
  = khoảng 24 connections nếu cả hai đường được mở

Rolling update tạm có 13 pods:
  khoảng 26 connections

Channel budget:
  mỗi pod có thể tới ~35 channels theo giả định sizing,
  khoảng 455 channels toàn deployment tại 13 pods
  (phân bố trên nhiều connection/factory).
~~~

**Hệ thống còn các dịch vụ khác dùng RabbitMQ**, nên tính tổng trên toàn broker/cluster, đồng thời dự phòng kết nối admin/metrics/replication phù hợp. Đừng gộp số channel của nhiều connection rồi so trực tiếp với `channel_max` per connection.

### 10.4. Kết luận sizing

Từ những con số trên có thể lập **giả thuyết để test**, không thể kết luận ngay:

1. Nếu 3 pod đã tạo backlog ở peak, đo xem CPU/DB/broker giới hạn ở đâu.
2. Nếu DB còn năng lực, tăng số pod hoặc consumer theo từng bước, giữ `channel cap` và client executor đủ chỗ.
3. Theo dõi p95/p99 processing latency, disk/memory alarms của RabbitMQ và backlog.
4. Khi thấy saturation, giảm burst hoặc đặt backpressure; không tiếp tục tăng replica vô hạn.

## 11. Kịch bản đo và stress test trước triển khai

Không chỉ test happy path. Các giới hạn CPU, memory và channel thường phát lộ khi tải tăng đột ngột hoặc một dịch vụ downstream bị chậm.

| Kịch bản | Điều chỉnh trong staging | Điều cần xác minh |
|---|---|---|
| CPU bị giới hạn chặt | Giảm CPU limit hoặc tạo tải CPU-bound | Throttling, p99 listener/confirm latency và heartbeat behavior |
| Memory gần giới hạn | Message lớn, prefetch cao hoặc payload deserialization nặng | GC tăng/OOM; không ACK trước DB commit |
| Thấp channel cap | `size=8`, `checkout-timeout=2s` với nhiều consumer/publisher | Timeout được xử lý có backoff; không mất outbox event |
| Bỏ channel cap | `checkout-timeout=0` và burst publish | Channel churn/count trên broker; cache không phải hard limit |
| Hết RabbitMQ `channel_max` | Dùng broker staging với negotiated limit nhỏ | Client phát hiện lỗi tạo channel, cảnh báo có ý nghĩa |
| Nhiều pods tăng cùng lúc | HPA maxReplicas hoặc scale thử | Total sockets/channels, CPU/memory/disk broker và DB load |
| Downstream database chậm | Giới hạn DB pool, tăng SQL latency | Unacked tăng, pool wait, timeout; không tạo retry storm |
| Cắt kết nối khi publish chưa confirm | Proxy/fault injection | Outcome chưa rõ; retry cùng event ID, consumer dedup |
| Kill pod sau DB commit trước ACK | Fault injection với consumer thật | Redelivery có thể xảy ra, không ghi nghiệp vụ hai lần |
| Rolling update | maxSurge/termination grace như production | Listener dừng hợp lý; không mất quorum/broker health |
| Broker flow control | Kích hoạt alarm ở staging có kiểm soát | Publisher blocked, backlog, khả năng phục hồi |
| Poison message | Payload lỗi liên tục | Retry hữu hạn, DLQ/parking và metric lỗi |

**Dùng RabbitMQ thật** ở staging hoặc Testcontainers cho kiểm thử integration/fault. Mock `RabbitTemplate` không mô phỏng channel checkout, broker flow control, ACK bị mất hoặc redelivery.

### Quy trình benchmark từng bước

1. Cố định RabbitMQ, Erlang, Spring AMQP, Java Client, JDK, TLS, queue type, durable flags và publisher confirm policy.
2. Chạy warm-up đủ để cache channel, JIT và pool database ổn định.
3. Phát tải tăng dần (ví dụ 100 → 200 → 400 → 600 msg/s) cùng kích thước payload.
4. Ghi **throughput nghiệp vụ đã commit**, p50/p95/p99 latency, RabbitMQ ready/unacked, CPU throttling, RSS/GC và channel count.
5. Thay **một tham số chính mỗi lần**: concurrency, prefetch, channel cache/cap, JVM heap headroom hoặc maxReplicas.
6. Thử peak ngắn, peak kéo dài, traffic giảm và restart/rolling deployment.
7. So số event phát, nhận và business effect đã commit; kiểm tra duplicate, retry/DLQ và publish returns.
8. Ghi lại cấu hình, biểu đồ và quyết định cuối cùng theo SLO; không chỉ chọn run có messages/giây cao nhất.

## 12. Quan sát và cảnh báo theo từng lớp giới hạn

Một dashboard RabbitMQ đơn lẻ không đủ. Khi ứng dụng bắt đầu xử lý chậm, cần biết nó đang chậm **trước khi nhận message, trong listener, lúc đợi DB hay khi chờ channel**.

| Lớp | Metric / log cần thu | Dấu hiệu nên cảnh báo |
|---|---|---|
| Kubernetes CPU | CPU usage theo request/limit; throttled periods và throttled time | Throttling kéo dài cùng p99 latency tăng |
| Kubernetes memory | Container RSS/working set; memory limit; OOMKilled/restarts | Memory tăng bền vững, OOMKill, GC bất thường |
| JVM | Heap used/committed/max, metaspace, direct buffers, GC pause, live threads | Heap sát trần, native memory tăng, GC chiếm nhiều thời gian |
| Spring Rabbit connection | Connection open/closed, reconnect count, ConnectionBlockedEvent | Churn hoặc broker flow control |
| Channel/cache | `getCacheProperties()`, idle/high-water, channel opened/closed và checkout timeout | Channel churn hoặc cap luôn đầy |
| Listener | SMLC/DMLC consumer count, listener processing time, errors | Ít consumer hơn cấu hình; xử lý lâu |
| Broker queue | `messages_ready`, `messages_unacknowledged`, deliver/ack/redeliver rates | Backlog kéo dài, unacked tăng, redelivery đột biến |
| Publisher | Confirm in-flight/latency, NACK, returned messages | Message route sai hoặc broker/connection chậm |
| Downstream | DB pool active/idle/pending, SQL latency, HTTP 429/5xx/timeouts | Tăng pod chỉ làm tăng tranh chấp |
| Retry/DLQ | Retry attempts, DLQ count, tuổi message lỗi | Poison message hoặc circuit breaker chưa hoạt động |

### 12.1. Chỉ số Kubernetes cần đặt cạnh latency

Khi sử dụng cAdvisor/Prometheus, các tên metric thường thấy gồm:

~~~text
container_cpu_usage_seconds_total
container_cpu_cfs_throttled_periods_total
container_cpu_cfs_throttled_seconds_total
container_memory_working_set_bytes
kube_pod_container_status_restarts_total
~~~

Sự tồn tại/tên cụ thể phụ thuộc Kubernetes, runtime, cAdvisor và bộ exporter/recording rules. Đừng copy một biểu thức PromQL mà chưa xác nhận metric thật trong cluster. CPU throttling phải được đối chiếu với **listener latency** và **CPU usage**, vì metric thô cao một mình không chỉ ra chính xác nơi nghẽn.

### 12.2. Theo dõi channel cache bằng Spring

`CachingConnectionFactory.getCacheProperties()` có các số liệu như `channelCacheSize`, số idle channels và high-water mark (tùy cache mode và phiên bản):

~~~java
import java.util.Properties;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;

public class RabbitCacheDiagnostics {
    private final CachingConnectionFactory factory;

    public RabbitCacheDiagnostics(CachingConnectionFactory factory) {
        this.factory = factory;
    }

    public Properties snapshot() {
        return factory.getCacheProperties();
    }
}
~~~

Nên xuất dưới dạng gauge/metric theo chu kỳ hoặc log có kiểm soát, không gọi/lưu toàn bộ properties với mỗi message. High-water mark **chạm cache size không nhất thiết là lỗi**; cần xem số channel được tạo/đóng, checkout wait/timeout, broker utilization và publish p99.

### 12.3. Ví dụ diễn giải đồ thị

**Tình huống A:** CPU usage cao, throttling cao, queue lag tăng nhưng DB pool còn rảnh. Khả năng listener CPU-bound; thử tăng CPU limit/request hoặc tối ưu conversion và giảm GC trước khi nâng replica.

**Tình huống B:** CPU thấp, `messages_unacknowledged` cao, DB pool pending lớn và SQL p99 chậm. Nhiều consumer đang chờ DB; giảm concurrency/prefetch hoặc tối ưu DB, không tăng HPA.

**Tình huống C:** Publish latency p99 tăng, `AmqpTimeoutException` xuất hiện, nhưng RabbitMQ CPU thấp. Kiểm tra channel cap/checkout timeout, long-lived consumer channels và request/reply; có thể thiếu channel dù broker còn rảnh.

**Tình huống D:** `OOMKilled` sau khi bật prefetch cao với payload lớn, heap graph vẫn còn khoảng trống. Đo native/direct memory, buffer, thread stacks và RSS; đừng chỉ tăng `-Xmx`.

## 13. Runbook khắc phục sự cố

### 13.1. Pod bị OOMKilled

1. Kiểm tra `kubectl describe pod`, container termination reason và restart count (theo quyền vận hành được cấp).
2. So memory limit, container RSS/working set và JVM heap + native memory.
3. Kiểm tra thay đổi gần nhất: số consumers, prefetch, payload size, deserialization, retry loop.
4. Giảm burst/concurrency/prefetch nếu cần để khôi phục, nhưng không che memory leak bằng việc tăng limit không giới hạn.
5. Khi pod restart, kiểm tra unacked redelivery và inbox/idempotency; tránh ghi nghiệp vụ trùng.
6. Sau khi chỉnh memory/JVM settings, chạy lại peak load và theo dõi GC ít nhất trong khoảng thời gian đủ dài.

### 13.2. Bị lỗi lấy channel

1. Xác minh `channelCheckoutTimeout` có dương hay không; `channelCacheSize` thực tế và cache mode.
2. Đo số consumer channels, producer concurrent calls, request/reply channels, transactional channel groups.
3. So sánh Spring cache high-water và channel count thực trên broker.
4. Phân biệt checkout timeout của Spring với negotiated `channel_max` hoặc lỗi channel do broker đóng.
5. Giảm concurrency không thiết yếu, tách publisher connection nếu hợp lý hoặc tăng cap **có đo tải**.
6. Nếu publish outcome không xác định do lỗi channel/connection, retry qua outbox với cùng `eventId` và consumer idempotent.

### 13.3. Backlog tăng dù tăng số replica

1. Kiểm tra consumer count có thực sự tăng hay listener không thể kết nối/đăng ký queue.
2. Đo throughput **business commits/s**, không chỉ số deliveries/s.
3. Kiểm tra DB/API downstream và timeout; nếu bão hòa, thêm replicas không giải quyết được bottleneck.
4. Kiểm tra broker resource alarms, queue leader/replication, disk I/O và flow control.
5. Quan sát prefetched-unacked và memory; giảm prefetch nếu message đang tích tụ trong ứng dụng.
6. Điều chỉnh HPA/KEDA theo lag và năng lực downstream, thêm cooldown để tránh scale lên/xuống liên tục.

### 13.4. Nhiều reconnect sau khi giới hạn CPU

1. Kiểm tra throttling cùng JVM GC pause, blocked threads và RabbitMQ heartbeat logs.
2. Xác định mạng/proxy idle timeout có làm ngắt connection hay không.
3. Nếu CPU quota quá thấp, tăng headroom hoặc giảm listener work CPU-bound.
4. Kiểm tra config `requested-heartbeat`/connection timeout và executor thực thi callback.
5. Khôi phục publisher confirmations chưa rõ và consumer unacked theo nguyên tắc at-least-once; đừng cố ACK bằng delivery tag của channel đã đóng.

## 14. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “CPU request 500m nghĩa là container luôn chỉ dùng được nửa core” | Request phục vụ scheduling/chia tài nguyên; CPU limit mới tạo quota trần |
| “CPU limit chỉ ảnh hưởng tính toán, không ảnh hưởng RabbitMQ” | Callback, heartbeat, serialization, ACK và health checks đều cần CPU |
| “-Xmx bằng memory limit thì an toàn” | JVM còn metaspace, native/direct buffers, thread stacks và GC |
| “Không thấy Java heap OOME nghĩa là không thể OOMKilled” | Kernel có thể kill do memory cgroup dù heap chưa đầy |
| “Cache channel 25 là tối đa 25 channel” | Khi `checkoutTimeout=0`, 25 chỉ là cache idle size |
| “channel_max của RabbitMQ là số channel tối đa toàn cluster” | Giới hạn đó áp dụng cho từng connection được thương lượng |
| “Thêm một pod chỉ tốn thêm CPU” | Pod còn mở TCP connection, channels, consumers, in-flight deliveries và DB connections |
| “Tăng concurrency và prefetch cùng lúc sẽ nhanh gấp đôi” | Có thể khiến DB/heap/channels bị bão hòa và làm p99 xấu hơn |
| “SMLC và DMLC dùng cùng taskExecutor để chạy listener” | SMLC chạy listener trên taskExecutor; DMLC chạy trực tiếp trên RabbitMQ client threads |
| “Readiness HTTP xanh nghĩa là listener RabbitMQ khỏe” | Phải kiểm tra listener/container, queue lag và connection riêng |
| “SIGTERM bảo đảm mọi delivery đang xử lý sẽ ACK xong” | Hết grace period có thể bị kill; message chưa ACK sẽ redeliver |
| “HPA maxReplicas là số pod tối đa trong rolling update” | `maxSurge` có thể tạo thêm pod tạm thời |
| “Khi RabbitMQ chậm, chỉ cần tăng maxReplicas” | Broker hoặc DB có thể là nút thắt; scale-out làm tải tăng thêm |
| “Publisher confirms và connection cache giải quyết exactly-once” | Vẫn cần outbox/idempotency và kiểm soát ACK/retry để chịu duplicate |

## 15. Checklist trước khi đưa một service vào production

1. **Workload/SLO:** ghi peak msg/s, payload p95/p99 size, thời gian xử lý, queue type, replay/ordering và durability.
2. **CPU:** đặt requests/limits hợp lý, đo throttling, concurrency và p99 latency.
3. **Memory:** đặt container limit với headroom ngoài JVM heap; đo RSS, GC, native memory và số threads.
4. **Prefetch:** tính `activeConsumers × prefetch × payload`, kiểm tra memory và unacked trên broker.
5. **Connection:** biết mỗi pod có bao nhiêu factory, TCP connections và publisher connections.
6. **Channel:** phân biệt cache idle và cap, cấu hình `channelCheckoutTimeout` có chủ đích; so với broker `channel_max`.
7. **Executor:** SMLC listener pool và DMLC client executor được sizing theo cách chạy thực tế.
8. **Downstream:** consumer concurrency không vượt khả năng DB/API; có backoff/circuit breaker khi tạm lỗi.
9. **Reliability:** publisher confirms + returns, ACK sau commit, retry hữu hạn, DLQ, transactional outbox và idempotency khi cần.
10. **Scaling:** tính tài nguyên theo HPA `maxReplicas`, `maxSurge` và tổng các microservice cùng sử dụng broker.
11. **Shutdown:** SIGTERM/grace period/lifecycle timeout được thử; redelivery sau crash không nhân đôi tác dụng.
12. **Monitoring:** CPU throttling, OOMKilled, channels, broker alarms, ready/unacked, confirms, DLQ và DB pool wait có dashboard/alert.
13. **Benchmark:** đo steady state, burst, downstream failure, rolling deploy và recovery trên broker thật.
14. **Bảo mật:** TLS, user/vhost permissions, network isolation cho broker Management/Prometheus và secret rotation.
15. **Rollback/runbook:** có cách giảm concurrency/replica khẩn cấp, giữ outbox event và xử lý dữ liệu còn ở DLQ.

### Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring AMQP — Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): `CachingConnectionFactory`, channel cache modes, checkout timeout, cache statistics.
- [Spring AMQP — Threading and Asynchronous Consumers](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/threading.html): khác biệt executor của SMLC và DMLC.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): `concurrentConsumers`, `maxConcurrentConsumers`, `consumersPerQueue`.
- [Spring AMQP — Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): prefetch, ACK, shutdown và các tùy chọn container.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.rabbitmq.*` và cấu hình cache/listener.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU/memory requests, limits và ảnh hưởng cgroup.
- [Kubernetes — Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/): HPA CPU utilization, replica bounds và scaling behavior.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): SIGTERM, grace period và quá trình dừng pod.
- [RabbitMQ — Connections](https://www.rabbitmq.com/docs/connections): tài nguyên TCP connection, heartbeats và giới hạn.
- [RabbitMQ — Channels](https://www.rabbitmq.com/docs/channels): AMQP channels, negotiated channel max và tác động tài nguyên.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): giới hạn unacknowledged deliveries và semantics prefetch.

**Kết luận:** Khi triển khai **SPRING_AMQP**, phải quản lý **CPU/bộ nhớ của pod, JVM heap/native memory, số TCP connections, AMQP channels, listener executors và prefetch** như một hệ ngân sách thống nhất. Đặt requests/limits để bảo vệ node, dùng `CachingConnectionFactory` đúng nghĩa cache/cap, sizing concurrency theo DB/API, và tính tổng ở `maxReplicas + maxSurge`. Sau đó chứng minh bằng benchmark và fault tests rằng việc giới hạn tài nguyên **không làm mất dữ liệu, ACK sớm hoặc tạo retry storm**. Mục tiêu không phải mở nhiều thread/channel nhất, mà là giữ throughput, tail latency và độ tin cậy của luồng message trong giới hạn tài nguyên có thể vận hành bền vững.
