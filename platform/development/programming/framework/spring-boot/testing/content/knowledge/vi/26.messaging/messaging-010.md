# Thông điệp trùng, tính lũy đẳng và tác động nghiệp vụ

## 1. Một message được xử lý hai lần có thể gây thiệt hại thật

Trong module **Spring Boot - testing**, nhóm **Messaging**, một consumer nhận cùng một thông điệp nhiều lần là tình huống **bình thường cần được thiết kế và kiểm thử**, không nhất thiết là lỗi của broker.

Ví dụ dịch vụ nhận sự kiện cộng tiền vào ví:

~~~json
{
  "eventId": "10000000-0000-4000-8000-000000000001",
  "accountId": "wallet-7",
  "deltaCents": 250
}
~~~

Nếu consumer chạy `UPDATE wallets SET balance_cents = balance_cents + 250` **mỗi khi nhận một delivery**, thông điệp bị giao lại có thể làm số dư tăng **500 cents** thay vì **250 cents**. Với các nghiệp vụ khác, tác động có thể là gửi hai email, trừ kho hai lần, tạo hai đơn hàng, gọi cổng thanh toán lặp hoặc cấp quyền sử dụng sản phẩm nhiều lần.

Có ba câu hỏi tách biệt:

1. **Message delivery:** broker có thể gửi lại message khi nào, và offset/ack xác định điều gì?
2. **Idempotency:** xử lý cùng một **logical event** nhiều lần có bảo đảm tác động nghiệp vụ chỉ xảy ra một lần không?
3. **Business side effects:** có điều gì ngoài database transaction — email, API thanh toán, Kafka publish, file, cache — mà một bảng dedup đơn giản **không tự bảo vệ được**?

Bài này triển khai mô hình **at-least-once delivery + idempotent consumer**, cùng chiến lược kiểm thử trực tiếp lẫn qua embedded Kafka; kiểm tra duplicate, hai events hợp lệ giống nội dung nhưng khác ID, payload mâu thuẫn, rollback marker khi thất bại, concurrency, retry/DLT, ordering và transactional outbox.

Ví dụ chính dùng **Java 17, Spring Boot 3.5.16, Spring Kafka 3.3.x theo BOM, Spring JDBC, H2, JUnit Jupiter** và `spring-kafka-test`. Có một lớp kiểm thử trực tiếp handler/DB và một lớp **@EmbeddedKafka** gửi hai Kafka records thật với cùng `eventId`. H2 đủ để minh họa transaction và unique key; kiểm thử contention/locking như production nên dùng PostgreSQL/MySQL Testcontainers theo DB thực.

## 2. Phân biệt bản tin trùng với hai hành động hợp lệ

Một “duplicate message” phải được định nghĩa bằng **identity ổn định của logical event**, không phải chỉ so sánh JSON body hoặc account ID.

| Trường hợp | Cùng `eventId`? | Nội dung? | Xử lý đúng |
| --- | --- | --- | --- |
| Broker redeliver record sau crash/ack lỗi | Có | Cùng payload | **Không áp dụng business effect lần nữa** |
| Producer retry rồi publish trùng logical event | Có nếu producer giữ ID qua retry | Cùng payload | Bỏ qua effect đã commit |
| Người dùng nạp tiền hai lần hợp lệ | **Khác** eventId | Có thể cùng account và cùng số tiền | **Áp dụng cả hai** |
| Cùng eventId nhưng amount/account khác | Có | **Mâu thuẫn** | Báo conflict, không lặng lẽ bỏ qua |
| Hai consumer projections khác nhau dùng cùng event | Có | Cùng payload | Mỗi consumer được xử lý theo **phạm vi projection riêng** |
| Replay lịch sử sau schema migration | Có | Có thể khác event version | Cần chính sách replay/dedup riêng |
| Một event chứa nhiều items | Có | Một logical command gồm nhiều effects | Phải atomic/idempotent cho cả tập nghiệp vụ |

Một phương trình hữu ích:

\[
f(f(S,e),e)=f(S,e)
\]

Trong đó `S` là business state và `e` là logical event. Idempotent processing nghĩa là áp dụng cùng event lại **không đổi kết quả nghiệp vụ**, trong phạm vi thời hạn và hệ thống đã định nghĩa. Nó **không** có nghĩa hai event khác nhau nhưng có cùng nội dung sẽ bị gộp.

**Chọn đúng key:** `eventId` hoặc `idempotencyKey` do producer gán **một lần cho một hành động logic** và gửi lại cùng key khi retry. Kafka `topic-partition-offset` nhận diện một record trong log nhưng **không luôn là logical-event key**: producer có thể publish lại cùng sự kiện vào một offset mới. Correlation ID/request tracing ID cũng không nên mặc định là idempotency key.

Với multi-tenant hoặc nhiều consumer độc lập, key thường cần phạm vi:

~~~text
(consumer_name, tenant_id, event_id)
~~~

Nếu producer ID không ổn định hoặc khách hàng không gửi key, cần thiết kế business key riêng (orderId + transition/version, payment provider idempotency key) và phân tích xung đột thay vì hash tất cả JSON rồi tuyên bố an toàn.

## 3. Vì sao broker giao lại thông điệp?

Một số kịch bản thực tế:

~~~text
Kafka broker             Consumer                  Database
    |                        |                         |
    |---- event E ---------->|                         |
    |                        |--- BEGIN -------------->|
    |                        |--- UPDATE + marker ----->|
    |                        |--- COMMIT -------------->|
    |                        |
    |     JVM crash trước khi Kafka offset được commit
    |                        |
    |---- redeliver E ------>|                         |
    |                        |--- thấy marker E ------->|
    |                        |--- KHÔNG update lại ----->|
    |                        |--- return success -------|
    |<--- offset commit -----|                         |
~~~

Khi consumer commit database **trước** commit Kafka offset, có khoảng thời gian mà business effect đã commit nhưng Kafka vẫn có thể giao lại. Nếu commit Kafka offset **trước** database và process chết, có nguy cơ mất business effect. Không thể giải quyết sự đánh đổi này chỉ bằng một lời hứa “consumer sẽ nhận đúng một lần”.

Nguồn duplicate có thể đến từ:

- Consumer crash/restart sau DB commit nhưng trước ack/offset commit.
- Retry khi network timeout làm caller **không biết** thao tác trước có hoàn tất.
- Consumer group rebalance và offset chưa commit.
- Producer retry hoặc replay lại event với offset mới.
- DLQ/DLT replay, khôi phục sau sự cố hoặc backfill.
- Manual reprocessing từ một timestamp/offset cũ.
- Các worker song song nhận bản sao từ retry topic hoặc một integration khác.

Khác biệt giữa Kafka và RabbitMQ quan trọng:

- **Kafka:** consumer lưu/commit offset; record vẫn ở log theo retention. Offset có thể được đọc lại khi consumer restart, seek/rebalance/replay.
- **RabbitMQ:** consumer ack delivery; nếu channel/connection đóng trước ack, unacked message thường có thể được requeue/redeliver; cấu hình nack/reject/DLX ảnh hưởng đường đi.
- **SQS/queue có visibility timeout:** message có thể xuất hiện lại khi timeout hết trước lúc worker delete.

Không nên kết luận rằng broker nào “có exactly-once” thì side effect đến database hoặc API bên ngoài cũng exactly-once.

## 4. Delivery semantics, producer idempotence và Kafka transactions

| Cơ chế | Phạm vi bảo đảm điển hình | Điều vẫn cần trong app |
| --- | --- | --- |
| At-most-once | Tránh redelivery bằng cách ghi nhận trước xử lý | Có thể **mất** effect nếu crash sau ack |
| At-least-once | Retry/redelivery khi chưa xác nhận | Consumer idempotence và cleanup |
| Kafka idempotent producer | Tránh một số duplicate **do producer retry trong producer session/partition** | Dedup logical event từ publish/replay khác |
| Kafka transaction/EOS | Commit atomically Kafka output records + consumer offsets trong topology Kafka phù hợp | Không tự làm DB/email/payment atomic với Kafka |
| DB unique constraint | Chỉ một transaction có thể insert marker cho một scoped event key | Transaction bao trùm **cả marker lẫn business mutation** |
| Provider API idempotency key | Hạn chế duplicate effect ở API provider nếu provider cam kết | Giữ key ổn định và xử lý timeout/retention hợp đồng |

