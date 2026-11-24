# Thiết kế metadata tùy chỉnh và xử lý kiểu chưa hỗ trợ

Trong Spring RSocket, metadata mang thông tin phụ trợ đi kèm message, chẳng hạn route, tracing, locale, tenant context hoặc thông tin xác thực theo cơ chế bảo mật đã cấu hình. Data thường chứa nội dung nghiệp vụ; metadata mô tả ngữ cảnh để responder định tuyến hoặc xử lý message.

Spring hỗ trợ metadata chuẩn như routing metadata, đồng thời cho phép ứng dụng định nghĩa MIME type và kiểu Java riêng. Để sử dụng custom metadata, hai phía cần thống nhất định dạng, đăng ký encoder/decoder và cấu hình **MetadataExtractor** để chuyển metadata nhận được thành các giá trị có tên, sau đó handler có thể đọc qua **@Header** hoặc **@Headers**.

Nếu kiểu metadata chưa được hỗ trợ, Spring không tự đoán cách serialize một object bất kỳ. Cần bổ sung codec tương thích hoặc chọn biểu diễn đơn giản như String, byte[] hay ByteBuffer. Việc thiết kế rõ hợp đồng metadata giúp client/server tương thích, tránh lỗi decode và không biến metadata thành một kênh truyền dữ liệu nghiệp vụ tùy tiện.

## 1. Metadata dùng để làm gì?

Một RSocket message có thể mang hai phần:

- **Data:** nội dung chính của request hoặc response, thường là DTO nghiệp vụ.
- **Metadata:** thông tin bổ sung phục vụ routing, bảo mật, tracing, định dạng hoặc ngữ cảnh xử lý.

Ví dụ một request tra cứu đơn hàng có thể có:

| Thành phần | Giá trị ví dụ | Mục đích |
|---|---|---|
| Route metadata | orders.find | Chọn handler |
| Data | FindOrderRequest | Mã đơn hàng và tham số truy vấn |
| Custom metadata | RequestContext | Tenant, locale, trace ID |

Không nên đưa toàn bộ DTO nghiệp vụ vào metadata. Data là nơi phù hợp cho nội dung mà handler cần xử lý như một phần của thao tác. Metadata phù hợp với thông tin phụ trợ, thường nhỏ và có ý nghĩa xuyên suốt nhiều route.

Metadata cũng không tự trở thành thông tin đáng tin cậy. Giá trị tenant, user hoặc role do client gửi vẫn phải được xác thực và phân quyền ở server.

## 2. MIME type xác định cách diễn giải metadata

Mỗi metadata entry có một MIME type để receiver biết định dạng byte. Ví dụ:

~~~java
MimeType contextMimeType = MimeType.valueOf(
    "application/vnd.acme.request-context.v1+json"
);
~~~

Tên MIME type nên mô tả định dạng và phiên bản hợp đồng. Hậu tố +json thể hiện nội dung được serialize bằng JSON; v1 cho biết phiên bản schema ứng dụng.

Các nguyên tắc khi chọn MIME type:

- Dùng tên ổn định, có namespace riêng của ứng dụng.
- Chọn định dạng mà hai phía có encoder và decoder tương thích.
- Có phiên bản khi schema có thể thay đổi không tương thích.
- Không dùng cùng một MIME type cho hai cấu trúc byte khác nhau.
- Không giả định MIME type là bằng chứng xác thực hoặc quyền truy cập.

Spring RSocket mặc định dùng **composite metadata** cho metadata của kết nối. Composite metadata cho phép nhiều entry độc lập cùng xuất hiện trong một message, mỗi entry có MIME type riêng. Ví dụ một message có thể mang routing metadata, authentication metadata và tracing metadata.

Nếu ứng dụng dùng một metadata MIME type đơn thay cho composite metadata, toàn bộ metadata được diễn giải như một khối theo MIME type đó. Khi đó không thể mặc định rằng các entry khác nhau sẽ tự được tách ra.

## 3. Composite metadata và metadata đơn

Hai cách tổ chức thường gặp:

| Cách tổ chức | Đặc điểm | Khi phù hợp |
|---|---|---|
| Composite metadata | Nhiều entry, mỗi entry có MIME type riêng | Route, tracing và context độc lập trong cùng message |
| Metadata đơn | Một khối metadata theo một MIME type | Một envelope riêng do ứng dụng kiểm soát |

