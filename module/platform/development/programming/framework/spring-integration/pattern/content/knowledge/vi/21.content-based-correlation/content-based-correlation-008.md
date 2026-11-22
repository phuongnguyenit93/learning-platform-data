# Correlation qua gateway và adapter

## 1. Bối cảnh: cùng một công việc đi qua nhiều ranh giới giao tiếp

Trong chương **Content-based correlation** của module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai các Enterprise Integration Patterns với **Spring Integration** để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation có thể phối hợp trong cùng một workflow; nhưng nếu thông điệp đi qua HTTP, JMS, AMQP hoặc TCP mà mất định danh liên kết, các nhánh sẽ không còn ghép được kết quả chính xác.

Hãy xét một hệ thống tạo báo giá giao hàng. Một yêu cầu của khách hàng có thể đi qua:

1. **HTTP inbound gateway** hoặc REST controller để nhận request.
2. **Messaging gateway** để gọi flow như một phương thức Java.
3. **Outbound adapter/gateway** để gửi yêu cầu tới hãng vận chuyển.
4. Broker/HTTP service bên ngoài để trả các kết quả.
5. **Inbound adapter** để nhận reply hoặc event callback.
6. **Aggregator** để tập hợp ba kết quả của cùng một yêu cầu.

Một flow có thể có cả **request/reply nhanh** và **sự kiện bất đồng bộ**:

~~~mermaid
flowchart LR
    C["Client HTTP"] --> H["HTTP ingress"]
    H --> J["Java Messaging Gateway"]
    J --> G["IntegrationFlow"]
    G --> O["Outbound HTTP/JMS/AMQP"]
    O --> P["External provider"]
    P -->|"Response đồng bộ"| O
    P -->|"Callback/event sau"| I["Inbound adapter"]
    I --> V["Verify + map correlation"]
    V --> A["Aggregator / workflow store"]
    A --> R["Business result / event"]
~~~

**Câu hỏi quan trọng:** khi một reply quay về, hệ thống biết nó trả lời **lời gọi Gateway nào**, thuộc **đơn hàng của tenant nào**, và có phải **bản gửi lại của một sự kiện đã xử lý** hay không?

Ba câu hỏi này dùng những identity khác nhau. Không nên giải quyết tất cả bằng cách đặt cùng một UUID lên mọi header có chữ “correlation”.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt **business correlation**, **Gateway reply correlation** và **transport/protocol correlation**.
- Biết khi nào Gateway tự tạo replyChannel và khi nào adapter cần một khóa được serialize qua network.
- Tạo một correlation key đáng tin tại ingress, giữ nó qua các adapter có header mapping khác nhau.
- Dùng **wire envelope** cho hệ thống không hỗ trợ chuyển Spring Message headers.
- Thiết kế flow request/reply và event-driven callback để không đánh đồng HTTP response với việc workflow đã hoàn tất.
- Chọn timeout, retry, idempotency, dead-letter/recovery khi reply đến muộn hoặc thất lạc.
- Viết ví dụ Java DSL và kiểm thử correlation với nhiều request song song, khác tenant và duplicate.

## 2. Bốn loại định danh thường bị gọi chung là correlation ID

| Identity | Mục đích | Ví dụ | Có nên đổi qua một gateway/adapter? |
| --- | --- | --- | --- |
| **Business correlation key** | Gom các sự kiện thuộc một workflow | order-ready:v1:tenant-a:ORD-90:7 | Không, với cùng workflow |
| **Request/reply correlation** | Ghép một request với reply của lời gọi hiện tại | Gateway internal request token/replyChannel | Có thể là riêng cho từng attempt |
| **Transport correlation** | Ghép request và response trong một giao thức | JMSCorrelationID, AMQP correlationId, TCP connectionId | Do adapter/gateway giao thức quản lý |
| **Event idempotency identity** | Nhận ra một logical event bị redeliver | tenant-a:provider-x:event-405 | Không đổi khi retry cùng event |

Một số metadata khác cần phân biệt:

- **Spring MessageHeaders.ID**: ID của một Message; không phải business group key.
- **traceId/spanId**: để quan sát request xuyên service; không mặc định là khóa nghiệp vụ.
- **orderId/requestId**: có thể là thành phần business key, nhưng chưa đủ khi có nhiều tenant hoặc nhiều workflow epoch.
- **replyChannel/errorChannel**: thường là đối tượng hoặc tên destination nội bộ; không được giả định có thể chuyển nguyên vẹn qua HTTP/JMS/TCP.
- **ip_connectionId**: dùng trong Spring Integration TCP để xác định connection khi gửi phản hồi bằng collaborating adapters trên server; không phải order ID.

### 2.1. Ví dụ hai HTTP requests cùng đơn hàng

~~~text
Business workflow:
  tenant-a / ORD-90 / epoch-7
  businessCorrelationKey = order-ready:v1:tenant-a:ORD-90:7

HTTP request A, attempt 1:
  gateway reply destination = temporary channel A
  transport request identity = req-A

HTTP request A, attempt 2 (sau timeout):
  gateway reply destination = temporary channel B
  transport request identity = req-B

Business correlation key vẫn là:
  order-ready:v1:tenant-a:ORD-90:7
~~~

Nếu dùng replyChannel A làm khóa của workflow, lần retry sẽ “đánh mất” trạng thái nghiệp vụ cũ. Nếu dùng businessCorrelationKey để thay luôn replyChannel, hai request/reply đồng thời có thể trả kết quả nhầm caller. **Mỗi lớp dùng đúng định danh mà nó quản lý.**

### 2.2. Kết nối các loại ID bằng một bảng ánh xạ

~~~mermaid
flowchart TB
    B["Business key: tenant/order/epoch"]
    B --> E1["Event A / eventId=A"]
    B --> E2["Event B / eventId=B"]
    B --> E3["Event C / eventId=C"]
    B --> R1["Gateway call attempt 1"]
    B --> R2["Gateway call attempt 2"]
    R1 --> T1["JMS/AMQP/HTTP request correlation 1"]
    R2 --> T2["JMS/AMQP/HTTP request correlation 2"]
~~~

Một request/reply attempt chỉ là **một lượt giao tiếp** trong workflow dài hơn. Khi điều tra, log có thể lưu mapping giữa business key, eventId, attemptId và transport correlation; không ép chúng thành một giá trị.

## 3. Gateway khác adapter ở hợp đồng phản hồi

Trong Spring Integration:

- **Gateway** đóng vai trò request/reply: nhận request và kỳ vọng một reply để trả cho caller hoặc phía giao thức.
- **Channel adapter** thường là one-way: nhận message từ bên ngoài vào flow hoặc gửi message từ flow ra ngoài, không cung cấp một request/reply pair mặc định.
- **Aggregator** ghép các messages có liên quan; nó không tự trở thành HTTP response hoặc JMS reply trừ khi wiring/contract yêu cầu.

| Endpoint | Hướng | Có tự chờ reply? | Correlation cần chú ý |
| --- | --- | --- | --- |
| Messaging Gateway (interface Java) | Java call → Message → reply | Có với method trả giá trị | Temporary replyChannel/request |
| HTTP inbound gateway | HTTP request → flow → HTTP response | Có | HTTP call lifecycle và metadata verified |
| HTTP inbound channel adapter | HTTP request → flow | Không theo nghiệp vụ request/reply | Business ID do ingress tạo |
| HTTP outbound gateway | Flow → remote HTTP → response | Có | HTTP request-response, business key |
| HTTP outbound channel adapter | Flow → remote HTTP | Không trả reply vào flow | Event ID, delivery state |
| JMS/AMQP outbound gateway | Flow → broker → reply | Có | Protocol correlation + reply destination |
| JMS/AMQP channel adapter | Message one-way vào/ra broker | Không tự ghép request/reply | Wire envelope + business ID |
| TCP outbound gateway | TCP request → reply | Có | Connection/request correlation |
| TCP collaborating adapters | TCP send/receive tách rời | Không tự ghép client requests | Application correlation và connection routing |

Đây là bảng ngữ nghĩa, **không** có nghĩa mọi implementation có cùng timeout mặc định. Cần đọc cấu hình cụ thể và adapter version.

### 3.1. Ranh giới đồng bộ và bất đồng bộ

Một Java method Gateway có thể trả một DTO đồng bộ, nhưng bên dưới dùng ExecutorChannel/remote service; lời gọi có thể bị chặn tới khi reply đến hoặc timeout.

Một inbound channel adapter nhận message từ broker có thể xử lý asynchronous, và kết quả của nó được gửi tới một topic khác sau vài phút. Trong trường hợp đó không tồn tại một Java caller đang giữ **temporary replyChannel** của attempt cũ.

**Quy tắc:** chỉ dựa vào replyChannel khi lifetime và topology của nó phù hợp; với workflow kéo dài, phải có business correlation key và workflow state bền.

## 4. Messaging Gateway tạo replyChannel như thế nào?

Một **@MessagingGateway** biến lời gọi Java thành Spring Message. Theo tài liệu Spring Integration, Gateway thường tạo một **temporary, anonymous, point-to-point reply channel** rồi gắn vào header **replyChannel** để chuyển reply về đúng invocation.

~~~mermaid
sequenceDiagram
    participant C as Java caller
    participant G as Messaging Gateway
    participant F as IntegrationFlow
    participant S as Service Activator
    C->>G: quote(request)
    G->>F: Message + temporary replyChannel
    F->>S: handle(request)
    S-->>F: QuoteReply
    F-->>G: Message gửi về replyChannel
    G-->>C: QuoteReply
~~~

Một số đặc tính:

1. Caller không phải tự tạo MessageChannel để nhận reply.
2. Handler cuối cần tạo reply **không null** nếu Gateway method cần một kết quả.
3. Nếu một Filter discard hoặc handler trả null, Gateway có thể hết thời gian chờ.
4. Khi Gateway được cấu hình một reply channel tường minh, framework có thể tạo bridge tới temporary reply channel của invocation; không nên giả định nó ngừng phân biệt các caller.
5. Timeout/exception do Gateway nhìn thấy phải được phân biệt với lỗi nghiệp vụ của external provider.

### 4.1. Temporary replyChannel không phải wire-format field

Một Spring Message có thể mang header replyChannel là **đối tượng MessageChannel**. Không thể JSON-serialize đối tượng đó rồi hy vọng một service khác chạy JVM khác hiểu và gửi reply trở lại cùng object.

Ví dụ phản ví dụ:

~~~text
MessageHeaders:
  replyChannel = org.springframework.messaging.MessageChannel instance

Serialize toàn bộ MessageHeaders sang JSON và chuyển qua broker:
  replyChannel = ???  (không portable)
~~~

Khi vượt network, adapter dùng **reply destination của giao thức** (JMSReplyTo/AMQP replyTo) hoặc một **callback address / response topic** đã cấu hình, kết hợp với request token tương ứng. Business correlation key nên được truyền qua **wire envelope** hoặc một header đã được ánh xạ và xác minh.

### 4.2. Đừng dùng correlationId nghiệp vụ làm tên channel

Một payload có thể chứa orderId hay businessCorrelationKey, nhưng không được phép để client quyết định tên **replyChannel** hoặc **errorChannel** của Spring context. Đó là metadata điều khiển flow; cho phép client tự đặt có thể gây định tuyến sai hoặc lộ thông tin.

Khi cần reply tới client, dùng destination/route đã được allowlist hoặc tra từ registry nội bộ, kiểm tra authorization và không tạo channel tùy tiện từ chuỗi input.

## 5. Correlation Strategy tại các điểm vào

**Content-based correlation** suy ra khóa từ **dữ liệu nghiệp vụ đáng tin** (payload, bản ghi registry hoặc verified metadata), thay vì lấy một MessageHeaders.ID ngẫu nhiên.

Ví dụ quy tắc:

~~~text
businessCorrelationKey =
    "shipment-quote:v1:"
    + verifiedTenantId + ":"
    + normalizedShipmentId + ":"
    + workflowEpoch
~~~

Cùng tenant + shipment + epoch → cùng khóa, kể cả qua HTTP Gateway, JMS adapter hoặc một lần replay.

### 5.1. Ngăn hai lỗi trái chiều

| Lỗi | Nguyên nhân | Hậu quả |
| --- | --- | --- |
| **False split** | Cùng workflow nhưng mỗi adapter tạo UUID mới | Aggregator chia thành nhiều group thiếu reply |
| **False join** | Hai tenant/epochs khác nhau dùng cùng shipmentId | Ghép dữ liệu sai khách hàng/phiên bản |

Để tránh cả hai, cần:

- Tenant lấy từ security principal/ACL đã xác minh.
- Shipment/Order ID được canonicalize theo contract.
- Workflow epoch được lookup theo logical workflow, không tăng vì mỗi attempt.
- Một schema/key version nhất quán giữa nhiều ingress.
- Header mapping/wire envelope không làm mất identity ở chặng adapter.
- Kiểm thử cross-protocol và cross-tenant.

### 5.2. Không tự tin vào một header tên X-Correlation-ID

Client có thể gửi:

~~~http
POST /api/shipments/SHIP-901/quotes HTTP/1.1
X-Tenant-Id: tenant-admin
X-Correlation-ID: tenant-admin:SHIP-999:7
Content-Type: application/json

{"shipmentId":"SHIP-901","epoch":7}
~~~

Không chuyển nguyên **X-Tenant-Id** và **X-Correlation-ID** thành trustedTenantId/businessCorrelationKey của framework. Kiểm tra token, binding, quyền truy cập rồi tự tính hoặc tra business key nội bộ.

Nếu cần lưu một client-provided trace token, validate độ dài/charset và đặt trong header/log dành riêng cho tracking, **không** sử dụng làm khóa Aggregator hay cơ chế ủy quyền.

## 6. Java 17: model có identity và response rõ ràng

Ta dùng một ví dụ **tính báo giá nội bộ** để cô lập cơ chế Gateway; nó không gọi dịch vụ bên ngoài hoặc ghi database. Các phần sau sẽ thêm transport adapter.

~~~java
import java.math.BigDecimal;

record QuoteCommand(
        String shipmentId,
        int workflowEpoch,
        int packageCount) {
    QuoteCommand {
        if (shipmentId == null
                || !shipmentId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_SHIPMENT_ID");
        }
        if (workflowEpoch < 1 || packageCount < 1
                || packageCount > 1000) {
            throw new IllegalArgumentException("INVALID_QUOTE_INPUT");
        }
    }
}

record QuoteReceipt(
        String businessCorrelationKey,
        String shipmentId,
        BigDecimal amountVnd,
        String status) {
}
~~~

**QuoteCommand không chứa tenant do client tự khai.** Tenant được lấy từ security context đã xác minh và truyền qua một lớp application service, không suy ra từ request body.

### 6.1. Hàm tạo business key thuần

~~~java
final class QuoteCorrelation {
    private static final String PREFIX = "shipment-quote:v1:";
    private QuoteCorrelation() {}

    static String key(
            String verifiedTenantId,
            QuoteCommand command) {
        if (verifiedTenantId == null
                || !verifiedTenantId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_VERIFIED_TENANT");
        }
        return PREFIX + verifiedTenantId
                + ":" + command.shipmentId()
                + ":" + command.workflowEpoch();
    }
}
~~~

Đây là **quy tắc minh họa**: tenant dùng ký tự a-z, shipmentId chỉ có chữ/số/gạch nối/gạch dưới, epoch dương. Trong domain khác, nếu shipment ID có Unicode/dấu phân cách, phải dùng canonical encoding không nhập nhằng; nếu ID không được phép normalize case, tuyệt đối không tự uppercase/lowercase.

### 6.2. Application service giữ ranh giới tenant

~~~java
record VerifiedCaller(String principalId, String tenantId) {}

interface ShipmentAccessPolicy {
    void assertCanRequestQuote(
            VerifiedCaller caller,
            QuoteCommand command);
}

final class QuoteApplicationService {
    private final ShipmentAccessPolicy access;
    private final QuoteGateway gateway;

    QuoteApplicationService(
            ShipmentAccessPolicy access,
            QuoteGateway gateway) {
        this.access = access;
        this.gateway = gateway;
    }

    QuoteReceipt requestQuote(
            VerifiedCaller caller,
            QuoteCommand command) {
        access.assertCanRequestQuote(caller, command);
        String key = QuoteCorrelation.key(caller.tenantId(), command);
        return gateway.quote(command, key);
    }
}
~~~

**ShipmentAccessPolicy** trong production phải kiểm tra shipment thuộc tenant và workflowEpoch đúng với instance được phép. Nếu caller tự chọn bất kỳ epoch nào, cùng shipment có thể bị chia nhóm giả. Ví dụ assume policy sẽ xác minh điều đó trước khi gọi Gateway.

## 7. Messaging Gateway: truyền business key mà không chiếm replyChannel

Một gateway interface cho phép code nghiệp vụ gọi Java method, nhưng framework quản lý request message và reply destination.

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway
interface QuoteGateway {
    @Gateway(requestChannel = "quoteGatewayRequests")
    QuoteReceipt quote(
            @Payload QuoteCommand command,
            @Header("businessCorrelationKey") String groupKey);
}
~~~

**@Header trong ví dụ này nhận key từ QuoteApplicationService đã xác minh**, không phải một header do client trực tiếp điều khiển. Đừng cho API bên ngoài gọi gateway method với arbitrary groupKey nếu chưa qua policy.

### 7.1. Java DSL flow trả một reply đồng bộ

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class QuoteGatewayFlowConfig {
    @Bean
    MessageChannel quoteGatewayRequests() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow quoteGatewayFlow() {
        return IntegrationFlow.from("quoteGatewayRequests")
                .handle(QuoteCommand.class, (command, headers) -> {
                    Object rawKey = headers.get(
                            "businessCorrelationKey");
                    if (!(rawKey instanceof String key)
                            || key.isBlank()) {
                        throw new IllegalArgumentException(
                                "MISSING_BUSINESS_CORRELATION_KEY");
                    }

                    BigDecimal price =
                            BigDecimal.valueOf(75_000L)
                                    .multiply(BigDecimal.valueOf(
                                            command.packageCount()));

                    return new QuoteReceipt(
                            key,
                            command.shipmentId(),
                            price,
                            "QUOTED");
                })
                .get();
    }
}
~~~

Endpoint cuối .handle() trả một payload **QuoteReceipt không null**. Vì flow không cấu hình outputChannel cố định và request có replyChannel của Gateway, framework có thể gửi reply về destination đó. Đây là ví dụ request/reply **bên trong cùng Spring context**, không chứng minh transport headers có thể đi qua HTTP/JMS/TCP mà không cấu hình mapper.

### 7.2. Gateway làm gì khi không có reply?

Nếu handler trả null hoặc Filter loại request, caller có thể:

- Chờ đến **reply timeout** được cấu hình.
- Nhận null hoặc exception tùy Gateway method/config/version; cần test hợp đồng.
- Không thể suy ra dịch vụ ngoài đã không thực hiện effect chỉ từ việc không thấy reply.

Không dùng một hàm Gateway trả QuoteReceipt rồi cố tình gọi Service Activator one-way mà kỳ vọng reply tự xuất hiện.

Đặt timeout hữu hạn theo SLA. Nếu một request có thể chạy vài giờ, chọn mô hình **async accepted + trạng thái workflow**, không chặn thread Java/HTTP đến khi mọi event đến.

### 7.3. Một method Gateway trả void

Khi giao tiếp one-way, method có thể khai báo void. Theo tài liệu Spring Integration, với gateway method void (từ Spring Integration 5.4), nếu không có replyChannel được cung cấp, framework có thể đặt replyChannel trỏ tới nullChannel để loại những reply không cần thiết.

Điều này **không đồng nghĩa side effect đã hoàn tất** khi method trở về, đặc biệt nếu downstream async; và không biến một flow one-way thành cơ chế correlation của những event gửi sau.

## 8. Gửi request qua adapter: điều gì được giữ?

Khi đi qua network, Spring Message thường được ánh xạ sang định dạng của giao thức:

~~~text
Spring Message:
  payload=QuoteCommand
  headers:
    businessCorrelationKey=shipment-quote:v1:tenant-a:SHIP-901:7
    replyChannel=<temporary Java MessageChannel>
    id=<spring-message-id>

Network message:
  body=<serialized representation>
  protocol properties=<allowed mapped headers>
  reply destination=<JMSReplyTo / AMQP replyTo / HTTP response context>
~~~

**Không có quy tắc toàn cục rằng mọi header Spring được mang qua tất cả adapters.** Mỗi transport có HeaderMapper, MessageConverter, serializer/framing và cấu hình riêng. Một số transport gửi payload đơn thuần nếu không được cấu hình chuyển headers.

### 8.1. Bộ dữ liệu tối thiểu phải vượt qua wire khi có callback

Một remote reply hoặc event callback cần biết:

- **businessCorrelationKey** hoặc các thành phần đủ để **tra lại** key.
- **eventId** hoặc operationId để dedup.
- **producerId/supplierId/partKind** nếu group có nhiều nguồn kết quả.
- **schemaVersion** để parse đúng payload.
- **business status/result** để biết thành viên đã hoàn tất hay chưa.

Nếu request/reply cần đưa reply về đúng caller đang chờ, còn phải có **transport request token hoặc reply destination** theo quy tắc giao thức. Token này khác business group key và không tự thay thế nó.

### 8.2. Không serialize Spring Message nội bộ vô điều kiện

Một lời gọi kiểu:

~~~java
objectMapper.writeValueAsString(message.getHeaders());
~~~

không phải một protocol ổn định giữa các hệ thống. Header có thể chứa non-serializable objects như replyChannel/errorChannel, Java class hoặc metadata nội bộ. Hãy thiết kế **wire DTO/envelope** với tập field rõ ràng và version hóa.

## 9. Wire envelope: cách portable để giữ content-based key

Một cấu trúc wire JSON có thể được dùng nhất quán với HTTP, broker hoặc TCP:

~~~json
{
  "schemaVersion": 1,
  "businessCorrelationKey": "shipment-quote:v1:tenant-a:SHIP-901:7",
  "eventId": "evt-provider-778",
  "providerId": "PARTNER-A",
  "shipmentId": "SHIP-901",
  "workflowEpoch": 7,
  "result": {
    "status": "QUOTED",
    "totalVnd": "150000"
  }
}
~~~

Đây là **wire format của ứng dụng**, không phải Spring Integration auto mapping. Định nghĩa field và JSON schema version để cả hai phía hiểu:

- **businessCorrelationKey** là identity group **được sender nội bộ cấp**, không phải bằng chứng authorization.
- **eventId** giữ nguyên qua retry/redelivery của cùng result.
- **providerId** dùng để biết nguồn reply và chống đếm trùng một supplier.
- **shipmentId/epoch** dùng để kiểm tra key và domain identity khớp.
- **totalVnd** là chuỗi decimal nhằm tránh sai số số thực; phải validate scale/currency.

Một service ngoài chỉ được phép cung cấp các trường do contract cho phép. Ở inbound, không tin tenant/role chỉ vì được gửi trong JSON; xác thực source qua mTLS/OAuth/broker ACL và tra business mapping được phép.

### 9.1. Cần chống tampering/replay

Nếu một callback có body chứa businessCorrelationKey nhưng gửi từ người lạ, nó không được phép tham gia nhóm chỉ vì key có cú pháp hợp lệ. Quy trình inbound:

1. Xác thực producer identity.
2. Kiểm tra producer có quyền phát **providerId/partKind** này.
3. Validate schemaVersion, field length, enum, signature nếu hợp đồng yêu cầu.
4. Tra persisted shipment/workflow binding, đối chiếu shipmentId, epoch và tenant.
5. Tính lại hoặc tra **expected businessCorrelationKey**; từ chối mismatch.
6. Kiểm tra eventId đã xử lý chưa, payload digest có trùng bản trước không.
7. Chỉ sau đó dựng một **Spring Message nội bộ mới** gửi tới Aggregator/flow.

Không copy wire header replyChannel, errorChannel, routingSlip vào Spring Message nếu chúng đến từ vùng chưa tin cậy.

### 9.2. Java records làm wire contract

~~~java
import java.math.BigDecimal;

record QuoteResultWire(
        int schemaVersion,
        String businessCorrelationKey,
        String eventId,
        String providerId,
        String shipmentId,
        int workflowEpoch,
        String status,
        String totalVnd) {}

record VerifiedTransportPeer(
        String authenticatedPeerId,
        String tenantId) {}

record VerifiedQuoteResult(
        String businessCorrelationKey,
        String eventId,
        String providerId,
        String shipmentId,
        int workflowEpoch,
        String tenantId,
        String status,
        BigDecimal totalVnd) {}
~~~

Các record trên là DTO ví dụ; parser/deserializer của adapter cần kiểm tra input size và schema trước khi tạo VerifiedQuoteResult. Không dùng constructor record như là authentication.

### 9.3. Viết mapper inbound xác minh correlation

