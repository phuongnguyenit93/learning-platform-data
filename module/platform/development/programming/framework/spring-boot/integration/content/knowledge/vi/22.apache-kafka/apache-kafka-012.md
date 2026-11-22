# Rebalance, consumer lag và lỗi xử lý quá thời gian cho phép

Trong một luồng tích hợp Spring Boot dùng Apache Kafka, consumer có thể vẫn kết nối được broker, nhưng **consumer lag** tăng đều. Sau một khoảng xử lý chậm, log có thể xuất hiện rebalance, partition bị thu hồi hoặc lỗi commit offset. Consumer mới nhận partition đọc lại các bản ghi chưa commit, tạo nguy cơ xử lý trùng ở cơ sở dữ liệu hay API bên ngoài.

Ba hiện tượng liên quan nhưng cần phân biệt:

- **Rebalance**: nhóm consumer thay đổi phân công partition giữa các thành viên.
- **Consumer lag**: khoảng cách giữa vị trí cuối log của partition và tiến độ xử lý/commit theo một cách đo offset cụ thể.
- **Vượt `max.poll.interval.ms`**: consumer không gọi `poll()` tiếp trong giới hạn thời gian, có thể mất quyền sở hữu partition theo giao thức đang dùng.

Đây là nội dung chương **Apache Kafka** của mô-đun **SPRING_BOOT_INTEGRATION**. Khi tích hợp HTTP client, cơ sở dữ liệu, cache, broker và adapter Spring Integration, cần xét cùng lúc cấu hình Kafka, hợp đồng event, lỗi hạ tầng, giao dịch, xử lý trùng, kiểm thử và khả năng quan sát. Tăng timeout hoặc tăng số replica đơn lẻ chưa đủ đảm bảo dữ liệu đúng.

## 1. Các khái niệm cần hiểu trước khi xử lý sự cố

### Consumer group và partition

Giả sử topic `orders.events` có 6 partition, group `order-projection` chạy 3 consumer Spring Boot. Trong một group, một partition tại một thời điểm do một consumer nắm quyền xử lý; một consumer có thể nhận nhiều partition.

~~~mermaid
flowchart TB
    T["Topic orders.events: 6 partitions"]
    T --> P0["Partition 0"]
    T --> P1["Partition 1"]
    T --> P2["Partition 2"]
    T --> P3["Partition 3"]
    T --> P4["Partition 4"]
    T --> P5["Partition 5"]
    P0 --> A["Consumer A"]
    P1 --> A
    P2 --> B["Consumer B"]
    P3 --> B
    P4 --> C["Consumer C"]
    P5 --> C
    A --> D["Cập nhật trạng thái đơn hàng"]
    B --> D
    C --> D
~~~

Các vị trí offset dễ bị nhầm:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Log end offset (LEO)** | Offset kế tiếp sau bản ghi cuối trong partition |
| **Consumer position** | Offset kế tiếp mà consumer dự kiến đọc theo tiến độ `poll()` của client |
| **Committed offset** | Offset kế tiếp mà consumer group đã ghi nhận làm điểm tiếp tục khi tiếp quản/restart |
| **Committed lag** | Thường bằng `LEO - committed offset` theo partition, nếu offset hợp lệ |
| **Position lag** | Đo theo vị trí đọc của client, có thể khác lag theo committed offset |

Ví dụ: LEO = 12.500, committed offset = 12.200, lag theo commit là **300 records**. Nếu client đã poll tới offset 12.230 nhưng chưa commit thì position và committed offset khác nhau; hai nguồn metric có thể hiển thị lag khác nhau.

**Consumer lag đo số bản ghi, không tự động đo thời gian trễ.** SLA nghiệp vụ cần bổ sung tốc độ xử lý, độ tuổi event, timestamp đầu vào và thời điểm hoàn thành xử lý. Một lượng lag nhỏ vẫn có thể chậm nghiêm trọng nếu một bản ghi kẹt lâu.

### Lag biến động như thế nào?

Trong khoảng quan sát ổn định, có thể xấp xỉ:

~~~text
Tốc độ producer: 800 bản ghi/giây
Tốc độ consumer xử lý và commit: 600 bản ghi/giây
=> Lag tăng xấp xỉ 200 bản ghi/giây
=> Sau 5 phút backlog tăng khoảng 60.000 bản ghi
~~~

