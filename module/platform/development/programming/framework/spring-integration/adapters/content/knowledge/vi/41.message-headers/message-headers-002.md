# HeaderMapper cho outbound message trong Spring Integration

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **outbound header mapping**: đưa metadata của Spring `MessageHeaders` sang HTTP request headers, JMS headers/properties, AMQP `MessageProperties` hoặc Kafka record headers khi message rời khỏi Spring Integration.
- Nhớ đúng **chiều của `HeaderMapper<T>`**: `fromHeaders(MessageHeaders source, T target)` là outbound, `toHeaders(T source)` là inbound. Đặc biệt, một **outbound gateway** có thể cần *cả hai* hướng: từ Spring headers sang request và từ response headers về Spring message.
- Phân biệt header mapping với payload conversion, endpoint routing, HTTP/JMS/AMQP/Kafka QoS, write acknowledgement và downstream business commit.
- Cấu hình `DefaultHttpHeaderMapper.outboundMapper()`, `setOutboundHeaderNames(...)`, HTTP Java DSL `headerMapper(...)` hoặc `mappedRequestHeaders(...)` và XML `mapped-request-headers`.
- Sử dụng `DefaultJmsHeaderMapper` trong JMS outbound adapter, chọn custom JMS properties hợp lệ, nhận biết `JMSCorrelationID`, TTL, priority, delivery mode và vai trò `JmsTemplate`.
- Cấu hình `DefaultAmqpHeaderMapper`, `setRequestHeaderNames(...)` cho AMQP outbound, tránh chuyển lại `x-*` broker-internal headers hoặc metadata của lần giao trước.
- Phân biệt `KafkaHeaderMapper` của **Spring for Apache Kafka** với interface `HeaderMapper<T>` của Spring Integration; kiểm soát wire-format `byte[]`, JSON type hints, Kafka record topic/key và multi-value headers.
- Biết File/SFTP/FTP, TCP/UDP, MongoDB, SMTP/WebSocket có các **protocol-specific outbound fields/headers** nhưng không phải adapter nào cũng có generic HeaderMapper.
- Thiết kế **outbound allowlist, type validation, secret minimization, correlation/idempotency contract, mapping policy theo destination và không rò rỉ nội bộ**.
- Xây dựng unit tests cho mapper, integration tests cho HTTP/broker endpoint, và xử lý retry/ACK/error channel/vòng đời kết nối.

Bài thuộc chương **Header message** của module **SPRING_INTEGRATION_ADAPTERS**. Phạm vi module là kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; xử lý hợp đồng message, lỗi và vòng đời kết nối. Đối với outbound, bài toán không chỉ là “gửi được header”, mà còn là **chọn đúng metadata để gửi sang đúng hệ thống, đúng kiểu và đúng hợp đồng ACK**.

> **Phạm vi phiên bản:** ví dụ dựa trên Java 17+, Spring Boot 3.x, Spring Integration 6.x và Spring Data/Spring Kafka được BOM của ứng dụng quản lý. Với Spring Integration 7.x hoặc Spring Kafka 4.x, tên một số API, defaults và mapper implementation có thể đổi. Cần kiểm tra Javadoc đúng phiên bản trước khi triển khai thực tế. Các URI/broker trong ví dụ là môi trường lab, không chứa credentials production.

## 1. Bài toán: một Spring Message gửi ra ba hệ thống

Giả sử upstream HTTP/Kafka/JMS chuyển một order event vào Spring Integration. Message sau validation có dạng:

~~~text
Message<String>
  payload = {"eventId":"evt-1001","orderId":"ord-101","status":"PAID"}
  headers:
    businessEventId  = "evt-1001"
    appTraceId       = "trace-5e1"
    trustedTenantId  = "tenant-a"
    sourceSystem     = "order-service"
    internalRole     = "ROLE_OPERATOR"
    replyChannel     = <Spring MessageChannel object>
    id               = <Spring Message UUID>
    timestamp        = <Spring timestamp>
~~~

Ứng dụng muốn:

1. Gửi HTTP POST tới API đối tác, có `Content-Type` và `X-Event-Id`.
2. Gửi JMS message cho một consumer legacy, với JMS string property `businessEventId`.
3. Gửi Kafka record có key theo orderId và custom header `businessEventId`.

**Không được sao chép nguyên xi tất cả Spring headers** ra cả ba giao thức. Ví dụ `replyChannel` có kiểu `MessageChannel` không thể là HTTP/JMS/Kafka wire metadata; `internalRole` và `trustedTenantId` có thể làm lộ dữ liệu/đặc quyền; Kafka offset/AMQP deliveryTag không có nghĩa ở hệ thống đích.

~~~mermaid
flowchart LR
    M["Spring Message<br/>payload + app headers"] --> V["Validate + allowlist"]
    V --> R["Route by trusted destination"]
    R --> HTTP["HTTP HeaderMapper<br/>Spring → HttpHeaders"]
    R --> JMS["JmsHeaderMapper<br/>Spring → JMS"]
    R --> AMQP["AmqpHeaderMapper<br/>Spring → MessageProperties"]
    R --> K["KafkaHeaderMapper<br/>Spring → Kafka Headers"]
    HTTP --> H["Partner HTTP API"]
    JMS --> J["JMS Broker"]
    AMQP --> A["RabbitMQ"]
    K --> B["Kafka Broker"]
~~~

**Một thông điệp gốc, nhiều outbound contracts.** HeaderMapper ở đây là thành phần chọn và chuyển *metadata*, không làm mã hóa JSON payload, chọn destination hoặc commit transaction xuyên các hệ thống.

## 2. HeaderMapper<T>: API và chiều outbound

Spring Integration định nghĩa:

~~~java
package org.springframework.integration.mapping;

import java.util.Map;
import org.springframework.messaging.MessageHeaders;

public interface HeaderMapper<T> {

    void fromHeaders(MessageHeaders headers, T target);

    Map<String, Object> toHeaders(T source);
}
~~~

| Phương thức | Nguồn | Đích | Khi nào dùng? |
|---|---|---|---|
| **`fromHeaders(headers, target)`** | Spring `MessageHeaders` | HTTP `HttpHeaders` / JMS message / AMQP properties | **Outbound** Spring → external |
| **`toHeaders(source)`** | External metadata | `Map<String,Object>` tạo Spring headers | **Inbound** external → Spring |
| `MessageConverter` | Spring payload | JSON, JMS TextMessage, AMQP body, Kafka bytes... | Payload conversion |
| Destination expression | Spring Message / config | URI, queue, exchange/routing key, Kafka topic... | Chọn nơi gửi |
| Endpoint handler | Spring Message | I/O operation | Gửi và nhận lỗi/ACK theo transport |

**Quy tắc nhớ:** `fromHeaders` = *đưa các headers từ Spring Message ra đối tượng ngoài*. Nó không làm ngược lại.

### 2.1. Một ví dụ thuần mapper

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

DefaultHttpHeaderMapper mapper =
        DefaultHttpHeaderMapper.outboundMapper();

mapper.setOutboundHeaderNames(
    "Content-Type", "X-Event-Id", "X-Trace-Id");

Message<String> message =
    MessageBuilder.withPayload("{\"orderId\":\"ord-101\"}")
        .setHeader("X-Event-Id", "evt-1001")
        .setHeader("X-Trace-Id", "trace-5e1")
        .setHeader("internalRole", "ROLE_OPERATOR")
        .build();

HttpHeaders target = new HttpHeaders();
mapper.fromHeaders(message.getHeaders(), target);

// target có các HTTP headers hợp lệ đã được chọn;
// internalRole không được ánh xạ vì không nằm trong allowlist.
~~~

Đây là ví dụ của **mapping**, không gọi HTTP và không chứng minh gửi mạng đã thành công.

### 2.2. “Outbound gateway” dùng cả hai hướng

Một HTTP **outbound channel adapter** có request nhưng không trả Spring reply message. Một HTTP **outbound gateway** gửi request và nhận response:

~~~mermaid
sequenceDiagram
    participant F as Spring Integration flow
    participant HM as HeaderMapper
    participant HTTP as HTTP server
    F->>HM: fromHeaders(Spring MessageHeaders, HttpHeaders)
    HM-->>F: outgoing request headers
    F->>HTTP: HTTP request (body + headers)
    HTTP-->>F: HTTP response (status + response headers + body)
    F->>HM: toHeaders(HttpHeaders response)
    HM-->>F: inbound Spring response headers
    Note over F: Response payload do message converter xử lý
~~~

Vì thế, **`DefaultHttpHeaderMapper.outboundMapper()`** có thể đồng thời cấu hình **`outboundHeaderNames` cho request** và **`inboundHeaderNames` cho response**. Không nhầm inbound/outbound ở đây với hướng toàn bộ endpoint.

## 3. Những headers nào có thể và không nên xuất?

| Nhóm | Ví dụ Spring header | Policy outbound |
|---|---|---|
| Business ID | `businessEventId` | Map nếu partner contract cần idempotency |
| Tracing | `appTraceId`, trace context | Map theo W3C/partner tracing format, validate |
| Content metadata | `contentType`, `schemaVersion` | Map/convert theo protocol, không ép kiểu mù |
| Tenant | `trustedTenantId` | Chỉ gửi nếu downstream được phép nhận; thường chuyển sang partner-scoped identifier |
| Spring core | `id`, `timestamp` | Không coi là business ID; thường loại |
| Spring routing | `replyChannel`, `errorChannel` | **Không gửi** sang external hệ thống |
| Security internal | `internalRole`, internal JWT, API token | **Không copy**; tạo outbound authentication riêng |
| HTTP request metadata | `http_requestMethod`, `http_requestUrl` | Không tự map lại thành request partner |
| Kafka received metadata | received topic/partition/offset/ack object | Không copy như arbitrary Kafka/JMS headers |
| AMQP received metadata | deliveryTag, receivedExchange, receivedRoutingKey | Không tái sử dụng như outbound QoS |
| JMS received metadata | JMSMessageID, redelivered, expiration | Không tự tái sử dụng provider-managed fields |
| File/SFTP source metadata | remote file/directory | Chỉ dùng cho routing đã được authorize, không auto forward |
| Retry counters | `deliveryAttempt`, custom retry metadata | Chỉ xuất nếu business contract thực sự cần |

### 3.1. Mapping, enrichment và filtering

Có ba lớp khác nhau:

- **HeaderEnricher** (trong flow): bổ sung/canonicalize application headers.
- **HeaderFilter** (trong flow): loại bỏ internal/untrusted headers.
- **HeaderMapper** (tại outbound adapter/gateway): ánh xạ các headers **được phép** sang giao thức đích.

Một flow cứng cáp thường thực hiện cả ba, nhưng không sao chép cùng một bộ headers cho mọi destination.

### 3.2. Spring Message ID không phải eventId

Spring `MessageHeaders.ID` có thể thay khi rebuild message, redelivery hoặc qua hệ thống khác. Kafka record key, JMSMessageID, AMQP messageId và HTTP X-Request-Id cũng có phạm vi/generation rules khác nhau. Nếu cần dedup, duy trì **business event ID ổn định** với tenant/source scope, dùng cho mọi lần retry.

## 4. HTTP outbound: DefaultHttpHeaderMapper

Class:

~~~java
org.springframework.integration.http.support.DefaultHttpHeaderMapper
~~~

Factory:

~~~java
DefaultHttpHeaderMapper.outboundMapper();
DefaultHttpHeaderMapper.inboundMapper();
~~~

Với **HTTP outbound adapter/gateway**, dùng **`outboundMapper()`**.

