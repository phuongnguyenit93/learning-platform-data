# Giới thiệu inbound gateway và outbound gateway của Spring Integration

## Mục tiêu bài học

Spring Integration dùng message channel để kết nối các thành phần trong ứng dụng. Khi một hệ thống bên ngoài cần gọi vào luồng xử lý nội bộ và nhận kết quả, ta dùng **inbound gateway**. Khi ứng dụng cần gửi request tới một hệ thống bên ngoài và chờ kết quả, ta dùng **outbound gateway**.

Với RSocket, Spring Integration cung cấp `RSocketInboundGateway` và `RSocketOutboundGateway`. Hai endpoint này nối RSocket request/reply với message flow của Spring Integration.

Sau bài này, bạn có thể:

- Phân biệt inbound gateway và outbound gateway theo hướng request.
- Phân biệt gateway với inbound/outbound channel adapter.
- Hiểu message, channel, request channel và reply channel.
- Cấu hình RSocket inbound gateway để nhận request từ client.
- Cấu hình RSocket outbound gateway để gọi một RSocket service khác.
- Chọn RSocket interaction model phù hợp với luồng xử lý.
- Quản lý kiểu payload, metadata, timeout và lỗi trong flow.
- Biết khi nào nên dùng gateway và khi nào chỉ cần một chiều.

## Gateway nằm ở đâu trong kiến trúc Spring Integration?

Spring Integration cung cấp mô hình message-driven để kết nối hệ thống. Một message thường có payload và headers. Message được gửi qua channel để chuyển từ endpoint này tới endpoint khác.

Gateway là biên giao tiếp request/reply giữa một hệ thống bên ngoài và message flow của ứng dụng. Nó chuyển request thành message nội bộ, rồi chuyển reply của flow trở lại bên gọi.

~~~mermaid
flowchart LR
    E[Hệ thống bên ngoài] <-->|Request / Reply| G[Gateway]
    G <-->|Message| C[Message Channel]
    C --> H[Service Activator / Transformer]
    H --> C
~~~

Với RSocket, message channel vẫn là cơ chế điều phối bên trong ứng dụng; RSocket là giao thức ở biên giao tiếp. Gateway kết hợp hai mô hình để hệ thống có thể xử lý request theo các bước độc lập, dễ thêm transformer, filter, router hoặc service activator.

## Inbound gateway và outbound gateway khác nhau thế nào?

Tên inbound/outbound được nhìn từ phía ứng dụng Spring Integration:

- **Inbound gateway:** request bắt đầu từ hệ thống bên ngoài và đi vào ứng dụng. Ứng dụng xử lý rồi trả reply về hệ thống gọi.
- **Outbound gateway:** request bắt đầu từ ứng dụng và được gửi tới hệ thống bên ngoài. Kết quả bên ngoài được đưa trở lại message flow.

~~~mermaid
flowchart TB
    subgraph Inbound["Inbound gateway"]
      A[Remote RSocket client] -->|Request| B[RSocketInboundGateway]
      B --> C[Request channel]
      C --> D[Internal integration flow]
      D --> E[Reply]
      E --> B
      B -->|Response| A
    end
    subgraph Outbound["Outbound gateway"]
      F[Internal integration flow] --> G[Request channel]
      G --> H[RSocketOutboundGateway]
      H -->|RSocket request| I[Remote RSocket service]
      I -->|Response| H
      H --> J[Reply channel]
      J --> K[Next internal handler]
    end
~~~

| Tiêu chí | Inbound gateway | Outbound gateway |
|---|---|---|
| Nơi khởi tạo request | Client/hệ thống bên ngoài | Ứng dụng Spring Integration |
| Hướng đi | Bên ngoài → ứng dụng | Ứng dụng → bên ngoài |
| Vai trò | Expose một flow nội bộ qua endpoint | Gọi dịch vụ ngoài từ flow nội bộ |
| Kết quả | Reply được gửi lại requester | Reply được đưa vào channel tiếp theo |
| RSocket component | `RSocketInboundGateway` | `RSocketOutboundGateway` |

Ví dụ:

- Một thiết bị gửi `inventory.lookup` qua RSocket. Inbound gateway nhận request, chuyển vào flow kiểm tra tồn kho và trả kết quả.
- Một flow xử lý đơn hàng cần hỏi service định giá từ xa. Outbound gateway gửi `pricing.quote` qua RSocket, nhận báo giá và đưa nó về flow xử lý đơn hàng.

