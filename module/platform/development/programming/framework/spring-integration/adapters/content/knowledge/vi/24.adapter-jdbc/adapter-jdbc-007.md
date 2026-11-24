# RowMapper chuyển ResultSet thành payload trong Spring Integration JDBC

## 1. Vì sao RowMapper quan trọng trong luồng tích hợp?

Một hệ thống nhận dữ liệu từ database rồi chuyển thành Spring Integration message để xử lý và gửi đến HTTP, Kafka, JMS, AMQP hoặc một dịch vụ khác. Kết quả truy vấn SQL là các hàng trong `ResultSet`, còn mã nghiệp vụ lại cần các đối tượng Java như `OrderEvent`, `OrderProjection` hoặc `ShipmentStatus`. Nếu để mỗi handler tự đọc `Map<String, Object>` với những tên cột khác nhau, hợp đồng giữa các bước sẽ khó kiểm tra, dễ ép kiểu sai và khó phát hiện thay đổi schema.

**`RowMapper<T>`** của Spring JDBC là giao diện ánh xạ **một hàng hiện tại của `ResultSet`** thành **một đối tượng `T`**. Spring JDBC gọi mapper cho từng hàng khi xử lý `SELECT`. Spring Integration JDBC inbound channel adapter có thể dùng mapper đó để tạo payload là `List<T>`; JDBC outbound gateway có thể dùng nó để tạo reply là một `T` hoặc `List<T>` theo cấu hình.

Bài thuộc chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**. Phạm vi module là kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, thực hành với file, SFTP, HTTP, JMS, AMQP, Kafka và database, đồng thời làm rõ hợp đồng message, lỗi và vòng đời kết nối. Ở bài này, **RowMapper là ranh giới chuyển đổi dữ liệu JDBC thành Java payload**, không phải bộ điều phối message hay transaction manager.

~~~mermaid
flowchart LR
    DB[("Database")] -->|"SELECT"| RS["JDBC ResultSet"]
    RS --> RM["RowMapper<T> cho từng row"]
    RM --> LIST["List<T>"]
    LIST --> MSG["Message<List<T>>"]
    MSG --> SPLIT["Splitter nếu cần"]
    SPLIT --> ITEMS["N × Message<T>"]
    ITEMS --> NEXT["Service / HTTP / Kafka / JMS"]
~~~

**Ghi nhớ ngay từ đầu:** `RowMapper` đổi **kiểu dữ liệu của row**; nó không tự thay đổi **số message**. Một query trả 20 hàng có thể vẫn chỉ tạo **một** inbound message chứa `List<OrderEvent>`. Muốn mỗi hàng thành message riêng thì thêm `Splitter` ở downstream.

## 2. Hợp đồng `RowMapper<T>` và vòng đời ResultSet

Giao diện Spring JDBC có hình dạng:

~~~java
package org.springframework.jdbc.core;

import java.sql.ResultSet;
import java.sql.SQLException;

@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
~~~

Ý nghĩa các thành phần:

| Thành phần | Ý nghĩa | Cảnh báo |
|---|---|---|
| `ResultSet rs` | Con trỏ đã được JDBC framework đặt tại **row hiện tại** | Không gọi `rs.next()` trong mapper |
| `int rowNum` | Chỉ số row do framework truyền, bắt đầu từ **0** | Không dùng làm business ID |
| `T` | DTO/record/bean/map kết quả | Không trả `null` tùy tiện cho row hợp lệ |
| `SQLException` | Lỗi truy cập column hoặc JDBC conversion | Để Spring JDBC dịch hoặc xử lý có chủ đích |

Một `RowMapper` tốt thường là **stateless**: không lưu `ResultSet` hoặc `Connection` vào field, không gọi lại database cho từng hàng, không giữ `MessageChannel` để gửi message ngay trong callback và không tạo tác dụng phụ nghiệp vụ.

~~~text
JdbcTemplate / JDBC adapter:
    while (rs.next()) {
        T mapped = rowMapper.mapRow(rs, rowNum++);
        results.add(mapped);
    }
    // Framework giải phóng ResultSet/Statement/Connection phù hợp.
~~~

Đoạn trên là **mô hình khái niệm**, không phải source code nội bộ của Spring JDBC. `JdbcTemplate`/adapter quản lý việc lặp và đóng JDBC resources. Mapper chỉ đọc các cột từ **row hiện tại** rồi tạo object.

**Không làm trong mapper:** gọi `rs.close()`, `rs.next()`, `connection.commit()`, `Thread.sleep(...)` hoặc gọi HTTP để bổ sung dữ liệu. Những thao tác đó phá hợp đồng hoặc khiến mỗi row chiếm tài nguyên lâu bất thường.

## 3. Không có RowMapper tùy chỉnh: payload mặc định là gì?

Theo tài liệu Spring Integration JDBC, **JDBC inbound channel adapter** chạy `SELECT` và đưa **toàn bộ result set** thành một payload dạng `List`. Nếu không cung cấp `RowMapper` riêng, mỗi phần tử mặc định được ánh xạ thành một `Map` theo các tên cột.

~~~sql
SELECT id, event_key, event_type
FROM inbound_event
WHERE state = 'NEW'
ORDER BY id;
~~~

Khi có hai rows, payload khái niệm là:

~~~text
Message<List<Map<String,Object>>>
  payload:
    [
      {id: 101, event_key: "evt-101", event_type: "order.created"},
      {id: 102, event_key: "evt-102", event_type: "order.paid"}
    ]
~~~

Với custom `RowMapper<InboundEvent>`, cùng query có thể tạo:

~~~text
Message<List<InboundEvent>>
  payload:
    [
      InboundEvent(id=101, eventKey="evt-101", ...),
      InboundEvent(id=102, eventKey="evt-102", ...)
    ]
~~~

**Không phụ thuộc cứng vào kiểu Map nội bộ** như `LinkedHashMap` hoặc việc tên cột được driver chuẩn hóa chữ hoa/chữ thường. Khi dùng map mặc định, đặt alias SQL rõ ràng và kiểm thử tên key thực tế. Tạo DTO bằng RowMapper giúp giảm phụ thuộc vào những chi tiết đó ở các handler sau.

### 3.1. Bốn kiểu dữ liệu cần phân biệt

| Kiểu | Số lượng | Khi gặp |
|---|---:|---|
| `ResultSet` | Một cursor JDBC | Bên trong `JdbcTemplate`/adapter, không gửi nguyên cursor qua channel |
| `List<InboundEvent>` | N phần tử đã map | Kết quả query trước khi đóng gói message |
| `Message<List<InboundEvent>>` | **Một message** | JDBC inbound adapter trước splitter |
| `List<Message<InboundEvent>>` hoặc N messages | **N messages** | Sau splitter/handler điều phối tương ứng |

