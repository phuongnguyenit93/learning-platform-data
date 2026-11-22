# Lag tăng dù consumer đang chạy

Consumer process vẫn hoạt động không có nghĩa là consumer đang xử lý record đủ nhanh. Một listener có thể đang block ở HTTP/DB, retry liên tục, không commit offset, liên tục rebalance hoặc chỉ có một partition nóng phải xử lý phần lớn traffic. Trong các tình huống đó, ứng dụng vẫn có thread, log và heartbeat nhưng consumer lag tiếp tục tăng.

Muốn chẩn đoán đúng, cần nhìn lag theo từng partition và theo thời gian, so sánh tốc độ record đi vào với tốc độ record được xử lý và commit, rồi đối chiếu với trạng thái poll, listener duration, rebalance, downstream và broker. Tăng concurrency hoặc reset offset ngay khi thấy lag thường không giải quyết nguyên nhân và có thể làm sự cố nặng hơn.

Bài học thuộc chương **Chẩn đoán sự cố** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Consumer lag là gì?

Consumer lag là khoảng cách giữa vị trí consumer group đã xác nhận và vị trí dữ liệu hiện có ở partition. Với cách tính phổ biến:

\[
\text{lag} = \text{log end offset} - \text{committed offset}
\]

Committed offset là vị trí tiếp theo mà consumer group sẽ đọc sau khi khởi động hoặc nhận lại partition. Log end offset (LEO) là vị trí cuối của log partition theo cách công cụ đo đang sử dụng.

Ví dụ:

| Topic partition | Committed offset | Log end offset | Lag |
| --- | ---: | ---: | ---: |
| orders-0 | 1.200 | 1.250 | 50 |
| orders-1 | 980 | 1.020 | 40 |
| orders-2 | 2.010 | 2.010 | 0 |
| orders-3 | 700 | 850 | 150 |
| **Tổng** |  |  | **240** |

Lag 240 nghĩa là group còn cách đầu log 240 offset theo tổng các partition. Nó không nhất thiết tương đương 240 event nghiệp vụ chưa xử lý trong mọi trường hợp: log compaction, transaction visibility, offset gap và cách công cụ lấy end offset có thể ảnh hưởng cách diễn giải.

Lag cũng không trực tiếp cho biết record cũ nhất đã chờ bao lâu. Một partition có lag 20 nhưng traffic thấp có thể chứa event cũ hơn partition có lag 2.000 đang được xử lý rất nhanh. Hãy theo dõi cả lag, tốc độ tăng/giảm và tuổi của record cũ nhất.

## 2. Consumer đang chạy không đồng nghĩa đang tiến triển

Cần phân biệt bốn trạng thái:

- **Process alive:** JVM và ứng dụng chưa dừng.
- **Consumer member active:** consumer còn tham gia consumer group.
- **Consumer polling:** consumer tiếp tục gọi poll và giữ liveness theo cơ chế Kafka client.
- **Processing progress:** listener hoàn thành record và offset được xác nhận tiến lên.

Một consumer có thể alive, heartbeat vẫn chạy và group ở trạng thái Stable nhưng listener đang block vô thời hạn. Một consumer khác có thể nhận record và xử lý xong nhưng không acknowledge/commit offset, khiến lag theo committed offset vẫn tăng.

Vì vậy, health endpoint trả UP hoặc log startup thành công không đủ để kết luận consumer khỏe. Cần một tín hiệu tiến triển, chẳng hạn thời điểm xử lý thành công gần nhất, committed offset progression hoặc tốc độ record hoàn tất.

## 3. Phân biệt lag tăng, lag cao và lag không đổi

Ba tình huống này dẫn tới hướng điều tra khác nhau:

| Quan sát | Ý nghĩa có thể có | Hướng kiểm tra |
| --- | --- | --- |
| Lag cao nhưng đang giảm | Consumer đang bắt kịp backlog cũ | Tính thời gian catch-up và theo dõi xu hướng |
| Lag thấp nhưng tăng liên tục | Tốc độ xử lý thấp hơn tốc độ đến | So sánh arrival rate và processing rate |
| Lag cao và gần như không đổi | Consumer có thể đang xử lý ngang tốc độ producer, hoặc bị kẹt ở một điểm | Kiểm tra lag từng partition và oldest record age |
| Lag bằng 0 nhưng event vẫn chậm | Có thể đo sai group/topic, commit sớm hoặc event chưa tới partition | Kiểm tra group ID, offset commit và producer timestamp |
| Lag nhảy lên rồi giảm nhanh | Producer burst, rebalance hoặc metric sampling | Đối chiếu thời gian và event rate |

Đừng đặt alert chỉ dựa trên một ngưỡng lag tuyệt đối. Một topic có traffic lớn có thể thường xuyên có lag hàng nghìn offset nhưng vẫn có độ trễ thấp; một topic ít traffic có lag 30 nhưng event đã chờ nhiều phút.

## 4. Bắt đầu bằng lag theo từng partition

Dùng công cụ consumer group để xem committed offset, log end offset và lag:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
~~~

Đọc các cột `CURRENT-OFFSET`, `LOG-END-OFFSET` và `LAG`. Ghi lại output tại nhiều thời điểm để biết partition nào tăng và tăng nhanh bao nhiêu.

Có thể xem trạng thái group và member nếu Kafka distribution hỗ trợ các tùy chọn tương ứng:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service \
  --state

kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service \
  --members \
  --verbose
~~~

Tên option và định dạng output có thể khác theo Kafka version/distribution. Chạy `--help` trên đúng bản CLI được triển khai. Không dùng lệnh reset offset như bước chẩn đoán đầu tiên.

Tập trung vào partition có lag tăng nhanh nhất. Nếu tất cả partition tăng tương tự, vấn đề có thể là tổng capacity. Nếu chỉ một vài partition tăng, hãy kiểm tra key distribution, partition assignment và record cụ thể đang chặn tiến độ.

## 5. Đo tốc độ đi vào và tốc độ xử lý

Lag tăng khi tốc độ record mới đi vào cao hơn tốc độ consumer hoàn tất và xác nhận offset trong cùng khoảng thời gian.

Gọi:

- \(\lambda\): tốc độ record được ghi vào topic, tính bằng record/giây.
- \(\mu\): tốc độ record consumer hoàn tất và xác nhận, tính bằng record/giây.
- \(L\): backlog hiện tại, tính bằng offset hoặc record tương đương trong phạm vi đo.

Xấp xỉ:

\[
\frac{dL}{dt} = \lambda - \mu
\]

Nếu \(\lambda > \mu\), lag tăng. Nếu \(\mu > \lambda\), consumer có thể giảm backlog. Khi backlog là \(L\) và tốc độ xử lý duy trì cao hơn tốc độ đến, thời gian catch-up xấp xỉ:

\[
T_{\text{catch-up}} = \frac{L}{\mu-\lambda}
\]

Ví dụ: backlog 60.000 record, producer ghi 800 record/giây, consumer xác nhận 1.000 record/giây. Consumer chỉ có capacity dư 200 record/giây, nên cần khoảng 300 giây để bắt kịp nếu traffic ổn định.

Công thức chỉ là ước lượng. Thực tế còn phụ thuộc phân bố partition, burst, retry, rebalance, batch size, record size và downstream. Tính theo từng partition khi traffic bị lệch.

## 6. Kiểm tra group ID và đúng consumer group

Một lỗi vận hành đơn giản là quan sát nhầm group. Ứng dụng có thể chạy với group ID khác profile hoặc environment, trong khi dashboard đang theo dõi group cũ.

Kiểm tra:

- `spring.kafka.consumer.group-id` trong cấu hình runtime.
- `groupId` trên `@KafkaListener`, nếu annotation override group mặc định.
- Profile Spring Boot đang được kích hoạt.
- Environment variable hoặc ConfigMap/secret override.
- Consumer group thực tế trong output của `kafka-consumer-groups.sh`.
- Có consumer cũ hoặc job phụ dùng cùng group hay không.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
~~~

