# Prepared statement và parameter binding trong Cassandra

## 1. Vì sao cần chuẩn bị CQL trước khi truyền dữ liệu?

Một luồng Spring Integration nhận sự kiện `OrderPaid` từ JMS, sau đó lưu vào Apache Cassandra. Cách viết câu lệnh bằng nối chuỗi có vẻ đơn giản:

~~~java
// KHÔNG LÀM: dữ liệu từ nguồn ngoài bị ghép trực tiếp thành CQL.
String unsafe = "SELECT event_id FROM order_event WHERE event_id = '"
        + eventId + "'";
~~~

Nếu `eventId` chứa dấu nháy hoặc ký tự CQL đặc biệt, câu lệnh có thể hỏng. Quan trọng hơn, mã ghép chuỗi tạo ra bề mặt **CQL injection** và một chuỗi CQL khác cho mỗi giá trị, gây tốn tài nguyên parse/prepare và khó kiểm soát truy vấn.

Giải pháp đúng là **prepared statement và parameter binding**:

~~~sql
SELECT event_id, order_id, event_type
FROM order_event
WHERE event_id = ?;
~~~

Ứng dụng chuẩn bị **câu CQL ổn định**, sau đó bind riêng giá trị `eventId` vào dấu `?`. Giá trị được driver mã hóa theo kiểu CQL; nó **không trở thành cú pháp câu lệnh**. Driver Cassandra 4.x còn giữ **prepared-statement cache theo `CqlSession`**, và Cassandra có cache/metadata phục vụ thực thi lặp lại.

Trong module **SPRING_INTEGRATION_ADAPTERS**, các inbound/outbound adapter, gateway, poller và `MessageChannel` kết nối file, SFTP, HTTP, JMS, AMQP, Kafka cùng cơ sở dữ liệu, đồng thời kiểm soát hợp đồng message, lỗi và vòng đời kết nối. Thuộc chương **Adapter Cassandra**, bài **Prepared statement và parameter binding** tập trung vào cách chuyển một Spring Message thành thao tác CQL an toàn, đúng kiểu và có thể kiểm thử.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt `SimpleStatement`, `PreparedStatement` và `BoundStatement` của Java Driver.
2. Sử dụng positional markers `?` và named markers `:name` đúng ngữ nghĩa.
3. Viết code trực tiếp với `CqlSession.prepare(...)`/`bind(...)`, hiểu quy tắc immutable và cache.
4. Dùng `CqlTemplate`/`ReactiveCqlTemplate` và `PreparedStatementCreator`/`PreparedStatementBinder` của Spring Data Cassandra.
5. Truyền tham số từ `payload`/`headers` trong **Spring Integration Cassandra outbound gateway/adapter**.
6. Phân biệt bind value với tên bảng/cột, CQL `NULL` với `UNSET`, batch/ingest và conditional write.
7. Kiểm soát retry, idempotency, paging, timeout và ranh giới acknowledgment với JMS/Kafka.

## 2. SimpleStatement, PreparedStatement và BoundStatement

Trong Java Driver 4.x, ba đối tượng quan trọng để hiểu **prepared binding** là:

| Loại | Cách tạo | Có bind sẵn? | Khi nào dùng? |
|---|---|---|---|
| `SimpleStatement` | `SimpleStatement.newInstance(cql)` hoặc builder | Có thể giữ positional/named values để tầng trên prepare/bind | CQL ít lặp hoặc xây dựng statement trước khi qua template |
| `PreparedStatement` | `CqlSession.prepare(cql)` | **Chưa** mang giá trị cụ thể của một execution | CQL lặp lại nhiều lần, cùng cấu trúc |
| `BoundStatement` | `prepared.bind(values...)` hoặc `prepared.boundStatementBuilder()` | **Có**, chứa giá trị đã được mã hóa/kiểm tra kiểu | Đối tượng gửi tới `CqlSession.execute(...)` |

**Phân loại chính xác ở tầng driver:** những `Statement<?>` được gửi để execute gồm `SimpleStatement`, `BoundStatement` và `BatchStatement`; còn `PreparedStatement` là **kết quả của bước prepare, chưa phải một statement đã bind để execute**. Bảng trên tập trung vào ba đối tượng phục vụ quá trình prepare/bind. Batch có thể chứa các `BoundStatement` và có ngữ nghĩa riêng về partition, consistency và chi phí coordinator.

### 2.1. Trình tự chuẩn bị và chạy

~~~mermaid
sequenceDiagram
    participant App as Spring service / handler
    participant Driver as Java driver CqlSession
    participant Broker as Cassandra coordinator

    App->>Driver: prepare("SELECT ... WHERE event_id = ?")
    Driver->>Broker: PREPARE CQL (nếu chưa cache)
    Broker-->>Driver: Prepared ID + metadata kiểu tham số
    Driver-->>App: PreparedStatement
    App->>App: bind("evt-4001") -> BoundStatement
    App->>Driver: execute(bound)
    Driver->>Broker: EXECUTE Prepared ID + encoded values
    Broker-->>Driver: Rows / error
    Driver-->>App: ResultSet / exception
~~~

**Prepared statement là một kế hoạch đã phân tích cú pháp và metadata cần thiết, không phải lệnh đã chứa giá trị của một event.** Mỗi request dùng giá trị khác cần bind ra `BoundStatement` phù hợp. Khi chạy với giá trị `evt-4002`, ứng dụng có thể dùng **cùng `PreparedStatement`**, tạo một `BoundStatement` khác.

### 2.2. Tại sao prepared statements hữu ích?

- **An toàn hơn với giá trị:** bind value không bị phân tích như CQL syntax, giảm rủi ro injection qua data.
- **Hiệu năng cho query lặp:** coordinator không phải parse lại cùng CQL ở mỗi execution theo cơ chế prepared-cache của provider.
- **Thông tin kiểu sớm:** metadata giúp driver kiểm tra codecs/type của bind variables.
- **Routing:** driver có thể suy ra partition key/routing key khi đầy đủ bind values.
- **Hạn chế wire payload:** Prepared ID + values có thể gọn hơn gửi full CQL string lặp đi lặp lại.

Không phải mọi truy vấn đều nên prepare: một CQL DDL chạy đúng một lần khi migration có thể dùng `SimpleStatement`. Prepared statements **không** tự tăng consistency level, tạo transaction đa bảng hay làm các mutations không-idempotent trở nên an toàn để retry.

## 3. Schema và môi trường minh họa

Ví dụ sử dụng Java 17+, Spring Integration 6+/7+, Spring Data Cassandra tương thích và Cassandra test cluster.

~~~sql
-- Chỉ dùng SimpleStrategy cho cluster thử nghiệm một node.
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    schema_version int,
    occurred_at timestamp,
    payload_json text
);
~~~

`event_id` là partition key vì bài tập cần đọc/ghi theo `eventId`. Nếu nghiệp vụ phải lấy toàn bộ event theo `orderId`, cần thiết kế bảng khác với partition/clustering key thích hợp. Cassandra tối ưu theo **query pattern**, không phải cứ dùng prepared statement là mọi `WHERE` đều nhanh.

Ví dụ sự kiện:

~~~json
{
  "eventId": "evt-4001",
  "orderId": "ORD-4001",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T03:00:00Z"
}
~~~

### 3.1. Dependencies

Với Spring Boot có BOM quản lý các phiên bản tương thích:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
</dependency>
<!-- Cho ReactiveCassandraOperations và Cassandra adapter/gateway có sẵn. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cassandra</artifactId>
</dependency>
~~~

Không bắt buộc mọi ứng dụng thêm cả imperative và reactive starter; tùy flow mà chọn. Nếu chỉ chạy driver/CqlTemplate không có Spring Integration, phần dependency integration là không cần thiết.

Một cấu hình Spring Boot cho môi trường lab:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

`datacenter1` phải khớp local DC của cluster. Đây là `application.yml` minh họa, **không phải** YAML metadata của bài học. Keyspace/table cần được tạo bằng script/migration có chủ đích; không tự suy ra starter tạo chúng sẵn.

### 3.2. CqlSession sống lâu

`CqlSession` là driver session thường được Spring Boot hoặc configuration bean tạo và tái sử dụng. Không gọi `CqlSession.builder()` rồi `close()` cho **từng Spring Message**: nó quản lý nhiều connection/tài nguyên và việc khởi tạo liên tục có thể làm quá tải cluster.

**Một prepared statement gắn với session đang dùng.** Nếu tạo nhiều `CqlSession` cho cùng cluster/ứng dụng không chủ đích, cache bị phân tán và số connection tăng. Trong production nên có chiến lược session lifecycle/credentials/TLS/ACL tập trung.

## 4. Positional binding: `?` phải khớp theo thứ tự

CQL có placeholders vô danh:

~~~sql
INSERT INTO order_event (
    event_id, order_id, event_type, schema_version, occurred_at, payload_json
) VALUES (?, ?, ?, ?, ?, ?);
~~~

Thứ tự bind **không dựa vào tên field Java**; `index=0` tương ứng dấu `?` đầu tiên, rồi 1, 2...

### 4.1. PreparedStatement và BoundStatement

