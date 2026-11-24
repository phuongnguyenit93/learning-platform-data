# JMS inbound gateway request-reply

## 1. Khi nào cần JMS inbound gateway?

Một hệ thống ERP gửi lệnh hỏi trạng thái đơn hàng tới JMS queue `orders.status.request` và cần nhận phản hồi `PAID`, `PENDING` hoặc `NOT_FOUND` trên một JMS reply destination. Ứng dụng Spring Integration cần **nhận JMS request, thực thi nghiệp vụ và gửi JMS reply** cho đúng người gọi. **JMS inbound gateway** cung cấp điểm vào cho giao tiếp hai chiều này.

Trong module **SPRING_INTEGRATION_ADAPTERS**, inbound/outbound adapter kết nối dữ liệu một chiều, gateway xử lý request-reply, poller kích hoạt nguồn dữ liệu theo lịch, còn `MessageChannel` liên kết các bước xử lý độc lập với protocol bên ngoài. Bài này đào sâu **JMS inbound gateway request-reply**; các đặc điểm của hợp đồng message, lỗi, kết nối và transaction cũng là nền tảng khi tích hợp file, SFTP, HTTP, AMQP, Kafka hay cơ sở dữ liệu.

**Sau bài học, bạn cần có thể:**

1. Giải thích đường đi từ JMS request đến Spring Message và trở lại JMS reply.
2. Cấu hình một `Jms.inboundGateway` bằng Java DSL hoặc XML.
3. Hiểu vai trò của `JMSReplyTo`, `JMSCorrelationID` và `JMSMessageID` để phản hồi không bị nhầm giữa các yêu cầu đồng thời.
4. Phân biệt response nghiệp vụ với exception, timeout, rollback và redelivery.
5. Kiểm chứng luồng trên broker thật và nhận ra ranh giới giữa JMS transaction và database transaction.

### Gateway khác channel adapter ở đâu?

| Endpoint | Nhận/gửi | Có cần trả một JMS reply? | Cách kích hoạt |
|---|---|---|---|
| JMS polling inbound channel adapter | Nhận | Không | `Poller` gọi `JmsTemplate.receive()` theo lịch |
| JMS message-driven inbound channel adapter | Nhận | Không | JMS listener container nhận message |
| JMS outbound channel adapter | Gửi | Không | Spring Message đi vào handler gửi JMS |
| **JMS inbound gateway** | **Nhận request và gửi reply** | **Có** | Listener container nhận JMS request, chờ kết quả xử lý |
| JMS outbound gateway | Gửi request và nhận reply | Có | Spring Integration là bên gọi JMS từ phía trong ứng dụng |

Inbound gateway phù hợp khi **client JMS ở bên ngoài** khởi tạo yêu cầu và ứng dụng hiện tại đóng vai trò phục vụ. Nếu ứng dụng hiện tại chủ động gọi dịch vụ JMS khác, dùng **outbound gateway**.

## 2. Kiến trúc request-reply và hai lớp message

~~~mermaid
sequenceDiagram
    participant Client as ERP (JMS client)
    participant Broker as JMS Broker
    participant Gateway as JMS Inbound Gateway
    participant Flow as MessageChannel + Handler

    Client->>Broker: TextMessage request (JMSReplyTo, correlation)
    Broker->>Gateway: Phân phối từ orders.status.request
    Gateway->>Flow: Spring Message + replyChannel
    Flow-->>Gateway: Spring Message chứa kết quả
    Gateway->>Broker: JMS reply đến JMSReplyTo
    Broker-->>Client: Reply đúng request
~~~

Cần phân biệt:

- **JMS message** là đối tượng thuộc API `jakarta.jms.Message`, có JMS body, JMS headers và properties, đi qua broker.
- **Spring Message** thuộc `org.springframework.messaging.Message<?>`, có payload và `MessageHeaders`; nó đi trong integration flow qua `MessageChannel`.
- **Gateway** tiếp nhận JMS message, chuyển thành Spring Message, phát yêu cầu đến downstream và chờ Spring reply. Sau đó gateway chuyển Spring reply thành JMS message để gửi về destination tương ứng.

Ví dụ request từ ERP:

~~~json
{
  "requestId": "req-7001",
  "schemaVersion": 1,
  "operation": "getOrderStatus",
  "orderId": "ORD-700"
}
~~~

Ví dụ reply:

~~~json
{
  "requestId": "req-7001",
  "schemaVersion": 1,
  "resultCode": "OK",
  "orderId": "ORD-700",
  "status": "PAID"
}
~~~

