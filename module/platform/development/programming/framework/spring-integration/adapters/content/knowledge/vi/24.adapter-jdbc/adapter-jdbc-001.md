# JDBC inbound channel adapter chạy SELECT trong Spring Integration

## 1. Mục tiêu: biến dữ liệu trong database thành message

Nhiều hệ thống tích hợp không chủ động phát sự kiện khi dữ liệu thay đổi. Ví dụ, một ứng dụng cũ chỉ ghi đơn hàng vào bảng `integration_inbox`. Hệ thống mới cần định kỳ tìm các đơn hàng chưa xử lý, chuyển chúng thành message, sau đó định tuyến tới service, HTTP gateway, JMS/AMQP hoặc Kafka. Khi nguồn là **database quan hệ qua JDBC**, **JDBC inbound channel adapter** là một cách thực hiện phù hợp.

Đây là nội dung chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**: kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; kiểm soát hợp đồng message, lỗi và vòng đời kết nối khi trao đổi qua file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu.

**Nhiệm vụ chính của JDBC inbound channel adapter:**

1. Đến mỗi lượt poll, chạy một câu SQL `SELECT` trên `DataSource`/`JdbcOperations`.
2. Chuyển toàn bộ tập kết quả thành **một message có payload là `List<?>`**.
3. Có thể chạy thêm câu `UPDATE` để đánh dấu những dòng đã được lấy, tránh chọn lại ở những lượt poll sau.
4. Gửi message qua `MessageChannel` để downstream xử lý. Nếu cần một message **cho mỗi dòng**, thêm `splitter`.

~~~mermaid
flowchart LR
    DB[("Database: integration_inbox")] -->|"SELECT khi poll"| A["JdbcPollingChannelAdapter"]
    A -->|"Message<List<Row>>"| CH["MessageChannel"]
    CH --> SPL["Splitter"]
    SPL -->|"Message<Row> theo từng dòng"| H["Business Handler"]
    H --> OUT["HTTP / JMS / Kafka / Service"]
    A -.->|"UPDATE đánh dấu đã chọn"| DB
~~~

**Điểm phải nhớ:** adapter chạy `SELECT` theo lịch **polling**, không phải lắng nghe database change stream/CDC theo thời gian thực. Nếu dữ liệu phải cập nhật gần như tức thời với độ trễ rất thấp hoặc quy mô lớn, cần cân nhắc CDC, outbox kết hợp broker hoặc cơ chế phát event ngay tại nguồn.

## 2. Phân biệt JDBC inbound adapter với các thành phần liên quan

| Thành phần | Bắt đầu từ đâu? | Hợp đồng | Trường hợp sử dụng |
|---|---|---|---|
| **JDBC inbound channel adapter** | Database `SELECT` theo poller | DB → message, một chiều | Lấy hàng chờ trong bảng, nhập dữ liệu định kỳ |
| JDBC outbound channel adapter | Message đang có trong flow | Message → SQL ghi/cập nhật, một chiều | `INSERT`/`UPDATE` sau khi xử lý event |
| JDBC outbound gateway | Message trong flow | SQL request → kết quả query/update → reply message | Cần kết quả JDBC để bước sau xử lý |
| JDBC stored procedure adapter/gateway | Stored procedure/function | Theo endpoint inbound/outbound và request-reply | Hệ thống hiện hữu cung cấp logic qua procedure |
| `JdbcTemplate` dùng trực tiếp | Lời gọi Java từ service | Kết quả Java thông thường | Không cần poller, channel hay IntegrationFlow |
| CDC / transactional outbox | Transaction log hoặc bảng outbox | Event theo change/queue semantics | Cần mở rộng quy mô, giảm polling hoặc delivery đáng tin hơn |

JDBC inbound adapter **không phải** HTTP inbound endpoint. Nó chạy theo lịch do poller điều khiển; không có HTTP request để trả response. Tương tự, `JdbcPollingChannelAdapter` sử dụng **JDBC đồng bộ**. Đưa nó vào một IntegrationFlow có tên “reactive” cũng không biến JDBC thành non-blocking I/O.

## 3. Hợp đồng message: SELECT trả một List, không phải từng row

Giả sử database có ba dòng chưa xử lý:

| id | order_id | amount | state |
|---:|---|---:|---|
| 101 | ORD-101 | 250000 | NEW |
| 102 | ORD-102 | 120000 | NEW |
| 103 | ORD-103 | 560000 | NEW |

SELECT:

~~~sql
SELECT id, order_id, amount
FROM integration_inbox
WHERE state = 'NEW'
ORDER BY id
LIMIT 20;
~~~

Với `RowMapper` mặc định, message trả về có cấu trúc logic:

~~~text
Message<List<Map<String, Object>>>
  payload:
    - {id: 101, order_id: "ORD-101", amount: 250000}
    - {id: 102, order_id: "ORD-102", amount: 120000}
    - {id: 103, order_id: "ORD-103", amount: 560000}
  headers:
    id: <message UUID>
    timestamp: <creation time>
~~~

Thực tế kiểu số, tên key (chữ hoa/thường) và cách biểu diễn cột phụ thuộc JDBC driver, SQL aliases và `RowMapper`; ví dụ chỉ minh họa dữ liệu.