Nếu `@KafkaListener(groupId = "order-service-v2")` được khai báo, hãy kiểm tra group thực tế tương ứng. Một dashboard hiển thị lag thấp của group A không chứng minh group B đang tiêu thụ tốt.

Không đổi group ID chỉ để làm lag về 0. Group mới có thể bắt đầu từ offset khác theo `auto.offset.reset`, tạo replay hoặc bỏ qua dữ liệu tùy cấu hình và trạng thái offset.

## 7. Kiểm tra consumer group state, assignment và rebalance

Group state Stable chỉ cho biết membership/assignment hiện tại đã ổn định tại thời điểm quan sát. Nó không chứng minh listener xử lý nhanh hoặc offset đang tiến.

Kiểm tra:

- Số member đang tham gia group.
- Số partition được assign cho từng member.
- Partition có bị unassigned hay không.
- Rebalance có diễn ra liên tục không.
- Member nào có poll interval hoặc processing duration bất thường.
- Có consumer instance khởi động/dừng liên tục không.

Rebalance thường xuyên có thể làm giảm throughput vì consumer phải revoke/assign partition, hoàn tất hoặc hủy công việc đang xử lý và thiết lập lại fetch state. Nếu lag tăng theo từng đợt cùng rebalance, điều tra nguyên nhân membership trước khi tăng số consumer.

Các nguyên nhân thường gặp gồm vượt `max.poll.interval.ms`, session timeout, deploy/restart liên tục, network interruption và thay đổi membership.

## 8. Listener xử lý chậm hoặc bị block

Listener chạy đồng bộ trên consumer thread. Nếu listener chờ HTTP, database, Redis, lock hoặc future quá lâu, consumer không thể tiếp tục poll theo nhịp cần thiết.

Ví dụ:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderEvent event) {
    inventoryClient.reserve(event);
    billingClient.createInvoice(event);
    orderRepository.updateStatus(event.orderId(), "PROCESSED");
}
~~~

Ba thao tác đồng bộ nối tiếp có thể khiến một record mất nhiều thời gian. Nếu một dependency timeout dài hoặc không có timeout, lag sẽ tăng dù JVM vẫn sống.

Đo thời gian riêng cho:

- Tổng listener invocation.
- HTTP request từng dependency.
- Database query và thời gian chờ connection.
- Lock/semaphore wait.
- Serialization/deserialization.
- Thời gian ghi output event.
- Thời gian xử lý batch.

Đặt timeout cho connect/read/request, query và connection acquisition. Tránh `Thread.sleep`, `Future.get` hoặc vòng lặp retry thủ công trong listener.

## 9. max.poll.interval.ms và consumer không poll kịp

`max.poll.interval.ms` giới hạn khoảng thời gian tối đa giữa các lần `poll()` của consumer group member. Nếu listener xử lý lâu khiến consumer thread không quay lại poll, member có thể bị xem là không còn tiến triển và partition được giao cho consumer khác.

Heartbeat vẫn có thể chạy trên luồng nền ở Kafka client hiện đại, nên chỉ nhìn heartbeat không đủ để phát hiện listener bị block. Poll progress và listener duration cần được theo dõi riêng.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
~~~

Giảm `max.poll.records` có thể giảm lượng công việc trong một poll và thời gian xử lý batch. Tăng `max.poll.interval.ms` chỉ phù hợp khi workload có thời gian xử lý dài nhưng hữu hạn và đã đo được. Không tăng giá trị này để che một dependency có thể treo vô thời hạn.

## 10. Batch size và thời gian xử lý một poll

Với record listener, container có thể dispatch nhiều record từ poll trước khi consumer poll tiếp. Với batch listener, một invocation có thể xử lý cả batch. Vì vậy, thời gian của một poll cycle có thể lớn hơn thời gian xử lý một record.

Ví dụ:

| Tham số | Giá trị |
| --- | ---: |
| `max.poll.records` | 200 |
| Thời gian xử lý trung bình mỗi record | 25 ms |
| Thời gian xử lý gần đúng nếu tuần tự | 5 giây |
| Overhead | serialization, dispatch, commit, scheduling |

