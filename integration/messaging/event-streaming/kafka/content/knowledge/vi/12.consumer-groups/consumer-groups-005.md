# Heartbeat, session timeout và phát hiện thành viên mất kết nối

## Mục tiêu bài học

Kafka consumer group cần biết consumer nào còn tham gia group và consumer nào đã dừng hoặc mất kết nối. Trong giao thức classic, consumer gửi heartbeat định kỳ đến group coordinator. Nếu coordinator không nhận heartbeat trong khoảng session timeout, member được xem là đã mất và partition của nó có thể được phân phối lại. Cơ chế này giúp group tự phục hồi khi process chết, máy bị mất mạng hoặc consumer không còn duy trì được kết nối.

Heartbeat không phải cơ chế duy nhất theo dõi sức khỏe consumer. Kafka còn kiểm tra tiến độ gọi poll thông qua max poll interval. Một consumer có thể vẫn gửi heartbeat nhưng xử lý record quá lâu và không gọi poll đúng hạn; trường hợp đó cũng có thể khiến group loại member. Hiểu rõ hai cơ chế này là điều cần thiết để tránh rebalance liên tục và tránh làm chậm quá trình phục hồi.

Sau bài học, người học có thể:

- Giải thích heartbeat và vai trò của group coordinator.
- Mô tả cách session timeout phát hiện consumer mất kết nối.
- Phân biệt session.timeout.ms, heartbeat.interval.ms và max.poll.interval.ms.
- Nhận diện nguyên nhân heartbeat bị trễ hoặc consumer bị loại khỏi group.
- Cấu hình timeout phù hợp với thời gian xử lý record.
- Hiểu static membership qua group.instance.id và tác động đến thời gian phục hồi.
- Theo dõi rebalance, heartbeat và consumer group bằng CLI, log và metrics.
- Xử lý việc revoke/lost partition trong Java và Spring Kafka.

## 1. Vì sao consumer group cần heartbeat?

Một consumer group chia các partition của topic cho nhiều consumer. Kafka cần biết thành viên nào đang hoạt động để quyết định partition nào thuộc về consumer nào. Nếu một consumer dừng đột ngột, group phải phát hiện sự cố và phân phối lại partition để các consumer còn lại tiếp tục xử lý.

Consumer gửi heartbeat đến group coordinator theo chu kỳ. Coordinator ghi nhận hoạt động của member. Nếu heartbeat không đến trong thời gian session timeout, coordinator đánh dấu member không còn hợp lệ và kích hoạt quá trình rebalance.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant G as Group Coordinator
    participant O as Consumer khác
    C->>G: JoinGroup / SyncGroup
    G-->>C: Assignment partition
    loop Trong khi hoạt động
        C->>G: Heartbeat
        G-->>C: Heartbeat response
    end
    Note over C,G: Consumer mất kết nối hoặc process dừng
    G->>G: Session timeout hết hạn
    G-->>O: Bắt đầu rebalance / phân phối lại partition
~~~

Heartbeat cho coordinator biết member còn liên lạc được với group. Nó không xác nhận rằng ứng dụng đã xử lý xong record, database đã commit hay nghiệp vụ đã thành công.

## 2. Group coordinator và vòng đời member

Mỗi consumer group có một group coordinator chịu trách nhiệm điều phối membership và offset của group. Coordinator được xác định dựa trên partition của internal topic __consumer_offsets tương ứng với group ID.

Khi consumer tham gia group theo giao thức classic, quy trình tổng quát gồm:

1. Consumer tìm group coordinator.
2. Consumer gửi JoinGroup để tham gia group.
3. Coordinator xử lý membership và chọn group leader cho bước phân phối assignment theo giao thức classic.
4. Consumer nhận assignment qua SyncGroup.
5. Consumer bắt đầu fetch record từ các partition được giao.
6. Consumer gửi heartbeat định kỳ để duy trì membership.

Nếu consumer rời group có chủ đích, nó có thể gửi LeaveGroup. Nếu process chết hoặc network bị đứt đột ngột, coordinator không nhận được thông báo rời group và phải dựa vào session timeout để phát hiện member mất kết nối.