`requestId` ở JSON là **ID nghiệp vụ** do hai hệ thống thống nhất, phục vụ tracing/idempotency. Nó không tự động là `JMSMessageID` hay `JMSCorrelationID`; các JMS header thuộc **protocol request-reply** và cần được kiểm tra độc lập.

### Đường đi chi tiết

1. Producer gửi `TextMessage` vào queue `orders.status.request` và thường đặt `JMSReplyTo` bằng một temporary queue hoặc reply queue do client quản lý.
2. JMS listener container của inbound gateway nhận message và gọi listener. Gateway áp dụng JMS converter/header mapper để tạo Spring Message.
3. Spring Message được đưa tới request channel; gateway cung cấp đường nhận reply (thường qua header `replyChannel` tạm thời).
4. Một service activator, transformer hoặc subflow xử lý request và **trả về** một giá trị/Message phù hợp.
5. Reply đến gateway qua reply channel; gateway chuyển payload sang JMS message, chọn reply destination và gửi.
6. Client nhận reply trên destination đã khai báo, rồi kiểm tra correlation để ghép với request ban đầu.

Inbound gateway dùng listener container, **không yêu cầu `PollerMetadata`**. Với `DirectChannel` và handler đồng bộ, đường xử lý thường chạy trên luồng listener, nên request lâu có thể giữ consumer trong thời gian đáng kể.

## 3. Cấu hình Java DSL từ request queue đến reply

Ví dụ dùng **Spring Integration 6+** và **Jakarta JMS**. Với Spring Integration/Spring Framework đời cũ có thể thấy package `javax.jms`. Để chạy ví dụ, dự án cần Spring Integration JMS cùng JMS client phù hợp broker (Artemis, IBM MQ hoặc provider khác).

~~~xml
<!-- Phiên bản dependency do Spring Boot BOM quản lý. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Thêm starter/client cho JMS provider và cấu hình broker tương ứng. -->
~~~

Điều kiện tiên quyết là có bean `ConnectionFactory` hoạt động và queue `orders.status.request` đã được tạo hoặc được phép tạo tự động theo chính sách broker. Không giả định thông số kết nối mặc định.

### 3.1. Tạo gateway và handler

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class OrderStatusJmsGatewayConfiguration {

    @Bean
    public IntegrationFlow orderStatusJmsGateway(
            ConnectionFactory connectionFactory,
            OrderStatusService orderStatusService) {

        return IntegrationFlow
                .from(Jms.inboundGateway(connectionFactory)
                        .requestDestination("orders.status.request"))
                .handle(String.class, (requestJson, headers) ->
                        orderStatusService.getStatusAsJson(requestJson))
                .get();
    }
}
~~~

Một service để người học tự implement:

~~~java
public interface OrderStatusService {
    // Trả JSON có requestId/resultCode/status; ném exception khi lỗi hạ tầng.
    String getStatusAsJson(String requestJson);
}
~~~

Ý nghĩa của từng bước:

- `Jms.inboundGateway(connectionFactory)` tạo message-driven JMS inbound gateway, sử dụng listener container nhận request.
- `.requestDestination("orders.status.request")` chọn queue nhận yêu cầu. Giá trị phải khớp destination của producer.
- `.handle(String.class, ...)` chỉ nhận Spring Message có payload `String` sau conversion. Khi client gửi JMS `TextMessage`, converter mặc định phổ biến tạo `String`.
- Handler **trả về chuỗi JSON** thay vì `null`: Spring Integration dùng giá trị trả về làm reply message để gateway phát JMS reply.
- `.get()` hoàn thành IntegrationFlow. Trong ví dụ này gateway sử dụng cơ chế reply channel nội bộ của flow; không cần tự viết một outbound JMS adapter để gửi response.

Nếu service ném lỗi, flow không tạo reply bình thường; cách chuyển lỗi thành response hoặc rollback phụ thuộc error channel/transaction được cấu hình. Nếu handler trả `null` hoặc không có consumer tạo reply, phía gọi có thể hết thời gian chờ và gateway cũng có thể báo timeout tùy cấu hình.

### 3.2. JMS client thử nghiệm bằng `JmsTemplate.sendAndReceive`

Đoạn minh họa sau dùng một client Spring JMS trong môi trường thử nghiệm. `JmsTemplate.sendAndReceive` tự tạo temporary queue cho reply và gắn vào header `JMSReplyTo` của request.

~~~java
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

