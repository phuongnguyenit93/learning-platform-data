# Batch update và hiệu năng trong Spring Integration JDBC

## 1. Vì sao xử lý từng message có thể làm database quá tải?

Giả sử một ứng dụng thương mại điện tử nhận 50.000 thay đổi tồn kho từ Kafka trong một khoảng ngắn. Mỗi thay đổi phải cập nhật bảng `inventory_projection` qua Spring Integration JDBC. Nếu mỗi message lập tức tạo một lệnh `UPDATE` riêng và phải trao đổi với database, hệ thống tiêu thụ nhiều round trips, nhiều lượt bind tham số và thời gian giữ connection. Khi lưu lượng tăng, backlog có thể tích tụ ở `MessageChannel` hoặc broker.

Một giải pháp là **gom nhiều cập nhật trong một lần thực thi batch**. Tuy nhiên, từ “batch” có ít nhất ba nghĩa rất khác nhau:

1. **Batch message**: một `Message<List<UpdateCommand>>` chứa nhiều phần tử.
2. **JDBC batch**: gọi `PreparedStatement.addBatch()` rồi `executeBatch()` (hoặc Spring JDBC `batchUpdate()`) để thực thi **một SQL template với nhiều bộ tham số**.
3. **Set-based SQL**: một câu `UPDATE ... WHERE id IN (:ids)` thay đổi nhiều hàng bằng **một statement**, không nhất thiết gọi JDBC `executeBatch()`.

Trong Spring Integration, phân biệt ba lớp này là chìa khóa tối ưu đúng và không đánh đổi dữ liệu lấy throughput.

~~~mermaid
flowchart LR
    A["Kafka/JMS/HTTP hoặc JDBC inbound"] --> B["MessageChannel"]
    B --> C["Gom/giữ payload List<Command>"]
    C --> D["JDBC outbound adapter"]
    D --> E["PreparedStatement batchUpdate"]
    E --> F[("Database")]
    F --> G["Commit / rollback"]
~~~

Bài học **Batch update và hiệu năng** thuộc chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**: kết nối các hệ thống ngoài vào Spring Integration qua inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; quản lý message contract, lỗi và vòng đời kết nối. Chủ đề này tập trung vào **batch SQL, transaction, row counts, hiệu năng đo được, retry và idempotency**.

**Mục tiêu sau bài:** nhận biết chính xác khi nào Spring Integration thật sự gọi JDBC batch; viết Java DSL/XML, dùng `JdbcTemplate`/`NamedParameterJdbcTemplate`, chọn batch size, đo bottleneck, và xử lý lỗi/rollback trong môi trường có nhiều workers.

## 2. Ba tầng batching không tương đương

| Tầng | Đơn vị gom | API/ví dụ | Điều nó không tự bảo đảm |
|---|---|---|---|
| Message | `List<Command>` trong một payload | Aggregator, polling result list | Database dùng batch API |
| JDBC | Nhiều parameter sets cho **cùng SQL** | `JdbcMessageHandler` với `Iterable`; `JdbcTemplate.batchUpdate` | Atomic cross-system commit |
| SQL set-based | Một statement xử lý nhiều rows | `UPDATE ... WHERE id IN (:ids)` | Nhận per-row outcome chi tiết |
| DB load | Bulk insert, staging table, vendor COPY | PostgreSQL COPY, bulk loader | Dùng được trên mọi JDBC adapter |
| Polling | Nhiều rows từ một SELECT | JDBC inbound `maxRows`, SQL LIMIT | Sẽ được gửi thành nhiều messages nếu không split |
| Transaction | Nhóm DML commit/rollback | `@Transactional` hoặc transactional poller | Broker Kafka/JMS cũng commit cùng DB |

Một ví dụ về lượng thao tác:

~~~text
100 Message<UpdateCommand>
    -> handler chạy từng message: có thể tạo 100 SQL executions

1 Message<List<UpdateCommand>> có 100 phần tử
    -> JdbcMessageHandler nhận Iterable:
       một batchUpdate cho 100 bộ tham số

1 Message<List<Long>> chứa 100 IDs
    -> UPDATE ... WHERE id IN (:ids):
       một SQL statement có 100 IDs, không phải JDBC batch 100 entries
~~~

**“Một message chứa 100 phần tử” không tự đồng nghĩa “một database transaction”.** Transaction phụ thuộc nơi mở, transaction manager, thread/channel và cách exception được xử lý.

## 3. Kiến trúc tham chiếu: đọc, biến đổi, ghi batch

~~~mermaid
sequenceDiagram
    participant P as JDBC poller
    participant DB as Source database
    participant T as Transformer
    participant H as JdbcMessageHandler
    participant OUT as Target database
    P->>DB: SELECT tối đa N rows
    DB-->>P: List<SourceRow>
    P->>T: Message<List<SourceRow>>
    T-->>H: Message<List<UpdateCommand>>
    H->>OUT: batchUpdate SQL với N parameter sets
    OUT-->>H: Batch result / exception
    Note over H,OUT: Cần transaction để rollback khi có lỗi
~~~

Một pipeline giữ được `List` từ inbound tới outbound có thể tận dụng **Iterable batch** trực tiếp. Nếu chèn `Splitter` ngay trước JDBC outbound, mỗi phần tử trở thành **một message** và handler thường chỉ thấy payload đơn; khi đó không còn auto-batch của `JdbcMessageHandler` theo từng message.

Ngược lại, nếu mỗi message cần xử lý độc lập hoặc mỗi row phải có reply/ACK riêng, splitter vẫn có thể đúng về nghiệp vụ. Không “gom để nhanh” bằng cách xóa bỏ những ranh giới lỗi quan trọng.

## 4. Schema và dữ liệu thực hành

Ví dụ dùng Java 17+, Spring Boot, Spring Integration JDBC, Spring JDBC. Dùng BOM/Spring Boot dependency management thay vì tự ghép các phiên bản Spring không tương thích.

~~~groovy
// build.gradle - mảnh dependencies của ứng dụng thực hành
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml: H2 chỉ dùng cho test và demo cơ bản.
spring:
  datasource:
    url: "jdbc:h2:mem:jdbc_batch_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
  sql:
    init:
      mode: always
~~~

