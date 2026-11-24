# Ánh xạ request response trong Spring Integration WebFlux

## 1. Ánh xạ request/response nghĩa là gì?

Khi kết nối hai hệ thống qua HTTP, dữ liệu phải đi qua hai mô hình khác nhau: **HTTP request/response** và **Spring Integration `Message<?>`**. *Ánh xạ* (*mapping*) là quy tắc xác định phần nào của HTTP trở thành payload/header của message và phần nào của reply message trở thành HTTP status, headers, body. Nếu ánh xạ sai, các bước trong IntegrationFlow có thể nhận sai kiểu dữ liệu, mất correlation ID, trả status không đúng hoặc vô tình làm lộ thông tin nội bộ.

Bài học thuộc chương **Adapter WebFlux** của module **SPRING_INTEGRATION_ADAPTERS**. Phạm vi module là dùng inbound/outbound adapter, gateway, poller và `MessageChannel` để kết nối file, SFTP, HTTP, JMS, AMQP, Kafka hay cơ sở dữ liệu, đồng thời thực hành hợp đồng message, lỗi và vòng đời kết nối. Ở đây ta tập trung vào **ranh giới HTTP của Spring Integration WebFlux**: nhận HTTP từ bên ngoài và gọi HTTP sang hệ thống khác.

Ví dụ: một API nhận yêu cầu kiểm tra đơn hàng dạng JSON. Spring Integration WebFlux inbound gateway đọc request, chuyển thành `Message<OrderCheckRequest>`, gọi handler nội bộ và đưa `OrderCheckResponse` trở lại client dưới dạng JSON. Khi một flow cần hỏi API của đối tác, WebFlux outbound gateway thực hiện chiều ngược lại.

~~~mermaid
flowchart LR
    A["HTTP client"] -->|"request: method, path, headers, body"| B["WebFlux inbound gateway"]
    B -->|"Message<OrderCheckRequest>"| C["MessageChannel"]
    C --> D["Business handler"]
    D -->|"Reply Message<OrderCheckResponse>"| B
    B -->|"response: status, headers, body"| A
~~~

**Phân biệt hướng và hợp đồng:** *inbound* nghĩa là HTTP gọi **vào** ứng dụng; *outbound* nghĩa là flow gọi HTTP **ra ngoài**. *Channel adapter* chuyển dữ liệu chủ yếu theo một chiều, trong khi *gateway* có hợp đồng **request-reply**, đưa kết quả nghiệp vụ trở lại phía gọi.

## 2. Bốn thành phần WebFlux trong mô hình ánh xạ

| Thành phần Spring Integration | Request được ánh xạ thành gì? | Response dùng để làm gì? |
|---|---|---|
| **WebFlux inbound channel adapter** | HTTP request → Spring Integration message trên input channel | Gửi mã HTTP xác nhận tiếp nhận; không lấy reply nghiệp vụ từ flow |
| **WebFlux inbound gateway** | HTTP request → request message có ngữ cảnh reply | Reply message → HTTP status, response headers và body |
| **WebFlux outbound channel adapter** | Message nội bộ → HTTP request qua `WebClient` | Response dùng trong hợp đồng HTTP và xử lý lỗi; không phát reply nghiệp vụ cho flow |
| **WebFlux outbound gateway** | Message nội bộ → HTTP request qua `WebClient` | HTTP response → reply message cho downstream |

Hai gateway có ánh xạ request-reply nhưng khác phía khởi tạo HTTP exchange:

~~~mermaid
flowchart TB
    subgraph IN["Inbound gateway"]
        X["HTTP request ngoài"] --> Y["Message request"]
        Y --> Z["Message reply"]
        Z --> W["HTTP response ngoài"]
    end
    subgraph OUT["Outbound gateway"]
        A["Message request"] --> B["HTTP request ra ngoài"]
        B --> C["HTTP response từ đối tác"]
        C --> D["Message reply"]
    end
~~~

Trên thực tế, các adapter/gateway này chạy trên hạ tầng WebFlux với HTTP readers/writers và codec, nhưng một `DirectChannel`, `QueueChannel` hoặc service gọi JDBC đồng bộ trong cùng flow không tự biến thành non-blocking.

## 3. Bản đồ ánh xạ từ HTTP request vào Message

Một HTTP request có nhiều phần: URL/path, query parameters, method, headers, body và thông tin security context. Không phải phần nào cũng mặc nhiên trở thành một field trong DTO nghiệp vụ.

| HTTP request | Trong Spring Integration | Lưu ý |
|---|---|---|
| `POST /api/orders/check` | Endpoint được chọn bởi request mapping | Path/method phải khớp trước khi tạo message |
| `Content-Type: application/json` | Codec quyết định cách đọc request body | Sai media type có thể bị từ chối |
| JSON body `{"orderId":"ORD-1001"}` | Payload kiểu `OrderCheckRequest` khi cấu hình `requestPayloadType` | Decoder không thay thế kiểm tra dữ liệu nghiệp vụ |
| `X-Correlation-Id` | Message header nếu được header mapper cho phép | Không lấy ID không đáng tin làm bằng chứng xác thực |
| `?verbose=true` | Request parameters, có thể ánh xạ thành metadata/payload tùy endpoint | Không tự xuất hiện dưới dạng field của JSON DTO |
| Path variable `/orders/{orderId}` | Thông tin path variable có thể được expose qua request metadata/mapper | Cần chỉ rõ cách đưa vào payload khi nghiệp vụ cần |
| Header `Authorization` | Thuộc tầng xác thực; có thể có trong HTTP headers | Không tự chuyển token nhạy cảm sang mọi message/downstream |

