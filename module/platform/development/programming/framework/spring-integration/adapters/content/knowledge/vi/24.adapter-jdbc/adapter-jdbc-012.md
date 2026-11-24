# Locking và tránh lấy trùng bản ghi trong Spring Integration JDBC

## 1. Tại sao hai pollers có thể lấy cùng một bản ghi?

Một ứng dụng Spring Integration chạy ở hai pods, cùng dùng **JDBC inbound channel adapter** để lấy các bản ghi `NEW` từ cơ sở dữ liệu rồi phát message đến Kafka, JMS, AMQP hoặc HTTP. Khi chạy một instance, câu `SELECT ... WHERE state='NEW'` rồi `UPDATE state='CLAIMED'` có vẻ đủ để không đọc lại dữ liệu. Nhưng trong môi trường nhiều instances, **hai transactions có thể SELECT cùng một row trước khi bất kỳ transaction nào UPDATE**.

~~~text
Thời điểm      Pod A                            Pod B
----------------------------------------------------------------
t1             SELECT id=101, state='NEW'
t2                                              SELECT id=101, state='NEW'
t3             UPDATE id=101 -> CLAIMED (1)
t4             COMMIT
t5                                              UPDATE id=101
                                                WHERE state='NEW' (0)
t6             publish event 101
t7                                              vẫn giữ row 101 trong
                                                List được SELECT ở t2;
                                                nếu publish sẽ bị trùng.
~~~

Câu `UPDATE ... WHERE state='NEW'` của pod B **có thể thành công về mặt SQL với affected rows bằng 0**. Dù row không được UPDATE, **kết quả SELECT trước đó chưa biến mất khỏi Java `List`**. Vì vậy không thể suy luận “không có lỗi SQL” là pod đã giành quyền sở hữu row.

Bài học **Locking và tránh lấy trùng bản ghi** thuộc chương **Adapter JDBC** trong module **SPRING_INTEGRATION_ADAPTERS**: kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành với file, SFTP, HTTP, JMS, AMQP, Kafka và database; quản lý message contract, lỗi và vòng đời kết nối. Ở đây trọng tâm là **row ownership, locking, transaction, claim, retry và idempotency**.

**Hai câu hỏi phải trả lời riêng:** (1) Làm sao một lúc chỉ một worker có quyền *claim* công việc? (2) Làm sao khi công việc bị *redeliver*, tác dụng nghiệp vụ không bị lặp? Locking giúp câu (1) trong phạm vi database; idempotency/outbox giúp câu (2) qua các lần retry và hệ thống ngoài.

## 2. Mục tiêu và phạm vi bài học

Sau bài học, người học có thể:

1. Tái hiện race condition từ `SELECT → UPDATE`, xác định chính xác nơi phát sinh duplicate.
2. Phân biệt **pessimistic row lock**, **optimistic version**, **atomic claim**, **lease**, **fencing token**, **idempotency**.
3. Sử dụng `FOR UPDATE SKIP LOCKED` trên PostgreSQL; hiểu giải pháp tương ứng **không hoàn toàn đồng nhất** của MySQL, SQL Server và Oracle.
4. Cấu hình Spring Integration JDBC inbound poller có transaction và giải thích vì sao `DirectChannel` khác `ExecutorChannel`.
5. Xây một `MessageSource` dùng **PostgreSQL UPDATE ... RETURNING** để phát đúng những rows thực sự được claim.
6. Thiết kế lease/timeout/recovery khi tiến trình crash và cơ chế tránh worker cũ ghi đè trạng thái của worker mới.
7. Kiểm thử concurrency bằng hai transactions thật, đồng thời đo lock contention, deadlocks và duplicate business effects.

Không có một lựa chọn locking duy nhất phù hợp mọi workload. Ví dụ SQL theo PostgreSQL sẽ được đánh dấu rõ; không copy sang H2, SQL Server, MySQL hoặc Oracle mà không kiểm chứng SQL dialect và transaction semantics.

## 3. Các khái niệm: đọc, khóa, claim và xử lý thành công

| Khái niệm | Định nghĩa | Điều chưa được bảo đảm |
|---|---|---|
| **Đã đọc (read)** | Row xuất hiện trong `ResultSet` của SELECT | Worker sở hữu row |
| **Row lock** | DB ngăn hoặc điều phối truy cập cạnh tranh trên hàng | Broker ngoài DB đã nhận event |
| **Claim** | DB ghi trạng thái/quyền xử lý của worker | Công việc đã thành công |
| **Lease** | Quyền claim có thời hạn; quá hạn có thể reclaim | Worker cũ chắc chắn ngừng chạy |
| **Fencing token** | Mã/version claim thay đổi mỗi lần lấy quyền | Remote service tự từ chối token cũ |
| **Optimistic locking** | UPDATE có điều kiện version/state, kiểm tra affected rows | Chỉ một worker từng SELECT row |
| **Pessimistic locking** | Khóa hàng trước khi cập nhật | Không có deadlock/starvation |
| **Idempotent effect** | Nhiều lần nhận cùng event không gây side effect trùng | Message chỉ được truyền một lần |
| **Transactional outbox** | Ghi event cần phát và thay đổi DB trong một local transaction | Consumer Kafka/JMS đã xử lý |
| **Exactly-once** | Thuật ngữ phải chỉ rõ scope (read, publish, effect) | Bảo đảm toàn hệ thống nếu không có protocol rõ |

Một mô hình trạng thái thường gặp:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> CLAIMED: atomic claim
    CLAIMED --> STAGED: stage durable outbox
    CLAIMED --> NEW: lease expired / recover
    CLAIMED --> FAILED: terminal error
    STAGED --> PUBLISHED: broker ACK + publisher bookkeeping
    FAILED --> NEW: replay được kiểm soát
    PUBLISHED --> [*]
~~~

**Cẩn trọng với tên trạng thái:** `STAGED` có thể nghĩa là outbox đã ghi bền, **chưa** nghĩa consumer đã áp dụng side effect. Nếu một pipeline xử lý công việc ngay tại worker thay vì ghi outbox, có thể dùng `DONE` khi hành động thuộc transaction đã hoàn thành. Phải định nghĩa từng trạng thái theo business contract.

## 4. Thứ tự xử lý message không thay thế row ownership

Theo Spring Integration JDBC Reference, **inbound channel adapter** chạy SELECT và phát **một message chứa toàn bộ result set dạng `List`**; mặc định từng row là `Map<String,Object>`, custom `RowMapper<T>` tạo DTO.

~~~text
Poller receive() một lần
  -> SELECT lấy 20 rows
  -> RowMapper được gọi 20 lần
  -> 1 Message<List<JobRow>>
  -> Splitter
  -> 20 Message<JobRow>
~~~

Không nhầm các giới hạn:

| Cấu hình | Đơn vị | Ví dụ |
|---|---|---|
| `maxRows(20)` của JDBC adapter | Tối đa 20 rows mỗi query result | Không phải 20 lần poll |
| `maxMessagesPerPoll(1)` | Tối đa một `receive()` mỗi nhịp | Không phải một row |
| SQL `LIMIT 20` | Số rows database trả ở SELECT | Chọn SQL theo vendor |
| `.split()` | Chuyển list thành từng message | Không tự khóa DB |
| `DirectChannel` | Chạy đồng bộ trên caller thread | Có thể tham gia JDBC transaction |
| `ExecutorChannel` | Dispatch sang executor thread | Không mang JDBC transaction thread-bound mặc định |

**Khi có hai pods, `maxMessagesPerPoll(1)` ở mỗi pod không ngăn cả hai cùng nhận row 101.** Chỉ policy ownership của database/partition mới xử lý trường hợp đó.

## 5. Các chiến lược tránh lấy trùng: chọn theo nhu cầu

| Chiến lược | Phạm vi phù hợp | Điểm mạnh | Giới hạn |
|---|---|---|---|
| Một leader/poller | Luồng nhỏ, SLA đơn giản | Dễ vận hành và debug | Cần failover/leader election |
| Chia partition theo key | Nguồn phân vùng ổn định | Giảm tranh chấp | Cần rebalancing và ownership |
| `SELECT FOR UPDATE SKIP LOCKED` | DB queue, nhiều consumers | Skip hàng đang bị khóa | Phải giữ TX/lock tới UPDATE |
| Atomic `UPDATE ... RETURNING` | PostgreSQL work queue | Trả chính rows đã claim | SQL vendor-specific |
| `UPDLOCK/READPAST/OUTPUT` | SQL Server work queue | Hỗ trợ locking và nhận rows | Hints/RCSI/page locks phức tạp |
| Optimistic `UPDATE ... WHERE version=...` | Update theo expected version | Không cần giữ read lock lâu | Có thể đọc trùng, phải xử lý 0 rows |
| Lease + fencing | Worker có thể crash hoặc chạy lâu | Recovery và chống stale completion | Cần clock/ownership policy |
| Outbox + idempotent consumer | Side effects ngoài DB | Retry an toàn hơn | Có thể publish trùng, phải dedupe |
| CDC/change log | Theo dõi thay đổi theo commit log | Giảm polling thiếu dữ liệu | Vận hành connector/checkpoint |

Lựa chọn phụ thuộc **DB vendor**, khả năng sửa nguồn dữ liệu, số replicas, thời gian xử lý và yêu cầu chống duplicate **effect**.