## Gateway khác channel adapter như thế nào?

Gateway và channel adapter đều là integration endpoint, nhưng hợp đồng trao đổi khác nhau.

| Endpoint | Chiều giao tiếp | Có reply nghiệp vụ trong cùng tương tác? | Ví dụ |
|---|---|---|---|
| Inbound channel adapter | Hệ thống ngoài → ứng dụng | Không | Nhận telemetry một chiều |
| Outbound channel adapter | Ứng dụng → hệ thống ngoài | Không | Phát event một chiều |
| Inbound gateway | Hệ thống ngoài → ứng dụng | Có | Client hỏi trạng thái thiết bị và nhận kết quả |
| Outbound gateway | Ứng dụng → hệ thống ngoài | Có | Flow gọi service định giá và nhận quote |

Nếu không cần reply, channel adapter thường diễn đạt đúng mục đích hơn. Nếu bên gọi cần kết quả hoặc cần giữ request/reply correlation, gateway là lựa chọn phù hợp.

Trong Spring Integration, `RSocketInboundGateway` có thể nhận các interaction model khác nhau. Với fire-and-forget, nó gửi message vào flow một chiều. Với interaction có response, gateway liên kết reply của flow với response RSocket.

## Các thành phần trong một message flow

Một flow đơn giản có thể gồm:

- **Message:** payload cùng headers, ví dụ `InventoryRequest` và correlation ID.
- **MessageChannel:** đường truyền message giữa các endpoint.
- **Gateway:** điểm vào hoặc điểm gọi ra của hệ thống.
- **Transformer:** chuyển payload từ kiểu này sang kiểu khác.
- **Filter:** quyết định message có được đi tiếp hay không.
- **Router:** chọn channel đích theo nội dung hoặc header.
- **Service Activator:** gọi một method hoặc service nghiệp vụ.
- **Reply channel:** nơi nhận kết quả của một endpoint request/reply.

Một số channel thường gặp:

| Channel | Đặc điểm | Khi dùng |
|---|---|---|
| `DirectChannel` | Gọi subscriber trên luồng gửi; thường dùng để nối các bước trực tiếp | Flow đơn giản, xử lý đồng bộ |
| `ExecutorChannel` | Chuyển xử lý sang executor | Tách luồng xử lý, cần cấu hình executor |
| `QueueChannel` | Giữ message trong queue để consumer nhận sau | Buffer và tách producer/consumer |
| `FluxMessageChannel` | Channel reactive, hỗ trợ Publisher và demand | Luồng dữ liệu reactive, RSocket stream/channel |

Chọn channel theo yêu cầu concurrency và backpressure. Một `DirectChannel` không tự biến lời gọi blocking thành non-blocking. Nếu handler thực hiện I/O blocking, cần thiết kế scheduler hoặc executor phù hợp.

## Thêm Spring Integration RSocket dependency

Module RSocket của Spring Integration được cung cấp qua artifact `spring-integration-rsocket`.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-rsocket</artifactId>
</dependency>
~~~

Gradle:

~~~kotlin
implementation("org.springframework.integration:spring-integration-rsocket")
~~~

Để không tự khóa một phiên bản có thể xung đột với Spring Boot, hãy dùng dependency management của Spring Boot hoặc import Spring Integration BOM. Nếu quản lý phiên bản độc lập, phải chọn release Spring Integration tương thích với Spring Framework, Reactor và RSocket của ứng dụng.

Module này cung cấp các thành phần như:

- `ServerRSocketConnector`: mở RSocket server listener và đăng ký inbound endpoint.
- `ClientRSocketConnector`: quản lý kết nối/requester tới RSocket server.
- `RSocketInboundGateway`: chuyển RSocket request thành message flow.
- `RSocketOutboundGateway`: gửi request từ message flow tới RSocket peer.
- `RSocketStrategies`: codec và chiến lược chuyển đổi payload/metadata.

## Inbound gateway: nhận request từ RSocket client

Giả sử một service quản lý tồn kho cần expose route `inventory.lookup`. RSocket client gửi request tới route này. Ở phía Spring Integration, inbound gateway nhận request và chuyển payload vào flow nội bộ.

~~~mermaid
sequenceDiagram
    participant C as RSocket client
    participant G as RSocketInboundGateway
    participant Q as request channel
    participant S as Inventory service
    C->>G: REQUEST_RESPONSE route=inventory.lookup
    G->>Q: Message<InventoryRequest>
    Q->>S: Gọi nghiệp vụ
    S-->>Q: InventoryView
    Q-->>G: Reply message
    G-->>C: RSocket response
