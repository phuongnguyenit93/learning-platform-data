# Giới hạn hàng đợi nội bộ, bộ nhớ và số tác vụ đang xử lý

## Mục tiêu

Một ứng dụng Spring Cloud Stream có thể nhận message nhanh hơn tốc độ xử lý nghiệp vụ. Nếu ứng dụng giữ quá nhiều message trong bộ nhớ, mở quá nhiều consumer hoặc đưa công việc vào một hàng đợi không giới hạn, heap sẽ tăng dần, garbage collection kéo dài và cuối cùng process có thể bị OutOfMemoryError. Khi đó broker vẫn còn backlog, nhưng chính consumer đã mất khả năng xử lý ổn định.

Để kiểm soát tải, cần giới hạn ba thứ riêng biệt:

- **Hàng đợi:** số message đang chờ trong broker, client prefetch hoặc hàng đợi nội bộ của ứng dụng.
- **Bộ nhớ:** lượng heap/direct memory mà payload, object đã deserialize, batch, buffer và task đang giữ.
- **Tác vụ đang xử lý (in-flight):** số handler, thread hoặc asynchronous task đang thực thi nhưng chưa hoàn tất/acknowledge.

Spring Cloud Stream cung cấp concurrency chung cho input binding; mỗi binder còn có cấu hình riêng như Kafka poll/fetch, RabbitMQ prefetch và Pulsar receiver queue. Không có một thuộc tính hàng đợi nội bộ duy nhất áp dụng giống nhau cho mọi binder. Cần hiểu đúng từng tầng rồi đặt giới hạn tại nơi dữ liệu thực sự được buffer.

Sau bài học, bạn có thể:

- Phân biệt broker backlog, client prefetch, application queue và in-flight work.
- Ước lượng bộ nhớ do message và task đang giữ.
- Chọn concurrency theo partition, subscription và năng lực dependency.
- Giới hạn hàng đợi của executor và áp dụng backpressure.
- Cấu hình Kafka max.poll.records, fetch limits và poll interval.
- Cấu hình RabbitMQ concurrency, maxConcurrency, prefetch và queue length.
- Cấu hình Pulsar receiverQueueSize và giới hạn receiver queue qua partition.
- Hiểu producer buffer và tác động khi broker chậm.
- Tránh xác nhận message trước khi asynchronous work hoàn tất.
- Đo throughput, latency, backlog, heap và số tác vụ đang chạy.
- Kiểm thử tải bình thường, burst, dependency chậm và tình huống quá tải.

## 1. Phân biệt bốn nơi message có thể được giữ

Một message không nhất thiết nằm trong đúng một hàng đợi. Trên đường đi từ broker đến handler và sang output, nó có thể tồn tại ở nhiều tầng:

1. **Broker backlog:** message đã được broker lưu nhưng chưa được consumer xử lý/ack. Ví dụ Kafka topic lag, RabbitMQ ready messages hoặc Pulsar subscription backlog.
2. **Client-side prefetch/fetch buffer:** message broker đã gửi về client nhưng ứng dụng chưa xử lý xong. Ví dụ RabbitMQ unacknowledged deliveries, Kafka fetch cache hoặc Pulsar receiver queue.
3. **Application queue:** message/task đã được đưa vào hàng đợi trong JVM, ví dụ ThreadPoolTaskExecutor, Reactor buffer hoặc một queue tự xây dựng.
4. **In-flight processing:** handler hoặc worker đã bắt đầu xử lý message và đang giữ payload, object, transaction, connection hoặc kết quả trung gian.

Có thể hình dung:

~~~mermaid
flowchart LR
    A[(Broker backlog)] --> B[Client prefetch / fetch]
    B --> C[Application queue]
    C --> D[In-flight workers]
    D --> E[ACK / offset commit]
    D --> F[Output producer buffer]
    F --> G[(Destination topic / queue)]
~~~

Broker backlog thường nằm trên storage của broker, không trực tiếp chiếm heap của JVM consumer. Ngược lại, prefetch, batch, queue nội bộ và object đang xử lý có thể chiếm heap hoặc direct memory của ứng dụng.

Một ứng dụng có thể có backlog broker rất lớn nhưng heap ổn định nếu consumer fetch có giới hạn. Điều đó thường tốt hơn việc kéo toàn bộ backlog về JVM rồi giữ trong một queue không giới hạn.

### Bảng phân biệt

| Tầng | Ví dụ | Nằm ở đâu | Giới hạn thường dùng |
|---|---|---|---|
| Broker backlog | Kafka lag, Rabbit ready, Pulsar backlog | Broker storage | Retention, queue max length/bytes, quota |
| Client prefetch | Rabbit prefetch, Pulsar receiver queue | Client memory và broker unacked state | Prefetch count, receiverQueueSize |
| Client fetch cache | Kafka fetch buffers | Kafka client memory | fetch.max.bytes, max.partition.fetch.bytes, max.poll.records |
| Application queue | Executor queue, Reactor buffer | JVM heap | queueCapacity, limitRate, bounded buffer |
| In-flight task | Handler/thread đang xử lý | JVM heap, stack, dependency resource | concurrency, semaphore, worker count |
| Producer buffer | Kafka producer buffer, Pulsar pending sends | JVM/direct memory | buffer.memory, max pending messages, block/timeout |

Không dùng một con số để mô tả tất cả các tầng. Ví dụ RabbitMQ prefetch 20 không có nghĩa ứng dụng chỉ giữ tối đa 20 message nếu code còn copy message vào executor queue.

## 2. Vì sao cần giới hạn hàng đợi?

