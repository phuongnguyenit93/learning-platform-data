# Đánh đổi độ bền với hiệu năng

## Mục tiêu của bài học

Trong chương **Hiệu năng**, bài này phân tích cách cân bằng độ bền dữ liệu (durability) với thông lượng (throughput) và độ trễ (latency) khi xây dựng ứng dụng Kafka bằng Spring Kafka. Một cấu hình có thể giảm nguy cơ mất record nhưng tăng thời gian xác nhận, chi phí replication hoặc độ trễ xử lý. Ngược lại, tối ưu tốc độ quá mức có thể làm tăng cửa sổ mất dữ liệu hoặc số lần xử lý trùng khi hệ thống gặp sự cố.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Đánh đổi độ bền với hiệu năng cần được đánh giá trên toàn bộ đường đi của event: producer, broker replication, consumer processing và offset commit.

Sau bài học, người học có thể:

- Phân biệt durability, availability, throughput và latency.
- Hiểu tác động của producer acks, retries và idempotence.
- Kết hợp replication factor với min.insync.replicas.
- Tối ưu batching, linger, compression và producer buffer.
- Chọn consumer acknowledgment/commit strategy phù hợp.
- Hiểu Kafka transaction và phạm vi exactly-once semantics.
- Nhận diện giới hạn của Kafka guarantee khi cập nhật database ngoài Kafka.
- Điều chỉnh fetch, poll và concurrency mà không gây rebalance liên tục.
- Thiết kế cấu hình theo SLA và mức độ quan trọng của event.
- Đo kiểm bằng failure test và benchmark có kiểm soát.

## 1. Durability và performance là hai mục tiêu khác nhau

**Durability** là khả năng giữ dữ liệu đã được xác nhận qua các lỗi như broker process dừng, máy chủ hỏng hoặc replica mất kết nối. **Performance** thường được đánh giá bằng throughput và latency:

- Throughput: số record hoặc byte xử lý được trong một đơn vị thời gian.
- Latency: thời gian từ lúc gửi đến lúc nhận xác nhận hoặc hoàn tất xử lý.
- Durability: xác suất record đã được xác nhận vẫn tồn tại sau sự cố.
- Availability: khả năng tiếp tục nhận và xử lý request khi một phần hệ thống gặp lỗi.

Không thể tối đa hóa tất cả các chỉ số bằng một cấu hình duy nhất. Ví dụ, chờ replication đầy đủ có thể tăng latency nhưng giảm nguy cơ mất record khi leader hỏng. Gom nhiều record vào một batch giảm số request và tăng throughput, nhưng record đầu tiên phải chờ lâu hơn để batch đầy hoặc hết linger.

Hãy phân biệt các mốc trong một luồng event:

1. Ứng dụng tạo event.
2. Producer serialize và đưa record vào buffer.
3. Producer gửi request tới broker.
4. Broker leader append record.
5. Replica theo kịp leader theo replication protocol.
6. Broker gửi acknowledgment theo cấu hình acks.
7. Consumer poll record.
8. Listener xử lý side effect.
9. Consumer commit offset.

Một record có thể đã được broker xác nhận nhưng chưa được consumer xử lý. Ngược lại, listener có thể đã cập nhật database nhưng offset chưa commit, khiến record được giao lại sau crash. Vì vậy, durability của producer và reliability của consumer là hai phần riêng.

~~~mermaid
flowchart LR
    A["Application event"] --> B["Serialize + producer buffer"]
    B --> C["Broker leader"]
    C --> D["Follower replicas"]
    D --> E["Producer acknowledgment"]
    E --> F["Consumer poll"]
    F --> G["Listener processing"]
    G --> H["Offset commit"]
    I["Producer settings"] -. "acks / retries / batching" .-> B
    J["Topic settings"] -. "replication / min ISR" .-> C
    K["Consumer settings"] -. "ack mode / commit" .-> G
~~~

## 2. Producer acks quyết định mức xác nhận ghi

Thuộc tính acks xác định producer cần bao nhiêu xác nhận từ broker trước khi xem send thành công.

| acks | Điều kiện xác nhận | Đánh đổi |
|---|---|---|
| 0 | Producer không chờ broker acknowledgment | Latency thấp, nhưng không biết broker đã nhận record hay chưa |
| 1 | Leader xác nhận sau khi append record vào log cục bộ | Nhanh hơn, nhưng leader có thể hỏng trước khi follower replicate |
| all | Leader chờ các replica hiện đang thuộc ISR xác nhận theo replication protocol | Độ bền tốt hơn, latency có thể cao hơn và phụ thuộc ISR |

### 2.1. acks=0

Producer gửi record mà không chờ broker xác nhận. Ứng dụng không có bằng chứng broker đã nhận record. Nếu network đứt hoặc broker không nhận được request, ứng dụng có thể vẫn coi lần gửi đã hoàn tất.

