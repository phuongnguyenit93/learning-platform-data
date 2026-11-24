# JMS outbound gateway request-reply

## 1. JMS outbound gateway dùng khi nào?

Một ứng dụng quản lý đơn hàng viết bằng Spring Integration cần hỏi một hệ thống kho kế thừa: *“Đơn ORD-501 còn đủ hàng để giao không?”*. Hệ thống kho chỉ hỗ trợ giao tiếp bằng JMS: nhận request trên queue `inventory.check.request` và gửi reply về destination được chỉ ra trong request. Ứng dụng Spring Integration phải **gửi một JMS request, đợi đúng JMS reply, chuyển reply thành Spring Message và đưa kết quả về phía gọi**.

**JMS outbound gateway** thực hiện đúng vai trò đó. Đây là điểm giao tiếp hai chiều mà **Spring Integration là bên khởi tạo request**. Nó khác `JMS outbound channel adapter`: adapter chỉ đẩy message ra broker, còn gateway cung cấp cơ chế liên kết request với reply trong một lời gọi logic.

Trong module **SPRING_INTEGRATION_ADAPTERS**, inbound/outbound adapter, gateway, poller và `MessageChannel` kết nối hệ thống ngoài vào các integration flow. Các ví dụ với file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu cùng đòi hỏi một hợp đồng payload/header rõ ràng, xử lý timeout/lỗi đúng ranh giới và quản lý vòng đời kết nối. Bài này tập trung vào **JMS outbound gateway request-reply**, áp dụng các nguyên tắc ấy cho kết nối với JMS broker.

**Mục tiêu sau bài học:**

1. Phân biệt outbound gateway với outbound adapter và inbound gateway.
2. Cấu hình flow gửi JMS request, nhận JMS reply bằng Spring Integration Java DSL và XML.
3. Giải thích `JMSReplyTo`, `JMSCorrelationID`, `JMSMessageID`, reply destination tạm thời/cố định và request ID nghiệp vụ.
4. Xử lý timeout, late reply, lỗi converter, lỗi broker, transaction và redelivery mà không tạo tác động nghiệp vụ trùng.
5. Kiểm thử flow với một consumer JMS thực và đọc được các metric vận hành cần thiết.

## 2. Cơ chế hoạt động từ Spring Message đến JMS reply

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Spring
    participant Flow as MessageChannel
    participant Gateway as JMS outbound gateway
    participant Broker as JMS broker
    participant Service as Inventory JMS server

    App->>Flow: Spring Message (kiểm tra ORD-501)
    Flow->>Gateway: Request message
    Gateway->>Broker: JMS request + JMSReplyTo + correlation
    Broker->>Service: Phân phối inventory.check.request
    Service->>Broker: JMS reply đến JMSReplyTo
    Broker-->>Gateway: JMS reply đúng request
    Gateway-->>Flow: Spring Message kết quả
    Flow-->>App: AVAILABLE / OUT_OF_STOCK
~~~

Một chu kỳ request-reply thường có các bước:

1. **Phía gọi Spring** đưa một Spring Message đến request channel của outbound gateway. Payload có thể là JSON `String`, `byte[]` hoặc đối tượng Java đã được chuyển đổi theo contract.
2. Gateway **chọn JMS request destination** và dùng `JmsTemplate`/JMS provider để gửi JMS message. Nó ghi thông tin reply destination vào `JMSReplyTo` và duy trì cơ chế correlation cho request đang chờ.
3. Broker giao request cho consumer ở hệ thống ngoài. Consumer xử lý và gửi một JMS message trả lời về destination mà gateway hoặc giao thức hai bên đã thống nhất.
4. Gateway **nhận reply tương ứng với request**, chuyển JMS reply thành Spring Message, rồi gửi đến reply channel của integration flow.
5. Phía gọi Spring lấy được payload reply hoặc gặp timeout/exception tùy cấu hình và tình huống.

Outbound gateway không phải poller định kỳ tìm request trong ứng dụng. Nó được **kích hoạt khi có Spring Message đi vào**. Việc chờ/nhận JMS reply do phần hạ tầng JMS của gateway thực hiện; chi tiết cách tiếp nhận có thể khác nhau theo chế độ reply destination và phiên bản Spring Integration.

### Hai tầng message cần phân biệt

| Thành phần | Kiểu dữ liệu | Chịu trách nhiệm |
|---|---|---|
| Request/reply trong integration flow | `org.springframework.messaging.Message<?>` | Payload và Spring Message headers, request/reply channel |
| Request/reply đi qua broker | `jakarta.jms.Message`, ví dụ `TextMessage` | JMS body, standard JMS headers và JMS properties |
| `JmsOutboundGateway` | Gateway Spring Integration | Chuyển hai loại message và ghép JMS reply với Spring request |
| JMS broker/provider | Infrastructure | Destination, phân phối message, session, timeout/expiry và tính bền tùy cấu hình |
| Hệ thống kho | Consumer/server | Đọc request, xử lý nghiệp vụ, gửi đúng reply |