Group coordinator cũng quản lý các committed offset của group. Heartbeat và offset commit là hai loại request khác nhau: heartbeat duy trì membership, còn commit lưu tiến độ đọc để group có thể tiếp tục sau restart hoặc rebalance.

## 3. Heartbeat hoạt động như thế nào?

Trong Kafka Java Consumer sử dụng classic group protocol, heartbeat thường được gửi bởi luồng nền của consumer client. Ứng dụng vẫn phải tiếp tục gọi poll theo yêu cầu; heartbeat thread không thay thế vòng poll của ứng dụng.

Các bước chính:

1. Consumer gia nhập group và nhận assignment.
2. Consumer client khởi chạy cơ chế heartbeat nền.
3. Theo heartbeat interval, client gửi Heartbeat request đến coordinator.
4. Coordinator phản hồi nếu member còn hợp lệ trong generation/group epoch hiện tại.
5. Nếu coordinator không nhận heartbeat trong session timeout, member có thể bị loại khỏi group.
6. Group thực hiện rebalance để phân phối lại partition.

~~~mermaid
flowchart TD
    A[Consumer đã có assignment] --> B[Heartbeat timer đến hạn]
    B --> C[Gửi Heartbeat request]
    C --> D{Coordinator phản hồi?}
    D -->|Có| E[Gia hạn trạng thái member]
    E --> B
    D -->|Không| F[Retry hoặc xử lý lỗi theo client]
    F --> G{Session timeout hết hạn?}
    G -->|Chưa| B
    G -->|Rồi| H[Member bị xem là mất]
    H --> I[Group rebalance]
~~~

Heartbeat có thể thất bại vì process bị dừng, network partition, DNS hoặc routing lỗi, broker/coordinator quá tải, JVM pause dài hoặc consumer không thể chạy luồng nền đúng hạn. Một lần heartbeat thất bại chưa chắc lập tức làm member bị loại; điều quan trọng là coordinator có nhận heartbeat hợp lệ trong cửa sổ session timeout hay không.

## 4. Ba cấu hình thường bị nhầm lẫn

Ba cấu hình cần được hiểu cùng nhau:

| Cấu hình | Vai trò | Câu hỏi nó trả lời |
|---|---|---|
| heartbeat.interval.ms | Chu kỳ client gửi heartbeat trong classic protocol | Consumer báo còn hoạt động thường xuyên đến mức nào? |
| session.timeout.ms | Thời gian coordinator chờ heartbeat hợp lệ trước khi loại member trong classic protocol | Mất liên lạc bao lâu thì xem member đã chết? |
| max.poll.interval.ms | Thời gian tối đa giữa hai lần gọi poll của ứng dụng | Consumer được phép mất bao lâu để xử lý trước khi phải poll tiếp? |

### 4.1. heartbeat.interval.ms

heartbeat.interval.ms xác định khoảng thời gian giữa các heartbeat request. Giá trị này phải nhỏ hơn session.timeout.ms. Một quy tắc cấu hình thường dùng trong classic protocol là heartbeat interval không vượt quá khoảng một phần ba session timeout.

Ví dụ:

~~~properties
heartbeat.interval.ms=3000
session.timeout.ms=10000
~~~

Consumer cố gắng gửi heartbeat khoảng mỗi ba giây, còn coordinator chờ tối đa mười giây kể từ heartbeat hợp lệ cuối cùng trước khi xem member đã mất. Các con số này chỉ là ví dụ; cần cân bằng giữa tốc độ phát hiện lỗi, jitter mạng và tải coordinator.

Heartbeat quá thường xuyên làm tăng request rate và tải coordinator. Heartbeat quá thưa khiến phát hiện lỗi chậm hơn và cần session timeout đủ lớn để không loại member vì một khoảng trễ ngắn.

### 4.2. session.timeout.ms

session.timeout.ms là cửa sổ coordinator chờ heartbeat hợp lệ. Khi hết thời gian, coordinator xem member là không còn hoạt động và bắt đầu xử lý membership thay đổi.

Session timeout thấp:

- Phát hiện consumer chết nhanh hơn.
- Có thể tăng rebalance giả khi mạng hoặc JVM tạm thời bị trễ.
- Nhạy hơn với broker load và network jitter.

Session timeout cao:

- Dễ chịu hơn với gián đoạn ngắn.
- Kéo dài thời gian phát hiện consumer chết thật.
- Partition có thể phải chờ lâu hơn trước khi được phân phối lại.

Broker classic protocol có giới hạn session timeout tối thiểu và tối đa qua group.min.session.timeout.ms và group.max.session.timeout.ms. Giá trị client gửi phải nằm trong khoảng broker cho phép.

### 4.3. max.poll.interval.ms

max.poll.interval.ms giới hạn khoảng thời gian giữa hai lần ứng dụng gọi poll(). Nó bảo vệ group khỏi một consumer vẫn giữ membership nhưng không tiếp tục tiến độ lấy record.

Ví dụ consumer nhận một batch gồm nhiều record, sau đó xử lý đồng bộ trong 7 phút. Nếu max.poll.interval.ms chỉ là 5 phút, consumer có thể vượt quá poll interval dù heartbeat thread vẫn có thể gửi heartbeat trong thời gian xử lý. Khi quá hạn, consumer bị xem là không còn tiến triển và có thể rời group; các partition sẽ được phân phối lại theo cơ chế membership.

Với static member có group.instance.id, khi max poll interval hết hạn, consumer ngừng heartbeat và partition có thể chỉ được phân phối lại sau session timeout, thay vì bị chuyển ngay lập tức. Điều này giúp giảm rebalance tức thời khi instance khởi động lại, nhưng có thể kéo dài thời gian phục hồi.

Nếu xử lý record lâu, hãy xem xét:

- Giảm max.poll.records để mỗi batch có ít record hơn.
- Tăng max.poll.interval.ms dựa trên thời gian xử lý xấu nhất có kiểm soát.
- Tối ưu xử lý nghiệp vụ và tránh I/O blocking kéo dài trên consumer thread.
- Dùng pause/resume hoặc mô hình xử lý bất đồng bộ có kiểm soát acknowledgement và ordering.
- Theo dõi thời gian giữa các lần poll và thời gian xử lý batch.

Không tăng session.timeout.ms để xử lý một consumer bị kẹt trong callback nếu nguyên nhân thực tế là max.poll.interval.ms.

## 5. Ví dụ cấu hình consumer classic

Ví dụ cấu hình Kafka Java Consumer:

~~~java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-projection");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());

props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

// Các giá trị minh họa cho classic group protocol.
props.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 3000);
props.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 10000);
props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300000);
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);
~~~

Với cấu hình này, ứng dụng cần gọi poll thường xuyên hơn năm phút. Mỗi poll trả về tối đa 100 record theo giới hạn max.poll.records, nhưng thời gian xử lý thực tế vẫn phụ thuộc payload, database và logic nghiệp vụ.

Ví dụ vòng poll đơn giản:

~~~java
while (running) {
    ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, String> record : records) {
        process(record);
    }

    consumer.commitSync();
}
~~~

Nếu process(record) mất quá nhiều thời gian, vòng lặp không gọi poll tiếp và có thể vượt max.poll.interval.ms. Cần ước lượng thời gian xử lý batch:

~~~text
Batch processing time
  = số record trong batch x thời gian xử lý trung bình mỗi record
    + overhead database/network
    + thời gian retry và backoff
~~~

Thiết kế nên dựa vào p95/p99 hoặc thời gian xử lý xấu nhất có kiểm soát, không chỉ dựa trên thời gian trung bình.

## 6. Điều gì xảy ra khi heartbeat bị mất?

Các nguyên nhân phổ biến:

| Nguyên nhân | Diễn biến | Hướng kiểm tra |
|---|---|---|
| Consumer process bị kill/crash | Không còn heartbeat từ member | Kiểm tra process exit, container restart và log JVM |
| Máy hoặc container mất mạng | Heartbeat không tới coordinator | Kiểm tra DNS, route, firewall, packet loss và broker endpoint |
| JVM stop-the-world pause dài | Luồng heartbeat không chạy trong thời gian pause | Kiểm tra GC pause, heap pressure và CPU saturation |
| Coordinator quá tải | Heartbeat response chậm hoặc request timeout | Kiểm tra broker CPU, request queue, network và coordinator load |
| Consumer xử lý quá lâu | Poll không được gọi đúng hạn; max poll interval bị vượt | Kiểm tra batch size, thời gian listener và max.poll.interval.ms |
| Session timeout quá thấp | Jitter ngắn cũng có thể khiến member bị loại | Đánh giá heartbeat interval và timeout theo network thực tế |
| Nhiều consumer khởi động/dừng đồng thời | Group liên tục thay đổi membership | Kiểm tra deployment rollout, autoscaling và static membership |

### 6.1. Session expired và rebalance

Khi coordinator không nhận heartbeat trong session timeout, nó có thể đánh dấu member đã chết. Các partition do member nắm giữ cần được gán lại cho consumer còn hoạt động.

Việc phân phối lại có thể làm phát sinh:

- Consumer khác bắt đầu đọc partition vừa được thu hồi.
- Consumer group chạy rebalance và có thể tạm dừng fetch trong một phần quy trình.
- Record chưa commit offset có thể được đọc lại.
- Các callback revoke/assigned/lost được gọi theo trạng thái partition và giao thức.

Nếu ứng dụng commit offset không đúng thời điểm, rebalance có thể gây xử lý lặp hoặc mất xử lý. Hãy gắn offset commit với kết quả nghiệp vụ và dùng idempotency khi cần.

### 6.2. Heartbeat khỏe không đồng nghĩa xử lý khỏe

Heartbeat chỉ chứng minh client còn giao tiếp được với coordinator. Consumer có thể vẫn heartbeat đều nhưng:

- Xử lý record quá chậm.
- Database downstream bị nghẽn.
- Consumer lag tăng.
- Một partition bị hot key.
- Thread xử lý bị block trong khi heartbeat thread vẫn hoạt động.

Do đó, cần giám sát đồng thời heartbeat, poll progress, rebalance và consumer lag. Không dùng heartbeat success làm chỉ số duy nhất để kết luận consumer đang xử lý tốt.

## 7. Static membership với group.instance.id

Mặc định, consumer được nhận diện bằng member ID do group coordinator quản lý. Khi consumer restart, nó có thể gia nhập lại với member ID mới và gây rebalance.

Static membership cho phép ứng dụng đặt group.instance.id ổn định cho một instance logic:

~~~java
props.put(ConsumerConfig.GROUP_INSTANCE_ID_CONFIG, "order-consumer-1");
~~~

Nếu instance restart trong thời gian session timeout và quay lại với cùng group.instance.id, Kafka có thể giữ assignment để member tiếp tục mà không phải phân phối lại toàn group như một dynamic member mới.

Lợi ích:

- Giảm rebalance khi rolling restart hoặc restart ngắn.
- Giữ assignment ổn định hơn cho các consumer có state/cache cục bộ.
- Giảm gián đoạn khi deployment có instance identity bền vững.

Giới hạn và rủi ro:

- group.instance.id phải duy nhất trong một group.
- Nếu hai process cùng dùng một ID, member cũ có thể bị fencing hoặc nhận lỗi duplicate static member.
- Static membership có thể kéo dài thời gian partition được giao lại khi instance thực sự chết, vì coordinator phải chờ session timeout.
- Không dùng hostname hoặc ID thay đổi liên tục nếu muốn membership ổn định.

Static membership phù hợp với deployment có identity rõ ràng như StatefulSet ordinal hoặc tên instance cố định. Với autoscaling tạo instance ngẫu nhiên, cần thiết kế ID và vòng đời member cẩn thận.

Phần static membership ở đây mô tả cách dùng trong classic group protocol. Khi chuyển sang group.protocol=consumer, không giả định group.instance.id có cùng hành vi hoặc được hỗ trợ giống classic ở mọi phiên bản. Hãy kiểm tra compatibility matrix và tài liệu broker/client của phiên bản triển khai trước khi bật đồng thời các tính năng này.

## 8. Classic protocol và consumer group protocol mới