Đối với inbound WebFlux, quá trình điển hình gồm:

1. **Route matching:** WebFlux tìm endpoint theo path và điều kiện method, `consumes`, `produces`, params/headers nếu có.
2. **Decode:** HTTP message reader/codec đọc body; `requestPayloadType` hướng dẫn loại payload cần chuyển đổi.
3. **Create Message:** Spring Integration tạo message với payload cùng metadata đã được ánh xạ.
4. **Dispatch:** Message được gửi vào `MessageChannel`; với gateway có thêm ngữ cảnh nhận reply.
5. **Reply:** downstream tạo reply, gateway serialize reply thành HTTP response theo quy tắc status/headers/body.

**Điểm dễ nhầm:** `requestPayloadType(OrderCheckRequest.class)` chỉ hướng dẫn **giải mã body**, không tự lấy `orderId` từ URL rồi điền vào DTO, cũng không bảo đảm field đó không rỗng. Các bước validation/biến đổi dữ liệu phải được thiết kế rõ.

## 4. Mapping endpoint: path, HTTP method, consumes, produces

Trong Spring Integration Java DSL, `WebFlux.inboundGateway(...)` hoặc `WebFlux.inboundChannelAdapter(...)` cung cấp inbound HTTP endpoint; `requestMapping(...)` khai báo các điều kiện chọn request.

Ví dụ phần cấu hình inbound gateway:

~~~java
WebFlux.inboundGateway("/api/orders/check")
    .requestMapping(mapping -> mapping
        .methods(HttpMethod.POST)
        .consumes(MediaType.APPLICATION_JSON_VALUE)
        .produces(MediaType.APPLICATION_JSON_VALUE))
    .requestPayloadType(OrderCheckRequest.class)
~~~

Ý nghĩa:

- **Path** cố định `/api/orders/check` là URL mà HTTP client gọi.
- **HTTP method** `POST` từ chối những method khác trên route này theo cơ chế WebFlux.
- **Consumes** `application/json` yêu cầu Content-Type của request phù hợp với mapping.
- **Produces** `application/json` biểu thị format response route có thể tạo; nó tham gia content negotiation với header `Accept` của client.
- **Request payload type** chọn Java type cho codec chuyển đổi HTTP body.

Một số kết quả lỗi ở tầng routing/codecs, khi không có xử lý ngoại lệ tùy chỉnh:

| Request của client | Kết quả thường gặp | Nguyên nhân |
|---|---|---|
| `GET /api/orders/check` | `405 Method Not Allowed` nếu path tồn tại nhưng method sai | Không khớp `POST` |
| `POST` với `Content-Type: text/plain` | `415 Unsupported Media Type` | Không khớp `consumes` |
| `POST` với `Accept: text/plain` | `406 Not Acceptable` trong trường hợp không thể tạo media type yêu cầu | Không khớp `produces`/codec |
| `POST` JSON hỏng cú pháp | Thường `400 Bad Request` | Codec đọc body thất bại |
| URL không được map | `404 Not Found` | Không có route |

Các mã trạng thái ở bảng là hành vi phổ biến của WebFlux khi không có custom error handling; thực tế còn phụ thuộc phiên bản, security filters, ngoại lệ và cấu hình ứng dụng. Không dùng chúng làm quy tắc tuyệt đối cho mọi dự án.

## 5. Payload: JSON, DTO, String và reactive Publisher

HTTP body không có sẵn Java type. Với JSON object, có thể ánh xạ sang Java record:

~~~java
public record OrderCheckRequest(String orderId) { }
public record OrderCheckResponse(String orderId, String status) { }
~~~

Với cấu hình `requestPayloadType(OrderCheckRequest.class)`, WebFlux codec đọc JSON thành payload `OrderCheckRequest`. Nếu cần text body, chọn `String.class`. Nếu nhận dữ liệu nhị phân, multipart hoặc stream, cần cấu hình reader/type phù hợp; không mặc định JSON codec sẽ xử lý mọi format.

**Hai hình dạng message khác nhau:**

~~~text
Message<OrderCheckRequest>
  payload: OrderCheckRequest(orderId="ORD-1001")

Message<Flux<OrderEvent>>
  payload: Flux<OrderEvent>    // một message chứa publisher
~~~

`Message<Flux<OrderEvent>>` không tương đương `Flux<Message<OrderEvent>>`. Trường hợp đầu downstream nhận một message có payload dạng publisher; nếu muốn xử lý mỗi event như một message riêng, phải có consumer/splitter phù hợp. Khi dùng request body streaming, có thể khai báo type `ResolvableType.forClassWithGenerics(Flux.class, OrderEvent.class)`, nhưng codec và HTTP media type của client phải hỗ trợ định dạng stream.

