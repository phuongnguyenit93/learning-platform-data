# Kiểm thử schema, converter, header và selector

> **Chương:** Kiểm thử  
> **Mục tiêu:** Xây dựng bộ kiểm thử hợp đồng cho message JMS: xác minh schema/payload tương thích theo phiên bản, converter serialize/deserialize đúng kiểu, header và property giữ đúng tên/kiểu dữ liệu, selector lọc đúng message ở broker, và lỗi chuyển đổi được xử lý như poison message có kiểm soát. Ví dụ chính dùng **Java 17, Spring Boot 3, Jakarta Messaging, Jackson và ActiveMQ Artemis**; phần cuối đối chiếu ActiveMQ Classic.

## 1. Vì sao một message gửi thành công vẫn có thể không được consumer xử lý?

Giả sử Order Service gửi sự kiện `OrderCreated` dạng JSON:

```json
{
  "schemaVersion": 2,
  "eventId": "5ec6f0e8-3e31-4a1c-9d77-9d7f3b8e2a10",
  "orderId": "O-1001",
  "amountMinor": 129900,
  "currency": "VND",
  "region": "apac"
}
```

Consumer Billing được triển khai từ phiên bản cũ, chỉ hiểu `schemaVersion=1`. Một message khác có `schemaVersion` được đặt thành **String** `"2"` trong JMS property, trong khi selector lại so sánh số `schemaVersion >= 2`. Consumer không nhận message đó, dù JSON body có version đúng. Một producer khác đặt `eventType` trong payload nhưng quên JMS property cùng tên, khiến selector `eventType = 'OrderCreated'` không match. Cuối cùng, một consumer nhận `TextMessage` nhưng converter lại được cấu hình mong `BytesMessage`, gây conversion exception.

Đây là bốn lớp hợp đồng khác nhau:

| Lớp | Câu hỏi | Ví dụ cần kiểm thử |
|---|---|---|
| **Schema / payload** | JSON có đúng field, type, required fields và version không? | `amountMinor` là integer, `eventId` hợp lệ |
| **Converter** | Body được encode/decode đúng message type và Java DTO không? | JSON ↔ record, type ID mapping |
| **Header / property** | Metadata có tên và JMS data type đúng không? | `eventType` là String, `schemaVersion` là Integer |
| **Selector** | Broker có lọc đúng message theo header/property không? | `eventType='OrderCreated' AND schemaVersion >= 2` |

**Không kiểm thử selector bằng cách gọi một hàm Java `if` rồi coi như đã kiểm thử broker.** Selector được broker áp dụng lúc dispatch message cho consumer/subscription. Muốn chứng minh nó hoạt động phải gửi message vào broker thật (hoặc broker test tương thích) và nhận bằng selector.

## 2. Thiết kế contract: payload, version và metadata

### 2.1. Tách event schema khỏi JMS transport metadata

Một event có thể dùng cấu trúc payload:

Đặt mỗi record ở file riêng, tương ứng OrderCreatedV1.java và OrderCreatedV2.java; đoạn dưới minh họa hai phiên bản cạnh nhau.

```java
public record OrderCreatedV1(
        int schemaVersion,
        String eventId,
        String orderId,
        long amountMinor,
        String currency
) {}

public record OrderCreatedV2(
        int schemaVersion,
        String eventId,
        String orderId,
        long amountMinor,
        String currency,
        String region
) {}
```

Trong ví dụ:

- `schemaVersion` nằm trong payload để consumer có thể lưu trữ/replay event độc lập với JMS.
- `eventId` nhận diện một **sự kiện logic**, ổn định qua publisher retry.
- `orderId` là aggregate/business identifier.
- `amountMinor` là số nguyên đơn vị nhỏ nhất (ví dụ đồng Việt Nam hoặc minor unit của currency đã quy ước), tránh sai số floating point.
- `region` được thêm ở V2; nếu consumer V1 không cần field này thì V1 vẫn có thể đọc event V1. Không được đổi ý nghĩa `amountMinor` hoặc `currency` mà vẫn giữ schema version cũ.

JMS metadata có thể lặp lại một số thông tin để routing/tracing:

| JMS property/header | Kiểu | Mục đích |
|---|---|---|
| `eventType` | String property | Selector phân loại `OrderCreated`, `OrderCancelled` |
| `schemaVersion` | Integer property | Selector lọc version bằng so sánh số |
| `eventId` | String property | Correlation/logging/inbox dedup |
| `region` | String property | Routing/filter khi thực sự cần |
| `JMSCorrelationID` | Header | Liên kết request/reply hoặc trace |
| `JMSType` | Header | Message type label nếu contract quy định |
| `_type` | Converter type-id property | Map JSON body về Java DTO đã allowlist |

**Quy tắc nhất quán:** nếu `schemaVersion`, `eventId`, `eventType` xuất hiện cả trong JSON và JMS properties, producer phải ghi cùng một giá trị. Consumer nên kiểm tra sự trùng khớp; không để selector route theo header version 2 trong khi body lại khai báo version 1.

### 2.2. Schema evolution và backward/forward compatibility

Không phải mọi thay đổi JSON đều tương thích:

| Thay đổi | Mức tương thích thường gặp | Cách xử lý |
|---|---|---|
| Thêm field optional có default | Thường backward-compatible nếu consumer cũ bỏ qua unknown field | Kiểm thử ObjectMapper/contract cũ và mới |
| Thêm field bắt buộc | Có thể làm consumer cũ hoặc event cũ không hợp lệ | Version mới, migration/default rõ |
| Xóa/đổi tên field | Breaking change | Version mới hoặc thời gian dual-read |
| Đổi `amountMinor` integer sang decimal/string | Breaking type change | Field mới/version mới, không tái dùng tên với type khác |
| Đổi enum thêm giá trị | Consumer cũ có thể không parse được | Consumer phải có chiến lược unknown enum hoặc version hóa |
| Đổi ý nghĩa field nhưng giữ type | Nguy hiểm nhất vì parse vẫn thành công | Tạo field/version mới và tài liệu hóa semantics |
| Đổi tên JMS property hoặc đổi String thành Integer | Selector/consumer có thể ngừng match | Kiểm thử header contract như schema độc lập |

