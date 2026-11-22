# Nhánh xử lý, gộp luồng và ghi sang topic đích

Kafka Streams cung cấp DSL để xây dựng topology xử lý dữ liệu ngay trong ứng dụng Java. Một topology thường đọc record từ một hoặc nhiều input topic, lọc hoặc biến đổi dữ liệu, định tuyến record theo điều kiện, kết hợp nhiều luồng rồi ghi kết quả sang output topic. Ba thao tác quan trọng trong kiểu xử lý này là branch, merge và sink.

Branch tách một stream thành nhiều nhánh dựa trên predicate. Merge hợp nhất nhiều KStream có cùng kiểu key/value thành một KStream. Sink ghi stream hiện tại vào một Kafka topic. Hiểu đúng semantics của từng thao tác giúp tránh lỗi như record đi vào nhiều nhánh ngoài ý muốn, nhầm merge với join, giả định có thứ tự toàn cục hoặc ghi output bằng Serdes không tương thích.

## 1. Vị trí của branch, merge và sink trong topology

Một pipeline định tuyến đơn hàng có thể đọc topic orders.events, phân loại event theo loại, gộp các loại event cần xử lý chung rồi ghi ra topic orders.lifecycle:

~~~mermaid
flowchart LR
    A[(orders.events)] --> B[Source KStream]
    B --> C{Branch by event type}
    C -->|CREATED| D[Created stream]
    C -->|CANCELLED| E[Cancelled stream]
    C -->|Other| F[Other stream]
    D --> G[Merge]
    E --> G
    G --> H[Normalize / enrich]
    H --> I[Sink: orders.lifecycle]
    F --> J[Sink: orders.unhandled]
~~~

| Thao tác | Input | Output | Mục đích |
|---|---|---|---|
| branch/split | Một KStream | Nhiều KStream | Định tuyến record theo predicate |
| filter/filterNot | Một KStream | Một KStream con | Giữ record thỏa điều kiện |
| merge | Hai KStream trở lên | Một KStream | Hợp nhất các record thành một luồng |
| to | Một KStream | Kafka topic | Ghi record ra topic đích |

Các thao tác này thuộc Kafka Streams DSL. Chúng mô tả topology xử lý; khi ứng dụng chạy, Kafka Streams tạo source, processor, repartition và sink nodes tương ứng.

## 2. Tạo input KStream

KStream là abstraction cho một luồng record key/value. Mỗi record là một sự kiện hoặc một lần cập nhật, khác với KTable vốn biểu diễn trạng thái mới nhất theo key.

Ví dụ định nghĩa event:

~~~java
public record OrderEvent(
    String eventId,
    String orderId,
    String customerId,
    String type,
    long amount,
    String currency
) {}
~~~

Tạo stream từ input topic:

~~~java
StreamsBuilder builder = new StreamsBuilder();

KStream<String, OrderEvent> orders = builder.stream(
    "orders.events",
    Consumed.with(Serdes.String(), orderEventSerde)
);
~~~

Key thường là orderId hoặc aggregate ID để các event cùng đơn hàng được đưa vào cùng partition theo partitioning strategy hiện tại. Value là OrderEvent đã deserialize. Nếu event dùng Avro hoặc Protobuf, hãy dùng Serde tương ứng và bảo đảm schema contract tương thích với producer.

Input topic cần tồn tại hoặc được provisioning theo quy trình nền tảng. Không nên phụ thuộc auto topic creation trong production vì số partition, replication factor và retention cần được quyết định rõ.

## 3. Branch: định tuyến record theo điều kiện

Branch tách stream đầu vào thành các nhánh. Với API hiện đại của Kafka Streams DSL, dùng split() kết hợp branch() và defaultBranch(). Mỗi predicate được xét theo thứ tự khai báo; một record được đưa vào nhánh đầu tiên có predicate trả về true. Sau khi khớp, record không tiếp tục xét các nhánh phía sau.

Ví dụ:

~~~java
Map<String, KStream<String, OrderEvent>> branches = orders
    .split(Named.as("orders-"))
    .branch(
        (key, event) -> event != null
            && "CREATED".equals(event.type()),
        Branched.as("created")
    )
    .branch(
        (key, event) -> event != null
            && "CANCELLED".equals(event.type()),
        Branched.as("cancelled")
    )
    .defaultBranch(Branched.as("other"));