Ví dụ riêng cho streaming request:

~~~java
import org.springframework.core.ResolvableType;
import reactor.core.publisher.Flux;

// Mảnh cấu hình của một WebFlux inbound endpoint:
.requestPayloadType(
    ResolvableType.forClassWithGenerics(
        Flux.class, OrderEvent.class))
~~~

Đây là mảnh cấu hình, không phải flow Java hoàn chỉnh. Khi sử dụng `Flux`, phải xác định ai subscribe, xử lý lỗi và cancellation; nếu chỉ đưa `Flux` vào `QueueChannel`, queue không tự đọc từng phần tử của publisher.

## 6. Inbound gateway hoàn chỉnh: JSON request → JSON reply

### 6.1. Dependency

Với Spring Boot, dùng BOM của Boot để quản lý phiên bản Spring Integration và Spring Framework tương thích.

~~~groovy
// build.gradle — phần dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-webflux'
}
~~~

Trong Spring Boot dùng WebFlux auto-configuration, thường không cần tự thêm `@EnableWebFlux`. Nếu dự án đồng thời có Spring MVC và WebFlux, cần kiểm tra web application type được chọn.

### 6.2. Java DSL: ánh xạ rõ request và reply

Ví dụ dưới đây công bố `POST /api/orders/check`. Handler nhận request đã decode và trả DTO tương ứng; header `X-Correlation-Id` được giữ trong reply để có thể đưa ra HTTP response.

~~~java
package com.example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class OrderCheckHttpFlow {

    public record OrderCheckRequest(String orderId) { }
    public record OrderCheckResponse(String orderId, String status) { }

    @Bean
    public IntegrationFlow orderCheckInboundGateway() {
        return IntegrationFlow
            .from(WebFlux.inboundGateway("/api/orders/check")
                .requestMapping(mapping -> mapping
                    .methods(HttpMethod.POST)
                    .consumes(MediaType.APPLICATION_JSON_VALUE)
                    .produces(MediaType.APPLICATION_JSON_VALUE))
                .requestPayloadType(OrderCheckRequest.class)
                .mappedRequestHeaders(
                    HttpHeaders.CONTENT_TYPE, "X-Correlation-Id")
                .mappedResponseHeaders("X-Correlation-Id")
                .statusCodeFunction(message -> HttpStatus.OK)
                .replyTimeout(5_000))
            .handle((payload, headers) -> {
                OrderCheckRequest request = (OrderCheckRequest) payload;

                OrderCheckResponse response = new OrderCheckResponse(
                    request.orderId(), "PROCESSING");

                // Giữ ngữ cảnh replyChannel/correlation của gateway.
                return MessageBuilder.withPayload(response)
                    .copyHeaders(headers)
                    .build();
            })
            .get();
    }
}
~~~

**Đọc các chặng mapping:**

1. `inboundGateway` tạo endpoint request-reply, khác inbound channel adapter dùng để tiếp nhận một chiều.
2. `requestMapping` quyết định HTTP requests nào có thể vào flow.
3. `requestPayloadType` chọn codec và kiểu Java của payload.
4. `mappedRequestHeaders` chỉ ánh xạ những HTTP headers cần thiết vào message. Ví dụ giữ `Content-Type` và `X-Correlation-Id`.
5. `statusCodeFunction` chọn mã `200 OK` cho response **thành công** của ví dụ. Nó không tự biến mọi ngoại lệ thành `200`.
6. `mappedResponseHeaders` kiểm soát headers từ reply được phép đưa ra HTTP response.
7. `replyTimeout` giới hạn thời gian gateway chờ reply theo hợp đồng messaging. Đây không phải connection timeout của WebClient outbound.
8. `MessageBuilder.withPayload(...).copyHeaders(headers)` giữ context reply/correlation khi tự xây dựng một message mới. Không được sao chép toàn bộ headers từ nguồn **không tin cậy** vào HTTP response; việc xuất ra HTTP vẫn phải được giới hạn bằng header mapper.

**Vì sao phải giữ reply context?** Gateway đang chờ một reply gắn với HTTP request hiện tại. Nếu handler tự tạo một message mới và bỏ mất `replyChannel` cùng thông tin tương quan, gateway có thể không nhận được kết quả đúng hoặc chờ đến timeout. Nếu chỉ trả một DTO thông thường từ service activator, Spring Integration có cơ chế tạo reply message và giữ các header cần thiết; ví dụ tự tạo `Message` nhằm làm rõ trách nhiệm đó.

### 6.3. Gửi thử bằng curl

~~~bash
curl -i -X POST http://localhost:8080/api/orders/check \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'X-Correlation-Id: req-001' \
  -d '{"orderId":"ORD-1001"}'
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Correlation-Id: req-001

{"orderId":"ORD-1001","status":"PROCESSING"}
~~~

