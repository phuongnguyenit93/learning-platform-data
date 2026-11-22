# Payload gồm data và metadata

## Mục tiêu

Trong RSocket, mỗi message mang một **payload** gồm hai phần độc lập: **data** và **metadata**. Data thường chứa nội dung nghiệp vụ mà ứng dụng muốn gửi hoặc nhận, còn metadata mô tả cách định tuyến, xác thực, tracing, tenant hoặc ngữ cảnh xử lý.

Ví dụ, một client có thể gửi yêu cầu tạo đơn hàng như sau:

- Data: `{"productId":"P-100","quantity":2}`
- Metadata định tuyến: `orders.create`
- Metadata xác thực: token của người dùng
- Metadata tenant: mã tenant đang hoạt động

Tách data và metadata giúp nội dung nghiệp vụ giữ cấu trúc riêng, trong khi thông tin điều khiển và ngữ cảnh có thể được mở rộng độc lập. Spring hỗ trợ mã hóa và giải mã cả hai phần thông qua `RSocketRequester`, `RSocketStrategies`, `Encoder` và `Decoder`.

## 1. Cấu trúc payload của RSocket

Trong Java, payload ở tầng giao thức được biểu diễn bởi `io.rsocket.Payload`. Một payload có hai vùng dữ liệu:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Data | Nội dung chính của message | DTO đơn hàng, JSON, chuỗi hoặc bytes |
| Metadata | Thông tin mô tả/điều khiển message | Route, token, tracing, tenant |

Một message có thể chỉ có data, có cả data và metadata, hoặc trong một số trường hợp chỉ cần metadata. Metadata không bắt buộc phải xuất hiện trong mọi request.

RSocket không quy định mọi ứng dụng phải dùng JSON cho cả hai phần. Data và metadata có thể sử dụng định dạng khác nhau. Ví dụ data là JSON, metadata định tuyến dùng định dạng routing chuẩn của RSocket, còn metadata xác thực dùng MIME type riêng.

Ở tầng Java thấp, `Payload` cung cấp data và metadata dưới dạng buffer. Ở tầng Spring, `RSocketRequester` cho phép truyền object Java và để các codec xử lý việc chuyển đổi.

## 2. MIME type của data và metadata

RSocket khai báo MIME type cho data và metadata trong frame `SETUP`. Hai MIME type này áp dụng cho kết nối và được hai phía sử dụng để diễn giải nội dung của các payload trên kết nối đó.

- **Data MIME type** cho biết cách diễn giải phần data, ví dụ `application/json`, `text/plain` hoặc một MIME type của Protobuf.
- **Metadata MIME type** cho biết cách diễn giải phần metadata, ví dụ một định dạng metadata đơn hoặc composite metadata.

Khi dùng composite metadata, metadata MIME type thường là:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

Composite metadata cho phép một payload chứa nhiều metadata entry, mỗi entry có MIME type riêng. Ví dụ:

| Metadata entry | MIME type | Giá trị |
|---|---|---|
| Routing | `message/x.rsocket.routing.v0` | `orders.create` |
| Authentication | `message/x.rsocket.authentication.bearer.v0` | Bearer token |
| Tenant context | `application/vnd.example.tenant+json` | JSON tenant context |
| Tracing | MIME type tracing đã thống nhất | Trace context |

Nếu không dùng composite metadata, metadata MIME type của kết nối mô tả định dạng metadata chung. Khi đó không thể tùy ý trộn nhiều định dạng metadata độc lập trong cùng payload theo cách composite metadata hỗ trợ.

Thông thường, Spring đặt data MIME type theo decoder đầu tiên được cấu hình và mặc định dùng composite metadata cho metadata MIME type. Chỉ thay đổi mặc định khi cả client và server có thỏa thuận rõ ràng về định dạng.

## 3. Data và metadata khác nhau ở đâu?

Hãy xét yêu cầu tìm các đơn hàng của một tenant:

~~~text
Data:
{
  "status": "PAID",
  "from": "2026-11-01",
  "to": "2026-11-07"
}

