# Theo dõi topology, trạng thái luồng và chỉ số state store

Một ứng dụng Kafka Streams có thể vẫn chạy tiến trình Spring Boot nhưng topology bên trong đã dừng, đang rebalance kéo dài hoặc mất một stream thread. Tương tự, endpoint health có thể báo UP trong khi consumer lag tăng, state store phục hồi chậm hoặc RocksDB bắt đầu ghi dữ liệu chậm. Vì vậy, vận hành Kafka Streams cần kết hợp ba lớp quan sát: **cấu trúc topology**, **trạng thái runtime** và **metrics của luồng cùng state store**.

Spring Cloud Stream Kafka Streams binder cung cấp endpoint Actuator để lấy mô tả topology, health indicator để theo dõi stream thread và khả năng xuất metrics qua Micrometer MeterRegistry. Kafka Streams bổ sung metrics ở cấp client, thread, task, processor node, state store và record cache. Các chỉ số này giúp xác định điểm nghẽn trong xử lý, rebalance, commit, restore state và truy cập dữ liệu cục bộ.

Bài học này hướng dẫn bật các endpoint cần thiết, đọc trạng thái KafkaStreams, lựa chọn metric theo recording level, giám sát state store in-memory/RocksDB, xây dựng cảnh báo và kiểm thử tình huống vận hành.

## 1. Ba lớp cần quan sát

Không có một chỉ số đơn lẻ nào mô tả đầy đủ sức khỏe của một topology. Hãy tách việc quan sát thành ba lớp:

| Lớp | Câu hỏi cần trả lời | Công cụ hoặc dữ liệu |
|---|---|---|
| Topology | Ứng dụng đang xây dựng những processor, source, sink, repartition topic và state store nào? | Endpoint Actuator kafkastreamstopology và topology description. |
| Runtime state | Kafka Streams client, stream thread và task đang ở trạng thái nào? Có thread lỗi, rebalance hoặc restore kéo dài không? | Binder health indicator, KafkaStreams state, thread/task metadata và log. |
| Metrics | Tốc độ nhận/xử lý, commit latency, end-to-end latency, state-store latency, RocksDB I/O và cache đang thay đổi ra sao? | Micrometer MeterRegistry, Actuator metrics, Prometheus hoặc hệ thống metrics tương đương. |

Topology description là bản mô tả cấu trúc được xây dựng từ DSL/Processor API. Nó không phải ảnh chụp trạng thái xử lý từng record. Runtime state cho biết topology đang chạy hay đang chuyển trạng thái; metrics cho biết hiệu năng và hành vi của các thành phần theo thời gian.

~~~mermaid
flowchart TD
    A[Spring Cloud Stream Kafka Streams application] --> B[Topology description]
    A --> C[Runtime health and state]
    A --> D[Micrometer MeterRegistry]
    B --> E[Actuator topology endpoint]
    C --> F[Actuator health endpoint]
    D --> G[Actuator metrics endpoint]
    D --> H[Prometheus / monitoring backend]
    E --> I[Topology visualization]
    F --> J[Operational alerts]
    G --> J
    H --> J
~~~

## 2. Bật Actuator và topology endpoint

Kafka Streams binder cung cấp endpoint:

- **GET /actuator/kafkastreamstopology**: lấy mô tả topology của các processor được quản lý bởi ứng dụng.
- **GET /actuator/kafkastreamstopology/{application-id}**: lấy mô tả topology của processor theo Kafka Streams application ID.

Endpoint topology bị tắt mặc định. Ứng dụng cần Spring Boot Actuator và web runtime; nếu dùng WebFlux, có thể dùng spring-boot-starter-webflux thay cho spring-boot-starter-web.

Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Bật các endpoint cần dùng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,kafkastreamstopology
  endpoint:
    health:
      show-details: when_authorized
~~~

Ví dụ truy vấn:

~~~http
GET /actuator/kafkastreamstopology
GET /actuator/kafkastreamstopology/order-enrichment-v1
~~~

Giá trị trong URL thứ hai là application.id của processor, không phải tên function bean hoặc binding name. Khi ứng dụng có nhiều Kafka Streams processor, hãy xác định đúng application ID trước khi lấy topology tương ứng.

Endpoint trả về mô tả topology. Có thể đưa mô tả này vào công cụ ngoài để hiển thị graph, kiểm tra source/sink, node xử lý, repartition và state store. Endpoint không tự cung cấp dashboard hiệu năng hoặc trạng thái từng node; cần dùng metrics và health cho các câu hỏi đó.

## 3. Đọc topology description

Topology Kafka Streams thường có các loại node:

- **Source:** đọc record từ một hoặc nhiều input topic.
- **Processor:** áp dụng filter, map, aggregate, join, window, suppression hoặc logic tùy chỉnh.
- **Sink:** ghi record tới output topic.
- **Repartition:** ghi và đọc lại dữ liệu để thay đổi cách phân vùng/key trước một phép xử lý cần co-partition.
- **State store:** lưu trạng thái cục bộ cho aggregate, join, window hoặc Processor API.

Ví dụ một topology tính tổng tiền theo khách hàng:

~~~mermaid
flowchart LR
    A[(order-amounts)] --> B[Source]
    B --> C[Group by customerId]
    C --> D[Aggregate]
    D <--> E[(amount-by-customer store)]
    D --> F[Sink]
    F --> G[(customer-totals)]
