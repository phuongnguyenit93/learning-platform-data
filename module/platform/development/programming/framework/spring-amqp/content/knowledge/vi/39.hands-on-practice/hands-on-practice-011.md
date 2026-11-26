# Mô phỏng broker/consumer gián đoạn và kiểm chứng phục hồi

Một hệ thống dùng **Spring AMQP** không thể được coi là đáng tin cậy chỉ vì `RabbitTemplate.convertAndSend(...)` không ném exception, hoặc một `@RabbitListener` đã chạy thành công trong điều kiện mạng bình thường. Ở production, RabbitMQ có thể restart, connection/channel bị đóng trong lúc publish, consumer bị kill sau khi database commit nhưng **trước ACK**, hoặc một message bị giao lại sau khi ứng dụng reconnect. Phục hồi an toàn nghĩa là hệ thống **không bỏ sót ý định xử lý**, không thực hiện trùng tác dụng nghiệp vụ và có thể quan sát những event còn chờ.

Bài thực hành tổng hợp này thuộc module **SPRING_AMQP**: tích hợp RabbitMQ với `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding; định tuyến message, xác nhận giao nhận, retry, dead-letter, giao dịch và quan sát hệ thống để xây xử lý bất đồng bộ đáng tin cậy.

Chúng ta sẽ dựng **một môi trường thử nghiệm biệt lập** gồm RabbitMQ, PostgreSQL và một ứng dụng Spring Boot. Thay vì chỉ viết test giả lập trả về `IOException`, bài dùng thao tác **dừng/khởi động broker**, **dừng/khởi động listener** và **kết thúc đột ngột JVM sau DB commit nhưng trước ACK**. Mỗi tình huống có giả thuyết, thao tác fault injection, chỉ số cần đo và điều kiện PASS/FAIL rõ ràng.

> **Phạm vi an toàn:** các lệnh `docker compose stop/kill/down` và fault injection trong bài **chỉ chạy với container của lab**, không chạy trên RabbitMQ, database hoặc service production. Tài khoản/mật khẩu minh họa chỉ dùng ở localhost, không mở RabbitMQ Management ra Internet.

## 1. Sau bài học phải chứng minh được điều gì?

| Mã | Bất biến cần kiểm chứng | Cơ chế |
|---|---|---|
| **I1** | API đã ghi nhận event vào DB thì **ý định gửi vẫn tồn tại** khi RabbitMQ down | Transactional outbox |
| **I2** | Chỉ đánh dấu outbox là gửi xong sau khi có publisher confirm phù hợp, đồng thời kiểm tra returned message | Correlated confirms + mandatory returns |
| **I3** | Message đã tới queue nhưng chưa ACK vẫn có cơ hội được xử lý sau consumer restart | Durable queue, persistent message, manual ACK, redelivery |
| **I4** | Consumer đã DB commit nhưng chưa ACK có thể xử lý lại cùng event **mà không tạo business effect lần hai** | Inbox/unique constraint trong cùng DB transaction |
| **I5** | Message lỗi vĩnh viễn không quay vòng `requeue` vô hạn | Reject/NACK không requeue, dead-letter/parking |
| **I6** | Khi broker phục hồi, listener và publisher tiếp tục hoạt động mà không cần xóa queue hay restart toàn hệ thống trong kịch bản thông thường | Spring AMQP connection/listener recovery |
| **I7** | Có thể phân biệt “event đang chờ gửi”, “đã được broker xác nhận”, “đã được xử lý nghiệp vụ” và “đang ở DLQ” | Outbox, inbox/business table, broker metrics |

**Không khẳng định exactly-once delivery.** Thông thường RabbitMQ với ACK/confirm cho phép thiết kế hướng tới **at-least-once**. Event vẫn có thể được publish hoặc deliver nhiều lần ở một số cửa sổ lỗi; mục tiêu của lab là **exactly-once business effect trong database minh họa**, thông qua unique key và transaction.

### 1.1. Kiến trúc bài lab

~~~mermaid
flowchart LR
    HTTP["POST /lab/events/{eventId}"] --> DB["PostgreSQL"]
    DB --> OUT["lab_outbox (PENDING)"]
    OUT --> RELAY["@Scheduled OutboxRelay"]
    RELAY --> RT["RabbitTemplate + confirms"]
    RT --> X["lab.orders.x"]
    X -->|"orders.created"| Q["lab.orders.q<br/>durable"]
    Q --> L["@RabbitListener<br/>manual ACK"]
    L --> TX["BusinessService @Transactional"]
    TX --> INBOX["lab_processed"]
    TX --> EFFECT["lab_business_effect"]
    L -->|"ACK sau commit"| Q
    L -->|"reject/requeue=false"| DLX["lab.parking.x"]
    DLX --> PARK["lab.parking.q"]
~~~

Lab dùng **một** Spring Boot instance để dễ kiểm soát; API, relay và consumer ở cùng process nhưng xử lý trên các luồng khác nhau. Điều này rất hữu ích để tạo tình huống **cả relay và consumer có thể bị ngắt giữa hai thao tác**. Trong production, việc chạy nhiều instance cần thêm lease/claim cho outbox và cơ chế phối hợp không trùng công việc.

## 2. Hiểu các cửa sổ lỗi trước khi chạy lệnh

### 2.1. Publisher confirm không phải consumer ACK

~~~mermaid
sequenceDiagram
    participant API as HTTP/API
    participant DB as PostgreSQL
    participant R as Outbox relay
    participant B as RabbitMQ
    participant C as Consumer
    API->>DB: COMMIT event vào outbox
    R->>B: Publish persistent message
    B-->>R: Confirm ACK
    R->>DB: Đánh dấu outbox.sent_at
    B->>C: Delivery
    C->>DB: COMMIT business effect + inbox
    C-->>B: Consumer basicAck
~~~

**Hai xác nhận khác nhau:**

- **Publisher confirm**: broker xác nhận publish theo cấu hình/guarantee tương ứng; không chứng minh consumer đã xử lý.
- **Consumer ACK**: consumer xác nhận delivery đã được xử lý; không phải transaction nguyên tử giữa RabbitMQ và PostgreSQL.

### 2.2. Vì sao phải dùng outbox và inbox?

Giả sử service đã commit đơn hàng nhưng RabbitMQ chưa sẵn sàng. Nếu API chỉ `convertAndSend` rồi ném lỗi, ta phải biết có thể trả response gì và lưu ý định gửi ở đâu. Outbox giải quyết bằng cách **ghi ý định gửi vào database trong cùng transaction với dữ liệu nguồn**.

Ở phía nhận, nếu DB commit thành công nhưng JVM chết trước `basicAck`, broker sẽ coi delivery chưa xác nhận và **có thể giao lại** sau khi connection đóng. Inbox dùng `eventId` làm khóa duy nhất để lần nhận lại không áp dụng tác dụng nghiệp vụ lần hai.

~~~text
Relay crash sau broker confirm nhưng trước outbox SENT
    -> event còn PENDING, có thể publish lại.

Consumer crash sau DB COMMIT nhưng trước RabbitMQ ACK
    -> broker có thể redeliver cùng event.

Inbox(eventId UNIQUE) và business effect trong một transaction
    -> xử lý lặp vẫn an toàn ở tầng database.
~~~

**Quan trọng:** giải pháp minh họa bảo vệ một transaction trong **cùng PostgreSQL**. Nếu consumer còn gửi email, gọi cổng thanh toán hoặc HTTP API khác, cần idempotency key của bên thứ ba hoặc một outbox/workflow riêng; unique key trong DB không tự rollback tác dụng ngoài DB.

## 3. Yêu cầu môi trường và giới hạn của lab

Bạn cần:

- JDK **17 trở lên** và Maven tương thích với Spring Boot được chọn.
- Docker Engine + Docker Compose v2, đủ quyền chạy container.
- Spring Boot 3.x với `spring-boot-starter-amqp`, `spring-boot-starter-web` và `spring-boot-starter-jdbc`; bài dùng các API Spring AMQP 0-9-1 phổ biến ở dòng 3.x.
- Khả năng gửi HTTP request (ví dụ `curl.exe` trên PowerShell hoặc `curl` trên Linux/macOS).
- Dung lượng đĩa đủ cho hai volumes Docker của RabbitMQ và PostgreSQL.

Trong ví dụ POM bên dưới dùng **Spring Boot 3.5.0** để minh họa bộ API nhất quán. Khi áp dụng thật, chọn **bản vá còn được hỗ trợ** tương thích với môi trường, thay vì giữ nguyên một version chỉ vì xuất hiện trong bài.

### 3.1. Cấu trúc dự án minh họa

~~~text
rabbit-recovery-lab/
  pom.xml
  compose.yaml
  src/main/java/com/example/recovery/
    RecoveryLabApplication.java
    RabbitTopology.java
    EventIntakeService.java
    OutboxRelay.java
    BusinessService.java
    LabFaultSwitch.java
    OrdersListener.java
    LabController.java
  src/main/resources/
    application.yml
    schema.sql
~~~

**Định hướng tái lập:** các đoạn mã ở phần tiếp theo được viết thành từng file tương ứng. Tất cả class đặt trong package `com.example.recovery`. Phần test fault injection có thể cố ý kết thúc JVM và làm Maven báo lỗi; đó là **kết quả được chờ đợi** của một kịch bản, không phải bằng chứng build sai.

## 4. Khởi động RabbitMQ và PostgreSQL bằng Docker Compose

File `compose.yaml`:

~~~yaml
services:
  rabbitmq:
    image: rabbitmq:4-management
    hostname: rabbitmq-lab
    environment:
      RABBITMQ_DEFAULT_USER: lab
      RABBITMQ_DEFAULT_PASS: lab-only-password
    ports:
      - "127.0.0.1:5672:5672"
      - "127.0.0.1:15672:15672"
    volumes:
      - rabbitmq-lab-data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 5s
      retries: 12

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: recoverylab
      POSTGRES_USER: lab
      POSTGRES_PASSWORD: lab-only-password
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - postgres-lab-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lab -d recoverylab"]
      interval: 5s
      timeout: 3s
      retries: 20

volumes:
  rabbitmq-lab-data:
  postgres-lab-data:
~~~

Khởi động:

~~~bash
docker compose up -d
docker compose ps
~~~

Sau khi healthcheck ổn định, RabbitMQ Management UI ở `http://127.0.0.1:15672`, đăng nhập bằng **lab / lab-only-password**. Các cổng được bind vào **loopback**, không xuất bản toàn mạng. Nếu máy đã dùng cổng 5432/5672/15672, đổi host-side port và cập nhật cấu hình Spring tương ứng.

**Lưu ý persistence:** `docker compose stop` và `docker compose start` giữ lại volumes và dữ liệu. `docker compose down` mặc định không xóa named volumes, nhưng **`docker compose down -v` sẽ xóa dữ liệu lab**. Không dùng `down -v` khi còn muốn đối chiếu kết quả giữa các lần chạy.

