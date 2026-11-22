# StreamsBuilder, Serdes và cấu hình ứng dụng

Kafka Streams là thư viện Java để xây dựng ứng dụng xử lý luồng dữ liệu trực tiếp từ Kafka. Ứng dụng mô tả các bước đọc, biến đổi, nhóm, tổng hợp và ghi dữ liệu bằng một topology. StreamsBuilder là điểm bắt đầu để khai báo topology bằng DSL; Serdes xác định cách chuyển key/value giữa byte trong Kafka và object Java; StreamsConfig cung cấp cấu hình để khởi chạy và vận hành ứng dụng.

Bài này xây dựng một ứng dụng tổng hợp đơn hàng: đọc event JSON từ topic orders.events, nhóm theo orderId, tính số event và tổng giá trị, lưu kết quả vào state store rồi ghi các bản cập nhật sang orders.summary. Qua ví dụ, người học sẽ hiểu cách chọn KStream/KTable, gắn Serde tại từng ranh giới, cấu hình application.id, broker, state directory, processing guarantee và quản lý lifecycle của KafkaStreams.

## 1. Ba thành phần cốt lõi

| Thành phần | Vai trò | Câu hỏi nó giải quyết |
|---|---|---|
| StreamsBuilder | Khai báo nguồn, processor, state store và sink để tạo topology | Dữ liệu đi qua những bước nào? |
| Serdes | Cung cấp serializer và deserializer cho key/value | Byte Kafka được chuyển thành kiểu Java nào và ngược lại? |
| StreamsConfig | Cấu hình ứng dụng, consumer, producer, state và processing guarantee | Ứng dụng chạy với identity, broker và semantics nào? |

Ba thành phần kết hợp với nhau:

~~~mermaid
flowchart TD
    A[StreamsConfig<br/>application.id, brokers, Serdes defaults] --> D[KafkaStreams]
    B[StreamsBuilder<br/>source, operators, state store, sink] --> C[Topology]
    C --> D
    E[Serdes<br/>key/value byte conversion] --> B
    D --> F[Kafka topics]
    D --> G[Local state + changelog]
~~~

StreamsBuilder chỉ mô tả cách xử lý. KafkaStreams mới khởi chạy topology, tạo consumer/producer nội bộ, tham gia consumer group, phân phối task và quản lý state store.

## 2. Topology là gì?

Topology là đồ thị xử lý gồm:

- **Source:** đọc record từ một hoặc nhiều Kafka topic.
- **Processor/operator:** filter, map, branch, group, aggregate, join hoặc transform record.
- **State store:** lưu trạng thái cục bộ mà processor cần để tổng hợp hoặc tra cứu.
- **Sink:** ghi kết quả sang Kafka topic.

Ví dụ luồng tổng hợp đơn hàng:

~~~text
orders.events
     |
     v
KStream<String, OrderEvent>
     |
  filter event hợp lệ
     |
  groupByKey(orderId)
     |
  aggregate
     |
  KTable<String, OrderSummary>
     |
  toStream()
     |
     v
orders.summary
~~~

Topology có thể được kiểm tra trước khi start bằng builder.build() và topology.describe(). Việc mô tả topology giúp kiểm tra source, sink, processor và repartition topic trước khi triển khai.

## 3. StreamsBuilder và các thao tác khai báo topology

Tạo builder:

~~~java
import org.apache.kafka.streams.StreamsBuilder;

StreamsBuilder builder = new StreamsBuilder();
~~~

Các API thường dùng:

| API | Kết quả | Khi dùng |
|---|---|---|
| builder.stream(topic) | KStream<K,V> | Đọc event như một chuỗi record |
| builder.table(topic) | KTable<K,V> | Đọc topic như changelog của bảng key/value |
| builder.globalTable(topic) | GlobalKTable<K,V> | Sao chép toàn bộ bảng tham chiếu đến mỗi instance |
| builder.build() | Topology | Hoàn tất đồ thị để khởi chạy |

Nên dùng overload có Consumed.with(keySerde, valueSerde) để xác định rõ cách deserialize ngay tại source:

~~~java
KStream<String, OrderEvent> events = builder.stream(
        "orders.events",
        Consumed.with(Serdes.String(), orderEventSerde));
~~~

Khi source có nhiều kiểu dữ liệu, khai báo Serde ở từng source sẽ dễ đọc và ít gây nhầm lẫn hơn việc phụ thuộc hoàn toàn vào default Serdes của ứng dụng.

## 4. Phân biệt KStream, KTable và GlobalKTable