Kafka transactions là hữu ích cho **consume-transform-produce** trong Kafka và `read_committed` consumers, nhưng **transaction của Kafka không phải distributed transaction tự động với một database hoặc payment gateway**. Spring Kafka có cơ chế đồng bộ transaction giữa JDBC và Kafka, song có thể có commit một bên thành công còn bên kia thất bại; cần compensation/outbox/idempotence tùy mục tiêu.  

Do đó cách nghĩ an toàn là: **delivery có thể lặp, business effect phải kiểm soát lặp**. Điều này cũng áp dụng khi “exactly-once” là yêu cầu của product: cần định nghĩa “exactly once” **ở ranh giới business nào**, chứ không dừng ở cấu hình broker.

## 5. Sai lầm: SELECT rồi UPDATE mà không có unique constraint

Một implementation mong manh:

~~~java
// PHẢN VÍ DỤ - race condition nếu hai consumers cùng xử lý E.
if (!wasProcessed(event.eventId())) {
    addBalance(event.accountId(), event.deltaCents());
    markProcessed(event.eventId());
}
~~~

Hai worker có thể cùng thấy `wasProcessed=false` trước khi một bên ghi marker:

~~~text
Worker A: SELECT E -> not found
Worker B: SELECT E -> not found
Worker A: UPDATE balance +250
Worker B: UPDATE balance +250
Worker A: INSERT processed E
Worker B: INSERT processed E
~~~

Nếu không có unique constraint, cả hai được ghi. Nếu có unique constraint nhưng marker được ghi **sau** balance update, cần bảo đảm hai statements ở cùng database transaction; nếu app không dùng transaction, balance đã bị cộng trước khi insert marker thất bại.

**Nguyên tắc chính:**

1. Tạo unique key ở DB như `PRIMARY KEY(consumer_name, event_id)`.
2. **Trong cùng một transaction**, ghi marker trước rồi mới thay đổi business state.
3. Nếu marker duplicate, transaction không được thực hiện business effect.
4. Bắt `DuplicateKeyException` **bên ngoài** transaction proxy để transaction thất bại đã rollback hoàn toàn; sau đó đọc marker đã commit và so payload để quyết định “duplicate hợp lệ” hay “event ID collision”.
5. Chỉ trả listener thành công/ack sau khi transaction đã commit hoặc đã xác nhận duplicate an toàn.

Với PostgreSQL, một INSERT vi phạm unique constraint làm transaction rơi vào trạng thái aborted; bắt exception **bên trong cùng transaction rồi tiếp tục SQL** là sai. Ví dụ chính để exception đi qua `@Transactional` service proxy trước khi listener phân loại duplicate.

## 6. Đặt inbox marker vào cùng transaction với business mutation

Sơ đồ an toàn hơn:

~~~text
Consumer nhận event E
       |
       v
BEGIN database transaction
       |
       v
INSERT inbox(consumer, event_id, account_id, delta)
       |
       +-- success ----------> UPDATE balance
       |                            |
       |                            +-- success -> COMMIT
       |                            +-- failure -> ROLLBACK marker + UPDATE
       |
       +-- duplicate key ---> ROLLBACK transaction mới
                                    |
                                    v
                           Query committed marker
                                    |
                          same payload?  YES -> success/no-op
                                         NO  -> conflict/error
~~~

Nếu UPDATE business row thất bại (account không tồn tại, check constraint, deadlock, timeout), toàn bộ transaction rollback gồm **marker**. Nhờ vậy một lần retry sau khi sửa nguyên nhân có thể xử lý event, thay vì bị đánh dấu “đã xử lý” quá sớm.

Nếu marker commit thành công nhưng business effect được thực thi ở **transaction khác**, atomicity bị phá. Đây là lỗi thường gặp khi marker service có `REQUIRES_NEW` còn business service dùng `REQUIRED`: marker sống sót sau business rollback, khiến mọi retry bị skip. Không dùng REQUIRES_NEW cho marker nếu mục tiêu là **marker và business update cùng commit/rollback**.

**Một transaction chỉ bao trùm những resource thực sự thuộc transaction manager đó.** Email, HTTP payment call và việc publish message tới broker không tự được rollback khi JDBC transaction rollback.

## 7. Tối thiểu một bộ ví dụ chạy được

Chúng ta dùng “credit event” biểu diễn tăng số dư **cents** bằng số nguyên long; tránh `double`/`float` cho tiền. Application có Kafka listener nhận JSON; business effect là update `credit_accounts.balance_cents` và lưu marker vào `credit_inbox`.

Thiết kế:

- Mỗi credit event có `UUID eventId`, `String accountId`, `long deltaCents`.
- `CreditProcessor.apply(...)` là Spring service `@Transactional` ghi marker rồi cộng tiền.
- `CreditKafkaListener.onMessage(String json)` parse JSON, gọi processor **qua Spring proxy**, bắt `DuplicateKeyException` **sau khi transaction đã rollback**, kiểm tra payload cũ và no-op với duplicate đúng.
- `DeliveryObserved` là event **quan sát trong ví dụ**, được publish sau khi xử lý xong để bài test Kafka đợi cả hai deliveries; không phải cam kết delivery/sự kiện production.
- Hai loại tests: direct listener + H2 để test DB idempotence nhanh và embedded Kafka test để test đường broker → consumer → DB.

Cấu trúc thư mục:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/credit/
  CreditApplication.java
  CreditEvent.java
  CreditProcessor.java
  DeliveryObserved.java
  CreditKafkaListener.java
src/main/resources/
  application.properties
src/test/resources/
  application.properties
  schema.sql
src/test/java/com/example/credit/
  CreditListenerDatabaseTest.java
  CreditEmbeddedKafkaTest.java
~~~

Mỗi Java file dùng package `com.example.credit`. Không cần Docker trong ví dụ **embedded Kafka + H2** này; tuy nhiên nó là integration test với broker in-process chứ không chứng minh cấu hình nhiều brokers/auth/TLS của Kafka production.

## 8. Build: Java 17 / Spring Boot 3.5.16

**`settings.gradle`:**

~~~groovy
rootProject.name = 'credit-idempotency-tests'
~~~

**`build.gradle` (Groovy DSL):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-json'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
}
~~~

- Spring JDBC xử lý DB transaction và `JdbcTemplate`.
- Starter JSON cung cấp Jackson `ObjectMapper` cho JSON record.
- `spring-kafka` cung cấp `@KafkaListener`/`KafkaTemplate`.
- `spring-kafka-test` cung cấp `@EmbeddedKafka`.
- H2 dành cho nhanh/độc lập; production phải có JDBC driver và database phù hợp.
- Spring Boot BOM quản lý Spring Kafka/Apache Kafka client/Jackson versions; không pin một Kafka major khác bằng tay nếu chưa kiểm tra compatibility.

`maxParallelForks=1` chỉ giới hạn Gradle test worker JVMs **chạy đồng thời trong task này**, không tự tắt JUnit parallel, multi-module jobs hay CI shards.

**`src/main/resources/application.properties`:**

~~~properties
app.kafka.credit-topic=credit-events
spring.kafka.consumer.group-id=credit-balance-consumer
~~~

Trong production cần cấu hình `spring.kafka.bootstrap-servers`, serializers/deserializers, bảo mật và datasource theo môi trường. File trên không chứa credentials.

## 9. Test schema và các properties để chạy độc lập

**`src/test/resources/schema.sql`:**