Metadata:
  route = orders.search
  tenant = {"tenantId":"acme"}
  trace = {"traceId":"..."}
~~~

Data mô tả điều kiện tìm kiếm. Route chỉ ra responder cần xử lý yêu cầu nào. Tenant và trace cung cấp ngữ cảnh cho việc kiểm tra quyền, chọn dữ liệu và quan sát hệ thống.

Một số nguyên tắc thiết kế:

- Đặt trường nghiệp vụ mà handler cần xử lý trong data.
- Đặt thông tin định tuyến và ngữ cảnh giao thức trong metadata.
- Không dùng metadata thay cho kiểm tra quyền. Token hoặc tenant ID chỉ có ý nghĩa khi server xác minh và ràng buộc với danh tính đã xác thực.
- Không gửi cùng một thông tin ở cả data và metadata nếu không có lý do rõ ràng; hai bản sao có thể không nhất quán.
- Thống nhất schema, MIME type và phiên bản metadata giữa requester và responder.

Metadata không tự động an toàn hoặc đáng tin cậy chỉ vì nó nằm ngoài data. Cả hai phần đều đến từ phía gửi và phải được kiểm tra trước khi sử dụng.

## 4. Gửi data bằng RSocketRequester

`RSocketRequester` là API cấp cao của Spring để gửi và nhận object mà không phải tự quản lý `ByteBuf` hay tạo `Payload` thủ công.

Ví dụ gửi một DTO:

~~~java
import java.math.BigDecimal;

public record CreateOrderRequest(
        String productId,
        int quantity,
        BigDecimal unitPrice
) {
}
~~~

Gửi request tới route `orders.create`:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.messaging.rsocket.RSocketRequester;

public class OrderClient {

    private final RSocketRequester requester;

    public OrderClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<OrderReceipt> createOrder() {
        CreateOrderRequest request = new CreateOrderRequest(
                "P-100",
                2,
                new BigDecimal("125.50")
        );

        return requester
                .route("orders.create")
                .data(request)
                .retrieveMono(OrderReceipt.class);
    }
}
~~~

Các bước:

1. `route("orders.create")` khai báo route trong metadata của request.
2. `data(request)` cung cấp object nghiệp vụ cần gửi.
3. `retrieveMono(OrderReceipt.class)` khai báo kiểu response mong đợi và chọn kiểu tương tác Request-Response.

Spring sử dụng encoder phù hợp trong `RSocketStrategies` để chuyển DTO thành bytes. Phía responder sử dụng decoder tương ứng để tạo object. Client và server cần thống nhất data MIME type và schema.

Nếu request không có nội dung data, có thể bỏ qua `data(...)` và chỉ gửi route cùng metadata cần thiết.

## 5. Thêm metadata riêng cho từng request

Khi metadata MIME type của kết nối là composite metadata, có thể thêm nhiều entry độc lập bằng `metadata(value, mimeType)`.

Ví dụ thêm bearer token và tenant context:

~~~java
import org.springframework.util.MimeType;
import reactor.core.publisher.Mono;

public Mono<OrderReceipt> createOrderWithContext(
        RSocketRequester requester,
        CreateOrderRequest request,
        String accessToken,
        TenantContext tenantContext) {

    MimeType bearerMimeType = MimeType.valueOf(
            "message/x.rsocket.authentication.bearer.v0");

    MimeType tenantMimeType = MimeType.valueOf(
            "application/vnd.example.tenant+json");

    return requester
            .route("orders.create")
            .metadata(accessToken, bearerMimeType)
            .metadata(tenantContext, tenantMimeType)
            .data(request)
            .retrieveMono(OrderReceipt.class);
}
~~~

Trong ví dụ:

- `route` được Spring mã hóa thành routing metadata entry.
- `accessToken` được mã hóa với MIME type bearer authentication.
- `tenantContext` được mã hóa bằng MIME type JSON riêng của ứng dụng.
- `request` được mã hóa thành data.

Mỗi giá trị metadata phải có encoder phù hợp trong `RSocketStrategies`. Nếu metadata MIME type của kết nối không phải composite, việc thêm nhiều metadata entry với MIME type riêng không hoạt động theo cách trên.

