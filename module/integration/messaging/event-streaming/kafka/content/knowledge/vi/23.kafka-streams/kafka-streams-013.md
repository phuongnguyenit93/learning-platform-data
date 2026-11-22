# processing.guarantee và phạm vi exactly_once_v2

Kafka Streams đọc record từ Kafka, xử lý qua topology rồi ghi kết quả trở lại Kafka. Một ứng dụng có thể vừa cập nhật state store, vừa ghi output topic và lưu tiến độ đọc input. Nếu process dừng giữa các thao tác này, hệ thống cần biết phần nào đã được commit để tránh mất dữ liệu hoặc tạo kết quả trùng.

Thuộc tính `processing.guarantee` xác định mức bảo đảm xử lý của Kafka Streams. Hai lựa chọn quan trọng là `at_least_once` và `exactly_once_v2`. Với `exactly_once_v2`, Kafka Streams dùng Kafka transaction để phối hợp output records, tiến độ đọc input và các cập nhật changelog của state store trong cùng ranh giới commit.

Bảo đảm này có phạm vi trong Kafka. Nó không tự động bao gồm database, HTTP API, email, filesystem hoặc side effect bên ngoài topology.

## 1. Vì sao cần processing guarantee?

Giả sử topology đọc event từ topic `orders`, tính điểm tích lũy rồi ghi kết quả sang `customer-scores`.

Một lần xử lý có thể bao gồm:

1. Đọc record từ input partition.
2. Cập nhật state store.
3. Gửi record kết quả sang output topic.
4. Ghi changelog để khôi phục state store.
5. Commit input offset.

Nếu ứng dụng crash sau bước 3 nhưng trước bước 5, lần khởi động tiếp theo có thể đọc lại input. Output trước đó có thể đã được ghi, vì vậy kết quả trùng có thể xuất hiện.

Nếu commit offset trước khi output được ghi, ứng dụng có thể bỏ qua record khi khởi động lại. Processing guarantee quyết định Kafka Streams phối hợp các bước này như thế nào.

## 2. at_least_once

`at_least_once` là processing guarantee mặc định của Kafka Streams. Ứng dụng xử lý record và ghi output, sau đó commit offset theo chu kỳ. Các thao tác này không được gom vào một Kafka transaction duy nhất.

Nếu process crash sau khi output được ghi nhưng trước khi offset input được commit, record có thể được đọc lại và output có thể xuất hiện lần nữa.

~~~mermaid
sequenceDiagram
    participant S as Kafka Streams
    participant I as Input topic
    participant O as Output topic
    participant G as Consumer group offsets

    S->>I: Read record at offset 100
    S->>O: Write transformed output
    Note over S,O: Output đã được ghi
    S-xG: Crash trước khi commit offset
    S->>I: Restart và đọc lại offset 100
    S->>O: Ghi output lần nữa
    S->>G: Commit offset sau xử lý
~~~

Đặc điểm:

- Đơn giản và thường có overhead thấp hơn transactional processing.
- Có thể tạo duplicate output khi process restart hoặc lỗi ở khoảng giữa output và offset commit.
- Consumer downstream nên idempotent nếu duplicate gây ảnh hưởng nghiệp vụ.
- State store và changelog vẫn được quản lý bởi Kafka Streams, nhưng không có atomic commit chung với input offset và output như EOS.

At-least-once có thể là lựa chọn hợp lý nếu duplicate được chấp nhận hoặc downstream đã có cơ chế deduplication. Không nên hiểu at-least-once là dữ liệu chắc chắn không bao giờ mất trong mọi cấu hình; durability còn phụ thuộc producer, broker, replication và cách ứng dụng quản lý lỗi.

## 3. exactly_once_v2 là gì?

`exactly_once_v2` là chế độ exactly-once semantics thế hệ 2 của Kafka Streams. Framework sử dụng Kafka transaction để commit các kết quả Kafka liên quan đến một đơn vị xử lý cùng nhau.

Trong một transaction, Kafka Streams phối hợp:

- Output records được ghi sang các topic đích.
- Record ghi vào repartition topics nếu topology cần repartition.
- Changelog records của state stores.
- Input offsets đại diện cho tiến độ đã xử lý.

Khi transaction commit, output và offset cùng được commit. Khi transaction abort, output transactional không được consumer `read_committed` nhìn thấy và input offsets của transaction không tiến lên.