Giả sử producer gửi 1.000 message/giây nhưng consumer chỉ xử lý được 600 message/giây. Phần chênh lệch 400 message/giây sẽ tích lũy thành backlog. Nếu broker giữ backlog, hệ thống có thể tiếp tục hoạt động và consumer có thể catch up khi tải giảm. Nếu ứng dụng kéo backlog về một queue heap không giới hạn, heap sẽ tăng theo thời gian.

Các triệu chứng thường gặp:

- Heap usage tăng liên tục dù CPU chưa đạt 100%.
- Full GC hoặc old-generation GC xuất hiện thường xuyên.
- Message latency tăng vì phải chờ lâu trong queue.
- Thread pool có nhiều task chờ nhưng ít task hoàn tất.
- Database connection pool hoặc HTTP connection pool bị cạn.
- Consumer bị rebalance, timeout hoặc redelivery vì xử lý batch quá lâu.
- Pod bị OOMKilled và khởi động lại liên tục.
- Retry làm tăng thêm tải đúng lúc dependency đang quá tải.

Giới hạn queue tạo một điểm dừng rõ ràng. Khi queue đầy, hệ thống có thể giảm tốc độ nhận, để broker giữ backlog, từ chối submit task hoặc trả lỗi có kiểm soát. Đó là backpressure.

### Backlog có thể tăng mà heap vẫn ổn định

Một consumer ổn định có thể xử lý chậm hơn producer trong một khoảng thời gian. Broker giữ phần backlog; client chỉ nhận một lượng hữu hạn; handler xử lý theo tốc độ mà dependency chịu được.

Điều quan trọng là phân biệt:

- **Backlog tăng ở broker:** cần tăng năng lực xử lý, giảm tốc độ producer hoặc chấp nhận thời gian catch-up.
- **Queue tăng trong JVM:** cần kiểm tra giới hạn prefetch, batch, executor và asynchronous fan-out.
- **In-flight tăng:** cần kiểm tra concurrency, thời gian xử lý và resource pool.

Không cố giải quyết mọi backlog bằng cách tăng queue capacity. Tăng queue chỉ trì hoãn thời điểm quá tải nếu tốc độ xử lý vẫn thấp hơn tốc độ đầu vào.

## 3. Ước lượng bộ nhớ cho message và task

Payload bytes trên broker không phải toàn bộ lượng heap mà ứng dụng giữ. Khi deserialize JSON thành Java object, framework có thể tạo thêm String, collection, object graph, header, buffer và bản sao tạm thời.

Một mô hình ước lượng đơn giản:

`M_queue ≈ N × S_retained`

Trong đó:

- N là số message đang được giữ ở client/application queue.
- S_retained là dung lượng thực tế một message chiếm trong JVM, gồm payload đã deserialize và metadata liên quan.

Nếu payload trung bình 48 KiB nhưng object graph sau deserialize giữ khoảng 2,5 lần dung lượng bytes, một message có thể giữ khoảng 120 KiB. Đây chỉ là giả định để lập ngân sách; phải đo bằng heap profiler hoặc allocation metrics của ứng dụng thực tế.

Với nhiều binding và replica:

`M_total ≈ replicas × (M_base + M_prefetch + M_appQueue + M_inFlight + M_producerBuffer)`

M_base bao gồm heap của framework, cache, connection, class metadata và dữ liệu nền của ứng dụng. Direct memory, native memory và RocksDB/off-heap cần được tính riêng nếu dùng.

### Ví dụ tính nhanh

Giả sử:

- 3 replica.
- Mỗi replica có 4 consumer.
- RabbitMQ prefetch 8 message trên mỗi consumer.
- Payload trung bình 48 KiB.
- Hệ số giữ lại sau deserialize là 2,5.

Số message chưa được ack tối đa theo prefetch xấp xỉ:

`3 × 4 × 8 = 96 messages`

Ước lượng phần memory tương ứng:

`96 × 48 KiB × 2,5 ≈ 11,25 MiB`

Con số này chưa tính object trung gian, task queue, output buffer, stack, cache và các binding khác. Nếu tăng prefetch lên 80, phần memory tương ứng tăng gần mười lần dù số consumer không đổi.

### Dùng percentile, không chỉ average

Message size và thời gian xử lý thường có phân phối lệch. Một vài message lớn có thể chiếm phần lớn memory. Hãy đo:

- Payload size p50, p95 và p99.
- Retained heap sau deserialize.
- Processing time p50, p95 và p99.
- Số message trong prefetch/queue.
- Số task active và queued.
- Heap occupancy sau GC và direct memory.

Khi sizing, dùng p95/p99 phù hợp với yêu cầu an toàn thay vì chỉ lấy message nhỏ nhất hoặc giá trị trung bình.

## 4. Số tác vụ đang xử lý và concurrency

Concurrency là số consumer/listener worker có thể nhận và xử lý message song song theo cơ chế binder. Trong Spring Cloud Stream, thuộc tính chung cho input binding là:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-service
          consumer:
            concurrency: 4
