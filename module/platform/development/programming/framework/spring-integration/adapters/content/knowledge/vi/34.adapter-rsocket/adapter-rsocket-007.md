# Payload codec và data MIME type trong RSocket Adapter

## 1. Vì sao RSocket cần codec?

Trong module **SPRING_INTEGRATION_ADAPTERS**, chúng ta kết nối hệ thống ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; đồng thời quan tâm đến hợp đồng message, lỗi và vòng đời kết nối. Với **Adapter RSocket**, bên gửi có thể thao tác trên đối tượng Java như `CreateOrder`, nhưng RSocket truyền dữ liệu ở dạng **byte**. Hai bên cần thống nhất định dạng byte đó để mã hóa và giải mã đúng.

Ví dụ, một client muốn gửi:

~~~java
new CreateOrder("ORD-102", 3)
~~~

Qua RSocket, đối tượng phải được mã hóa, chẳng hạn thành JSON:

~~~json
{"orderId":"ORD-102","quantity":3}
~~~

RSocket không tự biết `CreateOrder` là kiểu Java nào, cũng không tự chuyển mọi dãy byte thành JSON. **Codec** đảm nhiệm phép chuyển đổi này; **data MIME type** cho biết định dạng được sử dụng.

Sau bài học, bạn có thể:

- Phân biệt phần **data/payload**, **metadata**, **data MIME type** và codec của một tương tác RSocket.
- Giải thích chiều hoạt động của `Encoder` và `Decoder` trong Spring RSocket.
- Cấu hình client với `RSocketRequester` và sử dụng JSON DTO trong handler kết nối đến Spring Integration.
- Biết khi nào cần bổ sung codec cho định dạng khác JSON, cách kiểm tra tương thích và chẩn đoán lỗi chuyển đổi.

## 2. Bốn khái niệm không nên nhầm

| Khái niệm | Nội dung | Ví dụ |
| --- | --- | --- |
| **Data/payload** | Dữ liệu nghiệp vụ truyền trong phần data của một RSocket payload | JSON của đơn hàng |
| **Data MIME type** | Tên định dạng mà hai bên sử dụng để diễn giải phần data | `application/json`, `text/plain` |
| **Codec** | Bộ mã hóa/giải mã giữa giá trị ứng dụng và bytes | Jackson JSON encoder/decoder |
| **Metadata** | Thông tin đi kèm để định tuyến hoặc cung cấp ngữ cảnh | Route `orders.create`, trace ID |

Thuật ngữ *payload* của RSocket đôi khi được dùng để nói đến **cặp data + metadata**. Trong tài liệu này, khi nói **payload nghiệp vụ**, ta chỉ đề cập phần **data** chứa nội dung request/response.

Một request có thể trông như sau ở mức khái niệm:

~~~text
RSocket connection SETUP
  data MIME type:     application/json
  metadata MIME type: message/x.rsocket.composite-metadata.v0

REQUEST_RESPONSE:
  metadata:
    routing entry -> orders.create
  data:
    {"orderId":"ORD-102","quantity":3}
~~~

MIME type không đồng nghĩa với tên lớp Java. Cùng một `application/json` có thể được giải mã thành `CreateOrder`, `OrderReceipt` hoặc kiểu dữ liệu khác, tùy **kiểu đích mà handler/client yêu cầu** và cấu trúc JSON thực tế.

## 3. Data MIME type được thiết lập ở đâu?

Trong RSocket, client gửi **SETUP frame** khi mở kết nối. SETUP chứa khai báo `dataMimeType` và `metadataMimeType`. Ví dụ:

~~~text
Client                        Server
  |                             |
  |-- SETUP ------------------->|  dataMimeType = application/json
  |                             |  metadataMimeType = composite
  |-- REQUEST_RESPONSE -------->|  data là JSON bytes
  |<---------- RESPONSE --------|  data cũng theo hợp đồng JSON
  |                             |
~~~

Điều cần ghi nhớ:

1. Đây là **khai báo định dạng trong SETUP**, không phải một bước tự động đàm phán tìm codec chung. Client và server phải được cấu hình tương thích.
2. Theo mô hình RSocket chuẩn, **data MIME type thuộc về kết nối**, không phải một header HTTP `Content-Type` độc lập trong mỗi request. Nhiều route cùng dùng một kết nối phải có định dạng data tương thích với MIME type của kết nối đó.
3. **Metadata MIME type** dùng để diễn giải phần metadata. Route thường nằm trong routing metadata hoặc một entry của composite metadata; **route không phải JSON body và không quyết định data MIME type**.
4. Kiểu Java và schema payload có thể khác nhau giữa các route trên cùng kết nối: `orders.create` nhận `CreateOrder`, còn `orders.status` nhận `OrderQuery`, miễn cả hai cùng có thể dùng codec JSON đã thỏa thuận.

Nếu cần hai định dạng data khác nhau, ví dụ JSON và Protobuf, cách triển khai dễ hiểu là sử dụng **hai requester/kết nối** với SETUP và chiến lược codec tương ứng, hoặc xây dựng một giao thức bao gói riêng được thỏa thuận rõ. Không nên giả định gọi một route khác sẽ tự chuyển data MIME type của kết nối hiện hữu.

### Các MIME type thường gặp

| Data MIME type | Dạng data | Điều kiện ứng dụng |
| --- | --- | --- |
| `application/json` | Đối tượng, mảng, scalar JSON | Jackson hoặc JSON codec tương ứng phải có |
| `application/*+json` | Các loại JSON có hậu tố `+json`, ví dụ `application/vnd.example.order+json` | Codec cần hỗ trợ MIME type cụ thể |
| `text/plain` | Văn bản, chuỗi | Encoder/decoder văn bản tương thích với charset |
| `application/octet-stream` | Bytes nhị phân không gán schema ở tầng MIME | Sử dụng kiểu byte/buffer và codec nhị phân phù hợp |
| `application/cbor` | Dữ liệu nhị phân có cấu trúc kiểu CBOR | Phải có CBOR codec, không tự có chỉ vì dùng Spring |
| `application/x-protobuf` | Message theo schema Protobuf | Cần schema/type và codec Protobuf tương ứng hai phía |

Các MIME type trong bảng là ví dụ thiết kế giao thức. **Hỗ trợ thực tế phụ thuộc classpath, phiên bản thư viện và `RSocketStrategies`**; chỉ khai báo `application/cbor` hay `application/x-protobuf` không làm xuất hiện codec tương ứng.

## 4. Encoder và decoder hoạt động ở đâu?

Một codec có hai trách nhiệm chính:

- **Encoder:** nhận giá trị ứng dụng và tạo các byte theo MIME type đã chọn, ví dụ `CreateOrder` → JSON.
- **Decoder:** nhận các byte và tạo lại giá trị theo kiểu mà caller/handler mong muốn, ví dụ JSON → `CreateOrder`.

Trong Spring Framework, các hợp đồng codec thường gặp là `org.springframework.core.codec.Encoder` và `Decoder`. Spring RSocket sử dụng các encoder/decoder từ **`RSocketStrategies`** để xử lý data, kết hợp MIME type và kiểu dữ liệu đích.

~~~mermaid
flowchart LR
    A["Client: CreateOrder"] --> B["Encoder JSON"]
    B --> C["RSocket data bytes"]
    C --> D["Decoder JSON trên server"]
    D --> E["@MessageMapping: CreateOrder"]
    E --> F["Spring Integration Message"]
    F --> G["IntegrationFlow"]
    G --> H["OrderReceipt"]
    H --> I["Encoder JSON trên server"]
    I --> J["RSocket response bytes"]
    J --> K["Decoder JSON trên client"]
    K --> L["Client: OrderReceipt"]
~~~

Với request-response, có **hai quá trình codec** độc lập:

| Chặng | Encoder | Decoder |
| --- | --- | --- |
| Request client → server | Client mã hóa request | Server giải mã thành kiểu tham số handler |
| Reply server → client | Server mã hóa kết quả | Client giải mã theo kiểu `retrieveMono(...)` |

Các tình huống lỗi cần phân biệt:

- **Không có encoder phù hợp:** client không thể chuyển giá trị sang bytes, thường lỗi ngay khi chuẩn bị hoặc gửi request.
- **Không có decoder phù hợp:** server nhận bytes nhưng không tạo được kiểu tham số handler, hoặc client không giải mã được reply.
- **Có codec nhưng nội dung sai:** JSON bị hỏng, trường sai kiểu hoặc schema hai phía không tương thích.
- **Codec thành công nhưng nghiệp vụ sai:** DTO tạo được, nhưng quantity âm hoặc thiếu order ID; đây là lỗi validation, không phải lỗi codec.

## 5. Cách Spring chọn codec

Khi Spring cần gửi `CreateOrder`, nó xét kiểu dữ liệu cần mã hóa, data MIME type của kết nối và tập encoder có trong `RSocketStrategies`. Ở phía nhận, nó cũng dùng MIME type, các decoder có sẵn và **kiểu tham số handler** hoặc kiểu kết quả mà client yêu cầu.

Ví dụ:

~~~java
// Server: kiểu đích là CreateOrder.
@MessageMapping("orders.create")
Mono<OrderReceipt> create(@Payload CreateOrder request) {
    // ...
}

// Client: kiểu đích khi giải mã response là OrderReceipt.
Mono<OrderReceipt> reply = requester
    .route("orders.create")
    .data(new CreateOrder("ORD-102", 3))
    .retrieveMono(OrderReceipt.class);
~~~

Hai dòng trên không định nghĩa codec mới: chúng **sử dụng codec** đã cấu hình. Với ứng dụng Spring Boot có Jackson và các Spring RSocket codec mặc định, JSON DTO thường hoạt động mà không cần tự đăng ký encoder/decoder. Không nên đăng ký trùng JSON codec nếu chưa có nhu cầu thay đổi cách mã hóa.

### `RSocketStrategies` chứa gì?

`RSocketStrategies` tập hợp các chiến lược mà Spring Messaging RSocket cần, gồm encoder, decoder, metadata extractor, route matcher và một số thành phần hỗ trợ khác. Trong bài này, phần liên quan trực tiếp là encoder/decoder:

~~~java
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;

@Configuration
class CodecConfiguration {

    // Chỉ dùng khi thật sự cần tự bổ sung/tùy biến codec.
    // Với JSON thông thường, Spring Boot có thể đã cấu hình sẵn.
    @Bean
    RSocketStrategiesCustomizer customizeCodec() {
        return strategies -> {
            strategies.encoder(new Jackson2JsonEncoder());
            strategies.decoder(new Jackson2JsonDecoder());
        };
    }
}
~~~

Đây là minh họa vị trí đăng ký codec, **không phải cấu hình bắt buộc để chạy ví dụ JSON** ở phần tiếp theo. Trong hệ thống thật, có thể cần truyền `ObjectMapper` dùng chung để giữ thống nhất các quy ước JSON như xử lý thời gian, enum và naming strategy. Nếu client và server là hai ứng dụng khác nhau, phải rà soát cấu hình codec **ở cả hai đầu**.

### Giới hạn của việc “có Jackson là đủ”

Jackson là cơ chế chuyển object ↔ JSON, nhưng nó không tự giải quyết mọi trường hợp:

- DTO có kiểu trường hoặc cách khởi tạo không phù hợp vẫn có thể gây lỗi mapping.
- Tên trường và định dạng thời gian phải thống nhất giữa các bên.
- Không thể coi `text/plain` hay `application/x-protobuf` là JSON chỉ vì bytes nhìn có thể đọc được.
- Đăng ký codec không thay thế kiểm tra dữ liệu đầu vào hoặc phân quyền nghiệp vụ.
- Với payload lớn, bộ giải mã có thể phải gom dữ liệu vào bộ nhớ; cần thiết kế giới hạn kích thước và dạng stream phù hợp.

## 6. Ví dụ end-to-end: JSON qua RSocket đến IntegrationFlow

Ví dụ này dùng **Spring Boot 3, Spring Framework 6 và Spring Integration 6** để minh họa request-response: client gửi đơn hàng ở định dạng JSON, server giải mã thành `CreateOrder`, chuyển vào `MessageChannel` và trả `OrderReceipt`. Những đoạn Java là các thành phần minh họa trong **cùng package hoặc các package được scan**; khi dùng thực tế, đặt các public type trong file Java tương ứng.

### Bước 1 — Dependency và RSocket server

Ví dụ dependency Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
}
~~~

