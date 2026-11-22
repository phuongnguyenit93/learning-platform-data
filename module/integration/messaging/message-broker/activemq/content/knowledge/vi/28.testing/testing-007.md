# Kiểm thử thông điệp lặp, consumer lũy đẳng và outbox

> **Chương:** Kiểm thử  
> **Phạm vi:** Java/JMS với ActiveMQ Classic và Artemis; ví dụ triển khai dùng **Spring Boot 3, Jakarta JMS và PostgreSQL**. Trọng tâm là kiểm chứng message có thể được giao nhiều lần, consumer vẫn tạo đúng một hiệu ứng nghiệp vụ, và transactional outbox bảo vệ bước ghi dữ liệu đồng thời phát sự kiện. Các đoạn mã cần được đặt trong ứng dụng có schema, transaction manager và broker đã cấu hình theo môi trường.

Một producer gửi lệnh thành công nhưng timeout trước khi nhận phản hồi. Nó không biết broker đã commit message hay chưa nên gửi lại. Một consumer cập nhật database xong thì JVM chết trước khi ACK. Broker giao lại message sau khi kết nối phục hồi. Một relay đọc outbox, gửi message sang broker thành công rồi chết trước khi đánh dấu bản ghi đã publish. Cả ba tình huống đều có thể tạo **nhiều lần delivery cho cùng một sự kiện logic**.

Hệ thống tin cậy không giả định message chỉ đến một lần. Nó thiết kế để **delivery có thể lặp nhưng hiệu ứng nghiệp vụ không bị lặp**. Hai cơ chế cốt lõi:

- **Idempotent consumer / inbox:** nhận cùng event nhiều lần nhưng chỉ commit một lần thay đổi nghiệp vụ cho cùng business event ID.
- **Transactional outbox:** ghi thay đổi nghiệp vụ và ý định phát message trong cùng database transaction; relay phát lại cho đến khi broker xác nhận tiếp nhận.

Cả hai phải được kiểm thử với **retry, concurrency, crash và kết quả commit không rõ**. Chỉ kiểm tra một lần send/receive thành công chưa chứng minh được tính lũy đẳng.

## 1. Delivery lặp khác với nghiệp vụ bị lặp

JMS và broker cung cấp cơ chế delivery, acknowledgement, transaction, redelivery và persistence. Chúng không tự biết hai message có body giống nhau là cùng một nghiệp vụ hay hai lệnh hợp lệ khác nhau.

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| **Delivery attempt** | Broker giao message lần thứ 2 sau rollback | Một lần consumer nhận message |
| **JMSMessageID** | ID do provider cấp cho một message instance | Định danh message theo provider; không phải khóa nghiệp vụ |
| **eventId / commandId** | order-created-7f... | Định danh ổn định của một sự kiện/lệnh logic |
| **Business key** | paymentAttemptId, orderId + version | Khóa theo nghiệp vụ; có thể cần phân biệt nhiều lần thử |
| **Idempotent effect** | Cùng commandId cập nhật trạng thái tối đa một lần | Trạng thái cuối không đổi khi cùng lệnh được áp dụng lại |

**Không dùng JMSMessageID làm khóa idempotency mặc định.** Producer retry có thể tạo một JMS message mới với provider ID khác, dù đó là cùng một command. Một message được chuyển tiếp qua broker khác, replay từ DLQ hoặc phát lại từ outbox cũng không nên phụ thuộc vào việc provider giữ nguyên JMSMessageID.

Hợp đồng message nên có **eventId/commandId bất biến** ngay từ lúc tạo. ID này được lưu trong database/outbox, truyền qua JMS property và dùng làm khóa duy nhất ở consumer.

### 1.1. Những cửa sổ sinh duplicate phổ biến

~~~mermaid
flowchart TD
    P["Producer gửi"] --> A["Broker commit"]
    A --> T["Producer timeout trước response"]
    T --> R["Producer retry cùng commandId"]
    A --> D["Broker dispatch"]
    D --> DB["Consumer commit DB"]
    DB --> C["Crash trước JMS ACK"]
    C --> RD["Broker redelivery"]
    O["Outbox relay send"] --> B["Broker nhận"]
    B --> X["Crash trước published_at"]
    X --> O
~~~

Các nguồn duplicate cần được test riêng:

1. **Producer retry:** broker có thể đã nhận/commit message, nhưng response bị mất trên đường về producer.
2. **Consumer rollback:** lỗi xử lý khiến JMS transaction rollback; broker giao lại message.
3. **Crash sau DB commit, trước JMS ACK:** database đã lưu hiệu ứng; broker chưa biết receive đã hoàn tất.
4. **Network bridge/reconnect:** kết quả forwarding/ACK không rõ hoặc message được replay theo topology.
5. **Outbox relay crash:** broker đã nhận message nhưng outbox row vẫn chưa được đánh dấu published.
6. **DLQ replay/manual replay:** operator phát lại cùng một nghiệp vụ để khôi phục.
7. **Concurrency:** hai consumer nhận hai delivery của cùng event gần như đồng thời.

Đây là những tình huống bình thường của mô hình **at-least-once**. Một consumer đúng phải chịu được việc nhận lại cùng eventId.

### 1.2. Exactly-once phải được định nghĩa ở đâu?

Cụm từ “exactly-once” thường bị dùng quá rộng. Hãy tách rõ:

- **Exactly-once delivery:** một message chỉ được broker giao đúng một lần qua mọi crash/retry. Không nên dựa vào giả định này cho JMS end-to-end.
- **Exactly-once database effect:** cùng eventId chỉ tạo một thay đổi nghiệp vụ đã commit trong database một lần, nhờ unique key và transaction.
- **Exactly-once external side effect:** ví dụ charge thẻ chỉ xảy ra một lần; cần idempotency key hoặc cơ chế reconciliation của payment provider. DB inbox không thể rollback một HTTP request đã thành công.

Trong bài này, mục tiêu kiểm chứng là **một hiệu ứng nghiệp vụ bền vững cho một eventId**, trong khi message có thể được giao nhiều lần.

## 2. Hợp đồng event ID và payload bất biến

Một message nên mang envelope rõ ràng:

~~~json
{
  "eventId": "evt-2026-000041",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-17T09:30:00Z",
  "aggregateId": "order-1042",
  "aggregateVersion": 8,
  "payload": {
    "orderId": "order-1042",
    "status": "CONFIRMED"
  }
}
~~~

Quy tắc thiết kế:

- **eventId** được tạo một lần cho một sự kiện logic; retry/replay phải giữ nguyên ID.
- **eventType + schemaVersion** xác định cách giải mã payload.
- **aggregateId + aggregateVersion** giúp kiểm tra thứ tự hoặc phát hiện sự kiện cũ theo từng aggregate.
- **occurredAt** là thời điểm nghiệp vụ, không phải thời gian broker nhận hoặc consumer commit.
- Payload của cùng eventId phải bất biến. Nếu một eventId xuất hiện với payload khác, đó là **identity conflict**, không được âm thầm coi là duplicate bình thường.
- Một order có thể có nhiều command hợp lệ; không dùng riêng orderId làm eventId nếu mỗi command phải được xử lý độc lập.

### 2.1. JMS properties và body là hai phần khác nhau

Ví dụ producer gắn event ID vào property để consumer truy cập nhanh:

~~~java
jmsTemplate.convertAndSend(
    "orders.events.v1",
    jsonPayload,
    message -> {
        message.setStringProperty("eventId", eventId);
        message.setStringProperty("eventType", "OrderConfirmed");
        message.setIntProperty("schemaVersion", 1);
        return message;
    }
);
~~~

