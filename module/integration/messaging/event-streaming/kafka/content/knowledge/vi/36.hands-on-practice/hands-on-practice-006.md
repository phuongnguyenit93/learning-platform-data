# Mô phỏng crash giữa xử lý và commit để nhận diện bản ghi trùng

Một consumer Kafka có thể hoàn tất tác động nghiệp vụ rồi dừng đột ngột trước khi commit offset. Khi consumer khởi động lại, Kafka giao lại record vì offset của record đó chưa được xác nhận. Nếu consumer thực hiện lại tác động mà không có cơ chế chống trùng, một khoản tiền có thể bị cộng hai lần, một đơn hàng có thể được tạo hai lần hoặc một thông báo có thể được gửi lặp.

Bài thực hành này thuộc chương **Thực hành tổng hợp** của module **KAFKA**. Bạn sẽ dựng một Kafka broker chạy KRaft và PostgreSQL, viết consumer Java/Spring Kafka dùng manual acknowledgment, chủ động dừng tiến trình ở khoảng giữa transaction database và commit offset, sau đó quan sát record được giao lại. Cuối bài, bạn bổ sung Inbox/idempotency để chứng minh lần giao lại không lặp tác động nghiệp vụ.

## 1. Mục tiêu và mô hình thí nghiệm

Sau khi hoàn thành, bạn có thể:

- Phân biệt database commit với Kafka consumer offset commit.
- Giải thích vì sao crash sau khi xử lý nhưng trước khi commit offset tạo ra redelivery.
- Quan sát cùng một record được xử lý hai lần trong consumer group.
- Dùng eventId ổn định và bảng Inbox để chống tác động nghiệp vụ trùng.
- Kiểm tra offset của consumer group trước và sau khi khởi động lại.

Luồng thực nghiệm:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant K as Kafka
    participant C as Consumer
    participant D as PostgreSQL

    P->>K: Gửi PaymentRequested (offset 0)
    K->>C: Giao record
    C->>D: Ghi tác động nghiệp vụ
    D-->>C: Transaction đã commit
    Note over C: Tiến trình crash trước acknowledgment
    Note over K: Offset chưa được commit
    K->>C: Giao lại cùng record sau restart
    C->>D: Xử lý lại event
    D-->>C: Có thể tạo tác động lần hai
    C->>K: Acknowledge và commit offset
~~~

Kafka và PostgreSQL là hai hệ thống lưu trạng thái độc lập. Khi transaction PostgreSQL commit thành công nhưng consumer offset chưa commit, Kafka không biết database đã thực hiện tác động nào. Với cấu hình at-least-once, redelivery là hành vi bình thường để tránh mất record.

Trong bài lab, topic chỉ có một partition và consumer chỉ xử lý một record mỗi lần poll. Cách cô lập này giúp quan sát chính xác record và offset đang được thử nghiệm.

## 2. Chuẩn bị môi trường

Cần có:

- JDK 17 trở lên.
- Maven hoặc Maven Wrapper.
- Docker và Docker Compose.
- Một ứng dụng Spring Boot có Spring Kafka, Spring JDBC và PostgreSQL JDBC driver.

Tạo file docker-compose.yml:

~~~yaml
services:
  kafka:
    image: apache/kafka:4.1.0
    hostname: kafka
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_NUM_PARTITIONS: 1
      KAFKA_LOG_DIRS: /tmp/kraft-combined-logs
    volumes:
      - kafka-data:/tmp/kraft-combined-logs

  postgres:
    image: postgres:17
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: kafka_lab
      POSTGRES_USER: lab
      POSTGRES_PASSWORD: labpass
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  kafka-data:
  postgres-data:
~~~

Khởi động hạ tầng:

~~~bash
docker compose up -d
~~~

Tạo topic một partition:

~~~bash
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --if-not-exists \
  --topic payment.requested \
  --partitions 1 \
  --replication-factor 1
~~~

Topic có một partition và replication factor bằng 1 vì đây là lab chạy một broker. Cấu hình này đủ để học cách redelivery hoạt động; môi trường thật cần replication và mức ISR phù hợp yêu cầu dữ liệu.

Hãy dùng topic mới tạo và chưa có record trước khi bắt đầu để record thử nghiệm có offset 0. Nếu topic đã tồn tại và có dữ liệu, hãy tạo topic lab mới hoặc xóa dữ liệu lab cũ theo quy trình phù hợp; khi đó offset thực tế có thể khác 0.

## 3. Tạo cấu trúc ứng dụng

Ví dụ dùng Maven trong project đã khai báo Spring Boot parent/BOM và plugin spring-boot-maven-plugin, với các dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Ví dụ giả định package là com.example.kafkacrash. Tạo event:

~~~java
package com.example.kafkacrash;

public record PaymentRequested(
    String eventId,
    String accountId,
    long amount
) {}
~~~

eventId là định danh ổn định của sự kiện. Khi cùng một sự kiện được phát lại, producer hoặc outbox phải giữ nguyên eventId; không tạo UUID mới cho mỗi lần retry ở tầng ứng dụng.

Tạo lớp khởi động ứng dụng:

~~~java
package com.example.kafkacrash;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KafkaCrashLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(KafkaCrashLabApplication.class, args);
    }
}
~~~

Tạo file application.yml:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/kafka_lab
    username: lab
    password: labpass
  sql:
    init:
      mode: always
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: crash-lab
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        session.timeout.ms: 10000
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.kafkacrash.PaymentRequested
        spring.json.trusted.packages: com.example.kafkacrash
        spring.json.use.type.headers: false
        max.poll.records: 1
    listener:
      ack-mode: manual_immediate

app:
  topic: payment.requested
  idempotent: false
  crash-before-ack: true
~~~

Auto commit được tắt. Listener chỉ xác nhận record sau khi service xử lý xong và khoảng dừng mô phỏng crash đã kết thúc. MANUAL_IMMEDIATE yêu cầu listener gọi acknowledgment một cách tường minh; khi gọi trên consumer thread, container commit offset ngay theo chế độ này.

## 4. Chuẩn bị database để nhìn thấy tác động trùng

Tạo file src/main/resources/schema.sql:

~~~sql
CREATE TABLE IF NOT EXISTS account_balance (
    account_id VARCHAR(100) PRIMARY KEY,
    balance BIGINT NOT NULL
);