~~~

Với prefix orders- và nhãn nhánh created, cancelled, other, map kết quả chứa các stream theo tên tương ứng như orders-created, orders-cancelled và orders-other.

Ghi mỗi nhánh sang topic riêng:

~~~java
branches.get("orders-created").to(
    "orders.created",
    Produced.with(Serdes.String(), orderEventSerde)
);

branches.get("orders-cancelled").to(
    "orders.cancelled",
    Produced.with(Serdes.String(), orderEventSerde)
);

branches.get("orders-other").to(
    "orders.unhandled",
    Produced.with(Serdes.String(), orderEventSerde)
);
~~~

### Thứ tự predicate ảnh hưởng kết quả

Giả sử có hai predicate:

1. Event có type CREATED.
2. Event có amount lớn hơn 1.000.000.

Một event CREATED có amount 2.000.000 sẽ vào nhánh CREATED nếu predicate đó đứng trước. Nó không đồng thời vào nhánh amount lớn. Nếu nghiệp vụ cần một record đi vào nhiều output độc lập, hãy dùng nhiều filter/branch path hoặc fan-out tường minh thay vì dựa vào split semantics.

### defaultBranch và record không khớp

Nếu không khai báo defaultBranch, record không khớp predicate nào sẽ không xuất hiện trong các nhánh được tạo. Điều này có thể là chủ ý, nhưng cũng có thể làm rơi dữ liệu khỏi topology mà không có nơi quan sát.

Trong pipeline quan trọng, nên có nhánh default để ghi event không nhận diện vào topic quarantine/unhandled hoặc phát metric. Đừng tự động coi event lạ là lỗi dữ liệu; nó có thể là event type mới đang được rollout.

### Predicate cần an toàn và xác định

- Kiểm tra null trước khi đọc field nếu topic có thể chứa tombstone hoặc value null.
- Không gọi database/HTTP service bên trong predicate.
- Không tạo side effect trong predicate.
- Không dùng thời gian hiện tại hoặc random value làm điều kiện routing nếu cần kết quả tái lập.
- Giữ điều kiện đơn giản, có unit test cho boundary values và unknown enum.

Branch là phép định tuyến trong topology, không phải một cơ chế gọi service bên ngoài.

## 4. split/branch khác filter như thế nào?

Filter giữ lại record thỏa predicate trong một stream duy nhất. Split/branch tạo nhiều stream con theo thứ tự predicate.

~~~java
KStream<String, OrderEvent> highValueOrders =
    orders.filter((key, event) ->
        event != null && event.amount() >= 1_000_000);

KStream<String, OrderEvent> regularOrders =
    orders.filter((key, event) ->
        event != null && event.amount() < 1_000_000);
~~~

Ví dụ trên tạo hai topology path riêng. Cùng một input stream có thể được tham chiếu nhiều lần; Kafka Streams sẽ xây dựng graph xử lý phù hợp. Filter phù hợp khi chỉ cần một tập con. Split phù hợp khi muốn phân loại thành các nhánh loại trừ nhau và quản lý chúng bằng một map.

Trong Kafka Streams 2.8 trở lên, API split/Branched cung cấp cách khai báo tên nhánh rõ ràng. API branch() cũ trên KStream đã bị deprecated trong các phiên bản hiện đại; khi viết topology mới, ưu tiên split().branch().defaultBranch() và đối chiếu phiên bản thư viện của dự án.

## 5. Merge: hợp nhất nhiều KStream

Merge kết hợp record của hai KStream thành một KStream. Ví dụ, stream đơn hàng mới và stream đơn hàng bị hủy đều có cùng kiểu key/value, ta có thể hợp nhất để xử lý chung:

~~~java
KStream<String, OrderEvent> created =
    builder.stream(
        "orders.created",
        Consumed.with(Serdes.String(), orderEventSerde)
    );

KStream<String, OrderEvent> cancelled =
    builder.stream(
        "orders.cancelled",
        Consumed.with(Serdes.String(), orderEventSerde)
    );

KStream<String, OrderEvent> lifecycle =
    created.merge(cancelled);

lifecycle.to(
    "orders.lifecycle",
    Produced.with(Serdes.String(), orderEventSerde)
);
~~~

