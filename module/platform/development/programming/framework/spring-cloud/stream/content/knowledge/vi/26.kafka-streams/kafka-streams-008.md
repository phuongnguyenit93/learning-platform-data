# Suy luận Serde và cấu hình keySerde, valueSerde

Kafka lưu record dưới dạng byte. Khi Kafka Streams đọc record, nó cần chuyển byte của key và value thành kiểu Java để xử lý; khi ghi kết quả, nó phải chuyển các kiểu Java đó trở lại byte. Kafka Streams dùng Serde (serializer/deserializer) để thực hiện hai chiều này. Spring Cloud Stream Kafka Streams Binder có thể suy luận Serde từ kiểu generic trong chữ ký Function, Consumer, BiFunction hoặc StreamListener, nhưng ứng dụng vẫn cần hiểu thứ tự ưu tiên, cách cấu hình keySerde/valueSerde và những trường hợp phải khai báo rõ.

Suy luận Serde giúp giảm cấu hình lặp lại khi kiểu dữ liệu đã rõ. Nó không thể tự đoán chính xác mọi định dạng wire, đặc biệt khi dùng Avro, Protobuf, schema riêng, kiểu generic bị xóa thông tin hoặc nhiều topic có hợp đồng khác nhau. Chọn đúng Serde là điều kiện để đọc được dữ liệu cũ, ghi được dữ liệu mới, giữ đúng key cho partitioning và tránh làm hỏng state store.

## 1. Serde là gì?

Serde<T> là một cặp gồm:

- Serializer<T>: chuyển object Java thành byte trước khi ghi vào Kafka.
- Deserializer<T>: chuyển byte đọc từ Kafka thành object Java.

Ví dụ, Serdes.String() cung cấp serializer và deserializer cho chuỗi. Serdes.Long() làm tương tự với số nguyên dài. Spring Kafka cung cấp JsonSerde<T> để serialize/deserialize object theo JSON.

Một record Kafka có hai phần dữ liệu chính:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Key | Định danh record, thường dùng để chọn partition và gom nhóm | ORD-1001 |
| Value | Nội dung nghiệp vụ | OrderCreated |

Key và value có thể dùng hai Serde khác nhau. Trong nhiều hệ thống, key là String hoặc UUID, còn value là JSON, Avro hay Protobuf. Không nên mặc định cùng một Serde cho cả hai.

## 2. Vì sao Kafka Streams cần Serde?

Kafka broker không lưu object Java. Producer gửi byte và consumer nhận byte. Kafka Streams cần biết cách chuyển đổi byte đó ở ranh giới của topology:

~~~text
Kafka topic
   |
   | bytes(key, value)
   v
Deserializer / Serde
   |
   | KStream<K, V>
   v
Kafka Streams DSL / Processor API
   |
   | KStream<K2, V2>
   v
Serializer / Serde
   |
   | bytes(key, value)
   v
Kafka output topic
~~~

Nếu key Serde không tương thích với byte đã được producer ghi, consumer có thể không đọc được key hoặc giải mã thành giá trị sai. Nếu value Serde không tương thích, record có thể gây deserialization exception trước khi business logic chạy. Ở chiều ghi, serializer không đúng định dạng sẽ tạo record mà downstream consumer không thể đọc.

Serde còn ảnh hưởng đến:

- Partitioning: Kafka partitioner thường dựa trên byte của record key.
- Grouping và join: các key phải được giải mã và so sánh theo cùng semantics.
- Compaction: Kafka log compaction giữ trạng thái mới nhất theo key bytes.
- State store và changelog: Kafka Streams cần serialize key/value của dữ liệu trạng thái.
- Tombstone: value null trên compacted topic có thể biểu thị xóa một key trong KTable.

## 3. Binder suy luận Serde từ chữ ký function

Với functional model, Kafka Streams Binder đọc kiểu generic của KStream, KTable hoặc GlobalKTable trong chữ ký function. Ví dụ:

~~~java
@Bean
Function<KStream<String, OrderCreated>,
         KStream<String, OrderSummary>> summarizeOrders() {

    return orders -> orders
        .mapValues(event -> new OrderSummary(
            event.orderId(),
            event.total()
        ));
}
~~~

Chữ ký cho binder biết:

- Input key có kiểu String.
- Input value có kiểu OrderCreated.
- Output key có kiểu String.
- Output value có kiểu OrderSummary.

Binder có thể dùng thông tin kiểu này để tìm Serde phù hợp cho từng binding. Binding mặc định được tạo theo tên function:

- summarizeOrders-in-0: input.
- summarizeOrders-out-0: output.

Khai báo kiểu generic cụ thể giúp binder có thêm thông tin. Nếu dùng KStream<?, ?>, raw type hoặc generic type không thể phân giải ở runtime, binder có thể không biết key/value cần Serde nào. Khi đó cần cấu hình tường minh.

## 4. Thứ tự suy luận Serde ở input

Với inbound deserialization, Kafka Streams Binder áp dụng các bước sau:

1. Nếu ứng dụng có bean kiểu Serde<T> và kiểu T khớp với kiểu key/value trong chữ ký function, binder có thể dùng bean đó.
2. Binder kiểm tra các kiểu được Kafka Streams hỗ trợ sẵn: Integer, Long, Short, Double, Float, byte[], UUID và String.
3. Binder xem các default Serde trong Kafka Streams configuration có khớp kiểu đang cần hay không.
4. Nếu kiểu là object phù hợp JSON, binder có thể dùng JsonSerde của Spring Kafka.
5. Nếu không thể suy luận phù hợp, ứng dụng phải cấu hình Serde ở cấp binding hoặc cấu hình mặc định.

Một keySerde hoặc valueSerde khai báo trực tiếp ở cấp input binding có độ ưu tiên cao hơn suy luận. Khi có cấu hình này, binder không tiếp tục tự suy luận cho phần tương ứng.

Ví dụ với KStream<String, OrderCreated>, binder thường có thể chọn StringSerde cho key và JsonSerde<OrderCreated> cho value. Tuy nhiên, nếu upstream producer đang gửi Avro bytes thì JsonSerde không thể đọc chúng; phải cấu hình Avro Serde phù hợp hoặc dùng message conversion tương thích.

## 5. Suy luận Serde ở output

Outbound serialization cũng dựa trên kiểu key/value của output KStream. Binder tìm Serde tương ứng với kiểu output. Với các kiểu Kafka hỗ trợ sẵn như String, Long, UUID hoặc byte[], binder có thể dùng Serde phù hợp; với object JSON-friendly, binder có thể dùng JsonSerde.

Nếu không suy luận được key Serde, ứng dụng cần cấu hình rõ. Nếu value Serde không thể suy luận hoặc kiểu dữ liệu dùng schema format đặc thù, hãy khai báo valueSerde ở output binding.

Ví dụ:

~~~java
@Bean
Function<KStream<String, OrderCreated>,
         KStream<String, OrderSummary>> summarizeOrders() {
    return input -> input.mapValues(event ->
        new OrderSummary(event.orderId(), event.total()));
}
~~~

Input và output có value type khác nhau. Input cần Serde cho OrderCreated; output cần Serde cho OrderSummary. Không lấy cấu hình của input rồi mặc định áp dụng cho output nếu kiểu hoặc schema đã thay đổi.

## 6. Khai báo keySerde và valueSerde theo từng input binding

Khi binder không thể suy luận, hoặc cần dùng schema cụ thể, cấu hình Serde ngay trên input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
          group: order-processor
      kafka:
        streams:
          bindings:
            processOrders-in-0:
              consumer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: com.example.kafka.OrderEventSerde
~~~

Prefix chính xác cho Kafka Streams Binder là spring.cloud.stream.kafka.streams.bindings, không phải prefix của regular Kafka message-channel binder spring.cloud.stream.kafka.bindings.

Trong ví dụ:

- consumer.key-serde giải mã key của input topic.
- consumer.value-serde giải mã value của input topic.
- OrderEventSerde là Serde ứng dụng cung cấp, có thể là class có constructor phù hợp hoặc bean được binder nhận diện theo kiểu.

