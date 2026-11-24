# Serialization và sự khác nhau giữa dữ liệu trước và sau chuyển đổi

Trong một hệ thống giao tiếp bằng thông điệp, **producer** có thể tạo một đối tượng Java hoàn toàn hợp lệ nhưng **consumer** vẫn không đọc được sự kiện. Nguyên nhân có thể nằm ở bước **serialization**: tên trường đổi, số bị mất độ chính xác, thời điểm được chuyển thành dạng khác, thuộc tính `null` bị lược bỏ, header sai `contentType` hoặc hai phía dùng serializer/deserializer không tương thích. **Spring Cloud Contract** giúp mô tả và kiểm chứng hành vi trao đổi thông điệp, nhưng để sử dụng tốt, cần biết chính xác **dữ liệu trước chuyển đổi** và **dữ liệu thật sự đi qua kênh truyền** khác nhau thế nào.

Bài thuộc chương **Hợp đồng thông điệp** của mô-đun **SPRING_CLOUD_CONTRACT**. Mô-đun sử dụng **Groovy/YAML DSL** để viết hợp đồng HTTP hoặc messaging, sinh **producer tests**, phát hành **stub**, dùng **Stub Runner** cho consumer và kết hợp các bước này trong CI để phát hiện thay đổi API/sự kiện không tương thích. Trọng tâm ở đây là quá trình **domain object → Spring Message → payload trên đường truyền → object của consumer**, cách xác định phạm vi của hợp đồng và cách bổ sung phép kiểm serialization thực sự.

## 1. Bốn lớp dữ liệu trong một thông điệp

Giả sử **Order Service** phát sự kiện `OrderCreated` để **Billing Service** tạo hóa đơn. Dòng dữ liệu có thể như sau:

~~~mermaid
flowchart LR
    A["Domain event trong Java"] --> B["Spring Message với payload + headers"]
    B --> C["Message converter / serializer"]
    C --> D["Broker: bytes + metadata"]
    D --> E["Deserializer / converter phía consumer"]
    E --> F["DTO / domain event consumer"]
    F --> G["Xử lý nghiệp vụ"]
~~~

| Tầng | Ví dụ | Điều cần chú ý |
| --- | --- | --- |
| **Đối tượng trong bộ nhớ producer** | `OrderCreated("ORD-1042", 125000L, Instant...)` | Kiểu Java, getter/record, null, enum, quan hệ object. |
| **Spring Message** | `Message<OrderCreated>` với header `eventType=OrderCreated` | `payload` và `headers` là hai phần riêng; message có thể chưa được serialize. |
| **Dữ liệu trên đường truyền** | JSON UTF-8 `byte[]` hoặc Avro/Protobuf bytes | Tên trường, kiểu JSON, cách biểu diễn timestamp/decimal, encoding, schema ID. |
| **Dữ liệu sau giải mã** | `OrderCreatedV1` hoặc DTO của Billing | Mapping field, kiểu số, ngày giờ, cấu hình deserializer, giá trị mặc định. |

**Thông điệp trên broker không phải là object Java nguyên trạng.** Một `Long` trong bộ nhớ có thể thành số JSON; `Instant` có thể thành chuỗi thời gian; `null` có thể được serialize thành `null` hoặc không xuất hiện tùy cấu hình. Những metadata như Kafka key, partition, AMQP headers hay content type cũng có cách lưu khác nhau theo transport và binder.

Hai phía có thể viết bằng hai ngôn ngữ khác nhau. Vì vậy, hợp đồng nên mô tả **dạng dữ liệu và ý nghĩa mà hai bên trao đổi**, không chỉ tên class nội bộ của producer.

## 2. Một sự kiện mẫu trước và sau serialization

Ta chọn sự kiện nghiệp vụ có cấu trúc đơn giản, ổn định:

| Trường | Kiểu ý nghĩa | Giá trị mẫu |
| --- | --- | --- |
| `eventId` | Mã sự kiện duy nhất (string) | `evt-00042` |
| `orderId` | Mã đơn (string) | `ORD-1042` |
| `amountMinor` | Số tiền theo đơn vị nhỏ nhất (integer) | `125000` |
| `occurredAt` | Thời điểm UTC theo RFC 3339/ISO-8601 | `2026-01-15T10:20:30Z` |
| `note` | Ghi chú tùy chọn (string hoặc null, theo quy ước) | `null` |

Đối tượng Java producer có thể là:

~~~java
package com.acme.orders.events;

import java.time.Instant;

public record OrderCreated(
    String eventId,
    String orderId,
    long amountMinor,
    Instant occurredAt,
    String note
) {}
~~~

Producer tạo một instance:

~~~java
OrderCreated event = new OrderCreated(
    "evt-00042",
    "ORD-1042",
    125000L,
    Instant.parse("2026-01-15T10:20:30Z"),
    null
);
~~~

Nếu serializer được cấu hình xuất thời gian ISO-8601 và **giữ trường null**, payload JSON kỳ vọng:

~~~json
{
  "eventId": "evt-00042",
  "orderId": "ORD-1042",
  "amountMinor": 125000,
  "occurredAt": "2026-01-15T10:20:30Z",
  "note": null
}
~~~

**Đây là quy ước wire format cho ví dụ**, không phải cam kết rằng mọi cấu hình Jackson đều tạo chính xác JSON này. Ví dụ, nếu dùng `JsonInclude.Include.NON_NULL`, `note` có thể **biến mất**; nếu không cấu hình Java Time phù hợp, `Instant` có thể không serialize được hoặc được biểu diễn theo cách khác. Vì thế, phải kiểm **output của serializer được dùng trong ứng dụng thật**.

