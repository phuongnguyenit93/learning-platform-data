# Header, khóa hoặc metadata biến mất khi qua broker

Trong Spring Cloud Stream, một message có thể đi qua `Supplier`, `Function`, `Consumer` và một hoặc nhiều binder Kafka, RabbitMQ hoặc Pulsar. Lỗi thường gặp là payload vẫn đến nơi nhưng `correlationId`, tenant ID, khóa Kafka hoặc thông tin topic/partition/offset lại không xuất hiện ở service đích. Hiện tượng này không nhất thiết có nghĩa broker đã “làm mất” dữ liệu. Giá trị có thể chưa được gắn lên đúng field, đã bị lọc khi mapping header, bị thay thế khi tạo `Message` mới, không thể deserialize, hoặc là metadata chỉ tồn tại ở lần tiêu thụ một record cụ thể.

Bài học này trình bày cách phân biệt **payload**, **application header**, **record key** và **transport metadata**; khoanh vùng mất mát qua từng chặng; khắc phục với Kafka/RabbitMQ; cùng các bài kiểm thử end-to-end. Cấu hình mẫu minh họa message-channel Kafka binder theo functional model Spring Cloud Stream; với Kafka Streams Binder, RabbitMQ và Pulsar cần dùng API phù hợp với từng transport.

## 1. Nhận diện triệu chứng trước khi sửa cấu hình

| Triệu chứng | Giả thuyết ưu tiên | Điểm kiểm tra đầu tiên |
|---|---|---|
| Consumer đọc được payload nhưng không thấy `correlationId` | Producer không gắn header, mapper lọc hoặc function không chuyển tiếp | Header trong Spring `Message` trước send và header thô trên broker |
| Kafka record có value nhưng key là `null` | Chỉ đưa ID vào payload/header thường, chưa gán Kafka record key | `ProducerRecord.key()` hoặc Kafka console consumer in key |
| Kafka input có key nhưng topic output không có key | Function tạo message mới, không copy key hoặc producer key config không dùng giá trị đó | `KafkaHeaders.RECEIVED_KEY` tại input, `KafkaHeaders.MESSAGE_KEY` tại output |
| Header có trên broker nhưng thành `byte[]` hoặc không giải mã được | Header mapper/encoding của producer và consumer khác nhau | Raw header bytes, `KafkaHeaderMapper`, trusted packages |
| `id` hoặc `timestamp` thay đổi ở mỗi service | Đây là metadata của Spring `Message`, không phải business event ID bền vững | So sánh với `eventId` tự định nghĩa |
| Không còn topic/partition/offset ban đầu sau khi republish | Metadata nhận của record cũ không tự trở thành metadata của record mới | Tạo trường lineage riêng nếu nghiệp vụ cần |
| RabbitMQ không còn routing key/`x-death` như mong đợi | AMQP routing/property và DLX/republish semantics khác Kafka | RabbitMQ Management UI hoặc AMQP `MessageProperties` |
| Header có trong consumer thông thường nhưng không có trong batch/reactive flow | Kiểu đầu vào hoặc cách transform chưa giữ metadata | `Message<?>`, batch metadata, explicit copy |
| Header lỗi sau đổi version | Header mapping/type conversion hoặc binding config thay đổi | Reference đúng phiên bản, dependency đã resolve, regression test |

Hãy phân biệt **không tồn tại**, **có nhưng đổi tên**, **có nhưng đổi kiểu**, **không được expose trong chữ ký hàm** và **cố ý không được chuyển tiếp**. Mỗi trường hợp cần một hướng xử lý khác nhau.

## 2. Bốn lớp thông tin không thể xem là tương đương

Xem một sự kiện đơn hàng:

~~~text
Business event:
  payload: {"orderId":"O-501","status":"PAID"}
  eventId: EV-501
  correlationId: trace-business-501

Kafka record:
  topic: orders.events
  partition: 2
  offset: 1839
  key: O-501
  value: bytes của business event
  headers: ["correlationId" => bytes, "eventId" => bytes, ...]

Spring Message tại consumer:
  payload: OrderEvent hoặc String
  headers:
    correlationId
    eventId
    kafka_receivedMessageKey / KafkaHeaders.RECEIVED_KEY
    kafka_receivedTopic / KafkaHeaders.RECEIVED_TOPIC
    kafka_receivedPartitionId / KafkaHeaders.RECEIVED_PARTITION
    kafka_offset / KafkaHeaders.OFFSET
    ...
~~~

Các trường ở trên có nguồn gốc khác nhau:

1. **Payload** chứa dữ liệu nghiệp vụ. Nó được serialize/deserialize tùy content type và cấu hình client.
2. **Application headers** là metadata do ứng dụng chủ động gửi: `correlationId`, `tenantId`, `eventId`, `schemaVersion`. Khi binder hỗ trợ và mapper cho phép, chúng được ghi vào metadata của broker.
3. **Record key** là thành phần định tuyến riêng của Kafka record (`key` khác với `value` và `headers`). Kafka Streams cũng xử lý key/value như các thành phần chính của record. RabbitMQ không có Kafka record key tương đương trực tiếp; thay vào đó có routing key/property.
4. **Transport/receive metadata** mô tả lần truyền hoặc lần nhận cụ thể: topic, partition, offset, timestamp, RabbitMQ delivery tag, routing key hay Pulsar message ID. Nhiều trường được tạo bởi client/broker và có thể khác hoàn toàn ở hop kế tiếp.

