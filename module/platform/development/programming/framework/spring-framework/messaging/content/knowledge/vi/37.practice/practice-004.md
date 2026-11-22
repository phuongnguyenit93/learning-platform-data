# Thực nghiệm Topic bền vững và xử lý thông điệp trùng

## Mục tiêu

Trong mô hình publish/subscribe, publisher gửi một sự kiện tới Topic và nhiều subscriber độc lập có thể nhận cùng sự kiện. Nếu subscriber tạm dừng hoặc ứng dụng bị restart, một subscriber thông thường có thể bỏ lỡ những message được gửi trong thời gian offline. Khi hệ thống phục hồi, broker cũng có thể giao lại một message mà consumer đã xử lý nghiệp vụ nhưng chưa xác nhận thành công.

Bài thực hành này dùng Spring JMS, Jakarta Messaging và ActiveMQ Artemis để xây dựng durable topic subscription, gửi persistent message và xử lý duplicate delivery bằng idempotency. Phần lưu kết quả dùng PostgreSQL để minh họa cách kết hợp transaction nghiệp vụ với acknowledgement của broker.

Sau bài này, bạn có thể:

- Phân biệt Topic, non-durable subscription và durable subscription.
- Phân biệt persistent delivery mode với durable subscription.
- Cấu hình Spring JMS publisher và listener cho Topic.
- Giữ subscription ổn định qua các lần restart.
- Nhận biết redelivery bằng JMSRedelivered và JMSXDeliveryCount.
- Chống xử lý trùng bằng event ID và unique constraint trong database.
- Hiểu cửa sổ lỗi giữa database commit và JMS acknowledgement.
- Kiểm thử subscriber offline, duplicate message, rollback và dead-letter queue.

Ví dụ dùng Java 17+, Spring Boot 4.x, Spring Framework 7.x, Jakarta Messaging và ActiveMQ Artemis. Các kiểu JMS dùng package jakarta.jms.

## 1. Hiểu Topic và durable subscription

Topic là destination theo mô hình publish/subscribe. Publisher gửi một message tới Topic; mỗi subscription phù hợp có thể nhận một bản message riêng. Một subscriber không lấy message khỏi Topic theo cách queue competing-consumer thông thường. Broker quản lý việc phân phối theo từng subscription.

### 1.1. Non-durable subscription

Một non-durable subscription thường chỉ tồn tại trong thời gian subscriber đang hoạt động. Khi consumer ngắt kết nối, các message được publish trong thời gian đó thường không được giữ lại cho subscriber. Khi consumer kết nối lại, nó tiếp tục nhận các message mới.

Cách này phù hợp với dữ liệu cập nhật có thể bỏ lỡ, chẳng hạn tín hiệu hiện diện hoặc một số thông báo giao diện. Nó không phù hợp nếu subscriber phải nhận mọi sự kiện kể cả khi service offline.

### 1.2. Durable subscription

Durable subscription có tên và định danh client ổn định. Broker giữ message dành cho subscription khi consumer tạm offline, sau đó giao các message còn hạn khi subscriber kết nối lại.

Với Jakarta Messaging, durable subscription được nhận diện bằng client ID và subscription name. Tên subscription phải duy nhất trong phạm vi client ID. Hai giá trị này cần ổn định qua các lần restart của cùng một logical subscriber.

Ví dụ:

- Topic: inventory.events
- Client ID: inventory-projection-client
- Subscription name: inventory-projection-v1

Khi ứng dụng restart với cùng client ID và subscription name, nó tiếp tục subscription đã đăng ký. Nếu đổi tên hoặc đổi client ID, broker có thể coi đó là subscription khác; backlog của subscription cũ không tự chuyển sang subscription mới.

**Lưu ý:** durable subscription phải được tạo trước khi message cần lưu được publish. Nếu chưa có subscriber durable đăng ký, message cũ không tự được phát lại cho một subscription được tạo sau này.

### 1.3. Persistent message và durable subscription là hai cơ chế khác nhau

Hai khái niệm thường bị nhầm:

| Cơ chế | Bảo vệ điều gì? | Không tự bảo đảm điều gì? |
|---|---|---|
| DeliveryMode.PERSISTENT | Yêu cầu broker lưu message bền vững khi gửi, theo khả năng và cấu hình của broker. | Không tự tạo backlog cho một subscriber không durable. |
| Durable subscription | Giữ message dành cho subscription khi subscriber offline. | Không tự làm message non-persistent trở thành persistent. |
| Session transaction / acknowledgement | Xác định khi nào broker coi message đã được consumer xử lý thành công. | Không tự làm side effect trong database và acknowledgement JMS thành một transaction chung. |
| Idempotency ở ứng dụng | Ngăn cùng một sự kiện tạo side effect nghiệp vụ nhiều lần. | Không thay thế broker persistence, retention hay retry policy. |

