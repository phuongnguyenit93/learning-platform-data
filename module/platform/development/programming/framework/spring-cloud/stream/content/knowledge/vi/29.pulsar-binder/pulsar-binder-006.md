# Chuyển đổi của framework và native Pulsar Schema

Spring Cloud Stream có thể chuyển đổi message bằng cơ chế của Spring Messaging hoặc giao việc tuần tự hóa và giải tuần tự hóa cho Apache Pulsar thông qua native schema. Hai cách này đều cho phép function nhận các kiểu Java như record hoặc POJO, nhưng chúng tạo ra hợp đồng dữ liệu trên topic khác nhau.

Ở chế độ mặc định, Spring Cloud Stream dùng message converter của framework. Nếu không chỉ định content type, framework mặc định dùng application/json; payload được chuyển thành byte[] trước khi Pulsar binder gửi bằng Schema.BYTES. Khi consumer nhận dữ liệu, binder lấy byte[] và Spring MessageConverter chuyển thành kiểu đích. Pulsar broker không nhận được JSON Schema hoặc Avro Schema tương ứng chỉ vì ứng dụng đặt content type là application/json.

Với native encoding/decoding, ứng dụng bật use-native-encoding ở producer và use-native-decoding ở consumer. Pulsar binder dùng Pulsar Schema để serialize/deserialize dữ liệu và trao đổi SchemaInfo với broker. Ứng dụng phải khai báo schema-type và message-type cho binding, hoặc cung cấp custom schema mapping phù hợp.

Bài học này giải thích khác biệt giữa hai cơ chế, cách cấu hình native JSON/Avro, cách quản lý schema theo topic, kiểm soát schema evolution và chuyển đổi headers, cùng cách kiểm thử hợp đồng giữa các service.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt Spring MessageConverter với native Pulsar Schema.
- Giải thích vì sao contentType application/json không tự đăng ký JSON Schema trong Pulsar.
- Cấu hình use-native-encoding và use-native-decoding theo từng binding.
- Khai báo schema-type và message-type cho producer/consumer.
- Dùng message-key-type và message-value-type khi payload có key/value riêng.
- Hiểu SchemaInfo, schema version và schema registry tích hợp trong Pulsar broker.
- Chọn chiến lược BACKWARD, FORWARD, FULL và các biến thể TRANSITIVE.
- Cấu hình PulsarHeaderMapper để chuyển đổi headers an toàn.
- Chọn cấp cấu hình binder, binding hoặc Spring Boot phù hợp.
- Kiểm thử serialization, schema compatibility và triển khai nhiều phiên bản producer/consumer.

## 1. Hai tầng chuyển đổi dữ liệu

Khi một function Spring Cloud Stream phát hoặc nhận message, có hai tầng cần phân biệt:

1. **Message conversion của framework:** chuyển payload Java thành representation mà Spring Messaging/binder truyền đi.
2. **Native schema của Pulsar:** dùng Schema API của Pulsar để serialize/deserialize payload và trao đổi metadata schema với broker.

Hai tầng có thể cho kết quả JSON tương tự khi nhìn vào nội dung bytes, nhưng hợp đồng và metadata trên broker khác nhau.

| Nội dung | Framework message conversion | Native Pulsar Schema |
|---|---|---|
| Thành phần chuyển đổi | Spring MessageConverter | Pulsar Schema |
| Cấu hình chính | contentType và message converter | schema-type, message-type |
| Producer | Framework chuyển payload thành byte[]; binder gửi Schema.BYTES | Pulsar serializer tạo bytes theo schema đã chọn |
| Consumer | Nhận byte[] rồi framework chuyển sang kiểu đích | Pulsar deserializer tạo kiểu Java theo schema |
| Metadata schema tại broker | Không tự đăng ký JSON/Avro schema chỉ nhờ contentType | Pulsar quản lý SchemaInfo và schema version theo topic |
| Kiểm tra tương thích schema | Phụ thuộc converter/ứng dụng | Pulsar broker schema compatibility check |
| Phù hợp | Tích hợp linh hoạt, middleware-neutral | Hợp đồng dữ liệu được quản lý ở Pulsar |