Ví dụ composite metadata có thể chứa:

~~~text
Composite Metadata
  ├── Routing: message/x.rsocket.routing.v0
  │     └── orders.find
  ├── Request Context: application/vnd.acme.request-context.v1+json
  │     └── {"tenant":"acme","locale":"vi-VN"}
  └── Trace: message/x.example-trace.v1
        └── trace-8f31
~~~

Trong Spring RSocketRequester, composite metadata là mặc định. Vì vậy có thể thêm nhiều metadata entry bằng RequestSpec.metadata(value, mimeType). Mỗi giá trị phải được một Encoder phù hợp hỗ trợ.

Ví dụ:

~~~java
Mono<OrderView> response = requester
    .route("orders.find")
    .metadata(
        requestContext,
        contextMimeType
    )
    .metadata(
        traceId,
        traceMimeType
    )
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class);
~~~

Nếu dùng một metadata MIME type đơn, hãy thiết kế một envelope có schema rõ ràng và cấu hình MetadataExtractor phù hợp với toàn bộ khối đó. Không trộn cách gửi composite với cách giải mã metadata đơn.

## 4. Phân biệt metadata của request và metadata của connection

Metadata có thể xuất hiện ở các phạm vi khác nhau:

- **Request metadata:** gắn với một tương tác cụ thể, ví dụ trace ID hoặc locale cho request orders.find.
- **SETUP metadata:** được gửi khi tạo kết nối, phù hợp với ngữ cảnh cấp phiên nếu ứng dụng cần xử lý trong giai đoạn kết nối.
- **Metadata Push:** thông báo metadata ở phạm vi kết nối bằng frame METADATA_PUSH, không gắn với một request route riêng.

Trong RSocketRequester:

- RequestSpec.metadata(value, mimeType) thêm metadata cho request hiện tại.
- Builder.setupMetadata(value, mimeType) thêm metadata vào SETUP.
- Metadata Push dùng API sendMetadata().

Không dùng setup metadata cho dữ liệu thay đổi theo từng request, chẳng hạn trace ID của mỗi thao tác. Ngược lại, thông tin chỉ thuộc ngữ cảnh kết nối có thể được trao đổi trong SETUP nếu hợp đồng và cơ chế xác thực của ứng dụng quy định như vậy.

## 5. Gửi custom metadata bằng RSocketRequester

Để gửi object Java làm metadata, RSocketStrategies phải có Encoder tương thích với kiểu object và MIME type đã chọn.

Ví dụ DTO:

~~~java
public record RequestContext(
    String tenant,
    String locale,
    String traceId
) {}
~~~

Client gửi custom metadata:

~~~java
private static final MimeType CONTEXT_MIME =
    MimeType.valueOf(
        "application/vnd.acme.request-context.v1+json");

Mono<OrderView> findOrder(
        RSocketRequester requester,
        RequestContext context,
        String orderId) {

    return requester
        .route("orders.find")
        .metadata(context, CONTEXT_MIME)
        .data(new FindOrderRequest(orderId))
        .retrieveMono(OrderView.class);
}
~~~

Trong ví dụ này:

- route(...) chọn handler.
- metadata(context, CONTEXT_MIME) thêm một metadata entry độc lập.
- data(...) cung cấp nội dung nghiệp vụ.
- retrieveMono(...) nhận một response.

Đây là cách gửi metadata theo từng request. Client và server cần thống nhất MIME type, schema và codec. Nếu Encoder không hỗ trợ RequestContext với MIME type đó, request có thể lỗi ngay ở bước encode metadata.

## 6. Đăng ký Encoder và Decoder cho kiểu tùy chỉnh

RSocketStrategies quản lý các Encoder và Decoder dùng cho data cũng như metadata. Các codec cơ bản từ spring-core hỗ trợ một số kiểu đơn giản như String, byte[] và ByteBuffer. Để encode/decode DTO JSON, có thể bổ sung codec từ spring-web.

Ví dụ cấu hình JSON:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders ->
        encoders.add(new Jackson2JsonEncoder()))
    .decoders(decoders ->
        decoders.add(new Jackson2JsonDecoder()))
    .build();
~~~