Nếu record size lớn hoặc thời gian xử lý có tail latency cao, batch lớn có thể khiến memory tăng và poll cycle kéo dài. Giảm batch size có thể cải thiện liveness nhưng tăng số lần poll và overhead. Đo trước/sau khi thay đổi.

Batch listener cần được kiểm tra riêng: một record lỗi có thể làm retry hoặc rollback phạm vi batch tùy error handler và cấu hình. Một poison record có thể khiến nhiều record khác bị xử lý lại.

## 11. Partition skew và hot partition

Kafka chỉ cho phép một consumer group member sở hữu một partition tại một thời điểm. Nếu key distribution không đều, một partition có thể nhận phần lớn traffic trong khi các partition khác gần như rỗng.

Ví dụ:

| Partition | Tốc độ đến | Tốc độ xử lý | Lag trend |
| --- | ---: | ---: | --- |
| orders-0 | 100/s | 120/s | Giảm |
| orders-1 | 900/s | 250/s | Tăng nhanh |
| orders-2 | 80/s | 100/s | Giảm |
| orders-3 | 90/s | 110/s | Giảm |

Tổng thể có thể vẫn có consumer capacity nhàn rỗi nhưng partition 1 tiếp tục tăng lag. Thêm consumer không giúp nếu partition nóng vẫn chỉ được assign cho một member và thứ tự theo partition phải được giữ.

Kiểm tra key producer, partitioner, số lượng key phổ biến và kích thước record. Một key có tần suất quá cao có thể tạo hot partition. Thay đổi partition key hoặc tăng partition count cần cân nhắc ordering, key affinity và thay đổi mapping của key hiện hữu.

## 12. Concurrency không thể vượt giới hạn partition

Spring Kafka có thể đặt concurrency trên listener container:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    return factory;
}
~~~

Trong một consumer group, số consumer active hữu ích không thể vượt số partition được assign. Nếu topic có 4 partition và concurrency là 12, tối đa 4 consumer có partition để xử lý; các child consumer còn lại có thể idle.

Tăng concurrency có thể tăng throughput khi có partition đủ và downstream còn capacity. Nó không làm một partition được xử lý song song theo thứ tự. Nếu listener bị block ở database pool, tăng concurrency có thể làm pool quá tải hơn và lag tăng nhanh hơn.

Kiểm tra số partition, số member, assignment và downstream capacity trước khi scale.

## 13. Offset không commit dù listener đã xử lý xong

Lag phổ biến được tính từ committed offset, không chỉ từ số record listener đã chạy. Nếu listener hoàn tất nhưng offset không được xác nhận, lag có thể tiếp tục hiển thị cao.

Kiểm tra AckMode và acknowledgment:

| Cấu hình | Hành vi cần xác minh |
| --- | --- |
| `RECORD` | Offset được xác nhận sau khi từng record listener hoàn tất thành công. |
| `BATCH` | Offset được xác nhận theo batch poll khi batch hoàn tất. |
| `MANUAL` | Listener phải gọi acknowledge theo logic ứng dụng. |
| `MANUAL_IMMEDIATE` | Acknowledge có thể commit ngay khi được gọi trên consumer thread, tùy container configuration. |

Với manual acknowledgment, kiểm tra mọi nhánh code: success, exception, early return, timeout và asynchronous completion. Nếu một nhánh quên acknowledge, committed offset có thể đứng yên dù log cho thấy business method đã chạy.

Trong Spring Kafka, container thường quản lý commit offset; không bật Kafka client auto commit một cách tùy tiện. Dùng cấu hình cùng semantics với production khi kiểm tra lag.

## 14. Async handoff và offset commit quá sớm

Mẫu dễ gây hiểu nhầm:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(OrderEvent event) {
    executor.execute(() -> orderService.process(event));
}
~~~

Listener return ngay sau khi enqueue. Với acknowledgment thông thường, container có thể commit offset trước khi worker hoàn tất. Khi đó lag có thể giảm dù công việc thực tế chưa xong; nếu process crash, task trong RAM có thể mất.