KStream biểu diễn chuỗi sự kiện. Mỗi record được xem là một sự kiện độc lập; nhiều record có cùng key vẫn là nhiều sự kiện.

KTable biểu diễn trạng thái mới nhất theo key. Record mới cho một key cập nhật giá trị của key đó; record có value null thường được hiểu là tombstone để xóa key khỏi bảng.

GlobalKTable cũng biểu diễn bảng theo key nhưng được sao chép đầy đủ đến từng instance của ứng dụng. Nó tiện cho lookup/join với bảng tham chiếu nhỏ, đổi lại mỗi instance phải nhận toàn bộ dữ liệu của topic global table.

| Đặc điểm | KStream | KTable | GlobalKTable |
|---|---|---|---|
| Mô hình | Event stream | Changelog/table theo key | Bảng đầy đủ trên mỗi instance |
| Cùng key xuất hiện nhiều lần | Mỗi record là một event | Giá trị mới cập nhật giá trị trước | Giá trị mới cập nhật bảng cục bộ |
| Phân phối dữ liệu | Theo partition | Theo partition | Mỗi instance nhận tất cả partition |
| Dùng phổ biến | Filter, map, event processing | Aggregate, materialized state | Lookup/join với dữ liệu tham chiếu |
| Chi phí state | Tùy topology | Có state store khi materialize | Bộ nhớ/state trên mỗi instance lớn hơn |

Không chọn KTable chỉ vì dữ liệu có key. Hãy chọn theo ý nghĩa: cần xử lý mọi lần phát sinh thì dùng KStream; cần biểu diễn trạng thái mới nhất theo key thì dùng KTable.

## 5. Serde, Serializer và Deserializer

Kafka lưu key/value dưới dạng byte. Ứng dụng Java làm việc với object, vì vậy cần hai chiều chuyển đổi:

- Serializer<T> chuyển object Java thành byte[] trước khi ghi Kafka.
- Deserializer<T> chuyển byte[] thành object Java khi đọc Kafka.
- Serde<T> đóng gói serializer và deserializer của cùng một kiểu dữ liệu.

Kafka cung cấp các Serdes dựng sẵn:

| Serde | Kiểu Java |
|---|---|
| Serdes.String() | String |
| Serdes.ByteArray() | byte[] |
| Serdes.ByteBuffer() | ByteBuffer |
| Serdes.Integer() | Integer |
| Serdes.Long() | Long |
| Serdes.Short() | Short |
| Serdes.Double() | Double |
| Serdes.Float() | Float |
| Serdes.UUID() | UUID |

Với kiểu nghiệp vụ như OrderEvent hoặc OrderSummary, cần Serde riêng. Không thể giả định Kafka Streams tự biết cách serialize Java record, POJO hoặc collection.

## 6. Default Serdes và Serde tường minh

Có thể khai báo Serde mặc định trong StreamsConfig:

~~~java
properties.put(
        StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
        Serdes.StringSerde.class);
properties.put(
        StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
        Serdes.StringSerde.class);
~~~

Default Serdes được dùng khi DSL không nhận được Serde tường minh ở một số thao tác. Nếu source chứa JSON thành object Java nhưng default value Serde vẫn là String, cần truyền Serde JSON tại Consumed, Grouped, Materialized hoặc Produced tương ứng.

Các điểm gắn Serde thường gặp:

| DSL API | Tham số | Mục đích |
|---|---|---|
| Consumed.with(k, v) | Key/value Serde | Deserialize source topic |
| Produced.with(k, v) | Key/value Serde | Serialize sink topic |
| Grouped.with(k, v) | Key/value Serde | Serialize record khi group/repartition |
| Materialized.with(k, v) | Key/value Serde | Lưu key/value trong state store |
| Repartitioned.with(k, v) | Key/value Serde | Serialize repartition topic |

Nên truyền Serde tường minh tại các ranh giới quan trọng. Điều này đặc biệt cần thiết khi topology dùng nhiều kiểu value khác nhau.

## 7. Tạo JSON Serde cho kiểu nghiệp vụ

Ví dụ dùng Jackson để chuyển object Java thành JSON bytes. Với Kafka Streams Java API, thêm dependency kafka-streams cùng phiên bản Kafka client mà dự án sử dụng. Ví dụ:

~~~xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-streams</artifactId>
    <version>3.9.1</version>
</dependency>
~~~

Ví dụ record trong bài dùng Java record; chọn JDK 17 trở lên. Nếu dùng Spring Boot dependency management, để Boot quản lý phiên bản Kafka Streams tương thích thay vì ghim một version riêng. Jackson databind:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.18.2</version>
</dependency>
~~~

