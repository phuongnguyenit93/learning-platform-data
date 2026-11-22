# RSocket adapter hoặc gateway và hạ tầng Spring Boot hỗ trợ

Một hệ thống đặt hàng có thể dùng HTTP để nhận yêu cầu từ trình duyệt, JDBC để lưu đơn hàng, RabbitMQ để phân phối sự kiện, và **RSocket** để truy vấn hoặc nhận luồng dữ liệu liên tục từ một dịch vụ nội bộ. Khi các bước này được nối bằng **Spring Integration**, RSocket trở thành một *integration endpoint*: chuyển lời gọi RSocket thành Spring `Message<?>` để đưa vào integration flow, hoặc lấy một Spring Message từ flow rồi gọi dịch vụ RSocket phía ngoài.

Bài học thuộc chương **Adapter tích hợp** của module **SPRING_BOOT_INTEGRATION**. Module tập trung tổ chức tích hợp hệ thống Spring Boot qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và adapter của Spring Integration, đặc biệt là cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát luồng nghiệp vụ. Trong bối cảnh đó, cần phân biệt chính xác **RSocket adapter/gateway của Spring Integration** với **hạ tầng RSocket của Spring Messaging và Spring Boot**, và biết trách nhiệm nào còn phải tự triển khai.

Bài viết minh họa các API có trong **Spring Boot 3.x, Spring Framework 6.x và Spring Integration 6.x**. Những bản Spring Boot mới hơn có thể quản lý phiên bản Spring Integration khác; hãy dùng BOM/dependency management phù hợp và đối chiếu API của phiên bản dự án. Các ví dụ Java được trình bày như các mảnh ghép cấu hình cho từng ứng dụng server/client, không có nghĩa mọi bean đều phải khai báo cùng một nơi.

## 1. RSocket, Spring Messaging và Spring Integration giữ vai trò nào?

RSocket là giao thức nhị phân có hỗ trợ tương tác hai chiều trên một kết nối như TCP hoặc WebSocket. Nó không bị giới hạn vào request/response mà có bốn interaction model:

| Interaction model | Dữ liệu yêu cầu | Dữ liệu phản hồi | Trường hợp sử dụng |
| --- | --- | --- | --- |
| `requestResponse` | Một payload | Một phản hồi hoặc lỗi | Kiểm tra tồn kho, lấy thông tin phí |
| `fireAndForget` | Một payload | Không có kết quả nghiệp vụ | Gửi tín hiệu chấp nhận mất hoặc được xác nhận ở tầng khác |
| `requestStream` | Một payload | Nhiều phần tử phản hồi | Theo dõi thay đổi đơn hàng theo thời gian |
| `requestChannel` | Một stream payload | Một stream phản hồi | Đồng bộ trạng thái hai chiều, tương tác phiên |

**Spring Messaging** cung cấp `RSocketRequester`, `RSocketMessageHandler`, `@MessageMapping` và `RSocketStrategies`. Một `@Controller` có thể nhận request RSocket và trả `Mono` hoặc `Flux` mà không cần Spring Integration.

**Spring Integration** thêm mô hình *MessageChannel → filter/transformer/router/service activator → MessageChannel*, thuận tiện khi RSocket chỉ là một chặng trong workflow có HTTP, SQL, cache, broker hoặc hệ thống bên ngoài.

**Spring Boot** hỗ trợ phụ thuộc, bean, codec, cấu hình server/client và tự động hóa có điều kiện. Nó không tự thiết kế business contract, idempotency, timeout, retry, giao dịch database hay cơ chế lưu trữ message bền vững.

~~~mermaid
flowchart LR
    A["RSocket client"] --> B["RSocket transport / SETUP"]
    B --> C["Spring Messaging: RSocketStrategies"]
    C --> D["Spring Integration RSocketInboundGateway"]
    D --> E["MessageChannel"]
    E --> F["filter → transformer → service"]
    F --> G["SQL / cache / HTTP / broker"]
    F --> H["Phản hồi RSocket"]
~~~

Các thành phần chỉ tham gia vào luồng theo cấu hình cụ thể. Không phải request nào cũng gọi database hoặc broker.

### Vì sao tên “adapter” đôi khi gây nhầm?

Spring Integration gọi chung các thành phần kết nối giao thức là *channel adapter/endpoint*, nhưng bảng endpoint chính thức phân loại RSocket hiện có **`RSocketInboundGateway`** và **`RSocketOutboundGateway`**. Chúng có thể xử lý cả trường hợp không có phản hồi như `fireAndForget`, tuy nhiên không nên tự suy ra tồn tại các lớp `RSocketInboundChannelAdapter` và `RSocketOutboundChannelAdapter` tương ứng với JMS/AMQP. Hãy chọn đúng class và kiểu tương tác được thư viện công bố.

## 2. Inbound và outbound được xác định theo hướng của integration flow

Tên *inbound/outbound* mô tả **hướng so với ứng dụng Spring Integration**, không nhất thiết mô tả máy nào mở TCP connection.

- **Inbound gateway**: có một yêu cầu RSocket đi **vào** Spring Integration; gateway giải mã payload, tạo Spring Message và đưa vào request channel. Với interaction cần phản hồi, nó chuyển reply từ flow trở lại client RSocket.
- **Outbound gateway**: có Spring Message **đi ra** một endpoint RSocket khác; gateway chọn route, model, metadata và mong đợi response rồi chuyển kết quả về integration flow.

~~~mermaid
flowchart TD
    subgraph Provider["inventory-service"]
       IN["RSocketInboundGateway('inventory.stock')"] --> MC["stockReadChannel"]
       MC --> S["InventoryLookupService"]
    end

    subgraph Caller["checkout-service"]
       APP["Checkout flow"] --> OUT["RSocketOutboundGateway('inventory.stock')"]
    end

    OUT -->|"RSocket request-response"| IN
    S -->|"Mono response"| OUT
    OUT -->|"reply channel"| APP
~~~

Khi hai service giao tiếp qua RSocket, chúng có thể đồng thời đóng vai trò server và client trên hai chiều, vì giao thức có tính *symmetric*. `ServerRSocketConnector` có thể giữ registry những client đang kết nối để server gửi yêu cầu ngược lại, còn `ClientRSocketConnector` cũng có khả năng xử lý yêu cầu đến qua kết nối đã thiết lập nếu endpoint được đăng ký phù hợp.

