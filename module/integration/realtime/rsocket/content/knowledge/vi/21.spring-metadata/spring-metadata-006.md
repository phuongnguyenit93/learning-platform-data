# Truyền đồng thời route, thông tin xác thực và mã tương quan

## Mục tiêu bài học

Một request RSocket thường cần nhiều thông tin ngoài payload nghiệp vụ. Server cần biết route nào sẽ xử lý request, người gửi đã được xác thực ra sao và request thuộc trace hoặc giao dịch nào. RSocket đưa những thông tin này vào phần **metadata** của payload.

Trong Spring, `RSocketRequester` cung cấp API để tạo route và thêm metadata. Khi dùng **composite metadata**, một request có thể chứa nhiều mục metadata độc lập, mỗi mục có MIME type riêng.

Sau bài này, bạn có thể:

- Phân biệt route metadata, composite metadata và custom metadata.
- Giải thích vai trò của MIME type ở cấp kết nối và ở từng mục composite.
- Dùng `route()` để định tuyến tới handler Spring.
- Thêm token xác thực và correlation metadata vào cùng request.
- Cấu hình encoder, decoder và `MetadataExtractor`.
- Đọc custom metadata bằng `@Header` trong handler.
- Phân biệt metadata của từng request với metadata trong SETUP của kết nối.
- Tránh nhầm metadata với data payload, HTTP header hoặc cơ chế authorization.

## Metadata nằm ở đâu trong một request?

Một RSocket message có thể chứa hai phần:

- **Data:** payload nghiệp vụ, ví dụ nội dung tạo đơn hàng hoặc dữ liệu đo cảm biến.
- **Metadata:** thông tin mô tả hoặc điều khiển việc xử lý payload, ví dụ route, thông tin xác thực, correlation ID hoặc tracing context.

Data và metadata có MIME type riêng. MIME type của data và metadata được khai báo trong SETUP và áp dụng cho kết nối. Khi dùng composite metadata, từng mục metadata bên trong còn có MIME type riêng.

Ví dụ một request tạo đơn hàng:

- Data: `CreateOrder` chứa mã sản phẩm và số lượng.
- Route metadata: `orders.create` để chọn handler.
- Authentication metadata: bearer token để server xác thực người gọi.
- Custom correlation metadata: correlation ID để nối log và trace.

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    R[REQUEST_RESPONSE frame] --> P[RSocket Payload]
    P --> D[Data: CreateOrder]
    P --> M[Metadata]
    M --> C[Composite metadata]
    C --> RT[Routing entry: orders.create]
    C --> AU[Authentication entry: bearer token]
    C --> TR[Custom entry: correlation ID]
~~~

Metadata không thay thế Data. Không nên nhét toàn bộ object nghiệp vụ vào metadata chỉ vì Spring có API `metadata()`. Data dành cho nội dung mà handler xử lý; metadata dành cho thông tin định tuyến, xác thực, tracing và ngữ cảnh của request.

## Route metadata: chọn handler đích

Route là địa chỉ logic mà requester dùng để chọn responder. Trong Spring, route thường tương ứng với giá trị của `@MessageMapping`.

Ví dụ server:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

record CreateOrder(String sku, int quantity) {}
record OrderResult(String orderId, String status) {}

@Controller
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.create")
    Mono<OrderResult> create(CreateOrder request) {
        return orderService.create(request);
    }
}
~~~

Client chọn handler bằng `route()`:

~~~java
Mono<OrderResult> result = requester
    .route("orders.create")
    .data(new CreateOrder("SKU-42", 2))
    .retrieveMono(OrderResult.class);
~~~

`route("orders.create")` tạo routing metadata theo định dạng chuẩn của RSocket. MIME type của routing metadata là:

```text
message/x.rsocket.routing.v0
```

Trong composite metadata, route là một entry có MIME type này và nội dung là route string. Spring tự encode route khi gọi `route()`; thông thường không cần tự tạo ByteBuf hoặc ghép metadata bằng tay.

Route chỉ phục vụ định tuyến. Biết route `orders.create` không có nghĩa client có quyền tạo đơn hàng. Server vẫn phải xác thực danh tính và kiểm tra authorization cho thao tác tương ứng.