Merge giữ nguyên record key/value và đưa record từ các input stream vào cùng downstream path. Nó không tự join hai record có cùng key, không loại duplicate và không sắp xếp lại record theo timestamp.

### Merge không phải join

| Đặc điểm | merge | join |
|---|---|---|
| Mục tiêu | Hợp nhất các record thành một stream | Kết hợp dữ liệu liên quan từ hai luồng/table |
| Cần key giống nhau? | Hai stream phải có kiểu key tương thích; không cần key value phải trùng nhau | Thường cần key để ghép record |
| Chờ record từ input còn lại? | Không | Có thể cần window hoặc state tùy loại join |
| Tạo output | Mỗi record đầu vào tiếp tục đi qua stream hợp nhất | Output được tạo từ cặp/quan hệ record theo semantics join |
| Deduplicate | Không | Không tự động deduplicate theo business ID |

Nếu cần kết hợp thông tin customer với order theo customerId, hãy xem xét KStream-KStream, KStream-KTable hoặc KTable-KTable join. Merge chỉ phù hợp khi hai luồng là các nguồn record có cùng schema/ý nghĩa xử lý sau đó.

## 6. Merge không tạo thứ tự toàn cục

Kafka bảo đảm thứ tự trong một partition. Merge không thiết lập thứ tự tổng thể giữa các input topic hoặc partition.

Ví dụ:

- Topic orders.created có record A lúc 10:00.
- Topic orders.cancelled có record B lúc 10:01.
- Hai topic có partition và consumer task khác nhau.

KStream.merge() không cam kết output luôn theo timestamp A rồi B. Thứ tự quan sát được phụ thuộc lịch poll, partition assignment, task scheduling và tốc độ xử lý. Không dùng merge để tạo timeline toàn cục.

Nếu nghiệp vụ cần thứ tự theo orderId:

- Dùng orderId làm key ở mọi nguồn liên quan.
- Bảo đảm partitioning strategy tương thích.
- Dùng sequence/version nghiệp vụ để phát hiện event cũ hoặc thiếu.
- Nếu các event đến từ nhiều topic, thiết kế downstream để xử lý event theo version thay vì dựa vào timestamp đến.

Nếu cần thứ tự theo transaction hoặc event time toàn cục, phải thiết kế cơ chế buffering/watermark hoặc một nguồn event được tuần tự hóa theo đúng aggregate. Merge đơn thuần không cung cấp điều đó.

## 7. Key, partition và repartition sau khi merge

Merge không tự thay đổi key và không tự đảm bảo hai stream có cùng key được đưa vào cùng partition. Nếu hai input topic được tạo với partition count hoặc partitioner khác nhau, các record cùng key có thể nằm ở partition index khác nhau.

Điều này đặc biệt quan trọng khi sau merge có stateful operation như groupByKey, aggregate, count hoặc join. Kafka Streams cần đảm bảo record có cùng key được xử lý cùng task/store partition. Một số operation theo key có thể tạo repartition topic nội bộ tự động; ứng dụng cũng có thể yêu cầu repartition rõ ràng.

Ví dụ đổi key sang customerId rồi nhóm theo customer:

~~~java
KStream<String, OrderEvent> byCustomer = lifecycle
    .selectKey((orderId, event) -> event.customerId())
    .repartition(
        Repartitioned.with(
            Serdes.String(),
            orderEventSerde
        ).withName("orders-by-customer")
    );
~~~

Đoạn code giả định OrderEvent có customerId. Repartition ghi record qua topic nội bộ để phân phối lại theo key mới. Việc này tốn network, disk và serialization; chỉ làm khi semantics downstream cần key mới hoặc DSL yêu cầu repartition cho stateful operation.

### Khi nào cần repartition?

| Tình huống | Có cần xem xét repartition? |
|---|---|
| Chỉ merge rồi ghi output, không đổi key | Thường không cần |
| Merge các stream có cùng key semantics và partitioning | Có thể xử lý tiếp trực tiếp; vẫn cần kiểm tra topology |
| selectKey/groupBy theo key mới | Cần repartition trước stateful aggregation/join nếu key distribution chưa được đảm bảo |
| Thay partition count của topic nguồn | Đánh giá lại key-to-partition mapping và ordering |
| Hai nguồn có partitioner khác nhau | Kiểm tra trước stateful operation theo key |