Một consumer V1 có thể đọc JSON V2 nếu field mới là optional và converter cho phép unknown fields. Tuy nhiên, **đọc được không đồng nghĩa hiểu đúng nghiệp vụ**. Đừng bật `ignoreUnknown=true` để che một field mới mang ý nghĩa bắt buộc đối với tính tiền hoặc quyền truy cập.

### 2.3. Ma trận contract producer/consumer

Trước khi deploy, ghi rõ:

| Producer | Consumer | Kết quả mong đợi |
|---|---|---|
| V1 | Consumer V1 | Đọc và xử lý |
| V2 (chỉ thêm optional field) | Consumer V1 | Đọc được nếu policy unknown fields cho phép; semantics cũ vẫn đúng |
| V1 | Consumer V2 | Đọc được nếu V2 có default cho field mới |
| V2 (breaking change) | Consumer V1 | Bị từ chối có kiểm soát hoặc route version khác; không parse nhầm |
| Version không hỗ trợ | Consumer hiện tại | Quarantine/DLQ với event ID và version để điều tra |

Contract test phải chạy cho **các cặp version đang được triển khai đồng thời**, không chỉ test DTO hiện tại với chính nó.

### 2.4. Ví dụ JSON Schema cho V2

Khi nhiều ngôn ngữ cùng phát/nhận event, lưu schema độc lập với Java DTO giúp CI kiểm tra contract mà không phụ thuộc một class cụ thể:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "OrderCreatedV2",
  "type": "object",
  "required": [
    "schemaVersion",
    "eventId",
    "orderId",
    "amountMinor",
    "currency",
    "region"
  ],
  "properties": {
    "schemaVersion": { "const": 2 },
    "eventId": { "type": "string", "format": "uuid" },
    "orderId": { "type": "string", "minLength": 1 },
    "amountMinor": { "type": "integer", "minimum": 0 },
    "currency": { "type": "string", "minLength": 3, "maxLength": 3 },
    "region": { "type": "string", "minLength": 1 }
  },
  "additionalProperties": true
}
```

Ở đây để additionalProperties=true nhằm cho phép consumer tương lai đọc thêm field không phá V2; field mới vẫn cần đánh giá semantics và compatibility. Nếu dùng additionalProperties=false, schema trở nên strict và việc thêm field sẽ là breaking change đối với validator theo schema này. Chọn policy theo contract, không bật strict/loose theo thói quen.

## 3. Converter Spring Boot 3: JSON ↔ Jakarta JMS Message

### 3.1. Dependencies và cấu hình

Ví dụ dùng Spring Boot 3.x parent/BOM, Java 17:

```xml
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
```

`spring-boot-starter-json` cung cấp nền tảng Jackson JSON trong Spring Boot 3; nếu project đã có starter web, dependency này có thể đã được kéo vào theo dependency graph. Điều quan trọng là ứng dụng dùng Jackson 2 `ObjectMapper` được cấu hình thống nhất, và JMS API là `jakarta.jms.*`.

Ví dụ `application.yml` cho broker test:

```yaml
spring:
  artemis:
    mode: native
    broker-url: ${ARTEMIS_URL:tcp://localhost:61616}
    user: ${ARTEMIS_USER}
    password: ${ARTEMIS_PASSWORD}
  jms:
    listener:
      auto-startup: true

app:
  messaging:
    order-events-destination: orders.events
```

Không đưa secret vào source control. Với test tích hợp, dùng broker riêng hoặc endpoint test; không chạy test phá hủy trên queue production.

### 3.2. Allowlist type ID thay vì deserialize class tùy ý

`MappingJackson2MessageConverter` hỗ trợ lưu type ID trong JMS property. Dùng một map tên logic → DTO cho phép:

```java
package lab.contract;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

import java.util.Map;

@Configuration
@EnableJms
public class JmsContractConfig {
    @Bean
    MappingJackson2MessageConverter jmsMessageConverter(
            ObjectMapper objectMapper) {
        var converter = new MappingJackson2MessageConverter();
        converter.setObjectMapper(objectMapper);
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(Map.of(
                "order-created-v1", OrderCreatedV1.class,
                "order-created-v2", OrderCreatedV2.class
        ));
        return converter;
    }

    @Bean
    JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            MappingJackson2MessageConverter converter) {
        var template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(converter);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        return template;
    }

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            MappingJackson2MessageConverter converter) {
        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory, connectionFactory);
        factory.setMessageConverter(converter);
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

Giải thích:

- `MessageType.TEXT` yêu cầu converter encode JSON thành `TextMessage`, phù hợp contract JSON text.
- `_type` chứa ID logic như `order-created-v2`, không chứa tên class Java do producer gửi tùy ý.
- `setTypeIdMappings` allowlist các DTO consumer được phép deserialize. Không bật native Java serialization/`ObjectMessage` cho message xuyên service.
- `JmsTemplate` và listener container phải dùng cùng converter để producer/consumer hiểu cùng contract.
- `setSessionTransacted(true)` trong ví dụ giúp listener rollback JMS khi handler ném exception; nó không tự tạo transaction chung với database.

