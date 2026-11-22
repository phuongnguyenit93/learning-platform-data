# Tránh block trong listener

Trong Spring Kafka, listener thường được gọi trên consumer thread do listener container quản lý. Trong lúc listener đang xử lý một record, consumer đó chưa quay lại vòng `poll()` để lấy dữ liệu tiếp theo. Nếu listener chờ I/O quá lâu, chờ một future, giữ lock hoặc chạy tính toán kéo dài, thời gian giữa hai lần poll tăng lên, throughput giảm và consumer có thể vượt `max.poll.interval.ms`.

Tránh block không có nghĩa là mọi listener đều phải bất đồng bộ. Một listener xử lý đồng bộ vẫn phù hợp nếu công việc có thời gian giới hạn, timeout rõ ràng và throughput đáp ứng yêu cầu. Điều quan trọng là kiểm soát thời gian xử lý, không để một dependency chậm giữ consumer thread vô thời hạn, và chỉ xác nhận offset khi công việc đã hoàn tất hoặc được chuyển giao bền vững.

Bài học thuộc chương **Hiệu năng** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Consumer thread thực hiện những việc gì?

Listener container sở hữu Kafka consumer và điều phối vòng đời poll, dispatch record, acknowledgment và commit offset. Với record listener, container gọi listener cho từng record được lấy từ poll. Trong thời gian listener chạy đồng bộ, consumer thread thường chưa quay lại poll để nhận batch tiếp theo.

~~~mermaid
sequenceDiagram
    participant C as Consumer thread
    participant K as Kafka broker
    participant L as Listener
    C->>K: poll()
    K-->>C: records
    C->>L: invoke listener(record)
    Note over C,L: Consumer thread đang bận xử lý
    L-->>C: return
    C->>K: poll() tiếp theo
~~~

Với batch listener, một lần invocation có thể xử lý nhiều record trước khi container quay lại poll. Vì vậy, tổng thời gian xử lý batch cũng phải nằm trong ngân sách poll.

Không nên gọi trực tiếp `KafkaConsumer.poll()` từ listener. Consumer do container quản lý; tự điều khiển consumer từ listener có thể phá vỡ lifecycle, thread ownership và offset management của Spring Kafka.

## 2. Block trong listener có nghĩa là gì?

Một thao tác block là thao tác khiến consumer thread phải chờ trước khi có thể tiếp tục. Những ví dụ thường gặp:

- Gọi HTTP đồng bộ tới service chậm hoặc không có read timeout.
- Truy vấn database chờ connection pool, lock hoặc query lâu.
- Gọi `Future.get()`, `CompletableFuture.join()` hoặc `CountDownLatch.await()`.
- Dùng `Thread.sleep()` để chờ retry hoặc chờ dependency.
- Chờ semaphore, synchronized lock hoặc queue không có phần tử.
- Đọc/ghi file lớn hoặc gọi hệ thống filesystem chậm.
- Thực hiện CPU-bound work kéo dài trong listener.
- Retry thủ công nhiều lần ngay trong listener.
- Ghi log đồng bộ vào appender hoặc sink bị nghẽn.

Một lời gọi có vẻ nhanh trong môi trường dev có thể block hàng giây khi production có network latency, connection pool contention hoặc downstream overload. Đừng đánh giá hiệu năng chỉ bằng thời gian trung bình trên máy local.

## 3. Dấu hiệu listener đang bị block

Một số dấu hiệu thường xuất hiện cùng nhau:

| Triệu chứng | Khả năng liên quan |
| --- | --- |
| Consumer lag tăng liên tục | Listener xử lý chậm hơn tốc độ record đến. |
| Poll interval tăng cao | Consumer thread bị giữ trong listener hoặc chờ lock/I/O. |
| Rebalance không mong muốn | Consumer vượt max.poll.interval hoặc bị mất membership. |
| Throughput thấp dù CPU còn nhàn | Listener đang chờ I/O hoặc pool bên ngoài. |
| HTTP/DB connection pool cạn | Listener giữ connection quá lâu hoặc concurrency vượt capacity. |
| Độ trễ p95/p99 tăng mạnh | Có tail latency ở dependency hoặc lock contention. |
| Retry tăng cùng timeout | Listener đang xử lý dependency không ổn định. |
| Heap/queue tăng | Công việc được tích lũy nhanh hơn tốc độ xử lý. |