Không tăng partition count hoặc đổi partitioner như một thao tác tuning vô hại. Thay đổi có thể làm cùng key đi sang partition khác trong các record mới, ảnh hưởng ordering và state.

## 8. Ghi stream sang output topic bằng to()

to() là sink operation trong KStream DSL. Nó ghi key/value của stream vào topic đích bằng serializer được chỉ định qua Produced hoặc cấu hình mặc định.

~~~java
lifecycle.to(
    "orders.lifecycle",
    Produced.with(
        Serdes.String(),
        orderEventSerde
    )
);
~~~

Một stream có thể được ghi vào nhiều topic bằng cách gắn nhiều sink path. Nếu cần biến đổi khác nhau cho từng output, tạo các path riêng bằng filter/map/branch rồi gọi to() ở mỗi path.

~~~java
KStream<String, OrderEvent> normalized =
    lifecycle.mapValues(this::normalize);

normalized.to(
    "orders.lifecycle",
    Produced.with(Serdes.String(), orderEventSerde)
);

normalized.filter((key, event) -> event.amount() > 0)
    .to(
        "orders.validated",
        Produced.with(Serdes.String(), orderEventSerde)
    );
~~~

Trong ví dụ, hai sink nhận các path có chủ đích. Record có thể được ghi vào cả hai output vì topology có hai nhánh tiêu thụ cùng normalized stream.

### Chọn key và value Serde

Serde là cặp serializer/deserializer. Output Serde phải tương thích với định dạng mà consumer đích mong đợi:

- String key dùng Serdes.String().
- JSON có thể dùng custom JSON Serde hoặc serializer phù hợp.
- Avro/Protobuf dùng Serde tích hợp Schema Registry theo cấu hình.
- Byte array dùng Serdes.ByteArray() khi payload đã được encode thành bytes.

Nếu output key/value Serde không đúng, lỗi có thể xảy ra khi serialize record ở sink. Hãy kiểm thử bằng consumer thật hoặc TopologyTestDriver với đúng Serde.

### Topic đích và partition count

Output topic nên được tạo trước với:

- Partition count phù hợp throughput và mức song song downstream.
- Replication factor phù hợp độ bền.
- Cleanup policy phù hợp: delete cho event history hoặc compact cho trạng thái mới nhất theo key.
- Retention, ACL và schema compatibility được xác định.

Kafka Streams không nên được xem là công cụ tự thiết kế toàn bộ topic policy. Provisioning topic bằng Kafka Admin/CI/CD giúp kiểm soát cấu hình. Auto topic creation có thể tạo topic với partition/replication mặc định không phù hợp.

## 9. Ví dụ hoàn chỉnh: branch, merge và sink

Ví dụ định tuyến CREATED và CANCELLED vào các topic riêng, sau đó gộp hai nhánh để ghi một lifecycle topic. Các event khác được chuyển vào topic unhandled:

~~~java
public class OrderRoutingTopology {

    public static Topology build(
            Serde<OrderEvent> orderEventSerde) {

        StreamsBuilder builder = new StreamsBuilder();

        KStream<String, OrderEvent> source = builder.stream(
            "orders.events",
            Consumed.with(Serdes.String(), orderEventSerde)
        );

        Map<String, KStream<String, OrderEvent>> branches =
            source.split(Named.as("orders-"))
                .branch(
                    (key, event) -> event != null
                        && "CREATED".equals(event.type()),
                    Branched.as("created")
                )
                .branch(
                    (key, event) -> event != null
                        && "CANCELLED".equals(event.type()),
                    Branched.as("cancelled")
                )
                .defaultBranch(Branched.as("other"));

        KStream<String, OrderEvent> created =
            branches.get("orders-created");
        KStream<String, OrderEvent> cancelled =
            branches.get("orders-cancelled");
        KStream<String, OrderEvent> other =
            branches.get("orders-other");

        created.to(
            "orders.created",
            Produced.with(Serdes.String(), orderEventSerde)
        );

        cancelled.to(
            "orders.cancelled",
            Produced.with(Serdes.String(), orderEventSerde)
        );

        other.to(
            "orders.unhandled",
            Produced.with(Serdes.String(), orderEventSerde)
        );

        created.merge(cancelled)
            .to(
                "orders.lifecycle",
                Produced.with(Serdes.String(), orderEventSerde)
            );

        return builder.build();
    }
}
~~~