public String requestOrderStatus(JmsTemplate jmsTemplate)
        throws jakarta.jms.JMSException {

    // Cấu hình trên instance JmsTemplate của client, không phải inbound gateway.
    jmsTemplate.setReceiveTimeout(5000);

    Message reply = jmsTemplate.sendAndReceive(
            "orders.status.request",
            session -> {
                TextMessage request = session.createTextMessage(
                        "{\"requestId\":\"req-7001\",\"schemaVersion\":1,"
                        + "\"operation\":\"getOrderStatus\",\"orderId\":\"ORD-700\"}");
                request.setStringProperty("clientName", "erp-service");
                return request;
            });

    if (reply == null) {
        throw new IllegalStateException("JMS request hết thời gian đợi reply");
    }
    if (!(reply instanceof TextMessage)) {
        throw new IllegalStateException("Reply không phải JMS TextMessage");
    }
    return ((TextMessage) reply).getText();
}
~~~

Đây là đoạn trích method dùng trong service/test đã có `JmsTemplate` được cấu hình theo provider; không phải toàn bộ ứng dụng. Client gửi và nhận có thể nằm ở tiến trình khác với server. Nếu broker không hỗ trợ temporary destination hoặc ACL không cho tạo, phải dùng reply queue phù hợp và cơ chế correlation của client.

**Phân biệt hai loại timeout:** `jmsTemplate.setReceiveTimeout(5000)` ở **client** giới hạn thời gian chờ một JMS reply (đơn vị mili giây). Nó **không** tự động cấu hình thời gian chờ của gateway trên server, cũng không bảo đảm handler hoàn thành trong 5 giây.

### 3.3. XML namespace tương đương

~~~xml
<int:channel id="orderStatusRequests"/>

<int-jms:inbound-gateway
        id="orderStatusJmsGateway"
        connection-factory="jmsConnectionFactory"
        request-destination-name="orders.status.request"
        request-channel="orderStatusRequests"/>

<int:service-activator
        input-channel="orderStatusRequests"
        ref="orderStatusService"
        method="getStatusAsJson"/>
~~~

Đây là **fragment** XML. Ứng dụng còn cần khai báo namespace `int`/`int-jms`, bean `jmsConnectionFactory` và `orderStatusService`. Method `getStatusAsJson(String)` cần trả giá trị hợp lệ. Trong cấu hình này, Spring Integration giữ thông tin reply channel khi gửi request đến handler; handler không cần biết tên JMS reply queue.

## 4. `JMSReplyTo` và cơ chế correlation

Một request-reply đúng đắn phải trả lời **đúng nơi** và ghép reply với **đúng request**, đặc biệt khi nhiều client hoặc nhiều request gửi đồng thời.

### 4.1. Chọn reply destination

Khi nhận request, JMS inbound gateway ưu tiên header `JMSReplyTo` để chọn nơi gửi reply. Nếu không có header này, có thể cấu hình destination dự phòng bằng `defaultReplyDestination`, `defaultReplyQueueName` hoặc `defaultReplyTopicName`.

Ví dụ Java DSL khi ERP cũ không đặt `JMSReplyTo`:

~~~java
// Chỉ thay phần cấu hình endpoint trong IntegrationFlow ở mục 3.
Jms.inboundGateway(connectionFactory)
        .requestDestination("orders.status.request")
        .defaultReplyQueueName("orders.status.reply")
~~~

Chỉ cấu hình queue mặc định khi **client thực sự biết và đang lắng nghe** queue đó. Nếu nhiều client dùng một shared reply queue, client phải lọc reply theo correlation; nếu không, một client có thể đọc nhầm reply dành cho client khác.

| Cách chọn reply destination | Ưu điểm | Đánh đổi |
|---|---|---|
| `JMSReplyTo` là temporary queue | Client được reply vào queue dành cho phiên gọi; đơn giản cho request-reply ngắn | Phụ thuộc quyền tạo temporary queue và vòng đời connection |
| `JMSReplyTo` là reply queue cố định | Dễ quan sát, có thể tích hợp với ứng dụng kế thừa | Cần selector/correlation và cơ chế tránh tiêu thụ nhầm |
| `defaultReplyQueueName` ở inbound gateway | Hỗ trợ client không gửi `JMSReplyTo` | Phải thống nhất contract reply queue và consumer từ trước |
| `replyToExpression` (từ Spring Integration 6.1) | Có thể suy destination dự phòng theo request JMS khi `JMSReplyTo` trống | Phải giới hạn destination được phép gửi, bảo vệ ACL và validate dữ liệu |

