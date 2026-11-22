# Kiểm tra compatibility của serializer trong Spring Kafka

Một producer triển khai phiên bản mới có thể gửi message thành công lên Kafka, nhưng consumer phiên bản cũ lập tức báo lỗi deserialization và ngừng xử lý partition. Vấn đề thường không nằm ở broker: **Kafka lưu và chuyển byte**, còn việc hiểu byte đó phụ thuộc vào serializer, deserializer, schema, header và hợp đồng dữ liệu của ứng dụng. Khi rolling upgrade, producer và consumer không nhất thiết được nâng cấp cùng thời điểm; một thay đổi tưởng nhỏ như đổi tên field, đổi kiểu số, thay class Java trong type header hoặc thay serialization format có thể khiến hệ thống mất khả năng đọc dữ liệu cũ/mới.

Bài học thuộc **Spring Kafka Reliability Operations → Nâng cấp và tương thích**, hướng dẫn kiểm tra **compatibility của serializer/deserializer** trước khi phát hành: xác định phiên bản writer/reader; phân biệt backward, forward, full và transitive compatibility; triển khai kiểm thử JSON với Spring Kafka; hiểu kiểm tra schema của Avro, Protobuf và JSON Schema; chạy integration test bằng Embedded Kafka; thiết kế rolling deployment, rollback, replay và xử lý record không giải mã được. Ví dụ dùng **Java 17, Spring Boot 3.x, Spring Kafka 3.x, JUnit 5**. Các quyết định chính sách phải dựa trên hệ sinh thái serializer/schema registry và yêu cầu nghiệp vụ thực tế.

## 1. Compatibility của serializer là gì?

Producer biến object thành byte để ghi vào topic:

```text
Producer v1                               Kafka topic
  OrderCreatedV1                             orders.events.v1
      |                                           |
      v                                           |
  Serializer v1 -> bytes + optional headers ----->|
                                                  |
                                           Consumer v1
                                                  |
                                           Deserializer v1
                                                  |
                                             Domain object

Đợt nâng cấp:
  Producer v2 -> bytes v2 ------> Consumer v1 (chưa nâng cấp)
  Producer v1 -> bytes v1 ------> Consumer v2 (đã nâng cấp)
```

**Wire compatibility** nghĩa là những phiên bản writer và reader dự kiến chạy đồng thời có thể trao đổi dữ liệu mà không lỗi hoặc hiểu sai ngữ nghĩa. Nó bao gồm nhiều lớp:

1. **Encoding format:** JSON, Avro, Protobuf, String hay định dạng nhị phân riêng.
2. **Schema:** tên field, type, nullable, default, field number, enum và quy tắc evolution.
3. **Envelope/headers:** schema ID, event type, version, Spring JSON type headers.
4. **Deserializer configuration:** class mục tiêu, trusted packages, strictness, converters, reader schema.
5. **Ý nghĩa nghiệp vụ:** đơn vị tiền, timezone, enum mới, optional field và cách consumer xử lý giá trị chưa biết.

Ví dụ schema vẫn parse được nhưng trường `amount` đổi từ **đồng** sang **xu** mà không đổi tên hoặc bổ sung unit: kết quả là **không tương thích ngữ nghĩa**, dù deserializer không ném exception. Vì thế bài kiểm thử cần cả **schema-level** lẫn **behavior-level**.

### 1.1. Producer gửi được không có nghĩa consumer đọc được

Kafka broker không tự hiểu `OrderCreatedV2` là một Java record nào. Một producer có thể ghi JSON mới hợp lệ, trong khi consumer cũ dùng `JsonDeserializer<OrderCreatedV1>`:

```json
{
  "eventId": "evt-100",
  "orderId": "order-501",
  "amount": 120.50,
  "note": "priority delivery"
}
```

Nếu consumer cũ bỏ qua field `note` không biết thì nó có thể hoạt động. Nếu consumer cũ bật strict validation với `additionalProperties: false`, hoặc code Java từ chối unknown properties, việc đọc có thể thất bại. **Không kết luận compatibility chỉ vì JSON hợp lệ cú pháp.**

## 2. Backward, forward, full và transitive

Trước khi thay serializer/schema, cần xác định chính xác **ai đọc dữ liệu do ai ghi**.

| Chế độ | Cặp writer → reader cần hỗ trợ | Tình huống triển khai |
| --- | --- | --- |
| **BACKWARD** | Writer cũ → reader mới | Nâng cấp consumer trước, producer sau |
| **FORWARD** | Writer mới → reader cũ | Nâng cấp producer trước, consumer sau |
| **FULL** | Cả hai chiều | Producer/consumer phiên bản cũ và mới cùng tồn tại |
| **BACKWARD_TRANSITIVE** | Reader mới đọc **mọi** phiên bản writer cũ trong phạm vi lịch sử kiểm tra | Replay dữ liệu nhiều version cũ |
| **FORWARD_TRANSITIVE** | Mọi reader cũ đọc writer mới theo phạm vi chính sách | Consumer cũ còn tồn tại lâu |
| **FULL_TRANSITIVE** | Cả hai chiều qua toàn bộ những version liên quan | Mixed-version kéo dài và lịch sử dài |

Các tên trên thường gặp trong **Schema Registry**. Với registry có chế độ `BACKWARD` không transitive, kiểm tra có thể chỉ so với **phiên bản schema mới nhất trước đó**, không nhất thiết mọi phiên bản đã từng đăng ký. Chi tiết phụ thuộc registry và policy được cấu hình.

### 2.1. Ví dụ với ba phiên bản

```text
Version 1: OrderCreated { orderId, amount }
Version 2: OrderCreated { orderId, amount, note? }
Version 3: OrderCreated { orderId, amount, note?, source? }
```

Nếu một consumer v3 phải replay record v1 vẫn còn trong Kafka, cần **v3 đọc được v1**, không chỉ đọc được v2. Với non-transitive check chỉ so v3 với v2, một đường migration nhiều bước có thể che sự không tương thích với v1. Vì vậy retention, replay window và thời gian tồn tại của consumer cũ ảnh hưởng trực tiếp tới việc chọn chế độ compatibility.

### 2.2. Compatibility không hoàn toàn đối xứng

Một field mới **optional/default** thường dễ được reader mới xử lý khi đọc dữ liệu cũ. Nhưng reader cũ có thể không chấp nhận field mới nếu nó yêu cầu đúng một tập property cố định. Ngược lại, xóa field mà reader cũ yêu cầu có thể làm **forward compatibility** thất bại.

