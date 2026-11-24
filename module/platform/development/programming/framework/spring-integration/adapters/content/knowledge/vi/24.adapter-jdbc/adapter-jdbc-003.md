# JDBC inbound stored procedure adapter trong Spring Integration

## 1. Bối cảnh: lấy dữ liệu từ database bằng stored procedure

Trong nhiều hệ thống, các ứng dụng không được truy cập trực tiếp mọi bảng bằng câu `SELECT` tùy ý. Một hệ thống ERP có thể chỉ công bố stored procedure `POLL_NEW_ORDERS` để trả những đơn hàng mới cần xử lý; một hệ thống kế toán dùng procedure để đọc lô bút toán chưa đồng bộ. Spring Integration cần **chủ động gọi procedure theo chu kỳ** và đưa kết quả vào `MessageChannel` để transformer, splitter, service activator hoặc outbound adapter xử lý tiếp.

**JDBC inbound stored procedure adapter** là **message source có poller**: mỗi lượt poll, nó gọi stored procedure hoặc stored function qua JDBC, đọc các giá trị trả về rồi tạo Spring Integration message. Tên lớp triển khai là `StoredProcPollingChannelAdapter`, dùng `StoredProcExecutor` và nền tảng Spring JDBC `SimpleJdbcCall`.

Bài thuộc chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**. Module nghiên cứu kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, thực hành với file, SFTP, HTTP, JMS, AMQP, Kafka và database, chú trọng hợp đồng message, lỗi và vòng đời kết nối. Ở đây, điểm xuất phát là **database**, không phải HTTP client hay Kafka listener.

~~~mermaid
flowchart LR
    A["TaskScheduler / Poller"] --> B["StoredProcPollingChannelAdapter"]
    B --> C["StoredProcExecutor / SimpleJdbcCall"]
    C -->|"EXEC stored procedure"| D[("Relational database")]
    D -->|"ResultSet / OUT parameters"| C
    C --> B
    B -->|"Message<Map> hoặc Message<List>"| E["MessageChannel"]
    E --> F["Filter / Splitter / Transformer"]
    F --> G["JMS / Kafka / HTTP / Service"]
~~~

Ví dụ xuyên suốt dùng SQL Server. Procedure `POLL_NEW_ORDERS` nhận `maxRows`, nhận diện một số đơn hàng có trạng thái `NEW`, chuyển chúng sang `CLAIMED` và trả một result set. Đây là **ví dụ có side effect tại database**; cần nắm transaction và khôi phục các dòng đã claim nhưng chưa được xử lý trước khi áp dụng thực tế.

## 2. Phân biệt stored procedure inbound với các JDBC endpoint khác

| Endpoint | Ai khởi động? | Hợp đồng dữ liệu | Khi dùng |
|---|---|---|---|
| JDBC inbound channel adapter | **Poller** gọi `SELECT` | Database rows → message | Query trực tiếp được phép và đủ đơn giản |
| **Stored procedure inbound channel adapter** | **Poller** gọi `CALL/EXEC` | ResultSet/OUT → message | Phải gọi procedure/function, logic đọc nằm ở DB |
| Stored procedure outbound channel adapter | **Message đến input channel** | Message → procedure side effect, không có reply nghiệp vụ | Ghi bằng procedure sau khi nhận event |
| Stored procedure outbound gateway | **Message đến request channel** | Message → procedure → reply message | Cần tham số động từ message và nhận kết quả |
| JDBC outbound adapter | **Message đến input channel** | Message → DML `INSERT/UPDATE/DELETE` | Ghi SQL một chiều |

Một số hiểu nhầm thường gặp:

- Inbound stored procedure adapter **không chờ** một message đến trước khi gọi procedure: nó được poller kích hoạt theo lịch.
- `maxMessagesPerPoll` giới hạn **số lần message source được hỏi trong một chu kỳ**, không phải số hàng lấy từ database.
- Procedure trả nhiều rows **không đồng nghĩa** adapter phát một message cho từng row. Một result set có thể được map thành một `List<Row>` nằm trong một message; muốn các message riêng cần splitter.
- JDBC là **blocking I/O**. Poller có scheduler/worker thread; không giả định nó sử dụng R2DBC hoặc Reactive Streams chỉ vì output channel có thể nối với một ứng dụng WebFlux.

## 3. Cơ chế bên trong: poller, executor, SimpleJdbcCall và result map

Một lượt poll điển hình:

1. `SourcePollingChannelAdapter` kích hoạt `MessageSource.receive()` khi tới lịch.
2. `StoredProcPollingChannelAdapter` gọi `StoredProcExecutor.executeStoredProcedure()`.
3. `StoredProcExecutor` dùng Spring JDBC `SimpleJdbcCall` để gọi procedure/function từ `DataSource`.
4. Các `OUT` parameters, result sets và kết quả thích hợp được đưa vào một `Map<String, Object>`.
5. Adapter quyết định payload theo `expectSingleResult`, tạo message và gửi tới output channel.
6. Downstream xử lý payload; transaction của poller (nếu có) commit hoặc rollback theo ranh giới đã cấu hình.

~~~mermaid
sequenceDiagram
    participant Timer as Poller
    participant Source as StoredProcPollingChannelAdapter
    participant Exec as StoredProcExecutor
    participant DB as Database
    participant Next as Downstream
    Timer->>Source: receive()
    Source->>Exec: executeStoredProcedure()
    Exec->>DB: CALL/EXEC procedure
    DB-->>Exec: ResultSet + OUT parameters
    Exec-->>Source: Map<String,Object>
    Source-->>Next: Message<List<Row>> hoặc Message<Map>
    Note over Timer,Next: Khi cấu hình poller transaction, đồng bộ downstream có thể cùng TX