Không nên dùng header `id` của Spring làm định danh nghiệp vụ bền vững. `MessageHeaders.ID` được framework tạo và không được Kafka binder map thành record header như application header thông thường; nó có thể đổi khi message được xây dựng lại. Để deduplicate, dùng một `eventId` chủ động quản lý.

## 3. Sơ đồ khoanh vùng theo từng chặng

~~~mermaid
flowchart TD
    A[Producer tạo Spring Message] --> B[Output Function / StreamBridge]
    B --> C[Binder outbound header mapper]
    C --> D[(Broker record: key, headers, value)]
    D --> E[Binder inbound header mapper]
    E --> F[Consumer / Function đầu vào]
    F --> G[Function tạo Message mới]
    G --> H[Output binder và broker kế tiếp]
    C -. Có header trước C nhưng mất sau D .-> I[Kiểm tra headerPatterns / mapper / serialization]
    E -. Có trên D nhưng không có ở F .-> J[Kiểm tra inbound mapper / type / native decoding]
    G -. Có ở F nhưng mất ở H .-> K[Kiểm tra chuyển tiếp key và headers]
~~~

Phương pháp chẩn đoán hiệu quả nhất là xác nhận dữ liệu tại **từng ranh giới**:

1. Trước khi producer gọi `send`: Spring `Message` có những header nào?
2. Sau khi binder serialize: record trên broker có key, native headers và value gì?
3. Ngay sau khi consumer nhận: `MessageHeaders` có những trường nào, kiểu dữ liệu gì?
4. Sau xử lý `Function`: outgoing `Message` có giữ thông tin nghiệp vụ cần thiết không?
5. Sau publish lần hai: broker đích có đúng key/header cần thiết không?

Nếu broker thô đã có header, đừng chỉ sửa producer. Nếu broker thô chưa có header, sửa mapping phía consumer cũng không tạo lại được thông tin đã không gửi. Đừng dựa riêng vào log payload: log payload không chứng minh record key và native headers tồn tại.

## 4. Kafka record key không phải một header tùy ý

Kafka message là record gồm **key, value và headers**. Đặt `orderId` trong payload hoặc trong header `businessKey` không tự khiến Kafka producer dùng giá trị đó làm record key.

Spring Cloud Stream Kafka binder hỗ trợ hai cách phổ biến:

- Đặt `KafkaHeaders.MESSAGE_KEY` trên outgoing Spring `Message`.
- Cấu hình producer `messageKeyExpression` để lấy key từ payload hoặc một header.

Ví dụ tạo message có Kafka key thật:

~~~java
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
class OrderProducer {

    @Bean
    Supplier<Message<String>> publishOrder() {
        return () -> MessageBuilder
                .withPayload("{\"orderId\":\"O-501\",\"status\":\"PAID\"}")
                .setHeader(KafkaHeaders.MESSAGE_KEY, "O-501")
                .setHeader("eventId", "EV-501")
                .setHeader("correlationId", "trace-business-501")
                .setHeader("tenantId", "tenant-a")
                .build();
    }
}
~~~

Đây là ví dụ cấu trúc, không nên triển khai `Supplier` này như nguồn phát production vì poller có thể gửi cùng `eventId` liên tục. Trong ứng dụng thật, tạo event ID/record từ dữ liệu đầu vào và đặt cadence phù hợp. Điểm trọng tâm là `KafkaHeaders.MESSAGE_KEY` điều khiển **Kafka record key**, không chỉ tạo một native header có tên tùy ý.

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
~~~

Nếu muốn dùng header riêng thay vì `KafkaHeaders.MESSAGE_KEY`:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              messageKeyExpression: "headers['businessKey']"
~~~

Khi dùng cấu hình này, producer phải đặt `businessKey` lên outgoing message. Không nhầm `messageKeyExpression` của Kafka binder với `partitionKeyExpression` của generic Spring Cloud Stream producer: một cái chọn **Kafka record key**, cái kia là cơ chế partitioning của framework. Trong hệ thống cần ordering theo business key, phải kiểm tra key thực sự trên broker và cách partition được chọn.

## 5. Đọc key và receive metadata ở đầu vào

Với Kafka consumer, chọn chữ ký `Consumer<Message<T>>` nếu cần xem header:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@Configuration
class OrderDiagnostics {

    @Bean
    Consumer<Message<String>> inspectOrder() {
        return message -> {
            var headers = message.getHeaders();

            Object key = headers.get(KafkaHeaders.RECEIVED_KEY);
            Object topic = headers.get(KafkaHeaders.RECEIVED_TOPIC);
            Object partition = headers.get(KafkaHeaders.RECEIVED_PARTITION);
            Object offset = headers.get(KafkaHeaders.OFFSET);
            Object correlationId = headers.get("correlationId");

            System.out.printf(
                    "key=%s topic=%s partition=%s offset=%s correlation=%s%n",
                    key, topic, partition, offset, correlationId);
        };
    }
}
~~~

Trong Spring for Apache Kafka, `KafkaHeaders.RECEIVED_KEY` là thông tin key của **record vừa nhận**. Nó không phải outgoing `KafkaHeaders.MESSAGE_KEY`; nếu cần publish lại cùng key, phải chủ động đưa key đó sang outgoing message hoặc dùng cấu hình producer phù hợp.

