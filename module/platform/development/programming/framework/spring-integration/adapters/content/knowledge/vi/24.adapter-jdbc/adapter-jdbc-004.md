# JDBC outbound stored procedure adapter trong Spring Integration

## 1. Bài toán: nhận Message và thực thi thủ tục ghi dữ liệu

Một ứng dụng tích hợp nhận sự kiện `order.paid` từ Kafka, JMS, AMQP hoặc HTTP. Thay vì cho ứng dụng tự chạy nhiều câu `INSERT`/`UPDATE` vào schema ERP, phía database chỉ cấp quyền gọi thủ tục `apply_order_status`. Khi nhận một sự kiện, luồng phải lấy thông tin đơn hàng từ `Message<?>`, bind vào các tham số của stored procedure và **thực thi một side effect trong database**.

**JDBC outbound stored procedure adapter** là endpoint một chiều của Spring Integration dùng để làm việc đó. Khi một message đến input `MessageChannel`, adapter gọi stored procedure qua JDBC; nó **không gửi kết quả procedure thành reply message**. Lớp thực thi là `StoredProcMessageHandler` và phần gọi JDBC dùng `StoredProcExecutor`, dựa trên Spring JDBC `SimpleJdbcCall`.

Bài thuộc chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, với các nguồn/đích như file, SFTP, HTTP, JMS, AMQP, Kafka và database. Bên cạnh cú pháp cấu hình, điều quan trọng là ranh giới **message → tham số procedure → transaction**, khả năng xử lý lỗi và vòng đời kết nối.

~~~mermaid
flowchart LR
    A["Kafka / JMS / HTTP / File"] --> B["Validate + transform"]
    B --> C["Message<ChangeStatus>"]
    C --> D["orderStatusCommands"]
    D --> E["StoredProcMessageHandler"]
    E --> F["StoredProcExecutor"]
    F --> G["SimpleJdbcCall / JDBC"]
    G -->|"EXEC procedure"| H[("Relational DB")]
    G -.->|"SQL/transaction error"| I["Error handling / retry / DLQ"]
~~~

**Outbound** nghĩa là gọi **ra database** từ message flow, không phải gọi HTTP ra bên ngoài. **Channel adapter** nghĩa là một chiều: giá trị `RETURN`, `OUT` hay `ResultSet` của procedure có thể được JDBC đọc bên trong, nhưng `StoredProcMessageHandler` **bỏ qua chúng** trong hợp đồng messaging. Nếu downstream cần dựa trên kết quả đó, hãy chọn **stored procedure outbound gateway**.

## 2. So sánh bốn lựa chọn JDBC/stored procedure

| Thành phần | Ai kích hoạt? | Hành vi chính | Reply cho flow? |
|---|---|---|---|
| JDBC inbound channel adapter | Poller | `SELECT` đọc các hàng, phát message | Không phải request-reply |
| Stored procedure inbound channel adapter | Poller | Gọi procedure/function theo lịch, phát kết quả | Không phải request-reply |
| **Stored procedure outbound channel adapter** | **Message đến input channel** | **Gọi procedure để thay đổi dữ liệu** | **Không** |
| Stored procedure outbound gateway | Message đến request channel | Gọi procedure và đưa OUT/return/result set về flow | **Có** |
| JDBC outbound DML adapter | Message đến input channel | Chạy `INSERT`, `UPDATE`, `DELETE` trực tiếp | Không |

Chọn outbound stored procedure adapter khi ứng dụng **không cần đọc kết quả** để quyết định bước tiếp theo, hoặc thành công được định nghĩa là **procedure hoàn tất không có lỗi trong transaction phù hợp**. Nếu nghiệp vụ đòi biết số hàng cập nhật, mã lỗi domain trong `OUT`, ID được sinh hoặc result set để route message, không nên cố trông chờ adapter trả reply.

**Stored procedure và SQL function khác nhau:** `StoredProcMessageHandler` được thiết kế để **gọi procedures cho mục đích cập nhật**. Theo API Spring Integration, handler này **không hỗ trợ gọi SQL function**; khi cần function hoặc xử lý output parameters có ý nghĩa nghiệp vụ, dùng `StoredProcOutboundGateway`.

## 3. Luồng xử lý một message

~~~mermaid
sequenceDiagram
    participant Producer as Message producer
    participant Ch as DirectChannel
    participant Handler as StoredProcMessageHandler
    participant Exec as StoredProcExecutor
    participant DB as Database
    Producer->>Ch: send(Message<ChangeStatus>)
    Ch->>Handler: handleMessage
    Handler->>Exec: executeStoredProcedure(message)
    Exec->>DB: CALL procedure(IN parameters)
    alt Procedure chạy thành công
        DB-->>Exec: Complete / OUT data (nếu có)
        Exec-->>Handler: Result map
        Note over Handler: Adapter bỏ qua result map, không tạo reply
        Handler-->>Ch: Return
        Ch-->>Producer: send() returns
    else JDBC hoặc procedure lỗi
        DB-->>Exec: SQLException
        Exec-->>Handler: DataAccessException hoặc exception liên quan
        Handler-->>Producer: Exception theo cơ chế channel
    end
~~~

Trình tự trên minh họa `DirectChannel`, vốn dispatch đồng bộ trong thread của sender. Với `ExecutorChannel` hoặc `QueueChannel` và poller, việc xử lý diễn ra ở worker/thread hoặc thời điểm khác; `send()` thành công **không bảo đảm** database đã commit. Ngay cả với `DirectChannel`, một **transaction bao ngoài** có thể chỉ commit sau khi `send()` trả về.

## 4. Ví dụ xuyên suốt trên SQL Server: áp dụng trạng thái đơn hàng

Ví dụ sử dụng **Microsoft SQL Server** để việc tạo procedure có cú pháp cụ thể và kiểm thử được trên một DB thật. PostgreSQL, Oracle, MySQL và các hệ khác hỗ trợ stored procedure với cú pháp/driver khác; **không** chạy nguyên đoạn T-SQL dưới đây trên H2 hoặc PostgreSQL.