~~~mermaid
sequenceDiagram
    participant S as Kafka Streams
    participant I as Input topic
    participant T as Transaction coordinator
    participant O as Output topic
    participant C as State changelog
    participant G as Group coordinator

    S->>I: Read input records
    S->>T: Begin transaction
    S->>O: Produce output records
    S->>C: Produce state changelog records
    S->>G: Add consumed offsets to transaction
    S->>T: Commit transaction
    T-->>S: Transaction committed
    Note over O,G: Output, changelog và offsets cùng được commit
~~~

Nếu process crash trước khi commit hoàn tất, transaction sẽ bị abort hoặc được coordinator xử lý theo transaction timeout/recovery. Input offsets chưa được commit sẽ cho phép xử lý lại. Consumer dùng `read_committed` chỉ quan sát các output thuộc transaction đã commit.

### 3.1. V2 khác gì ở mức vận hành?

EOS v2 đơn giản hóa cách Kafka Streams phối hợp transaction so với cơ chế exactly-once đời đầu, giảm một số chi phí quản lý producer và transaction theo task. Ứng dụng không phải tự quản lý transactional producer cho từng record; Kafka Streams điều phối producer, transaction và offset.

EOS v2 được giới thiệu trong Kafka 2.5. Cần dùng Kafka Streams client có hỗ trợ `exactly_once_v2` và broker hỗ trợ protocol tương ứng (Kafka 2.5 trở lên là mốc nền tảng). Khi dùng distribution hoặc phiên bản hỗn hợp, hãy kiểm tra compatibility matrix trước khi bật chế độ này.

Hãy dùng hằng số cấu hình do Kafka Streams cung cấp thay vì gõ nhầm giá trị:

~~~java
props.put(
    StreamsConfig.PROCESSING_GUARANTEE_CONFIG,
    StreamsConfig.EXACTLY_ONCE_V2
);
~~~

Không nhầm `exactly_once_v2` với Kafka producer idempotence đơn thuần. Producer idempotence ngăn duplicate do retry ở tầng producer trong phạm vi producer session/sequence; EOS v2 còn phối hợp output, state changelog và input offsets.

## 4. So sánh at_least_once và exactly_once_v2

| Tiêu chí | at_least_once | exactly_once_v2 |
|---|---|---|
| Output và input offset atomic | Không | Có, trong Kafka transaction |
| Duplicate output sau crash ở ranh giới commit | Có thể | Không hiển thị như output đã commit khi consumer dùng read_committed |
| State changelog và input offset cùng transaction | Không | Có |
| Transaction coordinator | Không cần cho mỗi processing commit | Có |
| Latency/throughput overhead | Thường thấp hơn | Có thêm chi phí transaction |
| Cấu hình | Giá trị mặc định hoặc đặt tường minh | Đặt processing.guarantee |
| Side effect ngoài Kafka | Không được bao phủ | Không được bao phủ |
| Consumer downstream | Có thể dùng read_uncommitted nếu không cần transaction isolation | Cần read_committed để chỉ thấy output committed |

Exactly-once không có nghĩa code nghiệp vụ chỉ chạy đúng một lần trong bộ nhớ. Sau crash, Kafka Streams có thể chạy lại một số bước xử lý. Điều được bảo đảm là các output và tiến độ Kafka đã commit không tạo thành hai kết quả committed cho cùng một lần xử lý input trong phạm vi topology.

## 5. Phạm vi exactly_once_v2 bao gồm những gì?

### 5.1. Bao gồm trong Kafka Streams topology

Với một topology được cấu hình EOS v2, transaction bao phủ các thao tác Kafka do framework quản lý, tiêu biểu:

- Consume offsets từ input topics.
- Produce records sang output topics.
- Produce records sang repartition topics.
- Produce changelog records cho state stores.
- Commit input offsets cùng transaction output.

State store có thể dùng RocksDB hoặc in-memory store. Với persistent state store có changelog, Kafka Streams dùng changelog để phục hồi state sau khi task chuyển worker hoặc process restart. EOS bảo đảm cập nhật changelog được commit cùng tiến độ input và output tương ứng.

### 5.2. Không bao gồm side effect bên ngoài Kafka

Transaction của Kafka không tự động bao gồm:

- Ghi PostgreSQL, MySQL hoặc SQL Server.
- Gọi REST/gRPC service.
- Gửi email hoặc SMS.
- Ghi file hoặc object storage.
- Gọi payment gateway.
- Ghi vào cache hoặc hệ thống bên ngoài không tham gia Kafka transaction.