### Route template và biến

Spring hỗ trợ route có biến:

~~~java
Mono<OrderResult> result = requester
    .route("orders.{operation}", "create")
    .data(new CreateOrder("SKU-42", 2))
    .retrieveMono(OrderResult.class);
~~~

Server có thể ánh xạ pattern:

~~~java
import org.springframework.messaging.handler.annotation.DestinationVariable;

@MessageMapping("orders.{operation}")
Mono<OrderResult> handle(
        @DestinationVariable("operation") String operation,
        CreateOrder request) {
    return orderService.execute(operation, request);
}
~~~

Với route template, Spring định dạng biến thành chuỗi. Nếu giá trị biến chứa dấu chấm, Spring requester escape dấu chấm để tránh làm thay đổi ranh giới giữa các segment của route. Hãy dùng route có cấu trúc rõ ràng và không tự nối chuỗi tùy tiện từ dữ liệu chưa kiểm tra.

## Composite metadata: nhiều mục metadata trong cùng một request

Composite metadata là định dạng metadata chuẩn của RSocket cho phép ghép nhiều entry độc lập vào cùng một vùng metadata. Mỗi entry có MIME type và nội dung riêng.

MIME type của toàn bộ vùng metadata composite là:

```text
message/x.rsocket.composite-metadata.v0
```

Ví dụ các entry trong một request:

| Entry | MIME type | Nội dung |
|---|---|---|
| Route | `message/x.rsocket.routing.v0` | `orders.create` |
| Authentication | `message/x.rsocket.authentication.v0` | Bearer token theo extension xác thực RSocket |
| Correlation | `application/vnd.acme.correlation+json` | JSON chứa correlation ID và tenant ID |

Composite metadata không phải là một object JSON lớn chứa tất cả trường. Nó là một chuỗi entry có framing riêng; mỗi entry tự khai báo MIME type để receiver biết cách diễn giải nội dung.

Ở mức khái niệm:

~~~text
Composite metadata
├── Entry 1
│   ├── MIME: message/x.rsocket.routing.v0
│   └── Value: orders.create
├── Entry 2
│   ├── MIME: message/x.rsocket.authentication.v0
│   └── Value: bearer token
└── Entry 3
    ├── MIME: application/vnd.acme.correlation+json
    └── Value: {"correlationId":"...","tenantId":"..."}
~~~

Spring Framework mặc định chọn composite metadata cho `RSocketRequester.Builder`. Khi đó:

- `route(...)` thêm routing entry.
- `metadata(value, mimeType)` thêm một entry khác.
- Có thể gọi `metadata()` nhiều lần để thêm các loại metadata khác nhau.

Đây là cơ chế cho phép route, thông tin xác thực và correlation ID cùng tồn tại trong một request.

## Custom metadata: dữ liệu phụ trợ do ứng dụng định nghĩa

Custom metadata là metadata theo hợp đồng riêng của ứng dụng. Ví dụ:

- Correlation ID hoặc trace context.
- Tenant ID hoặc thông tin phân vùng.
- Locale hoặc phiên bản hợp đồng.
- Feature context hoặc thông tin định tuyến nội bộ bổ sung.

Mỗi custom metadata nên có MIME type rõ ràng. Ví dụ:

```text
application/vnd.acme.correlation+json
```

Tên MIME type nên có namespace của tổ chức hoặc ứng dụng, mô tả định dạng và có thể thể hiện phiên bản nếu schema thay đổi. Tránh dùng một MIME type chung như `application/octet-stream` cho nhiều loại metadata không liên quan, vì receiver sẽ khó chọn decoder đúng.

Ví dụ record:

~~~java
record CorrelationMetadata(
    String correlationId,
    String tenantId
) {}
~~~

Client thêm metadata:

~~~java
MimeType correlationMimeType =
    MimeTypeUtils.parseMimeType(
        "application/vnd.acme.correlation+json"
    );

Mono<OrderResult> result = requester
    .route("orders.create")
    .metadata(
        new CorrelationMetadata("corr-8f31", "tenant-42"),
        correlationMimeType
    )
    .data(new CreateOrder("SKU-42", 2))
    .retrieveMono(OrderResult.class);
