# HeaderMapper cho inbound message trong Spring Integration

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao **`HeaderMapper`** là lớp chuyển đổi **metadata của giao thức ngoài → Spring `MessageHeaders`** khi một inbound adapter/gateway nhận message; phân biệt việc map header với chuyển đổi payload.
- Nhớ chính xác chiều của API `HeaderMapper<T>`: **`toHeaders(T source)` là hướng inbound**, còn **`fromHeaders(MessageHeaders headers, T target)` là hướng outbound/response**. Tên method dễ gây nhầm nếu chỉ đọc “from/to” theo quan điểm hệ thống ngoài.
- Nhận biết các loại header: Spring core `id`, `timestamp`; application correlation/tracing/idempotency; HTTP/JMS/AMQP/Kafka/FTP/SFTP/IP protocol headers; và thông tin chỉ tồn tại tại transport.
- Cấu hình và kiểm thử `DefaultHttpHeaderMapper.inboundMapper()` cho HTTP inbound gateway, chọn header bằng `setInboundHeaderNames(...)` hoặc DSL `mappedRequestHeaders(...)`.
- Sử dụng `DefaultJmsHeaderMapper` với JMS message-driven inbound adapter để đọc JMS API headers, properties và hiểu sự khác biệt giữa `jms_correlationId` và Spring `correlationId`.
- Hiểu `DefaultAmqpHeaderMapper`, `AmqpHeaders` và request-header-name patterns khi nhận RabbitMQ/AMQP message; tránh map wildcard vô hạn hoặc để lọt broker-internal `x-*` headers.
- Phân biệt Spring Kafka `KafkaHeaderMapper`/`DefaultKafkaHeaderMapper`/`SimpleKafkaHeaderMapper` thuộc **Spring for Apache Kafka**, không mặc định là `org.springframework.integration.mapping.HeaderMapper<T>`.
- Biết khi nào File/SFTP/FTP/TCP/UDP adapters cung cấp headers **nội bộ** mà không cần một HeaderMapper tổng quát để cấu hình.
- Thiết kế policy **allowlist, validation, tenant authorization, correlation/idempotency key, type conversion và lọc sensitive headers** tại ingress.
- Viết unit test mapper, kiểm thử luồng HTTP/JMS/AMQP theo adapter thật, nhận diện tình huống mất header/đổi kiểu/đọc trùng, kiểm tra lỗi và vòng đời kết nối.

