# Không restart loop khi broker tạm thời lỗi

Trong một hệ thống Spring Kafka, broker có thể tạm thời không truy cập được vì rolling restart, leader election, network interruption, DNS, TLS handshake, quá tải hoặc sự cố của một node. Nếu mỗi lần gặp lỗi ứng dụng đều dừng listener container, ném lỗi làm process thoát rồi để Kubernetes khởi động lại pod ngay lập tức, một sự cố ngắn có thể biến thành **restart loop** kéo dài.

Restart loop làm nhiều việc xấu xảy ra cùng lúc: consumer group liên tục rời và gia nhập, partition rebalance nhiều lần, producer tạo kết nối mới dồn dập, request bị retry đồng loạt, log và alert tăng mạnh, trong khi broker đang phục hồi lại phải chịu thêm tải. Khi broker hoạt động trở lại, các client có thể cùng reconnect và phát sinh một đợt traffic đột biến.

Nguyên tắc của bài học **Không restart loop khi broker tạm thời lỗi** là phân biệt lỗi kết nối có thể tự phục hồi với lỗi cấu hình hoặc lifecycle thật sự cần can thiệp. Kafka client đã có cơ chế reconnect/retry cho nhiều lỗi tạm thời. Spring Kafka container và ứng dụng cần để cơ chế đó có cơ hội hoạt động, dùng backoff có giới hạn cho những trường hợp phải restart, và xây dựng readiness/liveness phản ánh đúng trạng thái nghiệp vụ.

Bài thuộc chương **Health và readiness** của Spring Kafka Reliability Operations. Nội dung đi từ Kafka client retry, listener container lifecycle, producer/consumer behavior, Kubernetes probes, đến cách quan sát và kiểm thử khi broker tạm thời mất kết nối.

## 1. Restart loop hình thành như thế nào?

Giả sử broker đang rolling restart trong 30 giây. Mỗi pod consumer nhận lỗi kết nối. Ứng dụng có một health check coi broker không truy cập được là liveness failure, nên Kubernetes restart pod.

    Broker đang rolling restart
             |
             v
    Consumer nhận disconnect / request timeout
             |
             v
    Liveness probe trả DOWN
             |
             v
    Kubernetes kill và restart pod
             |
             v
    Consumer group member rời group
             |
             v
    Các member khác rebalance
             |
             v
    Pod mới khởi tạo producer/consumer
             |
             v
    Broker vẫn chưa sẵn sàng
             |
             +------> lặp lại từ đầu

Khi tất cả replicas cùng bị ảnh hưởng, chúng có thể restart gần như đồng thời. Broker vừa trở lại phải nhận nhiều kết nối mới, metadata requests, group joins, producer initialization và authentication cùng lúc. Đây là một dạng **thundering herd**.

Một lần disconnect không nhất thiết có nghĩa consumer đã chết. Kafka client có thể tiếp tục reconnect và khôi phục hoạt động mà không cần restart JVM hoặc container.

## 2. Phân biệt lỗi broker tạm thời với lỗi ứng dụng

Không phải mọi lỗi Kafka đều nên xử lý bằng cùng một chính sách.

| Tình huống | Ví dụ | Hành động ban đầu |
|---|---|---|
| Broker tạm thời không truy cập được | Node restart, leader election, network flap | Để Kafka client reconnect/retry |
| Request tạm thời thất bại | Timeout, coordinator chuyển leader | Retry theo client policy và deadline |
| Authentication/authorization lỗi | Secret sai, ACL thiếu | Sửa credential/ACL; dùng retry interval có kiểm soát nếu phù hợp |
| Producer bị fencing | Trùng transactional identity, producer cũ còn sống | Sửa identity/lifecycle; restart đơn thuần không đủ |
| Offset không hợp lệ | Retention đã xóa offset cần đọc, reset policy là none | Quyết định recovery theo dữ liệu |
| Listener xử lý lỗi nghiệp vụ | Validation, database exception | Dùng error handler/retry/DLT cho record |
| JVM hoặc process bị treo | Deadlock, OOM, thread starvation | Điều tra liveness và tài nguyên process |
| Cấu hình cluster sai | Bootstrap address sai, advertised listener không reachable | Sửa cấu hình/network |

Điểm quan trọng là xác định **lỗi nằm ở broker/network, Kafka client, listener container, business handler hay JVM**. Một HTTP health check gọi broker thất bại không đủ để kết luận toàn bộ process cần restart.

## 3. Kafka client đã có reconnect và retry

Kafka Java client quản lý kết nối broker và có cơ chế thử kết nối lại khi broker tạm thời mất liên lạc. Với nhiều lỗi network/leader/coordinator tạm thời, client tự refresh metadata, reconnect và thử request lại theo policy.

Các cấu hình liên quan gồm:

- `reconnect.backoff.ms`: thời gian backoff cơ sở giữa các lần reconnect.
- `reconnect.backoff.max.ms`: giới hạn trên của reconnect backoff.
- `retry.backoff.ms`: khoảng chờ giữa các lần retry một số request thất bại.
- `request.timeout.ms`: thời gian chờ phản hồi request.
- `delivery.timeout.ms`: giới hạn tổng thời gian producer cố hoàn tất một lần gửi.
- `metadata.max.age.ms`: chu kỳ làm mới metadata định kỳ khi không có sự kiện cần refresh sớm.

Kafka client có thể áp dụng tăng backoff và jitter theo implementation/version. Không nên tự giả định tất cả request đều retry giống nhau: retryability phụ thuộc loại request, exception, producer/consumer API và trạng thái group/transaction.

**Reconnect không giống restart process.** Reconnect tạo lại kết nối broker trong client hiện tại; restart process tạo lại toàn bộ Spring context, consumer, producer, thread pool và nhiều tài nguyên khác.

## 4. Chọn bootstrap servers đủ khả năng dự phòng

Cấu hình `bootstrap.servers` nên có nhiều broker endpoint có thể truy cập trong cluster, thay vì chỉ một node duy nhất:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-0.kafka.svc:9092
      - kafka-1.kafka.svc:9092
      - kafka-2.kafka.svc:9092
~~~

Client dùng các endpoint bootstrap để lấy metadata và sau đó kết nối tới broker phù hợp cho từng partition/request. Danh sách bootstrap nhiều broker giúp client có nhiều điểm bắt đầu nếu một endpoint tạm thời không sẵn sàng.

Tuy nhiên, bootstrap list không sửa được:

- DNS/service discovery sai cho toàn cluster.
- `advertised.listeners` trả về địa chỉ mà client không thể truy cập.
- Network policy chặn mọi broker.
- TLS/SASL credentials không hợp lệ.
- Cluster thực sự ngừng hoạt động.

Sau khi bootstrap, client phải kết nối được các broker address được quảng bá trong metadata. Nếu bootstrap address reachable nhưng advertised address không reachable, client vẫn có thể lỗi liên tục.

Không thêm các hostname giả chỉ để danh sách dài hơn. Mỗi endpoint phải thuộc cluster thật và đúng network/security context.

## 5. Cấu hình reconnect backoff

Ví dụ cấu hình consumer và producer trong Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-0:9092,kafka-1:9092,kafka-2:9092
    consumer:
      group-id: order-workers
      enable-auto-commit: false
      properties:
        reconnect.backoff.ms: 500
        reconnect.backoff.max.ms: 10000
        retry.backoff.ms: 500
        request.timeout.ms: 30000
        session.timeout.ms: 45000
        heartbeat.interval.ms: 15000
    producer:
      properties:
        reconnect.backoff.ms: 500
        reconnect.backoff.max.ms: 10000
        retry.backoff.ms: 500
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        acks: all
        enable.idempotence: true