~~~sql
CREATE TABLE IF NOT EXISTS credit_accounts (
    account_id VARCHAR(80) PRIMARY KEY,
    balance_cents BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_inbox (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    account_id VARCHAR(80) NOT NULL,
    delta_cents BIGINT NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

`PRIMARY KEY(consumer_name,event_id)` là **rào chắn concurrency cuối cùng**: hai transactions không thể cùng commit marker cho cùng scoped logical event, kể cả khi cùng lúc thấy row chưa tồn tại.

**`src/test/resources/application.properties`:**

~~~properties
spring.datasource.url=jdbc:h2:mem:credit_idempotency;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=6
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql

spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.listener.auto-startup=false
~~~

Mặc định test app đặt `listener.auto-startup=false` để **test trực tiếp** không cố kết nối `localhost:9092`. Lớp `CreditEmbeddedKafkaTest` sẽ override nó thành `true` và cấp `spring.kafka.bootstrap-servers` từ embedded broker.

`DB_CLOSE_DELAY=-1` giữ H2 trong cùng JVM; vì vậy fixtures cần cleanup rõ ràng, đặc biệt khi có nhiều Spring contexts. Đây không phải một database production. Khi thay H2 bằng PostgreSQL, nên dùng migration thực của ứng dụng và test contention/SQL dialect theo PostgreSQL.

## 10. Spring Boot app và event schema

**`src/main/java/com/example/credit/CreditApplication.java`:**

~~~java
package com.example.credit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CreditApplication {
    public static void main(String[] args) {
        SpringApplication.run(CreditApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/credit/CreditEvent.java`:**

~~~java
package com.example.credit;

import java.util.UUID;

public record CreditEvent(
        UUID eventId,
        String accountId,
        long deltaCents
) {
}
~~~

JSON sử dụng UUID string và `deltaCents` integer. Một số hệ thống sử dụng `BigDecimal` cùng currency code/scale; ví dụ chọn cents để không nhầm floating-point. Production nên validate giới hạn số tiền, currency, tenant, schema version, source signature, authorization, overflow và số dư theo hợp đồng.

### Không dùng nội dung JSON làm identity duy nhất

Hai giao dịch hợp lệ có thể có payload **giống hệt** về account/amount nhưng là hai payment khác nhau. Ngược lại cùng logical event có thể được serialize khác thứ tự JSON fields nhưng ID vẫn như cũ. Bởi vậy `eventId` phải giữ ổn định qua retry, và payload được lưu/so sánh theo **canonical business fields** của event version.

## 11. CreditProcessor: marker và cập nhật số dư atomic

**`src/main/java/com/example/credit/CreditProcessor.java`:**

~~~java
package com.example.credit;

import java.util.List;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CreditProcessor {
    private static final String CONSUMER = "credit-balance-v1";

    private final JdbcTemplate jdbc;

    public CreditProcessor(JdbcTemplate jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    @Transactional
    public void apply(CreditEvent event) {
        Objects.requireNonNull(event, "event");

        if (event.eventId() == null
                || event.accountId() == null
                || event.accountId().isBlank()
                || event.deltaCents() <= 0) {
            throw new IllegalArgumentException("Invalid credit event");
        }

        // Primary key chặn trùng trước khi business UPDATE.
        jdbc.update(
                """
                INSERT INTO credit_inbox
                  (consumer_name, event_id, account_id, delta_cents)
                VALUES (?, ?, ?, ?)
                """,
                CONSUMER,
                event.eventId().toString(),
                event.accountId(),
                event.deltaCents()
        );

        // SQL atomic UPDATE; không SELECT số dư rồi set lại.
        int changed = jdbc.update(
                """
                UPDATE credit_accounts
                SET balance_cents = balance_cents + ?
                WHERE account_id = ?
                """,
                event.deltaCents(),
                event.accountId()
        );

        if (changed != 1) {
            throw new IllegalStateException(
                    "Unknown account: " + event.accountId()
            );
        }
    }

    // Gọi sau khi transaction INSERT trùng đã rollback.
    public boolean matchesCommittedEvent(CreditEvent event) {
        List<Boolean> matches = jdbc.query(
                """
                SELECT account_id, delta_cents
                FROM credit_inbox
                WHERE consumer_name = ? AND event_id = ?
                """,
                (rs, rowNum) ->
                        event.accountId().equals(
                                rs.getString("account_id")
                        )
                        && event.deltaCents()
                                == rs.getLong("delta_cents"),
                CONSUMER,
                event.eventId().toString()
        );
        return matches.size() == 1 && matches.get(0);
    }
}
~~~

**Vì sao thiết kế này đúng?**

1. `@Transactional` trên một Spring service tạo DB transaction, và listener sẽ gọi **qua proxy**.
2. Unique marker được INSERT **trước** business UPDATE.
3. Nếu account không tồn tại, service ném unchecked `IllegalStateException`. Spring rollback cả marker lẫn mọi SQL đã thực thi trong transaction.
4. Nếu eventId trùng, database từ chối INSERT trước khi balance được cộng.
5. Query `matchesCommittedEvent` được thực hiện **sau rollback của transaction thất bại**, tránh lỗi transaction bị aborted do duplicate-key và tránh đọc state tạm chưa commit.
6. Nếu cùng ID nhưng account/amount khác, test phải báo conflict; không được coi là duplicate an toàn.

**Không làm thế này:** catch `DuplicateKeyException` **bên trong** `apply` rồi tiếp tục SQL trên cùng transaction. PostgreSQL sẽ coi transaction bị lỗi là aborted. Một số DB khác có semantics khác nhưng việc tách catch khỏi transactional proxy là chiến lược an toàn hơn.

### Giới hạn nghiệp vụ

Đây là ví dụ cộng cents không có bảo vệ overflow, currency exchange, limit, authorization hay audit immutable. Production cần xác định luật balance, account ownership, timeout/lock và schema evolution. Marker này bảo vệ **DB balance effect** trong một database transaction; không tự bảo vệ email hay API thanh toán.

## 12. Listener: phân loại APPLIED, DUPLICATE và CONFLICT

**`src/main/java/com/example/credit/DeliveryObserved.java`:**

~~~java
package com.example.credit;

import java.util.UUID;

public record DeliveryObserved(
        UUID eventId,
        String outcome
) {
}
~~~

`DeliveryObserved` là một Spring application event phục vụ **quan sát trong ví dụ/test**. Publish event trong cùng JVM không phải một durable message broker; nếu process crash, event có thể mất. Không dùng record này để giả lập transactional outbox trong production.

**`src/main/java/com/example/credit/CreditKafkaListener.java`:**

~~~java
package com.example.credit;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class CreditKafkaListener {
    private final CreditProcessor processor;
    private final ObjectMapper json;
    private final ApplicationEventPublisher events;

    public CreditKafkaListener(
            CreditProcessor processor,
            ObjectMapper json,
            ApplicationEventPublisher events
    ) {
        this.processor = processor;
        this.json = json;
        this.events = events;
    }

    @KafkaListener(topics = "${app.kafka.credit-topic}")
    public void onMessage(String payload) {
        CreditEvent event;
        try {
            event = json.readValue(payload, CreditEvent.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Invalid credit event JSON", ex
            );
        }

        try {
            processor.apply(event);
            events.publishEvent(
                    new DeliveryObserved(event.eventId(), "APPLIED")
            );
        } catch (DuplicateKeyException duplicate) {
            if (!processor.matchesCommittedEvent(event)) {
                throw new IllegalStateException(
                        "Conflicting eventId: " + event.eventId(),
                        duplicate
                );
            }
            // Success/no-op: đã xử lý đúng event này rồi.
            events.publishEvent(
                    new DeliveryObserved(event.eventId(), "DUPLICATE")
            );
        }
    }
}
~~~

### Tại sao catch ở listener?

`processor.apply(event)` là lời gọi từ một bean sang một bean `@Transactional` khác. Khi duplicate INSERT ném `DuplicateKeyException`, Spring transaction interceptor rollback **trước khi exception thoát khỏi proxy** và tới listener. Listener lúc đó có thể query committed marker bằng connection/transaction hợp lệ.

Nếu query xác nhận **eventId + payload business fields giống nhau**, handler return bình thường; broker container có thể ghi nhận delivery đó thành công theo ack mode/offset policy. Nếu cùng event ID nhưng nội dung khác, listener ném exception; lỗi cần được phân loại/đưa vào DLT hoặc alert, không retry vô hạn như lỗi mạng tạm thời.

Nếu có lỗi JSON schema/validation, handler cũng ném exception. Trong production, **poison messages không nên bị retry vô hạn**; cấu hình error handler, retryable classification, DLT và observability phù hợp.

### Một lưu ý nhỏ về việc publish DeliveryObserved

`events.publishEvent(...)` ở đây là observer đồng bộ mặc định sau khi `apply(...)` đã return/commit. Nếu về sau gắn `@Async` vào listener quan sát event, test dựa vào tín hiệu này phải đổi thành wait phù hợp. Nếu observer tự ném exception sau business commit, Kafka có thể redeliver; DB marker vẫn bảo vệ balance nhưng callback observer không tự exactly-once. Trong production nên giữ probe/metrics tách khỏi transaction contract và không để telemetry làm một delivery thành lỗi không mong muốn.

## 13. JUnit direct integration test: kiểm tra business effect không qua broker

Lớp này chạy Spring context và JDBC/H2 **thật**, nhưng **không khởi động Kafka consumer thread**; nó gọi `onMessage` trực tiếp để test cùng logic idempotence trước khi thêm broker timing. Không gắn `@Transactional` lên test class, vì nếu test-managed transaction bao quanh test, nó sẽ làm mờ ranh giới commit của `@Transactional` processor và có thể khiến một unique violation đánh dấu outer rollback-only.

**`src/test/java/com/example/credit/CreditListenerDatabaseTest.java`:**

~~~java
package com.example.credit;

import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(properties = {
        "spring.kafka.listener.auto-startup=false"
})
class CreditListenerDatabaseTest {

    @Autowired
    CreditKafkaListener listener;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ObjectMapper mapper;

    private String account;

    @BeforeEach
    void createAccount() {
        account = "acct-" + UUID.randomUUID();
        jdbc.update(
                """
                INSERT INTO credit_accounts
                  (account_id, balance_cents) VALUES (?, ?)
                """,
                account, 1_000L
        );
    }

    @AfterEach
    void removeOnlyThisTestsRows() {
        jdbc.update(
                """
                DELETE FROM credit_inbox
                WHERE account_id IN (?, ?)
                """,
                account, account + "-missing"
        );
        jdbc.update(
                """
                DELETE FROM credit_accounts
                WHERE account_id IN (?, ?)
                """,
                account, account + "-missing"
        );
    }

    private String payload(CreditEvent event)
            throws JsonProcessingException {
        return mapper.writeValueAsString(event);
    }

    private long balance(String accountId) {
        Long value = jdbc.queryForObject(
                """
                SELECT balance_cents FROM credit_accounts
                WHERE account_id = ?
                """,
                Long.class,
                accountId
        );
        return value.longValue();
    }

    private int markerCount(UUID eventId) {
        Integer found = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM credit_inbox
                WHERE consumer_name = ? AND event_id = ?
                """,
                Integer.class,
                "credit-balance-v1",
                eventId.toString()
        );
        return found.intValue();
    }

    @Test
    void sameEventTwiceChangesBalanceOnlyOnce() throws Exception {
        UUID id = UUID.randomUUID();
        String json = payload(new CreditEvent(id, account, 250L));

        listener.onMessage(json);
        listener.onMessage(json);

        assertThat(balance(account)).isEqualTo(1_250L);
        assertThat(markerCount(id)).isEqualTo(1);
    }

    @Test
    void twoDifferentEventIdsAreTwoLegitimateCredits()
            throws Exception {
        UUID first = UUID.randomUUID();
        UUID second = UUID.randomUUID();

        listener.onMessage(
                payload(new CreditEvent(first, account, 100L))
        );
        listener.onMessage(
                payload(new CreditEvent(second, account, 200L))
        );

        assertThat(balance(account)).isEqualTo(1_300L);
        assertThat(markerCount(first)).isEqualTo(1);
        assertThat(markerCount(second)).isEqualTo(1);
    }

    @Test
    void sameEventIdWithChangedAmountIsAConflict()
            throws Exception {
        UUID id = UUID.randomUUID();

        listener.onMessage(
                payload(new CreditEvent(id, account, 150L))
        );

        String conflicting = payload(
                new CreditEvent(id, account, 999L)
        );

        assertThatThrownBy(
                () -> listener.onMessage(conflicting)
        ).isInstanceOf(IllegalStateException.class)
         .hasMessageContaining("Conflicting eventId");

        assertThat(balance(account)).isEqualTo(1_150L);
        assertThat(markerCount(id)).isEqualTo(1);
    }

    @Test
    void failedBusinessUpdateRollsBackMarkerSoRetryCanWork()
            throws Exception {
        String missing = account + "-missing";
        UUID id = UUID.randomUUID();
        String json = payload(
                new CreditEvent(id, missing, 700L)
        );

        assertThatThrownBy(
                () -> listener.onMessage(json)
        ).isInstanceOf(IllegalStateException.class)
         .hasMessageContaining("Unknown account");

        assertThat(markerCount(id)).isZero();

        // Khắc phục điều kiện tạm thời rồi replay CÙNG payload.
        jdbc.update(
                """
                INSERT INTO credit_accounts
                  (account_id, balance_cents) VALUES (?, ?)
                """,
                missing, 0L
        );

        listener.onMessage(json);

        assertThat(balance(missing)).isEqualTo(700L);
        assertThat(markerCount(id)).isEqualTo(1);
    }

    @Test
    void malformedJsonNeverChangesBusinessBalance() {
        assertThatThrownBy(
                () -> listener.onMessage("{not-json")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("Invalid credit event JSON");

        assertThat(balance(account)).isEqualTo(1_000L);
    }

    @Test
    void nonPositiveDeltaIsRejectedBeforeMarker()
            throws Exception {
        UUID id = UUID.randomUUID();

        assertThatThrownBy(
                () -> listener.onMessage(
                        payload(new CreditEvent(id, account, 0L))
                )
        ).isInstanceOf(IllegalArgumentException.class);

        assertThat(balance(account)).isEqualTo(1_000L);
        assertThat(markerCount(id)).isZero();
    }
}
~~~

**Sáu test methods** đi qua JSON parsing, handler và Spring JDBC transaction thật, nhưng không phụ thuộc Kafka broker. Quan sát:

- Duplicate cùng ID/payload -> balance chỉ tăng 250, marker duy nhất 1.
- Hai events khác ID -> cả hai được cộng.
- Cùng ID nhưng amount khác -> conflict, không cộng lần hai.
- Update tới account chưa tồn tại -> transaction rollback marker; sau khi tạo account, replay nguyên event xử lý được.
- JSON malformed -> exception; balance không đổi.
- Amount không hợp lệ -> không ghi marker/effect.

**Điểm QA:** test này không gọi `@Transactional` ở class. `@AfterEach` xóa đúng account IDs của test, dùng namespace UUID nên không dọn toàn bảng và ít xung đột giữa suite. Không assert hard-code UUID ngẫu nhiên; chỉ dùng ID làm key để truy vấn marker.

Trong production, `IllegalArgumentException` cho dữ liệu không hợp lệ không tự gửi vào DLT; cần cấu hình listener error handling phù hợp. Test direct này **không** chứng minh offset/ack semantics của Kafka.

## 14. Broker-level test: publish hai Kafka records, đợi hai deliveries

Dùng `@EmbeddedKafka` để có broker thực trong JVM, với random broker port và property `spring.kafka.bootstrap-servers` được remap đúng. Việc gọi `KafkaTemplate.send(...).get()` chỉ bảo đảm producer đã nhận kết quả gửi, **không chứng minh consumer đã xử lý xong**. Do đó test dùng `DeliveryObserved` và Awaitility đợi thấy cả kết quả “APPLIED” và “DUPLICATE” **trước khi assert DB state**.

Spring Kafka 3.3 có `@EmbeddedKafka` thuộc `spring-kafka-test`; khi dùng Spring TestContext, embedded broker là thành phần context. Tài liệu khuyến nghị cân nhắc `@DirtiesContext` để tránh broker shutdown/context cache race sau test. 

**`src/test/java/com/example/credit/CreditEmbeddedKafkaTest.java`:**

~~~java
package com.example.credit;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(properties = {
        "app.kafka.credit-topic=credit-events-test",
        "spring.kafka.consumer.group-id=credit-embedded-test",
        "spring.kafka.listener.auto-startup=true"
})
@EmbeddedKafka(
        partitions = 1,
        topics = "credit-events-test",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@Import(CreditEmbeddedKafkaTest.ProbeConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class CreditEmbeddedKafkaTest {

    static class DeliveryProbe {
        private final Map<UUID, ConcurrentLinkedQueue<String>> observed =
                new ConcurrentHashMap<>();

        @EventListener
        public void onDelivery(DeliveryObserved event) {
            observed.computeIfAbsent(
                    event.eventId(),
                    ignored -> new ConcurrentLinkedQueue<>()
            ).add(event.outcome());
        }

        List<String> states(UUID id) {
            ConcurrentLinkedQueue<String> result = observed.get(id);
            return result == null ? List.of() : List.copyOf(result);
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class ProbeConfig {
        @Bean
        DeliveryProbe deliveryProbe() {
            return new DeliveryProbe();
        }
    }

    @Autowired
    KafkaTemplate<String, String> kafka;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    DeliveryProbe probe;

    private String account;

    @BeforeEach
    void createIsolatedAccount() {
        account = "kafka-" + UUID.randomUUID();
        jdbc.update(
                """
                INSERT INTO credit_accounts
                  (account_id, balance_cents) VALUES (?, ?)
                """,
                account, 1_000L
        );
    }

    @AfterEach
    void removeOwnCommittedRows() {
        jdbc.update(
                "DELETE FROM credit_inbox WHERE account_id = ?",
                account
        );
        jdbc.update(
                "DELETE FROM credit_accounts WHERE account_id = ?",
                account
        );
    }

    private long balance() {
        Long result = jdbc.queryForObject(
                """
                SELECT balance_cents FROM credit_accounts
                WHERE account_id = ?
                """,
                Long.class,
                account
        );
        return result.longValue();
    }

    @Test
    void twoKafkaDeliveriesWithSameEventIdCreditOnlyOnce()
            throws Exception {
        UUID id = UUID.randomUUID();
        String payload = mapper.writeValueAsString(
                new CreditEvent(id, account, 250L)
        );

        // Dùng cùng account key để giữ thứ tự trong một partition.
        kafka.send(
                "credit-events-test", account, payload
        ).get(10, TimeUnit.SECONDS);
        kafka.send(
                "credit-events-test", account, payload
        ).get(10, TimeUnit.SECONDS);

        // Phải thấy cả hai deliveries được xử lý, không chỉ
        // thấy số dư sau delivery đầu.
        await().atMost(Duration.ofSeconds(20))
                .untilAsserted(() -> {
                    assertThat(probe.states(id))
                            .contains("APPLIED", "DUPLICATE");
                    assertThat(balance()).isEqualTo(1_250L);
                });

        Integer markers = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM credit_inbox
                WHERE consumer_name = ? AND event_id = ?
                """,
                Integer.class,
                "credit-balance-v1",
                id.toString()
        );
        assertThat(markers).isEqualTo(1);
    }
}
~~~

Test này nhận hai Kafka **records** cùng logical event, không cần crash/rebalance thật. Nó kiểm tra **Kafka listener wiring + JSON parsing + DB idempotency + quan sát đủ hai deliveries**.

**Không khẳng định** đã kiểm thử crash đúng thời điểm Kafka offset commit; tình huống đó cần fault injection và broker/container integration riêng. `DeliveryProbe` là test-only observer, không thay cho broker/DB source of truth và không bảo đảm xử lý exactly-once cho side effects khác.

**Tại sao không dùng `Thread.sleep(1000)`?** Thời gian broker/consumer startup trên CI thay đổi. Awaitility với timeout rõ ràng đợi **điều kiện nghiệp vụ/quan sát**; nếu consumer không xử lý, test FAIL có ý nghĩa thay vì một sleep may rủi.

### Điều cần tránh trong broker test

- Không assert “đã xử lý duplicate” chỉ vì DB có marker sau lần đầu.
- Không dùng cùng topic/group/record keys giữa nhiều suites song song nếu không cô lập broker/context.
- Không phụ thuộc thứ tự lớp test; mỗi test account/event ID riêng.
- Không tắt listener rồi tưởng đã test Kafka: test direct và test broker là hai phạm vi khác nhau.
- Không gắn `@Transactional` lên test client để mong rollback business writes đã được Kafka listener thread commit.
- Nếu broker được cache giữa classes, phải quản lý lifecycle phù hợp context, không stop broker sớm trong khi listener còn active.

## 15. Kết quả dự kiến của bảy test methods

| Lớp | Test | Expected về DB/exception |
| --- | --- | --- |
| Direct | `sameEventTwiceChangesBalanceOnlyOnce` | 1000 + 250 = **1250**, marker 1 |
| Direct | `twoDifferentEventIdsAreTwoLegitimateCredits` | 1000 + 100 + 200 = **1300**, 2 markers |
| Direct | `sameEventIdWithChangedAmountIsAConflict` | Exception conflict, balance **1150** |
| Direct | `failedBusinessUpdateRollsBackMarkerSoRetryCanWork` | Lần 1 marker 0; sau tạo account, balance **700**, marker 1 |
| Direct | `malformedJsonNeverChangesBusinessBalance` | Invalid JSON, balance vẫn **1000** |
| Direct | `nonPositiveDeltaIsRejectedBeforeMarker` | Invalid input, balance vẫn **1000**, marker 0 |
| Broker | `twoKafkaDeliveriesWithSameEventIdCreditOnlyOnce` | Đã quan sát APPLIED + DUPLICATE; balance **1250**, marker 1 |

Đây là **kỳ vọng theo logic code**, không phải output JUnit thực thi đã được ghi nhận. Code không có `System.out.println` và Kafka server/Gradle logs có thể khác nhau tùy môi trường.

Nếu muốn đánh giá throughput/race cùng một event ở **hai consumer instances thật**, embedded Kafka + H2 chỉ là baseline. Cần thêm stress tests với PostgreSQL/MySQL thật, tối thiểu hai consumer workers, cạnh tranh unique key, rollback/timeout và isolation thích hợp.

## 16. Thử concurrency: unique index là trọng tâm, không phải synchronized

Một cách sửa “trùng message” sai:

~~~java
// Không an toàn trên nhiều pods hoặc nhiều JVM:
synchronized void handle(CreditEvent e) {
    if (!seenInMemory.contains(e.eventId())) {
        applyBusinessEffect(e);
        seenInMemory.add(e.eventId());
    }
}
~~~

`synchronized` chỉ khóa một object trong một JVM. Nếu có ba Kubernetes pods, mỗi pod có bộ nhớ khác nhau. Nếu process restart, `seenInMemory` bị mất. Nếu cache eviction, duplicate cũ lại được xử lý. Dùng Redis `SETNX` có thể giúp coordination nhưng phải thiết kế atomicity với DB effect và TTL; chỉ lock/cache key không tự thay một unique constraint và transaction.

**Ma trận concurrency cần test trên DB thực:**

1. Hai workers cùng INSERT marker (same scoped event ID) và cùng cố UPDATE balance.
2. Một transaction commit, transaction còn lại nhận duplicate (hoặc phải retry vì lock/deadlock).
3. Balance chỉ tăng một lần.
4. Hai events khác ID cùng account đều được apply đầy đủ (SQL atomic increment không lost update).
5. Một worker crash trong transaction: DB rollback cả marker và effect; worker còn lại hoặc retry có thể làm việc.
6. Một worker commit rồi crash trước ack: replay no-op.

Dùng `CountDownLatch`/`CyclicBarrier` để ép interleaving có kiểm soát khi test race, không đặt `Thread.sleep` để “hy vọng” hai threads trùng lúc. Đặt timeout tránh treo vô hạn. Với PostgreSQL Testcontainers, kiểm tra SQL state/unique violation/lock wait thật; H2 không đại diện mọi behavior PostgreSQL.

### Vì sao SQL atomic UPDATE?

Code này có nguy cơ lost update:

~~~java
long balance = jdbc.queryForObject(
        "SELECT balance_cents FROM credit_accounts WHERE account_id=?",
        Long.class, accountId
);
jdbc.update(
        "UPDATE credit_accounts SET balance_cents=? WHERE account_id=?",
        balance + amount, accountId
);
~~~

Hai transactions đọc cùng balance 1000 rồi ghi lần lượt 1100 và 1200: kết quả cuối có thể **1200 thay vì 1300**. Ví dụ chính dùng `SET balance_cents = balance_cents + ?`, cho database chịu trách nhiệm atomic update/locking. Idempotency key và atomic increment giải **hai bài toán khác nhau**: duplicate event và concurrent distinct events.

## 17. Đừng đánh dấu processed trước khi business success

Một lỗi nguy hiểm:

~~~text
BEGIN TX #1
  INSERT credit_inbox(eventId)       -> COMMIT
BEGIN TX #2
  UPDATE business balance            -> FAIL / ROLLBACK

Kafka retry eventId:
  thấy marker đã tồn tại -> skip
=> mất business effect vĩnh viễn.
~~~

Điều này có thể xảy ra nếu service lưu marker dùng `@Transactional(propagation=REQUIRES_NEW)` trong khi business update tham gia transaction ngoài rồi rollback. **Không dùng transaction độc lập cho marker** nếu marker có nghĩa “business effect đã commit”.

Mẫu đúng: marker và business update trong **cùng DB transaction** như `CreditProcessor.apply`. Nếu event cần tạo **nhiều rows** trong cùng database, đảm bảo tất cả nằm trong một transaction. Nếu một effect là HTTP call ngoài DB, không thể rollback HTTP call bằng JDBC transaction: cần thiết kế idempotency API/outbox/workflow riêng.

## 18. Tác động nghiệp vụ ngoài database: email, payment và publish event

Unique inbox + transaction DB bảo vệ phép update số dư ví dụ. Nó **không tự bảo vệ**:

- Gửi email/SMS/push notifications.
- Gọi payment provider, shipping API hoặc credit limit service.
- Publish downstream Kafka/RabbitMQ event.
- Ghi file/object storage hoặc invalidate cache ngoài DB.
- Gọi một microservice khác đã commit transaction của nó.

Ba thứ tự dễ gây lỗi:

| Thứ tự | Crash xảy ra sau bước nào? | Rủi ro |
| --- | --- | --- |
| Call payment trước DB commit | Payment thành công, DB rollback | Retry có thể charge lần nữa |
| DB commit marker trước send email | Process crash sau DB commit, trước send | Event bị skip khi redeliver, **email bị mất** |
| Send email trước commit marker | Email thành công, DB rollback | Redelivery có thể gửi email hai lần |

### Pattern transactional outbox

Trong **cùng transaction với business effect và inbox marker**, INSERT thêm một row vào bảng `outbox` chứa event cần gửi. Một publisher/relay riêng đọc outbox, gửi qua broker rồi mark delivered/advance. Outbox bảo đảm **sự kiện cần gửi được ghi cùng DB commit**, không bảo đảm relay không publish trùng (ví dụ gửi thành công rồi crash trước khi mark). **Consumer downstream vẫn phải idempotent.**

~~~text
DB TX:
  INSERT inbox E
  UPDATE balance +250
  INSERT outbox O (CreditApplied)
  COMMIT

Relay:
  READ outbox O
  PUBLISH O
  MARK SENT (có thể crash ở giữa)

Downstream:
  nhận O một/nhiều lần
  dùng idempotency key để chỉ áp dụng effect một lần
~~~

Với payment provider có idempotency-key API, dùng **một key ổn định theo logical payment** và tuân thủ contract retention/provider. Không tự động dùng offset Kafka hay UUID mới mỗi retry làm payment idempotency key, vì như vậy duplicate charges vẫn có thể xảy ra.

### Transaction synchronization không phải distributed ACID

`@TransactionalEventListener(AFTER_COMMIT)` có thể trì hoãn callback tới sau DB commit, tránh publish thành công trước commit. Tuy nhiên crash **sau DB commit nhưng trước callback** vẫn có thể làm event mất; nếu yêu cầu durable messaging, outbox thường thích hợp hơn. Kafka transactions không tự bao trùm external API/DB commit. 

## 19. Retry: lỗi tạm thời khác lỗi vĩnh viễn

| Loại lỗi | Ví dụ | Chính sách tham khảo |
| --- | --- | --- |
| Transient | DB connection timeout, broker/network lỗi ngắn, deadlock có thể retry | Bounded retries + backoff/jitter, giữ nguyên idempotency key |
| Business dependency tạm thời | Account chưa tạo do event đến sớm | Thử lại có giới hạn hoặc pending queue, cân nhắc event ordering |
| Conflict/payload corruption | Cùng event ID nhưng account/amount khác | Không retry vô hạn; DLT/alert, điều tra producer |
| Malformed JSON/schema | Không parse được event | DLT/parking lot và replay sau khi sửa |
| Permanent authorization | Event từ nguồn không được phép | Reject/quarantine, audit security |
| Unbounded downstream throttling | HTTP 429 | Respect retry-after, rate limit, timeout, circuit breaker |

Trong Spring Kafka có `DefaultErrorHandler` cho blocking retry/error handling và `@RetryableTopic` cho non-blocking retries/topic chain. **Không bật cả hai một cách máy móc**; biết chính xác attempt count, backoff, DLT naming, acknowledgment/offset policy và thư viện đang chạy. Spring Kafka 3.3 docs nêu **non-blocking retries không kết hợp với Kafka container transactions**; đừng dùng ví dụ `@RetryableTopic` rồi hứa có end-to-end container transaction mà chưa kiểm chứng. 

### Dead Letter Topic là gì?

DLT là nơi lưu bản tin xử lý thất bại theo policy để operator điều tra/replay. DLT **không phải** “đánh dấu business effect đã được thực hiện”. Một event trong DLT có thể đã tạo **một phần** side effects nếu code không atomic. Khi replay DLT, **giữ logical event ID**; nếu thay ID, hệ thống có thể coi nó là event mới và làm side effect lần nữa.

### Thời điểm ack

- Ack/commit offset sau khi business transaction commit hoặc duplicate được xác minh là an toàn.
- Nếu listener ném lỗi trước completion, error handler quyết định retry/DLT theo cấu hình.
- Không swallow mọi exception rồi return success; như vậy broker có thể bỏ qua một event **chưa xử lý**.
- Nếu listener async trả completion cho framework, phải hiểu đúng ack timing và lifecycle.
- Với manual acknowledgment, phải xử lý thread/ack mode đúng API; không tự viết `acknowledge()` ngay sau parse JSON rồi để business effect chạy sau.

## 20. Same eventId nhưng payload khác: phải coi là lỗi

Một implementation “dedup” chỉ dựa vào existence:

~~~java
if (inboxExists(eventId)) {
    return; // quá rộng: nuốt cả event ID collision có nội dung khác
}
~~~

Nếu producer sinh nhầm cùng ID cho hai lệnh, hoặc một event bị chỉnh sửa khi replay, một event hợp lệ sẽ bị bỏ qua âm thầm. Mẫu ví dụ lưu `account_id` và `delta_cents` cùng marker. Khi duplicate key:

- **Cùng ID + cùng business payload:** coi là redelivery của logical event, return success/no-op.
- **Cùng ID + khác business payload:** lỗi `Conflicting eventId`, cần alert/DLT.
- **Khác ID + cùng payload:** là hai events độc lập trừ khi có business key riêng bắt buộc chúng chỉ được xử lý một lần.

Production nên lưu thêm `tenantId`, `eventType`, `schemaVersion`, source, canonical payload digest hoặc một normalized business fingerprint. Tránh so raw JSON byte-for-byte khi field order, whitespace hoặc version có thể thay đổi mà semantic vẫn cùng một event.

### Khi có event versions

Nếu event v1 và v2 đại diện cùng logical event, cần quyết định cách so payload: chuyển về canonical business semantics rồi so, hoặc lưu version và reject conflict có điều kiện. Không sửa sự kiện cũ bằng cách giữ ID mà thay nghĩa tiền/số lượng mà không có migration contract rõ ràng.

## 21. Idempotency marker phải sống bao lâu?

Một `processed_events`/`credit_inbox` table tăng liên tục. Xóa marker quá sớm để tiết kiệm storage có thể làm message cũ được replay rồi business effect xảy ra lần hai.

Ví dụ:

~~~text
Ngày 1: event E được apply, marker E lưu DB.
Ngày 8: cleanup xóa marker E theo TTL 7 ngày.
Ngày 9: backfill/replay E từ Kafka archive.
Kết quả: E bị coi như mới -> balance tăng lần 2.
~~~

TTL dedup cần tối thiểu bao trùm **khoảng thời gian replay/retry thực tế mà business contract yêu cầu**. Với tiền, có thể cần giữ marker rất lâu hoặc gắn uniqueness vào immutable business ledger có retention phù hợp, thay vì TTL ngắn. Nếu vì luật lưu trữ phải xóa dữ liệu nhận dạng, cần thiết kế key bảo mật/canonical digest/ledger và chính sách xử lý replay rõ ràng.

Có thể phân vùng inbox table theo thời gian, archive theo kỳ hoặc dùng business-level uniqueness constraint, nhưng phải xác minh rằng cơ chế cleanup không phá tính lũy đẳng trong thời hạn bảo đảm.

**Idempotency không phải “exactly-once vĩnh viễn”** nếu hệ thống đã xóa thông tin nhận diện event sau một thời điểm.

## 22. Message ordering, partition key và out-of-order events

Dedup chỉ giải quyết **cùng event xuất hiện nhiều lần**. Nó không giải quyết thứ tự giữa **hai events khác nhau**:

~~~text
Event E1: order status = PAID, version=2
Event E2: order status = SHIPPED, version=3

Do retry/DLT, consumer có thể thấy E2 trước E1.
Nếu ghi status không kiểm version, replay E1
có thể đổi SHIPPED trở lại PAID.
~~~

Trong Kafka, cùng key thường có thể đi vào cùng partition, giúp giữ **thứ tự records trong một partition** cho một consumer group bình thường. Nhưng multiple producer paths, retry topics, concurrent side effects, manual replay và cross-topic delivery có thể làm thứ tự **nghiệp vụ** bị đảo. Với state machine, dùng **aggregate version** / compare-and-set / optimistic locking:

~~~sql
UPDATE orders
SET status = ?, version = ?
WHERE order_id = ? AND version = ?;
~~~

Đây là SQL **minh họa** (không thuộc schema ví dụ credit). Nếu UPDATE ảnh hưởng 0 rows, cần phân loại duplicate/older event/out-of-order/new gap. Không tự động coi mọi 0-row là success; có thể phải chờ sự kiện version trước hoặc yêu cầu reconciliation.

### Kafka partition key và tính lũy đẳng

Trong test embedded Kafka, cả hai records được gửi với **cùng account key**. Bài test chỉ có một partition, giúp quan sát APPLIED rồi DUPLICATE dễ hiểu. Khi scale nhiều partitions và consumer instances, unique DB constraint vẫn cần thiết; partition order một mình không bảo vệ duplicate publish lại trên topic khác hoặc side effects cross-resource.

## 23. Phạm vi consumer/group/tenant của inbox marker

Marker `PRIMARY KEY(consumer_name,event_id)` được chọn để projection `credit-balance-v1` có thể dedup độc lập. Nếu thêm một projection khác như fraud detection hoặc email notification, nó cần process cùng event một lần cho **projection của nó**. Không nên dùng chung một cột “global processed” cho mọi consumers khiến consumer thứ hai bị skip.

Trong hệ multi-tenant:

~~~text
tenant_id | consumer_name      | event_id
-------------------------------------------------
tenant-A  | credit-balance-v1  | E
tenant-B  | credit-balance-v1  | E
tenant-A  | audit-v1           | E
~~~

Đây là **bảng minh họa**. Khóa có thể gồm tenant ID, event type, projection version; tùy nguồn phát sinh bảo đảm uniqueness ID ở phạm vi nào. Nếu eventId được thiết kế global unique trên toàn hệ thống, vẫn cần phân biệt consumer/projection. Nếu business effect phải unique theo payment transaction ID, cần thêm business unique constraint riêng để chặn **hai event IDs khác nhau** nhưng cùng payment.

**Không thay đổi key scope sau migration mà không xử lý lịch sử.** Cùng event ID trong projection v2 có thể cần replay để xây read model mới, nhưng đó không có nghĩa được charge lại một giao dịch tiền đã được áp dụng ở ledger v1.

## 24. Kiểm thử failure injection và crash windows

Một bộ test idempotence nghiêm túc cần nhiều hơn `onMessage(E)` gọi hai lần. Ma trận:

| Điểm lỗi/cú pháp | Điều cần kiểm |
| --- | --- |
| Trước khi INSERT marker | Không có effect; retry an toàn |
| Sau INSERT marker nhưng **trước UPDATE**, trong cùng DB transaction | Rollback marker; retry vẫn áp dụng được |
| Sau UPDATE nhưng **trước COMMIT** | Rollback cả marker và effect |
| Ngay sau DB COMMIT, trước Kafka ack | Redelivery no-op; không cộng lần 2 |
| Hai threads INSERT cùng event ID | Chỉ một tx commit effect |
| Hai distinct events trên cùng account | Không lost update; tổng hai delta |
| Business effect DB commit, outbound email chưa gửi | Không được tự tuyên bố email đã gửi; cần outbox |
| Outbox publish thành công, mark sent fail | Replay outbox có thể publish trùng; downstream dedup |
| Same ID, changed account/amount | Conflict được phát hiện, không skip im lặng |
| Poison JSON/schema v2 | DLT và alert theo policy, không endless retry |
| Replay từ DLT/backup | Giữ eventId, marker retention phù hợp |
| Multi-tenant same external event key | Không cross-tenant skip |
| Parallel test suites | Dữ liệu/consumer groups/topics không đè nhau |

Test direct ở phần 13 chứng minh marker rollback cho account chưa tồn tại. Embedded test ở phần 14 chứng minh **hai Kafka deliveries cùng logical event**. Để chứng minh chính xác crash window, cần thêm test fault injection sau DB commit nhưng trước offset commit, có thể dùng kill/pause consumer/container rồi restart cùng consumer group/offset trong môi trường Testcontainers Kafka + PostgreSQL.

**Không dùng assert sau `Thread.sleep` làm bằng chứng chắc chắn đã xử lý cả hai messages.** Test broker đã dùng `DeliveryProbe` chờ hai outcomes, kết hợp DB assertions.

## 25. RabbitMQ: ack/nack cũng dẫn tới duplicate

Trong Spring AMQP/RabbitMQ, listener có thể xử lý message xong nhưng connection/channel mất trước khi broker nhận ACK. Broker có thể requeue và redeliver cùng logical message. Cấu hình `AcknowledgeMode.AUTO`/`MANUAL`, prefetch, retry interceptor, dead-letter exchange và requeue policy ảnh hưởng behavior; **không** thay được business dedup.

Một skeleton minh họa:

~~~java
@RabbitListener(queues = "credit-events")
public void onRabbitMessage(String json) {
    creditKafkaListener.onMessage(json);
}
~~~

Đây **chỉ là ví dụ adapter**, không phải file runnable của project chính: cần `spring-rabbit`, imports, queue declaration và retry/ack config. Tên method `onMessage` ở đây chứa logic chung trong demo nhưng production nên rút core business handler khỏi transport adapter để Kafka/Rabbit không phải gọi lẫn nhau theo tên.

Cùng một inbox design có thể dùng cho Rabbit, SQS, Pulsar hoặc webhook retries nếu chúng đều cung cấp **stable logical idempotency key**. Nếu delivery ID do broker tạo thay đổi qua retry, không dùng nó thay business eventId khi chưa hiểu contract.

## 26. Observability và cảnh báo cho dedup/side effects

Đừng chỉ log “message received” rồi coi đã thành công. Các metric có ý nghĩa:

- `messaging.delivery.attempts`: số lần consumer nhận record.
- `messaging.business.applied`: số logical events đã commit business effect.
- `messaging.duplicate.skipped`: số deliveries no-op do marker hợp lệ.
- `messaging.conflict.detected`: cùng key nhưng payload khác, cần điều tra producer.
- `messaging.processing.failed`: failure chưa được xác nhận an toàn.
- `messaging.dlt.count`: sự kiện chuyển DLT sau policy.
- `messaging.lag`, `processing.latency`, `db.lock.wait`, `outbox.pending`: sức khỏe hệ thống.

Định nghĩa metric phải rõ **đếm theo delivery hay logical event**. Một event nhận ba lần có thể tạo 3 attempts, 1 applied, 2 skipped. Không tính 3 applied chỉ vì listener invoked 3 lần.

Logs nên mang `eventId`, `consumerName`, tenant, correlation ID và account reference theo chính sách bảo mật, nhưng không log payment token/PII nhạy cảm. Nếu cần truy vết end-to-end, dùng trace context nhưng **trace ID không được mặc định dùng làm idempotency key**.

### Alert tránh false positives

Duplicate count tăng có thể là bình thường trong burst/rebalance, nhưng conflict tăng thường bất thường. Alert theo tỷ lệ duplicate, lag và thời gian xử lý; xác định có replay/campaign hợp lệ hay sự cố. Với DLT, phải có playbook triage/replay bảo toàn logical event ID.

## 27. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Số dư tăng 2 lần khi Kafka redeliver | Không lưu marker/business key | Unique inbox + tx atomic |
| Hai workers đều thấy “not processed” | Check-then-act race | Unique constraint; marker INSERT trước |
| Duplicate key exception mà transaction tiếp tục query fail | Catch vi phạm unique **bên trong** PostgreSQL tx | Catch ngoài transactional proxy |
| Marker tồn tại nhưng business update thất bại | Marker và effect khác transactions / marker REQUIRES_NEW | Cùng DB transaction |
| Same event ID khác payload bị bỏ qua | Chỉ kiểm marker existence | Lưu/so sánh canonical business payload |
| Hai giao dịch hợp lệ bị gộp | Key = account+amount, không có event ID riêng | Stable unique ID per logical action |
| Retry charge external API lần nữa | Không truyền stable provider idempotency key | Provider key + workflow/outbox |
| Kafka EOS nhưng DB vẫn duplicate | EOS chỉ bao trùm Kafka transactions/offsets trong phạm vi | DB inbox/business idempotency |
| Test direct PASS, broker path FAIL | Listener/group/serializer/topic config sai | @EmbeddedKafka/real broker test |
| Test thấy balance 1250 nhưng chưa xử lý duplicate thứ hai | Assert DB trước khi delivery thứ hai đến | Await hai deliveries/outcomes |
| DLT replay làm cộng tiền lần nữa | Xóa marker quá sớm hoặc thay event ID | Retention/replay contract |
| Rabbit ack bị mất nên requeue | At-least-once delivery | Idempotent consumer |
| Đồng thời hai events khác ID bị lost update | Read-modify-write không lock | SQL atomic UPDATE/optimistic lock |
| Test `@Transactional` không thấy persisted effect | Test transaction rollback/đọc sai thread | Explicit commit và query ngoài tx |
| Error handler retry malformed JSON vô hạn | Chưa phân loại permanent errors | DLT/parking lot + alert |
| @RetryableTopic + Kafka container transaction chạy không đúng | Tính năng không kết hợp trong docs | Thiết kế lại retry/tx |
| DB marker trùng nhưng email vẫn gửi hai lần | Email ngoài DB tx | Outbox + downstream/provider dedup |
| Two different projections skip each other | Dùng global event marker | Scope consumer/tenant/version |
| CI flake do topic/group chung | Các tests dùng chung broker/offset/state | Isolate topics/groups/fixture namespace |

## 28. Checklist trước khi chốt bài kiểm thử Messaging

- [ ] Đã định nghĩa logical event ID ổn định qua producer retry, redelivery và DLT replay?
- [ ] Đã phân biệt same event ID với hai events khác nhau nhưng payload giống?
- [ ] Unique constraint tồn tại **ở database**, không chỉ trong Java/cache?
- [ ] Marker INSERT và business update chạy **cùng DB transaction**?
- [ ] Duplicate-key được xử lý **sau** rollback của transaction vừa thất bại?
- [ ] Same ID + changed payload được báo conflict?
- [ ] Business failure rollback marker để replay có thể xử lý tiếp?
- [ ] Không ack/commit offset quá sớm so với DB commit?
- [ ] Không swallow unexpected exceptions và báo delivery thành công?
- [ ] Có test cùng event gọi hai lần, balance chỉ thay đổi một lần?
- [ ] Có test hai different IDs cùng account phải được cộng hai lần?
- [ ] Có test transaction rollback khi account/business mutation fail?
- [ ] Có test malformed/poison event theo retry/DLT policy?
- [ ] Có test broker thật/embedded broker ngoài direct method test?
- [ ] Async test đợi **hai deliveries** chứ không chỉ đợi effect đầu?
- [ ] Có kế hoạch test concurrent unique inserts trên DB production-like?
- [ ] Side effects ngoài DB (email/payment/Kafka publish) đã có idempotency/outbox strategy?
- [ ] Dedup retention không ngắn hơn window replay cần bảo vệ?
- [ ] Idempotency key scope đúng tenant/consumer/aggregate?
- [ ] Với out-of-order events, có version/sequence guard?
- [ ] Retry/backoff/DLT phân loại lỗi transient và permanent?
- [ ] Không coi Kafka producer idempotence/EOS là database-level exactly-once?
- [ ] Test fixtures có cleanup và không dùng shared production resources?
- [ ] Không assert ngẫu nhiên dựa vào offset/timing của CI?
- [ ] Log và metric đo APPLIED/DUPLICATE/CONFLICT theo semantics rõ?

## 29. Chạy bộ test và cách đọc kết quả

Với JDK 17+, Gradle Wrapper và dependencies có sẵn:

~~~bash
./gradlew test --tests "com.example.credit.CreditListenerDatabaseTest"
./gradlew test --tests "com.example.credit.CreditEmbeddedKafkaTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.credit.CreditListenerDatabaseTest"
.\gradlew.bat test --tests "com.example.credit.CreditEmbeddedKafkaTest"
~~~

Có **7 ca JUnit** trong hai lớp. `CreditListenerDatabaseTest` chạy với H2 và listener Kafka không tự khởi động; `CreditEmbeddedKafkaTest` khởi động embedded broker (test scope), phát hai messages trùng rồi đợi APPLIED và DUPLICATE.

**Không có stdout cố định từ code mẫu**, vì không gọi `System.out.println`. Gradle/Kafka startup logs và thời gian test thay đổi theo môi trường. Các kết quả trong bảng phần 15 là **kỳ vọng phân tích từ source code**, không phải log chạy thực tế được ghi trong lúc biên soạn. Code chưa được compile/run JUnit ở môi trường hiện tại, nên cần thực thi sau khi sao chép đầy đủ các tệp và cài Gradle Wrapper.

Bài demo chỉ bảo vệ **một phép cộng tiền trong H2 transaction**. Trước production, bổ sung transaction isolation trên DB thật, account limits, overflow guards, currency validation, event signature, multi-tenant keys, outbox và provider-side idempotency cho các external effects.

**Kết luận:** Broker có thể giao lại thông điệp; consumer đúng phải coi duplicate như một trường hợp dự kiến. Dùng **stable event ID**, **unique inbox marker + business mutation trong cùng transaction**, phân biệt duplicate hợp lệ với payload conflict, rồi **ack sau thành công hoặc no-op an toàn**. Test cần kiểm tra **tác động nghiệp vụ**, không chỉ số lần method được gọi. Với email, payment hoặc downstream messages, transaction DB không đủ: phải mở rộng ranh giới bảo đảm bằng outbox/idempotency key và kiểm thử các crash windows.

### Tài liệu chính thức

- [Apache Kafka — Delivery semantics và giới hạn exactly-once](https://kafka.apache.org/design/)
- [Spring Kafka — Transactions, DB synchronization và giới hạn commit](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — Testing Applications và @EmbeddedKafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka 3.3 — Non-Blocking Retries / @RetryableTopic và DLT](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic.html)
- [Spring Boot 3.5 — Kafka messaging](https://docs.spring.io/spring-boot/3.5/reference/messaging/kafka.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework 6.2 — Declarative transaction rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Boot 3.5.16 — JDK and Gradle requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)