~~~

### Cấu hình connector phía server

Ví dụ mở một RSocket server listener:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.rsocket.ServerRSocketConnector;

@Configuration
class RSocketServerConfiguration {

    @Bean
    ServerRSocketConnector serverRSocketConnector() {
        return new ServerRSocketConnector("0.0.0.0", 7000);
    }
}
~~~

Connector quản lý RSocket server và tự phát hiện các inbound RSocket endpoint trong application context. Trong môi trường triển khai, chọn địa chỉ bind, port, TLS và security policy theo network topology. Ví dụ trên chỉ minh họa listener TCP cơ bản.

### Khai báo inbound gateway bằng Java DSL

Ví dụ flow xử lý một request-response:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.rsocket.RSocketInteractionModel;
import org.springframework.integration.rsocket.dsl.RSockets;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Bean
IntegrationFlow inventoryInboundFlow(InventoryService inventoryService) {
    return IntegrationFlow
        .from(RSockets.inboundGateway("/inventory.lookup")
            .interactionModels(RSocketInteractionModel.requestResponse))
        .<Flux<InventoryRequest>, Mono<InventoryView>>transform(requests ->
            requests.next()
                .flatMap(request -> inventoryService.find(request.sku()))
        )
        .get();
}
~~~

Ở đây:

- `RSockets.inboundGateway(...)` tạo endpoint nhận request theo path.
- `interactionModels(...)` giới hạn loại RSocket interaction được endpoint chấp nhận.
- Gateway chuyển request vào message flow. Payload đầu vào của RSocket Integration được biểu diễn dưới dạng reactive publisher.
- `transform(...)` lấy request đầu tiên, gọi service và tạo Mono reply.
- Reply được gateway gửi trở lại RSocket client.

RSocket inbound gateway hỗ trợ nhiều interaction model. Nếu không cấu hình giới hạn, endpoint có thể hỗ trợ các model mà implementation cho phép. Hãy chỉ bật loại interaction mà flow thực sự xử lý đúng.

### Cấu hình bằng bean RSocketInboundGateway

Có thể khai báo endpoint và channel tường minh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.rsocket.inbound.RSocketInboundGateway;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.DirectChannel;

@Bean
MessageChannel inventoryRequestChannel() {
    return new DirectChannel();
}

@Bean
RSocketInboundGateway inventoryInboundGateway() {
    RSocketInboundGateway gateway =
        new RSocketInboundGateway("/inventory.lookup");
    gateway.setRequestChannelName("inventoryRequestChannel");
    return gateway;
}
~~~

Một transformer hoặc service activator đăng ký trên channel sẽ xử lý message. Khi cần request/reply, downstream flow phải tạo reply đúng cách để gateway gửi lại requester. Cấu hình connector có thể tự phát hiện endpoint; cũng có thể gắn connector trực tiếp vào gateway để đăng ký tường minh.

### Payload và kiểu dữ liệu inbound

Inbound gateway nhận dữ liệu RSocket rồi dùng `RSocketStrategies` để decode payload. Có thể cấu hình request element type hoặc cung cấp strategies có decoder tương ứng.

Nếu không cấu hình kiểu đích, việc chuyển đổi mặc định phụ thuộc content type: dữ liệu text có thể được decode thành String; các nội dung khác thường được giữ ở dạng byte array. Với DTO nghiệp vụ, hãy đăng ký codec phù hợp và bảo đảm client gửi MIME type tương ứng.

Với publisher đầu vào, mỗi phần tử có thể được decode riêng. Tùy yêu cầu, `decodeFluxAsUnit` có thể thay đổi cách gateway xử lý toàn bộ Flux. Đừng giả định một stream nhiều phần tử luôn được gom thành một object duy nhất.

## Outbound gateway: gọi RSocket service từ message flow

Giả sử flow đơn hàng cần hỏi service định giá ở host `pricing-service`, port 7000, route `pricing.quote`. Outbound gateway lấy message từ request channel, gửi request qua RSocket và đưa response trở lại flow.