~~~mermaid
flowchart TD
    A["Java object trong function"] --> B{"Chọn cơ chế chuyển đổi"}
    B -->|Framework| C["Spring MessageConverter"]
    C --> D["byte[]"]
    D --> E["Pulsar Schema.BYTES"]
    B -->|Native| F["Pulsar Schema serializer"]
    F --> G["SchemaInfo + payload bytes"]
    E --> H["Pulsar topic"]
    G --> H
    H --> I{"Consumer binding"}
    I -->|Framework| J["byte[] rồi MessageConverter"]
    I -->|Native| K["Pulsar Schema deserializer"]
    J --> L["Java object"]
    K --> L
~~~

Không nên chọn chế độ chỉ dựa trên việc payload cuối cùng có phải JSON hay không. Hãy quyết định nơi quản lý schema, cách consumer giải mã và cách kiểm tra tương thích khi producer/consumer được triển khai độc lập.

## 2. Cơ chế mặc định: Spring MessageConverter

Trong binder-based application, Spring Cloud Stream mặc định sử dụng message conversion của Spring Framework. Nếu không khai báo content type, content type mặc định là application/json cho inbound và outbound binding.

Ở chiều gửi:
1. Function trả về một Java object.
2. Spring Cloud Stream dùng MessageConverter để chuyển object thành byte[].
3. Pulsar binder gửi byte[] tới topic bằng Schema.BYTES.

Ở chiều nhận:
1. Pulsar binder tiêu thụ message dưới dạng byte[].
2. Spring Cloud Stream dùng content type và MessageConverter để chuyển byte[] thành kiểu tham số của function.
3. Function nhận Java object đã được chuyển đổi.

Ví dụ function:

~~~java
import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderAccepted> acceptOrder() {
        return event -> new OrderAccepted(
            event.orderId(),
            "ACCEPTED",
            event.total()
        );
    }

    record OrderCreated(String orderId, BigDecimal total) {}
    record OrderAccepted(String orderId, String status, BigDecimal total) {}
}
~~~

Cấu hình framework conversion:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders
          content-type: application/json
        acceptOrder-out-0:
          destination: accepted-orders
          content-type: application/json
~~~

Cấu hình trên yêu cầu framework chuyển đổi payload JSON. Nó không tự đăng ký một Pulsar JSON Schema cho topic orders hoặc accepted-orders. Với đường đi mặc định, binder dùng Schema.BYTES khi gửi payload đã được framework serialize.

### Khi nào framework conversion phù hợp?

Dùng framework conversion khi:
- Ứng dụng cần giữ mô hình message converter chung giữa nhiều binder.
- Topic chỉ cần truyền bytes và hợp đồng được quản lý ở tầng ứng dụng hoặc API riêng.
- Các service đã thống nhất định dạng payload nhưng không cần Pulsar broker kiểm tra schema.
- Cần tùy chỉnh conversion qua Spring MessageConverter.

Đổi lại, broker không có đủ schema metadata để kiểm tra tương thích JSON/Avro chỉ từ content type. Producer có thể gửi bytes không đúng hợp đồng mà broker không phát hiện ở tầng Pulsar Schema.

## 3. Native encoding và native decoding

Native mode yêu cầu producer và consumer binding bật cờ riêng:

- Producer: spring.cloud.stream.bindings.<binding-name>.producer.use-native-encoding=true
- Consumer: spring.cloud.stream.bindings.<binding-name>.consumer.use-native-decoding=true

Khi native encoding/decoding được bật, Spring Cloud Stream không dùng Spring MessageConverter cho payload của binding đó. Pulsar binder sử dụng schema được cấu hình để encode hoặc decode payload.

Native mode không tự đoán schema nghiệp vụ từ contentType. Với Pulsar, khai báo extended binding properties:
- spring.cloud.stream.pulsar.bindings.<binding-name>.producer.schema-type
- spring.cloud.stream.pulsar.bindings.<binding-name>.producer.message-type
- spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.schema-type
- spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.message-type

Ví dụ function nhận OrderCreated và phát OrderAccepted:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders
          consumer:
            use-native-decoding: true
        acceptOrder-out-0:
          destination: accepted-orders
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          acceptOrder-in-0:
            consumer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
          acceptOrder-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.orders.OrderAccepted