**Lưu ý tương thích:** `MappingJackson2MessageConverter` là converter Jackson 2 trong Spring JMS. Nếu dự án chuyển Jackson generation hoặc Spring Framework version, kiểm tra package/API thực tế theo BOM; không trộn converter Jackson 3 với cấu hình Jackson 2.

### 3.3. DTO phải có contract rõ ràng

Ví dụ Java records:

```java
package lab.contract;

public record OrderCreatedV1(
        int schemaVersion,
        String eventId,
        String orderId,
        long amountMinor,
        String currency
) {}

public record OrderCreatedV2(
        int schemaVersion,
        String eventId,
        String orderId,
        long amountMinor,
        String currency,
        String region
) {}
```

Trong production, thêm validator cho `eventId`, `orderId`, `schemaVersion`, currency, miền giá trị và semantics. Converter chỉ chứng minh JSON có thể chuyển thành Java object; nó không tự chứng minh message hợp lệ về nghiệp vụ.

### 3.4. Gửi payload kèm header/property có kiểu chính xác

Producer V2:

```java
package lab.contract;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;
import java.util.UUID;

@Component
public class OrderEventPublisher {
    private final JmsTemplate jms;
    private final String destination;

    public OrderEventPublisher(
            JmsTemplate jms,
            @Value("${app.messaging.order-events-destination}")
            String destination) {
        this.jms = jms;
        this.destination = destination;
    }

    public UUID publishV2(String orderId, long amountMinor,
                          String currency, String region) {
        UUID eventId = UUID.randomUUID();
        var event = new OrderCreatedV2(
                2, eventId.toString(), orderId,
                amountMinor, currency, region);

        jms.convertAndSend(destination, event, message -> {
            message.setStringProperty("eventType", "OrderCreated");
            message.setIntProperty("schemaVersion", 2);
            message.setStringProperty("eventId", eventId.toString());
            message.setStringProperty("region", region);
            message.setJMSCorrelationID(orderId);
            message.setJMSType("OrderCreated");
            return message;
        });
        return eventId;
    }
}
```

Điểm cần kiểm tra:

1. Converter ghi `_type=order-created-v2` theo mapping.
2. Body JSON chứa `schemaVersion=2`.
3. JMS property `schemaVersion` là **Integer** do `setIntProperty`, không phải chuỗi `"2"`.
4. `eventId` trong property trùng `event.eventId`.
5. `JMSCorrelationID` là standard header, được set qua API `setJMSCorrelationID`; không tự tạo một property tên `JMSCorrelationID`.
6. `JMSType` là standard header; `eventType` là application property dùng trong selector.

Nếu có `schemaVersion` trong JSON nhưng không có property tương ứng, consumer selector không thể đọc field trong JSON body. JMS selector không parse nội dung JSON.

## 4. Header và property: kiểm thử đúng tên, đúng kiểu, đúng nguồn

### 4.1. Phân biệt standard JMS headers và application properties

JMS message có các standard headers được truy cập bằng method của `jakarta.jms.Message`; một số header do provider gán, một số header producer được phép đặt. Application properties là metadata do ứng dụng định nghĩa và thường được dùng trong selector.

| Trường | Ai thường đặt? | API | Có thể dùng trong selector? |
|---|---|---|---|
| `JMSMessageID` | Provider | `getJMSMessageID()` | Có |
| `JMSTimestamp` | Provider | `getJMSTimestamp()` | Có |
| `JMSCorrelationID` | Ứng dụng | `setJMSCorrelationID()` | Có |
| `JMSType` | Ứng dụng | `setJMSType()` | Có |
| `JMSPriority` | Producer/provider | `setJMSPriority()` | Có |
| `JMSDeliveryMode` | Producer/provider | `setJMSDeliveryMode()` | Có |
| `JMSDestination` | Provider | `getJMSDestination()` | Không dùng làm selector field chuẩn |
| `JMSReplyTo` | Ứng dụng | `setJMSReplyTo()` | Không dùng làm selector field chuẩn |
| `eventType` | Ứng dụng | `setStringProperty()` | Có |
| `schemaVersion` | Ứng dụng | `setIntProperty()` | Có |
| `JMSXDeliveryCount` | Provider | `getIntProperty()` | Là JMSX property; hỗ trợ selector tùy provider, không dùng làm routing contract portable |

Các header provider-set như `JMSMessageID`/`JMSTimestamp` không nên tự giả lập bằng application properties cùng tên. Tránh tự đặt application property bắt đầu bằng `JMSX` hoặc `JMS_` vì đây là namespace dành cho JMS/provider; dùng prefix riêng như `app_` hoặc tên contract rõ ràng.

### 4.2. JMS property có kiểu dữ liệu cụ thể

JMS selector so sánh theo **kiểu property**, không nên trông chờ broker tự chuyển String thành số:

```java
message.setStringProperty("eventType", "OrderCreated");
message.setIntProperty("schemaVersion", 2);
message.setLongProperty("amountMinor", 129900L);
message.setBooleanProperty("priorityOrder", false);
message.setStringProperty("region", "apac");
message.setStringProperty("eventId", eventId.toString());
```

Tránh:

```java
// Sai contract nếu selector mong schemaVersion là số.
message.setStringProperty("schemaVersion", "2");

// JMS property không nhận tùy ý mọi Java object.
message.setObjectProperty("eventId", UUID.randomUUID());
message.setObjectProperty("occurredAt", java.time.Instant.now());
```

Các kiểu property portable gồm primitive wrapper tương ứng (Boolean, Byte, Short, Integer, Long, Float, Double) và String. UUID/Instant/BigDecimal/enum nên được chuyển thành String hoặc số nguyên theo contract đã quy ước. Property names phân biệt hoa thường; `schemaVersion` và `SchemaVersion` là hai tên khác nhau.

