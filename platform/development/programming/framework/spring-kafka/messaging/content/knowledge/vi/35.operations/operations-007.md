# Xử lý consumer bị stuck trong Spring Kafka

Consumer bị stuck là tình trạng một consumer group không tiếp tục xử lý record như kỳ vọng. Biểu hiện thường gặp là consumer lag tăng, offset không tiến triển, listener không còn log xử lý, một partition bị đứng lâu hoặc consumer liên tục rebalance. Tuy nhiên, lag tăng không phải lúc nào cũng có nghĩa consumer bị treo: topic có thể đang nhận record nhanh hơn tốc độ xử lý, consumer có thể chưa được assign partition, hoặc listener đang retry một record lỗi.

Muốn xử lý đúng, cần xác định consumer đang ở trạng thái nào: không có partition assignment, không poll Kafka, đang poll nhưng listener bị block, đang retry, đã xử lý nhưng chưa commit offset, hay đơn giản là không có record mới. Restart consumer trước khi thu thập bằng chứng có thể làm mất dấu nguyên nhân và gây redelivery.

## 1. Hiểu các kiểu consumer stuck

Không có một nguyên nhân duy nhất cho hiện tượng “consumer đứng”. Hãy phân loại theo dấu hiệu:

| Hiện tượng | Điều có thể đang xảy ra |
|---|---|
| Consumer không có partition assignment | Sai group ID, subscription, rebalance chưa ổn định, topic không có partition phù hợp hoặc concurrency lớn hơn số partition |
| Container stopped | Listener chưa auto-start, bị stop qua registry hoặc ứng dụng chưa hoàn tất startup |
| Container paused | Pause được yêu cầu có chủ đích hoặc chưa được resume |
| Consumer poll được nhưng listener không hoàn tất | Business code bị block, deadlock, gọi HTTP/database không timeout hoặc xử lý quá lâu |
| Offset không tăng nhưng listener vẫn chạy | Record đang retry, listener đang xử lý một record lâu, manual ack chưa được gọi hoặc commit thất bại |
| Consumer liên tục rebalance | Poll interval/heartbeat vi phạm, network chập chờn, instance restart hoặc membership thay đổi |
| Listener không có log nhưng consumer vẫn lỗi | Deserialization, authentication, authorization hoặc lỗi xảy ra trước khi method listener được gọi |
| Lag bằng 0 và không có record mới | Consumer có thể đang idle bình thường, không phải stuck |

Trước tiên hãy xác định `group.id`, topic, partition, offset và thời điểm cuối cùng có tiến triển. Không kết luận từ một dòng log hoặc một lần xem lag.

## 2. Phân biệt consumer idle, lag và stuck

Ba trạng thái này khác nhau:

- **Idle:** consumer đang hoạt động và không có record mới để xử lý.
- **Lagging:** record mới được ghi nhanh hơn tốc độ consumer xử lý; lag tăng hoặc duy trì ở mức cao.
- **Stuck:** consumer không tạo tiến triển dù còn record cần xử lý, hoặc container/consumer không hoạt động như cấu hình.

Ví dụ:

| Log end offset | Consumer committed offset | Lag | Diễn giải |
|---:|---:|---:|---|
| 100 | 100 | 0 | Đã theo kịp; nếu không có record mới thì idle bình thường |
| 150 | 140 | 10 | Còn 10 record; cần xem tốc độ xử lý |
| 500 | 140 | 360 | Lag lớn; kiểm tra throughput và consumer health |
| 500 | 140 (không đổi lâu) | 360 | Có thể stuck, retry một record hoặc chưa commit |
| 500 (không đổi) | 500 | 0 | Không có dữ liệu mới; không phải stuck |

Lag là khoảng cách giữa log end offset và committed offset theo từng partition. Lag tăng cho biết consumer đang tụt lại, nhưng cần so sánh với tốc độ record mới được publish và tốc độ xử lý trước khi xác định lỗi.

Một partition có lag cao trong khi các partition khác bình thường có thể do key phân phối lệch, một record xử lý rất lâu hoặc một consumer thread cụ thể bị block. Hãy xem lag theo partition, không chỉ nhìn tổng lag của group.