Jackson2JsonEncoder chuyển object phù hợp thành JSON; Jackson2JsonDecoder chuyển JSON thành kiểu Java mà extractor yêu cầu. Cần có dependency spring-web và Jackson tương ứng trong ứng dụng.

Nếu dùng CBOR hoặc Protobuf, hãy đăng ký encoder/decoder tương ứng thay cho JSON. Không đăng ký một codec chỉ vì nó có thể xử lý data; phải xác nhận codec đó cũng hỗ trợ MIME type và kiểu metadata cần gửi/nhận.

### Dùng cùng RSocketStrategies ở server

Khi cấu hình RSocketMessageHandler trực tiếp, gắn strategies vào handler. Ví dụ dưới đây giả định bean strategies đã được tạo từ builder ở trên:

~~~java
@Configuration
public class RSocketServerConfiguration {

    @Bean
    RSocketMessageHandler rsocketMessageHandler(
            RSocketStrategies strategies) {

        RSocketMessageHandler handler =
            new RSocketMessageHandler();

        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
~~~

Trong Spring Boot, hãy tích hợp cấu hình custom vào RSocketStrategies/RSocketMessageHandler do ứng dụng sử dụng, tránh tạo hai bộ cấu hình codec khác nhau mà không biết server đang dùng bộ nào. Nếu client và server nằm trong cùng ứng dụng, RSocketStrategies có thể được dùng lại khi hợp đồng codec giống nhau.

## 7. MetadataExtractor chuyển metadata thành header

Việc đăng ký Decoder mới chỉ cho Spring biết cách giải mã byte thành object. Để handler truy cập object đó bằng tên, cần cấu hình **MetadataExtractor**.

MetadataExtractor nhận metadata đã serialize và tạo các cặp name-value. Trong Spring, những giá trị này có thể được truy cập như message header bằng @Header hoặc @Headers.

**DefaultMetadataExtractor** có sẵn hỗ trợ routing metadata với MIME type message/x.rsocket.routing.v0 và lưu route dưới key route. Với MIME type khác, cần đăng ký kiểu đích và tên header bằng MetadataExtractorRegistry.metadataToExtract(...).

Ví dụ:

~~~java
MimeType CONTEXT_MIME = MimeType.valueOf(
    "application/vnd.acme.request-context.v1+json");

RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders ->
        encoders.add(new Jackson2JsonEncoder()))
    .decoders(decoders ->
        decoders.add(new Jackson2JsonDecoder()))
    .metadataExtractorRegistry(registry -> {
        registry.metadataToExtract(
            CONTEXT_MIME,
            RequestContext.class,
            "requestContext"
        );
    })
    .build();
~~~

Đây là phần cấu hình đầy đủ được ghép từ codec ở mục trước và đăng ký extractor. Nếu đã có bean RSocketStrategies, hãy thêm metadataExtractorRegistry vào cùng builder hiện tại thay vì khai báo một bean trùng tên.

Lời gọi metadataToExtract(...) có ba ý nghĩa:

1. CONTEXT_MIME xác định entry nào cần giải mã.
2. RequestContext.class xác định kiểu Java đích.
3. requestContext là tên key được đưa vào map header.

Nếu chưa đăng ký entry này, DefaultMetadataExtractor không tự đoán rằng một MIME type tùy chỉnh cần được chuyển thành RequestContext. Kết quả có thể không xuất hiện dưới header requestContext mà handler mong đợi.

## 8. Đọc custom metadata trong @MessageMapping

Sau khi extractor đăng ký key requestContext, handler có thể nhận giá trị bằng @Header:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<OrderView> find(
            @Payload FindOrderRequest request,
            @Header("requestContext") RequestContext context) {

        return orderService.find(
            request.orderId(),
            context.tenant(),
            context.locale()
        );
    }
}
~~~

Nếu cần nhiều metadata entry, có thể dùng @Headers để nhận map:

~~~java
@MessageMapping("orders.find")
public Mono<OrderView> find(
        @Payload FindOrderRequest request,
        @Headers Map<String, Object> headers) {

    RequestContext context =
        (RequestContext) headers.get("requestContext");

    return orderService.find(
        request.orderId(),
        context.tenant(),
        context.locale()
    );
}
~~~

@Header lấy một giá trị đã được extractor đăng ký; nó không tự giải mã một MIME type bất kỳ. Nếu header bắt buộc mà metadata không được gửi hoặc không được extract, cần xử lý rõ trường hợp thiếu thay vì giả định giá trị luôn có mặt.