Consumer lag chỉ là một tín hiệu; lag tăng có thể do producer tăng tốc, partition thiếu hoặc consumer chậm. Hãy kết hợp lag với listener duration, poll interval, thread dump và metric downstream để tìm nguyên nhân.

## 4. max.poll.interval.ms và liveness

`max.poll.interval.ms` giới hạn khoảng thời gian tối đa giữa các lần gọi `poll()` khi consumer đang tham gia group. Nếu listener xử lý lâu khiến consumer không poll kịp, consumer có thể bị xem là không còn tiến triển; partition có thể được giao lại và lần xử lý hiện tại có thể mất quyền commit offset.

Cần phân biệt:

- `max.poll.interval.ms`: giới hạn tiến độ ứng dụng giữa hai lần poll.
- `session.timeout.ms`: giới hạn thời gian coordinator chờ heartbeat từ consumer trước khi xem member mất kết nối.
- Heartbeat: cơ chế duy trì membership; ở các Kafka client hiện đại, heartbeat có thể chạy trên luồng nền riêng.
- Listener duration: thời gian ứng dụng thực tế dùng để xử lý record hoặc batch.

Heartbeat vẫn có thể tiếp tục trong khi listener đang chạy, nhưng điều đó không loại bỏ giới hạn max poll interval. Nếu listener giữ consumer thread quá lâu, consumer vẫn có thể bị loại khỏi group do không gọi poll đúng hạn.

Không tăng `max.poll.interval.ms` để che giấu một listener có thể block vô hạn. Hãy đo thời gian xử lý, đặt timeout cho dependency và chỉ điều chỉnh poll interval sau khi hiểu worst-case workload.

## 5. Tính ngân sách thời gian cho poll

Một consumer cần hoàn thành công việc của dữ liệu đã nhận trước lần poll kế tiếp. Với record listener, nếu một poll trả về nhiều record và container xử lý tuần tự, thời gian tổng có thể gần bằng tổng thời gian xử lý các record trong poll, cộng overhead.

Ví dụ minh họa:

~~~text
max.poll.records = 100
Thời gian xử lý p95 mỗi record = 80 ms

Ngân sách xử lý gần đúng:
100 x 80 ms = 8 giây
Cộng overhead serialize, dispatch, commit và scheduling
~~~

Không lấy p95 nhân số record rồi coi đó là worst case. Tail latency của nhiều record có thể cộng dồn; hãy đo thời gian xử lý cả poll/batch và kiểm tra p99 trong tải thực tế.

Các thông số liên quan:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
~~~

Các giá trị trên chỉ minh họa. Chọn `max.poll.records` theo kích thước record, thời gian xử lý và memory; chọn `max.poll.interval.ms` với biên an toàn dựa trên thời gian xử lý tối đa có kiểm soát. Nếu giảm số record mỗi poll, số lần poll tăng nhưng thời gian xử lý một đợt có thể giảm.

## 6. Đặt timeout cho mọi I/O bên ngoài

Một listener đồng bộ vẫn có thể an toàn nếu mọi lời gọi bên ngoài có deadline. Timeout cần bao phủ cả thời gian chờ kết nối và thời gian chờ phản hồi.

Ví dụ dùng Java HttpClient:

~~~java
@Bean
HttpClient downstreamHttpClient() {
    return HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();
}

public String fetchOrderStatus(URI uri) throws Exception {
    HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

    HttpResponse<String> response =
        downstreamHttpClient.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

    if (response.statusCode() >= 500) {
        throw new DownstreamUnavailableException(
            "Downstream returned " + response.statusCode()
        );
    }

    return response.body();
}
~~~

`send()` vẫn block consumer thread, nhưng thời gian chờ đã được giới hạn. Timeout 2 giây kết nối và 3 giây request không có nghĩa tổng thời gian luôn đúng 3 giây; cần tính cả DNS, TLS, connection reuse, retry ở client và scheduling.

Với database, đặt query timeout, transaction timeout và giới hạn thời gian chờ connection pool. Với Redis hoặc HTTP client, cấu hình connect, read/response và acquisition timeout. Tránh một dependency có timeout dài hơn toàn bộ ngân sách xử lý record.

## 7. Truyền deadline xuyên suốt

Nếu listener gọi nhiều dependency nối tiếp, mỗi dependency không nên được phép dùng toàn bộ timeout riêng. Một record có deadline tổng; mỗi bước chỉ được dùng phần thời gian còn lại.

Ví dụ:

~~~java
Instant deadline = Instant.now().plusSeconds(5);

Duration remaining = Duration.between(
    Instant.now(),
    deadline
);

if (remaining.isNegative() || remaining.isZero()) {
    throw new ProcessingDeadlineExceededException();
}

downstreamClient.call(request, remaining);
~~~

Trong hệ thống phân tán, có thể truyền deadline hoặc request timeout qua header/correlation metadata theo contract nội bộ. Khi nhận record, tính ngân sách còn lại và truyền xuống database/HTTP client.

Deadline giúp tránh tình huống listener chờ 3 giây ở service A rồi tiếp tục chờ 3 giây ở service B dù SLA của toàn record chỉ là 4 giây. Khi hết deadline, ném exception phù hợp để error handler retry hoặc recover theo policy.

## 8. Không retry bằng vòng lặp sleep trong listener

Không nên viết retry thủ công như sau:

~~~java
@KafkaListener(topics = "orders")
public void listen(OrderEvent event) {
    for (int attempt = 0; attempt < 5; attempt++) {
        try {
            downstreamClient.process(event);
            return;
        }
        catch (TransientException exception) {
            Thread.sleep(1_000);
        }
    }

    throw new ProcessingFailedException();
}
~~~

Mỗi lần sleep giữ consumer thread, làm giảm throughput và có thể đẩy consumer vượt poll interval. Khi nhiều record gặp lỗi cùng lúc, tất cả consumer thread có thể bị giữ trong backoff.

Dùng cơ chế retry của Spring Kafka như `DefaultErrorHandler` với backoff hữu hạn cho blocking retry, hoặc retry topic cho non-blocking retry nếu ordering và semantics phù hợp. Với transactional listener, đường retry sau rollback thường dùng `AfterRollbackProcessor`.

Retry phải phân loại exception. Lỗi dữ liệu vĩnh viễn không nên lặp lại nhiều lần; lỗi tạm thời cần backoff và giới hạn attempts. Không retry ở cả HTTP client, service và Kafka handler mà không tính tổng số lần thử và tổng deadline.

## 9. Giới hạn connection pool và downstream concurrency

Tăng listener concurrency có thể làm số request đồng thời tới database hoặc HTTP service tăng theo. Nếu downstream chỉ chịu được 20 request đồng thời nhưng consumer tạo 80 request, connection pool và service có thể bị quá tải.

Đặt giới hạn ở các lớp:

- Kafka listener concurrency.
- HTTP connection pool và max connections.
- Database connection pool.
- Worker executor size.
- Semaphore/bulkhead theo dependency.
- Rate limit theo service hoặc tenant.

Ví dụ semaphore giới hạn số lời gọi đồng thời:

~~~java
private final Semaphore downstreamSlots = new Semaphore(20);

public Result callDownstream(Request request) {
    boolean acquired = downstreamSlots.tryAcquire();

    if (!acquired) {
        throw new DownstreamSaturatedException();
    }

    try {
        return downstreamClient.call(request);
    }
    finally {
        downstreamSlots.release();
    }
}
~~~

`tryAcquire()` không chờ vô hạn. Khi không còn slot, listener thất bại nhanh để error handler hoặc backpressure coordinator xử lý. Nếu chọn acquire có timeout, timeout đó phải nằm trong ngân sách record.

## 10. Điều chỉnh concurrency có giới hạn

Spring Kafka hỗ trợ concurrency trên listener container factory. Mỗi child container sở hữu consumer riêng; nhiều consumer có thể xử lý song song các partition được assign.

~~~java
factory.setConcurrency(4);
~~~

Concurrency có thể tăng throughput khi có đủ partition và downstream còn capacity. Nhưng concurrency quá cao có thể làm tăng:

- Số request đồng thời tới database/HTTP.
- Số thread và memory.
- Connection pool contention.
- Context switching và lock contention.
- Số record đang in-flight khi rebalance hoặc shutdown.

Trong một consumer group, số consumer active hữu ích bị giới hạn bởi số partition được assign. Tăng concurrency vượt số partition không làm một partition được xử lý song song theo thứ tự; một số child container có thể không có partition.

Tăng concurrency chỉ sau khi đo được bottleneck và kiểm tra capacity downstream. Nếu listener block do một API chậm, thêm consumer có thể chỉ làm API quá tải hơn.

## 11. Tách CPU-bound và I/O-bound work