~~~

Các tên class trong message-type phải là kiểu thực tế có thể được nạp bởi ứng dụng. Producer và consumer cần dùng schema tương thích với topic. Nếu package hoặc class name thay đổi, cập nhật cấu hình và kiểm thử deployment cùng lúc.

### Producer và consumer có thể chọn riêng

Cờ native encoding và native decoding được cấu hình theo từng binding. Có thể có producer native và consumer framework conversion hoặc ngược lại về mặt cấu hình, nhưng hai đầu phải thống nhất representation thực tế trên topic.

Ví dụ, nếu producer gửi JSON bytes bằng Schema.BYTES qua framework conversion, consumer framework conversion có thể đọc bytes rồi chuyển JSON thành object. Nếu producer gửi native Avro, consumer phải dùng native decoding với schema tương thích; không thể chỉ đặt contentType application/json để đọc Avro.

Để dễ vận hành, nên chọn một quy ước nhất quán cho mỗi topic và ghi rõ trong hợp đồng sự kiện: framework conversion hay native schema, schema type, message type và chính sách evolution.

## 4. schema-type và message-type

Hai thuộc tính này phục vụ hai mục đích khác nhau:

- schema-type chọn loại schema Pulsar dùng để serialize/deserialize, ví dụ JSON hoặc AVRO.
- message-type chỉ ra kiểu Java mà binder cần dùng khi tạo native schema hoặc chuyển dữ liệu về ứng dụng.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: AVRO
              message-type: com.acme.events.OrderCreated
~~~

Khi schema-type được bỏ trống, binder có thể tra cứu custom schema mappings đã cấu hình. Nếu không có mapping phù hợp, việc tạo producer/consumer có thể thất bại hoặc dùng cấu hình không như mong muốn. Với hệ thống cần hợp đồng rõ ràng, khai báo schema-type tường minh giúp reviewer nhìn thấy lựa chọn serialization ngay trong cấu hình.

### Các loại schema thường gặp

Pulsar hỗ trợ schema nguyên thủy và schema cấu trúc. Các nhóm thường dùng gồm:

| Nhóm | Ví dụ | Dữ liệu phù hợp |
|---|---|---|
| Primitive | STRING, BOOLEAN, INT32, INT64, BYTES | Giá trị đơn giản hoặc payload bytes |
| JSON | JSON | POJO/record được biểu diễn bằng JSON schema |
| AVRO | AVRO | Record có schema Avro |
| Protobuf | PROTOBUF, PROTOBUF_NATIVE | Message được định nghĩa bằng Protocol Buffers |
| KeyValue | KEY_VALUE | Message có schema riêng cho key và value |

Danh sách cụ thể và cách đặt tên schema-type phụ thuộc phiên bản Pulsar client và binder. Hãy kiểm tra enum/schema mapping của phiên bản dự án đang dùng trước khi đưa một loại schema mới vào cấu hình.

## 5. Ví dụ native JSON với Java record

Định nghĩa kiểu sự kiện:

~~~java
package com.acme.orders;

import java.math.BigDecimal;

public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total
) {}
~~~

Producer function:

~~~java
import java.math.BigDecimal;
import java.util.UUID;
import java.util.function.Supplier;

@Bean
Supplier<OrderCreated> publishOrder() {
    return () -> new OrderCreated(
        UUID.randomUUID().toString(),
        "ORD-1001",
        new BigDecimal("125.50")
    );
}
~~~

Cấu hình producer:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
~~~

Pulsar binder dùng JSON Schema cho kiểu OrderCreated thay vì gửi bytes theo Schema.BYTES của framework conversion. Khi producer kết nối topic, broker có thể kiểm tra SchemaInfo và compatibility theo cấu hình topic.

Lưu ý rằng record Java cần tương thích với cơ chế schema được chọn và phiên bản thư viện. Nếu dùng kiểu lồng nhau, enum, collection hoặc trường nullable, kiểm tra schema được tạo ra thay vì chỉ dựa vào tên class.

## 6. Ví dụ native AVRO

Với Avro, message type có thể là POJO/record phù hợp với Avro schema generation hoặc kiểu được hỗ trợ bởi Spring for Apache Pulsar.

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders-avro
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: AVRO
              message-type: com.acme.events.OrderCreated
