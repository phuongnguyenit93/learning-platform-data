# Cấu hình useNativeEncoding và useNativeDecoding

Spring Cloud Stream có thể chuyển đổi payload Java thành dữ liệu truyền qua broker bằng message converter của framework, hoặc giao việc tuần tự hóa cho cơ chế native của binder. Hai thuộc tính `useNativeEncoding` và `useNativeDecoding` điều khiển lựa chọn đó ở hai chiều độc lập:

- `useNativeEncoding` nằm trên output binding, quyết định cách payload được tuần tự hóa trước khi gửi.
- `useNativeDecoding` nằm trên input binding, quyết định cách dữ liệu nhận từ broker được giải mã thành đối tượng ứng dụng.

Khi để mặc định, Spring Cloud Stream thường dùng message conversion dựa trên content type. Khi bật native encoding hoặc decoding, binder và thư viện client của broker đảm nhiệm phần serialization hoặc deserialization tương ứng. Lựa chọn này hữu ích khi cần dùng Kafka Serializer/Deserializer, schema native hoặc định dạng dữ liệu đặc thù của broker. Tuy nhiên, producer và consumer phải thống nhất wire format; nếu cấu hình hai phía không tương thích, message có thể gửi thành công nhưng consumer không giải mã được.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt message conversion của Spring Cloud Stream với native serialization của binder.
- Cấu hình `useNativeEncoding` trên output binding và `useNativeDecoding` trên input binding.
- Chọn serializer/deserializer phù hợp khi dùng Kafka binder.
- Hiểu vai trò của content type khi bật hoặc tắt native encoding/decoding.
- Đánh giá khả năng hỗ trợ native serialization của Kafka, RabbitMQ và Pulsar binder.
- Kết hợp producer và consumer theo wire format tương thích.
- Kiểm thử payload sau khi đi qua broker và xử lý lỗi serialization/deserialization.

## 1. Hai cơ chế chuyển đổi dữ liệu

Một function Spring Cloud Stream làm việc với kiểu Java, ví dụ `OrderCreated`. Broker cần nhận dữ liệu theo định dạng truyền tải cụ thể như JSON bytes, Avro bytes hoặc một định dạng nhị phân khác. Quá trình chuyển đổi giữa đối tượng Java và dữ liệu truyền tải được gọi là serialization/deserialization hoặc message conversion, tùy tầng thực hiện.

Spring Cloud Stream cung cấp message conversion ở cấp framework. Binder cũng có thể sử dụng cơ chế serialization native của broker hoặc client thư viện.

### Message conversion của Spring Cloud Stream

Khi không bật native encoding/decoding, framework dùng message converter để chuyển đổi payload dựa trên kiểu dữ liệu và content type.

Ví dụ, output binding nhận một object `OrderCreated` và có `contentType: application/json`. Converter phù hợp có thể tuần tự hóa object thành JSON bytes. Ở phía consumer, converter đọc payload JSON và tạo lại object Java theo kiểu đầu vào của function.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          contentType: application/json
        inventory-in-0:
          destination: orders
          group: inventory
          contentType: application/json
~~~

Đây là cách tiếp cận phổ biến khi ứng dụng muốn dùng cùng cơ chế chuyển đổi của Spring Cloud Stream và không cần cấu hình serializer riêng cho từng broker.

### Native encoding và native decoding

Khi bật `useNativeEncoding: true`, output binding yêu cầu binder dùng cơ chế native để tuần tự hóa payload. Framework không thực hiện message conversion outbound theo cách thông thường.

Khi bật `useNativeDecoding: true`, input binding yêu cầu binder dùng cơ chế native để giải mã dữ liệu nhận được. Framework không thực hiện inbound message conversion theo cách thông thường.

| Thuộc tính | Binding | Hướng dữ liệu | Tác động |
|---|---|---|---|
| `useNativeEncoding` | Output | Ứng dụng → broker | Dùng serializer/cơ chế native của binder |
| `useNativeDecoding` | Input | Broker → ứng dụng | Dùng deserializer/cơ chế native của binder |