Đừng suy diễn từ tên `BACKWARD` rằng nó có nghĩa “consumer cũ đọc producer mới”: chính xác là **reader mới đọc dữ liệu writer cũ**.

## 3. Xác định contract của một message trước khi kiểm thử

Một contract tối thiểu nên ghi:

```yaml
topic: orders.events.v1
eventType: OrderCreated
key:
  format: UTF-8 String
  meaning: orderId
value:
  format: JSON
  schemaVersion: 2
  requiredFields:
    - eventId
    - orderId
    - amount
  optionalFields:
    - note
orderingScope: one orderId
supportedReaders:
  - consumer-v1
  - consumer-v2
retention: 7 days
```

Đây là **hợp đồng minh họa**, không phải cấu hình Kafka tự áp dụng. Cần ghi thêm event ID/idempotency, versioning, encoding, timezone, đơn vị đo, enum values, độ dài giới hạn, nullable và quy tắc lỗi. Trong hệ thống đa ngôn ngữ, Java class name **không nên là định danh lâu dài duy nhất** của event trên wire.

Đặc biệt cần phân biệt:

- **Kafka key serializer:** quyết định key bytes, có thể ảnh hưởng partitioning và ordering.
- **Kafka value serializer:** quyết định payload bytes, schema và cách đọc event.
- **Header serializer/converter:** quyết định các metadata được ghi theo message.
- **Schema Registry serializer:** thường thêm schema ID hoặc envelope nhị phân riêng; không giống việc gửi JSON thuần.

Một đợt nâng cấp thay `StringSerializer` của key bằng một cách encode khác có thể khiến cùng `orderId` chuyển sang **partition khác**, dù value JSON vẫn parse được. Vì vậy compatibility của **key** cũng phải được kiểm thử khi có ordering hoặc deduplication theo key.

## 4. Thực hành JSON: thêm field optional mà consumer cũ vẫn đọc được

Ta dùng hai version của event `OrderCreated`. Giả sử hệ thống cho phép `note` chỉ là dữ liệu bổ sung; consumer v1 không dùng nó.

**`OrderCreatedV1.java`:**

```java
package com.example.kafka.events;

import java.math.BigDecimal;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreatedV1(
        String eventId,
        String orderId,
        BigDecimal amount) {}
```

**`OrderCreatedV2.java`:**

```java
package com.example.kafka.events;

import java.math.BigDecimal;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreatedV2(
        String eventId,
        String orderId,
        BigDecimal amount,
        String note) {}
```

Sự thay đổi chỉ là thêm `note` có thể `null`. Với Jackson record binding thông thường, nếu JSON v1 không có `note`, component `note` trong V2 có thể nhận `null`. Cần để service xử lý `null` an toàn và **không giả định `note` đã hiện diện trong mọi record lịch sử**.

### 4.1. Payload cũ và mới

JSON v1:

```json
{
  "eventId": "evt-101",
  "orderId": "order-501",
  "amount": 120.50
}
```

JSON v2:

```json
{
  "eventId": "evt-101",
  "orderId": "order-501",
  "amount": 120.50,
  "note": "priority delivery"
}
```

Hai kiểm tra cần có:

1. **Backward:** reader `OrderCreatedV2` đọc JSON v1; `note == null` và các trường cũ còn nguyên.
2. **Forward:** reader `OrderCreatedV1` đọc JSON v2; bỏ qua `note` và không làm sai `eventId`, `orderId`, `amount`.

`@JsonIgnoreProperties(ignoreUnknown = true)` giúp chính V1 bỏ qua property mới. Nhưng **chỉ nâng cấp annotation trong V1 code hiện tại không chứng minh bản binary V1 đang chạy trong production đã có behavior ấy**. Khi kiểm tra rolling compatibility, phải dùng **reader implementation/binary thực sự đã phát hành**, không dùng một bản V1 đã lén sửa cho dễ pass.

### 4.2. Thay đổi nguy hiểm ngay cả với JSON

| Thay đổi | Rủi ro | Cách đánh giá |
| --- | --- | --- |
| Thêm field optional `note` | Reader cũ có thể từ chối unknown field | Test v1 đọc v2 |
| Thêm field bắt buộc không có default | Reader mới không đọc được record cũ | Test v2 đọc v1, kiểm tra constraint |
| Đổi `amount` number thành `"120.50"` string | Parser strict hoặc schema validation thất bại | Test cả hai chiều, tránh dựa vào coercion ngầm |
| Đổi `amount` từ VND sang cents | Parse được nhưng sai giá trị nghiệp vụ | Assert semantic transformation và unit |
| Đổi `orderId` thành `id` | Reader cũ có thể nhận `null` | Cần alias/migration/version mới |
| Thêm enum value `REFUNDED` | Consumer cũ có thể không có nhánh xử lý | Test unknown enum handling |
| Bỏ field `eventId` | Mất khóa dedup/audit | Chặn ngay ở contract test |
| Đổi `null` thành missing hoặc ngược lại | Có thể thay ý nghĩa "không đổi"/"xóa" | Kiểm tra null semantics |
| Chuyển JSON sang Avro nhưng vẫn cùng topic | Deserializer cũ hoàn toàn không hiểu bytes mới | Topic version/migration hoặc envelope phân biệt format |

Không nên tin rằng `ObjectMapper` mặc định ở mọi service đều giống nhau. Các cờ như `FAIL_ON_UNKNOWN_PROPERTIES`, `FAIL_ON_MISSING_CREATOR_PROPERTIES`, date modules và custom deserializer có thể làm kết quả khác nhau.

## 5. Unit test JSON compatibility ở mức byte

Tầng test đầu tiên không cần Kafka broker: serialize dữ liệu bằng **writer thực** rồi deserialize bằng **reader đích**. Việc so sánh theo byte giúp phát hiện trường hợp code JSON dùng annotation khác dự kiến, format timestamp thay đổi hoặc serializer thêm wrapper.

### 5.1. Dùng `ObjectMapper` làm baseline JSON

`OrderJsonCompatibilityTest.java`:

```java
package com.example.kafka.events;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class OrderJsonCompatibilityTest {

    private final ObjectMapper mapper =
            new ObjectMapper().findAndRegisterModules();

    @Test
    void newReaderCanReadOldPayload() throws Exception {
        byte[] v1Payload = """
                {"eventId":"evt-101","orderId":"order-501",
                 "amount":120.50}
                """.getBytes(StandardCharsets.UTF_8);

        OrderCreatedV2 result =
                mapper.readValue(v1Payload, OrderCreatedV2.class);

        assertThat(result.eventId()).isEqualTo("evt-101");
        assertThat(result.orderId()).isEqualTo("order-501");
        assertThat(result.amount())
                .isEqualByComparingTo("120.50");
        assertThat(result.note()).isNull();
    }

    @Test
    void oldReaderCanReadNewPayload() throws Exception {
        OrderCreatedV2 writerObject = new OrderCreatedV2(
                "evt-102",
                "order-502",
                new BigDecimal("57.25"),
                "priority delivery");

        byte[] v2Payload = mapper.writeValueAsBytes(writerObject);

        OrderCreatedV1 oldReaderResult =
                mapper.readValue(v2Payload, OrderCreatedV1.class);

        assertThat(oldReaderResult.eventId()).isEqualTo("evt-102");
        assertThat(oldReaderResult.orderId()).isEqualTo("order-502");
        assertThat(oldReaderResult.amount())
                .isEqualByComparingTo("57.25");
    }

    @Test
    void strictOldReaderMayRejectNewField() throws Exception {
        // Dùng DTO strict không có @JsonIgnoreProperties ở test riêng.
        record StrictV1(
                String eventId, String orderId, BigDecimal amount) {}

        ObjectMapper strictMapper = new ObjectMapper()
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

        byte[] v2Payload = """
                {"eventId":"evt-103","orderId":"order-503",
                 "amount":12.00,"note":"new"}
                """.getBytes(StandardCharsets.UTF_8);

        org.assertj.core.api.Assertions.assertThatThrownBy(
                () -> strictMapper.readValue(
                        v2Payload, StrictV1.class))
                .isInstanceOf(
                        com.fasterxml.jackson.databind.exc
                                .UnrecognizedPropertyException.class);
    }
}
```

Test cuối minh họa **hai consumer có policy Jackson khác nhau** có thể cho kết quả khác nhau. Khi dùng Java records, Jackson cần phiên bản hỗ trợ record và cấu hình tương thích; Spring Boot 3.x cung cấp Jackson hiện đại theo dependency management.

### 5.2. Test Spring Kafka serializer trực tiếp

Nếu ứng dụng dùng `org.springframework.kafka.support.serializer.JsonSerializer` và `JsonDeserializer`, nên kiểm tra **chính những class này**, không dừng ở `ObjectMapper`.

```java
import java.math.BigDecimal;
import org.springframework.kafka.support.serializer.JsonSerializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

JsonSerializer<OrderCreatedV2> writer = new JsonSerializer<>();
writer.setAddTypeInfo(false);

JsonDeserializer<OrderCreatedV1> oldReader =
        new JsonDeserializer<>(OrderCreatedV1.class, false);

byte[] payload = writer.serialize(
        "orders.events.v1",
        new OrderCreatedV2(
                "evt-200", "order-700",
                new BigDecimal("19.90"), "memo"));

OrderCreatedV1 result =
        oldReader.deserialize("orders.events.v1", payload);

assertThat(result.orderId()).isEqualTo("order-700");
```

Đây là **fragment** để đặt trong method test có import AssertJ. `JsonSerializer.serialize(topic, value)` trả payload bytes nhưng không tự chứng minh các **Kafka headers** mà `KafkaTemplate` có thể gửi cùng `ProducerRecord`. Nếu type headers là một phần wire contract, phải kiểm thử thêm message có headers thật trong integration test.

**Golden fixtures:** lưu các payload thật do release V1, V2 tạo ra dưới dạng file byte/JSON test version-controlled. Chạy test matrix **writer-version × reader-version** trên fixture này trước khi deploy. Đừng chỉ tạo cả hai đầu bằng class mới trong cùng một lần chạy test, vì test có thể bỏ sót breaking change với binary cũ.

## 6. Spring Kafka JSON type headers: bẫy khi nâng cấp Java class

Spring Kafka `JsonSerializer` có thể ghi thông tin type vào Kafka headers, ví dụ header chỉ định class Java được serialize. `JsonDeserializer` có thể đọc headers để quyết định loại object cần tạo.

```text
Kafka record
   key: "order-501"
   value bytes: {"eventId":"...","orderId":"...","amount":120.50}
   headers:
       __TypeId__: com.oldcompany.events.OrderCreated
```

Khi refactor package:

```text
com.oldcompany.events.OrderCreated
    ->
com.example.kafka.events.OrderCreatedV2
```

Payload JSON vẫn có thể tương thích, nhưng deserializer dựa vào `__TypeId__` cũ có thể không tìm thấy class hoặc từ chối package không nằm trong trusted packages. Vấn đề thuộc **wire headers và runtime configuration**, không nhất thiết thuộc JSON schema.

### 6.1. Nếu topic chỉ mang một event type

Có thể dùng một target type rõ ràng và không phụ thuộc Java FQCN header:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: false

    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.example.kafka.events.OrderCreatedV2
        spring.json.trusted.packages: com.example.kafka.events
```

Trong ví dụ, mỗi consumer biết event type mình đọc. Hãy áp dụng cùng config ở runtime và test; việc tắt type headers **chỉ phù hợp khi consumer có cách khác xác định đúng type**.

### 6.2. Nếu topic có nhiều event type

Không nên tắt header rồi ép mọi message vào `OrderCreatedV2`. Có thể chọn:

- Một envelope ổn định: `eventType`, `eventVersion`, `payload` với mapping an toàn.
- Spring Kafka type mappings qua những **logical type ID** đã thỏa thuận, thay vì dùng Java class name làm hợp đồng bên ngoài.
- Schema Registry cùng subject strategy phù hợp để xác định schema ID của từng record.
- Topic riêng theo loại event nếu kiến trúc và vận hành phù hợp.

Khi dùng `spring.json.trusted.packages`, nên allowlist package được phép. Cấu hình `"*"` cho mọi package làm giảm rào chắn an toàn; không dùng nó như giải pháp mặc định khi gặp `ClassNotFoundException` hoặc lỗi package sau nâng cấp.

**Compatibility test thực tế phải kiểm tra cả value bytes lẫn headers**: tạo record với serializer V1 và thử consume bằng deserializer V2; thử chiều ngược lại theo chiến lược rolling release.

## 7. Khi dùng Avro, Protobuf hoặc JSON Schema và Schema Registry

Schema Registry giúp quản lý phiên bản schema và tự động từ chối một số thay đổi không tương thích trước khi publish schema mới. Nhưng **schema compatibility check không thay thế runtime test**: serializer có thể dùng sai subject, sai schema ID/wire envelope hoặc consumer có logic không chấp nhận giá trị mới.

### 7.1. Avro evolution minh họa

Schema V1:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountCents", "type": "long"}
  ]
}
```