### 4.1. Hai chiều trong HTTP outbound gateway

| API | Ý nghĩa với HTTP outbound gateway |
|---|---|
| `outboundMapper()` | Factory cho HTTP outbound endpoint |
| `setOutboundHeaderNames(...)` | **Spring request headers → HTTP request headers** |
| `setInboundHeaderNames(...)` | **HTTP response headers → Spring reply headers** |
| `fromHeaders(MessageHeaders, HttpHeaders)` | Dựng HTTP request metadata |
| `toHeaders(HttpHeaders response)` | Đọc HTTP response metadata |
| `HTTP_REQUEST_HEADERS` | Pattern token cho standard HTTP request fields |
| `HTTP_RESPONSE_HEADERS` | Pattern token cho standard HTTP response fields |

Không gọi `setInboundHeaderNames("X-Event-Id")` rồi trông đợi HTTP request gửi X-Event-Id: thuộc tính này kiểm soát **headers nhận từ response**, không phải headers request gửi đi.

### 4.2. Bean allowlist request và response

~~~java
package example.headersout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

@Configuration
public class PartnerHttpMapperConfig {

    @Bean("partnerHttpHeaderMapper")
    public DefaultHttpHeaderMapper partnerHttpHeaderMapper() {

        DefaultHttpHeaderMapper mapper =
                DefaultHttpHeaderMapper.outboundMapper();

        mapper.setOutboundHeaderNames(
            "Content-Type",
            "Accept",
            "X-Event-Id",
            "X-Trace-Id");

        mapper.setInboundHeaderNames(
            "Content-Type",
            "X-Partner-Request-Id");

        return mapper;
    }
}
~~~

- Allowlist ghi tường minh sẽ **override danh sách default**. Nếu cần đầy đủ standard headers, dùng token `HTTP_REQUEST_HEADERS`/`HTTP_RESPONSE_HEADERS` hoặc thêm chính xác các tên cần.
- Mapper không phải chỗ sinh/refresh OAuth access token; token outbound chỉ được gắn bởi security-aware client component từ nguồn trusted, không mirror raw inbound Authorization.
- HTTP header names **case-insensitive**, nhưng Spring MessageHeaders key lookup có quy tắc Java map/mapper. Đặt tên canonical và test casing.
- HTTP headers có thể multi-valued, không đơn giản cast mọi value sang String.

### 4.3. Java DSL: HTTP outbound gateway

~~~java
package example.headersout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.http.dsl.Http;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

@Configuration
@EnableIntegration
public class PartnerHttpOutboundFlow {

    @Bean
    public IntegrationFlow partnerHttpOutbound(
            DefaultHttpHeaderMapper partnerHttpHeaderMapper) {

        return IntegrationFlow.from("sendToPartner")
            .handle(Http.outboundGateway(
                    "http://localhost:8091/api/orders/events")
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(String.class)
                .headerMapper(partnerHttpHeaderMapper))
            .channel("partnerReplies")
            .get();
    }
}
~~~

Giải thích:

1. `sendToPartner` nhận Spring Message đã có payload và headers được validate.
2. `Http.outboundGateway(...)` gửi HTTP request tới URL cố định trong lab.
3. `.headerMapper(...)` dùng `fromHeaders(...)` để gắn allowlisted request headers.
4. Body được HTTP converter serialize; `HeaderMapper` không phải JSON serializer.
5. Response quay lại Spring Message; mapper dùng `toHeaders(...)` cho selected response fields.
6. `partnerReplies` cần downstream consumer; nếu không có, flow có thể không dispatch thành công tùy channel topology.
7. Đây là **request/reply** gateway; nếu chỉ cần one-way send, dùng `Http.outboundChannelAdapter(...)`.

**Không đưa URL từ raw request header của người dùng vào expression outbound**: có thể gây SSRF. Dùng URL/host allowlist được server cấu hình và kiểm tra TLS/timeouts.

### 4.4. DSL mappedRequestHeaders không cần custom mapper bean

Có thể dùng DSL config đơn giản:

~~~java
Http.outboundGateway("http://localhost:8091/api/orders/events")
    .httpMethod(HttpMethod.POST)
    .mappedRequestHeaders(
        "HTTP_REQUEST_HEADERS",
        "X-Event-Id",
        "X-Trace-Id")
    .mappedResponseHeaders(
        "X-Partner-Request-Id",
        "HTTP_RESPONSE_HEADERS");
~~~

Đây là **builder fragment**, cần gắn vào `IntegrationFlow.handle(...)`. Với rule custom phức tạp, chọn `.headerMapper(partnerHttpHeaderMapper)` **thay vì đồng thời** cấu hình mapped lists và custom mapper khi API không cho precedence rõ.

### 4.5. XML outbound adapter/gateway

~~~xml
<!-- Cần namespaces int, int-http; bean partnerHttpHeaderMapper
     và các channels phải tồn tại. -->
<int-http:outbound-gateway
    id="partnerHttpGateway"
    url="http://localhost:8091/api/orders/events"
    http-method="POST"
    request-channel="sendToPartner"
    reply-channel="partnerReplies"
    header-mapper="partnerHttpHeaderMapper"/>
~~~

Hoặc một outbound adapter XML không reply:

~~~xml
<int-http:outbound-channel-adapter
    id="partnerHttpFireAndForget"
    url="http://localhost:8091/api/orders/events"
    http-method="POST"
    channel="sendToPartner"
    mapped-request-headers="Content-Type,X-Event-Id,X-Trace-Id"/>
~~~

Đây là **hai phương án độc lập**: không đăng ký cùng một channel gửi đi tới cả gateway và adapter nếu không chủ định multicast/competing consumers. HTTP “one-way” không có nghĩa client call đã chứng minh downstream DB transaction hoàn tất; HTTP response status và business ACK có hai nghĩa khác nhau.

### 4.6. Test fromHeaders mà không gửi network

~~~java
package example.headersout;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class HttpOutboundMapperTest {

    @Test
    void onlyApprovedHeadersLeaveService() {
        DefaultHttpHeaderMapper mapper =
                DefaultHttpHeaderMapper.outboundMapper();

        mapper.setOutboundHeaderNames(
            "X-Event-Id", "X-Trace-Id");

        Message<String> source =
            MessageBuilder.withPayload("hello")
                .setHeader("X-Event-Id", "evt-1001")
                .setHeader("X-Trace-Id", "trace-5e1")
                .setHeader("internalRole", "admin")
                .setHeader("Authorization", "internal-secret")
                .build();

        HttpHeaders requestHeaders = new HttpHeaders();
        mapper.fromHeaders(source.getHeaders(), requestHeaders);

        assertEquals(
            "evt-1001",
            requestHeaders.getFirst("X-Event-Id"));

        assertEquals(
            "trace-5e1",
            requestHeaders.getFirst("X-Trace-Id"));

        assertFalse(requestHeaders.containsKey("internalRole"));
        assertFalse(requestHeaders.containsKey("Authorization"));
    }
}
~~~

Đây là **unit test policy**, chưa xác minh HTTP gateway thật đang dùng đúng mapper bean. Integration test cần mock HTTP server và capture request thực tế (bao gồm header names, values, body, timeout).
## 5. HTTP authentication, tracing và response headers

### 5.1. Không sao chép raw Authorization inbound

Nếu một HTTP inbound request có:

~~~http
Authorization: Bearer external-client-token
X-Partner-Event-Id: evt-1001
~~~

đừng cho mapper của **outbound HTTP** tự forward cùng `Authorization` đến đối tác khác. Token nguồn có **audience, scope, tenant và thời hạn** của người gọi, không phải của service khi gọi downstream.

Policy tốt hơn:

1. HTTP ingress xác thực token nguồn và tenant.
2. Business flow mang **identity tối thiểu đã kiểm chứng**, không raw secret.
3. Outbound HTTP client nhận token **đúng audience của đích** từ credential provider/authorized client.
4. HeaderMapper chỉ đưa ra metadata cho phép, hoặc client interceptor chịu trách nhiệm đặt Authorization mới.
5. Không log/trace raw token; test không có token nguồn nào tới target server.

Nếu dùng `RestTemplate`/Spring `WebClient` cùng HTTP outbound gateway, chọn client security interceptor/filter theo stack và version; không tạo access token trực tiếp trong `HeaderMapper.fromHeaders` nếu cần I/O network vì mapper cần deterministic/bounded.

### 5.2. Correlation và W3C trace context

Ví dụ ứng dụng có `appTraceId` và muốn đối tác nhìn thấy `traceparent` theo chuẩn W3C. **Không chỉ đổi tên** appTraceId thành traceparent: W3C format có version, trace-id, parent-id và trace-flags. Sử dụng tracing instrumentation/propagator chính thức của Spring Observability/OpenTelemetry khi có thể.

Khi buộc map một custom header:

~~~java
Message<?> outbound = MessageBuilder.fromMessage(inbound)
    .setHeader("X-Event-Id", verifiedEventId)
    .setHeader("X-Trace-Id", validatedTraceHint)
    .removeHeader("X-External-Tenant-Role")
    .build();
~~~

Fragment này đòi `verifiedEventId` được ràng buộc với payload và tenant; `validatedTraceHint` có size/charset kiểm soát. Dù HTTP server trả 2xx, điều đó **không chứng minh Kafka/JMS downstream đã commit** nếu HTTP API là async.

### 5.3. Đọc response headers ở outbound gateway

Sau HTTP outbound request, gateway có thể đưa vào Spring reply:

~~~text
HTTP/1.1 202 Accepted
X-Partner-Request-Id: r-889
Retry-After: 4
Content-Type: application/json
~~~

Nếu cấu hình `mapper.setInboundHeaderNames("X-Partner-Request-Id","Retry-After","Content-Type")`, phương thức `toHeaders(HttpHeaders)` chuyển **HTTP response metadata → Spring reply headers**.

**Lưu ý:**

- Status 202 nghĩa server đã **chấp nhận request**, chưa chắc business effect đã hoàn tất.
- `Retry-After` có thể dùng trong retry policy nhưng phải parse/validate và giới hạn thời gian; không blindly sleep theo một header không tin cậy.
- Reply message headers có thể chứa HTTP status code/platform metadata bổ sung ngoài mapper.
- Đừng chọn routing/reply channel dựa trực tiếp trên untrusted HTTP response header.

### 5.4. Mapping không làm request body đúng schema

HTTP `Content-Type: application/json` không tự khiến payload String trở thành DTO hợp lệ. HTTP message converter xử lý body; business validation xử lý schema; mapper xử lý headers. Nếu upstream payload là file bytes nhưng Content-Type là JSON, request có thể bị downstream từ chối hoặc hiểu nhầm. Kiểm thử cả **header và body wire-level**.

## 6. JMS outbound: DefaultJmsHeaderMapper

Class và các phụ thuộc quan trọng trong Spring Integration 6.x:

~~~java
org.springframework.integration.jms.DefaultJmsHeaderMapper
org.springframework.integration.jms.JmsHeaderMapper
org.springframework.integration.jms.JmsHeaders
org.springframework.integration.jms.outbound.JmsSendingMessageHandler
org.springframework.integration.jms.dsl.Jms
jakarta.jms.ConnectionFactory
jakarta.jms.Message
~~~

`DefaultJmsHeaderMapper` ánh xạ Spring MessageHeaders sang standard JMS headers và custom JMS properties **khi hỗ trợ**. Một số JMS fields do provider hoặc producer send API đặt, vì thế không thể “gán tùy ý” qua property mapper.

### 6.1. Bảng JMS headers