Ví dụ:

~~~java
stream.mapValues(order -> {
    paymentClient.charge(order); // HTTP side effect
    return calculateResult(order);
}).to("payment-results");
~~~

Nếu payment API đã charge thành công nhưng Kafka transaction abort, Kafka Streams có thể xử lý lại input và gọi payment API lần nữa. Exactly-once v2 không rollback được khoản charge đó.

Với side effect bên ngoài, cần thiết kế idempotency key, inbox/outbox, transactional integration hoặc một quy trình saga/compensation phù hợp.

## 6. Consumer cần isolation.level=read_committed

Transactional output có thể ở trạng thái chưa commit hoặc đã abort. Consumer dùng `read_uncommitted` có thể nhìn thấy transactional records trước khi transaction hoàn tất, kể cả record thuộc transaction sau đó bị abort.

Consumer downstream cần chỉ đọc dữ liệu đã commit nên cấu hình:

~~~properties
isolation.level=read_committed
~~~

Kafka Streams tự cấu hình isolation phù hợp cho các consumer nội bộ khi dùng EOS. Với Kafka consumer bên ngoài đọc output topic của topology, hãy đặt `isolation.level=read_committed` một cách tường minh.

Ví dụ Java:

~~~java
Properties consumerProps = new Properties();
consumerProps.put(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
consumerProps.put(
    ConsumerConfig.GROUP_ID_CONFIG,
    "score-reporting"
);
consumerProps.put(
    ConsumerConfig.ISOLATION_LEVEL_CONFIG,
    "read_committed"
);
~~~

`read_committed` chỉ trả về record thuộc transaction đã commit và record non-transactional. Nó có thể phải chờ Last Stable Offset (LSO) nếu phía trước còn transaction chưa hoàn tất. Vì vậy, transaction mở quá lâu có thể làm consumer downstream bị chậm dù record đã được produce.

## 7. Cấu hình exactly_once_v2 trong Java

Ví dụ cấu hình Kafka Streams:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Produced;

Properties props = new Properties();

props.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "order-enrichment-v1"
);
props.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
props.put(
    StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
    Serdes.String().getClass().getName()
);
props.put(
    StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
    Serdes.String().getClass().getName()
);
props.put(
    StreamsConfig.PROCESSING_GUARANTEE_CONFIG,
    StreamsConfig.EXACTLY_ONCE_V2
);
props.put(StreamsConfig.REPLICATION_FACTOR_CONFIG, 3);
props.put(StreamsConfig.COMMIT_INTERVAL_MS_CONFIG, 100);
props.put(
    StreamsConfig.producerPrefix(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG),
    60000
);

StreamsBuilder builder = new StreamsBuilder();

builder.stream(
        "orders",
        Consumed.with(Serdes.String(), Serdes.String())
    )
    .filter((key, value) -> value != null)
    .mapValues(value -> value.toUpperCase())
    .to(
        "orders-normalized",
        Produced.with(Serdes.String(), Serdes.String())
    );

KafkaStreams streams = new KafkaStreams(builder.build(), props);

Runtime.getRuntime().addShutdownHook(
    new Thread(streams::close)
);

streams.start();
~~~

Các cấu hình đáng chú ý:

- `application.id` định danh logical Kafka Streams application, đồng thời tham gia tạo consumer group và tên internal topics.
- `processing.guarantee` chọn mức bảo đảm xử lý.
- `replication.factor` đặt replication factor cho internal topics do Streams tạo.
- `commit.interval.ms` điều khiển chu kỳ commit/checkpoint; dưới EOS v2, transaction commit thường gắn với chu kỳ này.
- `producer.transaction.timeout.ms` cấu hình timeout transaction của producer nội bộ theo cách prefix của Streams.

Giá trị timeout và commit interval trong ví dụ là dành cho lab. Hãy điều chỉnh theo thời gian xử lý, throughput và cấu hình broker.

### 7.1. Cấu hình bằng Spring Boot

Với Spring Boot Kafka Streams, có thể khai báo các thuộc tính tương đương:

~~~properties
spring.kafka.streams.application-id=order-enrichment-v1
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.streams.properties.processing.guarantee=exactly_once_v2
spring.kafka.streams.properties.replication.factor=3
spring.kafka.streams.properties.commit.interval.ms=100
spring.kafka.streams.properties.producer.transaction.timeout.ms=60000
~~~