Spring `replyChannel` không phải là JMS `JMSReplyTo`. `replyChannel` là nơi **Spring Message** được trả về trong ứng dụng; `JMSReplyTo` là **JMS destination** mà server gửi JMS reply tới.

## 3. Chọn đúng endpoint: adapter hay gateway?

| Yêu cầu | Endpoint nên chọn | Ai khởi tạo trao đổi? | Có reply về phía Spring? |
|---|---|---|---|
| Gửi event một chiều sang queue | **JMS outbound channel adapter** | Spring Integration | Không |
| Gửi JMS request, đợi JMS reply | **JMS outbound gateway** | Spring Integration | Có |
| Nhận JMS request từ bên ngoài và trả JMS reply | **JMS inbound gateway** | JMS client bên ngoài | Gateway trả reply qua JMS |
| Nhận JMS event khi broker phân phối | JMS message-driven inbound adapter | JMS producer bên ngoài | Không |
| Quét JMS queue theo lịch | JMS polling inbound adapter | Poller Spring Integration | Không |

Ví dụ `InventoryCheck` là thao tác tra cứu ngắn và có reply rõ ràng, nên dùng outbound gateway. Nếu cần gửi `OrderPaid` rồi hệ thống kho xử lý bất đồng bộ trong nhiều phút, mô hình outbound adapter + sự kiện kết quả riêng thường phù hợp hơn, bởi request-reply giữ tài nguyên chờ trong thời gian xử lý.

## 4. Xây dựng một JMS outbound gateway bằng Java DSL

Ví dụ dùng Spring Integration 6+ và Jakarta JMS. Các phiên bản Spring cũ có thể sử dụng `javax.jms` và tên API chi tiết khác nhau. Cần có `ConnectionFactory` hợp lệ cho broker, queue nhận request và JMS consumer có khả năng gửi reply.

### 4.1. Dependency

Trong dự án Maven dùng Spring Boot BOM quản lý phiên bản:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Thêm JMS starter/client cho ActiveMQ Artemis, IBM MQ hoặc JMS provider cụ thể. -->
~~~

Phải cấu hình bean `ConnectionFactory`, địa chỉ, credentials và các thiết lập bảo mật theo môi trường. Đoạn Java sau **không tạo broker** hoặc queue thay cho hệ thống JMS.

### 4.2. Định nghĩa request flow

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class InventoryJmsClientConfiguration {

    @Bean
    public IntegrationFlow inventoryJmsRequestFlow(
            ConnectionFactory connectionFactory) {

        return IntegrationFlow
                .from("inventoryJmsRequests")
                .handle(Jms.outboundGateway(connectionFactory)
                        .requestDestination("inventory.check.request"))
                .get();
    }
}
~~~

**Giải thích:**

- `IntegrationFlow.from("inventoryJmsRequests")` tạo hoặc sử dụng channel làm điểm nhận request từ các thành phần khác của Spring Integration.
- `Jms.outboundGateway(connectionFactory)` tạo endpoint request-reply phía JMS. Gateway phải giữ thông tin của request đang chờ để đưa reply về đúng Spring caller.
- `requestDestination("inventory.check.request")` chỉ ra destination bên ngoài nhận request. Trong ví dụ, đó là queue.
- `.handle(...)` tạo một endpoint có thể phát sinh reply cho flow; nó khác `Jms.outboundAdapter(...)` là endpoint gửi một chiều.
- Không có `poller` trong cấu hình này vì request phát sinh khi caller gọi gateway.

Nếu hệ thống kho không có JMS consumer hoặc không phát reply hợp lệ, flow không thể hoàn thành một giao dịch request-reply bình thường; client sẽ gặp timeout hoặc lỗi theo cấu hình.

### 4.3. Tạo một Spring messaging gateway cho service gọi

Để code nghiệp vụ gọi bằng interface thay vì trực tiếp tạo `Message<?>` và đọc reply channel, dùng `@MessagingGateway`:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface InventoryQueryClient {

    @Gateway(
            requestChannel = "inventoryJmsRequests",
            replyTimeout = 8000)
    String checkInventory(String requestJson);
}
~~~

Tại service sử dụng:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final InventoryQueryClient inventoryQueryClient;

    public CheckoutService(InventoryQueryClient inventoryQueryClient) {
        this.inventoryQueryClient = inventoryQueryClient;
    }

    public String checkOrderStock() {
        String requestJson = """
                {
                  "requestId": "req-501",
                  "schemaVersion": 1,
                  "operation": "checkStock",
                  "orderId": "ORD-501"
                }
                """;
        return inventoryQueryClient.checkInventory(requestJson);
    }
}
~~~

