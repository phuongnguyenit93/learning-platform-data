# UpdateSqlParameterSource và expression trong Spring Integration JDBC

## 1. Bài toán: SELECT một lô bản ghi rồi UPDATE đúng những bản ghi đó

Một ứng dụng tích hợp có thể nhận đơn hàng từ database, chuẩn hóa dữ liệu rồi chuyển sang Kafka, JMS, AMQP hoặc HTTP. Thay vì liên tục đọc cùng những bản ghi, một **JDBC inbound channel adapter** thường thực hiện hai bước trong mỗi lần poll:

1. Chạy câu `SELECT` để lấy các bản ghi đủ điều kiện, ví dụ các sự kiện có `state = 'NEW'`.
2. Chạy câu `UPDATE` để đánh dấu **chính những bản ghi vừa lấy** thành `CLAIMED`, tránh chúng bị chọn lại trong lần poll kế tiếp.

Thách thức là câu `UPDATE` cần biết danh sách ID từ **kết quả của SELECT**, không phải một tham số bất biến viết sẵn trong cấu hình. `SqlParameterSourceFactory`, cụ thể là thuộc tính **`updateSqlParameterSourceFactory`** của JDBC inbound adapter, giải quyết việc biến kết quả truy vấn thành các tham số SQL. Khi quy tắc ánh xạ phức tạp, ta có thể dùng **`ExpressionEvaluatingSqlParameterSourceFactory`** để tính tham số bằng **SpEL expression**.

Chủ đề nằm trong chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**, nơi chúng ta kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`. Module cũng bao gồm file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; ở đây trọng tâm là **hợp đồng SELECT → UPDATE → message**, mapping, transaction, lỗi và vòng đời kết nối.

~~~mermaid
flowchart LR
    P["Poller"] --> I["JDBC inbound adapter"]
    I --> S["SELECT NEW rows"]
    S --> R["List<Row> hoặc List<DTO>"]
    R --> F["SqlParameterSourceFactory"]
    F --> U["UPDATE ... WHERE id IN (:ids)"]
    U --> D[("Database")]
    R --> M["Message<List<Row>>"]
    M --> X["Splitter nếu cần"]
    X --> N["Kafka / JMS / handler"]
~~~

**Mục tiêu học tập:** hiểu tham số mặc định `:id`, biết khi nào cần custom `SqlParameterSourceFactory`, phân biệt biểu thức SpEL với placeholder SQL, chọn `updatePerRow(false/true)`, cấu hình `selectSqlParameterSource` riêng, kiểm thử transaction và nhận diện giới hạn của mô hình “đọc rồi đánh dấu”.

## 2. Hợp đồng của từng thành phần

| Thành phần | Vai trò | Điều không tự làm |
|---|---|---|
| `JdbcPollingChannelAdapter` | Chạy SELECT, có thể chạy UPDATE sau SELECT, trả payload danh sách | Không đảm bảo exactly-once giữa DB và Kafka |
| `RowMapper<T>` | Biến **một** hàng `ResultSet` thành `T` | Không tạo một message riêng cho từng row |
| `SqlParameterSource` | Cung cấp giá trị/SQL type cho các tên `:param` | Không chạy SQL |
| `SqlParameterSourceFactory` | Tạo `SqlParameterSource` từ đầu vào mỗi lần được gọi | Không phải transformer của message payload |
| `ExpressionEvaluatingSqlParameterSourceFactory` | Map tên SQL param sang biểu thức SpEL | Không tự làm mọi `:param` thành SpEL |
| `updatePerRow` | Chọn phạm vi xử lý tham số cho từng row hay cả batch | Không tự cấp transaction cho mỗi row |
| `selectSqlParameterSource` | Cấp tham số cho SELECT trước khi có kết quả | Không nhận List rows do query sắp thực hiện |
| Poller/transaction manager | Xác định lịch poll và phạm vi transaction | Không tự commit atomic với broker/HTTP |

Luồng dữ liệu khái niệm:

~~~text
DataSource / JdbcTemplate
  SELECT ... WHERE state = 'NEW'
    -> List<Map<String,Object>> hoặc List<EventRow>
      -> updateSqlParameterSourceFactory.createParameterSource(input)
        -> SqlParameterSource: {"ids": [101,102,103]}
          -> UPDATE ... WHERE id IN (:ids)
      -> Message<List<EventRow>>
        -> Splitter, Filter, Router, Service Activator ...
~~~

Đây là mô hình giải thích, không phải cam kết thứ tự gọi nội bộ ở mọi phiên bản. Những điểm cần giữ đúng là: **UPDATE lấy tham số từ dữ liệu đã SELECT**, còn message đầu ra mang payload các rows truy vấn (sau `RowMapper` nếu có).

## 3. Không cần custom factory: quy ước tham số mặc định `:id`

Spring Integration JDBC inbound adapter hỗ trợ một quy tắc mặc định rất tiện: cột có tên `id` trong kết quả SELECT được **chiếu thành danh sách các giá trị** cho tham số `:id` của câu UPDATE.

Ví dụ cấu hình XML:

~~~xml
<!-- Fragment XML, giả định đã khai báo namespace int và int-jdbc. -->
<int:channel id="eventBatches"/>

<int-jdbc:inbound-channel-adapter
    id="pendingEventPoller"
    data-source="dataSource"
    channel="eventBatches"
    query="SELECT id, event_key, state
           FROM sync_event
           WHERE state = 'NEW'
           ORDER BY id"
    update="UPDATE sync_event
            SET state = 'CLAIMED'
            WHERE id IN (:id) AND state = 'NEW'">

    <int:poller fixed-delay="5000"
                max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

Nếu SELECT nhận các row có ID `101, 102, 103`, giá trị tương ứng với `:id` là một collection `[101, 102, 103]`. Spring JDBC **named parameter support** triển khai việc bind collection vào `IN (...)`.

~~~text
SELECT rows: [{id:101,...},{id:102,...},{id:103,...}]
    |
Mặc định tạo SqlParameterSource với key "id"
    |
id = [101,102,103]
    |
UPDATE ... WHERE id IN (:id)
~~~

**`:id` không phải “nhúng SpEL vào SQL”.** Đây là tên parameter do Spring JDBC xử lý, cùng quy ước lấy thuộc tính/cột từ danh sách kết quả của Spring Integration. Với các tên/path phức tạp, hoặc khi cần kết hợp nhiều field và biến đổi kiểu, hãy dùng factory tường minh thay vì đặt biểu thức SpEL tùy ý trực tiếp sau dấu hai chấm.

**Giới hạn quan trọng:** quy ước này không giải quyết tranh chấp giữa hai pods cùng SELECT row `NEW`. Nó cũng không quyết định điều gì xảy ra nếu UPDATE ảnh hưởng 0 rows do instance khác vừa claim trước.

## 4. Phân biệt SELECT params và UPDATE params

Một inbound poll có **hai câu SQL** với hai nguồn tham số khác nhau:

| SQL | Khi thực thi | Tham số xuất phát từ đâu? |
|---|---|---|
| `SELECT ... WHERE state = :wantedState` | Trước khi có rows | `selectSqlParameterSource`, một parameter source dùng lại qua các lần poll |
| `UPDATE ... WHERE id IN (:ids)` | Sau khi đã SELECT rows | `updateSqlParameterSourceFactory`, tạo nguồn tham số từ **kết quả SELECT** |
| `UPDATE ... WHERE id = :rowId` với `updatePerRow(true)` | Cho từng row đã SELECT | Factory nhận **một row** mỗi lần |

Đừng cấu hình `selectSqlParameterSource` và nghĩ nó sẽ tự cấp `:ids` từ những row **chưa được SELECT**. Ngược lại, không dùng `updateSqlParameterSourceFactory` làm nguồn tham số cho câu SELECT.

### 4.1. Bảng nhận diện gốc đánh giá

| Nơi đánh giá | Đối tượng `#root` của SpEL |
|---|---|
| Inbound UPDATE, `updatePerRow(false)` | **Danh sách kết quả SELECT** |
| Inbound UPDATE, `updatePerRow(true)` | **Một row** của kết quả SELECT |
| Inbound SELECT với `createParameterSourceNoCache(root)` | **Đối tượng root do bạn cung cấp**, không phải message/rows |
| Outbound JDBC adapter dùng expression factory | Thường là **`Message<?>` đầu vào** (payload + headers) |