Đây là cách ước lượng xu hướng; thực tế còn phụ thuộc phân bố dữ liệu theo partition, commit theo batch, retry, rebalances và các offset đã poll nhưng chưa commit.

## 2. Rebalance xảy ra khi nào?

**Rebalance** là quá trình nhóm thay đổi phân công partition. Nó có thể xuất hiện khi:

1. Consumer gia nhập hoặc rời group do scale, rolling deploy, restart hoặc crash.
2. Member mất heartbeat/session hoặc không tiếp tục gọi `poll()` đúng hạn.
3. Số partition hoặc subscription thay đổi.
4. Consumer group đổi assignor/giao thức theo các đợt triển khai.
5. Ứng dụng liên tục lỗi và khởi động lại container tạo thành vòng lặp vào/ra group.

Trong lúc chuyển giao, một số partition có thể bị tạm dừng xử lý. Nếu consumer A đã cập nhật DB nhưng chưa commit offset, consumer B nhận lại partition có thể đọc và xử lý lại chính record đó. Vì vậy, cần thiết kế **at-least-once + idempotency** cho phần lớn luồng có tác động ra ngoài Kafka.

### Eager, cooperative và static membership

| Cơ chế | Đặc điểm | Lưu ý khi dùng |
| --- | --- | --- |
| **Eager rebalance** | Nhiều assignment bị thu hồi trước khi phân công lại | Có thể ngừng xử lý rộng hơn nhu cầu thực tế |
| **Cooperative/incremental rebalance** | Thu hồi dần các partition cần chuyển giao | Thường giảm gián đoạn, nhưng phụ thuộc phiên bản/protocol/assignor |
| **Static membership** | `group.instance.id` ổn định qua restart ngắn | Cần ID duy nhất cho mỗi member; không giải quyết listener bị treo |

Với giao thức group **classic**, cooperative rebalance có thể dùng assignor hỗ trợ như `CooperativeStickyAssignor`. Các phiên bản Kafka mới còn hỗ trợ **consumer group protocol** do broker điều phối nhiều thông số; không áp dụng máy móc mọi cấu hình classic cho giao thức này.

Static membership giúp tránh một số lần chuyển giao không cần thiết khi restart ngắn. Tuy nhiên, nếu static member vi phạm `max.poll.interval.ms`, nó có thể dừng heartbeat và partition chỉ được giao lại sau session timeout; lag vẫn có nguy cơ tăng trong thời gian đợi.

## 3. Phân biệt các timeout

| Cấu hình/cơ chế | Theo dõi điều gì? | Khi vượt |
| --- | --- | --- |
| `max.poll.interval.ms` | Khoảng cách tối đa giữa các lần ứng dụng gọi `poll()` | Member có thể bị xem là không tiến triển và mất assignment |
| `session.timeout.ms` | Khoảng thời gian thiếu heartbeat trước khi member bị xem là mất kết nối trong group classic | Coordinator có thể phân công lại partition |
| `heartbeat.interval.ms` | Tần suất heartbeat trong group classic | Dùng phối hợp với session timeout, không thay thế `poll()` |
| HTTP/DB client timeout | Thời gian một thao tác xuống hệ thống ngoài được phép chờ | Listener có thể bị chặn, hoặc nhận lỗi timeout |
| Retry backoff | Khoảng đợi giữa các lần xử lý lại | Nếu chặn consumer thread quá lâu, có thể đẩy poll vượt hạn |
| Commit timeout | Thời gian xác nhận tiến độ offset | Commit chậm hoặc thất bại có thể tăng lag theo committed offset |

Với Kafka consumer theo **classic protocol**, heartbeat có thể vẫn được gửi trên luồng nền khi listener đang xử lý. Như vậy, **heartbeat vẫn tốt nhưng `max.poll.interval.ms` vẫn bị vi phạm** nếu thread xử lý không quay về `poll()` kịp lúc.

Với `group.protocol=consumer` ở các phiên bản hỗ trợ, các tham số heartbeat/session tương ứng có thể do broker kiểm soát. Khi phân tích timeout phải kiểm tra đúng phiên bản Kafka broker, Kafka client và giao thức group, không chỉ đọc một file cấu hình.

### Tại sao một record nhanh vẫn có thể làm poll trễ?