## 3. Quy trình chẩn đoán tổng quát

Thực hiện theo thứ tự để giữ lại bằng chứng:

1. Xác định group ID, topic, listener ID, instance và partition đang bị ảnh hưởng.
2. Kiểm tra group state, member, partition assignment, current offset, log end offset và lag.
3. Kiểm tra container có running, paused hay stopped.
4. Đối chiếu log producer, consumer, retry handler, DLT và rebalance.
5. Chụp thread dump khi hiện tượng đang xảy ra.
6. Kiểm tra HTTP/database/cache/lock mà listener đang chờ.
7. Kiểm tra `max.poll.interval.ms`, `session.timeout.ms`, `max.poll.records`, AckMode và error handler.
8. Chọn cách khôi phục phù hợp; chỉ restart sau khi đã ghi nhận trạng thái cần thiết.

Nếu nhiều instance cùng bị ảnh hưởng, ưu tiên kiểm tra broker, network, authentication và downstream dùng chung. Nếu chỉ một instance hoặc một partition bị ảnh hưởng, tập trung vào thread, assignment, key distribution và record cụ thể.

## 4. Kiểm tra consumer group bằng Kafka CLI

Dùng `kafka-consumer-groups` để xem tiến độ theo partition:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-service
```

Kết quả thường có các cột:

- `TOPIC`, `PARTITION`: vị trí dữ liệu.
- `CURRENT-OFFSET`: offset consumer group đã commit.
- `LOG-END-OFFSET`: offset cuối của partition theo metadata broker.
- `LAG`: số record còn cách committed offset.
- `CONSUMER-ID`, `HOST`, `CLIENT-ID`: member đang sở hữu partition nếu có.

Có thể xem member và assignment chi tiết trên các Kafka version hỗ trợ:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
```

Tên option và định dạng output có thể khác giữa các phiên bản Kafka/distribution. Dùng đúng CLI đi cùng cluster đang vận hành.

Đọc kết quả theo từng partition:

- `CURRENT-OFFSET` không đổi trong khi `LOG-END-OFFSET` tăng: consumer không theo kịp hoặc không commit.
- Không có member/assignment: kiểm tra group state, listener startup, subscription và lỗi join group.
- Chỉ một partition có lag lớn: kiểm tra consumer sở hữu partition đó, key skew và record đang xử lý.
- Lag bằng 0: kiểm tra log end offset có tiếp tục tăng hay không trước khi gọi là stuck.

Không dùng `--reset-offsets` như bước chẩn đoán đầu tiên. Reset offset có thể bỏ qua record hoặc làm record được xử lý lại; chỉ thực hiện khi có kế hoạch nghiệp vụ, phê duyệt và phương án đối soát.

## 5. Kiểm tra ListenerContainer trong Spring Kafka

Với listener khai báo bằng `@KafkaListener`, có thể dùng `KafkaListenerEndpointRegistry` để kiểm tra container:

```java
@Service
public class ListenerDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(ListenerDiagnostics.class);

    private final KafkaListenerEndpointRegistry registry;

    public ListenerDiagnostics(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void inspect(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                    "Listener not found: " + listenerId);
        }

        log.info(
                "listener={} running={} pauseRequested={} paused={}",
                listenerId,
                container.isRunning(),
                container.isPauseRequested(),
                container.isContainerPaused());
    }
}
```

`isRunning()` cho biết trạng thái lifecycle của container, không chứng minh listener đang xử lý record. `isPauseRequested()` cho biết đã có yêu cầu pause; `isContainerPaused()` phản ánh trạng thái pause thực tế của container. Với concurrent container, trạng thái paused cần được hiểu theo toàn bộ consumer con.

Nếu `getListenerContainer()` trả về null, kiểm tra ID của annotation và thời điểm endpoint được đăng ký. Container tạo trực tiếp thành bean có thể không nằm trong registry; cần kiểm tra bean/container tương ứng theo cách ứng dụng đã khai báo.

Không expose API diagnostics này ra endpoint public mà thiếu authentication và authorization. Chỉ trả metadata cần thiết, không trả consumer config có credential.