Đây là một trong những điểm dễ nhầm nhất khi dùng cùng `ExpressionEvaluatingSqlParameterSourceFactory` ở cả inbound và outbound: **gốc đánh giá phụ thuộc endpoint và chế độ xử lý**, không chỉ tên class.

## 5. Chuẩn bị môi trường thực hành và bảng dữ liệu

Các ví dụ dùng Java 17+, Spring Boot, Spring JDBC, Spring Integration JDBC và H2 để thấy rõ tác động của UPDATE sau SELECT.

~~~groovy
// build.gradle - dependency management của Spring Boot quản lý versions
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml cho demo H2
spring:
  datasource:
    url: "jdbc:h2:mem:sql_parameter_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

Giả sử `src/main/resources/schema.sql` trong ứng dụng thực hành có:

~~~sql
CREATE TABLE sync_event (
    id             BIGINT NOT NULL PRIMARY KEY,
    event_key      VARCHAR(80) NOT NULL UNIQUE,
    event_type     VARCHAR(80) NOT NULL,
    state          VARCHAR(24) NOT NULL,
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at     TIMESTAMP NULL
);

INSERT INTO sync_event (id, event_key, event_type, state, attempt_count)
VALUES (101, 'evt-101', 'order.created', 'NEW', 0),
       (102, 'evt-102', 'order.paid', 'NEW', 0),
       (103, 'evt-103', 'order.shipped', 'NEW', 1),
       (104, 'evt-104', 'order.cancelled', 'CLAIMED', 1);
~~~

**Các ví dụ sau là phương án thay thế**, không bật tất cả pollers cùng lúc: nếu chạy nhiều flow cùng đọc `state='NEW'`, chúng có thể cạnh tranh và làm kết quả học tập khó dự đoán. H2 phù hợp demo mapping; locking, `SKIP LOCKED`, batch counts và behavior transaction phải kiểm chứng lại với DB production.

## 6. Java DSL 7.x: UPDATE theo danh sách ID bằng custom factory

Từ **Spring Integration 7.0**, module JDBC có Java DSL `org.springframework.integration.jdbc.dsl.Jdbc`. `JdbcInboundChannelAdapterSpec` có các phương thức `rowMapper(...)`, `maxRows(...)`, `updateSql(...)`, `updatePerRow(...)`, `updateSqlParameterSourceFactory(...)` và `selectSqlParameterSource(...)`.

### 6.1. DTO và RowMapper

~~~java
package com.example.integration;

import java.time.LocalDateTime;

public record EventRow(
    long id, String eventKey, String eventType,
    String state, int attemptCount, LocalDateTime createdAt) {
}
~~~

~~~java
package com.example.integration;

import org.springframework.jdbc.core.RowMapper;

public final class EventRowMapper implements RowMapper<EventRow> {
    @Override
    public EventRow mapRow(
            java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException {
        return new EventRow(
            rs.getLong("id"),
            rs.getString("event_key"),
            rs.getString("event_type"),
            rs.getString("state"),
            rs.getInt("attempt_count"),
            rs.getTimestamp("created_at").toLocalDateTime());
    }
}
~~~

Các cột `id`, `attempt_count` và `created_at` đều NOT NULL trong schema demo. Nếu production cho phép NULL, cần dùng Java wrapper hoặc kiểm tra `rs.wasNull()`/timestamp null trước khi gọi `toLocalDateTime()`.

### 6.2. SELECT, bind danh sách ID, UPDATE, emit message

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
public class EventBatchPollingFlow {