~~~

**Đừng suy từ tên `stored procedure` rằng lời gọi tự có transaction nguyên tử xuyên mọi hệ thống.** Procedure có thể thực hiện DML, commit hoặc rollback tùy database và code SQL. Poller transaction chỉ bao trùm những tài nguyên thực sự tham gia transaction đó; JMS/Kafka/HTTP không tự động commit cùng một JDBC transaction.

## 4. Tạo procedure minh họa trên SQL Server

### 4.1. Schema nguồn

Ví dụ dùng SQL Server để nhận về một JDBC `ResultSet` trực tiếp. DDL có tính đặc thù của SQL Server, không chạy nguyên văn trên PostgreSQL, MySQL, Oracle hoặc H2.

~~~sql
CREATE TABLE dbo.integration_order (
    order_id    BIGINT NOT NULL PRIMARY KEY,
    status      VARCHAR(20) NOT NULL,
    created_at  DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    claimed_at  DATETIME2 NULL
);
GO

INSERT INTO dbo.integration_order (order_id, status)
VALUES (1001, 'NEW'), (1002, 'NEW'), (1003, 'NEW');
GO
~~~

### 4.2. Stored procedure “claim và trả kết quả”

~~~sql
CREATE OR ALTER PROCEDURE dbo.POLL_NEW_ORDERS
    @maxRows INT
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH candidates AS (
        SELECT TOP (@maxRows)
            order_id, status, created_at, claimed_at
        FROM dbo.integration_order
            WITH (UPDLOCK, READPAST, ROWLOCK)
        WHERE status = 'NEW'
        ORDER BY created_at, order_id
    )
    UPDATE candidates
       SET status = 'CLAIMED',
           claimed_at = SYSUTCDATETIME()
    OUTPUT
       inserted.order_id,
       inserted.status,
       inserted.created_at;
END;
GO
~~~

Phân tích:

- `@maxRows` là input parameter, để giới hạn **số hàng tại database** trước khi đưa dữ liệu lên ứng dụng.
- `TOP (@maxRows)` là cú pháp SQL Server; trong hệ quản trị khác cần cơ chế giới hạn riêng.
- `UPDLOCK`/`READPAST`/`ROWLOCK` nhằm hạn chế nhiều consumer tranh cùng dòng, nhưng hiệu quả thực tế còn phụ thuộc **isolation level, chỉ mục và cấu hình database**. Với cơ chế `READ_COMMITTED_SNAPSHOT`, cần kiểm tra yêu cầu khóa cụ thể của SQL Server.
- `UPDATE ... OUTPUT inserted...` vừa claim vừa trả result set gồm các dòng đã claim. Đó là một **thao tác DML**, không phải truy vấn chỉ đọc.
- `SET NOCOUNT ON` hạn chế các update counts phụ làm nhiễu cấu trúc kết quả JDBC.

Sau một lượt poll nhận hai dòng, kết quả ví dụ:

| order_id | status | created_at |
|---:|---|---|
| 1001 | CLAIMED | Giá trị thời gian của DB |
| 1002 | CLAIMED | Giá trị thời gian của DB |

**Vấn đề cần giải quyết trước production:** nếu database commit claim thành công rồi ứng dụng crash trước khi gửi tiếp message, hai dòng có thể kẹt ở `CLAIMED`. Cần một chiến lược **lease/timeout, requeue, recovery worker hoặc transactional outbox**. Không xem ví dụ procedure trên là “exactly-once end-to-end”.

## 5. Dependency, version và môi trường chạy

Spring Integration JDBC sử dụng `DataSource` và JDBC driver. Với Spring Boot nên để BOM quản lý các phiên bản tương thích:

~~~groovy
// build.gradle: dependencies minh họa
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    // Driver phù hợp cho SQL Server; Boot BOM quản lý phiên bản nếu có.
    runtimeOnly 'com.microsoft.sqlserver:mssql-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml - môi trường có SQL Server và TLS được cấu hình đúng
spring:
  datasource:
    url: "jdbc:sqlserver://db.example.internal:1433;databaseName=integration;encrypt=true"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
~~~

Tên host và database chỉ là ví dụ. Không hardcode mật khẩu trong repository; dùng environment/secret manager. SQL Server cần cấu hình chứng chỉ, hostname và trust chain phù hợp; không tắt xác thực TLS để che lỗi kết nối.

**Phân biệt phiên bản Spring Integration:**

- Từ **7.0**, JDBC module có Java DSL factory `Jdbc.storedProcInboundAdapter(dataSource)` cùng `JdbcStoredProcInboundChannelAdapterSpec`.
- Với **6.x**, vẫn có `StoredProcPollingChannelAdapter`/`StoredProcExecutor` và XML namespace. Không giả định factory Java DSL 7.x tồn tại trong 6.x.
- Các kiểu JDBC như `SqlParameter` nằm trong Spring Framework; các kiểu như `ProcedureParameter` nằm trong `org.springframework.integration.jdbc.storedproc`. Chọn API và import theo version thực tế.

**H2 và stored procedure:** H2 không có đầy đủ các semantics `CallableStatement`/result set như mọi hệ quản trị production; bài test quan trọng nên chạy trên SQL Server thật hoặc Testcontainers, không chỉ H2.

## 6. Java DSL 7.x: poll stored procedure và phát từng row

Java DSL 7.x cung cấp builder để cấu hình executor, mapping result set và poller trong một flow. Dưới đây là cấu hình phù hợp với procedure ở mục 4.