### 4.1. Kiểm tra broker thực tế trước khi fault injection

~~~bash
docker compose exec rabbitmq rabbitmq-diagnostics -s listeners
docker compose exec rabbitmq rabbitmqctl status
docker compose exec postgres pg_isready -U lab -d recoverylab
~~~

Kết quả cần thấy: RabbitMQ nhận kết nối AMQP ở cổng cấu hình và Management UI hoạt động; PostgreSQL đã sẵn sàng. Nếu broker chưa healthy, **không** kết luận Spring AMQP recovery lỗi chỉ vì một test gửi sớm hơn thời điểm broker sẵn sàng.

## 5. Khai báo ứng dụng Spring Boot

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>rabbit-recovery-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-amqp</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
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
        <dependency>
            <groupId>org.springframework.amqp</groupId>
            <artifactId>spring-rabbit-test</artifactId>
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
~~~

Dependency `spring-rabbit-test` ở scope test là tùy chọn hỗ trợ mở rộng bài thực hành thành integration tests. Lab chính dùng Spring Boot và Docker Compose; **không cần thêm RabbitMQ Stream Protocol hoặc AMQP 1.0 client**.

### 5.2. application.yml

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
  datasource:
    url: jdbc:postgresql://127.0.0.1:5432/recoverylab
    username: lab
    password: lab-only-password
  sql:
    init:
      mode: always
  rabbitmq:
    host: 127.0.0.1
    port: 5672
    username: lab
    password: lab-only-password
    virtual-host: /
    connection-timeout: 3s
    requested-heartbeat: 20s
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      type: simple
      simple:
        acknowledge-mode: manual
        concurrency: 1
        max-concurrency: 1
        prefetch: 1
        default-requeue-rejected: false

lab:
  outbox:
    poll-ms: 1000
~~~

**Lý do cố tình đặt concurrency=1 và prefetch=1:** việc quan sát “message nào đang chờ ACK” dễ hơn khi chưa có nhiều delivery in-flight. Sau khi PASS, có thể tăng số consumer để chứng minh idempotency dưới concurrency. Với `acknowledge-mode: manual`, **listener phải gọi ACK/NACK rõ ràng**; cấu hình `default-requeue-rejected` không thay thế trách nhiệm ACK của code.

Chú ý phần này:

- `publisher-confirm-type: correlated`: kết quả publish được gắn với `CorrelationData`.
- `publisher-returns: true` và `mandatory: true`: phát hiện exchange nhận publish nhưng message **không route được tới queue**.
- `connection-timeout` là timeout kết nối, **khác** timeout chờ publisher confirm.
- `requested-heartbeat` giúp phát hiện connection không còn hoạt động; không phải một cam kết phục hồi trong đúng 20 giây.
- `server.shutdown: graceful` dùng khi process được dừng bình thường. Lệnh fault injection `Runtime.halt` ở phần sau **cố ý bỏ qua graceful shutdown**.

Tài khoản demo ở đây chỉ dành cho máy local. Với triển khai thực, mật khẩu phải lấy từ secret manager/environment, dùng TLS, phân quyền theo virtual host và không public RabbitMQ Management UI.

### 5.3. schema.sql

