# Đăng ký converter, header mapper và chiến lược phân vùng riêng

Spring Cloud Stream cho phép ứng dụng xử lý sự kiện qua `Supplier`, `Function` và `Consumer` mà không phụ thuộc hoàn toàn vào cách Kafka, RabbitMQ hay Pulsar truyền dữ liệu. Tuy nhiên, một hệ thống lớn thường cần vượt ra ngoài các giá trị mặc định: dữ liệu từ đối tác có định dạng riêng, một số header phải được chuẩn hóa hoặc loại bỏ, và partition key phải được tính theo quy tắc nghiệp vụ.

Ba điểm mở rộng thường gặp là **MessageConverter**, **header mapper** và **partitioning strategy**. Chúng can thiệp vào những ranh giới khác nhau của đường đi message. Đăng ký đúng sẽ giúp các service tương tác nhất quán; cấu hình sai có thể gây lỗi deserialize, mất correlation ID, lệch partition hoặc phá vỡ thứ tự sự kiện.

Bài này xây dựng một ví dụ xuyên suốt xử lý sự kiện đơn hàng, giải thích cách đăng ký bean và cấu hình binding, cách phân biệt lựa chọn chung của Spring Cloud Stream với các API riêng của Kafka, RabbitMQ, Pulsar, và cách kiểm thử toàn bộ đường đi trước khi mở rộng nhiều instance.

## 1. Ba điểm mở rộng nằm ở đâu?

~~~mermaid
flowchart LR
    A["Broker: dữ liệu và metadata"] --> B["Binder/Client"]
    B --> C["Header mapper"]
    B --> D["Message converter"]
    C --> E["Spring Message"]
    D --> E
    E --> F["Consumer / Function"]
    F --> G["Message hoặc DTO đầu ra"]
    G --> H["Message converter"]
    G --> I["Header mapper"]
    H --> J["Partition key + selector"]
    I --> J
    J --> K["Binder/Client → broker"]
~~~

Sơ đồ là mô hình khái niệm. Thứ tự xử lý thực tế và bước nào được gọi còn phụ thuộc binder, kiểu function, native encoding/decoding và version framework. Điều cần ghi nhớ là mỗi điểm mở rộng có trách nhiệm riêng:

| Điểm mở rộng | Đầu vào/đầu ra chính | Trách nhiệm | Không thay thế |
|---|---|---|---|
| `MessageConverter` | Payload trên wire ↔ đối tượng Java | Chọn chuyển đổi theo `contentType` và target type | Serializer/Serde native của broker khi native mode bật |
| Header mapper | Spring `MessageHeaders` ↔ broker headers/properties | Giữ, đổi kiểu hoặc lọc metadata | Chuyển đổi payload nghiệp vụ |
| `PartitionKeyExtractorStrategy` | Spring `Message<?>` → partition key | Rút key nghiệp vụ ổn định | Partition selector |
| `PartitionSelectorStrategy` | Key + số partition → partition index | Quyết định partition đích trong cơ chế chung | Kafka native partitioner hoặc Pulsar message router |

Một sự kiện có thể qua nhiều điểm mở rộng, nhưng chúng không nên cùng xử lý một trách nhiệm. Chẳng hạn, đừng cố nhét partition key đã hash vào `contentType` hoặc dùng payload converter để lọc token trong header.

## 2. Ví dụ miền nghiệp vụ và hợp đồng message

Giả sử hệ thống nhận sự kiện đơn hàng từ đối tác dùng định dạng ký tự `application/vnd.acme.order-line`:

~~~text
tenant-a|order-101|250000
tenant-a|order-102|125000
tenant-b|order-201|64000
~~~

Các trường lần lượt là `tenantId`, `orderId` và số tiền theo đơn vị nhỏ nhất (`totalMinor`). Đây là định dạng ví dụ có chủ đích, chỉ hỗ trợ ký tự không chứa dấu `|`. Một hệ thống thực tế nên dùng JSON, Avro, Protobuf hoặc định dạng có cơ chế escaping/schema rõ ràng nếu dữ liệu phức tạp.

Đối tượng Java đại diện sự kiện:

~~~java
public record OrderEvent(
        String tenantId,
        String orderId,
        long totalMinor) {
}
~~~

Metadata nghiệp vụ được truyền riêng:

~~~text
event-id       = evt-001
correlation-id = checkout-7842
event-type     = OrderCreated
~~~

Mục tiêu triển khai:

1. Converter đọc/ghi wire format đơn hàng.
2. Header mapper chỉ truyền metadata được phép qua broker.
3. Partition extractor chọn cùng shard cho mọi sự kiện của một đơn hàng.
4. Selector tính partition hợp lệ, ổn định và có thể kiểm thử.
5. Consumer nhận đúng DTO và header bất kể ứng dụng mở rộng thành nhiều instance.

## 3. Hiểu `contentType` trước khi tạo converter

Spring Cloud Stream có sẵn converter cho JSON, byte array và text. Khi payload cần chuyển đổi, framework kết hợp **target type** với **content type** để chọn converter.

Thứ tự lấy content type thường là:

1. Header `contentType` có sẵn trên `Message`.
2. Thuộc tính `spring.cloud.stream.bindings.<binding>.content-type`.
3. Giá trị mặc định `application/json`.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          content-type: application/vnd.acme.order-line
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: application/vnd.acme.order-line
~~~

Nếu producer chủ động gửi header `contentType=application/json`, giá trị trong header có thể được ưu tiên hơn cấu hình binding. Bởi vậy, khi converter không được gọi, cần kiểm tra cả header thực tế lẫn type khai báo của function.

Ví dụ function:

~~~java
@Bean
Function<OrderEvent, OrderEvent> normalizeOrder() {
    return event -> new OrderEvent(
            event.tenantId().trim(),
            event.orderId().trim(),
            event.totalMinor());
}
~~~