Nếu có nhiều input, mỗi binding có thể có schema khác nhau. Ví dụ một BiFunction nhận KStream và KTable:

~~~java
@Bean
BiFunction<KStream<String, OrderEvent>,
           KTable<String, Customer>,
           KStream<String, EnrichedOrder>> enrichOrders() {
    return (orders, customers) ->
        orders.leftJoin(customers,
            (order, customer) -> new EnrichedOrder(order, customer));
}
~~~

Cấu hình từng input:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            enrichOrders-in-0:
              consumer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: com.example.kafka.OrderEventSerde
            enrichOrders-in-1:
              consumer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: com.example.kafka.CustomerSerde
~~~

Không gán một valueSerde chung cho nhiều input nếu các topic chứa schema khác nhau. Binding-level Serde giúp từng input có hợp đồng giải mã riêng.

## 7. Khai báo Serde theo từng output binding

Output binding có cấu hình tương tự nhưng dùng nhánh producer:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            enrichOrders-out-0:
              producer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: com.example.kafka.EnrichedOrderSerde
~~~

Khi function branch ra nhiều output KStream[], mỗi output có thể ghi sang topic và schema khác nhau. Hãy cấu hình Serde riêng cho từng output nếu binder không thể suy luận:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            routeEvents-out-0:
              producer:
                value-serde: com.example.kafka.OrderCreatedSerde
            routeEvents-out-1:
              producer:
                value-serde: com.example.kafka.OrderCancelledSerde
~~~

Không giả định các output branch đều có cùng value type hoặc cùng schema chỉ vì chúng được tạo từ một function.

## 8. Dùng Serde bean có kiểu generic rõ ràng

Nếu muốn cấu hình Serde bằng Java, có thể đăng ký bean có generic type cụ thể:

~~~java
import org.apache.kafka.common.serialization.Serde;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.support.serializer.JsonSerde;

@Bean
Serde<OrderCreated> orderCreatedSerde() {
    return new JsonSerde<>(OrderCreated.class);
}
~~~

Khi function có KStream<String, OrderCreated>, binder có thể nhận ra bean Serde<OrderCreated> và dùng cho value tương ứng. Generic type trong kiểu trả về của bean là thông tin quan trọng; một bean chỉ khai báo raw Serde làm giảm khả năng suy luận theo kiểu.

Nếu có nhiều bean Serde cùng kiểu, cần tránh để binder phải chọn một cách mơ hồ. Có thể khai báo Serde trực tiếp trên binding để xác định rõ lựa chọn, hoặc tổ chức bean/configuration sao cho mỗi kiểu dữ liệu có một Serde phù hợp.

Với custom Serde, kiểm tra:

- Serializer và deserializer dùng cùng wire format.
- Cấu hình schema registry hoặc endpoint cần thiết đã được truyền vào Serde.
- Serializer có xử lý đúng null/tombstone nếu nghiệp vụ cần.
- Serde được đóng tài nguyên đúng cách nếu nó giữ connection hoặc client.
- Cả producer lẫn consumer tương ứng dùng cấu hình tương thích.

## 9. Cấu hình default Serde ở cấp binder

Nếu nhiều binding trong ứng dụng dùng cùng kiểu key/value phổ biến, có thể cấu hình default Serde trong Kafka Streams configuration:

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

Các thuộc tính default.key.serde và default.value.serde là Kafka Streams configuration, nên chúng nằm dưới spring.cloud.stream.kafka.streams.binder.configuration. Chúng áp dụng ở phạm vi binder/application, vì vậy chỉ dùng khi đó thật sự là mặc định chung phù hợp.

Khi một input hoặc output cần schema khác, khai báo key-serde/value-serde ở cấp binding để ghi đè mặc định. Không đặt một default JSON hoặc String Serde toàn cục rồi mong nó tự giải mã mọi topic có schema khác nhau.

## 10. Sự khác nhau giữa Serde và Spring MessageConverter

