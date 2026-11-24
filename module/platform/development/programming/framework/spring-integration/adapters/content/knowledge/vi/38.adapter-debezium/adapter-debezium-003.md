# Database table và connector configuration trong Spring Integration Debezium

## 1. Bài toán: kết nối đúng database chưa đủ để CDC chạy đúng

Một hệ thống bán hàng lưu `orders` và `order_outbox` trong PostgreSQL. Khi dữ liệu thay đổi, ứng dụng Spring Integration cần nhận các bản ghi CDC từ Debezium và chuyển thành `Message<?>`, sau đó cập nhật read model, gửi Kafka/JMS/AMQP hoặc đồng bộ một hệ thống ngoài. Nếu connector kết nối được nhưng cấu hình **bảng, replication, snapshot hoặc offset** sai, các tình huống sau vẫn xảy ra:

- Nhận quá nhiều bảng, vô tình phát tán PII sang sink.
- Đọc được snapshot `r` nhưng không nhận tiếp `c/u/d` do publication hoặc replication slot lỗi.
- Bỏ bảng mới sau migration dù ứng dụng nghĩ đã thay `table.include.list`.
- Chạy nhiều pods với cùng slot; một pod lỗi `replication slot is active` hoặc các slots khác nhau đọc trùng toàn bộ thay đổi.
- Xóa offset file hoặc slot rồi restart, làm snapshot lại, replay hoặc mất log cần thiết.
- Truyền `topic.prefix` nhưng tưởng nhầm Debezium Engine đã tự publish Kafka.

Bài **Database table và connector configuration** thuộc chương **Adapter Debezium** của module **SPRING_INTEGRATION_ADAPTERS**: kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành qua file, SFTP, HTTP, JMS, AMQP, Kafka và database; quan tâm message contract, xử lý lỗi và vòng đời kết nối.

**Mục tiêu:** thiết kế bảng nguồn có khóa, ràng buộc và hợp đồng CDC rõ ràng; chuẩn bị quyền và log replication; cấu hình Debezium PostgreSQL connector trong Spring Integration; phân biệt các tùy chọn của PostgreSQL, MySQL, SQL Server và Oracle; kiểm thử snapshot/stream/filter/schema migration, offset/restart, và các rủi ro vận hành.

## 2. Kiến trúc tổng thể: bảng nguồn, connector và IntegrationFlow

~~~mermaid
flowchart LR
    A["Business transaction"] --> B[("PostgreSQL: orders + outbox")]
    B --> C["WAL logical decoding"]
    C --> D["Publication + replication slot"]
    D --> E["Debezium PostgresConnector"]
    E --> F["Debezium Engine embedded"]
    F --> G["DebeziumMessageProducer"]
    G --> H["Spring MessageChannel"]
    H --> I["Filter / Transform / Validate"]
    I --> J["JDBC sink / Kafka / JMS / HTTP"]
~~~

Có **hai lớp cấu hình độc lập nhưng phải khớp nhau**:

1. **Database-side:** bảng và primary key; quyền `SELECT`/`REPLICATION`; PostgreSQL `wal_level`, publication, slot; MySQL binlog; SQL Server CDC enable; Oracle redo/LogMiner.
2. **Connector-side:** `connector.class`, địa chỉ/credentials, `topic.prefix`, database/schema/table/column filters, snapshot mode, offset store, transform, timeouts và engine lifecycle.

`DebeziumMessageProducer` là **inbound endpoint message-driven từ Engine**, không phải `JdbcPollingChannelAdapter` dùng `Pollers.fixedDelay(...)`. Sau khi chuyển thành Spring Message, upstream CDC có thể đi tiếp vào các kênh đồng bộ hoặc bất đồng bộ tùy yêu cầu.

**Phạm vi đảm bảo:** việc Debezium đọc một row change **không** khiến JDBC sink, Kafka producer hoặc remote HTTP commit cùng transaction với source database. Có thể replay events; cần idempotency hoặc transactional outbox/inbox ở ranh giới downstream.

## 3. Chọn cách triển khai Debezium trước khi viết Properties

| Cách chạy | Connector được quản lý ở đâu? | Khi nên chọn | Những gì cần tự quản lý |
|---|---|---|---|
| **Spring Integration Debezium inbound** | Debezium Engine nhúng trong Spring Boot JVM | Một luồng CDC nội bộ, ít hạ tầng riêng, muốn xử lý trực tiếp bằng `MessageChannel` | Startup/shutdown, offset, slot, HA, retry, lag |
| **Kafka Connect + Debezium connector** | Kafka Connect distributed cluster | Nhiều connectors, HA/operations tập trung, sink Kafka | Connect worker, connector tasks/config, Kafka/offset/history |
| **Debezium Server** | Runtime Debezium riêng | Tách CDC service khỏi ứng dụng, đẩy vào sinks được hỗ trợ | Server lifecycle, offset, sink delivery |
| **Transactional outbox + CDC** | Một trong các runtime trên đọc bảng outbox | Gửi business events sau DB transaction | Event ID, outbox schema, sink idempotency |

Trong bài này, ví dụ chính dùng **Embedded Debezium Engine qua Spring Integration**. Nếu triển khai Kafka Connect, cấu hình connector nguồn có nhiều trường tương tự nhưng **offset storage và vòng đời** của Connect worker khác Engine nhúng. Không sao chép nguyên mọi property giữa các runtime mà không hiểu quyền sở hữu.

## 4. Sơ đồ database cho một luồng CDC thực tế

Tạo bảng giao dịch và bảng outbox riêng. Ví dụ PostgreSQL:

~~~sql
CREATE SCHEMA IF NOT EXISTS commerce;