~~~

Khi đọc topology thực tế, hãy xác nhận:

1. Source node đọc đúng topic và đúng số input.
2. Các node repartition xuất hiện ở đúng vị trí cần đổi key.
3. Processor node được nối theo đúng thứ tự nghiệp vụ.
4. State store có tên, loại và processor liên kết đúng.
5. Sink node ghi tới đúng output topic.
6. Topology của từng application ID có đúng như cấu hình function definition.

Nếu một topology thay đổi sau khi thêm join, groupBy hoặc repartition, hãy so sánh topology description giữa các phiên bản triển khai. Thay đổi topology có thể làm thay đổi internal topic, state store và yêu cầu restore dữ liệu.

## 4. Phân biệt KafkaStreams state, stream thread state và task

Kafka Streams có nhiều cấp trạng thái. Không dùng từ “stream state” để chỉ tất cả các cấp vì một client có thể đang RUNNING trong khi một thread đang rebalance hoặc một task đang phục hồi state.

### Trạng thái KafkaStreams client

Trong Kafka 4.4, enum KafkaStreams.State có các giá trị:

| State | Ý nghĩa vận hành |
|---|---|
| CREATED | Đối tượng KafkaStreams đã được tạo nhưng chưa bắt đầu chạy. |
| REBALANCING | Một hoặc nhiều thread đang thu hồi/gán partition hoặc task chưa sẵn sàng xử lý. |
| RUNNING | Các stream thread đang ở trạng thái chạy và active task đã sẵn sàng xử lý. |
| PENDING_SHUTDOWN | Đang đóng tài nguyên theo quy trình shutdown. |
| NOT_RUNNING | Đã dừng sau khi shutdown hoàn tất. |
| PENDING_ERROR | Đang đóng tài nguyên sau một lỗi nghiêm trọng. |
| ERROR | Kafka Streams instance ở trạng thái lỗi; có thể xảy ra khi global thread hoặc toàn bộ stream thread bị chết. |

Chuyển từ RUNNING sang REBALANCING có thể là bình thường khi partition được thu hồi hoặc giao lại. Khi các active task đã sẵn sàng, client có thể trở lại RUNNING. Nếu REBALANCING kéo dài, cần kiểm tra task restoration, rebalance liên tục, broker connectivity và thời gian khởi động state store.

PENDING_SHUTDOWN và PENDING_ERROR là trạng thái chuyển tiếp. Chúng không phải trạng thái hoạt động ổn định; instance cần hoàn tất đóng tài nguyên trước khi sang trạng thái kết thúc tương ứng.

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> REBALANCING
    REBALANCING --> RUNNING
    RUNNING --> REBALANCING
    RUNNING --> PENDING_SHUTDOWN
    REBALANCING --> PENDING_SHUTDOWN
    CREATED --> PENDING_SHUTDOWN
    RUNNING --> PENDING_ERROR
    REBALANCING --> PENDING_ERROR
    PENDING_SHUTDOWN --> NOT_RUNNING
    PENDING_ERROR --> ERROR
~~~

### Trạng thái stream thread

Binder health indicator cung cấp metadata cho từng stream thread, gồm:

- Thread name.
- Thread state: CREATED, RUNNING, PARTITIONS_REVOKED, PARTITIONS_ASSIGNED, PENDING_SHUTDOWN hoặc DEAD.
- Active tasks cùng task ID và partition.
- Standby tasks cùng task ID và partition.

Các giá trị thread state ở bảng này không giống enum KafkaStreams.State. Ví dụ, PARTITIONS_REVOKED là trạng thái của thread trong quá trình rebalance; REBALANCING là trạng thái tổng hợp của KafkaStreams client.

### Task và partition assignment

Topology được chia thành các task theo input partitions. Task có thể là active hoặc standby. Active task thực hiện xử lý; standby task duy trì bản sao state để giảm thời gian phục hồi khi task được chuyển sang instance khác.

Khi điều tra một thread không chạy:

1. Xác định thread state.
2. Kiểm tra active task và partition đang được giao.
3. Xác nhận task có đang restore state store hay chờ partition assignment.
4. So sánh số task với số partition và số instance.
5. Kiểm tra rebalance log và consumer group membership.

Một application ID có thể có nhiều stream thread và task. Health details theo application ID giúp khoanh vùng processor nào có vấn đề khi một Spring Boot process chạy nhiều Kafka Streams processor.

## 5. Bật Kafka Streams binder health indicator

Health indicator của Kafka Streams binder cần spring-boot-starter-actuator. Spring Cloud Stream có thuộc tính management.health.binders.enabled để bật health indicator của binder.

Ví dụ:

~~~yaml
management:
  health:
    binders:
      enabled: true
  endpoint:
    health:
      show-details: when_authorized
  endpoints:
    web:
      exposure:
        include: health,metrics,kafkastreamstopology
~~~

Truy vấn:

~~~http
GET /actuator/health
~~~

Mặc định, endpoint chỉ hiển thị trạng thái tổng quát UP hoặc DOWN. Để xem thread name, state, active task và standby task, đặt management.endpoint.health.show-details thành ALWAYS hoặc WHEN_AUTHORIZED. Trong môi trường production, nên dùng WHEN_AUTHORIZED cùng Spring Security để chỉ người có quyền mới xem chi tiết.