Kafka Streams Binder hỗ trợ hai đường chuyển đổi dữ liệu ở ranh giới processor:

| Cách | Thành phần thực hiện | Khi phù hợp |
|---|---|---|
| Native Kafka Serde | Kafka/Kafka Streams | Cần native serialization, key/value rõ kiểu, Avro/JSON/custom Serde |
| Spring Cloud Stream MessageConverter | Framework chuyển đổi Message theo content type | Upstream producer đã dùng định dạng cần converter tương ứng |

Với Kafka Streams Binder hiện hành, inbound key luôn được giải mã bằng native Serde. Inbound value mặc định cũng được Kafka giải mã native. Nếu muốn framework xử lý value bằng message conversion, phải tắt native decoding trên từng input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          content-type: application/json
          consumer:
            native-decoding: false
~~~

Khi đó framework dùng content type và MessageConverter phù hợp để chuyển value. Với nhiều input, cấu hình native-decoding: false cho từng input cần chuyển đổi bằng framework.

Ở chiều output, native encoding mặc định được dùng. Nếu muốn Spring Cloud Stream MessageConverter chuyển đổi outbound value, đặt:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-out-0:
          content-type: application/json
          producer:
            native-encoding: false
~~~

Khi native decoding/encoding bị tắt, binder không thực hiện Serde inference theo cơ chế native cho binding đó. Ứng dụng phải cấu hình content type và converter tương ứng. Không cấu hình lẫn lộn hai cơ chế mà không xác định rõ thành phần nào chịu trách nhiệm serialize/deserialize byte.

## 11. Ví dụ JSON Serde cho POJO

Giả sử topic orders.events chứa JSON của OrderCreated. Function khai báo kiểu cụ thể:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    long total
) {}

public record OrderSummary(
    String orderId,
    long total
) {}

@Bean
Function<KStream<String, OrderCreated>,
         KStream<String, OrderSummary>> summarizeOrders() {
    return orders -> orders.mapValues(event ->
        new OrderSummary(event.orderId(), event.total()));
}
~~~

Với JSON-friendly POJO, binder có thể dùng JsonSerde của Spring Kafka nếu không có Serde bean phù hợp hơn và không có cấu hình binding-level override. Cấu hình topic và group:

~~~yaml
spring:
  cloud:
    function:
      definition: summarizeOrders
    stream:
      bindings:
        summarizeOrders-in-0:
          destination: orders.events
          group: order-summary
        summarizeOrders-out-0:
          destination: orders.summary
~~~

JSON Serde phải có đủ thông tin để deserialize đúng kiểu. Nếu producer và consumer không dùng cùng type header convention, hoặc upstream gửi JSON thuần không có type header phù hợp, cần cấu hình kiểu đích cụ thể bằng Serde bean hoặc một deserializer phù hợp. Không giả định mọi JSON document đều tự động trở thành đúng POJO chỉ vì function signature có kiểu đó.

## 12. Ví dụ Avro Serde và Schema Registry

Với Avro, producer thường ghi payload theo wire format do serializer của Schema Registry quy định. Consumer cần Serde tương ứng, chẳng hạn SpecificAvroSerde cho generated SpecificRecord:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              schema.registry.url: http://schema-registry:8081
          bindings:
            processOrders-in-0:
              consumer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: io.confluent.kafka.streams.serdes.avro.SpecificAvroSerde
            processOrders-out-0:
              producer:
                key-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
                value-serde: io.confluent.kafka.streams.serdes.avro.SpecificAvroSerde
~~~

Ví dụ này giả định dependency của Confluent Serdes đã có trong ứng dụng và các schema Avro/generated class tương ứng đã được tạo. schema.registry.url là cấu hình cho Serde; nếu môi trường dùng authentication hoặc subject naming strategy riêng, hãy cấu hình đầy đủ theo chính sách Schema Registry.

Với Protobuf hoặc format khác, dùng Serde của hệ sinh thái tương ứng. Điều quan trọng là consumer phải đọc đúng wire format do producer đã ghi; class Java tương tự nhau không có nghĩa byte encoding tương thích.