Topology trên tạo bốn sink topic:

| Output topic | Nội dung |
|---|---|
| orders.created | Event CREATED |
| orders.cancelled | Event CANCELLED |
| orders.unhandled | Event không khớp hai predicate |
| orders.lifecycle | Hợp nhất CREATED và CANCELLED |

Một event CREATED được ghi vào cả orders.created và orders.lifecycle. Đây là fan-out có chủ đích: branch stream có thể nối tới nhiều downstream node. Nó không phải duplicate do retry.

## 10. Đặt tên topology và quan sát processor

Named.as() và Branched.as() giúp topology dễ đọc và giảm tên node tự sinh khó hiểu. Có thể đặt tên sink bằng Produced.withName() nếu API phiên bản đang dùng hỗ trợ.

~~~java
created.to(
    "orders.created",
    Produced.with(
        Serdes.String(),
        orderEventSerde
    ).withName("orders-created-sink")
);
~~~

Sau khi build topology, có thể xem mô tả:

~~~java
Topology topology = OrderRoutingTopology.build(orderEventSerde);
System.out.println(topology.describe());
~~~

Topology description giúp kiểm tra source, processor, repartition và sink nodes. Trong production, nên lưu topology description/log ở startup để hỗ trợ đối chiếu khi thay đổi code.

## 11. Spring Boot tích hợp Kafka Streams

Spring Kafka hỗ trợ Kafka Streams thông qua StreamsBuilderFactoryBean và annotation @EnableKafkaStreams. Spring Boot có thể cấu hình bootstrap server và application ID bằng properties.

Ví dụ:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    streams:
      application-id: order-routing-service
      properties:
        processing.guarantee: exactly_once_v2
        default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Khai báo topology bean:

~~~java
@Configuration
@EnableKafkaStreams
public class OrderStreamsConfiguration {

    @Bean
    KStream<String, OrderEvent> orderRoutingStream(
            StreamsBuilder builder,
            Serde<OrderEvent> orderEventSerde) {

        KStream<String, OrderEvent> orders = builder.stream(
            "orders.events",
            Consumed.with(Serdes.String(), orderEventSerde)
        );

        Map<String, KStream<String, OrderEvent>> branches =
            orders.split(Named.as("orders-"))
                .branch(
                    (key, event) -> event != null
                        && "CREATED".equals(event.type()),
                    Branched.as("created")
                )
                .branch(
                    (key, event) -> event != null
                        && "CANCELLED".equals(event.type()),
                    Branched.as("cancelled")
                )
                .defaultBranch(Branched.as("other"));

        branches.get("orders-created").merge(
            branches.get("orders-cancelled")
        ).to(
            "orders.lifecycle",
            Produced.with(Serdes.String(), orderEventSerde)
        );

        branches.get("orders-other").to(
            "orders.unhandled",
            Produced.with(Serdes.String(), orderEventSerde)
        );

        return orders;
    }
}
~~~

Ví dụ cấu hình tập trung vào cách khai báo topology; bean return type và cách expose stream có thể thay đổi theo cách tổ chức ứng dụng. Không khai báo hai topology trùng nhau cho cùng application ID. Nếu dùng Spring Boot, hãy kiểm tra đúng dependency kafka-streams và spring-kafka version tương thích.

Kafka Streams application ID vừa là định danh ứng dụng vừa được dùng làm consumer group ID và prefix cho internal resources. Mỗi topology logic độc lập cần application ID riêng; các instance của cùng một topology dùng chung application ID để chia task.

## 12. Processing guarantee và ghi output

Branch, merge và sink đều có thể chạy với processing guarantee mặc định at-least-once hoặc exactly-once tùy cấu hình Kafka Streams.

~~~properties
processing.guarantee=exactly_once_v2
~~~

Exactly-once v2 dùng Kafka transaction để kết hợp output records, state store changelog và input offsets trong phạm vi Kafka Streams. Nó không tự bảo vệ database hoặc HTTP API được gọi từ custom processor. Tránh gọi side effect ngoài Kafka trong predicate/map/processor nếu không có idempotency hoặc outbox boundary riêng.

Để exactly-once hoạt động, cluster cần cấu hình replication và transaction phù hợp, bao gồm replication factor của internal topics. Cần kiểm tra broker version, min.insync.replicas và khả năng ghi transaction. Nếu transaction abort, downstream dùng read_committed để chỉ thấy output đã commit.