~~~sql
-- Ý định publish: một hàng cho một eventId.
CREATE TABLE IF NOT EXISTS lab_outbox (
    event_id VARCHAR(64) PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Inbox: đánh dấu event đã xử lý, cùng transaction với business effect.
CREATE TABLE IF NOT EXISTS lab_processed (
    event_id VARCHAR(64) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Tác dụng nghiệp vụ minh họa: một event chỉ tạo một hàng.
CREATE TABLE IF NOT EXISTS lab_business_effect (
    event_id VARCHAR(64) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS lab_outbox_ready_idx
    ON lab_outbox (next_attempt_at, created_at)
    WHERE sent_at IS NULL;
~~~

Các `CREATE TABLE IF NOT EXISTS` giúp restart app không xóa bảng và làm lại từ đầu. Đây là schema dành cho **PostgreSQL**; không thể copy nguyên `ON CONFLICT DO NOTHING`/`TIMESTAMPTZ` sang mọi database.

Nếu business thực tế còn ghi `orders` hay `invoices`, thao tác cập nhật business table và ghi inbox phải được bao trong **cùng DB transaction**. Ở lab, bảng `lab_business_effect` đại diện cho tác dụng đó.

## 6. Spring AMQP topology: exchange, queue, binding và parking

File `RabbitTopology.java`:

~~~java
package com.example.recovery;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitTopology {
    public static final String EVENTS_EXCHANGE = "lab.orders.x";
    public static final String ORDERS_QUEUE = "lab.orders.q";
    public static final String ROUTING_KEY = "orders.created";
    public static final String PARKING_EXCHANGE = "lab.parking.x";
    public static final String PARKING_QUEUE = "lab.parking.q";
    public static final String PARKING_KEY = "orders.failed";

    @Bean
    DirectExchange labOrdersExchange() {
        return new DirectExchange(EVENTS_EXCHANGE, true, false);
    }

    @Bean
    DirectExchange labParkingExchange() {
        return new DirectExchange(PARKING_EXCHANGE, true, false);
    }

    @Bean
    Queue labOrdersQueue() {
        return QueueBuilder.durable(ORDERS_QUEUE)
                .deadLetterExchange(PARKING_EXCHANGE)
                .deadLetterRoutingKey(PARKING_KEY)
                .build();
    }

    @Bean
    Queue labParkingQueue() {
        return QueueBuilder.durable(PARKING_QUEUE).build();
    }

    @Bean
    Binding labOrdersBinding(
            @Qualifier("labOrdersQueue") Queue queue,
            @Qualifier("labOrdersExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange)
                .with(ROUTING_KEY);
    }

    @Bean
    Binding labParkingBinding(
            @Qualifier("labParkingQueue") Queue queue,
            @Qualifier("labParkingExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange)
                .with(PARKING_KEY);
    }
}
~~~

Khi RabbitMQ đã sẵn sàng, `RabbitAdmin` do Spring Boot tạo có thể khai báo những `Queue`, `Exchange` và `Binding` beans này. Với broker restart, **durable topology được lưu bền vững** nếu broker và storage hoạt động đúng; cũng cần quan sát Spring AMQP listener tự reconnect và đăng ký lại.

**Lưu ý:** `durable queue` và `persistent message` là hai thuộc tính khác nhau. Đây là bài lab nên sử dụng cả hai, cộng với publisher confirms. Trong production cần đánh giá loại queue (classic/quorum), replication, ổ đĩa, recovery/failover và chính sách durability theo SLO.

## 7. Tạo Spring Boot app và API ghi ý định gửi

File `RecoveryLabApplication.java`:

~~~java
package com.example.recovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class RecoveryLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RecoveryLabApplication.class, args);
    }
}
~~~

File `EventIntakeService.java`:

~~~java
package com.example.recovery;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EventIntakeService {
    private final JdbcTemplate jdbc;

    public EventIntakeService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void enqueue(String eventId) {
        jdbc.update("""
                INSERT INTO lab_outbox(event_id)
                VALUES (?)
                ON CONFLICT (event_id) DO NOTHING
                """, eventId);
    }
}
~~~

API `enqueue` **chỉ ghi ý định vào DB**; nó không đợi broker. Do đó, khi RabbitMQ bị dừng, một request mới vẫn có thể được ghi nhận nếu PostgreSQL và ứng dụng còn hoạt động. Cụm “API đã chấp nhận request” trong bài nghĩa là **DB transaction đã commit**; chưa có nghĩa message đã đến broker hoặc consumer xử lý xong.

Với nghiệp vụ thực, việc thay đổi đơn hàng và `INSERT INTO lab_outbox` phải nằm trong **cùng transaction**; dùng hai transaction riêng sẽ mở cửa sổ “DB đã thay đổi nhưng không có event”.

## 8. Outbox relay: chỉ xóa trạng thái PENDING sau publisher confirm

File `OutboxRelay.java`:

~~~java
package com.example.recovery;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OutboxRelay {
    private static final Logger log =
            LoggerFactory.getLogger(OutboxRelay.class);

    private final JdbcTemplate jdbc;
    private final RabbitTemplate template;

    public OutboxRelay(JdbcTemplate jdbc, RabbitTemplate template) {
        this.jdbc = jdbc;
        this.template = template;
    }

    @Scheduled(fixedDelayString = "${lab.outbox.poll-ms:1000}")
    public void relayPending() {
        // Lab chỉ có một relay process.
        // Production nhiều instances cần claim/lease và SKIP LOCKED.
        List<String> ids = jdbc.queryForList("""
                SELECT event_id FROM lab_outbox
                WHERE sent_at IS NULL
                  AND next_attempt_at <= now()
                ORDER BY created_at
                LIMIT 10
                """, String.class);

        for (String id : ids) {
            try {
                publishAndAwaitConfirm(id);
                jdbc.update("""
                        UPDATE lab_outbox
                        SET sent_at = now()
                        WHERE event_id = ? AND sent_at IS NULL
                        """, id);
                log.info("OUTBOX_SENT eventId={}", id);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            } catch (Exception ex) {
                log.warn("OUTBOX_RETRY eventId={} cause={}",
                        id, ex.toString());
                jdbc.update("""
                        UPDATE lab_outbox
                        SET attempts = attempts + 1,
                            next_attempt_at = now() + INTERVAL '5 seconds'
                        WHERE event_id = ? AND sent_at IS NULL
                        """, id);
            }
        }
    }

    private void publishAndAwaitConfirm(String id) throws Exception {
        MessageProperties props = new MessageProperties();
        props.setMessageId(id);
        props.setContentType(MessageProperties.CONTENT_TYPE_TEXT_PLAIN);
        props.setContentEncoding(StandardCharsets.UTF_8.name());
        props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);

        Message message = new Message(
                id.getBytes(StandardCharsets.UTF_8), props);
        CorrelationData attempt =
                new CorrelationData(UUID.randomUUID().toString());

        template.send(
                RabbitTopology.EVENTS_EXCHANGE,
                RabbitTopology.ROUTING_KEY,
                message,
                attempt);

        CorrelationData.Confirm confirm =
                attempt.getFuture().get(5, TimeUnit.SECONDS);

        if (!confirm.isAck() || attempt.getReturned() != null) {
            throw new IllegalStateException(
                    "publish NACK hoặc không route được eventId=" + id);
        }
    }
}
~~~

Điều quan trọng nằm ở **thứ tự**:

1. Ghi outbox trước.
2. `RabbitTemplate.send` với message ID ổn định.
3. Chờ `CorrelationData` xác nhận, đồng thời kiểm tra `getReturned()` (khi `mandatory` và returns đã bật).
4. **Sau đó** mới cập nhật `sent_at`.

Nếu connection đứt khi chưa nhận confirm, relay **không thể khẳng định broker có nhận message hay chưa**. Trong ví dụ, nó giữ outbox PENDING và thử lại sau 5 giây. Điều đó có thể tạo **publish trùng**; đây là lý do consumer phải idempotent.

**Ranh giới giữa demo và production:**

- Lab dùng **một instance** và một scheduler. Production có nhiều pods/threads cần claim/lease (ví dụ transaction với `FOR UPDATE SKIP LOCKED`, lease timeout hoặc job coordinator) để giảm gửi trùng.
- `INTERVAL '5 seconds'` chỉ là backoff cố định để dễ quan sát; production thường dùng exponential backoff, jitter, retry limits và cảnh báo event bị kẹt.
- Nếu database lỗi **sau khi confirm nhưng trước khi cập nhật `sent_at`**, lần sau vẫn có thể publish lại. Đây là failure window bình thường của outbox; đừng đánh dấu `SENT` trước confirm để “xóa” duplicate bằng cách đánh đổi nguy cơ mất event.
- Publisher confirms chỉ có tác dụng khi ConnectionFactory/template đã cấu hình tương ứng. Khi chuyển sang broker/API khác, phải định nghĩa lại điều kiện “accepted”.

## 9. Consumer inbox: transaction nghiệp vụ và manual ACK

File `BusinessService.java`:

~~~java
package com.example.recovery;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BusinessService {
    private final JdbcTemplate jdbc;

    public BusinessService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean applyOnce(String eventId) {
        int inserted = jdbc.update("""
                INSERT INTO lab_processed(event_id)
                VALUES (?)
                ON CONFLICT (event_id) DO NOTHING
                """, eventId);

        if (inserted == 0) {
            // Event đã được xử lý và commit trước đó.
            return false;
        }

        jdbc.update("""
                INSERT INTO lab_business_effect(event_id)
                VALUES (?)
                """, eventId);
        return true;
        // Transaction commit khi method hoàn tất qua Spring proxy.
    }
}
~~~

Hai thao tác `INSERT INTO lab_processed` và `INSERT INTO lab_business_effect` cùng chạy trong **một PostgreSQL transaction** do `@Transactional` bao quanh. Nếu insert business thất bại, row inbox cũng rollback. Nếu event đã có trong inbox, method trả `false` và **không thực hiện business effect lại**.

**Không chuyển `@Transactional` từ service sang một method được gọi nội bộ bằng `this.applyOnce(...)`** rồi mặc định Spring proxy sẽ có hiệu lực. Ở đây listener gọi một bean `BusinessService` khác, nên transaction proxy được áp dụng đúng theo cấu hình Spring.

### 9.1. Fault switch: tạo hai lỗi có chủ đích

File `LabFaultSwitch.java`:

~~~java
package com.example.recovery;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class LabFaultSwitch {
    private final AtomicBoolean crashAfterCommit = new AtomicBoolean(false);
    private final AtomicBoolean rejectBeforeCommit = new AtomicBoolean(false);

    public void armCrashAfterCommit() {
        crashAfterCommit.set(true);
    }

    public void armRejectBeforeCommit() {
        rejectBeforeCommit.set(true);
    }

    public boolean takeCrashAfterCommit() {
        return crashAfterCommit.getAndSet(false);
    }

    public boolean takeRejectBeforeCommit() {
        return rejectBeforeCommit.getAndSet(false);
    }
}
~~~

Hai cờ tồn tại **trong RAM của JVM**. `take...()` chỉ kích hoạt một lần; sau restart, cờ được tạo lại với giá trị `false`. Nhờ đó, message redeliver sau crash sẽ không lặp lại fault injection vô hạn.

### 9.2. Manual ACK sau khi DB đã commit

File `OrdersListener.java`:

~~~java
package com.example.recovery;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import com.rabbitmq.client.Channel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersListener {
    private static final Logger log =
            LoggerFactory.getLogger(OrdersListener.class);

    private final BusinessService businessService;
    private final LabFaultSwitch faults;

    public OrdersListener(
            BusinessService businessService, LabFaultSwitch faults) {
        this.businessService = businessService;
        this.faults = faults;
    }

    @RabbitListener(
            id = "labOrdersListener",
            queues = RabbitTopology.ORDERS_QUEUE,
            ackMode = "MANUAL",
            concurrency = "1")
    public void consume(Message message, Channel channel)
            throws IOException {

        long tag = message.getMessageProperties().getDeliveryTag();
        String id = new String(
                message.getBody(), StandardCharsets.UTF_8);

        try {
            if (!id.matches("[A-Za-z0-9_-]{1,64}")) {
                throw new IllegalArgumentException("invalid eventId");
            }

            if (faults.takeRejectBeforeCommit()) {
                throw new IllegalArgumentException(
                        "LAB injected permanent business error");
            }

            boolean applied = businessService.applyOnce(id);
            log.info("DB_COMMITTED eventId={} applied={}", id, applied);

            if (faults.takeCrashAfterCommit()) {
                log.error("LAB_CRASH_AFTER_COMMIT eventId={}", id);
                System.out.flush();
                System.err.flush();
                Runtime.getRuntime().halt(137); // CHỈ TRONG LAB!
            }
        } catch (RuntimeException error) {
            log.warn("REJECT eventId={} error={}", id, error.toString());
            channel.basicReject(tag, false); // Không requeue; vào DLX.
            return;
        }

        channel.basicAck(tag, false);
        log.info("ACKED eventId={}", id);
    }
}
~~~

**Luồng xử lý an toàn:**

1. Lấy `deliveryTag` trên **đúng channel của delivery**.
2. Parse/validate event.
3. Gọi `BusinessService.applyOnce` qua bean riêng; DB commit **trước khi method trả về**.
4. Nếu fault switch bật, JVM bị kết thúc **trước `basicAck`**.
5. Nếu không lỗi, `channel.basicAck(tag,false)` xác nhận delivery.
6. Lỗi validation/business sẽ `basicReject(tag,false)` để chuyển vào DLX/parking, không tạo requeue loop.

**Vì sao không bắt mọi Exception rồi ACK?** Nếu DB rollback mà listener ACK, event có thể mất tác dụng nghiệp vụ. Còn nếu listener NACK `requeue=true` không có backoff đối với lỗi vĩnh viễn, cùng message có thể tạo vòng lặp nóng. Trong lab, ta **park** lỗi chưa xử lý; production cần phân loại lỗi tạm thời và dùng retry hữu hạn/backoff phù hợp.

**Lưu ý về kết nối:** `basicAck` hoặc `basicReject` có thể thất bại do channel đã đóng. Khi xảy ra, delivery có thể được RabbitMQ giao lại theo semantics của broker. Không thử ACK trên một channel mới bằng delivery tag của channel cũ; delivery tag có **phạm vi channel**.

### 9.3. Vì sao Runtime.halt khác System.exit?

`Runtime.getRuntime().halt(137)` chấm dứt JVM một cách đột ngột, **không chạy shutdown hooks** hay graceful shutdown bình thường. Đây là cách cố ý tạo sự cố “DB commit xong nhưng broker chưa nhận ACK”. `System.exit` có thể kích hoạt shutdown hooks nên hành vi timing có thể khác.

Chỉ giữ fault hook này trong **mã lab được cách ly**. Không triển khai endpoint kích hoạt `halt` lên production. Ở test thực tế có thể thay bằng kiểm soát container process/network mà không cài cơ chế kill trực tiếp vào mã nghiệp vụ.

## 10. API để điều khiển consumer và fault injection

File `LabController.java`:

~~~java
package com.example.recovery;

import java.util.Map;
import java.util.Objects;
import org.springframework.amqp.rabbit.listener.MessageListenerContainer;
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lab")
public class LabController {
    private final EventIntakeService intake;
    private final LabFaultSwitch faults;
    private final RabbitListenerEndpointRegistry registry;
    private final JdbcTemplate jdbc;

    public LabController(
            EventIntakeService intake,
            LabFaultSwitch faults,
            RabbitListenerEndpointRegistry registry,
            JdbcTemplate jdbc) {
        this.intake = intake;
        this.faults = faults;
        this.registry = registry;
        this.jdbc = jdbc;
    }

    @PostMapping("/events/{eventId}")
    public ResponseEntity<Map<String, String>> enqueue(
            @PathVariable String eventId) {
        if (!eventId.matches("[A-Za-z0-9_-]{1,64}")) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "invalid eventId"));
        }
        intake.enqueue(eventId);
        return ResponseEntity.accepted()
                .body(Map.of(
                        "eventId", eventId,
                        "state", "PERSISTED_TO_OUTBOX"));
    }

    @PostMapping("/consumer/pause")
    public Map<String, Object> pause() {
        var container = listener();
        container.stop();
        return Map.of("consumerRunning", container.isRunning());
    }

    @PostMapping("/consumer/resume")
    public Map<String, Object> resume() {
        var container = listener();
        container.start();
        return Map.of("consumerRunning", container.isRunning());
    }

    @PostMapping("/faults/crash-after-commit/arm")
    public Map<String, String> armCrash() {
        faults.armCrashAfterCommit();
        return Map.of("fault", "CRASH_AFTER_COMMIT_ARMED");
    }

    @PostMapping("/faults/reject-next/arm")
    public Map<String, String> armReject() {
        faults.armRejectBeforeCommit();
        return Map.of("fault", "REJECT_NEXT_ARMED");
    }

    @GetMapping("/status")
    public Map<String, Integer> status() {
        return Map.of(
                "outboxPending", count(
                        "SELECT count(*) FROM lab_outbox WHERE sent_at IS NULL"),
                "outboxSent", count(
                        "SELECT count(*) FROM lab_outbox WHERE sent_at IS NOT NULL"),
                "processed", count("SELECT count(*) FROM lab_processed"),
                "businessEffects", count(
                        "SELECT count(*) FROM lab_business_effect"));
    }

    private int count(String sql) {
        return jdbc.queryForObject(sql, Integer.class);
    }

    private MessageListenerContainer listener() {
        return Objects.requireNonNull(
                registry.getListenerContainer("labOrdersListener"),
                "Listener container chưa được đăng ký");
    }
}
~~~

`/lab/status` phản ánh các **bảng PostgreSQL**. Nó không phải RabbitMQ queue metrics. Để xác nhận `ready`, `unacked`, consumer count hoặc parking queue, cần dùng Management UI/CLI của broker như phần sau.

Các endpoint `/lab/consumer/pause` và `/lab/consumer/resume` dừng/khởi động **Spring listener container**, không xóa queue. `stop()` là đường dừng do framework quản lý, có thể chờ tác vụ đang xử lý; đây **không phải** mô phỏng crash cứng. Fault `crash-after-commit` mới mô phỏng tiến trình biến mất không ACK.

**Bảo mật:** các endpoint này **không có authentication** vì chỉ chạy trên máy cá nhân trong lab. Không mở cổng ứng dụng ra Internet hoặc đưa những endpoint này vào code production. Chúng có khả năng làm gián đoạn service và thậm chí kết thúc JVM.