~~~

Các giá trị trên chỉ là **điểm khởi đầu minh họa**, không phải cấu hình tối ưu cho mọi cluster. Chúng phải phù hợp với network RTT, broker capacity, SLA, timeout của ứng dụng và phiên bản Kafka client.

Lưu ý:

- `reconnect.backoff.ms` điều khiển reconnect attempts, không phải thời gian chờ cho toàn bộ business operation.
- `retry.backoff.ms` không thay thế `delivery.timeout.ms`.
- Producer có thể kết thúc một lần gửi bằng timeout sau khi hết delivery deadline dù client vẫn tiếp tục hoạt động và reconnect.
- `session.timeout.ms` và `heartbeat.interval.ms` ảnh hưởng group membership, không phải retry của producer.
- `enable.idempotence` giúp kiểm soát duplicate do một số producer retries trong phạm vi Kafka protocol, không deduplicate business command mới.

Đừng đặt backoff quá nhỏ cho toàn bộ replicas. Khi broker vừa phục hồi, hàng trăm consumer có thể cùng tạo kết nối/request với tần suất cao.

## 6. Exponential backoff và jitter

Khi ứng dụng thực sự cần tự retry một thao tác ngoài cơ chế Kafka client, exponential backoff giúp tăng khoảng chờ qua các lần thất bại.

Một công thức đơn giản:

    delay(n) = min(maxDelay, baseDelay * 2^n)

Ví dụ baseDelay = 1 giây, maxDelay = 30 giây:

| Attempt | Delay trước lần thử tiếp theo |
|---:|---:|
| 0 | 1 giây |
| 1 | 2 giây |
| 2 | 4 giây |
| 3 | 8 giây |
| 4 | 16 giây |
| 5 trở đi | Tối đa 30 giây |

Nếu mọi pod dùng cùng một lịch cố định, chúng vẫn có thể thử lại đồng thời. **Jitter** thêm độ ngẫu nhiên để phân tán các lần thử.

Một dạng full jitter:

    delay = random(0, min(maxDelay, baseDelay * 2^attempt))

Jitter giúp tránh nhiều instance cùng reconnect/restart đúng một thời điểm. Với retry phải có deadline hoặc giới hạn phù hợp; backoff không nên khiến một request nghiệp vụ chờ vô hạn.

Kafka client đã có reconnect backoff của riêng nó. Không nên bọc thêm một vòng retry bên ngoài cho từng poll/request mà không hiểu hai tầng sẽ cộng dồn ra sao.

## 7. Đừng restart container chỉ vì một disconnect

Một consumer có thể log disconnect hoặc request timeout nhưng vẫn còn sống và đang retry kết nối. Trong trường hợp này, việc gọi `stop()` rồi `start()` liên tục có thể phá vỡ chính quá trình phục hồi của client.

Một policy hợp lý:

1. Ghi nhận lỗi và thời điểm.
2. Kiểm tra container còn running không.
3. Quan sát client reconnect và request failures trong một cửa sổ thời gian.
4. Theo dõi consumer group assignment, lag và progress.
5. Chỉ can thiệp lifecycle nếu container đã dừng hoặc có lỗi terminal được xác định.
6. Nếu cần restart, dùng backoff/cooldown và giới hạn số lần restart.

Không lấy một dòng `Connection to node ... could not be established` làm điều kiện restart pod. Cần xác nhận lỗi kéo dài, ảnh hưởng tiến độ và không có cơ chế tự phục hồi phù hợp.

## 8. Broker outage không nhất thiết làm listener container dừng

Khi broker tạm thời mất kết nối, Kafka consumer có thể vẫn ở trong vòng poll và tiếp tục reconnect. Spring Kafka container có thể vẫn báo running trong khi record processing tạm thời không tiến triển.

Điều đó có nghĩa:

- `container.isRunning() == true` không chứng minh broker đang reachable.
- Một poll không nhận record không chứng minh group đã mất assignment.
- Một broker disconnect không nhất thiết tạo `ConsumerStoppedEvent`.
- Container có thể phục hồi mà không có start/stop event mới.
- Consumer lag có thể tăng trong thời gian broker hoặc leader unavailable.

Monitoring cần theo dõi đồng thời lifecycle, broker connectivity, group assignment, poll progress và lag. Không dùng một metric duy nhất để quyết định restart.

## 9. Khi nào Spring Kafka container có thể dừng?

Có những lỗi ở cấp consumer/lifecycle khiến container dừng thay vì chỉ reconnect. Ví dụ có thể bao gồm authentication/authorization exceptions theo policy, lỗi offset không thể phục hồi, producer fencing trong transactional listener hoặc lỗi terminal khác tùy phiên bản và cấu hình.

Khi container thực sự dừng, cần xem:

- ConsumerStoppedEvent và reason nếu event được phát.
- ContainerStoppedEvent/lifecycle state.
- Exception gốc trước thời điểm dừng.
- Listener container có auto-start/restart policy nào không.
- Có auth retry interval hay chưa.
- Broker/network đã phục hồi chưa.
- Restart có giải quyết nguyên nhân hay chỉ lặp lại cùng lỗi.

Đừng coi tất cả lỗi trong log Kafka client là lỗi làm container stop. Phân biệt lỗi request có thể retry bên trong client với exception khiến container lifecycle kết thúc.

## 10. AuthenticationException và authExceptionRetryInterval

Một trường hợp đặc biệt là broker tạm thời từ chối xác thực hoặc authorization. Nếu Spring Kafka container dừng khi gặp authentication/authorization exception, ứng dụng có thể cấu hình khoảng thời gian chờ trước khi thử lại bằng `authExceptionRetryInterval` ở những phiên bản hỗ trợ.

Ví dụ Java configuration:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
            .setAuthExceptionRetryInterval(Duration.ofSeconds(10));

    return factory;
}
~~~

Ví dụ này dùng API Spring Kafka có hỗ trợ setter tương ứng; kiểm tra Javadoc theo version dự án. Nếu giá trị không được cấu hình, một số phiên bản/container có thể dừng khi authentication/authorization exception xuất hiện thay vì tự thử lại theo interval.

Cần phân biệt:

- Broker tạm thời chưa sẵn sàng trả lời authentication request.
- Credential sai hoặc hết hạn.
- ACL thiếu quyền.
- Certificate/CA/TLS configuration sai.

Retry interval chỉ giúp thử lại sau một khoảng chờ. Nó không sửa password sai hoặc ACL bị từ chối vĩnh viễn. Với lỗi cấu hình, cần alert và sửa secret/permission; không retry nhanh vô hạn.

## 11. Listener error handler không phải broker reconnect policy

Spring Kafka có `DefaultErrorHandler`, `DeadLetterPublishingRecoverer` và các cơ chế retry/recovery để xử lý **record listener thất bại**.

Ví dụ:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );
}
~~~

Cấu hình trên minh họa retry hữu hạn cho một số lỗi xử lý record. Nó không phải cách cấu hình reconnect khi broker ngừng nhận kết nối.

Phân biệt:

| Lỗi | Cơ chế phù hợp |
|---|---|
| JSON/schema/business validation của một record | Error handler, retry có giới hạn, DLT |
| Database timeout trong listener | Retry có kiểm soát, idempotency, circuit breaker phù hợp |
| Broker disconnect / leader unavailable | Kafka client reconnect/retry |
| Consumer group rebalance | Kafka group protocol và rebalance handling |
| Authentication/authorization | Credential/ACL repair và auth retry interval nếu phù hợp |
| Process deadlock/OOM | Liveness/process recovery và sửa nguyên nhân |