Theo tài liệu Kafka Streams binder, health indicator báo UP khi tất cả Kafka thread đã đăng ký đều ở trạng thái RUNNING. Vì vậy, một đợt rebalance ngắn có thể làm health thay đổi tạm thời. Hãy đặt ngưỡng thời gian và kết hợp metrics trước khi kích hoạt hành động tự phục hồi, tránh restart liên tục trong lúc task đang restore bình thường.

Nếu ứng dụng có nhiều Kafka Streams processor, health của từng processor được phân loại theo application ID. Binder cũng có các binding type KStream, KTable và GlobalKTable; khi hiển thị chi tiết có thể xuất hiện thông tin tương tự ở nhiều health component.

## 6. Xuất Kafka Streams metrics qua Micrometer

Spring Cloud Stream Kafka Streams binder cung cấp Kafka Streams metrics qua Micrometer MeterRegistry. Nếu ứng dụng đã có Actuator và Micrometer trên classpath, các meter có thể được xem qua Actuator metrics endpoint.

Bật endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,kafkastreamstopology
~~~

Liệt kê metric:

~~~http
GET /actuator/metrics
~~~

Đọc một metric cụ thể:

~~~http
GET /actuator/metrics/{metric-name}
~~~

Tên metric, tag và số lượng meter phụ thuộc phiên bản Kafka Streams, Spring Boot, Micrometer và cấu hình recording level. Hãy đọc danh sách từ chính ứng dụng đang chạy trước khi viết dashboard; không sao chép tên metric từ một phiên bản Kafka khác rồi giả định chúng luôn tồn tại.

Nếu cần scrape bằng Prometheus, thêm dependency micrometer-registry-prometheus, expose endpoint prometheus và cấu hình Prometheus scrape. Endpoint /actuator/prometheus là định dạng phục vụ hệ thống metrics, còn /actuator/metrics phù hợp để khám phá và truy vấn một meter qua Actuator.

## 7. Cấu trúc metrics theo client, thread, task và processor node

Kafka Streams có hệ phân cấp metrics. Ở mức vận hành, có thể nhóm như sau:

| Cấp | Phạm vi | Ví dụ metric |
|---|---|---|
| Client | Một KafkaStreams instance/application ID | state, application-id, alive-stream-threads, failed-stream-threads. |
| Thread | Một stream thread | process-rate, poll-rate, commit-latency-avg, process-latency-avg. |
| Task | Một task xử lý các partition cụ thể | Task-level metrics và metrics gắn với processor/store thuộc task. |
| Processor node | Một source, processor hoặc sink node | records-consumed-total, records-produced-total, record-e2e-latency-avg. |
| State store/cache | Store hoặc record cache của task | put-latency-avg, get-rate, RocksDB I/O, cache hit ratio. |

Khi tổng hợp metrics lên dashboard, luôn giữ các tag nhận diện như application ID, client ID, thread ID, task ID, processor node và store scope nếu registry cung cấp. Nếu loại bỏ hết tag, số liệu giữa nhiều processor có thể bị cộng gộp và che mất một task đang lỗi.

## 8. Recording level: info, debug và trace

Kafka Streams cho phép điều chỉnh mức thu thập metrics:

| Recording level | Phạm vi | Khi sử dụng |
|---|---|---|
| info | Các metric nền tảng về client, thread và một số metric state store. | Mặc định phù hợp cho giám sát thường xuyên. |
| debug | Bổ sung nhiều metric về processor, state store, record cache và RocksDB. | Bật khi cần chẩn đoán hiệu năng hoặc vận hành state store. |
| trace | Bổ sung một số metric chi tiết như record end-to-end latency. | Dùng ngắn hạn hoặc khi có mục tiêu chẩn đoán cụ thể. |

Trong Kafka 4.4, phần lớn state-store metrics được ghi ở debug; một số metric như num-open-iterators và num-keys ở info, còn record-e2e-latency-* ở trace. Phiên bản Kafka cũ hơn có thể chỉ hỗ trợ một tập recording level khác, vì vậy cần kiểm tra theo Kafka client thực tế mà dependency management của ứng dụng kéo vào.

Có thể cấu hình ở cấp Kafka Streams binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              metrics.recording.level: debug
~~~

Tương đương dạng properties:

~~~properties
spring.cloud.stream.kafka.streams.binder.configuration.metrics.recording.level=debug
~~~

configuration chuyển các thuộc tính Kafka Streams StreamsConfig tới Kafka Streams client. Đây là cấu hình cấp binder, vì vậy khi có nhiều processor dùng chung binder, recording level có thể áp dụng cho tất cả processor thuộc binder đó.

Thu thập debug/trace có thể làm tăng chi phí đo đạc và lượng metrics. Bật mức chi tiết theo nhu cầu, theo dõi số lượng series và quay về info sau khi hoàn tất chẩn đoán nếu không cần duy trì các metric bổ sung.

## 9. Các client và thread metrics cần theo dõi