Định nghĩa event và kết quả tổng hợp:

~~~java
package com.example.streams.model;

import java.math.BigDecimal;

public record OrderEvent(
        String eventId,
        String orderId,
        BigDecimal amount
) {
}

public record OrderSummary(
        long eventCount,
        BigDecimal totalAmount
) {
}
~~~

Trong Java, mỗi public top-level record nên nằm trong file riêng (OrderEvent.java và OrderSummary.java).

JSON Serde dùng chung:

~~~java
package com.example.streams.serde;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.common.errors.SerializationException;
import org.apache.kafka.common.serialization.Deserializer;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serializer;
import org.apache.kafka.common.serialization.Serdes;

import java.io.IOException;

public final class JsonSerdes {
    private JsonSerdes() {
    }

    public static <T> Serde<T> of(Class<T> type) {
        ObjectMapper mapper = new ObjectMapper();

        Serializer<T> serializer = (topic, data) -> {
            if (data == null) {
                return null;
            }
            try {
                return mapper.writeValueAsBytes(data);
            } catch (JsonProcessingException exception) {
                throw new SerializationException(
                        "Cannot serialize " + type.getName(), exception);
            }
        };

        Deserializer<T> deserializer = (topic, bytes) -> {
            if (bytes == null) {
                return null;
            }
            try {
                return mapper.readValue(bytes, type);
            } catch (IOException exception) {
                throw new SerializationException(
                        "Cannot deserialize " + type.getName(), exception);
            }
        };

        return Serdes.serdeFrom(serializer, deserializer);
    }
}
~~~

ObjectMapper được tạo một lần cho mỗi Serde và được tái sử dụng. Với kiểu dữ liệu có Instant, LocalDate hoặc LocalDateTime, đăng ký Jackson Java Time module và thống nhất định dạng thời gian giữa producer/consumer.

JSON Serde ở ví dụ là cách học và phù hợp cho payload đơn giản. Trong hệ thống nhiều service, nên quản lý schema evolution có quy tắc (ví dụ schema version hoặc schema registry), xác định tương thích khi thêm/xóa field và xử lý payload không hợp lệ. Không dùng Java class name làm hợp đồng dữ liệu giữa các hệ thống độc lập.

## 8. Cấu hình StreamsConfig

StreamsConfig nhận một Properties chứa cấu hình Kafka Streams và một số cấu hình consumer/producer được chuyển tiếp. Các cấu hình quan trọng:

| Property | Ý nghĩa | Gợi ý |
|---|---|---|
| application.id | Identity của Kafka Streams application; cũng dùng làm consumer group ID và prefix cho internal topics | Ổn định cho cùng một ứng dụng logic |
| bootstrap.servers | Địa chỉ broker để kết nối cluster | Dùng nhiều broker để tăng khả năng kết nối |
| default.key.serde | Serde mặc định cho key | Serdes.StringSerde nếu key là String |
| default.value.serde | Serde mặc định cho value | Chọn kiểu phổ biến hoặc cấu hình rõ tại từng node |
| num.stream.threads | Số stream thread trong mỗi instance | Tăng theo CPU và số task có thể chạy |
| state.dir | Thư mục local chứa state store và dữ liệu phục hồi | Thư mục bền vững, có dung lượng và quyền ghi |
| processing.guarantee | Semantics xử lý at-least-once hoặc exactly-once v2 | Chọn theo yêu cầu và chi phí |
| replication.factor | Replication factor của internal repartition/changelog topics | Production thường dùng từ 3 nếu cluster cho phép |
| commit.interval.ms | Chu kỳ commit/flush theo cơ chế Streams | Cân bằng latency và overhead |
| cache.max.bytes.buffering | Dung lượng cache record/state buffering trong các phiên bản hỗ trợ | Điều chỉnh theo memory và workload |
| auto.offset.reset | Chính sách khi không có offset hợp lệ | earliest, latest hoặc none theo nghiệp vụ |

application.id là cấu hình đặc biệt quan trọng. Các instance của cùng một logical Streams application phải dùng cùng ID để chia sẻ task và state. Hai topology độc lập hoặc hai môi trường dev/prod cần ID khác nhau để không dùng chung consumer group và internal topics.

num.stream.threads là số luồng xử lý trong một instance, không phải số partition. Kafka Streams tạo task dựa trên partition của source topic và các repartition topic; số task có thể chạy song song là giới hạn thực tế của topology. Nếu cấu hình nhiều thread hơn số task có thể chạy, một số thread sẽ idle. Muốn tăng parallelism, cần xem số partition, topology và năng lực broker trước khi chỉ tăng thread.