## 3. Spring Message, payload, headers và dữ liệu broker

Trong Spring, `org.springframework.messaging.Message<T>` là một **vỏ thông điệp** gồm `payload` và `headers`. Ví dụ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
    .setHeader("eventType", "OrderCreated")
    .setHeader("schemaVersion", 1)
    .build();
~~~

Ở thời điểm này, `message.getPayload()` vẫn là **OrderCreated object**. Nó chưa tự động là một chuỗi JSON hoặc một `byte[]`; bước chuyển đổi phụ thuộc framework/binder/serializer thực thi khi gửi.

Ví dụ minh họa cách một codec JSON riêng biến payload thành bytes:

~~~java
byte[] payloadBytes = objectMapper.writeValueAsBytes(message.getPayload());
String text = new String(payloadBytes, StandardCharsets.UTF_8);
~~~

Phần trên chỉ serialize **payload**, không tự biến toàn bộ `MessageHeaders` thành một object JSON. Header `eventType`, `schemaVersion` và `contentType` thường được xử lý theo cơ chế metadata của transport. **Không mặc định suy ra** chúng nằm trong JSON body.

| Thành phần | Trong ví dụ | Khi triển khai cần xác nhận |
| --- | --- | --- |
| Message payload trước khi chuyển đổi | `OrderCreated` | Có phải Java object, String, `byte[]` hay CloudEvent không? |
| Message payload sau khi chuyển đổi | JSON bytes | Có đúng serializer mong đợi, đúng charset và schema không? |
| `contentType` | `application/json` | Header được chuyển thành dạng nào ở broker và được consumer/binder hiểu ra sao? |
| `eventType` | `OrderCreated` | Nằm ở transport header hay body? Consumer dựa vào trường nào? |
| `schemaVersion` | `1` | Là số hay chuỗi ở transport? Quy tắc nâng phiên bản? |
| Kafka key/partition, AMQP routing key | Tùy transport | Có là một phần giao tiếp phải cam kết hay chỉ cấu hình hạ tầng? |

Nếu producer tạo `Message<String>` đã chứa JSON, framework có thể tiếp tục **serialize String** hoặc xử lý như text/raw bytes tùy content type và native encoding. Tránh các lỗi như **double serialization**: chuỗi JSON `{"orderId":"ORD-1042"}` bị gửi thành một **JSON string** có dấu nháy và ký tự escape thay vì một **JSON object**.

## 4. Serialization thay đổi dữ liệu ở những điểm nào?

Đối với JSON, thay đổi có thể đến từ serializer, annotation, naming strategy, formatter, hoặc kiểu DTO.

| Giá trị trước chuyển đổi | Có thể thành gì trên đường truyền | Rủi ro đối với consumer |
| --- | --- | --- |
| `Instant.parse("2026-01-15T10:20:30Z")` | Chuỗi ISO-8601 hoặc số timestamp | Consumer parse sai hoặc lệch múi giờ. |
| `BigDecimal("125000.00")` | JSON number `125000.00`, `125000` hoặc chuỗi | Mất scale/ngữ nghĩa tiền tệ, lỗi chuyển kiểu. |
| Java `long amountMinor` | JSON number `125000` | Consumer dùng kiểu số hẹp, tràn hoặc mất chính xác. |
| `enum OrderStatus.CREATED` | `"CREATED"` hoặc giá trị được tùy biến | Consumer không nhận ra enum sau khi đổi cách serialize. |
| `String note = null` | `"note":null` hoặc **thiếu khóa `note`** | Hai trạng thái có thể mang ý nghĩa khác nhau. |
| Java field `orderId` | JSON `orderId` hoặc `order_id` | Consumer binding không nhận trường nếu naming strategy đổi. |
| Collection/Map | JSON array/object | Thứ tự array, phần tử trùng, null trong collection. |
| `byte[]` | Binary bytes, Base64 text trong JSON | Consumer nhầm payload bytes với text/base64. |

**Nguyên tắc thực hành:** những trường mà consumer thật sự đọc phải được kiểm **tại ranh giới giao tiếp**. So object Java trước khi serialize chỉ kiểm đối tượng; nó chưa chứng minh JSON bytes hoặc nội dung thực trên broker đúng hợp đồng.

### 4.1. Object field missing khác explicit null

Hai payload JSON khác nhau:

~~~json
{"orderId":"ORD-1042","note":null}
~~~

~~~json
{"orderId":"ORD-1042"}
~~~

Ở payload đầu, `note` **có mặt** với JSON `null`; payload sau **không có khóa `note`**. Nếu API sự kiện quy định `null` là “đã xóa ghi chú”, còn thiếu khóa là “không gửi cập nhật”, thì việc bật `NON_NULL` có thể gây **breaking change** dù `OrderCreated.note()` trong Java vẫn là `null`.

Với Jackson `JsonNode`:

~~~java
JsonNode withNull = objectMapper.readTree(
    "{\"orderId\":\"ORD-1042\",\"note\":null}"
);
JsonNode withoutNote = objectMapper.readTree(
    "{\"orderId\":\"ORD-1042\"}"
);

assert withNull.has("note");
assert withNull.get("note").isNull();
assert !withoutNote.has("note");
~~~