~~~

Custom metadata cần có encoder ở sender và decoder tương ứng ở receiver. Chỉ truyền một object Java vào `metadata()` không làm cho peer tự hiểu được class đó. Hai phía phải thống nhất MIME type, serialization format và schema.

## Truyền đồng thời route, token và correlation ID

Đây là tình huống tổng hợp của bài học. Một request tạo đơn hàng có thể mang ba entry metadata và một phần Data:

1. Route `orders.create`.
2. Bearer token theo RSocket Authentication Metadata Extension.
3. Correlation metadata theo MIME type riêng của ứng dụng.
4. Data chứa nội dung đơn hàng.

Ví dụ client:

~~~java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

class OrderClient {

    private static final MimeType AUTH_MIME =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
        );

    private static final MimeType CORRELATION_MIME =
        MimeTypeUtils.parseMimeType(
            "application/vnd.acme.correlation+json"
        );

    private final RSocketRequester requester;

    OrderClient(RSocketRequester requester) {
        this.requester = requester;
    }

    Mono<OrderResult> create(
            String accessToken,
            String correlationId,
            String tenantId,
            CreateOrder command) {

        BearerTokenMetadata token =
            new BearerTokenMetadata(accessToken);
        CorrelationMetadata correlation =
            new CorrelationMetadata(correlationId, tenantId);

        return requester
            .route("orders.create")
            .metadata(token, AUTH_MIME)
            .metadata(correlation, CORRELATION_MIME)
            .data(command)
            .retrieveMono(OrderResult.class);
    }
}
~~~

Trong ví dụ:

- `route()` tạo routing metadata.
- `metadata(token, AUTH_MIME)` thêm entry xác thực theo MIME type chuẩn.
- `metadata(correlation, CORRELATION_MIME)` thêm custom metadata của ứng dụng.
- `data(command)` encode payload nghiệp vụ.
- `retrieveMono()` nhận một response.

Cần bảo đảm `RSocketRequester` dùng `RSocketStrategies` có encoder cho `CorrelationMetadata`. Nếu dùng Spring Security để xác thực bearer token, server cũng phải cấu hình RSocket Security và JWT decoder phù hợp. Việc gửi token trong metadata không tự xác thực token nếu server chưa có cơ chế kiểm tra.

## Cấu hình encoder, decoder và MetadataExtractor

Sender cần encoder để chuyển object custom metadata thành byte. Receiver cần decoder để giải mã byte thành kiểu Java và một quy tắc để đặt giá trị đã giải mã vào metadata map.

Ví dụ cấu hình strategies:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

@Configuration
class RSocketMetadataConfiguration {

    private static final MimeType CORRELATION_MIME =
        MimeTypeUtils.parseMimeType(
            "application/vnd.acme.correlation+json"
        );

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
            .encoders(encoders ->
                encoders.add(new Jackson2JsonEncoder())
            )
            .decoders(decoders ->
                decoders.add(new Jackson2JsonDecoder())
            )
            .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                    CORRELATION_MIME,
                    CorrelationMetadata.class,
                    "correlation"
                )
            )
            .build();
    }
}
~~~

Ở đây:

- Jackson encoder serialize `CorrelationMetadata` thành JSON.
- Jackson decoder deserialize JSON thành `CorrelationMetadata`.
- `metadataToExtract(..., "correlation")` đăng ký tên mà handler dùng để lấy metadata.
- MIME type custom phải giống nhau giữa sender và receiver.

`RSocketStrategies` dùng cho cả encoding/decoding và metadata extraction. Trong ứng dụng Spring Boot, có thể khai báo bean strategies để requester builder và RSocket message handler sử dụng cùng cấu hình. Nếu cấu hình client và server ở hai ứng dụng khác nhau, hãy duy trì hợp đồng MIME type và schema tương thích.

Ở client, truyền cùng strategies vào builder trước khi tạo requester:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .tcp("orders-service", 7000);
~~~

Trong ứng dụng Spring Boot, builder được auto-configure có thể đã sử dụng bean `RSocketStrategies` của ứng dụng. Khi tự tạo builder, truyền strategies rõ ràng để custom metadata có encoder tương ứng.

