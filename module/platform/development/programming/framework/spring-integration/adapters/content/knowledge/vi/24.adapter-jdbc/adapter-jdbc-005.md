# JDBC outbound gateway trả kết quả trong Spring Integration

## 1. Vì sao cần JDBC outbound gateway?

Một luồng Spring Integration có thể nhận yêu cầu tra cứu đơn hàng từ HTTP, lấy một event `order.paid` từ Kafka hoặc tiêu thụ message JMS. Sau khi gửi yêu cầu SQL xuống cơ sở dữ liệu, đôi khi bước tiếp theo **cần biết kết quả**:

- Câu `UPDATE` thực sự sửa bao nhiêu hàng?
- Bản ghi được `INSERT` đã được database cấp ID nào?
- Có tìm thấy đơn hàng theo khóa không? Nếu có, các cột trả về là gì?
- Sau khi cập nhật trạng thái, dữ liệu mới nhất để gửi sang hệ thống khác là gì?

**JDBC outbound gateway** đáp ứng kiểu giao tiếp **request–reply** này. Nó nhận một `Message<?>` từ input `MessageChannel`, chạy SQL `UPDATE/INSERT/DELETE` và/hoặc `SELECT` bằng Spring JDBC, rồi gửi **reply message** chứa kết quả tới output channel hoặc `replyChannel` tương ứng. Lớp triển khai là `JdbcOutboundGateway`, một `AbstractReplyProducingMessageHandler`.

