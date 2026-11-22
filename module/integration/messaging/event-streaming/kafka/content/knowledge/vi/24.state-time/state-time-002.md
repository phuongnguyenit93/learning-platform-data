# Changelog topic và phục hồi state store

## Mục tiêu bài học

Kafka Streams duy trì state cục bộ để thực hiện aggregation, join, windowing và các phép xử lý có trạng thái. State store thường nằm trên disk của từng instance, nhưng disk local có thể mất khi process restart, container được thay thế hoặc task chuyển sang instance khác. Để khôi phục state, Kafka Streams ghi các thay đổi của store vào internal changelog topic trên Kafka.

Bài học giải thích mối quan hệ giữa state store, changelog topic và task; cách Kafka Streams restore state sau restart hoặc rebalance; vai trò của standby replica; cấu hình logging, replication và local state directory; cách giám sát restoration; và cách xử lý khi state store hoặc changelog gặp sự cố.

Sau bài học, người học có thể:

- Giải thích vì sao stateful Kafka Streams application cần state store và changelog.
- Phân biệt local state store, changelog topic và repartition topic.
- Hiểu cách Kafka Streams ghi state change và khôi phục store từ changelog.
- Giải thích compaction, tombstone và retention của changelog.
- Cấu hình state store logging, replication factor và state directory.
- Dùng standby replica để giảm thời gian phục hồi khi task failover.
- Theo dõi trạng thái task, restore progress, lag và RocksDB/local disk.
- Xử lý thay đổi topology, application ID, store name và state schema.
- Lập kế hoạch reset hoặc rebuild state an toàn.

## 1. Vì sao Kafka Streams cần state store?

Một số phép xử lý chỉ cần xem từng record độc lập. Ví dụ lọc event có amount lớn hơn một ngưỡng. Nhưng các phép xử lý như count, aggregate, join hoặc windowed aggregation phải nhớ dữ liệu đã xử lý trước đó.

Ví dụ một ứng dụng đếm số đơn hàng theo customer:

~~~text
Customer A: order-1, order-2, order-3
Customer B: order-4, order-5
~~~

Khi nhận order mới của Customer A, ứng dụng cần đọc giá trị count hiện tại rồi cập nhật thành giá trị mới. Giá trị count được lưu trong state store.

~~~mermaid
flowchart LR
    A[orders topic] --> B[Kafka Streams task]
    B --> C[State store<br/>customer-order-count]
    C --> D[Changelog topic]
    B --> E[Output topic]
    D --> F[Restore local state]
~~~

State store là dữ liệu phục vụ xử lý của Kafka Streams. Nó có thể được lưu bằng RocksDB trên local disk hoặc một store implementation khác. Local state giúp truy cập nhanh, nhưng bản thân nó không phải nguồn dữ liệu bền vững duy nhất.

## 2. Changelog topic là gì?

Changelog topic là internal Kafka topic lưu các thay đổi của state store. Khi stateful processor cập nhật một key trong store, Kafka Streams có thể ghi một record tương ứng vào changelog topic. Nếu local state bị mất hoặc task được chuyển sang instance khác, Kafka Streams đọc changelog để dựng lại state.

Ví dụ state store có key customer-7:

| Thời điểm | Thay đổi state | Changelog record |
|---|---|---|
| T1 | count = 1 | customer-7 → 1 |
| T2 | count = 2 | customer-7 → 2 |
| T3 | count = 3 | customer-7 → 3 |

Với key-value store được compact, Kafka có thể giữ giá trị mới nhất của mỗi key để restore. Sau compaction, consumer không cần đọc tất cả phiên bản cũ của key nếu chúng đã được loại bỏ an toàn khỏi log.

Kafka Streams có thể cache và gộp các cập nhật state trước khi flush xuống changelog theo chu kỳ commit hoặc khi cache đầy. Vì vậy, changelog là nhật ký đủ để tái tạo state đã commit, không nhất thiết có đúng một record cho mỗi input record.

### 2.1. Changelog là nguồn phục hồi của state store

Khi task khởi động:

1. Kafka Streams xác định state store cần khôi phục.
2. Nếu local state còn hợp lệ, ứng dụng có thể tiếp tục từ checkpoint đã lưu.
3. Nếu state chưa có hoặc không còn phù hợp, Kafka Streams đọc changelog partition tương ứng.
4. Các record changelog được deserialize và áp dụng vào local store.
5. Khi restore bắt kịp điểm cần thiết, task có thể chuyển sang xử lý input bình thường.

~~~mermaid
sequenceDiagram
    participant T as Kafka Streams task
    participant L as Local state store
    participant C as Changelog partition
    T->>L: Kiểm tra local state/checkpoint
    alt Local state hợp lệ
        L-->>T: State và checkpoint
        T->>C: Đọc phần changelog còn thiếu
    else Local state mất hoặc không hợp lệ
        T->>C: Đọc changelog để restore
        C-->>T: State change records
        T->>L: Áp dụng từng record
    end
    T->>T: Hoàn tất restore và xử lý input