Header `X-Correlation-Id` xuất hiện khi nó được request mapper nhận và response mapper cho phép xuất. Byte-level HTTP response thực tế còn tùy HTTP protocol, codec, server và custom filters; ví dụ chỉ thể hiện hợp đồng quan trọng cho người học.

## 7. Response mapping: status, headers, body và reply channel

### 7.1. Status code

HTTP status phải thể hiện **kết quả theo hợp đồng API**:

| Trường hợp | Status phù hợp thường gặp | Ý nghĩa |
|---|---|---|
| Tra cứu thành công có body | `200 OK` | Có kết quả trả lại |
| Tạo tài nguyên thành công | `201 Created` | Tạo tài nguyên, thường có `Location` |
| Nhận yêu cầu để xử lý về sau | `202 Accepted` | Chấp nhận để xử lý; chưa chắc hoàn tất |
| Thành công và không trả body | `204 No Content` | Không có nội dung response |
| Request sai | `400 Bad Request` | Lỗi định dạng/dữ liệu phía client |
| Không tìm thấy tài nguyên | `404 Not Found` | Không tìm thấy theo hợp đồng |
| Xung đột trạng thái | `409 Conflict` | Xung đột với trạng thái tài nguyên |
| Remote service không sẵn sàng | `502` / `503` / `504` tùy vai trò server | Lỗi liên quan upstream/khả năng phục vụ |

`statusCodeFunction(...)`/`statusCodeExpression(...)` của inbound endpoint cho phép cấu hình status thành công hoặc theo ngữ cảnh message. Khi cần nhiều nhánh kết quả, nên thiết kế quy tắc status từ reply/error rõ ràng; không mặc định `statusCodeFunction(m -> HttpStatus.OK)` dùng được cho mọi lỗi.

### 7.2. Response body và Content-Type

Với inbound gateway, reply payload được HTTP writer/codec serialize thành body theo `Content-Type`/`produces` và content negotiation. DTO sẽ thường thành JSON nếu codec Jackson được cấu hình. Với reply dạng `Flux<T>` và `text/event-stream`, WebFlux có thể stream nhiều phần tử theo thời gian. Với `204 No Content`, response theo giao thức không có body.

Không nên tự chuyển DTO sang chuỗi JSON rồi lại để codec JSON serialize lần nữa: nếu gửi `String` chứa JSON dưới `application/json` sai cách, client có thể nhận chuỗi đã escape thay vì JSON object. Tốt hơn là trả DTO và để codec xử lý; nếu cần raw bytes/text, khai báo media type phù hợp.

### 7.3. Response headers

Header mapper có vai trò kiểm soát metadata đi ra HTTP. Ví dụ `X-Correlation-Id` để đối soát log, `Location` cho tạo tài nguyên, `Cache-Control` để điều khiển cache; chỉ xuất những headers đáp ứng hợp đồng. Không đưa `replyChannel`, `errorChannel`, access token hoặc chi tiết hạ tầng nội bộ vào response.

Nếu dùng proxy/API gateway, một số headers có thể được bổ sung/ghi đè ở hạ tầng phía trước. Các bước test nên kiểm tra **HTTP response cuối cùng** chứ không chỉ message headers trong flow.

## 8. Ánh xạ URI, path variable và query parameters

WebFlux phân biệt ba vùng dữ liệu:

~~~http
GET /api/orders/ORD-1001?includeHistory=true HTTP/1.1
Accept: application/json
X-Correlation-Id: req-002
~~~

- **Path variable** `ORD-1001` là một phần của URI route; có thể ánh xạ từ biến `{orderId}` theo request mapping.
- **Query parameter** `includeHistory=true` là cặp key/value ở URL, không phải JSON body.
- **Header** `X-Correlation-Id` là metadata được gửi riêng với URI.

Với REST controller thuần, các annotation `@PathVariable`, `@RequestParam`, `@RequestHeader` hỗ trợ binding trực tiếp vào method parameters. **WebFlux inbound gateway của Spring Integration không tự động chạy method parameter binding của một `@RestController`**: nó tạo Spring Integration message theo cấu hình endpoint. Muốn dùng path/query trong payload, cần lấy request metadata phù hợp với version/header mapper và transform thành DTO hoặc dùng biểu thức payload tương ứng.

Một số HTTP inbound endpoint hỗ trợ fallback sang request parameters dạng `MultiValueMap<String, String>` khi payload expression không lấy được body. Đây là hành vi cần xem xét theo cấu hình cụ thể; không giả định mọi request không có body đều được tự chuyển thành `OrderCheckRequest`. Với request GET, nên lập hợp đồng nguồn dữ liệu từ path/query rõ ràng và kiểm thử.

Ví dụ transformer ý tưởng:

~~~text
GET /api/orders/{orderId}?includeHistory=true
    -> request path/query metadata
    -> OrderLookupRequest(orderId, includeHistory)
    -> service activator
    -> OrderLookupReply
    -> HTTP JSON response
~~~

Trong bài tập, hãy quyết định **chính xác header hoặc payload source** được endpoint xuất ra trước khi dùng SpEL/transformer. Không tự suy tên header từ URL.