### 4.3. Kiểm tra header consistency ở consumer

Nếu version và event ID được lặp lại trong body lẫn properties, validator phải đối chiếu:

```java
package lab.contract;

import jakarta.jms.JMSException;
import jakarta.jms.Message;

public final class MessageContractValidator {
    private MessageContractValidator() {}

    public static void validate(OrderCreatedV2 event, Message message)
            throws JMSException {
        if (event.schemaVersion() != 2) {
            throw new IllegalArgumentException("Expected body schema v2");
        }
        Object eventTypeProperty = message.getObjectProperty("eventType");
        if (!(eventTypeProperty instanceof String eventType)
                || !"OrderCreated".equals(eventType)) {
            throw new IllegalArgumentException("Wrong eventType property");
        }
        Object versionProperty = message.getObjectProperty("schemaVersion");
        if (!(versionProperty instanceof Integer headerVersion)
                || headerVersion != event.schemaVersion()) {
            throw new IllegalArgumentException(
                    "Header/body schemaVersion mismatch");
        }
        Object eventIdProperty = message.getObjectProperty("eventId");
        if (event.eventId() == null || event.eventId().isBlank()
                || !(eventIdProperty instanceof String headerEventId)
                || !event.eventId().equals(headerEventId)) {
            throw new IllegalArgumentException(
                    "Header/body eventId mismatch");
        }
        if (event.orderId() == null || event.orderId().isBlank()
                || event.amountMinor() < 0) {
            throw new IllegalArgumentException("Invalid event fields");
        }
    }
}
```

Trong code thật, kiểm tra null trước khi gọi method trên field, validate currency/region theo allowlist và dùng Bean Validation hoặc validator domain nếu phù hợp. Đoạn trên minh họa contract giữa body và JMS metadata; converter parse thành công chưa đủ để chấp nhận event.

### 4.4. Header/property test matrix

| Trường hợp | Cách gửi | Kỳ vọng |
|---|---|---|
| schemaVersion Integer | `setIntProperty("schemaVersion", 2)` | Selector numeric match |
| schemaVersion String | `setStringProperty("schemaVersion", "2")` | Không được coi như numeric 2; test phải phát hiện sai type |
| Thiếu eventType | Không set property | Selector equality không match |
| eventType sai chữ hoa/thường | `ordercreated` thay vì `OrderCreated` | Không match selector exact string |
| eventId trong body khác property | Set hai giá trị khác nhau | Validator từ chối/quarantine |
| Property tên khác casing | `SchemaVersion` thay vì `schemaVersion` | Selector không tìm thấy property đúng |
| JMSCorrelationID | Dùng `setJMSCorrelationID` | Đọc lại qua `getJMSCorrelationID`, không nhầm với property |

## 5. Selector: cú pháp SQL subset và semantics

### 5.1. Selector chạy ở broker, chỉ đọc header/property

Một selector hợp lệ:

```sql
eventType = 'OrderCreated'
AND schemaVersion >= 2
AND region IN ('apac', 'emea')
AND priorityOrder = FALSE
```

Selector chỉ đọc standard JMS headers được hỗ trợ và message properties. Nó **không** truy cập JSON body như `payload.orderId`, không gọi hàm Java và không chạy JSONPath. Nếu muốn filter theo `region`, producer phải publish property `region` đúng kiểu String.

JMS selector dùng một tập con biểu thức kiểu SQL-92:

| Toán tử/cú pháp | Ví dụ |
|---|---|
| So sánh | `schemaVersion >= 2` |
| Logic | `A = 1 AND B = 'x'` |
| `BETWEEN` | `amountMinor BETWEEN 1000 AND 500000` |
| `IN` | `region IN ('apac', 'emea')` |
| `LIKE` | `eventType LIKE 'Order%'` |
| `IS NULL` | `region IS NULL` |
| `IS NOT NULL` | `eventId IS NOT NULL` |
| `NOT` | `NOT (priorityOrder = TRUE)` |

Không dùng cú pháp tùy tiện như `contains()`, regex, truy cập nested JSON, hoặc hàm custom. Dùng ngoặc để biểu đạt rõ precedence của `NOT`, `AND`, `OR`.

### 5.2. Ba giá trị logic và property không tồn tại

Selector không chỉ có TRUE/FALSE; biểu thức có thể là **UNKNOWN** khi property không tồn tại hoặc giá trị NULL theo semantics selector. Consumer chỉ nhận message khi selector đánh giá TRUE.

Ví dụ:

```sql
region = 'apac'
```

Nếu message không có property `region`, nó không match. Với:

```sql
region IS NULL OR region <> 'blocked'
```

message thiếu `region` có thể match nhánh `IS NULL`; phải viết selector có chủ đích, không dựa vào cách hiểu “thiếu field chắc chắn là false”.

### 5.3. Kiểu số và chuỗi không tự chuyển đổi

Nếu producer gửi:

```java
message.setIntProperty("schemaVersion", 2);
```

selector:

```sql
schemaVersion >= 2
```

sẽ so sánh numeric. Nếu producer gửi cùng giá trị dưới dạng String, không nên kỳ vọng broker ép kiểu. Kết quả có thể không match hoặc biểu thức không hợp lệ tùy selector/provider; test phải bắt lỗi contract thay vì dựa vào coercion.

Với chuỗi, literal phải đặt trong dấu nháy đơn:

```sql
eventType = 'OrderCreated'
```

Chuỗi selector phân biệt hoa thường; tên property cũng phải đúng casing.

### 5.4. Selector queue và selector topic subscription