~~~

Consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders-avro
          group: order-processor
          consumer:
            use-native-decoding: true
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              schema-type: AVRO
              message-type: com.acme.events.OrderCreated
~~~

Producer và consumer phải thống nhất schema tương thích, không nhất thiết phải cùng một phiên bản class nếu schema evolution cho phép. Ví dụ consumer mới có thể đọc dữ liệu được ghi bằng schema cũ khi thay đổi tuân thủ backward compatibility.

Không nên đổi schema-type từ AVRO sang JSON trên cùng topic mà không có kế hoạch migration. Schema type là một phần của hợp đồng topic; các consumer hiện hữu có thể không giải mã được dữ liệu mới.

## 7. KeyValue schema và kiểu key/value riêng

Một số ứng dụng cần key và value có kiểu khác nhau. Ví dụ:
- Key: orderId để định tuyến hoặc partition.
- Value: OrderCreated chứa nội dung sự kiện.

Pulsar hỗ trợ KeyValue schema. Binder cung cấp message-key-type và message-value-type để khai báo kiểu đích cho key và value khi native conversion được sử dụng.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders-key-value
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: KEY_VALUE
              message-key-type: java.lang.String
              message-value-type: com.acme.orders.OrderCreated
~~~

Khi dùng consumer native decoding, cấu hình tương ứng trên input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders-key-value
          consumer:
            use-native-decoding: true
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              schema-type: KEY_VALUE
              message-key-type: java.lang.String
              message-value-type: com.acme.orders.OrderCreated
~~~

Pulsar KeyValue schema có thể mã hóa key/value theo kiểu INLINE (cùng nằm trong payload) hoặc SEPARATED (key là message key, value là payload). Lựa chọn encoding cần được thống nhất giữa producer, consumer và hệ thống khác đọc topic. Không giả định mọi client đều diễn giải key/value giống nhau nếu không thống nhất schema và encoding.

## 8. SchemaInfo và schema registry của Pulsar

Pulsar quản lý schema bằng metadata SchemaInfo. Thông tin này được lưu theo từng topic, gồm:
- name: tên schema.
- type: loại schema.
- schema: phần định nghĩa schema ở dạng bytes.
- properties: metadata tùy chỉnh dạng key/value.

Khi producer tạo kết nối với schema:
1. Client tạo schema instance từ kiểu dữ liệu.
2. Producer gửi SchemaInfo tới broker.
3. Broker tra cứu schema đã đăng ký của topic.
4. Nếu schema chưa có, broker xét chính sách auto update và compatibility.
5. Nếu hợp lệ, broker đăng ký schema version và trả version cho producer.
6. Message được ghi kèm thông tin schema version để consumer có thể chọn schema tương ứng khi deserialize.

Ở chiều đọc, consumer kết nối với schema tương thích. Broker kiểm tra schema của consumer so với schema topic theo compatibility policy.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Pulsar broker
    participant R as Schema registry
    participant T as Topic
    participant C as Consumer
    P->>B: Connect with SchemaInfo
    B->>R: Lookup / register schema
    R-->>B: Schema version or incompatibility
    B-->>P: Accept or reject producer
    P->>T: Publish message with schema version
    C->>B: Subscribe with consumer SchemaInfo
    B->>R: Check consumer compatibility
    R-->>B: Compatible schema version
    B-->>C: Deliver message with schema version
    Note over C: Client deserializes using the schema version
~~~

Schema registry của Pulsar được tích hợp với broker và storage của Pulsar. Nó khác với Spring Cloud Stream Schema Registry server. Spring Schema Registry là một thành phần riêng trong hệ sinh thái Spring Cloud Stream, còn native Pulsar Schema sử dụng SchemaInfo do Pulsar quản lý theo topic.

Một điểm vận hành cần kiểm tra là schema validation enforcement cho producer. Trong cấu hình Pulsar mặc định được tài liệu 5.0.x mô tả, enforcement này tắt đối với producer; producer không khai báo schema vẫn có thể ghi bytes vào topic đã có schema. Nếu cần broker từ chối producer không tuân theo schema topic, hãy bật và kiểm thử chính sách schema validation enforcement ở cluster, thay vì chỉ dựa vào việc topic đã đăng ký SchemaInfo.