Các cấu hình heartbeat phía client ở trên mô tả classic consumer group protocol. Kafka hiện đại còn có consumer group protocol mới, được bật bằng cấu hình group.protocol=consumer trong các phiên bản hỗ trợ.

Điểm khác biệt quan trọng:

| Nội dung | Classic protocol | Consumer protocol mới |
|---|---|---|
| Cấu hình giao thức | group.protocol=classic hoặc mặc định tùy phiên bản | group.protocol=consumer |
| Heartbeat interval | Client cấu hình heartbeat.interval.ms | Broker quản lý qua group.consumer.heartbeat.interval.ms |
| Session timeout | Client cấu hình session.timeout.ms trong giới hạn broker | Broker quản lý qua group.consumer.session.timeout.ms |
| Phân phối assignment | Group leader thực hiện theo assignor classic | Coordinator quản lý assignment theo giao thức mới |
| Rebalance | Có thể dùng eager hoặc cooperative assignor tùy cấu hình | Thiết kế giao thức mới giảm thời gian dừng và hỗ trợ incremental assignment |

Không sao chép nguyên các giá trị heartbeat.interval.ms và session.timeout.ms của classic sang consumer protocol mới rồi kỳ vọng chúng có cùng tác dụng. Khi dùng group.protocol=consumer, hãy kiểm tra cấu hình broker và tài liệu của phiên bản Kafka đang chạy.

Ví dụ khai báo classic rõ ràng:

~~~properties
group.protocol=classic
heartbeat.interval.ms=3000
session.timeout.ms=10000
~~~

Ví dụ chọn consumer protocol mới trên phiên bản hỗ trợ:

~~~properties
group.protocol=consumer
~~~

Các giá trị heartbeat/session timeout khi đó được điều khiển ở broker theo cấu hình của consumer group protocol mới. Tính năng và trạng thái hỗ trợ phụ thuộc phiên bản broker/client; hãy kiểm tra compatibility trước khi rollout.

## 9. Xử lý partition khi rebalance

Java Consumer API cung cấp ConsumerRebalanceListener để ứng dụng phản ứng khi partition được gán, thu hồi hoặc mất quyền sở hữu.

~~~java
consumer.subscribe(
    List.of("orders"),
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
            // Hoàn tất công việc an toàn và commit offset đã xử lý.
            commitProcessedOffsets(partitions);
            releasePartitionResources(partitions);
        }

        @Override
        public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
            initializePartitionResources(partitions);
        }

        @Override
        public void onPartitionsLost(Collection<TopicPartition> partitions) {
            // Partition đã mất quyền sở hữu; không giả định còn có thể commit.
            discardLocalOwnershipState(partitions);
        }
    }
);
~~~

Các hàm trong ví dụ là logic ứng dụng. Cần phân biệt:

- onPartitionsRevoked: group đang thu hồi partition; ứng dụng có cơ hội hoàn tất/commit phần đã xử lý theo thiết kế.
- onPartitionsAssigned: partition được gán cho consumer; ứng dụng có thể khởi tạo state hoặc seek offset theo yêu cầu.
- onPartitionsLost: consumer đã mất quyền sở hữu partition, ví dụ do session timeout hoặc rebalance đã tiến xa; không được giả định có thể commit như khi revoke bình thường.

Không thực hiện commit đồng bộ kéo dài trong callback nếu điều đó làm tăng thời gian rebalance. Offset chỉ nên commit đến vị trí tiếp theo của record đã xử lý thành công và bảo đảm không bỏ qua record chưa hoàn tất.

## 10. Spring Kafka: container quản lý poll và heartbeat

Với Spring Kafka, listener container tạo và quản lý Kafka Consumer, vòng poll và lifecycle. Ứng dụng thường cấu hình consumer properties qua application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      properties:
        group.protocol: classic
        heartbeat.interval.ms: 3000
        session.timeout.ms: 10000
        max.poll.interval.ms: 300000
        max.poll.records: 100
~~~

Ví dụ listener:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        topics = "orders",
        groupId = "order-projection",
        concurrency = "3"
    )
    public void consume(ConsumerRecord<String, String> record) {
        processOrder(record);
    }
}
~~~