- **Queue:** nhiều consumers có selector khác nhau có thể cạnh tranh nhận các message thỏa selector tương ứng. Message không match một consumer vẫn có thể nằm lại queue để consumer khác có selector phù hợp nhận; nếu không consumer nào match, queue depth không giảm.
- **Non-durable topic:** chỉ các subscribers đang hoạt động nhận message phù hợp selector của họ; offline subscriber không có backlog.
- **Durable topic:** selector là một phần cấu hình logical subscription. Không tự đổi selector trên subscription đang có backlog rồi giả định message cũ được lọc lại theo rule mới. Thay đổi selector cần kế hoạch migration: subscription mới, dual-run/đối soát backlog, cutover và cleanup có kiểm soát.
- **Shared durable:** nhiều consumers chia message của cùng subscription; selector phải thống nhất theo subscription identity, không phải mỗi replica tự định nghĩa filter khác nhau.

Một selector quá hẹp có thể khiến queue backlog tăng mà consumer count vẫn > 0. Dashboard cần quan sát cả MessageCount, ConsumerCount, selector config và số message match.

### 5.5. Selector không phải cơ chế authorization

Selector lọc message để dispatch; nó không thay ACL. Consumer không có quyền consume vẫn bị broker từ chối dù selector rất hẹp. Ngược lại, consumer có quyền consume có thể đọc tất cả message được phép trên queue nếu không có selector. Quyền truy cập phải được quản lý ở broker security policy, còn selector chỉ phục vụ routing/filter logic.

## 6. Consumer contract: deserialize, validate rồi mới chạy nghiệp vụ

### 6.1. Listener phân tách theo version

Khi V1 và V2 có semantics khác nhau, listener có thể chọn DTO bằng type ID converter và dùng selector để nhận đúng phiên bản:

```java
package lab.contract;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventConsumers {
    @JmsListener(
        destination = "orders.events",
        selector = "eventType = 'OrderCreated' AND schemaVersion = 1",
        containerFactory = "jmsListenerContainerFactory")
    public void onV1(OrderCreatedV1 event) {
        validateV1(event);
        // Gọi handler V1 hoặc adapter chuyển về canonical domain command.
    }

    @JmsListener(
        destination = "orders.events",
        selector = "eventType = 'OrderCreated' AND schemaVersion = 2",
        containerFactory = "jmsListenerContainerFactory")
    public void onV2(OrderCreatedV2 event) {
        validateV2(event);
    }

    private void validateV1(OrderCreatedV1 event) {
        if (event.schemaVersion() != 1
                || event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()
                || event.amountMinor() < 0) {
            throw new IllegalArgumentException("Invalid OrderCreated V1");
        }
    }

    private void validateV2(OrderCreatedV2 event) {
        if (event.schemaVersion() != 2
                || event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()
                || event.amountMinor() < 0
                || event.region() == null || event.region().isBlank()) {
            throw new IllegalArgumentException("Invalid OrderCreated V2");
        }
    }
}
```

Ví dụ trên minh họa hai selector độc lập. Nếu cần đối chiếu header với body, listener nên nhận cả raw Message và payload qua method signature/adapter phù hợp, hoặc thực hiện validation trong converter/interceptor trước khi dispatch vào handler. Không được bỏ qua header/body mismatch chỉ vì DTO parse thành công.

### 6.2. Selector không có consumer phù hợp sẽ để message tồn tại

Giả sử queue có:

- V1 consumer selector schemaVersion = 1.
- V2 consumer selector schemaVersion = 2.

Nếu producer gửi version 3, không consumer nào match; message có thể tiếp tục nằm ở queue ready. Nó **không tự động thành DLQ** chỉ vì selector không match. Cần một chiến lược cho version không hỗ trợ:

1. Dùng consumer kiểm tra/quarantine riêng có selector bắt các version không hỗ trợ, ví dụ schemaVersion IS NULL OR schemaVersion NOT IN (1, 2).
2. Hoặc chỉ có một consumer dispatch, đọc envelope rồi phân loại version trong ứng dụng.
3. Cảnh báo queue backlog và số message không match; không để version lạ nằm vô thời hạn mà không có owner.

Selector quarantine cần được thiết kế cẩn thận để không tranh message hợp lệ với consumer version-specific. Nếu dùng cùng ANYCAST queue, selectors phải **loại trừ nhau** hoặc có một dispatcher duy nhất; test integration phải chứng minh mỗi message đi đúng một handler.

### 6.3. Converter exception khác validation exception

| Lỗi | Xảy ra ở đâu? | Cách quan sát |
|---|---|---|
| JSON malformed | Converter parse body | Jackson parsing exception; listener method có thể chưa được gọi |
| Type ID không nằm trong mapping | Converter không xác định DTO được phép | Conversion/type mapping exception |
| JSON hợp lệ nhưng thiếu field bắt buộc | Sau parse, validator phát hiện | Validation exception có event ID nếu metadata đọc được |
| Header/body version mismatch | Boundary validator | Contract violation |
| Business rule fail | Domain handler | Business rejection hoặc compensation; không nhất thiết poison message |

Không retry vô hạn lỗi schema vĩnh viễn. Với Artemis, cấu hình max-delivery-attempts, delay và DLQ phù hợp; message poison sau budget được chuyển sang DLQ để điều tra. Với lỗi tạm thời (DB timeout, dependency 503), retry/backoff có thể hợp lý. Phân loại lỗi giúp tránh việc một message JSON sai schema chiếm consumer và tạo redelivery storm.

**Không đánh đồng validation failure với business rejection.** Một event đúng schema nhưng order đã hủy có thể là kết quả nghiệp vụ hợp lệ cần phát event từ chối/compensation; nó không nên bị đưa vào DLQ như message hỏng cấu trúc.