**Không tự lấy tên reply destination từ payload không đáng tin cậy** rồi cho phép gửi tùy ý. Nếu cần reply động, dùng danh sách queue hợp lệ và destination resolver với quyền rõ ràng.

### 4.2. Tại sao cần `JMSCorrelationID`?

Với nhiều request cùng lúc, một reply queue chung có thể chứa nhiều message:

~~~text
Request A: JMSMessageID=ID:A, JMSReplyTo=orders.status.reply
Request B: JMSMessageID=ID:B, JMSReplyTo=orders.status.reply

Reply cho A: JMSCorrelationID=ID:A
Reply cho B: JMSCorrelationID=ID:B
~~~

Một pattern phổ biến là server đặt `JMSCorrelationID` của **reply** bằng `JMSMessageID` của **request**. Một pattern khác dùng correlation ID đã có trên request: nếu client gửi `JMSCorrelationID` do mình quản lý, reply phản ánh giá trị đó theo cấu hình correlation mà hai bên đã thống nhất. Spring Integration inbound gateway hỗ trợ các pattern correlation mà outbound gateway Spring Integration hoặc client JMS tiêu chuẩn dùng.

Trong hệ thống dùng shared reply queue, client nên dùng JMS message selector hoặc cơ chế dispatch nội bộ để chỉ lấy reply khớp request của nó. Không gửi đồng loạt mọi reply vào một queue rồi nhận theo thứ tự đến và giả định `request 1 ↔ reply 1`.

**Ba ID cần phân biệt:**

- `JMSMessageID`: provider cấp cho **từng JMS message**, có thể khác khi producer gửi lại cùng lệnh.
- `JMSCorrelationID`: gắn reply với một request hoặc chuỗi trao đổi, theo contract.
- `requestId`: ID nghiệp vụ trong JSON, hữu ích cho logging, deduplication và truy vết xuyên nhiều hệ thống.

Đừng coi `requestId` tự động trùng `JMSCorrelationID` nếu không chủ động ánh xạ. Hãy kiểm thử tương thích với client thật.

## 5. Hợp đồng request và reply: chuyển đổi payload, header

JMS inbound gateway có **hai cấu hình payload extraction** khác nhau:

| Thuộc tính | Áp dụng cho | Mặc định | Kết quả thường thấy |
|---|---|---|---|
| `extractRequestPayload` | JMS request đến → Spring Message | `true` | `TextMessage` → payload `String` |
| `extractReplyPayload` | Spring reply → JMS reply đi | `true` | Spring payload `String` → JMS `TextMessage` |

Với `extractRequestPayload(false)`, JMS message nguyên bản có thể được giữ làm Spring payload; điều này khiến handler phụ thuộc JMS API và vòng đời session. Với `extractReplyPayload(false)`, toàn bộ Spring Message có thể được chuyển làm JMS body theo converter, thường không phù hợp với consumer bên ngoài chỉ hiểu JSON. Nên giữ mặc định và quy định schema rõ ràng trong phần lớn luồng nghiệp vụ.

| JMS message | Spring payload với `SimpleMessageConverter` | Cách dùng |
|---|---|---|
| `TextMessage` | `String` | JSON/XML có schema/version |
| `BytesMessage` | `byte[]` | Format binary có contract |
| `MapMessage` | Bản đồ các giá trị | Chú ý giới hạn type JMS và provider |
| `ObjectMessage` | Java `Serializable` | Hạn chế vì tương thích class và rủi ro deserialization |

`HeaderMapper` đảm nhiệm mapping một phần JMS headers/properties sang Spring headers và ngược lại. Không mọi header Spring đều hợp lệ là JMS property; ví dụ value object tùy ý hay tên property không phù hợp có thể không được giữ nguyên. JMS headers điều khiển giao thức, chẳng hạn `JMSReplyTo`, `JMSCorrelationID`, cần được kiểm tra trong integration test.

Một contract hữu ích cho dịch vụ tra cứu trạng thái:

- Request chứa `requestId`, `schemaVersion`, `operation` và `orderId`; server từ chối version hoặc operation không được hỗ trợ.
- Reply thành công chứa `requestId` tương ứng, `resultCode=OK`, `orderId`, `status`.
- Reply lỗi nghiệp vụ chứa `requestId`, `resultCode` là mã lỗi đã thống nhất, `message` không lộ thông tin nội bộ.
- Định nghĩa thời gian xử lý tối đa, chính sách retry và trạng thái khi không có reply.