## 9. Khi metadata có kiểu generic hoặc cần ánh xạ tùy chỉnh

metadataToExtract(...) hỗ trợ Class, ParameterizedTypeReference và mapper tùy chỉnh. Điều này hữu ích khi metadata là một map hoặc một envelope có nhiều trường cần đưa thành các header riêng.

Ví dụ metadata JSON chứa tenant và locale:

~~~json
{
  "tenantId": "acme",
  "locale": "vi-VN",
  "traceId": "trace-8f31"
}
~~~

Có thể đăng ký kiểu generic và mapper:

~~~java
private static final MimeType MAP_MIME = MimeType.valueOf(
    "application/vnd.acme.context-map.v1+json");

@Bean
RSocketStrategies rsocketStrategies() {
    return RSocketStrategies.builder()
        .decoders(decoders ->
            decoders.add(new Jackson2JsonDecoder()))
        .metadataExtractorRegistry(registry -> {
            registry.metadataToExtract(
                MAP_MIME,
                new ParameterizedTypeReference<Map<String, String>>() {},
                (values, output) -> {
                    output.put("tenantId", values.get("tenantId"));
                    output.put("locale", values.get("locale"));
                    output.put("traceId", values.get("traceId"));
                }
            );
        })
        .build();
}
~~~

Mapper cho phép kiểm soát tên và số lượng header đầu ra. Không nên đưa toàn bộ map không kiểm soát vào message header nếu chỉ cần một vài trường. Hãy chọn những giá trị handler thực sự sử dụng và validate chúng trước khi xử lý nghiệp vụ.

## 10. Xử lý khi kiểu metadata chưa được hỗ trợ

Một kiểu metadata có thể chưa được hỗ trợ ở nhiều cấp khác nhau. Cần xác định đúng nguyên nhân trước khi sửa.

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không encode được object khi gửi | Không có Encoder phù hợp với kiểu/MIME type | Đăng ký Encoder hoặc đổi sang kiểu đã hỗ trợ |
| Không decode được metadata khi nhận | Không có Decoder tương thích | Đăng ký Decoder cho MIME type |
| Decode được nhưng handler không thấy header | Chưa đăng ký metadataToExtract hoặc mapper chưa đưa key vào output map | Cấu hình MetadataExtractorRegistry |
| Generic type bị mất thông tin | Dùng Class cho kiểu đã bị type erasure | Dùng ParameterizedTypeReference |
| MIME type không được peer hỗ trợ | Hai bên không thống nhất hợp đồng | Thống nhất MIME type, version và codec |
| Chỉ có một metadata blob nhưng code mong composite entries | Sai cách tổ chức metadata | Dùng composite metadata hoặc extractor cho envelope đơn |

Không nên coi một object Java bất kỳ là metadata có thể tự serialize. Spring cần tìm được Encoder tương thích theo kiểu dữ liệu và MIME type. Ở chiều nhận, decoder phải có khả năng tạo đúng kiểu mà MetadataExtractor yêu cầu.

Hai trường hợp cần phân biệt: MIME type chưa được đăng ký thường không được DefaultMetadataExtractor ánh xạ thành header ứng dụng; MIME type đã đăng ký nhưng không có Decoder tương thích thì không thể giải mã thành kiểu đích và quá trình extract có thể phát sinh lỗi. Hãy kiểm tra cả registration lẫn danh sách decoder khi xử lý lỗi.

### Dùng kiểu đơn giản làm fallback

Nếu chưa thể đăng ký codec cho một kiểu phức tạp, có thể biểu diễn metadata bằng String hoặc byte[] với MIME type đã thống nhất:

~~~java
String compactContext =
    "tenant=acme;locale=vi-VN";

Mono<OrderView> response = requester
    .route("orders.find")
    .metadata(compactContext, MimeTypeUtils.TEXT_PLAIN)
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class);
~~~

Cách này dùng codec String cơ bản, nhưng server vẫn cần đăng ký việc extract entry text/plain để handler nhận được header:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .metadataExtractorRegistry(registry ->
        registry.metadataToExtract(
            MimeTypeUtils.TEXT_PLAIN,
            String.class,
            "compactContext"))
    .build();