~~~

Checkpoint giúp tránh phải đọc lại toàn bộ changelog mỗi lần restart. Nếu local state bị xóa, checkpoint không còn tương ứng hoặc store cần rebuild, Kafka Streams có thể phải restore nhiều dữ liệu hơn.

### 2.2. Changelog topic name

Với state store có tên rõ ràng, changelog topic thường có tên theo mẫu:

~~~text
<application.id>-<store-name>-changelog
~~~

Ví dụ:

~~~text
orders-state-app-customer-order-count-changelog
~~~

application.id là định danh của Kafka Streams application và cũng được dùng làm consumer group ID. Các instance thuộc cùng một logical application phải dùng cùng application.id. Các ứng dụng độc lập phải dùng application.id khác nhau để không tranh chấp task và internal topics.

Tên changelog cụ thể là chi tiết nội bộ của Kafka Streams. Không nên để ứng dụng nghiệp vụ publish record trực tiếp vào topic này hoặc phụ thuộc vào cấu trúc key/value nội bộ.

### 2.3. Partition của changelog

Changelog topic được partition để các task có thể ghi và restore state song song. Số partition thường gắn với số task partition của state store, vốn phụ thuộc partition count của input hoặc repartition topic đứng trước stateful operation. Mỗi task chịu trách nhiệm một phần state và changelog partition tương ứng.

Vì vậy, thay đổi partition count của input/repartition topic hoặc thay topology có thể ảnh hưởng task mapping và cách state được phân phối. Không tự tăng/giảm partition của changelog topic bằng tay; để Kafka Streams quản lý internal topic theo topology và version.

## 3. Changelog topic khác repartition topic như thế nào?

Kafka Streams có nhiều loại internal topic. Hai loại dễ nhầm nhất là changelog topic và repartition topic.

| Tiêu chí | Changelog topic | Repartition topic |
|---|---|---|
| Mục đích | Lưu thay đổi state store để phục hồi state | Phân phối lại input record theo key mới |
| Dữ liệu | State updates, tombstone và record phục vụ restore | Record trung gian sau thao tác rekey/grouping |
| Consumer chính | Task restore/standby của Kafka Streams | Task downstream trong topology |
| Cleanup policy thường dùng | compact; windowed store có thể compact,delete | delete |
| Vai trò khi restart | Rebuild local state | Không phải bản sao state store |

Ví dụ:

- selectKey đổi key của record rồi groupByKey có thể cần repartition topic để record cùng key về cùng partition.
- count hoặc aggregate tạo state store; store đó dùng changelog topic để phục hồi state.

Không xóa repartition topic hoặc changelog topic thủ công khi application đang chạy. Đây là internal topics do Kafka Streams quản lý.

## 4. Kafka Streams tạo state store và changelog

Kafka Streams DSL tạo state store khi topology có stateful operation như count, aggregate, reduce, join hoặc windowed aggregation. Store có thể được đặt tên tường minh để dễ quan sát và truy vấn.

Ví dụ:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Produced;
import org.apache.kafka.streams.state.KeyValueStore;

KStream<String, OrderEvent> orders =
    builder.stream(
        "orders",
        Consumed.with(Serdes.String(), orderEventSerde)
    );

KTable<String, Long> customerOrderCounts = orders
    .selectKey((ignoredKey, event) -> event.customerId())
    .groupByKey(Grouped.with(Serdes.String(), orderEventSerde))
    .count(
        Materialized.<String, Long, KeyValueStore<Bytes, byte[]>>as(
            "customer-order-count"
        )
        .withKeySerde(Serdes.String())
        .withValueSerde(Serdes.Long())
    );

customerOrderCounts.toStream().to(
    "customer-order-counts",
    Produced.with(Serdes.String(), Serdes.Long())
);
~~~

Ví dụ minh họa topology: event được rekey theo customerId, groupByKey và count tạo state store tên customer-order-count. Kafka Streams quản lý changelog topic cho store nếu logging được bật.

Vì key được thay đổi từ key ban đầu sang customerId, topology có thể tạo repartition topic trước bước aggregation để bảo đảm record cùng customer đi vào cùng task. Repartition topic và changelog topic phục vụ hai giai đoạn khác nhau.

### 4.1. Vì sao nên đặt tên store rõ ràng?

Tên store ổn định giúp:

- Tìm changelog topic trong Kafka.
- Quan sát state store qua Interactive Queries.
- Đọc log/metrics restore dễ hơn.
- Quản lý migration khi topology thay đổi.