Giả sử ứng dụng thực hành đặt DDL trong `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE inventory_projection (
    item_id       BIGINT NOT NULL PRIMARY KEY,
    quantity      INTEGER NOT NULL,
    version       INTEGER NOT NULL DEFAULT 0,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE incoming_inventory_change (
    id            BIGINT NOT NULL PRIMARY KEY,
    event_id      VARCHAR(80) NOT NULL UNIQUE,
    item_id       BIGINT NOT NULL,
    target_qty    INTEGER NOT NULL,
    state         VARCHAR(24) NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory_outbox (
    event_id      VARCHAR(80) NOT NULL PRIMARY KEY,
    item_id       BIGINT NOT NULL,
    payload_json  VARCHAR(2000) NOT NULL,
    published     BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO inventory_projection(item_id, quantity, version)
VALUES (201, 10, 0), (202, 20, 0), (203, 30, 0);

INSERT INTO incoming_inventory_change
    (id, event_id, item_id, target_qty, state)
VALUES (101, 'inv-101', 201, 11, 'NEW'),
       (102, 'inv-102', 202, 25, 'NEW'),
       (103, 'inv-103', 203, 34, 'NEW');
~~~

`target_qty` là giá trị thay thế, **không phải delta**. Với các lệnh `quantity = quantity + :delta`, retry trùng có thể làm tồn kho bị cộng hai lần; phần idempotency sẽ phân biệt kỹ hơn.

Sử dụng PostgreSQL/MySQL/SQL Server/Oracle thật khi đo driver batching, locking, isolation hoặc transaction. H2 không thay thế benchmark trên production database.

## 5. JDBC inbound: tối đa N rows không phải N lần update

`JdbcPollingChannelAdapter` chạy `SELECT` theo poller và phát kết quả là một `Message<List<Row>>`. Theo Spring Integration JDBC Reference:

- `maxRows` giới hạn **số rows trong một kết quả query**; `0` là không giới hạn.
- `maxMessagesPerPoll` là **số lần poller gọi `receive()` mỗi lần kích hoạt**; với JDBC inbound mặc định thường là 1.
- SQL `LIMIT`/`TOP`/`FETCH` giới hạn result ngay ở DB; nên ưu tiên khi dữ liệu nhiều.
- `RowMapper<T>` chuyển từng row thành DTO; `Splitter` chỉ cần khi downstream muốn từng message.

~~~sql
SELECT id, event_id, item_id, target_qty
FROM incoming_inventory_change
WHERE state = 'NEW'
ORDER BY created_at, id
LIMIT 100;
~~~

~~~text
maxRows=100, maxMessagesPerPoll=1, SQL LIMIT 100
  -> 1 SELECT mỗi trigger
  -> tối đa 100 rows
  -> 1 Message<List<ChangeRow>>
  -> nếu split: tối đa 100 Message<ChangeRow>
~~~

**Đừng đặt `maxMessagesPerPoll(100)` để mong nhận một lô 100 rows.** Làm vậy có thể chạy SELECT liên tiếp 100 lần trong một trigger, làm tăng tải database thay vì giảm.

## 6. JDBC inbound UPDATE: set-based khác per-row khác driver batch

Inbound JDBC adapter có SQL `UPDATE` để đánh dấu những rows đã SELECT. Có hai cách sử dụng đáng phân biệt:

### 6.1. UPDATE chung cho cả result list

~~~sql
UPDATE incoming_inventory_change
SET state='CLAIMED'
WHERE id IN (:ids) AND state='NEW';
~~~

Trong `updateSqlParameterSourceFactory`, tạo `SqlParameterSource` với `ids` là danh sách IDs từ **List kết quả SELECT**; để chế độ `updatePerRow(false)` (mặc định). Spring JDBC sẽ mở rộng named parameter collection phù hợp cho `IN`. Đây là **một câu SQL set-based**, *không phải* Spring JDBC `batchUpdate()`.

### 6.2. UPDATE mỗi row một lần

~~~sql
UPDATE incoming_inventory_change
SET state='CLAIMED'
WHERE id=:id AND state='NEW';
~~~

Khi `updatePerRow(true)`, factory nhận từng row để tạo parameter source. Adapter thực hiện update theo từng row, nhưng **không suy luận nó tự động gọi `PreparedStatement.addBatch/executeBatch`**. Đó là một chế độ xử lý đối tượng của inbound adapter; cơ chế JDBC batching của outbound `JdbcMessageHandler` là chuyện khác.

| Cơ chế | Số SQL statement điển hình cho 100 rows | Đơn vị tham số | Ưu điểm | Đánh đổi |
|---|---:|---|---|---|
| `updatePerRow(false)` + `IN (:ids)` | 1 | List 100 IDs | Ít round trips/SQL executions | Không có per-row update count |
| `updatePerRow(true)` | 100 | Từng row | Expression/context của từng row | Nhiều statements nếu không batch driver |
| `JdbcTemplate.batchUpdate` | 1 JDBC batch của 100 entries | 100 parameter sets | Reuse một SQL template | Row count/partial failure theo driver |
| `UPDATE ... FROM staging` | 1 set-based statement sau load | Staging table | Hiệu quả cho bulk lớn | Extra staging/maintenance |

Các con số “100” trong bảng là **số thao tác logic minh họa**, không phải benchmark trên một driver cụ thể. Với SQL `IN`, giới hạn placeholders, query-plan churn và kích thước packet cần được đo khi lô rất lớn.

## 7. Tính năng thật của JdbcMessageHandler: payload Iterable kích hoạt batch

Theo Spring Integration Reference, từ **phiên bản 5.1**, `JdbcMessageHandler` (JDBC outbound channel adapter) thực hiện `JdbcOperations.batchUpdate()` khi **payload của message là `Iterable`**.

Cơ chế:

1. Một message đến handler với payload `List<InventoryUpdate>`.
2. Handler duyệt từng phần tử. Nếu phần tử không phải `Message<?>`, nó được bọc thành message mới với **headers của message gốc**.
3. Với `SqlParameterSourceFactory`, handler tạo một mảng `SqlParameterSource[]` và gọi JDBC batch operation.
4. Nếu dùng `MessagePreparedStatementSetter`, handler dùng biến thể `BatchPreparedStatementSetter` để bind từng phần tử.
5. **Không hỗ trợ JDBC batch update khi bật `keysGenerated` mode.**

~~~text
Message<List<InventoryUpdate>>
  headers: {correlationId: "batch-27"}
  payload: [
    InventoryUpdate(201, 11),
    InventoryUpdate(202, 25),
    InventoryUpdate(203, 34)
  ]
            |
            v
JdbcMessageHandler.handleMessage(...)
            |
            v
PreparedStatement:
 UPDATE inventory_projection
 SET quantity = ?, version=version+1
 WHERE item_id = ?
  addBatch(qty=11, id=201)
  addBatch(qty=25, id=202)
  addBatch(qty=34, id=203)
  executeBatch()
~~~

**Điểm dễ sai:** nếu payload là một `List` nhưng bạn đã `.split()` trước handler, mỗi message chỉ có một `InventoryUpdate`, không còn batch của toàn bộ list. Một `byte[]` không phải `Iterable` chỉ vì chứa nhiều bytes; một Java array cũng không tự là `Iterable`. Muốn auto-batch theo cơ chế này, hãy gửi đúng payload thực thi `Iterable`.

## 8. Java DSL Spring Integration 7.x: outbound adapter batch

Spring Integration **7.0** giới thiệu Java DSL JDBC factory `org.springframework.integration.jdbc.dsl.Jdbc`. Ví dụ sau dùng `MessagePreparedStatementSetter` để tránh phụ thuộc cách introspect bean properties:

~~~java
package com.example.batch;

public record InventoryUpdate(long itemId, int targetQty) {
}
~~~

~~~java
package com.example.batch;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;

@Configuration
public class JdbcBatchOutboundFlow {

    @Bean
    public IntegrationFlow writeInventoryBatches(DataSource dataSource) {
        return IntegrationFlow.from("inventoryBatchInput")
            .handle(Jdbc.outboundAdapter(dataSource,
                    "UPDATE inventory_projection "
                  + "SET quantity=?, version=version+1, "
                  + "    updated_at=CURRENT_TIMESTAMP "
                  + "WHERE item_id=?")
                .preparedStatementSetter((ps, message) -> {
                    InventoryUpdate row =
                        (InventoryUpdate) message.getPayload();
                    ps.setInt(1, row.targetQty());
                    ps.setLong(2, row.itemId());
                }))
            .get();
    }
}
~~~

Đầu vào phải là một `Message<List<InventoryUpdate>>`, không phải từng `Message<InventoryUpdate>` nếu muốn handler batch cả danh sách:

~~~java
import java.util.List;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

List<InventoryUpdate> rows = List.of(
    new InventoryUpdate(201L, 11),
    new InventoryUpdate(202L, 25),
    new InventoryUpdate(203L, 34));

MessageChannel channel = /* Bean inventoryBatchInput */;
boolean accepted = channel.send(
    MessageBuilder.withPayload(rows).build());
~~~

**Đoạn gửi là fragment**, cần inject `@Qualifier("inventoryBatchInput") MessageChannel channel` từ Spring context. `send() == true` không phải bằng chứng commit cross-system; nó chỉ báo channel chấp nhận/send theo semantics của channel.

Một request payload là `Iterable` và `keysGenerated=false` là điều kiện để outbound handler chọn cơ chế batch. Nếu business cần trả **update counts cho từng row**, outbound **adapter** không tạo reply; dùng service `JdbcTemplate.batchUpdate` hoặc một hợp đồng gateway riêng được xác minh theo phiên bản.

### 8.1. Vì sao không dùng splitter trước outbound adapter?

~~~java
// KHÔNG batch cả list: splitter phát từng message riêng.
return IntegrationFlow.from("inventoryBatchInput")
    .split()
    .handle(Jdbc.outboundAdapter(dataSource, sql))
    .get();
~~~

Cấu hình trên **có thể đúng** khi yêu cầu mỗi row đi qua một bước xử lý riêng hoặc mỗi row cần retry/metrics riêng. Nhưng nó không đạt mục tiêu “một message Iterable → một JDBC batch” nếu không **gộp lại** trước handler.

## 9. Java configuration Spring Integration 6.x: JdbcMessageHandler

Trong **6.x**, `JdbcMessageHandler` đã có hỗ trợ Iterable batch (từ 5.1), dù factory `Jdbc.outboundAdapter(...)` của JDBC Java DSL 7.x chưa xuất hiện. Có thể cấu hình handler trực tiếp:

~~~java
package com.example.batch;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.jdbc.JdbcMessageHandler;

@Configuration
public class LegacyJdbcBatchConfiguration {

    @Bean
    @ServiceActivator(inputChannel = "inventoryBatchInput")
    public JdbcMessageHandler inventoryBatchHandler(
            DataSource dataSource) {
        JdbcMessageHandler handler = new JdbcMessageHandler(
            dataSource,
            "UPDATE inventory_projection SET quantity=?, "
          + "version=version+1 WHERE item_id=?");

        handler.setPreparedStatementSetter((ps, message) -> {
            InventoryUpdate row =
                (InventoryUpdate) message.getPayload();
            ps.setInt(1, row.targetQty());
            ps.setLong(2, row.itemId());
        });
        return handler;
    }
}
~~~

Một message có `List<InventoryUpdate>` vẫn kích hoạt batch. Đây là **phương án thay thế**, không đăng ký đồng thời cấu hình `inventoryBatchInput` của mục 8 và mục 9 trong cùng một context chỉ để demo; một `DirectChannel` với nhiều subscribers không tự broadcast tới cả hai.

## 10. XML JDBC outbound adapter xử lý batch Iterable

~~~xml
<!-- Fragment XML: yêu cầu namespace int-jdbc và bean dataSource. -->
<int:channel id="inventoryBatchInput"/>

<int-jdbc:outbound-channel-adapter
    id="inventoryBatchWriter"
    channel="inventoryBatchInput"
    data-source="dataSource"
    query="UPDATE inventory_projection
           SET quantity=:payload[targetQty],
               version=version+1
           WHERE item_id=:payload[itemId]"/>
~~~

Với payload `List`, từ Spring Integration 5.1 outbound `JdbcMessageHandler` xử lý theo cơ chế batch. Cú pháp `:payload[targetQty]` và `:payload[itemId]` được đánh giá trên **message của từng phần tử** (với default parameter strategy). Đây là **bean property / map path expression**, không phải SpEL đầy đủ. Để điều khiển SQL types hoặc dữ liệu phức tạp, có thể khai báo `sql-parameter-source-factory` hoặc `prepared-statement-setter` riêng theo contract.

Một số môi trường có bean properties khác cách truy cập Java records; hãy kiểm thử binding với phiên bản Spring cụ thể. Khi cần độ chắc chắn, dùng `MessagePreparedStatementSetter` như ví dụ Java phía trên hoặc DTO JavaBean có getters.

## 11. Không có generated keys trong JDBC outbound batch mode

Một ràng buộc được Spring Integration ghi rõ: **`JdbcMessageHandler` không hỗ trợ batch update nếu chọn chế độ `keysGenerated`**. Nguyên nhân hợp đồng và JDBC driver có độ phức tạp khác nhau khi trả generated keys theo từng batch entry.

| Yêu cầu | Cách tiếp cận |
|---|---|
| Batch nhiều UPDATE với IDs đã biết | Iterable payload + JDBC outbound adapter |
| Batch nhiều INSERT với IDs được ứng dụng cấp | Iterable payload + `keysGenerated=false` |
| INSERT cần generated key trả cho từng row | Dùng luồng INSERT/gateway riêng, hoặc repository/API đã kiểm chứng driver |
| Muốn per-row counts/partial failures | `JdbcTemplate.batchUpdate` và xử lý result/exception |
| Muốn trả danh sách rows mới theo `RETURNING` | Vendor-specific SQL + service/repository hoặc custom message source |

Không cấu hình `.keysGenerated(true)` rồi khẳng định outbound adapter vẫn batch. Với các DB cung cấp `INSERT ... RETURNING`/`OUTPUT`, đó là một hợp đồng riêng, cần test và map kết quả theo driver chứ không tự là `JdbcMessageHandler` batch mode.

## 12. Spring JDBC: BatchPreparedStatementSetter

Khi cần nhận kết quả per-row, kiểm tra affected count hoặc ghi rõ ràng trong một service, sử dụng Spring JDBC trực tiếp thay vì trông chờ vào outbound adapter one-way:

~~~java
package com.example.batch;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryJdbcBatchRepository {

    private final JdbcTemplate jdbc;

    public InventoryJdbcBatchRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int[] updateQuantities(List<InventoryUpdate> updates) {
        if (updates.isEmpty()) {
            return new int[0];
        }

        return jdbc.batchUpdate(
            "UPDATE inventory_projection "
          + "SET quantity=?, version=version+1, "
          + "    updated_at=CURRENT_TIMESTAMP "
          + "WHERE item_id=?",
            new BatchPreparedStatementSetter() {
                @Override
                public void setValues(
                        PreparedStatement ps, int index)
                        throws SQLException {
                    InventoryUpdate row = updates.get(index);
                    ps.setInt(1, row.targetQty());
                    ps.setLong(2, row.itemId());
                }

                @Override
                public int getBatchSize() {
                    return updates.size();
                }
            });
    }
}
~~~

`getBatchSize()` trả số parameter sets, `setValues(...)` bind từng entry, còn `batchUpdate(...)` trả `int[]` update counts do JDBC driver báo. Nó phù hợp khi lô đã nằm trong RAM và cần một `PreparedStatement` có nhiều bindings.

**Không gọi `jdbc.batchUpdate(...)` trên danh sách vô hạn.** Với một file/stream lớn, nên chia thành các chunk giới hạn bộ nhớ, hoặc dùng overload có batch size; kể cả khi JDBC hỗ trợ batching, giữ hàng triệu command objects và parameter values trong heap là một rủi ro.

## 13. NamedParameterJdbcTemplate.batchUpdate và SqlParameterSource

Khi SQL có nhiều tham số có tên, `NamedParameterJdbcTemplate.batchUpdate(sql, SqlParameterSource[])` giúp code dễ đọc. Cần **một `SqlParameterSource` cho mỗi row**, khác với `IN (:ids)` chỉ dùng một parameter source chứa một danh sách.

~~~java
package com.example.batch;

import java.util.List;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.stereotype.Repository;

@Repository
public class NamedInventoryBatchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public NamedInventoryBatchRepository(
            NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int[] update(List<InventoryUpdate> updates) {
        if (updates.isEmpty()) {
            return new int[0];
        }

        SqlParameterSource[] bindings = updates.stream()
            .map(row -> new MapSqlParameterSource()
                .addValue("qty", row.targetQty())
                .addValue("itemId", row.itemId()))
            .toArray(SqlParameterSource[]::new);

        return jdbc.batchUpdate(
            "UPDATE inventory_projection "
          + "SET quantity=:qty, "
          + "    version=version+1 "
          + "WHERE item_id=:itemId",
            bindings);
    }
}
~~~

`MapSqlParameterSource` không bắt buộc record phải có `getItemId()`. Với JavaBean properties hoặc `Map<String,Object>` phù hợp, có thể dùng `SqlParameterSourceUtils.createBatch(...)`:

~~~java
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSourceUtils;

// Giả sử records/map có các property phù hợp với tên SQL.
// Kiểm tra binding thực tế theo phiên bản Spring Framework.
SqlParameterSource[] batch =
    SqlParameterSourceUtils.createBatch(beanArray);

int[] counts = namedJdbc.batchUpdate(
    "UPDATE inventory_projection "
  + "SET quantity=:targetQty WHERE item_id=:itemId",
    batch);
~~~

`beanArray` là mảng DTO được khai báo ở ứng dụng. Mảnh code này nhấn mạnh API của `SqlParameterSourceUtils`, không phải một class đầy đủ. Với Java records, null values hay custom types, cách tạo `MapSqlParameterSource` tường minh thường dễ xác minh hơn.

## 14. Chia một input lớn thành nhiều JDBC batches có giới hạn

Spring JDBC có overload:

`JdbcTemplate.batchUpdate(String sql, Collection<T> args, int batchSize, ParameterizedPreparedStatementSetter<T> pss)`.

Nó trả `int[][]`, gồm **một mảng counts cho mỗi sub-batch**:

~~~java
package com.example.batch;

import java.util.Collection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ChunkedInventoryRepository {

    private final JdbcTemplate jdbc;

    public ChunkedInventoryRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int[][] updateInChunks(
            Collection<InventoryUpdate> commands) {
        return jdbc.batchUpdate(
            "UPDATE inventory_projection "
          + "SET quantity=?, version=version+1 "
          + "WHERE item_id=?",
            commands,
            100,
            (ps, row) -> {
                ps.setInt(1, row.targetQty());
                ps.setLong(2, row.itemId());
            });
    }
}
~~~

Với 230 commands và batch size 100, **về hình dạng kết quả**, thường có ba sub-batches:

~~~text
counts[0] -> 100 entries
counts[1] -> 100 entries
counts[2] -> 30 entries
~~~

**Quan trọng:** chia 230 entries thành ba sub-batches **không mặc định tạo ba database transactions**. Nếu code chạy trong một `@Transactional`, cả ba sub-batches vẫn có thể thuộc **một local transaction**; nếu không có transaction, driver/DataSource autocommit và execution semantics quyết định mức partial commit.

Khi một input có vài triệu rows, có thể đọc tuần tự theo pages/cursors, tạo `List<Command>` cỡ vừa, gọi batchUpdate và giải phóng list; kết hợp transaction boundaries rõ thay vì giữ toàn bộ dữ liệu trên heap.

## 15. Update count: 0, số dương, SUCCESS_NO_INFO và EXECUTE_FAILED

JDBC `executeBatch()` báo counts theo thứ tự các parameter sets:

| Giá trị | Hằng Java | Diễn giải |
|---|---|---|
| `0` | Không có hằng riêng | Statement chạy, nhưng không row nào phù hợp |
| `1` | — | Một row được tác động theo thông tin driver |
| `n > 1` | — | Entry tác động nhiều rows |
| `-2` | `Statement.SUCCESS_NO_INFO` | Entry xử lý thành công, **không có số rows chính xác** |
| `-3` | `Statement.EXECUTE_FAILED` | Entry thất bại khi driver tiếp tục sau lỗi |

Khi toàn batch thành công, JDBC `executeBatch()` trả counts; khi một entry lỗi, JDBC có thể ném `BatchUpdateException`. Tùy driver, nó **dừng ở entry lỗi** hoặc **tiếp tục chạy các entry khác**; mảng `getUpdateCounts()` có thể chỉ gồm những entries đã chạy trước lỗi, hoặc có các mã `EXECUTE_FAILED` cho các entries bị lỗi.

~~~java
import java.sql.Statement;

for (int count : updateCounts) {
    if (count == Statement.SUCCESS_NO_INFO) {
        // Thành công theo driver, nhưng không biết số rows.
    } else if (count == Statement.EXECUTE_FAILED) {
        // Thường thấy khi xử lý BatchUpdateException.
    } else if (count == 0) {
        // Có thể không tìm thấy itemId hoặc optimistic conflict.
    } else if (count > 0) {
        // Đã tác động count rows theo driver.
    }
}
~~~

**Không cộng thẳng tất cả `counts` để suy ra số rows đã cập nhật**, vì `-2` không phải số rows âm. Nếu ứng dụng phải xác nhận mỗi update chính xác một row, với `SUCCESS_NO_INFO` cần kiểm chứng theo cơ chế khác hoặc chọn query/driver phù hợp.

### 15.1. BatchUpdateException và exception translation

Spring `JdbcTemplate` thường dịch `SQLException` sang `DataAccessException`. Khi cần root cause/counters để chẩn đoán, kiểm tra cause chain để tìm `BatchUpdateException`, nhưng vẫn **không dùng partial counts làm căn cứ tự commit các entry thành công** nếu business yêu cầu all-or-nothing.

~~~java
import java.sql.BatchUpdateException;

// Pseudocode: trong một catch DataAccessException.
Throwable current = ex;
while (current != null) {
    if (current instanceof BatchUpdateException batchEx) {
        int[] partial = batchEx.getUpdateCounts();
        // Ghi metric / log theo giới hạn dữ liệu nhạy cảm.
        // Để transaction rollback; không ACK batch như thành công.
        break;
    }
    current = current.getCause();
}
~~~

**Trong transactional handler**, để exception truyền ra giúp transaction manager rollback theo quy tắc. Nếu catch `DataAccessException` rồi return success, poller/transaction interceptor có thể COMMIT một phần công việc. Driver partial execution và DB transaction commit là **hai tầng semantics khác nhau**.

## 16. Transaction và rollback khi batch có một entry lỗi

Một batch JDBC có thể chạy trong một local transaction. Đây là cách giữ các UPDATE thành **một unit of work**:

~~~java
package com.example.batch;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryBatchService {

    private final NamedInventoryBatchRepository repository;

    public InventoryBatchService(
            NamedInventoryBatchRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int[] apply(List<InventoryUpdate> updates) {
        int[] counts = repository.update(updates);

        for (int count : counts) {
            if (count != 1 &&
                count != java.sql.Statement.SUCCESS_NO_INFO) {
                throw new IllegalStateException(
                    "Unexpected update count: " + count);
            }
        }

        return counts;
    }
}
~~~

Ở ví dụ, `SUCCESS_NO_INFO` được chấp nhận như **statement thành công theo JDBC**, nhưng không khẳng định mọi row chắc chắn đã tồn tại/đúng version; policy thực tế có thể **không** chấp nhận nếu yêu cầu chính xác count bằng 1. Việc xác định policy phải dựa trên business contract.

Các điều kiện để rollback toàn batch:
- Service được gọi thông qua **Spring transactional proxy**, không self-invocation.
- Transaction manager quản lý đúng `DataSource` mà `NamedParameterJdbcTemplate` dùng.
- Sử dụng `JdbcTransactionManager` hoặc `DataSourceTransactionManager` phù hợp với JDBC resource; không nhầm với transaction manager của broker.
- Các statements thực thi qua connection tham gia transaction hiện hành.
- Lỗi được ném ra ngoài transaction method hoặc transaction được đánh dấu rollback-only.
- DB/dialect hỗ trợ transactional DML cho bảng đó.

**Ngoại lệ quan trọng:** nếu không có transaction, một số entries có thể đã commit trước khi driver báo lỗi. `@Transactional` không thể rollback dữ liệu ở database khác hoặc Kafka/HTTP đã được gửi bên ngoài local JDBC transaction.

### 16.1. TransactionTemplate khi cần boundary tường minh

~~~java
import org.springframework.transaction.support.TransactionTemplate;

int[] counts = new TransactionTemplate(transactionManager).execute(
    status -> repository.update(updates));
~~~

`TransactionTemplate` phải được gọi trên thread thực thi JDBC, cùng manager/DataSource. Nếu code gửi `Message<List<...>>` qua `ExecutorChannel`, không giả định transaction thread gửi được truyền sang executor.

## 17. Polling inbound rồi ghi JDBC outbound trong một transaction

Một kịch bản hay gặp: adapter inbound đọc `incoming_inventory_change`, đánh dấu `NEW → CLAIMED` và chuyển các rows để cập nhật `inventory_projection`. Nếu cần **cả hai bảng cùng commit**, giữ downstream đồng bộ trong transaction poller.

~~~mermaid
sequenceDiagram
    participant P as Poller transactional
    participant SRC as JDBC inbound
    participant DB as Database
    participant H as JdbcMessageHandler
    P->>DB: BEGIN
    P->>SRC: SELECT up to 100 NEW rows
    SRC->>DB: UPDATE matched IDs to CLAIMED
    SRC-->>H: Message<List<ChangeRow>>
    H->>DB: JDBC batchUpdate 100 updates
    alt Batch thành công
        P->>DB: COMMIT
    else Một entry bị lỗi
        H-->>P: Exception
        P->>DB: ROLLBACK cả claim và batch
    end
~~~

**Điểm cần xác minh:** `Message<List<ChangeRow>>` phải được giữ nguyên đến outbound handler. Nếu transformer chuyển thành `List<InventoryUpdate>` cũng được, miễn payload cuối là `Iterable`. Nếu splitter tách thành từng message hoặc một async channel chen giữa, transaction/batching semantics thay đổi.

### 17.1. Java DSL Spring Integration 7.x: một flow minh họa

~~~java
package com.example.batch;

import java.time.Duration;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ClaimThenBatchFlow {

    public record ChangeRow(
        long id, String eventId, long itemId, int targetQty) { }

    @Bean
    public IntegrationFlow claimAndUpdateProjection(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource,
                    "SELECT id, event_id, item_id, target_qty "
                  + "FROM incoming_inventory_change "
                  + "WHERE state='NEW' ORDER BY id LIMIT 100")
                    .maxRows(100)
                    .rowMapper((rs, n) -> new ChangeRow(
                        rs.getLong("id"),
                        rs.getString("event_id"),
                        rs.getLong("item_id"),
                        rs.getInt("target_qty")))
                    .updateSql(
                        "UPDATE incoming_inventory_change "
                      + "SET state='CLAIMED' "
                      + "WHERE id IN (:ids) AND state='NEW'")
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> list = (List<?>) result;
                        List<Long> ids = list.stream()
                            .map(ChangeRow.class::cast)
                            .map(ChangeRow::id)
                            .toList();
                        return new MapSqlParameterSource("ids", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(3))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .filter(payload ->
                payload instanceof List<?> list && !list.isEmpty())
            .handle(Jdbc.outboundAdapter(dataSource,
                    "UPDATE inventory_projection "
                  + "SET quantity=?, version=version+1 "
                  + "WHERE item_id=?")
                .preparedStatementSetter((ps, message) -> {
                    ChangeRow row = (ChangeRow) message.getPayload();
                    ps.setInt(1, row.targetQty());
                    ps.setLong(2, row.itemId());
                }))
            .get();
    }
}
~~~

**Đây là flow một-instance để học batch+transaction**, không phải hàng đợi phân tán chống race. Hai pods dùng SELECT thường vẫn có thể nhận cùng row trước khi UPDATE. Với multi-instance, cần `SELECT ... FOR UPDATE SKIP LOCKED` trong cùng transaction, atomic claim returning rows hoặc partition ownership; có thể thay SQL trong ví dụ theo DB vendor, kèm test concurrency.

Đặc biệt, `ChangeRow.targetQty` là **snapshot giá trị thay thế**. Với delta updates không idempotent hoặc events trên cùng item trong một batch, cần version/order/idempotency policy; một batch JDBC không tự giải quyết thứ tự nguồn/consumer.

### 17.2. Khi database nguồn và đích khác nhau

Flow trên chỉ có thể commit hai bảng cùng nhau nếu **cùng một local DataSource/transaction manager**. Nếu inbound đọc DB A và outbound ghi DB B, `.transactional(managerA)` không tự tạo atomic transaction DB A + DB B. Khi đó cần outbox/inbox, replay/idempotency, saga hoặc XA/JTA được thiết kế và kiểm chứng rõ.

## 18. Gom từ từng message bằng Aggregator: batch size và timeout

Nếu nguồn Kafka/JMS/HTTP gửi **một message mỗi event**, trước JDBC outbound handler cần một bước gom hoặc application batch buffer. Spring Integration có **Aggregator** và `MessageGroupStore`, nhưng phải thiết kế:

- **Correlation key:** nhóm nào được gom (tenant, aggregate, partition)? Không dùng một constant key cho mọi message nếu nhóm không bao giờ được đóng/released.
- **Release strategy:** phát khi đủ `N` messages hoặc tới deadline.
- **Group timeout:** tránh các groups dở dang không bao giờ đạt N.
- **Partial result:** nếu phát nhóm chưa đủ N, cần biết đơn vị retry và ACK.
- **Persistent MessageGroupStore:** nếu cần chống mất messages khi crash, dùng persistent store/queue.
- **Ordering:** giữ thứ tự per item/aggregate nếu nghiệp vụ yêu cầu; multi-worker có thể đảo thứ tự.
- **Backpressure:** chặn việc gom vô hạn trong RAM khi DB chậm.

~~~text
Kafka/JMS event stream:
 e1  e2  e3  e4  e5  ...
  |   |   |   |   |
  v   v   v   v   v
Aggregator (size=3 hoặc group timeout)
  -> Message<List<InventoryUpdate>> [e1,e2,e3]
  -> Message<List<InventoryUpdate>> [e4,e5] (partial group)
  -> JDBC outbound adapter batch
~~~

**Đừng coi `Aggregator` tự tạo một JDBC batch chỉ vì tồn tại.** Payload sau release phải là `Iterable` phù hợp. Hợp đồng mặc định của aggregator có thể là một message chứa `Collection` payload hoặc `MessageGroup` tùy cấu hình/release processor; cần kiểm tra và nếu cần `Transformer` tạo `List<InventoryUpdate>` thực tế.

**ACK với Kafka/JMS:** nếu offset/ACK nguồn được commit khi event chỉ mới nằm trong aggregator memory, crash có thể làm mất một nhóm chưa release. Với nghiệp vụ cần bảo đảm mạnh, sử dụng broker batch container hoặc persistent aggregator/outbox trước ACK.

## 19. Chọn batch size: cân bằng throughput và tail latency

Kích thước batch là một **tham số cần đo**, không có con số tối ưu chung cho mọi database. Một kế hoạch benchmark có thể thử `1, 10, 50, 100, 250, 500` entries/batch trong cùng workload.

| Batch nhỏ | Batch lớn |
|---|---|
| Latency mỗi event thường thấp hơn khi tải thưa | Throughput có thể cao hơn khi tải lớn |
| Dễ retry/định vị lỗi từng entry | Lỗi một entry có thể rollback cả lô lớn |
| Ít memory/connection lock duration | Payload/buffer lớn, transaction dài hơn |
| Nhiều database round trips | Ít round trips hơn nhưng packet/parameter limits |
| Dễ đảm bảo thứ tự đơn giản | Trùng IDs/ordering cần xử lý kỹ |

**Bài toán hai tham số:** `batch size` tối đa và `max wait`. Chỉ chờ đủ N khi tải thưa có thể làm event chờ rất lâu; chỉ flush rất sớm thì hiệu quả batching giảm. Cần quyết định ngưỡng theo SLA, không chỉ số rows/s.

### 19.1. Đo thay vì đoán

Từ mỗi phép thử, thu:
- `batch_size_actual` (p50/p95), số lô mỗi giây.
- `batch_execute_duration` (p50/p95/p99), transaction duration.
- Events/second và rows-affected/second.
- Thời gian event chờ trước khi vào batch (`queue_wait`).
- Database CPU/IO, WAL/redo volume, locks/deadlocks.
- Hikari pool acquire wait, active/pending connections.
- Số retries, rollback batches và DLQ.
- Heap sử dụng khi buffers lớn.

**Không ghi “batch 500 luôn nhanh gấp 5 lần batch 100”** nếu chưa đo. Tối ưu phụ thuộc tốc độ network, driver, SQL plan, row sizes, indexes, DB locks và cách gom.

## 20. SQL set-based vs JDBC batch: đôi lúc một statement tốt hơn

Nếu cùng trạng thái được áp dụng cho nhiều IDs, một SQL set-based có thể hiệu quả và dễ atomic hơn:

~~~sql
UPDATE incoming_inventory_change
SET state='CLAIMED'
WHERE id IN (:ids)
  AND state='NEW';
~~~

Trong khi mỗi row có quantity khác nhau thì JDBC batch với cùng SQL template thường tự nhiên:

~~~sql
UPDATE inventory_projection
SET quantity=:targetQty, version=version+1
WHERE item_id=:itemId;
~~~

Với hàng trăm nghìn values cần join/mapping phức tạp, phương án **staging table + merge/set-based UPDATE** có thể tốt hơn:

~~~sql
-- PostgreSQL minh họa: staging_inventory đã chứa dữ liệu sạch.
UPDATE inventory_projection AS i
SET quantity = s.target_qty,
    version = i.version + 1
FROM staging_inventory AS s
WHERE i.item_id = s.item_id;
~~~

Điều kiện: staging data phải được kiểm tra duplicate item IDs; nếu nhiều rows ở staging match cùng một row đích, semantics join/update có thể khó đoán và phụ thuộc DB. Thao tác load staging, update/merge và cleanup có transaction/recovery policy riêng.

**Không giả định batch JDBC = một SQL statement.** JDBC driver có thể gửi nhiều executions trong một protocol batch; set-based UPDATE là một statement xử lý nhiều rows trực tiếp.

## 21. Driver-level batching và cấu hình đặc thù

### 21.1. PostgreSQL pgJDBC

pgJDBC có property `reWriteBatchedInserts=true`, giúp các **batch INSERT tương thích** được viết lại thành multi-row INSERT, giảm network/protocol overhead:

~~~yaml
# PostgreSQL ví dụ; password phải lấy từ secret manager.
spring:
  datasource:
    url: "jdbc:postgresql://db.example:5432/app?reWriteBatchedInserts=true"
~~~

Không kết luận property này tối ưu **UPDATE** theo cách giống INSERT. Nó dành cho batch INSERT phù hợp driver rewrite. Rewrite có thể thay đổi **shape của update counts**, vì driver có thể không trả count riêng cho từng INSERT như ban đầu. Test khi có `ON CONFLICT`/generated keys/RETURNING.

### 21.2. MySQL Connector/J

MySQL Connector/J có property `rewriteBatchedStatements=true` cho một số tình huống batch, trong đó có rewrite `INSERT`/`REPLACE` tương thích thành multi-values và có các giới hạn về packet, generated keys, counts:

~~~text
jdbc:mysql://db.example:3306/app?rewriteBatchedStatements=true
~~~

**Lưu ý:** Khi kết hợp `INSERT ... ON DUPLICATE KEY UPDATE`, update counts từng entry có thể không còn chi tiết như trước; driver có thể trả `SUCCESS_NO_INFO`. Các câu SQL/batch lớn phải phù hợp `max_allowed_packet` và driver constraints.

### 21.3. SQL Server, Oracle và vendor khác

Không sao chép flag pgJDBC/MySQL sang JDBC URL của SQL Server hay Oracle. Mỗi driver có các tùy chọn statement caching, parameter binding, batch size và bulk operation riêng. Một số workload lớn có thể phù hợp `COPY`/bulk loader hơn JDBC batch.

**Chính sách đúng:** nâng driver tương thích, đo baseline, thay một thông số, kiểm tra correctness/update counts và benchmark lại cùng dataset. Không bật rewrite chỉ vì thấy tăng throughput trên hệ thống khác.

## 22. SQL parameter type, NULL và overhead khi batch

Batch có thể chậm do việc suy luận kiểu SQL của giá trị `null`, nhất là khi driver phải hỏi `ParameterMetaData.getParameterType()`. Spring Framework Reference lưu ý cơ chế metadata lookup này có thể tốn round trip; từ **Spring Framework 6.1.2**, một số driver PostgreSQL/SQL Server được bỏ qua đường suy luận mặc định đó.

Những cách chủ động giảm ambiguity:

1. Dùng `PreparedStatement#setNull(index, Types.VARCHAR)`, `setObject(..., sqlType)` hoặc setter typed phù hợp.
2. Với `MapSqlParameterSource`, chỉ định SQL type bằng `.addValue(name, value, Types.VARCHAR)` hoặc `registerSqlType(...)`.
3. Với danh sách `Object[]`, cung cấp `int[] argTypes` khi dùng overload phù hợp.
4. Với JavaBeans, Spring có thể suy ra kiểu từ property khai báo, nhưng cần kiểm tra behavior của driver đối với `null`.
5. Đo performance trước khi thay global system property `spring.jdbc.getParameterType.ignore`.

