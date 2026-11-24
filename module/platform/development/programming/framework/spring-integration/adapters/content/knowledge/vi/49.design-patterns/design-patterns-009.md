# Router theo protocol hoặc header trong Spring Integration Adapters

> **Chương:** Design patterns  
> **Bài học:** Router theo protocol hoặc header  
> **Ngữ cảnh module:** SPRING_INTEGRATION_ADAPTERS — kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và MessageChannel; tích hợp qua File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; quản lý hợp đồng message, lỗi và vòng đời kết nối.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **Message Router** là mẫu Enterprise Integration Patterns chọn nhánh xử lý dựa trên quy tắc, không phải một adapter tự chuyển giao thức.
2. Phân biệt **router theo protocol** (HTTP, SFTP, JMS, AMQP, Kafka, File, JDBC) và **router theo header** (routeKey, tenant, eventType, destinationAlias).
3. Sử dụng **HeaderValueRouter**, router bằng method/@Router và Java DSL ở một IntegrationFlow phù hợp.
4. Thiết kế **hợp đồng message đã chuẩn hóa** để không phụ thuộc header đặc thù của từng inbound adapter.
5. Kiểm soát channel mapping, default route, lỗi missing/unknown route và đường từ chối có thể kiểm toán.
6. Ngăn **header spoofing, SSRF, truy cập đích không được phép, route sai tenant** và truyền secret qua giao thức.
7. Phân biệt request–reply và one-way; hiểu ranh giới channel, ack/offset, transaction, retry, idempotency và ordering.
8. Kết hợp router với transformer, splitter, gateway, adapter, recipient list và các pattern liên quan.
9. Xây dựng tests chứng minh đúng message đến đúng đích và không gây duplicate/mất dữ liệu.

## 2. Bối cảnh: một nguồn, nhiều đích và nhiều giao thức

Một nền tảng nhận sự kiện hóa đơn qua HTTP webhook, SFTP file hoặc Kafka. Tùy đối tác/nghiệp vụ, message phải tới:

- REST API qua **HTTP outbound gateway**;
- SFTP server qua **SFTP outbound adapter**;
- JMS queue qua **JMS outbound adapter/gateway**;
- AMQP exchange/queue qua **AMQP outbound adapter**;
- Kafka topic qua **Kafka outbound adapter**;
- File output directory, hoặc database qua **JDBC handler/adapter**.

~~~text
HTTP inbound ----\
SFTP inbound -----+--> Normalize --> RoutePolicy --> Router --> HTTP branch
Kafka inbound ----/                                  |-----> SFTP branch
                                                    |-----> JMS/AMQP branch
                                                    |-----> Kafka branch
                                                    |-----> File/JDBC branch
                                                    \-----> Rejected route
~~~

Nếu mỗi inbound flow dùng if/else để chọn adapter riêng, logic phân tán, khó bảo mật và khó đo lường. **Router** tách câu hỏi “đi đâu?” khỏi “gửi như thế nào?”.

**Router làm:** đọc route key/đánh giá quy tắc, chọn channel/recipient phù hợp và đưa message đến nhánh đã cấu hình.

**Router không tự làm:** chuyển JSON thành CSV, xác thực request, mở SFTP session, tạo JMS message, quản lý Kafka offset, bảo đảm exactly-once hoặc cung cấp distributed transaction.

## 3. Các thành phần trong Spring Integration

| Thành phần | Chức năng | Cẩn trọng |
|---|---|---|
| **Message** | Payload và headers | Header đến từ bên ngoài có thể không đáng tin |
| **MessageChannel** | Kết nối endpoint/handler | Đồng bộ, async, queue có semantics khác nhau |
| **MessageSource / poller** | Lấy File/SFTP/JDBC message theo lịch | Poll lại không bảo đảm cùng message |
| **Inbound adapter/gateway** | Nhận từ hệ thống ngoài | Ack/reply theo contract nguồn |
| **Transformer/enricher** | Chuẩn hóa payload và headers | Tách raw headers khỏi trusted route headers |
| **Router** | Chọn một hoặc nhiều channel theo loại router | Không bỏ message unknown vô điều kiện |
| **Service activator** | Thực thi code nghiệp vụ | Side effects/idempotency |
| **Outbound adapter** | Gửi one-way ra ngoài | Không tự cung cấp reply |
| **Outbound gateway** | Gửi request và nhận response | Reply timeout, error mapping |
| **ErrorMessage/errorChannel** | Truyền thông tin lỗi | Không mặc định là kho lưu bền |
| **DLQ/parking** | Giữ failure để replay/triage | Event ID, owner, retention |
| **MessageStore** | Lưu message/trạng thái khi cấu hình | Không tự transaction qua hệ thống khác |

**Message Router** là một mẫu EIP; không nên nhầm với **Filter** (message có được đi tiếp?), **Transformer** (message đổi hình thức?), **Gateway** (có response?) hay **Adapter** (kết nối giao thức nào?).

## 4. Router theo protocol là gì?

Protocol routing chọn nhánh theo loại transport/adapter:

~~~text
routeKey=HTTP  -> httpOutboundChannel   -> HTTP gateway
routeKey=SFTP  -> sftpOutboundChannel   -> SFTP adapter
routeKey=JMS   -> jmsOutboundChannel    -> JMS adapter
routeKey=AMQP  -> amqpOutboundChannel   -> AMQP adapter
routeKey=KAFKA -> kafkaOutboundChannel  -> Kafka adapter
routeKey=FILE  -> fileOutboundChannel   -> File adapter
routeKey=JDBC  -> jdbcOutboundChannel   -> JDBC handler
~~~

Đây là **lựa chọn nhánh có sẵn**, không phải một bộ chuyển đổi giao thức tự động. Mỗi nhánh cần serializer, cấu hình đích, error handling và transaction/ack semantics riêng.

### Protocol không phải business destination

Một hệ thống có thể gửi HTTP đến ERP-A hoặc ERP-B; hai đối tác dùng cùng SFTP nhưng khác thư mục và schema. Vì vậy cần tách:

| Header | Ví dụ | Ý nghĩa |
|---|---|---|
| **targetProtocol** | HTTP | Loại adapter |
| **destinationAlias** | billing-erp | Đích logic đã đăng ký |
| **eventType** | invoice.created | Loại nghiệp vụ |
| **tenantId** | tenant-17 | Phạm vi truy cập/định tuyến |
| **schemaVersion** | v3 | Phiên bản message contract |
| **routePolicyVersion** | 2026-11-r3 | Phiên bản quy tắc |
| **businessEventId** | tenant-17:invoice-882:v3 | Idempotency/correlation |
| **replyRequired** | true | Cần request–reply hay one-way |

Chỉ thấy HTTP trong header **không đủ** để cho phép gửi một payload đến bất cứ URL nào.

## 5. Router theo header là gì?

Header routing chọn channel bằng metadata của message.

~~~yaml
# Minh họa hợp đồng nội bộ, không phải YAML cấu hình Spring.
payload:
  invoiceId: INV-882
  amount: 120000
headers:
  businessEventId: tenant-17:INV-882:v3
  tenantId: tenant-17
  eventType: invoice.created
  schemaVersion: v3
  destinationAlias: billing-erp
  targetProtocol: HTTP
  routeKey: HTTP
  routePolicyVersion: 2026-11-r3
~~~

Một **HeaderValueRouter** có thể đọc routeKey và chọn channel; các headers khác được dùng bởi policy/adapter handler.

### Không tin raw source headers

HTTP headers, Kafka record headers, JMS properties, AMQP headers, SFTP filenames hoặc giá trị JDBC đều có thể chịu ảnh hưởng bởi người gửi. Một HTTP client khai báo “targetProtocol=JDBC” **không được mặc nhiên có quyền ghi database**.

**Thực hành:** xác thực source, validate payload và business identity, tra destination registry, kiểm quyền, sau đó **tạo routeKey đáng tin trong hệ thống**. Không sao chép raw targetProtocol từ client rồi dùng trực tiếp.

### Một header hay nhiều header?

- **Một routeKey đã chuẩn hóa:** dùng HeaderValueRouter rất phù hợp.
- **Tenant + eventType + destinationAlias + version:** tính approved routeKey bằng **policy resolver** trước router, hoặc dùng method/expression router có validation.
- **Nhiều đích phải nhận cùng event:** cần Recipient List Router/fan-out với trạng thái recipient, không ép vào một routeKey đơn.

## 6. Chuẩn hóa message trước khi định tuyến

~~~mermaid
flowchart TD
    H["HTTP inbound"] --> V["Verify source + auth"]
    S["SFTP/File inbound"] --> V
    M["JMS/AMQP/Kafka inbound"] --> V
    D["JDBC poller"] --> V
    V --> N["Normalize canonical payload + trusted headers"]
    N --> P["Policy: tenant/event/destination authorization"]
    P --> R{"Router theo routeKey"}
    R -->|"HTTP"| A["HTTP transform + gateway"]
    R -->|"SFTP"| B["File render + SFTP adapter"]
    R -->|"JMS/AMQP"| C["Message converter + broker adapter"]
    R -->|"KAFKA"| K["Record serializer + Kafka adapter"]
    R -->|"FILE/JDBC"| F["File/DB handler"]
    R -->|"UNKNOWN / DENIED"| X["Rejected + durable handling"]
~~~

### Hợp đồng header nội bộ

| Header | Nguồn đáng tin | Validation |
|---|---|---|
| businessEventId | Nguồn nghiệp vụ và normalization | Stable, không rỗng, đúng tenant |
| correlationId | Trusted trace context hoặc ingress | Bounded length/format |
| sourceSystem | Adapter identity do ứng dụng đặt | Enum/registry |
| tenantId | Authenticated principal/tenant registry | Isolation/authorization |
| eventType | Payload/schema contract | Allowlist |
| schemaVersion | Schema validator | Supported versions |
| destinationAlias | Policy/registry | Exists và được phép |
| targetProtocol | Destination registry | Enum protocol |
| routeKey | Trusted classifier | Có mapping rõ |
| replyRequired | Business/ingress contract | One-way hay request–reply |
| deadlineAt | Business policy | Không hết hạn |
| routePolicyVersion | Resolver | Audit/replay |

