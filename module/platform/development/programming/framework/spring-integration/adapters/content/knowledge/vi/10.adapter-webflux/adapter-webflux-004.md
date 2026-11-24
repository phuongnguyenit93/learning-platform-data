# WebFlux outbound gateway gọi reactive service

## 1. Bối cảnh: gọi dịch vụ HTTP và nhận kết quả trong IntegrationFlow

Một hệ thống quản lý đơn hàng cần hỏi dịch vụ vận chuyển về phí giao hàng trước khi xác nhận đơn. Dữ liệu có thể đến từ API nội bộ, Kafka, JMS, AMQP, file, SFTP hoặc cơ sở dữ liệu. Sau khi nhận `Message<Order>`, luồng tích hợp phải gửi HTTP request đến dịch vụ định giá, nhận kết quả và tiếp tục xử lý `shippingFee`.

**WebFlux outbound gateway** đáp ứng nhu cầu này. Nó nhận `Message<?>` từ Spring Integration, tạo HTTP request bằng Spring WebFlux `WebClient` và đưa HTTP response trở lại flow dưới dạng **reply message**. Đích HTTP có thể là một dịch vụ reactive trả `Mono<T>` cho một kết quả hoặc `Flux<T>` cho một dòng kết quả. Việc dịch vụ bên ngoài dùng Reactor không buộc mọi thành phần của ứng dụng gọi cũng phải dùng Reactor.

Đây là chủ đề thuộc chương **Adapter WebFlux** của module **SPRING_INTEGRATION_ADAPTERS**: module kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành hợp đồng message, xử lý lỗi và vòng đời kết nối với file, SFTP, HTTP, JMS, AMQP, Kafka hay database.

~~~mermaid
flowchart LR
    A["Service / Kafka / JMS / DB"] --> B["Message<QuoteRequest>"]
    B --> C["Request MessageChannel"]
    C --> D["WebFlux outbound gateway"]
    D -->|"HTTP POST JSON qua WebClient"| E["Reactive HTTP service"]
    E -->|"HTTP response: JSON"| D
    D --> F["Reply Message<QuoteResponse>"]
    F --> G["Transformer / Router / Service Activator"]
~~~

Gateway là điểm nối **request-reply**: kết quả HTTP trở thành dữ liệu để các bước tích hợp ra quyết định. Đây là khác biệt cơ bản với một chiều gửi thông báo không cần quan tâm payload phản hồi.

## 2. Phân biệt các loại WebFlux endpoint

| Thành phần | Điểm bắt đầu | Có đưa kết quả nghiệp vụ thành reply message? | Khi nào dùng |
|---|---|---|---|
| **WebFlux outbound gateway** | Message trong Spring Integration | **Có**, nhận response của HTTP server ngoài | Tra giá, tra trạng thái, lấy token hoặc metadata, gọi dịch vụ tính toán |
| **WebFlux outbound channel adapter** | Message trong Spring Integration | **Không**, nhánh gửi HTTP một chiều | Gửi sự kiện, đẩy webhook, thông báo tới đối tác |
| **WebFlux inbound gateway** | HTTP client gọi vào ứng dụng | **Có**, trả reply của flow thành HTTP response | Công bố REST API request-reply |
| **WebFlux inbound channel adapter** | HTTP client gọi vào ứng dụng | **Không**, đưa request thành message | Thu nhận webhook và công việc nền |
| **WebClient dùng trực tiếp** | Lời gọi Java, controller hoặc service | Kết quả là `Mono`/`Flux` của ứng dụng | Không cần message channel, router, transformer hay IntegrationFlow |

Hai từ **outbound** và **gateway** nói về hai khía cạnh khác nhau: *outbound* là hướng gọi ra hệ thống ngoài; *gateway* là hợp đồng đưa dữ liệu phản hồi trở lại luồng. Một outbound gateway có thể nằm giữa luồng tích hợp dài, chẳng hạn `JMS inbound → filter → outbound HTTP gateway → enrich → JDBC outbound`.

Không nên dùng outbound gateway chỉ để gửi “fire-and-forget” khi body phản hồi không phục vụ bước nào. Trường hợp đó, outbound channel adapter đơn giản hơn. Ngược lại, nếu cần lấy `trackingId`, mức giá hoặc HTTP metadata để quyết định nhánh xử lý, outbound gateway là lựa chọn phù hợp.

