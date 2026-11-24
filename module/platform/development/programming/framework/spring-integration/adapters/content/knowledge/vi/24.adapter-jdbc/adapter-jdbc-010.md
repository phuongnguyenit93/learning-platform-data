# MetadataStore cho incremental query trong Spring Integration JDBC

## 1. Bài toán: đọc tiếp từ đâu sau khi ứng dụng khởi động lại?

Một ứng dụng Spring Integration cần lấy những bản ghi mới trong bảng `source_event` rồi chuyển chúng sang Kafka, JMS, AMQP, HTTP hoặc một dịch vụ nội bộ. Nếu mỗi lần poll đều `SELECT` toàn bộ bảng, dữ liệu cũ liên tục được đọc lại. Nếu dùng `WHERE state='NEW'` rồi `UPDATE`, ứng dụng phải có quyền sửa bảng nguồn; đôi khi điều này không được cho phép vì database thuộc ERP/đối tác.

Với nguồn dạng append-only, có thể dùng **incremental query**: lưu vị trí cuối cùng đã xử lý, gọi là **checkpoint/high-water mark**, rồi truy vấn các hàng ở phía sau mốc này.

~~~sql
-- Checkpoint đã lưu: last_id = 102.
SELECT id, event_type, payload_json
FROM source_event
WHERE id > 102
ORDER BY id
LIMIT 50;
~~~

Vấn đề xuất hiện ở các ranh giới lỗi:

- Nếu chỉ lưu `lastId` trong một biến Java, cursor mất khi JVM restart.
- Nếu checkpoint được ghi **ngay sau SELECT**, nhưng worker chết trước khi gửi sự kiện, bản ghi có thể bị bỏ qua mãi mãi.
- Nếu hai pods dùng cùng cursor mà không đồng bộ, một pod có thể ghi đè kết quả của pod kia.
- Nếu transaction tạo ID 105 commit **sau** transaction tạo ID 106, cursor nhảy đến 106 có thể làm mất hàng 105.
- Nếu bảng có UPDATE các hàng cũ, cursor chỉ theo `id` không phát hiện các thay đổi đó.

Spring Integration cung cấp `MetadataStore` để giữ thông tin tiến độ dưới dạng key–value. `JdbcMetadataStore` dùng database để giữ giá trị bền vững và có các thao tác nguyên tử dành cho nhiều instances.

Bài thuộc chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành qua file, SFTP, HTTP, JMS, AMQP, Kafka và database, chú trọng hợp đồng message, lỗi và vòng đời kết nối.

~~~mermaid
flowchart LR
    P["Poller"] --> C["Đọc checkpoint"]
    C --> S["SELECT rows > cursor"]
    S --> R["List<EventRow>"]
    R --> W["Ghi việc cần xử lý bền vững"]
    W --> M["CAS checkpoint"]
    M --> D[("JDBC MetadataStore")]
    W --> O[("Outbox")]
    O --> K["Kafka / JMS publisher"]
~~~

**Phân biệt trọng tâm:** metadata chỉ là **trạng thái điều phối**. Nó không chứa đầy đủ các business events và không bảo đảm broker đã nhận dữ liệu.

## 2. MetadataStore, watermark, broker offset và MessageStore

| Khái niệm | Chức năng | Ví dụ |
|---|---|---|
| Cursor/watermark | Vị trí để quyết định dữ liệu tiếp theo | `last_id=102` |
| Checkpoint | Cursor đã được ghi bền vững theo mốc an toàn | `source:last-id → "102"` |
| `MetadataStore` | Lưu chuỗi key/value | `get`, `put`, `remove` |
| `ConcurrentMetadataStore` | Metadata với thao tác điều kiện | `putIfAbsent`, `replace` |
| `JdbcMetadataStore` | Triển khai key/value trên RDBMS | Bảng `INT_METADATA_STORE` |
| `JdbcMessageStore` | Lưu message/message group | Queue, aggregator, claim-check |
| Broker offset/ACK | Tiến độ của consumer/producer broker | Kafka partition offset |
| Idempotency key | Nhận diện event để tránh tác dụng trùng | `event_id` |

Ví dụ một metadata region lưu một checkpoint:

~~~text
REGION = orders-incremental-v1
METADATA_KEY = source-event:last-id
METADATA_VALUE = "102"
~~~

Nếu downstream nhận bản ghi từ Kafka sau đó ghi tiếp vào database, **Kafka offset** và **cursor JDBC** là hai mốc riêng. Không tự xem commit của một trong hai là commit của hệ thống còn lại.

## 3. Các interface và API quan trọng

`org.springframework.integration.metadata.MetadataStore` có hợp đồng key–value:

~~~java
String before = metadataStore.get("orders:last-id");
metadataStore.put("orders:last-id", "102");
String removed = metadataStore.remove("orders:last-id");
~~~

`ConcurrentMetadataStore` bổ sung:

~~~java
String oldValue = concurrentStore.putIfAbsent(
    "orders:last-id", "102"); // null = tạo mới thành công.

boolean changed = concurrentStore.replace(
    "orders:last-id", "102", "110"); // true nếu oldValue khớp.
~~~

| API | Ngữ nghĩa |
|---|---|
| `get(k)` | Đọc giá trị của key hoặc null nếu không tồn tại |
| `put(k,v)` | Ghi đè không điều kiện |
| `remove(k)` | Xóa key và nhận giá trị cũ nếu có |
| `putIfAbsent(k,v)` | Atomic create-if-absent |
| `replace(k,expected,next)` | Compare-and-set; chỉ ghi khi hiện tại bằng expected |

**Không dùng `get` rồi `put` như một khóa phân tán.** Hai pods có thể cùng đọc 102, cùng chạy SELECT rồi ghi 110 mà không biết đã tranh chấp. `replace` giúp phát hiện lost update, nhưng nó vẫn không bảo đảm các event chưa bị gửi trùng sang hệ thống ngoài.

### 3.1. Những triển khai của MetadataStore

Spring Integration có `SimpleMetadataStore` trong bộ nhớ, `PropertiesPersistingMetadataStore` dựa trên file và các triển khai bền vững qua JDBC, Redis, MongoDB, ZooKeeper, v.v. `SimpleMetadataStore` **không** bảo toàn checkpoint qua restart process.

`JdbcMetadataStore` xuất hiện từ Spring Integration **5.0**, triển khai `ConcurrentMetadataStore` và có thể tham gia Spring JDBC transaction. Nó không phải database connection pool hay một hệ thống stream log; nó dùng `DataSource` của ứng dụng.

## 4. Giới hạn quan trọng: JdbcPollingChannelAdapter không tự dùng MetadataStore

Một số adapter File/FTP/SFTP/Feed có chức năng quản lý metadata/duplicate detection qua `MetadataStore`. Tuy nhiên, **`JdbcPollingChannelAdapter` không có API `setMetadataStore(...)` cho incremental SELECT tự động**.

JDBC inbound có các chức năng khác:

- `setSelectSqlParameterSource(...)` để cấp tham số `SELECT`.
- `setUpdateSql(...)` và `setUpdateSqlParameterSourceFactory(...)` để đánh dấu những rows đã đọc.
- `setRowMapper(...)` để chuyển `ResultSet` thành DTO.
- `setMaxRows(...)` để giới hạn số rows.

Điều này có nghĩa: ứng dụng **phải tự gắn watermark vào SELECT** bằng `SqlParameterSource` hoặc custom `MessageSource`, và **tự quyết định khi nào cập nhật checkpoint**.

~~~java
// SAI: không có các method này trong JdbcPollingChannelAdapter.
// jdbcSource.setMetadataStore(store);
// jdbcSource.enableAutomaticIncrementalCheckpoint();
~~~

Ngay cả khi khai báo bean tên `metadataStore`, JDBC inbound adapter cũng không tự thêm `WHERE id > :lastId` cho SQL của bạn.

## 5. Điều kiện để cursor ID mang ý nghĩa đúng

Mẫu `WHERE id > :lastId ORDER BY id` chỉ an toàn nếu đã kiểm tra:

1. ID là duy nhất, không null và có thứ tự có thể so sánh.
2. Những thay đổi nghiệp vụ mới xuất hiện ở phía **sau cursor**, không phải UPDATE row cũ.
3. Không có transaction **commit muộn** với ID nằm phía trước watermark mới, hoặc có overlap/reconciliation.
4. Checkpoint tăng **sau** khi những rows cần bảo vệ đã được ghi bền vững.
5. Một stream/partition không có nhiều workers tự cập nhật cùng key mà thiếu CAS và điều phối.
6. Không cần nhận biết DELETE/tombstone bằng phép SELECT từ bảng hiện tại; nếu cần, phải có change log/CDC.

**Lưu ý:** sequence/identity chỉ bảo đảm cơ chế cấp ID; không mặc nhiên bảo đảm các transactions **commit theo thứ tự ID**. Phần 17 sẽ phân tích trường hợp 106 commit trước 105.

## 6. Chuẩn bị Spring Boot, DataSource và schema

Ví dụ sử dụng Java 17+, Spring Boot, Spring JDBC, Spring Integration JDBC và H2 để thực hành. Dùng BOM của Spring Boot quản lý các phiên bản tương thích.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
spring:
  datasource:
    url: "jdbc:h2:mem:incremental_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

Giả sử một ứng dụng thực hành đặt DDL trong `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE source_event (
    id           BIGINT NOT NULL PRIMARY KEY,
    event_type   VARCHAR(80) NOT NULL,
    payload_json VARCHAR(2000) NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE event_outbox (
    event_id     VARCHAR(80) NOT NULL PRIMARY KEY,
    source_id    BIGINT NOT NULL UNIQUE,
    event_type   VARCHAR(80) NOT NULL,
    payload_json VARCHAR(2000) NOT NULL,
    published    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE INT_METADATA_STORE (
    METADATA_KEY   VARCHAR(255) NOT NULL,
    METADATA_VALUE VARCHAR(4000) NOT NULL,
    REGION         VARCHAR(100) NOT NULL,
    CONSTRAINT INT_METADATA_STORE_PK
        PRIMARY KEY (METADATA_KEY, REGION)
);

INSERT INTO source_event(id, event_type, payload_json)
VALUES (101, 'order.created', '{"orderId":"ORD-101"}'),
       (102, 'order.paid', '{"orderId":"ORD-102"}'),
       (103, 'order.shipped', '{"orderId":"ORD-103"}');
~~~

**`INT_METADATA_STORE` là bảng kỹ thuật** mà `JdbcMetadataStore` sử dụng. Module `spring-integration-jdbc` cung cấp schema scripts theo các DB vendors; H2 ở đây chỉ là ví dụ. Production nên áp dụng migrations bằng Flyway/Liquibase.

**H2 in-memory không bền qua process restart.** Muốn kiểm chứng metadata lưu qua restart thật, dùng DB server hoặc H2 file-backed; `DB_CLOSE_DELAY=-1` chỉ giữ H2 trong quá trình JVM còn chạy.

## 7. Cấu hình JdbcMetadataStore với region riêng

~~~java
package com.example.incremental;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.metadata.JdbcMetadataStore;
import org.springframework.integration.metadata.ConcurrentMetadataStore;

@Configuration
public class CheckpointStorageConfiguration {

    @Bean("incrementalCheckpointStore")
    public ConcurrentMetadataStore incrementalCheckpointStore(
            DataSource dataSource) {
        JdbcMetadataStore store = new JdbcMetadataStore(dataSource);
        store.setRegion("orders-incremental-v1");
        return store;
    }
}
~~~

`setRegion(...)` là namespace logic; mặc định region là `DEFAULT`. Dùng region riêng cho mỗi dòng công việc giúp giảm nguy cơ các pipelines sử dụng nhầm cùng key.

`JdbcMetadataStore#setLockHint(...)` cho phép tùy biến cú pháp locking khi thao tác update metadata; mặc định là `FOR UPDATE`, còn SQL Server dùng gợi ý khóa có cú pháp riêng. Chỉ cấu hình lock hint theo DB vendor thật, không copy nguyên mẫu từ một DB khác.

Từ **Spring Integration 6.2**, `JdbcMetadataStore` có `SmartLifecycle` và có thể kiểm tra bảng metadata tồn tại lúc startup. Nếu thiếu bảng theo table prefix, ứng dụng có thể fail khi khởi động; đây là tín hiệu cần sửa migration, không phải lý do tự động tắt `setCheckDatabaseOnStart(false)`.

## 8. Key, value, region và bootstrap cursor

Với một stream:

~~~java
static final String CURSOR_KEY = "source-event:last-id";
~~~

Một hệ thống nhiều tenants/partitions cần key tường minh, ví dụ:

~~~text
orders:partition-0:last-id
orders:partition-1:last-id
invoices:tenant-a:last-id
orders:source-event:cursor-v2
~~~

| Khi key chưa tồn tại | Ý nghĩa | Rủi ro |
|---|---|---|
| Cursor `0` | Đọc toàn bộ IDs dương từ đầu | Backlog lớn |
| Cursor theo snapshot đã đối soát | Bắt đầu từ mốc đã xác nhận | Sai mốc có thể bỏ dữ liệu |
| Cursor bằng `MAX(id)` hiện tại | **Cố ý bỏ qua lịch sử** | Mất backlog nếu không được phép |
| Cursor phục hồi từ backup | Tiếp tục trạng thái cũ | Có thể lệch với dữ liệu nguồn/outbox |

Ví dụ trong bài dùng `0L` khi key không tồn tại, **giả định ID > 0**. Không tự đổi checkpoint thành `MAX(id)` ở startup trừ khi có yêu cầu business cho phép bỏ qua dữ liệu lịch sử.

## 9. Compare-and-set checkpoint: phát hiện tranh chấp

~~~java
package com.example.incremental;