## 9. HeaderMapper: giữ đúng dữ liệu và bảo vệ ranh giới tin cậy

Spring Integration có cơ chế HTTP `HeaderMapper` để ánh xạ giữa HTTP headers và Spring Integration `MessageHeaders`. Những headers thường cần trong hợp đồng gồm:

| Header | Bên gửi | Ứng dụng trong flow |
|---|---|---|
| `Content-Type` | Client → inbound / outbound → remote | Giải mã và encode HTTP body |
| `Accept` | Client → server | Chọn response media type |
| `Authorization` | Client hoặc outbound HTTP client | Authentication; hạn chế sao chép qua boundary |
| `X-Correlation-Id` | Caller tạo hoặc proxy tin cậy | Log/tracing, đối soát request/reply |
| `Idempotency-Key` | Client theo hợp đồng | Khử trùng lặp tác vụ tạo/cập nhật |
| `Location` | HTTP server tạo tài nguyên | URI tài nguyên mới, thường với `201` |
| `Cache-Control` | Server → client | Chính sách cache response |

Không xem mọi header là dữ liệu đáng tin: client có thể tự tạo `X-User-Id` hoặc `X-Correlation-Id`. Header mapper giới hạn **headers được truyền**, còn authentication/authorization và xác thực chữ ký HMAC/mTLS phải được xử lý riêng.

### 9.1. Các loại header có cùng tên nhưng mục đích khác nhau

Phân biệt:

1. **HTTP headers**: metadata của HTTP exchange, ví dụ `Content-Type`.
2. **Spring Integration message headers**: metadata cho messaging, ví dụ `id`, `timestamp`, `replyChannel`, `errorChannel`.
3. **Business metadata**: ví dụ `orderId`, `tenantId`, `eventId`; nên có hợp đồng DTO hoặc header rõ ràng.

Không copy toàn bộ internal message headers ra HTTP request: có thể vô tình làm lộ thông tin hạ tầng hoặc gây va chạm với các header proxy/security. Tương tự, không để remote HTTP response ghi đè `replyChannel` hoặc thông tin điều phối nội bộ một cách không kiểm soát.

## 10. Outbound gateway: Message → HTTP request → Message reply

Với outbound gateway, chiều mapping đảo ngược: flow cung cấp payload/header để tạo request HTTP; remote service trả status/headers/body; gateway chuyển phản hồi thành message đi tiếp.

~~~mermaid
sequenceDiagram
    participant Source as Message producer
    participant Gateway as WebFlux outbound gateway
    participant Remote as Partner HTTP API
    participant Next as Downstream
    Source->>Gateway: Message<QuoteRequest> + headers
    Gateway->>Remote: POST JSON + mapped HTTP headers
    Remote-->>Gateway: HTTP 200 + JSON QuoteResponse
    Gateway->>Next: Message<QuoteResponse> + mapped response headers
~~~

### 10.1. Ví dụ Java DSL outbound request/response mapping

~~~java
package com.example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class PartnerQuoteOutboundFlow {

    public record QuoteRequest(String orderId, int weightKg) { }
    public record QuoteResponse(
        String orderId, long shippingFeeVnd, String currency) { }

    @Bean
    public WebClient partnerQuoteWebClient(WebClient.Builder builder) {
        return builder.build();
    }

    @Bean
    public IntegrationFlow partnerQuoteGateway(WebClient partnerQuoteWebClient) {
        return IntegrationFlow.from("quoteRequests")
            .handle(WebFlux.outboundGateway(
                    "http://localhost:9090/api/quote",
                    partnerQuoteWebClient)
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(QuoteResponse.class)
                .mappedRequestHeaders(
                    HttpHeaders.CONTENT_TYPE, "X-Correlation-Id")
                .mappedResponseHeaders("X-Partner-Request-Id"))
            .channel("quoteReplies")
            .get();
    }

    @ServiceActivator(inputChannel = "quoteReplies")
    public void handleQuote(QuoteResponse quote) {
        System.out.printf("Quote: %s -> %d %s%n",
            quote.orderId(), quote.shippingFeeVnd(), quote.currency());
    }
}
~~~

Khi gửi `Message<QuoteRequest>` có `Content-Type: application/json` vào `quoteRequests`, gateway gửi HTTP POST và dùng `expectedResponseType(QuoteResponse.class)` để giải mã response JSON. `mappedRequestHeaders`/`mappedResponseHeaders` quản lý danh sách headers HTTP đưa ra/nhận vào ở ranh giới. `quoteReplies` nhận reply payload kiểu `QuoteResponse` khi exchange thành công và codec tương thích.

Ở ví dụ này, channel `quoteRequests` được tạo theo cơ chế implicit channel của DSL khi tham chiếu tên; có thể khai báo bean channel tường minh nếu cần cấu hình executor, bounded capacity hoặc chính sách gửi riêng.

**Giới hạn:** `MessageChannel.send(...)` trả true không đảm bảo HTTP exchange đã hoàn tất, nhất là khi handler thực thi bất đồng bộ. Lỗi HTTP 4xx/5xx, network, timeout hay decode có thể xuất hiện ở đường lỗi; không mặc định downstream luôn nhận `QuoteResponse`.