Client và server là hai ứng dụng riêng thì mỗi bên cần dependency phục vụ vai trò của mình. Với server RSocket TCP:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

Nếu chưa có JSON codec trên classpath hoặc cấu hình tự động bị thay đổi, cần bổ sung Jackson/cấu hình `RSocketStrategies` phù hợp trước khi dùng DTO JSON. Không dùng MIME type để giả định dependency đã sẵn có.

### Bước 2 — Định nghĩa hợp đồng dữ liệu

~~~java
public record CreateOrder(String orderId, int quantity) {}

public record OrderReceipt(String orderId, String state) {}
~~~

Với Spring Boot 3 và Jackson phù hợp, Java records là một lựa chọn đơn giản cho DTO:

~~~json
{
  "orderId": "ORD-102",
  "quantity": 3
}
~~~

Trong data bytes không có thông tin “đây là lớp `CreateOrder`”. Server quyết định giải mã thành `CreateOrder` nhờ chữ ký của handler. Các trường trong JSON phải khớp hợp đồng DTO đã thống nhất.

### Bước 3 — Tạo IntegrationFlow xử lý DTO

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@MessagingGateway
interface OrderGateway {
    @Gateway(requestChannel = "newOrderInput")
    OrderReceipt create(CreateOrder order);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderIntegrationConfiguration {

    @Bean
    IntegrationFlow createOrderFlow() {
        return IntegrationFlow.from("newOrderInput")
            .handle(CreateOrder.class, (order, headers) -> {
                if (order.orderId() == null || order.orderId().isBlank()) {
                    throw new IllegalArgumentException("orderId is required");
                }
                if (order.quantity() <= 0) {
                    throw new IllegalArgumentException("quantity must be positive");
                }

                // Minh họa: thực tế sẽ gọi service/repository tạo đơn.
                return new OrderReceipt(order.orderId(), "ACCEPTED");
            })
            .get();
    }
}
~~~

`OrderGateway` là messaging gateway nội bộ dẫn dữ liệu vào `newOrderInput`. Handler của flow nhận **DTO đã được giải mã**, vì vậy code nghiệp vụ không phải parse JSON thủ công. Spring Integration có thể tiếp tục routing, transform, gọi adapter khác hoặc trả reply. Lưu ý phần kiểm tra quantity là **validation ở tầng nghiệp vụ**, diễn ra sau khi JSON đã được decode thành công.

### Bước 4 — RSocket responder làm biên inbound

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
class OrderRSocketController {
    private final OrderGateway gateway;