~~~mermaid
sequenceDiagram
    participant F as Order integration flow
    participant Q as pricingRequestChannel
    participant G as RSocketOutboundGateway
    participant R as Pricing RSocket service
    participant P as pricingReplyChannel
    F->>Q: Message<QuoteRequest>
    Q->>G: Request message
    G->>R: REQUEST_RESPONSE route=pricing.quote
    R-->>G: QuoteResponse
    G-->>P: Reply message
    P-->>F: Tiếp tục xử lý đơn hàng
~~~

### Cấu hình client connector

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.rsocket.ClientRSocketConnector;

@Configuration
class PricingRSocketClientConfiguration {

    @Bean
    ClientRSocketConnector pricingRSocketConnector() {
        return new ClientRSocketConnector("pricing-service", 7000);
    }
}
~~~

`ClientRSocketConnector` giữ requester được tạo từ RSocket connection tới service đích. Connector được tái sử dụng bởi outbound gateway thay vì tự mở một connection mới cho từng message.

### Khai báo outbound gateway bằng Java DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.rsocket.RSocketInteractionModel;
import org.springframework.integration.rsocket.ClientRSocketConnector;
import org.springframework.integration.rsocket.dsl.RSockets;

@Bean
IntegrationFlow pricingOutboundFlow(
        ClientRSocketConnector pricingRSocketConnector) {

    return IntegrationFlow
        .from("pricingRequestChannel")
        .handle(RSockets.outboundGateway("/pricing.quote")
            .interactionModel(RSocketInteractionModel.requestResponse)
            .expectedResponseType(QuoteResponse.class)
            .clientRSocketConnector(pricingRSocketConnector))
        .channel("pricingReplyChannel")
        .get();
}
~~~

Các phần cấu hình:

- Route `/pricing.quote` xác định endpoint trên remote RSocket service.
- `requestResponse` chọn interaction model một request, một response.
- `expectedResponseType(QuoteResponse.class)` chỉ định kiểu decode response.
- `clientRSocketConnector(...)` cung cấp kết nối tới peer.
- Reply được gửi tới channel tiếp theo của flow.

Nếu route thay đổi theo message, outbound gateway hỗ trợ route expression dựa trên payload hoặc headers. Chỉ dùng route động khi có hợp đồng rõ ràng và kiểm soát giá trị đầu vào; không để dữ liệu tùy ý của client quyết định route nội bộ mà không có authorization.

## Chọn RSocket interaction model cho gateway

Gateway là khái niệm request/reply ở mức tích hợp, nhưng RSocket có nhiều interaction model. Cần chọn kiểu phù hợp với dữ liệu đầu vào và phản hồi.

| RSocket model | Hành vi | Cách dùng với gateway |
|---|---|---|
| Request-response | Một request, tối đa một response | Phổ biến nhất cho gateway hỏi dịch vụ và nhận kết quả |
| Fire-and-forget | Một request, không có response nghiệp vụ | Inbound flow nhận thông điệp một chiều; outbound gateway không có kết quả nghiệp vụ |
| Request-stream | Một request mở ra nhiều response | Dùng khi flow cần nhận dữ liệu liên tục |
| Request-channel | Luồng request và luồng response hai chiều | Dùng khi cả hai bên trao đổi nhiều payload |

Outbound gateway mặc định dùng request-response. Khi chọn interaction model khác, hãy khai báo rõ để tránh hiểu nhầm hợp đồng.

Ví dụ outbound request-stream:

~~~java
.handle(RSockets.outboundGateway("/prices.watch")
    .interactionModel(RSocketInteractionModel.requestStream)
    .expectedResponseType(PriceTick.class)
    .clientRSocketConnector(marketDataConnector))
~~~

Với request-channel, payload message cần là Publisher và nên khai báo kiểu phần tử publisher để encoder chọn đúng codec. Gateway hỗ trợ `publisherElementType` hoặc expression tương ứng.

### Lưu ý về reply Flux của outbound gateway

`RSocketOutboundGateway` là asynchronous. Payload reply được bọc trong Mono để giữ request scope. Với request-stream hoặc request-channel, Flux response nằm bên trong Mono reply. Downstream cần tiêu thụ publisher đúng cách.

Nếu flow cần flatten response thành từng message, có thể dùng `FluxMessageChannel` và một service activator passthrough:

~~~java
@ServiceActivator(
    inputChannel = "rsocketReplyChannel",
    outputChannel = "fluxMessageChannel"
)
Flux<?> flattenResponse(Flux<?> payload) {
    return payload;
}
~~~