Nếu dùng error handler để ném lỗi ra ngoài nhằm làm pod restart mỗi lần broker tạm thời lỗi, có thể biến lỗi hạ tầng thành restart loop.

## 12. Producer send retry và delivery timeout

Producer có thể retry một số lỗi tạm thời. Một số thuộc tính quan trọng:

- `retries`: số lần retry trong những phiên bản/configuration còn dùng giới hạn này; client hiện đại thường quản lý retry cùng delivery timeout.
- `request.timeout.ms`: thời gian chờ response cho một request.
- `delivery.timeout.ms`: tổng thời gian tối đa producer cố gắng hoàn tất gửi record.
- `retry.backoff.ms`: khoảng nghỉ giữa các lần retry request.
- `acks`: mức xác nhận broker.
- `enable.idempotence`: hỗ trợ tránh duplicate do retry ở protocol producer.

Trong các Kafka client hiện đại, producer retries và delivery timeout phối hợp với nhau; cần xem tài liệu đúng version. Một lần send có thể kết thúc bằng exception khi delivery deadline hết, nhưng điều đó không đồng nghĩa phải restart producer hoặc JVM.

Với Spring Kafka, `KafkaTemplate.send()` trả future. Ứng dụng cần quan sát future completion và xử lý failure theo hợp đồng API. Không gọi send rồi bỏ qua future, sau đó log success như thể broker đã nhận record.

## 13. KafkaTemplate và lỗi gửi trong thời gian broker outage

Ví dụ:

~~~java
public void publish(OrderCreated event) {

    CompletableFuture<SendResult<String, OrderCreated>> future =
            kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
            );

    future.whenComplete((result, error) -> {
        if (error != null) {
            log.error(
                "Kafka publish failed: eventId={}",
                event.eventId(),
                error
            );
        }
        else {
            RecordMetadata metadata = result.getRecordMetadata();

            log.info(
                "Kafka publish acknowledged: eventId={}, topic={}, partition={}, offset={}",
                event.eventId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        }
    });
}
~~~

Đây là ví dụ Spring Kafka 3.x dùng `CompletableFuture`; kiểu trả về khác ở các phiên bản cũ. Callback có thể chạy trên thread khác, nên cần context propagation nếu log phụ thuộc MDC/tracing.

Khi broker outage kéo dài, future có thể chỉ hoàn tất sau khi producer retries hoặc delivery timeout kết thúc. Nếu ứng dụng nhận request HTTP, phải quyết định rõ API chờ tới kết quả, trả trạng thái pending qua outbox hay trả lỗi có thể retry.

Không giữ request thread chờ vô hạn. Hãy có deadline tổng cho request và một cơ chế bền vững nếu nghiệp vụ cần tiếp tục sau khi HTTP connection kết thúc.

## 14. Transactional producer trong thời gian broker lỗi

Kafka transaction cần transaction coordinator và các broker liên quan. Khi broker/coordinator tạm thời không khả dụng, transaction có thể gặp timeout hoặc abort.

Nguyên tắc:

- Không tạo producer mới cho mỗi exception timeout.
- Không tự động đổi `transactional.id` để né lỗi coordinator.
- Không restart container liên tục khi client đang có khả năng reconnect.
- Giữ event ID ổn định để xử lý uncertain outcome.
- Theo dõi transaction commit/abort/fencing riêng.
- Phân biệt timeout tạm thời với `ProducerFencedException`.

Fencing thường liên quan transactional identity/producer epoch, không phải một disconnect bình thường. Restart liên tục với cùng identity đang bị xung đột có thể lặp lại fencing.

Nếu Kafka transaction abort, output transactional chưa được coi là committed bởi consumer `read_committed`. Nếu ứng dụng đã thực hiện side effect database/API bên ngoài Kafka, side effect đó không tự rollback; cần idempotency/reconciliation.

## 15. Consumer behavior khi broker tạm thời không truy cập được

Consumer thường cần broker để fetch, commit offsets và tham gia group coordination. Khi kết nối gián đoạn:

- Fetch requests có thể thất bại hoặc chờ retry.
- Metadata có thể được refresh.
- Heartbeat/coordinator requests có thể bị ảnh hưởng.
- Group có thể rebalance nếu membership không được duy trì.
- Consumer lag tăng khi producer tiếp tục ghi nhưng consumer không đọc được.
- Sau khi kết nối trở lại, consumer có thể tiếp tục từ vị trí/committed offset theo trạng thái thực tế.

Không tự reset offset để “đánh thức” consumer. Nếu commit offset chưa thành công, record đã xử lý có thể được giao lại. Đây là một lý do phải có idempotent side effect.

Với consumer group, thời gian broker outage kéo dài hơn timeout membership có thể khiến assignment thay đổi. Điều đó không có nghĩa phải restart mọi member; sau khi cluster ổn định, group protocol có thể hoàn tất rebalance.

## 16. session.timeout.ms và max.poll.interval.ms là hai vấn đề khác nhau

Hai timeout này thường bị nhầm:

- `session.timeout.ms`: giới hạn thời gian broker chờ heartbeat hợp lệ trước khi coi member đã mất, theo group protocol.
- `max.poll.interval.ms`: giới hạn thời gian giữa các lần poll theo điều kiện consumer group, đặc biệt khi ứng dụng xử lý record lâu.

Một listener xử lý quá lâu có thể vượt max.poll.interval.ms dù broker vẫn reachable. Một network outage có thể làm heartbeat không tới broker và ảnh hưởng session timeout.

Không tăng cả hai giá trị lên rất lớn chỉ để tránh restart/rebalance. Việc đó có thể kéo dài thời gian phát hiện consumer chết thật.

Hãy đo listener processing time, poll cadence, heartbeat errors và broker availability để chọn timeout có headroom hợp lý.

## 17. max.poll.records và thời gian xử lý một poll

Nếu mỗi poll trả về quá nhiều record, listener có thể mất lâu mới xử lý xong batch và quay lại poll. Trong thời gian broker/network có sự cố, điều này có thể cộng thêm với thời gian xử lý và gây membership instability.

Ước lượng:

    PollWorkTime
      ~= RecordsPerPoll * AverageProcessingTime
         + RetryTime
         + SynchronousCommitWait

Ví dụ:

    max.poll.records = 200
    processing p95 = 100 ms/record

    Work time gần đúng = 20 giây
      (chưa tính retry, commit và scheduling)

Đặt `max.poll.records` theo thời gian xử lý thực tế và `max.poll.interval.ms`. Giảm batch size có thể giúp consumer quay lại poll sớm hơn nhưng cũng tăng overhead.

Broker outage không phải lý do duy nhất để điều chỉnh poll size; cần đánh giá workload bình thường và worst-case.

## 18. Spring Kafka container có cần restart sau reconnect không?

Trong nhiều trường hợp, không cần. Nếu Kafka client vẫn hoạt động, container vẫn running và client tự reconnect, listener sẽ tiếp tục nhận record khi broker/leader/coordinator sẵn sàng.

Chỉ cân nhắc restart container khi có bằng chứng lifecycle đã dừng hoặc client/container ở trạng thái không thể tự phục hồi theo contract của version đang dùng.

Trước khi restart, xác nhận:

1. `KafkaListenerEndpointRegistry` có container đúng ID không?
2. `isRunning()` phản ánh trạng thái gì?
3. ConsumerStoppedEvent có được phát không và reason là gì?
4. Có exception terminal hay chỉ network disconnect?
5. Broker đã thực sự phục hồi chưa?
6. Credential/ACL/transactional ID có vấn đề không?
7. Restart có ảnh hưởng các child consumers khác trong concurrent container không?
8. Có restart cooldown và giới hạn attempts không?

Không restart một container đang chạy khỏe chỉ vì metric broker request failure vừa tăng. Theo dõi thêm thời gian và progress.

## 19. Readiness và liveness không nên phụ thuộc giống nhau

Kubernetes thường có hai loại probe:

**Liveness** trả lời process có cần được restart vì không còn tiến triển ở mức ứng dụng hay không.

**Readiness** trả lời pod có nên nhận thêm traffic từ service hay không.

Broker tạm thời unavailable thường không phải lý do đủ để fail liveness. Restart JVM không làm broker hoạt động lại; nó có thể chỉ làm mất kết nối đang được client retry và tạo rebalance.

Readiness có thể phản ánh broker dependency nếu nghiệp vụ của service thực sự cần Kafka để nhận traffic an toàn. Nhưng policy cần theo contract:

- API có thể ghi durable outbox khi Kafka down: có thể vẫn ready nếu database và outbox còn đủ capacity.
- API chỉ hoàn tất request khi Kafka publish thành công: có thể trả lỗi có kiểm soát hoặc fail readiness theo SLO.
- Consumer-only worker: readiness có thể degraded khi group không xử lý được workload quá ngưỡng, nhưng cần grace period và không restart loop.
- Service có nhiều consumer groups: một group phụ bị lỗi không nhất thiết làm toàn API service NotReady.

Không có một policy chung cho mọi ứng dụng.

## 20. Ví dụ liveness probe không phụ thuộc broker

Một liveness endpoint nên phản ánh process và các thành phần nội bộ thiết yếu, tránh gọi Kafka broker đồng bộ trong mỗi lần probe.

Ví dụ cấu hình Kubernetes minh họa:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  initialDelaySeconds: 20
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Trong Spring Boot, cấu hình health groups:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Khi dùng Spring Boot Actuator probe groups, liveness/readiness endpoint phản ánh health indicators được đưa vào từng group theo cấu hình. Không thêm Kafka indicator vào liveness một cách mặc định.

Nếu broker tạm thời lỗi, liveness vẫn có thể UP để process giữ nguyên Kafka client và reconnect. Readiness được quyết định theo khả năng phục vụ nghiệp vụ và SLO.

## 21. Khi nào readiness nên DOWN vì Kafka?

Đặt readiness DOWN có thể hợp lý nếu pod nhận request mới mà không thể thực hiện hợp đồng đã cam kết và không có cơ chế lưu bền vững thay thế.

Ví dụ:

- API nhận lệnh và phải publish Kafka trước khi trả thành công.
- Không có outbox/database queue để giữ lệnh khi Kafka down.
- Trả success trong tình huống đó sẽ làm mất ý định nghiệp vụ.

Trong trường hợp khác:

- API ghi command vào database/outbox trước.
- Publisher background gửi event khi Kafka trở lại.
- Request có thể được xác nhận theo hợp đồng “accepted/pending”.

Khi đó service vẫn có thể ready nếu outbox capacity, database và SLA đáp ứng. Kafka outage được biểu diễn bằng backlog/alert, không nhất thiết loại pod khỏi service endpoints.

Với consumer worker, readiness cần đánh giá group-level processing. Một pod không có partition hợp lệ vì dư consumer không nên tự động DOWN.

## 22. Không gọi broker đồng bộ trong mỗi readiness probe

Một custom HealthIndicator có thể gọi AdminClient hoặc KafkaTemplate để kiểm tra broker. Nếu mỗi lần probe tạo request mạng có timeout dài, sự cố broker có thể làm health endpoint chậm và kéo theo probe failure.

Một số rủi ro:

- Probe bị timeout do request Kafka chờ.
- Mỗi pod liên tục tạo thêm request khi broker quá tải.
- Readiness thay đổi liên tục theo một lỗi ngắn.
- Health endpoint chiếm thread pool trong outage.
- Probe và recovery cùng tạo thundering herd.

Một thiết kế an toàn hơn:

1. Có một monitor định kỳ với timeout ngắn, có giới hạn.
2. Lưu snapshot trạng thái broker/connectivity và thời điểm kiểm tra gần nhất.
3. Health endpoint chỉ đọc snapshot trong bộ nhớ.
4. Đánh giá trạng thái theo ngưỡng và hysteresis.
5. Nếu snapshot quá cũ, trả UNKNOWN/DEGRADED theo policy.
6. Không tạo KafkaAdminClient mới cho mỗi probe.

Probe phải nhanh, deterministic và không trở thành nguồn tải bổ sung cho broker đang lỗi.

## 23. Grace period và hysteresis cho readiness

Một lần kiểm tra broker thất bại có thể chỉ là transient. Nếu readiness đổi UP/DOWN theo từng request, endpoint sẽ dao động.

Có thể dùng hai ngưỡng:

    Broker check success liên tục
      -> đánh dấu recovered sau điều kiện ổn định

    Broker check failure liên tục trong thời gian T
      -> đánh dấu unavailable

Ví dụ:

| Tín hiệu | Policy minh họa |
|---|---|
| Một lần request timeout | Ghi metric, giữ trạng thái trước |
| 3 lần thất bại liên tiếp trong 15 giây | Đánh dấu degraded |
| 2 phút không phục hồi | Alert cấp cao |
| 5 lần kiểm tra thành công liên tiếp | Đánh dấu recovered |
| Container không running | Health riêng theo lifecycle |

Đây là policy ví dụ; chọn ngưỡng theo SLO, traffic và timeout. Hysteresis giúp tránh flapping nhưng không được che giấu outage kéo dài.

Nếu health state là group-level, cần phân biệt lỗi của một member với lỗi toàn group. Có thể lấy group metrics từ monitor bên ngoài thay vì để từng pod tự suy luận toàn cục.

## 24. Startup khi broker chưa sẵn sàng

Một ứng dụng có thể cần khởi động HTTP server và health endpoints trước khi Kafka cluster sẵn sàng. Nếu startup path buộc phải gọi broker và fail-fast, ứng dụng có thể không lên được dù Kafka client vốn có khả năng reconnect sau đó.

Kiểm tra:

- Custom `@PostConstruct` có gọi AdminClient hoặc KafkaTemplate không?
- Startup runner có chờ topic metadata vô hạn không?
- Topic provisioning có được thực hiện đồng bộ không?
- KafkaAdmin có cấu hình fatal khi broker unavailable không?
- Listener container có auto-start ngay khi context refresh không?
- Startup readiness có grace period không?

Nếu nghiệp vụ cho phép, tách khởi động process khỏi việc broker sẵn sàng. Container có thể start và client tự reconnect; readiness phản ánh khả năng phục vụ thật sự.

Nếu bắt buộc topic/ACL/schema phải được xác minh trước khi nhận traffic, dùng startup/readiness gate có timeout rõ và thông báo nguyên nhân. Không lặp restart process chỉ để thử lại một startup check không có backoff.

## 25. Listener container autoStartup và lifecycle

Spring Kafka listener containers được quản lý bởi Spring lifecycle và thường auto-start theo cấu hình. Có thể đặt `autoStartup=false` để ứng dụng chủ động start sau khi một điều kiện nội bộ được thỏa mãn, nhưng không nên dùng nó để tạo một vòng polling broker check liên tục.