Schema V2 thêm `note` optional có default:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountCents", "type": "long"},
    {
      "name": "note",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
```

Avro giải quyết schema theo **writer schema và reader schema**. Khi reader V2 đọc record V1 không có field `note`, Avro có thể dùng default `null`. Khi reader V1 đọc record V2, reader thường bỏ qua field `note` mới. Đó là một ví dụ có thể tương thích hai chiều, nhưng phải test theo đúng registry compatibility policy và thư viện sử dụng.

**Đặc biệt:** thay `amountCents` bằng `amount` không phải chỉ đổi tên hiển thị. Consumer cũ có thể không thấy field cần thiết. Rename có thể cần alias và kế hoạch triển khai; thay type, logical type hoặc đơn vị tiền có thể tạo incompatibility hoặc lỗi ngữ nghĩa.

### 7.2. Protobuf evolution

Protobuf phụ thuộc rất nhiều vào **field number**:

```proto
syntax = "proto3";

package orders;

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  int64 amount_cents = 3;
  optional string note = 4;
}
```

Thường có thể bổ sung một field number mới mà reader cũ bỏ qua. **Không tái sử dụng field number cũ cho ý nghĩa mới**: một consumer lịch sử có thể giải mã bytes mới thành field sai nghĩa. Khi loại bỏ field, cần `reserved` field number và tên phù hợp trong schema tương lai.

Các thay đổi kiểu dữ liệu, enum, oneof và proto2/proto3 presence semantics có những quy tắc riêng. Không áp dụng nguyên xi kết luận “thêm field optional là an toàn” từ JSON hoặc Avro cho mọi schema Protobuf.

### 7.3. JSON Schema evolution

JSON Schema kiểm soát required/optional, type, enum và policy chấp nhận property không khai báo. Ví dụ schema có:

```json
{
  "type": "object",
  "properties": {
    "orderId": {"type": "string"},
    "amount": {"type": "number"}
  },
  "required": ["orderId", "amount"],
  "additionalProperties": false
}
```

Reader hoặc validator dựa vào schema này có thể từ chối field `note` mới nếu `additionalProperties` bị chặn. Do đó **JSON payload tự do** và **JSON Schema strict** không có cùng ngữ nghĩa compatibility. Kiểm tra theo implementation của registry và validator thực tế; không dựa vào mẹo “JSON luôn bỏ qua unknown field”.

### 7.4. Schema ID và wire envelope

Trong một số hệ sinh thái, ví dụ serializer định dạng wire của Confluent Schema Registry, payload bao gồm **marker và schema ID** trước dữ liệu Avro/Protobuf/JSON Schema:

```text
Kafka value bytes
  |
  +-- wire-format marker / schema ID
  +-- serialized record bytes
```

Một consumer chỉ dùng `StringDeserializer` hoặc `JsonDeserializer` để đọc toàn bộ bytes sẽ không tự hiểu định dạng này. Phải sử dụng **deserializer tương ứng với serializer của hệ sinh thái registry**. Không giả định mọi schema registry dùng cùng wire format hoặc giao thức xác thực.

## 8. Cấu hình Schema Registry và kiểm tra compatibility policy

Ví dụ Spring Boot khi dùng **serializer của Confluent** (cần thêm dependency/ repository tương thích; **không có sẵn chỉ bằng `spring-kafka`**):

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
      properties:
        schema.registry.url: ${SCHEMA_REGISTRY_URL}
        auto.register.schemas: false
        # Subject/schema phải được provision và xác minh trước.

    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        schema.registry.url: ${SCHEMA_REGISTRY_URL}
        specific.avro.reader: true
```

`auto.register.schemas=false` giúp runtime producer không tự ý đăng ký schema mới khi policy yêu cầu registry được cập nhật bởi pipeline riêng. Nếu schema chưa tồn tại đúng subject, **producer có thể lỗi serialization**; triển khai phải có thứ tự và preflight thích hợp.

`specific.avro.reader=true` phù hợp khi ứng dụng dùng Avro generated classes. Nếu dùng `GenericRecord`, cấu hình và type handling khác. URL, credentials và token registry phải được bảo vệ qua secret management; không ghi secret trong source, log hoặc test artifact.

### 8.1. Subject naming strategy là một phần contract

Một số chiến lược subject phổ biến trong hệ Confluent:

| Strategy | Ý tưởng | Hệ quả |
| --- | --- | --- |
| `TopicNameStrategy` | Subject gắn với topic + key/value | Một compatibility policy cho type tương ứng của topic |
| `RecordNameStrategy` | Subject theo tên record/schema | Nhiều topic có thể dùng cùng contract record |
| `TopicRecordNameStrategy` | Subject theo topic và record name | Quản lý nhiều record type trong từng topic |

Chọn strategy phải phù hợp với topic chứa một hay nhiều event type, quyền evolve riêng từng schema và chính sách multi-topic reuse. **Đổi subject naming strategy giữa producer/consumer hoặc giữa môi trường** có thể khiến schema ID/subject registration không như dự kiến và CI kiểm tra nhầm đối tượng.

### 8.2. Registry compatibility test trong CI

Với một registry hỗ trợ compatibility API kiểu Confluent, quy trình có thể là:

```text
1. Lấy subject đã được production dùng.
2. Lấy policy compatibility có hiệu lực.
3. Chuẩn bị candidate schema từ commit mới.
4. Gọi compatibility check với subject/version thích hợp.
5. Fail CI nếu không tương thích.
6. Nếu pass, chạy test deserialize/semantic bằng writer/reader thực.
7. Chỉ sau đó mới cho phép register + rollout.
```

Ví dụ gọi API với file request chứa **schema candidate đã escape đúng dạng registry yêu cầu**:

```bash
curl --fail-with-body \
  -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data @candidate-schema-request.json \
  "${SCHEMA_REGISTRY_URL}/compatibility/subjects/orders.events.v1-value/versions/latest"
```