## 3. Hợp đồng request-reply với reactive service

Trong ví dụ xuyên suốt, dịch vụ `Shipping Quote Service` chạy riêng tại `localhost:9090`. Nó dùng WebFlux và trả một `Mono<QuoteResponse>`, nhưng đối với HTTP client, đó vẫn là một HTTP response JSON thông thường.

| Thuộc tính | Hợp đồng minh họa |
|---|---|
| URL | `POST http://localhost:9090/api/shipping/quote` |
| Request `Content-Type` | `application/json` |
| Request header | `X-Request-Id: req-001` |
| Request body | `{"orderId":"ORD-1001","weightKg":2}` |
| Success HTTP status | `200 OK` |
| Response `Content-Type` | `application/json` |
| Response body | `{"orderId":"ORD-1001","shippingFeeVnd":30000,"currency":"VND"}` |
| Reply trong IntegrationFlow | `Message<QuoteResponse>` |

Trong Java DSL, `expectedResponseType(QuoteResponse.class)` chỉ định loại object cần giải mã từ **response body**. Bản thân `expectedResponseType` không thực hiện validation nghiệp vụ, không biến status 4xx/5xx thành giá trị thành công và cũng không bảo đảm dịch vụ ngoài đã commit bất kỳ giao dịch nào. Phải định nghĩa rõ những điều này trong hợp đồng dịch vụ.

~~~mermaid
sequenceDiagram
    participant Producer as Nguồn message
    participant Gateway as WebFlux outbound gateway
    participant Client as WebClient
    participant Remote as Reactive Quote Service
    participant Next as Downstream handler
    Producer->>Gateway: Message<QuoteRequest>
    Gateway->>Client: Chuẩn bị URI, method, body, headers
    Client->>Remote: POST /api/shipping/quote
    Remote-->>Client: Mono hoàn tất -> HTTP 200 + JSON
    Client-->>Gateway: Decode body thành QuoteResponse
    Gateway->>Next: Reply Message<QuoteResponse>
    Next->>Next: Tính tổng tiền hoặc lưu kết quả
~~~

Lưu ý: `Mono` là **kiểu triển khai trong service reactive**, không xuất hiện nguyên trạng trên đường truyền HTTP. HTTP client nhìn thấy bytes của status, headers và body. Gateway quyết định giải mã body thành object thông thường hay publisher theo cấu hình.

## 4. Chuẩn bị dự án

Ví dụ dùng Java 17+ và Spring Boot quản lý dependency của Spring Framework/Spring Integration. Các API minh họa theo Spring Integration 6.x/7.x; cấu hình chi tiết cần đối chiếu với phiên bản cụ thể của dự án.

~~~groovy
// build.gradle - phần dependencies của ứng dụng gọi
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

`spring-integration-webflux` cung cấp `WebFluxRequestExecutingMessageHandler` và Java DSL `WebFlux.outboundGateway(...)`. `spring-boot-starter-webflux` cung cấp `WebClient`, Reactor và HTTP codecs thường dùng. **Ứng dụng chỉ gọi outbound HTTP không bắt buộc phải mở WebFlux inbound endpoint.**

Giữ cấu hình HTTP client ở một bean dùng chung: đây là nơi đặt TLS, authentication, proxy, connection pool, timeout và tracing. Tránh tự tạo một `WebClient`/connection pool cho từng message.

## 5. Ví dụ hoàn chỉnh: gửi QuoteRequest và nhận QuoteResponse

### 5.1. Khai báo DTO

Hai Java record mô tả hợp đồng request/reply. Để dùng record với JSON cần codec tương thích, thường có sẵn trong Spring Boot WebFlux starter.

~~~java
package com.example.shipping;

public record QuoteRequest(String orderId, int weightKg) {
}
~~~

~~~java
package com.example.shipping;

public record QuoteResponse(
        String orderId,
        long shippingFeeVnd,
        String currency) {
}
~~~

Trong một dự án thực, cần validation `orderId` và `weightKg`. Ví dụ này để đơn giản chỉ mô tả cấu trúc dữ liệu.