~~~java
import java.math.BigDecimal;
import java.util.Set;

interface QuoteWorkflowRegistry {
    boolean isActiveOrRecoverable(
            String tenantId, String shipmentId, int epoch);

    boolean mayReport(
            String authenticatedPeerId, String providerId);
}

final class QuoteWireVerifier {
    private final QuoteWorkflowRegistry registry;

    QuoteWireVerifier(QuoteWorkflowRegistry registry) {
        this.registry = registry;
    }

    VerifiedQuoteResult verify(
            QuoteResultWire wire,
            VerifiedTransportPeer peer) {

        if (wire == null || peer == null
                || wire.schemaVersion() != 1
                || wire.eventId() == null
                || !wire.eventId().matches("[A-Za-z0-9_-]{1,80}")
                || wire.providerId() == null
                || !Set.of("PARTNER-A", "PARTNER-B", "BACKUP")
                        .contains(wire.providerId())) {
            throw new IllegalArgumentException("INVALID_WIRE_EVENT");
        }

        if (!registry.mayReport(
                peer.authenticatedPeerId(), wire.providerId())) {
            throw new SecurityException("PROVIDER_NOT_AUTHORIZED");
        }

        QuoteCommand identity = new QuoteCommand(
                wire.shipmentId(), wire.workflowEpoch(), 1);
        if (!registry.isActiveOrRecoverable(
                peer.tenantId(), identity.shipmentId(),
                identity.workflowEpoch())) {
            throw new SecurityException("WORKFLOW_NOT_AUTHORIZED");
        }

        String expected = QuoteCorrelation.key(
                peer.tenantId(), identity);
        if (!expected.equals(wire.businessCorrelationKey())) {
            throw new SecurityException("CORRELATION_MISMATCH");
        }

        if (!"QUOTED".equals(wire.status())
                && !"UNAVAILABLE".equals(wire.status())) {
            throw new IllegalArgumentException("UNKNOWN_STATUS");
        }

        BigDecimal price = null;
        if ("QUOTED".equals(wire.status())) {
            try {
                price = new BigDecimal(wire.totalVnd());
            } catch (NumberFormatException | NullPointerException ex) {
                throw new IllegalArgumentException(
                        "INVALID_QUOTE_AMOUNT", ex);
            }
            if (price.signum() <= 0 || price.scale() > 0) {
                throw new IllegalArgumentException("INVALID_QUOTE_AMOUNT");
            }
        } else if (wire.totalVnd() != null) {
            throw new IllegalArgumentException("UNAVAILABLE_WITH_PRICE");
        }

        return new VerifiedQuoteResult(
                expected,
                wire.eventId(),
                wire.providerId(),
                identity.shipmentId(),
                identity.workflowEpoch(),
                peer.tenantId(),
                wire.status(),
                price);
    }
}
~~~

**Điểm chính:** mapper tính lại expected key từ **peer identity đã xác thực** và workflow registry. Nó không để remote producer tự quyết định group. price chỉ được parse khi QUOTED; với UNAVAILABLE, kết quả vẫn có thể được báo về Aggregator như **một terminal outcome có kiểu**.

**Giới hạn ví dụ:** production còn cần chứng thực peer→tenant mapping, rate limit, phân biệt timeout/UNKNOWN với UNAVAILABLE, currency, timestamp/signature và phòng chống eventId trùng nhưng payload khác. Cơ chế registry có thể cần transactional lookup; đoạn code không tự làm toàn bộ authentication.

### 9.4. Dựng lại Spring Message từ DTO đã xác minh

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class QuoteMessageMapper {
    static Message<VerifiedQuoteResult> internal(
            VerifiedQuoteResult result) {
        return MessageBuilder.withPayload(result)
                .setHeader(
                        "businessCorrelationKey",
                        result.businessCorrelationKey())
                .setHeader(
                        "trustedTenantId",
                        result.tenantId())
                .setHeader(
                        "businessEventId",
                        result.eventId())
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        result.businessCorrelationKey())
                .build();
    }
}
~~~

Message được tạo lại ở inbound sẽ có Spring MessageHeaders.ID mới, nhưng **businessCorrelationKey và eventId giữ nguyên**. Không copy một replyChannel do wire body hoặc HTTP header tự khai. Đây là cách tách **wire metadata** khỏi **framework routing metadata**.

### 9.5. Vì sao cần schemaVersion?

Nếu provider nâng schema từ version 1 sang version 2 mà âm thầm đổi tên trường shipmentId, mappers có thể không đọc ra identity đúng. Với correlation, **silent fallback** từ missing shipmentId sang ID ngẫu nhiên là nguy hiểm: nó chia group thật ra nhiều nhóm sai.

Hãy reject/quarantine schema chưa hỗ trợ hoặc dùng một converter versioned có test tương thích. Nếu thay thuật toán tạo key, version hóa key và có kế hoạch drain/migrate group còn mở.

## 10. HTTP: request-response transport khác business callback

HTTP kết nối một request với response trên chính cuộc gọi HTTP. Nếu ứng dụng chỉ gửi quote request và nhận response ngay, **HTTP outbound gateway** có thể biểu diễn request/reply này mà không cần đặt một HTTP header mới để framework nhớ socket nào đang chờ.

Tuy nhiên, khi remote service **trả 202 Accepted** rồi callback sau vài phút, HTTP response ban đầu đã kết thúc. Callback là **một request HTTP khác**, không thể tự quay lại temporary replyChannel của Gateway cũ.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Application
    participant P as Provider
    participant S as Workflow Store
    C->>A: POST /quote-requests
    A->>S: Persist businessCorrelationKey + state
    A->>P: POST /provider/quotes + business operation ID
    P-->>A: HTTP 202 Accepted
    A-->>C: HTTP 202 + trackingId
    Note over C,A: Request/reply HTTP đầu tiên đã kết thúc
    P->>A: POST /callbacks với eventId và group key
    A->>S: Verify provider + dedup + correlate
    A-->>P: HTTP 2xx khi callback được nhận bền
    A->>S: Aggregate / complete workflow
~~~

### 10.1. HTTP HeaderMapper có thể làm mất custom header

Spring Integration sử dụng HTTP HeaderMapper, và có cách cấu hình các header request/response được map. Theo tài liệu, **standard HTTP headers** có mapping mặc định; khi cấu hình danh sách header tùy chỉnh, cần xem việc mapping đã bao gồm các standard headers mong muốn chưa.

Không mặc định một custom Spring header tên businessCorrelationKey sẽ luôn xuất hiện ở peer dưới tên X-Business-Correlation-Key, cũng không mặc định một HTTP header remote sẽ tự trở thành trusted Spring Message header.

Một ví dụ XML về chọn header outbound:

~~~xml
<!-- Mảnh cấu hình, giả định đã khai báo namespace int-http
     và bean channels/connection phù hợp. -->
<int-http:outbound-gateway
    id="remoteQuoteHttpGateway"
    url="https://provider.example/quotes"
    request-channel="remoteQuoteHttpRequests"
    reply-channel="remoteQuoteHttpReplies"
    mapped-request-headers="X-Operation-Id, X-Trace-Id, HTTP_REQUEST_HEADERS"
    mapped-response-headers="HTTP_RESPONSE_HEADERS" />
~~~

Đây là **cú pháp minh họa cho HeaderMapper**, không phải một cấu hình TLS/HTTP client production hoàn chỉnh. Không gửi dữ liệu bảo mật nhạy cảm trong custom headers, và không tin header response do remote service phát mà chưa kiểm tra nguồn.

### 10.2. Nên đặt business ID ở body hay header?

| Phương án | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| **Body / wire envelope** | Callback/broker event là dữ liệu nghiệp vụ | Contract versioned; validate đầy đủ |
| **HTTP header** | Tracing/routing giữa dịch vụ tin cậy | Có thể bị proxy/gateway rewrite hoặc không được map |
| **Cả body và header** | Cần quan sát nhanh và domain correlation bền | Phải kiểm tra hai giá trị khớp, không chọn im lặng |

Một **business correlation key trong body** giúp dữ liệu vẫn có meaning sau khi đã lưu event hoặc replay từ DLQ. HTTP header bổ sung có thể có ích cho tracing nhưng không thay thế nội dung nghiệp vụ đã được xác thực.

### 10.3. Không biến HTTP 200 thành bằng chứng aggregate completed

HTTP outbound gateway nhận 200 OK nghĩa là remote HTTP endpoint đã trả thành công theo contract của nó. Điều đó có thể có nghĩa **đã tiếp nhận request**, chứ không phải ba suppliers đã gửi đủ outcomes hoặc booking đã hoàn tất.

Phân biệt các trạng thái:

~~~text
HTTP_RECEIVED
REMOTE_ACCEPTED
WORKFLOW_IN_PROGRESS
WORKFLOW_COMPLETED
WORKFLOW_FAILED
WORKFLOW_UNKNOWN
~~~

Đặt trạng thái chính xác trong workflow state store và API trạng thái. Tránh phát business event COMPLETED chỉ dựa vào việc gửi request qua adapter không ném lỗi.

## 11. JMS: JMSCorrelationID và JMSReplyTo là giao thức request/reply

Một JMS outbound gateway có thể gửi request message tới **request destination** rồi đợi reply từ **reply destination**. Theo tài liệu Spring Integration JMS, nếu không đặt thuộc tính correlation-key, gateway thường mong response có JMSCorrelationID tương ứng với **JMSMessageID của outbound request**. Khi đặt correlation-key, gateway có thể tạo correlation token riêng và yêu cầu responder echo token đó trong cùng property/header.

~~~text
JMS request:
  JMSMessageID = ID:broker-391
  JMSReplyTo   = queue.reply.temporary
  businessCorrelationKey = shipment-quote:v1:tenant-a:SHIP-901:7

JMS reply:
  JMSCorrelationID = ID:broker-391
  body = provider response
~~~

JMSCorrelationID trong ví dụ đang ghép một **request và một reply JMS**, không nhất thiết là khóa để Aggregator ghép các kết quả nghiệp vụ của nhiều nhà cung cấp. Ngay cả khi cả hai chuỗi có nội dung giống nhau do cấu hình, chúng vẫn có **hai trách nhiệm khác nhau**.

### 11.1. Không ghi đè JMSCorrelationID mù quáng

Spring Integration JMS có nhiều chế độ correlation-key và reply-listener, ví dụ cho phép chỉ định JMSCorrelationID hoặc custom property. Một số chế độ cho phép dùng ID có sẵn, một số chế độ **không tương thích** với reply listener vì yêu cầu uniqueness/selector riêng.

**Quy tắc:** nếu đang dùng Outbound Gateway có quản lý reply, để Gateway và đối tác tuân thủ protocol correlation đã thống nhất. Không tự đặt JMSCorrelationID = orderId cho tất cả request đồng thời khi chưa kiểm tra semantics và uniqueness; điều đó có thể dẫn tới reply bị khớp sai hoặc selector không hoạt động đúng.

### 11.2. JMS channel adapter one-way không tự tạo request/reply correlation

Với hai adapters độc lập:

~~~text
JMS outbound adapter -> queue.request
Remote worker        -> queue.response
JMS inbound adapter  -> application
~~~

Không có một **temporary Gateway replyChannel** đương nhiên nối hai phía. Ứng dụng phải mang request identity qua wire (businessCorrelationKey, eventId, operationId) và đặt **correlation logic** ở inbound/recovery/aggregator. Dùng một response topic có partition/routing key phù hợp, inbox/dedup và TTL.

### 11.3. Mapper và converter phải được cấu hình theo contract

Spring Integration JMS hỗ trợ **HeaderMapper** để chuyển Spring Message headers sang JMS properties/headers và ngược lại. Không giả định mọi kiểu Java object header đều chuyển được thành JMS property. Dùng giá trị wire-compatible (String, số, Boolean, ...) và một DTO/JSON body versioned cho dữ liệu nghiệp vụ.

Nếu dùng JMS ReplyTo/correlation cho một gateway sync, **đừng serialize replyChannel Java object** rồi chuyển qua broker. Đó không phải cách JMS gateway quản lý reply.

## 12. AMQP: replyTo/correlation của RPC khác business group

Spring Integration AMQP có cả **channel adapters one-way** và **inbound/outbound gateways request/reply**. Với RabbitMQ, cơ chế RPC thường dùng các thuộc tính giao thức như replyTo và correlationId, do Spring AMQP/Integration adapter quản lý.