Trong Spring Java 17+, text block `"""` ở ví dụ trên là cú pháp Java hợp lệ. Interface messaging gateway được tạo proxy khi Spring Integration được bật. Phương thức `checkInventory` được khai báo trả `String` vì quy ước hệ thống kho trả JMS `TextMessage` và converter tạo Spring payload `String`.

**Lưu ý quan trọng:** `replyTimeout = 8000` trên annotation `@Gateway` là timeout khi **Spring messaging gateway chờ Spring reply** (8 giây). Nó không thay cho mọi timeout của JMS outbound gateway hoặc downstream. Trong mô hình đồng bộ, việc chờ ở JMS endpoint có thể đã chiếm phần lớn thời gian; cần thiết lập timeout ở JMS endpoint và client theo cùng một budget SLA.

### 4.4. Hợp đồng JSON mẫu

Request `TextMessage`:

~~~json
{
  "requestId": "req-501",
  "schemaVersion": 1,
  "operation": "checkStock",
  "orderId": "ORD-501"
}
~~~

Reply `TextMessage`:

~~~json
{
  "requestId": "req-501",
  "schemaVersion": 1,
  "resultCode": "OK",
  "orderId": "ORD-501",
  "availability": "AVAILABLE",
  "availableQuantity": 6
}
~~~

`requestId` trong payload là **khóa nghiệp vụ** do client chọn. Đó không tự động là JMS `JMSMessageID` hoặc `JMSCorrelationID`. Việc phản hồi đúng request phải dựa trên JMS correlation theo contract hai phía, còn `requestId` giúp truy vết và xử lý idempotency.

### 4.5. Cấu hình XML tương đương

~~~xml
<int:channel id="inventoryJmsRequests"/>
<int:channel id="inventoryJmsReplies"/>

<int-jms:outbound-gateway
        id="inventoryJmsGateway"
        request-channel="inventoryJmsRequests"
        reply-channel="inventoryJmsReplies"
        connection-factory="jmsConnectionFactory"
        request-destination-name="inventory.check.request"/>
~~~

Đây là đoạn cấu hình Spring XML: cần khai báo namespace `int`/`int-jms`, bean `jmsConnectionFactory` và consumer của `inventoryJmsReplies`. Trong Java DSL ở trên, interface `@MessagingGateway` tạo reply channel tạm cho mỗi lời gọi, nên không phải khai báo cố định `inventoryJmsReplies`.

Nếu muốn giới hạn thời gian chờ reply, đặt thuộc tính timeout được phiên bản Spring Integration hỗ trợ trên outbound gateway/JMS endpoint, rồi kiểm thử với server không trả reply. Không suy luận rằng `reply-channel` XML là tên queue JMS reply.

## 5. `JMSReplyTo` và các chiến lược reply destination

Khi gửi JMS request, client phải cho server biết **gửi reply về đâu**. JMS dùng header `JMSReplyTo` để chứa `Destination` này.

### Temporary reply destination

Trong thiết lập đơn giản, outbound gateway có thể sử dụng **temporary queue** của JMS để nhận reply. Temporary destination gắn với vòng đời JMS connection; server đọc `JMSReplyTo` từ request rồi gửi reply đến đó. Đây là cách thuận tiện khi request ngắn, một caller có thể giữ kết nối và provider cho phép tạo temporary destination.

Ưu điểm: không cần quản lý trước một reply queue cố định cho tất cả client. Đánh đổi: có chi phí tạo/quản lý destination tùy chế độ triển khai; nếu client kết thúc kết nối hoặc timeout rồi không còn listener, **late reply có thể không còn nơi nhận**.

### Reply destination cố định

Trong môi trường enterprise, ứng dụng có thể muốn một reply queue cố định để cấu hình ACL, metrics và vận hành. Khi đó nên quyết định **cách gateway phân biệt reply của nhiều request đang chờ**:

- Đặt `JMSCorrelationID` theo một quy ước mà client và server cùng hiểu.
- Nếu dùng shared reply queue, consumer nhận reply có thể cần selector hoặc reply listener có chức năng dispatch theo correlation, tùy phiên bản và cách cấu hình gateway.
- Lên kế hoạch xử lý reply muộn, stale reply, message không khớp request và độ sâu reply queue.

Ví dụ khái niệm khi khai báo một destination cố định:

~~~java
// Thay cấu hình JMS endpoint ở mục 4 nếu hai phía thống nhất reply queue.
Jms.outboundGateway(connectionFactory)
        .requestDestination("inventory.check.request")
        .replyDestination("inventory.check.reply")
~~~