Quy trình:

1. **Xác thực nguồn** bằng mTLS/token/SSH/broker principal/DB service account theo giao thức.
2. Parse và **validate schema, kích thước, media type**.
3. Xác định tenant/eventId/operation; không nhận lời tự khai chưa được kiểm chứng.
4. Tra **destinationAlias** trong registry.
5. Kiểm quyền gọi destination và loại operation.
6. Tạo **trusted routeKey và routePolicyVersion**.
7. Gửi vào router; unknown/denied chuyển nhánh reject hoặc parking.
8. Lưu quyết định khi cần audit hoặc replay.

**MessageHeaders tự nó không phải security boundary.** Ranh giới tin cậy nằm ở bước chuẩn hóa, xác thực và authorization.

## 7. Sơ đồ một router, nhiều adapters

~~~mermaid
flowchart LR
    I["Normalized input"] --> R{"Protocol Router"}
    R -->|"HTTP"| H["httpChannel"]
    R -->|"SFTP"| S["sftpChannel"]
    R -->|"JMS"| J["jmsChannel"]
    R -->|"AMQP"| A["amqpChannel"]
    R -->|"KAFKA"| K["kafkaChannel"]
    R -->|"FILE"| F["fileChannel"]
    R -->|"JDBC"| D["jdbcChannel"]
    R -->|"UNKNOWN"| X["routingRejectedChannel"]
    H --> HG["HTTP gateway"]
    S --> SA["SFTP adapter"]
    J --> JA["JMS adapter"]
    A --> AA["AMQP adapter"]
    K --> KA["Kafka adapter"]
    F --> FA["File adapter"]
    D --> DA["JDBC handler"]
~~~

Mỗi nhánh phải xác định:

- Payload/serializer contract.
- Destination alias, cấu hình và quyền.
- Error/timeout/retry/parking.
- One-way hay request–reply.
- Idempotency, acknowledgement và transaction.
- Metrics và trạng thái để replay.

## 8. Ví dụ Java DSL: route theo header đã chuẩn hóa

Ví dụ minh họa Java DSL, cần có các channel và adapter endpoint thực được cấu hình riêng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;

@Configuration
public class ProtocolRouterFlow {

    @Bean
    IntegrationFlow protocolRoutingFlow() {
        return IntegrationFlow.from("normalizedInputChannel")
            .route(Message.class,
                message -> message.getHeaders().get("routeKey"),
                mapping -> mapping
                    .channelMapping("HTTP", "httpOutboundChannel")
                    .channelMapping("SFTP", "sftpOutboundChannel")
                    .channelMapping("JMS", "jmsOutboundChannel")
                    .channelMapping("AMQP", "amqpOutboundChannel")
                    .channelMapping("KAFKA", "kafkaOutboundChannel")
                    .channelMapping("FILE", "fileOutboundChannel")
                    .channelMapping("JDBC", "jdbcOutboundChannel")
                    .resolutionRequired(true))
            .get();
    }
}
~~~

- Router đọc routeKey do normalizer đặt.
- Channel mapping là **tên channel đã đăng ký**, không phải raw URL, topic, path do nguồn tự chọn.
- Với giá trị không được resolve, ưu tiên fail rõ/đường reject, không silently drop.
- Handler của mỗi outbound channel cần được đăng ký và cấu hình đúng.
- Ví dụ chưa có đầy đủ dependencies, gateways, converters, transactions và error flows.

**Lưu ý tương thích:** cú pháp DSL/classpath có thể khác giữa các phiên bản Spring Integration; khi triển khai phải đối chiếu API đúng version và test wiring thực tế.

## 9. @Router khi cần kết hợp nhiều headers

Một router bằng method thích hợp khi quyết định phụ thuộc tenant/eventType/destinationAlias. Ví dụ sau dùng policy service chỉ trả approved channel name từ allowlist.

~~~java
import org.springframework.integration.annotation.Router;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class TrustedProtocolRouter {

    private final RoutingPolicyService routingPolicy;

    public TrustedProtocolRouter(RoutingPolicyService routingPolicy) {
        this.routingPolicy = routingPolicy;
    }

    @Router(inputChannel = "normalizedInputChannel")
    public String route(Message<?> message) {
        RoutingDecision decision = routingPolicy.evaluate(
                message.getHeaders().get("tenantId"),
                message.getHeaders().get("eventType"),
                message.getHeaders().get("destinationAlias"),
                message.getHeaders().get("routeKey")
        );

        if (!decision.isAllowed()) {
            return "routingRejectedChannel";
        }
        return decision.getApprovedChannelName();
    }

    // RoutingPolicyService và RoutingDecision do ứng dụng định nghĩa.
}
~~~

Đây là **minh họa kiến trúc**, chưa có domain class definitions nên không phải ví dụ chạy độc lập.

- Policy phải kiểm chứng tenant, quyền và destination registry.
- Return channel name chỉ được là một **tên channel có sẵn/đã phê duyệt**.
- Unknown route vào routingRejectedChannel, không trả tên tùy ý từ untrusted header.
- Nếu dùng phương thức @Router, **không đồng thời đăng ký Java DSL router khác cùng lấy message từ input channel** mà không thiết kế subscription semantics.

## 10. HeaderValueRouter cho bài toán một header

**HeaderValueRouter** chọn channel theo một header và có thể dùng mapping cố định:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.router.HeaderValueRouter;

// Đoạn cấu hình nằm trong @Configuration class.
@Bean
HeaderValueRouter protocolHeaderRouter() {
    HeaderValueRouter router = new HeaderValueRouter("routeKey");
    router.setChannelMapping("HTTP", "httpOutboundChannel");
    router.setChannelMapping("SFTP", "sftpOutboundChannel");
    router.setChannelMapping("JMS", "jmsOutboundChannel");
    router.setChannelMapping("AMQP", "amqpOutboundChannel");
    router.setChannelMapping("KAFKA", "kafkaOutboundChannel");
    router.setChannelMapping("FILE", "fileOutboundChannel");
    router.setChannelMapping("JDBC", "jdbcOutboundChannel");
    router.setResolutionRequired(true);
    return router;
}
~~~

Chỉ tạo bean router **chưa đủ**; cần gắn nó vào endpoint/IntegrationFlow. Cần xác minh route key được chuẩn hóa (kiểu, chữ hoa/chữ thường, khoảng trắng) và các channel được đăng ký có subscriber.

| Bài toán | Lựa chọn |
|---|---|
| Một routeKey đã trusted, mapping ổn định | HeaderValueRouter |
| Nhiều headers và authorization | Policy service + @Router/DSL |
| Định tuyến dựa payload | Content-Based Router |
| Một event phải tới nhiều đích | Recipient List Router / fan-out |
| Hành trình tuần tự qua nhiều bước | Routing slip / workflow |
| Không có route được phép | Rejected/parking, không default discard |

## 11. Phân biệt Router, Filter, Transformer, Gateway và Adapter

Các pattern có thể cùng đứng trên một flow, nhưng không nên gộp chúng thành “router”.

| Pattern/thành phần | Câu hỏi nó giải quyết | Ví dụ |
|---|---|---|
| **Filter** | Message có được đi tiếp không? | File không thuộc hợp đồng không vào business flow |
| **Router** | Message sẽ đi nhánh nào? | Gửi sang HTTP, SFTP hay Kafka |
| **Transformer** | Cần đổi định dạng payload/metadata thế nào? | Canonical JSON sang CSV |
| **Header enricher** | Bổ sung metadata trusted nào? | routeKey, destinationAlias, correlation |
| **Splitter** | Cần tách một message thành nhiều message? | Một file chứa nhiều orders |
| **Aggregator** | Cần gom kết quả của nhiều message? | Tổng hợp kết quả từng file/recipient |
| **Bridge** | Nối hai channel/segment mà không đổi nghiệp vụ? | Liên kết các đoạn flow |
| **Outbound adapter** | Gửi one-way tới hệ thống ngoài? | File, SFTP, Kafka publish |
| **Outbound gateway** | Gửi request và đợi reply? | HTTP request–reply |
| **Service activator** | Chạy code nghiệp vụ? | Lưu database hoặc gọi policy service |

Ví dụ **HTTP inbound → SFTP outbound** cần nhiều bước: xác thực HTTP, parse/validate, định tuyến, render file hợp đồng đối tác, chọn filename, upload tạm, publish/rename, ghi kết quả và trả phản hồi phù hợp. Router **không** tự làm các bước khác.

## 12. Channel mapping và resolution: key lạ phải đi đâu?

Một router có thể gặp:

- Thiếu routeKey;
- Header có kiểu khác String, case hoặc whitespace không chuẩn;
- Giá trị routeKey hợp lệ về cú pháp nhưng tenant không được phép;
- Key chưa được map;
- Channel bean chưa được tạo;
- Channel có nhưng chưa có consumer;
- Channel nhận message nhưng payload không khớp serializer;
- Adapter đích trả lỗi I/O hoặc timeout.

### Ma trận lỗi

| Lỗi | Lớp chịu trách nhiệm | Hành động |
|---|---|---|
| Missing routeKey | Message contract/normalizer | Reject với reason MISSING_ROUTE |
| Unsupported targetProtocol | Registry/policy | Reject, không tự chọn business destination |
| Unauthorized destination | Authorization | Security audit, không route |
| Mapped channel not found | Deployment/config | Fail rõ + alert |
| Channel không có subscriber | Topology/runtime | Alert, test fail, preserve message |
| Payload/schema không tương thích | Transformer/contract | Quarantine hoặc transform đúng |
| Remote connection timeout | Outbound adapter | Retry/recovery theo hợp đồng |
| Request–reply timeout | Gateway | OUTCOME_UNKNOWN nếu có side effect |

**Không default unknown route sang HTTP partner hoặc nullChannel** với message nghiệp vụ cần hoàn thành.

### Default route nên dùng thế nào?