`max.poll.interval.ms` không phải giới hạn thời gian cho **một record**. Giả sử:

- `max.poll.records = 20`.
- `max.poll.interval.ms = 300000` (5 phút).
- Mỗi record cần HTTP + DB, trong tình huống xấu mất 20 giây.
- Listener xử lý tuần tự 20 record nhận từ cùng một lần poll.

Thời gian xử lý có thể đạt `20 × 20 = 400 giây`, chưa gồm commit và retry. Lần `poll()` kế tiếp đến quá muộn.

~~~mermaid
sequenceDiagram
    participant C as Consumer thread
    participant L as Listener
    participant X as HTTP và DB
    participant G as Group coordinator
    C->>G: Nhận assignment
    C->>C: poll() trả tối đa 20 records
    loop Từng record
      C->>L: Gọi listener
      L->>X: Xử lý I/O
      X-->>L: Trả kết quả
      L-->>C: Kết thúc record
    end
    Note over C,G: Khoảng cách 2 poll lớn hơn max.poll.interval.ms
    G-->>C: Member/assignment có thể thay đổi
    C->>C: Poll/commit tiếp theo phát hiện lỗi group
~~~

Thời điểm phát hiện lỗi có thể ở heartbeat thread, lúc commit hoặc poll tiếp theo, tùy giao thức/client. Sơ đồ mô tả quan hệ nguyên nhân, không cam kết thứ tự log cụ thể. Khi dùng pause, retry, batch hoặc xử lý bất đồng bộ, cần đo đường đi thực tế của Spring Kafka container.

## 4. Phân tích consumer lag: tìm nguyên nhân thay vì đoán từ một metric

| Dấu hiệu quan sát | Nguyên nhân nghi ngờ | Cách kiểm chứng |
| --- | --- | --- |
| Lag tăng đều, ít rebalance | Throughput tiêu thụ thấp hơn đầu vào | So records in/out, CPU, thời gian xử lý p95/p99 |
| Lag nhảy trong đợt deploy | Restart/scale làm rebalance | Timeline deployment, revoked/assigned logs |
| Chỉ một partition có lag lớn | Hot key, hot partition hoặc poison pill | Phân bố key, log theo topic-partition-offset |
| CPU thấp nhưng lag cao | Đợi HTTP/DB, lock, pool connection hoặc retry | Timeout, latency downstream, thread dump |
| DB đã cập nhật nhưng lag không giảm | Offset chưa commit hoặc commit lỗi | So consumer position với committed offset |
| Cùng offset lỗi lặp lại | Poison pill hoặc retry vô hạn | Exception, retry count, deserializer, DLT |
| Lag tăng ngay sau đổi group ID | Group mới không có committed offset | Cấu hình group ID, auto-offset-reset |
| Lag thấp nhưng nghiệp vụ chậm | Trễ ở upstream hoặc nguồn chưa đưa event lên Kafka | Event age và trace end-to-end |

**Lag không chứng minh rebalance đã xảy ra**; consumer hoàn toàn ổn định vẫn tăng lag nếu API bên ngoài chậm. Ngược lại, rebalance ngắn khi không có traffic có thể không làm lag thay đổi đáng kể.

### Kiểm tra group bằng CLI

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe \
  --group order-projection
~~~

Ví dụ một phần kết quả:

~~~text
GROUP             TOPIC          PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG
order-projection  orders.events  0         12500          12520          20
order-projection  orders.events  1          8000           8500         500
order-projection  orders.events  2          9200           9200           0
~~~

Ở đây partition 1 đáng điều tra trước. **CURRENT-OFFSET** trong lệnh quản trị group là committed offset, không trực tiếp khẳng định side effect ở DB/API đã hoàn thành chính xác. Nếu group chưa có committed offset, có thể không tính được lag theo cách này.

Có thể xem trạng thái và thành viên (các cờ hỗ trợ tùy phiên bản CLI):

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe --group order-projection --state

kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe --group order-projection --members --verbose
~~~

Đối chiếu với log revoked/assigned, `CommitFailedException`, restart của pod, số member và số partition. Không reset offset trên production chỉ để làm chỉ số lag giảm; làm như vậy có thể phát lại hoặc bỏ qua dữ liệu.

### Metrics tối thiểu cần có

