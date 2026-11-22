# DLQ tăng do converter, schema, quyền truy cập hoặc lỗi nghiệp vụ

> **Chương:** Chẩn đoán sự cố  
> **Phạm vi:** Apache ActiveMQ Classic và Artemis, ứng dụng Java/JMS, Spring JMS và quy trình vận hành DLQ. Bài tập trung tìm nguyên nhân khiến message bị redeliver rồi chuyển vào Dead Letter Queue do **converter, schema, authorization hoặc xử lý nghiệp vụ**; cách phân biệt lỗi thật với lỗi quan sát, khôi phục và replay an toàn.

DLQ tăng là **triệu chứng**, không phải nguyên nhân. Một message vào DLQ thường đã trải qua một hoặc nhiều lần giao lại sau rollback/negative acknowledgement, hoặc được broker/operator chuyển theo chính sách hết hạn hay quarantine. Nếu chỉ tăng consumer concurrency, xóa DLQ hoặc reset redelivery counter, nguyên nhân gốc có thể vẫn tồn tại và message tiếp tục quay lại.

Bốn nhóm lỗi cần được tách ngay từ đầu:

- **Converter:** consumer không giải mã được kiểu message, encoding, JSON/XML, class mapping hoặc payload bytes.
- **Schema:** message giải mã được nhưng thiếu field, sai type/version, enum mới, ràng buộc dữ liệu hoặc contract không tương thích.
- **Quyền truy cập:** principal không có quyền consume/browse/send hoặc không thể gọi downstream destination trong transaction xử lý.
- **Nghiệp vụ:** dữ liệu hợp lệ về cú pháp nhưng vi phạm trạng thái/điều kiện nghiệp vụ, hoặc downstream tạm thời không đáp ứng.

Một khác biệt quan trọng: **consumer không có quyền đọc queue nguồn thường làm backlog tăng ở queue nguồn**, không tự động khiến message vào DLQ. Nếu consumer đã nhận message rồi bị từ chối khi gửi sang queue khác, cập nhật database hoặc commit, listener có thể rollback; các lần redelivery tiếp theo mới dẫn đến DLQ. Vì vậy phải xác định message đã bị broker chuyển DLQ theo policy nào và operation nào thất bại.

## 1. Hiểu đúng DLQ và giới hạn của tín hiệu “DLQ tăng”

**Dead Letter Queue (DLQ)** là nơi broker hoặc ứng dụng cách ly message không thể tiếp tục xử lý theo policy đã cấu hình. Nó giữ lại dữ liệu để điều tra, sửa lỗi và replay có kiểm soát. DLQ không phải một queue retry vô hạn và cũng không mặc nhiên là nơi chứa riêng message lỗi nghiệp vụ.

### 1.1. Những con đường message đi vào DLQ

| Nguyên nhân chuyển | Ví dụ | Cần phân biệt |
|---|---|---|
| **Poison message / hết số lần redelivery** | Converter luôn ném exception, consumer rollback mỗi lần | Cùng message bị thử lại đến ngưỡng cấu hình |
| **Expired message** | JMSExpiration đã qua trước khi consumer nhận | Có thể đi expiry destination hoặc bị loại theo policy; không nhất thiết là poison |
| **Non-persistent / delivery policy** | Message không persistent bị xử lý theo cấu hình riêng | Không giả định mọi loại delivery đều được giữ trong DLQ |
| **Ứng dụng tự quarantine** | Listener chủ động route payload sai schema vào queue cách ly | Phải phân biệt với broker dead-letter forwarding |
| **Operator replay/transfer** | Di chuyển message giữa queue khi xử lý sự cố | DLQ count thay đổi không nhất thiết do lỗi mới |

**DLQ count tăng** chỉ là một chỉ số tổng. Nó không cho biết message từ queue nào, exception nào, có bao nhiêu eventId khác nhau, hay một event đang bị gửi lặp nhiều lần. Cần đo tối thiểu:

- Tốc độ **enqueue vào DLQ** theo thời gian, không chỉ depth hiện tại.
- **Oldest message age** và tổng số message đang chờ.
- Nguồn gốc: original address/queue, destination, consumer/client ID nếu broker có metadata.
- **JMSMessageID, eventId/commandId, JMSRedelivered, JMSXDeliveryCount** khi có.
- Exception class/error code, converter/schema version và release ứng dụng.
- Số business IDs duy nhất so với số delivery attempts.

### 1.2. DLQ tăng khác với queue nguồn tăng

~~~mermaid
flowchart TD
    S["Producer gửi vào queue nguồn"] --> Q["Queue nguồn"]
    Q --> C["Consumer nhận message"]
    C --> X{"Xử lý thành công?"}
    X -->|Có| A["Commit / ACK"]
    X -->|Lỗi tạm thời| R["Rollback / redelivery"]
    R --> Q
    X -->|Lỗi lặp tới ngưỡng| D["Broker dead-letter routing"]
    D --> DLQ["DLQ / quarantine"]
    Q --> B["Consumer không kết nối / không có quyền"]
    B --> G["Backlog ở queue nguồn tăng"]
~~~

Sơ đồ minh họa đường phổ biến. Thực tế có thể có expiry routing, application quarantine và broker-specific policies. **Consumer không được phép consume** thường không lấy message khỏi queue nguồn, do đó queue nguồn tăng. **Consumer có quyền nhận nhưng xử lý thất bại rồi rollback** mới tạo vòng redelivery và có thể đưa message vào DLQ.

### 1.3. Xác định DLQ nào đang tăng

ActiveMQ Classic và Artemis có cách đặt tên/cấu hình khác nhau:

| Broker | Cách tổ chức thường gặp | Dấu hiệu cần đọc |
|---|---|---|
| **ActiveMQ Classic** | Mặc định thường dùng ActiveMQ.DLQ; có thể cấu hình individualDeadLetterStrategy để tạo DLQ.<queue> | Queue name, destination policy, redelivery policy, original-destination metadata |
| **Artemis** | Cấu hình dead-letter-address trong address-setting; queue DLQ phải được provision/routing phù hợp | _AMQ_ORIG_ADDRESS, _AMQ_ORIG_QUEUE, delivery count và address-setting match |
| **Application quarantine** | Queue riêng theo loại lỗi/schema hoặc domain | Header quarantineReason, eventId, app version và audit record |

Không gom tất cả DLQ vào một dashboard nếu mất thông tin nguồn gốc. Ví dụ DLQ.orders.commands và DLQ.billing.commands cần được theo dõi riêng nếu chúng có owner, SLO và quy trình replay khác nhau.

## 2. Quy trình triage trước khi thay đổi broker hoặc replay

Khi DLQ tăng đột ngột, mục tiêu đầu tiên là **giữ lại bằng chứng và khoanh vùng theo message cohort**. Đừng bulk replay trong lúc converter/schema mới vẫn đang lỗi.

### 2.1. Thứ tự xử lý ban đầu