Ngược lại, nếu dùng async acknowledgment nhưng một task không hoàn tất hoặc offset được acknowledge sai thứ tự, committed offset có thể bị giữ lại và lag tăng.

Chỉ offload khi có contract rõ ràng:

- Async listener return type được Spring Kafka version hỗ trợ.
- Manual/async acknowledgment đúng container configuration.
- Durable handoff vào database/outbox/work topic trước khi xác nhận input.
- Worker idempotent theo event ID và có recovery sau restart.

Không coi queue RAM là nơi lưu trữ bền vững.

## 15. Retry và backoff làm lag tăng

Blocking retry giữ partition/consumer xử lý record lỗi trước khi tiến tới record tiếp theo theo policy. Nếu downstream đang lỗi và mỗi record bị retry nhiều lần với backoff dài, throughput hữu ích giảm mạnh.

Ví dụ `FixedBackOff(5000, 3)` có thể tạo nhiều giây chờ cho một record trước khi recovery, tùy số lần retry và version semantics. Nhiều record liên tiếp gặp lỗi sẽ làm lag tăng nhanh.

Kiểm tra:

- Retry count theo topic và exception class.
- Backoff interval và số lần thử.
- Tỷ lệ record recover thành công.
- Thời gian DLT publish.
- Poison record có lặp lại ở cùng partition không.
- Có retry lồng nhau ở HTTP client, service và Kafka handler không.

Phân loại exception. Lỗi tạm thời cần retry hữu hạn; lỗi dữ liệu vĩnh viễn nên được recover sang DLT theo policy. Không retry vô hạn một poison record vì nó có thể chặn tiến độ partition.

## 16. Retry topic và DLT ảnh hưởng cách đọc lag

Non-blocking retry topic chuyển record lỗi sang topic retry để partition nguồn có thể tiếp tục xử lý record sau. Khi đó lag ở topic nguồn có thể giảm trong khi record vẫn đang chờ ở retry topic.

Vì vậy, dashboard chỉ theo dõi topic nguồn có thể báo khỏe dù backlog thực tế đã chuyển sang retry topic. Theo dõi lag và oldest record age trên cả retry topics và DLT, cùng số record đang chờ recovery.

Với retry topic, ordering có thể thay đổi: event sau có thể được xử lý trước event đang chờ retry. Nếu nghiệp vụ cần ordering theo aggregate, cần thiết kế sequence/version hoặc giữ xử lý tuần tự thích hợp.

DLT không nên được xem là nơi lưu trữ vô thời hạn mà không có owner. Theo dõi DLT arrival rate, age, replay status và quy trình xử lý.

## 17. Consumer pause hoặc backpressure đang được kích hoạt

Listener container có thể được pause khi queue nội bộ đầy hoặc downstream không sẵn sàng. Process vẫn chạy và consumer có thể tiếp tục poll để giữ membership, nhưng partition đang pause không cấp record mới cho listener.

Kiểm tra:

- `isPauseRequested()` và `isConsumerPaused()`.
- Lý do pause đang hoạt động.
- Thời điểm pause và thời lượng pause.
- Queue depth, capacity và số task in-flight.
- High/low watermark.
- Có component nào gọi resume quá sớm hoặc pause liên tục không.

Nếu pause lâu, lag tăng là hành vi dự kiến. Hãy xử lý nguyên nhân làm queue không drain hoặc dependency chưa phục hồi. Không resume cưỡng bức chỉ để làm metric lag giảm nếu downstream vẫn quá tải.

## 18. Deserialization hoặc listener error bị lặp lại

Record không deserialize được có thể thất bại trước khi listener method được gọi. Nếu error handling chưa cấu hình đúng, record lỗi có thể bị retry hoặc làm partition không tiến triển.

Kiểm tra:

- `ErrorHandlingDeserializer` và delegate deserializer.
- Schema/JSON version producer gửi.
- Key và value deserialization failure.
- Exception header và DLT payload raw bytes.
- `DefaultErrorHandler` hoặc `AfterRollbackProcessor` tương ứng container.
- Log theo topic, partition và offset.