### 5.2. Cấu hình message channel và outbound gateway

~~~java
package com.example.shipping;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.messaging.MessageChannel;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class ShippingQuoteIntegration {

    @Bean
    public MessageChannel shippingQuoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public WebClient shippingWebClient(WebClient.Builder builder) {
        return builder.build();
    }

    @Bean
    public IntegrationFlow requestShippingQuote(WebClient shippingWebClient) {
        return IntegrationFlow.from("shippingQuoteRequests")
            .handle(WebFlux.outboundGateway(
                    "http://localhost:9090/api/shipping/quote",
                    shippingWebClient)
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(QuoteResponse.class)
                .mappedRequestHeaders(
                    HttpHeaders.CONTENT_TYPE,
                    "X-Request-Id"))
            .channel("shippingQuoteResults")
            .get();
    }

    @ServiceActivator(inputChannel = "shippingQuoteResults")
    public void receiveQuote(QuoteResponse response) {
        System.out.printf(
            "order=%s, fee=%d %s%n",
            response.orderId(),
            response.shippingFeeVnd(),
            response.currency());
    }
}
~~~

Mỗi cấu hình có một vai trò cụ thể:

1. `shippingQuoteRequests` nhận message yêu cầu từ các nguồn trong ứng dụng. `DirectChannel` giúp minh họa gửi và dispatch; nó không phải queue bền vững.
2. `shippingWebClient` là client gọi HTTP có thể tái sử dụng, được Spring Boot tạo builder để kế thừa cấu hình codecs/connector phù hợp.
3. `WebFlux.outboundGateway(url, webClient)` biến message thành HTTP request và tạo reply message từ response. Đây là lời gọi khác với `outboundChannelAdapter`.
4. `httpMethod(POST)` khai báo rõ method. Với GET/DELETE, cân nhắc `extractPayload(false)` nếu không muốn truyền body.
5. `expectedResponseType(QuoteResponse.class)` hướng dẫn codec đọc response JSON thành `QuoteResponse`.
6. `mappedRequestHeaders(...)` chỉ cho phép các headers cần thiết đi ra HTTP. Các headers nội bộ như `replyChannel`, `errorChannel` hoặc metadata không liên quan không nên đưa ra dịch vụ ngoài.
7. `channel("shippingQuoteResults")` định tuyến **reply** đến bước downstream. `receiveQuote` được gọi khi có reply phù hợp, có thể diễn ra bất đồng bộ so với nơi gửi message ban đầu.

**Cảnh báo về kỳ vọng thời điểm:** `shippingQuoteRequests.send(...)` thành công xác nhận việc **channel chấp nhận/dispatch message theo hợp đồng của channel**, không đồng nghĩa remote service đã trả response hay handler `receiveQuote` đã chạy. Với WebFlux, quá trình HTTP thường được xử lý bất đồng bộ.

### 5.3. Đưa message vào flow

~~~java
package com.example.shipping;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class QuotePublisher {

    private final MessageChannel requests;

    public QuotePublisher(
            @Qualifier("shippingQuoteRequests") MessageChannel requests) {
        this.requests = requests;
    }

    public boolean requestQuote(String orderId, int weightKg) {
        return requests.send(
            MessageBuilder.withPayload(new QuoteRequest(orderId, weightKg))
                .setHeader(HttpHeaders.CONTENT_TYPE,
                    MediaType.APPLICATION_JSON_VALUE)
                .setHeader("X-Request-Id", "req-" + orderId)
                .build());
    }
}
~~~

Từ một service hoặc listener nguồn, gọi:

~~~java
publisher.requestQuote("ORD-1001", 2);
~~~

Gateway gửi JSON đi, nhận HTTP response, giải mã thành `QuoteResponse` và định tuyến đến `shippingQuoteResults`. Nếu cần gọi cùng gateway cho nhiều loại event, hãy xác định routing, tên channel và contract để tránh biến mọi message thành request sai cấu trúc.

## 6. Mô phỏng reactive service ở phía đối tác

Tạo một **ứng dụng WebFlux riêng** chạy trên port `9090`. Định nghĩa DTO tương thích với hợp đồng JSON ở mục 5; có thể dùng cùng các record hoặc khai báo bản tương ứng trong ứng dụng mock.