1. Ghi nhận thời điểm bắt đầu tăng DLQ và release/configuration thay đổi gần nhất.
2. Chụp số liệu queue nguồn, DLQ, enqueue/dequeue, in-flight, consumer count, oldest age và store usage.
3. Browse một mẫu message nhỏ ở chế độ read-only; giữ nguyên JMSMessageID, eventId, original destination, delivery count và headers.
4. Gom nhóm theo **exception class + source queue + schemaVersion + producer version**, không chỉ theo timestamp.
5. Đối chiếu log producer, consumer, broker và downstream ở cùng correlation/event ID.
6. Xác định lỗi là deterministic/permanent hay transient trước khi chọn retry.
7. Dừng hoặc giảm tốc producer/consumer có vấn đề khi cần; giữ consumer khỏe tiếp tục xử lý queue không liên quan.
8. Chỉ replay sau khi có bản sửa và test một nhóm nhỏ bằng canary.

### 2.2. Ma trận phân loại nhanh

| Dấu hiệu | Nhóm nghi ngờ | Kiểm tra đầu tiên |
|---|---|---|
| Cùng ClassCastException, MessageFormatException, Jackson mapping error | Converter/message type | JMS body type, content-type, encoding, converter config |
| UnrecognizedProperty, missing required field, invalid enum, schema version unsupported | Schema | Schema registry/contract, producer deployment, version compatibility |
| JMSSecurityException, SecurityException, broker authorization log | Quyền truy cập | Principal thực, operation bị deny, destination/role ACL |
| DB timeout, HTTP 503, lock timeout, rate limit | Lỗi tạm thời ở dependency nghiệp vụ | Timeout, retry budget, circuit breaker, transaction boundary |
| Domain exception như order state conflict, account closed | Nghiệp vụ | Đây là trạng thái hợp lệ cần ghi nhận hay message thực sự không thể xử lý? |
| Queue nguồn tăng nhưng DLQ không tăng | Consumer không nhận, routing sai hoặc throughput thấp | ConsumerCount, credentials, subscription, listener state |
| DLQ tăng sau một đợt deploy | Regression converter/schema/logic/config | So sánh version và payload cohort trước/sau deploy |

### 2.3. Bảo toàn bằng chứng

Với mỗi mẫu message, lưu tối thiểu:

~~~text
broker = artemis-prod-a
sourceAddress = orders
sourceQueue = orders.commands
deadLetterQueue = DLQ
JMSMessageID = ID:...
eventId = evt-...
JMSRedelivered = true
JMSXDeliveryCount = 5
schemaVersion = 3
producerVersion = orders-api-2026.11.17
consumerVersion = orders-worker-2026.11.16
exceptionClass = InvalidOrderStateException
firstSeenAt = ...
lastSeenAt = ...
~~~

Tên trường provider-specific cần lấy từ metadata thật của broker. Đừng tự gán sourceQueue từ tên DLQ nếu một DLQ chứa nhiều nguồn. Với Classic, tên/thuộc tính original destination phụ thuộc chiến lược DLQ và version; với Artemis, có thể đọc các property _AMQ_ORIG_* do broker gắn.

**Không log toàn bộ body mặc định.** Payload có thể chứa token, thông tin cá nhân hoặc dữ liệu thanh toán. Dùng hash, eventId, schema version và một tập field đã allowlist; nếu phải lưu raw payload để điều tra, dùng kho có quyền truy cập, retention và audit riêng.

## 3. Converter lỗi: message đến được consumer nhưng không giải mã được

Converter biến representation của JMS thành object mà ứng dụng xử lý. Converter có thể nằm trong Spring MessageConverter, Jackson, JAXB, serializer riêng hoặc đoạn code đọc BytesMessage. Một lỗi converter thường có tính **deterministic**: cùng bytes + cùng cấu hình sẽ thất bại giống nhau, nên retry message không sửa được nguyên nhân.

### 3.1. Kiểm tra JMS message type trước khi kiểm tra DTO

JMS có các message type khác nhau:

| JMS type | Nội dung | Lỗi thường gặp |
|---|---|---|
| TextMessage | Chuỗi text | JSON/XML sai cú pháp, encoding không đúng, content khác contract |
| BytesMessage | Dãy byte | Đọc sai length/offset, nhầm binary với UTF-8 text |
| MapMessage | Key/value JMS primitive | Consumer mong JSON TextMessage |
| ObjectMessage | Java serialized object | Class không có ở consumer, serialVersionUID mismatch, deserialization policy |
| StreamMessage | Dãy giá trị tuần tự | Đọc sai thứ tự hoặc type |
| Message thuần header/property | Không có body | Consumer ép kiểu body và thất bại |

Không tự động gọi getBody(String.class) cho mọi loại message. Trước khi chuyển DTO, ghi nhận message.getClass(), JMSMessageID, JMSType, content-type property và delivery count. **Đừng deserialize ObjectMessage từ nguồn không tin cậy**; Java native serialization có rủi ro bảo mật và phụ thuộc classpath. Ưu tiên JSON/Avro/Protobuf với schema rõ.

### 3.2. Đọc metadata an toàn bằng Jakarta JMS

Đoạn listener chẩn đoán nhận Message thô để kiểm tra header trước khi converter DTO chạy:

~~~java
package com.example.messaging.diagnostics;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class MessageMetadataProbe {
    @JmsListener(destination = "ops.converter.probe")
    public void inspect(Message message) throws JMSException {
        String messageId = message.getJMSMessageID();
        String type = message.getJMSType();
        boolean redelivered = message.getJMSRedelivered();

        String eventId = message.propertyExists("eventId")
            ? message.getStringProperty("eventId")
            : null;

        String contentType = message.propertyExists("contentType")
            ? message.getStringProperty("contentType")
            : null;

        Integer deliveryCount =
            message.propertyExists("JMSXDeliveryCount")
                ? message.getIntProperty("JMSXDeliveryCount")
                : null;

        System.out.printf(
            "messageId=%s eventId=%s type=%s contentType=%s " +
            "redelivered=%s deliveryCount=%s%n",
            messageId, eventId, type, contentType,
            redelivered, deliveryCount
        );
    }
}
~~~

Đây là probe trong **queue kiểm thử riêng**. Nếu listener container vẫn dùng transacted session, callback trả về bình thường sẽ commit message; không gắn nó vào queue production để “xem thử” vì nó sẽ tiêu thụ message. Để browse không phá hủy, dùng management browse hoặc QueueBrowser read-only phù hợp với broker/client.

Ví dụ dùng jakarta.jms; ActiveMQ Classic client cần bản Jakarta-compatible nếu ứng dụng dùng Spring Framework 6/Spring Boot 3. Với môi trường javax.jms, thay import và dependency tương ứng; không trộn hai namespace trong một classpath.

### 3.3. Lỗi converter Spring/Jackson

Một converter JSON có thể cấu hình rõ target type và mapping type ID:

~~~java
package com.example.messaging.config;

import java.util.Map;

import com.example.orders.events.OrderCreated;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
public class JmsConverterConfiguration {

    @Bean
    MappingJackson2MessageConverter jmsMessageConverter() {
        var converter = new MappingJackson2MessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(
            Map.of("order-created-v1", OrderCreated.class)
        );
        return converter;
    }
}
~~~

Producer phải gửi _type=order-created-v1 theo contract này, hoặc converter phải được cấu hình fallback tương ứng. Không tin một Java class name tùy ý đến từ message rồi load class động. **Type ID nên là tên contract allowlist**, không phải tên class do producer bên ngoài tùy ý điều khiển.

Các nguyên nhân thường gặp:

- Producer gửi BytesMessage nhưng consumer converter chỉ nhận TextMessage.
- contentType/encoding không thống nhất; producer serialize UTF-16 hoặc bytes khác trong khi consumer giả định UTF-8.
- _type thiếu, sai chính tả hoặc không nằm trong type mapping.
- Producer gửi Java class/object mà consumer không có class hoặc không tương thích version.
- Jackson không xử lý được date/time format, number-as-string, enum hoặc polymorphic type.
- Consumer deploy converter mới nhưng producer cũ vẫn gửi contract cũ, hoặc ngược lại.

### 3.4. Cách khoanh vùng converter

1. Lấy một message DLQ và một message còn xử lý thành công từ cùng source queue.
2. So sánh **JMS type**, body length, content-type, encoding, type ID và schema version.
3. Dùng cùng bytes/payload chạy converter test offline, không consume message production.
4. Chạy converter với đúng dependency/classpath của consumer release gây lỗi.
5. Kiểm tra serializer producer: output thực tế có đúng contract không?
6. Xác nhận message cũ trong queue có thể được consumer mới đọc hay không.
7. Sửa converter theo hướng backward-compatible hoặc route payload không hỗ trợ sang quarantine.

Không chỉnh converter production dựa trên một payload đã được copy/format lại, vì việc chuyển đổi có thể làm mất byte encoding hoặc JMS property gây ra lỗi gốc.

## 4. Schema incompatibility: giải mã được nhưng dữ liệu không còn đúng contract

Converter có thể parse JSON thành object nhưng dữ liệu vẫn sai schema. Ví dụ producer thêm field bắt buộc, đổi enum, thay số nguyên thành chuỗi, đổi nullability hoặc nâng version mà consumer chưa hỗ trợ.

### 4.1. Các dạng schema drift

| Thay đổi | Rủi ro với consumer cũ | Cách xử lý |
|---|---|---|
| Thêm optional field có default | Thường tương thích nếu converter bỏ qua field lạ | Test consumer cũ với payload mới |
| Thêm required field không có default | Consumer mới không đọc được payload cũ | Versioning/default migration |
| Đổi amount từ number sang string | Type mismatch hoặc parse sai | Giữ contract cũ hoặc version mới |
| Đổi enum PENDING thành AWAITING_PAYMENT | Enum deserialization có thể fail | Thêm mapping/unknown state có chủ đích |
| Đổi field nullable thành non-null | Payload cũ có null bị reject | Migration hoặc versioned event |
| Đổi semantics mà giữ tên field | Parse thành công nhưng business logic sai | Tạo event type/version mới |
| Đổi timezone/date format | Parse lỗi hoặc thời gian lệch | Chuẩn hóa ISO-8601 và test boundary |

**Schema tương thích cú pháp không đồng nghĩa tương thích nghiệp vụ.** Ví dụ amount vẫn là decimal nhưng chuyển từ đơn vị đồng sang đơn vị xu thì JSON parse thành công nhưng business effect sai nghiêm trọng.

### 4.2. Envelope có schemaVersion

~~~json
{
  "eventId": "evt-2026-9001",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "occurredAt": "2026-11-17T10:00:00Z",
  "payload": {
    "orderId": "order-9001",
    "currency": "VND",
    "totalMinor": 1250000
  }
}
~~~

Consumer phải kiểm tra eventType và schemaVersion trước khi áp business rule. Đừng dựa vào việc Jackson bỏ qua field lạ rồi coi payload hợp lệ. Nếu version chưa hỗ trợ, trả lỗi phân loại rõ để đưa vào **quarantine/compatibility queue** hoặc DLQ theo policy; retry vô hạn không làm consumer cũ hiểu schema mới.

### 4.3. Validation tách khỏi deserialization

~~~java
public record OrderCreated(
    String orderId,
    String currency,
    Long totalMinor
) {
    public void validate() {
        if (orderId == null || orderId.isBlank()) {
            throw new InvalidEventException("orderId is required");
        }
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new InvalidEventException("currency must be ISO code");
        }
        if (totalMinor == null || totalMinor < 0) {
            throw new InvalidEventException("totalMinor is invalid");
        }
    }
}
~~~

JSON có thể deserialize thành record nhưng orderId rỗng, currency có khoảng trắng hoặc totalMinor âm vẫn không hợp lệ. Gọi validation **trước side effect** và phân loại lỗi. Nếu schema validation fail, không ghi inbox marker như thể đã xử lý thành công.

### 4.4. Schema compatibility test trong CI

Mỗi thay đổi producer/consumer nên có test matrix:

| Producer payload | Consumer hiện tại | Kết quả cần đạt |
|---|---|---|
| Payload version hiện hành | Consumer version hiện hành | PASS |
| Payload version trước | Consumer mới | PASS nếu cam kết backward compatibility |
| Payload version mới | Consumer cũ | PASS chỉ khi cam kết forward compatibility; nếu không, fail rõ/quarantine |
| Field optional vắng mặt | Consumer mới | Default hợp lệ |
| Enum chưa biết | Consumer mới | Unknown-value policy rõ, không crash loop |
| Payload sai type/required field | Mọi consumer | Permanent validation failure có phân loại |

Nếu dùng schema registry, kiểm tra **compatibility mode** ở registry và test serializer/deserializer với schema thật. Registry chấp nhận schema mới không chứng minh mọi consumer đang triển khai đều tương thích.


## 5. Cấu hình dead-letter và redelivery đúng theo broker

Trước khi điều chỉnh retry, xác định broker đang chạy là **Classic hay Artemis**, version, loại destination và policy thực tế đang match. Cùng khái niệm DLQ nhưng file cấu hình, wildcard, metadata và cách đặt tên khác nhau.

### 5.1. ActiveMQ Classic: redelivery policy và individual DLQ

Classic thường dùng **client redelivery policy** để điều khiển delay/số lần giao lại. Khi transacted session rollback hoặc client recover theo cơ chế phù hợp, client/broker thực hiện redelivery. Khi vượt ngưỡng, client gửi poison acknowledgement để broker áp dead-letter strategy.

Ví dụ cấu hình policy cho một queue trong file activemq.xml của Classic:

Đây là fragment cấu hình broker; giữ nguyên các phần tử persistence, transport và plugin đang có trong file thực tế.

~~~xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="orders-classic"
        persistent="true">

    <destinationPolicy>
        <policyMap>
            <policyEntries>
                <policyEntry queue="orders.commands">
                    <deadLetterStrategy>
                        <individualDeadLetterStrategy
                            queuePrefix="DLQ."
                            useQueueForQueueMessages="true"
                            processExpired="false"
                            processNonPersistent="false"/>
                    </deadLetterStrategy>
                </policyEntry>
            </policyEntries>
        </policyMap>
    </destinationPolicy>

    <!-- persistenceAdapter, transportConnectors và phần khác -->
</broker>
~~~

Với policy trên, poison message của queue nguồn có thể được chuyển vào **DLQ.orders.commands**. Hai lựa chọn được cố ý nêu rõ:

- **processExpired=false:** message hết hạn không đi vào poison-message DLQ theo strategy này; nếu cần giữ expired messages, cấu hình/quan sát riêng.
- **processNonPersistent=false:** message non-persistent không được strategy này lưu vào DLQ. Nếu yêu cầu điều tra cả loại này, phải cân nhắc true và dung lượng lưu trữ.

