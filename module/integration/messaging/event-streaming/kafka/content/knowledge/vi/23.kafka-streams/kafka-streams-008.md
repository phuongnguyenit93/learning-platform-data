# Stream task, stream thread và phân bố công việc

Kafka Streams chia một topology thành các **task** gắn với partition đầu vào, rồi phân phối task lên các **stream thread** trong những tiến trình ứng dụng có cùng application ID. Task là đơn vị xử lý logic và quản lý state theo partition; thread là đơn vị thực thi song song trong một application instance. Khi cần scale, có thể tăng số thread hoặc thêm instance, nhưng mức song song tối đa vẫn bị giới hạn bởi số task mà topology tạo ra.

Hiểu đúng quan hệ giữa application instance, stream thread và task giúp trả lời các câu hỏi vận hành quan trọng: một topic có 12 partition thì tạo được bao nhiêu task, thêm thread có làm tăng parallelism không, vì sao một số thread bị idle, và standby task giúp phục hồi state sau rebalance như thế nào.

## 1. Ba cấp thực thi: application instance, stream thread và task

Một Kafka Streams application có thể chạy trên một hoặc nhiều JVM/container. Mỗi tiến trình chạy ứng dụng được xem là một **application instance**. Trong mỗi instance, Kafka Streams tạo một hoặc nhiều **StreamThread** theo cấu hình num.stream.threads. Mỗi thread được giao một hoặc nhiều **StreamTask** để xử lý.

| Thành phần | Vai trò | Phạm vi |
|---|---|---|
| Application instance | Một tiến trình/JVM/container chạy cùng topology và application.id | Một máy hoặc container |
| Stream thread | Thread sở hữu consumer/producer và thực thi các task được phân công | Bên trong một instance |
| Stream task | Đơn vị xử lý gắn với subtopology và partition đầu vào; quản lý processor context và state store tương ứng | Được phân công cho một stream thread tại một thời điểm |
| Standby task | Bản sao state của một stateful task để giảm thời gian phục hồi | Thường đặt trên instance khác với active task |

~~~mermaid
flowchart TB
    subgraph APP1["Application instance A"]
        T11["StreamThread 1"] --> A1["Active task 0_0"]
        T11 --> A2["Active task 0_1"]
        T12["StreamThread 2"] --> A3["Active task 0_2"]
        T12 --> S1["Standby task 0_3"]
    end
    subgraph APP2["Application instance B"]
        T21["StreamThread 1"] --> A4["Active task 0_3"]
        T21 --> S2["Standby task 0_0"]
        T22["StreamThread 2"] --> A5["Active task 0_4"]
        T22 --> S3["Standby task 0_1"]
    end
~~~

Sơ đồ minh họa một cách phân công có thể xảy ra; số task, vị trí active/standby và số thread thực tế phụ thuộc topology, partition, cấu hình và assignor. Không có quy tắc cố định rằng mỗi thread chỉ xử lý một task.

Một thread có thể xử lý nhiều task theo lượt. Trong một thread, việc xử lý task diễn ra tuần tự; hai task được giao cho cùng thread không chạy đồng thời trên hai CPU. Các thread khác nhau có thể xử lý task song song. Vì vậy:

- Tăng num.stream.threads có thể tận dụng thêm CPU trong cùng instance nếu còn task chưa được xử lý song song.
- Thêm application instance có thể cung cấp thêm thread và tài nguyên, sau đó task được rebalance giữa các instance.
- Tăng thread/instance không tự tạo thêm task nếu số partition đầu vào vẫn giữ nguyên.

## 2. Task được tạo từ subtopology và partition đầu vào

Kafka Streams không tạo task theo số thread. Nó phân tích topology thành các **subtopology**. Một subtopology là phần đồ thị xử lý có thể chạy độc lập theo các partition đầu vào; các ranh giới repartition thường chia topology thành nhiều subtopology.

Task ID thường có dạng subtopology-partition, ví dụ 0_0, 0_1, 1_0. Phần đầu xác định subtopology, phần sau xác định partition index của task. Task ID là định danh logic của đơn vị xử lý; stream thread và instance đang chạy task có thể thay đổi sau rebalance.

Với một subtopology đọc một topic có 6 partition, Kafka Streams thường tạo 6 task cho subtopology đó:

~~~text
Topic orders (6 partitions)
        |
        v
Subtopology 0
        |
        +-- Task 0_0 -> partition 0
        +-- Task 0_1 -> partition 1
        +-- Task 0_2 -> partition 2
        +-- Task 0_3 -> partition 3
        +-- Task 0_4 -> partition 4
        +-- Task 0_5 -> partition 5
~~~

Nếu một subtopology có nhiều source topic, các partition tương ứng theo index được phối hợp trong task; số task không đơn giản bằng tổng partition của tất cả topic. Số task của subtopology thường được quyết định bởi số partition lớn nhất trong các source topic của subtopology đó. Với các phép join cần co-partitioning, các topic đầu vào phải có partitioning tương thích: cùng số partition và cách phân phối key tương thích theo yêu cầu của phép join. Cấu hình không phù hợp có thể khiến topology không khởi động hoặc phải repartition dữ liệu.

Ví dụ hai topic:

| Topic | Số partition | Ý nghĩa |
|---|---:|---|
| orders | 6 | Event đơn hàng |
| payments | 6 | Event thanh toán |

Một task có thể xử lý partition 2 của orders cùng partition 2 của payments, phục vụ join theo key. Nếu orders có 6 partition còn payments có 3, task count của subtopology có thể được quyết định bởi 6 partition của orders, nhưng hai topic không co-partitioned cho phép join đó. Cần thiết kế lại partition count hoặc tạo repartition topic phù hợp.

Task là đơn vị logic của processing và state. Một task có thể chứa nhiều processor node, state store và input partition liên quan; nó không đồng nghĩa một record, một processor node hoặc một thread.

## 3. Subtopology và repartition topic

Các thao tác thay đổi key hoặc yêu cầu phân phối lại dữ liệu có thể tạo ranh giới repartition. Kafka Streams ghi dữ liệu trung gian vào internal repartition topic; một subtopology upstream ghi topic đó và subtopology downstream đọc lại topic đó.

Ví dụ:

~~~java
KStream<String, String> orders = builder.stream(
        "orders",
        Consumed.with(Serdes.String(), Serdes.String()));

orders
        .selectKey((oldKey, value) -> extractCustomerId(value))
        .repartition(
                Repartitioned.<String, String>as("orders-by-customer")
                        .withKeySerde(Serdes.String())
                        .withValueSerde(Serdes.String())
                        .withNumberOfPartitions(12))
        .groupByKey()
        .count()
        .toStream()
        .to("customer-order-counts",
                Produced.with(Serdes.String(), Serdes.Long()));
~~~

selectKey() thay key của record. repartition() buộc dữ liệu được ghi và đọc lại theo key mới, tạo một ranh giới phân phối công việc. Subtopology phía sau có thể có tập task dựa trên partition của repartition topic.

~~~mermaid
flowchart LR
    A["orders source partitions"] --> B["Subtopology 0: selectKey"]
    B --> R[("Internal repartition topic")]
    R --> C["Subtopology 1: groupByKey / count"]
    C --> O["customer-order-counts"]
~~~

Repartition có chi phí serialize, produce, consume, disk và network. Không gọi repartition tùy tiện; chỉ dùng khi cần thay đổi partitioning/key hoặc cần bảo đảm co-partitioning. Khi dùng DSL operation như groupBy() hoặc join theo key mới, Kafka Streams có thể tạo repartition nội bộ theo yêu cầu của topology; hãy xem Topology.describe() để xác nhận.

Một topology có nhiều subtopology có thể có số task khác nhau ở từng subtopology. Vì vậy, không chỉ nhìn số partition của topic đầu vào đầu tiên để suy ra toàn bộ task count.

## 4. StreamThread thực thi các task như thế nào?

Mỗi StreamThread là một luồng thực thi độc lập trong application instance. Thread quản lý các thành phần cần cho processing như consumer, producer, task manager và lịch xử lý record. Nó poll input, chuyển record tới task tương ứng, thực thi processor topology, commit tiến độ và xử lý các sự kiện rebalance.

Một thread có thể được giao nhiều task:

~~~text
StreamThread-1
  poll records
    -> Task 0_0: process batch
    -> Task 0_2: process batch
    -> Task 1_0: process batch
  poll tiếp
    -> Task 0_0
    -> Task 0_2
    -> Task 1_0