    @Bean
    public IntegrationFlow pollNewEvents(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        String selectSql = """
            SELECT id, event_key, event_type, state,
                   attempt_count, created_at
            FROM sync_event
            WHERE state = 'NEW'
            ORDER BY id
            """;

        String updateSql = """
            UPDATE sync_event
            SET state = 'CLAIMED', claimed_at = CURRENT_TIMESTAMP,
                attempt_count = attempt_count + 1
            WHERE id IN (:selectedIds) AND state = 'NEW'
            """;

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource, selectSql)
                    .rowMapper(new EventRowMapper())
                    .maxRows(25)
                    .updateSql(updateSql)
                    .updatePerRow(false)
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> rows = (List<?>) result;
                        List<Long> ids = rows.stream()
                            .map(EventRow.class::cast)
                            .map(EventRow::id)
                            .toList();
                        return new MapSqlParameterSource(
                            "selectedIds", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
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

**Điều xảy ra khi SELECT trả ba rows `101, 102, 103`:**

1. `RowMapper` ánh xạ từng row thành `EventRow`.
2. `updatePerRow(false)` khiến factory nhận **toàn bộ `List<EventRow>`**.
3. Lambda tạo `MapSqlParameterSource` với `selectedIds = [101,102,103]`.
4. `NamedParameterJdbcTemplate` bind `:selectedIds` trong mệnh đề `IN (...)`, UPDATE các row khớp.
5. Source phát **một message chứa `List<EventRow>`**; `split()` tách thành ba messages tới `claimedEvents`.

**Lưu ý:** payload `EventRow.state` được map từ SELECT trước UPDATE nên trong DTO có thể vẫn là `NEW`, dù database đã cập nhật `CLAIMED`. Nếu downstream cần trạng thái mới, hãy áp dụng quy tắc domain/transformer tường minh; không giả định RowMapper tự đọc lại dữ liệu.

`updateSqlParameterSourceFactory(result -> ...)` là một `SqlParameterSourceFactory` functional interface. Nó nhận **kết quả SELECT**, không phải `Message<?>` từ caller như JDBC outbound handler. Bản thân Java lambda là **một lựa chọn thay thế** cho expression factory, đặc biệt khi muốn tránh phụ thuộc cú pháp SpEL.

### 6.3. Consumer nhận từng row sau Splitter

~~~java
package com.example.integration;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class ClaimedEventConsumer {
    @ServiceActivator(inputChannel = "claimedEvents")
    public void process(EventRow event) {
        System.out.printf("Process event %s from DB%n", event.eventKey());
    }
}
~~~

`System.out.printf` chỉ để demo. Trong production, một log entry **không phải biên nhận** Kafka/JMS đã nhận, cũng không xác nhận nghiệp vụ đã xử lý bền vững. Phải thiết kế ACK, outbox, retry và idempotency riêng.

## 7. updatePerRow(false) và updatePerRow(true) có khác biệt gì?

`JdbcPollingChannelAdapter#setUpdatePerRow(boolean)` mặc định là **false**.

| Thuộc tính | `false` (mặc định) | `true` |
|---|---|---|
| Đối tượng truyền vào factory | **List các rows** của SELECT | **Một row** mỗi lần |
| SQL thường dùng | `WHERE id IN (:ids)` | `WHERE id = :rowId` |
| Số lệnh UPDATE | Thường một UPDATE cho lô | Có thể một UPDATE cho mỗi row |
| Phù hợp | Đánh dấu cùng trạng thái cho cả lô | Row có trạng thái/giá trị UPDATE riêng |
| SpEL `#root` | List | Row (Map hoặc DTO đã map) |
| Chi phí DB | Ít lượt SQL, có thể có danh sách tham số dài | Nhiều lượt SQL và round trips |
| Đảm bảo delivery | Không có sẵn | Cũng không có sẵn |

Ví dụ với 3 rows:

~~~text
updatePerRow(false):
  input to factory = [row101, row102, row103]
  UPDATE ... WHERE id IN (101,102,103)

updatePerRow(true):
  input to factory = row101  -> UPDATE ... WHERE id = 101
  input to factory = row102  -> UPDATE ... WHERE id = 102
  input to factory = row103  -> UPDATE ... WHERE id = 103
~~~

**Không nhầm update-per-row với “một transaction cho từng row”.** Transaction được quyết định bởi poller/transaction manager. Khi có một transaction bao quanh poll operation, nhiều updates per-row có thể vẫn thuộc cùng transaction; cần kiểm tra rollback và locking của database đang dùng.

## 8. ExpressionEvaluatingSqlParameterSourceFactory: SpEL cho từng row

Khi không muốn viết lambda mapping, Spring Integration cung cấp `ExpressionEvaluatingSqlParameterSourceFactory`. Tên param trong SQL vẫn là một tên đơn giản `:rowId`, còn **biểu thức SpEL** được khai báo ở factory.

Với `updatePerRow(true)` và row dạng Map có keys `id`/`event_key`, biểu thức `#root['id']` lấy ID của **row hiện tại**.

### 8.1. Tạo bean expression factory

~~~java
package com.example.integration;

import java.sql.Types;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.ExpressionEvaluatingSqlParameterSourceFactory;

@Configuration
public class EventSqlParameterConfiguration {

    @Bean("perRowUpdateParameters")
    public ExpressionEvaluatingSqlParameterSourceFactory
            perRowUpdateParameters() {

        var factory =
            new ExpressionEvaluatingSqlParameterSourceFactory();
        factory.setParameterExpressions(Map.of(
            "rowId", "#root['id']",
            "nextState", "'CLAIMED'"));
        factory.setSqlParameterTypes(Map.of(
            "rowId", Types.BIGINT,
            "nextState", Types.VARCHAR));
        return factory;
    }
}
~~~

**Giải thích:**

- `"rowId"` là tên param **SQL** trong `WHERE id = :rowId`.
- `"#root['id']"` là **SpEL** đọc key `id` của Map được adapter chuyển vào factory.
- `"'CLAIMED'"` là literal string trong SpEL, không phải tên bean/property `CLAIMED`.
- `setSqlParameterTypes(...)` khai báo JDBC types khi driver không tự suy đúng hoặc khi cần kiểm soát việc bind; tính năng này có từ Spring Integration 5.0.
- Bean do Spring quản lý giúp factory có lifecycle/bean resolver nếu biểu thức sử dụng `@beanName`.

### 8.2. Gắn factory vào inbound adapter

~~~java
package com.example.integration;

import java.time.Duration;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.ExpressionEvaluatingSqlParameterSourceFactory;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class PerRowExpressionFlow {

    @Bean
    public IntegrationFlow pollAndUpdatePerRow(
            DataSource dataSource,
            PlatformTransactionManager transactionManager,
            @Qualifier("perRowUpdateParameters")
            ExpressionEvaluatingSqlParameterSourceFactory params) {

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource,
                    "SELECT id, event_key, state FROM sync_event "
                  + "WHERE state = 'NEW' ORDER BY id")
                    .maxRows(10)
                    .updatePerRow(true)
                    .updateSql(
                        "UPDATE sync_event "
                      + "SET state = :nextState, "
                      + "    claimed_at = CURRENT_TIMESTAMP "
                      + "WHERE id = :rowId AND state = 'NEW'")
                    .updateSqlParameterSourceFactory(params),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .channel("perRowEventBatches")
            .get();
    }
}
~~~

**Hợp đồng payload:** đoạn này không khai báo `rowMapper(...)` nên mỗi row trong `List` mặc định là một `Map` do Spring JDBC tạo ra. Cần kiểm tra tên cột/key trên driver thực tế, đặc biệt nếu đang dựa vào `#root['id']`. Với cơ sở dữ liệu có column labels khác chữ hoa/chữ thường, hãy đặt alias rõ hoặc dùng custom RowMapper/parameter factory phù hợp.

Đây là **phương án thay thế** cho flow tại mục 6; không nên bật cả hai pollers cùng đọc bảng `sync_event` của một bài test đơn giản.

### 8.3. Khi nào expression là một lựa chọn tốt?

SpEL thích hợp khi bạn cần đọc thuộc tính lồng nhau, kết hợp field, lấy một bean do Spring quản lý hoặc ép kiểu dữ liệu theo quy tắc khai báo được. Nếu mapping đòi hỏi validation phức tạp hoặc phụ thuộc nhiều bước, một Java `SqlParameterSourceFactory` rõ ràng thường dễ debug và unit test hơn.

**Không dùng SpEL để biến tên bảng hoặc tên cột thành SQL động không kiểm soát.** Named parameters bind **giá trị**; SQL identifiers phải được chọn từ allowlist/config đáng tin cậy.

## 9. Expression cho cả danh sách với updatePerRow(false)

SpEL còn hỗ trợ **collection projection** khi gốc là một list. Với kết quả SELECT gồm các Map có key `id`, biểu thức `#root.![#this['id']]` tạo list IDs từ toàn bộ rows.

~~~java
@Bean("listUpdateParameters")
ExpressionEvaluatingSqlParameterSourceFactory listUpdateParameters() {
    var factory = new ExpressionEvaluatingSqlParameterSourceFactory();
    factory.setParameterExpressions(java.util.Map.of(
        "ids", "#root.![#this['id']]"));
    factory.setSqlParameterTypes(java.util.Map.of(
        "ids", java.sql.Types.BIGINT));
    return factory;
}
~~~

Mảnh cấu hình Java DSL tương ứng:

~~~java
Jdbc.inboundAdapter(dataSource,
        "SELECT id, event_key, state FROM sync_event "
      + "WHERE state = 'NEW' ORDER BY id")
    .maxRows(25)
    .updatePerRow(false)
    .updateSql(
        "UPDATE sync_event SET state = 'CLAIMED' "
      + "WHERE id IN (:ids) AND state = 'NEW'")
    .updateSqlParameterSourceFactory(listUpdateParameters)
~~~

`listUpdateParameters` là bean `ExpressionEvaluatingSqlParameterSourceFactory` đã khởi tạo; ví dụ chỉ là **mảnh DSL** đặt trong cấu hình `IntegrationFlow`. Với ba rows, biểu thức có thể tạo `ids=[101,102,103]`.

**Chú ý về typing:** collection projection phụ thuộc cấu trúc row. Nếu `RowMapper` đổi Map thành Java record, thay `#this['id']` bằng property access thích hợp (hoặc dùng lambda factory như mục 6). Một biểu thức hợp lệ trong mode per-row có thể sai ngay khi chuyển sang mode toàn list, và ngược lại.

### 9.1. Vì sao `:ids` không phải SpEL?

~~~text
SQL:  WHERE id IN (:ids)
                 |
Tên placeholder của NamedParameterJdbcTemplate
                 |
Factory: "ids" -> SpEL "#root.![#this['id']]"
                 |
SqlParameterSource: {ids=[101,102,103]}
~~~

SpEL là **giá trị cấu hình của factory**. SQL chỉ tham chiếu tên tham số; chúng là hai ngôn ngữ khác nhau. Vì Spring named-parameter SQL không cho phép mọi ký tự đặc biệt của SpEL xuất hiện trong tên tham số, cách tách này vừa rõ ràng vừa dễ bảo trì.

## 10. SqlParameterSourceFactory có nhất thiết phải dùng SpEL?

Không. `SqlParameterSourceFactory` trong package `org.springframework.integration.jdbc` là functional interface với một phương thức:

~~~java
package org.springframework.integration.jdbc;

import org.springframework.jdbc.core.namedparam.SqlParameterSource;

@FunctionalInterface
public interface SqlParameterSourceFactory {
    SqlParameterSource createParameterSource(Object input);
}
~~~

Ta có thể dùng Java lambda hoặc class chuyên biệt:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.integration.jdbc.SqlParameterSourceFactory;

SqlParameterSourceFactory factory = input -> {
    if (!(input instanceof List<?> rows)) {
        throw new IllegalArgumentException("Expected list of SQL rows");
    }
    List<Long> ids = rows.stream()
        .map(row -> (Map<?, ?>) row)
        .map(row -> ((Number) row.get("id")).longValue())
        .toList();
    return new MapSqlParameterSource("ids", ids);
};
~~~

Đoạn này giả định dữ liệu map có key `id`; đặt alias trong SELECT và test với driver thật. Với `EventRow` record, lấy `EventRow::id` như ví dụ mục 6, thường an toàn hơn ép kiểu Map.

**Quy tắc lựa chọn:**

- Mapping ngắn, cần khai báo ở cấu hình → `ExpressionEvaluatingSqlParameterSourceFactory`.
- Mapping cần kiểm tra kiểu, chuẩn hóa NULL, xử lý collection hoặc validation phức tạp → Java lambda/custom class.
- Mapping mặc định đã đáp ứng `:id` → **không cần factory riêng**.

Không nên tạo một factory mới **mỗi row** trong mapper. Hãy đăng ký bean/factory dùng chung và để adapter tạo `SqlParameterSource` phù hợp cho lần UPDATE tương ứng.

## 11. Tham số của SELECT: createParameterSourceNoCache

Với SELECT:

~~~sql
SELECT id, event_key, state
FROM sync_event
WHERE state = :wantedState
ORDER BY id;
~~~

Tại thời điểm SELECT, adapter **chưa có result list**. Vì thế nó nhận `selectSqlParameterSource` — một `SqlParameterSource` dùng qua các poll, không phải factory tạo từ rows mới.

Với tham số **bất biến**, có thể đơn giản dùng:

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var selectParams = new MapSqlParameterSource(
    "wantedState", "NEW");
~~~

Nếu tham số cần được tính lại giữa các lần poll, ví dụ từ bean `@pollStateProvider.currentState()`, dùng `ExpressionEvaluatingSqlParameterSourceFactory.createParameterSourceNoCache(...)` để tránh lưu giá trị cũ.

~~~java
package com.example.integration;

import java.sql.Types;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.ExpressionEvaluatingSqlParameterSourceFactory;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

@Configuration
public class SelectSqlParameterConfiguration {