Hai thuộc tính độc lập. Một ứng dụng có thể bật native encoding ở output binding nhưng vẫn dùng message converter ở input binding, hoặc ngược lại. Điều quan trọng là dữ liệu trên wire phải tương thích với cách phía nhận giải mã.

## 2. Luồng xử lý khi bật và tắt native mode

Luồng outbound khi dùng message converter:

1. Function hoặc service tạo payload Java.
2. Output binding xác định content type và message converter.
3. Converter chuyển payload thành bytes.
4. Binder gửi bytes cùng metadata cần thiết tới broker.

Luồng outbound khi bật native encoding:

1. Function hoặc service tạo payload Java.
2. Output binding chuyển payload cho binder.
3. Serializer native do binder/client cấu hình tạo dữ liệu truyền tải.
4. Broker nhận dữ liệu đã serialize cùng metadata native.

Luồng inbound khi dùng message converter:

1. Binder nhận bytes từ broker.
2. Binder tạo Spring Message và metadata tương ứng.
3. Message converter dùng content type để chuyển bytes thành payload Java.
4. Function hoặc Consumer nhận dữ liệu.

Luồng inbound khi bật native decoding:

1. Binder nhận dữ liệu từ broker.
2. Deserializer native chuyển dữ liệu thành kiểu Java mà ứng dụng mong đợi.
3. Binder chuyển payload đã giải mã vào input binding.
4. Function hoặc Consumer nhận dữ liệu.

~~~mermaid
flowchart TD
    A["Payload Java ở producer"] --> B{"useNativeEncoding?"}
    B -->|false| C["Spring MessageConverter"]
    B -->|true| D["Native serializer của binder"]
    C --> E["Bytes trên broker"]
    D --> E
    E --> F["Binder nhận message"]
    F --> G{"useNativeDecoding?"}
    G -->|false| H["Spring MessageConverter"]
    G -->|true| I["Native deserializer của binder"]
    H --> J["Payload Java ở consumer"]
    I --> J
~~~

Trong cả hai đường đi, binder vẫn quản lý kết nối, destination, group và giao nhận message. Native mode chỉ thay đổi tầng tuần tự hóa hoặc giải mã dữ liệu; nó không tự thay đổi consumer group, partition, retry hay chính sách lưu giữ của broker.

## 3. Cấu hình useNativeEncoding trên output binding

Thuộc tính `useNativeEncoding` được đặt trong phần `producer` của binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          producer:
            useNativeEncoding: true
~~~

Khi bật, binder sẽ sử dụng serializer hoặc cơ chế native được cấu hình cho binding đó. Với Kafka, điều này thường có nghĩa là cấu hình Kafka producer serializer cho key và value.

Ví dụ function phát sự kiện:

~~~java
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderSourceConfiguration {

    @Bean
    Supplier<OrderCreated> orderSource(OrderEventSource source) {
        return source::pollNextPendingEvent;
    }
}
~~~

Binding `orderSource-out-0` có thể được cấu hình native encoding. Khi dùng Supplier, mỗi lần poller lấy được một object, binder sẽ áp dụng serializer đã chọn để gửi payload.

Có thể bật native encoding cho một output binding và giữ message conversion mặc định cho binding khác. Không cần bật cho toàn ứng dụng nếu chỉ một luồng cần serializer đặc thù.

## 4. Cấu hình useNativeDecoding trên input binding

Thuộc tính `useNativeDecoding` được đặt trong phần `consumer` của binding:

~~~yaml
spring:
  cloud:
    stream:
      function:
        definition: inventory
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
          consumer:
            useNativeDecoding: true
~~~

Khi bật, binder sử dụng deserializer native để tạo payload Java. Kiểu dữ liệu mà deserializer trả về phải phù hợp với chữ ký function.

Ví dụ consumer:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InventoryConfiguration {

    @Bean
    Consumer<OrderCreated> inventory() {
        return event -> {
            System.out.println("Đơn hàng: " + event.orderId());
        };
    }
}
~~~

Nếu deserializer trả về `byte[]` nhưng function yêu cầu `OrderCreated`, consumer sẽ không nhận được kiểu dữ liệu mong đợi. Cần cấu hình deserializer để tạo đúng đối tượng, hoặc thiết kế function nhận byte array và tự giải mã theo hợp đồng.