~~~mermaid
sequenceDiagram
    participant A as App A
    participant B as AMQP Broker
    participant S as Service B
    A->>B: Request + replyTo + AMQP correlation
    B->>S: Deliver request
    S->>B: Reply + matching correlation
    B-->>A: Deliver reply
    Note over A: Gateway khớp reply với request chờ
~~~

**Business correlation key** có thể được gửi như một allowed AMQP header hoặc trong body. Khi event từ nhiều services cùng thuộc một workflow, business key mới là thông tin dùng để gom chúng ở Aggregator.

### 12.1. Hai kiểu triển khai AMQP không tương đương

- **Outbound Gateway**: thích hợp khi cần một reply theo RPC contract và có reply deadline; adapter quản lý response theo AMQP request/reply.
- **Outbound Adapter + Inbound Adapter**: thích hợp khi trao đổi sự kiện bất đồng bộ, callback có thể đến muộn, nhiều reply hoặc nhiều worker; application phải có correlation/idempotency/workflow state của riêng mình.

Nếu remote xử lý lâu hơn reply timeout, một gateway sync không giữ được ý nghĩa “chờ kết quả cuối cùng” chỉ bằng cách tăng timeout vô hạn. Dùng event-driven reply và workflow store nếu cần chịu lỗi dài hạn.

### 12.2. HeaderMapper và producer trust

AMQP header có thể do producer gửi; broker ACL/mTLS giúp xác minh **connection identity**, nhưng không tự biến mọi business field trong payload thành đáng tin. Ở inbound:

1. Xác thực source/routing permissions.
2. Deserialize đúng schema.
3. Tính hoặc lookup business key từ trusted tenant/workflow state.
4. So sánh business key đi kèm với expected key.
5. Tạo Spring Message nội bộ và loại những header điều khiển không được phép.

Không chấp nhận arbitrary routingSlips, errorChannel hoặc replyChannel từ AMQP message chưa qua trust boundary.

## 13. TCP: gateway có correlation, collaborating adapters cần application logic

Theo tài liệu Spring Integration **TCP Message Correlation**:

- TCP Gateways hỗ trợ correlation request/reply tương ứng.
- Với một single shared connection, một outbound gateway có thể bị giới hạn chỉ một request/reply đang hoạt động tại một thời điểm trên connection đó; throughput cần được đánh giá theo cấu hình connection factory.
- Với collaborating inbound/outbound adapters phía client, **application correlation thường phải tự triển khai**.
- Ở server, TCP inbound adapter gắn **ip_connectionId** để outbound adapter biết gửi reply về TCP connection nào.
- TCP mặc định thường chuyển **payload**; muốn chuyển headers phải cấu hình mapper và serializer phù hợp.

### 13.1. ip_connectionId không thay cho correlationId của đơn hàng

~~~text
TCP connection ip_connectionId = conn-10
  request A: shipment SHIP-901 / epoch 7
  request B: shipment SHIP-902 / epoch 1

Cả A và B đi cùng conn-10:
  ip_connectionId giống nhau
  businessCorrelationKey khác nhau
~~~

Một connection có thể phục vụ nhiều logical requests; nhiều connection khác nhau có thể được dùng cho cùng business workflow qua retry. Vì vậy ip_connectionId không phải business group key và không phải eventId.

### 13.2. TCP header transfer là cấu hình rõ ràng

Tài liệu TCP mô tả cách dùng **MessageConvertingTcpMessageMapper** và serializer/deserializer để chuyển selected headers cùng payload. Trong đó có thể chọn correlationId, sequenceNumber, sequenceSize hoặc header business custom theo nhu cầu.

Mặc định chỉ chuyển payload trong nhiều cấu hình TCP. **Không** tạo một message mới ở đầu nhận rồi mong tất cả Spring MessageHeaders của bên gửi tự xuất hiện.

Với hệ thống đa ngôn ngữ, một wire envelope JSON/protobuf có field businessCorrelationKey thường dễ kiểm soát hơn một serialized Java Message object.

### 13.3. TCP half-close, timeout và late replies

Một request có thể đã tới server nhưng connection rớt trước khi reply về. Caller timeout **không chứng minh server chưa thực hiện tác động**. Khi retry qua connection khác:

- Giữ business operation ID ổn định.
- Server thực hiện idempotency/tra cứu trạng thái.
- Nếu reply của attempt cũ đến muộn, không gán nhầm vào attempt mới.
- Nếu là TCP adapters bất đồng bộ, app phải có store ánh xạ request→response thay vì dựa vào connectionId đơn lẻ.

## 14. File/SFTP/email adapter không có request/reply correlation sẵn

Một file inbound adapter hoặc email inbound adapter thường tạo message từ file/email/event. File name, mtime, email Message-ID có thể giúp nhận diện nguồn nhưng **không tự trở thành business group ID**.

Ví dụ một batch import được chia qua nhiều file:

~~~text
import-APR-10-part-1.csv
import-APR-10-part-2.csv
import-APR-10-part-3.csv
~~~

Ứng dụng cần validate manifest của batch, expected count, tenant và version; sau đó tạo businessCorrelationKey từ **batch identity**. Không nhóm mọi file có cùng prefix do người dùng tự đặt nếu chưa xác minh file thuộc batch/tenant hợp lệ.

File move/rename sau khi đọc không bảo đảm dữ liệu đã commit. Nếu một file được quét lại sau crash, dùng file checksum/eventId/inbox để chống side effect trùng và tránh nhận nhầm cùng file thành một group mới.

## 15. Nhiều callbacks cùng workflow: Aggregator dùng key nào?

Giả sử một quote request yêu cầu **ba nhà cung cấp** phản hồi qua các inbound adapters khác nhau:

~~~text
PARTNER-A -> HTTP callback -> VerifiedQuoteResult
PARTNER-B -> JMS inbound   -> VerifiedQuoteResult
BACKUP    -> AMQP inbound  -> VerifiedQuoteResult
~~~

Cả ba messages phải mang **cùng businessCorrelationKey**. Tuy nhiên **eventId, providerId, transport correlation IDs** của chúng khác nhau. Một Aggregator nội bộ có thể nhóm theo businessCorrelationKey đã được xác minh.

### 15.1. Group khác message count

Ba messages đều từ PARTNER-A không được coi là đã nhận đủ ba suppliers. ReleaseStrategy phải kiểm tra tập providers kỳ vọng:

~~~text
expected = {PARTNER-A, PARTNER-B, BACKUP}
received = {PARTNER-A, PARTNER-B, BACKUP}
=> complete

received = {PARTNER-A, PARTNER-A, BACKUP}
=> NOT complete, dù đã nhận 3 messages
~~~

Với redelivery, cần xử lý duplicate **trước Aggregator**. Nếu duplicate làm group có bốn messages, một release strategy kiểm tra size==3 có thể chờ mãi; đừng chỉ thay bằng size>=3 vì như vậy bỏ qua duplicate/collision.

### 15.2. Java DSL nhóm callbacks theo content-based key

~~~java
import java.util.Set;
import java.util.HashSet;
import org.springframework.integration.store.MessageGroup;

final class QuoteGroupRules {
    static final Set<String> EXPECTED =
            Set.of("PARTNER-A", "PARTNER-B", "BACKUP");

    private QuoteGroupRules() {}

    static boolean complete(MessageGroup group) {
        if (group.size() != EXPECTED.size()) {
            return false;
        }

        Set<String> providers = new HashSet<>();
        for (var message : group.getMessages()) {
            if (!(message.getPayload()
                    instanceof VerifiedQuoteResult result)) {
                return false;
            }
            if (!EXPECTED.contains(result.providerId())
                    || !providers.add(result.providerId())) {
                return false;
            }
        }
        return providers.equals(EXPECTED);
    }
}
~~~

Một IntegrationFlow minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class QuoteCallbackFlowConfig {

    @Bean
    MessageChannel verifiedQuoteCallbacks() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel quoteAggregationOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow callbackAggregationFlow() {
        return IntegrationFlow.from("verifiedQuoteCallbacks")
                .aggregate(a -> a
                        .correlationStrategy(message -> {
                            Object value = message.getHeaders()
                                    .get("businessCorrelationKey");
                            if (!(value instanceof String key)
                                    || key.isBlank()) {
                                throw new IllegalArgumentException(
                                        "MISSING_CORRELATION_KEY");
                            }
                            return key;
                        })
                        .releaseStrategy(QuoteGroupRules::complete)
                        .outputProcessor(QuoteReports::fromGroup)
                        .groupTimeout(30_000)
                        .sendPartialResultOnExpiry(false))
                .channel("quoteAggregationOutput")
                .get();
    }
}
~~~

**Điểm quan trọng:** Đầu vào verifiedQuoteCallbacks **chỉ nhận messages đã qua QuoteWireVerifier**. Một HTTP callback không được gửi trực tiếp payload chưa xác thực vào aggregator. Cấu hình này mang tính **minh họa trong một Spring context**, chưa có persistent MessageGroupStore, inbox, multi-instance lock hoặc business deadline thực.

### 15.3. Tạo báo cáo khi đủ ba nguồn

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;

import org.springframework.integration.store.MessageGroup;

record QuoteAggregationReport(
        String businessCorrelationKey,
        int receivedCount,
        String status,
        VerifiedQuoteResult bestQuote,
        List<VerifiedQuoteResult> outcomes) {}

final class QuoteReports {
    private QuoteReports() {}

    static QuoteAggregationReport fromGroup(MessageGroup group) {
        if (!QuoteGroupRules.complete(group)) {
            throw new IllegalStateException("INCOMPLETE_QUOTE_GROUP");
        }

        List<VerifiedQuoteResult> outcomes = group.getMessages().stream()
                .map(message ->
                        (VerifiedQuoteResult) message.getPayload())
                .sorted(Comparator.comparing(
                        VerifiedQuoteResult::providerId))
                .toList();

        String key = outcomes.get(0).businessCorrelationKey();
        String tenant = outcomes.get(0).tenantId();
        for (VerifiedQuoteResult item : outcomes) {
            if (!key.equals(item.businessCorrelationKey())
                    || !tenant.equals(item.tenantId())) {
                throw new IllegalStateException(
                        "MIXED_CORRELATION_OR_TENANT");
            }
        }

        VerifiedQuoteResult best = outcomes.stream()
                .filter(item -> "QUOTED".equals(item.status()))
                .min(Comparator.comparing(
                        VerifiedQuoteResult::totalVnd))
                .orElse(null);

        return new QuoteAggregationReport(
                key,
                outcomes.size(),
                best == null ? "NO_OFFER"
                        : outcomes.stream().allMatch(item ->
                                "QUOTED".equals(item.status()))
                                ? "COMPLETE"
                                : "PARTIAL_SUPPLIER_FAILURE",
                best,
                List.copyOf(outcomes));
    }
}
~~~

**Giới hạn ví dụ:** report chỉ chứng minh đã có ba **terminal outcomes** trong nhóm đang xử lý; nó không đảm bảo ba suppliers đã commit cùng transaction. Nếu mọi supplier UNAVAILABLE, bestQuote=null là hợp lệ, nhưng reportStatus phải là NO_OFFER, không phải COMPLETE.

### 15.4. Correlation cho sub-groups của Splitter

Khi một flow vừa Splitter một batch rồi gọi ba providers cho **mỗi item**, có ít nhất hai tầng correlation:

~~~text
batch = B-100
  item 1 -> provider replies (PARTNER-A/B/BACKUP)
  item 2 -> provider replies (PARTNER-A/B/BACKUP)
  item 3 -> provider replies (PARTNER-A/B/BACKUP)
~~~

Nếu dùng chỉ batchId làm key, 9 supplier replies bị trộn thành một group thay vì ba subgroups. Cần key ở cấp **batchId + itemId + workflowEpoch** cho provider results, rồi một Aggregator cha gom item summaries theo batch key. Không tự copy CORRELATION_ID từ một Splitter mà không kiểm tra group semantics.

## 16. Timeout: Gateway, adapter và Aggregator có đồng hồ khác nhau

Một ứng dụng có thể cấu hình **bốn mốc timeout** cho cùng workflow:

| Timeout | Nơi áp dụng | Điều xảy ra khi hết hạn |
| --- | --- | --- |
| **Gateway reply timeout** | Lời gọi Java request/reply | Caller không còn đợi reply |
| **Transport timeout** | HTTP/JMS/AMQP/TCP | Attempt giao tiếp có thể thất bại hoặc mất connection |
| **Aggregator groupTimeout** | Nhóm messages trong MessageGroupStore | Group chưa đủ được xử lý theo expiry policy |
| **Business deadline** | Persistent workflow state | Workflow chuyển sang INCOMPLETE/FAILED/RECONCILING |