Muốn subscriber offline nhận lại sự kiện, thường cần cả message được gửi ở chế độ PERSISTENT và subscriber có durable subscription. Broker cũng phải được cấu hình persistence, quota và retention phù hợp. Message có thể hết hạn theo TTL hoặc bị ảnh hưởng bởi chính sách lưu trữ khi broker hết dung lượng.

## 2. Redelivery và duplicate message

Duplicate có thể xuất hiện ở nhiều tình huống:

1. Consumer nhận message và xử lý nghiệp vụ.
2. Database commit thành công.
3. Consumer hoặc broker gặp lỗi trước khi JMS session commit acknowledgement.
4. Broker chưa nhận được xác nhận, nên giao lại message.

Ở lần giao thứ hai, side effect database có thể đã xảy ra từ lần đầu. Nếu listener thực hiện lại thao tác mà không có idempotency, dữ liệu sẽ bị cập nhật hai lần.

Một tình huống khác xảy ra ở publisher: ứng dụng gửi persistent message nhưng mất kết nối trước khi biết kết quả gửi. Publisher có thể gửi lại cùng sự kiện. Lần gửi lại có thể tạo một JMSMessageID mới, dù đó vẫn là cùng một sự kiện nghiệp vụ.

Vì vậy, cần phân biệt:

- **JMSMessageID:** ID do provider tạo cho một message cụ thể; hữu ích để truy vết broker và redelivery.
- **Business event ID:** ID ổn định do ứng dụng tạo cho một sự kiện nghiệp vụ; dùng để deduplicate kể cả khi publisher gửi lại message.
- **JMSRedelivered:** cờ cho biết provider đang giao lại message.
- **JMSXDeliveryCount:** số lần giao được provider báo cáo, nếu provider cung cấp property này.

Không dùng JMSMessageID làm idempotency key duy nhất. Nếu publisher gửi lại cùng event bằng một lần send mới, provider có thể cấp ID khác. Business event ID phải được giữ nguyên qua mọi lần retry của cùng sự kiện.

### 2.1. At-least-once và idempotent consumer

Với durable subscription và transacted listener, ứng dụng thường thiết kế consumer theo hướng có thể nhận lại message chưa được xác nhận. Đây là lý do consumer phải an toàn khi xử lý cùng event nhiều lần.

Idempotent consumer bảo đảm rằng nếu cùng event ID đến nhiều lần thì side effect nghiệp vụ chỉ được áp dụng một lần. Các lần nhận tiếp theo đọc lại kết quả đã lưu và xác nhận message mà không thực hiện side effect lần nữa.

Không nên hứa exactly-once chỉ vì đã bật persistent delivery hoặc durable subscription. Exactly-once ở cấp nghiệp vụ cần phối hợp broker, transaction, database, publisher và consumer. Mẫu phổ biến là delivery có thể lặp lại kết hợp với xử lý idempotent.

## 3. Chuẩn bị project Spring Boot và broker

Ví dụ sử dụng ActiveMQ Artemis làm JMS provider và PostgreSQL làm nơi lưu trạng thái xử lý.

### 3.1. Dependencies

Trong Maven, thêm các dependency sau; phiên bản được Spring Boot dependency management quản lý:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-artemis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-jackson2</artifactId>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Lưu ý về Jackson trên Spring Boot 4:** Spring Boot 4 ưu tiên Jackson 3. Bài thực hành này giữ các import `com.fasterxml.jackson.*` của Jackson 2 để tập trung vào JMS, nên cần module `spring-boot-jackson2` để Spring Boot tự cấu hình bean `ObjectMapper` tương thích. Module này đã deprecated và chỉ nên dùng như bước chuyển tiếp; với dự án mới, ưu tiên Jackson 3 (`tools.jackson.*`) và `JsonMapper`.

Spring Boot starter Artemis cung cấp tích hợp JMS và ConnectionFactory cho Artemis. Spring Boot cũng có thể tự cấu hình JmsTemplate và listener infrastructure. Ví dụ này tạo các bean riêng cho Topic để làm rõ delivery mode và durable subscription.

### 3.2. Cấu hình kết nối

Trong application.properties:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=your-artemis-user
spring.artemis.password=your-artemis-password

spring.datasource.url=jdbc:postgresql://localhost:5432/inventory
spring.datasource.username=your-database-user
spring.datasource.password=your-database-password
~~~

Các giá trị đăng nhập trên là placeholder. Trong production, inject chúng qua environment hoặc secret manager; không commit password thật vào repository.

Broker cần bật persistent storage và cho phép tạo hoặc quản trị Topic/destination theo chính sách của môi trường. Trong production, nên provision destination, storage quota, expiration, redelivery và dead-letter address bằng cấu hình broker thay vì phụ thuộc vào auto-create.