## 5. Ví dụ Kafka: dùng serializer và deserializer native

Kafka lưu record value và key dưới dạng byte array. Kafka producer dùng serializer để chuyển object thành bytes; consumer dùng deserializer để chuyển bytes trở lại kiểu ứng dụng.

Với Kafka binder, native encoding/decoding thường được dùng khi cần kiểm soát serializer/deserializer ở tầng Kafka. Có thể cấu hình serializer và deserializer theo binding thông qua namespace Kafka binder.

Giả sử producer gửi `OrderCreated` dưới dạng JSON bằng `JsonSerializer`, consumer giải mã bằng `JsonDeserializer`.

### Producer configuration

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          producer:
            useNativeEncoding: true
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
                value.serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

Ở đây:

- `useNativeEncoding: true` yêu cầu Kafka binder dùng serializer native.
- `StringSerializer` tuần tự hóa record key nếu ứng dụng có key dạng chuỗi.
- `JsonSerializer` tuần tự hóa value object thành JSON bytes.

Nếu không cần key, cấu hình key serializer có thể được điều chỉnh theo kiểu key và chính sách producer của ứng dụng.

### Consumer configuration

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
          consumer:
            useNativeDecoding: true
      kafka:
        bindings:
          inventory-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
                spring.json.value.default.type: com.example.events.OrderCreated
                spring.json.trusted.packages: com.example.events
~~~

Ở phía consumer:

- `useNativeDecoding: true` yêu cầu binder dùng Kafka deserializer.
- `StringDeserializer` giải mã record key thành chuỗi.
- `JsonDeserializer` giải mã value thành `OrderCreated`.
- `spring.json.value.default.type` xác định kiểu đích mặc định nếu cấu hình serializer/deserializer cần thông tin kiểu.
- `spring.json.trusted.packages` giới hạn package được phép giải mã theo cấu hình Spring Kafka.

Tên package và class trong ví dụ cần được thay bằng kiểu dữ liệu thực tế của ứng dụng. Chỉ tin cậy package chứa các DTO đã kiểm soát; không mở rộng danh sách trusted packages cho mọi package chỉ để bỏ qua lỗi giải mã.

### Hợp đồng giữa producer và consumer

Producer và consumer cần thống nhất:

- Kiểu dữ liệu của record key.
- Kiểu dữ liệu của record value.
- Serializer và deserializer tương ứng.
- Cấu trúc JSON và quy tắc tương thích schema.
- Cách xử lý metadata kiểu do serializer tạo ra.
- Phiên bản thư viện serializer/deserializer đang dùng.

Nếu producer dùng `JsonSerializer` còn consumer dùng `StringDeserializer` cho value, consumer sẽ nhận chuỗi JSON thay vì `OrderCreated`. Điều đó chỉ phù hợp nếu function nhận chuỗi và tự parse. Nếu function nhận `OrderCreated`, cần dùng deserializer tương thích.

## 6. Content type khi dùng native mode

Content type và native encoding/decoding có liên quan nhưng không thay thế nhau.

- `contentType` mô tả định dạng payload và hỗ trợ message conversion của Spring Cloud Stream.
- `useNativeEncoding` yêu cầu binder sử dụng cơ chế serialize native cho outbound.
- `useNativeDecoding` yêu cầu binder sử dụng cơ chế deserialize native cho inbound.

Khi native mode được bật ở một chiều, không nên mặc định rằng Spring Cloud Stream vẫn dùng content type để chuyển đổi payload ở chiều đó. Serializer/deserializer native phải biết cách xử lý kiểu dữ liệu và wire format.

Ví dụ, Kafka `JsonSerializer` tạo JSON bytes. Consumer có thể giải mã bằng Kafka `JsonDeserializer` hoặc nhận byte/string rồi dùng một bước chuyển đổi riêng. Chỉ đặt `contentType: application/json` không tự cấu hình Kafka serializer/deserializer khi native encoding/decoding đã được bật.