### Client-level metrics

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| state | Trạng thái KafkaStreams client dưới dạng chuỗi. | REBALANCING kéo dài hoặc ERROR. |
| application-id | Application ID của client. | Xác định đúng processor trên dashboard. |
| alive-stream-threads | Số stream thread còn sống, đang chạy hoặc tham gia rebalance. | Giảm bất thường so với cấu hình. |
| failed-stream-threads | Số stream thread đã thất bại kể từ khi client khởi động. | Tăng sau deploy hoặc khi có lỗi xử lý. |
| topology-description | Mô tả topology đang chạy. | Đối chiếu thay đổi topology giữa các phiên bản. |

### Thread-level metrics

| Metric | Ý nghĩa | Cách đọc |
|---|---|---|
| process-rate / process-total | Tốc độ và tổng số record được xử lý. | Tốc độ giảm có thể do không có dữ liệu, rebalance hoặc processor chậm. |
| poll-rate / poll-total | Số lần consumer poll mỗi giây và tổng số lần poll. | Poll giảm cần đối chiếu trạng thái thread và broker. |
| poll-records-avg / poll-records-max | Số record trung bình/lớn nhất trong một poll iteration. | Poll rỗng liên tục có thể là topic không có dữ liệu hoặc partition assignment không đúng. |
| process-latency-avg / process-latency-max | Thời gian xử lý record. | Tăng kéo dài thường báo hiệu logic chậm, I/O hoặc state-store access. |
| commit-latency-avg / commit-latency-max | Thời gian commit. | Tăng có thể liên quan broker, transaction hoặc state-store commit. |
| punctuate-latency-avg / punctuate-latency-max | Thời gian chạy punctuator. | Tăng có thể ảnh hưởng window, schedule và xử lý định kỳ. |
| process-ratio, poll-ratio, commit-ratio | Tỷ lệ thời gian thread dành cho các hoạt động tương ứng. | Giúp phân biệt thread đang bận xử lý, chờ poll hay commit. |

Không đặt cảnh báo chỉ dựa vào process-rate bằng 0. Nếu topic không có record mới thì tốc độ xử lý bằng 0 là bình thường. Hãy kết hợp số record đã poll, topic input rate, consumer lag, trạng thái thread và thời gian kể từ lần xử lý gần nhất.

## 10. Processor-node và topic metrics

Metrics tại processor node giúp tìm vị trí trong topology nơi độ trễ hoặc lưu lượng thay đổi:

- records-consumed-total: tổng record đã được source processor tiêu thụ.
- records-produced-total: tổng record sink processor đã ghi.
- record-e2e-latency-avg và record-e2e-latency-max: độ trễ từ timestamp của record đến khi node hoàn tất xử lý.
- Các metric suppression: số record được phát ra từ suppression node và độ trễ phát final record.

So sánh record count giữa source và sink cần tính đến filter, branch, join, aggregation và suppression. Số record sink thấp hơn source không tự động chứng minh mất dữ liệu; topology có thể chủ động loại hoặc gộp record.

Độ trễ record-e2e-latency phụ thuộc timestamp của record và đồng hồ hệ thống. Nếu producer tạo timestamp sai, timestamp ở tương lai hoặc clock giữa các máy lệch nhau, số liệu có thể âm hoặc bất thường. Hãy kiểm tra event-time semantics trước khi dùng metric này làm SLO.

## 11. State store được tạo và materialize như thế nào?

Kafka Streams tự tạo state store khi các thao tác DSL cần lưu trạng thái, chẳng hạn aggregate, count, reduce, join hoặc windowed aggregation. Với Processor API, ứng dụng có thể cần đăng ký StoreBuilder tường minh.

Ví dụ aggregate tổng số lượng theo khách hàng và đặt tên state store:

~~~java
import java.util.function.Function;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.state.KeyValueStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CustomerTotalsTopology {

    @Bean
    public Function<KStream<String, Long>, KTable<String, Long>>
            aggregateByCustomer() {
        return input -> input
                .groupByKey()
                .aggregate(
                        () -> 0L,
                        (customerId, amount, total) -> total + amount,
                        Materialized.<String, Long,
                                KeyValueStore<Bytes, byte[]>>as(
                                        "amount-by-customer")
                                .withKeySerde(Serdes.String())
                                .withValueSerde(Serdes.Long())
                );
    }
}
~~~

Tên amount-by-customer giúp nhận diện store trong topology, log và metrics. Key/value Serde phải phù hợp với kiểu dữ liệu thực tế. State store thường có changelog topic để Kafka Streams phục hồi trạng thái khi task được chuyển sang instance khác.

Nếu input binding có kiểu KTable và muốn materialize thành named store, Kafka Streams binder hỗ trợ thuộc tính:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            process-in-1:
              consumer:
                materialized-as: incoming-store
~~~

Trong ví dụ trên, process-in-1 là input binding thứ hai của function process. Tên binding phải khớp function thực tế trong ứng dụng. Đối với Processor API, custom store có thể được khai báo bằng bean StoreBuilder; binder phát hiện và thêm store vào Streams builder khi khởi tạo topology.

## 12. State store metrics: latency, throughput và iterator

State-store metrics gắn với thread, task và store scope. Với built-in stores, các scope thường gặp gồm:

- in-memory-state, in-memory-lru-state, in-memory-window-state.
- rocksdb-state, rocksdb-window-state, rocksdb-session-state.
- in-memory-suppression cho suppression buffer.

Một số metric quan trọng:

| Metric | Ý nghĩa | Tín hiệu vận hành |
|---|---|---|
| put-latency-avg, put-latency-max | Thời gian ghi một key/value vào store, đơn vị ns. | Tăng kéo dài có thể do disk, compaction hoặc store contention. |
| get-latency-avg, get-latency-max | Thời gian đọc dữ liệu. | Tăng có thể làm chậm join hoặc lookup. |
| delete-latency-avg, put-all-latency-avg | Thời gian xóa hoặc ghi batch. | Dùng để nhận biết workload thay đổi. |
| put-rate, get-rate, delete-rate | Số thao tác mỗi giây. | Đối chiếu với input rate và logic topology. |
| restore-latency-avg, restore-latency-max | Thời gian thao tác phục hồi state. | Tăng có thể kéo dài thời gian rebalance/startup. |
| commit-latency-avg, commit-latency-max | Thời gian commit state store. | Tăng có thể làm giảm throughput. |
| num-open-iterators | Số iterator đã mở nhưng chưa đóng. | Tăng và không giảm có thể cho thấy iterator bị rò rỉ. |
| iterator-duration-avg, iterator-duration-max | Thời gian iterator tồn tại. | Iterator sống lâu có thể giữ tài nguyên RocksDB. |
| oldest-iterator-open-since-ms | Thời điểm hệ thống tạo iterator cũ nhất còn mở. | Dùng để tìm iterator bị bỏ quên. |

num-keys chỉ có ở in-memory state store; metric này không có sẵn cho RocksDB-backed store. Không dùng num-keys để ước lượng số bản ghi trong RocksDB. Với suppression buffer, các metric buffer size/count là nhóm riêng; các metric store thông thường không áp dụng cho suppression buffer.

Đơn vị của latency state-store operation trong Kafka Streams là nanosecond. Khi chuyển sang dashboard, hãy đổi đơn vị rõ ràng; tránh so trực tiếp số ns với latency thread được ghi theo ms.

## 13. Theo dõi RocksDB state store

Kafka Streams thường dùng RocksDB cho persistent key-value, window và session stores. RocksDB metrics được chia thành:

- **Statistics-based:** số liệu tích lũy hoặc tốc độ đọc/ghi, flush, compaction.
- **Properties-based:** trạng thái hiện tại như bộ nhớ và cache.

Một số metric hữu ích:

| Metric | Ý nghĩa | Dùng để chẩn đoán |
|---|---|---|
| bytes-written-rate, bytes-written-total | Lượng byte ghi vào RocksDB. | Ước lượng write workload và tăng trưởng I/O. |
| bytes-read-rate, bytes-read-total | Lượng byte đọc. | Nhận diện read-heavy workload. |
| memtable-bytes-flushed-rate | Tốc độ flush memtable xuống đĩa. | Đối chiếu với write rate và disk throughput. |
| memtable-hit-ratio | Tỷ lệ lookup trúng memtable. | Hiểu hiệu quả của dữ liệu còn trong bộ nhớ ghi. |
| block-cache-data-hit-ratio | Tỷ lệ hit của data block cache. | Thấp kéo dài có thể làm tăng disk read. |
| block-cache-index-hit-ratio | Tỷ lệ hit của index block cache. | Đánh giá hiệu quả cache index. |
| write-stall-duration-avg, write-stall-duration-total | Thời gian RocksDB bị write stall. | Cảnh báo compaction hoặc disk không theo kịp ghi. |
| compaction-time-avg, compaction-time-max | Thời gian compaction. | Xác định áp lực nền của RocksDB. |
| number-file-errors-total | Tổng lỗi file. | Điều tra filesystem, disk và lỗi I/O. |

Trong Kafka 4.4, thống kê RocksDB ở recording level debug được thu thập định kỳ khoảng mỗi phút. Với store gồm nhiều RocksDB instance, chẳng hạn window/session stores, một số metric là tổng hợp trên các instance của store.

Thu thập RocksDB statistics có thể làm tăng chi phí vận hành. Chỉ bật debug khi cần theo dõi chi tiết và theo dõi CPU, I/O, heap và số lượng metrics. Một số metric file counter có thể không còn hữu ích ở phiên bản RocksDB mới; hãy kiểm tra mô tả metric trong Kafka client đang chạy trước khi viết alert.

## 14. Record cache và suppression buffer

Kafka Streams có record cache để gộp hoặc trì hoãn một số cập nhật state store và output trong quá trình xử lý. Record-cache metrics giúp xác định cache có giảm thao tác ghi lặp hay không:

- hit-ratio-avg, hit-ratio-min, hit-ratio-max: tỷ lệ cache hit.
- Các metric hit/miss và kích thước cache khác tùy Kafka client version.

Cache hit ratio thấp không nhất thiết là lỗi. Nó phụ thuộc workload, phân bố key, cache size, topology và tốc độ cập nhật. Hãy so sánh cùng throughput và state-store write rate trước khi tăng cache.

Suppression buffer có metric riêng:

- suppression-buffer-size-avg và suppression-buffer-size-max: kích thước dữ liệu đang buffer.
- suppression-buffer-count-avg và suppression-buffer-count-max: số record đang buffer.
- suppression-emit-rate và suppression-emit-total: tốc độ/tổng số record được phát xuống downstream.
- emit-final-latency-avg và emit-final-latency-max: độ trễ phát final record.