### MetadataExtractor xử lý route như thế nào?

`DefaultMetadataExtractor` có hỗ trợ sẵn routing MIME type:

```text
message/x.rsocket.routing.v0
```

Nó giải mã route thành String và lưu dưới key `route`. Vì vậy, khi dùng `@MessageMapping`, Spring có thể định tuyến request mà không cần bạn tự đăng ký decoder cho route.

Với MIME type khác, cần đăng ký decoder và tên metadata như ví dụ `metadataToExtract`. Nếu custom metadata là một Map JSON cần tách thành nhiều header, có thể dùng overload nhận mapper để đưa từng trường vào output map.

## Đọc custom metadata trong handler bằng @Header

Sau khi đăng ký metadata extractor với tên `correlation`, handler có thể nhận metadata đã giải mã bằng `@Header`:

~~~java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.create")
    Mono<OrderResult> create(
            @Payload CreateOrder command,
            @Header("correlation") CorrelationMetadata correlation) {

        return orderService.create(
            command,
            correlation.correlationId(),
            correlation.tenantId()
        );
    }
}
~~~

Route được dùng để chọn method `@MessageMapping("orders.create")`. Custom correlation metadata được đọc bằng `@Header("correlation")` vì tên này khớp với key đã đăng ký trong extractor.

Nếu handler cần nhiều giá trị metadata, có thể dùng `@Headers Map<String, Object>` để nhận các giá trị đã được trích xuất. `@Header` không tự giải mã mọi MIME type; metadata phải được đăng ký với extractor và có decoder tương ứng.

Thông tin xác thực thường được xử lý ở tầng Spring Security hoặc interceptor xác thực. Không nên tự coi một chuỗi token trong metadata map là danh tính đã được xác minh. Sau khi xác thực, authorization vẫn cần kiểm tra quyền trên route và tài nguyên nghiệp vụ.

### Bearer token và Spring Security

Bearer token có thể dùng extension xác thực RSocket với MIME type `WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION`. Spring Security cung cấp `BearerTokenMetadata` để biểu diễn token và hỗ trợ JWT qua cấu hình `.jwt(...)` cùng một `ReactiveJwtDecoder`.

Ví dụ cấu hình interceptor ở server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
class RSocketSecurityConfiguration {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(RSocketSecurity rsocket) {
        rsocket
            .authorizePayload(authorize -> authorize
                .anyRequest().authenticated()
                .anyExchange().permitAll()
            )
            .jwt(Customizer.withDefaults());
        return rsocket.build();
    }
}
~~~

Spring Boot có thể tự đăng ký security interceptor khi các dependency RSocket Security phù hợp được khai báo. JWT decoder vẫn phải được cấu hình theo issuer hoặc khóa tin cậy của hệ thống. Với connection dùng chung cho nhiều người dùng, gửi token trên từng request cho phép xác thực theo người dùng của request đó; nếu một connection chỉ thuộc về một danh tính, có thể xác thực ngay trong SETUP.

## Phân biệt metadata của request với metadata của connection

Không phải mọi metadata đều thuộc một request cụ thể.

| API/frame | Phạm vi | Mục đích |
|---|---|---|
| `route(...)` | Request | Chọn handler cho request |
| `metadata(value, mimeType)` | Request | Thêm thông tin xác thực, tracing hoặc context cho request đó |
| `setupMetadata(...)` | Connection setup | Gửi metadata trong SETUP, thường dùng cho thông tin gắn với phiên kết nối |
| `@ConnectMapping` | Connection | Xử lý SETUP metadata và metadata push |
| `METADATA_PUSH` | Connection | Gửi thông báo metadata không gắn với một request cụ thể |

Nếu token ổn định trong toàn bộ vòng đời kết nối, có thể gửi trong SETUP bằng `setupMetadata()`. Server xử lý dữ liệu SETUP qua `@ConnectMapping` hoặc security interceptor phù hợp. Nếu token có thể thay đổi theo request hoặc mỗi request có principal khác nhau, dùng metadata trên request.