| Spring header | JMS metadata | Quy tắc outbound |
|---|---|---|
| `JmsHeaders.CORRELATION_ID` / `jms_correlationId` | `JMSCorrelationID` | Dùng cho request/reply, String format phù hợp |
| `correlationId` | JMS custom property (String) theo mapper | Khác `JMSCorrelationID`; thường phục vụ aggregator |
| `JmsHeaders.TYPE` / `jms_type` | `JMSType` | Chỉ khi partner dùng type contract |
| `JmsHeaders.REPLY_TO` / `jms_replyTo` | `JMSReplyTo` | JMS Destination hợp lệ, không tin input tùy ý |
| `businessEventId` | Custom JMS String property | Business idempotency |
| `appTraceId` | Custom JMS String property | Tracing |
| `priority` | JMS producer send QoS | Không kỳ vọng mapper tự quyết định JMSPriority |
| `jms_deliveryMode` | JMS producer QoS | Phải dùng JmsTemplate/endpoint QoS |
| `jms_expiration` | Expiration/TTL semantics | TTL tính tại thời điểm gửi, không copy expiry cũ |
| `jms_messageId` | `JMSMessageID` do provider gán | Không tự set bằng Spring Message ID |
| `jms_redelivered` | `JMSRedelivered` do provider quản lý | Không chuyển từ received message để giả lập redelivery |

### 6.2. Vì sao Priority, TTL, delivery mode khác các JMS properties thường?

Spring Integration JmsSendingMessageHandler dùng `JmsTemplate`/`DynamicJmsTemplate` và JMS producer send API để áp dụng QoS; một số fields như JMSPriority/deliveryMode/expiration do broker/provider tính và set ở **send time**.

Ví dụ XML từ Spring Integration JMS docs có:

~~~xml
<int-jms:outbound-channel-adapter
    id="jmsOut"
    channel="outgoingJms"
    destination-name="orders.out"
    delivery-mode-expression="headers.jms_deliveryMode"
    time-to-live-expression="headers.jms_expiration - T(System).currentTimeMillis()"/>
~~~

Đây là fragment có tính minh họa; TTL expression có thể âm khi message hết hạn, vì vậy **production phải giới hạn TTL vào khoảng được phép** và kiểm tra clock skew. Khi sử dụng JMS dynamic QoS, `explicitQosEnabled` phải được bật trên JmsTemplate/producer theo cấu hình phù hợp.

Không lấy `JMSExpiration` cũ từ một inbound message rồi forward nguyên số vào outbound JMS như một property và mong broker tự diễn giải thành expiry mới.

### 6.3. Java DSL JMS outbound adapter

~~~java
package example.headersout;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class JmsOrderOutboundConfig {

    @Bean
    public DefaultJmsHeaderMapper jmsOutboundHeaderMapper() {
        return new DefaultJmsHeaderMapper();
    }

    @Bean
    public IntegrationFlow jmsOrdersOut(
            ConnectionFactory connectionFactory,
            DefaultJmsHeaderMapper jmsOutboundHeaderMapper) {

        return IntegrationFlow.from("sendToJms")
            .handle(Jms.outboundAdapter(connectionFactory)
                .destination("orders.events")
                .headerMapper(jmsOutboundHeaderMapper))
            .get();
    }
}
~~~

Giải thích:

1. `sendToJms` là Spring input MessageChannel.
2. `Jms.outboundAdapter(...)` tạo one-way JMS sending handler.
3. `.headerMapper(...)` dùng `fromHeaders(...)` để đặt JMS-compatible headers/properties.
4. `MessageConverter` chuyển payload thành JMS TextMessage/BytesMessage/loại tương ứng; **không** dùng HeaderMapper để serialize payload.
5. ConnectionFactory, destination, producer credentials, timeout, transaction và broker ACK cần cấu hình riêng.
6. Không tự giả định một `send()==true` ở upstream async QueueChannel đã chứng minh broker receive/commit.

Trong production, cân nhắc **tạo outbound message sạch** trước adapter để mapper không gặp arbitrary object headers từ inbound sources khác.

### 6.4. Gửi một business event với JMS-friendly property types

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> orderEvent =
    MessageBuilder.withPayload(
            "{\"eventId\":\"evt-1001\",\"status\":\"PAID\"}")
        .setHeader("businessEventId", "evt-1001")
        .setHeader("appTraceId", "trace-5e1")
        .setHeader("schemaVersion", "1")
        .build();
~~~

JMS property types được provider hỗ trợ gồm primitive/wrapper/String theo JMS specification; một `Map<String,Object>`, `MessageChannel`, `Instant`, `BigDecimal` hoặc Kafka acknowledgment object **không mặc nhiên thành JMS property hợp lệ**. Convert chúng sang String/primitive theo schema hoặc lọc bỏ.

### 6.5. JMS correlation khác application correlation

Nếu dùng outbound **JMS gateway** request/reply, `JMSCorrelationID` có thể được gateway sinh/tự quản lý để match replies. Một `jms_correlationId` được đưa vào MessageHeaders có thể ảnh hưởng behavior tùy `correlation-key` và config. Đừng tự ghi đè correlation property cho mọi request chỉ để truyền `appTraceId`.

- Dùng business event ID trong property `businessEventId` cho dedup.
- Dùng tracing ID trong `appTraceId`.
- Để JMS gateway quản lý request/reply correlation theo contract đã cấu hình.
- Khi thực sự cần dùng JMSCorrelationID do app cung cấp, bật cấu hình phù hợp và test với JMS broker/provider.

### 6.6. JMS XML outbound adapter

~~~xml
<!-- Requires int-jms namespace, ConnectionFactory and destination. -->
<int-jms:outbound-channel-adapter
    id="outJms"
    channel="sendToJms"
    connection-factory="jmsConnectionFactory"
    destination-name="orders.events"
    header-mapper="jmsOutboundHeaderMapper"/>
~~~

Là cấu hình thay thế Java DSL, không đăng ký cả hai trên cùng consumer channel trừ khi bạn muốn cạnh tranh nhận hoặc broadcast có chủ đích.

### 6.7. JMS one-way vs gateway

| Endpoint | Chức năng | HeaderMapper |
|---|---|---|
| JMS outbound channel adapter | Gửi message, thường không có reply message | Spring → JMS qua `fromHeaders(...)` |
| JMS outbound gateway | Gửi request rồi chờ/nhận JMS reply | Cả `fromHeaders(...)` khi gửi và `toHeaders(...)` khi nhận reply |
| JMS inbound gateway | Nhận JMS request rồi trả JMS reply | Ngược lại theo request/reply direction |
| JMS message-driven inbound adapter | Nhận JMS message | JMS → Spring qua `toHeaders(...)` |

HeaderMapper **không** thay `JmsTemplate`/session transaction hoặc broker ACK. Cần kiểm thử message listener, timeout, redelivery và reply correlation end-to-end.

## 7. AMQP outbound: DefaultAmqpHeaderMapper và MessageProperties

AMQP/RabbitMQ có metadata trong `org.springframework.amqp.core.MessageProperties`, được Spring Integration chuyển từ `MessageHeaders` qua:

~~~java
org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper
org.springframework.integration.amqp.support.AmqpHeaderMapper
org.springframework.amqp.core.MessageProperties
org.springframework.amqp.support.AmqpHeaders
~~~

### 7.1. Request headers trong outbound AMQP nghĩa là gì?

`DefaultAmqpHeaderMapper` có hai tập policy thường gặp:

- **`requestHeaderNames`**: mapping **Spring MessageHeaders ↔ AMQP request metadata**, gồm outbound adapter/gateway request.
- **`replyHeaderNames`**: mapping ở hướng reply khi có AMQP gateway.

Với AMQP outbound adapter **một chiều**, tập trung vào **`setRequestHeaderNames(...)`** để cho phép các custom headers bạn chủ động gửi.

Bảng ví dụ:

| Spring header | AMQP field/properties | Điều cần lưu ý |
|---|---|---|
| `contentType` | `MessageProperties.contentType` | Không dùng `amqp_` prefix |
| `amqp_messageId` | AMQP messageId | ID của producer/application tùy policy |
| `amqp_correlationId` | AMQP correlationId | Request/reply, không tự là business event ID |
| `businessEventId` | Custom AMQP header | Nên là stable String/bytes hợp lệ |
| `appTraceId` | Custom AMQP header | Xác minh charset/length |
| `amqp_receivedExchange` | Broker metadata từ inbound | **Không xuất nguyên trạng** làm exchange mới |
| `amqp_receivedRoutingKey` | Inbound received routing | Routing outbound phải do endpoint quyết định |
| `amqp_deliveryTag` | Delivery tag của lần nhận trước | **Không forward** qua new delivery |
| `amqp_redelivered` | Received flag | Không được producer “set lại” để tạo redelivery |
| `x-received-from` | RabbitMQ federation metadata | **Không copy** khi gửi/reply |

### 7.2. Cấu hình outbound allowlist

~~~java
package example.headersout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

@Configuration
public class PartnerAmqpMapperConfig {

    @Bean
    public DefaultAmqpHeaderMapper outboundAmqpHeaderMapper() {
        DefaultAmqpHeaderMapper mapper =
                new DefaultAmqpHeaderMapper();

        mapper.setRequestHeaderNames(
            "STANDARD_REQUEST_HEADERS",
            "businessEventId",
            "appTraceId",
            "!x-*",
            "!Authorization");

        return mapper;
    }
}
~~~

**Chú ý version:** Spring Integration reference và một số Javadoc cũ khác nhau ở mô tả **default mapping custom AMQP headers**; reference hiện đại nói nhiều custom properties được copy tự động nhưng mặc định loại `x-*` ở outbound, trong khi Javadoc của một số versions mô tả chỉ standard fields. **Không dựa vào default mơ hồ:** chỉ định allowlist và kiểm thử đúng artifacts/version.

Khi dùng pattern `STANDARD_REQUEST_HEADERS`, bạn giữ các standard AMQP fields hợp lệ theo mapper; những header khác không nên được xuất trừ khi được list. Negated patterns `!x-*` được ưu tiên và chặn broker-internal metadata.

### 7.3. Java DSL AMQP outbound adapter

~~~java
package example.headersout;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class RabbitOutboundConfig {

    @Bean
    public IntegrationFlow orderEventsToRabbit(
            RabbitTemplate rabbitTemplate,
            DefaultAmqpHeaderMapper outboundAmqpHeaderMapper) {

        return IntegrationFlow.from("sendToRabbit")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName("partner.events")
                .routingKey("orders.paid")
                .headerMapper(outboundAmqpHeaderMapper))
            .get();
    }
}
~~~

- Exchange/routing key trong demo là **trusted application config**, không phải raw inbound header.
- HeaderMapper copy các standard/custom metadata được phép sang MessageProperties.
- Payload/body do Spring AMQP MessageConverter xử lý.
- Broker exchange/queue/binding, connection/credential và publisher confirm/return policy phải có riêng.
- Nếu route động, dùng `routingKeyExpression` hoặc `routingKeyFunction` **trên header đã được validate/allowlist**, không dùng tên exchange do client gửi tùy tiện.

### 7.4. Unit test từ Spring headers sang AMQP properties