Nếu suppression buffer tăng liên tục mà số record phát ra thấp, hãy kiểm tra window, grace period, watermark/event-time và điều kiện final emission. Không coi buffer lớn là lỗi ngay nếu workload có cửa sổ thời gian dài; hãy đối chiếu với giới hạn buffer và SLO độ trễ.

## 15. Restore state và thời gian rebalance

Khi task được giao cho instance khác, Kafka Streams cần khôi phục state store từ changelog topic nếu không có standby task phù hợp hoặc local state không thể tái sử dụng. Trong giai đoạn restore, thread có thể chưa trở lại RUNNING; client có thể ở REBALANCING.

Các tín hiệu nên quan sát:

- Thời gian REBALANCING từ lúc bắt đầu tới khi client trở lại RUNNING.
- restore-latency-avg và restore-latency-max.
- Lượng dữ liệu đọc từ changelog/restore rate.
- Số active task và standby task.
- Input lag trong thời gian restore.
- Disk throughput, RocksDB write rate và compaction.

Nếu restore kéo dài sau mỗi lần restart:

1. Kiểm tra kích thước state store và changelog topic.
2. Kiểm tra disk throughput, dung lượng và tình trạng filesystem.
3. Xem standby replica có được cấu hình và phân bổ phù hợp không.
4. Kiểm tra số partition và số task được giao cho mỗi instance.
5. Đánh giá có thể giữ local state giữa lần restart hay cấu hình cleanup đang xóa state không cần thiết.

Spring Cloud Stream Kafka Streams binder mặc định không xóa local state khi binding dừng. Có thể thay đổi hành vi bằng một bean CleanupConfig để chỉ định cleanup lúc start, stop hoặc không cleanup. Chỉ bật cleanup khi đã hiểu tác động: xóa local state làm lần chạy sau phải restore lại từ changelog, có thể kéo dài thời gian khởi động.

## 16. Phân biệt health, throughput và lag

Health UP là tín hiệu quan trọng nhưng không thay thế các chỉ số năng lực xử lý:

| Quan sát | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| Health UP | Các Kafka thread đã đăng ký đang ở trạng thái RUNNING theo health indicator. | Không chứng minh consumer lag thấp hoặc business output đúng. |
| process-rate cao | Thread đang xử lý nhiều record. | Không chứng minh record được ghi đúng hoặc không bị duplicate. |
| process-rate bằng 0 | Không có record được xử lý trong khoảng đo. | Không chứng minh thread bị treo; có thể topic không có dữ liệu. |
| REBALANCING | Client đang trong quá trình gán/thu hồi partition hoặc chuẩn bị task. | Không nhất thiết là lỗi nếu diễn ra ngắn. |
| restore-latency tăng | Phục hồi state đang tốn thời gian. | Không tự xác định nguyên nhân là disk hay changelog. |
| failed-stream-threads tăng | Có thread đã thất bại kể từ lúc client khởi động. | Không cho biết lỗi nghiệp vụ cụ thể nếu không xem log. |

Regular Kafka binder có metric spring.cloud.stream.binder.kafka.offset cho consumer group/topic lag. Metric đó thuộc Kafka message-channel binder. Không mặc định giả định metric này được cung cấp giống hệt cho Kafka Streams binder. Với Kafka Streams, hãy kết hợp consumer metrics, stream/thread/task metrics, consumer group tooling và lag từ hệ thống giám sát broker theo phiên bản triển khai.

## 17. Cấu hình quan sát cho một processor

Ví dụ cấu hình processor aggregateByCustomer:

~~~yaml
spring:
  application:
    name: customer-aggregation
  cloud:
    function:
      definition: aggregateByCustomer
    stream:
      bindings:
        aggregateByCustomer-in-0:
          destination: order-amounts
        aggregateByCustomer-out-0:
          destination: customer-totals
      kafka:
        streams:
          binder:
            application-id: customer-aggregation-v1
            configuration:
              metrics.recording.level: debug

management:
  health:
    binders:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,metrics,kafkastreamstopology
  endpoint:
    health:
      show-details: when_authorized
~~~

Cấu hình này:

1. Kích hoạt function aggregateByCustomer.
2. Đọc topic order-amounts và ghi kết quả tới customer-totals.
3. Đặt application ID customer-aggregation-v1.
4. Bật debug metrics để quan sát state store và processor chi tiết hơn.
5. Expose health, metrics và topology endpoint.
6. Cho phép người dùng đã xác thực xem health details.

Khi dùng nhiều processor trong một ứng dụng, hãy đặt application ID cho từng processor theo cấu hình Kafka Streams binder. Topology endpoint và health details sẽ phân loại theo application ID; điều này giúp dashboard không trộn trạng thái giữa các processor.

## 18. Dashboard và cảnh báo vận hành

Một dashboard tốt nên chia thành các hàng theo mục đích:

### Hàng 1 — Sức khỏe processor

- KafkaStreams client state theo application ID.
- Số alive stream threads.
- Số failed stream threads.
- Số thread đang RUNNING, REBALANCING hoặc DEAD.
- Active task/standby task và partition assignment.

### Hàng 2 — Năng lực xử lý