Nếu eventId cũng có trong JSON body, hãy xác minh **property và body trùng nhau** ở consumer. Không để một bên ghi eventId A, bên kia eventId B; điều đó có thể khiến inbox dedupe theo sai khóa.

JMS property có kiểu dữ liệu và giới hạn riêng; dùng tên property hợp lệ, tránh reserved/provider-specific properties nếu không chủ đích. Với Artemis, property riêng của broker như duplicate-detection ID có semantics đặc thù; không thay thế eventId ở tầng nghiệp vụ.

### 2.2. Hash payload để phát hiện event ID bị tái sử dụng

Một inbox có thể lưu **SHA-256 của payload bất biến**. Khi eventId đã tồn tại:

- Hash giống: delivery trùng của cùng nội dung; có thể bỏ qua business effect và cho listener hoàn tất ACK.
- Hash khác: cùng ID bị dùng cho nội dung khác; cần quarantine/DLQ và cảnh báo, không silently drop.

Nếu payload JSON được serialize khác thứ tự field hoặc khoảng trắng, hash byte thô có thể khác dù nội dung logic tương đương. Chọn một trong hai hợp đồng:

1. **Immutable wire payload:** producer lưu nguyên bytes và mọi retry gửi lại đúng bytes đó.
2. **Canonical representation:** chuẩn hóa JSON/schema trước khi hash.

Không tùy tiện parse rồi stringify bằng serializer có cấu hình khác giữa producer và consumer.

## 3. Idempotent consumer bằng inbox và unique constraint

Cách phổ biến, dễ kiểm chứng nhất là lưu event ID đã xử lý trong **cùng database transaction** với thay đổi nghiệp vụ. Unique constraint là chốt đồng bộ khi có nhiều consumer đồng thời.

### 3.1. Schema PostgreSQL

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name   VARCHAR(120) NOT NULL,
    event_id        VARCHAR(160) NOT NULL,
    payload_sha256  CHAR(64) NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE orders (
    order_id        VARCHAR(120) PRIMARY KEY,
    status          VARCHAR(40) NOT NULL,
    version         BIGINT NOT NULL
);
~~~

Khóa chính là **(consumer_name, event_id)**, không chỉ eventId. Điều này cho phép hai logical consumers độc lập xử lý cùng một event nếu kiến trúc cần hai projections/side effects khác nhau. Mỗi consumer name phải ổn định theo contract; đổi tên tùy tiện có thể khiến inbox coi mọi message cũ là mới.

Không xóa inbox row ngay sau ACK. Retention phải dài ít nhất bằng **thời gian tối đa message có thể replay**, gồm broker retention, DLQ retention, backup restore và outbox replay horizon. Nếu xóa marker rồi replay event cũ, business effect có thể chạy lại.

### 3.2. Nguyên tử giữa inbox và business update

Trong **một DB transaction**:

1. Thử insert khóa (consumer_name, event_id).
2. Nếu insert thành công, áp dụng business update.
3. Nếu khóa đã tồn tại và hash trùng, không áp dụng update lần nữa.
4. Nếu khóa tồn tại nhưng hash khác, báo identity conflict.
5. Commit marker và business update cùng nhau.

**Không** ghi inbox rồi commit riêng trước khi cập nhật nghiệp vụ. Nếu process chết giữa hai commit, lần redelivery sau thấy marker đã có và bỏ qua update bị thiếu. Ngược lại, nếu cập nhật nghiệp vụ trước rồi ghi inbox ở transaction khác, crash có thể khiến update chạy hai lần.

### 3.3. Java service với Spring Boot 3 và JdbcTemplate

Ví dụ dùng **Java 17, Spring Boot 3, Jakarta JMS và PostgreSQL**. Service này xử lý event body đã được giải mã thành JSON string; transaction manager tên **transactionManager** đại diện cho datasource PostgreSQL của ứng dụng.