Nếu Kafka record có key `null`, header nhận key có thể **không tồn tại**. Không kiểm tra thiếu header bằng giả định rằng mọi message đều chứa `KafkaHeaders.RECEIVED_KEY`.

Các trường `RECEIVED_TOPIC`, `RECEIVED_PARTITION` và `OFFSET` mô tả record hiện tại. Nếu message được publish sang topic mới, offset và partition mới do Kafka quyết định, không phải bản sao offset gốc.

Khi dùng `Consumer<String>`, function chỉ nhận payload và không có đối số header để truy cập. Không được kết luận binder đánh mất header chỉ vì chữ ký hàm không cung cấp `MessageHeaders`.

## 6. Chuyển tiếp key và header qua Function

Một lỗi phổ biến là Function nhận `Message<String>` nhưng trả về một `String` hoặc tạo `Message` mới mà không đưa các trường quan trọng vào. Việc framework có thể tự chuyển tiếp một phần header trong một số đường xử lý **không phải hợp đồng** bảo đảm mọi key và metadata đặc thù broker được giữ nguyên giữa hai lần publish.

Ví dụ chuyển tiếp có chủ đích:

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
class OrderRelayConfiguration {

    @Bean
    Function<Message<String>, Message<String>> orderRelay() {
        return incoming -> {
            var output = MessageBuilder.withPayload(
                    incoming.getPayload().trim().toUpperCase(Locale.ROOT));

            Object correlationId = incoming.getHeaders().get("correlationId");
            if (correlationId != null) {
                output.setHeader("correlationId", correlationId);
            }

            Object eventId = incoming.getHeaders().get("eventId");
            if (eventId != null) {
                output.setHeader("eventId", eventId);
            }

            Object key = incoming.getHeaders().get(KafkaHeaders.RECEIVED_KEY);
            if (key != null) {
                output.setHeader(KafkaHeaders.MESSAGE_KEY, key);
            }

            return output.build();
        };
    }
}
~~~

Binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderRelay
    stream:
      bindings:
        orderRelay-in-0:
          destination: orders.events
          group: order-relay
        orderRelay-out-0:
          destination: orders.normalized
~~~

Đây là ví dụ **Kafka → Kafka**. Nó chuyển tiếp `correlationId`, `eventId` và key nghiệp vụ; không sao chép toàn bộ headers đầu vào. Việc sao chép mù quáng có thể đưa các field `kafka_received*`, acknowledgement hoặc error metadata vốn chỉ có ý nghĩa ở consumer vào producer khác.

Nếu muốn ghi dấu nguồn gốc, tạo application header riêng như `sourceTopic` hoặc `sourcePartition`; không dùng lại header hệ thống mà binder sẽ diễn giải với ý nghĩa khác:

~~~java
Object topic = incoming.getHeaders().get(KafkaHeaders.RECEIVED_TOPIC);
if (topic != null) {
    output.setHeader("sourceTopic", topic.toString());
}
~~~

Khi pipeline đi qua nhiều hop, quyết định có ghi `originalTopic`, `originalPartition`, `originalOffset` hay `lastHopTopic` phải nhất quán. Chúng chỉ là **lineage application metadata**, không thay thế record metadata mà Kafka cung cấp tại consumer.

## 7. Kiểm tra Kafka headerPatterns trước khi tìm lỗi broker

Kafka binder ánh xạ Spring `MessageHeaders` sang Kafka native `Headers` theo cấu hình producer `headerPatterns`. Reference của Kafka binder mô tả default là `*`, ngoại trừ `id` và `timestamp`, hai header framework không được map như header người dùng.

Ví dụ một cấu hình dễ gây mất header:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orderRelay-out-0:
            producer:
              headerPatterns: "eventId"
~~~

Ở đây `correlationId` và `tenantId` không nằm trong pattern cho phép nên không thể kỳ vọng chúng xuất hiện như native Kafka headers ở topic output.

Sửa theo contract:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orderRelay-out-0:
            producer:
              headerPatterns: "eventId,correlationId,tenantId,contentType"
~~~

Chỉ đưa những header ứng dụng thật sự cần qua transport vào allowlist. `headerPatterns` nhận các pattern cách nhau bởi dấu phẩy, có `*` ở đầu/cuối và có thể phủ định bằng `!`; **pattern đầu tiên khớp sẽ quyết định**. Đặt phủ định trước nếu muốn loại một header nhạy cảm.

Lưu ý key Kafka không được sửa bằng cách thêm `KafkaHeaders.MESSAGE_KEY` vào danh sách native header patterns. Key là field riêng của `ProducerRecord`; cần kiểm tra cách Kafka binder đặt record key.

## 8. Tìm custom KafkaHeaderMapper vô tình làm mất header

Một ứng dụng có thể định nghĩa bean tên `kafkaBinderHeaderMapper` để tùy chỉnh ánh xạ header. Khi bean này thay mapper mặc định và cách triển khai không xử lý `fromHeaders` hoặc `toHeaders` đầy đủ, một header sẽ biến mất dù producer đã gắn giá trị.

Ví dụ anti-pattern:

~~~java
// Không nên dùng: mapper này bỏ qua mọi header.
@Bean
KafkaHeaderMapper kafkaBinderHeaderMapper() {
    return new KafkaHeaderMapper() {
        @Override
        public void fromHeaders(MessageHeaders source, Headers target) {
            // Không làm gì.
        }

        @Override
        public void toHeaders(Headers source, Map<String, Object> target) {
            // Không làm gì.
        }
    };
}
~~~

Trường hợp này được mô tả trực tiếp trong **Kafka Binder Tips, Tricks and Recipes**, mục “Adding custom header mapper in Kafka”. Nếu thiếu header, kiểm tra có bean mapper tùy chỉnh không, mapper đó serialize/deserialize đúng cả chiều outbound/inbound không.

Ưu tiên dùng mapper mặc định khi dữ liệu chỉ gồm các header phổ biến như `String`/`byte[]`. Nếu cần mapper tùy chỉnh, viết test với cả hai chiều, xử lý `null` và charset cụ thể, giới hạn danh sách header cho phép và xác nhận không phát tán dữ liệu nhạy cảm.

Không thêm mapper tùy chỉnh chỉ vì một trường `id` không đi qua broker. Đặt tên application header rõ ràng như `eventId` hoặc `correlationId` để tránh đụng ý nghĩa nội bộ của Spring `MessageHeaders.ID`.

## 9. Header có tồn tại nhưng sai kiểu hoặc bị chặn deserialize

Kafka native header lưu **byte array**. Spring Kafka có `KafkaHeaderMapper` ánh xạ qua lại giữa kiểu Java và bytes. Các header `String` có thể được mã hóa dạng UTF-8/raw bytes hoặc theo dạng JSON tùy mapper/version; một consumer viết bằng ngôn ngữ khác có thể thấy bytes nhưng không hiểu kiểu dữ liệu.

Ví dụ:

~~~text
Spring producer:
  correlationId: String("abc-123")
Kafka native record:
  correlationId: byte[]
Another consumer:
  phải giải mã UTF-8 hoặc định dạng đã thống nhất
~~~

Một số mapper có header metadata mô tả type. Nếu phía nhận dùng mapper khác, header có thể trở thành `byte[]`, `NonTrustedHeaderType` hoặc không được ánh xạ như mong muốn. `JsonKafkaHeaderMapper` chỉ deserialize một số package được trust mặc định; không nên cấu hình `addTrustedPackages("*")` chỉ để “sửa mất header” trong môi trường có dữ liệu không đáng tin.

Giải pháp an toàn:

- Với dữ liệu dùng chung nhiều service/ngôn ngữ, quy định header contract đơn giản: `String` UTF-8 hoặc `byte[]` có schema rõ ràng.
- Đồng bộ header mapper, encoding, charset và tên header theo version client.
- Nếu cần deserialize custom Java class, allowlist chính xác package đáng tin và kiểm tra security implications.
- Không đưa object phức tạp như `Authentication`, `HttpServletRequest` hoặc transaction context trực tiếp vào broker header.
- Phân biệt giá trị “không được tạo” với giá trị “có bytes nhưng không đọc đúng kiểu”.

Tài liệu Spring Kafka `Message Headers` mô tả cách đặt raw-mapped headers và trusted packages. Khi chẩn đoán phiên bản cụ thể, cần đọc đúng reference của Spring Kafka đã được Spring Cloud BOM giải quyết.

## 10. headerMode, native encoding và contentType

Spring Cloud Stream có thuộc tính `headerMode` trên binding, với các lựa chọn như `headers` (header native của broker), `embeddedHeaders` (nhúng header vào payload cho transport cần cơ chế nhúng) và `none` (không nhúng). Default phụ thuộc binder.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderRelay-in-0:
          consumer:
            headerMode: headers
        orderRelay-out-0:
          producer:
            headerMode: headers
~~~

Đây là ví dụ minh họa khi binder và phiên bản hỗ trợ native headers. Kafka và RabbitMQ hiện đại có native header support; không nên bật `embeddedHeaders` theo lời khuyên lấy từ phiên bản Kafka cũ mà không kiểm tra giao thức thực tế.

Hai property khác cần phân biệt:

- `producer.useNativeEncoding: true`: để client serializer của broker quyết định cách serialize **value**; chuyển đổi payload theo binding `contentType` không còn áp dụng theo cách mặc định.
- `consumer.useNativeDecoding: true`: để client deserializer của broker đọc value; phải khớp serializer phía producer.

Khi dùng native encoding/decoding, cách nhúng `embeddedHeaders` có thể bị bỏ qua theo reference binding properties. Điều đó **không có nghĩa mọi native broker header đều mất**; cần xem binder mapper cụ thể. Sai `contentType` thường gây lỗi convert **payload**, khác với lỗi Kafka record key `null` hoặc header bị pattern loại.

Nếu message đi qua một consumer không dùng Spring Cloud Stream, việc bật cơ chế embedded header mà đối tác không hiểu có thể làm thay đổi bytes payload khiến đối tác parse sai. Hãy thống nhất wire format với các bên liên quan.

## 11. Functional model và reactive pipeline có thể thay đổi metadata

Với function:

~~~java
Function<String, String> upperCase() {
    return value -> value.toUpperCase(Locale.ROOT);
}
~~~