Phản hồi thường chứa kết quả tương tự `{"is_compatible": true}` hoặc `false` trong hệ API này. Đó là **kiểm tra schema-level**, không phải bảo đảm business logic hay Spring deserializer đều chạy được.

**Cảnh báo thực hành:** subject `orders.events.v1-value` là tên minh họa cho `TopicNameStrategy`. Đừng copy nguyên nếu production dùng chiến lược khác. Nếu policy cần transitive history, phải chạy đúng mode và phạm vi version; một lần check `latest` theo policy mặc định không tự chứng minh consumer đọc được mọi historical writer.

## 9. Thiết kế ma trận kiểm thử phiên bản

Khi nâng cấp từ V1 lên V2, tối thiểu nên có:

| Writer | Reader | Kiểm tra gì? |
| --- | --- | --- |
| V1 | V1 | Baseline đã từng chạy |
| V1 | V2 | **Backward**: consumer mới đọc record cũ |
| V2 | V1 | **Forward**: producer mới không phá consumer cũ |
| V2 | V2 | Đường xử lý mới |
| Historical V0 | V2 | Replay nếu data V0 còn được lưu |
| V2 key serializer | V1 consumer/key routing | Ordering, partitioning, deduplication |

Mỗi cặp test cần kiểm tra:

1. Bytes do **serializer thật của writer version** tạo ra, không phải JSON tự viết có thể khác runtime.
2. Headers/schema ID/event type mà producer thật gửi.
3. Deserializer và configuration của **reader version thực tế**.
4. Giá trị sau khi parse: các field bắt buộc, enum, null/default, timezone và business semantics.
5. Xử lý unknown fields và dữ liệu hỏng: không im lặng map thành object thiếu khóa.
6. Khi Kafka transactions được sử dụng, xem đúng isolation semantics và offset/recovery.

### 9.1. Golden payload và artifact phiên bản cũ

Một dự án có thể lưu:

```text
src/test/resources/compat/
  ├── order-created-v1.json
  ├── order-created-v2.json
  ├── avro-order-created-v1.bin
  ├── avro-order-created-v2.bin
  └── compatibility-cases.yml
```

File golden cần được tạo từ **phiên bản writer thực**, có source/version/checksum rõ và không chứa dữ liệu cá nhân. Nếu dùng registry wire format, hãy lưu **raw bytes đầy đủ**, gồm header/envelope cần thiết, cùng schema registry fixture tương ứng. Đừng chỉnh fixture cũ chỉ để test pass; fixture có vai trò ghi lại contract đã phát hành.

Khi nâng Java dependency, cần test lại golden fixture bằng **reader mới**. Khi nâng producer, cần chạy **binary hoặc container image của consumer cũ** để kiểm tra forward compatibility nếu consumer cũ sẽ tiếp tục tồn tại.

## 10. Integration test bằng Embedded Kafka

Unit test Jackson không đi qua Kafka producer, headers, topic hay consumer configuration. Integration test với Embedded Kafka sẽ xác nhận rằng **Kafka record thực chứa payload V2** có thể được một consumer mô phỏng V1 giải mã đúng trong môi trường cô lập.

### 10.1. Dependency

Ví dụ phần Gradle dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ví dụ Spring Boot 3.x quản lý các phiên bản liên quan qua BOM. Không trộn phiên bản Spring Kafka/Spring Framework không tương thích hoặc giả định embedded broker mô phỏng mọi đặc điểm của cluster production.

### 10.2. Test thực tế: raw JSON V2 tới deserializer V1

`SerializerCompatibilityIT.java`:

```java
package com.example.kafka.events;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@SpringBootTest(
        classes = SerializerCompatibilityIT.TestApp.class)
@EmbeddedKafka(
        topics = "compat.orders.v1",
        partitions = 1,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class SerializerCompatibilityIT {

    private static final String TOPIC = "compat.orders.v1";
    private final ObjectMapper mapper = new ObjectMapper();

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {}

    @Autowired
    EmbeddedKafkaBroker broker;

    @Test
    void oldReaderConsumesNewProducerJson() throws Exception {
        OrderCreatedV2 v2 = new OrderCreatedV2(
                "evt-200",
                "order-700",
                new BigDecimal("19.90"),
                "priority delivery");

        byte[] wireValue = mapper.writeValueAsBytes(v2);

        Map<String, Object> producerProps =
                KafkaTestUtils.producerProps(broker);
        producerProps.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        producerProps.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                ByteArraySerializer.class);

        try (Producer<String, byte[]> producer =
                     new KafkaProducer<>(producerProps)) {
            producer.send(new ProducerRecord<>(
                    TOPIC, "order-700", wireValue))
                    .get(10, TimeUnit.SECONDS);
        }

        Map<String, Object> consumerProps =
                KafkaTestUtils.consumerProps(
                        "legacy-reader-" + UUID.randomUUID(),
                        "false", broker);
        consumerProps.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest");

        var consumerFactory =
                new DefaultKafkaConsumerFactory<String, OrderCreatedV1>(
                        consumerProps,
                        new StringDeserializer(),
                        new JsonDeserializer<>(
                                OrderCreatedV1.class, false));

        try (Consumer<String, OrderCreatedV1> consumer =
                     consumerFactory.createConsumer()) {
            broker.consumeFromAnEmbeddedTopic(consumer, TOPIC);

            ConsumerRecord<String, OrderCreatedV1> record =
                    KafkaTestUtils.getSingleRecord(
                            consumer, TOPIC, Duration.ofSeconds(15));

            assertThat(record.key()).isEqualTo("order-700");
            assertThat(record.value().eventId()).isEqualTo("evt-200");
            assertThat(record.value().orderId()).isEqualTo("order-700");
            assertThat(record.value().amount())
                    .isEqualByComparingTo("19.90");
        }
    }
}
```

**Giới hạn có chủ đích của test:** producer gửi bytes JSON bằng `ObjectMapper` và `ByteArraySerializer`, không phải `KafkaTemplate` chạy cấu hình `JsonSerializer` kèm type headers. Test xác nhận **payload JSON và `JsonDeserializer` V1** trong môi trường Kafka; nó **chưa kiểm tra type headers thực tế**. Nếu ứng dụng thật dùng Spring Kafka type headers hoặc Avro wire format, phải tạo thêm test dùng **đúng producer factory/serializer cấu hình production**.

Mỗi test cần dùng topic hoặc group cô lập để tránh đọc record thừa từ test khác. Với suite có nhiều testcase cùng topic, dùng `@DirtiesContext`, topic khác hoặc tách broker/context theo fixture phù hợp. Không nên chỉ tăng timeout để che nhiễu do shared data.