## 13. Serde ở ranh giới binding và Serde trong DSL

Binder suy luận hoặc cấu hình Serde cho inbound/outbound binding. Những Serde này giải quyết việc đọc từ topic đầu vào và ghi ra topic đầu ra.

Trong business logic, một số Kafka Streams DSL API cũng yêu cầu Serde riêng. Binder không thể suy luận mọi Serde được dùng bên trong topology. Ứng dụng phải truyền chúng khi gọi các API như:

- Consumed.with(keySerde, valueSerde).
- Produced.with(keySerde, valueSerde).
- Grouped.with(keySerde, valueSerde).
- Joined.with(keySerde, leftValueSerde, rightValueSerde).
- Repartitioned.with(keySerde, valueSerde).
- Materialized.with(keySerde, valueSerde).

Ví dụ group theo key và đếm số sự kiện:

~~~java
@Bean
Function<KStream<String, OrderCreated>, KTable<String, Long>> countOrders(
        Serde<OrderCreated> orderCreatedSerde) {

    return orders -> orders
        .groupByKey(Grouped.with(
            Serdes.String(),
            orderCreatedSerde
        ))
        .count(Materialized.as("order-counts"));
}
~~~

Grouped.with cho Kafka Streams biết Serde cần dùng khi nhóm và repartition. Nếu topology có join, repartition, aggregate hoặc state store, hãy kiểm tra Serde mà DSL operation yêu cầu. Serde ở binding không tự động thay thế mọi Serde tường minh trong các operator nội bộ.

## 14. Serde cho state store và changelog

Kafka Streams tạo state store khi topology dùng các phép toán stateful như count, aggregate, reduce, join hoặc materialize. State store có key/value Serde để ghi dữ liệu cục bộ và changelog topic.

Có thể khai báo Serde trên Materialized:

~~~java
Materialized.<String, Long, KeyValueStore<Bytes, byte[]>>as("order-counts")
    .withKeySerde(Serdes.String())
    .withValueSerde(Serdes.Long());
~~~

Nếu binding nhận một KTable và muốn materialize nó thành named state store, Kafka Streams Binder còn có thuộc tính materializedAs trên consumer binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            processOrders-in-1:
              consumer:
                materialized-as: customer-store
~~~

materializedAs đặt tên store cho incoming KTable binding; nó không tự thay thế việc chọn Serde đúng cho key/value của store. Nếu dùng Processor API và tự tạo StoreBuilder, cần truyền Serde cho store builder theo đúng kiểu dữ liệu.

Khi đổi Serde của state store/changelog, cần đánh giá khả năng khôi phục state cũ. Nếu byte format mới không đọc được changelog cũ, ứng dụng có thể cần đổi tên store/application ID hoặc có kế hoạch reset/rebuild state có kiểm soát. Không đổi Serde trong production mà không kiểm tra dữ liệu state hiện hữu.

## 15. KeySerde, partitioning và compaction

Kafka partitioner thường chọn partition dựa trên serialized key bytes. Hai producer có thể cùng tạo một object Java CustomerKey nhưng nếu Serde khác nhau thì byte key khác nhau; kết quả có thể là partition khác nhau. Khi đó, các event của cùng customer có thể bị phân tán, làm sai kỳ vọng ordering/grouping.

Key Serde còn quan trọng với log compaction. Kafka xác định record cùng key dựa trên serialized key bytes. Nếu producer đổi cách encode key mà không có migration, cùng một customer có thể tồn tại dưới hai key bytes khác nhau và compaction không coi đó là cùng một key.

Nguyên tắc:

- Chọn một key schema và encoding ổn định.
- Dùng cùng key Serde trên mọi producer/consumer tham gia một luồng.
- Không thay đổi cách normalize/case/format key giữa các phiên bản.
- Nếu cần đổi key format, thiết kế migration hoặc versioned topic.
- Kiểm tra partition thực tế khi đổi Serde, partition count hoặc partitioner.

## 16. Tombstone và null value