Function nhìn thấy `String` payload, không có cơ hội trực tiếp đọc hoặc sửa header. Với nhu cầu chuyển tiếp correlation ID/key, ưu tiên `Function<Message<String>, Message<String>>` như ví dụ mục 6.

Đặc biệt với function reactive `Function<Flux<Message<T>>, Flux<Message<R>>>`, trách nhiệm tạo `Message` đầu ra và chuyển tiếp headers nằm ở code reactive. Không mặc định mỗi record sẽ giữ key/metadata nếu pipeline dùng `map(Message::getPayload)` rồi tạo message từ payload mới.

Ví dụ minh họa:

~~~java
@Bean
Function<Flux<Message<String>>, Flux<Message<String>>> reactiveRelay() {
    return flux -> flux.map(incoming -> {
        var builder = MessageBuilder.withPayload(
                incoming.getPayload().toUpperCase(Locale.ROOT));

        Object correlation = incoming.getHeaders().get("correlationId");
        if (correlation != null) {
            builder.setHeader("correlationId", correlation);
        }

        Object key = incoming.getHeaders().get(KafkaHeaders.RECEIVED_KEY);
        if (key != null) {
            builder.setHeader(KafkaHeaders.MESSAGE_KEY, key);
        }
        return builder.build();
    });
}
~~~

Ví dụ cần import `reactor.core.publisher.Flux` và các lớp Spring Messaging/Spring Kafka tương ứng. Với reactive binder chuyên biệt, kiểm tra tài liệu của binder vì acknowledgment và message propagation có thể khác message-channel binder.

**Với consumer batch**, đừng giả định mọi record đều được biểu diễn bằng một `MessageHeaders` phẳng. Một số binder đưa danh sách payload vào `Message<List<?>>` và cung cấp metadata tương ứng từng phần tử theo cấu trúc riêng. Ví dụ Rabbit binder đặt danh sách map header vào `AmqpInboundChannelAdapter.CONSOLIDATED_HEADERS`; index của map phải tương ứng index phần tử payload. Khi thấy “mất header” trong batch, kiểm tra metadata tổng hợp trước khi đổi mapper hoặc producer.

## 12. RabbitMQ: AMQP properties và routing key khác Kafka key

RabbitMQ transport có các khái niệm:

- **Exchange** nhận message từ producer.
- **Routing key** cùng exchange/binding rule giúp broker chọn queue đích.
- **MessageProperties** và application headers chứa `contentType`, `messageId`, `correlationId` và custom fields.
- **Delivery tag**, consumer tag, received exchange/routing key là metadata của một lần nhận.

Không có trường Kafka `ProducerRecord.key` trong RabbitMQ. Nếu yêu cầu định tuyến theo mã khách hàng, ứng dụng có thể chọn routing key phù hợp với exchange type, hoặc đưa business key vào application header/payload theo contract. Đừng dùng `KafkaHeaders.MESSAGE_KEY` trên RabbitMQ rồi kỳ vọng nó trở thành routing key AMQP.

Rabbit binder có thuộc tính `headerPatterns` cho cả input và output, mặc định thường là `['*']` theo reference binder:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          audit-in-0:
            consumer:
              headerPatterns: "eventId,correlationId,tenantId,contentType"
          audit-out-0:
            producer:
              headerPatterns: "eventId,correlationId,tenantId,contentType"
~~~

Nếu thu hẹp allowlist mà bỏ `correlationId`, ứng dụng không thể trông chờ header đó đi qua mapper. Tên/bản chất AMQP property có thể được mapper xử lý đặc biệt; không phải mọi property đều chỉ là một key trong user headers map.

Spring Integration AMQP header mapping mặc định còn có quy tắc loại một số header `x-*`, đặc biệt để tránh chuyển tiếp sai metadata broker/system. Nếu muốn giữ header có tiền tố đặc biệt, phải kiểm tra quy tắc mapper theo phiên bản; không cấu hình wildcard toàn bộ chỉ để copy `x-death` hoặc thông tin nhận về sang một message mới.

## 13. RabbitMQ DLQ và metadata do broker tạo ra

Khi RabbitMQ dead-letter một message, broker có thể thêm `x-death` với thông tin về lần dead-letter. Khi application republish sang DLQ bằng recoverer, các header lỗi và header nguồn có thể khác cơ chế native dead-letter của broker.

Vì vậy, đừng giả định:

- Mọi message trong DLQ đều có `x-death` cùng cấu trúc.
- `x-death` luôn còn nguyên sau một service trung gian đọc rồi gửi lại bằng `RabbitTemplate` hoặc `StreamBridge`.
- `deliveryTag` hoặc received routing key là ID bền vững để deduplicate.
- Application header `eventId` tự xuất hiện nếu producer chưa tạo.

Nếu nghiệp vụ cần truy vết DLQ, lưu `eventId`/`correlationId` của ứng dụng, thống nhất schema error metadata và kiểm thử riêng hai đường **broker DLX** và **application republish**. Không dùng thông tin stack trace dài làm header tùy ý; RabbitMQ có giới hạn frame/header và binder có cơ chế truncate một số thông tin lỗi.

## 14. Kafka Streams Binder: key là dữ liệu của record trong topology

Với Kafka Streams, `KStream<K,V>` biểu diễn key/value, không phải cặp payload và `MessageHeaders` theo đúng mô hình message-channel binder. Ví dụ:

~~~java
@Bean
Function<KStream<String, String>, KStream<String, String>> normalize() {
    return input -> input.mapValues(value -> value.trim().toUpperCase());
}
~~~

Ở đây `mapValues` giữ key của record trong DSL, còn `selectKey` hoặc `map` có thể thay đổi key theo logic ứng dụng. Sau `groupBy`, `repartition`, aggregation, join hoặc materialization, cần kiểm tra key/output record semantics thực tế: Kafka Streams có thể tạo repartition/changelog topics và record mới.

Kafka Streams có native record headers, nhưng không phải API nào cũng expose/chuyển tiếp chúng giống message-channel `Message<T>`. Một số thao tác stateful tạo record tổng hợp chứ không mang nguyên trạng metadata của input. Nếu cần giữ `eventId` hoặc lineage qua cửa sổ/aggregate, thiết kế rõ schema cho giá trị tổng hợp hoặc dùng processor API/header enricher phù hợp; không giả định Kafka `OFFSET` của nguồn sẽ tồn tại trong output aggregate.

Kiểm tra key serde, repartition topic, topology output key và consumer deserializer khi thấy “khóa biến mất” sau join hoặc aggregation. Một lỗi key serde có thể trông giống mất key nhưng thực ra consumer đang giải mã sai hoặc không đọc được giá trị.

## 15. Pulsar: message key và properties cần ánh xạ riêng

Apache Pulsar có message metadata riêng: `partition_key`/key, `properties` dạng key/value, `messageId`, `publishTime`, `producerName`, `sequenceId` và các trường khác. Những giá trị này không mặc định trùng với Kafka `KafkaHeaders.MESSAGE_KEY` hoặc RabbitMQ routing key.

Khi dùng một Pulsar binder hoặc Spring for Apache Pulsar:

1. Kiểm tra binder có map Spring application headers sang Pulsar `properties` hay không.
2. Kiểm tra cách binder đặt Pulsar message key/partition key.
3. Xác định bên nhận đọc `Message` wrapper, raw Pulsar message hay payload đơn thuần.
4. Kiểm tra schema/serialization và conversion cho metadata.
5. Không dùng `KafkaHeaders.RECEIVED_KEY` để tìm Pulsar message key.
6. Phân biệt `messageId` do Pulsar cấp với `eventId` do nghiệp vụ tạo.

Hợp đồng trao đổi đa broker nên ưu tiên field nghiệp vụ có tên rõ ràng và định dạng ổn định. Nếu ứng dụng bridge Kafka → Pulsar, hãy ánh xạ key và properties một cách tường minh trong tầng chuyển đổi; không mong Spring tự giữ mọi metadata vận chuyển giữa hai giao thức.

## 16. Header tracing và security không phải một thứ

Các thư viện Micrometer Tracing/OpenTelemetry có thể inject `traceparent`, `tracestate`, baggage hoặc metadata quan sát vào message qua integration được bật. Nếu tracing context biến mất:

- Kiểm tra producer và consumer đều có tracing instrumentation đúng phiên bản.
- Kiểm tra header mapper không loại trace headers.
- Kiểm tra các function tạo message mới có giữ propagation context khi async/reactive.
- Phân biệt `traceId`, `spanId`, `correlationId` và `eventId` vì chúng giải quyết các nhu cầu khác nhau.

Không biến `traceId` thành business key chỉ để khôi phục ordering. Trace ID có thể đổi giữa request/hop và không phải deduplication ID.

Cũng không sao chép mù quáng các header như `Authorization`, session cookie, token nội bộ, security principal hoặc PII sang broker. Việc một header “không đi qua” có thể là **cơ chế bảo vệ có chủ đích**, không phải lỗi. Bảo đảm header allowlist tuân thủ privacy, multi-tenant authorization và quy ước truyền dữ liệu.

## 17. Cách quan sát Kafka record thực trên broker

Với Kafka command-line tool tương thích version broker/client:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.events \
  --from-beginning \
  --property print.key=true \
  --property print.headers=true \
  --property print.partition=true \
  --property print.offset=true
~~~

Không chạy `--from-beginning` trên topic production dung lượng lớn khi không có giới hạn đọc. Dùng topic thử nghiệm có message ID duy nhất hoặc đặt consumer timeout/max messages theo công cụ đang dùng.

Đọc kỹ ba thành phần:

- **Key:** hiển thị `null` nếu record được ghi không có key; nó không tự lấy từ `orderId` nằm trong JSON.
- **Headers:** native key/value metadata trên record; khi in CLI, một số bytes không thể đọc trực tiếp như text.
- **Topic/partition/offset:** xác định record đã được lưu ở đâu, không phải application headers gốc.

Với consumer Java trong integration test, có thể dùng `ConsumerRecord<K,V>`:

~~~java
ConsumerRecord<String, String> record = ...; // Đọc từ topic test.

String key = record.key();
String value = record.value();

Header header = record.headers().lastHeader("correlationId");
String correlationId = header == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);

System.out.printf(
        "topic=%s partition=%d offset=%d key=%s correlation=%s value=%s%n",
        record.topic(),
        record.partition(),
        record.offset(),
        key,
        correlationId,
        value);
~~~