- Input records/sec và output records/sec.
- process-rate, poll-rate.
- process-latency-avg/max.
- commit-latency-avg/max.
- Record end-to-end latency nếu đã bật trace.

### Hàng 3 — State store

- Put/get rate và latency.
- Restore latency.
- RocksDB bytes read/written.
- Block-cache hit ratio.
- Write-stall duration và compaction time.
- Open iterator count và iterator duration.

### Hàng 4 — Broker và tài nguyên

- Consumer lag theo input topic/partition.
- Changelog topic throughput và replication health.
- CPU, heap, GC pause, disk I/O, disk free space.
- Network throughput và request latency tới Kafka broker.

Các cảnh báo nên gắn với thời gian duy trì và nhiều tín hiệu:

| Cảnh báo | Điều kiện gợi ý | Hành động điều tra |
|---|---|---|
| Processor ở ERROR | Client state chuyển ERROR. | Kiểm tra uncaught exception, failed thread và log. |
| Thread chết | alive-stream-threads thấp hơn dự kiến hoặc thread state DEAD. | Kiểm tra exception, shutdown và thread failure. |
| Rebalance kéo dài | REBALANCING vượt ngưỡng vận hành đã đo. | Kiểm tra task restore, partition churn và broker connectivity. |
| Lag tăng liên tục | Consumer lag tăng trong khi input rate lớn hơn output/process rate. | Tìm processor chậm, state-store I/O hoặc thiếu task parallelism. |
| Commit chậm | commit-latency-max tăng kéo dài. | Kiểm tra broker, transaction và state-store flush/commit. |
| Restore chậm | Restore latency tăng hoặc startup bị kéo dài. | Kiểm tra changelog, RocksDB, disk và standby task. |
| RocksDB write stall | write-stall-duration-total tăng nhanh. | Kiểm tra disk, compaction, write rate và RocksDB resource limits. |
| Iterator bị rò rỉ | num-open-iterators hoặc tuổi iterator cũ nhất tăng liên tục. | Kiểm tra code tạo iterator và bảo đảm đóng iterator. |
| Suppression buffer tăng | Buffer size/count tăng liên tục mà emit rate thấp. | Kiểm tra window, grace period và event-time. |

Không đặt ngưỡng cố định giống nhau cho mọi topology. Đo baseline dưới tải bình thường, kiểm tra giờ cao điểm và dùng tỷ lệ thay đổi hoặc thời gian kéo dài thay vì alert trên một mẫu đơn lẻ.

## 19. Kiểm thử khả năng quan sát

Kiểm thử cần xác nhận cả endpoint và metric thực sự xuất hiện trên ứng dụng chạy với Kafka broker thử nghiệm. Unit test topology không chứng minh Actuator đã expose endpoint hoặc recording level đã bật.

### Kịch bản topology và health

1. Khởi động ứng dụng có application ID đã biết.
2. Gọi /actuator/kafkastreamstopology.
3. Gọi /actuator/kafkastreamstopology/{application-id}.
4. Đối chiếu source, processor, sink và state store với cấu hình topology.
5. Gọi /actuator/health với user được phép xem chi tiết.
6. Xác nhận health details có application ID, thread state, active task và standby task.
7. Tạo một rebalance có kiểm soát trong môi trường test và quan sát client/thread state chuyển đổi.

### Kịch bản state store metrics

1. Tạo topology có aggregate materialize thành store có tên.
2. Gửi record với nhiều key để tạo hoạt động put/get.
3. Khám phá /actuator/metrics và xác nhận metric Kafka Streams được đăng ký.
4. Kiểm tra put/get latency và rate theo store scope.
5. Bật recording level debug và xác nhận RocksDB/state-store metrics cần thiết xuất hiện.
6. Restart processor trong môi trường test để tạo state restoration.
7. Quan sát restore latency, disk I/O và thời gian trở lại RUNNING.
8. Nếu topology dùng iterator, xác nhận iterator được đóng và số open iterator trở về mức bình thường.

### Ma trận kiểm thử

| Tình huống | Thiết lập | Kết quả cần xác nhận |
|---|---|---|
| Topology endpoint tổng hợp | GET /actuator/kafkastreamstopology. | Nhận mô tả các topology đang được binder quản lý. |
| Topology theo application ID | GET endpoint với đúng ID. | Nhận topology của processor tương ứng. |
| Endpoint chưa expose | Bỏ kafkastreamstopology khỏi exposure list. | Endpoint không được truy cập qua web. |
| Health bình thường | Broker hoạt động, task đã restore. | Thread RUNNING và health UP. |
| Rebalance | Thay đổi instance/partition assignment trong test. | Thread state và client state phản ánh quá trình chuyển tiếp. |
| Thread failure | Gây lỗi có kiểm soát trong test phù hợp. | Failed thread/state/health được ghi nhận và log có nguyên nhân. |
| Metrics info | metrics.recording.level=info. | Client/thread metrics nền tảng có thể truy vấn. |
| Metrics debug | Bật debug. | State-store, processor và RocksDB metrics bổ sung xuất hiện theo Kafka version. |
| Metrics trace | Bật trace khi cần. | Các metric chi tiết như record end-to-end latency có thể xuất hiện. |
| State restore | Xóa local state trong môi trường thử nghiệm hoặc chuyển task sang instance mới. | Restore latency và thời gian rebalance được quan sát. |
| Iterator lifecycle | Tạo rồi đóng iterator trong processor. | Open iterator count không tăng vô hạn. |
| Nhiều processor | Ứng dụng có nhiều application ID. | Health và topology phân biệt từng processor. |
| Bảo mật endpoint | Truy cập bằng user không có quyền. | Health details/topology/metrics được bảo vệ theo chính sách. |

