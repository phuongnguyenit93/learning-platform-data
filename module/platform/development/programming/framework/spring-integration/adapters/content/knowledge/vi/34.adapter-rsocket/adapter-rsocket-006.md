# Metadata và route trong RSocket Adapter

## 1. Bối cảnh và mục tiêu

Trong Spring Integration, adapter và gateway kết nối luồng xử lý nội bộ với hệ thống bên ngoài. Với **RSocket**, một kết nối có thể phục vụ nhiều thao tác như tạo đơn hàng, tra cứu trạng thái hay nhận luồng sự kiện. Để yêu cầu đến đúng nơi, client gửi **route**; để chuyển thông tin ngữ cảnh như tenant, trace hoặc thông tin xác thực, client sử dụng **metadata**.

Bài này thuộc chương **Adapter RSocket** của module **SPRING_INTEGRATION_ADAPTERS**: kết nối hệ thống ngoài với Spring Integration bằng inbound/outbound adapter, gateway và `MessageChannel`; xây dựng hợp đồng message, xử lý lỗi và vòng đời kết nối. Phạm vi của bài là cách route và metadata đi qua ranh giới RSocket để đến một luồng Spring Integration, không đi sâu vào cấu hình vận chuyển TCP/WebSocket hoặc vận hành kết nối.

Sau bài học, bạn có thể:

- Phân biệt **route**, **metadata** và **data/payload** trong một RSocket request.
- Hiểu vì sao route thường nằm trong routing metadata, và khi nào cần composite metadata.
- Ánh xạ metadata đã được giải mã thành header của Spring Message trước khi xử lý bằng `IntegrationFlow`.
- Thiết kế route rõ nghĩa, kiểm tra hợp đồng, phát hiện lỗi route/metadata và tránh tin cậy metadata do client tự khai.

## 2. Route là gì?

RSocket hỗ trợ nhiều tương tác trên cùng một kết nối. Client cần xác định tác vụ mà server sẽ thực hiện. **Route** là tên đích logic, ví dụ:

| Route | Ý nghĩa | Dạng tương tác ví dụ |
| --- | --- | --- |
| `orders.create` | Gửi yêu cầu tạo đơn | Request-response |
| `orders.status` | Lấy trạng thái một đơn | Request-response |
| `orders.events` | Theo dõi sự kiện đơn hàng | Request-stream |
| `inventory.changed` | Thông báo tồn kho thay đổi | Fire-and-forget |

Route **không phải** URL HTTP, đường dẫn filesystem hay tên Java method. Nó là giá trị được client và server thỏa thuận. Với Spring Messaging RSocket, route có thể được đối chiếu với `@MessageMapping("orders.create")`; với Spring Integration, thành phần RSocket inbound/outbound gateway đưa request vào hoặc ra luồng message theo cấu hình adapter.

Ví dụ về một request ở mức khái niệm:

~~~text
RSocket request-response
  route metadata: "orders.create"
  extra metadata: tenant = "shop-a"
  data (JSON):   {"orderId":"A-100","quantity":2}
~~~

Server chọn handler theo route, sau đó xử lý payload và các metadata cần thiết. Không nên bắt server đọc trường `action` trong JSON chỉ để tìm handler khi RSocket đã có cơ chế định tuyến.

### Route được mang như thế nào?

RSocket có hai phần dữ liệu của một payload ở mức protocol: **data** và **metadata**. Khi dùng routing, route được mã hóa trong **routing metadata** (MIME chuẩn `message/x.rsocket.routing.v0`). Đây là định dạng có cấu trúc của RSocket, không phải HTTP header và cũng không phải chuỗi JSON tùy ý.

Trong Spring, lời gọi:

~~~java
requester.route("orders.create")
         .data(request)
         .retrieveMono(OrderAck.class);
~~~