~~~

Đây là mô tả khái niệm, không phải lịch scheduling cố định. Kafka Streams điều phối task và record theo consumer poll, task state và topology. Một task không được xử lý đồng thời bởi hai stream thread; khi task được chuyển sang thread khác, quyền sở hữu được thay đổi qua cơ chế assignment/rebalance.

Nếu một thread xử lý nhiều task stateful, mỗi task có state store và tiến độ riêng. Một task bị lỗi hoặc cần restore có thể ảnh hưởng tới throughput của thread đang chứa nó; phân phối task hợp lý giúp tránh một thread quá tải trong khi thread khác rảnh.

### num.stream.threads

num.stream.threads xác định số StreamThread trong một application instance. Ví dụ đặt giá trị 3 nghĩa là mỗi instance tạo ba stream thread; nó không có nghĩa topology chỉ có ba task hoặc sẽ tạo ba task.

Các điểm cần nhớ:

- Nếu instance có 2 task nhưng cấu hình 6 thread, tối đa chỉ 2 thread có task active trong subtopology đó; thread còn lại có thể idle.
- Nếu instance được giao 12 task và có 3 thread, mỗi thread có thể xử lý nhiều task theo lượt.
- Nếu một task là bottleneck do logic nặng hoặc state lớn, thêm thread không chia nhỏ task đó.
- Tổng thread trong ứng dụng nhiều instance bằng tổng thread của các instance đang hoạt động, nhưng số active task vẫn bị giới hạn bởi topology.

## 5. Phân phối task giữa nhiều instance

Các instance của cùng một Kafka Streams application phải dùng cùng application.id. Giá trị này được dùng làm consumer group ID và thường là prefix cho internal topics của ứng dụng. Kafka Streams sử dụng group membership và StreamsPartitionAssignor để phân phối task cho các stream thread trên các instance.

~~~mermaid
flowchart TB
    G["application.id = orders-enricher"]
    G --> I1["Instance A"]
    G --> I2["Instance B"]
    G --> I3["Instance C"]
    I1 --> T1["Stream threads A"]
    I2 --> T2["Stream threads B"]
    I3 --> T3["Stream threads C"]
    T1 --> A["Active tasks"]
    T2 --> A
    T3 --> A
~~~

Ví dụ một topology có 12 active tasks, ba instance và mỗi instance có hai stream thread:

| Thành phần | Số lượng |
|---|---:|
| Application instance | 3 |
| Stream thread mỗi instance | 2 |
| Tổng stream thread | 6 |
| Active task của topology | 12 |
| Task trung bình mỗi thread | 2 |

Trong ví dụ này, mỗi thread xử lý trung bình hai task. Assignment thực tế có thể khác để cân bằng tải và tuân theo các ràng buộc state/standby; không nên dựa vào phép chia trung bình để giả định task cụ thể nằm trên thread nào.

Nếu chỉ có 4 task nhưng tổng cộng 9 stream thread, nhiều thread không có active task. Nếu có 20 task nhưng chỉ 4 thread, mỗi thread phải xử lý nhiều task hơn. Hãy scale dựa trên task count, CPU, processing latency, state restore và throughput thay vì chỉ tăng số thread.

### Vai trò của application.id

- Tất cả instance của cùng một logical Streams application dùng cùng application.id.
- Hai ứng dụng độc lập không được dùng chung application.id, vì chúng có thể tranh cùng consumer group và internal topics.
- Môi trường dev, staging và production nên có ID riêng để không chia sẻ state hoặc assignment.
- Đổi application.id tạo một logical application khác, thường kéo theo internal topics và state riêng; không phải cách scale một ứng dụng đang chạy.

state.dir là thư mục local lưu state store và dữ liệu local của instance. Mỗi instance/process cần vùng lưu trữ riêng và đủ dung lượng. Không cấu hình nhiều process cùng dùng một thư mục state local.

## 6. Active task và standby task

**Active task** nhận input partition và thực thi processor topology. **Standby task** duy trì bản sao state store cho một active task khác, thường trên instance khác, bằng cách đọc changelog topic. Standby không xử lý input business record như active task; mục tiêu chính là giữ state gần đồng bộ để giảm thời gian restore khi active task phải chuyển nơi chạy.