import org.springframework.integration.metadata.ConcurrentMetadataStore;

public final class IdCheckpoint {

    private final ConcurrentMetadataStore store;
    private final String key;

    public IdCheckpoint(
            ConcurrentMetadataStore store, String key) {
        this.store = store;
        this.key = key;
    }

    public long read() {
        String value = store.get(key);
        return value == null ? 0L : Long.parseLong(value);
    }

    public void advance(String expected, long nextId) {
        long previous = expected == null
            ? 0L : Long.parseLong(expected);

        if (nextId <= previous) {
            throw new IllegalArgumentException(
                "Checkpoint must increase");
        }

        String next = Long.toString(nextId);
        boolean success = expected == null
            ? store.putIfAbsent(key, next) == null
            : store.replace(key, expected, next);

        if (!success) {
            throw new IllegalStateException(
                "Checkpoint changed concurrently");
        }
    }
}
~~~

`expected` phải là **giá trị đã đọc trước khi SELECT**. Nếu đọc lại metadata ngay trước `replace` và chấp nhận giá trị mới mà không kiểm tra batch của mình, có nguy cơ xử lý dữ liệu cũ rồi đẩy cursor về trạng thái không nhất quán.

**CAS chỉ bảo vệ metadata key, không khóa source rows và không thu hồi được sự kiện đã gửi Kafka/HTTP.** Khi CAS thất bại, worker phải rollback công việc local trong transaction rồi SELECT lại theo cursor mới.

## 10. Xây một MessageSource đọc incremental từ MetadataStore

Để kiểm soát chính xác lúc đọc checkpoint, có thể tạo nguồn tùy chỉnh từ `AbstractMessageSource<List<SourceEvent>>`. Mỗi poll đọc cursor, truy vấn ID lớn hơn cursor, rồi CAS checkpoint **trong local transaction do poller mở**.

~~~java
package com.example.incremental;

public record SourceEvent(
    long id, String eventType, String payloadJson) {
}
~~~

~~~java
package com.example.incremental;

import java.util.List;
import org.springframework.integration.endpoint.AbstractMessageSource;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.jdbc.core.JdbcTemplate;

public final class IncrementalEventSource
        extends AbstractMessageSource<List<SourceEvent>> {

    private static final String KEY = "source-event:last-id";

    private final JdbcTemplate jdbc;
    private final ConcurrentMetadataStore checkpoint;

    public IncrementalEventSource(
            JdbcTemplate jdbc, ConcurrentMetadataStore checkpoint) {
        this.jdbc = jdbc;
        this.checkpoint = checkpoint;
    }

    @Override
    protected Object doReceive() {
        String expected = checkpoint.get(KEY);
        long lastId = expected == null
            ? 0L : Long.parseLong(expected);

        List<SourceEvent> rows = jdbc.query(
            "SELECT id, event_type, payload_json "
          + "FROM source_event "
          + "WHERE id > ? ORDER BY id LIMIT ?",
            (rs, index) -> new SourceEvent(
                rs.getLong("id"),
                rs.getString("event_type"),
                rs.getString("payload_json")),
            lastId, 50);

        if (rows.isEmpty()) {
            return null; // Không tạo message ở lượt này.
        }

        long next = rows.get(rows.size() - 1).id();
        String nextValue = Long.toString(next);

        boolean saved = expected == null
            ? checkpoint.putIfAbsent(KEY, nextValue) == null
            : checkpoint.replace(KEY, expected, nextValue);

        if (!saved) {
            throw new IllegalStateException(
                "Cursor race: another poller advanced it");
        }
        return rows;
    }

    @Override
    public String getComponentType() {
        return "jdbc:incremental-event-source";
    }
}
~~~

**Điều kiện áp dụng bắt buộc:** `doReceive()` cập nhật checkpoint **trước khi** downstream chạy. Vì vậy phải có transactional poller và downstream **đồng bộ, ghi việc bền vững vào cùng DataSource** trước COMMIT. Nếu source chạy autocommit rồi downstream thất bại, các rows vừa SELECT có thể mất mãi.

`AbstractMessageSource` đóng gói `List<SourceEvent>` thành `Message<List<SourceEvent>>`. Muốn mỗi row là một message, cần `Splitter` downstream. Câu `LIMIT ?` phù hợp H2/PostgreSQL; SQL Server/Oracle có cú pháp khác.

## 11. Ghi checkpoint cùng outbox trong một transaction

Một thiết kế an toàn hơn việc ghi cursor rồi gửi Kafka trực tiếp là:

1. Poller mở JDBC transaction.
2. Source đọc rows, CAS checkpoint trong transaction.
3. Handler **đồng bộ** ghi toàn bộ rows thành các outbox events trong cùng transaction.
4. COMMIT checkpoint và outbox cùng nhau.
5. Publisher riêng đọc outbox đã commit, gửi Kafka/JMS và đánh dấu đã publish theo cơ chế retry/deduplication.

~~~mermaid
sequenceDiagram
    participant P as Transactional poller
    participant S as IncrementalEventSource
    participant DB as Source + metadata + outbox DB
    participant W as OutboxWriter
    P->>DB: BEGIN
    P->>S: receive()
    S->>DB: Read checkpoint + SELECT id > lastId
    DB-->>S: Rows [101,102,103]
    S->>DB: CAS cursor -> 103 (chưa commit)
    S-->>W: Message<List<SourceEvent>> -> split
    W->>DB: INSERT outbox for 101,102,103
    alt Thành công
        P->>DB: COMMIT cursor + outbox
    else Lỗi handler/JDBC
        P->>DB: ROLLBACK cursor + outbox
    end
~~~

### 11.1. OutboxWriter

~~~java
package com.example.incremental;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class OutboxWriter {

    private final JdbcTemplate jdbc;

    public OutboxWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void stage(SourceEvent row) {
        String eventId = "source-event-" + row.id();
        jdbc.update(
            "INSERT INTO event_outbox "
          + "(event_id, source_id, event_type, payload_json) "
          + "VALUES (?, ?, ?, ?)",
            eventId, row.id(), row.eventType(), row.payloadJson());
    }
}
~~~

`event_id` và `source_id` được ràng buộc UNIQUE. Khi một event đã stage được phát lại, ứng dụng phải phân biệt **duplicate thực sự giống dữ liệu** và **conflict cùng ID nhưng payload khác**; không catch mọi duplicate-key rồi coi như thành công.

### 11.2. IntegrationFlow với transactional poller

