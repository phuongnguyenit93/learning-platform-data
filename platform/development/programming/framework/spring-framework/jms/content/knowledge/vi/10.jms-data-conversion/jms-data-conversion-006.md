# Thiết kế schema thông điệp độc lập với lớp Java nội bộ trong Spring JMS

## 1. Vấn đề và mục tiêu

Trong một hệ thống hướng sự kiện, producer và consumer cần thống nhất **hợp đồng thông điệp (message contract / wire schema)**: tên sự kiện, ý nghĩa, trường dữ liệu, kiểu dữ liệu, đơn vị đo, điều kiện bắt buộc, phiên bản và quy tắc thay đổi. Hợp đồng này **không nên phụ thuộc** tên class Java, package, ORM entity hoặc cấu trúc domain model của một service.

Giả sử service A gửi sự kiện đơn hàng. Ban đầu A dùng `com.company.sales.OrderEntity`, sau đó refactor thành `com.company.orders.PurchaseAggregate` và đổi một field nội bộ từ `amountCents` thành `grossMinorUnits`. Service B (Spring), C (Python) và D (Go) chỉ cần biết `orderId`, `totalMinor` và `currency` để thực hiện công việc. Nếu message payload là Java serialized object, refactor A có thể khiến consumer hỏng. Nếu A map domain sang JSON contract ổn định, các thay đổi nội bộ sẽ không ảnh hưởng wire.

```text
Producer:
 Domain entity / business aggregate (được quyền refactor)
        |
        v explicit mapper
 Transport DTO OrderPlacedV1 (adapter Java cho contract)
        |
        v JSON serializer / schema validation
 JMS TextMessage + header / properties
        |
        v
       Broker
        |
        v
 Consumer đọc JSON contract v1
        |
        v validate, map sang domain model của chính consumer
```

**Nguyên tắc trung tâm:** Java class là chi tiết triển khai; schema công bố giữa các hệ thống là một API. Có thể dùng Java `record` đại diện schema khi code, nhưng không được mặc định rằng tên class Java hay cách Jackson tự serialize entity chính là hợp đồng công khai.

Kết quả học tập: thiết kế event envelope/payload, xác định schema độc lập ngôn ngữ, map rõ ràng domain ↔ transport DTO, hiểu Spring JMS conversion, quản lý phiên bản/tương thích, viết demo Java 17+ và kiểm thử consumer cũ khi message thay đổi.

## 2. Phân biệt các lớp dữ liệu

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Domain model / entity | Quy tắc nghiệp vụ, trạng thái nội bộ và persistence | `OrderAggregate`, `@Entity Order` |
| Transport DTO | Cấu trúc giao tiếp ở biên producer/consumer | `OrderPlacedV1` record |
| Message schema | Quy định tên, kiểu, required/optional, ngữ nghĩa và version **độc lập ngôn ngữ** | JSON Schema, Avro, Protobuf |
| Serializer / converter | Biến DTO thành text/bytes và ngược lại | Jackson `ObjectMapper`, `MessageConverter` |
| JMS Message | Headers, properties, body của Jakarta Messaging | `TextMessage`, `BytesMessage`, `MapMessage` |
| Broker / destination | Định tuyến, lưu trữ, delivery, ack theo cấu hình | ActiveMQ Artemis queue |

JMS không định nghĩa schema của `OrderPlaced`. `TextMessage` chỉ nói body là chuỗi; broker không biết trường JSON `totalMinor` nghĩa gì. `MapMessage` chứa tên–giá trị có kiểu theo JMS nhưng không thay thế hợp đồng đa phiên bản. `ObjectMessage` dùng Java serialization và không phải format liên ngôn ngữ độc lập class.

### 2.1. Vì sao gửi thẳng Java entity là anti-pattern?

```java
// Minh họa cách KHÔNG NÊN dùng như hợp đồng công khai:
jmsTemplate.convertAndSend("orders.events", orderEntity);
```

Có ít nhất sáu rủi ro:

1. `SimpleMessageConverter` mặc định của Spring JMS **không tự chuyển mọi POJO thành JSON**. Nếu object `Serializable`, nó có thể tạo `ObjectMessage` với Java serialization.
2. Thay đổi tên class/package hoặc `serialVersionUID` có thể làm consumer không deserialize được.
3. Entity JPA có Hibernate proxy, lazy association và vòng tham chiếu; serialize nguyên graph không phản ánh event contract.
4. Có thể vô tình xuất mật khẩu, email, thông tin fraud/risk, trường quản trị hoặc dữ liệu không được phép ra broker.
5. Consumer Python/Go không thể phụ thuộc một Java class trong classpath của producer.
6. Class domain có vòng đời release khác với version của public message contract.

Thay vào đó, tạo **wire DTO riêng**, chỉ chọn trường được phép công bố, rồi serialize qua format đã định nghĩa. Producer và consumer có thể dùng hai class mang tên khác nhau nhưng cùng thỏa contract.

## 3. Mẫu schema sự kiện OrderPlaced v1

Ví dụ payload JSON có cấu trúc cố định:

```json
{
  "schemaVersion": 1,
  "eventType": "order.placed",
  "eventId": "123e4567-e89b-42d3-a456-426614174000",
  "occurredAt": "2026-10-30T02:00:00Z",
  "payload": {
    "orderId": "order-42",
    "totalMinor": 1999,
    "currency": "VND"
  }
}
```

| Trường | Kiểu wire | Ý nghĩa contract | Bắt buộc |
| --- | --- | --- | --- |
| `schemaVersion` | integer | Version major của schema, ở đây là `1` | Có |
| `eventType` | string | Tên sự kiện ổn định `order.placed` | Có |
| `eventId` | UUID string | Nhận diện duy nhất **sự kiện** phục vụ trace/dedup | Có |
| `occurredAt` | date-time string có offset | Thời điểm sự kiện xảy ra, ưu tiên UTC `Z` | Có |
| `payload` | object | Body nghiệp vụ riêng của event | Có |
| `payload.orderId` | string | Mã đơn hàng public | Có |
| `payload.totalMinor` | integer | Số tiền theo **đơn vị nhỏ nhất có định nghĩa** | Có |
| `payload.currency` | string ISO 4217 | Ví dụ `VND` | Có |

**Vì sao có envelope?** Bốn trường `schemaVersion`, `eventType`, `eventId`, `occurredAt` là metadata chung, giúp consumer chọn decoder, ghi log và nhận diện duplicate. `payload` là dữ liệu riêng của `order.placed`. Không đặt tên envelope theo class `com.company.OrderEntity`.

**Vì sao dùng integer tiền?** `double` thường không biểu diễn chính xác các giá trị thập phân, dễ tạo lỗi làm tròn. `totalMinor` là số đơn vị nhỏ nhất đã thống nhất: với `VND` ví dụ 1999 là 1999 đồng; với đồng tiền có phần lẻ, hệ thống phải định nghĩa scale/rounding tương ứng. Nếu dùng decimal string thay thế, cũng phải quy định dấu, độ chính xác, rounding.

**Vì sao timestamp có offset?** `2026-10-30T02:00:00Z` có thể hiểu nhất quán ở mọi timezone. Một `LocalDateTime` Java không gắn múi giờ không phải representation đủ rõ cho event trao đổi liên hệ thống. `occurredAt` là event time, khác processing time của consumer.

### 3.1. ID của event không đồng nghĩa JMS ID

- `eventId`: identifier cấp ứng dụng dành cho event để trace/dedup; cần chính sách giữ nguyên khi cùng event được gửi lại.
- `JMSMessageID`: provider cấp cho một JMS message khi send, có thể khác ở mỗi attempt.
- `JMSCorrelationID`: header để tương quan request–reply hoặc các message liên quan.
- `schemaId`: định danh contract trong registry, không phải ID của message.
- `traceId`: identifier của distributed trace, có thể truyền qua property riêng.

Không dùng một ID cho tất cả chỉ vì tên chúng giống nhau. Chỉ dùng chung khi kiến trúc có quy ước chủ đích.

### 3.2. Null, absent, empty và default

JSON có những trạng thái khác nhau: field hoàn toàn thiếu, field `null`, chuỗi rỗng `""`, số `0`. Nếu `orderId` bắt buộc, vắng mặt/null/rỗng đều không hợp lệ. Nếu `promotionCode` tùy chọn, hợp đồng phải nói rõ absent tương đương gì, `null` có cho phép không và default nào được áp dụng.