num.standby.replicas cấu hình số standby replica mong muốn cho mỗi stateful task. Giá trị 0 nghĩa là không tạo standby task. Nếu đặt 1, Kafka Streams cố gắng duy trì một bản sao standby theo khả năng assignment và số instance hiện có.

~~~mermaid
flowchart LR
    IN[("Input topic partition 3")] --> A["Active task 0_3"]
    A --> S[("State store")]
    S --> CH[("Changelog topic partition 3")]
    CH --> ST["Standby task 0_3"]
    ST --> SS[("Standby state store")]
~~~

State store có thể được khôi phục từ changelog topic. Standby task đọc changelog để duy trì state; khi active instance gặp sự cố, standby có thể được promote thành active nếu assignment và điều kiện phục hồi cho phép. Nếu không có standby, task mới phải restore state từ changelog trước khi xử lý đầy đủ.

Lợi ích và chi phí:

| Cấu hình | Lợi ích | Chi phí |
|---|---|---|
| num.standby.replicas=0 | Ít tài nguyên và traffic changelog hơn | Failover có thể phải restore state lâu |
| num.standby.replicas=1 | Có một bản sao state dự phòng cho task stateful | Tốn thêm disk, network, broker I/O và processing |
| Nhiều standby replicas | Có thể tăng khả năng phục hồi khi nhiều instance lỗi | Tăng đáng kể tài nguyên và không phải lúc nào cũng có đủ instance để phân bố |

Standby task hữu ích với topology stateful như aggregate, join hoặc windowed operation. Topology stateless không có state store cần phục hồi theo cách này. Standby không thay thế replication factor của Kafka topic; changelog topic vẫn cần replication phù hợp để state có thể khôi phục.

Không đặt standby replica lớn hơn số instance có thể phân bố một cách hữu ích. Với một instance duy nhất, standby trên cùng process không đem lại khả năng chịu lỗi khi process/máy mất; cần nhiều instance độc lập để tăng tính sẵn sàng.

## 7. GlobalKTable và GlobalStreamThread khác task thông thường

GlobalKTable được sao chép toàn bộ dữ liệu tới mỗi application instance, thay vì chia partition state như KTable thông thường. Kafka Streams sử dụng GlobalStreamThread để duy trì global state trên instance. Vì vậy, không tính GlobalKTable như một tập active/standby task giống các source partition task.

| Cấu trúc | Cách phân phối state |
|---|---|
| KTable thông thường | Chia theo partition/task; mỗi task giữ phần state tương ứng |
| GlobalKTable | Mỗi instance giữ bản sao toàn bộ dữ liệu |
| GlobalStreamThread | Thread riêng duy trì global store, tách khỏi các StreamThread xử lý task thông thường |

GlobalKTable thuận tiện khi bảng tham chiếu nhỏ và cần join mà không repartition luồng chính theo key của bảng. Nhưng nếu bảng global lớn, mọi instance đều phải tải và lưu toàn bộ dữ liệu; tăng số instance cũng nhân dung lượng state và traffic restore.

## 8. Tính parallelism và chọn số partition

Để ước lượng khả năng song song, hãy tính task cho từng subtopology rồi so với tổng stream thread:

~~~text
active parallelism tối đa của một subtopology
    ~= số task được tạo từ partition đầu vào của subtopology

tổng stream thread
    = số application instance x num.stream.threads mỗi instance
~~~

Ví dụ:

| Kịch bản | Task | Tổng thread | Nhận xét |
|---|---:|---:|---|
| 1 topic, 4 partition | 4 | 2 | Hai thread có thể xử lý khoảng hai task mỗi thread |
| 1 topic, 4 partition | 4 | 8 | Tối đa bốn thread có task active; thread dư có thể idle |
| 1 topic, 12 partition | 12 | 6 | Có thể phân bố khoảng hai task mỗi thread |
| 1 topic, 12 partition | 12 | 12 | Có thể có một task trên mỗi thread nếu assignment/capacity phù hợp |
| 1 topic, 1 partition | 1 | 16 | Một task không thể được chia thành 16 task bằng cách tăng thread |

Đây là giới hạn song song logic; throughput thực tế còn phụ thuộc record rate, xử lý CPU, state store, RocksDB, disk, network, broker, producer batching, consumer poll và external calls.