~~~java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource parameters =
    new MapSqlParameterSource()
        .addValue("id", 201L, Types.BIGINT)
        .addValue("description", null, Types.VARCHAR);
~~~

**Không bật hay tắt global flag mà chưa đo**, vì một driver có thể yêu cầu kiểu SQL chính xác để xử lý binary/LOB hoặc cột đặc biệt. Với payload có JSON, UUID, ARRAY, BLOB, CLOB, timezone hoặc enum, hãy xác minh binding theo vendor thay vì ép mọi tham số thành `VARCHAR`.

### 22.1. PreparedStatement reuse không đồng nghĩa truy vấn không cần index

Batch giảm overhead tạo/execution của statements, nhưng database vẫn thực hiện công việc UPDATE trên các rows. Nếu `WHERE item_id=?` thiếu index, 100 entry batch vẫn có thể gây 100 scans đắt đỏ. Với khóa primary key/index tốt, chi phí row lookup thường thấp hơn; đo với `EXPLAIN`/actual plan, thống kê locks và buffer misses.

## 23. Thứ tự commands và trùng khóa trong cùng một batch

Giả sử hai updates cùng `itemId=201` xuất hiện trong một batch:

~~~text
InventoryUpdate(201, 11)
InventoryUpdate(202, 25)
InventoryUpdate(201, 99)
~~~