Hai loại công việc cần cách xử lý khác nhau:

| Loại | Ví dụ | Hướng tối ưu |
| --- | --- | --- |
| I/O-bound | HTTP, JDBC, Redis, file/network | Timeout, connection pool, async I/O có giới hạn, bulkhead |
| CPU-bound | Nén, mã hóa, tính toán, parse lớn | Profiling CPU, giảm allocation, batch, giới hạn worker theo CPU |

Nếu CPU thấp nhưng listener duration cao, hãy tìm thời gian chờ I/O, lock hoặc queue. Nếu CPU cao và thread dump cho thấy listener đang tính toán, thêm async thread thường không tăng năng lực CPU; có thể chỉ tăng context switching.

Không chạy CPU-bound task nặng trên common ForkJoinPool mặc định nếu không kiểm soát tải. Dùng executor có kích thước và queue phù hợp, đồng thời giữ giới hạn số tác vụ in-flight.

## 12. Dùng bounded executor khi cần offload

Offload có thể hữu ích khi listener phải gọi công việc tốn thời gian và ứng dụng có cách quản lý acknowledgment phù hợp. Executor phải bounded; queue vô hạn có thể làm heap tăng không giới hạn khi downstream chậm.

Ví dụ cấu hình:

~~~java
@Bean
ThreadPoolTaskExecutor orderExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(16);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("order-worker-");
    executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy()
    );
    return executor;
}
~~~

Queue capacity và pool size phải phù hợp throughput downstream. Khi queue đầy, `AbortPolicy` từ chối công việc; lỗi rejection cần được đưa về listener/error handler hoặc backpressure policy. Không dùng `CallerRunsPolicy` một cách vô thức vì nó có thể chạy task nặng ngay trên consumer thread, làm listener block trở lại.

Executor không làm công việc trở nên bền vững. Nếu process dừng, task đang chạy và queue trong memory có thể mất.

## 13. Offload bất đồng bộ nhưng không xác nhận offset quá sớm

Mẫu nguy hiểm:

~~~java
@KafkaListener(topics = "orders", groupId = "orders")
public void listen(OrderEvent event) {
    orderExecutor.execute(() -> orderService.process(event));
}
~~~

Listener return ngay sau khi enqueue. Với acknowledgment tự động thông thường, container có thể commit offset trước khi worker hoàn tất. Nếu process crash sau commit nhưng trước khi xử lý xong, record không được Kafka giao lại và task trong RAM đã mất.

Chỉ offload khi có một trong các contract rõ ràng:

1. Dùng asynchronous listener return type được Spring Kafka version hỗ trợ để container biết thời điểm tác vụ hoàn tất.
2. Dùng manual acknowledgment với cấu hình async acknowledgment phù hợp và chỉ acknowledge sau khi công việc hoàn tất.
3. Lưu công việc vào một nơi bền vững trong listener transaction trước khi xác nhận offset.
4. Chuyển record sang một work topic hoặc durable queue và xác nhận sau khi handoff bền vững.

Nếu không có contract như trên, xử lý đồng bộ trong listener với timeout thường đơn giản và an toàn hơn.

## 14. Asynchronous listener return type

Các phiên bản Spring Kafka mới hỗ trợ một số kiểu trả về bất đồng bộ, chẳng hạn `CompletableFuture` và `Mono`. Khi dùng tính năng này, container có thể chờ completion để xác nhận record theo semantics async listener của phiên bản tương ứng.

Ví dụ minh họa:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders",
    containerFactory = "asyncOrderListenerFactory"
)
public CompletableFuture<Void> listen(OrderEvent event) {
    return CompletableFuture.runAsync(
        () -> orderService.process(event),
        orderExecutor
    );
}
~~~

Nếu công việc hoàn tất bình thường, future hoàn tất thành công. Nếu worker ném exception, future hoàn tất exceptional để container xử lý theo error handling path được hỗ trợ.

Trước khi dùng, kiểm tra Spring Kafka version và tài liệu tương ứng: kiểu return được hỗ trợ, AckMode được container điều chỉnh hay phải cấu hình, async acknowledgment, retry behavior và cách xử lý future completion sau rebalance. Không giả định mọi version Spring Kafka đều hỗ trợ cùng một kiểu return.

Executor vẫn phải bounded và có rejection policy. Future không được tách rời khỏi listener; nếu method trả future đã hoàn tất trước khi công việc thực sự hoàn tất, offset vẫn có thể được xác nhận quá sớm.