### Khi nào cần tăng partition?

Nếu một subtopology chỉ có 4 task nhưng cần nhiều hơn bốn luồng xử lý độc lập, tăng số stream thread không đủ. Có thể cần tăng partition của source topic hoặc thiết kế lại topology để có nhiều task.

Tuy nhiên, tăng partition của topic đã có dữ liệu có thể làm thay đổi kết quả hash partitioning cho key mới. Event của cùng một key có thể trước đây vào partition cũ, sau thay đổi lại vào partition khác, ảnh hưởng ordering theo key và state migration. Cần đánh giá:

- Ordering theo key có phải invariant nghiệp vụ không.
- Topic có compacted hay không.
- Consumer/state store có cần rebuild hoặc migrate không.
- Các topic join có cùng partition count/partitioner không.
- Có cần tạo topic mới và chuyển luồng thay vì tăng partition tại chỗ không.

Chọn partition count từ đầu dựa trên throughput mục tiêu, số consumer/task dự kiến, key cardinality, retention, kích thước state và khả năng broker. Không chỉ chọn partition bằng số CPU.

## 9. Ví dụ cấu hình và khởi chạy nhiều thread

Ví dụ topology đơn giản đọc orders, chuẩn hóa value rồi ghi orders-normalized:

~~~java
import java.util.Properties;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Produced;

public class OrdersNormalizer {
    public static void main(String[] args) {
        StreamsBuilder builder = new StreamsBuilder();

        builder.stream(
                    "orders",
                    Consumed.with(Serdes.String(), Serdes.String()))
                .mapValues(String::toUpperCase)
                .to(
                    "orders-normalized",
                    Produced.with(Serdes.String(), Serdes.String()));

        Topology topology = builder.build();
        System.out.println(topology.describe());

        Properties props = new Properties();
        props.put(StreamsConfig.APPLICATION_ID_CONFIG, "orders-normalizer");
        props.put(
                StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
                "broker-1:9092,broker-2:9092,broker-3:9092");
        props.put(StreamsConfig.NUM_STREAM_THREADS_CONFIG, 3);
        props.put(StreamsConfig.NUM_STANDBY_REPLICAS_CONFIG, 1);
        props.put(StreamsConfig.STATE_DIR_CONFIG, "/var/lib/orders-normalizer/state");

        KafkaStreams streams = new KafkaStreams(topology, props);
        streams.setStateListener((newState, oldState) ->
                System.out.printf("Kafka Streams state: %s -> %s%n",
                        oldState, newState));

        Runtime.getRuntime().addShutdownHook(new Thread(streams::close));
        streams.start();
    }
}
~~~

Ví dụ dùng API Kafka Streams hiện đại; import và API chi tiết cần khớp phiên bản dependency của dự án. Nếu chạy nhiều process trên cùng host, mỗi process cần state.dir riêng. Trong container, nên mount volume local phù hợp nếu cần giữ state qua restart; Kafka changelog vẫn là nguồn phục hồi bền vững cho state store được cấu hình logging.

Nếu topic orders có 9 partition và một instance đặt num.stream.threads=3, topology đơn giản này tạo khoảng 9 task trong subtopology nguồn; mỗi thread có thể được giao khoảng 3 task. Chạy thêm instance với cùng application.id sẽ chia các task active giữa các instance, không tạo thêm task nếu partition count không đổi.

topology.describe() mô tả processor graph và subtopology, không phải báo cáo task đang nằm trên thread/instance nào. Để quan sát assignment runtime, dùng Kafka Streams metadata APIs, JMX metrics và log lifecycle theo phiên bản đang triển khai.

## 10. Rebalance và di chuyển task

Kafka Streams rebalance khi membership hoặc điều kiện assignment thay đổi, ví dụ:

- Application instance khởi động hoặc dừng.
- Stream thread bị lỗi hoặc được thêm/bớt do thay đổi cấu hình/restart.
- Input topic partition hoặc subscription thay đổi.
- Instance mất heartbeat hoặc không đáp ứng group protocol.
- Topology/internal topic thay đổi làm task set thay đổi.

Trong quá trình rebalance, task có thể bị revoke khỏi thread cũ và assign cho thread/instance mới. Với stateful task, instance mới phải khôi phục state từ local state còn hợp lệ, standby hoặc changelog topic trước khi xử lý bình thường.