Một số router cho phép khai báo **defaultOutputChannel** và điều khiển cách xử lý khi resolution thất bại. Route mặc định phù hợp nhất thường là một **routingRejectedChannel** được giám sát. Nếu đẩy reject vào một DirectChannel in-memory rồi coi đã lưu bền, message vẫn có thể bị mất sau crash.

Ví dụ policy:

~~~yaml
# Pseudocode minh họa chính sách, không phải cấu hình Spring Integration trực tiếp.
route_resolution:
  allowed_keys: [HTTP, SFTP, JMS, AMQP, KAFKA, FILE, JDBC]
  unknown_route:
    action: REJECT
    reason_code: UNSUPPORTED_ROUTE
    destination: routingRejectedChannel
  unauthorized:
    action: ESCALATE
    reason_code: ROUTE_NOT_AUTHORIZED
  logging:
    include_business_event_id: true
    include_credentials: false
~~~

### Không sử dụng nullChannel để che lỗi routing

**NullChannel** hủy message có chủ đích. Nó phù hợp cho nhánh đã được chứng minh không cần xử lý, nhưng route key chưa xác định, lỗi mapping hoặc destination không tồn tại là **lỗi chưa giải quyết**. Hãy dùng rejected/parking flow, exception/error channel và durable state tùy nguồn.

## 13. Bảo mật khi định tuyến theo header

### 13.1. Header spoofing

~~~text
HTTP client tự gửi:
   X-Target-Protocol: JDBC
   X-Destination-Alias: finance-write
~~~

Nếu ứng dụng dùng các giá trị ấy trực tiếp để chọn JDBC handler, client có thể ghi dữ liệu không được phép. Cần:

1. Xác thực nguồn và xác định principal/tenant;
2. Parse nghiệp vụ hợp lệ;
3. Resolve destination từ registry do hệ thống kiểm soát;
4. Kiểm tenant có được thực hiện operation này không;
5. Tạo routeKey trusted **sau** authorization;
6. Kiểm quyền thêm lần nữa ở handler đích nếu nghiệp vụ nhạy cảm.

### 13.2. SSRF trong dynamic HTTP routing

Nếu outbound HTTP handler đọc URL tùy ý từ header do upstream kiểm soát, kẻ gửi có thể cố gọi mạng nội bộ hoặc metadata service. Dùng **destinationAlias → URL registry allowlisted**, giới hạn scheme/host/port/redirect và egress policy.

### 13.3. Path/topic/destination injection

Một header sai có thể khiến:

- SFTP ghi vào remote directory ngoài phạm vi tenant;
- File outbound ghi vượt root directory;
- JMS/AMQP đẩy message vào queue hoặc exchange của đối tượng khác;
- Kafka publish vào topic không được phép;
- JDBC tạo tên table/SQL từ untrusted string.

**Dùng allowlist, ACL và kiểm tra ở adapter.** Không interpolate user input vào SQL identifier/URL/path/topic mà chưa có policy.

### 13.4. Header propagation và secrets

Đừng chuyển toàn bộ inbound HTTP/JMS/Kafka headers tới hệ thống ngoài. Các header có thể chứa bearer token, cookie, source IP, replyChannel/errorChannel reference hoặc nội dung nhạy cảm.

Nên **chỉ chọn những header thuộc outbound contract**; đưa correlation ID an toàn nhưng không phát tán credential hay internal routing metadata.

### 13.5. Định tuyến theo tenant không được dựa vào tenantId tự khai

Nếu một payload có tenantId=T2 nhưng principal chỉ có quyền T1, hệ thống phải reject trước router. Không cho phép “route sang T2 vì message header viết vậy”, kể cả mapping T2 đến một channel có sẵn.

## 14. Định tuyến theo nhiều chiều: tenant + eventType + protocol

Trong sản phẩm thực, protocol chỉ là một chiều; quyết định đích thường phải xét các chiều khác.

| Tenant | Event | Destination alias | Protocol | Channel |
|---|---|---|---|---|
| Tenant A | invoice.created | ERP-X | HTTP | httpOutboundChannel |
| Tenant A | invoice.exported | Archive-X | SFTP | sftpOutboundChannel |
| Tenant A | order.changed | Fulfillment-Q | JMS | jmsOutboundChannel |
| Tenant B | order.changed | Broker-Y | AMQP | amqpOutboundChannel |
| Tenant B | shipment.event | Analytics-K | KAFKA | kafkaOutboundChannel |
| Tenant C | report.ready | Archive-Local | FILE | fileOutboundChannel |
| Tenant C | reconciliation | Internal-DB | JDBC | jdbcOutboundChannel |

Các hàng là ví dụ minh họa, không phải rule của một hệ thống thật.

### Hai cấp router

~~~text
Ingress
  -> Normalize + authorize
  -> Business destination resolver(tenant,eventType,version)
  -> Protocol router(targetProtocol)
  -> Adapter handler
~~~

### Một cấp router

~~~text
Ingress
  -> Normalize + authorize
  -> RoutingPolicyService
  -> approvedChannelName
  -> Adapter handler
~~~

Hai cấp giúp **tái sử dụng protocol branches** và tách business policy khỏi transport. Một cấp tập trung decision. Dù chọn cách nào, cần **policy version, rejected route và audit**.

## 15. Payload contract và serializer theo protocol

Một canonical business DTO không tự tương thích với mọi outbound adapter.

| Nhánh | Payload adapter mong đợi | Metadata quan trọng |
|---|---|---|
| HTTP | JSON/XML/bytes theo API contract | Method, path alias, content-type, idempotency key |
| SFTP | File content, byte[]/stream theo adapter | Remote temp/final filename, checksum |
| JMS | Converted JMS message payload | Correlation, destination alias, delivery mode |
| AMQP | Encoded message body theo converter | Exchange/routing key, message ID, confirm |
| Kafka | Key/value serialized đúng schema | Topic alias, record key, partition policy |
| File | Text/binary/document | Filename, directory, publish strategy |
| JDBC | Params/DTO cho SQL operation | Transaction boundary, business key |

### Ví dụ schema transformation sau router

~~~text
CanonicalInvoiceV3
    -> Router: SFTP
    -> RenderPartnerCsvV2
    -> Produce manifest + checksum
    -> SFTP outbound adapter
~~~

Router chọn **nhánh SFTP**, không tự biến InvoiceV3 thành CSV. Chọn transformer theo destination contract để không áp dụng “mọi SFTP đều CSV cùng schema”.

### Header chỉ hỗ trợ, không thay validation

Header contentType=application/json không chứng minh payload JSON hợp lệ. Header schemaVersion=v3 không chứng minh fields đúng v3. Cần parse/validate và xử lý lỗi, không đẩy vào adapter rồi retry mãi.

## 16. DirectChannel, ExecutorChannel và QueueChannel tại nhánh đích

Loại MessageChannel tác động đến thời gian/semantics của việc router gửi message.

### DirectChannel

Thường dispatch subscriber **đồng bộ** trong thread gửi. Nếu outbound handler ném lỗi và exception propagate, upstream có thể nhận exception trong cùng call stack.

Một HTTP inbound gateway dùng DirectChannel có thể bị giữ khi outbound HTTP retry. Cần connect/read timeout và tổng deadline.

### ExecutorChannel

Gửi message sang executor để xử lý bất đồng bộ. Sender có thể nhận kết quả send trong khi handler đích chưa hoàn thành.

**Gửi thành công tới ExecutorChannel không chứng minh remote adapter đã gửi xong**. Cần error flow và durable handoff nếu phải khôi phục qua crash.

### QueueChannel

Tính bền vững phụ thuộc MessageStore và transaction/consumer semantics. Poller lấy message ra khỏi queue có thể cần rollback/redelivery theo thiết kế nếu downstream thất bại.

| Channel | Thành công của send có nghĩa gì? | Nếu adapter đích lỗi |
|---|---|---|
| DirectChannel | Subscriber có thể đã chạy đồng bộ | Exception có thể propagate |
| ExecutorChannel | Work được giao/đặt vào executor | Error async cần xử lý riêng |
| QueueChannel | Message được xếp theo cấu hình | Retry/rollback/persistence cần định nghĩa |
| PublishSubscribeChannel | Dispatch tới subscribers theo mode | Fan-out success/failure policy riêng |

**Router không phải durable broker.** Cần xác định ranh giới nguồn ack, transaction và persistence cho từng topology.

## 17. Chọn một nhánh hay fan-out nhiều đích?

Protocol router thường quyết định **một đích**. Nhưng có nghiệp vụ cần gửi **cùng một event** tới nhiều recipient:

~~~text
invoice.created
    -> HTTP ERP
    -> Kafka analytics
    -> SFTP audit export
~~~

Trường hợp này cần Recipient List Router, PublishSubscribeChannel hoặc fan-out orchestration thích hợp.

### Fan-out không đồng nghĩa atomic delivery

Nếu gửi ba đích và kết quả:

~~~text
eventId=invoice-882-v3
  HTTP recipient: DONE
  Kafka recipient: DONE
  SFTP recipient: RETRY_WAIT
~~~

Việc retry **cả fan-out** có thể gửi lại HTTP/Kafka đã thành công. Nên lưu **trạng thái theo recipient** và retry SFTP riêng, dùng idempotency/transactional outbox.

| Pattern | Số đích | Khi phù hợp |
|---|---|---|
| HeaderValueRouter | Thường một theo key | Chọn protocol |
| Content-Based Router | Thường một theo điều kiện | Chọn theo nội dung nghiệp vụ |
| Recipient List Router | Nhiều theo danh sách | Gửi tới tập recipient đã quy định |
| Publish–Subscribe | Broadcast theo topology | Eventing nhiều subscriber |
| Routing Slip | Nhiều bước có thứ tự | Workflow gồm các bước tuần tự |
| Scatter–Gather | Nhiều requests, gom replies | Query nhiều backend |

### Đừng nhầm nhiều subscribers trên một channel với routing có thứ tự

Một DirectChannel có nhiều subscribers không có nghĩa message sẽ được gửi tới **tất cả**. Muốn fan-out, dùng thành phần được thiết kế cho phân phối nhiều recipient và kiểm thử failure semantics. Tương tự, router tới một PublishSubscribeChannel không tự đảm bảo tất cả subscribers đã commit nghiệp vụ.