## 6. Kiểm tra listener có bị block trong business code

Đây là một nguyên nhân phổ biến: Kafka consumer đã nhận record nhưng method listener không hoàn tất vì chờ một dependency.

Các tình huống thường gặp:

- HTTP call không có connect timeout hoặc read timeout.
- Database query chờ lock hoặc connection pool hết connection.
- Gọi service đồng bộ trong khi service đó đang quá tải.
- Chờ `Future.get()` vô thời hạn.
- Dùng `CountDownLatch.await()` hoặc semaphore không có timeout.
- Deadlock do nhiều thread giữ lock theo thứ tự khác nhau.
- Vòng lặp CPU không thoát hoặc xử lý payload quá lớn.
- Ghi file/network chậm hoặc filesystem bị treo.

Đo thời gian xử lý của listener giúp nhận diện record xử lý lâu:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service"
)
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    long startedAt = System.nanoTime();
    OrderCreated event = record.value();

    try {
        if (event == null) {
            // Tombstone: xử lý theo semantics của topic compacted.
            log.info(
                    "kafka.consume.tombstone topic={} partition={} offset={}",
                    record.topic(), record.partition(), record.offset());
            return;
        }

        orderService.process(event);
    }
    catch (RuntimeException exception) {
        log.error(
                "kafka.consume.failed topic={} partition={} offset={}",
                record.topic(), record.partition(), record.offset(), exception);
        throw exception;
    }
    finally {
        long durationMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedAt);
        log.debug(
                "kafka.consume.finished topic={} partition={} offset={} durationMs={}",
                record.topic(), record.partition(), record.offset(), durationMs);
    }
}
```

Log `finished` chỉ xuất hiện khi method thoát. Nếu thread bị block vô hạn, log này sẽ không xuất hiện; khi đó cần thread dump để xác định stack đang chờ ở đâu. Trong ứng dụng thực tế, có thể ghi thêm event ID nếu event có ID và được phép log.

Đặt timeout rõ ràng cho HTTP client, JDBC query, lock acquisition và các thao tác I/O. Timeout phải phù hợp với SLA xử lý record và ngân sách `max.poll.interval.ms`.

## 7. Chụp thread dump khi consumer đứng

Thread dump là bằng chứng quan trọng để xác định listener thread đang làm gì. Chụp khi hiện tượng đang xảy ra, tốt nhất nhiều lần cách nhau vài giây để phân biệt thread đang tiến triển với thread bị kẹt.

Trên JVM hỗ trợ `jcmd`:

```bash
jcmd <PID> Thread.print
```

Hoặc:

```bash
jstack <PID>
```

Tìm thread xử lý listener/container và đọc stack trace:

| Stack trace thường thấy | Khả năng cần kiểm tra |
|---|---|
| `SocketInputStream.read` hoặc HTTP client socket read | Downstream không phản hồi, thiếu read timeout |
| JDBC driver / connection pool wait | Query chậm, DB lock hoặc hết connection |
| `LockSupport.park`, `Object.wait`, `ReentrantLock` | Đang chờ lock/condition hoặc deadlock |
| Cùng một method nghiệp vụ lặp lại ở nhiều dump | Vòng lặp hoặc xử lý CPU-bound |
| GC/safepoint hoặc thread bị dừng lâu | Áp lực heap, allocation hoặc stop-the-world pause |
| Kafka consumer poll/fetch/coordinator code | Cần kiểm tra broker, network, group coordination và client state |

Không kết luận chỉ từ tên thread. Đọc toàn bộ stack và đối chiếu log, metric, thread state, CPU và heap. Thread dump có thể chứa dữ liệu nhạy cảm trong stack/arguments; lưu ở nơi có quyền truy cập hạn chế.

## 8. Phân biệt max.poll.interval.ms và session.timeout.ms

Hai timeout này giải quyết hai vấn đề khác nhau:

| Property | Ý nghĩa | Triệu chứng khi vi phạm |
|---|---|---|
| `max.poll.interval.ms` | Giới hạn thời gian tối đa giữa các lần `poll()` khi consumer group đang hoạt động | Consumer xử lý một poll quá lâu, không poll lại kịp và có thể rời group/rebalance |
| `session.timeout.ms` | Thời gian broker chờ heartbeat hợp lệ trước khi xem consumer là mất kết nối | Consumer không heartbeat được do process/network/GC hoặc lỗi client |
| `heartbeat.interval.ms` | Khoảng thời gian client gửi heartbeat trong classic group protocol | Cần được đặt phù hợp với session timeout và độ ổn định network |

`max.poll.interval.ms` không phải timeout cho từng câu SQL hay HTTP request. Đây là giới hạn giữa các lần poll. Nếu listener xử lý batch quá lâu trước lần poll tiếp theo, consumer có thể vượt giới hạn này dù process vẫn còn sống.

`session.timeout.ms` liên quan tới heartbeat và phát hiện member mất kết nối. Tăng session timeout không giải quyết business code đang block nhưng vẫn heartbeat; tăng max poll interval cũng không giải quyết broker/network làm heartbeat thất bại.

Hãy xác định đúng timeout xuất hiện trong log và metric trước khi thay đổi cấu hình.

## 9. Điều chỉnh max.poll.records và max.poll.interval.ms

`max.poll.records` giới hạn số record tối đa được trả về trong một lần poll. Khi listener xử lý tuần tự, batch càng lớn thì tổng thời gian xử lý trước lần poll tiếp theo càng dài.

Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[max.poll.records]": 50
        "[max.poll.interval.ms]": 300000
```