cache.max.bytes.buffering có thể xuất hiện trong cấu hình của các phiên bản Kafka Streams cũ; ở phiên bản mới, kiểm tra tên property cache state store được hỗ trợ (ví dụ statestore.cache.max.bytes). Đối chiếu đúng version Kafka Streams thay vì sao chép property giữa các phiên bản.

## 9. Cấu hình ứng dụng bằng Properties

Ví dụ cấu hình cho lab một broker:

~~~java
Properties properties = new Properties();
properties.put(StreamsConfig.APPLICATION_ID_CONFIG, "order-summary-streams");
properties.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
properties.put(StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
        Serdes.StringSerde.class);
properties.put(StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
        Serdes.StringSerde.class);
properties.put(StreamsConfig.NUM_STREAM_THREADS_CONFIG, 2);
properties.put(StreamsConfig.STATE_DIR_CONFIG,
        Path.of("data/kafka-streams/order-summary").toAbsolutePath().toString());
properties.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG,
        StreamsConfig.AT_LEAST_ONCE);
properties.put(StreamsConfig.REPLICATION_FACTOR_CONFIG, (short) 1);
properties.put(StreamsConfig.COMMIT_INTERVAL_MS_CONFIG, 1000);
properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
~~~

replication.factor = 1 chỉ phù hợp cho lab một broker. Trong cluster production, cấu hình replication factor của internal topics phù hợp với số broker và durability policy. Với EXACTLY_ONCE_V2, broker cũng cần hỗ trợ transaction và internal transaction/offset topics phải có replication/min ISR tương ứng.

state.dir là local path của từng instance, không phải thư mục dùng chung giữa các máy. Không để hai KafkaStreams instance chạy đồng thời dùng cùng một state directory. Nếu instance bị thay thế, Kafka Streams có thể khôi phục state từ changelog topic; local disk tốt giúp khôi phục nhanh hơn.

## 10. Cấu hình bằng application.properties

Có thể lưu cấu hình cơ bản trong file properties:

~~~properties
spring.kafka.streams.application-id=order-summary-streams
spring.kafka.bootstrap-servers=localhost:9092

# Kafka Streams native properties are nested under spring.kafka.streams.properties
spring.kafka.streams.properties.default.key.serde=org.apache.kafka.common.serialization.Serdes$StringSerde
spring.kafka.streams.properties.default.value.serde=org.apache.kafka.common.serialization.Serdes$StringSerde
spring.kafka.streams.properties.num.stream.threads=2
spring.kafka.streams.properties.processing.guarantee=at_least_once
spring.kafka.streams.properties.replication.factor=1
spring.kafka.streams.properties.commit.interval.ms=1000
~~~

Đây là cú pháp Spring Boot application.properties: các thuộc tính riêng của Kafka Streams được đưa vào map spring.kafka.streams.properties. Nếu dùng Kafka Streams Java API trực tiếp, cấu hình native được đặt trực tiếp trong Properties như ví dụ ở mục trước. Không trộn hai kiểu cấu hình.

Ví dụ YAML Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    streams:
      application-id: order-summary-streams
      properties:
        default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
        default.value.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
        num.stream.threads: 2
        processing.guarantee: at_least_once
        replication.factor: 1
        commit.interval.ms: 1000
~~~

Phần còn lại của bài dùng Kafka Streams Java API trực tiếp để làm rõ StreamsBuilder và KafkaStreams lifecycle. Với Spring Boot, có thể khai báo StreamsBuilderFactoryBean và cấu hình topology qua bean; tránh tự tạo một KafkaStreams instance song song nếu framework đã quản lý lifecycle.

## 11. Xây dựng topology tổng hợp đơn hàng

Mục tiêu: mỗi event có key là orderId; ứng dụng tính tổng số event và tổng amount theo order. Ví dụ này dùng KStream làm nguồn và KTable làm trạng thái tổng hợp.

~~~java
package com.example.streams;

import com.example.streams.model.OrderEvent;
import com.example.streams.model.OrderSummary;
import com.example.streams.serde.JsonSerdes;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Produced;
import org.apache.kafka.streams.state.KeyValueStore;

import java.math.BigDecimal;

public final class OrderSummaryTopology {
    public static final String INPUT_TOPIC = "orders.events";
    public static final String OUTPUT_TOPIC = "orders.summary";