## 18. Request–reply khác one-way routing

Đây là sai lầm phổ biến khi trộn nhiều protocol.

### One-way

Inbound event nhận qua Kafka → gửi SFTP file. Việc route sang SFTP outbound adapter chỉ tạo bước **gửi một chiều**. Nó không có contract nhận một reply như HTTP outbound gateway.

### Request–reply

HTTP inbound gateway nhận request → router chọn HTTP/JMS gateway → nhận response → trả lại caller.

Nếu route chọn một nhánh **không trả reply** nhưng caller đang đợi, gateway có thể timeout. Router không tự biến adapter one-way thành request–reply.

~~~mermaid
sequenceDiagram
    participant C as HTTP caller
    participant I as Inbound gateway
    participant R as Router
    participant H as HTTP outbound gateway
    C->>I: Request + correlation
    I->>R: Normalized message, reply required
    R->>H: Approved route HTTP
    H-->>I: Partner response
    I-->>C: Reply theo contract
~~~

### Những kiểm tra bắt buộc

- Nhánh được chọn có **reply contract** phù hợp không?
- Reply có chứa correlation với request gốc không?
- Timeout/deadline còn đủ cho toàn flow không?
- Exception của downstream có được trả về caller không?
- Nếu một nhánh asynchronous, ai chịu trách nhiệm response/job ID?
- Trả trạng thái accepted/202 khi job được persist **khác với** nói rằng operation đã hoàn tất.

### ReplyChannel/errorChannel headers

Spring Integration có thể dùng replyChannel và errorChannel headers cho message flow. Không copy những reference này qua boundary không tin cậy hoặc chuyển chúng tới broker bên ngoài tùy ý. Header serialization không đảm bảo chúng có ý nghĩa với consumer ở process khác.

## 19. Error handling: routing fail khác delivery fail

Hai nhóm lỗi cần tách:

**Routing failure:** thiếu routeKey, invalid protocol, unauthorized target, channel mapping không tồn tại.

**Delivery/handler failure:** route hợp lệ nhưng HTTP 503, SFTP timeout, JMS broker unavailable, Kafka publish fail hoặc DB deadlock.

~~~mermaid
flowchart TD
    M["Normalized message"] --> V["Validate routing policy"]
    V --> Q{"Route hợp lệ?"}
    Q -->|"Không"| X["ROUTING_REJECTED: reason + audit"]
    Q -->|"Có"| R{"Protocol router"}
    R --> H["Adapter handler"]
    H --> O{"Delivery thành công?"}
    O -->|"Có"| D["Record DONE / reply"]
    O -->|"Transient"| T["Bounded retry + backoff"]
    T --> H
    O -->|"Permanent"| P["Quarantine / owner triage"]
    O -->|"Unknown outcome"| U["Query/reconcile / PARKED"]
    T -->|"Exhausted"| E["Durable delayed retry / DLQ"]
    X --> F["Durable reject handling"]
    P --> F
    U --> F
    E --> F
~~~

Một ErrorMessage/errorChannel có thể được dùng theo cấu hình để quan sát hoặc chuyển lỗi. **ErrorChannel không mặc định là DLQ**, và **NullChannel** không phải recovery cho route không hợp lệ.

### Hợp đồng lỗi đề xuất

| Field | Ý nghĩa |
|---|---|
| businessEventId | Khóa business stable |
| correlationId | Liên kết ingress/router/adapter |
| sourceSystem | Nguồn xác thực |
| routeKey/destinationAlias | Quyết định đích được phép |
| routePolicyVersion | Version của mapping |
| failureStage | NORMALIZE, ROUTE, TRANSFORM, DELIVER, ACK |
| errorCategory | ROUTE_INVALID, AUTH_DENIED, TRANSIENT, PERMANENT, OUTCOME_UNKNOWN |
| retryCount | Attempts đã thực hiện theo scope |
| payloadReference | Tham chiếu tới data store bền |
| finalOutcome | DONE, REJECTED, PARKED, DLQ |
| occurredAt | Thời điểm lỗi |
| owner | Đơn vị xử lý tiếp |

Không ghi secret/PII/raw payload vào log thất bại khi không cần. Nếu lưu để redrive, bảo vệ bằng phân quyền và retention.

## 20. Retry tại router hay ở adapter handler?

Một router **chọn route**; sau đó handler mới thực hiện I/O ngoài. Nếu handler lỗi transient, đơn vị retry thường nên là **handler có thao tác ngoài** hơn là retry từ đầu toàn flow.

~~~text
Inbound -> Normalize -> Router -> HTTP gateway [retry advice] -> Save status
                           |
                           +-> SFTP adapter [retry policy phù hợp]
~~~

Nếu retry cả flow từ Normalize, có thể:

- Tạo route decision khác khi registry đã thay đổi;
- Chạy lại validation/enrichment có side effects;
- Gửi lại đích đã xử lý xong;
- Mất trace/correlation ổn định;
- Tạo duplicate khi remote đã commit nhưng response bị mất.

### RetryPolicy, BackOffPolicy và RequestHandlerRetryAdvice

- **RetryPolicy:** exception/điều kiện nào được retry, bao nhiêu attempts.
- **BackOffPolicy:** khoảng nghỉ giữa attempts; không tự quyết định retryability.
- **RequestHandlerRetryAdvice:** bọc invocation của handler được gắn.
- **RecoveryCallback:** xử lý khi exhausted; nếu trả bình thường có thể ảnh hưởng ack/commit.
- **Delayed retry:** retry dài lưu bền qua broker/job store.

**Không tự cho rằng adapter Kafka/JMS sẽ ack lại hoặc SFTP poller sẽ tải lại file chỉ vì handler có retry advice.**

## 21. Transaction, acknowledgement và idempotency

Routing qua nhiều protocol hiếm khi có một transaction chung.

### Ba ranh giới

1. **Source delivery:** File/SFTP scan, JMS/AMQP delivery, Kafka record/offset, HTTP request hoặc JDBC poll row.
2. **Routing/processing:** normalize, policy, channel dispatch và handler.
3. **Destination side effect:** remote HTTP order, file transfer, broker publish hoặc DB transaction.

Một source được ack sớm khi downstream chưa hoàn tất có thể gây **mất tác vụ**. Ngược lại, không ack sau khi remote đã commit có thể tạo **duplicate** khi source redeliver.

### Stable business event ID

~~~text
businessEventId = tenant-17:invoice-882:v3
routePolicyVersion = 2026-11-r3
destinationAlias = billing-erp

Attempt 1:
    HTTP POST tạo invoice thành công nhưng response mất.

Attempt 2:
    Dùng cùng idempotency key hoặc query trạng thái trước retry.
~~~

**Router không tự tạo idempotency**. Cần inbox/dedupe, idempotency key theo partner contract, unique business key hoặc reconciliation.

### Outbox/inbox

- **Inbox:** ghi business event ID/result để consumer xử lý duplicate an toàn.
- **Transactional outbox:** lưu nghiệp vụ và event cần gửi cùng DB transaction; publisher có thể retry.
- **Routing decision state:** lưu đích/route policy version cho những message phải retry hoặc replay.
- **Recipient state:** nếu fan-out, theo dõi DONE/RETRY_WAIT/PARKED cho từng destination.

### Quyết định route khi replay

Nếu destination registry thay đổi giữa lần đầu và lần replay, message có thể được gửi sang một đích khác ngoài ý muốn. Nên xác định rõ:

- **Pinned decision:** lưu routeKey, destinationAlias, policy version của lần quyết định đầu và replay cùng đích (thường thích hợp cho tài chính/audit).
- **Re-evaluate decision:** tính lại route theo policy mới, chỉ khi business contract cho phép và có migration/audit.
- **Manual override:** cho phép admin chuyển đích có approval, reason và kiểm soát idempotency.

Không tự động re-evaluate mọi message chỉ vì router method được cập nhật.

## 22. File và SFTP: router không thay trạng thái file

File inbound và SFTP inbound thường sử dụng **poller** và filters. Bài toán route có thể là:

~~~text
SFTP inbound:
    invoices/*.ready -> parse InvoiceV3
    reports/*.ready  -> parse ReportV2
        -> normalized event
        -> protocol router
~~~

### File/SFTP inbound

- **File ready:** nguồn ghi tên tạm rồi publish/rename hoặc manifest. Không parse file đang upload.
- **File filters:** accept-once/local/remote metadata không tự bảo đảm event chỉ được xử lý một lần.
- **Parser:** schema, encoding và checksum phải được kiểm tra trước route.
- **Splitter:** một file nhiều records cần stable eventId cho từng record hoặc stable file+record key.
- **Error:** invalid file/record vào quarantine; unknown route không vào NullChannel.
- **Poller:** lần poll sau không chắc lại thấy file đã đánh dấu/di chuyển.
- **Recovery:** downstream fail cần durable message state hoặc parking để replay.

### SFTP/File outbound

Router chọn nhánh SFTP/File nhưng handler quyết định cách publish và trạng thái transfer.

| Thuộc tính | Ví dụ | Bảo vệ |
|---|---|---|
| Destination alias | archive-partner-A | Allowlist; không raw host |
| Directory | /outgoing/invoices | Root allowlist/path validation |
| Temp filename | INV-882.v3.part | Stable id, tránh collision |
| Final filename | INV-882.v3.csv | Quy tắc overwrite |
| Format | CSV v2 | Contract, charset |
| Checksum/manifest | SHA-256 | Kiểm transfer |
| Publish step | Rename/ready marker | Không giả định atomic xuyên filesystem |
| Recovery | RETRY_WAIT/PARKED | Không tự xóa source |

Nếu upload thành công nhưng response mất, gửi lại có thể ghi đè hoặc tạo file thứ hai. **Đối soát remote state** trước retry; chọn đúng channel chưa chứng minh transfer đã hoàn tất.

## 23. HTTP: chọn đúng endpoint, bảo toàn request–reply

HTTP inbound gateway thường xử lý request–reply. Outbound gateway gọi API đích; cần phân biệt với Kafka/SFTP one-way.

~~~text
Normalized event:
  tenantId=tenant-17
  eventType=invoice.created
  destinationAlias=billing-erp
  routeKey=HTTP

Registry:
  billing-erp -> approved HTTPS endpoint

HTTP outbound handler:
  InvoiceV3 -> ERP InvoiceRequestV2
  POST cùng Idempotency-Key ổn định
~~~

### Những thứ router không tự bảo đảm

- URL/method/path được allowlist, không SSRF;
- Authentication/token/mTLS đúng;
- Schema request/response đúng;
- Connect/read timeout, total deadline;
- 429/503 được backoff/rate limit/circuit breaker phù hợp;
- 400/401/403 không bị retry vô ích;
- POST timeout có thể là **OUTCOME_UNKNOWN**;
- Reply correlation và status trả về caller;
- Không phát tán Authorization/cookie sang đối tác.

### Lỗi route hợp lệ nhưng delivery thất bại

Router chọn đúng HTTP channel, đối tác trả 503. Không cần quay về đầu flow và route lại vô hạn. Retry ở **HTTP handler** với maxAttempts/backoff/budget, rồi delayed retry có pinned destinationAlias nếu sự cố kéo dài.

Nếu remote tạo order rồi mất response, dùng **idempotency contract hoặc query trạng thái**. Không xem exception là bằng chứng chưa commit.

## 24. JMS và AMQP: broker routing khác Spring Integration routing

**Spring Integration router** chọn **MessageChannel nội bộ**. JMS queue và AMQP exchange/routing key là **địa chỉ broker** do outbound adapter sử dụng.

### JMS inbound/outbound

Quy trình điển hình:

1. JMS listener nhận delivery.
2. Inbound adapter chuyển thành Spring Message.
3. Normalizer tạo trusted eventId/headers.
4. Router chọn channel.
5. Handler đích thực hiện operation.
6. Container quản lý ack/commit/rollback theo cấu hình và outcome.

Nếu ErrorMessage bị nuốt rồi container ack trước khi outbound hoàn tất, message có thể mất. JMS broker redelivery **không đồng nghĩa** handler retry.

### AMQP outbound

~~~text
Spring Integration:
    routeKey=AMQP
      -> amqpOutboundChannel
      -> AMQP outbound adapter

AMQP broker:
    exchange=approved-exchange
    routingKey=approved-broker-routing-key
~~~

Client upstream không được chọn tùy ý exchange/routingKey của broker qua headers. Dùng **destinationAlias → registry allowlisted** và quyền của producer.

### Publisher confirm, retries và duplicate

- Publish có thể tới broker nhưng client không nhận confirm → **unknown outcome**.
- Retry publish có thể tạo duplicate.
- Publisher confirm không xác nhận consumer đã xử lý nghiệp vụ.
- Consumer cần stable eventId và dedupe.
- Nếu event phát sinh từ DB transaction, cân nhắc transactional outbox.
- Requeue ngay liên tục có thể tạo AMQP hot loop; cần delayed retry/DLQ theo contract.

Nếu handler có 4 attempts và broker redeliver 5 deliveries, có thể có **20 handler invocations**, chưa tính HTTP client retries.

## 25. Kafka: chọn topic không đồng nghĩa quản lý offset

Kafka có topics, partitions, record keys, consumer groups và offsets. Router Spring Integration vẫn chỉ chọn **internal channel**.

### Kafka outbound

~~~text
Normalized event:
  eventType=shipment.updated
  destinationAlias=analytics-kafka
  routeKey=KAFKA

Kafka handler:
  topic alias -> allowlisted topic
  key = stable aggregate ID
  value = serializer theo schema contract
  headers = whitelisted correlation metadata
~~~

Router không tự chọn partition, serializer hay guarantee của producer; adapter/client chịu trách nhiệm những thuộc tính đó.

### Kafka inbound

Một inbound record có Kafka-specific headers. Normalizer cần chuyển chúng thành **businessEventId/eventType/schemaVersion/tenantId** theo nguồn đáng tin, không yêu cầu mọi protocol downstream hiểu Kafka-specific headers.

**Offset commit** thuộc consumer/container. Nếu router gửi message vào ExecutorChannel rồi offset commit sớm trong khi outbound chưa hoàn tất, có nguy cơ mất nghiệp vụ.

### Ordering

~~~text
Partition P:
  offset 100: order-created
  offset 101: order-updated
  offset 102: order-cancelled
~~~

Nếu offset 100 đi qua HTTP retry dài còn 101 đi Kafka branch khác chạy nhanh, **ordering nghiệp vụ** có thể bị thay đổi. Cần bảo vệ theo aggregate/version hoặc chọn topology phù hợp. Retry topic/DLT có thể ảnh hưởng thứ tự.

Exactly-once trong phạm vi Kafka không tự mở rộng sang HTTP partner hoặc DB ở transaction độc lập.

## 26. JDBC: route tới database không cấp quyền SQL

RouteKey=JDBC chỉ chọn nhánh DB. Handler phải thực hiện **operation đã được kiểm soát**:

- Không lấy tên table/SQL nguyên văn từ header do client khai.
- Dùng **operationAlias** được duyệt, ví dụ markReconciled hoặc saveInvoiceStatus.
- Kiểm tenant/business permissions và DB service-account scope.
- Parameter binding cho dữ liệu, transaction boundary rõ.
- Unique business key và idempotency.
- Deadlock/serialization conflict retry transaction mới khi cần.
- JDBC inbound polling quản lý row lease/state qua restart.

### JDBC inbound polling

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                  |
                  +-> RETRY_WAIT -> PROCESSING
                  |
                  +-> PARKED
~~~

Nếu poller đã claim row rồi downstream HTTP handler lỗi, row không tự về NEW vì router kết thúc. Cần atomic claim, leaseOwner/leaseUntil, attemptCount/nextAttemptAt và policy recovery.

## 27. Route registry, policy version và replay

Khi có nhiều đích, một **destination registry được quản trị** thường tốt hơn hard-code business alias ở hàng chục routers.

### Ví dụ registry record

~~~json
{
  "destinationAlias": "billing-erp",
  "targetProtocol": "HTTP",
  "channelName": "httpOutboundChannel",
  "allowedTenants": ["tenant-17"],
  "allowedEventTypes": ["invoice.created", "invoice.updated"],
  "schemaContract": "erp-invoice-v2",
  "enabled": true,
  "routingPolicyVersion": "2026-11-r3",
  "owner": "integration-platform",
  "sloClass": "business-critical"
}
~~~

Đây là schema gợi ý, không phải một kiểu cấu hình mặc định của Spring Integration.

### Quy tắc quản trị

1. Chỉ principal được phép mới sửa registry.
2. ChannelName/adapter target nằm trong **allowlist** có thể kiểm thử.
3. Không chấp nhận raw user-provided URL/path/topic/queue để tạo mapping.
4. Validate destination trước khi enable.
5. Mọi quyết định lưu **routePolicyVersion** khi cần replay/audit.
6. Có khả năng disable một destination khi incident/circuit open.
7. Có canary/rollback cho thay đổi route theo tenant/eventType.
8. Không tự động thay đích của message đang retry khi chưa có business approval.
9. Sửa policy cần regression tests về tenant isolation và protocol boundaries.
10. Khi registry unavailable, default **fail safe**/parking thay vì bypass authorization.

### Routing decision record

~~~json
{
  "businessEventId": "tenant-17:INV-882:v3",
  "tenantId": "tenant-17",
  "eventType": "invoice.created",
  "destinationAlias": "billing-erp",
  "targetProtocol": "HTTP",
  "routeKey": "HTTP",
  "routePolicyVersion": "2026-11-r3",
  "decision": "APPROVED",
  "deliveryState": "RETRY_WAIT",
  "attemptCountPersisted": 3,
  "nextAttemptAt": "2026-11-23T10:30:00Z",
  "deadlineAt": "2026-11-24T00:00:00Z",
  "payloadReference": "secure-message-store/INV-882-v3"
}
~~~

### Pin hay re-evaluate khi replay?

- **Pinned route:** giữ destinationAlias/targetProtocol/policyVersion của quyết định ban đầu; thường an toàn hơn khi cần audit hoặc gửi tài chính.
- **Re-evaluate:** chạy policy mới khi hợp đồng nghiệp vụ cho phép chuyển đích, có migration và đối soát.
- **Manual override:** người có quyền chọn đích mới, ghi approval/reason, kiểm tra duplicate effect ở cả đích cũ và mới.

Không tự chuyển message sang đối tác khác chỉ vì Registry đã thay đổi giữa các retries.

## 28. Observability: phân biệt route success và delivery success

**Một message được route thành công** chỉ chứng minh nó đã tới channel theo topology. Nếu channel là ExecutorChannel/QueueChannel, tác vụ ngoài có thể chưa chạy.

| Metric | Định nghĩa | Mục đích |
|---|---|---|
| **route_decisions_total** | Số quyết định theo routeKey/flow | Phân phối giao thức |
| **route_rejected_total** | Số message không có route hợp lệ | Phát hiện policy/config errors |
| **route_unauthorized_total** | Số route bị từ chối quyền | Tín hiệu security |
| **route_resolution_errors_total** | Mapping/channel không resolve | Bắt deployment regressions |
| **route_decision_latency_seconds** | Độ trễ policy resolver | Đo registry bottleneck |
| **delivery_attempts_total** | Số lần handler/adapter thử gửi | Tách attempts khỏi message count |
| **delivery_success_total** | Số business deliveries hoàn tất theo đích | Không nhầm send-to-channel |
| **delivery_exhausted_total** | Số delivery hết retry budget | Phát hiện nhu cầu parking |
| **unknown_outcome_total** | Remote đã có thể commit nhưng response mất | Đối soát kịp thời |
| **parked_backlog_age_seconds** | Tuổi message chưa giải quyết | SLA/operational debt |
| **broker_redelivery_total** | Source/broker giao lại | Tách với handler retry |
| **duplicate_prevented_total** | Duplicate bị dedupe đúng | Độ an toàn replay |
| **destination_latency_seconds** | P50/P95/P99 theo protocol/alias | Bottleneck |
| **queue_lag / queue_depth** | Message chờ theo nhánh | Backpressure |
| **incorrect_route_incidents_total** | Sai đích đã xác minh | Chất lượng policy |