Ví dụ:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "order-workers",
    autoStartup = "false"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Sau đó có thể điều khiển container qua `KafkaListenerEndpointRegistry`:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && !container.isRunning()) {
    container.start();
}
~~~

Đây là ví dụ điều khiển lifecycle, không phải supervisor hoàn chỉnh. Cần đảm bảo start không được gọi liên tục từ nhiều thread, có backoff và trạng thái rõ. Nếu broker chỉ tạm thời disconnect nhưng container đang running, không cần gọi start.

Với concurrent container, `start()`/ `stop()` trên parent có thể ảnh hưởng tất cả child consumers. Nếu chỉ một child có vấn đề, phải hiểu API và ownership trước khi thao tác.

## 26. Supervisor restart có backoff

Nếu một container đã thực sự stopped vì lỗi có thể phục hồi, supervisor có thể thử start lại sau một khoảng chờ. Cần quản lý:

- Số lần restart trong cửa sổ thời gian.
- Exponential backoff và jitter.
- Cooldown sau khi start thành công.
- Trạng thái đang restart để tránh nhiều trigger cùng lúc.
- Phân loại lỗi terminal/non-terminal.
- Không restart khi pod đang shutdown.
- Không restart liên tục nếu credentials/ACL/transactional identity chưa được sửa.

Mô hình:

    ContainerStoppedEvent / lifecycle state
                |
                v
        Recovery supervisor
                |
                v
       Phân loại nguyên nhân
          /             \
      transient       configuration
         |                  |
         v                  v
    backoff + retry     alert + wait for fix
         |
         v
     container.start()
         |
         v
    quan sát started + assignment + progress

Không restart chỉ vì ConsumerStoppedEvent.NORMAL trong lúc rolling deployment hoặc application shutdown. Không coi mọi ERROR đều retryable.

## 27. Ví dụ state machine cho restart policy

Một supervisor nên có state rõ ràng:

| State | Ý nghĩa | Chuyển trạng thái |
|---|---|---|
| RUNNING | Container đang hoạt động | Stop/error → STOPPED |
| STOPPED | Container đã dừng | Nếu transient và không shutdown → BACKOFF |
| BACKOFF | Đang chờ lần thử tiếp theo | Hết delay → STARTING |
| STARTING | Đã yêu cầu start | Started → RUNNING; fail → BACKOFF |
| CIRCUIT_OPEN | Vượt giới hạn restart | Chờ cooldown/operator |
| SHUTTING_DOWN | Ứng dụng đang đóng | Không restart |

Các quy tắc:

- Chỉ một restart attempt đang chạy cho một listener.
- Một event trùng lặp không tạo thêm restart.
- Số lần restart có giới hạn.
- Backoff có jitter.
- Khi container chạy ổn định đủ lâu, reset failure count.
- Nếu lỗi AUTH/FENCED/NO_OFFSET có tính cấu hình/data, không restart nhanh vô hạn.
- Khi process shutdown, hủy pending restart tasks.

State machine này có thể được triển khai bằng scheduler, lock/atomic state hoặc một supervisor service phù hợp. Không cần tự viết một hệ thống restart phức tạp nếu Kubernetes hoặc framework đã quản lý lifecycle đầy đủ.

## 28. Producer outage và transactional outbox

Nếu API nhận lệnh nghiệp vụ và cần publish event nhưng Kafka có thể tạm thời unavailable, **transactional outbox** là một lựa chọn để không buộc request phụ thuộc vào broker availability.

Luồng:

    HTTP command
        |
        v
    Database transaction
      +-- update business state
      +-- insert outbox row
        |
        v
    Commit database
        |
        v
    API trả accepted
        |
        v
    Outbox publisher
        |
        +--> Kafka available: publish, mark sent
        |
        +--> Kafka unavailable: giữ row, retry sau

Outbox giữ ý định publish bền vững khi Kafka tạm thời down. Publisher có thể retry sau khi broker trở lại mà không yêu cầu restart toàn bộ API pod.

Trade-off:

- Event delivery thường at-least-once; downstream cần idempotency theo eventId.
- Outbox backlog tăng trong outage.
- Cần metric oldest outbox age và pending count.
- Cần giới hạn retry/backoff và xử lý poison event.
- Database capacity phải đủ cho thời gian outage dự kiến.

Outbox không phải yêu cầu cho mọi producer. Nếu request contract yêu cầu Kafka ACK đồng bộ, API phải trả kết quả đúng với việc publish; nhưng vẫn không nên restart JVM khi send future thất bại do broker tạm thời.

## 29. Consumer offset khi broker phục hồi

Trong thời gian broker unavailable, consumer có thể không commit offset. Khi kết nối trở lại:

- Consumer có thể tiếp tục poll theo vị trí hiện tại nếu assignment vẫn hợp lệ.
- Nếu group membership đã thay đổi, rebalance sẽ quyết định assignment mới.
- Record chưa được commit có thể được giao lại.
- Side effect đã hoàn tất trước outage nhưng offset chưa commit có thể chạy lần nữa.

Ví dụ:

    Committed offset = 500
    Consumer xử lý record 500, 501
    Broker mất kết nối trước offset commit
    Consumer reconnect hoặc group rebalance
    Consumer mới đọc từ offset 500

Đây là lý do cần:

- Event ID ổn định.
- Database unique constraint/inbox.
- Side effect idempotent.
- Không commit offset trước khi xử lý bền vững.
- Theo dõi duplicate detection sau outage.

Không tự seek về latest để bỏ qua backlog khi broker phục hồi. Việc đó có thể biến một outage tạm thời thành mất dữ liệu vĩnh viễn.

## 30. Kafka transactions khi broker outage

Với transactional listener hoặc producer-initiated Kafka transaction, broker outage có thể làm send/commit timeout hoặc abort.

Cần phân biệt:

- Producer reconnect đang diễn ra.
- Transaction timeout.
- Transaction coordinator unavailable.
- Producer bị fencing.
- Commit outcome không chắc chắn do response bị mất.

Một transaction đã abort không làm output xuất hiện với consumer `read_committed`. Input offset trong transaction bị abort cũng không được commit như thành công.

Không tạo transactional.id mới mỗi lần retry để né timeout. Việc đó có thể phá vỡ producer identity/fencing model. Khi có `ProducerFencedException`, điều tra identity conflict; khi có timeout tạm thời, xem retry/transaction outcome và giữ eventId ổn định.

Nếu transaction commit timeout và outcome chưa rõ, không tự kết luận chắc chắn transaction chưa commit. Dùng reconciliation/idempotency thay vì phát lại command với event ID mới.

## 31. Graceful shutdown giúp tránh thêm rebalance

Khi deployment hoặc scale down là chủ đích, cho listener container thời gian dừng có kiểm soát giúp consumer rời group rõ ràng và giảm rủi ro xử lý dở dang.

Một số điểm:

- Spring context shutdown phải có thời gian đủ cho listener containers.
- Kubernetes `terminationGracePeriodSeconds` cần lớn hơn khoảng dừng dự kiến.
- `preStop` hook nếu có phải phù hợp với deployment lifecycle.
- Listener không nên block vô hạn trên DB/API.
- Không commit offset cho record chưa xử lý xong.
- Dùng idempotency vì crash vẫn có thể xảy ra.
- Producer/transaction cần được đóng đúng lifecycle.

Ví dụ Kubernetes:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
~~~