Policy entry ở ví dụ chỉ match queue cụ thể. Nếu áp wildcard, hãy kiểm tra precedence của destination policy để không vô tình thay đổi mọi queue/topic. Classic có default shared DLQ **ActiveMQ.DLQ** khi không dùng individual strategy; tên DLQ thực tế phải được đọc từ cấu hình và broker, không đoán.

Ví dụ Java cấu hình redelivery cho Classic client:

~~~java
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.RedeliveryPolicy;

ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("tcp://broker-a:61616");

RedeliveryPolicy policy = factory.getRedeliveryPolicy();
policy.setInitialRedeliveryDelay(1_000L);
policy.setUseExponentialBackOff(true);
policy.setBackOffMultiplier(2.0);
policy.setMaximumRedeliveries(5);
~~~

Giá trị ở đây là ví dụ cho client đang dùng factory đó. Kiểm tra factory thực sự được inject vào listener container, vì một factory khác có thể vẫn dùng policy cũ. **maximumRedeliveries** là số lần redelivery theo semantics của Classic client, không phải số lần business retry do ứng dụng tự đếm. Khi vượt ngưỡng, broker mới áp dead-letter handling; kiểm tra log và DLQ thay vì chỉ tin config đã được load.

### 5.2. Artemis: dead-letter-address và max-delivery-attempts

Artemis đặt retry/DLQ trong **address-settings**. Ví dụ dưới đây giới hạn policy cho addresses bắt đầu bằng orders:

Hai fragment address-settings và addresses phải nằm trong phần core của broker.xml Artemis, không phải file XML độc lập.

~~~xml
<address-settings>
    <address-setting match="orders.#">
        <dead-letter-address>DLQ</dead-letter-address>
        <max-delivery-attempts>5</max-delivery-attempts>
        <redelivery-delay>1000</redelivery-delay>
        <redelivery-delay-multiplier>2.0</redelivery-delay-multiplier>
        <max-redelivery-delay>30000</max-redelivery-delay>
    </address-setting>
</address-settings>

<addresses>
    <address name="DLQ">
        <anycast>
            <queue name="DLQ"/>
        </anycast>
    </address>
</addresses>
~~~

Ý nghĩa:

- **dead-letter-address:** address đích cho message vượt quá delivery attempts.
- **max-delivery-attempts:** ngưỡng giao lại; chọn số hữu hạn để poison message không chiếm consumer vô thời hạn.
- **redelivery-delay:** khoảng chờ ban đầu trước khi giao lại.
- **redelivery-delay-multiplier / max-redelivery-delay:** backoff tăng dần và trần thời gian chờ.
- **DLQ address/queue:** phải được provision với routing type phù hợp. Ví dụ trên dùng anycast queue tên DLQ.

Không so sánh số 5 của Classic maximumRedeliveries với số 5 của Artemis max-delivery-attempts như cùng một phép đếm. Classic client policy nói về số lần redelivery sau lần giao đầu; Artemis setting giới hạn delivery attempts theo semantics của broker. Hãy đo lần giao đầu và các lần giao lại trên đúng version khi xác nhận ngưỡng thực tế.

Wildcard Artemis dùng dấu chấm làm separator; ký tự **#** match nhiều segments và ký tự sao **(*)** match một segment. Kiểm tra đúng address mà queue đang bind vào, không chỉ queue name. Một address-setting rộng hơn hoặc cụ thể hơn có thể làm policy khác được áp dụng. Đọc effective configuration và management metrics của broker đang chạy.

### 5.3. Đừng tăng max-delivery-attempts để che lỗi deterministic

Nếu converter luôn fail vì message là BytesMessage nhưng consumer chỉ nhận TextMessage, tăng retry từ 5 lên 50 chỉ làm tăng latency và CPU/log. Nếu dependency tạm unavailable, retry với backoff có thể hợp lý. Cần phân loại lỗi trước khi chọn:

- **Transient:** broker/downstream tạm thời, timeout, deadlock/serialization contention có khả năng hết; retry hữu hạn với backoff.
- **Permanent:** schema không hỗ trợ, payload malformed, quyền cấu hình sai, trạng thái không thể xử lý; quarantine/DLQ sau ít lần thử hoặc chuyển nhánh xử lý rõ.
- **Business rejection hợp lệ:** ví dụ thanh toán bị từ chối hoặc đơn đã hủy; ghi kết quả terminal theo domain rồi ACK, không coi là poison message.

## 6. Quyền truy cập: phân biệt lỗi consume với lỗi trong lúc xử lý

Authorization có thể ảnh hưởng ở nhiều điểm: mở connection, subscribe/consume queue nguồn, browse message, send sang destination tiếp theo, quản lý DLQ hoặc replay. Cần biết **principal nào thực hiện operation nào trên destination nào**.

### 6.1. Bảng triệu chứng theo operation

| Operation bị deny | Triệu chứng thường thấy | Message nằm ở đâu? |
|---|---|---|
| Connect/authenticate | JMS connection không mở được | Thường vẫn ở queue nguồn |
| Consume/read queue nguồn | Consumer không nhận được message | Backlog ở queue nguồn tăng |
| Browse DLQ | Operator không xem được message | Message vẫn nằm trong DLQ |
| Send tới downstream queue trong listener transaction | Listener ném security exception/rollback | Message nguồn redeliver; có thể vào DLQ sau ngưỡng |
| Consume/replay từ DLQ | Không thể khôi phục message | Message tiếp tục nằm ở DLQ |
| Create queue/address động | Consumer không thể provision destination | Có thể không có queue/subscription để nhận; không mặc nhiên là DLQ |

**Authorization fail không đồng nghĩa dead-letter.** Nếu broker từ chối consume trước khi dispatch, message chưa rời source queue. Nếu application đã nhận message rồi thao tác send downstream bị deny và listener rollback, message có thể redeliver đến giới hạn rồi dead-letter. Phân biệt hai tình huống bằng broker security log, consumer logs và queue counters.

### 6.2. ActiveMQ Classic authorization entries

Một ví dụ ý tưởng về quyền theo queue trong Classic:

Đây là fragment bên trong cấu hình plugin/authorization của broker; group names phải khớp với nhóm mà authentication plugin cấp cho principal.

~~~xml
<authorizationPlugin>
    <map>
        <authorizationMap>
            <authorizationEntries>
                <authorizationEntry
                    queue="orders.commands"
                    read="orders-consumer"
                    write="orders-producer"
                    admin="broker-admin"/>

                <authorizationEntry
                    queue="DLQ.orders.commands"
                    read="dlq-operator"
                    write="broker-admin"
                    admin="broker-admin"/>
            </authorizationEntries>
        </authorizationMap>
    </map>
</authorizationPlugin>
~~~

Các giá trị read/write/admin là **group names** đã được authentication plugin ánh xạ từ user. Không đặt password vào đoạn ACL và không cấp broker-admin cho consumer chỉ để hết lỗi. Nếu dùng shared DLQ hoặc wildcard destination, phải bổ sung policy match tương ứng; rule cụ thể trên không tự cấp quyền cho mọi DLQ.

### 6.3. Artemis security-settings

Ví dụ phân quyền riêng cho source address và DLQ:

Đây là fragment security-settings trong cấu hình core Artemis. Các role phải được khai báo trong security domain đang dùng.

