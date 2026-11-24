# Cấu hình schema-type, message-type và kiểu khóa, giá trị

Khi Spring Cloud Stream gửi hoặc nhận message qua Pulsar, ứng dụng cần thống nhất cách chuyển đổi dữ liệu giữa Java object và bytes trên topic. Pulsar hỗ trợ schema có tên và phiên bản như JSON, Avro, Protobuf, primitive và KeyValue. Spring Cloud Stream Pulsar binder cung cấp các thuộc tính mở rộng để khai báo schema cho từng binding: `schema-type`, `message-type`, `message-key-type` và `message-value-type`.

Các thuộc tính này đặc biệt quan trọng khi bật native encoding/decoding. Ở chế độ mặc định, Spring Cloud Stream thường chuyển object thành JSON bytes bằng message converter rồi binder gửi bytes với `Schema.BYTES`; khi đó Pulsar không quản lý schema JSON của object. Nếu muốn broker và client sử dụng Pulsar Schema Registry, producer phải dùng native encoding và consumer phải dùng native decoding, đồng thời hai phía phải thống nhất schema type và kiểu dữ liệu.

## 1. Ba lớp cần phân biệt

Trước khi cấu hình, hãy phân biệt ba khái niệm:

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| `content-type` của Spring Cloud Stream | Framework message converter diễn giải payload như thế nào? | `application/json` |
| Pulsar `schema-type` | Pulsar client dùng schema nào để encode/decode payload? | `JSON`, `AVRO`, `PROTOBUF`, `KEY_VALUE` |
| `message-type` | Java class nào đại diện cho value mà producer/consumer xử lý? | `com.acme.OrderCreated` |

Với message KeyValue, cần xác định thêm kiểu Java của key và value thông qua `message-key-type` và `message-value-type`. Đây là thông tin kiểu dữ liệu cho schema KeyValue; không nên nhầm nó với Pulsar message key dùng cho định tuyến hoặc ordering.

Một schema đúng phải đồng thời phù hợp với payload thực tế, kiểu Java mà function nhận/trả về và schema đã đăng ký trên topic. Chỉ khai báo `content-type: application/json` không có nghĩa topic đã dùng Pulsar JSON schema.

## 2. Hai đường chuyển đổi dữ liệu

Spring Cloud Stream Pulsar binder hỗ trợ hai cách chuyển đổi chính.

### 2.1. Framework message conversion mặc định

Nếu không bật native encoding/decoding, Spring Cloud Stream dùng message conversion của Spring Messaging. Mặc định `content-type` là `application/json`:

- Producer: Java object được message converter serialize thành `byte[]`.
- Binder: gửi byte array tới Pulsar bằng `Schema.BYTES`.
- Consumer: nhận `byte[]` từ Pulsar.
- Framework: dùng message converter để chuyển bytes thành kiểu Java đích.

~~~mermaid
flowchart LR
    A[Java object] --> B[Spring MessageConverter]
    B --> C[JSON bytes]
    C --> D[Pulsar binder]
    D --> E[Schema.BYTES]
    E --> F[(Pulsar topic)]
    F --> G[byte array]
    G --> H[Spring MessageConverter]
    H --> I[Java object]
~~~

Đường này thuận tiện khi ứng dụng cần mô hình message Spring và muốn dùng content type để chọn converter. Tuy nhiên, Pulsar nhìn thấy payload là bytes; schema JSON của object không được đăng ký như Pulsar schema chỉ nhờ content type.

### 2.2. Native encoding/decoding bằng Pulsar Schema

Native encoding yêu cầu Pulsar client serialize object bằng schema của Pulsar. Native decoding yêu cầu Pulsar client deserialize payload thành kiểu dữ liệu đã khai báo:

- Producer binding đặt `use-native-encoding: true`.
- Consumer binding đặt `use-native-decoding: true`.
- Pulsar extended binding khai báo `schema-type` và thông tin Java type tương ứng.

~~~mermaid
flowchart LR
    A[Java object] --> B[Pulsar Schema encoder]
    B --> C[Schema-aware payload]
    C --> D[(Pulsar topic + schema version)]
    D --> E[Pulsar Schema decoder]
    E --> F[Java object]
~~~

Khi dùng native mode, framework message conversion theo `content-type` không còn chịu trách nhiệm encode/decode payload. Schema và kiểu dữ liệu phải được cấu hình tương ứng ở Pulsar binding.

## 3. Vị trí các thuộc tính theo binding