Nếu không đặt tên, Kafka Streams có thể tạo tên store nội bộ dựa trên topology. Tên được sinh tự động có thể thay đổi khi topology được sửa, gây khó khăn cho việc theo dõi và phục hồi.

### 4.2. Logging mặc định và tắt changelog

Với state store có logging được bật, Kafka Streams ghi state change vào changelog topic để phục hồi. Có thể cấu hình store logging thông qua Materialized hoặc StoreBuilder.

Ví dụ tắt logging:

~~~java
Materialized.<String, Long, KeyValueStore<Bytes, byte[]>>as(
    "temporary-order-count"
)
.withKeySerde(Serdes.String())
.withValueSerde(Serdes.Long())
.withLoggingDisabled();
~~~

Khi tắt logging, state store không còn changelog để khôi phục. Nếu local state mất, ứng dụng có thể phải rebuild từ source topic nếu topology và dữ liệu nguồn cho phép. Nếu source topic đã xóa dữ liệu cũ hoặc chỉ giữ trạng thái không đủ để tái tạo kết quả, state có thể không khôi phục được.

Chỉ tắt logging khi đã đánh giá rõ trade-off và có chiến lược rebuild. Với state nghiệp vụ cần phục hồi sau mất disk hoặc failover, giữ changelog logging là lựa chọn thông thường.

## 5. Changelog compaction, tombstone và retention

Changelog topic thường dùng log compaction để giữ trạng thái mới nhất theo key. Khi một key được cập nhật nhiều lần, cleaner có thể loại các phiên bản cũ và giữ bản mới nhất.

~~~mermaid
flowchart LR
    A["customer-7 → 1"] --> B["customer-7 → 2"]
    B --> C["customer-7 → 3"]
    C --> D["Compaction"]
    D --> E["customer-7 → 3"]
~~~

Compaction chạy nền, không xóa record cũ ngay sau mỗi lần update. Log có thể tạm thời chứa nhiều phiên bản của cùng key.

### 5.1. Tombstone

Khi state store xóa một key, Kafka Streams có thể ghi record có key đó và value null vào changelog. Record này gọi là tombstone. Tombstone cho log cleaner biết key cần được xóa khỏi trạng thái compacted.

Nếu không có tombstone, key đã bị xóa ở local store có thể xuất hiện trở lại khi restore từ changelog cũ.

Tombstone cũng có thời gian tồn tại theo cấu hình delete retention của Kafka. Không thay đổi các config cleanup của internal changelog tùy tiện vì có thể ảnh hưởng khả năng phục hồi.

### 5.2. Key-value store và window store

Key-value store thường cần giữ trạng thái mới nhất cho mỗi key nên changelog dùng compact.

Window store có nhiều phiên bản theo key và window timestamp. Dữ liệu cũ có thể hết hạn theo retention của window. Internal topic cho windowed store có thể dùng cleanup policy kết hợp compact và delete để vừa compact vừa loại dữ liệu hết retention.

Kafka Streams quản lý các cấu hình nội bộ này theo loại store và topology. Khi cấu hình window retention bằng API Materialized/window store, cần bảo đảm retention phù hợp với nghiệp vụ và yêu cầu restore.

### 5.3. Retention của window store

Ví dụ khai báo retention cho một windowed aggregation:

~~~java
import java.time.Duration;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.state.WindowStore;

Materialized.<String, Long, WindowStore<Bytes, byte[]>>as(
    "customer-hourly-count"
)
.withKeySerde(Serdes.String())
.withValueSerde(Serdes.Long())
.withRetention(Duration.ofDays(7));
~~~

Ví dụ cần các import Duration, WindowStore và Bytes. Cấu hình retention phải phù hợp với window size, grace period, late event policy và phiên bản Kafka Streams. Không đặt retention thấp hơn khoảng thời gian cần giữ window state để xử lý event đến muộn.

## 6. State store restore sau restart

Local state store được đặt dưới state.dir. Với RocksDB, mỗi task/store có thư mục dữ liệu cục bộ và checkpoint offset để Kafka Streams biết phần changelog đã áp dụng.

### 6.1. Trường hợp local state còn hợp lệ

Nếu instance restart trên cùng node và state directory vẫn còn:

1. Kafka Streams tìm local task state.
2. Đọc checkpoint offset.
3. Xác định phần changelog mới hơn checkpoint.
4. Restore phần còn thiếu.
5. Đưa task vào trạng thái hoạt động khi đã bắt kịp.

Đây thường là đường phục hồi nhanh hơn so với dựng lại store từ đầu.

### 6.2. Trường hợp local state bị mất

Nếu pod bị thay thế và local disk là ephemeral, state directory có thể mất. Kafka Streams cần đọc changelog để rebuild local state.

Thời gian restore phụ thuộc:

- Kích thước state store.
- Số record cần đọc từ changelog.
- Throughput broker/network.
- Disk write throughput và RocksDB compaction.
- Số task được restore đồng thời.
- Tải của broker và số replica.

State store lớn có thể làm application mất nhiều thời gian mới sẵn sàng xử lý task.

### 6.3. Task migration và rebalance

Khi consumer group rebalance hoặc instance rời group, Kafka Streams có thể chuyển task sang instance khác. Instance mới phải có state local hợp lệ hoặc restore từ changelog.

Nếu task chuyển thường xuyên giữa các instance, thời gian restore lặp lại có thể làm tăng processing latency. Cần ổn định deployment, tránh restart liên tục và cân nhắc standby replicas.

## 7. Standby replica giúp giảm thời gian failover

Kafka Streams có thể duy trì standby task trên instance khác. Standby task không xử lý input như active task, nhưng tiêu thụ changelog để giữ state store gần đồng bộ.

Khi active task gặp sự cố, standby có thể được nâng thành active với ít dữ liệu cần restore hơn.

~~~mermaid
flowchart TB
    I[Input topic] --> A[Active task on instance A]
    A --> S[Active local state store]
    S --> C[Changelog topic]
    C --> R[Standby task on instance B]
    R --> RS[Standby local state store]
    A -.-> X[Instance A fails]
    RS --> P[Promote standby to active]
    P --> O[Continue processing]
~~~

Cấu hình số standby:

~~~properties
num.standby.replicas=1
~~~

Số standby là số bản task state dự phòng mà Kafka Streams cố gắng duy trì, không phải replication factor của changelog topic.

### 7.1. Standby replica khác broker replica

Hai cơ chế bảo vệ hai lớp khác nhau:

| Cơ chế | Bảo vệ |
|---|---|
| Changelog topic replication factor | Dữ liệu changelog khi broker hoặc disk broker lỗi |
| num.standby.replicas | Local state store của Kafka Streams task khi một application instance lỗi |

Có standby nhưng changelog topic replication factor thấp vẫn có rủi ro mất dữ liệu khi broker gặp sự cố. Ngược lại, changelog topic có nhiều broker replica nhưng không có standby thì task mới có thể phải restore nhiều dữ liệu khi failover.

### 7.2. Điều kiện để standby hữu ích

- Cần có đủ application instances để đặt active và standby trên các process khác nhau.
- Standby phải có thời gian đọc changelog và bắt kịp state.
- Broker phải đủ capacity để phục vụ changelog consumers.
- Assignment cần tránh đặt active và standby của cùng task trên cùng failure domain nếu mục tiêu là chịu lỗi node/rack.
- Theo dõi recovery lag để biết standby có thực sự gần đồng bộ hay không.

Nếu chỉ chạy một instance, num.standby.replicas=1 không tạo được standby trên một process khác. Muốn HA thực sự cần triển khai nhiều instance của cùng application.id trên các node/failure domain phù hợp.

## 8. Cấu hình Kafka Streams cho state store recovery

Một số cấu hình quan trọng:

| Cấu hình | Vai trò |
|---|---|
| application.id | Định danh logical Streams application và namespace internal topics |
| state.dir | Thư mục local lưu state store và metadata task |
| replication.factor | Replication factor cho internal topics do Kafka Streams tạo |
| num.standby.replicas | Số standby task cần duy trì |
| processing.guarantee | Chọn at-least-once hoặc exactly-once processing |
| commit.interval.ms | Chu kỳ commit/flush theo processing guarantee và cấu hình |
| acceptable.recovery.lag | Ngưỡng recovery lag dùng trong quyết định task assignment ở các phiên bản hỗ trợ |
| state.cleanup.delay.ms | Thời gian chờ trước khi xóa state directory của app/task cũ theo lifecycle |

Ví dụ cấu hình:

~~~properties
application.id=orders-state-app
bootstrap.servers=localhost:9092
state.dir=/var/lib/kafka-streams/orders-state-app
replication.factor=3
num.standby.replicas=1
processing.guarantee=exactly_once_v2
commit.interval.ms=1000
~~~

Giá trị replication.factor=3 phù hợp với cluster có ít nhất ba broker. Với lab một broker, có thể dùng 1; không dùng cấu hình đó cho production cần chịu lỗi broker.

### 8.1. state.dir

state.dir chứa dữ liệu local của Kafka Streams. Trong production:

- Chọn đường dẫn có đủ disk capacity.
- Dùng local SSD nếu workload cần RocksDB I/O cao.
- Bảo đảm mỗi instance/process có state directory riêng.
- Không cho nhiều process Kafka Streams độc lập dùng chung một state directory.
- Nếu dùng ephemeral storage, tính thời gian restore sau mỗi lần thay pod.
- Theo dõi disk usage và RocksDB compaction.