~~~java
package com.example.mock;

import java.time.Duration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class ShippingQuoteController {

    public record QuoteRequest(String orderId, int weightKg) { }
    public record QuoteResponse(
        String orderId, long shippingFeeVnd, String currency) { }

    @PostMapping(
        path = "/api/shipping/quote",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<QuoteResponse> quote(@RequestBody Mono<QuoteRequest> body) {
        return body
            .filter(request -> request.orderId() != null
                    && !request.orderId().isBlank()
                    && request.weightKg() > 0)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid quote request")))
            .delayElement(Duration.ofMillis(150))
            .map(request -> new QuoteResponse(
                request.orderId(),
                request.weightKg() * 15_000L,
                "VND"));
    }
}
~~~

~~~yaml
# application.yml của ứng dụng mock - chạy riêng
server:
  port: 9090
~~~

Phép `delayElement` chỉ mô phỏng độ trễ bằng Reactor, **không chặn thread bằng `Thread.sleep`**. Với dữ liệu `weightKg=2`, API trả phí `30000 VND`. Test trực tiếp dịch vụ ngoài trước để phân biệt lỗi client với lỗi của gateway:

~~~bash
curl -i -X POST http://localhost:9090/api/shipping/quote \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ORD-1001","weightKg":2}'
~~~

HTTP response mong đợi khi request hợp lệ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"orderId":"ORD-1001","shippingFeeVnd":30000,"currency":"VND"}
~~~

Sau đó chạy ứng dụng Spring Integration và gọi `publisher.requestQuote("ORD-1001", 2)`. Log ở `receiveQuote` dự kiến:

~~~text
order=ORD-1001, fee=30000 VND
~~~

Không suy ra quan hệ thời gian cố định giữa kết quả trả về của `requestQuote` và log ở `receiveQuote`. Hành vi phụ thuộc kiểu channel, scheduler và quá trình xử lý bất đồng bộ.

## 7. Cơ chế reactive của WebFlux outbound gateway

`WebFluxRequestExecutingMessageHandler` dùng `WebClient` để tạo HTTP exchange. Đường xử lý nội bộ dựa trên `Mono<ClientResponse>` và chuyển kết quả thành reply message tương ứng. Khi **output channel là `ReactiveChannel`**, việc thực thi publisher có thể **được hoãn đến lúc downstream subscribe**. Với output channel thông thường, handler sử dụng mô hình phản hồi bất đồng bộ tích hợp vào messaging endpoint.

~~~mermaid
flowchart TD
    A["Inbound Message"] --> B["WebFlux outbound gateway"]
    B --> C{"Kiểu output channel?"}
    C -->|"ReactiveChannel"| D["Giữ publisher đến khi subscribe"]
    C -->|"Channel thông thường"| E["Cơ chế async reply của endpoint"]
    D --> F["Thực thi HTTP exchange"]
    E --> F
    F --> G["Decode HTTP response"]
    G --> H["Reply Message"]
~~~

Đây là một khác biệt quan trọng khi debug:

- Không có subscriber phù hợp ở nhánh reactive có thể khiến request chưa được thực thi dù đã tạo publisher; cần thiết kế luồng tiêu thụ rõ ràng.
- `Mono<T>` từ **dịch vụ ngoài** không mặc định được đưa vào flow dưới dạng `Mono<T>`. Với cấu hình `expectedResponseType(QuoteResponse.class)` thông thường, downstream nhận payload `QuoteResponse` sau khi body đã được giải mã.
- Việc sử dụng `DirectChannel` ở đầu vào không chứng minh toàn flow đồng bộ hay thread gọi `send()` chờ HTTP response. Đừng dùng `send()` làm biên nhận remote delivery.
- Reactive I/O có thể tiết kiệm thread khi chờ mạng, nhưng `JDBC` đồng bộ, xử lý CPU nặng, queue không giới hạn hoặc các lệnh `block()` vẫn có thể gây nghẽn.

**Giữ ngữ cảnh message:** reply được tạo từ HTTP response. Nếu phía sau còn bước cần tương quan với request ban đầu, dùng correlation ID/headers theo hợp đồng Spring Integration, đồng thời chỉ ánh xạ những header HTTP được phép. Một reply thiếu ngữ cảnh có thể khiến việc ghép kết quả vào đơn hàng ban đầu khó kiểm soát.