## 11. Khởi động và chạy bài test cơ sở

Ở thư mục dự án, khởi động hai container nếu chưa chạy:

~~~bash
docker compose up -d
docker compose ps
~~~

Khởi động ứng dụng Spring Boot **trên máy host**, không phải bên trong Compose:

~~~bash
mvn spring-boot:run
~~~

Ứng dụng cần kết nối PostgreSQL ở `127.0.0.1:5432` và RabbitMQ ở `127.0.0.1:5672`; Spring Boot sẽ tạo bảng từ `schema.sql` và hạ tầng RabbitMQ sẽ khai báo topology. Nếu bạn chọn chạy **ứng dụng trong Docker**, hostname phải đổi từ `127.0.0.1` sang tên service Compose tương ứng (`rabbitmq`, `postgres`); localhost trong container không trỏ về container khác.

Mở một terminal khác:

~~~bash
# PowerShell: gọi curl.exe để tránh alias "curl" của Windows PowerShell.
curl.exe -s -X POST http://127.0.0.1:8080/lab/events/baseline-001
curl.exe -s http://127.0.0.1:8080/lab/status
~~~

Sau khi relay và listener hoàn tất, dự kiến:

~~~json
{
  "outboxPending": 0,
  "outboxSent": 1,
  "processed": 1,
  "businessEffects": 1
}
~~~

Số trên là cho **một lần chạy với database trống**; nếu bạn đã tạo nhiều event thì các giá trị là tổng tích lũy và sẽ khác. API trả `202 Accepted` lúc outbox commit, **không phải** lúc business effect hoàn tất. Nếu gọi status quá sớm, bạn có thể thấy `outboxPending=1` hoặc `outboxSent=1` nhưng `businessEffects=0`; chờ trạng thái cuối thay vì giả định đồng bộ.

Kiểm tra broker:

~~~bash
docker compose exec rabbitmq rabbitmqctl list_queues \
  -p / name messages_ready messages_unacknowledged consumers
~~~