Metadata push không phải cách thay thế route hoặc custom metadata của request. Nó gửi thông báo ở cấp connection, không gắn với một interaction cụ thể.

Metadata request thường được mang trong frame mở đầu của tương tác, như REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_CHANNEL hoặc REQUEST_FNF. Với stream, route và context mở đầu không cần lặp lại trong từng payload tiếp theo. Nếu mỗi phần tử stream có correlation riêng, hãy đưa correlation vào chính payload phần tử hoặc dùng cơ chế tracing phù hợp.

## Điều gì xảy ra nếu không dùng composite metadata?

`RSocketRequester.Builder.metadataMimeType(...)` cấu hình MIME type metadata cho kết nối trong SETUP.

Mặc định Spring dùng:

```text
message/x.rsocket.composite-metadata.v0
```

Nếu thay bằng một MIME type khác, Spring xem MIME type đó là định dạng metadata của route khi route được cung cấp. Khi đó, không có composite envelope để chứa nhiều entry MIME type độc lập. Vì vậy, không thể dùng `.metadata(value, anotherMimeType)` như cách thêm một entry thứ hai.

| Cấu hình metadata MIME type | Hệ quả |
|---|---|
| Composite metadata mặc định | Có thể gửi route và nhiều metadata entry khác MIME type |
| Một MIME type đơn | Toàn bộ metadata dùng định dạng MIME type đó; route được encode theo MIME type đã chọn |
| Composite nhưng thiếu decoder custom | Sender có thể gửi entry, nhưng receiver không giải mã được custom value thành object ứng dụng |

Nếu cần đồng thời route, authentication và correlation, giữ composite metadata ở cả hai phía. Đừng đổi metadata MIME type của client sang custom correlation MIME type chỉ để gửi một giá trị; việc đó làm mất khả năng ghép các entry độc lập theo cách Spring mong đợi.

## Bảo mật và quy ước thiết kế metadata

Metadata thường chứa dữ liệu nhạy cảm hoặc dữ liệu điều khiển. Hãy thiết kế có chủ đích:

- Dùng MIME type chuẩn của RSocket cho các extension chuẩn như routing và authentication.
- Dùng MIME type riêng có namespace cho metadata ứng dụng.
- Định nghĩa schema, kiểu dữ liệu và phiên bản cho custom metadata.
- Xác thực token bằng Spring Security hoặc cơ chế xác thực đã được kiểm chứng.
- Kiểm tra authorization cho từng route và tài nguyên.
- Dùng TLS khi metadata đi qua mạng không tin cậy.
- Không ghi bearer token, mật khẩu hoặc dữ liệu nhạy cảm vào log.
- Giới hạn kích thước metadata và số lượng entry để tránh lạm dụng bộ nhớ.
- Không đặt dữ liệu nghiệp vụ lớn trong metadata; hãy dùng Data payload.
- Tránh dùng correlation ID do client gửi như bằng chứng danh tính hoặc quyền truy cập.

Correlation ID giúp ghép log và trace, nhưng bản thân nó không phải secret và không chứng minh ai gửi request. Nếu cần truy vết xuyên service, hãy xác định rõ quy tắc tạo, truyền và kiểm tra correlation/trace context.

## Các lỗi thường gặp

### Gửi route như custom metadata

Nếu dùng `.metadata("orders.create", customMimeType)` thay cho `.route("orders.create")`, Spring không xem entry đó là routing metadata chuẩn. Handler có thể không được tìm thấy. Dùng `route()` để tạo route.

### Gọi metadata() khi kết nối không dùng composite

API thêm metadata entry yêu cầu composite metadata. Nếu connection dùng một metadata MIME type đơn, việc thêm entry custom có thể phát sinh `IllegalArgumentException`. Kiểm tra `metadataMimeType` của builder.

### Sender và receiver dùng MIME type khác nhau

Sender encode theo một MIME type nhưng receiver đăng ký decoder theo MIME type khác. Kết quả là custom metadata không được trích xuất hoặc không có decoder phù hợp. Đặt MIME type thành hằng số hợp đồng và kiểm tra ở cả hai phía.

### Nghĩ rằng MetadataExtractor tự giải mã mọi custom metadata