```

Thuộc tính concurrency chung có mặc định là 1. Binder có thể ánh xạ nó thành số consumer, listener hoặc thread theo mô hình middleware. Vì vậy, không nên giả định concurrency có cùng cách triển khai ở Kafka, RabbitMQ và Pulsar.

Concurrency cao hơn có thể tăng throughput nếu công việc độc lập và dependency còn capacity. Nhưng nó cũng làm tăng:

- Số message được xử lý cùng lúc.
- Số object và transaction đang sống.
- Số connection hoặc request tới database/API.
- Số message chưa ack/commit.
- CPU contention và context switching.
- Khả năng tranh chấp cùng một key hoặc tài nguyên.

### Chọn concurrency theo điểm nghẽn

Nếu mỗi message cần một database connection trong suốt quá trình xử lý, concurrency lớn hơn connection pool có thể chỉ tạo thêm thread chờ connection. Ví dụ pool có 12 connection mà concurrency là 48, phần lớn worker có thể nằm chờ database, giữ payload và làm tăng latency.

Hãy xác định resource giới hạn:

| Điểm nghẽn | Giới hạn nên đối chiếu |
|---|---|
| Database | Connection pool, query latency, lock contention |
| HTTP service | Connection pool, rate limit, timeout |
| CPU | Số core, CPU time/message, serialization |
| File/object storage | Concurrent request quota, IOPS |
| Kafka partition | Số partition và consumer assignment |
| Rabbit queue | Consumer count, prefetch và queue capacity |
| Pulsar subscription | Subscription type, partition và receiver queue |

Concurrency nên bắt đầu ở mức thấp, sau đó tăng theo từng bước trong load test. Đừng đặt concurrency bằng số CPU core theo thói quen nếu mỗi message chủ yếu chờ I/O; cũng đừng đặt rất cao nếu mỗi message tiêu thụ nhiều heap hoặc database connection.

### Concurrency không đồng nghĩa với số thread của mọi tầng

Một input binding có concurrency 4, function lại submit task vào executor 16 thread, và mỗi task gọi thêm một HTTP client có pool 20 connection. Số task thực tế và số request có thể khác nhau ở từng tầng.

Hãy ghi rõ các giới hạn riêng:

- Consumer concurrency: số listener/consumer.
- Worker concurrency: số task nghiệp vụ được chạy song song.
- Executor queue capacity: số task chờ trong JVM.
- Dependency concurrency: số request đang dùng connection/resource.
- Broker in-flight: số message đã giao nhưng chưa ack.

## 5. Little's Law để ước lượng số tác vụ cần thiết

Little's Law mô tả quan hệ giữa số công việc trung bình trong hệ thống, throughput và thời gian lưu lại:

`L = λ × W`

Trong đó:

- L là số message trung bình đang ở trong hệ thống.
- λ là throughput, tính bằng message/giây.
- W là thời gian trung bình một message ở trong hệ thống, tính bằng giây.

Ví dụ hệ thống cần xử lý 800 message/giây và thời gian xử lý trung bình là 25 ms:

`L = 800 × 0,025 = 20`

Cần khoảng 20 message đang được xử lý hoặc chờ trong vùng đo để duy trì throughput đó theo giả định ổn định. Đây không phải chỉ dẫn đặt queue capacity bằng 20. Nếu service time biến động lớn, cần headroom và giới hạn rõ ràng cho queue.

Một worker xử lý tuần tự với thời gian 25 ms có năng lực lý thuyết khoảng 40 message/giây. Tám worker có thể đạt khoảng 320 message/giây nếu công việc độc lập và không bị dependency giới hạn. Để đạt 800 message/giây, cần tăng năng lực xử lý hoặc giảm service time; chỉ tăng queue không làm throughput tăng.

### Queue capacity là thời gian chờ có thể chấp nhận

Nếu throughput xử lý là 500 message/giây và queue nội bộ có 5.000 message, queue đầy tương đương khoảng 10 giây công việc đang chờ, chưa tính thời gian xử lý mới. Hãy chọn queue capacity dựa trên latency/SLA và khả năng phục hồi, không chỉ dựa trên lượng RAM còn trống.

## 6. Giới hạn hàng đợi nội bộ của JVM

Spring Cloud Stream không cung cấp một property chung tên internalQueueCapacity cho mọi binder. Hàng đợi nội bộ thường xuất hiện khi ứng dụng chủ động dùng executor, asynchronous channel, Reactor buffer hoặc một cơ chế fan-out.

Với ThreadPoolTaskExecutor, queueCapacity phải hữu hạn. Ví dụ:

```java
@Bean
ThreadPoolTaskExecutor orderExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(32);
    executor.setThreadNamePrefix("order-worker-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.CallerRunsPolicy()
    );
    executor.initialize();
    return executor;
}
```

Trong ví dụ:

- Tối đa 8 task được thực thi đồng thời.
- Tối đa 32 task chờ trong executor queue.
- Khi queue đầy, CallerRunsPolicy chạy task trên thread gửi task, làm chậm producer của task và tạo backpressure.
- Queue không thể tăng vô hạn theo tốc độ đầu vào.

Với ThreadPoolExecutor, khi số thread đã đạt corePoolSize, task mới thường được đưa vào queue trước; chỉ khi queue đầy mới tăng thread tới maxPoolSize. Vì vậy, queueCapacity và core/max pool size cần được thiết kế cùng nhau. Trong ví dụ này core và max đều bằng 8 để số worker cố định.

### Không ack message trước khi task bất đồng bộ hoàn tất

Một lỗi nguy hiểm là function nhận message, submit task vào executor rồi trả về ngay:

```java
@Bean
Consumer<OrderCreated> processOrders(
        OrderExecutor executor,
        OrderService orderService) {
    return event -> executor.submit(() -> orderService.process(event));
}
```

Nếu binder xem function đã hoàn tất và ack/commit message ngay sau khi submit, process có thể chết trước khi task chạy xong. Broker sẽ không giao lại message đã được xác nhận, trong khi công việc chỉ tồn tại trong heap và bị mất khi JVM dừng.

Nếu dùng executor nội bộ, phải bảo đảm acknowledgment chỉ diễn ra sau khi công việc hoàn tất. Có thể chờ Future hoàn thành trong handler, dùng API manual acknowledgment đúng binder và chỉ ack khi task hoàn tất, hoặc ghi công việc vào một store/queue bền vững trước khi trả về. Không dựa vào một executor in-memory để thay thế durable queue.

### Rejection policy phải phù hợp semantics

| Policy | Hành vi | Khi phù hợp |
|---|---|---|
| CallerRunsPolicy | Thread submit chạy task khi queue đầy | Muốn đẩy áp lực ngược về listener/request thread |
| AbortPolicy | Ném RejectedExecutionException | Muốn từ chối rõ ràng và đưa lỗi vào error handling |
| DiscardPolicy | Bỏ task mới | Chỉ dùng khi mất task được chấp nhận rõ ràng |
| DiscardOldestPolicy | Bỏ task cũ nhất trong queue | Chỉ dùng với dữ liệu có thể thay thế và policy đã được chứng minh |

Không dùng DiscardPolicy hoặc DiscardOldestPolicy cho message nghiệp vụ cần bảo đảm giao nhận nếu không có cơ chế durable replay. Với CallerRunsPolicy, handler có thể chậm lại; hãy bảo đảm timeout/heartbeat/poll interval và shutdown behavior phù hợp.

## 7. Backpressure trong function/reactive pipeline

Với function xử lý reactive, có thể giới hạn concurrency và prefetch của toán tử Reactor:

```java
@Bean
Function<Flux<OrderCreated>, Flux<OrderResult>> processOrders() {
    return orders -> orders.flatMap(
            this::processOne,
            8,
            16
    );
}
```

Trong ví dụ, flatMap cho phép tối đa 8 inner publisher hoạt động đồng thời và prefetch 16 phần tử cho mỗi inner subscription theo semantics của Reactor. Đây là giới hạn trong pipeline Reactor; nó không tự giới hạn mọi fetch/prefetch của Kafka, RabbitMQ hoặc Pulsar client.

Không gọi subscribe() thủ công bên trong function để tách công việc khỏi lifecycle mà binder quản lý. Việc tự subscribe có thể làm mất backpressure, làm function kết thúc trước khi xử lý xong và khiến error/ack không còn gắn với message gốc.

Các toán tử như onBackpressureBuffer có thể tạo thêm queue. Nếu sử dụng, phải chọn capacity hữu hạn và xác định hành vi khi buffer đầy. Không dùng buffer không giới hạn trong luồng message liên tục.

### Backpressure chỉ hiệu quả khi nối xuyên các tầng

Một pipeline có thể giới hạn flatMap ở 8 nhưng binder vẫn prefetch 1.000 message. Khi đó heap vẫn có thể giữ nhiều message trước khi Reactor nhận chúng. Ngược lại, prefetch nhỏ nhưng function đẩy mỗi message vào một executor queue không giới hạn cũng không an toàn.

Hãy giới hạn từng tầng và kiểm thử tổng số message đang được giữ, không chỉ một operator.

## 8. Kafka: poll batch, fetch buffer và partition

Với regular Kafka binder, các consumer properties có thể đặt theo binding. Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-service
          consumer:
            concurrency: 4
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                max.poll.records: 100
                max.poll.interval.ms: 300000
                fetch.max.bytes: 10485760
                max.partition.fetch.bytes: 1048576
```