    private OrderSummaryTopology() {
    }

    public static Topology build() {
        Serde<OrderEvent> orderEventSerde = JsonSerdes.of(OrderEvent.class);
        Serde<OrderSummary> summarySerde = JsonSerdes.of(OrderSummary.class);

        StreamsBuilder builder = new StreamsBuilder();

        KStream<String, OrderEvent> events = builder.stream(
                INPUT_TOPIC,
                Consumed.with(Serdes.String(), orderEventSerde));

        KTable<String, OrderSummary> summaries = events
                .filter((orderId, event) ->
                        orderId != null
                                && event != null
                                && event.amount() != null
                                && event.amount().signum() > 0)
                .groupByKey(Grouped.with(Serdes.String(), orderEventSerde))
                .aggregate(
                        () -> new OrderSummary(0L, BigDecimal.ZERO),
                        (orderId, event, current) -> new OrderSummary(
                                current.eventCount() + 1,
                                current.totalAmount().add(event.amount())),
                        Materialized.<String, OrderSummary,
                                KeyValueStore<Bytes, byte[]>>as("order-summary-store")
                                .withKeySerde(Serdes.String())
                                .withValueSerde(summarySerde));

        summaries.toStream().to(
                OUTPUT_TOPIC,
                Produced.with(Serdes.String(), summarySerde));

        return builder.build();
    }
}
~~~

Các điểm cần chú ý:

- Source khai báo Consumed.with để deserialize key String và value JSON thành OrderEvent.
- filter loại record không có key hoặc amount không hợp lệ trước khi aggregate.
- groupByKey dùng key hiện tại là orderId; nếu đổi key bằng selectKey hoặc groupBy, Kafka Streams có thể cần repartition để đưa cùng key về cùng partition.
- aggregate tạo state store order-summary-store và cập nhật summary theo từng event.
- Materialized khai báo Serde của state store; thiếu Serde phù hợp có thể gây lỗi khi ghi/đọc state hoặc phục hồi từ changelog.
- toStream().to(...) chuyển các cập nhật của KTable thành record để ghi sang output topic.

orders.summary nhận các bản cập nhật của bảng theo key, không phải chỉ một kết quả cuối cùng duy nhất. Nếu một order nhận thêm event, summary của order đó được phát lại với count và total mới.

Ví dụ trên không deduplicate theo eventId. Nếu producer gửi cùng event hai lần ở hai offset khác nhau, aggregate sẽ cộng hai lần. Muốn loại duplicate cần bổ sung state store/inbox theo eventId hoặc đảm bảo upstream phát event idempotent.

## 12. Khởi chạy KafkaStreams và quản lý lifecycle

builder.build() tạo topology; KafkaStreams kết hợp topology với cấu hình để khởi chạy:

~~~java
package com.example.streams;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.Topology;

import java.nio.file.Path;
import java.time.Duration;
import java.util.Properties;

public final class OrderSummaryApplication {
    public static void main(String[] args) {
        Properties properties = new Properties();
        properties.put(StreamsConfig.APPLICATION_ID_CONFIG,
                "order-summary-streams");
        properties.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
                System.getenv().getOrDefault(
                        "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"));
        properties.put(StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
                Serdes.StringSerde.class);
        properties.put(StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
                Serdes.StringSerde.class);
        properties.put(StreamsConfig.NUM_STREAM_THREADS_CONFIG, 2);
        properties.put(StreamsConfig.STATE_DIR_CONFIG,
                Path.of("data/kafka-streams/order-summary")
                        .toAbsolutePath().toString());
        properties.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG,
                StreamsConfig.AT_LEAST_ONCE);
        properties.put(StreamsConfig.REPLICATION_FACTOR_CONFIG, (short) 1);
        properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        Topology topology = OrderSummaryTopology.build();
        System.out.println(topology.describe());

        KafkaStreams streams = new KafkaStreams(topology, properties);
        streams.setStateListener((newState, oldState) ->
                System.out.printf("Kafka Streams state: %s -> %s%n",
                        oldState, newState));

        Runtime.getRuntime().addShutdownHook(new Thread(
                () -> streams.close(Duration.ofSeconds(10)),
                "streams-shutdown"));

        streams.start();
    }
}
~~~

Các trạng thái của KafkaStreams giúp quan sát lifecycle: CREATED, REBALANCING, RUNNING, PENDING_SHUTDOWN và NOT_RUNNING. Trong production, kết hợp state listener với log/metric và xử lý lỗi thread theo chính sách ứng dụng.