Nếu chúng mang **giá trị thay thế**, kết quả cuối phụ thuộc thứ tự thực thi được quan sát và concurrency. JDBC batch entries được thêm theo thứ tự, nhưng giữa nhiều **batches**, nhiều database connections, workers hoặc partition broker, không có bảo đảm thứ tự nghiệp vụ toàn cục.

**Các quy tắc cần thiết:**

- Nếu chỉ quan tâm latest snapshot, có thể coalesce theo `itemId` **dựa trên sequence/version đáng tin**, không chỉ lấy item xuất hiện sau trong list tùy ý.
- Nếu là **delta** (cộng/trừ số lượng), bỏ một event để coalesce sai có thể làm mất doanh số/tồn kho.
- Nếu cần thứ tự theo aggregate, giữ consumer partition/worker ownership hoặc version và optimistic update.
- Nếu hai commands có cùng item nhưng khác versions, SQL nên kiểm tra `expected_version` để từ chối update stale.
- Nếu có một batch được retry sau timeout, target quantity SET tương đối idempotent hơn `quantity = quantity + delta`, nhưng vẫn cần event/version check trước khi tuyên bố exactly-once effect.

~~~sql
-- Bản có optimistic version, mỗi entry update count phải được xử lý.
UPDATE inventory_projection
SET quantity=:targetQty,
    version=version+1,
    updated_at=CURRENT_TIMESTAMP