**Đầu vào sai định dạng phải được xử lý như một trường hợp có chủ đích.** Nếu parse JSON lỗi trước khi tìm `requestId`, reply vẫn có thể trả `INVALID_REQUEST` với `requestId=null` khi contract cho phép; nếu không thể trả reply an toàn, để exception đi theo cơ chế lỗi/rollback phù hợp.

## 6. Timeout, kênh đồng bộ và đường xử lý bất đồng bộ

Cùng tên "timeout" nhưng nhiều vị trí khác nhau:

| Điểm chờ | Chờ điều gì? | Khi hết hạn |
|---|---|---|
| JMS client `JmsTemplate.receiveTimeout` | JMS reply trên reply destination | Có thể nhận `null` hoặc báo timeout ở tầng client |
| Gateway `replyTimeout` | Reply từ luồng Spring Integration, đặc biệt khi xử lý bất đồng bộ | Không tìm thấy reply trong thời gian quy định; xử lý lỗi tùy cấu hình |
| Gateway `requestTimeout` | Gửi Spring request vào channel có thể block, ví dụ bounded `QueueChannel` đã đầy | Không chuyển request vào channel kịp |
| Timeout truy cập DB/HTTP | Hoàn thành downstream service call | Service ném lỗi; gateway quyết định reply lỗi hoặc rollback |
| JMS time-to-live | JMS request/reply còn hiệu lực trên broker | Message hết hạn có thể bị loại hoặc xử lý theo broker policy |

Không dựa vào các **giá trị mặc định** khi hệ thống có SLA nghiêm ngặt; hãy đặt timeout rõ ràng cho client, gateway và các phụ thuộc downstream. Thời gian client chờ phải tính đến xếp hàng, xử lý, gửi reply và độ trễ broker. Ví dụ client chỉ chờ 2 giây nhưng DB timeout 10 giây có thể tạo **late reply** ngay cả khi server cuối cùng xử lý thành công.

### Giữ luồng xử lý đồng bộ cho request ngắn

`DirectChannel` cho phép handler trả kết quả trong cùng thread của listener. Gateway có thể nhận reply ngay sau khi handler hoàn thành. Mô hình phù hợp với tra cứu nhanh, dễ quan sát exception và transaction, nhưng mỗi request lâu chiếm một luồng/consumer.

### Khi dùng `ExecutorChannel` hoặc `QueueChannel`

Gateway có thể gửi Spring Message cho một consumer ở thread khác rồi **chờ reply qua reply channel**. Khi đó:

1. Reply có thể đến sau thời gian chờ của gateway.
2. Exception từ handler bất đồng bộ không nhất thiết đi ngược qua listener theo cách một call stack đồng bộ.
3. Transaction JMS ở listener không tự bao trùm DB transaction của thread khác.
4. Khi client timeout, công việc downstream có thể vẫn đang chạy; nếu client retry, có nguy cơ xử lý trùng.

Với tác vụ mất vài phút, cân nhắc mô hình **command + acknowledgement + status query/event** bất đồng bộ thay vì giữ một JMS request-reply mở quá lâu. Gateway request-reply không biến một tác vụ dài thành hoàn thành tức thời.

## 7. Transaction, acknowledge và redelivery

**JMS inbound gateway thường sử dụng listener container có session transacted** theo mặc định của Spring Integration (từ phiên bản 4.2), **trừ trường hợp cung cấp container ngoài** và phải tự quản lý cấu hình. Spring Integration khuyến nghị acknowledge dạng transacted với `DefaultMessageListenerContainer` để giảm nguy cơ mất message. Hành vi thực tế còn phụ thuộc JMS provider và cách cấu hình container.

Trong đường xử lý đồng bộ:

1. Listener nhận một JMS request trong transaction JMS.
2. Gateway chuyển tới handler; handler tạo Spring reply.
3. Gateway gửi reply tới `JMSReplyTo` hoặc destination dự phòng.
4. Khi callback thành công và transaction được commit, broker xem việc nhận request và gửi reply đã hoàn tất theo transaction JMS tương ứng.
5. Nếu exception chưa được xử lý truyền ra tới listener, JMS transaction có thể rollback; broker quyết định redelivery/DLQ theo cấu hình.

Trong một broker và transaction JMS cục bộ, việc nhận và gửi reply có thể thuộc cùng transaction. **Không suy ra rằng cập nhật DB cũng thuộc transaction JMS.** Nếu handler commit DB rồi việc phát reply thất bại hoặc listener rollback, cùng request có thể được redeliver trong khi thay đổi DB đã xảy ra.