## 8. Nhận một đối tượng, nhận một Flux hay nhận toàn bộ ResponseEntity?

### 8.1. Response JSON một đối tượng

Đây là trường hợp của ví dụ chính:

~~~java
.handle(WebFlux.outboundGateway("http://localhost:9090/api/shipping/quote")
    .httpMethod(HttpMethod.POST)
    .expectedResponseType(QuoteResponse.class))
~~~

Khi HTTP response chứa JSON object phù hợp, reply payload là `QuoteResponse`. `replyPayloadToFlux` mặc định là `false`. Cách này thích hợp khi phải xử lý một giá trị duy nhất, chẳng hạn mức phí.

### 8.2. Response là dòng nhiều phần tử

Nếu reactive service phát một chuỗi cập nhật trạng thái, kết quả kiểm tra hàng loạt hoặc `text/event-stream`, gateway hỗ trợ:

~~~java
.handle(WebFlux.outboundGateway("http://localhost:9090/api/quotes/updates")
    .httpMethod(HttpMethod.GET)
    .expectedResponseType(QuoteUpdate.class)
    .replyPayloadToFlux(true))
~~~

**Ý nghĩa chính xác:** reply message mang **`Flux<QuoteUpdate>` làm payload**, không tự động biến thành nhiều `Message<QuoteUpdate>` riêng biệt. Để xử lý từng phần tử, cần downstream biết tiêu thụ `Publisher` hoặc dùng splitter/flow reactive phù hợp. Với streaming response, codec và `Accept` phải tương thích (ví dụ `text/event-stream` hoặc NDJSON); không bật `replyPayloadToFlux(true)` cho mọi API JSON đơn lẻ rồi coi đó là một stream vô hạn.

| Cấu hình | Payload reply điển hình | Kịch bản |
|---|---|---|
| `expectedResponseType(QuoteResponse.class)` | `QuoteResponse` | Một JSON object |
| `expectedResponseType(QuoteUpdate.class)` + `replyPayloadToFlux(true)` | `Flux<QuoteUpdate>` | Stream từng cập nhật |
| `extractResponseBody(false)` | `ResponseEntity<...>` | Cần status và response headers |
| `bodyExtractor(...)` | Theo giá trị trả về của `BodyExtractor` | Tùy biến cách đọc response ở mức thấp |

### 8.3. Cần đọc status và headers từ remote service

Từ Spring Integration 5.5, `extractResponseBody(false)` cho phép giữ **`ResponseEntity`** làm payload reply, cùng status và headers:

~~~java
.handle(WebFlux.outboundGateway("http://localhost:9090/api/shipping/quote")
    .httpMethod(HttpMethod.POST)
    .expectedResponseType(QuoteResponse.class)
    .extractResponseBody(false))
~~~

Lúc này downstream phải xử lý kiểu payload `ResponseEntity<QuoteResponse>` (hoặc dạng tương ứng với body thực nhận), **không** ép kiểu thẳng sang `QuoteResponse` như ví dụ mục 5. Nếu response không có body, handler có thể trả toàn bộ `ResponseEntity` dù `extractResponseBody` đang bật; cần kiểm tra các tình huống `204 No Content` và response rỗng.

Lưu ý rằng `extractResponseBody(false)` giúp quan sát metadata **trong những response được xử lý bình thường**; nó không mặc nhiên vô hiệu hóa việc HTTP client coi status lỗi là ngoại lệ. Chính sách xử lý 4xx/5xx cần được thiết kế và thử riêng.

### 8.4. Gửi request body dạng Publisher

Từ Spring Integration 5.2, handler hỗ trợ `Publisher`, `Resource` và `MultiValueMap` làm request payload. Với `Publisher<QuoteRequest>`, có thể định nghĩa loại phần tử để HTTP body inserter/codec hiểu đúng:

~~~java
.handle(WebFlux.outboundGateway("http://localhost:9090/api/bulk-quote")
    .httpMethod(HttpMethod.POST)
    .publisherElementType(QuoteRequest.class)
    .expectedResponseType(String.class))
~~~