Cấu hình này chỉ phù hợp với dữ liệu có thể mất và có khả năng tạo lại, chẳng hạn một số telemetry không quan trọng. Không dùng cho payment, order, inventory hoặc command cần bảo đảm.

### 2.2. acks=1

Leader xác nhận sau khi ghi record vào log của mình. Follower có thể replicate sau đó. Nếu leader hỏng trước khi follower nhận record, một replica khác được bầu làm leader có thể không có record vừa được xác nhận.

acks=1 có thể giảm thời gian chờ so với acks=all, nhưng tạo cửa sổ mất dữ liệu khi leader failure. Hãy dùng khi yêu cầu độ bền cho phép mức rủi ro này và replication topology đã được đánh giá.

### 2.3. acks=all

acks=all yêu cầu leader chờ tất cả replica hiện thuộc ISR xác nhận record theo replication protocol. Đây thường là lựa chọn cho event quan trọng, nhưng cần cấu hình min.insync.replicas phù hợp để tránh ghi khi ISR quá nhỏ.

acks=all không có nghĩa broker đã fsync từng record xuống thiết bị lưu trữ trước khi trả lời. Kafka dựa vào log, page cache và replication; durability thực tế còn phụ thuộc cấu hình broker, hệ điều hành, filesystem và hạ tầng lưu trữ.

## 3. Replication factor và min.insync.replicas

Producer acks chỉ là một phần của durability. Topic cần có đủ replica để chịu lỗi broker.

Ví dụ topic có replication factor bằng 3:

~~~text
Topic: commerce.order.created
Partition 0:
  Broker 1: Leader
  Broker 2: Follower
  Broker 3: Follower

min.insync.replicas = 2
producer acks = all
~~~

Trong cấu hình này, producer chỉ được phép ghi với acks=all khi số replica thuộc ISR đạt ít nhất hai. Leader chờ các replica hiện có trong ISR xác nhận. Nếu ISR giảm xuống một, broker từ chối ghi để giữ điều kiện min ISR thay vì chấp nhận một lần ghi có mức bảo vệ thấp hơn.

| Replication factor | min.insync.replicas | Ý nghĩa vận hành |
|---:|---:|---|
| 1 | 1 | Không có replica dự phòng |
| 3 | 1 | Vẫn có thể ghi khi chỉ leader còn trong ISR |
| 3 | 2 | Có thể ghi khi còn ít nhất hai ISR |
| 3 | 3 | Yêu cầu đủ cả ba replica trong ISR mới ghi |

Với dữ liệu quan trọng, cấu hình phổ biến là replication factor 3, min.insync.replicas 2 và producer acks=all. Đây là điểm khởi đầu để đánh giá, không phải con số bắt buộc cho mọi workload.

Có thể khai báo topic mới bằng Spring Kafka khi ứng dụng quản lý topic qua KafkaAdmin:

~~~java
@Bean
public NewTopic orderCreatedTopic() {
    return TopicBuilder.name("commerce.order.created")
        .partitions(6)
        .replicas(3)
        .config(TopicConfig.MIN_IN_SYNC_REPLICAS_CONFIG, "2")
        .build();
}
~~~

Ví dụ này áp dụng khi tạo topic mới. Với topic đã tồn tại, hãy quản lý cấu hình bằng quy trình provisioning/admin riêng và xác minh cấu hình thực tế trên broker; không giả định khai báo bean sẽ tự sửa mọi thuộc tính của topic hiện hữu.

### 3.1. Khi ISR nhỏ hơn min ISR

Khi số replica trong ISR thấp hơn min.insync.replicas, producer có thể nhận lỗi NotEnoughReplicas hoặc NotEnoughReplicasAfterAppend. Đây là hành vi bảo vệ durability: broker từ chối ghi vì không đạt mức replication tối thiểu.

Ứng dụng cần:

- Retry theo delivery timeout và retry policy phù hợp.
- Theo dõi ISR shrink và under-replicated partitions.
- Khắc phục broker/network/disk gây replica tụt lại.
- Tránh tự hạ min ISR trong lúc incident nếu chưa đánh giá rủi ro mất dữ liệu.
- Có alert khi producer error rate tăng do replica không đủ.

Nếu min ISR được đặt bằng replication factor, bất kỳ replica nào tạm mất cũng có thể chặn ghi. Độ bền cao hơn nhưng availability ghi thấp hơn. Nếu min ISR quá thấp, hệ thống vẫn ghi được khi ít replica còn khỏe, nhưng khả năng chịu lỗi giảm.

### 3.2. Unclean leader election

Unclean leader election cho phép một replica không thuộc ISR trở thành leader khi không còn ISR replica nào có thể làm leader. Điều này có thể khôi phục availability nhưng có nguy cơ mất các record chưa được replica đó nhận.

Với dữ liệu cần độ bền, thường tắt unclean leader election. Đổi lại, partition có thể unavailable cho tới khi một ISR replica có thể trở lại. Đây là lựa chọn giữa availability và durability khi toàn bộ ISR mất khả năng làm leader.