Điều này không biến RSocket thành queue: các message gửi trên kết nối sống không có mặc định *broker persistence*, DLQ, history hay consumer offset.

## 3. Chọn phương án triển khai trước khi khai báo bean

Có ba cách phổ biến:

| Phương án | Thành phần chính | Dùng khi nào |
| --- | --- | --- |
| **Spring Messaging thuần** | `@Controller`, `@MessageMapping`, `RSocketRequester` | Một số route RPC/stream đơn giản, không cần EIP flow |
| **Spring Integration RSocket gateway** | `RSocketInboundGateway`, `RSocketOutboundGateway`, `ClientRSocketConnector` | Có workflow nhiều adapter, transformer, filter, route, error channel |
| **Tự tạo rsocket-java server/client** | `RSocketServer`, `RSocketConnector`, codec/handler tự cấu hình | Tích hợp cấp thấp hoặc yêu cầu vận chuyển không có trong các abstraction trên |

Một ứng dụng có thể trộn Spring Messaging `@MessageMapping` với Spring Integration gateway, nhưng phải có **một cơ chế đăng ký route/server nhất quán**. Đừng vô tình mở hai RSocket server cùng port, hoặc dùng hai message handler độc lập với cùng một route rồi kỳ vọng Boot tự chọn đúng.

Khi vấn đề chỉ là gọi một RPC nội bộ, `RSocketRequester` trực tiếp có thể dễ bảo trì. Gateway thể hiện giá trị khi cần lắp ghép RSocket vào **một chuỗi xử lý Spring Integration**, đặc biệt trong hệ thống đã sử dụng `IntegrationFlow`, header, transformer, router và channel.

## 4. Dependency và những gì Spring Boot cấu hình giúp

Với Maven, ứng dụng dùng cả Spring Boot RSocket và Spring Integration có thể khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-rsocket</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-rsocket</artifactId>
    </dependency>
</dependencies>
~~~

Trong dự án dùng Spring Boot dependency management phù hợp, phiên bản Spring Integration thường được BOM quản lý. Không tự ghép ngẫu nhiên `spring-integration-rsocket` từ major mới với Boot/Framework major cũ. Nếu dự án dùng BOM riêng, phải kiểm tra compatibility và dependency tree của Reactor, rsocket-java, spring-messaging và các codec.

### Auto-configuration cơ bản

Spring Boot có thể cung cấp:

- `RSocketStrategies` cho mã hóa/giải mã payload, với codec như CBOR/JSON khi dependency phù hợp. Có thể bổ sung bằng `RSocketStrategiesCustomizer`.
- `RSocketMessageHandler` và hỗ trợ `@MessageMapping` của Spring Messaging.
- Server RSocket TCP/WebSocket khi cấu hình thuộc tính server và có dependency thích hợp.
- `RSocketRequester.Builder` cho ứng dụng gọi RSocket theo Spring Messaging.
- **Khi có `spring-integration-rsocket`**, hạ tầng Spring Integration RSocket có thể dùng server được Boot quản lý và tạo `ClientRSocketConnector` từ `spring.integration.rsocket.client.*` khi cấu hình điều kiện thỏa.

Điểm cuối là khác biệt quan trọng. Có RSocket starter không đồng nghĩa có mọi gateway Spring Integration; có Spring Integration core không đồng nghĩa tự động có RSocket connector khi module `spring-integration-rsocket` chưa ở classpath.

### Cổng server RSocket TCP độc lập

Trong **inventory-service**, nếu dùng RSocket TCP:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 9898
~~~

Đây là cấu hình cho RSocket server, không phải cổng REST `server.port`. Khi dùng WebFlux + Reactor Netty, có thể kết hợp RSocket qua WebSocket theo cấu hình `spring.rsocket.server.transport=websocket` và `mapping-path`, nhưng không phải mọi Servlet web server đều hỗ trợ cách gắn RSocket đó.

### Kết nối client Spring Integration do Boot tạo

Trong **checkout-service**, nếu đã có `spring-integration-rsocket`:

~~~yaml
spring:
  integration:
    rsocket:
      client:
        host: inventory.internal
        port: 9898
~~~

Ví dụ trên chọn TCP. Với WebSocket, có thể dùng `spring.integration.rsocket.client.uri` theo phiên bản Boot hỗ trợ, thay vì host/port TCP. Connector được Boot cấu hình giúp giảm boilerplate, nhưng ứng dụng vẫn phải định nghĩa **route, interaction model, expected response type, timeout và business error handling**.

Khi cần điều chỉnh nhiều backend, TLS hoặc transport đặc biệt, có thể tạo connector bằng bean riêng. Trước khi làm, xác minh điều kiện auto-configuration để tránh hai connector cùng kết nối đến một service ngoài ý muốn.

## 5. Inbound gateway: chuyển request RSocket thành Spring Message

Để minh họa, inventory-service tiếp nhận một `requestResponse` trên route `inventory.stock`. Bên nhận dùng Java bean `RSocketInboundGateway` và transformer của Spring Integration. Giả sử payload yêu cầu là một mã SKU dạng string và response là chuỗi trạng thái kho.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.rsocket.RSocketInteractionModel;
import org.springframework.integration.rsocket.inbound.RSocketInboundGateway;

@Configuration
public class StockInboundConfiguration {

    @Bean
    RSocketInboundGateway stockInboundGateway() {
        var gateway = new RSocketInboundGateway("inventory.stock");
        gateway.setRequestChannelName("stockRequests");
        gateway.setRequestElementClass(String.class);
        gateway.setInteractionModels(
                RSocketInteractionModel.requestResponse);
        return gateway;
    }
}
~~~

Transformer xử lý yêu cầu theo hướng reactive:

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class StockTransformer {

    private final InventoryQueryService inventory;

    public StockTransformer(InventoryQueryService inventory) {
        this.inventory = inventory;
    }

    @Transformer(inputChannel = "stockRequests")
    public Mono<String> readStock(Flux<String> skuPublisher) {
        return skuPublisher
                .next()
                .flatMap(inventory::describeStock);
    }
}
~~~