Đừng ép handler `handle(InboundEvent)` nhận trực tiếp payload khi upstream còn ở hình dạng `List<InboundEvent>`.

## 4. Chuẩn bị dự án Spring Boot và schema mẫu

Bài dùng Java 17+, Spring Boot, Spring JDBC, Spring Integration JDBC và H2. Để tránh xung đột phiên bản, dùng BOM của Spring Boot quản lý các dependency Spring Framework/Integration tương thích.

~~~groovy
// build.gradle - phần dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml - chỉ dành cho ví dụ H2
spring:
  datasource:
    url: "jdbc:h2:mem:row_mapper_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

Đặt SQL sau vào `src/main/resources/schema.sql` của **ứng dụng thực hành**. Bước soạn bài này chỉ chỉnh Markdown/YAML được giao, không tự tạo file dự án:

~~~sql
CREATE TABLE inbound_event (
    id             BIGINT NOT NULL PRIMARY KEY,
    event_key      VARCHAR(64) NOT NULL UNIQUE,
    event_type     VARCHAR(64) NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    attempt_count  INTEGER NULL,
    state          VARCHAR(20) NOT NULL
);
~~~

Ví dụ dữ liệu thử (có thể lưu trong `data.sql`):

~~~sql
INSERT INTO inbound_event
    (id, event_key, event_type, created_at, attempt_count, state)
VALUES
    (101, 'evt-101', 'order.created',
        TIMESTAMP '2026-11-01 09:00:00', 0, 'NEW'),
    (102, 'evt-102', 'order.paid',
        TIMESTAMP '2026-11-01 09:01:00', NULL, 'NEW'),
    (103, 'evt-103', 'order.shipped',
        TIMESTAMP '2026-11-01 09:02:00', 2, 'CLAIMED');
~~~

Trong ví dụ, `attempt_count` có thể `NULL` để người học thấy sự khác nhau giữa `Integer` và `int`. `created_at` là `TIMESTAMP` không có timezone; bài dùng `LocalDateTime`. Production nên quy định rõ timezone và kiểu timestamp theo database vendor khi dữ liệu cần biểu diễn một thời điểm toàn cầu.

## 5. Tạo DTO Java record và RowMapper thủ công

### 5.1. DTO làm hợp đồng payload

~~~java
package com.example.integration;

import java.time.LocalDateTime;

public record InboundEvent(
    long id,
    String eventKey,
    String eventType,
    LocalDateTime createdAt,
    Integer attemptCount) {
}
~~~

**Vì sao dùng record?** Đây là kiểu dữ liệu bất biến, có các accessor như `id()` và `eventKey()`, thuận tiện để chuyển giữa các bước trong flow. Trường `attemptCount` dùng `Integer` để giữ đúng khả năng `NULL` của SQL.

### 5.2. RowMapper rõ ràng và kiểm tra dữ liệu

~~~java
package com.example.integration;

import java.sql.Timestamp;
import org.springframework.dao.DataRetrievalFailureException;
import org.springframework.jdbc.core.RowMapper;