## 7. Kiểm thử converter và selector với broker thật

### 7.1. Unit test schema/DTO

Kiểm tra fixture JSON ở cấp Jackson/validator:

```java
package lab.contract;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderSchemaTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void readsV2FixtureAndPreservesVersionAndAmount() throws Exception {
        String json = """
            {
              "schemaVersion": 2,
              "eventId": "5ec6f0e8-3e31-4a1c-9d77-9d7f3b8e2a10",
              "orderId": "O-1001",
              "amountMinor": 129900,
              "currency": "VND",
              "region": "apac"
            }
            """;

        OrderCreatedV2 event =
                mapper.readValue(json, OrderCreatedV2.class);

        assertEquals(2, event.schemaVersion());
        assertEquals(129900L, event.amountMinor());
        assertEquals("apac", event.region());
        assertDoesNotThrow(() -> validateV2(event));
    }

    @Test
    void rejectsMissingRequiredBusinessFields() {
        var event = new OrderCreatedV2(
                2, "", "O-1001", -1, "VND", "");
        assertThrows(IllegalArgumentException.class,
                () -> validateV2(event));
    }

    private static void validateV2(OrderCreatedV2 event) {
        if (event.schemaVersion() != 2
                || event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()
                || event.amountMinor() < 0
                || event.currency() == null || event.currency().isBlank()
                || event.region() == null || event.region().isBlank()) {
            throw new IllegalArgumentException("Invalid V2 contract");
        }
    }
}
```

Unit test không cần broker; nó kiểm tra payload parsing và domain validation. ObjectMapper trong test nên lấy từ Spring context hoặc cấu hình giống production khi có custom modules/naming strategy/deserialization settings. Nếu test tạo một ObjectMapper khác cấu hình production, nó chỉ kiểm tra default Jackson chứ không kiểm tra converter thật.

### 7.2. Integration test selector và converter qua JmsTemplate

Kiểm thử sau phải chạy với Artemis broker test đã sẵn sàng, JmsContractConfig được nạp và auto-create destination được bật **chỉ trong môi trường test**, hoặc queue test được provision trước.

```java
package lab.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jms.core.JmsTemplate;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class JmsContractIntegrationTest {
    @Autowired
    JmsTemplate jms;

    @Test
    void converterRoundTripsAndSelectorSelectsOnlyV2() {
        String queue = "test.contract." + UUID.randomUUID();
        var v1 = new OrderCreatedV1(
                1, UUID.randomUUID().toString(),
                "O-V1", 1000L, "VND");
        var v2 = new OrderCreatedV2(
                2, UUID.randomUUID().toString(),
                "O-V2", 2000L, "VND", "apac");

        jms.convertAndSend(queue, v1, message -> {
            message.setStringProperty("eventType", "OrderCreated");
            message.setIntProperty("schemaVersion", 1);
            message.setStringProperty("eventId", v1.eventId());
            return message;
        });
        jms.convertAndSend(queue, v2, message -> {
            message.setStringProperty("eventType", "OrderCreated");
            message.setIntProperty("schemaVersion", 2);
            message.setStringProperty("eventId", v2.eventId());
            message.setStringProperty("region", "apac");
            return message;
        });

        jms.setReceiveTimeout(3000L);
        Object selected = jms.receiveSelectedAndConvert(
                queue,
                "eventType = 'OrderCreated' " +
                "AND schemaVersion >= 2 AND region = 'apac'");
        assertInstanceOf(OrderCreatedV2.class, selected);
        assertEquals(v2.eventId(),
                ((OrderCreatedV2) selected).eventId());

        // Message V1 không match selector vẫn còn trong queue.
        Object remaining = jms.receiveSelectedAndConvert(
                queue,
                "eventType = 'OrderCreated' AND schemaVersion = 1");
        assertInstanceOf(OrderCreatedV1.class, remaining);
        assertEquals(v1.eventId(),
                ((OrderCreatedV1) remaining).eventId());
    }
}
```

Test này chứng minh đồng thời:

1. JmsTemplate dùng converter cấu hình thật để encode DTO thành JMS message và decode về đúng class.
2. Header/property eventType, schemaVersion, region được gửi đúng kiểu.
3. Selector thực sự được broker áp dụng: V2 được nhận trước, V1 không match và vẫn còn trong queue.
4. Type ID mapping _type chọn đúng OrderCreatedV1/OrderCreatedV2.

JmsTemplate được đặt receive timeout để test không treo vô hạn. Queue tên ngẫu nhiên tránh dữ liệu tồn từ test khác; nếu broker tắt auto-create, provision queue test trước và cleanup bằng management API/test fixture có kiểm soát. Không chạy purge trên queue dùng chung.

### 7.3. Kiểm thử property sai kiểu và header/body mismatch

Tạo một message sai contract trong integration test:

```java
jms.convertAndSend(queue, v2, message -> {
    message.setStringProperty("eventType", "OrderCreated");
    // Cố ý sai: selector mong Integer.
    message.setStringProperty("schemaVersion", "2");
    message.setStringProperty("eventId", "different-id");
    return message;
});
```

Test phải chứng minh producer contract bị từ chối. Không khóa bài test vào một phản ứng không portable như “mọi broker chắc chắn throw cùng một exception cho so sánh String >= Integer”. Thay vào đó:

- Kiểm tra property type khi nhận raw Message không selector và xác nhận schemaVersion không phải numeric property theo contract.
- Chạy validator header/body và xác nhận event ID mismatch bị từ chối.
- Chạy selector numeric và xác minh message sai kiểu không được coi là V2 hợp lệ; nếu broker ném selector/type error, ghi nhận hành vi cụ thể của version đó.