Tên property và cách bind có thể phụ thuộc phiên bản Spring Boot/Spring Kafka. Kiểm tra cấu hình thực tế được bind vào StreamsConfig, nhất là các property có prefix `producer.`.

Không cấu hình thủ công transactional.id cho từng producer trong Kafka Streams như khi tự viết KafkaProducer. Framework quản lý producer/transaction lifecycle cho topology.

## 8. application.id và vòng đời ứng dụng

`application.id` cần ổn định qua các lần restart của cùng một logical application. Kafka Streams dùng ID này để định danh consumer group và internal topics.

Ví dụ:

~~~properties
application.id=order-enrichment-v1
~~~

Các nguyên tắc:

- Các instance thuộc cùng một Kafka Streams application phải dùng cùng application.id.
- Một ứng dụng logic khác cần application.id riêng.
- Đổi application.id tạo consumer group/internal topics mới và thường bắt đầu một vòng đời xử lý khác.
- Không đổi application.id chỉ để restart hoặc deploy phiên bản code mới nếu muốn tiếp tục tiến độ và state cũ.
- Khi cần reset/replay, dùng quy trình reset có kiểm soát thay vì đổi ID tùy tiện.

Nếu hai ứng dụng không liên quan dùng chung application.id, chúng có thể chia sẻ consumer group và internal topic namespace ngoài ý muốn.

## 9. Internal topics và replication factor

Kafka Streams có thể tạo internal topics cho:

- Repartitioning giữa các bước topology.
- Changelog của state stores.
- Các luồng dữ liệu nội bộ cần thiết cho topology.

Với production, internal topics cần replication factor phù hợp, ví dụ 3 nếu cluster có đủ broker:

~~~java
props.put(StreamsConfig.REPLICATION_FACTOR_CONFIG, 3);
~~~

Đồng thời cần kiểm tra:

- Broker đủ số lượng để đáp ứng replication factor.
- `min.insync.replicas` phù hợp với yêu cầu durability.
- Producer transaction có thể commit khi ISR đáp ứng policy.
- Internal topics có retention/cleanup policy đúng loại topic.
- ACL cho application principal đủ quyền tạo/đọc/ghi internal topics.

EOS v2 không thay thế replication và durability. Nếu internal topic chỉ có một replica trên một broker rồi broker đó mất dữ liệu, transaction semantics không thể khôi phục dữ liệu đã mất. Cấu hình replication, ISR và storage là một phần của thiết kế độ tin cậy.

## 10. Transaction timeout và commit interval

Một Kafka transaction phải kết thúc trong giới hạn timeout được broker cho phép. Nếu transaction mở quá lâu, coordinator có thể abort transaction.

Cần phân biệt:

| Cấu hình | Ý nghĩa |
|---|---|
| `commit.interval.ms` | Chu kỳ Streams commit tiến độ/transaction theo cơ chế processing |
| `producer.transaction.timeout.ms` | Timeout transaction của producer nội bộ |
| Broker `transaction.max.timeout.ms` | Giới hạn tối đa broker chấp nhận cho transaction timeout |
| `max.poll.interval.ms` | Giới hạn khoảng thời gian consumer không poll tiếp |
| `request.timeout.ms` | Timeout chờ một request mạng |

Transaction timeout cần lớn hơn thời gian topology thực tế cần để xử lý và commit, nhưng không nên tăng vô hạn. Nếu transaction timeout vượt quá giới hạn broker, producer có thể bị từ chối khi khởi tạo transaction.

Commit interval thấp có thể giảm thời gian output chờ được commit, nhưng làm tăng số transaction và overhead coordinator. Commit interval cao có thể cải thiện batching nhưng làm tăng độ trễ visibility và lượng công việc có thể phải xử lý lại khi crash trước commit.

Default commit interval có thể khác giữa at-least-once và EOS v2 cũng như giữa các phiên bản. Hãy kiểm tra default của Kafka Streams release đang dùng thay vì dựa vào giá trị của phiên bản khác.

## 11. Performance trade-off của exactly_once_v2

EOS v2 có thêm chi phí transaction, nhưng không phải lúc nào cũng làm throughput giảm theo một tỷ lệ cố định. Kết quả phụ thuộc:

- Số input/output partitions.
- Số task và số stream thread.
- Số record trong mỗi transaction.
- Kích thước output và changelog.
- Broker load và transaction coordinator.
- Commit interval.
- Network latency và replication factor.
- Thời gian xử lý từng record.

Các cách tối ưu:

1. Đo throughput và p95/p99 latency trước khi bật EOS.
2. Chọn commit interval theo latency target và transaction overhead.
3. Tránh xử lý blocking lâu bên trong processor.
4. Chọn số partition và stream threads phù hợp.
5. Bảo đảm internal topics có replication factor hợp lý.
6. Theo dõi transaction abort, timeout và coordinator errors.
7. Không tăng thread/task chỉ dựa trên CPU; kiểm tra partition parallelism.

Không tắt EOS chỉ vì thấy transaction có overhead. Trước tiên hãy xác định yêu cầu correctness, đo bottleneck và tối ưu topology/batching.

## 12. Exactly-once không bảo đảm thứ tự toàn cục

Kafka bảo đảm thứ tự trong từng partition. EOS v2 không tạo ra một thứ tự tổng thể giữa nhiều partition hoặc nhiều topic.

Nếu topology đọc nhiều partition và ghi output, thứ tự xử lý giữa các partition có thể khác nhau. Để giữ thứ tự theo entity:

- Dùng key ổn định như orderId hoặc accountId.
- Bảo đảm các event cùng entity đi vào cùng partition.
- Tránh tăng partition tùy tiện nếu phụ thuộc key-to-partition mapping.
- Dùng sequence hoặc aggregate version để phát hiện event đến sai thứ tự.
- Không dùng timestamp làm bằng chứng duy nhất của ordering.

Exactly-once nói về atomicity của kết quả đã commit, không nói rằng tất cả event được xử lý theo thứ tự nghiệp vụ toàn cục.

## 13. Side effect bên ngoài Kafka: dùng idempotency hoặc outbox

Nếu topology cần cập nhật database, có một số hướng:

### 13.1. Ghi output Kafka rồi dùng sink consumer

Kafka Streams ghi kết quả vào output topic trong EOS transaction. Một consumer riêng đọc output và ghi database bằng inbox/idempotency.

~~~mermaid
flowchart LR
    I["Kafka input"] --> S["Kafka Streams<br/>exactly_once_v2"]
    S --> O["Kafka output topic"]
    O --> C["Database sink consumer"]
    C --> D["Database transaction<br/>inbox + side effect"]
~~~

Cách này tách Kafka EOS khỏi database transaction. Sink consumer vẫn cần xử lý duplicate và commit offset sau khi database transaction hoàn tất.

### 13.2. Dùng idempotency key

Nếu gọi API bên ngoài, gửi event ID làm idempotency key nếu API hỗ trợ:

~~~java
paymentClient.capture(
    payment.getId(),
    event.eventId()
);
~~~

API đích cần lưu key và trả cùng kết quả khi request được gửi lại. Nếu API không hỗ trợ idempotency, phải thiết kế trạng thái request, reconciliation hoặc compensation.

### 13.3. Outbox ở service sở hữu database

Nếu service cần cập nhật database và phát event, dùng transactional outbox: cập nhật dữ liệu và insert event trong cùng DB transaction; CDC chuyển event sang Kafka. Kafka Streams có thể tiêu thụ event đó và tiếp tục xử lý trong EOS scope.

Không dùng Kafka Streams EOS để tuyên bố một HTTP call hoặc database write đã được thực hiện đúng một lần.

## 14. Lỗi và trạng thái transaction thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Transaction timeout | Topology xử lý quá lâu hoặc commit interval không phù hợp | Đo processing time, điều chỉnh timeout trong giới hạn broker |
| Transaction bị abort | Process crash, rebalance, fencing hoặc lỗi producer | Kiểm tra log Streams, broker và transaction coordinator |
| Consumer không thấy output | Consumer dùng read_committed và transaction chưa commit/đã abort | Kiểm tra transaction state và producer logs |
| Consumer thấy record bị abort | Consumer đang dùng read_uncommitted | Chuyển sang read_committed nếu cần transactional visibility |
| Streams application bị fencing | Nhiều instance dùng nhầm application identity hoặc instance cũ còn hoạt động | Kiểm tra application.id, lifecycle và group membership |
| Internal topic không tạo được | Thiếu ACL, replication factor vượt số broker hoặc broker policy | Kiểm tra quyền và cluster capacity |
| Throughput giảm mạnh | Transaction quá nhỏ/nhiều, coordinator hoặc broker bận | Đo commit interval, batch size và transaction metrics |
| Downstream vẫn có duplicate side effect | Consumer ngoài Kafka không idempotent | Dùng event ID/inbox/idempotency key |
| State store restore chậm | Changelog lớn, broker/replication chậm | Kiểm tra changelog partitions, restore rate và local state |