Sau `splitter`, có thể tạo ba message:

~~~text
Message<Map<String, Object>> (id=101)
Message<Map<String, Object>> (id=102)
Message<Map<String, Object>> (id=103)
~~~

Không được nhầm **`maxRows(20)`** với “tối đa 20 messages một lần poll”. Adapter thường trả **một message chứa tối đa 20 rows**, sau đó splitter mới tách thành nhiều message ở downstream.

## 4. Thiết lập dự án và database mẫu

### 4.1. Dependencies

Sử dụng Spring Boot BOM để quản lý phiên bản Spring Integration, Spring JDBC và JDBC driver tương thích.

~~~groovy
// build.gradle — phần dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    // Chỉ dùng H2 in-memory để học/thử nghiệm.
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-integration-jdbc` cung cấp `JdbcPollingChannelAdapter` và các JDBC endpoint. `spring-boot-starter-jdbc` cung cấp `DataSource`, Spring JDBC, transaction manager và thường sử dụng HikariCP. Trong production, dùng driver phù hợp PostgreSQL, MySQL, SQL Server hoặc Oracle, cùng cấu hình pool và credentials an toàn.

### 4.2. Cấu hình DataSource cho H2

~~~yaml
# application.yml — minh họa ứng dụng Spring Boot local
spring:
  datasource:
    url: jdbc:h2:mem:jdbc-adapter-demo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

Với cấu hình SQL initialization của Spring Boot, có thể đặt DDL/DML sau vào `src/main/resources/schema.sql`; đây là **tệp ví dụ để người học tự tạo**, không phải một tệp được tạo trong quá trình viết tài liệu:

~~~sql
CREATE TABLE integration_inbox (
    id BIGINT PRIMARY KEY,
    order_id VARCHAR(80) NOT NULL,
    amount DECIMAL(14, 2) NOT NULL,
    state VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_inbox_state_id
    ON integration_inbox(state, id);

INSERT INTO integration_inbox(id, order_id, amount, state)
VALUES
    (101, 'ORD-101', 250000.00, 'NEW'),
    (102, 'ORD-102', 120000.00, 'NEW'),
    (103, 'ORD-103', 560000.00, 'NEW');
~~~

Trong thực tế, dùng Flyway/Liquibase để quản lý migration thay vì phụ thuộc `schema.sql` của ứng dụng. Với database lớn, cân nhắc index theo cột filter/sort và đo query plan; không thêm index tùy tiện trên các bảng có tần suất ghi cao.

## 5. Bắt đầu từ SELECT thuần: đọc lặp để quan sát dữ liệu

Đây là ví dụ tối thiểu để thấy cách adapter trở thành **MessageSource**. Câu SELECT không có UPDATE, vì thế các dòng `NEW` sẽ được đọc lại ở lần poll sau.

~~~java
package com.example.jdbc;

import java.time.Duration;
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.messaging.Message;

@Configuration
@EnableIntegration
public class ReadOnlyJdbcPollingConfiguration {

    @Bean
    public IntegrationFlow observeInbox(DataSource dataSource) {
        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource, """
                SELECT id, order_id, amount
                FROM integration_inbox
                WHERE state = 'NEW'
                ORDER BY id
                LIMIT 20
                """);

        return IntegrationFlow
            .from(source, endpoint -> endpoint.poller(
                Pollers.fixedDelay(Duration.ofSeconds(5))
                    .maxMessagesPerPoll(1)))
            .handle((Message<?> message) -> {
                System.out.println("Rows from database: "
                    + message.getPayload());
            })
            .get();
    }
}
~~~

Với ba dòng `NEW`, mỗi lượt poll đều có thể tạo một message chứa danh sách ba dòng. **Đây là demo đọc lặp**, không phải pipeline dùng để xử lý đơn hàng một lần. Nếu cùng ứng dụng chạy cả ví dụ này và flow có `UPDATE` ở mục sau, sẽ có **hai pollers cạnh tranh**; chỉ bật **một** trong hai khi thực hành.

Với câu SELECT không có dòng phù hợp, adapter thường không tạo message để downstream xử lý. Không dựa vào “payload list rỗng” như một sự kiện nghiệp vụ cần nhận ở mọi lần poll; muốn heartbeat/metric thời gian trống, nên có giám sát poller riêng.

## 6. SELECT + UPDATE: đánh dấu các dòng đã được chọn

Đối với dữ liệu hàng đợi, một câu `SELECT` thuần khiến row được lấy lặp đi lặp lại. JDBC inbound adapter hỗ trợ `updateSql` để cập nhật trạng thái ngay sau khi SELECT, trước khi message được đẩy vào flow.

~~~sql
-- Bước 1: lấy các row NEW
SELECT id, order_id, amount
FROM integration_inbox
WHERE state = 'NEW'
ORDER BY id
LIMIT 20;

-- Bước 2: đánh dấu những id trong kết quả vừa chọn
UPDATE integration_inbox
SET state = 'CLAIMED'
WHERE id IN (:id)
  AND state = 'NEW';
~~~

Đoạn `:id` **không phải cú pháp JDBC `?` thông thường**, mà là **named parameter** do Spring JDBC và Spring Integration xử lý. Adapter có quy ước lấy cột `id` từ các dòng SELECT, tạo một tập/list các ID để bind vào `:id` trong UPDATE. Vì vậy:

- SELECT **phải trả cột `id`** (hoặc cấu hình parameter source tương ứng).
- Câu UPDATE chỉ áp dụng cho các ID từ **lượt SELECT hiện tại**, không cập nhật tất cả dòng `NEW` trong bảng.
- Nếu không có kết quả, không nên tạo `IN ()` bằng logic SQL thủ công; adapter xử lý trường hợp không có dữ liệu theo vòng đời poll.
- UPDATE trạng thái `CLAIMED` không có nghĩa nghiệp vụ đã hoàn tất; nó chỉ đánh dấu giai đoạn lấy dữ liệu. Cần thiết kế `DONE`/`FAILED` và recovery ở phần vận hành.

### 6.1. Java configuration với JdbcPollingChannelAdapter

Ví dụ dưới đây sử dụng API Java phổ biến của `JdbcPollingChannelAdapter`, không phụ thuộc vào factory `Jdbc.inboundAdapter(...)` mới có từ Spring Integration 7.0.

~~~java
package com.example.jdbc;

import java.time.Duration;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.messaging.Message;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class JdbcInboxIntegrationConfiguration {

    @Bean
    public IntegrationFlow pollNewOrders(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource, """
                SELECT id, order_id, amount
                FROM integration_inbox
                WHERE state = 'NEW'
                ORDER BY id
                LIMIT 20
                """);

        source.setUpdateSql("""
            UPDATE integration_inbox
            SET state = 'CLAIMED'
            WHERE id IN (:id)
              AND state = 'NEW'
            """);

        source.setMaxRows(20);

        return IntegrationFlow
            .from(source, endpoint -> endpoint.poller(
                Pollers.fixedDelay(Duration.ofSeconds(2))
                    .maxMessagesPerPoll(1)
                    .transactional(transactionManager)))
            .split() // List<Map<String,Object>> -> từng Message<Map<...>>
            .handle((Message<?> message) -> {
                @SuppressWarnings("unchecked")
                Map<String, Object> row =
                    (Map<String, Object>) message.getPayload();

                // Demo: xử lý đồng bộ, không gọi API bên ngoài.
                System.out.printf(
                    "Picked id=%s, order=%s, amount=%s%n",
                    row.get("id"),
                    row.get("order_id"),
                    row.get("amount"));
            })
            .get();
    }
}
~~~

Ví dụ giả định Spring Boot đã cấu hình một `PlatformTransactionManager` quản lý **cùng DataSource** (thường được Boot auto-configure khi chỉ có một JDBC DataSource). Nếu nhiều transaction managers, hãy chọn đúng manager bằng `@Qualifier`; không mặc định một manager của JMS/Kafka có thể điều khiển transaction JDBC.

Diễn giải theo trình tự:

1. Poller kích hoạt adapter khoảng mỗi 2 giây theo `fixedDelay`.
2. Adapter thực thi SELECT với tối đa 20 row.
3. Adapter thực thi UPDATE, đánh dấu các ID đã chọn thành `CLAIMED`, trong **cùng transaction** khi poller có advice transaction phù hợp.
4. Adapter gửi **một message chứa `List<Map<String,Object>>`**.
5. `split()` tách list thành một message cho mỗi map.
6. Handler in ra dữ liệu, chạy đồng bộ trong flow minh họa.
7. Nếu không có lỗi, transaction được commit; sau đó SELECT ở lượt tiếp theo sẽ không thấy các row đã chuyển khỏi `NEW`.

**Đừng kết luận các dòng đã “xử lý nghiệp vụ xong” chỉ vì được in ra màn hình.** Trong production, một bước cập nhật `DONE`, audit hoặc phát event cần ranh giới commit/ACK rõ ràng. Ví dụ cố ý chỉ thể hiện nguyên lý SELECT → UPDATE → MessageChannel.

## 7. Poller: lịch chạy và hai giới hạn rất dễ nhầm

JDBC inbound adapter là một **polling message source**. Trong Java DSL, `Pollers.fixedDelay(...)` và `Pollers.fixedRate(...)` xác định thời điểm gọi `receive()`.

| Cấu hình | Điều bị giới hạn | Ví dụ |
|---|---|---|
| `fixedDelay(2s)` | Khoảng nghỉ giữa các lần kích hoạt theo scheduler | Có lượt poll khoảng 2 giây sau lượt trước theo lịch |
| `fixedRate(2s)` | Nhịp kích hoạt cố định theo thời gian scheduler | Nếu tác vụ chậm, cần kiểm soát executor và overlap |
| `maxMessagesPerPoll(1)` | Số lần gọi `receive()` mỗi chu kỳ | Thường là **một lần SELECT** trên mỗi lượt poll |
| `setMaxRows(20)` | Số row dùng từ result set của **một SELECT** | Payload có thể là list tối đa 20 phần tử |
| `LIMIT 20` / `TOP 20` | Giới hạn ngay ở SQL/database | DB không cần trả quá nhiều row trước khi client cắt |
| Transactional poller | Transaction bao phủ poll và phần xử lý sync liên quan | Cho SELECT/UPDATE và bước sync có thể rollback cùng nhau |

**`maxMessagesPerPoll` khác `maxRows`**: tăng `maxMessagesPerPoll` từ 1 lên 5 có thể khiến adapter thực thi SELECT nhiều lần liên tiếp trong cùng chu kỳ, không chỉ tăng kích thước batch. Với JDBC inbound channel adapter, thường giữ giá trị mặc định tương đương 1, rồi điều chỉnh SQL `LIMIT`/`TOP` theo batch mong muốn.

Spring Integration khuyến nghị **giới hạn ngay trong SQL** theo cú pháp database, vì `setMaxRows` là giới hạn phía JDBC/adapter và có thể không giúp database tối ưu việc scan/sort nhiều row. Ví dụ:

~~~sql
-- PostgreSQL / H2 / MySQL (cần đối chiếu phiên bản):
SELECT id, order_id, amount
FROM integration_inbox
WHERE state = 'NEW'
ORDER BY id
LIMIT 20;

-- SQL Server:
SELECT TOP (20) id, order_id, amount
FROM integration_inbox
WHERE state = 'NEW'
ORDER BY id;
~~~

Không copy cú pháp `LIMIT` sang SQL Server/Oracle mà không điều chỉnh. Nếu không có `ORDER BY` ổn định, các lượt poll có thể lấy tập row khác nhau khó dự đoán. `ORDER BY id` chỉ bảo đảm thứ tự *trong kết quả truy vấn*, không tự giải quyết tranh chấp giữa nhiều pollers.

## 8. RowMapper: từ Map mặc định sang DTO có kiểu

Mặc định, JDBC inbound adapter dùng cách map mỗi row thành `Map`, phù hợp khi schema linh hoạt. Khi nghiệp vụ cần type-safe payload, cấu hình Spring JDBC `RowMapper<T>`.

~~~java
package com.example.jdbc;

import java.math.BigDecimal;

public record InboxOrder(
    long id,
    String orderId,
    BigDecimal amount) { }
~~~

~~~java
import org.springframework.jdbc.core.RowMapper;

RowMapper<InboxOrder> inboxOrderMapper = (rs, rowNum) ->
    new InboxOrder(
        rs.getLong("id"),
        rs.getString("order_id"),
        rs.getBigDecimal("amount"));

JdbcPollingChannelAdapter adapter =
    new JdbcPollingChannelAdapter(dataSource, """
        SELECT id, order_id, amount
        FROM integration_inbox
        WHERE state = 'NEW'
        ORDER BY id
        LIMIT 20
        """);

adapter.setRowMapper(inboxOrderMapper);
~~~

**Lưu ý quan trọng khi kết hợp custom RowMapper và UPDATE:** `updateSql("... WHERE id IN (:id)")` cần truy xuất được thuộc tính `id` từ các row mà mapper tạo ra. Với class JavaBean có `getId()` hoặc một kiểu mà SpEL hỗ trợ rõ, việc lấy thuộc tính có thể trực tiếp. Với Java record hoặc DTO tùy biến, cần **kiểm chứng cách property accessor của Spring Integration/SpEL trong phiên bản đang dùng**; khi cần thì cấu hình `SqlParameterSourceFactory` rõ ràng, hoặc dùng `Map` như ví dụ đầy đủ để tránh nhầm lẫn. Không sử dụng custom RowMapper rồi giả định update parameter tự hoạt động trong mọi trường hợp.

Về kiểu dữ liệu, cột tiền nên map sang `BigDecimal`, không ép thành `double` vì sai số dấu phẩy động. Cột thời gian cần quy định timezone/`Instant`/`LocalDateTime` tương ứng với JDBC driver và schema.

## 9. UPDATE theo danh sách ID và updatePerRow

Spring Integration có hai cách áp dụng cập nhật sau SELECT:

- **Cập nhật theo cả tập**: ví dụ `WHERE id IN (:id)`, với `:id` là list các ID từ batch vừa SELECT.
- **Cập nhật từng row**: bật `setUpdatePerRow(true)`, khi đó update parameter factory làm việc trên **một row** mỗi lần và SQL phải phù hợp với tham số đơn.

Ví dụ minh họa tùy chọn update từng row:

~~~java
JdbcPollingChannelAdapter adapter =
    new JdbcPollingChannelAdapter(dataSource,
        "SELECT id, order_id FROM integration_inbox WHERE state = 'NEW'");

adapter.setUpdatePerRow(true);
adapter.setUpdateSql(
    "UPDATE integration_inbox SET state='CLAIMED' WHERE id=:id");
~~~

Với row mapper mặc định là `Map` chứa `id`, cách lấy tham số mặc định có thể truy xuất từ từng row. Ưu điểm là dễ biểu đạt điều kiện UPDATE riêng; nhược điểm là có thể có nhiều lần thực thi SQL UPDATE cho một batch. Đo số round trips và kiểm tra transaction cho database thật.

Khi tên cột khác tên tham số hoặc logic ánh xạ phức tạp, cấu hình `setUpdateSqlParameterSourceFactory(...)` để kiểm soát cách tạo parameter source. Không nối giá trị `id` hoặc trạng thái từ input không đáng tin vào SQL string; dùng named parameters/bind values giúp giảm lỗi và nguy cơ SQL injection.

## 10. SELECT có tham số: tránh hardcode trạng thái

Đối với SELECT có named parameters, adapter hỗ trợ `setSelectSqlParameterSource(SqlParameterSource)`:

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;

JdbcPollingChannelAdapter adapter =
    new JdbcPollingChannelAdapter(dataSource, """
        SELECT id, order_id, amount
        FROM integration_inbox
        WHERE state = :state
        ORDER BY id
        LIMIT 20
        """);

adapter.setSelectSqlParameterSource(
    new MapSqlParameterSource("state", "NEW"));
~~~

Ở đây `:state` được bind như giá trị SQL, không phải ghép chuỗi. Parameter source dùng khi poll không có request message từ caller, nên nếu cần trạng thái/điều kiện động dựa trên runtime, phải thiết kế nguồn tham số được cập nhật đúng cách. Với `ExpressionEvaluatingSqlParameterSourceFactory`, Spring Integration có hướng dẫn `createParameterSourceNoCache` để tránh caching kết quả biểu thức khi giá trị cần thay đổi giữa các lượt poll.

**Không dùng SQL parameter để thay tên bảng/cột**. Những vị trí schema identifier thường không thể bind theo cách bind SQL values; nếu cần chọn bảng động, chỉ chọn từ danh sách định nghĩa sẵn, không lấy trực tiếp từ người dùng.

## 11. Transaction: SELECT, UPDATE và downstream đồng bộ

Trường hợp SELECT + UPDATE cần tính nhất quán: khi lấy một batch và đánh dấu nó, hai câu SQL nên cùng một transaction. Spring Integration cho phép bọc poller bằng transaction advice; ví dụ mục 6 dùng:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(2))
    .maxMessagesPerPoll(1)
    .transactional(transactionManager)
~~~

Với `DataSource` và transaction manager tương thích, một poller transaction có thể bao gồm SELECT, UPDATE và các handler downstream chạy **trên cùng thread, trong cùng transaction**. Khi handler đồng bộ ném exception ra ngoài và transaction đánh dấu rollback, cập nhật `CLAIMED` có thể được rollback, làm row xuất hiện lại là `NEW` ở lượt poll tiếp theo.

~~~mermaid
sequenceDiagram
    participant Poller as Poller (transaction)
    participant DB as JDBC Database
    participant Flow as Direct flow
    Poller->>DB: BEGIN
    Poller->>DB: SELECT rows NEW
    DB-->>Poller: ids = [101, 102]
    Poller->>DB: UPDATE state=CLAIMED WHERE id IN (...)
    Poller->>Flow: Message<List<Row>>
    alt Handler đồng bộ thành công
        Flow-->>Poller: Hoàn tất
        Poller->>DB: COMMIT
    else Handler đồng bộ lỗi
        Flow--xPoller: Exception
        Poller->>DB: ROLLBACK
    end
~~~

**Ranh giới transaction không tự kéo dài qua mọi channel**:

- `DirectChannel`/handler đồng bộ trên cùng thread có thể tham gia transaction JDBC đang mở.
- `ExecutorChannel`, `QueueChannel`, broker và publisher reactive có thể tách thread/process/thời điểm thực thi; transaction poller **không** bao trùm mọi side effect xảy ra bất đồng bộ sau đó.
- Gửi HTTP request, JMS hoặc Kafka **không tự nằm chung trong một transaction database**. Nếu đã gửi ra ngoài rồi JDBC rollback, đối tác vẫn có thể đã nhận event.
- Nếu cần bảo đảm delivery qua crash, cần **outbox**, idempotent consumer, trạng thái xử lý và reconciliation; không coi `@Transactional` là distributed transaction.

Trong ví dụ mục 6, handler chỉ in log: một log đã in ra không thể rollback nếu transaction sau đó thất bại. Đây là giới hạn của side effect bên ngoài transaction ngay cả với flow đồng bộ.

## 12. Nhiều instance cùng poll: tranh chấp và xử lý trùng

Nếu ứng dụng có hai replicas và mỗi replica chạy SELECT `WHERE state='NEW'`, **cả hai có thể cùng đọc một row** trước khi một UPDATE commit. Chỉ đặt `UPDATE ... WHERE state='NEW'` **không tự bảo đảm** mỗi row được xử lý đúng một lần; cần xét số row được update, isolation, locks và sự cạnh tranh.

Một số phương án:

1. **Chỉ một poller active:** dùng leader election, scheduler coordination hoặc phân vùng bảng. Dễ hiểu nhưng phải xử lý failover.
2. **Pessimistic row locking:** dùng câu SELECT lock row và `SKIP LOCKED` nếu database hỗ trợ; giữ transaction trong lúc claim.
3. **Atomic claim:** dùng SQL cập nhật có điều kiện, `UPDATE ... RETURNING` hoặc cấu trúc claim transaction riêng theo khả năng database. Chỉ phát những row đã claim thành công.
4. **Lease/timeout:** đánh dấu `CLAIMED` với `claimed_at` và `owner_id`; có cơ chế phục hồi claim bị kẹt sau crash.
5. **Idempotent downstream:** nhận trùng `orderId`/`eventId` vẫn không tạo side effect trùng.

Ví dụ PostgreSQL cho nhiều worker (cú pháp **phụ thuộc database**, không áp dụng nguyên xi cho H2/MySQL/Oracle):

~~~sql
BEGIN;

SELECT id, order_id, amount
FROM integration_inbox
WHERE state = 'NEW'
ORDER BY id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- UPDATE các id vừa lấy trong chính transaction.
-- COMMIT sau khi đã xác định chính sách claim/dispatch.

COMMIT;
~~~

`SKIP LOCKED` giúp tránh tranh chấp khóa row giữa các worker, nhưng transaction dài có thể giữ lock và làm ảnh hưởng các thao tác khác. Nếu SELECT/UPDATE theo batch và downstream chậm, cần cân nhắc **claim nhanh rồi commit**, đưa xử lý ra ngoài transaction và dùng lease/retry/outbox để phục hồi lỗi.

**Không hứa “exactly once”** chỉ bằng JDBC polling. Thực tế thường thiết kế **at-least-once** ở mức event, cùng consumer idempotent và trạng thái có thể đối soát. Nếu cần “mỗi đơn chỉ tính tiền một lần”, ràng buộc đó phải được đảm bảo ở nghiệp vụ và database/bên nhận, không chỉ tại poller.

## 13. Kiến trúc trạng thái: NEW, CLAIMED, DONE và FAILED

Cách chỉ có `NEW` và `CLAIMED` hữu ích để học nhưng chưa đủ cho vận hành dài hạn. Nên xác định state machine:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> CLAIMED: Poll/claim batch
    CLAIMED --> DONE: Business processing success
    CLAIMED --> FAILED: Non-retryable error
    CLAIMED --> NEW: Retry/lease timeout/recovery
    FAILED --> NEW: Manual requeue có kiểm soát
    DONE --> [*]
~~~

Các trường bổ sung thường hữu ích:

| Trường | Mục đích |
|---|---|
| `claimed_at` | Phát hiện claim quá hạn |
| `claim_owner` | Biết worker/process đang sở hữu claim |
| `attempt_count` | Giới hạn retry, quyết định dead-letter |
| `last_error_code` | Phân loại lỗi phục hồi/vĩnh viễn |
| `processed_at` | Audit thời điểm thành công |
| `event_id` duy nhất | Idempotency và đối soát với broker/HTTP |

Nếu xử lý thất bại sau khi đã commit `CLAIMED`, row có nguy cơ **kẹt vĩnh viễn** nếu không có recovery. Có thể định kỳ tìm `CLAIMED` quá lease để đưa về `NEW` hoặc chuyển `FAILED`. Cần phối hợp với idempotency để khi chạy lại không nhân đôi thao tác đã thành công trước crash.

## 14. Hiệu năng: không biến bảng thành điểm nghẽn

Polling SELECT có chi phí ngay cả khi bảng không đổi. Với bảng lớn, câu SELECT cần **WHERE**, index và giới hạn batch phù hợp. Hệ thống ghi nhiều cũng có thể bị ảnh hưởng nếu poller thường xuyên giữ transaction hoặc scan nhiều row.

**Checklist SQL và poller:**

- Dùng index hỗ trợ `WHERE state='NEW'` và `ORDER BY id`; đo `EXPLAIN`/query plan.
- Chỉ SELECT cột thực sự cần thay vì `SELECT *`; giảm I/O và chi phí mapping.
- Dùng `LIMIT/TOP/FETCH FIRST` phù hợp database; chọn batch theo độ trễ và năng lực downstream.
- Đặt poll interval theo mức chấp nhận độ trễ; poll quá dày gây query load khi nguồn rỗng.
- Cấu hình `DataSource` pool, JDBC query timeout và connection lifetime đúng với môi trường.
- Giới hạn concurrency/queue khi splitter đưa dữ liệu sang service hoặc broker.
- Với nhiều row, đo chi phí UPDATE tập hợp `IN (:id)` so với updatePerRow và kích thước tối đa parameter list của driver/database.
- Giữ transaction đủ ngắn, tránh lock kéo dài do handler blocking hoặc remote HTTP.
- Có chiến lược dọn bảng, partition/archive trạng thái `DONE` và index maintenance.

**Không nhầm `maxRows` với backpressure:** adapter JDBC đồng bộ lấy kết quả thành list; `maxRows` giới hạn số row của một lần gọi, chứ không làm JDBC chuyển thành reactive stream theo `request(n)`. Muốn non-blocking DB I/O cần driver/API reactive như R2DBC, nhưng mô hình SQL, transaction và message delivery vẫn phải thiết kế.

## 15. Xử lý lỗi và retry khi poll thất bại

Một poller có thể lỗi trong SELECT, UPDATE, mapping, gửi message, splitter hoặc business handler. Cần phân loại thay vì retry vô hạn.

| Loại lỗi | Ví dụ | Cách ứng xử |
|---|---|---|
| Kết nối database | Database restart, pool hết connection | Backoff, health check, giới hạn retry, quan sát |
| SQL sai | Thiếu cột, sai bảng, query syntax | Lỗi cấu hình; sửa deployment/schema, không retry dồn dập |
| Lock/deadlock | Transaction tranh chấp | Retry **có giới hạn**, xem isolation/index/lock duration |
| Duplicate key | DB unique constraint | Xem idempotency và hợp đồng dữ liệu, tránh nuốt lỗi |
| RowMapper lỗi | Parse cột kiểu sai, NULL không được xử lý | Sửa mapping/schema, có error flow phù hợp |
| Downstream synchronous handler lỗi | Logic ném exception trong transaction | Rollback nếu cùng transaction và exception truyền ra |
| Downstream async/remote lỗi | Kafka/HTTP timeout sau khi DB đã claim | Cần outbox/lease/reconciliation, không tự dựa vào rollback poller |
| Không có rows | SELECT kết quả rỗng | Hoạt động bình thường, không phải lỗi |

Spring Integration có `errorChannel` và `ErrorMessage` cho các endpoint/handler thích hợp, nhưng **không mặc định mọi lỗi từ poller đều được chuyển đúng vào một error flow do mình mong muốn**. Nên cấu hình error handling cho poller, scheduler, transaction advice và channel phù hợp phiên bản, đồng thời test lỗi thật.

Khi error retry xảy ra ở **nhiều lớp** (scheduler, advice, HTTP client, Kafka listener), số lần xử lý một row có thể tăng rất lớn. Quy định rõ nơi sở hữu retry budget, thời gian backoff, trạng thái cuối `FAILED` và cảnh báo vận hành.

## 16. Theo dõi và kiểm thử

### 16.1. Chỉ số nên theo dõi

- Số lần poll, số lần poll rỗng, thời gian SELECT/UPDATE và thời gian transaction.
- Số row mỗi batch, số row chuyển `NEW → CLAIMED`, tổng `NEW/CLAIMED/DONE/FAILED`.
- Độ trễ từ `created_at` tới lúc được poll và đến khi nghiệp vụ hoàn tất.
- Connection pool active/idle/waiting, query timeout, lock wait và deadlock.
- Số row claim quá lease, số retry, số event trùng bị chặn và dead-letter count.
- Độ dài queue/message backlog và tỉ lệ downstream thành công/thất bại.

Không ghi toàn bộ dữ liệu nhạy cảm của mỗi row vào log. Dùng `eventId`/`orderId` có kiểm soát để correlate, với chính sách che/mask phù hợp.

### 16.2. Bài test tối thiểu với H2

Có thể dùng `@SpringBootTest` và `JdbcTemplate` để kiểm tra trạng thái database sau khi flow đã poll. Vì poller chạy theo thời gian, test cần cơ chế chờ có deadline và điều kiện quan sát rõ ràng; tránh chỉ gọi `Thread.sleep(1000)` rồi cho rằng chắc chắn đúng trên mọi máy.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class JdbcInboundSmokeTest {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void queryShowsSeedDataBeforePolling() {
        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM integration_inbox",
            Integer.class);

        assertThat(count).isNotNull();
        assertThat(count).isGreaterThanOrEqualTo(0);
    }
}
~~~

**Giới hạn test:** đây chỉ là smoke test xác minh schema/kết nối; poller tự chạy có thể đã thay đổi `state` trước khi assertion đọc bảng. Để kiểm thử đầy đủ, cần cô lập poller lifecycle trong test (start/stop endpoint), khởi tạo seed data có kiểm soát, bắt message ở `QueueChannel`/test handler, kiểm tra payload là `List`, dùng splitter rồi assert status và rollback khi handler ném lỗi.

Ma trận kiểm thử cần có:

| Tình huống | Kỳ vọng |
|---|---|
| Không có row NEW | Poller không đẩy event nghiệp vụ |
| Có 3 row NEW | SELECT trả một list chứa 3 rows |
| Có 25 row và LIMIT 20 | Chỉ chọn batch tối đa 20 row |
| Splitter bật | Mỗi row trở thành một message downstream |
| UPDATE thành công | Các row đã chọn không còn nằm trong điều kiện SELECT kế tiếp |
| Handler đồng bộ ném lỗi | Poller transaction rollback thay đổi JDBC khi cấu hình đúng |
| Handler async lỗi sau commit | Không có rollback tự động cho transaction đã commit; cần recovery |
| Hai app poll đồng thời | Không tạo side effect trùng nếu có claim protocol/idempotency |
| Row CLAIMED quá lease | Recovery/requeue hoạt động theo policy |
| Database down | Có giám sát, retry/báo lỗi có giới hạn |

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “SELECT trả ba row thì adapter phát ba messages” | Payload của một poll là **List**; splitter mới tách |
| “Không có UPDATE cũng chỉ đọc row một lần” | SELECT thuần có thể lấy cùng dữ liệu ở mỗi poll |
| “`maxMessagesPerPoll(20)` nghĩa là 20 rows” | Nó là số lần `receive()`, không phải số rows mỗi query |
| “`setMaxRows(20)` thay SQL LIMIT và tối ưu query” | Nó giới hạn rows ở JDBC; nên giới hạn ngay trong SQL |
| “`UPDATE ... WHERE state='NEW'` đảm bảo exactly once với hai replicas” | Vẫn có race khi SELECT; cần locking/atomic claim/idempotency |
| “`@Transactional` rollback được HTTP/Kafka sau khi đã gửi” | Transaction JDBC không tự rollback side effects ngoài DB |
| “`DirectChannel` và `ExecutorChannel` giống nhau về transaction” | Tách thread/queue có thể làm đứt transaction context |
| “Đánh dấu CLAIMED là đã xử lý nghiệp vụ xong” | Cần DONE/FAILED, lease và recovery |
| “JDBC polling là CDC realtime” | Nó định kỳ SELECT, có polling lag và query cost |
| “Chỉ thêm Flux là JDBC trở thành non-blocking” | JDBC vẫn blocking; Reactive Streams là hợp đồng khác |

## 18. Bài thực hành

1. Tạo `integration_inbox` trong H2 với ba dòng `NEW`, chạy SELECT thuần ở mục 5. Quan sát cùng các dòng xuất hiện ở nhiều lần poll.
2. Chuyển sang flow SELECT + UPDATE ở mục 6; giải thích vì sao các dòng chuyển sang `CLAIMED` và không xuất hiện ở lần poll sau.
3. Tắt `split()` để quan sát một `Message<List<Map<String,Object>>>`; bật lại để có từng message theo row.
4. Tăng dữ liệu từ 3 lên 50 row; so sánh `maxMessagesPerPoll(1)` với `setMaxRows(20)` và `LIMIT 20`.
5. Sửa query SELECT thành `WHERE state=:state`, bind `MapSqlParameterSource`. Thử thay giá trị state mà không ghép chuỗi SQL.
6. Thêm `RowMapper<InboxOrder>` và kiểm tra kiểu `BigDecimal`; nếu dùng UPDATE `:id`, xác nhận parameter source hoạt động với DTO.
7. Thay handler in log bằng một handler **JDBC đồng bộ** cập nhật bảng audit. Cho handler ném exception để kiểm tra transaction rollback.
8. Chuyển handler sang `ExecutorChannel` hoặc queue, gây lỗi sau commit và chỉ ra vì sao poller không thể rollback tự động.
9. Chạy hai ứng dụng/pollers trên cùng bảng; mô phỏng race SELECT và thử một chiến lược claim/lock hoặc leader election, kèm idempotent consumer.
10. Thêm `claimed_at`, `attempt_count` và recovery lease; thử crash giữa CLAIMED và DONE rồi xử lý lại có kiểm soát.
11. Đo thời gian query khi số rows lớn; thêm index cho `state, id` và so sánh `EXPLAIN` trước/sau.
12. Tạo một downstream outbound HTTP/Kafka flow và thiết kế outbox/ACK để không mất dữ liệu khi remote chậm hoặc lỗi.

**Câu hỏi thiết kế:** một dịch vụ vận hành ba replicas, tất cả poll cùng bảng đơn hàng. Mỗi row phải phát đúng một sự kiện nghiệp vụ tới Kafka, dù một instance bị kill sau khi UPDATE `CLAIMED` nhưng trước khi Kafka xác nhận. Bạn sẽ dùng khóa/claim, outbox, recovery và idempotency như thế nào? Vì sao chỉ có `SELECT + UPDATE` trong một transaction JDBC chưa đủ để bảo đảm việc gửi Kafka đúng một lần?

## 19. Tài liệu tham khảo

- [Spring Integration — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): các JDBC adapter/gateway, message store và dependency.
- [Spring Integration — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): SELECT → `List` payload, default Map mapper, `UPDATE`/`:id`, poller, transaction, `max-rows` và `max-messages-per-poll`.
- [Spring Integration — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): factory `Jdbc`, specs inbound/outbound từ **Spring Integration 7.0**.
- [Spring Integration API — JdbcPollingChannelAdapter](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): constructor, `setUpdateSql`, `setRowMapper`, `setSelectSqlParameterSource`, `setMaxRows`.
- [Spring Integration — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): polling endpoints và poller configuration.
- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): transaction advice, thread boundary, transaction synchronization và rollback semantics.
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): `DataSource`, `JdbcTemplate`, `RowMapper` và named parameters.

> **Ghi nhớ:** JDBC inbound channel adapter **định kỳ chạy SELECT** và phát **một message chứa List các rows**. Dùng `split()` khi cần từng row; dùng `UPDATE`, poller transaction và trạng thái rõ ràng để tránh đọc lặp. Trong hệ thống nhiều worker hoặc có downstream ngoài database, cần bổ sung atomic claim/locking, idempotency, outbox và recovery; một transaction JDBC không tự bảo đảm exactly-once cho toàn bộ chuỗi tích hợp.