Không tự tạo định dạng token tùy ý rồi coi đó là xác thực. Nếu dùng Spring Security RSocket, hãy sử dụng cơ chế authentication metadata mà security configuration hỗ trợ và xác minh token ở phía server.

## 6. Cấu hình MIME type trong SETUP

`RSocketRequester.Builder` cho phép khai báo data MIME type và metadata MIME type khi thiết lập kết nối:

~~~java
import org.springframework.util.MimeType;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(MimeType.valueOf("application/json"))
        .metadataMimeType(MimeType.valueOf(
                "message/x.rsocket.composite-metadata.v0"))
        .tcp("localhost", 7000);
~~~

Hai cấu hình này được gửi trong frame `SETUP` và áp dụng cho kết nối:

- `dataMimeType(...)` khai báo định dạng data.
- `metadataMimeType(...)` khai báo định dạng metadata.

Đoạn code trên tạo requester để sử dụng kết nối TCP. Có thể dùng `websocket(URI)` khi server mở RSocket qua WebSocket.

Nếu không chỉ định data MIME type, Spring suy ra từ decoder đã cấu hình. Metadata mặc định thường là composite metadata. Hãy xác nhận cấu hình hai phía tương thích; thay MIME type ở một phía mà không thay phía còn lại có thể khiến giải mã thất bại.

`setupData(...)`, `setupRoute(...)` và `setupMetadata(...)` là các tùy chọn để thêm nội dung vào chính SETUP frame. Đây là thông tin ở cấp kết nối, khác với data và metadata được gửi trong từng request.

## 7. Cấu hình Encoder và Decoder qua RSocketStrategies

`RSocketStrategies` quản lý encoder, decoder, metadata extractor và các thành phần chuyển đổi dùng bởi RSocket. Đây là nơi cấu hình codec để hai phía có thể chuyển đổi cùng một schema.

Ví dụ đăng ký Jackson JSON encoder và decoder trong ứng dụng có module `spring-web`:

~~~java
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.http.codec.json.JacksonJsonEncoder;
import org.springframework.http.codec.json.JacksonJsonDecoder;

RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new JacksonJsonEncoder()))
        .decoders(decoders -> decoders.add(new JacksonJsonDecoder()))
        .build();

RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(strategies)
        .tcp("localhost", 7000);
~~~

Các codec JSON cụ thể phụ thuộc phiên bản Spring và Jackson đang dùng. Spring Framework 7 sử dụng các codec Jackson 3 tương ứng; Spring Framework 6.x thường dùng codec Jackson 2. Không trộn Jackson 2 và Jackson 3 tùy tiện trong cùng một cấu hình codec.

Theo mặc định, các codec cơ bản từ `spring-core` hỗ trợ `String`, `byte[]` và `ByteBuffer`. Thêm `spring-web` để sử dụng các codec JSON, CBOR hoặc các định dạng khác được hỗ trợ.

Có thể dùng chung một `RSocketStrategies` cho requester và responder trong cùng ứng dụng để giảm nguy cơ hai phía cấu hình codec khác nhau.

## 8. Đọc metadata ở responder bằng MetadataExtractor

Metadata nhận được ở tầng RSocket Java vẫn là dữ liệu đã mã hóa. Spring dùng `MetadataExtractor` để giải mã các metadata entry và ánh xạ chúng thành các key-value có thể truy cập trong handler.

`DefaultMetadataExtractor` hỗ trợ routing metadata chuẩn `message/x.rsocket.routing.v0` sẵn có, lưu route dưới key `route`. Các MIME type khác cần đăng ký decoder và cách ánh xạ.

Ví dụ đăng ký metadata tenant:

~~~java
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeType;

MimeType tenantMimeType = MimeType.valueOf(
        "application/vnd.example.tenant+json");

RSocketStrategies strategies = RSocketStrategies.builder()
        .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                        tenantMimeType,
                        TenantContext.class,
                        "tenant"))
        .build();
~~~