Concurrency tạo nhiều consumer trong listener container, nhưng số consumer có partition thực tế còn phụ thuộc số partition của topic và assignment. Nếu listener xử lý đồng bộ lâu, thread consumer không quay lại poll kịp thời và có thể vượt max.poll.interval.ms.

Khi cần xử lý lâu:

- Giảm max.poll.records để giới hạn số record trong mỗi batch.
- Chọn concurrency phù hợp số partition và năng lực downstream.
- Tối ưu truy vấn database và tránh gọi dịch vụ ngoài với timeout quá dài.
- Cấu hình retry/backoff có giới hạn.
- Nếu chuyển xử lý sang executor, phải quản lý acknowledgement, offset và ordering rõ ràng; không để container commit trước khi công việc bất đồng bộ hoàn tất.

Spring Kafka cũng có các cơ chế pause/resume và container error handler. Hãy dùng chúng theo đúng phiên bản Spring Kafka; đừng chỉ tăng session timeout để che giấu listener đang bị block.

## 11. Theo dõi heartbeat và consumer group

### 11.1. Kafka CLI

Xem trạng thái group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group order-projection
~~~

Xem member và assignment:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group order-projection --members --verbose
~~~

Xem trạng thái group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group order-projection --state
~~~

Tùy phiên bản Kafka, các tùy chọn hiển thị có thể khác nhau. Dùng script đi kèm phiên bản cluster và kiểm tra help nếu một tùy chọn chưa được hỗ trợ.

### 11.2. Log cần quan sát

Tìm các dấu hiệu:

- Heartbeat request timeout hoặc coordinator unavailable.
- Session expired hoặc member removed.
- max.poll.interval.ms exceeded.
- Rebalance started/completed.
- Commit failed do generation/member đã thay đổi.
- Static member bị fencing hoặc duplicate instance ID.

Đối chiếu timestamp log của consumer và broker để xác định heartbeat cuối cùng, thời điểm coordinator loại member và thời điểm rebalance hoàn tất.

### 11.3. Metrics

Các consumer metrics hữu ích gồm:

| Metric | Ý nghĩa |
|---|---|
| heartbeat-rate / heartbeat-total | Tần suất và tổng số heartbeat |
| heartbeat-response-time-max | Thời gian phản hồi heartbeat lớn nhất |
| last-heartbeat-seconds-ago | Thời gian kể từ heartbeat gần nhất |
| rebalance-rate-per-hour / rebalance-total | Tần suất và tổng số lần rebalance |
| rebalance-latency-avg / rebalance-latency-max | Độ trễ rebalance |
| assigned-partitions | Số partition đang được gán |
| records-lag-max | Lag lớn nhất của consumer |

Tên metric cụ thể và cách export phụ thuộc phiên bản client/JMX exporter. Hãy xác minh metric có tồn tại trong môi trường thực tế trước khi tạo dashboard hoặc alert.

Theo dõi đồng thời heartbeat, rebalance, poll interval, processing latency và consumer lag. Heartbeat ổn định nhưng lag tăng liên tục thường chỉ ra vấn đề throughput/downstream thay vì membership.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Member liên tục bị remove do session timeout | Heartbeat không tới coordinator đúng hạn | Kiểm tra network, GC pause, CPU, broker load và tăng timeout có cơ sở |
| Rebalance liên tục dù consumer process không chết | max.poll.interval.ms bị vượt hoặc deployment liên tục restart | Giảm batch, tối ưu listener, điều chỉnh poll interval và rollout theo đợt |
| Heartbeat response chậm | Coordinator/broker quá tải hoặc network latency cao | Kiểm tra broker request queue, CPU, network và coordinator |
| Consumer lag tăng nhưng heartbeat bình thường | Xử lý record chậm hoặc downstream nghẽn | Đo processing latency, DB latency, concurrency và partition skew |
| Static member bị fencing | Trùng group.instance.id | Đảm bảo ID duy nhất cho mỗi instance trong group |
| Partition được gán lại chậm sau khi instance chết | Session timeout cao hoặc static membership | Đánh giá trade-off giữa restart ổn định và thời gian failover |
| Commit thất bại sau rebalance | Generation/member đã thay đổi hoặc partition đã lost | Commit đúng lifecycle, xử lý revoke/lost và không commit offset chưa xử lý |
| Heartbeat mất trong thời gian GC | JVM pause dài hơn cửa sổ timeout | Kiểm tra GC log, heap, allocation rate và CPU saturation |