Khi dừng process, gọi close(Duration) để đóng thread và tài nguyên có kiểm soát. Không xóa state directory khi ứng dụng đang chạy.

## 13. application.id và state.dir

application.id ảnh hưởng trực tiếp đến định danh và tài nguyên Kafka:

- Là consumer group ID mà Kafka Streams dùng để phối hợp các instance.
- Là prefix cho internal repartition/changelog topics.
- Gắn với committed offsets và trạng thái xử lý của topology.
- Quyết định ứng dụng tiếp tục từ offset cũ hay khởi tạo một logical application mới.

Quy tắc:

| Tình huống | application.id |
|---|---|
| Nhiều replica của cùng một service/topology | Giống nhau |
| Dev và production | Khác nhau |
| Hai topology độc lập | Khác nhau |
| Muốn chạy lại từ đầu như ứng dụng logic mới | Dùng ID mới có chủ đích hoặc reset theo quy trình |

state.dir lưu state store local và dữ liệu phục hồi theo task. Mỗi instance cần thư mục riêng, local và có quyền đọc/ghi. Trong container, mount volume phù hợp nếu muốn giảm thời gian khôi phục sau restart. Changelog topic vẫn là nguồn phục hồi state khi local store mất.

Không xóa state directory hoặc đổi application.id tùy tiện để “sửa” lỗi. Việc đó có thể làm ứng dụng rebuild state, đọc lại dữ liệu hoặc tạo internal topics mới; cần đánh giá tác động tới offset và kết quả output.

## 14. Repartition topic và state store

Khi topology cần gom record theo key mới, Kafka Streams có thể tạo repartition topic nội bộ. Ví dụ:

~~~java
events
    .selectKey((oldKey, event) -> event.orderId())
    .groupByKey(Grouped.with(Serdes.String(), orderEventSerde))
    .count();
~~~

selectKey thay key; groupByKey sau đó cần dữ liệu cùng key nằm cùng partition. Kafka Streams có thể chèn repartition node/topic giữa các bước.

State store giữ dữ liệu aggregate, window hoặc join. Với persistent state store, Kafka Streams thường tạo changelog topic để khôi phục trạng thái sau lỗi instance. Internal topics được quản lý theo application.id và cần replication/retention phù hợp.

Có thể đặt tên state store bằng Materialized.as("store-name") để dễ quan sát và truy vấn qua Interactive Queries khi topology hỗ trợ.

## 15. Processing guarantee và cấu hình commit

Kafka Streams hỗ trợ hai semantics chính:

| Guarantee | Ý nghĩa | Cấu hình |
|---|---|---|
| At-least-once | Record có thể được xử lý lại sau crash; ứng dụng cần idempotency nếu side effect có thể lặp | StreamsConfig.AT_LEAST_ONCE |
| Exactly-once v2 | Kafka phối hợp input offsets, output records và state changelog trong transaction | StreamsConfig.EXACTLY_ONCE_V2 |

Ví dụ bật exactly-once v2:

~~~java
properties.put(
        StreamsConfig.PROCESSING_GUARANTEE_CONFIG,
        StreamsConfig.EXACTLY_ONCE_V2);
~~~

Exactly-once v2 áp dụng cho luồng Kafka và state được Kafka Streams quản lý. Nó không tự đưa database, HTTP hoặc hệ thống ngoài vào cùng transaction. Side effect ngoài Kafka vẫn cần inbox/outbox hoặc idempotency.

commit.interval.ms ảnh hưởng chu kỳ commit/flush theo processing guarantee. Khi bật EOS, transaction và commit semantics do Kafka Streams quản lý; không tự tạo producer/consumer riêng để commit thay cho framework trong cùng topology.

## 16. Cấu hình bảo mật và môi trường

Trong cluster có bảo mật, bổ sung cấu hình tương ứng vào Properties:

~~~java
properties.put("security.protocol", "SASL_SSL");
properties.put("sasl.mechanism", "PLAIN");
properties.put("sasl.jaas.config", System.getenv("KAFKA_SASL_JAAS_CONFIG"));
~~~

Ví dụ chỉ minh họa vị trí cấu hình; mechanism, JAAS module, truststore và certificate phải khớp với cluster. Secret lấy từ secret manager/environment, không ghi trực tiếp vào source code hoặc log.

Các principal của Kafka Streams cần quyền đọc source topics, ghi sink topics, dùng consumer group tương ứng và tạo/đọc/ghi internal repartition/changelog topics. Với cluster bật ACL, cấp quyền theo application.id và resource topic/group cần thiết; không cấp quyền quản trị rộng nếu ứng dụng chỉ xử lý stream.