~~~java
import java.time.Instant;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class OrderEventPreparedDao {

    private final CqlSession session;
    private final PreparedStatement insertEvent;

    public OrderEventPreparedDao(CqlSession session) {
        this.session = session;
        this.insertEvent = session.prepare("""
                INSERT INTO order_event
                (event_id, order_id, event_type,
                 schema_version, occurred_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """);
    }

    public void save(String eventId, String orderId,
                     String eventType, int version,
                     Instant occurredAt, String payloadJson) {

        BoundStatement statement = insertEvent.bind(
                eventId, orderId, eventType,
                version, occurredAt, payloadJson);

        session.execute(statement);
    }
}
~~~

Ở đây constructor chỉ `prepare(...)` một lần cho DAO khi khởi tạo; các lần `save(...)` gọi `bind(...)` tạo statement mới với values khác. Giả định Cassandra session dùng keyspace `shop_integration` và table tồn tại. Với `Instant`, driver cần codec phù hợp cho Cassandra `timestamp` (có sẵn ở driver hiện đại).

**Tránh đảo thứ tự** `eventId` và `orderId` vì cả hai đều là `String`; lỗi này có thể **không bị Java compiler hoặc codec phát hiện**. Validate contract và dùng integration test kiểm tra bản ghi đọc lại từ DB.

### 4.2. Positional setter tường minh

~~~java
BoundStatement bound = insertEvent.bind()
        .setString(0, eventId)
        .setString(1, orderId)
        .setString(2, eventType)
        .setInt(3, version)
        .setInstant(4, occurredAt)
        .setString(5, payloadJson);

session.execute(bound);
~~~

**Immutable là quy tắc quan trọng:** các setter `setString(...)`, `setInt(...)`, `setInstant(...)` trả về **BoundStatement mới**. Chain như ví dụ hoặc gán lại biến; không gọi setter rồi bỏ kết quả.

~~~java
// SAI: kết quả setter bị bỏ qua, statement ban đầu không thay đổi.
BoundStatement wrong = insertEvent.bind();
wrong.setString(0, eventId);

// ĐÚNG:
wrong = wrong.setString(0, eventId);
~~~

Các ví dụ ở mục này là snippets của class/method đã có biến `insertEvent`, `eventId` và `session`; không chạy độc lập ngoài context của DAO.

## 5. Named binding: `:name` và tên tham số có ý nghĩa

Khi câu CQL có nhiều biến, positional binding dễ bị đổi nhầm các field có cùng Java type. **Named markers** cho phép nêu rõ vai trò:

~~~sql
INSERT INTO order_event (
    event_id, order_id, event_type, schema_version, occurred_at, payload_json
) VALUES (
    :eventId, :orderId, :eventType, :schemaVersion, :occurredAt, :payloadJson
);
~~~

### 5.1. Driver bind theo tên

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

PreparedStatement prepared = session.prepare("""
        INSERT INTO order_event
        (event_id, order_id, event_type, schema_version, occurred_at, payload_json)
        VALUES (:eventId, :orderId, :eventType,
                :schemaVersion, :occurredAt, :payloadJson)
        """);

BoundStatement bound = prepared.bind()
        .setString("eventId", eventId)
        .setString("orderId", orderId)
        .setString("eventType", "OrderPaid")
        .setInt("schemaVersion", 1)
        .setInstant("occurredAt", occurredAt)
        .setString("payloadJson", payloadJson);

session.execute(bound);
~~~

Trong các `setXxx("name", ...)`, **không có dấu `:`** ở tên truyền vào. `eventId` ở đây là marker name, không phải tên cột Cassandra (cột là `event_id`). Khi viết CQL, chọn quy tắc tên nhất quán, tránh các tên marker trùng nhau nếu chúng biểu diễn hai dữ liệu khác nhau.

### 5.2. Named binding trên CQL có `?`

Driver có thể gán tên cho các marker vô danh dựa trên **cột mà marker tham chiếu**. Ví dụ:

~~~sql
SELECT event_type
FROM order_event
WHERE event_id = ?;
~~~

Trong một số tình huống, bạn có thể bind bằng tên cột `event_id` thay vì index. Tuy nhiên, khi **cùng một cột xuất hiện nhiều lần** (ví dụ `occurred_at > ? AND occurred_at < ?`), tên tự suy ra trở nên mơ hồ.

**Khuyến nghị:** sử dụng positional indices cho CQL viết bằng `?`, hoặc khai báo **named markers duy nhất** cho mỗi vị trí cần phân biệt. Đừng tự giả định cách suy ra tên mặc định của driver áp dụng cho mọi biểu thức phức tạp.

### 5.3. Chọn giữa positional và named binding

| Tiêu chí | Positional `?` | Named `:name` |
|---|---|---|
| Viết nhanh cho vài biến | Rất tiện | Hơi dài hơn |
| Nhiều biến cùng type | Dễ bị đảo nhầm | Dễ đọc và review |
| Tên marker trong contract | Không có | Có, nhưng là tên **CQL marker**, không phải JSON field tự động |
| Bind bằng driver | `bind(v1, v2)`, `setString(0, ...)` | `setString("eventId", ...)` |
| Với Spring Data `CqlTemplate` cơ bản | Varargs dùng positional theo thứ tự | Dùng callback nếu cần kiểm soát tên |
| Với Spring Integration `.query(...)` | Thường dùng query named markers | DSL `.parameter("name", ...)` ánh xạ từ message |

Không dùng một `Map` thiếu validation để tạo tên marker động từ dữ liệu HTTP/JMS. Mapper và query phải có tập tên **được định nghĩa trước**.

## 6. `BoundStatementBuilder`: tối ưu thao tác bind và option cho từng request

Mỗi setter trên `BoundStatement` immutable có thể tạo object mới. Khi nhiều tham số hoặc cần cấu hình consistency/timeout riêng cho một operation, sử dụng `boundStatementBuilder()`:

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

BoundStatement toSend = prepared.boundStatementBuilder()
        .setString("eventId", eventId)
        .setString("orderId", orderId)
        .setString("eventType", "OrderPaid")
        .setInt("schemaVersion", 1)
        .setInstant("occurredAt", occurredAt)
        .setString("payloadJson", payloadJson)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(2))
        .setIdempotent(true)
        .build();

session.execute(toSend);
~~~

Đây là fragment trên **prepared statement có named markers**, không phải lời khuyên mặc định dùng `LOCAL_QUORUM` hoặc timeout 2 giây trong mọi production cluster. Consistency phải phù hợp replication topology, p99 và nghiệp vụ; `setIdempotent(true)` chỉ phù hợp khi câu CQL và business effect thật sự an toàn khi driver retry.

### 6.1. Immutable statement khác mutable builder

- `PreparedStatement` được dùng lại để tạo các lần bind độc lập.
- `BoundStatement` được driver xem là immutable; setter trả về instance mới.
- `BoundStatementBuilder` là đối tượng xây dựng cho một lần bind, tạo `BoundStatement` qua `build()`.
- Không lưu một builder mutable dùng chung cho nhiều threads/calls; hãy tạo builder mới cho từng operation.

Đối với một service nhận nhiều message song song, **PreparedStatement có thể dùng chung**, nhưng mỗi event nên có **BoundStatement riêng**. Không dùng một mutable builder global rồi sửa `eventId` từ các threads khác nhau.

### 6.2. Prepared statement và routing key

Prepared metadata có thể cho driver biết biến nào tham gia **partition key**, ví dụ `event_id`. Khi bind đầy đủ, driver có thể suy ra routing key và ưu tiên node có replica liên quan (token-aware routing), giúp giảm hop.

Tuy nhiên:

- Thiếu bind value của partition key có thể làm query không hợp lệ hoặc mất cơ sở routing.
- Prepared metadata không sửa được mô hình bảng Cassandra sai.
- Partition key phân phối không đều vẫn có thể tạo **hot partitions**.
- Với câu CQL không thể suy ra partition key, có thể cần routing metadata được chỉ định rõ trong statement/driver configuration.

Để tối ưu read/write throughput, đo **coordinator node distribution** và query latency thực tế thay vì chỉ dựa vào việc “query đã prepare”.

## 7. Null và UNSET: sự khác nhau có thể gây mất dữ liệu

Đây là một trong những khác biệt quan trọng nhất khi binding Cassandra values:

| Trạng thái bind | Ý nghĩa | Hậu quả điển hình |
|---|---|---|
| **Giá trị cụ thể** | Set một CQL value | INSERT/UPDATE cột tương ứng |
| **CQL `NULL`** | Đặt biến bằng null | Trong mutation có thể tạo **tombstone/xóa giá trị** |
| **`UNSET`** | Không đặt giá trị cho marker | Theo protocol/provider hỗ trợ, mutation bỏ qua field đó |
| **Thiếu bind ngoài ý muốn** | Programmer quên marker | Có thể gây lỗi hoặc tạo hành vi ngoài mong đợi tùy statement/protocol |

### 7.1. Bind null tường minh

~~~java
// Trên một BoundStatement của CQL UPDATE có named marker :payloadJson.
BoundStatement withNull = preparedUpdate.bind()
        .setString("eventId", eventId)
        .setToNull("payloadJson");
session.execute(withNull);
~~~

Trong một UPDATE, null có thể tạo **tombstone** để thể hiện cột đã bị xóa. Nó **không** có nghĩa “giữ nguyên giá trị cũ”.

### 7.2. UNSET khi không muốn chạm cột

~~~java
BoundStatement withoutPayloadUpdate = preparedUpdate.bind()
        .setString("eventId", eventId)
        .unset("payloadJson");
session.execute(withoutPayloadUpdate);
~~~