Trong ví dụ `InventoryQueryService.describeStock(String)` do ứng dụng định nghĩa và trả `Mono<String>`, ví dụ `Mono.just("IN_STOCK")`. Thực tế nó cần kiểm tra SKU, phân quyền và truy vấn qua client/DAO phù hợp. Nếu sử dụng JDBC blocking, không gọi JDBC trực tiếp trên event loop của RSocket; cần scheduler có giới hạn hoặc adapter bất đồng bộ phù hợp.

Ý nghĩa các dòng cấu hình:

1. `RSocketInboundGateway("inventory.stock")` đăng ký mapping route RSocket.
2. `setInteractionModels(requestResponse)` giới hạn endpoint này nhận loại tương tác đã chọn; mặc định lớp gateway có thể hỗ trợ nhiều interaction model.
3. `setRequestElementClass(String.class)` xác định cách decode phần tử payload. Nếu không đặt, kiểu được suy theo content type và có thể là `String` hoặc `byte[]`, tùy RSocketStrategies.
4. `setRequestChannelName("stockRequests")` đặt tên request channel Spring Integration.
5. Transformer nhận một `Flux<String>` vì gateway xử lý đường payload theo ngữ nghĩa reactive. `next()` lấy phần tử đầu tiên cho unary request; đây là chính sách của ví dụ, không phải cách nên xử lý request-channel có nhiều phần tử.
6. Khi response cần trả về, gateway sử dụng reply của flow và encoder tương ứng để tạo RSocket reply.

Nếu cần phép biến đổi không phụ thuộc database, ví dụ:

~~~java
@Transformer(inputChannel = "stockRequests")
public Mono<String> echoUppercase(Flux<String> input) {
    return input.next().map(String::toUpperCase);
}
~~~

Đây là **phương án thay thế** transformer nghiệp vụ phía trên; nếu đặt đồng thời hai subscriber/transformer cùng xử lý một request channel, có thể gây tranh chấp hoặc sai quy tắc reply. Hãy chọn một flow xử lý chính hoặc dùng router xác định đường đi.

### Input publisher không mặc nhiên là một String

Với interaction model `requestChannel`, payload có thể là nhiều phần tử theo thời gian. Nếu dùng `next()` sẽ chỉ tiêu thụ phần tử đầu và hủy subscription upstream; không phù hợp nếu yêu cầu xử lý từng phần tử. Với một số codec như `StringDecoder`, cách xác định ranh giới mỗi phần tử còn phụ thuộc MIME/encoding. `setDecodeFluxAsUnit(true)` là một lựa chọn đặc biệt khi muốn decode toàn bộ Flux như một đơn vị, nhưng phải hiểu chi phí buffer và hành vi của decoder đang dùng.

Đối với stream lớn, tránh `collectList()` không giới hạn; xử lý theo backpressure, batch kích thước hữu hạn hoặc cơ chế lưu trữ riêng.

## 6. Inbound gateway bằng Java DSL

Nếu ứng dụng dùng Java DSL `IntegrationFlow`, có thể tạo endpoint và transformer trong một bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.rsocket.RSocketInteractionModel;
import org.springframework.integration.rsocket.dsl.RSockets;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class StockInboundFlowConfiguration {

    @Bean
    IntegrationFlow uppercaseInboundFlow() {
        return IntegrationFlow
                .from(RSockets.inboundGateway("/text.upper")
                        .interactionModels(
                                RSocketInteractionModel.requestChannel))
                .<Flux<String>, Mono<String>>transform(
                        flux -> flux.next().map(String::toUpperCase))
                .get();
    }
}
~~~

Đoạn trên minh họa **requestChannel** nhưng chỉ đọc một phần tử để làm ví dụ ngắn về kiểu reactive. Đối với hai chiều thực tế, transformer phải xử lý cả stream đầu vào và trả stream/publisher phù hợp, không lấy phần tử đầu tiên nếu cần giữ đầy đủ giao tiếp. Nên ghi rõ hợp đồng tương tác ở mức route để client không gửi requestStream tới một endpoint chỉ được đăng ký requestChannel.

Một `ClientRSocketConnector` hoặc `ServerRSocketConnector` cần tồn tại để endpoint được phát hiện/đăng ký. Nếu dùng hạ tầng server của Boot với Spring Integration, không nhất thiết tự tạo một `ServerRSocketConnector` thứ hai. Việc thêm connector phải theo **một mô hình quản lý server nhất quán**.

## 7. Outbound gateway: gọi RSocket từ integration flow

Trong **checkout-service**, một Spring Message từ integration flow cần gọi route `inventory.stock` rồi chuyển kết quả cho các bước tiếp theo. Ta dùng `ClientRSocketConnector` do Boot cấu hình theo `spring.integration.rsocket.client.host` và `port` ở mục 4.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.rsocket.ClientRSocketConnector;
import org.springframework.integration.rsocket.RSocketInteractionModel;
import org.springframework.integration.rsocket.dsl.RSockets;

@Configuration
public class StockOutboundFlowConfiguration {

    @Bean
    IntegrationFlow stockOutboundFlow(
            ClientRSocketConnector inventoryConnector) {

        return IntegrationFlow
                .from("stockLookupRequests")
                .handle(RSockets.outboundGateway("inventory.stock")
                        .interactionModel(
                                RSocketInteractionModel.requestResponse)
                        .expectedResponseType(String.class)
                        .clientRSocketConnector(inventoryConnector))
                .channel("stockLookupReplies")
                .get();
    }
}
~~~

Ở đây:

- `stockLookupRequests` là channel đầu vào của integration flow; upstream có thể là gateway ứng dụng, transformer hoặc service activator.
- `RSockets.outboundGateway("inventory.stock")` xác định route đích, **khác với tên TCP host**.
- `interactionModel(requestResponse)` chọn ngữ nghĩa một request/một response.
- `expectedResponseType(String.class)` khai báo cách decode phản hồi.
- `clientRSocketConnector(...)` cung cấp requester/kết nối cần thiết.
- `stockLookupReplies` nhận kết quả downstream theo cơ chế reactive/async của outbound gateway.

