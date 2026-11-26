# TaskExecutor, thread pool và giới hạn xử lý đồng thời trong Spring AMQP

Khi một queue RabbitMQ bắt đầu tích lũy hàng nghìn message, phản ứng đầu tiên thường là tăng số consumer. Nhưng đặt `concurrency=20` chưa chắc tạo ra 20 tác vụ nghiệp vụ chạy hiệu quả: listener có thể thiếu thread trong `TaskExecutor`, RabbitMQ Java client có thể thiếu thread dispatch, database connection pool có thể chỉ phục vụ được 8 truy vấn cùng lúc, hoặc mỗi consumer đang giữ quá nhiều message chưa ack vì `prefetch` quá lớn.

Bài học thuộc chương **Listener container** của module **SPRING_AMQP**. Trong hệ thống tích hợp `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding, listener container chịu trách nhiệm nhận message, điều phối xử lý, acknowledgement, retry và recovery. Bài này tập trung vào **`TaskExecutor`, thread pool và giới hạn xử lý đồng thời** để vận hành các luồng bất đồng bộ đáng tin cậy, thay vì chỉ chạy được trong môi trường ít tải.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **consumer**, **channel**, **listener invocation** và **thread**; hiểu chúng liên hệ nhưng không hoàn toàn đồng nhất.
2. Giải thích `TaskExecutor` của `SimpleMessageListenerContainer` (SMLC) khác với executor của **RabbitMQ Java client** trong `DirectMessageListenerContainer` (DMLC).
3. Cấu hình `concurrentConsumers`, `maxConcurrentConsumers`, `consumersPerQueue`, `prefetchCount` và thread pool theo mô hình listener cụ thể.
4. Ước lượng số message đồng thời đang chờ ack, bộ nhớ giữ message và áp lực lên database/API bên dưới.
5. Hiểu vì sao `ThreadPoolTaskExecutor` có `corePoolSize`, `maxPoolSize` và `queueCapacity` phải được thiết kế cùng nhau.
6. Kiểm thử khả năng mở rộng, quan sát queue ready/unacked, consumer count, thread pool, latency và tác động tới retry/DLQ.

## 2. Bức tranh tổng thể: từ message đến business thread

~~~mermaid
flowchart LR
    P["RabbitTemplate<br/>Publisher"] --> EX["Exchange"]
    EX --> Q["Queue"]
    Q --> C["RabbitMQ delivery<br/>consumer/channel"]
    C --> LC["Spring AMQP<br/>listener container"]
    LC --> INV["@RabbitListener<br/>business invocation"]
    INV --> DB["Database / API / Storage"]
    INV -.-> ACK["Ack / nack / reject"]
    ACK -.-> Q
~~~

Những khái niệm thường bị lẫn lộn:

| Đơn vị | Định nghĩa | Tác động đến hiệu năng |
|---|---|---|
| **Connection** | Phiên AMQP/TCP kết nối ứng dụng với broker | Có thể chứa nhiều channel; chia sẻ tài nguyên mạng |
| **Channel** | Phiên logic trong connection | Consumer và delivery tag gắn với channel |
| **Consumer** | Subscription broker dùng để giao message từ queue | Tăng consumer có thể tăng khả năng nhận song song |
| **Listener invocation** | Một lần Spring gọi method `@RabbitListener` | Thường là một xử lý nghiệp vụ trên một thread |
| **TaskExecutor** | Executor mà container sử dụng cho các tác vụ thuộc trách nhiệm của nó | Vai trò khác nhau giữa SMLC và DMLC |
| **Client dispatch executor** | Executor của RabbitMQ Java client | Gọi consumer callback, đặc biệt quan trọng với DMLC |
| **Prefetch** | Số delivery có thể đang chờ xác nhận theo giới hạn QoS phù hợp | Ảnh hưởng số message unacked và phân phối công việc |

**Nhiều consumer không đồng nghĩa nhiều CPU core.** Nếu tất cả consumer đều gọi cùng một database có pool 8 connections, tăng lên 40 listener threads có thể chỉ tăng số thread chờ, timeout và áp lực bộ nhớ.

## 3. Hai loại listener container cần phân biệt

Spring AMQP có hai mô hình listener container thường gặp:

- **SimpleMessageListenerContainer (SMLC):** dùng cấu trúc hàng đợi nội bộ để chuyển delivery từ client callback tới listener invoker. Các invoker chạy trên `TaskExecutor` của container.
- **DirectMessageListenerContainer (DMLC):** gọi listener trực tiếp trên thread dispatch của RabbitMQ Java client. `TaskExecutor` của DMLC chủ yếu phục vụ các tác vụ hỗ trợ như theo dõi/giám sát consumer; muốn đủ năng lực xử lý callback cần quan tâm **executor phía RabbitMQ client**.

| Tiêu chí | SMLC | DMLC |
|---|---|---|
| Thread gọi logic listener | Thread `TaskExecutor` của container | Thread dispatch của RabbitMQ Java client |
| Cách cấu hình consumer chính | `concurrentConsumers`, `maxConcurrentConsumers` | `consumersPerQueue` |
| Co giãn concurrency | Có cơ chế tăng/giảm dựa vào hoạt động khi cấu hình min/max | Chủ yếu chỉnh số consumer per queue; cơ chế khác SMLC |
| Phản ứng với thiếu container `TaskExecutor` | Listener invokers có thể không đủ thread để chạy | Không thể suy tăng pool container sẽ tăng trực tiếp callback throughput |
| Phản ứng với client dispatch executor thiếu thread | Delivery vào container có thể bị chậm | Business handler trực tiếp chịu ảnh hưởng |
| Hợp với bài toán nào? | Phổ biến, dễ hiểu khi điều chỉnh listener worker và concurrency | Muốn đơn giản hóa đường callback, cần quản lý client threads cẩn thận |

Các loại container có các khác biệt khác như cách thay đổi queue trong runtime, hành vi consumer recovery và một số thuộc tính hỗ trợ. Bài này chỉ đi sâu vào **executor/concurrency**; khi chuyển loại container, phải kiểm tra tài liệu đúng phiên bản và tất cả thuộc tính listener liên quan.

## 4. SMLC: TaskExecutor thực sự chạy listener

Với SMLC, callback của RabbitMQ Java client chuyển delivery qua một hàng đợi nội bộ. Listener invoker của SMLC chạy trên `TaskExecutor` và lấy delivery để gọi method nghiệp vụ.

~~~mermaid
flowchart LR
    NET["RabbitMQ client<br/>delivery callback"] --> DISPATCH["Client dispatch<br/>executor"]
    DISPATCH --> BUFFER["SMLC internal queue"]
    BUFFER --> WORKERS["SMLC TaskExecutor<br/>listener invokers"]
    WORKERS --> L["@RabbitListener"]
    L --> DOWN["DB / downstream"]
~~~

Nếu `concurrentConsumers = 4`, container cần khả năng chạy **bốn listener invokers**. Khi `maxConcurrentConsumers = 8`, nó có thể mở rộng đến tối đa **tám consumer workers** theo điều kiện hoạt động và các giới hạn khác. Một thread pool cố định chỉ cho chạy hai invokers không đủ để thực thi kỳ vọng bốn hoặc tám consumer.

### 4.1. Ý nghĩa các thuộc tính SMLC

| Thuộc tính | Vai trò | Rủi ro nếu hiểu sai |
|---|---|---|
| `concurrentConsumers` | Số consumer cơ sở của SMLC | Đặt cao hơn năng lực thread pool/downstream |
| `maxConcurrentConsumers` | Giới hạn trên của số consumer khi scaling động | Tưởng container luôn chạy tại mức max |
| `prefetchCount` | Giới hạn delivery chưa ack theo QoS của consumer | Quá cao gây giữ nhiều message unacked |
| `taskExecutor` | Chạy listener invokers | Pool nhỏ làm worker không khởi động/chạy kịp |
| `receiveTimeout` | Tham gia chu kỳ đợi message của container | Không phải timeout của toàn business handler |
| `batchSize` và cài đặt batch liên quan | Ảnh hưởng các chu kỳ nhận/ack/batch tùy container | Không phải số thread xử lý song song |

`maxConcurrentConsumers` **không phải mục tiêu** container phải đạt ngay. SMLC xem xét các khoảng thời gian hoạt động/nhàn rỗi trước khi thêm hoặc bớt consumer; tốc độ scaling còn chịu các trigger và khoảng thời gian tối thiểu giữa các lần tăng/giảm.

Ví dụ, cấu hình min 4/max 8 nhưng workload chỉ thỉnh thoảng có vài message có thể giữ quanh 4 consumer. Nếu cần phản ứng nhanh khi backlog dâng cao, phải đo xem dynamic scaling có kịp với nhịp tải hay không, thay vì chỉ đọc `maxConcurrentConsumers`.

### 4.2. Vì sao container mặc định vẫn chạy được mà chưa cấu hình pool?

Spring AMQP có executor mặc định phù hợp cho các listener trong một số cấu hình. Nhưng mặc định không phải cam kết về **ngân sách thread**, khả năng queueing hay shutdown cho production. Khi số container/replica tăng, việc dùng `ThreadPoolTaskExecutor` được quản lý và đo đạc giúp biết ứng dụng có bao nhiêu thread xử lý thật sự.

Không tự động chuyển mọi listener sang cùng một pool nếu chúng có mức độ ưu tiên khác nhau; tác vụ email blocking lâu có thể làm thiếu thread cho tác vụ thanh toán nếu dùng chung pool.

## 5. DMLC: listener chạy trên thread của RabbitMQ client

Với DMLC, listener được gọi **trực tiếp** trên thread dispatch của RabbitMQ Java client. Vì thế:

~~~mermaid
flowchart LR
    BROKER["RabbitMQ broker"] --> CLIENT["RabbitMQ Java client<br/>dispatch executor"]
    CLIENT --> DMLC["DirectMessageListenerContainer"]
    DMLC --> METHOD["@RabbitListener<br/>chạy trên client thread"]
    SUPPORT["DMLC TaskExecutor"] -.->|"Tác vụ hỗ trợ / monitor"| DMLC
~~~

Nếu bạn chỉnh `taskExecutor` của DMLC từ 4 lên 32 nhưng **client executor** vẫn thiếu năng lực dispatch, listener có thể tiếp tục bị nghẽn. Cần điều chỉnh executor dùng bởi RabbitMQ client/connection factory và phân bổ đủ thread cho **tổng số consumers trên các connection chia sẻ executor đó**.

### 5.1. consumersPerQueue không phải concurrentConsumers

Ví dụ một DMLC đăng ký hai queue:

~~~text
queues = ["orders.created.q", "orders.cancelled.q"]
consumersPerQueue = 3

Số consumer subscriptions dự kiến:
  3 consumer trên orders.created.q
  3 consumer trên orders.cancelled.q
  = 6 consumer cho một container instance
~~~

Trong SMLC, `concurrentConsumers` áp dụng cho số consumer worker của container; một worker có thể subscribe đến các queue được cấu hình. Vì vậy **không lấy công thức của DMLC áp nguyên xi lên SMLC**.

### 5.2. Blocking handler trên client thread

Nếu handler của DMLC gọi API bên ngoài và chờ 10 giây, thread dispatch đang gọi handler bị chiếm trong thời gian đó. Đây không phải lý do để tạo `CompletableFuture.runAsync(...)` bừa bãi rồi trả về ngay: với ack mode AUTO, container có thể xem listener đã xử lý xong trước khi công việc async thực sự hoàn tất.

Muốn xử lý bất đồng bộ, phải dùng khả năng asynchronous listener được framework hỗ trợ với **acknowledgement/error handling tương thích đúng phiên bản**, hoặc thiết kế worker/container có kiểm soát. Không tự động offload công việc rồi giả định độ tin cậy vẫn như listener đồng bộ.

## 6. ThreadPoolTaskExecutor: core, max và queueCapacity tương tác thế nào?

Trong Spring, `ThreadPoolTaskExecutor` là lựa chọn phổ biến để quản lý pool cho SMLC.

Giả sử cấu hình:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(100);
executor.setThreadNamePrefix("amqp-worker-");
~~~

Nhiều developer tưởng cấu hình này cho phép chạy ngay 8 tác vụ khi có 8 listeners. Nhưng cách mở rộng của `ThreadPoolExecutor` phía dưới thường là:

1. Tạo thread đến `corePoolSize = 4` khi tác vụ được submit.
2. Sau khi core threads bận, **đưa tác vụ vào queue** khi queue còn chỗ.
3. Chỉ khi queue không thể nhận thêm, pool mới có thể tăng tới `maxPoolSize = 8`.
4. Khi đã đến giới hạn và queue đầy, task có thể bị từ chối theo rejection policy.

Với `queueCapacity = 100`, một listener invoker mới có thể bị **xếp hàng** thay vì có thêm thread để chạy, khiến dynamic consumers không thật sự hoạt động như kỳ vọng. Vì vậy cần thiết kế queue capacity theo tính chất **long-running listener invokers**, khác với executor nhận các task ngắn.

| Thiết lập | Ý nghĩa | Gợi ý sử dụng |
|---|---|---|
| `corePoolSize` | Số thread cơ sở | Ít nhất đáp ứng số listener invokers cần chạy thường xuyên |
| `maxPoolSize` | Giới hạn thread tối đa khi pool mở rộng | Cân đối với max consumer và các tác vụ khác cùng pool |
| `queueCapacity = 0` | Dùng handoff trực tiếp, không tích hàng chờ trong executor | Phù hợp khi muốn pool có thể tăng đến max để chạy invokers |
| `queueCapacity > 0` | Xếp task đang chờ trước khi tăng vượt core | Hợp task ngắn; phải cân nhắc với listener invokers sống lâu |
| `threadNamePrefix` | Đặt tên thread | Hữu ích để quan sát thread dump và logs |
| Rejection policy | Khi không còn thread/queue capacity | Đừng bỏ qua lỗi khởi tạo/restart consumer do bị reject |

`queueCapacity=0` không có nghĩa unlimited concurrency: khi pool đạt `maxPoolSize`, task mới vẫn có thể bị từ chối. Đừng biến một lỗi thiếu thread thành lỗi âm thầm bằng cách đặt queue không giới hạn.

**Nhớ:** nếu tất cả SMLC listener invokers giữ thread trong suốt vòng đời consumer, một pool chia sẻ phải có đủ thread cho **tổng nhu cầu invoker của các container cùng dùng nó**, không chỉ riêng một listener.

## 7. Ví dụ Spring Boot: TaskExecutor riêng cho SMLC

Giả sử ứng dụng Spring Boot sử dụng `spring-boot-starter-amqp`. Ta tạo một listener factory riêng cho xử lý đơn hàng, giữ các cấu hình Boot có thể áp dụng thông qua configurer rồi ghi đè những phần cần thiết. Ví dụ sau minh họa cách triển khai với các phiên bản Spring Boot 3.x có API này; cần đối chiếu import và setter với phiên bản dự án.

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class OrderWorkerConfiguration {

    @Bean
    ThreadPoolTaskExecutor orderListenerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("orders-listener-");
        // Spring tự khởi tạo/hủy bean; không cần gọi initialize() lần hai.
        return executor;
    }

    @Bean
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory,
            @Qualifier("orderListenerExecutor")
            ThreadPoolTaskExecutor executor) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        configurer.configure(factory, connectionFactory);
        factory.setTaskExecutor(executor);
        factory.setConcurrentConsumers(4);
        factory.setMaxConcurrentConsumers(8);
        factory.setPrefetchCount(20);
        return factory;
    }
}
~~~

Tạo listener:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedWorker {

    @RabbitListener(
        id = "orders-created-worker",
        queues = "orders.created.q",
        containerFactory = "ordersListenerFactory")
    public void consume(String body) {
        // Ví dụ xử lý đồng bộ: thread này được giữ đến khi method trả về.
        // Xác minh idempotency, timeout DB/API và exception handling.
        System.out.printf("thread=%s, payload=%s%n",
                Thread.currentThread().getName(), body);
    }
}
~~~

Các giới hạn của ví dụ:

- Queue `orders.created.q` và binding phải tồn tại; code listener **không tự khai báo** chúng khi dùng `queues` đơn thuần.
- `String` được chọn để tập trung vào concurrency. Nếu message là DTO JSON, phải cấu hình `MessageConverter` đồng bộ với producer.
- `SimpleRabbitListenerContainerFactoryConfigurer` giúp giữ các cấu hình Boot hỗ trợ, nhưng các setter gọi **sau** `configure` sẽ ghi đè những giá trị tương ứng. Kiểm tra retry, converter, observation, ack mode và transaction của ứng dụng.
- `core=4`, `max=8`, `queueCapacity=0` được chọn tương ứng với min/max consumer trong ví dụ; **không phải con số tối ưu cho mọi ứng dụng**.
- Log body chỉ dùng để minh họa; trong thực tế tránh ghi payload nhạy cảm vào log.

### Khi muốn cấu hình bằng application.yml

Nếu dùng listener factory mặc định của Spring Boot thay vì tạo riêng:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: simple
      simple:
        concurrency: 4
        max-concurrency: 8
        prefetch: 20
~~~

Những property trên cấu hình listener **mặc định** do Boot tạo trong các phiên bản hỗ trợ. Chúng không tự gắn một `ThreadPoolTaskExecutor` riêng vào factory tùy chỉnh bạn tạo. Đồng thời, nếu trong code bạn ghi đè concurrency, cấu hình code đó có thể thắng property của Boot.

Nên chọn **một nguồn cấu hình rõ ràng** cho từng listener: Boot defaults, factory được đặt tên, hay override tại annotation. Tránh tăng thông số ở YAML nhưng thực tế ứng dụng đang dùng một custom factory khác.

## 8. Ví dụ DMLC và cách cấp client executor

Với DMLC, bạn có thể tạo một listener factory riêng:

~~~java
import org.springframework.amqp.rabbit.config.DirectRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.DirectRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AuditListenerConfiguration {

    @Bean
    DirectRabbitListenerContainerFactory auditDirectFactory(
            DirectRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        DirectRabbitListenerContainerFactory factory =
                new DirectRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);
        factory.setConsumersPerQueue(2);
        factory.setPrefetchCount(10);
        return factory;
    }
}
~~~

Listener:

~~~java
@RabbitListener(
    id = "audit-direct-worker",
    queues = "orders.audit.q",
    containerFactory = "auditDirectFactory")
public void audit(String payload) {
    // DMLC gọi listener trên RabbitMQ client dispatch thread.
}
~~~

Nếu nhiều DMLC cùng dùng một `CachingConnectionFactory`, hãy tính tổng consumer và kiểm tra **RabbitMQ Java client executor** của connection factory, thay vì chỉ tăng `TaskExecutor` của từng DMLC.

Về mặt API, Spring AMQP cho phép cấu hình executor dùng cho client trên connection factory (ví dụ `CachingConnectionFactory.setExecutor(...)` tùy phiên bản). Nếu tự tạo `CachingConnectionFactory`, cần giữ đủ cấu hình host, TLS, virtual host, credentials, publisher confirms/returns, lifecycle và recovery mà Spring Boot vốn có thể auto-configure. Không thay hẳn connection factory production chỉ để chỉnh executor khi chưa đánh giá các phần đó.

Một cấu hình Boot mặc định cho DMLC có thể có:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: direct
      direct:
        consumers-per-queue: 2
        prefetch: 10
~~~

Tên properties có thể thay đổi qua các nhánh Spring Boot; hãy kiểm tra bảng application properties của đúng version. Không cấu hình cả `simple` và `direct` rồi giả định cả hai cùng áp dụng lên mọi listener.

## 9. @RabbitListener(concurrency): override tại endpoint

Ngoài factory, một số phiên bản Spring AMQP cho phép cấu hình `concurrency` trực tiếp ở annotation:

~~~java
@RabbitListener(
    queues = "orders.created.q",
    containerFactory = "ordersListenerFactory",
    concurrency = "4-8")
public void process(String body) {
    // ...
}
~~~

Với SMLC, chuỗi `"4-8"` biểu thị khoảng min–max consumer theo cú pháp container. Với DMLC, giá trị phù hợp thường là một số nguyên chỉ **consumers per queue**; không dùng cú pháp khoảng SMLC một cách máy móc.

**Chú ý:** Annotation có thể override concurrency của container factory; khi cố kiểm tra thay đổi cấu hình YAML, hãy xem annotation có đang cố định giá trị khác hay không. Đồng thời không tự suy rằng `concurrency="8"` có nghĩa luôn đúng tám handler đang **bận xử lý**, vì consumer có thể đang idle.

## 10. Giới hạn xử lý đồng thời: tính cả prefetch

Số worker quyết định mức độ **đang xử lý**, còn `prefetch` cho phép broker giao message trước khi chúng được ack. Ví dụ một listener có:

~~~text
Replicas: 3
Consumers mỗi replica: 4
Prefetch mỗi consumer: 20

Số consumer dự kiến: 3 x 4 = 12
Số delivery có thể đang unacked:
       3 x 4 x 20 = 240
~~~

Con số **240** là một mức ước lượng có điều kiện cho tổng delivery chưa ack, không có nghĩa 240 method nghiệp vụ đang chạy song song. Với listener đồng bộ xử lý từng message, số business invocations đồng thời gần với **12 consumer** hơn, nếu mỗi consumer có thread/callback capacity và không bị downstream hạn chế.

~~~mermaid
flowchart TD
    Q["Queue backlog"] --> A["Replica A<br/>4 consumers × prefetch 20"]
    Q --> B["Replica B<br/>4 consumers × prefetch 20"]
    Q --> C["Replica C<br/>4 consumers × prefetch 20"]
    A --> UA["Tới ~80 unacked"]
    B --> UB["Tới ~80 unacked"]
    C --> UC["Tới ~80 unacked"]
    UA --> DB["DB pool / downstream"]
    UB --> DB
    UC --> DB
~~~

Những con số này thay đổi theo queue type, QoS semantics, manual/auto ack, batch, số queue trên một container, việc consumer restart và giới hạn broker. Khi dùng `AcknowledgeMode.NONE` (broker auto-ack) thì metric unacked không diễn giải như trường hợp manual/auto ack có xác nhận.

### 10.1. Vì sao prefetch quá cao gây mất cân bằng?

Nếu consumer A nhận trước một lượng lớn delivery chưa ack, consumer B mới khởi động có thể thấy ít message sẵn sàng để xử lý, dù B nhàn rỗi. Với message tốn nhiều thời gian xử lý, `prefetch` nhỏ hơn có thể cải thiện fairness và giảm memory/locked work. Prefetch lớn đôi khi giúp throughput tốt hơn cho message rất ngắn vì giảm round trip, nhưng phải thử với workload thực tế.

Không có một giá trị prefetch tối ưu cho mọi ứng dụng. Hãy bắt đầu với mức dễ quan sát (ví dụ 10–20 cho tác vụ xử lý tương đối lâu), đo throughput, latency, ready/unacked và memory, rồi điều chỉnh.

### 10.2. Công thức ngân sách tài nguyên

Với listener xử lý đồng bộ một message mỗi consumer, có thể ước lượng:

~~~text
Max business concurrency cần dự trù
  ≈ số replica x số consumer tối đa / replica

Potential unacked delivery budget
  ≈ tổng consumer x prefetch / consumer

Tổng mức tải hữu hiệu
  <= mức nhỏ nhất giữa consumer execution capacity,
     DB pool/downstream concurrency,
     CPU/memory và broker/network capacity.
~~~

Nếu DB connection pool chỉ có 10 kết nối nhưng 24 consumers đều có thể truy vấn DB, hệ thống có thể phải chờ kết nối. Khi đó tăng `maxConcurrentConsumers` làm tăng contention mà không tăng throughput.

**Đừng dùng prefetch để thay concurrency.** Prefetch 100 không làm một listener đồng bộ xử lý 100 message cùng lúc; nó chủ yếu cho phép broker giao trước nhiều message chưa ack.

## 11. Scaling động của SMLC: min, max và độ trễ phản ứng

SMLC không nhất thiết scale ngay khi queue vừa có một burst. Với khoảng min/max, nó dùng các quan sát theo chu kỳ nhận để đánh giá consumer **active** hay **idle**, cùng các khoảng thời gian tối thiểu giữa các lần khởi tạo/dừng consumer.

| Nhóm thuộc tính | Tác dụng | Cảnh báo |
|---|---|---|
| `concurrentConsumers` | Mức cơ sở | Phải có đủ thread |
| `maxConcurrentConsumers` | Mức trần | Không bảo đảm đạt ngay |
| `consecutiveActiveTrigger` | Số chu kỳ hoạt động liên tiếp cần để cân nhắc tăng | Burst ngắn có thể không kích hoạt |
| `startConsumerMinInterval` | Khoảng tối thiểu giữa các lần thêm consumer | Không phù hợp nếu kỳ vọng tăng đột biến tức thời |
| `consecutiveIdleTrigger` | Số chu kỳ idle liên tiếp để cân nhắc giảm | Không giảm ngay khi traffic vừa hết |
| `stopConsumerMinInterval` | Khoảng tối thiểu giữa các lần giảm consumer | Có thể giữ thread trong một thời gian |

Các default và điều kiện scaling chi tiết phụ thuộc phiên bản Spring AMQP. Không điều chỉnh đồng thời mọi trigger chỉ vì thấy backlog tăng. Hãy phân biệt **scale-up chậm** với **business handler xử lý chậm** và **pool không còn thread**.

Với workload tăng giảm mạnh, đặt min gần mức nhu cầu thực tế hoặc chuẩn bị thêm capacity có thể giúp giảm độ trễ cold-start. Tuy nhiên, giữ consumer idle nhiều cũng tốn channel và tài nguyên broker.

## 12. Đừng chuyển tác vụ async tùy tiện khỏi listener thread

Một anti-pattern thường gặp:

~~~java
@RabbitListener(queues = "payments.commands.q")
public void handle(String payload) {
    businessExecutor.execute(() -> chargePayment(payload));
    // Phương thức trả về trước khi chargePayment hoàn tất.
}
~~~

Với `AcknowledgeMode.AUTO`, container thường coi method handler đã thành công khi **phương thức trả về bình thường**, từ đó có thể ack delivery trước khi `chargePayment` thực sự hoàn thành. Nếu task async ném exception sau đó, RabbitMQ không tự biết và không tự redeliver message này.

Điều đúng hơn tùy bài toán:

1. Giữ nghiệp vụ đồng bộ trong listener và điều chỉnh consumer concurrency, executor, timeout phù hợp.
2. Nếu cần async listener, dùng cơ chế return type/ack handling được Spring AMQP **hỗ trợ ở đúng version**, kiểm tra exception propagation và manual acknowledgement.
3. Nếu giao một task dài sang hệ thống worker khác, hãy làm rõ **điểm chuyển giao bền vững**; tránh ack message trước khi task thật sự được lưu và có cơ chế phục hồi.

Không nên trộn một thread pool nền của ứng dụng vào listener rồi coi việc tăng pool đã tăng số consumer RabbitMQ. Hai lớp giới hạn xử lý khác nhau và phải có hợp đồng acknowledgement riêng.

## 13. Ack, retry, DLQ và tác động tới concurrency

Tăng concurrency không sửa lỗi xử lý dữ liệu; nó có thể làm lỗi diễn ra nhanh hơn nếu retry/requeue không được giới hạn.

~~~mermaid
flowchart TD
    Q["Queue"] --> C["Listener consumer"]
    C --> H["@RabbitListener xử lý"]
    H -->|"Success"| A["Ack delivery"]
    H -->|"Transient error"| RET["Retry/backoff theo chính sách"]
    H -->|"Permanent error"| DL["Reject / dead-letter khi cấu hình phù hợp"]
    RET -->|"Hết giới hạn"| DL
    RET -->|"Retry"| H
~~~

| Cơ chế | Ảnh hưởng tới giới hạn đồng thời |
|---|---|
| `AcknowledgeMode.AUTO` | Container ack sau khi handler hoàn tất; lỗi đi qua error handler |
| `AcknowledgeMode.MANUAL` | Nếu không ack/nack, message giữ trạng thái unacked và tiêu tốn prefetch credit |
| Retry ngay trong listener thread | Giữ worker bận, giảm capacity xử lý message mới |
| Retry bằng queue/DLX có delay | Giải phóng worker ban đầu nhưng tạo vòng đời message bổ sung |
| `defaultRequeueRejected=true` không có giới hạn | Có thể tạo poison-message loop và tiêu tốn CPU/consumer |
| Idempotency | Giảm hậu quả khi disconnect/retry gây delivery trùng |

Ví dụ một message lỗi cố định và bị requeue liên tục: nếu tăng concurrency lên 20, nhiều consumer có thể đồng thời tranh xử lý message lỗi/những message khác, tạo log storm và áp lực DB. Cần **phân loại lỗi**, giới hạn retry và có DLQ/quarantine rõ ràng trước khi mở rộng consumer.

**Không nhầm publisher confirm với consumer ack:** publisher confirm báo broker xử lý publish; consumer ack báo trạng thái delivery tới listener. Đặt thread pool lớn không tự bảo đảm cả hai loại xác nhận.

## 14. Theo dõi metrics để tìm đúng giới hạn

Một dashboard hữu ích nên ghép nhiều tín hiệu:

| Metric/quan sát | Diễn giải | Hướng điều tra |
|---|---|---|
| `messages_ready` | Message chưa được giao, đang chờ trên queue | Producer > consumer hoặc consumer không đủ năng lực |
| `messages_unacknowledged` | Message đã giao nhưng chưa ack | Handler chậm, prefetch cao, manual ack thiếu, network |
| Consumer count | Số consumer subscriptions broker thấy | Có đủ consumers theo cấu hình không? |
| Active thread count | Thread đang chạy trong executor | Có chạm core/max hoặc không mở rộng như kỳ vọng? |
| Executor queue depth | Task đang chờ được pool chạy | Pool `queueCapacity` có đang che giấu thiếu worker? |
| Rejected tasks | Task không nhận được vì executor đầy | Nguy cơ consumer không khởi động hoặc task bị từ chối |
| Handler latency p50/p95/p99 | Thời gian xử lý một message | Downstream bottleneck và tail latency |
| Broker connection/channel count | Tài nguyên mạng/AMQP | Channel cache, checkout limit, nhiều replicas |
| Consumer error/retry/DLQ rate | Độ tin cậy xử lý | Poison messages và chính sách retry |
| CPU, memory, DB pool utilization | Khả năng thực tế của hệ thống | Đừng tăng consumer vượt năng lực downstream |

Ví dụ phân tích nhanh:

- **Ready tăng, unacked thấp, active thread thấp:** có thể ít consumer, route/consumer registration lỗi hoặc throughput thấp do cấu hình.
- **Ready tăng, unacked gần `consumer × prefetch`, thread busy:** business processing hoặc downstream có thể đang nghẽn.
- **Consumer count thấp hơn kỳ vọng, executor bị reject:** điều tra TaskExecutor và lifecycle khởi tạo consumer.
- **Threads rất nhiều nhưng throughput không tăng:** đo DB pool, CPU, I/O waits, lock contention trước khi tăng thêm.

Không dùng chỉ một metric để kết luận. Chẳng hạn queue rỗng không chứng minh listener khỏe nếu message đã được prefetch và đang chờ xử lý ở trạng thái unacked.

### 14.1. Đặt tên thread có mục đích

~~~text
orders-listener-1
orders-listener-2
orders-listener-3
rabbit-client-1
rabbit-client-2
~~~

Tên thread giúp xác định thread dump thuộc SMLC invoker hay RabbitMQ Java client callback. Nếu nhiều factory cùng dùng chung prefix, cần thêm tên nghiệp vụ/role. Không đưa password hoặc dữ liệu cá nhân vào thread name.

### 14.2. Theo dõi container thực tế

Spring AMQP cung cấp `RabbitListenerEndpointRegistry` để quản lý listener containers do annotation đăng ký. Tìm container bằng `id` của `@RabbitListener` rồi kiểm tra trạng thái và các API mà loại container hỗ trợ. Ví dụ:

~~~java
import org.springframework.amqp.rabbit.config.RabbitListenerEndpointRegistry;
import org.springframework.amqp.rabbit.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class ListenerInspector {
    private final RabbitListenerEndpointRegistry registry;

    public ListenerInspector(RabbitListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);
        return container != null && container.isRunning();
    }
}
~~~

`isRunning()` chỉ cho biết container đang trong trạng thái hoạt động, **không chứng minh** các message đều xử lý thành công. Cần thêm consumer count của broker, errors, latency và kết quả nghiệp vụ. Không tự động dừng hoặc thay đổi container trên production chỉ để kiểm tra thống kê.

## 15. Bài thực hành: đo concurrency theo từng tầng

### 15.1. Chuẩn bị topology test

Tạo queue test riêng `jobs.work.q` và binding từ direct exchange `jobs.work.x` với key `job.created`. Đảm bảo không có consumer khác tranh nhận message trong phép thử.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JobsTopology {
    @Bean
    DirectExchange jobsExchange() {
        return new DirectExchange("jobs.work.x", true, false);
    }

    @Bean
    Queue jobsQueue() {
        return QueueBuilder.durable("jobs.work.q").build();
    }

    @Bean
    Binding jobsBinding(Queue jobsQueue, DirectExchange jobsExchange) {
        return BindingBuilder.bind(jobsQueue)
                .to(jobsExchange)
                .with("job.created");
    }
}
~~~

### 15.2. Producer gửi burst có ID riêng

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public void publishJobs(RabbitTemplate rabbitTemplate) {
    for (int i = 1; i <= 200; i++) {
        rabbitTemplate.convertAndSend(
                "jobs.work.x", "job.created", "job-" + i);
    }
}
~~~

Ví dụ này mô phỏng burst; `convertAndSend` không tự chứng minh broker đã xác nhận từng publish. Nếu cần kết quả chính xác hãy bật publisher confirms/returns và kiểm tra route. Với test, nên ghi kết quả publish để tránh nhầm message không được route với concurrency thấp.

### 15.3. Listener ghi lại mức song song thực tế

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class JobsWorker {
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger maxSeen = new AtomicInteger();

    @RabbitListener(
        id = "jobs-worker",
        queues = "jobs.work.q",
        containerFactory = "ordersListenerFactory")
    public void onJob(String body) throws InterruptedException {
        int running = active.incrementAndGet();
        maxSeen.accumulateAndGet(running, Math::max);
        try {
            // Chỉ giả lập I/O chậm trong môi trường test.
            Thread.sleep(200);
            System.out.printf(
                    "%s handled %s, active=%d, maxSeen=%d%n",
                    Thread.currentThread().getName(),
                    body, running, maxSeen.get());
        } finally {
            active.decrementAndGet();
        }
    }
}
~~~

Trong ví dụ, factory `ordersListenerFactory` của mục 7 đang dùng để minh họa cơ chế SMLC. Ứng dụng thực tế có thể tạo `jobsListenerFactory` riêng để tránh dùng chung cấu hình nghiệp vụ khác.

`Thread.sleep(200)` chỉ để nhìn thấy concurrency trong lab, **không dùng làm kỹ thuật xử lý tải**. Nếu job thực sự mất 200 ms và được phép chạy song song, số consumer cao hơn có thể tăng throughput cho đến khi gặp giới hạn thread/DB/network. MaxSeen đo **số handler đồng thời của một instance JVM**; nếu có 3 replicas, số toàn hệ thống cần quan sát tổng hợp.

### 15.4. Các lượt thử

| Lượt | Container | Executor | Prefetch | Điều cần đo |
|---|---|---|---|---|
| A | SMLC min=max=1 | Pool đủ 1 | 1 | Baseline throughput và latency |
| B | SMLC min=max=4 | Pool đủ 4 | 10 | `maxSeen` tăng tới gần 4 khi có backlog |
| C | SMLC min=4/max=8 | Pool core 4/max 8, queue capacity 0 | 20 | Scaling động có lên 8 hay không |
| D | SMLC max=8 | Pool core 2/max 2 | 20 | Thiếu thread so với consumer kỳ vọng |
| E | DMLC consumersPerQueue=2 | Client executor đủ năng lực | 10 | Thread name của callback và throughput |
| F | DMLC consumersPerQueue=4 | Chỉ tăng container TaskExecutor | 10 | Xem client executor còn là giới hạn không |

Không chạy tất cả lượt thử đồng thời trên cùng queue, vì consumer đang hoạt động sẽ làm phép đo nhiễu. Trước mỗi lượt, reset queue test hoặc dùng event IDs riêng và so sánh số đã publish, đã xử lý, lỗi, unacked. Nếu test dùng `AcknowledgeMode.AUTO`, method ném lỗi sẽ đi qua container error handler; cần cấu hình rõ retry/DLQ để tránh lặp vô hạn.

## 16. Các lỗi phổ biến và cách sửa

| Dấu hiệu | Nguyên nhân đáng kiểm tra | Cách xử lý |
|---|---|---|
| SMLC có min 8 nhưng chỉ thấy vài listener threads chạy | Executor core/max/queue capacity không phù hợp | Xem thread pool thực, nhiệm vụ bị queue/reject |
| Tăng `maxConcurrentConsumers` mà throughput không tăng | Scale chưa kích hoạt hoặc downstream đã bão hòa | Đọc active/idle triggers, DB pool và latency |
| DMLC xử lý chậm dù tăng container TaskExecutor | Business callback chạy trên client thread | Kiểm tra RabbitMQ client executor và blocking logic |
| Queue ready tăng, unacked cao | Prefetch lớn, handler chậm, thiếu ack | Đo handler latency, QoS và ack policy |
| Có nhiều consumer nhưng chỉ một DB connection rảnh | Thread bị block/lock hoặc pool downstream quá nhỏ | Xem thread dump, DB pool metrics và transactions |
| `@RabbitListener(concurrency)` không theo YAML | Annotation/custom factory override Boot defaults | Xác định factory thực và thứ tự cấu hình |
| Channel checkout timeout khi tăng concurrency | Giới hạn channel cache với checkout timeout dương | Tính tổng channel cần dùng, chỉnh pool/connection hợp lý |
| Message xử lý trùng sau reconnect | Delivery chưa ack được redeliver | Dùng event ID và consumer idempotent |
| Async task lỗi nhưng message đã ack | Listener trả về trước khi task nền hoàn tất | Dùng async listener/ack strategy chính thức hoặc xử lý đồng bộ |
| Retry không giới hạn khiến CPU tăng | Poison-message loop/requeue liên tục | Thiết lập retry giới hạn, dead-letter/quarantine |

### Không nhầm timeout của executor với timeout kết nối

`AmqpTimeoutException` khi lấy channel có thể là do **channel checkout**, còn `TaskRejectedException` của executor có thể do **pool hết thread và queue đã đầy**. `connection-timeout` liên quan thiết lập socket đến RabbitMQ; `receive-timeout` của listener container lại liên quan chu kỳ chờ delivery. Đọc stack trace để biết điểm chờ bị lỗi, không tăng mọi timeout cùng lúc.

## 17. Bài tập có lời giải gợi ý

### Bài 1 — Pool không mở rộng

Một SMLC có min 4/max 8 nhưng `ThreadPoolTaskExecutor` core 4/max 8/queueCapacity 100. Vì sao có thể chỉ thấy 4 threads, dù muốn tăng consumer?

**Gợi ý:** executor có thể queue tác vụ invoker khi core đang bận trước khi tạo thêm threads. Với invoker lâu dài, xem xét `queueCapacity=0` và đảm bảo pool đủ cho max consumers, đồng thời đo xem cơ chế dynamic scaling đã quyết định tăng chưa.

### Bài 2 — Prefetch có tạo concurrency không?

Một listener đồng bộ có 2 consumers, prefetch 100. Có chắc 200 method `@RabbitListener` đang chạy song song?

**Đáp án:** không. Số handler đồng thời thường gần số consumer đang thực thi (khoảng 2), còn prefetch có thể cho phép nhiều delivery được giữ ở trạng thái unacked.

### Bài 3 — SMLC và DMLC dùng executor khác nhau

Tại sao tăng pool của SMLC có thể giúp listener invokers chạy, còn tăng `TaskExecutor` của DMLC không chắc tăng handler concurrency?

**Gợi ý:** SMLC gọi listener từ task executor của container, DMLC gọi trực tiếp từ RabbitMQ client dispatch thread. Cần kiểm tra đúng executor theo kiến trúc.

### Bài 4 — Consumers per queue

DMLC đăng ký 3 queues với `consumersPerQueue=2`. Dự kiến có bao nhiêu consumer subscriptions trong một instance?

**Đáp án:** khoảng 6 subscriptions nếu cả 3 queue hoạt động/đăng ký thành công. Không dùng công thức này để suy SMLC `concurrentConsumers=2` sẽ có đúng 6 invoker threads.

### Bài 5 — Giới hạn database

Có 4 replicas, mỗi replica có 8 consumer, DB pool toàn hệ thống thực tế chỉ phục vụ 12 truy vấn đồng thời. Nên tăng consumer lên 64 mỗi replica không?

**Gợi ý:** không chỉ tăng consumer; trước hết đo DB wait, throughput, latency và khả năng query. Cần ngân sách concurrency/backpressure tương thích downstream, không để threads chờ tràn lan.

### Bài 6 — Async ack quá sớm

Listener nhận payment command rồi submit công việc vào `ExecutorService` và trả về. Với `AcknowledgeMode.AUTO`, điều gì có thể sai?

**Đáp án:** container có thể ack khi listener trả về, trước khi payment task thực sự hoàn thành. Nếu task lỗi, broker không tự retry delivery đã ack. Phải quản lý completion/ack tương thích hoặc xử lý đồng bộ.

### Bài 7 — Scaling chậm

SMLC đặt min 2/max 10, queue có burst 100 message, nhưng consumer count chỉ ở 2 và burst kết thúc rất nhanh. Điều này có phải bug không?

**Gợi ý:** không nhất thiết. Cơ chế co giãn của SMLC xem xét active/idle cycles và khoảng thời gian tối thiểu. Burst ngắn có thể kết thúc trước khi đủ điều kiện tăng; đo thời gian xử lý và điều chỉnh baseline phù hợp.

### Bài 8 — Unacked và retry

Một DMLC có 5 consumers, prefetch 50, broker thấy khoảng 250 unacked nhưng throughput thấp. Hãy nêu ít nhất bốn giả thuyết.

**Gợi ý:** business handler blocking, client executor thiếu threads, DB pool bão hòa, manual ack không được gọi, retry lâu chiếm callback, network/broker flow control. Prefetch lớn không bảo đảm nhiều handler chạy.

## 18. Checklist trước khi vận hành production

- [ ] Xác nhận listener dùng `SimpleMessageListenerContainer` hay `DirectMessageListenerContainer`, cùng Spring Boot/Spring AMQP version.
- [ ] Xác định đúng **executor chạy business handler**; không nhầm SMLC TaskExecutor với RabbitMQ client dispatch executor của DMLC.
- [ ] Với SMLC, cấp đủ thread cho min/max consumer và **tổng nhu cầu của các container dùng chung pool**.
- [ ] Hiểu `corePoolSize`, `maxPoolSize`, `queueCapacity` và cơ chế rejection; không để invoker lâu dài chỉ xếp hàng mà không chạy.
- [ ] Với DMLC, tính consumer subscriptions theo số queue × consumersPerQueue và kiểm tra năng lực RabbitMQ client executor.
- [ ] Tính tổng concurrency ở **tất cả replicas**; không chỉ xem cấu hình mỗi JVM.
- [ ] Đặt `prefetch` theo thời gian xử lý, memory và fairness; dự trù số delivery unacked.
- [ ] Cân đối với DB connection pool, HTTP client pool, CPU, memory và giới hạn broker.
- [ ] Phân biệt Boot application properties, factory customizations và `@RabbitListener(concurrency)` overrides.
- [ ] Có cơ chế xử lý lỗi/retry/DLX và idempotency, không tăng consumer để che poison-message loop.
- [ ] Không offload business work rồi ack quá sớm; dùng async listener semantics có kiểm chứng nếu cần.
- [ ] Giám sát queue ready/unacked, consumer count, active threads, executor queue/rejection, p95 latency, lỗi và DLQ.
- [ ] Test burst traffic, steady load, slow DB, pool exhaustion, broker restart, reconnect, rolling deployment và graceful shutdown.
- [ ] Ghi nhận số liệu trước/sau mỗi thay đổi; không chỉnh đồng thời mọi concurrency/prefetch/timeout mà không đo hiệu quả.

## 19. Tài liệu tham khảo

Ưu tiên tài liệu theo **phiên bản Spring AMQP và Spring Boot đang chạy**:

- [Spring AMQP Reference — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): `concurrentConsumers`, `maxConcurrentConsumers`, `consumersPerQueue` và dynamic scaling.
- [Spring AMQP Reference — Threading and Asynchronous Consumers](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/threading.html): khác biệt threading giữa SMLC và DMLC.
- [Spring AMQP Reference — Listener Container Attributes](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): `prefetchCount`, ack, task executor và cài đặt container.
- [Spring AMQP Reference — Connections and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): connection, channel cache, client executor.
- [Spring Boot Reference — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): auto-configuration, listener container factories và properties.
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): thread pool, core/max/queue capacity và lifecycle.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): QoS/prefetch semantics.
- [RabbitMQ — Consumers](https://www.rabbitmq.com/docs/consumers): consumer subscriptions, delivery, acknowledgements và giới hạn vận hành.

**Ghi nhớ:** `TaskExecutor` không phải một nút “tăng tốc” chung cho mọi listener container. **SMLC** thực thi handler trên executor của container, còn **DMLC** gọi handler trên RabbitMQ client thread. Cần phối hợp **consumer concurrency, kích thước pool, queueCapacity, prefetch và năng lực downstream**, rồi đo từ queue tới business outcome. Có như vậy việc tăng song song mới giúp Spring AMQP xử lý message nhanh hơn mà không làm mất kiểm soát acknowledgement, retry và tài nguyên hệ thống.