`hasNonNull("note")` là `false` cho **cả hai** trường hợp, nên không dùng nó để kiểm sự hiện diện của trường. Đặc biệt với event cập nhật một phần, hãy định nghĩa rõ sự khác biệt giữa **missing**, **null**, **chuỗi rỗng** và **giá trị thật**.

### 4.2. Số nguyên, số thực và tiền tệ

JSON có kiểu **number**, không phân biệt trực tiếp Java `long`, `int` hay `BigDecimal` theo class name. Consumer có thể parse JSON number thành `Double`, `Long`, `BigDecimal` hoặc một kiểu khác tùy runtime.

Đối với tiền, ví dụ dùng **`amountMinor=125000`** để tránh dùng số thực dấu phẩy động làm đơn vị lưu trữ. Nếu hệ thống trao đổi giá trị decimal, hãy thống nhất **đơn vị tiền, scale, quy tắc làm tròn, max/min và cách biểu diễn**. Không dùng regex chung chung cho số rồi kết luận đã bảo vệ tính chính xác kế toán.

### 4.3. Thời gian, timezone và độ chính xác

Ba biểu diễn:

~~~text
2026-01-15T10:20:30Z
2026-01-15T17:20:30+07:00
2026-01-15T10:20:30.000Z
~~~

có thể chỉ cùng một thời điểm (tùy phần phân số giây) nhưng **khác chuỗi ký tự**. Hợp đồng cần nói rõ consumer yêu cầu **cùng thời điểm** hay **đúng định dạng chuỗi**. Nếu producer thay ISO string bằng epoch milliseconds, đó thường là thay đổi schema, dù cả hai biểu diễn cùng thời gian về mặt toán học.

### 4.4. Header có thể bị converter/broker biến đổi

Không phải mọi header trong `MessageHeaders` đều tồn tại nguyên vẹn trên broker. Một số header nội bộ có thể bị lọc, chuyển kiểu hoặc ánh xạ theo binder. Nếu consumer dựa vào `eventType`, `correlationId` hoặc `schemaVersion`, chúng cần nằm trong **hợp đồng và kiểm thử qua kênh vận chuyển thực tế**, không chỉ trong `MessageBuilder` trước khi gửi.

## 5. Groovy DSL cho hợp đồng message output