Không đặt cả bốn bằng 5 giây rồi nghĩ hệ thống sẽ nhất quán. Một external provider có thể:

1. Nhận request và hoàn tất nghiệp vụ sau 4,9 giây.
2. Response bị kẹt trong broker, Gateway timeout ở giây thứ 5.
3. Reply đến inbound adapter ở giây thứ 7.
4. Aggregator vẫn có thể nhận được event **nếu workflow chưa đóng**.

Ở thời điểm Gateway timeout, **không thể kết luận remote effect đã thất bại**.

### 16.1. Late reply của Gateway không đồng nghĩa late business event

~~~mermaid
sequenceDiagram
    participant C as Gateway Caller
    participant A as App / Gateway
    participant P as Provider
    participant W as Workflow Store
    C->>A: invoke quote()
    A->>P: request attempt A
    Note over A: replyTimeout elapsed
    A-->>C: Timeout / null theo contract
    P-->>A: Reply attempt A đến muộn
    A->>W: Kiểm tra trạng thái workflow
    Note over W: Business deadline có thể chưa hết
~~~

Late reply của **attempt** có thể không còn caller chờ, nhưng vẫn có thể là thông tin nghiệp vụ hợp lệ. Có thể lưu vào workflow state qua một channel adapter riêng, hoặc discard/audit nếu contract đã chốt kết quả.

Đừng cố resurrect temporary replyChannel đã hết thời gian chờ hoặc gửi trực tiếp reply muộn tới một invocation Java mới. Dùng business key và persisted state để quyết định có nhận kết quả muộn không.

### 16.2. Partial result cần nói rõ loại partial

Hai tình huống khác nhau:

- **Ba terminal replies**, một supplier từ chối: group hoàn tất, reportStatus=PARTIAL_SUPPLIER_FAILURE.
- **Chỉ hai trên ba replies** trước business deadline: group chưa đủ, reportStatus=INCOMPLETE nếu nghiệp vụ muốn phát một snapshot.

Nếu bật sendPartialResultOnExpiry ở Aggregator nhưng vẫn dùng QuoteReports.fromGroup() vốn cần đủ ba suppliers, processor có thể ném lỗi khi nhận group chưa đầy đủ. Muốn partial release phải **tạo processor riêng**, dùng manifest expected providers và danh sách missing providers.

### 16.3. Group cleanup và late arrivals

Sau khi Aggregator release group, Spring Integration có thể giữ metadata completed group để nhận diện late message. Nếu group bị xóa hoàn toàn do cleanup, một bản reply cũ cùng correlationId có thể tạo **group mới**.

Thời gian retention phải được xác định theo broker redelivery, DLQ replay và lịch xử lý của workflow. Nếu cần chống duplicate qua thời gian dài hơn metadata store, dùng inbox/event ledger bền.

## 17. Retry và idempotency: giữ business key, thay attempt token khi cần

Khi một gateway/outbound adapter gặp timeout, có thể retry. Đừng tạo business key mới cho mỗi retry:

~~~text
logicalOperation = tenant-a / SHIP-901 / epoch 7 / provider PARTNER-A

attempt 1:
  businessCorrelationKey = shipment-quote:v1:tenant-a:SHIP-901:7
  operationId = quote:SHIP-901:7:PARTNER-A
  transportCorrelation = transport-001

attempt 2:
  businessCorrelationKey = shipment-quote:v1:tenant-a:SHIP-901:7
  operationId = quote:SHIP-901:7:PARTNER-A
  transportCorrelation = transport-002
~~~

**businessCorrelationKey và operationId** ổn định theo logical work. Transport correlation được gateway/protocol quản lý cho từng attempt. Một callback có thể phải ánh xạ transport-001 hoặc transport-002 về cùng business operation.

### 17.1. Những lỗi thường xảy ra khi retry toàn flow

Giả sử đã nhận báo giá từ PARTNER-A và PARTNER-B, nhưng BACKUP timeout:

~~~text
Attempt 1:
  PARTNER-A -> QUOTED
  PARTNER-B -> QUOTED
  BACKUP    -> timeout

Retry cả workflow:
  PARTNER-A bị gọi lại
  PARTNER-B bị gọi lại
  BACKUP bị gọi lại
~~~

Nếu provider chỉ tính toán một quote đọc dữ liệu, lặp có thể ít rủi ro side effect hơn. Nếu provider **giữ chỗ, thu phí hoặc tạo vận đơn**, lặp có thể tạo tác động trùng. Đặt retry ở phạm vi hẹp nhất cần thiết và dùng provider idempotency key khi hỗ trợ.

### 17.2. Inbox bền cho inbound callbacks

Một bảng PostgreSQL minh họa:

~~~sql
CREATE TABLE quote_callback_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    provider_id VARCHAR(48) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    group_key VARCHAR(240) NOT NULL,
    payload_digest VARCHAR(128) NOT NULL,
    status VARCHAR(24) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, provider_id, event_id)
);

CREATE INDEX quote_callback_inbox_group_idx
    ON quote_callback_inbox (group_key);

CREATE TABLE quote_provider_operation (
    tenant_id VARCHAR(48) NOT NULL,
    group_key VARCHAR(240) NOT NULL,
    provider_id VARCHAR(48) NOT NULL,
    operation_id VARCHAR(100) NOT NULL,
    status VARCHAR(24) NOT NULL,
    PRIMARY KEY (tenant_id, group_key, provider_id)
);
~~~

Các primary keys được chọn theo contract: eventId của provider chỉ được xem là duy nhất trong phạm vi tenant + provider. Nếu một producer gửi cùng eventId với payload digest khác, báo **ID_CONFLICT** và quarantine; đừng tự đổi eventId để bỏ qua lỗi.

### 17.3. Cửa sổ crash giữa dedup và dispatch

Một đoạn flow thiếu transaction/recovery có thể làm mất result:

~~~text
1. INSERT inbox event-1 status=SEEN
2. Commit
3. Crash trước khi gửi event-1 tới Aggregator
4. Broker redeliver event-1
5. Code thấy SEEN -> bỏ qua
=> Aggregator không bao giờ nhận event-1
~~~

Giải pháp có thể là **transactional inbox/outbox**, hoặc state machine inbox phân biệt RECEIVED, DISPATCH_PENDING, DISPATCHED, PROCESSED và một recovery worker. Không chỉ đánh dấu “đã thấy” rồi drop mọi redelivery mà không biết bước downstream đã xảy ra chưa.

### 17.4. Một terminal outcome cho một provider

Nếu timeout dẫn đến error handler tạo UNAVAILABLE rồi provider thật trả QUOTED muộn, cần chính sách rõ:

- Không đưa cả hai outcomes vào Aggregator như hai providers khác nhau.
- Dedup theo logical provider operation.
- Nếu report đã công bố, chọn freeze hoặc tạo revision với audit.
- Nếu external effect UNKNOWN, đối soát trước khi ra quyết định.

**Gateway timeout không phải một business failure outcome có thể dùng để tự động ghi đè reply hợp lệ.**

## 18. Error channel, DLQ và compensation

Trong DirectChannel đồng bộ, exception thường truyền ngược về caller. Với ExecutorChannel, poller hoặc broker, lỗi có thể được đưa vào ErrorMessage theo cơ chế xử lý lỗi của endpoint.

Một ErrorMessage không tự thay thế một VerifiedQuoteResult, và **errorChannel không tự đồng nghĩa với durable DLQ**. Nếu một provider callback có lỗi:

1. Xác định failedMessage và trusted metadata (có thể thiếu trong một số exception).
2. Phân loại schema/security/validation vs transient network/DB vs application bug.
3. Không cho lỗi bảo mật vào group.
4. Retry có giới hạn cho lỗi tạm thời, giữ cùng eventId/operationId.
5. Với lỗi đã terminal và có đầy đủ identity đáng tin, có thể tạo failure outcome hợp lệ theo domain.
6. Nếu không biết side effect đã xảy ra chưa, lưu UNKNOWN và đối soát.
7. Ghi đủ audit/trace và chuyển message không xử lý được vào quarantine/DLQ bền nếu contract yêu cầu.

### 18.1. Lỗi giao thức không phải lỗi correlation nghiệp vụ

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra trước tiên |
| --- | --- | --- |
| Java Gateway timeout | Không có reply/Filter drop/transport delay | replyChannel và downstream reply path |
| JMS reply không tới Gateway | JMSCorrelationID/JMSReplyTo sai | protocol correlation và reply destination |
| AMQP RPC chờ mãi | replyTo/correlation mismatch | RabbitTemplate/gateway configuration |
| TCP gửi reply nhầm connection | ip_connectionId sai/mất | connection routing metadata |
| Aggregator chờ thiếu member | business key sai hoặc một provider không trả | verified business key + expected provider set |
| Hai workflow bị trộn | thiếu tenant/epoch, collision | ingress trust boundary + key schema |
| Cùng provider được đếm hai lần | broker redelivery/duplicate callback | inbox/eventId + operation ledger |
| HTTP 202 nhưng không thấy report | callback chưa tới hoặc mapping lỗi | workflow state + callback endpoint |

Đừng kết luận “correlationId sai” chỉ vì Gateway timeout; cần biết **lớp nào** không khớp: Java replyChannel, protocol request/reply hay business group.

### 18.2. Khi nào tạo compensation reply?

Trong một scatter-gather cần một terminal outcome cho từng nhánh, recovery handler có thể phát failure outcome sau khi retry hết hạn và lỗi được phân loại. Nhưng:

- Phải giữ đúng **business key và providerId**.
- Phải chống phát hai outcomes nếu provider trả thật muộn.
- Không đánh dấu UNAVAILABLE cho một payment charge có trạng thái UNKNOWN.
- Không copy raw errorChannel/replyChannel từ payload untrusted để gửi compensation.

Nếu không đủ metadata đáng tin, quarantine và thông báo điều tra; không đoán correlation key theo tên exception.

## 19. Unit test: business key ổn định qua các attempts

Trước khi thử các adapter, kiểm tra contract của business key bằng JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class QuoteCorrelationTest {

    @Test
    void sameVerifiedWorkflowHasSameKeyOnRetry() {
        QuoteCommand command =
                new QuoteCommand("SHIP-901", 7, 2);

        String attempt1 = QuoteCorrelation.key(
                "tenant-a", command);
        String attempt2 = QuoteCorrelation.key(
                "tenant-a", command);

        assertEquals(attempt1, attempt2);
        assertEquals(
                "shipment-quote:v1:tenant-a:SHIP-901:7",
                attempt1);
    }

    @Test
    void differentTenantOrEpochGetsDifferentKey() {
        QuoteCommand epoch7 =
                new QuoteCommand("SHIP-901", 7, 2);
        QuoteCommand epoch8 =
                new QuoteCommand("SHIP-901", 8, 2);

        assertNotEquals(
                QuoteCorrelation.key("tenant-a", epoch7),
                QuoteCorrelation.key("tenant-b", epoch7));
        assertNotEquals(
                QuoteCorrelation.key("tenant-a", epoch7),
                QuoteCorrelation.key("tenant-a", epoch8));
    }

    @Test
    void invalidTenantCannotEnterCorrelationGroup() {
        QuoteCommand command =
                new QuoteCommand("SHIP-901", 7, 1);
        assertThrows(IllegalArgumentException.class,
                () -> QuoteCorrelation.key(
                        "tenant-a:admin", command));
    }
}
~~~

Test này xác minh deterministic key; **không** kiểm tra ShipmentAccessPolicy hoặc quyền producer thực tế. Trong production, hai tenants có thể có shipment IDs giống nhau, vì vậy test khác tenant là bắt buộc, không chỉ là trường hợp hiếm.

## 20. Integration test: Messaging Gateway reply đúng invocation

Với cấu hình QuoteGatewayFlowConfig ở phần 7, một integration test cần xác minh rằng:

1. Gateway method trả **QuoteReceipt** chứ không phải một internal Spring Message.
2. businessCorrelationKey do caller tin cậy truyền được tới handler.
3. Hai lời gọi có khóa khác nhau nhận đúng receipt.
4. Kết quả không phụ thuộc vào việc caller tạo/đọc temporary replyChannel thủ công.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(QuoteGatewayFlowConfig.class)
class QuoteGatewayFlowTest {

    @Autowired
    QuoteGateway gateway;