~~~xml
<security-settings>
    <security-setting match="orders.#">
        <permission type="consume" roles="orders-consumer"/>
        <permission type="send" roles="orders-producer"/>
        <permission type="browse" roles="orders-ops"/>
    </security-setting>

    <security-setting match="DLQ">
        <permission type="consume" roles="dlq-operator"/>
        <permission type="browse" roles="dlq-operator"/>
        <permission type="send" roles="dlq-replay"/>
    </security-setting>
</security-settings>
~~~

Ví dụ chỉ minh họa quyền client trên addresses tương ứng; tên role phải tồn tại trong security domain của broker. Trong môi trường production, tách **producer, consumer, operator và replay identity**. Không cấp role manage cho DLQ reader. Nếu broker tự route message theo dead-letter-address, không yêu cầu application consumer quyền admin để broker thực hiện routing nội bộ; hãy kiểm tra broker logs và ACL theo operation thực tế.

### 6.4. Chẩn đoán security exception

1. Lấy full exception chain và broker-side authorization log cùng timestamp.
2. Xác nhận user/role thực của JMS connection, không chỉ tên service trong Kubernetes.
3. Xác định operation bị deny: consume, browse, send, create hay manage.
4. Ghi destination/address chính xác, kể cả prefix/vhost/tenant.
5. Kiểm tra wildcard ACL và precedence.
6. Thử bằng đúng principal trong môi trường test; không thử bằng admin rồi kết luận quyền consumer đúng.
7. Sau khi sửa ACL, kiểm tra message source queue có được consume và downstream send có commit không.

Nếu operator không browse được DLQ, tạo quyền browse read-only tạm thời cho nhóm trực ca theo audit. Không di chuyển message bằng tài khoản ứng dụng consumer để tránh mở rộng quyền production.

## 7. Lỗi nghiệp vụ: phân loại transient, permanent và kết quả hợp lệ

Không phải mọi exception từ business handler đều là poison message. Một payment bị decline có thể là **kết quả nghiệp vụ hợp lệ**. Một DB timeout có thể là transient. Một event trỏ tới order không tồn tại có thể là message đến sai thứ tự, dữ liệu bị thiếu hoặc producer bug; cần domain policy trước khi retry/reject.

### 7.1. Bảng phân loại

| Nhóm | Ví dụ | Hành động |
|---|---|---|
| **Transient dependency** | DB unavailable, HTTP 503, lock timeout, rate limit | Rollback/retry hữu hạn, backoff, circuit breaker |
| **Permanent payload** | Thiếu orderId, amount âm, schema version không hỗ trợ | Quarantine/DLQ với reason rõ, không retry vô hạn |
| **Business terminal rejection** | Payment declined, order canceled, duplicate command đã hoàn tất | Ghi terminal outcome/idempotency rồi ACK |
| **Business state conflict có thể phục hồi** | Event version 8 đến trước version 7 | Retry có giới hạn hoặc hold theo aggregate ordering |
| **Programming defect** | NullPointerException, mapping bug sau deploy | Dừng rollout/rollback, giới hạn retry, giữ message để replay sau fix |
| **Security/configuration defect** | Consumer không có quyền send downstream | Sửa ACL/config, kiểm tra redelivery và replay sau fix |

### 7.2. Không rollback một kết quả decline hợp lệ

Ví dụ:

~~~java
public ProcessResult handlePayment(PaymentRequested event) {
    PaymentResult result = paymentGateway.authorize(
        event.paymentAttemptId(),
        event.amount()
    );

    if (result == PaymentResult.DECLINED) {
        paymentRepository.markDeclined(
            event.paymentAttemptId(), result.reason());
        return ProcessResult.TERMINAL_REJECTION;
    }

    paymentRepository.markAuthorized(event.paymentAttemptId());
    return ProcessResult.APPLIED;
}
~~~

Nếu DECLINED là kết quả domain cuối, listener nên commit DB outcome và JMS receive. Ném exception rồi rollback chỉ khiến cùng một khoản thanh toán bị thử lại, dù provider đã trả lời decline. Đối với timeout không rõ kết quả, cần idempotency key của provider và reconciliation; không suy ra decline hay success chỉ từ timeout.

### 7.3. Không ACK message khi side effect chưa được lưu

Một lỗi nguy hiểm là catch mọi exception rồi log, sau đó return bình thường:

~~~java
@JmsListener(destination = "orders.commands")
public void onMessage(OrderCommand command) {
    try {
        orderService.apply(command);
    } catch (Exception error) {
        log.error("Processing failed", error);
        // Sai nếu listener container sẽ ACK khi method return.
    }
}
~~~

Nếu listener container commit session khi callback return, message biến mất khỏi queue dù business transaction rollback hoặc chưa được lưu. Chỉ ACK khi:

- Business update đã commit và inbox/idempotency marker cùng commit.
- Hoặc lỗi đã được chuyển bền vững sang quarantine/DLQ theo transaction/contract đã định nghĩa.
- Hoặc domain đã ghi một terminal rejection hợp lệ.

Với lỗi transient, ném exception để transacted listener rollback; cấu hình redelivery hữu hạn ở broker/client. Với lỗi permanent, chuyển vào quarantine bằng quy trình rõ và giữ event ID/original metadata.

### 7.4. External API có kết quả không rõ

Nếu consumer gọi payment provider rồi timeout, provider có thể đã charge nhưng response bị mất. Rollback JMS và gọi lại API bằng request mới có thể charge hai lần. Dùng cùng **paymentAttemptId/idempotency key** ở mọi retry; nếu provider không hỗ trợ idempotency, phải tra soát theo merchant reference trước khi gửi lại.

Inbox bảo vệ database update, nhưng không tạo transaction nguyên tử với HTTP API. Với side effect ngoài database, cần **downstream idempotency, saga/compensation hoặc reconciliation** tùy domain.

## 8. Phân biệt lỗi xảy ra trước và sau khi listener nhận message

Converter, listener adapter và business handler nằm ở các tầng khác nhau. Nếu không biết exception phát sinh ở đâu, việc thêm try/catch trong business method có thể không bao giờ bắt được lỗi.

~~~mermaid
flowchart TD
    B["Broker dispatch JMS Message"] --> H["JMS headers / body"]
    H --> CV["Spring/JMS converter"]
    CV -->|Fail| CE["Conversion exception"]
    CV -->|Success| DTO["DTO / schema validation"]
    DTO -->|Fail| SE["Schema validation error"]
    DTO -->|Pass| L["Business listener"]
    L -->|Dependency error| TE["Transient failure"]
    L -->|Domain terminal result| OK["Persist outcome + ACK"]
    L -->|Permanent domain error| PE["Quarantine / DLQ"]
    CE --> RB["Rollback / bounded redelivery"]
    SE --> RB
    TE --> RB
~~~

- **Converter fail:** listener method có thể chưa được gọi; error đi qua listener adapter/container.
- **Schema validation fail:** converter đã tạo object, nhưng validation từ chối payload.
- **Business fail:** listener đã nhận object và bắt đầu xử lý.
- **Terminal business result:** không phải exception; lưu kết quả rồi commit.
- **Quarantine:** nếu ứng dụng chủ động chuyển message, phải bảo đảm thao tác lưu quarantine thành công trước khi ACK source.

Để kiểm soát conversion error, có thể nhận JMS Message thô rồi tự parse trong listener, hoặc cấu hình error handler/container phù hợp. Cách nhận raw message cho phép phân loại body type và route payload lỗi; đổi lại ứng dụng phải tự quản lý parsing, validation và error semantics.