Với các terminal chạy PowerShell, lệnh trên có thể nhập **một dòng** nếu ký tự xuống dòng `\` không được shell của bạn hỗ trợ:

~~~powershell
docker compose exec rabbitmq rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers
~~~

Thông thường `lab.orders.q` có `messages_ready=0` và `messages_unacknowledged=0` sau khi xử lý thành công; `consumers=1` khi listener đang chạy. `lab.parking.q` trống. Log ứng dụng nên có:

~~~text
OUTBOX_SENT eventId=baseline-001
DB_COMMITTED eventId=baseline-001 applied=true
ACKED eventId=baseline-001
~~~

**Không dựa vào thứ tự của hai dòng log `OUTBOX_SENT` và `DB_COMMITTED`**. RabbitMQ có thể giao message cho listener ngay sau publish, trước khi relay kịp ghi `sent_at` vào database. Cả hai đường chạy song song; thứ tự đúng phải được xác minh bằng hợp đồng outbox, publisher confirm và DB transaction.

### 11.1. Kiểm chứng một event không tạo business effect hai lần

Gửi lại cùng `eventId`:

~~~bash
curl.exe -s -X POST http://127.0.0.1:8080/lab/events/baseline-001
~~~

`INSERT ... ON CONFLICT DO NOTHING` ở intake không tạo outbox row mới, nên **không tạo publish attempt mới**. Kiểm tra `businessEffects` vẫn là 1.

Nếu cần mô phỏng **delivery trùng thật** thay vì API idempotent, dùng fault case “crash sau commit trước ACK” ở phần 14. Test đó buộc broker có cơ hội redeliver cùng message, và outbox có thể tự publish lại nếu chưa được đánh dấu `SENT`.

## 12. Case A — Consumer tạm dừng, message còn ở queue

**Mục tiêu:** chứng minh message không biến mất chỉ vì một consumer không còn chạy, và khi consumer quay lại, backlog được xử lý.

**Giả thuyết:** khi `labOrdersListener` dừng, outbox relay vẫn publish được vào RabbitMQ. Queue bền vững giữ message ở trạng thái `ready`; sau `resume`, listener nhận và ACK từng message.

### 12.1. Thao tác

Đảm bảo không còn event đang chờ xử lý từ bài trước. Trong terminal thứ hai:

~~~bash
curl.exe -s -X POST http://127.0.0.1:8080/lab/consumer/pause

curl.exe -s -X POST http://127.0.0.1:8080/lab/events/paused-001
curl.exe -s -X POST http://127.0.0.1:8080/lab/events/paused-002

curl.exe -s http://127.0.0.1:8080/lab/status
docker compose exec rabbitmq rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers
~~~

Chờ relay publish xong rồi quan sát:

- `lab_outbox` có hai event mới với `sent_at` khác NULL.
- `lab_business_effect` **chưa** có các event `paused-001`, `paused-002`.
- `lab.orders.q` có khoảng **2 ready messages**, `consumers=0` (nếu chỉ có listener của lab).

Khởi động lại consumer:

~~~bash
curl.exe -s -X POST http://127.0.0.1:8080/lab/consumer/resume
curl.exe -s http://127.0.0.1:8080/lab/status
~~~

Kiểm tra `lab.orders.q` trở về 0 ready/0 unacked, và `lab_business_effect` tăng thêm **chính xác 2**. Nếu vừa resume xong mà status chưa cập nhật, hãy chờ có giới hạn rồi kiểm tra lại.

### 12.2. Điều kiện PASS/FAIL

| Quan sát | PASS | FAIL cần điều tra |
|---|---|---|
| Khi pause | `consumers=0`, các message đã confirm vẫn ready | Message biến mất khỏi queue hoặc vẫn có consumer ngoài ý muốn |
| Sau resume | Listener chạy lại, queue dần trống | Container không start/recover, queue không đúng binding |
| DB state | Mỗi event có một business row | Thiếu event hoặc có duplicate business effect |
| Log/metrics | Không có retry storm, không có DLQ bất ngờ | Requeue liên tục hoặc conversion failure |

**Giới hạn test:** `container.stop()` là graceful stop, không tương đương OS kill hoặc mạng bị mất. Muốn kiểm chứng redelivery của **unacked** message sau crash, dùng case C ở phần 14.

## 13. Case B — RabbitMQ dừng trong khi API vẫn nhận event

**Mục tiêu:** xác nhận khi broker mất kết nối, event vẫn được giữ ở **transactional outbox** và tự được chuyển đi sau khi RabbitMQ khởi động lại.

**Giả thuyết:** HTTP request có thể thành công vì chỉ ghi PostgreSQL; scheduled relay sẽ gặp lỗi hoặc timeout khi publish, để `sent_at` ở NULL và thử lại có backoff. Sau khi broker quay lại, Spring AMQP khôi phục connection và listener, relay nhận publisher confirm rồi đánh dấu outbox đã gửi.

### 13.1. Dừng RabbitMQ có kiểm soát

Trong lúc ứng dụng Spring vẫn chạy:

~~~bash
docker compose stop rabbitmq
docker compose ps
~~~

Chỉ dừng **service `rabbitmq` của Compose lab**. PostgreSQL phải tiếp tục healthy. Sau đó tạo hai event:

~~~bash
curl.exe -s -X POST http://127.0.0.1:8080/lab/events/outage-001
curl.exe -s -X POST http://127.0.0.1:8080/lab/events/outage-002
curl.exe -s http://127.0.0.1:8080/lab/status
~~~

API dự kiến trả **202 Accepted** cho cả hai request. Trong database, các event này có row ở `lab_outbox` nhưng chưa có `sent_at`. Relay có thể ghi log:

~~~text
OUTBOX_RETRY eventId=outage-001 cause=...
OUTBOX_RETRY eventId=outage-002 cause=...
RabbitMQ connection lost / connection refused ...
~~~

**Đừng kết luận ứng dụng phải trả HTTP 503 vì broker đang dừng.** Trong kiến trúc outbox, endpoint nhận event chỉ cần DB commit. Nhưng nếu PostgreSQL cũng down, endpoint phải báo lỗi; nó **không thể xác nhận một ý định chưa lưu bền vững**.

Kiểm tra row trực tiếp, khi broker vẫn tắt:

~~~bash
docker compose exec postgres psql -U lab -d recoverylab \
  -c "SELECT event_id, attempts, sent_at FROM lab_outbox WHERE event_id LIKE 'outage-%' ORDER BY event_id;"
~~~

Với PowerShell dùng một dòng:

~~~powershell
docker compose exec postgres psql -U lab -d recoverylab -c "SELECT event_id, attempts, sent_at FROM lab_outbox WHERE event_id LIKE 'outage-%' ORDER BY event_id;"
~~~

Kỳ vọng `sent_at` của hai event là **NULL** trong thời gian broker down. `attempts` có thể lớn hơn 0, phụ thuộc bạn chờ bao lâu. Kiểm tra `outboxPending` là số tổng; nếu còn event khác chưa gửi thì không nhất thiết bằng 2.

### 13.2. Khôi phục broker và quan sát Spring AMQP reconnect

~~~bash
docker compose start rabbitmq
docker compose ps
docker compose exec rabbitmq rabbitmq-diagnostics -q ping
~~~

Theo dõi ứng dụng và chạy lại:

~~~bash
curl.exe -s http://127.0.0.1:8080/lab/status
docker compose exec rabbitmq rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers
~~~

Chờ đủ lâu cho lịch retry (5 giây mỗi lần thử trong demo), kết quả cần thấy:

- `outage-001` và `outage-002` có `sent_at` khác NULL.
- Bảng `lab_processed` và `lab_business_effect` có **mỗi event đúng một row**.
- `lab.orders.q` trở về trạng thái không backlog nếu downstream còn khỏe.
- Listener đã đăng ký lại (`consumers=1`) và relay tiếp tục gửi message mà **không cần xóa queue hoặc restart app**.

Trên broker có thể thấy connection/channel cũ biến mất và connection/channel mới được tạo. Đó là dấu hiệu **reconnection**, không phải lỗi nếu không kéo theo message bị mất.

### 13.3. Phân biệt planned stop và crash

`docker compose stop rabbitmq` gửi signal để container dừng theo quy trình bình thường. Muốn thử **broker chết đột ngột** trong lab:

~~~bash
# Chỉ dùng khi đã xác nhận container và volume là của lab.
docker compose kill rabbitmq
docker compose start rabbitmq
~~~

Một lần kill broker sau khi queue/message đã được ghi bền vững có thể kiểm tra recovery khác với stop có kiểm soát. Tuy nhiên **không được suy từ một lần test đơn node rằng đã kiểm chứng quorum failover hoặc khả năng không mất dữ liệu dưới mọi kiểu đứt nguồn**. Với yêu cầu HA, cần thêm cluster nhiều node, quorum queues và kịch bản mất leader/partition đúng topology.

### 13.4. Điều kiện PASS/FAIL

| Bước | PASS | FAIL |
|---|---|---|
| Broker down, API ghi event | Có row outbox mới, `sent_at=NULL` | API trả thành công nhưng không lưu DB |
| Relay thử publish | Ghi lỗi/timeout, giữ event PENDING | Đánh dấu `sent_at` khi chưa có confirm |
| Broker start | Connection/listener hồi phục | Chỉ chạy tiếp khi restart toàn bộ ứng dụng |
| Sau hồi phục | Hai event có đúng một business effect mỗi event | Mất event hoặc DB áp dụng trùng |
| Theo dõi | Confirm, retry, queue lag được quan sát | Không biết event nào còn pending |

**Ghi nhận thực nghiệm:** thời gian phục hồi = từ lúc broker healthy đến khi `outboxPending` của hai event về 0 và business table ghi đủ. Tránh chỉ ghi “đã tự phục hồi” mà không có số đo.

## 14. Case C — JVM chết sau DB COMMIT nhưng trước consumer ACK

Đây là **thử nghiệm quan trọng nhất** của bài: tạo ra một *failure window* khiến RabbitMQ không biết consumer đã hoàn tất DB transaction. Nếu hệ thống chỉ kiểm thử case broker down, rủi ro **duplicate business effect** vẫn chưa được chứng minh là đã kiểm soát.

### 14.1. Tiền điều kiện

Trước khi bật fault, bảo đảm:

1. RabbitMQ và PostgreSQL khỏe.
2. Listener đang chạy, `lab.orders.q` không có backlog; không có job cũ đang xử lý.
3. Chọn `eventId` mới, ví dụ `crash-001`.
4. Ứng dụng Spring đang chạy trong terminal mà bạn có thể **khởi động lại** sau khi JVM thoát.

Fault switch là biến toàn cục dùng đúng **một lần**, sẽ kích hoạt trên **message tiếp theo**. Không arming khi còn backlog hoặc khi các client khác cùng dùng queue, vì message bị crash có thể không phải event bạn muốn quan sát.

### 14.2. Arm fault và gửi event

~~~bash
curl.exe -s -X POST http://127.0.0.1:8080/lab/faults/crash-after-commit/arm
curl.exe -s -X POST http://127.0.0.1:8080/lab/events/crash-001
~~~

Ứng dụng sẽ:

1. Ghi `crash-001` vào outbox.
2. Relay publish message đến RabbitMQ.
3. Consumer nhận message và gọi `BusinessService.applyOnce`.
4. PostgreSQL commit cả `lab_processed` và `lab_business_effect`.
5. Listener in log `LAB_CRASH_AFTER_COMMIT` rồi gọi `Runtime.halt(137)` **trước `basicAck`**.

Khi JVM bị kết thúc, terminal chạy `mvn spring-boot:run` có thể trả về lỗi/exit code khác 0. Đây là **kết quả mong đợi** của fault injection. Nếu JVM không thoát, kiểm tra fault arm đã được gọi trước khi listener nhận message và không có listener khác nhận thay.

### 14.3. Kiểm chứng DB khi ứng dụng đang chết

Ứng dụng REST lúc này sẽ không phản hồi. Nhưng PostgreSQL vẫn chạy:

~~~powershell
docker compose exec postgres psql -U lab -d recoverylab -c "SELECT event_id FROM lab_processed WHERE event_id = 'crash-001';"
docker compose exec postgres psql -U lab -d recoverylab -c "SELECT count(*) AS business_count FROM lab_business_effect WHERE event_id = 'crash-001';"
docker compose exec rabbitmq rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers
~~~

**Kỳ vọng:** bảng `lab_processed` có `crash-001` và `business_count = 1`. Khi RabbitMQ nhận thấy connection đã đóng, delivery chưa ACK có thể quay lại trạng thái ready. Thời điểm chuyển `unacked → ready` không nhất thiết là tức thì, vì broker phải phát hiện connection đóng.

**Một cửa sổ lỗi thứ hai cũng có thể xảy ra:** relay có thể **chưa kịp cập nhật `outbox.sent_at`** trước khi consumer kill cả JVM. Vì vậy khi restart, outbox có thể còn PENDING và publish lại event; điều đó **không làm bài test fail**. Nó chính là lý do thiết kế inbox chống duplicate.

### 14.4. Restart app, quan sát redelivery và idempotency

Trong terminal chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Fault switch được khởi tạo lại với giá trị `false`. Có thể có **một hoặc nhiều delivery** cùng `eventId` do unacked redelivery và/hoặc outbox republish. Log kỳ vọng sẽ chứa một lần:

~~~text
DB_COMMITTED eventId=crash-001 applied=true
LAB_CRASH_AFTER_COMMIT eventId=crash-001
~~~

trước khi JVM bị kill, và sau restart có thể là:

~~~text
DB_COMMITTED eventId=crash-001 applied=false
ACKED eventId=crash-001
~~~

Kiểm tra lại:

~~~powershell
docker compose exec postgres psql -U lab -d recoverylab -c "SELECT count(*) AS processed_count FROM lab_processed WHERE event_id = 'crash-001';"
docker compose exec postgres psql -U lab -d recoverylab -c "SELECT count(*) AS business_count FROM lab_business_effect WHERE event_id = 'crash-001';"
docker compose exec postgres psql -U lab -d recoverylab -c "SELECT event_id, sent_at, attempts FROM lab_outbox WHERE event_id = 'crash-001';"
~~~

**PASS:** `processed_count = 1`, `business_count = 1`, outbox cuối cùng được đánh dấu gửi và queue trở về không có unacked delivery cho event này. Nếu listener nhận lại cùng event, log `applied=false` chứng minh logic idempotency đã bỏ qua tác dụng lặp.

Nếu không quan sát thấy `applied=false` nhưng `business_count` vẫn bằng 1, cần kiểm tra RabbitMQ delivery redelivery và outbox trạng thái để xác định đã thật sự tạo được cửa sổ crash trước ACK hay chưa. **Không chấp nhận một test chỉ kiểm tra tổng DB count nhưng không biết fault đã xảy ra đúng vị trí.**

### 14.5. Tại sao unique key phải nằm cùng transaction?

Đoạn code kiểu sau **không an toàn**:

~~~text
if (!alreadyProcessed(eventId)) {
    chargeCreditCard(eventId)
    saveProcessed(eventId)
}
~~~

Hai thread/consumer có thể đồng thời đọc `alreadyProcessed=false`, rồi cùng thực hiện side effect. Hoặc side effect thành công nhưng JVM chết trước khi lưu dấu.

Trong lab, câu `INSERT ... ON CONFLICT DO NOTHING` dựa trên unique primary key tạo một quyết định nguyên tử trong PostgreSQL, đồng thời ghi business effect trong **cùng transaction**. Điều đó bảo vệ **DB effect của bài tập**, còn cổng thanh toán/email ngoài DB vẫn cần idempotency key phía dịch vụ đích.

## 15. Case D — Consumer lỗi vĩnh viễn, message đi parking queue

**Mục tiêu:** kiểm chứng đường lỗi **reject không requeue**, topology dead-letter và ranh giới giữa “publish thành công” với “business xử lý thành công”.

**Giả thuyết:** fault switch `reject-next` làm listener ném exception **trước DB transaction**, sau đó gọi `basicReject(tag,false)`. RabbitMQ đưa message đến `lab.parking.x` và route vào `lab.parking.q`; event không được ghi vào inbox/business effect.

### 15.1. Arm reject và gửi event

Đảm bảo queue chính đã trống và listener đang chạy:

~~~bash
curl.exe -s -X POST http://127.0.0.1:8080/lab/faults/reject-next/arm
curl.exe -s -X POST http://127.0.0.1:8080/lab/events/rejected-001
curl.exe -s http://127.0.0.1:8080/lab/status
~~~

Sau khi outbox relay publish và listener nhận:

~~~powershell
docker compose exec rabbitmq rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers
docker compose exec postgres psql -U lab -d recoverylab -c "SELECT event_id FROM lab_processed WHERE event_id = 'rejected-001';"
docker compose exec postgres psql -U lab -d recoverylab -c "SELECT event_id FROM lab_business_effect WHERE event_id = 'rejected-001';"
~~~

Kết quả kỳ vọng:

- Event `rejected-001` có `sent_at` khác NULL trong outbox: **broker đã nhận publish**.
- `lab_processed` và `lab_business_effect` **không có** event `rejected-001`.
- `lab.orders.q` không còn message đó.
- `lab.parking.q` có **1 ready message** nếu trước test đang trống.
- Không có hàng nghìn redelivery do vòng lặp `requeue=true`.

**Chú ý:** `outboxSent` tăng không đồng nghĩa business effect tăng. Mỗi trạng thái đo một ranh giới khác nhau.

### 15.2. Khi nào nên retry thay vì reject?

| Loại lỗi | Ví dụ | Hành vi hợp lý |
|---|---|---|
| **Vĩnh viễn** | Schema sai, invalid enum, dữ liệu không hợp lệ | Reject/parking để điều tra; không requeue vô hạn |
| **Tạm thời** | Database timeout, HTTP 503, connection pool bận | Retry hữu hạn, backoff/jitter, sau đó parking nếu hết lượt |
| **Không rõ kết quả** | Cổng thanh toán timeout sau khi gửi request | Truy vấn trạng thái/idempotency key trước khi thử lại |
| **Hạ tầng gián đoạn** | Broker down giữa publish/confirm | Giữ outbox intent và thử lại khi khôi phục |

RabbitMQ DLX chỉ định **đích đi tiếp** cho dead-lettered message; nó không tự cung cấp phân loại lỗi, exponential backoff hay quy trình sửa lỗi. Muốn redrive `lab.parking.q` an toàn, cần một tool/quy trình có quyền giới hạn, giữ `eventId`, ghi audit, xem xét nguyên nhân và gửi lại có kiểm soát. **Không tự động đưa toàn bộ parking messages về main queue** khi chưa kiểm tra khả năng xử lý.

## 16. Case E — Mất publisher confirm: kết quả không xác định

Case này khó mô phỏng **đúng thời điểm** hơn các case trước. Publisher có thể gửi message xong, RabbitMQ đã ghi nhận, nhưng TCP connection bị ngắt trước khi confirm tới ứng dụng. `docker compose kill rabbitmq` trong lúc publish **có thể** tạo tình huống đó, nhưng không bảo đảm đúng mỗi lần.

~~~mermaid
sequenceDiagram
    participant R as OutboxRelay
    participant B as RabbitMQ
    participant C as Consumer
    R->>B: Publish eventId=e99
    B->>C: Delivery e99 (có thể đã xảy ra)
    B--xR: Connection mất trước confirm
    Note over R: Không xác định e99 đã được nhận hay chưa
    R->>R: Giữ outbox PENDING
    R->>B: Retry eventId=e99 sau recovery
    B->>C: Có thể delivery trùng e99
    C->>C: Inbox/eventId bảo vệ tác dụng DB
~~~

### 16.1. Thực nghiệm gần đúng

1. Đảm bảo broker/DB/app khỏe.
2. Gửi nhiều event riêng biệt để tạo publish attempts liên tục.
3. Trong terminal khác, `docker compose kill rabbitmq` lúc relay đang publish.
4. Kiểm tra log `OUTBOX_RETRY`, `sent_at` của events và trạng thái broker.
5. `docker compose start rabbitmq`, chờ relay tự gửi lại.
6. So sánh số **unique event IDs** giữa outbox và business table, không chỉ message count.

Ví dụ tạo 30 event trong PowerShell:

~~~powershell
1..30 | ForEach-Object {
    curl.exe -s -X POST "http://127.0.0.1:8080/lab/events/burst-$($_)"
}
~~~

Những lệnh này tạo traffic trong lab, **không** tái hiện network partition chính xác. Với kiểm thử tự động, dùng **Toxiproxy**, proxy mạng có điều khiển hoặc fault injection ở connection layer để cắt đường trả confirm sau khi broker đã nhận. Khi đó mới có thể lặp lại failure window đủ ổn định.

### 16.2. Tiêu chí đúng khi confirm bị mất

- Không đánh dấu `sent_at` nếu chưa quan sát confirm ACK phù hợp.
- Nếu nhận NACK hoặc returned message, giữ event để retry/điều tra theo policy.
- **Không** suy luận timeout nghĩa là broker chắc chắn chưa nhận.
- Retry dùng **cùng `eventId`**, không tạo business ID mới cho cùng nghiệp vụ.
- Consumer xử lý an toàn dù nhận cùng event nhiều lần.
- Có metric cho outbox pending, attempts và tuổi event chưa gửi.

**Giới hạn phép thử:** một RabbitMQ node với một disk volume không thể chứng minh các bảo đảm của quorum queue/cluster failover. Đánh giá RPO/RTO production cần cluster tương ứng và thử mất node, disk, quorum, network partition, TLS/proxy.

## 17. Case F — Graceful shutdown khác process crash

| Cách dừng | Điều xảy ra | Kỳ vọng |
|---|---|---|
| `container.stop()` hoặc Spring lifecycle stop | Container ngừng nhận delivery mới và có thể chờ delivery đang xử lý | Graceful, số unacked giảm khi task hoàn thành |
| `SIGTERM` + Spring Boot graceful shutdown | Framework đóng tài nguyên theo lifecycle, trong giới hạn thời gian | Hoàn tất việc đang xử lý nếu kịp |
| `SIGKILL`, `Runtime.halt`, OOMKilled | JVM chết không cleanup | Broker redeliver unacked khi connection mất, DB vẫn nhất quán |
| Network partition tạm thời | Connection timeout rồi reconnect | Có thể duplicate/unknown publish outcome, xử lý idempotent |

**Thực hành mở rộng:** chạy app trong container với `terminationGracePeriodSeconds` (Kubernetes) hoặc dùng `docker stop`/`docker kill` với container chỉ dành cho lab, rồi kiểm tra backlog và idempotency. Đừng kết luận graceful shutdown chắc chắn ACK mọi delivery: nếu task quá lâu hoặc hết grace period, process vẫn bị kill.

### 17.1. Spring AMQP quản lý recovery

Khi dùng `CachingConnectionFactory` và listener container của Spring AMQP, framework quản lý connection/channel và khôi phục consumer trong các đường lỗi phù hợp. Trong cấu hình phổ biến, Spring AMQP **không yêu cầu bật thêm automatic recovery của RabbitMQ Java client**; hai cơ chế recovery cạnh tranh có thể gây sự cố nếu tự bật không đúng cách.

Sau broker restart, quan sát:

- Log kết nối lại của `CachingConnectionFactory`.
- Listener container khôi phục và broker có `consumers` trở lại.
- Relay lấy được channel mới, tiếp tục chờ confirms.
- Durable topology vẫn còn; nếu queue/exchange bị xóa ngoài ý muốn, xác minh `RabbitAdmin`/declaration policy.

Tách bạch ba sự kiện: **connection hồi phục**, **listener đăng ký lại**, **message xử lý xong**. Không chỉ kiểm tra socket established rồi ghi PASS.

## 18. Ma trận tổng hợp kết quả mong đợi

| Case | Fault injection | Outbox | RabbitMQ queue | Business DB | Bằng chứng PASS |
|---|---|---|---|---|---|
| Baseline | Không | SENT sau confirm | Message đã ACK | 1 effect/event | Log publish + DB commit + ACK |
| A | Pause consumer | SENT | Ready tăng khi consumer=0 | Chưa tăng, sau resume tăng đúng số | Backlog được xử lý hết |
| B | Stop/start broker | PENDING khi down, SENT sau recovery | Persistent state theo điều kiện durability | Mỗi event 1 effect sau recovery | Không mất outbox intent |
| C | Halt JVM sau DB commit | SENT hoặc PENDING tùy timing; cuối cùng SENT | Unacked có thể redeliver | Vẫn 1 effect/event | Applied=true trước crash, applied=false sau redelivery |
| D | Reject trước DB commit | SENT | Main queue giảm, parking tăng | Không có effect của event lỗi | Reject không requeue; không hot loop |
| E | Cắt connection trong publish | PENDING nếu chưa confirm | Có thể đã nhận hoặc chưa | Dedup qua inbox | Unknown outcome được retry an toàn |
| F | Graceful vs hard stop | Tùy thời điểm publish | Delivery chưa ACK có thể trở lại | Không trùng effect | Recovery khác nhau nhưng DB nhất quán |

**Quan trọng:** khi so các số tổng trên `/lab/status`, tính thêm dữ liệu từ test trước. Sau case D, outbox có thể SENT nhưng business effect không tăng — đó là kết quả **đúng** vì event được parking. Không dùng “outboxSent phải bằng businessEffects” làm bất biến toàn cục.

## 19. Dùng SQL và RabbitMQ metrics để kiểm chứng chính xác

Đừng chỉ dựa vào log `ACKED`. Log có thể bị mất khi JVM chết, bị ghi trễ hoặc ghi trước khi transaction khác hoàn tất. Cần đối chiếu **PostgreSQL + RabbitMQ** bằng ID của từng event.

### 19.1. Xem trạng thái từng event trong một truy vấn

~~~powershell
docker compose exec postgres psql -U lab -d recoverylab -c "SELECT o.event_id, (o.sent_at IS NOT NULL) AS published, (p.event_id IS NOT NULL) AS processed, (b.event_id IS NOT NULL) AS business_effect, o.attempts FROM lab_outbox o LEFT JOIN lab_processed p ON p.event_id=o.event_id LEFT JOIN lab_business_effect b ON b.event_id=o.event_id ORDER BY o.created_at, o.event_id;"
~~~

Đọc kết quả theo các trạng thái:

| Published | Processed | Business effect | Diễn giải |
|---|---|---|---|
| false | false | false | Outbox còn chờ relay/broker; **chưa được xác nhận gửi** |
| true | false | false | Broker đã confirm publish, nhưng consumer chưa commit hoặc message đã vào parking |
| false | true | true | Consumer đã commit nhưng relay chưa cập nhật `sent_at`, có thể xảy ra khi crash rất đúng lúc |
| true | true | true | Đã confirm publish và có business effect |
| bất kỳ | true | false | **Bất biến DB bị vi phạm** trong schema/lab (inbox và effect cần cùng transaction) |
| bất kỳ | false | true | **Bất biến DB bị vi phạm**, cần điều tra transaction/SQL |

Hàng `published=true` ở đây nghĩa là **ứng dụng đã ghi `sent_at` sau khi thấy confirm**, không chứng minh end-to-end business completion. Bảng so sánh không thể hiện mọi trường hợp broker reject/parking hoặc message còn unacked; phải xem queue metrics.

### 19.2. Xem trạng thái queue và consumer

~~~powershell
docker compose exec rabbitmq rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers
~~~

Các số quan trọng:

- `messages_ready`: message đang ở queue và có thể cấp cho consumer.
- `messages_unacknowledged`: đã deliver nhưng broker chưa ghi nhận ACK.
- `consumers`: số consumer đăng ký với queue.
- `lab.parking.q`: backlog của các message bị reject/dead-letter.

**Một snapshot có thể đánh lừa:** nếu listener nhận/ACK nhanh, `unacked` chỉ tăng trong một khoảng rất ngắn nên bạn có thể không nhìn thấy ở CLI. Case C dùng `Runtime.halt` để tạo cửa sổ lỗi rõ ràng hơn, nhưng vẫn cần kiểm tra broker đã phát hiện connection đóng.

### 19.3. Viết một assertion có chờ giới hạn

Trong PowerShell, thay việc chờ cố định 30 giây bằng polling theo điều kiện:

~~~powershell
$deadline = (Get-Date).AddSeconds(60)
$count = ""

do {
    $count = docker compose exec -T postgres psql -U lab -d recoverylab -tAc "SELECT count(*) FROM lab_business_effect WHERE event_id = 'crash-001';"
    if ($LASTEXITCODE -ne 0) {
        throw "Không đọc được database của lab"
    }
    if ($count.Trim() -eq "1") {
        break
    }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)

if ($count.Trim() -ne "1") {
    throw "FAIL: crash-001 chưa có đúng một business effect"
}

Write-Host "PASS: crash-001 có một business effect"
~~~

Đây là **một assertion**, không phải toàn bộ test C. Muốn chứng minh recovery, còn phải ghi nhận **fault đã được kích hoạt**, listener thực sự crash **trước ACK**, broker redeliver hoặc relay republish, rồi hệ thống xử lý tiếp thành công. Một test chỉ assert `count=1` ngay sau commit có thể PASS ngay cả khi ứng dụng **không hề restart**.

### 19.4. Gợi ý log/metric nên thu thập

| Metric / event | Lấy từ đâu | Vì sao |
|---|---|---|
| `OUTBOX_RETRY`, attempts, tuổi pending | App log + PostgreSQL | Phát hiện broker không nhận publish hoặc confirm bị mất |
| `OUTBOX_SENT` | App log + `sent_at` | Xác minh kết quả publish đã được ghi vào DB |
| `DB_COMMITTED`, `applied=true/false` | Consumer log + business table | Phân biệt xử lý mới và duplicate |
| `ACKED` / `REJECT` | Listener log + broker queue stats | Quan sát settlement hoặc reject |
| Ready/unacked/consumer count | RabbitMQ Management/CLI/Prometheus | Phát hiện backlog, consumer biến mất và recovery |
| Connection/heartbeat failures | Spring AMQP/RabbitMQ logs | Phát hiện gián đoạn/reconnect |
| DLQ depth/age | `lab.parking.q` | Phát hiện message không xử lý được |
| CPU/heap/GC/thread pool/DB pool wait | JVM + Micrometer/DB metrics | Phát hiện bottleneck khiến recovery chậm |

Trong production, gắn `eventId`, consumer identity, routing key, message ID và publish attempt ID vào tracing. Không log payload nhạy cảm, mật khẩu RabbitMQ hoặc database credentials.

## 20. Chẩn đoán khi kết quả không như dự kiến

| Triệu chứng | Nguyên nhân có thể | Điều cần kiểm tra | Hướng sửa |
|---|---|---|---|
| App không start dù Postgres chạy | Không kết nối được DB, `schema.sql` lỗi, port bận | `docker compose ps`, JDBC URL, exception startup | Sửa DB/port trước khi test recovery |
| Bean topology khai báo lỗi `PRECONDITION_FAILED` | Queue cũ cùng tên nhưng khác durability/arguments | RabbitMQ Management và definitions | Dùng tên queue lab mới hoặc reset **chỉ môi trường lab** |
| POST trả 202 nhưng outbox không có row | Transaction không commit hoặc đang nhìn nhầm database | JDBC URL, query eventId | Không trả success trước khi DB commit |
| Outbox cứ PENDING khi broker healthy | Auth/vhost/port sai, template không confirm, exchange không tồn tại | App logs, `CorrelationData`, connection, returns | Sửa kết nối/topology và giữ event để retry |
| Broker down mà POST cũng fail | PostgreSQL down hoặc API đang phụ thuộc broker đồng bộ | DB health và luồng controller | Tách DB intent khỏi broker publish |
| Consumer resume nhưng không có consumers | Listener chưa start, permission/queue sai, connection chưa hồi phục | Registry, broker `consumers`, Spring logs | Kiểm tra container, credentials, topology |
| Message ở `ready` mãi | Consumer không đăng ký hoặc xử lý không kịp | `consumers`, exception listener, thread dump | Phục hồi consumer và downstream |
| Message `unacked` mãi | Listener block/DB chậm, channel còn mở | Listener thread, DB pool, transaction duration | Timeout, điều chỉnh consumer/prefetch, phân tích blocked calls |
| Crash xong DB chưa có `crash-001` | Fault kích hoạt trước khi DB commit hoặc gửi event chưa đến listener | Log fault và transaction, query eventId | Kiểm tra thứ tự lệnh, tạo event mới và chạy lại |
| Crash xong DB có 2 business rows | Không có unique key/transaction hoặc side effect nằm ngoài DB | Schema PK, transaction boundary | Inbox/unique transaction, external idempotency |
| Không thấy redelivery | Message không còn unacked, fault chưa trigger hoặc broker chưa phát hiện disconnect | Log `LAB_CRASH`, queue, eventId, connection | Chạy lại khi queue trống; xác minh thời điểm ACK |
| Parking queue rỗng sau reject | DLX/parking binding sai, listener không gọi reject, queue khác | Exchange/queue/binding, `basicReject` | Kiểm tra topology và manual ACK |
| Parking tăng quá nhanh | Lỗi converter/validation toàn bộ message hoặc retry policy sai | Log classification, schema, producer version | Dừng rollout, xử lý lỗi, redrive có kiểm soát |
| Outbox retry rất nhiều | Backoff quá ngắn, broker flow control, publisher NACK/return | `attempts`, broker memory/disk alarm | Exponential backoff/jitter, kiểm tra broker |
| Recovery làm app OOM | Prefetch/concurrency lớn, retry burst, payload nặng | Heap/RSS, unacked, GC và executor | Backpressure, giới hạn tải, điều chỉnh sizing |
| Publisher báo confirm ACK nhưng business table không tăng | Consumer pause/reject/DB lỗi hoặc event đang chờ | Queue, parking, inbox và listener logs | Phân biệt publish acceptance với consumer commit |

**Đừng sửa một bài test thất bại bằng cách tăng `Thread.sleep` vô hạn.** Hãy xem dữ liệu và metric ở đúng ranh giới: outbox → publisher confirm → queue ready/unacked → listener → DB commit → ACK.

### 20.1. Connection recovery không phải exactly-once

Khi RabbitMQ hoặc JVM gián đoạn, một số API hoàn tất bằng timeout, NACK hoặc exception. **Không thể từ exception suy ra broker chắc chắn chưa nhận message.** Mọi retry của producer nên giữ business event ID; consumer phải chịu được duplicate.

### 20.2. Listener catch Exception rồi return có thể làm mất message

Đây là lỗi phổ biến với `AcknowledgeMode.AUTO`:

~~~java
@RabbitListener(queues = "orders.q")
public void handle(String payload) {
    try {
        updateDatabase(payload);
    } catch (Exception ex) {
        log.error("business failed", ex);
        // Method vẫn return bình thường!
    }
}
~~~

Với AUTO ACK, method trả về bình thường thường khiến container xác nhận message, **dù DB đã lỗi**. Phải để exception truyền ra theo error/retry policy phù hợp hoặc điều khiển settlement tường minh. Trong lab ta chọn manual ACK để đường thành công/thất bại hiển thị rõ.

### 20.3. Chạy lại cùng eventId và một event mới có nghĩa khác nhau

Gửi lại cùng `eventId` là **retry của cùng nghiệp vụ**; tạo một ID khác cho cùng hành động có thể làm consumer tưởng đó là nghiệp vụ mới. Ở các hệ thống thanh toán, hóa đơn hoặc email, hãy dùng business idempotency key ổn định (ví dụ payment ID hoặc command ID), không chỉ UUID ngẫu nhiên mỗi lần HTTP request.

## 21. Mở rộng bài lab thành test tự động trong CI

Sau khi thao tác thủ công đã PASS, có thể biến kịch bản thành integration/fault tests:

| Tầng | Công cụ gợi ý | Test chính |
|---|---|---|
| Unit test | JUnit 5, Mockito | `BusinessService.applyOnce` chỉ ghi effect lần đầu |
| Integration test DB | Spring JDBC + PostgreSQL Testcontainers | Transaction rollback và unique constraint dưới concurrency |
| Integration RabbitMQ | `spring-rabbit-test`, `@RabbitAvailable` hoặc RabbitMQ Testcontainers | Exchange/binding, persistent message, ACK/reject/DLX |
| Fault broker | Testcontainers stop/start, Toxiproxy | Relay giữ PENDING khi broker down, gửi tiếp sau recovery |
| Fault consumer | Kill Spring process/container ở điểm xác định | DB commit trước ACK, redelivery, business effect không trùng |
| End-to-end | API + DB + RabbitMQ metrics | Các bất biến I1–I7 và thời gian recovery |

**Không mặc định một test có annotation `@RabbitAvailable` sẽ fail nếu broker không chạy**: một số cấu hình có thể skip khi broker vắng mặt. Trong pipeline bắt buộc, cấu hình job để không “xanh” khi toàn bộ integration tests bị bỏ qua. Dùng tên queue/vhost riêng và không cho CI quyền purge/xóa queue production.

### 21.1. Assertion hữu ích cho test tự động

~~~text
GIVEN event e100 được ghi outbox và RabbitMQ down
WHEN RabbitMQ được khởi động lại
THEN outbox(e100).sent_at khác NULL trước deadline
 AND business_effect_count(e100) == 1
 AND queue không giữ delivery e100 mãi

GIVEN consumer đã COMMIT event e101
WHEN process chết trước ACK và được restart
THEN redelivery hoặc retry cùng e101 được chấp nhận
 AND processed_count(e101) == 1
 AND business_effect_count(e101) == 1

GIVEN event e102 bị reject không requeue
WHEN RabbitMQ dead-letter
THEN e102 xuất hiện ở parking queue
 AND business_effect_count(e102) == 0
~~~

Một test fault tốt phải xác minh **đã tiêm đúng fault**. Nếu broker được restart trước khi có publish attempt hoặc JVM bị kill trước DB commit, kết quả vẫn có thể cho cùng số count nhưng không chứng minh failure window bạn định thử.

### 21.2. Không song song hóa lab state một cách vô thức

Các endpoint arm fault sử dụng cờ trong RAM áp dụng cho **message tiếp theo**, còn queue main là shared resource. Nếu hai tests cùng chạy hoặc có message khác từ bài trước, một test có thể gây crash nhầm event của test kia. Khi tự động hóa nên:

- Mỗi test dùng queue/vhost và database/schema độc lập, hoặc khóa tuần tự cho fault tests.
- Gắn fault với **eventId cụ thể** thay vì một flag global (nâng cấp code lab khi mở rộng).
- Dọn resource theo lifecycle test, không purge queue chung của người khác.
- Với broker restart, chờ điều kiện health và readiness có timeout; không chỉ sleep cố định.
- Thêm instrumentation để nhận được tín hiệu **DB committed**, **trước ACK**, **connection closed** và **redelivered** rõ ràng.

## 22. Đưa mô hình từ lab lên production cần thay đổi những gì?

Lab mô phỏng đúng các failure windows cốt lõi nhưng không phải một mẫu production hoàn chỉnh. Bảng sau giúp tránh sao chép nguyên code thử nghiệm:

| Thành phần trong lab | Production cần bổ sung |
|---|---|
| Một broker RabbitMQ container | Chọn topology phù hợp HA/RPO/RTO, quorum queue hoặc giải pháp bền vững khác, cluster/replication, backup/restore và thử failover |
| User `lab` và password trong file | TLS, secret manager, service accounts riêng, vhost ACL tối thiểu, credential rotation, Management API chỉ nội bộ |
| Một PostgreSQL container | Database HA/backup, transaction observability, migration scripts, connection pool và storage capacity |
| Một scheduled outbox relay | Claim/lease cho nhiều instances, batch size/backpressure, exponential backoff/jitter, max attempts, monitoring |
| Chờ confirm tối đa 5 giây | Timeout theo SLO, bounded in-flight, circuit breaker và cơ chế xử lý outcome không xác định |
| Manual ACK với lỗi nào cũng reject | Phân loại retryable/permanent, retry schedule, parking/quarantine, redrive audit |
| Một consumer với prefetch=1 | Tuning concurrency/prefetch theo throughput, CPU, DB capacity và ordering requirements |
| Inbox theo `eventId` | Chốt business idempotency key, retention inbox, transaction isolation, xử lý side effects ngoài DB |
| Endpoint bật `Runtime.halt` | **Loại bỏ hoàn toàn** khỏi artifact production; fault injection do test infrastructure kiểm soát |
| `/lab/status` tổng số hàng | Micrometer/Prometheus metrics, tracing theo eventId, alert queue lag, DLQ, outbox age, confirm/ACK errors |
| Docker volumes local | Backup/snapshot, disaster recovery, node failover, upgrade runbook và health probes |

### 22.1. Broker availability khác data durability

Một lần restart RabbitMQ container và thấy dữ liệu còn không chứng minh:

- Dữ liệu sẽ còn khi host disk bị mất hoàn toàn.
- Quorum queue sẽ luôn sẵn sàng khi cluster mất đa số replicas.
- Producer confirm đồng nghĩa consumer đã commit.
- Mọi message ở queue transient/durable đều có cùng bảo đảm lưu bền vững.
- Mất điện đúng thời điểm sẽ luôn cho cùng kết quả như `docker compose stop`.

Phân biệt:

- **Availability:** service có thể tiếp tục phục vụ hoặc phục hồi khi thành phần ngừng hoạt động.
- **Durability:** message đã được chấp nhận theo policy có còn sau sự cố thuộc phạm vi được cam kết hay không.
- **Delivery:** broker còn trách nhiệm giao message nếu chưa ACK.
- **Business consistency:** tác dụng nghiệp vụ không bị mất hoặc áp dụng trùng.

Đó là **bốn phép kiểm thử khác nhau**. Bài lab chủ yếu kiểm tra application recovery và idempotency; nếu yêu cầu HA ở cấp cluster, phải chạy bài kiểm thử tương ứng trên quorum/replicated topology.

### 22.2. Multiple consumers và nguy cơ tranh chấp

Tăng số replica hoặc `@RabbitListener(concurrency="4")` có thể giúp xử lý song song, nhưng tạo ra khả năng nhiều delivery của cùng eventId được xử lý gần nhau (do publisher retry hoặc redelivery).

Unique constraint trên `lab_processed.event_id` và transaction giữ cho DB effect chỉ xảy ra một lần. Khi business effect là một HTTP call bên ngoài, phải có key/idempotent endpoint ở phía đích hoặc một workflow xác nhận kết quả để tránh thực hiện lại.

Nếu cần thứ tự xử lý theo `orderId`, cần thiết kế routing/shard hoặc version guard phù hợp; việc chỉ tăng consumers có thể khiến thứ tự **hoàn thành** khác thứ tự **giao**.

### 22.3. Bảo vệ broker khỏi retry storm

Khi broker hoặc database hồi phục sau downtime dài, nhiều relay/consumer có thể thử lại cùng lúc. Cần kết hợp:

- Exponential backoff + jitter khi lỗi kết nối hoặc downstream.
- Max in-flight publishes và bounded channel/connection usage.
- Đặt `prefetch`/concurrency phù hợp năng lực DB/API.
- Giới hạn retries và đưa poison messages tới parking queue.
- Theo dõi outbox pending age, rate of redelivery và DLQ age.
- Kiểm tra broker memory/disk alarms và flow control, không chỉ HTTP health.

**Không đánh đổi độ tin cậy để đạt throughput:** ACK trước khi DB commit có thể làm mất công việc; tăng throughput bằng cách không chờ confirm cũng làm thay đổi guarantee của publisher. Mọi tuning phải được đánh giá trên cả tốc độ, p95/p99 latency, failure recovery và business correctness.

## 23. Checklist hoàn thành bài thực hành

1. [ ] Docker Compose chỉ chạy RabbitMQ/PostgreSQL của lab; port Management không public.
2. [ ] Spring app khởi động, topology có `lab.orders.x`, `lab.orders.q` và `lab.parking.q`.
3. [ ] API nhận event chỉ sau khi outbox được ghi; `202` không bị hiểu nhầm là business đã xử lý.
4. [ ] Correlated publisher confirm và mandatory return đã bật, `sent_at` chỉ ghi sau ACK đúng và không returned.
5. [ ] Listener dùng manual ACK **sau khi** `BusinessService.applyOnce` commit.
6. [ ] Inbox và business effect nằm trong một DB transaction với unique key.
7. [ ] Case baseline: mỗi event mới có đúng một business effect, queue hết ready/unacked.
8. [ ] Case A: pause consumer → queue ready tăng; resume → backlog được xử lý.
9. [ ] Case B: broker down → outbox PENDING; broker up → listener/relay hồi phục.
10. [ ] Case C: đã thấy fault sau DB commit trước ACK; restart → redelivery/retry an toàn, DB effect vẫn bằng 1.
11. [ ] Case D: lỗi vĩnh viễn → message đến parking queue, không retry nóng.
12. [ ] Case E: mất confirm được xem là **unknown outcome**, retry cùng eventId.
13. [ ] Case F: phân biệt graceful stop và hard crash; có kế hoạch dừng/khôi phục.
14. [ ] Có bằng chứng từ **SQL và broker queue stats**, không chỉ log “connected”.
15. [ ] Đã ghi nhận thời gian recovery, lỗi còn lại và hướng cải thiện.
16. [ ] Đã dừng lab và dọn dữ liệu theo đúng mục đích, không xóa nhầm volumes của dự án khác.

### 23.1. Mẫu báo cáo thực nghiệm

Ghi một bản báo cáo ngắn sau mỗi lần chạy:

| Trường | Ví dụ nội dung |
|---|---|
| Case | C — crash sau commit, trước ACK |
| Phiên bản | Spring Boot/AMQP, JDK, RabbitMQ, PostgreSQL, image digests |
| Tải | 1 eventId, listener concurrency=1, prefetch=1 |
| Fault | `Runtime.halt(137)` sau DB commit, trước `basicAck` |
| Bằng chứng | `DB_COMMITTED` trước kill; DB count=1; listener reconnect và thấy duplicate |
| Thời gian recovery | Thời điểm JVM restart → business state/queue ổn định |
| Dữ liệu | Outbox PENDING/SENT, processed count, business count, ready/unacked |
| Kết luận | PASS/FAIL, nguyên nhân nếu FAIL, bước tiếp theo |

Khi test theo nhóm, dùng event IDs riêng và ghi ảnh màn hình hoặc snapshot các metrics có timestamp; tránh hai người vô tình dùng chung queue khi fault switch global đang được bật.

## 24. Dừng lab và dọn dữ liệu an toàn

Sau khi hoàn thành, dùng `Ctrl+C` trong terminal ứng dụng để Spring Boot dừng bình thường. Dừng và xóa containers Compose:

~~~bash
docker compose down
~~~

Lệnh trên **giữ named volumes** để có thể mở lại lab và xem dữ liệu cũ. Nếu muốn dọn **toàn bộ dữ liệu chỉ thuộc dự án Compose lab này** sau khi đã lưu kết quả:

~~~bash
# XÓA DỮ LIỆU LAB trong named volumes đã khai báo!
docker compose down -v
~~~

**Kiểm tra tên project/container trước khi chạy `down -v`.** Không chạy từ thư mục Compose của dịch vụ khác, không dùng lệnh xóa volume toàn hệ thống và không xóa broker production. Nếu bạn muốn lặp lại bài từ dữ liệu trống, dùng project/volumes lab riêng, hoặc reset có kiểm soát sau khi đã xác minh không cần dữ liệu cũ.

Lưu ý khi tái sử dụng volume RabbitMQ: thay `RABBITMQ_DEFAULT_USER`/`RABBITMQ_DEFAULT_PASS` trong Compose **không nhất thiết đổi credentials của broker đã khởi tạo dữ liệu trước đó**. Đối với lab, có thể dùng một môi trường mới; đối với production, dùng quy trình quản lý user/secret thực tế.

## 25. Những nhận định dễ sai

| Nhận định | Điều đúng |
|---|---|
| “`convertAndSend` trả về là message đã được broker lưu” | Phải quan sát publisher confirm tương ứng; timeout có thể là kết quả chưa rõ |
| “Publisher confirm ACK là consumer đã xử lý xong” | Publish và consumer ACK/business commit là hai xác nhận khác nhau |
| “Durable queue đủ để không bao giờ mất message” | Còn message persistence, confirms, topology, disk/replication và failure model |
| “Broker restart thì mọi message chưa ACK bị mất” | Khi connection đóng, unacked delivery có thể được giao lại |
| “Consumer đã commit DB thì broker tự biết để xóa message” | DB commit không gửi consumer ACK một cách nguyên tử |
| “Manual ACK giải quyết exactly-once delivery” | ACK có thể mất khi connection hỏng; cần idempotency để bảo vệ business effect |
| “Đánh dấu outbox SENT trước khi publish giúp tránh duplicate” | Có thể mất event nếu broker không nhận được publish |
| “Nếu confirm timeout thì broker chắc chắn chưa nhận” | Kết quả không xác định, có thể phải retry cùng event ID |
| “Một consumer đang pause nghĩa là queue bị xóa” | Queue vẫn tồn tại; message đã route có thể chờ ở `ready` |
| “Bật lại consumer chắc chắn xử lý đúng thứ tự hoàn thành” | Concurrency/retry/side effects có thể làm completion order khác delivery order |
| “NACK requeue=true luôn là retry tốt” | Với lỗi vĩnh viễn có thể tạo hot loop và áp lực broker |
| “`default-requeue-rejected=false` là đủ cho manual ACK” | Với manual ACK, code phải ACK/NACK/reject hoặc framework phải xử lý theo trường hợp |
| “Restart app thành công là đã kiểm chứng recovery” | Cần kiểm tra outbox, broker delivery, inbox/DB effect và DLQ |
| “`Runtime.halt` giống graceful shutdown” | Nó bỏ qua cleanup; dùng để mô phỏng hard crash |
| “Case stop RabbitMQ một node chứng minh cluster HA” | Cluster/quorum/network failure cần test riêng theo topology |

### Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `RabbitTemplate`, `CorrelationData`, confirms và returns.
- [Spring AMQP — Receiving Messages](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): listener containers, acknowledgments và consumer lifecycle.
- [Spring AMQP — Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): `CachingConnectionFactory`, connection recovery và publisher connections.
- [Spring AMQP — Rabbit Listener Annotation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): `@RabbitListener`, manual ACK và listener configuration.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): hai cơ chế xác nhận và failure scenarios.
- [RabbitMQ — Reliability Guide](https://www.rabbitmq.com/docs/reliability): recovery, delivery guarantee và dữ liệu bền vững.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): dead-letter routing, reject/NACK và policy.
- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): queue durability, type và consumer delivery.
- [Docker Compose](https://docs.docker.com/compose/): start/stop, volumes, isolated lab environment.

**Kết luận:** Khả năng phục hồi của một ứng dụng Spring AMQP không thể được kiểm chứng chỉ bằng việc dừng RabbitMQ rồi thấy ứng dụng kết nối lại. Cần thử **cả đường producer lẫn consumer**: broker down nhưng outbox giữ ý định gửi, publisher confirm bị mất nhưng relay retry an toàn, consumer dừng rồi nhận lại backlog, và đặc biệt **JVM chết sau DB commit nhưng trước ACK** mà business effect vẫn không bị áp dụng hai lần. Khi đã có bằng chứng từ outbox, RabbitMQ ready/unacked/parking, inbox và transaction nghiệp vụ, bạn mới có thể nói hệ thống xử lý bất đồng bộ **phục hồi đúng trong các failure windows đã thử** — không phải tuyên bố “không bao giờ mất hoặc trùng message” ở mọi điều kiện.