Đoạn minh họa dùng `org.apache.kafka.clients.consumer.ConsumerRecord`, `org.apache.kafka.common.header.Header` và `java.nio.charset.StandardCharsets`. Việc giải mã UTF-8 đúng khi contract quy định header này là chuỗi raw UTF-8; nếu mapper dùng JSON bytes hoặc định dạng khác, giải mã theo contract thực tế.

Đây là phép kiểm tra quan trọng: nếu `record.headers()` có `correlationId` nhưng `Consumer<Message<String>>` không có, trọng tâm nằm ở mapper/converter phía nhận; nếu broker record đã thiếu, kiểm tra đường tạo message và mapper outbound.

## 18. Metadata của successful send không phải metadata của record nhận

Kafka binder có producer property `recordMetadataChannel`. Khi cấu hình, một lần send thành công có thể phát message vào channel với header `KafkaHeaders.RECORD_METADATA` chứa `RecordMetadata` do Kafka producer cung cấp, ví dụ partition và offset nơi bản ghi được ghi.

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orderRelay-out-0:
            producer:
              recordMetadataChannel: producerResults
~~~

`producerResults` phải là bean `MessageChannel` thực sự tồn tại. Metadata này dùng để quan sát kết quả send; nó không tự trở thành header nghiệp vụ trong consumer topic kế tiếp. Một record được tạo lại có metadata producer/consumer mới, dù giữ nguyên `eventId`.

Không log toàn bộ serialized payload chỉ để quan sát offset. Dùng topic, partition, offset, event ID, key đã được ẩn/hashed khi cần và thời gian send để chẩn đoán; hạn chế lưu dữ liệu cá nhân trong hệ thống giám sát.

## 19. Test Binder không kiểm chứng header trên wire

Spring Integration Test Binder chạy trong JVM, rất phù hợp kiểm thử logic function và việc sử dụng `MessageHeaders`. Tuy nhiên, nó **không** thay Kafka record header mapping, AMQP MessageProperties, Pulsar key, serialization và brokering thực.

Bộ test nên có hai tầng:

**Tầng logic với Test Binder:**

~~~java
var input = MessageBuilder.withPayload(" paid ")
        .setHeader("eventId", "EV-501")
        .setHeader("correlationId", "trace-business-501")
        .build();

var relay = new OrderRelayConfiguration().orderRelay();
Message<String> output = relay.apply(input);

assertThat(output.getPayload()).isEqualTo("PAID");
assertThat(output.getHeaders().get("eventId")).isEqualTo("EV-501");
assertThat(output.getHeaders().get("correlationId"))
        .isEqualTo("trace-business-501");
~~~

Test này xác nhận function chuyển tiếp application headers; nó không chứng minh producer gán đúng Kafka record key vì input ví dụ chưa có `KafkaHeaders.RECEIVED_KEY`.

**Tầng integration với Kafka/Rabbit/Pulsar thật:**

1. Producer gửi event ID, correlation ID, business key và content type đã xác định.
2. Đọc record thô trực tiếp từ broker để xác nhận key, value, native headers.
3. Chạy consumer qua binder thật, kiểm tra `MessageHeaders` ở đầu vào.
4. Chạy Function/relay và đọc output record thô.
5. Kiểm tra producer output key và application headers đúng hợp đồng.
6. Lặp lại với key `null`, thiếu optional header, header Unicode và header bytes.
7. Kiểm tra serializer khác nhau, header mapper tùy chỉnh và `headerPatterns` giới hạn.
8. Kiểm tra đường retry/DLQ, re-publish và migration version nếu có.

Với RabbitMQ, sử dụng queue test riêng và kiểm tra AMQP properties/routing key qua client/management API; với Pulsar, đọc native Pulsar Message metadata. Không khẳng định header portable khi chưa có integration test cross-binder tương ứng.

## 20. Quy trình xử lý sự cố theo bằng chứng

Khi có ticket “header bị mất”, áp dụng runbook:

1. **Xác định định danh:** broker, topic/exchange, consumer group/queue/subscription, `eventId`, thời điểm và phiên bản của từng service.
2. **Định nghĩa trường kỳ vọng:** tên header, kiểu Java, wire format, ai tạo và hop nào phải giữ. Với key, nêu rõ đây là Kafka record key, RabbitMQ routing key hay Pulsar key.
3. **Kiểm tra producer:** ngay trước `send` có `MessageHeaders` như mong đợi không? Key có được gán theo binder không?
4. **Đọc broker thô:** kiểm tra key/native headers/value bằng tool hoặc client test.
5. **Kiểm tra binder outbound:** `headerPatterns`, `headerMode`, `messageKeyExpression`, `useNativeEncoding` và mapper tùy chỉnh.
6. **Kiểm tra binder inbound:** header mapper, trusted packages, charset, `useNativeDecoding` và batch semantics.
7. **Kiểm tra chữ ký function:** `Consumer<T>` hay `Consumer<Message<T>>`? Function có tạo message mới, reactive pipeline có làm mất context không?
8. **Kiểm tra output tiếp theo:** key/header application có được đặt rõ ràng và không mang theo metadata nhận không?
9. **Kiểm tra DLQ/retry:** message có đi qua recoverer/republisher làm thay đổi header không?
10. **Viết regression test:** tái tạo lỗi qua binder thật và chốt contract để tránh lặp lại sau nâng cấp.