### 8.1. Raw-message listener để phân loại converter error

Ví dụ minh họa xử lý TextMessage trước khi gọi Jackson; chỉ dùng trong queue test hoặc listener production đã có policy quarantine rõ:

~~~java
package com.example.orders.messaging;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class RawOrderListener {
    private final ObjectMapper mapper;
    private final OrderHandler handler;

    public RawOrderListener(ObjectMapper mapper, OrderHandler handler) {
        this.mapper = mapper;
        this.handler = handler;
    }

    @JmsListener(
        destination = "orders.commands.raw",
        containerFactory = "transactedJmsListenerContainerFactory"
    )
    public void onMessage(Message message) throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new UnsupportedMessageTypeException(
                message.getClass().getName());
        }

        final OrderCommand command;
        try {
            command = mapper.readValue(
                textMessage.getText(), OrderCommand.class);
        } catch (Exception conversionFailure) {
            throw new InvalidPayloadException(
                "Cannot decode orders.commands.raw",
                conversionFailure);
        }

        command.validate();
        handler.apply(command);
    }
}
~~~

Trong ví dụ, UnsupportedMessageTypeException và InvalidPayloadException là exception do ứng dụng định nghĩa, kế thừa RuntimeException; OrderCommand và OrderHandler là domain types. InvalidEventException trong ví dụ validation ở mục 4 cũng là exception của domain. Khi đưa vào codebase, khai báo chúng rõ ràng và phân loại retryable/permanent trong error policy.

Ở đây exception được ném ra để container rollback; sau ngưỡng retry, broker policy chuyển message vào DLQ. Trong production, có thể thay cách đó bằng quarantine sớm cho lỗi permanent, nhưng phải có một transaction đảm bảo **quarantine send + source receive commit** hoặc cơ chế outbox tương đương. Không catch conversion exception rồi return, vì sẽ ACK và mất message lỗi.




## 9. Đọc DLQ và metrics để xác định cohort lỗi

Đừng browse toàn bộ DLQ qua một consumer nghiệp vụ. Công cụ điều tra cần **read-only browse**, giới hạn số message và hiển thị metadata trước body. Nếu broker management API hỗ trợ browse, dùng quyền chỉ đọc; nếu dùng JMS QueueBrowser, đóng browser/session/connection và không gọi receive.

### 9.1. Metadata cần thu thập

| Field | Mục đích |
|---|---|
| JMSMessageID | Định danh message instance theo provider |
| eventId / commandId | Gom các delivery/replay của cùng sự kiện logic |
| Redelivered flag | Cho biết provider đánh dấu message đã được giao trước đó |
| JMSXDeliveryCount | Delivery count khi provider hỗ trợ |
| JMSType / contentType / schemaVersion | Phân tích converter và contract |
| Original destination/address/queue | Xác định source trước khi dead-letter |
| Timestamp/expiration | Phát hiện message cũ hoặc hết hạn |
| Producer/application version | Tìm cohort phát sinh sau deploy |
| Failure reason/error class | Phân nhóm lỗi theo nguyên nhân |

JMSXDeliveryCount là property chuẩn khi provider hỗ trợ JMSX; kiểm tra propertyExists trước khi đọc và không dùng nó làm event ID. Redelivered flag là boolean, không thay thế delivery count. Metadata gốc do broker thêm là provider-specific; Artemis thường có _AMQ_ORIG_ADDRESS, _AMQ_ORIG_QUEUE và _AMQ_ORIG_MESSAGE_ID. Classic có metadata original destination/transaction/message ID theo strategy/version. Xác minh bằng một message thật của broker đang chạy.

### 9.2. Metrics tối thiểu

Các metric dưới đây là metric ứng dụng/exporter tự định nghĩa; tên không phải API thống nhất mặc định của Classic và Artemis.

| Metric | Loại | Ý nghĩa |
|---|---|---|
| messaging_dlq_depth | Gauge theo broker/DLQ | Message hiện còn trong DLQ |
| messaging_dlq_enqueue_total | Counter theo source/reason | Tốc độ message mới vào DLQ |
| messaging_dlq_oldest_age_seconds | Gauge | Tuổi message lâu nhất |
| messaging_redelivery_total | Counter theo consumer/source | Số lần redelivery quan sát được |
| messaging_consumer_failure_total | Counter theo exception class | Nhóm lỗi consumer |
| messaging_converter_failure_total | Counter theo message type | Lỗi giải mã |
| messaging_schema_rejection_total | Counter theo schema version | Payload bị reject |
| messaging_authorization_failure_total | Counter theo operation | Quyền bị từ chối |
| messaging_business_retry_total | Counter theo error class | Retry do dependency/domain |
| messaging_quarantine_total | Counter theo reason | Số message chủ động cách ly |
| messaging_replay_total | Counter theo source/replay batch | Theo dõi redrive có kiểm soát |

Không gắn eventId, orderId, customerId hoặc JMSMessageID làm Prometheus label vì cardinality tăng không giới hạn và có thể lộ dữ liệu. ID chi tiết nên ở log/trace có access control; metric chỉ dùng source queue, event type đã giới hạn, version, error class và broker.

### 9.3. PromQL cho DLQ tăng

~~~promql
# Tốc độ message mới đi vào DLQ trong 5 phút.
sum by (broker, dlq, source_queue, reason) (
  rate(messaging_dlq_enqueue_total[5m])
)

# DLQ nào đang có message cũ nhất.
max by (broker, dlq) (
  messaging_dlq_oldest_age_seconds
)

# Tỷ lệ lỗi converter theo consumer.
sum by (consumer) (
  rate(messaging_converter_failure_total[5m])
)

# Authorization failure theo operation.
sum by (broker, operation) (
  rate(messaging_authorization_failure_total[5m])
)
~~~

Alert nên dựa trên **tốc độ tăng và tuổi message**, không chỉ depth tuyệt đối. DLQ depth 100 có thể là bình thường nếu là queue quarantine lâu dài; tăng từ 0 lên 100 trong hai phút sau deploy có thể là incident. Thêm điều kiện theo source_queue/reason để đội chịu trách nhiệm nhận đúng cảnh báo.

## 10. Khôi phục và replay an toàn

DLQ là nơi giữ bằng chứng, không phải nơi để bấm “redrive all” ngay khi thấy queue tăng. Trước replay, cần trả lời ba câu hỏi:

1. **Nguyên nhân đã được sửa chưa?** Converter/schema/ACL/business handler mới đã được test với payload thật chưa?
2. **Message còn hợp lệ về nghiệp vụ không?** Order/payment có thể đã được xử lý qua một con đường khác hoặc đã hết hạn.
3. **Replay có thể tạo side effect trùng không?** Consumer có inbox/idempotency và downstream idempotency key chưa?

### 10.1. Quy trình replay theo cohort

1. Chụp metadata, event IDs, source queue, failure reason và timestamp trước khi di chuyển.
2. Chọn cohort nhỏ theo cùng lỗi/version; không gom message từ nhiều source queues nếu owner khác nhau.
3. Sửa và triển khai consumer/converter/ACL; chạy integration test bằng payload đại diện.
4. Replay một batch canary nhỏ vào destination đã kiểm soát.
5. Theo dõi redelivery, DLQ enqueue rate, consumer failure, business outcome và duplicate-suppressed count.
6. Nếu canary ổn, tăng batch theo rate limit; nếu lỗi lặp, dừng replay và giữ nguyên cohort còn lại.
7. Đối soát eventId/business IDs với database và downstream trước khi đóng incident.
8. Ghi audit: ai replay, lúc nào, từ queue nào, sang đâu, bao nhiêu message và kết quả.