**Điểm quan trọng về reply:** `RSocketOutboundGateway` là một `AbstractReplyProducingMessageHandler` hoạt động theo kiểu bất đồng bộ. Hồi đáp từ gateway có liên quan tới `Mono`/`Flux` và cách channel phía sau xử lý subscription. Đặc biệt với `requestStream`/`requestChannel`, reply `Flux` có thể được bọc trong một phản hồi reactive để giữ phạm vi một request; không được giả định mỗi event sẽ tự biến thành một Spring Message độc lập cho mọi cấu hình channel.

Khi flow có kết hợp gateway gọi method của ứng dụng, `@MessagingGateway` hoặc functional gateway, cần kiểm thử **kiểu trả về và thời điểm hoàn tất** đúng với loại channel sử dụng. Nếu không có subscriber cho một publisher lạnh (cold publisher), thao tác RSocket có thể chưa được thực thi.

### Tự tạo ClientRSocketConnector khi cần

Nếu Boot không tự tạo được connector do cấu hình đặc biệt, có thể khai báo:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.rsocket.ClientRSocketConnector;

@Configuration
public class ManualRSocketClientConfiguration {

    @Bean
    ClientRSocketConnector inventoryConnector() {
        return new ClientRSocketConnector(
                "inventory.internal", 9898);
    }
}
~~~

Đây là **phương án thay thế** cấu hình client qua properties của Spring Boot. Không cùng lúc tạo thêm bean này và auto-configured connector trùng mục tiêu mà không có lý do. Với nhiều server, tạo bean có tên/`@Qualifier` cho từng endpoint và xác định những connector nào có thể tự khởi động trong môi trường startup phụ thuộc downstream.

`ClientRSocketConnector` quản lý vòng đời kết nối RSocket và có thể nhận cấu hình `RSocketStrategies`, setup route/data/metadata và connector configurer. Cần định nghĩa TLS, reconnect, keepalive và thời hạn lời gọi khi môi trường yêu cầu; cấu hình host/port chỉ giải quyết bước định tuyến cơ bản.

## 8. Khi nào dùng outbound như một “adapter” một chiều?

Trong mô hình Spring Integration, outbound gateway thường có reply, nhưng RSocket cung cấp `fireAndForget`. Để phát một sự kiện telemetry có thể không cần payload nghiệp vụ trả về:

~~~java
@Bean
IntegrationFlow telemetrySignalFlow(
        ClientRSocketConnector telemetryConnector) {

    return IntegrationFlow
            .from("telemetrySignals")
            .handle(RSockets.outboundGateway("telemetry.ingest")
                    .interactionModel(
                            RSocketInteractionModel.fireAndForget)
                    .clientRSocketConnector(telemetryConnector))
            .channel("telemetryCompletions")
            .get();
}
~~~

**Không nhầm fire-and-forget với delivery bền vững.** Không có phản hồi nghiệp vụ không có nghĩa message đã được consumer thực thi hoặc persisted. RSocket `fireAndForget` phù hợp với tín hiệu mất được hoặc có nguồn dữ liệu để đồng bộ lại.

Nếu dùng outbound gateway như một outbound adapter với `expectedResponseType = void`, vẫn phải bảo đảm **Mono được subscribe**; tài liệu Spring Integration lưu ý output channel phải được cấu hình, kể cả khi sử dụng `NullChannel` để khởi tạo subscription theo đường xử lý của thư viện. Các cách cấu hình `NullChannel`/reply semantics phụ thuộc API và flow cụ thể; test fire-and-forget phải đo rằng handler remote thật sự được gọi.

Với thông điệp tạo đơn hàng, thanh toán hoặc xuất hóa đơn cần đảm bảo, nên sử dụng queue, transactional outbox hoặc request-response có idempotency key/receipt theo hợp đồng. Một method RSocket fire-and-forget không thay thế hàng đợi.

## 9. So sánh Gateway Spring Integration với @MessageMapping và RSocketRequester

Một server RSocket không bắt buộc phải có `RSocketInboundGateway`. Nếu chỉ xử lý một route, Spring Messaging `@MessageMapping` đôi khi rõ hơn:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class StockController {

    private final InventoryQueryService inventory;

    public StockController(InventoryQueryService inventory) {
        this.inventory = inventory;
    }

    @MessageMapping("inventory.stock")
    public Mono<String> stock(String sku) {
        return inventory.describeStock(sku);
    }
}
~~~

Ở client Spring Messaging, có thể dùng `RSocketRequester`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
public class StockRequesterConfig {

    @Bean
    RSocketRequester stockRequester(
            RSocketRequester.Builder builder) {
        return builder.tcp("inventory.internal", 9898);
    }
}
~~~

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

public class DirectStockClient {
    private final RSocketRequester requester;

    public DirectStockClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<String> getStock(String sku) {
        return requester.route("inventory.stock")
                .data(sku)
                .retrieveMono(String.class);
    }
}
~~~

Hai ví dụ này là **đường trực tiếp Spring Messaging**. Trong hệ thống tích hợp phức tạp, gateway Spring Integration giúp đóng gói đường RSocket như một endpoint của flow và tạo điều kiện dùng router, transform, enrich, error channel hoặc các adapter khác.

Nếu dùng đồng thời `@MessageMapping` và Spring Integration RSocket gateways trên một server, với Spring Boot cần xem `spring.integration.rsocket.server.message-mapping-enabled`. Khi property này được bật theo phiên bản hỗ trợ, hạ tầng tích hợp có thể phục vụ cả hai loại endpoint bằng message handler tương thích. Tránh hai handler cùng đăng ký route trùng nhau và kiểm thử mapping thật sự trên network.

## 10. Mapping interaction model với payload và channel

Không có một cơ chế channel chung phù hợp cho cả bốn model:

| Model | Payload đi vào Spring Integration | Reply phù hợp | Điều cần tránh |
| --- | --- | --- | --- |
| `requestResponse` | Một yêu cầu, có thể được biểu diễn dưới dạng reactive publisher trong inbound handler | `Mono<T>` hoặc kết quả duy nhất | Để transformer trả Flux dài vô hạn |
| `fireAndForget` | Payload một chiều | Không có business response | ACK/commit giả định đã thành công |
| `requestStream` | Một request đầu vào | `Flux<T>` phản hồi nhiều phần tử | Buffer toàn bộ stream hoặc block event loop |
| `requestChannel` | `Publisher<T>` nhiều phần tử đầu vào | Publisher/Flux phản hồi | Dùng `next()` rồi bỏ hết phần dữ liệu còn lại |