Trước khi triển khai, cần kiểm tra method của `JmsOutboundGatewaySpec` trong phiên bản đang dùng, quyền receive trên reply destination, bộ lọc correlation và các tùy chọn reply listener. **Chỉ cấu hình một tên reply queue mà không định nghĩa matching cho nhiều request đồng thời là chưa đủ**.

| Cấu hình | Phù hợp khi | Điều cần kiểm tra |
|---|---|---|
| Temporary reply queue | Request-reply ngắn, client quản lý được JMS connection | Quyền tạo temporary destination và hành vi khi timeout/reconnect |
| Fixed reply queue riêng mỗi client | Hạ tầng yêu cầu queue định danh và ACL ổn định | Tên queue, cleanup, quyền gửi/nhận, matching theo request |
| Shared fixed reply queue | Nhiều concurrent request hoặc nhiều instance dùng chung | Correlation, selector/listener, thứ tự, tải, xử lý stale reply |

Nếu bên nhận bỏ qua `JMSReplyTo` và luôn gửi vào queue khác, phải sửa contract hoặc cấu hình gateway tương ứng; không thể kỳ vọng outbound gateway tự tìm reply ở một destination mà nó không theo dõi.

## 6. Correlation: ghép đúng request với reply

Hai request gửi gần nhau có thể hoàn thành đảo thứ tự. JMS hỗ trợ các header chuẩn:

| Header/ID | Ai tạo, dùng để làm gì? | Ví dụ |
|---|---|---|
| `JMSMessageID` | JMS provider cấp cho một lần gửi; có thể dùng làm tham chiếu cho reply | `ID:request-501` |
| `JMSCorrelationID` | Client/server thống nhất giá trị để nối reply với request | `ID:request-501` hoặc `corr-501` |
| `JMSReplyTo` | Destination server cần gửi JMS reply | Queue tạm hoặc `inventory.check.reply` |
| `requestId` trong payload | Khóa nghiệp vụ, thường dùng để audit, deduplication và truy vết | `req-501` |

### Pattern dùng JMSMessageID

~~~text
Client gửi request:
  JMSMessageID     = ID:A   (do broker/provider cấp)
  JMSReplyTo       = temp-reply-A

Server trả reply:
  JMSCorrelationID = ID:A
  Destination      = temp-reply-A
~~~

### Pattern dùng correlation ID do client cấp

~~~text
Client gửi request:
  JMSCorrelationID = corr-501
  JMSReplyTo       = shared.reply.queue

Server trả reply:
  JMSCorrelationID = corr-501
  Destination      = shared.reply.queue
~~~

Cả hai pattern đều có thể xuất hiện trong tích hợp JMS. **Cấu hình thực tế phải thống nhất với gateway và server**: không tự giả định server sẽ sao chép ID nào hoặc client sẽ dùng header nào để lọc. `JMSCorrelationID` mang giá trị nào, khi nào được thiết lập và việc gateway ánh xạ nó ra Spring headers phải được kiểm chứng bằng integration test với broker thật.

Khi nhiều client chung một reply destination, không ghép reply theo thứ tự nhận:

~~~mermaid
sequenceDiagram
    participant C as Spring JMS client
    participant B as Broker
    participant S as Inventory service
    C->>B: Request A (corr-A)
    C->>B: Request B (corr-B)
    B->>S: A và B
    S->>B: Reply B (corr-B) đến trước
    S->>B: Reply A (corr-A) đến sau
    B-->>C: Reply B: map vào B
    B-->>C: Reply A: map vào A
~~~

Một reply thiếu correlation hoặc sai correlation có thể bị bỏ qua, không được ghép với request nào hoặc gây timeout, tùy implementation. Không nên “chữa cháy” bằng cách bỏ qua correlation và nhận message đầu tiên từ queue.

### Header mapper và hợp đồng payload

`DefaultJmsHeaderMapper` chuyển các header/properties được hỗ trợ giữa Spring Message và JMS message. Không phải mọi Spring header có thể biến thành JMS property: JMS properties chỉ chấp nhận kiểu dữ liệu theo đặc tả, còn Spring header có thể chứa object bất kỳ. Ưu tiên kiểu `String`, số và boolean đơn giản cho các metadata mà server cần.

Trong ví dụ JSON, `schemaVersion` và `requestId` nên có trong payload để hợp đồng không phụ thuộc hoàn toàn vào JMS header. Không lấy `JMSMessageID` thay thế cho `requestId` trong nghiệp vụ cần deduplication: gửi lại cùng một lệnh có thể tạo JMS message ID mới.

## 7. Chuyển đổi body request và reply

Outbound gateway thực hiện **hai chiều chuyển đổi**: Spring request → JMS request, sau đó JMS reply → Spring reply.