| Metric | Mục đích |
| --- | --- |
| Lag theo group/topic/partition, tổng và lớn nhất | Phân biệt backlog lan rộng với hot partition |
| Thời gian listener p50/p95/p99 và timeout | Biết bản ghi/đợt poll có nguy cơ vượt hạn |
| Khoảng cách giữa các lần poll, last poll | Nhận biết consumer không tiến triển |
| Số lần và thời lượng rebalance | Phát hiện churn của consumer group |
| Records consumed/committed rate | So tốc độ xử lý với tốc độ produce |
| Retry, lỗi deserialize, DLT, commit failure | Phát hiện kẹt ở một bản ghi hoặc lỗi hạ tầng |
| Latency HTTP/DB và pool saturation | Tìm nút thắt ngoài Kafka |
| Event age khi hoàn thành nghiệp vụ | Đo SLA thay vì suy đoán từ lag |

Kafka client có các metric như `records-lag-max`, `time-between-poll-max` và metric rebalance tùy phiên bản. **Metric lag ở phía client có thể đo theo consumer position**, khác với committed lag của công cụ quản trị. Khi tạo dashboard Prometheus/Micrometer, xem định nghĩa metric và nhãn theo exporter đang dùng.

Một dashboard có trục thời gian chung cho **lag + latency HTTP + listener time + rebalance count + commit errors** thường giúp thấy rõ chuỗi: API chậm → xử lý lâu → poll trễ → rebalance → commit lỗi → backlog tăng.

## 5. Cấu hình consumer Spring Boot

Ví dụ sau cho Spring Kafka listener kiểu record, sử dụng **classic group protocol**. Những giá trị timeout mang tính minh họa, không phải cấu hình tối ưu chung cho mọi hệ thống:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      enable-auto-commit: false
      max-poll-records: 20
      properties:
        "[max.poll.interval.ms]": 300000
        "[session.timeout.ms]": 45000
        "[heartbeat.interval.ms]": 15000
    listener:
      concurrency: 3
      ack-mode: record
~~~

- `max-poll-records` giới hạn **số record trả về từ một lần poll**; không phải giới hạn tổng byte fetch hoặc bộ nhớ client.
- `max.poll.interval.ms` quá nhỏ dễ gây timeout khi batch xử lý chậm, nhưng quá lớn sẽ chậm nhận ra worker thực sự treo.
- `enable-auto-commit: false` và `ack-mode: record`: với record listener, Spring Kafka container commit sau khi record được xử lý thành công; vẫn phải xét error handler/recovery.
- `concurrency: 3`: một application instance có thể tạo tối đa ba consumer con. Tính **tổng consumer của tất cả replica**; nhiều hơn số partition sẽ không cải thiện throughput của group.
- `auto-offset-reset: earliest` chỉ có tác dụng khi consumer chưa có offset hợp lệ đã commit, không tự động đọc lại toàn bộ từ đầu.
- Thời gian heartbeat/session ở trên áp dụng cho classic protocol và cần thỏa giới hạn broker; nếu dùng `group.protocol=consumer`, xác minh các tham số do broker kiểm soát.

### Listener có side effect idempotent

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

record OrderChanged(String eventId, String orderId, String status) {}

interface OrderProjector {
    void applyOnce(OrderChanged event);
}

@Service
class OrderProjectionListener {
    private final OrderProjector projector;

    OrderProjectionListener(OrderProjector projector) {
        this.projector = projector;
    }

    @KafkaListener(topics = "orders.events")
    public void onMessage(ConsumerRecord<String, OrderChanged> record) {
        // applyOnce phải atomic/idempotent ở cơ sở dữ liệu.
        projector.applyOnce(record.value());
    }
}
~~~

Ví dụ giả định consumer đã cấu hình deserializer tương ứng với `OrderChanged`. Hàm `applyOnce` là hợp đồng của tầng ứng dụng: nên lưu event ID hoặc khóa `topic-partition-offset` với unique constraint và cập nhật projection **trong cùng DB transaction**. Listener chỉ trả về sau khi transaction hoàn thành. Nếu crash sau DB commit nhưng trước Kafka commit, event đọc lại sẽ không tạo tác động lần hai.

Phải đặt HTTP/DB timeout hữu hạn, kiểm soát retry và connection pool. Một record bị kẹt nhiều phút ở HTTP vẫn đủ làm vượt `max.poll.interval.ms`, dù `max.poll.records=1`.