## 15. Kiểm thử exactly_once_v2

Một bài kiểm thử hữu ích cần cố ý tạo crash tại các ranh giới quan trọng.

| Kịch bản | Cách kiểm thử | Kết quả cần xác minh |
|---|---|---|
| Crash trước khi produce output | Dừng process khi đang xử lý input | Input được đọc lại sau restart |
| Crash sau produce nhưng trước commit | Dừng process khi transaction còn mở | Output transaction cũ không xuất hiện với read_committed |
| Transaction abort | Tạo exception trước commit | Output và offsets của transaction không được commit |
| Restart sau commit | Dừng process sau commit thành công | Input không tạo thêm committed output do đọc lại cùng offset |
| Consumer dùng read_uncommitted | Đọc topic trong lúc transaction đang mở | Có thể thấy record chưa commit; dùng để minh họa isolation |
| Consumer dùng read_committed | Đọc cùng output topic | Chỉ thấy record thuộc transaction đã commit |
| State store restore | Xóa local state hoặc chạy task trên worker mới | State được khôi phục từ changelog đã commit |
| Broker/leader failure | Dừng broker trong môi trường test | Kiểm tra retry, transaction recovery và durability |
| External API retry | Cho API thành công nhưng làm Streams transaction abort | Xác nhận idempotency key ngăn side effect lặp |

Đừng chỉ đếm output record trong một consumer dùng `read_uncommitted`. Cần kiểm thử bằng `read_committed`, kiểm tra committed offsets và state store sau restart.

## 16. Monitoring cho EOS v2

Theo dõi các nhóm metric:

- Transaction commit rate.
- Transaction abort rate.
- Transaction duration.
- Transaction timeout và fencing errors.
- Producer request latency và errors.
- Consumer lag theo input partition.
- Output records per second.
- State store/changelog restore latency.
- Rebalance và task migration.
- Commit interval và processing latency.

Log nên có application.id, task/partition, exception type và transaction error. Không dùng event ID hoặc customer ID làm metric label có cardinality cao.

Nếu transaction abort tăng, xác định nguyên nhân là timeout, broker/coordinator, fencing hay lỗi xử lý. Không tự động tăng timeout cho mọi trường hợp.

## 17. Checklist triển khai processing.guarantee

- [ ] Đã xác định duplicate output có được chấp nhận hay không.
- [ ] Đã chọn `at_least_once` hoặc `exactly_once_v2` theo yêu cầu nghiệp vụ.
- [ ] Kafka Streams client và broker hỗ trợ EOS v2 tương thích.
- [ ] Đã cấu hình application.id ổn định và duy nhất cho logical application.
- [ ] Consumer ngoài topology dùng `isolation.level=read_committed`.
- [ ] Internal topics có replication factor phù hợp production.
- [ ] Broker min ISR và durability policy được cấu hình phù hợp.
- [ ] Transaction timeout nằm trong giới hạn broker và đủ cho processing.
- [ ] Commit interval phù hợp latency/throughput.
- [ ] Không giả định Kafka transaction bao gồm database/API/email.
- [ ] Side effect ngoài Kafka có inbox, outbox hoặc idempotency key.
- [ ] Ordering theo entity dùng Kafka key và aggregate version.
- [ ] Đã kiểm thử crash trước commit, abort, restart và state restore.
- [ ] Theo dõi transaction commit/abort, timeout, lag và task migration.
- [ ] Đã xác minh output bằng consumer `read_committed`.

`processing.guarantee` quyết định Kafka Streams xử lý và commit tiến độ như thế nào. `at_least_once` đơn giản hơn nhưng có thể tạo duplicate output khi crash ở khoảng giữa ghi output và commit offset. `exactly_once_v2` dùng Kafka transaction để phối hợp output, state changelog và input offsets, giúp chỉ các kết quả đã commit được quan sát như một đơn vị nhất quán. Bảo đảm này dừng ở ranh giới Kafka; database, API và side effect bên ngoài vẫn cần idempotency hoặc outbox/inbox riêng.