Đoạn trên chỉ minh họa cấu hình; để thực sự stream request, message gửi đến gateway phải có payload dạng `Publisher<QuoteRequest>`, server đích phải hỗ trợ media type phù hợp và downstream phải tiêu thụ reply. Tránh tự ý gọi `block()` hay `subscribe()` ngoài ngữ cảnh lifecycle của IntegrationFlow.

## 9. HTTP method, URI, header mapping và xác thực

**Method và body.** Với `POST`, payload DTO thường được serialize thành JSON. Với `GET`, nên để dữ liệu tra cứu ở path/query parameters và không trông chờ request body; có thể sử dụng `extractPayload(false)` khi phù hợp. `Content-Type` mô tả body gửi đi; `Accept` mô tả format response mong muốn.

**URI động.** Gateway có overload URI function/expression cho từng message, chẳng hạn dùng partner ID để chọn host đã cấu hình. Đừng nối trực tiếp URL nhận từ header/JSON không tin cậy rồi cho `WebClient` truy cập: điều này có thể tạo lỗ hổng SSRF. Nên ánh xạ ID sang allowlist endpoint, cố định scheme/host/port hoặc qua routing service tin cậy.

**Header mapping.** Định nghĩa tập outbound HTTP headers cần thiết: `Content-Type`, `Accept`, `Authorization`, `X-Request-Id`, v.v. `mappedResponseHeaders(...)` có thể kiểm soát headers HTTP từ phản hồi được đưa vào message; không giả định mọi header bên ngoài đều đáng tin cậy hay được copy nguyên vẹn.

**Xác thực.** Đặt Bearer token, OAuth2 client hoặc mTLS trong cấu hình `WebClient`/filter phù hợp, dùng secret manager, định kỳ xoay vòng token. Không hardcode token vào tài liệu source và không forward `Authorization` của user sang hệ thống khác nếu chưa có hợp đồng delegation rõ ràng.

~~~java
// Chỉ là đoạn minh họa, accessToken lấy từ cấu hình bí mật an toàn.
WebClient client = builder
    .defaultHeaders(headers -> headers.setBearerAuth(accessToken))
    .build();
~~~

## 10. Timeout, lỗi HTTP, retry và giới hạn tải

| Giai đoạn | Lỗi thường gặp | Điều cần kiểm soát |
|---|---|---|
| Tạo request | URI sai, body không encode được | Validation payload, codec, URL và method |
| Kết nối/TLS | DNS thất bại, handshake lỗi, connection refused | Connect timeout, chứng chỉ, proxy, pool |
| Chờ response | Server chậm, client timeout | Response timeout và deadline tổng |
| HTTP 4xx | Request sai, hết quyền, `429` | Không retry mọi 4xx; xử lý riêng rate limit |
| HTTP 5xx | Dịch vụ ngoài lỗi, tạm thời unavailable | Retry có giới hạn + backoff/jitter |
| Decode response | Trả HTML thay JSON, schema thay đổi | Kiểm tra `Content-Type`, codec và hợp đồng phiên bản |
| Downstream | Reply không có consumer, queue đầy, xử lý lỗi | Error channel, kiểm soát channel và quan sát |

**Thứ tự timeout:** có thể có timeout kết nối, response timeout, timeout của endpoint/gateway, deadline workflow, timeout nguồn message và timeout của reverse proxy. Một giá trị `replyTimeout` ở Messaging Gateway hoặc handler không thay thế toàn bộ timeout mạng và nghiệp vụ. Hãy định nghĩa một deadline tổng rồi chia ngân sách cho các bước.

Cấu hình timeout phản hồi bằng Reactor Netty khi dùng connector này:

~~~java
import java.time.Duration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

HttpClient http = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(3));

WebClient webClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(http))
    .build();
~~~

Đoạn này thiết lập **response timeout**, không bao gồm mọi thời gian chờ kết nối, queue hoặc các lần retry. Trên production, cần cấu hình thêm connection pool, connect timeout, metrics và giới hạn concurrency.

### 10.1. Retry không được gây trùng nghiệp vụ

Một request POST có thể đã được remote service thực hiện dù client nhìn thấy timeout khi chờ response. Nếu gửi lại mù quáng, dịch vụ ngoài có thể tính phí hoặc tạo vận đơn hai lần.