## 4. Producer idempotence và retry

Retry giúp producer phục hồi lỗi tạm thời như network timeout hoặc broker chuyển leader. Nhưng nếu broker đã ghi record mà acknowledgment bị mất, producer có thể gửi lại và tạo duplicate.

Idempotent producer dùng producer ID và sequence number để broker nhận diện retry của cùng một batch, tránh ghi duplicate do retry trong phạm vi producer session.

Cấu hình khuyến nghị:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
~~~

Với Kafka client hiện đại, idempotence được bật mặc định trong nhiều cấu hình mặc định; khai báo rõ giúp ý định vận hành dễ đọc hơn. Khi bật idempotence, Kafka yêu cầu các điều kiện tương thích như acks=all, retries lớn hơn 0 và max.in.flight.requests.per.connection không vượt quá giới hạn được hỗ trợ.

Idempotence bảo vệ retry nội bộ của producer. Nó không tự loại bỏ duplicate do:

- Ứng dụng gọi publish hai lần cho cùng một business event.
- Service restart và tạo lại event.
- Client gửi lại command sau timeout.
- Hai producer độc lập phát cùng một event.
- Consumer xử lý side effect nhiều lần sau offset chưa commit.

Vì vậy, event quan trọng vẫn nên có eventId ổn định và consumer idempotency.

### 4.1. Retry và delivery timeout

Producer retry lỗi có thể tăng latency. delivery.timeout.ms giới hạn tổng thời gian producer cố gắng gửi record trước khi báo thất bại; request.timeout.ms giới hạn thời gian chờ một request; linger.ms thêm thời gian chờ gom batch.

Cần đặt delivery.timeout.ms đủ lớn so với request.timeout.ms và linger.ms. Nếu timeout quá ngắn, producer có thể báo thất bại khi broker đang phục hồi. Nếu quá dài, caller phải chờ lâu trước khi biết gửi không thành công.

Không retry vô hạn ở tầng nghiệp vụ mà không có giới hạn. Khi producer đã hết delivery timeout, ứng dụng cần ghi nhận trạng thái thất bại và quyết định retry ở tầng application theo event ID/idempotency policy.

## 5. Batching: tăng throughput bằng cách gom record

Producer gom nhiều record cùng partition vào một batch trước khi gửi. Batch giảm overhead network request, amortize chi phí protocol và thường tăng throughput.

Hai cấu hình quan trọng:

- batch.size: kích thước batch mục tiêu theo byte cho mỗi partition.
- linger.ms: thời gian producer chờ thêm record để batch đầy hơn trước khi gửi.

Ví dụ:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 65536
        linger.ms: 5
        buffer.memory: 67108864
~~~

Ví dụ dùng batch mục tiêu 64 KiB, linger 5 ms và producer buffer 64 MiB. Đây là giá trị khởi điểm để benchmark; workload ít record hoặc latency-sensitive có thể cần linger thấp hơn.

### 5.1. Tăng batch size

Batch lớn có thể tăng hiệu quả network và compression khi có đủ traffic trên partition. Nhưng batch quá lớn có thể:

- Tăng bộ nhớ producer sử dụng.
- Làm record đầu tiên chờ lâu hơn.
- Tạo burst traffic lớn tới broker.
- Tăng thời gian serialize/compress mỗi batch.
- Không đem lại lợi ích nếu traffic mỗi partition quá thấp.

Batch được tạo theo partition, nên tổng bộ nhớ có thể tăng khi producer gửi tới nhiều partition cùng lúc.

### 5.2. Tăng linger.ms

linger.ms cho producer thêm thời gian gom record. Tăng linger thường cải thiện batch utilization và throughput khi traffic dày, đổi lại tăng latency gửi.

Với API cần phản hồi trong vài mili giây, linger thấp hoặc bằng 0 có thể hợp lý. Với event pipeline ưu tiên throughput, vài mili giây hoặc hơn có thể cải thiện hiệu suất đáng kể. Hãy đo p95/p99 latency thay vì chỉ nhìn throughput trung bình.

### 5.3. Không flush sau mỗi record

Gọi flush sau từng send sẽ ép producer đẩy các batch đang chờ và làm mất lợi ích batching. Thường nên để producer buffer và batch hoạt động tự nhiên, rồi theo dõi send future.

Chỉ flush khi có ranh giới nghiệp vụ rõ ràng, khi cần bảo đảm các record đã được gửi trước một thao tác shutdown hoặc trong một workflow đặc biệt. Không dùng flush mỗi message như mặc định.

## 6. Compression: giảm network và disk bằng CPU

Producer có thể nén batch trước khi gửi. Kafka hỗ trợ các codec phổ biến như gzip, snappy, lz4 và zstd tùy phiên bản client/broker.