Branch/merge không tự tạo exactly-once. Guarantee đến từ Kafka Streams processing configuration và cách ứng dụng thực hiện side effect.

## 13. Xử lý lỗi deserialize và record không hợp lệ

Branch chỉ hoạt động sau khi record đã được deserialize thành key/value. Nếu deserializer lỗi, predicate không nhận được event để phân loại. Cần cấu hình DeserializationExceptionHandler phù hợp và có chiến lược quarantine/DLQ theo phiên bản Kafka Streams.

Các trường hợp nên tách biệt:

| Trường hợp | Cách xử lý |
|---|---|
| Payload không parse được | Deserialization exception handler hoặc raw-byte ingress topic |
| Event parse được nhưng thiếu field bắt buộc | Validation branch hoặc side output/quarantine |
| Event type chưa biết | Default branch và metric/schema rollout |
| Business rule không hợp lệ | Nhánh reject/quarantine có reason code |
| Lỗi tạm thời downstream | Retry/backoff hoặc pause/backpressure theo topology design |

Không đưa mọi event không nhận diện vào cùng một nhánh rồi bỏ qua. Nên ghi lý do, source topic/partition/offset, event ID và schema version nếu có để điều tra.

Nếu cấu hình LogAndContinueExceptionHandler, record deserialize lỗi có thể bị bỏ qua khỏi topology sau khi ghi log; đây là lựa chọn có thể làm mất xử lý. Chỉ dùng khi dữ liệu lỗi được chấp nhận bỏ qua hoặc đã có cơ chế lưu raw payload riêng. Với dữ liệu quan trọng, cân nhắc handler đưa lỗi vào luồng phục hồi hoặc giữ raw bytes trước khi parse.

## 14. Branching với tombstone và null value

Với compacted topic, record có key và value null có thể là tombstone. Nếu predicate gọi event.type() mà không kiểm tra null, topology có thể ném NullPointerException.

~~~java
KStream<String, OrderEvent> nonNullEvents =
    orders.filter((key, event) -> event != null);

KStream<String, OrderEvent> nullValues =
    orders.filter((key, event) -> event == null);
~~~

Nếu tombstone có ý nghĩa xóa trạng thái, không được lọc bỏ nó trước khi xử lý state. Ví dụ KTable materialization có semantics riêng cho null value; với KStream, tombstone vẫn là record value null và logic phải quyết định rõ.

Nếu branch null sang quarantine, cần bảo đảm output Serde chấp nhận null value và key vẫn được giữ để downstream biết entity nào bị xóa.

## 15. Partitioning và output topic

Sink topic có partition count riêng. Producer của Kafka Streams ghi record theo key và partitioner của output topic. Nếu key không null, partition thường được xác định từ serialized key và partition count; nếu key null, partitioner có thể chọn partition theo cơ chế khác.

Để duy trì ordering theo aggregate:

- Giữ key ổn định từ source tới sink nếu key đó là aggregate ID.
- Khi đổi key, hiểu rằng repartitioning có thể làm đổi partition.
- Không kỳ vọng merge giữ thứ tự toàn cục.
- Tạo output topic với partition count phù hợp và thống nhất với downstream.
- Nếu nhiều input topic có cùng entity nhưng key/partitioning khác nhau, chuẩn hóa trước stateful operation.

Tăng partition count có thể thay đổi kết quả key-to-partition mapping đối với record mới. Điều này có thể làm event cũ và mới của cùng key nằm ở partition khác nhau. Hãy có kế hoạch migration nếu ordering theo key là yêu cầu nghiệp vụ.

## 16. Tên topic và ACL cho Kafka Streams

Kafka Streams cần quyền đọc input topics, ghi output topics và quản lý internal topics theo application ID. Internal topics có thể gồm repartition topics và changelog topics cho state stores.

| Resource | Quyền thường cần |
|---|---|
| Input topic | READ và DESCRIBE |
| Output topic | WRITE và DESCRIBE |
| Consumer group theo application.id | READ |
| Repartition topic nội bộ | READ/WRITE và DESCRIBE |
| Changelog topic nội bộ | READ/WRITE và DESCRIBE |
| Cluster | Các quyền metadata/transaction cần thiết theo cấu hình và version |

