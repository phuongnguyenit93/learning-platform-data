# Tích hợp Avro MessageConverter hoặc native Serde theo binder

Apache Avro là định dạng dữ liệu nhị phân có schema. Trong một hệ thống Spring Cloud Stream, Avro giúp producer và consumer trao đổi dữ liệu có cấu trúc, giảm kích thước payload và quản lý thay đổi hợp đồng theo phiên bản. Tuy nhiên, Avro chỉ phát huy tác dụng khi hai phía thống nhất cách serialize, cách tìm schema và cách giải quyết khác biệt giữa schema lúc ghi với schema lúc đọc.

Spring Cloud Stream có thể tích hợp Avro theo hai hướng chính. Ứng dụng có thể dùng **Avro MessageConverter** để framework chuyển đổi payload dựa trên content type và schema registry, hoặc dùng **native serializer/deserializer (Serde)** do binder và client broker cung cấp. Cách chọn phụ thuộc broker, hệ thống schema hiện có và yêu cầu tương tác với ứng dụng ngoài Spring Cloud Stream.

Bài học này tập trung vào việc lựa chọn và cấu hình hai hướng đó với Kafka, RabbitMQ và Pulsar; đồng thời trình bày cách quản lý writer schema, reader schema, compatibility và kiểm thử hợp đồng message.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Avro schema, writer schema, reader schema và schema registry.
- Phân biệt Avro MessageConverter của Spring Cloud Stream với native Avro Serde của binder.
- Chọn `SpecificRecord`, `GenericRecord` hoặc POJO theo cách quản lý schema.
- Cấu hình Avro MessageConverter với schema cố định hoặc schema registry.
- Cấu hình Kafka Avro Serializer/Deserializer và Pulsar Avro schema theo binder.
- Chọn cách chuyển đổi phù hợp khi dùng RabbitMQ.
- Đánh giá thay đổi schema theo backward, forward và full compatibility.
- Kiểm thử round-trip và khả năng đọc message giữa các phiên bản producer/consumer.

## 1. Avro schema và hợp đồng message

Avro định nghĩa cấu trúc dữ liệu bằng schema. Schema mô tả tên record, namespace, các field, kiểu dữ liệu, giá trị mặc định và những quy tắc liên quan. Producer serialize dữ liệu theo schema đang dùng để ghi; consumer giải mã dữ liệu theo schema ghi kèm message và schema mà ứng dụng hiện tại mong đợi.

Ví dụ schema cho sự kiện `OrderCreated`:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    { "name": "totalMinorUnits", "type": "long" },
    { "name": "currency", "type": "string" },
    { "name": "source", "type": ["null", "string"], "default": null }
  ]
}
~~~

Trong ví dụ, `totalMinorUnits` lưu số tiền theo đơn vị nhỏ nhất của tiền tệ, tránh đưa số thực dấu phẩy động vào hợp đồng tài chính. Field `source` là union giữa `null` và `string`, có giá trị mặc định `null`.

Schema đóng vai trò hợp đồng giữa producer và consumer. Khi đổi schema, cần xem xét các ứng dụng đang chạy có thể vẫn dùng phiên bản cũ hay không. Một thay đổi hợp lệ với producer mới có thể vẫn gây lỗi cho consumer cũ nếu không thỏa quy tắc schema resolution.

### Writer schema và reader schema

- **Writer schema** là schema producer dùng để ghi message.
- **Reader schema** là schema consumer dùng để tạo đối tượng mà ứng dụng đọc.
- **Schema resolution** là quá trình Avro đối chiếu hai schema để xác định field nào được đọc, bỏ qua hoặc nhận giá trị mặc định.

Ví dụ, producer phiên bản 1 ghi `OrderCreated` chưa có field `source`. Consumer phiên bản 2 đã thêm field `source` với default `null`. Khi đọc message cũ, Avro có thể điền `null` cho field mới nhờ default.

Nếu consumer yêu cầu một field mà writer schema không cung cấp và reader schema không khai báo default, quá trình đọc có thể thất bại. Vì vậy, default trong Avro schema là một phần của chiến lược tương thích, không chỉ là giá trị khởi tạo tiện lợi.

### Schema registry

Schema registry lưu trữ schema, subject và phiên bản để producer/consumer có thể tra cứu cùng một hợp đồng. Tùy hệ thống, registry cũng áp dụng chính sách compatibility trước khi chấp nhận phiên bản mới.