~~~mermaid
sequenceDiagram
    participant A as Instance A / Thread 1
    participant G as Streams group coordinator
    participant B as Instance B / Thread 1
    participant K as Changelog topic

    A->>G: Membership change / rebalance
    G-->>A: Revoke task 0_2
    G-->>B: Assign task 0_2
    B->>K: Restore state if required
    K-->>B: Changelog records
    B->>B: Promote task to active and resume processing
~~~

Thời gian phục hồi phụ thuộc kích thước state, tốc độ đọc changelog, disk, network, cache và standby lag. Có standby gần đồng bộ có thể giảm thời gian restore, nhưng không loại bỏ hoàn toàn rebalance hoặc mọi lỗi.

Không nên restart toàn bộ instance cùng lúc khi có state lớn nếu không cần thiết. Rolling restart, graceful close và quan sát task migration giúp giảm số task phải restore đồng thời.

## 11. State store, changelog và task ownership

State store được gắn với task/partition để mỗi task duy trì phần state tương ứng. Ví dụ aggregate số đơn theo customer sẽ lưu state phân vùng theo key partition. Kafka Streams có thể tạo changelog topic để ghi các thay đổi state store, giúp phục hồi state khi local disk mất hoặc task được chuyển instance.

Các thành phần:

- Local state store: bản state trên disk của instance, thường dùng RocksDB cho store persistent mặc định.
- Changelog topic: log Kafka lưu cập nhật state store để restore.
- Active task: xử lý input và cập nhật state store.
- Standby task: đọc changelog để giữ bản sao state gần nhất.
- Restore consumer: đọc changelog khi task cần khôi phục state.

Changelog partitioning gắn với task/state store. Không xóa changelog topic hoặc đổi cấu hình cleanup/retention tùy tiện; nếu mất changelog và local state không còn, task có thể không khôi phục được state mong muốn.

num.standby.replicas chỉ là một phần của availability. Cần replication factor và ISR phù hợp cho internal topics, disk bền vững, rack/zone placement, monitoring restore lag và runbook phục hồi.

## 12. Quan sát task và thread trong production

Theo dõi cả cấp thread, task và ứng dụng:

| Nhóm | Chỉ số/trạng thái cần theo dõi | Ý nghĩa |
|---|---|---|
| Application | RUNNING, REBALANCING, ERROR, NOT_RUNNING | Ứng dụng có hoạt động ổn định không |
| Stream thread | Số thread sống, thread state, uncaught exception | Phát hiện thread chết hoặc dừng xử lý |
| Task | Active/standby count, task created/closed, task migration | Kiểm tra assignment và phân bố công việc |
| Processing | Records processed, process latency, punctuate latency | Phát hiện processor chậm |
| Consumer | Records consumed, poll latency, commit latency, lag | Phát hiện input không theo kịp |
| State | Restore rate, restore latency, standby lag, state size | Ước lượng khả năng phục hồi |
| Rebalance | Số lần và thời gian rebalance | Phát hiện group churn |
| Internal topics | Changelog/repartition throughput, under-replicated partitions | Phát hiện bottleneck hoặc rủi ro state |

Tên metric và tag cụ thể có thể thay đổi theo Kafka Streams version và metrics reporter. Dùng JMX hoặc metrics integration của ứng dụng, nhưng tránh hard-code dashboard theo tên metric chưa xác nhận ở phiên bản đang chạy.

Log nên có application.id, client.id, thread name, task ID, topic/partition và event ID nếu có. Không log payload nhạy cảm. Khi task migration xảy ra, các trường này giúp liên hệ lỗi processor với instance/thread cụ thể.