~~~

Handler nhận String qua @Header("compactContext") rồi tự parse và validate định dạng. Không nên tạo format chuỗi mơ hồ bằng cách nối tùy tiện các trường có thể chứa dấu phân tách. Nếu dùng text, hãy định nghĩa grammar rõ ràng hoặc dùng JSON/CBOR với codec phù hợp.

Với dữ liệu nhị phân, có thể dùng byte[] hoặc ByteBuffer và MIME type riêng. Hãy quy định byte order, encoding, schema version và giới hạn kích thước.

## 11. Metadata đơn không dùng composite

Một số peer có thể không hỗ trợ composite metadata hoặc ứng dụng chọn một metadata envelope duy nhất. Khi đó toàn bộ metadata được decode theo một MIME type.

Ví dụ server nhận JSON map làm metadata đơn. Có thể đăng ký mapper trong cấu hình RSocketStrategies như sau:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .decoders(decoders ->
        decoders.add(new Jackson2JsonDecoder()))
    .metadataExtractorRegistry(registry -> {
        registry.metadataToExtract(
            MimeType.valueOf(
                "application/vnd.acme.metadata.v1+json"),
            new ParameterizedTypeReference<Map<String, String>>() {},
            (values, output) -> {
                output.put("tenantId", values.get("tenantId"));
                output.put("locale", values.get("locale"));
            }
        );
    })
    .build();
~~~

Trong mô hình này, extractor giải mã một khối JSON và mapper quyết định header nào được tạo. Đây là cách xử lý phù hợp khi peer gửi một envelope duy nhất thay vì nhiều composite entries.

Nếu cần route cùng nhiều metadata entry độc lập, composite metadata thường đơn giản hơn vì routing, tracing và context có thể dùng MIME type riêng. Khi đổi sang metadata đơn, phải thiết kế cách mang route và các giá trị phụ trợ trong cùng envelope theo hợp đồng riêng.

## 12. Tự viết MetadataExtractor khi định dạng quá đặc biệt

Nếu metadata có định dạng proprietary hoặc cần giải mã theo quy tắc không thể biểu diễn bằng Decoder thông thường và mapper, có thể triển khai MetadataExtractor riêng.

MetadataExtractor nhận Payload và metadata MIME type của kết nối, sau đó trả về map các giá trị đã giải mã. Key route phải được đưa vào MetadataExtractor.ROUTE_KEY nếu extractor tự xử lý routing metadata; nếu bỏ qua route, Spring có thể không tìm được handler tương ứng.

Ví dụ khung triển khai:

~~~java
public final class AcmeMetadataExtractor
        implements MetadataExtractor {

    @Override
    public Map<String, Object> extract(
            Payload payload,
            MimeType metadataMimeType) {

        Map<String, Object> values = new HashMap<>();

        // Giải mã metadata theo định dạng đã thống nhất.
        // Nếu có route, phải đưa route vào MetadataExtractor.ROUTE_KEY.
        // Các giá trị khác được lưu dưới key ổn định.

        return values;
    }
}
~~~

Sau đó cấu hình extractor:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .metadataExtractor(new AcmeMetadataExtractor())
    .build();
~~~

Chỉ nên tự triển khai extractor khi cơ chế đăng ký MIME type, decoder và mapper không đáp ứng. Custom extractor phải xử lý chính xác composite metadata nếu ứng dụng sử dụng định dạng đó; không được coi toàn bộ byte của composite metadata là một chuỗi hoặc JSON đơn.

## 13. Validation, bảo mật và versioning metadata

Metadata có thể ảnh hưởng đến tenant, tracing, routing hoặc bảo mật nên cần được kiểm soát như đầu vào không tin cậy.

Các nguyên tắc:

- Kiểm tra metadata bắt buộc có mặt và đúng kiểu.
- Giới hạn kích thước metadata và từng trường.
- Validate tenant/locale/trace ID theo định dạng đã quy định.
- Không tin tenant ID hoặc user ID do client tự khai báo nếu chưa được xác thực.
- Không ghi access token, secret hoặc dữ liệu cá nhân nhạy cảm vào log.
- Chỉ extract những MIME type ứng dụng thực sự hỗ trợ.
- Có version trong MIME type hoặc envelope khi schema thay đổi.
- Quy định cách xử lý trường lạ, trường thiếu và phiên bản không tương thích.