### 10.2. Giữ nguyên eventId khi replay cùng sự kiện

Replay cùng một business event phải giữ **eventId/commandId ban đầu**. Nếu tạo eventId mới, inbox không nhận ra message đã được xử lý trước đó và có thể thực hiện side effect lần nữa.

Nếu nghiệp vụ cần một hành động mới (ví dụ hoàn tiền sau payment cũ), đó là **command/event mới** có ID mới và correlation/causation ID trỏ về event gốc. Không sửa payload dưới eventId cũ rồi replay; payload khác cùng ID là identity conflict.

### 10.3. Quarantine theo reason

Với hệ thống có nhiều nhóm lỗi, có thể tách destination theo owner/purpose:

~~~text
DLQ.orders.converter
DLQ.orders.schema
DLQ.orders.business
DLQ.billing.authorization
DLQ.billing.business
~~~

Đây là naming convention ở tầng vận hành, không phải queue broker tự tạo mặc định. Nếu vẫn dùng một DLQ chung, gắn metadata có kiểm soát như:

~~~text
quarantineReason = SCHEMA_VERSION_UNSUPPORTED
sourceAddress = orders
sourceQueue = orders.commands
consumerName = orders-worker-v2
failureClass = UnsupportedSchemaVersion
failureAt = 2026-11-17T10:15:00Z
eventId = evt-...
~~~

Các property này do application quarantine handler thêm; không ghi đè JMS reserved properties hoặc metadata broker. Nếu broker dead-letter forwarding tự động trước khi application gắn reason, dùng original destination + delivery count + consumer/broker logs để phân loại, hoặc xây bước enrich sau đó có audit.

### 10.4. Không replay vào queue nguồn trước khi bảo đảm idempotency

Khi replay trực tiếp về source queue, consumer production có thể nhận message ngay lập tức. Nếu chưa kiểm chứng inbox retention, event ID hoặc side effect ngoài, rủi ro duplicate rất cao. Có thể dùng replay queue/canary consumer riêng để xác minh payload trước, nhưng sau đó vẫn phải kiểm tra destination cuối và thứ tự aggregate.

**Không purge DLQ sau khi replay** cho tới khi đã xác nhận kết quả. Giữ audit record hoặc bản lưu phù hợp retention; xóa bằng chứng sớm làm mất khả năng đối soát.


## 11. Kiểm thử nguyên nhân và chính sách DLQ

Một bài test DLQ có giá trị phải chứng minh **message được xử lý đúng theo từng loại lỗi**, không chỉ assert queue depth tăng.

### 11.1. Test matrix

| Test | Tạo lỗi có kiểm soát | Kết quả mong đợi |
|---|---|---|
| Converter type mismatch | Gửi BytesMessage vào consumer chỉ nhận TextMessage | Lỗi được phân loại; rollback/redelivery hữu hạn hoặc quarantine |
| Invalid JSON | Gửi text JSON malformed | Không ACK mất message; sau policy vào DLQ |
| Unsupported schema version | Gửi version chưa hỗ trợ | Permanent rejection/quarantine; không retry vô hạn |
| Missing required field | Bỏ orderId hoặc amount | Validation fail trước side effect |
| Consumer không có quyền consume | Thu hồi consume ACL ở sandbox | Source queue backlog tăng, không mặc định message vào DLQ |
| Downstream send bị deny | Consumer nhận message nhưng không được send queue tiếp theo | Transaction rollback; redelivery rồi DLQ nếu không sửa ACL |
| Transient DB outage | Làm DB unavailable ngắn | Retry/backoff; khi DB phục hồi message xử lý thành công |
| Permanent business invalid | Gửi command sai trạng thái | Quarantine hoặc terminal rejection theo domain contract |
| Max attempts exceeded | Cho listener rollback có chủ đích | Message vào DLQ theo policy thực tế |
| Expired message | Đặt TTL ngắn và ngừng consumer | Xác minh expiry policy riêng, không nhầm poison DLQ |
| Replay duplicate | Replay event đã có inbox marker | Không lặp business effect |
| DLQ permission | Thu hồi browse/read quyền operator | Operator bị từ chối; message vẫn ở DLQ |

### 11.2. Kiểm thử converter với payload cố định

Lưu fixture ở dạng bytes gốc cùng metadata cần thiết: message type, encoding, content-type, type ID, schema version. Chạy converter test offline với cùng thư viện/version của consumer. Không chỉ dùng một JSON đã format lại từ log, vì log có thể đã thay encoding, escape hoặc bỏ JMS properties.

### 11.3. Kiểm thử redelivery và max attempts

Trong broker sandbox:

1. Tạo queue test với max attempts nhỏ, ví dụ 3–5.
2. Gửi message persistent có eventId duy nhất.
3. Consumer transacted cố ý rollback với một exception đã định.
4. Ghi nhận delivery count và delay giữa các lần nhận.
5. Xác minh message cuối cùng vào đúng DLQ đã cấu hình.
6. Sửa handler, replay một bản và xác nhận xử lý thành công.
7. Kiểm tra message gốc không bị duplicate side effect.

Không assert chính xác số lần callback bằng giá trị config mà không tính lần delivery đầu tiên, semantics của client và version. Ghi nhận behavior thực tế bằng delivery count/log của broker.

### 11.4. Kiểm thử security đúng principal

Không chạy test authorization bằng admin. Dùng đúng user/role của producer, consumer, operator và replay tool:

- Consumer chỉ có quyền consume trên source queue.
- Operator chỉ browse/read DLQ theo quyền được duyệt.
- Replay principal chỉ send vào destination được phép.
- Consumer workflow cần send downstream phải có đúng send permission ở queue đích.
- User không được phép phải bị deny và message state được quan sát đúng.

## 12. Runbook theo từng nhóm nguyên nhân

### 12.1. Converter/schema failure sau deploy

1. Khoanh thời điểm bắt đầu DLQ tăng và consumer/producer release.
2. Chọn 3–5 message đại diện cùng source queue, giữ nguyên bytes/headers.
3. So sánh message type, content-type, encoding, type ID và schema version.
4. Chạy converter/validation test bằng đúng artifact đang triển khai.
5. Rollback consumer hoặc triển khai converter tương thích nếu có regression.
6. Với payload version không hỗ trợ, route quarantine có reason; không retry vô hạn.
7. Chạy canary replay và theo dõi DLQ enqueue rate trước khi replay rộng.

### 12.2. Authorization failure

1. Lấy broker-side denial log và exception từ client.
2. Xác định operation và destination bị từ chối.
3. Xác minh principal/role thực và wildcard precedence.
4. Cấp đúng quyền hẹp cho operation đó; không cấp admin toàn broker.
5. Kiểm tra source queue backlog và consumer reconnect.
6. Nếu message đã bị redeliver/DLQ do downstream send deny, replay cohort sau khi ACL được sửa.
7. Đối soát các side effect đã commit trước lần rollback.

### 12.3. Business dependency hoặc logic failure