### 3.3. Bật JMS listener

Trong lớp ứng dụng:

~~~java
package com.example.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class InventoryMessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            InventoryMessagingApplication.class,
            args
        );
    }
}
~~~

Trong Spring Boot, JMS listener infrastructure có thể được auto-configure khi có JMS provider và listener annotation. @EnableJms được đặt rõ ở đây để thể hiện việc bật annotation-driven listener trong ví dụ.

## 4. Tạo publisher gửi persistent message tới Topic

### 4.1. Event payload

Tạo file InventoryEvent.java:

~~~java
package com.example.inventory.contract;

public record InventoryEvent(
    String eventId,
    String sku,
    int quantity
) {}
~~~

eventId là định danh nghiệp vụ ổn định. Publisher phải tạo eventId một lần khi tạo sự kiện và giữ nguyên ID này khi retry gửi cùng sự kiện.

Không tạo UUID mới mỗi lần gọi publish() cho cùng một event. Nếu làm vậy, consumer sẽ không nhận ra các lần gửi lại là cùng một thao tác.

### 4.2. Cấu hình JmsTemplate cho Topic

Tạo file InventoryTopicConfiguration.java:

~~~java
package com.example.inventory.config;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;

import java.time.Duration;

import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.boot.jms.autoconfigure.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class InventoryTopicConfiguration {

    @Bean
    public JmsTemplate inventoryTopicTemplate(
        ConnectionFactory connectionFactory
    ) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setTimeToLive(Duration.ofDays(7).toMillis());
        return template;
    }

    @Bean
    public DefaultJmsListenerContainerFactory
            inventoryDurableTopicFactory(
                ConnectionFactory connectionFactory,
                DefaultJmsListenerContainerFactoryConfigurer configurer
            ) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        configurer.configure(
            factory,
            ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory)
        );

        factory.setPubSubDomain(true);
        factory.setClientId("inventory-projection-client");
        factory.setSubscriptionDurable(true);
        factory.setSubscriptionName("inventory-projection-v1");
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");

        return factory;
    }
}
~~~

Các cấu hình quan trọng:

- pubSubDomain=true: destination name được xử lý như Topic thay vì Queue.
- explicitQosEnabled=true: yêu cầu JmsTemplate sử dụng các giá trị QoS được cấu hình.
- DeliveryMode.PERSISTENT: yêu cầu broker lưu message bền vững theo cấu hình provider.
- timeToLive: giới hạn thời gian message còn hiệu lực; ví dụ là bảy ngày.
- clientId và subscriptionName: xác định durable subscription ổn định.
- subscriptionDurable=true: đăng ký durable topic subscription.
- sessionTransacted=true: listener session commit khi listener xử lý thành công và rollback khi listener ném lỗi.
- concurrency=1: dùng một consumer cho durable subscription không shared trong ví dụ này.

ConnectionFactoryUnwrapper.unwrapCaching giúp listener container dùng native ConnectionFactory thay vì wrapper cache do Spring Boot cấu hình cho các thao tác JMS thông thường. Điều này cho phép listener container tự quản lý connection và recovery. Package của Boot configurer có thể khác giữa các major version; dùng package tương ứng với Spring Boot BOM của dự án.

Một durable subscription thông thường chỉ cho phép một consumer hoạt động tại một thời điểm. Không tăng concurrency hoặc chạy nhiều instance cùng client ID một cách tùy tiện.

TTL bảy ngày chỉ là ví dụ. Chọn thời hạn theo thời gian tối đa consumer có thể offline và chính sách dữ liệu của hệ thống. Persistent message vẫn có thể hết hạn khi TTL đến hạn.

### 4.3. Publisher gửi TextMessage

Tạo file InventoryEventPublisher.java:

~~~java
package com.example.inventory.messaging;

import com.example.inventory.contract.InventoryEvent;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.jms.TextMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MessageConversionException;
import org.springframework.stereotype.Component;

@Component
public class InventoryEventPublisher {

    private final JmsTemplate topicTemplate;
    private final ObjectMapper objectMapper;

    public InventoryEventPublisher(
        @Qualifier("inventoryTopicTemplate")
        JmsTemplate topicTemplate,
        ObjectMapper objectMapper
    ) {
        this.topicTemplate = topicTemplate;
        this.objectMapper = objectMapper;
    }

    public void publish(InventoryEvent event) {
        final String body;

        try {
            body = objectMapper.writeValueAsString(event);
        }
        catch (JsonProcessingException ex) {
            throw new MessageConversionException(
                "Cannot serialize inventory event",
                ex
            );
        }

        topicTemplate.send("inventory.events", session -> {
            TextMessage message = session.createTextMessage(body);
            message.setStringProperty("eventId", event.eventId());
            return message;
        });
    }
}
~~~

