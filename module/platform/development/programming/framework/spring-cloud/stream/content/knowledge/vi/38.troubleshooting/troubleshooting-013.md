# Kafka Streams thiếu Serde, state store chưa sẵn sàng hoặc lỗi phục hồi

Một ứng dụng Spring Cloud Stream dùng Kafka Streams có thể khởi động được nhưng không xử lý được record, hoặc xử lý input rồi dừng khi truy vấn state store. Các nguyên nhân thường gặp gồm Serde không khớp với dữ liệu trên topic, Serde bên trong topology chưa được khai báo, state store chưa được materialize hoặc đăng ký, local RocksDB không truy cập được, hay Kafka Streams đang phục hồi state từ changelog topic.

Ba tình huống này có biểu hiện khác nhau:

- **Serde lỗi:** record không thể chuyển từ byte thành key/value hoặc từ object thành byte; lỗi thường xuất hiện ở biên input/output hoặc khi state store đọc changelog.
- **Store chưa sẵn sàng:** topology đang khởi tạo, rebalance hoặc restore; truy vấn interactive query có thể nhận InvalidStateStoreException dù process vẫn sống.
- **Restore thất bại hoặc kéo dài:** Kafka Streams không thể đọc changelog, ghi local state, hoặc bắt kịp offset để đưa task vào trạng thái hoạt động.

Bài học này hướng dẫn kiểm tra theo thứ tự Serde → topology/state store → changelog/restoration → health và vận hành. Các ví dụ sử dụng functional model của Spring Cloud Stream với KStream, KTable, Kafka Streams Binder và Micrometer/Actuator.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt lỗi Serde ở input/output với lỗi Serde dùng bên trong topology.
- Hiểu cách Kafka Streams Binder suy luận key/value Serde và thứ tự ưu tiên cấu hình.
- Cấu hình Serde theo binding hoặc ở cấp binder.
- Biết khi nào cần tắt native decoding/encoding để dùng Spring MessageConverter.
- Materialize state store bằng DSL, KTable hoặc Processor API.
- Giải thích changelog topic và cách Kafka Streams phục hồi local state.
- Chẩn đoán InvalidStateStoreException, RocksDB, disk, ACL và changelog.
- Theo dõi restoration, thread state, active/standby task và store readiness.
- Chọn application.id, state.dir, standby replicas và retry policy phù hợp.
- Kiểm thử Serde, state store và quá trình phục hồi sau restart.

## 1. Phân biệt ba tầng lỗi

Một Kafka Streams topology có thể đọc record, biến đổi dữ liệu, cập nhật state store rồi phát output. Khi có lỗi, cần xác định nó xảy ra ở đâu:

~~~mermaid
flowchart TD
    A["Kafka input topic"] --> B["Key/value deserialization"]
    B --> C["KStream / KTable topology"]
    C --> D["State store read/write"]
    D --> E["Key/value serialization"]
    E --> F["Kafka output topic"]
    D <--> G["Changelog topic"]
    G --> H["Restore consumer"]
    H --> D
    D --> I["Interactive query"]
~~~

| Tầng | Dấu hiệu thường gặp | Câu hỏi đầu tiên |
|---|---|---|
| Input Serde | SerializationException, DeserializationException, record bị fail/skip/DLQ | Bytes trên topic có đúng format và schema không? |
| Topology Serde | Lỗi khi groupBy, aggregate, join, Materialized hoặc Processor API | Serde truyền cho operation/state store có đúng key/value type không? |
| Output Serde | Lỗi khi ghi output topic | Output key/value có Serde phù hợp với wire contract không? |
| Store readiness | InvalidStateStoreException, store không query được lúc startup | Task đã được assign và restore xong chưa? |
| State restoration | Restore lag không giảm, RocksDB/disk error, changelog fetch error | Kafka Streams có đọc được changelog và ghi local state không? |

Serde là viết tắt của serializer/deserializer. Một Serde kết hợp Serializer<T> và Deserializer<T> cho cùng một kiểu dữ liệu. Kafka lưu bytes; Java type chỉ xuất hiện sau khi deserializer chuyển bytes thành object.

Không nhầm content-type của Spring Message với Kafka Streams Serde. Kafka Streams Binder mặc định sử dụng native Serde của Kafka cho key và value. Spring MessageConverter chỉ tham gia khi native decoding/encoding được tắt theo binding.

## 2. Cách Kafka Streams Binder suy luận Serde

Với Kafka Streams Binder, key được deserialize bằng native Serde. Value inbound mặc định cũng được Kafka deserialize native. Binder cố suy luận Serde từ chữ ký Function hoặc Consumer và các bean trong ApplicationContext.

Thứ tự suy luận thường dùng:

1. Serde được cấu hình trực tiếp trên input/output binding có ưu tiên cao nhất.
2. Binder tìm bean Serde<T> có generic type khớp với kiểu key/value trong chữ ký topology.
3. Binder nhận diện các kiểu có Serde dựng sẵn như String, Integer, Long, Short, Double, Float, byte[] và UUID.
4. Binder kiểm tra Serde mặc định trong Kafka Streams configuration.
5. Nếu không có cấu hình phù hợp, binder có thể fallback sang JsonSerde của Spring Kafka cho các kiểu JSON-friendly.

Khi đã khai báo Serde ở cấp binding, binder dùng Serde đó thay vì tiếp tục suy luận. Điều này hữu ích khi cùng một topology có nhiều input với các schema khác nhau.

Ví dụ chữ ký:

~~~java
@Bean
Function<KStream<String, OrderCreated>,
         KStream<String, OrderAccepted>> acceptOrders() {
    return orders -> orders.mapValues(order ->
        new OrderAccepted(order.orderId(), "ACCEPTED")
    );
}
~~~

Binder có thể nhận ra key là String và value là OrderCreated/OrderAccepted. String có Serde dựng sẵn. Với object nghiệp vụ, binder có thể dùng Serde<OrderCreated> hoặc JSON fallback nếu phù hợp.

### Khai báo Serde bean

Nếu muốn kiểm soát JSON Serde rõ ràng, cung cấp bean có generic type tương ứng:

~~~java
import org.apache.kafka.common.serialization.Serde;
import org.springframework.kafka.support.serializer.JsonSerde;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderSerdeConfiguration {

    @Bean
    Serde<OrderCreated> orderCreatedSerde() {
        return new JsonSerde<>(OrderCreated.class);
    }

    @Bean
    Serde<OrderAccepted> orderAcceptedSerde() {
        return new JsonSerde<>(OrderAccepted.class);
    }
}
~~~

Tên bean giúp người đọc nhận biết mục đích. Quan trọng là kiểu generic Serde<OrderCreated> phải khớp với value type mà topology khai báo. Nếu bean trả về raw Serde, binder có thể không suy luận được kiểu cụ thể.

Không tạo nhiều bean Serde cùng generic type nếu không có chiến lược chọn rõ ràng. Khi cùng một kiểu Java được serialize theo hai wire format khác nhau, hãy cấu hình theo binding để tránh binder chọn nhầm bean.

## 3. Cấu hình Serde theo binding

Khi inference không phù hợp, cấu hình keySerde và valueSerde cho từng binding.

Ví dụ processor có hai input:

~~~java
@Bean
BiFunction<KStream<CustomKey, OrderCreated>,
           KTable<CustomKey, CustomerProfile>,
           KStream<String, OrderSummary>> summarizeOrders() {
    // topology implementation
}
~~~

Cấu hình input:

~~~properties
spring.cloud.stream.kafka.streams.bindings.summarizeOrders-in-0.consumer.keySerde=com.acme.kafka.CustomKeySerde
spring.cloud.stream.kafka.streams.bindings.summarizeOrders-in-0.consumer.valueSerde=com.acme.kafka.OrderCreatedSerde

spring.cloud.stream.kafka.streams.bindings.summarizeOrders-in-1.consumer.keySerde=com.acme.kafka.CustomKeySerde
spring.cloud.stream.kafka.streams.bindings.summarizeOrders-in-1.consumer.valueSerde=com.acme.kafka.CustomerProfileSerde
~~~

Cấu hình output:

~~~properties
spring.cloud.stream.kafka.streams.bindings.summarizeOrders-out-0.producer.keySerde=org.apache.kafka.common.serialization.Serdes$StringSerde
spring.cloud.stream.kafka.streams.bindings.summarizeOrders-out-0.producer.valueSerde=com.acme.kafka.OrderSummarySerde
~~~

Tên binding được tạo từ function bean name và hướng input/output. Với BiFunction, hai input là summarizeOrders-in-0 và summarizeOrders-in-1; output là summarizeOrders-out-0.

Các class Serde tùy chỉnh trong ví dụ phải implement Serde cho đúng kiểu dữ liệu và có thể được binder khởi tạo/cấu hình theo cách dự án chọn. Nếu Serde cần schema registry hoặc secret, cấu hình các giá trị đó qua binder configuration hoặc typed Serde bean thay vì hard-code vào class.

Nếu mọi binding trong một processor đều dùng key và value kiểu String, có thể áp dụng Serde mặc định ở binder level:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
              default.value.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Cấu hình default chỉ phù hợp khi các binding thực sự dùng cùng wire type. Với topic chứa JSON object, Avro, Protobuf hoặc key có kiểu riêng, cấu hình Serde theo binding hoặc bean typed sẽ an toàn hơn.