## 9. Schema compatibility và evolution

Schema evolution cho phép thay đổi cấu trúc dữ liệu theo thời gian mà không làm hỏng tất cả producer/consumer đang chạy. Pulsar kiểm tra compatibility theo schema type và strategy được cấu hình.

Các chiến lược phổ biến:

| Strategy | Ý nghĩa | Ví dụ thay đổi thường tương thích |
|---|---|---|
| BACKWARD | Consumer dùng schema mới đọc được dữ liệu từ schema ngay trước đó | Thêm field optional; xóa field |
| BACKWARD_TRANSITIVE | Schema mới đọc được dữ liệu từ mọi schema cũ | Áp dụng backward check với toàn bộ lịch sử |
| FORWARD | Consumer schema cũ đọc được dữ liệu được ghi bằng schema mới | Thêm field; xóa field optional |
| FORWARD_TRANSITIVE | Consumer cũ đọc được dữ liệu từ mọi schema mới hơn trong lịch sử | Áp dụng forward check xuyên suốt |
| FULL | Schema mới và schema trước có thể đọc dữ liệu của nhau | Thay đổi field optional theo quy tắc của schema type |
| FULL_TRANSITIVE | Tương thích hai chiều với toàn bộ các phiên bản trước | Full check với toàn bộ lịch sử |

Ví dụ:
- Producer v1 phát OrderCreated(orderId, total).
- Producer v2 thêm trường optional currency.
- Consumer v2 đọc được message v1 nếu schema cho phép giá trị mặc định/optional.
- Consumer v1 có thể đọc message v2 hay không phụ thuộc FORWARD/FULL compatibility và cách schema định nghĩa trường mới.

Từ “optional” không chỉ là Java field có thể null. Nó phải được biểu diễn đúng trong schema, chẳng hạn union nullable hoặc default value theo quy tắc Avro/JSON Schema tương ứng. Một field Java có thể null nhưng schema sinh ra vẫn khai báo required nếu không cấu hình phù hợp.

### Transitive và non-transitive

Non-transitive kiểm tra schema mới với phiên bản gần nhất theo chiến lược. Transitive kiểm tra với tất cả phiên bản trước đó. Ví dụ:
- V1 -> V2 -> V3.
- BACKWARD chỉ kiểm tra V3 với V2.
- BACKWARD_TRANSITIVE kiểm tra V3 với cả V2 và V1.

Transitive hữu ích khi có consumer cũ vẫn tồn tại hoặc dữ liệu lịch sử lâu dài. Nó cũng giới hạn thay đổi mạnh hơn vì phải giữ tương thích với nhiều phiên bản.

### Default compatibility không nên được đoán

Theo tài liệu Pulsar 5.0.x, mặc định cho Avro và JSON là FULL; các schema type khác thường mặc định ALWAYS_INCOMPATIBLE. Giá trị thực tế phụ thuộc phiên bản và cấu hình broker. Trước khi triển khai, kiểm tra strategy của topic và schema type cụ thể; đừng dựa vào default được nhớ từ một cluster khác.

Schema compatibility chỉ kiểm tra cấu trúc dữ liệu theo strategy. Nó không chứng minh ý nghĩa nghiệp vụ không đổi. Ví dụ đổi đơn vị total từ VND sang USD mà vẫn giữ kiểu decimal có thể tương thích cấu trúc nhưng sai nghiệp vụ. Hãy version hóa semantics hoặc bổ sung trường/currency rõ ràng.

## 10. Thay đổi schema an toàn

Một quy trình schema evolution nên có các bước:

1. Xác định producer và consumer đang dùng schema version nào.
2. Xem schema hiện tại trên topic và compatibility strategy.
3. Tạo schema mới trong môi trường test.
4. Kiểm tra schema mới có tương thích theo strategy đã chọn.
5. Triển khai consumer có thể đọc cả schema cũ và mới.
6. Sau đó mới triển khai producer phát schema mới.
7. Theo dõi lỗi deserialization, schema rejection và consumer lag.
8. Chỉ loại bỏ hỗ trợ schema cũ khi dữ liệu cũ đã hết retention hoặc mọi consumer đã nâng cấp.