~~~java
package com.example.orders.messaging;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdempotentOrderProcessor {
    private static final String CONSUMER = "orders-projection-v1";

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public IdempotentOrderProcessor(
            JdbcTemplate jdbc,
            ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    @Transactional(transactionManager = "transactionManager")
    public ProcessResult process(String eventId, String payload) {
        String hash = sha256(payload);

        int inserted = jdbc.update("""
            INSERT INTO consumer_inbox
                (consumer_name, event_id, payload_sha256)
            VALUES (?, ?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            CONSUMER, eventId, hash
        );

        if (inserted == 0) {
            String previousHash = jdbc.queryForObject("""
                SELECT payload_sha256
                FROM consumer_inbox
                WHERE consumer_name = ?
                  AND event_id = ?
                """,
                String.class, CONSUMER, eventId
            );

            if (!MessageDigest.isEqual(
                    previousHash.getBytes(StandardCharsets.US_ASCII),
                    hash.getBytes(StandardCharsets.US_ASCII))) {
                throw new EventIdentityConflictException(eventId);
            }

            return ProcessResult.DUPLICATE;
        }

        try {
            OrderConfirmed event =
                objectMapper.readValue(payload, OrderConfirmed.class);

            int changed = jdbc.update("""
                UPDATE orders
                SET status = ?, version = ?
                WHERE order_id = ? AND version = ?
                """,
                "CONFIRMED",
                event.aggregateVersion(),
                event.orderId(),
                event.aggregateVersion() - 1
            );

            if (changed != 1) {
                throw new IllegalStateException(
                    "Order missing or aggregate version mismatch: "
                    + event.orderId());
            }

            return ProcessResult.APPLIED;
        } catch (Exception error) {
            // Runtime exception làm rollback cả inbox insert
            // và business update trong cùng transaction.
            throw new IllegalArgumentException(
                "Cannot process event " + eventId, error);
        }
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    public enum ProcessResult {
        APPLIED,
        DUPLICATE
    }

    public record OrderConfirmed(
        String orderId,
        long aggregateVersion
    ) {}

    public static final class EventIdentityConflictException
            extends RuntimeException {
        public EventIdentityConflictException(String eventId) {
            super("Same eventId has different payload: " + eventId);
        }
    }
}
~~~

PostgreSQL unique constraint đồng bộ các transaction cạnh tranh. Nếu hai transaction cùng insert một eventId, một transaction thắng; transaction còn lại chờ conflict được giải quyết và nhận **inserted = 0** nếu row đầu đã commit. Nó tiếp tục đọc hash và so sánh nội dung.

Nếu cùng eventId nhưng payload khác, exception làm transaction hiện tại rollback. Đây là **message lỗi hợp đồng**, không phải duplicate bình thường; cấu hình error handler/redelivery/DLQ để cách ly sau số lần thử hữu hạn. Không catch exception rồi trả về bình thường, vì listener có thể ACK message sai.

**ProcessResult.DUPLICATE** là kết quả thành công về xử lý delivery: không áp dụng lại business effect, nhưng listener có thể commit JMS receive.

### 3.4. Gắn listener với local JMS transaction

~~~java
package com.example.orders.messaging;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderConfirmedListener {
    private final IdempotentOrderProcessor processor;

    public OrderConfirmedListener(IdempotentOrderProcessor processor) {
        this.processor = processor;
    }

    @JmsListener(
        destination = "orders.events.v1",
        containerFactory = "transactedJmsListenerContainerFactory"
    )
    public void onMessage(
            String payload,
            @Header("eventId") String eventId) {
        processor.process(eventId, payload);
        // Không tự ACK ở đây; listener container commit session.
    }
}
~~~

Listener factory phải bật local transacted session:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Bean
public DefaultJmsListenerContainerFactory
        transactedJmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-8");
    return factory;
}
~~~

**Hai transaction trong ví dụ vẫn là hai resource local:**

- Method **process** commit PostgreSQL transaction khi method qua Spring transaction proxy trả về thành công.
- Sau khi callback listener trả về, container commit JMS receive session.
- Nếu process ném exception trước DB commit, DB rollback và listener container rollback receive.
- Nếu DB đã commit nhưng JVM chết trước JMS commit, broker redeliver. Inbox row đã commit nên lần tiếp theo trả DUPLICATE và không lặp business update.

Đây là failure window được thiết kế để an toàn nhờ inbox. **Không tuyên bố DB và JMS có atomic commit** chỉ vì cả hai đều transacted. Nếu ứng dụng có nhiều transaction managers, chỉ rõ manager cho business service và kiểm tra thứ tự commit thực tế.

### 3.5. Hash mismatch và poison message

Một eventId đã dùng với payload khác có thể chỉ ra producer bug, event ID bị tái sử dụng, corruption hoặc một nguồn gửi không đáng tin. Không tự động bỏ qua theo eventId vì sẽ che mất dữ liệu xung đột.

Quy trình phù hợp:

- Ghi log có **eventId, consumerName, payload hashes**, không log toàn bộ dữ liệu nhạy cảm.
- Ném lỗi phân loại được để retry policy xử lý hữu hạn.
- Sau ngưỡng, đưa message vào **DLQ/quarantine** và tạo alert.
- Operator đối chiếu nguồn phát, schema và business aggregate trước khi replay.
- Khi sửa dữ liệu, phát event mới với ID mới nếu đó là một sự kiện nghiệp vụ mới; không âm thầm sửa body dưới eventId cũ.

## 4. Transactional outbox: ghi business state và ý định publish cùng nhau

Một lỗi phổ biến là cập nhật database rồi gọi JMS trong cùng method có annotation **@Transactional**:

~~~java
@Transactional
public void confirmOrder(Order order) {
    orderRepository.save(order);
    jmsTemplate.convertAndSend("orders.events.v1", toEvent(order));
}
~~~

Nếu transaction manager được chọn là database manager, annotation chỉ quản lý database. JMS send vẫn là một resource khác. Có thể xảy ra:

- DB commit nhưng send thất bại: trạng thái nghiệp vụ đã đổi mà event không được phát.
- Broker nhận event nhưng DB rollback: consumer nhìn thấy event cho thay đổi chưa được lưu.
- Broker nhận event, producer mất kết nối trước response: caller retry và phát event lần nữa.

**Transactional outbox** lưu event cần phát trong cùng DB transaction với thay đổi nghiệp vụ. Một relay độc lập đọc outbox và publish sau commit:

~~~text
DB transaction:
    UPDATE business aggregate
    INSERT outbox_event
    COMMIT

Relay:
    CLAIM pending rows
    SEND persistent JMS message
    MARK published_at
~~~

Outbox bảo đảm **ý định phát event không bị tách khỏi business commit**. Nó vẫn có thể phát trùng nếu relay crash sau khi broker nhận message nhưng trước khi đánh dấu published. Vì vậy cần kết hợp với inbox/idempotent consumer ở mục 3.

### 4.1. Schema PostgreSQL

~~~sql
CREATE TABLE outbox_event (
    event_id          UUID PRIMARY KEY,
    aggregate_id      VARCHAR(160) NOT NULL,
    aggregate_version BIGINT,
    event_type        VARCHAR(160) NOT NULL,
    destination       VARCHAR(240) NOT NULL,
    payload           TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at      TIMESTAMPTZ,
    attempts          INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner       VARCHAR(160),
    lease_token       UUID,
    lease_until       TIMESTAMPTZ,
    failed_at         TIMESTAMPTZ,
    last_error        TEXT,
    CHECK ((lease_owner IS NULL) = (lease_token IS NULL)),
    CHECK ((lease_owner IS NULL) = (lease_until IS NULL)),
    CHECK (published_at IS NULL OR failed_at IS NULL)
);

CREATE INDEX outbox_pending_idx
    ON outbox_event (next_attempt_at, created_at, event_id)
    WHERE published_at IS NULL AND failed_at IS NULL;
~~~

- **event_id:** ID bất biến sẽ được truyền sang JMS.
- **aggregate_id / aggregate_version:** hỗ trợ trace và thứ tự theo aggregate.
- **event_type / destination / payload:** routing và nội dung đã chốt lúc business transaction commit.
- **published_at:** relay đã hoàn tất send theo contract của JMS client; **không** chứng minh consumer đã xử lý.
- **attempts / next_attempt_at:** retry/backoff.
- **lease_owner / lease_token / lease_until:** claim tạm thời của một relay worker.
- **failed_at:** trạng thái terminal để loại row lỗi vĩnh viễn khỏi claim tự động; cần runbook sửa nguyên nhân và replay có kiểm soát.
- **last_error:** thông tin lỗi đã được làm sạch; không lưu credentials hoặc payload nhạy cảm.

Partial index tránh quét lịch sử rows đã published. Production cần archive/cleanup có kiểm soát; không xóa pending rows.

Destination nên được ánh xạ từ **event_type** qua allowlist cấu hình của ứng dụng; không lấy tên queue tùy ý từ request bên ngoài rồi lưu thẳng vào outbox để relay gửi. Nếu ứng dụng kết nối nhiều brokers, JmsTemplate của relay phải được inject đúng ConnectionFactory bằng **@Qualifier**.

### 4.2. Business update và outbox insert trong cùng transaction

Ví dụ dùng eventId được tạo từ command/idempotency key đã được chấp nhận:

~~~java
package com.example.orders.application;

import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderConfirmationService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public OrderConfirmationService(
            JdbcTemplate jdbc,
            ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    @Transactional(transactionManager = "transactionManager")
    public void confirm(
            String orderId,
            long expectedVersion,
            UUID eventId) {

        long newVersion = expectedVersion + 1;

        int changed = jdbc.update("""
            UPDATE orders
            SET status = 'CONFIRMED', version = ?
            WHERE order_id = ? AND version = ?
            """,
            newVersion, orderId, expectedVersion
        );

        if (changed != 1) {
            throw new IllegalStateException(
                "Order missing or version conflict: " + orderId);
        }

        var event = new OrderConfirmed(
            eventId.toString(), orderId, newVersion);

        final String payload;
        try {
            payload = objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException error) {
            throw new IllegalArgumentException(
                "Cannot serialize OrderConfirmed", error);
        }

        jdbc.update("""
            INSERT INTO outbox_event (
                event_id, aggregate_id, aggregate_version,
                event_type, destination, payload
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            eventId, orderId, newVersion,
            "OrderConfirmed", "orders.events.v1", payload
        );
    }

    public record OrderConfirmed(
        String eventId,
        String orderId,
        long aggregateVersion
    ) {}
}
~~~

**Không sinh eventId mới mỗi lần API retry.** ID phải được tạo/lưu theo command logic. Nếu request client timeout rồi gửi lại, application phải nhận diện cùng request hoặc cùng aggregate transition; nếu không, hai request có thể tạo hai outbox rows hợp lệ về mặt kỹ thuật nhưng cùng một ý định nghiệp vụ.

Nếu business UPDATE thành công nhưng INSERT outbox thất bại, exception làm **cùng transaction rollback**. Nếu cả hai commit, relay có thể publish sau khi request kết thúc.

### 4.3. Kiểm thử atomicity

| Kịch bản | Business row | Outbox row | Kết quả mong đợi |
|---|---|---|---|
| Update và insert thành công | Commit | Commit | Relay có thể publish |
| Outbox insert fail do constraint | Rollback | Không có row | Không có business commit thiếu event |
| Business update fail | Rollback | Không được commit | Không phát event |
| Transaction rollback sau cả hai lệnh | Rollback | Rollback | Không có row để relay |

Dùng database thật trong integration test (ví dụ PostgreSQL Testcontainers), cố tình gây constraint violation hoặc ném exception rồi query lại bằng transaction mới. **Mock JmsTemplate không kiểm chứng được atomicity DB/outbox**, vì tính chất này nằm hoàn toàn trong database transaction.

## 5. Relay đa worker: claim ngắn, send ngoài transaction, mark có fencing token

Không để nhiều relay worker cùng đọc một row pending rồi cùng publish. PostgreSQL hỗ trợ **FOR UPDATE SKIP LOCKED** để worker claim các rows khác nhau mà không phải chờ row đã bị worker khác khóa.

Không giữ row lock trong lúc network send: broker chậm có thể làm transaction database kéo dài và giữ lock không cần thiết. Chia thành ba giai đoạn:

1. Claim một batch trong transaction ngắn, gán lease/token rồi commit.
2. Gửi message tới broker bên ngoài transaction claim.
3. Khi send thành công, mark published bằng đúng lease token; khi lỗi thì lên lịch retry và giải phóng lease.

### 5.1. Claim batch bằng SQL

Trong các câu lệnh SQL bên dưới, dấu hai chấm như **:worker_id** là placeholder minh họa cho NamedParameterJdbcTemplate; ví dụ Java ở mục 6 dùng dấu **?** của JdbcTemplate.

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_event
    WHERE published_at IS NULL
      AND failed_at IS NULL
      AND next_attempt_at <= clock_timestamp()
      AND (lease_until IS NULL OR lease_until < clock_timestamp())
    ORDER BY created_at, event_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_event AS o
SET lease_owner = :worker_id,
    lease_token = :lease_token,
    lease_until = clock_timestamp() + interval '30 seconds',
    attempts = o.attempts + 1
FROM candidates AS c
WHERE o.event_id = c.event_id
RETURNING
    o.event_id, o.destination, o.event_type,
    o.payload, o.lease_token;
~~~

Câu lệnh chạy trong **một DB transaction**. Các row locks bảo vệ việc chọn candidates; UPDATE gán lease. Khi transaction commit, worker khác không claim row cho tới khi lease hết hạn hoặc được giải phóng.

**lease_token** là UUID mới cho mỗi batch. Khi mark published/retry, worker đưa token vào điều kiện WHERE. Nếu worker cũ chạy chậm qua lease expiry và worker mới đã claim row, token cũ không thể cập nhật trạng thái của claim mới.

### 5.2. Lease expiry phục hồi worker bị chết

Với lease 30 giây:

- Worker send xong: mark published và xóa lease.
- Worker gặp lỗi send: đặt next_attempt_at, xóa lease để retry sau backoff.
- Worker crash: không thể giải phóng lease; sau 30 giây worker khác có thể claim.
- Worker cũ thức dậy muộn: token cũ không còn quyền mark row.

Lease phải dài hơn thời gian xử lý batch thông thường. Nếu publish có thể kéo dài, giảm batch size, gia hạn lease bằng heartbeat hoặc tăng thời hạn. **Fencing token ngăn cập nhật trạng thái sai, nhưng không ngăn worker cũ gửi message sau khi lease hết hạn.** Consumer vẫn phải idempotent.

### 5.3. Mark published và lên lịch retry

Sau khi broker send trả về thành công:

~~~sql
UPDATE outbox_event
SET published_at = clock_timestamp(),
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    last_error = NULL
WHERE event_id = :event_id
  AND lease_token = :lease_token
  AND published_at IS NULL
  AND failed_at IS NULL;
~~~

Kiểm tra số rows cập nhật:

- **1 row:** worker vẫn sở hữu lease và mark thành công.
- **0 rows:** lease đã đổi/hết hạn hoặc row đã được xử lý; worker cũ không được ghi đè. Send trước đó có thể đã xảy ra, nên duplicate vẫn có thể tồn tại.

Khi send lỗi:

~~~sql
UPDATE outbox_event
SET next_attempt_at = clock_timestamp() + interval '30 seconds',
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    last_error = :sanitized_error
WHERE event_id = :event_id
  AND lease_token = :lease_token
  AND published_at IS NULL
  AND failed_at IS NULL;
~~~

30 giây là giá trị minh họa. Production nên dùng **exponential backoff có jitter và mức trần**, phân biệt lỗi tạm thời (broker unavailable, timeout) với lỗi vĩnh viễn (destination sai, payload/schema lỗi). Lỗi vĩnh viễn cần FAILED/quarantine và alert, không retry vô hạn.

Khi xác định lỗi vĩnh viễn, relay hoặc operator có thể đánh dấu row terminal bằng lease token đang sở hữu:

~~~sql
UPDATE outbox_event
SET failed_at = clock_timestamp(),
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    last_error = :sanitized_error
WHERE event_id = :event_id
  AND lease_token = :lease_token
  AND published_at IS NULL
  AND failed_at IS NULL;
~~~

Row FAILED không được poller tự động claim lại. Sau khi sửa cấu hình/schema, operator phải thực hiện thao tác replay có audit, giữ nguyên eventId nếu vẫn là cùng sự kiện logic.

### 5.4. Nhiều relay workers không bảo đảm FIFO toàn cục

ORDER BY created_at trong claim query **không bảo đảm thứ tự publish toàn cục** khi nhiều worker chạy song song. Worker 1 claim event A, worker 2 claim event B rồi B send nhanh hơn; consumer có thể nhận B trước A.

Nếu nghiệp vụ yêu cầu thứ tự theo aggregate:

- Ghi **aggregate_version/sequence** trong cùng transaction với aggregate.
- Chỉ claim event chưa published nhỏ nhất của mỗi aggregate; event version sau đợi version trước.
- Hoặc partition relay theo aggregate key để cùng một aggregate đi cùng lane.
- Consumer kiểm tra version và xử lý event đến sớm/muộn theo contract.

Không khóa toàn bộ outbox để đạt global FIFO nếu không có yêu cầu; nó làm giảm throughput.

## 6. Java relay với JmsTemplate

Ví dụ tiếp tục dùng **Spring Boot 3/Jakarta JMS**. Relay claim rows trong một service transaction riêng, gửi message persistent và chỉ sau khi send trả về mới mark published.

### 6.1. Cấu hình JmsTemplate persistent

~~~java
package com.example.orders.outbox;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class OutboxJmsConfiguration {

    @Bean
    public JmsTemplate outboxJmsTemplate(
            ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        return template;
    }
}
~~~

Trong Spring, QoS properties tùy chỉnh của JmsTemplate chỉ được áp dụng khi **explicitQosEnabled=true**. Persistent delivery yêu cầu broker lưu message theo persistence policy của destination. Nó không thay việc kiểm tra broker store, send confirmation, TLS/auth hoặc consumer idempotency.

Relay nên dùng chế độ gửi đồng bộ hoặc cơ chế producer confirmation được provider hỗ trợ. Không bật async-send/window mode rồi coi việc API trả về sớm là bằng chứng broker đã xác nhận lưu message; kiểm tra semantics của client Classic/Artemis và version đang chạy.

### 6.2. Record đại diện outbox row đã claim

~~~java
package com.example.orders.outbox;

import java.util.UUID;

public record ClaimedOutboxEvent(
    UUID eventId,
    String destination,
    String eventType,
    String payload,
    UUID leaseToken
) {}
~~~

### 6.3. Claim service với transaction ngắn

~~~java
package com.example.orders.outbox;

import java.util.List;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OutboxClaimService {
    private final JdbcTemplate jdbc;

    public OutboxClaimService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "transactionManager")
    public List<ClaimedOutboxEvent> claimBatch(
            String workerId,
            UUID leaseToken,
            int batchSize) {

        return jdbc.query("""
            WITH candidates AS (
                SELECT event_id
                FROM outbox_event
                WHERE published_at IS NULL
                  AND failed_at IS NULL
                  AND next_attempt_at <= clock_timestamp()
                  AND (
                      lease_until IS NULL
                      OR lease_until < clock_timestamp()
                  )
                ORDER BY created_at, event_id
                LIMIT ?
                FOR UPDATE SKIP LOCKED
            )
            UPDATE outbox_event AS o
            SET lease_owner = ?,
                lease_token = ?,
                lease_until = clock_timestamp()
                    + interval '30 seconds',
                attempts = o.attempts + 1
            FROM candidates AS c
            WHERE o.event_id = c.event_id
            RETURNING
                o.event_id,
                o.destination,
                o.event_type,
                o.payload,
                o.lease_token
            """,
            (rs, rowNum) -> new ClaimedOutboxEvent(
                rs.getObject("event_id", UUID.class),
                rs.getString("destination"),
                rs.getString("event_type"),
                rs.getString("payload"),
                rs.getObject("lease_token", UUID.class)
            ),
            batchSize, workerId, leaseToken
        );
    }
}
~~~

Transaction claim commit khi method trả về qua Spring proxy. **OutboxRelay** gọi service này từ bean khác để transaction kết thúc trước network send. Nếu claim và send nằm trong cùng method @Transactional, DB locks có thể bị giữ trong lúc broker chậm.

### 6.4. Relay publish và mark

~~~java
package com.example.orders.outbox;

import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class OutboxRelay {
    private final OutboxClaimService claimService;
    private final JmsTemplate outboxJmsTemplate;
    private final JdbcTemplate jdbc;

    public OutboxRelay(
            OutboxClaimService claimService,
            JmsTemplate outboxJmsTemplate,
            JdbcTemplate jdbc) {
        this.claimService = claimService;
        this.outboxJmsTemplate = outboxJmsTemplate;
        this.jdbc = jdbc;
    }

    public int publishBatch(String workerId, int batchSize) {
        UUID token = UUID.randomUUID();
        var events = claimService.claimBatch(
            workerId, token, batchSize);

        int markedPublished = 0;

        for (ClaimedOutboxEvent event : events) {
            try {
                outboxJmsTemplate.convertAndSend(
                    event.destination(),
                    event.payload(),
                    message -> {
                        message.setStringProperty(
                            "eventId", event.eventId().toString());
                        message.setStringProperty(
                            "eventType", event.eventType());
                        return message;
                    }
                );

                int updated = jdbc.update("""
                    UPDATE outbox_event
                    SET published_at = clock_timestamp(),
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_until = NULL,
                        last_error = NULL
                    WHERE event_id = ?
                      AND lease_token = ?
                      AND published_at IS NULL
                      AND failed_at IS NULL
                    """,
                    event.eventId(), event.leaseToken()
                );

                if (updated == 1) {
                    markedPublished++;
                } else {
                    // Lease đã đổi hoặc row đã được worker khác xử lý.
                    // Send trước đó có thể đã thành công; consumer phải dedupe.
                }
            } catch (Exception failure) {
                String safeError =
                    failure.getClass().getSimpleName();

                jdbc.update("""
                    UPDATE outbox_event
                    SET next_attempt_at =
                            clock_timestamp() + interval '30 seconds',
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_until = NULL,
                        last_error = ?
                    WHERE event_id = ?
                      AND lease_token = ?
                      AND published_at IS NULL
                      AND failed_at IS NULL
                    """,
                    safeError, event.eventId(), event.leaseToken()
                );
            }
        }

        return markedPublished;
    }
}
~~~

Đoạn code thể hiện cơ chế; production cần bổ sung **logger, metrics, scheduler, exponential backoff, lease renewal, xử lý lỗi DB và phân loại lỗi permanent/transient**. Mẫu catch trong code đang lên lịch retry cho mọi exception để giữ luồng minh họa ngắn; lỗi vĩnh viễn phải đi nhánh FAILED/quarantine bằng thao tác có lease token ở mục 5.3, không retry vô hạn. Nếu broker send thành công nhưng update published_at lỗi hoặc process chết, row vẫn pending/lease hết hạn và relay sẽ gửi lại **cùng eventId**. Đây là hành vi đúng của outbox at-least-once.

**Không** bắt exception rồi đánh dấu published để tránh retry. Nếu send timeout không rõ kết quả, giữ row retryable và dựa vào inbox/idempotency ở consumer.

### 6.5. published_at không phải consumer receipt

**published_at** chỉ ghi nhận relay đã hoàn tất thao tác gửi theo contract của JMS client/provider. Nó không chứng minh consumer đã nhận, commit database, gọi API thành công hoặc message chưa bị DLQ/expiry. Muốn biết consumer xử lý đến đâu, cần **consumer-side outcome/inbox/business metrics** hoặc một event xác nhận riêng.

## 7. Kiểm thử idempotency: test kết quả DB, không chỉ đếm ACK

Một test idempotent consumer phải chứng minh **business effect chỉ được commit một lần**, dù processor được gọi nhiều lần hoặc đồng thời. Kiểm tra số lần callback chạy không đủ: callback có thể chạy hai lần nhưng inbox vẫn bảo vệ một update; đó là hành vi mong muốn.

### 7.1. Test cùng event được gọi hai lần

~~~java
package com.example.orders.messaging;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class IdempotentOrderProcessorIT {
    @Autowired
    IdempotentOrderProcessor processor;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void repeatedEventChangesBusinessStateOnlyOnce() {
        String eventId = "evt-idempotency-" + java.util.UUID.randomUUID();
        String payload = """
            {
              "orderId": "order-test-1001",
              "aggregateVersion": 4
            }
            """;

        jdbc.update("""
            INSERT INTO orders(order_id, status, version)
            VALUES (?, 'PENDING', 3)
            ON CONFLICT (order_id) DO UPDATE
              SET status = 'PENDING', version = 3
            """,
            "order-test-1001"
        );

        var first = processor.process(eventId, payload);
        var second = processor.process(eventId, payload);

        assertThat(first)
            .isEqualTo(IdempotentOrderProcessor.ProcessResult.APPLIED);
        assertThat(second)
            .isEqualTo(IdempotentOrderProcessor.ProcessResult.DUPLICATE);

        Integer inboxRows = jdbc.queryForObject("""
            SELECT COUNT(*)
            FROM consumer_inbox
            WHERE consumer_name = ?
              AND event_id = ?
            """,
            Integer.class, "orders-projection-v1", eventId
        );

        Long version = jdbc.queryForObject("""
            SELECT version FROM orders WHERE order_id = ?
            """,
            Long.class, "order-test-1001"
        );

        assertThat(inboxRows).isEqualTo(1);
        assertThat(version).isEqualTo(4L);
    }
}
~~~

Test này cần schema và fixture PostgreSQL thật. Không đánh dấu test method bằng **@Transactional** nếu muốn kiểm tra mỗi lần gọi processor commit độc lập; transaction của test có thể che ranh giới commit mà listener production sẽ dùng.

### 7.2. Test cùng event đến đồng thời

Một unique constraint phải bảo vệ cả trường hợp nhiều consumer threads cùng xử lý một eventId:

~~~java
@Test
void concurrentDeliveriesApplyOneBusinessEffect() throws Exception {
    int workers = 8;
    var pool = java.util.concurrent.Executors
        .newFixedThreadPool(workers);
    var ready = new java.util.concurrent.CountDownLatch(workers);
    var start = new java.util.concurrent.CountDownLatch(1);
    var futures = new java.util.ArrayList<
        java.util.concurrent.Future<?>>();

    String eventId = "evt-concurrent-" + java.util.UUID.randomUUID();
    String payload = """
        {"orderId":"order-test-2001","aggregateVersion":9}
        """;

    jdbc.update("""
        INSERT INTO orders(order_id, status, version)
        VALUES (?, 'PENDING', 8)
        ON CONFLICT (order_id) DO UPDATE
          SET status = 'PENDING', version = 8
        """,
        "order-test-2001"
    );

    try {
        for (int i = 0; i < workers; i++) {
            futures.add(pool.submit(() -> {
                ready.countDown();
                start.await();
                processor.process(eventId, payload);
                return null;
            }));
        }

        if (!ready.await(10, java.util.concurrent.TimeUnit.SECONDS)) {
            throw new IllegalStateException("Workers did not become ready");
        }
        start.countDown();

        for (var future : futures) {
            future.get();
        }
    } finally {
        pool.shutdownNow();
    }

    Integer rows = jdbc.queryForObject("""
        SELECT COUNT(*) FROM consumer_inbox
        WHERE consumer_name = ? AND event_id = ?
        """,
        Integer.class, "orders-projection-v1", eventId
    );

    assertThat(rows).isEqualTo(1);

    Long version = jdbc.queryForObject("""
        SELECT version FROM orders WHERE order_id = ?
        """,
        Long.class, "order-test-2001"
    );
    assertThat(version).isEqualTo(9L);
}
~~~

Cần seed order-test-2001 trước khi chạy test. Mọi worker phải cùng gọi qua **Spring proxy** của processor để mỗi lời gọi có transaction riêng. Nếu test chạy trong một transaction ngoài hoặc gọi method nội bộ bỏ qua proxy, nó không còn kiểm tra đúng ranh giới transaction production.

### 7.3. Test cùng ID nhưng payload khác

~~~java
@Test
void sameEventIdWithDifferentPayloadIsRejected() {
    String eventId = "evt-conflict-" + java.util.UUID.randomUUID();

    jdbc.update("""
        INSERT INTO orders(order_id, status, version)
        VALUES (?, 'PENDING', 0)
        ON CONFLICT (order_id) DO UPDATE
          SET status = 'PENDING', version = 0
        """,
        "order-a"
    );

    processor.process(
        eventId,
        "{\"orderId\":\"order-a\",\"aggregateVersion\":1}"
    );

    org.assertj.core.api.Assertions.assertThatThrownBy(() ->
        processor.process(
            eventId,
            "{\"orderId\":\"order-b\",\"aggregateVersion\":1}"
        )
    ).isInstanceOf(
        IdempotentOrderProcessor.EventIdentityConflictException.class
    );
}
~~~

Kết quả mong đợi: inbox giữ hash ban đầu, business state không bị cập nhật bởi payload thứ hai, exception được phân loại để đưa vào quarantine/DLQ sau policy phù hợp. Không assert rằng message conflict bị ACK bình thường.

### 7.4. Test crash sau DB commit, trước JMS ACK

Đây là test quan trọng nhất của listener:

1. Gửi một message có eventId cố định.
2. Listener gọi processor; PostgreSQL commit inbox + business update.
3. Một **test-only failure hook** ném exception sau khi processor trả về nhưng trước khi listener method kết thúc.
4. Listener container rollback JMS session; broker redeliver message.
5. Lần thứ hai processor trả DUPLICATE; listener kết thúc bình thường và container commit receive.
6. Assert business update chỉ có một hiệu ứng, nhưng delivery attempt quan sát được ít nhất hai.

Failure hook chỉ dùng trong integration test, được kích hoạt đúng một lần. Không thêm một đường production có thể tự ý crash listener. Với Artemis và Classic, chạy test trên từng broker/client version mà hệ thống thực sự triển khai; không suy từ một provider rằng mọi redelivery headers/metrics của provider khác giống hệt.

## 8. Kiểm thử outbox và relay dưới lỗi

### 8.1. Atomicity: không thể có business commit thiếu outbox

Test phải tạo lỗi sau business UPDATE nhưng trước khi outbox INSERT hoàn tất, ví dụ cố tình dùng destination/event constraint không hợp lệ. Sau khi service ném exception, query bằng transaction mới:

- Business aggregate vẫn ở trạng thái trước.
- Không có outbox row cho eventId đó.
- Không có relay nào có thể publish event này.

Lặp lại với transaction commit thành công: cả business state và outbox row phải tồn tại. Đây là test **database transaction**, không cần broker chạy.

### 8.2. Relay crash sau broker send, trước published_at

Đây là cửa sổ duplicate của outbox:

~~~mermaid
sequenceDiagram
    participant R as Outbox relay
    participant DB as PostgreSQL
    participant B as JMS broker
    participant C as Idempotent consumer
    R->>DB: Claim event evt-5001
    R->>B: Send persistent evt-5001
    B-->>R: Send accepted
    Note over R,DB: Process crash trước UPDATE published_at
    Note over DB: Lease hết hạn, row vẫn pending
    R->>DB: Worker khác claim evt-5001
    R->>B: Send lại cùng eventId
    B->>C: Có thể giao một hoặc nhiều lần
    C->>DB: Inbox chỉ commit business effect một lần
~~~

Test nên có failpoint **sau khi send trả về nhưng trước update published_at**:

1. Publish eventId cố định; xác nhận broker test nhận message.
2. Dừng relay ở failpoint để row chưa mark published.
3. Chờ lease hết hạn hoặc giải phóng lease theo test harness.
4. Chạy relay lần nữa; nó gửi lại cùng eventId.
5. Cho consumer idempotent xử lý cả hai delivery.
6. Assert **một business effect**, outbox cuối cùng published và duplicate counter tăng.

Đừng xóa message đầu ở broker để làm test “đẹp”; mục tiêu là chứng minh hệ thống chịu được cả hai lần gửi.

### 8.3. Kiểm thử nhiều relay workers

Chạy ít nhất hai worker đồng thời trên cùng outbox table:

- Mỗi worker claim batch với **SKIP LOCKED**.
- Không có cùng eventId trong hai batch còn lease hiệu lực.
- Nếu worker chết, lease hết hạn và row có thể được claim lại.
- Worker cũ dùng token cũ không thể mark row đã được worker mới claim.
- Nếu worker cũ vẫn kịp gửi sau lease expiry, duplicate được consumer dedupe.

Đếm **distinct eventId đã publish** và **send attempts** riêng. Nếu chỉ assert số send attempts bằng số outbox rows, test sẽ sai khi mô phỏng retry.

### 8.4. Test broker-specific và môi trường thật

Một bộ integration test nên có hai lớp:

| Lớp | Kiểm tra | Không thay thế |
|---|---|---|
| PostgreSQL + processor test | Unique key, transaction, rollback, concurrency, payload hash | JMS delivery/redelivery |
| JMS + broker integration | Persistent send, transacted receive, redelivery, DLQ, restart | Atomicity business DB/outbox |
| Full flow test | Outbox → broker → consumer inbox → business outcome | Load, soak và failure behavior dài hạn |
| Production-safe synthetic | Đường đi thật với test identity/side effect sandbox | Kiểm thử mọi schema, tenant và payload |

Chạy integration tests trên **ActiveMQ Classic và Artemis riêng**, dùng client/API tương ứng. Boot 3 dùng **jakarta.jms**; Classic client phải là bản Jakarta-compatible nếu test cùng Spring JMS 6. Môi trường Boot 2/javax cần profile/dependency riêng. Không trộn hai namespace trong một classpath test.

## 9. Những trường hợp kiểm thử thường bị bỏ sót

| Trường hợp | Vì sao cần test | Kết quả mong đợi |
|---|---|---|
| **Producer timeout sau send** | Broker có thể đã commit | Retry giữ eventId; consumer không lặp effect |
| **Consumer rollback trước DB commit** | Không có inbox/business row đã commit | Redelivery có thể xử lý lại |
| **Crash sau DB commit trước JMS ACK** | Inbox đã tồn tại, broker giao lại | Lần sau DUPLICATE, JMS được commit |
| **Hai consumers xử lý cùng ID đồng thời** | Race insert/update | Unique key chỉ cho một transaction áp dụng |
| **Cùng ID, payload khác** | Event identity bị vi phạm | Conflict/quarantine, không silently drop |
| **Outbox transaction rollback** | DB không được phát event cho state chưa commit | Không business row, không outbox row |
| **Relay crash sau send** | Broker nhận nhưng outbox chưa mark | Retry cùng eventId, consumer dedupe |
| **Lease hết hạn khi worker cũ còn chạy** | Hai worker có thể send | Token ngăn stale update; consumer chịu duplicate |
| **Broker restart sau persistent send** | Kiểm tra persistence thật | Message còn theo broker/destination policy |
| **DLQ replay** | Operator có thể phát lại event cũ | Inbox retention còn hiệu lực |
| **Inbox cleanup rồi replay muộn** | Marker đã bị xóa | Test phải chứng minh retention policy ngăn effect lặp |
| **Out-of-order aggregate version** | Relay song song có thể reorder | Consumer phát hiện version cũ/thiếu và xử lý theo contract |
| **External API timeout không rõ** | API có thể đã thực hiện side effect | Retry cùng idempotency key hoặc reconcile |

## 10. Artemis duplicate detection và Classic audit không thay inbox

Artemis hỗ trợ cơ chế **duplicate detection** ở broker với duplicate ID property theo API/provider và cấu hình address. Nó có thể giảm duplicate messages khi producer/bridge retry trong phạm vi cache và semantics mà broker hỗ trợ. ActiveMQ Classic cũng có các cơ chế audit/duplicate suppression trong một số đường xử lý.

Nhưng broker-level duplicate detection có giới hạn:

- Phụ thuộc provider, version, cấu hình cache/window và đường message.
- Không đồng nhất một lần gọi payment API với một event đã commit trong DB.
- Không thay unique key nghiệp vụ ở consumer.
- Có thể không bao phủ replay sau retention/cache eviction, restore hoặc một đường gửi mới.
- Không làm hai resource DB và JMS trở thành một transaction nguyên tử.

**Dùng broker dedupe như lớp tối ưu**, còn inbox/business idempotency là lớp bảo vệ hiệu ứng. Không để logic nghiệp vụ phụ thuộc riêng vào property nội bộ của Artemis khi message có thể được chuyển qua Classic hoặc protocol khác.

## 11. Retention, replay và vận hành inbox/outbox

### 11.1. Inbox retention phải dài hơn replay horizon

Inbox marker cần tồn tại ít nhất trong khoảng thời gian một event còn có thể quay lại từ:

- Queue retention/persistent backlog.
- Redelivery và DLQ retention.
- Broker backup/restore.
- Outbox retry hoặc replay thủ công.
- Consumer offset/replay window của một connector khác.
- Quy trình disaster recovery có thể phục hồi message cũ.

Nếu DLQ giữ 90 ngày nhưng inbox chỉ giữ 7 ngày, replay message ngày thứ 60 có thể lặp business effect. Chọn retention theo **kịch bản replay dài nhất**, có thể dài bằng vòng đời dữ liệu nghiệp vụ nếu side effect không thể lặp.

### 11.2. Outbox retention và cleanup

Chỉ archive/xóa rows có **published_at** đã có từ trước một khoảng an toàn, và giữ đủ dữ liệu phục vụ audit/replay. Không xóa rows pending, leased hoặc FAILED chưa được operator xử lý.

Các chiến lược thường gặp:

- Partition theo created_at và archive partition cũ sau retention.
- Xóa theo batch nhỏ để tránh transaction/lock lớn.
- Giữ event metadata/hash và business correlation ở kho audit nếu payload cần được xóa vì chính sách dữ liệu.
- Có runbook cho row FAILED, lease hết hạn và publish retry quá số lần dự kiến.

### 11.3. Replay không được tạo event ID mới tùy tiện

Khi operator replay một event cũ để phục hồi, giữ **eventId/commandId ban đầu** nếu vẫn là cùng một business event. Consumer đã xử lý rồi sẽ dedupe; nếu cần chạy lại một hành động mới, hãy tạo **command mới có ID mới**, liên kết với event gốc bằng causation/correlation ID và ghi lý do nghiệp vụ.

Không sửa payload dưới eventId đã phát trước. Nếu cần correction, tạo event mới như **OrderCorrection** hoặc **PaymentReversal** theo domain contract.

### 11.4. Metrics cho inbox/outbox

Các metrics tùy chỉnh hữu ích:

| Metric | Loại | Câu hỏi |
|---|---|---|
| **outbox_pending_count** | Gauge | Còn bao nhiêu event chưa publish? |
| **outbox_oldest_pending_age_seconds** | Gauge | Event pending lâu nhất bao nhiêu? |
| **outbox_publish_attempts_total** | Counter | Relay phải thử bao nhiêu lần? |
| **outbox_lease_expired_total** | Counter | Worker/lease bị mất bao nhiêu lần? |
| **outbox_publish_failed_total** | Counter theo error class | Broker/destination/serialization đang lỗi gì? |
| **consumer_duplicate_suppressed_total** | Counter theo consumer | Có bao nhiêu delivery được inbox nhận diện là duplicate? |
| **consumer_event_identity_conflict_total** | Counter | Có eventId bị tái sử dụng với payload khác không? |
| **consumer_business_commit_total** | Counter theo outcome | Bao nhiêu hiệu ứng nghiệp vụ đã commit? |
| **consumer_dlq_total** | Counter | Bao nhiêu message bị cách ly? |

Không gắn **eventId**, **orderId** hoặc **customerId** làm Prometheus label vì cardinality rất cao và có thể lộ dữ liệu. Các ID thuộc log/trace; metric labels nên là consumer name ổn định, event type được kiểm soát, outcome và error class.

## 12. Các lỗi triển khai và cách xử lý

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Consumer xử lý hai lần sau retry | Không có inbox hoặc key không ổn định | Dùng eventId bất biến và unique constraint |
| Inbox có row nhưng business update thiếu | Commit inbox tách khỏi business transaction | Đưa cả hai vào cùng DB transaction |
| Consumer bỏ qua message khác payload | Chỉ kiểm tra eventId, không so payload hash | Phát hiện identity conflict và quarantine |
| Message bị ACK dù xử lý thất bại | Callback nuốt exception/return bình thường | Cho exception phù hợp đi ra để rollback hoặc lưu recovery bền vững |
| Outbox row tồn tại nhưng không publish | Relay lỗi, lease kẹt hoặc destination sai | Theo dõi age/lease/attempts, retry và FAILED handling |
| Outbox publish duplicate | Crash sau broker send trước published_at | Giữ eventId, inbox ở consumer |
| Hai relay cùng publish một row | Claim không có lock/lease hoặc token | SKIP LOCKED, lease expiry và fencing token |
| Outbox giữ transaction DB lâu | Send JMS nằm trong claim transaction | Claim commit trước; network send ngoài transaction |
| Event theo aggregate đến sai thứ tự | Nhiều relay workers | Sequence/version và partition/ordering policy |
| Cleanup xóa marker quá sớm | Inbox retention ngắn hơn replay window | Đồng bộ retention với DLQ/backup/replay |
| Artemis duplicate ID được coi là đủ | Nhầm broker dedupe với business effect | Giữ consumer inbox/idempotency |
| API ngoài bị gọi hai lần | DB transaction không bao trùm HTTP/payment API | Downstream idempotency key và reconciliation |

## 13. Bài lab tổng hợp

### Lab A — Delivery lặp nhưng một business effect

1. Tạo một order test và eventId cố định.
2. Gửi cùng message hai lần vào queue test.
3. Cho listener transacted xử lý cả hai.
4. Đọc inbox và business table.
5. Xác minh hai delivery attempts nhưng một inbox key và một business transition.

**Đạt:** phân biệt delivery count với business effect count.

### Lab B — Concurrent duplicate

1. Gửi nhiều bản cùng eventId vào queue.
2. Cho listener concurrency ít nhất 4.
3. Đo số callback, số duplicate suppressed và số business commits.
4. Lặp lại nhiều lần với database PostgreSQL thật.
5. Kiểm tra không có unique violation làm mất transaction hợp lệ; duplicate path phải được xử lý qua ON CONFLICT.

**Đạt:** chỉ một transaction áp dụng business effect; những transaction còn lại kết thúc như duplicate hợp lệ.

### Lab C — Crash sau DB commit trước JMS ACK

1. Dùng test-only failpoint ném exception sau processor commit.
2. Quan sát broker redelivery.
3. Xác minh inbox row vẫn có.
4. Cho lần redelivery tiếp theo xử lý thành công.
5. Đếm business updates và delivery attempts.

**Đạt:** một business effect dù message được giao lại.

### Lab D — Payload mismatch

1. Gửi eventId X với payload A.
2. Gửi eventId X với payload B.
3. Xác minh lần hai không ghi đè business state.
4. Kiểm tra error classification, retry limit và DLQ/quarantine.
5. Replay sau khi sửa theo event ID mới hoặc quy trình correction rõ ràng.

**Đạt:** duplicate hợp lệ và identity conflict không bị đánh đồng.

### Lab E — Outbox atomicity

1. Gọi OrderConfirmationService với eventId mới.
2. Kiểm tra business state và outbox row cùng xuất hiện.
3. Lặp lại với một lỗi cố ý tại bước insert outbox.
4. Kiểm tra business update rollback cùng outbox insert.
5. Xác minh relay chỉ claim rows đã commit.

**Đạt:** không có trạng thái business commit mà mất ý định publish.

### Lab F — Relay crash và lease recovery

1. Claim outbox row và publish persistent JMS message.
2. Dừng relay sau send nhưng trước mark published.
3. Chờ lease hết hạn.
4. Cho worker khác claim và gửi lại cùng eventId.
5. Xác minh consumer inbox bỏ qua duplicate và outbox cuối cùng được mark published.

**Đạt:** không mất event; chấp nhận send attempt trùng.

### Lab G — Hai relay worker và ordering

1. Chạy hai relay workers với batch size nhỏ.
2. Tạo nhiều events thuộc cùng một aggregate với version tăng dần.
3. Quan sát thứ tự send/receive.
4. Bật cơ chế partition/head-of-line nếu domain yêu cầu.
5. Xác minh consumer phát hiện version gap hoặc stale event.

**Đạt:** hiểu SKIP LOCKED bảo vệ claim, không tự bảo đảm FIFO nghiệp vụ.

### Lab H — Replay sau DLQ/backup restore

1. Xử lý thành công một event và giữ inbox marker.
2. Replay cùng eventId từ DLQ hoặc fixture backup.
3. Xác minh không lặp business effect.
4. Mô phỏng retention marker đã hết hạn trong sandbox và chứng minh rủi ro.
5. Chọn retention đủ dài trước khi cho replay production.

**Đạt:** retention inbox được quyết định theo replay horizon, không theo dung lượng bảng đơn thuần.

## 14. Checklist trước khi phát hành

- [ ] Event có **eventId/commandId ổn định**, không dùng JMSMessageID làm khóa business.
- [ ] Retry/replay giữ cùng eventId; eventId không bị tái sử dụng cho payload khác.
- [ ] Inbox có unique key theo consumer và eventId.
- [ ] Inbox marker và business DB effect commit trong **cùng database transaction**.
- [ ] Duplicate cùng payload được bỏ qua có chủ đích; payload mismatch đi quarantine/DLQ.
- [ ] Listener dùng transacted JMS session và exception không bị nuốt sai.
- [ ] Hiểu rõ DB commit và JMS ACK vẫn có failure window; inbox chịu được redelivery.
- [ ] Business state và outbox row được ghi trong cùng transaction.
- [ ] Relay claim ngắn bằng SKIP LOCKED/lease; network send diễn ra ngoài transaction claim.
- [ ] Mark published có fencing token; retry khi kết quả send chưa rõ dùng lại eventId.
- [ ] Outbox send dùng delivery mode/persistence phù hợp và xác minh broker confirmation semantics.
- [ ] Có retry/backoff/jitter, lease expiry, FAILED/quarantine và runbook.
- [ ] Ordering theo aggregate được thiết kế riêng nếu domain yêu cầu.
- [ ] Test sequential duplicate, concurrent duplicate, crash sau DB commit, relay crash sau send và payload conflict.
- [ ] Test riêng trên broker/client Classic và Artemis thực tế; không trộn javax.jms với jakarta.jms.
- [ ] Inbox/outbox retention đủ dài so với DLQ, backup restore và replay horizon.
- [ ] Metrics phân biệt attempts, duplicate suppressed, business commit, outbox pending và DLQ.
- [ ] External side effects có idempotency key/reconciliation riêng; DB inbox không được coi là transaction với HTTP API.

**Kết luận:** Kiểm thử message lặp phải chứng minh **cùng một eventId có thể được giao nhiều lần nhưng chỉ tạo một hiệu ứng nghiệp vụ đã commit**. Inbox/unique constraint bảo vệ consumer; transactional outbox gắn business commit với ý định publish; relay có lease và retry để khôi phục sau crash. Cả ba vẫn chấp nhận duplicate ở biên gửi/giao, vì vậy cần **ID ổn định, transaction đúng phạm vi, payload bất biến, idempotency ở consumer và test failure windows**. Đó là cơ sở để vận hành ActiveMQ Classic/Artemis đáng tin cậy dưới retry, reconnect, redelivery và replay.