### Lỗi key Serde và value Serde không giống nhau

Kafka record có key và value riêng. Chỉ cấu hình value Serde không sửa được lỗi key deserialization. Một số lỗi thường gặp:

- Producer ghi key bằng Avro nhưng consumer đọc key như String.
- Producer dùng UUID bytes nhưng consumer cấu hình StringSerde.
- Producer ghi JSON value nhưng consumer dùng Avro deserializer.
- Output key/value Serde không khớp với schema downstream.
- Windowed key cần Windowed Serde thay vì Serde của key gốc.

Khi thấy lỗi deserialize, đọc exception để xác định key hay value, topic, partition và offset. Đừng đổi cả hai Serde cùng lúc nếu chỉ một phía sai.

## 4. Avro, Schema Registry và Serde tùy chỉnh

Nếu upstream producer dùng Confluent Avro, consumer Kafka Streams phải dùng Serde tương ứng. Không thể chỉ đổi content-type sang application/avro rồi kỳ vọng Kafka native deserializer tự hiểu payload.

Ví dụ bean cho generated Avro class:

~~~java
import java.util.Map;

import io.confluent.kafka.streams.serdes.avro.SpecificAvroSerde;
import org.apache.kafka.common.serialization.Serde;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AvroSerdeConfiguration {

    @Bean
    Serde<OrderCreatedAvro> orderCreatedAvroSerde() {
        SpecificAvroSerde<OrderCreatedAvro> serde =
            new SpecificAvroSerde<>();

        String registryUrl = System.getenv("SCHEMA_REGISTRY_URL");
        serde.configure(
            Map.of("schema.registry.url", registryUrl),
            false
        );

        return serde;
    }
}
~~~

Ví dụ này giả định OrderCreatedAvro là class được sinh từ Avro schema và dependency Confluent Serde tương thích với Kafka client trong BOM của ứng dụng. Trong production, kiểm tra biến SCHEMA_REGISTRY_URL, credentials và TLS trước khi khởi tạo Serde.

Nếu dùng Serde<OrderCreatedAvro> bean, binder có thể suy luận theo generic type. Nếu chọn cấu hình Serde bằng class name trên binding, hãy bảo đảm class có thể được khởi tạo và nhận đúng cấu hình registry. Không để username/password hoặc API key trong file cấu hình được commit; lấy chúng từ secret store/environment.

### Schema evolution cũng ảnh hưởng tới restoration

State store có changelog riêng. Nếu Serde dùng cho store thay đổi wire format, record trong changelog cũ vẫn được serialize bằng format trước đó. Một ứng dụng mới có thể đọc input topic thành công nhưng thất bại khi restore store từ changelog.

Khi thay Serde của state store:
- Giữ khả năng đọc dữ liệu changelog cũ nếu có thể.
- Kiểm tra schema history của key và value trong store.
- Test khởi động mới với changelog cũ trong môi trường thử nghiệm.
- Nếu thay đổi phá vỡ, lập kế hoạch tạo store/topic mới hoặc rebuild state từ nguồn gốc.
- Không xóa changelog hoặc local state production chỉ để thử xem lỗi có hết không.

## 5. Native Serde hay Spring MessageConverter?

Spring Cloud Stream Kafka Streams Binder dùng native encoding/decoding mặc định. Nếu producer upstream dùng một format mà Kafka Streams Serde không xử lý được, có thể giao conversion cho Spring Cloud Stream.

Tắt native decoding trên từng input:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        acceptOrders-in-0:
          consumer:
            native-decoding: false
          content-type: application/json
~~~

Tắt native encoding trên output:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        acceptOrders-out-0:
          producer:
            native-encoding: false
          content-type: application/json
~~~

Khi dùng MessageConverter:
- Kiểm tra content-type thực tế của message.
- Đăng ký converter tương ứng.
- Kiểm tra payload type sau conversion.
- Cấu hình từng input/output nếu topology có nhiều binding.
- Không kỳ vọng binder tiếp tục suy luận native Serde cho binding đã tắt native conversion.

Đối với Kafka Streams, nên ưu tiên native Serde khi có thể vì Kafka Streams API cũng cần Serde trong các thao tác bên trong topology. MessageConverter chỉ xử lý ranh giới message của Spring Cloud Stream; nó không tự cung cấp Serde cho groupBy, aggregate, join, Materialized hoặc Processor API.

## 6. Serde bên trong topology và state store

Một lỗi phổ biến là input/output binding đã có Serde nhưng stateful operation bên trong topology vẫn thiếu Serde.

Ví dụ đếm số đơn hàng theo customer key:

~~~java
import java.util.function.Function;