Registry thường giúp:

- Tránh nhúng toàn bộ schema vào mọi message.
- Tra cứu writer schema từ schema ID hoặc metadata phiên bản.
- Quản lý lịch sử schema theo subject.
- Kiểm tra compatibility trước khi phát hành schema mới.
- Cho phép consumer dùng reader schema riêng của phiên bản ứng dụng.

Schema registry không tự đảm bảo message tương thích. Producer vẫn cần phát đúng schema, consumer phải có reader schema phù hợp và chính sách compatibility cần được cấu hình theo vòng đời triển khai.

## 2. Chọn cách tích hợp Avro trong Spring Cloud Stream

Hai hướng phổ biến có ranh giới trách nhiệm khác nhau:

| Tiêu chí | Avro MessageConverter | Native Avro Serde |
|---|---|---|
| Thành phần chuyển đổi | Message converter của Spring Cloud Stream | Serializer/deserializer của binder hoặc client broker |
| Cách kích hoạt | Content type và converter được đăng ký/cấu hình | Native encoding/decoding và cấu hình Serde |
| Schema management | Có thể dùng SchemaRegistryClient của Spring Cloud Stream | Theo serializer/schema registry hoặc schema API của broker |
| Phụ thuộc broker | Thấp hơn ở tầng logic chuyển đổi | Cao hơn, tùy Serde của broker |
| Tương tác với ứng dụng ngoài Spring | Cần thống nhất wire format của converter | Thuận tiện khi dùng cùng Serde và wire format |
| Phạm vi hỗ trợ | Phụ thuộc module converter và phiên bản | Phụ thuộc binder/client và tính năng schema |

**Avro MessageConverter** phù hợp khi muốn Spring Cloud Stream quản lý chuyển đổi payload và có thể dùng schema registry client tích hợp. **Native Serde** phù hợp khi broker đã có chuẩn serialization riêng, chẳng hạn Kafka với Confluent Schema Registry hoặc Pulsar với schema native.

Không nên chọn native chỉ vì Avro là định dạng nhị phân. Hãy xác định ai sở hữu schema, producer ngoài Spring đang serialize theo chuẩn nào và consumer cần nhận kiểu Java nào.

## 3. Dùng Avro MessageConverter với schema cố định

Spring Cloud Stream cung cấp `AvroSchemaMessageConverter` trong module hỗ trợ schema registry/converter tương ứng với release train đang sử dụng. Converter có thể làm việc với schema biết trước, schema nằm trong classpath hoặc schema được lấy từ kiểu Avro của payload.

Một cách tiếp cận là dùng Avro `SpecificRecord`: lớp Java được sinh từ file `.avsc` và chứa schema tương ứng. Một cách khác là dùng `GenericRecord`, trong đó ứng dụng tạo record dựa trên một schema được cung cấp riêng.

Ví dụ đăng ký converter với schema cố định trong classpath:

~~~java
import org.springframework.cloud.stream.schema.avro.AvroSchemaMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.MimeType;

@Configuration
public class AvroConverterConfiguration {

    @Bean
    AvroSchemaMessageConverter orderAvroConverter() {
        AvroSchemaMessageConverter converter =
            new AvroSchemaMessageConverter(MimeType.valueOf("avro/bytes"));

        converter.setSchemaLocation(
            new ClassPathResource("schemas/OrderCreated.avsc")
        );

        return converter;
    }
}
~~~

Ví dụ minh họa API converter của Spring Cloud Stream Schema Registry Client. Kiểm tra package, dependency và constructor theo phiên bản dự án đang dùng. Nếu target type là `GenericRecord`, ứng dụng phải cung cấp schema để converter biết cấu trúc record.

Cấu hình binding dùng content type tương ứng:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      bindings:
        orders-out-0:
          destination: orders
          contentType: avro/bytes
        inventory-in-0:
          destination: orders
          group: inventory
          contentType: avro/bytes
~~~

Ở đây, converter được đăng ký với MIME type `avro/bytes`, vì vậy binding cần dùng content type khớp với converter. Nếu dùng MIME type mặc định của converter, hãy đặt content type phù hợp với MIME type đó.

### Dùng SpecificRecord