`use-native-encoding` và `use-native-decoding` là thuộc tính chung của Spring Cloud Stream:

~~~text
spring.cloud.stream.bindings.<binding-name>.producer.use-native-encoding
spring.cloud.stream.bindings.<binding-name>.consumer.use-native-decoding
~~~

Các thuộc tính schema của Pulsar binder nằm trong extended binding properties:

~~~text
spring.cloud.stream.pulsar.bindings.<binding-name>.producer.schema-type
spring.cloud.stream.pulsar.bindings.<binding-name>.producer.message-type
spring.cloud.stream.pulsar.bindings.<binding-name>.producer.message-key-type
spring.cloud.stream.pulsar.bindings.<binding-name>.producer.message-value-type

spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.schema-type
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.message-type
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.message-key-type
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.message-value-type
~~~

Trong YAML, các tên Java camelCase được viết theo dạng kebab-case, ví dụ `schema-type`, `message-type`, `message-key-type` và `message-value-type`.

Producer và consumer có thể dùng schema khác nhau nếu function biến đổi kiểu dữ liệu giữa input và output. Tuy nhiên, mỗi binding phải khớp schema của topic mà nó đọc hoặc ghi.

## 4. Ví dụ end-to-end với JSON schema

Giả sử ứng dụng nhận `OrderCreated`, kiểm tra dữ liệu rồi phát `OrderValidated`. Input topic dùng JSON schema và output topic cũng dùng JSON schema.

Java model và function:

Trong dự án, đặt mỗi `public record` vào file riêng có tên tương ứng; đoạn dưới hiển thị hai model cạnh nhau để dễ đọc.

~~~java
package com.acme.orders;

public record OrderCreated(
    String eventId,
    String orderId,
    long amount
) {}

public record OrderValidated(
    String eventId,
    String orderId,
    long amount,
    String status
) {}
~~~

~~~java
package com.acme.orders;

import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return order -> {
            if (order.amount() <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            return new OrderValidated(
                order.eventId(),
                order.orderId(),
                order.amount(),
                "VALIDATED"
            );
        };
    }
}
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          consumer:
            use-native-decoding: true
        validateOrder-out-0:
          destination: orders.validated
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          validateOrder-in-0:
            consumer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
          validateOrder-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.orders.OrderValidated
~~~

Các bước hoạt động:

1. Pulsar consumer đọc record từ `orders.created`.
2. Native decoder dùng JSON schema để tạo `OrderCreated`.
3. Function `validateOrder` nhận object và tạo `OrderValidated`.
4. Native encoder dùng JSON schema của output binding để serialize object.
5. Pulsar producer ghi record vào `orders.validated`.

Tên class trong `message-type` phải là fully qualified class name và class phải có mặt trên classpath. Nếu đổi package hoặc tên class, cần cập nhật cấu hình và đánh giá khả năng tương thích schema; không đổi tên class chỉ để khớp một topic mà chưa kiểm tra dữ liệu hiện có.

## 5. schema-type là gì?

`schema-type` chọn loại schema Pulsar dùng cho payload. Một số loại thường gặp:

| Schema type | Dữ liệu phù hợp | Ghi chú |
|---|---|---|
| `STRING` | Chuỗi UTF-8. | Dùng cho message text đơn giản. |
| `BOOLEAN`, `INT8`, `INT16`, `INT32`, `INT64`, `FLOAT`, `DOUBLE` | Giá trị primitive tương ứng. | Spring for Apache Pulsar có thể suy luận schema cho kiểu Java primitive được hỗ trợ. |
| `BYTES` | `byte[]` hoặc payload nhị phân tự quản lý. | Không cung cấp cấu trúc field để schema registry kiểm tra như JSON/Avro. |
| `JSON` | Object có cấu trúc JSON. | Dễ đọc và phù hợp trao đổi giữa nhiều ngôn ngữ. |
| `AVRO` | Record có schema Avro. | Phù hợp dữ liệu có cấu trúc và schema evolution. |
| `PROTOBUF` | Message theo Protocol Buffers. | Phù hợp contract có định nghĩa `.proto` và code sinh từ schema. |
| `KEY_VALUE` | Một message gồm key schema và value schema. | Cần khai báo kiểu key/value tương ứng. |
| `AUTO_CONSUME` | Consumer đọc schema chưa biết trước thành generic record. | Dành cho luồng đọc nhiều schema hoặc công cụ kiểm tra dữ liệu. |