Đặc biệt ở RSocket inbound của Spring Integration, `payload` có thể là **Flux** kể cả trường hợp requestResponse. Điều này khác với hình dung “handler nhận một DTO trực tiếp” của nhiều controller MVC. Thiết kế transformer phải kiểm tra loại payload mà gateway gửi theo `requestElementClass` và codec.

### MessageChannel không tự biến Flux thành từng Message

- `DirectChannel` đưa một Spring Message đến handler đồng bộ trên thread gọi theo mặc định; nếu payload là `Flux`, handler nhận **publisher đó**, không nhất thiết từng event riêng.
- `FluxMessageChannel` hỗ trợ reactive pipeline; subscription và sự lan truyền publisher có semantics riêng.
- `ExecutorChannel` chuyển execution sang thread khác và không tự lan transaction ThreadLocal của JDBC.
- `QueueChannel` có thể buffer message nội bộ trong tiến trình, nhưng **không thay thế durable queue** của RabbitMQ/JMS.

Trong một flow RSocket-to-JDBC, đừng áp dụng `block()` trực tiếp trên event loop khi chờ SQL. Nếu dùng JDBC blocking, tách sang bounded scheduler/worker thích hợp và giới hạn concurrency, hoặc dùng R2DBC khi mô hình reactive hoàn toàn là yêu cầu.

### Backpressure và huỷ subscription

RSocket hỗ trợ request-n/backpressure ở mức giao thức cho các stream thích hợp. Tuy nhiên, backpressure xuyên suốt phụ thuộc cách những channel và transformer trong flow xử lý `Publisher`. Nếu một bước chuyển sang hàng đợi không giới hạn hoặc gọi `subscribe()` tùy tiện, downstream có thể mất khả năng phản áp và memory tăng liên tục.

Các yêu cầu thiết kế:

1. Giới hạn message size, số connection/stream và số event đang xử lý đồng thời.
2. Bảo toàn tín hiệu `cancel` tới nguồn dữ liệu khi caller ngừng nhận.
3. Tránh `collectList()`, `cache()` và buffer vô hạn cho stream dài.
4. Với dữ liệu nghiệp vụ cần đúng thứ tự, thiết kế sequence/version và chiến lược partition; không mặc định mọi consumer chạy song song vẫn giữ thứ tự end-to-end.
5. Kiểm tra metrics buffer, event loop saturation, heap và p99 latency ở tải lớn.

## 11. Route, MIME, codec và hợp đồng dữ liệu

Route RSocket tương đương tên method/đích logic, ví dụ `inventory.stock` hoặc `orders.status.watch`. Nó **không phải** host, port hay đường dẫn file. RSocket truyền payload và metadata; phần routing thường được mã hoá trong metadata theo định dạng được hỗ trợ.

`RSocketStrategies` của Spring Messaging/Boot chứa decoder, encoder và metadata extractor. Khi triển khai hai service, chúng phải thống nhất:

- `dataMimeType` như JSON/CBOR hoặc MIME custom có decoder/encoder phù hợp.
- `metadataMimeType` và cách routing metadata được ghép.
- Kiểu payload đầu vào, `expectedResponseType` đầu ra.
- Version của DTO/schema, ví dụ `eventVersion`, `schemaVersion` và quy tắc mở rộng không phá consumer cũ.
- Cách biểu diễn missing/null/default, dấu thời gian, số tiền và mã lỗi.
- Giới hạn kích thước frame/payload và khả năng chunking/streaming.

Ví dụ một payload nghiệp vụ:

~~~json
{
  "requestId": "REQ-2026-1093",
  "schemaVersion": 1,
  "sku": "SKU-042",
  "quantity": 2
}
~~~

Đối với message nhiều thành phần, dùng DTO có validation rõ:

~~~java
public record StockQuery(
        String requestId,
        int schemaVersion,
        String sku,
        int quantity
) {}
~~~

Nếu dùng `RSocketInboundGateway` với payload JSON DTO, cấu hình `requestElementClass(StockQuery.class)` và codec phải tương thích. Ở outbound, khai báo `expectedResponseType` là DTO phản hồi, đồng thời chú ý response type thay đổi khi dùng streaming hoặc generic publisher. Không nhầm **Spring Integration MessageHeaders** với metadata RSocket: không phải mọi header Java sẽ tự được serialize qua connection.

### Metadata và correlation ID

`RSocketOutboundGateway` có khả năng tính `metadata` theo `Message<?>` thông qua một expression trả map gắn giá trị với `MimeType`. Đây là cơ chế để chuyển những trường như trace/correlation hoặc metadata được hợp đồng quy định; phải khai báo đúng MIME và codec.

Không gửi bearer token hoặc dữ liệu bí mật trong log, error header, URL hoặc trace tag. Khi đưa thông tin định danh/role qua metadata, phía server phải **xác thực** token hoặc kết nối, không mặc định tin một header do client tự khai. Áp dụng quyền theo route và tenant sau khi xác thực.

## 12. Timeout, reconnect, retry và resume trong gateway

Có bốn lớp khôi phục dễ nhầm:

| Cơ chế | Phạm vi | Điều được giải quyết | Điều vẫn cần ứng dụng quyết định |
| --- | --- | --- | --- |
| `timeout` của Reactor | Publisher/RPC cụ thể | Không chờ mãi một phản hồi | Timeout sau side effect có thể không rõ kết quả |
| `reconnect` của connector | Connection/transport | Tạo kết nối mới khi mất transport | Stream/request cũ không tự có lại toàn bộ tiến độ |
| `resume` của giao thức/thư viện | Session RSocket đang có | Cố khôi phục frame/stream nếu hai phía còn state | Hết hạn, mất session, server restart và dữ liệu lịch sử |
| `retryWhen` hoặc retry flow | Nghiệp vụ/request | Thử lại lời gọi khi lỗi hợp lệ | Giới hạn attempts, idempotency, total budget |