Nếu listener invocation count không tăng nhưng lag đứng ở cùng offset, điều tra deserialization và container error handling. Không chỉ tìm log từ business listener vì listener có thể chưa bao giờ nhận được object.

## 19. Broker, network và fetch throughput

Consumer có thể chạy bình thường nhưng fetch record chậm do broker hoặc network. Điều tra:

- Broker request latency và request queue.
- Disk I/O, page cache và network throughput.
- Under-replicated partitions và ISR changes.
- Broker availability và leader movement.
- Network packet loss, DNS, TLS handshake/reconnect.
- Consumer fetch throttling do quota.
- `fetch.min.bytes`, `fetch.max.wait.ms`, `max.partition.fetch.bytes` và `fetch.max.bytes`.
- Record size lớn hoặc compression/decompression cost.

Không tăng fetch size theo cảm tính. Fetch setting quá thấp có thể làm throughput giảm; quá cao có thể làm memory pressure tăng. Đo bytes consumed rate, fetch latency, fetch rate và broker metrics trước khi điều chỉnh.

Nếu mọi consumer của nhiều group cùng chậm trên một broker/topic, nghiêng về broker/network hoặc producer burst hơn là lỗi riêng listener.

## 20. CPU, garbage collection và memory pressure

Listener có thể chậm do CPU-bound serialization, compression, validation hoặc business logic. JVM cũng có thể pause do garbage collection hoặc allocation rate cao.

Kiểm tra:

- CPU utilization và throttling của container.
- Heap usage, allocation rate và GC pause.
- Thread count và context switching.
- Thread dump của consumer thread.
- Object size của payload và batch.
- Serialization/deserialization CPU.
- Queue và in-flight object count.

CPU thấp cùng lag cao thường gợi ý I/O wait, lock hoặc dependency pool; CPU cao cùng listener duration cao có thể gợi ý CPU-bound processing. GC pause dài có thể tạo các đợt poll delay và rebalance.

Dùng profiler hoặc Java Flight Recorder khi cần. Không tăng heap hoặc thread pool trước khi xác định allocation và bottleneck.

## 21. Transactional consumer và read_committed

Với consumer cấu hình `isolation.level=read_committed`, Kafka chỉ cung cấp record thuộc transaction đã commit và không cho consumer đọc vượt qua Last Stable Offset (LSO) của partition khi có transaction đang mở.

Do đó, với topic có transactional producer, raw log end offset và vị trí consumer có thể khác cách hiển thị lag của công cụ. Một transaction mở lâu hoặc producer transaction bị treo có thể giữ LSO, khiến record phía sau chưa visible cho read_committed consumer dù broker đã nhận thêm dữ liệu.

Kiểm tra:

- Producer transaction commit/abort rate.
- Transaction duration và timeout.
- Producer fencing hoặc transactional ID collision.
- Transaction đang mở lâu trên partition.
- Consumer isolation level.
- LEO, high watermark và LSO theo công cụ broker phù hợp.

Không kết luận listener chậm chỉ từ LEO khi workload dùng transaction. Xác định consumer đang bị giới hạn bởi LSO hay thực sự không xử lý các record đã visible.

## 22. Producer tăng tốc hoặc tạo burst

Lag có thể tăng dù consumer giữ nguyên năng lực vì producer đột ngột tăng traffic. Một đợt batch import, retry storm từ upstream hoặc nhiều producer mới có thể làm arrival rate vượt processing rate.

Đối chiếu:

- Producer records/sec và bytes/sec.
- Số producer instance.
- Batch job hoặc replay job mới chạy.
- Kích thước record thay đổi.
- Retry ở upstream.
- Phân phối key và partition.
- Thời điểm lag bắt đầu tăng.

Nếu consumer rate không đổi nhưng producer rate tăng gấp đôi, vấn đề có thể là capacity planning hoặc producer burst. Cần quyết định scale consumer/partition, giới hạn producer hoặc điều tiết traffic theo SLA.

Đừng chỉ scale consumer nếu partition nóng hoặc downstream đã đạt giới hạn.