Publisher gửi JSON trong TextMessage. eventId cũng được đặt vào message property để broker selector hoặc công cụ quan sát có thể sử dụng, nhưng consumer vẫn đọc eventId từ payload và kiểm tra idempotency trong database.

JmsTemplate dùng delivery mode đã cấu hình trong bean. Nếu bỏ explicitQosEnabled, các giá trị delivery mode/priority/TTL được đặt trên template có thể không được áp dụng theo cách mong muốn.

JMSMessageID do broker cấp sau khi gửi. Nó hữu ích cho log và điều tra nhưng không thay thế eventId.

## 5. Tạo durable topic listener

### 5.1. Cấu trúc database chống xử lý trùng

Tạo bảng inventory và processed_event. Ví dụ SQL dưới đây dành cho PostgreSQL:

~~~sql
CREATE TABLE inventory (
    sku VARCHAR(80) PRIMARY KEY,
    quantity BIGINT NOT NULL CHECK (quantity >= 0)
);

CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    payload_hash CHAR(64) NOT NULL,
    outcome VARCHAR(40) NOT NULL,
    jms_message_id VARCHAR(255),
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

processed_event lưu một hàng cho mỗi business event đã được xử lý. Unique primary key trên event_id là hàng rào chống hai consumer cùng áp dụng một event nhiều lần.

payload_hash giúp phát hiện trường hợp producer vô tình dùng lại eventId cho payload khác. Nếu eventId đã tồn tại nhưng hash không khớp, đây là lỗi contract hoặc lỗi tạo ID; không được âm thầm coi message mới là duplicate hợp lệ.

### 5.2. Service xử lý idempotent

Tạo file InventoryEventService.java:

~~~java
package com.example.inventory.service;