import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.springframework.kafka.support.serializer.JsonSerde;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderCountTopology {

    @Bean
    Function<KStream<String, OrderCreated>, KTable<String, Long>>
    countOrders(Serde<OrderCreated> orderCreatedSerde) {
        return orders -> orders
            .groupByKey(
                Grouped.with(Serdes.String(), orderCreatedSerde)
            )
            .count(
                Materialized.as("orders-by-customer")
                    .withKeySerde(Serdes.String())
                    .withValueSerde(Serdes.Long())
            );
    }

    @Bean
    Serde<OrderCreated> orderCreatedSerde() {
        return new JsonSerde<>(OrderCreated.class);
    }
}
~~~

Trong ví dụ:
- Grouped.with xác định key/value Serde khi nhóm record.
- Materialized.as đặt tên store ổn định.
- withKeySerde và withValueSerde xác định Serde của state store.
- count tạo KTable chứa số lượng theo key.

Tên store cần duy nhất trong topology. Khi nhiều topology cùng chạy trong một application, không dùng trùng store name nếu chúng thuộc các builder khác nhau mà không có chủ đích.

Nếu không truyền Serde ở các API yêu cầu, Kafka Streams có thể ném ConfigException, SerializationException hoặc lỗi liên quan đến Serde khi topology được build hoặc khi record đi vào operation.

## 7. State store được tạo như thế nào?

Kafka Streams có thể tạo state store tự động khi dùng high-level DSL và gọi các operation có state như count, aggregate, reduce, join hoặc Materialized.

Có ba trường hợp thường gặp:

| Cách tạo | Cách đăng ký |
|---|---|
| DSL materialization | Gọi operation stateful và dùng Materialized.as("store-name") |
| Input KTable | Cấu hình materializedAs trên binding KTable nếu cần đặt tên store |
| Processor API | Đăng ký StoreBuilder để topology biết store cần dùng |

### Đặt tên store cho incoming KTable

Với function có một KStream và một KTable input:

~~~java
@Bean
BiFunction<KStream<String, Long>,
           KTable<String, String>,
           KStream<String, Long>> process() {
    // use the table as a lookup/reference stream
}
~~~

Cấu hình tên store cho KTable binding:

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

Tên incoming-store được dùng để materialize dữ liệu của incoming KTable thành named state store. Property này dành cho KTable input; với store được tạo bởi DSL operation, đặt tên bằng Materialized.as.

### Đăng ký custom store trong Processor API

Khi dùng Processor API, tạo StoreBuilder bean để binder đưa store vào StreamsBuilder:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.state.KeyValueStore;
import org.apache.kafka.streams.state.StoreBuilder;
import org.apache.kafka.streams.state.Stores;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class StateStoreConfiguration {

    @Bean
    StoreBuilder<KeyValueStore<String, Long>> customerTotalsStore() {
        return Stores.keyValueStoreBuilder(
            Stores.persistentKeyValueStore("customer-totals"),
            Serdes.String(),
            Serdes.Long()
        );
    }
}
~~~

Processor có thể truy cập store đã đăng ký trong init:

~~~java
@Override
public void init(ProcessorContext context) {
    KeyValueStore<String, Long> totals =
        context.getStateStore("customer-totals");
}
~~~

Tên trong getStateStore phải trùng tên store đã đăng ký. Nếu store không được thêm vào topology hoặc tên sai, processor không thể truy cập store. Với GlobalKTable/global store, cách đăng ký có khác biệt; hãy dùng cơ chế tùy chỉnh StreamsBuilderFactoryBean phù hợp thay vì giả định mọi StoreBuilder bean đều được xử lý giống nhau.

## 8. Changelog topic và cơ chế phục hồi

State store local thường được lưu bằng RocksDB. Để state không mất khi instance bị hỏng, Kafka Streams duy trì changelog topic chứa các thay đổi của store. Changelog thường được compact để giữ trạng thái mới nhất theo key.

Khi task được gán cho instance mới:
1. Kafka Streams kiểm tra local state và checkpoint.
2. Nếu local state chưa tồn tại, restore consumer đọc changelog từ đầu phạm vi cần thiết.
3. Nếu local state còn checkpoint hợp lệ, restore từ offset đã checkpoint.
4. Kafka Streams áp dụng các record changelog vào local store.
5. Khi state đạt yêu cầu, task mới có thể tiếp tục xử lý record.

~~~mermaid
sequenceDiagram
    participant K as Kafka changelog topic
    participant R as Restore consumer
    participant S as Local RocksDB store
    participant T as Stream task
    R->>K: Fetch changelog records
    K-->>R: Key/value updates
    R->>S: Apply updates
    S-->>R: Write completed
    R-->>T: Restore reaches required offset
    T->>T: Start normal processing
~~~