Ví dụ Order Service có một thao tác nghiệp vụ làm phát sự kiện. Hợp đồng có thể đặt tại `src/test/resources/contracts/messages/order_created.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    description 'Phát OrderCreated v1 cho Billing Service'

    input {
        triggeredBy('publishOrderCreated()')
    }

    outputMessage {
        sentTo('orders.created')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'OrderCreated')
            header('schemaVersion', 1)
        }
        body(
            eventId: 'evt-00042',
            orderId: 'ORD-1042',
            amountMinor: 125000,
            occurredAt: '2026-01-15T10:20:30Z',
            note: null
        )
    }
}
~~~

Đây là **hợp đồng thông điệp**, không phải HTTP contract:

- `input.triggeredBy('publishOrderCreated()')` yêu cầu generated producer test có thể gọi một **phương thức kích hoạt sự kiện** từ lớp base test; tên method phải tồn tại và phù hợp cấu hình.
- `outputMessage.sentTo('orders.created')` chỉ **destination/đích** của thông điệp theo ngữ nghĩa messaging adapter được dùng.
- `headers` mô tả metadata consumer cần đọc; tên và kiểu thực sau mapping phải được xác nhận theo binder/transport.
- `body` mô tả **payload hợp đồng** mà receiver kỳ vọng sau khi converter phù hợp đã xử lý. Phần này **không tự bảo đảm** bytes trên Kafka/RabbitMQ đúng nếu chưa xác minh serialization thực.
- `label` là định danh thuận tiện khi trigger messaging stub; không đồng nghĩa broker topic hay routing key.

**Lưu ý phiên bản và adapter:** cấu trúc hợp đồng trên dùng các thành phần messaging Groovy DSL thông dụng của Spring Cloud Contract. Cần đối chiếu khả năng plugin, message verifier/adapter và binder ở **phiên bản dự án thực tế**, đặc biệt là cách `sentTo` được ánh xạ với destination, cách `contentType` được giữ lại và cách xử lý `null` trong body.

Một hợp đồng hợp lệ **không tự làm producer phát message**. Muốn generated producer test chạy đúng, cần cài đặt đường kích hoạt và kênh nhận thông điệp trong môi trường test.

## 6. Dùng YAML DSL để mô tả cùng message

Nhóm có thể chọn **YAML DSL** thay vì Groovy. Tùy phiên bản Spring Cloud Contract, khả năng và cú pháp mô tả messaging ở YAML cần kiểm theo tài liệu/toolchain, vì không nên giả định tất cả cấu trúc Groovy đều có bản dịch một-một.

Ví dụ **ý định tương đương** trong YAML DSL:

~~~yaml
description: Phát OrderCreated v1 cho Billing Service
label: orderCreatedV1
input:
  triggeredBy: publishOrderCreated()
outputMessage:
  sentTo: orders.created
  headers:
    contentType: application/json
    eventType: OrderCreated
    schemaVersion: 1
  body:
    eventId: evt-00042
    orderId: ORD-1042
    amountMinor: 125000
    occurredAt: "2026-01-15T10:20:30Z"
    note: null
~~~

**Đây là bản minh họa cấu trúc YAML messaging để thảo luận**, không thay thế bước kiểm tra parser của phiên bản Spring Cloud Contract đang dùng. Trước khi áp dụng, hãy xác minh chính xác schema YAML của plugin, chạy bước sinh test/stub, kiểm body và headers thực. **Không được xem “YAML parse thành công” là bằng chứng hợp đồng messaging đã được công cụ nạp và thực thi.**

Khi thực hành, chọn **một DSL có hiệu lực** cho cùng một event. Đừng đặt cả Groovy và YAML mô tả cùng trường hợp vào đường dẫn plugin quét nếu không muốn sinh trùng generated tests/stubs hoặc hai đặc tả bị lệch khi sửa.

## 7. Thiết lập đường phát message ở producer

Giả sử ứng dụng dùng **Spring Cloud Stream** với `StreamBridge` để phát event. Đường phát có thể được tổ chức:

~~~java
package com.acme.orders;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

@Service
public class OrderEventPublisher {
    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publishOrderCreated() {
        OrderCreated event = new OrderCreated(
            "evt-00042",
            "ORD-1042",
            125000L,
            java.time.Instant.parse("2026-01-15T10:20:30Z"),
            null
        );

        Message<OrderCreated> message = MessageBuilder
            .withPayload(event)
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
            .setHeader("eventType", "OrderCreated")
            .setHeader("schemaVersion", 1)
            .build();

        boolean accepted =
            streamBridge.send("ordersCreated-out-0", message);
        if (!accepted) {
            throw new IllegalStateException("Cannot send OrderCreated");
        }
    }
}
~~~

Giả sử `OrderCreated` là record ở mục 2. `StreamBridge.send(...)` dùng **tên output binding**, không phải lúc nào cũng là tên broker topic trực tiếp. Có thể cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        ordersCreated-out-0:
          destination: orders.created
          content-type: application/json
~~~

Trong hợp đồng, `sentTo('orders.created')` biểu diễn đích thông điệp; trong code, `ordersCreated-out-0` là binding của StreamBridge. Cần thiết lập **message verifier adapter** và binder/test binder sao cho đích mà generated test quan sát được **trùng với destination được contract mô tả**. Không suy rằng chỉ cần chuỗi giống nhau là mọi binder đã được kết nối chính xác.

### 7.1. Lớp base test làm nhiệm vụ gì?

Generated producer test cần một method `publishOrderCreated()` để kích hoạt hành vi. Lớp cơ sở có thể có phần sau:

~~~java
@SpringBootTest
public abstract class MessageContractBase {
    @Autowired
    private OrderEventPublisher publisher;

    public void publishOrderCreated() {
        publisher.publishOrderCreated();
    }
}
~~~

Đoạn này chỉ minh họa **đường kích hoạt**. Để Contract Verifier thực sự thu thập message đã gửi, dự án còn cần **cấu hình messaging test adapter, binder hoặc MessageVerifier** được phiên bản Spring Cloud Contract hỗ trợ. Tùy transport/binder, có thể dùng test binder, fake channel hoặc broker test container. **Một base test chỉ có method trigger mà không có kênh capture thông điệp sẽ chưa đủ.**

Nếu producer phát message bất đồng bộ, test cần chờ **đúng message đã được phát** với timeout xác định, không dựa vào `Thread.sleep` đoán thời gian. Nếu có nhiều message trên cùng destination, test phải phân biệt theo `eventId`/header hoặc fixture.

## 8. Generated producer test kiểm payload ở lớp nào?

Sau khi cấu hình đúng, Contract Verifier có thể tạo test có ý nghĩa:

1. Gọi `publishOrderCreated()` trong base test.
2. Quan sát message mà producer phát tới `orders.created` thông qua adapter tương ứng.
3. Đối chiếu `headers` theo hợp đồng.
4. Đối chiếu `body` đã được converter/adapter trình bày cho test với body mong đợi.

Tuy nhiên, **mức độ bảo đảm phụ thuộc điểm quan sát**. Nếu adapter test nhận `Message<OrderCreated>` trước khi binder chuyển thành JSON bytes, test có thể **PASS** dù JSON serializer thực đang phát tên trường sai ở broker production. Nếu adapter quan sát sau serialization, nó có thể kiểm thêm phần wire format. **Phải mở generated test, cấu hình message converter và đường gửi thật để biết đang quan sát ở đâu.**

| Cấp kiểm thử | Phát hiện tốt | Điều có thể bị bỏ sót |
| --- | --- | --- |
| Unit test của event object | Field logic, kiểu Java, mapping từ domain. | JSON bytes, transport headers, binder. |
| Generated messaging contract test tại Spring Message abstraction | Đích, headers và body logic đã định nghĩa. | Serializer transport nếu test binder không serialize thật. |
| Serialization test với ObjectMapper thực | Tên JSON field, null/missing, định dạng timestamp và kiểu số. | Kafka/AMQP header mapping hoặc broker settings. |
| Integration test với binder/broker test | Dữ liệu trên transport, header/codec, định tuyến và deserialization. | Những điều kiện vận hành ngoài phạm vi test: throughput, retry dài hạn, version phối hợp. |
| Consumer test với stub | Consumer nhận và xử lý message mẫu. | Producer thật đã gửi đúng wire bytes hay chưa nếu producer tests không kiểm. |

**Một bộ kiểm thử mạnh kết hợp các lớp**: không kỳ vọng Contract Verifier tự chứng minh mọi đặc tính của Jackson, serializer, broker và toàn bộ giao diện triển khai.

## 9. Kiểm serialization thật bằng Jackson

Ví dụ kiểm JSON codec mà producer sử dụng. Nếu `ObjectMapper` lấy từ Spring Boot context đã có module hỗ trợ Java Time, một bài test có thể:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.nio.charset.StandardCharsets;
import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OrderCreatedSerializationTest {
    @Autowired ObjectMapper objectMapper;

    @Test
    void serializesWireContractAsExpected() throws Exception {
        OrderCreated event = new OrderCreated(
            "evt-00042", "ORD-1042", 125000L,
            Instant.parse("2026-01-15T10:20:30Z"), null
        );

        byte[] bytes = objectMapper.writeValueAsBytes(event);
        JsonNode json = objectMapper.readTree(bytes);

        assertThat(json.get("eventId").asText()).isEqualTo("evt-00042");
        assertThat(json.get("orderId").asText()).isEqualTo("ORD-1042");
        assertThat(json.get("amountMinor").isIntegralNumber()).isTrue();
        assertThat(json.get("amountMinor").longValue()).isEqualTo(125000L);
        assertThat(json.get("occurredAt").asText())
            .isEqualTo("2026-01-15T10:20:30Z");
        assertThat(json.has("note")).isTrue();
        assertThat(json.get("note").isNull()).isTrue();

        String wireText = new String(bytes, StandardCharsets.UTF_8);
        assertThat(wireText).contains("\"orderId\"");
    }
}
~~~

Test này xác minh **payload JSON** từ một `ObjectMapper` được inject trong test context. Nếu ứng dụng thực dùng **serializer khác** cho Spring Cloud Stream hoặc Kafka, cần kiểm chính serializer đó: test Jackson mặc định không bảo vệ một producer sử dụng Avro/Protobuf hoặc native encoding.

Đặc biệt, assertion `json.has("note")` là chủ ý. Nếu bật `NON_NULL` và field bị bỏ khỏi JSON, test **FAIL**, vì hợp đồng ví dụ yêu cầu **explicit JSON null**. Nếu API của nhóm quy định note không có mặt khi null, hãy đổi hợp đồng và test theo quy ước đó, không áp đặt lựa chọn từ ví dụ.

### 9.1. So sánh cấu trúc JSON thay vì chuỗi nguyên văn

Hai payload:

~~~json
{"eventId":"evt-00042","orderId":"ORD-1042"}
~~~

~~~json
{"orderId":"ORD-1042","eventId":"evt-00042"}
~~~

có **cùng ý nghĩa object JSON** dù thứ tự khóa khác nhau. Nếu giao thức không bắt buộc canonical JSON, hãy parse và so kiểu/giá trị các trường thay vì assert chuỗi bytes bằng nhau. Ngược lại, với **chữ ký số trên bytes** hoặc một protocol đòi canonical encoding, định dạng bytes thực sự là một phần yêu cầu và cần test tương ứng.

## 10. Kiểm deserialization ở consumer

Giả sử Billing có một DTO độc lập, không dùng chung class của producer:

~~~java
package com.acme.billing.events;

import java.time.Instant;

public record BillingOrderCreatedV1(
    String eventId,
    String orderId,
    long amountMinor,
    Instant occurredAt,
    String note
) {}
~~~

Một test consumer có thể đọc payload theo wire format đã thỏa thuận:

~~~java
@Test
void readsOrderCreatedV1Json() throws Exception {
    String payload = """
        {
          "eventId":"evt-00042",
          "orderId":"ORD-1042",
          "amountMinor":125000,
          "occurredAt":"2026-01-15T10:20:30Z",
          "note":null
        }
        """;

    BillingOrderCreatedV1 decoded = objectMapper.readValue(
        payload, BillingOrderCreatedV1.class
    );

    assertThat(decoded.orderId()).isEqualTo("ORD-1042");
    assertThat(decoded.amountMinor()).isEqualTo(125000L);
    assertThat(decoded.occurredAt())
        .isEqualTo(Instant.parse("2026-01-15T10:20:30Z"));
    assertThat(decoded.note()).isNull();
}
~~~

**Giới hạn quan trọng:** ở DTO chỉ có `String note`, kết quả `note()==null` **không phân biệt** payload chứa `"note":null` với payload **không chứa `note`**. Nếu consumer cần phân biệt, hãy đọc `JsonNode`/`Map.containsKey` hoặc dùng DTO/deserializer có trạng thái field presence, rồi kiểm riêng cả hai trường hợp.

Nếu consumer sử dụng Spring Cloud Stream functional consumer như `Consumer<Message<BillingOrderCreatedV1>>`, framework/binder có thể chuyển bytes thành DTO **trước khi code consumer chạy**. Khi kiểm tương thích, phải xác định **đoạn mapping/deserialization nào do binder thực hiện** và nên có một bài integration test đi qua chính binder hoặc adapter đang sử dụng.

## 11. Stub Runner cho messaging: mô phỏng sự kiện, không phải HTTP

Với HTTP, Stub Runner có thể khởi động WireMock server từ stub artifact. Với **message contracts**, cách phát message stub cần **messaging integration phù hợp**; nó không tự biến sự kiện thành một HTTP endpoint. Một hợp đồng có `label 'orderCreatedV1'` có thể được dùng để kích hoạt thông điệp mẫu trong bài test consumer.

Ví dụ ý tưởng JUnit test phía Billing:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingMessageContractTest {

    @Autowired StubTrigger stubTrigger;
    @Autowired BillingEventProbe billingProbe;

    @Test
    void handlesOrderCreated() {
        stubTrigger.trigger("orderCreatedV1");

        BillingOrderCreatedV1 received =
            billingProbe.awaitOrder("ORD-1042");
        assertThat(received.amountMinor()).isEqualTo(125000L);
    }
}
~~~

Đây là **khung test minh họa**: `BillingEventProbe` và `awaitOrder(...)` phải được dự án triển khai, có timeout hữu hạn và gắn vào đúng kênh mà consumer sử dụng; imports và dependencies cho Stub Runner/messaging cũng cần cấu hình phù hợp. Cơ chế `StubTrigger` chỉ có ý nghĩa khi plugin/binder đã kết nối event stub với nơi consumer nhận, không tự khởi động Kafka hay RabbitMQ hoặc bảo đảm listener nhận message.

Với `LOCAL`, artifact `stubs` phải được producer cài vào Maven local; CI đa máy thường publish stub và dùng `REMOTE` cùng `repositoryRoot`/credentials. **Ghim version** để test tái lập, không luôn dùng bản mới nhất mà không biết producer nào đã phát hành.

**Điều consumer test bảo vệ:** mã nhận/deserialize/định tuyến/xử lý của Billing có thể hoạt động với **mẫu sự kiện trong hợp đồng**. **Điều nó không chứng minh:** Order Service thật đã serialise và gửi bytes đúng trên broker, hoặc broker bảo đảm delivery/ordering/retry trong mọi tình huống. Các phần đó cần generated producer tests và integration tests tương ứng.

## 12. Khi message contract dùng input từ broker

Không phải mọi messaging contract bắt đầu từ một phương thức `triggeredBy(...)`. Có tình huống producer nhận **một message đầu vào** rồi phát **message đầu ra**. Ở Groovy DSL, khái niệm có thể biểu đạt bằng:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'invoiceRequestHandled'

    input {
        messageFrom('billing.invoice.request')
        messageBody(
            orderId: 'ORD-1042'
        )
        messageHeaders {
            header('contentType', 'application/json')
        }
    }

    outputMessage {
        sentTo('billing.invoice.created')
        headers {
            header('contentType', 'application/json')
        }
        body(
            orderId: 'ORD-1042',
            invoiceStatus: 'CREATED'
        )
    }
}
~~~

Trong trường hợp này, test cần một **kênh đưa message vào producer**, converter nhận payload, handler xử lý và kênh quan sát output; không chỉ gọi một method trigger. Việc hỗ trợ `messageFrom`, `messageBody`, `messageHeaders` và cách gắn với Spring Cloud Stream binder phụ thuộc phiên bản và adapter. Hãy **đối chiếu generated tests và nguồn message thật** khi áp dụng.

Với cả input và output message, hãy xác định rõ **raw payload** và **payload sau deserialization** ở từng điểm. Nếu contract kiểm message input sau converter nhưng consumer thực gửi JSON sai tên trường, một test trừu tượng quá cao có thể bỏ sót lỗi. Đây là lý do cần kiểm một đoạn wire serialization/deserialization thực tế.

## 13. JSON, Avro, Protobuf: không có một serializer chung cho mọi hệ thống

Spring Cloud Contract diễn đạt kỳ vọng trao đổi, còn **wire format** có thể được hiện thực bằng nhiều công nghệ:

| Wire format | Đặc điểm | Cần kiểm thêm ngoài body mẫu |
| --- | --- | --- |
| **JSON** | Dễ đọc; converter có thể dùng Jackson; kiểu number/string/null rõ theo JSON. | Field naming, null/missing, timestamp, số, content type, charset. |
| **Avro** | Binary theo schema, có thể dùng Schema Registry. | Schema ID/version, backward/forward compatibility, field defaults, cách decode. |
| **Protobuf** | Binary theo message definition, field number quan trọng. | Field number, reserved fields, optional/presence, default values, version. |
| **Text/raw bytes** | Có thể là plain text hoặc byte stream tùy định dạng ứng dụng. | Encoding, delimiter, framing, checksum/signature khi có. |

Nếu producer dùng Kafka serializer kiểu **Avro** mà generated contract test chỉ quan sát một `Map` trước serialization, nó không phát hiện được một schema registry ID sai. Một **schema compatibility check** và một **integration test với serializer/deserializer thật** sẽ phù hợp hơn để bảo vệ phần đó.

Không phải mọi kiểm tra schema thay thế được hợp đồng nghiệp vụ: hai schema có thể tương thích về cú pháp nhưng đổi ý nghĩa `amountMinor` từ “đồng” sang “xu” chẳng hạn, khiến Billing tính tiền sai mà parser vẫn chạy.

## 14. Quản lý phiên bản và tương thích khi đổi dạng message

Một số thay đổi tưởng chỉ là sửa serializer nhưng ảnh hưởng trực tiếp consumer:

| Thay đổi | Rủi ro | Hướng bảo vệ |
| --- | --- | --- |
| `orderId` → `order_id` | Consumer đọc `orderId` không map được. | Cố định naming strategy hoặc version sự kiện. |
| `amountMinor` từ number thành string | DTO/validation hoặc toán học có thể sai. | Test wire JSON và deserializer consumer. |
| `occurredAt` ISO string → epoch number | Parser thời gian cũ không tương thích. | Giữ schema cũ hoặc có kế hoạch version/migration. |
| Bật `NON_NULL` làm mất `note:null` | Consumer phân biệt null và missing bị ảnh hưởng. | Contract/test riêng cho presence và null. |
| `eventType` chuyển từ header sang body | Consumer định tuyến bằng header bị hỏng. | Thống nhất và test header trên transport thật. |
| Đổi tên destination/topic | Listener không nhận được event dù payload đúng. | Messaging contract + integration test routing. |
| Enum `CREATED` → `created` | Consumer case-sensitive có thể lỗi. | Bảo vệ giá trị enum trong hợp đồng. |
| Thêm trường tùy chọn | Có thể tương thích nếu consumer bỏ qua trường không biết. | Kiểm chính sách unknown fields; xác nhận consumer cũ. |
| Xóa trường, đổi ý nghĩa hoặc thu hẹp miền | Có thể phá consumer đang hoạt động. | Phát hành version, duy trì contract cũ khi cần, kiểm ma trận consumer. |

**Tương thích cần được đánh giá theo hướng producer phát và consumer nhận.** Ví dụ, một consumer dùng Jackson với `FAIL_ON_UNKNOWN_PROPERTIES` có thể không chấp nhận trường mới dù JSON schema coi trường đó là tùy chọn. Đừng chỉ xem producer gửi “hợp lệ” mà bỏ qua cách consumer cũ deserialize.

Với sự kiện có nhiều phiên bản đang lưu hành, nhóm có thể chọn tên type `OrderCreatedV1`, header `schemaVersion`, topic versioned hoặc cơ chế schema registry; điều quan trọng là **quy tắc định tuyến và giải mã phải được document, test và quản lý lifecycle**.

## 15. Một ma trận kiểm thử cho trước và sau serialization

Trong CI, hãy xác minh những điểm sau:

| Bài kiểm | Đầu vào | Assertion chính | Phát hiện lỗi gì? |
| --- | --- | --- | --- |
| **Domain event test** | Lệnh tạo đơn | Object `OrderCreated` đúng id/số tiền/thời gian. | Lỗi map business → event. |
| **Messaging contract producer test** | `triggeredBy` hoặc message input | Output destination, headers, payload thỏa hợp đồng. | Producer đổi hành vi event có thể quan sát qua adapter. |
| **JSON wire test** | Object producer | Bytes JSON, trường/kiểu/null/timestamp đúng. | Serializer/Jackson config sai. |
| **Transport integration test** | Publish qua binder/broker test | Consumer nhận đúng bytes/headers/destination. | Header mapping, codec, route hoặc native encoding sai. |
| **Consumer deserializer test** | Payload theo phiên bản hợp đồng | DTO được map đúng, lỗi dữ liệu sai được xử lý. | Consumer không parse được event. |
| **Stub Runner consumer test** | Trigger labeled event | Consumer nhận, xử lý và tạo tác dụng mong đợi. | Logic client/listener không phù hợp contract. |
| **Schema compatibility test** (nếu có) | Schema cũ và mới | Phù hợp chính sách tương thích đã chọn. | Breaking changes của Avro/Protobuf/schema. |

Sơ đồ CI:

~~~mermaid
flowchart TD
    A["Thay đổi producer hoặc hợp đồng"] --> B["Review event schema + metadata"]
    B --> C["Verifier sinh producer message tests"]
    C --> D["Chạy test body/header/destination"]
    D --> E["Kiểm serializer và transport"]
    E --> F{"Tất cả producer checks đạt?"}
    F -->|Không| G["Chặn phát hành stub và event version"]
    F -->|Có| H["Publish stubs theo version"]
    H --> I["Consumer CI: Stub Runner + deserialization"]
    I --> J["Đánh giá tương thích với consumer cũ"]
~~~

**Đừng chỉ kiểm JSON string trong unit test rồi bỏ qua generated producer tests.** Ngược lại, **đừng chỉ kiểm message object qua test binder** mà bỏ qua serializer dùng trong production. Hai nhóm phép kiểm bổ trợ nhau, bảo vệ cả **ý nghĩa sự kiện** và **cách nó xuất hiện trên đường truyền**.

## 16. Lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm |
| --- | --- | --- |
| Producer test PASS, Billing không parse được message. | Converter/broker serializer khác converter trong test; đổi wire field. | Capture payload bytes + headers thực, chạy deserializer consumer. |
| `occurredAt` thành số thay vì chuỗi. | Jackson date/time config hoặc serializer khác. | Kiểm `ObjectMapper`/module Java Time, timestamp settings và payload bytes. |
| `note:null` biến mất. | `NON_NULL` hoặc conversion bỏ null. | Test `JsonNode.has("note")` và `isNull()`. |
| Số tiền sai sau khi decode. | Double precision, scale hoặc đơn vị tiền không thống nhất. | So kiểu JSON và số nguyên minor units/BigDecimal theo chính sách. |
| Consumer nhận header `eventType` rỗng. | Header bị lọc/đổi tên bởi binder hoặc không publish. | Kiểm message trước gửi và metadata trên broker thực. |
| Consumer nhận String JSON có dấu nháy ngoài. | Double serialization: JSON string bị encode thêm lần nữa. | Kiểm raw bytes, loại payload trước converter và content type. |
| Không thấy generated producer messaging test. | Contract không được plugin nạp hoặc test framework/messaging adapter sai. | Xem generated test sources, test report, config Contract Verifier. |
| Test báo không thấy message ở destination. | Sai `sentTo`, output binding khác broker destination, subscriber chưa sẵn. | Đối chiếu `spring.cloud.stream.bindings`, adapter và kênh thực. |
| Stub trigger chạy nhưng listener không nhận. | Chưa cấu hình messaging stub adapter/binder hoặc label sai. | Kiểm `StubTrigger`, tên label, destination, test binder và subscriber. |
| Consumer test xanh dù producer publish không được. | Stub mô phỏng đúng message nhưng producer thật không được verification. | Chặn publish khi producer tests fail; bổ sung transport integration test. |
| CI chạy lúc pass lúc fail. | Message bất đồng bộ chưa đến, queue chứa message cũ, timeout không rõ. | Cô lập topic/queue, dùng event ID, await có deadline xác định. |

Khi debug, lần theo **đối tượng producer → Spring Message → serializer → bytes/metadata broker → deserializer → đối tượng consumer**. Ghi nhận đúng payload và header ở từng ranh giới, tránh chỉ log `toString()` của Java object rồi kết luận wire message đúng.

## 17. Bài thực hành: phát hiện lỗi xảy ra giữa producer và consumer

Trên một dự án Spring Boot/Spring Cloud Stream có Spring Cloud Contract Verifier và một consumer có Stub Runner:

1. **Định nghĩa event `OrderCreatedV1`** gồm `eventId`, `orderId`, `amountMinor`, `occurredAt`, `note`; ghi rõ kiểu JSON, nghĩa của đơn vị tiền và quy tắc null.
2. **Tạo hợp đồng message Groovy** có `label=orderCreatedV1`, `triggeredBy`, `sentTo=orders.created`, headers và body theo mục 5; chỉ chọn một DSL chính thức.
3. **Cài đặt đường phát message** với `StreamBridge`, cấu hình output binding trỏ tới destination được hợp đồng dùng.
4. **Tạo base test và messaging adapter** để generated producer test có thể kích hoạt publish và quan sát đúng message; xác nhận test thật sự được sinh, thực thi và PASS.
5. **Viết JSON serialization test** bằng `ObjectMapper` thực của producer; kiểm `note` xuất hiện là JSON null, `occurredAt` là ISO string và `amountMinor` là integer.
6. **Gây lỗi có chủ đích**: bật `NON_NULL` để `note` biến mất. Kiểm test wire format FAIL, giải thích vì sao generated message test có thể vẫn PASS nếu nó quan sát object trước serialization.
7. **Thử đổi naming strategy** để `orderId` thành `order_id`. Ghi nhận lỗi ở test wire JSON và/hoặc consumer deserializer, sau đó hoàn nguyên.
8. **Kiểm transport integration** với binder/broker phù hợp; xác nhận header `eventType` và `schemaVersion` thực sự đến được phía nhận.
9. **Đóng gói/cài hoặc publish stub** sau khi producer verification đạt. Dùng Stub Runner trigger label và xác nhận consumer thực xử lý event `ORD-1042`.
10. **Giả lập nâng schema**: thêm trường optional, xóa một trường bắt buộc hoặc đổi `amountMinor` từ number sang string. Đánh giá tương thích với consumer phiên bản cũ; chỉ phát hành sau khi có chiến lược migration và bộ test phù hợp.

**Tiêu chí hoàn thành:** người học chỉ ra được **giá trị nào tồn tại trước serialization**, **JSON bytes/header nào thực sự đi qua transport**, **DTO nào consumer nhận sau deserialization**, và **lớp test nào phát hiện lỗi khi ba biểu diễn không nhất quán**.

## 18. Câu hỏi tự kiểm tra

1. Vì sao `Message<OrderCreated>` không có nghĩa rằng broker đã nhận một JSON object?
2. Header `contentType` khác JSON field `contentType` trong body như thế nào?
3. Nếu `ObjectMapper` của producer bỏ qua null, `{"note":null}` có thể đổi thành gì? Khi nào là breaking change?
4. Một generated producer test so payload dạng Java object có phát hiện mọi lỗi Kafka/AMQP serialization không?
5. Vì sao consumer dùng DTO riêng có thể không map được `order_id` nếu trước đó hợp đồng là `orderId`?
6. Dùng `long amountMinor` thay cho `double amount` có thể giảm loại rủi ro nào? Còn điều gì cần quy định về đơn vị tiền?
7. `sentTo('orders.created')` và `streamBridge.send("ordersCreated-out-0", ...)` cần được kết nối bằng cấu hình nào?
8. Stub Runner với message contract có tự khởi động broker production và chạy producer thật không?
9. Tại sao một bài consumer stub test thành công chưa chứng minh producer publish đúng wire bytes?
10. Khi đổi timestamp từ ISO string thành epoch number, vì sao producer/consumer vẫn có thể bất tương thích dù biểu diễn cùng thời điểm?

**Ghi nhớ:** **Đối tượng trước serialization, payload sau serialization và đối tượng sau deserialization không tự động giống nhau**. Hợp đồng messaging của Spring Cloud Contract cần diễn đạt đúng payload, header và destination mà consumer dựa vào; generated producer tests xác minh đường phát được cấu hình, còn **serialization/transport integration tests** bảo vệ bytes và metadata thực. Consumer dùng Stub Runner để kiểm xử lý event độc lập, và CI phối hợp các lớp kiểm này trước khi phát hành phiên bản sự kiện mới. Như vậy, thay đổi serializer không âm thầm biến thành breaking change đối với các consumer vẫn đang hoạt động.