## 17. Kiểm tra topology trước khi triển khai

Luôn in hoặc lưu topology.describe() trong bước kiểm tra:

~~~java
Topology topology = OrderSummaryTopology.build();
System.out.println(topology.describe());
~~~

Kiểm tra:

- Source topics đúng tên và đúng key/value Serde.
- Các operator có đúng thứ tự.
- Có repartition node/topic ở vị trí dự kiến không.
- State store có tên rõ ràng và Serde phù hợp.
- Sink topic đúng tên, đúng key/value Serde.
- Không có branch/filter vô tình loại bỏ dữ liệu nghiệp vụ.

Topology description cho biết cấu trúc xử lý, nhưng không chứng minh dữ liệu runtime hợp lệ. Cần test với record đại diện, payload lỗi, null/tombstone và key phân phối qua nhiều partition.

## 18. Kiểm thử topology bằng TopologyTestDriver

TopologyTestDriver cho phép kiểm tra DSL mà không cần chạy Kafka broker thật. Thêm dependency test cùng phiên bản với kafka-streams:

~~~xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-streams-test-utils</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ví dụ test một event tạo ra summary:

~~~java
import com.example.streams.model.OrderEvent;
import com.example.streams.model.OrderSummary;
import com.example.streams.serde.JsonSerdes;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.TestInputTopic;
import org.apache.kafka.streams.TestOutputTopic;
import org.apache.kafka.streams.TopologyTestDriver;
import org.apache.kafka.streams.KeyValue;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderSummaryTopologyTest {
    @Test
    void aggregatesOrderEvents() {
        Properties properties = new Properties();
        properties.put(StreamsConfig.APPLICATION_ID_CONFIG, "order-summary-test");
        properties.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "dummy:9092");

        var orderSerde = JsonSerdes.of(OrderEvent.class);
        var summarySerde = JsonSerdes.of(OrderSummary.class);

        try (TopologyTestDriver driver = new TopologyTestDriver(
                OrderSummaryTopology.build(), properties)) {
            TestInputTopic<String, OrderEvent> input =
                    driver.createInputTopic(
                            OrderSummaryTopology.INPUT_TOPIC,
                            Serdes.String().serializer(),
                            orderSerde.serializer());

            TestOutputTopic<String, OrderSummary> output =
                    driver.createOutputTopic(
                            OrderSummaryTopology.OUTPUT_TOPIC,
                            Serdes.String().deserializer(),
                            summarySerde.deserializer());

            input.pipeInput("order-1",
                    new OrderEvent("evt-1", "order-1", new BigDecimal("120.00")));

            KeyValue<String, OrderSummary> result = output.readKeyValue();
            assertEquals("order-1", result.key);
            assertEquals(1L, result.value.eventCount());
            assertEquals(new BigDecimal("120.00"), result.value.totalAmount());
        }
    }
}
~~~

TopologyTestDriver kiểm tra logic topology, serialization và output trong môi trường test. Nó không thay thế integration test với broker thật để xác minh ACL, partition assignment, internal topics, rebalance, transaction coordinator hoặc khôi phục state sau crash.

## 19. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| ClassCastException hoặc serialization error | Default Serde không khớp kiểu dữ liệu tại node | Khai báo Consumed, Grouped, Materialized, Produced rõ ràng |
| Không deserialize được JSON | Schema/payload không khớp class hoặc Jackson module thiếu | Kiểm tra payload, type và module |
| State store không khôi phục | Changelog/internal topic lỗi, state directory hoặc Serde không tương thích | Kiểm tra internal topics, Serde và application.id |
| Hai ứng dụng dùng chung offset | Trùng application.id ngoài ý muốn | Đặt application.id khác cho ứng dụng độc lập |
| Instance tranh chấp local state | Dùng chung state.dir | Cấp local directory riêng cho từng instance |
| Lag tăng dù topology đơn giản | Số thread/task, downstream sink, repartition hoặc broker là nút thắt | Xem task assignment, throughput, commit và broker metrics |
| Topic output không có dữ liệu | Filter loại hết record, sink topic sai hoặc lỗi Serde | In topology, kiểm tra key/value và exception |
| Internal topic không tạo được | Thiếu ACL hoặc replication factor vượt số broker | Cấp ACL và cấu hình replication phù hợp môi trường |
| Chạy lại tạo kết quả khác | At-least-once replay hoặc input duplicate | Dùng eventId dedup/idempotency và chọn processing guarantee phù hợp |