Một task đang restore có thể chưa phục vụ interactive query hoặc chưa chuyển sang trạng thái RUNNING. Đây là giai đoạn bình thường nếu changelog vẫn được đọc và restore progress tiếp tục tăng.

### Những điều cần bảo vệ

- Changelog topics phải tồn tại và broker phải cho phép ứng dụng đọc/ghi.
- application.id phải ổn định giữa các lần restart của cùng một logical processor.
- Internal topic naming và store name cần được quản lý như một phần của topology.
- Changelog retention/cleanup policy phải phù hợp với cơ chế fault tolerance.
- Không xóa changelog topic hoặc đổi application ID tùy tiện khi muốn khôi phục một instance.
- Khi thay Serde của store, phải xác minh ứng dụng mới có thể đọc changelog được ghi bằng Serde cũ.

Nếu changelog bị xóa hoặc không còn dữ liệu cần thiết, local store có thể không phục hồi được từ checkpoint hiện tại. Khi đó cần kế hoạch rebuild từ source topics hoặc bản backup phù hợp; không thể giải quyết bằng cách chỉ tăng retry.

## 9. application.id và state.dir

application.id là định danh của Kafka Streams application. Nó được dùng trong group membership và làm prefix cho các internal changelog/repartition topics. Với Spring Cloud Stream Kafka Streams Binder, nên đặt rõ ID trong production.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: countOrders
    stream:
      kafka:
        streams:
          binder:
            application-id: order-counts-v1
            configuration:
              state.dir: /var/lib/order-stream/state
~~~

Trong ứng dụng có nhiều Kafka Streams processor, đặt application ID riêng cho từng function bằng property dạng spring.cloud.stream.kafka.streams.binder.functions.<function-name>.applicationId. Các replica của cùng processor phải dùng cùng application ID để tham gia cùng logical application.

state.dir là thư mục local chứa state store. Mỗi Kafka Streams instance dùng chung filesystem phải có đường dẫn state riêng. Không để nhiều pod cùng ghi vào một thư mục RocksDB. Trong Kubernetes, mount local persistent volume hoặc writable volume phù hợp, đặt path riêng theo instance/pod và theo dõi dung lượng. Nếu local disk bị mất, Kafka Streams có thể phục hồi từ changelog nhưng thời gian restore có thể tăng đáng kể.

Không đổi application.id chỉ để xóa lỗi state. ID mới có thể tạo consumer group và internal topics mới, khiến ứng dụng bắt đầu một vòng đời state khác. Việc này có thể kéo theo replay dữ liệu, duplicate side effect hoặc state bị dựng lại từ đầu tùy offset/reset policy.

## 10. Standby replicas và phục hồi nhanh

Kafka Streams có thể duy trì standby task để giữ bản sao state store trên instance khác. Khi active task gặp sự cố, một standby đã theo kịp changelog có thể được chuyển thành active, giảm thời gian restore.

Cấu hình ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              num.standby.replicas: 1
~~~

Nếu đặt num.standby.replicas = 1, cần ít nhất hai KafkaStreams instances để có active và standby task. Tổng quát, n standby replicas cần ít nhất n+1 instances. Với một standby, mỗi state store có thể cần thêm khoảng một bản sao dung lượng local state trên các instance. Cân đối disk, network và broker load trước khi bật nhiều standby.

Kafka Streams còn có acceptable.recovery.lag và warmup replicas trong các phiên bản hỗ trợ. Chúng giúp tránh chuyển active task sang instance chưa bắt kịp state nếu vẫn có instance khác đang phục vụ. Giá trị lag phải dựa trên tốc độ restore và workload thực tế; đặt quá thấp có thể làm failover chờ lâu, đặt quá cao có thể cho phép instance chưa đủ mới nhận task.

## 11. State store chưa sẵn sàng và InteractiveQueryService

Ứng dụng có thể đã khởi động nhưng store chưa thể query vì task chưa được assign, đang rebalance hoặc đang restore changelog. Khi gọi InteractiveQueryService quá sớm, có thể nhận InvalidStateStoreException hoặc exception báo KafkaStreams/store chưa sẵn sàng.

Ví dụ truy vấn store:

~~~java
ReadOnlyKeyValueStore<String, Long> store =
    interactiveQueryService.getQueryableStoreType(
        "orders-by-customer",
        QueryableStoreTypes.keyValueStore()
    );
~~~

Store name phải trùng tên đã materialize trong topology. Nếu query trước khi store ready, hãy xử lý trạng thái chưa sẵn sàng như một điều kiện có thể retry trong thời gian startup.

Kafka Streams Binder cung cấp retry cho các lời gọi InteractiveQueryService:

~~~properties
spring.cloud.stream.kafka.streams.binder.stateStoreRetry.maxAttempts=8
spring.cloud.stream.kafka.streams.binder.stateStoreRetry.backoffPeriod=1000
~~~

Giá trị mặc định thường là một lần thử và backoff 1.000 ms. Điều chỉnh số lần và khoảng chờ theo thời gian restore dự kiến.

Cấu hình retry này giúp thử lại thao tác lấy store/host metadata khi KafkaStreams chưa sẵn sàng. Nó không sửa được lỗi Serde, changelog bị thiếu, RocksDB không ghi được hoặc broker không truy cập được. Nếu restore thất bại liên tục, cần xử lý nguyên nhân gốc thay vì tăng số lần retry vô hạn.

### Interactive query trên nhiều instance

Một key có thể thuộc task đang chạy ở instance khác. Nếu ứng dụng expose interactive query qua nhiều instance, cần cấu hình application.server để Kafka Streams có thể xác định host đang sở hữu key.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              application.server: order-stream-0.order-stream:8080
~~~

Trong hệ thống nhiều replica, mỗi instance phải quảng bá địa chỉ riêng có thể truy cập được. API InteractiveQueryService cung cấp metadata host cho key; nếu key thuộc instance khác, request phải được định tuyến đến đúng host hoặc được proxy qua service layer.

## 12. Theo dõi health và tiến độ restoration

Thêm Spring Boot Actuator để dùng Kafka Streams Binder health indicator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Bật binder health:

~~~yaml
management:
  health:
    binders:
      enabled: true
  endpoint:
    health:
      show-details: when-authorized
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Health indicator của Kafka Streams Binder báo trạng thái thread và metadata của active/standby tasks. Các thread state thường thấy gồm:

- CREATED
- RUNNING
- PARTITIONS_REVOKED
- PARTITIONS_ASSIGNED
- PENDING_SHUTDOWN
- DEAD

Binder health là UP khi tất cả Kafka Streams threads được đăng ký ở trạng thái RUNNING. Trong startup/rebalance/restore, trạng thái có thể chưa RUNNING. Xem chi tiết thread, task ID, partition và standby task để phân biệt đang phục hồi với đã chết.

### StateRestoreListener

Kafka Streams cung cấp StateRestoreListener để quan sát restoration:
- onRestoreStart: bắt đầu restore một store partition, có starting/ending offset.
- onBatchRestored: mỗi batch record đã được áp dụng, có batch end offset và số record.
- onRestoreEnd: hoàn tất restore, có tổng số record.
- onRestoreSuspended: restore bị tạm dừng do task được chuyển sang instance khác.

Dùng listener để ghi log/metric về store name, topic partition, số record đã restore và thời gian. Listener được chia sẻ giữa stream threads nên implementation phải thread-safe. Có thể cấu hình listener thông qua Kafka Streams customizer/factory bean integration phù hợp với phiên bản Spring for Apache Kafka đang dùng.

### Metrics cần theo dõi

| Nhóm | Chỉ số | Cách diễn giải |
|---|---|---|
| Stream threads | Thread state, thread count, task count | Thread chết hay đang rebalance? |
| Restoration | Restore records rate, restore duration, remaining lag | Restore có tiến triển không? |
| Changelog | Consumer fetch rate, lag, request errors | Restore consumer có đọc được changelog không? |
| State store | RocksDB size, open files, write/read latency | Store có thiếu disk hoặc bị chậm không? |
| Runtime | CPU, heap, GC, disk I/O, file descriptors | Instance có bị cạn tài nguyên không? |
| Interactive query | Query success, unavailable count, retry count | Store đã sẵn sàng phục vụ chưa? |

Kafka Streams Binder có metrics có thể export qua Micrometer MeterRegistry. Expose Actuator metrics và Prometheus trong management network; tránh công khai endpoint nội bộ.

## 13. Chẩn đoán theo dấu hiệu

