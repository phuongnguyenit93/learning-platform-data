# Header không được truyền qua boundary trong Spring Integration

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt rõ **boundary nội bộ giữa các MessageHandler**, **boundary thread/queue**, **boundary lưu trữ/serialize**, **boundary process/service**, **boundary protocol**, **boundary bảo mật/tenant** và **boundary phản hồi request/reply**.
- Giải thích vì sao Spring Integration thường **propagate headers** khi một message-producing endpoint tạo output mới; không mặc định headers bí mật, internal channel objects hay source-specific metadata đã bị loại.
- Liệt kê các nhóm headers **không nên truyền nguyên trạng**: Spring `replyChannel`/`errorChannel`, `id`/`timestamp` dùng sai mục đích, broker ACK/channel/delivery tags, Kafka offset/ConsumerRecord metadata, JMS/AMQP received-only fields, token/cookie/PII, raw tenant/role claims, socket/session objects, temporary processing metadata và các header có kiểu không serializable.
- Sử dụng `HeaderFilter`, `MessageBuilder.removeHeader/removeHeaders`, `AbstractMessageProducingHandler.setNotPropagatedHeaders(...)` và Java DSL `notPropagatedHeaders(...)` **đúng vị trí và đúng giới hạn**.
- Phân biệt `notPropagatedHeaders` với `readOnlyHeaders`: cấu hình read-only để hạn chế copy/override khi tạo message **không tương đương** một policy allowlist bảo mật ở network boundary.
- Hiểu trường hợp transformer trả một **payload** hoặc trả nguyên một **Message<?>** dẫn đến quy tắc propagation khác nhau; giải thích vì sao bridge/router không chịu cùng quy tắc `notPropagatedHeaders` của message-producing handler.
- Cấu hình outbound `HeaderMapper`/Spring Kafka header mapper để tạo **allowlist theo giao thức**, phân biệt mapping header với payload conversion, destination routing và ACK.
- Giải thích tại sao `HeaderChannelRegistry` có thể giúp chuyển Spring `MessageChannel` sang token trong một số luồng lưu trữ/truyền message, nhưng **không phải** phương tiện chuyển quyền điều khiển reply/error cho external client tùy ý hoặc tạo reply bền xuyên restart.
- Thiết kế policy chống **lộ credentials, cross-tenant access, SSRF, header injection, replay/dedup sai ID, stale ACK handles, serialization lỗi và route override**.
- Viết JUnit/IntegrationFlow tests, kiểm tra headers tại trước và sau boundary, xác minh wire metadata tại HTTP/JMS/AMQP/Kafka và xử lý retry/recovery/lifecycle.

Bài thuộc chương **Header message** của module **SPRING_INTEGRATION_ADAPTERS**. Trong phạm vi module, chúng ta kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller, `MessageChannel` và thực hành File, SFTP, HTTP, JMS, AMQP, Kafka, MongoDB/cơ sở dữ liệu. Vì thế, việc giới hạn header phải gắn với **hợp đồng message, quyền truy cập, đường đi ACK/reply, lỗi và vòng đời kết nối**.

> **Phạm vi:** các ví dụ sử dụng Java 17+, Spring Boot 3.x và Spring Integration 6.x theo BOM phù hợp. Một số Java DSL overloads và behavior có thể khác ở Spring Integration 7.x/Spring Kafka 4.x. Không dùng API nào mà chưa đối chiếu Javadoc đúng version. Tất cả URI, IDs, partner và database đều là dữ liệu minh họa.

## 1. Vấn đề: message vẫn “đúng payload” nhưng headers gây sự cố

Hệ thống HTTP inbound nhận order từ đối tác:

~~~http
POST /orders/events HTTP/1.1
Content-Type: application/json
Authorization: Bearer <redacted>
X-Tenant-Id: tenant-a
X-Role: admin
X-Event-Id: evt-1001
X-Trace-Id: tr-9c

{"eventId":"evt-1001","orderId":"ord-101","status":"PAID"}
~~~

Giả sử một adapter/gateway tạo Spring Message có:

~~~text
payload:
  order event JSON

headers:
  id = <Spring UUID>
  timestamp = <Spring epoch millis>
  replyChannel = <temporary MessageChannel>
  errorChannel = <error flow MessageChannel>
  Authorization = "<token>"
  X-Tenant-Id = "tenant-a"
  X-Role = "admin"
  X-Event-Id = "evt-1001"
  X-Trace-Id = "tr-9c"
  sourceSystem = "partner-http"
~~~

Nếu application chuyển message này qua nhiều handlers rồi đưa tiếp tới **JMS/Kafka/AMQP/HTTP/SFTP**, việc propagate header “nguyên trạng” có thể:

1. **Rò rỉ token** nguồn sang đối tác không được cấp quyền.
2. Cho một external user **ghi đè tenant/role** nếu business handler tin giá trị header.
3. Truyền Spring `MessageChannel` object như JMS property, gây serialization/conversion exception.
4. Gửi lại broker delivery/ACK metadata ở một context nơi nó đã **hết hiệu lực**.
5. Dùng Spring `id` làm idempotency key, tạo bản ghi trùng khi redelivery/rebuild.
6. Phản chiếu RabbitMQ `x-*` federation metadata, làm broker xử lý reply sai.
7. Cho một raw header quyết định Kafka topic, HTTP URL hay SFTP directory, gây **unauthorized routing/SSRF/path traversal**.
8. Giữ debug/attempt headers quá lâu, khiến audit/metrics và recovery sai.

**Header boundary** là nơi ta quyết định metadata nào được phép **tiếp tục tồn tại**, metadata nào chỉ có nghĩa **trong một đoạn flow**, và metadata nào phải được **chuyển thành application contract đã validate**.

## 2. “Boundary” không chỉ là HTTP network boundary

Có nhiều loại ranh giới với quy tắc khác nhau:

| Boundary | Ví dụ trong Spring Integration | Rủi ro nếu copy header |
|---|---|---|
| **Xử lý nội bộ** | Transformer → ServiceActivator | Internal token/temporary flags bị truyền ngoài phạm vi cần |
| **Thread** | DirectChannel → ExecutorChannel | ThreadLocal/ACK handle/session context không còn đúng |
| **Queue/store** | QueueChannel backed by MessageStore | Object header không serializable hoặc stale khi restore |
| **Process/restart** | MessageStore → new app instance | Temporary replyChannel bean/object không thể resolve |
| **Protocol** | Message → HTTP/JMS/AMQP/Kafka | Type/format/semantics không tương thích |
| **Security/tenant** | Public HTTP ingress → internal tenant-aware service | External header bị nâng lên quyền trusted |
| **External partner** | Internal event → partner API | Leak credentials, PII, topology |
| **Request/reply** | Gateway request → response | replyChannel/correlation/response metadata bị giả mạo |
| **Observability** | Message → logs/metrics/DLQ | Token/PII hoặc high-cardinality dữ liệu bị lộ |
| **Storage/business** | Message → MongoDB/JDBC row/document | Header kỹ thuật bị lưu lâu, hoặc business ID không được lưu |

Một **DirectChannel** boundary không giống một **Kafka broker** boundary. Lọc sai vị trí có thể làm mất headers cần thiết cho routing nội bộ, hoặc lọc quá muộn sau khi secret đã tới client.

### 2.1. Ví dụ chia các zone

~~~mermaid
flowchart LR
  U["Untrusted input<br/>HTTP/JMS/SFTP"] --> A["Ingress authentication<br/>+ input validation"]
  A --> R["Raw Spring Message<br/>external metadata"]
  R --> N["Normalize / sanitize<br/>trust boundary"]
  N --> B["Business Message<br/>trusted app headers"]
  B --> S["Create outbound DTO<br/>minimal metadata"]
  S --> P["Protocol HeaderMapper<br/>destination allowlist"]
  P --> O["HTTP / Kafka / JMS / AMQP"]
  B --> D["Persistent inbox/outbox<br/>business ID + payload"]
~~~

Ở sơ đồ:

- **Ingress** xác thực/kiểm tra input.
- **Normalizer** chuyển external keys thành canonical application keys.
- **Business flow** chỉ dùng trusted state và dữ liệu đã validate.
- **Outbound serializer/HeaderMapper** chọn những headers được phép gửi **cho từng đích**.
- **Persistence** lưu business fields tối thiểu, không dump nguyên MessageHeaders.

## 3. Spring Integration mặc định propagate headers thế nào?

Theo Spring Integration Reference, phần lớn **message-producing endpoints** khi xử lý rồi tạo output mới sẽ **copy incoming headers sang output** nếu output chưa có key đó. Đặc biệt:

- Nếu transformer/service method trả về **payload** mới, framework thường tạo Spring Message mới và tiếp tục propagate incoming headers.
- Nếu transformer trả về **một `Message<?>` hoàn chỉnh**, user/framework xem message đó là output do code tạo; developer phải chủ động định nghĩa headers của output.
- Khi incoming header key đã có ở output, output value được ưu tiên; không overwrite bằng value từ input theo default propagation.
- `MessageHeaders.ID`/`TIMESTAMP` là core read-only headers, thường được tạo theo message mới chứ không phải user-supplied arbitrary values.

**Điểm quan trọng:** automatic propagation **không phải một security policy**. Nếu một service chỉ đổi String payload thành DTO, raw Authorization hoặc client-controlled X-Role có thể vẫn tồn tại ở headers downstream, trừ khi developer lọc/bỏ chúng.

### 3.1. Ví dụ “chỉ đổi payload” vẫn mang headers

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.handler.annotation.Payload;

public final class EventTransformer {

    @Transformer(inputChannel = "rawOrders",
                 outputChannel = "normalizedOrders")
    public String transform(@Payload String payload) {
        return payload.trim();
    }
}
~~~

Nếu source message chứa `X-Untrusted-Role`, một transformer chỉ trả String **không tự bảo đảm xóa** header đó. Phải có `HeaderFilter`/propagation policy hoặc tự xây message sạch.

### 3.2. Transformer trả Message là một trường hợp khác

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> toCanonicalMessage(
        Message<String> original) {

    String canonicalBody = original.getPayload().trim();

    return MessageBuilder.withPayload(canonicalBody)
        .setHeader("sourceSystem", "partner-http")
        .setHeader(
            "businessEventId",
            verifiedBusinessEventId)
        .setHeader(
            "trustedTenantId",
            authorizedTenantId)
        .build();
}
~~~

Đây là **service method fragment**: `verifiedBusinessEventId`, `authorizedTenantId` phải được xác minh trước, và khi sử dụng như transformer, return type phải là `Message<?>` thực sự. Vì tạo message **từ đầu** bằng `withPayload(...)`, đoạn code **không tự copy tất cả headers** của original. Tuy vậy, cần kiểm tra endpoint wiring và propagation behavior đúng version để bảo đảm output không được merge ngoài dự kiến.

### 3.3. Header values vẫn có thể mutable

Spring `MessageHeaders` cung cấp map interface không sửa tùy tiện, nhưng value có thể là `List`, `Map` hoặc object mutable. Copy reference một value không tương đương deep-copy an toàn qua threads/processes. Trước khi serialize, chuẩn hóa thành String/byte[]/immutable DTO hoặc bỏ hẳn.