| Payload Spring ban đầu | JMS body thường gặp nếu dùng converter mặc định | Phía nhận cần hiểu |
|---|---|---|
| `String` | `TextMessage` | JSON/XML/chuỗi theo schema |
| `byte[]` | `BytesMessage` | Binary format, charset/encoding |
| `Map` với giá trị JMS hỗ trợ | `MapMessage` | Key/value và quy tắc type |
| Java `Serializable` | `ObjectMessage` | Class compatibility và rủi ro deserialization |

Với `SimpleMessageConverter` thông dụng, `String` thường trở thành `TextMessage`. Trường hợp hệ thống kho chỉ hiểu JSON, hãy **serialize đối tượng domain trước khi gọi gateway** hoặc cấu hình `MessageConverter` phù hợp. Không mặc định mọi Java record/DTO đều tự chuyển thành JSON.

Một số thuộc tính cần phân biệt khi thiết kế:

- `extractRequestPayload` điều khiển cách gateway tạo nội dung JMS từ Spring request; thường giữ mặc định trích payload.
- `extractReplyPayload` điều khiển cách reply JMS được chuyển thành Spring payload; thường giữ dạng payload nghiệp vụ thay vì buộc service xử lý nguyên đối tượng JMS.
- `MessageConverter` quyết định mapping body thực tế; `HeaderMapper` quyết định mapping headers/properties. Hai cơ chế phục vụ mục đích khác nhau.

**Không mặc định reply có cùng kiểu với request.** Server có thể trả `TextMessage` chứa JSON, `BytesMessage` chứa Protobuf hoặc payload không hợp lệ. Nếu interface Spring khai báo kết quả `String` mà converter trả `byte[]`, phải bổ sung transformer hoặc thay contract rõ ràng.

### Validate contract trước khi gửi

Ví dụ dữ liệu request cần có:

- `requestId` là chuỗi không rỗng, duy nhất trong phạm vi nghiệp vụ; dùng lại đúng ID khi retry cùng lệnh.
- `schemaVersion` là số nguyên được hai phía hỗ trợ.
- `operation` thuộc tập lệnh cho phép như `checkStock`.
- `orderId` đúng định dạng và không dài quá giới hạn.

Reply cần phản ánh `requestId`, `resultCode` và các field kết quả. Một reply lỗi nghiệp vụ có thể là:

~~~json
{
  "requestId": "req-501",
  "schemaVersion": 1,
  "resultCode": "ORDER_NOT_FOUND",
  "message": "Order does not exist"
}
~~~

**Reply lỗi nghiệp vụ** là một JMS reply hợp lệ có `resultCode` khác `OK`. **Lỗi hạ tầng** như không kết nối được broker, không nhận reply hoặc không parse được message là một tình huống khác và phải xử lý theo exception/timeout.

## 8. Timeout: phân biệt từng điểm chờ

Trong request-reply có nhiều thời hạn độc lập. Không có một tham số `timeout` nào tự giải quyết mọi vấn đề.

| Vị trí | Đang chờ điều gì? | Rủi ro |
|---|---|---|
| Spring `@Gateway(replyTimeout=...)` | Spring reply qua message channel | Caller có thể chờ quá lâu hoặc quá ngắn so với phần JMS |
| Outbound JMS gateway | JMS reply trên destination đã cấu hình | Timeout/no reply; tài nguyên in-flight còn bị chiếm |
| JMS broker | TTL/expiry của request hoặc reply | Message hết hạn trước khi service nhận/đáp |
| Inventory service | DB/API bên trong warehouse xử lý xong | Service chậm, số request chờ tăng |
| Network/provider | Gửi/nhận hoặc recover kết nối | Có thể không biết broker đã nhận request hay chưa |

Ví dụ: Spring client đặt SLA 8 giây, warehouse có thể mất 12 giây, và server vẫn gửi reply. Client đã timeout ở giây thứ 8; reply đến sau gọi là **late reply**. Nó có thể bị bỏ qua, hết hạn hoặc tồn trên reply queue tùy cơ chế nhận. Caller có thể retry trước khi server hoàn thành lần đầu, tạo hai lần xử lý cùng lệnh.

### Thiết kế một timeout budget

Với SLA giả định 8 giây, có thể phân bổ mục tiêu vận hành:

~~~text
Tổng SLA của client:                      8.0 giây
  Phân phối JMS + chờ queue:             1.0 giây
  Xử lý warehouse/DB:                    5.0 giây
  Phát và nhận JMS reply:                1.0 giây
  Dự phòng network/scheduler:            1.0 giây
~~~

Đây là **mục tiêu thiết kế**, không phải bảo đảm đo được. Khi cài đặt, đặt JMS gateway receive/reply timeout, Spring gateway timeout, broker expiry và downstream timeout sao cho không xung đột; xác nhận bằng đo độ trễ p95/p99.