Tránh cách sửa bằng việc copy toàn bộ `MessageHeaders` hoặc bật cho phép deserialize mọi package. Những cách này có thể chuyển tiếp authentication token hoặc metadata nhạy cảm, gây lỗi ở transport khác và che giấu nguyên nhân gốc.

## 21. Bảng chẩn đoán nhanh

| Nếu thấy... | Kiểm tra... | Cách xử lý ưu tiên |
|---|---|---|
| Kafka key `null` | `ProducerRecord.key`, `KafkaHeaders.MESSAGE_KEY`, `messageKeyExpression` | Gán key đúng field và xác nhận trên broker |
| Key có ở input, mất ở output | `KafkaHeaders.RECEIVED_KEY` và outgoing message | Copy sang `KafkaHeaders.MESSAGE_KEY` hoặc cấu hình producer expression |
| Mất riêng `correlationId` | Producer/consumer `headerPatterns` | Bổ sung vào allowlist sau khi xem security contract |
| Mất mọi custom header | Bean `kafkaBinderHeaderMapper`, headerMode | Dùng mapper mặc định hoặc sửa mapping hai chiều |
| `id` hoặc `timestamp` biến đổi | Spring `MessageHeaders` lifecycle | Dùng `eventId`/`createdAt` của nghiệp vụ |
| Header là `byte[]` thay vì `String` | Wire encoding và mapper | Đồng bộ charset/JSON/raw header contract |
| Header thành `NonTrustedHeaderType` | Trusted package của JSON header mapper | Chỉ trust package cần thiết hoặc dùng String/bytes |
| Kafka offset gốc không còn sau relay | Record mới có offset mới | Ghi lineage có chủ đích ở application header |
| RabbitMQ routing key không giữ | AMQP routing semantics | Đặt routing key theo binder/protocol, không dùng Kafka key |
| `x-death` khác giữa DLQ message | Native DLX và application republish khác nhau | Kiểm tra đường vào DLQ, giữ eventId |
| Trace context mất qua reactive pipeline | Message creation và instrumentation | Chuyển context đúng cơ chế tracing |
| Test Binder PASS nhưng production mất header | Test chưa đi qua broker thật | Bổ sung integration test raw record |

## 22. Checklist phòng ngừa

- Phân biệt payload, application header, record key và transport metadata.
- Dùng application header có tên rõ như `eventId`, `correlationId`, `tenantId`.
- Không dùng framework `id`/`timestamp` làm business ID bền vững.
- Chọn Kafka record key qua `KafkaHeaders.MESSAGE_KEY` hoặc `messageKeyExpression`.
- Kiểm tra `KafkaHeaders.RECEIVED_KEY` khi đọc input record có key.
- Dùng `Message<T>` nếu function cần đọc/copy application headers.
- Không copy mù quáng received metadata hoặc security credentials sang broker kế tiếp.
- Kiểm tra `headerPatterns` và custom header mapper ở cả hai chiều.
- Đồng bộ wire encoding, charset, content type và trusted package policy.
- Phân biệt `headerMode` với native encoding/decoding và conversion của payload.
- Khi dùng RabbitMQ, xác định AMQP routing key/properties và DLQ behavior riêng.
- Khi dùng Pulsar, kiểm tra key/properties/messageId qua API của Pulsar binder/client.
- Với Kafka Streams, xác nhận key/value, repartition và output semantics của topology.
- Quan sát raw broker record và Spring `MessageHeaders` ở cùng một event ID.
- Có integration test với broker thật cho key, custom headers, null/bytes và DLQ.
- Ghi rõ phiên bản Spring Boot, Spring Cloud Stream, binder, Spring Kafka/AMQP/Pulsar.

## Tổng kết

Khi header, khóa hoặc metadata “biến mất” qua broker, câu hỏi đầu tiên không phải “broker có lỗi không?” mà là **giá trị đó thuộc lớp nào, ai tạo, nó có mặt ở ranh giới nào và có được phép đi qua ranh giới tiếp theo không?** Với Kafka, key là một field riêng của record; `KafkaHeaders.MESSAGE_KEY` chọn key khi gửi còn `KafkaHeaders.RECEIVED_KEY` mô tả key khi nhận. Custom header phụ thuộc mapper và `headerPatterns`. Với RabbitMQ và Pulsar, routing key/properties/message ID có semantics khác nên phải ánh xạ có chủ đích. Với Spring Cloud Stream functional model, hãy kiểm tra đầu vào `Message<T>`, lúc tạo output message và broker record thật để tìm đúng điểm mất dữ liệu.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.1 — Binding Properties: headerMode, useNativeEncoding/useNativeDecoding](https://docs.spring.io/spring-cloud-stream/reference/5.1/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream 5.0 — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream Kafka Binder — Tips, Tricks and Recipes: keys and custom header mapper](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/tips.html)
- [Spring Kafka — Message Headers and Header Mappers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
- [Spring Kafka — Listener Record Metadata Headers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring Cloud Stream RabbitMQ Binder — Configuration Options and Headers](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Integration — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html)
- [Spring Kafka — Kafka Streams Support and Header Enricher](https://docs.spring.io/spring-kafka/reference/streams.html)
- [Apache Pulsar — Binary Protocol: Message Metadata](https://pulsar.apache.org/docs/4.2.x/developing-binary-protocol/)