INSERT INTO account_balance(account_id, balance)
VALUES ('acct-1', 0)
ON CONFLICT (account_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS payment_effect (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(100) NOT NULL,
    account_id VARCHAR(100) NOT NULL,
    amount BIGINT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

payment_effect ghi lại mỗi lần ứng dụng thực hiện tác động. Trong lượt thử đầu tiên, bảng này cố ý không có unique constraint trên event_id để bạn thấy cùng một event có thể tạo hai tác động. processed_event sẽ được dùng ở lượt thử thứ hai để chặn xử lý lặp.

## 5. Viết service xử lý payment

Tạo PaymentService. Mỗi lần gọi apply() chạy trong transaction PostgreSQL. Khi phương thức trả về qua Spring proxy, transaction đã commit trước khi listener tiếp tục.

~~~java
package com.example.kafkacrash;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {
    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean apply(PaymentRequested event, boolean idempotent) {
        if (idempotent) {
            int inserted = jdbc.update(
                """
                INSERT INTO processed_event(event_id)
                VALUES (?)
                ON CONFLICT (event_id) DO NOTHING
                """,
                event.eventId()
            );

            if (inserted == 0) {
                return false;
            }
        }

        jdbc.update(
            """
            UPDATE account_balance
            SET balance = balance + ?
            WHERE account_id = ?
            """,
            event.amount(),
            event.accountId()
        );

        jdbc.update(
            """
            INSERT INTO payment_effect(event_id, account_id, amount)
            VALUES (?, ?, ?)
            """,
            event.eventId(),
            event.accountId(),
            event.amount()
        );

        return true;
    }
}
~~~

Khi idempotent=false, mỗi lần nhận record đều cộng tiền và thêm một dòng payment_effect. Khi idempotent=true, service chèn eventId vào processed_event trước. Chỉ lần chèn đầu tiên mới được cộng tiền và ghi payment_effect; lần giao lại gặp khóa chính đã tồn tại nên bỏ qua tác động.

Điều quan trọng là thao tác ghi processed_event và tác động nghiệp vụ nằm trong cùng transaction database. Nếu hai thao tác này không atomic, ứng dụng có thể ghi dấu đã xử lý nhưng chưa thực hiện tác động, hoặc thực hiện tác động mà không lưu được dấu chống trùng.

## 6. Tạo điểm dừng giữa database commit và Kafka acknowledgment

Tạo CrashWindow để tiến trình chờ vô hạn sau khi transaction database đã commit. Khi log xuất hiện, bạn sẽ chủ động buộc dừng tiến trình từ terminal khác.

~~~java
package com.example.kafkacrash;

import java.util.concurrent.CountDownLatch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CrashWindow {
    private static final Logger log =
        LoggerFactory.getLogger(CrashWindow.class);

    @Value("${app.crash-before-ack:false}")
    private boolean enabled;

    public void pauseIfEnabled(String eventId) throws InterruptedException {
        if (!enabled) {
            return;
        }

        log.error(
            "DB_COMMITTED_BEFORE_ACK eventId={} pid={}",
            eventId,
            ProcessHandle.current().pid()
        );

        new CountDownLatch(1).await();
    }
}
~~~

Listener gọi service trước, sau đó mới vào CrashWindow:

~~~java
package com.example.kafkacrash;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class PaymentConsumer {
    private static final Logger log =
        LoggerFactory.getLogger(PaymentConsumer.class);

    private final PaymentService paymentService;
    private final CrashWindow crashWindow;

    @Value("${app.idempotent:false}")
    private boolean idempotent;

    public PaymentConsumer(
        PaymentService paymentService,
        CrashWindow crashWindow
    ) {
        this.paymentService = paymentService;
        this.crashWindow = crashWindow;
    }

    @KafkaListener(topics = "${app.topic}")
    public void onMessage(
        PaymentRequested event,
        Acknowledgment acknowledgment
    ) throws InterruptedException {
        boolean applied = paymentService.apply(event, idempotent);

        log.info(
            "DB_TRANSACTION_FINISHED eventId={} applied={}",
            event.eventId(),
            applied
        );

        crashWindow.pauseIfEnabled(event.eventId());

        acknowledgment.acknowledge();
        log.info("OFFSET_ACK_SENT eventId={}", event.eventId());
    }
}
~~~

PaymentService là một bean riêng để lời gọi đi qua transaction proxy của Spring. Khi apply() trả về, transaction database đã hoàn tất. CrashWindow nằm sau điểm đó và trước acknowledgment. Nếu tiến trình bị dừng cưỡng bức trong khoảng này, database giữ thay đổi đã commit còn Kafka offset chưa được xác nhận.

## 7. Chạy thử lần một: quan sát duplicate

Khởi động ứng dụng với cấu hình mặc định: group crash-lab, idempotent=false và crash-before-ack=true.

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell, dùng Maven Wrapper dạng batch:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Trong PowerShell, khi log DB_COMMITTED_BEFORE_ACK xuất hiện, ghi lại PID được in trong log. Listener đang chờ và chưa gọi acknowledgment.

Mở terminal khác, gửi một record bằng console producer:

~~~bash
docker compose exec -it kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic payment.requested --property parse.key=true --property key.separator=:
~~~

Tại dấu nhắc của producer, nhập một dòng:

~~~text
evt-1001:{"eventId":"evt-1001","accountId":"acct-1","amount":100}
~~~

Consumer ghi transaction vào PostgreSQL rồi dừng ở khoảng trước acknowledgment. Kiểm tra database:

Mở PostgreSQL shell bằng lệnh docker compose exec postgres psql -U lab -d kafka_lab rồi chạy các câu SQL sau:

~~~sql
SELECT account_id, balance
FROM account_balance
WHERE account_id = 'acct-1';

SELECT event_id, COUNT(*) AS effect_count
FROM payment_effect
GROUP BY event_id;
~~~

Kết quả mong đợi ở thời điểm này: balance bằng 100 và eventId evt-1001 có một dòng payment_effect. Database đã ghi nhận tác động, nhưng consumer chưa gửi acknowledgment.

### Buộc dừng consumer

Dùng PID trong log để kết thúc cưỡng bức tiến trình Java. Trên Windows PowerShell:

~~~powershell
Stop-Process -Id 12345 -Force
~~~

Thay 12345 bằng PID số được in trong log.

Trên Linux/macOS:

~~~bash
kill -9 12345
~~~

Thay 12345 bằng PID số được in trong log.

Đây là crash mô phỏng. Không chỉ đóng terminal hoặc dừng container theo cách có thể chờ listener hoàn tất; mục tiêu là dừng tiến trình trước khi nó gọi acknowledgment. Kafka broker và PostgreSQL vẫn chạy, nên trạng thái database và offset còn được giữ.

Sau khi kill, chờ consumer group phát hiện thành viên đã rời và hoàn tất rebalance rồi mới kiểm tra lần khởi động lại. Lab đặt session.timeout.ms bằng 10 giây để thời gian phát hiện consumer mất kết nối ngắn hơn mặc định.

Khởi động lại consumer với cùng group ID nhưng tắt điểm dừng:

~~~powershell
$env:APP_CRASH_BEFORE_ACK = "false"
$env:APP_IDEMPOTENT = "false"
$env:SPRING_KAFKA_CONSUMER_GROUP_ID = "crash-lab"
.\mvnw.cmd spring-boot:run
~~~

Vì offset chưa được commit, Kafka giao lại record evt-1001. Consumer xử lý lần nữa, cộng thêm 100 rồi acknowledgment. Kiểm tra database:

~~~sql
SELECT account_id, balance
FROM account_balance
WHERE account_id = 'acct-1';

SELECT event_id, COUNT(*) AS effect_count
FROM payment_effect
GROUP BY event_id;
~~~

Kết quả mong đợi: balance bằng 200 và effect_count bằng 2. Cùng một eventId đã tạo hai tác động. Đây là ví dụ điển hình của at-least-once delivery khi consumer commit offset sau khi thực hiện side effect.

## 8. Xác nhận offset của consumer group

Kiểm tra trạng thái group:

~~~bash
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group crash-lab
~~~

Sau khi lần xử lý thứ hai acknowledgment thành công, CURRENT-OFFSET thường là 1 cho partition 0 vì record ở offset 0 đã được xử lý và offset commit biểu thị vị trí tiếp theo cần đọc. Trước lần giao lại, nếu group chưa từng commit record nào, consumer bắt đầu từ earliest do cấu hình auto-offset-reset.

Đừng nhầm CURRENT-OFFSET với offset của record vừa xử lý. Record thử nghiệm có offset 0; giá trị committed offset 1 nghĩa là consumer group đã xác nhận tiến qua record đó.

## 9. Chạy thử lần hai: thêm Inbox để chống trùng

Dừng consumer. Reset dữ liệu lab:

~~~sql
TRUNCATE TABLE payment_effect, processed_event;

UPDATE account_balance
SET balance = 0
WHERE account_id = 'acct-1';
~~~

Để không dùng offset đã commit của group cũ, chạy cùng topic với một group mới tên crash-lab-safe. Group mới chưa có offset nên auto-offset-reset=earliest đưa nó về record evt-1001 ở offset 0.

Khởi động ứng dụng với idempotent=true và crash-before-ack=true:

~~~powershell
$env:APP_CRASH_BEFORE_ACK = "true"
$env:APP_IDEMPOTENT = "true"
$env:SPRING_KAFKA_CONSUMER_GROUP_ID = "crash-lab-safe"
.\mvnw.cmd spring-boot:run
~~~

Khi log DB_COMMITTED_BEFORE_ACK xuất hiện, kiểm tra database:

~~~sql
SELECT account_id, balance
FROM account_balance
WHERE account_id = 'acct-1';

SELECT event_id, COUNT(*) AS effect_count
FROM payment_effect
GROUP BY event_id;

SELECT event_id
FROM processed_event;
~~~

Kết quả mong đợi: balance bằng 100, payment_effect có một dòng và processed_event chứa evt-1001. Transaction đã ghi cả dấu Inbox và tác động nghiệp vụ.

Buộc dừng tiến trình bằng PID trong log. Sau đó khởi động lại với cùng group crash-lab-safe và tắt crash window:

~~~powershell
$env:APP_CRASH_BEFORE_ACK = "false"
$env:APP_IDEMPOTENT = "true"
$env:SPRING_KAFKA_CONSUMER_GROUP_ID = "crash-lab-safe"
.\mvnw.cmd spring-boot:run
~~~

Kafka giao lại evt-1001 vì offset chưa được commit. Service thử insert eventId vào processed_event nhưng gặp khóa chính đã tồn tại, nhận số dòng được chèn bằng 0 và bỏ qua cập nhật balance. Listener vẫn tiếp tục acknowledgment để consumer group tiến offset.

Kiểm tra lại database. Kết quả mong đợi vẫn là balance bằng 100, effect_count bằng 1 và processed_event có một dòng. Consumer đã nhận record hai lần nhưng tác động nghiệp vụ chỉ xảy ra một lần.

## 10. So sánh hai lần chạy

| Quan sát | Không có Inbox | Có Inbox/idempotency |
|---|---:|---:|
| Số lần record được giao | 2 | 2 |
| Số lần transaction listener chạy | 2 | 2 |
| Số tác động nghiệp vụ | 2 | 1 |
| Số dòng payment_effect | 2 | 1 |
| Balance sau cùng | 200 | 100 |
| Offset sau khi acknowledgment thành công | 1 | 1 |

Inbox không ngăn Kafka giao lại record. Nó làm cho lần xử lý lặp trở nên an toàn. Đây là điểm cốt lõi: at-least-once cho phép redelivery, còn idempotency bảo đảm tác động nghiệp vụ không bị nhân đôi khi cùng event được xử lý lại.

## 11. Những điều cần kiểm soát trong hệ thống thật

### Đặt acknowledgment sau khi side effect hoàn tất

Nếu commit offset trước khi database transaction hoàn tất, crash có thể khiến Kafka không giao lại record trong khi database chưa có tác động. Với xử lý database, trình tự thường là commit transaction database trước, rồi mới acknowledge offset; Inbox xử lý trường hợp crash ở khoảng giữa hai thao tác.

### Inbox và side effect phải atomic

Không ghi eventId vào Inbox trong một transaction rồi thực hiện tác động nghiệp vụ ở transaction khác. Nếu ứng dụng crash giữa hai bước, event có thể bị đánh dấu đã xử lý nhưng tác động chưa xảy ra. Ghi dấu và cập nhật nghiệp vụ trong cùng transaction database.

### Idempotency key phải ổn định

Không dùng Kafka offset làm khóa idempotency duy nhất nếu cùng một sự kiện có thể được phát lại vào topic khác, partition khác hoặc môi trường khác. eventId nên được tạo từ nguồn phát sự kiện và giữ nguyên qua mọi lần retry. Có thể lưu thêm topic, partition và offset để phục vụ truy vết.

### Side effect ngoài database

Nếu consumer gọi HTTP sang hệ thống thanh toán hoặc gửi email, transaction PostgreSQL không thể tự rollback tác động của dịch vụ ngoài. Hãy truyền eventId làm idempotency key nếu dịch vụ đích hỗ trợ. Nếu không, cần thiết kế trạng thái xử lý, outbox hoặc quy trình đối soát phù hợp; không giả định @Transactional bao trùm được network call.

### Thứ tự và concurrency

Lab dùng một partition và concurrency bằng 1. Trong ứng dụng nhiều partition, các record khác có thể được xử lý đồng thời. Inbox cần có khóa duy nhất phù hợp và transaction isolation đủ để hai consumer không cùng áp dụng một eventId. Nếu nhiều event khác nhau cập nhật cùng một tài khoản, cần xem xét thứ tự nghiệp vụ, khóa dòng hoặc optimistic locking.

### Kafka transaction không tự bao gồm database

Kafka transactions có thể kết hợp việc đọc và ghi Kafka với commit offset theo transaction khi dùng consume-transform-produce. Chúng không tự biến transaction Kafka và transaction PostgreSQL thành một transaction nguyên tử. Khi tác động đích nằm trong database, Inbox hoặc mô hình phối hợp tương ứng vẫn cần thiết.

## 12. Bài tập mở rộng

1. Gửi hai event khác nhau cho cùng accountId và xác minh balance được cập nhật theo đúng tổng amount.
2. Gửi lại cùng eventId nhưng thay đổi amount. Xác định contract nên xử lý dữ liệu mâu thuẫn này thế nào; không âm thầm áp dụng lần hai.
3. Thêm cột payload_hash vào processed_event để phát hiện cùng eventId nhưng payload khác.
4. Tạo hai consumer instance cùng group và kiểm tra cách Kafka phân phối partition. Giải thích vì sao một partition chỉ được gán cho một consumer trong cùng group tại một thời điểm.
5. Thay acknowledgment bằng commit tự động trong một nhánh thử nghiệm, quan sát rủi ro mất tác động khi offset được commit trước database.
6. Thử lỗi database trước commit và xác nhận transaction rollback; sau đó quan sát Kafka redelivery.
7. Thiết kế Transactional Outbox cho producer và Inbox cho consumer để xây dựng luồng phát/nhận event có thể phục hồi.

## 13. Checklist hoàn thành

- [ ] Kafka chạy ở KRaft mode và topic payment.requested có một partition.
- [ ] Consumer dùng group ID cố định, enable-auto-commit=false và manual_immediate acknowledgment.
- [ ] Database transaction hoàn tất trước khi listener acknowledge.
- [ ] Đã buộc dừng tiến trình sau log DB_COMMITTED_BEFORE_ACK.
- [ ] Khi khởi động lại cùng group, record cũ được giao lại.
- [ ] Không có Inbox: balance tăng hai lần và payment_effect có hai dòng.
- [ ] Có Inbox: record vẫn được giao lại nhưng balance chỉ tăng một lần.
- [ ] Đã xác nhận committed offset tiến từ record offset 0 sang CURRENT-OFFSET 1.
- [ ] Đã giải thích vì sao Kafka offset và database transaction không nguyên tử với nhau.

Thực hành này cho thấy crash giữa database commit và Kafka offset commit có thể tạo duplicate dù producer chỉ phát một event. Consumer không nên dựa vào giả định mỗi record chỉ được giao một lần. Hãy thiết kế tác động nghiệp vụ idempotent, lưu eventId trong Inbox cùng transaction với side effect và chỉ acknowledge sau khi transaction hoàn tất.