sẽ gửi route theo cách RSocket requester và chiến lược metadata đã cấu hình hỗ trợ. Phần `data(request)` vẫn là payload nghiệp vụ. Một route không quyết định kiểu payload hay kiểu tương tác; cả hai phải được thống nhất trong hợp đồng của endpoint.

## 3. Metadata: thông tin về request, khác với payload

Metadata giúp bên nhận hiểu **cách** xử lý request; payload chứa **dữ liệu nghiệp vụ** cần xử lý. Ví dụ:

| Thông tin | Đặt ở đâu? | Lý do |
| --- | --- | --- |
| `orders.create` | Routing metadata | Chọn đích xử lý |
| `orderId`, `quantity` | Data/payload | Nội dung nghiệp vụ |
| `tenantId` | Custom metadata đã thỏa thuận | Cung cấp ngữ cảnh tenant, phải được kiểm tra ở server |
| Trace/correlation ID | Metadata hoặc header sau ánh xạ | Liên kết log/tracing giữa hệ thống |
| Access token | Metadata xác thực theo cơ chế bảo mật phù hợp | Xác thực, phân quyền; không ghi log giá trị nhạy cảm |

Ở bước thiết lập kết nối (**SETUP**), hai phía thỏa thuận MIME type của data và metadata, chẳng hạn data JSON và **composite metadata**. MIME type của data định hướng codec dùng để mã hóa/giải mã payload; MIME type của metadata định hướng cách phân tích phần metadata.

Những giá trị cần phân biệt:

| MIME type | Vai trò |
| --- | --- |
| `application/json` | Một định dạng phổ biến cho phần data |
| `message/x.rsocket.routing.v0` | Định dạng một routing metadata entry |
| `message/x.rsocket.composite-metadata.v0` | Vỏ chứa nhiều metadata entry, mỗi entry có MIME type riêng |
| `text/plain` | Có thể dùng cho metadata dạng chuỗi khi cả hai phía thỏa thuận cách diễn giải |

**Composite metadata** đặc biệt hữu ích khi một request vừa cần route, vừa cần tenant ID, trace context hoặc authentication metadata:

~~~text
RSocket metadata (composite)
  ├─ entry MIME: message/x.rsocket.routing.v0 → "orders.create"
  └─ entry MIME: text/plain                 → "shop-a"

RSocket data (JSON)
  └─ {"orderId":"A-100","quantity":2}
~~~

Lưu ý: sơ đồ thể hiện **ý nghĩa** các entry, không phải các byte truyền thực tế. Metadata RSocket được mã hóa nhị phân theo MIME type và codec tương ứng. Metadata gửi kèm **SETUP** áp dụng cho giai đoạn thiết lập kết nối; metadata gửi theo **request** gắn với tương tác cụ thể. Nếu một kết nối xử lý nhiều tenant, ngữ cảnh tenant phải được xác định đúng cho từng request, không được ngầm suy ra tenant từ một yêu cầu trước đó.

## 4. Từ route và metadata đến Spring Integration

Luồng mẫu:

~~~mermaid
flowchart LR
    A["Client RSocketRequester<br/>route + metadata + data"] --> B["RSocket responder"]
    B --> C["Giải mã route<br/>và metadata"]
    C --> D["@MessageMapping<br/>hoặc RSocket inbound gateway"]
    D --> E["Spring Message<br/>payload + headers"]
    E --> F["MessageChannel"]
    F --> G["IntegrationFlow<br/>xử lý nghiệp vụ"]
    G --> H["Reply / error"]
    H --> A
~~~

Có hai hướng tích hợp thường gặp:

1. **Spring Messaging ở biên RSocket:** `@MessageMapping` chọn route; `@Header` lấy metadata đã được extract; một Spring Integration messaging gateway nhận `Message<?>` và chuyển vào `MessageChannel`. Ví dụ ở phần tiếp theo sử dụng hướng này vì dễ quan sát chính xác điểm ánh xạ metadata.
2. **Spring Integration RSocket gateway/adapter:** RSocket inbound gateway đưa request bên ngoài vào flow; outbound gateway phát request từ flow đến RSocket peer. Route và cách truyền metadata phải được cấu hình phù hợp API của **phiên bản Spring Integration đang sử dụng**; handler nghiệp vụ vẫn nhận Spring Message với payload/header.