`UNSET` được hỗ trợ từ Cassandra native protocol V4 (Cassandra 2.2+). Khi sử dụng với mutation, unset có thể giữ nguyên giá trị cột hiện có. Không coi `unset` và `setToNull` là tương đương.

### 7.3. Ví dụ UPDATE partial

~~~sql
UPDATE order_event
SET event_type = :eventType, payload_json = :payloadJson
WHERE event_id = :eventId;
~~~

Nếu phía API chỉ muốn cập nhật `eventType`, còn JSON payload cũ giữ nguyên, hãy dùng `UNSET` cho `payloadJson` hoặc xây một câu UPDATE khác chỉ chứa cột cần cập nhật. **Không** tự biến một field thiếu trong JSON thành CQL `NULL`, vì điều đó có thể tạo tombstone và làm mất dữ liệu.

### 7.4. Tránh suy luận sai khi dùng Java `null`

Một lệnh `prepared.bind(a, null, c)` không tự biểu đạt rõ bạn muốn CQL `NULL` hay marker `UNSET`. Với dữ liệu partial update, nên chọn tường minh `setToNull(...)` hoặc `unset(...)` để code review và integration test thấy được ý định. Nếu ứng dụng dùng Spring Data entity mapper, kiểm tra null-saving strategy, version và write options tương ứng; **đừng lấy behavior của một DAO mapper khác để suy ngược về CqlTemplate**.

## 8. Bind kiểu dữ liệu: String không thay thế mọi Cassandra codec

Mỗi marker được Cassandra chuẩn bị với **CQL type**. Driver dùng codecs để chuyển Java object thành bytes đúng kiểu. Một vài mapping thông dụng:

| Cassandra type | Java value thích hợp | Driver setter ví dụ |
|---|---|---|
| `text`, `varchar` | `String` | `setString(...)` |
| `int` | `int` / `Integer` | `setInt(...)` |
| `bigint` | `long` / `Long` | `setLong(...)` |
| `boolean` | `boolean` | `setBoolean(...)` |
| `uuid` | `java.util.UUID` | `setUuid(...)` |
| `timestamp` | `java.time.Instant` | `setInstant(...)` |
| `date` | `java.time.LocalDate` | `setLocalDate(...)` |
| `decimal` | `java.math.BigDecimal` | `setBigDecimal(...)` |
| `blob` | `java.nio.ByteBuffer` | `setByteBuffer(...)` |
| `list<text>` | `List<String>` | `setList(index, values, String.class)` |

Ví dụ schema `schema_version int` và Java producer đưa `"1"` dạng String. Driver không bắt buộc tự parse String thành int trong mọi codec path. Nên chuyển đổi và validate **trước bind**:

~~~java
int version;
try {
    version = Integer.parseInt(versionFromInput);
} catch (NumberFormatException ex) {
    throw new IllegalArgumentException("schemaVersion phải là số nguyên", ex);
}

BoundStatement bound = prepared.bind()
        .setString("eventId", eventId)
        .setInt("schemaVersion", version);
~~~

Đây là fragment cho một query có `:eventId` và `:schemaVersion`. Không dùng `setString("schemaVersion", "1")` chỉ vì JSON đầu vào là chuỗi.

### 8.1. CQL collection, UDT và codec

Các cột `list<text>`, `set<uuid>`, `map<text,int>`, UDT/tuple/vector có **type parameters** hoặc codec phức tạp. Kiểm tra tương thích Java generic type và CQL schema; ví dụ:

~~~java
BoundStatement bound = preparedTags.bind()
        .setString("eventId", eventId)
        .setList("tags", java.util.List.of("billing", "validated"), String.class);
~~~

`preparedTags` ở đây là một prepared UPDATE/INSERT có marker `:tags` cho cột `list<text>`. Dùng các API driver tương ứng với collection type; không serialize toàn bộ `List<String>` thành một chuỗi CSV nếu table mong `list<text>`.

### 8.2. Trường hợp schema/type thay đổi

Khi thay đổi CQL schema trong môi trường đang chạy, metadata của prepared statement/driver có thể không đồng bộ tức thời. Với Cassandra 3 trở xuống, prepared `SELECT *` đặc biệt dễ gặp vấn đề khi thêm/xóa cột vì result metadata đã được cache. Tốt hơn:

~~~sql
SELECT event_id, order_id, event_type
FROM order_event
WHERE event_id = ?;
~~~

Chọn rõ các columns, phối hợp schema migration và triển khai code tương thích ngược, đồng thời có integration test sau migration. **Prepared statements không thay thế migration management**.

## 9. `CqlTemplate`: prepared binding không cần tự gọi `session.prepare()`

Spring Data Cassandra cung cấp `org.springframework.data.cassandra.core.cql.CqlTemplate` và interface `CqlOperations`. Đây là API **đồng bộ** bao quanh driver, giúp tạo/reuse prepared statements, bind arguments, map rows và translate exception.

Theo tài liệu chính thức:

- `execute(String cql)`: thực thi câu CQL cố định theo đường thông thường, không có arguments để bind.
- `execute(String cql, Object... args)`: **dùng prepared statement** rồi bind positional args theo thứ tự.
- `queryForObject(String cql, Class<T>, Object... args)`: query một giá trị có bind arguments.
- Các overload nhận `PreparedStatementCreator` và `PreparedStatementBinder`: cho phép tùy biến cách prepare/bind.

### 9.1. CqlTemplate INSERT và SELECT

~~~java
import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.stereotype.Repository;

@Repository
public class EventCqlRepository {

    private final CqlOperations cql;

    public EventCqlRepository(CqlOperations cql) {
        this.cql = cql;
    }

    public void insert(String eventId, String orderId,
                       String eventType, int schemaVersion,
                       java.time.Instant occurredAt, String json) {
        cql.execute(
                "INSERT INTO order_event "
                + "(event_id, order_id, event_type, schema_version, occurred_at, payload_json) "
                + "VALUES (?, ?, ?, ?, ?, ?)",
                eventId, orderId, eventType, schemaVersion, occurredAt, json);
    }

    public String findEventType(String eventId) {
        return cql.queryForObject(
                "SELECT event_type FROM order_event WHERE event_id = ?",
                String.class, eventId);
    }
}
~~~

Spring inject một bean `CqlTemplate` triển khai `CqlOperations` đã được cấu hình bằng `SessionFactory`/`CqlSession`. Repository cần validate schema và quyền người gọi trước khi ghi; việc bind ngăn giá trị trở thành CQL syntax, nhưng **không tự cho phép mọi event/tenant truy cập database**.

### 9.2. Các callbacks để tùy biến preparation

~~~java
import java.util.List;
import org.springframework.data.cassandra.core.cql.CqlTemplate;

List<String> ids = cqlTemplate.query(
        session -> session.prepare(
                "SELECT order_id FROM order_event WHERE event_id = ?"),
        prepared -> prepared.bind("evt-4001"),
        (row, rowNum) -> row.getString("order_id"));
~~~

Đây là ví dụ chính thức về **ba callback**:

1. `PreparedStatementCreator` nhận `CqlSession`, tạo `PreparedStatement`.
2. `PreparedStatementBinder` nhận `PreparedStatement` rồi tạo `BoundStatement`.
3. `RowMapper` nhận từng Cassandra `Row` và ánh xạ ra Java type.

Nếu query trả nhiều rows, `query(...)` trả `List<T>`; `RowMapper` không tự streaming end-to-end. Với dữ liệu lớn, thiết kế partition/paging và không query toàn bảng rồi materialize thành list vô hạn.

### 9.3. Bind theo tên trong callback

Khi dùng named CQL markers, có thể:

~~~java
String cqlText = """
        SELECT order_id FROM order_event WHERE event_id = :eventId
        """;

List<String> orderIds = cqlTemplate.query(
        session -> session.prepare(cqlText),
        prepared -> prepared.bind()
                .setString("eventId", "evt-4001"),
        (row, rowNum) -> row.getString("order_id"));
~~~

Ở đây `cqlText` là **câu CQL tĩnh**; `"evt-4001"` chỉ được truyền như bound value. Nếu giá trị đến từ HTTP/JMS, lấy nó từ DTO đã validate; không chuyển cả nội dung HTTP body thành CQL query text.

### 9.4. `ArgumentPreparedStatementBinder` và `SimplePreparedStatementCreator`

Spring Data Cassandra có các utility classes:

- `SimplePreparedStatementCreator`: triển khai `PreparedStatementCreator` cho một câu CQL có sẵn.
- `ArgumentPreparedStatementBinder`: triển khai `PreparedStatementBinder` với tập arguments cho `PreparedStatement`.

Phần lớn trường hợp chỉ cần `cqlTemplate.execute(cql, values...)` hoặc `queryForObject(...)`; dùng callback/utility khi cần tùy biến rõ ràng. Spring Data và driver 4.x đã có caching; không tự viết map cache vô hạn theo event value.

### 9.5. `CassandraTemplate` và `ReactiveCassandraTemplate`

`CassandraTemplate` là API mức cao hơn, kết hợp mapping `@Table`, `@PrimaryKey`, converters và query DSL. Spring Data Cassandra **mặc định bật dùng prepared statements** cho nhiều template operations và cho phép điều chỉnh bằng `setUsePreparedStatements(...)` trên các template phù hợp.

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.data.cassandra.core.CassandraTemplate;