public final class InboundEventRowMapper
        implements RowMapper<InboundEvent> {

    @Override
    public InboundEvent mapRow(
            java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException {

        long id = rs.getLong("id");
        if (rs.wasNull()) {
            throw new DataRetrievalFailureException(
                "inbound_event.id must not be NULL");
        }

        Timestamp timestamp = rs.getTimestamp("created_at");
        if (timestamp == null) {
            throw new DataRetrievalFailureException(
                "created_at must not be NULL");
        }

        return new InboundEvent(
            id,
            rs.getString("event_key"),
            rs.getString("event_type"),
            timestamp.toLocalDateTime(),
            rs.getObject("attempt_count", Integer.class));
    }
}
~~~

`rs.getLong(...)` trả `0` khi SQL column là `NULL`, vì vậy `rs.wasNull()` là cách phân biệt với giá trị số 0 thật. Mặc dù schema đánh dấu `id NOT NULL`, ví dụ kiểm tra phòng trường hợp query/join/alias thay đổi trong tương lai.

`rs.getObject("attempt_count", Integer.class)` giữ SQL `NULL` thành Java `null` trên JDBC driver hỗ trợ typed retrieval. Một số driver cũ hoặc kiểu đặc thù có hạn chế với `getObject(..., Class)`; khi đó dùng `getInt` + `wasNull()`:

~~~java
int value = rs.getInt("attempt_count");
Integer attemptCount = rs.wasNull() ? null : value;
~~~

Nếu có nghiệp vụ cần mặc định số lần xử lý bằng 0, hãy thể hiện quy tắc đó **tường minh**, không để JDBC primitive tự biến `NULL` thành 0 mà không ai biết.

### 5.3. Những việc RowMapper không nên làm

Một mapper nên chỉ làm chuyển đổi và validation cơ bản của **một row**. Không nên:

- Truy vấn database khác cho mỗi row gây vấn đề `N+1 queries`.
- Gửi HTTP/Kafka/JMS ngay trong `mapRow`; side effect đó không được transaction của `SELECT` bảo vệ như kỳ vọng.
- Tạo correlation ID ngẫu nhiên cho mỗi lần map nếu ID nghiệp vụ phải ổn định qua retry.
- Lưu `ResultSet` hay `Connection` trong DTO; hai tài nguyên đó sẽ hết hiệu lực sau khi query hoàn tất.
- Gọi `rs.next()` vì việc di chuyển cursor thuộc JDBC framework.

**Nơi hợp lý cho nghiệp vụ:** RowMapper tạo `InboundEvent`; service activator/transformer tiếp theo kiểm tra state transition, enrich, xác thực, publish hoặc ghi outbox.

## 6. Ba chiến lược ánh xạ: Map, Bean và record

| Chiến lược | Đầu ra | Ưu điểm | Rủi ro |
|---|---|---|---|
| Mapper mặc định/`ColumnMapRowMapper` | `Map<String,Object>` | Nhanh thử nghiệm, schema linh hoạt | Ép kiểu/column names rải rác |
| `BeanPropertyRowMapper<T>` | Java bean có constructor rỗng và setters | Ít code mapping khi tên cột khớp | Bean mutable, NULL primitive, reflection/conversion |
| `DataClassRowMapper<T>` | Java record/Kotlin data class/constructor-based type | Mapping constructor, DTO bất biến | Tên/kiểu cột phải khớp constructor |
| `RowMapper<T>` tùy chỉnh | `T` bất kỳ | Rõ validation, alias, kiểu/precision | Phải viết và bảo trì mapping |

### 6.1. BeanPropertyRowMapper dùng cho bean mutable

~~~java
package com.example.integration;

public class EventBean {
    private Long id;
    private String eventKey;
    private String eventType;

    public EventBean() { }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getEventKey() { return eventKey; }
    public void setEventKey(String eventKey) {
        this.eventKey = eventKey;
    }

    public String getEventType() { return eventType; }
    public void setEventType(String eventType) {
        this.eventType = eventType;
    }
}
~~~

~~~java
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.RowMapper;

RowMapper<EventBean> beanMapper =
    BeanPropertyRowMapper.newInstance(EventBean.class);
~~~

Spring có thể ánh xạ `event_key` → `eventKey` và `event_type` → `eventType` theo quy tắc underscore/camelCase. `BeanPropertyRowMapper` phù hợp DTO mutable có constructor không tham số và setters; **không nên dùng nó như cách mặc định cho Java record** vốn không có setter và constructor rỗng.

### 6.2. DataClassRowMapper dùng cho Java record

~~~java
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.RowMapper;

RowMapper<InboundEvent> recordMapper =
    DataClassRowMapper.newInstance(InboundEvent.class);
~~~

`DataClassRowMapper` có hỗ trợ constructor data class cho Java records. Nó hoạt động tốt khi JDBC columns và constructor parameters có thể được ghép tên/kiểu chính xác. Hãy **kiểm thử thực tế** các kiểu `TIMESTAMP`, `UUID`, enum, JSON columns và SQL `NULL` với driver mà ứng dụng dùng.

**Chọn mapper nào?** Với projection đơn giản, `DataClassRowMapper` gọn và dễ hiểu. Với tiền tệ, timestamp/timezone, nullability, enum hoặc SQL aliases phức tạp, custom `RowMapper` thường có hợp đồng rõ hơn và có thể tối ưu hơn.

### 6.3. ColumnMapRowMapper chỉ phù hợp khi chấp nhận dữ liệu động

~~~java
import java.util.Map;
import org.springframework.jdbc.core.ColumnMapRowMapper;
import org.springframework.jdbc.core.RowMapper;

RowMapper<Map<String, Object>> mapMapper =
    new ColumnMapRowMapper();
~~~

Đây là mapper có thể dùng khi bảng/cột thay đổi và downstream đã định nghĩa cách xử lý map. Không suy ra map keys luôn có cùng cách viết hoa giữa mọi database; khi hợp đồng công khai cần tên ổn định, **chọn alias SQL hoặc DTO rõ ràng**.

## 7. SQL alias, tên cột và mapping kiểu dữ liệu

Một `RowMapper` lấy giá trị từ `ResultSet` theo **column label** hoặc index. Khi SQL dùng join, đổi tên cột hoặc có nhiều cột cùng tên, cần alias:

~~~sql
SELECT
    e.id                AS id,
    e.event_key         AS event_key,
    e.event_type        AS event_type,
    e.created_at        AS created_at,
    e.attempt_count     AS attempt_count
FROM inbound_event e
WHERE e.state = 'NEW'
ORDER BY e.id;
~~~

Với query join, tránh `SELECT *` nếu hai bảng có cột `id` cùng tên. Có thể dùng alias `event_id`, `order_id` và cập nhật mapper tương ứng. Chọn alias rõ còn giúp test phát hiện query bị sửa sai contract.

| SQL type phổ biến | Java type gợi ý | Vấn đề cần chú ý |
|---|---|---|
| `BIGINT NOT NULL` | `long` hoặc `Long` | `getLong` + `wasNull` khi cần |
| `INTEGER NULL` | `Integer` | Đừng mất thông tin SQL NULL |
| `DECIMAL(18,2)` | `BigDecimal` | Không tự đổi tiền sang `double` |
| `VARCHAR` | `String` | Encoding, trim, empty/null, max length |
| `TIMESTAMP` | `LocalDateTime` hoặc type phù hợp timezone | Quy tắc timezone/driver và precision |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime`/`Instant` theo hỗ trợ | Cần kiểm tra driver/DB thật |
| `BOOLEAN` / bit | `Boolean` hoặc `boolean` | Nullability và dialect |
| `UUID` | `UUID` hoặc `String` | Kiểu native vs CHAR/VARCHAR theo vendor |
| JSON/BLOB/CLOB | DTO/byte[]/stream phù hợp | Codec, memory, tài nguyên |

**Ví dụ tiền tệ:** nếu SQL `DECIMAL(18,2)` chứa `125000.50`, `rs.getBigDecimal("amount")` giữ độ chính xác thập phân; dùng `getDouble` rồi tính toán tiền có thể tạo sai số nhị phân. Trường hợp doanh nghiệp cần rounding/scale, quy tắc nằm ở domain layer hoặc mapper có kiểm tra, không dựa vào default conversion ngẫu nhiên.

## 8. RowMapper và JdbcTemplate: kiểm tra mapping riêng trước khi tích hợp

Trước khi đưa mapper vào một poller, nên test nó qua `JdbcTemplate.query(...)` với SQL đơn giản. Như vậy việc sai kiểu dữ liệu/cột có thể được phân biệt với lỗi scheduler, channel hoặc broker.

~~~java
package com.example.integration;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InboundEventRepository {

    private final JdbcTemplate jdbc;
    private final InboundEventRowMapper mapper =
        new InboundEventRowMapper();

    public InboundEventRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<InboundEvent> findNewEvents() {
        return jdbc.query(
            "SELECT id, event_key, event_type, "
          + "created_at, attempt_count "
          + "FROM inbound_event WHERE state = ? ORDER BY id",
            mapper, "NEW");
    }
}
~~~

`JdbcTemplate.query(...)` gọi mapper **một lần cho mỗi row** và trả `List<InboundEvent>`. Nếu không có row, kết quả là danh sách rỗng; `queryForObject(...)` là API khác, thường yêu cầu **chính xác một row** và có ngoại lệ khi cardinality không khớp.

~~~java
List<InboundEvent> events = repository.findNewEvents();
System.out.println("Mapped rows = " + events.size());
~~~

**Điểm giới hạn:** `JdbcTemplate.query(...)` vẫn là I/O đồng bộ và thường materialize `List` trước khi trả về. `RowMapper` tự nó không tạo `Flux<InboundEvent>` hay tự quản lý backpressure cho các hệ thống ngoài database.

## 9. Java DSL Spring Integration 7.x: inbound RowMapper → message payload

Từ **Spring Integration 7.0**, JDBC module cung cấp Java DSL factory `Jdbc.inboundAdapter(...)`. `JdbcInboundChannelAdapterSpec.rowMapper(...)` nhận một `RowMapper<?>`, `maxRows(...)` giới hạn số rows và poller quyết định nhịp truy vấn.

Ví dụ dưới đây dùng SQL có `WHERE state = 'NEW'`, cập nhật rows được chọn thành `CLAIMED` và phát từng `InboundEvent` đến channel `mappedEvents`. Đây là ví dụ **claim rồi xử lý**, chưa phải bảo đảm exactly-once end-to-end.

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
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class JdbcInboundRowMappingFlow {

    @Bean
    public RowMapper<InboundEvent> inboundEventRowMapper() {
        return new InboundEventRowMapper();
    }

    @Bean
    public IntegrationFlow pollAndMapEvents(
            DataSource dataSource,
            RowMapper<InboundEvent> inboundEventRowMapper,
            PlatformTransactionManager transactionManager) {

        String selectSql = """
            SELECT id, event_key, event_type,
                   created_at, attempt_count
            FROM inbound_event
            WHERE state = 'NEW'
            ORDER BY id
            """;

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource, selectSql)
                    .rowMapper(inboundEventRowMapper)
                    .maxRows(25)
                    .updateSql(
                        "UPDATE inbound_event SET state = 'CLAIMED' "
                      + "WHERE id IN (:id) AND state = 'NEW'")
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> rows = (List<?>) result;
                        List<Long> ids = rows.stream()
                            .map(InboundEvent.class::cast)
                            .map(InboundEvent::id)
                            .toList();
                        return new MapSqlParameterSource("id", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .filter(payload ->
                payload instanceof List<?> rows && !rows.isEmpty())
            .split()
            .channel("mappedEvents")
            .get();
    }
}
~~~

Đọc theo trình tự:

1. `Jdbc.inboundAdapter(dataSource, selectSql)` tạo JDBC polling message source cho SQL `SELECT`.
2. `rowMapper(inboundEventRowMapper)` đổi **từng row** sang `InboundEvent`.
3. `maxRows(25)` giới hạn số rows được adapter đưa vào message cho mỗi lần query; không giống `maxMessagesPerPoll(1)` là số lần `receive()` trong một trigger.
4. `updateSql(...)` đánh dấu bản ghi đã đọc để poll sau không thấy lại những bản ghi ở trạng thái `NEW`. Nó không thay thế transaction/recovery strategy.
5. `updateSqlParameterSourceFactory(...)` minh họa lấy IDs từ **list kết quả đã map** để bind `:id`; tránh phụ thuộc vào quy ước tự suy tên field sau khi chuyển `Map` thành record.
6. `transactional(transactionManager)` bọc poll operation khi transaction manager tương ứng với `DataSource`. Điều đó hữu ích với cặp SELECT/UPDATE; cần xem tiếp thread và channel ở mục 14.
7. `filter` và `split()` kiểm soát shape: danh sách không rỗng được chia thành N messages có payload `InboundEvent`.
8. `mappedEvents` là channel downstream; để thực sự xử lý, cần có subscriber/handler cho channel này.

**Lưu ý về ví dụ:** truy vấn `SELECT ... ORDER BY id` cộng `UPDATE ... WHERE id IN (...)` chưa phải thuật toán **atomic claim** an toàn khi nhiều ứng dụng/pods cùng poll. Hai instances có thể đọc cùng rows trước khi một instance UPDATE. Production nên dùng cơ chế claim/locking theo DB vendor (ví dụ `FOR UPDATE SKIP LOCKED` hoặc update-returning thích hợp), lease/outbox và idempotency.

### 9.1. Consumer cho từng payload sau Splitter

~~~java
package com.example.integration;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class InboundEventConsumer {

    @ServiceActivator(inputChannel = "mappedEvents")
    public void handle(InboundEvent event) {
        System.out.printf("Event %d: %s%n",
            event.id(), event.eventType());
    }
}
~~~

Handler nhận **`InboundEvent` đơn** vì trước đó có `.split()`. Trong production, không dùng `System.out.println` làm bằng chứng broker đã nhận event hoặc database đã commit. Nếu cần HTTP/Kafka/JMS outbound, nên thiết kế error/ACK boundary và idempotency rõ ràng.

## 10. Một lượt poll tạo bao nhiêu messages?

Giả sử SQL trả 3 rows, mapper chuyển thành 3 DTO, poller có `maxMessagesPerPoll(1)`:

~~~text
Poller:
  1 lần gọi source.receive()
      -> SELECT lấy 3 rows
      -> RowMapper.mapRow(...) chạy 3 lần
      -> 1 List<InboundEvent> chứa 3 objects
      -> 1 Message<List<InboundEvent>>
      -> Splitter
      -> 3 x Message<InboundEvent>
~~~

| Cấu hình | Kết quả | Điều không thay đổi |
|---|---|---|
| Không RowMapper riêng | `Message<List<Map<String,Object>>>` | Số message vẫn 1 trước splitter |
| Có `RowMapper<InboundEvent>` | `Message<List<InboundEvent>>` | Số message vẫn 1 trước splitter |
| Thêm splitter | N `Message<InboundEvent>` | Query vẫn thực thi theo poller |
| `maxRows(25)` | Tối đa 25 rows trong một kết quả query | Không thành 25 polls |
| `maxMessagesPerPoll(1)` | Một lần hỏi source/triggers theo policy | Không giới hạn query còn 1 row |
| SELECT trả 0 rows | Không có business rows để split | Không tự coi đó là lỗi JDBC |

**Khác biệt về defaults:** JDBC inbound adapter có `maxRows` mặc định là **0**, nghĩa là không áp giới hạn ở tầng adapter. JDBC outbound gateway với SELECT thường có `maxRows` mặc định **1**. Dùng chung mapper không làm hai endpoint có cùng hình dạng reply.

### 10.1. Limit tại database thay vì chỉ tại Java

`maxRows(25)` giới hạn số records adapter xử lý, nhưng với bảng lớn, nên sử dụng SQL giới hạn ngay tại database, ví dụ `LIMIT`/`FETCH FIRST`/`TOP` tùy vendor, kết hợp index và pagination. Khi có ORDER BY ổn định, mỗi poll có thể lấy batch dự đoán được hơn.

**Không làm** `SELECT * FROM huge_table` rồi dựa vào mapper để bỏ bớt các row nếu yêu cầu thực tế chỉ có 25 events. RowMapper không phải bộ điều khiển truy vấn tối ưu và không dừng JDBC driver/network từ đầu theo hợp đồng ứng dụng.

## 11. Cách cấu hình RowMapper trên Spring Integration 6.x

Java DSL JDBC factory `Jdbc.inboundAdapter(...)` được giới thiệu từ **Spring Integration 7.0**. Với Spring Integration **6.x**, lớp `org.springframework.integration.jdbc.JdbcPollingChannelAdapter` đã có `setRowMapper(...)` và có thể dùng trực tiếp trong `IntegrationFlow.from(messageSource, pollerSpec)`:

~~~java
package com.example.integration;

import java.time.Duration;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.jdbc.core.RowMapper;

@Configuration
public class JdbcRowMappingLegacyFlow {

    @Bean
    public IntegrationFlow legacyMappedEvents(
            DataSource dataSource) {
        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(
                dataSource,
                "SELECT id, event_key, event_type, "
              + "created_at, attempt_count "
              + "FROM inbound_event WHERE state = 'NEW' ORDER BY id");

        RowMapper<InboundEvent> mapper = new InboundEventRowMapper();
        source.setRowMapper(mapper);
        source.setMaxRows(25);

        return IntegrationFlow.from(source, endpoint ->
                endpoint.poller(Pollers.fixedDelay(Duration.ofSeconds(5))
                    .maxMessagesPerPoll(1)))
            .filter(payload ->
                payload instanceof java.util.List<?> rows &&
                !rows.isEmpty())
            .split()
            .channel("legacyMappedEventsChannel")
            .get();
    }
}
~~~

**Khác biệt với mục 9:** ví dụ 6.x cố ý chỉ SELECT và map, **không đánh dấu rows đã xử lý**, để tập trung vào API cấu hình. Vì thế nó sẽ **đọc lại cùng rows ở mỗi poll** nếu database không đổi. Production phải thêm `setUpdateSql(...)`/`setUpdateSqlParameterSourceFactory(...)` và transactional poller, hoặc dùng atomic claim/outbox phù hợp.

Trong dự án thật, dùng **một cách** cấu hình phù hợp phiên bản đang chạy; không bật đồng thời flow 7.x và 6.x cùng truy cập một nguồn mà không thiết kế concurrency.

### 11.1. XML cấu hình cho 6.x

~~~xml
<!-- Fragment trong Spring XML có khai báo namespace int và int-jdbc. -->
<bean id="inboundEventRowMapper"
      class="com.example.integration.InboundEventRowMapper"/>

<int:channel id="mappedEventBatches"/>

<int-jdbc:inbound-channel-adapter
    id="jdbcMappedEvents"
    query="SELECT id, event_key, event_type,
                  created_at, attempt_count
           FROM inbound_event WHERE state = 'NEW' ORDER BY id"
    data-source="dataSource"
    channel="mappedEventBatches"
    row-mapper="inboundEventRowMapper"
    max-rows="25">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-jdbc:inbound-channel-adapter>
~~~

XML chỉ thể hiện **một message chứa list DTO** trên `mappedEventBatches`. Nếu cần từng row làm message, cấu hình splitter downstream. Khi bật `update` của inbound adapter, thêm transaction manager vào poller và xác định rõ chính sách chuyển trạng thái/recovery.

## 12. JDBC outbound gateway: RowMapper ảnh hưởng reply như thế nào?

Ở **JDBC outbound gateway**, message từ input channel là **request** chứa các tham số query, còn `RowMapper` chuyển các hàng SELECT thành **reply payload**. Khi `maxRows` mặc định hoặc bằng 1, gateway thường trả row đơn; khi `maxRows(0)` trả nhiều rows, reply thường là list.

~~~mermaid
flowchart LR
    A["Message<Map: orderId>"] --> B["JDBC outbound gateway"]
    B --> C["SELECT WHERE order_id = :payload[orderId]"]
    C --> D["ResultSet"]
    D --> E["RowMapper<InboundEvent>"]
    E --> F["Reply: InboundEvent hoặc List<InboundEvent>"]
~~~

### 12.1. Java DSL 7.x cho SELECT một row

~~~java
package com.example.integration;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;

@Configuration
public class EventLookupGatewayFlow {

    @Bean
    public IntegrationFlow eventLookup(DataSource dataSource) {
        return IntegrationFlow.from("eventLookupRequests")
            .handle(Jdbc.outboundGateway(
                    dataSource,
                    null,
                    "SELECT id, event_key, event_type, "
                  + "created_at, attempt_count "
                  + "FROM inbound_event "
                  + "WHERE id = :payload[id]")
                .maxRows(1)
                .rowMapper(new InboundEventRowMapper()))
            .channel("eventLookupReplies")
            .get();
    }
}
~~~

Payload request ví dụ là `Map.of("id", 101L)`. Gateway gọi query, RowMapper tạo `InboundEvent` và reply chứa đối tượng đó **khi có một row**. Trong DSL, overload ba tham số `Jdbc.outboundGateway(dataSource, updateSql, selectSql)` với `updateSql = null` biểu thị chế độ chỉ SELECT.

Nếu `SELECT` không tìm thấy row, đừng tự suy rằng gateway nhất định trả `null` hoặc luôn timeout: từ Spring Integration **6.0**, kết quả danh sách rỗng được **giữ làm reply** thay vì tự chuyển thành “không có reply”. Việc reply cụ thể là row đơn hay list còn phụ thuộc `maxRows` và kết quả thực tế; hãy kiểm tra 0/1/nhiều rows bằng test.

### 12.2. Khi cần nhiều rows

~~~java
.handle(Jdbc.outboundGateway(
        dataSource, null, selectSql)
    .maxRows(0)
    .rowMapper(new InboundEventRowMapper()))
.split()
.channel("oneEventPerMessage")
~~~

Đây là mảnh DSL; `selectSql` là chuỗi SELECT phù hợp, `dataSource` là bean được inject. `maxRows(0)` nghĩa là không giới hạn số hàng theo cấu hình gateway, **không phải lấy 0 rows**. Nếu query có thể trả hàng triệu rows, hãy bổ sung WHERE, pagination hoặc keyset cursor trước khi dùng `maxRows(0)`.

## 13. Stored procedure, result set và RowMapper

JDBC stored procedure có thể trả một hoặc nhiều `ResultSet`, OUT parameters và return value. Với Spring Integration stored procedure endpoints, có thể khai báo `returningResultSetRowMapper("events", mapper)` để map **mỗi row trong result set mang tên `events`** sang DTO.

~~~java
// Mảnh cấu hình trong StoredProcExecutorSpec của Spring Integration 7.x:
.returningResultSetRowMapper(
    "events", new InboundEventRowMapper())
~~~

**Khác với inbound channel adapter thông thường:** stored procedure executor thường tạo một **`Map<String,Object>`** gồm các result sets/OUT parameters. Một result set có thể là `List<InboundEvent>` dưới key `events`; nó không tự được trải thành N messages.

Nếu bật `expectSingleResult(true)` ở stored procedure inbound adapter, cơ chế này hướng tới trích **một entry duy nhất trong result map**, không phải một row. Khi map chỉ có key `events`, payload có thể thành `List<InboundEvent>` và vẫn cần splitter. Nếu map có nhiều OUT/result entries, `expectSingleResult(true)` không thể thay thế việc định nghĩa đúng hợp đồng map.

## 14. RowMapper, SELECT/UPDATE và ranh giới transaction của poller

Một JDBC inbound adapter có thể vừa thực hiện `SELECT` lấy rows, vừa thực hiện `UPDATE` để đánh dấu rows đã được poll. `RowMapper` chỉ quyết định **hình dạng row**, còn policy chọn/đánh dấu/ACK thuộc endpoint và transaction.

~~~mermaid
sequenceDiagram
    participant P as Poller / transaction
    participant A as JDBC inbound adapter
    participant DB as Database
    participant R as RowMapper
    participant D as Downstream DirectChannel
    P->>A: receive()
    A->>DB: SELECT NEW rows
    DB-->>A: ResultSet
    A->>R: mapRow cho từng row
    R-->>A: List<InboundEvent>
    A->>DB: UPDATE claimed rows
    A-->>D: Message<List<InboundEvent>>
    Note over P,D: Đồng bộ + cùng TX có thể rollback nếu downstream lỗi
~~~

Với `DirectChannel` và downstream **đồng bộ cùng thread**, database updates có thể cùng transaction của poller nếu transaction manager dùng đúng `DataSource`. Nhưng khi đưa message qua `ExecutorChannel`, `QueueChannel` hoặc gọi HTTP/Kafka bất đồng bộ, transaction của poller **không tự tiếp tục** trên thread/process khác.

Một câu `SELECT` + `UPDATE` thông thường **không bảo đảm atomic claim giữa nhiều replicas** nếu không có locking/isolation phù hợp. Cần chọn thuật toán theo DB vendor, ví dụ locking và `SKIP LOCKED`/`OUTPUT` hoặc lease, thay vì cho nhiều instance đọc cùng các rows `NEW` rồi cùng gửi ra broker.

**Crash recovery:** nếu `UPDATE state='CLAIMED'` commit rồi ứng dụng chết trước khi publish, dữ liệu có thể bị kẹt ở `CLAIMED`. Dùng lease/reclaim, transactional outbox, idempotency và metrics theo trạng thái, chứ không kỳ vọng RowMapper sửa vấn đề delivery.

## 15. Null, precision, timestamp và schema drift

### 15.1. Null không được lặng lẽ chuyển thành giá trị thật

Trong JDBC:

~~~java
long id = rs.getLong("id");
boolean isNull = rs.wasNull();
~~~

Nếu SQL `NULL`, getter primitive có thể trả `0` và `wasNull()` mới phân biệt được. Đối với số lần retry, số tiền hoặc flags, việc hiểu `NULL` thành 0/false có thể phá logic nghiệp vụ. Dùng `Integer`/`Long`/`Boolean` khi nullable hoặc kiểm tra explicit với getter tương ứng.

### 15.2. Timestamp cần hợp đồng timezone

`Timestamp.toLocalDateTime()` biểu diễn thời gian dạng local calendar fields, **không mang timezone**. Nếu dữ liệu là thời điểm UTC toàn cầu, nên cân nhắc lưu kiểu có timezone hoặc mapping theo UTC có cấu hình JDBC driver rõ. Không biến `LocalDateTime` thành `Instant` bằng cách tự gắn timezone của máy chủ mà chưa có hợp đồng.

### 15.3. Column alias và schema changes

Nếu DB đổi `event_type` thành `type` nhưng query vẫn alias `AS event_type`, RowMapper không cần đổi. Nếu một cột bị xóa hoặc đổi kiểu không tương thích, mapper nên báo lỗi rõ thay vì âm thầm sinh DTO thiếu dữ liệu.

Sử dụng migration/contract tests để phát hiện thay đổi schema. Không log toàn bộ row có dữ liệu nhạy cảm khi xảy ra lỗi mapping.

## 16. RowMapper không phải ResultSetExtractor hay RowCallbackHandler

| API Spring JDBC | Khi gọi | Kiểu kết quả | Tình huống |
|---|---|---|---|
| `RowMapper<T>` | **Mỗi row** | Một `T` | DTO cho inbound adapter/gateway/JdbcTemplate |
| `ResultSetExtractor<R>` | **Một lần cho cả ResultSet** | Một `R` bất kỳ | Tổng hợp nhiều rows thành cấu trúc phức tạp |
| `RowCallbackHandler` | **Mỗi row** với side effect callback | Không trả một `T`/row trực tiếp | Xử lý thống kê/ghi file theo từng row trong callback |

Một số nghiệp vụ cần nhóm dữ liệu master-detail từ một JOIN. Khi query trả nhiều dòng lặp thông tin master, có thể dùng `ResultSetExtractor` hoặc một `RowMapper` rồi group downstream. Không ép RowMapper mỗi row làm luôn công việc **gom toàn bộ ResultSet** bằng cách giữ biến mutable toàn cục.

### 16.1. Ví dụ ResultSetExtractor cho tổng hợp

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.jdbc.core.ResultSetExtractor;

ResultSetExtractor<List<Long>> extractor = rs -> {
    List<Long> ids = new ArrayList<>();
    while (rs.next()) {
        ids.add(rs.getLong("id"));
    }
    return ids;
};
~~~

Trong `ResultSetExtractor`, việc duyệt `rs.next()` là **đúng hợp đồng** vì extractor sở hữu việc xử lý toàn bộ cursor. Trong `RowMapper`, hành động đó là **sai hợp đồng**.

## 17. Test RowMapper độc lập bằng Mockito

Để kiểm tra mapper không phụ thuộc database thực, mock `ResultSet` và khẳng định từng field được chuyển đúng:

~~~java
package com.example.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.Mockito.*;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;

class InboundEventRowMapperTest {

    @Test
    void mapsOneRowIncludingNullableCount() throws Exception {
        ResultSet rs = mock(ResultSet.class);
        LocalDateTime created =
            LocalDateTime.of(2026, 11, 1, 9, 1);

        when(rs.getLong("id")).thenReturn(102L);
        when(rs.wasNull()).thenReturn(false);
        when(rs.getString("event_key")).thenReturn("evt-102");
        when(rs.getString("event_type")).thenReturn("order.paid");
        when(rs.getTimestamp("created_at"))
            .thenReturn(Timestamp.valueOf(created));
        when(rs.getObject("attempt_count", Integer.class))
            .thenReturn(null);

        InboundEvent result =
            new InboundEventRowMapper().mapRow(rs, 1);

        assertEquals(102L, result.id());
        assertEquals("evt-102", result.eventKey());
        assertEquals("order.paid", result.eventType());
        assertEquals(created, result.createdAt());
        assertNull(result.attemptCount());
        verify(rs, never()).next();
    }
}
~~~

Test này chứng minh **logic của RowMapper** và xác nhận mapper không tự di chuyển cursor. Nó **không** chứng minh SQL query/schema/JDBC driver trả đúng column types, hay transaction của poller hoạt động; cần integration test tương ứng.

### 17.1. Test lỗi dữ liệu

Thêm test với `rs.getTimestamp("created_at") == null` để khẳng định mapper ném `DataRetrievalFailureException`. Điều này quan trọng hơn việc cho phép DTO có `createdAt=null` trong một nghiệp vụ yêu cầu bắt buộc timestamp.

Nếu dùng `BeanPropertyRowMapper`, hãy thử các trường `NULL` ánh xạ vào primitive; so sánh việc ném `TypeMismatchException` với tùy chọn `primitivesDefaultedForNullValue` và xem việc default im lặng có phù hợp hay không.

## 18. Integration test: từ JdbcTemplate đến MessageChannel

Khi đã kiểm tra mapper riêng, dùng H2 hoặc database tương thích production để kiểm tra query và hình dạng payload. Ví dụ `@SpringBootTest` với schema và fixtures ở mục 4:

~~~java
package com.example.integration;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class InboundEventJdbcMappingTest {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void mapsSqlRowsToRecord() {
        List<InboundEvent> result = jdbc.query(
            "SELECT id, event_key, event_type, "
          + "created_at, attempt_count "
          + "FROM inbound_event WHERE id = ?",
            new InboundEventRowMapper(), 102L);

        assertEquals(1, result.size());
        assertEquals("evt-102", result.get(0).eventKey());
        assertNull(result.get(0).attemptCount());
    }
}
~~~

**Khi test toàn IntegrationFlow có poller chạy nền:** đừng đọc trực tiếp channel mà không kiểm soát lịch poll, fixture và consumer. Một test hợp lý có thể dùng `QueueChannel` test-only, gửi dữ liệu sau khi app context sẵn sàng rồi đợi tối đa một deadline xác định bằng `receive(timeout)`. Nếu flow có `split()`, assert mỗi payload là `InboundEvent` chứ không phải list; nếu bỏ split, assert payload là `List<InboundEvent>`.

Trong production, Testcontainers hoặc database cùng vendor nên được dùng để kiểm tra `TIMESTAMP`, `UUID`, enum, JSON, locking và row mapping của driver thật. H2 không tái hiện đầy đủ SQL Server/PostgreSQL/Oracle.

## 19. Lỗi ánh xạ và xử lý error trong Spring Integration

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `SQLException: Column not found` | Sai column label/alias | In query projection, test `RowMapper` |
| `ClassCastException` downstream | Handler tưởng `InboundEvent` nhưng payload là `List`/`Map` | Kiểm tra trước/sau splitter |
| `NullPointerException` trong mapper | SQL NULL chưa xử lý | Đổi sang wrapper/validate |
| Giá trị giờ bị lệch | Timestamp/timezone/driver không thống nhất | Quy định UTC/local semantics và test |
| `BigDecimal` bị sai precision | Convert sang `double` | Giữ số thập phân đúng type |
| Dữ liệu phát lại mỗi poll | Không có UPDATE/claim/recovery | Thiết kế lifecycle dữ liệu |
| Không nhận được message nào | Query trả 0 row, poller/channel/transaction lỗi | Metrics, SQL test, logs/error flow |
| Database connection timeout | Pool quá tải hoặc DB chậm | Theo dõi Hikari/poller concurrency |
| RowMapper chậm nghiêm trọng | N+1 queries hoặc I/O bên trong mapper | Đưa enrichment ra service layer |

Spring JDBC thường chuyển `SQLException` thành `DataAccessException`. Trong một poller/endpoint của Spring Integration, lỗi có thể được bọc thành `MessagingException` hoặc chuyển qua `ErrorMessage`/`errorChannel` tùy cách endpoint chạy. **Đừng mặc định mọi mapper error là một business message** hoặc mọi lỗi sẽ truyền đồng bộ tới HTTP caller.

Nếu mapper lỗi giữa kết quả lớn, query/operation có thể thất bại sau khi đã map một phần bộ nhớ. Transaction rollback có thể hoàn tác SQL updates cùng transaction, nhưng **không thu hồi được Kafka/HTTP/JMS side effect đã gửi**. Vì vậy cần tránh publish từ mapper và thiết kế transaction/outbox ở boundary phù hợp.

## 20. Hiệu năng, bộ nhớ và backpressure

**`JdbcTemplate`/JDBC là blocking I/O.** `RowMapper` không biến một query thành reactive publisher; Spring Integration inbound adapter thường tạo `List<T>` trước khi phát message. Với hàng trăm nghìn rows, bộ nhớ và thời gian giữ connection có thể tăng mạnh.

Các biện pháp thường cần:

1. **Giới hạn rows tại SQL:** `LIMIT`, `TOP`, `FETCH FIRST`, keyset pagination tùy database.
2. **Giới hạn tại adapter:** `maxRows(n)` như lớp bảo vệ bổ sung, không phải tối ưu duy nhất.
3. **Index:** xây theo `WHERE state='NEW'`/`ORDER BY id` hoặc điều kiện thực tế; tránh full scan liên tục.
4. **Mapper tối giản:** không gọi HTTP, không N+1 queries, không đọc BLOB/CLOB không cần thiết.
5. **Bounded executor/queue:** kiểm soát số pollers/consumers, connection pool và backlog.
6. **Batch/claim policy:** đánh dấu/idempotency đúng transaction và xử lý recovery.
7. **Metrics:** đo query time, rows/poll, map failures, backlog và thời gian end-to-end.

Đối với WebFlux, nếu một handler cần gọi JDBC trực tiếp, hãy chạy công việc blocking trên worker/scheduler thích hợp (ví dụ Reactor `boundedElastic`) hoặc tách qua message queue; **không đặt `JdbcTemplate.query(...)` lên Netty event loop rồi kỳ vọng backpressure tự dừng SQL**. Nếu cần database reactive end-to-end, tìm hiểu R2DBC và thiết kế hợp đồng khác.

### 20.1. RowMapper là lựa chọn tốt hay không?

`BeanPropertyRowMapper` và `DataClassRowMapper` tiện cho phần lớn DTO đơn giản. Với ingestion throughput cao, mapping phức tạp hoặc driver có kiểu đặc thù, custom `RowMapper` thường dễ tối ưu và dễ kiểm soát lỗi hơn. Chỉ chọn tối ưu sau khi đo SQL/network/mapper overhead; trong phần lớn pipeline, bottleneck thường nằm ở DB query, locks hoặc I/O ngoài, không phải vài phép gán field Java.

## 21. Checklist thiết kế và những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “`RowMapper` nhận toàn bộ `ResultSet` và tự `rs.next()`” | Mapper xử lý **một row hiện tại**, JDBC framework duyệt cursor |
| “Một query trả 10 rows tạo 10 messages” | JDBC inbound thường phát **một message chứa list**; splitter mới tách |
| “Có `rowMapper(...)` là payload luôn `InboundEvent`” | Có thể là `List<InboundEvent>` trước splitter |
| “Dùng `BeanPropertyRowMapper` là đủ cho Java record” | Record nên dùng `DataClassRowMapper` hoặc mapper tùy chỉnh |
| “`getLong` SQL NULL tự thành Java null” | Primitive thường trả 0; cần `wasNull()` |
| “`created_at` LocalDateTime luôn là UTC Instant” | `LocalDateTime` không mang timezone |
| “`maxMessagesPerPoll(1)` là chỉ lấy một row” | Đó là số lần source `receive()` trong trigger |
| “Inbound `maxRows(0)` là không lấy row” | Mặc định 0 nghĩa là không giới hạn tại adapter |
| “RowMapper giúp tránh poll trùng” | Cần update/atomic claim/idempotency và recovery |
| “Có transaction JDBC là Kafka cũng rollback theo” | DB và broker không tự có distributed transaction |
| “RowMapper chạy async vì ứng dụng dùng WebFlux” | JDBC query vẫn blocking |
| “SELECT ít cột không cần kiểm tra schema” | Alias/type/NULL phải kiểm thử và quản lý migration |

**Checklist trước production:** xác định DTO và nullability; khai báo SQL projection/alias rõ; unit test RowMapper; integration test DB driver; xác định list vs row payload; chọn splitter; kiểm soát poller/limit/transaction; thiết kế claim, idempotency, ACK, recovery; theo dõi query duration, queue depth và lỗi mapper.

## 22. Bài thực hành

1. Tạo bảng `inbound_event`, chèn dữ liệu từ mục 4, chạy `JdbcTemplate.query(...)` mà không custom mapper và quan sát kiểu map nhận được.
2. Triển khai `InboundEventRowMapper` rồi xác minh SQL hai rows được chuyển thành `List<InboundEvent>`.
3. Bỏ `rs.wasNull()` khỏi một field nullable, kiểm tra trường hợp `NULL` và giải thích dữ liệu bị mất nghĩa thế nào.
4. Dùng `BeanPropertyRowMapper<EventBean>` để map `event_key` → `eventKey`; sửa alias để kiểm chứng mapping.
5. Dùng `DataClassRowMapper.newInstance(InboundEvent.class)` cho record và so sánh cách xử lý `LocalDateTime`/`Integer` với mapper viết tay.
6. Tạo query join có hai cột `id`; thêm SQL aliases và viết RowMapper đúng nhãn cột để không đọc nhầm.
7. Dùng `Jdbc.inboundAdapter(dataSource, selectSql).rowMapper(...)` trên Spring Integration 7.x; quan sát payload trước và sau splitter.
8. Chuyển flow tương tự sang Spring Integration 6.x bằng `JdbcPollingChannelAdapter#setRowMapper`; giải thích vì sao không dùng factory Java DSL 7.x.
9. Bỏ `.split()` và gọi handler typed `InboundEvent`; quan sát lỗi type mismatch, sau đó sửa hợp đồng payload.
10. So sánh `maxRows(25)` với `maxMessagesPerPoll(1)`; đo số lần query và số messages nhận được.
11. Cấu hình `UPDATE state='CLAIMED'` sau SELECT, thử hai pollers chạy đồng thời và nêu hạn chế của select-then-update.
12. Xây dựng query SQL giới hạn tại DB bằng `LIMIT`/`TOP`/`FETCH FIRST` theo vendor và dùng index phù hợp.
13. Dùng JDBC outbound gateway SELECT với `RowMapper<InboundEvent>`, thử `maxRows(1)`, `maxRows(0)` và trường hợp 0 rows.
14. Thêm stored procedure trả result set `events`, ánh xạ bằng `returningResultSetRowMapper`; phân biệt `expectSingleResult` với một row.
15. Viết Mockito test cho `InboundEventRowMapper`, bao gồm `NULL`, sai tên cột, timestamp và lỗi schema.
16. Viết H2/production-compatible DB integration test kiểm tra mapper, rồi test message shape của inbound flow qua một `QueueChannel` test-only.
17. Mô phỏng DB query trả 10.000 rows, đo heap/latency và áp dụng batch giới hạn; không dùng unbounded list trong gateway.
18. Thiết kế lease/outbox khi một row đã `CLAIMED` nhưng tiến trình crash trước khi Kafka nhận event; giải thích tại sao sửa RowMapper không giải quyết mất dữ liệu.

**Tình huống tổng hợp:** hệ thống ERP lưu hàng chục nghìn dòng `order_event`, Spring Integration poll 50 dòng một lần và đưa sang Kafka. Hai instance cùng chạy, một instance bị crash sau khi đánh dấu rows là `CLAIMED`. Hãy xác định shape của payload trước/sau splitter, điều kiện query, atomic claim, lease/recovery, event ID ổn định, transaction boundary và cách kiểm thử RowMapper để tránh vừa mất row vừa phát trùng vô hạn.

## 23. Tài liệu tham khảo

- [Spring Integration — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): kết quả SELECT thành `List` payload, mapper mặc định, splitter, SELECT/UPDATE và poller.
- [Spring Integration — JDBC Outbound Gateway](https://docs.spring.io/spring-integration/reference/jdbc/outbound-gateway.html): `RowMapper` cho SELECT reply, `maxRows` và empty list behavior.
- [Spring Integration — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.inboundAdapter`, `Jdbc.outboundGateway` và các DSL specs từ Spring Integration 7.0.
- [Spring Integration API — JdbcInboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcInboundChannelAdapterSpec.html): `rowMapper`, `maxRows`, `updateSql` và parameter source factory.
- [Spring Integration API — JdbcPollingChannelAdapter 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): constructor, `setRowMapper`, `setMaxRows`, SQL update sau poll.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `RowMapper`, `ResultSetExtractor` và callback contracts.
- [Spring Framework API — BeanPropertyRowMapper](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html): bean properties, column labels, null primitives và chi phí convenience mapping.
- [Spring Framework API — DataClassRowMapper](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html): Java record/Kotlin data class constructor mapping.
- [Spring Integration — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): transaction trong polling message flow và downstream.

> **Ghi nhớ:** `RowMapper<T>` biến **một hàng của JDBC `ResultSet` thành một object `T`**, còn JDBC inbound adapter thường đóng gói **toàn bộ `List<T>` vào một message**. Muốn mỗi row thành message riêng phải dùng splitter. Thiết kế chắc chắn cần DTO/alias/nullability rõ ràng, test với JDBC driver thật, giới hạn query/poller hợp lý và tách trách nhiệm mapping khỏi transaction, delivery, idempotency và recovery.