## 20. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không truy cập được topology endpoint | Chưa thêm Actuator/web dependency hoặc chưa expose endpoint. | Thêm dependency và kafkastreamstopology vào exposure list. |
| Endpoint topology trả về không đúng processor | Dùng nhầm application ID. | Xác nhận application ID của processor và gọi endpoint tương ứng. |
| Health chỉ hiển thị UP/DOWN | Chưa cấu hình show-details hoặc user không được quyền. | Dùng WHEN_AUTHORIZED và cấp quyền phù hợp. |
| Health DOWN trong lúc rebalance | Một thread chưa RUNNING hoặc task còn restore. | Kiểm tra thread/task state và thời gian rebalance trước khi restart. |
| Không thấy state-store metrics | Recording level đang là info, hoặc store type/version không cung cấp metric đó. | Kiểm tra Kafka client version và bật debug khi cần. |
| Không thấy num-keys | Store đang dùng RocksDB. | num-keys chỉ có cho in-memory state store; dùng RocksDB properties/metrics thay thế. |
| Metrics không xuất hiện trong Actuator | MeterRegistry/Actuator chưa có hoặc metric bị filter. | Kiểm tra dependency Micrometer, endpoint exposure và MeterFilter. |
| Metric bị cộng gộp giữa processor | Dashboard bỏ tag application ID/client/task/store. | Giữ các tag định danh khi query và alert. |
| Restore kéo dài sau restart | State lớn, changelog đọc chậm, disk yếu hoặc local state bị cleanup. | Kiểm tra restore metrics, changelog, RocksDB và CleanupConfig. |
| Open iterator tăng mãi | Iterator trong Processor API không được đóng. | Dùng try-with-resources hoặc đóng iterator trong mọi nhánh. |
| Process rate bằng 0 bị alert liên tục | Topic không có dữ liệu mới hoặc topology filter hết record. | Kết hợp input rate, lag, poll metrics và business output. |
| RocksDB write stall tăng | Compaction hoặc disk không theo kịp write workload. | Kiểm tra write rate, compaction, disk latency và resource limits. |

Khi điều tra, đi từ client state tới thread/task, sau đó xem processor node và state store. Đối chiếu cùng thời điểm với input rate, output rate, consumer lag, broker health và tài nguyên máy. Cách đọc theo tầng giúp xác định vấn đề nằm ở topology, phân vùng, logic xử lý hay state-store I/O.

## 21. Checklist trước khi triển khai

- [ ] Đã đặt application ID rõ ràng cho từng Kafka Streams processor.
- [ ] Đã bật Actuator và web runtime cần thiết.
- [ ] Đã expose health, metrics và kafkastreamstopology theo nhu cầu.
- [ ] Topology endpoint được bảo vệ bằng xác thực/phân quyền.
- [ ] Health indicator của binder được bật.
- [ ] Health details chỉ hiển thị cho người có quyền.
- [ ] Dashboard phân biệt client state, thread state và task assignment.
- [ ] Metrics có tag application ID, thread, task, processor node và store.
- [ ] Recording level mặc định phù hợp; chỉ bật debug/trace khi cần.
- [ ] Có metrics process, poll, commit và record end-to-end latency.
- [ ] Có metrics state store put/get/restore và iterator lifecycle.
- [ ] Có RocksDB I/O, cache, compaction và write-stall metrics nếu dùng RocksDB.
- [ ] Đã hiểu num-keys chỉ áp dụng cho in-memory state store.
- [ ] Có giám sát consumer lag, changelog và broker.
- [ ] Có ngưỡng alert dựa trên baseline và thời gian duy trì.
- [ ] Đã kiểm thử topology endpoint, health, metrics và state restoration.

Theo dõi Kafka Streams trong Spring Cloud Stream cần kết hợp topology description, runtime health và metrics. Endpoint kafkastreamstopology cho biết cấu trúc processor; health indicator cho biết trạng thái stream thread và task; Micrometer cùng Kafka Streams metrics giúp đo throughput, latency, commit, restore, state-store và RocksDB. Khi giữ các tag theo application ID, thread, task và store, đội vận hành có thể xác định processor hoặc state store đang gây chậm, phân biệt rebalance bình thường với lỗi kéo dài và xây dựng cảnh báo dựa trên baseline thực tế.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0.3 — Kafka Streams Binder: Health Indicator and Metrics](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/accessing-metrics.html)
- [Spring Cloud Stream — Kafka Streams Topology Visualization](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/topology-visualization.html)
- [Spring Cloud Stream — Kafka Streams Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html)
- [Apache Kafka 4.4 — Monitoring Kafka Streams](https://kafka.apache.org/44/operations/monitoring/)
- [Apache Kafka 4.4 — KafkaStreams.State API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/KafkaStreams.State.html)
- [Apache Kafka 4.4 — Running Streams Applications](https://kafka.apache.org/44/streams/developer-guide/running-app/)