Đây thường là quy trình consumer-first khi cần backward compatibility: consumer mới phải đọc được message cũ trước khi producer bắt đầu phát message mới.

Không xóa schema cũ chỉ để làm registry gọn hơn. Message lịch sử có thể vẫn cần schema version cũ để giải mã. Việc giữ lịch sử schema là một phần của khả năng replay và audit.

## 11. Header conversion giữa Pulsar và Spring Message

Payload schema và message headers là hai phần khác nhau. Native schema quyết định cách encode/decode payload; Pulsar binder còn phải chuyển metadata/header giữa Pulsar message và Spring Message.

Pulsar binder cung cấp PulsarHeaderMapper mặc định. Có thể thay thế bằng bean PulsarHeaderMapper riêng, ví dụ JsonPulsarHeaderMapper, để kiểm soát:
- inboundPatterns: header nào được đưa từ Pulsar vào Spring Message.
- outboundPatterns: header nào được gửi từ Spring Message ra Pulsar.
- trustedPackages: package nào được phép deserialize object header.
- toStringClasses: kiểu header được biểu diễn bằng chuỗi.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.pulsar.support.header.JsonPulsarHeaderMapper;
import org.springframework.pulsar.support.header.PulsarHeaderMapper;

@Configuration
class PulsarHeaderConfiguration {

    @Bean
    PulsarHeaderMapper pulsarHeaderMapper() {
        return JsonPulsarHeaderMapper.builder()
            .inboundPatterns("!secret", "*")
            .outboundPatterns("!password", "!accessToken", "*")
            .trustedPackages("com.acme.events")
            .build();
    }
}
~~~

Tên package và API cụ thể cần đối chiếu phiên bản Spring for Apache Pulsar đang dùng. Ví dụ trên minh họa chính sách lọc header: không đưa secret vào ứng dụng và không phát password/accessToken ra broker.

Không đặt toàn bộ payload nghiệp vụ vào headers. Headers phù hợp với correlation ID, trace ID, tenant, event type hoặc metadata định tuyến. Payload schema nên chứa dữ liệu nghiệp vụ có cấu trúc.

### Headers không thay thế schema

Một header content-type hoặc event-type không tự đăng ký Pulsar schema. Khi dùng native encoding, schema-type và message-type xác định serializer/deserializer. Header mapper chỉ điều khiển metadata message. Hai cấu hình này cần được kiểm thử độc lập.

## 12. Cấp cấu hình và thứ tự ưu tiên

Pulsar binder sử dụng Spring for Apache Pulsar để tạo producer/consumer. Vì vậy, có thể cấu hình property ở nhiều cấp:

- Spring Boot properties: spring.pulsar.producer..., spring.pulsar.consumer...
- Binder-wide properties: spring.cloud.stream.pulsar.binder.producer..., spring.cloud.stream.pulsar.binder.consumer...
- Extended binding properties: spring.cloud.stream.pulsar.bindings.<binding-name>.producer... hoặc consumer...

Thứ tự ưu tiên từ cao xuống thấp:

1. Extended binding properties.
2. Binder properties.
3. Spring Boot properties.

Ví dụ:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://localhost:6650
  cloud:
    stream:
      pulsar:
        binder:
          producer:
            batching-enabled: true
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
              batching-enabled: false
~~~

Trong ví dụ, batching-enabled ở cấp binding ghi đè giá trị cấp binder cho output binding publishOrder-out-0. Service URL ở Spring Boot áp dụng cho Pulsar client toàn ứng dụng.

Dùng cấp binder cho thiết lập chung. Dùng extended binding khi hai function hoặc hai topic cần schema, batching, producer/consumer behavior khác nhau. Tránh cấu hình cùng một property ở nhiều cấp mà không ghi rõ giá trị cuối cùng; khi debug, hãy kiểm tra property source và binding cụ thể.

## 13. Custom schema mapping

Nếu ứng dụng có nhiều kiểu dữ liệu hoặc muốn dùng schema mapping chung, có thể cấu hình custom schema mappings trong Pulsar binder. Khi schema-type bị bỏ trống, binder có thể tham khảo các mapping này để xác định schema phù hợp.