Bài thuộc chương **Header message** của module **SPRING_INTEGRATION_ADAPTERS**. Module tập trung kết nối các hệ thống ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`. Trong những luồng file, SFTP, HTTP, JMS, AMQP, Kafka, TCP/UDP hay database, **headers tạo hợp đồng kỹ thuật giữa protocol boundary và business flow**: chúng định tuyến, cung cấp correlation, hỗ trợ truy vết và truyền metadata; nhưng không tự bảo đảm tính xác thực, ACK hay giao hàng exactly-once.

> Phạm vi: ví dụ chủ yếu theo Java 17+, Spring Boot 3.x, Spring Integration 6.x, Spring Framework 6.x. Với Spring Integration 7.x, một số package, factory DSL, phiên bản Jakarta JMS, Spring Kafka và cấu hình mặc định có thể khác. **Luôn xác minh Javadoc theo BOM cụ thể của dự án.**

## 1. Một HTTP request trở thành Spring Message như thế nào?

Giả sử hệ thống đối tác gọi:

~~~http
POST /ingest/orders HTTP/1.1
Host: localhost:8080
Content-Type: application/json
X-Trace-Id: trace-6a1
X-Partner-Event-Id: event-101
X-Tenant-Id: tenant-a
Authorization: Bearer <TOKEN>

{"orderId":"order-1001","amount":125.00}
~~~

Spring Integration HTTP inbound gateway tạo một Spring `Message<?>` cho luồng xử lý. **Payload** đến từ body và `HttpMessageConverter`; **headers** được trích từ HTTP request hoặc do gateway/platform tự thêm.

~~~mermaid
flowchart LR
  H["HTTP request<br/>body + headers"] --> G["Http.inboundGateway"]
  G --> MC["HTTP MessageConverter<br/>body → payload"]
  G --> HM["DefaultHttpHeaderMapper<br/>HttpHeaders → MessageHeaders"]
  MC --> M["Spring Message<?>"]
  HM --> M
  M --> C["MessageChannel"]
  C --> S["Validate / route / transform / handle"]
~~~

Ví dụ message nội bộ dạng logic:

~~~text
Spring Message
  payload = {"orderId":"order-1001","amount":125.00}
  headers = {
    id: <generated UUID>,
    timestamp: <generated epoch millis>,
    contentType: "application/json"  (tùy mapper/codec),
    X-Trace-Id: "trace-6a1"          (nếu được map),
    X-Partner-Event-Id: "event-101" (nếu được map)
  }
~~~

**Lưu ý về ví dụ:** cách viết tên/kiểu value thực tế của HTTP header có thể là `String`, `List<String>`, `MediaType` hay dạng được mapper chuyển đổi, tùy adapter/mapper/config. Đừng lập trình phụ thuộc một kiểu chỉ vì nhìn thấy header text trong request; hãy kiểm tra Message thực tế bằng test.

### 1.1. Câu hỏi bảo mật ngay tại ingress

Header HTTP `X-Tenant-Id: tenant-a` **do client gửi, chưa phải tenant đã xác thực**. Nếu business handler dùng nó để quyết định MongoDB collection, Kafka topic hoặc quyền truy cập, đối tác có thể đổi header để truy cập tenant khác.

Tách:

- **External input:** request headers được map, nhưng ở mức *untrusted data*.
- **Trusted context:** principal/JWT claims đã được security filter xác thực, tenant authorization do server tính toán.
- **Internal application headers:** `trustedTenantId`/`businessEventId`/`traceId` do ingress validator/enricher tạo, không cho client tự override.

## 2. HeaderMapper<T> — hợp đồng và đúng chiều ánh xạ

Interface:

~~~java
package org.springframework.integration.mapping;

public interface HeaderMapper<T> {
    void fromHeaders(
            org.springframework.messaging.MessageHeaders headers,
            T target);

    java.util.Map<String, Object> toHeaders(T source);
}
~~~

Generic type `T` là loại object của **hệ thống ngoài**: ví dụ `HttpHeaders`, `jakarta.jms.Message` hoặc `MessageProperties` tùy implementation.

| Phương thức | Nguồn dữ liệu | Đích | Trong inbound |
|---|---|---|---|
| **`toHeaders(T source)`** | Headers/properties của message **bên ngoài** | `Map<String,Object>` để tạo Spring `MessageHeaders` | **Có, phương thức trọng tâm** |
| **`fromHeaders(MessageHeaders headers, T target)`** | Spring `MessageHeaders` | Mutable external headers/properties | Dùng khi **outbound** hoặc **inbound gateway gửi reply** |
| `MessageConverter` | Body/bytes/JSON/XML/JMS payload | Spring Message payload hoặc external body | Là **cơ chế khác** với header mapping |
| Header enricher | Spring Message đang ở trong flow | Spring Message với headers thêm/đổi | **Sau** khi đã qua inbound boundary |
| Header filter | Spring Message đang ở trong flow | Spring Message loại bỏ một số headers | **Sau** mapping; hữu ích cho trust boundary |

**Quy tắc nhớ:** `toHeaders(source)` có nghĩa “chuyển *từ đối tượng bên ngoài sang Spring Message headers*”, không phải “gửi headers ra bên ngoài”.

### 2.1. API ví dụ độc lập

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;
import java.util.Map;

HttpHeaders httpHeaders = new HttpHeaders();
httpHeaders.add("X-Trace-Id", "trace-6a1");
httpHeaders.set("Content-Type", "application/json");

DefaultHttpHeaderMapper mapper =
        DefaultHttpHeaderMapper.inboundMapper();
mapper.setInboundHeaderNames(
        "Content-Type", "X-Trace-Id");

Map<String, Object> inboundHeaders =
        mapper.toHeaders(httpHeaders);
~~~

Sau đó framework có thể dùng các entries trong map để tạo một `Message<?>` (với các core headers được tạo/kiểm soát riêng). Kiểu value trả về phụ thuộc implementation; test nên kiểm tra **tên và semantics**, không tự ép tất cả về String.

### 2.2. HeaderMapper<T> không phải Spring MessageConverter

Ví dụ HTTP:

~~~text
Content-Type: application/json
X-Trace-Id: trace-6a1

{"orderId":"o-1"}
~~~

- `HttpMessageConverter` chuyển body JSON thành `String`, `byte[]` hoặc Java DTO, tùy requestPayloadType/converters.
- `HeaderMapper<HttpHeaders>` đọc Content-Type và X-Trace-Id cho Spring MessageHeaders.
- Một custom `HeaderMapper` **không** tự deserialize JSON.
- Một custom `MessageConverter` **không** tự bảo đảm các custom protocol headers được giữ.

Thành công chuyển payload không chứng minh header mapper đã nhận đúng metadata, và ngược lại.

## 3. Header trong Spring Message: tên, kiểu và quyền sở hữu

Spring Message có cấu trúc:

~~~java
org.springframework.messaging.Message<T>
org.springframework.messaging.MessageHeaders
~~~

Lấy header:

~~~java
Message<?> message = ...;

Object raw = message.getHeaders().get("X-Trace-Id");
String trace = message.getHeaders().get(
        "appTraceId", String.class);
~~~

### 3.1. Core headers và application headers

| Nhóm | Ví dụ | Lưu ý |
|---|---|---|
| **Spring core** | `MessageHeaders.ID`, `MessageHeaders.TIMESTAMP` | Do framework tạo/quản lý; không coi là ID gốc của hệ thống ngoài |
| **Correlation/reply flow** | `correlationId`, `replyChannel`, `errorChannel` | Có ý nghĩa với gateway/aggregator/error flow; không để bên ngoài tùy ý điều khiển |
| **HTTP metadata** | Content-Type, Accept, X-Trace-Id | Tên case-insensitive trên HTTP nhưng map Java không mặc định case-insensitive |
| **JMS metadata** | `jms_messageId`, `jms_correlationId`, `jms_redelivered` | ID/correlation của broker khác Spring Message ID |
| **AMQP metadata** | `amqp_receivedRoutingKey`, `amqp_receivedExchange`, `amqp_redelivered` | Delivery/routing properties từ broker |
| **Kafka metadata** | received topic/partition/offset/key | Được converter/header mapper theo Spring Kafka; types khác HTTP |
| **File/SFTP** | file name, remote directory, original file | Do adapter sinh; không nhất thiết qua generic HeaderMapper |
| **IP/TCP/UDP** | source IP/port, connection id | Metadata network do IP adapter đặt |
| **Business application** | `businessEventId`, `trustedTenantId` | Nên được suy từ identity/payload đã validate |

**`MessageHeaders.ID` không bằng HTTP request ID, JMSMessageID, Kafka record key hay business event ID.** Redelivery có thể tạo Spring Message mới với UUID khác. Với idempotency/dedup, chọn ID nghiệp vụ ổn định và có phạm vi tenant/nguồn rõ ràng.

### 3.2. Immutability và cách thêm header sau mapping

`MessageHeaders` là map header được quản lý theo hợp đồng không sửa trực tiếp từ business handler. Thêm/sửa bằng `MessageBuilder` hoặc EIP `HeaderEnricher`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> normalized =
    MessageBuilder.withPayload("accepted")
        .setHeader("appTraceId", "trace-6a1")
        .setHeader("businessEventId", "event-101")
        .build();
~~~

Khi xây message dựa trên một message có sẵn:

~~~java
Message<?> sanitized =
    MessageBuilder.fromMessage(message)
        .removeHeader("Authorization")
        .removeHeader("X-Untrusted-Role")
        .setHeader("trustedTenantId", authenticatedTenantId)
        .build();
~~~

**`authenticatedTenantId` phải được lấy từ security context/server identity đã xác thực**, không chỉ copy `X-Tenant-Id` từ client. Đây là fragment với `message`/`authenticatedTenantId` do caller cung cấp.

### 3.3. Kiểu header, null và chuyển đổi

- HTTP header có thể có **nhiều values**. Không biến `List<String>` thành một String ghép dấu phẩy khi semantic của header không cho phép.
- JMS properties giới hạn các loại primitive/wrapper/String được JMS hỗ trợ; không chuyển Java arbitrary object thành JMS property một cách ngây thơ.
- Kafka record headers có giá trị dạng **`byte[]`** ở wire level; deserialization của Spring Kafka mapper có thể cho ra String/JSON types theo policy.
- AMQP `MessageProperties` có typed fields và map custom headers.
- Spring `@Header` injection có thể áp conversion; lỗi không convert được là **validation/mapping error**, không phải thông điệp “header không tồn tại” đơn thuần.
- Header vắng mặt khác header có giá trị rỗng, malformed hoặc nhiều giá trị mâu thuẫn.

## 4. Header mapping diễn ra ở bước nào của inbound flow?

Các endpoint thông dụng:

~~~mermaid
sequenceDiagram
    participant E as External system
    participant A as Inbound adapter/gateway
    participant HM as HeaderMapper
    participant MC as MessageConverter
    participant C as MessageChannel
    participant H as Business handler
    E->>A: Request / broker message
    A->>HM: toHeaders(external headers)
    HM-->>A: Map<String,Object>
    A->>MC: convert body/payload
    MC-->>A: Java payload
    A->>C: Spring Message(payload, mapped headers)
    C->>H: deliver message
    H-->>C: result / reply if gateway
~~~

**Không tự giả định thứ tự nội bộ chính xác của mọi adapter**: converter và mapper có thể gọi theo implementation-specific sequence. Điều chắc chắn là cả hai góp phần dựng Spring Message **trước khi handler downstream xử lý**.

### 4.1. Inbound channel adapter vs inbound gateway

| Endpoint | Đầu vào | Đầu ra | Hệ quả cho header mapper |
|---|---|---|---|
| **Inbound channel adapter** | HTTP/JMS/AMQP/SFTP/UDP... | One-way Spring Message | Chủ yếu dùng `toHeaders(...)` khi endpoint có HeaderMapper |
| **Inbound gateway** | HTTP/JMS/AMQP request | Spring Message + reply | `toHeaders(...)` cho request **và** `fromHeaders(...)` cho reply headers |
| **Outbound adapter** | Spring Message | External write/send | Chủ yếu `fromHeaders(...)` |
| **Outbound gateway** | Spring Message request | External request/reply | `fromHeaders(...)` cho outgoing request, `toHeaders(...)` cho incoming response |

**Direction phụ thuộc vào endpoint và đối tượng được map**. Với HTTP inbound gateway, `DefaultHttpHeaderMapper.inboundMapper()` được cấu hình cho *request inbound và response outbound*; tránh nhầm với `outboundMapper()` dùng cho HTTP outbound gateway/adapter.

### 4.2. Một mapper không tự thêm mọi header bảo mật

Việc copy HTTP `Authorization` vào Spring Message không đồng nghĩa Spring Security đã xác minh bearer token. Việc copy `X-Forwarded-For` cũng không chứng minh đó là IP thực khi proxy chain chưa được tin cậy.

HeaderMapper chỉ **chọn/chuyển metadata**. Authorization, signature verification, tenant isolation, input validation và rate limiting phải có cơ chế riêng.

## 5. DefaultHttpHeaderMapper: inbound HTTP request

Implementation:

~~~java
org.springframework.integration.http.support.DefaultHttpHeaderMapper
~~~

Nó implement:

~~~java
org.springframework.integration.mapping.HeaderMapper<
    org.springframework.http.HttpHeaders>
~~~

Factory được xác nhận:

~~~java
DefaultHttpHeaderMapper.inboundMapper();
DefaultHttpHeaderMapper.outboundMapper();
~~~

Đối với **HTTP inbound gateway**, dùng **`inboundMapper()`** rồi chỉ định những request headers được phép map.

### 5.1. HTTP allowlist mapper bean

~~~java
package example.headers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

@Configuration
public class InboundHttpHeaderConfiguration {

    @Bean("inboundHttpHeaderMapper")
    public DefaultHttpHeaderMapper inboundHttpHeaderMapper() {

        DefaultHttpHeaderMapper mapper =
                DefaultHttpHeaderMapper.inboundMapper();

        mapper.setInboundHeaderNames(
            "Content-Type",
            "Accept",
            "X-Trace-Id",
            "X-Partner-Event-Id");

        return mapper;
    }
}
~~~

- `setInboundHeaderNames(...)` cấu hình những header names/patterns **được map từ HTTP request**.
- Cấu hình danh sách tường minh **thay đổi phạm vi default mapping**: đừng giả định những standard headers khác vẫn tự động có mặt.
- `Content-Type`/`Accept` thường cần cho application contract; trong một số flow, payload converter có thể đọc Content-Type từ request trực tiếp trước/ngoài header map.
- `X-Trace-Id` chỉ là một **external trace hint**; phải validate format/length và phân biệt với trace/span ID nội bộ.
- `Authorization` được cố ý không đưa vào MessageHeaders; authentication nên thực hiện trước ở security layer.
- `X-Tenant-Id` được cố ý không copy vào trusted headers vì tenant phải suy từ principal đã xác thực.

### 5.2. HTTP HeaderMapper có tên method inbound/outbound dễ gây hiểu nhầm

| API DefaultHttpHeaderMapper | Hướng của HTTP inbound gateway |
|---|---|
| `inboundMapper()` | Factory đúng cho endpoint inbound |
| `setInboundHeaderNames(...)` | Danh sách HTTP **request** headers được nhận vào Spring Message |
| `setOutboundHeaderNames(...)` | Danh sách Spring reply headers được gửi **ra HTTP response** |
| `toHeaders(HttpHeaders request)` | HTTP request → Spring Message headers |
| `fromHeaders(MessageHeaders reply, HttpHeaders response)` | Spring reply headers → HTTP response |
| `HTTP_REQUEST_HEADERS` | Pattern token cho standard HTTP request headers |
| `HTTP_RESPONSE_HEADERS` | Pattern token cho standard HTTP response headers |

**Không dùng `setOutboundHeaderNames` để quyết định input headers của HTTP request**. Nó dành cho direction ngược.

### 5.3. Test độc lập HTTP mapper

~~~java
package example.headers;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

import static org.junit.jupiter.api.Assertions.*;

class InboundHttpHeaderMapperTest {

    @Test
    void mapsOnlySelectedHeaders() {
        DefaultHttpHeaderMapper mapper =
                DefaultHttpHeaderMapper.inboundMapper();

        mapper.setInboundHeaderNames(
                "X-Trace-Id", "X-Partner-Event-Id");

        HttpHeaders incoming = new HttpHeaders();
        incoming.add("X-Trace-Id", "trace-a7");
        incoming.add("X-Partner-Event-Id", "event-101");
        incoming.add("X-Untrusted-Role", "admin");

        Map<String, Object> mapped =
                mapper.toHeaders(incoming);

        assertTrue(mapped.keySet().stream()
            .anyMatch(s -> s.equalsIgnoreCase("X-Trace-Id")));

        assertTrue(mapped.keySet().stream()
            .anyMatch(s -> s.equalsIgnoreCase(
                    "X-Partner-Event-Id")));

        assertFalse(mapped.keySet().stream()
            .anyMatch(s -> s.equalsIgnoreCase(
                    "X-Untrusted-Role")));
    }
}
~~~

Kiểm tra bằng `equalsIgnoreCase` ở test vì HTTP header names về protocol là case-insensitive, trong khi map Java có thể lưu tên/casing nhất định theo implementation. Test này không khẳng định value luôn là String; nếu business cần một String đã validate, hãy normalize sau mapping.

### 5.4. Nếu muốn giữ thêm standard headers

Trong cấu hình mapping patterns, các shortcut được tài liệu hóa:

~~~text
HTTP_REQUEST_HEADERS
HTTP_RESPONSE_HEADERS
~~~

Ví dụ bạn muốn giữ standard request headers và một custom key:

~~~java
mapper.setInboundHeaderNames(
        "HTTP_REQUEST_HEADERS",
        "X-Trace-Id",
        "X-Partner-Event-Id");
~~~

Chú ý: include tất cả standard headers có thể mang nhiều metadata nhạy cảm hoặc không cần thiết; với public API, **allowlist hẹp thường dễ kiểm soát hơn**. Không dùng wildcard `*` chỉ để tiết kiệm vài dòng cấu hình.

## 6. HTTP inbound gateway: wiring Java DSL

Spring Integration HTTP module có Java DSL `Http.inboundGateway(...)` và `HttpInboundEndpointSupportSpec.headerMapper(...)`.

~~~java
package example.headers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.http.dsl.Http;
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

@Configuration
@EnableIntegration
public class HttpOrdersInboundFlow {

    @Bean
    public IntegrationFlow ordersHttpFlow(
            DefaultHttpHeaderMapper inboundHttpHeaderMapper) {

        return IntegrationFlow.from(
                Http.inboundGateway("/ingest/orders")
                    .requestMapping(m ->
                        m.methods(HttpMethod.POST))
                    .requestPayloadType(String.class)
                    .headerMapper(inboundHttpHeaderMapper))
            .handle(String.class, (payload, headers) -> {
                // Demo: chỉ phản hồi độ dài payload.
                // Production cần validate, persist/ACK rõ ràng.
                return "accepted bytes/chars=" + payload.length();
            })
            .get();
    }
}
~~~

Để chạy:

- Có `spring-integration-http` và web stack tương ứng; application chạy với Spring Boot web starter phù hợp.
- Http endpoint path/method không trùng route khác.
- HTTP request payload là String trong ví dụ; production nên parse schema/JSON và validate size/type.
- HeaderMapper bean phải là mapper configured theo hướng **HTTP inbound**.
- Gateway sẽ nhận Spring Message từ HTTP và trả HTTP response từ reply handler. Chưa có persist business, nên response “accepted” chỉ chứng minh demo handler chạy.
- Các HTTP framework headers tự sinh ngoài mapper cũng có thể tồn tại; đừng khẳng định mọi header trong Message chỉ có các entries của `mapper.toHeaders()`.

### 6.1. Thử nghiệm bằng curl

~~~bash
curl -i -X POST http://localhost:8080/ingest/orders \
  -H 'Content-Type: application/json' \
  -H 'X-Trace-Id: trace-a7' \
  -H 'X-Partner-Event-Id: event-101' \
  -H 'X-Untrusted-Role: admin' \
  -d '{"orderId":"order-1001","amount":125.00}'
~~~

Handler demo trả một String; trong integration test nên **kiểm tra headers thực tế** tại handler, không chỉ status 200. Header `X-Untrusted-Role` không nên xuất hiện do mapper cho phép quá rộng.

### 6.2. XML wiring (phương án thay thế)

~~~xml
<!-- Cần khai báo XML namespaces int, int-http và các channels.
     inboundHttpHeaderMapper là bean đã đăng ký. -->
<int-http:inbound-gateway
        id="ordersGateway"
        path="/ingest/orders"
        request-channel="ordersInput"
        header-mapper="inboundHttpHeaderMapper"
        request-payload-type="java.lang.String"/>
~~~

Đây là cấu hình **thay thế Java DSL**, không đăng ký đồng thời cả hai vào cùng HTTP path. Với XML, có thể dùng `mapped-request-headers` để khai các patterns thay vì inject custom mapper, nhưng **không kết hợp hai cách cấu hình khi schema/endpoint không cho phép**.

### 6.3. DSL mappedRequestHeaders hoặc headerMapper

Nếu chỉ cần pattern đơn giản, có thể cấu hình trực tiếp trên spec:

~~~java
Http.inboundGateway("/ingest/orders")
    .mappedRequestHeaders(
        "Content-Type",
        "X-Trace-Id",
        "X-Partner-Event-Id");
~~~

Đây là **builder fragment** — nối với `IntegrationFlow.from(...)`. Với logic custom, dùng `.headerMapper(inboundHttpHeaderMapper)` thay vì cố cấu hình cả mapped headers và mapper riêng trên cùng endpoint; đọc API version để biết precedence.

## 7. Tự viết HeaderMapper khi cần policy đặc biệt

Khi `DefaultHttpHeaderMapper` không đủ để chuẩn hóa một external header, có thể implement `HeaderMapper<HttpHeaders>`. Mục tiêu là **map một trace ID đã kiểm tra** chứ không copy tất cả từ client.

~~~java
package example.headers;

import java.util.HashMap;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.integration.mapping.HeaderMapper;
import org.springframework.messaging.MessageHeaders;

public final class SafeTraceHttpHeaderMapper
        implements HeaderMapper<HttpHeaders> {

    private static final String EXTERNAL =
            "X-External-Trace-Id";
    private static final String INTERNAL =
            "externalTraceId";

    @Override
    public Map<String, Object> toHeaders(HttpHeaders source) {
        Map<String, Object> mapped = new HashMap<>();
        String value = source.getFirst(EXTERNAL);

        if (isAllowed(value)) {
            mapped.put(INTERNAL, value);
        }
        return mapped;
    }

    @Override
    public void fromHeaders(
            MessageHeaders headers,
            HttpHeaders target) {
        Object value = headers.get(INTERNAL);

        if (value instanceof String trace
                && isAllowed(trace)) {
            target.set(EXTERNAL, trace);
        }
    }

    private static boolean isAllowed(String value) {
        return value != null
            && value.matches("[A-Za-z0-9_-]{1,64}");
    }
}
~~~

**Giới hạn của custom mapper này:**

- Nó chỉ map một trace field; **không xử lý standard HTTP headers như Content-Type**. Nếu gắn vào inbound gateway có reply content negotiation, kiểm thử toàn bộ HTTP contract hoặc delegate sang DefaultHttpHeaderMapper cho phần standard được cho phép.
- `fromHeaders(...)` hiện gửi lại trace vào HTTP response; trong production có thể bỏ qua outbound phần này nếu không muốn phản chiếu external input cho caller.
- Validation bằng regex không phải xác thực truy vết: client vẫn có thể gửi bất kỳ trace text hợp lệ. Hãy có server-generated trace ID riêng.
- Không trả `null` thay map rỗng.
- Không chấp nhận header role/admin/tenant làm trusted authorization chỉ vì nó hợp regex.
- Nếu một header có nhiều values, `getFirst` có nghĩa chỉ lấy một; production cần quy định **từ chối nhiều giá trị** đối với các security-sensitive singleton headers.

### 7.1. Test custom mapper

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.MessageHeaders;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SafeTraceHttpHeaderMapperTest {

    private final SafeTraceHttpHeaderMapper mapper =
            new SafeTraceHttpHeaderMapper();

    @Test
    void acceptsValidTraceOnly() {
        HttpHeaders in = new HttpHeaders();
        in.add("X-External-Trace-Id", "trace_001");
        assertEquals("trace_001",
            mapper.toHeaders(in).get("externalTraceId"));
    }

    @Test
    void rejectsInvalidTrace() {
        HttpHeaders in = new HttpHeaders();
        in.add("X-External-Trace-Id", "../../admin");
        assertFalse(
            mapper.toHeaders(in).containsKey("externalTraceId"));
    }

    @Test
    void mapsSafeTraceToResponseWhenRequested() {
        HttpHeaders response = new HttpHeaders();
        MessageHeaders internal = new MessageHeaders(
                Map.of("externalTraceId", "trace_001"));

        mapper.fromHeaders(internal, response);

        assertEquals("trace_001",
            response.getFirst("X-External-Trace-Id"));
    }
}
~~~

Đây là unit test của mapping logic, không khởi tạo HTTP server hay Spring Integration endpoint. Bổ sung integration test với gateway để xác minh mapper thực sự được inject và header vượt ranh giới request/response đúng contract.
## 8. JMS inbound: DefaultJmsHeaderMapper

JMS có API header và properties riêng. Trong Spring Boot 3.x, JMS types thuộc `jakarta.jms`; Spring Integration mapper ở package:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;
import org.springframework.integration.jms.JmsHeaderMapper;
import org.springframework.integration.jms.JmsHeaders;
~~~

`DefaultJmsHeaderMapper` chuyển JMS API headers và custom JMS properties vào Spring `MessageHeaders`. Mapping **không đổi** JMS body: body được `MessageConverter` xử lý, mặc định thường chuyển `TextMessage` sang String và `BytesMessage` sang byte[].

### 8.1. Những JMS headers cần hiểu

| JMS API header/property | Spring header thông thường | Ý nghĩa |
|---|---|---|
| `JMSMessageID` | `jms_messageId` | ID do JMS provider gán; không phải Spring MessageHeaders.ID |
| `JMSCorrelationID` | `jms_correlationId` | JMS request/reply correlation |
| `JMSReplyTo` | `jms_replyTo` | JMS reply destination |
| `JMSRedelivered` | `jms_redelivered` | Message đã có thể được giao lại |
| `JMSDestination` | `jms_destination` | Destination mà provider sử dụng |
| `JMSPriority` | `priority` khi bật inbound mapping theo mapper | Transport QoS |
| `JMSDeliveryMode` | `jms_deliveryMode` khi bật option | Delivery mode |
| `JMSExpiration` | `jms_expiration` khi bật option | Expiration timestamp |
| Custom `businessEventId` property | `businessEventId` nếu type/name được hỗ trợ | Business ID từ producer |

Tên, kiểu và quyền map chính xác phải tra `JmsHeaders` theo version. `jms_correlationId` phản ánh **JMSCorrelationID**, khác Spring `correlationId` dùng trong aggregator/resequencer; không hoán đổi tùy ý.

### 8.2. Đăng ký DefaultJmsHeaderMapper

~~~java
package example.headers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;

@Configuration
public class InboundJmsHeaderConfig {

    @Bean("inboundJmsHeaderMapper")
    public DefaultJmsHeaderMapper inboundJmsHeaderMapper() {
        DefaultJmsHeaderMapper mapper =
                new DefaultJmsHeaderMapper();

        mapper.setMapInboundPriority(true);
        mapper.setMapInboundDeliveryMode(true);
        mapper.setMapInboundExpiration(true);
        return mapper;
    }
}
~~~

Option priority/delivery mode/expiration cung cấp **metadata từ inbound JMS** theo contract của mapper. Không làm một JMS message đang được xử lý tự thay QoS chỉ bằng việc đổi các Spring headers.

### 8.3. JMS message-driven inbound adapter

~~~java
package example.headers;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class JmsOrdersInboundFlow {

    @Bean
    public IntegrationFlow jmsOrdersInbound(
            ConnectionFactory jmsConnectionFactory,
            DefaultJmsHeaderMapper inboundJmsHeaderMapper) {

        return IntegrationFlow.from(
                Jms.messageDrivenChannelAdapter(
                        jmsConnectionFactory)
                    .destination("orders.in")
                    .headerMapper(inboundJmsHeaderMapper))
            .channel("ordersFromJms")
            .get();
    }
}
~~~

Cần `spring-integration-jms`, broker/destination thực, security/connection config, và consumer nhận messages từ `ordersFromJms`. Một **message-driven adapter** nhận callback từ JMS listener container; nó **không phải** `Jms.inboundAdapter(...)` polling source cần poller.

### 8.4. JMS redelivery, correlation và error channel

- `JMSMessageID` là ID transport, không tự là idempotency key nghiệp vụ.
- `JMSCorrelationID` phục vụ JMS request/reply; business event ID nên là property riêng được ràng buộc với nội dung đã validate.
- `JMSRedelivered=true` thông báo provider đã giao lại, **không** chứng minh side effect trước đó đã commit hay chưa.
- Khi mapper/converter lỗi, transaction/error-channel policy quyết định broker rollback/redeliver hay ACK; **mapper không điều khiển session ACK**.
- Nếu error channel chỉ log rồi return, JMS container transacted có thể commit message tùy wiring; với dữ liệu không được mất, phải có durable DLQ hoặc propagate exception đúng contract.
- JMS custom properties không chấp nhận arbitrary Java objects; chuyển giá trị sang kiểu được JMS hỗ trợ trước khi gửi outbound.

### 8.5. JMS end-to-end test nên kiểm tra gì?

1. Producer gửi một `TextMessage` có `JMSCorrelationID` và custom String property `businessEventId`.
2. JMS inbound adapter nhận và mapper tạo Spring headers mong đợi.
3. Assert `jms_correlationId` tồn tại và không bị đồng nhất với Spring Message ID.
4. Assert `businessEventId` đã đến business handler đúng kiểu.
5. Test JMS redelivery/rollback và kiểm tra `jms_redelivered` chỉ là metadata quan sát.
6. Test conversion failure đi error channel và xác minh transaction rollback/DLQ theo policy, không chỉ assert exception được log.

## 9. AMQP inbound: DefaultAmqpHeaderMapper

AMQP có `MessageProperties` chứa broker fields và một map custom headers. Class Spring Integration:

~~~java
org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper
org.springframework.integration.amqp.support.AmqpHeaderMapper
org.springframework.amqp.core.MessageProperties
org.springframework.amqp.support.AmqpHeaders
~~~

### 9.1. AMQP headers thường gặp

| Transport metadata | Spring MessageHeader thường gặp | Lưu ý |
|---|---|---|
| Received routing key | `amqp_receivedRoutingKey` | Từ routing thực nhận |
| Received exchange | `amqp_receivedExchange` | Tên exchange |
| Delivery tag | `amqp_deliveryTag` | Chỉ có nghĩa trong broker channel/delivery đó |
| Redelivered | `amqp_redelivered` | Có thể là redelivery |
| Consumer queue | `amqp_consumerQueue` | Queue listener dùng |
| Message ID | `amqp_messageId` | Không phải Spring ID |
| Correlation ID | `amqp_correlationId` | AMQP request/reply |
| Content type | `contentType` | Đặc biệt: không dùng prefix `amqp_` |
| Custom headers | `businessEventId`, `appTraceId` | Chỉ nhận khi policy cho phép |

### 9.2. Chỉ map các headers cần thiết

~~~java
package example.headers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

@Configuration
public class InboundAmqpHeaderConfig {

    @Bean("inboundAmqpHeaderMapper")
    public DefaultAmqpHeaderMapper inboundAmqpHeaderMapper() {
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

**Giải thích hướng:**

- `setRequestHeaderNames(...)` chọn AMQP request headers được đọc **vào** Spring Message.
- `STANDARD_REQUEST_HEADERS` là token cho standard AMQP properties theo `AbstractHeaderMapper`.
- `businessEventId`, `appTraceId` là custom properties do producer tạo.
- `!x-*` ưu tiên loại các headers do broker/federation có tiền tố x-, như `x-received-from`.
- `setReplyHeaderNames(...)` áp cho reply/outbound direction, **không thay** request policy.

Tài liệu Spring Integration theo version có mô tả khác nhau về việc default mapper tự map custom headers; một số Javadoc cũ chỉ nói standard properties, trong khi Reference Guide trình bày default rộng hơn và cảnh báo riêng `x-*`. **Đừng phụ thuộc default ngầm**: khai báo patterns tường minh và test với đúng phiên bản/adapter.

### 9.3. AMQP XML inbound adapter dùng header-mapper

~~~xml
<!-- Cần XML namespaces int-amqp, ConnectionFactory,
     queue orders.in và downstream channel thực tế. -->
<int-amqp:inbound-channel-adapter
        id="ordersAmqpInbound"
        queue-names="orders.in"
        channel="ordersFromAmqp"
        header-mapper="inboundAmqpHeaderMapper"/>
~~~

Đây là XML **phương án độc lập**, không đăng ký trùng một listener Java DSL cùng queue khi muốn kiểm thử một pipeline. Nếu dùng `mapped-request-headers` trực tiếp trên adapter, không đồng thời dùng `header-mapper` khi schema quy định hai option loại trừ.

### 9.4. Test mapper AMQP không cần RabbitMQ server

~~~java
package example.headers;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

import static org.junit.jupiter.api.Assertions.*;

class AmqpHeaderPolicyTest {

    @Test
    void mapsBusinessHeaderButNotFederationHeader() {
        DefaultAmqpHeaderMapper mapper =
                new DefaultAmqpHeaderMapper();

        mapper.setRequestHeaderNames(
                "STANDARD_REQUEST_HEADERS",
                "businessEventId",
                "!x-*");

        MessageProperties props = new MessageProperties();
        props.setHeader("businessEventId", "evt-101");
        props.setHeader("x-received-from", "node-internal");

        Map<String, Object> mapped = mapper.toHeaders(props);

        assertEquals("evt-101", mapped.get("businessEventId"));
        assertFalse(mapped.containsKey("x-received-from"));
    }
}
~~~

Đây là **unit test mapping**, không chứng minh ACK hoặc RabbitMQ queue integration. Bổ sung test thật với broker và một inbound gateway để xác minh reply không vô ý forward `x-received-from`.

### 9.5. Vì sao wildcard * có thể nguy hiểm?

Spring Integration docs cảnh báo về RabbitMQ federation: nếu inbound gateway copy các `x-*` header rồi gửi lại qua reply/outbound, broker có thể hiểu metadata ấy như dấu hiệu vòng lặp và drop message.

~~~text
Inbound RabbitMQ header:
  businessEventId = evt-101
  x-received-from  = broker-specific federation metadata

Unsafe wildcard:
  inbound MessageHeaders includes x-received-from
      -> reply copies it back
      -> federation misinterprets / may drop reply
~~~

Dùng allowlist hoặc negative patterns; nếu vẫn nhận wildcard, lọc header trước outbound. **DeliveryTag và broker channel** có vòng đời ngắn, không được serialize/forward sang HTTP/JMS như business metadata.

### 9.6. Mapping không thay ACK

Với `AcknowledgeMode.MANUAL`, adapter có thể cung cấp delivery tag/channel cho application ACK; `AcknowledgeMode.AUTO`/listener container có quy tắc khác. HeaderMapper **không** ACK broker, không bảo đảm message đã được lưu bền, và việc sửa `amqp_redelivered` không làm thay đổi redelivery policy.

## 10. Kafka: HeaderMapper ở Spring Kafka, không phải interface chung của Integration

Spring Integration Kafka inbound adapter dùng converter từ **Spring for Apache Kafka**, có header strategy riêng:

~~~java
org.springframework.kafka.support.KafkaHeaderMapper
org.springframework.kafka.support.DefaultKafkaHeaderMapper
org.springframework.kafka.support.SimpleKafkaHeaderMapper
org.springframework.kafka.support.converter.MessagingMessageConverter
~~~

`KafkaHeaderMapper` không mặc định là cùng kiểu Java generic `org.springframework.integration.mapping.HeaderMapper<T>` của HTTP/JMS. Kafka wire record headers có value dạng **`byte[]`** và **có thể có nhiều entries cùng key**.

### 10.1. Metadata Kafka cần giữ đúng kiểu

| Metadata | Ý nghĩa | Bẫy thường gặp |
|---|---|---|
| Received topic | Topic thực nhận | Không dùng raw client header để ghi đè |
| Received partition | Partition của record | Không phải tenant |
| Offset | Vị trí record trong partition | Không phải business event ID |
| Received record key | Kafka key đã deserialize theo consumer | Không nhất thiết globally unique |
| Timestamp/type | Broker/record metadata | Không phải thời gian business commit |
| Custom headers | Thường là bytes/JSON-encoded | Phải decode theo contract/version |
| Acknowledgment object | Có thể chỉ xuất hiện với manual ACK | Không serialize/forward qua JMS/HTTP |

Một số metadata được `MessagingMessageConverter` tạo **từ ConsumerRecord properties**, không đến từ raw Kafka record header map.

### 10.2. Cấu hình custom Kafka mapper qua converter

Fragment theo Spring Kafka 3.x/phiên bản tương thích:

~~~java
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;

MessagingMessageConverter converter =
        new MessagingMessageConverter();

converter.setHeaderMapper(
        new SimpleKafkaHeaderMapper(
                "businessEventId",
                "appTraceId"));
~~~

Sau đó inject converter vào Spring Integration Kafka inbound adapter theo API `setMessageConverter(...)` hoặc DSL hỗ trợ ở phiên bản đang dùng. **Đây không phải một IntegrationFlow hoàn chỉnh**; cần ConsumerFactory, listener container, group/topic và error handling.

- `SimpleKafkaHeaderMapper` ưu tiên raw byte representation, không tùy tiện khôi phục arbitrary Java object.
- `DefaultKafkaHeaderMapper` hỗ trợ JSON type mapping; với input từ nguồn không tin cậy phải giới hạn trusted packages/types.
- Nhiều values cùng Kafka header name có thể được xử lý khác nhau theo version/multi-value-header policy; không tự cho rằng tất cả đều được giữ.
- Không forward Kafka offset/ack object thành JMS property hoặc HTTP header; normalize business headers riêng.

### 10.3. Kafka retry và idempotency

Nếu Kafka redeliver sau MongoDB commit nhưng trước khi commit offset, Spring Message mới có thể có `MessageHeaders.ID` khác. Dùng `businessEventId` ổn định và durable inbox/unique index theo nghiệp vụ. **Mapper không tự commit offset hoặc tạo exactly-once**.
## 11. File/FTP/SFTP/SMB và TCP/UDP: adapter tạo headers trực tiếp

HTTP/JMS/AMQP có mapper cho external headers, nhưng **không phải mọi adapter đều có một HeaderMapper generic**. Với File/FTP/SFTP/SMB/IP, framework thường gắn protocol metadata vào Spring `MessageHeaders` ngay khi tạo message.

### 11.1. Remote file headers

Spring Integration cung cấp:

~~~java
org.springframework.integration.file.FileHeaders
~~~

Các constants liên quan:

| Header constant | Mục đích | Lưu ý |
|---|---|---|
| `FileHeaders.FILENAME` | Tên file cho file-output naming | Không tự có ở mọi file inbound message |
| `FileHeaders.REMOTE_DIRECTORY` | Thư mục remote | Có ở các FTP/SFTP/SMB source hỗ trợ |
| `FileHeaders.REMOTE_FILE` | Tên remote file | Tùy operation/source |
| `FileHeaders.REMOTE_HOST_PORT` | Host:port session | Chỉ khi adapter có remote session metadata |
| `FileHeaders.REMOTE_FILE_INFO` | Thông tin file remote | Kiểu JSON/object tùy adapter/version |

Đừng suy ra business identity hoặc file transfer đã hoàn tất chỉ bằng `REMOTE_FILE`. Có thể trùng tên file ở hai partners, thay mtime, hoặc remote file chưa upload xong. Cần file naming contract, checksum/business ID, persistent accept-once filter và recovery sau crash.

### 11.2. Dùng HeaderEnricher khi adapter không có HeaderMapper chung

~~~java
@Bean
public IntegrationFlow partnerFileFlow(
        org.springframework.integration.core.MessageSource<?> sftpSource) {

    return IntegrationFlow.from(sftpSource,
            e -> e.poller(Pollers.fixedDelay(5000)))
        .enrichHeaders(h ->
            h.header("sourceSystem", "partner-a-sftp"))
        .channel("partnerFiles")
        .get();
}
~~~

Đây là **fragment** với SFTP source, polling configuration, session factory và downstream consumer do ứng dụng cung cấp. `sourceSystem` là server configuration, không phải một tên do file từ remote tự khai. Không cần gắn `DefaultHttpHeaderMapper` cho SFTP.

### 11.3. IpHeaders cho UDP/TCP

Spring Integration IP cung cấp:

~~~java
org.springframework.integration.ip.IpHeaders
~~~

UDP inbound có thể tạo headers IP address/port/packet address, TCP inbound có connection ID/related metadata theo adapter và connection factory.

~~~java
Message<?> incoming = ...;

Object ip = incoming.getHeaders()
    .get(org.springframework.integration.ip.IpHeaders.IP_ADDRESS);

Message<?> normalized =
    MessageBuilder.fromMessage(incoming)
        .setHeader("sourceTransport", "udp")
        .setHeader("externalSourceAddress", ip)
        .build();
~~~

Đây là ứng dụng `MessageBuilder` sau adapter, **không phải HeaderMapper raw UDP**. IP nguồn không phải authenticated identity vì NAT, proxy và spoofing; UDP cũng không tự có reliability/dedup.

## 12. Thiết kế application header contract chung cho nhiều nguồn

Khi HTTP, JMS, AMQP, Kafka và SFTP đều đưa message vào cùng business channel, business handler không nên phải hiểu mọi tên protocol header khác nhau. Chuẩn hóa tại ingress:

| Application header | Kiểu | Nguồn tin cậy | Dùng cho |
|---|---|---|---|
| `businessEventId` | String | ID ổn định từ payload/producer đã validate | Idempotency |
| `appTraceId` | String | Tracing context/hint đã chuẩn hóa | Truy vết |
| `trustedTenantId` | String | Authentication/authorization server-side | Tenant isolation |
| `sourceSystem` | String/enum | Endpoint configuration | Routing |
| `sourceProtocol` | String/enum | Adapter identity | Metrics, debugging |
| `receivedAt` | Instant | Server clock | SLA |
| `schemaVersion` | String/int | Event schema contract | Parser selection |
| `contentType` | MediaType/String | Converter/mapping đã validate | Decode |

### 12.1. Nhiều ingress, một hợp đồng chuẩn

~~~mermaid
flowchart LR
  H["HTTP Mapper"] --> N["Validate + normalize"]
  J["JMS Mapper"] --> N
  A["AMQP Mapper"] --> N
  K["Kafka converter"] --> N
  S["SFTP source"] --> N
  N --> C["canonicalInbound channel"]
  C --> B["Business handler"]
~~~

Business handler chỉ đọc keys đã được kiểm tra, không phụ thuộc protocol source.

### 12.2. Một số metadata không được copy xuyên giao thức

Ví dụ Kafka → JMS:

- `kafka_offset`, partition, acknowledgment object không phải JMS properties nghiệp vụ.
- Kafka custom header có thể là byte[] nhưng JMS property có những kiểu giới hạn.
- HTTP Authorization là bí mật, không forward sang broker/log.
- AMQP deliveryTag và channel object chỉ có nghĩa trong listener hiện tại.
- `replyChannel`/`errorChannel` của Spring Integration là routing objects, không serialize sang external headers.
- Chỉ copy `businessEventId`/`appTraceId` và fields cần thiết sau validation.

### 12.3. Immutable contract cho values

Spring `MessageHeaders` mang contract không sửa map trực tiếp; nhưng value có thể là object mutable. Không để `Map`/`List` từ transport được nhiều threads cùng mutate hoặc giữ reference session/socket vào message bền. Khi cần, copy/convert thành String/record/immutable collection có giới hạn kích thước.

## 13. HeaderEnricher, HeaderFilter và MessageBuilder sau mapping

`HeaderMapper` xử lý **protocol boundary**. Sau khi đã có Spring Message, Spring Integration có EIPs:

- **HeaderEnricher**: gắn application metadata.
- **HeaderFilter**: loại bỏ một số header.
- **Transformer**: đổi payload/headers và xây message mới.
- **Router**: định tuyến theo header đã được validate.
- **ServiceActivator**: nhận payload, header values và gọi nghiệp vụ.

### 13.1. XML HeaderFilter

~~~xml
<int:header-filter
        input-channel="rawInbound"
        output-channel="filteredInbound"
        header-names="Authorization,X-Untrusted-Role"/>
~~~

Cần XML namespace `int` và các channels/consumers. Filter dùng **tên header sau mapping**; nếu external X-Trace-Id đã chuẩn hóa thành appTraceId, loại tên X-Trace-Id không tác động appTraceId.

### 13.2. Java DSL filter/enrich

~~~java
@Bean
public IntegrationFlow normalizeInbound() {
    return IntegrationFlow.from("rawInbound")
        .headerFilter(
            "Authorization", "X-Untrusted-Role")
        .enrichHeaders(h -> h
            .header("sourceSystem", "partner-a")
            .headerExpression(
                "serverReceivedAt",
                "T(java.time.Instant).now().toString()"))
        .channel("canonicalInbound")
        .get();
}
~~~

Đây là fragment trong `@Configuration` với upstream rawInbound/downstream canonicalInbound. `sourceSystem` do server quyết định; SpEL expression là **trusted application configuration**, không cho client truyền arbitrary expression.

### 13.3. MessageBuilder thêm trusted tenant và business ID

~~~java
Message<?> clean = MessageBuilder.fromMessage(incoming)
    .removeHeader("Authorization")
    .removeHeader("X-Untrusted-Role")
    .setHeader("sourceProtocol", "http")
    .setHeader("trustedTenantId", authorizedTenantId)
    .setHeader("businessEventId", verifiedEventId)
    .build();
~~~

`authorizedTenantId` phải đến từ authenticated principal/ACL; `verifiedEventId` phải được validate và ràng buộc với payload. Tránh lấy chúng trực tiếp từ client headers chưa kiểm chứng.

### 13.4. @ServiceActivator đọc contract

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class CanonicalEventHandler {

    @ServiceActivator(inputChannel = "canonicalInbound")
    public void process(
            String payload,
            @Header("businessEventId") String eventId,
            @Header("trustedTenantId") String tenantId) {

        // Business service phải xác minh schema và idempotency.
    }
}
~~~

Nếu header bắt buộc không tồn tại hoặc sai kiểu, argument binding có thể ném messaging/conversion exception. Đó là input error cần xử lý rõ, không tự coi nó là header rỗng hợp lệ.
## 14. Bảo mật inbound headers: external data không phải trusted state

Bất cứ header nào đến từ HTTP client, JMS/AMQP/Kafka producer, tên file SFTP hay UDP sender đều phải xem là **input từ hệ thống ngoài** cho đến khi ứng dụng xác minh.

| External header | Sai lầm nguy hiểm | Policy an toàn |
|---|---|---|
| HTTP Authorization | Forward bearer token vào Kafka/JMS/log | Spring Security xác minh, chỉ giữ principal/claims cần |
| HTTP X-Tenant-Id | Chọn MongoDB collection theo header do client gửi | Tenant lấy từ authenticated identity/ACL |
| HTTP X-Forwarded-For | Tin địa chỉ client bất kỳ | Tin only configured reverse proxy chain |
| HTTP X-Role | Map role=admin và route | Role từ IAM/access control server-side |
| JMS businessEventId | Coi là đúng chỉ vì là JMS property | Validate producer, schema/tenant/length |
| AMQP x-* | Phản chiếu broker federation headers sang reply | Filter/allowlist và test reply |
| Kafka type header | Deserialize arbitrary Java class | Trusted packages/schema allowlist |
| SFTP remote filename | Ghép path không normalize | Giới hạn root dir và validate filename |
| UDP source IP | Dùng như authentication | Auth/signature ở tầng ứng dụng |
| External reply routing | Cho client chọn internal replyChannel bean | Gateway/server routing policy |

### 14.1. Reserved/internal header collision

External producer có thể đặt tên `id`, `timestamp`, `replyChannel`, `errorChannel`, `trustedTenantId` hoặc header bị business router hiểu như lệnh điều khiển.

- Spring framework có thể bảo vệ một số core headers nhưng đừng xem đó là security boundary hoàn chỉnh.
- Không map `*` từ external headers vào toàn bộ MessageHeaders không kiểm soát.
- Tách external hint `X-Trace-Id` khỏi server-generated `appTraceId` khi yêu cầu truy vết tin cậy.
- Tạo `trustedTenantId` **sau** authentication, không cho raw external header ghi đè.
- Reply routing phải qua gateway policy, không lấy raw request header như một bean name hoặc destination tùy ý.

### 14.2. Input size và header injection

Bổ sung giới hạn:

1. Số lượng headers và tổng bytes metadata.
2. Độ dài từng key/value và số repeated values.
3. Charset, Unicode normalization và control characters CR/LF.
4. JSON type hints và class names trong Kafka/AMQP.
5. Nội dung log/error messages: không vô tình ghi token, credentials, PII, raw payload.
6. Metric labels: không dùng từng request ID/event ID làm label high-cardinality.

Với HTTP inbound gateway, một custom mapper có method `fromHeaders(...)` còn có thể viết headers vào **HTTP response**. Không echo untrusted value chứa CR/LF hoặc secret; chỉ allowlist những response headers thực sự cần và validate.

## 15. Kiểu dữ liệu, casing và multiple values

### 15.1. HTTP header names là case-insensitive

HTTP `X-Trace-Id` và `x-trace-id` cùng tên ở wire protocol; nhưng một Java `Map<String,Object>` không tự bảo đảm case-insensitive key lookups.

Không nên:

~~~java
String trace = (String) message.getHeaders()
        .get("x-trace-id"); // Có thể null/sai kiểu.
~~~

Nên dùng HttpHeaders extraction có contract rõ ràng ở boundary, normalize thành `appTraceId` kiểu String đã validate, rồi business handlers chỉ đọc canonical key.

### 15.2. Multi-value header và ambiguous identity

~~~http
X-Partner-Event-Id: event-101
X-Partner-Event-Id: event-102
~~~

Nếu event ID bắt buộc là **một** giá trị, từ chối multiple distinct values thay vì chọn cái đầu hay ghép dấu phẩy. Với `Accept`, multiple values có semantics khác; policy phải theo từng header, không dùng một hàm `String.join(",")` cho mọi loại.

### 15.3. Kafka có repeated record headers

Kafka record có thể chứa nhiều header cùng key. Spring Kafka converter có chính sách mapping JSON/simple/multi-value tùy version. Test cần xác nhận đã giữ, gộp hay chọn một giá trị; không giả định một `KafkaHeaderMapper` luôn bảo toàn mọi entries.

### 15.4. JMS properties bị giới hạn type

JMS properties hỗ trợ các kiểu nguyên thủy/chuỗi nhất định, không phải map arbitrary Java object. Nếu chuyển `Kafka → JMS`, một header byte[]/List/Map có thể không phù hợp JMS. Chuẩn hóa trước khi gửi; đừng cast mù.

### 15.5. Bảng tình huống validation

| Trạng thái | Ví dụ | Chính sách |
|---|---|---|
| Header vắng | Không có businessEventId | Reject nếu business yêu cầu |
| Header rỗng | businessEventId="" | Reject hoặc generate server-side theo contract |
| Header sai định dạng | Event ID quá dài hoặc chứa ký tự lạ | Reject/quarantine |
| Multi-value conflict | Hai IDs trên một HTTP request | Reject |
| Header/body mismatch | External eventId khác JSON eventId | Conflict, không tự ưu tiên ngầm |
| Sai kiểu | byte[] nhưng handler mong String | Convert có schema, tránh ClassCastException |
| Header reserved | External replyChannel / trustedTenantId | Không cho ghi đè |
| Header trùng tên với case khác | X-TRACE-ID và x-trace-id | Normalize/reject ambiguity |

## 16. Correlation, tracing và idempotency không phải một loại ID

Một inbound event có thể mang:

~~~text
Spring MessageHeaders.id  = <UUID của Spring Message>
HTTP X-Trace-Id           = trace-006
JMS jms_messageId         = ID:provider:...
JMS jms_correlationId     = request-42
AMQP amqp_messageId       = msg-808
Kafka offset              = topic orders, partition 2, offset 1801
Business eventId          = order-accepted-1001
~~~

Phân biệt:

- **Spring Message ID:** định danh một Spring Message instance, có thể đổi sau rebuild/transform/redelivery.
- **Correlation ID:** liên kết request/reply, aggregator hoặc trace; không tự là idempotency ID.
- **Protocol Message ID:** định danh trong broker/giao thức, có thể đổi khi republish.
- **Kafka offset:** vị trí theo topic-partition, không globally unique theo business.
- **Business event ID:** ID do domain/producer contract bảo đảm ổn định qua retry, thường là khóa của durable inbox/dedup.

### 16.1. Ví dụ dedup key đúng ngữ cảnh

~~~text
External HTTP header X-Partner-Event-Id = event-101
JSON body.eventId                       = event-101
Authorized tenant                        = tenant-a
Dedup business key                       = (tenant-a, event-101)
~~~

Header và payload phải khớp theo contract; nếu cùng ID nhưng payload khác, đây là conflict cần đối soát, không phải duplicate hợp lệ được ACK mù.

### 16.2. Correlation trong inbound gateway

JMS gateway có thể dùng `JMSCorrelationID` để trả reply đến đúng request. HTTP gateway có request/response context của transport. Đừng dùng `MessageHeaders.ID` thay `JMSCorrelationID` hoặc `appTraceId` để suy ra business event identity.

Nếu cần route theo reply header, chỉ cho phép những destinations được server cấu hình/authorize; không để client tự gắn `replyChannel` và kiểm soát internal routing.

### 16.3. HeaderMapper không tạo exactly-once

Map `businessEventId` đúng giúp triển khai durable inbox/idempotent consumer; **nó không commit Kafka offset, không ACK JMS/AMQP, không move SFTP file, không xử lý UDP loss**. Transaction/ACK/retry/recovery là công việc của adapter/handler/broker/service khác.

## 17. Lỗi tại bước header mapping và ảnh hưởng tới ACK

Một mapping error có thể xuất hiện:

~~~text
External message
    -> adapter receives
    -> HeaderMapper.toHeaders / MessageConverter
    -> validation/conversion error
    -> errorChannel / listener container / upstream response
~~~

**Không mặc định mọi lỗi đều đi đúng một error channel**: còn phụ thuộc adapter, asynchronous boundary, gateway, transaction config và exception thrown at source.

### 17.1. HTTP inbound gateway

- Header thiếu/sai kiểu/size → trả HTTP 400/422 theo exception mapping do application cấu hình.
- Chưa authenticate/authorize → 401/403 do security filter, **không** đợi HeaderMapper.
- Business handler lỗi → HTTP 5xx/timeout theo gateway/error policy.
- Một status 200 không chứng minh downstream Kafka/MongoDB đã commit nếu handler asynchronous và trả quá sớm.
- Không trả raw stack trace/token/header values trong response lỗi.

### 17.2. JMS message-driven adapter

- Conversion/mapping error có thể được đưa vào `ErrorMessage` qua error channel.
- Nếu error flow nuốt exception, listener transaction có thể commit thay vì rollback, dẫn đến message không redeliver.
- Với dữ liệu không được mất, cần propagate exception hoặc durable quarantine/DLQ trước ACK theo contract.
- `jms_redelivered` là metadata observation, không tự trigger retry.

### 17.3. AMQP inbound adapter

- Broker ACK mode manual/auto do container config, không do mapper.
- Không tự ACK bằng cách sửa `amqp_deliveryTag`/`amqp_redelivered` headers.
- Với `AcknowledgeMode.MANUAL`, delivery tag và channel gắn với listener/connection cụ thể; không forward/lưu lâu làm business metadata.
- Tránh vòng lặp poison-message khi schema không thể xử lý; cần reject/DLQ/quarantine policy.

### 17.4. Kafka inbound adapter

- Header mapper lỗi trong converter/deserializer có thể làm listener fail hoặc đi error handler/DLT theo container config.
- Commit offset/callback timing được xác định ở Kafka listener/adapter layer.
- Nếu retry cùng event, businessEventId phải ổn định; spring Message ID và offset không thay thế business key.
- Kafka record headers có thể chứa type information; hạn chế classes/trusted packages để không deserialize tùy tiện.

### 17.5. File/SFTP/IP

- File source có thể dùng accept-once filter/persistent MetadataStore; header mapping không tạo checkpoint giao dịch.
- SFTP download fail trước handler khác với handler fail sau download. Marker đã thấy có thể vẫn tồn tại, cần recovery.
- UDP không có broker ACK mặc định; payload/header parsing error cần policy drop/quarantine/alert đúng protocol.
- Timeout/mất ACK của downstream có thể tạo unknown result; replay cùng business ID thay vì ID mới.
## 18. Dependencies và môi trường thực hành

Chọn dependency theo đúng giao thức đang dùng. Ví dụ Maven cho ứng dụng muốn thực hành HTTP/JMS/AMQP/Kafka (Spring Boot 3.x, Spring Integration 6.x, quản lý version theo BOM):

~~~xml
<!-- Các dependency thuộc <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-http</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-amqp</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-kafka</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đây là **tập ví dụ**, không cần cài mọi module nếu sản phẩm chỉ dùng một protocol. JMS cần Jakarta JMS broker/client phù hợp, AMQP cần RabbitMQ, Kafka cần Kafka cluster/consumer factory, SFTP cần SSH/SFTP session factory. Với test dùng Testcontainers, CI runner cần Docker hoặc một test service thay thế.

| Giao thức | Module | HeaderMapper/metadata |
|---|---|---|
| HTTP Servlet | `spring-integration-http` | DefaultHttpHeaderMapper |
| WebFlux | `spring-integration-webflux` | HTTP/WebFlux endpoint mapping |
| JMS | `spring-integration-jms` | DefaultJmsHeaderMapper |
| RabbitMQ/AMQP | `spring-integration-amqp` | DefaultAmqpHeaderMapper |
| Kafka | `spring-integration-kafka` và Spring Kafka | KafkaHeaderMapper từ Spring Kafka |
| File/FTP/SFTP | `spring-integration-file/ftp/sftp` | FileHeaders, source metadata |
| TCP/UDP | `spring-integration-ip` | IpHeaders |
| MongoDB | `spring-integration-mongodb` | MongoDB sources, không dùng HTTP HeaderMapper |

## 19. Kiểm thử header mapping: unit đến end-to-end

### 19.1. Ma trận kiểm thử

| Test | Cấp | Assertion |
|---|---|---|
| HTTP allowlist | Unit | X-Trace-Id được map, X-Untrusted-Role bị loại |
| HTTP case-insensitive | Unit | X-Trace-Id/x-trace-id cùng semantic |
| HTTP multi-value ID | Unit | Reject hai event IDs trên một request |
| HTTP gateway mapping | Integration | Request đến handler, headers đúng |
| HTTP reply mapping | Integration | Không echo raw Authorization/Role |
| JMS correlation | Broker integration | jms_correlationId đúng, khác Spring ID |
| JMS custom property | Broker integration | businessEventId có đúng kiểu |
| JMS rollback | Broker integration | Error flow không ACK sai |
| AMQP allowlist | Unit | appTraceId được map, x-received-from bị chặn |
| AMQP gateway reply | Broker integration | Broker metadata không bị mirror |
| Kafka custom header | Converter unit | bytes → application value đúng |
| Kafka duplicate header | Converter unit | Multi-value policy đúng version |
| SFTP remote info | Integration | FileHeaders đúng khi adapter hỗ trợ |
| UDP sender metadata | Socket integration | IpHeaders phản ánh packet source |
| Tenant spoofing | Security integration | X-Tenant-Id không đổi trusted tenant |
| Missing business ID | Integration | Reject/quarantine có error policy |
| Restart/redelivery | Integration | Event ID ổn định và downstream idempotent |

### 19.2. MockMvc với HTTP inbound gateway

Với flow HTTP mục 6:

~~~java
package example.headers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class HttpOrdersInboundIT {

    @Autowired
    MockMvc mvc;

    @Test
    void gatewayResponds() throws Exception {
        mvc.perform(post("/ingest/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Trace-Id", "trace-100")
                .header("X-Partner-Event-Id", "event-101")
                .header("X-Untrusted-Role", "admin")
                .content("{\"orderId\":\"o-101\"}"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                org.hamcrest.Matchers.startsWith("accepted")));
    }
}
~~~

**Quan trọng:** test này chỉ chứng minh route và response; để **chứng minh HeaderMapper** đã gắn thật, cần capture Spring Message trong handler/test spy/wire tap và assert headers có/không được copy. Response HTTP 200 không tự chứng minh mapping hoặc durable business commit.

### 19.3. QueueChannel test sink

Một channel test bounded:

~~~java
@Bean("observedInbound")
public org.springframework.messaging.PollableChannel observedInbound() {
    return new org.springframework.integration.channel.QueueChannel(10);
}
~~~

Sau khi một inbound **one-way adapter** gửi message vào channel:

~~~java
Message<?> received = observedInbound.receive(2000);

assertNotNull(received);
assertNotNull(received.getHeaders().get("X-Partner-Event-Id"));
~~~

Đây là fragment trong test; wire/adapter phải nối tới `observedInbound`. Nếu bạn đưa inbound **gateway** thẳng vào QueueChannel mà không có handler reply, HTTP/JMS caller có thể bị timeout. Trong trường hợp gateway, dùng capture side-channel/wire tap hoặc test handler trả reply.

### 19.4. Broker integration tests

Unit test `DefaultAmqpHeaderMapper.toHeaders(...)` không cần RabbitMQ, nhưng để xác minh `amqp_deliveryTag`/ACK, redelivery/reconnect, manual/auto ACK phải dùng broker test. JMS tương tự với JMS provider; Kafka cần listener/container để test received topic/partition/offset, converter và DLT.

Một mapper unit test không chứng minh container transaction/offset commit. Khi mapping lỗi, error-channel flow có thể nuốt exception, làm nguồn ACK sai; test trường hợp đó.

## 20. Hiệu năng, logging và lifecycle

### 20.1. HeaderMapper nên thuần túy và bounded

Tránh dùng custom mapper để:

- Query database/HTTP service mỗi lần nhận message.
- Deserialize arbitrary object graphs/class names từ user type header.
- Copy wildcard toàn bộ broker-specific metadata.
- Gắn hàng trăm/những MB raw headers vào Spring Message.
- Log toàn bộ MessageHeaders chứa secrets.
- Thực hiện blocking I/O trên WebFlux/reactive event loop hoặc broker listener thread.

Một HeaderMapper tốt nên **deterministic, không I/O, ít cấp phát, validate nhanh và có giới hạn kích thước**. Authorization/database lookup thuộc một stage được thiết kế với timeout/caching phù hợp.

### 20.2. Gợi ý metrics

| Metric | Mục đích |
|---|---|
| `inbound_header_mapping_total` | Số lần mapper chạy |
| `inbound_header_mapping_error_total` | Lỗi mapper/conversion |
| `inbound_header_rejected_total` | Headers bị reject |
| `inbound_header_type_mismatch_total` | Type conversion sai |
| `inbound_header_missing_event_id_total` | Thiếu business ID |
| `inbound_header_validation_duration_seconds` | Latency validation |
| `inbound_authz_rejected_total` | Tenant/role conflict |
| `inbound_dlq_total` | Durable-quarantined events |
| `inbound_business_committed_total` | Số business effects hoàn tất |

Đây là **tên metric gợi ý**, không mặc định framework tự xuất ra. Không dùng từng eventId/deviceId/header value làm metric label gây cardinality cao.

### 20.3. Logging an toàn

~~~text
ingress_received      protocol=http source=partner-a
headers_mapped        headerCount=4
header_validated      tracePresent=true eventIdPresent=true
business_dispatched   route=orders
business_committed    outcome=accepted
~~~

Không log raw tokens, cookies, passwords, PII hoặc full payload. Với tracing context qua `ExecutorChannel`/Reactor, cấu hình context propagation; không tự giả định MDC ThreadLocal được giữ.

### 20.4. Vòng đời connector không phụ thuộc mapper

- HTTP: request/response timeout, servlet/reactive lifecycle.
- JMS/AMQP: listener connection, concurrency, broker ACK/redelivery.
- Kafka: consumer poll/rebalance/offset commit.
- SFTP/File: poller, remote/local filters, session/transfer.
- IP/UDP: datagram handling và connection state, không có broker ACK.
- MongoDB: query/poller/checkpoint/claim tùy source.

**HeaderMapper không khởi động/dừng poller, không tự retry broker hoặc drain in-flight messages.** Khi deploy, thiết kế durable source/replay/idempotency riêng.
## 21. Troubleshooting: header có ở transport nhưng mất trong flow

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| HTTP custom header không có | setInboundHeaderNames chưa include | Cấu hình allowlist và test toHeaders |
| Đã dùng HeaderMapper nhưng sai hướng | Gọi fromHeaders cho inbound request | Inbound dùng toHeaders(external) |
| Mapper có header, handler mất | HeaderFilter/Transformer/flow khác | Capture Message tại từng channel |
| Header casing khác | HTTP case-insensitive nhưng Java Map lookup khác | Normalize tên sang appTraceId |
| Custom mapper làm mất Content-Type | Override standard defaults | Thêm đúng Content-Type hoặc HTTP_REQUEST_HEADERS |
| HTTP request có hai event IDs | Không kiểm tra multiple values | Reject singleton ID ambiguity |
| HTTP Authorization bị forward ra broker | Wildcard copy | Exclude, security boundary/allowlist |
| X-Tenant-Id đổi tenant | Client input được coi là trusted | Principal/ACL server-side |
| Header bị ClassCastException | String vs List/byte[]/MediaType | Typed conversion theo contract |
| JMS messageId được dùng làm dedup | Nhầm protocol ID và business ID | Stable businessEventId |
| JMS correlation không khớp reply | Nhầm jms_correlationId/correlationId | Kiểm tra gateway correlation policy |
| JMS conversion error vẫn ACK | Error flow swallow exception | Transaction rollback hoặc durable DLQ |
| AMQP header x-received-from vào reply | Wildcard copy federation property | Filter/negative pattern |
| AMQP custom header mất | Default mapping khác phiên bản | Explicit requestHeaderNames |
| RabbitMQ deliveryTag vô hiệu | Dùng tag sau reconnect/khác channel | ACK đúng active channel |
| Kafka custom header là byte[] | Cast String trực tiếp | KafkaHeaderMapper/codec |
| Kafka type header gây deserialize lỗi | Class không trusted/schema sai | Trusted package/schema policy |
| Kafka duplicate header bị mất | Multi-value policy của converter | Kiểm tra version và test |
| SFTP remote filename header không có | Source/option không cung cấp | Đối chiếu FileHeaders/API |
| UDP IP được dùng làm identity | NAT/spoofing | App-level identity verification |
| replyChannel bị external override | Copy reserved headers | Restrict external keys |
| send() trả true nhưng business chưa commit | Async channel/service | ACK sau durable stage |
| ErrorMessage chỉ log rồi biến mất | Không có durable recovery | Re-throw/ack policy/DLQ |
| Request timeout dù mapper OK | Inbound gateway thiếu reply consumer | Configure reply handler/correlation |
| Tests pass nhưng broker lỗi | Chỉ test mapper unit | Integration test với broker/container |
| Header quá lớn gây memory pressure | Wildcard, unbounded size | Giới hạn tên/value/count/buffer |

### 21.1. Thứ tự khoanh vùng hợp lý

~~~text
1. Request/broker payload + external headers
2. Inbound adapter/gateway và MessageConverter
3. HeaderMapper.toHeaders(external) hoặc native adapter headers
4. Message<?> được tạo (type/name/values)
5. HeaderFilter/Enricher/Transformer/Router
6. Business handler (@Header và payload contract)
7. Error channel, ACK/retry, downstream commit
~~~

Log/tap từng stage trên test env, không log secrets. Nếu HTTP mapper unit test PASS nhưng HTTP flow không thấy header, kiểm tra **mapper bean thật sự được inject vào đúng endpoint** và có bước transform/filter nào thay message.

### 21.2. Các lỗi cần phân biệt

- **Missing header**: nguồn không gửi hoặc mapper chưa chọn.
- **Wrong type**: mapper đã chọn nhưng value là `List<String>`/`byte[]`.
- **Invalid value**: header có nhưng không qua validation.
- **Untrusted**: value có vẻ hợp lệ nhưng chưa authenticated/authorized.
- **Lost along flow**: transform/filter đã bỏ hoặc đổi tên.
- **Downstream failure**: headers đúng nhưng broker/DB không commit.
- **ACK ambiguity**: nguồn không biết message đã được bền hóa hay chưa.

Mỗi loại đòi hỏi cách xử lý khác nhau; không retry một malformed header vô hạn như lỗi kết nối transient.

## 22. Bài thực hành tổng hợp

Xây **HTTP/JMS/AMQP/Kafka/SFTP → HeaderMapper/Normalizer → MessageChannel → Router → business service**. Mỗi phần dùng một profile độc lập hoặc broker test, không cần bật mọi adapter cùng lúc.

### Phần A — HTTP inbound

1. Tạo `DefaultHttpHeaderMapper.inboundMapper()` và allowlist `Content-Type`, `X-Trace-Id`, `X-Partner-Event-Id`.
2. Unit test `toHeaders(HttpHeaders)` có các keys được chọn.
3. Assert `X-Untrusted-Role`, `Authorization` không được forward.
4. Dùng `Http.inboundGateway("/ingest/orders")`, nối vào một handler trả reply.
5. Thử curl/MockMvc request có eventId/traceId hợp lệ.
6. Capture Spring Message, assert casing/typed headers đúng thay vì chỉ status 200.
7. Gửi hai event IDs trong cùng request, áp reject policy.
8. Implement custom HeaderMapper map trace hint thành `externalTraceId`.

### Phần B — JMS

1. Cấu hình `DefaultJmsHeaderMapper` với inbound delivery mode/expiration/priority khi cần.
2. Dùng JMS message-driven channel adapter và broker test.
3. Gửi `JMSCorrelationID`, `businessEventId` property.
4. Kiểm tra `jms_correlationId` khác Spring MessageHeaders.ID.
5. Gây rollback/redelivery, kiểm tra `jms_redelivered` và ACK policy.
6. Gây conversion error, xác minh error channel/DLQ hoạt động thực sự.

### Phần C — AMQP/RabbitMQ

1. Dùng `DefaultAmqpHeaderMapper` có `STANDARD_REQUEST_HEADERS` và 2 custom keys.
2. Thử `MessageProperties.headers` có `x-received-from`.
3. Unit assert federation metadata không được map.
4. Cấu hình inbound adapter/gateway thật với broker test.
5. Kiểm tra reply không mirror `x-*`.
6. Thử manual ACK, phân biệt deliveryTag với event ID nghiệp vụ.

### Phần D — Kafka, SFTP và IP

1. Cấu hình Spring Kafka `MessagingMessageConverter` với header mapper phù hợp.
2. Gửi Kafka raw bytes header, test decode và duplicate names.
3. Dùng SFTP inbound source có remote file metadata.
4. Kiểm tra `FileHeaders.REMOTE_DIRECTORY`/`REMOTE_FILE` khi source hỗ trợ.
5. Gắn `sourceSystem` qua HeaderEnricher.
6. Thử UDP inbound, đọc `IpHeaders.IP_ADDRESS` và giải thích giới hạn tin cậy.
7. Chuẩn hóa các giao thức về `businessEventId`/`appTraceId`/`trustedTenantId`.

### Phần E — Production hardening

1. Viết bảng allowlist external header cho từng giao thức.
2. Quy định max header count/bytes, multi-value policy và validation regex.
3. Bắt header/body conflict và tenant spoofing.
4. Cấm external overwrites của `replyChannel`, `errorChannel`, `trustedTenantId`.
5. Test error handling không ACK source sớm khi mapping/conversion thất bại.
6. Test retry/redelivery vẫn giữ stable business event ID.
7. Đo metrics mapping/reject/latency, nhưng không log secrets/high-cardinality IDs.
8. Diễn tập deploy/restart, đảm bảo connector lifecycle và durable recovery.

**Câu hỏi tự đánh giá:**

- `HeaderMapper<T>` có hai method gì? Vì sao `toHeaders` là inbound?
- HeaderMapper khác MessageConverter và HeaderEnricher ra sao?
- DefaultHttpHeaderMapper.inboundMapper() áp dụng cho endpoint nào?
- setInboundHeaderNames có giữ các standard headers không liệt kê không?
- Vì sao `X-Tenant-Id` không tự là `trustedTenantId`?
- HTTP header name case-insensitive gây lỗi gì khi đọc Spring MessageHeaders?
- JMSCorrelationID khác Spring correlationId và businessEventId thế nào?
- `jms_redelivered` có chứng minh business commit không?
- Vì sao AMQP x-received-from có thể gây lỗi federation reply?
- AMQP contentType có prefix amqp_ không?
- KafkaHeaderMapper thuộc Spring Kafka khác interface Spring Integration HeaderMapper thế nào?
- Tại sao không copy Kafka offset/ack object sang JMS properties?
- SFTP remote headers khác một HTTP HeaderMapper ra sao?
- HeaderFilter có thay được HTTP authentication filter không?
- Vì sao HTTP response 200 không tự chứng minh mapper đúng/DB commit?
- Một error-channel handler chỉ log rồi return có thể ảnh hưởng broker ACK ra sao?
- Header mapper giúp gì cho idempotency và không giúp gì cho exactly-once?

## 23. Tài liệu tham khảo

- [Spring Integration API — HeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/mapping/HeaderMapper.html): `toHeaders`/`fromHeaders` strategy interface.
- [Spring Integration API — AbstractHeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/mapping/AbstractHeaderMapper.html): request/reply patterns.
- [Spring Integration Reference — HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html): DefaultHttpHeaderMapper và standard/request/response headers.
- [Spring Integration API — DefaultHttpHeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/http/support/DefaultHttpHeaderMapper.html): inboundMapper, setInboundHeaderNames, toHeaders.
- [Spring Integration API — HTTP Inbound Spec](https://docs.spring.io/spring-integration/api/org/springframework/integration/http/dsl/HttpInboundEndpointSupportSpec.html): headerMapper, mappedRequestHeaders, requestMapping.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): JMS header mapping, conversion, message-driven adapter, error channel.
- [Spring Integration API — DefaultJmsHeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/jms/DefaultJmsHeaderMapper.html): JMS headers và options.
- [Spring Integration API — JMS Message Driven Spec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsMessageDrivenChannelAdapterSpec.html): headerMapper(JmsHeaderMapper).
- [Spring Integration Reference — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html): AMQP standard headers, custom patterns, negative patterns và federation.
- [Spring Integration API — DefaultAmqpHeaderMapper](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/amqp/support/DefaultAmqpHeaderMapper.html): AMQP mapper.
- [Spring Integration Reference — AMQP Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/amqp/inbound-channel-adapter.html): header-mapper/mapped-request-headers, ACK mode.
- [Spring Integration Reference — Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): record to Message conversion.
- [Spring Kafka Reference — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html): KafkaHeaderMapper, Simple/Default implementations.
- [Spring Integration Reference — SFTP Remote File Information](https://docs.spring.io/spring-integration/reference/sftp/remote-file-info.html): FileHeaders.REMOTE_FILE/REMOTE_DIRECTORY/REMOTE_HOST_PORT.
- [Spring Integration Reference — TCP and UDP](https://docs.spring.io/spring-integration/reference/ip.html): source IP and connection metadata.
- [Spring Integration Reference — Header Enricher](https://docs.spring.io/spring-integration/reference/content-enrichment.html): enrichment EIP.
- [Spring Integration Reference — Header Filter](https://docs.spring.io/spring-integration/reference/header-filter.html): filter sensitive headers.

## Kết luận

**HeaderMapper cho inbound message** là chiến lược chuyển metadata của giao thức ngoài thành **Spring `MessageHeaders`**. Với `HeaderMapper<T>`, **`toHeaders(externalSource)` là chiều inbound**; `fromHeaders(...)` dùng chiều outbound hoặc reply. HTTP dùng `DefaultHttpHeaderMapper`, JMS dùng `DefaultJmsHeaderMapper`, AMQP dùng `DefaultAmqpHeaderMapper`; Kafka có header mappers riêng thuộc Spring Kafka. File/SFTP/IP thường có các protocol headers do adapter tự tạo và được chuẩn hóa bằng HeaderEnricher/Transformer sau đó.

Trong **SPRING_INTEGRATION_ADAPTERS**, làm đúng không phải “copy được càng nhiều header càng tốt”, mà là **allowlist, type/casing/multi-value validation, tách trusted và untrusted data, phân biệt message/correlation/business IDs, bảo vệ tenant/reply routing, test mapper và adapter thực tế, gắn error/ACK đúng stage, và giữ business ID ổn định khi retry**. **Header mapping thành công không đồng nghĩa nguồn đã xác thực, payload hợp lệ, broker đã ACK hay business operation đã commit.**