Chủ đề thuộc chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối các hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`; những hệ thống đó có thể là file, SFTP, HTTP, JMS, AMQP, Kafka hoặc database. Ở JDBC outbound gateway, trọng tâm là **hợp đồng request/reply, ánh xạ tham số, kiểu kết quả, transaction và lỗi**.

~~~mermaid
flowchart LR
    A["HTTP / Kafka / JMS / Service"] --> B["Message<Command>"]
    B --> C["requestChannel"]
    C --> D["JDBC outbound gateway"]
    D --> E["DataSource / JdbcTemplate"]
    E --> F[("Database")]
    F -->|"Rows / update count / generated keys"| E
    E --> D
    D --> G["Message<Result>"]
    G --> H["replyChannel"]
    H --> I["Router / HTTP reply / next adapter"]
~~~

**Không nhầm:** *outbound* mô tả hướng gọi **ra database**, không phải outbound HTTP. *Gateway* phải tạo **reply** cho flow; khác với JDBC outbound channel adapter chỉ thực hiện DML một chiều.

## 2. Đặt gateway đúng vị trí giữa các JDBC endpoint

| Endpoint | Ai kích hoạt? | Lệnh SQL | Trả kết quả cho flow? |
|---|---|---|---|
| JDBC inbound channel adapter | Poller | `SELECT` theo lịch | Phát message từ DB, không có cặp request–reply |
| JDBC outbound channel adapter | Message đến channel | DML: `INSERT/UPDATE/DELETE` | **Không** tạo reply nghiệp vụ |
| **JDBC outbound gateway** | **Message đến request channel** | **DML**, **SELECT**, hoặc **DML + SELECT** | **Có**: update count, generated keys, rows |
| Stored procedure inbound adapter | Poller | Gọi procedure/function | Phát kết quả định kỳ |
| Stored procedure outbound adapter | Message đến channel | Gọi procedure gây side effect | Không tạo reply |
| Stored procedure outbound gateway | Message đến channel | Procedure/function và OUT/result sets | Có reply theo hợp đồng procedure |

Hãy chọn JDBC outbound gateway khi downstream thật sự cần kết quả. Ví dụ `UPDATE ... WHERE id=? AND status=?` có thể tác động **0 hàng** dù SQL không ném lỗi. Nếu nghiệp vụ cần phát `order.updated` chỉ khi một hàng đã đổi trạng thái, gateway giúp lấy update count để router quyết định.

Với thao tác phức tạp gồm nhiều câu SQL, domain validation và transaction riêng, service activator gọi `JdbcTemplate` hoặc một service repository có thể dễ bảo trì hơn. Gateway phù hợp khi request–reply SQL có hợp đồng đủ rõ và có thể định nghĩa ở một endpoint.

## 3. Ba kiểu reply chính và kiểu payload cần dự đoán

Theo Spring Integration JDBC, reply phụ thuộc chế độ SQL:

| Cấu hình gateway | Reply payload thường gặp | Ghi chú |
|---|---|---|
| **Chỉ `update`**, không `query` và không generated keys | `Map` chứa `UPDATED`, ví dụ `{UPDATED=1}` | Cho biết tổng số hàng bị tác động |
| **`update` với `keysGenerated=true`** | Map/list các **generated keys** theo JDBC driver | Tên cột/key và hỗ trợ phụ thuộc database |
| **Chỉ `query`** | Một row, hoặc list rows tùy `maxRows` | Có thể dùng cho tra cứu theo message |
| **`update` + `query`** | Kết quả `SELECT` sau thao tác update | Đặt hợp đồng SELECT và transaction rõ |
| `query` không có bản ghi, dạng list | **List rỗng** kể từ Spring Integration 6.0 | Không tự đồng nghĩa “không có reply” |

Ví dụ:

~~~text
Message<{orderId:"ORD-1001",status:"PAID"}>
    -> UPDATE order_projection SET status='PAID' WHERE order_id='ORD-1001'
    -> Reply Message<{UPDATED=1}>

Message<{orderId:"ORD-1001"}>
    -> SELECT order_id,status,total_amount FROM order_projection ...
    -> Reply Message<OrderView>    (maxRows mặc định là 1)
~~~

Với `maxRows(0)`, kết quả `SELECT` có thể là `List<OrderView>`, kể cả khi tìm thấy 0 hoặc 1 hàng. Đừng viết consumer luôn ép kiểu `List` nếu bạn đang để gateway lấy **một row**; cũng không ép reply thành một row đơn nếu đã yêu cầu lấy **nhiều rows**.

**Hai phạm vi khác nhau:** SQL `UPDATE` trả `UPDATED=0` không đồng nghĩa một câu `SELECT` trả list rỗng. Hai trường hợp biểu đạt những điều kiện nghiệp vụ khác nhau và cần được kiểm tra riêng.

## 4. Dự án và schema chạy thử

Ví dụ dùng Java 17+, Spring Boot, Spring Integration JDBC, Spring JDBC và H2 cho các câu SQL chuẩn. Nên để Spring Boot BOM quản lý các phiên bản tương thích:

~~~groovy
// build.gradle - dependencies
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
    url: "jdbc:h2:mem:jdbc_gateway_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

Trong `src/main/resources/schema.sql` của dự án **ví dụ**, có thể đặt:

~~~sql
CREATE TABLE order_projection (
    order_id      VARCHAR(64) PRIMARY KEY,
    status        VARCHAR(32) NOT NULL,
    total_amount  DECIMAL(18, 2) NOT NULL,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE order_audit (
    audit_id   BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id   VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL
);
~~~

Dữ liệu thử:

~~~sql
INSERT INTO order_projection (order_id, status, total_amount)
VALUES ('ORD-1001', 'RECEIVED', 125000.00),
       ('ORD-1002', 'RECEIVED', 75000.00),
       ('ORD-1003', 'SHIPPED', 30000.00);
~~~

Trong ứng dụng production, dùng migration (Flyway/Liquibase) để quản lý schema, quyền truy cập tối thiểu và backup. H2 là lựa chọn thuận tiện để giải thích SQL; generated keys, locking, isolation và kiểu dữ liệu có thể khác PostgreSQL, MySQL, SQL Server hoặc Oracle.

### 4.1. Java DSL được giới thiệu từ Spring Integration 7.0

Các ví dụ `Jdbc.outboundGateway(...)` sau đây dành cho **Spring Integration 7.x**. Tài liệu chính thức ghi nhận factory `org.springframework.integration.jdbc.dsl.Jdbc` có từ **7.0**. Nếu dự án dùng **6.x**, không sao chép các DSL factory này: mục 11 trình bày `JdbcOutboundGateway` + `@ServiceActivator` hoặc XML.

Trong 7.x, lớp handler chính nằm trong package `org.springframework.integration.jdbc.outbound.JdbcOutboundGateway`; với 6.x, dùng `org.springframework.integration.jdbc.JdbcOutboundGateway`. Luôn kiểm tra import và cấu hình theo phiên bản dependency đang chạy.

## 5. Ví dụ 1: UPDATE và nhận số hàng bị tác động

### 5.1. Hợp đồng request

Luồng nhận payload dạng `Map<String, Object>` gồm:

~~~json
{
  "orderId": "ORD-1001",
  "expectedStatus": "RECEIVED",
  "newStatus": "PAID"
}
~~~

Câu SQL dùng các named parameters từ message:

~~~sql
UPDATE order_projection
SET status = :payload[newStatus],
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = :payload[orderId]
  AND status = :payload[expectedStatus];
~~~

Điều kiện `AND status = :payload[expectedStatus]` là một **optimistic check đơn giản**: nếu một luồng khác đã thay trạng thái, update count có thể bằng 0. Với sản phẩm thực tế, nên dùng `version` hoặc quy tắc state transition rõ ràng để chống cập nhật ngược trạng thái.

### 5.2. Java DSL 7.x

~~~java
package com.example.jdbc;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OrderUpdateGatewayFlow {

    @Bean
    public MessageChannel statusRequests() {
        return new DirectChannel();
    }

    @Bean
    public PollableChannel statusReplies() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow updateOrderStatus(
            DataSource dataSource,
            @Qualifier("statusRequests") MessageChannel requests) {
        return IntegrationFlow.from(requests)
            .handle(Jdbc.outboundGateway(dataSource,
                "UPDATE order_projection "
              + "SET status = :payload[newStatus], "
              + "    updated_at = CURRENT_TIMESTAMP "
              + "WHERE order_id = :payload[orderId] "
              + "  AND status = :payload[expectedStatus]"))
            .channel("statusReplies")
            .get();
    }
}
~~~

**Giải thích từng điểm:**

1. `statusRequests` là input `DirectChannel`; message đến đây kích hoạt gateway ngay trong đường dispatch đồng bộ.
2. `Jdbc.outboundGateway(dataSource, updateSql)` tạo `JdbcOutboundGateway` và cấu hình DML.
3. `:payload[orderId]`, `:payload[newStatus]` và `:payload[expectedStatus]` được lấy từ **payload Map của request message**, không nối trực tiếp dữ liệu đầu vào thành SQL string.
4. Handler chạy SQL và tạo reply; nếu một hàng cập nhật, reply payload là map chứa `UPDATED=1`.
5. `.channel("statusReplies")` đưa reply sang `QueueChannel` để demo/test có thể dùng `receive()`. Trong một workflow đồng bộ thực, có thể thay bằng router/service activator.
6. `statusReplies` là **output reply channel**, không phải poller đọc dữ liệu từ database; `receive()` chỉ là cách ứng dụng kiểm tra kết quả đã phát.

### 5.3. Gửi message và đọc reply

~~~java
import java.util.Map;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

// requests và replies được inject qua @Qualifier tương ứng.
boolean sent = requests.send(MessageBuilder.withPayload(
    Map.of(
        "orderId", "ORD-1001",
        "expectedStatus", "RECEIVED",
        "newStatus", "PAID"))
    .setHeader("correlationId", "req-1001")
    .build());

if (!sent) {
    throw new IllegalStateException("Request was not accepted");
}

Message<?> reply = replies.receive(1_000);
if (reply == null) {
    throw new IllegalStateException("No JDBC reply received");
}

Map<?, ?> result = (Map<?, ?>) reply.getPayload();
Number updated = (Number) result.get("UPDATED");
System.out.println("Updated rows = " + updated.intValue());
~~~

Giả định `requests` là `MessageChannel` bean `statusRequests` và `replies` là `PollableChannel` bean `statusReplies`. Đây là hai bean phải được inject hoặc lấy từ Spring context; các biến không tự có trong một static `main`.

**`UPDATED=1`** có nghĩa câu UPDATE tác động một hàng; **`UPDATED=0`** có nghĩa không có hàng nào khớp predicate. Một câu UPDATE trả về 0 không mặc nhiên ném exception, và cũng không tự chứng minh đơn hàng không tồn tại: có thể là **đơn đã đổi trạng thái**. Cần phân biệt not-found và conflict khi workflow thực sự yêu cầu.

### 5.4. Vì sao input channel không quyết định transaction đã commit?

Trong ví dụ `DirectChannel`, JDBC handler chạy đồng bộ. Nếu không có transaction bao ngoài, database thường thực hiện/commit theo cấu hình JDBC. Nhưng nếu `requests.send(...)` được gọi bên trong một `@Transactional` chưa hoàn tất, transaction có thể **rollback sau khi reply `UPDATED=1` đã được phát**. Reply nói về câu lệnh SQL đã thực hiện, **không phải chứng thư commit bền vững cuối cùng**.

## 6. Route theo update count và hợp đồng nghiệp vụ

Nếu cần logic “cập nhật đúng 1 dòng thì phát event, bằng 0 thì báo xung đột”, một router có thể đọc `UPDATED`:

~~~java
import org.springframework.integration.dsl.IntegrationFlow;
import java.util.Map;

@Bean
IntegrationFlow routeUpdateResult() {
    return IntegrationFlow.from("statusResultInput")
        .route(message -> {
            Map<?, ?> map = (Map<?, ?>) message.getPayload();
            int updated = ((Number) map.get("UPDATED")).intValue();
            return updated == 1 ? "updated" : "notUpdated";
        }, mapping -> mapping
            .channelMapping("updated", "updatedOrders")
            .channelMapping("notUpdated", "conflictedOrders"))
        .get();
}
~~~

Đây là **flow minh họa tách riêng**; muốn dùng cùng ví dụ mục 5, thay output channel của gateway thành `statusResultInput`, thay vì cho cả `statusReplies` và `statusResultInput` tiêu thụ một reply mà không có publish-subscribe design. Đầu vào của router phải đúng là `Map` với `UPDATED`; không dùng lại router này cho `SELECT` trả DTO hoặc `INSERT` trả generated keys.

Với command idempotent, `UPDATED=0` chưa chắc là lỗi: nếu event đã được xử lý trước đó, database có thể đang ở trạng thái mong muốn. Khi quyết định ACK Kafka/JMS, nên đối soát state/event ID thay vì coi mọi số 0 là “chưa xử lý”.

## 7. Ví dụ 2: SELECT theo request message và trả một row

Không phải gateway nào cũng cần cập nhật. Từ Spring Integration 2.2, `JdbcOutboundGateway` cho phép **chỉ có truy vấn SELECT**, hữu ích cho enrich payload hoặc phản hồi tra cứu HTTP.

### 7.1. Dùng Java DSL 7.x với chỉ SELECT

~~~java
package com.example.jdbc;

import java.math.BigDecimal;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;

@Configuration
public class OrderLookupFlow {

    public record OrderView(
        String orderId, String status, BigDecimal totalAmount) { }

    @Bean
    public IntegrationFlow lookupOrder(DataSource dataSource) {
        return IntegrationFlow.from("lookupRequests")
            .handle(Jdbc.outboundGateway(
                    dataSource,
                    null, // Không chạy UPDATE.
                    "SELECT order_id, status, total_amount "
                  + "FROM order_projection "
                  + "WHERE order_id = :payload[orderId]")
                .maxRows(1)
                .rowMapper((rs, rowNum) -> new OrderView(
                    rs.getString("order_id"),
                    rs.getString("status"),
                    rs.getBigDecimal("total_amount"))))
            .channel("lookupReplies")
            .get();
    }
}
~~~

**Chú ý:** overload ba tham số `Jdbc.outboundGateway(dataSource, updateQuery, selectQuery)` thể hiện rõ chế độ kết hợp. Theo hợp đồng JDBC outbound gateway, `updateQuery` có thể được bỏ khi chỉ cần `SELECT`; ở đây dùng `null` để mô tả “không có DML”, còn `selectQuery` luôn có. Nếu đang ở phiên bản thư viện khác, đối chiếu constructor/factory trước khi dùng.

Với `maxRows(1)` và một row trúng điều kiện, reply payload là **`OrderView` đơn**, không phải `List<OrderView>`. Nếu không cấu hình `rowMapper`, mapper mặc định tạo `Map<String, Object>` theo tên cột.

Một message input ví dụ:

~~~java
Map<String, String> criteria = Map.of("orderId", "ORD-1001");
lookupRequests.send(MessageBuilder.withPayload(criteria).build());
~~~

Để thử đoạn cuối, `lookupRequests` cần được inject thành `MessageChannel`, `MessageBuilder` cần import, và `lookupReplies` phải có downstream consumer (hoặc bean `QueueChannel` để `receive()`). Nên luôn kiểm tra result type bằng test thay vì giả định mọi SELECT trả list.

### 7.2. Không có row và một row khác nhau

Với `SELECT` không tìm thấy kết quả, hình dạng response phụ thuộc `maxRows` và hành vi phiên bản. Từ Spring Integration **6.0**, khi kết quả là một danh sách rỗng, gateway **giữ danh sách rỗng làm reply** thay vì chuyển thành `null` mang ý nghĩa “không có reply”.

Không nên sử dụng quy tắc “không nhận reply nghĩa là database không có record”. Với tra cứu một row, cần viết test cho **0 row**, **1 row** và **nhiều row** trong phiên bản đang chạy, đặc biệt nếu upstream HTTP gateway còn có reply timeout.

Nếu yêu cầu API công khai cần trả `404 Not Found`, hãy ánh xạ điều kiện không tìm thấy tại tầng nghiệp vụ, không để một `List<?>` rỗng vô tình trở thành HTTP `200` thành công không rõ ý nghĩa.

## 8. `maxRows`: một hàng, nhiều hàng, danh sách rỗng

Mặc định `maxRows` của JDBC outbound gateway là **1** đối với `SELECT`. Với những truy vấn cần trả tất cả các dòng, đặt `maxRows(0)`.

~~~java
@Bean
IntegrationFlow listOrders(DataSource dataSource) {
    return IntegrationFlow.from("listOrderRequests")
        .handle(Jdbc.outboundGateway(
                dataSource,
                null,
                "SELECT order_id, status, total_amount "
              + "FROM order_projection "
              + "WHERE status = :payload[status] "
              + "ORDER BY order_id")
            .maxRows(0)
            .rowMapper((rs, rowNum) ->
                new OrderLookupFlow.OrderView(
                    rs.getString("order_id"),
                    rs.getString("status"),
                    rs.getBigDecimal("total_amount"))))
        .channel("listOrderReplies")
        .get();
}
~~~

Với input `{"status":"RECEIVED"}`, reply có thể là `List<OrderView>` gồm nhiều record. Khi `maxRows(0)`, danh sách rỗng vẫn là kết quả có nghĩa: “truy vấn thành công nhưng không tìm thấy hàng phù hợp”.

| Giá trị cấu hình | Ý nghĩa thực tế | Reply downstream |
|---|---|---|
| Không đặt `maxRows` | Mặc định giới hạn 1 | Thường một row/map/DTO khi có dữ liệu |
| `maxRows(1)` | Lấy tối đa một hàng | Thường một row khi có dữ liệu |
| `maxRows(5)` | Giới hạn tối đa 5 hàng | Trường hợp nhiều hàng trả list; hãy test khi chỉ có một hàng |
| `maxRows(0)` | Không áp giới hạn số rows của gateway | Danh sách các row, có thể rỗng |

**Không dùng `maxRows(0)` để lấy một bảng hàng triệu dòng trong một message** nếu không có ràng buộc. Gateway thường materialize kết quả `SELECT` thành bộ sưu tập trước khi phát reply. Với data set lớn cần pagination, keyset cursor, giới hạn kết quả, batch hoặc một streaming protocol thích hợp.

### 8.1. Khi muốn mỗi row là một message

Nếu `maxRows(0)` trả `List<OrderView>`, downstream có thể dùng splitter:

~~~java
.handle(Jdbc.outboundGateway(dataSource, null, selectSql)
    .maxRows(0)
    .rowMapper(orderRowMapper))
.split()
.channel("oneOrderPerMessage")
~~~

Đây là **mảnh Java DSL**; `selectSql` và `orderRowMapper` là các biến/bean do ứng dụng cung cấp. `split()` biến phần tử của list thành các messages riêng; nó **không** khiến JDBC query trở nên reactive hoặc biến SQL thành cursor streaming với backpressure tự động.

## 9. Ví dụ 3: INSERT và nhận generated keys

Khi bảng dùng primary key tự tăng, outbound gateway có thể lấy khóa vừa được database tạo. Ví dụ bảng `order_audit` trong mục 4:

~~~sql
INSERT INTO order_audit (order_id, event_type)
VALUES (?, ?);
~~~

Java DSL:

~~~java
package com.example.jdbc;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;

@Configuration
public class OrderAuditGatewayFlow {

    @Bean
    public IntegrationFlow insertAuditAndReturnKey(DataSource dataSource) {
        return IntegrationFlow.from("auditRequests")
            .handle(Jdbc.outboundGateway(dataSource,
                    "INSERT INTO order_audit (order_id, event_type) "
                  + "VALUES (?, ?)")
                .requestPreparedStatementSetter((ps, message) -> {
                    // Giả định payload là Map<String,Object>.
                    var payload = (java.util.Map<?, ?>) message.getPayload();
                    ps.setString(1, payload.get("orderId").toString());
                    ps.setString(2, payload.get("eventType").toString());
                })
                .keysGenerated(true))
            .channel("auditKeys")
            .get();
    }
}
~~~

Trong ví dụ:

1. `requestPreparedStatementSetter(...)` dùng `MessagePreparedStatementSetter` để bind `?` trực tiếp từ request message.
2. `keysGenerated(true)` yêu cầu JDBC lấy generated keys (không phải tất cả DB/driver đều hỗ trợ cách lấy khóa giống nhau).
3. Gateway trả kết quả khóa bằng cấu trúc Map/list map phụ thuộc DB driver, cấu hình và số rows; **không hardcode** rằng tên key luôn là `audit_id` hoặc `ID`.
4. Hãy kiểm tra reply thực tế và chuyển đổi thành một DTO `AuditCreated(auditId, ...)` trong một transformer có validation nếu downstream cần type ổn định.

**Không cấu hình `requestPreparedStatementSetter` và `requestSqlParameterSourceFactory` cùng lúc khi cả hai đang định nghĩa cách bind cùng câu UPDATE/INSERT.** Đây là hai chiến lược thay thế, phù hợp với kiểu SQL/DTO khác nhau.

### 9.1. Generated key không đồng nghĩa idempotency

Nếu ứng dụng timeout hoặc broker redeliver sau khi INSERT đã commit, retry có thể tạo **hai** audit rows với **hai generated IDs**. Nếu thao tác phải thực thi một lần theo `eventId`, dùng unique constraint hoặc bảng idempotency; đừng chỉ dựa vào khóa tự sinh.

## 10. Ví dụ 4: UPDATE rồi SELECT và trả bản ghi mới

Gateway có thể thực thi DML trước rồi `SELECT` để lấy trạng thái hiện tại trong cùng lần xử lý message. Điều này hữu ích cho use case “đổi trạng thái đơn rồi trả DTO”.

~~~java
@Bean
IntegrationFlow updateAndRead(DataSource dataSource) {
    return IntegrationFlow.from("updateAndReadRequests")
        .handle(Jdbc.outboundGateway(
                dataSource,
                "UPDATE order_projection "
              + "SET status = :payload[newStatus], "
              + "    updated_at = CURRENT_TIMESTAMP "
              + "WHERE order_id = :payload[orderId]",
                "SELECT order_id, status, total_amount "
              + "FROM order_projection "
              + "WHERE order_id = :payload[orderId]")
            .maxRows(1)
            .rowMapper((rs, n) -> new OrderLookupFlow.OrderView(
                rs.getString("order_id"),
                rs.getString("status"),
                rs.getBigDecimal("total_amount"))))
        .channel("orderAfterUpdate")
        .get();
}
~~~

**Hai bước có ý nghĩa khác nhau:**

- `UPDATE` quyết định thay đổi nào được áp dụng. Nếu không có dòng phù hợp, UPDATE có thể trả 0.
- `SELECT` quyết định **reply payload** mà downstream nhận. Nếu query trả row, downstream có thể nhận `OrderView` dù UPDATE không sửa dòng nào (ví dụ bản ghi đã ở trạng thái mong muốn hoặc predicate khác).

**Cẩn trọng về transaction và tính nhất quán:** khi cần bảo đảm `UPDATE + SELECT` thuộc cùng một transaction/isolation boundary, phải thiết kế transaction manager rõ ràng. `JdbcOutboundGateway` là endpoint đồng bộ nhưng không tự thay thế mọi kiểm soát concurrency hoặc transaction của nghiệp vụ. Dữ liệu SELECT có thể bị thay đổi bởi giao dịch khác theo isolation/locking của database.

Nếu downstream cần **cả update count và bản ghi**, đừng giả định gateway tự trả một tuple `(UPDATED, OrderView)`. Có thể dùng service activator thực hiện SQL trong transaction rồi tạo DTO riêng, hoặc tách các chặng với hợp đồng lưu/đối soát rõ.

### 10.1. Truy vấn sau INSERT với khóa sinh

Khi cấu hình `keysGenerated(true)`, nguồn tham số mặc định cho **reply SELECT** có thể là **generated keys** (map hoặc list các maps) thay vì request message ban đầu. Câu `SELECT` phải tham chiếu đúng khóa JDBC trả về, với tên cột được driver hỗ trợ; nếu không, có thể gặp lỗi binding hoặc truy vấn không có dòng.

Đây là một trong những lý do cần test cả generated-key reply và SELECT-after-INSERT trên database/driver production. H2, PostgreSQL, SQL Server và Oracle không nhất thiết dùng cùng tên key hoặc chiến lược trả generated keys.

## 11. Binding SQL: named parameters, PreparedStatement và RowMapper

JDBC outbound gateway có hai phía binding:

1. **Request side:** bind tham số cho `UPDATE/INSERT/DELETE` nếu có DML.
2. **Reply side:** bind tham số cho `SELECT` nếu có truy vấn đọc kết quả.

Nếu dùng named parameters, root context mặc định có thể truy cập request `payload` và `headers`:

~~~sql
UPDATE order_projection
SET status = :payload[newStatus]
WHERE order_id = :payload[orderId];

SELECT *
FROM order_projection
WHERE order_id = :payload[orderId];
~~~

Các ví dụ trên giả định `payload` là một Map có key phù hợp. Với DTO Java record, phải kiểm tra khả năng truy cập property trong parameter source hoặc tạo factory/binder tường minh; không giả định mọi field name camelCase sẽ tự tương ứng với cột SQL snake_case.

| Cơ chế | Dùng cho | Điểm cần lưu ý |
|---|---|---|
| Named parameters `:payload[orderId]` | Câu lệnh SQL cần giá trị message | Dựa trên root context và property paths |
| `requestSqlParameterSourceFactory` | DML binding tùy biến | Có thể dùng biểu thức chuyển đổi/kiểu |
| `requestPreparedStatementSetter` | Bind JDBC `?` trực tiếp cho DML | Chỉ số tham số bắt đầu từ 1 |
| `replySqlParameterSourceFactory` | `SELECT` binding riêng | Quan trọng khi SELECT dùng generated keys |
| `rowMapper(...)` | Ánh xạ từng JDBC row thành Java object | Tránh downstream phụ thuộc `Map` tên cột tùy driver |

### 11.1. RowMapper để tránh ép kiểu map khắp flow

~~~java
import org.springframework.jdbc.core.RowMapper;
import java.math.BigDecimal;

RowMapper<OrderLookupFlow.OrderView> mapper = (rs, rowNum) ->
    new OrderLookupFlow.OrderView(
        rs.getString("order_id"),
        rs.getString("status"),
        rs.getBigDecimal("total_amount"));
~~~

Các tên cột trong `RowMapper` phải khớp với `SELECT` hoặc alias. Với SQL columns có thể `NULL`, cần xử lý null rõ ràng (chẳng hạn `ResultSet.wasNull()` đối với primitive), thay vì âm thầm tạo giá trị business sai.

### 11.2. Chống SQL injection

PreparedStatement placeholders và named parameters là cách bind **giá trị**, không phải cách bind tên bảng, tên cột, `ORDER BY` tùy ý hoặc toàn bộ mệnh đề SQL. Nếu input yêu cầu sort hoặc table đích khác nhau, chọn từ allowlist do ứng dụng kiểm soát; không nối `payload.tableName` vào SQL.

## 12. Spring Integration 6.x: Java bean và XML

Ở 6.x, chưa có `Jdbc.outboundGateway(...)` của JDBC Java DSL 7.x. Lớp `JdbcOutboundGateway` vẫn tồn tại và có thể đăng ký làm `MessageHandler` trả reply.

### 12.1. Tạo handler bean trực tiếp

~~~java
package com.example.jdbc;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.jdbc.JdbcOutboundGateway;
import org.springframework.messaging.MessageHandler;

@Configuration
public class LegacyJdbcGatewayConfiguration {

    @Bean
    @ServiceActivator(
        inputChannel = "legacyStatusRequests",
        outputChannel = "legacyStatusReplies")
    public MessageHandler jdbcStatusGateway(DataSource dataSource) {
        return new JdbcOutboundGateway(
            dataSource,
            "UPDATE order_projection "
          + "SET status = :payload[newStatus] "
          + "WHERE order_id = :payload[orderId]");
    }
}
~~~

Đây là **phương án 6.x** để tạo outbound gateway. Nếu cần SELECT, dùng constructor có `selectQuery`, có thể cấu hình `setMaxRows(...)`/`setRowMapper(...)`. Để dùng trong 7.x với handler thủ công, import `org.springframework.integration.jdbc.outbound.JdbcOutboundGateway`.

### 12.2. Cấu hình XML

~~~xml
<!-- Fragment trong Spring XML có khai báo namespace int/int-jdbc. -->
<int:channel id="orderLookupRequests"/>
<int:channel id="orderLookupReplies"/>

<int-jdbc:outbound-gateway
    id="orderLookupGateway"
    request-channel="orderLookupRequests"
    reply-channel="orderLookupReplies"
    data-source="dataSource"
    query="SELECT order_id, status, total_amount
           FROM order_projection
           WHERE order_id = :payload[orderId]"
    max-rows="1"/>
~~~

Ở dạng XML, `query` có thể đứng độc lập mà không cần `update`, theo hợp đồng JDBC outbound gateway. Đây là một **phương án cấu hình thay thế**, không cần đăng ký thêm Java DSL cho cùng channel.

### 12.3. Update count qua XML

~~~xml
<int-jdbc:outbound-gateway
    id="legacyUpdateGateway"
    request-channel="updateRequests"
    reply-channel="updateReplies"
    data-source="dataSource"
    update="UPDATE order_projection
            SET status = :payload[newStatus]
            WHERE order_id = :payload[orderId]"/>
~~~

Reply mặc định cho DML có map `UPDATED`. Nếu `keys-generated="true"` với INSERT, reply chuyển sang generated keys theo contract DB; đừng cùng lúc kỳ vọng `UPDATED` vẫn là payload chính.

## 13. Reply channel, correlation và request–reply workflow

### 13.1. Reply đi đâu?

`JdbcOutboundGateway` là `AbstractReplyProducingMessageHandler`. Reply có thể được gửi tới output channel định nghĩa trong endpoint hoặc `replyChannel` trong header của request khi không chỉ định output channel cố định.

~~~mermaid
sequenceDiagram
    participant Caller as Request producer
    participant Input as requestChannel
    participant JDBC as JdbcOutboundGateway
    participant DB as Database
    participant Reply as replyChannel
    Caller->>Input: Message<Command> + reply context
    Input->>JDBC: handle
    JDBC->>DB: SQL query/update
    DB-->>JDBC: Rows/count/keys
    JDBC-->>Reply: Message<Result>
    Reply-->>Caller: Theo request-reply contract
~~~

Trong ví dụ `QueueChannel` mục 5, reply đi đến `statusReplies` vì DSL đã khai báo output. Nếu một messaging gateway như `@MessagingGateway` gửi request và chờ reply, cần xem cách `replyChannel` được tạo/truyền; gắn một output channel tĩnh khác có thể khiến caller chờ mãi nếu không có cầu nối về reply context.

**Correlation ID** là dữ liệu giúp đối soát message đầu vào và đầu ra; không coi `MessageHeaders.ID` thay thế hoàn toàn cho business `eventId`. Khi split/list và gửi qua broker, một business event ID ổn định thường hữu ích hơn ID message mới được tạo trong Spring Integration.

### 13.2. Không có reply khác reply rỗng

Một `Message<List<?>>` chứa danh sách rỗng **vẫn là một message**. Trong những phiên bản cũ, kết quả SELECT rỗng từng có thể bị chuyển thành `null` và dẫn đến không có reply; từ Spring Integration 6.0, gateway giữ kết quả danh sách rỗng. Nếu workflow HTTP muốn trả `404` hoặc `204`, phải định nghĩa mapping nghiệp vụ rõ.

Đặc biệt, một `@MessagingGateway` có reply timeout không nên dùng “không thấy reply” để biểu đạt đơn giản rằng DB không có hàng; timeout còn có thể do lỗi channel, handler hoặc transaction.

## 14. Transaction và concurrency: reply không phải commit receipt

### 14.1. DirectChannel và cùng thread

Với `DirectChannel`, gateway thường thực thi SQL trên cùng thread của producer. Nếu có một `@Transactional` đang quản lý connection qua đúng transaction manager, JDBC operations có thể tham gia transaction ấy.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class PaymentService {

    private final org.springframework.messaging.MessageChannel requests;

    PaymentService(
            @org.springframework.beans.factory.annotation.Qualifier(
                "statusRequests")
            org.springframework.messaging.MessageChannel requests) {
        this.requests = requests;
    }

    @Transactional
    public void markPaid(String orderId) {
        // Message request được xử lý trong thread/transaction hiện tại
        // khi qua DirectChannel và handler JDBC đồng bộ.
        // Reply vẫn có thể được phát trước thời điểm outer commit.
        requests.send(
            org.springframework.messaging.support.MessageBuilder
                .withPayload(java.util.Map.of(
                    "orderId", orderId,
                    "expectedStatus", "RECEIVED",
                    "newStatus", "PAID"))
                .build());
    }
}
~~~

**Nếu transaction rollback sau khi gateway đã trả `UPDATED=1`, database không nhất thiết giữ thay đổi cuối cùng.** Vì vậy, không phát một event không thể thu hồi sang Kafka chỉ dựa trên reply update count khi transaction chưa commit.

### 14.2. ExecutorChannel / QueueChannel

Nếu thay `DirectChannel` bằng `ExecutorChannel`, dispatcher chuyển sang worker thread; transaction của sender thường không tự chuyển theo. Với `QueueChannel`/poller, message có thể được xử lý ở thời điểm khác sau khi transaction gửi đã hoàn tất. Điều đó thay đổi cả lỗi, reply timeout và bảo đảm ACK.

| Boundary | Khi nào chạy SQL? | Gợi ý kiểm soát |
|---|---|---|
| DirectChannel | Trong đường gọi sender | Transaction manager, exceptions, commit sau reply |
| ExecutorChannel | Thread executor | Bounded pool/queue, transaction tại worker |
| QueueChannel + poller | Poller nhận message | Poller transaction, error channel, reply timeout |
| Kafka/JMS inbound | Theo listener/adapter | ACK/offset commit, redelivery, idempotency |

**Không có transaction phân tán tự động** giữa JDBC, Kafka, JMS và HTTP chỉ vì tất cả nằm trong một `IntegrationFlow`. Khi cần ghi database rồi gửi event, ưu tiên transactional outbox hoặc một giao thức đảm bảo nhất quán được thiết kế rõ.

### 14.3. Update-and-select có tranh chấp

Một flow “UPDATE trạng thái rồi SELECT bản ghi” có thể bị tác động bởi những transaction khác. Với các business commands cần kiểm soát trạng thái chặt, nên có cột `version`, điều kiện update theo version và xử lý `UPDATED=0`; việc chỉ SELECT lại row không chứng minh lệnh của mình đã được áp dụng.

## 15. Lỗi SQL, timeout, retry và idempotency

Spring JDBC dịch nhiều `SQLException` thành `DataAccessException`; Spring Integration có thể bọc thêm thành `MessagingException` khi handler thất bại. Không nhầm một SQL query thành công nhưng không có row với exception.

| Trường hợp | Kết quả thường thấy | Hành động hợp lý |
|---|---|---|
| UPDATE không khớp hàng | `UPDATED=0` | Phân biệt not-found, stale version hoặc duplicate |
| Trùng primary/unique key | `DuplicateKeyException` | Kiểm tra idempotency/conflict; không retry vô hạn |
| Vi phạm constraint | `DataIntegrityViolationException` | Validation/contract error |
| DB mất kết nối tạm thời | `DataAccessResourceFailureException` hoặc driver cause | Retry có giới hạn, xác định outcome |
| Deadlock/serialization | Transient data access exception tùy DB | Rollback và retry **toàn transactional unit** |
| SELECT không có row | Reply rỗng theo shape/version | Not-found logic riêng |
| SELECT quá nhiều rows | Memory/latency tăng | Giới hạn `maxRows`, pagination và indexes |
| Transaction rollback sau reply | Reply có thể từng chứa `UPDATED=1` nhưng data rollback | Chỉ công bố side effect sau commit |
| Payload sai type/key | Binding exception | Sửa transformer, không retry như network |

### 15.1. Retry sau timeout có thể gây tác dụng trùng

Client có thể mất kết nối **sau khi database đã commit INSERT**. Retry cùng yêu cầu có thể tạo một row mới với generated key khác. Đối với giao dịch quan trọng, dùng:

1. **Business key/idempotency key** ổn định và unique constraint.
2. **Transaction** ghi nghiệp vụ cùng idempotency record.
3. **Outbox** cho bước publish event sau DB commit.
4. **Retry policy** theo lỗi transient, backoff/jitter, giới hạn attempts.
5. **Reconciliation** khi outcome không chắc chắn.

Không dựa vào `keysGenerated(true)` để chống tạo trùng: generated key chỉ cho biết ID DB cấp trong một attempt, không xác nhận sự kiện nghiệp vụ đã được xử lý đúng một lần.

### 15.2. Error channel

Với `DirectChannel`, lỗi SQL đồng bộ có thể đi ngược về caller; với executor/poller, lỗi có thể được xử lý qua `ErrorMessage`/`errorChannel` của endpoint. Đừng giả định mọi lỗi tự động thành reply payload `{ERROR=...}`: gateway bình thường trả **kết quả SQL**, còn lỗi có đường xử lý riêng. Kiểm tra nơi error xảy ra trước/sau ACK nguồn để quyết định retry/DLQ.

## 16. JDBC là blocking I/O: hiệu năng và vận hành

`JdbcOutboundGateway` chạy qua JDBC driver đồng bộ. Nếu gọi nó từ WebFlux inbound handler chạy trên Reactor Netty event loop, thao tác chờ connection hoặc query có thể chặn event loop.

**Cách tổ chức an toàn hơn:** xử lý JDBC trên worker thread có giới hạn, ví dụ `ExecutorChannel` hoặc các scheduler thích hợp, nhưng phải quản lý transaction và reply timeout tương ứng. Nếu ứng dụng cần pipeline reactive database thực sự, xem xét R2DBC; **đổi thread không biến JDBC thành non-blocking**.

Nên đo:

- Connection pool active/idle/pending và thời gian chờ connection.
- Thời gian SQL update/SELECT, transaction duration, locks/deadlocks.
- Số rows `UPDATED=0`, `UPDATED=1` và bất thường `UPDATED>1`.
- Kích thước result set, thời gian mapping và sử dụng heap.
- In-flight messages, queue depth, request/reply latency và timeout.
- Retry, error channel, dead-letter, rollback, idempotency conflicts.

Không tăng `maxRows(0)` hoặc thread count vô hạn để cải thiện throughput. Kết quả lớn, query thiếu index và nhiều giao dịch tranh locks đều có thể làm toàn flow chậm hơn.

## 17. Kiểm thử gateway: kiểm tra reply và dữ liệu DB

### 17.1. Spring Boot + H2 test cho UPDATE count

Với `schema.sql` và `data.sql` tương ứng mục 4:

~~~java
package com.example.jdbc;

import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class JdbcOutboundGatewayTest {

    @Autowired
    @Qualifier("statusRequests")
    MessageChannel requests;

    @Autowired
    @Qualifier("statusReplies")
    PollableChannel replies;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void updateReturnsAffectedRowCount() {
        // Điều kiện dữ liệu test: ORD-1001 có status RECEIVED.
        jdbc.update(
            "UPDATE order_projection SET status = ? WHERE order_id = ?",
            "RECEIVED", "ORD-1001");

        boolean sent = requests.send(MessageBuilder
            .withPayload(Map.of(
                "orderId", "ORD-1001",
                "expectedStatus", "RECEIVED",
                "newStatus", "PAID"))
            .build());
        assertTrue(sent);

        Message<?> reply = replies.receive(1_000);
        assertNotNull(reply);
        Map<?, ?> result = (Map<?, ?>) reply.getPayload();
        assertEquals(1, ((Number) result.get("UPDATED")).intValue());

        String status = jdbc.queryForObject(
            "SELECT status FROM order_projection WHERE order_id = ?",
            String.class, "ORD-1001");
        assertEquals("PAID", status);
    }

    @Test
    void missingOrderReturnsZeroUpdated() {
        boolean sent = requests.send(MessageBuilder
            .withPayload(Map.of(
                "orderId", "ORD-DOES-NOT-EXIST",
                "expectedStatus", "RECEIVED",
                "newStatus", "PAID"))
            .build());
        assertTrue(sent);

        Message<?> reply = replies.receive(1_000);
        assertNotNull(reply);
        Map<?, ?> result = (Map<?, ?>) reply.getPayload();
        assertEquals(0, ((Number) result.get("UPDATED")).intValue());
    }
}
~~~

Các test ở trên giả định **không có consumer khác** đang lấy message từ `statusReplies` và dữ liệu fixture không bị test chạy song song sửa ngoài ý muốn. Với `QueueChannel`, reply được lấy bằng `receive()`; nếu production dùng router/service activator thay vì queue, hãy test output tương ứng.

### 17.2. Ma trận kiểm thử SELECT/generated keys

| Trường hợp | Điều cần khẳng định |
|---|---|
| DML tác động đúng một hàng | Reply `UPDATED=1`, DB đổi đúng dữ liệu |
| DML không khớp hàng | Reply `UPDATED=0`, không tự thành exception |
| DML ảnh hưởng nhiều hàng ngoài dự kiến | Cảnh báo hoặc từ chối nếu hợp đồng yêu cầu đúng một |
| SELECT với `maxRows(1)` | Kiểu payload một row khi có kết quả |
| SELECT với `maxRows(0)` | Reply list, kể cả list rỗng |
| SELECT không có dữ liệu | Mapping `404`/`NOT_FOUND` theo hợp đồng, không nhầm timeout |
| INSERT generated keys | Kiểu/nội dung reply khớp JDBC driver thật |
| INSERT rồi SELECT theo generated keys | Binding tên khóa đúng trên DB production |
| UPDATE + SELECT | Dữ liệu sau update và transaction isolation đúng |
| Schema/parameter sai | Lỗi được xử lý theo error flow, không thành success |
| Transaction rollback sau reply | Không phát event bền vững trước DB commit |
| Source Kafka/JMS redelivery | Không nhân đôi effect, ACK/retry có kiểm soát |

Đặc biệt, cần chạy integration test với DB production-compatible cho generated keys, transaction isolation, deadlocks và row count. H2 có thể không tái hiện hết semantics của SQL Server, PostgreSQL hoặc Oracle.

## 18. Những sai lầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “JDBC outbound gateway là poller đọc DB liên tục” | Gateway **được kích hoạt bằng request message** |
| “Outbound adapter và outbound gateway đều trả kết quả” | Adapter một chiều không phát reply |
| “UPDATE 0 hàng chắc chắn ném exception” | Thường là kết quả `UPDATED=0` |
| “`UPDATED=1` có nghĩa transaction bao ngoài đã commit” | Reply có thể phát **trước** outer commit |
| “SELECT gateway luôn trả `List`” | Mặc định `maxRows=1`, có thể trả một row |
| “SELECT 0 hàng luôn nghĩa không có reply” | Từ SI 6.0, empty list được giữ thay vì đổi sang null |
| “`maxRows(0)` là lấy 0 rows” | Nó cho phép lấy **tất cả** rows của query |
| “Generated keys luôn mang tên `ID`” | Tên/shape phụ thuộc JDBC driver/DB |
| “RowMapper khiến JDBC trở thành reactive” | JDBC vẫn là blocking |
| “`Jdbc.outboundGateway` có trong mọi bản 6.x” | Java DSL JDBC factory được thêm từ 7.0 |
| “Request SQL parameter factory và PreparedStatement setter cần bật cùng lúc” | Chúng là các cách bind thay thế cho DML |
| “Gateway UPDATE+SELECT luôn trả cả update count và row” | SELECT quyết định reply payload khi có query |
| “Có khóa tự sinh thì retry chắc chắn không trùng” | Cần unique business key/idempotency |

## 19. Bài thực hành

1. Khởi tạo schema H2 và gửi UPDATE qua `Jdbc.outboundGateway(...)`. Kiểm tra reply `{UPDATED=1}` và giá trị DB.
2. Gửi request `orderId` không tồn tại; xác nhận `UPDATED=0` và xây một router xử lý not-found/conflict.
3. Đổi predicate UPDATE để thêm `expectedStatus`; thử hai command chạy đồng thời, đánh giá race và độ tin cậy.
4. Tạo flow SELECT theo `orderId` với `maxRows(1)` và `RowMapper<OrderView>`; kiểm tra reply một row.
5. Đổi thành `maxRows(0)`, trả nhiều rows; dùng `split()` để đưa từng row vào `MessageChannel` riêng.
6. Cho SELECT không khớp row; kiểm tra empty list behavior trong phiên bản đang chạy, thiết kế mapping domain `NOT_FOUND`.
7. Tạo `order_audit` có auto-generated ID, dùng `keysGenerated(true)` và nhận generated keys. Đọc tên key thực tế từ DB.
8. Thêm SELECT sau INSERT theo generated key; xác định `replySqlParameterSourceFactory` và tên parameter phù hợp DB.
9. Viết flow DML + SELECT cùng message; test cập nhật và reply từ `SELECT`, phân tích isolation/transaction.
10. Chuyển Java DSL 7.x sang bean `JdbcOutboundGateway` + `@ServiceActivator` ở 6.x. Đối chiếu import và config XML.
11. Thử transaction rollback sau `send()`; giải thích vì sao reply `UPDATED=1` không bảo đảm commit cuối cùng.
12. Thay `DirectChannel` bằng `ExecutorChannel`; quan sát thread, error propagation, reply timeout và transaction boundary.
13. Dùng một HTTP inbound gateway gọi JDBC outbound gateway; tránh blocking WebFlux event loop và chuyển reply/404 phù hợp.
14. Dùng Kafka/JMS gửi request và mô phỏng crash sau DB commit trước ACK; bổ sung idempotency/outbox để không nhân đôi.
15. Gửi nhiều request SELECT không có giới hạn, đo heap/latency; chuyển sang pagination và indexes phù hợp.

**Tình huống thiết kế:** một hệ thống nhận sự kiện `payment.captured`, cập nhật trạng thái đơn qua JDBC outbound gateway rồi phát Kafka event `order.paid`. Lần đầu SQL trả `UPDATED=1` nhưng ứng dụng crash trước khi ACK Kafka nguồn; lần sau message được redeliver, câu UPDATE trả `UPDATED=0` vì trạng thái đã là `PAID`. Bạn sẽ xác định “duplicate đã xử lý” khác “conflict” thế nào, đâu là transaction boundary của reply, và cách dùng outbox/idempotency để vẫn phát đủ event đầu ra mà không tạo tác dụng trùng?

## 20. Tài liệu tham khảo

- [Spring Integration Reference — JDBC Outbound Gateway](https://docs.spring.io/spring-integration/reference/jdbc/outbound-gateway.html): update count `UPDATED`, generated keys, SELECT, `maxRows` và empty list từ 6.0.
- [Spring Integration Reference — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): Java DSL `Jdbc` có từ 7.0 và `JdbcOutboundGatewaySpec`.
- [Spring Integration API — Jdbc Factory](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/Jdbc.html): overload `outboundGateway(dataSource, updateQuery, selectQuery)`.
- [Spring Integration API — JdbcOutboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcOutboundGatewaySpec.html): `maxRows`, `keysGenerated`, `rowMapper`, request/reply SQL parameter source factory.
- [Spring Integration API — JdbcOutboundGateway (7.x)](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/outbound/JdbcOutboundGateway.html): constructor và request/reply handler behavior.
- [Spring Integration API — JdbcOutboundGateway (6.x)](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/jdbc/JdbcOutboundGateway.html): handler import cũ, row mapper và max rows.
- [Spring Framework Reference — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): DataSource, JdbcTemplate, RowMapper, exception translation.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries, commit/rollback và proxy.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request-reply, replyChannel, timeout và correlation.

> **Ghi nhớ:** JDBC outbound gateway là **message-driven request–reply endpoint**. Nó chạy DML/SELECT và trả kết quả tương ứng: `{UPDATED=n}`, generated keys hoặc hàng dữ liệu từ SELECT. Muốn dùng đúng phải thiết kế rõ payload type/`maxRows`, parameter binding, reply channel, transaction và xử lý empty result. Đừng nhầm update count với commit receipt, và đừng nhầm JDBC outbound gateway với outbound adapter chỉ tạo side effect một chiều.