Đây chỉ là giá trị minh họa; không sao chép vào production nếu chưa đo thời gian xử lý thực tế.

Quy trình chọn cấu hình:

1. Đo p95/p99 thời gian xử lý một record.
2. Đo tổng thời gian xử lý batch lớn nhất mà listener thực sự nhận.
3. Tính cả retry, DB/HTTP timeout, GC pause và thời gian xử lý trước lần poll kế tiếp.
4. Chọn `max.poll.records` để batch nằm trong ngân sách xử lý.
5. Đặt `max.poll.interval.ms` lớn hơn thời gian xử lý dự kiến với biên an toàn hợp lý.
6. Theo dõi rebalance và lag sau khi triển khai.

Giảm `max.poll.records` giúp rút ngắn thời gian xử lý mỗi batch nhưng có thể giảm throughput do tăng số lần poll. Tăng `max.poll.interval.ms` có thể trì hoãn phát hiện consumer thực sự bị treo; không dùng nó để che một dependency không có timeout.

Nếu mỗi record có thời gian xử lý rất dài, hãy cân nhắc thiết kế lại tác vụ, chia nhỏ công việc hoặc đưa phần xử lý dài sang workflow riêng. Nếu chuyển xử lý sang thread khác, phải bảo đảm semantics acknowledgment, thứ tự partition và lifecycle không làm commit offset trước khi công việc hoàn tất.

## 10. Kiểm tra concurrency và partition assignment

Spring Kafka có thể chạy nhiều consumer con bằng `concurrency` của listener container. Nhưng số consumer hữu ích trong một group bị giới hạn bởi số partition được assign.

Ví dụ topic có 4 partition:

| Concurrency | Consumer có thể nhận partition | Diễn giải |
|---:|---|---|
| 1 | Một consumer nhận cả 4 | Một luồng xử lý |
| 2 | Mỗi consumer khoảng 2 partition | Có thể tăng song song |
| 4 | Mỗi consumer một partition | Tối đa hóa consumer song song cho topic này |
| 8 | Chỉ 4 consumer có partition; số còn lại idle | Không tăng throughput chỉ bằng cách tăng concurrency |

Nếu một consumer không có partition, không nhất thiết là stuck. Kiểm tra assignment và số partition trước. Khi tăng concurrency vượt số partition, các consumer dư có thể không nhận record.

Nếu nhiều topic được subscribe, assignment tổng thể phụ thuộc số partition của tất cả topic và chiến lược assignor. Không kết luận chỉ dựa trên partition count của một topic.

## 11. Kiểm tra pause, stop và autoStartup

Consumer có thể ngừng nhận record do thao tác lifecycle có chủ đích:

- `autoStartup=false` khiến listener không tự chạy khi context khởi tạo.
- Một service quản trị đã gọi `stop()`.
- `pause()` được dùng để backpressure nhưng không có luồng gọi `resume()`.
- Listener container bị stop trong quá trình deploy/shutdown.
- Dynamic listener chưa được đăng ký hoặc đăng ký với ID/topic khác.

Kiểm tra `isRunning()`, `isPauseRequested()` và `isContainerPaused()` qua registry. Đối chiếu audit log hoặc log quản trị để biết ai đã thay đổi trạng thái.

Nếu consumer đang pause do downstream quá tải, khắc phục dependency rồi gọi resume theo quy trình. Không resume liên tục khi hệ thống đích vẫn đang quá tải vì có thể tạo thêm lỗi và retry.

Pause giữ consumer trong group theo cơ chế container; stop đóng consumer và có thể gây rebalance. Chọn đúng thao tác theo mục tiêu vận hành.

## 12. Kiểm tra retry và error handler

Một record lỗi có thể khiến offset không tiến triển trong khi consumer đang retry:

- `DefaultErrorHandler` có thể thực hiện retry blocking theo `BackOff`.
- Retry kéo dài làm listener container dành nhiều thời gian cho cùng record.
- Backoff lớn cần được cấu hình phù hợp với poll interval.
- Sau khi hết retry, recoverer có thể gửi record sang DLT hoặc thực hiện hành động recovery khác.

Với backoff dài, Spring Kafka cung cấp `ContainerPausingBackOffHandler` để pause container trong thời gian chờ và tiếp tục poll theo cơ chế phù hợp. API và cấu hình cần đối chiếu với version Spring Kafka đang dùng.

Nếu một record poison pill liên tục thất bại, xác định exception có retry được hay không. Lỗi dữ liệu/validation thường không tự hết khi retry; nên phân loại exception và chuyển sang recovery/DLT theo policy thay vì retry vô hạn.

Không để listener catch exception rồi return bình thường nếu muốn error handler retry. Exception phải được chuyển về container theo đúng cơ chế.

## 13. Kiểm tra non-blocking retry và retry topic

Khi dùng `@RetryableTopic`, Spring Kafka chuyển record lỗi sang retry topic để xử lý sau. Consumer trên topic gốc có thể tiếp tục record tiếp theo; event bị lỗi sẽ chờ ở retry topic theo delay được cấu hình.

Nếu người vận hành chỉ quan sát topic gốc, có thể tưởng record đã mất hoặc consumer đã stuck. Cần kiểm tra:

- Retry topic tương ứng và thời gian delay.
- Consumer group đang đọc retry topic.
- Retry attempt và exception header.
- DLT khi hết attempt.
- `KafkaBackoffException` hoặc lỗi liên quan đến thời điểm xử lý retry.

Non-blocking retry thay đổi thứ tự xử lý tương đối giữa các event. Nếu nghiệp vụ yêu cầu ordering chặt theo key, cần đánh giá tác động của retry topic và cách consumer áp dụng kết quả khi event đến muộn.

## 14. Kiểm tra lỗi deserialization trước listener

Nếu payload không deserialize được, method `@KafkaListener` có thể chưa được gọi. Vì vậy, không thấy log ở đầu listener không có nghĩa Kafka không giao record.

Các nguyên nhân thường gặp:

- Producer và consumer dùng schema/serializer không tương thích.
- JSON không đúng kiểu hoặc thiếu field bắt buộc.
- Type header không hợp lệ hoặc không được tin cậy.
- Avro/Protobuf schema không tương thích.
- Payload bị hỏng hoặc vượt giới hạn.

Với Spring Kafka, `ErrorHandlingDeserializer` cho phép chuyển lỗi deserialize vào cơ chế error handling/recovery phù hợp. Kiểm tra cấu hình deserializer, log consumer client và error handler. Nếu dùng DLT, xác minh recoverer có thể xử lý record mà value chưa deserialize thành object.