Không tự gọi `subscribe()` ở giữa flow nếu không quản lý rõ vòng đời. Hãy để channel và reactive pipeline điều phối demand, cancellation và lỗi.

## Khi nào gateway chỉ là một chiều?

Gateway thường được dùng cho request/reply. Tuy nhiên, RSocket inbound gateway cũng nhận fire-and-forget. Với model này, gateway gửi message vào output channel mà không chờ reply nghiệp vụ.

Outbound gateway cũng có thể cấu hình fire-and-forget. Khi đó không có response nghiệp vụ để đưa vào reply channel. Gateway vẫn trả một publisher biểu diễn hoàn tất/lỗi của thao tác gửi; nếu cần kích hoạt subscription và xử lý lỗi, cần cấu hình output channel phù hợp.

Nếu use case chỉ là phát telemetry hoặc notification, hãy cân nhắc channel adapter một chiều thay vì dùng gateway chỉ để bỏ qua reply.

## Metadata và headers trong gateway

RSocket metadata có thể mang route, authentication, correlation ID hoặc context riêng của ứng dụng. Spring Integration outbound gateway hỗ trợ metadata expression được đánh giá từ request message. Expression phải trả về Map ánh xạ metadata value tới MIME type.

Ví dụ về ý tưởng:

~~~java
import java.util.Map;

import org.springframework.util.MimeType;

.handle(RSockets.outboundGateway("/orders.create")
    .interactionModel(RSocketInteractionModel.requestResponse)
    .expectedResponseType(OrderReceipt.class)
    .metadata(message -> Map.of(
        message.getHeaders().get("correlationId"),
        MimeType.valueOf("text/plain")
    ))
    .clientRSocketConnector(orderConnector))
~~~

Đây là phác thảo cấu hình metadata; hãy dùng MIME type và kiểu dữ liệu phù hợp với decoder của peer. Không nhầm Spring message headers với RSocket metadata tự động được truyền đi. Chỉ metadata được cấu hình/encode theo hợp đồng mới tới remote peer.

Với inbound gateway, metadata có thể được trích xuất thành message headers tùy theo `RSocketStrategies` và metadata extractor. Flow có thể dùng correlation ID để ghi log hoặc liên kết reply, nhưng không dùng header do client gửi làm bằng chứng xác thực.

## Xử lý lỗi, timeout và reply

Gateway tạo ranh giới request/reply, do đó cần quy định rõ điều gì xảy ra khi flow hoặc remote peer không trả lời.

Các nhóm lỗi thường gặp:

- **Connection error:** không thể mở hoặc giữ RSocket connection.
- **Setup error:** hai phía không thống nhất được session, MIME type hoặc cấu hình bảo mật.
- **Route error:** remote peer không có route tương ứng.
- **Decode error:** payload hoặc metadata không khớp codec.
- **Handler error:** service nội bộ hoặc service từ xa phát lỗi.
- **Timeout:** request không có reply trong thời gian cho phép.
- **Cancellation:** bên gọi không còn chờ kết quả và hủy tương tác.

Hãy cấu hình timeout theo SLA nghiệp vụ. Timeout không chứng minh remote service chưa xử lý request; nếu response bị mất sau khi transaction commit, kết quả có thể không xác định. Với thao tác có tác dụng phụ, dùng command ID/idempotency key và API truy vấn trạng thái.

Spring Integration hỗ trợ error channel để định tuyến lỗi của flow. Inbound gateway có thể cấu hình timeout/reply timeout và `errorOnTimeout` để phát `MessageTimeoutException` khi downstream không trả reply theo cấu hình. Hãy xác định lỗi nào được chuyển thành response nghiệp vụ, lỗi nào kết thúc RSocket interaction và lỗi nào cần retry.

## Gateway không thay thế bảo mật

RSocket gateway mở một đường vào hoặc gọi ra hệ thống khác. Nó không tự cấp authorization cho mọi route.

Các nguyên tắc:

- Xác thực peer hoặc requester bằng TLS/mTLS, RSocket authentication hoặc cơ chế phù hợp.
- Phân quyền route theo danh tính và nghiệp vụ.
- Kiểm tra metadata trước khi đưa vào flow.
- Không tin correlation ID, tenant ID hoặc user ID chỉ vì chúng nằm trong message header.
- Không ghi token hoặc dữ liệu nhạy cảm vào log.
- Giới hạn payload, concurrency và thời gian xử lý.
- Kiểm tra route động trước khi gọi service đích.