## 15. Manual acknowledgment và async acknowledgment

Nếu dùng manual acknowledgment, listener hoặc worker chỉ acknowledge sau khi công việc đã hoàn tất theo contract. Với xử lý bất đồng bộ/out-of-order, cần kiểm tra `asyncAcks` và AckMode của container.

Ví dụ khái niệm:

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "manualAckOrderFactory"
)
public void listen(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderExecutor.execute(() -> {
        try {
            orderService.process(event);
            acknowledgment.acknowledge();
        }
        catch (Exception exception) {
            // Gửi lỗi vào cơ chế retry/recovery phù hợp.
            failureHandler.handle(event, exception);
        }
    });
}
~~~

Đây chỉ là phác thảo luồng. Không sao chép trực tiếp nếu chưa cấu hình manual AckMode, async acknowledgment và error handling đúng version. Acknowledgment có thể chịu ràng buộc về thứ tự và consumer thread; việc gọi từ worker thread phải được hỗ trợ bởi cấu hình container.

Khi bật async acknowledgment, container có thể giữ các offset đã acknowledge ngoài thứ tự và pause consumer cho đến khi các offset còn thiếu được xác nhận. Nếu một task không bao giờ hoàn tất, partition có thể bị giữ lại. Cần timeout, cancellation và xử lý lỗi cho mọi task.

## 16. Durable handoff cho công việc dài

Nếu một công việc kéo dài nhiều phút hoặc cần tồn tại qua restart, không nên giữ consumer thread hoặc chỉ lưu task trong RAM. Hãy chuyển trách nhiệm sang một cơ chế bền vững:

- Ghi job vào database trong transaction rồi worker khác đọc job.
- Ghi outbox row và relay sang work topic.
- Publish command sang topic riêng và xác nhận input sau khi broker xác nhận handoff.
- Dùng durable work queue nếu kiến trúc có hệ thống đó.

Ví dụ mô hình:

~~~mermaid
flowchart TD
    A[Input topic] --> B[Listener]
    B --> C[Persist job hoặc outbox]
    C --> D[Commit input offset]
    C --> E[Worker đọc durable job]
    E --> F[Thực hiện công việc dài]
    F --> G[Đánh dấu hoàn tất]
~~~

Nếu ghi job database và commit Kafka offset không nằm trong cùng một transaction, cần xử lý failure window và idempotency. Có thể dùng database transaction synchronization hoặc inbox/outbox pattern tùy chiều dữ liệu và mức bảo đảm cần thiết.

Durable handoff làm listener ngắn và ổn định hơn, nhưng thêm thành phần lưu trữ, worker lifecycle, retry và trạng thái job. Thiết kế job cần event ID duy nhất để chống tạo trùng khi input được giao lại.

## 17. Pause/resume để tạo backpressure

Khi bounded queue hoặc downstream worker pool gần đầy, có thể yêu cầu listener container pause để hạn chế nhận thêm record. Khi queue giảm xuống dưới low watermark và các pause reason khác đã được gỡ, container resume.

Ví dụ logic:

~~~java
if (queueDepth >= HIGH_WATERMARK) {
    container.pause();
}
else if (queueDepth <= LOW_WATERMARK) {
    container.resume();
}
~~~

Dùng high/low watermark khác nhau để tránh pause/resume liên tục. Tính cả record đã poll và task in-flight vì pause không thu hồi record đã nhận. Container vẫn tiếp tục poll để duy trì consumer liveness; partition đang pause không cấp record mới cho listener.

Pause/resume không thay thế acknowledgment đúng. Nếu listener đã commit offset ngay sau khi enqueue vào RAM, pause chỉ làm chậm việc nhận thêm record chứ không bảo vệ task khỏi mất khi process restart.

## 18. Ordering và idempotency khi tăng bất đồng bộ

Khi listener xử lý bất đồng bộ, thứ tự hoàn thành có thể khác thứ tự record được poll. Ví dụ event `OrderUpdated(version=2)` có thể hoàn tất trước `OrderUpdated(version=1)` nếu hai task chạy song song.

Nếu ordering theo key hoặc aggregate là yêu cầu nghiệp vụ:

- Giữ xử lý tuần tự theo partition hoặc theo key.
- Dùng keyed executor/partitioned worker queue.
- Đưa sequence/version vào event và từ chối cập nhật cũ.
- Không ack offset vượt qua record trước đó nếu container không hỗ trợ async ack semantics phù hợp.
- Dùng idempotency key để xử lý redelivery.