    @Bean("selectExpressionFactory")
    public ExpressionEvaluatingSqlParameterSourceFactory
            selectExpressionFactory() {
        var factory =
            new ExpressionEvaluatingSqlParameterSourceFactory();
        factory.setParameterExpressions(Map.of(
            "wantedState", "@pollStateProvider.currentState()"));
        factory.setSqlParameterTypes(Map.of(
            "wantedState", Types.VARCHAR));
        return factory;
    }

    @Bean("selectSqlParameters")
    public SqlParameterSource selectSqlParameters(
            @Qualifier("selectExpressionFactory")
            ExpressionEvaluatingSqlParameterSourceFactory factory) {
        return factory.createParameterSourceNoCache("");
    }
}
~~~

Ở đây cần có một bean tên `pollStateProvider` với method `currentState()` trả state hợp lệ như `NEW`. Đây là một ví dụ về **SpEL tham chiếu bean do Spring quản lý**; không nhận tùy ý tên bean hay đoạn SpEL từ HTTP request.

Gắn vào DSL:

~~~java
Jdbc.inboundAdapter(dataSource,
        "SELECT id, event_key, state "
      + "FROM sync_event WHERE state = :wantedState")
    .selectSqlParameterSource(selectSqlParameters)
    .maxRows(25)
~~~

**Điểm quan trọng về cache:**

- `createParameterSource(input)` tạo source có thể **cache kết quả đánh giá** của tham số. Với một UPDATE trên một batch cố định, điều đó giúp cùng parameter được dùng nhiều lần mà không tính lại.
- `createParameterSourceNoCache(input)` không cache; phù hợp cho `selectSqlParameterSource` được tái sử dụng qua nhiều lần poll nếu giá trị cần thay đổi.
- Vì không cache, nếu cùng `:wantedState` xuất hiện nhiều lần trong một câu SELECT, biểu thức có thể được đánh giá nhiều lần trong một lượt. Tránh biểu thức có side effect hoặc kết quả không ổn định ngay giữa một SQL statement.

Nếu trạng thái cần thay đổi theo một lịch nhất quán, cân nhắc snapshot giá trị trước một poll thay vì một method mỗi lần được gọi có thể trả kết quả khác nhau. SQL parameter expressions nên **thuần và có thể dự đoán**.

## 12. updateSqlParameterSourceFactory khác selectSqlParameterSource

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant S as SELECT parameter source
    participant A as JdbcPollingChannelAdapter
    participant DB as Database
    participant U as UPDATE factory
    P->>A: receive()
    A->>S: getValue(:wantedState)
    S-->>A: "NEW"
    A->>DB: SELECT ... state=:wantedState
    DB-->>A: List<Row> (101,102,103)
    A->>U: createParameterSource(List<Row>)
    U-->>A: {ids:[101,102,103]}
    A->>DB: UPDATE ... id IN (:ids)
    A-->>P: Message<List<Row>>
~~~

| Câu hỏi | SELECT | UPDATE |
|---|---|---|
| Có result list trước khi chạy? | Chưa | Có |
| Adapter nhận gì? | `SqlParameterSource` | `SqlParameterSourceFactory` |
| Cấu hình DSL 7.x | `selectSqlParameterSource(...)` | `updateSqlParameterSourceFactory(...)` |
| Cấu hình Java 6.x | `setSelectSqlParameterSource(...)` | `setUpdateSqlParameterSourceFactory(...)` |
| Ví dụ SQL | `WHERE state=:wantedState` | `WHERE id IN (:ids)` |
| Khi cần tham số động | `createParameterSourceNoCache` hoặc nguồn dynamic phù hợp | `createParameterSource(result)` trên mỗi lô/row |

**Không chia sẻ nhầm một parameter source với transaction state:** giá trị SELECT có thể do cấu hình/bean quyết định, trong khi IDs của UPDATE phải lấy từ **các rows đã chọn trong cùng poll**. Nếu nối danh sách IDs từ poll trước, bạn có thể đánh dấu sai dữ liệu.

## 13. updatePerRow(true) dùng khi từng row có quy tắc khác nhau

Nếu mỗi event cần cập nhật bằng giá trị riêng, có thể dùng `updatePerRow(true)` và `SqlParameterSourceFactory` lấy thông tin từ row:

~~~java
// Mảnh DSL: giả sử payload SELECT là Map có "id", "attempt_count".
Jdbc.inboundAdapter(dataSource,
        "SELECT id, attempt_count FROM sync_event "
      + "WHERE state='NEW' ORDER BY id")
    .maxRows(10)
    .updatePerRow(true)
    .updateSql(
        "UPDATE sync_event "
      + "SET attempt_count = :nextAttempt, state = 'CLAIMED' "
      + "WHERE id = :rowId AND state = 'NEW'")
    .updateSqlParameterSourceFactory(row -> {
        Map<?, ?> values = (Map<?, ?>) row;
        long id = ((Number) values.get("id")).longValue();
        int attempt = ((Number) values.get("attempt_count")).intValue();
        return new MapSqlParameterSource()
            .addValue("rowId", id)
            .addValue("nextAttempt", attempt + 1);
    })
~~~

`Map`, `MapSqlParameterSource` cần import đúng trong file Java thực. Đây là **mảnh cấu hình**: nếu dùng database driver khác, kiểm tra column labels. Trường hợp counter có thể được tăng an toàn trực tiếp bằng `SET attempt_count = attempt_count + 1` thay vì truyền `nextAttempt` tính từ row; ví dụ minh họa cách bind **giá trị tính toán theo từng row**, không khuyến nghị optimistic counter logic này khi có nhiều workers.

**Khi có cạnh tranh:** hai pollers cùng đọc `attempt_count=1`, cùng tính `nextAttempt=2` rồi UPDATE có thể gây lost update hoặc 0 rows theo điều kiện. Nếu cần optimistic concurrency, thêm version predicate; nếu cần atomic counter, tính ở database.

## 14. SQL parameter types, static parameters và expression caching

`ExpressionEvaluatingSqlParameterSourceFactory` hỗ trợ:

~~~java
factory.setParameterExpressions(Map.of(
    "rowId", "#root['id']",
    "normalizedKey", "#root['event_key'].toUpperCase()"));

factory.setSqlParameterTypes(Map.of(
    "rowId", java.sql.Types.BIGINT,
    "normalizedKey", java.sql.Types.VARCHAR));

factory.setStaticParameters(Map.of(
    "sourceSystem", "ERP"));
~~~

Các API này được gọi trong cấu hình factory trước khi sử dụng. Với expression factory, **static parameters có độ ưu tiên cao hơn parameter expressions nếu cùng tên**. Vì vậy, tránh vô tình cấu hình một tham số ở cả hai nơi.

| Nhu cầu | Cách làm |
|---|---|
| Đổi key `event_key` thành uppercase | `"#root['event_key'].toUpperCase()"` |
| Dùng constant trong SQL | `setStaticParameters(Map.of("sourceSystem","ERP"))` |
| Ép kiểu BIGINT | `setSqlParameterTypes(Map.of("rowId", Types.BIGINT))` |
| SELECT status thay đổi theo thời gian | `createParameterSourceNoCache(...)` |
| UPDATE dùng ID của một row | `updatePerRow(true)` và row-root SpEL |
| UPDATE dùng IDs của nhiều rows | `updatePerRow(false)` và list projection/lambda |

**NULL safety:** nếu `event_key` có thể null, biểu thức `toUpperCase()` sẽ lỗi. SpEL có safe navigation `?.`, nhưng kết quả null vẫn phải được SQL/DB constraint xử lý. Dùng validation/DTO phù hợp thay vì âm thầm biến dữ liệu hỏng thành một khóa trống.

## 15. Xml và cấu hình Java trực tiếp cho Spring Integration 6.x

Ở Spring Integration **6.x**, lớp `JdbcPollingChannelAdapter` cùng hai setter `setUpdateSqlParameterSourceFactory` và `setSelectSqlParameterSource` đã có. Factory Java DSL `Jdbc.inboundAdapter(...)` được giới thiệu từ **7.0**, vì vậy dự án 6.x có thể dùng Java bean hoặc XML.

### 15.1. Java configuration ở 6.x

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
public class LegacyJdbcPollingFlow {