### 10.2. Muốn lấy cả HTTP status và headers từ remote

Thông thường reply payload là **response body** đã decode. Khi downstream cần cả `statusCode`, headers và body, WebFlux outbound gateway hỗ trợ `extractResponseBody(false)`:

~~~java
.handle(WebFlux.outboundGateway("http://localhost:9090/api/quote")
    .httpMethod(HttpMethod.POST)
    .expectedResponseType(QuoteResponse.class)
    .extractResponseBody(false))
~~~

Đây là **mảnh DSL**; khi dùng, downstream cần dự kiến reply payload dạng `ResponseEntity<QuoteResponse>` (hoặc kiểu phù hợp body thực tế), thay vì ép kiểu trực tiếp sang `QuoteResponse` như ví dụ chính. Nếu response rỗng, cách tạo reply còn tùy cấu hình và loại response, nên test với `204 No Content`. Tùy chọn này cũng **không tự biến HTTP 4xx/5xx thành reply thành công**: phải xét cơ chế xử lý status/error của handler.

## 11. Mapping reactive response: Mono, Flux và SSE

Một reactive HTTP service có thể trả `Mono<T>`, nhưng HTTP client chỉ thấy HTTP response body sau khi `Mono` được subscribe và thực thi. Outbound gateway với `expectedResponseType(T.class)` thường tạo reply payload kiểu `T`, không mặc định đưa `Mono<T>` vào MessageChannel.

Khi remote trả stream (SSE hoặc NDJSON) và downstream cần tiêu thụ lần lượt, gateway có thể dùng `replyPayloadToFlux(true)`:

~~~java
.handle(WebFlux.outboundGateway(
        "http://localhost:9090/api/quote/updates")
    .httpMethod(HttpMethod.GET)
    .expectedResponseType(QuoteUpdate.class)
    .replyPayloadToFlux(true))
~~~

Lúc đó reply có payload `Flux<QuoteUpdate>`, tức là **một message mang publisher**. Nếu muốn mỗi cập nhật thành một Spring Integration message riêng, phải có consumer/splitter reactive thích hợp. `Flux` không tự biến thành hàng nghìn message chỉ vì flow dùng gateway.

Ở chiều inbound, WebFlux inbound gateway có thể lấy một `Flux<T>` làm reply payload và ghi ra HTTP response theo `text/event-stream`:

~~~java
import java.time.Duration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import reactor.core.publisher.Flux;

@Bean
public IntegrationFlow progressStream() {
    return IntegrationFlow
        .from(WebFlux.inboundGateway("/api/orders/progress")
            .requestMapping(m -> m.methods(HttpMethod.GET)
                .produces(MediaType.TEXT_EVENT_STREAM_VALUE)))
        .handle((payload, headers) -> Flux
            .just("RECEIVED", "PROCESSING", "COMPLETE")
            .delayElements(Duration.ofMillis(300)))
        .get();
}
~~~

Đây là phương án minh họa độc lập với flow POST ở mục 6. Test với `curl -N` để quan sát từng event; trong production cần tính heartbeat, ngắt kết nối, proxy buffering, giới hạn số subscriber và cancellation. Không giả định client ngắt SSE đồng nghĩa tác vụ đã gửi Kafka hoặc database tự rollback.

## 12. Validation và ánh xạ lỗi

### 12.1. Decode thành DTO không đủ để xác nhận dữ liệu hợp lệ

Ví dụ `OrderCheckRequest` có thể decode thành công từ `{"orderId":null}` nếu không có validation phù hợp. Vì vậy phải tách:

- **Kiểm tra cấu trúc:** JSON hợp lệ, kiểu trường phù hợp; thường do codec xử lý.
- **Validation dữ liệu:** `orderId` không rỗng, đúng độ dài, không chứa ký tự trái hợp đồng.
- **Authorization:** caller có quyền xem đơn hàng tương ứng.
- **Nghiệp vụ:** đơn hàng tồn tại, trạng thái cho phép thao tác, không bị xung đột.

Spring Integration WebFlux inbound endpoint có thể tích hợp `Validator`. Nếu dùng Bean Validation hoặc custom validator, cần cấu hình sao cho lỗi validation được ánh xạ thành HTTP status/body phù hợp. Với payload dạng publisher, xác định rõ việc validation xảy ra trên những phần tử nào và ở giai đoạn nào.

### 12.2. Bảng lựa chọn lỗi

| Lỗi | Nơi phát sinh | Xử lý gợi ý |
|---|---|---|
| Method/path/media type sai | WebFlux request mapping | HTTP 404/405/415/406 theo trường hợp |
| JSON body lỗi cú pháp | HTTP codec | HTTP 400 với thông báo an toàn |
| Thiếu `orderId` | Validation | HTTP 400 hoặc 422 theo hợp đồng API |
| Không tìm thấy đơn hàng | Business handler | HTTP 404 nếu hợp đồng quy định |
| Không đủ quyền | Security/authorization | HTTP 401/403 tùy ngữ cảnh |
| Reply không xuất hiện | Gateway reply timeout | Timeout/error flow; HTTP status do cấu hình quy định |
| Remote partner trả 5xx | Outbound gateway | Error flow, retry có giới hạn hoặc báo lỗi phù hợp |
| Codec không decode được response remote | WebClient/codec | Ghi nhận lỗi tích hợp, cảnh báo schema drift |