    OrderRSocketController(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @MessageMapping("orders.create")
    Mono<OrderReceipt> create(@Payload CreateOrder order) {
        return Mono.fromCallable(() -> gateway.create(order))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Spring Messaging RSocket dùng routing metadata để khớp `orders.create`; sau đó decoder phù hợp chuyển **data bytes** thành `CreateOrder`. Vì messaging gateway của ví dụ là **đồng bộ**, `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` giúp tránh chạy công việc có thể chặn trên event-loop của RSocket. Một luồng end-to-end reactive cần thiết kế gateway/handler không chặn thay vì chỉ dựa vào việc đổi scheduler.

### Bước 5 — RSocketRequester gửi JSON và giải mã reply

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

class OrderClient {
    private final RSocketRequester requester;

    OrderClient(RSocketRequester.Builder builder) {
        this.requester = builder
            .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
            .metadataMimeType(MimeTypeUtils.parseMimeType(
                "message/x.rsocket.composite-metadata.v0"))
            .tcp("localhost", 7000);
    }

    Mono<OrderReceipt> create(CreateOrder order) {
        return requester.route("orders.create")
            .data(order)
            .retrieveMono(OrderReceipt.class);
    }
}
~~~

Trong ví dụ:

1. `dataMimeType(application/json)` khai báo định dạng **data** của kết nối khi tạo requester.
2. `metadataMimeType(composite)` cho biết cách đóng gói **metadata**, bao gồm routing entry.
3. `route("orders.create")` đặt đích logic cho request; nó **không** đổi data MIME type.
4. `data(order)` yêu cầu Spring tìm encoder JSON phù hợp với `CreateOrder`.
5. `retrieveMono(OrderReceipt.class)` yêu cầu client giải mã reply thành `OrderReceipt`.

Nếu server và client đều dùng chiến lược JSON tương thích, response dự kiến là:

~~~json
{"orderId":"ORD-102","state":"ACCEPTED"}
~~~

Đây là **kết quả kỳ vọng**, chưa phải kết quả chạy kiểm thử trong repository.

## 7. Đổi định dạng data: điều gì phải thay đổi?

Giả sử một route chỉ nhận chuỗi văn bản thay vì DTO JSON. Trên **kết nối dành cho `text/plain`**, client có thể tạo requester riêng:

~~~java
RSocketRequester textRequester = builder
    .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
    .tcp("localhost", 7000);

Mono<String> result = textRequester
    .route("echo.text")
    .data("Xin chào RSocket")
    .retrieveMono(String.class);
~~~

Và server có handler tương ứng:

~~~java
@MessageMapping("echo.text")
Mono<String> echo(String text) {
    return Mono.just("Đã nhận: " + text);
}
~~~

Ví dụ trên chỉ hoạt động nếu server chấp nhận MIME type `text/plain` và có codec String phù hợp. Nó minh họa **một kết nối khác**, không minh họa đổi codec riêng cho từng request của một kết nối JSON hiện hữu. Nếu ứng dụng không hỗ trợ định dạng text/plain ở endpoint này, phải cấu hình codec hoặc chọn định dạng đã được server hỗ trợ.

### Codec tùy chỉnh và vendor MIME type

Khi một hệ thống chọn `application/vnd.example.order+json`, hãy thỏa thuận MIME type này với tất cả client. Nếu cần đăng ký codec tường minh cho định dạng đó:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

@Configuration
class OrderVendorJsonCodecConfiguration {

    private static final MimeType ORDER_JSON =
        MimeTypeUtils.parseMimeType("application/vnd.example.order+json");

    @Bean
    RSocketStrategiesCustomizer orderVendorJson(ObjectMapper mapper) {
        return builder -> {
            builder.encoder(new Jackson2JsonEncoder(mapper, ORDER_JSON));
            builder.decoder(new Jackson2JsonDecoder(mapper, ORDER_JSON));
        };
    }
}
~~~

Client phải khai báo `dataMimeType(ORDER_JSON)` và cả hai phía phải có encoder/decoder đọc được dữ liệu. Jackson có thể đã hỗ trợ một số loại MIME `+json` trong cấu hình mặc định; **kiểm tra codec hiện có trước khi bổ sung** để tránh cấu hình chồng chéo. Với Protobuf, CBOR hay binary riêng, cần codec phù hợp định dạng đó, không thay MIME name để tái sử dụng JSON codec.

## 8. Codec với các kiểu tương tác RSocket

RSocket có bốn dạng tương tác phổ biến:

| Tương tác | Data được xử lý thế nào? | Ví dụ |
| --- | --- | --- |
| Request-response | Encode một request; decode một reply | `orders.create` |
| Fire-and-forget | Encode request; không chờ payload nghiệp vụ trả về | `inventory.changed` |
| Request-stream | Encode request; decode nhiều phần tử reply | `orders.events` |
| Request-channel | Encode/decode chuỗi phần tử hai chiều | `orders.sync` |

Với request-stream, bạn có thể gặp:

~~~java
Flux<OrderEvent> events = requester
    .route("orders.events")
    .data(new OrderQuery("ORD-102"))
    .retrieveFlux(OrderEvent.class);
~~~

Mỗi phần tử `OrderEvent` được decoder xử lý theo hợp đồng của stream. **Backpressure** điều phối tốc độ phát/nhận phần tử; nó không giải quyết lỗi MIME hoặc lỗi ánh xạ schema. Cần kiểm soát số lượng phần tử, kích thước dữ liệu và bộ nhớ tích lũy. Framing/fragmentation ở giao thức RSocket cũng không đồng nghĩa với việc parser của ứng dụng được phép nhận payload lớn vô hạn.

Nếu dùng Spring Integration sau RSocket, hãy xác định flow đang thao tác với **một DTO**, một tập DTO, hay một **Publisher**; không tự gom vô hạn stream vào một `List` để qua gateway đồng bộ. Chọn kiểu tương tác và codec cùng với thiết kế message flow ngay từ hợp đồng.

## 9. Codec và hợp đồng message của IntegrationFlow

Ba lớp có trách nhiệm khác nhau:

| Lớp | Đầu vào/đầu ra | Kiểm tra chính |
| --- | --- | --- |
| RSocket | Bytes và metadata theo SETUP | Định dạng được khai báo, tương tác, định tuyến |
| Spring Messaging + codec | Bytes ↔ Java DTO | Có encoder/decoder và schema tương thích |
| Spring Integration | `Message<?>` qua channel và flow | Hợp đồng nghiệp vụ, transform, routing, reply/error |

Sau khi RSocket decoder tạo DTO, **payload** của Spring Integration message có thể là đối tượng đã giải mã. Header phục vụ correlation, tracing hoặc tenant có thể đi kèm nếu đã được ánh xạ metadata. Không nên đặt code parse JSON lặp lại ở mọi `ServiceActivator` khi codec tại biên đã cung cấp DTO phù hợp.

Một hợp đồng rõ ràng cho route `orders.create` nên ghi:

| Mục | Giá trị ví dụ |
| --- | --- |
| Route | `orders.create` |
| Interaction | Request-response |
| Data MIME type | `application/json` |
| Request DTO | `CreateOrder(orderId, quantity)` |
| Reply DTO | `OrderReceipt(orderId, state)` |
| Metadata MIME type | `message/x.rsocket.composite-metadata.v0` |
| Quy tắc kiểm tra | `orderId` không rỗng, `quantity > 0` |
| Lỗi hợp đồng | Codec thất bại, JSON sai, dữ liệu không hợp lệ |
| Tương thích | Quy tắc bổ sung/đổi tên field và phiên bản DTO |

Nếu nâng cấp payload từ JSON sang Protobuf, đó là thay đổi hợp đồng **codec, schema và SETUP**, không chỉ là đổi tên route. Với nhiều client phát hành độc lập, có thể duy trì kết nối/endpoint tương thích cho phiên bản cũ trong giai đoạn chuyển đổi.

## 10. Kiểm thử đúng trọng tâm codec

Một bộ test có ích nên kiểm tra cả bytes qua RSocket và giá trị mà IntegrationFlow thực sự nhận:

1. **JSON hợp lệ:** gửi `CreateOrder("ORD-102", 3)` và nhận `OrderReceipt` đúng field; xác nhận handler nhận DTO, không nhận chuỗi JSON thô.
2. **Payload thiếu field bắt buộc:** gửi JSON không có `orderId`; xác định rõ validation/mapper cho phép null hay từ chối, rồi kiểm tra kết quả mong muốn.
3. **JSON sai kiểu:** gửi `quantity: "abc"`; kiểm tra lỗi giải mã và bảo đảm IntegrationFlow không chạy nghiệp vụ tạo đơn.
4. **JSON hỏng cú pháp:** gửi bytes không phải JSON hợp lệ dưới data MIME type `application/json`; kiểm tra phản hồi lỗi từ decoder.
5. **MIME type không hỗ trợ:** dùng requester khai báo `text/plain` rồi gửi DTO chỉ có JSON codec; kiểm tra lỗi encode hoặc decode phù hợp.
6. **Phản hồi sai schema:** làm client yêu cầu `OrderReceipt` trong khi server trả cấu trúc không tương thích; kiểm tra lỗi decode phía client.
7. **Định dạng khác JSON:** nếu hỗ trợ vendor JSON hoặc Protobuf, gửi payload thật qua kết nối với SETUP tương ứng; xác nhận đọc được trên cả hai phía.
8. **Giới hạn kích thước:** kiểm tra payload lớn và xác định hành vi khi vượt giới hạn codec/buffer đã cấu hình.

Khi dùng Reactor, `StepVerifier` giúp kiểm tra tín hiệu `onNext`, `onComplete` và `onError`. Các test chỉ gọi thẳng handler Java **không kiểm chứng được** việc encode/decode và khai báo data MIME type. Ít nhất một nhóm integration test cần đi qua `RSocketRequester` và responder cấu hình tương tự production.

## 11. Troubleshooting: lỗi thường gặp

| Biểu hiện | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| Client báo không encode được `CreateOrder` | Thiếu JSON encoder hoặc data MIME type sai | Kiểm tra `RSocketStrategies`, MIME ở builder và Jackson trên classpath |
| Server báo không decode được request | JSON hỏng, sai MIME, thiếu decoder hoặc DTO không tương thích | Kiểm tra bytes, schema, signature của `@MessageMapping` và codec |
| Server xử lý được nhưng client lỗi ở `retrieveMono` | Reply không khớp `OrderReceipt` hoặc thiếu decoder ở client | Kiểm tra response schema và kiểu đích |
| `orders.create` không tìm thấy handler | Route/metadata routing sai | Kiểm tra route và metadata MIME type; lỗi này khác lỗi JSON |
| Dữ liệu vào flow là `String` thay vì `CreateOrder` | Handler nhận String hoặc có bước chuyển đổi khác | Định nghĩa kiểu tham số chính xác và kiểm tra điểm chuyển DTO sang channel |
| Một client dùng JSON thành công, client khác thất bại | SETUP MIME, codec, schema hoặc phiên bản DTO không thống nhất | So sánh cấu hình hai client và contract với server |
| Payload lớn gây lỗi bộ nhớ hoặc buffer | Thiếu giới hạn kích thước hoặc thiết kế gom data | Áp giới hạn ở codec/transports, dùng stream/phân mảnh nghiệp vụ thích hợp |
| Gửi `application/x-protobuf` nhưng kết quả không đọc được | Chưa cài codec/schema Protobuf phù hợp | Đăng ký codec thực sự hỗ trợ Protobuf và kiểm tra schema hai bên |

Khi khoanh vùng lỗi, đi theo thứ tự: **SETUP MIME → encoder phía gửi → bytes trên wire → decoder phía nhận → kiểu DTO → IntegrationFlow → encoder reply → decoder client**. Phân biệt lỗi payload với lỗi route, metadata và validation để không sửa nhầm tầng.

Không nên log toàn bộ bytes của payload trong production nếu có thông tin cá nhân, token hoặc dữ liệu nhạy cảm. Có thể log route, MIME type, correlation ID, độ dài payload và mã lỗi đã loại bỏ dữ liệu bí mật.

## 12. Bài tập thực hành

### Bài A — Quan sát DTO tại biên RSocket

Hoàn thiện ví dụ `orders.create`, thêm một phép kiểm tra payload mà `IntegrationFlow` thực nhận là `CreateOrder` và `quantity == 3`. So sánh với kết quả khi handler tạm thời nhận dữ liệu dạng `String`. Giải thích tại sao kiểu tham số lại ảnh hưởng đến việc decode.

### Bài B — Bổ sung route văn bản

Tạo `echo.text` với requester dùng `text/plain` và trả về một `String`. Viết test cho kết nối JSON và kết nối text độc lập. Giải thích vì sao không thể dùng cùng một kết nối RSocket hiện có để tùy ý đổi `dataMimeType` cho từng route theo cơ chế SETUP mặc định.

### Bài C — Lỗi hợp đồng và tương thích

Viết test cố tình gửi JSON sai kiểu, gửi DTO với MIME không phù hợp và yêu cầu response class sai schema. Với mỗi test, ghi rõ lỗi xảy ra **trước khi gửi**, **trong bước decode tại server**, **trong IntegrationFlow** hay **khi client decode reply**.

## 13. Những điểm cần nhớ

- RSocket truyền bytes; **codec** chuyển đổi giữa bytes và giá trị ứng dụng.
- **Data MIME type** được khai báo trong SETUP và định hướng cách diễn giải data của kết nối. **Metadata MIME type** quy định cách diễn giải route và metadata khác.
- JSON DTO đi qua encoder ở bên gửi và decoder ở bên nhận; reply có chiều mã hóa/giải mã ngược lại.
- Spring RSocket dùng `RSocketStrategies` để quản lý codec. Việc đặt đúng MIME type chưa đủ nếu hai đầu thiếu codec hoặc schema không tương thích.
- Spring Integration nên nhận payload đã giải mã ở biên RSocket, rồi tập trung xử lý nghiệp vụ qua `MessageChannel` và `IntegrationFlow`. Kiểm thử cần đi qua RSocket thật để phát hiện lỗi codec mà unit test handler thuần Java không thấy.