Các property có vai trò khác nhau:

| Property | Vai trò | Tác động |
|---|---|---|
| concurrency | Số consumer/listener cho binding | Tăng song song và số fetch loop |
| max.poll.records | Số record tối đa trả về trong một poll | Giới hạn batch được đưa cho listener mỗi lần poll |
| max.poll.interval.ms | Thời gian tối đa giữa các lần poll | Nếu xử lý batch quá lâu, consumer có thể bị xem là không còn hoạt động và group rebalance |
| fetch.max.bytes | Giới hạn dữ liệu trả về cho một fetch request | Ảnh hưởng kích thước fetch buffer |
| max.partition.fetch.bytes | Giới hạn dữ liệu mỗi partition trong fetch | Ảnh hưởng memory theo số partition được fetch |

max.poll.records không phải giới hạn tuyệt đối của toàn bộ dữ liệu client đang cache. Kafka consumer có thể fetch dữ liệu trước và giữ trong cache; poll trả các record theo từng batch. fetch.max.bytes cũng không phải giới hạn tuyệt đối trong mọi trường hợp: Kafka cho phép trả batch đầu tiên của partition nếu batch đó lớn hơn giới hạn để consumer vẫn tiến triển. Hãy đối chiếu kích thước message tối đa ở broker/topic.

### Ví dụ tính batch và thời gian xử lý

Nếu max.poll.records = 100 và mỗi record cần 40 ms xử lý tuần tự, thời gian xử lý batch xấp xỉ:

`100 × 40 ms = 4.000 ms`

Con số này chưa gồm deserialize, commit offset và thời gian gọi dependency. Nó cần nhỏ hơn max.poll.interval.ms với headroom đủ lớn. Nếu xử lý batch có concurrency, dùng p95/p99 và kiểm tra offset commit semantics; không chỉ chia thời gian trung bình cho số thread rồi kết luận an toàn.

### Concurrency và số partition

Trong consumer group, một partition chỉ được gán cho một consumer member tại một thời điểm. Nếu topic có 6 partition và mỗi replica dùng concurrency 4, ba replica có thể tạo tối đa 12 consumer nhưng chỉ 6 consumer có thể nhận partition của topic đó; phần còn lại idle đối với topic này.

Không tăng concurrency vượt xa số partition nếu không có lý do khác. Nếu cần throughput cao hơn, đánh giá partition count, key distribution, processing time và dependency capacity. Tăng partition có thể ảnh hưởng ordering theo key và cần kế hoạch vận hành.

### Kafka Streams khác regular Kafka binder

Kafka Streams binder dùng topology/task/thread model riêng. Số luồng xử lý có thể được điều khiển bằng num.stream.threads hoặc concurrency trên input binding theo hỗ trợ của phiên bản binder. Số task thực tế còn bị giới hạn bởi partition và topology. Không áp dụng máy móc concurrency của regular Kafka binder vào Kafka Streams mà chưa kiểm tra binder reference.

