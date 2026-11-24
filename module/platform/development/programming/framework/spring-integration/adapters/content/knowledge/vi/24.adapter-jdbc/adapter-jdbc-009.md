# Polling query và trạng thái đã đọc trong Spring Integration JDBC

## 1. Bài toán: đọc dữ liệu theo chu kỳ nhưng không đọc lặp vô hạn

Một ứng dụng cần lấy những bản ghi chờ đồng bộ từ database và đẩy sang Kafka, JMS, AMQP hoặc HTTP. Nếu cứ chạy câu lệnh `SELECT * FROM integration_event WHERE state = 'NEW'` mỗi vài giây mà không đổi trạng thái, các bản ghi cũ sẽ được gửi đi **mỗi lần poll**. Nếu đánh dấu `DONE` ngay khi đọc nhưng ứng dụng chết trước khi gửi thành công, sự kiện có thể **bị mất**.

**JDBC inbound channel adapter** của Spring Integration xử lý phần cơ bản của bài toán này: **poller** gọi SQL `SELECT`; tùy cấu hình, adapter chạy thêm SQL `UPDATE` để thay đổi trạng thái của những hàng vừa đọc; sau đó nó phát một `Message<?>` vào `MessageChannel`.

Bài học thuộc chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**. Phạm vi module là kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và MessageChannel, bao gồm file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; bài này tập trung vào **truy vấn polling, trạng thái đã đọc, transaction, xử lý lỗi, ACK và khả năng khôi phục**.

~~~mermaid
flowchart LR
    P["Poller / Scheduler"] --> A["JDBC inbound channel adapter"]
    A --> S["SELECT các rows đủ điều kiện"]
    S --> DB[("Database")]
    DB --> R["List<Row>"]
    R --> U["UPDATE trạng thái đã đọc/CLAIMED"]
    U --> DB
    R --> M["Message<List<Row>>"]
    M --> F["Splitter / Transformer"]
    F --> D["Kafka / JMS / HTTP / handler"]
    D -.->|"ACK/commit riêng"| K["Đối soát và hoàn tất"]
~~~

**Điểm cốt lõi:** “đã đọc” chỉ xác nhận hệ thống **đã chọn** row trong một lượt SELECT. “Đã claim” xác nhận database đã ghi quyền sở hữu/trạng thái cho công việc. “Đã xử lý” đòi bằng chứng từ bước nghiệp vụ và hệ thống đích. Ba mốc này **không tương đương**.

## 2. Phân biệt SELECT, UPDATE và trạng thái nghiệp vụ

| Hoạt động | Ý nghĩa | Điều chưa được chứng minh |
|---|---|---|
| `SELECT` lấy row `NEW` | Row đủ điều kiện tại thời điểm query | Row được sở hữu độc quyền; downstream đã làm xong |
| `UPDATE` từ `NEW` sang `CLAIMED` | DB ghi trạng thái đang được worker xử lý | Kafka/JMS/HTTP đã nhận |
| `UPDATE` từ `CLAIMED` sang `DONE` | Ứng dụng đã ghi nhận thành công theo policy | Mọi consumer bên ngoài đều hoàn tất end-to-end |
| `ACK` nguồn broker | Broker ghi nhận consumer đã xử lý/nhận message theo cơ chế cụ thể | DB và broker có commit nguyên tử |
| Outbox `PUBLISHED` | Publisher đã ghi nhận thành công theo hợp đồng gửi | Consumer đích chưa chắc xử lý đúng một lần |

Một state machine thực tế:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> CLAIMED: Poll + atomic claim
    CLAIMED --> DONE: Xử lý và xác nhận thành công
    CLAIMED --> RETRY: Lỗi transient / hết lease
    RETRY --> CLAIMED: Claim lại có kiểm soát
    RETRY --> FAILED: Vượt retry / lỗi dữ liệu
    FAILED --> NEW: Manual replay sau sửa lỗi
    DONE --> [*]
~~~

Không nhất thiết mọi dự án phải lưu đủ các trạng thái trên. Nếu dùng **transactional outbox**, ta có thể tổ chức lifecycle bằng `NEW/PUBLISHED` cùng bộ đếm attempt và thời gian retry. Điều bắt buộc là **hợp đồng về trạng thái và thời điểm được phép chuyển trạng thái phải rõ ràng**.

## 3. JDBC inbound adapter khác polling thủ công như thế nào?

| Giải pháp | Động lực chạy | Cách có dữ liệu | Phần phải tự làm |
|---|---|---|---|
 `JdbcPollingChannelAdapter` | Spring Integration poller | SELECT + optional UPDATE, trả message | Quy tắc claim/recovery, idempotency, downstream |
 `JdbcTemplate` trong `@Scheduled` | Spring scheduler | Repository tự query | Tạo/dispatch message, error flow, transaction |
 JDBC inbound stored procedure | Spring Integration poller | Gọi routine, nhận result set/OUT | Thiết kế routine, mapping và recovery |
 Kafka/JMS inbound adapter | Broker listener/poller theo adapter | Broker cung cấp messages | ACK/offset, retry/DLQ, DB integration |
 CDC/outbox relay | Theo log/broker/publisher | Theo dõi DB changes hoặc outbox | Semantics redelivery, checkpoint và idempotency |

JDBC inbound adapter **không nhận request message** để bắt đầu query. Một `SourcePollingChannelAdapter` hỏi `MessageSource.receive()` theo lịch, rồi chuyển kết quả vào integration flow.

**Khi nào phù hợp?** Một bảng outbox hoặc bảng pending jobs có trạng thái rõ, SQL đơn giản, tốc độ đọc vừa phải, không yêu cầu CDC theo từng thay đổi. Nếu các business events phải có bảo đảm mạnh khi nhiều instances, cần bổ sung atomic claim/outbox hoặc chọn kiến trúc event relay chuyên dụng.

## 4. Hợp đồng payload: mỗi poll thường phát một message chứa List

Theo tài liệu Spring Integration JDBC, kết quả `SELECT` được biểu diễn thành **toàn bộ result set dưới dạng `List`**. Mặc định mỗi row được map thành `Map<String,Object>`; khi cung cấp `RowMapper<T>`, mỗi row được map thành `T`.

~~~text
SELECT trả 3 rows
  -> JdbcPollingChannelAdapter
  -> Message<List<Map<String,Object>>>
  hoặc Message<List<EventRecord>> nếu có RowMapper
  -> Splitter
  -> 3 x Message<EventRecord>
~~~

| Thành phần | Đơn vị | Ví dụ |
|---|---|---|
| Một hàng trong `ResultSet` | Row | Event có ID 101 |
| Kết quả một `SELECT` | List | Events 101, 102, 103 |
| Adapter phát sau một `receive()` | Message có payload List | Một `Message<List<EventRecord>>` |
| `Splitter` downstream | Message cho từng phần tử | Ba `Message<EventRecord>` |

Không đưa handler có signature `process(EventRecord)` ngay sau adapter khi payload thực tế còn là `List<EventRecord>`. Thêm `.split()` hoặc một transformer có hợp đồng rõ ràng.