Với hệ thống có xử lý dài hàng phút, cần cân nhắc **asynchronous command + result event/status query** thay cho request-reply đồng bộ. Người gọi có thể nhận acknowledgement nhanh rồi tra cứu trạng thái sau; cách này giảm thời gian giữ request đang chờ reply.

## 9. Transaction, retry, idempotency và các cửa sổ lỗi

Request-reply chạy trên JMS không đồng nghĩa hai phía thực thi một **giao dịch phân tán**. Outbound gateway có thể gửi JMS request trong JMS transaction cục bộ; server có thể nhận/transact request riêng; warehouse DB có transaction riêng; reply cũng có thể được gửi trong transaction riêng.

### Tình huống gửi thành công nhưng không nhận reply

Giả sử server đã kiểm tra và *đặt giữ hàng* cho `ORD-501`, nhưng khi gửi reply thì kết nối hỏng. Client timeout rồi gửi lại:

~~~mermaid
flowchart TD
    A["Spring gửi request req-501"] --> B["Warehouse nhận request"]
    B --> C["DB commit thao tác giữ hàng"]
    C --> D{"JMS reply tới client?"}
    D -->|"Có"| E["Client xử lý kết quả"]
    D -->|"Không, client timeout"| F["Client có thể retry req-501"]
    F --> G{"Server đã xử lý req-501?"}
    G -->|"Có"| H["Trả lại kết quả đã lưu"]
    G -->|"Chưa"| I["Thực thi nghiệp vụ một lần"]
    I --> J["Lưu kết quả theo req-501"]
    J --> H
~~~

Nếu client dùng `requestId` mới cho mỗi lần retry cùng lệnh, server khó phát hiện đó là một thao tác lặp. Với các lệnh **thay đổi trạng thái**, nên:

1. Cấp một `requestId` ổn định cho hành động logic.
2. Phía server dùng unique constraint/idempotency store theo `requestId`.
3. Trong cùng DB transaction, lưu trạng thái nghiệp vụ và kết quả request đã xử lý.
4. Khi nhận lại `requestId` cũ, trả kết quả đã lưu thay vì thực thi tác động lần nữa.
5. Giữ idempotency record đủ lâu theo cửa sổ retry/redelivery và yêu cầu nghiệp vụ.

Với tra cứu chỉ đọc, retry thường an toàn hơn nhưng vẫn cần giới hạn tần suất, timeout và backoff để tránh làm quá tải server đang chậm.

### Những cửa sổ lỗi khác

| Tình huống | Điều thực sự biết được | Cách xử lý |
|---|---|---|
| Lỗi serialize trước send | JMS request chưa gửi thành công | Sửa payload/schema; không retry vô hạn cùng dữ liệu lỗi |
| Broker từ chối kết nối trước send | Có thể chưa đến broker | Retry có backoff, circuit breaker, metrics |
| Mất kết nối ngay sau send | **Có thể** broker đã nhận | Retry phải có idempotency vì kết quả gửi không chắc chắn |
| Server commit DB nhưng reply mất | Thao tác có thể đã thành công | Truy vấn lại theo `requestId` hoặc retry an toàn |
| Client nhận reply rồi crash trước khi ghi trạng thái | Client có thể lặp lại lời gọi | Lưu trạng thái bền vững và chống trùng ở server |
| Reply sai correlation | Không thể ghép đúng request | Log/truy vết và sửa contract; không chấp nhận reply bất kỳ |

**JMS transaction cục bộ không tự đồng bộ commit với DB.** Nếu cần tính nhất quán giữa lưu dữ liệu và phát sự kiện, có thể dùng outbox/inbox; nếu cần nguyên tử giữa nhiều tài nguyên, chỉ cân nhắc XA/distributed transaction khi provider, broker và hạ tầng thực sự hỗ trợ. Không tuyên bố `exactly-once` dựa trên một cờ transaction.

### Khi request xuất phát từ một inbound JMS flow

Ví dụ kiến trúc:

~~~text
JMS inbound gateway nhận yêu cầu từ ERP
    -> xử lý / chuyển đổi
    -> JMS outbound gateway hỏi inventory
    -> tạo reply cho ERP
~~~

Với các handler nối bằng `DirectChannel`, lời gọi request-reply có thể kéo dài trên một luồng listener. Nếu outbound gateway đợi inventory 8 giây, inbound listener cũng có thể giữ tài nguyên trong thời gian đó. Sử dụng `ExecutorChannel` hoặc `QueueChannel` làm đổi ranh giới thread và transaction; lỗi ở phía outbound có thể không còn rollback được JMS nhận ở phía trước. Phải thiết kế timeout toàn chuỗi và dự phòng khi một hệ thống ngừng phản hồi.

## 10. Xử lý lỗi và trả kết quả có ý nghĩa

Ở outbound gateway, không phải mọi sự cố đều xuất hiện thành JMS error reply:

- **Business error có reply:** server trả JSON với `resultCode` như `NOT_FOUND` hoặc `OUT_OF_STOCK`. Gateway có thể nhận bình thường; ứng dụng cần đọc `resultCode` để quyết định.
- **Không có reply:** server không gửi, reply bị lạc, correlation sai, reply queue không dùng được hoặc reply đến muộn. Gateway/caller phải xử lý timeout.
- **Lỗi gửi/nhận:** broker mất kết nối, thiếu quyền, destination sai, converter hoặc header mapper lỗi. Endpoint có thể ném `MessagingException`/exception do provider được bọc lại.
- **Lỗi xử lý sau gateway:** transformer hoặc service downstream nhận reply bị lỗi; cơ chế error handling ở Spring Integration quyết định nơi báo lỗi.

Với flow đồng bộ, exception thường có thể truyền ngược về Spring messaging gateway gọi `InventoryQueryClient.checkInventory(...)`. Nhưng cách exception cụ thể được bọc và giá trị khi timeout phụ thuộc endpoint, timeout và phiên bản. Không bắt tất cả exception để trả `"AVAILABLE"` hoặc `null` như thể request thành công.

`errorChannel`/`ErrorMessage` hữu ích để thu thập lỗi của các endpoint chạy bất đồng bộ. Tuy nhiên error channel **không tự động** retry request, khôi phục correlation hay gửi JMS reply. Khi triển khai retry advice, phải xác định rõ lỗi nào an toàn để retry, số lần, backoff và khả năng server đã hoàn thành side effect.

### Mẫu phân loại kết quả ở tầng ứng dụng

~~~text
InventoryQueryClient.checkInventory(requestJson)
  -> JMS reply "OK"           : cập nhật/đọc kết quả bình thường
  -> JMS reply "OUT_OF_STOCK" : kết quả nghiệp vụ, không retry mù quáng
  -> JMS reply "INVALID_REQUEST" : lỗi contract, cần sửa payload
  -> timeout                  : trạng thái chưa xác định; retry có idempotency
  -> broker unavailable       : retry có backoff hoặc trả 503 tương ứng cho caller
  -> converter error          : đưa vào theo dõi lỗi dữ liệu/cấu hình
~~~

Không log nguyên payload chứa token hoặc dữ liệu cá nhân; log `requestId`, correlation ID, JMS message ID, destination, thời gian xử lý, loại lỗi và kết quả.

## 11. Vòng đời kết nối, concurrency và vận hành

JMS outbound gateway dùng `ConnectionFactory`, JMS session/producer và cơ chế nhận reply do Spring Integration/JMS provider quản lý. Khi dùng reply destination cố định cùng nhiều request đồng thời, việc xử lý correlation và reply listener cần được cấu hình đúng theo phiên bản Spring Integration và khả năng của broker.

Những điểm cần theo dõi:

| Chỉ số/trạng thái | Vì sao quan trọng? |
|---|---|
| Số request được gửi/giây | Phát hiện đột biến lưu lượng |
| Số reply hợp lệ/giây | Kiểm tra server có phản hồi hay không |
| Số request đang chờ reply | Phát hiện cạn tài nguyên khi server chậm |
| Reply latency p50/p95/p99 | Đối chiếu SLA và phát hiện bottleneck |
| Timeout rate | Thể hiện reply bị trễ, mất hoặc sai correlation |
| Late/unmatched reply | Phát hiện contract, timeout budget hoặc retry sai |
| JMS connection/reconnect errors | Phát hiện broker hoặc mạng không ổn định |
| Request queue depth và oldest age | Biết server đang bị backlog |
| Reply queue depth và expiry | Phát hiện reply tồn đọng, stale hoặc không được tiêu thụ |

Trên nhiều instance, cần tính tổng lượng request đang chờ, pool connection và quyền truy cập reply destination. Mỗi instance dùng temporary reply destination có thể cô lập tự nhiên hơn, nhưng tạo/quản lý nhiều temporary destination làm tăng tài nguyên broker. Shared reply queue giảm nhu cầu tạo queue nhưng đòi hỏi routing chính xác, đặc biệt khi nhiều gateway/instance cùng lắng nghe.

Khi dừng/restart ứng dụng, temporary queue và request đang chờ có thể không còn tiếp tục được. Client cần biết cách xử lý lời gọi thất bại, lưu `requestId` nếu là lệnh quan trọng và tra cứu/ retry an toàn sau khi khôi phục. Đừng xem việc JVM còn sống là bằng chứng JMS connection và reply consumer đang khỏe.

## 12. Thực hành: hỏi kho qua JMS rồi nhận reply

**Môi trường:** một JMS broker thử nghiệm, queue `inventory.check.request`, Spring Integration client dùng outbound gateway và một JMS server dùng inbound gateway hoặc listener tự triển khai. Chỉ triển khai **một** consumer xử lý request cho mỗi bài thử cơ bản để kết quả dễ đối chiếu.