~~~java
package example.headersout;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class AmqpOutboundMapperTest {

    @Test
    void exportsApprovedBusinessMetadataOnly() {
        DefaultAmqpHeaderMapper mapper =
                new DefaultAmqpHeaderMapper();

        mapper.setRequestHeaderNames(
            "STANDARD_REQUEST_HEADERS",
            "businessEventId",
            "!x-*");

        Message<String> message =
            MessageBuilder.withPayload("hello")
                .setHeader("businessEventId", "evt-1001")
                .setHeader("x-received-from", "internal-broker")
                .setHeader("internalRole", "admin")
                .build();

        MessageProperties target = new MessageProperties();
        mapper.fromHeaders(message.getHeaders(), target);

        assertEquals(
            "evt-1001",
            target.getHeaders().get("businessEventId"));

        assertFalse(target.getHeaders()
            .containsKey("x-received-from"));

        assertFalse(target.getHeaders()
            .containsKey("internalRole"));
    }
}
~~~

Nếu test này fail vì version cụ thể dùng khác token/naming rule, cần đối chiếu Javadoc, không nới policy thành `*` để test qua.

### 7.5. AMQP publisher confirms và returns khác mapping

Gửi RabbitMQ có nhiều mốc:

1. Spring Integration handler chấp nhận/biến đổi message.
2. RabbitTemplate gửi AMQP message tới broker.
3. Broker có thể gửi **publisher confirm** ACK/NACK, nếu connection/channel đã bật.
4. Message có thể bị **returned** nếu không route được và mandatory/return callbacks được cấu hình.
5. Consumer có thể nhận/redeliver/ACK sau đó.

**Một MessageHeaders đã được map thành công không chứng minh (3), (4) hay (5).** Với Spring Integration AMQP outbound adapter có các tùy chọn `confirmAckChannel`, `confirmNackChannel`, `returnChannel` và `waitForConfirm` tùy version/endpoint. Kiểm thử cả positive, unroutable và negative confirm cases.

### 7.6. Vì sao không forward x-* từ broker?

RabbitMQ federation có thể gắn `x-received-from` hoặc các broker-specific `x-*` headers. Nếu một inbound AMQP message mang metadata đó sang outbound/reply, federation có thể hiểu nhầm là message loop và drop. Đừng sử dụng pattern wildcard `*` bất chấp nguồn. Nếu có yêu cầu giữ một plugin header như `x-delay`, **tách policy riêng cho đúng broker/plugin** và validate TTL/delay; không mở hết `x-*`.

### 7.7. AMQP XML outbound

~~~xml
<!-- Requires int-amqp namespace, RabbitTemplate, exchange, channels. -->
<int-amqp:outbound-channel-adapter
    id="rabbitOut"
    channel="sendToRabbit"
    amqp-template="rabbitTemplate"
    exchange-name="partner.events"
    routing-key="orders.paid"
    header-mapper="outboundAmqpHeaderMapper"/>
~~~

Một endpoint XML khác có thể dùng `mapped-request-headers` thay `header-mapper`; hai cách có thể loại trừ nhau. Cần kiểm tra schema của version thực tế và không cấu hình hai hướng/mappers cạnh tranh.
## 8. Kafka outbound: KafkaHeaderMapper thuộc Spring Kafka

Kafka producer record gồm **topic, partition, key, timestamp, value và headers**. Headers của Kafka wire-level là một tập những entry:

~~~java
package org.apache.kafka.common.header;

public interface Header {
    String key();
    byte[] value();
}
~~~

Spring Kafka cung cấp interface **khác** Spring Integration generic HeaderMapper:

~~~java
package org.springframework.kafka.support;

import org.apache.kafka.common.header.Headers;
import org.springframework.messaging.MessageHeaders;
import java.util.Map;

public interface KafkaHeaderMapper {
    void fromHeaders(MessageHeaders headers, Headers target);
    void toHeaders(Headers source, Map<String, Object> target);
}
~~~

Ở đây `fromHeaders(...)` vẫn là outbound, nhưng **generic type và signature khác** interface `org.springframework.integration.mapping.HeaderMapper<T>`. Đừng inject một `DefaultHttpHeaderMapper` vào Kafka producer converter.

### 8.1. Các implementation và khác biệt version

| Lựa chọn | Hành vi | Khi nào nên chọn? |
|---|---|---|
| `SimpleKafkaHeaderMapper` | Chủ yếu map raw header values dạng `byte[]`, hỗ trợ cấu hình raw String | Hợp đồng với consumer ngoài Spring, ít type metadata |
| `DefaultKafkaHeaderMapper` (Spring Kafka 3.x) | JSON-serialize Java values và type hints | Hai bên Spring Kafka muốn type round-trip |
| `JsonKafkaHeaderMapper` (tài liệu Spring Kafka 4.x) | JSON mapping tương tự, thêm multi-value policy theo version | Spring Kafka 4.x / kiểu phức tạp có schema |
| Custom `KafkaHeaderMapper` | Tự kiểm soát serialization/patterns | Legacy wire format hoặc yêu cầu bảo mật riêng |

**Quan trọng:** những class `DefaultKafkaHeaderMapper`/`JsonKafkaHeaderMapper` và defaults có thể khác theo Spring Kafka version. Bài dùng `SimpleKafkaHeaderMapper` cho ví dụ raw bytes tương thích thông dụng; kiểm tra Javadoc/BOM trước khi đổi tên class hoặc bật JSON typed headers.

### 8.2. Tại sao không copy id/timestamp/received metadata?

KafkaHeaderMapper thường loại Spring `id`, `timestamp` và các Kafka headers có ý nghĩa như **record metadata**, ví dụ received topic/partition/offset. Những metadata này do `ConsumerRecord`/`ProducerRecord` hoặc producer endpoint quản lý, không phải arbitrary custom Kafka headers cần forward.

| Spring header | Kafka record | Có nên map như custom header? |
|---|---|---|
| `KafkaHeaders.TOPIC` | ProducerRecord.topic | Không; là destination control |
| `KafkaHeaders.KEY` | ProducerRecord.key | Không; key ảnh hưởng partition/order |
| `KafkaHeaders.PARTITION` | ProducerRecord.partition | Không; explicit partitioning cần policy |
| `KafkaHeaders.RECEIVED_TOPIC` | Metadata từ consumer nguồn | Không chuyển thành topic mới |
| `KafkaHeaders.OFFSET` | Received Kafka offset | Không chuyển thành business ID |
| `KafkaHeaders.ACKNOWLEDGMENT` | Listener ACK object | Không serialize ra broker |
| `businessEventId` | Kafka custom header | Có, theo format đã thỏa thuận |
| `schemaVersion` | Kafka custom header | Có, dạng bytes/String/JSON có schema |
| `appTraceId` | Kafka custom header | Có, nếu tracing contract yêu cầu |

Một Kafka record key có thể giúp ordering theo aggregate, nhưng **không tự bảo đảm dedup xuyên retry**: app cần business event ID và idempotent consumer/outbox.

### 8.3. Raw byte policy với SimpleKafkaHeaderMapper

~~~java
package example.headersout;

import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class KafkaHeaderMappingDemo {

    public static RecordHeaders encodeEventId() {
        SimpleKafkaHeaderMapper mapper =
            new SimpleKafkaHeaderMapper(
                "businessEventId",
                "!id",
                "!timestamp");

        Message<byte[]> message =
            MessageBuilder.withPayload(new byte[] {1, 2, 3})
                .setHeader(
                    "businessEventId",
                    "evt-1001".getBytes(StandardCharsets.UTF_8))
                .setHeader("internalRole", "operator")
                .build();

        RecordHeaders kafkaHeaders = new RecordHeaders();
        mapper.fromHeaders(
            message.getHeaders(), kafkaHeaders);

        return kafkaHeaders;
    }
}
~~~

**Lý do dùng `byte[]`:** `SimpleKafkaHeaderMapper` chủ yếu giữ raw bytes. Trong consumer không phải Spring, decode bằng UTF-8 và kiểm tra length/charset/schema. Nếu dùng Java String trực tiếp với JSON mapper, wire representation có thể **không giống bytes văn bản thuần** và được gắn thêm type metadata.

### 8.4. Unit test Kafka record headers

~~~java
package example.headersout;

import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class KafkaOutboundMapperTest {

    @Test
    void onlyApprovedHeaderBecomesKafkaWireBytes() {
        RecordHeaders headers =
                KafkaHeaderMappingDemo.encodeEventId();

        assertArrayEquals(
            "evt-1001".getBytes(StandardCharsets.UTF_8),
            headers.lastHeader("businessEventId").value());

        assertNull(headers.lastHeader("internalRole"));
        assertNull(headers.lastHeader("id"));
    }
}
~~~

Đây là **mapper unit test**, không gửi Kafka record và không chứng minh producer ACK. Cần Kafka broker test để xác minh topic/key/partition, wire bytes, headers và retry/error channel đúng configuration thực tế.

### 8.5. Cấu hình Kafka converter theo Spring Kafka 3.x

~~~java
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;

MessagingMessageConverter converter =
        new MessagingMessageConverter();

converter.setHeaderMapper(
    new SimpleKafkaHeaderMapper(
        "businessEventId",
        "appTraceId",
        "!id",
        "!timestamp"));
~~~

**Đây là fragment**, phải gắn `converter` vào producer KafkaTemplate/handler theo API phiên bản. Kafka adapter sẽ xử lý outbound Spring Message → ProducerRecord, còn KafkaHeaderMapper chuyển **những custom headers** vào `RecordHeaders`.

Nếu dùng `DefaultKafkaHeaderMapper` (Spring Kafka 3.x) hoặc `JsonKafkaHeaderMapper` (Spring Kafka 4.x), cần giới hạn trusted classes/packages cho chiều inbound và biết nội dung header sẽ được JSON-serialize; không cho client chỉ định arbitrary class.

### 8.6. Spring Integration Kafka outbound flow

Spring Integration Kafka có DSL `Kafka.outboundChannelAdapter(kafkaTemplate)`:

~~~java
package example.headersout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.kafka.dsl.Kafka;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.KafkaHeaders;

@Configuration
@EnableIntegration
public class KafkaOrderOutboundConfig {

    @Bean
    public IntegrationFlow kafkaOrderEvents(
            KafkaTemplate<String, String> kafkaTemplate) {

        return IntegrationFlow.from("sendToKafka")
            .enrichHeaders(h -> h
                .header(KafkaHeaders.TOPIC, "orders.events"))
            .handle(Kafka.outboundChannelAdapter(kafkaTemplate))
            .get();
    }
}
~~~

Ứng dụng cần producer factory/serializers, Kafka brokers, ACLs, failure channels và KafkaTemplate converter có policy ở trên. Topic được gắn **server-side** qua HeaderEnricher; key/order ID cần quyết định từ business state đã validate. **Không nhận raw `KafkaHeaders.TOPIC` từ untrusted client** để cho producer gửi tới bất kỳ topic nào.

### 8.7. Tại sao multi-value headers cần test riêng?

Kafka record cho phép nhiều entries cùng key. Spring Kafka 4.x có multi-value header mapping opt-in với JSON mapper; mặc định có thể serialize collection thành một header hoặc chỉ expose giá trị cuối cùng khi đọc. Spring Kafka 3.x có behavior khác.

Ví dụ:

~~~text
Kafka Headers:
  tracing-hop: byte[]{A}
  tracing-hop: byte[]{B}
~~~

Không thể tự giả định `MessageHeaders.get("tracing-hop")` trả `List<byte[]>` hoặc khi outbound dùng List sẽ trở thành 2 Kafka headers. Nếu cần multiple values:

1. Chọn version có hỗ trợ.
2. Cấu hình multi-value header patterns.
3. Test wire-level record có đúng số entry/key/order.
4. Kiểm tra tương thích consumer không dùng Spring Kafka.
5. Không dùng multi-value cho business event ID nếu contract yêu cầu singleton.

### 8.8. Kafka broker ACK khác header mapping