Trong Java, một `int` missing từ JSON đôi khi biến thành số `0`, làm che mất thiếu trường. Có thể dùng `Integer`/`Long` cho DTO wire và validate non-null, hoặc dùng JSON Schema validator. **Java type check không thay thế kiểm thử schema đầy đủ**.

## 4. JSON Schema: contract không chứa tên Java package

Một bản định nghĩa bằng JSON Schema Draft 2020-12:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.com/orders/order-placed/v1.schema.json",
  "title": "OrderPlacedV1",
  "type": "object",
  "required": [
    "schemaVersion", "eventType", "eventId", "occurredAt", "payload"
  ],
  "properties": {
    "schemaVersion": { "type": "integer", "const": 1 },
    "eventType": { "type": "string", "const": "order.placed" },
    "eventId": { "type": "string", "format": "uuid" },
    "occurredAt": { "type": "string", "format": "date-time" },
    "payload": {
      "type": "object",
      "required": ["orderId", "totalMinor", "currency"],
      "properties": {
        "orderId": { "type": "string", "minLength": 1 },
        "totalMinor": { "type": "integer", "minimum": 0 },
        "currency": {
          "type": "string",
          "pattern": "^[A-Z]{3}$"
        }
      },
      "additionalProperties": true
    }
  },
  "additionalProperties": true
}
```

Giải thích và giới hạn:

- `required` bắt buộc các trường xuất hiện; `type`/`minimum` quy định kiểu và phạm vi.
- `const` khóa version 1 và event type.
- `additionalProperties: true` cho phép reader v1 bỏ qua field mới *được công bố là optional*, nhưng cũng có thể che một typo. Vì vậy contract governance phải review field, không tùy tiện mở rộng dữ liệu nhạy cảm.
- `format: uuid`/`date-time` cần validator hỗ trợ **format assertion**; không phải mọi engine tự reject định dạng sai.
- Pattern `^[A-Z]{3}$` chưa xác thực currency code có tồn tại trong ISO 4217; cần kiểm tra thêm nếu nghiệp vụ yêu cầu.
- `$id` chỉ là URI minh họa, không phải server/schema registry đã được tạo.
- Schema mô tả cấu trúc, không diễn tả hết ý nghĩa như “totalMinor bao gồm thuế” hoặc “occurredAt là khi đơn được chấp nhận”. Các quy tắc đó cần tài liệu và test ngữ nghĩa.

**Không đưa metadata như** `javaClass=com.company.internal.OrderEntity` hoặc `_type=com.company.persistence.OrderAggregate` vào wire contract. Thay vào đó dùng `eventType`, `schemaVersion` hoặc stable alias/schema ID.

## 5. Tách domain model khỏi wire DTO bằng mapper

Model nội bộ có thể là:

```java
record InternalOrder(
    String internalDbId,
    String publicOrderId,
    long grossInMinorUnits,
    String settlementCurrency
) {}
```

DTO truyền tải:

```java
public record OrderPlacedV1(
    Integer schemaVersion,
    String eventType,
    String eventId,
    String occurredAt,
    Payload payload
) {
    public record Payload(
        String orderId,
        Long totalMinor,
        String currency
    ) {}
}
```

Mapper **chọn có chủ đích**:

```java
// Đoạn code minh họa đặt trong một class có quyền truy cập hai type:
OrderPlacedV1 toWire(InternalOrder domain, String eventId, String time) {
    return new OrderPlacedV1(
        1,
        "order.placed",
        eventId,
        time,
        new OrderPlacedV1.Payload(
            domain.publicOrderId(),
            domain.grossInMinorUnits(),
            domain.settlementCurrency()
        )
    );
}
```

Field `internalDbId` không được xuất bản. Tên `grossInMinorUnits` có thể thay đổi trong Java mà không làm đổi `payload.totalMinor` trên wire. Consumer đọc DTO contract rồi map sang model/command **riêng của consumer**, không nhập JPA entity class từ producer.

### 5.1. Không để Map động đi hết mọi tầng

`Map<String,Object>`/`JsonNode` hữu ích khi đọc envelope để biết `eventType/schemaVersion`, nhưng nếu mọi business layer đều dùng map, sai tên field/missing data dễ xuất hiện muộn ở runtime. Sau bước phân loại schema, parse sang **wire DTO đã version hóa**, validate, rồi chuyển sang domain model.

```text
TextMessage JSON
 → kiểm tra properties eventType/schemaVersion
 → chọn parser/schema
 → parse + validate payload
 → OrderPlacedV1 DTO
 → mapper tường minh
 → consumer-local domain object
 → business handler