    @Test
    void gatewayReplyKeepsBusinessCorrelationKey() {
        QuoteCommand command =
                new QuoteCommand("SHIP-901", 7, 2);
        String key = QuoteCorrelation.key("tenant-a", command);

        QuoteReceipt reply = gateway.quote(command, key);

        assertNotNull(reply);
        assertEquals(key, reply.businessCorrelationKey());
        assertEquals("SHIP-901", reply.shipmentId());
        assertEquals("QUOTED", reply.status());
        assertEquals(new BigDecimal("150000"),
                reply.amountVnd());
    }

    @Test
    void twoInvocationsDoNotShareTheBusinessKey() {
        QuoteCommand first =
                new QuoteCommand("SHIP-901", 7, 1);
        QuoteCommand second =
                new QuoteCommand("SHIP-902", 4, 3);

        QuoteReceipt replyA = gateway.quote(
                first, QuoteCorrelation.key("tenant-a", first));
        QuoteReceipt replyB = gateway.quote(
                second, QuoteCorrelation.key("tenant-b", second));

        assertNotEquals(
                replyA.businessCorrelationKey(),
                replyB.businessCorrelationKey());
        assertEquals("SHIP-901", replyA.shipmentId());
        assertEquals("SHIP-902", replyB.shipmentId());
    }
}
~~~

**Điều kiện:** ví dụ đặt interface @MessagingGateway và @IntegrationComponentScan trong cùng phạm vi package được scan. Spring Integration và spring-test/JUnit 5 phải có trên classpath. Không tự chạy test trong bước viết nội dung; khi tích hợp vào project cần điều chỉnh package/bean scanning theo cấu trúc thực tế.

### 20.1. Test Gateway timeout không giống kiểm tra correlation

Một test khác có thể cấu hình một Gateway riêng với replyTimeout ngắn và downstream không tạo reply, rồi kiểm tra hợp đồng timeout. Không gửi request vào một Gateway có thời gian chờ không giới hạn để test “mất reply” vì nó có thể làm suite treo.

Trong test HTTP/JMS/AMQP thật, cần kiểm tra **reply adapter** đang dùng đúng request/reply correlation do transport cấu hình. Hai tests ở trên chỉ kiểm tra Gateway local, chưa kiểm chứng việc serialize wire.

## 21. Unit test: inbound wire mapper không tin correlation giả mạo

Tạo một registry giả chỉ cho peer-partner-a báo kết quả PARTNER-A cho shipment SHIP-901 đang active.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class QuoteWireVerifierTest {

    private final QuoteWorkflowRegistry registry =
            new QuoteWorkflowRegistry() {
        @Override
        public boolean isActiveOrRecoverable(
                String tenantId, String shipmentId, int epoch) {
            return "tenant-a".equals(tenantId)
                    && "SHIP-901".equals(shipmentId)
                    && epoch == 7;
        }

        @Override
        public boolean mayReport(
                String peerId, String providerId) {
            return "peer-partner-a".equals(peerId)
                    && "PARTNER-A".equals(providerId);
        }
    };

    private final QuoteWireVerifier verifier =
            new QuoteWireVerifier(registry);

    private QuoteResultWire sample(String key) {
        return new QuoteResultWire(
                1, key, "evt-a-001", "PARTNER-A",
                "SHIP-901", 7, "QUOTED", "150000");
    }

    @Test
    void verifiedCallbackKeepsBusinessKey() {
        QuoteCommand identity =
                new QuoteCommand("SHIP-901", 7, 1);
        String expected =
                QuoteCorrelation.key("tenant-a", identity);

        VerifiedQuoteResult verified = verifier.verify(
                sample(expected),
                new VerifiedTransportPeer(
                        "peer-partner-a", "tenant-a"));

        assertEquals(expected,
                verified.businessCorrelationKey());
        assertEquals("tenant-a", verified.tenantId());
        assertEquals("PARTNER-A", verified.providerId());
        assertEquals(new BigDecimal("150000"),
                verified.totalVnd());
    }

    @Test
    void forgedBusinessKeyIsNotTrusted() {
        QuoteResultWire forged = sample(
                "shipment-quote:v1:tenant-admin:SHIP-901:7");

        assertThrows(SecurityException.class,
                () -> verifier.verify(
                        forged,
                        new VerifiedTransportPeer(
                                "peer-partner-a", "tenant-a")));
    }

    @Test
    void unauthorizedProviderIsRejected() {
        String valid = QuoteCorrelation.key(
                "tenant-a", new QuoteCommand("SHIP-901", 7, 1));

        assertThrows(SecurityException.class,
                () -> verifier.verify(
                        sample(valid),
                        new VerifiedTransportPeer(
                                "unknown-peer", "tenant-a")));
    }

    @Test
    void invalidAmountIsRejectedBeforeAggregation() {
        String key = QuoteCorrelation.key(
                "tenant-a", new QuoteCommand("SHIP-901", 7, 1));
        QuoteResultWire bad = new QuoteResultWire(
                1, key, "evt-a-002", "PARTNER-A",
                "SHIP-901", 7, "QUOTED", "-10");

        assertThrows(IllegalArgumentException.class,
                () -> verifier.verify(
                        bad,
                        new VerifiedTransportPeer(
                                "peer-partner-a", "tenant-a")));
    }
}
~~~

**Kết luận của test:** cùng một wire event không có quyền chọn tùy ý correlation group nội bộ; peer và workflow registry quyết định tenant/epoch hợp lệ. Test không chứng minh mTLS/OAuth của adapter đã được cấu hình; VerifiedTransportPeer phải được tạo từ lớp xác thực thật.

### 21.1. Kiểm tra header sau khi dựng Message

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;

class QuoteMessageMapperTest {
    @Test
    void internalMessageHasTrustedCorrelationHeaders() {
        VerifiedQuoteResult result = new VerifiedQuoteResult(
                "shipment-quote:v1:tenant-a:SHIP-901:7",
                "evt-a-001", "PARTNER-A",
                "SHIP-901", 7, "tenant-a",
                "QUOTED", new java.math.BigDecimal("150000"));

        var message = QuoteMessageMapper.internal(result);
        assertEquals(result,
                message.getPayload());
        assertEquals(
                result.businessCorrelationKey(),
                message.getHeaders()
                        .get("businessCorrelationKey"));
        assertEquals(
                result.businessCorrelationKey(),
                message.getHeaders().get(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID));
        assertNull(message.getHeaders().get("errorChannel"));
    }
}
~~~

Một Spring Message mới **không có replyChannel của client** là mong muốn trong ví dụ callback async; inbound event không cần trả một Java Gateway reply qua temporary channel đã hết lifetime.

## 22. Integration test: ba adapter đưa replies về cùng business group

Trong test thuần Spring context, ta mô phỏng rằng HTTP, JMS và AMQP đã được xử lý/validate và gửi vào cùng verifiedQuoteCallbacks. Mục tiêu ở đây là chứng minh **content-based group correlation** không phụ thuộc vào arrival order hay nguồn adapter ban đầu.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(QuoteCallbackFlowConfig.class)
class QuoteCallbackFlowTest {

    @Autowired
    @Qualifier("verifiedQuoteCallbacks")
    MessageChannel input;

    @Autowired
    @Qualifier("quoteAggregationOutput")
    QueueChannel reports;

    @BeforeEach
    void clearReports() {
        while (reports.receive(0) != null) {
            // Dọn output queue nếu test context được tái sử dụng.
        }
    }

    private VerifiedQuoteResult result(
            String tenantId,
            String shipmentId,
            int epoch,
            String eventId,
            String providerId,
            String status,
            String totalVnd) {

        QuoteCommand identity =
                new QuoteCommand(shipmentId, epoch, 1);
        String key = QuoteCorrelation.key(tenantId, identity);

        return new VerifiedQuoteResult(
                key,
                eventId,
                providerId,
                shipmentId,
                epoch,
                tenantId,
                status,
                totalVnd == null ? null : new BigDecimal(totalVnd));
    }

    private void send(VerifiedQuoteResult verified) {
        assertTrue(input.send(
                QuoteMessageMapper.internal(verified)));
    }

    @Test
    void repliesFromThreeAdaptersJoinSameGroup() {
        // Arrival order: AMQP, HTTP, JMS.
        send(result("tenant-a", "SHIP-901", 7,
                "evt-backup-901", "BACKUP", "QUOTED", "190000"));
        send(result("tenant-a", "SHIP-901", 7,
                "evt-a-901", "PARTNER-A", "QUOTED", "150000"));

        assertNull(reports.receive(0));

        send(result("tenant-a", "SHIP-901", 7,
                "evt-b-901", "PARTNER-B", "QUOTED", "160000"));

        Message<?> reply = reports.receive(0);
        assertNotNull(reply);
        QuoteAggregationReport report =
                (QuoteAggregationReport) reply.getPayload();

        assertEquals(3, report.receivedCount());
        assertEquals("COMPLETE", report.status());
        assertEquals(
                "shipment-quote:v1:tenant-a:SHIP-901:7",
                report.businessCorrelationKey());
        assertEquals("PARTNER-A",
                report.bestQuote().providerId());
        assertEquals(new BigDecimal("150000"),
                report.bestQuote().totalVnd());
        assertNull(reports.receive(0));
    }

    @Test
    void tenantAndWorkflowEpochStayIsolated() {
        send(result("tenant-a", "SHIP-902", 1,
                "a1", "PARTNER-A", "QUOTED", "100000"));
        send(result("tenant-a", "SHIP-902", 1,
                "a2", "PARTNER-B", "QUOTED", "120000"));

        // Hai message khác scope, không lấp member còn thiếu.
        send(result("tenant-b", "SHIP-902", 1,
                "b1", "BACKUP", "QUOTED", "90000"));
        send(result("tenant-a", "SHIP-902", 2,
                "a3", "BACKUP", "QUOTED", "85000"));
        assertNull(reports.receive(0));

        send(result("tenant-a", "SHIP-902", 1,
                "a4", "BACKUP", "QUOTED", "110000"));

        QuoteAggregationReport report =
                (QuoteAggregationReport)
                        reports.receive(0).getPayload();

        assertEquals(
                "shipment-quote:v1:tenant-a:SHIP-902:1",
                report.businessCorrelationKey());
        assertEquals(3, report.outcomes().size());
        assertNull(reports.receive(0));
    }

    @Test
    void unavailableIsATerminalOutcomeNotAMissingReply() {
        send(result("tenant-a", "SHIP-903", 1,
                "a903", "PARTNER-A", "QUOTED", "150000"));
        send(result("tenant-a", "SHIP-903", 1,
                "b903", "PARTNER-B", "UNAVAILABLE", null));
        send(result("tenant-a", "SHIP-903", 1,
                "c903", "BACKUP", "QUOTED", "180000"));

        QuoteAggregationReport report =
                (QuoteAggregationReport)
                        reports.receive(0).getPayload();

        assertEquals(3, report.receivedCount());
        assertEquals("PARTIAL_SUPPLIER_FAILURE", report.status());
        assertEquals("PARTNER-A",
                report.bestQuote().providerId());
    }
}
~~~

### 22.1. Giới hạn của bộ integration tests này

Các test trên **không thực sự khởi động HTTP server, Kafka/JMS/AMQP broker hoặc TCP connection**. Chúng kiểm chứng điểm hội tụ **sau khi adapter đã xác minh data và dựng Spring Message nội bộ**.

Vì thế chưa thể kết luận:

- Header mapping qua HTTP/JMS/AMQP thực tế không mất businessCorrelationKey.
- JMSCorrelationID/JMSReplyTo hoặc AMQP replyTo được echo chính xác.
- TCP serializer giữ correlation fields.
- Broker redelivery không gây duplicate.
- Multi-instance MessageGroupStore chịu concurrent updates.

Những điều đó cần các **contract/integration tests ở transport boundary**.

### 22.2. Test transport contract bằng broker hoặc mock HTTP server

Thiết kế một bộ test adapter riêng:

| Adapter | Tác động test | Assertion |
| --- | --- | --- |
| HTTP outbound gateway | Stub server echo request metadata | Correct payload/header mapping + returned reply |
| HTTP inbound callback | Gửi callback có forged key | Bị chặn trước verifiedQuoteCallbacks |
| JMS outbound gateway | Remote responder trả đúng JMSCorrelationID | Gateway nhận đúng reply của request |
| JMS outbound gateway | Responder trả sai JMSCorrelationID | Không gán nhầm reply cho caller khác |
| AMQP gateway | Hai RPC requests chạy đồng thời | Replies đúng invocation |
| AMQP adapters | Consumer redelivery eventId cũ | Dedup ledger bảo vệ outcome/effect |
| TCP gateway | Reply cùng connection theo protocol | Đúng connection/request |
| TCP collaborating adapters | Hai requests trên connection khác nhau | Application key vẫn ghép đúng |

