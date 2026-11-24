# Transaction trên flow JDBC trong Spring Integration

## 1. Vì sao transaction trên flow JDBC không chỉ là một câu lệnh SQL?

Một luồng Spring Integration có thể đọc các bản ghi chưa xử lý từ database, chuyển chúng thành `Message<?>`, ghi bảng outbox và gửi sự kiện sang Kafka/JMS. Khi một bước lỗi, câu hỏi nghiệp vụ là: **những thao tác nào phải rollback cùng nhau, những gì đã commit, và dữ liệu sẽ được thử lại thế nào?**

Ví dụ một lượt poll:

~~~text
SELECT 10 payment_event state='NEW'
    -> UPDATE các hàng thành 'CLAIMED'
    -> Message<List<PaymentEvent>>
    -> Splitter
    -> INSERT 10 outbox rows
    -> publisher Kafka/JMS
~~~

Nếu `UPDATE` commit nhưng outbox chưa ghi thì sự kiện có thể kẹt ở `CLAIMED`. Nếu đã gửi Kafka nhưng transaction database rollback thì cùng sự kiện có thể được gửi lại, tạo tác dụng trùng. Một annotation `@Transactional` đặt tùy ý trên một class không tự giải quyết được những trường hợp này.

Trong chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**, chúng ta thực hành kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`: file, SFTP, HTTP, JMS, AMQP, Kafka và database. Bài **Transaction trên flow JDBC** tập trung vào cách xác định **đơn vị công việc có thể commit/rollback**, ranh giới thread/channel, lỗi và vòng đời kết nối.

**Mục tiêu:** sau bài học, bạn có thể xác định khi nào `SELECT + UPDATE + service activator` thuộc cùng transaction; cấu hình transactional poller và transaction ở dịch vụ; hiểu rollback khi có lỗi; và thiết kế giao tiếp DB–broker mà không nhầm local transaction với distributed transaction.

## 2. Các khái niệm phải tách biệt

| Khái niệm | Ý nghĩa | Không có nghĩa |
|---|---|---|
| **Local JDBC transaction** | Commit/rollback các thao tác qua một database resource/transaction manager | Kafka/JMS/HTTP tự rollback theo |
| **Transaction boundary** | Phạm vi bắt đầu–kết thúc transaction | Một `IntegrationFlow` luôn có đúng một transaction |
| **Spring transaction context** | Trạng thái transaction gắn với thread khi dùng JDBC đồng bộ | Tự truyền qua `ExecutorChannel` |
| **Poller transaction** | Bao thao tác `receive()` và xử lý đồng bộ trong một poll | Mỗi row được một transaction riêng |
| **`@Transactional` service** | Áp dụng transaction advice khi gọi đúng Spring proxy | Tự áp dụng cho self-invocation |
| **Transaction synchronization** | Chạy callback trước/sau commit/rollback | Biến tài nguyên ngoài DB thành transactional |
| **Retry/redelivery** | Chạy lại một phần hoặc toàn bộ công việc | Không có duplicate side effects |
| **Idempotency** | Cùng event được xử lý lại mà không lặp tác dụng nghiệp vụ | Ngăn mọi event phát lại trên mạng |
| **Outbox** | Ghi bản ghi công việc gửi broker trong cùng DB transaction | Kafka producer ACK tương đương consumer xử lý xong |

**ACID** áp dụng ở phạm vi resource/transaction cụ thể. Khi sử dụng `DataSourceTransactionManager` hoặc `JdbcTransactionManager`, transaction thường bao các JDBC operations trên **cùng `DataSource`** trong **cùng thread**. Một message chuyển qua channel khác không tự mở rộng phạm vi này.

## 3. Luồng transaction đi theo thread, không đi theo tên IntegrationFlow

~~~mermaid
flowchart LR
    A["Transactional poller"] --> B["JDBC inbound source"]
    B --> C["DirectChannel"]
    C --> D["Service activator JDBC"]
    D --> E["COMMIT / ROLLBACK cùng TX"]

    B --> F["ExecutorChannel / QueueChannel"]
    F --> G["Worker / poller khác"]
    G --> H["Transaction khác"]
~~~

Spring Integration tham gia các transaction của Spring Framework. Với JDBC, transaction context thông thường được giữ trong `TransactionSynchronizationManager` theo thread đang chạy.

- **`DirectChannel`:** gọi subscriber ngay trong thread của sender. Khi sender đang ở trong transaction, handler đồng bộ có thể dùng cùng transaction.
- **`ExecutorChannel`:** chuyển sang thread executor. Transaction của sender **không tự được truyền** qua worker.
- **`QueueChannel`:** sender đặt message vào queue; poller/receiver khác xử lý sau. Transaction JDBC cũ không tự mở lại.
- **`PublishSubscribeChannel`:** nếu dùng executor, các subscriber có thể chạy ở threads khác. Không dựa vào tên channel để suy luận đồng bộ.
- **`FluxMessageChannel` hoặc reactive boundary:** không mặc nhiên áp dụng cách truyền transaction thread-bound của JDBC.

**Kết luận quan trọng:** một flow có thể nhìn như một đường mũi tên liên tục trên sơ đồ nhưng thực tế chứa **nhiều transaction độc lập**, vì nó có nhiều async boundaries.

## 4. Transactional poller và message-driven endpoint khác nhau

JDBC inbound channel adapter là **polling message source**: poller gọi `receive()` theo lịch để kích hoạt SELECT/UPDATE. Ngược lại, JDBC outbound adapter/gateway là **message-driven handlers**: chúng chạy khi một message tới input channel.

| Endpoint | Khi nào được gọi? | Cách bọc transaction phổ biến |
|---|---|---|
| JDBC inbound channel adapter | Poller gọi `receive()` | Transaction advice trên **poller** |
| JDBC outbound channel adapter | Message được dispatch vào handler | Transaction từ caller hoặc service/advice tại handler |
| JDBC outbound gateway | Message request kích hoạt SQL và tạo reply | Transaction từ caller hoặc advice ở boundary cần thiết |
| JDBC stored procedure outbound | Message tới handler | Transaction của caller/service hoặc endpoint advice |
| JDBC inbound stored procedure | Poller gọi procedure | Transaction trên poller |
| Service activator dùng `JdbcTemplate` | Message tới handler method | `@Transactional` trên service hoặc transaction bao ngoài |

Việc định nghĩa một `@Bean IntegrationFlow` **không tự bật transaction**. Bạn phải có `PlatformTransactionManager` phù hợp và đặt boundary ở chỗ chứa tất cả thao tác JDBC cần commit/rollback cùng nhau.

## 5. Sơ đồ ba cửa sổ commit cần phân biệt

~~~mermaid
sequenceDiagram
    participant P as Transactional poller
    participant DB as Database
    participant D as DirectChannel handler
    participant K as Kafka producer
    P->>DB: BEGIN
    P->>DB: SELECT NEW rows
    P->>DB: UPDATE rows to CLAIMED
    P->>D: Message<List<Event>>
    D->>DB: INSERT outbox rows
    D-->>P: Return
    P->>DB: COMMIT
    Note over P,DB: DB rows + outbox đã bền vững
    P->>K: (Tốt hơn: outbox publisher độc lập)
    K-->>P: ACK theo delivery semantics
    Note over K: Consumer đích vẫn có thể xử lý sau
~~~

Bảng phân tích:

| Thời điểm lỗi | Trạng thái DB | Hành động phù hợp |
|---|---|---|
| Lỗi khi SELECT | Chưa đổi nếu chưa có DML | Rollback/đợi retry |
| Lỗi sau UPDATE trước COMMIT | UPDATE có thể rollback | Đọc lại rows trong poll sau |
| Lỗi INSERT outbox cùng transaction | UPDATE và outbox đều rollback | Retry toàn batch |
| Crash sau DB COMMIT, trước publish | Outbox bền, chưa gửi | Publisher đọc outbox sau restart |
| Broker nhận nhưng crash trước đánh dấu published | Event outbox có thể còn pending | Gửi lại với ID ổn định/idempotent consumer |

**Không suy luận từ `send() == true` rằng mọi nguồn dữ liệu và broker đã commit.** Giá trị này phản ánh việc gửi message vào channel theo cơ chế của channel, không phải một biên nhận cross-system commit.

## 6. Chuẩn bị Spring Boot, database và dữ liệu mẫu

Ví dụ sử dụng Java 17+, Spring Boot, Spring Integration JDBC, Spring JDBC và H2. Spring Boot BOM nên quản lý phiên bản tương thích.

~~~groovy
// build.gradle - dependencies minh họa
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml của ứng dụng thực hành H2
spring:
  datasource:
    url: "jdbc:h2:mem:jdbc_tx_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
  sql:
    init:
      mode: always
~~~

Giả sử `src/main/resources/schema.sql` chứa:

~~~sql
CREATE TABLE payment_event (
    id             BIGINT PRIMARY KEY,
    event_id       VARCHAR(80) NOT NULL UNIQUE,
    order_id       VARCHAR(80) NOT NULL,
    state          VARCHAR(24) NOT NULL,
    version        INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_projection (
    order_id       VARCHAR(80) PRIMARY KEY,
    status         VARCHAR(32) NOT NULL,
    version        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE event_outbox (
    event_id       VARCHAR(80) PRIMARY KEY,
    aggregate_id   VARCHAR(80) NOT NULL,
    event_type     VARCHAR(80) NOT NULL,
    payload_json   VARCHAR(2000) NOT NULL,
    published      BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO payment_event(id,event_id,order_id,state,version)
VALUES (101,'payment-101','ORD-101','NEW',0),
       (102,'payment-102','ORD-102','NEW',0),
       (103,'payment-103','ORD-103','NEW',0);

INSERT INTO order_projection(order_id,status,version)
VALUES ('ORD-101','RECEIVED',0),
       ('ORD-102','RECEIVED',0),
       ('ORD-103','RECEIVED',0);
~~~

DDL ở đây dành cho demo; với production dùng migrations Flyway/Liquibase. H2 không tái hiện chính xác locking, commit ordering và dialect của PostgreSQL, Oracle, SQL Server hoặc MySQL.

## 7. DataSource và PlatformTransactionManager

Spring Boot với `spring-boot-starter-jdbc` thường tự tạo `DataSource`, `JdbcTemplate` và JDBC transaction manager khi auto-configuration được đáp ứng. Không cần tạo transaction manager thứ hai nếu đã có bean đúng.

Khi muốn quản lý rõ ràng một JDBC resource, có thể định nghĩa:

~~~java
package com.example.jdbc.transaction;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class JdbcTxConfiguration {

    // Chỉ khai báo nếu ứng dụng CHƯA có manager phù hợp.
    @Bean("jdbcTransactionManager")
    public PlatformTransactionManager jdbcTransactionManager(
            DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

`JdbcTransactionManager` là một triển khai JDBC transaction manager kế thừa/điều chỉnh behavior của `DataSourceTransactionManager` để hỗ trợ exception translation khi commit/rollback. `DataSourceTransactionManager` cũng là lựa chọn hợp lệ cho JDBC đồng bộ.

**Không khai báo hai managers cùng có khả năng được inject tự động** mà không chỉ định `@Primary`/`@Qualifier` hoặc `transactionManager` rõ ràng. Với nhiều DataSources, một transaction manager phải trỏ đến đúng datasource mà JDBC adapter và repositories dùng.

### 7.1. Vì sao JdbcTemplate tự tham gia transaction?

`JdbcTemplate` lấy connection qua hạ tầng Spring JDBC (`DataSourceUtils`). Nếu transaction manager đã bind một connection vào thread cho DataSource ấy, những lời gọi `JdbcTemplate` trong cùng thread thường dùng connection transaction-bound đó.

~~~text
@Transactional service / transactional poller
  -> TransactionManager BEGIN
  -> DataSourceUtils lấy/bind connection
  -> JdbcTemplate UPDATE ...
  -> JdbcTemplate INSERT ...
  -> TransactionManager COMMIT/ROLLBACK
  -> Connection trở lại pool khi phù hợp
~~~

Không tự gọi `connection.commit()` hoặc `connection.close()` trên connection đang được Spring transaction manager quản lý. Một manual JDBC connection ngoài `DataSourceUtils` có thể không tham gia transaction hiện hành như mong đợi.

## 8. JDBC inbound: SELECT và UPDATE trong một poll transaction

Spring Integration JDBC inbound adapter có thể chạy một câu `SELECT` để tạo message và một câu `UPDATE` để đánh dấu những rows vừa đọc. **Poller transaction** là cách chuẩn để bao cả hai câu SQL, và có thể bao downstream đồng bộ.

~~~mermaid
sequenceDiagram
    participant Poller
    participant Adapter as JdbcPollingChannelAdapter
    participant DB as Database
    participant Handler as DirectChannel handler
    Poller->>DB: BEGIN
    Poller->>Adapter: receive()
    Adapter->>DB: SELECT state='NEW'
    DB-->>Adapter: Rows 101,102
    Adapter->>DB: UPDATE rows to CLAIMED
    Adapter-->>Handler: Message<List<Row>>
    alt Handler hoàn thành
        Handler-->>Poller: Return
        Poller->>DB: COMMIT
    else Handler ném exception
        Handler-->>Poller: Exception
        Poller->>DB: ROLLBACK
    end
~~~

Giả sử transaction manager dùng đúng DataSource của adapter, `SELECT` và `UPDATE` được thực hiện trong cùng transaction; điều này được mô tả trực tiếp trong Spring Integration JDBC Reference.

### 8.1. Java DSL cho Spring Integration 7.x

Từ Spring Integration **7.0**, JDBC module cung cấp `Jdbc.inboundAdapter(...)` trong package `org.springframework.integration.jdbc.dsl.Jdbc`.

~~~java
package com.example.jdbc.transaction;

import java.time.Duration;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class PaymentPollingFlow {

    public record PaymentRow(
        long id, String eventId, String orderId) { }

    @Bean
    public IntegrationFlow pollPayments(
            DataSource dataSource,
            PlatformTransactionManager jdbcTransactionManager,
            PaymentOutboxWriter outboxWriter) {

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource,
                        "SELECT id, event_id, order_id "
                      + "FROM payment_event "
                      + "WHERE state='NEW' ORDER BY id")
                    .maxRows(20)
                    .rowMapper((rs, n) -> new PaymentRow(
                        rs.getLong("id"),
                        rs.getString("event_id"),
                        rs.getString("order_id")))
                    .updateSql(
                        "UPDATE payment_event "
                      + "SET state='CLAIMED', version=version+1 "
                      + "WHERE id IN (:ids) AND state='NEW'")
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> rows = (List<?>) result;
                        List<Long> ids = rows.stream()
                            .map(PaymentRow.class::cast)
                            .map(PaymentRow::id)
                            .toList();
                        return new MapSqlParameterSource("ids", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(jdbcTransactionManager)))
            .filter(payload ->
                payload instanceof List<?> rows && !rows.isEmpty())
            .split()
            .handle(outboxWriter, "stage")
            .get();
    }
}
~~~

**Điều kiện bảo đảm của ví dụ:** `outboxWriter.stage(PaymentRow)` phải chỉ ghi database **bằng cùng DataSource** và chạy đồng bộ trong poller thread; nếu nó ném exception và exception truyền ra, transaction của poller có thể rollback cả `UPDATE state` và các outbox rows đã ghi trước đó. Ở đây **không gửi Kafka trong transaction này**.

`Jdbc.inboundAdapter` tạo message source; `maxRows(20)` là số rows tối đa của query; `maxMessagesPerPoll(1)` là số lần `receive()` trong một trigger, không phải số rows. `.split()` biến `Message<List<PaymentRow>>` thành các messages có payload `PaymentRow`, vẫn có thể được xử lý đồng bộ nếu không có async channel.

**Không xem mẫu SELECT rồi UPDATE này là atomic claim giữa nhiều pods.** Hai pods có thể SELECT cùng một row trước khi một pod UPDATE. Nếu cần quyền sở hữu độc quyền, hãy dùng row locks/`SKIP LOCKED`, atomic claim/RETURNING hoặc lease theo DB vendor, kết hợp idempotency.

### 8.2. Java handler ghi outbox đồng bộ

~~~java
package com.example.jdbc.transaction;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class PaymentOutboxWriter {

    private final JdbcTemplate jdbc;

    public PaymentOutboxWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void stage(PaymentPollingFlow.PaymentRow row) {
        jdbc.update(
            "INSERT INTO event_outbox "
          + "(event_id, aggregate_id, event_type, payload_json) "
          + "VALUES (?, ?, ?, ?)",
            row.eventId(),
            row.orderId(),
            "order.payment.received",
            "{\"orderId\":\"" + row.orderId() + "\"}");
    }
}
~~~

`event_id` là khóa nghiệp vụ ổn định qua retry. Ví dụ JSON chỉ dùng cho demo với `orderId` giả định có định dạng an toàn; trong thực tế dùng JSON serializer/DTO thay vì tự nối JSON string từ input không tin cậy.

**Điểm mấu chốt:** Handler ghi **outbox**; publisher khác gửi Kafka/JMS *sau commit*. Nếu stage row thứ hai ném `DataAccessException`, transaction của poller rollback các rows trước đó khi cùng resource/thread, tránh cập nhật `CLAIMED` mà không còn công việc để gửi.

## 9. Spring Integration 6.x: JdbcPollingChannelAdapter và poller

Trước Spring Integration 7.0, sử dụng `JdbcPollingChannelAdapter` trực tiếp:

~~~java
package com.example.jdbc.transaction;

import java.time.Duration;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class LegacyJdbcPollingConfiguration {

    @Bean
    public IntegrationFlow legacyPolling(
            DataSource dataSource,
            PlatformTransactionManager jdbcTransactionManager,
            PaymentOutboxWriter outboxWriter) {

        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource,
                "SELECT id, event_id, order_id "
              + "FROM payment_event WHERE state='NEW' ORDER BY id");

        source.setRowMapper((rs, n) ->
            new PaymentPollingFlow.PaymentRow(
                rs.getLong("id"),
                rs.getString("event_id"),
                rs.getString("order_id")));
        source.setMaxRows(20);
        source.setUpdateSql(
            "UPDATE payment_event SET state='CLAIMED' "
          + "WHERE id IN (:id) AND state='NEW'");

        // Với custom RowMapper trả Java record, cấu hình factory
        // thay vì dựa vào projection mặc định từ Map.
        source.setUpdateSqlParameterSourceFactory(result -> {
            var rows = (java.util.List<?>) result;
            var ids = rows.stream()
                .map(PaymentPollingFlow.PaymentRow.class::cast)
                .map(PaymentPollingFlow.PaymentRow::id)
                .toList();
            return new MapSqlParameterSource("id", ids);
        });

        return IntegrationFlow.from(source, endpoint ->
                endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(jdbcTransactionManager)))
            .split()
            .handle(outboxWriter, "stage")
            .get();
    }
}
~~~

Đây là một **phương án thay thế**, không đăng ký đồng thời flow 7.x và 6.x trên cùng bảng khi chưa thiết kế concurrency. Import `JdbcPollingChannelAdapter` ở 6.x thuộc `org.springframework.integration.jdbc`; JDBC Java DSL factory chỉ có từ 7.x.

## 10. XML transactional poller: SELECT + UPDATE

~~~xml
<!-- Fragment, context có namespace int và int-jdbc. -->
<int:channel id="paymentBatches"/>

<int-jdbc:inbound-channel-adapter
    id="paymentsFromDatabase"
    data-source="dataSource"
    channel="paymentBatches"
    query="SELECT id, event_id, order_id
           FROM payment_event
           WHERE state='NEW'
           ORDER BY id"
    update="UPDATE payment_event
            SET state='CLAIMED'
            WHERE id IN (:id) AND state='NEW'"
    max-rows="20">
    <int:poller fixed-delay="5000" max-messages-per-poll="1">
        <int:transactional
            transaction-manager="jdbcTransactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

Ở dạng XML, `:id` theo naming convention mặc định lấy danh sách ID từ SELECT. Downstream muốn một message cho mỗi row cần một splitter; muốn transaction rollback khi downstream lỗi, các handlers tiếp theo phải đồng bộ cùng thread và không nuốt exception.

Không cần thêm `@Transactional` lên từng handler nếu đã có poller transaction bao toàn bộ local JDBC work. Tuy nhiên việc có nhiều transactions lồng nhau và propagation khác nhau có thể thay đổi hành vi (xem mục 14).

## 11. DirectChannel: chặng xử lý đồng bộ có thể cùng transaction

Ví dụ:

~~~text
Transactional poller BEGIN
  -> JDBC source SELECT/UPDATE
  -> DirectChannel
  -> Splitter
  -> DirectChannel
  -> @ServiceActivator ghi outbox
  -> Return
Transactional poller COMMIT
~~~

Vì không thay thread, transaction resource có thể được chia sẻ. Một `DataAccessException` tại outbox writer, nếu được ném ra khỏi handler, có thể làm poller rollback `SELECT/UPDATE` và các DML khác.

Không đánh giá transaction bằng **sơ đồ flow** đơn thuần. Hãy xác minh tại runtime: thread, transaction manager, DataSource, exception propagation, propagation policy và COMMIT thật.

### 11.1. ExecutorChannel: async handoff kết thúc phần transaction trước

~~~text
Poller BEGIN
  -> SELECT/UPDATE
  -> ExecutorChannel gửi message sang worker
Poller COMMIT

Worker khác:
  -> JDBC outbox writer
  -> Exception
  -> Có thể dùng transaction riêng / errorChannel
~~~

**Kết quả:** trạng thái `CLAIMED` đã commit ở poller, còn lỗi outbox nằm ở worker thread. Không mặc định lỗi đó quay về poller để rollback.

Dùng `ExecutorChannel` có bounded executor/queue và transaction **riêng** tại worker nếu cần. Nếu mục tiêu là “không mất công việc”, hãy stage thông tin vào persistent outbox/work queue **trước** async boundary.

### 11.2. QueueChannel: gửi/nhận cách nhau về thời gian

`QueueChannel` lưu message để một poller khác nhận. Nó có thể làm việc vượt khỏi transaction cũ. Một in-memory queue **không phải kho lưu công việc bền vững** qua crash. Nếu cần durable queue, dùng broker hoặc persistent message store với semantics phù hợp; vẫn phải quản lý ACK/transaction giữa hai resource.

## 12. Transaction của message-driven JDBC handler

JDBC outbound adapter/gateway không tự được poller JDBC inbound bao bọc nếu caller ở channel khác. Một handler có thể nhận transaction do service gọi nó hoặc được bọc bằng `@Transactional` ở một service boundary.

~~~mermaid
flowchart LR
    A["HTTP / Kafka / JMS inbound"] --> B["MessageChannel"]
    B --> C["Transactional service"]
    C --> D["JdbcTemplate UPDATE"]
    C --> E["JdbcTemplate INSERT outbox"]
    D --> F[("Same DB TX")]
    E --> F
    C --> G["Return DTO/result"]
~~~

Ví dụ một dịch vụ cập nhật đơn hàng, ghi outbox và để transaction manager commit **sau khi method hoàn tất**:

~~~java
package com.example.jdbc.transaction;

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
    public PaymentResult apply(String eventId, String orderId) {
        int updated = jdbc.update(
            "UPDATE order_projection "
          + "SET status='PAID', version=version+1 "
          + "WHERE order_id=? AND status='RECEIVED'",
            orderId);

        if (updated != 1) {
            throw new IllegalStateException(
                "Order not found, already paid or state changed");
        }

        jdbc.update(
            "INSERT INTO event_outbox "
          + "(event_id, aggregate_id, event_type, payload_json) "
          + "VALUES (?, ?, ?, ?)",
            eventId, orderId, "order.paid",
            "{\"orderId\":\"" + orderId + "\"}");

        return new PaymentResult(orderId, updated);
    }

    public record PaymentResult(String orderId, int updatedRows) { }
}
~~~

Nếu `event_outbox` INSERT vi phạm UNIQUE và exception truyền ra, transaction mặc định rollback UPDATE của `order_projection`. Khi message được redeliver, cần tra cứu event ID/aggregate state để phân biệt **duplicate đã thành công** với **conflict**; ví dụ này chủ ý ném lỗi với updated count 0 để người học nhìn thấy boundary.

### 12.1. Dùng @ServiceActivator để expose method

~~~java
package com.example.jdbc.transaction;

import java.util.Map;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class PaymentMessageHandler {

    private final PaymentService service;

    public PaymentMessageHandler(PaymentService service) {
        this.service = service;
    }

    @ServiceActivator(
        inputChannel = "paymentRequests",
        outputChannel = "paymentReplies")
    public PaymentService.PaymentResult handle(
            Map<String, String> payload) {
        return service.apply(
            payload.get("eventId"), payload.get("orderId"));
    }
}
~~~

**Điều kiện:** `PaymentService` là Spring bean được gọi **qua proxy** từ bean handler khác. `@Transactional` ở service tạo boundary ngay cả khi handler không được gọi bởi một transactional poller. `paymentReplies` phải có consumer/reply context phù hợp; một reply nhận được tại handler level không luôn chứng minh transaction của caller bao ngoài đã commit.

## 13. JDBC outbound gateway: reply đến trước commit có thể gây hiểu nhầm

JDBC outbound gateway nhận request message, chạy SQL, rồi tạo reply chứa update count, generated keys hoặc SELECT rows. **Reply từ handler** và **commit của transaction bao ngoài** không phải một sự kiện duy nhất.

~~~text
@Transactional outerService:
  -> Gửi request đến JDBC outbound gateway
  -> UPDATE tạo reply {UPDATED=1}
  -> outerService tiếp tục xử lý
  -> Một bước sau ném RuntimeException
  -> Outer JDBC transaction ROLLBACK
~~~

Reply `UPDATED=1` ở đây chỉ nói rằng SQL đã tác động một row **trước rollback**; nó **không phải biên nhận đã commit**. Với generated keys, database có thể đã cấp key nhưng row cuối cùng vẫn rollback.

| SQL | Reply thường gặp | Cần lưu ý |
|---|---|---|
| DML không generated keys | Map `{UPDATED=n}` | Có thể bị rollback sau reply |
| INSERT có generated keys | Map/list keys tùy driver | Generated key không chứng minh COMMIT |
| SELECT | Row hoặc list theo `maxRows` | Dữ liệu phụ thuộc snapshot/isolation |
| UPDATE + SELECT | Kết quả SELECT là payload | Không tự là tuple count + rows |

Ví dụ Java DSL **Spring Integration 7.x**:

~~~java
// Mảnh trong @Bean IntegrationFlow; dataSource được inject.
return IntegrationFlow.from("statusCheckRequests")
    .handle(Jdbc.outboundGateway(dataSource,
        "UPDATE order_projection "
      + "SET status = :payload[newStatus], version=version+1 "
      + "WHERE order_id = :payload[orderId] "
      + "  AND version = :payload[expectedVersion]"))
    .channel("statusCheckReplies")
    .get();
~~~

Payload request giả định là một `Map` gồm `orderId`, `newStatus`, `expectedVersion`. `UPDATED=0` có thể chỉ ra không có row phù hợp hoặc version conflict, không tự tạo SQL exception. Nếu cần cập nhật business table **và** ghi outbox, hãy đặt cả hai trong một service transaction hoặc đồng bộ chặng JDBC thích hợp, không chỉ chuyển reply sang một worker riêng rồi hy vọng chúng sẽ atomic.

## 14. @Transactional: proxy, rollback rules và propagation

`@Transactional` mặc định hoạt động thông qua Spring proxy. **Self-invocation** từ method cùng object thường bypass transaction advice:

~~~java
@Service
public class SelfInvocationExample {

    public void run() {
        update(); // Không đi qua proxy @Transactional của Spring.
    }

    @Transactional
    public void update() {
        // JDBC DML...
    }
}
~~~

Cách sửa: gọi transactional method thông qua một **Spring bean khác** (được inject qua proxy) hoặc dùng `TransactionTemplate`.

### 14.1. Exception nào làm rollback?

Thông thường Spring rollback khi `RuntimeException` hoặc `Error` được ném qua transactional method. Checked exception cần `rollbackFor` hoặc quy tắc rollback phù hợp phiên bản:

~~~java
@Transactional(rollbackFor = Exception.class)
public void importPayments() throws Exception {
    // JDBC updates + outbox
}
~~~

Bẫy nghiêm trọng là **catch exception rồi trả thành công**:

~~~java
@Transactional
public void unsafeOperation() {
    try {
        // JDBC DML...
    } catch (RuntimeException ex) {
        // Nếu chỉ log và return, transaction interceptor có thể
        // không thấy exception để rollback theo quy tắc mặc định.
    }
}
~~~

Khi nghiệp vụ cần rollback, ném lại exception hoặc thiết kế rollback-only rõ ràng. Không catch `DataAccessException` rồi biến lỗi kết nối thành “không tìm thấy dữ liệu”.

### 14.2. Propagation làm thay đổi phạm vi

| Propagation | Ý nghĩa | Rủi ro cần lưu ý |
|---|---|---|
| `REQUIRED` | Tham gia TX hiện hành hoặc tạo mới | Mặc định phổ biến |
| `REQUIRES_NEW` | Tạm treo TX ngoài, tạo TX mới | Có thể cần thêm connection |
| `SUPPORTS` | Tham gia nếu có | Không có TX thì DML không atomic theo nhóm |
| `MANDATORY` | Bắt buộc đã có TX | Lỗi nếu caller không có transaction |
| `NOT_SUPPORTED` | Chạy ngoài TX hiện hành | Có thể auto-commit |
| `NESTED` | Savepoint khi resource/manager hỗ trợ | Không phải một DB transaction độc lập |
| `NEVER` | Không cho chạy trong TX | Ném lỗi nếu có active transaction |

`REQUIRES_NEW` không phải cách mặc định để “an toàn hơn”. Khi poller transaction đang giữ connection, nested service mở `REQUIRES_NEW` có thể cần connection thứ hai; nhiều pollers và pool quá nhỏ tạo nguy cơ chờ cạn connection.

### 14.3. Isolation

| Isolation | Góc nhìn cần xét |
|---|---|
| `READ_COMMITTED` | Không thấy uncommitted rows, nhưng vẫn có race khi đọc rồi cập nhật |
| `REPEATABLE_READ` | Snapshot/locking phụ thuộc DB vendor |
| `SERIALIZABLE` | Cô lập mạnh nhưng có serialization failures/deadlocks |
| `READ_UNCOMMITTED` | DB có thể cho dirty reads nếu hỗ trợ |
| `DEFAULT` | Theo cấu hình DB |

Không có một isolation level đơn lẻ nào biến JDBC và Kafka thành giao dịch phân tán. Với multi-instance polling, thường cần thêm locking/atomic claim/idempotency theo database.

## 15. Optimistic locking và update count

Một row có `version` giúp phát hiện cập nhật tranh chấp:

~~~sql
UPDATE order_projection
SET status = :newStatus,
    version = version + 1
WHERE order_id = :orderId
  AND version = :expectedVersion;
~~~

Kết quả `updated=1` nghĩa predicate phù hợp lúc UPDATE; `updated=0` nghĩa order không tồn tại, version thay đổi hoặc command đã được áp dụng theo trạng thái khác. Cần kiểm tra domain state và processed-event ID trước khi quyết định ACK/retry.

~~~text
Lần 1: event e-101 làm order RECEIVED -> PAID, version 0 -> 1
DB COMMIT nhưng Kafka/JMS source chưa ACK
Lần 2: event e-101 bị redeliver
UPDATE WHERE version=0 -> 0 rows
~~~

Ở lần hai, trả `0` không nhất thiết là lỗi; nếu đây đúng cùng event ID và trạng thái đã đạt, có thể được coi là duplicate hợp lệ. Nếu một event khác gây version conflict, không được âm thầm ACK như đã xử lý.

**Transaction** quyết định commit/rollback của các bước SQL; **optimistic locking** quyết định tính hợp lệ của một UPDATE khi concurrency. Chúng bổ trợ nhau, không thay thế nhau.

## 16. TransactionTemplate cho boundary tường minh

`TransactionTemplate` phù hợp khi muốn đặt chính xác ranh giới JDBC transaction mà không dựa trên proxy annotation:

~~~java
package com.example.jdbc.transaction;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ExplicitPaymentTransaction {

    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;

    public ExplicitPaymentTransaction(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.tx = new TransactionTemplate(manager);
    }

    public int markPaidAndStage(String orderId, String eventId) {
        return tx.execute(status -> {
            int changed = jdbc.update(
                "UPDATE order_projection SET status='PAID', "
              + "version=version+1 "
              + "WHERE order_id=? AND status='RECEIVED'",
                orderId);
            if (changed != 1) {
                throw new IllegalStateException(
                    "Order already processed or conflicting");
            }

            jdbc.update(
                "INSERT INTO event_outbox "
              + "(event_id, aggregate_id, event_type, payload_json) "
              + "VALUES (?, ?, ?, ?)",
                eventId, orderId, "order.paid",
                "{\"orderId\":\"" + orderId + "\"}");
            return changed;
        });
    }
}
~~~

Cả hai câu DML chạy trong cùng local JDBC transaction nếu template và manager cùng DataSource. Không tạo transaction ở thread A rồi chuyển DML qua `ExecutorChannel` thread B mà kỳ vọng transaction context của A đi theo.

## 17. Transaction advice của poller và retry advice

Cú pháp Java DSL:

~~~java
endpoint -> endpoint.poller(
    Pollers.fixedDelay(Duration.ofSeconds(5))
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
~~~

Cú pháp XML:

~~~xml
<int:poller fixed-delay="5000" max-messages-per-poll="1">
    <int:transactional
        transaction-manager="jdbcTransactionManager"/>
</int:poller>
~~~

Transaction advice khác với việc thêm `@Transactional` lên một bean tùy ý. Khi poller có **retry advice, transaction advice, metrics/tracing advice**, thứ tự thực thi advice quyết định retry nằm **trong** hay **ngoài** transaction.

Ví dụ:
- Retry sau deadlock thường cần **rollback trước, rồi chạy lại toàn transactional unit trong một transaction mới**.
- Retry một SQL trên transaction đang đánh dấu rollback-only có thể không cứu được transaction đó.
- Nếu advice bắt exception và không ném lại, transaction manager có thể thấy poll hoàn tất bình thường và COMMIT.

Không gắn retry mù quáng cho DuplicateKey, SQL grammar hoặc validation errors. Dùng policy theo subtype `DataAccessException`, giới hạn attempts và backoff/jitter.

## 18. TransactionSynchronization và afterCommit

Spring cho phép đăng ký callback khi transaction hoàn tất:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

// Chỉ dùng khi transaction synchronization đang active.
TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            // Chạy sau local JDBC COMMIT.
        }
    });
~~~

Spring Integration cung cấp `TransactionSynchronizationFactory` cho các polling endpoints, với `before-commit`, `after-commit` và `after-rollback`:

~~~xml
<int:transaction-synchronization-factory id="syncFactory">
    <int:after-commit expression="payload" channel="committedChannel"/>
    <int:after-rollback expression="payload" channel="rolledBackChannel"/>
</int:transaction-synchronization-factory>
~~~

Poller có thể tham chiếu `synchronization-factory="syncFactory"` trong `<int:transactional ... />`. Những callbacks này **đồng bộ hành động với transaction**, nhưng không biến HTTP/Kafka/JMS thành tài nguyên có thể rollback.

**Crash window:** DB COMMIT xong, ứng dụng chết trước khi callback `afterCommit` gửi Kafka. Callback trong RAM không phải durable work queue. Với dữ liệu không được phép mất, dùng **transactional outbox** thay vì chỉ dựa vào afterCommit callback.

`afterRollback` không nên giả định có thể tiếp tục dùng transaction vừa rollback để ghi audit bền vững. Nếu cần ghi thông tin failure vào DB, dùng transaction riêng có semantics rõ ràng.

## 19. Outbox: chia DB transaction và broker publish đúng cách

~~~mermaid
flowchart LR
    A["HTTP / Kafka / JMS source"] --> B["Transactional service"]
    B --> C["UPDATE business tables"]
    B --> D["INSERT event_outbox"]
    C --> E[("DB COMMIT")]
    D --> E
    E --> F["Outbox publisher"]
    F --> G["Kafka / JMS broker"]
    G --> H["Idempotent consumer"]
~~~

**Trong một DB transaction**: ghi nghiệp vụ + outbox rồi commit cùng nhau. **Ở publisher khác**: lấy outbox pending, gửi broker, ghi `published=true` theo retry/ACK contract.

Nếu broker nhận message thành công nhưng publisher chết trước khi đánh dấu `published`, message có thể được gửi lại. Vì vậy outbox thường cung cấp **at-least-once delivery**, kết hợp consumer idempotency; không tự đảm bảo exactly-once effect trên mọi hệ thống.

### 19.1. Kafka listener và JDBC transaction

Một quy trình thực tế:

1. Nhận Kafka event `eventId=e-101`.
2. Trong local JDBC transaction, validate event, ghi business changes, processed-event ID và outbox record.
3. COMMIT JDBC.
4. Commit Kafka offset/ACK theo listener container semantics.

Nếu ứng dụng chết sau bước 3 nhưng trước bước 4, Kafka có thể redeliver. Processed-event unique constraint cần giúp lần hai **không tạo duplicate effect**. Nếu commit Kafka offset trước DB COMMIT, crash có thể khiến event không được xử lý nhưng offset đã tiến.

Spring Kafka có các cơ chế phối hợp transaction nhất định, nhưng không mặc định có một XA distributed transaction DB+Kafka. Cần kiểm chứng thứ tự commit/rollback và recovery theo phiên bản đang chạy.

### 19.2. JMS không tự XA với JDBC

Transacted JMS session chỉ quản lý transaction ở JMS broker/session. Một `DataSourceTransactionManager` cục bộ không tự commit/rollback cả JMS. Khi thật sự cần atomic multi-resource commit, phải thiết kế JTA/XA với resource managers phù hợp; nhiều ứng dụng chọn outbox + idempotent receiver để giảm độ phức tạp.

## 20. SELECT–UPDATE transaction vẫn không tự ngăn hai pollers trùng row

~~~text
Pod A SELECT row 101 (state=NEW)
Pod B SELECT row 101 (state=NEW)
Pod A UPDATE row 101 -> CLAIMED, COMMIT
Pod B UPDATE row 101 WHERE state=NEW -> 0 rows
Pod B vẫn giữ row 101 trong result list cũ
Pod B có thể phát event 101 trùng
~~~

Ngay cả khi từng poll được bọc trong local JDBC transaction, câu `SELECT` thường không trao exclusive ownership nếu không có lock/claim policy phù hợp.

Production có thể dùng:
- `SELECT ... FOR UPDATE SKIP LOCKED` trong PostgreSQL cùng transaction;
- Atomic `UPDATE ... RETURNING` hoặc SQL Server `UPDATE ... OUTPUT` theo vendor;
- Lease `claimed_by/lease_until` và fencing token;
- Partition ownership phân chia khóa;
- Outbox + stable event ID + idempotent consumer.

Không giữ DB locks quá lâu khi đợi remote HTTP/Kafka. Claim/stage công việc bền vững trong một transaction ngắn, COMMIT, sau đó xử lý remote qua publisher/retry.

## 21. Deadlock, timeout và retry sau rollback

| Lỗi hoặc kết quả | Có nên retry? | Nguyên tắc |
|---|---|---|
| Deadlock/serialization | Có, có giới hạn | Rollback toàn TX, mở TX mới, backoff |
| Database connection transient | Có thể | Kiểm tra outcome gần COMMIT |
| SQL syntax/schema sai | Không | Sửa query/migration |
| Duplicate key cùng event ID | Theo business | Phân biệt duplicate với conflict |
| UPDATE version không khớp | Theo nghiệp vụ | Đọc state mới, không retry vô hạn |
| Broker publish timeout | Có thể | Stable event ID và reconciliation |
| Payload thiếu field | Không | Validation/DLQ |

Một JDBC transaction **có thể đã commit** nhưng response/connection bị mất khiến caller không biết chắc kết quả. Retry có nguy cơ lặp side effect; cần unique event ID, idempotency và khả năng đối soát.

`JdbcTemplate` thường ném `DataAccessException`; Spring Integration có thể bọc `MessagingException` hoặc chuyển qua `ErrorMessage`/`errorChannel` tùy handler và thread. Không coi mọi errorChannel message là bằng chứng transaction đã rollback; phải kiểm tra nơi exception bị bắt trước hay sau transactional advice.

## 22. Nhiều DataSource và transaction manager

Nếu ứng dụng có DB đơn hàng và DB audit khác nhau, `@Transactional` đơn giản không tự bảo đảm atomic trên cả hai:

~~~java
// Pseudo API: đây chỉ là minh họa về transaction boundary.
@Transactional(transactionManager = "ordersTransactionManager")
public void updateAcrossDatabases(String orderId) {
    // ordersJdbcTemplate: DB orders, nằm trong orders local TX
    // auditJdbcTemplate: DB audit khác, KHÔNG tự nằm cùng TX
}
~~~

`DataSourceTransactionManager`/`JdbcTransactionManager` gắn với **một DataSource**. Khi thao tác trên DB thứ hai, nó có thể dùng autocommit hoặc một transaction manager khác, tạo các kết quả commit không đồng bộ.

Những lựa chọn phù hợp: dùng một database nếu cần atomic local unit; dùng outbox/saga/compensation nếu có thể eventual consistency; hoặc thiết kế XA/JTA khi hệ thống thực sự cần atomic commit xuyên nhiều transactional resources và mọi resource đều hỗ trợ.

### 22.1. REQUIRES_NEW và kết nối bị giữ

Nếu outer transaction giữ một connection nhưng inner `REQUIRES_NEW` cần connection khác, 10 poller threads với pool size 10 có thể cùng giữ hết connections và chờ các inner transactions. Bài học là phải tính **pool capacity, transaction duration và propagation**, không tăng concurrency vô hạn.

## 23. Timeouts, readOnly và blocking I/O

| Thiết lập | Nơi tác động | Ý nghĩa |
|---|---|---|
| Hikari `connectionTimeout` | Connection pool | Thời gian chờ lấy connection |
| `JdbcTemplate.queryTimeout` | JDBC statement | Thời hạn query theo driver/DB |
| `@Transactional(timeout=...)` | Transaction manager | Giới hạn transaction theo cơ chế hỗ trợ |
| Gateway reply timeout | Messaging request–reply | Thời gian caller chờ reply |
| HTTP/Kafka send timeout | External client/broker | Không tự rollback JDBC đã commit |

`@Transactional(readOnly=true)` thường là hint/contract cho đọc, **không phải biện pháp phân quyền** bảo đảm DB từ chối UPDATE. Với JDBC inbound `SELECT` cộng `UPDATE` đánh dấu rows, transaction phải được cấu hình **read-write**.

JDBC và `JdbcTemplate` là **blocking I/O**. Trong WebFlux, không gọi chúng trên Reactor Netty event loop. Nếu cần integration với reactive endpoint, đặt toàn bộ phương thức JDBC `@Transactional` đồng bộ trong một bounded worker boundary hoặc dùng R2DBC khi yêu cầu reactive transaction end-to-end. Không tách nhiều JDBC operations của cùng transaction sang nhiều threads rồi giả định chúng dùng chung connection.

## 24. Test local JDBC rollback bằng TransactionTemplate

Một test cần xác minh **database state sau transaction** thay vì chỉ assert một method đã bị gọi. Ví dụ Spring Boot + H2:

~~~java
package com.example.jdbc.transaction;

import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class LocalJdbcTransactionTest {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PlatformTransactionManager manager;

    @Test
    void rollbackRestoresBusinessAndOutbox() {
        String orderId = "ORD-TX-" + UUID.randomUUID();
        String eventId = "evt-" + UUID.randomUUID();

        jdbc.update(
            "INSERT INTO order_projection(order_id,status,version) "
          + "VALUES (?, 'RECEIVED', 0)",
            orderId);

        TransactionTemplate tx = new TransactionTemplate(manager);

        assertThrows(IllegalStateException.class,
            () -> tx.executeWithoutResult(status -> {
                jdbc.update(
                    "UPDATE order_projection SET status='PAID' "
                  + "WHERE order_id=?",
                    orderId);
                jdbc.update(
                    "INSERT INTO event_outbox "
                  + "(event_id,aggregate_id,event_type,payload_json) "
                  + "VALUES (?,?,?,?)",
                    eventId, orderId, "order.paid", "{}");
                throw new IllegalStateException("failure before commit");
            }));

        String dbStatus = jdbc.queryForObject(
            "SELECT status FROM order_projection WHERE order_id=?",
            String.class, orderId);
        assertEquals("RECEIVED", dbStatus);

        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM event_outbox WHERE event_id=?",
            Integer.class, eventId);
        assertEquals(0, count);
    }
}
~~~

Test dùng ID riêng để không xung đột fixtures và **không gắn `@Transactional` trên test method**, vì một test-level transaction tự rollback có thể che vấn đề commit. Assertions sau exception đọc database khi TransactionTemplate đã hoàn tất.

### 24.1. Test COMMIT thành công

~~~java
// Mảnh code trong một test có sẵn jdbc/manager/orderId/eventId.
int updated = new TransactionTemplate(manager).execute(status -> {
    int rows = jdbc.update(
        "UPDATE order_projection SET status='PAID' "
      + "WHERE order_id=? AND status='RECEIVED'",
        orderId);
    jdbc.update(
        "INSERT INTO event_outbox "
      + "(event_id,aggregate_id,event_type,payload_json) "
      + "VALUES (?,?,?,?)",
        eventId, orderId, "order.paid", "{}");
    return rows;
});
~~~

Sau transaction, cần query lại row và outbox từ một JDBC operation độc lập để kiểm tra commit. Mảnh code không phải ứng dụng chạy độc lập; các biến phải được khởi tạo trong test.

## 25. Test rollback trong JDBC inbound flow

Với flow mục 8, một integration test nên khởi tạo các rows `NEW`, chạy **đúng một poll** trong transaction, cho handler ghi outbox rồi ném lỗi ở phần tử thứ hai và kiểm tra mọi rows vẫn `NEW` sau rollback.

| Test | Điều cần khẳng định |
|---|---|
| SELECT + UPDATE + writer đồng bộ thành công | CLAIMED và outbox commit cùng nhau |
| Handler đồng bộ ném RuntimeException | UPDATE và outbox rollback |
| Handler bắt lỗi rồi return | Có thể COMMIT; kiểm tra thiết kế |
| Chèn `ExecutorChannel` trước writer | DB poller COMMIT không chờ worker |
| Chèn `QueueChannel` rồi poller khác | Transaction của consumer độc lập |
| Duplicate outbox event ID | Unique constraint/error policy rõ |
| 2 instances SELECT cùng row | Không mặc định có exclusive ownership |
| Transaction manager khác DataSource | Test phát hiện unintended autocommit |
| Metadata checkpoint cùng outbox local TX | Rollback chung khi lỗi |
| Broker đã nhận nhưng chưa ACK nguồn | Có thể redeliver, idempotency hoạt động |

**Test setup:** disable các pollers nền không liên quan; tránh test song song sửa cùng bảng; kiểm soát scheduler, sample data, consumer và error channel.

### 25.1. Dùng TransactionTemplate mô phỏng synchronous receive

Nếu muốn test riêng một source mà không chờ lịch poll, có thể gọi `JdbcPollingChannelAdapter.receive()` và xử lý payload trong một `TransactionTemplate` tường minh. Sau đó ném exception để xác minh rollback. Điều này test **các JDBC operations cùng transaction**, nhưng chưa chứng minh mọi cấu hình retry/error của `SourcePollingChannelAdapter` hoạt động; nên có thêm test chạy poller thật.

### 25.2. Test ranh giới bất đồng bộ

Đặt một `ExecutorChannel` hoặc `QueueChannel` có test-controlled consumer. Cho poller hoàn tất COMMIT trước, rồi mới cho worker ném lỗi. Kỳ vọng lỗi worker **không rollback được trạng thái CLAIMED đã commit**. Khi cần không mất dữ liệu, test thêm outbox/lease/recovery chứ không chỉ test errorChannel.

## 26. Test database concurrency và crash windows

H2 hữu ích cho local transaction nhưng không đủ xác nhận locking/isolation trên production DB. Dùng Testcontainers hoặc một test database đúng vendor cho:

1. Hai transactions UPDATE cùng row với expected version.
2. Deadlock/serialization conflict và retry toàn transaction.
3. `FOR UPDATE SKIP LOCKED`, `UPDATE ... RETURNING` hoặc `OUTPUT` theo vendor.
4. Crash sau claim/DB commit trước khi gửi broker.
5. Broker ACK xong nhưng app chết trước khi outbox đánh dấu `published`.
6. `REQUIRES_NEW` trong hoàn cảnh connection pool nhỏ/concurrency cao.
7. Nested transaction/savepoint nếu ứng dụng dùng.
8. Source/poller có transaction manager sai database.
9. Kafka/JMS redelivery và processed-event ID uniqueness.
10. Kết hợp polling và transaction synchronization trước/sau commit.

**Không tuyên bố exactly-once chỉ vì một test không thấy duplicate.** Cần fault injection tại các cửa sổ crash và xác minh trạng thái business, outbox, broker, retry backlog và processed-event store.

## 27. Theo dõi vận hành transaction

Các metrics hữu ích:
- Transaction count, commit/rollback count, transaction duration, rollback-only outcomes.
- SQL SELECT/UPDATE latency, `UPDATED=0`, deadlocks, lock waits, query timeout.
- Hikari active/idle/pending connections, thời gian lấy connection và acquire failures.
- Poll frequency, rows/poll, `maxMessagesPerPoll`, queue depth và consumer lag.
- Outbox pending count/oldest age, publish attempts, broker ACKs và duplicate event IDs.
- `errorChannel`/DLQ count, retry rate, failed message correlation ID.
- Rows kẹt `CLAIMED`, expired leases, recovery attempts.

Không gắn từng `orderId/eventId` thành metric tag cardinality cao. Đưa ID vào logs/traces có hạn chế PII và secret.

### 27.1. Quan sát transaction đang active trên thread

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
~~~

Đây chỉ là tín hiệu debug; `true` không chứng minh transaction manager đã bind đúng DataSource hoặc commit cuối cùng thành công. Dùng thử ở DirectChannel handler và ExecutorChannel worker để thấy thread-bound transaction không truyền tự động.

## 28. Bảo mật và tính ổn định

- Bind tham số SQL bằng `PreparedStatement`/named parameters; không nối input message thành SQL.
- Giới hạn quyền DB account theo bảng/procedure thật sự cần; dùng TLS và secret manager.
- Tránh giữ transaction mở khi chờ network I/O hoặc một callback Kafka lâu.
- Giới hạn Hikari pool, bounded executor, số pollers, batch size, statement timeout và retry attempts.
- Với tenants, kiểm tra authorization trước DML; đừng tin header `tenantId` do client tự cung cấp.
- Áp dụng unique business event ID, optimistic version, atomic claim hoặc outbox cho redelivery/concurrency.
- Bảo vệ migration schema outbox/metadata khi deployments cũ và mới cùng chạy.

## 29. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Có IntegrationFlow là có transaction” | Boundary phải được cấu hình |
| “@Transactional trên method tự gọi luôn áp dụng” | Self-invocation thường bypass proxy |
| “Transaction JDBC truyền qua ExecutorChannel” | Thread-bound transaction không tự truyền |
| “QueueChannel in-memory là durable work queue” | Có thể mất khi crash |
| “send() true nghĩa DB và broker đã commit” | Chỉ nói về channel send |
| “Gateway trả UPDATED=1 nghĩa commit cuối cùng” | Outer TX vẫn có thể rollback |
| “Checked exception luôn rollback mặc định” | Phụ thuộc rollback rules |
| “REQUIRES_NEW luôn an toàn hơn” | Có thể làm cạn pool và chia tách atomicity |
| “readOnly=true chặn mọi SQL UPDATE” | Không thay thế DB permissions |
| “READ_COMMITTED ngăn mọi race” | Cần locking/version/ownership |
| “SELECT rồi UPDATE ngăn mọi duplicate giữa pods” | Hai pods có thể SELECT cùng row |
| “JDBC @Transactional tự bao Kafka/JMS” | Local TX không phân tán |
| “afterCommit callback đảm bảo event Kafka đã gửi” | Crash sau DB COMMIT vẫn có thể mất publish |
| “Retry timeout không gây side effect trùng” | Outcome có thể đã commit; cần idempotency |
| “JDBC trong WebFlux không blocking” | JDBC vẫn blocking |
| “Test @Transactional thấy data là đã COMMIT” | Test TX có thể tự rollback |
| “Một transaction manager bao hai databases” | Cần XA/JTA hoặc thiết kế khác |

## 30. Bài thực hành

1. Dựng schema `payment_event`, `order_projection` và `event_outbox` trên H2.
2. Dùng `TransactionTemplate` UPDATE và INSERT rồi COMMIT; assert trạng thái DB.
3. Ném exception sau INSERT và xác minh rollback cả business/outbox.
4. Dùng `PaymentService @Transactional` qua một `@ServiceActivator`; so sánh với self-invocation.
5. Tạo JDBC inbound `SELECT NEW + UPDATE CLAIMED` với transactional poller Java DSL 7.x.
6. Dùng `JdbcPollingChannelAdapter` ở Spring Integration 6.x để tạo flow tương ứng.
7. Viết XML `<int:transactional/>` cho poller và xác định đúng transaction manager.
8. Cho outbox writer DirectChannel ném lỗi ở row thứ hai, xác nhận cả batch rollback.
9. Thêm ExecutorChannel trước writer, kiểm tra transaction của poller kết thúc sớm.
10. Đưa message qua QueueChannel và poller thứ hai, giải thích transaction độc lập.
11. Gọi JDBC outbound gateway nhận `UPDATED=1` rồi rollback outer transaction để kiểm tra commit receipt.
12. Thử `REQUIRED` và `REQUIRES_NEW`, quan sát rollback khi outer service thất bại.
13. Giảm pool size khi có inner `REQUIRES_NEW` và theo dõi connection waits.
14. Dùng version column, gửi hai commands có cùng expected version để tạo conflict.
15. Tạo race hai pollers SELECT cùng rows, phân biệt transaction với ownership.
16. Trên PostgreSQL, kiểm thử `FOR UPDATE SKIP LOCKED` và atomic claim.
17. Viết transactional outbox publisher và mô phỏng crash trước/sau broker ACK.
18. Tạo processed-event unique constraint, kiểm tra Kafka/JMS redelivery không lặp effect.
19. Thử `TransactionSynchronization.afterCommit` và phân tích cửa sổ lỗi trước callback.
20. Mô phỏng deadlock rồi retry toàn transaction với backoff.
21. Test `DataAccessException`, `MessagingException` và `errorChannel` khi dùng DirectChannel/ExecutorChannel.
22. Chia hai DataSources, chọn đúng transaction manager, nhận diện khi nào cần outbox/saga.
23. Thử cấu hình `@Transactional(readOnly=true)` không phù hợp trên SELECT+UPDATE flow.
24. Xây dashboard cho commit/rollback, pool wait, outbox lag và retry/DLQ.

**Tình huống tổng hợp:** hai pods poll bảng `payment_event`, stage outbox rồi phát Kafka. Pod A đọc 25 rows, lỗi tại hàng outbox thứ ba; Pod B đồng thời đọc vài rows giống Pod A. Outbox publisher gửi một event rồi crash trước khi đánh dấu `published`. Hãy thiết kế transactional poller, atomic claim/locking, unique event IDs, retry và idempotent consumer. Vẽ khác biệt commit/rollback khi luồng chạy qua DirectChannel và khi chuyển sang ExecutorChannel.

## 31. Tài liệu tham khảo

- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): transaction boundaries theo threads/channels và TransactionSynchronizationFactory.
- [Spring Integration Reference — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): SELECT + UPDATE trong transactional poller, `maxRows` và `maxMessagesPerPoll`.
- [Spring Integration Reference — Messaging Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html): poller transactions, advice và error flow.
- [Spring Integration Reference — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): inbound/outbound adapters, gateways, stored procedures.
- [Spring Integration Reference — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.inboundAdapter` và `Jdbc.outboundGateway` từ 7.0.
- [Spring Integration Reference — JDBC Outbound Gateway](https://docs.spring.io/spring-integration/reference/jdbc/outbound-gateway.html): `UPDATED`, generated keys và reply.
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxy/propagation/rollback.
- [Spring Framework Reference — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate`.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `PlatformTransactionManager`, `JdbcTransactionManager` và transaction synchronization.
- [Spring Framework Reference — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate` và exception translation.

> **Ghi nhớ:** transaction trên flow JDBC là **ranh giới commit/rollback của một unit of work**, không phải thuộc tính tự động của mọi IntegrationFlow. Poller có thể bao SELECT, UPDATE và handler chạy đồng bộ cùng thread/DataSource; ExecutorChannel/QueueChannel tách transaction context. `@Transactional` và `TransactionTemplate` phải đặt đúng bean proxy, manager và thread. Khi cần ghi DB rồi gửi Kafka/JMS/HTTP, local JDBC transaction không tự commit phân tán: hãy dùng outbox, stable event ID, retry và idempotency.