```

## 6. MessageConverter trong Spring JMS không tự tạo hợp đồng

`JmsTemplate.convertAndSend` và `receiveAndConvert` dùng `org.springframework.jms.support.converter.MessageConverter`.

| Java value | `SimpleMessageConverter` thường tạo |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` với các kiểu hợp lệ | `MapMessage` |
| `Serializable` | `ObjectMessage` |

Vì thế **không mặc định rằng** `convertAndSend(myDto)` là JSON. Các lựa chọn hợp lý:

1. Dùng `ObjectMapper` serialize **wire DTO**, rồi `JmsTemplate.send(destination, session -> session.createTextMessage(json))`.
2. Tạo custom `MessageConverter` chuyển đúng version của DTO ↔ `TextMessage` hoặc `BytesMessage`.
3. Dùng `MappingJackson2MessageConverter` với `MessageType.TEXT`, type ID aliases ổn định và `setTypeIdMappings(...)`. Nếu không cấu hình mappings khi dùng type property, converter có thể gửi **raw Java class name** — đây là coupling cần tránh. Cần cấu hình các type/trusted packages an toàn.
4. Với Avro/Protobuf, mã hóa bytes trong `BytesMessage` và truyền schema identifier phù hợp.

### 6.1. Đồng bộ metadata body và JMS properties

Ví dụ message có:

```text
JMS Properties:
  eventType     = "order.placed"
  schemaVersion = 1
  contentType   = "application/json"

TextMessage body:
  {"schemaVersion":1,"eventType":"order.placed", ...}
```

Properties giúp JMS selector/consumer định tuyến mà không phải parse body. Tuy vậy **body và JMS properties có thể bị ghi lệch nhau**. Consumer cần reject/quarantine khi type/version ở hai nơi không khớp. `schemaId`, nếu có, phải là ID contract, không phải tên Java class.

JMS selector lọc headers/properties theo semantics chuẩn, **không tự đọc JSON nested field**. Giữ business payload và metadata routing tách biệt.

## 7. Project chạy được: Java 17+, Spring Boot 3.5.7, Artemis, Jackson JSON

Demo gửi một event `order.placed` mà producer có domain field khác tên wire. Consumer nhận raw JMS `TextMessage`, validate version/type, deserialize thành DTO rồi map sang model cục bộ. Có thêm unit test chứng minh consumer v1 đọc được payload chứa optional field mới.

### 7.1. Cấu trúc

```text
jms-contract-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── resources/application.properties
    │   └── java/com/example/contract/
    │       ├── ContractApplication.java
    │       ├── InternalOrder.java
    │       ├── OrderPlacedV1.java
    │       └── OrderPlacedConsumer.java
    └── test/
        └── java/com/example/contract/
            └── ContractCompatibilityTest.java
```

### 7.2. Artemis broker local

```bash
docker run --rm -d --name jms-contract-broker \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine

docker logs jms-contract-broker
```

Đợi broker sẵn sàng. Đây là tài khoản demo **chỉ dùng local**; production cần secret manager, TLS và ACL. Broker lab có thể auto-create queue theo policy; production nên provision trước.

### 7.3. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jms-contract-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-artemis` cung cấp client/infrastructure JMS; JSON starter đưa Jackson vào classpath và Boot tạo bean `ObjectMapper`.

### 7.4. `src/main/resources/application.properties`

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
```

Chỉ dùng credential lab. Không commit mật khẩu thật vào YAML/properties của production; cấp qua biến môi trường hoặc secrets, TLS, quyền tối thiểu.

### 7.5. `InternalOrder.java`

```java
package com.example.contract;