// Fragment trong service có CassandraTemplate được inject.
cassandraTemplate.setUsePreparedStatements(true);

MappedOrderEvent row = cassandraTemplate.selectOne(
        SimpleStatement.newInstance(
                "SELECT event_id, order_id, event_type, schema_version, "
                + "occurred_at, payload_json FROM order_event WHERE event_id = ?",
                "evt-4001"),
        MappedOrderEvent.class);
~~~

`MappedOrderEvent` ở ví dụ là **entity do ứng dụng định nghĩa với `@Table("order_event")`, primary key và các field được map đúng với bảng**; khác với DTO `OrderEvent` không có annotation ở mục 12.3 chỉ dùng cho manual statement binding. **Không điều chỉnh `setUsePreparedStatements(...)` trên singleton template ở từng request**, vì nó là cấu hình chung; đặt trước khi ứng dụng bắt đầu xử lý message.

Spring Data có thể trích query và args từ `SimpleStatement` để chuẩn bị/bind; không giả định mọi custom implementation của `Statement<?>` đều có thể được template tự prepare. Các API nhận entity đã map cũng có đường tạo CQL khác với `CqlTemplate` low-level.

## 10. `ReactiveCqlTemplate`: binding và subscription

`ReactiveCqlTemplate` và `ReactiveCqlOperations` có các method kiểu tương tự nhưng trả **`Mono`/`Flux`** thay vì chờ trực tiếp:

~~~java
import org.springframework.data.cassandra.core.cql.ReactiveCqlOperations;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class ReactiveEventCqlRepository {

    private final ReactiveCqlOperations cql;

    public ReactiveEventCqlRepository(ReactiveCqlOperations cql) {
        this.cql = cql;
    }

    public Mono<Boolean> insert(String eventId, String orderId,
                                String eventType, int version,
                                java.time.Instant occurredAt, String json) {
        return cql.execute(
                "INSERT INTO order_event "
                + "(event_id, order_id, event_type, schema_version, occurred_at, payload_json) "
                + "VALUES (?, ?, ?, ?, ?, ?)",
                eventId, orderId, eventType, version, occurredAt, json);
    }

    public Mono<String> findType(String eventId) {
        return cql.queryForObject(
                "SELECT event_type FROM order_event WHERE event_id = ?",
                String.class, eventId);
    }
}
~~~

**Reactive publisher là lazy**: trả `Mono` không có nghĩa đã chạy I/O. Subscription phải đến từ WebFlux/Reactive IntegrationFlow hoặc một subscriber được quản lý. Không gọi repository `insert(...)` rồi bỏ quên `Mono`:

~~~java
// SAI: bỏ rơi publisher, operation có thể không chạy.
reactiveRepository.insert(eventId, orderId, eventType, 1, now, json);

// ĐÚNG: method trong service có reactiveRepository đã được inject;
// caller/framework sẽ subscribe vào Mono được trả về.
public Mono<Void> saveReactive(
        String eventId, String orderId, String eventType,
        java.time.Instant now, String json) {
    return reactiveRepository.insert(eventId, orderId, eventType, 1, now, json)
            .then();
}
~~~

Đoạn thứ hai là method minh họa trong service có `reactiveRepository` đã được inject, không phải một class độc lập. Không dùng `Mono.block()` trên Reactor/WebFlux event-loop: làm block thread, có thể gây lỗi hoặc giảm throughput.

### 10.1. Prepared callbacks trong reactive

~~~java
reactiveCqlTemplate.query(
        session -> session.prepare(
                "SELECT order_id FROM order_event WHERE event_id = ?"),
        prepared -> prepared.bind("evt-4001"),
        (row, rowNum) -> row.getString("order_id"));
~~~

Phương thức trả một `Flux<String>` (theo overload dùng RowMapper). Nhờ vậy Spring Data còn hỗ trợ trường hợp cần kiểm soát preparation/binding mà không phải viết driver reactive bridging riêng trong mọi service.

### 10.2. Error signal xảy ra khi thực thi

~~~java
return reactiveRepository.insert(
                eventId, orderId, eventType, 1, now, json)
        .doOnError(ex -> log.warn("Cassandra error eventId={}", eventId, ex))
        .then();
~~~

Đây là fragment service đã có `log`. `doOnError` chỉ quan sát; nó không biến một write thất bại thành thành công. Retry, nếu cần, phải có giới hạn và phân loại lỗi. Đối với thao tác không idempotent, retry có thể tạo side effect lặp.

## 11. Driver cache, prepared metadata và vấn đề tạo CQL động

Với **Java Driver 4+**, prepared statements được cache ở cấp **`CqlSession`**. Gọi `session.prepare(...)` lặp lại cùng query string có thể tìm thấy statement đã cache, không nhất thiết gửi PREPARE tới broker mỗi lần.

### 11.1. Cache key không phụ thuộc giá trị đã bind

~~~text
Chuỗi CQL cố định:
  SELECT event_type FROM order_event WHERE event_id = ?

Bind eventId:
  evt-4001  -> BoundStatement A
  evt-4002  -> BoundStatement B
  evt-4003  -> BoundStatement C

PreparedStatement:
  Một cấu trúc CQL có thể được reuse cho cả ba lần bind.
~~~

Nếu code nối trực tiếp mỗi `eventId` vào query string, driver nhìn thấy **nhiều CQL khác nhau**, giảm cache hit và có thể tạo nhiều prepared entries trên cluster. Không tối ưu bằng cách prepare một câu lệnh mới cho mỗi input value.

### 11.2. Cache còn xét execution parameters

Driver docs nêu cache dựa trên **query text chính xác** và các execution attributes khi prepare (chẳng hạn consistency được đặt trên `SimpleStatement` đưa vào `prepare`). Hai chuỗi chỉ khác whitespace/casing hoặc prepared config có thể tạo cache entries khác nhau.

Vì thế:

- Dùng constant query string hoặc một DAO khởi tạo prepared statements một lần.
- Đừng tạo hàng triệu phiên bản CQL bằng cách nối giá trị nghiệp vụ, tên bảng động hoặc danh sách field tùy ý.
- Với các execution profiles khác nhau, cân nhắc chuẩn hóa cách chuẩn bị và setting per-operation.
- Đo `cql-prepared-cache-size` (theo driver/version metric) và số PREPARE/UNPREPARED events nếu cần.

### 11.3. Reprepare khi node restart/failover

Prepared statement **không phải một file SQL được lưu vĩnh viễn trong ứng dụng**. Mỗi Cassandra coordinator/node có cơ chế cache riêng; khi một node chưa biết prepared ID, driver có thể xử lý `UNPREPARED` và gửi lại PREPARE.

Driver 4.x hỗ trợ pre-prepare trên nodes khác và reprepare khi node trở lại. Tuy vậy:

- Reprepare có chi phí; với nhiều câu CQL unique, khởi động/failover có thể tạo spike.
- Không cần tự triển khai cơ chế nhận `UNPREPARED` và gửi lại query ở mọi handler, trừ khi driver/provider đòi hỏi.
- Khi schema đổi, metadata type/result có thể cũ; phối hợp migration và restart/reprepare/version compatibility khi cần.

### 11.4. Prepared không phải hiệu năng tối ưu cho query thiết kế sai

`SELECT * FROM order_event` không có partition predicate vẫn có thể đắt đỏ dù đã prepare. Câu UPDATE/DELETE nhiều partition hoặc logged batch khổng lồ vẫn có chi phí lớn. Query design, partition distribution, page size, consistency và backpressure thường quan trọng không kém prepared cache.

## 12. Spring Integration: binding từ Spring Message sang Cassandra

Spring Integration Cassandra (từ **6.0**) cung cấp **Cassandra outbound channel adapter** và **Cassandra outbound gateway**. Cả hai dựa trên `CassandraMessageHandler` và `ReactiveCassandraOperations`, **không nhận `CqlTemplate` imperative** vào constructor.

~~~mermaid
flowchart LR
    A["JMS/HTTP inbound"] --> B["Validate + convert"]
    B --> C["Spring Message: payload + headers"]
    C --> D{"Cần reply?"}
    D -->|"Không"| E["Cassandra outbound adapter"]
    D -->|"Có"| F["Cassandra outbound gateway"]
    E --> G["CassandraMessageHandler: STATEMENT"]
    F --> G
    G --> H["ReactiveCassandraOperations"]
    H --> I[("Cassandra")]
    F -. "Result / Error" .-> J["replyChannel / reactive output"]
~~~

Với những câu CQL có dữ liệu từ Spring Message:

- `.query(String)` + `.parameter(name, ...)` hỗ trợ **named parameters** dựa trên `payload` và `headers`; đặc biệt phù hợp với SELECT/gateway.
- `.statementFunction(...)` hoặc `.statementExpression(...)` tạo một driver `Statement<?>` dựa trên message.
- `.ingestQuery(...)` thực hiện INSERT hàng loạt bằng ma trận `List<List<?>>`.
- `Type.INSERT/UPDATE/DELETE` dùng entity được map bằng `@Table`; những mode này **không tự nhận JSON String và suy ra bindings**.

### 12.1. Outbound gateway SELECT với named parameters

Giả sử input là Spring Message có payload `String eventId`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow findEventFlow(ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("findEventRequests")
            .handle(Cassandra.outboundGateway(operations)
                    .query("SELECT event_id, order_id, event_type, "
                           + "schema_version FROM order_event "
                           + "WHERE event_id = :eventId")
                    .parameter("eventId", "payload"))
            .channel("findEventResults")
            .get();
}
~~~