- Kafka producer `acks`, retries và idempotence thuộc producer configuration, không do KafkaHeaderMapper.
- `send()==true` vào QueueChannel không chứng minh Kafka record đã được broker ACK.
- Spring Integration Kafka outbound handler có các chế độ sync/async và success/failure channels; application phải chọn ACK contract tương ứng.
- Một timeout ở producer có thể tạo **unknown result**; retry giữ cùng businessEventId, downstream dedup.
- Kafka producer idempotence giảm duplicate trong phạm vi producer protocol, nhưng **không tự thay idempotency xuyên MongoDB/HTTP/JMS**.

## 9. File outbound: FileHeaders.FILENAME và FileNameGenerator

File adapter là ví dụ quan trọng về **header ảnh hưởng outbound operation nhưng không cần generic HeaderMapper**. Spring Integration FileWritingMessageHandler dùng `FileNameGenerator` để chọn tên file.

Spring Integration cung cấp:

~~~java
org.springframework.integration.file.FileHeaders
org.springframework.integration.file.DefaultFileNameGenerator
org.springframework.integration.file.FileWritingMessageHandler
~~~

### 9.1. Hợp đồng tên file

Khi viết file, default file-name generator thường:

1. Dùng Spring header `FileHeaders.FILENAME` nếu có và hợp lệ.
2. Nếu payload là `java.io.File`, có thể dùng tên file payload.
3. Nếu không có, fallback theo Spring Message ID kèm `.msg`.

**Không dùng fallback Spring Message ID khi cần replay/idempotency**: sau restart hoặc redelivery, ID mới có thể tạo file khác dù cùng business event.

### 9.2. Chuẩn hóa outbound filename

~~~java
import org.springframework.integration.file.FileHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

String verifiedEventId = "evt-1001";

Message<String> document =
    MessageBuilder.withPayload(
            "{\"eventId\":\"evt-1001\",\"status\":\"PAID\"}")
        .setHeader(
            FileHeaders.FILENAME,
            verifiedEventId + ".json")
        .setHeader("businessEventId", verifiedEventId)
        .build();
~~~

**verifiedEventId** phải có charset/length không chứa slash, backslash, `..` hoặc control characters, và nên được tạo từ domain contract. Khi cấu hình cho phép tên file là child path, path traversal có thể xảy ra nếu sử dụng header không kiểm soát. Chỉ cho phép tên file theo root directory do server đặt.

### 9.3. File output không phải HTTP/JMS header mapping

~~~text
Spring Message
  payload         = JSON bytes / String / File
  file_name       = evt-1001.json
      ↓
FileWritingMessageHandler / FileNameGenerator
      ↓
/var/app/outgoing/evt-1001.json
~~~

Không cần `DefaultHttpHeaderMapper` cho local file write. Header này là **input cho naming policy** của FileWritingMessageHandler, không được viết vào file body trừ khi app tự serialize nó.

### 9.4. Overwrite, append và temporary-file strategy

Tên file đúng chưa đủ. Nếu event redeliver:

- `FileExistsMode.REPLACE` có thể ghi đè file cũ.
- `APPEND` có thể tạo dữ liệu trùng.
- `IGNORE` có thể bỏ một file mà nội dung cũ không khớp.
- `FAIL` làm flow lỗi, cần policy xử lý duplicate khác biệt.
- Temporary-file suffix/atomic rename (nếu adapter/FS hỗ trợ) giúp giảm rủi ro consumer đọc file chưa ghi xong.

Không coi file naming header là một transaction; cần write-complete policy, checksum/reconciliation và idempotency giữa source/destination.

## 10. FTP/SFTP/SMB outbound: remote path không phải header tùy ý

Remote file outbound adapter thường dùng `FileNameGenerator`, `remoteDirectory` hoặc expression để quyết định nơi đặt file; có thể đọc Spring Message headers như `FileHeaders.FILENAME`. Đây **không phải** một `HeaderMapper<T>` chung của mọi giao thức.

### 10.1. Ví dụ routing theo tenant có allowlist

~~~java
public String remoteDirectoryForTenant(String trustedTenantId) {
    return switch (trustedTenantId) {
        case "tenant-a" -> "/partners/a/inbox";
        case "tenant-b" -> "/partners/b/inbox";
        default -> throw new IllegalArgumentException(
            "Unauthorized outbound tenant");
    };
}
~~~

Đây là service/helper, không phải một adapter được cấu hình hoàn chỉnh. Trong Spring Integration DSL, gắn logic này vào `remoteDirectoryExpression`/function theo version; chỉ dùng `trustedTenantId` đã được server validate, không dùng raw HTTP `X-Tenant-Id` hay path từ partner.

### 10.2. Ví dụ SFTP header-based naming (fragment)

~~~java
import org.springframework.integration.file.FileHeaders;
import org.springframework.messaging.Message;

// Một filename generator có thể dùng:
String safeName = (String) message.getHeaders()
    .get(FileHeaders.FILENAME);

// Sau đó validate tên và dùng trong cấu hình
// SFTP outbound adapter/FileNameGenerator.
~~~

**Không gắn `REMOTE_DIRECTORY` từ một SFTP inbound message khác làm outbound directory** nếu chưa authorize. Remote paths có thể mang dấu slash/backslash, case sensitivity và permission model khác nhau. SessionFactory cần security/host-key validation, timeouts và retry.

### 10.3. Transfer completion, ACK và lifecycle

SFTP/FTP outbound là operation có trạng thái mạng:

1. Chọn remote path/filename.
2. Connect/authenticate.
3. Upload/write file, có thể dùng temporary remote filename.
4. Rename/finalize.
5. Trả kết quả hoặc exception.

Một timeout có thể xảy ra sau khi server đã nhận file nhưng trước khi client nhận ACK. Retry cùng tên file có thể overwrite hoặc conflict; cần xác minh size/checksum, idempotent destination policy, không tự sinh tên khác khi retry cùng event.

FileHeaders chỉ giúp xác định filename/metadata; **nó không thay transaction/remote ACK, host key verification hoặc durable retry queue**.

## 11. TCP/UDP/IP outbound: IpHeaders và destination

Spring Integration IP có `IpHeaders` cho network metadata (source address/port, connection ID, packet address...). Một số TCP/UDP outbound adapters hoặc gateways có thể dùng headers/destination config để chọn host/port hoặc connection, tùy loại endpoint/connection factory.

### 11.1. Đừng dùng inbound source IP làm outbound destination

Ví dụ một UDP inbound message có header IP nguồn. **Không copy y nguyên** rồi cho outbound sender gửi response tới bất kỳ IP/port nào mà client tự quảng cáo, đặc biệt nếu server mở public. Rủi ro: SSRF/UDP reflection, gửi dữ liệu tới internal network hoặc amplification.

Chọn destination từ server allowlist hoặc connection đã xác thực, có rate limit và kiểm tra quyền.

### 11.2. TCP connection ID có vòng đời riêng

TCP inbound có thể gắn connection ID phục vụ request/reply trên một existing connection. Nó không phải globally unique business ID, có thể hết hiệu lực khi connection đóng/restart. Dùng connection factory/adapter API phù hợp, test reconnect/stale connection handling. Không serialize một `TcpConnection` object thành Kafka/JMS header.

### 11.3. UDP metadata không tạo tin cậy

UDP không bảo đảm giao hàng, ordering, retransmission hoặc sender authentication. Một header outbound đính kèm `businessEventId` có thể giúp ứng dụng tự dedup nếu payload protocol mang ID, nhưng không khiến UDP trở thành giao thức delivery bảo đảm. Cần ACK/application retry nếu business thực sự yêu cầu.

## 12. Database và MongoDB outbound: headers không tự thành columns/documents

Trong SPRING_INTEGRATION_ADAPTERS, JDBC/MongoDB outbound handlers thường ghi **payload** theo mapping của repository/template. Ví dụ:

- MongoDB storing handler lưu document từ payload bằng `MongoOperations`; header `businessEventId` không tự trở thành BSON field.
- JDBC outbound adapter có thể sử dụng SpEL expressions lấy header values làm SQL parameters nếu developer cấu hình; không mặc định chép cả MessageHeaders vào row.
- Kafka/JMS/AMQP headers nếu cần lưu audit phải được **chọn/serialize có chủ đích** thành payload/columns.

Nếu một unique business key chỉ nằm trong Spring header mà không có trong payload DB, retry/redelivery có thể không được dedup đúng. Trước khi lưu, chuyển ID đã verify vào domain model hoặc SQL binding theo policy.

### 12.1. Ví dụ trước khi ghi MongoDB

~~~java
public record AuditRecord(
    String id,
    String tenantId,
    String type,
    String payloadHash) {
}

// Fragment: tạo domain record từ input đã xác minh
AuditRecord audit = new AuditRecord(
    verifiedEventId,
    authorizedTenantId,
    "ORDER_PAID",
    canonicalPayloadHash);
~~~

Không giả định `AuditRecord.id` có MongoDB `@Id` mapping nếu chưa annotate/schema; khi dùng template và unique key phải cấu hình mapping rõ. Đây là ví dụ chuyển business metadata sang **domain data**, không phải generic MongoDB HeaderMapper.
## 13. Custom outbound HeaderMapper: đổi tên và validate header

DefaultHttpHeaderMapper phù hợp khi Spring header và HTTP header **cùng tên**. Nếu Spring dùng `businessEventId` nhưng đối tác yêu cầu `X-Event-Id`, bạn có thể:

- Dùng `HeaderEnricher` thêm `X-Event-Id` trước mapper.
- Hoặc implement `HeaderMapper<HttpHeaders>`, validate và đổi tên tại ranh giới outbound.

### 13.1. Implement HeaderMapper<HttpHeaders>

~~~java
package example.headersout;

import java.util.HashMap;
import java.util.Map;
import java.util.regex.Pattern;

import org.springframework.http.HttpHeaders;
import org.springframework.integration.mapping.HeaderMapper;
import org.springframework.messaging.MessageHeaders;

public final class PartnerEventHeaderMapper
        implements HeaderMapper<HttpHeaders> {

    private static final Pattern EVENT =
            Pattern.compile("[A-Za-z0-9_-]{1,128}");
    private static final Pattern TRACE =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    @Override
    public void fromHeaders(
            MessageHeaders spring,
            HttpHeaders request) {

        String eventId =
            spring.get("businessEventId", String.class);
        String traceId =
            spring.get("appTraceId", String.class);

        if (eventId == null ||
                !EVENT.matcher(eventId).matches()) {
            throw new IllegalArgumentException(
                "Invalid businessEventId");
        }

        request.set("X-Event-Id", eventId);

        if (traceId != null &&
                TRACE.matcher(traceId).matches()) {
            request.set("X-Trace-Id", traceId);
        }

        // Không chuyển Authorization, internalRole,
        // replyChannel, errorChannel hoặc arbitrary metadata.
    }

    @Override
    public Map<String, Object> toHeaders(
            HttpHeaders response) {

        Map<String, Object> mapped = new HashMap<>();
        String requestId =
                response.getFirst("X-Partner-Request-Id");

        if (requestId != null &&
                TRACE.matcher(requestId).matches()) {
            mapped.put("partnerRequestId", requestId);
        }

        return mapped;
    }
}
~~~

**Điểm cần hiểu:**