Không retry vô hạn một payload hỏng mà không có thay đổi schema hoặc dữ liệu. Giữ raw bytes theo policy an toàn, ghi metadata nguồn và chuyển DLT để điều tra.

## 15. Kiểm tra commit và acknowledgment

Offset không tiến triển dù listener đã log xử lý xong có thể do commit strategy:

- `AckMode.MANUAL` nhưng code không gọi `Acknowledgment.acknowledge()`.
- `AckMode.MANUAL_IMMEDIATE` được dùng nhưng acknowledgment xảy ra không đúng thread/điều kiện hỗ trợ.
- Commit request thất bại do rebalance hoặc lỗi broker.
- Transaction bị abort nên offset không được commit như kỳ vọng.
- Với `asyncAcks`, acknowledgment đến không đúng thứ tự có thể khiến container tạm dừng giao record mới cho tới khi các offset còn thiếu được ack.

Ví dụ manual acknowledgment:

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-manual",
        containerFactory = "manualAckKafkaListenerContainerFactory"
)
public void onOrder(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.process(event);
    acknowledgment.acknowledge();
}
```

Chỉ acknowledge sau khi xử lý nghiệp vụ đã đạt điều kiện hoàn tất. Nếu ack trước rồi process thất bại, record có thể không được giao lại dù side effect chưa hoàn tất.

Đối chiếu AckMode thực tế của container factory. Không lấy ví dụ manual ack áp dụng cho listener đang dùng `RECORD`, `BATCH` hoặc Kafka transaction.

## 16. Kiểm tra downstream và tài nguyên ứng dụng

Consumer có thể vẫn hoạt động nhưng bị giới hạn bởi hệ thống phụ thuộc:

| Dependency | Dấu hiệu | Việc cần kiểm tra |
|---|---|---|
| Database | Listener chờ query/connection | Query plan, lock, pool active/idle, connection timeout |
| HTTP service | Thread chờ socket hoặc retry liên tục | Connect/read timeout, latency, circuit breaker, rate limit |
| Cache | Timeout hoặc connection pool cạn | Cluster health, pool, DNS/network |
| Thread pool | Task queue tăng, không có worker rảnh | Pool size, queue capacity, task duration, rejection |
| CPU/heap | CPU cao, GC pause dài | Thread dump, GC log, allocation và heap pressure |
| File/object storage | I/O chậm hoặc request treo | Timeout, retry policy, throughput và permission |

Đặt timeout hữu hạn ở mọi lời gọi bên ngoài listener. Kết hợp circuit breaker và bulkhead khi downstream có thể quá tải. Nếu dependency đang hỏng, pause consumer có kiểm soát hoặc để error handler xử lý theo retry policy đã thiết kế.

Không dùng thread pool không giới hạn để “giải phóng” listener. Nó có thể chuyển vấn đề thành hàng đợi task tăng vô hạn và làm cạn heap.

## 17. Kiểm tra broker, network và quyền truy cập

Nếu nhiều consumer hoặc nhiều service cùng bị ảnh hưởng, kiểm tra hạ tầng:

- Broker có online và controller/leader ổn định không.
- Partition có leader và ISR phù hợp không.
- Network có packet loss, DNS lỗi hoặc connection reset không.
- Kafka client có authentication/authorization failure không.
- ACL có cho phép topic và consumer group hiện tại không.
- Broker có request queue, disk hoặc network saturation không.
- TLS certificate có hết hạn hoặc trust chain thay đổi không.

Một consumer không thể join group hoặc fetch record do ACL/authentication thường tạo log lỗi client dù listener không có log. Kiểm tra exception và broker audit log; đừng xử lý bằng cách cấp quyền superuser tạm thời.

Nếu producer cũng không ghi được hoặc AdminClient không lấy được metadata, khả năng cao vấn đề nằm ở cluster/network/security hơn là riêng listener code.

## 18. Metrics và cảnh báo phát hiện consumer stuck

Theo dõi metric theo group, topic, partition và instance:

- Consumer lag theo partition và thời gian lag duy trì.
- `records-consumed-rate` và tốc độ record được publish.
- `records-lag-max` của Kafka consumer client nếu có.
- Fetch rate/latency và commit rate/latency.
- `poll-idle-ratio-avg` để hiểu consumer dành bao nhiêu thời gian giữa các lần poll cho xử lý.
- Số partition được assign và số member trong group.
- Listener processing duration p95/p99.
- Retry rate, DLT rate và số record đang chờ retry.
- Rebalance count, authentication failure và consumer error.

Tên metric, tag và mức hỗ trợ phụ thuộc Kafka client, Spring Kafka và metrics backend. Đối chiếu version thực tế; không giả định mọi metric đều được export sẵn.

Alert nên dựa trên tổ hợp điều kiện:

- Lag lớn hơn ngưỡng trong một khoảng thời gian và log end offset vẫn tăng.
- Committed offset không đổi trong khi có record mới.
- Listener processing duration vượt SLA.
- Rebalance lặp lại hoặc consumer liên tục rời group.
- Consumer có assignment nhưng không có record consumed trong khi lag còn dương.
- Retry/DLT rate tăng bất thường.

Không alert chỉ vì consumer không có record trong một khoảng thời gian nếu lag bằng 0 và topic không có dữ liệu mới.

## 19. Khôi phục consumer an toàn

Khi đã xác định nguyên nhân, chọn mức can thiệp nhỏ nhất có thể:

1. **Downstream tạm quá tải:** giảm tải, khôi phục dependency, sau đó resume hoặc để retry tiếp tục theo policy.
2. **Listener xử lý quá lâu:** sửa timeout/logic, giảm batch hoặc điều chỉnh poll budget sau khi đo.
3. **Poison record:** phân loại exception, chuyển DLT theo policy và lưu metadata để replay có kiểm soát.
4. **Container bị pause/stop ngoài ý muốn:** xác định nguyên nhân thao tác lifecycle rồi resume/start đúng listener ID.
5. **Consumer thread deadlock hoặc process không thể phục hồi:** lưu thread dump/log/metric, dừng container có kiểm soát, xử lý nguyên nhân rồi start lại.
6. **Broker/network/authentication:** khôi phục cluster, network hoặc credential; không restart hàng loạt consumer liên tục.

Trước khi stop/restart:

- Ghi nhận group state, assignment, current offset, log end offset và lag.
- Lưu thread dump và log liên quan.
- Xác định listener có đang xử lý side effect chưa commit không.
- Xác minh consumer idempotent hoặc có khả năng chịu redelivery.
- Dừng container bằng lifecycle API/callback để có cơ hội hoàn tất xử lý và đóng consumer.

Restart có thể làm record chưa commit được giao lại. Không xóa consumer group, không reset offset và không skip record chỉ để làm lag biến mất.

## 20. Kiểm tra sau khi khôi phục

Sau khi consumer chạy lại, xác minh bằng dữ liệu thực tế:

- Container ở trạng thái running và không bị pause ngoài ý muốn.
- Consumer group có member và partition assignment mong đợi.
- Current offset tiếp tục tiến triển trên partition bị ảnh hưởng.
- Lag giảm khi tốc độ xử lý lớn hơn tốc độ publish.
- Không có rebalance loop hoặc lỗi poll interval lặp lại.
- Listener processing duration trở về trong SLA.
- Retry topic và DLT không tăng bất thường.
- Database/API downstream không bị quá tải do backlog replay.
- Business side effect không bị nhân đôi ngoài dự kiến.

Không coi việc log “consumer started” là bằng chứng sự cố đã hết. Chỉ đóng incident khi offset/lag, xử lý nghiệp vụ và dependency đều trở lại trạng thái bình thường trong khoảng theo dõi phù hợp.

## 21. Kiểm thử tình huống consumer stuck

Trong môi trường test/staging, có thể chủ động tạo các tình huống:

1. Listener xử lý lâu hơn `max.poll.interval.ms` để quan sát rebalance và redelivery.
2. Downstream HTTP chậm hoặc không phản hồi; xác minh timeout/circuit breaker hoạt động.
3. Database lock hoặc connection pool cạn; xác minh metric và thread dump chỉ ra điểm chờ.
4. Gửi poison record không deserialize được; xác minh listener/error handler/DLT xử lý đúng.
5. Dùng manual ack và cố ý không acknowledge; quan sát offset và redelivery theo cấu hình.
6. Pause container rồi resume; xác minh assignment và record processing.
7. Tăng concurrency vượt partition count; xác minh consumer dư ở trạng thái idle được hiểu đúng.
8. Restart process khi listener đang xử lý; xác minh consumer idempotent chịu được redelivery.

Dùng topic/group riêng cho mỗi test và chờ điều kiện bằng polling có timeout. Không dùng `Thread.sleep()` cố định làm bằng chứng duy nhất. Khi mô phỏng lỗi, giữ lại log, consumer group description và metric để so sánh trước/sau.

## 22. Các lỗi thường gặp

**Restart consumer ngay khi thấy lag:** làm mất thread state và có thể tạo redelivery. Thu thập group state, log và thread dump trước.

**Tăng `session.timeout.ms` để sửa listener xử lý lâu:** session timeout điều khiển heartbeat failure detection; listener không poll đúng hạn liên quan tới `max.poll.interval.ms`.

**Tăng `max.poll.interval.ms` thật lớn:** có thể che thread bị treo và kéo dài thời gian phát hiện lỗi. Đo batch duration và sửa dependency timeout.

**Tăng concurrency vượt số partition:** consumer dư không có partition không phải stuck. Kiểm tra assignment.

**Thấy log processed rồi kết luận offset đã commit:** listener completion và broker offset commit là hai mốc khác nhau.

**Retry vô hạn poison record:** dữ liệu lỗi không tự hết lỗi; phân loại exception và dùng recovery/DLT.

**Không thấy log listener nên nghĩ Kafka không giao record:** lỗi deserialization có thể xảy ra trước khi listener method được gọi.

**Unpause mà không kiểm tra downstream:** consumer nhận backlog ngay và làm dependency quá tải hơn.

**Reset offset để xóa lag:** có thể bỏ qua hoặc phát lại dữ liệu. Chỉ reset theo kế hoạch đối soát.

**Chỉ nhìn tổng lag:** một partition hoặc một consumer có thể là điểm nghẽn. Kiểm tra lag và assignment theo partition.

## 23. Checklist runbook production

- Xác định đúng cluster, group ID, topic, listener ID và instance.
- So sánh current offset, log end offset và lag theo partition.
- Kiểm tra member, assignment và group state.
- Kiểm tra container running, pause requested và paused state.
- Đối chiếu log listener, retry, DLT, rebalance và Kafka client.
- Chụp nhiều thread dump khi hiện tượng đang xảy ra.
- Kiểm tra HTTP/database/thread pool/CPU/GC và timeout của dependency.
- Phân biệt `max.poll.interval.ms` với `session.timeout.ms`.
- Kiểm tra `max.poll.records`, concurrency, partition count và AckMode.
- Kiểm tra deserialization và error handler khi listener không có log.
- Ghi nhận offset/lag trước khi stop hoặc restart.
- Không reset/skip offset nếu chưa có kế hoạch nghiệp vụ.
- Xác minh idempotency và khả năng chịu redelivery.
- Sau khôi phục, xác minh offset tiến triển, lag giảm, rebalance ổn định và downstream khỏe.
- Ghi lại nguyên nhân gốc, thời gian ảnh hưởng và biện pháp ngăn tái diễn.

Consumer bị stuck là một triệu chứng cần chẩn đoán theo nhiều lớp: group assignment, poll loop, listener thread, error handling, offset commit, downstream và broker. Hãy bắt đầu bằng lag theo partition và group state, dùng thread dump để tìm điểm block, kiểm tra poll/heartbeat timeout và chỉ can thiệp lifecycle sau khi đã lưu bằng chứng. Khôi phục thành công phải thể hiện ở offset tiếp tục tiến triển và nghiệp vụ hoàn tất an toàn, không chỉ ở việc process đã restart.

## Tài liệu tham khảo

- [Apache Kafka – Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka – Consumer Group Protocol](https://kafka.apache.org/documentation/#intro_consumers)
- [Spring for Apache Kafka – Listener Container](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka – Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