Khi không dùng native mode, content type thường là thông tin quan trọng để framework chọn converter. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          contentType: application/json
        inventory-in-0:
          destination: orders
          group: inventory
          contentType: application/json
~~~

Nếu producer dùng native encoding và consumer dùng message converter, sự kết hợp vẫn có thể hoạt động khi native serializer tạo ra đúng wire format mà converter phía nhận có thể giải mã theo content type. Ngược lại, producer dùng message converter và consumer dùng native decoding cũng có thể hoạt động nếu deserializer hiểu chính xác bytes được tạo ra. Những kết hợp này cần kiểm thử tích hợp, không nên suy đoán từ tên content type.

## 7. Kết hợp native encoding và decoding

Hai thuộc tính được cấu hình độc lập ở từng binding. Bảng sau mô tả cách suy nghĩ về các tổ hợp:

| Producer | Consumer | Điều kiện |
|---|---|---|
| Native encoding tắt | Native decoding tắt | Spring Cloud Stream converter hai phía phải thống nhất content type |
| Native encoding bật | Native decoding bật | Serializer và deserializer native phải tương thích về wire format và kiểu dữ liệu |
| Native encoding bật | Native decoding tắt | Bytes do native serializer tạo ra phải được converter phía nhận giải mã đúng |
| Native encoding tắt | Native decoding bật | Bytes do framework converter tạo ra phải tương thích với deserializer native |

Trong một hệ thống mới, thường dễ kiểm soát nhất khi hai phía dùng cùng một chiến lược serialization. Nếu cần kết nối một producer ngoài Spring với consumer Spring Cloud Stream, native mode có thể giúp tích hợp trực tiếp với serializer/deserializer mà producer ngoài đang dùng.

Không nhất thiết mọi binding trong ứng dụng đều dùng cùng chế độ. Ví dụ, một output binding Kafka có thể dùng Avro serializer trong khi một input binding khác vẫn dùng JSON message converter. Cấu hình theo binding giúp mỗi luồng có hợp đồng dữ liệu riêng.

## 8. Native encoding và decoding với RabbitMQ và Pulsar

Ý nghĩa chung của hai thuộc tính là yêu cầu binder sử dụng cơ chế native thay cho message conversion thông thường của framework. Tuy nhiên, khả năng và cách cấu hình serializer/deserializer khác nhau theo binder.

### RabbitMQ binder

RabbitMQ truyền body dưới dạng bytes và hỗ trợ các AMQP properties cùng headers. Binder RabbitMQ thường tích hợp với cơ chế message conversion của Spring AMQP. Khả năng sử dụng native encoding/decoding và cách chỉ định converter phụ thuộc phiên bản binder cùng cấu hình của nó.

Không nên lấy cấu hình Kafka `key.serializer`, `value.serializer` hoặc `value.deserializer` áp dụng cho RabbitMQ. Những thuộc tính đó thuộc Kafka client. Với RabbitMQ, hãy kiểm tra message converter và các tùy chọn riêng của Rabbit binder đang sử dụng, đồng thời xác nhận body thực tế là JSON, byte array hay định dạng khác.

Nếu cần tương tác với ứng dụng AMQP ngoài Spring, hãy thống nhất content type, content encoding, kiểu body và AMQP properties. Native mode không tự tạo schema chung giữa các ứng dụng.

### Pulsar binder

Pulsar hỗ trợ schema-aware producer và consumer. Native serialization có thể tận dụng schema và kiểu dữ liệu do Pulsar client hỗ trợ, tùy binder và phiên bản. Producer và consumer cần thống nhất schema type, schema version và kiểu Java tương ứng.

Không áp dụng cấu hình Kafka serializer/deserializer cho Pulsar. Hãy sử dụng tùy chọn schema hoặc serialization mà Pulsar binder phiên bản hiện tại cung cấp. Nếu schema không tương thích, consumer có thể không giải mã được message hoặc không thể đăng ký subscription theo cấu hình mong muốn.

### Bảng so sánh