Không đồng nhất lỗi HTTP **tới ứng dụng** với lỗi khi ứng dụng **gọi ra remote**. Inbound gateway phải trả lỗi cho client của chính mình; outbound gateway cần phân loại lỗi của đối tác và đưa vào error handling của flow.

`replyTimeout` của inbound gateway giới hạn thời gian đợi reply messaging; nó không phải TCP connect timeout hay `responseTimeout` của WebClient outbound. Với luồng qua queue/poller hoặc broker, cần xem thời điểm gửi message, nhận reply, ACK và transaction boundary.

### 12.3. Một quy tắc điều phối lỗi có thể kiểm thử

~~~text
HTTP POST /api/orders/check
  ├─ không khớp mapping/media type -> WebFlux route/codec error
  ├─ JSON decode lỗi -> HTTP 400
  ├─ validation lỗi -> error mapping theo hợp đồng
  ├─ service thành công -> reply OrderCheckResponse -> HTTP 200 JSON
  ├─ không tìm thấy -> business error -> HTTP 404 (khi đã cấu hình)
  └─ không có reply -> timeout -> error flow/HTTP status đã định nghĩa
~~~

Đây là **mô hình thiết kế**; các status cho lỗi nghiệp vụ không tự có chỉ vì người học đặt tên exception. Cần error handler, advice hoặc mapping response tùy framework/version và test toàn đường đi.

## 13. Bảo mật và bảo toàn hợp đồng message

Khi ánh xạ HTTP vào Spring Integration, ranh giới tin cậy cần được kiểm soát:

1. **Xác thực nguồn:** áp dụng Spring Security, API key, OAuth2/JWT, HMAC signature hoặc mTLS theo hợp đồng. Không lấy một header `X-User-Id` do client gửi làm bằng chứng định danh.
2. **Chọn header mapper:** chỉ nhận/gửi những headers cần thiết. Không phơi bày `replyChannel`, `errorChannel` và các thông tin nội bộ trong HTTP response hay HTTP outbound.
3. **Chống dữ liệu quá lớn:** giới hạn HTTP body, codec buffer, số request đồng thời, timeouts, queue capacity và số phần tử trong stream.
4. **Correlation và idempotency:** giữ request ID từ thành phần đáng tin để trace; dùng idempotency key nếu tác vụ có khả năng bị retry và tạo side effects.
5. **URL outbound:** với URI động, chỉ chọn remote host từ danh sách được phép; đừng biến JSON payload thành URL tùy ý gây SSRF.
6. **Thông tin nhạy cảm:** không log nguyên `Authorization`, cookies, token, dữ liệu cá nhân hay toàn bộ request body không cần thiết.
7. **Content negotiation và CORS:** `produces/consumes` không thay thế CORS hay CSRF policies. CORS chỉ có ý nghĩa với trình duyệt; security phải kiểm soát đúng trường hợp sử dụng.

### 13.1. Reply headers và HTTP headers không tương đương một-một

Một business reply có thể gồm `Message<OrderCheckResponse>` và metadata theo Spring Integration. Khi viết HTTP response, chỉ headers được map và được server/runtime cho phép mới xuất hiện; một số headers như `Content-Length`, `Transfer-Encoding`, `Connection` do HTTP stack quản lý. Không nên cố ghi đè các transport headers từ message nghiệp vụ.

## 14. Kiểm thử hợp đồng request/response

### 14.1. Thử thủ công với curl

Sau khi chạy ứng dụng ở `localhost:8080`:

~~~bash
# Hợp lệ: nhận 200 và JSON phản hồi
curl -i -X POST http://localhost:8080/api/orders/check \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'X-Correlation-Id: req-003' \
  -d '{"orderId":"ORD-1001"}'

# Sai Content-Type: kiểm tra 415
curl -i -X POST http://localhost:8080/api/orders/check \
  -H 'Content-Type: text/plain' \
  -d 'ORD-1001'

# Sai JSON: kiểm tra cách codec xử lý lỗi
curl -i -X POST http://localhost:8080/api/orders/check \
  -H 'Content-Type: application/json' \
  -d '{"orderId":'
~~~

Trên PowerShell, có thể dùng `curl.exe` để chạy cú pháp curl kiểu command-line tương tự. Kết quả lỗi thực tế phụ thuộc mapping/security/error handler, vì vậy luôn kiểm tra cả **status** lẫn **body/content-type**.

### 14.2. Integration test bằng WebTestClient