### Structured log tại ranh giới routing

Thông tin nên ghi:

- businessEventId, correlationId;
- sourceSystem/tenant đã xác thực;
- eventType/schemaVersion;
- destinationAlias, targetProtocol, routeKey;
- routePolicyVersion, decision reason;
- failureStage/errorCategory;
- terminal outcome và acknowledgement outcome khi biết;
- elapsed time và attempt count.

Không ghi raw Authorization headers, bearer tokens, SSH keys, broker credentials hoặc full customer payload.

### Cardinality

Không dùng eventId/orderId/correlationId làm metric labels vì cardinality lớn. Chúng phù hợp với log/tracing; metric labels nên là routeKey, endpointAlias, errorCategory, outcome và danh mục eventType giới hạn.

### Cảnh báo “route success 100%” đánh lừa

Nếu hệ thống chỉ đo message.send thành công vào QueueChannel, dashboard có thể báo 100% trong khi consumer không chạy hoặc outbound adapter trả 503. Cần một **business completion metric** và backlog/unknown-outcome metrics độc lập.

## 29. Unit test route policy và header normalization

Một router đáng tin phải có test đúng route, từ chối route không hợp lệ và ngăn header giả mạo.

| Input | Kỳ vọng |
|---|---|
| tenant-17 + invoice.created + billing-erp | HTTP approved |
| tenant-17 + invoice.exported + archive-x | SFTP approved |
| tenant-17 + unknown event | ROUTING_REJECTED |
| tenant không được cấp quyền destinationAlias | ROUTE_NOT_AUTHORIZED |
| Thiếu routeKey sau normalization | MISSING_ROUTE |
| Header routeKey chứa case/whitespace sai | Normalize hoặc reject nhất quán |
| HTTP client tự gửi routeKey=JDBC | Không vượt policy |
| destinationAlias chứa raw internal URL | Reject SSRF |
| SFTP path chứa traversal | Reject |
| Kafka topic ngoài allowlist | Reject |
| Unsupported schemaVersion | Reject hoặc convert theo contract |
| Business event quá deadline | CANCELLED/PARKED theo policy |
| Registry tạm unavailable | Fail safe/parking |
| Route policy thay giữa retry | Pinned/migrated quyết định được kiểm toán |
| Destination disabled | Reject/PARKED, không default sang đích khác |
| Event duplicate với version khác | Không dedupe nhầm |

### Test message contract

Với mỗi adapter inbound:

1. Header raw được chuyển sang trusted metadata theo đúng nguồn.
2. Principal/tenant được xác minh trước khi tạo routeKey.
3. businessEventId ổn định qua retry/redelivery/replay.
4. schemaVersion được validate bằng payload chứ không chỉ header.
5. Correlation ID được bảo toàn và không bị leak credential.
6. Unknown route được reject có reason, không đi nullChannel.
7. Header đặc thù Kafka/SFTP/JMS không bị lộ sang HTTP partner.
8. Route decision chứa policy version phù hợp.

## 30. Integration test: chứng minh đúng MessageChannel và adapter

Một topology test:

~~~text
testInputChannel
    -> normalizer
    -> protocolRouter
       -> mockHttpChannel
       -> mockSftpChannel
       -> mockKafkaChannel
       -> mockJdbcChannel
       -> rejectedChannel
~~~

**Không cần gọi mạng thật để kiểm tra routing thuần túy**; có thể dùng test endpoints, spy/ChannelInterceptor, mock handler hoặc test application context.

Với message routeKey=HTTP:

- Chỉ mockHttpChannel nhận một message theo semantics một-nhánh.
- Các channel khác không nhận message.
- Payload/headers giữ contract.
- RejectedChannel không nhận.
- Nếu adapter HTTP giả lập lỗi, error/recovery được kích hoạt ở nhánh HTTP, không gửi lại SFTP/Kafka.
- Khi thiếu mapping, error flow có reason và message không bị silent drop.

### Kiểm thử request–reply

Một HTTP inbound gateway đồng bộ cần:

- Reply được trả khi nhánh chọn gateway có response.
- Error status rõ khi không có route hợp lệ.
- One-way branch không bị dùng như reply path nếu contract chưa có job acceptance.
- Correlation ID đúng khi có concurrency.
- Timeout/deadline được kiểm tra; caller retry không tạo duplicate.

### Test asynchronous boundaries

Với ExecutorChannel hoặc QueueChannel, đừng chỉ assert send thành công. Cần chờ **destination completion hoặc durable status** với timeout test, kiểm tra errorChannel, storage/recovery và lifecycle khi shutdown.

## 31. Ma trận kiểm thử end-to-end đa protocol

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| R1 | routeKey=HTTP hợp lệ | Chỉ HTTP branch |
| R2 | routeKey=SFTP hợp lệ | Chỉ SFTP branch |
| R3 | routeKey=JMS hợp lệ | Chỉ JMS branch |
| R4 | routeKey=AMQP hợp lệ | Chỉ AMQP branch |
| R5 | routeKey=KAFKA hợp lệ | Chỉ Kafka branch |
| R6 | routeKey=FILE hợp lệ | Chỉ File branch |
| R7 | routeKey=JDBC hợp lệ | Chỉ JDBC branch |
| R8 | Thiếu routeKey | ROUTING_REJECTED có reason |
| R9 | Unsupported key | Không chuyển business destination mặc định |
| R10 | Channel mapping typo | Fail rõ/alert |
| R11 | Channel không subscriber | Test phát hiện topology lỗi |
| R12 | Header case/kiểu sai | Normalize/reject theo policy |
| R13 | Client HTTP cố chọn JDBC | Authorization chặn |
| R14 | Tenant A chọn destination tenant B | Từ chối |
| R15 | Raw URL tới metadata/internal host | SSRF guard chặn |
| R16 | Raw SFTP path vượt root | Path guard chặn |
| R17 | Raw JMS queue/AMQP exchange ngoài allowlist | Không publish |
| R18 | Raw Kafka topic không được phép | Không publish |
| R19 | HTTP route đúng nhưng schema sai | Quarantine/transform error |
| R20 | HTTP 503 rồi success | Retry bounded, một kết quả |
| R21 | POST commit rồi response mất | Idempotency/reconcile |
| R22 | SFTP upload timeout sau remote write | Đối soát remote state |
| R23 | SFTP file đang upload | Không parse partial |
| R24 | File duplicate sau restart | Stable eventId dedupe |
| R25 | JMS listener rollback | Redelivery theo contract |
| R26 | AMQP confirm mất | Consumer/idempotency xử lý duplicate |
| R27 | Kafka offset chưa commit và handler fail | Redelivery/recovery đúng |
| R28 | Kafka ordering theo aggregate | Không xử lý sai version |
| R29 | JDBC deadlock | Transaction mới, commit hợp lệ |
| R30 | JDBC row claim rồi app chết | Lease/recovery hoạt động |
| R31 | Policy đổi giữa retry | Pinned/migrated decision có audit |
| R32 | Destination disabled | PARKED/reject rõ |
| R33 | DirectChannel downstream throw | Exception path đúng |
| R34 | ExecutorChannel downstream throw | ErrorMessage/parking đúng |
| R35 | HTTP inbound route sang one-way adapter | Reply/job contract, không timeout vô nghĩa |
| R36 | Fan-out ba recipient, SFTP lỗi | Chỉ retry recipient chưa DONE |
| R37 | Ghi DLQ/parking thất bại | Không ack mất source message |
| R38 | Replay businessEventId | Không nhân đôi ERP order |
| R39 | Header chứa bearer token khi bridge | Outbound/log đã redact |
| R40 | Metric có eventId label | Test phát hiện high-cardinality |
| R41 | Unsupported schemaVersion | Reject/transform hợp lệ |
| R42 | Destination credential expired | Alert, không retry vô hạn |
| R43 | RecoveryCallback nuốt exception | Test ack/commit phát hiện |
| R44 | Retry lồng nhau client/handler/broker | Tổng attempts được kiểm soát |
| R45 | Restart giữa DB commit và broker publish | Outbox phục hồi |
| R46 | Trace từ HTTP sang SFTP/Kafka | Correlation giữ, không leak secret |
| R47 | Unknown route → nullChannel | Negative test phải fail |
| R48 | Một event cần hai protocols | Fan-out theo recipient state |
| R49 | Default route thay đổi ở release | Contract test phát hiện |
| R50 | Registry unavailable | Fail safe, không bypass auth |

### Crash-point tests

Dừng ứng dụng có kiểm soát ở các điểm:

1. Sau inbound receive nhưng trước inbox/normalization.
2. Sau approved route decision nhưng trước adapter send.
3. Sau remote HTTP commit nhưng trước response.
4. Sau DB commit/outbox write nhưng trước broker publish.
5. Sau durable DLQ write nhưng trước source ack.
6. Sau source ack nhưng trước khi ghi telemetry.

Mỗi case cần xác định event **DONE/PARKED/OUTCOME_UNKNOWN/cần redelivery**, một chủ sở hữu xử lý và bằng chứng tránh mất/nhân đôi side effect. Không chỉ assert routeKey map đúng.

## 32. Case study: một hệ thống Order Hub định tuyến nhiều protocol

### Bối cảnh

Một doanh nghiệp vận hành **Order Hub** trên Spring Integration. Đơn hàng được nhận từ:

- HTTP webhook của kênh bán hàng;
- SFTP file batch từ đối tác;
- Kafka topic chứa order lifecycle events;
- JMS queue chứa yêu cầu cập nhật tồn kho.

Order Hub phải chọn:

- **HTTP ERP** cho lệnh tạo/cập nhật đơn hàng;
- **SFTP** cho file đối soát cuối ngày;
- **AMQP** cho thông báo kho vận;
- **Kafka** cho analytics;
- **JDBC** để ghi trạng thái đơn hàng nội bộ;
- **File** để xuất một số báo cáo nội bộ.

### Yêu cầu nghiệp vụ