Nếu đầu vào đã là `OrderEvent` và target type cũng là `OrderEvent`, framework có thể bỏ qua conversion. Nếu function nhận `Object`, framework có quá ít thông tin để quyết định target type; hãy khai báo kiểu cụ thể trong contract khi cần chuyển đổi.

### Native encoding/decoding thay đổi đường đi

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-out-0:
          producer:
            use-native-encoding: true
        normalizeOrder-in-0:
          consumer:
            use-native-decoding: true
~~~

Khi bật native mode, việc serialize/deserialize payload do broker client và serializer/deserializer hoặc schema tương ứng thực hiện. Đừng kỳ vọng custom `MessageConverter` của Spring Cloud Stream tiếp tục được áp dụng cho phần payload đang ở native mode. Với Kafka có thể dùng native `Serializer`/`Deserializer`, Kafka Streams sử dụng `Serde`; với Pulsar có Pulsar schema. Header mapping vẫn là trách nhiệm riêng và có thể cần cấu hình tương ứng.

## 4. Đăng ký `MessageConverter` riêng

Spring Cloud Stream tự nhận diện bean kiểu `org.springframework.messaging.converter.MessageConverter`. Có thể kế thừa `AbstractMessageConverter` để công bố MIME type và triển khai cả hai chiều chuyển đổi.

Ví dụ converter dành riêng cho `OrderEvent`:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.AbstractMessageConverter;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.util.MimeType;