Giá trị 60 giây chỉ là ví dụ. Đặt theo worst-case shutdown, listener processing deadline, transaction timeout và yêu cầu deployment. Graceful shutdown không giải quyết broker outage, nhưng tránh biến outage thành hàng loạt member rời group do restart liên tục.

## 32. Circuit breaker có vai trò gì?

Circuit breaker có thể hữu ích cho **dependency nghiệp vụ** mà listener gọi, ví dụ HTTP API hoặc database, khi downstream liên tục timeout. Nó không nên thay thế Kafka client reconnect.

Ví dụ:

    Consumer poll vẫn hoạt động
          |
          v
    Listener gọi Payment API
          |
          v
    Circuit breaker OPEN
          |
          +--> pause container/partition theo policy
          |
          +--> hoặc retry record có backoff hữu hạn
          |
          v
    Health probe độc lập kiểm tra Payment API
          |
          v
    HALF_OPEN -> CLOSED khi phục hồi

Nếu broker unavailable, circuit breaker bao quanh một health check broker có thể giúp giới hạn số probe, nhưng không nên tạo một vòng restart container mỗi lần breaker OPEN.

Đảm bảo recovery probe không phụ thuộc vào listener đang bị pause. Khi resume, vẫn giữ rate limit/backoff để tránh xả backlog thành một burst lớn.

## 33. Không nhân retry ở mọi tầng

Một hệ thống có thể vô tình xếp chồng retry:

    HTTP client retry: 3 lần
      x service retry: 3 lần
      x Kafka producer retry: nhiều lần trong delivery timeout
      x listener retry: 4 lần
      x Kubernetes restart: không giới hạn

Kết quả là một thao tác nghiệp vụ có thể được thử rất nhiều lần, trong khi các tầng không chia sẻ deadline hoặc idempotency key.

Nên xác định:

- Tầng nào chịu trách nhiệm retry transport?
- Tầng nào chịu trách nhiệm retry record?
- Tầng nào restart container/process?
- Deadline tổng là bao lâu?
- Có backoff/jitter ở đâu?
- Retry nào được tính là cùng event/command?
- Khi hết retry, recovery/DLT/outbox xử lý thế nào?

Kafka client tự retry transport trong giới hạn cấu hình. DefaultErrorHandler xử lý record failure. Kubernetes restart process khi container/process không khỏe theo liveness. Ba trách nhiệm này không nên bị nhập làm một.

## 34. Phân biệt broker outage với DNS và advertised.listeners

Khi log báo broker không reachable, nguyên nhân có thể không phải broker process chết.

Kiểm tra:

- DNS có resolve đúng hostname không?
- Service discovery có trả endpoint đúng không?
- Network policy/security group có chặn port không?
- Broker `advertised.listeners` có hostname/IP mà pod truy cập được không?
- TLS certificate có SAN khớp hostname không?
- SASL mechanism/credentials có đúng không?
- Client có dùng đúng bootstrap cluster/environment không?

Một tình huống thường gặp:

    Client kết nối bootstrap broker thành công
          |
          v
    Nhận metadata
          |
          v
    Metadata quảng bá broker.internal.local
          |
          v
    Pod không resolve được hostname đó
          |
          v
    Requests tới leader/coordinator thất bại

Thêm retry hoặc restart không sửa được advertised listener sai. Cần sửa cluster/network configuration.

## 35. Readiness khi consumer group vẫn đang rebalance

Sau một broker outage hoặc network interruption, consumer group có thể cần thời gian để trở lại Stable. Trong thời gian đó, một số member có thể chưa có assignment hoặc assignment đang thay đổi.

Readiness không nên fail ngay ở lần snapshot đầu tiên.

Có thể sử dụng:

- Startup grace period.
- Thời gian group phải Stable trước khi đánh giá.
- Assignment count theo toàn group.
- Số member khỏe mạnh.
- Lag/oldest record age.
- Thời gian kể từ commit/processing progress cuối.
- Pause state và listener lifecycle.

Một pod không có partition có thể là member dư hợp lệ. Nếu toàn group không có partition trong khi topic có dữ liệu và workload cần xử lý, đó mới là dấu hiệu nghiêm trọng.

Không gọi `consumer.assignment()` từ health thread. Dùng snapshot được cập nhật trên rebalance callbacks hoặc AdminClient monitor có giới hạn.

## 36. Monitoring cần có trong broker outage

Dashboard nên kết hợp bốn lớp.

**Broker và network**

- Broker availability/health.
- Client connection/disconnect count.
- Request latency/error rate.
- Metadata refresh errors.
- Authentication/authorization errors.
- DNS/network/TLS failures.

**Consumer group**

- Group member count.
- Assigned partitions.
- Rebalance count/duration.
- Heartbeat failures.
- Consumer lag và oldest record age.
- Commit rate, latency và failures.

**Producer**

- Send rate/error rate.
- Record retry rate.
- Delivery timeout count.
- Buffer availability/wait time.
- Transaction commit/abort/fencing.
- Outbox pending count/oldest age nếu có.

**Application và Kubernetes**

- Container running/stopped events.
- ConsumerStarted/Stopped events.
- Pod restart count.
- Liveness/readiness state.
- JVM GC pause, CPU throttling, memory.
- Restart supervisor attempts/backoff state.

Không chỉ theo dõi log error count. Trong outage, log volume có thể rất lớn; metric cho biết xu hướng và phạm vi ảnh hưởng tốt hơn.

## 37. Alerting không tạo thêm restart storm

Alert nên phân biệt lỗi ngắn với outage kéo dài:

| Điều kiện | Hành động |
|---|---|
| Một broker disconnect ngắn | Log/metric, không paging |
| Nhiều reconnect nhưng consumer vẫn phục hồi | Warning nếu kéo dài |
| Group lag tăng liên tục vượt SLO | Alert theo freshness/lag |
| Toàn group không có assignment | Critical nếu topic/workload phải hoạt động |
| Container dừng bất thường và không tự start | Alert lifecycle |
| AUTH/FENCED/NO_OFFSET lặp lại | Alert theo nguyên nhân cụ thể |
| Pod restart count tăng | Alert restart loop |
| Broker phục hồi nhưng reconnect rate tăng đột biến | Cảnh báo thundering herd |

Dùng duration, rate và nhiều tín hiệu để quyết định mức độ. Không paging mỗi lần Kafka client thử reconnect.

Alert không nên tự động kích hoạt restart cho mọi disconnect. Nếu có auto-remediation, phải giới hạn attempts và có circuit breaker.

## 38. Một health snapshot không blocking

Một custom monitor có thể cập nhật trạng thái kết nối gần nhất ở background, còn health endpoint chỉ đọc snapshot.

Ví dụ mô hình đơn giản:

~~~java
public record BrokerStatus(
        boolean reachable,
        Instant checkedAt,
        String lastError) {
}

@Component
public class BrokerStatusSnapshot {

    private final AtomicReference<BrokerStatus> current =
            new AtomicReference<>(
                new BrokerStatus(false, Instant.EPOCH, "Not checked")
            );

    public void update(BrokerStatus status) {
        current.set(status);
    }

    public BrokerStatus current() {
        return current.get();
    }
}
~~~

Một monitor riêng thực hiện probe có timeout, giới hạn tần suất và cập nhật snapshot. HealthIndicator không gọi broker trực tiếp:

~~~java
@Component
public class KafkaReadinessIndicator implements HealthIndicator {

    private final BrokerStatusSnapshot snapshot;

    public KafkaReadinessIndicator(BrokerStatusSnapshot snapshot) {
        this.snapshot = snapshot;
    }