Khi dùng Spring Integration `ClientRSocketConnector`, có thể cấu hình `RSocketConnectorConfigurer` để điều chỉnh rsocket-java connector theo phiên bản sử dụng. Khi dùng Spring Messaging `RSocketRequester.Builder`, callback `rsocketConnector(...)` cũng cho phép tùy biến connector ở tầng thấp. Chọn một nơi chủ quản lý connection để policy không lệch nhau.

Ví dụ retry cho một **truy vấn chỉ đọc** trong mã Reactor:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<StockReply> readWithBudget(Mono<StockReply> rpc) {
    return rpc.retryWhen(
            Retry.backoff(2, Duration.ofMillis(200))
                    .filter(this::isTransientTransportError))
            .timeout(Duration.ofSeconds(2));
}

private boolean isTransientTransportError(Throwable failure) {
    // Phân loại exception dựa trên Spring/RSocket phiên bản đang dùng.
    return failure instanceof TransientRSocketCallException;
}
~~~

`TransientRSocketCallException` trong ví dụ là **exception nghiệp vụ do ứng dụng tự định nghĩa**, cần ánh xạ từ lỗi transport thực tế. Không bắt mọi exception và coi đều retryable. `Retry.backoff(2,...)` biểu thị tối đa hai lần retry sau lần đầu; `timeout` ngoài bảo vệ ngân sách tổng publisher.

Đối với thao tác ghi `reserveStock`, khi client timeout rồi retry, server có thể **đã commit** giao dịch nhưng response bị mất. Dùng cùng một `requestId` cho mọi attempt, ghi biên nhận giao dịch có unique constraint và trả lại kết quả đã xử lý. Thời hạn reconnect/resume của connection không thay thế transaction/idempotency nghiệp vụ.

**Resume không phải durable messaging.** Nó chỉ cố duy trì một phiên RSocket đã tồn tại nếu cả hai phía còn trạng thái và frame buffer; không cung cấp lịch sử nhiều ngày hoặc phát lại xuyên mọi server restart. Khi cần lấy lại event bị lỡ, dùng cursor/sequence kết hợp database, outbox hoặc broker có retention.

## 13. Transaction, inbox/outbox và kết hợp các adapter khác

Một integration flow có thể nhận yêu cầu RSocket, ghi SQL rồi phát sự kiện qua RabbitMQ:

~~~mermaid
flowchart LR
    Client["RSocket Client"] --> G["Inbound Gateway"]
    G --> V["Validate + authorize"]
    V --> S["@Transactional Service"]
    S --> DB[("SQL + inbox/outbox")]
    DB --> Relay["Outbox relay"]
    Relay --> MQ[("RabbitMQ")]
    S --> Reply["RSocket response"]
~~~

Cần phân biệt **kết thúc xử lý RSocket** và **commit của nguồn dữ liệu**. Nếu handler trả response trước SQL commit rồi transaction lỗi, client nhận một tín hiệu sai. Nếu SQL commit nhưng TCP rớt trước khi response đến nơi, caller không biết đã thành công hay chưa. Thiết kế state và idempotency cho cả hai trường hợp.

### Ví dụ khoá chống trùng

~~~sql
CREATE TABLE processed_inventory_commands (
    caller_id     VARCHAR(100) NOT NULL,
    request_id    VARCHAR(120) NOT NULL,
    result_json   TEXT NOT NULL,
    processed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (caller_id, request_id)
);
~~~

Mỗi lần nhận `ReserveStock` server xác thực caller, lấy `requestId`, rồi trong cùng SQL transaction:

1. Ghi khóa xử lý duy nhất hoặc khóa/đọc biên nhận tồn tại theo chiến lược concurrency.
2. Nếu request đã hoàn tất, trả kết quả đã lưu, không tạo reservation mới.
3. Nếu là request mới, cập nhật tồn kho và reservation, lưu kết quả trong cùng transaction.
4. Commit trước khi báo nghiệp vụ thành công.
5. Nếu cần phát sự kiện, ghi `outbox_event` cùng transaction và để relay gửi sau.

Với JDBC qua Spring Integration async channel, nhớ rằng transaction imperative gắn với thread; gửi message qua `ExecutorChannel` hoặc một reactive scheduler mới **không tự đem transaction theo**. Hãy đặt transaction boundary trong một Spring service được gọi ở đoạn xử lý đúng thread, hoặc chọn R2DBC transaction khi kiến trúc yêu cầu reactive database và được cấu hình tương ứng.

### Kết hợp HTTP và cache

Nếu flow RSocket nhận trạng thái order, sau đó gọi HTTP client rồi lưu cache:

- HTTP timeout không làm SQL transaction rollback phần đã commit từ trước.
- Cập nhật cache trước commit SQL có thể tạo dữ liệu sai khi SQL rollback.
- Chuyển trạng thái sang broker có thể phát trùng do broker retry; consumer phải chống trùng.
- Một message stream RSocket không nên đóng vai trò nguồn sự thật duy nhất khi cần phục hồi sau mất kết nối dài.

Điểm tích hợp cần có hợp đồng lỗi: retry ở chặng nào, ai giữ trạng thái, bao giờ coi job thành công, và có được phép trả response trước khi các bước downstream hoàn tất hay không.

## 14. Bảo mật đường truyền và phân quyền theo route

RSocket hoạt động qua TCP/WebSocket và có thể có TLS hoặc đi qua network proxy/mesh. Khi triển khai:

- Xác định server port/WebSocket path, TLS termination và tuyến traffic tới đúng pod.
- Bật TLS cho kết nối ngoài vùng tin cậy, cấu hình certificate/trust store và rotation phù hợp.
- Xác thực caller theo token, mTLS hoặc cơ chế bảo mật được hỗ trợ trong hệ sinh thái Spring/RSocket.
- Phân quyền theo route: `inventory.stock` có thể được phép cho nhiều caller, `inventory.reserve` cần identity có quyền ghi.
- Kiểm soát số connections/streams, kích thước payload/metadata và tốc độ request theo tenant.
- Hạn chế CORS/Origin và xác thực handshake nếu sử dụng WebSocket từ browser hoặc gateway.

Đừng coi route hay `requestId` là bằng chứng quyền; chúng do client cung cấp. Metadata phải được validate và truy cập tài nguyên theo identity đã xác thực. Không viết token, password hoặc nội dung khách hàng vào log/tracing mặc định.