~~~java
package com.example.integration;

import java.sql.Types;
import java.time.Duration;
import java.time.LocalDateTime;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.integration.jdbc.storedproc.ProcedureParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class StoredProcedureInboundFlow {

    public record OrderRow(
        long orderId, String status, LocalDateTime createdAt) { }

    @Bean
    public IntegrationFlow ordersFromProcedure(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow.from(
                Jdbc.storedProcInboundAdapter(dataSource)
                    .expectSingleResult(true)
                    .configurerStoredProcExecutor(c -> c
                        .storedProcedureName("POLL_NEW_ORDERS")
                        .isFunction(false)
                        .ignoreColumnMetaData(true)
                        .sqlParameter(new SqlParameter(
                            "maxRows", Types.INTEGER))
                        .procedureParameter(new ProcedureParameter(
                            "maxRows", 25, null))
                        .returningResultSetRowMapper(
                            "orders",
                            (rs, rowNum) -> new OrderRow(
                                rs.getLong("order_id"),
                                rs.getString("status"),
                                rs.getTimestamp("created_at")
                                    .toLocalDateTime()))),
                e -> e.poller(Pollers.fixedDelay(Duration.ofSeconds(5))
                    .maxMessagesPerPoll(1)
                    .transactional(transactionManager)))
            .filter(payload ->
                payload instanceof java.util.List<?> rows && !rows.isEmpty())
            .split()
            .channel("claimedOrders")
            .get();
    }

    @ServiceActivator(inputChannel = "claimedOrders")
    public void processRow(OrderRow row) {
        System.out.printf("Claimed order %d: %s%n",
            row.orderId(), row.status());
    }
}
~~~

**Phân tích từng thành phần:**

1. `Jdbc.storedProcInboundAdapter(dataSource)` tạo `MessageSource` của **inbound procedure**, không phải outbound gateway.
2. `configurerStoredProcExecutor(...)` đặt tên procedure, khai báo metadata/parameter và row mapper.
3. `ignoreColumnMetaData(true)` tắt lookup parameter metadata tự động; ví dụ khai báo rõ input `maxRows` bằng `SqlParameter`.
4. `ProcedureParameter("maxRows", 25, null)` cung cấp **giá trị tĩnh 25** tại thời điểm poll. Inbound adapter không có message request bên ngoài để lấy `payload.maxRows`.
5. `returningResultSetRowMapper("orders", ...)` biến từng hàng của JDBC ResultSet thành `OrderRow` và đặt list trong output map dưới key `orders`.
6. `expectSingleResult(true)` trích **một phần tử duy nhất của result map**. Trong ví dụ, đó là **`List<OrderRow>`**, không phải một `OrderRow` đơn.
7. `maxMessagesPerPoll(1)` yêu cầu message source tối đa một lần mỗi nhịp poll. **Không thay thế `maxRows=25`** trong procedure.
8. `transactional(transactionManager)` cho phép poller chạy trong transaction khi manager thích hợp được cấu hình. Phải đánh giá ranh giới transaction của toàn bộ luồng; không mặc định nó bao trùm mọi hệ thống ngoài DB.
9. `filter` loại danh sách rỗng, `split()` biến từng row trong `List` thành message riêng cho `claimedOrders`.
10. `@ServiceActivator` minh họa consumer đồng bộ; trong ứng dụng thực, không coi `System.out.println` là điểm xác nhận xử lý bền vững.

**Cảnh báo quan trọng:** SQL Server trong ví dụ tạo procedure ở schema `dbo`. Account JDBC phải có default schema/khả năng resolve `POLL_NEW_ORDERS` phù hợp; nếu không, cần cấu hình schema của `SimpleJdbcCall` theo API hỗ trợ hoặc tạo procedure ở schema được resolve. Không ghép schema/tên procedure từ input không tin cậy.

### 6.1. Một lượt poll tạo bao nhiêu message?

Giả sử `maxRows=25` và procedure lấy được 3 hàng:

~~~text
Poller (1 lần receive)
  -> StoredProcExecutor
  -> resultMap = {"orders": List<OrderRow>(3)}
  -> expectSingleResult(true)
  -> Message<List<OrderRow>>(3)
  -> filter (list không rỗng)
  -> splitter
  -> 3 x Message<OrderRow>
~~~

Nếu bỏ `split()`, downstream nhận **một message chứa list**. Nếu đổi `expectSingleResult(false)`, downstream có thể nhận **map** thay vì list, nên splitter/transformer phải được viết theo kiểu dữ liệu tương ứng.

## 7. expectSingleResult: một kết quả trong map không phải một row

Sau khi thực thi procedure/function, `StoredProcExecutor` trả `Map<String, Object>`. Map có thể bao gồm nhiều OUT params, return value và các result set. `StoredProcPollingChannelAdapter.setExpectSingleResult(true)` hoạt động với **số entry của result map**:

| Kết quả executor | `expectSingleResult=false` | `expectSingleResult=true` |
|---|---|---|
| `{"orders": List<OrderRow>}` | Payload là map | Payload là `List<OrderRow>` |
| `{"count": 7}` | Payload là map | Payload là `Integer`/giá trị OUT |
| `{"orders": List, "total": 7}` | Payload là map | **Lỗi** vì có nhiều result entries |
| Kết quả rỗng/không có payload phù hợp | Phụ thuộc result map/DB/framework | Không được giả định có một message chứa null |

Vì vậy, **`expectSingleResult(true)` không phải chế độ trả một row**. Để biến từng row thành message, dùng splitter, và nếu cần chỉ một row thì phải giới hạn row count ở procedure/SQL hoặc kiểm tra kết quả sau mapping.