### 10.3. Test schema header và versioned events

Khi message có header `eventType`, `schemaVersion` hoặc `__TypeId__`, cần tạo `ProducerRecord` bằng serializer/cấu hình runtime rồi kiểm tra **toàn bộ record**:

```java
for (var header : record.headers()) {
    String name = header.key();
    // Chỉ assert các header thuộc wire contract.
    // Không in toàn bộ header values nếu có credential/PII.
}
```

Đây là **fragment** cho test message metadata. Khi dùng Spring `JsonSerializer`, việc `serialize(topic, headers, value)` có thể ghi type header tùy cấu hình; hãy assert **version/logic ID đúng** thay vì chỉ assert Java FQCN tình cờ có ở classpath hiện tại.

## 11. Khi deserializer thất bại trước khi listener được gọi

Một lỗi rất quan trọng khi rolling deployment:

```text
Producer v2 gửi value bytes không tương thích
    |
    v
KafkaConsumer.poll()
    |
    v
Deserializer ném exception
    |
    X  @KafkaListener CHƯA nhận được object
```

Vì lỗi phát sinh trước khi listener method được gọi, **`try/catch` bên trong `@KafkaListener` không thể xử lý trực tiếp**. Nếu thiếu chiến lược, consumer có thể cứ cố đọc lại offset lỗi và kẹt partition.

### 11.1. `ErrorHandlingDeserializer` của Spring Kafka

Một cấu hình cho JSON reader có thể sử dụng wrapper:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      enable-auto-commit: false
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.kafka.events.OrderCreatedV2
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.kafka.events
```

`ErrorHandlingDeserializer` ghi nhận lỗi deserialize theo cơ chế Spring Kafka và cho container/error handler cơ hội xử lý record thay vì để exception không xử lý được ở `poll()`. **Nó không tự sửa payload hoặc bảo đảm tự gửi DLT**. Phải cấu hình error handler, recoverer, chính sách commit/seek và DLT theo phiên bản Spring Kafka và contract vận hành.

Ví dụ với record listener **không transactional**, `DefaultErrorHandler` kết hợp `DeadLetterPublishingRecoverer` có thể là lựa chọn. Với transactional listener, cơ chế after-rollback recovery và offset commit khác; không sao chép cùng một error handler khi chưa xem transaction semantics.

### 11.2. Không làm mất record chỉ vì skip deserialization error

Khi lỗi xảy ra:

1. Ghi **topic, partition, offset, error code, schema ID** đã được duyệt.
2. Xác định lỗi do schema/serializer mismatch, payload hỏng hay thiếu dependency/config.
3. Nếu recovery/DLT được phép, lưu nguyên bytes ở kho có phân quyền cùng metadata cần replay; đừng in raw payload vào log.
4. Kiểm tra DLT publish thành công và offset được xử lý theo policy.
5. Sau khi sửa consumer, có đường replay/reprocess idempotent cho record lỗi.

Nếu lỗi do cả một deployment mới thay đổi format sai, chuyển hàng triệu record vào DLT có thể không phải phương án tốt nhất: cần **dừng rollout/rollback producer** và phục hồi compatibility, rồi replay theo kế hoạch.

### 11.3. Tombstone và `null` value

Với topic compacted, Kafka tombstone là record có key và **value `null`**. Không nên giả định `null` luôn là payload invalid; listener có thể cần xử lý `@Payload(required = false)` hoặc `ConsumerRecord` trực tiếp theo contract.

```text
key=order-501
value=null
meaning=delete state for order-501
```

Nếu chuyển serializer khiến `null` bị biến thành chuỗi `"null"` hoặc object `{"value":null}`, consumer có thể hiểu khác. Kiểm tra **tombstone bytes thật**, cả trường hợp producer v1/v2, trước khi đổi serialization format của compacted topic.

## 12. Rolling deployment và thứ tự nâng cấp an toàn

Một thay đổi serializer thường được triển khai qua nhiều pod/service, nên có giai đoạn **mixed versions**:

```text
T0: Producer V1  -> Consumer V1

T1: Producer V1  -> Consumer V1 + Consumer V2
                   (cần BACKWARD compatibility)

T2: Producer V1 + Producer V2
                  -> Consumer V2
                   (có mixed-version writer)

T3: Producer V2  -> Consumer V2