Với các test cần xác định exact exception của Artemis hoặc Classic, viết **provider-specific integration test** và đặt tên rõ ràng; không gộp nó vào bộ portability contract.

## 8. Durable topic selector: kiểm thử subscription identity và backlog

Selector của durable topic subscription được gắn với logical subscription. Vì vậy cần test cả ba thời điểm: subscription được tạo, publisher gửi khi subscriber offline, và subscriber quay lại bằng cùng danh tính.

Với Artemis, topic JMS cần multicast address. Nếu broker test tắt auto-create, provision fragment này trong khối addresses hiện có của broker.xml:

```xml
<address name="orders.events">
    <multicast/>
</address>
```

Queue subscription durable do broker quản lý; xác minh subscription queue/binding được tạo và principal test có quyền cần thiết.

Ví dụ kiểm thử bằng Jakarta JMS API:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import jakarta.jms.Topic;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class DurableSelectorIntegrationTest {
    @org.springframework.beans.factory.annotation.Autowired
    private ConnectionFactory connectionFactory;

    // Chạy với @SpringBootTest và Artemis test broker đã provision topic.

    @Test
    void durableSubscriptionKeepsOnlyMessagesMatchingItsSelector()
            throws Exception {
        String clientId = "contract-test-" + UUID.randomUUID();
        String subscription = "orders-v2-only";

        // Step 1: create the durable subscription, then go offline.
        try (Connection connection = connectionFactory.createConnection()) {
            connection.setClientID(clientId);
            try (Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE)) {
                Topic topic = session.createTopic("orders.events");
                try (MessageConsumer ignored =
                        session.createDurableConsumer(
                            topic, subscription,
                            "eventType = 'OrderCreated' " +
                            "AND schemaVersion = 2",
                            false)) {
                    // Closing the consumer leaves the durable subscription.
                }
            }
        }

        // Step 2: publish while that durable subscriber is offline.
        try (Connection connection = connectionFactory.createConnection();
             Session session = connection.createSession(
                     false, Session.AUTO_ACKNOWLEDGE)) {
            Topic topic = session.createTopic("orders.events");
            try (MessageProducer producer = session.createProducer(topic)) {
                producer.setDeliveryMode(DeliveryMode.PERSISTENT);
                TextMessage v1 = session.createTextMessage("v1");
                v1.setStringProperty("eventType", "OrderCreated");
                v1.setIntProperty("schemaVersion", 1);
                producer.send(v1);

                TextMessage v2 = session.createTextMessage("v2");
                v2.setStringProperty("eventType", "OrderCreated");
                v2.setIntProperty("schemaVersion", 2);
                producer.send(v2);
            }
        }

        // Step 3: reconnect with exactly the same client ID and name.
        try (Connection connection = connectionFactory.createConnection()) {
            connection.setClientID(clientId);
            try (Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE)) {
                Topic topic = session.createTopic("orders.events");
                MessageConsumer consumer = session.createDurableConsumer(
                        topic, subscription,
                        "eventType = 'OrderCreated' " +
                        "AND schemaVersion = 2",
                        false);
                try {
                    connection.start();
                    Message received = consumer.receive(3000L);
                    assertNotNull(received);
                    assertEquals("v2",
                            ((TextMessage) received).getText());
                    assertNull(consumer.receive(500L));
                } finally {
                    try {
                        consumer.close();
                    } finally {
                        session.unsubscribe(subscription);
                    }
                }
            }
        }
    }
}
```

Test này yêu cầu broker test có multicast address/topic và cho phép durable subscription. Consumer tạo subscription trước, đóng consumer nhưng giữ subscription; publisher gửi V1/V2 khi subscriber offline; khi mở lại với cùng client ID/name, chỉ V2 match selector. Cuối test unsubscribe để xóa subscription lab và backlog còn lại.

**Điểm cần kiểm soát:** nếu test fail trước đoạn cleanup, subscription có thể còn lại trong broker. Dùng client ID có UUID riêng và có teardown dọn các subscription test bị bỏ dở qua management fixture. Không dùng client ID production hoặc unsubscribe subscription đang chứa backlog nghiệp vụ.

### 8.1. Thay selector là migration, không phải chỉnh tham số tại chỗ

Nếu selector hiện tại là schemaVersion = 2 và muốn nhận cả V1/V2, không được mở một consumer mới cùng durable identity với selector khác rồi mong broker thay rule mà giữ backlog nguyên vẹn. Cách an toàn:

1. Tạo subscription mới với tên/version mới và selector mới.
2. Kiểm tra quyền, backlog, retention và producer publication window.
3. Dual-run hoặc replay/backfill có kiểm soát, dedup bằng eventId.
4. Đối soát số event đã nhận ở subscription cũ và mới.
5. Chuyển consumer ownership; chỉ unsubscribe subscription cũ sau khi backlog được xử lý và owner xác nhận.

## 9. Kiểm thử lỗi converter và quarantine

### 9.1. Gửi payload không parse được

Một message JSON sai cú pháp hoặc có type ID không nằm trong allowlist sẽ thất bại ở converter trước khi listener method được gọi. Với listener transacted, lỗi conversion thường làm delivery rollback; nếu broker retry mãi, một poison message có thể chiếm tài nguyên.

Ví dụ Artemis test address setting cho destination kiểm thử:

```xml
<address-setting match="test.contract.#">
    <dead-letter-address>DLQ</dead-letter-address>
    <max-delivery-attempts>3</max-delivery-attempts>
    <redelivery-delay>250</redelivery-delay>
    <max-redelivery-delay>1000</max-redelivery-delay>