Với outbound gateway, endpoint và route đích cũng là ranh giới tin cậy. Không cho phép message không tin cậy tự chọn host/port hoặc RSocket connector.

## Kiểm thử inbound và outbound gateway

Kiểm thử nên bao gồm cả transport và message flow.

**Inbound gateway:**

1. Khởi động server connector.
2. Kết nối một RSocket client.
3. Gửi request tới path đã đăng ký.
4. Xác nhận message vào đúng request channel.
5. Xác nhận transformer/service activator xử lý payload.
6. Xác nhận reply trở lại client.
7. Kiểm tra route không tồn tại, handler lỗi, timeout và payload sai MIME type.

**Outbound gateway:**

1. Khởi động một RSocket peer giả hoặc test server.
2. Gửi message vào request channel.
3. Xác nhận gateway gọi đúng route.
4. Xác nhận payload và metadata được encode đúng.
5. Xác nhận response được đưa vào reply channel.
6. Kiểm tra connection error, route error, timeout và response decode lỗi.
7. Kiểm tra stream/channel có demand và cancellation đúng.

Không chỉ kiểm tra method service bằng unit test. Integration test qua connector và RSocket transport mới xác nhận được route, codec, metadata và request/reply correlation.

## Chọn gateway phù hợp

| Câu hỏi | Lựa chọn |
|---|---|
| Một RSocket client gọi vào ứng dụng và cần kết quả? | RSocket inbound gateway |
| Ứng dụng cần gọi RSocket service và nhận kết quả? | RSocket outbound gateway |
| Chỉ nhận event RSocket một chiều, không reply? | RSocket inbound gateway với `fireAndForget` |
| Chỉ gửi notification RSocket một chiều? | RSocket outbound gateway với `fireAndForget` |
| Cần nhiều response từ một request? | Gateway với request-stream |
| Cần hai luồng payload cùng tương tác? | Gateway với request-channel |
| Cần gọi một flow nội bộ từ Java interface? | Spring Integration messaging gateway, không phải RSocket gateway |

Đừng nhầm **messaging gateway** với **RSocket inbound/outbound gateway**. Messaging gateway thường là interface Java giúp code ứng dụng gọi một message flow nội bộ. RSocket gateway là endpoint tích hợp giao thức RSocket với message flow.

## Checklist triển khai

Trước khi đưa gateway vào ứng dụng, hãy trả lời:

1. Request bắt đầu từ hệ thống ngoài hay từ flow nội bộ?
2. Có cần reply nghiệp vụ hay chỉ cần gửi một chiều?
3. Inbound path hoặc outbound route đã thống nhất giữa hai peer chưa?
4. Connector server/client được cấu hình và quản lý vòng đời chưa?
5. Request/reply channel có đúng tên và đúng kiểu payload không?
6. Interaction model có khớp cardinality của Publisher và response không?
7. Codec, MIME type và metadata extractor có tương thích không?
8. Timeout, error channel và cancellation đã có chính sách chưa?
9. Gateway có giới hạn concurrency và payload size không?
10. Authentication và authorization đã được áp dụng ở route tương ứng chưa?
11. Integration test đã kiểm tra transport, route, codec và reply chưa?
12. Nếu response timeout sau khi remote đã commit, hệ thống có idempotency hoặc query status không?

Inbound gateway đưa request từ RSocket vào message flow và gửi reply trở lại peer. Outbound gateway nhận message nội bộ, gọi route RSocket từ xa và đưa response về flow. Khi phân biệt đúng hướng giao tiếp, chọn interaction model phù hợp và quản lý channel, codec, timeout cùng security, Spring Integration giúp kết nối các hệ thống RSocket mà vẫn giữ được cấu trúc xử lý message rõ ràng.

## Tài liệu tham khảo

- [Spring Integration Reference: Integration Endpoints](https://docs.spring.io/spring-integration/reference/endpoint-summary.html)
- [Spring Integration Reference: RSocket Support](https://docs.spring.io/spring-integration/reference/rsocket.html)
- [Spring Integration API: RSockets Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/rsocket/dsl/RSockets.html)
- [Spring Integration API: RSocketInboundGateway](https://docs.spring.io/spring-integration/api/org/springframework/integration/rsocket/inbound/RSocketInboundGateway.html)
- [Spring Integration API: RSocketOutboundGateway](https://docs.spring.io/spring-integration/api/org/springframework/integration/rsocket/outbound/RSocketOutboundGateway.html)