**Trường hợp không có hàng:** thường không có business data để xử lý. Việc adapter phát hay không phát một message rỗng cần kiểm chứng theo phiên bản, cấu hình và downstream; không suy luận một `List.empty()` chính là một lỗi SQL.

## 5. Dự án Spring Boot và schema thực hành

Ví dụ sử dụng Java 17+, Spring Boot, Spring JDBC và Spring Integration JDBC. H2 chỉ phục vụ test logic cơ bản; cơ chế locking giữa nhiều instances sẽ cần database đúng vendor.

~~~groovy
// build.gradle: sử dụng Spring Boot BOM quản lý phiên bản tương thích.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml cho demo
spring:
  datasource:
    url: "jdbc:h2:mem:polling_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

Với ứng dụng demo, đặt DDL sau trong `src/main/resources/schema.sql`. Đây là **mẫu minh họa**, không phải file mà worker cần tạo trong repository bài học.

~~~sql
CREATE TABLE integration_event (
    id            BIGINT NOT NULL PRIMARY KEY,
    event_id      VARCHAR(80) NOT NULL UNIQUE,
    event_type    VARCHAR(80) NOT NULL,
    payload_json  VARCHAR(2000) NOT NULL,
    state         VARCHAR(24) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    claimed_by    VARCHAR(100),
    claimed_at    TIMESTAMP,
    lease_until   TIMESTAMP,
    completed_at  TIMESTAMP,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_event_polling
    ON integration_event (state, created_at, id);
~~~

Một số dữ liệu ban đầu:

~~~sql
INSERT INTO integration_event
    (id, event_id, event_type, payload_json, state)
VALUES
    (101, 'evt-101', 'order.created',
     '{"orderId":"ORD-1001"}', 'NEW'),
    (102, 'evt-102', 'order.paid',
     '{"orderId":"ORD-1002"}', 'NEW'),
    (103, 'evt-103', 'order.shipped',
     '{"orderId":"ORD-1003"}', 'NEW'),
    (104, 'evt-104', 'order.cancelled',
     '{"orderId":"ORD-1004"}', 'DONE');
~~~

`event_id` là **ID ổn định theo nghiệp vụ**, dùng để khử trùng lặp khi message được phát lại. Không sinh lại event ID mỗi lần poll. `claimed_by`, `claimed_at` và `lease_until` phục vụ hướng mở rộng recovery; ví dụ cơ bản chỉ đổi `NEW → CLAIMED`.

## 6. Viết polling query đúng: WHERE, ORDER BY và giới hạn lô

SQL cơ bản:

~~~sql
SELECT
    id, event_id, event_type, payload_json,
    state, attempt_count, created_at
FROM integration_event
WHERE state = 'NEW'
ORDER BY created_at, id;
~~~

**Vì sao phải có điều kiện `WHERE`?** Nếu SELECT tất cả rows, bản ghi `CLAIMED`/`DONE` vẫn được đọc lại ở mọi poll.

**Vì sao phải có `ORDER BY`?** Không có ORDER BY, database **không cam kết** thứ tự hàng. Nếu business cần ưu tiên dữ liệu cũ, chọn `created_at, id` và index theo điều kiện truy vấn. Thứ tự SELECT không đồng nghĩa thứ tự publish khi downstream dùng `flatMap`, executor nhiều threads hoặc Kafka có nhiều partitions.

**Giới hạn tại DB:** để chỉ lấy 20 events trong một lượt, H2/PostgreSQL có thể dùng:

~~~sql
SELECT id, event_id, event_type, payload_json,
       state, attempt_count, created_at
FROM integration_event
WHERE state = 'NEW'
ORDER BY created_at, id
LIMIT 20;
~~~

SQL Server dùng `TOP (20)` hoặc `OFFSET/FETCH`; Oracle có cách giới hạn riêng. Chọn cú pháp đúng theo database vendor. `LIMIT` là cú pháp của ví dụ H2/PostgreSQL, không phải SQL portable hoàn toàn.

**Không lấy một bảng hàng triệu rows rồi kỳ vọng `RowMapper` hoặc `splitter` làm chức năng pagination.** Giới hạn từ SQL làm giảm I/O và thời gian giữ connection; `maxRows` của adapter vẫn có thể dùng như giới hạn bảo vệ bổ sung.

## 7. UPDATE trạng thái sau SELECT: mẫu đơn giản

Sau khi chọn ID `101, 102, 103`, chạy:

~~~sql
UPDATE integration_event
SET state = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP,
    attempt_count = attempt_count + 1
WHERE id IN (:ids) AND state = 'NEW';
~~~

`:ids` là **named parameter** của Spring JDBC, được bind bằng danh sách IDs do adapter lấy từ kết quả SELECT. Khi danh sách là `[101,102,103]`, Spring JDBC mở rộng placeholders phù hợp; không nối trực tiếp chuỗi IDs vào SQL.

Nếu chỉ cần quy tắc mặc định, Spring Integration JDBC inbound adapter hỗ trợ tham số `:id` dựa trên một cột `id` trong kết quả SELECT:

~~~xml
<!-- Fragment XML rút gọn: default id projection. -->
<int-jdbc:inbound-channel-adapter
    data-source="dataSource"
    channel="eventBatches"
    query="SELECT id, event_id, event_type
           FROM integration_event
           WHERE state='NEW' ORDER BY id"
    update="UPDATE integration_event
            SET state='CLAIMED'
            WHERE id IN (:id) AND state='NEW'">
    <int:poller fixed-delay="3000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

Đoạn XML cần khai báo các namespace `int`/`int-jdbc` và bean `transactionManager`, `dataSource` trong application context. Không chạy cùng Java DSL flow ở mục sau nếu cùng bảng và cùng trạng thái, trừ khi đang chủ ý thử concurrency.

**Điều UPDATE không tự xác nhận:** nếu một instance khác vừa claim row trước, câu UPDATE có thể tác động **0 hàng**. Danh sách trả từ SELECT ban đầu vẫn có thể chứa row đó; nếu downstream publish dựa trên danh sách mà không kiểm tra quyền claim, có thể xảy ra duplicate.

## 8. Java DSL 7.x: triển khai SELECT → UPDATE → Message

Từ **Spring Integration 7.0**, module JDBC có factory `Jdbc.inboundAdapter(...)` và builder `JdbcInboundChannelAdapterSpec`. Các API này **không có cùng factory trong Spring Integration 6.x**; cách triển khai 6.x nằm ở mục 10.

### 8.1. DTO và RowMapper

~~~java
package com.example.polling;

import java.time.LocalDateTime;

public record EventRecord(
    long id,
    String eventId,
    String eventType,
    String payloadJson,
    String state,
    int attemptCount,
    LocalDateTime createdAt) {
}
~~~

~~~java
package com.example.polling;

import java.sql.Timestamp;
import org.springframework.jdbc.core.RowMapper;

public final class EventRecordRowMapper implements RowMapper<EventRecord> {

    @Override
    public EventRecord mapRow(
            java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException {

        Timestamp created = rs.getTimestamp("created_at");
        if (created == null) {
            throw new java.sql.SQLException(
                "created_at unexpectedly NULL");
        }

        return new EventRecord(
            rs.getLong("id"),
            rs.getString("event_id"),
            rs.getString("event_type"),
            rs.getString("payload_json"),
            rs.getString("state"),
            rs.getInt("attempt_count"),
            created.toLocalDateTime());
    }
}
~~~

Với các cột numeric nullable, `rs.getInt`/`rs.getLong` có thể trả 0 cho SQL NULL, nên cần `rs.wasNull()` hoặc wrapper types. Trong schema demo, `id`/`attempt_count` không cho phép NULL. `LocalDateTime` không mang timezone; production phải xác định rõ DB lưu local time hay UTC và cách JDBC driver diễn giải.

### 8.2. IntegrationFlow dùng custom parameter source cho UPDATE

~~~java
package com.example.polling;

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
public class EventPollingFlow {

    @Bean
    public IntegrationFlow pollPendingEvents(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        String selectSql = """
            SELECT id, event_id, event_type, payload_json,
                   state, attempt_count, created_at
            FROM integration_event
            WHERE state = 'NEW'
            ORDER BY created_at, id
            LIMIT 20
            """;

        String updateSql = """
            UPDATE integration_event
            SET state = 'CLAIMED',
                claimed_at = CURRENT_TIMESTAMP,
                attempt_count = attempt_count + 1
            WHERE id IN (:ids) AND state = 'NEW'
            """;

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource, selectSql)
                    .rowMapper(new EventRecordRowMapper())
                    .maxRows(20)
                    .updateSql(updateSql)
                    .updatePerRow(false)
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> rows = (List<?>) result;
                        List<Long> ids = rows.stream()
                            .map(EventRecord.class::cast)
                            .map(EventRecord::id)
                            .toList();
                        return new MapSqlParameterSource("ids", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(3))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .filter(payload ->
                payload instanceof List<?> rows && !rows.isEmpty())
            .split()
            .channel("claimedEvents")
            .get();
    }
}
~~~

Đây là một **mẫu một-instance để học**, dùng SQL `LIMIT` của H2/PostgreSQL. Kết quả của flow:

1. Poller gọi `receive()` mỗi 3 giây theo fixed delay.
2. `SELECT` lấy tối đa 20 rows `NEW`.
3. `RowMapper` chuyển từng row thành `EventRecord`.
4. `updateSqlParameterSourceFactory` nhận **`List<EventRecord>`**, tạo `ids` để bind vào `UPDATE`.
5. `UPDATE` đánh dấu những IDs này là `CLAIMED`, tăng `attempt_count`.
6. Adapter phát payload `List<EventRecord>`; `filter` bỏ lô rỗng và `split()` tạo từng `Message<EventRecord>`.
7. Downstream trên channel `claimedEvents` tiêu thụ từng event.

**Quan trọng về dữ liệu trong DTO:** `EventRecord.state()` vẫn có thể là `NEW` vì được map từ `SELECT` **trước** khi UPDATE. Không dựa vào trường này để khẳng định row đã được claim hoặc đã publish. Khi cần kiểm chứng trạng thái hiện tại, đọc lại database/metadata xử lý theo hợp đồng riêng.

### 8.3. Consumer cho từng event

~~~java
package com.example.polling;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class ClaimedEventHandler {

    @ServiceActivator(inputChannel = "claimedEvents")
    public void process(EventRecord event) {
        System.out.printf("Received event %s%n", event.eventId());
        // Demo: thực tế hãy gọi service hoặc adapter có error/ACK policy.
    }
}
~~~

`System.out.printf` chỉ minh họa một subscriber đồng bộ. Nó không chứng minh việc gửi Kafka/JMS hoặc nghiệp vụ đã thành công. Nếu handler ném exception trong **cùng thread và transaction của poller**, DB update có thể rollback; nếu handler chuyển việc sang thread/queue khác, commit boundary thay đổi.

## 9. maxRows và maxMessagesPerPoll không cùng đơn vị

Theo Spring Integration Reference:

| Cấu hình | Đơn vị | Mặc định đáng lưu ý | Kết quả |
|---|---|---|---|
| Adapter `maxRows` | Số rows được dùng từ kết quả query | **0** = không giới hạn | Ví dụ `maxRows(20)` giới hạn tối đa 20 rows |
| Poller `maxMessagesPerPoll` | Số lần hỏi `receive()` mỗi trigger | Thường **1** cho JDBC inbound | Ví dụ 1 lần SELECT/trigger |
| Poller `fixedDelay` | Khoảng cách thời gian | Do bạn cấu hình | Ví dụ 3 giây sau khi lượt trước hoàn tất |
| SQL `LIMIT/TOP/FETCH` | Số rows do DB trả | Phụ thuộc SQL | Giới hạn từ server |
| Splitter | Số messages sinh ra từ một list | Phụ thuộc số phần tử | 20 rows → 20 messages nếu split |

Ví dụ có 57 sự kiện đang `NEW`:

~~~text
maxRows(20), maxMessagesPerPoll(1), update state NEW -> CLAIMED

Poll 1 -> SELECT 20 rows -> UPDATE 20 -> 1 batch message -> 20 item messages
Poll 2 -> SELECT 20 rows -> UPDATE 20 -> 1 batch message -> 20 item messages
Poll 3 -> SELECT 17 rows -> UPDATE 17 -> 1 batch message -> 17 item messages
Poll 4 -> SELECT 0 rows  -> không có business rows để xử lý
~~~

Tăng `maxMessagesPerPoll` lên 3 có thể khiến poller **gọi lại SELECT/UPDATE nhiều lần trong cùng một lần trigger**, không phải chỉ làm query trả ba hàng. Với JDBC, mặc định 1 thường hợp lý hơn cho khả năng kiểm soát tải.

**Mẹo thực tế:** đặt giới hạn ngay trong SQL và thêm `maxRows` như một hàng rào. Một SELECT quá rộng vẫn có thể làm DB quét nhiều dữ liệu, dù Java không đưa tất cả rows vào message.

## 10. Spring Integration 6.x: dùng JdbcPollingChannelAdapter trực tiếp

Ở **6.x**, `JdbcPollingChannelAdapter` vẫn hỗ trợ `SELECT`, `UPDATE`, `RowMapper`, `setMaxRows`, `setUpdateSqlParameterSourceFactory` và `setUpdatePerRow`. Bạn có thể tạo `MessageSource` rồi đưa vào Java DSL thông thường:

~~~java
package com.example.polling;

import java.time.Duration;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class LegacyEventPollingFlow {

    @Bean
    public IntegrationFlow legacyPollEvents(
            DataSource dataSource,
            PlatformTransactionManager tx) {

        var source = new JdbcPollingChannelAdapter(
            dataSource,
            "SELECT id, event_id, event_type, payload_json, "
          + "state, attempt_count, created_at "
          + "FROM integration_event WHERE state = 'NEW' "
          + "ORDER BY created_at, id");

        source.setRowMapper(new EventRecordRowMapper());
        source.setMaxRows(20);
        source.setUpdateSql(
            "UPDATE integration_event "
          + "SET state = 'CLAIMED', claimed_at = CURRENT_TIMESTAMP "
          + "WHERE id IN (:ids) AND state = 'NEW'");
        source.setUpdateSqlParameterSourceFactory(result -> {
            List<?> rows = (List<?>) result;
            List<Long> ids = rows.stream()
                .map(EventRecord.class::cast)
                .map(EventRecord::id)
                .toList();
            return new MapSqlParameterSource("ids", ids);
        });

        return IntegrationFlow.from(source, e ->
                e.poller(Pollers.fixedDelay(Duration.ofSeconds(3))
                    .maxMessagesPerPoll(1)
                    .transactional(tx)))
            .filter(payload ->
                payload instanceof List<?> rows && !rows.isEmpty())
            .split()
            .channel("legacyClaimedEvents")
            .get();
    }
}
~~~

**Khác biệt phiên bản:** `Jdbc.inboundAdapter(...)` Java DSL factory là API được giới thiệu ở Spring Integration 7.0; còn `JdbcPollingChannelAdapter` có mặt từ trước, nên phù hợp cho 6.x. Ví dụ 6.x dùng trực tiếp source và **không** ép thư viện 7.x vào classpath.

Mặc dù code cùng ý tưởng, phiên bản sản phẩm thật phải được kiểm tra với BOM và Java/JDK tương ứng. Bài chưa chạy compile; STEP 6 có thể kiểm thử/làm rõ API theo phiên bản cụ thể.

## 11. XML: cấu hình SELECT, UPDATE và transactional poller

Spring Integration JDBC cũng hỗ trợ XML namespace:

~~~xml
<!-- Fragment: context cần khai báo namespace int và int-jdbc. -->
<int:channel id="dbEventBatches"/>

<int-jdbc:inbound-channel-adapter
    id="dbEventPoller"
    data-source="dataSource"
    channel="dbEventBatches"
    query="SELECT id, event_id, event_type
           FROM integration_event
           WHERE state = 'NEW'
           ORDER BY id"
    update="UPDATE integration_event
            SET state = 'CLAIMED'
            WHERE id IN (:id) AND state = 'NEW'"
    max-rows="20">

    <int:poller fixed-delay="3000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

Trong XML, `query` là `SELECT`; `update` là câu SQL đánh dấu hàng đã lấy; `:id` dùng quy ước mặc định lấy các IDs từ result set. `dbEventBatches` nhận một message chứa list; để có từng event, định nghĩa splitter downstream. Hai ví dụ XML/Java là **phương án thay thế**, không bật cả hai cùng source nếu chỉ đang làm demo một worker.

### 11.1. SELECT có tham số động

Đôi khi không thể hardcode `state='NEW'` mà phải truyền vào:

~~~sql
SELECT id, event_id, event_type
FROM integration_event
WHERE state = :wantedState
ORDER BY id;
~~~

Sử dụng `selectSqlParameterSource` trong DSL hoặc `setSelectSqlParameterSource(...)` ở `JdbcPollingChannelAdapter`. Khác với UPDATE, tham số SELECT được tạo **trước khi có kết quả query**:

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var selectParams = new MapSqlParameterSource(
    "wantedState", "NEW");

// Trong JdbcInboundChannelAdapterSpec 7.x:
.selectSqlParameterSource(selectParams)
~~~

Đây là một **mảnh DSL**, chỉ dùng bên trong chain khai báo source. Với tham số cần thay đổi từng poll bằng SpEL, có thể dùng `ExpressionEvaluatingSqlParameterSourceFactory.createParameterSourceNoCache(...)` theo tài liệu Spring Integration; không cấu hình nhầm UPDATE factory để cấp tham số cho SELECT.

## 12. updatePerRow, SqlParameterSourceFactory và RowMapper

UPDATE có hai chiến lược:

| Cơ chế | Đầu vào factory | SQL thường dùng |
|---|---|---|
| `updatePerRow(false)` (mặc định) | `List` toàn bộ rows đã SELECT | `WHERE id IN (:ids)` |
| `updatePerRow(true)` | Từng row của kết quả | `WHERE id = :rowId` |

Với RowMapper map thành `EventRecord`, factory cần đọc `EventRecord.id()`; với mapper mặc định, factory thường nhận row dạng `Map`. **Chuyển từ Map sang record nhưng quên cập nhật factory** rất dễ tạo `ClassCastException`.

Ví dụ per-row:

~~~java
// Mảnh cấu hình JdbcInboundChannelAdapterSpec 7.x:
.updateSql(
    "UPDATE integration_event "
  + "SET state='CLAIMED' WHERE id=:rowId AND state='NEW'")
.updatePerRow(true)
.updateSqlParameterSourceFactory(row ->
    new MapSqlParameterSource(
        "rowId", ((EventRecord) row).id()))
~~~

`updatePerRow(true)` **không** có nghĩa một transaction riêng hoặc một message riêng cho mỗi row. Nó chỉ làm thay đổi số lần/đơn vị UPDATE. Nếu muốn mỗi row thành message, thêm `Splitter`; nếu muốn transaction riêng, cấu hình transaction boundaries chủ động.

`ExpressionEvaluatingSqlParameterSourceFactory` có thể thay lambda và đánh giá SpEL trên **cả list** hoặc **row hiện tại** theo `updatePerRow`. Không đặt biểu thức SpEL tùy ý trực tiếp vào named parameter `:rowId` — SQL chỉ biết tên parameter.

## 13. Transaction của poller bảo vệ được phần nào?

Spring Integration cho phép **bọc một lần poll** trong Spring transaction:

~~~java
endpoint -> endpoint.poller(
    Pollers.fixedDelay(Duration.ofSeconds(3))
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
~~~

Nếu `transactionManager` quản lý đúng `DataSource`, SELECT và UPDATE có thể dùng **cùng local database transaction**. Khi downstream dùng `DirectChannel` và handler thực thi **đồng bộ cùng thread**, lỗi trong handler trước lúc commit có thể dẫn đến rollback.

~~~mermaid
sequenceDiagram
    participant Poller as Poller transactional
    participant DB as JDBC database
    participant Channel as DirectChannel
    participant Handler as Synchronous handler
    Poller->>DB: BEGIN + SELECT NEW rows
    DB-->>Poller: Rows 101, 102
    Poller->>DB: UPDATE rows to CLAIMED
    Poller->>Channel: Message<List<Row>>
    Channel->>Handler: Process
    alt Handler thành công
        Handler-->>Poller: Return
        Poller->>DB: COMMIT
    else Handler ném exception
        Handler-->>Poller: Exception
        Poller->>DB: ROLLBACK
    end
~~~

**Ranh giới quan trọng:** nếu handler chỉ gửi một HTTP request/Kafka event ra ngoài rồi database transaction rollback, remote **có thể đã nhận** side effect. Local DB rollback không thu hồi event trên broker hay request từ đối tác. Chỉ nên giữ transaction xuyên một đoạn downstream đồng bộ ngắn, phù hợp với chiến lược transaction; không giữ DB locks lâu để chờ remote I/O.

### 13.1. DirectChannel khác ExecutorChannel và QueueChannel

| Boundary | Handler chạy lúc nào? | Transaction của poller? |
|---|---|---|
| `DirectChannel` | Ngay trong caller/poller thread | Có thể dùng chung nếu cùng resource/manager |
| `ExecutorChannel` | Thread executor | Không tự mang transaction thread-bound |
| `QueueChannel` + poller khác | Sau, ở thời điểm khác | Transaction riêng |
| Kafka/JMS outbound | Theo adapter/client/broker semantics | Không tự atomic với DB transaction |

Đừng viết `send() == true` rồi kết luận “database và broker đã commit” nếu flow có async boundary.

## 14. Cạnh tranh nhiều instances: SELECT rồi UPDATE chưa đủ

Giả sử hai pods cùng poll với câu SELECT bình thường:

~~~text
T1  Pod A: SELECT row 101 (state=NEW)
T2  Pod B: SELECT row 101 (state=NEW)
T3  Pod A: UPDATE row 101 -> CLAIMED (1 row)
T4  Pod A: phát event 101
T5  Pod B: UPDATE row 101 WHERE state=NEW (0 row)
T6  Pod B: vẫn sở hữu List<Row> có event 101 từ SELECT ở T2
T7  Pod B: phát event 101 lần nữa
~~~

Điều kiện `WHERE state='NEW'` trong UPDATE giúp tránh **ghi đè state** khi row đã bị claim, nhưng **không tự loại row của pod B khỏi result list**. Một số ứng dụng chỉ kiểm tra “UPDATE không ném exception” rồi vẫn phát mọi rows đã SELECT — điều đó không đủ để đảm bảo một pod duy nhất sở hữu bản ghi.

### 14.1. Các lựa chọn khắc phục

1. **Row-level locking với SKIP LOCKED:** SELECT khóa những rows định claim, bỏ qua rows đã bị khóa, UPDATE trước commit; yêu cầu transaction/isolation phù hợp.
2. **Atomic UPDATE … RETURNING/OUTPUT:** chọn và claim trong **một statement**, nhận chính các rows thực sự được claim; cách triển khai phụ thuộc DB vendor.
3. **Lease/owner:** ghi `claimed_by`, `lease_until` và version; worker khác chỉ reclaim khi lease hết hạn.
4. **Partition ownership:** mỗi pod chỉ poll một tập khóa được phân công rõ ràng.
5. **Idempotent consumer:** chấp nhận at-least-once delivery và chống side effects trùng bằng business event ID.

Trong hệ thống nhiều replicas, nên ưu tiên **atomic claim + idempotency**; không chỉ dựa vào “mỗi pod có một poller” hay “DB có transaction” để suy ra exactly-once.

## 15. Ví dụ PostgreSQL: khóa rows khi SELECT

PostgreSQL cung cấp `FOR UPDATE SKIP LOCKED` để những transaction khác bỏ qua các rows đang bị khóa:

~~~sql
-- PostgreSQL; chạy bên trong một transaction giữ lock đến commit.
SELECT id, event_id, event_type, payload_json,
       state, attempt_count, created_at
FROM integration_event
WHERE state = 'NEW'
ORDER BY created_at, id
LIMIT 20
FOR UPDATE SKIP LOCKED;
~~~

Sau khi lấy IDs, cùng transaction chạy:

~~~sql
UPDATE integration_event
SET state = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP,
    attempt_count = attempt_count + 1
WHERE id IN (:ids) AND state = 'NEW';
~~~

Nếu cả SELECT và UPDATE nằm trong **transaction của poller**, các rows đã được khóa khi SELECT không bị một transaction tuân thủ cùng cơ chế lấy đồng thời. Tuy nhiên cần kiểm tra isolation level, index, row lock behavior và cách DB tối ưu LIMIT/ORDER BY trong môi trường thật.

**Không áp dụng nguyên văn cho H2/SQL Server/MySQL/Oracle.** Vendor khác có cú pháp hoặc semantics locking khác. Đừng kết luận câu SELECT này bảo đảm thứ tự xử lý toàn hệ thống; khi có nhiều workers, những rows bị khóa được skip và có thể được xử lý sau.

### 15.1. Khi cần atomic claim trả về chính các rows

PostgreSQL hỗ trợ cấu trúc minh họa:

~~~sql
WITH picked AS (
    SELECT id
    FROM integration_event
    WHERE state = 'NEW'
    ORDER BY created_at, id
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE integration_event e
SET state = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP,
    attempt_count = attempt_count + 1
FROM picked
WHERE e.id = picked.id
RETURNING e.id, e.event_id, e.event_type, e.payload_json;
~~~

Đây là **mẫu SQL theo PostgreSQL**, cần thực thi qua cơ chế phù hợp với driver và endpoint, ví dụ repository/JdbcTemplate hoặc một stored procedure/message source có hợp đồng rõ. Không mặc định rằng `JdbcPollingChannelAdapter` với một `selectQuery` được thiết kế để thay thế mọi kiểu DML `RETURNING`; nếu chọn giải pháp này, hãy kiểm tra cách query và JDBC driver trả result set.

Ưu điểm của atomic claim là danh sách nhận được gắn với **những rows thật sự bị thay đổi**, thay vì phụ thuộc vào một SELECT cũ. Nó vẫn **chưa** bảo đảm Kafka/HTTP đã nhận message.

## 16. Đã claim, đã gửi và đã xử lý: chọn mốc chuyển state

Một quy trình có thể lưu các mốc:

~~~text
NEW
  -> CLAIMED (worker X, lease đến thời điểm T)
  -> PUBLISHING
  -> PUBLISHED
  -> DONE (nếu còn cần ACK/side effect nghiệp vụ)
~~~

Với hệ thống nhỏ, `CLAIMED → DONE` có thể đủ. Với outbox, `NEW → PUBLISHED` có thể là hợp đồng gọn hơn. Nhưng mọi tên trạng thái phải có **định nghĩa chính xác**:

| Mốc | Bằng chứng cần có | Ai chịu trách nhiệm? |
|---|---|---|
| `CLAIMED` | DB commit claim và owner/lease | DB/polling worker |
| `PUBLISHED` | Adapter/client ghi nhận kết quả gửi theo delivery contract | Publisher/outbox relay |
| `DONE` | Tác vụ hoàn tất theo hợp đồng nghiệp vụ | Worker/service |
| `FAILED` | Đã phân loại không thể tự retry, có dữ liệu đối soát | Error handler/recovery |

Đặc biệt, **Kafka producer callback/ack** không tự chứng minh consumer của Kafka đã hoàn tất việc xử lý event; ACK của JMS/Kafka listener cũng có nghĩa khác ACK phía producer.

Không đặt tên cột `is_read=true` rồi coi đó là đủ thay thế cho thiết kế delivery. Nếu muốn một “đọc đúng một lần” qua nhiều hệ thống, hãy viết rõ yêu cầu **exactly-once effect**, không chỉ exactly-once read.

## 17. Lease và recovery khi worker chết giữa chừng

Nếu row chuyển `CLAIMED` rồi ứng dụng crash trước khi gửi, row có thể không bao giờ được SELECT lại nếu query chỉ lấy `NEW`. Một giải pháp thường gặp là **lease**:

~~~sql
-- DML minh họa với parameter do ứng dụng bind.
UPDATE integration_event
SET state = 'CLAIMED',
    claimed_by = :workerId,
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = :leaseUntil,
    attempt_count = attempt_count + 1
WHERE id IN (:ids)
  AND state = 'NEW';
~~~

`:workerId`, `:leaseUntil` và `:ids` phải được truyền qua parameter source; đây không phải SQL đầy đủ của flow ở mục 8. Deadline `leaseUntil` nên được xác định rõ theo UTC/clock policy; tránh để đồng hồ các pods lệch quá nhiều. Với hệ quản trị có hỗ trợ tính deadline trực tiếp tại DB, việc dùng đồng hồ DB có thể giảm lệch giờ.

Recovery job có thể xét:

~~~sql
-- Khái niệm: reclaim những bản ghi đã hết lease.
SELECT id, event_id, attempt_count
FROM integration_event
WHERE state = 'CLAIMED'
  AND lease_until < CURRENT_TIMESTAMP
ORDER BY lease_until, id;
~~~

Sau đó phải **reclaim atomically** bằng lock/version/owner mới. Chỉ đọc danh sách lease hết hạn rồi UPDATE tùy tiện vẫn tạo race khi nhiều recovery workers chạy cùng lúc.

### 17.1. Fencing token để tránh worker cũ ghi đè

Giả sử worker A mất kết nối, lease của A hết hạn; worker B lấy lại job, nhưng A vẫn còn chạy. Nếu A hoàn tất và cập nhật `DONE` mà không kiểm tra quyền sở hữu, nó có thể phá trạng thái của B.

Một cơ chế phòng vệ là version/fencing token tăng mỗi lần claim:

~~~sql
UPDATE integration_event
SET state = 'DONE',
    completed_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND claimed_by = :workerId
  AND claim_version = :claimVersion
  AND state = 'CLAIMED';
~~~

Đây là **mẫu DML mở rộng**, yêu cầu bổ sung cột `claim_version` và logic tăng version khi claim; nó không chạy nguyên văn trên schema mục 5. Khi row count bằng 0, worker có thể đã mất ownership; không tự ghi đè để cố “hoàn tất”.

## 18. Transactional outbox: thay vì gửi broker ngay sau SELECT

Với dữ liệu nghiệp vụ có sự kiện cần phát, cách an toàn phổ biến:

~~~mermaid
flowchart LR
    A["Business transaction"] --> B["Ghi nghiệp vụ + outbox trong cùng DB TX"]
    B --> C[("Outbox table")]
    C --> D["Outbox polling relay"]
    D --> E["Kafka / JMS"]
    E --> F["Consumer xử lý idempotent"]
    D -->|"ACK gửi thành công"| G["Đánh dấu PUBLISHED"]
    D -->|"Thất bại"| H["Retry / lease"]
~~~

Outbox giúp tránh tình huống **ghi database thành công nhưng sự kiện chưa được ghi bền để gửi**. Tuy nhiên, một publisher có thể gửi broker thành công rồi crash **trước khi đánh dấu `PUBLISHED`**. Sau restart, outbox được gửi lại: đó là **at-least-once**, nên consumer vẫn phải idempotent.

**Phân biệt hai thiết kế:**

- “Đọc bảng nghiệp vụ NEW rồi UPDATE CLAIMED”: worker phải quản lý claim, recovery và xác minh kết quả downstream.
- “Ghi outbox trong transaction nghiệp vụ rồi relay”: đảm bảo có bản ghi sự kiện bền vững và có thể retry độc lập; vẫn phải quản lý publish state và dedupe.

Không nên giữ một local database transaction đang mở chỉ để chờ Kafka hoặc HTTP response lâu. Nếu nghiệp vụ cần phản hồi nhanh, tạo outbox cùng transaction rồi trả trạng thái **ACCEPTED/PENDING** theo hợp đồng ứng dụng.

## 19. Poller có thể làm quá tải DB như thế nào?

Mỗi lần poll tiêu thụ connection và có thể thực hiện một SELECT + UPDATE. Khi số pods, poller threads và batch size tăng, database có thể bị quá tải bởi:

- Full table scan do thiếu index `(state, created_at, id)`.
- Nhiều pollers cùng tranh row locks.
- Transaction giữ connection/locks lâu vì handler downstream chạy chậm.
- Batch quá lớn khiến statement `IN (:ids)` có hàng nghìn parameters.
- Retry liên tục khi DB đang mất kết nối.
- Đọc các rows giống nhau do UPDATE không đổi state/rollback.

| Thông số | Đặt ở đâu? | Khuyến nghị thiết kế |
|---|---|---|
| Fixed delay | Poller | Chọn từ throughput thực tế, không poll liên tục khi rỗng |
| `maxMessagesPerPoll` | Poller | Thường giữ 1 với JDBC inbound |
| `maxRows` | Adapter | Giới hạn mỗi lượt, cần đi kèm SQL limit |
| SQL `LIMIT/TOP` | Database | Đảm bảo index phù hợp |
| JDBC pool max size | Hikari/DataSource | Không tăng vượt năng lực DB |
| Handler concurrency | Channel/executor | Bounded; kiểm soát transaction boundary |
| Retry attempts/backoff | Poller/worker/recovery | Giới hạn và có jitter để tránh retry storm |

Khi polling nhiều rows, `RowMapper` và splitter không biến JDBC thành non-blocking. `JdbcTemplate`/JDBC vẫn sử dụng **blocking I/O**; tránh chạy chúng trên Reactor Netty event loop khi ứng dụng có WebFlux.

## 20. Lỗi trong SELECT, UPDATE và downstream có hậu quả khác nhau

| Lỗi | Thời điểm | Kết quả có thể xảy ra | Cách phản ứng |
|---|---|---|---|
| DB mất kết nối | Trước hoặc trong SELECT | Không có rows | Alert, retry có giới hạn |
| Query SQL sai/schema đổi | SELECT | Lỗi cấu hình | Sửa SQL/migration, không retry vô hạn |
| RowMapper sai column/type | Đang map rows | Chưa tạo payload hợp lệ | Sửa mapper/schema, rollback nếu cần |
| UPDATE trả 0 rows | Sau SELECT | Row đã bị claim/không khớp | Không tự tuyên bố ownership |
| Deadlock/serialization | UPDATE/commit | Transaction rollback | Retry toàn transaction nếu an toàn |
| Downstream đồng bộ ném exception | Sau source receive | Có thể rollback poller transaction | Kiểm tra DirectChannel, resource manager |
| Downstream async lỗi | Sau khi poller đã commit | Row có thể kẹt CLAIMED | Lease/outbox/error flow |
| Broker đã nhận nhưng app crash trước ghi DONE | Sau gửi | Có thể redeliver | Stable event ID và consumer idempotency |
| Poller bị lỗi lặp | Mỗi trigger | DB chịu tải không cần thiết | Backoff/health gating, cảnh báo |

Spring JDBC thường dịch `SQLException` sang các subtype `DataAccessException`. Spring Integration có thể đưa lỗi từ poller/handler sang `ErrorMessage`/`errorChannel` hoặc error handler tương ứng theo cách endpoint được cấu hình. **Không mặc định mọi lỗi sẽ biến thành reply message** hoặc tự được broker retry.

### 20.1. Retry đúng đơn vị transaction

Nếu poller SELECT và UPDATE trong cùng transaction rồi gặp deadlock, retry **toàn bộ poll/transaction sau rollback**, không chỉ lặp một câu UPDATE mà vẫn dùng list ID cũ. Khi mất kết nối sát thời điểm commit, outcome có thể không chắc chắn; cần đọc lại trạng thái và dedupe, không gửi lặp vô hạn theo giả định rollback chắc chắn.

## 21. Quan sát trạng thái: metrics và logging

Các chỉ số nên có:

1. **Polls:** số lượt chạy, khoảng cách trigger, số lần poll rỗng, thời gian SELECT/UPDATE.
2. **Rows:** số rows SELECT, số rows thực sự UPDATE/claim, chênh lệch count giữa hai thao tác.
3. **Backlog:** số rows `NEW`, `CLAIMED`, `FAILED`, tuổi row lâu nhất chưa hoàn thành.
4. **Lease:** số row hết lease, số reclaim, thời gian từ CLAIMED đến DONE.
5. **Delivery:** số lần publish, retry, error, broker ACK, duplicate consumer effect.
6. **Database:** active/idle/pending connections, locks, deadlocks, query timeout và transaction duration.

Log nên có `event_id`, `workerId`, `pollId`/correlation ID, trạng thái trước/sau và loại lỗi; tránh log toàn bộ `payload_json` nếu chứa thông tin nhạy cảm. Không dùng `event_id` duy nhất cho từng row làm metric tag nếu gây cardinality quá cao — phù hợp hơn cho logs/traces.

### 21.1. Chỉ số UPDATE = 0 là tín hiệu vận hành

Nếu SELECT trả 20 rows nhưng UPDATE chỉ sửa 7, có thể có concurrency/race, predicate quá chặt, rows đổi state trong lúc poll hoặc SQL mapping sai. Với application coi 20 rows là “đã claim”, đây là cảnh báo thiết kế nghiêm trọng.

JDBC inbound adapter **không tự trở thành distributed ownership coordinator** chỉ vì bạn có thể đo row count. Nếu yêu cầu chính xác những rows đã claim, triển khai atomic claim trả row IDs thực sự thành công và đưa **danh sách đó** làm message source.

## 22. Kiểm thử cơ bản với H2

Đối với logic một instance, H2 đủ để kiểm thử SELECT + UPDATE và RowMapper. Không coi H2 là bằng chứng cho locking/transaction semantics của PostgreSQL, SQL Server hoặc Oracle.

### 22.1. Test một nguồn JDBC trực tiếp

Một bài integration test có thể tạo `JdbcPollingChannelAdapter` làm **MessageSource** mà không bật scheduler, để chủ động gọi `receive()`. Ví dụ:

~~~java
package com.example.polling;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.messaging.Message;

@SpringBootTest
class EventPollingSourceTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void selectsAndMarksRowsForProcessing() throws Exception {
        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource,
                "SELECT id, event_id, event_type, payload_json, "
              + "state, attempt_count, created_at "
              + "FROM integration_event "
              + "WHERE state = 'NEW' ORDER BY id");

        source.setMaxRows(2);
        source.setRowMapper(new EventRecordRowMapper());
        source.setUpdateSql(
            "UPDATE integration_event SET state='CLAIMED' "
          + "WHERE id IN (:ids) AND state='NEW'");
        source.setUpdateSqlParameterSourceFactory(rows -> {
            List<?> list = (List<?>) rows;
            List<Long> ids = list.stream()
                .map(EventRecord.class::cast)
                .map(EventRecord::id)
                .toList();
            return new MapSqlParameterSource("ids", ids);
        });

        // Test tự tạo source, phải hoàn tất lifecycle cần thiết.
        source.afterPropertiesSet();

        Message<?> message = source.receive();
        assertNotNull(message);
        List<?> events = (List<?>) message.getPayload();
        assertEquals(2, events.size());

        Integer claimed = jdbc.queryForObject(
            "SELECT COUNT(*) FROM integration_event "
          + "WHERE state = 'CLAIMED'",
            Integer.class);
        assertEquals(2, claimed);
    }
}
~~~

**Điều kiện của ví dụ:** bảng fixture phải có ba rows `NEW` như mục 5, không có poller/flow khác đang đụng bảng, không dùng test-level transaction tự rollback, và datasource/bean lifecycle phải được cấu hình tương thích. Trong một ứng dụng có các IntegrationFlows tự động startup, hãy tách test context hoặc disable source khác để tránh cạnh tranh.

Test trên **không có transactional poller**, nên không kiểm chứng rollback khi downstream lỗi; nó chỉ kiểm tra thao tác SELECT/UPDATE và payload. Để test transaction, cần dùng poller thực hoặc mở `TransactionTemplate` bao source receive + một downstream operation trong cùng thread.

### 22.2. Test khi không còn rows

Sau khi tất cả các rows `NEW` đã được claim, gọi `receive()` tiếp và kiểm tra hành vi nguồn **trong phiên bản đang dùng** (không có business message hoặc kết quả rỗng theo hợp đồng). Đừng viết test chỉ khẳng định `send()==true` mà không nhìn dữ liệu DB.

### 22.3. Bảng test tối thiểu

| Kịch bản | Kỳ vọng |
|---|---|
| 3 NEW rows, maxRows=2 | Hai rows được map/mark trong lượt đầu |
| Lượt thứ hai | Row còn lại được xử lý, không đọc lại hai rows đã CLAIMED |
| Không còn NEW rows | Không có business events mới |
| Sai tên column trong RowMapper | Lỗi xuất hiện, không lặng lẽ tạo DTO sai |
| UPDATE predicate không match | Không tự xác nhận quyền claim |
| DirectChannel handler lỗi | Poller TX rollback nếu cùng local DB transaction |
| ExecutorChannel handler lỗi | Poller TX không tự rollback do worker khác |
| Hai instances cùng SELECT | Nguy cơ trùng, cần atomic locking |
| Worker crash sau CLAIMED | Lease/recovery lấy lại row |
| Publisher gửi Kafka rồi crash | Stable event ID giúp consumer dedupe |

## 23. Kiểm thử concurrency và crash recovery

Hãy dùng PostgreSQL/SQL Server/MySQL/Oracle test instance hoặc Testcontainers phù hợp để tái hiện concurrency thực tế:

1. Tạo 100 rows `NEW`.
2. Chạy hai worker transactions cùng SELECT theo mốc thời gian có kiểm soát (barrier/latch), xác nhận cùng-row race ở thiết kế naïve.
3. Thay bằng truy vấn `FOR UPDATE SKIP LOCKED` hoặc atomic claim theo vendor; xác nhận hai workers không cùng claim một ID trong những transaction thành công.
4. Cho một worker ngủ/treo giữa claim và commit, kiểm tra lock wait/timeout và rollback.
5. Commit claim, rồi giả lập crash trước khi publish; thử lease-expiry/reclaim.
6. Giả lập broker nhận event nhưng app crash trước khi đánh dấu DONE; xác minh nhận lại cùng event ID không gây side effect trùng.
7. Gửi hai business events cùng aggregate nhưng khác version theo thứ tự đảo; kiểm tra consumer không ghi lùi state.
8. Giảm pool size, tăng pollers và theo dõi connection wait, lock contention, throughput.

**Không chỉ kiểm tra số lần callback được gọi**. Để chứng minh một thiết kế không mất công việc, cần kiểm tra **DB state, broker outcome, retry backlog, lease recovery và idempotent business effect**. Kể cả khi một test không thấy duplicate, điều đó không chứng minh hệ thống có exactly-once delivery trong mọi crash windows.

## 24. Những hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Polling JDBC nghĩa là nhận message từ broker” | JDBC inbound tự **chạy SELECT theo lịch** |
| “Một SELECT trả 20 rows thì adapter phát 20 messages” | Thường một message chứa list; splitter tách |
| “`maxMessagesPerPoll(1)` chỉ lấy một row” | Là một lần hỏi `receive()` trong trigger |
| “`maxRows(0)` không lấy hàng nào” | 0 nghĩa là không giới hạn theo adapter |
| “`WHERE state='NEW'` đã chống duplicate giữa nhiều pods” | Hai pods có thể SELECT cùng row trước UPDATE |
| “UPDATE trả 0 hàng sẽ luôn ném lỗi” | JDBC UPDATE có thể thành công với count 0 |
| “UPDATE CLAIMED là Kafka đã nhận” | Claim DB khác broker publish/consumer ACK |
| “Poller transaction tự rollback HTTP/Kafka” | Chỉ các resources trong transaction; side effect ngoài DB không tự rollback |
| “Rows không còn NEW nghĩa đã được xử lý hết” | Có thể đang kẹt CLAIMED hoặc FAILED |
| “Chỉ cần tăng poll frequency sẽ hết backlog” | Có thể gây pool exhaustion và lock contention |
| “RowMapper đổi trạng thái đã đọc” | Mapper chỉ tạo Java objects; SQL UPDATE thực hiện thay đổi |
| “Retries không tạo duplicate nếu event ID luôn mới” | Event ID phải ổn định để dedupe |
| “SELECT + UPDATE trong transaction là exactly-once end-to-end” | Cần ownership, recovery, broker ACK và consumer idempotency |

## 25. Bài thực hành

1. Tạo bảng `integration_event` với các trạng thái `NEW/CLAIMED/DONE`, chèn dữ liệu mẫu và kiểm tra chỉ `NEW` được SELECT.
2. Chạy JDBC inbound adapter không có UPDATE; quan sát cùng rows xuất hiện trong các polls kế tiếp.
3. Thêm UPDATE `state='CLAIMED' WHERE id IN (:id)` theo quy ước mặc định; đối chiếu với custom parameter `:ids`.
4. Viết flow Java DSL 7.x với `Jdbc.inboundAdapter` và `RowMapper<EventRecord>`; dùng splitter để gửi từng event.
5. Chuyển flow tương tự sang 6.x bằng `JdbcPollingChannelAdapter` và kiểm tra lifecycle/đường import.
6. So sánh `maxRows(20)`, SQL `LIMIT 20` và `maxMessagesPerPoll(1)` về số query, số rows và số messages.
7. Test DB trả 0 rows, 1 row và 100 rows; tránh gửi empty business events.
8. Thử `updatePerRow(true)` cho SQL update từng row; so sánh với batch update bằng list IDs.
9. Tạo SELECT có `:wantedState` và `selectSqlParameterSource`; phân biệt với UPDATE parameter factory.
10. Bọc poller trong transaction, cho downstream DirectChannel ném exception và xác nhận DB rollback.
11. Đổi downstream sang ExecutorChannel; giải thích vì sao worker lỗi sau khi poller commit không tự rollback CLAIMED.
12. Chạy hai pollers cùng bảng; tạo tình huống cả hai SELECT chung row và phân tích UPDATE count.
13. Trên PostgreSQL test, dùng `FOR UPDATE SKIP LOCKED` và đo số rows trùng giữa hai transactions.
14. Thử atomic UPDATE ... RETURNING theo vendor trong repository/message source riêng; chỉ emit rows được claim thành công.
15. Thêm `claimed_by`, `lease_until`, `attempt_count`, xây recovery job và cảnh báo rows kẹt.
16. Dùng fencing token/version khi hoàn tất work; từ chối cập nhật DONE nếu worker đã mất lease.
17. Đổi sang transactional outbox và mô phỏng crash sau DB commit trước publish.
18. Gửi event sang Kafka/JMS, làm crash sau broker ACK trước DONE; kiểm tra consumer idempotency với `event_id`.
19. Đo pool active connections, poll duration, SQL UPDATE count, backlog và lease expired theo tải.
20. Viết integration test trên DB production-compatible để kiểm tra locking, transaction, crash windows và redelivery.

**Câu hỏi tình huống:** Có hai pods poll bảng `integration_event` chứa 50.000 rows `NEW`. Mỗi pod lấy 100 rows rồi đánh dấu `CLAIMED`, gửi Kafka, sau đó một pod bị kill ngay khi broker đã nhận nhưng database chưa đánh dấu `DONE`. Hãy xác định cách SELECT/UPDATE, locking, lease, outbox, unique event ID, consumer idempotency và recovery cần phối hợp để không mất công việc và không nhân đôi tác dụng nghiệp vụ.

## 26. Tài liệu tham khảo

- [Spring Integration Reference — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): SELECT + optional UPDATE, row mapping, tham số `:id`, transactional poller, `maxRows` vs `maxMessagesPerPoll`.
- [Spring Integration Reference — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): Java DSL `Jdbc.inboundAdapter(...)` từ Spring Integration 7.0.
- [Spring Integration API — JdbcInboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcInboundChannelAdapterSpec.html): `rowMapper`, `maxRows`, `updateSql`, `updatePerRow`, `updateSqlParameterSourceFactory`.
- [Spring Integration API — JdbcPollingChannelAdapter](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): source, SELECT/UPDATE, row mapper và parameter sources.
- [Spring Integration Reference — Inbound Channel Adapters](https://docs.spring.io/spring-integration/reference/dsl/java-inbound-adapters.html): `MessageSource`, `IntegrationFlow.from` và `Pollers`.
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): transaction trên poller, đồng bộ channel và rollback.
- [Spring Framework Reference — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `RowMapper`, named parameters và SQL operations.
- [PostgreSQL Documentation — SELECT](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE`, `SKIP LOCKED` và `LIMIT`.
- [PostgreSQL Documentation — UPDATE](https://www.postgresql.org/docs/current/sql-update.html): `UPDATE ... FROM` và `RETURNING` phục vụ mẫu atomic claim.

> **Ghi nhớ:** JDBC polling là **chu kỳ SELECT → ánh xạ rows → có thể UPDATE trạng thái → phát message**. `NEW → CLAIMED` giúp tránh đọc lặp trong trường hợp đơn giản nhưng **không** đồng nghĩa đã gửi hay xử lý thành công. Muốn nhiều instances hoạt động đáng tin phải quản lý transaction, locking/atomic claim, lease/recovery, outbox và idempotency; `maxRows` giới hạn rows, `maxMessagesPerPoll` giới hạn số lần hỏi source, còn splitter mới tạo các messages riêng cho từng row.