Một ứng dụng dùng Spring Integration gateway có thể kiểm tra auth trước khi message đi vào core flow, ví dụ trong RSocket authentication/interceptor hay một service xác thực đầu flow. Nhưng nếu dùng filter của flow để từ chối, phải thiết kế **đường trả lỗi RSocket** rõ ràng; không âm thầm drop request-response làm caller chờ tới timeout.

## 15. Quan sát flow: metric nào cho thấy adapter đang khỏe?

RSocket gateway nối giữa network và message flow; quan sát một bên là chưa đủ. Các số liệu có ích:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Connection opens/closes, handshake failures | Độ ổn định transport và TLS/setup |
| Active RSocket streams theo route | Áp lực requestStream/requestChannel |
| Request count theo route/model/status | Tập trung lỗi ở endpoint nào |
| End-to-end latency p50/p95/p99 | Phân biệt route chậm vì codec, DB hay downstream |
| Timeout/cancellation counts | Caller bỏ cuộc hoặc server quá chậm |
| Backpressure/buffer pending | Có chặng xử lý không theo kịp dữ liệu hay không |
| Spring Integration channel dispatch failures | Lỗi transformer/router/service activator |
| Reactive error signals và errorChannel | Lỗi có được đưa về đường xử lý mong muốn không |
| Connector reconnect/resume attempts | Nguyên nhân mạng/churn, tỷ lệ khôi phục |
| SQL transaction rollback, retry/inbox hits | Sự cố dữ liệu, redelivery và side effect trùng |
| Outbox backlog/age | Broker/event relay có đang bị tụt hậu không |

Có thể dùng Spring Boot Actuator/Micrometer và instrumentation/tracing của Reactor/Spring Integration/RSocket phù hợp phiên bản. **Không mặc định** starter RSocket tự thu thập metric riêng cho mọi route và MessageChannel; khi cần, bổ sung interceptor/observability handler và kiểm tra dữ liệu thật.

Một bản log gợi ý dùng các trường: `traceId`, `requestId`, `route`, `interactionModel`, `elapsedMs`, `status`, `exceptionCategory`. Khi nhiều service cùng tham gia, truyền correlation/trace qua metadata an toàn và gắn vào context phù hợp. Reactor Context và Spring Message headers không tự luôn đồng nhất; cần thiết kế propagation thay vì trông chờ ThreadLocal.

### Khi flow lỗi, phản hồi về client thế nào?

Với request-response, lỗi trong transformer/service có thể biến thành tín hiệu `onError` trên publisher, từ đó đi thành lỗi RSocket. Nếu dùng Spring Integration errorChannel, kiểm tra xem error handling có **tiếp tục tạo reply**, phát lỗi hay kết thúc không phản hồi. Không chỉ log `ErrorMessage` rồi bỏ qua, vì caller có thể phải chờ tới timeout và dữ liệu không được ghi nhận.

Với fire-and-forget, client không có business response để kiểm tra kết quả; cần giám sát server, receipt ở tầng khác hoặc durable messaging khi SLA không cho phép mất dữ liệu.

## 16. Kiểm thử các lớp một cách tách biệt

**Unit test của transformer** xác minh payload đúng, validate/route và mapping error. **Integration test RSocket thật** mới xác nhận channel, connector, codec, route và subscription hoạt động với Spring Boot.

| Kịch bản | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Server startup | Boot với `spring.rsocket.server.port` và module RSocket | Gọi route qua TCP thành công |
| Inbound requestResponse | Gửi SKU qua `inventory.stock` | Transformer nhận Flux và trả đúng response |
| Model sai | Gửi requestStream vào endpoint chỉ cho requestResponse | Request bị từ chối/không route như hợp đồng |
| Outbound qua ClientRSocketConnector | Gửi Message vào `stockLookupRequests` | Remote nhận một request, reply đi vào channel đã cấu hình |
| MIME/codec không khớp | Client gửi sai content type hoặc schema | Nhận lỗi decode có kiểm soát, không ghi dữ liệu sai |
| Metadata/correlation | Gửi trace ID hợp lệ | Server ghi trace và trả kết quả liên kết đúng |
| Auth thiếu/quyền sai | Gọi route bị hạn chế | Bị từ chối trước side effect |
| Reactive stream/backpressure | Server stream nhiều phần tử; subscriber request từng nhóm | Giới hạn buffer và demand đúng; không OOM |
| Client cancel stream | Caller cancel giữa luồng | Server ngừng tác vụ/giải phóng tài nguyên theo policy |
| Transport mất/reconnect | Cắt TCP rồi thử gọi lại | Kết nối mới phục vụ request mới; stream cũ có recovery rõ |
| Resume (nếu bật) | Cắt mạng ngắn khi session còn state | Có RESUME_OK hoặc lỗi/fallback theo khả năng đã cấu hình |
| Timeout sau SQL commit | Giữ hoặc cắt response sau khi DB ghi | Retry cùng requestId không nhân đôi side effect |
| Spring Integration + @MessageMapping | Bật property tương thích, đăng ký 2 route khác nhau | Cả endpoint gateway lẫn controller hoạt động |
| Nhiều backend | Hai ClientRSocketConnector khác nhau | Mỗi flow gọi đúng endpoint theo qualifier |
| Error channel | Transformer ném lỗi | Có đường xử lý lỗi và tín hiệu tới caller phù hợp |
| Shutdown | Dừng Spring context khi có stream | Connector đóng/stream được hủy trong giới hạn SLA |

Một integration test có thể gọi thật bằng `RSocketRequester` tới server test trên port động. Nếu dùng server port 0, cần lấy bound port theo khả năng Boot/connector hỗ trợ; không hardcode cổng có nguy cơ trùng trong CI. Đừng chỉ kiểm tra `ApplicationContext` start thành công rồi kết luận route RSocket đã được đăng ký.

### Test Reactor với StepVerifier

Ví dụ logic độc lập:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class StockTransformerTest {

    @Test
    void convertsFirstSkuToUppercase() {
        var source = Flux.just("sku-1", "sku-2");

        StepVerifier.create(
                source.next().map(String::toUpperCase))
            .expectNext("SKU-1")
            .verifyComplete();
    }
}
~~~