Tài liệu Spring Integration cũng lưu ý một số cơ sở dữ liệu (đặc biệt một số kịch bản H2 functions) có cách trả `CallableStatement` khác; cùng cấu hình có thể vẫn cho một collection thay vì scalar. Hãy **kiểm tra kiểu payload thực tế** trong integration test với database bạn dùng.

## 8. Cấu hình XML dùng cho hệ thống Spring Integration 6.x

Spring Integration JDBC đã hỗ trợ stored procedure inbound qua XML namespace từ lâu. Cấu hình sau tương đương về ý tưởng với Java DSL: dùng poller gọi procedure, map result set và gửi vào channel.

~~~xml
<!-- Fragment: cần namespace int và int-jdbc trong Spring XML context. -->
<int:channel id="orderBatchChannel"/>

<int-jdbc:stored-proc-inbound-channel-adapter
    id="storedProcOrderPoller"
    channel="orderBatchChannel"
    data-source="dataSource"
    stored-procedure-name="POLL_NEW_ORDERS"
    ignore-column-meta-data="true"
    skip-undeclared-results="true">

    <int:poller fixed-delay="5000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>

    <int-jdbc:sql-parameter-definition
        name="maxRows" direction="IN" type="INTEGER"/>
    <int-jdbc:parameter
        name="maxRows" type="java.lang.Integer" value="25"/>
    <int-jdbc:returning-resultset
        name="orders" row-mapper="orderRowMapper"/>
</int-jdbc:stored-proc-inbound-channel-adapter>
~~~

Ví dụ này cần có bean `dataSource`, `transactionManager`, `orderRowMapper` và cấu hình namespace/schema XML của Spring Integration. `orderBatchChannel` nhận message chứa **result map** mặc định; nếu muốn downstream nhận `List<OrderRow>` như Java DSL mục 6, cần cấu hình `expect-single-result="true"` nếu phiên bản schema XML tương ứng hỗ trợ và xác minh kết quả, hoặc dùng transformer lấy `payload['orders']` rồi splitter.

**Không copy đoạn XML lẫn Java DSL trong cùng ứng dụng và vô tình chạy hai pollers** cho một nguồn, trừ khi đó là thiết kế concurrency có chủ đích. Cấu hình 7.x ở mục 6 và XML ở đây là hai cách triển khai thay thế.

## 9. Java configuration trực tiếp cho Spring Integration 6.x

Khi không dùng XML và dự án còn ở Spring Integration 6.x, có thể khởi tạo `StoredProcExecutor` cùng `StoredProcPollingChannelAdapter` theo API đã có trước Java DSL 7.x:

~~~java
package com.example.integration;

import java.sql.Types;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.StoredProcExecutor;
import org.springframework.integration.jdbc.StoredProcPollingChannelAdapter;
import org.springframework.integration.jdbc.storedproc.ProcedureParameter;
import org.springframework.jdbc.core.SqlParameter;

@Configuration
public class StoredProcLegacyConfiguration {