// Model nội bộ của service phát.
record InternalOrder(
        String internalDbId,
        String publicOrderId,
        long grossInMinorUnits,
        String settlementCurrency
) {}
```

### 7.6. `OrderPlacedV1.java`

```java
package com.example.contract;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderPlacedV1(
        Integer schemaVersion,
        String eventType,
        String eventId,
        String occurredAt,
        Payload payload
) {
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Payload(
            String orderId,
            Long totalMinor,
            String currency
    ) {}
}
```

`Integer`/`Long` giúp phân biệt thiếu trường với giá trị số 0. Annotation bỏ qua unknown fields hỗ trợ **một kiểu tương thích** khi producer thêm optional field, nhưng không thay thế schema validation và security checks.

### 7.7. `ContractApplication.java` — producer map domain → wire

```java
package com.example.contract;

import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.TextMessage;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContractApplication.class, args);
    }

    @Bean
    CommandLineRunner publish(JmsTemplate template, ObjectMapper mapper) {
        return args -> {
            InternalOrder domain = new InternalOrder(
                    "internal-db-482", "order-42", 1999L, "VND");

            OrderPlacedV1 event = new OrderPlacedV1(
                    1,
                    "order.placed",
                    UUID.randomUUID().toString(),
                    Instant.now().toString(),
                    new OrderPlacedV1.Payload(
                            domain.publicOrderId(),
                            domain.grossInMinorUnits(),
                            domain.settlementCurrency()
                    )
            );

            // Serialize ngoài callback: Jackson exception không bị
            // ép thành JMSException trong MessageCreator.
            String json = mapper.writeValueAsString(event);

            template.send("demo.contract.order-placed.v1", session -> {
                TextMessage message = session.createTextMessage(json);
                message.setStringProperty("eventType", event.eventType());
                message.setIntProperty("schemaVersion", event.schemaVersion());
                message.setStringProperty("contentType", "application/json");
                return message;
            });
            System.out.println("Published contract: order.placed v1");
        };
    }
}
```

Ở đây `internalDbId` không ra wire. `schemaVersion`, `eventType` có mặt trong body lẫn JMS properties. `JmsTemplate` quản lý connection/session/producer trong phạm vi thao tác; mapper quyết định business contract.

### 7.8. `OrderPlacedConsumer.java` — parse, validate, map DTO

```java
package com.example.contract;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedConsumer {

    private final ObjectMapper mapper;

    OrderPlacedConsumer(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @JmsListener(destination = "demo.contract.order-placed.v1")
    public void consume(TextMessage raw) throws Exception {
        if (!"application/json".equals(
                raw.getStringProperty("contentType"))) {
            throw new IllegalArgumentException("Unsupported content type");
        }
        if (!raw.propertyExists("schemaVersion")
                || raw.getIntProperty("schemaVersion") != 1
                || !"order.placed".equals(
                        raw.getStringProperty("eventType"))) {
            throw new IllegalArgumentException("Unsupported contract");
        }

        OrderPlacedV1 event = mapper.readValue(
                raw.getText(), OrderPlacedV1.class);

        if (!Objects.equals(event.schemaVersion(), 1)
                || !"order.placed".equals(event.eventType())) {
            throw new IllegalArgumentException(
                    "Body and JMS properties mismatch");
        }

        if (event.eventId() == null || event.occurredAt() == null) {
            throw new IllegalArgumentException("Missing envelope field");
        }
        UUID.fromString(event.eventId());
        Instant.parse(event.occurredAt());

        OrderPlacedV1.Payload p = event.payload();
        if (p == null || p.orderId() == null || p.orderId().isBlank()
                || p.totalMinor() == null || p.totalMinor() < 0
                || p.currency() == null
                || !p.currency().matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid payload");
        }

        // Model do consumer tự quản lý; không nhập class nội bộ producer.
        ConsumerOrderView local = new ConsumerOrderView(
                p.orderId(), p.totalMinor(), p.currency());

        System.out.println("Consumed contract: "
                + local.orderId() + " "
                + local.amountMinor() + " "
                + local.currencyCode());
    }
}

record ConsumerOrderView(
        String orderId,
        long amountMinor,
        String currencyCode
) {}
```

Đây là validation **minh họa**: trong production cần JSON Schema validator thực sự, business checks, kích thước payload, idempotency và DLQ handling. `@JmsListener` chạy ở thread độc lập với producer; không dùng thứ tự dòng console để suy delivery ordering.

### 7.9. Chạy demo

```bash
mvn spring-boot:run
```

Với broker sẵn sàng, không có consumer khác trên queue demo, các dòng do code in ra gồm:

```text
Published contract: order.placed v1
Consumed contract: order-42 1999 VND
```

**Thứ tự hai dòng có thể đảo nhau**, vì listener bất đồng bộ. Ngoài chúng còn log Spring và Artemis. Dừng broker:

```bash
docker stop jms-contract-broker
```

Ví dụ không bảo đảm exactly-once processing, failover hoặc atomicity với database; cần thiết kế riêng khi đưa vào production.

## 8. Kiểm thử tương thích khi thêm field optional

Giả sử producer v1.1 gửi thêm `payload.deliveryChannel` và `sourceSystem`. Đó có thể là thay đổi **forward compatible** với reader v1 nếu reader được phép ignore unknown fields; không được thay đổi ý nghĩa của field cũ.

### 8.1. `ContractCompatibilityTest.java`

```java
package com.example.contract;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ContractCompatibilityTest {

    @Test
    void oldReaderAcceptsNewOptionalFields() throws Exception {
        String json = """
                {
                  "schemaVersion": 1,
                  "eventType": "order.placed",
                  "eventId": "123e4567-e89b-42d3-a456-426614174000",
                  "occurredAt": "2026-10-30T02:00:00Z",
                  "payload": {
                    "orderId": "order-42",
                    "totalMinor": 1999,
                    "currency": "VND",
                    "deliveryChannel": "pickup"
                  },
                  "sourceSystem": "web"
                }
                """;

        OrderPlacedV1 event = new ObjectMapper()
                .readValue(json, OrderPlacedV1.class);

        assertEquals(1, event.schemaVersion());
        assertEquals("order-42", event.payload().orderId());
        assertEquals(1999L, event.payload().totalMinor());
        assertEquals("VND", event.payload().currency());
    }
}
```

Chạy bằng `mvn test`. Test được thiết kế để **pass** và cho thấy **một chiều tương thích cụ thể**, không chứng minh tất cả producer/consumer versions đều tương thích. Nếu producer đổi `totalMinor` thành `grossMinorUnits` trên wire và xóa trường cũ, reader v1 sẽ nhận `totalMinor=null` rồi bị validation reject. Refactor Java không phải lý do hợp lệ để đổi schema công khai.

## 9. Versioning và compatibility

**Version contract khác version của JAR.** Có thể phát `schemaVersion=1` sau nhiều lần nâng cấp ứng dụng nếu payload schema/semantics không thay đổi.

| Thay đổi | Tác động phổ biến | Cách xử lý |
| --- | --- | --- |
| Thêm trường optional, reader bỏ unknown | Có thể forward compatible | Test reader cũ |
| Thêm field required cho reader mới | Old message thiếu | Default hoặc breaking version |
| Đổi tên `orderId` thành `id` | Reader cũ mất field | Breaking |
| Xóa required `currency` | Consumer thiếu ngữ cảnh | Breaking |
| `totalMinor` integer → `total` double | Sai kiểu, sai precision | Breaking |
| Đổi đơn vị tiền nhưng giữ tên field | Dữ liệu sai âm thầm | Breaking về ngữ nghĩa |
| Thêm enum value | Old reader có thể không biết | Unknown-value policy |
| Thay timestamp có offset bằng local datetime | Mất timezone | Breaking |
| Đổi Java class/package, giữ JSON wire | Không ảnh hưởng consumer | Không phải breaking |
| Thêm property metadata được phép | Có thể không ảnh hưởng | Test routing |

**Backward compatibility:** reader mới đọc được data do writer cũ tạo. **Forward compatibility:** reader cũ đọc được data từ writer mới. **Full:** cả hai chiều theo chính sách cụ thể. Đừng chỉ hỏi “compatible hay không?” mà không chỉ rõ phiên bản writer và reader nào.

### 9.1. Chiến lược migration breaking

```text
1. Publish schema v2 và migration guide
2. Deploy reader hỗ trợ v1 + v2
3. Bắt đầu phát v2 theo rollout đã thống nhất
4. Quan sát queue backlog, consumer lag, DLQ và lỗi decode
5. Gỡ v1 sau khi hết retention và không còn consumer cũ
```

Có thể giữ `eventType=order.placed` và tăng `schemaVersion=2`, hoặc dùng tên event versioned `order.placed.v2`. Chọn một convention thống nhất giữa body, JMS property và registry. Nếu dual-publish v1/v2, thiết kế dedupe để không xử lý cùng business event hai lần.

**Thay đổi semantics cũng có thể phá hợp đồng** dù JSON parse được: chuyển `totalMinor` từ giá **sau thuế** thành giá **trước thuế** mà giữ nguyên tên/kiểu/version khiến consumer tính sai, thường nguy hiểm hơn một parsing exception.

## 10. Schema-first và contract governance

Quy trình đề xuất:

1. Chỉ định **owner của schema**, producer và consumers.
2. Tài liệu hóa fields, types, required/optional, nullability, units, timezone, enum values, PII, retention và version.
3. Lưu schema trong repository contract hoặc registry có lịch sử, review và quyền truy cập.
4. Dùng code generation cho DTO nếu cần, **không** ép mọi service dùng chung Java entity/JPA library.
5. Tạo golden JSON fixtures, producer tests và consumer compatibility tests.
6. Đưa schema compatibility checks vào CI; yêu cầu review khi có breaking changes.
7. Giám sát `eventType`, `schemaVersion`, invalid schema, DLQ và consumer lag khi deploy.
8. Công bố deprecation và retention window trước khi bỏ schema cũ.

Các kiểm thử nên có cả positive và negative cases: required field thiếu/null, wrong type, malformed JSON, unknown enum, oversize, timezone, mapping sai đơn vị, body/property version mismatch và schema migration.

## 11. JSON, Avro hay Protobuf?

| Tiêu chí | JSON + JSON Schema | Avro | Protobuf |
| --- | --- | --- | --- |
| Dễ đọc khi debug | Cao | Binary khó đọc trực tiếp | Binary khó đọc trực tiếp |
| Contract tách class Java | Có | Có | Có |
| JMS body thường dùng | `TextMessage` | `BytesMessage` | `BytesMessage` |
| Kích thước | Thường lớn hơn binary | Thường gọn | Thường gọn |
| Evolution mechanism | Schema policy/CI | Writer–reader resolution/defaults | Field numbers và presence |
| Hỗ trợ đa ngôn ngữ | Rộng | Rộng | Rộng |
| Bẫy chính | Precision, unknown fields, defaults | Schema ID và union/default rules | Không tái sử dụng field numbers |

Một event nhỏ dễ debug thường phù hợp JSON. Hệ thống tải cao hoặc muốn code generation mạnh có thể cân nhắc Avro/Protobuf. **Định dạng binary không tự làm hợp đồng an toàn** nếu thiếu version governance và semantic validation.

## 12. Giao nhận, security và idempotency

Schema ổn định **không** bảo đảm message được xử lý exactly-once. JMS có thể redeliver khi mất kết nối hoặc transaction rollback; consumer nên dùng `eventId`/business idempotency key và lưu dấu xử lý nếu cần tránh tạo side effect trùng. Nếu producer vừa ghi DB vừa gửi JMS, có thể gặp **dual-write**; `@Transactional` cho database không tự tạo atomic transaction với JMS. Transactional outbox là một cách giảm rủi ro: ghi business change + outbox row trong cùng DB transaction rồi publish có retry.

Bảo mật:

- Chỉ publish field cần thiết; không serialise entity có password/PII/field quản trị.
- Xác thực broker, phân quyền send/consume, TLS, retention và giới hạn kích thước/nesting.
- Không deserialize Java `ObjectMessage` từ nguồn không tin cậy.
- Với type ID converter, dùng stable aliases và allowed classes/trusted packages, không tạo type tùy ý từ Java FQCN trong message.
- Log metadata `eventId`, `eventType`, version, result; tránh full JSON có dữ liệu riêng tư.
- Với message sai schema, quyết định DLQ/quarantine và không retry vô hạn cùng lỗi permanent.

## 13. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Serialize trực tiếp JPA entity | Coupling và lộ field nội bộ | DTO contract tách biệt |
| Dùng raw Java FQCN trong type property | Refactor class làm hỏng consumer | Stable alias/schemaId |
| Mặc định `convertAndSend` tạo JSON | Có thể tạo `ObjectMessage` | JSON converter hoặc explicit TextMessage |
| Refactor Java kéo theo đổi JSON field | Breaking change ngoài ý muốn | Explicit mapper và golden tests |
| Dùng `double` cho tiền | Sai precision/rounding | Integer minor units hoặc decimal string |
| Timestamp không offset | Sai múi giờ | ISO 8601/RFC 3339 offset |
| Enum ordinal trên wire | Thêm enum làm đổi nghĩa | Stable string và unknown policy |
| Thêm required field không migration | Reader cũ/mới lỗi | Optional/default hoặc v2 |
| Ignore unknown nhưng không validate | Che typo/payload lạ | Schema validation + security checks |
| JMS properties khác body | Chọn sai decoder | Check consistency |
| Đổi nghĩa field nhưng giữ version | Parse được nhưng business sai | Semantic review và version mới |
| Không có contract tests | Deploy lệch phiên bản | Fixtures + compatibility matrix |
| Retry poison message vô hạn | Kẹt queue/CPU | DLQ, alert, quarantine |
| Nhầm schema ID với JMS correlation | Decode/route sai | Tách rõ từng identifier |

## 14. Checklist code review

- [ ] Event name và version mang ý nghĩa nghiệp vụ, không dựa Java class.
- [ ] Schema có owner, changelog, fields, types, required/optional và units.
- [ ] Producer map domain → wire DTO, không publish entity/JPA proxy.
- [ ] Consumer map wire DTO → model riêng; validate schema trước business.
- [ ] Không có Java FQCN/serialVersionUID làm identity public.
- [ ] Converter/serializer được cấu hình/test, không giả định POJO thành JSON.
- [ ] `eventType/schemaVersion` của body và JMS properties khớp.
- [ ] Có compatible golden fixtures cho reader/writer phiên bản cũ/mới.
- [ ] Các thay đổi schema được review về cả cấu trúc **và ngữ nghĩa**.
- [ ] Có chính sách malformed/unknown version, retry, DLQ và idempotency.
- [ ] Không lộ secrets/PII, có auth/ACL/TLS và payload size limits.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao không gửi trực tiếp `OrderEntity`?**  
Vì entity là chi tiết triển khai, phụ thuộc Java serialization/JPA và có thể chứa field không được phép công bố.

**2. Java record `OrderPlacedV1` có phải contract duy nhất không?**  
Không. Nó là adapter Java; JSON Schema và các quy tắc nghiệp vụ được công bố mới là contract độc lập ngôn ngữ.

**3. Tại sao `JmsTemplate.convertAndSend(dto)` không mặc nhiên tạo JSON?**  
Vì converter mặc định chọn JMS body type theo Java value; có thể dùng ObjectMessage cho Serializable.

**4. Thêm field optional `deliveryChannel` có luôn tương thích?**  
Không luôn. Chỉ tương thích khi reader cũ bỏ unknown fields hoặc có rule hỗ trợ; cần test.

**5. Đổi field nội bộ Java có cần tăng schema version?**  
Không nếu wire JSON tên/kiểu/ý nghĩa vẫn giữ nguyên.

**6. Đổi `totalMinor` integer thành decimal có breaking không?**  
Có, đổi kiểu/precision và thường đổi semantics, cần migration/version.

**7. Schema ID và `JMSCorrelationID` khác nhau thế nào?**  
Schema ID chọn decoder; JMSCorrelationID dùng liên kết message như request–reply.

**8. JSON Schema có tự bảo đảm exactly-once không?**  
Không. Delivery/transaction/idempotency phải thiết kế riêng.

**9. Vì sao timestamp nên có UTC hoặc offset?**  
Để consumer ở múi giờ khác hiểu cùng một thời điểm.

**10. Khi nào chọn Avro/Protobuf?**  
Khi cần binary compact, code generation và schema tooling mạnh; vẫn cần governance.

## 16. Tài liệu tham khảo chính thức

1. [Spring Framework — JMS Sending and Message Converters](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
2. [Spring Framework 6.2 — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html)
3. [Spring Framework — JMS Reference](https://docs.spring.io/spring-framework/reference/integration/jms.html)
4. [Spring Boot 3.5 — JMS with ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
5. [Spring Boot 3.5 — JSON / Jackson](https://docs.spring.io/spring-boot/3.5/reference/features/json.html)
6. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
7. [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)
8. [Apache Avro Schema Specification](https://avro.apache.org/docs/current/specification/)
9. [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/)
10. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)