1. Phân loại transient hay permanent.
2. Với transient, kiểm tra timeout, circuit breaker, retry/backoff và dependency health.
3. Với terminal business rejection, ghi outcome rồi ACK.
4. Với permanent invalid state, quarantine có eventId và domain reason.
5. Với timeout external API không rõ kết quả, tra soát theo idempotency key trước retry.
6. Sau khi phục hồi, replay có rate limit và inbox/idempotency.
7. Đóng incident khi business outcomes và DLQ cohort đã được đối soát, không chỉ khi DLQ depth về 0.

### 12.4. Kiểm tra nhanh trước khi tuyên bố đã phục hồi

- DLQ enqueue rate đã về baseline chưa?
- Source queue có consumer hợp lệ và backlog đang giảm không?
- Oldest message age có nằm trong SLO không?
- Converter/schema error rate đã giảm chưa?
- Authorization denied có còn trong broker logs không?
- Business terminal outcomes có tăng tương ứng với accepted work không?
- Replay batch có duplicate suppression hoặc side effect lặp không?
- DLQ còn message chưa phân loại hoặc chưa có owner không?

## 13. Bài lab thực hành

### Lab A — Converter không tương thích JMS type

1. Gửi một BytesMessage vào queue test.
2. Chạy consumer chỉ nhận TextMessage trong transacted session.
3. Quan sát exception, redelivery count và source queue.
4. Để message vượt max attempts trong sandbox.
5. Browse DLQ và xác minh metadata nguồn.
6. Sửa consumer đọc đúng BytesMessage hoặc chuẩn hóa contract; replay một eventId.

**Đạt:** chỉ ra converter failure khác với broker connectivity; không ACK message do ép kiểu sai.

### Lab B — Schema version không được hỗ trợ

1. Producer gửi schemaVersion mới hơn consumer.
2. Consumer parse envelope nhưng reject version.
3. Kiểm tra policy quarantine/permanent error.
4. Triển khai consumer hỗ trợ version đó trong test.
5. Replay cùng eventId và xác nhận outcome.

**Đạt:** phân biệt parse thành công với schema/business contract hợp lệ.

### Lab C — Consumer thiếu quyền consume

1. Tạo user consumer chỉ có quyền trên queue khác.
2. Gửi message vào source queue.
3. Thử kết nối/consume bằng đúng user.
4. Quan sát source queue backlog tăng và DLQ không nhất thiết tăng.
5. Cấp quyền consume đúng queue rồi xác nhận message được xử lý.

**Đạt:** không kết luận mọi authorization failure đều dead-letter.

### Lab D — Downstream send bị deny

1. Consumer nhận message từ source queue trong transacted session.
2. Thu hồi send permission tới downstream queue trong sandbox.
3. Handler nhận message nhưng send downstream bị deny; transaction rollback.
4. Quan sát redelivery và DLQ khi vượt ngưỡng.
5. Sửa ACL, replay message và đối soát side effect.

**Đạt:** nhận diện authorization error xảy ra sau receive có thể dẫn tới DLQ.

### Lab E — Lỗi nghiệp vụ transient và permanent

1. Tạo một dependency trả HTTP 503 tạm thời.
2. Consumer rollback với retry/backoff; khôi phục dependency.
3. Xác nhận message xử lý thành công trước max attempts.
4. Gửi một payload vi phạm business invariant vĩnh viễn.
5. Chuyển payload đó vào quarantine/terminal rejection theo policy.
6. Kiểm tra không retry vô hạn.

**Đạt:** retry transient và cách ly permanent đúng mục đích.

### Lab F — Replay không lặp side effect

1. Xử lý một eventId thành công và lưu inbox marker.
2. Replay cùng message từ DLQ.
3. Xác minh consumer nhận diện duplicate.
4. Kiểm tra business update/external idempotency chỉ có một hiệu ứng.
5. Replay một command mới với eventId mới và xác nhận đó là một nghiệp vụ riêng.

**Đạt:** giữ event identity qua replay.

### Lab G — Phân loại DLQ cohort

1. Tạo ba nhóm lỗi: converter, schema và business.
2. Đưa mỗi nhóm vào DLQ/quarantine với metadata phù hợp.
3. Đếm DLQ enqueue rate theo reason/source.
4. Tạo dashboard/alert theo cohort.
5. Xác minh không dùng eventId làm metric label.

**Đạt:** dashboard chỉ ra owner/root-cause group thay vì một con số DLQ tổng.

### Lab H — So sánh Classic và Artemis

1. Dựng hai broker sandbox riêng.
2. Classic: cấu hình individual DLQ strategy và client redelivery policy.
3. Artemis: cấu hình dead-letter-address, max-delivery-attempts và redelivery-delay.
4. Gửi cùng loại poison message, quan sát số lần giao và DLQ đích.
5. Ghi metadata gốc của từng broker và khác biệt namespace/client.
6. Không copy cấu hình XML của broker này sang broker kia.

**Đạt:** giải thích được cơ chế tương đương về mục tiêu nhưng khác cách cấu hình và quan sát.

## 14. Checklist vận hành và phát hành

- [ ] Xác định đúng broker/version, source queue/address và DLQ thực tế.
- [ ] Phân biệt poison redelivery, expiry, application quarantine và operator transfer.
- [ ] Có DLQ enqueue rate, depth, oldest age và grouping theo source/reason.
- [ ] Browse message read-only; lưu JMSMessageID, eventId, delivery count và original destination.
- [ ] Không log body nhạy cảm; có audit khi export/replay.
- [ ] Converter kiểm tra đúng JMS message type, encoding, content-type và type ID.
- [ ] Không deserialize ObjectMessage từ nguồn không tin cậy.
- [ ] Schema có eventType/schemaVersion, compatibility test và validation trước side effect.
- [ ] Authorization được kiểm tra bằng principal thực và operation/destination cụ thể.
- [ ] Phân biệt consume denied ở source với downstream send denied sau khi nhận.
- [ ] Business rejection hợp lệ được ghi terminal outcome và ACK, không rollback vô hạn.
- [ ] Lỗi transient có timeout, backoff, retry budget và circuit breaker.
- [ ] Lỗi permanent được quarantine/DLQ với reason và owner rõ.
- [ ] Classic redelivery/DLQ policy được kiểm tra trên client factory và destination policy đang dùng.
- [ ] Artemis address-setting match, max-delivery-attempts và dead-letter-address đã được xác minh.
- [ ] Replay giữ eventId khi là cùng event; side effects có inbox/downstream idempotency.
- [ ] Replay theo batch/canary, có rate limit, audit và business reconciliation.
- [ ] Inbox/DLQ retention đủ dài so với replay horizon.
- [ ] DLQ depth về 0 không được coi là phục hồi nếu business outcomes vẫn thiếu.

**Kết luận:** DLQ tăng do converter, schema, quyền truy cập hoặc lỗi nghiệp vụ cần được chẩn đoán theo **điểm thất bại trong đường xử lý**. Converter/schema thường là lỗi deterministic; authorization phải phân biệt thao tác consume với downstream send; business failure phải tách transient, permanent và terminal rejection. ActiveMQ Classic và Artemis có cấu hình redelivery/dead-letter khác nhau, nhưng nguyên tắc chung là **giữ bằng chứng, retry hữu hạn, quarantine có phân loại và replay có idempotency/audit**. Chỉ tuyên bố phục hồi khi message được xử lý đúng và kết quả nghiệp vụ đã được đối soát.