## 20. Lab: chạy ứng dụng tổng hợp đơn hàng

### Bước 1: tạo topic đầu vào và đầu ra

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic orders.events --partitions 3 --replication-factor 1

kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic orders.summary --partitions 3 --replication-factor 1
~~~

Replication factor một chỉ dùng cho lab một broker. Trong cluster nhiều broker, chọn replication factor phù hợp.

### Bước 2: khởi chạy ứng dụng

Build project và chạy OrderSummaryApplication. Xem log state chuyển sang RUNNING và đọc topology description để kiểm tra source, aggregate state store và sink.

### Bước 3: gửi event JSON

Gửi ba record với key là orderId:

~~~text
key=order-1 value={"eventId":"evt-1","orderId":"order-1","amount":120.00}
key=order-1 value={"eventId":"evt-2","orderId":"order-1","amount":80.00}
key=order-2 value={"eventId":"evt-3","orderId":"order-2","amount":50.00}
~~~

Có thể dùng producer Java hoặc console producer với parse.key=true và key.separator=: để phát record có key.

### Bước 4: đọc kết quả

Đọc topic orders.summary và kiểm tra:

- order-1 có eventCount = 1, totalAmount = 120.00 sau event đầu.
- order-1 được cập nhật eventCount = 2, totalAmount = 200.00 sau event thứ hai.
- order-2 có eventCount = 1, totalAmount = 50.00.

KTable phát các bản cập nhật; output có thể chứa nhiều phiên bản liên tiếp của cùng key.

### Bước 5: thử lỗi Serde

Gửi payload JSON không hợp lệ hoặc amount sai kiểu. Quan sát lỗi deserialization và quyết định exception handling/quarantine phù hợp. Không để payload lỗi làm ứng dụng restart liên tục mà không có cảnh báo.

### Bước 6: thử restart và state recovery

Dừng ứng dụng bằng shutdown hook, sau đó khởi động lại với cùng application.id và state.dir. Xác nhận ứng dụng tiếp tục từ committed offsets và khôi phục state. Trong lab riêng, thử xóa local state directory khi app đã dừng để quan sát state được phục hồi từ changelog; không thực hiện trên môi trường production.

### Bước 7: thử exactly-once v2

Đổi processing.guarantee sang exactly_once_v2, bảo đảm broker và internal topics hỗ trợ transaction. Chạy lại lab và so sánh behavior khi restart. Exactly-once Kafka Streams không bao gồm side effect database/HTTP.

## 21. Checklist triển khai

- application.id ổn định cho cùng logical application và khác giữa các môi trường độc lập.
- bootstrap.servers trỏ tới listener mà ứng dụng có thể truy cập.
- Key/value Serde được khai báo đúng tại source, repartition, state store và sink.
- state.dir là local path riêng, có quyền ghi và đủ dung lượng.
- Internal topic replication factor phù hợp số broker.
- Input/output topics đã được provision với partition và retention phù hợp.
- processing.guarantee được chọn theo yêu cầu và năng lực cluster.
- Có graceful shutdown và theo dõi KafkaStreams state.
- Có topology description và test bằng TopologyTestDriver.
- Có integration test cho broker, ACL, rebalance và state recovery.
- Có metric cho stream thread, task, consumer lag, processing latency và state restore.

## 22. Ghi nhớ

| Khái niệm | Cần nhớ |
|---|---|
| StreamsBuilder | Khai báo source, operator, state store và sink |
| Topology | Đồ thị xử lý được build từ builder |
| KStream | Chuỗi event |
| KTable | Trạng thái mới nhất theo key |
| GlobalKTable | Bảng được sao chép đầy đủ đến mỗi instance |
| Serde | Kết hợp serializer và deserializer |
| Consumed / Produced | Khai báo Serde tại source và sink |
| Grouped / Materialized | Khai báo Serde cho grouping và state store |
| application.id | Định danh logical Streams application và internal resources |
| state.dir | Thư mục state cục bộ của instance |
| KafkaStreams | Quản lý lifecycle và thực thi topology |
| TopologyTestDriver | Kiểm thử topology không cần broker thật |

StreamsBuilder mô tả luồng xử lý, Serdes bảo đảm dữ liệu được chuyển đổi đúng kiểu, còn StreamsConfig xác định ứng dụng tham gia cluster và lưu state như thế nào. Khi khai báo Serde tường minh tại source, repartition, state store và sink, đồng thời quản lý đúng application.id và state.dir, topology sẽ dễ kiểm tra, phục hồi và vận hành hơn.