## 6. Chuẩn bị Spring Boot, schema và dữ liệu mẫu

Ví dụ dùng Java 17+, Spring Boot, Spring Integration JDBC, Spring JDBC, PostgreSQL. Dùng BOM của Spring Boot để quản lý phiên bản phù hợp; Java DSL JDBC `Jdbc.inboundAdapter` chỉ có từ Spring Integration **7.0**, còn `JdbcPollingChannelAdapter` dùng được trên 6.x.

~~~groovy
// build.gradle (dependencies) cho ứng dụng thực hành
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
}
~~~

~~~yaml
# application.yml (giá trị minh họa, secrets qua environment)
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/integration_demo
    username: integration_app
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
app:
  worker-id: "${WORKER_ID}"
~~~

`${DB_PASSWORD}` và `${WORKER_ID}` là Spring Boot placeholders, yêu cầu hai biến môi trường tương ứng. `WORKER_ID` phải khác nhau giữa các replicas. Không commit credential thật vào Git; sản xuất nên dùng secret manager.

Tạo schema mẫu ở `schema.sql` của **ứng dụng thực hành** (không phải file worker sẽ ghi trong bước này):

~~~sql
CREATE TABLE work_item (
    id             BIGINT PRIMARY KEY,
    event_id       VARCHAR(80) NOT NULL UNIQUE,
    payload_json   TEXT NOT NULL,
    state          VARCHAR(24) NOT NULL,
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    claimed_by     VARCHAR(100),
    claim_token    UUID,
    claimed_at     TIMESTAMPTZ,
    lease_until    TIMESTAMPTZ,
    staged_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_work_item_ready
    ON work_item (created_at, id)
    WHERE state = 'NEW';

CREATE INDEX idx_work_item_lease
    ON work_item (lease_until, id)
    WHERE state = 'CLAIMED';

CREATE TABLE job_outbox (
    event_id      VARCHAR(80) PRIMARY KEY,
    work_id       BIGINT NOT NULL UNIQUE,
    payload_json  TEXT NOT NULL,
    published     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO work_item(id,event_id,payload_json,state)
VALUES
    (101,'evt-101','{"orderId":"ORD-101"}','NEW'),
    (102,'evt-102','{"orderId":"ORD-102"}','NEW'),
    (103,'evt-103','{"orderId":"ORD-103"}','NEW'),
    (104,'evt-104','{"orderId":"ORD-104"}','STAGED');
~~~

Các index theo `state`/`created_at`/`lease_until` cần được kiểm tra bằng `EXPLAIN (ANALYZE, BUFFERS)` và workload thật; partial indexes ở trên là **PostgreSQL-specific**. Với hàng triệu rows, việc chọn index và kích thước batch ảnh hưởng đáng kể tới lock contention.

## 7. Transactional poller: điều kiện tiên quyết

Spring Integration JDBC inbound source hỗ trợ **SELECT** và một **UPDATE** sau SELECT để đánh dấu rows được nhận. Poller có thể được bọc trong Spring JDBC transaction:

~~~java
endpoint -> endpoint.poller(
    Pollers.fixedDelay(Duration.ofSeconds(3))
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
~~~

Với `PlatformTransactionManager` quản lý đúng `DataSource`, SELECT và UPDATE trong cùng một poll có thể tham gia **cùng local DB transaction**. Những handlers thông qua `DirectChannel` đồng bộ cũng có thể nằm trong transaction cho tới khi poller hoàn tất.

~~~mermaid
sequenceDiagram
    participant P as Transactional poller
    participant A as JDBC inbound source
    participant DB as Database
    participant H as DirectChannel handler
    P->>DB: BEGIN
    P->>A: receive()
    A->>DB: SELECT NEW ... FOR UPDATE SKIP LOCKED
    DB-->>A: Rows + locks held
    A->>DB: UPDATE rows to CLAIMED
    A-->>H: Message<List<Row>>
    H->>DB: INSERT job_outbox
    alt Handler thành công
        P->>DB: COMMIT and release locks
    else Handler ném lỗi
        P->>DB: ROLLBACK and release locks
    end
~~~

**Nguyên tắc bắt buộc:** `SELECT ... FOR UPDATE` phải chạy khi một transaction vẫn **mở** từ trước SELECT cho tới UPDATE. Nếu `autocommit=true` và SELECT kết thúc trước UPDATE, row locks có thể được giải phóng quá sớm, cho phép worker khác SELECT cùng rows.

`@Transactional(readOnly=true)` là lựa chọn sai cho một poll vừa SELECT vừa UPDATE; phải dùng transaction read-write. Không giữ transaction mở quá lâu khi chờ một HTTP/Kafka remote operation.

## 8. PostgreSQL: SELECT FOR UPDATE SKIP LOCKED

PostgreSQL hỗ trợ `FOR UPDATE` để lấy row locks, `NOWAIT` để thất bại nếu không lấy lock ngay, và `SKIP LOCKED` để **bỏ qua những rows đang bị transaction khác giữ lock**.

~~~sql
-- PostgreSQL, phải chạy trong transaction đang mở.
SELECT id, event_id, payload_json
FROM work_item
WHERE state = 'NEW'
ORDER BY created_at, id
LIMIT 20
FOR UPDATE SKIP LOCKED;
~~~

Giả sử transaction A đang khóa IDs 101 và 102, B chạy cùng truy vấn thì có thể nhận 103 trở đi thay vì chờ. Khi cả A và B cùng thực hiện **SELECT lock → UPDATE state → COMMIT**, có thể phân chia công việc mà không giữ cùng row đã được claim.

**Giới hạn theo tài liệu PostgreSQL:**
- `SKIP LOCKED` cho một **view không nhất quán**; nó thích hợp cho queue-like processing, không nên dùng để tính tổng tồn kho hay báo cáo tài chính chính xác.
- Nó chỉ áp dụng cho **row-level locks**; table-level lock phù hợp vẫn được lấy theo cơ chế thông thường.
- `ORDER BY` với locks và concurrent updates không mặc định tạo thứ tự xử lý toàn hệ thống.
- `LIMIT` ngăn tiếp tục khóa thêm sau khi đủ rows, nhưng `OFFSET` có thể vẫn khóa những rows bị bước qua; queue polling thường tránh OFFSET pagination.
- Nếu một row bị khóa lâu, các workers có thể skip liên tục; cần metrics và starvation/recovery policy.

### 8.1. UPDATE các rows đã lock trong cùng transaction

~~~sql
UPDATE work_item
SET state = 'CLAIMED',
    claimed_by = :workerId,
    claimed_at = CURRENT_TIMESTAMP,
    attempt_count = attempt_count + 1
WHERE id IN (:ids) AND state = 'NEW';
~~~

`:ids` phải là danh sách từ **chính kết quả SELECT đã được lock**, không lấy từ bộ nhớ cache của poll trước. `:workerId` do ứng dụng cấp, không nhận từ request không tin cậy. Khi đã đúng transaction và mọi workers đều tuân thủ cùng locking protocol, rows từ A sẽ không bị B cùng claim trong khoảng lock còn hiệu lực.

**Không nên** dùng câu SELECT locking ở transaction A rồi gửi danh sách IDs qua một `ExecutorChannel` để transaction B cập nhật sau. Khi đó lock của A có thể đã mất trước khi B UPDATE.

## 9. Spring Integration Java DSL 7.x: SELECT có lock và UPDATE trong poller

Ở Spring Integration **7.x**, Java DSL factory `Jdbc.inboundAdapter(...)` dùng `JdbcInboundChannelAdapterSpec`; đây là cách giữ JDBC inbound adapter có sẵn và đưa SQL locking vào SELECT.

~~~java
package com.example.integration;

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
public class LockedJdbcInboundFlow {

    public record JobRow(
        long id, String eventId, String payloadJson) { }

    @Bean
    public IntegrationFlow lockedWorkItems(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        String select = """
            SELECT id, event_id, payload_json
            FROM work_item
            WHERE state = 'NEW'
            ORDER BY created_at, id
            LIMIT 20
            FOR UPDATE SKIP LOCKED
            """;

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource, select)
                    .maxRows(20)
                    .rowMapper((rs, n) -> new JobRow(
                        rs.getLong("id"),
                        rs.getString("event_id"),
                        rs.getString("payload_json")))
                    .updateSql(
                        "UPDATE work_item "
                      + "SET state = 'CLAIMED', "
                      + "    claimed_at = CURRENT_TIMESTAMP, "
                      + "    attempt_count = attempt_count + 1 "
                      + "WHERE id IN (:ids) AND state = 'NEW'")
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> rows = (List<?>) result;
                        List<Long> ids = rows.stream()
                            .map(JobRow.class::cast)
                            .map(JobRow::id)
                            .toList();
                        return new MapSqlParameterSource("ids", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(3))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .filter(payload ->
                payload instanceof List<?> list && !list.isEmpty())
            .split()
            .channel("lockedJobs")
            .get();
    }
}
~~~

**Hợp đồng của ví dụ:**

1. Poller mở một transaction read-write cho SELECT/UPDATE.
2. PostgreSQL trả các rows `NEW` **không bị khóa** bởi worker khác.
3. RowMapper tạo `List<JobRow>`.
4. `updateSqlParameterSourceFactory` dùng **danh sách kết quả của chính SELECT** để bind `:ids`.
5. UPDATE các rows vừa lock trước khi transaction kết thúc.
6. Adapter phát một message chứa list; splitter tách thành mỗi `JobRow` một message.

**Giới hạn thiết kế:** đoạn này đánh dấu `CLAIMED`, nhưng **chưa cấp claim_token/lease và chưa giải quyết crash sau COMMIT**. Một handler trên `lockedJobs` có thể chạy ở transaction khác, đặc biệt nếu channel/handler tạo async boundary. Đây là ví dụ học **locking đúng cho SELECT+UPDATE**, không phải pipeline production đầy đủ.

### 9.1. Handler cần nhận payload nào?

~~~java
package com.example.integration;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class LockedJobConsumer {

    @ServiceActivator(inputChannel = "lockedJobs")
    public void process(LockedJdbcInboundFlow.JobRow job) {
        System.out.println(job.eventId());
    }
}
~~~

Handler nhận `JobRow` đơn vì upstream có `split()`. `System.out.println` chỉ là demo, không phải durable acknowledgement hoặc broker commit. Khi thực tế cần Kafka/JMS, phải có retry/lease/outbox và business event ID ổn định.

## 10. Spring Integration 6.x: dùng JdbcPollingChannelAdapter trực tiếp

Java DSL factory `Jdbc.inboundAdapter(...)` được giới thiệu từ Spring Integration 7.0. Với **6.x**, tạo `JdbcPollingChannelAdapter` và bọc poller bằng transaction:

~~~java
package com.example.integration;

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
public class LegacyLockedJdbcFlow {

    @Bean
    public IntegrationFlow lockedJobsSix(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource,
                "SELECT id, event_id, payload_json "
              + "FROM work_item WHERE state='NEW' "
              + "ORDER BY created_at, id LIMIT 20 "
              + "FOR UPDATE SKIP LOCKED");
        source.setMaxRows(20);
        source.setRowMapper((rs, n) ->
            new LockedJdbcInboundFlow.JobRow(
                rs.getLong("id"),
                rs.getString("event_id"),
                rs.getString("payload_json")));
        source.setUpdateSql(
            "UPDATE work_item SET state='CLAIMED' "
          + "WHERE id IN (:ids) AND state='NEW'");
        source.setUpdateSqlParameterSourceFactory(result -> {
            var rows = (java.util.List<?>) result;
            var ids = rows.stream()
                .map(LockedJdbcInboundFlow.JobRow.class::cast)
                .map(LockedJdbcInboundFlow.JobRow::id)
                .toList();
            return new MapSqlParameterSource("ids", ids);
        });

        return IntegrationFlow.from(source, endpoint ->
                endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(3))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .split()
            .channel("lockedJobsSix")
            .get();
    }
}
~~~

Đây là **phương án thay thế** flow 7.x, không bật đồng thời cả hai khi thử chức năng một worker trên cùng bảng. DDL `work_item` ở mục 6 và Java DTO `JobRow` được dùng chung để rút ngắn ví dụ. Nếu thực hành độc lập trên 6.x, đưa record `JobRow` vào một file DTO không phụ thuộc lớp cấu hình 7.x.

## 11. XML: transaction cần bao toàn bộ SELECT và UPDATE

~~~xml
<!-- XML fragment; khai báo namespace int và int-jdbc. -->
<int:channel id="lockedBatches"/>

<int-jdbc:inbound-channel-adapter
    id="lockedJdbcPoller"
    data-source="dataSource"
    channel="lockedBatches"
    query="SELECT id, event_id, payload_json
           FROM work_item
           WHERE state='NEW'
           ORDER BY created_at, id
           LIMIT 20
           FOR UPDATE SKIP LOCKED"
    update="UPDATE work_item
            SET state='CLAIMED'
            WHERE id IN (:id) AND state='NEW'"
    max-rows="20">
    <int:poller fixed-delay="3000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

Với mapper mặc định, `:id` được tạo từ column `id` của result list. XML là fragment và cần các Spring beans/namespaces tương ứng. Nếu cần mỗi row một message, đặt một `<int:splitter>` ở downstream; transaction vẫn phụ thuộc vào tính đồng bộ của channel và poller.

**Không đặt `FOR UPDATE SKIP LOCKED` vào một câu SELECT report/read-only** không có cùng transaction với UPDATE. Lock sẽ không giúp claim khi nó đã được giải phóng.

## 12. Atomic claim: chỉ phát đúng các rows thực sự được UPDATE

Cách `SELECT → UPDATE` qua adapter đơn giản có một điểm khó kiểm chứng: danh sách row được tạo **trước UPDATE**, trong khi result list không tự thay đổi theo update count. Với queue nhiều instances, một giải pháp mạnh hơn là **atomic claim**: chọn và đánh dấu trong **một SQL statement**, nhận các rows **đã thật sự bị UPDATE**.

Trên PostgreSQL, kết hợp CTE, row lock và `UPDATE ... RETURNING`:

~~~sql
WITH picked AS (
    SELECT id
    FROM work_item
    WHERE state = 'NEW'
    ORDER BY created_at, id
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE work_item AS w
SET state = 'CLAIMED',
    claimed_by = :workerId,
    claim_token = :claimToken,
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds',
    attempt_count = attempt_count + 1
FROM picked
WHERE w.id = picked.id
RETURNING w.id, w.event_id, w.payload_json,
          w.claim_token;
~~~

**Đặc điểm:**

- `picked` chỉ chứa tối đa 20 IDs `NEW` mà transaction có thể khóa.
- `UPDATE` thay đổi **chính** những IDs ấy trong cùng statement/transaction.
- `RETURNING` trả dữ liệu từ **các rows đã được UPDATE**, không phải từ một SELECT rời rạc.
- `claim_token` định danh **lần sở hữu** hiện tại; khi reclaim, tạo token mới.
- `lease_until` giới hạn thời gian worker được quyền hoàn tất theo hợp đồng.
- Nếu không claim được row nào, statement trả **0 rows**; đó không mặc nhiên là lỗi.
- `RETURNING` không bảo đảm thứ tự phát message; nếu downstream yêu cầu thứ tự, cần sắp xếp theo key sau khi nhận, và thiết kế order xuyên workers riêng.

**Quan trọng:** đây là **PostgreSQL SQL**, không phải cú pháp SQL di động. SQL thực tế cần test transaction isolation, index, driver, retry và row count theo DB đang triển khai.

### 12.1. Vì sao không nhét UPDATE RETURNING vào JDBC inbound SELECT tùy ý?

`JdbcPollingChannelAdapter` được thiết kế chủ yếu để thực hiện một **SELECT query** sinh message, kèm một **UPDATE query** tùy chọn. Một câu `UPDATE ... RETURNING` là một dạng **DML có result set** của PostgreSQL. Không mặc định rằng `query=...` của adapter sẽ có cùng semantics như message source cho statement này trên mọi driver/phiên bản.

Nếu chọn atomic-claim SQL, cách dễ kiểm soát là viết **`MessageSource` riêng sử dụng Spring JDBC** hoặc stored procedure phù hợp. Khi đó bạn có thể xác nhận chính xác danh sách rows được claim trong `RETURNING`, dùng transaction manager ở poller và tạo message từ result set thật.

## 13. MessageSource atomic claim bằng NamedParameterJdbcTemplate

### 13.1. DTO cho những rows đã được claim

~~~java
package com.example.integration;

import java.util.UUID;

public record ClaimedJob(
    long id,
    String eventId,
    String payloadJson,
    UUID claimToken) {
}
~~~

Với DTO này, business key `eventId` ổn định qua retries; `claimToken` lại thay đổi theo **mỗi lần nhận quyền xử lý**. Không dùng claim token làm ID sự kiện gửi Kafka, vì token mới ở lần retry khiến consumer khó dedupe.

### 13.2. Tạo nguồn đọc atomic UPDATE RETURNING

~~~java
package com.example.integration;

import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import org.springframework.integration.endpoint.AbstractMessageSource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

public final class AtomicClaimMessageSource
        extends AbstractMessageSource<List<ClaimedJob>> {

    private static final String CLAIM_SQL = """
        WITH picked AS (
            SELECT id
            FROM work_item
            WHERE state = 'NEW'
            ORDER BY created_at, id
            LIMIT 20
            FOR UPDATE SKIP LOCKED
        )
        UPDATE work_item AS w
        SET state = 'CLAIMED',
            claimed_by = :workerId,
            claim_token = :claimToken,
            claimed_at = CURRENT_TIMESTAMP,
            lease_until =
                CURRENT_TIMESTAMP + INTERVAL '90 seconds',
            attempt_count = attempt_count + 1
        FROM picked
        WHERE w.id = picked.id
        RETURNING w.id, w.event_id,
                  w.payload_json, w.claim_token
        """;

    private final NamedParameterJdbcTemplate jdbc;
    private final String workerId;

    public AtomicClaimMessageSource(
            NamedParameterJdbcTemplate jdbc,
            String workerId) {
        this.jdbc = jdbc;
        this.workerId = workerId;
    }

    @Override
    protected Object doReceive() {
        UUID token = UUID.randomUUID();

        MapSqlParameterSource params =
            new MapSqlParameterSource()
                .addValue("workerId", workerId)
                .addValue("claimToken", token);

        List<ClaimedJob> claimed = jdbc.query(
            CLAIM_SQL, params,
            (rs, rowNum) -> new ClaimedJob(
                rs.getLong("id"),
                rs.getString("event_id"),
                rs.getString("payload_json"),
                rs.getObject("claim_token", UUID.class)));

        if (claimed.isEmpty()) {
            return null;
        }

        // RETURNING không hứa giữ thứ tự CTE.
        claimed.sort(Comparator.comparingLong(ClaimedJob::id));
        return claimed;
    }

    @Override
    public String getComponentType() {
        return "jdbc:atomic-claim-work-item";
    }
}
~~~

Đây là **PostgreSQL-specific**. Spring JDBC dùng JDBC driver thực thi statement có `RETURNING` và map result set; cần kiểm thử phiên bản PgJDBC/SQL cụ thể. `AbstractMessageSource` đóng gói payload `List<ClaimedJob>` thành một message; `return null` biểu thị lượt này không có message.

**Giới hạn của source:** nó *claim* rows, chưa ghi outbox/hoàn tất. Nếu downstream làm việc bền vững trong **cùng transaction** trước khi COMMIT, cả claim lẫn staging có thể rollback chung. Nếu downstream bất đồng bộ và poller commit ngay, phải có lease/recovery để không kẹt việc.

## 14. Ghi outbox, chốt claim và cấu hình flow

### 14.1. OutboxStager chỉ thao tác trong cùng database

~~~java
package com.example.integration;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class JobOutboxStager {

    private final JdbcTemplate jdbc;

    public JobOutboxStager(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void stage(ClaimedJob job) {
        // event_id UNIQUE: không stage cùng event hai lần.
        jdbc.update(
            "INSERT INTO job_outbox "
          + "(event_id, work_id, payload_json) "
          + "VALUES (?, ?, ?)",
            job.eventId(), job.id(), job.payloadJson());

        int updated = jdbc.update(
            "UPDATE work_item "
          + "SET state='STAGED', staged_at=CURRENT_TIMESTAMP "
          + "WHERE id=? AND state='CLAIMED' AND claim_token=?",
            job.id(), job.claimToken());

        if (updated != 1) {
            throw new IllegalStateException(
                "Worker no longer owns job " + job.id());
        }
    }
}
~~~

Nếu `INSERT` trùng event ID, `DuplicateKeyException` thường khiến transaction thất bại. Với recovery có replay, ứng dụng phải kiểm tra event đã stage **cùng nội dung** hay là conflict, không catch mọi unique violation rồi coi đã thành công.

`WHERE claim_token=?` là **fencing condition** ở database: một worker giữ token cũ không được chốt trạng thái sau khi token bị thay. Đây chưa phải distributed fencing ở remote service; remote cũng cần version/idempotency nếu công việc có side effect bên ngoài.

### 14.2. Transactional IntegrationFlow cho source tùy chỉnh

~~~java
package com.example.integration;

import java.time.Duration;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class AtomicClaimFlowConfiguration {

    @Bean
    public AtomicClaimMessageSource atomicClaimSource(
            DataSource dataSource,
            @Value("${app.worker-id}") String workerId) {
        return new AtomicClaimMessageSource(
            new NamedParameterJdbcTemplate(dataSource), workerId);
    }

    @Bean
    public IntegrationFlow stageClaimedJobs(
            AtomicClaimMessageSource source,
            JobOutboxStager stager,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow.from(source,
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(2))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .split()
            .handle(stager, "stage")
            .get();
    }
}
~~~

Đặt `app.worker-id` là **ID duy nhất của worker instance**, được cấp từ deployment/config; không dùng ID cố định giống nhau cho các pods. Nếu yêu cầu leader/partition ownership phức tạp hơn, áp dụng cơ chế điều phối tương ứng.

**Bảo đảm trong mẫu này chỉ khi:**
- `AtomicClaimMessageSource`, `JobOutboxStager`, `PlatformTransactionManager` dùng **cùng DataSource**.
- Không có `ExecutorChannel`/`QueueChannel` bất đồng bộ giữa source và writer.
- `JobOutboxStager.stage` ném lỗi khi staging thất bại; poller không nuốt exception rồi COMMIT.
- Database transaction rollback nếu handler thất bại.
- Publisher outbox chạy riêng và xử lý retry/idempotency.

Như vậy một transaction có thể vừa claim các hàng, vừa ghi outbox bền, vừa đổi `CLAIMED → STAGED`. Kafka/JMS publish chỉ xảy ra **sau** khi commit transaction này.

### 14.3. Vì sao cần hai loại ID?

| ID | Ví dụ | Có ổn định qua retry? | Mục đích |
|---|---|---|---|
| `work_item.id` | 101 | Có | Khóa hàng DB |
| `event_id` | `evt-101` | **Có** | Dedupe business event/consumer |
| `claim_token` | UUID mỗi claim | **Không** | Chống stale worker chốt trạng thái |
| `worker_id` | `pod-2` | Theo vòng đời instance | Logs, lease owner, vận hành |
| `poll_id` | Một correlation ID mỗi poll | Không | Trace một lần source.receive |

Một token/UUID sinh lại theo từng retry **không phù hợp làm event ID** nếu consumer dùng event ID để tránh tác dụng nghiệp vụ trùng lặp.

## 15. SQL Server: UPDLOCK, READPAST và OUTPUT

SQL Server không dùng cú pháp PostgreSQL `FOR UPDATE SKIP LOCKED`. Thông dụng là kết hợp **`UPDLOCK`** để lấy update locks khi đọc và **`READPAST`** để bỏ qua hàng có row locks từ transaction khác; **`ROWLOCK`** là gợi ý, không phải bảo đảm DB sẽ chỉ lấy row locks.

Ví dụ khóa khi đọc trong một transaction:

~~~sql
-- SQL Server, ví dụ SELECT ở isolation/read-committed phù hợp.
SELECT TOP (20)
    id, event_id, payload_json
FROM dbo.work_item WITH (
    UPDLOCK, READPAST, ROWLOCK, READCOMMITTEDLOCK
)
WHERE state = 'NEW'
ORDER BY created_at, id;
~~~

**Các giới hạn thực tế:**
- `READPAST` bỏ qua **row-level locks**, nhưng **không** tự bỏ qua page-level locks.
- `UPDLOCK` giúp giữ khóa cập nhật cho tới transaction kết thúc, giảm hai readers cùng chọn job.
- Khi bật `READ_COMMITTED_SNAPSHOT`, việc kết hợp hints và isolation bị hạn chế; theo Microsoft docs có tình huống cần `READCOMMITTEDLOCK`.
- Cần kiểm tra lock escalation, deadlocks, index access plan và database compatibility level.
- `NOLOCK/READUNCOMMITTED` **không phải** biện pháp queue concurrency an toàn: nó có thể đọc dữ liệu chưa commit.

SQL Server hỗ trợ `OUTPUT inserted...` để trả các hàng thực sự được UPDATE. Cấu trúc minh họa có thể kết hợp CTE chọn hàng cần claim:

~~~sql
-- SQL Server T-SQL, cần test đúng isolation/lock hints.
;WITH picked AS (
    SELECT TOP (20) id
    FROM dbo.work_item WITH (
        UPDLOCK, READPAST, ROWLOCK, READCOMMITTEDLOCK
    )
    WHERE state='NEW'
    ORDER BY created_at, id
)
UPDATE w
SET state='CLAIMED',
    claimed_by=@workerId,
    claimed_at=SYSUTCDATETIME(),
    attempt_count=attempt_count+1
OUTPUT inserted.id, inserted.event_id,
       inserted.payload_json
FROM dbo.work_item AS w
JOIN picked AS p ON p.id=w.id;
~~~

Câu lệnh trả **các rows đã thay đổi** theo `OUTPUT`, nhưng syntax/parameter binding của `@workerId` thuộc T-SQL client; khi dùng Spring JDBC, bạn phải bind tham số theo driver/template phù hợp, không copy `@workerId` như thể đó là named parameter `:workerId` của Spring. DDL ở mục 6 là PostgreSQL và **không thể chạy nguyên văn** trên SQL Server vì kiểu `TIMESTAMPTZ`/`UUID` khác.

## 16. MySQL 8.0+/8.4 InnoDB: SKIP LOCKED có nhưng khác PostgreSQL

MySQL InnoDB hỗ trợ locking read `SELECT ... FOR UPDATE SKIP LOCKED` trong transaction:

~~~sql
-- MySQL InnoDB, autocommit phải được quản lý theo transaction.
START TRANSACTION;

SELECT id, event_id, payload_json
FROM work_item
WHERE state = 'NEW'
ORDER BY created_at, id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- UPDATE các IDs đã SELECT và giữ lock, cùng transaction.
UPDATE work_item
SET state='CLAIMED', claimed_by=?
WHERE id IN (?,?,...) AND state='NEW';

COMMIT;
~~~

Dấu `?` là JDBC bind placeholders minh họa; không nối danh sách ID vào SQL string không kiểm soát. Với Spring `NamedParameterJdbcTemplate` có thể dùng `:ids` và collection bind.

**Điểm khác cần nhớ:**
- InnoDB ở `REPEATABLE READ` có thể dùng **next-key/gap locks**; cách đánh index và isolation ảnh hưởng phạm vi locks.
- `SKIP LOCKED` cho view không nhất quán, phù hợp work queue chứ không phải báo cáo chính xác.
- MySQL docs lưu ý statements có `NOWAIT/SKIP LOCKED` không an toàn cho **statement-based replication**; cần xem replication format.
- Không giả định MySQL phiên bản đang dùng hỗ trợ `UPDATE ... RETURNING` như PostgreSQL; thường chọn SELECT locking + UPDATE cùng transaction hoặc stored procedure/claim strategy khác.

MySQL không phải H2. Hãy thực hiện concurrency test trên InnoDB thật và kiểm tra transaction/autocommit qua Spring JDBC.

## 17. Oracle và các DB vendors khác

Oracle có `SELECT ... FOR UPDATE SKIP LOCKED` trong các phiên bản phù hợp, nhưng tương tác với `FETCH FIRST`, `ROWNUM`, cursor/fetch và locking query có những giới hạn theo phiên bản và cấu trúc SQL.

~~~sql
-- Oracle: skeleton locking read, chưa giới hạn batch.
SELECT id, event_id, payload_json
FROM work_item
WHERE state = 'NEW'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED;
~~~

**Không ghép `FETCH FIRST n ROWS ONLY` vào mọi query `FOR UPDATE` rồi mặc định chạy trên tất cả Oracle versions.** Một số phiên bản/cách viết có hạn chế cú pháp hoặc hành vi khóa. Hãy chọn cơ chế bounded fetch, stored procedure hoặc atomic claim theo tài liệu/driver Oracle đang triển khai và chạy concurrency test thật.

Ma trận tóm tắt:

| DB vendor | Cách tiếp cận phổ biến | Phải kiểm tra riêng |
|---|---|---|
| PostgreSQL | `FOR UPDATE SKIP LOCKED`; `UPDATE ... RETURNING` | CTE, lock timeout, READ COMMITTED, starvation |
| SQL Server | `UPDLOCK + READPAST`; `OUTPUT inserted` | RCSI, row/page locks, lock escalation |
| MySQL InnoDB | `FOR UPDATE SKIP LOCKED` + UPDATE cùng transaction | Next-key/gap locks, replication, isolation |
| Oracle | `FOR UPDATE SKIP LOCKED` + bounded fetch/procedure | Version-specific syntax/fetch/locking |
| H2 | Test cơ bản schema/SQL | Không chứng minh concurrency behavior production |

**Không tồn tại một flag `setSkipLocked(true)` duy nhất trên `JdbcPollingChannelAdapter`** tự dịch ra đúng SQL của tất cả vendors. Chọn SQL strategy và transaction theo database thực tế.

## 18. Lease và recovery: lock chỉ tồn tại đến COMMIT

Row locks giúp bảo vệ **giai đoạn claim trong transaction**, nhưng sau COMMIT, lock được giải phóng. Nếu worker được phép giữ việc trong thời gian dài hoặc xử lý async, cần **lease**:

~~~text
t0  Worker A atomic claim job 101, lease_until = t0 + 90s
t1  COMMIT -> row locks được giải phóng
t2  Worker A bắt đầu xử lý ngoài DB transaction
t3  Worker A crash / mất kết nối
t4  Lease hết hạn; worker B có thể reclaim job 101
t5  Worker B có token mới; worker A nếu còn chạy không được chốt DONE
~~~

Một query phát hiện lease hết hạn:

~~~sql
SELECT id, event_id, claimed_by, claim_token, lease_until
FROM work_item
WHERE state = 'CLAIMED'
  AND lease_until < CURRENT_TIMESTAMP
ORDER BY lease_until, id;
~~~

**Chỉ SELECT lease expired rồi UPDATE sau đó** vẫn có race giữa các recovery workers. Reclaim cần **atomic claim** hoặc row locks theo cùng protocol.

### 18.1. Atomic reclaim có token mới (PostgreSQL)

~~~sql
WITH expired AS (
    SELECT id
    FROM work_item
    WHERE state = 'CLAIMED'
      AND lease_until < CURRENT_TIMESTAMP
    ORDER BY lease_until, id
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE work_item AS w
SET claimed_by = :newWorkerId,
    claim_token = :newToken,
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds',
    attempt_count = attempt_count + 1
FROM expired
WHERE w.id = expired.id
RETURNING w.id, w.event_id, w.claim_token;
~~~

Mỗi lần reclaim đổi token; token cũ phải hết quyền cập nhật trạng thái. Vì hai transactions vẫn có thể cạnh tranh, `FOR UPDATE SKIP LOCKED` và `UPDATE ... RETURNING` được đặt trong cùng statement.

**Chính sách attempt:** nếu vượt số lần retry, chuyển `FAILED`/DLQ có audit thay vì reclaim vô hạn. Việc phát hiện job không còn ownership phải được phân loại khác với một lỗi mạng tạm thời.

## 19. Fencing token: chặn worker cũ hoàn tất nhầm

Giả sử worker A bị stop-the-world GC hoặc mất kết nối lâu, lease hết hạn và worker B đã reclaim với token mới. A thức dậy và muốn ghi `DONE`.

DML đúng phải kiểm tra token và trạng thái:

~~~sql
UPDATE work_item
SET state='STAGED',
    staged_at=CURRENT_TIMESTAMP
WHERE id=:jobId
  AND state='CLAIMED'
  AND claim_token=:claimToken;
~~~

Nếu affected rows = `0`, worker đã **mất quyền sở hữu** hoặc job đã chuyển trạng thái. Nó không được ghi đè bằng một câu UPDATE chỉ có `WHERE id=:jobId`.

Nếu dùng numeric `claim_version` thay UUID, mỗi reclaim tăng version và mọi completion UPDATE phải so sánh version. Điều này hữu ích khi cần token có thứ tự monotonic.

**Fencing trong DB không tự chặn remote side effects:** A vẫn có thể gửi HTTP hoặc Kafka từ bên ngoài database dù không còn quyền ghi `STAGED`. Để bảo vệ remote service, cần remote hỗ trợ idempotency key, fencing version hoặc một protocol kiểm soát nguồn/consumer. Không hứa “đã có lease thì không còn duplicate effects”.

### 19.1. Gia hạn lease

Với job chạy lâu, worker còn quyền có thể heartbeat:

~~~sql
UPDATE work_item
SET lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds'
WHERE id = :jobId
  AND state = 'CLAIMED'
  AND claim_token = :claimToken
  AND lease_until > CURRENT_TIMESTAMP;
~~~

Nếu UPDATE ảnh hưởng 0 rows, token có thể hết hạn/đã bị reclaim; worker phải dừng hoặc chuyển sang reconciliation, không tự coi gia hạn thành công.

Đo thời gian lease dựa trên **đồng hồ database** giảm rủi ro clock skew giữa các pods. Lease duration phải lớn hơn thời gian critical section điển hình, có heartbeat/recovery policy và metrics cho jobs kẹt.

## 20. Transaction boundary: DirectChannel và ExecutorChannel

~~~mermaid
flowchart LR
    A["Poller BEGIN"] --> B["Atomic claim SQL"]
    B --> C["DirectChannel / Splitter"]
    C --> D["Insert outbox + STAGED"]
    D --> E["COMMIT cùng DB"]
    B --> F["ExecutorChannel"]
    F --> G["Async worker"]
    G --> H["TX khác; không rollback claim cũ"]
~~~

**Khi dùng `DirectChannel`:** đồng bộ handlers ở cùng poller thread có thể tham gia local JDBC transaction. Source claim và writer stage outbox cùng DataSource/transaction manager; nếu writer ném exception và nó truyền ra ngoài, cả claim lẫn outbox rollback.

**Khi dùng `ExecutorChannel` hoặc `QueueChannel`:** message được handoff sang thread/poller khác; transaction của poller có thể COMMIT trước khi việc ở worker xong. Vì vậy source có thể đã ghi `CLAIMED` nhưng worker chưa có durable work. Muốn an toàn, stage outbox/persistent queue **trước** async boundary, hoặc xây lease/recovery và idempotency.

**Không giữ DB transaction mở để chờ Kafka producer response hoặc HTTP call lâu.** Một transaction kéo dài giữ connections/locks, giảm throughput và tăng nguy cơ deadlock. Phân tách nhanh **claim + durable stage + COMMIT**, rồi publish riêng.

## 21. Crash windows: khóa ngăn tranh chấp, không bảo đảm giao hàng

| Crash window | Row lock / DB state | Khôi phục như thế nào? |
|---|---|---|
| Trước transaction claim | `NEW` | Worker khác claim bình thường |
| Sau SELECT lock nhưng trước UPDATE | Transaction rollback, lock nhả | Retry/worker khác claim |
| Sau UPDATE nhưng trước COMMIT | UPDATE rollback | Không mất job |
| Sau COMMIT `CLAIMED`, trước stage | Lock đã nhả, job đang CLAIMED | Lease/reclaim cần có |
| Trong stage outbox cùng transaction | Claim + outbox rollback khi lỗi | Poll lại |
| Sau COMMIT `STAGED` + outbox | Outbox bền vững | Publisher xử lý tiếp |
| Broker đã nhận, chưa ghi `published` | Có thể còn outbox pending | Publish lại, consumer idempotent |
| Worker A bị treo, B reclaim | Token của A không còn hợp lệ | Fencing ở DB và remote idempotency |

**Không gộp `CLAIMED`, `STAGED`, `PUBLISHED` và “consumer đã xử lý thành công” thành cùng một trạng thái**. Mỗi mốc có sự kiện commit/ACK khác nhau.

## 22. Idempotency và outbox: tránh duplicate business effects

Locking và atomic claim chỉ đảm bảo **quyền lấy việc tại một thời điểm**. Trên mạng, một request có thể thành công ở remote rồi timeout tại client. Retry khi không biết outcome có thể gửi trùng. Outbox và idempotent receiver giải quyết tầng này.

~~~mermaid
flowchart LR
    A["DB transactional claim"] --> B["Outbox record (stable eventId)"]
    B --> C["COMMIT"]
    C --> D["Kafka/JMS publisher"]
    D --> E["Consumer nhận một hoặc nhiều lần"]
    E --> F["Dedupe eventId + business TX"]
    F --> G["Business effect một lần"]
~~~

| Thành phần | Hợp đồng |
|---|---|
| `event_id` | Không đổi qua claim/retry/redelivery |
| `job_outbox.event_id UNIQUE` | Không tạo nhiều outbox rows cho cùng event |
| `processed_event(event_id UNIQUE)` | Consumer ghi marker trong cùng transaction business |
| Producer ACK | Broker đã nhận theo contract producer; không chứng minh consumer xử lý |
| Consumer offset/JMS ACK | Xác nhận tiến độ consumer; không tự commit atomically với DB |
| Reconciliation | So sánh pending/staged/published và trạng thái đích khi outcome không chắc |

### 22.1. Ví dụ idempotent consumer trên database

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(80) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Một consumer transaction thường làm:
1. `INSERT INTO processed_event(event_id) VALUES (:eventId) ON CONFLICT DO NOTHING`.
2. Nếu insert 0 rows, đã có event; xác nhận duplicate hợp lệ và **không thực hiện lại side effect**.
3. Nếu insert 1 row, thực hiện business UPDATE trong **cùng transaction**.
4. COMMIT rồi ACK Kafka/JMS theo container policy.

Marker phải nằm trong transaction cùng business DML; nếu đánh dấu processed trước rồi commit riêng, crash có thể gây **mất xử lý**. Nếu có external HTTP side effect, DB marker vẫn chưa đủ để đảm bảo remote exactly-once; cần idempotency key/remote reconciliation.

## 23. Isolation level và MVCC có thay thế locking không?

Transaction isolation quyết định transaction đọc được dữ liệu nào và DB điều phối concurrency như thế nào. **MVCC/READ COMMITTED không đồng nghĩa worker đã claim row.** Hai transactions ở READ COMMITTED đều có thể SELECT row `NEW` nếu không lấy lock hoặc không thực thi atomic DML.

| Isolation | Ý nghĩa khái quát | Lưu ý với work queue |
|---|---|---|
| `READ_UNCOMMITTED` | Cho phép hoặc được nâng lên mức thực tế theo DB vendor | Không phải giải pháp; dirty reads nguy hiểm |
| `READ_COMMITTED` | Thường chỉ thấy committed rows | SELECT thường chưa tạo ownership |
| `REPEATABLE_READ` | Snapshot/lock tùy database | Có thể tăng contention, vẫn phải thiết kế claim |
| `SERIALIZABLE` | Tăng isolation để xử lý anomalies | Có thể sinh serialization failures, cần retry toàn TX |
| `DEFAULT` | Theo datasource/database | Phải biết giá trị thực ở runtime |

Ví dụ `@Transactional(isolation = Isolation.SERIALIZABLE)` không có nghĩa:
- A và B không thể đồng thời bắt đầu SELECT cùng row theo mọi database;
- một request Kafka đã gửi cũng rollback với database;
- thứ tự ID đồng nghĩa với thứ tự COMMIT;
- không cần kiểm tra affected row count.

**Row lock/atomic claim rõ ràng vẫn là hợp đồng ownership tốt hơn** việc hy vọng một isolation level chung tự giải quyết mọi trường hợp.

### 23.1. Lock chặn đến đâu và giữ đến khi nào?

Các thao tác có thể giữ row locks từ lúc SELECT locking/UPDATE tới COMMIT hoặc ROLLBACK. Khi một transaction giữ locks quá lâu:
- Worker khác skip hoặc chờ cùng row.
- Pool connections đang bị chiếm.
- Deadlocks/lock timeout tăng.
- Starvation có thể khiến một job cũ bị liên tục bỏ qua.

Đây là lý do tách **transaction claim + durable stage ngắn** khỏi xử lý HTTP/Kafka lâu.

## 24. NOWAIT, SKIP LOCKED và chờ lock: chọn behavior phù hợp

| Cơ chế | Khi row đang bị lock | Ưu tiên |
|---|---|---|
| Chờ mặc định | Đợi lock được giải phóng hoặc timeout | Khi cần chính row đó, không thể skip |
| `NOWAIT` | Thất bại ngay khi không lấy được lock | Interactive/low-latency hoặc retry có kiểm soát |
| `SKIP LOCKED` | Bỏ qua rows đang bị lock, lấy rows khác | Queue nhiều workers có backlog |
| Atomic conditional UPDATE | Chỉ claim rows match predicate tại lúc DML | Cần nhận đúng affected rows |
| Lock timeout | Giới hạn thời gian chờ | Bảo vệ threads/connections và cảnh báo contention |

Trên PostgreSQL:

~~~sql
-- Một số lựa chọn tách biệt, không dùng cả hai cùng lúc.
SELECT id FROM work_item
WHERE state='NEW'
FOR UPDATE NOWAIT;

SELECT id FROM work_item
WHERE state='NEW'
FOR UPDATE SKIP LOCKED;
~~~

`SKIP LOCKED` không thay thế vòng đời xử lý lỗi. Nếu một job bị khóa bởi transaction bị treo, các workers khác có thể liên tục bỏ qua nó. Theo dõi **tuổi job lâu nhất**, lock duration, attempts và lease-expired thay vì chỉ nhìn throughput tổng.

### 24.1. Retry sau deadlock phải tạo transaction mới

Nếu database chọn transaction A làm deadlock victim:
1. A phải rollback transaction hiện tại.
2. Trả connection/giải phóng locks phù hợp.
3. Chờ backoff (có jitter) để tránh nhiều replicas retry đồng bộ.
4. Mở transaction mới, chạy lại **atomic claim từ trạng thái database hiện tại**.
5. Chỉ phát messages cho rows được claim thành công ở attempt mới.

**Không retry chỉ câu UPDATE với danh sách ID được SELECT trong transaction đã lỗi**, vì ownership và snapshot có thể đã thay đổi. `SqlParameterSourceFactory` không phải bộ quản lý retries/locks.

## 25. Optimistic version: chống lost update nhưng không đủ cho queue

Một mẫu optimistic locking:

~~~sql
UPDATE work_item
SET state='CLAIMED',
    attempt_count=attempt_count + 1
WHERE id=:id AND state='NEW' AND version=:expectedVersion;
~~~

DDL trong mục 6 chưa có cột `version`; đây là **mở rộng cần ALTER TABLE** cho bài thực hành. Khi affected rows bằng 1, worker đã cập nhật row theo version mong đợi. Khi bằng 0, nó không có quyền tự cho rằng đã claim và không được phát event dựa trên snapshot SELECT cũ.

Sự khác biệt:
- **Optimistic version** phù hợp khi xung đột hiếm, có thể thử lại và xử lý 0 rows.
- **Pessimistic `FOR UPDATE SKIP LOCKED`** phù hợp nhiều consumers giành việc từ một queue.
- **Atomic claim RETURNING/OUTPUT** tạo kết quả rõ ràng từ những rows đã đổi state.
- **Idempotency** vẫn cần khi Kafka/JMS/HTTP redeliver.

Không mở một transaction dài chỉ để khóa một business record trong toàn bộ thời gian remote service xử lý. Có thể dùng optimistic version/idempotency ở bước completion.

## 26. Hiệu năng, batch size, index và fairness

Một số sai lầm khi tối ưu queue:
- `SELECT *` với payload rất lớn trong khi chỉ cần IDs để claim.
- `WHERE state='NEW'` không có index phù hợp.
- `ORDER BY priority DESC, created_at` nhưng index chỉ có `id`; DB phải sort nhiều rows.
- Batch hàng nghìn IDs tạo câu `IN (:ids)` rất dài, tăng lock duration.
- Chạy quá nhiều pollers so với Hikari pool, CPU/IO capacity.
- Giữ transaction khi gọi HTTP/Kafka làm connection wait và lock timeout tăng.
- Dùng OFFSET pagination cho queue đang thay đổi trạng thái, khiến rows bị skip hoặc khóa không cần thiết.
- Chọn batch theo “càng lớn càng nhanh” mà không đo thời gian commit/outbox latency.

### 26.1. Công thức kiểm tra capacity gần đúng

Nếu một poller claim và stage trung bình 20 rows trong 100 ms (đã đo), mỗi poller có thể xử lý tối đa xấp xỉ 200 rows/giây **trong điều kiện không có bottleneck khác**. Con số thực tế thấp hơn do network, DB locks, disk flush, scheduler delay và publish lag. Đây chỉ là cách nghĩ về throughput, không phải benchmark của framework.

Để tránh giữ transaction lâu, hãy đo:
- p50/p95/p99 của `claim transaction duration`;
- rows/claim, rows staged/second, outbox pending;
- lock wait/deadlock count;
- Hikari connections active/pending;
- số rows `NEW` và tuổi row `NEW` lâu nhất.

### 26.2. Starvation và priority

Với `SKIP LOCKED`, một row luôn bị transaction khác lock có thể bị bỏ qua trong nhiều polls. Nếu `ORDER BY priority DESC` luôn chọn ưu tiên cao, một tập ưu tiên thấp có thể chờ vô hạn khi tải cao.

Các cách giảm:
- Theo dõi age của item và phát cảnh báo những item chờ quá lâu.
- Tách queue/partition theo SLA, hoặc dùng aging/fairness policy.
- Giới hạn transaction duration và retry hợp lý.
- Có worker định kỳ xử lý lease-expired/FAILED thay vì chỉ SELECT `NEW`.
- Đánh giá starvation khi có nhiều concurrent pollers và index/ordering khác nhau.

**ORDER BY trong SELECT** không hứa Kafka/JMS nhận message theo cùng thứ tự khi có nhiều workers, splitter, executor threads và broker partitions. Nếu ordering per aggregate là yêu cầu bắt buộc, cần partition ownership và sequencing/event version.

## 27. Metrics, logging và cảnh báo vận hành

| Chỉ số | Ý nghĩa |
|---|---|
| `rows_selected_per_poll` | Số rows đầu vào từ SELECT |
| `rows_actually_claimed` | Số rows thay đổi thật trong UPDATE/RETURNING |
| `claim_conflicts` | UPDATE 0 rows/CAS failures/ownership lost |
| `claim_transaction_duration` | Thời gian giữ transaction, ảnh hưởng lock contention |
| `db_lock_waits` và deadlocks | Chỉ báo concurrency và index |
| `new_backlog`, `oldest_new_age` | Queue lũy kế, starvation |
| `claimed_lease_expired` | Workers chết, treo hoặc hoàn tất chậm |
| `outbox_pending`, `oldest_unpublished_age` | Broker/publisher bị chậm |
| `duplicate_event_seen` | Redelivery/idempotency activity |
| Hikari active/idle/pending | Pool pressure |
| `dlq_failed_jobs` | Work không thể tự retry |

**Báo động sớm:** nếu SELECT 20 rows nhưng UPDATE chỉ sửa 0–5 và ứng dụng vẫn phát 20 messages, có lỗi ownership nghiêm trọng. Thiết kế atomic RETURNING nên lấy chính rows đã claim; monitor sai lệch result counts khi dùng hai câu SQL.

Logs nên có `workerId`, `pollId`, `eventId`, `claimToken` (hạn chế nếu nhạy cảm), count và DB transaction outcome. Không dùng `eventId` làm metric tag cardinality vô hạn; ưu tiên logs/traces. Hạn chế log `payload_json` hoặc customer PII.

## 28. Kiểm thử hai workers cạnh tranh cùng bảng

**Không dùng H2 làm bằng chứng cho PostgreSQL `FOR UPDATE SKIP LOCKED` hoặc SQL Server `READPAST`.** Test concurrency cần hai database connections/transactions độc lập và một DB production-compatible. Testcontainers rất phù hợp.

### 28.1. Kịch bản hai transactions

~~~mermaid
sequenceDiagram
    participant A as Worker A / Transaction A
    participant DB as PostgreSQL
    participant B as Worker B / Transaction B
    A->>DB: BEGIN + claim 20 rows via UPDATE RETURNING
    Note over DB: Locks A giữ đến COMMIT
    B->>DB: BEGIN + claim 20 rows via UPDATE RETURNING
    DB-->>B: 20 rows khác do SKIP LOCKED
    A->>DB: COMMIT
    B->>DB: COMMIT
    Note over A,B: Intersect(claimedIdsA, claimedIdsB) = empty
~~~

Nếu chỉ có 20 rows, B có thể nhận 0 rows khi A đang giữ toàn bộ locks. **Kết quả không trùng** vẫn đúng; việc nhận 0 không phải lỗi.

### 28.2. JUnit concurrency test template

~~~java
package com.example.integration;

import static org.junit.jupiter.api.Assertions.*;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.*;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class AtomicClaimConcurrencyTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    PlatformTransactionManager manager;

    @Test
    void twoWorkersNeverClaimSameIdInOneRace() throws Exception {
        // Setup ở DB PostgreSQL test: ít nhất 40 rows NEW;
        // không có poller tự chạy song song với test.
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Set<Long>> claim = () -> {
            var source = new AtomicClaimMessageSource(
                new NamedParameterJdbcTemplate(dataSource),
                "test-" + UUID.randomUUID());
            source.afterPropertiesSet();
            start.await();

            return new TransactionTemplate(manager).execute(status -> {
                Message<?> message = source.receive();
                if (message == null) {
                    return Set.<Long>of();
                }
                List<?> payload = (List<?>) message.getPayload();
                Set<Long> ids = new HashSet<>();
                for (Object item : payload) {
                    ids.add(((ClaimedJob) item).id());
                }
                return ids;
            });
        };

        try {
            Future<Set<Long>> left = executor.submit(claim);
            Future<Set<Long>> right = executor.submit(claim);
            start.countDown();

            Set<Long> a = left.get(10, TimeUnit.SECONDS);
            Set<Long> b = right.get(10, TimeUnit.SECONDS);
            assertTrue(java.util.Collections.disjoint(a, b));
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

**Đây là template**, cần Testcontainers PostgreSQL, dữ liệu test độc lập và transaction manager gắn với đúng `DataSource`. Test chỉ xác nhận **không trùng claimed IDs trong cuộc đua này**, chưa chứng minh crash recovery hoặc Kafka idempotency. Lặp test với nhiều interleavings, số workers, lock contention và fault injection. Không chạy cùng những `IntegrationFlow` đang polling bảng test ở background.

### 28.3. Vì sao kiểm tra trực tiếp database?

Một `Message<?>` nhận được không đủ chứng minh transaction đã COMMIT. Sau test, query `work_item` để xác nhận số rows `CLAIMED`, token khác nhau, attempt_count và số rows `NEW` còn lại. Với test outbox, kiểm tra cả `job_outbox` sau khi writer thành công/rollback.

## 29. Ma trận kiểm thử transaction và crash recovery

| Test case | Kỳ vọng |
|---|---|
| Hai workers SELECT thường cùng row | Race được tái hiện trong cấu hình không locking |
| Một worker `FOR UPDATE` đang giữ lock | Worker khác `SKIP LOCKED` bỏ qua các rows bị khóa |
| A rollback sau lock/UPDATE | Rows trở lại `NEW`; B claim được lần sau |
| A commit claim, worker chết | Job ở `CLAIMED`, lease expiry/reclaim hoạt động |
| A xử lý lâu, B reclaim | Token A cũ không hoàn tất thành công |
| A stage outbox row 1 rồi lỗi row 2 | Cả claim và outbox rollback cùng DB transaction |
| Publisher gửi Kafka rồi crash trước `published` | Event có thể gửi lại, consumer xử lý idempotent |
| Duplicate event ID nhưng payload khác | Phát hiện conflict, không silently drop |
| `UPDATE count = 0` | Không phát event như đã sở hữu row |
| Hikari pool quá nhỏ | Báo acquire waits và có bounded concurrency |
| Deadlock xảy ra | Transaction rollback, retry toàn claim với backoff |
| SQL Server RCSI ON | Hints/isolation được xác nhận theo Microsoft docs |
| MySQL InnoDB REPEATABLE READ | Lock scope/next-key được đo trên DB thật |
| Starvation một row lock lâu | Metrics phát hiện oldest pending tăng |
| Lease clock skew | So sánh dùng DB clock thay vì worker clocks |
| Job priority lớn | Ordering/fairness rõ và không suy ra broker order |

Test cần đọc lại DB state **sau COMMIT**, không chỉ assert `send()==true` hay số callback được gọi. Với Kafka/JMS cần test broker ACK/redelivery theo container và producer settings thực tế.

## 30. Checklist production cho JDBC work queue

1. Đã chọn **một DB vendor và version cụ thể**, xác minh SQL locking syntax.
2. Transaction manager dùng **đúng DataSource**, poller mở transaction trước SELECT/claim.
3. Không dùng autocommit cho hai bước SELECT locking rồi UPDATE cần atomic.
4. Nếu multi-instance, chọn `SKIP LOCKED` hoặc atomic claim; không chỉ dùng `WHERE state='NEW'`.
5. Payload từ custom source là **các rows đã thực sự claim**, không phải list SELECT cũ sau UPDATE 0.
6. Có unique `event_id` và claim token/version/worker ownership khi cần.
7. Có lease/recovery cho jobs `CLAIMED` tồn tại sau crash.
8. Staging outbox/hoàn tất business DML **cùng transaction** với claim khi cần atomic.
9. Không gọi remote Kafka/HTTP lâu khi đang giữ DB locks.
10. Có idempotent consumer hoặc remote idempotency key.
11. Retry deadlock/serialization bằng transaction **mới**, backoff/jitter có giới hạn.
12. Hệ thống đo rows selected/claimed, lock waits, oldest item age, pending outbox.
13. Có test concurrency hai transactions và fault injection tại các crash windows.
14. Có chính sách xử lý duplicate, conflict, poison message, DLQ, manual replay.
15. Bounded concurrency, SQL index, batch size và pool capacity được đo thực tế.

## 31. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`SELECT WHERE state='NEW'` là độc quyền” | Hai pods vẫn có thể cùng SELECT |
| “UPDATE không báo lỗi là claim thành công” | UPDATE count có thể bằng 0 |
| “`maxMessagesPerPoll(1)` ngăn multi-pod duplicates” | Chỉ giới hạn receive trong một poller |
| “`SKIP LOCKED` dùng được khi autocommit mỗi statement” | SELECT lock cần cùng transaction với UPDATE |
| “`SKIP LOCKED` cho kết quả báo cáo chính xác” | Nó cho inconsistent view, phục vụ queue |
| “`ORDER BY` bảo đảm message ordering toàn hệ thống” | Concurrent workers/broker partitions phá global ordering |
| “H2 test qua nghĩa PostgreSQL/MySQL cũng giống” | Lock behavior theo vendor |
| “`READPAST` bỏ qua mọi page/table locks” | SQL Server chủ yếu skip row locks |
| “`ROWLOCK` luôn buộc SQL Server chỉ row locks” | Hint không thay thế query plan/escalation |
| “`SERIALIZABLE` tự bảo đảm exactly-once Kafka” | Isolation chỉ ở database |
| “Row lock tồn tại sau DB COMMIT” | Lock thường được nhả tại transaction end |
| “Lease hết hạn nghĩa worker cũ đã chết” | Worker cũ có thể vẫn chạy |
| “Claim token tự chặn HTTP side effect cũ” | Remote cần idempotency/fencing support |
| “Event ID nên thay đổi theo mỗi retry” | Event ID phải ổn định để dedupe |
| “Transaction outbox khiến broker chỉ nhận một lần” | Publisher có thể redeliver |
| “`ExecutorChannel` nhận JDBC transaction của poller” | Thread-bound transaction không tự truyền |
| “READ UNCOMMITTED giúp không tranh lock an toàn” | Dirty reads không phải ownership |
| “Retry chỉ UPDATE sau deadlock là đủ” | Phải chạy lại transactional unit |
| “`UPDATE RETURNING` là SQL portable” | Vendor-specific, có SQL Server OUTPUT khác |
| “Locking biến JDBC thành non-blocking” | JDBC vẫn blocking I/O |

## 32. Bài thực hành

1. Tạo bảng `work_item` với các IDs 101–104; chạy hai transactions SELECT thường để tái hiện row 101 bị chọn trùng.
2. Thêm UPDATE `WHERE state='NEW'`, quan sát một worker UPDATE 0 rows nhưng Java list vẫn có row.
3. Đổi sang PostgreSQL `FOR UPDATE SKIP LOCKED` trong transaction, xác minh B không lấy IDs A đang khóa.
4. Bỏ transaction hoặc bật autocommit để thấy khóa SELECT không bảo vệ UPDATE về sau.
5. Dùng Spring Integration 7.x `Jdbc.inboundAdapter` với SELECT locking và transactional poller.
6. Dùng `JdbcPollingChannelAdapter` trong 6.x và cấu hình tương đương bằng XML.
7. So sánh `maxRows(20)` với `maxMessagesPerPoll(1)` và số messages sau splitter.
8. Tạo atomic CTE `UPDATE ... RETURNING`; assert output IDs chính là rows chuyển `CLAIMED`.
9. Viết custom `AtomicClaimMessageSource` + `NamedParameterJdbcTemplate` trên PostgreSQL.
10. Tạo `ClaimedJob` record có event ID ổn định và claim token theo lần ownership.
11. Thêm `JobOutboxStager`, transactional poller, splitter; lỗi ở row thứ hai phải rollback cả claim và outbox.
12. Đặt `ExecutorChannel` giữa claim và staging; nêu cơ chế recovery cần bổ sung để không mất việc.
13. Tạo recovery query cho `CLAIMED` hết lease, triển khai atomic reclaim `RETURNING`.
14. Gia hạn lease với `WHERE claim_token=:token`; cho token sai và kiểm tra UPDATE 0 rows.
15. Mô phỏng A bị pause, B reclaim, A tỉnh lại; kiểm tra A không ghi `STAGED` với token cũ.
16. Viết processed-event unique constraint, gửi duplicate Kafka/JMS và kiểm tra business effect đúng một lần.
17. Dùng SQL Server test `UPDLOCK, READPAST`, thử `READ_COMMITTED_SNAPSHOT` và page locks.
18. Dùng MySQL InnoDB test `FOR UPDATE SKIP LOCKED` và next-key/gap locks với indexes khác nhau.
19. Thử NOWAIT vs SKIP LOCKED, đo latency và lượng công việc nhận được.
20. Tạo deadlock trong DB test rồi retry toàn transaction với backoff/jitter.
21. Thử batch size 5, 20, 100; đo p95 transaction duration, lock waits, pool utilization và outbox lag.
22. Cố tình giữ lock của một row lâu, đo starvation/oldest pending age và thiết kế alert.
23. Viết JUnit test với hai threads + barrier và Testcontainers PostgreSQL, kiểm tra claimed IDs không giao nhau.
24. Mô phỏng crash sau broker ACK trước `published=true`, kiểm tra stable event ID và consumer idempotency.
25. So sánh một-leader, partition ownership, row locking, outbox, CDC cho workload có nhiều producers/consumers.
26. Lập runbook về stuck `CLAIMED`, lease expiry, DLQ, manual replay và đổi phiên bản schema khi các pods còn chạy.

**Tình huống tổng hợp:** hệ thống có ba pods cùng poll 100.000 jobs `NEW`. Pod A claim 20 jobs và bị treo trước khi commit; pod B chọn các jobs tiếp theo bằng `SKIP LOCKED`; pod C claim được 20 jobs nhưng chết sau khi database commit `CLAIMED`, trước khi ghi outbox. Một phút sau pod A sống lại và muốn hoàn tất job đã hết lease. Hãy xác định **transaction boundary, database locks, atomic claim output, claim token, lease/heartbeat, outbox staging, retry và consumer idempotency** để giải quyết từng cửa sổ lỗi mà không mất job hoặc nhân đôi side effects không kiểm soát.

## 33. Tài liệu tham khảo

- [Spring Integration Reference — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): SELECT/UPDATE, list payload, RowMapper, `:id`, transactional poller.
- [Spring Integration Reference — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.inboundAdapter(...)` từ Spring Integration 7.0.
- [Spring Integration API — JdbcPollingChannelAdapter 6.x](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): `setUpdateSql`, `setRowMapper`, `setMaxRows`, factory tham số.
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): poller transaction, DirectChannel và async boundaries.
- [Spring Integration Reference — Distributed Locks](https://docs.spring.io/spring-integration/reference/distributed-locks.html): lock registry khi cần leader/critical section khác với row locking.
- [Spring Framework Reference — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `NamedParameterJdbcTemplate` và row mapping.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `PlatformTransactionManager`, transaction scope, rollback/isolation.
- [PostgreSQL Documentation — SELECT (locking clauses)](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE`, `NOWAIT`, `SKIP LOCKED` và giới hạn.
- [PostgreSQL Documentation — UPDATE](https://www.postgresql.org/docs/current/sql-update.html): `UPDATE ... FROM` và `RETURNING`.
- [Microsoft Learn — SQL Server Table Hints](https://learn.microsoft.com/en-us/sql/t-sql/queries/hints-transact-sql-table): `READPAST`, `UPDLOCK`, `ROWLOCK`, `READCOMMITTEDLOCK`, RCSI.
- [Microsoft Learn — SQL Server OUTPUT Clause](https://learn.microsoft.com/en-us/sql/t-sql/queries/output-clause-transact-sql): `OUTPUT inserted` cho các rows thực sự thay đổi.
- [MySQL 8.4 Reference — InnoDB Locking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html): `FOR UPDATE SKIP LOCKED`, NOWAIT và hạn chế replication.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `FOR UPDATE` và `SKIP LOCKED` theo phiên bản.
- [Spring Integration Reference — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html): khi cần persistent messages/queue thay vì một in-memory channel.

> **Ghi nhớ:** **SELECT một row không đồng nghĩa sở hữu row**. Để nhiều JDBC pollers tránh lấy trùng, cần row-level locking có transaction (ví dụ `FOR UPDATE SKIP LOCKED`), hoặc atomic claim trả về **chính rows đã UPDATE**. Lock chỉ bảo vệ khi transaction còn mở; sau COMMIT phải có lease/recovery nếu xử lý chưa hoàn tất. Khi gửi sang Kafka/JMS/HTTP, hãy kết hợp **stable event ID, transactional outbox và idempotent consumer**: tránh duplicate *claim* và tránh duplicate *business effect* là hai mục tiêu liên quan nhưng khác nhau.