Điểm quan trọng là **RSocket metadata không tự động trở thành mọi header trong Spring Integration**. Spring phải biết cách trích xuất từng metadata entry. Sau khi được trích xuất thành Spring Messaging header, giá trị mới có thể được đưa tiếp vào `MessageHeaders` của Spring Integration. Trường header có cùng tên chưa bảo đảm cùng ý nghĩa nếu bên gửi và bên nhận chưa thỏa thuận MIME type, kiểu dữ liệu và cách xác thực.

## 5. Ví dụ end-to-end: route `orders.create` và metadata `tenantId`

Giả sử client tạo đơn với JSON request và gửi tenant ID riêng trong metadata. Server đưa request vào một IntegrationFlow rồi trả `OrderAck`. Đây là ví dụ minh họa với **Spring Boot 3 / Spring Framework 6 và Spring Integration 6**, sử dụng Spring Messaging RSocket làm inbound boundary. Có thể dùng các dependency tương ứng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
}
~~~

Khai báo RSocket server qua TCP trong `application.yml`:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

### Bước 1: Định nghĩa hợp đồng dữ liệu

~~~java
public record OrderRequest(String orderId, int quantity) {}

public record OrderAck(String orderId, String status) {}
~~~

Đây là hai kiểu DTO minh họa; đặt chúng trong các file Java phù hợp. Client và server phải thống nhất cấu trúc JSON và ý nghĩa từng field. Route `orders.create` tương ứng với tương tác request-response trả về đúng một `OrderAck`.

### Bước 2: Đăng ký cách trích xuất metadata

Spring cần biết metadata entry có MIME `text/plain` phải được giải mã thành chuỗi và xuất hiện ở header `tenantId`:

~~~java
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.MimeTypeUtils;

@Configuration
class RSocketMetadataConfiguration {

    @Bean
    RSocketStrategiesCustomizer tenantMetadataExtractor() {
        return strategies -> strategies.metadataExtractorRegistry(registry ->
            registry.metadataToExtract(
                MimeTypeUtils.TEXT_PLAIN,
                String.class,
                "tenantId"
            )
        );
    }
}
~~~

Ở đây `text/plain` được dùng **chỉ để đơn giản hóa ví dụ**. Khi có nhiều loại metadata dạng text, nên định nghĩa MIME type riêng cho từng loại, đăng ký codec/extractor phù hợp ở cả hai phía và tránh nhập nhằng ý nghĩa giữa các entry. Nếu thiếu extractor, route có thể vẫn được nhận diện nhưng `@Header("tenantId")` sẽ không có giá trị.

### Bước 3: Đưa Spring Message vào IntegrationFlow

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;

@MessagingGateway
interface OrderFlowGateway {
    @Gateway(requestChannel = "ordersInput")
    OrderAck submit(Message<OrderRequest> request);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderFlowConfiguration {

    @Bean
    IntegrationFlow orderFlow() {
        return IntegrationFlow.from("ordersInput")
            .handle(OrderRequest.class, (order, headers) -> {
                String tenantId = (String) headers.get("tenantId");

                if (tenantId == null || tenantId.isBlank()) {
                    throw new IllegalArgumentException("Missing tenantId");
                }
                if (order.quantity() <= 0) {
                    throw new IllegalArgumentException("quantity must be > 0");
                }

                // Demo: ở hệ thống thật, kiểm tra quyền truy cập tenant
                // và gọi dịch vụ tạo đơn trước khi trả ACK.
                return new OrderAck(order.orderId(), "ACCEPTED");
            })
            .get();
    }
}
~~~

Method `submit(Message<OrderRequest>)` mang **payload lẫn headers** vào Spring Integration. Handler nhận `OrderRequest` làm payload, đồng thời truy cập `tenantId` từ `MessageHeaders`. Nếu chỉ chuyển DTO thay vì `Message<OrderRequest>` mà không chuyển header, bạn sẽ làm mất metadata vừa extract ở ranh giới RSocket.

### Bước 4: RSocket responder ghép route với flow

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
class OrderRSocketController {
    private final OrderFlowGateway gateway;