    @Override
    public Health health() {
        BrokerStatus status = snapshot.current();

        if (!status.reachable()) {
            return Health.outOfService()
                    .withDetail("brokerReachable", false)
                    .withDetail("checkedAt", status.checkedAt())
                    .build();
        }

        return Health.up()
                .withDetail("brokerReachable", true)
                .withDetail("checkedAt", status.checkedAt())
                .build();
    }
}
~~~

Đây là ví dụ cấu trúc, chưa có grace period/hysteresis và chưa phân biệt group-level readiness. `reachable` phải được cập nhật bởi monitor có deadline rõ; không tạo KafkaAdminClient mới trong mỗi lần `health()`.

Trong production, trạng thái quá cũ nên được xử lý riêng. Một snapshot báo reachable từ 10 phút trước không chứng minh broker hiện vẫn khỏe.

## 39. Vì sao health probe không nên gọi KafkaTemplate.send?

Một cách kiểm tra broker là gửi record test trong mỗi readiness request. Cách này có thể gây side effect và tạo thêm traffic.

Rủi ro:

- Probe có thể publish record test vào topic thật.
- Record có thể bị consumer nghiệp vụ xử lý.
- Transactional producer có thể tạo thêm transaction.
- Mỗi pod và mỗi probe period tạo request mới.
- Probe failure có thể bị nhầm với business send failure.
- Topic/ACL có thể khác với quyền thực tế của consumer.

Nếu cần kiểm tra producer path, dùng synthetic canary riêng có key/topic/consumer và retention phù hợp, với tần suất thấp. Đừng gửi record kiểm tra trong mỗi lần Kubernetes probe.

Readiness nên đọc health snapshot hoặc dependency state đã được đo, không thực hiện một business publish mới.

## 40. Broker phục hồi: tránh burst khi consumer resume

Khi broker trở lại, consumer có thể thấy backlog lớn. Nếu tất cả consumers resume và xử lý tối đa ngay lập tức, downstream database/API có thể bị quá tải.

Cần cân nhắc:

- Giữ rate limiter/concurrency limit.
- Scale consumer theo partition count và dependency capacity.
- Resume theo nhóm hoặc theo thời gian có jitter nếu ứng dụng chủ động pause.
- Theo dõi oldest record age và drain rate.
- Không tăng concurrency vượt partition count.
- Không tăng producer retry vô hạn.
- Kiểm soát retry topic/DLT re-drive.
- Đảm bảo database connection pool và HTTP quotas đủ năng lực.

Backlog drain time gần đúng:

    DrainRate = ConsumerCapacity - IncomingRate

    DrainTime = CurrentLag / DrainRate

Ví dụ:

    Lag = 360.000 records
    Capacity = 800 records/s
    Incoming = 500 records/s
    DrainRate = 300 records/s

    DrainTime ~= 1.200 giây = 20 phút

Nếu capacity nhỏ hơn incoming rate, backlog không thể giảm. Khi đó cần giảm input hoặc tăng năng lực dependency/consumer phù hợp.

## 41. Không tự động scale theo lag mà bỏ qua dependency

Autoscaling theo consumer lag có thể hữu ích, nhưng khi broker vừa phục hồi hoặc downstream đang chậm, tăng pod ngay có thể làm tăng số kết nối, consumer group churn và request tới dependency.

Trước khi scale, xem:

- Số partition và mức song song tối đa.
- CPU/memory của consumer.
- Listener processing duration.
- Database/API capacity.
- Rate limiter state.
- Rebalance overhead.
- Lag trend và input rate.
- Số consumer member hiện có.

Nếu bottleneck là database connection pool, tăng consumer pods có thể làm database quá tải hơn. Nếu bottleneck là partition count, tăng pod vượt partition không tăng throughput.

## 42. Xử lý credential rotation khi broker tạm thời từ chối

Một đợt secret rotation có thể khiến consumer cũ dùng credential hết hạn trong khi secret mới chưa được mount hoặc refresh đúng.

Quy trình:

1. Xác định AUTH error khác với network disconnect.
2. Kiểm tra thời điểm secret rotation và version credential.
3. Xác nhận pod đang dùng secret mới.
4. Kiểm tra ACL của principal mới.
5. Nếu container dừng vì authentication exception, dùng auth retry interval phù hợp hoặc restart có kiểm soát sau khi credential đã cập nhật.
6. Tránh restart tất cả pods liên tục khi secret vẫn sai.
7. Xác nhận group join, assignment và offset progress sau phục hồi.

Retry interval không giải quyết ACL sai. Một vòng retry không giới hạn chỉ tạo log và tải xác thực, không sửa cấu hình.

## 43. Transaction fencing không phải lỗi reconnect thông thường

Nếu log có `ProducerFencedException`, `InvalidProducerEpochException` hoặc lỗi transactional identity, đừng coi đó là broker disconnect đơn thuần.

Kiểm tra:

- Có hai producer cùng sử dụng một `transactional.id` không?
- Transaction ID prefix có duy nhất theo instance không?
- Có zombie pod/process cũ chưa shutdown không?
- Producer factory có cache/suffix lifecycle đúng không?
- Rolling deployment có tạo identity conflict không?

Kafka client có thể reconnect thành công nhưng producer cũ vẫn bị fencing vì identity đã mất quyền hợp lệ. Restart loop với cùng transactional ID conflict có thể lặp lại lỗi.

Cần sửa identity/lifecycle và bảo đảm transaction outcome. Không đổi transactional ID tùy tiện mỗi lần lỗi vì có thể ảnh hưởng transaction recovery và producer identity semantics.

## 44. Test broker outage và recovery

Một integration test có ý nghĩa nên mô phỏng broker không truy cập được rồi phục hồi.

Có thể dùng Testcontainers và một proxy mạng có khả năng ngắt/kết nối lại traffic, hoặc môi trường test cho phép dừng/khởi động broker. Kịch bản:

1. Khởi động broker, topic và consumer group.
2. Gửi một số record và xác nhận listener xử lý.
3. Ngắt đường kết nối giữa application và broker trong thời gian giới hạn.
4. Xác nhận container/process không restart liên tục chỉ vì disconnect.
5. Xác nhận metric reconnect/request failures tăng.
6. Trong outage, gửi producer record theo hợp đồng đã chọn và quan sát future/outbox behavior.
7. Khôi phục kết nối broker.
8. Xác nhận client reconnect và consumer group ổn định.
9. Xác nhận record chưa commit được xử lý lại an toàn.
10. Xác nhận lag giảm và producer sends tiếp tục.
11. Xác nhận pod restart count không tăng ngoài dự kiến.
12. Kiểm tra readiness chuyển trạng thái theo grace period/hysteresis.

Không viết assertion cứng rằng container luôn giữ nguyên assignment trong outage dài; group protocol có thể rebalance tùy timeout và tình trạng coordinator. Kiểm tra outcome cuối và delivery guarantee.

## 45. Test readiness/liveness khi broker down

Tách hai mục tiêu:

**Liveness test**

1. Chạy ứng dụng với broker healthy.
2. Ngắt broker.
3. Xác nhận liveness vẫn UP nếu JVM/process còn hoạt động.
4. Xác nhận không có restart do chỉ một lỗi broker tạm thời.
5. Tạo deadlock nội bộ có kiểm soát trong test riêng.
6. Xác nhận liveness có thể phát hiện lỗi process thật theo policy.

**Readiness test**