| Hiện tượng | Nguyên nhân có thể | Kiểm tra tiếp theo |
|---|---|---|
| SerializationException ở input | Key/value Serde không khớp producer | Xác định key hay value, kiểm tra wire format và schema |
| Chỉ một input của BiFunction lỗi | Serde cấu hình nhầm binding index | Đối chiếu process-in-0 và process-in-1 |
| Input đọc được nhưng aggregate lỗi | Thiếu Serde trong Grouped/Materialized | Cấu hình key/value Serde bên trong DSL |
| Output topic có bytes sai format | Producer Serde không khớp consumer | Kiểm tra producer.keySerde/valueSerde và schema |
| InvalidStateStoreException ngay sau startup | Store chưa restore hoặc task chưa RUNNING | Kiểm tra thread state, restore listener và retry query |
| Restore không tiến triển | Changelog fetch bị lỗi, ACL hoặc broker/network | Kiểm tra restore consumer, changelog topic, authorization |
| RocksDB open/write error | Disk đầy, permission sai, lock hoặc filesystem không phù hợp | Kiểm tra state.dir, volume, disk I/O và ownership |
| Restore lặp đi lặp lại sau mỗi restart | Local state không giữ được hoặc checkpoint không hữu ích | Kiểm tra volume, state.dir và shutdown behavior |
| Store restore báo lỗi deserialization | Store/changelog được ghi bằng Serde/schema khác | Kiểm tra schema history và version của state-store Serde |
| Thread chuyển sang DEAD | Exception không được xử lý hoặc lỗi nghiêm trọng | Đọc exception gốc, thread state và uncaught handler |
| Task rebalance liên tục | Instance churn, session timeout, partition movement | Kiểm tra deploy, network, heartbeat và instance stability |
| Consumer input bình thường nhưng query không có store | Store chưa materialize hoặc tên query sai | Kiểm tra Materialized.as, materializedAs, store name |
| Standby không được tạo | Thiếu instance hoặc standby replica config | Kiểm tra num.standby.replicas và số replica |
| DLQ không xuất hiện | Chưa bật sendToDlq, topic chưa tồn tại hoặc ACL thiếu | Kiểm tra handler, DLQ name, partition và permissions |

## 14. Xử lý poison pill và lỗi deserialization

Kafka Streams Binder mặc định dùng logAndFail cho deserialization exception. Có thể chọn handler phù hợp:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            deserialization-exception-handler: sendToDlq
~~~

Các lựa chọn được binder hỗ trợ gồm:
- logAndFail: log lỗi và dừng xử lý theo handler.
- logAndContinue: log lỗi rồi tiếp tục record tiếp theo.
- skipAndContinue: bỏ qua record lỗi và tiếp tục.
- sendToDlq: gửi record không deserialize được sang dead-letter topic.

Nếu có nhiều input binding, có thể cấu hình handler ở từng binding để chỉ áp dụng cho input cụ thể:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            process-in-0:
              consumer:
                deserialization-exception-handler: sendToDlq
            process-in-1:
              consumer:
                deserialization-exception-handler: skipAndContinue
~~~

Handler ở input binding có độ ưu tiên cao hơn handler ở binder level. Nếu dùng DlqDestinationResolver, ứng dụng phải bảo đảm các DLQ topic được tạo trước vì binder không thể tự suy ra tất cả tên topic mà resolver có thể trả về. Nếu dùng static dlqName, khai báo rõ topic và quyền publish.

Mặc định DLQ giữ partition tương ứng với record gốc; DLQ topic cần đủ partition. Poison pill do input Serde khác với lỗi restore state store. Gửi một record input lỗi vào DLQ không khắc phục được changelog đã được ghi bằng Serde không tương thích.

## 15. Quy trình điều tra và khôi phục

Thực hiện theo trình tự sau để giữ nguyên bằng chứng và tránh làm mất state:

1. Ghi lại application.id, function name, input binding, store name và phiên bản ứng dụng.
2. Xác định lỗi xuất hiện ở input deserialization, topology operation, output serialization, query hay restoration.
3. Đọc exception đầu tiên trong log; không chỉ đọc exception cuối cùng sau nhiều lần retry.
4. Kiểm tra Serde key và value của từng binding.
5. Kiểm tra Serde trong Grouped, Materialized, join hoặc Processor API.
6. Kiểm tra store đã được tạo/đăng ký và tên store có khớp với query không.
7. Kiểm tra binder health, thread state, task assignment và restore progress.
8. Kiểm tra changelog topic tồn tại, có partition đúng và application có ACL đọc/ghi.
9. Kiểm tra state.dir, quyền filesystem, dung lượng disk, RocksDB files và local volume.
10. Kiểm tra schema của changelog có tương thích với Serde hiện tại không.
11. Chờ restore tiến triển và chỉ mở query khi store sẵn sàng.
12. Nếu cần rebuild state, lập kế hoạch riêng cho source retention, offsets, side effects và duplicate trước khi thao tác.

### Khi nào được xóa local state?

Xóa local state chỉ nên là một bước khôi phục có kiểm soát trong môi trường phù hợp. Khi xóa local state, Kafka Streams có thể phải replay changelog từ đầu phạm vi cần thiết. Nếu changelog vẫn còn đầy đủ và Serde đúng, đây có thể là cách rebuild local copy. Nếu changelog thiếu hoặc không đọc được, xóa local state sẽ làm mất checkpoint hữu ích và khiến quá trình phục hồi khó hơn.