## 23. Metric cần theo dõi

Theo dõi đồng thời metric consumer, listener và downstream:

| Nhóm | Metric gợi ý | Câu hỏi cần trả lời |
| --- | --- | --- |
| Lag | Lag theo group/topic/partition, oldest record age | Backlog ở đâu và chờ bao lâu? |
| Poll | Time between poll, last poll age, poll rate | Consumer có tiếp tục poll không? |
| Processing | Listener duration p50/p95/p99, records processed rate | Listener xử lý nhanh đến đâu? |
| Fetch | Records/bytes consumed rate, fetch latency/rate | Consumer lấy dữ liệu từ broker có nhanh không? |
| Group | Assigned partitions, rebalance rate, failed rebalance | Assignment có ổn định không? |
| Commit | Commit rate, commit latency, commit failures | Offset có tiến lên không? |
| Retry | Delivery attempts, backoff time, DLT rate | Bao nhiêu thời gian bị tiêu tốn cho lỗi? |
| Downstream | HTTP latency, DB query/pool wait, error rate | Dependency nào làm listener chậm? |
| Runtime | CPU, GC pause, heap, thread state | JVM có bị nghẽn không? |

Kafka client cung cấp nhiều metric qua JMX. Tên metric cụ thể và tag có thể thay đổi theo Kafka client version; kiểm tra metric catalog của runtime thay vì hard-code dashboard dựa trên một version khác.

Một số metric Kafka consumer thường hữu ích khi điều tra gồm `records-consumed-rate`, `records-lag-max`, `fetch-rate`, `fetch-latency-avg`, `time-between-poll-avg`, `time-between-poll-max`, `last-poll-seconds-ago`, `assigned-partitions`, `rebalance-rate-per-hour` và `commit-latency-avg`. Tên metric và MBean group có thể thay đổi theo Kafka client version; xác minh trong JMX runtime trước khi tạo alert.

Spring Kafka có thể tích hợp Micrometer để quan sát listener và Kafka client. Dùng listener ID, group ID, client ID và topic làm dimension có kiểm soát. Tránh đưa event ID hoặc offset vào metric label vì cardinality rất cao.

## 24. Runbook chẩn đoán theo thứ tự

Khi alert lag tăng, đi theo trình tự:

~~~mermaid
flowchart TD
    A[Lag alert] --> B[Verify group and topic]
    B --> C[Compare lag per partition]
    C --> D[Measure arrival and commit rates]
    D --> E[Check assignment and poll progress]
    E --> F[Inspect listener and downstream]
    F --> G[Check ack, retry, pause and broker]
    G --> H[Apply targeted change]
    H --> I[Verify lag and record age recover]
~~~

1. **Xác nhận đúng group/topic:** kiểm tra group ID runtime và topic đang được theo dõi.
2. **Xem lag từng partition:** xác định tất cả partition hay chỉ một vài partition tăng.
3. **Đo tốc độ:** so sánh records in/sec với records processed/committed per second.
4. **Kiểm tra group:** state, member, assignment và rebalance rate.
5. **Kiểm tra poll progress:** last poll, time between poll và `max.poll.interval.ms`.
6. **Kiểm tra listener duration:** tìm HTTP/DB/lock wait, CPU và batch quá lớn.
7. **Kiểm tra offset:** AckMode, manual ack, commit failure và async completion.
8. **Kiểm tra retry/recovery:** retry attempts, backoff, DLT và deserialization failure.
9. **Kiểm tra pause/backpressure:** pause reason, queue depth và worker capacity.
10. **Kiểm tra broker/network:** fetch latency, quota, broker health và traffic.
11. **Chọn hành động có kiểm soát:** giảm batch, sửa dependency, scale phù hợp hoặc điều tiết producer.
12. **Theo dõi catch-up:** xác nhận lag giảm và oldest record age trở về SLA.

Ghi lại timestamp, partition, committed offset, end offset, listener duration và event rate trước khi thay đổi cấu hình. Điều đó giúp so sánh tác động của mỗi hành động.