    OrderRSocketController(OrderFlowGateway gateway) {
        this.gateway = gateway;
    }

    @MessageMapping("orders.create")
    Mono<OrderAck> create(
            @Payload OrderRequest request,
            @Header("tenantId") String tenantId) {

        Message<OrderRequest> message = MessageBuilder
            .withPayload(request)
            .setHeader("tenantId", tenantId)
            .build();

        // Messaging gateway trong ví dụ là đồng bộ. Chuyển phần xử lý
        // sang boundedElastic để tránh chặn RSocket event loop.
        return Mono.fromCallable(() -> gateway.submit(message))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

`@MessageMapping` chọn handler bằng route; `@Header("tenantId")` lấy giá trị đã trích xuất từ RSocket metadata; `MessageBuilder` đưa giá trị đó sang message của Spring Integration. Quy tắc quan trọng: **không coi tenant ID do client khai là bằng chứng phân quyền**. Cần kết hợp principal/token đã xác thực và chính sách phân quyền phía server trước khi đọc hoặc ghi dữ liệu tenant.

### Bước 5: Client gửi route và extra metadata

Trong ứng dụng client, sau khi server đã chạy ở cổng 7000:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

class OrderRSocketClient {
    private final RSocketRequester requester;

    OrderRSocketClient(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("localhost", 7000);
    }

    Mono<OrderAck> create(OrderRequest request, String tenantId) {
        return requester.route("orders.create")
            .metadata(tenantId, MimeTypeUtils.TEXT_PLAIN)
            .data(request)
            .retrieveMono(OrderAck.class);
    }
}
~~~

Spring RSocketRequester thường dùng **composite metadata** để mang route cùng những metadata entry khác. Nếu tự cấu hình metadata MIME type/strategies, phải bảo đảm client và server đồng thuận với định dạng đã chọn. Không thể giả định rằng mọi RSocket peer bên ngoài Spring đều tự giải mã route hay custom metadata như Spring.

Kết quả kỳ vọng khi gửi `OrderRequest("A-100", 2)` kèm `tenantId = "shop-a"` là:

~~~json
{"orderId":"A-100","status":"ACCEPTED"}
~~~

Đây là kết quả dự kiến của ví dụ, không phải log chạy thử thực tế. Nếu bỏ metadata tenant hoặc gửi sai MIME type, server có thể không tạo được header `tenantId` và request phải bị từ chối theo hợp đồng.

## 6. Phân biệt ba tầng thông tin trong luồng

| Tầng | Thành phần | Ví dụ | Trách nhiệm |
| --- | --- | --- | --- |
| RSocket wire protocol | Data + metadata entries | JSON, routing, text metadata | Vận chuyển trên TCP/WebSocket theo tương tác RSocket |
| Spring RSocket/Messaging | Route, decoded payload, extracted headers | `@MessageMapping`, `@Header` | Giải mã, chọn handler, chuyển đổi message |
| Spring Integration | `Message<?>` / `MessageHeaders` | `ordersInput`, `IntegrationFlow` | Routing nội bộ, chuyển đổi, xử lý, reply/error |

Không đồng nhất ba khái niệm sau:

- **RSocket route**: tên tác vụ ở biên kết nối, ví dụ `orders.create`.
- **Spring Integration channel name**: địa chỉ luồng nội bộ, ví dụ `ordersInput`.
- **Metadata/header**: ngữ cảnh request, ví dụ `tenantId` hoặc `traceId`.

Cả route và channel đều định hướng xử lý, nhưng thuộc hai tầng khác nhau. Bạn có thể đổi tên channel nội bộ mà vẫn giữ route công khai. Tương tự, metadata trong RSocket cần extractor/map để đi vào headers và metadata gửi ra RSocket cần được cấu hình/serialize riêng; không phải mọi header nội bộ đều tự động được phát ra ngoài.

## 7. Thiết kế route và hợp đồng metadata

Một cách đặt tên route dễ bảo trì là `<miền>.<thao-tác>`, chẳng hạn `orders.create`, `orders.status` và `inventory.reserve`. Khi cần tương thích nhiều phiên bản hợp đồng, có thể thỏa thuận route như `v1.orders.create` hoặc `orders.v2.create`. Không đổi ý nghĩa payload của route đang được client sử dụng mà không có kế hoạch tương thích.

Nên mô tả mỗi route bằng các trường:

| Trường hợp đồng | Ví dụ cho `orders.create` |
| --- | --- |
| Route | `orders.create` |
| Tương tác | Request-response |
| Data MIME/kiểu request | JSON / `OrderRequest` |
| Reply | `OrderAck` |
| Metadata bắt buộc | `tenantId` sau khi extract; thông tin xác thực theo cơ chế được chọn |
| Quy tắc lỗi | Thiếu metadata, payload sai, tenant không được phép, lỗi nghiệp vụ |
| Tính lặp lại | Xác định rõ xử lý trùng `orderId` và chính sách idempotency |

Trong thực tế, tên route cần ổn định qua thời gian; trường động như `orderId` hoặc `tenantId` thường phù hợp hơn trong payload/metadata thay vì tạo vô hạn route riêng. Nếu dùng route template hoặc biến đích của `@MessageMapping`, cần kiểm tra cách framework khớp pattern và ánh xạ biến trong phiên bản đang sử dụng.

## 8. Route không quyết định kiểu tương tác

| Kiểu RSocket | Điều client mong chờ | Gợi ý route |
| --- | --- | --- |
| Request-response | Một kết quả hoặc lỗi | `orders.create` |
| Fire-and-forget | Không có response nghiệp vụ | `inventory.changed` |
| Request-stream | Nhiều phần tử phản hồi theo luồng | `orders.events` |
| Request-channel | Hai phía trao đổi các luồng phần tử | `orders.sync` |

Hai route có thể có tên gần giống nhau nhưng hợp đồng tương tác rất khác nhau. Với stream/channel, cần đặc biệt quan tâm **backpressure**, cancellation và việc chuyển đổi giữa Reactor Publisher với kênh/handler của Spring Integration. Không nên sử dụng một gateway đồng bộ có thể chặn thread để xử lý vô hạn một request-stream. Ví dụ `orders.create` ở trên chủ ý giới hạn ở request-response.

## 9. Kiểm tra route và metadata

Một bộ kiểm tra có giá trị cần đi qua biên RSocket thật hoặc test responder được cấu hình tương đương:

1. **Đường thành công:** gửi `orders.create`, payload hợp lệ và metadata tenant hợp lệ; kiểm tra response `ACCEPTED` và chứng minh header đã đến flow.
2. **Thiếu metadata:** bỏ `tenantId`; handler không được âm thầm nhận một tenant mặc định. Kiểm tra loại lỗi trả về và cách client xử lý.
3. **Sai MIME type:** gửi tenant dưới MIME không đăng ký extractor; kiểm tra rằng server không suy đoán sai header.
4. **Sai route:** gửi `orders.unknown`; server phải báo lỗi định tuyến thích hợp, không tự xử lý bằng flow khác.
5. **Sai payload:** gửi quantity không hợp lệ hoặc JSON không đúng schema; lỗi chuyển đổi/validation phải được quan sát rõ.
6. **Sai quyền tenant:** metadata tự khai không được mở quyền truy cập khi principal không được phép.
7. **Nhiều request trên cùng connection:** xen kẽ tenant/trace khác nhau, bảo đảm header mỗi request được cách ly chính xác.

Với test client reactive, có thể dùng Reactor `StepVerifier` để kiểm tra giá trị và tín hiệu `onError`. Trong vận hành, ghi log route, correlation ID và mã lỗi đã làm sạch; che token, mật khẩu và thông tin nhạy cảm. Khi đi qua nhiều integration flow, cần chủ động giữ những header thực sự cần thiết, tránh tùy ý đưa tất cả metadata bên ngoài vào log hoặc outbound adapter.

## 10. Lỗi thường gặp và hướng khoanh vùng

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không tìm được handler cho request | Client route sai hoặc `@MessageMapping` không khớp | Đối chiếu tên route chính xác và bean responder được đăng ký |
| Có route nhưng thiếu `tenantId` | Chưa đăng ký extractor; sai MIME; client quên extra metadata | Kiểm tra composite metadata, MIME entry và cấu hình metadata extractor |
| Payload không chuyển thành DTO | Codec/data MIME hoặc schema JSON không tương thích | Xác nhận định dạng data, lớp DTO và codec hai phía |
| Flow nhận payload nhưng mất ngữ cảnh | Chỉ chuyển DTO, bỏ `MessageHeaders` | Dùng Spring `Message<?>` hoặc ánh xạ header tường minh |
| Request-response không kết thúc | Handler không trả reply, có tác vụ chặn hoặc flow bị treo | Kiểm tra reply path, timeout và scheduler phù hợp |
| Người dùng truy cập nhầm dữ liệu tenant | Tin `tenantId` client gửi như thông tin đã xác thực | Kiểm tra quyền ở server theo principal/token và tenant được phép |
| Metadata chạy với Spring client nhưng lỗi ở peer khác | Peer không dùng chung metadata MIME/codec | Thống nhất composite metadata, routing entry, custom MIME và phiên bản protocol |

Để chẩn đoán, kiểm tra **từng lớp theo thứ tự**: kết nối RSocket → MIME/setup → routing metadata → extractor/header → Spring Messaging handler → Spring Integration channel/flow → reply. Đừng chỉ nhìn payload JSON vì route và metadata không nhất thiết xuất hiện trong JSON.

## 11. Bài tập thực hành

**Bài tập A — Bổ sung trace ID:** Thêm metadata `traceId` cho `orders.create`. Đăng ký extractor phù hợp, đưa giá trị vào Spring Message header và ghi log correlation ID mà không ghi nội dung nhạy cảm. Kiểm tra hai request liên tiếp có trace ID khác nhau.

**Bài tập B — Route mới:** Tạo route `orders.status` với request-response, payload gồm `orderId` và reply gồm `orderId`, `status`. Có thể dùng chung một `MessageChannel` hoặc tách channel tùy trách nhiệm xử lý, nhưng phải mô tả rõ ánh xạ route → flow.

**Bài tập C — Kiểm thử hợp đồng:** Viết các test cho route không tồn tại, tenant metadata bị thiếu, quantity âm và truy cập tenant sai quyền. Tiêu chí đạt là các trường hợp sai bị từ chối có thể quan sát, không phát sinh xử lý nghiệp vụ ngoài ý muốn.

### Ghi nhớ

Một yêu cầu RSocket thường mang **route trong metadata**, **payload trong data**, cùng các **metadata entry** bổ sung khi cần. Ở biên Spring, hãy giải mã và kiểm tra metadata trước khi chuyển thành header; sau đó dùng `MessageChannel` và `IntegrationFlow` để thực hiện nghiệp vụ. Route là hợp đồng với client, còn channel là thiết kế nội bộ; tách bạch hai tầng giúp hệ thống dễ thay đổi và dễ kiểm thử.