</address-setting>
```

Đây là fragment chèn vào khối address-settings hiện có. DLQ address/queue phải được provision và binding đúng. Giá trị retry nhỏ chỉ dành cho test; production cần delay/budget theo SLA và downstream capacity.

### 9.2. Các ca lỗi phải có test riêng

| Ca | Input | Kỳ vọng |
|---|---|---|
| JSON malformed | TextMessage body thiếu dấu ngoặc/quote | Converter lỗi; message rollback và đi DLQ sau budget |
| Type ID không allowlist | _type=java.lang.Runtime hoặc ID lạ | Converter từ chối; không deserialize class tùy ý |
| Thiếu type ID | Không có _type trong message yêu cầu typed mapping | Conversion failure rõ ràng |
| Schema version lạ | Body/header version 99 | Không route vào handler V1/V2; quarantine hoặc version-unsupported handler |
| Header/body mismatch | Header schemaVersion=2, body schemaVersion=1 | Validator từ chối, log event ID |
| Property sai type | schemaVersion là String | Contract test thất bại; selector numeric không coi đó là số |
| Business rejection | Payload hợp lệ nhưng order đã cancel | Domain xử lý rejection/compensation, không coi là poison message |

Không phải mọi lỗi đều nên vào cùng DLQ. Có thể tách quarantine cho contract/schema violations và DLQ cho delivery attempts exhausted; cách tách cần có event ID, source address, reason code và retention.

### 9.3. Replay sau khi sửa schema

Khi sửa consumer để hỗ trợ schema mới:

- Giữ nguyên logical eventId khi replay cùng event.
- Kiểm tra inbox/business database trước khi áp dụng side effect.
- Replay theo batch nhỏ, giới hạn tốc độ và ghi audit record.
- Xác minh số message DLQ giảm **và** số business effects hợp lệ tăng tương ứng.
- Không dùng converter permissive vô điều kiện để biến mọi payload lạ thành DTO; validate version/required fields sau deserialize.

## 10. ActiveMQ Classic: portable contract, broker test riêng

JMS selector là một phần của Jakarta/JMS contract, nên biểu thức cơ bản như eventType equality, numeric version comparison, IN/LIKE/IS NULL có tính portable. Tuy nhiên converter, client namespace, destination topology và broker management là phần cần kiểm tra theo provider.

| Khía cạnh | Artemis | ActiveMQ Classic |
|---|---|---|
| Client trong ví dụ chính | Artemis Jakarta client / Spring Artemis starter | Classic client tương thích Jakarta JMS với Spring Boot 3 |
| Queue/topic | Address + ANYCAST/MULTICAST | Queue/topic destination của Classic |
| DLQ config | address-settings, dead-letter-address | dead-letter strategy trong activemq.xml |
| Expiry | expiry-address và queue bindings | Expiry/dead-letter behavior theo Classic policy |
| Selector | JMS selector được broker thực thi | JMS selector được broker thực thi |
| Management | Artemis QueueControl/JMX | Classic destination MBeans/JMX |

Không copy Artemis broker.xml vào activemq.xml. Khi kiểm thử Classic, dùng starter/client đúng Jakarta namespace của phiên bản đã chọn; không trộn client javax.jms cũ với Spring Boot 3. Chạy cùng contract test suite trên **mỗi broker profile** để phát hiện khác biệt parser/selector/provider behavior.

## 11. Checklist thiết kế bộ kiểm thử contract

### Unit tests

- [ ] Deserialize JSON fixtures cho mọi schema version đang hỗ trợ.
- [ ] Kiểm tra required fields, numeric ranges, enum values, timestamp và business invariants.
- [ ] Kiểm tra converter type ID allowlist và unknown type ID.
- [ ] Kiểm tra serialization không vô tình đổi tên field, số thành chuỗi hoặc bỏ field quan trọng.
- [ ] Kiểm tra body/header eventId, eventType, schemaVersion nhất quán.

### Broker integration tests

- [ ] Producer gửi đúng JMS Message type (TextMessage/BytesMessage) và converter round-trip về đúng DTO.
- [ ] Header/property được lưu với đúng tên, casing và primitive type.
- [ ] Selector equality, numeric comparison, IN/LIKE/IS NULL hoạt động với broker thật.
- [ ] Message không match selector vẫn ở đúng queue hoặc subscription backlog.
- [ ] Durable topic subscriber giữ selector, client ID và subscription name qua offline/reconnect.
- [ ] Selector không hỗ trợ version không làm message biến mất; có quarantine/unsupported-version path.
- [ ] Malformed payload và unknown type ID rollback/DLQ theo retry budget.
- [ ] Queue/DLQ/subscription test được cleanup có kiểm soát sau khi đối soát.

### Release checks

- [ ] Producer và consumer versions đang chạy đồng thời có contract compatibility matrix.
- [ ] Schema breaking change có version mới hoặc migration plan.
- [ ] Selector không dựa vào provider-specific property nếu cần portability.
- [ ] Không dùng event ID/PII làm metric label hoặc selector không cần thiết.
- [ ] DLQ/quarantine có owner, retention, replay procedure và audit.
- [ ] Bộ test chạy riêng cho Artemis và Classic nếu module hỗ trợ cả hai.

**Kết luận:** kiểm thử schema, converter, header và selector phải kiểm tra trọn đường đi của một message. Schema bảo vệ ý nghĩa payload theo version; converter bảo đảm body thành đúng DTO; header/property cung cấp metadata đúng kiểu để routing; selector được broker thực thi và quyết định consumer/subscription nào nhận message. Kết hợp unit tests với broker integration tests giúp phát hiện sớm các lỗi “send thành công nhưng không ai nhận”, payload parse sai, durable subscription lọc nhầm và poison message lặp vô hạn.