1. Không gửi nhầm tenant A sang destination chỉ thuộc tenant B.
2. Một order event có stable ID; replay không tạo đơn hàng ERP trùng.
3. Raw HTTP headers không được quyền chọn URL/SQL/topic.
4. Event từ các nguồn khác nhau được chuẩn hóa về hợp đồng nội bộ.
5. Những đích one-way được theo dõi hoàn tất theo trạng thái riêng.
6. Lỗi transient được retry có giới hạn; lỗi permanent/unknown được lưu và điều tra.
7. Khi thay đổi route policy, các job pending phải có **pinned hoặc explicitly migrated decision**.
8. Không làm lộ Authorization token khi chuyển từ HTTP sang Kafka.
9. Có telemetry chứng minh đúng đích và status hoàn tất.
10. Một đối tác SFTP lỗi không được ngăn mọi luồng HTTP/Kafka khác.

### Luồng dữ liệu

~~~mermaid
flowchart TD
    HTTP["HTTP webhook"] --> N["Canonical normalizer"]
    SFTP["SFTP batch + poller"] --> N
    KIN["Kafka inbound"] --> N
    JMSIN["JMS inbound"] --> N
    N --> V["Validate identity/schema/eventId"]
    V --> P["Destination policy: tenant/eventType/version"]
    P --> R{"Protocol Router"}
    R -->|"HTTP"| H["ERP HTTP gateway"]
    R -->|"SFTP"| S["Render CSV + SFTP adapter"]
    R -->|"AMQP"| A["AMQP outbox publisher"]
    R -->|"KAFKA"| K["Kafka adapter"]
    R -->|"FILE"| F["File adapter"]
    R -->|"JDBC"| D["JDBC transaction handler"]
    R -->|"UNKNOWN / DENIED"| X["Rejected + audit + parking"]
    H --> O["Per-destination status"]
    S --> O
    A --> O
    K --> O
    F --> O
    D --> O
    X --> O
~~~

Các mũi tên không biểu thị mọi nguồn luôn đi mọi đích. **Destination policy** quyết định một hoặc nhiều recipients theo hợp đồng.

### Event mẫu

~~~json
{
  "eventId": "tenant-17:order-882:v3",
  "tenantId": "tenant-17",
  "eventType": "order.updated",
  "schemaVersion": "v3",
  "occurredAt": "2026-11-23T08:00:00Z",
  "payload": {
    "orderId": "order-882",
    "businessVersion": 3,
    "status": "CONFIRMED"
  }
}
~~~

Inbound adapter có thể cung cấp metadata phụ nhưng normalizer phải quyết định những field nào là đáng tin và phải loại bỏ những header transport-specific/secret không phù hợp.

### Sự kiện trong một ngày

| Mốc | Sự kiện | Rủi ro routing |
|---|---|---|
| 08:00 | Webhook hợp lệ yêu cầu đồng bộ ERP | Chọn HTTP đúng tenant, đảm bảo reply |
| 08:02 | Client giả header targetProtocol=JDBC | Unauthorized route |
| 08:04 | SFTP file chưa upload xong | Poller/partial file handling |
| 08:06 | Kafka nhận order.updated v3 | Normalization/version/ordering |
| 08:08 | HTTP ERP trả 503 | Retry handler đúng nhánh |
| 08:09 | ERP đã commit nhưng response mất | Outcome unknown/duplicate |
| 08:10 | AMQP publisher down | Outbox và per-recipient retry |
| 08:11 | Registry đổi ERP endpoint | Replay nên pin decision |
| 08:12 | Một message routeKey=KAFKA nhưng topic bị disable | Parking/alert, không NullChannel |
| 08:14 | JDBC gặp deadlock | Transaction retry đúng boundary |
| 08:16 | Bản sao cùng eventId được nhận lại | Inbox/dedupe |
| 08:20 | Consumer restart giữa publish và ack | At-least-once/idempotency |

### Nhiệm vụ thực hành

1. Phác thảo các inbound adapters và **trusted normalization boundary**.
2. Định nghĩa ít nhất 8 headers nội bộ gồm identity, route và correlation.
3. Chọn protocol branch cho sáu nghiệp vụ và giải thích tại sao routeKey không thể thay thế destinationAlias.
4. Dựng bảng **allowlist tenantId + eventType + destinationAlias**.
5. Viết chính sách khi routeKey missing/unknown, destination disabled hoặc registry unavailable.
6. Giải thích vì sao client tự đưa targetProtocol=JDBC phải bị từ chối.
7. Thiết kế payload transformer riêng cho HTTP, SFTP, Kafka và JDBC.
8. Xác định branch cần **reply**, branch chỉ cần **one-way completion**.
9. Với fan-out tới ERP + Kafka + SFTP, lưu per-recipient statuses thế nào?
10. Khi HTTP POST ERP commit nhưng response timeout, xử lý thế nào để không tạo order trùng?
11. Nếu route policy đổi trong lúc replay, chọn pinned hay migrated decision và vì sao?
12. Đề xuất 6 metrics và 10 integration tests quan trọng nhất.

### Hướng dẫn lời giải

**1. Normalization:** HTTP/SFTP/Kafka/JMS ingress xác thực nguồn, parse schema, chuẩn hóa businessEventId/tenantId/eventType/schemaVersion; policy resolver tra destination registry và sinh routeKey. Không dùng raw client-provided targetProtocol để bypass policy.

**2. Contract:** businessEventId, correlationId, sourceSystem, tenantId, eventType, schemaVersion, destinationAlias, targetProtocol, routeKey, routePolicyVersion, deadlineAt. Header từ broker/HTTP chỉ đóng vai trò source metadata khi được xác minh.

**3. Route branches:** HTTP cho ERP, SFTP cho export đối tác, AMQP cho kho, Kafka cho analytics, JDBC cho trạng thái nội bộ, File cho báo cáo. Mỗi branch có serializer, timeout, error handling và delivery semantics riêng.

**4. Authorization:** tenant-17 chỉ được route đến alias đã đăng ký. Nếu alias thuộc tenant-99, reject trước khi channel mapping. Kiểm quyền lại ở adapter handler nếu dữ liệu nhạy cảm.

**5. Missing/unknown:** routingRejectedChannel có reason code và durable recovery. Không default vào HTTP partner hoặc NullChannel.

**6. Spoofed header:** raw JDBC protocol/header không thay được quyền principal. Trusted routeKey phải do policy tạo.

**7. Transformer:** canonical event sang JSON ERP v2, CSV SFTP v2, Kafka key/value schema, JDBC prepared parameters. Router không tự chuyển các format.

**8. Reply semantics:** HTTP inbound gateway có request–reply; SFTP/Kafka/AMQP publish thường one-way, cần trạng thái xử lý riêng nếu nghiệp vụ yêu cầu biết đã hoàn thành.

**9. Fan-out:** ví dụ trạng thái ERP=DONE, Kafka=DONE, SFTP=RETRY_WAIT; chỉ retry SFTP, không gửi lại ERP/Kafka một cách mù. Dùng outbox/per-recipient state và idempotency.

**10. Unknown outcome:** query ERP bằng orderId/idempotency key, lưu OUTCOME_UNKNOWN cho tới khi xác định; chỉ retry POST cùng stable key nếu partner hỗ trợ contract đó.

**11. Route policy change:** pin destinationAlias và routePolicyVersion cho pending event khi cần audit/correctness; migration qua review có kiểm soát nếu muốn chuyển đích.

**12. Metrics và tests:** route_decisions_total, route_rejected_total, route_unauthorized_total, delivery_success_total, unknown_outcome_total, parked_backlog_age_seconds; test HTTP/SFTP/Kafka đúng channel, tenant isolation, header spoof, unknown route, payload mismatch, reply path, timeout-after-commit, retry-only-failed-recipient và restart.

### Phác thảo lưu trạng thái

~~~text
businessEventId = tenant-17:order-882:v3

INGESTED
   -> VALIDATED
   -> ROUTE_APPROVED
   -> PER_RECIPIENT_PENDING
       ERP_HTTP: DONE
       KAFKA_ANALYTICS: DONE
       SFTP_EXPORT: RETRY_WAIT
   -> DONE khi đủ các recipient bắt buộc

Nếu route không hợp lệ:
   -> ROUTING_REJECTED + reason + owner

Nếu remote outcome không rõ:
   -> OUTCOME_UNKNOWN + reconciliation

Nếu hết retry:
   -> PARKED/DLQ + audit + controlled redrive
~~~

Đừng đánh dấu toàn event DONE chỉ vì router gửi message đến một ExecutorChannel thành công.

## 33. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Router trực tiếp theo raw HTTP header | Header spoof, unauthorized routing | Normalize + authorize |
| protocol=HTTP nghĩa là dùng bất kỳ URL | SSRF/đích sai | destinationAlias + allowlisted registry |
| MessageChannel tên lấy từ client | Truy cập handler nội bộ ngoài ý muốn | Map key vào static approved channel |
| Default unknown route sang HTTP | Side effect sai đích | Rejected/parking |
| Unknown route đưa NullChannel | Silent data loss | Durable rejection/audit |
| Một canonical DTO gửi thẳng mọi adapter | Schema mismatch | Transformer per destination |
| JMS routing key và Spring routeKey bị coi là một | Sai broker destination | Hai tầng mapping tách biệt |
| Kafka topic name từ untrusted header | Publish không được phép | Topic alias + ACL |
| SFTP path ghép từ tenant raw string | Path traversal/tenant leak | Root allowlist + validation |
| JDBC table/SQL từ header | SQL injection/quyền sai | Prepared params + operation allowlist |
| Chỉ đo channel send success | Không biết outbound có hoàn tất | Business delivery status |
| Dùng one-way adapter làm reply cho HTTP gateway | Caller timeout | Reply/202-job contract |
| Mỗi inbound source có router policy riêng | Logic trùng, khó governance | Canonical normalizer + shared policy |
| Retry toàn flow khi một adapter fail | Lặp side effects đã DONE | Retry đúng handler/recipient |
| Replay luôn re-route bằng policy mới | Gửi sang đích khác bất ngờ | Pinned decision/migration |
| Fan-out không lưu trạng thái recipients | Không biết thiếu đích nào | Per-recipient status/outbox |
| Kafka offset commit khi chỉ enqueue async | Mất tác vụ sau crash | Durable handoff/ack boundary |
| JMS/AMQP exception bị nuốt | Ack message chưa xử lý | Rethrow/durable recovery |
| Không phân biệt exception route/delivery | Retry lỗi cấu hình vô ích | Failure stage + classifier |
| Log toàn MessageHeaders | Lộ token/credentials | Header whitelist/redaction |
| Không có test wrong tenant | Cross-tenant data leak | Authorization negative tests |
| Poller được xem như retry source vô điều kiện | Không nhận lại message đã claim | Durable metadata/parking |
| Destination registry không có version | Replay không thể kiểm toán | Policy version/audit |
| Dynamic routing không circuit breaker/bulkhead | Partner down kéo toàn platform | Isolation/backpressure |