**Không tự ý dùng chung `KafkaConsumer` giữa các thread**: client không thread-safe. Nếu offload công việc sang worker pool để consumer thread quay lại poll nhanh, cần thiết kế hàng đợi có giới hạn, backpressure, pause/resume, commit theo **dải offset hoàn thành liên tục** trên từng partition và cơ chế thu hồi assignment. Listener trả về trước khi tác vụ bất đồng bộ hoàn thành mà container đã ack có thể khiến mất dữ liệu.

### Ước lượng giới hạn thời gian poll

~~~text
Thời gian giữa hai lần poll (ước lượng)
≈ records được trả về × thời gian xử lý xấu nhất mỗi record
  + retry + commit + scheduler/overhead

Cần giữ nhỏ hơn max.poll.interval.ms với dự phòng thực tế.
~~~

Ví dụ `max.poll.records=20`, thời gian mỗi record p99 khoảng 8 giây: tính thô 160 giây, chưa kể outlier và retry. Nếu HTTP timeout cho một record có thể là 240 giây, dùng p99 không chứng minh 20 records sẽ hoàn tất trong 300 giây. Giải pháp phải bao gồm giới hạn thời gian I/O, giảm batch, hoặc thay đổi kiến trúc tác vụ dài.

## 6. Retry, poison pill và Dead Letter Topic

Retry trên consumer thread có thể làm một chu kỳ xử lý vượt `max.poll.interval.ms`. Mặt khác, xử lý lỗi xong rồi trả về bình thường mà không đưa record tới kênh thích hợp có thể khiến container commit offset và bỏ qua dữ liệu.

| Lỗi | Ví dụ | Cách xử lý thường hợp lý |
| --- | --- | --- |
| Lỗi dữ liệu vĩnh viễn | Sai schema, thiếu trường bắt buộc | Không retry vô hạn; quarantine/DLT và cảnh báo |
| Lỗi nghiệp vụ vĩnh viễn | Trạng thái không được phép | Ghi kết quả lỗi theo miền, DLT nếu chính sách yêu cầu |
| Lỗi tạm thời | HTTP 503, DB tạm thời không truy cập | Retry giới hạn, có backoff và idempotency |
| Kết quả không chắc chắn | Timeout sau yêu cầu tạo thanh toán | Đối chiếu kết quả hoặc dùng idempotency key trước khi thử lại |
| Poison pill | Deserializer luôn fail tại cùng offset | Dùng error-handling deserializer và cơ chế xử lý record lỗi |
| Lỗi group/commit | Rebalance, generation thay đổi | Phục hồi theo cơ chế container và quan sát assignment |

Trong Spring Kafka, `DefaultErrorHandler` kết hợp `DeadLetterPublishingRecoverer` cho phép retry hữu hạn rồi chuyển record sang DLT:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

class InvalidOrderEventException extends RuntimeException {
    InvalidOrderEventException(String message) {
        super(message);
    }
}

@Configuration
class OrderKafkaErrorConfiguration {
    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var handler = new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)); // 2 retry sau lần đầu

        handler.addNotRetryableExceptions(
                InvalidOrderEventException.class);
        return handler;
    }
}
~~~

Để ví dụ hoạt động đúng cần cấu hình **producer/serializer dùng cho DLT**, topic đích có partition phù hợp, chính sách commit sau recovery và quy trình xử lý DLT. `InvalidOrderEventException` là kiểu lỗi ứng dụng chủ động ném cho dữ liệu không thể sửa bằng retry. Với lỗi giải mã xảy ra **trước khi listener nhận record**, cần `ErrorHandlingDeserializer` hoặc giải pháp tương đương để chuyển thông tin lỗi đến handler.

Backoff dài trên consumer thread cần được thiết kế cùng **poll budget**. Tùy phiên bản Spring Kafka, cân nhắc **container-pausing backoff** hoặc **retry topic/non-blocking retry** cho lỗi cần đợi lâu. Retry topic có thể làm thứ tự xử lý khác với partition gốc; cần kiểm thử yêu cầu ordering trước khi chọn. DLT không phải trạng thái nghiệp vụ thành công: phải có người/chương trình phân loại, sửa và replay có kiểm soát.

## 7. Khi rebalance gặp commit: xử lý trùng là vấn đề dữ liệu