Ví dụ trên giả định decoder hỗ trợ `TenantContext` đã được đăng ký trong strategies. Khi giải mã thành công, metadata entry được đưa vào map header dưới key `tenant`.

Responder có thể nhận metadata bằng `@Header`:

~~~java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    @MessageMapping("orders.create")
    public Mono<OrderReceipt> create(
            @Payload CreateOrderRequest request,
            @Header("tenant") TenantContext tenant) {

        return orderService.createOrder(request, tenant);
    }
}
~~~

`@Payload` nhận data đã được giải mã thành DTO. `@Header("tenant")` nhận metadata đã được extractor giải mã và ánh xạ. Route được xử lý riêng bởi cơ chế routing, không phải data body.

Nếu metadata MIME type không được đăng ký decoder, hoặc body metadata không hợp lệ, việc giải mã có thể thất bại trước khi phương thức handler được gọi.

## 9. Composite metadata và routing metadata

Composite metadata là một định dạng container cho nhiều metadata entry. Mỗi entry có MIME type riêng và nội dung riêng. Điều này cho phép một payload đồng thời chứa route, authentication, tracing và tenant context.

Hai MIME type quan trọng:

~~~text
message/x.rsocket.composite-metadata.v0
message/x.rsocket.routing.v0
~~~

- `message/x.rsocket.composite-metadata.v0` cho biết metadata của payload là composite.
- `message/x.rsocket.routing.v0` biểu diễn route của request.

Với Spring `RSocketRequester`, khi dùng composite metadata (mặc định), gọi `route("orders.create")` sẽ tạo routing metadata entry. Không cần tự nối route vào data.

Nếu muốn thêm một metadata entry khác, cần truyền MIME type cho giá trị:

~~~java
requester.route("orders.search")
        .metadata(tenantContext, tenantMimeType)
        .data(searchCriteria)
        .retrieveFlux(OrderSummary.class);
~~~

Nếu route hoặc metadata được đặt sai phần, responder có thể không tìm được handler hoặc không giải mã được metadata. Ví dụ, gửi route như một field JSON trong data không tương đương với routing metadata của giao thức.

## 10. Data và metadata ở tầng Payload Java thấp

Khi làm việc trực tiếp với `io.rsocket.Payload`, ứng dụng nhìn thấy data và metadata dưới dạng `ByteBuf`. API cấp thấp hữu ích khi tích hợp trực tiếp với RSocket Java hoặc cần tối ưu thao tác buffer.

Các thao tác thường gặp:

- Đọc vùng data bằng `payload.data()`.
- Đọc vùng metadata bằng `payload.metadata()` khi payload có metadata.
- Kiểm tra metadata có tồn tại bằng `payload.hasMetadata()`.
- Tạo payload mới bằng các API của RSocket hoặc tiện ích Spring như `PayloadUtils.createPayload(...)`.

`Payload` sử dụng reference counting vì có thể giữ buffer Netty bên dưới. Khi ứng dụng tự quản lý payload ở tầng thấp, phải tuân thủ vòng đời buffer: không sử dụng sau khi đã release; nếu cần giữ lại qua ranh giới xử lý bất đồng bộ, phải retain đúng cách và release đúng số lần. Không lưu tham chiếu ByteBuf để sử dụng tùy ý sau khi payload đã được giải phóng.

Spring `RSocketRequester` và các annotated responder thường phù hợp hơn cho mã ứng dụng vì encoder/decoder quản lý việc chuyển đổi và framework xử lý vòng đời payload. Chỉ dùng API raw khi có lý do kỹ thuật rõ ràng.

## 11. Metadata cấp kết nối và metadata cấp request

Không phải metadata nào cũng thuộc một request:

| Phạm vi | Cách gửi | Mục đích |
|---|---|---|
| Kết nối | `setupMetadata(...)` trong SETUP | Ngữ cảnh ban đầu hoặc thông tin bảo mật ở cấp kết nối |
| Request | `metadata(value, mimeType)` trên RequestSpec | Route, token, tenant hoặc tracing cho request cụ thể |
| Metadata push | `sendMetadata(...)` | Thông báo metadata ở cấp kết nối, không gắn với một request riêng |