Persist state.dir trên volume có thể giảm thời gian restart cùng node, nhưng không thay thế changelog replication hoặc standby vì volume vẫn có thể mất cùng node.

### 8.2. replication.factor

replication.factor điều khiển replication factor cho internal topics như changelog và repartition topics do Kafka Streams tạo. Giá trị mặc định trong nhiều phiên bản là 1, không đủ khả năng chịu lỗi broker. Giá trị quá thấp làm giảm khả năng chịu lỗi của state log; giá trị lớn hơn số broker có thể khiến việc tạo internal topic thất bại hoặc application không khởi động được.

Khi thay đổi config này, không mặc định các internal topics đã tồn tại tự động được tăng replication factor. Cần kiểm tra metadata và dùng quy trình reassignment riêng nếu cần thay đổi replica của topic đã tạo.

### 8.3. Exactly-once processing

Với processing.guarantee=exactly_once_v2, Kafka Streams dùng Kafka transactions để phối hợp input offsets, output records và changelog updates trong Kafka. Consumer downstream cần dùng isolation.level=read_committed nếu chỉ muốn thấy output đã commit.

Exactly-once của Kafka Streams không tự bao gồm side effect ngoài Kafka như gọi REST API hoặc ghi database tùy ý. Nếu processor ghi database bên ngoài, cần outbox/inbox hoặc cơ chế idempotency riêng.

## 9. Tùy chỉnh logging của state store

State store builder có thể bật/tắt changelog logging hoặc cấu hình topic overrides tùy API và phiên bản.

Ví dụ bật logging với topic config bổ sung:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.state.KeyValueStore;

Map<String, String> changelogConfig = new HashMap<>();
changelogConfig.put("min.insync.replicas", "2");

Materialized.<String, Long, KeyValueStore<Bytes, byte[]>>as(
    "customer-order-count"
)
.withKeySerde(Serdes.String())
.withValueSerde(Serdes.Long())
.withLoggingEnabled(changelogConfig);
~~~

Các topic overrides phải được broker hỗ trợ và phù hợp replication factor/ISR. Không đặt cleanup.policy=delete cho changelog key-value store nếu vẫn cần compaction để khôi phục state. Kiểm tra config thực tế của internal topic sau khi topology tạo topic.

Nếu logging bị tắt bằng withLoggingDisabled, Kafka Streams không có changelog tương ứng để restore store. Đây là lựa chọn ảnh hưởng trực tiếp đến fault tolerance.

## 10. State schema evolution và thay đổi topology

Changelog chứa serialized state value. Khi ứng dụng restart, phiên bản mới phải deserialize được dữ liệu cũ trong changelog. Nếu đổi serde hoặc cấu trúc state value mà không có migration, restoration có thể thất bại.

Các thay đổi cần đánh giá:

- Đổi key serde hoặc value serde.
- Đổi class/record state.
- Đổi schema Avro/Protobuf/JSON.
- Đổi store name trong Materialized.as.
- Đổi application.id.
- Đổi partition count hoặc topology làm task mapping thay đổi.

### 10.1. Giữ tương thích state value

Nếu state value dùng Avro/Protobuf, cần kiểm tra schema compatibility của dữ liệu changelog. Consumer state restore phải đọc được writer schema cũ trong suốt thời gian changelog còn dữ liệu cần thiết.

Nếu dùng Java class serialization hoặc custom serde, thay đổi class/package/field có thể phá khả năng deserialize. Ưu tiên schema format có evolution rules rõ ràng và kiểm thử restore từ dữ liệu cũ.

### 10.2. Đổi store name

Store name thường là một phần của changelog topic name. Đổi tên store có thể khiến Kafka Streams tìm changelog topic mới và không thấy state cũ. Ứng dụng có thể bắt đầu với state store trống rồi rebuild từ input nếu dữ liệu nguồn còn đủ.

Không đổi store name như một refactor nhỏ khi store chứa state lớn. Cần xem đó là một migration có kế hoạch, ước lượng thời gian rebuild và kiểm thử output trong thời gian restore.

### 10.3. Đổi application.id

application.id mới tạo namespace consumer group và internal topics mới. Ứng dụng mới không tự kế thừa local state/changelog của application ID cũ.

Đổi application.id có thể là cách tạo phiên bản ứng dụng song song hoặc reset có chủ đích, nhưng phải quyết định input offsets, auto.offset.reset, output topic và nguy cơ phát lại dữ liệu.

## 11. Phục hồi khi local state hoặc changelog gặp sự cố

### 11.1. Local state store bị mất

Nếu local state mất nhưng changelog còn đầy đủ:

1. Dừng/để Kafka Streams đánh dấu instance lỗi theo lifecycle.
2. Đưa task sang instance có thể phục hồi.
3. Instance mới restore từ changelog.
4. Theo dõi restore progress và task state.
5. Chỉ đưa traffic/query vào store khi task đã sẵn sàng.

Không xóa state directory đang được process sử dụng. Nếu cần cleanup local state, dừng KafkaStreams trước và dùng API cleanup theo lifecycle phù hợp.

### 11.2. Changelog partition bị unavailable

Kiểm tra:

- Broker giữ leader và replica của changelog partition.
- ISR có đủ replica.
- Disk/network/controller health.
- Topic có bị xóa hoặc config bị thay đổi không.
- ACL của application principal.
- Kafka Streams log có lỗi restore/deserialization không.

Không tạo một topic cùng tên bằng tay rồi ghi dữ liệu tùy ý vào đó. Changelog có format và semantics nội bộ; tạo topic rỗng không khôi phục state.

### 11.3. Changelog bị xóa hoặc mất dữ liệu cần thiết

Nếu changelog không còn dữ liệu cần để restore, có thể phải rebuild state từ source topics. Khả năng rebuild phụ thuộc:

- Source topic còn đủ lịch sử không.
- Retention có giữ toàn bộ event cần thiết không.
- Source topic compaction có giữ đủ trạng thái cuối cùng không.
- Topology hiện tại có thể tái tạo state tương đương không.
- Output side effect có được bảo vệ khỏi replay duplicate không.

Nếu source topic chỉ giữ dữ liệu vài ngày nhưng state cần tích lũy nhiều năm, rebuild có thể không thể tạo lại trạng thái ban đầu. Cần backup/export state hoặc chiến lược snapshot nghiệp vụ riêng nếu yêu cầu recovery vượt quá khả năng của changelog.

### 11.4. Reset application

Kafka Streams có Application Reset Tool cho các tình huống muốn reset offsets và internal topics theo quy trình được hỗ trợ. Công cụ này có thể xóa internal topics hoặc thay đổi offsets tùy tham số và phiên bản.

Trước khi reset:

- Dừng tất cả instance của application.
- Sao lưu hoặc ghi lại input offsets cần thiết.
- Xác định input topics, intermediate topics và application.id.
- Đọc kỹ help của đúng Kafka version.
- Kiểm tra tác động đến output và side effects downstream.
- Chạy trên môi trường staging trước khi áp dụng production.

Reset không phải thao tác chữa lỗi mặc định. Nếu chỉ mất local state nhưng changelog còn tốt, restore bình thường thường an toàn hơn reset toàn application.

## 12. Theo dõi state restoration

Một lần restore lớn có thể khiến task chưa sẵn sàng trong một khoảng thời gian. Cần quan sát cả Kafka Streams state và broker side.

### 12.1. Application state

KafkaStreams có lifecycle state như CREATED, REBALANCING, RUNNING, PENDING_SHUTDOWN, NOT_RUNNING và ERROR tùy phiên bản. Có thể đăng ký StateListener để ghi log khi trạng thái thay đổi:

~~~java
KafkaStreams streams = new KafkaStreams(topology, props);

streams.setStateListener((newState, oldState) ->
    log.info(
        "Kafka Streams state changed old={} new={}",
        oldState,
        newState
    )
);

streams.start();
~~~

Trạng thái RUNNING cho biết instance đã hoàn thành các bước cần thiết để chạy topology hiện tại, nhưng không thay thế việc kiểm tra từng task/store hoặc business readiness trong mọi ứng dụng.

### 12.2. Restore listener và metrics

Kafka Streams cung cấp hook/listener cho state restoration trong các API/version tương ứng, cùng metrics về số record restore, tốc độ restore và thời gian restore. Tên callback/config có thể thay đổi theo phiên bản; kiểm tra API Kafka Streams đang dùng trước khi triển khai.

StateRestoreListener nhận các callback như bắt đầu restore, batch đã restore và kết thúc restore. Cần phân biệt listener cho regular task stores với global state stores; API cấu hình và phạm vi callback phụ thuộc Kafka Streams version. Với global state stores, KafkaStreams có API setGlobalStateRestoreListener. Không dùng callback của global store để suy ra tiến độ restore của mọi task store.

Theo dõi:

- Tổng số record đã restore.
- Restore rate và restore latency.
- Changelog consumer lag.
- Task đang RESTORING hay RUNNING.
- Standby task recovery lag.
- RocksDB write/compaction latency.
- Local state directory disk usage.
- Thời gian từ application start đến task ready.

### 12.3. Broker-side monitoring

Đối với changelog topics, theo dõi:

- Partition leader và ISR.
- Under-replicated partitions.
- Offline partitions.
- Produce/fetch request latency.
- Disk usage và log cleaner activity.
- Replication lag.
- Topic cleanup policy và retention config.