Trong rollback:
Producer V2 -> Consumer V1 có thể xuất hiện lại!
```

Quy tắc:

- **Consumer-first:** nếu V2 reader đọc được V1 bytes, nâng consumer trước producer thường thuận lợi.
- **Producer-first:** chỉ an toàn nếu V1 reader đọc được V2 bytes.
- **Rolling hoặc rollback hai chiều:** thường cần FULL compatibility giữa các phiên bản đang có thể gặp nhau.
- **Replay lịch sử:** consumer mới phải đọc các version cũ còn trong retention hoặc archive; cần transitive behavior hoặc migration reader phù hợp.

### 12.1. Quy trình đề xuất

1. **Inventory:** liệt kê mọi producer và consumer theo topic/group; tìm các batch job, connector, replay tool và service phiên bản cũ ít khi chạy.
2. **Contract diff:** so schema, JSON headers, serializer class, key encoder, default/null/enum và business semantics.
3. **Registry check:** nếu dùng registry, kiểm tra candidate schema theo đúng subject và mode dự kiến.
4. **Golden tests:** chạy writer V1/V2 với reader V1/V2, bao gồm payload/headers thật.
5. **Deploy reader tương thích trước:** nếu phù hợp backward path.
6. **Canary producer:** gửi một lượng nhỏ V2, xem deserialization errors, lag, DLT và output nghiệp vụ.
7. **Rollout từng phần:** giữ feature flag/versioned serializer nếu cần rollback.
8. **Monitor:** xác nhận không có lag tăng bất thường, không có parse error, DLQ và business metrics hợp lệ.
9. **Cleanup:** chỉ bỏ reader/schema cũ khi retention, replay và rollback window đã hết hoặc đã có migration rõ.

Nếu không thể làm V1/V2 tương thích vì thay đổi schema quá lớn, cân nhắc **topic version mới** (`orders.events.v2`) với dual-read/dual-write có kiểm soát, key/idempotency và ranh giới cutover rõ. Không âm thầm đổi format của topic đang có consumer cũ.

### 12.2. Rollback không chỉ là đổi image

Giả sử producer V2 đã gửi dữ liệu V2 vào topic. Nếu rollback consumer về V1 nhưng V1 không hiểu record V2 còn trong log, **rollback code không cứu được partition**. Rollback plan phải dự kiến:

- Có giữ V1 reader đọc được V2 bytes không?
- Có thể tạm dừng producer để tránh ghi thêm dữ liệu không tương thích không?
- Có reader/router thích hợp cho đa version không?
- Có cần replay sang topic mới sau khi sửa format không?
- Những record V2 đã được đọc/gây side effect có cần dedup khi replay không?

Mục tiêu của compatibility testing là phát hiện rủi ro này **trước khi** có dữ liệu không tương thích tồn tại bền vững trong Kafka.

## 13. Các yếu tố ngoài schema cần kiểm tra

### 13.1. Partition key, ordering và idempotency

Nếu trước kia key là:

```text
StringSerializer("order-501") -> UTF-8 bytes
```

nhưng sau nâng cấp thành JSON string có dấu nháy:

```text
JsonSerializer("order-501") -> bytes của "order-501"
```

Kafka partitioner có thể tính hash khác từ key bytes. Sự kiện cùng order có thể vào partition mới, gây xử lý sai thứ tự trong giai đoạn mixed. Hãy kiểm tra **serialized key bytes và partition assignment** khi key serialization thay đổi, không chỉ check value schema.

Idempotency consumer nên dựa trên `eventId`/business key ổn định; khi v2 đổi event ID format hoặc chỉ đổi key, cần xác minh dedup vẫn hoạt động. Nếu record được redeliver hoặc replay sau rollback, không tạo side effect trùng.

### 13.2. Thời gian và độ chính xác số

| Thay đổi | Rủi ro |
| --- | --- |
| ISO timestamp thành epoch number | Sai parser, milliseconds/seconds bị nhầm |
| `LocalDateTime` thành `Instant` không có timezone contract | Lệch thời gian nghiệp vụ |
| `double` thành decimal/string | Khác rounding và precision |
| `amount` từ cents sang major currency unit | Sai số tiền dù deserialize thành công |
| Enum string viết hoa/thường khác | Consumer cũ có thể không map được |

Compatibility test phải assert **giá trị nghiệp vụ sau giải mã**, không chỉ `notNull`. Một event thanh toán parse được nhưng số tiền bị nhân 100 vẫn là breaking change nghiêm trọng.

### 13.3. Schema Registry availability và authentication

Serializer dùng registry có thể cần tra cứu schema ID hoặc đăng ký schema. Khi nâng cấp:

- Kiểm tra subject/schema đã tồn tại và ứng dụng có quyền READ/WRITE phù hợp.
- Kiểm tra certificate/TLS, auth token, endpoint và timeout.
- Có chiến lược khi registry tạm lỗi; đừng coi mọi lỗi registry là invalid payload.
- Đừng expose registry credentials qua logs hoặc exception HTTP.
- Trong test, phân biệt **schema incompatible** với **schema registry unavailable**.

Ngay cả schema đã được đánh dấu compatible, producer vẫn có thể thất bại nếu đăng ký vào nhầm subject, serializer dùng sai version hoặc registry permission bị từ chối.

## 14. Ma trận test tự động trước phát hành

Một CI pipeline thực tế có thể tổ chức:

```text
Pull request thay event model / serializer
       |
       v
Compile + unit serializer tests
       |
       +-- old bytes -> new reader
       +-- new bytes -> old reader
       +-- missing/null/unknown/enum
       |
       v
Schema Registry compatibility checks
       |
       +-- subject + version + policy
       +-- transitive history nếu cần
       |
       v
Embedded Kafka integration tests
       |
       +-- value bytes + headers + key
       +-- error handler/DLT
       |
       v
Contract tests với release binaries thực
       |
       +-- producer V2 / consumer V1
       +-- producer V1 / consumer V2
       |
       v
Staging rollout tests
       |
       +-- canary + lag/DLT/semantic output