Không cấp quyền quản trị toàn cluster cho Streams application chỉ để ghi sink topic. Dùng ACL theo prefix application ID cho internal topics và quyền cụ thể cho input/output topic.

Nếu dùng exactly_once_v2, transactional producer cần quyền transaction ID phù hợp và cluster-level idempotent write theo ACL policy của Kafka version. Kiểm tra authorization error trong broker log để cấp đúng resource/operation.

## 17. Kiểm thử branch, merge và sink với TopologyTestDriver

TopologyTestDriver cho phép kiểm thử DSL mà không cần broker thật. Có thể tạo input topic, ghi record, đọc output topic và xác minh routing.

~~~java
Properties props = new Properties();
props.put(StreamsConfig.APPLICATION_ID_CONFIG, "orders-routing-test");
props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "dummy:9092");

Topology topology = OrderRoutingTopology.build(orderEventSerde);

try (TopologyTestDriver driver =
         new TopologyTestDriver(topology, props)) {

    TestInputTopic<String, OrderEvent> input =
        driver.createInputTopic(
            "orders.events",
            Serdes.String().serializer(),
            orderEventSerde.serializer()
        );

    TestOutputTopic<String, OrderEvent> created =
        driver.createOutputTopic(
            "orders.created",
            Serdes.String().deserializer(),
            orderEventSerde.deserializer()
        );

    input.pipeInput(
        "order-1",
        new OrderEvent(
            "evt-1", "order-1", "customer-1", "CREATED", 100_000, "VND")
    );

    assertEquals("order-1", created.readKeyValue().key);
}
~~~

Ví dụ giả định đã có orderEventSerde và test framework JUnit. Nên kiểm thử:

- Mỗi event type chỉ vào nhánh đầu tiên khớp.
- Event không khớp đi vào default branch.
- Null/tombstone được xử lý đúng.
- Merge đưa record từ cả hai input tới output.
- Merge không làm mất hoặc tự deduplicate record.
- Output key/value được serialize đúng.
- Repartition sau đổi key tạo kết quả aggregation đúng.
- Unknown event type được quan sát hoặc quarantine.

TopologyTestDriver kiểm tra logic topology trong process. Vẫn cần integration test với Kafka broker để kiểm tra ACL, topic configuration, Serde/schema registry, transaction và rebalance thực tế.

## 18. Monitoring và troubleshooting

Các tín hiệu quan trọng:

| Tín hiệu | Cần quan sát |
|---|---|
| Input records per topic/partition | Nguồn có phát dữ liệu đều không |
| Branch count theo nhánh | Predicate có phân loại đúng và default branch có tăng bất thường không |
| Unhandled/quarantine rate | Event type/schema mới hoặc dữ liệu lỗi có tăng không |
| Output throughput | Sink có ghi đủ dữ liệu không |
| Consumer lag/application lag | Streams application có tụt lại không |
| Repartition topic traffic | Đổi key có tạo network/disk overhead lớn không |
| Serialization error | Serde có tương thích với input/output schema không |
| Task/stream thread state | Có thread hoặc task bị chết không |
| Transaction abort rate | Exactly-once transaction có lỗi hoặc timeout không |
| Output partition skew | Một key/partition có gây hot spot không |

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không có record ở output | Predicate không khớp, không có default branch hoặc sink sai topic | Kiểm tra branch count và topology description |
| Event vào nhánh không mong muốn | Predicate rộng đứng trước predicate cụ thể | Sắp xếp lại predicate và thêm test overlap |
| Một event xuất hiện ở nhiều topic | Có nhiều sink path/fan-out | Xác minh đây là chủ đích hay cấu hình nhầm |
| Merge output không theo timestamp | Merge không bảo đảm thứ tự toàn cục | Dùng sequence/event-time strategy nếu cần |
| State aggregation sai sau merge | Key/partitioning không đồng nhất | Re-key/repartition và kiểm tra topology |
| Sink serialize thất bại | Output Serde hoặc schema không tương thích | Kiểm tra Produced Serde và registry |
| Task restart liên tục | Deserialization, processor exception, broker hoặc transaction error | Kiểm tra Streams logs, handler và broker authorization |
| Default branch tăng mạnh | Producer phát event type mới hoặc schema rollout | Kiểm tra producer version và contract |