Nếu restore chậm, cần phân biệt bottleneck ở Kafka fetch, network, local disk/RocksDB hay số lượng task được restore đồng thời.

Có thể kiểm tra changelog topic bằng CLI ở chế độ chỉ đọc:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic orders-state-app-customer-order-count-changelog

kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders-state-app-customer-order-count-changelog \
  --describe
~~~

Xác minh partition count, replication factor, leader, ISR và cleanup policy. Không dùng kafka-configs để đổi cleanup policy của changelog tùy tiện; cấu hình nội bộ phải còn phù hợp với loại state store.

## 13. Vận hành và tối ưu restore

### 13.1. Giảm kích thước state cần restore

- Chọn store phù hợp với nghiệp vụ.
- Dùng window retention đúng nhu cầu.
- Xóa key khỏi state khi không còn cần và để changelog ghi tombstone.
- Tránh giữ dữ liệu không giới hạn trong store.
- Theo dõi kích thước changelog và local RocksDB.

Không giảm retention chỉ để tiết kiệm disk nếu dữ liệu cũ còn cần cho late events hoặc recovery.

### 13.2. Dùng standby replicas có chủ đích

Standby giúp giảm recovery time nhưng làm tăng:

- Consumer load trên changelog topic.
- Local disk usage trên các instance.
- Network traffic và CPU.
- Số task/store cần quản lý.

Chọn số standby dựa trên RTO, số instance và tài nguyên. Một standby không có ích nếu nó không thể bắt kịp changelog hoặc cùng nằm trên failure domain với active task.

### 13.3. Ổn định topology và deployment

Rolling restart liên tục có thể gây rebalance và restore lặp lại. Nên:

- Dùng application.id ổn định cho cùng logical app.
- Đặt store name tường minh và không đổi tùy tiện.
- Cấp đủ CPU, memory và disk cho RocksDB.
- Cấu hình graceful shutdown để task có thời gian đóng state và commit.
- Triển khai nhiều instance trên các node/failure domain khác nhau.
- Tránh autoscaling dao động mạnh làm task di chuyển liên tục.

### 13.4. Restore từ changelog không phải replay nghiệp vụ

Restore changelog nhằm tái tạo state store để tiếp tục xử lý. Nó không có nghĩa là phát lại output event hoặc gọi lại side effect nghiệp vụ như xử lý input từ đầu.

Nếu chủ động reset input offsets và replay source topic, đó là một hoạt động khác: topology sẽ xử lý lại input và có thể phát output/side effects lần nữa. Cần có idempotency và kế hoạch kiểm soát output.

## 14. Ví dụ cấu hình Spring Kafka Streams

Spring Kafka hỗ trợ cấu hình Kafka Streams qua @EnableKafkaStreams và KafkaStreamsConfiguration.

### 14.1. Cấu hình application

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.streams.StreamsConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafkaStreams;
import org.springframework.kafka.config.KafkaStreamsConfiguration;
import org.springframework.kafka.config.KafkaStreamsDefaultConfiguration;

@Configuration
@EnableKafkaStreams
public class KafkaStreamsConfigurationBean {

    @Bean(name = KafkaStreamsDefaultConfiguration.DEFAULT_STREAMS_CONFIG_BEAN_NAME)
    KafkaStreamsConfiguration streamsConfig() {
        Map<String, Object> props = new HashMap<>();
        props.put(
            StreamsConfig.APPLICATION_ID_CONFIG,
            "orders-state-app"
        );
        props.put(
            StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        props.put(
            StreamsConfig.STATE_DIR_CONFIG,
            "/var/lib/kafka-streams"
        );
        props.put(StreamsConfig.REPLICATION_FACTOR_CONFIG, 3);
        props.put(StreamsConfig.NUM_STANDBY_REPLICAS_CONFIG, 1);
        props.put(
            StreamsConfig.PROCESSING_GUARANTEE_CONFIG,
            StreamsConfig.EXACTLY_ONCE_V2
        );
        props.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest"
        );

        return new KafkaStreamsConfiguration(props);
    }
}
~~~

state.dir là thư mục gốc; Kafka Streams tự tạo thư mục con theo application.id và task. Không tự thêm cùng application.id vào state.dir trừ khi muốn cấu trúc đường dẫn đó một cách có chủ đích.

Trong Spring Kafka, StreamsBuilderFactoryBean quản lý KafkaStreams lifecycle. Không tự tạo một KafkaStreams instance thứ hai cho cùng topology nếu ứng dụng đã dùng factory bean.