Trước khi xóa:
- Xác nhận changelog topic và partition còn tồn tại.
- Xác nhận consumer có quyền đọc changelog.
- Xác nhận Serde hiện tại đọc được bytes cũ.
- Ước lượng thời gian restore và dung lượng disk.
- Xác nhận ứng dụng có thể chịu được thời gian không phục vụ query.
- Có snapshot/backup hoặc phương án rebuild từ source topic nếu cần.

Không xóa changelog topic trong production để chữa một lỗi local RocksDB. Không đổi application ID để reset khi chưa có kế hoạch rõ về consumer group, offsets, replay và duplicate side effects.

## 16. Bài thực hành: khôi phục store orders-by-customer

Tình huống: function countOrders đọc topic orders, materialize store orders-by-customer và expose query để lấy số đơn hàng theo customer. Sau một lần rollout, thread không chuyển sang RUNNING và query trả InvalidStateStoreException.

1. Xác nhận function countOrders có chữ ký Function<KStream<String, OrderCreated>, KTable<String, Long>>.
2. Kiểm tra String key Serde và OrderCreated value Serde.
3. Khai báo Serde<OrderCreated> bean hoặc cấu hình consumer.keySerde/valueSerde theo binding.
4. Kiểm tra Serde String và Long trong Materialized store.
5. Xác nhận store name orders-by-customer giống tên trong InteractiveQueryService.
6. Xác nhận application.id không bị thay đổi ngoài kế hoạch.
7. Kiểm tra changelog topic theo application ID và store name.
8. Kiểm tra quyền read/write internal topics của principal.
9. Kiểm tra state.dir có thể ghi và disk còn đủ chỗ.
10. Bật binder health và xem thread state/active task.
11. Theo dõi restore start, batch restored và restore end.
12. Chờ store ready rồi gọi interactive query.
13. Nếu query còn thất bại trong startup, cấu hình retry có giới hạn cho InteractiveQueryService.
14. Chạy thử restart instance để xác nhận local state được giữ hoặc restore từ changelog.
15. Mô phỏng instance mới không có local state trong môi trường test và xác nhận changelog replay hoàn tất.
16. Ghi lại thời gian restore, số record, lag, lỗi và điều kiện readiness.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Input Serde | Key/value deserialize đúng với wire format |
| Output Serde | Output key/value được serialize đúng |
| DSL Serde | Grouped/Materialized/Join có Serde phù hợp |
| Store registration | Store được tạo tự động hoặc đăng ký bằng StoreBuilder |
| Store naming | Materialized name và query name khớp |
| Application ID | Ổn định giữa các replica và lần restart |
| Changelog | Topic/partition tồn tại, ACL và replication đúng |
| Local state | state.dir ghi được, đủ disk và không dùng chung sai cách |
| Restore | Restore progress tăng và kết thúc |
| Health | Stream threads chuyển sang RUNNING |
| Query readiness | Interactive query chỉ chạy khi store sẵn sàng |
| Recovery | Instance mới phục hồi được từ changelog |
| Error handling | Poison pill được log/skip/DLQ theo policy |
| Operations | Có dashboard, alert và runbook restore |

## Kết luận

Kafka Streams thiếu Serde, state store chưa sẵn sàng và restore lỗi là ba vấn đề có liên quan nhưng cần chẩn đoán riêng. Serde phải khớp ở cả input, output và các stateful operation bên trong topology. Store cần được materialize hoặc đăng ký đúng, còn Kafka Streams phục hồi local state bằng cách đọc changelog trước khi task tiếp tục xử lý.

Hãy giữ application.id ổn định, đặt state.dir riêng cho mỗi instance, bảo vệ changelog topics và theo dõi restore progress. Dùng binder health, StateRestoreListener, Kafka Streams metrics và retry có giới hạn cho interactive query. Khi thay đổi Serde của state store, kiểm thử với changelog lịch sử và có kế hoạch rebuild rõ ràng. Không xóa state hoặc changelog tùy tiện vì hành động đó có thể biến một lỗi cục bộ thành một lần phục hồi toàn bộ state.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0.4 – Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html)
- [Spring Cloud Stream – State Store](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/state-store.html)
- [Spring Cloud Stream – Interactive Queries](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/interactive-queries.html)
- [Spring Cloud Stream – Kafka Streams Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/health-indicator.html)
- [Spring Cloud Stream – Kafka Streams Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Apache Kafka 4.2 – Configuring Kafka Streams](https://kafka.apache.org/42/streams/developer-guide/config-streams/)
- [Apache Kafka 4.2 – Running Streams Applications and State Restoration](https://kafka.apache.org/42/streams/developer-guide/running-app/)
- [Apache Kafka 4.4 – StateRestoreListener API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/processor/StateRestoreListener.html)
- [Spring for Apache Kafka – JSON Serde](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)