Ở đây `.query(...)` chuyển handler sang chế độ **STATEMENT**, `:eventId` là **CQL named marker**, còn `"payload"` là **SpEL expression** được đánh giá trên Spring Message. Hai cách dùng dấu hai chấm rất khác: `:eventId` là cú pháp CQL, `payload` là property của Spring Message.

Với gateway async mặc định, kết quả có thể là reactive publisher/response theo operation và channel; kiểm tra payload type trên `findEventResults` và có consumer thích hợp. Nếu cần kết quả đồng bộ trong một luồng imperative, thêm cấu hình endpoint `async(false)` nhưng không gọi blocking handler trên WebFlux event-loop.

### 12.2. Bind từ headers và payload, có validation

Ví dụ một lookup có giới hạn số hàng:

~~~java
.handle(Cassandra.outboundGateway(operations)
        .query("SELECT event_id, order_id, event_type "
               + "FROM order_event WHERE event_id = :eventId LIMIT :limit")
        .parameter("eventId", "payload")
        .parameter("limit", message -> message.getHeaders().get("limit")))
~~~

Đây là fragment Java DSL trong flow đã có `operations`. Một header `limit` thiếu, kiểu `String` hay vượt giới hạn có thể gây lỗi binding hoặc tạo query quá tốn tài nguyên. **Validate và chuẩn hóa limit thành `int` có trần** (ví dụ 1..100) trước khi đến Cassandra endpoint.

`.parameter(name, expression)` hỗ trợ `String` SpEL, đối tượng `Expression` hoặc Java `Function<Message<?>, ?>`. **`parameterExpressions` chỉ dùng với `query(String)`**; không gắn thêm chúng vào một handler `statementFunction` rồi mong tự bind lần thứ hai.

### 12.3. StatementFunction nhận PreparedStatement đã tạo sẵn

Trường hợp cần **đích danh chuẩn bị và cache một câu INSERT**, có thể tạo bean `PreparedStatement` rồi bind theo message:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean("insertEventPreparedStatement")
public PreparedStatement insertEventPreparedStatement(CqlSession session) {
    return session.prepare("""
            INSERT INTO order_event
            (event_id, order_id, event_type, schema_version, occurred_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """);
}