Test này chỉ xác minh toán tử reactive. Muốn kiểm thử `RSocketInboundGateway` và `RSocketOutboundGateway`, cần chạy connector với server/client trên transport thực hoặc môi trường tích hợp phù hợp. Kết hợp test happy path với kiểm thử lỗi parse, cancel, timeouts, nhiều request đồng thời và rollback.

## 17. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Gọi route trả “route not found”/handler không nhận | Sai route, gateway chưa đăng ký, khác server handler | Xem mapping, connector/server startup và phiên bản |
| Boot mở server nhưng inbound flow không chạy | Thiếu `spring-integration-rsocket` hoặc endpoint chưa được phát hiện | Kiểm tra classpath, bean connector, route và request channel |
| @MessageMapping hoạt động nhưng Integration gateway không | Hai handler đăng ký độc lập hoặc mixed mapping chưa bật | Kiểm tra `spring.integration.rsocket.server.message-mapping-enabled` |
| Client boot bean không xuất hiện | Thiếu client host/port/uri hoặc điều kiện auto-config chưa thỏa | Kiểm tra property, dependency và auto-configuration report |
| Outbound không gọi được server | Wrong host/port/transport/TLS | Dùng RSocketRequester test gọi trực tiếp, xem handshake |
| Outbound trả kiểu khác dự kiến | `expectedResponseType`/codec/Publisher không khớp | Kiểm tra reply publisher và downstream channel |
| Fire-and-forget không gửi gì | Cold Mono không được subscribe | Xác minh output channel và subscription |
| RequestStream nhận một event rồi dừng | Transformer dùng `next()` hoặc cancel upstream | Xem pipeline/interaction model và subscriber demand |
| Request handler treo | Code blocking trên event loop hoặc không có reply/error | Thread dump, latency, Reactor debug, error handling |
| Kết nối chập chờn | Proxy idle timeout, TLS, keepalive, reconnect policy | Metrics connection/keepalive, proxy logs |
| Business command chạy hai lần | Retry sau timeout hoặc reconnect, thiếu idempotency | `requestId`, inbox unique, SQL transaction |
| ErrorChannel có log nhưng client timeout | Error flow không tạo response hoặc phát onError | Test đường reply của gateway với exception |
| Buffer tăng/OutOfMemoryError | `collectList()` không giới hạn, mất backpressure | Heap, active streams, pending buffers |
| WebSocket browser không kết nối | Sai path, Origin, TLS, codec hoặc proxy protocol | Network trace và cấu hình WebFlux/ingress |

Khi chẩn đoán, tách **transport** (TCP/WebSocket, TLS), **RSocket protocol** (route, interaction model, frame, keepalive), **Spring Integration** (channel, transformer, reply/error) và **nghiệp vụ** (DB commit, idempotency, broker). Cùng một biểu hiện “không nhận phản hồi” có thể xuất hiện ở bất kỳ tầng nào; đo thời gian và tín hiệu từng tầng sẽ giúp tìm nguyên nhân.

## 18. Checklist trước khi triển khai

1. Chọn Spring Messaging thuần hay Spring Integration gateway dựa trên nhu cầu integration flow; xác định đúng `RSocketInboundGateway`/`RSocketOutboundGateway`.
2. Đồng bộ phiên bản `spring-boot-starter-rsocket`, Spring Integration RSocket và Spring Framework theo BOM tương thích.
3. Có một cơ chế tạo server/đăng ký route rõ ràng; xác nhận `spring.rsocket.server.*` và mixed `@MessageMapping` nếu cần.
4. Dùng `spring.integration.rsocket.client.host/port` hoặc `uri` cho connector do Boot cấu hình khi phù hợp; tránh tạo duplicate connector.
5. Chốt route, interaction model, payload/reply type, MIME, schema version và metadata giữa client/server.
6. Thiết kế channel theo reactive semantics, subscription/backpressure, timeout, cancellation và không block event loop.
7. Với fire-and-forget, không coi việc gửi frame là business ACK; với thao tác ghi, có idempotency key và receipt.
8. Chỉ định retry/reconnect/resume theo SLA và ranh giới rõ; giữ ngân sách thời gian tổng và giám sát số attempt.
9. Phân biệt transaction database với RSocket, broker và HTTP; dùng inbox/outbox khi cần chuyển giao bền vững.
10. Bảo vệ kết nối bằng TLS và xác thực/phân quyền; hạn chế payload size/concurrency, không log dữ liệu nhạy cảm.
11. Triển khai metrics/traces cho cả transport, gateway, channel và downstream; đặt cảnh báo connection failures, timeouts và business lag.
12. Test trên network thực các trường hợp mapping, codec, mixed handler, streaming, cancel, reconnect, lỗi SQL và shutdown.

### Tài liệu tham khảo theo phiên bản

- [Spring Integration 6.5 – RSocket Support](https://docs.spring.io/spring-integration/reference/6.5/rsocket.html): các connector, inbound/outbound gateway, Java DSL, tương tác Publisher và reply.
- [Spring Boot 3.5 – Spring Integration](https://docs.spring.io/spring-boot/3.5/reference/messaging/spring-integration.html): cấu hình RSocket connector và hạ tầng tích hợp của Boot.
- [Spring Boot – RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): RSocketStrategies, server, RSocketRequester và Spring Messaging.
- [Spring Integration – Endpoint Summary](https://docs.spring.io/spring-integration/reference/endpoint-summary.html): phân biệt adapter và gateway ở từng module.
- [Spring Integration 6.5 API – RSocketInboundGateway](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/rsocket/inbound/RSocketInboundGateway.html): requestElementClass, interactionModels và gateway behavior.
- [Spring Integration 6.5 API – RSocketOutboundGateway](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/rsocket/outbound/RSocketOutboundGateway.html): route, reactive response và loại channel.

**Ghi nhớ:** RSocket cung cấp các hình thức tương tác bất đồng bộ; Spring Messaging cung cấp requester, handler và codec; Spring Integration đưa các lời gọi đó vào **MessageChannel** thông qua inbound/outbound gateway; Spring Boot giúp dựng hạ tầng theo dependency và property. Để có luồng tích hợp đáng tin cậy, vẫn cần thiết kế response subscription, backpressure, timeout, bảo mật, transaction, idempotency và khả năng kiểm thử phục hồi sau lỗi.