## 4. Ma trận: nhóm headers thường không được truyền qua boundary

**Đây là policy kiến trúc, không phải danh sách framework tự động cấm 100%.** Tùy destination có ngoại lệ do thiết kế chủ động cho phép.

| Header hoặc nhóm | Không nên vượt qua boundary nào? | Lý do / phương án thay thế |
|---|---|---|
| `replyChannel` là `MessageChannel` object | Broker, persistent store, remote service | Object tham chiếu runtime; dùng gateway contract hoặc registry nội bộ có TTL |
| `errorChannel` là `MessageChannel` object | Broker, external service, restart | Internal routing object; lưu durable error event thay vì object |
| `id` / `timestamp` | External business identity | Spring message metadata, không phải business key; dùng `businessEventId` |
| `routingSlip` / runtime route state | External endpoint | Tránh cho client điều khiển route nội bộ |
| `Authorization`, Cookie, refresh token | Partner khác, logs/DLQ | Secret/credential theo audience; outbound auth riêng |
| `trustedTenantId`, internal roles | Unauthorized tenant/partner | Tenant isolation và least privilege |
| Raw `X-Tenant-Id` / `X-Role` | Trusted business context | Chưa authenticated; chỉ dùng sau validate/authorization |
| JMS delivery/session/provider handles | Ngoài JMS listener/session | Hết hiệu lực; broker quản lý |
| AMQP deliveryTag/channel/redelivered/received exchange | HTTP/Kafka/JMS hoặc AMQP publish mới | Received-only metadata, không phải outbound control |
| Kafka received offset/partition/topic/consumer ACK | External general-purpose headers | Gắn với ConsumerRecord, consumer group/lifecycle |
| TCP connection ID / socket | Restart hoặc partner khác | Runtime connection context |
| SFTP/FTP session / raw remote path | External routing/persistence | Authentication/path scope và traversal risk |
| Spring error `ErrorMessage.payload(Throwable)` | Public API, unprotected DLQ/log | Exception chứa stack, secrets, PII; dùng safe error code |
| `MessageHistory`/debug trace | Public wire/log không kiểm soát | Leaks internal flow topology |
| `contentType` chưa phù hợp body | Protocol destination | Kiểm tra converter/body, không copy mù |
| Java `Class<?>`, `MessageChannel`, `InputStream` objects | JMS/Kafka/JSON serialization | Unsupported/non-serializable/mutable runtime state |
| Internal retry attempts/lease owner | Downstream partner khác | Tránh để stale worker state ảnh hưởng nghiệp vụ |
| `spring_json_header_types` không trusted | Cross-trust Kafka boundary | Type metadata cần schema/trusted packages |

### 4.1. Ba mức quyết định

Khi review một header cụ thể, chọn một trong ba loại:

1. **DROP** — header chỉ có nghĩa trong source/runtime hoặc chứa secret không cần thiết.
2. **TRANSFORM** — chuyển external/broker-specific value thành application field đã validate (ví dụ `X-Partner-Event-Id → businessEventId`).
3. **ALLOW** — chuyển nguyên value **chỉ sau validation** và chỉ đến destination mà hợp đồng cho phép.

Ví dụ `businessEventId` thường được **ALLOW** sang Kafka/JMS/HTTP, nhưng phải canonicalize type/length và scope. `Authorization` inbound thường phải **DROP** khi ra outbound; outbound service có thể tự thêm token **mới** đúng partner audience.

### 4.2. Không có khái niệm “copy cả MessageHeaders cho an toàn”

Một `Message<?>` có thể mang cả:

~~~text
Reply routing:
  replyChannel, errorChannel

Business:
  businessEventId, schemaVersion

Transport:
  kafka_receivedTopic, kafka_offset, amqp_deliveryTag

Security:
  Authorization, X-Tenant-Id, principal/session

Observability:
  traceId, history

Infrastructure:
  MessageChannel, ClientSession, acknowledgment object
~~~

Nếu gửi toàn bộ map này sang một protocol khác, các giá trị có **kiểu, quyền truy cập và vòng đời khác nhau**. Cách an toàn là xây **destination-specific contract**.

## 5. Cơ chế 1 — HeaderFilter trong Spring Integration flow

`HeaderFilter` là một Enterprise Integration Pattern loại một số header keys khỏi Spring Message trước khi message đi tiếp.

### 5.1. Java DSL

~~~java
package example.headerboundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class InboundBoundaryFlow {

    @Bean
    public IntegrationFlow sanitizeInboundFlow() {
        return IntegrationFlow.from("rawInbound")
            .headerFilter(
                "Authorization",
                "Cookie",
                "X-Untrusted-Role",
                "X-Untrusted-Tenant")
            .channel("sanitizedInbound")
            .get();
    }
}
~~~

Đoạn này tạo **một flow** từ `rawInbound` tới `sanitizedInbound`. Nó chỉ loại **đúng tên keys**; nếu mapper đã đổi casing/tên, cần filter đúng normalized key. Không dùng Java DSL filter để thay thế HTTP authentication đã phải chạy **trước đó**.

### 5.2. XML HeaderFilter

~~~xml
<!-- Cần xmlns:int và channel beans tương ứng. -->
<int:header-filter
    input-channel="rawInbound"
    output-channel="sanitizedInbound"
    header-names="Authorization,Cookie,X-Untrusted-Role,X-Untrusted-Tenant"/>
~~~

Đây là phương án thay thế Java DSL, không cấu hình cả hai cùng lọc một flow nếu không có lý do rõ.

### 5.3. Giới hạn của HeaderFilter

- **Không xóa header ở hệ thống nguồn**; nó lọc Spring Message ở bước xử lý được đặt.
- **Không cấm producer khác bổ sung lại cùng header** ở bước sau.
- **Không tạo allowlist tự động**. Một header mới lạ có thể lọt qua danh sách blocklist nếu không được nêu tên.
- **Không xử lý mọi boundary**; nếu có nhánh route khác không đi qua filter, nhánh đó vẫn có headers gốc.
- **Không sửa nested payload**. Nếu token nằm trong JSON body, lọc MessageHeaders không loại token trong body.
- **Không phải chỗ thay đổi `id`/`timestamp`** theo ý muốn; hai core headers là read-only và có giới hạn cấu hình riêng.
- **Không thể thay authentication/authorization**: raw tenant/role có thể đã ảnh hưởng route trước khi filter chạy.

**Dùng blocklist để bảo vệ một flow nội bộ đã biết headers; dùng allowlist/dựng DTO sạch ở boundary external hoặc multi-tenant.**

## 6. Cơ chế 2 — MessageBuilder, removeHeader và xây message sạch

Khi cần clone một message rồi loại các headers:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> stripSecrets(Message<String> input) {
    return MessageBuilder.fromMessage(input)
        .removeHeader("Authorization")
        .removeHeader("Cookie")
        .removeHeader("X-Untrusted-Role")
        .removeHeader("debugInternal")
        .build();
}
~~~

`fromMessage(input)` bắt đầu từ headers của input; ta loại từng key mong muốn. Đây là **blocklist**. Nếu có một header mới không được liệt kê, nó có thể vẫn được copy.

### 6.1. Khi boundary yêu cầu allowlist mạnh hơn

Tạo **message mới từ payload** và copy đúng một vài fields:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> toPartnerMessage(
        Message<String> original,
        String trustedEventId,
        String sanitizedTraceId) {

    return MessageBuilder.withPayload(original.getPayload())
        .setHeader("businessEventId", trustedEventId)
        .setHeader("appTraceId", sanitizedTraceId)
        .setHeader("schemaVersion", 2)
        .build();
}
~~~

**Lợi ích:** output chỉ có business/application headers được phép (cộng core framework headers). **Điều kiện:** `trustedEventId` và `sanitizedTraceId` được validate; developer không truyền `replyChannel` hay `errorChannel` từ input vào builder mới.

### 6.2. MessageBuilder không bảo vệ khỏi self-contradiction

Nếu bạn viết:

~~~java
Message<?> bad = MessageBuilder.withPayload(payload)
    .setHeader("businessEventId", rawHeaderValue)
    .build();
~~~

thì tuy đã tạo message mới, app vẫn **đưa dữ liệu không tin cậy** vào trusted contract. Dựng message sạch chỉ an toàn nếu có validation/authorization, không phải chỉ vì method là `withPayload()`.

### 6.3. Header value có thể chứa secret dù tên không nhạy cảm

Ví dụ `X-Trace-Id` bị client dùng để gửi một chuỗi token hoặc JSON PII. Allowlist **tên** không đủ: phải validate type, charset, maximum length, semantics và log policy của **value**. Không dump `message.getHeaders().toString()` trong production logger.

## 7. Cơ chế 3 — notPropagatedHeaders trên message-producing handlers

Spring Integration hỗ trợ loại một tập headers khỏi **automatic propagation** của các handler **tạo output messages**.

### 7.1. Java DSL với ConsumerEndpointSpec

~~~java
package example.headerboundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class NotPropagatedFlow {

    @Bean
    public IntegrationFlow redactAtServiceActivator() {
        return IntegrationFlow.from("rawEvents")
            .handle(
                String.class,
                (payload, headers) -> payload.trim(),
                endpoint -> endpoint.notPropagatedHeaders(
                    "Authorization",
                    "Cookie",
                    "X-Internal-*",
                    "debug*"))
            .channel("normalizedEvents")
            .get();
    }
}
~~~

Điểm mấu chốt: khi handler ở ví dụ trả về **payload**, framework tạo message output. `notPropagatedHeaders(...)` ngăn những header names/patterns được chọn **trong bước copy tự động** từ input sang output.

### 7.2. Java API trên handler

Handler kế thừa `AbstractMessageProducingHandler` có thể hỗ trợ:

~~~java
handler.setNotPropagatedHeaders(
    "Authorization", "X-Internal-*");

// Nếu version cho phép thêm thay vì thay danh sách:
handler.addNotPropagatedHeaders("debug*");
~~~

Đây là **fragment**: `handler` là bean đúng kiểu API, và method availability phải xem theo version. Không áp dụng API này lên bất kỳ MessageHandler một chiều nào mà không tạo outbound message.

### 7.3. XML service activator

~~~xml
<!-- Khi ServiceActivator tạo output message,
     những pattern chỉ định không được copy tự động. -->
<int:service-activator
    input-channel="rawEvents"
    output-channel="normalizedEvents"
    ref="eventTransformer"
    method="normalize"
    not-propagated-headers="Authorization,Cookie,X-Internal-*,debug*"/>
~~~

Dùng fragment này **thay thế** Java DSL ở mục 7.1. Bean `eventTransformer.normalize(...)` phải có logic phù hợp, và XML namespaces phải đúng version.

### 7.4. Pattern và trường hợp "*"

Các patterns dùng kiểu simple pattern, ví dụ:

~~~text
Authorization     khớp đúng key
X-Internal-*      khớp mọi key bắt đầu bằng X-Internal-
*Token            khớp key kết thúc bằng Token
*Secret*          khớp key chứa Secret
*
                  trường hợp đặc biệt: không propagate header nào