@Bean
public IntegrationFlow insertPreparedEventFlow(
        ReactiveCassandraOperations operations,
        PreparedStatement insertEventPreparedStatement) {
    return IntegrationFlow.from("preparedEventWrites")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        OrderEvent event = (OrderEvent) message.getPayload();
                        return insertEventPreparedStatement.bind(
                                event.eventId(),
                                event.orderId(),
                                event.eventType(),
                                event.schemaVersion(),
                                event.occurredAt(),
                                event.payloadJson());
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Entity/DTO được dùng ở ví dụ:

~~~java
import java.time.Instant;

public record OrderEvent(
        String eventId,
        String orderId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String payloadJson) {
}
~~~

Trong mode **STATEMENT** này, handler nhận `BoundStatement` thông qua `statementFunction(...)`; DTO `OrderEvent` **không cần** `@Table` nếu chỉ dùng để bind statement thủ công. Ngược lại, dùng `Type.INSERT` theo Spring Data mapping sẽ yêu cầu entity `@Table` đúng chuẩn.

**Điều kiện vận hành:** `insertEventPreparedStatement(...)` chuẩn bị CQL khi bean khởi tạo, vì vậy schema phải được provision trước khi app chạy. Nếu migration chưa tạo table, startup có thể lỗi ngay tại PREPARE. Điều này đôi khi tốt (fail-fast), nhưng cần phối hợp thứ tự deployment.

### 12.4. Vì sao không dùng `new SimpleStatement("..."+payload)`?

Một `SimpleStatement` vẫn có thể dùng **positional values** mà không nối dữ liệu thành CQL:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

return SimpleStatement.newInstance(
        "INSERT INTO order_event "
        + "(event_id, order_id, event_type, schema_version, occurred_at, payload_json) "
        + "VALUES (?, ?, ?, ?, ?, ?)",
        event.eventId(), event.orderId(), event.eventType(),
        event.schemaVersion(), event.occurredAt(), event.payloadJson());
~~~

Đây là fragment return trong `statementFunction(...)`. Với một số Spring Data template APIs, `SimpleStatement` mang CQL + values có thể được template **prepare và bind** trước khi thực thi. Nhưng việc đó phụ thuộc đường API cụ thể; nếu yêu cầu bảo đảm **driver prepared statement**, ví dụ `PreparedStatement.bind(...)` ở mục 12.3 minh bạch hơn.

### 12.5. Một chiều hay có reply?

| Endpoint | Cấu hình | Caller nhận kết quả? |
|---|---|---|
| Outbound channel adapter | `Cassandra.outboundChannelAdapter(operations)` | Không sinh Spring reply; cần theo dõi completion/error |
| Outbound gateway | `Cassandra.outboundGateway(operations)` | Có reply theo operation và async/sync mode |
| Handler tự khai báo | `CassandraMessageHandler` + `setProducesReply(true/false)` | Tùy `producesReply` và `outputChannel` |

Nếu business logic cần biết **LWT `[applied]`**, SELECT results hoặc trạng thái ghi, dùng gateway/driver phù hợp để **đọc kết quả**. Một outbound adapter một chiều không tự gửi lại object `ResultSet` tới caller chỉ vì đã prepare query.

## 13. Ingest query và batch: parameter matrix không phải PreparedStatement cho từng dòng

`CassandraMessageHandler.setIngestQuery(...)` của Spring Integration nhận CQL INSERT với `?` markers và **payload `List<List<?>>`**, mỗi inner list là một hàng đúng thứ tự marker.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow batchIngestEvents(ReactiveCassandraOperations operations) {
    String ingestCql = """
            INSERT INTO order_event
            (event_id, order_id, event_type, schema_version, occurred_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """;

    return IntegrationFlow.from("batchEventWrites")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .ingestQuery(ingestCql),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Ví dụ payload gửi vào `batchEventWrites`:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.messaging.support.MessageBuilder;

List<List<Object>> values = List.of(
        List.<Object>of("evt-4001", "ORD-4001", "OrderPaid", 1,
                Instant.parse("2026-11-23T03:00:00Z"), "json-a"),
        List.<Object>of("evt-4002", "ORD-4002", "OrderPaid", 1,
                Instant.parse("2026-11-23T03:01:00Z"), "json-b")
);

batchEventWrites.send(MessageBuilder.withPayload(values).build());
~~~

`batchEventWrites` là `MessageChannel` được inject. Đoạn này chỉ minh họa **ma trận bind values**; không ngụ ý Cassandra batch có tính atomic toàn cục giống một database SQL transaction.

### 13.1. Rủi ro của ingest/batch

- **Đúng số lượng và thứ tự:** mỗi inner list phải có đúng sáu giá trị.
- **Đúng kiểu:** field `schema_version` phải là `int`, `occurred_at` phải có codec timestamp.
- **Null:** `List.of(...)` không nhận null trong Java; nếu có cột null, chọn cấu trúc phù hợp và làm rõ semantics `NULL`/`UNSET`.
- **Giới hạn kích thước:** không gom hàng chục nghìn event vào một payload vô hạn; chunk có giới hạn.
- **Partition:** một logged batch trải nhiều partitions thường đắt hơn các writes phân tán hợp lý; đo coordinator latency và cluster pressure.
- **Khôi phục:** nếu upstream retry cả batch, từng event phải có idempotency riêng; không dựa vào batch làm khóa chống trùng.

## 14. Conditional CQL và LWT: bind values không tự bảo đảm exactly-once

Cassandra `INSERT` thông thường có **upsert semantics**. Một câu lệnh INSERT lặp lại với cùng primary key có thể ghi đè/hoà nhập các giá trị cột theo timestamp và conflict resolution rules. Prepared statement chỉ giúp **phân tách CQL và dữ liệu**, không tự biến INSERT thành unique insert.

### 14.1. `IF NOT EXISTS` với PreparedStatement

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class InsertOnceDao {

    private final CqlSession session;
    private final PreparedStatement insertIfAbsent;

    public InsertOnceDao(CqlSession session) {
        this.session = session;
        this.insertIfAbsent = session.prepare("""
                INSERT INTO order_event
                (event_id, order_id, event_type, schema_version, occurred_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                IF NOT EXISTS
                """);
    }

    public boolean saveOnce(OrderEvent event) {
        ResultSet result = session.execute(insertIfAbsent.bind(
                event.eventId(), event.orderId(), event.eventType(),
                event.schemaVersion(), event.occurredAt(), event.payloadJson()));
        return result.wasApplied();
    }
}
~~~

`ResultSet.wasApplied()` cho biết condition của lightweight transaction (LWT) có được áp dụng hay không. Nếu `false`, cần kiểm tra bản ghi đang có:

- **Cùng `eventId` và cùng payload immutable**: có thể là retry/duplicate hợp lệ.
- **Cùng `eventId` nhưng nội dung khác**: đó có thể là sự cố hợp đồng dữ liệu; nên quarantine/alert, không tự coi như thành công.
- **Lỗi timeout**: trạng thái vẫn có thể không chắc chắn, cần query lại theo key/kiểm chứng idempotency.

**LWT có chi phí/độ trễ cao hơn write thường**. Không bật `IF NOT EXISTS` cho mọi thao tác chỉ vì “prepared statement tốt”. Với bảng event log immutable được thiết kế kỹ, idempotent upsert có thể đủ; với lệnh chỉ-ghi-một-lần bắt buộc, LWT phù hợp hơn khi đã đánh giá hiệu năng và semantics.

### 14.2. `setIdempotent(true)` trên statement không phải business deduplication

`BoundStatement.setIdempotent(true)`/builder tương ứng là **gợi ý cho driver retry policy**: một operation được coi an toàn để lặp lại khi kết quả chưa chắc chắn. Nó **không tự lưu danh sách event IDs** hoặc ngăn producer gửi hai JMS messages khác nhau.

| CQL operation | An toàn retry mù quáng? | Vì sao? |
|---|---|---|
| SELECT theo key | Thường có | Không thay state, nhưng trả dữ liệu ở thời điểm khác |
| INSERT immutable event theo key cố định | Thường có điều kiện | Cùng key/cùng giá trị giảm rủi ro; xem timestamp/TTL |
| INSERT với timestamp/TTL thay đổi mỗi retry | Không luôn | Lần sau có thể kéo dài TTL hoặc đổi conflict resolution |
| UPDATE set state theo version guard | Có điều kiện | Phải giữ version/conditional semantics |
| Counter increment | **Không** | Retry có thể tăng hai lần |
| Side-effect nghiệp vụ ngoài Cassandra | **Không tự động** | Driver không quản lý email/HTTP/DB khác |

Ngay cả khi statement được đánh dấu idempotent, **end-to-end exactly-once business effect** vẫn cần một hợp đồng sự kiện và cơ chế idempotency được kiểm chứng.

## 15. Parameter binding bảo vệ điều gì và không bảo vệ điều gì?

Bind parameters chỉ dùng cho **value expressions** tại những vị trí CQL cho phép. Chúng **không** là phương thức an toàn để tùy ý chọn tên keyspace/table/column hoặc chèn nguyên một CQL fragment.

### 15.1. Ví dụ sai: cho client điều khiển tên bảng

~~~java
// KHÔNG LÀM: tableName đến từ HTTP/JMS header chưa được xác thực.
String cql = "SELECT event_id FROM " + tableName
        + " WHERE event_id = ?";
~~~

Ngay cả khi `eventId` được bind đúng, tên bảng có thể chứa chuỗi bất hợp lệ hoặc phá boundary giữa các tenants. **Prepared markers không thay thế authorization** cho tên database object.

### 15.2. Chọn identifier từ allowlist

~~~java
public enum EventStore {
    PAID("order_paid_event"),
    CANCELLED("order_cancelled_event");

    private final String table;

    EventStore(String table) {
        this.table = table;
    }

    public String table() {
        return table;
    }
}
~~~

Nếu thực sự cần hai tables, người viết ứng dụng chọn `EventStore` bằng **business rules đã xác thực**, không lấy tên tự do từ client. Prepared CQL cho từng table vẫn là **hai query strings tĩnh**, với một cache entry tương ứng cho mỗi câu lệnh. Trong nhiều hệ thống, thiết kế chung một bảng với event type/partition phù hợp sẽ đơn giản hơn.

### 15.3. Các bước validation trước bind

1. **Contract:** kiểm tra `eventId` không rỗng, `schemaVersion` được hỗ trợ, độ dài JSON phù hợp.
2. **Type:** chuyển JSON strings/numbers sang Java `int`, `UUID`, `Instant`, v.v. có chủ đích.
3. **Authorization:** xác minh sender được phép truy cập tenant/partition này.
4. **Query shape:** dùng CQL tĩnh, identifiers từ allowlist, kiểm tra query theo partition key.
5. **Value binding:** truyền các Java scalar/collections tương thích codec vào `BoundStatement`.
6. **Runtime policy:** consistency, timeout, retry, tracing và giới hạn concurrency.
7. **Result:** đọc `ResultSet` hoặc reactive completion, phân biệt success, applied=false, timeout và exception.

**Không log raw bind values có PII/token/credentials** chỉ vì PREPARE/EXECUTE dễ debug. Broker, driver traces, application logs và DLQ của nguồn có thể giữ metadata hoặc payload lâu hơn dự kiến.

## 16. Timeout, transaction boundary và nguồn JMS/Kafka

Trong Spring Integration, prepared statements nằm ở **đích Cassandra**; chúng không tự tạo transaction nguyên tử với **nguồn message**.

~~~mermaid
sequenceDiagram
    participant JMS as JMS broker
    participant Adapter as Inbound adapter
    participant H as Handler / CqlTemplate
    participant DB as Cassandra
    JMS->>Adapter: OrderPaid eventId=evt-4001
    Adapter->>H: DirectChannel, payload đã validate
    H->>DB: PREPARED EXECUTE (bound values)
    DB-->>H: Write completed theo CL
    H-->>Adapter: Handler returns
    Adapter-->>JMS: JMS commit/ack
    Note over JMS,DB: Hai resource không có atomic commit chung
~~~

### 16.1. Cửa sổ lỗi thứ nhất: DB đã ghi, source chưa commit

~~~text
Cassandra write evt-4001 thành công
     -> JVM crash trước JMS commit
     -> Broker redeliver evt-4001
     -> INSERT được thực hiện lại
~~~

Nếu event log dùng key `eventId` cố định, payload immutable và semantics phù hợp, retry có thể không tạo một sự kiện thứ hai. Nếu thao tác là counter increment hoặc ghi trạng thái không có version guard, tác động có thể lặp/sai thứ tự.

### 16.2. Cửa sổ lỗi thứ hai: source commit trước Cassandra completion

~~~text
JMS listener -> ExecutorChannel / Cassandra handler async
  -> listener thấy bàn giao thành công
  -> JMS commit
  -> Cassandra async operation thất bại
  -> JMS không thể tự rollback nhận message đã commit
~~~

`CassandraMessageHandler` của Spring Integration mặc định **async**; nếu cần propagation lỗi đồng bộ qua `DirectChannel`, có thể cấu hình endpoint `async(false)`. Tuy nhiên cách này **không** tạo distributed transaction. Cần tích hợp acknowledgment boundary, durable handoff, retry/outbox hoặc cơ chế bảo vệ khác theo SLA.

### 16.3. Timeout không phải bằng chứng write chưa xảy ra

Coordinator có thể đã nhận write và replicas đã lưu nhưng response bị mất. Client nhận timeout; retry bằng cùng event ID hoặc câu điều kiện có thể được yêu cầu. Không dùng kết quả `try/catch timeout` để tự kết luận “Cassandra chưa ghi” và phát sinh một business ID mới.

### 16.4. Retry budget nhiều tầng

Một sự kiện có thể bị thử lại bởi:

- Cassandra driver retry policy.
- Spring Retry/Resilience4j ở service.
- JMS rollback và broker redelivery.
- Kafka consumer replay khi offset chưa commit.
- DLQ replay thủ công sau khi sửa lỗi.

Nếu mỗi tầng retry riêng, tổng số write attempts có thể lớn hơn nhiều dự kiến. Đặt **một retry budget end-to-end**, phân biệt transient errors với permanent contract/schema errors, và theo dõi duplicate/conflicting `eventId`.

### 16.5. `errorChannel` không thay thế DLQ

Spring Integration `errorChannel` là nơi chuyển `ErrorMessage` để quan sát/phân loại lỗi. Nó không tự đảm bảo JMS rollback, Kafka offset replay hoặc một DLQ bền vững. Trong đường đồng bộ, nếu error handler **nuốt exception**, listener nguồn có thể commit dù Cassandra operation thất bại.

Khi code chạy reactive, lỗi còn có thể xuất hiện **sau** lời gọi tạo publisher. Đảm bảo có subscriber, error handling và cách nối completion tới nguồn được thiết kế rõ.

## 17. Quan sát hoạt động và tối ưu prepared statements

Một hệ thống dùng prepared statements vẫn có thể chậm nếu model Cassandra không phù hợp, đặt timeout không thực tế hoặc tạo quá nhiều requests đồng thời.

| Chỉ số | Nguồn | Vì sao cần đo? |
|---|---|---|
| `cql-prepared-cache-size` | Driver 4.x metrics (nếu bật) | Xem số prepared statements đang được giữ |
| PREPARE/UNPREPARED/reprepare events | Driver/broker logs/metrics | Phát hiện cache churn và lỗi khi node restart |
| Query request rate | App/driver | So sánh input rate với write completion |
| Read/write latency p50/p95/p99 | Driver + Cassandra | Tìm bottleneck thực thay vì chỉ đo `send()` |
| Timeout/unavailable/overloaded | Driver exceptions | Phân biệt cluster failure với binding/contract error |
| Bind/codec exception count | App/mapper | Đánh giá schema/version mismatch |
| In-flight Cassandra operations | Driver/reactive pipeline | Nguy cơ overload và thiếu backpressure |
| Coordinator/node distribution | Cluster metrics | Token-aware routing và hot partition |
| Tombstone/compaction warnings | Cluster | Chất lượng TTL/DELETE/NULL update |
| LWT applied/failed count | Business metrics | Kiểm tra duplicate và conflict |
| JMS queue depth / Kafka lag | Source broker | Cassandra chậm có làm backlog tăng không? |

### 17.1. Cache hiệu quả không đồng nghĩa không có PREPARE lại

Ngay cả khi application cache cùng `PreparedStatement`, driver vẫn có thể gửi PREPARE sang node mới/recovered hoặc sau `UNPREPARED`. Điều này là hành vi khôi phục bình thường, không nhất thiết là lỗi.

Điều đáng điều tra là **tăng nhanh số unique CQL text**: ví dụ code sinh một prepared query khác cho từng requestId, mỗi tên table hoặc danh sách cột tùy ý. Khi đó driver/server phải quản lý nhiều entries và cache hit giảm.

### 17.2. Tracing vừa đủ

Nên ghi event ID, tên logical operation, elapsed time, loại lỗi, schema version và trace ID đã được kiểm soát. Không đưa raw JWT, password, thông tin thanh toán hoặc toàn bộ JSON vào logging. Với metrics, **không dùng từng `eventId` làm label** vì cardinality có thể bùng nổ; log/trace phù hợp hơn.

### 17.3. Tối ưu đúng vấn đề

Nếu query chậm, đánh giá theo thứ tự:

1. **Query shape:** có partition key không, có `ALLOW FILTERING` hay scan quá rộng không?
2. **Workload distribution:** partition key có tạo hot partition không?
3. **Concurrency:** bao nhiêu requests in-flight, source có backpressure không?
4. **Prepared reuse:** có dùng cùng CQL text và markers ổn định không?
5. **Latency:** driver request timeout và Cassandra p99 có tương thích không?
6. **Consistency:** đọc/ghi CL phù hợp replication/SLA chưa?
7. **Rows/bytes:** page size, payload size, batch size và tombstone pressure?

Không chỉ chỉnh `prepare-on-all-nodes`/`reprepare-on-up` để chữa một query quét toàn bảng.

## 18. Bảng lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
|---|---|---|
| Prepared statement có 6 markers nhưng bind 5 values | Thiếu field hoặc sai số dấu `?` | Validate danh sách arguments và query constant |
| Event ID bị ghi vào cột order ID | Hai fields cùng `String` bị đảo positional indices | Named binding hoặc integration test đọc lại row |
| `CodecNotFoundException` | Java type khác CQL type | Chuyển đổi typed DTO; dùng `setInt`/`setInstant` đúng cột |
| Named marker không tồn tại | Dùng `"id"` thay vì `"eventId"` hoặc thêm dấu `:` vào name | So khớp tên marker và setters |
| Đặt `setString(...)` nhưng DB nhận giá trị rỗng/cũ | Bỏ kết quả immutable `BoundStatement` setter | Gán lại hoặc chain setters |
| Partial update xóa giá trị cũ | Bind CQL `NULL` thay vì `UNSET` | Dùng `unset(...)` hoặc UPDATE chỉ cột cần sửa |
| CQL syntax lỗi khi event chứa dấu nháy | Nối giá trị vào query string | Dùng `?`/`:name` markers và bind values |
| Query table theo header user truyền | Bind không bảo vệ CQL identifier | Allowlist tên table/columns, authorization |
| Cache prepared tăng liên tục | Sinh query text khác nhau theo event IDs | Tách query constant khỏi giá trị |
| Driver reprepare sau node restart | Node mới chưa biết prepared ID | Theo dõi, để driver phục hồi; không tự spam PREPARE |
| Kết quả `IF NOT EXISTS` false | Row đã tồn tại theo key | Kiểm tra duplicate hợp lệ hay conflicting payload |
| Cassandra timeout nhưng row có tồn tại | Response bị mất sau write | Idempotent retry/kiểm tra state, không tạo event ID mới |
| `CqlTemplate` thành phần compile không đúng | Import nhầm Java driver/Spring Data class | Đối chiếu package và API version |
| Spring Integration `parameter(...)` không áp dụng | Dùng `statementFunction` thay vì `query` | Chọn một cơ chế tạo/bind statement |
| Gateway SELECT trả publisher chưa được consume | Reactive output không có subscriber/consumer | Thiết kế `FluxMessageChannel`/reply handling phù hợp |
| Adapter `send()` true nhưng Cassandra chưa ghi | Handler async mặc định | Theo dõi completion; chọn sync khi cần |
| JSON String vào `Type.INSERT` bị lỗi | Handler chờ entity `@Table` | Transform JSON → entity hoặc dùng STATEMENT |
| Retry quá nhiều khi Cassandra degraded | Driver retry × app retry × broker redelivery | Giới hạn retry budget, backoff và concurrency |
| Prepared SELECT sai sau schema migration cũ | Metadata/result shape thay đổi | Chọn explicit columns, tương thích version, verify cache |

### Những lỗi không nên xử lý bằng retry liên tục

Sai câu CQL, thiếu table/keyspace, mất quyền truy cập, JSON contract không hợp lệ, marker sai tên và codec mismatch thường không tự biến mất sau một giây. Hãy **fail fast**, cảnh báo và sửa nguyên nhân. Với transient connection loss hoặc overloaded cluster, có thể retry có kiểm soát nhưng phải biết operation có idempotent hay không.

## 19. Bài thực hành: xây một luồng bind CQL hoàn chỉnh

**Môi trường:** Java 17+, Cassandra 4/5 hoặc phiên bản tương thích, driver Java 4.x, Spring Data Cassandra và Spring Integration 6+. Dùng test cluster/container, keyspace `shop_integration` và bảng `order_event` mục 3; không chạy thử lỗi/destructive CQL trên production.

### Bài A — Chuẩn bị một lần, bind nhiều lần

1. Tạo `CqlSession` được quản lý bởi Spring, tạo `OrderEventPreparedDao` mục 4.
2. Ghi ba event khác nhau `evt-4001`, `evt-4002`, `evt-4003` bằng cùng một `PreparedStatement`.
3. Truy vấn từng row:

~~~sql
SELECT event_id, order_id, event_type, schema_version
FROM shop_integration.order_event
WHERE event_id = 'evt-4001';
~~~

4. Dùng metrics/logs phù hợp để kiểm tra application không tạo một CQL text khác cho từng event.
5. Tạo một `BoundStatement` mới cho mỗi event và chứng minh values không bị lẫn giữa hai request chạy đồng thời.

**PASS:** ba rows tồn tại với đúng ID/values, không nối event IDs vào CQL string, một prepared query dùng lại cho các lần bind.

### Bài B — Positional và named markers

1. Thực hiện INSERT bằng `?` và `prepared.bind(...)`.
2. Thực hiện INSERT tương đương bằng `:eventId`, `:orderId`... cùng các named setters.
3. Chủ động đảo `eventId`/`orderId` ở positional mode trong test, so sánh lỗi khó phát hiện.
4. Sửa bằng named markers; kiểm tra query actual và values.
5. Cố ý dùng một marker sai tên, ví dụ `setString("event_id", ...)` khi CQL định nghĩa `:eventId`, ghi nhận exception.

**PASS:** hiểu thứ tự positional binding, cách named binding không dùng dấu `:` trong setter và rủi ro khi hai fields cùng type.

### Bài C — Immutable và null/unset

1. Tạo `BoundStatement bound = prepared.bind()`, gọi `bound.setString(...)` nhưng bỏ kết quả trong một test âm tính.
2. Sửa thành `bound = bound.setString(...)` hoặc builder chaining.
3. Tạo row có `payload_json` không rỗng.
4. Với một prepared UPDATE, bind `setToNull("payloadJson")` và quan sát field bị xóa/tạo tombstone theo Cassandra semantics.
5. Khôi phục row, dùng `unset("payloadJson")` và cập nhật một field khác; xác nhận payload cũ được giữ.
6. Kiểm tra native protocol/provider hỗ trợ unset.

**PASS:** phân biệt rõ immutable setter, CQL NULL và UNSET, không tạo accidental deletes do JSON field vắng mặt.

### Bài D — CqlTemplate và reactive CqlTemplate

1. Dùng `CqlTemplate.execute(cql, args...)` để INSERT một event mới.
2. Dùng `queryForObject(cql, String.class, eventId)` để lấy event type.
3. Dùng `PreparedStatementCreator` + `PreparedStatementBinder` + `RowMapper` để query theo key.
4. Chuyển cùng logic sang `ReactiveCqlTemplate`, trả `Mono/Flux` cho subscriber.
5. Gọi reactive method nhưng chưa subscribe; so sánh với case có subscriber/StepVerifier.
6. Ngắt Cassandra, phân biệt exception đồng bộ với reactive error signal.

**PASS:** API imperative/reactive đều bind đúng tham số; lỗi được quan sát, reactive publisher không bị bỏ rơi.

### Bài E — Spring Integration gateway dùng named parameter

1. Cấu hình `findEventFlow` mục 12.1 và một consumer cho `findEventResults`.
2. Gửi Spring Message với payload `"evt-4001"`; xác minh `:eventId` nhận giá trị từ `payload`.
3. Thêm header `limit=10` và query `LIMIT :limit`; validate type/range trước khi tới gateway.
4. Gửi thiếu header limit hoặc đặt kiểu sai, xác nhận lỗi binding được ghi nhận.
5. Thử một output channel reactive; kiểm tra subscription/result mapping.

**PASS:** tên `.parameter(...)` khớp CQL marker, expression đọc đúng payload/header, không viết CQL từ raw JSON/string.

### Bài F — Spring Integration adapter dùng PreparedStatement trực tiếp

1. Khởi tạo bean `insertEventPreparedStatement` và flow `insertPreparedEventFlow` mục 12.3.
2. Gửi `Message<OrderEvent>` vào `preparedEventWrites`.
3. Đọc DB theo `eventId`, kiểm tra các fields đã bind đúng.
4. Cho một field sai CQL type (ví dụ `schemaVersion` chuỗi thay vì int khi chuyển payload), quan sát lỗi ở transformer/bind.
5. Đổi adapter sang `async=true` để thấy `send()` có thể kết thúc trước Cassandra completion.
6. Nếu business cần kết quả read/conditional write, thay bằng outbound gateway có đường reply phù hợp.

**PASS:** statement function trả một `Statement<?>` hợp lệ, Spring Integration không tự đoán bind values từ headers và caller hiểu sự khác nhau giữa adapter/gateway.

### Bài G — Retry, LWT và source acknowledgment

1. Dùng `InsertOnceDao.saveOnce(...)`, gửi `evt-4001` lần đầu, kiểm tra `wasApplied()==true`.
2. Gửi lại cùng event, kiểm tra `wasApplied()==false` và nội dung row hiện có.
3. Cố ý gửi cùng ID nhưng payload khác, phân loại là **conflicting event**, không bỏ qua vô điều kiện.
4. Tạo một flow JMS listener transacted → DirectChannel → Cassandra handler sync.
5. Cho Cassandra ghi thành công nhưng mô phỏng lỗi trước JMS commit; xác minh event có thể được giao lại mà không phát sinh side effect sai.
6. Chuyển sang `ExecutorChannel` hoặc handler async để thấy JMS callback có thể commit trước Cassandra operation.
7. Ngắt kết nối Cassandra để kiểm thử timeout, backoff và tổng số retry qua các tầng.

**PASS:** chuẩn bị statement không bị nhầm với transaction cross-system; một event được retry có khóa ổn định và exception đi đúng ranh giới.

### Ma trận kiểm thử tổng hợp

| Kịch bản | Dấu hiệu PASS |
|---|---|
| Positional binding | Số marker và giá trị khớp, thứ tự đúng |
| Named binding | Setter name khớp `:marker`, giá trị được mã hóa đúng |
| Prepared reuse | Cùng CQL text, không prepare riêng theo event value |
| Immutable statement | Không bỏ kết quả setters hoặc dùng builder đúng |
| Null vs unset | Xóa cột và bỏ qua cập nhật được phân biệt |
| Typed binding | `int`, `timestamp`, `text`, collections dùng codec thích hợp |
| Query shape | Truy vấn có partition predicate hợp lệ |
| CqlTemplate | Overload có args dùng prepare/bind và translate exception |
| ReactiveCqlTemplate | Mono/Flux được consume/subscribed, lỗi không bị mất |
| Spring Integration parameter | CQL named marker và payload/header expression khớp |
| Statement function | BoundStatement được tạo theo message, một chiều/gateway đúng |
| LWT | `[applied]` được kiểm tra khi dùng `IF NOT EXISTS` |
| Timeout/retry | Không đánh đồng timeout với DB chưa ghi |
| Security | Không nối user identifiers/CQL fragments, không log secrets |
| Broker/driver recovery | Cassandra có thể reprepare khi node restart |

**Không thể khẳng định cache, prepared metadata, codecs, LWT, failover hoặc retry semantics chỉ từ mock `CqlSession`.** Cần chạy integration tests với Cassandra thật/test container; muốn kiểm chứng JMS redelivery phải có JMS broker tương ứng.

## 20. Câu hỏi tự đánh giá

1. `PreparedStatement` và `BoundStatement` khác nhau về metadata và giá trị cụ thể như thế nào?
2. Vì sao `PreparedStatement` có thể dùng lại cho `evt-4001` và `evt-4002` mà không tạo hai query strings?
3. Positional marker `?` gắn với giá trị theo thứ tự gì?
4. Với query có `:eventId`, khi gọi `setString(...)` có đặt dấu hai chấm trong tên tham số không?
5. Vì sao hai cột `String` có thể bị đảo nhầm mà compiler không báo lỗi?
6. Các setter của driver 4.x trên `BoundStatement` có sửa trực tiếp object ban đầu không?
7. `BoundStatementBuilder` có ưu điểm gì khi câu lệnh có nhiều markers?
8. Khác biệt giữa CQL `NULL` và `UNSET` trong một UPDATE là gì?
9. Vì sao một partial DTO thiếu field không nên mặc định tạo CQL `NULL`?
10. `CodecNotFoundException` thường liên quan tới điều gì?
11. `event_id text` nên dùng Java type/setter nào? Nếu đổi thành `uuid` thì sao?
12. CQL bind markers có cho phép bind tên table và column tùy ý không?
13. Tại sao việc chuẩn bị một CQL text khác nhau cho từng event làm giảm cache hiệu quả?
14. Driver 4.x cache prepared statements ở cấp nào?
15. Điều gì có thể khiến driver phải gửi PREPARE lại dù ứng dụng reuse `PreparedStatement`?
16. Vì sao nên hạn chế prepared `SELECT *` khi schema thường xuyên đổi?
17. `CqlTemplate.execute(String, Object... args)` khác gì với `execute(String)` về prepared binding?
18. Vai trò của `PreparedStatementCreator` và `PreparedStatementBinder` trong Spring Data Cassandra là gì?
19. `ReactiveCqlTemplate` tạo `Mono` nhưng không có subscriber thì chuyện gì có thể xảy ra?
20. Khi nào dùng `CassandraTemplate` thay vì `CqlTemplate`?
21. Vì sao `CassandraMessageHandler` nhận `ReactiveCassandraOperations` thay vì `CqlTemplate`?
22. Trong Spring Integration, `.query(...).parameter("eventId","payload")` hoạt động theo hai ngôn ngữ nào?
23. Khi đã dùng `statementFunction(...)`, có nên tiếp tục kỳ vọng `parameterExpressions` của `query(...)` tự chạy không?
24. `List<List<?>>` trong `ingestQuery(...)` biểu diễn cấu trúc gì?
25. Cassandra `INSERT` thông thường có tự từ chối key đã tồn tại như unique insert RDBMS không?
26. `IF NOT EXISTS` có ý nghĩa gì; tại sao phải đọc `wasApplied()`?
27. `setIdempotent(true)` trên driver statement có tự ngăn producer gửi trùng event không?
28. Vì sao Cassandra timeout không chứng minh dữ liệu chưa được lưu?
29. `DirectChannel` với Cassandra handler sync khác `ExecutorChannel` với async ở ranh giới JMS commit thế nào?
30. Nên đo metric nào để xác định query chậm do hot partition chứ không phải do thiếu prepared cache?

## 21. Tài liệu tham khảo chính thức

- [Spring Data for Apache Cassandra — Prepared Statements](https://docs.spring.io/spring-data/cassandra/reference/cassandra/prepared-statements.html): `CqlTemplate`/`ReactiveCqlTemplate`, các overload có args, prepared callbacks và driver cache.
- [Spring Data for Apache Cassandra — CQL Template API](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html): `CqlTemplate`, RowMapper, execute/query và exception translation.
- [Spring Data for Apache Cassandra — Reactive Cassandra](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCqlTemplate`, reactive operations, subscription/error.
- [Spring Data Cassandra API — CqlTemplate](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/CqlTemplate.html): các overload `execute`, `queryForObject`, `query` và callback contracts.
- [Spring Data Cassandra API — PreparedStatementBinder](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/PreparedStatementBinder.html): trách nhiệm bind values.
- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, `query`, `parameterExpressions`, `statementProcessor` và `ingestQuery`.
- [Spring Integration API — CassandraMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/CassandraMessageHandlerSpec.html): `parameter(name, expression)`, `query`, `statementFunction` và DSL.
- [Apache Cassandra Java Driver 4.19 — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): prepare/bind, immutable `BoundStatement`, named/positional markers, null/unset và caching.
- [Apache Cassandra Java Driver 4.19 — Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): `SimpleStatement`, `BoundStatement`, `BatchStatement` và execution attributes.
- [Apache Cassandra Java Driver 4.19 — Performance](https://apache.github.io/cassandra-java-driver/4.19.0/core/performance/): prepared reuse, request latency, routing và hiệu năng.
- [Apache Cassandra Documentation](https://cassandra.apache.org/doc/latest/): CQL data types, primary/partition keys, consistency, LWT, schema migration và batch semantics.

**Ghi nhớ:** `PreparedStatement` giữ **cấu trúc câu CQL và metadata**, `BoundStatement` giữ **giá trị đã bind cho một execution**, còn `CqlSession`/driver 4.x quản lý prepared cache. Positional markers `?` và named markers `:name` đều giúp tách dữ liệu khỏi CQL syntax; chúng **không** bảo vệ tên table/cột do client cung cấp và **không** tự tạo exactly-once business processing. Trong Spring Data, dùng `CqlTemplate`/`ReactiveCqlTemplate` với prepared arguments; trong Spring Integration Cassandra, dùng `.query(...).parameter(...)` hoặc `statementFunction(...)` cùng `ReactiveCassandraOperations`. Để chạy ổn định phải kiểm tra kiểu dữ liệu, `NULL`/`UNSET`, query pattern, timeout, idempotency, ranh giới acknowledgment và thực tế Cassandra cluster.