CREATE TABLE commerce.orders (
    id              BIGINT PRIMARY KEY,
    customer_id     VARCHAR(64) NOT NULL,
    status          VARCHAR(24) NOT NULL,
    amount_cents    BIGINT NOT NULL CHECK (amount_cents >= 0),
    version         BIGINT NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE commerce.order_outbox (
    event_id        UUID PRIMARY KEY,
    aggregate_id    BIGINT NOT NULL,
    aggregate_ver   BIGINT NOT NULL,
    event_type      VARCHAR(80) NOT NULL,
    payload_json    JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (aggregate_id, aggregate_ver)
);

CREATE INDEX idx_order_outbox_created
    ON commerce.order_outbox (created_at, event_id);

INSERT INTO commerce.orders
    (id, customer_id, status, amount_cents, version)
VALUES (101, 'C-101', 'CREATED', 150000, 0);
~~~

Một câu INSERT vào `order_outbox` nên được thực hiện **trong cùng business transaction** với UPDATE `orders`. Bảng outbox lưu event ID ổn định để downstream dedupe; không cần tin rằng mọi lần Debezium emit chỉ xảy ra một lần.

### 4.1. Các quyết định bảng ảnh hưởng trực tiếp CDC

| Thiết kế bảng | Tác động lên CDC | Khuyến nghị |
|---|---|---|
| **Primary key ổn định** | Tạo record key, route/partition/dedupe thuận lợi | Có PK rõ ràng, tránh đổi PK thường xuyên |
| Không có PK | Event key có thể null, DELETE/rekey khó xử lý | Xác định custom key hoặc điều chỉnh schema |
| Thay đổi PK | Có thể thành DELETE/tombstone/CREATE | Định nghĩa rekey policy |
| `BIGINT amount_cents` | Dễ giữ số tiền chính xác theo minor units | Kiểm tra range và currency riêng |
| Timestamp `updated_at` | Hữu ích quan sát, không phải offset Debezium | Không dùng timestamp làm CDC checkpoint |
| `version` tăng theo aggregate | Hỗ trợ idempotent read model và ordering | Tăng trong mỗi transaction nghiệp vụ |
| JSONB payload ở outbox | Business event envelope độc lập schema bảng | Version schema và hạn chế PII |
| Trigger/DDL | Có thể tạo thêm row changes | Kiểm tra tác dụng phụ, CDC capture scope |

**Không chỉ dựa vào `MAX(id)` hay `updated_at` để xác định vị trí log:** Debezium có source offsets (WAL LSN, binlog position...) do connector quản lý.

## 5. Schema, table và column filtering: filter nào tác động ở đâu?

Một connector có thể được cấu hình ở nhiều tầng:

~~~text
PostgreSQL database 'appdb'
  schemas: commerce, audit, public
  commerce.orders
  commerce.order_outbox
  commerce.customer_private
  audit.security_log

PostgreSQL publication: [commerce.orders, commerce.order_outbox]
          |
Debezium schema/table.include.list
          |
Debezium column.include.list / column.exclude.list
          |
SMT / Spring Integration filter/router
          |
Consumer allowed destinations
~~~

**Publication** quyết định bảng nào PostgreSQL xuất vào replication stream theo publication (đối với `pgoutput`). **`table.include.list`** của Debezium giới hạn những bảng connector **phát ra CDC events**. Chúng không phải một cơ chế duy nhất và không thay thế nhau. **`column.exclude.list`** điều chỉnh các trường được phát trong event; nó không bảo đảm dữ liệu nhạy cảm chưa từng xuất hiện trong database log hoặc pipeline nội bộ.

### 5.1. Danh sách include/exclude và regex

Các properties tiêu biểu:

~~~properties
schema.include.list=commerce
table.include.list=commerce[.]orders,commerce[.]order_outbox
column.exclude.list=commerce[.]orders[.]customer_id
~~~

Tài liệu Debezium dùng **regular expressions được khớp với toàn bộ tên định danh**, không phải từ khóa SQL `LIKE '%orders%'`. Dấu chấm regex thô `.` có nghĩa wildcard; dùng `[.]` để chỉ dấu chấm literal nếu muốn match chính xác. Kiểm tra cú pháp regex/identifier case theo connector version.

| Thuộc tính | Ví dụ | Phạm vi | Chú ý |
|---|---|---|---|
| `database.include.list` | `shopdb` ở MySQL | Database source (connector-dependent) | Không phải mọi connector hỗ trợ như nhau |
| `schema.include.list` | `commerce` | Các schema | Không trùng với exclude list |
| `table.include.list` | `commerce[.]orders` | Các bảng fully qualified | Phải phù hợp publication |
| `table.exclude.list` | `commerce[.]debug_.*` | Loại bảng | Không khai báo đồng thời include/exclude một scope |
| `column.include.list` | `commerce[.]orders[.]id,...` | Chọn columns | Không vừa include và exclude cùng scope |
| `column.exclude.list` | `commerce[.]orders[.]customer_id` | Bỏ columns | Không nên bỏ keys cần cho consumer |
| `snapshot.include.collection.list` | Phụ thuộc connector | Tập bảng snapshot nếu cấu hình | Khác tập bảng streaming |
| `table.include.list` sau deploy | Thêm bảng mới | Không tự hồi tố dữ liệu cũ | Cần incremental snapshot/backfill |

**Khi cần chính xác bảng `commerce.orders`, không dùng biểu thức `.*orders.*`**: nó có thể match thêm tables không muốn. Với PostgreSQL, tên/schema mặc định phân biệt quoted identifiers; để tránh nhầm, chọn tên đơn giản lower-case và kiểm tra representation thực.

### 5.2. Publication và Debezium filters không tự cập nhật lẫn nhau

Nếu publication chỉ chứa `commerce.orders` nhưng Debezium `table.include.list` chọn thêm `commerce.order_outbox`, không thể kỳ vọng connector nhận outbox changes chỉ nhờ sửa Properties. DBA phải cập nhật publication hoặc dùng chế độ auto-create/filtered được cho phép, rồi chạy kế hoạch snapshot/backfill phù hợp.

Ngược lại, publication chứa nhiều bảng nhưng Debezium lọc chỉ một bảng cũng không tự có nghĩa database không xử lý log của các bảng khác. Tối ưu và bảo mật nên bắt đầu từ **nguồn capture** rồi mới tới filters ở ứng dụng.

## 6. PostgreSQL: bật logical replication trước khi chạy connector

PostgreSQL logical decoding cần cấu hình server và quyền thích hợp. Với môi trường tự quản, DBA xem xét:

~~~conf
# postgresql.conf - ví dụ cho lab/DBA
wal_level = logical
max_replication_slots = 5
max_wal_senders = 5
# max_slot_wal_keep_size, wal retention, disk capacity:
# cần chọn theo lưu lượng và RPO/RTO thực tế
~~~

Một số thay đổi server parameters có thể yêu cầu restart. Trên managed PostgreSQL (RDS, Cloud SQL, Azure Database for PostgreSQL...), cách bật logical replication/parameter group và quyền replication khác; dùng tài liệu provider và không giả định có superuser.

Kiểm tra server:

~~~sql
SHOW wal_level;
SHOW max_replication_slots;
SHOW max_wal_senders;
SELECT current_database(), current_user;
~~~

**Điều kiện để stream event:** `wal_level=logical`, có slot capacity, quyền replication, publication đúng và connector có thể đọc log. Một kết nối JDBC `SELECT 1` thành công chưa chứng minh CDC đủ điều kiện.

## 7. PostgreSQL user, SELECT quyền và publication

Ví dụ môi trường lab, thực hiện bởi DBA/owner:

~~~sql
-- Database appdb, schema commerce đã được tạo.
CREATE ROLE cdc_reader LOGIN REPLICATION
  PASSWORD 'REPLACE_IN_SECRETS';

GRANT CONNECT ON DATABASE appdb TO cdc_reader;
GRANT USAGE ON SCHEMA commerce TO cdc_reader;
GRANT SELECT ON commerce.orders TO cdc_reader;
GRANT SELECT ON commerce.order_outbox TO cdc_reader;

-- DBA hoặc chủ sở hữu bảng tạo publication.
CREATE PUBLICATION commerce_cdc_pub
  FOR TABLE commerce.orders, commerce.order_outbox;
~~~

Trong production, **không nhúng mật khẩu**. Cấp quyền tối thiểu và quản lý qua secret manager; ví dụ `REPLACE_IN_SECRETS` chỉ là dấu minh họa.

### 7.1. Publication auto-create mode

| Mode | Ý nghĩa | Khi dùng |
|---|---|---|
| `disabled` | Connector không tự tạo publication | Ưu tiên khi DBA quản lý publication sẵn |
| `all_tables` | Tự tạo publication cho tất cả tables theo cơ chế/version | Cần quyền cao; cẩn trọng data exposure |
| `filtered` | Tự tạo/chỉnh publication theo filtering (khi quyền cho phép) | Cần kiểm tra ownership/privileges |
| `no_tables` | Chế độ khác có thể tồn tại ở một số phiên bản | Chỉ dùng khi docs phiên bản xác nhận |

Chỉ sử dụng modes **được connector version hỗ trợ**. Một property sai tên hoặc mode không hỗ trợ có thể làm Engine startup fail; không sử dụng `no_tables` nếu không được tài liệu version cụ thể xác nhận.

Với bài thực hành, chọn `publication.autocreate.mode=disabled`, xác định rõ publication do DBA tạo và đòi hỏi không cấp CREATE thêm cho ứng dụng. **Thao tác `CREATE PUBLICATION` đòi hỏi quyền sở hữu và quyền database phù hợp**; tài khoản `cdc_reader` chỉ có SELECT/REPLICATION không nhất thiết tự tạo được publication.

### 7.2. Kiểm tra publication

~~~sql
SELECT pubname, puballtables, pubinsert, pubupdate, pubdelete
FROM pg_publication
WHERE pubname = 'commerce_cdc_pub';

SELECT pubname, schemaname, tablename
FROM pg_publication_tables
WHERE pubname = 'commerce_cdc_pub'
ORDER BY schemaname, tablename;
~~~

Nếu bảng mới chưa nằm trong `pg_publication_tables`, connector `table.include.list` không làm PostgreSQL phát WAL logical rows của bảng ấy qua publication đã tồn tại.

## 8. Replication slot: vị trí đọc, quyền sở hữu và WAL retention

`slot.name` xác định một logical replication slot, ví dụ `commerce_cdc_slot`. PostgreSQL giữ lại WAL cần thiết cho consumer dựa trên slot; nếu Engine ngừng tiêu thụ lâu, WAL có thể tích tụ và làm đầy ổ đĩa.

~~~sql
SELECT slot_name, plugin, slot_type, active,
       restart_lsn, confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_name = 'commerce_cdc_slot';
~~~

Ước lượng WAL bytes còn cần từ vị trí `restart_lsn`:

~~~sql
SELECT slot_name,
       pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
         AS retained_wal_bytes
FROM pg_replication_slots
WHERE slot_name = 'commerce_cdc_slot'
  AND restart_lsn IS NOT NULL;
~~~

Đây là **một chỉ số** cần theo dõi, không thay thế toàn bộ connector lag metrics. `restart_lsn` và `confirmed_flush_lsn` có semantics khác nhau; không xem `pg_wal_lsn_diff` là end-to-end consumer latency.

### 8.1. Slot có thể tạo bằng Connector hoặc DBA

PostgreSQL cung cấp API SQL để tạo slot thủ công:

~~~sql
-- Chỉ DBA/nhân sự vận hành có quyền thực hiện,
-- chỉ dùng nếu slot chưa tồn tại và đã có kế hoạch ownership.
SELECT *
FROM pg_create_logical_replication_slot(
    'commerce_cdc_slot', 'pgoutput');
~~~

Nếu cấu hình connector và quyền cho phép, Debezium cũng có thể tạo slot khi start. **Không tạo hai slot khác nhau để “chia việc cho hai pods”**: hai slots đọc cùng publication sẽ có thể phát cùng data changes đến cả hai engines. Với một luồng CDC HA, thường cần một Engine active/leader, lưu offset bền và failover được điều phối.

### 8.2. Không đặt `slot.drop.on.stop=true` khi muốn resume bình thường

`slot.drop.on.stop` mặc định được thiết kế giữ slot qua shutdown. Nếu bật tự xóa slot, khi restart có thể không còn vị trí/WAL mà Engine cần để tiếp tục. Chỉ sử dụng trong bài lab hoặc chiến lược lifecycle rất cụ thể. Xóa slot production để chữa đầy đĩa mà không xem offset/recovery plan có nguy cơ gây **data loss**.

## 9. Replica identity: cột trước UPDATE/DELETE phụ thuộc DB

PostgreSQL `REPLICA IDENTITY DEFAULT` thường đưa **primary key** vào old-row identity, không tự cung cấp mọi giá trị `before` của UPDATE/DELETE trong CDC event.

~~~sql
-- Quan sát identity mode của bảng.
SELECT n.nspname, c.relname, c.relreplident
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'commerce'
  AND c.relname IN ('orders','order_outbox');
~~~

Nếu consumer cần full before image:

~~~sql
-- Cần DBA/owner duyệt vì tăng dữ liệu logical WAL.
ALTER TABLE commerce.orders REPLICA IDENTITY FULL;
~~~

**Trade-off:** `FULL` tăng thông tin trước thay đổi nhưng có thể tăng log volume và chứa PII vốn không cần đưa tới downstream. Ưu tiên thay đổi contract consumer để dùng `after`/business version hoặc dùng outbox nếu chỉ cần business event.

Không áp dụng REPLICA IDENTITY FULL cho toàn bộ database tùy tiện; đánh giá từng bảng, update rate, độ lớn row, index và yêu cầu bảo mật.

## 10. Cấu hình PostgreSQL Debezium connector bằng Properties

Một file properties minh họa cho **Embedded Engine**:

~~~properties
name=commerce-debezium-engine
connector.class=io.debezium.connector.postgresql.PostgresConnector
database.hostname=localhost
database.port=5432
database.user=cdc_reader
database.password=REPLACE_WITH_SECRET
database.dbname=appdb

plugin.name=pgoutput
slot.name=commerce_cdc_slot
publication.name=commerce_cdc_pub
publication.autocreate.mode=disabled

topic.prefix=commerce_source
schema.include.list=commerce
table.include.list=commerce[.]orders,commerce[.]order_outbox
snapshot.mode=initial

offset.storage=org.apache.kafka.connect.storage.FileOffsetBackingStore
offset.storage.file.filename=/var/lib/app/offsets/commerce-cdc.dat
offset.flush.interval.ms=10000
~~~

**Giải thích từng nhóm:**
- `name` định danh Engine/connector; `connector.class` chọn PostgreSQL connector.
- `database.*` mở kết nối đến DB. Không dùng tài khoản ứng dụng writer nếu có thể dùng CDC role chuyên biệt.
- `plugin.name=pgoutput` chọn logical decoding plugin tương thích PostgreSQL.
- `slot.name` là slot, `publication.name` là danh sách tables server phát cho connector.
- `topic.prefix` là logical namespace cho Debezium event destination (ví dụ `commerce_source.commerce.orders`), **không tự publish Kafka** khi chạy Engine nhúng.
- `schema.include.list` và `table.include.list` xác định data capture scope của Debezium; chúng phải phù hợp publication.
- `snapshot.mode=initial` lấy state hiện có lần đầu theo connector semantics, sau đó stream.
- `offset.storage` và `offset.storage.file.filename` quy định nơi lưu source offset của Engine; không phải Spring Integration MessageStore.
- `offset.flush.interval.ms` là chu kỳ flush, **không** phải Kafka/JMS consumer ACK và không bảo đảm exactly-once.

**Không đưa `REPLACE_WITH_SECRET` vào production config**: dùng environment/secret manager. Nếu dùng file properties trên ổ đĩa cục bộ tạm của container, startup có thể hoạt động nhưng restart mất offset; cần persistent volume hoặc một offset store bền khác.

## 11. Spring Boot config và bí mật môi trường

Ví dụ đặt thông số vận hành trong `application.yml`, không lưu credentials thật:

~~~yaml
cdc:
  postgres:
    host: "${CDC_DB_HOST:localhost}"
    port: 5432
    db: appdb
    user: "${CDC_DB_USER}"
    password: "${CDC_DB_PASSWORD}"
  topic-prefix: commerce_source
  publication: commerce_cdc_pub
  slot: commerce_cdc_slot
  offset-file: "${CDC_OFFSET_FILE}"
  tables: "commerce[.]orders,commerce[.]order_outbox"
~~~

`${...}` trong ví dụ sau khi render là Spring property placeholder `$...`; với `CDC_DB_HOST:localhost` có default host phục vụ lab, còn user/password/offset file **bắt buộc** phải được cấp ngoài Git. Trên production, ràng buộc offset store vào lifecycle container/volume và quyền truy cập.

Các biến config nhạy cảm phải được redacted khi log startup. Không in toàn bộ `Properties` ra logs: nó có `database.password`.

## 12. Java config: đưa Debezium Properties vào Spring Integration

Spring Integration hỗ trợ Debezium inbound adapter từ **6.2**. Java DSL `Debezium.inboundChannelAdapter(Properties)` nhận native Debezium connector/Engine settings. Ví dụ có một bean Properties tên cụ thể và một `IntegrationFlow`:

~~~java
package com.example.cdc;

import java.util.Properties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.debezium.dsl.Debezium;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class CommerceCdcConfiguration {

    @Bean("commerceCdcProperties")
    public Properties commerceCdcProperties(
            @Value("${cdc.postgres.host}") String host,
            @Value("${cdc.postgres.port}") int port,
            @Value("${cdc.postgres.db}") String database,
            @Value("${cdc.postgres.user}") String username,
            @Value("${cdc.postgres.password}") String password,
            @Value("${cdc.topic-prefix}") String prefix,
            @Value("${cdc.publication}") String publication,
            @Value("${cdc.slot}") String slot,
            @Value("${cdc.offset-file}") String offsetFile,
            @Value("${cdc.tables}") String tables) {

        Properties props = new Properties();
        props.setProperty("name", "commerce-embedded-cdc");
        props.setProperty("connector.class",
            "io.debezium.connector.postgresql.PostgresConnector");
        props.setProperty("database.hostname", host);
        props.setProperty("database.port", String.valueOf(port));
        props.setProperty("database.dbname", database);
        props.setProperty("database.user", username);
        props.setProperty("database.password", password);
        props.setProperty("plugin.name", "pgoutput");
        props.setProperty("publication.name", publication);
        props.setProperty("publication.autocreate.mode", "disabled");
        props.setProperty("slot.name", slot);
        props.setProperty("topic.prefix", prefix);
        props.setProperty("schema.include.list", "commerce");
        props.setProperty("table.include.list", tables);
        props.setProperty("snapshot.mode", "initial");

        props.setProperty("offset.storage",
            "org.apache.kafka.connect.storage.FileOffsetBackingStore");
        props.setProperty("offset.storage.file.filename", offsetFile);
        props.setProperty("offset.flush.interval.ms", "10000");
        return props;
    }

    @Bean
    public IntegrationFlow commerceCdcInbound(
            @Qualifier("commerceCdcProperties") Properties properties) {
        return IntegrationFlow.from(
                Debezium.inboundChannelAdapter(properties)
                    .contentType("application/json")
                    .enableBatch(false))
            .channel("commerceRawChanges")
            .get();
    }
}
~~~

Đây là ví dụ cấu hình **một embedded Engine**. Connector `debezium-connector-postgres` phải có trên classpath với version tương thích. Bean `commerceRawChanges` cần downstream consumer/subscriber; thường tạo một `@ServiceActivator(inputChannel="commerceRawChanges")` hoặc flow xử lý riêng.

`.contentType("application/json")` mô tả payload JSON serialization mà adapter phát; không dùng setter content type để tự đổi JSON thành Avro/Protobuf. `.enableBatch(false)` phát từng event, dễ phân tích key/value và xử lý lỗi từng message; khi `true`, payload là `List<ChangeEvent>` và không mặc định serializable.

**Không gọi `Pollers.fixedDelay(...)` trên Debezium inbound adapter:** Debezium Engine tự theo stream, không phải JDBC polling message source.

### 12.1. Tránh chạy hai Engines trên cùng slot

Một Spring context không nên đăng ký **hai flow hoặc hai producers** cùng dùng `commerce_cdc_slot` với cùng source offset. Chúng có thể cạnh tranh active replication slot. Nếu muốn một flow có hai consumers, route/broadcast Spring messages **sau một Engine** (ví dụ `PublishSubscribeChannel` có transaction/async semantics rõ), hoặc gửi vào một broker bền vững.

## 13. Handler kiểm tra bảng và operation trước khi xử lý

Một event Spring Integration thường có:
- `Message.getPayload()`: JSON value ở dạng `byte[]` trong single-event JSON byte-array mode; cũng có thể khác ở batch/tombstone/serializer mode.
- `DebeziumHeaders.KEY`: record key, thường là JSON `byte[]`.
- `DebeziumHeaders.DESTINATION`: tên destination logic như `commerce_source.commerce.orders`.

~~~java
package com.example.cdc;

import java.nio.charset.StandardCharsets;
import java.util.Set;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.debezium.support.DebeziumHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class CommerceCdcReceiver {

    private static final Set<String> ALLOWED = Set.of(
        "commerce_source.commerce.orders",
        "commerce_source.commerce.order_outbox");

    @ServiceActivator(inputChannel = "commerceRawChanges")
    public void accept(Message<?> message) {
        Object destinationHeader =
            message.getHeaders().get(DebeziumHeaders.DESTINATION);

        if (!(destinationHeader instanceof String destination)
                || !ALLOWED.contains(destination)) {
            throw new IllegalArgumentException(
                "Unexpected Debezium destination");
        }

        Object value = message.getPayload();
        if (!(value instanceof byte[] bytes)) {
            // Nếu bật enableEmptyPayload(true), tombstone có thể
            // thành Optional.empty(); cần xử lý theo policy riêng.
            throw new IllegalArgumentException(
                "Unexpected payload type");
        }

        // Đoạn lab chỉ hiển thị loại dữ liệu và kích thước,
        // không in JSON raw vì có thể chứa PII.
        System.out.printf(
            "destination=%s, bytes=%d%n", destination, bytes.length);

        String json = new String(bytes, StandardCharsets.UTF_8);
        // Tầng service thật cần parse envelope trước khi route.
        // Tránh log biến json ở production.
        processJson(destination, json);
    }

    private void processJson(String destination, String json) {
        // Validate op, key, schema, then stage inbox/outbox.
    }
}
~~~

**Không biến `DESTINATION` thành tên bảng SQL thông qua string concatenation.** Một allowlist tĩnh và repository có sẵn an toàn hơn. Khi deploy thêm bảng, thay allowlist/message contract có kiểm thử và quản trị thay vì wildcard route vào mọi sink.

### 13.1. Data contract cho từng bảng

| Bảng | Key | Operation hợp lệ | Downstream effect |
|---|---|---|---|
| `commerce.orders` | `id BIGINT` | `r/c/u/d`; `t` nếu connector hỗ trợ | UPSERT/DELETE read model có version guard |
| `commerce.order_outbox` | `event_id UUID` | `c`; `r` khi backfill; `d` nếu cleanup | Publish business event với stable `event_id` |
| `commerce.customer_private` | Không được capture | Không có | Không route/serialize PII |
| Control/transaction topic | Key/value khác row envelope | BEGIN/END hoặc heartbeat | Route riêng, không parse như order row |

Nếu outbox được cleanup bằng DELETE sau publish, raw Debezium capture có thể tạo thêm `d`/tombstone. Downstream outbox publisher nên **chỉ publish op=c/r hợp lệ theo business contract**, không gửi một “EventDeleted” mới vì cleanup. Dùng SMT outbox EventRouter khi muốn map outbox rows thành business events trực tiếp.

## 14. Snapshot modes và hệ quả khi thay bảng capture

| Cấu hình | Ý nghĩa chính | Nguy cơ nếu hiểu sai |
|---|---|---|
| `snapshot.mode=initial` | Snapshot data khi chưa có offset hợp lệ, rồi streaming | Bảng lớn có thể tạo backlog rất lớn |
| `snapshot.mode=no_data` | Không snapshot rows ban đầu, theo streaming semantics | Read model thiếu dữ liệu trước điểm bắt đầu |
| `snapshot.mode=always` | Snapshot mỗi lần startup theo mode hỗ trợ | Có thể phát lại lượng lớn `r` events |
| Incremental snapshot | Backfill theo chunk khi streaming (connector/signal hỗ trợ) | Không tự xảy ra chỉ bằng sửa include list |
| Recovery/schema-only modes | Phục hồi metadata theo connector/version | Không phải cách chung để lấy lại data bị mất |

Debezium PostgreSQL docs mô tả snapshot + streaming với vị trí log nhằm hạn chế bỏ sót changes trong giai đoạn chụp dữ liệu. Tuy nhiên restart/crash trước khi snapshot hoàn tất có thể khiến snapshot lại; consumer phải xử lý duplicate `r` idempotently.

**Thêm bảng mới:** chỉnh `table.include.list` và publication **chưa chắc** phát toàn bộ rows hiện có của bảng đó. Streaming thường chỉ thấy changes sau khi connector bắt đầu capture; nếu muốn backfill, phải chạy initial/incremental snapshot theo cơ chế hỗ trợ hoặc một kế hoạch migration/snapshot có kiểm chứng.

### 14.1. Kế hoạch thêm bảng `commerce.payments`

1. Tạo bảng `commerce.payments` và kiểm tra PK, permissions, replica identity.
2. Cấp `SELECT` cho CDC role và thêm bảng vào publication theo DBA policy.
3. Bổ sung `commerce[.]payments` vào `table.include.list`.
4. Version downstream parser/router và kiểm tra destination allowlist.
5. Chọn incremental snapshot hoặc backfill có kiểm soát cho rows tồn tại trước đó.
6. Kiểm tra order/version/duplicates trong thời gian snapshot và stream giao nhau.
7. Theo dõi snapshot progress, slot WAL retention, lag, error rate.
8. Chỉ đánh dấu rollout hoàn tất khi cả old rows và live changes đã được xử lý.

**Nếu bỏ bảng ra khỏi capture list**, cần xác định sink có giữ bản sao dữ liệu cũ hay cần cleanup; chỉ xóa tên bảng khỏi connector không tự xóa read model đã được dựng trước đó.

## 15. Incremental snapshot và signal table

Một số Debezium connectors hỗ trợ **ad hoc incremental snapshot** thông qua signaling. Ý tưởng là yêu cầu chụp lại dữ liệu của một/bộ bảng mới mà không dừng streaming toàn hệ thống.

Ví dụ **PostgreSQL signal table (chỉ minh họa)**:

~~~sql
CREATE TABLE commerce.debezium_signal (
    id    VARCHAR(100) PRIMARY KEY,
    type  VARCHAR(80) NOT NULL,
    data  VARCHAR(2000)
);

-- Cấu hình tín hiệu tương ứng trên connector trước khi dùng.
INSERT INTO commerce.debezium_signal(id,type,data)
VALUES (
    'snapshot-payments-001',
    'execute-snapshot',
    '{"data-collections":["commerce.payments"],"type":"incremental"}'
);
~~~

Để ví dụ có hiệu lực, connector cần được cấu hình **`signal.data.collection`, các signaling channels được hỗ trợ và publication/capture scope thích hợp**. Không chỉ tạo signal table rồi tự động có snapshot. Với PostgreSQL/logical replication, cần xem liệu signal table đã nằm trong publication hoặc cách connector đọc signal theo tài liệu Debezium version đang dùng.

**Điểm cần kiểm tra:** incremental snapshot chunks, watermark, việc reconcile update đồng thời, heap usage và thứ tự event giữa snapshot với stream. Một read-model consumer phải chịu được `op=r` cho row đã từng nhận `u` từ streaming, thường cần version hoặc reconciliation policy.

## 16. Connection và TLS: connector dùng nhiều hơn JDBC URL

Connector có `database.hostname`/`database.port`/`database.dbname`/credentials, nhưng chúng không mặc định dùng cùng `DataSource` của Spring Boot `JdbcTemplate`. Embedded Debezium Engine tự quản lý nguồn connection/replication channel theo connector.

**Không tưởng rằng `spring.datasource.url` của Spring Boot tự cấu hình Debezium.** Phải chuyển thông số phù hợp vào Debezium `Properties`. Và nếu JDBC sink dùng DB khác, nó cần DataSource/transaction manager riêng.

Ví dụ một số PostgreSQL connector pass-through configs (kiểm tra với Debezium/PgJDBC version):

~~~properties
database.sslmode=verify-full
database.sslrootcert=/etc/cdc-certs/ca.pem
# database.sslcert=/etc/cdc-certs/client.pem
# database.sslkey=/etc/cdc-certs/client-key.pk8
~~~

`verify-full` yêu cầu server certificate hợp lệ với hostname; container phải mount certificate/CA đúng permissions. Các settings SSL khác nhau theo database vendor và driver; không copy `database.sslmode` sang SQL Server/Oracle.

Không cho phép log password, SSL private keys hoặc raw connection properties. Rotate secrets/certs có kế hoạch restart/reconnect, đảm bảo vẫn resume từ offset/slot cũ.

## 17. Offset store của embedded Debezium và lifecycle

Trong ví dụ `FileOffsetBackingStore`:

~~~text
DB WAL  --- LSN A --- LSN B --- LSN C ...
                         |
                  Engine source offset
                         |
                  FileOffsetBackingStore
                         |
                 /var/lib/app/offsets/commerce-cdc.dat
~~~

- Offset file phải ở **persistent volume**, có quyền ghi và backup strategy.
- Flush là định kỳ; engine crash có thể **replay** các events chưa được checkpoint bền.
- Không chuyển file offset giữa unrelated connectors chỉ vì cùng DB.
- Nhiều replicas không dùng chung file offset **đồng thời** như một locking mechanism.
- Replication slot giữ WAL liên quan offset; **slot còn nhưng offset mất**, hoặc **offset còn nhưng WAL/slot mất** đều đòi hỏi kế hoạch recovery.
- Đổi `topic.prefix`, `name`, `slot.name` hoặc source identity có thể ảnh hưởng resume/destination. Không rename tùy tiện giữa deployments.

Các backing stores khác (Kafka/JDBC/Redis theo Debezium modules và phiên bản) có thể phù hợp HA hơn. Nhưng đổi offset storage backend phải có **migration plan**: chỉ sửa `offset.storage` từ file sang DB trong lúc deploy mà không chuyển state cũ có thể khiến Engine hiểu như startup mới.

## 18. MySQL: binlog và schema history không phải PostgreSQL publication

MySQL Debezium connector đọc row changes từ **binary log**, không dùng `pgoutput`, `slot.name` hay PostgreSQL publication.

### 18.1. MySQL server configuration

Ví dụ DBA kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'server_id';
~~~

Cấu hình thường dùng:

~~~ini
# MySQL server / my.cnf (minh họa)
server-id=223344
log_bin=mysql-bin
binlog_format=ROW
binlog_row_image=FULL
binlog_expire_logs_seconds=604800
~~~

`binlog_format=ROW` là tiền đề quan trọng; `binlog_row_image=FULL` hữu ích để có đầy đủ dữ liệu row trong log theo connector contract. Binlog retention phải đủ cho mọi outage dự kiến; tăng retention chỉ sau khi tính disk/backup.

### 18.2. MySQL connector Properties

~~~properties
name=shop-mysql-cdc
connector.class=io.debezium.connector.mysql.MySqlConnector
database.hostname=mysql.internal
database.port=3306
database.user=cdc_reader
database.password=REPLACE_WITH_SECRET

database.server.id=5402
topic.prefix=shop_mysql
database.include.list=shopdb
table.include.list=shopdb[.]orders
snapshot.mode=initial

offset.storage=org.apache.kafka.connect.storage.FileOffsetBackingStore
offset.storage.file.filename=/var/lib/app/offsets/mysql-offset.dat
offset.flush.interval.ms=10000

schema.history.internal=io.debezium.storage.file.history.FileSchemaHistory
schema.history.internal.file.filename=/var/lib/app/offsets/mysql-schema-history.dat
~~~

`database.server.id` phải **không xung đột** với MySQL server/replication clients; nó khác PostgreSQL `slot.name`. `topic.prefix` là logical namespace. `table.include.list` ở MySQL thường dùng định danh `database.table`, không `schema.table` như PostgreSQL.

**Schema history là bắt buộc về mặt kiến trúc MySQL connector**: Debezium cần DDL history để giải mã binlog theo schema đúng thời điểm. File schema history ở trên là lựa chọn **embedded/lab** khi dependency cung cấp `FileSchemaHistory`; nếu ứng dụng dùng Kafka schema history store thì phải cấu hình topic/brokers/security và replication đúng. Offset và schema history là **hai loại state khác nhau**.

Nếu schema history file mất nhưng offset còn, connector có thể không decode changes/khôi phục đúng schema. Không “fix” bằng cách xóa cả hai files mà chưa đánh giá replay/snapshot và kết quả ở sink.

### 18.3. MySQL quyền hạn

Tài khoản CDC thường cần một tập quyền `SELECT`, `REPLICATION SLAVE`/`REPLICATION CLIENT` hoặc tên quyền tương ứng phiên bản, và các quyền snapshot/locking nếu connector cần. Thiết lập chính xác theo MySQL/MariaDB/cloud provider version; không tự cấp `ALL PRIVILEGES` vì nhanh.

## 19. SQL Server: phải enable CDC ở database và từng bảng

Debezium SQL Server connector dùng **SQL Server Change Data Capture**, không phải PostgreSQL WAL logical replication.

Ví dụ do DBA thực hiện:

~~~sql
USE ShopDB;
GO

EXEC sys.sp_cdc_enable_db;
GO

EXEC sys.sp_cdc_enable_table
    @source_schema = N'dbo',
    @source_name = N'orders',
    @role_name = NULL;
GO
~~~

`GO` là **batch separator của SQL tooling** như sqlcmd/SSMS, không phải T-SQL statement JDBC. Khi chạy từ Java, chia commands hoặc dùng migration/DBA script phù hợp.

Khi CDC đã bật, kiểm tra bảng:

~~~sql
SELECT name, is_tracked_by_cdc
FROM sys.tables
WHERE name = 'orders';

SELECT capture_instance, source_object_id, start_lsn
FROM cdc.change_tables;
~~~

Các capture jobs, retention/change tables, SQL Server Agent hoặc dịch vụ tương đương tùy SQL Server/cloud version phải hoạt động. Nếu cleanup xóa change tables trước khi Debezium đọc, **connector không thể khôi phục đầy đủ chỉ từ offset**.

### 19.1. SQL Server connector Properties minh họa

~~~properties
name=shop-sqlserver-cdc
connector.class=io.debezium.connector.sqlserver.SqlServerConnector
database.hostname=sqlserver.internal
database.port=1433
database.user=cdc_reader
database.password=REPLACE_WITH_SECRET
database.names=ShopDB

topic.prefix=shop_sqlserver
table.include.list=dbo[.]orders
snapshot.mode=initial

offset.storage=org.apache.kafka.connect.storage.FileOffsetBackingStore
offset.storage.file.filename=/var/lib/app/offsets/sqlserver-offset.dat
offset.flush.interval.ms=10000
~~~

Đây là **mảnh cấu hình nguồn**, chưa thay thế toàn bộ SQL Server security/TLS và schema history configuration nếu version yêu cầu. Một số Debezium SQL Server versions cần nơi lưu internal schema history riêng. Không áp dụng properties PostgreSQL `plugin.name`/`publication.name`/`slot.name` cho SQL Server.

## 20. Oracle: redo log/LogMiner và quyền khác hẳn

Oracle Debezium connector có thể dùng LogMiner hoặc cơ chế capture được connector version hỗ trợ (ví dụ XStream khi được cấp phép và cấu hình phù hợp). Không có một `wal_level=logical` cho Oracle.

Các bước chuẩn bị thường cần DBA:
- Bật supplemental logging ở database/table theo yêu cầu.
- Xác định `CDB/PDB`, service name và privileges của LogMiner.
- Kiểm tra redo/archive log retention và throughput.
- Chốt connector capture mode, offset/SCN semantics.
- Chọn tables/schemas bằng filter đúng naming.
- Test DDL evolution, LONG/LOB và redo log pressure.
- Bảo mật quyền dictionary và dữ liệu nhạy cảm.

Không cung cấp một script `GRANT DBA` tổng quát cho connector: quyền Oracle khá rộng và khác nhau theo version, cloud service và connector mode. Tài liệu chính thức và DBA phải xác nhận câu lệnh cụ thể.

## 21. Ma trận khác biệt cấu hình theo database

| Ý định | PostgreSQL | MySQL | SQL Server | Oracle |
|---|---|---|---|---|
| Nguồn log | WAL logical decoding | Binlog ROW | CDC change tables/LSN | Redo/LogMiner/SCN |
| Bật capture | `wal_level=logical`, slot, publication | Binary log/ROW | Enable CDC database và table | Supplemental logging, quyền LogMiner |
| Connector | `PostgresConnector` | `MySqlConnector` | `SqlServerConnector` | `OracleConnector` |
| Database chọn | `database.dbname` | `database.include.list` | `database.names` | Connector-specific |
| Table filter | `schema.table` | `database.table` | `schema.table` | `schema.table` theo docs |
| Log identity | LSN + metadata | Binlog file/pos/GTID | Commit/change LSN | SCN/transaction metadata |
| Schema history | Khác MySQL, không sao chép MySQL config | DDL/schema history rất quan trọng | Có thể dùng internal history theo version | Phụ thuộc LogMiner/version |
| Snapshot | Initial/no_data/incremental theo hỗ trợ | Initial/no_data/incremental | Initial/no_data/incremental | Theo connector mode/version |
| Retry/retention | WAL retained by slot | Binlog purge | CDC cleanup retention | Archive/redo retention |

**Chỉ copy các properties chung đã được connector version xác nhận**, không copy toàn bộ file PostgreSQL sang MySQL hoặc SQL Server. Ngay cả các properties có cùng tên cũng có điều kiện và defaults khác nhau.

## 22. Schema evolution: bảng nguồn thay đổi khi connector đang chạy

Các thay đổi schema thường gặp:

| Migration | Rủi ro với connector | Rủi ro consumer |
|---|---|---|
| Thêm nullable column | DDL/cache schema cần cập nhật | Parser có thể bỏ qua hoặc chấp nhận |
| Đổi tên column | Schema mới ảnh hưởng event | Field cũ biến mất |
| Đổi datatype `INT → BIGINT` | Connector/converter thay logical type | Overflow nếu cast `int` |
| Đổi PK | Record key format đổi | Partition/dedupe/rekey lỗi |
| Xóa table | Publication/history/capture mismatch | Consumer giữ dữ liệu cũ |
| Thêm table | Publication/filter chưa cập nhật | Missing initial rows |
| Bật `REPLICA IDENTITY FULL` | WAL tăng | More before image/PII |
| Thay `topic.prefix` | Destination đổi | Router/subscriptions nhận khác |
| Đổi outbox payload schema | Business events mới/old mixed | Cần versioned contracts |

Quy trình migration gợi ý:
1. **Expand:** thêm cột/bảng theo hướng backward compatible; cấp quyền.
2. **Connector config:** update publication/filter/offset/history theo plan.
3. **Consumer:** hỗ trợ cả schema cũ và mới, contract tests/golden events.
4. **Backfill:** incremental snapshot hoặc migration command có idempotency.
5. **Monitor:** snapshots, WAL/binlog lag, error rates, backlog.
6. **Contract:** chỉ remove field cũ khi tất cả consumers đã nâng cấp.

**Đổi `topic.prefix` hoặc offset identity không phải thao tác rename vô hại.** Khi deployment thay đổi namespace, việc resume và routing events cần kế hoạch dữ liệu.

## 23. Transactional outbox: thiết kế bảng để Debezium đọc đúng business event

Raw CDC của bảng `orders` thường chỉ nói một row đã thay đổi, không diễn giải lý do nghiệp vụ. Với các message phải phát Kafka/JMS an toàn, có thể ghi **outbox row trong chính transaction cập nhật đơn hàng**.

~~~sql
-- Ví dụ PostgreSQL; :orderId, :eventId, :newVersion...
-- được bind từ PreparedStatement/NamedParameterJdbcTemplate ở Java.
BEGIN;

UPDATE commerce.orders
SET status = 'PAID',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND version = :expectedVersion;

-- Service phải xác nhận UPDATE ảnh hưởng đúng 1 row.
-- Nếu không, ROLLBACK thay vì INSERT outbox.

INSERT INTO commerce.order_outbox (
    event_id, aggregate_id, aggregate_ver, event_type, payload_json
) VALUES (
    :eventId, :orderId, :newVersion,
    'order.paid',
    CAST(:payloadJson AS jsonb)
);

COMMIT;
~~~

**Cảnh báo cho ví dụ SQL:** `BEGIN/COMMIT` là pseudo transaction block để dễ đọc; khi Spring quản lý local JDBC transaction, để `@Transactional`/`TransactionTemplate` commit và không lồng thêm JDBC `BEGIN` bằng tay. `:newVersion` phải phản ánh version thực đã UPDATE, không tự cộng từ một snapshot lỗi; dùng `UPDATE ... RETURNING version` hoặc kiểm soát version trong service theo transaction.

Ở Debezium source side:
- Publication và `table.include.list` phải chứa `commerce.order_outbox`.
- Connector phát event `c` với `after.event_id` và `after.payload_json` (theo serialization).
- Downstream publish **event ID ổn định**, không tạo UUID mới khi redelivery.
- Nếu snapshot lại table outbox, `op=r` có thể đưa lại event đã publish; consumer phải dedupe.
- Nếu có dọn bảng outbox định kỳ, `d` và tombstone là sự kiện housekeeping, không tự là một domain event mới.

### 23.1. Dùng Outbox Event Router SMT khi hợp đồng phù hợp

Debezium có **Outbox Event Router SMT** để chuyển outbox row thành message business với ID, key, type và payload. Các cột bảng của ví dụ này (`event_id`, `aggregate_id`, `payload_json`) **khác defaults** của SMT, vì vậy cần mapping properties tương ứng hoặc đổi schema theo outbox event router contract.

Không cấu hình `transforms.outbox.*` mà chưa đối chiếu version/column mapping; một SMT cấu hình sai có thể route sai destination hoặc bỏ key, và parser raw CDC còn mong `before/after` sẽ không dùng được sau transform.

## 24. Khi nào đọc trực tiếp bảng orders, khi nào đọc bảng outbox?

| Nhu cầu | Raw `orders` CDC | `order_outbox` CDC |
|---|---|---|
| Rebuild một read model hiện trạng | Phù hợp với snapshot + upsert | Tùy event coverage; có thể không đầy đủ state |
| Đồng bộ cache/search index | Phù hợp nếu schema ổn định | Phù hợp khi business event chứa đủ projection data |
| Gửi `OrderPaid` event cho services ngoài | Khó suy từ UPDATE nguyên nhân nghiệp vụ | Rõ event type/contract/version |
| Xử lý DELETE | Thấy `op=d`/tombstone theo connector | Cần business deletion event nếu quan trọng |
| Schema DB thay đổi thường xuyên | Consumer bị ảnh hưởng trực tiếp | Business event contract độc lập hơn |
| PII trong row | Nguy cơ phát tán cột mới | Chủ động chọn dữ liệu event |
| Replay và idempotency | Cần source position/aggregate version | `event_id` ổn định/UNIQUE |

Có thể dùng **hai luồng riêng**: một table capture cho raw materialized view, một outbox table cho integration events; đừng phát tất cả raw `orders` changes tới partner ngoài mà không có data classification và semantic contract.

## 25. Offset, snapshot, publication, slot: thứ tự khởi động an toàn

Quy trình triển khai một connector PostgreSQL mới:

~~~mermaid
flowchart TD
    A["DBA kiểm tra wal_level và slots"] --> B["Tạo tables + PK + publication"]
    B --> C["Cấp replication + SELECT permissions"]
    C --> D["Provision durable offset store + secrets"]
    D --> E["Deploy một active Engine"]
    E --> F["Initial snapshot"]
    F --> G["Continuous WAL streaming"]
    G --> H["Monitor lag, slot WAL, downstream inbox"]
    H --> I["Graceful shutdown / restart"]
    I --> G
~~~

**Preflight deployment checklist:**
1. `wal_level=logical` và capacity slots/senders đúng.
2. Bảng có PK; `REPLICA IDENTITY` và dữ liệu `before` phù hợp.
3. Publication thực sự có các bảng đã khai báo.
4. CDC role có kết nối, SELECT, replication; TLS/certificates đúng.
5. `slot.name` không bị engine khác chiếm.
6. `topic.prefix` và `name` duy nhất, ổn định qua rollout.
7. Snapshot mode được chốt theo chuyện có/không dữ liệu trước deploy.
8. Offset store có quyền ghi và dữ liệu tồn tại qua restart.
9. Downstream có allowlist, parser, durable inbox và idempotency.
10. SLO cho source lag, backlog, WAL retained bytes và retry đã được đặt.

**Một thay đổi bảng hoặc filter trong ứng dụng không thay thế bước kiểm tra publication của DBA.**

## 26. High availability: single-reader ownership và scale downstream

Với PostgreSQL một logical replication slot được consume active bởi một client tại một thời điểm trong mô hình thông thường. Ba Spring Boot pods cùng auto-start một `DebeziumMessageProducer` dùng một slot sẽ **không** được chia jobs theo cơ chế Spring Integration poller.

~~~text
DB PostgreSQL logical replication
            |
        commerce_cdc_slot
            |
       One active Engine/leader
            |
        Durable broker/inbox
          /    |    \
    worker A worker B worker C
~~~

**Lựa chọn:** một leader chạy connector, standby không start Engine cho đến khi quyền sở hữu được chuyển an toàn; hoặc chuyển connector sang Kafka Connect/Debezium Server cho orchestration riêng. Downstream có thể scale theo broker partitions/queue, không nhất thiết scale số connections vào cùng slot.

Một Engine **mỗi pod với các slots khác nhau** không phải load balancing: mỗi slot có thể nhận **cùng row changes** từ source, tăng storage pressure và duplicates downstream. Có use case chạy pipelines độc lập với slots riêng, nhưng phải hiểu chúng là các subscribers khác nhau.

### 26.1. Failover checklist

- Stop old leader/đảm bảo nó mất quyền trước khi standby start Engine.
- Duy trì slot/offset identity hợp lệ hoặc kế hoạch khôi phục có đối soát.
- Kiểm tra connector thực sự stream tiếp sau snapshot/recovery.
- Dedupe events có thể replay qua failover.
- Đánh giá replication slot behavior khi PostgreSQL primary failover (khả năng đồng bộ slots tùy PG/cloud version).
- Không tự động drop slot chỉ vì standby không connect được vài giây.

## 27. Backpressure, fetch/batch và connector throughput

Debezium có tham số quản lý connector queue/batch/heartbeat, tùy connector version. Ví dụ properties phổ biến có thể gồm:

~~~properties
max.batch.size=2048
max.queue.size=8192
poll.interval.ms=500
heartbeat.interval.ms=10000
~~~

**Chỉ là giá trị minh họa**; không copy vào mọi connector mà không kiểm tra defaults và constraints của Debezium version. `max.queue.size` thường phải lớn hơn `max.batch.size` theo các ràng buộc connector; các thông số này tác động bộ nhớ và throughput của Debezium Engine, **không giống** `maxMessagesPerPoll` của JDBC inbound adapter.

Nếu downstream `DirectChannel` handler ghi JDBC lâu, Engine callback có thể bị chậm; nếu chuyển sang `ExecutorChannel`, phải có bounded executor và durable inbox trước khi coi event đã được xử lý bền vững. Không dùng queue RAM không giới hạn để che độ trễ broker/DB.

**Một câu hỏi vận hành:** khi sink Kafka down một giờ, nguồn PostgreSQL vẫn ghi 10.000 rows/s, hệ thống sẽ giữ pending data ở đâu và backlog bao lâu? Cần tính WAL retention, Engine queue, persistent inbox, disk quotas và SLA; không chỉ tăng `max.queue.size` vô hạn.

### 27.1. Heartbeat không phải business change event

Debezium connector có heartbeat để giúp cập nhật offsets/monitor liveness khi bảng capture ít thay đổi. Heartbeat có destination/payload semantics khác row envelope `before/after/op`; consumer không nên route mọi heartbeat vào handler `orders` rồi báo “missing op” như lỗi dữ liệu. Với PostgreSQL ít events nhưng WAL lớn từ các bảng khác, heartbeat/slot monitoring là yếu tố vận hành quan trọng theo cấu hình/version.

## 28. Quan sát vận hành bằng SQL và metrics

| Tín hiệu | Nguồn | Điều cần hiểu |
|---|---|---|
| `pg_replication_slots.active` | PostgreSQL | Slot có consumer đang đọc |
| `restart_lsn` | PostgreSQL | WAL tối thiểu cần giữ liên quan slot |
| `confirmed_flush_lsn` | PostgreSQL | Phần WAL đã được consumer xác nhận |
| `pg_wal_lsn_diff(...)` | PostgreSQL | Ước lượng WAL retention bytes |
| Snapshot state/duration | Debezium metrics | Đang snapshot hay streaming |
| Events/s theo table/op | Spring Integration metrics | Capture scope đúng và throughput |
| Source→process latency | Debezium timestamp metadata | Connector lag (khác downstream end-to-end) |
| Inbox oldest pending | Application DB | Sink xử lý chậm |
| Outbox publish retry | Kafka/JMS outbound | Broker/sink delivery failure |
| Offset flush success/failure | Engine/offset store | Khả năng resume |
| CDC user permission errors | Logs/connector status | Setup hoặc secret rotation sai |
| Schema history errors | MySQL/SQL Server connector | Không decode được log theo đúng schema |

Query hữu ích để kiểm tra publications và slots:

~~~sql
SELECT pubname, schemaname, tablename
FROM pg_publication_tables
WHERE pubname='commerce_cdc_pub'
ORDER BY schemaname, tablename;

SELECT slot_name, active, restart_lsn, confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_name='commerce_cdc_slot';
~~~

**Không dùng `pg_wal_lsn_diff` làm thước đo business event đã publish Kafka**. Việc tiến offset nguồn, inbox commit, outbox send và consumer ACK là những mốc khác nhau.

### 28.1. Một số alert đáng có

- Slot inactive liên tục khi source còn có business writes.
- `retained_wal_bytes` vượt ngưỡng vận hành/đĩa và tăng nhanh.
- Snapshot kéo dài bất thường hoặc restart/snapshot lặp lại.
- Source events/s giảm còn zero không phù hợp hoạt động DB.
- Capture destination ngoài allowlist (có thể filter/publication sai).
- Parser schema errors sau migration.
- Offset store không flush được và Event replay tăng mạnh.
- Outbox/inbox backlog hoặc oldest pending age vượt SLA.

Tránh tag metrics theo `orderId`/`eventId` có cardinality vô hạn; đưa IDs vào traces/logs có phân quyền và masking.

## 29. Cấu hình bảo mật, masking và phân quyền dữ liệu

**CDC có thể sao chép cả dữ liệu cũ lẫn mới của row**, vì vậy chỉ tạo publication và `table.include.list` là chưa đủ nếu bảng chứa PII/secrets.

~~~text
Database table -> Publication -> Debezium filter/SMT -> MessageChannel -> Sink
    ^               ^                  ^                    ^
  Data owner       DBA              Security rules      Consumer policy
~~~

Checklist:
- Capture chỉ bảng cần thiết; tách `customer_private` ra khỏi publication.
- Dùng `column.exclude.list`/column masking theo converter để bỏ fields không cần thiết.
- Bảo vệ cả `before` image khi `REPLICA IDENTITY FULL`.
- Không đặt passwords, SSL private keys hoặc raw `Properties` trong logs.
- Dùng TLS verification và secret manager.
- Dùng allowlist destination; không tạo SQL động từ message headers.
- Quy định data retention/erasure trong Kafka, inbox, outbox, DLQ, snapshots, backup.
- Kiểm tra migrations thêm cột nhạy cảm (wildcard capture có thể vô tình xuất dữ liệu).
- Kiểm tra `topic.prefix` và event routing không lộ tenant names/customer IDs.
- Xác minh CDC role chỉ có quyền SELECT/REPLICATION cần thiết; service consumer không cần database superuser.

**Column filtering xảy ra ở connector/event serialization stage, không làm dữ liệu biến mất khỏi WAL hoặc ngăn DB ghi column.** Các yêu cầu compliance mạnh có thể đòi thay đổi source schema/outbox contract hoặc encryption/tokenization trước lưu nguồn.

## 30. Troubleshooting theo triệu chứng

| Triệu chứng | Kiểm tra đầu tiên | Hướng khắc phục |
|---|---|---|
| Engine startup `ClassNotFoundException` | Debezium connector/version/dependencies | Thêm đúng connector và align BOM |
| Kết nối được DB nhưng không CDC | `wal_level`, role REPLICATION, publication/slot | Sửa setup DB và restart an toàn |
| Có snapshot `r` nhưng không có `c/u/d` | Publication, slot active, WAL/logical streaming | Kiểm tra connector logs/DB |
| Không có bảng mới | Publication chưa thêm, include regex sai | Sửa cả publication/filter; backfill |
| Nhận bảng không mong muốn | Include regex rộng, publication all tables | Siết filters, review dữ liệu đã phát |
| Event DELETE thiếu before fields | `REPLICA IDENTITY`, key contract | Dùng key/version hoặc FULL có cân nhắc |
| Slot `already active` | Engine khác đang consume | Xác minh leader ownership, không drop slot |
| WAL disk tăng liên tục | Slot lag, Engine down, sink chậm | Monitor/recover safely, không xóa mù |
| MySQL schema history fail | File/topic history mất, sai permissions | Khôi phục state theo runbook |
| SQL Server không có changes | CDC chưa enable database/table, jobs | Bật CDC/kiểm tra cleanup retention |
| Offset file mất sau deploy | Ephemeral volume, sai mount | Restore/backfill, dùng durable store |
| Sau restart phát lại nhiều events | Offset flush/downtime/re-snapshot | Idempotent consumer/outbox |
| Consumer JSON parse sai | Converter/SMT/schema evolution | Test bytes thực, version parser |
| `topic.prefix` đổi bất ngờ | Config drift/deployment | Reconcile destination/routing/migration |
| TLS handshake fail | CA/hostname/client cert | Đối chiếu SSL mode/certificate |
| Lag tăng khi DB writes bình thường | Slow handler, bounded queue, WAL retention | Scale downstream và tune có đo lường |

**Không chạy script xóa replication slot hoặc offset file như một “retry” vô hại.** Đây là dữ liệu trạng thái của CDC; mất state có thể đòi full snapshot hoặc đối soát thủ công.

## 31. Kiểm thử cấu hình ở mức đơn vị

Không cần PostgreSQL để test việc tạo Properties:

~~~java
package com.example.cdc;

import static org.junit.jupiter.api.Assertions.*;
import java.util.Properties;
import org.junit.jupiter.api.Test;

class CommerceCdcPropertiesTest {

    @Test
    void capturesOnlyAllowedTables() {
        CommerceCdcConfiguration config =
            new CommerceCdcConfiguration();

        Properties p = config.commerceCdcProperties(
            "localhost", 5432, "appdb", "testuser",
            "testpass", "commerce_source",
            "commerce_cdc_pub", "commerce_cdc_slot",
            "/tmp/cdc-test-offset.dat",
            "commerce[.]orders,commerce[.]order_outbox");

        assertEquals(
            "io.debezium.connector.postgresql.PostgresConnector",
            p.getProperty("connector.class"));
        assertEquals("pgoutput", p.getProperty("plugin.name"));
        assertEquals("disabled",
            p.getProperty("publication.autocreate.mode"));
        assertEquals(
            "commerce[.]orders,commerce[.]order_outbox",
            p.getProperty("table.include.list"));
        assertEquals("commerce_cdc_slot",
            p.getProperty("slot.name"));
    }
}
~~~

Đây là **unit test mapping Properties**, không chứng minh DB role có quyền, publication chứa tables, slot tồn tại, offset store writable hoặc Engine đọc được events. Không commit `testpass` trong production config; chỉ là fake test fixture.

### 31.1. Test lọc destination downstream

Nên tạo các messages giả với:
- `DebeziumHeaders.DESTINATION="commerce_source.commerce.orders"` → cho phép.
- `...order_outbox` → cho phép và route khác.
- `...customer_private` → từ chối/quarantine.
- Thiếu destination/đổi `topic.prefix` → từ chối có metrics, không SQL concat.
- Bảng mới `commerce.payments` trước khi consumer được cập nhật → phát hiện rõ.

Kiểm tra consumer không phát tán raw JSON có PII khi ném exception; dùng test logger/redaction nếu hệ thống có cơ chế kiểm thử.

## 32. Integration test PostgreSQL với Testcontainers (khung tham khảo)

**Yêu cầu**: chạy PostgreSQL có `wal_level=logical`, tạo bảng/publication/CDC role và offset store riêng. Với Spring Integration inbound producer, Engine chạy bất đồng bộ, nên test cần chờ conditions thay vì `Thread.sleep(1000)`.

~~~java
// Template Testcontainers 2.x, không phải test class hoàn chỉnh.
// Requires modules: testcontainers-postgresql, testcontainers-junit-jupiter.
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

@Testcontainers
class CommercePostgresCdcIT {

    @Container
    static final PostgreSQLContainer postgres =
        new PostgreSQLContainer("postgres:16-alpine")
            .withDatabaseName("appdb")
            .withUsername("testuser")
            .withPassword("testpass")
            .withCommand("postgres",
                "-c", "wal_level=logical",
                "-c", "max_replication_slots=5",
                "-c", "max_wal_senders=5");

    @Test
    void checksPublicationAndChangeEvents() {
        // 1. Seed tables + CREATE PUBLICATION qua DB admin.
        // 2. Cấp quyền CDC, tạo unique slot/offset path.
        // 3. Start Debezium IntegrationFlow/test probe.
        // 4. INSERT/UPDATE/DELETE commerce.orders.
        // 5. Await op=c/u/d và key/destination đúng.
        // 6. Shutdown Engine, cleanup slot/offset after test.
    }
}
~~~

**Chú ý:** image/testuser setup có thể cấp quyền khác production; dùng admin connection cho việc tạo publication/role trong test, CDC connection cho streaming. Testcontainers 1.x dùng module/imports khác (`org.testcontainers.containers.PostgreSQLContainer<?>`); không trộn 1.x và 2.x. Không chạy hai tests song song với cùng `slot.name`/offset file trừ khi đang chủ động kiểm tra collision.

### 32.1. Test matrix quan trọng

| Test | Kỳ vọng |
|---|---|
| Initial snapshot | Nhận `r` cho `orders` hiện có |
| INSERT/UPDATE/DELETE | Nhận `c/u/d` cho bảng được capture |
| Bảng ngoài `table.include.list` | Không phát raw CDC message vào app |
| Bảng có trong filter nhưng ngoài publication | Không stream changes, có cảnh báo config mismatch |
| Bảng mới thêm vào publication/filter | Stream được; old data cần backfill |
| `REPLICA IDENTITY DEFAULT` vs FULL | Before image khác theo DB contract |
| Change column type | Parser/schema migration xử lý đúng |
| Restart Engine với offset store còn | Resume và có thể replay có kiểm soát |
| Mất offset nhưng slot còn | Runbook resnapshot/reconcile |
| Slot bị active bởi Engine khác | Startup/failover được phân loại rõ |
| Outbox INSERT trong business transaction | CDC có stable event ID |
| Consumer nhận duplicate | Idempotency ngăn repeated business effect |
| Sink tạm outage | Backpressure/lag đo được; không OOM |
| MySQL history file bị mất | Kịch bản recovery có bản sao/plan |
| SQL Server CDC disabled | Test phát hiện thiếu setup và hướng dẫn DBA |
| Dữ liệu nhạy cảm trong bảng exclude | Không tới downstream logs/message sink |

## 33. Bài thực hành

1. Tạo `commerce.orders` và `commerce.order_outbox` trên PostgreSQL, xác định primary keys và unique event ID.
2. Ghi một business transaction UPDATE `orders` và INSERT `order_outbox`, xác minh rollback cả hai khi lỗi.
3. Bật `wal_level=logical`, kiểm tra `max_replication_slots` và `max_wal_senders` với DBA.
4. Cấp CDC role quyền CONNECT/USAGE/SELECT/REPLICATION theo lab.
5. Tạo publication `commerce_cdc_pub` chỉ chứa hai bảng, query `pg_publication_tables` để xác nhận.
6. Tạo hoặc cho Debezium tự tạo replication slot `commerce_cdc_slot` theo policy, kiểm tra `pg_replication_slots`.
7. Đặt `table.include.list=commerce[.]orders,commerce[.]order_outbox` và `schema.include.list=commerce`.
8. Thử regex `commerce.orders` không escape dấu chấm, giải thích nguy cơ match quá rộng.
9. Thử `column.exclude.list` bỏ `customer_id`, xác minh không xuất hiện trong events; kiểm tra `REPLICA IDENTITY FULL`.
10. Cấu hình Embedded Engine `Properties`, dùng Spring Integration `Debezium.inboundChannelAdapter`.
11. Viết Spring Boot `application.yml` đọc CDC secrets từ biến môi trường.
12. Viết `@ServiceActivator` nhận `DebeziumHeaders.DESTINATION` và allowlist các bảng.
13. Chạy snapshot initial, nhận `op=r`; thực hiện INSERT/UPDATE/DELETE và kiểm tra `op=c/u/d`.
14. Thử `snapshot.mode=no_data` trên DB lab mới; phân biệt không backfill old rows.
15. Tạo bảng mới `commerce.payments`, chỉ sửa `table.include.list` mà không sửa publication; quan sát lỗi cấu hình/thiếu events.
16. Bổ sung `payments` vào publication, cấp SELECT, cập nhật consumer allowlist rồi chạy backfill phù hợp.
17. Tạo signal table, cấu hình `signal.data.collection` và thực hành incremental snapshot trong connector version hỗ trợ.
18. So sánh `REPLICA IDENTITY DEFAULT` với FULL, đo size `before` image, WAL retained bytes.
19. Restart container với offset file trên volume bền; xác minh resume.
20. Xóa offset file **chỉ trên test đã backup**, đánh giá snapshot/replay.
21. Dừng Engine một khoảng, dùng `pg_wal_lsn_diff` đo WAL retention, khởi động lại và theo dõi lag giảm.
22. Tạo hai Spring Boot instances cùng slot, chứng minh không phải load balancing đúng.
23. Cấu hình leader/standby, bảo đảm một active Engine và trạng thái offset phù hợp.
24. Bật TLS `database.sslmode=verify-full` trong môi trường có certs; thử lỗi hostname/CA để thấy kiểm tra bảo mật.
25. Đặt sink chậm phía sau `DirectChannel` và so sánh với bounded `ExecutorChannel` + durable inbox.
26. Xây outbox EventRouter SMT trên một flow riêng, map cột thực tế và kiểm tra downstream business event ID.
27. Cấu hình MySQL binlog ROW/FULL, `database.server.id` riêng, và schema history store bền.
28. Với SQL Server, enable CDC ở database/table rồi kiểm tra `sys.tables.is_tracked_by_cdc`.
29. Viết unit test Properties và contract filter/destination, không cần DB thật.
30. Viết integration test PostgreSQL Testcontainers với publication/slot/offset cô lập, chờ async event đúng.
31. Mô phỏng lỗi schema migration đổi tên cột, kiểm tra parser versioning và golden events.
32. Tạo dashboard source lag, snapshot progress, slot WAL retention, inbox/outbox backlog, connector errors.
33. Viết recovery runbook cho slot bị drop, offset file mất, MySQL schema history thiếu và SQL Server CDC cleanup.
34. Đánh giá data governance: table whitelist, column masking, secrets, PII trong `before`/`after` và DLQ.

**Tình huống tổng hợp:** hệ thống bán hàng dùng hai Spring Boot pods để chạy embedded Debezium, PostgreSQL đã có `orders`, `order_outbox`; DBA mới tạo `payments` và đổi cột `customer_id`. Pod A đang consume `commerce_cdc_slot` nhưng bị kill sau khi gửi một event Kafka; pod B khởi động với offset file trống. WAL retention tăng và downstream gặp schema mismatch. Hãy thiết kế **publication/filter migration, leader failover, offset recovery, incremental snapshot, outbox idempotency, schema versioning, bảo mật và metrics**, rồi lập ma trận test các crash windows trước khi rollout.

## 34. Tài liệu tham khảo

- [Spring Integration Reference — Debezium Support](https://docs.spring.io/spring-integration/reference/debezium.html): `DebeziumMessageProducer` và `Debezium.inboundChannelAdapter(Properties)`, headers, batch, lifecycle.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): Direct/Executor/QueueChannel và tác động tới xử lý đồng bộ.
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): local transaction và giới hạn async boundary.
- [Debezium Documentation — PostgreSQL Connector](https://debezium.io/documentation/reference/stable/connectors/postgresql.html): role, publication, slot, snapshot, table/column filters, replica identity, WAL retention.
- [Debezium Documentation — MySQL Connector](https://debezium.io/documentation/reference/stable/connectors/mysql.html): binlog, server ID, schema history và capture filters.
- [Debezium Documentation — SQL Server Connector](https://debezium.io/documentation/reference/stable/connectors/sqlserver.html): enable CDC ở DB/bảng, capture jobs, schema/table filters.
- [Debezium Documentation — Oracle Connector](https://debezium.io/documentation/reference/stable/connectors/oracle.html): supplemental logging, LogMiner, redo/SCN và permissions.
- [Debezium Documentation — Debezium Engine](https://debezium.io/documentation/reference/stable/development/engine.html): Engine embedded, offset store, `ChangeEvent`, lifecycle và serialization.
- [Debezium Documentation — Storage Configuration](https://debezium.io/documentation/reference/stable/configuration/storage.html): file/Kafka/JDBC backing store và schema history.
- [Debezium Documentation — Incremental Snapshots](https://debezium.io/documentation/reference/stable/configuration/signalling.html): signaling channels và snapshot requests.
- [Debezium Documentation — Outbox Event Router SMT](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): mapping outbox events và message routing.
- [PostgreSQL Documentation — Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html): publications, replication slots và logical decoding.
- [PostgreSQL Documentation — pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html): slot `active`, `restart_lsn`, `confirmed_flush_lsn` và WAL retention.
- [PostgreSQL Documentation — Replica Identity](https://www.postgresql.org/docs/current/sql-altertable.html): `REPLICA IDENTITY` tác động UPDATE/DELETE images.
- [Microsoft Learn — Enable and Disable CDC](https://learn.microsoft.com/en-us/sql/relational-databases/track-changes/enable-and-disable-change-data-capture-sql-server): `sys.sp_cdc_enable_db` và `sys.sp_cdc_enable_table`.
- [Testcontainers Java Documentation](https://java.testcontainers.org/modules/databases/postgres/): thiết lập PostgreSQL container để test integration.

> **Ghi nhớ:** cấu hình **database table và Debezium connector** là một hợp đồng hai phía. PostgreSQL cần **bảng có key, quyền, publication, replication slot và WAL**, connector cần **table filters, snapshot, offset store và version phù hợp**; Spring Integration nhận events qua `Debezium.inboundChannelAdapter(...)` rồi route vào `MessageChannel`. MySQL, SQL Server và Oracle dùng log/CDC/history khác, không thể copy Properties nguyên xi. Để rollout an toàn phải kiểm soát **snapshot/backfill, schema evolution, một active reader, persistent offsets, WAL retention, outbox/idempotency và data governance**.