Custom mapping giúp:
- Chuẩn hóa schema type cho các class dùng chung.
- Tránh lặp schema-type và message-type ở nhiều binding.
- Quản lý mapping giữa kiểu Java và Pulsar Schema tập trung.

Tuy nhiên, mapping không thay thế schema compatibility trên broker. Mapping chỉ giúp binder chọn schema/kiểu dữ liệu; Pulsar broker vẫn quản lý SchemaInfo theo topic và kiểm tra tương thích khi producer/consumer kết nối.

Khi thay đổi mapping, kiểm tra tất cả binding sử dụng class đó. Một mapping mới có thể làm producer chuyển từ Schema.BYTES sang native schema hoặc đổi schema type, ảnh hưởng tới consumer đang chạy.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JSON payload chạy được nhưng topic không có JSON Schema | Đang dùng framework conversion và Schema.BYTES | Bật native encoding và khai báo schema-type/message-type |
| Consumer native không deserialize được | Thiếu use-native-decoding hoặc schema-type/message-type sai | Kiểm tra cấu hình input binding và class |
| Producer/consumer dùng schema khác nhau | Message type hoặc schema version không tương thích | Kiểm tra SchemaInfo và compatibility strategy |
| Producer bị broker từ chối khi tạo | Schema mới không tương thích hoặc auto update bị giới hạn | Kiểm tra strategy và đăng ký schema |
| Native Avro bị đọc như JSON | Producer/consumer không thống nhất schema type | Dùng cùng hợp đồng Avro và native decoding |
| Không tìm được message-type | Sai fully qualified class name hoặc class không có trên classpath | Kiểm tra package, dependency và class loader |
| KeyValue deserialize sai | Thiếu message-key-type/message-value-type hoặc encoding không thống nhất | Khai báo cả hai kiểu và thống nhất INLINE/SEPARATED |
| contentType không có tác dụng như mong đợi | Binding đã bật native encoding/decoding | Cấu hình Pulsar schema thay vì dựa vào MessageConverter |
| Header bị mất | Header mapper không map pattern tương ứng | Kiểm tra inbound/outbound patterns |
| Header nhạy cảm bị phát ra | Mapper cho phép wildcard quá rộng | Dùng deny patterns và trusted packages rõ ràng |
| Schema mới được chấp nhận nhưng nghiệp vụ lỗi | Cấu trúc tương thích nhưng semantics thay đổi | Version hóa semantics và kiểm thử contract |
| Một function ghi đè cấu hình function khác | Dùng binder-wide property trong khi binding cần cấu hình riêng | Chuyển sang extended binding properties |

## 15. Kiểm thử framework conversion và native schema

Nên kiểm thử hai đường chuyển đổi riêng biệt. Không dùng một test duy nhất để kết luận cả framework converter và Pulsar native schema đều đúng.

### Kiểm thử framework conversion

1. Cấu hình producer và consumer không bật native encoding/decoding.
2. Gửi một Java record với contentType application/json.
3. Xác minh payload trên Pulsar được gửi theo Schema.BYTES.
4. Consumer nhận bytes và Spring MessageConverter chuyển thành đúng kiểu Java.
5. Kiểm tra trường optional, decimal, timestamp và nested object.
6. Xác minh broker không được giả định đang kiểm tra JSON schema.

### Kiểm thử native JSON/Avro

1. Bật use-native-encoding cho producer.
2. Khai báo schema-type và message-type.
3. Bật use-native-decoding cho consumer.
4. Dùng cùng schema hoặc schema tương thích.
5. Gửi message và xác minh consumer nhận đúng object.
6. Xem SchemaInfo và schema version trên topic.
7. Thử producer dùng schema không tương thích và xác minh broker từ chối khi compatibility enforcement được bật.
8. Thử consumer schema cũ/mới theo chiến lược BACKWARD/FORWARD/FULL.

### Kiểm thử KeyValue và headers

- Gửi key/value với hai kiểu khác nhau.
- Xác minh key/value type và encoding INLINE/SEPARATED.
- Xác minh correlation ID và event type được map qua PulsarHeaderMapper.
- Xác minh secret/password/access token không đi qua header mapper.
- Thử header object từ package không được trusted và kiểm tra deserialization behavior.