### Hành vi khi client không nhận reply

Nếu server đã xử lý lệnh thành công nhưng client timeout do reply bị trễ hoặc lỗi mạng, client có thể gửi lại cùng lệnh. Đối với nghiệp vụ **chỉ đọc** (`getOrderStatus`), thực thi lại có thể chấp nhận được; đối với lệnh **ghi tiền / tạo đơn / đặt hàng**, phải thiết kế khóa idempotency ổn định, ví dụ `requestId` duy nhất và bảng lưu kết quả đã xử lý.

~~~mermaid
flowchart TD
    A["Nhận JMS request"] --> B["Parse + validate"]
    B --> C{"requestId đã xử lý?"}
    C -->|"Có"| D["Lấy kết quả đã lưu để trả reply"]
    C -->|"Chưa"| E["Thực thi nghiệp vụ trong DB transaction"]
    E --> F["Lưu requestId + kết quả trong cùng DB transaction"]
    F --> G["Tạo JMS reply"]
    D --> G
    G --> H{"Gateway gửi reply thành công?"}
    H -->|"Có"| I["JMS commit theo cấu hình"]
    H -->|"Lỗi chưa xử lý"| J["JMS rollback / broker redelivery"]
~~~

Với lệnh thay đổi dữ liệu, idempotency nên dùng unique constraint và lưu **kết quả nghiệp vụ ổn định** theo request ID để cùng request được thử lại không tạo tác động kép. Ràng buộc unique + cập nhật dữ liệu phải nằm trong cùng transaction DB. Cần quyết định chính sách giữ kết quả và xử lý race giữa nhiều consumer.

## 8. Error channel: trả lỗi nghiệp vụ hay rollback?

Nếu handler ném exception, JMS inbound gateway có thể gửi lỗi vào một **`errorChannel`** để chuyển thành một **reply hợp lệ** theo contract. Ví dụ client yêu cầu một đơn không tồn tại: trả `NOT_FOUND` dạng JSON có thể tốt hơn việc để client chờ JMS timeout.

Tuy nhiên phải phân loại lỗi:

| Tình huống | Xử lý thường phù hợp | Hệ quả |
|---|---|---|
| Request thiếu trường, sai version | Tạo reply `INVALID_REQUEST` hoặc `UNSUPPORTED_VERSION` | Client nhận lỗi rõ ràng; nếu error flow kết thúc bình thường, transaction có thể commit |
| Đơn không tìm thấy | Tạo reply `NOT_FOUND` như một kết quả nghiệp vụ | Thường không cần broker redelivery |
| Database tạm thời mất kết nối | Ném lại exception hoặc cơ chế retry có giới hạn | Transacted listener có thể rollback, broker redeliver |
| Hết timeout downstream | Xem có thể trả `TEMPORARY_UNAVAILABLE` hay cần rollback | Phải tránh client retry gây tác động trùng |
| JSON converter không đọc được | Error channel có thể nhận `ErrorMessage` từ bước conversion | Quyết định trả lỗi hay ném lại để rollback |
| Không gửi được JMS reply | Lỗi có thể dẫn đến rollback hoặc timeout ở client | Không được đánh đồng "đã xử lý" và "client đã nhận" |

### 8.1. Chuyển exception thành response có cấu trúc

Ví dụ định nghĩa riêng một error flow **khi chủ ý xác nhận request lỗi nghiệp vụ và trả một phản hồi lỗi**:

~~~java
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.context.annotation.Bean;

@Bean
public IntegrationFlow orderGatewayErrorFlow() {
    return IntegrationFlow.from("orderGatewayErrors")
            .<ErrorMessage, String>transform(error ->
                    "{\"resultCode\":\"INTERNAL_ERROR\","
                    + "\"message\":\"Request could not be processed\"}")
            .get();
}
~~~

Để dùng flow này, cấu hình thêm `.errorChannel("orderGatewayErrors")` trên `Jms.inboundGateway(...)` ở ví dụ mục 3. Phản hồi lỗi minh họa dùng message chung, không lộ stack trace hay credentials. Trong ứng dụng thực, nên phân loại exception và tạo JSON từ DTO theo schema; có thể lấy `requestId` từ request gốc nếu đã validate, tránh đọc trực tiếp dữ liệu không tin cậy vào thông báo lỗi.

**Hệ quả rất quan trọng:** nếu error flow **biến exception thành Spring reply thành công**, listener có thể commit JMS transaction vì lỗi đã được xử lý. Với lỗi hạ tầng cần rollback/redelivery, error flow phải **ném lại exception** (hoặc không cấu hình error channel theo chiến lược phù hợp). Từ Spring Integration 4.2, conversion error của JMS inbound gateway cũng có thể được đưa vào error channel.