Có thể dùng **WireMock/MockWebServer** cho HTTP hoặc Testcontainers/broker test fixture cho JMS/AMQP, tùy dự án. Đặt timeout bounded, tránh tests có thể treo vô hạn khi một reply không đến.

### 22.3. Test khi callback thực sự đến muộn

Với cùng businessCorrelationKey:

1. Send PARTNER-A và PARTNER-B, xác minh chưa có full report.
2. Kết thúc Gateway attempt đồng bộ bằng timeout giả lập.
3. Sau đó gửi BACKUP callback hợp lệ trong business deadline.
4. Xác minh workflow state có thể nhận kết quả muộn theo policy.
5. Nếu business deadline đã qua, xác minh late callback bị audit/quarantine hoặc tạo revision, không mặc định thay đổi report cũ.

Không chỉ nhìn QueueChannel output: cần kiểm tra **workflow store** khi mô phỏng mất reply qua adapter.

## 23. Nếu chỉ có Adapter callback, có cần Gateway không?

**Không nhất thiết.** Một hệ thống nhận HTTP/JMS callbacks từ ba providers có thể dùng trực tiếp inbound adapters, verified mapper và Aggregator, không cần một Java Messaging Gateway đang chờ mỗi reply.

~~~text
Inbound Adapter 1 ----+
Inbound Adapter 2 ----+--> Verify -> Correlate -> Aggregate -> Persist result
Inbound Adapter 3 ----+
~~~

Gateway hữu ích khi một module Java muốn gọi flow theo kiểu phương thức, hoặc khi protocol thực sự có request/reply. Nhưng nếu process kéo dài nhiều phút và cần sống qua restart, một Gateway call có temporary replyChannel **không phải kho lưu trạng thái workflow**.

### 23.1. Mô hình kết hợp

Có thể dùng cả hai:

1. HTTP inbound gateway nhận lệnh khởi tạo.
2. Application service tạo workflow bền và phát tasks qua outbound adapters.
3. HTTP gateway trả ngay **AcceptedResponse** gồm trackingId.
4. Inbound adapters nhận callbacks bất đồng bộ và dùng business correlation để ghép.
5. Khi đủ outcomes, Aggregator cập nhật trạng thái và phát event hoàn thành.
6. Client gọi API trạng thái hoặc nhận notification theo authorization.

**Đây là request/reply để chấp nhận công việc, không phải request/reply để chờ toàn bộ workflow hoàn tất.** Tách hai hợp đồng giúp tránh giữ HTTP threads hàng phút.

### 23.2. Correlation key có thể không nằm sẵn trong callback

Một provider chỉ trả providerTicketId thay vì businessCorrelationKey:

~~~json
{
  "providerTicketId": "ticket-553",
  "status": "QUOTED",
  "priceVnd": "150000"
}
~~~

Trong trường hợp này, lưu mapping bền **providerTicketId → trustedTenantId + businessCorrelationKey + providerId + operationId** khi gửi request. Lúc callback tới, tra mapping và xác minh callback source; không tạo một workflow mới từ ticketId tùy ý.

Nếu mapping mất sau restart, phải có cơ chế recovery/đối soát. Không điền một correlationId ngẫu nhiên chỉ để message có thể vào Aggregator.

## 24. Observability: theo dõi cả ba lớp correlation

Một hệ thống không có metric correlation thường chỉ nhìn thấy “Gateway timeout”, nhưng không biết lỗi do adapter header mapper, provider, hay Aggregator group. Log nên phân biệt:

1. **Business workflow identity**: group key/tracking ID.
2. **Transport attempt**: JMSCorrelationID, AMQP request correlation, HTTP request ID hoặc TCP connection ID.
3. **Logical event identity**: eventId, providerId, operationId.

### 24.1. Mẫu log tại outbound

~~~json
{
  "stage": "quote-outbound",
  "businessCorrelationRef": "opaque-quote-901",
  "providerId": "PARTNER-A",
  "operationId": "quote:SHIP-901:7:PARTNER-A",
  "transport": "JMS",
  "transportAttempt": 2,
  "status": "SENT"
}
~~~

### 24.2. Mẫu log tại inbound adapter

~~~json
{
  "stage": "quote-inbound-verified",
  "businessCorrelationRef": "opaque-quote-901",
  "providerId": "PARTNER-A",
  "eventId": "evt-provider-778",
  "transport": "HTTP_CALLBACK",
  "verified": true,
  "dedupStatus": "FIRST_ARRIVAL",
  "workflowState": "IN_PROGRESS"
}
~~~

**Đây là log mẫu**, không phải output tự động của Spring Integration. Không ghi credential, Authorization headers, raw payload nhạy cảm hoặc live replyChannel object. Dùng opaque/redacted reference ở hệ thống log nếu business key chứa tenant/shipmentId nhạy cảm.

### 24.3. Metrics nên có

| Metric | Đo điều gì? |
| --- | --- |
| **gateway_invocations_total{method,status}** | Số Java Gateway calls và kết quả |
| **gateway_reply_timeout_total{method}** | Số lời gọi hết hạn chờ reply |
| **transport_requests_total{protocol,provider}** | Số outbound attempts |
| **transport_reply_mismatch_total{protocol}** | Response không khớp transport request |
| **adapter_header_mapping_failure_total{protocol}** | Mapping thiếu/sai header |
| **business_correlation_verification_failed_total{reason}** | Inbound wire key không khớp verified binding |
| **callback_duplicate_total{provider}** | Event callback bị dedup |
| **callback_identity_conflict_total{provider}** | Cùng event ID nhưng payload/group khác |
| **callback_recovery_total{outcome}** | Retry/reconciliation/quarantine |
| **aggregation_group_pending** | Số business groups chưa hoàn tất |
| **aggregation_group_age_seconds** | Tuổi nhóm còn chờ |
| **aggregation_complete_total{status}** | Kết quả COMPLETE/NO_OFFER/PARTIAL |
| **aggregation_incomplete_total** | Business deadline đã qua mà thiếu provider |
| **aggregation_late_event_total{reason}** | Reply tới sau khi group đóng |

Không dùng businessCorrelationKey, tenantId, shipmentId, eventId hoặc transport correlation token tùy ý làm label metric nếu cardinality lớn. Dùng trace/log có thời hạn lưu và quyền truy cập phù hợp.

### 24.4. Một metric reply timeout chưa đủ

Hai hệ thống có cùng tỷ lệ Gateway timeout nhưng nguyên nhân khác:

- **A:** adapter không serialize business key, nên business Aggregator chờ thiếu member.
- **B:** transport reply correlation khớp nhưng remote service thật sự chậm.

Để xác định, xem các metric verified callback accepted, pending groups, transport mismatches, supplier latency và message store. Không sửa một vấn đề identity bằng cách chỉ tăng timeout.

## 25. Runbook: response đến broker nhưng không về đúng workflow

### Bước 1 — Xác định contract cần hoàn thành

Đang chờ **một reply của Java Gateway** hay đang chờ **ba terminal events của business Aggregator**? Hai hợp đồng khác nhau và có thể kết thúc ở các thời điểm khác.

### Bước 2 — Tìm business group từ input đáng tin

Kiểm tra verified tenant, shipmentId, workflowEpoch và key algorithm version. Nếu business key ở outbound và inbound khác nhau, xem lại canonicalization, workflow registry và header/body mapping.

### Bước 3 — Kiểm tra transport correlation

| Transport | Kiểm tra |
| --- | --- |
| HTTP | Response cùng request hay callback mới? HeaderMapper/body schema đúng không? |
| JMS | JMSReplyTo, JMSMessageID/JMSCorrelationID hoặc custom correlation property |
| AMQP | replyTo, correlationId và RPC gateway settings |
| TCP | ip_connectionId, serializer/deserializer và gateway/adapter pairing |
| File | Manifest/batch identity, file name/ID không bị đổi khi retry |

Nếu lỗi tại protocol correlation, application aggregator có thể chưa từng nhận message. Nếu protocol giao thành công nhưng business group sai, sửa mapper/registry thay vì sửa JMSCorrelationID một cách mù quáng.

### Bước 4 — Xác thực và kiểm tra inbound envelope

Kiểm tra peer được phép gửi event cho providerId và tenant không. So sánh wire businessCorrelationKey với giá trị tính từ authoritative registry. Nếu mismatch, quarantine/alert và không gửi vào Aggregator.

### Bước 5 — Kiểm tra inbox và redelivery

Truy eventId/providerId trong inbox:

- Chưa từng thấy: tìm lỗi delivery/routing/network.
- Có RECEIVED nhưng chưa DISPATCHED: cần recovery/outbox.
- Có DISPATCHED nhưng Aggregator không thấy: kiểm tra ack/store/transaction.
- Có COMPLETED: reply có thể là duplicate, không tạo effect lần hai.
- Payload digest khác với cùng identity: ID_CONFLICT.

### Bước 6 — Xem Aggregator group

Group đúng key đã nhận bao nhiêu **unique providers**, không chỉ bao nhiêu Message objects? Có đủ expected set chưa? ReleaseStrategy có chờ sequenceSize không phù hợp với các callback độc lập không? Group đã expired hoặc completed chưa?

### Bước 7 — Kiểm tra late/timeout policy

Gateway có thể timeout trước khi callback đến, nhưng business workflow vẫn đang active. Đối chiếu deadline và late-event policy trước khi replay. Không gửi reply muộn tới một temporary replyChannel đã đóng.

### Bước 8 — Quyết định xử lý có kiểm soát

- Retry đúng **logical operation**, giữ business key/event identity.
- Reconcile khi remote effect UNKNOWN.
- Quarantine schema/authorization mismatch.
- Phát revision của report nếu business cho phép cập nhật sau deadline.
- Không tự tạo một correlation key mới chỉ để khỏi gặp group cũ.

### Bước 9 — Xác minh sau khắc phục

Mỗi request/reply được giao đúng caller còn hiệu lực; mỗi business group có đúng các terminal outcomes được phép; không có duplicate side effect; số nhóm pending trở về mức bình thường.

## 26. Những sai lầm thiết kế thường gặp

| Sai lầm | Hậu quả | Điều chỉnh |
| --- | --- | --- |
| Dùng MessageHeaders.ID làm business correlation | Mỗi hop/rebuild có thể đổi ID | Derive/lookup stable group key |
| Copy client X-Correlation-ID vào Aggregator | False join hoặc dữ liệu vượt tenant | Verify tenant+binding, create internal key |
| Sinh UUID mới tại mỗi inbound adapter | Callback cùng workflow vào nhiều groups | Một mapping bền hoặc deterministic key |
| Gộp JMSCorrelationID với orderId | Reply nhiều attempts có thể khớp sai | Để JMS Gateway quản lý protocol token |
| Cho callback trở lại temporary Gateway channel | Channel đã hết lifetime | Workflow store + async result |
| Serialize toàn MessageHeaders qua TCP | Live objects không portable | Wire DTO / selected header mapper |
| Dùng ip_connectionId làm group key | Gộp nhiều requests cùng connection | Business payload/operation key |
| Bỏ business ID khi chuyển HTTP → AMQP | Không thể ghép callbacks | Explicit body/header mapping |
| Tin providerId từ callback chưa xác minh | Supplier giả mạo member khác | Peer identity + allowlist |
| Dùng group.size()==3 | Duplicate che mất supplier thiếu | Unique provider release + inbox dedup |
| Filter bỏ supplier UNAVAILABLE | Group chờ vô hạn | Terminal failure outcome nếu phù hợp |
| Coi ErrorMessage như supplier result | Throwable không phải domain outcome | Recovery/compensation có kiểu |
| Timeout Gateway = workflow FAILED | Mất callback hợp lệ đến sau | Tách transport timeout và business deadline |
| Retry toàn workflow khi một provider lỗi | Có thể lặp side effect ở nguồn khác | Per-provider retry + idempotency |
| Chỉ lưu dedup trước dispatch | Crash gây mất event | Transaction/outbox/recovery |
| Xóa completed group ngay | Late reply có thể tạo group mới | Retention và persistent ledger |
| Dùng cùng batchId cho mọi subgroup | Trộn outputs của các items | Key gồm itemId + epoch |
| Không giới hạn active groups | Quá tải MessageGroupStore | Quota, timeout, cleanup, monitoring |

## 27. Bài thực hành: kết hợp HTTP Gateway, JMS Adapter và TCP callback

Thiết kế một workflow quản lý việc cấp phép xuất hàng:

~~~text
HTTP inbound gateway /api/shipments/{id}/dispatch-check
     -> verified ingress / business group
     -> publish 3 checks:
          WAREHOUSE  qua JMS
          COMPLIANCE qua HTTP
          TRANSPORT  qua TCP
     -> mỗi nguồn trả event độc lập
     -> inbound adapters
     -> verify + correlation
     -> Aggregator
     -> DispatchDecision
~~~

### 27.1. Contract của bài thực hành

Định danh:

~~~java
record DispatchCheckRequest(
        String shipmentId,
        int workflowEpoch,
        String requestedBy) {}

record DispatchPartResult(
        String eventId,
        String businessCorrelationKey,
        String sourceId,
        String status,
        String errorCode) {}

record DispatchDecision(
        String businessCorrelationKey,
        String decision,
        java.util.List<DispatchPartResult> evidence) {}
~~~

Quy tắc:

- Mỗi source cần trả đúng một **terminal outcome**: ALLOWED, DENIED hoặc UNAVAILABLE theo hợp đồng.
- Workflow chỉ quyết định READY khi cả WAREHOUSE, COMPLIANCE, TRANSPORT đều ALLOWED.
- Nếu source DENIED, có thể tạo decision REJECTED khi đã đủ các terminal outcomes cần thiết.
- Nếu nguồn chưa gửi event, không tự coi là DENIED; giữ IN_PROGRESS hoặc INCOMPLETE khi quá deadline.
- Tenant từ verified principal; shipment và epoch phải được kiểm tra với workflow registry.
- eventId giữ nguyên qua redelivery, transport request token có thể khác giữa attempts.

### 27.2. Các bước triển khai

1. Viết ingress service xác minh tenant/shipments và tạo businessCorrelationKey versioned.
2. Dựng một Messaging Gateway cho lời gọi Java nhận accepted/receipt ngắn hạn.
3. Tạo ba outbound adapters/gateways theo đúng contract một chiều hay request/reply.
4. Thiết kế wire envelope chung gồm schemaVersion, eventId, sourceId, business key và trạng thái.
5. Cấu hình HeaderMapper/converter từng transport, không copy live replyChannel/errorChannel qua network.
6. Xây dựng mapper inbound xác thực producer và tra binding trong registry.
7. Viết dedup inbox bảo vệ eventId và phát hiện ID_CONFLICT.
8. Dựng Aggregator có CorrelationStrategy theo business key và ReleaseStrategy theo ba source IDs.
9. Bổ sung group timeout, business deadline và chính sách report INCOMPLETE.
10. Xác định reply correlation của JMS Gateway và TCP ip_connectionId ở đúng scope.
11. Gửi hai yêu cầu khác tenant cùng shipmentId; xác minh không trộn.
12. Cho HTTP source trả callback muộn sau khi Gateway attempt timeout; kiểm tra state/revision policy.
13. Cho JMS event redeliver, kiểm tra không tạo hai terminal outcomes/side effects.
14. Mô phỏng crash giữa inbox insert và dispatch, chứng minh recovery/outbox.
15. Thêm metrics, trace logs và runbook cho missing replies.

### 27.3. Ma trận kiểm thử

| Case | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| A | Cả ba sources ALLOWED | Một DispatchDecision READY |
| B | COMPLIANCE DENIED, hai nguồn ALLOWED | Decision đúng policy, không thiếu member |
| C | TRANSPORT không reply | IN_PROGRESS → INCOMPLETE khi deadline |
| D | WAREHOUSE event duplicate | Không đếm là nguồn thứ tư |
| E | Tenant A và B dùng cùng shipmentId | Hai groups độc lập |
| F | Cùng shipment nhưng epoch 3, 4 | Hai workflows độc lập |
| G | X-Correlation-ID do client giả mạo | Bị bỏ qua/chặn ở ingress |
| H | JMSCorrelationID sai | Không chuyển reply sang caller khác |
| I | TCP ip_connectionId sai | Không route nhầm connection |
| J | HTTP callback sau reply timeout | Business state vẫn xử lý đúng policy |
| K | Payload schemaVersion không hỗ trợ | Reject/quarantine, không tạo random key |
| L | Restart trước khi Aggregator release | Durable store/recovery giữ tiến độ |
| M | Redelivery sau khi group metadata đã xóa | Persistent ledger không tạo effect trùng |

### 27.4. Câu hỏi tự kiểm tra

1. Tại sao Gateway replyChannel không đồng nghĩa business correlation key?
2. Khi nào Spring Integration Gateway dùng temporary anonymous reply channel?
3. Correlation cần gửi qua adapter có bắt buộc là CORRELATION_ID Spring header không?
4. Khi nào nên dùng wire envelope thay vì copy toàn MessageHeaders?
5. HTTP 202 Accepted có nói business workflow đã hoàn tất không?
6. JMSCorrelationID được dùng để nối những thành phần nào?
7. AMQP replyTo khác business callback destination ra sao?
8. TCP ip_connectionId có thể đại diện cho nhiều business requests không?
9. Vì sao một client-supplied correlation ID cần được xác minh?
10. Một workflow đã retry có cần business key mới không?
11. Nếu một callback không mang business key nhưng có providerTicketId, xử lý thế nào?
12. Vì sao ba callbacks từ cùng provider không đủ cho group ba providers?
13. Lỗi mapper khác Gateway timeout như thế nào?
14. Một ErrorMessage trên errorChannel có tự tạo thành viên Aggregator không?
15. Tại sao cần ledger idempotency ngay cả khi correlation ID ổn định?
16. Khi nào cần thay Gateway sync bằng workflow async?
17. Nếu Splitter phát ba items, correlation key của provider replies phải gồm những thành phần nào?
18. Khi một callback đến sau business deadline, có thể tự sửa report đã công bố không?

## 28. Checklist trước khi triển khai correlation qua gateway và adapter

- Đã phân biệt **business key**, **Gateway reply channel**, **protocol correlation** và **event ID** trong tài liệu kiến trúc.
- Ingress xác thực tenant, producer, business object và workflow epoch trước khi gắn key.
- Mọi adapter dùng chung key schema/version và quy tắc canonicalization.
- Cùng logical workflow và redelivery tạo cùng businessCorrelationKey; workflow khác tenant/epoch tạo key khác.
- Messaging Gateway có reply timeout hữu hạn và contract rõ khi không có reply.
- Không chuyển temporary replyChannel/errorChannel Java object thành wire payload.
- HTTP HeaderMapper đã được kiểm tra với các custom header cần thiết, không chỉ standard headers.
- HTTP 202 Accepted được phân biệt với final business completion.
- JMS request/reply tuân thủ JMSCorrelationID/JMSReplyTo và cấu hình correlation-key thực tế.
- AMQP request/reply dùng replyTo/correlation của giao thức đúng contract.
- TCP connection routing giữ ip_connectionId ở nơi cần trả reply; không dùng nó làm business key.
- TCP serializer/deserializer và framing biết chính xác những headers/fields nào qua wire.
- Callback không có correlation key có mapping bền từ provider ticket/operation ID.
- Wire envelope có schemaVersion, eventId, providerId, workflow identity và status có kiểu.
- Không tin arbitrary headers/correlation key được gửi từ vùng chưa xác thực.
- Inbound mapping tính lại/lookup key, xác minh tenant và nguồn event, phát hiện mismatch.
- Đã tách group key của Aggregator theo workflow cha với technical correlation của Splitter/Scatter-Gather con.
- ReleaseStrategy kiểm tra đúng tập member IDs; không chỉ đếm Message objects.
- Event duplicate được nhận diện bởi inbox/ledger trước khi đếm đủ group.
- Có transaction/outbox/recovery chống crash giữa dedup và dispatch.
- Các side effects dùng provider idempotency key hoặc reconciliation độc lập với group metadata.
- Timeout của Gateway, transport, Aggregator và business deadline được định nghĩa riêng.
- Late reply policy được công bố: discard/audit, freeze, revision hoặc reconcile.
- MessageGroupStore/LockRegistry phù hợp với restart và multi-instance nếu phải lưu trạng thái bền.
- Error channel/DLQ/quarantine có consumer, retry và retention đúng hợp đồng.
- Không đưa raw business keys, transport tokens hoặc high-cardinality IDs vào metric labels.
- Có ít nhất test Gateway local, wire verifier, Aggregator grouping, cross-tenant, cross-epoch, callback duplicate, protocol mismatch, timeout và restart.
- Đã kiểm tra khả năng hết queue, socket, broker và connection pools khi nhiều requests đồng thời.
- Đã có runbook phân biệt lỗi **protocol reply matching** với lỗi **business group correlation**.

## 29. Tổng kết mô hình ba lớp

Một kiến trúc Content-based correlation qua Gateway và Adapter đáng tin có thể được đọc từ ngoài vào trong:

~~~mermaid
flowchart TB
    A["Trusted ingress<br/>tenant + shipment + epoch"] --> B["Business correlation key<br/>ổn định qua retry"]
    B --> C["Gateway / outbound adapter"]
    C --> D["Protocol correlation<br/>JMS / AMQP / TCP / HTTP"]
    D --> E["Remote provider"]
    E --> F["Inbound adapter / callback"]
    F --> G["Verify producer + envelope + eventId"]
    G --> H["Rebuild internal Message<br/>business key"]
    H --> I["Dedup / Aggregator / workflow state"]
    I --> J["Business result / idempotent effect"]
~~~

**Lớp 1 — Nghiệp vụ:** correlation key cho biết ba message có thuộc cùng tenant, shipment và workflow epoch không. Nó phải ổn định khi sự kiện đi qua nhiều transport và bị redeliver.

**Lớp 2 — Giao tiếp:** Gateway và adapter dùng replyChannel, JMSCorrelationID/JMSReplyTo, AMQP replyTo/correlation hoặc TCP ip_connectionId để trả một **transport reply** đúng nơi. Những trường này thường có lifetime ngắn hơn business workflow và có thể đổi giữa attempts.

**Lớp 3 — Tin cậy và phục hồi:** một callback chỉ được tham gia group sau khi xác minh nguồn, nội dung, event ID và workflow binding. Inbox/outbox, MessageGroupStore, timeout, duplicate suppression và idempotency làm cho luồng **không bị mất hoặc lặp business effect** khi broker/network gặp sự cố.

**Kết luận:** Correlation qua Gateway và Adapter không phải là copy một header tên correlationId qua mọi nơi. Cần giữ **identity nghiệp vụ đáng tin xuyên các ranh giới**, đồng thời để **Gateway/protocol quản lý request/reply correlation** của chính nó. Khi có callback bất đồng bộ, business workflow không được phụ thuộc vào temporary replyChannel đã hết lifetime. Xác định đúng ba lớp, kiểm thử mapping từng transport và đặt retry/idempotency tại đúng điểm giúp Spring Integration phối hợp Router, Transformer, Splitter, Aggregator, Gateway và error channel một cách đáng tin cậy.

## Tài liệu tham khảo

- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): temporary replyChannel, cấu hình gateway, reply timeout và các quy tắc request/reply.
- [Spring Integration Reference — HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html): HTTP headers, HeaderMapper, custom mapping và inbound/outbound directions.
- [Spring Integration Reference — HTTP Support](https://docs.spring.io/spring-integration/reference/http.html): HTTP inbound/outbound gateways và channel adapters.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): JMS inbound/outbound gateways, JMSCorrelationID, JMSReplyTo và correlation-key.
- [Spring AMQP — Spring Integration Reference](https://docs.spring.io/spring-amqp/reference/integration-reference.html): inbound/outbound adapters và request/reply gateways với AMQP.
- [Spring Integration Reference — TCP Message Correlation](https://docs.spring.io/spring-integration/reference/ip/correlation.html): gateways, collaborating adapters, ip_connectionId và chuyển selected headers qua TCP.
- [Spring Integration Reference — TCP Gateways](https://docs.spring.io/spring-integration/reference/ip/tcp-gateways.html): request/reply theo connection và các lưu ý của inbound/outbound gateways.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): CorrelationStrategy, ReleaseStrategy, MessageGroupStore, group timeout và late arrivals.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): sequencing headers và các group lồng nhau.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel và sự khác biệt giữa lỗi đồng bộ/bất đồng bộ.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, QueueChannel và semantics dispatch.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): công cụ hỗ trợ dedup và giới hạn của idempotency advice.
- [Enterprise Integration Patterns — Correlation Identifier](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html): pattern liên kết một reply với đúng request và phân biệt các messages tương ứng.
- [Enterprise Integration Patterns — Messaging Gateway](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html): cách che chi tiết messaging khỏi ứng dụng gọi.