    @Bean
    public IntegrationFlow legacyEvents(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource,
                "SELECT id, event_key, state FROM sync_event "
              + "WHERE state = 'NEW' ORDER BY id");

        source.setMaxRows(25);
        source.setUpdateSql(
            "UPDATE sync_event SET state = 'CLAIMED' "
          + "WHERE id IN (:ids) AND state = 'NEW'");
        source.setUpdateSqlParameterSourceFactory(rows -> {
            var selected = (java.util.List<?>) rows;
            var ids = selected.stream()
                .map(item -> (java.util.Map<?, ?>) item)
                .map(item -> ((Number) item.get("id")).longValue())
                .toList();
            return new MapSqlParameterSource("ids", ids);
        });

        return IntegrationFlow.from(source, endpoint ->
                endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .channel("legacyEventBatches")
            .get();
    }
}
~~~

Lưu ý code dùng Java 17+ `stream().toList()`. Với Spring Integration 6.x, hãy chọn bản Spring Boot/Framework/JDK được hỗ trợ và kiểm tra imports theo dependency thực. Flow ở đây **không có splitter** nên `legacyEventBatches` nhận `Message<List<Map<...>>>`.

### 15.2. XML sử dụng expression factory

~~~xml
<!-- Fragment: khai báo namespace int, int-jdbc và beans trong context. -->
<bean id="perRowExpressions"
      class="org.springframework.integration.jdbc.ExpressionEvaluatingSqlParameterSourceFactory">
    <property name="parameterExpressions">
        <map>
            <entry key="rowId" value="#root['id']"/>
            <entry key="nextState" value="'CLAIMED'"/>
        </map>
    </property>
</bean>

<int:channel id="eventBatchMessages"/>

<int-jdbc:inbound-channel-adapter
    id="eventsFromJdbc"
    data-source="dataSource"
    channel="eventBatchMessages"
    query="SELECT id, event_key, state
           FROM sync_event WHERE state = 'NEW' ORDER BY id"
    update="UPDATE sync_event
            SET state = :nextState
            WHERE id = :rowId AND state = 'NEW'"
    update-per-row="true"
    sql-parameter-source-factory="perRowExpressions"
    max-rows="25">
    <int:poller fixed-delay="5000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

Trong XML, thuộc tính `sql-parameter-source-factory` là **UPDATE** parameter factory; còn `select-sql-parameter-source` là một bean `SqlParameterSource` khác cho SELECT. Không đưa `ExpressionEvaluatingSqlParameterSourceFactory` trực tiếp vào thuộc tính SELECT khi endpoint yêu cầu **parameter source**, không phải factory.

## 16. Poller, maxRows và tính ổn định của một lần đọc

| Cấu hình | Đơn vị | Ảnh hưởng |
|---|---|---|
| `fixedDelay(5s)` | Thời gian giữa các nhịp poll | Điều khiển tần suất truy cập DB |
| `maxMessagesPerPoll(1)` | Số lần gọi `receive()`/trigger | Không phải số rows |
| `maxRows(25)` | Rows SELECT trả mỗi lần | Không tự bảo đảm chỉ 25 rows được scan trên DB |
| SQL `LIMIT/TOP/FETCH` | Rows mà DB trả theo query | Thường có hiệu quả kiểm soát lượng đọc tốt hơn |
| `updatePerRow(false)` | Batch của rows đã chọn | UPDATE theo danh sách |
| `updatePerRow(true)` | Mỗi row của batch | UPDATE riêng từng row |
| `SqlParameterSourceFactory` | Mapping param | Không thay đổi nhịp poll |

`maxMessagesPerPoll(1)` nghĩa một lần hỏi message source trong một trigger, nhưng source có thể trả một list 25 rows. Nếu thêm splitter, downstream nhận tới 25 messages; không được suy thành 25 SQL SELECTs.

**Khi dataset lớn:** nên giới hạn ngay từ câu SELECT theo DB dialect và index, thay vì query toàn bộ bảng rồi dùng `maxRows` ở tầng JDBC. Dữ liệu đã SELECT có thể chiếm connection, memory và transaction locks trong một khoảng thời gian đáng kể.

## 17. Transaction: SELECT và UPDATE cùng poll có thực sự nguyên tử?

Spring Integration inbound adapter cho phép poller chạy trong Spring transaction:

~~~java
endpoint -> endpoint.poller(
    Pollers.fixedDelay(Duration.ofSeconds(5))
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
~~~

Với `DataSourceTransactionManager` phù hợp (hoặc transaction manager JDBC được cấu hình tương ứng), SELECT và UPDATE có thể cùng tham gia **một local DB transaction**.

~~~mermaid
sequenceDiagram
    participant Poller as Poller transaction
    participant Adapter as JDBC inbound adapter
    participant DB as Database
    participant Flow as DirectChannel consumer
    Poller->>Adapter: receive()
    Adapter->>DB: SELECT state='NEW'
    DB-->>Adapter: 101,102
    Adapter->>DB: UPDATE state='CLAIMED' WHERE id IN (...)
    Adapter-->>Flow: Message<List<Row>>
    alt Đồng bộ downstream thành công
        Flow-->>Poller: Return
        Poller->>DB: COMMIT
    else Đồng bộ downstream ném lỗi
        Flow-->>Poller: Exception
        Poller->>DB: ROLLBACK (nếu chung TX)
    end
~~~

**Điều kiện cần đọc kỹ:**

- Với `DirectChannel` và handler **đồng bộ cùng thread**, downstream có thể cùng tham gia transaction của poller.
- Với `ExecutorChannel`, `QueueChannel` hoặc publisher HTTP/Kafka bất đồng bộ, transaction từ poller **không tự vượt** sang thread/process khác.
- Transaction rollback bảo vệ **DB changes cùng local transaction**, không thu hồi được message Kafka/JMS hoặc HTTP request đã gửi và được remote xử lý.
- Một method `@Transactional` được gọi sai ngoài Spring proxy có thể không mở transaction dù annotation xuất hiện trong code.

Đừng tự kết luận rằng một lệnh UPDATE được gọi đã tương đương message được xử lý thành công trên mọi hệ thống đích.

## 18. Cạnh tranh nhiều pollers: SELECT rồi UPDATE chưa đủ chống trùng

Hai instance A và B có thể cùng chạy:

~~~text
T1  Instance A: SELECT id=101 WHERE state='NEW'
T2  Instance B: SELECT id=101 WHERE state='NEW'
T3  Instance A: UPDATE id=101 -> CLAIMED
T4  Instance A: publish event 101
T5  Instance B: UPDATE id=101 AND state='NEW' -> 0 rows
T6  Instance B: vẫn giữ row101 trong list đã SELECT
T7  Instance B: publish event 101 lần nữa
~~~

Một UPDATE có predicate `state='NEW'` giúp ngăn **ghi trùng trong DB**, nhưng **không tự xóa row khỏi danh sách kết quả SELECT ban đầu** của instance B. Nếu downstream publish dựa trên danh sách đó mà không kiểm tra quyền claim, vẫn có thể phát trùng.

Với production nhiều pods, thiết kế một trong các hướng:

1. **Atomic claim** theo DB vendor: SQL Server có thể dùng `UPDATE ... OUTPUT` với locking phù hợp; PostgreSQL có `FOR UPDATE SKIP LOCKED` kết hợp transaction; database khác cần cách riêng.
2. **Lease/reclaim:** lưu `claimed_by`/`lease_until` để tiếp tục xử lý khi worker crash.
3. **Transactional outbox:** lưu event cần phát trong cùng DB transaction, publisher riêng gửi broker và xử lý redelivery.
4. **Idempotent consumer:** event ID ổn định, unique key hoặc bảng `processed_event` để hạn chế duplicate side effects.
5. **Ràng buộc concurrency/partition:** chỉ định rõ instance nào sở hữu một partition hoặc key range khi cần.

Đừng tin rằng `updateSqlParameterSourceFactory`, SpEL hoặc `updatePerRow` tự giải quyết exactly-once; chúng chỉ tạo **tham số SQL**.

## 19. Idempotency, recovery và trạng thái CLAIMED

Nếu một poll đánh dấu row `CLAIMED` thành công rồi ứng dụng crash **trước khi Kafka nhận event**, những row đó có thể bị kẹt. Một trạng thái `CLAIMED` đơn giản chưa đủ cho vận hành dài hạn.

~~~mermaid
flowchart LR
    A["NEW"] -->|"Claim atomically"| B["CLAIMED"]
    B -->|"Publish + confirm"| C["PROCESSED"]
    B -->|"Worker crash / lease expired"| D["RECOVERY"]
    D -->|"Retry with stable eventId"| A
    D -->|"Permanent failure"| E["FAILED / DLQ"]
~~~

**Quy tắc đề xuất:** có một business `eventKey` ổn định; trạng thái `CLAIMED` phải có owner/lease/attempt count; khi lease hết hạn, recovery worker có thể reclaim theo chính sách; sau khi publish thành công, ghi mốc đã hoàn tất. Với transactional outbox, thường không cần trực tiếp đánh dấu `NEW → CLAIMED` theo cách poller của ví dụ, vì event lifecycle được tổ chức quanh outbox.

**Retry an toàn:** không tạo UUID mới cho cùng một event mỗi lần retry nếu UUID được dùng làm idempotency key. Nếu client timeout sau khi remote đã ghi, phải query/reconcile outcome trước khi quyết định gửi lại thao tác có side effect.

## 20. Xử lý lỗi mapping và SQL parameter expressions

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `No value supplied for SQL parameter 'ids'` | Factory không tạo đúng key `ids` | Kiểm tra tên `:ids` và `SqlParameterSource` |
| SpEL không tìm thấy `id` | Root là List nhưng expression viết cho một row, hoặc ngược lại | Kiểm tra `updatePerRow` và kiểu root |
| `ClassCastException` | Đã cấu hình RowMapper DTO nhưng factory ép Map | Đổi factory sang DTO accessor |
| `NullPointerException` trong SpEL | Field SQL NULL hoặc key không có | Validate nullability/alias |
| `DataAccessException` khi UPDATE | Sai SQL dialect/type, DB down, lock conflict | Phân loại transient/permanent |
| Trùng message sau poll | Nhiều instances hoặc ACK/recovery sai | Atomic claim/idempotency |
| Rows luôn bị SELECT lại | UPDATE không match IDs hoặc transaction rollback | Đọc log SQL/bind count, test state |
| SELECT status không thay đổi giữa các poll | Dùng parameter source có cache | Dùng `createParameterSourceNoCache` khi cần |
| UPDATE rất chậm với `IN (:ids)` lớn | Batch quá lớn, locks và parameter limit của DB | Limit rows/chunking/indexes |

**Không nuốt exception rồi coi message là thành công.** Khi một expression lỗi, source có thể thất bại trước khi phát message. Spring JDBC thường dịch `SQLException` thành `DataAccessException`; poller có error handling riêng và có thể chuyển lỗi vào `ErrorMessage`/`errorChannel` tùy cấu hình. Cần test rollback, log/tracing và lối retry thực tế.

### 20.1. Tránh side effect trong SpEL

Biểu thức nên đọc dữ liệu, chuẩn hóa giá trị hoặc chọn cấu hình ổn định; không gọi một HTTP service trong SpEL rồi dựa vào số lần đánh giá để thực hiện nghiệp vụ. Caching và `createParameterSourceNoCache` có thể khiến số lần gọi khác nhau giữa SELECT và UPDATE. Side effects cần nằm ở handler/service có transaction/error contract rõ ràng.

## 21. Bảo mật và hiệu năng

**SQL injection:** `:ids`, `:rowId` và các named params được Spring JDBC bind dưới dạng giá trị. Chúng **không thay thế** việc kiểm soát tên bảng, tên cột, tên procedure hoặc toàn bộ SQL fragment. Không lấy SQL string từ request header hoặc từ dữ liệu database không đáng tin.

**SpEL security:** biểu thức ở `setParameterExpressions(...)` phải là **cấu hình do ứng dụng kiểm soát**, không nhận tùy ý từ Kafka/HTTP payload. SpEL có khả năng gọi methods hoặc tham chiếu Spring beans; nếu cho phép người ngoài cung cấp expression, có thể tạo bề mặt thực thi ngoài mong muốn.

**Tải JDBC:** `JdbcTemplate` và JDBC driver là **blocking I/O**. Kiểm soát pool size, poll interval, SQL query time, connection acquire timeout, số rows, update batch size và transaction duration. Không đặt JDBC trong Reactor Netty event loop rồi giả định việc dùng Spring Integration làm nó non-blocking.

Các metrics hữu ích:

- Số polls, rows SELECT/poll, rows UPDATE/poll, số lần UPDATE không khớp.
- Thời gian SELECT và UPDATE, thời gian chờ connection, query timeout/deadlock.
- Kích thước danh sách IDs, số parameters trong câu `IN`, batch duration.
- Poller error, retry rate, rollback count, queue depth và consumer lag.
- Tuổi những rows `CLAIMED`, lease expired, outbox lag và duplicate events.

Không đưa `eventKey`, user ID hay payload nhạy cảm vào metric tags cardinality cao; dùng trace/correlation IDs trong logs có lọc thông tin.

## 22. Unit test cho custom SqlParameterSourceFactory

Tách factory khỏi IntegrationFlow giúp kiểm tra mapping **không cần database**:

~~~java
package com.example.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.integration.jdbc.SqlParameterSourceFactory;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

class UpdateParameterFactoryTest {

    private record Item(long id) { }

    @Test
    void mapsSelectedRowsToIds() {
        SqlParameterSourceFactory factory = input -> {
            var ids = ((List<?>) input).stream()
                .map(Item.class::cast)
                .map(Item::id)
                .toList();
            return new MapSqlParameterSource("ids", ids);
        };

        var source = factory.createParameterSource(
            List.of(new Item(101), new Item(102)));

        assertEquals(List.of(101L, 102L), source.getValue("ids"));
    }
}
~~~

Test xác nhận factory **lấy đúng danh sách ID** và tên SQL parameter. Nó **không** chứng minh UPDATE được DB thực thi/commit, SpEL bean resolver hoạt động, hay error channel xử lý đúng; cần integration test sau đó.

### 22.1. Test expression factory

Khi dùng `ExpressionEvaluatingSqlParameterSourceFactory`, hãy kiểm tra các trường hợp:

1. `updatePerRow(true)`: root là Map có `id`, expression `#root['id']` lấy đúng giá trị.
2. `updatePerRow(false)`: root là List; projection `#root.![#this['id']]` cho list IDs.
3. Root sai shape: fail rõ, không silently dùng ID rỗng.
4. NULL/key thiếu: có lỗi validation hoặc fallback được định nghĩa tường minh.
5. Cùng parameter dùng nhiều lần: UPDATE source cache giá trị đúng hợp đồng.
6. SELECT dynamic: giá trị `wantedState` được đánh giá lại giữa hai poll khi dùng `createParameterSourceNoCache`.

Để test expressions tham chiếu `@beanName`, nên khởi tạo factory trong một Spring test context, vì bean resolver/lifecycle của Spring Integration cần hoạt động.

## 23. Integration test với H2: SELECT, UPDATE, rollback

Với schema/dữ liệu mục 5, một test end-to-end nên chứng minh cả **payload shape** lẫn **DB state**:

~~~text
Setup:
  sync_event 101,102,103 = NEW
  sync_event 104 = CLAIMED

Poll one time with maxRows(2), updatePerRow(false):
  SELECT returns 101,102
  UPDATE uses ids [101,102]
  DB 101,102 -> CLAIMED
  Output Message<List<EventRow>> has exactly 2 elements
  After splitter: 2 × Message<EventRow>

Next poll:
  103 is selected and claimed
  104 remains untouched

When downstream DirectChannel handler throws before commit:
  Poller TX rolls back SELECT/UPDATE work
  Rows eligible again according to original DB state
~~~

### 23.1. Ma trận kiểm thử

| Tình huống | Kỳ vọng |
|---|---|
| SELECT 2 rows, batch UPDATE | Factory nhận List; UPDATE đúng 2 IDs |
| SELECT 2 rows, per-row UPDATE | Factory nhận từng row; 2 update calls |
| SELECT 0 rows | Không cập nhật sai, không phát business event rỗng |
| Dùng RowMapper DTO | Factory không ép nhầm Map |
| SQL parameter name không khớp | Lỗi rõ thay vì ghi dữ liệu sai |
| SQL status/attempt type không khớp | Exception được quan sát, rollback phù hợp |
| SELECT dynamic parameter | Dùng no-cache và thấy config mới ở poll sau |
| UPDATE ảnh hưởng 0 rows vì race | Không mặc định publish như đã claim thành công |
| DirectChannel handler ném exception | DB transaction rollback khi cùng TX |
| ExecutorChannel async handler ném lỗi | Không mặc định rollback poller TX |
| Hai replicas poll song song | Phát hiện nguy cơ duplicate, cần atomic claim |
| Crash sau DB claim trước broker publish | Lease/outbox/recovery ngăn mất việc |

Không chạy test này chỉ bằng việc thấy `send() == true`; cần kiểm tra **database sau commit**, output messages và behavior khi exception xảy ra. Với các lỗi lock/deadlock/concurrency, dùng DB test đúng vendor hoặc Testcontainers, vì H2 không tái tạo đầy đủ.

## 24. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`:id` trong SQL là SpEL” | Nó là named parameter; giá trị do parameter source cung cấp |
| “Cần factory custom cho mọi UPDATE” | Quy ước cột `id` → `:id` thường đã đủ |
| “`updateSqlParameterSourceFactory` nhận một Message đầu vào” | JDBC inbound nhận **result của SELECT**; không có request message như outbound |
| “`updatePerRow(true)` nghĩa một message cho mỗi row” | Nó thay phạm vi UPDATE; **splitter** mới tách messages |
| “`updatePerRow(false)` gốc SpEL là một row” | Mặc định gốc là **List rows** |
| “Tham số SELECT lấy từ list rows vừa đọc” | SELECT xảy ra **trước** khi có rows |
| “`createParameterSource` và `createParameterSourceNoCache` giống nhau” | Khác về cache expression values |
| “`maxMessagesPerPoll(1)` là một row” | Là một lần gọi source trong nhịp poll |
| “`maxRows(0)` là không lấy row” | Nó không đặt giới hạn rows ở adapter |
| “RowMapper DTO không làm thay đổi factory” | Root object có thể đổi từ Map thành DTO |
| “UPDATE state='CLAIMED' tự bảo đảm không publish trùng” | Hai instances vẫn có thể giữ cùng row đã SELECT |
| “DB rollback tự thu hồi Kafka event” | JDBC transaction không bao trùm broker theo mặc định |
| “SpEL do client gửi an toàn vì là SQL parameter” | Expression evaluation là bề mặt riêng, phải dùng cấu hình tin cậy |
| “JDBC adapter trong WebFlux là non-blocking” | JDBC vẫn là blocking I/O |

## 25. Bài thực hành

1. Dựng bảng `sync_event` theo mục 5, dùng JDBC inbound adapter SELECT các rows `NEW`, ghi nhận payload trước splitter.
2. Cấu hình UPDATE mặc định `WHERE id IN (:id)` không custom factory; kiểm tra đúng rows được đánh dấu.
3. Đổi `:id` thành `:selectedIds`, tự viết lambda `SqlParameterSourceFactory` và kiểm tra list IDs.
4. Viết `EventRowMapper`, đổi payload từ Map sang Java record; sửa factory tương ứng.
5. Bật `updatePerRow(true)` và dùng expression `#root['id']` với row Map; so sánh số SQL UPDATE calls với batch mode.
6. Dùng `ExpressionEvaluatingSqlParameterSourceFactory` cùng list projection `#root.![#this['id']]` cho mode batch.
7. Cố tình chuyển mode batch sang per-row nhưng giữ biểu thức list; quan sát lỗi và giải thích kiểu root.
8. Định nghĩa `setSqlParameterTypes` cho `BIGINT`/`VARCHAR`, kiểm tra JDBC parameter binding.
9. Thêm `setStaticParameters` rồi dùng cùng key với `setParameterExpressions` để kiểm tra quy tắc ưu tiên.
10. Cấu hình SELECT `WHERE state = :wantedState` với `MapSqlParameterSource` giá trị cố định.
11. Thay SELECT state bằng bean dynamic, dùng `createParameterSourceNoCache` và thay giá trị giữa hai polls.
12. Bọc poller trong transaction, cho downstream `DirectChannel` ném exception; xác minh rollback.
13. Chuyển downstream sang `ExecutorChannel`, kiểm tra tại sao transaction của poller không tự lan sang worker.
14. Chạy hai pollers hoặc hai instances cạnh tranh cùng rows; chứng minh predicate UPDATE vẫn có thể tạo duplicate publish.
15. Triển khai atomic claim/lease trên DB vendor thật và so sánh với SELECT-then-UPDATE.
16. Tạo outbox/processed_event key ổn định để xử lý crash sau claim và trước publish.
17. Cấu hình XML 6.x với `sql-parameter-source-factory`, `update-per-row` và poller transaction; so sánh Java DSL 7.x.
18. Dùng H2 test SQL mapping, sau đó chạy Testcontainers DB production-compatible để kiểm chứng locking và rollback.

**Tình huống tổng hợp:** hai pods cùng poll bảng có 100 events `NEW`. Một pod SELECT được 25 rows nhưng crash sau UPDATE; pod kia nhận một phần IDs trùng và đã gửi Kafka. Hãy xác định gốc của `SqlParameterSourceFactory` ở mỗi chế độ, SQL claim phù hợp, transaction/lease, rule ACK, danh sách event IDs ổn định, outbox và các tests cần có để hạn chế mất hoặc nhân đôi tác dụng.

## 26. Tài liệu tham khảo

- [Spring Integration Reference — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): tham số `:id` mặc định, `SqlParameterSourceFactory`, SpEL root, `createParameterSourceNoCache`, poller và transaction.
- [Spring Integration Reference — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): Java DSL JDBC được giới thiệu từ Spring Integration 7.0.
- [Spring Integration API — JdbcInboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcInboundChannelAdapterSpec.html): `updateSqlParameterSourceFactory`, `updatePerRow`, `selectSqlParameterSource` và `maxRows`.
- [Spring Integration API — JdbcPollingChannelAdapter 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): Java setters, hành vi SELECT/UPDATE và update-per-row mặc định.
- [Spring Integration API — SqlParameterSourceFactory](https://docs.spring.io/spring-integration/docs/latest-ga/api/org/springframework/integration/jdbc/SqlParameterSourceFactory.html): hợp đồng factory và `createParameterSource(Object)`.
- [Spring Integration API — ExpressionEvaluatingSqlParameterSourceFactory](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/ExpressionEvaluatingSqlParameterSourceFactory.html): `setParameterExpressions`, `setStaticParameters`, `setSqlParameterTypes` và cache behavior.
- [Spring Integration Reference — JDBC Outbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/outbound-channel-adapter.html): so sánh root là message ở outbound, named parameters và SpEL.
- [Spring Framework Reference — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `NamedParameterJdbcTemplate`, `SqlParameterSource`, `MapSqlParameterSource` và JDBC operations.
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): transactional poller và synchronous message flow.

> **Ghi nhớ:** `updateSqlParameterSourceFactory` biến **kết quả SELECT** thành tham số của UPDATE; `updatePerRow(false)` làm việc trên **cả danh sách**, còn `updatePerRow(true)` trên **từng row**. `ExpressionEvaluatingSqlParameterSourceFactory` dùng **SpEL cấu hình riêng** để tính giá trị, trong khi `:id`/`:ids` trong SQL vẫn là named parameters. Tham số của SELECT thuộc `selectSqlParameterSource` và có quy tắc cache khác. Muốn đáng tin cậy cần kiểm soát transaction, duplicate poll, atomic claim, recovery và idempotency; factory chỉ giải quyết **mapping tham số**, không tự bảo đảm delivery.