| Binder | Cơ chế native thường liên quan | Điều cần xác minh |
|---|---|---|
| Kafka | Kafka Serializer/Deserializer cho key và value | Class serializer/deserializer, key/value type, JSON/Avro bytes và cấu hình trusted packages |
| RabbitMQ | Cơ chế message conversion/serialization của Spring AMQP và binder | Converter được dùng, content type, AMQP properties và body bytes |
| Pulsar | Schema và serializer/deserializer của Pulsar client | Schema type, schema version, kiểu payload và khả năng tương thích của binder |

Không phải mọi binder đều cung cấp cùng mức cấu hình native. Trước khi bật cờ, hãy kiểm tra tài liệu của binder và phiên bản đang triển khai. Nếu binder không hỗ trợ hành vi mong muốn, hãy dùng message conversion chung hoặc cơ chế serialization được binder hỗ trợ rõ ràng.

## 9. Khi nào nên dùng native encoding/decoding?

Native mode phù hợp trong những tình huống sau:

- Producer hoặc consumer cần dùng serializer/deserializer cụ thể của Kafka.
- Hệ thống sử dụng Avro, Protobuf hoặc schema native do nền tảng broker quản lý.
- Ứng dụng Spring cần trao đổi dữ liệu với producer/consumer ngoài Spring Cloud Stream theo một wire format đã thống nhất.
- Cần kiểm soát chính xác key, value và cách serialize thay vì dựa vào converter mặc định.
- Muốn sử dụng tính năng schema hoặc serialization riêng của binder.

Message conversion mặc định thường thuận tiện hơn khi:

- Ứng dụng chủ yếu truyền DTO Java dưới dạng JSON.
- Không cần cấu hình serializer riêng theo broker.
- Muốn dùng cùng cơ chế chuyển đổi cho nhiều binder.
- Cần dựa vào content type và message converter của Spring Cloud Stream.

Native mode không mặc nhiên nhanh hơn hoặc tốt hơn. Nó chuyển trách nhiệm serialization sang binder/client và làm cho cấu hình wire format trở nên quan trọng hơn. Hãy chọn theo yêu cầu tích hợp, schema và khả năng vận hành.

## 10. Những rủi ro và lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Consumer không giải mã được payload | Deserializer không tương thích serializer | Đồng bộ serializer/deserializer và wire format |
| Function nhận `byte[]` thay vì DTO | Native deserializer trả về bytes hoặc kiểu đích chưa được cấu hình | Cấu hình deserializer đúng kiểu hoặc giải mã rõ ràng trong ứng dụng |
| Kafka báo lỗi serializer | Serializer không hỗ trợ kiểu payload thực tế | Dùng serializer phù hợp với kiểu object hoặc chuyển payload trước khi gửi |
| Kafka báo lỗi deserializer | Bytes không đúng định dạng hoặc JSON type không hợp lệ | Kiểm tra producer bytes, default type và schema |
| JSON có trên broker nhưng function lỗi | Consumer đang dùng native decoding với deserializer không đúng | Chọn JsonDeserializer hoặc dùng message converter |
| Content type không làm thay đổi kết quả | Native mode bỏ qua framework conversion ở chiều đó | Cấu hình serializer/deserializer native |
| Producer gửi được nhưng consumer không nhận | Deserializer ném lỗi, group hoặc destination sai | Kiểm tra log binder, consumer group và tài nguyên broker |
| Avro/Protobuf không tương thích | Schema version hoặc schema registry khác nhau | Đồng bộ schema và chính sách compatibility |
| RabbitMQ nhận body nhưng không đọc được | Converter hoặc content type AMQP không khớp | Kiểm tra body bytes, contentType và converter của binder |
| Pulsar không giải mã được | Schema type hoặc schema version không tương thích | Kiểm tra schema và cấu hình native của Pulsar binder |

Khi chẩn đoán, cần phân biệt lỗi gửi message với lỗi giải mã. Producer có thể gửi thành công vì serializer hoạt động, nhưng consumer vẫn lỗi khi deserializer nhận bytes không đúng kiểu. Hãy kiểm tra log ở cả hai phía và quan sát payload thực tế trong môi trường thử nghiệm.

## 11. Kiểm thử native serialization

Kiểm thử native mode nên bao gồm ba cấp độ.