## 19. Bài thực hành: định tuyến và hợp nhất order events

Tạo ba input topic hoặc một input topic orders.events có event type CREATED, CANCELLED và UPDATED.

1. Tạo topology đọc orders.events bằng String key và OrderEvent value Serde.
2. Dùng split/branch để tách CREATED, CANCELLED và default.
3. Ghi từng nhánh vào topic riêng và xác minh output.
4. Gộp CREATED và CANCELLED bằng merge rồi ghi orders.lifecycle.
5. Gửi event UPDATED và xác minh nó chỉ vào default topic.
6. Đổi thứ tự predicate để tạo một event khớp hai điều kiện; xác minh nhánh đầu tiên thắng.
7. Tạo hai input KStream cùng kiểu rồi merge; kiểm tra record từ cả hai nguồn.
8. Gửi hai record cùng key từ hai topic và quan sát merge không join, không sort theo timestamp.
9. selectKey sang customerId, repartition rồi groupByKey/count; xác minh aggregation theo customer.
10. Kiểm thử null value/tombstone và event type không biết.
11. Dùng TopologyTestDriver kiểm tra output key/value và default branch.
12. Chạy integration test với broker, kiểm tra ACL, output partitioning và processing guarantee.

Chỉ thử nghiệm trên môi trường lab. Không đổi partition count hoặc ACL của topic production trong bài thực hành.

## 20. Checklist khi thiết kế topology

- Xác định event type và điều kiện của từng branch.
- Sắp xếp predicate từ cụ thể tới tổng quát.
- Có default branch hoặc chủ đích loại bỏ record không khớp.
- Xử lý null/tombstone trước khi truy cập field.
- Không đặt side effect bên ngoài trong predicate hoặc mapper.
- Dùng merge chỉ khi các stream có key/value semantics tương thích.
- Không nhầm merge với join hoặc deduplication.
- Không giả định merge tạo thứ tự toàn cục.
- Giữ key theo aggregate nếu cần ordering.
- Repartition khi đổi key trước stateful operation nếu partitioning chưa được đảm bảo.
- Chọn output topic, partition count, replication, retention và cleanup policy trước deployment.
- Cấu hình Produced Serde đúng schema của sink.
- Cấp ACL riêng cho input, output và internal topics.
- Chọn processing guarantee phù hợp và hiểu transaction boundary.
- Test branch overlap, default branch, merge, null, Serde và repartition.
- Theo dõi branch distribution, sink throughput, lag và transaction errors.

## 21. Những nhầm lẫn thường gặp

- **Branch phát một record vào mọi nhánh khớp:** split/branch xét theo thứ tự và đưa record vào nhánh đầu tiên khớp.
- **Không cần default branch:** record không khớp có thể biến mất khỏi các output path.
- **Merge là join:** merge chỉ hợp nhất record, không ghép hai record theo key.
- **Merge tự loại duplicate:** record lặp từ hai nguồn vẫn có thể xuất hiện nhiều lần.
- **Merge sắp xếp theo timestamp:** không có thứ tự toàn cục giữa các input partition/topic.
- **Hai stream cùng key chắc chắn cùng partition:** partitioner và partition count có thể khác nhau.
- **Đổi key không ảnh hưởng state:** stateful operation cần repartition theo key mới.
- **to() tự tạo topic đúng cấu hình:** topic nên được provisioning với partition/replication/retention phù hợp.
- **Output Serde có thể dùng bất kỳ:** sink serializer phải khớp định dạng downstream mong đợi.
- **Exactly-once bao gồm HTTP/database side effect:** guarantee của Kafka Streams chỉ bao trùm các thao tác Kafka trong transaction boundary.
- **Branch xử lý được deserialization exception:** lỗi deserialize xảy ra trước khi predicate nhận được typed record.

Branch, merge và sink là các khối nền tảng để xây dựng topology định tuyến trong Kafka Streams. Branch phân loại record theo predicate có thứ tự; merge hợp nhất nhiều luồng mà không join, deduplicate hay sắp xếp toàn cục; to ghi record ra output topic với key/value Serde và topic policy đã chọn. Khi kết hợp chúng, cần giữ đúng semantics của key, partition, ordering, null/tombstone và processing guarantee để pipeline có thể kiểm thử và vận hành ổn định.