Metadata xác thực nên dùng cơ chế Spring Security/RSocket Security phù hợp. Việc metadata được decode thành một object Authentication hoặc RequestContext không tự chứng minh người gửi có quyền. Phải xác thực token/chứng thư và kiểm tra quyền truy cập route, tenant và tài nguyên.

Khi thay đổi schema, ưu tiên thêm trường tùy chọn có default rõ ràng. Nếu đổi kiểu hoặc ý nghĩa trường hiện có, hãy phát hành MIME type version mới hoặc duy trì cơ chế tương thích trong giai đoạn chuyển đổi.

## 14. Kiểm thử custom metadata

Nên kiểm tra cả encoder/decoder lẫn đường đi qua RSocket:

1. Encoder chuyển RequestContext thành byte theo CONTEXT_MIME.
2. Decoder tạo lại RequestContext từ byte metadata.
3. MetadataExtractor đăng ký key requestContext.
4. Handler nhận đúng giá trị qua @Header.
5. Metadata bị thiếu được xử lý theo hợp đồng.
6. MIME type không hỗ trợ được phát hiện và báo lỗi rõ.
7. Trường sai kiểu hoặc sai định dạng bị validation từ chối.
8. Composite metadata có route và custom entries được giải mã đúng.
9. Metadata đơn dùng mapper đúng với envelope.
10. Cancellation/transport error không làm giữ lại buffer hoặc tài nguyên.

Có thể kiểm tra codec riêng bằng ObjectMapper hoặc Encoder/Decoder API, sau đó chạy integration test với RSocket client/server thật. Unit test mapper không đủ để xác nhận composite metadata được đóng gói và tách đúng qua transport.

## 15. Checklist thiết kế metadata

| Câu hỏi | Quyết định cần có |
|---|---|
| Thông tin này có thực sự là metadata? | Phân biệt với data nghiệp vụ |
| MIME type là gì? | Tên rõ ràng, có version |
| Dùng composite hay metadata đơn? | Thống nhất giữa hai peer |
| Java type nào được gửi? | DTO/primitive/binary có schema |
| Encoder nào serialize? | Đăng ký theo MIME type |
| Decoder nào deserialize? | Đăng ký theo MIME type |
| MetadataExtractor tạo key nào? | Tên header ổn định |
| Handler nhận bằng cách nào? | @Header hoặc @Headers |
| Kiểu chưa hỗ trợ xử lý ra sao? | Bổ sung codec hoặc fallback có schema |
| Ai xác thực giá trị? | Security và authorization phía server |
| Giới hạn tài nguyên thế nào? | Size limit và validation |
| Schema thay đổi ra sao? | Versioning và tương thích |

## 16. Kết luận

Spring RSocket hỗ trợ metadata chuẩn và custom metadata thông qua MIME type, Encoder, Decoder và MetadataExtractor. Composite metadata cho phép nhiều entry độc lập cùng tồn tại; mỗi entry có MIME type riêng. DefaultMetadataExtractor nhận biết routing metadata, còn metadata tùy chỉnh cần được đăng ký bằng MetadataExtractorRegistry.metadataToExtract(...).

Khi gửi custom metadata, RSocketRequester cần Encoder tương thích. Khi nhận, RSocketStrategies cần Decoder và extractor để ánh xạ giá trị thành key mà handler có thể đọc bằng @Header hoặc @Headers. Nếu kiểu chưa được hỗ trợ, hãy đăng ký codec hoặc dùng biểu diễn đơn giản có MIME type và schema rõ ràng. Chỉ triển khai MetadataExtractor riêng khi định dạng đặc biệt thực sự cần thiết.

Thiết kế metadata tốt giúp giữ data tập trung vào nghiệp vụ, metadata tập trung vào ngữ cảnh, đồng thời bảo đảm hai peer hiểu cùng một hợp đồng. Kết hợp versioning, validation, giới hạn kích thước và bảo mật để metadata không trở thành nguồn lỗi decode hoặc lỗ hổng tin cậy trong hệ thống realtime.

Tài liệu tham khảo:
- [Spring Framework Reference – RSocket and MetadataExtractor](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc – MetadataExtractorRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractorRegistry.html)
- [Spring Framework Javadoc – RSocketStrategies.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.Builder.html)