Trong compacted topic, record có key và value null thường là tombstone để yêu cầu Kafka xóa trạng thái của key đó trong quá trình compaction. Với KTable, tombstone có ý nghĩa xóa row tương ứng.

Ví dụ:

~~~text
key = "customer-100"
value = {"name":"An","tier":"GOLD"}

key = "customer-100"
value = null
~~~

Record thứ hai là tín hiệu xóa customer-100 khỏi bảng trạng thái. Value Serde và business logic phải cho phép xử lý null đúng cách. Không coi mọi null value là message lỗi hoặc cố deserialize null thành POJO. Nếu topic không dùng tombstone semantics, hãy định nghĩa rõ null có ý nghĩa gì trong hợp đồng event.

## 17. Windowed key và Serde chuyên biệt

Khi topology dùng windowing, key trong một số state store hoặc output có thể là Windowed<K> thay vì chỉ K. Khi đó, Serdes.String() đơn thuần không đủ cho windowed key. Kafka Streams cung cấp Serde chuyên biệt cho time window và session window, ví dụ TimeWindowedSerde hoặc SessionWindowedSerde.

Chọn đúng loại Serde theo kiểu window đang dùng. Khi ghi windowed key ra topic, consumer downstream cũng phải hiểu wire format đó hoặc chuyển đổi sang key nghiệp vụ thông thường trước khi publish. Không để Windowed<K> lọt vào hợp đồng output mà downstream chỉ mong đợi K.

## 18. Xử lý lỗi deserialization

Nếu byte trong topic không khớp Serde, Kafka Streams có thể phát sinh deserialization exception trước khi function nhận được record. Binder hỗ trợ các chiến lược xử lý:

- logAndFail: ghi log và dừng xử lý; đây là mặc định của Kafka Streams.
- logAndContinue: ghi log và bỏ qua record lỗi để tiếp tục.
- sendToDlq: gửi record lỗi đến dead-letter topic.

Có thể cấu hình ở cấp binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            deserialization-exception-handler: sendToDlq
~~~

Hoặc cấu hình riêng cho từng input binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            processOrders-in-0:
              consumer:
                deserialization-exception-handler: sendToDlq
~~~

Binding-level handler có độ ưu tiên cao hơn binder-level handler. Nếu dùng sendToDlq, cần tạo và cấu hình DLQ topic phù hợp. Mặc định record lỗi được gửi đến partition tương ứng với partition gốc, vì vậy DLQ cần đủ partition; nếu đổi chiến lược partition, cần cung cấp DlqPartitionFunction.

Không dùng logAndContinue một cách máy móc cho dữ liệu tài chính hoặc event không thể mất. Bỏ qua record có thể làm sai trạng thái downstream. Với poison pill, DLQ thường giúp giữ record để điều tra và replay sau khi sửa schema hoặc Serde.

## 19. Những lỗi cấu hình Serde thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| SerializationException khi ghi output | Output valueSerde không khớp kiểu object | Kiểm tra generic output và producer Serde |
| DeserializationException khi đọc input | Topic dùng wire format khác Serde cấu hình | Kiểm tra raw bytes, producer serializer và schema registry |
| Key đọc thành byte[] hoặc kiểu không mong muốn | Không có key Serde phù hợp hoặc generic type quá rộng | Khai báo consumer.keySerde |
| JSON deserialize sai class | Thiếu type mapping/header hoặc dùng target type không đúng | Dùng Serde bean có kiểu cụ thể hoặc custom deserializer |
| Avro schema không được tìm thấy | Registry URL/authentication/subject strategy sai | Kiểm tra cấu hình Schema Registry và schema ID |
| Join không khớp dù key nhìn giống nhau | Key bytes hoặc cách normalize khác nhau | So sánh serialized key và Serde ở hai input |
| State store không khôi phục sau deploy | Changelog byte format không tương thích Serde mới | Kiểm tra state store, changelog và migration plan |
| Branch output lỗi ở một topic | Nhiều output có schema khác nhau nhưng dùng chung Serde | Cấu hình Serde riêng cho từng output binding |