`METADATA_PUSH` là frame riêng của RSocket. Ở phía responder, `@ConnectMapping` có thể xử lý SETUP và các metadata push tiếp theo. Không nhầm `sendMetadata()` với `metadata(...)` trên một request: một bên là thông báo ở cấp kết nối, bên kia là metadata của payload request.

Không gửi token trong mọi request nếu hệ thống dùng xác thực gắn với kết nối và có chính sách làm mới phù hợp. Ngược lại, nếu token có thể thay đổi theo request, phải xác định rõ cơ chế metadata và xác thực ở server.

## 12. Kiểm thử data và metadata

Một integration test nên xác nhận cả hai phần đã được mã hóa và giải mã đúng:

1. Khởi động RSocket server với route `orders.create`.
2. Cấu hình client và server dùng cùng data MIME type và metadata MIME type.
3. Đăng ký decoder cho DTO data và metadata tenant.
4. Client gửi route, data DTO và tenant metadata.
5. Server xác nhận route đúng, data đúng field và metadata được ánh xạ thành đúng key.
6. Server trả response DTO; client xác nhận response được decode đúng.
7. Thử metadata MIME type không hỗ trợ và payload sai schema để xác nhận lỗi được quan sát rõ ràng.

Ngoài happy path, nên kiểm tra trường hợp không có metadata, metadata rỗng, sai MIME type, thiếu route và token không hợp lệ. Không chỉ kiểm tra object cuối cùng; hãy xác minh cả MIME type, route và metadata mapping vì đây là các phần của giao thức.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Server không tìm thấy handler | Route bị đặt trong data thay vì routing metadata | Dùng `route(...)` của requester |
| Data decode lỗi | Data MIME type không khớp encoder/decoder | Thống nhất MIME type và codec hai phía |
| Metadata không xuất hiện trong `@Header` | Chưa đăng ký MIME type trong MetadataExtractor | Thêm `metadataToExtract` và decoder phù hợp |
| Chỉ route được giải mã | Default extractor chỉ tự hỗ trợ routing metadata phổ biến | Đăng ký extractor cho metadata custom |
| Metadata composite không parse được | Một phía dùng MIME type không composite hoặc entry sai định dạng | Kiểm tra `metadataMimeType` và MIME type từng entry |
| JSON tenant metadata không deserialize | Chưa có decoder cho TenantContext hoặc JSON mapper không tương thích | Đăng ký decoder phù hợp trong RSocketStrategies |
| Token có trong metadata nhưng vẫn bị từ chối | Metadata chỉ là dữ liệu; server chưa cấu hình authentication tương ứng | Cấu hình Spring Security RSocket và xác minh token |
| Handler nhận sai kiểu dữ liệu | `getPayloadType` hoặc kiểu decoder không đúng | Khai báo kiểu đích và codec nhất quán |

## Ghi nhớ

- RSocket payload có hai phần: data và metadata.
- Data chứa nội dung nghiệp vụ; metadata chứa route, token, tenant, tracing hoặc ngữ cảnh giao thức.
- MIME type của data và metadata được khai báo trong SETUP và áp dụng cho kết nối.
- Composite metadata cho phép nhiều metadata entry có MIME type độc lập.
- Spring `RSocketRequester` cung cấp `data(...)`, `metadata(...)` và `route(...)` để xây dựng payload cấp cao.
- `RSocketStrategies` quản lý encoder, decoder và metadata extractor.
- `DefaultMetadataExtractor` tự nhận biết routing metadata; metadata custom cần đăng ký.
- Metadata phải được xác thực và kiểm tra như mọi input khác.
- `Payload` raw dùng reference-counted buffers; phải quản lý retain/release đúng cách.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/7.0/rsocket.html)
- [RSocketRequester API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [MetadataExtractor API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractor.html)
- [DefaultMetadataExtractor API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/rsocket/DefaultMetadataExtractor.html)
- [PayloadUtils API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/rsocket/PayloadUtils.html)