Danh sách schema và hỗ trợ cụ thể phụ thuộc phiên bản Pulsar client/Spring for Apache Pulsar. Không phải mọi kiểu trong Pulsar đều có thể dùng giống nhau ở cả producer và consumer. `AUTO_CONSUME` là chế độ schema dành cho đọc generic record. `AUTO_PRODUCE_BYTES` là schema strategy phía producer do Spring for Apache Pulsar cung cấp, không phải một giá trị `SchemaType` thông thường để dùng thay cho JSON hoặc Avro trong mọi cấu hình binder.

Với Java primitive, Spring for Apache Pulsar thường tự suy luận schema phù hợp. Với complex type, schema mặc định thường là JSON nếu không có cấu hình hoặc mapping khác. Trong hệ thống production, nên khai báo tường minh schema quan trọng để tránh phụ thuộc suy luận mặc định.

## 6. message-type chỉ định Java type, không phải schema type

`message-type` là tên đầy đủ của Java class mà binder cần chuyển đổi. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          customerEvents-in-0:
            consumer:
              schema-type: AVRO
              message-type: com.acme.customer.CustomerChanged
~~~

Ở đây:

- `AVRO` nói Pulsar dùng định dạng schema Avro.
- `com.acme.customer.CustomerChanged` nói ứng dụng muốn nhận dữ liệu dưới dạng Java type nào.

Hai thông tin phải phù hợp với nhau. Nếu khai báo `schema-type: AVRO` nhưng class không có cấu trúc mà Avro serializer/resolver có thể xử lý, producer có thể thất bại khi tạo schema hoặc serialize.

Không ghi `application/json` vào `message-type`; content type và Java type là hai khái niệm khác nhau. Cũng không ghi tên topic vào `message-type`; topic được khai báo bằng `destination` ở binding.

## 7. Primitive type và complex type

Spring for Apache Pulsar có thể tự suy luận schema cho một số kiểu Java primitive/wrapper như String, Integer, Long, Boolean, Float, Double và byte array. Với object phức tạp, framework thường dùng JSON nếu không có schema được chỉ định.

Ví dụ producer gửi chuỗi:

~~~java
@Bean
Supplier<String> statusSupplier() {
    return () -> "READY";
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: statusSupplier
    stream:
      bindings:
        statusSupplier-out-0:
          destination: system.status
          producer:
            use-native-encoding: true
~~~

Với kiểu primitive được hỗ trợ, schema có thể được suy luận từ generic type của Supplier. Nếu muốn cấu hình rõ ràng hoặc cần interoperability với client khác, có thể đặt `schema-type: STRING` cho producer và consumer tương ứng.

Ví dụ complex type:

~~~java
package com.acme;

record CustomerChanged(String customerId, String email) {}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: customerChanged
    stream:
      bindings:
        customerChanged-out-0:
          destination: customer.events
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          customerChanged-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.CustomerChanged
~~~

Nếu không khai báo schema type cho complex type, Spring for Apache Pulsar có thể suy luận JSON theo mặc định. Tuy nhiên, khi topic đã có schema khác, producer phải dùng schema tương thích với topic thay vì dựa vào default.

## 8. Khi message có cả key và value

Pulsar hỗ trợ schema `KEY_VALUE` để mô tả một cặp key/value có kiểu. Trong Spring Cloud Stream Pulsar binder, có thể chỉ định:

- `schema-type: KEY_VALUE` để chọn schema tổng thể.
- `message-key-type` để chỉ định Java type của key.
- `message-value-type` để chỉ định Java type của value.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderState-out-0:
          destination: orders.state
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          orderState-out-0:
            producer:
              schema-type: KEY_VALUE
              message-key-type: java.lang.String
              message-value-type: com.acme.orders.OrderState
~~~

Trong ví dụ, key là String và value là OrderState. Kiểu value phải có schema mapping phù hợp, ví dụ JSON hoặc Avro theo cấu hình và phiên bản Spring Pulsar đang dùng. Nếu cần schema cụ thể cho từng phần của cặp KeyValue, hãy cấu hình schema resolver/type mapping hoặc customizer phù hợp thay vì giả định một thuộc tính `message-type` duy nhất đủ mô tả cả hai.

### 8.1. Phân biệt KeyValue schema với Pulsar message key

Hai khái niệm dễ nhầm:

| Khái niệm | Ý nghĩa |
|---|---|
| Pulsar message key | Metadata key gắn với message, có thể dùng cho routing, ordering hoặc compaction tùy cấu hình topic/subscription. |
| `Schema.KEY_VALUE` | Cấu trúc payload có schema riêng cho key và value. |
| `message-key-type` | Java type cho key component khi schema type là KEY_VALUE. |
| `message-value-type` | Java type cho value component khi schema type là KEY_VALUE. |

Nếu chỉ cần đặt Pulsar message key để định tuyến mà payload vẫn là một object thông thường, không nhất thiết phải dùng `Schema.KEY_VALUE`. Ngược lại, nếu payload là một cặp key/value có schema, phải cấu hình đúng KeyValue schema và kiểu của từng thành phần.

### 8.2. Encoding của KeyValue

Pulsar định nghĩa hai kiểu encoding phổ biến cho KeyValue:

- `INLINE`: key và value được encode cùng trong payload theo KeyValue schema.
- `SEPARATED`: key được lưu trong message key metadata, value nằm trong payload.

Tài liệu Spring for Apache Pulsar hiện mô tả hỗ trợ complex `KEY_VALUE` với INLINE encoding. Nếu hệ thống cần SEPARATED encoding, hãy xác minh khả năng của đúng phiên bản binder/client hoặc dùng Pulsar client API phù hợp; không mặc định cấu hình binder hỗ trợ mọi biến thể KeyValue.

## 9. Cấu hình consumer phải khớp producer

Producer và consumer cần thống nhất schema type và message type. Ví dụ producer ghi JSON:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.events
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          orderEvents-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
~~~

Consumer tương ứng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderProjection-in-0:
          destination: orders.events
          consumer:
            use-native-decoding: true
      pulsar:
        bindings:
          orderProjection-in-0:
            consumer:
              schema-type: JSON
              message-type: com.acme.orders.OrderCreated
~~~

Nếu producer dùng Avro nhưng consumer khai báo JSON, client có thể không giải mã được payload hoặc schema registry từ chối subscription. Cùng tên Java class cũng không đủ nếu schema thực tế đã thay đổi không tương thích.

Với nhiều consumer dùng các ngôn ngữ khác nhau, không cần mọi consumer có cùng Java class; điều cần thiết là schema của mỗi consumer có thể đọc các phiên bản message mà producer phát ra theo compatibility strategy của topic.

## 10. Native encoding/decoding và content-type

Khi bật native encoding/decoding, không dùng `content-type` như cách chọn serializer cho payload. Pulsar schema được chọn bởi `schema-type` và type information của binding.

| Cấu hình | Producer | Consumer |
|---|---|---|
| Mặc định framework conversion | Spring converter tạo bytes, binder dùng `Schema.BYTES`. | Binder nhận bytes, Spring converter tạo Java object. |
| Native mode | Pulsar Schema serialize Java object. | Pulsar Schema deserialize thành Java object. |
| `content-type` | Ảnh hưởng framework message converter khi converter được dùng. | Ảnh hưởng framework message converter khi converter được dùng. |
| `schema-type` | Chọn Pulsar schema để ghi. | Chọn Pulsar schema để đọc. |
| `message-type` | Kiểu Java object cần serialize. | Kiểu Java object cần deserialize. |

Hai phía có thể chọn native mode độc lập theo binding, nhưng payload phải tương thích với cách phía bên kia đọc. Trong một pipeline Pulsar schema-aware, thường bật native encoding ở output và native decoding ở input tương ứng.

Native mode cũng ảnh hưởng việc chuyển header. Không nên kỳ vọng embedded Spring headers được gắn vào payload theo cùng cách khi framework converter không còn serialize message envelope. Pulsar có message properties/metadata riêng và binder có cơ chế header mapper.

## 11. Header không phải schema của payload

Pulsar message có metadata và user properties để mang thông tin như correlation ID, event source hoặc tenant. Binder chuyển đổi header giữa Pulsar message và Spring Message thông qua `PulsarHeaderMapper`.

Header mapper mặc định có thể được thay thế bằng bean `PulsarHeaderMapper` nếu cần lọc hoặc chuyển đổi header đặc biệt. Ví dụ:

~~~java
@Bean
PulsarHeaderMapper customPulsarHeaderMapper() {
    return JsonPulsarHeaderMapper.builder()
        .inboundPatterns("!secret", "*")
        .outboundPatterns("!password", "!token", "*")
        .trustedPackages("com.acme")
        .build();
}
~~~

Schema type mô tả cấu trúc payload; header mapper mô tả cách chuyển metadata. Không đưa mọi trường nghiệp vụ vào header chỉ để tránh schema. Các trường cần kiểm tra tương thích và được consumer xử lý nên nằm trong payload schema.

## 12. Custom schema mapping khi không muốn lặp schema-type

Spring for Apache Pulsar cho phép ánh xạ Java type sang Pulsar schema. Khi có mapping, framework có thể tìm schema dựa trên message type; binder docs cũng nêu custom schema mapping được xem xét khi không khai báo `schema-type`.

Ví dụ cấu hình mapping:

~~~yaml
spring:
  pulsar:
    defaults:
      type-mappings:
        - message-type: com.acme.orders.OrderCreated
          schema-info:
            schema-type: JSON
        - message-type: com.acme.orders.OrderValidated
          schema-info:
            schema-type: AVRO
~~~

Có thể khai báo mapping bằng `SchemaResolverCustomizer` khi cần logic phức tạp hơn:

~~~java
@Bean
SchemaResolverCustomizer<DefaultSchemaResolver> orderSchemaMappings() {
    return resolver -> {
        resolver.addCustomSchemaMapping(
            OrderCreated.class,
            Schema.JSON(OrderCreated.class)
        );
        resolver.addCustomSchemaMapping(
            OrderValidated.class,
            Schema.AVRO(OrderValidated.class)
        );
    };
}
~~~

Một lựa chọn khác là đánh dấu class bằng `@PulsarMessage(schemaType = SchemaType.JSON)` để đặt schema mặc định cho message type. Cách này phù hợp khi class thuộc ứng dụng và luôn có cùng schema mặc định ở các binding.

Custom mapping giúp tránh lặp cấu hình, nhưng cần tránh một class bị ánh xạ sang nhiều schema khác nhau tùy topic mà không có quy tắc rõ ràng. Nếu hai binding dùng schema khác nhau cho cùng Java type, cấu hình tường minh theo binding thường dễ kiểm soát hơn.

## 13. Phạm vi và độ ưu tiên của cấu hình Pulsar

Pulsar binder kế thừa Spring Boot auto-configuration của Spring for Apache Pulsar. Có ba cấp cấu hình:

1. Spring Boot properties, ví dụ `spring.pulsar.producer.*` và `spring.pulsar.consumer.*`.
2. Binder-level properties, ví dụ `spring.cloud.stream.pulsar.binder.producer.*` và `spring.cloud.stream.pulsar.binder.consumer.*`.
3. Extended binding properties, ví dụ `spring.cloud.stream.pulsar.bindings.<binding-name>.producer.*` và `.consumer.*`.

Độ ưu tiên từ cao xuống thấp:

| Mức | Phạm vi |
|---|---|
| Extended binding properties | Chỉ binding được chỉ định. |
| Binder properties | Các binding thuộc binder trong ứng dụng. |
| Spring Boot properties | Cấu hình nền cho ứng dụng. |

Ví dụ, hai output binding cần schema khác nhau:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        customerJson-out-0:
          destination: customer.events.json
          producer:
            use-native-encoding: true
        customerAvro-out-0:
          destination: customer.events.avro
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          customerJson-out-0:
            producer:
              schema-type: JSON
              message-type: com.acme.CustomerChanged
          customerAvro-out-0:
            producer:
              schema-type: AVRO
              message-type: com.acme.CustomerChanged
~~~

Ở đây cùng Java type được phát theo hai schema ở hai topic khác nhau. Chỉ làm vậy khi hai contract được quản lý rõ ràng; không gửi hai schema khác nhau vào cùng topic nếu không có compatibility strategy và consumer hỗ trợ tương ứng.

## 14. Schema Registry và schema version

Pulsar lưu SchemaInfo và version của schema theo topic. Khi producer đăng ký schema mới, broker kiểm tra tương thích theo strategy đang cấu hình. Message được ghi kèm thông tin version để consumer có thể lấy schema tương ứng khi deserialize.

Schema registry giúp:

- Xác định cấu trúc dữ liệu đã được đăng ký cho topic.
- Theo dõi các phiên bản schema.
- Kiểm tra một schema mới có tương thích với schema hiện tại hay không.
- Cho consumer đọc message được tạo từ schema version phù hợp.

`schema-type` chỉ chọn họ schema như JSON/Avro; nó không phải version number. `message-type` chỉ chọn Java class; nó không thay thế việc quản lý schema version ở broker.

### 14.1. Các compatibility strategy

Pulsar hỗ trợ nhiều strategy, trong đó các lựa chọn phổ biến:

| Strategy | Ý nghĩa | Cách triển khai thường gặp |
|---|---|---|
| `BACKWARD` | Consumer dùng schema mới đọc được dữ liệu được ghi bằng schema trước liền kề. | Thường thêm field optional hoặc xóa field theo quy tắc schema. |
| `BACKWARD_TRANSITIVE` | Consumer mới đọc được dữ liệu của tất cả schema cũ. | Dùng khi cần tương thích với toàn bộ lịch sử dữ liệu. |
| `FORWARD` | Consumer cũ đọc được dữ liệu do producer mới ghi. | Cần giữ consumer cũ tương thích với field mới. |
| `FORWARD_TRANSITIVE` | Consumer cũ đọc được dữ liệu của mọi schema mới hơn. | Dùng khi nhiều thế hệ producer/consumer cùng tồn tại. |
| `FULL` | Tương thích cả backward và forward với phiên bản liền kề. | Phù hợp rolling upgrade khi thay đổi schema có thể tương thích hai chiều. |
| `FULL_TRANSITIVE` | Tương thích hai chiều với mọi phiên bản trước. | Dùng khi yêu cầu tương thích toàn bộ lịch sử cao. |
| `ALWAYS_COMPATIBLE` | Không từ chối thay đổi schema vì compatibility check. | Chỉ dùng khi có cơ chế kiểm soát contract khác. |
| `ALWAYS_INCOMPATIBLE` | Không cho phép schema evolution. | Khi muốn cố định contract hoặc yêu cầu quy trình thay topic/version riêng. |

Các thay đổi được cho phép phụ thuộc schema type và compatibility checker. Với JSON và Avro, cấu hình broker mặc định thường dùng FULL; các schema type khác có thể mặc định ALWAYS_INCOMPATIBLE. Hãy kiểm tra broker configuration thực tế thay vì dựa vào một giá trị mặc định chung cho mọi cluster.

### 14.2. Ví dụ tiến hóa schema an toàn

Schema V1:

~~~json
{
  "eventId": "evt-100",
  "orderId": "order-9001",
  "amount": 125000
}
~~~

Schema V2 bổ sung trường optional:

~~~json
{
  "eventId": "evt-100",
  "orderId": "order-9001",
  "amount": 125000,
  "source": "MOBILE"
}
~~~

Nếu schema và compatibility strategy cho phép, consumer V1 có thể bỏ qua trường mới và consumer V2 có thể xử lý dữ liệu cũ bằng default/null phù hợp. Khi thay đổi kiểu của `amount` từ số sang chuỗi hoặc đổi ý nghĩa field mà không đổi tên, compatibility checker có thể từ chối hoặc consumer cũ có thể hiểu sai dữ liệu.

Không xóa field bắt buộc hoặc đổi type chỉ vì Java code mới compile. Hãy kiểm tra schema compatibility, thứ tự rollout producer/consumer và dữ liệu lịch sử.

## 15. KeyValue schema và tiến hóa riêng của key/value

Với `KEY_VALUE`, schema tổng thể bao gồm schema key và schema value. Cần quản lý thay đổi của cả hai thành phần:

- Key thường được dùng để định danh entity, routing hoặc compaction. Thay đổi key type có thể làm thay đổi cách consumer tìm hoặc nhóm record.
- Value thường mang nội dung nghiệp vụ và có thể tiến hóa field theo compatibility strategy.
- Schema version của KeyValue đại diện cho cấu trúc cặp; khi thay schema của key hoặc value, cần kiểm tra khả năng tương thích tổng thể.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        accountState-out-0:
          destination: account.state
          producer:
            use-native-encoding: true
      pulsar:
        bindings:
          accountState-out-0:
            producer:
              schema-type: KEY_VALUE
              message-key-type: java.lang.String
              message-value-type: com.acme.AccountState
~~~

Nếu key là accountId, giữ kiểu String ổn định qua các phiên bản thường dễ tương thích hơn việc đổi sang một class phức tạp. Value có thể tiến hóa theo schema strategy đã chọn.

## 16. AUTO_CONSUME và generic record

Khi consumer không biết trước class của schema hoặc topic có thể chứa nhiều schema version, Pulsar hỗ trợ `AUTO_CONSUME`. Consumer nhận `GenericRecord` và đọc field theo schema thực tế gắn với message.

Ví dụ cấu hình consumer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        auditReader-in-0:
          destination: audit.events
          consumer:
            use-native-decoding: true
      pulsar:
        bindings:
          auditReader-in-0:
            consumer:
              schema-type: AUTO_CONSUME
~~~

Ví dụ function nhận generic record:

~~~java
@Bean
Consumer<GenericRecord> auditReader() {
    return record -> record.getFields().forEach((field) ->
        log.info("{}={}", field.getName(), record.getField(field))
    );
}
~~~

GenericRecord hữu ích cho schema inspection, data migration hoặc công cụ audit. Với business service, kiểu Java cụ thể thường dễ kiểm tra compile-time hơn. Nếu dùng generic record, phải xử lý trường có thể thiếu, type khác nhau giữa schema version và dữ liệu null.

## 17. AUTO_PRODUCE_BYTES và raw payload

Nếu producer chỉ có raw JSON/Avro bytes và không muốn deserialize thành Java object trước khi gửi, Spring for Apache Pulsar hỗ trợ `AUTO_PRODUCE_BYTES` trong các trường hợp phù hợp. Producer gửi `byte[]`, Pulsar kiểm tra bytes tương thích với schema của topic.

Đây là lựa chọn nâng cao, không phải cách thay thế schema cho mọi loại payload. Theo Spring Pulsar docs, hỗ trợ AUTO_PRODUCE_BYTES tập trung vào JSON và Avro. Cần xác minh binder version có expose schema type này theo đúng cách ứng dụng cần dùng.

Không gửi raw bytes tùy ý vào topic có schema rồi kỳ vọng broker tự nhận biết nội dung. Producer phải cung cấp đúng bytes và schema target; nếu không, validation/serialization có thể thất bại hoặc dữ liệu không thể đọc được.

## 18. Lỗi thường gặp khi cấu hình schema

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Consumer nhận byte[] thay vì Java object. | Đang dùng framework conversion hoặc native decoding chưa bật. | Kiểm tra `use-native-decoding` và `schema-type`. |
| Producer gửi được nhưng topic không có JSON schema như mong đợi. | Framework converter đã tạo JSON bytes nhưng binder dùng `Schema.BYTES`. | Bật `use-native-encoding` và cấu hình Pulsar `schema-type: JSON`. |
| `SchemaSerializationException` hoặc lỗi tạo schema. | `message-type` sai, class không hỗ trợ schema hoặc schema không khớp. | Kiểm tra FQN, classpath, schema resolver và model. |
| Consumer không deserialize được message. | Producer/consumer dùng schema type hoặc message type không tương thích. | So sánh schema topic, binding properties và schema version. |
| Broker từ chối đăng ký schema mới. | Schema mới không tương thích theo strategy. | Kiểm tra field/type change và compatibility strategy. |
| KeyValue schema không khởi tạo được. | Thiếu `message-key-type` hoặc value schema mapping. | Khai báo key/value types và schema resolver tương ứng. |
| Producer và consumer xử lý key khác nhau. | Nhầm Pulsar message key với KeyValue schema component. | Xác định có cần message metadata key hay `Schema.KEY_VALUE`. |
| Java class thay đổi package khiến consumer lỗi. | `message-type` vẫn trỏ class cũ hoặc schema mapping chưa cập nhật. | Đồng bộ cấu hình và đánh giá schema compatibility. |
| AUTO_CONSUME trả generic record nhưng code cast sai. | Consumer giả định schema cố định. | Đọc field và type từ GenericRecord theo schema thực tế. |
| Header bị mất hoặc không map được. | Nhầm header mapper với schema payload hoặc mapper filter loại header. | Kiểm tra PulsarHeaderMapper và metadata properties. |

## 19. Kiểm thử schema producer và consumer

Test Binder có thể kiểm thử function logic và Spring Message conversion, nhưng không chứng minh Pulsar Schema Registry đã đăng ký đúng schema hoặc broker chấp nhận schema evolution. Cần integration test với Pulsar broker phù hợp.

Các kịch bản nên có:

1. Producer native JSON gửi record; consumer native JSON nhận đúng object và field.
2. Producer Avro gửi schema; consumer Avro giải mã đúng phiên bản.
3. Consumer dùng schema type không tương thích; kiểm tra lỗi xuất hiện rõ ràng khi subscribe/deserialize.
4. Gửi schema V2 tương thích; xác minh consumer V1/V2 theo strategy đã chọn.
5. Gửi schema V2 không tương thích; xác minh broker từ chối đăng ký theo policy.
6. Gửi message KeyValue; kiểm tra key type, value type và encoding.
7. Đọc topic bằng AUTO_CONSUME; xác minh GenericRecord có field/type đúng.
8. Producer gửi raw bytes với AUTO_PRODUCE_BYTES; xác minh bytes được kiểm tra với schema topic.
9. Kiểm tra framework conversion mặc định để xác nhận payload dùng Schema.BYTES.
10. Kiểm tra headers qua PulsarHeaderMapper, bao gồm header bị lọc và header nhạy cảm.

Khi test schema evolution, nên lưu lại schema version và compatibility strategy đã dùng để kết quả có thể tái lập. Không chỉ assert object Java cuối cùng; hãy xác minh schema đã đăng ký trên topic và consumer thực sự dùng native decoding.

## 20. Quy trình chọn schema-type và message-type

1. Xác định payload là primitive, object có cấu trúc, raw bytes hay cặp key/value.
2. Quyết định dùng Spring framework conversion hay Pulsar native schema.
3. Nếu dùng framework conversion, khai báo `content-type` phù hợp và hiểu rằng binder mặc định có thể gửi `Schema.BYTES`.
4. Nếu dùng native mode, bật `use-native-encoding` ở producer và `use-native-decoding` ở consumer tương ứng.
5. Chọn `schema-type` phù hợp với contract: JSON, AVRO, PROTOBUF, primitive hoặc KEY_VALUE.
6. Với complex type, khai báo `message-type` bằng fully qualified class name.
7. Với KEY_VALUE, khai báo `message-key-type` và `message-value-type`; xác định rõ inline/separated encoding theo hỗ trợ của phiên bản.
8. Đảm bảo producer schema tương thích với schema topic và consumer.
9. Chọn schema compatibility strategy và quy trình rollout producer/consumer.
10. Nếu nhiều binding dùng schema khác nhau, đặt extended binding properties thay vì cấu hình chung toàn ứng dụng.
11. Dùng custom schema mapping khi cần tránh lặp cấu hình, nhưng giữ mapping nhất quán theo Java type.
12. Integration test schema registration, serialization, deserialization, versioning, header và lỗi không tương thích.

## 21. Checklist production

- [ ] Mỗi binding có quyết định rõ framework conversion hay native encoding/decoding.
- [ ] Producer và consumer tương ứng dùng cách encode/decode tương thích.
- [ ] `schema-type` khớp schema đã đăng ký trên topic.
- [ ] `message-type` là FQN của Java type có trên classpath.
- [ ] Với KEY_VALUE, key type và value type được khai báo đầy đủ.
- [ ] Không nhầm Pulsar message key metadata với KeyValue payload schema.
- [ ] Schema compatibility strategy được chọn có chủ đích.
- [ ] Thay đổi schema đã được kiểm thử với dữ liệu và consumer version cũ.
- [ ] Custom type mappings không xung đột giữa các binding.
- [ ] Header mapper không đưa secret hoặc dữ liệu nhạy cảm vào metadata.
- [ ] Có integration test với Pulsar broker, không chỉ Test Binder.
- [ ] Có quy trình theo dõi schema registration failure và deserialization error.

Schema type xác định định dạng dữ liệu mà Pulsar hiểu; message type xác định Java object mà ứng dụng xử lý; key/value type bổ sung cấu trúc cho message dạng cặp. Khi ba lớp này khớp với native encoding/decoding, schema trên topic và compatibility strategy, Spring Cloud Stream Pulsar binder có thể trao đổi message có cấu trúc giữa nhiều service mà vẫn kiểm soát được thay đổi contract theo thời gian.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0 – Binder for Apache Pulsar](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring for Apache Pulsar – Message Production and Schema Information](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-production.html)
- [Spring for Apache Pulsar – Message Consumption and Schema Information](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Spring for Apache Pulsar – SchemaResolver API](https://docs.spring.io/spring-pulsar/docs/1.2.x/api/org/springframework/pulsar/core/SchemaResolver.html)
- [Apache Pulsar – Schema Evolution and Compatibility](https://pulsar.apache.org/docs/4.2.x/schema-evolution-compatibility/)
- [Apache Pulsar – KeyValue Schema](https://pulsar.apache.org/docs/4.2.x/schema-understand/)