Kịch bản sau thường gây phát sự kiện hoặc ghi DB lặp:

1. Consumer A `poll()` nhận record offset 100 của partition 0.
2. A cập nhật DB xong nhưng **chưa commit offset 101**.
3. A chậm vượt hạn poll hoặc crash, partition 0 được giao cho B.
4. B đọc từ committed offset 100 và chạy lại nghiệp vụ.
5. Nếu thao tác không idempotent, hệ thống tạo tác động lần hai.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant D as Database/API
    participant G as Kafka group
    participant B as Consumer B
    A->>A: poll offset 100
    A->>D: Cập nhật nghiệp vụ
    D-->>A: Thành công
    Note over A,G: Chưa commit offset 101
    G->>B: Rebalance, giao partition
    B->>B: Đọc lại offset 100
    B->>D: Xử lý lại
    D-->>B: Idempotency check / unique key
~~~

**Kafka offset commit và database transaction là hai việc khác nhau.** Commit trước khi DB thành công có thể mất tác động. DB thành công nhưng chưa commit offset có thể đọc lại; phải làm các tác động bên ngoài idempotent. Kafka transactions/exactly-once semantics có thể giúp một số luồng đọc–xử lý–ghi **trong Kafka**, nhưng không tự làm cho HTTP hoặc SQL bên ngoài Kafka thành exactly-once. Với nhiều tích hợp thực tế, dùng **inbox/dedup table**, outbox, idempotency key và workflow bù trừ.

Không commit offset lớn nhất đã đọc nếu các tác vụ của cùng partition trước đó chưa hoàn thành liên tục. Nếu dùng callback rebalance để flush/commit, cần xử lý đúng partition đang bị thu hồi, generation còn hợp lệ, và không giả định callback có đủ thời gian cho HTTP kéo dài.

## 8. Giảm lag mà vẫn giữ đúng dữ liệu

| Biện pháp | Hữu ích khi | Đánh đổi |
| --- | --- | --- |
| Giảm `max.poll.records` | Nhiều records tuần tự làm poll quá chậm | Tăng số lần poll; không chữa record đơn bị treo |
| Giới hạn HTTP/DB timeout và retry | Downstream là nguyên nhân chặn thread | Cần phân biệt lỗi vĩnh viễn và lỗi không chắc kết quả |
| Tăng concurrency hoặc replica | Có nhiều partition và backend còn năng lực | Consumer > partition không tăng xử lý; scale gây rebalance |
| Tăng số partition có kế hoạch | Thiếu khả năng song song theo partition | Thay đổi phân bố key/order và chi phí vận hành |
| Cooperative assignor/static membership | Deploy/scale gây rebalance nhiều | Phụ thuộc phiên bản/protocol; static ID phải duy nhất |
| Tối ưu I/O hoặc batch nghiệp vụ | DB/HTTP là nút thắt | Không được phá thứ tự, hợp đồng, transaction |
| DLT và retry hữu hạn | Poison pill chặn một partition | Cần vận hành DLT, replay và quy tắc idempotency |
| Điều chỉnh `max.poll.interval.ms` | Công việc hợp lệ cần thời gian dài có kiểm soát | Đặt quá cao làm chậm phát hiện consumer kẹt |
| Tách việc dài thành workflow khác | Chờ duyệt/callback/tính toán nhiều phút | Cần trạng thái tiến độ, checkpoint, outbox, giới hạn queue |

Điều chỉnh theo chuỗi: **đo thời gian xử lý → tìm chỗ chặn thread → đặt timeout và retry → kiểm soát lượng record mỗi poll → đo lại lag/độ trễ → mới tối ưu concurrency hoặc poll interval**. Tăng replica khi DB/API đã quá tải thường làm nghẽn nặng hơn.

## 9. Kiểm thử rebalance, lag và quá hạn poll

Không nên chỉ unit test trực tiếp method `@KafkaListener`, vì cách đó không kiểm tra group coordinator, assignment, commit hay redelivery. Với ca tích hợp, dùng embedded Kafka hoặc Testcontainers Kafka và một downstream mock có điều khiển thời gian.