### Unit test serializer/deserializer

Nếu ứng dụng dùng serializer riêng, kiểm tra round-trip:

1. Tạo một object mẫu.
2. Serialize thành bytes.
3. Deserialize bytes thành object.
4. So sánh các trường quan trọng và xác minh schema version.

Với JSON, kiểm tra các field, kiểu số, ngày giờ và giá trị null. Với Avro hoặc Protobuf, kiểm tra schema và quy tắc tương thích khi thêm hoặc đổi field.

### Binding test

Test binder có thể kiểm tra function và binding ở cấp Spring Cloud Stream, nhưng không mô phỏng đầy đủ mọi serializer native của broker. Không dùng kết quả test binder làm bằng chứng duy nhất rằng Kafka JsonSerializer, Avro serializer hoặc Pulsar schema hoạt động đúng.

### Broker integration test

Chạy broker thật hoặc Testcontainers để xác minh:

- Output binding dùng đúng serializer.
- Message trên broker có wire format mong đợi.
- Input binding dùng đúng deserializer.
- Function nhận đúng kiểu payload.
- Header và metadata cần thiết vẫn có mặt.
- Consumer xử lý được message sau khi ứng dụng khởi động lại.

Với Kafka, có thể dùng console consumer hoặc consumer kiểm thử có deserializer phù hợp để đọc topic. Không dùng deserializer sai kiểu rồi kết luận dữ liệu bị hỏng. Với Pulsar, dùng client có schema tương thích; với RabbitMQ, đọc body và AMQP properties bằng client hoặc công cụ quản trị phù hợp.

## 12. Quy trình thực hành: bật native mode cho Kafka

Thực hiện trong môi trường phát triển có Kafka:

1. Khai báo record `OrderCreated` với `eventId`, `orderId` và `total`.
2. Tạo output binding `orders-out-0` tới destination `orders`.
3. Bật `producer.useNativeEncoding: true`.
4. Cấu hình Kafka `JsonSerializer` cho value và serializer phù hợp cho key.
5. Tạo input binding `inventory-in-0` với destination `orders` và group `inventory`.
6. Bật `consumer.useNativeDecoding: true`.
7. Cấu hình Kafka `JsonDeserializer` với kiểu đích `OrderCreated` và trusted packages phù hợp.
8. Khởi động producer và consumer, phát một sự kiện mẫu.
9. Xác minh consumer nhận được đúng object và các trường dữ liệu.
10. Thử thay deserializer bằng `StringDeserializer`; quan sát consumer nhận chuỗi hoặc lỗi kiểu dữ liệu tùy chữ ký function.
11. Khôi phục deserializer đúng và chạy lại kiểm thử.
12. Thử một thay đổi schema tương thích, sau đó kiểm tra producer và consumer vẫn trao đổi được.

Cấu hình producer và consumer minh họa:

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
          consumer:
            useNativeDecoding: true
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
                value.serializer: org.springframework.kafka.support.serializer.JsonSerializer
          inventory-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
                spring.json.value.default.type: com.example.events.OrderCreated
                spring.json.trusted.packages: com.example.events
~~~

Thay `com.example.events.OrderCreated` và package tương ứng bằng class thật trong ứng dụng. Nếu producer và consumer là hai ứng dụng độc lập, bảo đảm cả hai dùng schema và cấu hình tương thích. Không dùng một package trusted rộng hơn mức cần thiết.

## Kết luận

`useNativeEncoding` và `useNativeDecoding` cho phép Spring Cloud Stream chuyển việc serialize và deserialize payload sang cơ chế native của binder. Producer dùng native encoding ở output binding; consumer dùng native decoding ở input binding. Hai lựa chọn độc lập nhưng phải tạo ra wire format tương thích.

Với Kafka, cần cấu hình đúng serializer/deserializer cho key và value; với RabbitMQ, cần hiểu converter và AMQP body/properties; với Pulsar, cần thống nhất schema và kiểu dữ liệu mà binder hỗ trợ. Hãy kiểm thử round-trip trên broker thực tế, vì content type hoặc test binder riêng lẻ không chứng minh native serialization đã được cấu hình đúng.