### 14.2. Khai báo topology và state store

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Produced;
import org.apache.kafka.streams.state.KeyValueStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderCountTopology {

    @Bean
    KStream<String, OrderEvent> orderCountStream(
            StreamsBuilder builder,
            Serde<OrderEvent> orderEventSerde) {

        KStream<String, OrderEvent> orders = builder.stream(
            "orders",
            Consumed.with(Serdes.String(), orderEventSerde)
        );

        var counts = orders
            .selectKey((key, event) -> event.customerId())
            .groupByKey(Grouped.with(Serdes.String(), orderEventSerde))
            .count(
                Materialized.<String, Long, KeyValueStore<Bytes, byte[]>>as(
                    "customer-order-count"
                )
                .withKeySerde(Serdes.String())
                .withValueSerde(Serdes.Long())
            );

        counts.toStream().to(
            "customer-order-counts",
            Produced.with(Serdes.String(), Serdes.Long())
        );

        return orders;
    }
}
~~~

OrderEvent và Serde<OrderEvent> là kiểu ứng dụng cần cung cấp. Store name customer-order-count giúp nhận diện changelog tương ứng. Nếu key thay đổi qua selectKey, topology có thể tạo repartition topic trước aggregation.

### 14.3. Kiểm tra store sau khi application chạy

Với Interactive Queries, ứng dụng có thể truy cập local state store đang được instance sở hữu. Chỉ query khi store/task đã sẵn sàng và instance hiện tại có assignment phù hợp. Nếu key nằm ở instance khác, cần discovery/routing đến host sở hữu partition tương ứng.

Không đọc trực tiếp RocksDB files khi Kafka Streams đang chạy. Dùng Kafka Streams APIs để query store và lifecycle callbacks/metrics để kiểm tra readiness.

## 15. Bài tập thực hành

### Bài tập 1: Quan sát changelog topic

1. Tạo Kafka Streams application có stateful count store tên customer-order-count.
2. Chạy topology và gửi một số order event.
3. Dùng Kafka CLI liệt kê changelog topic theo application ID và store name.
4. Mô tả partition count, replication factor và cleanup policy.
5. Kiểm tra state store trả về count mới nhất.

### Bài tập 2: Restore sau khi mất local state

1. Chạy application và tạo state cho nhiều customer.
2. Dừng application đúng lifecycle.
3. Sao lưu rồi xóa local state directory trong môi trường lab.
4. Khởi động lại application.
5. Theo dõi restore progress và xác minh state khôi phục đúng.

Không xóa state directory của process đang chạy.

### Bài tập 3: Standby replica

1. Chạy cùng application.id trên ít nhất hai instance.
2. Cấu hình num.standby.replicas=1.
3. Tạo state store có đủ dữ liệu.
4. Quan sát standby task consume changelog.
5. Dừng instance active trong môi trường lab.
6. Quan sát task promotion và thời gian phục hồi.

### Bài tập 4: So sánh logging bật/tắt

1. Tạo một store mặc định có changelog.
2. Tạo store khác với withLoggingDisabled.
3. Ghi dữ liệu vào cả hai store.
4. Xóa local state trong lab và restart.
5. So sánh khả năng restore/rebuild của từng store.

### Bài tập 5: Thay đổi state schema

1. Tạo state value schema v1 và ghi dữ liệu vào store.
2. Lưu changelog từ phiên bản v1.
3. Thay serde/schema sang v2.
4. Restart với changelog cũ.
5. Kiểm tra compatibility và thiết kế migration an toàn.

## 16. Câu hỏi tự kiểm tra

1. State store giải quyết nhu cầu nào trong Kafka Streams?
2. Changelog topic lưu dữ liệu gì?
3. Vì sao local state store không phải nguồn dữ liệu bền vững duy nhất?
4. Changelog topic khác repartition topic ở mục đích nào?
5. Vì sao key-value changelog thường dùng compaction?
6. Tombstone có vai trò gì khi xóa key khỏi state store?
7. Kafka Streams dùng checkpoint để giảm thời gian restore như thế nào?
8. Standby replica khác replication factor của changelog topic ra sao?
9. Vì sao application.id và store name cần ổn định?
10. Tắt changelog logging ảnh hưởng recovery như thế nào?
11. Exactly-once v2 phối hợp state changelog, output và input offsets ra sao?
12. Khi nào đổi state serde có thể làm restore thất bại?
13. Vì sao PostgreSQL/DB side effects không nằm trong exactly-once Kafka Streams?
14. Khi nào cần rebuild state từ source topic?
15. Vì sao không nên xóa internal changelog topic khi application đang chạy?

Changelog topic là bản ghi phục hồi của state store trong Kafka Streams. Khi local state mất hoặc task chuyển instance, Kafka Streams dùng changelog để dựng lại state; standby replica có thể rút ngắn failover. Thiết kế đúng logging, replication, schema evolution và monitoring giúp stateful stream processing phục hồi có kiểm soát.