## 20. Kiểm thử Serde

Nên kiểm tra cả round-trip và tương thích với dữ liệu thực:

1. Serialize một key/value mẫu, sau đó deserialize và so sánh object.
2. Kiểm tra JSON/Avro/Protobuf bytes do producer hiện tại tạo ra có được consumer đọc đúng.
3. Kiểm tra key Serde ở tất cả producer tạo cùng byte cho cùng business key.
4. Kiểm tra null value/tombstone nếu topic compacted hoặc binding dùng KTable.
5. Kiểm tra record cũ từ schema version trước khi triển khai Serde mới.
6. Kiểm tra state store/changelog có thể khôi phục sau restart.
7. Gửi một record có wire format sai và xác nhận deserialization exception handler hoạt động.
8. Kiểm tra từng input và output binding của function nhiều input/branching.
9. Integration test với Kafka thật hoặc Testcontainers; Test Binder không thay thế việc kiểm tra serializer/deserializer và raw record bytes trên broker.

Ví dụ kiểm tra round-trip đơn giản:

~~~java
@Test
void orderSerdeRoundTrip() {
    Serde<OrderCreated> serde = new JsonSerde<>(OrderCreated.class);
    OrderCreated original =
        new OrderCreated("evt-1", "ORD-1001", 250000L);

    byte[] bytes = serde.serializer().serialize("orders.events", original);
    OrderCreated decoded =
        serde.deserializer().deserialize("orders.events", bytes);

    assertThat(decoded).isEqualTo(original);
}
~~~

Đóng Serde sau khi kiểm thử nếu test tự tạo instance và Serde có tài nguyên cần giải phóng. Trong integration test, xác minh cả key/value Serde được binder dùng ở đúng binding, không chỉ test riêng class Serde.

## 21. Checklist cấu hình

- [ ] Chữ ký function dùng kiểu generic cụ thể cho key/value của từng KStream/KTable.
- [ ] Đã hiểu inbound key luôn dùng native Serde và inbound value mặc định dùng native deserialization.
- [ ] Đã xác định Serde được suy luận từ bean, kiểu Kafka built-in, default config hay JsonSerde.
- [ ] Đã cấu hình binding-level consumer.keySerde/consumer.valueSerde khi cần override input inference.
- [ ] Đã cấu hình binding-level producer.keySerde/producer.valueSerde khi output cần Serde riêng.
- [ ] Default key/value Serde ở binder phù hợp với phạm vi toàn application.
- [ ] Đã phân biệt Kafka Streams Binder prefix với regular Kafka Binder prefix.
- [ ] Native decoding/encoding và Spring MessageConverter được chọn rõ ràng.
- [ ] DSL operations như Grouped, Joined, Materialized có Serde phù hợp.
- [ ] State store, changelog, tombstone và windowed key có Serde tương thích.
- [ ] Key encoding ổn định trên mọi producer để giữ partitioning và compaction semantics.
- [ ] Deserialization exception handler và DLQ có chính sách phù hợp.
- [ ] Đã kiểm thử round-trip, dữ liệu cũ, schema registry và broker thật.

Serde quyết định cách Kafka Streams đọc và ghi byte cho key/value. Spring Cloud Stream Kafka Streams Binder có thể suy luận nhiều trường hợp từ chữ ký function, bean Serde và các kiểu Kafka phổ biến; khi cần kiểm soát chính xác, cấu hình keySerde và valueSerde theo từng binding hoặc default ở cấp binder. Hãy phân biệt Serde ở ranh giới binding với Serde mà DSL/state store yêu cầu, đồng thời giữ key encoding và schema tương thích giữa producer, processor và consumer.

## Tài liệu tham khảo

- [Spring Cloud Stream — Kafka Streams Binder: Record Serialization and Deserialization](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html#record-serialization-and-deserialization)
- [Spring Cloud Stream — Kafka Streams Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring for Apache Kafka — Serialization, Deserialization and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Apache Kafka Streams — Data Types and Serdes](https://kafka.apache.org/documentation/streams/developer-guide/datatypes.html)