```

### 14.1. Chọn dữ liệu biên

| Fixture | Kiểm tra |
| --- | --- |
| Payload V1 không có field mới | Default/null logic của V2 reader |
| Payload V2 có field mới | V1 reader xử lý unknown field |
| `null` ở field optional | Phân biệt absent/null và validation |
| Field required thiếu | Fail có chủ đích, không tạo object sai |
| Enum value mới | Fallback hay error đúng contract |
| Decimal lớn/nhỏ, precision đặc biệt | Không làm tròn sai |
| Unicode / ký tự escape | Encoding, parser và JSON escaping |
| Tombstone có value null | Consumer compacted topic xử lý đúng |
| Message có headers V1 và V2 | Không lệ thuộc Java FQCN cũ |
| Key cùng business identity | Key bytes và partition routing ổn định |
| Schema Registry envelope | Reader tìm đúng schema ID |
| Bytes hỏng/ngắn/truncated | Deserialization recovery và DLT |
| Record nhiều version trong một topic | Dispatch theo event type/version chính xác |

Không dùng dữ liệu cá nhân thật để tạo golden payload. Nếu cần xác minh bảo mật log, dùng marker dữ liệu giả và kiểm tra rằng marker không xuất hiện ở log/exception xuất công khai.

### 14.2. Test tiêu chí chấp nhận

Để một thay đổi được coi là deployable, không chỉ cần `schemaCompatible=true`, mà còn cần:

```text
Schema compatibility: PASS
Wire payload compatibility: PASS
Headers / schema IDs: PASS
Old reader with new writer: PASS nếu rollout cần
New reader with old writer: PASS nếu replay/rollout cần
Key routing and ordering: PASS
Business semantics: PASS
Deserialization failure recovery: PASS
Canary lag / DLT / error budget: within policy
```

Không phải hệ thống nào cũng cần full bidirectional compatibility. Nhưng mọi hướng tương thích mà deployment/rollback/replay **có thể xảy ra** đều phải được xác định và thử nghiệm.

## 15. Quan sát lỗi compatibility trong production

Sau triển khai, cần theo dõi:

| Dấu hiệu | Nguyên nhân khả dĩ | Bước xử lý |
| --- | --- | --- |
| `SerializationException` ở producer | Schema đăng ký sai, serializer config, payload không hỗ trợ | Kiểm tra writer schema/subject và exception classification |
| `RecordDeserializationException` ở consumer | Bytes format sai hoặc deserializer không tương thích | Dừng rollout, xác định topic-partition-offset và wire format |
| Spring `MessageConversionException` | Mapping envelope/header/type thất bại | Kiểm tra type IDs và converter policy |
| `ClassNotFoundException` khi đọc type header | Producer ghi Java class FQCN không còn tồn tại | Logical type mapping/target type, kiểm tra version |
| `IllegalArgumentException` do trusted packages | Class trong header không được phép | Đánh giá header và allowlist, không bật wildcard bừa bãi |
| Consumer lag tăng tại một offset | Poison record sau deployment | Xem error handler, offset và DLT, không commit skip mù |
| DLT tăng theo version mới | Một nhóm consumer chưa hiểu V2 payload | Kiểm tra rollout order, reader compatibility |
| Đọc được nhưng kết quả sai | Semantic incompatibility | So business invariants và audit |
| Producer timeout sau khi bật registry | Registry/Auth/network unavailable | Kiểm tra dependency và retry budget |
| Message cùng key phân bố khác | Đổi key serialization/partitioner | So serialized key bytes, ordering và migration |

Log hỗ trợ chẩn đoán nên có `topic`, `partition`, `offset`, `producer_version`, `schema_id`, `event_type`, `error_code` và correlation ID đã được duyệt. Không log toàn bộ message value, thông tin xác thực registry hoặc exception có raw payload nếu chưa có kênh xử lý dữ liệu an toàn.

Metric nên tổng hợp theo topic, consumer group, schema version/error code có cardinality kiểm soát. Tránh dùng `eventId`, order ID hoặc offset làm metric labels.

### 15.1. Khi xảy ra compatibility incident

1. **Xác định cặp version** producer/consumer nào bắt đầu lỗi sau release.
2. **Giữ bằng chứng an toàn**: metadata topic-partition-offset, schema ID, serialized key/value lưu trong kho có quyền; không in payload vào log công khai.
3. **Dừng phát tán** nếu producer đang tạo thêm payload consumer không hiểu.
4. **Kiểm tra schema/header/bytes** đối chiếu golden fixture và binary cũ.
5. **Quyết định recovery**: deploy reader hỗ trợ cả hai version, rollback producer, replay/DLT hoặc route sang topic version mới.
6. **Giữ offset/idempotency** rõ ràng; không tăng offset để “làm hết lỗi” khi chưa có quyết định bỏ dữ liệu.
7. **Xác nhận kết quả**: lag giảm, DLT được giải thích, số event vào/ra và business aggregates đối soát được.
8. **Bổ sung test hồi quy** cho cặp writer/reader và fixture gây lỗi.

Nếu đã có record không tương thích trong Kafka, **không xóa topic hoặc reset group offset bừa bãi**. Các hành động này có thể làm mất dữ liệu hoặc khiến consumer xử lý trùng những event đã tạo side effect.

## 16. Bài thực hành

Hãy dựng producer và consumer cho topic `orders.events.v1`, rồi giả lập nâng cấp từ V1 lên V2.

1. **Xác định contract:** chọn key là `orderId`, value format JSON, `eventId`, `orderId`, `amount`, field `note` mới optional; ghi rõ retention/replay và thứ tự triển khai.
2. **Unit test backward:** tạo payload do writer V1 phát ra; reader V2 phải parse và nhận `note=null` mà không mất các field cũ.
3. **Unit test forward:** tạo payload bằng writer V2; chạy reader V1 **đúng như release cũ**, không sửa DTO chỉ để test pass.
4. **Strict-reader test:** bật `FAIL_ON_UNKNOWN_PROPERTIES` cho reader cũ và quan sát điều kiện mà thêm field mới trở thành breaking change.
5. **Spring serializer test:** kiểm tra `JsonSerializer`/`JsonDeserializer` với type headers bật và tắt; thử refactor Java package.
6. **Embedded Kafka:** gửi record V2 lên broker test và nhận bằng V1 deserializer; assert value, key, topic và partition.
7. **Golden fixtures:** lưu JSON/raw bytes V1 và V2 từ runtime thật; chạy matrix V1→V2 và V2→V1 trong CI.
8. **Schema Registry:** định nghĩa Avro V1/V2, chạy compatibility check theo subject đang dùng; so `BACKWARD` với `FULL_TRANSITIVE`.
9. **Protobuf:** thêm field number mới, rồi tạo một ví dụ cố ý tái sử dụng field number cũ để hiểu vì sao đó là breaking change.
10. **Key compatibility:** đổi thử key serializer từ String sang JSON string và quan sát serialized key bytes/partition mapping; viết đề xuất giữ ordering khi migration.
11. **Deserialization failure:** gửi bytes hỏng, dùng `ErrorHandlingDeserializer` và error handler/DLT đã cấu hình; xác nhận record không bị mất im lặng.
12. **Rolling release:** mô phỏng consumer-first rồi producer rollout; cuối cùng giả lập rollback consumer và giải thích khi nào cần FULL compatibility.
13. **Semantic test:** đổi thử đơn vị tiền từ VND sang cents mà giữ nguyên `amount`; kiểm tra test nghiệp vụ phát hiện sai dù JSON parse được.
14. **Release checklist:** viết quyết định phát hành nêu rõ cặp version được hỗ trợ, bước canary, metric giám sát và đường rollback/replay.

## 17. Tổng kết

Kiểm tra compatibility của serializer trong Spring Kafka không chỉ là xem JSON còn hợp lệ hay Schema Registry có trả `is_compatible=true` hay không. Cần kiểm tra **writer bytes, reader behavior, headers/schema ID, key serialization, dữ liệu lịch sử và ý nghĩa nghiệp vụ** dưới những tổ hợp phiên bản có thể gặp nhau trong rollout và rollback.

**Backward** giúp consumer mới đọc dữ liệu cũ; **forward** giúp consumer cũ đọc dữ liệu mới; **full/transitive** phục vụ giai đoạn mixed-version và replay theo phạm vi tương ứng. Golden fixtures, test serializer trực tiếp, Embedded Kafka, registry checks và contract tests với artifact thực là các lớp kiểm chứng bổ trợ cho nhau. Khi một thay đổi không tương thích là bắt buộc, hãy dùng migration/versioned topic và quy trình đối soát thay vì âm thầm đổi format của topic đang được sử dụng. **Mục tiêu cuối cùng là không để nâng cấp serializer trở thành mất dữ liệu, kẹt partition hoặc xử lý sai nghiệp vụ.**