Với `SpecificRecord`, class Java thường được sinh từ schema Avro trong quá trình build. Producer tạo đối tượng generated class, sau đó converter dùng schema có sẵn trong class để serialize. Consumer dùng class tương ứng hoặc reader schema đã cấu hình để deserialize.

Ví dụ về cách sử dụng ở tầng function:

~~~java
@Bean
Consumer<OrderCreated> inventory() {
    return event -> {
        System.out.println(
            "Đơn hàng " + event.getOrderId()
        );
    };
}
~~~

Trong ví dụ, `OrderCreated` là lớp Java được sinh từ Avro schema. Tên getter thực tế phụ thuộc vào code generation và naming convention của Avro.

### Dùng GenericRecord

`GenericRecord` hữu ích khi ứng dụng xử lý nhiều loại schema hoặc không muốn sinh class riêng cho từng record. Tuy nhiên, converter cần biết schema khi đọc và ghi. Không nên giả định chỉ khai báo kiểu `GenericRecord` là đủ để framework suy ra cấu trúc.

Với dữ liệu động, ứng dụng nên quản lý schema rõ ràng, kiểm tra field trước khi đọc và xử lý trường hợp field tùy chọn hoặc không tồn tại trong phiên bản schema hiện tại.

## 4. Dùng Schema Registry của Spring Cloud Stream

Khi ứng dụng có `SchemaRegistryClient` trong Application Context, Spring Cloud Stream có thể tự cấu hình Avro message converter cho schema management. Cơ chế này cho phép producer đăng ký schema và consumer tra cứu writer schema dựa trên metadata của message.

Ở phía producer, cấu hình output binding với content type dạng `application/*+avro` để kích hoạt converter dùng schema registry:

~~~yaml
spring:
  cloud:
    stream:
      schemaRegistryClient:
        endpoint: http://localhost:8990
      bindings:
        orders-out-0:
          destination: orders
          contentType: application/*+avro
~~~

Khi gửi message, converter suy ra schema từ kiểu payload. Nếu schema chưa tồn tại cho subject tương ứng, converter đăng ký schema và nhận thông tin phiên bản; nếu schema đã tồn tại, converter sử dụng phiên bản đã đăng ký. Metadata content type mang subject và version để consumer tra cứu writer schema.

Ví dụ content type được tạo có dạng:

~~~text
application/vnd.order-created.v2+avro
~~~

Trong ví dụ, `order-created` là subject và `v2` là version minh họa. Tên subject thực tế phụ thuộc chiến lược đặt tên subject và kiểu payload.

Khi nhận message, converter đọc thông tin schema từ content type, lấy writer schema từ registry và dùng Avro schema resolution để chuyển dữ liệu sang reader schema mà consumer sử dụng.

### Các cấu hình schema registry thường dùng

| Thuộc tính | Ý nghĩa |
|---|---|
| `spring.cloud.stream.schemaRegistryClient.endpoint` | Địa chỉ schema registry server |
| `spring.cloud.stream.schema.avro.dynamicSchemaGenerationEnabled` | Cho phép suy ra schema từ POJO bằng reflection khi cần |
| `spring.cloud.stream.schema.avro.readerSchema` | Schema cục bộ dùng làm reader schema trong những trường hợp cần ghi đè lookup |
| `spring.cloud.stream.schema.avro.prefix` | Prefix dùng trong content type mang subject/version, nếu phiên bản hỗ trợ |

Tên và vị trí một số thuộc tính có thể khác giữa các phiên bản Spring Cloud Stream hoặc module Schema Registry. Hãy đối chiếu tài liệu đúng release train. Với POJO không phải Avro `SpecificRecord` hoặc `GenericRecord`, dynamic schema generation cần được bật nếu muốn converter suy ra schema bằng reflection.

Schema registry client thường cache kết quả tra cứu để giảm số lần gọi server. Trong production, cần bảo đảm registry có tính sẵn sàng phù hợp, endpoint được bảo vệ và producer có quyền đăng ký schema theo chính sách của tổ chức.

## 5. Native Avro Serde với Kafka binder

Kafka không có schema registry tích hợp sẵn trong broker. Một giải pháp phổ biến là dùng Kafka Avro Serializer/Deserializer của Confluent cùng Confluent Schema Registry. Có thể dùng registry hoặc serializer khác nếu toàn bộ producer/consumer thống nhất wire format.

Khi dùng native Serde, Kafka client thực hiện serialization/deserialization. Output binding cần bật native encoding; cấu hình Kafka producer dùng Avro serializer. Consumer dùng Avro deserializer tương thích và cấu hình kiểu dữ liệu đích.

Ví dụ dưới đây minh họa cấu hình Confluent Avro Serde theo từng binding:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      bindings:
        orders-out-0:
          destination: orders
          producer:
            useNativeEncoding: true
        inventory-in-0:
          destination: orders
          group: inventory
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
                value.serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
                schema.registry.url: http://localhost:8081
          inventory-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
                specific.avro.reader: true
                schema.registry.url: http://localhost:8081
~~~

Một số điểm cần lưu ý:

- `useNativeEncoding: true` yêu cầu producer dùng serializer native của Kafka.
- `KafkaAvroSerializer` serialize value theo Avro và đăng ký/tra cứu schema qua Confluent Schema Registry.
- `KafkaAvroDeserializer` dùng schema ID trong wire format để lấy writer schema và giải mã.
- `specific.avro.reader: true` yêu cầu deserializer trả về lớp Avro SpecificRecord khi ứng dụng dùng class được sinh từ schema.
- Nếu dùng `GenericRecord`, cấu hình deserializer theo chế độ generic phù hợp với phiên bản thư viện.

Với Kafka binder, Kafka client thực hiện deserialization trước khi payload tới binder. Vì vậy, một số phiên bản/tình huống không cần bật riêng `useNativeDecoding`; hãy kiểm tra tài liệu binder và cấu hình consumer thực tế. Điều quan trọng là value deserializer phải trả về kiểu tương thích với chữ ký function.

### Wire format của Confluent khác Avro bytes thuần

Confluent Avro Serializer thường đóng gói payload theo wire format riêng, gồm byte nhận diện, schema ID và dữ liệu Avro. Một converter Avro thuần hoặc một consumer chỉ đọc Avro bytes không tự động hiểu định dạng này.

Không dùng Confluent `KafkaAvroDeserializer` để đọc payload do một Avro MessageConverter khác tạo ra nếu hai bên không dùng cùng wire format. Tương tự, không dùng Spring Cloud Stream Avro converter để giải mã Confluent payload chỉ vì cả hai đều dùng Avro.

## 6. Native Avro schema với Pulsar binder

Pulsar hỗ trợ schema ở cấp topic và client. Pulsar binder có thể dùng native encoding/decoding để giao việc serialization cho Pulsar client. Với Avro, cấu hình schema type và kiểu message cho producer và consumer.

Ví dụ cấu hình theo binding:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      bindings:
        orders-out-0:
          destination: orders
          producer:
            use-native-encoding: true
        inventory-in-0:
          destination: orders
          group: inventory
          consumer:
            use-native-decoding: true
    pulsar:
      bindings:
        orders-out-0:
          producer:
            schema-type: AVRO
            message-type: com.example.events.OrderCreated
        inventory-in-0:
          consumer:
            schema-type: AVRO
            message-type: com.example.events.OrderCreated
~~~

Trong ví dụ:

- `use-native-encoding` và `use-native-decoding` bật cơ chế native ở hai chiều.
- `schema-type: AVRO` chọn schema Avro của Pulsar.
- `message-type` cho binder biết kiểu Java đích/nguồn cần dùng với schema.

Kiểu `OrderCreated` phải tương thích với schema mà Pulsar client có thể xử lý. Cấu hình chính xác và khả năng hỗ trợ class cụ thể phụ thuộc phiên bản Spring Cloud Stream Pulsar binder và Spring for Apache Pulsar. Nếu message có cả key và value với kiểu khác nhau, binder có thể có thuộc tính riêng để khai báo kiểu key/value.

Pulsar schema được quản lý theo topic và có thể áp dụng chính sách compatibility của broker. Khi producer gửi schema mới, Pulsar có thể kiểm tra schema theo policy của topic. Hãy xác minh schema type, schema version và compatibility policy trên môi trường thử nghiệm trước khi triển khai.

Không áp dụng cấu hình Confluent `schema.registry.url` hoặc Kafka Avro serializer cho Pulsar. Đây là hai hệ sinh thái schema/Serde khác nhau.

## 7. Avro với RabbitMQ binder

RabbitMQ truyền message body dưới dạng bytes và hỗ trợ AMQP properties cùng headers. RabbitMQ không tự áp đặt một schema registry Avro chung cho các message. Vì vậy, ứng dụng thường dùng Avro MessageConverter hoặc converter/serializer tích hợp với Spring AMQP để tạo body Avro.

Một hướng tiếp cận là dùng converter Avro của Spring Cloud Stream với schema cố định hoặc schema registry. Ở phía RabbitMQ, body chứa bytes Avro; metadata như content type hoặc schema version cần được truyền qua AMQP properties/header theo hợp đồng của converter.

Khi producer và consumer đều dùng Spring Cloud Stream Avro MessageConverter, hai phía cần thống nhất MIME type, cách tham chiếu schema và cấu hình converter. Khi consumer là ứng dụng ngoài Spring, cần công bố rõ cách lấy writer schema: schema cố định, registry subject/version hoặc metadata được đặt trong message.

Không có một cấu hình Kafka-style `value.serializer` nào áp dụng cho RabbitMQ. Nếu cần native serialization riêng, phải cấu hình message converter hoặc serializer mà Rabbit binder/Spring AMQP hỗ trợ ở phiên bản đang dùng. Đừng giả định RabbitMQ tự biết cách giải mã Avro chỉ vì payload có MIME type `application/avro`.

## 8. So sánh cách tích hợp theo binder

| Binder | Hướng tích hợp Avro | Schema reference | Điều cần thống nhất |
|---|---|---|---|
| Kafka | Avro MessageConverter hoặc Kafka Avro Serde | Spring Schema Registry hoặc schema ID trong wire format của Serde | Serializer/deserializer, registry, subject, wire format và reader type |
| Pulsar | MessageConverter hoặc native Pulsar schema | Metadata/schema version do Pulsar quản lý | Schema type, message type, topic schema và compatibility policy |
| RabbitMQ | Avro MessageConverter hoặc converter/serializer Spring AMQP | Schema cố định, registry hoặc metadata do ứng dụng quy định | Body bytes, content type, schema reference và AMQP properties |

Không trộn lẫn hai định dạng wire format chỉ vì cùng dùng Avro. Producer và consumer cần thống nhất cả schema lẫn cách đóng gói schema reference. Việc hai payload đều là Avro không có nghĩa chúng có thể đọc thay thế lẫn nhau.

## 9. Quản lý schema evolution và compatibility

Avro hỗ trợ schema resolution giữa writer schema và reader schema. Tuy nhiên, mức tương thích phụ thuộc hướng triển khai và chính sách registry/broker.

Ba khái niệm thường gặp:

- **Backward compatibility**: consumer dùng schema mới có thể đọc dữ liệu được ghi bằng schema cũ.
- **Forward compatibility**: consumer dùng schema cũ có thể đọc dữ liệu được ghi bằng schema mới.
- **Full compatibility**: đáp ứng cả backward và forward theo quy tắc của registry.

Một số thay đổi thường gặp:

| Thay đổi schema | Tác động cần xem xét |
|---|---|
| Thêm field mới có default | Thường hỗ trợ consumer mới đọc message cũ vì reader có giá trị mặc định cho field chưa tồn tại |
| Thêm field mới không có default | Consumer mới có thể không đọc được message cũ vì writer schema không cung cấp field bắt buộc |
| Bỏ field | Consumer cũ có thể cần default nếu writer mới không còn ghi field mà reader cũ yêu cầu |
| Đổi tên field | Có thể cần alias hoặc chiến lược chuyển đổi; đổi tên trực tiếp dễ làm reader không tìm thấy field |
| Đổi kiểu dữ liệu | Chỉ một số phép promotion được Avro hỗ trợ; cần kiểm tra quy tắc cụ thể |
| Thêm giá trị enum | Consumer cũ có thể không nhận biết symbol mới nếu không có default phù hợp |
| Đổi namespace hoặc record name | Có thể ảnh hưởng định danh schema và cách registry phân subject |

Không chỉ kiểm tra schema mới với phiên bản liền trước. Hệ thống có thể còn message tồn trong broker được ghi từ nhiều phiên bản trước đó. Nếu retention dài hoặc consumer có thể replay, cần bảo đảm reader hiện tại đọc được toàn bộ dữ liệu còn nằm trong phạm vi hỗ trợ.

### Quy trình thay đổi schema an toàn

1. Xác định producer và consumer đang dùng những phiên bản schema nào.
2. Chọn compatibility policy phù hợp với chiến lược rollout.
3. Thêm field mới theo cách tương thích, thường kèm default.
4. Đăng ký schema mới ở môi trường kiểm thử.
5. Kiểm tra registry/broker chấp nhận schema theo policy.
6. Kiểm thử consumer mới đọc dữ liệu cũ.
7. Kiểm thử consumer cũ đọc dữ liệu mới nếu yêu cầu forward compatibility.
8. Triển khai producer/consumer theo thứ tự phù hợp.
9. Theo dõi lỗi serialization/deserialization sau khi rollout.
10. Chỉ loại bỏ field cũ khi không còn consumer hoặc message nào phụ thuộc vào field đó.

Schema registry giúp phát hiện thay đổi không tương thích trước khi phát hành, nhưng không thay thế kiểm thử tích hợp và kế hoạch triển khai nhiều phiên bản.

## 10. Kiểm thử Avro MessageConverter và native Serde

Nên kiểm thử ở nhiều lớp để tách lỗi schema khỏi lỗi binder.

### Unit test schema và record

Kiểm tra:
- Field bắt buộc có giá trị.
- Field union và default được xử lý đúng.
- Kiểu dữ liệu và logical type được ánh xạ chính xác.
- Generated SpecificRecord tương thích với schema nguồn.
- GenericRecord không truy cập field không tồn tại mà không kiểm tra.

### Round-trip serialization

Với mỗi serializer/deserializer:
1. Tạo record mẫu.
2. Serialize thành bytes.
3. Deserialize bằng writer schema và reader schema dự kiến.
4. So sánh giá trị field, default và logical type.
5. Thử đọc message bằng schema phiên bản trước và sau thay đổi.

### MessageConverter test

Nếu dùng Avro MessageConverter:
- Xác minh content type kích hoạt đúng converter.
- Xác minh converter tìm được schema cố định hoặc schema registry.
- Xác minh subject/version được truyền và tra cứu chính xác.
- Xác minh reader schema được áp dụng khi nhận message.
- Kiểm tra hành vi khi registry không sẵn sàng hoặc schema không tồn tại.

### Native Serde integration test

Với Kafka:
- Dùng đúng Kafka Avro Serializer/Deserializer và Schema Registry tương ứng.
- Kiểm tra schema ID và wire format trên topic.
- Kiểm tra SpecificRecord hoặc GenericRecord đúng kiểu.
- Kiểm tra producer/consumer dùng cùng subject strategy và compatibility policy.

Với Pulsar:
- Kiểm tra topic nhận đúng schema type AVRO.
- Kiểm tra message type và schema version.
- Kiểm tra consumer giải mã được message đã ghi bởi phiên bản producer trước.

Với RabbitMQ:
- Kiểm tra body bytes, content type, schema reference và AMQP properties.
- Đọc message bằng converter tương thích.
- Kiểm tra consumer ngoài Spring có thể giải mã theo tài liệu hợp đồng.

Test binder có thể kiểm tra function và binding ở cấp Spring Cloud Stream, nhưng không thay thế broker integration test cho schema registry, native Serde hoặc wire format cụ thể.

## 11. Lỗi thường gặp khi tích hợp Avro

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy converter | MIME type không khớp hoặc thiếu module Avro converter | Kiểm tra dependency và content type |
| `GenericRecord` không serialize được | Converter chưa được cung cấp schema | Cấu hình schema cố định hoặc schema registry |
| Schema registry từ chối đăng ký | Schema vi phạm compatibility policy | Kiểm tra thay đổi field, default, alias và policy |
| Consumer không tìm được writer schema | Thiếu schema reference hoặc registry endpoint sai | Kiểm tra content type/schema ID và endpoint |
| Producer gửi được nhưng consumer lỗi | Writer schema và reader schema không tương thích | Kiểm tra schema resolution và default |
| Kafka báo lỗi deserializer | Dùng sai Serde hoặc wire format không khớp | Đồng bộ Kafka serializer/deserializer và registry |
| Kafka nhận bytes nhưng không đọc được bằng converter | Confluent wire format khác Avro bytes thuần | Dùng đúng deserializer hoặc chuyển về cùng converter |
| Pulsar từ chối schema | Schema type/message type không khớp hoặc policy không chấp nhận | Kiểm tra binding schema config và topic policy |
| RabbitMQ consumer không đọc được body | Converter hoặc MIME type khác với producer | Đồng bộ converter, content type và schema reference |
| Consumer mới không đọc message cũ | Reader schema thiếu default hoặc schema cũ không còn tra cứu được | Kiểm tra retention schema và compatibility |
| Payload đổi kiểu sau rollout | Generated class, schema hoặc serializer khác phiên bản | Kiểm thử tương thích và phát hành class/schema đồng bộ |

Khi chẩn đoán, kiểm tra lần lượt: payload Java, schema được dùng khi serialize, bytes thực tế, schema reference, writer schema, reader schema và kiểu object mà function mong đợi. Đừng chỉ dựa vào log “send success” để kết luận hợp đồng Avro hoạt động đúng.

## 12. Bài thực hành: phát hành OrderCreated bằng Avro

Tạo một luồng sự kiện đơn hàng có producer và consumer:

1. Viết file `OrderCreated.avsc` với các field `eventId`, `orderId`, `totalMinorUnits`, `currency` và `source` có default.
2. Sinh lớp Java SpecificRecord từ schema hoặc tạo GenericRecord có schema rõ ràng.
3. Khai báo producer function hoặc service phát hành `OrderCreated`.
4. Chọn một trong hai hướng: Avro MessageConverter với schema registry, hoặc native Serde theo binder.
5. Cấu hình output binding destination `orders` và content type hoặc native encoding tương ứng.
6. Cấu hình consumer `inventory` dùng reader schema phù hợp.
7. Gửi một message mẫu và xác minh consumer nhận đúng field.
8. Thêm field `salesChannel` có default vào schema phiên bản mới.
9. Đăng ký schema mới hoặc cập nhật schema native theo binder.
10. Kiểm thử consumer mới đọc message phiên bản cũ và consumer cũ đọc message mới theo compatibility policy.
11. Thử bỏ default của field mới trong môi trường kiểm thử để quan sát lỗi tương thích.
12. Ghi lại schema version, subject, serializer/converter và phiên bản ứng dụng trong kết quả kiểm thử.

Bảng kiểm tra thực hành:

| Nội dung | Kết quả cần xác nhận |
|---|---|
| Schema nguồn | Hợp lệ và có namespace/record name ổn định |
| Producer type | SpecificRecord hoặc GenericRecord đúng schema |
| Serialization path | MessageConverter hoặc native Serde đã chọn |
| Schema reference | Subject/version hoặc schema ID được truyền đúng |
| Consumer type | Reader schema và kiểu Java tương thích |
| Compatibility | Các phiên bản producer/consumer cần hỗ trợ đều đọc được |
| Broker test | Payload được ghi và đọc đúng trên broker mục tiêu |

Khi hoàn thành, bạn cần giải thích được vì sao Avro MessageConverter và native Serde có thể tạo ra hai wire format khác nhau, vì sao consumer cần writer schema và reader schema, và cách kiểm tra thay đổi schema trước khi triển khai.

## Kết luận

Avro cung cấp schema có cấu trúc và cơ chế schema resolution giúp producer, consumer phát triển hợp đồng theo phiên bản. Trong Spring Cloud Stream, Avro MessageConverter để framework xử lý chuyển đổi và có thể tích hợp SchemaRegistryClient; native Serde giao việc serialization cho binder/client của broker.

Kafka có thể dùng Kafka Avro Serializer/Deserializer cùng schema registry; Pulsar có thể dùng native Avro schema và message type; RabbitMQ thường cần Avro converter hoặc serializer ở tầng ứng dụng vì AMQP chỉ vận chuyển body và metadata. Dù chọn cách nào, producer và consumer phải thống nhất wire format, schema reference và compatibility policy. Hãy kiểm thử round-trip cùng dữ liệu của nhiều phiên bản trước khi đưa schema mới vào production.

## Tài liệu tham khảo

- [Spring Cloud Stream – Schema Registry và Avro Message Converters](https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html)
- [Spring Cloud Stream – Kafka Binder: Native Serializer và Deserializer](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring Cloud Stream – Pulsar Binder: Native Conversion với Pulsar Schema](https://docs.spring.io/spring-cloud-stream/docs/current-SNAPSHOT/reference/html/spring-cloud-stream-binder-pulsar.html)
- [Apache Avro – Specification](https://avro.apache.org/docs/)