## 13. Troubleshooting phân bố công việc

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
|---|---|---|
| Một số thread idle | Số task ít hơn số thread hoặc assignment không có task cho thread đó | Xem task count từng subtopology và partition đầu vào |
| Một thread có quá nhiều task | Tổng thread ít, partition/task nhiều hoặc assignment/capacity không cân bằng | Theo dõi process latency, CPU và task assignment; tăng thread/instance nếu còn parallelism |
| Thêm instance nhưng throughput không tăng | Task count đã là giới hạn hoặc bottleneck nằm ở processor/state/broker | Kiểm tra task parallelism và thời gian xử lý từng task |
| Một task xử lý chậm | Key skew, partition nóng, state lớn hoặc logic nặng | Kiểm tra phân bố key, record rate và processor latency |
| Rebalance liên tục | Instance restart, thread chết, poll/processing chậm hoặc hạ tầng chập chờn | Xem state transition, uncaught exception, heartbeat và thời gian xử lý |
| Restore state lâu | Changelog lớn, standby lag, disk/network chậm | Theo dõi restore rate, state size và changelog throughput |
| Join không chạy/không khởi động | Input topics không co-partitioned hoặc key serde/partitioner không phù hợp | Kiểm tra partition count, key và repartition topology |
| Task chuyển instance nhưng output trùng | Xử lý lại trong cửa sổ commit/rebalance hoặc side effect ngoài Kafka không idempotent | Kiểm tra processing guarantee và idempotency của side effect |

Khi chẩn đoán, bắt đầu từ Topology.describe() để biết topology có bao nhiêu subtopology và ranh giới repartition. Sau đó so sánh partition count của source/repartition topics với số task runtime, số thread và assignment trên từng instance.

## 14. Những hiểu nhầm thường gặp

- **“Một stream thread tương đương một task.”** Một thread có thể xử lý nhiều task; task mới là đơn vị logic gắn với partition.
- **“num.stream.threads tăng thì task count tăng.”** Thread chỉ tăng năng lực thực thi; task count phụ thuộc topology và partition.
- **“Mỗi topic luôn tạo đúng một task.”** Một topic nhiều partition tạo nhiều task cho subtopology; nhiều topic có thể được phối hợp theo partition index.
- **“Thêm instance luôn tăng throughput.”** Nếu task count không đủ hoặc bottleneck nằm ở nơi khác, instance mới có thể idle.
- **“Task ID là thread ID.”** Task ID định danh subtopology/partition; thread có thể thay đổi sau rebalance.
- **“Standby task xử lý business record song song với active.”** Standby chủ yếu duy trì state từ changelog để hỗ trợ failover.
- **“GlobalKTable được chia partition như KTable.”** GlobalKTable được sao chép toàn bộ trên mỗi instance qua GlobalStreamThread.
- **“Tăng partition không ảnh hưởng key ordering.”** Hash mapping có thể thay đổi; event cùng key có thể đi sang partition khác sau thay đổi.
- **“Topology.describe() cho biết runtime assignment.”** Nó mô tả graph/subtopology, không phải task placement đang chạy.

## 15. Checklist thiết kế và vận hành

- [ ] Xác định source topic, partition count và task count cho từng subtopology.
- [ ] Phân biệt application instance, StreamThread, StreamTask và GlobalStreamThread.
- [ ] Dùng cùng application.id cho các instance của một logical application; tách ID giữa môi trường/ứng dụng độc lập.
- [ ] Chọn num.stream.threads theo CPU và số task có thể chạy song song.
- [ ] Không tăng thread vượt xa task count nếu không có lý do rõ ràng.
- [ ] Kiểm tra co-partitioning cho join và dùng repartition khi cần đổi key/partitioning.
- [ ] Đánh giá tác động ordering/key/state trước khi tăng partition.
- [ ] Chọn num.standby.replicas theo RTO, state size và số instance độc lập.
- [ ] Bảo vệ changelog/repartition topics bằng replication, ACL và cleanup policy phù hợp.
- [ ] Dùng state.dir riêng, đủ dung lượng cho mỗi instance.
- [ ] Theo dõi task assignment, thread state, rebalance, consumer lag và state restore.
- [ ] Kiểm thử restart instance, mất thread, rebalance và restore state.
- [ ] Giữ side effect ngoài Kafka idempotent nếu task có thể được xử lý lại.

Kafka Streams dùng task để chia topology theo partition và dùng stream thread để thực thi các task trên từng application instance. Số task quyết định giới hạn parallelism logic; số thread và số instance quyết định tài nguyên có thể dùng để xử lý các task đó. Active/standby task cùng changelog topic giúp duy trì và phục hồi state khi rebalance. Khi thiết kế, hãy tính task theo từng subtopology, bảo đảm co-partitioning cho join và scale dựa trên số task thực tế thay vì chỉ tăng thread hoặc container.