| Kịch bản | Thao tác kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Xử lý bình thường | Produce N events, không có lỗi | Offset commit tiến, lag về 0 khi producer ngừng gửi |
| Chậm nhưng trong ngưỡng | Giả lập I/O kéo dài có giới hạn | Không có rebalance vì quá hạn poll |
| Vượt `max.poll.interval.ms` | Cấu hình ngưỡng thấp trong test, giữ listener đủ lâu | Quan sát thay assignment/group, sau đó hồi phục |
| Crash sau DB, trước Kafka commit | Dừng tiến trình giữa hai hành động | Event có thể được đọc lại nhưng side effect chỉ xảy ra một lần |
| Poison pill | Gửi event sai schema hoặc gây lỗi deserialize | Record được xử lý theo policy/DLT, partition không kẹt vĩnh viễn |
| Retry sau timeout | Downstream trả 503/timeout rồi phục hồi | Retry có giới hạn, lag hồi phục, không trùng tác động |
| Scale 1 → 3 → 1 | Thêm/bớt thành viên group | Không mất record và assignment ổn định sau rebalance |
| Hot partition | Dồn key vào một partition | Lag per-partition và alert phát hiện đúng nút thắt |
| Consumer restart | Restart khi còn record chưa commit | At-least-once và idempotency được kiểm chứng |

Với test rebalance, **phải quan sát điều kiện thực sự xảy ra** qua log/metric/assignment, không chỉ ngủ N giây và giả định timeout. Test idempotency nên gửi **cùng event ID nhiều lần**, kể cả trên các offset khác nhau, rồi assert trạng thái DB, số lần gọi API hoặc bản ghi outbox. Dùng cơ chế chờ theo điều kiện với timeout test, tránh `Thread.sleep` cố định gây flaky test.

## 10. Quy trình ứng cứu thực tế

Khi nhận cảnh báo consumer lag hoặc rebalance liên tục:

1. **Khoanh vùng:** group, topic, partition, timestamp bắt đầu chậm; so lag tổng và partition lớn nhất.
2. **Xác nhận cơ chế:** số member, số partition, restart/deploy, thông báo revoke/assign, timeout, lỗi commit.
3. **Đo đúng thời gian:** từ poll tới poll, thời gian listener p95/p99, số records/poll, I/O, retry/backoff.
4. **Tìm nút thắt:** hot partition, poison pill, downstream chậm, consumer bị crash hay sản lượng vượt năng lực.
5. **Bảo vệ dữ liệu:** kiểm tra committed offset, event đã tác động bên ngoài, khả năng idempotent và trạng thái DLT.
6. **Thay đổi nhỏ và đo lại:** giảm batch, đặt timeout, sửa retry, tối ưu DB/API hoặc chỉnh concurrency theo số partition.
7. **Ngăn tái diễn:** thêm test crash/rebalance, dashboard lag+poll+rebalance, cảnh báo event age và runbook replay.

**Ví dụ:** Nếu chỉ partition 4 lag cao do một event gọi API giá mất 90 giây còn các partition khác xử lý tốt, ưu tiên kiểm tra API, dữ liệu/key ở partition 4 và timeout. Tăng số replica không làm hai consumer cùng group xử lý song song một partition theo cách phân công thông thường.

## 11. Checklist trước khi đưa vào production

- [ ] Group ID, số partition và concurrency phù hợp throughput.
- [ ] Đã đo poll interval cùng thời gian xử lý/HTTP/DB p95/p99.
- [ ] Có timeout hữu hạn, retry giới hạn và phân loại lỗi.
- [ ] Có quy trình DLT, quarantine và replay.
- [ ] Các tác động DB/API/broker khác có idempotency.
- [ ] Phân biệt lag theo committed offset và consumer position.
- [ ] Có metrics về rebalance, poll interval, committed lag per-partition, retry và event age.
- [ ] Đã kiểm thử crash/rebalance quanh thời điểm commit offset.
- [ ] Cấu hình session/heartbeat/assignment đúng phiên bản Kafka client/broker.

**Kết luận:** Rebalance là thay đổi quyền xử lý partition, lag phản ánh tiến độ, còn `max.poll.interval.ms` ràng buộc tần suất consumer quay lại vòng poll. Với Spring Boot, cần xử lý từ **latency thực tế của listener và downstream**, **cách commit offset**, **idempotency khi partition đổi chủ**, rồi kiểm chứng qua test và metrics; như vậy hệ thống mới vừa theo kịp lưu lượng, vừa bảo toàn dữ liệu.