import com.example.inventory.contract.InventoryEvent;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryEventService {

    private final JdbcTemplate jdbcTemplate;

    public InventoryEventService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public ApplyResult applyOnce(
        InventoryEvent event,
        String jmsMessageId
    ) {
        validate(event);
        String hash = payloadHash(event);

        int inserted = jdbcTemplate.update("""
            INSERT INTO processed_event (
                event_id,
                payload_hash,
                outcome,
                jms_message_id,
                processed_at
            )
            VALUES (?, ?, 'PROCESSING', ?, CURRENT_TIMESTAMP)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.eventId(),
            hash,
            jmsMessageId
        );

        if (inserted == 0) {
            StoredEvent stored = jdbcTemplate.queryForObject(
                """
                SELECT payload_hash, outcome
                FROM processed_event
                WHERE event_id = ?
                """,
                (rs, rowNum) -> new StoredEvent(
                    rs.getString("payload_hash"),
                    rs.getString("outcome")
                ),
                event.eventId()
            );

            if (!stored.payloadHash().equals(hash)) {
                throw new EventIdCollisionException(
                    "eventId was reused with a different payload"
                );
            }

            return new ApplyResult(stored.outcome(), true);
        }

        int updated = jdbcTemplate.update(
            """
            UPDATE inventory
            SET quantity = quantity + ?
            WHERE sku = ?
            """,
            event.quantity(),
            event.sku()
        );

        String outcome = updated == 1
            ? "APPLIED"
            : "REJECTED_UNKNOWN_SKU";

        jdbcTemplate.update(
            """
            UPDATE processed_event
            SET outcome = ?
            WHERE event_id = ?
            """,
            outcome,
            event.eventId()
        );

        return new ApplyResult(outcome, false);
    }

    private void validate(InventoryEvent event) {
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()
                || event.sku() == null
                || event.sku().isBlank()
                || event.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Invalid inventory event"
            );
        }
    }

    private String payloadHash(InventoryEvent event) {
        String canonical = event.eventId()
            + "\n" + event.sku()
            + "\n" + event.quantity();

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(canonical.getBytes(StandardCharsets.UTF_8));

            return HexFormat.of().formatHex(digest);
        }
        catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "SHA-256 is unavailable",
                ex
            );
        }
    }

    private record StoredEvent(
        String payloadHash,
        String outcome
    ) {}

    public record ApplyResult(
        String outcome,
        boolean duplicate
    ) {}

    public static class EventIdCollisionException
            extends RuntimeException {

        public EventIdCollisionException(String message) {
            super(message);
        }
    }
}
~~~

Quy trình trong applyOnce():

1. Validate event và tính hash từ nội dung nghiệp vụ.
2. Insert eventId vào processed_event.
3. Nếu eventId đã tồn tại, đọc kết quả đã lưu.
4. Nếu payload hash khác, phát lỗi collision để message được xử lý theo chính sách lỗi vĩnh viễn/DLQ.
5. Nếu hash giống, trả kết quả cũ và đánh dấu duplicate=true.
6. Nếu đây là event mới, cập nhật inventory.
7. Ghi outcome APPLIED hoặc REJECTED_UNKNOWN_SKU.
8. Commit transaction database.

Câu lệnh INSERT ... ON CONFLICT là cú pháp PostgreSQL. Với MySQL, SQL Server, Oracle hoặc database khác, dùng unique constraint và câu lệnh insert-if-absent/upsert tương đương. Không bỏ unique constraint vì kiểm tra kiểu SELECT trước rồi INSERT có thể gặp race khi hai message cùng đến đồng thời.

Side effect cập nhật inventory và bản ghi processed_event nằm trong cùng database transaction. Nếu cập nhật database thất bại, cả hai thay đổi rollback; lần giao lại có thể thử xử lý lại. Nếu transaction commit, lần nhận tiếp theo thấy eventId đã có và không cập nhật inventory lần nữa.

REJECTED_UNKNOWN_SKU là kết quả nghiệp vụ đã được lưu. Listener có thể xác nhận message sau khi kết quả từ chối đã commit. Với lỗi kỹ thuật tạm thời, service phải ném exception để transaction rollback và broker có thể redeliver.

### 5.3. Listener nhận TextMessage

Tạo file InventoryTopicListener.java:

~~~java
package com.example.inventory.messaging;

import com.example.inventory.contract.InventoryEvent;
import com.example.inventory.service.InventoryEventService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageFormatException;
import jakarta.jms.TextMessage;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.converter.MessageConversionException;
import org.springframework.stereotype.Component;

@Component
public class InventoryTopicListener {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryTopicListener.class);

    private final ObjectMapper objectMapper;
    private final InventoryEventService service;

    public InventoryTopicListener(
        ObjectMapper objectMapper,
        InventoryEventService service
    ) {
        this.objectMapper = objectMapper;
        this.service = service;
    }

    @JmsListener(
        destination = "inventory.events",
        containerFactory = "inventoryDurableTopicFactory"
    )
    public void receive(Message message) throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new MessageFormatException(
                "Expected a TextMessage"
            );
        }

        final InventoryEvent event;

        try {
            event = objectMapper.readValue(
                textMessage.getText(),
                InventoryEvent.class
            );
        }
        catch (JsonProcessingException ex) {
            throw new MessageConversionException(
                "Invalid inventory event JSON",
                ex
            );
        }

        boolean redelivered = message.getJMSRedelivered();
        int deliveryCount = message.propertyExists("JMSXDeliveryCount")
            ? message.getIntProperty("JMSXDeliveryCount")
            : 1;

        InventoryEventService.ApplyResult result =
            service.applyOnce(event, message.getJMSMessageID());

        log.info(
            "eventId={} outcome={} duplicate={} redelivered={} " +
            "deliveryCount={} jmsMessageId={}",
            event.eventId(),
            result.outcome(),
            result.duplicate(),
            redelivered,
            deliveryCount,
            message.getJMSMessageID()
        );
    }
}
~~~

Listener không tự acknowledge message. Vì listener factory dùng sessionTransacted=true:

- Listener trả về bình thường: container commit JMS session và message được acknowledge.
- Listener ném exception: container rollback JMS session; broker có thể giao lại message theo redelivery policy.
- Listener nhận lại eventId đã có trong database: service trả kết quả cũ, listener hoàn tất bình thường và broker có thể xác nhận lần giao này.

Không bắt rồi bỏ qua mọi exception. Nếu listener nuốt lỗi database và trả về bình thường, broker sẽ coi message đã được xử lý và commit acknowledgement dù nghiệp vụ chưa thành công.

## 6. Hiểu transaction giữa JMS và database

Ví dụ trên có hai transaction cục bộ:

1. Transaction database do @Transactional quản lý trong InventoryEventService.
2. Transaction JMS do listener container quản lý qua sessionTransacted=true.

Khi listener gọi service, transaction database hoàn tất trước khi listener method trả về. Sau đó listener container mới commit JMS session. Hai transaction cục bộ này không tự trở thành một distributed transaction.

### 6.1. Các cửa sổ lỗi

| Thời điểm lỗi | Trạng thái có thể xảy ra | Cách phục hồi |
|---|---|---|
| Trước khi database commit | DB rollback; JMS session rollback khi listener ném lỗi. | Broker giao lại message. |
| Sau DB commit, trước JMS commit | Side effect đã lưu; acknowledgement chưa chắc đã commit. | Broker có thể redeliver; eventId làm lần xử lý sau thành no-op. |
| Sau JMS commit | Message đã được xác nhận. | Không cần redeliver message đó theo transaction này. |
| Publisher gửi thành công nhưng chưa ghi nhận trạng thái gửi | Message có thể đã ở broker nhưng publisher không biết. | Publisher có thể gửi lại; giữ nguyên eventId để consumer deduplicate. |

Nếu cần atomic commit giữa JMS và database, có thể dùng JTA/XA với XA-capable ConnectionFactory và transaction coordinator. Đây là lựa chọn phức tạp hơn, cần cấu hình broker, datasource, transaction manager và vận hành phù hợp. Với nhiều hệ thống, local transaction kết hợp idempotent consumer và transactional outbox thường dễ kiểm soát hơn.

### 6.2. Vì sao không dùng AUTO_ACKNOWLEDGE cho xử lý quan trọng?

Với AUTO_ACKNOWLEDGE, provider tự xác nhận theo quy tắc của session. Nếu listener xử lý side effect rồi gặp lỗi hoặc container shutdown trong một cửa sổ không thuận lợi, ứng dụng có thể không đạt được semantics rollback mong muốn.

Spring Framework khuyến nghị dùng transacted session khi cần độ tin cậy cho listener, bao gồm durable topic subscription. Hãy để exception đi tới container khi cần rollback; chỉ chuyển lỗi thành kết quả nghiệp vụ bình thường khi đã lưu trạng thái kết quả đó một cách có chủ đích.

## 7. Kiểm thử subscriber offline và message bền vững

Thực hiện theo thứ tự để chứng minh durable subscription hoạt động:

1. Khởi động ActiveMQ Artemis với persistent storage đã bật.
2. Khởi động ứng dụng consumer lần đầu.
3. Xác nhận listener tạo durable subscription với client ID và subscription name đã cấu hình.
4. Dừng consumer hoặc stop listener container nhưng không xóa durable subscription.
5. Trong lúc consumer offline, publisher gửi một hoặc nhiều message tới inventory.events ở DeliveryMode.PERSISTENT.
6. Khởi động lại consumer với cùng client ID và subscription name.
7. Xác nhận consumer nhận các message còn hạn đã được giữ cho subscription.
8. Kiểm tra database để xác nhận mỗi eventId chỉ làm thay đổi inventory một lần.

Nếu chưa từng khởi tạo durable subscription trước khi publish, không kỳ vọng broker tự giữ các message cũ cho subscription chưa tồn tại.

Không gọi unsubscribe hoặc xóa durable subscription trong quy trình restart bình thường. Việc xóa subscription có thể xóa backlog đang chờ và làm consumer mất khả năng nhận lại message offline.

### 7.1. Kiểm tra duplicate

Gửi cùng payload hai lần với cùng eventId:

~~~json
{
  "eventId": "inventory-receipt-00042",
  "sku": "BOOK-001",
  "quantity": 5
}
~~~

Giả sử inventory ban đầu có quantity bằng 10:

- Lần đầu: processed_event chưa có eventId, inventory tăng lên 15 và outcome được lưu là APPLIED.
- Lần thứ hai: eventId đã tồn tại và payload hash khớp, service trả duplicate=true; inventory vẫn là 15.

Hai lần publish mới có thể có hai JMSMessageID khác nhau. Điều này không ảnh hưởng vì deduplication dựa trên eventId nghiệp vụ.

### 7.2. Kiểm tra redelivery sau rollback

Có thể tạo integration test làm database transaction thất bại trước commit:

1. Publish một event mới.
2. Làm service ném lỗi trước khi transaction database commit.
3. Xác nhận processed_event và thay đổi inventory đều rollback.
4. Xác nhận JMS session rollback.
5. Khôi phục database và cho broker giao lại message.
6. Xác nhận lần giao lại tạo một bản ghi processed_event và chỉ áp dụng side effect một lần.

Để kiểm tra cửa sổ lỗi sau DB commit nhưng trước JMS commit, dùng fault injection trong integration test hoặc môi trường thử nghiệm broker. Sau khi DB đã commit, buộc acknowledgement JMS thất bại; khi message được redeliver, kiểm tra service trả duplicate=true và inventory không tăng thêm.

### 7.3. Kiểm tra event ID bị dùng lại sai

Gửi hai payload có cùng eventId nhưng khác SKU hoặc quantity. Hash sẽ khác và service ném EventIdCollisionException.

Đây là lỗi producer hoặc contract, không phải duplicate hợp lệ. Cấu hình redelivery policy có giới hạn và dead-letter queue để message lỗi vĩnh viễn không bị giao lại vô hạn. Ghi cảnh báo kèm eventId, JMSMessageID và correlation ID để điều tra.

## 8. Redelivery policy và dead-letter queue

Một lỗi tạm thời như database unavailable có thể được retry. Một lỗi dữ liệu vĩnh viễn như JSON sai định dạng hoặc eventId collision không nên bị retry vô hạn.

Cần cấu hình broker theo các yếu tố:

- Số lần giao lại tối đa.
- Khoảng nghỉ hoặc backoff giữa các lần redelivery.
- Dead-letter address/queue cho message vượt quá giới hạn.
- Retention và alert cho dead-letter message.
- Cách replay message sau khi lỗi đã được sửa.

Cấu hình cụ thể của redelivery và dead-letter phụ thuộc broker. Với Artemis, thiết lập address settings, dead-letter address, max-delivery-attempts và redelivery-delay theo tài liệu provider. Không coi tên property hoặc XML cấu hình của broker khác là cấu hình dùng chung của Jakarta Messaging.

Consumer không nên tự động ack một message lỗi vĩnh viễn chỉ để tránh retry. Hãy để broker đưa message vào DLQ sau số lần giao đã quy định, hoặc triển khai một quy trình quarantine có audit rõ ràng.

Khi replay từ DLQ, giữ nguyên business event ID. Nếu side effect đã commit trước khi message đi vào DLQ, idempotency store sẽ ngăn replay làm thay đổi dữ liệu lần nữa.

## 9. Quản lý nhiều subscriber và scale-out

Một Topic có thể có nhiều durable subscription độc lập. Ví dụ:

| Client ID | Subscription name | Consumer | Mục đích |
|---|---|---|---|
| inventory-projection-client | inventory-projection-v1 | Inventory projection | Cập nhật tồn kho |
| audit-service-client | audit-events-v1 | Audit service | Ghi lịch sử |
| notification-client | user-notifications-v1 | Notification service | Gửi thông báo |

Mỗi durable subscription độc lập nhận bản message dành cho subscription của nó. Một subscriber offline không làm mất backlog của subscriber khác nếu broker còn lưu và chính sách retention cho phép.

Nếu cần nhiều instance cùng xử lý một logical subscription, cân nhắc shared durable subscription theo Jakarta Messaging 2.0+ và khả năng của broker. Spring hỗ trợ cấu hình shared subscription bằng subscriptionShared và subscriptionName. Phải kiểm tra broker có hỗ trợ shared durable subscription, giới hạn consumer, client ID và concurrency trước khi scale-out.

Không khởi chạy nhiều instance cùng một non-shared durable subscription với cùng client ID rồi mong chúng tự chia tải. Một durable subscription thông thường không cho nhiều consumer cạnh tranh đồng thời; dùng shared subscription hoặc kiến trúc queue phù hợp khi cần competing consumers.

Nếu thứ tự xử lý theo aggregate là bắt buộc, concurrency cao có thể khiến thứ tự hoàn tất khác thứ tự nhận. Hãy mang aggregate ID và sequence number trong event, rồi tuần tự hóa xử lý theo aggregate hoặc dùng cơ chế partition/ordering mà broker hỗ trợ.

## 10. Producer retry và transactional outbox

Consumer idempotency xử lý duplicate delivery, nhưng producer cũng cần tránh mất sự kiện khi cập nhật database và gửi JMS.

Một lỗi phổ biến:

1. Cập nhật database nghiệp vụ.
2. Gửi JMS message.
3. Process crash giữa hai bước.

Nếu database commit nhưng message chưa được gửi, downstream không biết thay đổi đã xảy ra. Nếu message gửi xong nhưng ứng dụng không ghi nhận kết quả gửi, producer có thể gửi lại.

Transactional outbox giải quyết dual-write:

1. Trong cùng database transaction với thay đổi nghiệp vụ, ghi một outbox row.
2. Worker đọc outbox row chưa publish.
3. Worker gửi persistent JMS message với eventId lấy từ outbox.
4. Khi gửi thành công, đánh dấu row đã publish.
5. Nếu worker crash sau send nhưng trước khi đánh dấu, worker có thể gửi lại cùng eventId.
6. Consumer deduplicate bằng processed_event.

Outbox không làm broker và database commit thành một transaction duy nhất. Nó tạo nguồn sự kiện bền vững để publisher có thể retry; consumer idempotency xử lý trường hợp relay gửi lại.

Không tạo eventId mới khi relay retry cùng outbox row. Event ID phải được tạo và lưu ngay lúc ghi outbox.

## 11. Retention và vận hành durable subscription

Durable subscription có thể tích lũy backlog khi consumer offline. Vì vậy, cần theo dõi:

- Số message đang chờ theo subscription.
- Tuổi của message cũ nhất.
- Tốc độ publish và tốc độ consume.
- Dung lượng storage broker.
- Message hết hạn và message bị chuyển DLQ.
- Thời gian consumer offline.
- Số duplicate/redelivery.
- Số eventId collision hoặc lỗi payload.

Chính sách TTL phải cân bằng thời gian phục hồi với dung lượng lưu trữ. Nếu message hết hạn trước khi consumer trở lại, durable subscription không thể giao lại message đã hết hạn.

Khi ngừng hẳn một subscriber, quản trị viên cần quyết định có giữ backlog, replay sang consumer mới hay xóa subscription. Chỉ unsubscribe khi đã xác nhận backlog không còn cần thiết hoặc đã được lưu trữ/di chuyển theo quy trình.

Processed_event cũng cần retention. Giữ deduplication record ít nhất bằng thời gian tối đa mà message có thể được redeliver hoặc replay. Nếu xóa record quá sớm, một message cũ được replay có thể thực hiện side effect lần nữa. Với event ID toàn cục, có thể giữ key lâu dài hoặc archive các key cũ theo chính sách có thể truy vấn.

## 12. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ bật PERSISTENT nhưng dùng non-durable subscriber | Consumer offline vẫn có thể bỏ lỡ message. | Tạo durable subscription trước khi publish. |
| Dùng durable subscription nhưng gửi NON_PERSISTENT | Message có thể mất khi broker gặp sự cố. | Dùng DeliveryMode.PERSISTENT và bật broker persistence. |
| Đổi client ID hoặc subscription name sau restart | Tạo subscription khác và không đọc backlog cũ. | Giữ định danh ổn định qua deployment. |
| Dùng JMSMessageID làm khóa dedup | Publisher gửi lại cùng event có thể có ID mới. | Dùng business event ID ổn định. |
| Chỉ kiểm tra JMSRedelivered | Không phát hiện publisher gửi lại cùng event bằng message mới. | Deduplicate bằng eventId trong database. |
| Ack trước khi commit side effect | Message có thể mất khi nghiệp vụ chưa được lưu. | Dùng transacted listener và commit nghiệp vụ trước khi listener trả về. |
| DB commit nhưng JMS commit thất bại | Broker giao lại message và có thể lặp side effect. | Unique eventId và side effect trong cùng DB transaction. |
| Bắt rồi nuốt mọi exception | Broker coi message đã xử lý dù nghiệp vụ thất bại. | Propagate lỗi cần rollback; phân loại business outcome riêng. |
| Retry vô hạn message sai định dạng | Một poison message liên tục quay lại. | Bounded redelivery và DLQ. |
| Chạy nhiều consumer trên non-shared durable subscription | Xung đột subscription/client hoặc lỗi khởi tạo. | Dùng một consumer hoặc shared durable subscription có hỗ trợ. |
| Xóa processed_event quá sớm | Replay cũ có thể áp dụng side effect lần nữa. | Giữ dedup record theo replay/retention window. |
| Dùng Topic như Queue | Hiểu sai việc mỗi subscriber nhận một bản riêng. | Chọn đúng pub/sub hoặc competing-consumer model. |

## 13. Checklist thực hành

- [ ] Broker đã bật persistent storage và cấu hình retention/quota.
- [ ] Topic destination được provision hoặc auto-create theo policy rõ ràng.
- [ ] Publisher dùng pubSubDomain=true.
- [ ] Publisher bật explicit QoS và DeliveryMode.PERSISTENT.
- [ ] TTL phù hợp với thời gian consumer có thể offline.
- [ ] Durable subscription có client ID và subscription name ổn định.
- [ ] Durable subscription được tạo trước khi cần nhận backlog.
- [ ] Listener dùng sessionTransacted=true.
- [ ] Exception cần retry được propagate tới listener container.
- [ ] Mỗi business event có eventId ổn định qua các lần gửi lại.
- [ ] Database có unique constraint trên eventId.
- [ ] Side effect và processed_event được commit trong cùng DB transaction.
- [ ] Payload hash được kiểm tra để phát hiện eventId bị tái sử dụng sai.
- [ ] JMSRedelivered và JMSXDeliveryCount được log để quan sát.
- [ ] Broker có bounded redelivery, backoff và DLQ.
- [ ] Đã thử subscriber offline rồi restart cùng định danh.
- [ ] Đã thử gửi hai lần cùng eventId và xác nhận side effect chỉ chạy một lần.
- [ ] Đã thử DB rollback, JMS redelivery và cửa sổ DB commit/JMS ack.
- [ ] Đã có chính sách retention cho backlog và processed_event.
- [ ] Đã đánh giá shared durable subscription trước khi scale nhiều instance.

## Tài liệu tham khảo

- [Spring Framework Reference — Using JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): JmsTemplate, DefaultMessageListenerContainer, transaction và duplicate detection.
- [Spring Framework Reference — Receiving JMS Messages](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener container, transacted session và acknowledgement.
- [Spring Framework Reference — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): @JmsListener và cấu hình listener factory.
- [Spring Boot Reference — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html): Artemis auto-configuration, JmsTemplate và listener infrastructure.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): durable subscriptions, persistent delivery, acknowledgement, redelivery và duplicate delivery.
- [ActiveMQ Artemis Documentation](https://activemq.apache.org/components/artemis/documentation/): persistence, address settings, redelivery và dead-letter configuration.