1. Xác định service contract: có outbox hay yêu cầu Kafka synchronous?
2. Ngắt broker.
3. Xác nhận readiness theo đúng contract, không dao động theo từng request.
4. Khôi phục broker.
5. Chờ số lần probe thành công đủ điều kiện hysteresis.
6. Xác nhận readiness trở lại UP.
7. Kiểm tra readiness không gọi broker blocking ở mỗi request.

Không dùng một test chung để chứng minh cả liveness và readiness; chúng có mục đích khác nhau.

## 46. Test restart supervisor và backoff

Nếu ứng dụng có cơ chế restart listener container:

1. Tạo một lỗi khiến container thực sự stopped theo contract của version đang dùng.
2. Ghi nhận supervisor nhận đúng event/state.
3. Xác nhận một restart attempt duy nhất được lên lịch.
4. Xác nhận backoff tăng và có jitter trong giới hạn.
5. Gửi nhiều event duplicate; không tạo nhiều restart đồng thời.
6. Cho broker phục hồi; xác nhận container start và group assignment ổn định.
7. Cho lỗi lặp lại quá ngưỡng; xác nhận circuit open/alert thay vì restart vô hạn.
8. Bắt đầu application shutdown; xác nhận supervisor không schedule start mới.
9. Xác nhận success ổn định reset failure counter theo policy.

Không test restart loop bằng cách restart process vô hạn trong CI. Dùng clock/scheduler giả hoặc giới hạn số lần thử để suite kết thúc xác định.

## 47. Runbook khi broker tạm thời lỗi

Khi thấy nhiều Kafka disconnect/request timeout:

1. **Xác định phạm vi:** một broker, một client, một pod hay toàn cluster?
2. **Kiểm tra broker health:** node restart, controller/leader election, coordinator.
3. **Kiểm tra network:** DNS, routing, firewall, network policy, TLS và advertised listeners.
4. **Kiểm tra Kafka client:** reconnect attempts, request latency, retry và timeout.
5. **Kiểm tra lifecycle:** listener container còn running hay đã stopped?
6. **Kiểm tra group:** member count, assignment, rebalance và heartbeat.
7. **Kiểm tra producer:** future failures, delivery timeout, buffer pressure.
8. **Kiểm tra transaction:** commit/abort, fencing và outcome unknown.
9. **Kiểm tra Kubernetes:** liveness/readiness transitions, restart count và termination events.
10. **Kiểm tra retry layers:** client retry, record retry, supervisor restart và orchestrator.
11. **Giữ offset an toàn:** không reset/seek bỏ qua backlog.
12. **Giữ side effect idempotent:** dự phòng redelivery sau outage.
13. **Khôi phục broker/network/config:** sửa root cause trước khi tăng restart.
14. **Theo dõi reconnect:** tránh thundering herd và broker overload.
15. **Theo dõi drain:** lag, oldest record age, producer/consumer rate.
16. **Ghi nhận hậu kiểm:** thời gian outage, số lần restart, duplicate và SLO impact.

Không reset consumer group hoặc xóa topic để xử lý lỗi kết nối tạm thời. Những thao tác đó không khôi phục network và có thể làm mất tiến độ dữ liệu.

## 48. Những lỗi thiết kế thường gặp

| Sai sót | Hậu quả | Cách xử lý |
|---|---|---|
| Liveness gọi broker trực tiếp | Broker outage làm restart mọi pod | Liveness phản ánh process |
| Restart pod ở mỗi disconnect | Restart loop và rebalance storm | Để Kafka client reconnect |
| Restart container đang tự reconnect | Phá recovery đang diễn ra | Kiểm tra lifecycle/terminal error |
| Retry không có backoff | Thundering herd | Exponential backoff và jitter |
| Mỗi tầng retry độc lập không có deadline | Retry multiplication | Phân vai và deadline rõ |
| Readiness gọi AdminClient blocking mỗi probe | Health endpoint treo khi broker down | Background snapshot có timeout |
| Coi container running là broker healthy | Bỏ sót request failures | Kết hợp client metrics/progress |
| Coi broker disconnect là listener exception | Dùng sai DefaultErrorHandler | Tách transport và record errors |
| Dùng auth retry để chữa ACL sai | Retry mãi không phục hồi | Sửa credential/permission |
| Đổi transactional.id sau mọi timeout | Phá identity/recovery semantics | Phân biệt timeout và fencing |
| Commit offset hoặc seek để bỏ backlog | Mất dữ liệu | Giữ committed progress |
| Restart tất cả pods cùng lúc | Connection storm | Stagger, jitter, rollout có kiểm soát |
| Scale consumer theo lag mà bỏ qua DB | Downstream quá tải hơn | Scale theo bottleneck và partition |
| Resume toàn bộ backlog không giới hạn | Burst tới dependency | Rate limit/concurrency control |
| Chỉ monitor log errors | Không thấy progress/SLO | Metrics group, lag, restart, health |

## 49. Checklist triển khai production

- Bootstrap servers có nhiều endpoint hợp lệ?
- Advertised listeners/DNS/network/TLS đúng với nơi chạy consumer?
- Kafka client reconnect/retry backoff có giá trị phù hợp?
- Producer delivery timeout và request timeout phù hợp SLA?
- Consumer session timeout, heartbeat và max.poll interval được hiểu đúng?
- Listener container có thể tự reconnect trong outage tạm thời?
- Có phân biệt lỗi request retryable với lỗi terminal làm container dừng?
- Auth exception retry interval có được cấu hình khi phù hợp?
- DefaultErrorHandler chỉ xử lý lỗi record, không bị dùng làm broker reconnect policy?
- Liveness không phụ thuộc trực tiếp vào broker tạm thời?
- Readiness phản ánh service contract và có grace/hysteresis?
- Health endpoint không tạo network call blocking cho mỗi probe?
- Restart supervisor có backoff, jitter, cooldown và attempt limit?
- Restart không chạy khi application đang shutdown?
- Retry không bị nhân ở mọi tầng?
- Event ID/idempotency bảo vệ redelivery?
- Transactional ID không bị thay đổi tùy tiện hoặc trùng giữa instance?
- Outbox được cân nhắc nếu API cần nhận command khi Kafka down?
- Metrics có reconnect, request failures, group assignment, lag, delivery timeout và pod restarts?
- Có test broker outage/recovery, readiness/liveness và restart supervisor?
- Runbook không reset offset để chữa lỗi kết nối?

## 50. Kết luận

**Không restart loop khi broker tạm thời lỗi** bắt đầu từ việc hiểu rằng Kafka client có khả năng reconnect và retry nhiều lỗi transport mà không cần khởi động lại JVM. Spring Kafka listener container có thể vẫn running trong lúc broker unavailable, và việc restart liên tục có thể làm group rebalance, tăng tải broker và kéo dài outage.

Hãy để Kafka client xử lý reconnect theo backoff của nó; dùng error handler cho lỗi record; dùng auth retry hoặc recovery policy phù hợp cho những lỗi lifecycle có thể thử lại; và chỉ restart container/process khi có bằng chứng nó đã dừng hoặc không thể tự phục hồi. Liveness cần bảo vệ process, readiness cần phản ánh hợp đồng phục vụ, còn supervisor phải có backoff, jitter và giới hạn attempts.

Khi broker trở lại, offset và side effect phải được xử lý an toàn trước redelivery, backlog cần được drain theo năng lực downstream, và monitoring phải cho thấy cả connectivity lẫn progress. **Một client giữ được khả năng tự phục hồi trong outage ngắn thường ổn định hơn một hệ thống restart mỗi khi gặp lỗi mạng.**