1. **Happy path:** server nhận request JSON `req-501` và trả `AVAILABLE`; Spring `InventoryQueryClient` nhận reply `String` có đúng `requestId` và `resultCode=OK`.
2. **Correlation:** gửi 20 request với `requestId` khác nhau, cố ý thay đổi độ trễ xử lý để reply đảo thứ tự. Ghi nhận JMSCorrelationID và chứng minh reply không bị gán sai.
3. **No reply:** cho server nhận request nhưng không trả reply. Kiểm tra timeout ở JMS gateway và Spring caller; đo thời gian thực tế.
4. **Late reply:** server trả sau khi caller timeout. Theo dõi reply không có người nhận hoặc bị loại, rồi retry request cùng `requestId` và quan sát idempotency.
5. **Broker unavailable:** ngắt kết nối broker trước và sau thao tác gửi. Kiểm tra exception, log, reconnect và việc retry có thể tạo bản sao.
6. **Schema invalid:** gửi JSON thiếu `orderId` và thống nhất server trả `INVALID_REQUEST`; bảo đảm caller phân biệt business error với timeout.
7. **Fixed reply queue:** cấu hình reply destination cố định, thiết lập matching theo correlation, chạy nhiều caller đồng thời rồi kiểm tra không có reply bị nhận nhầm.
8. **Temporary reply queue:** xác nhận provider cho tạo temporary queue, xem lifecycle của reply destination khi client dừng/khởi động lại.
9. **Tác động ghi dữ liệu:** đổi từ `checkStock` sang `reserveStock`, tạo bảng idempotency theo `requestId`; cho reply mất sau DB commit rồi retry và xác nhận không giữ hàng hai lần.
10. **Tải và quan sát:** tăng số request đồng thời, thu thập p95 latency, timeout rate, request queue depth và in-flight count; quyết định có nên dùng mô hình bất đồng bộ cho tác vụ dài hay không.

### Checklist xác minh hợp đồng

| Kỳ vọng | Cách chứng minh |
|---|---|
| Client phát đúng JMS request destination | Xem metadata request tại broker/server |
| Server biết nơi trả reply | Kiểm tra `JMSReplyTo` của request |
| Reply ghép đúng lời gọi | Kiểm tra `JMSCorrelationID`/cách correlation theo contract |
| Body sau chuyển đổi đúng kiểu | Client nhận JSON `String`, validate schema/version |
| Timeout được xử lý có chủ đích | Server không trả reply và client thoát trong ngân sách thời gian |
| Không double effect khi retry | Unique `requestId` ở DB server và kiểm tra số bản ghi |
| Restart không gây hiểu nhầm kết quả | Retry/truy vấn lại theo request ID bền vững |

Các bài thử liên quan correlation, JMS transaction, reply destination, late reply và recovery cần **broker/JMS provider thực** hoặc container test tương đương. Mock `JmsTemplate` hoặc mock `MessageChannel` không chứng minh được những hành vi đó.

### Câu hỏi tự đánh giá

1. Vì sao một outbound channel adapter không thay thế được outbound gateway khi caller cần nhận trạng thái kho?
2. Phân biệt Spring `replyChannel` với `JMSReplyTo` trong luồng request-reply.
3. `JMSMessageID`, `JMSCorrelationID` và `requestId` khác nhau ở điểm nào?
4. Khi server trả reply B trước reply A, client làm gì để trả kết quả đúng cho từng lời gọi?
5. Vì sao `@Gateway(replyTimeout=8000)` không nên được xem là cấu hình thời hạn duy nhất trong toàn luồng JMS?
6. Điều gì xảy ra nếu client timeout sau khi server đã commit việc giữ hàng nhưng reply bị mất?
7. Vì sao dùng shared fixed reply queue cần thiết kế correlation chặt chẽ hơn?
8. Khi nào nên chuyển từ JMS request-reply sang command + result event bất đồng bộ?

## 13. Tài liệu tham khảo

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): outbound gateway, request/reply, correlation, reply destination và các thiết lập JMS.
- [Spring Integration API — JmsOutboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundGatewaySpec.html): cấu hình Java DSL của outbound gateway.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): `@MessagingGateway`, Spring request/reply channels và timeout.
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): `JmsTemplate`, `MessageConverter` và giao dịch JMS.

**Ghi nhớ:** JMS outbound gateway cho phép một Spring Integration flow gửi request sang broker và nhận reply quay về đúng Spring caller. Chất lượng của request-reply không chỉ nằm ở việc gửi JMS thành công, mà còn ở **reply destination, correlation, hợp đồng payload, timeout đồng bộ, transaction boundaries, xử lý lỗi và idempotency khi retry**.