Spring có built-in extraction cho routing metadata. Các MIME type tùy chỉnh cần decoder và đăng ký qua `metadataExtractorRegistry`.

### Nhầm metadata với HTTP header

RSocket metadata là phần của RSocket payload và có định dạng MIME riêng. Spring có thể đưa giá trị đã trích xuất vào message headers để handler dùng `@Header`, nhưng điều đó không biến metadata thành HTTP header.

### Gửi token trong metadata nhưng không xác thực

Token chỉ là dữ liệu được truyền. Server phải xác minh chữ ký, thời hạn, issuer/audience và áp dụng authorization. Không tin token chỉ vì nó xuất hiện trong metadata.

## Kiểm thử route và nhiều metadata entry

Một integration test nên xác nhận cả định tuyến và trích xuất custom metadata. Ví dụ, gửi request có correlation metadata rồi kiểm tra handler nhận đúng correlation ID:

~~~java
StepVerifier.create(
    requester
        .route("orders.create")
        .metadata(
            new CorrelationMetadata("corr-8f31", "tenant-42"),
            CORRELATION_MIME
        )
        .data(new CreateOrder("SKU-42", 2))
        .retrieveMono(OrderResult.class)
)
.expectNextMatches(result -> result.status().equals("ACCEPTED"))
.verifyComplete();
~~~

Ngoài trường hợp thành công, kiểm thử nên bao gồm:

1. Route đúng được chuyển tới handler tương ứng.
2. Route không tồn tại bị từ chối theo chính sách lỗi của ứng dụng.
3. Request có route, authentication và correlation entry cùng lúc.
4. Custom metadata được giải mã đúng kiểu.
5. MIME type không được đăng ký bị xử lý như lỗi hoặc metadata không hỗ trợ theo cấu hình.
6. Thiếu correlation metadata được xử lý theo quy tắc optional/required của ứng dụng.
7. Token hết hạn hoặc không hợp lệ bị Spring Security từ chối.
8. Request có nhiều entry metadata nhưng payload Data vẫn được deserialize đúng.
9. Client và server có cùng cấu hình composite metadata.
10. Log/trace có correlation ID nhưng không ghi credential.

Test nên chạy qua RSocket transport và codec thật, không chỉ gọi trực tiếp method handler. Như vậy mới kiểm tra được encoding, composite framing, metadata extraction và route mapping.

## Checklist trước khi triển khai

Trước khi đưa một hợp đồng metadata vào service, hãy trả lời:

1. Route nào được dùng để chọn handler?
2. Connection có đang dùng `message/x.rsocket.composite-metadata.v0` không?
3. Authentication metadata dùng MIME type chuẩn nào và server xác thực bằng cơ chế gì?
4. Custom metadata có MIME type riêng, schema và phiên bản chưa?
5. Encoder ở sender và decoder ở receiver có tương thích không?
6. MetadataExtractor đã đăng ký custom MIME type với key cần dùng chưa?
7. Handler đọc metadata qua `@Header` hay `@Headers`?
8. Dữ liệu nào thuộc request, dữ liệu nào thuộc SETUP/connection?
9. Metadata có giới hạn kích thước và được bảo vệ khi truyền không?
10. Integration test đã xác nhận route, token, correlation và Data cùng hoạt động chưa?

`route()` tạo routing metadata để chọn handler. Composite metadata cho phép đặt nhiều entry MIME type độc lập trong cùng một request. Custom metadata bổ sung context riêng của ứng dụng, nhưng cần MIME type, encoder/decoder và quy tắc trích xuất thống nhất. Khi kết hợp đúng ba phần này, một request RSocket có thể mang route, thông tin xác thực và correlation ID mà vẫn giữ payload nghiệp vụ trong Data.

## Tài liệu tham khảo

- [Spring Framework Reference: RSocketRequester và MetadataExtractor](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework 6.2: RSocketRequester.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [RSocket Java: CompositeMetadata và WellKnownMimeType](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/metadata/package-summary.html)
- [Spring Security Reference: RSocket Authentication](https://docs.spring.io/spring-security/reference/7.0/reactive/integrations/rsocket.html)