| Codec | Đặc điểm tổng quát | Trade-off |
|---|---|---|
| none | Không nén | CPU thấp, byte truyền nhiều |
| lz4 | Tốc độ nén/giải nén nhanh | Tỷ lệ nén thường vừa phải |
| snappy | Nhanh, chi phí CPU thấp | Tỷ lệ nén thường vừa phải |
| gzip | Tỷ lệ nén tốt trong nhiều workload | CPU cao hơn và có thể tăng latency |
| zstd | Tỷ lệ nén tốt, có nhiều mức compression level | Có thể tốn CPU tùy level |

Ví dụ:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        compression.type: lz4
~~~

Compression thường hiệu quả hơn khi batch đủ lớn và payload có cấu trúc lặp. Payload đã nén hoặc mã hóa có thể không giảm được nhiều. Nén làm giảm network bandwidth và lượng dữ liệu ghi, nhưng tăng CPU producer, broker hoặc consumer tùy vị trí codec được xử lý.

Đo cả CPU, network bytes, disk throughput và latency. Không chọn codec chỉ dựa vào tỷ lệ nén cao nhất.

## 7. Buffer và gửi bất đồng bộ

KafkaTemplate.send gửi bất đồng bộ và trả về future. Nếu gọi get ngay sau từng send, ứng dụng biến luồng gửi thành tuần tự và tự giới hạn throughput theo latency của broker.

Ví dụ:

~~~java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event) {

    return kafkaTemplate.send(
        "commerce.order.created",
        event.orderId(),
        event
    );
}
~~~

Có thể gắn callback để ghi nhận thành công/thất bại:

~~~java
kafkaTemplate.send(topic, key, event)
    .whenComplete((result, exception) -> {
        if (exception != null) {
            log.error("Kafka publish failed, eventId={}",
                event.eventId(), exception);
            return;
        }

        RecordMetadata metadata =
            result.getRecordMetadata();

        log.debug("Published topic={}, partition={}, offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset());
    });
~~~

Ví dụ dùng CompletableFuture trong Spring Kafka 3.x. Với Spring Kafka 2.x, send thường trả về ListenableFuture và callback API tương ứng khác.

Không tạo số lượng future không giới hạn. Nếu producer nhanh hơn broker, buffer.memory có thể đầy; send có thể block tới max.block.ms rồi ném exception. Dùng bounded concurrency, rate limit hoặc backpressure ở tầng ứng dụng.

## 8. Chọn cấu hình producer theo mục tiêu

| Workload | Acks | Idempotence | Batching/compression | Định hướng |
|---|---|---|---|---|
| Payment/order command | all | true | Batch vừa, linger thấp theo SLA | Ưu tiên durability và xử lý lỗi rõ |
| Audit event | all | true | Batch vừa/lớn, compression phù hợp | Ưu tiên lưu bền và throughput ổn định |
| Clickstream lớn | all hoặc policy theo khả năng mất dữ liệu | true nếu cần chống duplicate retry | Batch lớn hơn, compression | Ưu tiên throughput và chi phí |
| Metrics có thể tái tạo | Có thể cân nhắc 1 hoặc 0 theo rủi ro | Theo nhu cầu | Batch lớn, compression | Ưu tiên tốc độ/chi phí |
| Low-latency command | all nếu cần durability | true | linger thấp, batch nhỏ hơn | Giữ SLA nhưng không bỏ guarantee nghiệp vụ |

Không dùng acks=0 chỉ vì benchmark cho thấy throughput cao. Benchmark phải phản ánh cả lỗi broker/network và mức mất dữ liệu mà nghiệp vụ chấp nhận.

## 9. Consumer acknowledgment và offset commit

Consumer poll record từ Kafka. Offset commit cho broker biết consumer group đã xử lý tới đâu. Thời điểm commit quyết định cửa sổ record có thể được giao lại sau crash.

Với Spring Kafka, container quản lý commit theo AckMode. Một số chế độ thường dùng:

| AckMode | Thời điểm commit | Đánh đổi |
|---|---|---|
| RECORD | Sau khi listener xử lý từng record thành công | Cửa sổ replay nhỏ hơn, commit thường xuyên hơn |
| BATCH | Sau khi xử lý toàn bộ batch từ poll | Ít commit hơn, có thể replay nhiều record hơn |
| TIME | Khi đủ khoảng thời gian và điều kiện xử lý | Điều chỉnh tần suất commit |
| COUNT | Khi đủ số record | Giảm commit overhead |
| COUNT_TIME | Theo count hoặc time | Cân bằng số lần commit |
| MANUAL | Listener chủ động acknowledge; container commit theo policy | Kiểm soát rõ hơn, cần code cẩn thận |
| MANUAL_IMMEDIATE | Commit ngay khi acknowledge theo execution context | Có thể tăng commit overhead |

Tên và semantics chi tiết cần đối chiếu với phiên bản Spring Kafka đang sử dụng. Với RECORD/BATCH, listener phải hoàn tất thành công trước khi container commit theo mode tương ứng.

### 9.1. Vì sao commit trước xử lý có thể mất dữ liệu?

Giả sử consumer commit offset trước khi cập nhật database. Nếu process crash sau commit nhưng trước database write, Kafka sẽ không giao lại record đã commit. Side effect bị mất.

Nếu consumer xử lý database trước rồi mới commit offset, crash sau database commit nhưng trước Kafka offset commit có thể khiến record được giao lại. Đây là at-least-once behavior; cần idempotency để không tạo side effect trùng.

Đối với nghiệp vụ quan trọng, thứ tự thường là xử lý thành công rồi mới commit offset, kết hợp idempotent database operation hoặc inbox table.

### 9.2. Auto commit và Spring Kafka

Nên hiểu rõ enable.auto.commit. Spring Kafka listener container thường quản lý offset commit và mặc định tắt Kafka auto commit trong cấu hình container hiện đại, nhưng hãy khai báo rõ và kiểm tra cấu hình effective.

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

Spring Kafka listener container mặc định dùng synchronous commit trong các cấu hình thông dụng. Có thể cấu hình rõ trên listener container factory:

~~~java
factory.getContainerProperties().setSyncCommits(true);
~~~

Synchronous commit dùng commitSync cho commit do container quản lý. Nó có thể tăng latency nhưng lỗi commit được quan sát ngay trong luồng commit. Async commit có thể giảm thời gian chờ nhưng cần hiểu callback, thứ tự commit và cách xử lý lỗi.

### 9.3. RECORD hay BATCH?

RECORD hợp lý khi mỗi event có side effect độc lập và cần thu nhỏ số record có thể bị replay sau lỗi. BATCH có thể tăng hiệu quả commit khi xử lý nhiều record mỗi poll, nhưng một lỗi ở cuối batch có thể khiến nhiều record chưa commit được giao lại tùy error handling và acknowledgment policy.

Hãy chọn dựa trên chi phí commit, semantics xử lý và khả năng idempotency. Không chọn BATCH chỉ vì muốn giảm commit count nếu code listener không xử lý được duplicate.

## 10. Consumer fetch và poll tuning

Consumer lấy record theo poll. Một số thuộc tính ảnh hưởng lượng dữ liệu và thời gian poll:

- fetch.min.bytes: lượng dữ liệu tối thiểu broker cố gắng gom trước khi trả fetch response.
- fetch.max.wait.ms: thời gian broker có thể chờ để đạt fetch.min.bytes.
- max.partition.fetch.bytes: giới hạn dữ liệu lấy từ một partition trong fetch.
- fetch.max.bytes: giới hạn tổng dữ liệu fetch response.
- max.poll.records: số record tối đa trả về trong một lần poll.
- max.poll.interval.ms: giới hạn thời gian giữa các lần poll trước khi consumer bị xem là không còn tiến triển.

Tăng fetch.min.bytes có thể giảm số request và tăng throughput khi traffic dày, nhưng tăng latency khi traffic thấp. Tăng max.poll.records có thể tăng lượng việc mỗi poll, nhưng listener phải xử lý batch đó trong giới hạn max.poll.interval.ms.

Nếu xử lý record chậm, tăng max.poll.records có thể làm consumer vượt max.poll.interval.ms và bị rebalance. Hãy điều chỉnh processing time, concurrency và poll interval đồng thời.

Ví dụ một số cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 500
      properties:
        fetch.min.bytes: 65536
        fetch.max.wait.ms: 50
        max.partition.fetch.bytes: 1048576
        max.poll.interval.ms: 300000
~~~

Các giá trị này chỉ là ví dụ để benchmark. Không áp dụng nguyên xi khi payload lớn, listener xử lý lâu hoặc số partition thấp.

## 11. Concurrency và partition

Trong một consumer group, một partition tại một thời điểm chỉ được gán cho một consumer member. Tăng concurrency giúp xử lý song song khi topic có đủ partition.

Ví dụ topic có 6 partition:

- Concurrency 1: một consumer đọc cả 6 partition.
- Concurrency 3: tối đa ba consumer chia nhau 6 partition.
- Concurrency 6: có thể dùng tối đa sáu consumer, mỗi consumer một partition.
- Concurrency 10: ít nhất bốn consumer không có partition trong group nếu không có topic khác được subscribe.

Tăng concurrency vượt số partition không làm tăng throughput của topic đó. Nó còn tăng thread, connection và chi phí quản lý consumer.

Trong Spring Kafka:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    groupId = "billing-service",
    concurrency = "3"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Concurrency phải cân bằng với:

- Số partition.
- Thời gian xử lý mỗi record.
- Capacity của database/downstream.
- Số consumer instance trong deployment.
- Ordering yêu cầu theo key.
- Consumer lag và rebalance frequency.

Không tăng concurrency khi database đã quá tải; việc đó có thể làm throughput end-to-end giảm do contention và connection pool exhaustion.

## 12. Kafka transaction và exactly-once semantics

Idempotent producer ngăn duplicate do retry trong một producer session. Kafka transaction mở rộng khả năng bảo đảm cho nhiều record và offset trong workflow Kafka-to-Kafka.

Một transaction có thể:

- Ghi nhiều record vào một hoặc nhiều topic.
- Đưa offset của consumer group vào cùng transaction.
- Commit tất cả hoặc abort tất cả.

Với consume-transform-produce, consumer đọc input, producer ghi output và offset input được commit trong transaction. Consumer downstream cấu hình isolation.level=read_committed chỉ đọc record thuộc transaction đã commit.

~~~mermaid
sequenceDiagram
    participant C as Input Consumer
    participant A as Application
    participant T as Kafka Transaction
    participant O as Output Topic
    participant G as Consumer Group Offset
    C->>A: Read input record
    A->>T: Begin transaction
    A->>T: Produce output record
    A->>T: Send input offset to transaction
    T->>O: Commit output
    T->>G: Commit offset atomically
    Note over O,G: Hoặc abort cả output và offset
~~~

Kafka exactly-once semantics bảo vệ chuỗi consume-process-produce trong phạm vi Kafka transaction được cấu hình đúng. Nó không tự tạo transaction nguyên tử giữa Kafka và database ngoài Kafka.

### 12.1. Cấu hình transaction trong Spring Kafka

Với Spring Boot, có thể cấu hình transaction ID prefix:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-instance-unique-
    consumer:
      properties:
        isolation.level: read_committed
~~~

Transaction ID prefix phải duy nhất giữa các application instance đang hoạt động để tránh producer fencing lẫn nhau. Trong môi trường nhiều replica, cần gắn instance identity ổn định và duy nhất vào prefix thay cho giá trị minh họa ở trên.

Spring Boot có thể tự cấu hình transaction-capable producer factory khi transaction-id-prefix được đặt. Listener container có thể tham gia transaction theo cấu hình Spring Kafka phù hợp. Cần kiểm tra transaction manager, listener factory và error handling theo phiên bản ứng dụng.

### 12.2. Chi phí của transaction

Transaction tăng độ phức tạp và có thể tăng latency:

- Producer phải begin/commit/abort transaction.
- Coordinator quản lý transaction state.
- Consumer read_committed chỉ đọc tới last stable offset, có thể chờ transaction đang mở hoàn tất.
- Transaction kéo dài có thể làm record phía sau chưa hiển thị cho read_committed consumer.
- Transaction timeout và fencing cần được vận hành đúng.

Giữ transaction ngắn, giới hạn số record mỗi transaction và không gọi dịch vụ ngoài chậm trong khi transaction mở.

## 13. Kafka transaction không bao trùm database

Một listener có thể cập nhật database rồi publish event Kafka. Kafka transaction không tự commit/rollback database transaction cùng lúc.

Ví dụ:

1. Database transaction commit thành công.
2. Process crash trước khi Kafka publish.
3. Database có dữ liệu mới nhưng event không được gửi.

Hoặc:

1. Kafka publish thành công.
2. Database transaction rollback.
3. Event đã phát nhưng trạng thái database chưa đổi.

Đây là vấn đề dual write. Các hướng xử lý thường gặp:

- Transactional Outbox: ghi business data và outbox row trong cùng database transaction; publisher riêng phát outbox sang Kafka.
- Inbox/idempotency: consumer lưu event ID đã xử lý cùng business update.
- CDC: đọc outbox/change log để publish event.
- Saga/compensation: phối hợp nhiều service bằng các bước nghiệp vụ có thể bù trừ.

Không quảng cáo Kafka EOS như bảo đảm exactly-once cho mọi side effect trong hệ thống. Hãy nói rõ ranh giới transaction.

## 14. Đánh đổi độ bền với tốc độ theo từng tầng

| Tầng | Ưu tiên độ bền | Ưu tiên tốc độ | Rủi ro/chi phí |
|---|---|---|---|
| Producer acks | all | 1 hoặc 0 | Mức xác nhận ghi thấp hơn |
| Idempotence | bật | Có thể tắt trong workload cho phép duplicate | Retry có thể ghi duplicate |
| Broker replication | RF 3, min ISR 2 | RF thấp hơn | Ít replica dự phòng hơn |
| Leader election | Tắt unclean election | Có thể bật nếu ưu tiên availability | Có thể mất record chưa replicate |
| Batching | Batch đủ lớn nhưng giữ SLA | Batch lớn, linger cao | Latency và memory tăng |
| Compression | Chọn codec cân bằng | Có thể tắt nén | Network/disk tăng |
| Consumer commit | Sau xử lý thành công | Commit theo batch/count/time | Cửa sổ replay lớn hơn |
| Transaction | Kafka EOS khi cần | At-least-once đơn giản hơn | Coordinator/transaction overhead |
| Consumer isolation | read_committed cho transactional flow | read_uncommitted khi chấp nhận | Có thể thấy aborted records |

Cấu hình bền không nhất thiết làm mọi thứ chậm đáng kể nếu batching và compression được tối ưu. Hãy đo từng tầng để xác định bottleneck thực tế.

## 15. Ba profile cấu hình tham khảo

Các profile sau là điểm bắt đầu để benchmark, không phải preset dùng chung.

### 15.1. Profile ưu tiên durability

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        linger.ms: 5
        batch.size: 32768
        compression.type: lz4
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
    listener:
      ack-mode: record
~~~

Topic nên dùng replication factor 3 và min.insync.replicas 2. Profile này phù hợp với event quan trọng, có transaction hoặc yêu cầu commit sau từng record. Chỉ đặt read_committed khi consumer cần loại bỏ transactional records chưa commit/đã abort; nếu producer không dùng transaction, read_uncommitted có thể đơn giản hơn.

### 15.2. Profile cân bằng

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        linger.ms: 5
        batch.size: 65536
        compression.type: lz4
        delivery.timeout.ms: 120000
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: batch
~~~

Dùng batch commit để giảm commit overhead khi listener xử lý batch an toàn và idempotent. Cần đánh giá số record có thể bị replay sau lỗi.

### 15.3. Profile ưu tiên throughput

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        linger.ms: 20
        batch.size: 131072
        compression.type: zstd
        buffer.memory: 134217728
    consumer:
      enable-auto-commit: false
      max-poll-records: 1000
    listener:
      ack-mode: batch
~~~

Profile này tăng thời gian gom batch, batch size và buffer. Throughput có thể tăng khi traffic dày và payload nén tốt, nhưng latency và memory cũng tăng. Hãy kiểm tra CPU producer/consumer, broker request queue, consumer lag và p99 end-to-end latency.

## 16. Đo lường thay vì đoán

Benchmark phải phản ánh payload và failure mode gần production.

Đo tối thiểu:

- Producer records/sec và bytes/sec.
- Producer request latency p50, p95, p99.
- Send error, retry count và timeout.
- Average batch size và compression ratio.
- Broker network, disk throughput và request queue.
- Under-replicated partitions và ISR shrink.
- Consumer records/sec và lag theo partition.
- Listener processing time.
- Commit latency và commit failure.
- End-to-end event age từ createdAt tới processedAt.
- Duplicate rate và DLT rate.

Không chỉ đo throughput trung bình. Một cấu hình có thể tăng throughput 30% nhưng làm p99 latency tăng gấp nhiều lần hoặc khiến consumer lag tăng liên tục.

### 16.1. Quy trình benchmark

1. Tạo topic với replication factor và partition giống production.
2. Dùng payload có kích thước và phân bố giống dữ liệu thực.
3. Warm up producer, broker và consumer.
4. Chạy một cấu hình baseline.
5. Thay đổi một nhóm tham số tại một thời điểm.
6. Đo throughput, p95/p99 latency, CPU, network, disk và lag.
7. Lặp lại với broker restart hoặc replica chậm.
8. So sánh dữ liệu mất, duplicate và thời gian phục hồi.
9. Chọn cấu hình đạt SLA thay vì chỉ đạt throughput cao nhất.

Dùng cùng số producer, consumer, partition và workload khi so sánh. Nếu thay nhiều tham số cùng lúc, khó biết thay đổi nào tạo ra kết quả.

## 17. Failure test cho durability

Độ bền chỉ được kiểm chứng khi hệ thống gặp lỗi.

Các kịch bản cần thử trong môi trường test/staging:

- Dừng broker leader ngay sau khi producer gửi.
- Làm follower mất kết nối để ISR giảm.
- Tạm dừng broker hoặc gây network partition.
- Khởi động lại producer trong lúc có request đang chờ.
- Kill consumer sau khi xử lý side effect nhưng trước offset commit.
- Kill consumer sau offset commit.
- Làm database chậm hoặc từ chối connection.
- Để transaction mở lâu rồi abort.
- Replay record cũ qua consumer version mới.

Kiểm tra kết quả theo event ID:

| Kịch bản | Điều cần xác minh |
|---|---|
| Leader hỏng sau acks=1 | Có thể mất record nếu follower chưa replicate |
| Leader hỏng sau acks=all và min ISR phù hợp | Record đã được xác nhận vẫn có trên replica đủ điều kiện |
| Consumer crash trước xử lý | Record được giao lại |
| Consumer crash sau DB commit, trước offset commit | Record có thể được giao lại nhưng side effect không lặp |
| Consumer crash sau offset commit | Không mất side effect đã hoàn tất trước commit |
| Transaction abort | read_committed consumer không thấy output đã abort |
| ISR dưới min ISR | Producer nhận lỗi thay vì ghi dưới ngưỡng bảo vệ |

Không chạy failure test phá hủy trên production. Dùng môi trường có thể khôi phục và dữ liệu test nhận diện rõ.

## 18. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Producer throughput thấp | acks, linger, compression hoặc broker bottleneck | Đo request latency, batch và CPU |
| Record mất khi leader fail | acks=1 hoặc replication/min ISR yếu | Dùng acks=all, RF và min ISR phù hợp |
| Producer báo NotEnoughReplicas | ISR thấp hơn min ISR | Khôi phục replica và theo dõi ISR |
| Producer buffer đầy | Broker chậm hoặc ứng dụng gửi quá nhanh | Backpressure, bounded concurrency, tăng buffer có đo lường |
| Latency tăng sau tăng linger | Producer chờ gom batch | Giảm linger hoặc điều chỉnh SLA |
| CPU cao sau bật compression | Codec/level quá nặng | Thử lz4/snappy hoặc giảm compression level |
| Consumer lag tăng | Throughput xử lý thấp hơn tốc độ publish | Kiểm tra partition, downstream, poll và concurrency |
| Rebalance liên tục | Xử lý lâu vượt max.poll.interval.ms hoặc consumer không ổn định | Điều chỉnh poll/processing và tìm bottleneck |
| Duplicate side effect | At-least-once redelivery, app retry | Idempotency theo event ID |
| read_committed thấy lag cao | Transaction đang mở hoặc commit chậm | Giảm transaction duration và theo dõi LSO |
| Transaction producer bị fencing | Transaction ID prefix trùng giữa instance | Dùng prefix duy nhất |
| DLT không đọc được record cũ | Schema Registry thiếu schema version | Giữ schema history và test replay |

## 19. Quy tắc lựa chọn theo mức quan trọng của event

Không phải event nào cũng cần cùng mức durability.

| Loại event | Mức bảo vệ gợi ý | Lý do |
|---|---|---|
| PaymentCaptured | acks=all, RF 3, min ISR 2, idempotence | Không được âm thầm mất giao dịch |
| OrderCreated | acks=all, RF 3, min ISR 2, consumer idempotent | Event khởi đầu nhiều workflow |
| Audit/security event | Replication cao, retention rõ, giám sát DLT | Cần truy vết và điều tra |
| InventoryChanged | acks=all, key theo product/warehouse, idempotent consumer | Cần đúng trạng thái và thứ tự theo key |
| Clickstream | Batch/compression, replication theo giá trị dữ liệu | Khối lượng lớn, có thể có nguồn tái tạo |
| Metrics định kỳ | Có thể ưu tiên throughput/retention ngắn | Dữ liệu thường có thể tổng hợp lại |

Nếu một topic chứa nhiều loại event với mức quan trọng khác nhau, hãy cân nhắc tách topic hoặc producer policy để tránh một cấu hình compromise không phù hợp với bất kỳ loại nào.

## 20. Checklist thiết kế và vận hành

- [ ] Đã xác định RPO: có thể mất tối đa bao nhiêu record?
- [ ] Đã xác định latency SLA p95/p99?
- [ ] Producer dùng acks phù hợp với mức quan trọng?
- [ ] Idempotence được bật khi cần chống duplicate do retry?
- [ ] Replication factor và min.insync.replicas phù hợp?
- [ ] Unclean leader election có policy rõ?
- [ ] Retry và delivery timeout có giới hạn hợp lý?
- [ ] Batching/linger được benchmark với payload thực?
- [ ] Compression codec phù hợp CPU/network?
- [ ] Producer buffer có backpressure?
- [ ] Consumer commit sau khi xử lý thành công?
- [ ] AckMode phù hợp với duplicate window và commit cost?
- [ ] Concurrency không vượt capacity partition/downstream?
- [ ] max.poll.interval.ms phù hợp thời gian xử lý?
- [ ] Kafka transaction chỉ dùng khi cần atomic Kafka workflow?
- [ ] Database side effect có outbox/inbox hoặc idempotency?
- [ ] Có metrics cho ISR, under-replicated partitions, lag và commit?
- [ ] Đã failure test broker, producer, consumer và transaction?
- [ ] Đã đo end-to-end latency, không chỉ producer throughput?

## Kết luận

Độ bền và hiệu năng cần được cân bằng theo yêu cầu nghiệp vụ. Với event quan trọng, một cấu hình nền tảng thường là producer acks=all, idempotence bật, topic replication factor 3 và min.insync.replicas 2; consumer xử lý thành công rồi mới commit offset, kết hợp idempotency để chịu được redelivery. Batching, linger và compression có thể cải thiện throughput mà vẫn giữ các guarantee này, nhưng phải đo latency, CPU, network và memory.

Kafka transaction hỗ trợ exactly-once cho luồng consume-process-produce trong phạm vi Kafka; nó không tự bao trùm database hoặc side effect bên ngoài. Hãy xác định RPO và latency SLA trước, tối ưu từng tầng bằng benchmark, rồi kiểm chứng bằng failure test. Cấu hình tốt là cấu hình đạt yêu cầu nghiệp vụ khi hệ thống hoạt động bình thường lẫn khi broker, network hoặc consumer gặp sự cố.