public final class OrderLineMessageConverter
        extends AbstractMessageConverter {

    public OrderLineMessageConverter() {
        super(new MimeType("application", "vnd.acme.order-line"));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return OrderEvent.class.equals(clazz);
    }

    @Override
    protected Object convertFromInternal(
            Message<?> message, Class<?> targetClass, Object hint) {
        if (!(message.getPayload() instanceof byte[] bytes)) {
            throw new MessageConversionException(
                    message, "Order-line payload must be byte[]");
        }

        String line = new String(bytes, StandardCharsets.UTF_8);
        String[] fields = line.split("\\|", -1);
        if (fields.length != 3
                || fields[0].isBlank() || fields[1].isBlank()) {
            throw new MessageConversionException(
                    message, "Invalid order-line fields");
        }

        try {
            return new OrderEvent(
                    fields[0], fields[1], Long.parseLong(fields[2]));
        }
        catch (NumberFormatException ex) {
            throw new MessageConversionException(
                    message, "Invalid totalMinor", ex);
        }
    }

    @Override
    protected Object convertToInternal(
            Object payload, MessageHeaders headers, Object hint) {
        OrderEvent event = (OrderEvent) payload;
        if (event.tenantId().isBlank()
                || event.orderId().isBlank()
                || event.tenantId().contains("|")
                || event.orderId().contains("|")) {
            throw new IllegalArgumentException(
                    "Order identifiers cannot be blank or contain '|'");
        }

        String line = event.tenantId()
                + "|" + event.orderId()
                + "|" + event.totalMinor();
        return line.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Đăng ký trong Spring context:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.converter.MessageConverter;

@Configuration(proxyBeanMethods = false)
class MessageConversionConfiguration {

    @Bean
    MessageConverter orderLineConverter() {
        return new OrderLineMessageConverter();
    }
}
~~~

`convertFromInternal` chuyển `byte[]` nhận được thành `OrderEvent`; `convertToInternal` trả về `byte[]` để truyền lên broker. Converter chỉ nhận MIME type được khai báo và target type được hỗ trợ.

**Tính mở rộng có kiểm soát:** custom converters được thêm vào đầu danh sách converter của Spring Cloud Stream, vì vậy chúng có mức ưu tiên cao hơn converter tích hợp khi cùng nhận một message. Nếu `supports` hoặc MIME matching quá rộng, converter mới có thể vô tình chặn JSON/text của những function khác. Dùng MIME type riêng, giới hạn target class và kiểm thử cả những binding không dùng converter này.

Đây là wire format minh họa cho bài học; production cần bổ sung giới hạn kích thước, validation schema, quy tắc escaping, versioning và chính sách xử lý lỗi dữ liệu đến từ hệ thống không tin cậy.

## 5. Lỗi chuyển đổi và tính tương thích dữ liệu

Converter không chỉ cần thành công với dữ liệu đẹp. Cần xác định cách xử lý các trường hợp:

| Tình huống | Hành vi mong đợi |
|---|---|
| Content type không khớp | Converter từ chối nhận; framework thử converter phù hợp hoặc báo lỗi. |
| Thiếu trường bắt buộc | Báo lỗi conversion có thông tin loại lỗi, tránh log toàn bộ payload nhạy cảm. |
| Số tiền sai định dạng | Báo lỗi conversion; áp dụng retry/DLQ theo binder và error handler. |
| Wire format phiên bản cũ | Chuyển đổi tương thích hoặc từ chối có kiểm soát; không đoán dữ liệu. |
| Byte array quá lớn | Từ chối trước khi giải mã tốn bộ nhớ theo giới hạn nghiệp vụ. |
| Content type trong header bị giả mạo | Kiểm tra nguồn dữ liệu và validate payload, không tin tuyệt đối header. |

Nếu một sự kiện có nhiều phiên bản, nên dùng `contentType` có version, header `schema-version` hoặc schema registry phù hợp. Khi nâng version, kiểm tra producer mới với consumer cũ theo chính sách tương thích.

Với Kafka Streams, converter ứng dụng không thay thế `Serde` tại các bước repartition, state store và changelog. Nếu topology cần native Serde riêng, cấu hình `keySerde`/`valueSerde` theo Kafka Streams binder thay vì kỳ vọng `MessageConverter` xử lý mọi record nội bộ.

## 6. Header mapper là lớp khác với payload converter

Spring `Message<?>` gồm payload và `MessageHeaders`. Broker có cơ chế header riêng:

| Broker | Dữ liệu metadata | Điểm cần quan tâm |
|---|---|---|
| Kafka | Header name và `byte[]` value | Mapper quyết định kiểu dữ liệu và header nào được chuyển; Kafka record key/partition/offset có ý nghĩa riêng. |
| RabbitMQ | AMQP properties và headers | Mapper chuyển Spring headers sang properties và header table; exchange/routing key/delivery tag là metadata giao nhận. |
| Pulsar | User properties và message metadata | User properties thường là String; metadata như message ID/key có ngữ nghĩa riêng. |

Ví dụ tạo message có header nghiệp vụ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderEvent> orderMessage(OrderEvent event) {
    return MessageBuilder.withPayload(event)
            .setHeader("event-id", "evt-101")
            .setHeader("correlation-id", "checkout-7842")
            .setHeader("event-type", "OrderCreated")
            .build();
}
~~~

Header `event-id` định danh một sự kiện; `correlation-id` liên kết nhiều service; `event-type` mô tả loại hợp đồng. Không sử dụng các biến thể `Id` hoặc `ID` làm header nghiệp vụ nếu có thể đặt tên riêng: `id` và `timestamp` là header đặc biệt của Spring Messaging, dễ gây xung đột mapper.

Mapper là một phần của hợp đồng tương tác. Chỉ chọn header được phép, giới hạn kiểu/kích thước, và giữ những header phục vụ tracing hoặc schema khi chúng thực sự cần đi qua broker. Một mapper viết thiếu có thể làm mất header dù producer đã đặt đúng.

## 7. Đăng ký Kafka header mapper

Kafka binder cho phép chỉ định tên bean `KafkaHeaderMapper` qua thuộc tính:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          header-mapper-bean-name: orderKafkaHeaderMapper
~~~

Nếu không khai báo tên, binder có cơ chế tìm bean mặc định `kafkaBinderHeaderMapper` theo kiểu tương ứng rồi dùng mapper mặc định của binder. Việc tự tạo bean `KafkaHeaderMapper` chung trong context không nhất thiết bảo đảm binder chọn đúng bean nếu dự án có nhiều bean; hãy đặt tên rõ ràng và cấu hình trên.

Ví dụ mapper giản lược chỉ truyền ba header kiểu String. Nó minh họa cách ánh xạ hai chiều và việc giới hạn whitelist:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaderMapper;
import org.springframework.messaging.MessageHeaders;

@Configuration(proxyBeanMethods = false)
class KafkaHeaderConfiguration {

    private static final List<String> ALLOWED =
            List.of("event-id", "correlation-id", "event-type");

    @Bean("orderKafkaHeaderMapper")
    KafkaHeaderMapper orderKafkaHeaderMapper() {
        return new KafkaHeaderMapper() {
            @Override
            public void fromHeaders(
                    MessageHeaders source, Headers target) {
                for (String name : ALLOWED) {
                    Object value = source.get(name);
                    if (value instanceof String text) {
                        target.add(name, text.getBytes(StandardCharsets.UTF_8));
                    }
                }
            }

            @Override
            public void toHeaders(
                    Headers source, Map<String, Object> target) {
                for (String name : ALLOWED) {
                    Header header = source.lastHeader(name);
                    if (header != null) {
                        target.put(name,
                                new String(header.value(),
                                        StandardCharsets.UTF_8));
                    }
                }
            }
        };
    }
}
~~~

**Phạm vi ví dụ:** mapper trên cố ý không truyền `contentType`, `traceparent` hoặc các header framework khác. Nó chỉ thích hợp để minh họa đường đi của ba header String. Trong ứng dụng thật, thay toàn bộ mapper mặc định bằng triển khai tối giản như vậy có thể làm hỏng conversion, tracing hoặc logic cần header khác. Nên ưu tiên cấu hình/điều chỉnh `BinderHeaderMapper` mặc định khi có thể, hoặc lập danh sách đầy đủ header cần truyền và kiểm thử với broker thực.

`spring.cloud.stream.kafka.binder.headerMapperBeanName` áp dụng trong phạm vi Kafka binder; đây không phải tùy chọn của Spring Cloud Stream chung hay của RabbitMQ/Pulsar.

### Trusted packages và kiểu header

Mapper dựa trên JSON có thể giải mã header thành đối tượng Java. Không mở rộng trusted packages thành `*` cho message từ nguồn không tin cậy. Với ID, correlation và tracing, nên dùng String hoặc các primitive đơn giản; với custom object, chỉ cho phép package cụ thể và kiểm tra hợp đồng serialization ở cả producer/consumer.

Với Kafka, `KafkaHeaders.KEY` là record key và có thể dùng để native partitioning. Nó không giống một header tùy ý có tên `partition-key`. Kiểm tra key bằng Kafka producer/consumer thực, tránh suy ra key chỉ từ header map.

## 8. RabbitMQ: tùy chỉnh AMQP header mapping

Spring Integration AMQP dùng `DefaultAmqpHeaderMapper` để ánh xạ Spring headers và AMQP message properties. Các properties như `contentType`, `correlationId`, `messageId`, routing key và delivery metadata có vị trí riêng; không nên copy tất cả native AMQP properties thành chuỗi tùy ý.

Ở tầng Spring Integration, mapper có thể chỉ định request/reply header names và pattern lọc. Ví dụ cấu hình cho outbound AMQP adapter theo quy ước ứng dụng:

~~~java
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

DefaultAmqpHeaderMapper amqpOutboundMapper() {
    DefaultAmqpHeaderMapper mapper =
            DefaultAmqpHeaderMapper.outboundMapper();
    mapper.setRequestHeaderNames(
            "event-id", "correlation-id", "event-type");
    return mapper;
}
~~~

Đoạn trên tạo đối tượng mapper ở cấp adapter. **Chỉ đăng ký bean này không đồng nghĩa Rabbit binder tự nhận và sử dụng nó**: cần gắn mapper vào đúng outbound endpoint/inbound adapter qua cơ chế cấu hình hoặc customizer được phiên bản binder hỗ trợ. Xem tài liệu Spring Integration AMQP và Rabbit binder tương ứng để xác định điểm chèn. Với cấu hình chỉ cần truyền String headers thông thường, mapper mặc định có thể đã đủ và không cần override.

Đối với nhiều consumer group, routing key và queue declaration của Rabbit binder ảnh hưởng mạnh hơn đến mở rộng số instance. Header mapper không tạo partition hoặc queue; phân phối cho Rabbit cần cấu hình partitioning và topology riêng.

## 9. Đăng ký PulsarHeaderMapper

Pulsar binder cho phép cung cấp bean kiểu `PulsarHeaderMapper` để thay mapper mặc định. `JsonPulsarHeaderMapper` hỗ trợ pattern lọc header và danh sách package tin cậy:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.pulsar.support.header.JsonPulsarHeaderMapper;
import org.springframework.pulsar.support.header.PulsarHeaderMapper;

@Configuration(proxyBeanMethods = false)
class PulsarHeaderConfiguration {

    @Bean
    PulsarHeaderMapper customPulsarHeaderMapper() {
        return JsonPulsarHeaderMapper.builder()
                .inboundPatterns("!secret", "*")
                .outboundPatterns(
                        "!id", "!timestamp", "!secret", "*")
                .trustedPackages("com.acme.events")
                .build();
    }
}
~~~

Pattern có thể dùng wildcard và phủ định `!`; **pattern đầu tiên khớp sẽ thắng**. Vì vậy `!secret` phải xuất hiện trước `*`. Giữ loại trừ `id` và `timestamp` trừ khi có lý do đặc biệt để truyền. Không đặt `trustedPackages("*")` khi nhận event từ đối tác hoặc hệ thống ngoài.

Pulsar user properties khác metadata nội bộ như message ID, topic, key hoặc publish time. Không giả định tùy chỉnh header mapper sẽ thay đổi cơ chế định tuyến key của Pulsar producer. Hãy kiểm tra message key, partitioned topic và subscription type riêng.

## 10. Cơ chế partitioning chung trong Spring Cloud Stream

Spring Cloud Stream chia quyết định partition làm hai bước:

1. `PartitionKeyExtractorStrategy` nhận `Message<?>` và trả về key.
2. `PartitionSelectorStrategy` nhận key và `partitionCount`, trả về partition index từ `0` đến `partitionCount - 1`.

Nếu logic đơn giản, có thể dùng SpEL mà không cần Java bean:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-out-0:
          destination: orders.normalized
          producer:
            partition-key-expression: payload.orderId
            partition-count: 12
~~~

Nếu quy tắc cần chuẩn hóa, composite key hoặc sharding, đăng ký bean chiến lược riêng giúp gom logic ở một nơi có thể unit test. Hai tùy chọn `partitionKeyExpression` và `partitionKeyExtractorName` loại trừ lẫn nhau. Tương tự, `partitionSelectorExpression` và `partitionSelectorName` cũng không được dùng đồng thời trên cùng binding.

## 11. Đăng ký `PartitionKeyExtractorStrategy` và `PartitionSelectorStrategy`

Giả sử ứng dụng cần giữ thứ tự trong phạm vi một đơn hàng; các đơn hàng độc lập của cùng tenant có thể phân tán. Composite key `tenantId:orderId` là lựa chọn hợp lý:

~~~java
import org.springframework.cloud.stream.binder.PartitionKeyExtractorStrategy;
import org.springframework.cloud.stream.binder.PartitionSelectorStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OrderPartitionConfiguration {

    @Bean("tenantOrderExtractor")
    PartitionKeyExtractorStrategy tenantOrderExtractor() {
        return message -> {
            if (!(message.getPayload() instanceof OrderEvent event)) {
                throw new IllegalArgumentException(
                        "Expected OrderEvent payload");
            }
            if (event.tenantId().isBlank() || event.orderId().isBlank()) {
                throw new IllegalArgumentException(
                        "Partition key fields must not be blank");
            }
            return event.tenantId().trim() + ":" + event.orderId().trim();
        };
    }

    @Bean("stableSelector")
    PartitionSelectorStrategy stableSelector() {
        return (key, count) -> {
            if (count <= 0 || key == null) {
                throw new IllegalArgumentException(
                        "Partition count and key must be valid");
            }
            return Math.floorMod(key.hashCode(), count);
        };
    }
}
~~~

Cấu hình chọn đúng hai bean bằng tên:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          content-type: application/vnd.acme.order-line
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: application/vnd.acme.order-line
          producer:
            partition-key-extractor-name: tenantOrderExtractor
            partition-selector-name: stableSelector
            partition-count: 12
~~~

Tên bean trong `@Bean("tenantOrderExtractor")` phải khớp giá trị `partition-key-extractor-name`. Tương tự, tên selector phải khớp `partition-selector-name`. Khi có nhiều chiến lược cùng kiểu bean, việc khai báo tên trên từng binding giúp tránh chọn nhầm bean hoặc lỗi ambiguous bean.

Selector ví dụ chỉ chuẩn hóa kết quả hash về khoảng không âm. Nếu hash mặc định đã đạt yêu cầu, không cần tạo selector mới; chỉ tạo custom bean khi cần một quy tắc có lý do rõ ràng. Key extractor nên **xác định và không có side effect**; không đọc thời gian hiện tại, random, round-robin counter hoặc trạng thái cục bộ nếu cùng thực thể cần giữ thứ tự.

### Phân biệt extractor và selector

Cho key `tenant-a:order-101` và 12 partition:

~~~text
Message<OrderEvent>
        |
        v
tenantOrderExtractor -> "tenant-a:order-101"
        |
        v
stableSelector(key, 12) -> một số từ 0 đến 11
        |
        v
Binder gửi tới partition tương ứng
~~~

Nếu extractor trả về key sai, selector đúng cũng không thể giữ thứ tự nghiệp vụ. Nếu extractor trả key đúng nhưng selector không ổn định giữa các instance, cùng key có thể bị gửi đến các partition khác nhau.

## 12. Khi nào dùng SpEL, khi nào dùng bean?

| Nhu cầu | Cách phù hợp | Ví dụ |
|---|---|---|
| Đọc một trường đơn giản | `partitionKeyExpression` | `payload.orderId` |
| Đọc một header đã chuẩn hóa | `partitionKeyExpression` | `headers['partitionKey']` |
| Ghép nhiều trường và validate | `PartitionKeyExtractorStrategy` | `tenantId:orderId` |
| Chia hot tenant thành shard | Extractor có thuật toán shard nhất quán | `tenantId + '#' + shard` |
| Hash mặc định đủ dùng | Không khai báo custom selector | Dùng selector mặc định |
| Cần tương thích hash giữa nhiều producer | `PartitionSelectorStrategy` có thuật toán được đặc tả | Hash chuẩn hóa và test cross-language |
| Nhiều output bindings khác nhau | Named bean trên từng binding | `tenantOrderExtractor` và `accountExtractor` |

SpEL ngắn, dễ cấu hình nhưng khó unit test các nhánh phức tạp. Bean Java rõ ràng hơn cho logic có validation, fallback và thuật toán hashing. Đừng lạm dụng custom selector chỉ vì có thể thay nó.

### Ví dụ key salting

Một tenant lớn có thể được chia thành nhiều shard khi các đơn hàng độc lập:

~~~java
String shardKey(OrderEvent event, int shards) {
    int shard = Math.floorMod(event.orderId().hashCode(), shards);
    return event.tenantId() + "#" + shard;
}
~~~

Salting **mất thứ tự toàn tenant**; nó chỉ giữ thứ tự của các event luôn vào cùng shard. Nếu hai đơn hàng cần cập nhật một aggregate duy nhất theo tenant, phải thiết kế bước tổng hợp hai giai đoạn hoặc giữ key cũ. Thay đổi số shard cũng có thể làm một đơn hàng chuyển shard; cần kế hoạch chuyển đổi để bảo toàn dữ liệu và thứ tự.

## 13. Những khác biệt quan trọng giữa Kafka, RabbitMQ và Pulsar

Khả năng phân vùng không hoàn toàn giống nhau ở ba binder:

| Chủ đề | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Khái niệm phân vùng gốc | Native topic partitions | Exchange/queue; queue không đồng nghĩa partition Kafka | Partitioned topic |
| Cách chọn key thông dụng | Kafka record key và native partitioner | Spring Cloud Stream partitioner + queue/routing convention | Pulsar message key và routing mode |
| Scale consumer | Group chia partitions giữa consumer | Nhiều consumer nhận từ queue hoặc chia queue theo index | Subscription type và partitioned topics |
| Giữ thứ tự | Trong một partition, theo thứ tự record được ghi | Phụ thuộc topology, consumer, prefetch và requeue | Phụ thuộc key, partition và subscription type |
| Thử nghiệm nên có | Key → partition, offset, group assignment | Routing key → queue, consumer/instance index | Message key → partition, subscription và ordering |

### Kafka: ưu tiên native key khi phù hợp

Kafka producer chọn partition dựa trên record key nếu không đặt partition cụ thể. Cách cấu hình thường được khuyến nghị khi muốn giữ thứ tự theo key là đưa key vào record bằng `KafkaHeaders.KEY`:

~~~java
Message<OrderEvent> output = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .build();
~~~

Hoặc khai báo Kafka binder producer:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          normalizeOrder-out-0:
            producer:
              message-key-expression: payload.orderId
~~~

Khi đó không cần bật generic `partition-key-extractor-name` trên cùng binding. Nếu dùng generic partitioning, Spring Cloud Stream tính partition theo hash của key do extractor trả về; thuật toán này **có thể khác** native Kafka partitioner nên cùng chuỗi key chưa chắc cùng partition so với một Kafka producer thuần.

Thay đổi `partitionCount` hoặc số partition thật có thể làm key được ánh xạ lại; không đổi âm thầm khi đang có dữ liệu cần giữ thứ tự hoặc state. Trên Kafka, `partition-count` của Spring Cloud Stream còn được dùng như gợi ý khi provision topic; không giả định thay property này sẽ tự thay mọi topic đã tồn tại.

### RabbitMQ: quan tâm cả phía producer và consumer

Generic partitioning giúp Spring Cloud Stream định tuyến tới các queue/shard theo partition index, nhưng consumer RabbitMQ có thể cần cấu hình `partitioned` cùng `instanceCount` và `instanceIndex`:

~~~yaml
spring:
  cloud:
    stream:
      instance-count: 4
      instance-index: 0
      bindings:
        consumeOrder-in-0:
          destination: orders.normalized
          group: order-worker
          consumer:
            partitioned: true
~~~

Ví dụ là cấu hình của **một instance**, index `0`. Các instance khác phải dùng index riêng (`1`, `2`, `3`) nếu deployment dùng cơ chế partitioning theo instance. Các instance cùng index có thể không nhận tải như dự kiến. Kiểm tra queue name, binding, routing key và consumer assignment thực tế theo Rabbit binder đang sử dụng.

Thêm consumer vào cùng queue không có nghĩa đã phân vùng theo key. Nếu yêu cầu thứ tự nghiêm ngặt theo aggregate, phải kiểm tra cách các message được phân phối giữa consumer và chính sách ACK/requeue.

### Pulsar: key và subscription type là hai lớp

Pulsar có partitioned topic và message routing riêng. Khi dùng `Key_Shared` subscription, các message cùng key được điều phối theo cơ chế của subscription; có thể xử lý song song nhiều key. Producer cần đặt key ổn định và dùng key-based batching hoặc tắt batching nếu yêu cầu Key_Shared của phiên bản broker đòi hỏi như vậy.

Custom partition strategy của Spring Cloud Stream không tự động thay Pulsar native router. Nếu ứng dụng dùng native encoding/schema và Pulsar key routing, hãy xác minh key thực sự được ghi vào message và partitioned topic có đủ partition; không kỳ vọng một `PartitionSelectorStrategy` Java chung sẽ điều khiển mọi quyết định của Pulsar broker.

### Kafka Streams binder: dùng đúng API riêng

Kafka Streams topology dùng Serde và task/partition model riêng. Nếu cần custom outbound partitioner cho Kafka Streams binder, dùng bean `StreamPartitioner` và tùy chọn `streamPartitionerBeanName` theo binder, thay vì mặc định áp dụng `PartitionSelectorStrategy` của message-channel Kafka binder cho topology.

## 14. Thứ tự xử lý, độ ổn định của key và triển khai nhiều instance

Một chiến lược phân vùng chỉ an toàn nếu các instance áp dụng cùng quy tắc:

- Cùng normalization: viết hoa/thường, trim, Unicode normalization và xử lý null.
- Cùng encoding: UTF-8 hoặc encoding được quy định, tránh phụ thuộc default charset.
- Cùng hash và seed: nếu producer có Java, Go và Python, thuật toán phải được mô tả độc lập với ngôn ngữ.
- Cùng shard count và partition mapping trong một giai đoạn triển khai.
- Cùng schema của trường dùng làm key.
- Cùng yêu cầu thứ tự: hiểu rõ cần thứ tự theo tenant, order hay account.

Ví dụ nếu instance A dùng key `tenant-a:order-101` còn instance B dùng `TENANT-A:order-101`, chúng có thể tạo hai partition khác nhau. Unit test ở mỗi instance không phát hiện lỗi này nếu không có test chung bằng fixture key.

### Cần thận trọng với hot key

Một key duy nhất có thể tạo hot partition dù topic có hàng chục partition. Tăng số instance không chia một key có ràng buộc cùng partition. Muốn chia tải, có thể đổi đơn vị key từ `tenantId` sang `orderId`, dùng composite key hoặc shard sau khi xác nhận được nới lỏng thứ tự toàn tenant.

Không dùng random key cho workflow cần idempotency/order. Tối ưu throughput phải bảo toàn hành vi nghiệp vụ; việc giảm lag nhưng làm sai thứ tự hoặc cập nhật trùng không phải cải thiện hợp lệ.

## 15. Đăng ký nhiều converter hoặc chiến lược trên cùng ứng dụng

Ứng dụng có thể đồng thời xử lý sự kiện JSON, định dạng đối tác và Protobuf:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder;routeInvoice
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          content-type: application/vnd.acme.order-line
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: application/vnd.acme.order-line
          producer:
            partition-key-extractor-name: tenantOrderExtractor
            partition-count: 12
        routeInvoice-in-0:
          destination: invoices.raw
          content-type: application/json
        routeInvoice-out-0:
          destination: invoices.normalized
          content-type: application/json
          producer:
            partition-key-extractor-name: invoiceExtractor
            partition-count: 12
~~~

Các function trên chỉ mang tính minh họa; application context cần có bean `normalizeOrder` và `routeInvoice`. Một bean converter riêng được đăng ký toàn context, do đó phải kiểm tra rằng nó chỉ nhận đúng MIME type và target type. Chiến lược phân vùng dùng bean name trên từng binding nên các luồng không vô tình dùng chung key.

Nếu ứng dụng dùng nhiều binder, có thể chỉ định:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-out-0:
          binder: kafka
        routeInvoice-out-0:
          binder: rabbit
~~~

Tên binder phải khớp phần định nghĩa binder của ứng dụng. Kafka header mapper chỉ có hiệu lực trong Kafka binder; RabbitMQ và Pulsar có cơ chế riêng. Không kỳ vọng một bean header mapper áp dụng cho cả ba transport.

## 16. Kiểm thử converter ở cấp unit

Kiểm tra round-trip với `toMessage`/`fromMessage` giúp xác nhận converter trả bytes đúng và đọc lại đúng record:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

class OrderLineMessageConverterTest {

    private final MessageConverter converter =
            new OrderLineMessageConverter();

    @Test
    void roundTrip() {
        OrderEvent event =
                new OrderEvent("tenant-a", "order-101", 250000L);
        var mime = MimeTypeUtils.parseMimeType(
                "application/vnd.acme.order-line");
        MessageHeaders headers = new MessageHeaders(
                Map.of(MessageHeaders.CONTENT_TYPE, mime));

        Message<?> encoded = converter.toMessage(event, headers);
        assertThat(encoded).isNotNull();
        assertThat(encoded.getPayload()).isInstanceOf(byte[].class);
        assertThat(new String(
                (byte[]) encoded.getPayload(),
                StandardCharsets.UTF_8))
                .isEqualTo("tenant-a|order-101|250000");

        Message<byte[]> incoming = MessageBuilder
                .withPayload((byte[]) encoded.getPayload())
                .setHeader(MessageHeaders.CONTENT_TYPE, mime)
                .build();

        OrderEvent decoded = (OrderEvent)
                converter.fromMessage(incoming, OrderEvent.class);
        assertThat(decoded).isEqualTo(event);
    }
}
~~~

Các test bổ sung nên kiểm tra trường trống, dấu phân cách sai, số tiền không hợp lệ, input byte array quá dài và MIME type khác. Nếu converter bị từ chối cho kiểu không hỗ trợ, test cần xác nhận nó không chiếm quyền của JSON converter thông thường.

## 17. Kiểm thử header mapper hai chiều

Kafka có thể kiểm tra mapper bằng `RecordHeaders` không cần broker:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.support.MessageBuilder;

class KafkaHeaderConfigurationTest {

    @Test
    void keepsAllowedHeaders() {
        var mapper = new KafkaHeaderConfiguration()
                .orderKafkaHeaderMapper();
        var source = MessageBuilder.withPayload("value")
                .setHeader("event-id", "evt-101")
                .setHeader("correlation-id", "checkout-7842")
                .setHeader("secret", "do-not-forward")
                .build();

        var kafkaHeaders = new RecordHeaders();
        mapper.fromHeaders(source.getHeaders(), kafkaHeaders);

        Map<String, Object> mapped = new HashMap<>();
        mapper.toHeaders(kafkaHeaders, mapped);

        assertThat(mapped).containsEntry("event-id", "evt-101");
        assertThat(mapped)
                .containsEntry("correlation-id", "checkout-7842")
                .doesNotContainKey("secret");
    }
}
~~~

Đoạn test minh họa đặt trong class test có JUnit Jupiter/AssertJ dependency. Unit test này xác nhận mapper tự viết và whitelist, nhưng chưa chứng minh broker/binder thực sự đang sử dụng bean. Phải bổ sung test có Kafka container và kiểm tra consumer nhận đúng header, cũng như content type/tracing mà application cần.

Với Pulsar, unit test nên kiểm tra `toPulsarHeaders` và `toSpringHeaders` qua message/fixture tương thích API của phiên bản Spring Pulsar. Với RabbitMQ, kiểm tra mapping từ `MessageHeaders` tới `MessageProperties` và ngược lại, sau đó kiểm chứng trên queue thật.

## 18. Kiểm thử partitioning strategy

Những đặc tính quan trọng là:

1. **Determinism:** cùng key, cùng số partition → cùng partition.
2. **Range:** index luôn nằm trong `[0, partitionCount - 1]`.
3. **Business grouping:** các event của cùng đơn hàng vào cùng key.
4. **Distribution:** tập dữ liệu đại diện không dồn quá nhiều vào một partition.
5. **Compatibility:** thuật toán giữa các producer và instance nhất quán.
6. **Migration:** thay partition count hoặc shard count có kế hoạch về ordering và state.

Ví dụ test selector trực tiếp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.stream.binder.PartitionSelectorStrategy;

class StableSelectorTest {

    private final PartitionSelectorStrategy selector =
            new OrderPartitionConfiguration().stableSelector();

    @Test
    void sameKeyAlwaysGetsSamePartition() {
        int first = selector.selectPartition("tenant-a:order-101", 12);
        int second = selector.selectPartition("tenant-a:order-101", 12);
        assertThat(second).isEqualTo(first);
    }

    @Test
    void resultIsWithinRange() {
        for (int i = 0; i < 1000; i++) {
            int partition = selector.selectPartition("order-" + i, 12);
            assertThat(partition).isBetween(0, 11);
        }
    }
}
~~~

Kiểm tra partition phân phối đều bằng một tập key ngẫu nhiên không đủ để chứng minh production sẽ cân bằng. Cần dùng sample traffic thật hoặc phân phối mô phỏng có hot tenant/hot account, và đo record, byte lẫn chi phí xử lý. Nếu một key chiếm 50% traffic, hash hoàn hảo vẫn có thể tạo hot partition.

### Test với Spring Integration Test Binder

Test Binder hỗ trợ kiểm tra `Function`/`Consumer`, content conversion và đường đi binding qua `InputDestination`/`OutputDestination`. Nó hữu ích để xác nhận các function và converter được chọn, nhưng không mô phỏng đầy đủ partition assignment, native Kafka header mapper, RabbitMQ routing hoặc Pulsar subscription.

Với custom partitioning, test bean trực tiếp và thêm broker integration test. Đừng dùng kết quả Test Binder làm bằng chứng rằng cùng key đã được ghi đúng partition ngoài broker.

## 19. Kiểm thử end-to-end với broker thực

Nên có một bộ integration test cho mỗi binder được triển khai, ví dụ Testcontainers:

| Kiểm thử | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Converter payload | Đọc DTO từ producer bytes và gửi ngược đúng wire format | Tương tự qua AMQP payload | Tương tự qua Pulsar `Schema.BYTES` nếu dùng framework conversion |
| Header round-trip | Custom KafkaHeaderMapper giữ đúng headers | AMQP properties và user headers đúng | PulsarHeaderMapper chuyển đúng user properties |
| Partition/routing | Đọc topic/partition và record key | Xác minh exchange/queue/routing key | Xác minh topic partition và message key |
| Scale group | Nhiều consumer chia Kafka partitions | Group/queue hoặc partition instance assignment | Subscription type và consumer distribution |
| Failure path | Conversion error, retry và DLT | Reject/requeue, DLX/DLQ | NACK/redelivery, DLQ |

Quy trình tích hợp:

1. Khởi chạy broker test đúng loại và version.
2. Khởi động ứng dụng với binder thật; xác nhận binder giả lập không vô tình thay thế.
3. Gửi message có `contentType`, event ID, correlation ID và key.
4. Nhận ở consumer và assert payload, header, key/partition hoặc routing metadata.
5. Tạo thêm message cùng key và xác nhận tính ổn định của phân vùng.
6. Gửi một message sai format để xác nhận chính sách lỗi, retry và DLQ.
7. Chạy nhiều consumer instance nếu hệ thống thực sự yêu cầu scale.

Chạy với message có kích thước và key distribution đại diện. Không chỉ assert broker nhận một message là đủ: các lỗi mapper/partition thường chỉ xuất hiện khi có nhiều kiểu header, nhiều producer hoặc thay đổi partition count.

## 20. Quan sát và xử lý lỗi trong môi trường mở rộng

Thêm extension sẽ tạo thêm một số loại lỗi đặc thù:

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Function nhận `byte[]` thay vì DTO | Content type sai hoặc bật native decoding | Đối chiếu header, binding content type, native flag và converter bean. |
| Converter đúng nhưng không được gọi | Payload đã cùng target type; converter khác bắt trước; native mode | Kiểm tra function signature và converter precedence. |
| JSON binding bắt đầu lỗi sau khi thêm converter | Custom converter hỗ trợ MIME/type quá rộng | Thu hẹp `supports` và supported MIME types. |
| Kafka thiếu `event-id` | Custom mapper quên truyền inbound/outbound | Kiểm tra cả hai chiều và binder mapper bean name. |
| Kafka mất trace context | Mapper chỉ whitelist vài header nghiệp vụ | Bổ sung propagation cần thiết hoặc tùy chỉnh mapper mặc định an toàn hơn. |
| Pulsar mất correlation ID | Pattern `!` đặt sau `*` hoặc mapper khác được chọn | Kiểm tra thứ tự pattern, bean và giá trị user properties. |
| Rabbit không nhận header mong muốn | Header mapper adapter/binder không được gắn đúng | Kiểm tra wiring và message properties ở broker. |
| Partition ngoài phạm vi | Selector trả index âm hoặc ≥ partitionCount | Dùng `Math.floorMod` và unit test range. |
| Cùng order vào nhiều partition | Key normalization, hash, encoding hoặc partition count khác nhau | So sánh quy ước và bản ghi metadata thực tế. |
| Thêm instance không tăng throughput | Một hot key hoặc ít partition hơn consumer | Đo lag theo partition, key skew và consumer assignment. |
| Retry làm dữ liệu bị xử lý sai thứ tự | Nhiều partition, requeue hoặc concurrency | Xác định ranh giới ordering và thiết kế idempotency. |
| Production lỗi nhưng test binder pass | Test không dùng broker/mapper native thật | Bổ sung Testcontainers hoặc broker test environment. |

Log chẩn đoán nên có tên binding, destination, content type, event ID, correlation ID, broker, partition hoặc queue và loại lỗi. Không dump toàn bộ message headers hoặc payload chứa thông tin nhạy cảm. Chỉ dùng exception stack trace khi phục vụ điều tra, và phân biệt lỗi conversion (không đọc được dữ liệu) với lỗi nghiệp vụ (đã đọc được nhưng xử lý thất bại).

## 21. Kế hoạch triển khai extension an toàn

Khi thay converter, mapper hoặc partition strategy của một luồng đang chạy, hãy triển khai như thay đổi giao thức:

1. Chốt hợp đồng payload, content type, header names/encoding và key semantics với các producer/consumer.
2. Thêm unit test cho converter, header round-trip và selector determinism.
3. Tạo test producer phiên bản mới với consumer phiên bản cũ và chiều ngược lại nếu phải hỗ trợ rolling upgrade.
4. Đảm bảo tất cả instance dùng cùng bean/config và hash algorithm trước khi chuyển lưu lượng.
5. Nếu key hoặc partition mapping thay đổi, đánh giá ordering, state store, changelog và lượng backlog hiện tại.
6. Cân nhắc dùng topic/version mới khi cần chuyển đổi không tương thích để tránh trộn hai semantics trên một topic.
7. Chạy canary với lưu lượng nhỏ, quan sát conversion error, DLQ, header missing rate và lag theo partition.
8. Chuyển lưu lượng theo kế hoạch, kiểm tra idempotency, duplicate và thứ tự ở consumer.
9. Giữ khả năng rollback nhưng hiểu rằng rollback key partitioning có thể cần xử lý dữ liệu được tạo bằng mapping mới.

Không cập nhật converter và partition strategy đồng thời nếu không cần thiết; triển khai từng thay đổi theo bước giúp dễ xác định nguyên nhân nếu luồng bị lỗi.

## 22. Checklist hoàn thành

- [ ] Đã phân biệt converter, header mapper, extractor và selector.
- [ ] Custom converter chỉ hỗ trợ MIME type và target class cần thiết.
- [ ] Converter trả/nhận bytes theo hợp đồng khi dùng framework conversion.
- [ ] `contentType` header và binding config không mâu thuẫn.
- [ ] Native encoding/decoding đã được kiểm tra để tránh bypass converter ngoài ý muốn.
- [ ] Metadata nghiệp vụ có header names rõ ràng và không dùng tên reserved.
- [ ] Kafka header mapper được đăng ký đúng bean name và giữ đủ header cần dùng.
- [ ] Rabbit AMQP mapper được gắn vào đúng adapter hoặc binder extension point khi custom.
- [ ] PulsarHeaderMapper loại trừ header nhạy cảm, chỉ tin cậy package cần thiết.
- [ ] `partition-key-extractor-name` và `partition-selector-name` khớp bean.
- [ ] Không dùng đồng thời expression và bean name cho cùng chức năng.
- [ ] Selector luôn trả partition hợp lệ và deterministic.
- [ ] Hash/encoding/key normalization nhất quán trên mọi instance.
- [ ] Ranh giới ordering nghiệp vụ đã được xác nhận.
- [ ] Kafka native partitioner, Rabbit queue routing và Pulsar Key_Shared không bị nhầm là một cơ chế.
- [ ] Unit test và real-broker integration test đã kiểm tra converter/header/partition.
- [ ] Kịch bản retry, DLQ, rolling upgrade và rollback đã được xem xét.
- [ ] Monitoring theo dõi conversion error, missing header, skew và consumer lag.

## Tổng kết

Spring Cloud Stream cho phép tùy chỉnh sâu mà vẫn giữ mô hình hàm `Supplier/Function/Consumer`: `MessageConverter` quản lý định dạng payload, header mapper bảo vệ và ánh xạ metadata, còn extractor/selector quyết định phân phối key trong cơ chế partitioning chung. Những bean này cần được đăng ký với tên, MIME type và phạm vi rõ ràng. Với Kafka, RabbitMQ và Pulsar, phải kiểm tra thêm cơ chế native của từng broker vì chúng có cách serialize, định tuyến và scale consumer khác nhau. Một thay đổi được coi là thành công khi payload đọc đúng, header không thất lạc, partitioning ổn định và thứ tự nghiệp vụ vẫn được bảo đảm khi hệ thống mở rộng.

## Tài liệu tham khảo

- [Spring Cloud Stream — User-defined Message Converters](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-user-defined-message-converters.html)
- [Spring Cloud Stream — Content Type and Message Conversion](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/mechanics.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder Partitioning](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html)
- [Spring Cloud Stream — Kafka Header Mapper Tips](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html)
- [Spring Integration — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Pulsar — Header Mapping](https://docs.spring.io/spring-pulsar/reference/reference/pulsar-header.html)