    @Bean
    public StoredProcExecutor orderProcedureExecutor(DataSource dataSource) {
        StoredProcExecutor executor = new StoredProcExecutor(dataSource);
        executor.setStoredProcedureName("POLL_NEW_ORDERS");
        executor.setIgnoreColumnMetaData(true);
        executor.setSqlParameters(List.of(
            new SqlParameter("maxRows", Types.INTEGER)));
        executor.setProcedureParameters(List.of(
            new ProcedureParameter("maxRows", 25, null)));
        executor.setReturningResultSetRowMappers(Map.of(
            "orders",
            (rs, rowNum) -> new StoredProcedureInboundFlow.OrderRow(
                rs.getLong("order_id"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime())));
        return executor;
    }

    @Bean
    public StoredProcPollingChannelAdapter orderProcedureSource(
            StoredProcExecutor orderProcedureExecutor) {
        StoredProcPollingChannelAdapter source =
            new StoredProcPollingChannelAdapter(orderProcedureExecutor);
        source.setExpectSingleResult(true);
        return source;
    }

    @Bean
    public IntegrationFlow orderProcedureFlow(
            StoredProcPollingChannelAdapter orderProcedureSource) {
        return IntegrationFlow.from(orderProcedureSource,
                e -> e.poller(Pollers.fixedDelay(Duration.ofSeconds(5))
                    .maxMessagesPerPoll(1)))
            .filter(payload ->
                payload instanceof java.util.List<?> rows && !rows.isEmpty())
            .split()
            .channel("legacyClaimedOrders")
            .get();
    }
}
~~~

**Ghi chú phiên bản/cấu trúc:** đoạn này minh họa API `org.springframework.integration.jdbc.StoredProcExecutor` và `StoredProcPollingChannelAdapter` ở 6.x; kiểu DTO `OrderRow` được lấy từ ví dụ 7.x nhằm tránh lặp định nghĩa, nhưng trong ứng dụng 6.x độc lập hãy khai báo record DTO riêng cùng cấu trúc. Transactional poller đã được trình bày ở mục 6 và 8; ví dụ này cố ý chỉ minh họa cách tạo source, nên cần bổ sung transaction manager nếu procedure có DML claim.

Trong 6.x, framework tự quản lý bean lifecycle của `StoredProcExecutor` khi nó là một Spring bean; không cần gọi thủ công `afterPropertiesSet()` trong đoạn cấu hình trên. Không trộn API factory `Jdbc.storedProcInboundAdapter(...)` của 7.x vào dự án 6.x.

## 10. Stored procedure parameters: IN, OUT, INOUT và return value

`SimpleJdbcCall` có thể lấy thông tin parameters từ JDBC metadata nếu database hỗ trợ. Khi metadata không đủ tin cậy hoặc cần kiểu cụ thể, dùng khai báo thủ công:

| Loại | Vai trò | Cách cấu hình |
|---|---|---|
| `IN` | Giá trị truyền vào procedure | `SqlParameter` + `ProcedureParameter` tĩnh/SpEL |
| `OUT` | Giá trị procedure trả ra | `SqlOutParameter` hoặc XML `sql-parameter-definition direction="OUT"` |
| `INOUT` | Vừa vào vừa ra | `SqlInOutParameter` hoặc XML `direction="INOUT"` |
| ResultSet | Danh sách hàng | `returning-resultset` / `returningResultSetRowMapper(...)` |
| SQL function return | Giá trị hàm | `is-function="true"` và khai báo kiểu/return phù hợp |

**Điểm rất quan trọng cho inbound:** adapter không nhận một request message từ bên ngoài để lấy tham số động theo `payload`/`headers`. Tham số `maxRows` trong ví dụ là **giá trị tĩnh**. Tài liệu Spring Integration nêu rằng `sql-parameter-source-factory` và `use-payload-as-parameter-source` **không áp dụng** cho stored procedure inbound channel adapter.

Nếu procedure cần giá trị **khác nhau cho từng message**, thường nên chọn **stored procedure outbound gateway** để gửi `Message<?>` vào request channel, hoặc triển khai một nguồn dữ liệu chủ động khác với cách cung cấp parameter được kiểm soát rõ. Đừng viết SpEL `payload.xxx` cho inbound poller rồi kỳ vọng tự có payload nguồn.

### 10.1. Procedure hay function?

`isFunction(false)` (mặc định) gọi stored procedure. Với function, đặt `isFunction(true)` và xác định tên/return theo hợp đồng của DB. SQL functions không giống nhau giữa PostgreSQL, Oracle, MySQL hoặc SQL Server; có DB trả scalar, có DB trả set/table. Test `OUT`, result map và `expectSingleResult` với driver thật.

### 10.2. Tên procedure không phải tham số SQL bind

`stored-procedure-name-expression` cho một số thành phần có khả năng chọn procedure name bằng SpEL. Đừng cho input không tin cậy quyết định tên procedure/function, vì placeholder chỉ bind **giá trị** chứ không bảo vệ việc gọi một routine tùy ý. Với inbound poller nên ưu tiên tên routine cố định, tài khoản DB có quyền `EXECUTE` tối thiểu.

## 11. Poller: khoảng thời gian, số lần gọi và giới hạn rows

| Tham số | Đơn vị | Ví dụ | Hệ quả |
|---|---|---|---|
| `fixedDelay` | Thời gian giữa kết thúc và bắt đầu đợt sau | 5 giây | Không tự chồng chu kỳ nếu một poll chạy lâu trong cùng cấu hình |
| `fixedRate` | Lịch theo nhịp định kỳ | 5 giây | Cần kiểm soát concurrency và scheduler |
| `maxMessagesPerPoll` | Số lần `receive()` trong một lần trigger | 1 | Không đồng nghĩa một row |
| `maxRows` truyền vào procedure | Số rows claim/trả trên **mỗi lời gọi** | 25 | Giới hạn ngay tại database |
| Giới hạn thread/pool | Số tác vụ/connection đang xử lý | Theo tải | Tránh tạo quá nhiều kết nối và DB locks |

Giả sử poller mỗi 5 giây có `maxMessagesPerPoll(1)` và procedure chọn tối đa 25 rows. Một poll có thể tạo **một message chứa 25 rows**, sau splitter thành 25 messages. Nếu tăng `maxMessagesPerPoll` lên 5, adapter có thể gọi procedure **nhiều lần trong cùng một chu kỳ**, tùy nguồn và kết quả, gây thêm các database calls; không phải tự đổi thành “5 rows”.

**Không nên dựa vào giới hạn rows ở tầng Java mới cắt dữ liệu đã được DB đọc quá nhiều.** Ưu tiên LIMIT/TOP/cursor/batch ngay trong procedure để bảo vệ DB và memory.

### 11.1. Poller có transaction

Với procedure vừa claim vừa trả rows, có thể bọc công việc trong **transaction của poller**:

~~~java
// Mảnh DSL, transactionManager là PlatformTransactionManager
e -> e.poller(
    Pollers.fixedDelay(Duration.ofSeconds(5))
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
~~~

Khi downstream dùng `DirectChannel` và chạy **đồng bộ trong cùng thread**, công việc JDBC có thể cùng transaction của poller. Khi chèn `ExecutorChannel`, `QueueChannel` hoặc gửi Kafka/HTTP bất đồng bộ, transaction của poller không tự lan qua thread/process khác. Phải chọn commit/ACK/recovery boundary riêng.

## 12. Transaction, crash recovery và chống xử lý trùng

### 12.1. Vì sao “claim xong” chưa phải “đã xử lý xong”?

Ví dụ procedure mục 4 đổi trạng thái `NEW → CLAIMED`. Nếu downstream thất bại, có hai tình huống:

- **Cùng JDBC transaction, downstream đồng bộ ném lỗi trước commit**: transaction có thể rollback, đưa trạng thái về `NEW` để poll tiếp.
- **Transaction đã commit claim rồi downstream xử lý ở hệ thống khác**: một lỗi sau commit **không tự rollback** claim. Cần lease/reclaim và idempotency ở bước sau.

~~~mermaid
flowchart TB
    A["NEW"] -->|"procedure claim"| B["CLAIMED"]
    B -->|"Xử lý thành công + commit"| C["PROCESSED"]
    B -->|"Rollback cùng transaction"| A
    B -->|"Crash / lease hết hạn"| D["Reclaim hoặc DEAD_LETTER"]
    D -->|"Retry có giới hạn"| A
    D -->|"Lỗi vĩnh viễn"| E["FAILED + cảnh báo"]
~~~

### 12.2. Hai phương án đáng tin cậy

**Phương án A — transaction đồng bộ, thao tác DB cùng nguồn.** Bọc poller và handler đồng bộ trong cùng local `DataSourceTransactionManager`; khi handler ném exception, rollback claim. Phù hợp khi toàn bộ công việc thực sự nằm trong một database transaction ngắn. Không giữ transaction dài chỉ để chờ HTTP/SFTP/Kafka.

**Phương án B — claim/lease + outbox/idempotency.** Procedure claim và lưu `lease_until`/`attempt_count`, một worker xử lý; nếu worker chết, job recovery lấy lại lease hết hạn. Với event publish ra broker, transactional outbox ghi event trong DB transaction, rồi publisher gửi và đánh dấu. Consumer downstream dùng `eventId` để chống xử lý trùng khi redelivery.

Không có cấu hình poller nào biến JDBC + Kafka + HTTP thành **một giao dịch phân tán exactly-once** theo mặc định.

### 12.3. Concurrency khi nhiều instance chạy cùng poller

Nếu chạy nhiều ứng dụng/pods cùng gọi procedure, mỗi instance có poller độc lập. Cần đảm bảo **atomic claim ở database**, locks/cursor đúng và cơ chế lease cho các rows chưa hoàn thành. SQL Server hints chỉ là ví dụ; các DB khác dùng cơ chế tương ứng như `FOR UPDATE SKIP LOCKED` hoặc transactional update với locking tương thích. Không dùng một câu `SELECT WHERE status='NEW'` thuần rồi giả định các pods không đọc cùng row.

## 13. Lỗi, retry, backoff và errorChannel

Những nhóm lỗi thường gặp:

| Lỗi | Biểu hiện | Xử lý |
|---|---|---|
| Procedure không tồn tại / sai schema | Invalid object/name | Sửa schema, quyền EXECUTE, version migration |
| Tên/kiểu parameter không khớp | JDBC metadata/bind failure | Kiểm tra `SqlParameter`, `ignoreColumnMetaData`, driver |
| ResultSet trả hình dạng bất ngờ | Mapper lỗi / `expectSingleResult` không đúng | Kiểm tra OUT/results, codec/type và count của map |
| DB connection unavailable | `DataAccessResourceFailureException` hoặc driver cause | Retry có giới hạn, backoff, alert |
| Deadlock / lock timeout | Transient data access exception | Retry **toàn transaction** nếu an toàn |
| Downstream service ném lỗi | Message handling exception | Rollback/recovery tùy channel/transaction |
| Không có rows | List rỗng hoặc không tạo message theo semantics | Filter rỗng, metrics, không coi là lỗi mặc định |
| DB chậm / batch lớn | Poll chồng lịch, pool exhaustion | Giới hạn maxRows, pool, timeouts và concurrency |

**Retry:** không đặt poller cố định quá dày khi DB đang chết; nhiều replicas cùng retry có thể tạo *retry storm*. Thêm backoff/jitter và circuit-breaker/health gating theo nhu cầu. Các lỗi cấu hình/schema không nên retry vô hạn. Với procedure có side effect claim, retry cần đảm bảo idempotency và transaction semantics.

**Error channel:** Spring Integration có `ErrorMessage`/`errorChannel` hoặc error handler của poller, tùy endpoint và cấu hình. Đừng giả định một lỗi JDBC tự động biến thành một business message bình thường trên output channel, hoặc mọi lỗi của mọi thread đều đến cùng một handler. Kiểm thử đường đi của exception, transaction rollback và re-poll trong phiên bản thực tế.

## 14. Payload contract, chuyển đổi và split

Một inbound procedure thường có **kết quả không đồng nhất**: map có key theo OUT parameter, result set list, count hoặc function return. Dễ nhất là tạo một ranh giới chuyển đổi rõ ràng:

~~~text
StoredProcExecutor result map
  {"orders": List<OrderRow>}
      |
expectSingleResult(true)
      v
Message<List<OrderRow>>
      |
filter(!empty)
      |
splitter
      v
Message<OrderRow> x N
      |
validator / router / gateway / Kafka adapter
~~~

Không định tuyến payload vào một handler có signature `handle(OrderRow)` nếu thực tế payload còn là `Map<String,Object>` hoặc `List<OrderRow>`. Thêm test cho:

- Map chỉ có một entry trả list.
- Map có thêm OUT parameter; xử lý lỗi/transformer khi `expectSingleResult` bật.
- List rỗng hoặc không có result set.
- Null trong một SQL column, `Timestamp` chuyển `LocalDateTime`, tên cột/alias.
- Out-of-order events và duplicate IDs.

Với file/SFTP/HTTP/JMS/Kafka ở downstream, thêm correlation ID mang ý nghĩa nghiệp vụ (order ID, event ID, source system), không chỉ dùng message ID do Spring Integration sinh; message ID có thể khác sau retry hoặc split.

## 15. Bảo mật, hiệu năng và quan sát

**Quyền truy cập:** tài khoản kết nối DB chỉ nên có `EXECUTE` trên procedure được phép và quyền bảng tối thiểu mà routine cần. Không biến dữ liệu nguồn thành tên procedure động rồi thực thi tùy ý; dùng schema, allowlist và migration kiểm soát routine.

**Connection pool:** poller JDBC sử dụng connection của `DataSource`, vì vậy mỗi procedure đang chạy có thể chiếm slot của pool và giữ locks. Theo dõi active/idle/pending connections, thời gian chờ acquire, thời gian thực thi procedure và số transaction rollback. Tăng poller concurrency vô hạn có thể làm DB chậm đi.

**Metrics cần ghi:**

1. Số lần poll, độ trễ procedure, số rows mỗi poll, số rows mới/đã xử lý.
2. Số batch rỗng, tỉ lệ lỗi DB, lock wait, deadlock, timeout và retry.
3. Dung lượng backlog (số rows `NEW`/`CLAIMED`/`FAILED`), tuổi `CLAIMED`, lease quá hạn.
4. Độ trễ end-to-end từ row tạo đến Kafka/JMS/HTTP đã nhận.
5. Số duplicate events, số lần redelivery, outbox lag, DLQ và cảnh báo.

**Bảo mật dữ liệu:** không log PII/payment data từ toàn result set, JDBC credentials hay SQL bind values nhạy cảm. Dùng tracing/correlation ID có giới hạn cardinality, kiểm tra encryption at rest/TLS theo chính sách môi trường.

## 16. Kiểm thử với database thật và thử nghiệm lỗi

Tài liệu Spring Integration ghi rõ stored procedure support phụ thuộc `SimpleJdbcCall` và JDBC driver, H2 có hạn chế về semantics `CallableStatement`. Với ví dụ SQL Server, test nên dùng **SQL Server riêng cho test hoặc Testcontainers**, không chỉ mock `StoredProcExecutor`.

### 16.1. Mô tả integration test

1. Khởi tạo bảng và procedure theo mục 4 trong database test.
2. Chèn 3 đơn hàng `NEW`.
3. Khởi động ứng dụng chứa flow với `maxRows=2` và thời gian poll test có kiểm soát.
4. Quan sát **một** poll claim tối đa 2 rows, trả `List<OrderRow>`, splitter phát 2 messages.
5. Xác nhận DB đã chuyển đúng hai rows sang `CLAIMED` sau transaction commit.
6. Cho poll tiếp: claim row thứ ba; khi hết `NEW`, downstream không nhận batch nghiệp vụ rỗng.
7. Đưa exception vào một downstream handler đồng bộ để kiểm chứng rollback nếu poller transaction đã cấu hình; kiểm tra row có được poll lại không.
8. Chạy 2 app instances song song, đối soát mỗi order ID được claim theo policy concurrency.
9. Mô phỏng crash sau commit claim: khởi động recovery job hoặc lease timeout, xác minh không có rows kẹt vô hạn.

### 16.2. Test mapper đơn vị

Có thể kiểm tra RowMapper bằng unit test độc lập với poller:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.RowMapper;

class OrderRowMapperTest {

    @Test
    void mapsDatabaseColumns() throws Exception {
        ResultSet rs = mock(ResultSet.class);
        LocalDateTime created = LocalDateTime.of(2026, 11, 1, 9, 0);
        when(rs.getLong("order_id")).thenReturn(1001L);
        when(rs.getString("status")).thenReturn("CLAIMED");
        when(rs.getTimestamp("created_at"))
            .thenReturn(Timestamp.valueOf(created));

        RowMapper<StoredProcedureInboundFlow.OrderRow> mapper =
            (resultSet, rowNum) ->
                new StoredProcedureInboundFlow.OrderRow(
                    resultSet.getLong("order_id"),
                    resultSet.getString("status"),
                    resultSet.getTimestamp("created_at")
                        .toLocalDateTime());

        var row = mapper.mapRow(rs, 0);
        assertEquals(1001L, row.orderId());
        assertEquals("CLAIMED", row.status());
        assertEquals(created, row.createdAt());
    }
}
~~~

Ví dụ Mockito giả lập một `ResultSet` để test mapping field/type, **không kiểm chứng** procedure thực sự trả đúng ResultSet hoặc JDBC metadata. Kiểm thử đó cần database thật. Nếu test dùng Spring Boot starter test, kiểm tra dependency Mockito/JUnit tương ứng.

### 16.3. Ma trận kiểm thử tối thiểu

| Tình huống | Điều cần xác minh |
|---|---|
| Procedure trả 2 rows | `Message<List<OrderRow>>` → 2 messages sau splitter |
| Procedure trả 0 rows | Không phát business event trống ngoài ý muốn |
| Result map chứa nhiều OUT entries | `expectSingleResult` và mapping đúng hợp đồng |
| SQL parameter sai kiểu/tên | Lỗi xuất hiện, metrics/error flow ghi nhận |
| DB mất kết nối | Poller retry/backoff, không tạo busy loop |
| Một downstream handler ném lỗi | Rollback nếu cùng DB TX; recovery nếu đã commit |
| Nhiều pollers/replicas | Không claim trùng ngoài giới hạn thiết kế |
| Crash sau claim trước publish | Lease/recovery hoặc outbox xử lý |
| H2 khác SQL Server | Test không suy diễn tương đương CallableStatement |
| DB schema/permissions sai | Dừng/cảnh báo lỗi cấu hình, không retry vô hạn |

## 17. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Inbound procedure adapter chạy mỗi khi nhận message” | **Poller** chủ động gọi `receive()` |
| “`maxMessagesPerPoll(1)` là lấy một hàng” | Một lần gọi source có thể trả `List` nhiều hàng |
| “`expectSingleResult(true)` là lấy một row” | Nó bóc **một entry của result map**, có thể là `List<Row>` |
| “Stored procedure trả 3 rows tạo 3 messages ngay” | Cần splitter hoặc logic tách row |
| “Không có rows là exception bắt buộc” | Có thể là trạng thái thường, cần filter/contract |
| “Có `@Transactional` ở bất kỳ downstream nào là đủ” | Ranh giới thread, poller TX và resource manager quyết định |
| “Procedure claim thành công nghĩa Kafka đã nhận event” | DB TX không tự đồng bộ với broker |
| “Bật nhiều replicas tự tránh double claim” | Cần DB locks/atomic claim và recovery |
| “`Jdbc.storedProcInboundAdapter` dùng được Spring Integration 6.x” | Factory Java DSL có từ 7.0 |
| “Inbound có thể đọc `payload.maxRows` của request” | Không có request message; parameter phải được cấu hình độc lập |
| “JDBC là non-blocking vì flow nằm trong WebFlux app” | JDBC synchronous; phải quản lý poller thread/pool |
| “H2 test thành công đảm bảo mọi vendor giống nhau” | Stored procedure/CallableStatement khác theo DB/driver |

## 18. Bài thực hành

1. Tạo bảng `integration_order` và procedure `POLL_NEW_ORDERS` trên SQL Server test. Thử gọi procedure thủ công với `@maxRows=2`.
2. Tạo flow `Jdbc.storedProcInboundAdapter` cho Spring Integration 7.x, poll mỗi 5 giây; kiểm tra output map/list.
3. Bỏ `expectSingleResult(true)` và in kiểu payload. Sau đó bật lại, giải thích vì sao kết quả là list chứ không phải một row.
4. Bỏ `split()`, sau đó thêm lại; đo số messages downstream cho 2, 5 và 0 rows.
5. Đổi `maxMessagesPerPoll(1)` thành `2` và quan sát số lần procedure có thể chạy trong một nhịp; phân biệt với `maxRows`.
6. Tạo cấu hình XML inbound stored-proc cho 6.x và so sánh với Java `StoredProcExecutor`/`StoredProcPollingChannelAdapter`.
7. Thêm OUT parameter `totalClaimed` vào procedure, kiểm thử result map có nhiều entries và `expectSingleResult`.
8. Cố tình khai báo sai `SqlParameter` hoặc tắt metadata lookup không phù hợp; xác định lỗi từ `SimpleJdbcCall`.
9. Đưa handler ghi DB đồng bộ sau splitter và ném exception có chủ đích, kiểm tra poller transaction rollback.
10. Thêm `ExecutorChannel` trước handler, chứng minh transaction của poller không tự chuyển sang thread mới.
11. Chạy hai instances cùng gọi procedure, xác minh atomic claim/locking và không có duplicate vượt policy.
12. Mô phỏng crash khi row đã `CLAIMED`; bổ sung `lease_until`, recovery job và idempotency theo `orderId`/`eventId`.
13. Gửi rows đã lấy qua JMS/Kafka, thiết kế outbox và xác định điều kiện ACK/commit để xử lý redelivery.
14. Thay SQL Server bằng một DB khác, viết lại procedure và điều chỉnh JDBC parameter/result mapping theo vendor thật.

**Tình huống thiết kế:** hệ thống ERP chỉ cho phép đọc sự kiện qua stored procedure. Hai instance Spring Integration cùng poll, procedure claim 100 rows rồi một instance chết trước khi gửi sang Kafka. Hãy đề xuất transaction boundary, lease/reclaim, bảng outbox, batch size, deduplication key và metrics để không mất công việc và hạn chế xử lý trùng.

## 19. Tài liệu tham khảo

- [Spring Integration — Stored Procedures](https://docs.spring.io/spring-integration/reference/jdbc/stored-procedures.html): stored procedure inbound adapter, OUT/IN parameters, resultset mapper, `SimpleJdbcCall` và các lựa chọn XML.
- [Spring Integration — Java DSL for JDBC Components (7.x)](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.storedProcInboundAdapter(...)`, `configurerStoredProcExecutor`, `expectSingleResult`, poller.
- [Spring Integration API — JdbcStoredProcInboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcStoredProcInboundChannelAdapterSpec.html): DSL builder từ phiên bản 7.0.
- [Spring Integration API — StoredProcPollingChannelAdapter](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/jdbc/StoredProcPollingChannelAdapter.html): nguồn polling, constructor, `setExpectSingleResult`.
- [Spring Integration API — StoredProcExecutor](https://docs.spring.io/spring-integration/docs/6.3.0-RC1/api/org/springframework/integration/jdbc/StoredProcExecutor.html): `executeStoredProcedure`, parameters, result set mappers.
- [Spring Integration — Inbound Channel Adapters in Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-inbound-adapters.html): `MessageSource`, `IntegrationFlow.from` và `Pollers`.
- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): transaction ở poller, đồng bộ message flow, rollback.
- [Spring Framework — SimpleJdbcCall](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html): JDBC stored procedure/function, metadata và mapping.

> **Ghi nhớ:** JDBC inbound stored procedure adapter là **nguồn message được poller kích hoạt**, sử dụng `StoredProcExecutor` và `SimpleJdbcCall` để gọi procedure/function rồi đưa **result map hoặc list** vào Spring Integration. Hãy phân biệt `maxMessagesPerPoll` với giới hạn hàng của procedure, `expectSingleResult` với số rows, và transaction DB với ACK của Kafka/JMS. Muốn vận hành ổn định cần mapping result rõ ràng, claim nguyên tử, recovery/lease, idempotency và kiểm thử đúng database vendor.