## 9. RabbitMQ: prefetch, concurrency và queue length

RabbitMQ đẩy message đến consumer theo cơ chế delivery. Prefetch giới hạn số delivery chưa được ack mà broker có thể giữ outstanding cho một consumer/channel. Khi đạt prefetch, broker ngừng gửi thêm cho đến khi có acknowledgment.

Spring Cloud Stream Rabbit binder có các thuộc tính quan trọng:

- concurrency: thuộc tính consumer chung của Spring Cloud Stream.
- maxConcurrency: số consumer tối đa của listener container; không hỗ trợ với containerType direct.
- prefetch: số message chưa ack được giao trước cho consumer; mặc định binder hiện hành là 1.
- maxLength và maxLengthBytes: giới hạn queue theo số message hoặc tổng byte khi binder khai báo queue.
- overflowBehavior: hành vi khi queue vượt giới hạn.

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-service
          consumer:
            concurrency: 4
      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              maxConcurrency: 4
              prefetch: 8
              maxLength: 100000
              maxLengthBytes: 1073741824
              overflowBehavior: reject-publish
```

Với concurrency 4 và prefetch 8, số delivery chưa ack có thể xấp xỉ tối đa 32 trên một instance trong điều kiện mỗi consumer có một giới hạn prefetch riêng. Với 3 replica, tổng số delivery in-flight có thể xấp xỉ 96. Hãy kiểm tra container type và cách binder/Spring AMQP áp dụng QoS trong version đang dùng.

RabbitMQ áp dụng prefetch theo từng consumer trong cấu hình hiện đại. Không nhầm với một giới hạn global duy nhất cho cả connection. Cách áp dụng global QoS có khác biệt và trong RabbitMQ 4.3 tính năng global/per-channel prefetch cũ đã bị deprecated và mặc định bị vô hiệu hóa. Hãy dùng per-consumer prefetch và tham chiếu tài liệu broker đúng version.

### Prefetch cao có lợi và có hại

Prefetch lớn có thể giữ consumer bận trong lúc xử lý, giảm round trip và tăng throughput. Nhưng nó cũng:

- Tăng số message chưa ack.
- Tăng heap client nếu message được giữ trong memory.
- Làm một consumer giữ nhiều message trong khi consumer khác ít việc.
- Tăng thời gian drain khi dừng consumer.
- Tăng khả năng redelivery nhiều message khi connection bị đóng.
- Làm tăng độ trễ của message nằm sau message chậm nếu handler tuần tự.

Prefetch 0 trong AMQP có nghĩa không giới hạn, không phải không prefetch. Không dùng giá trị 0 như cách tăng throughput mặc định.

### Giới hạn queue ở broker

maxLength và maxLengthBytes giới hạn queue khi binder tạo queue. Nếu vượt ngưỡng, overflow policy quyết định message mới bị reject hay message cũ bị loại theo cấu hình. Chọn policy dựa trên nghiệp vụ; không đặt drop-head nếu dữ liệu cũ không được phép mất.

Nếu hạ tầng tạo queue bằng policy/definitions bên ngoài, kiểm tra queue arguments và policy thực tế tại broker. Property của binder có thể không thay đổi được một queue đã tồn tại với declaration khác.

## 10. Pulsar: receiver queue và partition queue

Pulsar consumer có receiver queue để client prefetch message trước khi ứng dụng gọi receive hoặc listener xử lý. Kích thước queue lớn có thể tăng throughput nhưng làm tăng memory usage.

Các thuộc tính quan trọng của Pulsar Java client:

| Property | Ý nghĩa |
|---|---|
| receiverQueueSize | Số message có thể được tích lũy trong receiver queue |
| maxTotalReceiverQueueSizeAcrossPartitions | Giới hạn tổng receiver queue của consumer trên các partition |
| maxPendingMessages | Giới hạn message đang chờ của producer |
| maxPendingMessagesAcrossPartitions | Giới hạn pending messages trên producer partitioned topic |

Trong Spring Cloud Stream Pulsar binder, binder sử dụng Spring for Apache Pulsar và Spring Boot auto-configuration. Có thể đặt Pulsar consumer properties ở cấp ứng dụng, cấp binder hoặc extended binding. Extended binding có độ ưu tiên cao hơn binder-level và Spring Boot properties.

Ví dụ cấu hình receiver queue cho một binding:

```yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          processOrders-in-0:
            consumer:
              receiver-queue-size: 200
              max-total-receiver-queue-size-across-partitions: 5000
```

Hoặc cấu hình chung ở Spring Boot level:

```yaml
spring:
  pulsar:
    consumer:
      receiver-queue-size: 200
      max-total-receiver-queue-size-across-partitions: 5000