## 34. Checklist triển khai

- [ ] Inbound adapters/gateways và các MessageChannels được vẽ rõ.
- [ ] Canonical message contract có businessEventId, tenantId, eventType và schemaVersion.
- [ ] Raw headers được tách khỏi trusted routing headers.
- [ ] Source identity/principal được xác thực trước khi quyết định đích.
- [ ] destinationAlias và operation được kiểm quyền theo tenant.
- [ ] targetProtocol chỉ thuộc allowlisted protocol enum.
- [ ] routeKey chuẩn hóa; không dùng raw arbitrary channel name.
- [ ] HeaderValueRouter/@Router/DSL mapping phù hợp, đã test wiring.
- [ ] Unknown/missing/unauthorized routes đi rejected/parking có reason.
- [ ] Không dùng NullChannel làm default cho message nghiệp vụ.
- [ ] HTTP URL, SFTP path, JMS/AMQP destinations, Kafka topics và JDBC operations dùng approved registry.
- [ ] Có transformer/serializer riêng theo destination/schemaVersion.
- [ ] Không copy Authorization/secret/PII headers tùy tiện qua protocol.
- [ ] One-way và request–reply được xác định ở từng nhánh.
- [ ] DirectChannel/ExecutorChannel/QueueChannel có error semantics được kiểm thử.
- [ ] Retry tại outbound handler/recipient phù hợp, không retry toàn orchestration mù.
- [ ] RetryPolicy/BackOffPolicy có timeout, maxAttempts và deadline tổng.
- [ ] Source ack/offset và transaction được đồng bộ với durable outcome.
- [ ] Inbox/outbox/idempotency hoặc reconciliation bảo vệ duplicate effects.
- [ ] Fan-out có per-recipient statuses và retry chỉ recipient thiếu.
- [ ] SFTP/File có ready marker, partial file handling và stable filenames.
- [ ] Kafka ordering và offset/commit đúng hợp đồng.
- [ ] JDBC transaction retry có ranh giới mới khi cần và unique business key.
- [ ] Route decision/routePolicyVersion được lưu nếu cần replay/audit.
- [ ] Destination registry thay đổi có owner, approval, canary, rollback.
- [ ] Registry unavailable không làm bypass authorization.
- [ ] Routing metrics và delivery metrics được theo dõi riêng.
- [ ] Có cảnh báo ROUTING_REJECTED, unauthorized routes, unknown outcomes và parked backlog.
- [ ] Có test contract, negative security, crash/restart, duplicate delivery và destination outage.
- [ ] Có runbook triage/replay cho từng protocol và bước xử lý lỗi.

## 35. Thuật ngữ và tài liệu tham khảo

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Message Router** | Mẫu chọn nhánh/channel theo quy tắc |
| **HeaderValueRouter** | Router của Spring Integration chọn channel từ giá trị header |
| **Content-Based Router** | Chọn đích theo nội dung message |
| **Recipient List Router** | Phân phối một message tới nhiều recipient đã chọn |
| **Dynamic Router** | Routing dựa trên policy/registry runtime |
| **Routing Slip** | Hành trình xử lý nhiều bước có thứ tự |
| **MessageChannel** | Đường truyền message giữa endpoints |
| **Inbound/Outbound adapter** | Kết nối nguồn/đích ngoài, thường one-way |
| **Gateway** | Thành phần tích hợp request–reply |
| **Route key** | Giá trị chọn nhánh routing |
| **Destination alias** | Định danh logic của đích đã đăng ký |
| **Policy version** | Phiên bản quy tắc định tuyến có thể kiểm toán |
| **Canonical message** | Hợp đồng message nội bộ chuẩn hóa |
| **Header spoofing** | Giả mạo metadata để tác động quyết định routing |
| **SSRF** | Ép ứng dụng gọi mạng tới đích không được phép |
| **Idempotency key** | Khóa ổn định nhận diện cùng business operation |
| **Outbox/Inbox** | Mẫu bảo toàn ý định gửi và/hoặc dedupe khi nhận |
| **DLQ/PARKED** | Trạng thái/đích giữ message lỗi để xử lý lại |
| **Redelivery** | Broker/source giao lại message |
| **Unknown outcome** | Remote có thể đã commit nhưng caller không biết |
| **ReplyChannel/ErrorChannel** | Kênh trả response/lỗi theo Spring Messaging semantics |
| **Backpressure** | Hạn chế upstream để tránh downstream bị quá tải |

### Tài liệu đọc tiếp

- **Spring Integration Reference — Routers:** HeaderValueRouter, Content-Based Router, recipient list, expressions, method routers.
- **Spring Integration Reference — Java DSL:** IntegrationFlow, channel mapping, router endpoint configuration.
- **Spring Integration Reference — Message Channels:** DirectChannel, ExecutorChannel, QueueChannel và PublishSubscribeChannel.
- **Spring Integration Reference — Message Headers and Header Enrichment:** metadata, replyChannel/errorChannel và cách truyền headers.
- **Spring Integration Reference — HTTP, File, SFTP, JMS, AMQP, Kafka, JDBC adapters/gateways:** đặc điểm kết nối mỗi protocol.
- **Spring Integration Reference — Error Handling and Message Handler Advice:** error channel, retry advice và recovery.
- **Spring Retry Reference:** RetryTemplate, RetryPolicy, BackOffPolicy.
- **Spring AMQP/Spring for Apache Kafka References:** acknowledgement, redelivery, offset và DLQ/DLT.
- **Enterprise Integration Patterns:** Message Router, Content-Based Router, Recipient List, Routing Slip, Idempotent Receiver và Dead Letter Channel.

## 36. Câu hỏi tự kiểm tra

1. Router chọn channel khác với adapter thực thi protocol ở điểm nào?
2. Vì sao routeKey=HTTP không đủ xác định đối tác nào sẽ nhận message?
3. Khi nào dùng HeaderValueRouter thay vì @Router method?
4. Vì sao raw X-Target-Protocol từ HTTP client không thể là trusted routeKey?
5. Nếu routeKey không được mapping, default sang HTTP có thể gây rủi ro gì?
6. Router một nhánh khác Recipient List Router thế nào?
7. Vì sao message.send thành công tới ExecutorChannel không chứng minh HTTP ERP đã xử lý?
8. Khi HTTP inbound gateway route sang SFTP adapter one-way, cần hợp đồng phản hồi gì?
9. Nếu JMS/Kafka source đã ack/commit trước khi outbound handler hoàn tất, hệ quả gì?
10. Tại sao một message bị retry sau khi route policy đổi có thể cần pinned decision?
11. Khi Kafka event offset 100 và 101 được route qua hai nhánh xử lý khác tốc độ, điều gì xảy ra với ordering?
12. Làm sao thử nghiệm tránh route nhầm tenant và tránh SSRF?
13. Khi một fan-out có HTTP=DONE, Kafka=DONE, SFTP=RETRY_WAIT, nên retry ở đâu?
14. Route policy/version nên được lưu ở đâu nếu message còn chờ delayed replay?
15. Tại sao NullChannel không phải một đường recovery mặc định cho unsupported route?

### Đáp án tóm tắt

1. Router chọn nhánh MessageChannel; adapter/transformer thực hiện I/O và chuyển đổi cần thiết.
2. Nhiều đích có cùng protocol; cần destinationAlias/tenant/eventType và authorization.
3. HeaderValueRouter hợp với một trusted header; method router tiện cho điều kiện nhiều chiều và policy.
4. Client có thể giả mạo; phải xác thực, chuẩn hóa và cho phép destination trước khi tạo key.
5. Message có thể gửi nhầm đích, gây side effect sai hoặc rò rỉ dữ liệu.
6. Router một nhánh chọn một đích; Recipient List Router có thể gửi nhiều đích và cần tracking.
7. Async channel chỉ chứng minh đã giao vào executor; remote handler có thể chưa chạy.
8. Cần response/job ID/accepted status theo contract; không để caller chờ reply không tồn tại.
9. Có nguy cơ mất business event nếu process crash hoặc outbound fail.
10. Registry đổi có thể khiến replay gửi sang đích khác, tạo duplicate/sai nghiệp vụ.
11. Event sau có thể được xử lý trước event trước; cần ordering/version guard.
12. Negative tests về tenant permissions, raw URL/path/topic/channel injection và allowlist.
13. Chỉ retry SFTP recipient; giữ DONE của HTTP/Kafka và dùng stable event ID.
14. Trong durable message/job state hoặc audit store gắn eventId/approved destination/policy version.
15. NullChannel hủy message; unknown route cần rejected/parking/alert và bằng chứng.

**Điểm cần ghi nhớ:** **Router theo protocol hoặc header** trong Spring Integration là **cơ chế lựa chọn MessageChannel dựa trên một hợp đồng định tuyến đáng tin**, không phải thành phần tự chuyển đổi mọi giao thức hay bảo đảm mọi delivery thành công. Một thiết kế đáng tin luôn **normalize/authorize trước route**, ánh xạ vào **approved destinations**, biến đổi payload đúng contract, bảo vệ **request–reply/transaction/ack/idempotency**, xử lý route không hợp lệ bằng **rejected/parking** và duy trì **policy version + observability** để retry/replay an toàn.