1. `fromHeaders` nhận Spring headers và xây request headers cho hệ thống ngoài.
2. `toHeaders` dùng khi một HTTP outbound gateway nhận **HTTP response**, chỉ map response metadata được phép.
3. Header `businessEventId` bắt buộc; nếu sai, **fail fast trước send** thay vì gửi thiếu khóa idempotency.
4. Trace ID optional được drop khi không hợp lệ; nếu partner yêu cầu trace ID, có thể chọn reject.
5. Không forward các Spring reserved objects và secrets.
6. Ví dụ không tự map `Content-Type/Accept`. Nếu cần giữ standard HTTP mapping, kết hợp với DefaultHttpHeaderMapper hoặc xây policy đầy đủ và test message converter.
7. `getFirst` có thể bỏ qua multi-values khác. Với correlation header quan trọng, phải reject trường hợp đa giá trị mâu thuẫn.

### 13.2. Unit test custom mapper

~~~java
package example.headersout;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class PartnerEventHeaderMapperTest {

    private final PartnerEventHeaderMapper mapper =
            new PartnerEventHeaderMapper();

    @Test
    void mapsOnlyApprovedBusinessFields() {
        Message<String> source =
            MessageBuilder.withPayload("event-data")
                .setHeader("businessEventId", "evt-1001")
                .setHeader("appTraceId", "trace-5e1")
                .setHeader("Authorization", "do-not-send")
                .build();

        HttpHeaders request = new HttpHeaders();
        mapper.fromHeaders(source.getHeaders(), request);

        assertEquals(
            "evt-1001", request.getFirst("X-Event-Id"));
        assertEquals(
            "trace-5e1", request.getFirst("X-Trace-Id"));
        assertNull(request.getFirst("Authorization"));
    }

    @Test
    void invalidEventIdFailsBeforeSend() {
        Message<String> source =
            MessageBuilder.withPayload("payload")
                .setHeader("businessEventId", "../../bad")
                .build();

        assertThrows(
            IllegalArgumentException.class,
            () -> mapper.fromHeaders(
                source.getHeaders(), new HttpHeaders()));
    }

    @Test
    void mapsOnlyApprovedPartnerResponseId() {
        HttpHeaders response = new HttpHeaders();
        response.set("X-Partner-Request-Id", "r-889");
        response.set("Set-Cookie", "secret");

        Map<String, Object> mapped =
                mapper.toHeaders(response);

        assertEquals("r-889", mapped.get("partnerRequestId"));
        assertFalse(mapped.containsKey("Set-Cookie"));
    }
}
~~~

Đây là **unit test mapper**, chưa chứng minh HTTP gateway đã inject bean này. Cần capture request thật bằng HTTP test server và test response mapping riêng.

## 14. Policy outbound theo destination: allowlist cả key lẫn value

Một business event có thể được gửi sang nhiều đích, nhưng mỗi đích có **wire contract và quyền nhận dữ liệu khác nhau**:

| Destination | Header nên gửi | Header nên bỏ |
|---|---|---|
| Partner HTTP public | X-Event-Id, X-Trace-Id, Content-Type | raw Authorization inbound, internalRole, replyChannel |
| JMS queue nội bộ | businessEventId, schemaVersion, appTraceId | Kafka ACK/offset, HTTP cookies, AMQP deliveryTag |
| RabbitMQ exchange | businessEventId, appTraceId, contentType | receivedRoutingKey, receivedExchange, x-received-from |
| Kafka topic | businessEventId raw bytes, schemaVersion | Spring ID/timestamp, arbitrary objects, listener ACK |
| SFTP | sanitized filename, approved remote dir | user-controlled path, raw internal paths |
| MongoDB | verified eventId trong domain object | Spring MessageChannel hoặc HTTP Authorization trong document |

### 14.1. Không có một generic all-protocol serializer an toàn

Một helper chỉ kiểm tra tên:

~~~java
package example.headersout;

import java.util.Set;

public final class CommonOutboundPolicy {

    private static final Set<String> SAFE =
        Set.of(
            "businessEventId",
            "appTraceId",
            "schemaVersion");

    private CommonOutboundPolicy() {}

    public static boolean approved(String name) {
        return SAFE.contains(name);
    }
}
~~~

Chưa đủ để serialize sang tất cả transports: Kafka cần byte encoding/JSON schema; JMS property types có giới hạn; HTTP header values là text/multiple values; AMQP metadata có broker-specific fields. Áp **destination-specific mapper**, validate size/type và reject unsupported values.

### 14.2. Bắt buộc/optional và xử lý đa giá trị

- `businessEventId` thường bắt buộc cho idempotency: absent, blank, invalid length hoặc multi-value conflict → reject.
- `appTraceId` có thể optional, nhưng nếu gửi phải đúng định dạng.
- `schemaVersion` phải trong allowed set, không là arbitrary Java class name.
- `Content-Type` phải phù hợp payload codec.
- `trustedTenantId` chỉ được gửi nếu destination được authorize; có thể chuyển thành partner-scoped ID.
- Header name/value chứa CR/LF/control chars → reject tránh header injection.
- `replyChannel`, `errorChannel`, `id`/`timestamp` không được mirror tùy tiện.
- Kafka topic, JMS destination, AMQP routing key, SFTP remote path phải lấy từ **trusted route config**.

## 15. Khi mapper thất bại: phân loại lỗi trước retry

| Loại lỗi | Ví dụ | Xử lý |
|---|---|---|
| Missing header bắt buộc | Không có businessEventId | Reject/quarantine, không gửi thiếu ID |
| Invalid header | Event ID quá dài, CR/LF | Reject, sửa producer/schema |
| Unsupported header type | JMS property chứa MessageChannel | Filter/convert, không retry liên tục |
| Header forbidden | X-Internal-Role hoặc Authorization inbound | Strip và security alert nếu bất thường |
| Destination không được phép | Topic/url/path raw do user chọn | Reject, không retry |
| Payload conversion error | JSON/JMS serializer không map | Sửa schema, không retry vô hạn |
| Network/connection fail | HTTP timeout, JMS broker down | Retry có budget theo transport |
| Ambiguous ACK | Đích đã nhận nhưng response thất lạc | Reconcile cùng business ID |
| Partner business rejection | HTTP 409/422, validation error | Cần phân loại conflict vs permanent |
| AMQP returned message | Exchange nhận nhưng không route tới queue | Recovery theo return channel |
| Kafka producer failure | Future/report lỗi | Giữ event ID, retry/outbox nếu an toàn |

### 15.1. Đừng nuốt lỗi của required metadata

~~~java
// Mẫu SAI: mất khóa idempotency mà vẫn tiếp tục send.
try {
    validateBusinessEventId(message);
} catch (Exception ignored) {
    // Không làm gì.
}
sendToPartner(message);
~~~

Nếu downstream yêu cầu ID để dedup, thiếu ID phải làm **send fail có kiểm soát**, không nên cho mapper tự bỏ giá trị rồi gửi. Optional trace có thể drop theo policy; bắt buộc và optional phải tách rõ.

### 15.2. Mapping failure khác transport failure

- Mapping fail thường xảy ra **trước network send** và có tính deterministic.
- Transport fail có thể xảy ra **trước hoặc sau khi đích nhận**.
- Một timeout không chứng minh đích chưa commit.
- Gateway reply business rejection khác broker negative publisher confirm.
- Khi error flow chỉ log và return, upstream có thể ACK nhầm; cần error policy/durable recovery rõ ràng.

## 16. MessageChannel đồng bộ/bất đồng bộ thay đổi thời điểm ACK

### 16.1. DirectChannel

~~~text
Caller.send(Spring Message)
  -> DirectChannel
  -> mapper.fromHeaders()
  -> transport handler
  -> success/exception in caller stack
  -> send() returns
~~~

Với handler đồng bộ, exception mapping/conversion/transport có thể propagate trong caller thread. Nhưng Kafka producer hoặc AMQP confirms có thể báo kết quả **bất đồng bộ sau khi method trả về**.

### 16.2. QueueChannel/ExecutorChannel

~~~text
Thread A:
  send(message) -> accepted into RAM queue -> return

Thread B:
  read queued message
  mapper.fromHeaders()
  network send / broker result
~~~

Nếu HTTP/JMS/Kafka nguồn ACK ngay khi `QueueChannel` nhận vào RAM, crash có thể làm mất event chưa gửi. Cần durable source/durable queue/outbox hoặc giữ ACK ở đúng stage.

### 16.3. Reactive flows

Với `FluxMessageChannel` và reactive endpoints, tạo publisher không đồng nghĩa I/O đã chạy; publisher thường cần subscription và terminal signal. Tránh `subscribe()` fire-and-forget trong handler nếu caller cần biết gửi thành công. `HeaderMapper` chỉ tạo metadata, không quản lý backpressure/subscription.

## 17. Retry outbound, idempotency và transaction boundary

Một HTTP POST có thể thành công tại đích rồi mất response:

~~~mermaid
sequenceDiagram
    participant S as Spring Integration
    participant H as Partner API
    S->>H: POST eventId=evt-1001
    H->>H: commit event
    H--xS: response lost
    S->>H: retry same eventId=evt-1001
    H-->>S: ALREADY_ACCEPTED
~~~

Nếu retry tạo eventId mới, downstream sẽ thấy một sự kiện mới. Vì vậy:

1. Giữ **businessEventId và payload** ổn định qua retry.
2. Downstream đối chiếu cùng ID cùng canonical content, conflict nếu khác.
3. Phân loại permanent HTTP 4xx và transient 429/503/network lỗi.
4. Giới hạn attempts, exponential backoff+jitter, deadline/circuit breaker.
5. Không retry non-idempotent payment/write API khi không có protocol dedup.
6. Không retry mapping/schema errors như network outage.
7. Khi kết quả không rõ, dùng reconciliation thay vì mặc định failure.
8. Với broker, hiểu producer ACK khác business ACK của consumer.

### 17.1. Các lớp retry không thay thế nhau

| Tầng | Retry | Cần để ý |
|---|---|---|
| HTTP client | HTTP 429/503/timeouts | Idempotency-Key và status-specific policy |
| JMS producer/session | Send exception/transaction | Broker receive/commit ACK theo session |
| AMQP publisher | Confirm/NACK/return | Không route được khác publish failed |
| Kafka producer | Idempotent producer/retries | Application event ID vẫn cần cho downstream dedup |
| SFTP upload | Reconnect/reupload | Same filename, checksum và remote completion |
| MongoDB writer | Driver retryable write | Unique business key và unknown ACK reconciliation |

### 17.2. Transactional outbox

Một `@Transactional("mongoTransactionManager")` có thể commit business state và outbox entry trong **cùng MongoDB transaction**, nhưng **không commit Kafka/HTTP/JMS/AMQP send**. Outbox worker phát lại khi crash và giữ eventId trong outbound header; consumer đích vẫn cần idempotency.

**HeaderMapper là công cụ truyền metadata của idempotency contract**, không phải exactly-once engine.
## 18. Bảo mật outbound: data leakage, SSRF, injection và trust boundary

Một outbound mapper là **cửa đưa metadata ra khỏi ranh giới ứng dụng**. Nếu mặc định copy tất cả headers từ inbound message, ứng dụng có thể vô tình gửi thông tin nội bộ đến partner không có quyền xem.

### 18.1. Những thông tin không được forward nguyên trạng

| Header/metadata | Rủi ro | Policy |
|---|---|---|
| Inbound Authorization/cookie | Lộ token có audience sai | Outbound credentials riêng theo destination |
| `trustedTenantId` | Lộ tenancy/cho phép impersonation | Chỉ export partner-scoped ID nếu được authorize |
| `internalRole` / ACL | Lộ quyền người dùng/server | Không export |
| `replyChannel` / `errorChannel` | Internal routing objects, không serializable | Drop |
| Spring `id`/`timestamp` | Không phải business identity | Không dùng làm idempotency |
| Kafka received offset/topic | Lộ topology và không đúng destination | Drop |
| AMQP delivery tag/channel | Nhầm provider delivery context | Drop |
| JMS messageId/redelivered | Nhầm provider-managed fields | Không copy raw |
| SFTP internal absolute path | Lộ cấu trúc file system | Normalize hoặc drop |
| HTTP X-Forwarded-* inbound | Giả mạo client/proxy identity | Không mirror sang partner tùy ý |
| Java type header / class name | Thông tin implementation, type injection | Trusted schema/type allowlist |