```

Ví dụ minh họa property mapping của Spring for Apache Pulsar. Kiểm tra metadata của đúng Spring Pulsar/binder version vì tên và vị trí property có thể thay đổi giữa các release.

### Partitioned topic

Với partitioned topic, receiver queue có thể được tạo theo partition. maxTotalReceiverQueueSizeAcrossPartitions giúp giới hạn tổng số message được đẩy về consumer trên tất cả partition. Nếu chỉ nhìn receiverQueueSize mà bỏ qua tổng partition queue, memory có thể lớn hơn dự kiến.

Ví dụ topic có 24 partition và receiver queue size cấu hình 500 message. Nếu không có giới hạn tổng phù hợp, tổng lượng message được buffer có thể lớn hơn nhiều so với 500. Hãy kiểm tra cách client version áp dụng maxTotalReceiverQueueSizeAcrossPartitions và đo số message thực tế.

### Queue size bằng 0

Một số Pulsar client version cho phép receiverQueueSize = 0 để tắt prefetch và yêu cầu message khi ứng dụng sẵn sàng. Điều này có thể cải thiện phân phối trong một số shared subscription nhưng giảm throughput và có giới hạn với partitioned topic, batch message hoặc receive API. Không dùng 0 như một thiết lập chung cho mọi topology; kiểm tra version và subscription type trước khi thử.

## 11. Giới hạn producer buffer

Consumer không phải nơi duy nhất giữ message. Khi broker chậm hoặc mạng nghẽn, producer có thể tích lũy message chưa gửi hoặc chưa được broker xác nhận.

### Kafka producer

Kafka producer có buffer memory để giữ record chờ gửi. Các thuộc tính thường cần xem xét:

- buffer.memory: tổng dung lượng buffer của producer.
- batch.size: kích thước batch mục tiêu cho mỗi partition.
- linger.ms: thời gian chờ thêm record để gom batch.
- max.block.ms: thời gian send/metadata có thể block khi buffer cạn hoặc metadata chưa sẵn sàng.
- compression.type: nén batch, giảm network và storage nhưng tiêu tốn CPU.

Nếu buffer cạn, send có thể block đến max.block.ms rồi lỗi. Không tăng buffer.memory vô hạn; điều đó chỉ chuyển backlog từ broker sang heap producer.

### RabbitMQ publisher

Publisher confirm giúp biết broker đã xác nhận publish. Nếu ứng dụng giữ quá nhiều future/callback chờ confirm, heap và pending state có thể tăng. Hãy giới hạn số publish outstanding, batch hợp lý và xử lý confirm/return sớm.

### Pulsar producer

Pulsar producer có giới hạn pending messages. Nếu queue đầy, producer có thể block hoặc lỗi tùy blockIfQueueFull và cấu hình timeout. Giới hạn pending message giúp bảo vệ client memory khi broker chậm.

Producer buffer cần được tính vào ngân sách memory của ứng dụng, đặc biệt khi một process vừa consume vừa produce.

## 12. Retry và DLQ cũng tiêu thụ capacity

Khi handler thất bại, retry giữ worker và message lâu hơn. Nếu retry nhanh và liên tục, một phần lớn concurrency có thể bị chiếm bởi message lỗi.

Ví dụ:

- 8 worker có thể xử lý 8 message cùng lúc.
- 6 message gặp dependency timeout và retry nhiều lần.
- Chỉ còn 2 worker phục vụ message mới.
- Queue/backlog tăng dù tốc độ producer không đổi.

Một số nguyên tắc:

- Dùng backoff có giới hạn cho lỗi tạm thời.
- Phân loại lỗi không retry được để chuyển DLQ sớm.
- Không requeue vô hạn poison message.
- Đặt retry budget và timeout tổng thể.
- Theo dõi retry rate riêng với success rate.
- Tránh retry ở nhiều tầng mà không tính tổng số lần thử.
- Giữ idempotency khi message có thể được giao lại.

Tăng concurrency để bù cho retry storm có thể làm database hoặc API downstream quá tải hơn. Trước hết cần giảm nguồn lỗi, backoff và giới hạn in-flight retry.

## 13. Ordering, fairness và kích thước batch

Concurrency và prefetch có thể ảnh hưởng thứ tự xử lý.

- Với Kafka, ordering được bảo đảm trong một partition; tăng concurrency không tạo ordering toàn topic.
- Với RabbitMQ, nhiều consumer trên cùng queue có thể xử lý song song và hoàn tất không theo thứ tự delivery.
- Với Pulsar Shared subscription, nhiều consumer xử lý song song; Key_Shared phù hợp hơn khi cần phân phối theo key theo semantics của Pulsar.
- Batch lớn tăng throughput nhưng làm tăng memory, thời gian xử lý và phạm vi redelivery khi lỗi.
- Prefetch quá lớn có thể khiến một consumer giữ nhiều message hơn consumer khác.

Nếu nghiệp vụ yêu cầu thứ tự theo account/order ID, hãy partition theo key hoặc dùng subscription/queue strategy phù hợp. Không giải quyết ordering bằng cách đặt concurrency = 1 cho toàn hệ thống nếu chỉ cần tuần tự theo từng key; hãy chọn mô hình partitioning có thể mở rộng.

## 14. Ví dụ sizing tổng hợp

Giả sử một service chạy 3 replica. Mỗi replica có:

- 4 consumer.
- Mỗi consumer giữ tối đa 8 message chưa ack.
- Worker xử lý tối đa 8 task đồng thời.
- Executor queue tối đa 32 task.
- Payload trung bình 48 KiB.
- Hệ số retained size 2,5.

Ước lượng prefetch memory toàn fleet:

`3 × 4 × 8 × 48 KiB × 2,5 ≈ 11,25 MiB`

Ước lượng executor queue memory toàn fleet:

`3 × 32 × 48 KiB × 2,5 ≈ 11,25 MiB`

Ước lượng 8 worker đang xử lý mỗi replica:

`3 × 8 × 48 KiB × 2,5 ≈ 2,81 MiB`

Tổng phần ước lượng này khoảng 25,31 MiB, chưa tính object graph bổ sung, producer buffer, batch copy, header, retry state, cache và memory nền.

Mô hình này chỉ để lập ngân sách sơ bộ. Thực tế có thể có cùng một message được giữ ở nhiều bản sao object, hoặc binder chuyển đổi payload theo cách khác. Dùng heap dump, allocation profiler và metrics để hiệu chỉnh.

### Giữ headroom cho JVM

Không dành toàn bộ heap cho queue. JVM cần memory cho:

- Framework, bean và metadata.
- Thread stack và task context.
- Connection/client buffers.
- Serialization/deserialization.
- Cache, transaction và database driver.
- GC survivor/old generation.
- Metrics, tracing và logging.

Đặt giới hạn queue đủ thấp để còn headroom khi burst hoặc message lớn bất thường. Kiểm thử với payload p99 và dependency latency p99, không chỉ dữ liệu trung bình.

## 15. Khi nào nên dùng queue, khi nào nên để broker giữ backlog?

Dùng queue nội bộ hữu hạn khi:

- Cần một lượng nhỏ task chờ để hấp thụ burst ngắn.
- Công việc độc lập và có thể xử lý bằng worker pool cố định.
- Có backpressure/rejection policy rõ ràng.
- Có thể giữ message unacknowledged cho đến khi task hoàn tất.
- Queue capacity được tính vào memory budget.

Để broker giữ backlog khi:

- Tải vượt khả năng xử lý trong thời gian dài.
- Cần durability qua process restart.
- Muốn nhiều consumer instance chia sẻ công việc.
- Cần retry/replay theo broker semantics.
- Ứng dụng không thể bảo đảm xử lý task in-memory khi JVM dừng.

Không dùng in-memory queue để làm lớp đệm bền vững giữa hai hệ thống. Nếu cần tách producer khỏi worker dài hạn, hãy dùng broker topic/queue hoặc một durable work store.

## 16. Quan sát capacity và dấu hiệu quá tải

Theo dõi cả broker, binder và JVM.

| Chỉ số | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Broker backlog/lag | Công việc chưa được consumer xử lý | Tăng liên tục |
| Ready messages (RabbitMQ) | Message chưa giao | Tăng trong khi consumer capacity thấp |
| Unacked messages (RabbitMQ) | Delivery đang được consumer giữ | Cao bất thường hoặc không giảm |
| Pulsar subscription backlog | Message chưa ack | Tăng theo thời gian |
| Client receiver/fetch queue | Message đã được kéo về client | Gần giới hạn liên tục |
| Executor queue size | Task đang chờ trong JVM | Luôn đầy hoặc tăng không giảm |
| Active worker count | Task đang chạy | Luôn bằng max và latency tăng |
| Rejected task count | Task không được nhận vào executor | Lớn hơn 0 |
| JVM heap after GC | Memory còn giữ sau GC | Tăng theo thời gian |
| Direct memory | Buffer ngoài heap | Tăng bất thường |
| GC pause/time | Chi phí thu gom | Pause kéo dài, throughput giảm |
| Processing latency p95/p99 | Thời gian xử lý | Tăng khi queue tăng |
| Dependency pool usage | Resource downstream | Pool chạm max, wait time tăng |
| Retry/DLQ rate | Message xử lý thất bại | Retry storm hoặc poison message |

Một binding đang running không có nghĩa consumer còn capacity. Hãy xem throughput, latency, backlog và in-flight cùng lúc.

## 17. Kiểm thử quá tải và backpressure

Không chỉ load test happy path. Cần kiểm tra queue có giữ giới hạn khi hệ thống bị chậm.

### Baseline test

- Dùng payload có kích thước đại diện.
- Tăng tải từ thấp lên mức mục tiêu.
- Ghi throughput, latency p50/p95/p99, heap và backlog.
- Xác minh queue không tăng vô hạn.
- Xác minh consumer concurrency và worker count đúng cấu hình.

### Burst test

- Tăng đột ngột producer rate trong một khoảng ngắn.
- Xác minh broker backlog tăng thay vì heap tăng không kiểm soát.
- Xác minh client prefetch và executor queue không vượt giới hạn.
- Sau burst, xác minh consumer catch up và backlog giảm.

### Slow dependency test

- Làm database/API chậm hơn bình thường.
- Xác minh concurrency không làm cạn connection pool.
- Xác minh queue nội bộ đầy sẽ kích hoạt backpressure/rejection đã chọn.
- Xác minh message chưa được ack trước khi nghiệp vụ hoàn tất.

### Failure/restart test

- Dừng một consumer khi đang xử lý.
- Kiểm tra message redelivery/offset semantics.
- Restart broker hoặc dependency nếu cần.
- Xác minh không mất task đã được ack sớm.
- Kiểm tra retry không làm queue tăng vô hạn.

### Memory pressure test

- Dùng payload p95/p99 và message có object graph lớn.
- Tăng số partition hoặc subscription để kiểm tra tổng prefetch.
- Quan sát heap, direct memory và GC.
- Xác minh OOM không xảy ra trong thời gian soak test.
- Kiểm tra graceful shutdown có drain hoặc dừng task theo policy.

## 18. Quy trình điều chỉnh theo thứ tự

Khi service xử lý chậm hoặc memory cao, điều chỉnh theo trình tự:

1. Đo tốc độ producer, consumer throughput và backlog.
2. Xác định message size p95/p99 và retained heap.
3. Xác định số consumer/worker thực tế.
4. Kiểm tra dependency pool và thời gian xử lý.
5. Giới hạn application queue và asynchronous fan-out.
6. Điều chỉnh concurrency theo partition/subscription và dependency capacity.
7. Điều chỉnh prefetch/fetch/receiver queue để giới hạn client buffer.
8. Đặt queue length/byte limit ở broker nếu phù hợp.
9. Đặt batch size và retry budget hợp lý.
10. Chạy lại load, burst và failure tests.
11. Ghi lại throughput/latency/memory trước và sau thay đổi.

Nếu throughput thấp do database query chậm, tăng prefetch hoặc concurrency thường chỉ tăng số message chờ và số connection tranh chấp. Hãy xử lý bottleneck trước khi tăng parallelism.

## 19. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Heap tăng dù broker backlog không lớn | Client prefetch hoặc app queue quá lớn | Giảm prefetch, batch và queue capacity |
| Broker backlog tăng nhưng heap ổn định | Consumer throughput thấp hơn producer | Tối ưu handler, tăng năng lực có kiểm soát hoặc giảm producer rate |
| Nhiều task chờ executor | Worker pool nhỏ hoặc dependency chậm | Đo service time và giới hạn queue |
| OOM sau khi tăng concurrency | Nhiều payload/task sống cùng lúc | Giảm concurrency/prefetch và tính lại memory budget |
| Rabbit unacked tăng cao | Prefetch lớn hoặc handler chưa ack | Giảm prefetch, kiểm tra processing/ack time |
| Kafka rebalance khi xử lý batch | Poll không được gọi trước max.poll.interval.ms | Giảm max.poll.records, tối ưu xử lý hoặc thiết kế poll/worker an toàn |
| Kafka consumer idle dù concurrency cao | Số consumer lớn hơn số partition | Điều chỉnh concurrency hoặc partition plan |
| Pulsar memory cao với nhiều partition | Receiver queue nhân theo partition | Giảm receiverQueueSize và đặt max total queue |
| Retry làm throughput giảm mạnh | Nhiều worker bị giữ bởi message lỗi | Backoff, phân loại lỗi và DLQ |
| Message bị mất sau khi submit executor | Binder ack trước khi task hoàn tất | Chờ task hoặc ack thủ công sau completion |
| Queue đầy nhưng task bị bỏ | Rejection policy discard | Dùng policy có backpressure hoặc error handling bền vững |
| CPU thấp nhưng latency cao | Worker chờ connection/dependency | Kiểm tra pool wait, timeout và downstream |
| Producer bị block | Producer buffer đầy hoặc broker chậm | Giới hạn outstanding sends, xử lý confirm và kiểm tra broker |
| Tăng prefetch không tăng throughput | Bottleneck nằm ở handler/dependency hoặc broker | Đo từng tầng, không tiếp tục tăng buffer |

## 20. Checklist cấu hình production

Trước khi phát hành:

- Xác định broker backlog, client prefetch, app queue và in-flight task riêng biệt.
- Đặt concurrency rõ ràng cho input binding quan trọng.
- Đặt giới hạn executor queue hữu hạn nếu có asynchronous worker.
- Chọn rejection policy không làm mất message ngoài ý muốn.
- Đảm bảo ack/offset commit chỉ xảy ra sau khi công việc cần bảo đảm đã hoàn tất.
- Với Kafka, cấu hình max.poll.records và kiểm tra max.poll.interval.ms.
- Với RabbitMQ, đặt prefetch và concurrency dựa trên message size/processing time.
- Với Pulsar, đặt receiverQueueSize và giới hạn tổng qua partition.
- Tính producer buffer vào memory budget.
- Đặt queue max length/bytes ở broker khi cần giới hạn backlog.
- Kiểm tra retry/backoff không tạo retry storm.
- Giữ headroom cho heap, direct memory và GC.
- Theo dõi queue depth, in-flight, heap, latency và dependency pool.
- Chạy burst, slow dependency, restart và memory pressure test.
- Ghi lại cấu hình và kết quả đo để có thể rollback.

## Kết luận

Giới hạn hàng đợi, bộ nhớ và số tác vụ đang xử lý là ba phần của cùng một bài toán capacity. Broker backlog thường nằm trên broker storage; client prefetch/fetch buffer, application queue và in-flight task mới trực tiếp giữ dữ liệu trong JVM. Tăng một giới hạn mà không tính các tầng khác có thể chuyển điểm nghẽn từ broker sang heap hoặc dependency pool.

Trong Spring Cloud Stream, concurrency chung của input binding mặc định là 1. Kafka cần kiểm soát poll batch, fetch buffer, poll interval và partition assignment. RabbitMQ cần kiểm soát consumer concurrency, maxConcurrency, prefetch và queue length/bytes. Pulsar cần kiểm soát receiverQueueSize và tổng receiver queue trên partition. Mỗi binder có semantics riêng, vì vậy hãy xác minh property theo version đang dùng.

Dùng queue hữu hạn, worker count rõ ràng và backpressure để giữ memory ổn định. Không ack message trước khi asynchronous task hoàn tất; không dùng in-memory queue như một durable broker. Đo throughput, latency, heap, queue depth và in-flight work, rồi kiểm thử burst, dependency chậm và restart để chứng minh giới hạn thực sự có hiệu lực.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream 5.0 — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/binding-properties.html): consumer concurrency và các thuộc tính chung của input binding.
- [Spring Cloud Stream 5.0.4 — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html): prefetch, maxConcurrency, maxLength và maxLengthBytes.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): giới hạn delivery chưa ack theo consumer và tác động đến memory.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): in-flight delivery, QoS và throughput.
- [Spring Cloud Stream 5.1 — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html): consumer-specific configuration và max.poll.records.
- [Apache Kafka 4.4 — Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/): max.poll.records, max.poll.interval.ms, fetch.max.bytes và max.partition.fetch.bytes.
- [Apache Kafka 4.4 — KafkaConsumer API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html): poll loop, processing thread và partition pause considerations.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html): Pulsar Boot properties, binder properties và extended binding precedence.
- [Apache Pulsar 4.0 — ConsumerBuilder API](https://pulsar.apache.org/api/client/4.0.x/org/apache/pulsar/client/api/ConsumerBuilder.html): receiverQueueSize và giới hạn receiver queue trên partitioned topic.

Khi triển khai, dùng reference guide trùng với Spring Cloud Stream, Spring Boot, binder, Kafka client, RabbitMQ hoặc Pulsar version trong dependency/runtime. Không giả định default hoặc property mapping của một release được giữ nguyên ở mọi phiên bản.