Với `spring-boot-starter-test` (scope test), một test có thể kiểm tra thành công end-to-end:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderCheckHttpFlowTest {
    @Autowired
    WebTestClient webTestClient;

    @Test
    void mapsJsonRequestToJsonReply() {
        webTestClient.post()
            .uri("/api/orders/check")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .header("X-Correlation-Id", "req-004")
            .bodyValue(new OrderCheckHttpFlow.OrderCheckRequest("ORD-1001"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.orderId").isEqualTo("ORD-1001")
            .jsonPath("$.status").isEqualTo("PROCESSING");
    }
}
~~~

Đây là ví dụ test dựa trên ứng dụng Spring Boot có đầy đủ auto-configuration. Nó kiểm tra đường request → gateway → handler → HTTP response. Nếu có security, cấu hình test authentication thích hợp. Nếu flow thực sự gọi remote HTTP, nên dùng mock server để kiểm tra request method/headers/body và response mapping.

### 14.3. Ma trận kiểm thử tối thiểu

| Kiểm thử | Điều cần xác nhận |
|---|---|
| POST JSON hợp lệ | Body DTO đúng, HTTP 200 và response JSON |
| Sai method, path, Content-Type hoặc Accept | Route/media-type error phù hợp |
| JSON malformed hoặc field thiếu | Codec/validation báo lỗi an toàn |
| Header correlation hợp lệ | Được map qua message rồi xuất đúng theo chính sách |
| Header không nằm trong allowlist | Không bị đẩy ra ngoài trái ý muốn |
| Business handler lỗi hoặc không trả reply | HTTP status/error flow/timeout đúng cấu hình |
| Remote 4xx/5xx, network timeout | Không biến thành reply thành công; retry có điều kiện |
| SSE/Flux với client chậm | Không tạo buffer vô hạn, xử lý cancel/timeout |

## 15. Bài thực hành vận dụng

1. Chạy `OrderCheckHttpFlow`, gửi request có và không có `X-Correlation-Id`. Quan sát message headers và HTTP response headers, giải thích vì sao header mapper quan trọng.
2. Đổi `consumes` sang `application/xml` nhưng giữ JSON body. Quan sát route/codec từ chối request như thế nào và phân biệt `415` với `400`.
3. Thêm validation cho `orderId`, thử `null`, chuỗi rỗng và quá dài; thiết kế response lỗi có mã, thông điệp và correlation ID ổn định.
4. Sửa API thành `GET /api/orders/{orderId}`, yêu cầu thêm query `includeHistory=true`. Xác định chính xác bước chuyển path variable/query parameters thành DTO trong flow.
5. Thay handler trả một `Flux<OrderCheckResponse>` dạng SSE; dùng `curl -N` quan sát event, ngắt client giữa chừng và giải thích cancellation.
6. Viết thêm outbound gateway gọi mock partner API, map `X-Correlation-Id` vào request, nhận `QuoteResponse` rồi thử `extractResponseBody(false)` để lấy cả `ResponseEntity`.
7. Cho mock partner trả `404`, `429`, `503`, JSON sai schema và timeout. Thiết kế luồng xử lý lỗi, retry và quan sát cho từng trường hợp.
8. Đưa request vào `QueueChannel` trước bước xử lý lâu, đặt `replyTimeout` ngắn. Giải thích vì sao HTTP client có thể timeout dù message vẫn tiếp tục xử lý.
9. Tạo event có `Idempotency-Key` cố định và thử gửi lại. Xác định cách ngăn nghiệp vụ tạo kết quả hai lần khi HTTP response bị mất.
10. Kiểm tra security filters và các headers do proxy bổ sung; không tin tưởng headers nhận diện user từ client khi chưa được xác thực.

**Câu hỏi thiết kế:** ứng dụng nhận HTTP POST để tạo vận đơn, gọi remote shipping API và ghi DB. Nếu remote tạo vận đơn thành công nhưng phản hồi bị mất, client retry với cùng request ID. Hãy xác định cách ánh xạ HTTP status/body giữa các hệ thống, vị trí lưu idempotency key và điều kiện cho phép trả `201 Created` thay vì `202 Accepted`.

## 16. Tài liệu tham khảo

- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): inbound/outbound adapter, gateway, request mapping, payload type, reply reactive.
- [Spring Integration Reference — HTTP Support](https://docs.spring.io/spring-integration/reference/http.html): HTTP header mapper, URI variables, request/response semantics và timeout.
- [Spring Integration API — WebFluxInboundEndpointSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFluxInboundEndpointSpec.html): cấu hình inbound WebFlux endpoint, request mapping và mapping headers.
- [Spring Integration API — WebFluxMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFluxMessageHandlerSpec.html): outbound HTTP handler, response type và cách trích response body.
- [Spring Framework Reference — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): request mapping, path/query/header binding, validation và response handling.
- [Spring Framework Reference — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): các nguyên tắc xử lý reactive và HTTP body.

> **Ghi nhớ:** ánh xạ request/response là hợp đồng **HTTP ↔ Message**. Cần chỉ rõ route, media type, payload type, headers nào được map, reply đi qua channel nào và HTTP status/body được tạo ra sao. Với WebFlux inbound/outbound gateway, kiểm soát đúng ánh xạ giúp luồng tích hợp vừa trả dữ liệu chính xác vừa xử lý được validation, timeout, lỗi mạng và giới hạn bảo mật.