WHERE item_id=:itemId
  AND version=:expectedVersion;
~~~

`UPDATED=0` ở đây không tự động là lỗi SQL. Nó có thể là conflict, missing row hoặc duplicate đã xử lý; phải đọc state/processed-event ID trước khi quyết định ACK hoặc retry.

## 24. Idempotency khi nguồn Kafka/JMS/HTTP redeliver cả batch

**Batching tối ưu throughput, không thay thế idempotency.** Nếu consumer Kafka/JMS xử lý một batch 100 messages rồi database commit thành công nhưng ACK/offset commit thất bại, **toàn batch hoặc một phần** có thể được nhận lại.

Một thiết kế bền vững:

~~~mermaid
flowchart LR
    A["Kafka/JMS batch / HTTP batch"] --> B["Validate + dedupe by eventId"]
    B --> C["JDBC transaction"]
    C --> D["INSERT processed_event unique"]
    C --> E["UPDATE inventory"]
    C --> F["INSERT outbox nếu cần publish"]
    D --> G[("DB COMMIT")]
    E --> G
    F --> G
    G --> H["ACK/offset theo container policy"]
~~~

Bảng processed-event (minh họa):

~~~sql
CREATE TABLE processed_inventory_event (
    event_id VARCHAR(80) NOT NULL PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Trong **cùng JDBC transaction**, mỗi event ID được insert/claim để ngăn duplicate business effects. Nếu marker đã tồn tại, cần kiểm tra đó là duplicate hợp lệ cùng nội dung/ý nghĩa, không tùy tiện bỏ qua conflict.

Nếu lô chứa 100 rows nhưng 5 đã xử lý:
- Có thể lọc 5 duplicates **trước** tạo JDBC batch còn 95 parameter sets.
- Hoặc áp dụng SQL idempotent `INSERT ... ON CONFLICT DO NOTHING`/`MERGE` phù hợp vendor.
- Không tạo event ID mới mỗi lần retry, vì dedupe sẽ mất hiệu lực.
- Nếu sau update phải phát Kafka, ghi outbox cùng transaction để tránh mất event sau DB commit.

**JDBC transaction không tự commit Kafka offset hoặc JMS ACK.** Một local JDBC COMMIT có thể thành công trước broker ACK; redelivery là bình thường và phải được dự kiến.

## 25. Retry một batch lỗi: xử lý cả lô hay tách để tìm poison record?

Giả sử batch 100 rows có entry thứ 37 vi phạm constraint. Chiến lược xử lý cần dựa trên lỗi:

| Loại lỗi | Hướng xử lý |
|---|---|
| Deadlock/lock timeout transient | Rollback toàn transaction; retry batch trong TX mới với backoff |
| Network failure sát COMMIT | Outcome có thể không chắc; đối soát bằng event ID/state |
| Unique duplicate hợp lệ | Chọn dedupe/UPSERT policy; không retry vô hạn |
| Schema/SQL syntax sai | Dừng flow, sửa migration/config |
| Payload quá dài hoặc dữ liệu sai | Validation, quarantine/DLQ và manual replay |
| Version conflict (update count 0) | Đối soát state/version; không coi là DB outage |
| Driver báo `SUCCESS_NO_INFO` | Không giả định count chính xác là 1 |
| Partial JDBC batch failure | Exception + local rollback; dùng counts để chẩn đoán |

### 25.1. Chiến lược cô lập poison event

Với một batch có một record sai dữ liệu, có thể:
1. Rollback batch.
2. Nếu lỗi **đã xác định là dữ liệu vĩnh viễn**, dùng kiểm tra pre-validation hoặc chia batch có kiểm soát (ví dụ chia đôi) để khoanh vùng record.
3. Ghi một sự kiện lỗi/DLQ bền vững; chỉ ACK các event có contract xử lý xong hoặc được chuyển quarantine thành công.
4. Giữ business event ID và audit lý do tách/skip/retry.

**Không dùng binary-split retry bừa bãi** khi các commands phụ thuộc thứ tự và transaction của nhau; chia batch có thể làm thay đổi kết quả nghiệp vụ. Không “bỏ record lỗi rồi commit 99 records” nếu business yêu cầu 100 records phải atomic như một lô.

### 25.2. Không retry trực tiếp trên transaction đã hỏng

Ở PostgreSQL, khi một statement làm transaction vào trạng thái aborted, các SQL tiếp theo thường không thể tiếp tục như bình thường cho đến rollback. Retry phải tạo **transaction mới**. Với deadlock, danh sách rows, ownership, version và pending state có thể đã đổi: đọc lại current state, không dùng cache IDs cũ như đã chắc chắn claim.

## 26. Kết nối, transaction, channel và timeout

Bottleneck không chỉ nằm ở SQL. Một batch giữ một JDBC connection trong suốt thời gian giao dịch; nếu nhiều batches thực thi đồng thời, Hikari pool có thể cạn.

| Thông số | Tầng | Tác động |
|---|---|---|
| `spring.datasource.hikari.maximum-pool-size` | JDBC pool | Số connections tối đa |
| `connection-timeout` | JDBC pool | Thời gian chờ lấy connection |
| `JdbcTemplate#setQueryTimeout` | JDBC statement | Giới hạn query execution theo driver |
| `@Transactional(timeout=...)` | JDBC transaction | Thời hạn unit of work |
| `maxMessagesPerPoll` | Poller | Số lần receive/query mỗi trigger |
| `batch size` và max wait | Aggregator/app buffer | Throughput vs latency/memory |
| Executor pool/queue size | Async channel | Concurrency và backpressure |
| Kafka/JMS ACK timeout | Broker/container | Không là JDBC transaction timeout |

**Với `DirectChannel`**, handler chạy ngay trên thread gửi và có thể dùng transaction hiện tại. **Với `ExecutorChannel` hoặc `QueueChannel`**, transaction thread-bound không tự truyền. Nếu adapter JDBC batch chạy ở worker khác, phải mở transaction **tại worker** hoặc stage dữ liệu bền vững trước khi handoff.

~~~text
Transactional poller BEGIN
  -> JDBC inbound SELECT/UPDATE
  -> DirectChannel
  -> JdbcMessageHandler batchUpdate
Transactional poller COMMIT/ROLLBACK

--- Chèn ExecutorChannel ---

Poller BEGIN -> inbound UPDATE -> ExecutorChannel.send -> Poller COMMIT
                                               |
                                               v
                                   Worker batchUpdate (TX riêng)
~~~

Nếu worker lỗi sau poller COMMIT, rollback worker **không** hồi lại state `CLAIMED` ở source. Cần lease/recovery hoặc outbox.

JDBC là **blocking I/O**. Trong ứng dụng WebFlux, không chạy `JdbcTemplate` batch trực tiếp trên Reactor Netty event loop; chuyển toàn bộ JDBC transaction sang worker phù hợp, hoặc dùng database reactive theo hợp đồng khác.

## 27. Chẩn đoán hiệu năng bằng số liệu thay vì chỉ SQL logs

Một quy trình quan sát nên trả lời:
- Mỗi batch chứa bao nhiêu entries, bao nhiêu rows thực sự thay đổi?
- `batchUpdate()` tốn thời gian ở **DB execution**, **connection acquire** hay **queue wait**?
- JDBC driver có thực sự batching không, hay fallback sang từng statement?
- Có quá nhiều unique constraints/indexes/triggers tăng write amplification không?
- Batch size lớn có làm transaction duration/p99 cao hay lock wait tăng?
- Hệ thống có đang gây retry storm khi DB mất kết nối không?

### 27.1. Metrics đề xuất

| Metric | Cách hiểu |
|---|---|
| `jdbc_batch_size` | Histogram số entries thực tế mỗi batch |
| `jdbc_batch_duration` | Duration cho `batchUpdate` |
| `jdbc_batch_failures` | Số batch lỗi phân loại SQLState/vendor code |
| `rows_updated_known` | Chỉ tính counts không âm khi driver biết count |
| `success_no_info_count` | Số entries thành công nhưng không biết affected row count |
| `batch_queue_wait` | Thời gian từ event nhận đến lúc flush batch |
| `transaction_duration` | Thời gian giữ connection/locks |
| `hikari_connections_pending` | Threads chờ lấy connection |
| `db_lock_wait`/deadlocks | Contention ảnh hưởng tail latency |
| `outbox_pending_age` | Nguy cơ tồn backlog khi broker chậm |
| `duplicate_event_filtered` | Mức redelivery/idempotency |

Logs/traces nên chứa `batchId`, event count, correlation ID, query class, elapsed, exception type. Không log nguyên tất cả 500 payload JSON nếu chứa PII hoặc tokens. Không dùng từng eventId làm metrics label cardinality cao.

### 27.2. Benchmark theo ma trận có đối chứng

| Biến thử nghiệm | Các mức ví dụ | Giữ cố định |
|---|---|---|
| Batch size | 1, 10, 50, 100, 250, 500 | Dataset và SQL |
| Concurrency | 1, 2, 4, 8 workers | Pool, batch size |
| Driver rewrite | OFF/ON | Driver version, SQL, workload |
| Index | baseline/optimized | Hardware và data volume |
| Transaction scope | per event/per batch | Isolation và replay policy |
| Message assembly | List sẵn/Aggregator | Batch size thực, max wait |

Chạy warm-up, test đủ lâu, nhiều repetitions, thu p95/p99 và error rates; report cả CPU, network và DB resource limits. So sánh H2 in-memory với PostgreSQL production **không** cho kết luận đúng về database batch latency.

## 28. Unit test Spring JDBC batch update

Để kiểm tra binding và row-count semantics ở môi trường kiểm soát, có thể dùng test với bảng H2 ở mục 4.

~~~java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class NamedInventoryBatchRepositoryTest {

    @Autowired
    NamedInventoryBatchRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void updatesThreeExistingRows() {
        int[] counts = repository.update(List.of(
            new InventoryUpdate(201, 11),
            new InventoryUpdate(202, 25),
            new InventoryUpdate(203, 34)));

        assertEquals(3, counts.length);

        Integer quantity = jdbc.queryForObject(
            "SELECT quantity FROM inventory_projection "
          + "WHERE item_id=?",
            Integer.class, 201L);

        assertEquals(11, quantity);
    }
}
~~~

Test này giả định `schema.sql` đã có ba hàng như ví dụ, không có poller nền cùng sửa bảng, và JDBC driver test tương thích. `int[]` có thể dùng values `SUCCESS_NO_INFO` thay vì count cụ thể; test không nên hardcode `assertArrayEquals(new int[]{1,1,1}, ...)` cho mọi driver.

### 28.1. Rollback toàn batch trong một transaction

~~~java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class InventoryBatchRollbackTest {

    @Autowired
    NamedInventoryBatchRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PlatformTransactionManager manager;

    @Test
    void exceptionRollsBackBatch() {
        int before = jdbc.queryForObject(
            "SELECT quantity FROM inventory_projection "
          + "WHERE item_id=201",
            Integer.class);

        TransactionTemplate tx = new TransactionTemplate(manager);

        assertThrows(IllegalStateException.class,
            () -> tx.executeWithoutResult(status -> {
                repository.update(List.of(
                    new InventoryUpdate(201, 999),
                    new InventoryUpdate(202, 888)));
                throw new IllegalStateException(
                    "Simulated failure before COMMIT");
            }));

        int after = jdbc.queryForObject(
            "SELECT quantity FROM inventory_projection "
          + "WHERE item_id=201",
            Integer.class);

        assertEquals(before, after);
    }
}
~~~

**Không gắn `@Transactional` lên test method chỉ để làm code dễ chạy.** Spring Test có thể rollback test transaction ở cuối, che việc production flow có commit đúng hay không. Test `TransactionTemplate` trên đọc được dữ liệu sau transaction giúp kiểm tra rollback rõ hơn.

## 29. Integration test JDBC outbound adapter với List payload

Mục tiêu của test: xác minh **một message chứa `List<InventoryUpdate>`** đi tới `JdbcMessageHandler` và làm thay đổi ba rows.

~~~java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class JdbcBatchOutboundAdapterTest {

    @Autowired
    @Qualifier("inventoryBatchInput")
    MessageChannel batches;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void iterablePayloadUpdatesAllRows() {
        boolean sent = batches.send(
            MessageBuilder.withPayload(List.of(
                new InventoryUpdate(201, 11),
                new InventoryUpdate(202, 25),
                new InventoryUpdate(203, 34)))
            .build());
        assertTrue(sent);

        Integer actual = jdbc.queryForObject(
            "SELECT quantity FROM inventory_projection "
          + "WHERE item_id=203",
            Integer.class);
        assertEquals(34, actual);
    }
}
~~~

Đây là integration test **của cấu hình Java DSL ở mục 8** trên một context riêng, không đồng thời bật `LegacyJdbcBatchConfiguration` (mục 9), flow inbound (mục 17) hoặc poller khác đang sửa cùng fixtures. `MessageChannel.send` và SELECT xác minh thay đổi đã diễn ra với sync DirectChannel, nhưng **không đo chính xác số JDBC driver round trips**. Để chắc chắn driver sử dụng batch, dùng datasource-proxy/SQL metrics phù hợp mà không dựa vào log format của một driver.

## 30. Kiểm thử lỗi một entry, concurrency và driver rewrite

| Kịch bản | Kỳ vọng |
|---|---|
| Batch 100 rows đều hợp lệ | Cập nhật theo policy; counts phù hợp driver |
| Batch có item ID không tồn tại | Update count 0, policy không silently ACK |
| Batch có entry vi phạm CHECK/UNIQUE | Có exception; transaction rollback nếu configured |
| Driver trả SUCCESS_NO_INFO | Không kết luận 0 hoặc 1 affected row |
| Driver tiếp tục sau BatchUpdateException | Phân tích partial counts nhưng rollback toàn TX nếu cần |
| JDBC outbound bật keysGenerated | Không dùng auto Iterable batch mode |
| Dùng `.split()` trước JdbcMessageHandler | Auto-batch toàn list không còn |
| Dùng `ExecutorChannel` sau inbound claim | Poller TX không rollback theo worker failure |
| Retry batch sau COMMIT nhưng trước ACK | Stable IDs/idempotent effect chống trùng |
| Hai updates cùng itemId trong batch | Ordering/version semantics rõ |
| 500 entries với nullable params | Kiểm tra typed null và metadata overhead |
| PostgreSQL rewriteBatchedInserts ON/OFF | Benchmark chỉ với INSERT phù hợp |
| MySQL rewriteBatchedStatements ON/OFF | Check correctness/counts/packet limits |
| Batch lớn và pool nhỏ | Không gây lock timeout/retry storm |
| Retry deadlock | Rollback, mở transaction mới và backoff |
| Poller inbound UPDATE trước outbound batch lỗi | Cùng transaction thì rollback, async thì cần recovery |

Để kiểm tra đúng behavior PostgreSQL/MySQL/SQL Server/Oracle, dùng **Testcontainers hoặc test DB cùng vendor** và test với network latency thực tế gần production. Không dùng H2 để kết luận về rewrite, batch packet limits, deadlocks hoặc driver-specific count codes.

## 31. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Một List payload là driver batch” | Chỉ khi handler/service dùng JDBC batch API |
| “Inbound `maxRows=100` là JDBC batch 100 updates” | Nó giới hạn result SELECT; update strategy khác |
| “`updatePerRow(true)` luôn là executeBatch” | Là per-row updates; không mặc định driver batch |
| “`UPDATE ... IN (:ids)` là batchUpdate” | Một SQL set-based statement |
| “`JdbcMessageHandler` tự batch payload Java array” | Auto-batch dựa trên `Iterable` |
| “Splitter trước outbound adapter tăng batching” | Nó tách Iterable thành nhiều messages |
| “`keysGenerated=true` vẫn batch Iterable” | Batch mode không hỗ trợ generated keys |
| “Outbound adapter trả per-row counts” | One-way handler không cung cấp reply theo cách đó |
| “`SUCCESS_NO_INFO=-2` là failed update” | Thành công nhưng không biết count |
| “`EXECUTE_FAILED=-3` chỉ là 0 affected rows” | Là mã failure trong batch exception |
| “Một entry lỗi tự rollback toàn lô dù autocommit” | Phải cấu hình JDBC transaction |
| “`@Transactional` tự chạy trên self-invocation” | Proxy có thể bị bypass |
| “`ExecutorChannel` giữ transaction của poller” | Transaction không tự lan sang executor |
| “Một batch COMMIT cùng Kafka offset” | Local JDBC transaction không là XA mặc định |
| “Batch 100 luôn nhanh hơn batch 10” | Phụ thuộc SQL, driver, DB, SLA và tải |
| “Batch size là số connections” | Batch size khác pool size và concurrency |
| “PostgreSQL rewriteBatchedInserts tối ưu mọi UPDATE” | Nó hướng tới INSERT phù hợp |
| “Retry batch không thể tạo duplicate” | ACK/outcome không chắc, cần idempotency |
| “SQL UPDATE count 0 luôn là lỗi mạng” | Có thể missing row/version conflict |
| “JDBC batching là non-blocking” | JDBC vẫn blocking I/O |

## 32. Bài thực hành

1. Tạo ba bảng `inventory_projection`, `incoming_inventory_change`, `inventory_outbox` và chèn dữ liệu mẫu.
2. Thực hiện 100 lệnh `JdbcTemplate.update` riêng lẻ, ghi baseline latency với DB thật.
3. Thay bằng `JdbcTemplate.batchUpdate` và `BatchPreparedStatementSetter`; đo throughput và counts.
4. Thử `NamedParameterJdbcTemplate.batchUpdate` với `MapSqlParameterSource[]`.
5. Thử `SqlParameterSourceUtils.createBatch(...)`, kiểm tra mapping JavaBean/record.
6. Dùng overload `batchUpdate(sql, Collection, 100, pss)` cho 230 rows; xác minh `int[][]`.
7. Xử lý `Statement.SUCCESS_NO_INFO` mà không cộng nhầm -2 vào số rows.
8. Ném exception sau batch trong `TransactionTemplate`; kiểm tra rollback.
9. Gây constraint violation ở entry giữa, kiểm tra `BatchUpdateException`/cause chain và transaction outcome.
10. Cấu hình Java DSL Spring Integration 7.x `Jdbc.outboundAdapter` với `MessagePreparedStatementSetter`.
11. Gửi một `Message<List<InventoryUpdate>>`; xác minh handler cập nhật tất cả rows.
12. Chèn `.split()` trước handler; so sánh số JDBC batch executions.
13. Dùng `JdbcMessageHandler` trực tiếp trong Spring Integration 6.x hoặc XML `int-jdbc:outbound-channel-adapter`.
14. Bật `keysGenerated` trên cấu hình thực hành và xác định vì sao không dùng batch mode.
15. Tạo inbound JDBC polling `maxRows=100`, phân biệt với `maxMessagesPerPoll=1`.
16. So sánh inbound `updatePerRow(false)` với `updatePerRow(true)` và đo số SQL executions.
17. Nối inbound JDBC với outbound batch trong cùng transactional poller và `DirectChannel`; gây lỗi để kiểm tra rollback cả hai tables.
18. Chèn `ExecutorChannel` trước outbound handler; mô tả recovery khi inbound đã CLAIMED.
19. Dùng Aggregator size/timeout để gom message đơn thành `List`; xác nhận payload cuối cùng là `Iterable`.
20. Thử batch sizes `1,10,50,100,250,500` trên PostgreSQL và đo p95/p99, DB CPU, lock waits, pool wait.
21. So sánh PostgreSQL `reWriteBatchedInserts=true/false` với batch INSERT phù hợp.
22. So sánh MySQL `rewriteBatchedStatements=true/false` và update count sau `ON DUPLICATE KEY UPDATE`.
23. Tạo các nullable parameters, chỉ định `Types.VARCHAR/BIGINT` và đo metadata lookup overhead.
24. Tạo hai commands cùng itemId với expected version khác nhau; kiểm tra ordering/conflict.
25. Gửi duplicate Kafka/JMS events sau DB COMMIT nhưng trước ACK; dùng processed-event UNIQUE để bảo vệ effect.
26. Thử một input 100.000 rows, đọc theo pages và bounded batches thay vì đưa tất cả vào RAM.
27. Đổi từ JDBC batch sang staging table + set-based UPDATE trên PostgreSQL, so sánh hiệu năng và correctness.
28. Xây dashboard theo batch size, duration, failures, success-no-info, queue wait, outbox age và Hikari pending.
29. Lập runbook xử lý poison event trong một batch, phân biệt transient retry, quarantine và manual replay.
30. Viết test trên DB production-compatible để kiểm tra driver batching, transactions và crash windows.

**Tình huống tổng hợp:** một consumer Kafka nhận 500 thay đổi tồn kho mỗi đợt, muốn gom thành JDBC batch size 100. Trong lô thứ ba có một record sai dữ liệu; DB đã xử lý một số entries trước khi JDBC báo lỗi. Sau khi sửa dữ liệu, consumer bị restart đúng lúc transaction commit nhưng offset Kafka chưa commit. Hãy thiết kế **transaction boundaries, update counts, dedupe theo eventId, partial-batch policy, timeout, retry/ACK và metrics** sao cho không mất event, không âm thầm ghi sai tồn kho và không gây retry storm.

## 33. Tài liệu tham khảo

- [Spring Integration Reference — JDBC Outbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/outbound-channel-adapter.html): `JdbcMessageHandler` xử lý payload `Iterable` bằng `JdbcOperations.batchUpdate()` từ 5.1, `MessagePreparedStatementSetter`, giới hạn `keysGenerated`.
- [Spring Integration Reference — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): payload `List`, `maxRows`, `maxMessagesPerPoll`, update SQL, `updatePerRow` và transactional poller.
- [Spring Integration Reference — Java DSL for JDBC](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.outboundAdapter` và `Jdbc.inboundAdapter` từ 7.0.
- [Spring Integration Reference — JDBC Outbound Gateway](https://docs.spring.io/spring-integration/reference/jdbc/outbound-gateway.html): `UPDATED` reply khác một one-way outbound adapter, generated keys và SELECT reply.
- [Spring Framework — JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html): `BatchPreparedStatementSetter`, `NamedParameterJdbcTemplate.batchUpdate`, `SqlParameterSourceUtils`, `ParameterizedPreparedStatementSetter` và `int[][]`.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, named params, JDBC types, `JdbcClient`.
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): transaction ở poller, đồng bộ channel và thread boundaries.
- [Java SE API — Statement](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/Statement.html): JDBC batch update counts, `SUCCESS_NO_INFO`, `EXECUTE_FAILED`.
- [Java SE API — BatchUpdateException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/BatchUpdateException.html): partial update counts khi một batch entry lỗi.
- [PostgreSQL JDBC Driver Documentation](https://jdbc.postgresql.org/documentation/use/): connection parameters, `reWriteBatchedInserts` và JDBC driver behavior.
- [MySQL Connector/J — Performance Extensions](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html): `rewriteBatchedStatements`, generated keys/count limitations và packet considerations.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, rollback rules, proxy và propagation.

> **Ghi nhớ:** Muốn tăng hiệu năng JDBC trong Spring Integration phải **phân biệt batch message, JDBC driver batch và một SQL set-based statement**. `JdbcMessageHandler` batch khi nhận payload `Iterable` (không dùng `keysGenerated`); `JdbcTemplate.batchUpdate` cho phép quản lý parameter sets, chunk sizes và update counts rõ ràng. `maxRows` của inbound adapter khác `maxMessagesPerPoll` của poller; `updatePerRow` không tự là driver batching. Tối ưu có giá trị khi được đo trên DB/driver thực, đặt trong transaction đúng, có bounded buffers, retry, outbox và idempotent handling cho những lô được gửi lại.