Không xử lý mọi trường hợp bằng cách tăng session.timeout.ms. Nếu nguyên nhân là listener xử lý quá lâu, cần xem max.poll.interval.ms và batch size. Nếu nguyên nhân là GC pause, cần xử lý heap/GC. Nếu nguyên nhân là network, cần khắc phục kết nối và latency.

## 13. Bài tập thực hành

### Bài tập 1: Quan sát heartbeat bình thường

1. Tạo topic orders-lab có ít nhất ba partition.
2. Khởi chạy hai consumer cùng group.
3. Cấu hình heartbeat.interval.ms=3000 và session.timeout.ms=10000 trong classic protocol.
4. Dùng CLI xem members, assignment và state.
5. Quan sát heartbeat metrics và rebalance metrics.

**Kết quả mong đợi:** consumer giữ membership ổn định khi heartbeat đều và poll tiếp tục được gọi.

### Bài tập 2: Mô phỏng consumer mất kết nối

1. Dùng môi trường lab, khởi chạy một consumer trong group.
2. Dừng process consumer đột ngột hoặc chặn network có kiểm soát.
3. Quan sát thời điểm coordinator phát hiện member mất.
4. Kiểm tra partition được gán lại cho consumer còn lại.
5. So sánh thời gian phục hồi khi session.timeout.ms ngắn và dài.

Không thực hiện việc chặn network hoặc kill process trên cluster production.

### Bài tập 3: Phân biệt session timeout và max poll interval

1. Cấu hình max.poll.records đủ nhỏ để quan sát.
2. Thêm xử lý giả lập mất nhiều thời gian trong listener.
3. Đặt max.poll.interval.ms ngắn hơn thời gian xử lý batch.
4. Quan sát member bị rời group dù process vẫn chạy.
5. Tăng max.poll.interval.ms hoặc giảm batch size và so sánh.

**Kết quả mong đợi:** người học giải thích được heartbeat và poll progress là hai cơ chế khác nhau.

### Bài tập 4: Static membership

1. Cấu hình group.instance.id ổn định cho mỗi consumer instance.
2. Restart một instance trong thời gian session timeout.
3. Quan sát assignment và số lần rebalance.
4. Thử khởi chạy hai instance có cùng group.instance.id trong lab.
5. Giải thích hiện tượng fencing và trade-off của static membership.

## 14. Câu hỏi tự kiểm tra

1. Heartbeat được gửi đến thành phần nào trong Kafka?
2. Coordinator dựa vào điều gì để xác định member đã mất?
3. heartbeat.interval.ms khác session.timeout.ms thế nào?
4. max.poll.interval.ms bảo vệ group khỏi tình huống nào?
5. Vì sao consumer có thể heartbeat bình thường nhưng vẫn bị loại khỏi group?
6. Session timeout thấp và cao tạo ra trade-off gì?
7. group.instance.id giúp giảm rebalance trong trường hợp nào?
8. Vì sao static membership có thể kéo dài thời gian failover?
9. onPartitionsRevoked khác onPartitionsLost ở điểm nào?
10. Khi consumer lag tăng nhưng heartbeat ổn định, cần kiểm tra điều gì?
11. Consumer protocol mới khác classic protocol ở cách quản lý heartbeat/session timeout ra sao?
12. Vì sao không nên chỉ tăng session timeout để xử lý listener bị block?

Khi hiểu heartbeat là tín hiệu membership, session timeout là cửa sổ phát hiện mất liên lạc và max poll interval là giới hạn tiến độ poll của ứng dụng, người vận hành có thể chọn timeout hợp lý, giảm rebalance giả và rút ngắn thời gian phục hồi khi consumer thực sự gặp sự cố.