Các nguyên tắc vận hành:

1. Gắn **idempotency key** cố định vào từng thao tác nghiệp vụ; request retry dùng lại cùng key.
2. Chỉ retry các trường hợp được phép theo hợp đồng, ví dụ lỗi mạng hoặc một số `429`/`5xx`; có giới hạn số lần, exponential backoff và jitter.
3. Có nơi lưu request chưa hoàn tất, dead-letter, cảnh báo và khả năng xử lý thủ công. Với yêu cầu không mất message khi ứng dụng restart, cần persistent outbox hoặc broker.
4. Không kết luận HTTP `200 OK` có nghĩa mọi tác vụ tiếp theo ở remote service đã commit; phải đọc chính xác hợp đồng API.
5. Khi nguồn là JMS/Kafka/DB poller, xác định **thời điểm ACK/commit nguồn** sau khi ghi nhận trạng thái gửi. ACK sớm có thể làm mất việc; retry muộn có thể gửi trùng.

### 10.2. Error channel và xử lý phản hồi thất bại

Trong flow phản ứng, lỗi xảy ra lúc thực thi publisher hoặc giải mã response có thể được truyền qua đường lỗi bất đồng bộ của endpoint, tùy loại channel, cấu hình `errorChannel` và advice. Không mặc định một lệnh `channel.send(...)` sẽ ném mọi lỗi HTTP. Nếu cần quyết định nghiệp vụ dựa trên 4xx/5xx, hãy cấu hình một đường xử lý lỗi rõ ràng và kiểm chứng thực tế; `extractResponseBody(false)` không tự biến lỗi thành reply thành công.

Với lỗi tạm thời, `retry` có thể đặt tại tầng client hoặc Spring Integration tùy mục tiêu; tránh kết hợp nhiều lớp retry mà không biết tổng số lần gửi lại. Với lỗi vĩnh viễn, nên chuyển sang kênh xử lý thất bại và lưu thông tin cần thiết để đối soát.

## 11. Thiết kế flow end-to-end

Hãy coi HTTP gateway là **một chặng** giữa nhiều hệ thống, không phải thay thế toàn bộ thiết kế tích hợp.

Ví dụ nghiệp vụ định giá từ nguồn Kafka:

~~~mermaid
flowchart TD
    A["Kafka inbound adapter"] --> B["Validate + map thành QuoteRequest"]
    B --> C["WebFlux outbound gateway"]
    C -->|"HTTP response QuoteResponse"| D["Enrich đơn hàng bằng phí vận chuyển"]
    D --> E["Persist / gửi sự kiện tiếp theo"]
    C -.->|"HTTP/network/decode error"| F["Retry policy / error flow"]
    F --> G["DLQ / outbox / cảnh báo"]
~~~

Các quyết định cần được làm rõ:

- **Định tuyến:** nếu nhiều đối tác, giữ endpoint, credential và response schema riêng hoặc có lớp adapter chuyển đổi sang contract chung.
- **Correlation:** một reply phải xác định được yêu cầu nguồn tương ứng bằng `requestId`/`orderId` và metadata đáng tin cậy.
- **Điều phối:** `DirectChannel`, `ExecutorChannel` và `FluxMessageChannel` có semantics khác nhau về đồng bộ, executor, subscription và backpressure.
- **Giới hạn tải:** cấu hình pool, timeout, rate limit, concurrency và độ dài queue thay vì chỉ dùng WebFlux rồi suy ra hệ thống chịu tải lớn.
- **Quan sát:** đo tỉ lệ success/error, HTTP latency, lỗi encode/decode, retry, số message tồn đọng và thời gian từ nguồn đến kết quả nghiệp vụ.
- **Shutdown:** đóng kết nối và dừng nhận công việc mới có kiểm soát; đừng coi một request chưa nhận response là đã thất bại chắc chắn tại server bên ngoài.