## 25. Chọn biện pháp khắc phục theo nguyên nhân

| Nguyên nhân | Biện pháp ưu tiên | Điều cần tránh |
| --- | --- | --- |
| Listener gọi HTTP/DB chậm | Timeout, tối ưu query, bulkhead, pool phù hợp | Tăng concurrency vô hạn |
| Batch/poll cycle quá dài | Giảm `max.poll.records`, tối ưu batch | Chỉ tăng max poll interval |
| Không đủ partition song song | Đánh giá partition/key design | Tăng consumer vượt partition |
| Hot partition | Sửa key distribution hoặc xử lý key nóng | Chỉ thêm consumer |
| Retry/backoff quá nhiều | Phân loại exception, giới hạn retry, DLT | Retry vô hạn |
| Offset không commit | Sửa AckMode/manual ack/commit failure | Reset offset để che metric |
| Consumer bị pause | Xử lý queue/downstream và pause reason | Resume cưỡng bức |
| Broker/network chậm | Điều tra broker, fetch và quota | Tăng fetch size tùy tiện |
| Producer burst | Rate limit, batch, capacity plan | Scale consumer mà không kiểm tra downstream |
| JVM/CPU/GC | Profile, giảm allocation và tối ưu code | Thêm thread khi CPU đã bão hòa |

Sau khi sửa, theo dõi lag trend và record age trong ít nhất một khoảng đủ đại diện cho traffic bình thường và peak. Một lần lag giảm ngắn hạn chưa chứng minh nguyên nhân đã được giải quyết.

## 26. Không reset offset để làm lag về 0

`--reset-offsets` có thể bỏ qua dữ liệu hoặc phát lại dữ liệu tùy lựa chọn reset. Đây là thao tác thay đổi vị trí đọc của consumer group, không phải biện pháp tăng throughput.

Chỉ reset khi có quyết định nghiệp vụ rõ ràng về việc bỏ qua hoặc replay dữ liệu, đã xác định group/topic/partition và có kế hoạch xử lý duplicate. Với production, cần lưu offset hiện tại, xác định phạm vi tác động, dừng consumer theo quy trình phù hợp và có phê duyệt vận hành.

Nếu lag tăng vì listener bị block hoặc offset không commit, reset offset chỉ che triệu chứng và có thể làm mất dữ liệu cần xử lý.

## 27. Checklist phòng ngừa lag tăng

Trước khi đưa consumer vào production, xác nhận:

1. Dashboard hiển thị lag và oldest record age theo partition.
2. Có metric records in/sec và records processed/committed per second.
3. Consumer group ID runtime được quan sát rõ ràng.
4. Có cảnh báo rebalance và poll interval bất thường.
5. Listener có timeout/deadline cho mọi dependency I/O.
6. `max.poll.records` phù hợp thời gian xử lý record/batch.
7. `max.poll.interval.ms` có biên an toàn dựa trên workload đã đo.
8. Concurrency phù hợp số partition và capacity downstream.
9. Partition key không tạo hot partition kéo dài.
10. AckMode và manual acknowledgment có integration test.
11. Retry hữu hạn, exception classification rõ và DLT được theo dõi.
12. Deserialization failure có đường recovery.
13. Async handoff có acknowledgment đúng hoặc durable queue.
14. Pause/backpressure có high/low watermark và pause reason.
15. Broker/network/fetch metrics được giám sát.
16. Có runbook xác định partition và member gây lag.
17. Không dùng reset offset như thao tác chữa cháy mặc định.

Lag tăng dù consumer đang chạy thường có nghĩa tốc độ xử lý và xác nhận offset không theo kịp tốc độ dữ liệu đến, hoặc consumer bị giới hạn bởi partition, retry, commit, broker hay downstream. Bắt đầu bằng lag từng partition, group assignment và tốc độ records vào/ra; sau đó kiểm tra poll progress, listener duration, acknowledgment và dependency. Chỉ scale hoặc thay offset sau khi đã xác định bottleneck và hiểu tác động tới ordering, duplicate và dữ liệu cần xử lý.