Kafka chỉ đảm bảo thứ tự record trong một partition. Offload sang worker pool không tự bảo toàn thứ tự hoàn thành nghiệp vụ. Cần test riêng trường hợp task đầu chậm hơn task sau.

## 19. Retry, circuit breaker và timeout

Một downstream chậm có thể gây block, nhưng retry liên tục có thể làm tải tăng thêm. Kết hợp timeout, circuit breaker, bulkhead và retry policy:

- Timeout giới hạn thời gian mỗi lời gọi.
- Circuit breaker ngăn tiếp tục gọi dependency đang lỗi kéo dài.
- Bulkhead giới hạn số request đồng thời.
- Retry có backoff và giới hạn attempts.
- Backpressure pause listener khi năng lực xử lý phía sau không còn.

Không retry ngay trong listener bằng vòng lặp sleep. Để exception đi tới error handler hoặc chuyển sang retry topic theo policy. Với circuit breaker đang mở, có thể fail nhanh để retry/recover; đừng giữ consumer thread chờ trạng thái half-open bằng sleep.

## 20. Transaction và side effect khi offload

Kafka transaction context và Spring database transaction thông thường gắn với thread hoặc resource context cụ thể. Khi chuyển việc sang executor, đừng giả định transaction từ listener tự truyền sang worker.

Một số rủi ro:

- Kafka transaction của container có thể kết thúc khi listener return, trong khi worker vẫn chạy.
- Database transaction ở thread listener không bao bọc lệnh SQL chạy trong worker.
- Offset có thể được commit trước khi worker hoàn tất.
- Worker có thể tiếp tục chạy sau rebalance hoặc shutdown.
- Retry có thể chạy lại cùng event trong khi task trước vẫn còn hoạt động.

Nếu cần transaction, hãy giữ thao tác trong transaction boundary phù hợp hoặc dùng durable handoff. Worker nên idempotent theo event ID và kiểm tra trạng thái job trước khi tạo side effect.

## 21. Shutdown, rebalance và cancellation

Khi ứng dụng shutdown hoặc consumer rebalance, task bất đồng bộ có thể vẫn đang chạy. Nếu task hoàn tất sau khi partition đã được giao cho consumer khác, acknowledgment cũ có thể không còn hợp lệ hoặc offset commit có thể thất bại.

Cần có chính sách:

- Ngừng nhận task mới khi container dừng.
- Chờ worker đang chạy trong grace period giới hạn.
- Hủy task chưa bắt đầu nếu có thể.
- Không ack nếu công việc chưa đạt durability contract.
- Đảm bảo redelivery có thể xảy ra và worker idempotent.
- Ghi nhận task đang chạy để recovery sau restart nếu công việc quan trọng.

Không giữ shutdown vô hạn để chờ downstream. Graceful shutdown phải có deadline; sau deadline, để record chưa xác nhận được giao lại theo cơ chế Kafka.

## 22. Đo lường và profiling listener

Theo dõi metric theo listener ID, topic và consumer group:

- Listener processing duration p50/p95/p99.
- Poll interval và số lần vượt max poll interval.
- Consumer lag theo partition.
- Records per poll và batch size.
- Số lần timeout, retry, recovery và DLT.
- HTTP latency, DB query latency và connection pool wait.
- Executor active threads, queue depth và rejected tasks.
- Pause duration, in-flight task count và async completion latency.

Khi cần tìm thread đang block, lấy thread dump và xem stack của consumer thread. Các frame như socket read, JDBC wait, `Future.get`, `LockSupport.park`, `Thread.sleep` hoặc monitor contention thường chỉ ra vị trí chờ.

Dùng tracing/correlation ID để nối thời gian listener với các lời gọi downstream. Đừng chỉ xem CPU usage; CPU thấp nhưng consumer lag cao thường là dấu hiệu đáng kiểm tra I/O wait hoặc pool exhaustion.

## 23. Kiểm thử listener không block và xử lý bất đồng bộ

Kiểm thử cần bao phủ cả thành công, timeout, queue đầy và lifecycle:

1. Downstream trả nhanh: listener hoàn tất và offset tiến đúng policy.
2. Downstream chậm: timeout xảy ra trong ngân sách đã định.
3. Downstream không phản hồi: consumer không bị giữ vô hạn.
4. Worker executor đầy: task bị reject và record đi theo error handling policy.
5. Async task thất bại: exception tới container/error handler, không bị nuốt.
6. Async task hoàn tất: offset chỉ được xác nhận sau completion hoặc durable handoff.
7. Process restart sau enqueue: xác nhận không mất task theo durability contract.
8. Rebalance trong khi task chạy: xác nhận task/ack được xử lý an toàn.
9. Nhiều record cùng key: ordering và idempotency đúng yêu cầu.
10. Queue đạt high watermark: container pause; khi xuống low watermark thì resume.
11. Concurrency tăng: downstream connection pool không vượt capacity.
12. Batch lớn: thời gian xử lý batch nằm trong poll budget.

Dùng Testcontainers hoặc Embedded Kafka để kiểm tra offset và redelivery; dùng mock server có khả năng điều khiển latency để mô phỏng downstream. Dùng latch/Awaitility với timeout thay vì sleep cố định. Test cần quan sát committed offset và output topic, không chỉ xác nhận method được gọi.

## 24. Các lỗi thường gặp

| Cách làm | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Gọi HTTP đồng bộ không timeout | Consumer thread có thể chờ vô hạn | Đặt connect/response timeout và deadline tổng |
| Dùng `Thread.sleep` để retry | Giữ consumer thread trong backoff | Dùng error handler/retry topic |
| Gọi `Future.get` trong listener | Biến async task thành blocking wait | Dùng async listener return support hoặc xử lý đồng bộ có timeout |
| Enqueue RAM rồi return | Offset có thể commit trước khi worker xử lý | Async ack đúng cách hoặc durable handoff |
| Dùng queue vô hạn | Heap tăng khi downstream chậm | Bounded queue và backpressure |
| Tăng concurrency không đo tải | Downstream/pool bị quá tải | Giới hạn concurrency theo partition và capacity |
| Tăng max.poll.interval để che lỗi | Rebalance chỉ bị trì hoãn | Giảm thời gian xử lý và đặt timeout |
| Chạy CPU-heavy trên consumer thread | Poll chậm dù không có I/O | Profile và dùng worker có giới hạn nếu ack semantics cho phép |
| Nuốt exception trong listener | Offset có thể được xác nhận dù nghiệp vụ lỗi | Ném exception hoặc xử lý recovery rõ ràng |
| Offload qua executor nhưng dùng transaction context cũ | Side effect và offset không còn cùng boundary | Durable handoff, idempotency và transaction phù hợp |

## 25. Checklist tránh block

Trước khi đưa listener vào production, hãy xác nhận:

1. Đã đo listener duration p95/p99 và thời gian xử lý batch.
2. Mọi HTTP/DB/Redis call đều có timeout.
3. Có deadline tổng cho một record.
4. Không có `Thread.sleep`, `Future.get` hoặc lock wait không giới hạn.
5. Retry nằm trong error handler/retry mechanism phù hợp.
6. `max.poll.records` và `max.poll.interval.ms` phù hợp ngân sách xử lý.
7. Listener concurrency không vượt capacity downstream.
8. Connection pool, worker pool và semaphore có giới hạn.
9. Executor có bounded queue và rejection policy.
10. Offload không commit offset trước completion hoặc durable handoff.
11. Async listener return type phù hợp Spring Kafka version.
12. Manual/async acknowledgment được kiểm thử theo đúng container configuration.
13. Ordering theo partition/key được giữ hoặc bảo vệ bằng sequence/version.
14. Side effect ngoài Kafka có idempotency và transaction boundary rõ ràng.
15. Pause/resume dùng high/low watermark và tính cả in-flight records.
16. Shutdown/rebalance có grace period, cancellation và redelivery policy.
17. Có metric poll interval, listener duration, queue depth, timeout và rejected task.
18. Có integration test cho timeout, async failure, restart và offset.

Tránh block trong listener bằng cách giới hạn thời gian mọi thao tác, kiểm soát concurrency và bảo vệ poll budget. Offload sang worker chỉ an toàn khi container biết lúc công việc hoàn tất hoặc record đã được chuyển giao bền vững; enqueue vào RAM rồi return có thể khiến offset tiến trước khi nghiệp vụ hoàn tất. Kết hợp timeout, bounded executor, acknowledgment đúng, idempotency và backpressure sẽ giúp consumer duy trì tiến độ mà không tạo backlog không kiểm soát.