~~~java
package com.example.incremental;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class IncrementalFlowConfiguration {

    @Bean
    public IncrementalEventSource incrementalEventSource(
            JdbcTemplate jdbc,
            @Qualifier("incrementalCheckpointStore")
            ConcurrentMetadataStore checkpoint) {
        return new IncrementalEventSource(jdbc, checkpoint);
    }

    @Bean
    public IntegrationFlow stageIncrementalEvents(
            IncrementalEventSource source,
            OutboxWriter writer,
            PlatformTransactionManager transactionManager) {
        return IntegrationFlow.from(source,
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .split()
            .handle(writer, "stage")
            .get();
    }
}
~~~

Trong flow, `.split()` và `.handle(writer, "stage")` là các chặng **đồng bộ** khi không chèn async boundary; transaction của poller có thể bao toàn bộ các JDBC operations qua cùng transaction manager và DataSource.

**Không chèn `ExecutorChannel`/`QueueChannel` trước outbox writer rồi vẫn cho rằng checkpoint và outbox sẽ commit cùng nhau.** Transaction thread-bound của poller không tự lan sang worker thread khác. Không dùng một `DataSource` cho checkpoint và một database khác cho outbox rồi kết luận local transaction đảm bảo atomic.

## 12. Từng cửa sổ crash và kết quả

| Thời điểm lỗi | Checkpoint | Outbox | Điều phải xảy ra |
|---|---|---|---|
| Trước SELECT | Chưa tăng | Chưa ghi | Poll lại như bình thường |
| Sau SELECT, trước CAS | Chưa tăng | Chưa ghi | Đọc lại được |
| Sau CAS nhưng chưa COMMIT | Rollback khi lỗi | Rollback | Không skip rows |
| Đang INSERT outbox hàng thứ hai | Rollback | Rollback toàn batch | Retry từ checkpoint cũ |
| Sau COMMIT của JDBC transaction | Đã tăng | Đã ghi bền | Publisher relay tiếp tục |
| Broker nhận nhưng publisher crash trước đánh dấu published | Không đổi | Event còn pending | Có thể publish lại, consumer phải idempotent |

Một **JDBC transaction cục bộ** không tạo transaction xuyên Kafka/JMS/HTTP. Nếu publisher gửi broker thành công rồi crash trước khi ghi `published=true`, event có thể bị gửi lại; đó là **at-least-once**, không phải “exactly-once delivery” tự động.

Với `DirectChannel`, lỗi đồng bộ có thể rollback poller transaction. Với `ExecutorChannel` hoặc một queue/poller khác, checkpoint có thể đã COMMIT trước khi việc thực sự được xử lý. Boolean `send() == true` không chứng minh downstream đã commit.

## 13. Sử dụng JDBC inbound adapter có sẵn với cursor động

Nếu muốn giữ `JdbcPollingChannelAdapter` của Spring Integration, ta có thể tự nối `MetadataStore` vào **`selectSqlParameterSource`**:

~~~sql
SELECT id, event_type, payload_json
FROM source_event
WHERE id > :lastId
ORDER BY id
LIMIT 50;
~~~

Quy tắc đúng:

1. `:lastId` được lấy từ checkpoint **trước mỗi SELECT**.
2. JDBC inbound adapter chạy query và trả `Message<List<SourceEvent>>`.
3. Một handler **do ứng dụng viết** ghi kết quả sang nơi bền vững và CAS checkpoint, trong cùng local transaction.
4. Với bài toán multi-instance, handler cần kiểm tra giá trị expected đã dùng khi SELECT và chịu được CAS conflict; không đơn giản đọc checkpoint mới nhất rồi ghi đè.

**Tuyệt đối không kết luận chỉ gọi `selectSqlParameterSource(...)` là checkpoint sẽ tự tăng.** JDBC inbound adapter không cài sẵn cơ chế này.

### 13.1. Tạo SqlParameterSource không cache từ MetadataStore

Một `SqlParameterSource` cho SELECT được dùng lại giữa các lượt poll. Nếu giá trị SpEL bị cache từ lần đầu, SQL vẫn dùng cursor cũ, dù MetadataStore đã thay đổi. `ExpressionEvaluatingSqlParameterSourceFactory.createParameterSourceNoCache(...)` giải quyết vấn đề.

~~~java
package com.example.incremental;

import java.sql.Types;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.ExpressionEvaluatingSqlParameterSourceFactory;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

@Configuration
public class SelectCursorParameterConfiguration {

    public record CursorReader(ConcurrentMetadataStore store) {
        public long lastId() {
            String value = store.get("source-event:last-id");
            return value == null ? 0L : Long.parseLong(value);
        }
    }

    @Bean("cursorReader")
    public CursorReader cursorReader(
            @Qualifier("incrementalCheckpointStore")
            ConcurrentMetadataStore checkpoints) {
        return new CursorReader(checkpoints);
    }

    @Bean("cursorExpressions")
    public ExpressionEvaluatingSqlParameterSourceFactory
            cursorExpressions() {
        var factory =
            new ExpressionEvaluatingSqlParameterSourceFactory();
        factory.setParameterExpressions(Map.of(
            "lastId", "@cursorReader.lastId()"));
        factory.setSqlParameterTypes(Map.of(
            "lastId", Types.BIGINT));
        return factory;
    }

    @Bean("cursorSelectParams")
    public SqlParameterSource cursorSelectParams(
            @Qualifier("cursorExpressions")
            ExpressionEvaluatingSqlParameterSourceFactory factory) {
        return factory.createParameterSourceNoCache("");
    }
}
~~~

Factory là bean do Spring quản lý để SpEL có bean resolver cho `@cursorReader`. `createParameterSourceNoCache("")` trả nguồn tham số dùng lại qua nhiều poll; mỗi lần cần `lastId` nó đọc giá trị hiện hành.

**Tác dụng phụ:** vì không cache, nếu cùng `:lastId` xuất hiện hai lần trong SQL, biểu thức có thể được gọi nhiều lần. Hãy tránh biểu thức tự tăng counter hoặc thay đổi dữ liệu. Với nhiều pods, CAS/transaction hoặc snapshot mốc cho từng poll vẫn cần thiết.

### 13.2. Java DSL 7.x: SELECT incremental bằng Jdbc.inboundAdapter

Từ Spring Integration **7.0**, JDBC Java DSL có `Jdbc.inboundAdapter(...)` và `JdbcInboundChannelAdapterSpec`:

~~~java
// Fragment: đây là phương án THAY THẾ cho custom source ở mục 10.
// dataSource, cursorSelectParams, transactionManager, batchHandler
// là các bean/biến do ứng dụng cung cấp.
return IntegrationFlow.from(
        Jdbc.inboundAdapter(dataSource,
                "SELECT id, event_type, payload_json "
              + "FROM source_event "
              + "WHERE id > :lastId "
              + "ORDER BY id LIMIT 50")
            .selectSqlParameterSource(cursorSelectParams)
            .rowMapper((rs, rowNum) -> new SourceEvent(
                rs.getLong("id"),
                rs.getString("event_type"),
                rs.getString("payload_json")))
            .maxRows(50),
        endpoint -> endpoint.poller(
            Pollers.fixedDelay(Duration.ofSeconds(5))
                .maxMessagesPerPoll(1)
                .transactional(transactionManager)))
    .handle(batchHandler, "stageBatch")
    .get();
~~~

`batchHandler.stageBatch(List<SourceEvent>)` **chưa được Spring Integration cung cấp sẵn**. Đó phải là handler của ứng dụng có nhiệm vụ:

- Ghi các rows đã đọc thành công việc bền vững, ví dụ outbox.
- CAS checkpoint dựa trên mốc của chính lượt query, **không làm watermark đi lùi**.
- Ném exception khi không có quyền cập nhật cursor, để rollback outbox cùng transaction.
- Không phát Kafka/JMS trực tiếp trước khi công việc có commit bền vững.

Nếu muốn tránh rủi ro query parameter bị thay đổi giữa lúc xử lý và lúc ghi checkpoint, có thể **tự thiết kế source giữ mốc expected** như ví dụ mục 10, hoặc truyền giá trị cursor đã dùng qua headers/DTO một cách tường minh. Mảnh DSL ở đây chỉ minh họa cách **đọc** checkpoint, không tự hoàn chỉnh toàn bộ thuật toán cạnh tranh.

## 14. Spring Integration 6.x và XML

Ở **Spring Integration 6.x**, `JdbcPollingChannelAdapter` có `setSelectSqlParameterSource(...)`, nhưng **không** có factory `Jdbc.inboundAdapter(...)` của JDBC Java DSL 7.x.

~~~java
package com.example.incremental;

import java.time.Duration;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class LegacyIncrementalConfiguration {

    @Bean
    public IntegrationFlow incrementalOnSix(
            DataSource dataSource,
            SqlParameterSource cursorSelectParams,
            PlatformTransactionManager transactionManager,
            BatchOutboxStageHandler batchHandler) {

        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource,
                "SELECT id, event_type, payload_json "
              + "FROM source_event WHERE id > :lastId "
              + "ORDER BY id LIMIT 50");
        source.setSelectSqlParameterSource(cursorSelectParams);
        source.setRowMapper((rs, rowNum) -> new SourceEvent(
            rs.getLong("id"),
            rs.getString("event_type"),
            rs.getString("payload_json")));
        source.setMaxRows(50);

        return IntegrationFlow.from(source,
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .handle(batchHandler, "stageBatch")
            .get();
    }
}
~~~

Ở đây `BatchOutboxStageHandler` là **kiểu ứng dụng phải tự định nghĩa**, có method `stageBatch(List<SourceEvent>)`; không phải class có sẵn của Spring Integration. Để chạy độc lập, cần bổ sung handler và bảo đảm checkpoint CAS, outbox và transaction như phần trước.

Một phần cấu hình tương tự bằng XML:

~~~xml
<!-- Fragment: namespace int và int-jdbc cần được khai báo. -->
<int:channel id="incrementalBatches"/>

<int-jdbc:inbound-channel-adapter
    id="incrementalJdbc"
    data-source="dataSource"
    channel="incrementalBatches"
    query="SELECT id, event_type, payload_json
           FROM source_event
           WHERE id > :lastId ORDER BY id"
    select-sql-parameter-source="cursorSelectParams"
    max-rows="50">
    <int:poller fixed-delay="5000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

XML **chưa** có service activator để ghi outbox và CAS checkpoint. Trong production phải thêm chặng đó hoặc chọn custom MessageSource. Không gắn trực tiếp `JdbcMetadataStore` vào thuộc tính `select-sql-parameter-source` vì loại tham số kỳ vọng là `SqlParameterSource`.

## 15. Khi nào được phép tăng checkpoint?

| Tình huống | Có nên lưu lastId? | Giải thích |
|---|---|---|
| Đã SELECT rows trong RAM | **Không** | Crash có thể mất toàn bộ payload |
| Đã transform thành DTO | **Không** | DTO vẫn chỉ nằm trong bộ nhớ |
| Đã gửi vào queue không bền | Thường **không** | Queue có thể mất khi restart |
| Đã ghi outbox trong **cùng DB transaction** | **Có** | Cursor và công việc cùng commit |
| Đã nhận Kafka producer ACK | Có thể, nhưng có crash window | Gửi trùng nếu chết trước checkpoint |
| Đã nhận HTTP 200 | Tùy hợp đồng remote | Response bị mất không nói remote thất bại |
| Consumer đã hoàn tất công việc và ACK | Có thể theo thiết kế end-to-end | Cần protocol/ACK có thể đối soát |

Ví dụ **mất dữ liệu**:

~~~text
SELECT 101..110
MetadataStore.put(lastId, "110") -> COMMIT
Ứng dụng chết trước khi gửi Kafka
Restart: WHERE id > 110
=> 101..110 không còn được đọc.
~~~

Ví dụ **at-least-once và idempotency**:

~~~text
SELECT 101..110
Đã ghi công việc bền vững / Kafka đã nhận
Chết trước checkpoint
Restart đọc lại 101..110
Consumer dùng stable eventId để dedupe
=> có thể gửi trùng, nhưng tránh mất công việc.
~~~

Đối với tác vụ quan trọng, **at-least-once delivery + idempotent effect** thường là đích thực tế hơn là một tuyên bố “exactly-once” chỉ dựa trên `lastId`.

## 16. Cửa sổ lỗi do late commit: ID không phải thứ tự commit

Một ví dụ dễ bị bỏ qua:

~~~text
10:00  Transaction A cấp ID=105, vẫn chưa COMMIT
10:01  Transaction B cấp ID=106 và COMMIT
10:02  Poller thấy 106, cập nhật cursor lên 106
10:03  Transaction A COMMIT ID=105
10:04  Poller chạy WHERE id > 106
       -> 105 bị bỏ sót dù đang tồn tại trong database.
~~~

CAS hoạt động đúng, checkpoint bền qua restart và transaction của poller vẫn **không chữa được lỗi này**. Lý do: thứ tự tạo ID không bắt buộc trùng thứ tự dữ liệu hiển thị sau COMMIT.

**Không kết luận “đã ORDER BY id thì không thể bỏ sót”.** `ORDER BY` chỉ sắp xếp những hàng **đã visible** trong snapshot của query.

Các lựa chọn:

1. Dùng CDC/transaction log/commit-ordered cursor nếu cần mọi thay đổi theo thứ tự commit.
2. Dùng overlap window cộng idempotency và reconciliation.
3. Dùng transactional outbox ở ngay transaction nguồn nếu có quyền thay đổi ứng dụng ghi.
4. Dùng atomic claim/locking nếu bảng nguồn là hàng đợi xử lý.
5. Chỉ dùng ID cursor khi hợp đồng nguồn **thực sự bảo đảm** thứ tự hiển thị.

## 17. Cursor ghép `(updated_at, id)` cho bảng có UPDATE

Nếu rows có thể cập nhật sau khi tạo, truy vấn `id > :lastId` không phát hiện cập nhật trên ID cũ. Một cách là cursor lexicographic theo **timestamp và ID**:

~~~sql
SELECT id, updated_at, status
FROM source_entity
WHERE updated_at > :lastUpdatedAt
   OR (updated_at = :lastUpdatedAt AND id > :lastId)
ORDER BY updated_at, id
LIMIT :batchSize;
~~~

Ví dụ có cùng timestamp:

| updated_at | id |
|---|---:|
| 2026-11-23 08:00:00 | 7 |
| 2026-11-23 08:00:00 | 8 |
| 2026-11-23 08:00:00 | 9 |

Nếu chỉ lưu timestamp sau khi query lấy hai rows, lần sau dùng `updated_at > 08:00:00` sẽ **bỏ ID 9**. Cặp `(timestamp,id)` cho phép tiếp tục từ (08:00:00, 8) đến (08:00:00, 9).

Lưu cặp cursor trong MetadataStore cần định dạng/phiên bản cụ thể:

~~~text
KEY   = source-entity:cursor:v2
VALUE = 2026-11-23T08:00:00.000000Z|8
~~~

Quy định timezone (UTC), precision SQL timestamp, escaping/parsing và version của key. **Timestamp cursor vẫn có late-commit hazard** nếu `updated_at` được gán trước COMMIT hoặc ứng dụng ghi timestamp lùi; tie-breaker chỉ xử lý nhiều rows cùng timestamp.

## 18. Overlap window và idempotency cho dữ liệu đến muộn

Một chiến lược giảm rủi ro là đọc lặp một khoảng gần mốc đã lưu:

~~~sql
-- Pseudo SQL, cách trừ thời gian thuộc DB/ứng dụng:
SELECT id, updated_at, status
FROM source_entity
WHERE updated_at >= :checkpointMinusOverlap
ORDER BY updated_at, id;
~~~

Khi đọc lại khoảng gần cursor, cần key ổn định theo **sự kiện/phiên bản**, không chỉ row ID nếu cùng row có nhiều lần UPDATE.

| Thành phần | Vai trò |
|---|---|
| Overlap | Cho phép nhìn thấy rows cập nhật/commit muộn trong một khoảng |
| Dedupe store | Tránh xử lý lại cùng event/version |
| Checkpoint | Biết tiến độ đã stage ở những vùng ổn định |
| Backfill/reconciliation | Phục hồi late events vượt ngoài overlap |
| CDC | Phương án thay thế khi không chấp nhận bỏ sót changes |

**Cảnh báo:** overlap hữu hạn không thể bảo đảm nhìn thấy mọi transaction trễ **không giới hạn**. Một watermark thời gian đơn thuần cũng không phát hiện DELETE của row đã biến mất khỏi bảng hiện hành. Nếu hợp đồng yêu cầu không mất một thay đổi nào, dùng CDC hoặc một event log có semantics phù hợp.

## 19. Nhiều instances: CAS không phải distributed work queue

Hai pods có thể cùng đọc cursor 100 và cùng SELECT 101..110. Một `replace("100","110")` thành công, cái còn lại thất bại.

~~~text
Pod A: get 100 -> SELECT 101..110 -> CAS 100->110 thành công
Pod B: get 100 -> SELECT 101..110 -> CAS 100->110 thất bại
~~~

Nếu cả hai dùng cùng JDBC transaction để ghi cursor và **outbox**, pod B có thể rollback toàn bộ DML khi CAS thất bại. Nhưng nếu pod B đã gửi HTTP/Kafka bên ngoài DB trước CAS, event đã gửi **không tự thu hồi**.

| Kiến trúc | Cách phối hợp |
|---|---|
| Single leader per stream | Distributed lock/leader lease |
| Partitioned stream | Cursor key riêng cho từng partition |
| Work queue tại DB | Atomic claim + lease + row ownership |
| Transactional outbox | Atomic staging và publisher riêng |
| CDC connector | Offset/checkpoint theo commit log |

Spring Integration có các giải pháp JDBC lock registry riêng như `JdbcLockRegistry`/`DefaultLockRepository`. Metadata CAS trên một key **không đồng nghĩa đã sở hữu một distributed lock**, và không bảo đảm nguồn dữ liệu được partition đúng.

## 20. MetadataStore và Idempotent Receiver

**Checkpoint** mô tả vị trí lớn nhất đã xử lý theo quy tắc; **processed-event store** ghi nhận từng event đã hoàn tất.

~~~text
Checkpoint:
  source:last-id -> 110

Processed IDs:
  source:evt-101 -> DONE
  source:evt-103 -> DONE
  source:evt-110 -> DONE
~~~

Spring Integration có **Idempotent Receiver** pattern hỗ trợ các metadata stores hoặc `MetadataStoreSelector`. Tuy nhiên thứ tự ghi trạng thái quyết định độ tin cậy:

- Đánh dấu xử lý **trước** side effect có thể gây mất event nếu crash.
- Đánh dấu **sau** side effect nhưng không cùng transaction có thể gây xử lý trùng sau crash.
- Với một database, có thể ghi processed ID và business changes trong **cùng local transaction**, kết hợp unique constraint.
- Khi cùng event ID đi kèm payload khác nhau, cần phát hiện **conflict**, không coi là duplicate vô hại.

Nếu lưu processed key với TTL, phải bảo đảm TTL đủ lâu cho khoảng redelivery/replay; xóa quá sớm có thể làm event cũ gây tác dụng trùng.

## 21. Quản lý bootstrap, reset và backfill

| Thao tác vận hành | Hệ quả |
|---|---|
| Xóa checkpoint | Có thể đọc lại từ đầu, tạo backlog rất lớn |
| Đưa checkpoint lùi | Replay; cần dedupe và side-effect idempotency |
| Đưa checkpoint tiến | Bỏ qua rows cũ; nguy cơ mất dữ liệu |
| Đổi `REGION` | Flow có thể không nhìn thấy cursor cũ |
| Đổi định dạng `lastId` thành timestamp | Cần key/format version mới |
| Restore backup cũ | Source/outbox/metadata có thể không đồng bộ |

Runbook nên gồm: dừng hoặc khóa pollers; snapshot metadata và outbox; xác định cursor mục tiêu; xác nhận business impact; chỉ cập nhật qua thao tác được kiểm soát; chạy một instance để kiểm tra; sau đó mới tăng concurrency.

**Không mở endpoint HTTP cho phép người gọi tự đặt `lastId` hoặc tên metadata region** nếu không có phân quyền và audit nghiêm ngặt.

## 22. Xử lý lỗi, retry và checkpoint consistency

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Restart từ đầu | `SimpleMetadataStore` RAM/H2 in-memory | JDBC/Redis persistent store thực |
| Cùng rows xuất hiện liên tục | Select parameter cache hoặc rollback | `createParameterSourceNoCache` và kiểm tra transaction |
| Cursor tăng nhưng outbox rỗng | Commit checkpoint trước durable work | Đặt cùng DB transaction |
| `replace` trả false | Worker khác vừa cập nhật key | Rollback/retry toàn poll, không dùng list cũ |
| Cursor bị parse lỗi | Giá trị MetadataStore sai format | Dừng/cảnh báo, không reset 0 âm thầm |
| Không thấy row ID 105 | Late commit sau watermark 106 | Overlap/CDC/backfill |
| DuplicateKey ở outbox | Event đã stage hoặc cùng ID khác payload | Phân biệt duplicate và conflict |
| Bảng metadata không tồn tại | Chưa migration hoặc sai table prefix | Chạy script theo vendor |
| Lỗi `FOR UPDATE` | Lock hint sai DB dialect | Cấu hình `setLockHint` đúng vendor |
| Pool cạn/SQL timeout | Quá nhiều polls, query lâu, locks | Limit batch, tối ưu SQL, bounded concurrency |

Với deadlock/network transient, retry **toàn transactional unit** sau rollback, có backoff/jitter và giới hạn số lần. Với lỗi schema, định dạng cursor hoặc SQL sai, retry vô hạn chỉ gây tải. Khi mất kết nối sát thời điểm COMMIT, outcome có thể không chắc chắn, nên đối soát metadata/outbox và dựa vào stable event ID.

## 23. Hiệu năng và bảo mật

Một poll có thể đọc checkpoint, chạy SELECT, CAS metadata và INSERT nhiều outbox rows. Cần theo dõi:

1. Số lượt poll, tỉ lệ poll rỗng, rows/poll và latency.
2. Last checkpoint, max visible ID và độ trễ theo thời gian.
3. CAS conflicts, transaction rollback, duplicate/replay counts.
4. Outbox pending, oldest unpublished event age, publisher retries.
5. Hikari pool active/idle/pending, connection timeouts, DB locks/deadlocks.
6. Late commits/reconciliation findings và source IDs bị backfill.

**Không tăng pool size hoặc tần suất poll vô hạn** để giải quyết query thiếu index. SQL `WHERE id > :lastId ORDER BY id LIMIT :n` nên có index phù hợp; đo explain plan với database production.

`maxRows` ở JDBC adapter giới hạn **rows mỗi query**; `maxMessagesPerPoll` giới hạn **số lần receive() mỗi trigger**. Một `Message<List<SourceEvent>>` có thể chứa 50 rows và splitter tạo 50 messages mà chỉ có một lần SELECT.

JDBC là **blocking I/O**. Khi dùng WebFlux, không gọi JDBC trên Reactor Netty event loop. Dùng poller/worker thread hoặc lựa chọn database reactive phù hợp; việc chuyển thread không biến JDBC thành R2DBC.

Về bảo mật, chỉ cấp DB account quyền đúng bảng metadata/source/outbox; không lưu PII/token vào metadata value; không log toàn bộ `payload_json`; tránh dùng event ID làm metric tag có cardinality quá cao; quản lý TLS/credentials qua secret manager.

## 24. Unit test CAS và kiểm tra rollback

### 24.1. Kiểm tra CAS bằng metadata store

~~~java
// Mảnh thử nghiệm, checkpointStore được inject từ Spring context.
String key = "test:cursor:cas";
checkpointStore.remove(key);

assertNull(checkpointStore.putIfAbsent(key, "100"));
assertEquals("100", checkpointStore.get(key));
assertTrue(checkpointStore.replace(key, "100", "105"));
assertFalse(checkpointStore.replace(key, "100", "104"));
assertEquals("105", checkpointStore.get(key));
~~~

Đoạn trên cần JUnit assertions imports và một `ConcurrentMetadataStore` bean đã được cấu hình. Chỉ dùng test keys, không xóa checkpoint đang được flow production sử dụng.

### 24.2. Test transaction rollback

~~~java
package com.example.incremental;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class MetadataRollbackTest {

    @Autowired
    @Qualifier("incrementalCheckpointStore")
    ConcurrentMetadataStore store;

    @Autowired
    PlatformTransactionManager manager;

    @Test
    void rollbackDoesNotSaveCheckpoint() {
        String key = "test:rollback:checkpoint";
        store.remove(key);

        TransactionTemplate tx = new TransactionTemplate(manager);

        assertThrows(IllegalStateException.class,
            () -> tx.executeWithoutResult(status -> {
                assertNull(store.putIfAbsent(key, "105"));
                throw new IllegalStateException("simulated failure");
            }));

        assertNull(store.get(key));
    }
}
~~~

Test giả định `JdbcMetadataStore` và `PlatformTransactionManager` dùng **cùng DataSource**, bảng metadata đã tồn tại và Spring container quản lý đúng lifecycle. Nó chỉ chứng minh rollback metadata, **chưa** chứng minh outbox và checkpoint commit cùng nhau.

### 24.3. Integration test end-to-end

Với schema ở mục 6, kiểm tra:

1. Key checkpoint chưa có; source 101,102,103 đã được chèn.
2. Chạy một poll trong transaction; outbox có ba rows và checkpoint bằng `"103"` sau commit.
3. Chạy poll tiếp; outbox không có thêm rows.
4. Chèn ID 104, poll; checkpoint trở thành `"104"`.
5. Làm `OutboxWriter` ném exception tại row thứ hai; xác minh **cả checkpoint và outbox rollback**.
6. Kiểm tra checkpoint vẫn lưu qua restart app với database bền vững, không chỉ H2 in-memory.
7. Gắn một consumer publisher giả lập; thử crash sau broker ACK trước khi đánh dấu outbox published.

Khi test custom source, không bật thêm scheduler nền cùng đọc source table; nếu không, test sẽ có race khó tái hiện.

## 25. Test concurrency, late commits và recovery

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Hai pods cùng cursor 100 | Một CAS thành công, bên còn lại rollback |
| CAS xong nhưng stage outbox lỗi | Checkpoint không được commit |
| Broker nhận rồi publisher crash | Outbox còn pending; replay có idempotency |
| ID 106 commit trước ID 105 | Cursor ID-only có thể bỏ 105 |
| Timestamp giống nhau qua hai batches | Cặp `(updated_at,id)` không bỏ row đồng thời |
| UPDATE row cũ với ID nhỏ hơn cursor | Cần updatedAt/change log hoặc CDC |
| Late event vượt overlap | Reconciliation phát hiện, không tuyên bố guaranteed |
| Metadata schema thiếu | Startup failure/migration error rõ |
| Hai regions cùng key | Metadata tách biệt đúng thiết kế |
| Cùng region nhưng key collision | Phát hiện hai flows giẫm checkpoint |
| Database outage giữa COMMIT | Retry/đối soát không nhân đôi tác dụng |

H2 thích hợp test cơ bản; để kiểm chứng locking, metadata CAS giữa nhiều JVMs và transaction isolation, dùng **Testcontainers hoặc database production-compatible** (PostgreSQL, SQL Server, Oracle, MySQL tùy ứng dụng).

## 26. Ví dụ ba lượt poll và khả năng rollback

Giả sử có 123 source events, ID từ 1 đến 123, batch size 50 và **không có late commits**:

~~~text
Poll 1: IDs   1..50  -> outbox 50 -> checkpoint 50
Poll 2: IDs  51..100 -> outbox 50 -> checkpoint 100
Poll 3: IDs 101..123 -> outbox 23 -> checkpoint 123
Poll 4: không có row  -> checkpoint giữ nguyên 123
~~~

Nếu poll thứ hai lỗi lúc ghi outbox thứ 10 và transaction rollback, checkpoint vẫn phải là 50; lần chạy kế tiếp đọc lại `51..100`. Nếu transaction commit được cursor 100 nhưng outbox chỉ có 60 rows, cấu hình **không đạt** hợp đồng atomic staging và có nguy cơ mất công việc.

## 27. Các hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “JdbcMetadataStore sẽ tự làm JDBC inbound incremental” | JDBC source phải tự dùng checkpoint trong SELECT |
| “MetadataStore là nơi lưu toàn bộ messages” | Chỉ là key/value, khác JdbcMessageStore |
| “SimpleMetadataStore lưu qua restart” | In-memory, không bền qua process restart |
| “`put` tương đương CAS” | Không; dùng `replace` hoặc `putIfAbsent` |
| “CAS chống duplicate publish tuyệt đối” | Không thu hồi side effect ngoài DB |
| “ID auto-increment nghĩa commit theo ID” | Transactions có thể commit đảo thứ tự |
| “ORDER BY id tránh mọi late commit” | Chỉ sắp rows đang visible |
| “Checkpoint là ID SELECT lớn nhất” | Chỉ nên tăng sau durable processing boundary |
| “No-cache SpEL tự giải quyết multi-instance” | Vẫn cần lock/CAS/transaction |
| “MaxRows(50) tạo 50 SQL polls” | Một source.receive có thể trả list 50 rows |
| “Checkpoint commit đồng thời với Kafka vì @Transactional” | JDBC transaction không bao Kafka mặc định |
| “Timestamp luôn đủ để không bỏ row” | Cần tie-breaker; vẫn có late commit |
| “Overlap 5 phút chắc chắn không mất event” | Không nếu có event trễ quá 5 phút |
| “Xóa checkpoint là fix an toàn” | Có thể replay vô hạn hoặc tạo backlog lớn |
| “JDBC trong WebFlux là non-blocking” | JDBC vẫn là blocking I/O |

## 28. Bài thực hành

1. Dựng schema `source_event`, `event_outbox` và `INT_METADATA_STORE` với H2.
2. Khai báo bean `JdbcMetadataStore` cùng `setRegion(...)`; đọc các rows metadata trực tiếp bằng SQL.
3. Thực hành `get`, `putIfAbsent`, `replace`; kiểm tra failed CAS không ghi đè.
4. Dùng `SimpleMetadataStore` và đối chiếu hành vi sau restart với store bền vững.
5. Tạo custom `IncrementalEventSource`, chạy SELECT theo `lastId` và trả một `Message<List<SourceEvent>>`.
6. Thêm splitter, `OutboxWriter` và transactional poller; quan sát cursor và outbox COMMIT cùng nhau.
7. Cố tình lỗi tại row thứ hai; kiểm tra transaction rollback và retry từ cursor cũ.
8. Chèn `ExecutorChannel` trước outbox writer để thấy vì sao checkpoint commit có thể xảy ra trước khi stage.
9. Tạo `ExpressionEvaluatingSqlParameterSourceFactory` cho `:lastId` với `createParameterSourceNoCache("")`.
10. Cấu hình JDBC inbound chuẩn Spring Integration 7.x bằng `Jdbc.inboundAdapter(...)` và handler cập nhật cursor.
11. Chuyển ví dụ sang 6.x bằng `JdbcPollingChannelAdapter`/XML, đối chiếu API và imports.
12. Chạy hai workers cùng metadata region/key, phân tích CAS conflict và transactional rollback.
13. Đổi region/key theo partition để cho các workers đọc các partitions riêng.
14. Dùng transaction nguồn có ID 105 commit sau 106; chứng minh cursor ID-only bỏ sót 105.
15. Viết cursor `(updated_at,id)`, kiểm tra cùng timestamp across batches.
16. Tạo overlap window, idempotent processed ID store và reconciliation cho late updates.
17. Dùng outbox publisher gửi Kafka/JMS, mô phỏng crash sau broker ACK nhưng trước `published=true`.
18. Dùng Testcontainers để kiểm tra concurrent metadata updates với DB vendor thật.
19. Xây metrics: lastId, cursor lag, rows/poll, CAS failures, outbox pending, late commits.
20. Viết runbook reset checkpoint có snapshot, replay, dedupe, xác nhận mốc mục tiêu.
21. Đặt thử giá trị sai format vào metadata; dừng/alert thay vì reset 0 âm thầm.
22. So sánh kiến trúc watermark, atomic claim, transactional outbox và CDC cho một hệ thống yêu cầu không mất events.

**Tình huống thiết kế:** hai pods cùng poll một bảng append-only có một triệu bản ghi. Source tạo ID 105 nhưng commit sau ID 106; Pod A đã tăng checkpoint lên 106. Outbox publisher vừa gửi Kafka xong thì chết trước khi đánh dấu `published`. Hãy đề xuất **CDC/commit-order cursor hoặc overlap+reconciliation**, metadata CAS/ownership, atomic outbox staging, stable event ID, ACK/retry và các tests cần có để không bỏ sót công việc và giảm duplicate side effects.

## 29. Tài liệu tham khảo

- [Spring Integration — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): key/value, persistent stores, ConcurrentMetadataStore và Idempotent Receiver.
- [Spring Integration — JDBC Metadata Store](https://docs.spring.io/spring-integration/reference/jdbc/metadata-store.html): JdbcMetadataStore, database schema, region, locking và transaction.
- [Spring Integration API — JdbcMetadataStore](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/jdbc/metadata/JdbcMetadataStore.html): `get`, `putIfAbsent`, `replace`, `setRegion`, `setLockHint`.
- [Spring Integration — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): polling SELECT/UPDATE, selectSqlParameterSource, maxRows và poller transactions.
- [Spring Integration API — JdbcPollingChannelAdapter 6.x](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): những setter có thật của JDBC source.
- [Spring Integration — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): factory `Jdbc.inboundAdapter` từ 7.0.
- [Spring Integration API — AbstractMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/AbstractMessageSource.html): contract `doReceive()` và `receive()`.
- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): poller transaction, DirectChannel và rollback.
- [Spring Framework — JDBC and Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `PlatformTransactionManager` và `TransactionTemplate`.
- [Spring Integration — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html): khác biệt giữa metadata checkpoint và message persistence.

> **Ghi nhớ:** `MetadataStore` lưu checkpoint cho incremental query; `JdbcMetadataStore` giúp lưu bền vững và hỗ trợ CAS. Nhưng **JDBC inbound adapter không tự dùng checkpoint và không tự tăng watermark**: ứng dụng phải nối cursor vào SQL và chỉ cập nhật mốc sau công việc đã được lưu bền vững. Với nhiều workers, cần CAS/ownership; với nguồn có late commits cần overlap/CDC/change log; khi gửi Kafka/JMS/HTTP cần outbox, retry và idempotency. Một cursor tăng đều **không đồng nghĩa** không mất sự kiện.