### 8.2. Lỗi không đồng nghĩa với JMS reply

Không có cấu hình error channel thích hợp, exception từ handler không tự biến thành JMS response chứa lỗi; client có thể chỉ nhận **timeout**. Các cách triển khai như gửi một `ErrorMessage` sang `nullChannel` hoặc bắt lỗi rồi trả `null` có thể che giấu lỗi và làm khó việc rollback. Đừng tự động nuốt mọi exception.

Nếu cần retry tại adapter, Spring Integration 6.3+ có hỗ trợ `retryTemplate` và `recoveryCallback` cho thao tác nội bộ của gateway. Đây là chức năng phụ thuộc version; đặt số lần thử và backoff có giới hạn để tránh giữ consumer quá lâu, và xác định trường hợp nào đã có side effect trước khi thử lại.

## 9. Điều chỉnh listener container và vận hành

Inbound gateway sử dụng JMS `MessageListenerContainer` để quản lý consumer nhận request. Các thông số thường được quan tâm:

| Cấu hình | Vai trò | Cân nhắc |
|---|---|---|
| `concurrentConsumers` | Số consumer tối thiểu nhận request song song | Tăng khi handler nhanh, độc lập và tài nguyên đủ |
| `maxConcurrentConsumers` | Số consumer tối đa khi container hỗ trợ scale động | Thử tải để tránh bão hòa DB/HTTP downstream |
| `sessionTransacted` | JMS nhận/gửi reply trong transaction listener | Kiểm tra provider và exception propagation |
| `receiveTimeout` của listener container | Nhịp chờ khi nhận JMS message nội bộ | Khác client `JmsTemplate.receiveTimeout` |
| `recoveryInterval` / `BackOff` | Chiến lược khôi phục kết nối JMS | Ghi metric và cảnh báo khi listener không nhận được request |
| `destinationName` / `requestDestination` | Queue/topic nhận request | Sai destination khiến client timeout dù broker còn hoạt động |

Với request-reply, **concurrency không chỉ quyết định throughput mà còn quyết định bao nhiêu request có thể đang chờ handler/reply**. Nếu mỗi request mất 2 giây và chỉ có một consumer, hàng chờ sẽ tăng nhanh khi client gửi nhiều request. Tăng consumer cần đi kèm pool DB, bộ nhớ, connection broker và timeout budget. Request có thể hoàn thành **không đúng thứ tự gửi** khi chạy song song; client phải dựa trên correlation.

Khi dùng **queue**, nhiều listener container/instance có thể cạnh tranh nhận request. Với **topic**, mỗi subscription có thể nhận bản sao request và tạo nhiều reply nếu không thiết kế contract cẩn thận; request-reply qua queue thường dễ kiểm soát hơn. Nếu bắt buộc dùng topic, phải quyết định `pubSubDomain` và durable/shared subscription theo JMS provider.

### Vòng đời kết nối

- Khi ứng dụng khởi động, listener container mở connection/session/consumer và đăng ký callback; khi endpoint dừng, mặc định container cũng dừng và giải phóng kết nối/consumer theo phiên bản/config.
- Nếu broker tạm ngắt, listener container có thể recovery; cần theo dõi **số consumer hoạt động** và **tuổi request chờ**, không chỉ kiểm tra process Java còn sống.
- Khi triển khai lại đúng lúc request đang xử lý, client có thể timeout và retry; JMS session rollback/redelivery phụ thuộc transaction và broker policy.
- Không lưu biến trạng thái request chờ chỉ trong RAM nếu nghiệp vụ đòi hỏi tiếp tục sau restart; với lệnh ghi, dùng idempotency và kho kết quả có độ bền thích hợp.

**Metrics cần có:** request nhận được/giây, reply gửi thành công/giây, tỉ lệ business error, thời gian xử lý p50/p95/p99, tỉ lệ timeout phía client, redelivery, queue depth, age of oldest request, số consumer active và tình trạng broker reconnect. Log nên chứa `requestId`, JMS message ID và correlation ID khi có; không log nguyên payload chứa dữ liệu cá nhân.

## 10. Bài thực hành: tra cứu trạng thái đơn hàng từ ERP

Sử dụng broker thử nghiệm có queue `orders.status.request` và ứng dụng Spring Integration cung cấp `OrderStatusService`.

