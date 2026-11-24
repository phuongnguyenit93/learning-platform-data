# Debezium inbound channel adapter trong Spring Integration

## 1. Bài toán: nhận thay đổi database mà không polling SELECT liên tục

Một ứng dụng có bảng `orders` trong PostgreSQL. Khi có `INSERT`, `UPDATE` hoặc `DELETE`, hệ thống cần cập nhật cache, search index, bảng read model hoặc phát sự kiện sang Kafka/JMS/AMQP. Cách đơn giản là viết một JDBC inbound adapter liên tục chạy `SELECT ... WHERE updated_at > :cursor`. Nhưng cách này có nhiều hạn chế: phải chọn chu kỳ poll, xử lý clock skew/timestamp trùng, UPDATE ở hàng cũ, DELETE không còn thấy được và tranh chấp khi nhiều instances.

**Change Data Capture (CDC)** giải quyết bài toán theo hướng khác: đọc luồng thay đổi bền vững của database (ví dụ PostgreSQL logical decoding/WAL, MySQL binlog), thay vì tìm row thay đổi bằng câu SELECT của ứng dụng. **Debezium** cung cấp các connector CDC; Spring Integration có **Debezium inbound channel adapter** để đưa các change events đó vào `MessageChannel`.

~~~mermaid
flowchart LR
    W["Ứng dụng ghi database"] --> DB[("PostgreSQL tables")]
    DB --> LOG["WAL / logical replication"]
    LOG --> CON["Debezium PostgreSQL connector"]
    CON --> ENG["Debezium Engine"]
    ENG --> SI["DebeziumMessageProducer"]
    SI --> CH["MessageChannel"]
    CH --> FLOW["Filter / Transform / Route"]
    FLOW --> SINK["Cache / Outbox / Kafka / JMS"]
~~~

Đây là bài học thuộc chương **Adapter Debezium** của module **SPRING_INTEGRATION_ADAPTERS**: kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành qua file, SFTP, HTTP, JMS, AMQP, Kafka và database; chú trọng hợp đồng message, lỗi và vòng đời kết nối.

**Mục tiêu:** nắm rõ vai trò Debezium Engine và `DebeziumMessageProducer`, cấu hình Java DSL hoặc Java beans, đọc và phân loại events, quản lý snapshot/offset/tombstone, thiết kế khả năng khôi phục và đo vận hành. Bài tập trung vào **inbound CDC**; việc ghi Kafka/JMS/HTTP là downstream flow riêng.

## 2. CDC khác JDBC inbound polling và domain event thế nào?

| Cơ chế | Nguồn sự kiện | Ưu điểm | Giới hạn |
|---|---|---|---|
| JDBC inbound polling | SQL `SELECT` theo thời gian | Dễ thiết lập, không cần quyền replication | Có thể quét lặp/skip late commits, DELETE khó phát hiện |
| Debezium CDC | Database log + snapshot ban đầu | Nhìn thấy INSERT/UPDATE/DELETE ở mức row, ít polling ứng dụng | Cần replication/log retention/offset/DDL handling |
| Application domain event | Business service chủ động phát | Ngữ nghĩa nghiệp vụ phong phú | Có thể thiếu event nếu DB commit rồi publish lỗi |
| Transactional outbox + Debezium | Outbox row ghi cùng business transaction, Debezium đọc log | Business event bền và có thể relay | Vẫn phải retry/dedupe downstream |
| Kafka Connect Debezium | Connector chạy ở Connect cluster | Quản trị connector/offset/scale theo Connect | Phải vận hành hạ tầng Connect/Kafka |
| Debezium Server | Runtime CDC riêng, nhiều sink integrations | Tách vòng đời CDC khỏi service | Hạ tầng deploy riêng |

`Debezium inbound channel adapter` của Spring Integration dùng **Debezium Engine nhúng trong ứng dụng Java**. Nó không đồng nghĩa bạn đã triển khai Kafka Connect cluster, cũng không tự tạo một Kafka topic. Nó chuyển các thay đổi DB thành **Spring Messages** cho flow tiếp theo xử lý.

**CDC row event ≠ business command:** `UPDATE orders SET status='PAID'` tạo change event kỹ thuật, chưa chắc đã nói rõ tại sao đơn hàng được thanh toán. Khi cần sự kiện cấp nghiệp vụ như `OrderPaid`, hãy cân nhắc outbox để tách contract business khỏi mọi thay đổi cột trong bảng nguồn.

## 3. Module, phiên bản và API thật

Spring Integration bổ sung Debezium inbound channel adapter từ **Spring Integration 6.2**. Các lớp chính:

| Lớp/API | Vai trò |
|---|---|
| `org.springframework.integration.debezium.inbound.DebeziumMessageProducer` | Message producer/endpoint dùng Debezium Engine |
| `org.springframework.integration.debezium.dsl.Debezium` | Factory Java DSL với `inboundChannelAdapter(...)` |
| `org.springframework.integration.debezium.dsl.DebeziumMessageProducerSpec` | Builder cấu hình adapter trong `IntegrationFlow` |
| `org.springframework.integration.debezium.support.DebeziumHeaders` | Tên các message headers như `KEY`, `DESTINATION` |
| `io.debezium.engine.DebeziumEngine` | Engine đọc connector và phát `ChangeEvent` |
| `io.debezium.engine.ChangeEvent<K,V>` | Event chứa key/value đã serialize |
| `io.debezium.connector.postgresql.PostgresConnector` | Connector nguồn PostgreSQL |

Không nhầm với JDBC Java DSL `Jdbc.inboundAdapter(...)` được giới thiệu về sau: **Debezium Java DSL có từ 6.2**. Các ví dụ này dành cho Spring Integration 6.2+ (bao gồm các nhánh 6.4, 6.5, 7.x) với **Debezium version tương thích**; phiên bản thực tế cần theo Spring Boot BOM và dependency resolution.

### 3.1. Thành phần phải có trên classpath

~~~groovy
// Gradle: dùng BOM của Spring Boot để chọn Spring Integration
// version tương thích. Debezium connector version cần align riêng.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-debezium'
    implementation 'org.springframework.boot:spring-boot-starter-json'

    runtimeOnly 'io.debezium:debezium-connector-postgres:COMPATIBLE_VERSION'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    // Nếu dùng Testcontainers 2.x cho integration tests ở mục 30:
    testImplementation 'org.testcontainers:testcontainers-postgresql'
    testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
}
~~~

`COMPATIBLE_VERSION` là **ký hiệu yêu cầu thay thế bằng phiên bản Debezium connector tương thích** với Spring Integration/BOM đang dùng, không phải một tọa độ artifact để chạy nguyên văn. Có thể dùng platform/BOM phù hợp theo tập dependencies của ứng dụng. Tránh tự ghép ngẫu nhiên Debezium Engine, connector, Kafka Connect API, Jackson và Spring Integration từ nhiều major versions.

**Một điểm khác:** muốn đọc PostgreSQL phải có `debezium-connector-postgres`, không chỉ `spring-integration-debezium`. Với MySQL phải thêm connector MySQL tương ứng; tên class và cấu hình connector sẽ thay đổi theo DB.

## 4. Kiến trúc Engine → Adapter → Message

Luồng thực thi:

1. PostgreSQL ghi row changes vào WAL khi transaction commit.
2. Logical decoding với replication slot/publication cho phép connector đọc thay đổi.
3. Debezium Engine nhận các `ChangeEvent` cùng metadata nguồn.
4. `DebeziumMessageProducer` chuyển events thành Spring messages.
5. Spring Integration gửi messages vào output channel.
6. Handler downstream parse, transform, route, persist/publish theo hợp đồng của ứng dụng.

~~~mermaid
sequenceDiagram
    participant App as Business app
    participant DB as PostgreSQL
    participant Rep as Replication slot
    participant Engine as Debezium Engine
    participant Adapter as Spring Integration adapter
    participant Handler as Downstream handler
    App->>DB: BEGIN; INSERT / UPDATE / DELETE; COMMIT
    DB->>Rep: WAL records visible for logical decoding
    Engine->>Rep: Read changes from source offset
    Rep-->>Engine: ChangeEvent
    Engine->>Adapter: Callback event/batch
    Adapter->>Handler: Message via MessageChannel
    Handler-->>Adapter: Return / exception (policy-dependent)
    Engine->>Engine: Offset bookkeeping / periodic flush
~~~

**Debezium là message-driven từ Engine**, không phải Spring `SourcePollingChannelAdapter`. Bạn **không cần đặt `Pollers.fixedDelay(...)`** để Engine “đi đọc DB”; connector đã có vòng đời streaming riêng. Spring `MessageChannel` vẫn là phần liên kết logic CDC với downstream adapters.

## 5. Chuẩn bị PostgreSQL: dữ liệu và logical replication

Tạo bảng mẫu trong database thực hành:

~~~sql
CREATE TABLE public.orders (
    id          BIGINT PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    status      VARCHAR(24) NOT NULL,
    total_cents BIGINT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO public.orders(id, customer_id, status, total_cents)
VALUES (101, 'C-001', 'CREATED', 125000),
       (102, 'C-002', 'CREATED', 89000);
~~~

PostgreSQL phải cấu hình logical replication đúng môi trường. Ví dụ phía DBA:

~~~conf
# postgresql.conf (minh họa, cần quyền admin và restart nếu DB yêu cầu)
wal_level = logical
max_replication_slots = 5
max_wal_senders = 5
~~~

DBA tạo user có quyền replication và đọc đúng bảng; chỉ minh họa cấu trúc quyền:

~~~sql
-- Ví dụ cho môi trường lab; password thực lấy từ secret manager.
CREATE ROLE cdc_reader WITH LOGIN REPLICATION PASSWORD 'REPLACE_ME';

GRANT CONNECT ON DATABASE appdb TO cdc_reader;
GRANT USAGE ON SCHEMA public TO cdc_reader;
GRANT SELECT ON TABLE public.orders TO cdc_reader;

-- DBA/owner tạo publication trước để không yêu cầu connector tự mở rộng quyền.
CREATE PUBLICATION orders_publication FOR TABLE public.orders;
~~~

**Lưu ý vận hành:**
- Thao tác với `postgresql.conf`, role replication và publication đòi hỏi quyền DBA/chính sách cloud provider cụ thể.
- Cấp quyền tối thiểu; không dùng tài khoản superuser cho service nếu không cần.
- `publication.autocreate.mode=disabled` (hoặc cơ chế tương đương theo phiên bản) khi publication được DBA tạo sẵn.
- Replication slot/offset phải có kế hoạch retention, backup, failover; slot không được consume có thể giữ WAL và làm đầy đĩa.
- Những thay đổi schema hoặc trường khóa chính ảnh hưởng event key và consumer contract; cần versioning.

**Chú ý:** tạo publication **khác** với tạo replication slot. Connector thường có thể tạo/quản lý slot khi khởi động nếu có quyền; trong production, DBA cần quyết định ownership và life cycle, tránh tạo trùng slot theo các pods.

## 6. Các thuộc tính connector PostgreSQL quan trọng

| Property | Ví dụ | Vai trò |
|---|---|---|
| `name` | `spring-orders-cdc` | Tên logic của engine/connector |
| `connector.class` | `io.debezium.connector.postgresql.PostgresConnector` | Đúng Debezium connector |
| `database.hostname` | `db.internal` | Địa chỉ PostgreSQL |
| `database.port` | `5432` | Port |
| `database.user` / `database.password` | Từ secrets | Credential replication |
| `database.dbname` | `appdb` | Database nguồn |
| `plugin.name` | `pgoutput` | Logical decoding plugin |
| `slot.name` | `spring_orders_slot` | PostgreSQL replication slot |
| `publication.name` | `orders_publication` | Publication chứa tables quan sát |
| `publication.autocreate.mode` | `disabled` | Không tự tạo publication khi đã có |
| `table.include.list` | `public.orders` | Chỉ đọc những bảng được cho phép |
| `topic.prefix` | `orders_source` | Namespace event destination của connector |
| `snapshot.mode` | `initial` | Chụp snapshot lần đầu rồi stream |
| `offset.storage` | `org.apache.kafka.connect.storage.FileOffsetBackingStore` | Triển khai lưu offset |
| `offset.storage.file.filename` | `/var/lib/app/cdc/orders-offset.dat` | Đường dẫn offsets bền |
| `offset.flush.interval.ms` | `10000` | Chu kỳ thử flush offset |

**`topic.prefix` trong Embedded Engine không có nghĩa adapter tự publish lên Kafka.** Nó là tên logic dùng để tạo destination/topic field của change events. Muốn gửi Kafka phải có downstream Kafka outbound adapter hoặc deploy connector qua Kafka Connect.

`offset.storage.file.filename` chỉ hợp cho môi trường có filesystem **bền và được dành riêng cho engine**. Một container có ephemeral disk sẽ mất file khi được tạo lại; nhiều pods dùng chung một file offset mà không có điều phối cũng không phải thiết kế HA an toàn.

## 7. Cấu hình ứng dụng bằng Spring Boot properties

Ví dụ `application.yml` của ứng dụng thực hành:

~~~yaml
cdc:
  postgres:
    hostname: "localhost"
    port: 5432
    database: "appdb"
    username: "${CDC_DB_USER}"
    password: "${CDC_DB_PASSWORD}"
  slot: "spring_orders_slot"
  publication: "orders_publication"
  offset-file: "${CDC_OFFSET_FILE}"
~~~

Hai biến `CDC_DB_USER`/`CDC_DB_PASSWORD` phải được cấp ngoài Git, ví dụ secret manager. `CDC_OFFSET_FILE` phải trỏ tới volume có quyền ghi và tồn tại qua restart nếu muốn resume. Với local test có thể dùng thư mục riêng như `./runtime/orders-offset.dat`, nhưng nên tạo thư mục trước khi chạy.

**Không copy ví dụ này làm cấu hình production hoàn chỉnh**: còn cần DB privileges, WAL settings, slot cleanup, TLS/certificates, monitor lag, timeout, shutdown và retry policy.

## 8. Java DSL: một Spring IntegrationFlow dùng Debezium inbound adapter

Factory `Debezium.inboundChannelAdapter(Properties)` dùng native Debezium configuration với JSON serialization phù hợp, không bắt bạn tự xây `DebeziumEngine.Builder`.

~~~java
package com.example.cdc;

import java.util.Properties;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.debezium.dsl.Debezium;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrdersCdcFlow {

    @Bean
    public IntegrationFlow ordersDebeziumInbound(
            @Value("${cdc.postgres.hostname}") String host,
            @Value("${cdc.postgres.port}") int port,
            @Value("${cdc.postgres.database}") String database,
            @Value("${cdc.postgres.username}") String username,
            @Value("${cdc.postgres.password}") String password,
            @Value("${cdc.slot}") String slotName,
            @Value("${cdc.publication}") String publication,
            @Value("${cdc.offset-file}") String offsetFile) {

        Properties config = new Properties();
        config.setProperty("name", "spring-orders-cdc");
        config.setProperty("connector.class",
            "io.debezium.connector.postgresql.PostgresConnector");
        config.setProperty("database.hostname", host);
        config.setProperty("database.port", Integer.toString(port));
        config.setProperty("database.dbname", database);
        config.setProperty("database.user", username);
        config.setProperty("database.password", password);
        config.setProperty("plugin.name", "pgoutput");
        config.setProperty("slot.name", slotName);
        config.setProperty("publication.name", publication);
        config.setProperty("publication.autocreate.mode", "disabled");
        config.setProperty("table.include.list", "public.orders");
        config.setProperty("topic.prefix", "orders_source");
        config.setProperty("snapshot.mode", "initial");

        config.setProperty("offset.storage",
            "org.apache.kafka.connect.storage.FileOffsetBackingStore");
        config.setProperty("offset.storage.file.filename", offsetFile);
        config.setProperty("offset.flush.interval.ms", "10000");

        return IntegrationFlow
            .from(Debezium.inboundChannelAdapter(config)
                .contentType("application/json")
                .enableBatch(false))
            .channel("ordersCdcInput")
            .get();
    }
}
~~~

Cấu hình trên là **một pipeline embedded Debezium, không dùng Spring poller**. Khi application context khởi động, producer/engine lifecycle được Spring quản lý. Output channel `ordersCdcInput` cần consumer/handler tiếp theo; nếu không, gửi message có thể thất bại tùy channel.

**Version caution:** danh sách connector properties/phụ thuộc thay đổi giữa Debezium 2.x, 3.x và các DB vendors. Đối chiếu đúng tài liệu version đã chốt trong dependency resolution; ví dụ mô tả contract PostgreSQL với `pgoutput` và file offset store.

## 9. Nhận change event với ServiceActivator và DebeziumHeaders

Ở chế độ mặc định `enableBatch(false)` với JSON byte-array serialization, mỗi event thường được chuyển thành một Spring message với payload `byte[]`. Header `DebeziumHeaders.KEY` chứa key đã serialize; `DebeziumHeaders.DESTINATION` cho biết destination logic.

~~~java
package com.example.cdc;

import java.nio.charset.StandardCharsets;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.debezium.support.DebeziumHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrdersCdcLogger {

    @ServiceActivator(inputChannel = "ordersCdcInput")
    public void onChange(Message<?> message) {
        Object destination =
            message.getHeaders().get(DebeziumHeaders.DESTINATION);

        Object keyHeader =
            message.getHeaders().get(DebeziumHeaders.KEY);
        String key = keyHeader instanceof byte[] data
            ? new String(data, StandardCharsets.UTF_8)
            : String.valueOf(keyHeader);

        Object payload = message.getPayload();
        if (payload instanceof byte[] bytes) {
            String json = new String(bytes, StandardCharsets.UTF_8);
            System.out.printf("destination=%s key=%s payload=%s%n",
                destination, key, json);
        } else {
            // Ví dụ tombstone / payload format khác; không cast bừa.
            System.out.printf("destination=%s key=%s type=%s%n",
                destination, key, payload.getClass().getSimpleName());
        }
    }
}
~~~

**Đây là logger dùng cho lab.** Trong production không log toàn bộ `customer_id`/`total_cents`/JSON có thể chứa PII, mã định danh khách hàng hoặc secrets. Biến `payload` không nhất thiết luôn là `byte[]` nếu bật batch/tombstone hoặc cấu hình serialization khác.

Các header này là metadata từ Debezium change event, **không phải OAuth/JWT headers đáng tin để authorize**. Định tuyến theo destination và key cũng phải có allowlist vì schema/topic có thể thay đổi sau migration.

## 10. Hợp đồng JSON: trước/sau, loại thao tác và metadata nguồn

Debezium tạo **change event envelope**. Với PostgreSQL, giá trị được serialize thường có các trường `before`, `after`, `op`, `source`, `ts_ms` và có thể có metadata transaction. Nếu bật JSON schema, có thể có wrapper `schema`/`payload`:

~~~json
{
  "schema": {
    "type": "struct",
    "name": "orders_source.public.orders.Envelope"
  },
  "payload": {
    "before": null,
    "after": {
      "id": 101,
      "customer_id": "C-001",
      "status": "CREATED",
      "total_cents": 125000
    },
    "source": {
      "connector": "postgresql",
      "db": "appdb",
      "schema": "public",
      "table": "orders",
      "snapshot": "true",
      "lsn": 123456789
    },
    "op": "r",
    "ts_ms": 1730000000000
  }
}
~~~

Đây là **JSON minh họa đã rút gọn**, không phải bản chép chính xác mọi trường/schema của một connector version. Trên thực tế, schema có thể dài và event formats khác nhau theo `converter.schemas.enable`/Debezium serialization. Không hardcode đường dẫn `root.payload` mà bỏ qua các trường hợp output đã bỏ schema wrapper.

Các mã `op` thường gặp:

| `op` | Ý nghĩa | `before` | `after` |
|---|---|---|---|
| `r` | Snapshot read event | Thường null | Row được snapshot |
| `c` | CREATE/INSERT | Thường null | Row mới |
| `u` | UPDATE | Row trước, tùy cấu hình/replica identity | Row mới |
| `d` | DELETE | Row cũ (nếu nguồn ghi đủ) | Null |
| `t` | TRUNCATE nếu connector và cấu hình hỗ trợ | Không theo row bình thường | Không theo row bình thường |

**Chú ý PostgreSQL `REPLICA IDENTITY`:** nếu là `DEFAULT`, thông tin `before` của UPDATE/DELETE có thể chỉ bao các cột khóa hoặc giới hạn; không suy luận luôn có full row trước UPDATE. Nếu nghiệp vụ cần toàn bộ before image, xem xét `REPLICA IDENTITY FULL` và chi phí WAL/storage.

**DELETE và tombstone khác nhau:** một `op="d"` event có payload với `before` và `after=null`; sau đó có thể có **tombstone event** có value null/empty dùng cho log compaction. Hai events cần được xử lý theo hợp đồng khác nhau.

## 11. Parse JSON an toàn và tạo domain change event

Handler dùng Jackson để parse event; trước khi truy cập `after.id` phải kiểm tra `op`, schema wrapper và null:

~~~java
package com.example.cdc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.stereotype.Component;

@Component
public class CdcJsonParser {

    private final ObjectMapper mapper;

    public CdcJsonParser(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public CdcOperation parse(byte[] jsonBytes) throws IOException {
        JsonNode root = mapper.readTree(jsonBytes);
        JsonNode envelope = root.hasNonNull("payload")
            ? root.path("payload") : root;

        String op = envelope.path("op").asText("");
        JsonNode before = envelope.path("before");
        JsonNode after = envelope.path("after");

        if (op.isBlank()) {
            throw new IllegalArgumentException(
                "Missing Debezium operation");
        }

        return new CdcOperation(
            op,
            before.isMissingNode() || before.isNull()
                ? null : before,
            after.isMissingNode() || after.isNull()
                ? null : after);
    }

    public record CdcOperation(
        String operation, JsonNode before, JsonNode after) { }
}
~~~

Hãy **parse `DebeziumHeaders.KEY` riêng** nếu cần primary key. Key có thể là structured JSON chứa `schema/payload`, không tự là text `101`. Dùng `StandardCharsets.UTF_8`, kiểm tra null/empty; không rely vào platform default encoding.

Ví dụ routing nghiệp vụ:

~~~java
CdcJsonParser.CdcOperation event = parser.parse(bytes);

switch (event.operation()) {
    case "r", "c" -> upsertProjection(event.after());
    case "u" -> upsertProjection(event.after());
    case "d" -> deleteProjection(event.before());
    default -> auditUnknownOperation(event.operation());
}
~~~

Đây là **pseudocode trong method có `parser`, `bytes` và các services đã định nghĩa**, không phải ứng dụng chạy độc lập. Khi snapshot chạy lại, `r` có thể trùng dữ liệu đã stage; `upsertProjection` nên idempotent và dùng version/ordering nếu có concurrency.

## 12. Snapshot rồi streaming: khởi động lần đầu

Debezium thường cần **initial snapshot** để có trạng thái các rows hiện tại, sau đó theo log để nhận các thay đổi tiếp theo.

~~~mermaid
stateDiagram-v2
    [*] --> START
    START --> SNAPSHOT: snapshot.mode=initial, chưa có offset
    SNAPSHOT --> STREAM: Hoàn tất snapshot
    START --> STREAM: Có offset bền, có thể resume
    STREAM --> STREAM: WAL INSERT/UPDATE/DELETE
    STREAM --> STOP: Graceful shutdown
    STOP --> START: Restart dùng offset
~~~

| Trường hợp | Hành vi cần hiểu |
|---|---|
| Start lần đầu với `snapshot.mode=initial` | Connector thường snapshot dữ liệu hiện có rồi stream |
| Restart với offset hợp lệ | Resume từ offset đã lưu (kèm khả năng replay) |
| Offset file bị xóa | Có nguy cơ snapshot lại hoặc tái lập vị trí sai |
| Replication slot/WAL cần đọc không còn | Connector có thể không resume và cần recovery |
| `snapshot.mode=no_data` | Chỉ theo dõi thay đổi từ vị trí phù hợp, **không** lấy dữ liệu cũ ban đầu |
| Thay `table.include.list` | Phạm vi capture thay đổi, phải có migration/backfill plan |
| Initial snapshot khi DB đang nhiều writes | Cần hiểu snapshot consistency và log catch-up của connector |

Đừng nhìn event `op="r"` như thao tác INSERT mới của business nếu đó là snapshot. Nếu consumer phải phân biệt “đã tồn tại từ trước” với “được tạo sau connector startup”, dùng `op` và metadata `source.snapshot` tương ứng.

**Không dùng cursor `MAX(id)` thủ công để thay cho replication offset của Debezium**. Offset thuộc vị trí log/snapshot của connector và có ngữ nghĩa riêng theo DB vendor; tự sửa file offset không có runbook có thể làm mất/thừa events.

## 13. Cách cấu hình khác: DebeziumEngine.Builder và DebeziumMessageProducer

Bên cạnh `Properties` trong DSL, Spring Integration chấp nhận **`DebeziumEngine.Builder<ChangeEvent<byte[],byte[]>>` đã cấu hình trước**. Cách này hữu ích khi ứng dụng có một service riêng cung cấp engine builder, hoặc khi cần chỉnh tùy chọn serialization, custom Debezium SMT/predicates hoặc engine lifecycle.

~~~java
package com.example.cdc;

import io.debezium.engine.ChangeEvent;
import io.debezium.engine.DebeziumEngine;
import io.debezium.engine.format.JsonByteArray;
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DebeziumEngineBuilderConfiguration {

    @Bean
    public DebeziumEngine.Builder<ChangeEvent<byte[], byte[]>>
            postgresEngineBuilder(Properties postgresCdcProperties) {

        return DebeziumEngine.create(JsonByteArray.class)
            .using(postgresCdcProperties);
    }
}
~~~

**Điều kiện:** `postgresCdcProperties` là một bean `Properties` do ứng dụng cung cấp, chứa các trường `name`, `connector.class`, `offset.storage` và PostgreSQL connector properties tương tự mục 8. Đây là **cấu hình thay thế**, không phải class độc lập đầy đủ chỉ với mảnh code trên.

Sau khi có builder, tạo message producer:

~~~java
package com.example.cdc;

import io.debezium.engine.ChangeEvent;
import io.debezium.engine.DebeziumEngine;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.debezium.inbound.DebeziumMessageProducer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageProducer;

@Configuration
public class DebeziumProducerBeans {

    @Bean
    public MessageChannel ordersCdcDirect() {
        return new DirectChannel();
    }

    @Bean
    public MessageProducer ordersDebeziumProducer(
            DebeziumEngine.Builder<ChangeEvent<byte[], byte[]>> builder,
            @Qualifier("ordersCdcDirect") MessageChannel channel) {
        DebeziumMessageProducer producer =
            new DebeziumMessageProducer(builder);
        producer.setContentType("application/json");
        producer.setEnableBatch(false);
        producer.setOutputChannel(channel);
        return producer;
    }
}
~~~

**Quan trọng:** `DebeziumEngine.create(JsonByteArray.class)` chọn JSON dạng `byte[]` và tương thích với `ChangeEvent<byte[],byte[]>`. Nếu dùng `Json.class` của Debezium Engine, kiểu event thường là `ChangeEvent<String,String>`; không cast builder `String` sang `byte[]` rồi gắn vào constructor trên. Debezium có thể chọn engine implementation bất đồng bộ khác theo phiên bản, nhưng API builder vẫn phải đúng generic format.

Đây là một **cách dựng khác** với `IntegrationFlow.from(Debezium.inboundChannelAdapter(config))`. Không đăng ký cả hai producers trên cùng slot/config cùng lúc; hai engines tranh cùng replication slot và offset có thể gây lỗi hoặc duplicate.

### 13.1. Kết nối producer với handler

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;

@ServiceActivator(inputChannel = "ordersCdcDirect")
public void consume(Message<?> message) {
    // Parse JSON bytes, phân loại op và ghi công việc bền vững.
}
~~~

Đây là **mảnh method** cần đặt trong Spring `@Component` hoặc bean phù hợp. Nếu muốn gắn thêm filter/router/service activator bằng DSL, có thể dùng `IntegrationFlow.from("ordersCdcDirect")...` ở một cấu hình riêng, nhưng phải bảo đảm có **đúng subscriber mong muốn** trên `DirectChannel`.

## 14. Cấu hình headers, content type và routing

`DebeziumMessageProducer` hỗ trợ các tùy chọn:

| Tùy chọn | Mặc định/ý nghĩa |
|---|---|
| `contentType` | JSON mặc định; có thể AVRO/PROTOBUF, phải đúng `SerializationFormat` của Engine |
| `enableBatch(false)` | Mỗi `ChangeEvent` thành một message riêng |
| `enableBatch(true)` | Một message có `List<ChangeEvent>` của batch Engine |
| `enableEmptyPayload(false)` | Bỏ/không chuyển các tombstone empty-value events |
| `headerMapper` | Ánh xạ Debezium event headers vào Spring message headers |
| `headerNames(...)` DSL | Chọn tên event headers cần map |
| `taskExecutor(...)` | Dùng một `TaskExecutor` cho Engine |
| `errorChannel(...)` | Cấu hình cơ chế message producer error channel theo khả năng framework |

Ví dụ Java DSL:

~~~java
// Mảnh đặt bên trong IntegrationFlow.from(...).
Debezium.inboundChannelAdapter(config)
    .contentType("application/json")
    .enableBatch(false)
    .enableEmptyPayload(true)
    .headerNames("trace*", "tenant*");
~~~

Các patterns trong `headerNames` dùng để lọc **Debezium event headers**, không phải để chọn bảng cần CDC. Muốn chọn bảng, cấu hình `table.include.list` của connector; muốn chọn message theo `DebeziumHeaders.DESTINATION`, dùng Spring Integration filter/router downstream.

`DebeziumHeaders.KEY` chứa event key, `DebeziumHeaders.DESTINATION` là tên logical destination (thường xuất phát từ `topic.prefix`, schema, table). Không mặc định mọi Debezium event header đều là business header; cần quy tắc trust, size và serialization.

### 14.1. Content type phải phù hợp serialization

Nếu engine builder tạo `JsonByteArray`, handler có thể nhận `byte[]`. Nếu chuyển sang `Avro` hoặc `Protobuf`, không dùng `new String((byte[]) payload)` rồi coi là JSON; cần đúng deserializer/schema registry hoặc mapping phù hợp.

**Không gán `contentType("application/avro")` chỉ để đổi HTTP header trong khi Engine vẫn serialize JSON.** Content type là hợp đồng giữa producer và downstream, phải khớp bytes thật.

## 15. Batch mode: một List<ChangeEvent> không phải List<byte[]>

Spring Integration Debezium adapter có hai dạng phát message:

~~~text
enableBatch(false): default
  Debezium ChangeEvent 1 -> Message<byte[]> 1
  Debezium ChangeEvent 2 -> Message<byte[]> 2
  Debezium ChangeEvent 3 -> Message<byte[]> 3

enableBatch(true):
  Debezium batch [event1,event2,event3]
       -> một Message<List<ChangeEvent>>
~~~

**Giới hạn được tài liệu chính thức nhấn mạnh:** khi bật `enableBatch(true)`, payload là **`List<ChangeEvent>` không serializable** theo contract của adapter. Nó không thích hợp để mặc định gửi qua một persistent message store, Redis/JMS serializer hoặc JSON transformer kỳ vọng một Java bean đơn.

Để xử lý in-process:

~~~java
package com.example.cdc;

import io.debezium.engine.ChangeEvent;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class BatchCdcHandler {

    @ServiceActivator(inputChannel = "ordersCdcBatches")
    public void onBatch(Message<?> message) {
        if (!(message.getPayload() instanceof List<?> events)) {
            throw new IllegalArgumentException("Expected List");
        }
        for (Object candidate : events) {
            if (!(candidate instanceof ChangeEvent<?, ?> event)) {
                throw new IllegalArgumentException(
                    "Expected Debezium ChangeEvent");
            }
            Object value = event.value();
            if (value instanceof byte[] bytes) {
                String json =
                    new String(bytes, StandardCharsets.UTF_8);
                // Parse/store/idempotent handler: không chỉ print.
                handleJson(json);
            } else {
                handleTombstoneOrFormat(value);
            }
        }
    }

    private void handleJson(String json) {
        // Application-specific durable processing.
    }

    private void handleTombstoneOrFormat(Object value) {
        // Xử lý empty value / format khác theo contract.
    }
}
~~~

**Đoạn này chỉ dùng khi flow được cấu hình `enableBatch(true)` và output channel là `ordersCdcBatches`.** Ví dụ `ordersCdcInput` ở mục 8/9 dùng `enableBatch(false)`, vì vậy không được nối trực tiếp handler kiểu batch vào đó. Nếu cần chuyển list thành các messages riêng, hãy viết splitter/transformer có chính sách tombstone và serialization rõ ràng.

### 15.1. Đừng nhầm Debezium batch với JdbcMessageHandler batch

| Thành phần | Từ “batch” nghĩa là gì? |
|---|---|
| Debezium Engine | Nhiều change records đến một callback |
| Debezium inbound `enableBatch(true)` | Một `Message<List<ChangeEvent>>` |
| Spring `Aggregator` | Gom một nhóm messages theo rule riêng |
| JDBC outbound `JdbcMessageHandler` | Có thể `batchUpdate` khi payload `Iterable` theo hợp đồng JDBC |
| Kafka producer | Batch các records cho network/protocol |

`Message<List<ChangeEvent>>` **không phải `List<InventoryUpdate>`** phù hợp JDBC outbound SQL. Cần parse, validate, transform và xác định keys/types trước khi chuyển sang JDBC batch. Không truyền trực tiếp raw `ChangeEvent` vào PreparedStatement setter dành cho domain DTO.

## 16. DELETE và tombstone: không đánh đồng hai sự kiện

Khi một row bị DELETE, Debezium có thể phát:

1. **Delete event:** envelope với `op="d"`, `before` có dữ liệu (tùy connector/replica identity), `after=null`.
2. **Tombstone event:** cùng key nhưng value null/empty, phục vụ Kafka log compaction hoặc downstream protocol khác.

Tùy cấu hình Debezium connector, tombstone có thể được bật/tắt. Tại Spring Integration adapter, **`enableEmptyPayload(false)` là mặc định**, nghĩa là không tự nhận mọi tombstone. Khi cần chuyển loại event này, bật:

~~~java
Debezium.inboundChannelAdapter(config)
    .enableEmptyPayload(true);
~~~

**Lưu ý:** Spring Messaging không chấp nhận một `null` payload thông thường; theo API của Debezium adapter, tombstone/empty value được biểu diễn theo hợp đồng **`Optional.empty()`**. Handler phải kiểm tra kiểu trước khi cast `byte[]`.

~~~java
import java.util.Optional;
import org.springframework.messaging.Message;

void handle(Message<?> message) {
    Object payload = message.getPayload();
    if (payload instanceof Optional<?> option && option.isEmpty()) {
        // Tombstone: xử lý theo policy compaction / delete cache entry.
    } else if (payload instanceof byte[] bytes) {
        // Change-event JSON, kiểm tra op, before/after.
    } else {
        // Unexpected format: log metadata an toàn và phân loại.
    }
}
~~~

Đây là **mảnh method** chứ không phải full class. Không mặc định mọi `payload=null` là DELETE: một message có giá trị không mong đợi cũng có thể do lỗi serialization, converter hoặc schema.

Nếu downstream là cache/search index, thường `op="d"` đủ để xóa theo business key; nếu downstream là một log-compacted Kafka topic, tombstone có vai trò riêng. Định nghĩa chính sách từng sink, không bỏ các DELETE im lặng.

## 17. Offset store: thay cho “lần đọc cuối” trong JDBC polling

Debezium Engine phải lưu **source offset** để biết đã đọc/đánh dấu xử lý đến đâu. Trên PostgreSQL, vị trí này liên quan tới WAL/LSN, snapshot và metadata connector; không giống `last_id` của JDBC polling.

~~~text
PostgreSQL WAL change stream:
    ... LSN A --- LSN B --- LSN C ...
                   |
                   +--- Debezium Engine offset
                          |
                          +--- FileOffsetBackingStore / other durable store
~~~

Cấu hình lab:

~~~properties
offset.storage=org.apache.kafka.connect.storage.FileOffsetBackingStore
offset.storage.file.filename=/var/lib/app/cdc/orders-offset.dat
offset.flush.interval.ms=10000
~~~

**Quan trọng khi restart:**
- File cần **volume bền**. Nếu pod bị xóa cùng local disk ephemeral, offset mất.
- Engine flush offset định kỳ; process crash có thể khiến một số change records được **phát lại**.
- Một file offset không tự bảo vệ downstream Kafka/HTTP/DB commit; offset và business side effect thuộc hai tài nguyên độc lập.
- Không chia sẻ file offset cùng lúc giữa nhiều engines nếu thiếu cơ chế khóa/ownership.
- Không chỉnh offset bằng tay hoặc xóa replication slot để “sửa lag” khi chưa có runbook đối soát.

Debezium có những offset backing stores khác (ví dụ JDBC, Kafka, Redis tùy version và dependencies). Chọn đúng connector/engine version và storage của hệ thống; `FileOffsetBackingStore` chỉ phù hợp workload/lifecycle đơn giản hoặc môi trường có persistent volume được kiểm soát.

## 18. Engine acknowledgment không đồng nghĩa downstream đã commit

Debezium Engine có API xử lý nâng cao `ChangeConsumer<R>` và `RecordCommitter<R>`. Với tự quản lý Engine, consumer gọi `markProcessed(record)` theo từng record và `markBatchFinished()` sau một batch để báo Engine đã xử lý, rồi Engine có thể flush offset theo policy.

~~~java
// Pseudocode khi trực tiếp dùng DebeziumEngine.ChangeConsumer,
// KHÔNG phải callback do DebeziumMessageProducer public API expose.
for (ChangeEvent<?, ?> event : records) {
    durableStage(event);  // ghi DB/outbox hoặc remote confirmation theo policy
    committer.markProcessed(event);
}
committer.markBatchFinished();
~~~

`DebeziumMessageProducer` **đóng gói Engine** và không tự biến mọi `MessageChannel`, executor hay Kafka outbound thành một transaction thống nhất. Cần kiểm tra implementation/version của adapter và Debezium Engine để xác định chính xác thời điểm callback/offset được đánh dấu. Không giả định `message sent` = `consumer business commit`.

Ví dụ ba cửa sổ lỗi:

| Thời điểm | Điều có thể xảy ra | Cách đối phó |
|---|---|---|
| Event đã đọc nhưng offset chưa flush | Sau restart event đọc lại | Idempotency/dedupe |
| Offset tiến/flush nhưng xử lý async chưa bền | Mất việc sau crash | Stage bền trước async boundary hoặc thiết kế ack riêng |
| Downstream Kafka nhận nhưng app chết trước khi ghi ack/offset | Có thể publish lại | Stable event ID, idempotent consumer |

**Nguyên tắc an toàn:** xem nguồn CDC là **at-least-once** trừ khi có hợp đồng end-to-end đã được chứng minh. Tránh “fire-and-forget” vào queue trong RAM rồi dựa vào offset để bảo đảm không mất record.

## 19. Transaction boundaries với DirectChannel, ExecutorChannel và broker

~~~mermaid
flowchart LR
    A["Debezium Engine callback"] --> B["DebeziumMessageProducer"]
    B --> C["DirectChannel"]
    C --> D["Synchronous JDBC stage/outbox"]
    D --> E[("Local DB commit")]
    B --> X["ExecutorChannel"]
    X --> Y["Async worker"]
    Y --> Z["TX riêng / retry riêng"]
~~~

| Chặng | Điều có thể bảo đảm | Điều không tự bảo đảm |
|---|---|---|
| `DirectChannel` tới handler JDBC | Handler chạy đồng bộ trên caller thread | Có sẵn JDBC transaction mà không mở |
| `@Transactional` service ở handler | DML của service cùng local DB transaction | Offset Debezium và DB commit atomic |
| `ExecutorChannel` | Offload compute/IO sang worker | Engine offset chờ đến khi worker hoàn tất |
| `QueueChannel` memory | Có buffer giữa producer và consumer | Bền qua JVM crash |
| Kafka outbound adapter | Gửi event tới broker theo client contract | Consumer downstream xử lý xong |
| JMS outbound adapter | Gửi message tới JMS broker | Local PostgreSQL offset/LSN cùng JMS commit |

**Không có một transaction Spring duy nhất tự bao PostgreSQL logical replication offset, SQL UPDATE ở database đích và Kafka/JMS ACK**. Nếu nghiệp vụ không chấp nhận mất sự kiện, hãy ghi durable inbox/outbox và thiết kế retry/ack tường minh.

Một chiến lược phổ biến: giữ handler CDC **nhanh**, parse/validate, ghi `inbox_event` vào database với unique event identifier; commit; rồi worker khác xử lý Kafka/HTTP. Nhưng cần hiểu rằng **độ bền của inbox phải được bảo vệ so với offset acknowledgment**, không chỉ viết một `@Transactional` trên một method bất kỳ.

## 20. Idempotency: CDC không mặc định exactly-once business effect

Khi offset flush và downstream commit là hai bước khác nhau, event có thể được phát lại. Một consumer an toàn cần xác định **định danh event/phiên bản**.

**Không dùng duy nhất primary key của row làm event ID** nếu nhiều UPDATE khác nhau xảy ra trên cùng row. Primary key `orders.id=101` chỉ nhận diện **aggregate**, không phân biệt lần cập nhật status từ CREATED → PAID rồi PAID → SHIPPED.

| Khóa | Có thể dùng cho | Lưu ý |
|---|---|---|
| `DebeziumHeaders.KEY` | Nhận diện row/partition | Không tự phân biệt các UPDATE khác nhau |
| `source.lsn` | Vị trí WAL/connector metadata | Một LSN đơn lẻ không luôn là ID event duy nhất qua mọi connectors |
| `source.txId` + order metadata | Hỗ trợ đối soát thứ tự | Cần xem uniqueness/scoping theo connector |
| Business `event_id` trong outbox | Dedupe business event | Ổn định và duy nhất qua retries |
| `(aggregateId, version)` | Idempotent projection/upsert có version | Cần version tăng đơn điệu theo aggregate |

Nếu cần phát sự kiện nghiệp vụ, **transactional outbox** cho phép ghi `event_id` cùng business transaction. Debezium theo dõi outbox table và downstream dùng event_id đó để dedupe, có thể thêm Debezium EventRouter SMT nếu phù hợp contract.

Ví dụ inbox idempotent:

~~~sql
CREATE TABLE processed_cdc_event (
    event_id     VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Trong **một local DB transaction của consumer**:
1. Kiểm tra/insert processed event ID bằng unique constraint.
2. Nếu đã tồn tại và payload khớp, coi đó là redelivery (không tạo side effect lần hai).
3. Nếu mới, áp dụng business UPDATE và ghi marker **cùng transaction**.
4. Commit trước khi ACK nguồn theo delivery policy thực tế.
5. Với Kafka/HTTP remote side effect, dùng outbox/remote idempotency key.

Không `INSERT processed` và commit riêng **trước** business operation: crash giữa hai bước có thể khiến lần retry bị coi là duplicate dù business chưa được áp dụng.

## 21. Deploy nhiều replicas: một CDC source không phải nhiều pollers tự chia job

Một hệ thống có ba Spring Boot pods đều auto-start `DebeziumMessageProducer` với **cùng slot.name` có thể tranh logical replication slot hoặc thất bại vì slot đang active. Nếu mỗi pod có một slot riêng trên cùng DB/tables, cả ba có thể nhận **cùng changes**, gây publish trùng và tăng WAL retention.

| Kiến trúc | Khuyến nghị |
|---|---|
| Một app instance nhúng Engine | Đơn giản nhất cho workload nhỏ |
| Nhiều app pods, chỉ một engine active | Leader election/lock với failover có kiểm soát |
| Nhiều độc lập CDC pipelines | Mỗi pipeline có identity/slot/offset riêng và downstream contract riêng |
| Cần HA/connector orchestration chuyên dụng | Kafka Connect cluster, Debezium Server/Operator tùy mục tiêu |
| Cần throughput cao downstream | Một CDC reader → durable queue/Kafka → nhiều consumers có partitioning |

**Đừng tạo một Engine mỗi HTTP request hoặc một Engine mỗi integration message.** Engine là long-running component có startup, snapshot, replication slot, offset và shutdown lifecycle; Spring quản lý `SmartLifecycle` của producer.

**Standby/failover cần giữ offset và slot nhất quán.** Bật standby trong khi primary vẫn chạy không phải HA an toàn nếu hai engines có thể đồng thời phát cùng stream. Quyết định single-reader ownership và định nghĩa cách verify failover before restart.

## 22. Graceful shutdown và startup lifecycle

`DebeziumMessageProducer` kế thừa `MessageProducerSupport`, là một Spring-managed endpoint có lifecycle. Khi start, engine chạy theo `TaskExecutor` (mặc định do adapter quyết định); khi stop, engine cần có cơ hội hoàn thành callback/flush offsets.

**Đối với Kubernetes:**
- Dùng graceful termination period đủ cho Engine dừng, connections đóng, offsets được flush.
- Không tắt cưỡng bức ngay khi nhận SIGTERM; pod có thể replay dữ liệu khi restart.
- Cấu hình liveness/readiness theo trạng thái thực của connector/lag; tránh liveness probes quá nhạy làm pod restart vòng lặp.
- Không giữ replication slot không còn dùng mãi; có runbook và quyền DBA để cleanup đúng.
- Persistent offset store (nếu file-based) phải mounted trước khi Engine start; kiểm tra read/write permissions.
- Nếu cần mTLS/TLS PostgreSQL, cấu hình connector/driver và secret rotation đúng version.

### 22.1. Chỉ định TaskExecutor

~~~java
import org.springframework.core.task.TaskExecutor;

// Mảnh cấu hình Java bean từ mục 13:
producer.setTaskExecutor(debeziumTaskExecutor);
~~~

Trong Java DSL có `.taskExecutor(debeziumTaskExecutor)`. `debeziumTaskExecutor` là một Spring bean `TaskExecutor` phù hợp long-running task; không dùng executor bão hòa bởi request handlers hoặc không có capacity. Với Debezium 3.x, default Engine implementation có thể là **AsyncEmbeddedEngine**, vì vậy cần xác định cả cơ chế concurrency của Engine, không chỉ tên executor Spring.

### 22.2. Đừng nhầm thread management với delivery guarantee

Đổi `TaskExecutor` sang một thread pool lớn **không** cho phép một logical PostgreSQL slot chia các records đồng đều thành nhiều reader instances, không tự bảo đảm ordering hay exactly-once. Tăng throughput cần đo bottleneck ở source decoding, serialization, transformation, channel, DB sinks và broker.

## 23. Khi nào chọn batch mode, khi nào mỗi message riêng?

| Tiêu chí | `enableBatch(false)` | `enableBatch(true)` |
|---|---|---|
| Payload | Thường JSON `byte[]` | `List<ChangeEvent>` |
| Tách lỗi từng event | Dễ hơn | Cần batch error policy |
| Mỗi event đi qua router/filter | Trực tiếp | Cần splitter/processor batch |
| Memory | Ít batch retention hơn | Có thể giữ nhiều events trong RAM |
| Serialization qua channel/store | Dễ chuyển thành JSON domain DTO | Raw List không serializable |
| Throughput | Overhead Spring message per event | Giảm số Spring messages nhưng parsing batch riêng |
| Retry | Theo event policy | Phải phân biệt lỗi một record/lỗi cả batch |
| Tombstone | Handler theo event | Phải xử lý null/empty value trong list |

**Bài toán cụ thể:** một batch CDC có 200 events, event thứ 73 sai schema. Nếu adapter phát list rồi handler ném exception, business phải chọn rollback toàn lô, quarantine event 73, hay tách thành phần. Không quyết định bằng cách tăng `enableBatch` mà không có xử lý poison message/offset consistency.

Một batch từ Debezium Engine **không đồng nghĩa một transaction DB nguồn**: kích thước batch và transaction grouping có thể khác. Khi consumer cần atomic theo business transaction, phải dùng transaction metadata/aggregation theo source thay vì coi mỗi batch là một source transaction.

## 24. Khả năng tương thích schema: update, rename, add column

CDC consumer thường gắn với dữ liệu row. Khi DBA thay đổi schema:

- Thêm cột nullable: parser nên bỏ qua trường không cần thiết hoặc xử lý default.
- Thêm cột NOT NULL: snapshot/stream có thể có hai hình dạng dữ liệu theo thời gian; cần quy tắc version.
- Rename column: `after.oldName` mất, `after.newName` xuất hiện; consumer hardcode field cũ sẽ fail.
- Đổi kiểu numeric/timestamp: Java `long`/`BigDecimal`/ISO timestamp có thể không còn tương thích.
- Đổi primary key: `DebeziumHeaders.KEY` và compacted Kafka topic semantics có thể đổi.
- Thay `REPLICA IDENTITY`: dữ liệu `before` của UPDATE/DELETE có thể khác.
- Connector schema history: MySQL/SQL Server/Oracle có thể cần history store riêng để giải mã sự kiện theo thời điểm schema.

**Phân biệt offset và schema history:** PostgreSQL `pgoutput` thường không cần history store kiểu MySQL theo ví dụ embedded engine; nhưng với MySQL connector, cần cấu hình `schema.history.internal` và nơi lưu history bền vững. Đừng copy `schema.history.internal.file.filename` từ MySQL sang PostgreSQL rồi mặc định bắt buộc cho mọi DB vendor.

Với JSON có schema wrapper, hãy version/validate cả event contract, không chỉ parse `after.id` bằng hardcoded path.

## 25. Lỗi kết nối, handler exception và retry

Một CDC pipeline gặp lỗi tại nhiều tầng khác nhau:

| Tầng | Lỗi điển hình | Cách ứng phó |
|---|---|---|
| PostgreSQL | DB unreachable, replication permission thiếu | Alert, retry kết nối có giới hạn |
| Logical replication | Slot active ở process khác, publication sai | Kiểm tra ownership/DBA, không tự xóa slot |
| WAL retention | Offset tham chiếu dữ liệu log đã bị xóa | Re-snapshot/rebuild/reconciliation theo runbook |
| Debezium Engine | Serializer/connector crash, config mismatch | Ghi diagnostics, quản lý Engine lifecycle |
| Spring adapter | Lỗi map headers/payload/tombstone | Handler nhận đúng dạng message/serialization |
| Downstream parser | JSON/schema sai, thiếu op/id | Validation/quarantine; không loop retry mãi |
| JDBC sink | Deadlock/constraint/connection timeout | Rollback unit, retry có backoff |
| Kafka/JMS outbound | ACK timeout hoặc kết quả không rõ | Outbox, stable event ID, reconciliation |
| Async channel | Queue đầy hoặc worker chết sau handoff | Bounded buffer, durable staging |
| Shutdown | Kill trước flush offset | Graceful stop và idempotent replay |

**Đừng giả định mọi exception ở `@ServiceActivator` đều đi thành một business reply.** CDC inbound là stream/producer, không phải request-reply gateway. Một số lỗi có thể được log, chuyển tới `errorChannel` hoặc khiến connector dừng/tiếp tục tùy API/phiên bản; cần test đúng version và phân loại.

### 25.1. Error channel không thay thế durable retry

`DebeziumMessageProducer` kế thừa `MessageProducerSupport` và có thể cấu hình `errorChannel`. Đây là cơ chế báo lỗi trong Spring Integration, nhưng **chưa phải** bảo đảm một Debezium change record được phát lại trước khi Engine tiến offset.

Ví dụ ý tưởng:

~~~java
// Mảnh Java DSL trong cấu hình source:
Debezium.inboundChannelAdapter(config)
    .errorChannel("cdcErrors");
~~~

Một handler của `cdcErrors` có thể log exception type, failedMessage metadata và gửi cảnh báo. Không đơn thuần gọi `logger.error(...)` rồi ACK mất event. Nếu phải không mất business effect, thiết kế stage bền vững/idempotency ở trước ranh giới bất đồng bộ, hoặc tự quản lý Engine với `ChangeConsumer/RecordCommitter` theo protocol đã kiểm thử.

### 25.2. Tránh poison message làm nghẽn vô hạn

Khi event không parse được do schema mismatch:
- **Không** retry cùng JSON 1000 lần mỗi giây; đó là retry storm.
- Không bỏ event và đánh dấu xử lý thành công nếu domain yêu cầu giữ dữ liệu.
- Ghi metadata event, destination, key, source position và nguyên nhân vào quarantine/DLQ **bền vững**; hạn chế log PII.
- Chọn policy có thể replay sau khi sửa schema, giữ source offset/unique event ID nếu phù hợp.
- Với lỗi transient DB/broker, dùng exponential backoff + jitter và circuit breaker/rate limiting khi cần.

**Định nghĩa “đã xử lý” trước khi bắt đầu:** đã parse? đã stage inbox? đã commit read model? đã publish Kafka? Mốc nào được dùng để cho phép connector tiến offset?

## 26. Backpressure và memory: nhanh quá cũng nguy hiểm

CDC stream có thể đến nhanh hơn tốc độ downstream xử lý. Nếu adapter nối tới một `DirectChannel` với handler JDBC/HTTP chậm, đường callback có thể bị kéo dài; trong khi đó WAL/offset lag có thể tăng. Nếu chuyển ngay vào `ExecutorChannel` không giới hạn, ứng dụng có thể tạo hàng nghìn tasks/memory và chết do OOM.

~~~mermaid
flowchart LR
    E["Engine callback"] --> M["Spring Message"]
    M --> D{"Downstream"}
    D -->|"DirectChannel"| S["Synchronous handler / latency"]
    D -->|"Async channel"| Q["Executor queue (bounded)"]
    Q --> W["Workers"]
    W --> B[("DB / Kafka sink")]
    S --> B
~~~

**Backpressure policy cần được chọn rõ:**
1. Dùng bounded executor/queue nếu offload I/O; định nghĩa hành vi khi queue đầy.
2. Ghi vào **durable inbox/outbox** trước khi coi record đã được nhận bền vững.
3. Đo throughput source/handler và lag, không chỉ kích thước executor queue.
4. Tránh giữ toàn bộ `List<ChangeEvent>` qua các stages không serialize được.
5. Điều chỉnh Debezium Engine/connector batch, queue, poll/heartbeat configuration **theo đúng connector version**.
6. Nếu sink down lâu, kiểm soát WAL retention; đừng tăng memory nội bộ vô hạn chỉ để che lag.

**Không xem `FluxMessageChannel` hoặc Reactor type là phép màu non-blocking.** PostgreSQL connector/replication client và JDBC sinks có phần blocking; các transaction JDBC theo thread không tự lan qua reactive/async boundaries.

## 27. Monitoring replication slot, WAL và offset lag trên PostgreSQL

Một subscription CDC bị kẹt có thể làm replication slot giữ WAL. Cần theo dõi:
- Slot có `active` hay không, process nào đang consume.
- `restart_lsn` và `confirmed_flush_lsn`.
- Độ lớn WAL có nguy cơ phải giữ (`pg_wal_lsn_diff` so với `restart_lsn`).
- Thời gian snapshot/stream lag; source DB CPU/network.
- Debezium Engine errors và last successfully processed record time.
- Message throughput/latency của Spring Integration.
- Downstream inbox/outbox pending age và DLQ.
- Kết quả failover, offset restore và replay duplicates.

~~~sql
-- PostgreSQL, cần quyền xem pg_replication_slots.
SELECT slot_name,
       plugin,
       active,
       restart_lsn,
       confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_name = 'spring_orders_slot';
~~~

~~~sql
-- Ước lượng WAL bytes phải giữ liên quan tới slot này.
SELECT slot_name,
       pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
           AS retained_wal_bytes
FROM pg_replication_slots
WHERE slot_name = 'spring_orders_slot'
  AND restart_lsn IS NOT NULL;
~~~

Đây là **chỉ số hỗ trợ cảnh báo**, không phải định nghĩa duy nhất của CDC lag. Dữ liệu thực phụ thuộc trạng thái replication, lag và chính sách WAL retention; kiểm tra `pg_stat_replication`, metrics DB và Debezium connector tương ứng. Không xóa replication slot đang giữ WAL chỉ vì disk báo đầy: nếu offset còn trỏ vào log đã mất, connector có thể không resume và sự kiện chưa đọc có thể thất lạc.

### 27.1. Metrics ứng dụng

| Metric | Ý nghĩa |
|---|---|
| `cdc_messages_received` | Số Spring Messages từ producer |
| `cdc_operations` theo `r/c/u/d` | Phân bố snapshot/stream/change |
| `cdc_parse_failures` | Schema/format errors |
| `cdc_ingest_latency` | Từ timestamp nguồn đến inbox commit |
| `cdc_snapshot_progress` | Tiến độ snapshot theo connector |
| `cdc_offset_flush_errors` | Lỗi persisting offsets |
| `cdc_slot_wal_retained_bytes` | Rủi ro WAL do replication slot |
| `cdc_inbox_oldest_age` | Downstream xử lý chậm |
| `cdc_outbox_publish_retries` | Broker/sink delivery issues |
| `cdc_duplicate_detected` | Replay/idempotency activity |
| `cdc_engine_running` | Liveness engine (khác HTTP app health) |

Không dùng `orderId/customerId` làm metric tag cardinality lớn. IDs chỉ nên vào logs/traces có kiểm soát; không in full `payload_json` nhạy cảm khi debug một trường hợp CDC.

## 28. Security và compliance cho CDC

CDC có thể sao chép **toàn bộ row và dữ liệu nhạy cảm** sang các hệ thống ngoài database. Trước khi bật `table.include.list`:

- Kiểm kê PII, secrets, token, payment data trong bảng.
- Dùng include/exclude table/column options hoặc SMT masking để chỉ truyền trường cần thiết.
- Chặn các trường cần mã hóa/tokenization trước khi tới Kafka/JMS/search.
- Cấp quyền DB `REPLICATION` và `SELECT` tối thiểu; không nhúng password vào source repository.
- Bảo vệ file offset và schema history với filesystem permissions/encryption khi cần.
- Kết nối DB bằng TLS/verification, quản lý certificate rotation và secret rotation.
- Định nghĩa retention/TTL cho inbox/outbox/replicated data phù hợp yêu cầu pháp lý.
- Dùng allowlist destination/schema và validate JSON trước khi quyết định side effect.
- Kiểm tra tombstone/delete policies khi phải xóa dữ liệu khỏi caches, indexes và sink storage.

**Một thay đổi schema có thể vô tình đưa thêm cột nhạy cảm vào CDC stream** nếu consumer/loggers tự serialize toàn bộ `after`. Versioning và data classification phải nằm trong deployment review, không chỉ trong Java parser.

## 29. Kiểm thử mức đơn vị: parser, operation và tombstone

Không cần một database thật để test parser xử lý `r/c/u/d` và schema wrapper. Một unit test dùng Jackson:

~~~java
package com.example.cdc;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class CdcJsonParserTest {

    @Autowired
    CdcJsonParser parser;

    @Test
    void parsesAnUpdateEnvelope() throws Exception {
        String json = """
            {
              "payload": {
                "before": {"id":101, "status":"CREATED"},
                "after":  {"id":101, "status":"PAID"},
                "op":"u",
                "source":{"table":"orders"}
              }
            }
            """;

        var change = parser.parse(
            json.getBytes(StandardCharsets.UTF_8));

        assertEquals("u", change.operation());
        assertEquals("CREATED",
            change.before().path("status").asText());
        assertEquals("PAID",
            change.after().path("status").asText());
    }
}
~~~

Tương tự, cần test:
1. Event `op="r"` có `before=null`.
2. Event `op="c"` có `after` và key.
3. Event `op="d"` có `after=null`.
4. Value tombstone không phải JSON bytes; handler phải rẽ nhánh trước parser.
5. JSON không có `op` hoặc thiếu `id` phải bị phân loại rõ ràng.
6. JSON không có `schema/payload` wrapper cũng phải parse.
7. UPDATE event có `before` thiếu các trường không thuộc key.
8. `after` chứa column mới, parser không ném lỗi vô cớ.
9. Key `DebeziumHeaders.KEY` có thể là JSON schema/value, không parse thành plain long.
10. Sensitive fields không xuất hiện nguyên văn trong error logs.

**Đây là unit/bean-context test của parser, không chứng minh Debezium Engine thực sự đọc được WAL**. Các tests về replication cần PostgreSQL/test DB thật.

## 30. Integration test PostgreSQL CDC bằng Testcontainers

Các điều kiện trước khi kiểm thử end-to-end:
- PostgreSQL chạy với `wal_level=logical` và đủ `max_replication_slots`/`max_wal_senders`.
- User/role có quyền replication và SELECT trên bảng đích.
- Publication, replication slot và `table.include.list` đúng.
- Offset store nằm ở thư mục test cô lập, có read/write permission.
- Chỉ **một Debezium Engine** đang consume slot test.
- Test có cơ chế chờ nhận events bất đồng bộ, không `Thread.sleep` cố định rồi đoán.

### 30.1. Container PostgreSQL với logical replication

~~~java
// Template test setup, không phải test class hoàn chỉnh.
import org.junit.jupiter.api.Test;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class PostgresDebeziumCdcIT {

    @Container
    static final PostgreSQLContainer postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("appdb")
            .withUsername("testuser")
            .withPassword("testpass")
            .withCommand("postgres",
                "-c", "wal_level=logical",
                "-c", "max_replication_slots=5",
                "-c", "max_wal_senders=5");

    @Test
    void capturesInsertUpdateDelete() {
        // Khởi tạo schema/role/publication trong DB test,
        // tạo Engine config riêng với ephemeral test offset,
        // start integration context, thực hiện SQL changes,
        // chờ message qua bounded QueueChannel/test probe,
        // assert op c/u/d + headers, rồi stop engine.
    }
}
~~~

**Đây là template định hướng với Testcontainers 2.x**, còn thiếu bootstrap SQL/roles, dynamic properties, test probe và assertions. Nếu ứng dụng dùng Testcontainers 1.x, tọa độ dependency và import class cũ khác (ví dụ `org.testcontainers:postgresql`, `org.testcontainers.containers.PostgreSQLContainer<?>`); không trộn hai major versions. Đặc biệt, `testuser` không nhất thiết có quyền thực hiện đầy đủ replication/publication trong mọi image/environment. Hãy dùng quyền trong lab thích hợp hoặc thao tác setup qua admin connection, không đem test-only superuser vào production.

### 30.2. Ma trận tích hợp

| Kịch bản | Điều cần xác minh |
|---|---|
| Khởi động lần đầu `snapshot.mode=initial` | Nhận sự kiện `r` cho rows hiện hữu |
| INSERT sau snapshot | Nhận `op="c"` với `after` |
| UPDATE | Nhận `op="u"`; xử lý `before` tùy replica identity |
| DELETE | Nhận `op="d"`; tombstone theo config |
| `enableBatch(false)` | Payload một event `byte[]` |
| `enableBatch(true)` | Payload `List<ChangeEvent>` |
| Offset bền qua process restart | Resume hợp lệ, có thể replay có kiểm soát |
| Offset file mất | Kịch bản resnapshot/recovery được xác định |
| Engine đang dùng slot | Engine thứ hai không được assumed share slot |
| Publication không chứa bảng | Phát hiện không có events do DB config |
| Event có thêm cột | Consumer không vỡ vì field không dùng |
| Handler fail/transient DB outage | Error policy, offset/retry/idempotency thực tế |
| Queue đầy khi sink chậm | Bounded buffer, không OOM |
| Kafka/JMS sink timeout | Đối soát/ràng buộc durable inbox/outbox |
| WAL lag tăng | Alert trước khi retention gây outage |

**Không chạy song song nhiều integration tests dùng cùng `slot.name` và offset file** trừ khi chủ đích kiểm tra collision. Với mỗi test suite, tạo tên slot/publication/offset path riêng hoặc cô lập database. Cleanup slot và volume test sau khi Engine dừng an toàn.

## 31. Crash/restart và redelivery: bài test tin cậy nhất

~~~mermaid
sequenceDiagram
    participant DB as PostgreSQL
    participant C as Debezium + Spring Integration
    participant I as Durable inbox
    participant S as Downstream service
    DB-->>C: Change event E1
    C->>I: INSERT inbox(E1)
    I-->>C: COMMIT
    Note over C: Process bị kill trước offset flush
    DB-->>C: Sau restart phát lại E1
    C->>I: INSERT inbox(E1) lần hai
    I-->>C: Unique event ID conflict (duplicate hợp lệ)
    I->>S: Một worker xử lý E1 theo policy
~~~

Bài test fault-injection nên mô phỏng:
1. Crash **trước** khi handler nhận event: Engine resume/đọc lại theo offset đã lưu.
2. Crash **sau inbox COMMIT trước offset flush**: event replay; inbox unique constraint chống stage trùng.
3. Crash **sau offset flush nhưng trước async worker xử lý**: nếu inbox chưa bền, có nguy cơ mất việc; xác nhận thiết kế không dựa vào queue RAM.
4. Kafka nhận message nhưng publisher crash **trước** khi đánh dấu outbox published: có thể publish lại; consumer idempotent.
5. Replication slot bị xóa hoặc WAL không còn: runbook re-snapshot/backfill bảo vệ thiếu dữ liệu.
6. Một pod leader chết, standby start: không chạy hai engines dùng cùng slot đồng thời và không bỏ qua offsets.
7. Schema thay đổi trong lúc snapshot/stream: consumer xử lý format evolution.
8. Lỗi mạng giữa snapshot và streaming: connector resume chính xác theo semantics của version.

**Không kết luận exactly-once end-to-end chỉ vì một bài test không thấy duplicate.** Các cửa sổ commit/ACK/offset khác nhau khiến at-least-once và idempotency là giả định an toàn hơn.

## 32. Troubleshooting nhanh theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Động tác kiểm tra |
|---|---|---|
| Không có event nào | Publication/slot/table include, quyền DB hoặc snapshot mode | DB logs, connector startup, `pg_replication_slots` |
| Chỉ có `r` snapshot, không có `c/u/d` | WAL streaming chưa chạy/connector lỗi | Connector metrics, slot confirmed flush, WAL |
| Java `ClassCastException` với payload | Bật batch/tombstone/format khác | Kiểm tra `enableBatch`, `enableEmptyPayload`, `contentType` |
| Header key null | Source table không có PK/định dạng khác | Key mapping, table key constraint |
| `before` thiếu cột | PostgreSQL replica identity/config | Xem `REPLICA IDENTITY` và connector docs |
| Event duplicate khi restart | Offset flush chưa có/delivery at-least-once | Dedupe bằng event ID/aggregate version |
| Database disk tăng | Replication slot giữ WAL | WAL retained bytes, lag và consumer health |
| Nhiều pods lỗi slot active | Duplicate CDC engine/ownership | Single-leader protocol |
| Consumer backlog tăng | JDBC/Kafka sink chậm | Queue, pool, sink latency, rate limiting |
| Deserialize Avro/Protobuf lỗi | `contentType` khác Engine serialization | Converter/format và schema registry |
| Consumer bỏ mất DELETE | Không xử lý `op=d`/tombstone | Kiểm tra stream, `enableEmptyPayload` |
| Retry vô hạn cùng event | Poison message/schema conflict | Quarantine và policy theo loại lỗi |
| `topic.prefix` thay đổi | Destination/key mapping bị đổi | Kiểm tra migration; không rename tùy tiện |
| Offset file bị xóa | Không có persistent store | Restore/backfill/snapshot theo runbook |

Một sự cố CDC thường trải qua **ba khu vực trách nhiệm**: DBA quản lý WAL/slot/publication; platform quản lý Engine lifecycle/offset và deployment; application quản lý downstream idempotency/transaction. Checklist xử lý phải có đủ ba thay vì chỉ khởi động lại pod liên tục.

## 33. Các hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Debezium adapter chỉ là JDBC inbound poller có interval nhỏ” | Debezium dùng CDC/log streaming, không cần Spring poller |
| “Có `spring-integration-debezium` thì không cần connector” | Cần connector theo database (PostgreSQL, MySQL...) |
| “Java DSL `Debezium` chỉ có từ 7.0” | Có từ Spring Integration 6.2 |
| “`topic.prefix` nghĩa tự động gửi lên Kafka” | Chỉ là logical namespace; downstream Kafka adapter là bước khác |
| “Một table update luôn là business event đầy đủ” | Row change event có semantics kỹ thuật, nên cân nhắc outbox |
| “Snapshot `r` là INSERT thực tế vừa xảy ra” | Đó là đọc trạng thái ban đầu |
| “`op=d` giống tombstone” | Delete envelope và tombstone là hai events khác nhau |
| “`before` luôn chứa toàn bộ row” | Phụ thuộc DB/replica identity |
| “Payload luôn là `byte[]`” | Batch mode/tombstone/serialization khác có dạng khác |
| “`enableBatch(true)` tạo List<byte[]> serializable” | Tạo `List<ChangeEvent>` không serializable mặc định |
| “Đổi contentType sang Avro sẽ tự chuyển JSON thành Avro” | Engine serialization và contentType phải khớp |
| “`headerNames` chọn bảng Debezium đọc” | Chọn event headers để map, bảng do connector config |
| “Offset file đã lưu thì không bao giờ duplicate” | Có crash window, replay và at-least-once |
| “MessageChannel.send() nghĩa Kafka đã ACK” | Spring channel delivery khác broker ACK |
| “DirectChannel đồng bộ là DB transaction tự có” | Cần transaction boundary riêng |
| “ExecutorChannel giữ Engine ack cho đến worker hoàn tất” | Không có bảo đảm tự động |
| “3 pods cùng slot sẽ chia đều events” | Có thể tranh slot; không có auto partition work |
| “Mỗi pod một slot thì không trùng data” | Các slots riêng có thể đều đọc cùng changes |
| “WAL/replication slot không cần monitor” | Slot ngừng consume có thể giữ WAL và đầy disk |
| “Xóa slot để sửa lag vô hại” | Có thể mất log cần để resume |
| “CDC theo dõi được mọi thay đổi ngoài cấu hình quyền/bảng” | Phụ thuộc capture list, permission và log availability |
| “Thêm cột không ảnh hưởng consumer” | Schema evolution có thể làm parser/contract fail |

## 34. Bài thực hành

1. Tạo bảng `public.orders` trong PostgreSQL và chèn hai đơn hàng mẫu.
2. Cấu hình `wal_level=logical`, replication user, publication, slot ownership theo lab.
3. Thêm `spring-integration-debezium` và `debezium-connector-postgres` đúng versions.
4. Tạo `Properties` với PostgreSQL connector config, `topic.prefix` và file offset store bền vững.
5. Viết `IntegrationFlow.from(Debezium.inboundChannelAdapter(props))`, dùng `enableBatch(false)`.
6. Gắn `@ServiceActivator` vào output channel, đọc `DebeziumHeaders.KEY` và `DESTINATION`.
7. Đọc `byte[]` payload bằng UTF-8 và parse `r/c/u/d` qua Jackson.
8. Bật snapshot initial, kiểm chứng `op=r` cho rows có sẵn.
9. Thực hiện INSERT, UPDATE, DELETE sau snapshot; xác minh sự kiện và thứ tự dự kiến.
10. Đổi PostgreSQL `REPLICA IDENTITY` trong lab, so sánh `before` data khi UPDATE/DELETE.
11. Bật `enableEmptyPayload(true)`, kích hoạt DELETE có tombstone, xử lý `Optional.empty()`.
12. Bật `enableBatch(true)` ở một flow riêng, xác minh payload là `List<ChangeEvent>`.
13. Cố thử serialize batch payload vào persistent MessageStore, thiết kế mapper sang DTO serializable.
14. Tạo một `DebeziumEngine.Builder<ChangeEvent<byte[],byte[]>>` từ `JsonByteArray` và cấu hình producer bằng Java beans.
15. Thử `contentType` JSON/AVRO/PROTOBUF chỉ khi Engine format khớp; quan sát lỗi nếu không khớp.
16. Chọn `headerNames("trace*")`, phân biệt với `table.include.list`.
17. Restart Spring Boot với offset file bền; quan sát resume và có thể replay.
18. Xóa offset file **chỉ trong lab đã backup**, phân tích snapshot lại hoặc dữ liệu bị phát trùng.
19. Tạo hai Engine instances cùng `slot.name` trong test, phân tích slot active/collision.
20. Chạy một Engine với two downstream consumers qua Kafka/JMS thay vì mỗi pod một connector độc lập.
21. Tạo `inbox_event` với unique business event ID, mô phỏng event được redeliver sau crash.
22. Ghi transactional outbox cùng đơn hàng, dùng Debezium bắt thay đổi từ outbox table.
23. Cho sink DB/Kafka bị outage, theo dõi WAL retention, lag, bounded queue và error policy.
24. Viết test Testcontainers PostgreSQL với `wal_level=logical` và kiểm tra `r/c/u/d`.
25. Tạo migration thêm cột `discount_cents`, kiểm tra consumer schema evolution.
26. Cho Engine dừng graceful và kill cưỡng bức, so sánh các record bị replay và offset behavior.
27. Tạo dashboard cho slot active, WAL retained bytes, CDC messages/s, snapshot duration, inbox lag.
28. Lập runbook recovery khi slot bị xóa, offset không khớp hoặc WAL đã bị purge.
29. Thiết kế chế độ leader/standby cho hai pods, đảm bảo một reader active tại một thời điểm.
30. Viết phép thử bất đồng bộ: `ExecutorChannel` + durable inbox; kiểm tra không ACK mất event trước inbox commit.

**Tình huống tổng hợp:** một service Spring Boot đọc CDC từ PostgreSQL qua Debezium inbound adapter để gửi đơn hàng tới Kafka. Pod A vừa ghi inbox event và gửi Kafka thành công nhưng bị kill trước khi Engine flush offset; pod B standby khởi chạy cùng replication slot. Đồng thời DBA đã đổi schema thêm cột nhạy cảm, còn hàng đợi xử lý chậm khiến WAL retention tăng. Hãy thiết kế **leadership, offset persistence, inbox/outbox/idempotency, schema filtering/masking, graceful shutdown, metrics và recovery** sao cho không mất business event và không nhân đôi tác dụng nghiệp vụ không kiểm soát.

## 35. Tài liệu tham khảo

- [Spring Integration Reference — Debezium Support](https://docs.spring.io/spring-integration/reference/debezium.html): `DebeziumMessageProducer`, Java DSL, batch, tombstone, header mapper, JSON/Avro/Protobuf.
- [Spring Integration API — DebeziumMessageProducer](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/debezium/inbound/DebeziumMessageProducer.html): constructor, `setEnableBatch`, `setEnableEmptyPayload`, `setTaskExecutor`.
- [Spring Integration API — DebeziumMessageProducerSpec](https://docs.spring.io/spring-integration/docs/6.5.1/api/org/springframework/integration/debezium/dsl/DebeziumMessageProducerSpec.html): Java DSL methods `headerNames`, `enableBatch`, `contentType` và lifecycle.
- [Spring Integration API — Debezium DSL Factory](https://docs.spring.io/spring-integration/docs/6.5.1/api/org/springframework/integration/debezium/dsl/Debezium.html): `inboundChannelAdapter(Properties)` và `inboundChannelAdapter(Builder)`.
- [Spring Integration API — DebeziumHeaders](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/debezium/support/DebeziumHeaders.html): `KEY` và `DESTINATION`.
- [Spring Integration Reference — Changes 6.1 to 6.2](https://docs.spring.io/spring-integration/reference/changes-6.1-6.2.html): Debezium inbound adapter ra đời ở 6.2.
- [Debezium Documentation — Debezium Engine](https://debezium.io/documentation/reference/stable/development/engine.html): Engine, JSON/JsonByteArray, offset store, callback, `ChangeConsumer/RecordCommitter`, lifecycle.
- [Debezium Documentation — PostgreSQL Connector](https://debezium.io/documentation/reference/stable/connectors/postgresql.html): logical replication, `pgoutput`, publication, slot, snapshot, change event envelope.
- [Debezium Documentation — Storage Configuration](https://debezium.io/documentation/reference/stable/configuration/storage.html): file/JDBC/Kafka offset stores và schema history.
- [Debezium Documentation — Outbox Event Router SMT](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): khi dùng Debezium capture transactional outbox.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, QueueChannel và async boundaries.
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): transaction ở handler, scope và error behavior.
- [PostgreSQL Documentation — Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html): publications, subscriptions, WAL/logical decoding.
- [PostgreSQL Documentation — pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html): thông tin slot và WAL retention.

> **Ghi nhớ:** **Debezium inbound channel adapter** là cầu nối **CDC từ database log → Debezium Engine → Spring `MessageChannel`**, không phải JDBC poller. Trong Spring Integration 6.2+, `DebeziumMessageProducer`/`Debezium.inboundChannelAdapter(...)` hỗ trợ JSON, Avro/Protobuf, batch và tombstones theo cấu hình. Hãy phân biệt **snapshot `r`, stream `c/u/d`, tombstone, source offset, broker ACK và downstream transaction**; chúng không tự commit nguyên tử. Để vận hành an toàn cần offset store bền, quản lý replication slot/WAL, một active CDC reader có điều phối, schema/PII policy, inbox/outbox, retry và idempotency.