~~~

Tùy phiên bản, pattern matcher hỗ trợ prefix/suffix/infix match theo `PatternMatchUtils`. Nếu `"*"` được dùng làm pattern, **không header nào được copy tự động**; các pattern khác có thể bị bỏ qua trong trường hợp này.

**Hãy thận trọng với `"*"`**: nó có thể loại cả businessEventId/correlation headers mà output vẫn cần. Chỉ dùng nếu business code chủ động xây lại full contract.

### 7.5. Không áp dụng cho bridge/router như với service-activator

Tài liệu Spring Integration nêu rõ `notPropagatedHeaders` **không áp dụng** cho những endpoints **không tạo sửa message**, ví dụ bridges và routers. Chúng thường forward **chính message hiện tại** hoặc chuyển địa chỉ đích, không tạo copy qua cơ chế propagation này.

Nếu cần bảo đảm header bị lọc trước router hoặc bridge, đặt **HeaderFilter**/**Transformer** hoặc dựng message sạch **trước** đoạn route đó.

### 7.6. Propagation khác HeaderMapper

- `notPropagatedHeaders` quyết định header nào **không copy từ input sang output trong một endpoint nội bộ cụ thể**.
- `HeaderMapper` quyết định header nào được **convert ra metadata của protocol đích**.

Có thể cần cả hai. Một message đã đi qua router với header nhạy cảm vẫn có thể tới outbound adapter nếu chỉ cấu hình `notPropagatedHeaders` ở một service-activator khác không nằm trên path đó.

## 8. Cơ chế 4 — readOnlyHeaders không phải outbound security allowlist

Trong Spring Integration, `MessageHeaders.ID` và `MessageHeaders.TIMESTAMP` được xem là **read-only** theo default builder/framework. Developer không nên override chúng để ép business event ID hay timestamp của nguồn.

Spring Integration còn cho phép chỉ định read-only headers bổ sung thông qua:

- `MessageBuilder.readOnlyHeaders(...)` khi xây message trong một số use cases.
- Thuộc tính global `spring.integration.readOnly.headers` / `readOnlyHeaders` trong `META-INF/spring.integration.properties` theo version và factory.

Mục tiêu của nhóm cơ chế này là **hạn chế việc copy/override một số headers khi message được dựng lại**; nó **không tự đóng vai trò network allowlist**.

### 8.1. Không nhầm ba công cụ

| Công cụ | Phạm vi | Câu hỏi nó giải quyết |
|---|---|---|
| `HeaderFilter` | Bước flow cố định | Loại keys nào khỏi Spring Message trước downstream? |
| `notPropagatedHeaders` | Automatic header copy của output-producing handler | Keys/patterns nào không được truyền từ input sang **output của handler**? |
| `readOnlyHeaders` | Message builder/factory | Header nào không nên được copy/override trong thao tác xây dựng message theo builder semantics? |
| `HeaderMapper` | Protocol boundary | Headers nào được chuyển ra HTTP/JMS/AMQP/Kafka wire metadata? |
| DTO/explicit fields | External/stored business contract | Chỉ dữ liệu nghiệp vụ nào có quyền rời service? |

**Không thay allowlist bảo mật bằng một flag global readOnlyHeaders**. Lọc nhầm ở builder có thể phá business flow; không lọc ở outbound mapper có thể leak dữ liệu khác.

### 8.2. HeaderFilter và core headers

Không cố dùng `HeaderFilter` hoặc `HeaderEnricher` để ép `id`/`timestamp` giá trị tuỳ ý. Spring Integration Reference mô tả rằng với `DefaultMessageBuilderFactory` các core names này được bảo vệ và cấu hình filter/enricher cố can thiệp có thể dẫn đến lỗi khởi tạo (tùy version).

Nếu cần giữ **ID nguồn**, đặt key mới `sourceMessageId` hoặc `businessEventId`; nếu cần giữ **thời gian sự kiện**, dùng `occurredAt`, không override Spring Message timestamp.
## 9. ReplyChannel, ErrorChannel và HeaderChannelRegistry

Spring Messaging định nghĩa:

~~~java
MessageHeaders.REPLY_CHANNEL   // "replyChannel"
MessageHeaders.ERROR_CHANNEL   // "errorChannel"
~~~

Giá trị có thể là `MessageChannel` instance hoặc String do framework hiểu như tên channel/registry token. Một `MessageChannel` object là **tham chiếu runtime của ApplicationContext**, không phải “địa chỉ reply” để gửi qua Kafka/JMS/HTTP rồi tự sử dụng ở process khác.

### 9.1. Trong gateway nội bộ, có thể cần giữ

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Spring Gateway
    participant H as Service Handler
    participant R as Temporary Reply Channel
    C->>G: request
    G->>H: Message(replyChannel=R)
    H->>R: reply
    R-->>G: response
    G-->>C: result
~~~

Nếu loại `replyChannel` **quá sớm** trong request/reply flow, handler có thể không tìm thấy nơi trả lời. Không có quy tắc “xóa mọi replyChannel ngay khi nhận”. Phải đặt filter ở **boundary thực sự không còn cần internal reply**.

### 9.2. Khi đi qua persistent queue hoặc restart

~~~text
gateway → Message(replyChannel=<temporary object>)
        → QueueChannel backed by MessageStore
        → application restart / worker khác
        → handler hoàn tất
        → temporary reply channel cũ ở đâu?
~~~

Serialization có thể thất bại, hoặc object được restore không còn đại diện cho channel cũ. Kể cả khi có tên, gateway caller có thể đã timeout từ lâu.

### 9.3. HeaderChannelRegistry là giải pháp có phạm vi

Spring Integration có `HeaderChannelRegistry` và HeaderEnricher để biến `replyChannel`/`errorChannel` dạng `MessageChannel` thành **String/token có registry mapping**, dùng cho một số luồng cần serialize headers hoặc gửi qua JMS.

Ví dụ XML từ Spring Integration Reference:

~~~xml
<int:header-enricher
    input-channel="beforeStore"
    output-channel="afterRegistry">
    <int:header-channels-to-string
        time-to-live-expression="120000"/>
</int:header-enricher>
~~~

Giải pháp này đòi registry có lifecycle/TTL phù hợp. **Không** hiểu token như một protocol reply bền xuyên services/restarts:

- Registry mặc định thường **in-memory**, entry có thể hết hạn.
- Gateway request/temporary reply channel cũng có timeout riêng.
- Một String token không được xem như tên bean routing do external client được quyền tự gán.
- Muốn durable request/reply xuyên systems, dùng **correlation ID + reply queue/topic/database status** đã thiết kế và authorize.

### 9.4. Quyết định với replyChannel/errorChannel

| Bối cảnh | Policy |
|---|---|
| Gateway đồng bộ đang đợi reply | Giữ trong đúng lifecycle |
| Output event đưa vào Kafka/JMS one-way | DROP runtime channel objects |
| HTTP outbound tới partner | DROP, HTTP gateway quản response riêng |
| Persistent store có temporary reply | Chỉ dùng registry/token theo TTL nếu app design cho phép |
| Message lưu BSON/JDBC | Lưu business correlation, không serialize channels |
| Async RPC xuyên process/restart | Durable correlation protocol, không temporary channel |

External `replyChannel`/`errorChannel` header được người dùng gửi đến **không được** điều khiển internal routing bean/channel.

## 10. Kafka consumer metadata: không đem ACK và offset sang nơi khác

Spring Kafka và Spring Integration Kafka có thể thêm:

~~~java
org.springframework.kafka.support.KafkaHeaders
~~~

Headers phổ biến: `KafkaHeaders.RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `OFFSET`, `RECEIVED_KEY`, `ACKNOWLEDGMENT` trong manual ACK mode và các delivery attempt/consumer metadata tùy container.

### 10.1. Những thứ không nên forward

| Kafka header | Không nên dùng như | Vì sao |
|---|---|---|
| ACK callback/object | Serialized JMS/HTTP/Kafka header | Runtime object chỉ hợp lệ trong listener lifecycle |
| Consumer instance | Persistence/wire header | Context/connection không portable |
| Received partition/offset | Business event ID | Offset theo topic-partition, không globally unique |
| Received topic | Outbound destination tùy ý | Có thể vượt topic ACL/đường đi dữ liệu |
| Delivery attempt | Durable business completion | Đây chỉ là trạng thái retry của tầng nhận |
| JSON class type hints | Trusted domain class | Có thể gây nguy hiểm khi deserialize |

Kafka offset có thể ổn định cho **một record trong topic-partition**, nhưng khi republish sang topic khác hoặc tạo record mới, offset khác. Nếu cần idempotency, dùng `businessEventId` trong event contract, không dựa Spring Message ID hoặc offset.

### 10.2. KafkaHeaderMapper có exclusions nhưng không phải security policy đầy đủ

Spring Kafka `SimpleKafkaHeaderMapper`/JSON mapper thường tránh chuyển một số core headers `id`, `timestamp` và Kafka ConsumerRecord metadata thành raw headers, **nhưng không mặc định loại mọi arbitrary secret/custom PII header**.

Ví dụ outbound allowlist:

~~~java
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;

SimpleKafkaHeaderMapper mapper =
    new SimpleKafkaHeaderMapper(
        "!id",
        "!timestamp",
        "businessEventId",
        "appTraceId",
        "schemaVersion");
~~~

Mẫu này chỉ tạo policy tên. Với `SimpleKafkaHeaderMapper`, các value muốn xuất lên Kafka wire thường cần `byte[]`; cần convert String sang UTF-8 bytes hoặc cấu hình mapper raw String behavior tương ứng.

**Không xuất** `KafkaHeaders.ACKNOWLEDGMENT` hoặc consumer object; chúng không phải metadata nghiệp vụ.

### 10.3. Typed Kafka headers

JSON header mapper có thể dùng `spring_json_header_types`. Nếu header từ external broker, không cho phép user điều khiển arbitrary Java type to deserialize:

- Chọn trusted packages/schema registry có kiểm soát.
- Giới hạn kích thước và nesting.
- Không tin class name như bằng chứng xác thực.
- Không chuyển arbitrary object graphs sang JMS/HTTP.
- Trong Kafka → JMS/HTTP, tạo canonical application DTO/header values trước outbound.

### 10.4. ACK vẫn thuộc listener

Kafka ACK/offset commit được quản lý bởi container/transaction/error policy. Copy một ACK callback sang message lưu bền/worker process khác **không bảo đảm callback còn hợp lệ**. Nếu flow bất đồng bộ, thiết kế durable inbox và ACK tại đúng stage; test rebalance/shutdown.

## 11. JMS: received-only metadata và provider-owned fields

| JMS metadata | Ý nghĩa | Quy tắc |
|---|---|---|
| `JMSMessageID` | ID do provider gán khi gửi | Không copy như business key |
| `JMSRedelivered` | Broker báo delivery có thể là redelivery | Không tự set để tạo redelivery |
| `JMSDestination` | Nơi message đã được giao | Outbound destination theo policy server |
| `JMSExpiration` | Mốc hết hạn message đã gửi | Không copy mù thành TTL của message mới |
| `JMSDeliveryMode`/Priority | QoS của producer | Điều chỉnh qua send API/endpoint |
| `JMSCorrelationID` | Protocol request/reply correlation | Chỉ map khi contract cần |
| `JMSReplyTo` | JMS reply Destination | Không cho client chọn internal destination không authorize |
| Custom JMS properties | Primitive/String | Chọn allowlist và convert đúng type |

`DefaultJmsHeaderMapper` hỗ trợ một số fields và custom properties; nó không biến provider-owned state thành application business metadata an toàn.

### 11.1. Đừng dùng JMSMessageID làm business ID

Khi app republish một JMS message, broker/provider có thể gán `JMSMessageID` mới. Nếu downstream dùng provider ID làm idempotency key thì cùng event logic có thể bị xem là event mới. Tạo một custom property `businessEventId` (String) từ domain contract, giữ nguyên qua retries.

### 11.2. JMSReplyTo khác Spring replyChannel

`JMSReplyTo` có type `jakarta.jms.Destination`, còn `replyChannel` là Spring `MessageChannel`/String. Chúng có **kiểu và lifecycle khác nhau**. JMS outbound gateway thường quản lý correlation/reply theo config, không copy raw Spring channel object sang JMS property.

### 11.3. JMS properties không chấp nhận arbitrary objects

Một header kiểu `MessageChannel`, `InputStream`, `Map<String,Object>`, `Class<?>` hay acknowledgment handle không phải generic JMS property được bảo đảm hợp lệ. Normalize businessEventId/appTraceId/schemaVersion thành String/primitive; drop runtime objects. Test với **JMS provider thật** vì unit mapper test không chứng minh broker chấp nhận kiểu.

## 12. AMQP/RabbitMQ: deliveryTag, received fields và x-*

AMQP inbound có thể mang:

~~~text
amqp_deliveryTag
amqp_redelivered
amqp_receivedExchange
amqp_receivedRoutingKey
amqp_receivedDeliveryMode
amqp_consumerQueue
amqp_consumerTag
amqp_channel
x-received-from
~~~

Đây là received/broker runtime metadata, **không** phải default contract cho publish mới.

### 12.1. Vì sao không copy deliveryTag/channel?

- `amqp_deliveryTag` có nghĩa trên **đúng AMQP channel/delivery** hiện tại.
- `amqp_channel` là runtime object, không thể dùng như durable remote reference.
- `amqp_redelivered` do broker xác lập, không phải flag producer được đổi theo ý muốn.
- `amqp_receivedExchange`/`amqp_receivedRoutingKey` mô tả inbound routing, không cấp quyền chọn outbound destination.
- `amqp_receivedDeliveryMode` là thông tin nhận, không tự đổi producer delivery mode.

### 12.2. Federation header x-received-from

RabbitMQ federation có thể gắn `x-received-from`. Nếu gateway phản chiếu nguyên header đó trong reply/publish, broker có thể xem message như vòng lặp và drop. Spring Integration Reference khuyên lọc broker proprietary headers hoặc dùng explicit header names.

~~~java
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

DefaultAmqpHeaderMapper mapper =
    new DefaultAmqpHeaderMapper();

mapper.setRequestHeaderNames(
    "STANDARD_REQUEST_HEADERS",
    "businessEventId",
    "appTraceId",
    "!x-*",
    "!Authorization");
~~~

Một số versions có x-* exclusions mặc định, nhưng **custom wildcard mapper có thể thay đổi policy**. Nếu plugin broker cần một header x-* cụ thể, thêm exception có kiểm soát thay vì cho phép tất cả.

### 12.3. HeaderMapper không ACK RabbitMQ

Một Spring header `amqp_deliveryTag` không có nghĩa app có thể ACK bằng cách gửi nó qua HTTP hoặc Kafka. Broker ACK cần active channel, tag đúng, mode đúng. Khi chuyển service/broker, dùng durable state/idempotency event key thay vì stale tag.

### 12.4. contentType có thể giữ, nhưng phải đúng payload

AMQP `contentType` là common header không có `amqp_` prefix. Có thể truyền nó giữa HTTP/AMQP/Kafka nếu body thật đúng format. `contentType=application/json` không khiến payload Java object tự serialize thành JSON hợp lệ; phải có MessageConverter và schema validation.

## 13. HTTP: headers bí mật, claims giả, hop-by-hop và SSRF

Một HTTP ingress có thể có:

~~~http
Authorization: Bearer <token>
Cookie: session=...
X-Tenant-Id: tenant-b
X-Role: admin
X-Forwarded-For: 10.0.0.1
X-Target-Url: http://127.0.0.1:8080/internal
X-Request-Id: client-generated
~~~

### 13.1. Không mirror sang HTTP outbound

- **Authorization/Cookie:** credential của client → service, không phải service → downstream partner.
- **X-Tenant-Id/X-Role:** raw claims chưa được xác minh.
- **X-Forwarded-For/Host:** chỉ tin khi có trusted reverse proxy policy.
- **X-Target-Url:** không chọn arbitrary outbound host từ client input (SSRF).
- **X-Request-Id:** trace hint phải validate, không tự là business ID.
- **Hop-by-hop headers** như Connection/Transfer-Encoding/Upgrade: client HTTP nên quản lý theo request mới, không copy từ request cũ.

### 13.2. Tạo trusted context từ authentication

~~~java
Message<?> clean =
    MessageBuilder.fromMessage(incoming)
        .removeHeader("Authorization")
        .removeHeader("Cookie")
        .removeHeader("X-Tenant-Id")
        .removeHeader("X-Role")
        .setHeader("trustedTenantId", authenticatedTenantId)
        .build();
~~~

Fragment này yêu cầu `authenticatedTenantId` được lấy từ security principal/verified claims. Không nhận raw client header rồi đặt tên lại thành trusted.

### 13.3. Outbound Authorization đúng audience

Nếu outbound HTTP gọi partner API cần OAuth token, dùng outbound authorized client/credential provider đúng partner audience/scopes; **không dùng lại inbound token**. Kiểm thử partner HTTP stub không thấy raw token nguồn trong request, logs hay error payload.

### 13.4. HTTP mapper allowlist

~~~java
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

DefaultHttpHeaderMapper mapper =
    DefaultHttpHeaderMapper.outboundMapper();

mapper.setOutboundHeaderNames(
    "Content-Type",
    "Accept",
    "X-Event-Id",
    "X-Trace-Id");
~~~

`setInboundHeaderNames(...)` trên **HTTP outbound gateway** kiểm soát headers nhận từ **response**, không phải request đang gửi. Tránh wildcard mapping tới partner nếu chưa có security review.

## 14. File/FTP/SFTP/SMB, TCP/UDP, MongoDB/JDBC boundary

| Adapter | Control header/metadata | Rủi ro nếu copy mù |
|---|---|---|
| File writer | `FileHeaders.FILENAME` | Path traversal/overwrite khi user chọn tên |
| FTP/SFTP output | remote directory/filename expression | Upload sai tenant/path |
| FTP/SFTP input | remote file/path/host-port | Không tự là business identity |
| TCP | connection ID/IP/port | Stale after reconnect |
| UDP | packet source address | Spoofing/reflection |
| MongoDB outbound | business ID trong payload/document | Header không tự thành BSON field |
| JDBC outbound | SQL params từ headers nếu cấu hình | Không dùng raw header làm SQL identifier |
| Logs/DLQ | full headers | Lộ secrets, PII, runtime handles |

### 14.1. SFTP: remote directory chỉ từ server allowlist

~~~java
public String remoteDirectoryFor(String tenant) {
    return switch (tenant) {
        case "tenant-a" -> "/partners/a/exports";
        case "tenant-b" -> "/partners/b/exports";
        default -> throw new IllegalArgumentException(
            "Unauthorized tenant");
    };
}
~~~

Chỉ gọi helper với tenant đã authorize. Không lấy raw `X-Remote-Path` từ client làm SFTP remoteDirectory expression. SessionFactory còn cần host-key verification, credentials và timeout riêng.

### 14.2. File name và idempotency

Khi FileWritingMessageHandler fallback filename theo Spring Message UUID, retry có thể tạo tên mới cho cùng business event. Dùng filename theo event ID đã validate, chọn fileExistsMode/checksum/temporary rename phù hợp.

~~~java
Message<String> fileMessage =
    MessageBuilder.withPayload(
            "{\"eventId\":\"evt-1001\"}")
        .setHeader(
            org.springframework.integration.file.FileHeaders.FILENAME,
            "evt-1001.json")
        .build();
~~~

Không cho tên file chứa path separators/`..`/control chars hoặc ghi ngoài root directory.

### 14.3. Không lưu nguyên MessageHeaders vào MongoDB/JDBC

Một `businessEventId` chỉ ở Spring header **không tự được lưu** vào MongoDB storing adapter hoặc JDBC row; nếu DB cần dedup, bind nó vào domain object/unique index hay SQL parameter rõ ràng.

Không lưu `replyChannel`, `errorChannel`, ACK handles, raw tokens, exception objects hoặc provider delivery metadata vào BSON/SQL vì đó là **persistent boundary** lâu dài.

### 14.4. UDP source address không là trusted destination

UDP datagram source IP/port có thể bị spoof hoặc thay đổi qua NAT; phản xạ dữ liệu sang raw source address có thể gây reflection/SSRF tương tự. Dùng trusted destination policy/rate limit/app-level authentication; UDP không tự cung cấp reliable delivery.
## 15. Xây hợp đồng header chuẩn trước khi vượt boundary

Giả sử nhận event từ HTTP/JMS/Kafka và phải gửi đến đối tác, ta không nên giữ lại toàn bộ protocol headers. Thiết kế một application contract **tối thiểu**:

| Application header | Kiểu | Ai cấp/validate? | Có được xuất ra partner? |
|---|---|---|---|
| `businessEventId` | String | Producer contract + canonical validator | Có, nếu đối tác cần idempotency |
| `appTraceId` | String | Tracing layer/validation | Có, nếu tracing contract yêu cầu |
| `schemaVersion` | int/String | Versioned event schema | Có, nếu downstream dùng |
| `sourceSystem` | Enum/String | Server-configured ingress identity | Có điều kiện |
| `trustedTenantId` | String | Authenticated identity + ACL | Chỉ khi partner có quyền; có thể map sang externalTenant |
| `receivedAt` | Instant | Server clock | Chỉ khi domain contract cần |
| `replyChannel` | MessageChannel/String | Spring runtime | **Không**, trừ internal reply lifecycle |
| `errorChannel` | MessageChannel/String | Spring runtime | **Không** |
| `Authorization` | String secret | HTTP client/request | **Không**; outbound auth riêng |
| `kafka_offset` | Long | Kafka consumer | **Không** như business metadata |
| `amqp_deliveryTag` | Long | RabbitMQ delivery | **Không** |
| `jms_redelivered` | Boolean | JMS provider | **Không** như outbound business status |

### 15.1. Một DTO transport-neutral

Một record chỉ chứa những business facts cần di chuyển giữa services:

~~~java
package example.headerboundary;

import java.time.Instant;

public record CanonicalOrderEvent(
        String tenantId,
        String eventId,
        String orderId,
        String status,
        int schemaVersion,
        Instant occurredAt) {
}
~~~

Điều quan trọng là **dùng domain DTO** thay vì serialize nguyên Spring `Message<?>` hoặc `MessageHeaders` ra broker/DB. Source-specific ACK handles, reply/error channels và credentials không xuất hiện trong domain DTO.

### 15.2. Normalize header từ nhiều giao thức

Ví dụ application tạo message sau khi auth/validation:

~~~java
package example.headerboundary;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class CanonicalEventMessageFactory {

    public Message<CanonicalOrderEvent> build(
            CanonicalOrderEvent event,
            String authorizedTenant,
            String validatedTraceId) {

        if (event == null
                || authorizedTenant == null
                || !authorizedTenant.equals(event.tenantId())
                || event.eventId() == null
                || !event.eventId().matches(
                    "[A-Za-z0-9_-]{1,128}")) {
            throw new IllegalArgumentException(
                "Invalid event identity/tenant");
        }

        return MessageBuilder.withPayload(event)
            .setHeader(
                "businessEventId", event.eventId())
            .setHeader(
                "trustedTenantId", authorizedTenant)
            .setHeader("appTraceId", validatedTraceId)
            .setHeader(
                "schemaVersion", event.schemaVersion())
            .build();
    }
}
~~~

Đây là ví dụ học thuật: cần validate `orderId/status/occurredAt`, trace ID length/type và tenant rights theo business. Nếu `validatedTraceId` là null, Spring builder có thể bỏ header theo semantics; production phải có contract rõ bắt buộc/optional.

**Không copy source MessageHeaders** vào output. Nếu cần giữ một protocol-specific field để audit, chuyển nó thành field đã chọn, đặt hạn dùng/retention và giới hạn người được đọc.

## 16. Allowlist ở outbound HeaderMapper, không chỉ lọc nội bộ

Ngay cả khi đã dùng HeaderFilter trong flow, trước external protocol boundary vẫn cần mapper cho phép **đúng những headers được gửi**.

### 16.1. HTTP outbound

~~~java
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

DefaultHttpHeaderMapper mapper =
    DefaultHttpHeaderMapper.outboundMapper();

mapper.setOutboundHeaderNames(
    "Content-Type",
    "Accept",
    "X-Event-Id",
    "X-Trace-Id");
~~~

Nếu Spring application sử dụng key `businessEventId` nhưng partner muốn `X-Event-Id`, dùng HeaderEnricher/custom mapper để **đổi tên có kiểm soát**; không mong DefaultHttpHeaderMapper tự đổi mọi custom field names.

### 16.2. JMS outbound

JMS properties nên là **String/primitive được hỗ trợ**. Với một service đang giữ header `businessEventId` String và `appTraceId` String, custom JMS mapper cần chỉ cho phép hai fields đó nếu default mapping quá rộng. JMS provider-owned fields như `JMSMessageID`/`JMSRedelivered` không được tự nhân bản để giả lập delivery state.

### 16.3. AMQP outbound

~~~java
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

DefaultAmqpHeaderMapper mapper =
    new DefaultAmqpHeaderMapper();

mapper.setRequestHeaderNames(
    "STANDARD_REQUEST_HEADERS",
    "businessEventId",
    "appTraceId",
    "!x-*",
    "!Authorization");
~~~

`STANDARD_REQUEST_HEADERS` có thể bao gồm standard AMQP properties theo mapper/version; nếu có field không nên xuất, bổ sung policy rõ hoặc tạo message mới để tránh retained fields. Không dùng wildcard `*` cho mọi custom header.

### 16.4. Kafka outbound

~~~java
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;

SimpleKafkaHeaderMapper mapper =
    new SimpleKafkaHeaderMapper(
        "!id", "!timestamp",
        "businessEventId", "appTraceId");
~~~

Khi dùng simple mapper, chuyển custom values thành raw UTF-8 bytes/kiểu đúng version. JSON Kafka mapper có type metadata, cần trusted schema/packages. Header map của Kafka không thay thế record key/topic/partition control.

### 16.5. Đồng bộ HeaderMapper với MessageConverter

Một HTTP/JMS/AMQP/Kafka mapper chỉ xử lý metadata. Body có thể được converter biến đổi; `contentType` trong original message có thể **không còn đúng** sau conversion. Cần xác minh wire payload thực tế và header contentType/encoding đi kèm, nhất là khi từ `Object` sang JSON, Avro/Protobuf hoặc byte[].

### 16.6. Boundary double check

Đặt một số business fields trong both header/payload có thể hỗ trợ routing nhưng dễ mâu thuẫn:

~~~text
Header businessEventId = evt-101
Payload eventId        = evt-202
~~~

**Không chọn ngầm một bên và tiếp tục.** Validate consistency, reject conflict hoặc áp explicit canonical policy có chữ ký và quyền ưu tiên rõ. Với tenant, giá trị trusted phải được liên kết với authenticated identity, không lấy raw user header.

## 17. Không propagate header khi chuyển thread, queue hoặc lưu bền

### 17.1. Thread boundary không biến dữ liệu thành “an toàn”

`DirectChannel` thường xử lý cùng caller thread, còn `ExecutorChannel`/`QueueChannel` có thể đưa message sang thread khác. Header map vẫn có thể đi theo message, nhưng:

- SecurityContext/MDC ThreadLocal không mặc định đi theo executor/Reactive context.
- `MessageChannel` và provider ACK handles có lifecycle/thread affinity riêng.
- Một `InputStream` hoặc session object có thể đã bị đóng khi consumer xử lý.
- Không lưu trực tiếp mutable object header rồi cho nhiều workers chỉnh.
- `send()==true` vào memory queue không có nghĩa transport phía sau đã commit.

**Giải pháp:** propagate correlation ID/tracing qua context propagation phù hợp, chọn immutable data, và ACK nguồn sau durable processing theo contract.

### 17.2. MessageStore persistent không có “serialize mọi Java object” thần kỳ

Khi `QueueChannel` có persistent `MessageStore`, store/serializer có thể phải serialize cả payload và headers. Rủi ro:

- Header chứa non-serializable `MessageChannel`, JMS Destination, socket/session, acknowledgment callback.
- Java object deserialization thành object khác runtime context hoặc không được resolve ở version mới.
- Payload/header schema thay đổi qua deploy, đọc lại thất bại.
- Token/secret bị lưu vào database lâu hơn chính sách bảo mật.
- Serialization diễn ra nhưng `replyChannel` tạm đã không còn caller.

Do đó, ưu tiên store **canonical business messages/data**, hoặc tách một durable inbox/outbox table/document có schema tối thiểu; không lưu nguyên runtime message graph.

### 17.3. Nếu thực sự cần reply sau durable queue

Một số thiết kế có thể dùng `HeaderChannelRegistry` để lưu token String cho reply/error channel **trong giới hạn TTL và registry scope**. Nhưng nếu business cần gửi reply sau vài giờ/restart/multi-region, hãy dùng **reply destination bền + correlation ID + status store**, không trông chờ temporary channel.

### 17.4. Một ví dụ pipeline có filter trước durable queue

~~~mermaid
flowchart LR
    I["Inbound Message<br/>token + replyChannel + eventId"] --> V["Validate + authorize"]
    V --> S["Sanitize/normalize"]
    S --> O["Canonical inbox/outbox<br/>eventId + payload"]
    O --> W["Async worker"]
    W --> M["Destination-specific HeaderMapper"]
    M --> B["Broker/Partner"]
~~~

**Thứ tự quan trọng:** nếu `QueueChannel/MessageStore` nằm **trước** sanitizer, raw secrets/runtime handles có thể đã được ghi bền và không thể “thu hồi” chỉ bằng HeaderFilter sau đó.

## 18. ErrorMessage, stack trace và DLQ: boundary quan sát cũng phải lọc

Spring Integration `ErrorMessage` thường có payload là một `Throwable`, với nested causes/messages có thể chứa endpoint URL, credentials, input identifiers hoặc PII.

**Không forward nguyên `ErrorMessage.getPayload()` hoặc `Throwable.toString()` đến public HTTP response, Kafka topic public, partner DLQ hoặc logs không được bảo vệ.**

### 18.1. Tạo một error envelope an toàn

~~~java
package example.headerboundary;

import java.time.Instant;

public record SafeFailureEvent(
        String eventId,
        String errorCode,
        boolean retryable,
        Instant failedAt) {
}
~~~

Khi bắt lỗi, application classification tạo một event mới:

~~~java
SafeFailureEvent safeFailure =
    new SafeFailureEvent(
        verifiedBusinessEventId,
        "DOWNSTREAM_TIMEOUT",
        true,
        Instant.now());
~~~

Đây là **fragment** cần eventId đã validate và lỗi đã được phân loại. Không đưa raw exception message/stack vào errorCode. Nếu cần diagnostics nội bộ, lưu trong một restricted store/tracing với retention và redaction riêng.

### 18.2. DLQ/quarantine không tự bảo đảm an toàn

Một durable DLQ có thể giữ message nhiều ngày, được nhiều team/tool đọc. Nếu original headers chứa Bearer token, Cookie, principal/session, authorization claim hoặc raw payload nhạy cảm, việc gửi thẳng vào DLQ có thể mở rộng quyền truy cập dữ liệu.

Policy khuyến nghị:

1. Dựng **safe failure payload** với eventId/errorCode/correlation.
2. Chỉ lưu payload gốc trong restricted encrypted bucket/store khi thật sự cần replay.
3. Scrub headers trước khi lưu hoặc gửi.
4. Có retention/access auditing và GDPR/PII policy phù hợp.
5. Không dùng một ErrorMessage chứa provider channel object làm durable replay record.
6. Replay phải dựng lại business message mới từ dữ liệu đã validate, không rehydrate arbitrary runtime objects.

### 18.3. Error channel không phải broker dead-letter ACK

Một `errorChannel` là Spring Messaging concept; gửi `ErrorMessage` tới errorChannel **không tự đồng nghĩa JMS/Kafka/AMQP đã dead-letter bền**. Nếu error handler chỉ log rồi return, source có thể ACK tùy adapter/container. Cần transaction/error propagation/durable DLQ policy riêng, test retry và poison-message loop.

## 19. Security review: boundary threat model

### 19.1. Tấn công giả tenant/role bằng external headers

Client gửi:

~~~http
X-Tenant-Id: tenant-b
X-Role: admin
X-Target-Topic: finance.sensitive
~~~

Nếu app tin các headers này để chọn MongoDB collection hoặc Kafka topic, user thuộc tenant A có thể truy cập data của B.

**Mitigation:**

- Authenticate/authorize dựa trên trusted security context.
- Bind `trustedTenantId` với claims/ACL đã verify.
- Cho phép destination theo server allowlist của tenant.
- Dùng explicit names/DTO; không map raw X-Target-Topic thành `KafkaHeaders.TOPIC`.
- Kiểm tra tenant header/payload mismatch và audit conflict.
- Test một user tenant A cố đổi header để gửi sang tenant B.

### 19.2. Reply/error channel injection

External client gửi key `replyChannel="adminControlChannel"` hoặc `errorChannel="sensitiveLogs"`. Nếu một mapper/custom handler copy những tên này vào Spring internal routing context, reply/error có thể đi nhầm.

**Mitigation:** không cho external header overwrite reserved keys; gateway/server cấp reply/error channels nội bộ, dynamic routes phải dùng allowlist/tên bean được authorize.

### 19.3. HTTP SSRF và SFTP path traversal

Raw headers như `X-Target-Url=http://localhost:8080/admin` hoặc `X-Remote-Directory=../../secrets` không bao giờ nên trở thành outbound destination expressions trực tiếp. Dùng server-side mapping từ authenticated partner ID sang URL/remote directory cố định, hạn chế egress và validate paths.

### 19.4. Header injection, type injection và size DoS

- HTTP value chứa `\r`/`\n` có thể gây header injection hoặc bị client reject.
- Kafka JSON type hints có thể gây deserialization sang kiểu không được phép nếu trusted packages mở quá rộng.
- AMQP/JMS headers có size/type restrictions; arbitrary Java object gây converter failure.
- Hàng trăm custom headers/large values có thể làm message/broker limits tăng, memory pressure hoặc log bloat.
- Header value có thể là secret ngay cả khi tên được allowlist; validate length/content.

### 19.5. Logging/metrics boundary

Không log `message.getHeaders()` nguyên vẹn. Đo những metric **low-cardinality**: protocol, destination ID đã allowlist, outcome, error category; không dùng mỗi eventId/tenant-sensitive token làm label. Correlation ID có thể đi trong trace/log đã redacted với retention và quyền truy cập.

### 19.6. Security checklist theo mỗi boundary

| Kiểm tra | Câu hỏi |
|---|---|
| Ownership | Ai tạo header? External client, broker, hay server? |
| Trust | Đã authenticated/validated/authorized chưa? |
| Lifetime | Header còn hợp lệ sau thread switch/restart không? |
| Type | Có serialize được sang protocol đích không? |
| Semantics | Receiver có hiểu cùng ý nghĩa không? |
| Sensitive | Có lộ token/PII/topology/roles không? |
| Destination | Có được quyền dùng header để route không? |
| Retry | Nếu redelivery, value còn đúng và ổn định không? |
| Audit | Có cần lưu lâu không, retention thế nào? |
| Test | Đã assert vắng mặt trên wire/log/store chưa? |
## 20. Kiểm thử tự động: header thực sự không qua boundary

Để chứng minh một header **không được truyền qua boundary**, unit/integration tests phải assert **header vắng mặt ở output**, không chỉ assert handler trả về success. Một test tốt còn khẳng định **businessEventId/tracing fields cần thiết vẫn còn**.

### 20.1. JUnit test MessageBuilder tạo allowlisted message

~~~java
package example.headerboundary;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class MessageBoundaryTest {

    @Test
    void onlyBusinessMetadataIsCopied() {
        Message<String> input =
            MessageBuilder.withPayload("order-paid")
                .setHeader("Authorization", "secret")
                .setHeader("X-Untrusted-Role", "admin")
                .setHeader("businessEventId", "evt-1001")
                .setHeader("appTraceId", "trace-01")
                .build();

        Message<String> outbound =
            MessageBuilder.withPayload(input.getPayload())
                .setHeader("businessEventId",
                    input.getHeaders().get(
                        "businessEventId", String.class))
                .setHeader("appTraceId",
                    input.getHeaders().get(
                        "appTraceId", String.class))
                .build();

        assertEquals("evt-1001",
            outbound.getHeaders()
                .get("businessEventId", String.class));

        assertEquals("trace-01",
            outbound.getHeaders()
                .get("appTraceId", String.class));

        assertFalse(outbound.getHeaders()
            .containsKey("Authorization"));

        assertFalse(outbound.getHeaders()
            .containsKey("X-Untrusted-Role"));
    }
}
~~~

**Giới hạn:** test này kiểm tra builder policy. Nó không chứng minh **toàn bộ IntegrationFlow** đều đi qua builder hay không có handler nào về sau thêm lại forbidden header.

### 20.2. Integration test HeaderFilter với QueueChannel

Cấu hình test trong Spring context:

~~~java
package example.headerboundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
class BoundaryFilterTestConfig {

    @Bean("rawInbound")
    MessageChannel rawInbound() {
        return new DirectChannel();
    }

    @Bean("sanitizedInbound")
    PollableChannel sanitizedInbound() {
        return new QueueChannel(10);
    }

    @Bean
    IntegrationFlow sanitizeInboundFlow() {
        return IntegrationFlow.from("rawInbound")
            .headerFilter(
                "Authorization",
                "Cookie",
                "X-Untrusted-Role")
            .channel("sanitizedInbound")
            .get();
    }
}
~~~

Kiểm thử:

~~~java
package example.headerboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(BoundaryFilterTestConfig.class)
class HeaderFilterIT {

    @Autowired
    @Qualifier("rawInbound")
    MessageChannel input;

    @Autowired
    @Qualifier("sanitizedInbound")
    PollableChannel output;

    @Test
    void secretsAreRemovedBeforeNextChannel() {
        Message<String> source =
            MessageBuilder.withPayload("order-paid")
                .setHeader("businessEventId", "evt-1001")
                .setHeader("Authorization", "secret")
                .setHeader("Cookie", "sid=secret")
                .setHeader("X-Untrusted-Role", "admin")
                .build();

        assertTrue(input.send(source));

        Message<?> result = output.receive(2000);
        assertNotNull(result);

        assertEquals("evt-1001",
            result.getHeaders()
                .get("businessEventId", String.class));

        assertFalse(result.getHeaders()
            .containsKey("Authorization"));

        assertFalse(result.getHeaders()
            .containsKey("Cookie"));

        assertFalse(result.getHeaders()
            .containsKey("X-Untrusted-Role"));
    }
}
~~~

Điều kiện: test cần `spring-integration-core` và `spring-test`/JUnit Jupiter trong classpath. Mỗi test nên có context/queue được reset để tránh nhận message cũ. `QueueChannel(10)` ở đây **in-memory**, không thay cho persistent store/broker integration test.

### 20.3. Test notPropagatedHeaders ở đúng endpoint

Cấu hình minh họa **flow riêng** để tránh trùng bean/channel của test trên:

~~~java
@Bean
IntegrationFlow noSecretPropagation() {
    return IntegrationFlow.from("rawTransformInput")
        .handle(
            String.class,
            (payload, headers) -> payload.toUpperCase(),
            e -> e.notPropagatedHeaders(
                "Authorization", "debug*"))
        .channel("noSecretOutput")
        .get();
}
~~~

Đây là **fragment**; khai báo channels trong context tương ứng. Test cần assert `Authorization` và `debugTrace` vắng ở output, nhưng `businessEventId` vẫn tồn tại. Quan trọng: vì handler trả **payload**, automatic propagation xảy ra và option `notPropagatedHeaders` có tác dụng. Đừng dùng cùng test để suy ra router/bridge cũng filter.

### 20.4. Test rằng bridge/router không tự lọc

Tạo một flow:

~~~java
@Bean
IntegrationFlow bridgeOnly() {
    return IntegrationFlow.from("bridgeInput")
        .bridge()
        .channel("bridgeOutput")
        .get();
}
~~~

Nếu source message có `Authorization`, một bridge thường chỉ forward message; **không** dựa vào `notPropagatedHeaders` của handler khác để loại nó. Cần `HeaderFilter` trước hoặc sau bridge, đúng vị trí mọi paths đều đi qua.

### 20.5. Test HTTP outbound wire metadata

Sử dụng một HTTP test server (WireMock, MockWebServer hoặc embedded server) và một outbound gateway **đã inject mapper allowlist**. Kiểm tra:

1. Request body còn đúng business payload.
2. Header `X-Event-Id` có businessEventId đã verify.
3. Không có raw inbound `Authorization` hoặc `Cookie`.
4. Không có Spring `replyChannel`/`errorChannel`/`id` trong HTTP headers.
5. Content-Type đúng payload đã được convert.
6. Partner response headers chỉ map những fields được cho phép.
7. Gửi event thiếu ID thì fail trước network call.

### 20.6. Test Kafka, JMS và AMQP ở wire-level

| Giao thức | Unit mapper assertion | Integration assertion |
|---|---|---|
| Kafka | `RecordHeaders.lastHeader("businessEventId")` đúng bytes, không có internalRole | ConsumerRecord headers thực, topic/key đúng, retry/ACK |
| JMS | Allowed String property từ Spring header | JMS listener nhận đúng property; không có Spring channel object |
| AMQP | `DefaultAmqpHeaderMapper.fromHeaders` không tạo x-received-from/internalRole | RabbitMQ message properties thực, confirm/return |
| SFTP | Sanitized filename và trusted directory expression | Remote file đúng path, không traversal |
| Persistent store | Headers có kiểu serializable/canonical | Message restore được qua restart và reply/error policy hợp lệ |

Một mock unit test không chứng minh broker đã ACK, Kafka offset đã commit hoặc SFTP upload đã finalize. Test cả **failure path** khi broker down/network timeout.

## 21. Ma trận retry, ACK và recovery sau khi lọc headers

| Giai đoạn | Nếu có lỗi | Header giữ lại để retry | Header tuyệt đối không bền hóa |
|---|---|---|---|
| Ingress parse/validate | Reject/HTTP 4xx hoặc quarantine | sourceEventId, sanitized source ID | Raw token, untrusted role |
| Durable inbox write | Retry/reconcile cùng key | businessEventId, tenant authorized, schema | Temporary replyChannel, Kafka ACK |
| Queue/process boundary | Recover pending work | business fields/attempt count trong durable store | JMS session, AMQP channel/deliveryTag |
| HTTP outbound | Retry có idempotency | businessEventId, safe trace | Inbound Authorization/Cookie |
| Kafka producer | Retry/outbox/ack policy | Kafka key, event ID, schema | Consumer offset/ACK object |
| JMS/AMQP producer | Broker retry/confirm/returns | businessEventId | inbound delivery tags/redelivered |
| Persistent DLQ | Manual replay sau triage | safe event ID/error code | Throwable stack/raw token |
| App restart | Rebuild canonical message | domain DTO/transaction status | In-memory channels/session refs |

### 21.1. Vì sao cùng một header có thể hợp lệ ở bước này nhưng sai ở bước khác?

Một `replyChannel` hợp lệ trong **gateway sync** có thể sai khi lưu vào **Kafka outbox**. Một `kafka_offset` có ích để debug listener nhưng không phải header hợp lệ để ra **partner HTTP**. Một `trustedTenantId` có thể cần cho database authorization nội bộ nhưng không được gửi tới partner khác tenant.

Đây là lý do không nên xây một global “cấm mọi header A” hoặc “copy mọi header B”; phải xác định **source, destination, trust, lifetime và contract**.

### 21.2. Recovery sau lost ACK

Giả sử HTTP partner đã commit nhưng response timeout. Ứng dụng retry với **cùng businessEventId** và canonical payload; partner/destination cần idempotent logic để trả ALREADY_ACCEPTED hoặc business conflict.

Không tạo Spring Message UUID mới rồi dùng như business ID thay thế. Việc lọc `id` là đúng khi nó bị dùng sai qua boundary, nhưng event ID nghiệp vụ phải **được giữ và lưu bền**.

### 21.3. Đừng giữ broker ACK handles ở MessageStore

Kafka acknowledgment object, AMQP deliveryTag/channel hoặc JMS session là **runtime capabilities** gắn với listener/connection/transaction. Sau restart hay worker khác, chúng không phải durable replay mechanism. Cần commit/rollback trong đúng listener lifecycle hoặc chuyển thành durable inbox/outbox và recovery policy được thiết kế rõ.

### 21.4. Error channel không tự có nghĩa durable DLQ

Một error handler tạo `ErrorMessage` rồi trả bình thường có thể khiến upstream ACK theo container policy. Nếu chưa lưu được message an toàn vào durable quarantine, không được giả định retry sẽ tiếp tục. Một DLQ phải có owner, retention, redaction, replay idempotent và metric.

## 22. Observability, bảo mật log và lifecycle

### 22.1. Metrics hữu ích

Những tên sau là **gợi ý**, không mặc định framework tự tạo:

| Metric | Ý nghĩa |
|---|---|
| `boundary_header_filtered_total` | Số headers bị loại theo policy |
| `boundary_header_rejected_total` | Header sai/forbidden khiến event fail |
| `boundary_header_type_error_total` | Không serialize/convert được |
| `boundary_untrusted_tenant_attempt_total` | Attempt đổi tenant/route |
| `boundary_reserved_header_attempt_total` | Header cố ghi đè reply/error/channel |
| `boundary_wire_header_leak_total` | Vi phạm contract phát hiện trong kiểm thử/giám sát |
| `boundary_outbound_send_total` | Số lần gửi transport |
| `boundary_outbound_unknown_total` | Timeout/ACK chưa rõ |
| `boundary_dlq_depth` | Safe quarantined events đang chờ |
| `boundary_recovery_success_total` | Sự kiện được khôi phục thành công |
| `boundary_business_committed_total` | Business effect đã hoàn tất |

Không dùng raw event ID/token/URL động làm metric labels có cardinality cao. Với tracing, correlation ID hợp lệ có thể vào structured logs/spans theo retention policy.

### 22.2. Log gợi ý

~~~text
ingress_received     source=http-partner
header_validated     allowed=4 rejected=2
canonicalized        hasBusinessEventId=true
persisted_inbox      status=accepted
outbound_started     protocol=kafka destination=orders.events
broker_ack           result=success
business_committed   result=pending_downstream
~~~

Các logs trên **không chứa raw credentials**, payload nhạy cảm hoặc arbitrary object toString(). Đừng log full `message.getHeaders()` chỉ để debug production.

### 22.3. Lifecycle/threads

- HTTP request/gateway có timeout và reply lifetime ngắn.
- JMS/AMQP listener có session/channel delivery lifetime; handle không tự portable sau reconnect.
- Kafka consumer có rebalance/offset lifecycle; acknowledgment handle không phải durable task ID.
- QueueChannel/ExecutorChannel có async context boundary; ThreadLocal/MDC không tự propagate.
- SFTP/FTP session có remote connection lifecycle; raw session object không bền.
- MessageStore có serialization/schema/restart boundary.
- Outbound HTTP/Kafka/JMS/AMQP có separate delivery/confirmation lifecycle.

HeaderFilter/mapper không tự khởi động/dừng poller, không drain in-flight messages hoặc tạo outbox. Khi deploy/restart, phải bảo đảm durable pending work, idempotent replay và graceful shutdown.

### 22.4. Kiểm tra định kỳ policy khi đổi schema

Khi thêm một header mới `internalApprovalRole`, nếu app đang dùng blocklist chỉ loại `Authorization`, header mới có thể lọt sang partner. Trước mỗi release nên chạy contract tests kiểu **“unknown header must not appear on wire”**. Destination allowlist dễ kiểm tra hơn danh sách blocklist phình to.
## 23. Case study: HTTP inbound → MongoDB inbox → Kafka → JMS/HTTP partner

### 23.1. Yêu cầu nghiệp vụ

Một hệ thống nhận `OrderPaid` qua HTTP từ đối tác. Sau đó:

1. Xác thực tenant và chữ ký/token.
2. Lưu một durable MongoDB inbox document với business event ID.
3. Dùng worker gửi Kafka `orders.paid` với `businessEventId`.
4. Consumer khác chuyển sang JMS queue `accounting.paid`.
5. Một partner khác nhận HTTP POST xác nhận trạng thái.
6. Mỗi bước có thể retry/redelivery sau crash hoặc mất ACK.

### 23.2. Những headers đầu vào

~~~text
HTTP ingress headers:
  Authorization = Bearer <token>
  X-Tenant-Id = tenant-a
  X-Role = admin
  X-Event-Id = evt-1001
  X-Trace-Id = tr-9c

Spring framework / transport headers:
  id = <new UUID>
  replyChannel = <temporary MessageChannel>
  errorChannel = <MessageChannel>
  http_requestUrl = /orders/events
  http_requestMethod = POST
~~~

### 23.3. Chính sách ở từng điểm

| Điểm | DROP | TRANSFORM/KEEP |
|---|---|---|
| HTTP ingress → trusted business | Authorization, Cookie, X-Role, raw X-Tenant-Id | authenticatedTenantId → trustedTenantId, X-Event-Id → businessEventId, validated trace |
| Business → MongoDB inbox | replyChannel/errorChannel, raw HTTP request metadata | Canonical DTO, unique business ID, schemaVersion |
| MongoDB outbox → Kafka | Runtime DB/worker/lease objects | Kafka key by orderId, custom businessEventId bytes |
| Kafka consumer → JMS producer | Kafka ACK/ConsumerRecord/topic/offset metadata | businessEventId String, appTraceId String |
| JMS consumer → HTTP partner | JMSMessageID/Redelivered/JMSReplyTo, raw token | X-Event-Id, X-Trace-Id, body JSON, outbound token mới |
| Any error → DLQ | Throwable object, raw headers, secrets | safe errorCode, eventId, retryable flag |
| Replay after restart | Temporary channels/ACK handles | Stable event ID, durable pending status |

### 23.4. Thiết kế end-to-end

~~~mermaid
flowchart TB
  H["HTTP request"] --> SEC["Auth + tenant validation"]
  SEC --> N["Sanitize external headers"]
  N --> C["CanonicalOrderEvent<br/>+ businessEventId"]
  C --> DB["MongoDB Inbox/Outbox<br/>durable transaction"]
  DB --> W["Outbox worker"]
  W --> K["Kafka producer<br/>custom allowed headers"]
  K --> KC["Kafka consumer"]
  KC --> J["JMS producer<br/>JMS-friendly properties"]
  J --> JC["JMS consumer"]
  JC --> PH["HTTP partner<br/>new auth, selected headers"]
  W -. failure .-> D["Safe DLQ / retry"]
  KC -. failure .-> D
  JC -. failure .-> D
~~~

### 23.5. Crash windows

**Tình huống A — DB commit thành công, HTTP client timeout:** client retry cùng X-Event-Id, MongoDB unique key giúp phát hiện record đã có. Không dùng Spring Message UUID mới làm event ID.

**Tình huống B — Kafka broker ACK nhưng outbox worker crash trước mark SENT:** event có thể được publish lại. Consumer dedup theo businessEventId; Kafka offset không cần và không nên được copy sang JMS/HTTP như event identity.

**Tình huống C — JMS consumer nhận lại message:** JMSRedelivered giúp quan sát, không chứng minh business side effect trước đó đã xảy ra. Durable inbox ở accounting service phân xử xử lý trùng.

**Tình huống D — HTTP partner API trả 202 rồi connection lost:** không xem 202 là business completed. Reconcile cùng eventId/partner status; không tự tạo token/trace/event ID mới để “thử lại sạch”.

**Tình huống E — application restart:** temporary replyChannel và ACK callbacks của process trước không còn. Durable outbox/inbox khôi phục qua business IDs, không deserialize runtime callback objects.

### 23.6. Tiêu chí chấp nhận

- Không token/role/raw tenant header đi sang Kafka/JMS/partner.
- Không Spring `replyChannel`/`errorChannel` object có trong persisted inbox/outbox.
- Kafka wire headers chỉ chứa fields đã cho phép và encoding đúng.
- JMS custom properties chỉ chứa String/primitive theo contract.
- AMQP `x-received-from`/deliveryTag không bị mirror nếu pipeline có RabbitMQ.
- Partner chỉ nhận outbound token đúng audience, X-Event-Id và body hợp lệ.
- Redelivery giữ cùng businessEventId, không tạo business effect thứ hai.
- Missing/mismatched event ID bị reject/quarantine, không retry mãi.
- Error logs/DLQ không chứa secrets hoặc raw exception stack theo policy.
- Async queue receive != transport/business ACK; metrics phân biệt mốc.

## 24. Troubleshooting: header vượt boundary sai hoặc bị mất

| Triệu chứng | Nguyên nhân | Cách kiểm tra và sửa |
|---|---|---|
| Authorization xuất hiện ở partner HTTP | Copy wildcard/mapper default quá rộng | Bật outbound allowlist, redact ingress |
| Spring header replyChannel có trong JMS property | Serialize nguyên headers hoặc custom mapper | Không đưa runtime object; use JMS gateway correlation |
| HeaderFilter không có tác dụng | Flow không đi qua filter, sai key/casing | Capture message trước/sau, verify wiring |
| notPropagatedHeaders không lọc router | Router/bridge forward message, không tạo output copy | HeaderFilter/transformer trước route |
| notPropagatedHeaders xóa cả businessEventId | Dùng pattern `*` hoặc quá rộng | Chỉ định patterns cụ thể, assert required headers |
| readOnlyHeaders bị hiểu là outbound denylist | Sai phạm vi builder vs network | Dùng destination HeaderMapper allowlist |
| Transformer chỉ đổi payload nhưng secrets còn | Automatic propagation | HeaderFilter, notPropagated hoặc tạo Message sạch |
| Transformer trả Message mất correlation | Không copy required headers | Explicit correlation fields, test gateway |
| Persist queue lỗi serialize | Header chứa MessageChannel/InputStream/ACK callback | Canonical DTO, HeaderChannelRegistry có TTL nếu phù hợp |
| Reply sau restart không tới caller | Temporary replyChannel mất hoặc TTL hết | Durable reply destination + correlation ID |
| Kafka ACK handle được gửi vào JMS | Copy runtime Kafka headers | Drop listener context, commit tại consumer |
| Kafka offset được dùng làm eventId | Nhầm log position và business identity | Stable businessEventId |
| JMSMessageID đổi sau republish | Provider-generated ID mới | Custom businessEventId String |
| JMS property conversion lỗi | Unsupported Java object type | Normalize/allowlist JMS primitive/String |
| AMQP deliveryTag sai sau reconnect | Tag gắn với channel cũ | ACK đúng active channel; không persist tag |
| RabbitMQ reply bị drop | `x-received-from` federation header bị mirror | Exclude x-* hoặc filter có kiểm soát |
| Kafka JSON type header nguy hiểm | Trusted packages quá rộng | Schema/trusted types allowlist |
| HTTP client gọi nội bộ qua X-Target-Url | SSRF từ raw header | Server route allowlist/egress policy |
| SFTP upload sai thư mục tenant | Remote path từ untrusted header | Trusted tenant → fixed allowed directory |
| Header có id bị bỏ nhầm | Core read-only/header rebuild semantics | Tách businessEventId khỏi Message ID |
| Content-Type không khớp body | Converter thay payload sau mapping | Wire-level body/header test |
| DLQ có token/PII | Lưu ErrorMessage/full headers | Safe envelope + restricted data store |
| Error flow chỉ log rồi source ACK | Recovery callback swallow exception | Durable DLQ hoặc propagate lỗi theo contract |
| QueueChannel.send true nhưng outbound chưa chạy | RAM queue async | Durable outbox/ACK đúng stage |
| Test unit pass nhưng leak ngoài mạng | Chỉ test builder, không test HeaderMapper/endpoint | Capture HTTP/JMS/AMQP/Kafka wire metadata |
| Metrics cardinality tăng | Dùng eventId/token làm labels | Low-cardinality dimensions |

### 24.1. Quy trình chẩn đoán theo thứ tự

~~~text
1. External source + raw metadata
2. Security filter / producer ACL / tenant validation
3. HeaderMapper.toHeaders hoặc native inbound adapter headers
4. Raw Spring Message
5. HeaderFilter / Transformer / notPropagatedHeaders
6. Canonical Spring Message & domain DTO
7. Persistent queue/inbox/outbox serialization
8. Outbound HeaderMapper.fromHeaders
9. Actual HTTP/JMS/AMQP/Kafka/SFTP wire payload & headers
10. Transport ACK/confirm/return
11. Business consumer commit
12. Retry, DLQ and recovery after crash/restart
~~~

Test **từng boundary**, không chỉ đọc message ở đầu và cuối. Nếu leak xảy ra, nhìn path cụ thể: Spring header có thể đi qua một nhánh không chạy filter hoặc một gateway/mapper khác với bean đã kiểm thử.

## 25. Bài thực hành

Xây một hệ thống lab với hai nhánh: **HTTP → canonical event → Kafka** và **JMS/AMQP → canonical event → HTTP partner**, sau đó kiểm tra headers bị loại tại mọi boundary.

### Phần A — Spring Message propagation

1. Tạo message với Authorization, X-Untrusted-Role, businessEventId, appTraceId.
2. Tạo transformer chỉ trả payload; quan sát headers nào được propagate.
3. Tạo transformer trả nguyên Message mới bằng `MessageBuilder.withPayload(...)`; so sánh.
4. Dùng `HeaderFilter` để loại Authorization/Cookie/Role.
5. Test `notPropagatedHeaders("Authorization","debug*")` trên service activator tạo output.
6. Đặt một bridge/router trước filter, kiểm tra vì sao filtering phải nằm trên mọi path.
7. Dùng `"*"` cho notPropagatedHeaders trong **lab**, giải thích vì sao required headers có thể bị mất.
8. Kiểm tra id/timestamp read-only, dùng businessEventId riêng.

### Phần B — Reply/error và durable boundary

1. Gửi một request/reply message qua gateway đồng bộ, quan sát replyChannel.
2. Đưa message chứa runtime MessageChannel vào MessageStore test; phân tích serialization/lifecycle.
3. Thử `HeaderChannelRegistry` và chuyển replyChannel thành token String với TTL.
4. Chứng minh token/temporary reply không thành durable cross-service RPC sau restart.
5. Thiết kế reply queue + correlation ID/bền hóa status cho request xử lý lâu.
6. Test external header `replyChannel="internalAdminChannel"` không thể override internal route.

### Phần C — Kafka/JMS/AMQP metadata

1. Gửi Kafka record, nhận `KafkaHeaders.OFFSET`/`RECEIVED_TOPIC` trong listener.
2. Rebuild canonical message, assert không có consumer ACK/offset object trong outbound Kafka headers.
3. Tạo JMS outbound message với custom businessEventId property, không provider JMSMessageID cũ.
4. Kiểm tra JMS property type unsupported gây failure trước/ở provider.
5. Nhận AMQP message có `amqp_deliveryTag` và `x-received-from`, loại trước outbound.
6. Test publisher confirm/returns khác với message header mapping.
7. Đo một redelivery event ID và đối chiếu idempotency.

### Phần D — HTTP/SFTP và security

1. Nhận HTTP request có Authorization, X-Role, X-Tenant-Id.
2. Auth user tenant A và gửi header giả tenant B, assert trusted tenant không đổi.
3. Gọi HTTP partner stub, assert không leak inbound token/cookie/role.
4. Cấu hình outbound API URL theo allowlist; test X-Target-Url SSRF bị từ chối.
5. Dùng SFTP remote directory từ authenticated tenant → fixed config, không raw user path.
6. Dùng filename từ validated businessEventId và thử replay cùng ID.
7. Kiểm thử Content-Type và body wire-level cùng lúc.

### Phần E — Persistence, DLQ, vận hành

1. Lưu canonical event + business ID vào MongoDB inbox/outbox.
2. Đảm bảo không lưu replyChannel/errorChannel/Throwable/raw token vào document.
3. Simulate crash sau broker ACK trước SENT, thấy event có thể được phát lại.
4. Bổ sung idempotent consumer với unique business key.
5. Làm DLQ safe envelope với errorCode, eventId, retryable flag.
6. Tạo metrics header dropped/rejected, transport ack, unknown outcome, DLQ backlog.
7. Thực hiện restart test với persistent store và kiểm tra message được khôi phục.
8. Thiết kế retention/access control cho logs/DLQ và graceful drain.

### 25.1. Câu hỏi tự đánh giá

- “Header không được truyền qua boundary” có nghĩa framework tự chặn mọi header nhạy cảm không?
- Transformer trả payload khác transformer trả Message như thế nào về propagation?
- HeaderFilter khác notPropagatedHeaders và HeaderMapper ra sao?
- Vì sao notPropagatedHeaders không giải quyết mọi router/bridge path?
- `readOnlyHeaders` và `MessageHeaders.ID/TIMESTAMP` có liên quan gì?
- Khi dùng pattern `*` với notPropagatedHeaders, điều gì xảy ra?
- Vì sao Spring replyChannel không nên serialize sang Kafka/JMS?
- HeaderChannelRegistry có làm reply bền xuyên restart không?
- Kafka ACK callback/offset/consumer object có nên gửi sang partner không?
- JMSMessageID có thể thay khi republish không?
- AMQP deliveryTag và x-received-from có thể gây lỗi gì?
- Vì sao HTTP inbound Authorization không thể trở thành outbound Authorization?
- Một header tên trustedTenantId có đáng tin chỉ vì nó tồn tại không?
- SFTP path từ client có thể gây vấn đề gì?
- MongoDB storing handler có tự lưu mọi Spring headers không?
- Vì sao wire-level tests quan trọng hơn chỉ test mapper unit?
- HeaderFilter có loại được bí mật đã nằm trong payload không?
- Vì sao một errorChannel chỉ log không tự là durable DLQ?
- Redelivery sẽ dùng Spring Message ID hay businessEventId để dedup?
- Khi QueueChannel.send() thành công, broker đã ACK chưa?

## 26. Tài liệu tham khảo

- [Spring Integration — Message and Header Propagation](https://docs.spring.io/spring-integration/reference/message.html): read-only headers, propagation, notPropagatedHeaders và giới hạn với bridges/routers.
- [Spring Integration — Transformer and Header Filter](https://docs.spring.io/spring-integration/reference/transformer.html): Header Filter EIP, Java DSL/XML, transform output.
- [Spring Integration — Header Enricher and HeaderChannelRegistry](https://docs.spring.io/spring-integration/reference/content-enrichment.html): chuyển replyChannel/errorChannel sang token, TTL và registry.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): persistence, serialization, Store types và lifecycle.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel/QueueChannel/ExecutorChannel và thread boundaries.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel, error flow.
- [Spring Integration — HTTP Header Mapping](https://docs.spring.io/spring-integration/reference/http/header-mapping.html): DefaultHttpHeaderMapper inbound/outbound allowlists.
- [Spring Integration — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): default JMS header mapper, message-driven/outbound, correlation.
- [Spring Integration — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html): `x-*`/federation, received-only fields, request/reply header patterns.
- [Spring Integration — AMQP Outbound](https://docs.spring.io/spring-integration/reference/amqp/outbound-channel-adapter.html): RabbitMQ publisher confirms và returns.
- [Spring Integration — Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): inbound/outbound Kafka adapters và converter.
- [Spring Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html): Simple/JSON KafkaHeaderMapper, header exclusions, patterns và typed headers.
- [Spring Integration — File Writing](https://docs.spring.io/spring-integration/reference/file/writing.html): FileHeaders.FILENAME, FileNameGenerator, FileExistsMode.
- [Spring Integration — SFTP](https://docs.spring.io/spring-integration/reference/sftp.html): remote paths, session management, file delivery.
- [Spring Integration — TCP and UDP](https://docs.spring.io/spring-integration/reference/ip.html): IP headers và network connection metadata.
- [Spring Framework — MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html): reserved/core headers và typed access.
- [Spring Integration API — HeaderMapper](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/mapping/HeaderMapper.html): `toHeaders`/`fromHeaders`.

## 27. Kết luận

**Header không được truyền qua boundary** không phải một danh sách cấm mang tính hình thức. Đó là quyết định dựa trên **nguồn sinh, mức độ tin cậy, thời gian sống, kiểu dữ liệu, semantic, quyền của destination và khả năng retry/replay**. Spring Integration thường propagate headers giữa message-producing endpoints, vì thế chúng ta phải chủ động xác định nơi lọc.

Trong **SPRING_INTEGRATION_ADAPTERS**, áp dụng kết hợp **HeaderFilter/MessageBuilder** cho message nội bộ, **notPropagatedHeaders** khi handler tạo output mới, và **destination-specific HeaderMapper/DTO** tại HTTP/JMS/AMQP/Kafka/file/database boundary. Không serialize Spring `replyChannel`/`errorChannel` hay broker ACK handles như business metadata; không forward source credentials, raw tenant claims, stale delivery tags hoặc arbitrary Java objects. Giữ **businessEventId ổn định**, chỉ xuất data đã validate và test sự vắng mặt của forbidden headers tại **wire/store/log/DLQ**.

**Một message gửi đi thành công không chứng minh headers đã an toàn; một header bị lọc đúng cũng không chứng minh downstream đã ACK hoặc business đã commit.** Muốn bảo toàn dữ liệu qua crash, hãy kết hợp các boundary policies với durable inbox/outbox, idempotent consumer, retry/backoff, recovery và observability.