1. **Đường thành công:** khởi động gateway theo mục 3, gửi request `ORD-700` qua `JmsTemplate.sendAndReceive`; xác minh reply đúng `requestId`, `resultCode` và `status`.
2. **Không có JMSReplyTo:** gửi request bằng producer không đặt reply-to; xác minh hành vi khi chưa cấu hình default reply queue, sau đó thêm `defaultReplyQueueName` và một consumer đúng queue.
3. **Nhiều yêu cầu đồng thời:** chạy nhiều client với request khác nhau; kiểm tra `JMSCorrelationID`, không ghép kết quả theo thứ tự nhận.
4. **Lỗi nghiệp vụ:** gửi request thiếu `orderId`; cấu hình error flow trả `INVALID_REQUEST` và kiểm tra client nhận một reply lỗi có schema rõ ràng.
5. **Lỗi hạ tầng:** cho service ném exception khi DB không sẵn sàng; với listener transacted, kiểm tra rollback/redelivery và số lần thử lại/DLQ theo broker.
6. **Timeout:** thêm độ trễ server lớn hơn `JmsTemplate.receiveTimeout` của client; quan sát client nhận `null`/timeout và phân tích late reply.
7. **Đường async:** đưa request vào `ExecutorChannel`, quan sát ranh giới transaction và reply timeout; giải thích tại sao lỗi downstream không nhất thiết rollback cùng JMS request.
8. **Idempotency:** đổi service thành lệnh tạo đơn có `requestId` ổn định; gửi hai lần và kiểm tra database chỉ tạo một đơn.
9. **Khôi phục:** dừng broker hoặc gateway rồi khởi động lại; quan sát listener status, queue backlog, client retries và correlation.

### Những kiểm tra quan trọng

| Điều cần xác minh | Cách quan sát |
|---|---|
| Request được converter giải mã đúng | Handler nhận `String` thay vì JMS object khi dùng `TextMessage` |
| Reply dùng đúng JMS destination | Kiểm tra `JMSReplyTo` hoặc default reply queue |
| Reply khớp request | Kiểm tra `JMSCorrelationID`/JMS message ID theo contract |
| Lỗi có rollback hay commit | Quan sát redelivery và số message trong queue |
| Timeout không làm xử lý trùng | Gửi lại cùng `requestId` và kiểm tra unique constraint |
| Broker mất kết nối được phục hồi | Listener tiếp tục nhận request mới sau recovery |

Integration test nên dùng **JMS broker thực hoặc test container tương ứng provider**. Mock `MessageChannel` hoặc handler chỉ xác minh logic cục bộ, không chứng minh được reply destination, correlation, transaction, redelivery và recovery.

### Câu hỏi tự đánh giá

1. Vì sao JMS inbound gateway cần reply trong khi JMS message-driven channel adapter không cần?
2. `JMSReplyTo` và `JMSCorrelationID` giải quyết hai bài toán khác nhau như thế nào?
3. Nếu client dùng temporary queue và timeout trước khi server gửi reply, chuyện gì có thể xảy ra?
4. Khi nào nên cấu hình `defaultReplyQueueName`? Vì sao shared reply queue cần correlation?
5. Khác nhau giữa timeout ở `JmsTemplate` client, `replyTimeout` gateway và timeout DB là gì?
6. Tại sao lỗi được biến thành error reply có thể khiến JMS transaction commit?
7. Tại sao listener transacted vẫn cần idempotency khi handler ghi database?
8. Nếu client muốn gửi một sự kiện mà không cần phản hồi, chọn JMS endpoint nào?

## 11. Tài liệu tham khảo

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): inbound/outbound gateway, `JMSReplyTo`, chuyển đổi message, error channel, transaction và correlation.
- [Spring Integration API — JmsInboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsInboundGatewaySpec.html): `requestDestination`, `defaultReplyQueueName`, `extractRequestPayload`, `extractReplyPayload` và `replyToExpression`.
- [Spring Framework API — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `sendAndReceive` và cơ chế temporary reply destination.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): reply channel, request/reply timeout và tương tác giữa gateway với các Spring Message channels.

**Ghi nhớ:** JMS inbound gateway biến một JMS request thành Spring Message, đợi downstream tạo Spring reply và gửi JMS reply về destination của client. Kết quả đúng phụ thuộc đồng thời vào payload contract, `JMSReplyTo`, correlation, timeout, transaction, xử lý lỗi và idempotency; gửi được một reply không tự bảo đảm mọi side effect trên database đã được commit nguyên tử với JMS.