### 18.2. Không để client chọn outbound destination

Nếu inbound HTTP header `X-Target-Url` hoặc `X-Routing-Key` được copy rồi dùng như outbound URL/topic/queue/exchange, kẻ gọi có thể gây SSRF, đọc internal resources hoặc phát message tới unauthorized destinations.

Mô hình an toàn:

~~~java
public String endpointFor(String partnerId) {
    return switch (partnerId) {
        case "partner-a" ->
            "https://api.partner-a.example/v1/events";
        case "partner-b" ->
            "https://api.partner-b.example/v1/events";
        default -> throw new IllegalArgumentException(
            "Unknown partner");
    };
}
~~~

Đây là helper minh họa, cần partnerId được xác thực, TLS/egress/network policy và secrets riêng. Không thực hiện “cho phép bất kỳ URL nào bắt đầu bằng https” vì có thể vẫn trỏ tới tài nguyên không mong muốn.

### 18.3. Chặn HTTP response splitting và oversized headers

Header value từ untrusted payload có thể chứa control characters `\r`/`\n` hoặc quá dài. Kiểm tra:

- Allowlist header names.
- Maximum header count/aggregate bytes.
- Maximum value length và characters.
- Multiple values cho singleton keys như businessEventId.
- Encoding/charset; Kafka String/byte[], HTTP textual headers.
- Không log raw values nhạy cảm.
- Không tạo headers động có tên lấy nguyên từ input.

Dù HTTP client library có thể tự reject CR/LF, application vẫn cần validation/business contract rõ để xử lý thành lỗi input, không nhầm với network retry.

### 18.4. Kafka/AMQP typed headers và RCE-risk

Trong Spring Kafka JSON type headers, producer có thể gắn class/type metadata. Receiver không được deserialize bất kỳ Java class name do external producer gửi; dùng trusted packages/schema registry. Tránh cấu hình `addTrustedPackages("*")` ở consumer không tin cậy.

AMQP custom headers có thể chứa nested maps/arrays; giới hạn kích thước, typed values và serialization. JMS properties thường chỉ có primitive/String; không cố truyền arbitrary Java objects.

## 19. Kiểm thử outbound HeaderMapper theo các tầng

### 19.1. Bảng test tối thiểu

| Case | Cấp | Assertion |
|---|---|---|
| HTTP allowlist | Unit | X-Event-Id được gửi; Authorization/internalRole không có |
| HTTP rename | Unit | businessEventId → X-Event-Id |
| HTTP invalid ID | Unit | Mapper reject trước send |
| HTTP response header | Unit | X-Partner-Request-Id → partnerRequestId |
| HTTP gateway | Integration | Wire-level request headers/body, reply/status/timeout |
| HTTP wrong URL | Security integration | Destination allowlist chặn SSRF |
| JMS property mapping | Broker integration | businessEventId là JMS String property |
| JMS correlation | Broker integration | JMSCorrelationID/reply đúng contract |
| JMS QoS | Broker integration | Priority/TTL/delivery mode đúng producer settings |
| AMQP fromHeaders | Unit | businessEventId có, x-received-from không |
| AMQP exchange/routing | Broker integration | Message route đúng queue |
| AMQP unroutable return | Broker integration | Return/NACK channel và recovery |
| Kafka simple mapper | Unit | businessEventId xuất raw UTF-8 bytes |
| Kafka producer record | Broker integration | Topic/key/headers và ACK |
| Kafka multi-value | Converter unit | Số entries và typed serialization đúng version |
| File outbound | Filesystem integration | filename sạch và content đúng |
| SFTP outbound | Remote test | remote directory/filename, temp rename, retry |
| Header redaction | Security | Không có raw secrets trong broker/log/errorMessage |
| Async ACK | Integration | Source không ACK khi chỉ QueueChannel nhận RAM |
| Redelivery/idempotency | E2E | Gửi lại eventId → không tạo business effect thứ hai |

### 19.2. Unit test không thay integration test

Chẳng hạn `HttpOutboundMapperTest` ở mục 4 xác minh `mapper.fromHeaders(...)`. Nó **không chứng minh** HTTP outbound gateway thực sự được cấu hình dùng bean mapper đó.

Khi test outbound HTTP, dùng một HTTP server stub như WireMock/MockWebServer hoặc embedded test HTTP server:

1. Thay URL demo bằng base URL từ test configuration.
2. Producer gửi Spring Message tới `sendToPartner`.
3. Stub ghi lại raw request.
4. Assert method/path, Content-Type, X-Event-Id và X-Trace-Id.
5. Assert **không có** Authorization nguồn, internalRole hay Spring internal headers.
6. Stub trả 202 và X-Partner-Request-Id, assert gateway reply mapping.
7. Stub 400/409/429/503/timeout để xác minh error/retry policy.
8. Test malformed eventId bị từ chối **trước khi HTTP request tới stub**.

### 19.3. Mock HTTP server thay vì gọi production partner

Ví dụ fragment test với OkHttp MockWebServer **nếu thêm test dependency tương ứng**:

~~~java
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import static org.junit.jupiter.api.Assertions.*;

try (MockWebServer server = new MockWebServer()) {
    server.enqueue(
        new MockResponse()
            .setResponseCode(202)
            .addHeader(
                "X-Partner-Request-Id", "r-889")
            .setBody("{\"accepted\":true}"));

    server.start();

    String url = server.url("/api/orders/events")
            .toString();

    // Wire an HTTP outbound gateway to this dynamic test URL,
    // send a Message with X-Event-Id, await the reply.
    // The exact wiring depends on the app's test configuration.

    // After the gateway has sent:
    // RecordedRequest request = server.takeRequest();
    // assertEquals("evt-1001", request.getHeader("X-Event-Id"));
}
~~~

**Đây là fragment minh họa**, không phải JUnit test hoàn chỉnh: cần khởi tạo Spring Integration flow dùng `url` động, thực sự gửi Message, và dùng bounded timeout với `takeRequest(timeout, TimeUnit)` trong code test production. Không truy cập thật partner production để thử lỗi/timeout.

### 19.4. JMS broker integration test

Không thể chứng minh JMS properties được provider chấp nhận chỉ bằng một `MessageHeaders` map. Trên JMS test broker:

1. Gửi Spring message có businessEventId/appTraceId/schemaVersion.
2. JMS listener test đọc TextMessage/BytesMessage.
3. Assert `getStringProperty("businessEventId")` đúng.
4. Assert provider-generated JMSMessageID tồn tại, không bị Spring Message ID ép.
5. Khi dùng gateway, test JMSCorrelationID và reply routing.
6. Test TTL/priority bằng JMS producer settings/explicitQoS, không chỉ mapper.
7. Gây JMS broker down, test exception/retry/transaction ACK.

### 19.5. AMQP broker integration test

Với RabbitMQ test:

1. Gửi Spring Message vào outbound adapter.
2. Bind queue với exchange/routing key được cấu hình.
3. Nhận Rabbit message và kiểm tra properties/headers.
4. Assert businessEventId có, `x-received-from` không có.
5. Gửi tới routing key không có binding (khi mandatory/returns enabled), xác minh return channel/recovery.
6. Test publisher confirm ACK/NACK theo broker config.
7. Assert deliveryTag của inbound message không bị copy như producer metadata.

### 19.6. Kafka broker integration test

Trên Kafka test:

1. Dùng topic test và serializer có config rõ.
2. Cấu hình producer converter/header mapper (raw hoặc JSON).
3. Gửi message với businessEventId/trace.
4. Consumer test đọc `ConsumerRecord.headers()`.
5. Assert Kafka wire bytes, topic, key, partition semantics.
6. Assert Spring ID, internalRole và listener ACK không bị xuất.
7. Test duplicate record IDs và consumer idempotency riêng.
8. Test producer failure channel/unknown result.

### 19.7. Không cần broker để test mọi thứ

Unit tests cho DefaultHttpHeaderMapper, custom PartnerEventHeaderMapper, AMQP HeaderMapper và KafkaHeaderMapper có thể chạy không broker. Broker integration chỉ cần khi test transport delivery/ACK/replication/consumer behavior.

Tách unit (fast) với integration (slower) và chỉ chạy broker fault injection trên môi trường cô lập.

## 20. Observability và vận hành outbound

### 20.1. Đo đúng mốc

| Metric gợi ý | Ý nghĩa |
|---|---|
| `outbound_headers_mapped_total` | Messages đã qua mapper |
| `outbound_header_validation_error_total` | Lỗi required/type/format |
| `outbound_header_dropped_total` | Optional/forbidden header bị loại |
| `outbound_header_map_latency_seconds` | Thời gian map metadata |
| `outbound_transport_send_attempt_total` | Lần cố gửi ra ngoài |
| `outbound_transport_send_error_total` | Send exception |
| `outbound_delivery_confirm_total` | Broker/transport confirm theo policy |
| `outbound_delivery_unknown_total` | Timeout/ambiguous result |
| `outbound_retry_attempt_total` | Application retry count |
| `outbound_dlq_total` | Durable quarantined events |
| `outbound_business_committed_total` | Đích xác nhận business completion |

Tên metric là **gợi ý**, không mặc định framework xuất sẵn. Không dùng từng eventId, userId, token hay URL động làm metric label có cardinality cao.

### 20.2. Log không chứa raw headers

~~~text
outbound_received    destination=partner-a eventType=ORDER_PAID
header_validation_ok mappedHeaderCount=3
transport_send       protocol=http
transport_ack        status=202
business_pending     partnerRequestId=r-889
reconciliation_done  outcome=ALREADY_ACCEPTED
~~~

Đừng log raw Authorization/Cookie, JMS connection secrets, Kafka type hints nhạy cảm hoặc full payload. Correlation ID có thể đưa vào trace/log với retention và quyền đọc phù hợp.

### 20.3. Lifecycle và in-flight sends

- **HTTP outbound:** connection pool, socket/connect timeout, retries, HTTP status mapping.
- **JMS outbound:** ConnectionFactory, JmsTemplate/session transaction, connection recovery.
- **AMQP outbound:** RabbitTemplate, publisher confirms/returns, exchange/binding, broker reconnect.
- **Kafka outbound:** ProducerFactory/KafkaTemplate, async send futures, flush/close và producer retries.
- **SFTP outbound:** SessionFactory, host key verification, upload/temp rename, remote connection recovery.
- **File outbound:** disk space, directory permissions, temp file suffix, move/rename.
- **MongoDB outbound:** transaction/unique key/write concern.
- **FluxMessageChannel:** subscriptions/terminal signals/backpressure theo reactive contract.

Khi shutdown, ngừng nhận dữ liệu mới, chờ **in-flight writes/publishes** theo deadline rồi lưu bền trạng thái chưa hoàn tất để instance mới có thể retry. HeaderMapper không tự làm graceful drain hoặc replay.