## 12. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Dịch vụ ngoài trả `Mono<T>` nên reply payload luôn là `Mono<T>`” | Với `expectedResponseType(T.class)`, gateway thường giải mã thành `T`; `Mono` là cách remote hoàn tất HTTP response |
| “WebFlux outbound gateway giống outbound channel adapter” | Gateway sinh reply message; adapter dùng cho nhánh một chiều |
| “`send() == true` chứng minh HTTP request đã xử lý xong” | `send` phản ánh hợp đồng của channel, không phải biên nhận remote |
| “Thêm `FluxMessageChannel` thì request tự chạy ngay” | Với output reactive, có thể cần downstream subscription để kích hoạt publisher |
| “`replyPayloadToFlux(true)` tự tạo nhiều reply messages” | Reply payload là một `Flux<T>`; phải thiết kế bước tiêu thụ hoặc split |
| “`extractResponseBody(false)` sẽ không bao giờ ném lỗi 4xx/5xx” | Tùy cơ chế xử lý status; giữ `ResponseEntity` không đồng nghĩa bỏ qua lỗi HTTP |
| “WebClient non-blocking nghĩa toàn flow non-blocking” | Handler, database, queue, scheduler và mã ứng dụng quyết định hành vi cuối cùng |
| “Retry một POST sau timeout luôn an toàn” | Remote có thể đã xử lý request; cần idempotency và đối soát |

## 13. Bài thực hành

1. Chạy mock reactive service ở `9090` rồi dùng `curl` kiểm tra HTTP `200` và JSON reply. Tiếp theo gửi message qua `QuotePublisher` và xác minh `shippingQuoteResults` nhận `QuoteResponse`.
2. Cho mock trả `weightKg=0` để tạo lỗi client `400`; quan sát đường lỗi và lý giải tại sao downstream không nên nhận payload `QuoteResponse` như thành công.
3. Đổi mock trả `204 No Content`; thử cấu hình `extractResponseBody(false)` và kiểm tra kiểu payload trong reply.
4. Tạo endpoint mock trả `Flux<QuoteUpdate>` dưới dạng SSE hoặc NDJSON; dùng `replyPayloadToFlux(true)` rồi thiết kế subscriber/splitter xử lý từng phần tử. So sánh với response JSON đơn lẻ.
5. Thêm độ trễ giả lập vượt quá response timeout; so sánh exception, thời gian hồi phục, số lần retry và tác động lên API.
6. Gửi cùng một `X-Request-Id` hai lần sau khi mô phỏng mất response; giải thích cách remote dùng idempotency key để ngăn tạo dữ liệu trùng.
7. Thay nguồn message bằng Kafka/JMS hoặc một poller DB; phân tích vị trí ACK/commit và xác định điều kiện nào cho phép message nguồn được đánh dấu hoàn tất.

**Câu hỏi vận dụng:** Một dịch vụ định giá trả `HTTP 200` cùng body `{"orderId":"ORD-1001","shippingFeeVnd":30000}`. Bước kế tiếp phải lưu giá và chỉ phát sự kiện `quote.calculated` sau khi database commit. Nếu mất kết nối sau khi remote đã trả body nhưng trước khi local commit, bạn sẽ đặt ranh giới retry, idempotency và ACK nguồn như thế nào?

## 14. Tài liệu tham khảo

- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): `WebFluxRequestExecutingMessageHandler`, Java DSL, reactive output channel, `expectedResponseType`, `replyPayloadToFlux` và `extractResponseBody`.
- [Spring Integration API — WebFlux Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFlux.html): các overload của `outboundGateway` và `outboundChannelAdapter`.
- [Spring Integration API — WebFluxMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFluxMessageHandlerSpec.html): `replyPayloadToFlux`, `publisherElementType`, `bodyExtractor` và cấu hình kế thừa.
- [Spring Integration Reference — HTTP Outbound Components](https://docs.spring.io/spring-integration/reference/http/outbound.html): request mapping, response, URI và header mapping.
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): cách WebClient gọi reactive HTTP services, xử lý response, codec và timeout.

> **Ghi nhớ:** `WebFlux.outboundGateway(...)` là điểm gọi HTTP **ra ngoài** trong Spring Integration và **trả kết quả HTTP về flow** dưới dạng reply message. Với reactive service, cần phân biệt `Mono`/`Flux` ở phía server, kiểu reply payload của gateway, thời điểm subscription và ranh giới xác nhận nghiệp vụ. Thiết kế tốt kết hợp đúng hợp đồng message với timeout, idempotency, xử lý lỗi và khả năng quan sát toàn luồng.
