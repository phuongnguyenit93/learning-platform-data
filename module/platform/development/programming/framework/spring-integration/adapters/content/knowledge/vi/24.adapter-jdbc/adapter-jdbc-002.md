# JDBC outbound channel adapter chạy DML trong Spring Integration

## 1. Bài toán: nhận Message và ghi thay đổi xuống cơ sở dữ liệu

Trong ứng dụng tích hợp, một sự kiện có thể đến từ HTTP, Kafka, JMS, AMQP, file hoặc SFTP. Sau khi kiểm tra và chuẩn hóa, hệ thống cần **ghi dữ liệu xuống database**: thêm đơn hàng, đổi trạng thái, cập nhật tồn kho hoặc xóa bản ghi hết hiệu lực. Việc gọi `JdbcTemplate.update(...)` ngay trong service Java là một cách thực hiện; **JDBC outbound channel adapter** là cách đặt hoạt động ghi SQL thành một **message-handling endpoint** trong Spring Integration.

Ví dụ: nhận `Message<OrderSnapshot>` có payload `orderId`, `status` và `totalAmount`, rồi thực thi:

~~~sql
INSERT INTO order_projection (order_id, status, total_amount)
VALUES (?, ?, ?);
~~~

Với Spring Integration, SQL được thực hiện khi message đến **input channel**. Adapter **không gửi reply nghiệp vụ** về một output channel. Nó thích hợp khi mục đích của chặng này là **side effect ghi database** chứ không phải đọc dữ liệu hoặc lấy row count làm payload cho bước sau.

Bài thuộc chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**. Toàn module tập trung kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; với JDBC, điểm quan trọng là hợp đồng message–SQL, an toàn tham số, transaction, retry và vòng đời connection.

~~~mermaid
flowchart LR
    A["HTTP / Kafka / JMS / File / SFTP"] --> B["Transformer / Filter"]
    B --> C["Message<OrderSnapshot>"]
    C --> D["orderWrites: MessageChannel"]
    D --> E["JDBC outbound channel adapter"]
    E --> F["PreparedStatement / JdbcOperations"]
    F -->|"INSERT, UPDATE, DELETE"| G["Database"]
    F -.->|"DataAccessException nếu lỗi"| H["Caller / error flow"]
~~~

**Không nhầm tên gọi:** outbound ở đây là hướng **Spring Integration → database**. Nó không tự mở cổng HTTP; không phải JDBC inbound poller; cũng không phải outbound gateway có reply.

## 2. Phân biệt outbound adapter với các JDBC endpoint khác

| Thành phần | Hướng dữ liệu | SQL chính | Có reply message? | Mục đích |
|---|---|---|---|---|
| **JDBC inbound channel adapter** | Database → MessageChannel | `SELECT` theo poller; có thể kèm cập nhật trạng thái | Không có reply request-reply | Quét bản ghi mới và phát message |
| **JDBC outbound channel adapter** | MessageChannel → Database | `INSERT`, `UPDATE`, `DELETE` | **Không** | DML một chiều, ghi side effect |
| **JDBC outbound gateway** | MessageChannel → DB → reply channel | `SELECT` hoặc DML | **Có** | Trả rows, số rows bị tác động hoặc generated keys theo cấu hình |
| **Stored procedure adapter/gateway** | Theo hướng inbound/outbound | Stored procedure/function | Tùy adapter/gateway | Hợp đồng gọi procedure |
| **JdbcTemplate trong service activator** | Message → service → DB | SQL tùy nghiệp vụ | Tùy service trả về | Khi cần nhiều nhánh, row count, xử lý domain phức tạp |

**Tình huống lựa chọn:** Nếu yêu cầu là “ghi event vào bảng audit, không cần biết row count trong flow”, outbound channel adapter phù hợp. Nếu phải quyết định “UPDATE ảnh hưởng đúng một hàng thì phát event tiếp, nếu không thì báo conflict”, hãy cân nhắc **JDBC outbound gateway** hoặc một service activator có `JdbcTemplate` trả số hàng.

## 3. Hợp đồng dữ liệu và SQL DML

Giả sử ứng dụng xây dựng bảng đọc nhanh `order_projection` từ các event đơn hàng. Trong demo, dùng H2 hoặc một hệ quản trị có SQL tương thích:

~~~sql
CREATE TABLE order_projection (
    order_id      VARCHAR(64) PRIMARY KEY,
    status        VARCHAR(32) NOT NULL,
    total_amount  DECIMAL(18, 2) NOT NULL,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Message nghiệp vụ:

~~~java
import java.math.BigDecimal;

public record OrderSnapshot(
    String orderId,
    String status,
    BigDecimal totalAmount) {
}
~~~

Hợp đồng cho INSERT:

| Nguồn | Đích SQL | Ràng buộc |
|---|---|---|
| `payload.orderId` | `order_id` | Không null, duy nhất, tối đa 64 ký tự |
| `payload.status` | `status` | Trạng thái hợp lệ theo domain |
| `payload.totalAmount` | `total_amount` | Dùng `BigDecimal` cho giá trị tiền |
| Thời gian DB | `updated_at` | Do DB tạo theo `CURRENT_TIMESTAMP` |
| `headers["eventId"]` (nếu dùng) | Cột audit hoặc bảng idempotency riêng | Giữ ổn định qua redelivery/retry |

**Điều JDBC không tự làm:** chuyển mọi event thành trạng thái đúng thứ tự, loại bỏ message trùng, kiểm soát phiên bản nghiệp vụ và xác định lúc được ACK nguồn. Cần thiết kế riêng các quy tắc này trước khi bật ghi dữ liệu.

Ba lệnh DML căn bản:

~~~sql
-- Thêm bản ghi mới
INSERT INTO order_projection (order_id, status, total_amount)
VALUES (?, ?, ?);

-- Chuyển trạng thái có điều kiện
UPDATE order_projection
SET status = ?, updated_at = CURRENT_TIMESTAMP
WHERE order_id = ? AND status = ?;

-- Xóa theo khóa
DELETE FROM order_projection WHERE order_id = ?;
~~~

`?` là placeholders cho **giá trị dữ liệu**, không phải cách ghép tên bảng/cột. Khi dùng `PreparedStatement`, JDBC driver bind tham số đúng kiểu và tránh SQL injection từ những giá trị không tin cậy.

## 4. Chuẩn bị dependency và lưu ý khác biệt phiên bản

Ví dụ dùng Spring Boot, Spring JDBC và module Spring Integration JDBC. Nên để BOM của Spring Boot quản lý phiên bản tương thích:

~~~groovy
// build.gradle - dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    // H2 chỉ dành cho demo. Production dùng JDBC driver của DB thật.
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml - cấu hình demo H2
spring:
  datasource:
    url: jdbc:h2:mem:integration_demo;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

Nếu lưu câu lệnh `CREATE TABLE` ở `src/main/resources/schema.sql`, Spring Boot có thể khởi tạo schema khi ứng dụng bắt đầu theo cấu hình thích hợp. Với production, dùng công cụ migration như Flyway/Liquibase để kiểm soát phiên bản schema thay vì dựa vào tự tạo bảng.

**Rất quan trọng về API:**

- **Spring Integration 7.0+** giới thiệu Java DSL factory `org.springframework.integration.jdbc.dsl.Jdbc` với `Jdbc.outboundAdapter(...)`.
- **Spring Integration 6.x** vẫn có endpoint `JdbcMessageHandler` và cấu hình qua `@ServiceActivator`/XML; **không sử dụng `Jdbc.outboundAdapter(...)`** như thể nó đã tồn tại ở 6.x.
- `JdbcMessageHandler` thuộc package `org.springframework.integration.jdbc.JdbcMessageHandler` ở 6.x; trong API 7.x, package là `org.springframework.integration.jdbc.outbound.JdbcMessageHandler`. Chọn import theo phiên bản thực tế, không trộn code của hai thế hệ.

Các ví dụ Java DSL sau đây hướng tới **Spring Integration 7.x**. Phần riêng cho 6.x ở mục 9 dùng cách khởi tạo trực tiếp handler.

## 5. Java DSL 7.x: INSERT bằng JDBC outbound channel adapter

### 5.1. Bean MessageChannel và IntegrationFlow

~~~java
package com.example.orders;

import java.math.BigDecimal;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderWriteFlow {

    public record OrderSnapshot(
        String orderId, String status, BigDecimal totalAmount) {
    }

    @Bean
    public MessageChannel orderWrites() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow insertOrders(
            DataSource dataSource,
            @Qualifier("orderWrites") MessageChannel orderWrites) {

        return IntegrationFlow.from(orderWrites)
            .handle(Jdbc.outboundAdapter(dataSource,
                    "INSERT INTO order_projection "
                  + "(order_id, status, total_amount) VALUES (?, ?, ?)")
                .preparedStatementSetter((ps, requestMessage) -> {
                    OrderSnapshot order =
                        (OrderSnapshot) requestMessage.getPayload();
                    ps.setString(1, order.orderId());
                    ps.setString(2, order.status());
                    ps.setBigDecimal(3, order.totalAmount());
                }))
            .get();
    }
}
~~~

**Diễn giải:**

1. `DirectChannel` nhận message và chuyển ngay tới subscriber/handler trong luồng gọi của sender, trừ khi một thành phần khác thay đổi execution boundary.
2. `Jdbc.outboundAdapter(dataSource, sql)` tạo outbound JDBC endpoint; về bản chất dùng `JdbcMessageHandler` để chạy câu SQL update.
3. `preparedStatementSetter((ps, requestMessage) -> ...)` được gọi với JDBC `PreparedStatement` và message nguồn, cho phép lấy payload/header để bind tham số.
4. Chỉ có một `INSERT` và **không có `replyChannel`/output channel** cho kết quả DML trong flow này.
5. SQL dùng placeholders nên `orderId`, `status` và `totalAmount` là **giá trị được bind**, không nối thẳng thành SQL string.

Đối với ví dụ này, không cần cả `SqlParameterSourceFactory` lẫn `preparedStatementSetter`: đây là **hai chiến lược binding thay thế**, không cấu hình đồng thời.

### 5.2. Gửi message vào adapter

Một component nghiệp vụ có thể inject channel và phát sự kiện:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class OrderWritePublisher {

    private final MessageChannel input;

    public OrderWritePublisher(
            @Qualifier("orderWrites") MessageChannel input) {
        this.input = input;
    }

    public void persist(String orderId, BigDecimal amount) {
        var snapshot = new OrderWriteFlow.OrderSnapshot(
            orderId, "RECEIVED", amount);

        boolean delivered = input.send(
            MessageBuilder.withPayload(snapshot)
                .setHeader("eventId", "evt-" + orderId)
                .build());

        if (!delivered) {
            throw new IllegalStateException(
                "Message was not accepted by orderWrites");
        }
    }
}
~~~

Ví dụ gọi:

~~~java
publisher.persist("ORD-1001", new BigDecimal("125000.00"));
~~~

Khi câu `INSERT` thành công trong một transaction được commit, database có:

| order_id | status | total_amount |
|---|---|---:|
| ORD-1001 | RECEIVED | 125000.00 |

**`input.send(...) == true` không phải biên nhận commit** cho mọi loại channel. Với `DirectChannel` và handler JDBC đồng bộ, thao tác SQL được thực hiện theo đường gọi của sender; tuy nhiên, **transaction bao ngoài vẫn có thể rollback sau khi `send` trả true**. Nếu thay bằng `ExecutorChannel` hoặc queue/poller, xử lý có thể diễn ra ở thread/thời điểm khác.

## 6. UPDATE và DELETE: viết có điều kiện, không ghi đè mù quáng

### 6.1. UPDATE dựa trên trạng thái hiện tại

Đổi trạng thái đơn từ `RECEIVED` sang `PROCESSING`:

~~~java
public record OrderStatusChange(
    String orderId, String expectedStatus, String newStatus) {
}

@Bean
IntegrationFlow updateOrderStatus(DataSource dataSource) {
    return IntegrationFlow.from("orderStatusChanges")
        .handle(Jdbc.outboundAdapter(dataSource,
                "UPDATE order_projection "
              + "SET status = ?, updated_at = CURRENT_TIMESTAMP "
              + "WHERE order_id = ? AND status = ?")
            .preparedStatementSetter((ps, message) -> {
                OrderStatusChange change =
                    (OrderStatusChange) message.getPayload();
                ps.setString(1, change.newStatus());
                ps.setString(2, change.orderId());
                ps.setString(3, change.expectedStatus());
            }))
        .get();
}
~~~

Lệnh `UPDATE ... WHERE order_id = ? AND status = ?` tránh ghi đè khi trạng thái không còn như dự kiến. Tuy nhiên, khi không khớp bản ghi, JDBC có thể trả **0 rows affected mà không ném exception**. Vì outbound channel adapter không tạo reply, flow không thể dựa vào adapter này để tự phát hiện tình huống “0 rows”. Nếu nghiệp vụ yêu cầu đúng một dòng phải được cập nhật, **dùng outbound gateway hoặc JdbcTemplate handler có kiểm tra update count**.

Ở ví dụ, `orderStatusChanges` là channel được tham chiếu theo tên trong DSL, phải có producer đưa message `OrderStatusChange` vào đó. Đây là **một flow riêng** với flow INSERT ở mục 5, không tự chạy khi chỉ khai báo bean.

### 6.2. DELETE an toàn theo khóa

~~~java
public record DeleteOrderCommand(String orderId) { }

@Bean
IntegrationFlow deleteOrder(DataSource dataSource) {
    return IntegrationFlow.from("orderDeletes")
        .handle(Jdbc.outboundAdapter(dataSource,
                "DELETE FROM order_projection WHERE order_id = ?")
            .preparedStatementSetter((ps, message) -> {
                DeleteOrderCommand command =
                    (DeleteOrderCommand) message.getPayload();
                ps.setString(1, command.orderId());
            }))
        .get();
}
~~~

Không tạo SQL DELETE không có `WHERE` từ dữ liệu không tin cậy. Trong nhiều nghiệp vụ nên ưu tiên *soft delete* (đánh dấu `deleted_at` hoặc trạng thái) để phục vụ audit, khôi phục và kiểm toán.

### 6.3. INSERT, UPDATE, DELETE có tính chất khác nhau

| Lệnh | Trường hợp thường gặp | Vấn đề cần xử lý |
|---|---|---|
| `INSERT` | Tạo một dòng mới | Trùng khóa chính, idempotency |
| `UPDATE` | Sửa trạng thái/giá trị | Stale event, race condition, số rows = 0 |
| `DELETE` | Xóa bản ghi | Xóa nhầm, số rows = 0, ràng buộc khóa ngoại |
| `UPSERT/MERGE` | Tạo hoặc cập nhật | Cú pháp phụ thuộc DB và chính sách conflict |

Chỉ dùng `UPSERT` khi có hợp đồng rõ: event nào được phép ghi đè và cần bảo vệ chống out-of-order events ra sao. Một câu lệnh “upsert mọi thứ” có thể làm dữ liệu quay về trạng thái cũ nếu message bị xử lý lại sai thứ tự.

## 7. Binding tham số: mặc định, SpEL và PreparedStatement

Spring Integration JDBC hỗ trợ các cách lấy tham số SQL từ message.

### 7.1. Cú pháp named parameters mặc định

Ví dụ XML trong tài liệu Spring Integration:

~~~xml
<int-jdbc:outbound-channel-adapter
    data-source="dataSource"
    channel="inventoryAudit"
    query="INSERT INTO audit_event (event_id, description)
           VALUES (:headers[eventId], :payload[text])"/>
~~~

Đầu vào là message có header `eventId` và payload kiểu Map chứa key `text`. Tham số `:headers[eventId]` và `:payload[text]` được giải từ **cấu trúc message**, qua `SqlParameterSource` mặc định; đây **không phải cú pháp SpEL tự do**. Không đặt dấu nháy quanh tên header trong `:headers[eventId]` chỉ để giả lập SpEL.

XML là **cách cấu hình thay thế**, không cần dùng đồng thời với Java DSL ví dụ trước. Khi dùng XML thật, ứng dụng phải có namespace/schema configuration phù hợp.

### 7.2. Dùng SqlParameterSourceFactory tùy biến

Khi SQL cần biến đổi tham số (ngày giờ, text, headers...) bằng SpEL, có thể cấu hình `ExpressionEvaluatingSqlParameterSourceFactory`, với biểu thức như `headers['eventId']`, `payload.orderId`. Cách này khác với binding mặc định và cần **đăng ký factory tường minh**.

Từ Spring Integration **6.5**, `JdbcMessageHandler#setUsePayloadAsParameterSource(true)` cho phép lấy **toàn bộ payload** làm nguồn parameter binding, thay vì message đầy đủ. Ví dụ SQL `:orderId`, `:status` dùng cho payload tương ứng; tên thuộc tính cần thực sự được parameter source đọc được.

### 7.3. PreparedStatement callback

`MessagePreparedStatementSetter` là lựa chọn rõ ràng khi cần `setString`, `setBigDecimal`, `setTimestamp`, `setBlob` hoặc xử lý kiểu JDBC cụ thể. Phù hợp với Java records/DTO, tránh phụ thuộc vào cách truy xuất nested property paths. Trong các ví dụ mục 5 và 6, `?` ứng với **chỉ số JDBC bắt đầu từ 1**, không phải 0.

| Cơ chế | SQL | Dữ liệu bind | Khi dùng |
|---|---|---|---|
| Binding mặc định | `:headers[eventId]`, `:payload[key]` | Message headers/payload theo property path | Cấu hình ngắn, message đơn giản |
| `SqlParameterSourceFactory` custom | `:id`, `:createdDate` | Expressions/mapper do ứng dụng định nghĩa | Chuyển đổi tham số phức tạp |
| `MessagePreparedStatementSetter` | `?`, `?`, `?` | `ps.setXxx(index, value)` | Kiểu JDBC rõ ràng, BLOB/CLOB, records |

**An toàn SQL:** named parameters và `?` áp dụng cho **giá trị**, không phải tên bảng hoặc cột. Nếu tên bảng thay đổi theo tenant, phải chọn từ allowlist/schema thiết kế sẵn; không nối trực tiếp `payload.tableName` vào SQL.

## 8. Batch DML: payload Iterable

Từ Spring Integration 5.1, `JdbcMessageHandler` hỗ trợ **batch update** khi payload của request message là một `Iterable`. Mỗi phần tử có thể được bọc thành message có headers từ message nguồn; adapter dùng `JdbcOperations.batchUpdate(...)` hoặc biến thể dựa trên `MessagePreparedStatementSetter`.

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.messaging.support.MessageBuilder;

List<OrderWriteFlow.OrderSnapshot> batch = List.of(
    new OrderWriteFlow.OrderSnapshot(
        "ORD-2001", "RECEIVED", new BigDecimal("50000.00")),
    new OrderWriteFlow.OrderSnapshot(
        "ORD-2002", "RECEIVED", new BigDecimal("75000.00"))
);

// Cùng input channel orderWrites, payload lần này là Iterable.
orderWrites.send(MessageBuilder.withPayload(batch)
    .setHeader("batchId", "batch-001")
    .build());
~~~

Khi handler đã cấu hình `preparedStatementSetter` theo `OrderSnapshot` ở mục 5, nó có thể bind từng phần tử của batch; headers từ message gốc được bảo toàn cho mỗi phần tử theo quy tắc của handler. **Batch không có nghĩa tự động chia transaction**, và khi một hàng thất bại, driver có thể báo các update counts/trạng thái từng câu lệnh khác nhau.

Lưu ý:

- Không bật `keysGenerated` cùng batch: **batch update không được hỗ trợ ở chế độ generated keys** của `JdbcMessageHandler`.
- Với bản ghi quan trọng, dùng transaction rõ ràng để tránh trạng thái “một phần thành công” không mong muốn; kết quả cụ thể còn tùy JDBC driver và database.
- Chia batch có giới hạn kích thước để tránh giữ lượng message quá lớn, transaction dài hoặc lock lâu.
- Một `Iterable` rất lớn không tự tạo backpressure; hãy kiểm soát nguồn, chunking, pool và tốc độ xử lý.
- Tránh gửi một payload `List<?>` nếu ý nghĩa nghiệp vụ thực ra là **một** JSON/list cần lưu vào **một** cột, vì handler có thể hiểu đó là batch.

## 9. Tương thích Spring Integration 6.x bằng JdbcMessageHandler

Trong Spring Integration 6.x, có thể khai báo `JdbcMessageHandler` trực tiếp và gắn vào `@ServiceActivator`, thay vì dùng factory `Jdbc.outboundAdapter(...)` chưa tồn tại ở phiên bản này.

~~~java
package com.example.orders;

import java.math.BigDecimal;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.jdbc.JdbcMessageHandler;
import org.springframework.messaging.MessageHandler;

@Configuration
public class LegacyJdbcAdapterConfiguration {

    // DTO độc lập với phần Java DSL 7.x ở mục 5.
    public record OrderSnapshot(
        String orderId, String status, BigDecimal totalAmount) { }

    @Bean
    @ServiceActivator(inputChannel = "legacyOrderWrites")
    public MessageHandler insertOrderHandler(DataSource dataSource) {
        JdbcMessageHandler handler = new JdbcMessageHandler(
            dataSource,
            "INSERT INTO order_projection "
          + "(order_id, status, total_amount) VALUES (?, ?, ?)");

        handler.setPreparedStatementSetter((ps, message) -> {
            OrderSnapshot order = (OrderSnapshot) message.getPayload();
            ps.setString(1, order.orderId());
            ps.setString(2, order.status());
            ps.setBigDecimal(3, order.totalAmount());
        });
        return handler;
    }
}
~~~

Đây là **phương án thay thế** cho flow INSERT ở mục 5. Nếu cùng ứng dụng chạy cả hai cấu hình và cùng nhận một message, có thể ghi trùng. Không nên bật đồng thời nếu mục tiêu là chỉ một câu lệnh INSERT cho mỗi event.

Ở **Spring Integration 7.x**, nếu chọn xây dựng `JdbcMessageHandler` thủ công thay vì Java DSL, dùng import `org.springframework.integration.jdbc.outbound.JdbcMessageHandler`. Phần chức năng cơ bản vẫn là nhận message và chạy SQL DML; chi tiết package/API phải theo version thực tế.

## 10. Transaction: khi nào INSERT thật sự được commit?

### 10.1. DirectChannel giữ cùng thread/transaction của sender

Theo hợp đồng Spring Integration, nếu input là `DirectChannel`, handler JDBC chạy trong **cùng thread** của caller. Khi caller đang ở transaction quản lý bởi cùng `DataSource` và transaction manager phù hợp, JDBC update có thể tham gia transaction đó.

~~~mermaid
sequenceDiagram
    participant Service as @Transactional Service
    participant Channel as DirectChannel
    participant Handler as JDBC outbound adapter
    participant DB as Database
    Service->>Service: Begin transaction
    Service->>Channel: send(Message<OrderSnapshot>)
    Channel->>Handler: handleMessage
    Handler->>DB: INSERT (trong transaction)
    DB-->>Handler: SQL executed
    Handler-->>Channel: Return
    Channel-->>Service: send returns
    Service->>DB: COMMIT khi method hoàn tất
~~~

Ví dụ:

~~~java
import java.math.BigDecimal;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TransactionalOrderCommand {
    private final MessageChannel orderWrites;

    TransactionalOrderCommand(
            @Qualifier("orderWrites") MessageChannel orderWrites) {
        this.orderWrites = orderWrites;
    }

    @Transactional
    public void accept(String orderId, BigDecimal amount) {
        boolean sent = orderWrites.send(
            MessageBuilder.withPayload(
                new OrderWriteFlow.OrderSnapshot(
                    orderId, "RECEIVED", amount))
                .build());
        if (!sent) {
            throw new IllegalStateException("No JDBC subscriber");
        }
        // Commit sau khi method trả về, không phải tại lệnh send().
    }
}
~~~

Ví dụ giả định `@Transactional` được gọi qua Spring-managed proxy, có transaction manager JDBC tương ứng với `DataSource` được inject vào adapter và không có asynchronous boundary. Không được suy ra một transaction nếu gọi phương thức nội bộ bằng `this.accept(...)` rồi bypass proxy hoặc dùng sai transaction manager.

### 10.2. ExecutorChannel, QueueChannel và poller

Nếu thay `DirectChannel` bằng `ExecutorChannel`, dispatch chuyển sang thread của executor. Transaction thread-bound ở caller **không tự chảy theo** sang handler. Với `QueueChannel`, message nằm chờ poller tiêu thụ; transaction của sender có thể commit trước khi JDBC adapter chạy.

~~~mermaid
flowchart TB
    A["Sender @Transactional"] --> B{"Loại channel"}
    B -->|"DirectChannel"| C["Handler cùng thread; có thể cùng TX"]
    B -->|"ExecutorChannel"| D["Thread khác; cần TX riêng"]
    B -->|"QueueChannel + poller"| E["Thời điểm khác; poller quản lý TX"]
~~~

Vì vậy, **lựa chọn channel là lựa chọn về transaction boundary và cách xử lý lỗi**, không chỉ khác biệt hiệu năng. Với nguồn Kafka/JMS và ghi JDBC, cần kiểm tra chính xác thời điểm ACK/commit của nguồn; một transaction database local không biến Kafka + database thành một giao dịch phân tán atomic.

### 10.3. Outbox khi cần phát sự kiện sau DB commit

Nếu nghiệp vụ “ghi đơn hàng rồi gửi Kafka”, cách an toàn phổ biến là **transactional outbox**: ghi bảng nghiệp vụ và bảng outbox trong **cùng local DB transaction**, sau đó một publisher riêng đọc outbox và gửi broker; khi gửi thành công đánh dấu trạng thái outbox. Thiết kế này hỗ trợ retry sau restart, nhưng vẫn cần idempotency vì publisher có thể gửi trùng khi crash.

Không nên tuyên bố rằng một chuỗi `JDBC outbound adapter → Kafka outbound adapter` tự có transaction xuyên hai hệ thống.

## 11. Lỗi JDBC, retry và idempotency

Spring JDBC dịch nhiều `SQLException` thành các kiểu `DataAccessException`; có trường hợp framework bọc thêm thành `MessagingException` hoặc lỗi endpoint. Chính sách nên phân loại lỗi theo nguyên nhân:

| Nhóm lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Trùng khóa | `DuplicateKeyException` | Xác minh event đã xử lý; không retry vô hạn |
| Vi phạm NOT NULL/FK/check | `DataIntegrityViolationException` | Kiểm tra dữ liệu và hợp đồng, chuyển lỗi nghiệp vụ |
| Database mất kết nối | Một số `DataAccessResourceFailureException` | Retry có giới hạn khi điều kiện cho phép |
| Deadlock/serialization conflict | Lỗi concurrency/transient tùy DB | Backoff/jitter, retry **toàn transaction** khi an toàn |
| Lock/statement timeout | Exception theo driver/DB | Điều chỉnh transaction, index, thời hạn, tải |
| UPDATE 0 rows | Không nhất thiết có exception | Dùng gateway/service để kiểm tra row count |
| Payload không đúng kiểu | `ClassCastException`/conversion | Sửa transformer/validation, không retry như network error |

**JDBC là blocking I/O.** Trên WebFlux event loop, không chạy adapter JDBC đồng bộ trực tiếp như thể nó là publisher non-blocking. Hãy tách tác vụ JDBC sang executor/boundedElastic hoặc dùng mô hình messaging có worker thread, giới hạn connection pool/concurrency; việc chuyển thread không làm JDBC thành non-blocking.

### 11.1. Retry đúng đơn vị giao dịch

Nếu transaction gồm hai UPDATE cùng phụ thuộc nhau, khi deadlock cần retry **toàn bộ đơn vị transactional** sau rollback, không chỉ retry một statement rồi mặc định trạng thái trước đó còn đúng. Với database lock timeout hoặc transient network lỗi sau commit không rõ, kết quả có thể ở trạng thái **unknown** đối với caller; idempotency và query lại trạng thái giúp tránh ghi trùng.

### 11.2. Đừng coi trùng khóa luôn là thành công

Giả sử `order_id` là PRIMARY KEY. Khi nhận lại cùng event, câu INSERT thứ hai có thể ném `DuplicateKeyException`. Nếu dữ liệu đã lưu **chính xác tương ứng** với event cũ, hệ thống có thể coi là duplicate đã xử lý. Nếu cùng `orderId` nhưng amount/status khác, đó có thể là conflict nghiêm trọng. Phải so sánh **business event ID/version và payload hash hoặc quy tắc domain**, không “catch mọi duplicate key rồi bỏ qua”.

Với consumer Kafka/JMS, có thể dùng bảng `processed_event(event_id UNIQUE, ...)` ghi cùng transaction với thay đổi nghiệp vụ. Khi xử lý lại, kiểm tra key và trạng thái đã commit trước khi quyết định ACK. Nếu cần exactly-once effect ở database, thiết kế ranh giới DB idempotency rõ ràng thay vì kỳ vọng broker không bao giờ redeliver.

## 12. Khi cần update count hoặc generated keys

Outbound channel adapter chỉ thực hiện side effect; nó **không công bố số hàng cập nhật qua reply channel**.

- Với `UPDATE ... WHERE ...`, **0 rows affected** có thể là không tìm thấy hoặc trạng thái cũ không còn đúng. Nếu workflow cần biết, dùng `JdbcOutboundGateway` hoặc service activator `JdbcTemplate.update(...)` và trả số hàng như một reply message.
- Với auto-generated ID, JDBC outbound adapter có tùy chọn `keysGenerated` nhưng đó **không phải một response message** cho downstream. Nếu cần generated key để tiếp tục flow, dùng outbound gateway có cấu hình phù hợp.
- Với batch, chế độ generated keys của `JdbcMessageHandler` không được hỗ trợ.

Ví dụ ý tưởng về gateway DML:

~~~text
Message<StatusChange>
    -> JDBC outbound gateway chạy UPDATE
    -> Reply payload chứa UPDATED count theo hợp đồng gateway
    -> Router: UPDATED == 1 ? success : conflict/not-found
~~~

Không dùng outbound adapter rồi viết một router đọc `headers["UPDATED"]` nếu chưa có chặng nào thực sự tạo header/result đó. Cần xác định đầu ra của endpoint được chọn.

## 13. Hiệu năng, khóa và vận hành production

### 13.1. Connection pool và giới hạn đồng thời

Mỗi JDBC operation sử dụng connection thuộc `DataSource` pool. Nếu nguồn gửi message nhanh hơn database xử lý, bạn có thể gặp pool exhaustion, lock contention, transaction dài hoặc backlog trên queue.

Các chỉ số cần theo dõi:

1. **Throughput INSERT/UPDATE/DELETE:** số message nhận, số rows thực hiện và tốc độ commit.
2. **Latency:** thời gian chờ connection, thời gian SQL execution, commit time, p95/p99.
3. **Pool:** active/idle/pending connections và connection timeout; đừng tăng pool vô hạn.
4. **DB:** locks, deadlock, CPU, I/O, wait events, slow queries, index usage.
5. **Message flow:** queue depth, consumer lag, số retry, DLQ, bản ghi bị trùng và time-to-persist.
6. **Transaction:** số rollback và thời gian transaction giữ locks.

Đặt input capacity, executor concurrency và batch size theo **năng lực database**, không theo số lượng message đầu vào. `DirectChannel` nối trực tiếp với sender sẽ làm caller chịu độ trễ ghi DB; `ExecutorChannel` tách thời gian nhưng phải có queue/pool giới hạn và transactional policy riêng.

### 13.2. Timeout và khóa

`DataSource` pool connection timeout khác với `JdbcTemplate` query timeout hoặc thời gian chờ lock của DB. Một query timeout không chứng minh transaction đã rollback nếu chưa được transaction manager xử lý đúng. Đừng tự dùng `Thread.sleep` để retry trong poller khiến thread bị giữ lâu; với hệ thống throughput lớn, cân nhắc scheduling backoff ở tầng consumer.

### 13.3. Bảo mật SQL

- Dùng prepared statements hoặc named parameters cho **mọi giá trị từ payload/headers**.
- Không cho phép payload tùy ý quyết định tên bảng, tên cột hoặc toàn bộ SQL.
- Áp dụng DB account với quyền tối thiểu chỉ trên bảng/thao tác cần thiết.
- Không log giá trị nhạy cảm của SQL parameters hoặc JDBC credentials.
- Dùng migration kiểm soát schema và indexes theo truy vấn thực tế.
- Xác minh tenant/authorization trước khi ghi; `tenantId` từ header không đáng tin không thay thế phân quyền.

## 14. Kiểm thử JDBC outbound channel adapter

Một integration test phải kiểm tra **trạng thái database sau khi transaction hoàn tất**, không chỉ kiểm tra `send()`. Ví dụ test với Spring Boot + H2 và schema ở mục 3:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.math.BigDecimal;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class JdbcOutboundAdapterTest {

    @Autowired
    @Qualifier("orderWrites")
    MessageChannel orderWrites;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void insertsOrderIntoProjection() {
        String id = "ORD-" + UUID.randomUUID();
        var payload = new OrderWriteFlow.OrderSnapshot(
            id, "RECEIVED", new BigDecimal("20000.00"));

        boolean dispatched =
            orderWrites.send(MessageBuilder.withPayload(payload).build());
        assertEquals(true, dispatched);

        String savedStatus = jdbc.queryForObject(
            "SELECT status FROM order_projection WHERE order_id = ?",
            String.class, id);
        assertEquals("RECEIVED", savedStatus);
    }
}
~~~

Test dùng `DirectChannel` và không bao ngoài bằng một test-level transaction rollback. Nếu test dùng `@Transactional` ở method test, cần hiểu dữ liệu chưa commit vẫn có thể thấy từ cùng thread/connection; muốn kiểm chứng commit thực, chạy một transaction khác hoặc test qua cách gọi service thật sau khi transaction kết thúc.

### 14.1. Ma trận kiểm thử quan trọng

| Trường hợp | Kết quả cần kiểm tra |
|---|---|
| INSERT message hợp lệ | DB có một dòng đúng dữ liệu |
| Gửi lại cùng message | Duplicate key hoặc idempotency đúng thiết kế |
| UPDATE state hợp lệ | Thay đúng một dòng, không chạm dòng khác |
| UPDATE state cũ sai | 0 rows; gateway/service phát hiện nếu hợp đồng cần |
| DELETE theo orderId | Chỉ xóa đúng dòng |
| Payload không hợp lệ | Validation/mapper báo lỗi trước khi ghi |
| Driver/DB không sẵn sàng | Error flow, rollback và retry theo chính sách |
| Batch có một dòng trùng | Rollback/partial failure theo transaction và DB driver |
| ExecutorChannel thay DirectChannel | Transaction boundary thay đổi, test timing/ACK |
| Kafka/JMS redelivery | Không nhân đôi tác dụng của event |
| Restart sau ghi DB trước broker publish | Outbox tiếp tục gửi và idempotency tránh trùng |

## 15. Các lỗi thiết kế thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “JDBC outbound adapter dùng poller để chạy DML” | Nó xử lý **message đến**; poller chỉ thuộc nguồn/queue tương ứng |
| “`Jdbc.outboundAdapter` dùng được mọi Spring Integration 6.x” | Java DSL factory này chỉ có từ 7.0 |
| “`send() == true` nghĩa database chắc chắn commit” | Transaction có thể còn mở hoặc handler chạy async |
| “INSERT trùng khóa phải retry mãi” | Đây thường là conflict/idempotency case, không phải network transient |
| “UPDATE 0 dòng sẽ tự ném lỗi” | Nhiều JDBC updates hợp lệ trả row count 0 |
| “Outbound adapter tạo reply `UPDATED=1`” | Reply update count thuộc gateway/service có kết quả |
| “Dùng `:headers[eventId]` là SpEL tự do” | Mặc định là parameter property path; SpEL cần factory thích hợp |
| “Đã dùng prepared statement nên cho phép SQL tên bảng động từ input” | Parameter placeholders chỉ bind **giá trị**, không bind identifier |
| “Batch chắc chắn atomic nếu không khai báo transaction” | Cần TX rõ ràng; driver/DB có thể partial execute |
| “JDBC trên WebFlux event loop tự non-blocking” | JDBC là blocking; phải tránh chặn event loop |
| “DirectChannel và ExecutorChannel giữ cùng transaction” | Executor thường chuyển thread, transaction không tự đi theo |
| “DB transaction có thể commit Kafka đồng thời” | Cần outbox/XA được thiết kế, không tự có |

## 16. Bài thực hành

1. Tạo schema `order_projection` và chạy flow INSERT. Kiểm tra một `OrderSnapshot` được ghi đúng các cột và `updated_at`.
2. Gửi hai messages cùng `orderId`, phân tích `DuplicateKeyException`; bổ sung bảng `processed_event` để xử lý idempotency.
3. Tạo flow UPDATE có điều kiện `WHERE order_id=? AND status=?`. Gửi trạng thái đúng và sai; chỉ rõ vì sao adapter một chiều không tự trả số dòng.
4. Thay flow UPDATE bằng JDBC outbound gateway hoặc `JdbcTemplate` service activator có reply update count; route `0` thành conflict và `1` thành success.
5. Viết flow DELETE theo khóa; đối chiếu với soft delete và quy tắc audit.
6. Gửi một `List<OrderSnapshot>` làm payload để batch update. Quan sát số lệnh SQL, transaction, và test khi một dòng trùng khóa.
7. Thử mapping với `:headers[eventId]` và `:payload[text]`, sau đó chuyển sang `MessagePreparedStatementSetter`. Phân biệt property path mặc định và SpEL.
8. Chạy với `DirectChannel` và một service `@Transactional`; cố tình ném exception sau `send` để kiểm tra rollback.
9. Đổi sang `ExecutorChannel` và kiểm tra transaction không tự truyền sang handler; quyết định nơi mở transaction mới.
10. Mô phỏng DB mất kết nối rồi khôi phục; thiết kế retry có giới hạn, backoff và dead-letter thay vì giữ thread vô hạn.
11. Gắn nguồn Kafka/JMS hoặc poller vào channel; xác định thời điểm ACK/commit và cách xử lý redelivery khi DB đã commit.
12. Thiết kế outbox ghi cùng transaction với `order_projection`, sau đó một publisher riêng đọc outbox gửi event sang broker.

**Câu hỏi tình huống:** Một message `order.paid` được broker phát lại sau khi database đã lưu trạng thái `PAID`, nhưng trước khi ứng dụng ACK. Nếu dùng JDBC outbound adapter INSERT trực tiếp, điều gì xảy ra với khóa chính? Bạn sẽ thiết kế event ID, idempotent update/outbox, transaction và ACK như thế nào để vừa không mất sự kiện vừa không cập nhật sai thứ tự?

## 17. Tài liệu tham khảo

- [Spring Integration Reference — JDBC Outbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/outbound-channel-adapter.html): SQL update, tham số, `PreparedStatement` callback, batch và transaction cùng `DirectChannel`.
- [Spring Integration Reference — Java DSL for JDBC Components](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.outboundAdapter(...)` từ Spring Integration 7.0 và các builder specs.
- [Spring Integration API — JdbcMessageHandler (7.x)](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/outbound/JdbcMessageHandler.html): constructor, prepared statement setter, generated keys, payload parameter source.
- [Spring Integration API — JdbcMessageHandler (6.5)](https://www.springframework.org/spring-integration/docs/6.5.0/api/org/springframework/integration/jdbc/JdbcMessageHandler.html): package cũ và các tùy chọn handler.
- [Spring Integration Reference — JDBC Outbound Gateway](https://docs.spring.io/spring-integration/reference/jdbc/outbound-gateway.html): reply, update count và generated keys.
- [Spring Framework Reference — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): `JdbcTemplate`, `DataSource`, exception translation và transaction.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction scope, propagation, rollback và proxy semantics.

> **Ghi nhớ:** JDBC outbound channel adapter là **message handler một chiều chạy DML**. Nó nhận payload/headers từ `MessageChannel`, bind giá trị vào SQL rồi thực hiện INSERT/UPDATE/DELETE qua `DataSource`, nhưng **không phát reply update count**. Muốn vận hành đáng tin, cần phân biệt phiên bản Java DSL, loại channel, transaction boundary, batch, lỗi JDBC và idempotency khi message bị gửi lại.