### Kiểm thử migration

- Chạy producer v1 và consumer v1.
- Triển khai consumer v2 có thể đọc v1.
- Đăng ký schema v2.
- Chuyển producer sang v2.
- Xác minh consumer v1/v2 theo compatibility strategy.
- Theo dõi schema rejection và deserialization errors.

Có thể dùng Pulsar broker riêng hoặc Testcontainers trong integration test. Unit test MessageConverter không thay thế kiểm thử schema registry và compatibility ở broker.

## 16. Bài thực hành: chuyển topic orders sang native JSON Schema

Giả sử hệ thống có producer phát OrderCreated và consumer xử lý đơn hàng.

1. Tạo Java record OrderCreated gồm eventId, orderId, total.
2. Viết Supplier hoặc StreamBridge producer phát event.
3. Khởi đầu với framework conversion và contentType application/json.
4. Xác minh message đi qua Pulsar bằng Schema.BYTES.
5. Bật use-native-encoding cho output binding.
6. Đặt schema-type JSON và message-type đúng class OrderCreated.
7. Bật use-native-decoding cho input binding.
8. Đặt schema-type và message-type tương ứng ở consumer.
9. Gửi message và xác minh consumer nhận đúng object.
10. Xem SchemaInfo và schema version của topic orders.
11. Thêm field optional currency vào OrderCreated v2.
12. Kiểm tra schema compatibility trước khi triển khai producer mới.
13. Thử consumer cũ với message v2 và ghi nhận kết quả.
14. Thử custom PulsarHeaderMapper để giữ correlationId nhưng loại bỏ header nhạy cảm.
15. Chạy integration test với broker và ghi lại contract của topic.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Conversion mode | Framework hay native được chọn rõ cho từng binding |
| Producer | use-native-encoding đúng khi dùng Pulsar Schema |
| Consumer | use-native-decoding đúng khi dùng Pulsar Schema |
| Schema type | JSON/AVRO/KeyValue khớp hợp đồng |
| Message type | Fully qualified class đúng |
| SchemaInfo | Có schema và version trên topic khi native schema được dùng |
| Compatibility | Thay đổi schema được broker chấp nhận hoặc từ chối đúng policy |
| Headers | PulsarHeaderMapper map đúng và loại bỏ secret |
| Key/value | Kiểu key/value và encoding thống nhất |
| Configuration precedence | Binding override binder và Boot theo thứ tự |
| Integration test | Producer và consumer thực tế đọc/ghi được dữ liệu |

## Kết luận

Spring Cloud Stream framework conversion và native Pulsar Schema là hai cơ chế khác nhau. Framework conversion mặc định dùng application/json, chuyển payload thành byte[] và Pulsar binder gửi bằng Schema.BYTES. Cơ chế này thuận tiện cho ứng dụng middleware-neutral nhưng không tự đăng ký JSON/Avro schema với Pulsar broker.

Native encoding/decoding chuyển trách nhiệm serialization cho Pulsar Schema. Producer và consumer bật use-native-encoding/use-native-decoding theo binding, đồng thời khai báo schema-type và message-type; với KeyValue có thể khai báo message-key-type và message-value-type. Pulsar quản lý SchemaInfo, schema version và compatibility theo từng topic.

Hãy chọn một representation rõ ràng cho mỗi topic, kiểm tra schema evolution trước khi triển khai producer mới, cấu hình header mapper để kiểm soát metadata và kiểm thử với broker thật. Content type, native schema và headers là ba phần riêng; cần cấu hình và xác minh đúng từng phần để các service có thể trao đổi sự kiện ổn định.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0.4 – Binder for Apache Pulsar](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring for Apache Pulsar – Message Conversion and Pulsar Schema](https://docs.spring.io/spring-pulsar/reference/)
- [Apache Pulsar 5.0 – Schema Overview](https://pulsar.apache.org/docs/5.0.x/schema-overview/)
- [Apache Pulsar 5.0 – Understand Schema and Compatibility](https://pulsar.apache.org/docs/5.0.x/schema-understand/)
- [Apache Pulsar – Manage Schemas](https://pulsar.apache.org/docs/5.0.x/admin-api-schemas/)