### 4.1. Tạo bảng nghiệp vụ và bảng chống xử lý trùng

~~~sql
CREATE TABLE dbo.order_state (
    order_id      VARCHAR(64) NOT NULL PRIMARY KEY,
    status        VARCHAR(32) NOT NULL,
    updated_at    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE dbo.processed_order_event (
    event_id      VARCHAR(64) NOT NULL PRIMARY KEY,
    order_id      VARCHAR(64) NOT NULL,
    new_status    VARCHAR(32) NOT NULL,
    processed_at  DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

INSERT INTO dbo.order_state (order_id, status)
VALUES ('ORD-1001', 'RECEIVED');
GO
~~~

`processed_order_event.event_id` dùng làm **idempotency key**: cùng một event được broker gửi lại có thể được nhận diện. Một event ID tái sử dụng với dữ liệu khác phải báo conflict, **không** được coi là duplicate thành công.

### 4.2. Procedure cập nhật cùng giao dịch với idempotency record

~~~sql
CREATE OR ALTER PROCEDURE dbo.apply_order_status
    @order_id    VARCHAR(64),
    @new_status  VARCHAR(32),
    @event_id    VARCHAR(64)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        DECLARE @old_order_id VARCHAR(64);
        DECLARE @old_status   VARCHAR(32);

        SELECT
            @old_order_id = order_id,
            @old_status = new_status
        FROM dbo.processed_order_event WITH (UPDLOCK, HOLDLOCK)
        WHERE event_id = @event_id;

        IF @old_order_id IS NOT NULL
        BEGIN
            IF @old_order_id <> @order_id OR @old_status <> @new_status
                THROW 51001, 'event_id reused with different data', 1;

            -- Cùng event + cùng dữ liệu: không ghi trạng thái lần nữa.
            COMMIT TRANSACTION;
            RETURN;
        END;

        UPDATE dbo.order_state
        SET status = @new_status,
            updated_at = SYSUTCDATETIME()
        WHERE order_id = @order_id;

        IF @@ROWCOUNT <> 1
            THROW 51002, 'Order not found', 1;

        INSERT INTO dbo.processed_order_event (
            event_id, order_id, new_status
        ) VALUES (
            @event_id, @order_id, @new_status
        );

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO
~~~

**Điều procedure này bảo đảm trong phạm vi ví dụ:** cập nhật `order_state` và ghi `processed_order_event` trong cùng transaction DB; nhận lại đúng `event_id` + dữ liệu sẽ không cập nhật lại. Khóa chính cùng `UPDLOCK, HOLDLOCK` nhằm phối hợp các yêu cầu tranh cùng key.

**Điều chưa bảo đảm:** trạng thái `PAID` đến sau `SHIPPED` vẫn có thể làm đơn quay lùi nếu hai event IDs khác nhau. Production cần kiểm tra **chuyển trạng thái hợp lệ, thứ tự/version và quyền của nguồn sự kiện**. Tùy cách gọi, procedure có transaction nội bộ và có thể tham gia một outer Spring JDBC transaction: semantics nested transaction/rollback phụ thuộc DB và cần kiểm thử.

Một lần gọi thủ công bằng SQL Server client:

~~~sql
EXEC dbo.apply_order_status
    @order_id = 'ORD-1001',
    @new_status = 'PAID',
    @event_id = 'evt-order-1001-paid-v1';

SELECT * FROM dbo.order_state WHERE order_id = 'ORD-1001';
SELECT * FROM dbo.processed_order_event
WHERE event_id = 'evt-order-1001-paid-v1';
~~~

Kỳ vọng `order_state.status = 'PAID'` và **một** dòng `processed_order_event`. Gọi lại `EXEC` với đúng bộ tham số không tạo bản ghi thứ hai. Nếu đổi `@new_status` nhưng giữ `@event_id`, procedure ném lỗi.

## 5. Dependency và cấu hình DataSource

Với Spring Boot và Spring Integration JDBC:

~~~groovy
// build.gradle - phần dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'
    runtimeOnly 'com.microsoft.sqlserver:mssql-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Không khai báo phiên bản tùy ý cho từng thư viện khi Spring Boot BOM đã quản lý; tránh trộn Spring Framework/Spring Integration không tương thích.

~~~yaml
# application.yml minh họa; môi trường thật dùng secret manager
spring:
  datasource:
    url: "jdbc:sqlserver://db.internal.example:1433;databaseName=integration;encrypt=true"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
~~~

Đây là địa chỉ giả lập, không phải database có thể truy cập ngay. Cần SQL Server test, schema và quyền `EXECUTE` trên procedure. Với kết nối thật, cấu hình **TLS certificate trust/hostname validation** đúng môi trường; không tắt xác thực chứng chỉ để tránh lỗi.

### 5.1. Lưu ý API giữa Spring Integration 6.x và 7.x

| Phiên bản | Cách triển khai phù hợp |
|---|---|
| **7.0 trở lên** | Java DSL `Jdbc.storedProcOutboundAdapter(dataSource)`, `JdbcStoredProcOutboundChannelAdapterSpec` và `StoredProcExecutorSpec` |
| **6.x** | `StoredProcExecutor` + `StoredProcMessageHandler` gắn vào `@ServiceActivator` hoặc XML namespace |
| **7.x dựng thủ công** | `StoredProcMessageHandler` nằm trong `org.springframework.integration.jdbc.outbound` |
| **6.x dựng thủ công** | `StoredProcMessageHandler` nằm trong `org.springframework.integration.jdbc` |

Factory Java DSL JDBC module xuất hiện từ **7.0**. Vì vậy, các ví dụ mục 6 dùng 7.x; mục 8 minh họa cách dùng 6.x. Không copy import từ hai phiên bản vào chung một class.

## 6. Java DSL 7.x: cấu hình outbound stored procedure adapter

### 6.1. Định nghĩa payload và channel

~~~java
package com.example.orders;

public record ChangeStatus(String orderId, String newStatus) {
}
~~~

Trong flow, `eventId` được đặt ở **message header** và là khóa idempotency. Ví dụ cố ý tách business payload với metadata của delivery.

### 6.2. Cấu hình IntegrationFlow

~~~java
package com.example.orders;

import java.sql.Types;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.integration.jdbc.storedproc.ProcedureParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderStatusProcedureFlow {

    @Bean
    public MessageChannel orderStatusCommands() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow callStatusProcedure(
            DataSource dataSource,
            @Qualifier("orderStatusCommands") MessageChannel commands) {

        return IntegrationFlow.from(commands)
            .handle(Jdbc.storedProcOutboundAdapter(dataSource)
                .configurerStoredProcExecutor(executor -> executor
                    .storedProcedureName("apply_order_status")
                    .ignoreColumnMetaData(true)
                    .sqlParameter(new SqlParameter(
                        "order_id", Types.VARCHAR))
                    .sqlParameter(new SqlParameter(
                        "new_status", Types.VARCHAR))
                    .sqlParameter(new SqlParameter(
                        "event_id", Types.VARCHAR))
                    .procedureParameter(new ProcedureParameter(
                        "order_id", null, "payload.orderId"))
                    .procedureParameter(new ProcedureParameter(
                        "new_status", null, "payload.newStatus"))
                    .procedureParameter(new ProcedureParameter(
                        "event_id", null, "headers['eventId']"))))
            .get();
    }
}
~~~

**Giải thích:**

1. `IntegrationFlow.from(commands)` tạo flow kích hoạt bởi message gửi vào `DirectChannel`; đây **không phải** inbound poller.
2. `Jdbc.storedProcOutboundAdapter(dataSource)` tạo endpoint dựa trên `StoredProcMessageHandler`; nó thực hiện procedure **một chiều**.
3. `configurerStoredProcExecutor(...)` cấu hình `StoredProcExecutor` qua DSL spec. Tên procedure được định nghĩa **cố định**, không lấy từ input không tin cậy.
4. `ignoreColumnMetaData(true)` tắt tự phát hiện parameter metadata từ JDBC. Vì vậy ví dụ khai báo đầy đủ `SqlParameter` với tên và kiểu SQL.
5. `ProcedureParameter(name, null, expression)` định nghĩa tham số lấy bằng **SpEL**, không phải giá trị tĩnh. Với adapter outbound, SpEL có thể truy cập **toàn bộ message**.
6. `payload.orderId` và `payload.newStatus` lấy từ Java record; `headers['eventId']` lấy từ header nguồn. Cả ba được bind làm **giá trị SQL**, không nối thành chuỗi SQL.
7. Không có `.channel("reply")` sau adapter: `StoredProcMessageHandler` bỏ qua return map; không phát `OUT`/result set thành reply message.

Về schema SQL Server, `apply_order_status` có tên đầy đủ `dbo.apply_order_status`. Ví dụ Java dùng tên ngắn và giả định tài khoản JDBC resolve đúng schema; nếu không, cần cấu hình schema/default schema tương thích với `SimpleJdbcCall`, hoặc triển khai procedure trong schema thích hợp. Kiểm thử với SQL Server thực tế để tránh lỗi “Could not find stored procedure”.

### 6.3. Gửi message

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class OrderStatusPublisher {

    private final MessageChannel commands;

    public OrderStatusPublisher(
            @Qualifier("orderStatusCommands") MessageChannel commands) {
        this.commands = commands;
    }

    public void markPaid(String orderId, String eventId) {
        boolean accepted = commands.send(
            MessageBuilder
                .withPayload(new ChangeStatus(orderId, "PAID"))
                .setHeader("eventId", eventId)
                .build());
        if (!accepted) {
            throw new IllegalStateException(
                "orderStatusCommands did not accept the message");
        }
    }
}
~~~

Gọi:

~~~java
publisher.markPaid("ORD-1001", "evt-order-1001-paid-v1");
~~~

Khi `DirectChannel` dùng một synchronous handler và không có transaction bao ngoài, lỗi JDBC thường truyền về thread gọi `send()`; đồng thời `send() == true` chỉ cho biết handler không báo thất bại theo hợp đồng dispatch, **không phải một receipt có nội dung OUT parameter**. Nếu có transaction bao ngoài, commit có thể xảy ra sau đó.

## 7. Parameter binding: mặc định, SpEL và SqlParameterSourceFactory

Các stored procedure components dùng `StoredProcExecutor` và Spring JDBC `SimpleJdbcCall`. Parameter values có thể được ánh xạ tự động từ payload hoặc khai báo tường minh.

| Cơ chế | Nguồn dữ liệu | Khi nào dùng |
|---|---|---|
| **Mặc định**, không khai báo `ProcedureParameter` | Bean properties của payload, hoặc map keys theo hỗ trợ phiên bản | Procedure đơn giản, tên input khớp rõ ràng |
| `ProcedureParameter` với `value` | Giá trị tĩnh cố định | Tenant/kênh thực thi có giá trị cấu hình cố định |
| `ProcedureParameter` với `expression` | SpEL truy cập payload, headers, thông tin message | Tên field không khớp, cần correlation/event ID |
| `SqlParameter`/`SqlOutParameter` | Khai báo kiểu SQL và chiều IN/OUT | JDBC metadata không đáng tin hoặc phức tạp |
| `SqlParameterSourceFactory` custom | Quy tắc ánh xạ tùy biến | Chuyển đổi dữ liệu/kiểu đặc biệt, có kiểm thử |

### 7.1. Mặc định không phải luôn dùng SpEL

Khi **không** cung cấp `ProcedureParameter`, `StoredProcExecutor` mặc định dùng `BeanPropertySqlParameterSourceFactory` với **payload** làm parameter source. Nếu tên bean property khớp tên procedure parameter trong metadata, cấu hình có thể chỉ cần tên procedure.

Tài liệu Spring Integration cảnh báo việc Spring JDBC `CallMetaDataContext` có thể chuyển tên parameter sang chữ thường khi match. Do đó bean property kiểu camelCase như `lastName` có thể không được tìm đúng. Nếu gặp trường hợp này, dùng **`ProcedureParameter` tường minh** với SpEL hoặc một mapping được kiểm thử, thay vì suy rằng mọi field DTO tự khớp.

Khi có `ProcedureParameter` tường minh, mặc định executor dùng **toàn bộ `Message`** làm nguồn biểu thức, giúp truy cập cả `payload` lẫn `headers`. Khi không khai báo, mặc định là **payload**. Sự khác biệt này là lý do đoạn DSL mục 6 dùng `headers['eventId']`.

### 7.2. Ví dụ tham số tĩnh và biểu thức

~~~java
// Mảnh DSL trong configurerStoredProcExecutor:
.procedureParameter(
    new ProcedureParameter("source_system", "SPRING_INTEGRATION", null))
.procedureParameter(
    new ProcedureParameter("order_id", null, "payload.orderId"))
.procedureParameter(
    new ProcedureParameter("event_id", null, "headers['eventId']"))
~~~

Chú ý: trong ví dụ chính, procedure **không có** tham số `source_system`, nên đoạn này chỉ minh họa cú pháp. Muốn dùng thật phải thêm parameter tương ứng vào procedure và khai báo `SqlParameter` khi đã bật `ignoreColumnMetaData(true)`.

### 7.3. OUT/INOUT và result set

Stored procedure có thể có `IN`, `OUT`, `INOUT`, return code và result sets. Tên/kiểu/chiều tham số phải khớp driver và database. Có thể khai báo `SqlOutParameter`/`SqlInOutParameter` và result-set `RowMapper` ở `StoredProcExecutor`.

**Nhưng với outbound channel adapter, các kết quả vẫn bị `StoredProcMessageHandler` bỏ qua.** Nếu bạn cần giá trị OUT để quyết định transaction nghiệp vụ, gửi reply hoặc ghi sang hệ thống khác, **dùng outbound gateway**. Không cố thêm `.channel("results")` sau adapter để nhận một map mà endpoint không phát.

### 7.4. Tránh chọn procedure name từ message không tin cậy

`StoredProcExecutor` hỗ trợ tên routine động qua SpEL và cache `SimpleJdbcCall` theo tên. Đây là tính năng hữu ích cho router tin cậy, nhưng **không phải SQL parameter binding**: việc chọn tên routine có thể làm ứng dụng gọi sai stored procedure hoặc mở rộng quyền DB không chủ ý.

Ưu tiên danh sách procedure cố định, ánh xạ business command type tới tên đã duyệt, tài khoản DB có quyền `EXECUTE` tối thiểu và giới hạn kích thước cache. Không lấy thẳng `headers['procedureName']` từ webhook.

## 8. Spring Integration 6.x: StoredProcExecutor và StoredProcMessageHandler

Ở 6.x, Java DSL factory `Jdbc.storedProcOutboundAdapter(...)` của 7.x **chưa có**. Có thể tạo một `StoredProcExecutor` và gắn `StoredProcMessageHandler` với `@ServiceActivator`.

~~~java
package com.example.orders;

import java.sql.Types;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.jdbc.StoredProcExecutor;
import org.springframework.integration.jdbc.StoredProcMessageHandler;
import org.springframework.integration.jdbc.storedproc.ProcedureParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.messaging.MessageHandler;

@Configuration
public class LegacyProcedureAdapterConfiguration {

    @Bean
    public StoredProcExecutor statusExecutor6(DataSource dataSource) {
        StoredProcExecutor executor = new StoredProcExecutor(dataSource);
        executor.setStoredProcedureName("apply_order_status");
        executor.setIgnoreColumnMetaData(true);
        executor.setSqlParameters(List.of(
            new SqlParameter("order_id", Types.VARCHAR),
            new SqlParameter("new_status", Types.VARCHAR),
            new SqlParameter("event_id", Types.VARCHAR)));
        executor.setProcedureParameters(List.of(
            new ProcedureParameter("order_id", null, "payload.orderId"),
            new ProcedureParameter("new_status", null, "payload.newStatus"),
            new ProcedureParameter("event_id", null, "headers['eventId']")));
        return executor;
    }

    @Bean
    @ServiceActivator(inputChannel = "legacyStatusCommands")
    public MessageHandler statusHandler6(StoredProcExecutor statusExecutor6) {
        return new StoredProcMessageHandler(statusExecutor6);
    }
}
~~~

Trong cấu hình này, `StoredProcExecutor` là Spring bean nên container quản lý khởi tạo, bao gồm callback lifecycle `afterPropertiesSet()`. Không cần tự gọi callback ấy trong đoạn cấu hình; trong các phép thử tự tạo object **ngoài** Spring container mới phải chủ động bảo đảm khởi tạo đầy đủ.

**Dự án 7.x:** nếu dựng thủ công thay vì DSL, package của `StoredProcMessageHandler` là `org.springframework.integration.jdbc.outbound`, không phải `org.springframework.integration.jdbc` như 6.x. Luôn dùng import đúng với dependency đang chạy.

### 8.1. XML configuration là một lựa chọn khác

~~~xml
<!-- Fragment, cần khai báo namespace int và int-jdbc ở Spring XML. -->
<int:channel id="xmlStatusCommands"/>

<int-jdbc:stored-proc-outbound-channel-adapter
    id="orderStatusProcedureAdapter"
    data-source="dataSource"
    channel="xmlStatusCommands"
    stored-procedure-name="apply_order_status"
    ignore-column-meta-data="true">

    <int-jdbc:sql-parameter-definition
        name="order_id" direction="IN" type="VARCHAR"/>
    <int-jdbc:sql-parameter-definition
        name="new_status" direction="IN" type="VARCHAR"/>
    <int-jdbc:sql-parameter-definition
        name="event_id" direction="IN" type="VARCHAR"/>

    <int-jdbc:parameter name="order_id"
        expression="payload.orderId"/>
    <int-jdbc:parameter name="new_status"
        expression="payload.newStatus"/>
    <int-jdbc:parameter name="event_id"
        expression="headers['eventId']"/>
</int-jdbc:stored-proc-outbound-channel-adapter>
~~~

Đây là **phương án thay thế** cho Java DSL và Java bean 6.x, không phải cấu hình cần bật đồng thời. Nếu cả ba endpoint cùng nghe một message qua các channel khác nhau, bạn có thể gọi procedure nhiều lần.

**Poller trong XML:** khi endpoint nhận từ `SubscribableChannel` như `DirectChannel`, nó là consumer hướng sự kiện và không cần poller. Nếu nhận từ `PollableChannel` như `QueueChannel`, framework dùng `PollingConsumer` và cần khai báo poller phù hợp. Tên “outbound adapter” **không** có nghĩa nó chủ động poll database.

## 9. Channel quyết định thread, transaction và lỗi

| Input channel | Cách handler nhận message | Hệ quả đối với transaction và độ trễ |
|---|---|---|
| `DirectChannel` | Subscriber chạy đồng bộ trong caller thread | Có thể tham gia Spring transaction hiện tại của sender |
| `ExecutorChannel` | Submit vào task executor | Thread khác; không tự mang transaction thread-bound của sender |
| `QueueChannel` + poller | Message vào queue, sau đó polling consumer lấy | Cần transaction cho poller/handler, ranh giới ACK rõ ràng |
| Broker inbound adapter → channel | Theo listener container/adapter của broker | Phải thiết kế thời điểm ACK/offset commit và xử lý redelivery |

~~~mermaid
flowchart TD
    A["Message producer"] --> B{"Channel type"}
    B -->|"DirectChannel"| C["Same thread: handler JDBC"]
    B -->|"ExecutorChannel"| D["Worker thread: handler JDBC"]
    B -->|"QueueChannel"| E["Poller thread: handler JDBC"]
    C --> F["Transaction có thể chia sẻ với caller"]
    D --> G["Transaction boundary khác"]
    E --> G
~~~

**JDBC là blocking I/O.** Một ứng dụng có WebFlux endpoint không nên gọi stored procedure JDBC trực tiếp trên Reactor Netty event loop rồi tự cho rằng đoạn đó non-blocking. Nếu cần từ HTTP reactive, dùng bounded worker/executor có kiểm soát, hoặc thiết kế gửi message vào broker/queue và trả `202 Accepted` theo hợp đồng. Đổi scheduler không biến JDBC thành R2DBC; database vẫn cần connection pool và transaction.

## 10. Transaction: một lời gọi thành công có nghĩa gì?

### 10.1. DirectChannel và Spring transaction

Ví dụ một service đang có `@Transactional`:

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderStatusCommandService {

    private final MessageChannel commands;

    public OrderStatusCommandService(
            @Qualifier("orderStatusCommands") MessageChannel commands) {
        this.commands = commands;
    }

    @Transactional
    public void acceptStatus(
            String orderId, String newStatus, String eventId) {

        boolean sent = commands.send(
            MessageBuilder
                .withPayload(new ChangeStatus(orderId, newStatus))
                .setHeader("eventId", eventId)
                .build());

        if (!sent) {
            throw new IllegalStateException("No subscriber");
        }
        // Commit của outer transaction sau khi method hoàn tất.
    }
}
~~~

Với `DirectChannel`, không có async boundary và cùng `DataSourceTransactionManager`, JDBC call có thể tham gia Spring transaction của caller. **`@Transactional` chỉ có tác dụng nếu phương thức đi qua Spring proxy/transaction interceptor**. Nếu procedure cũng tự `BEGIN TRANSACTION/COMMIT` như ví dụ SQL Server, cách transaction lồng nhau tương tác với Spring transaction cần được kiểm thử; không mặc định “procedure commit” luôn độc lập với outer transaction.

Khi sender gọi `send()` thành công, điều đó **không tự chứng minh transaction bao ngoài đã commit**. Nếu code phía sau ném lỗi dẫn tới rollback, DB update có thể bị rollback theo semantics thực tế.

### 10.2. Executor/Queue và nguồn Kafka/JMS

Khi đổi sang `ExecutorChannel` hoặc `QueueChannel`, transaction hiện hành của producer thường không tự chuyển qua worker thread. Với listener Kafka/JMS, phải quyết định mốc ACK/commit:

- ACK **trước** khi JDBC commit: ứng dụng có thể mất công việc nếu crash.
- ACK **sau** khi JDBC commit: message có thể bị gửi lại nếu crash trước ACK.
- Với redelivery, procedure/idempotency record giúp lệnh lặp lại không gây side effect trùng.

Một JDBC transaction cục bộ **không** tự tạo transaction nguyên tử với Kafka, JMS, SFTP hoặc HTTP. Nếu cần phát event sau khi DB commit, cân nhắc transactional outbox; vẫn phải xử lý khả năng publisher gửi trùng.

## 11. OUT parameters, return values và khi nào cần gateway

`StoredProcExecutor.executeStoredProcedure(message)` có thể trả `Map<String, Object>` gồm `OUT`, return code và result sets. Nhưng `StoredProcMessageHandler.handleMessageInternal(...)` thực thi procedure rồi **bỏ qua các return values**, chỉ có thể ghi log debug.

Ví dụ procedure muốn trả mã nghiệp vụ:

~~~sql
-- Ý tưởng mở rộng SQL Server, không thay thế procedure mục 4:
CREATE OR ALTER PROCEDURE dbo.check_order_state
    @order_id VARCHAR(64),
    @current_status VARCHAR(32) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT @current_status = status
    FROM dbo.order_state
    WHERE order_id = @order_id;
END;
GO
~~~

Với adapter một chiều, `@current_status` **không trở thành một reply message**. Để handler sau có thể route theo `current_status`, nên chọn **stored procedure outbound gateway** và khai báo `SqlOutParameter` tương ứng:

~~~java
// Spring Integration 7.x - mảnh cấu hình minh họa gateway
.handle(Jdbc.storedProcOutboundGateway(dataSource)
    .configurerStoredProcExecutor(executor -> executor
        .storedProcedureName("check_order_state")
        .ignoreColumnMetaData(true)
        .sqlParameter(new SqlParameter("order_id", Types.VARCHAR))
        .sqlParameter(new SqlOutParameter(
            "current_status", Types.VARCHAR))
        .procedureParameter(new ProcedureParameter(
            "order_id", null, "payload.orderId"))))
~~~

Đây là mảnh DSL; trong file Java thực cần imports cho `Jdbc`, `SqlParameter`, `SqlOutParameter`, `ProcedureParameter`, `Types` và các lớp flow. Gateway có hợp đồng reply, còn **hình dạng payload** có thể là map hay một phần tử tùy cấu hình gateway/executor và database. Hãy kiểm tra bằng integration test trước khi ép kiểu.

**Tương tự, SQL functions:** `StoredProcMessageHandler` không gọi function; hãy dùng stored procedure outbound gateway nếu muốn gọi function/nhận return value. Không chỉ bật `isFunction(true)` trên outbound adapter rồi kỳ vọng chạy được.

## 12. Lỗi SQL, retry và idempotency

Spring JDBC thường chuyển `SQLException` thành các subtype của `DataAccessException`; Spring Integration có thể bọc lỗi thêm tùy endpoint/channel. Các nhóm lỗi không có cùng chính sách xử lý:

| Nhóm | Ví dụ | Retry? | Hành động |
|---|---|---|---|
| Mất kết nối tạm thời | Network, connection pool/DB outage | Có điều kiện | Backoff, giới hạn, theo dõi và retry toàn đơn vị giao dịch |
| Deadlock/serialization | Transient concurrency failure | Có điều kiện | Rollback rồi retry toàn transaction |
| Procedure thiếu/quyền EXECUTE sai | Invalid object, permission denied | Không | Sửa migration/quyền/cấu hình |
| Tên/kiểu tham số không khớp | Metadata, conversion failure | Không | Sửa contract SQL/DTO |
| Dùng lại event ID với dữ liệu khác | Procedure `THROW 51001` | Không | Conflict; ghi nhận để điều tra |
| Không tìm thấy order | Procedure `THROW 51002` | Theo nghiệp vụ, thường không | Báo not-found hoặc chuyển DLQ |
| Query/lock timeout | JDBC timeout hoặc driver exception | Có điều kiện | Rà soát DB và transaction, xác định outcome |
| Duplicate event đúng dữ liệu | Procedure trả bình thường | Không cần retry | Idempotency success theo hợp đồng |

**Một lỗi kết nối hoặc timeout không chứng minh DB chưa commit.** Ví dụ client mất kết nối sau khi procedure đã commit nhưng trước khi nhận phản hồi. Khi gửi lại cùng `eventId`, procedure phải xác định duplicate một cách ổn định. Nếu không có bảng idempotency, retry có thể làm cập nhật trạng thái sai, tăng số lượng hoặc ghi audit trùng.

### 12.1. Tránh retry trong nhiều tầng

Một hệ thống có thể retry tại:

1. JDBC advice/service layer.
2. Listener Kafka/JMS hoặc poller.
3. Scheduler replay outbox/DLQ.
4. Client bên ngoài gửi lại cùng business command.

Nếu mỗi tầng thử lại nhiều lần, tổng số lần gọi procedure có thể tăng rất mạnh. Chọn ranh giới retry rõ, giới hạn attempts, backoff/jitter và kết thúc bằng dead-letter/reconciliation. Một `DuplicateKeyException` hoặc lỗi tham số cố định không được retry vô hạn.

### 12.2. Không nuốt exception rồi ACK nhầm

~~~java
// Không nên: dữ liệu có thể chưa lưu mà upstream vẫn coi như thành công.
try {
    commands.send(message);
} catch (Exception error) {
    log.warn("DB error ignored", error);
}

// Hướng đúng: phân loại lỗi, cho retry/DLQ đúng hợp đồng.
// Chỉ ACK nguồn sau khi outcome được lưu/đối soát phù hợp.
~~~

Code là mảnh minh họa; `commands`, `message`, `log` phải được cung cấp trong ứng dụng thực. Với asynchronous channel, caller còn có thể **không nhận exception ngay lúc `send`**, nên error flow phải gắn với worker/endpoint đúng chỗ.

## 13. Bảo mật stored procedure và ranh giới tin cậy

1. **Least privilege:** cấp quyền `EXECUTE` đúng routine, không cấp quyền DDL hoặc quyền đọc/ghi mọi bảng khi không cần.
2. **Tham số hóa:** bind các giá trị bằng `ProcedureParameter`/JDBC, không ghép input trực tiếp vào SQL trong procedure. Dynamic SQL nội bộ cũng phải parameterize và kiểm tra allowlist.
3. **Routine name cố định:** không để message header không đáng tin chọn procedure; nếu cần dynamic routing, ánh xạ qua danh sách định nghĩa sẵn.
4. **Data validation:** kiểm tra `orderId`, `newStatus` và `eventId` trước khi gọi; procedure cũng kiểm tra trạng thái/trùng lặp ở DB.
5. **Tenant authorization:** header `tenantId` do client gửi không tự chứng minh người gửi được quyền cập nhật tenant đó.
6. **Credential/TLS:** dùng secret manager và xác minh certificate DB; tránh log JDBC URL chứa mật khẩu hoặc bind parameters nhạy cảm.
7. **Error sanitization:** lỗi SQL có thể chứa tên bảng/schema, constraint hoặc dữ liệu; không trả nguyên stack trace về HTTP public API.

## 14. Hiệu năng: pool, locks và điều phối tải

Mỗi stored procedure call dùng một connection thuộc `DataSource` pool. Procedure có transaction và locks, nên một slow procedure có thể chiếm connection lâu và gây backlog trong Kafka/JMS/queue.

| Chỉ số | Điều cho biết |
|---|---|
| JDBC pool active/idle/pending | Có thiếu connection không |
| Thời gian gọi procedure p50/p95/p99 | Database và logic procedure có bị chậm không |
| Lock wait, deadlock, transaction duration | Mức độ contention và nguy cơ rollback |
| Message ingress/processing rate | Nguồn đến nhanh hơn khả năng ghi không |
| Queue depth, listener lag, redelivery | Backlog và khả năng phục hồi |
| Unique/idempotent duplicates | Có retry/duplicate nhiều không |
| Failed messages / DLQ / pending outbox | Công việc cần đối soát hoặc retry bền vững |

**Đừng tăng concurrency vô hạn** chỉ để cải thiện throughput. Nếu procedure update một bảng nóng, nhiều threads sẽ tranh locks và giảm hiệu năng. Cần đo throughput, giới hạn executor/queue, tối ưu index và transaction length, chọn batch/chunk nếu phù hợp với hợp đồng DB.

### 14.1. DataSource connection timeout khác query timeout

Chờ lấy connection từ pool khác với thời gian thực thi `CallableStatement` và chờ locks tại database. Cần cấu hình timeout ở từng tầng và có deadline nghiệp vụ hợp lý. Một exception do timeout không tự xác nhận transaction rollback nếu connection bị mất ở thời điểm outcome không rõ.

### 14.2. Procedure name cache

`StoredProcExecutor` có cache `SimpleJdbcCallOperations` theo procedure name; mặc định giới hạn số instance trong cache và có thể cấu hình `jdbcCallOperationsCacheSize`. Nếu dùng routine name động, cần kiểm soát số tên khác nhau để tránh tăng resource và tăng nguy cơ gọi routine ngoài ý muốn. Với một procedure cố định như ví dụ, cấu hình đơn giản hơn và dễ quan sát hơn.

## 15. Kiểm thử end-to-end với database thật

H2 hoặc mock JDBC không luôn tái hiện đúng `CallableStatement`, metadata, OUT parameters, locks và SQL Server `THROW`. Với ví dụ T-SQL, nên dùng **SQL Server test instance hoặc Testcontainers SQL Server** (tuân thủ cấu hình/licensing của môi trường), không suy diễn từ H2.

### 15.1. Integration test cho stored procedure side effect

Giả sử ứng dụng test đã khởi tạo schema/procedure và cấu hình các bean của mục 6:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class StoredProcedureAdapterTest {

    @Autowired
    @Qualifier("orderStatusCommands")
    MessageChannel commands;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void appliesEventOnlyOnce() {
        String orderId = "ORD-" + UUID.randomUUID();
        String eventId = "evt-" + UUID.randomUUID();

        jdbc.update(
            "INSERT INTO dbo.order_state (order_id, status) "
                + "VALUES (?, ?)",
            orderId, "RECEIVED");

        var message = MessageBuilder
            .withPayload(new ChangeStatus(orderId, "PAID"))
            .setHeader("eventId", eventId)
            .build();

        commands.send(message);
        commands.send(message); // Duplicate delivery có cùng eventId.

        String actual = jdbc.queryForObject(
            "SELECT status FROM dbo.order_state WHERE order_id = ?",
            String.class, orderId);
        Integer processed = jdbc.queryForObject(
            "SELECT COUNT(*) FROM dbo.processed_order_event "
                + "WHERE event_id = ?",
            Integer.class, eventId);

        assertEquals("PAID", actual);
        assertEquals(1, processed);
    }
}
~~~

Test dựa trên **`DirectChannel` đồng bộ** và không có test-level `@Transactional` rollback; nếu đổi sang `ExecutorChannel`/`QueueChannel`, phải chờ kết quả bất đồng bộ bằng cơ chế kiểm thử phù hợp trước khi query DB. Test này kiểm tra side effect **đã commit theo cấu hình test**, không phải kiểm chứng sự tồn tại của một reply message — outbound adapter không có reply.

### 15.2. Ma trận kiểm thử

| Tình huống | Điều cần xác nhận |
|---|---|
| Event hợp lệ | Status DB cập nhật, một event record |
| Gửi lại cùng eventId và payload | Không nhân đôi effect |
| Cùng eventId, payload khác | Procedure báo conflict |
| Order không tồn tại | Procedure lỗi, transaction rollback |
| Wrong parameter name/type | Metadata/binding exception, không âm thầm bỏ qua |
| Stored procedure không tồn tại | Lỗi cấu hình, không retry vô hạn |
| DB mất kết nối | Error flow, retry có giới hạn và không ACK sai |
| Crash sau DB commit trước broker ACK | Redelivery không tạo side effect trùng |
| DirectChannel → ExecutorChannel | Ranh giới thread, transaction và kiểm thử timing thay đổi |
| Stored procedure trả OUT/result set | Adapter không phát reply |
| Gateway nhận OUT/result set | Reply payload đúng contract/gateway |
| Nhiều event đến sai thứ tự | Business version/state transition không bị ghi lùi |

### 15.3. Kiểm thử các tình huống transaction phức tạp

Trong sản xuất, thử cả trường hợp Spring `@Transactional` bao lời gọi adapter và procedure tự dùng `BEGIN TRANSACTION`. Với SQL Server, commit/rollback nested transaction có semantics riêng; không nên kết luận chỉ bằng việc thấy lệnh `COMMIT` trong procedure. Thử lỗi sau `send()`, rollback ngoài, lock timeout và mất kết nối sát thời điểm commit để xác định **outcome không chắc chắn** và cách đối soát.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Outbound stored procedure adapter tự poll database” | Nó **nhận message** từ channel; poller chỉ dùng khi đầu vào là `PollableChannel` |
| “StoredProcMessageHandler gửi OUT params ra reply channel” | Handler **bỏ qua** return values; dùng gateway khi cần reply |
| “Có stored procedure là phải dùng `isFunction(true)`” | Procedure khác function; adapter không hỗ trợ SQL function |
| “`Jdbc.storedProcOutboundAdapter` có trong mọi 6.x” | Java DSL JDBC factory có từ 7.0 |
| “Record camelCase luôn tự bind theo JDBC metadata” | Metadata có thể lower-case; dùng `ProcedureParameter` tường minh |
| “Khai báo `ProcedureParameter` nhưng SpEL không thấy header” | Khi dùng biểu thức, cần hiểu nguồn tham số là toàn message |
| “`send() == true` là commit đã được xác nhận ở mọi flow” | Phụ thuộc channel và transaction |
| “Một JDBC transaction tự commit Kafka/JMS luôn” | Cần thiết kế outbox/ACK/idempotency riêng |
| “Retry procedure POST-like sau timeout luôn vô hại” | DB có thể đã commit; idempotency key phải được thực thi |
| “Tạo nhiều executor threads luôn tăng throughput” | DB locks/pool thường thành nút nghẽn |
| “JDBC trong WebFlux app là non-blocking” | JDBC là blocking I/O |
| “Một event ID trùng luôn có nghĩa dữ liệu giống nhau” | Phải kiểm tra và báo conflict nếu khác |

## 17. Bài thực hành

1. Dựng SQL Server test, tạo `order_state`, `processed_order_event` và procedure `apply_order_status`. Gọi `EXEC` trực tiếp để kiểm chứng transaction/idempotency.
2. Viết flow Spring Integration 7.x với `Jdbc.storedProcOutboundAdapter`, truyền `orderId/newStatus` từ payload và `eventId` từ header.
3. Xóa `ProcedureParameter` và thử binding tự động. Quan sát tên field camelCase, SQL metadata và giải thích khác biệt.
4. Bật `ignoreColumnMetaData(true)` rồi bỏ một `SqlParameter`. Kiểm tra cách driver/`SimpleJdbcCall` phản hồi.
5. Chuyển cùng một flow sang Spring Integration 6.x bằng `StoredProcExecutor` + `StoredProcMessageHandler`; so sánh import với 7.x.
6. Viết cấu hình XML outbound stored procedure adapter và giải thích vì sao không có poller với `DirectChannel`.
7. Thêm OUT parameter `old_status` vào procedure; xác minh adapter không phát reply. Đổi sang stored procedure outbound gateway để nhận result.
8. Gửi hai lần message với cùng eventId và dữ liệu giống nhau; kiểm chứng chỉ một event được ghi.
9. Gửi lại cùng eventId nhưng newStatus khác; xác minh exception và transaction rollback.
10. Đổi `DirectChannel` sang `ExecutorChannel`/`QueueChannel` rồi theo dõi thread, transaction boundary và thời điểm ACK.
11. Mô phỏng deadlock, DB outage, query timeout; phân loại lỗi có thể retry và không retry, thêm backoff cùng giới hạn attempts.
12. Thêm Kafka/JMS source, làm crash sau database commit trước ACK; chứng minh idempotency giữ trạng thái đúng.
13. Tạo transactional outbox để phát sự kiện `order.status.changed` sau commit; xử lý redelivery khi publisher crash.
14. Tạo hai event chuyển trạng thái sai thứ tự; thêm version/optimistic rule vào procedure để tránh ghi lùi.

**Tình huống tổng hợp:** Kafka phát event `order.paid`, Spring Integration gọi stored procedure, database commit thành công nhưng kết nối JDBC mất trước khi client nhận kết quả; broker sẽ redeliver. Hãy nêu cách procedure nhận diện cùng event, cách xử lý outcome không chắc chắn, vị trí ACK/commit, thời điểm phát sự kiện tiếp theo và lý do outbound adapter không phải API phù hợp nếu downstream cần mã trả về `OUT`.

## 18. Tài liệu tham khảo

- [Spring Integration — Stored Procedures](https://docs.spring.io/spring-integration/reference/jdbc/stored-procedures.html): outbound stored procedure adapter/gateway, parameter sources, metadata và XML.
- [Spring Integration — Java DSL for JDBC Components](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): Java DSL JDBC từ 7.0, `Jdbc.storedProcOutboundAdapter` và các component specs.
- [Spring Integration API — JdbcStoredProcOutboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcStoredProcOutboundChannelAdapterSpec.html): `configurerStoredProcExecutor` và handler spec.
- [Spring Integration API — StoredProcExecutorSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/StoredProcExecutorSpec.html): `sqlParameter`, `procedureParameter`, procedure name và metadata.
- [Spring Integration API — StoredProcMessageHandler 7.x](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/outbound/StoredProcMessageHandler.html): một chiều, bỏ qua return values và giới hạn function support.
- [Spring Integration API — StoredProcExecutor 6.x](https://docs.spring.io/spring-integration/docs/6.5.0-SNAPSHOT/api/org/springframework/integration/jdbc/StoredProcExecutor.html): execution với `Message<?>`, parameter source và lifecycle.
- [Spring Framework — SimpleJdbcCall](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html): stored procedure metadata, IN/OUT parameters và JDBC support.
- [Spring Framework — Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): proxy, transaction boundaries, commit và rollback.

> **Ghi nhớ:** JDBC outbound stored procedure adapter là **một `MessageHandler` gọi procedure để tạo side effect**, không phải nguồn polling và **không trả reply business result**. Muốn gọi đúng, cần bind payload/headers thành parameters an toàn, chọn API theo Spring Integration 6.x/7.x và hiểu transaction, errors, retry, idempotency cùng ACK của nguồn message. Nếu cần `OUT`, result set hoặc SQL function, hãy dùng **stored procedure outbound gateway**.