## 21. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| HTTP X-Event-Id không có | Dùng setInboundHeaderNames thay outbound | setOutboundHeaderNames |
| Outbound gateway thiếu response header | Chưa setInboundHeaderNames | Cấu hình response allowlist |
| HTTP Content-Type bị mất | Explicit allowlist override defaults | Thêm Content-Type/HTTP_REQUEST_HEADERS |
| HTTP request có Authorization nguồn | Copy wildcard | Loại raw token, auth riêng cho đích |
| HTTP 202 được coi business DONE | Nhầm accepted vs committed | Poll/reconcile business state |
| HTTP response header bị dùng làm replyChannel | Tin untrusted data | Server policy/route |
| JMS businessEventId mất | Unsupported type/name, mapper/converter | JMS-friendly String property |
| JMS TTL không áp dụng | Chỉ map header, chưa set producer QoS | JmsTemplate explicit QoS/TTL |
| JMSCorrelationID mismatch | Ghi đè correlation của gateway | Kiểm tra correlation-key/config |
| JMSMessageID đổi khi republish | Nhầm provider ID là business ID | Stable businessEventId |
| AMQP x-received-from bị forward | Wildcard/include broker metadata | Negate x-* và test |
| AMQP publisher send nhưng không route | Không có binding/mandatory return | Return channel và confirm policy |
| AMQP deliveryTag được serialize | Copy inbound runtime state | Loại received metadata |
| Kafka header String thành JSON bytes | Dùng JSON mapper không thỏa wire contract | Raw mapping/schema policy |
| Kafka consumer không hiểu class type | Type-hint/deserialization mismatch | Trusted packages/schema evolution |
| Kafka topic/key sai | Lấy từ raw header không validate | Trusted topic/key policy |
| Kafka duplicate values bị mất | Multi-value policy theo version | Test wire-level, bật option khi có |
| File ghi thành nhiều tên khi retry | Fallback Spring Message ID | Stable filename từ business ID |
| SFTP remote path traversal | Path từ untrusted header | Directory allowlist/sanitize |
| TCP connection ID stale | Reconnect làm mất context | Lifecycle-aware connection factory |
| UDP send không có ACK | Giao thức best effort | Application-level ACK nếu cần |
| MongoDB không có eventId | ID chỉ nằm trong Spring header | Bind ID vào domain payload |
| Mapping pass nhưng QueueChannel mất event | RAM queue rồi crash | Durable outbox/ACK đúng stage |
| Retry mãi vì header invalid | Retry all exceptions | Tách validation vs transient |
| Tests mapper pass nhưng broker fail | Không test transport-level | Integration test |
| Metrics cardinality tăng | Label theo từng ID/header value | Low-cardinality dimensions |

### 21.1. Quy trình chẩn đoán

~~~text
1. Upstream Spring Message: payload, headers và origin trust
2. HeaderEnricher/HeaderFilter: canonical keys/values
3. Outbound endpoint configuration: target URL/destination/topic
4. HeaderMapper.fromHeaders: selected names, types, patterns
5. MessageConverter: payload/wire encoding
6. Actual HTTP/JMS/AMQP/Kafka/file/SFTP request/record
7. Transport send/ACK/confirm/return
8. Downstream business commit và idempotency
9. Retry/recovery sau timeout hoặc crash
~~~

Nếu mapper unit test thành công nhưng actual outbound request thiếu header, kiểm tra **bean được inject vào đúng endpoint**, converter có override header hay không và có header filter sau mapper không.

## 22. Bài thực hành tổng hợp

Xây pipeline **HTTP/JMS/Kafka inbound → normalize headers → outbound HTTP/JMS/AMQP/Kafka/SFTP**. Có thể chạy từng protocol bằng profile riêng, không cần tất cả brokers cùng một lúc.

### Phần A — Hợp đồng HeaderMapper

1. Viết bảng phân biệt `HeaderMapper<T>.fromHeaders` và `toHeaders`.
2. Lấy Spring message có businessEventId/appTraceId/internalRole.
3. Viết allowlist cho partner HTTP.
4. Unit test fromHeaders chỉ gửi các custom headers được phép.
5. Test HTTP outbound gateway nhận response header và map lại bằng toHeaders.
6. Thử thiếu/invalid businessEventId, assert fail trước network call.
7. Tự implement `PartnerEventHeaderMapper` đổi businessEventId thành X-Event-Id.

### Phần B — HTTP outbound gateway

1. Dùng `DefaultHttpHeaderMapper.outboundMapper()`.
2. setOutboundHeaderNames("Content-Type","X-Event-Id","X-Trace-Id").
3. setInboundHeaderNames("X-Partner-Request-Id","Content-Type").
4. Dựng `Http.outboundGateway(...)`, mock HTTP server.
5. Kiểm tra request method, headers, body, response headers.
6. Thử 202/409/429/503/timeout và phân loại.
7. Ngăn SSRF nếu partner URL được chọn động, test allowlist.

### Phần C — JMS/AMQP

1. Tạo JMS outbound adapter với DefaultJmsHeaderMapper.
2. Gửi custom String property businessEventId và test broker receive.
3. So sánh JMSCorrelationID với Spring correlationId và businessEventId.
4. Cấu hình producer TTL/priority/deliveryMode bằng QoS API.
5. Tạo AMQP DefaultAmqpHeaderMapper requestHeaderNames.
6. Test x-received-from/internalRole không ra broker.
7. Test AMQP publisher confirm/return khi routing fail.
8. Thử broker down/reconnect và durable retry.

### Phần D — Kafka/SFTP/File

1. Chọn SimpleKafkaHeaderMapper raw bytes hoặc JSON mapper theo version.
2. Test record header businessEventId có bytes đúng UTF-8.
3. Kiểm tra topic/key từ trusted server config, không từ raw client header.
4. Test Kafka multi-value semantics theo version.
5. Dùng FileHeaders.FILENAME theo stable business ID.
6. Gửi SFTP tới remote dir có allowlist, kiểm tra filename/temp rename.
7. Thử retry cùng ID/filename khi ACK bị mất.
8. Ghi MongoDB payload với unique event ID thay vì chỉ header.

### Phần E — Reliability và hardening

1. Loại Authorization, replyChannel, errorChannel, raw tenant role.
2. Quy định max header bytes/values và type schema.
3. So sánh DirectChannel với QueueChannel về thời điểm send/ACK.
4. Dùng outbox để gửi event từ MongoDB tới Kafka/RabbitMQ.
5. Simulate crash sau broker ACK trước khi mark SENT, test redelivery.
6. Dùng idempotent consumer ở đích với businessEventId.
7. Đặt metric mapper errors, transport ACK, unknown result, retry, DLQ.
8. Viết runbook shutdown/restart để không mất in-flight events.

**Câu hỏi tự đánh giá:**

- Vì sao `fromHeaders` là outbound của HeaderMapper<T>?
- Outbound gateway phải dùng cả `fromHeaders` và `toHeaders` khi nào?
- `setOutboundHeaderNames` khác `setInboundHeaderNames` thế nào ở HTTP?
- Vì sao mapping Authorization từ inbound sang HTTP partner là nguy hiểm?
- JMS property khác producer QoS TTL/priority/deliveryMode thế nào?
- Vì sao JMSMessageID không nên làm businessEventId?
- AMQP requestHeaderNames có vai trò gì trong outbound?
- Vì sao không copy `x-received-from` hoặc `amqp_deliveryTag`?
- KafkaHeaderMapper khác org.springframework.integration.mapping.HeaderMapper<T> ở đâu?
- Khi nào SimpleKafkaHeaderMapper phù hợp hơn JSON mapper?
- Kafka TOPIC/KEY là record metadata hay custom header bytes?
- Multi-value Kafka headers cần lưu ý theo version ra sao?
- Vì sao FileHeaders.FILENAME cần ổn định qua retry?
- SFTP remoteDirectory từ untrusted header có rủi ro gì?
- Vì sao MongoDB storing adapter không tự lưu mọi MessageHeaders?
- Khi `QueueChannel.send()==true`, broker đã ACK chưa?
- HTTP 202 có nghĩa business đã hoàn tất chưa?
- Mapping lỗi khác network timeout/unknown outcome như thế nào?
- Vì sao HeaderMapper không tạo exactly-once cross-system?

## 23. Tài liệu tham khảo

- [Spring Integration API — HeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/mapping/HeaderMapper.html): `fromHeaders` và `toHeaders`.
- [Spring Integration API — AbstractHeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/mapping/AbstractHeaderMapper.html): header patterns, request/reply.
- [Spring Integration Reference — HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html): outboundMapper, mapped-request-headers, mapped-response-headers.
- [Spring Integration API — BaseHttpMessageHandlerSpec](https://docs.spring.io/spring-integration/docs/6.1.x/api/org/springframework/integration/http/dsl/BaseHttpMessageHandlerSpec.html): headerMapper, mappedRequestHeaders.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): outbound JMS, DefaultJmsHeaderMapper, QoS và gateway correlation.
- [Spring Integration API — JmsOutboundChannelAdapterSpec](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/jms/dsl/JmsOutboundChannelAdapterSpec.html): headerMapper(JmsHeaderMapper), destination, TTL.
- [Spring Integration Reference — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html): request/reply name patterns, x-* exclusions.
- [Spring Integration API — AmqpBaseOutboundEndpointSpec](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/amqp/dsl/AmqpBaseOutboundEndpointSpec.html): headerMapper, mappedRequestHeaders, confirms/returns.
- [Spring Integration Reference — AMQP Outbound Channel Adapter](https://docs.spring.io/spring-integration/reference/amqp/outbound-channel-adapter.html): broker routing, publisher confirms, returns.
- [Spring Kafka Reference — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html): KafkaHeaderMapper, Simple/JSON mappers, typed/multi-value headers.
- [Spring Kafka Reference — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): KafkaHeaders.TOPIC/KEY, producer messages.
- [Spring Integration Reference — Apache Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): outbound Kafka adapter/gateway và response/failure channels.
- [Spring Integration Reference — Writing Files](https://docs.spring.io/spring-integration/reference/file/writing.html): FileHeaders.FILENAME, FileNameGenerator, temporary suffix.
- [Spring Integration Reference — FTP Outbound](https://docs.spring.io/spring-integration/reference/ftp/outbound.html): remote directory, filename expressions và file exists modes.
- [Spring Integration Reference — SFTP Support](https://docs.spring.io/spring-integration/reference/sftp.html): outbound remote transfer/session lifecycle.
- [Spring Integration Reference — IP Support](https://docs.spring.io/spring-integration/reference/ip.html): TCP/UDP metadata.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): synchronous vs async channel behavior.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): error channel và delivery failures.

## Kết luận

**HeaderMapper cho outbound message** biến metadata đã được kiểm soát của **Spring `MessageHeaders`** thành headers/properties của giao thức đích. Trong Spring Integration, **`fromHeaders(MessageHeaders, target)` là hướng outbound**; outbound gateway còn có thể gọi `toHeaders(externalResponse)` để map response trở lại Spring Message. HTTP thường dùng `DefaultHttpHeaderMapper.outboundMapper()`; JMS và AMQP dùng mapper riêng; Kafka dùng `KafkaHeaderMapper` của Spring Kafka; File/SFTP/IP/DB có cách sử dụng headers theo adapter, không phải một HeaderMapper chung.

Trong **SPRING_INTEGRATION_ADAPTERS**, hãy coi outbound header mapping là **ranh giới truyền dữ liệu có kiểm soát**: allowlist theo destination, validate tên/kiểu/độ dài, không rò rỉ token/role/routing nội bộ, giữ businessEventId ổn định, test wire-level request/broker message, tách header mapping khỏi payload conversion, ACK/transaction/retry và recovery. **Map header thành công không đồng nghĩa dữ liệu đã được giao bền, downstream đã xử lý xong hay hệ thống đạt exactly-once.**








