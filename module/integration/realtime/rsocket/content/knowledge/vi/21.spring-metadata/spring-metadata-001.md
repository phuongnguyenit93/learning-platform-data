# Mã hóa và giải mã composite metadata bằng RSocketStrategies

RSocket cho phép một message mang data và metadata. Data thường chứa nội dung nghiệp vụ; metadata có thể mang route, thông tin xác thực, tenant, correlation ID hoặc tracing context. Khi một request cần nhiều loại metadata, RSocket thường dùng **Composite Metadata**: mỗi entry có MIME type riêng để responder biết cách diễn giải byte của entry đó.

Trong Spring, **RSocketStrategies** tập hợp các Encoder, Decoder và MetadataExtractor dùng cho quá trình chuyển đổi. Phía gửi dùng Encoder để mã hóa object metadata thành byte; RSocketRequester đóng gói các entry vào Composite Metadata. Phía nhận dùng MetadataExtractor cùng Decoder đã đăng ký để giải mã từng entry và đưa kết quả vào message headers. Hiểu rõ hai chiều này giúp cấu hình metadata nhất quán và tránh lỗi khi client gửi được nhưng server không đọc được.

Sau bài học, bạn có thể:

- Giải thích cấu trúc Composite Metadata và vai trò của MIME type trên từng entry.
- Phân biệt encoding metadata với extraction/decoding metadata.
- Cấu hình Encoder và Decoder trong RSocketStrategies.
- Gửi nhiều metadata entry bằng RSocketRequester.
- Đăng ký metadataToExtract để đọc custom metadata trong @MessageMapping.
- Xử lý metadata dạng DTO hoặc Map với kiểu generic.
- Kiểm thử encoding, decoding, MIME type và tương thích giữa requester/responder.

## 1. Composite Metadata là gì?

Một RSocket payload có hai phần độc lập:

- **Data**: nội dung chính của request hoặc response, ví dụ mã sản phẩm và số lượng cần kiểm tra.
- **Metadata**: thông tin mô tả hoặc điều khiển message, ví dụ route, tenant, authentication và tracing.

Composite Metadata là một định dạng metadata cho phép ghép nhiều entry trong cùng metadata section. Mỗi entry có MIME type và nội dung riêng. Vì vậy, một request có thể mang route theo định dạng routing chuẩn, tenant theo JSON và correlation context theo một MIME type khác.

~~~mermaid
flowchart TD
    A[RSocket request payload] --> B[Data section]
    A --> C[Metadata section: Composite Metadata]
    B --> D[JSON request DTO]
    C --> E[Routing entry]
    C --> F[Tenant entry]
    C --> G[Correlation entry]
    D --> H[Message handler]
    E --> H
    F --> H
    G --> H
~~~

Ví dụ về một request ở mức khái niệm:

~~~text
REQUEST_RESPONSE
  metadata:
    message/x.rsocket.routing.v0
      inventory.check

    application/vnd.acme.tenant-v1+json
      {"tenantId":"tenant-17"}

    application/vnd.acme.trace-v1+json
      {"correlationId":"corr-91"}

  data:
    {"sku":"SKU-42","quantity":3}
~~~

Các entry trong ví dụ có mục đích khác nhau. Routing entry chọn handler; tenant entry mang ngữ cảnh tenant; trace entry giúp liên kết log; data chứa yêu cầu kiểm tra tồn kho.

Composite Metadata không phải một JSON object lớn có các field tùy ý. Nó là tập hợp entry có cấu trúc và MIME type riêng. Responder có thể giải mã từng entry theo codec tương ứng.

## 2. Phân biệt MIME type của kết nối và MIME type của entry

RSocket khai báo data MIME type và metadata MIME type trong SETUP frame. Hai giá trị này áp dụng cho kết nối. Nếu metadata MIME type là Composite Metadata, từng entry bên trong lại có MIME type riêng.

| Cấp | Ý nghĩa | Ví dụ |
|---|---|---|
| Data MIME type | Định dạng data của payload trên kết nối | application/json |
| Metadata MIME type | Định dạng của toàn metadata section | message/x.rsocket.composite-metadata.v0 |
| Entry MIME type | Định dạng nội dung của từng entry composite | application/vnd.acme.tenant-v1+json |

Trong Spring RSocketRequester, Composite Metadata là mặc định cho metadata. Có thể khai báo rõ để hợp đồng kết nối dễ đọc:

~~~java
private static final MimeType COMPOSITE_METADATA =
    MimeType.valueOf(
        "message/x.rsocket.composite-metadata.v0"
    );

RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .metadataMimeType(COMPOSITE_METADATA)
    .tcp("inventory.internal", 7000);
~~~

Data MIME type mặc định của requester được suy ra từ Decoder đầu tiên đã cấu hình. Metadata MIME type mặc định là Composite Metadata. Nếu ứng dụng cần một hợp đồng rõ ràng giữa nhiều dịch vụ, nên khai báo tường minh cả hai.

Một custom entry như application/vnd.acme.tenant-v1+json không thay thế metadata MIME type của kết nối. Nó chỉ mô tả cách diễn giải một entry nằm trong Composite Metadata.

## 3. RSocketStrategies chịu trách nhiệm gì?

RSocketStrategies là tập cấu hình dùng chung cho requester và responder. Nó cung cấp:

- Danh sách Encoder để serialize object thành data hoặc metadata bytes.
- Danh sách Decoder để deserialize data hoặc metadata bytes thành object.
- MetadataExtractor để trích xuất route và các giá trị metadata thành name-value pairs.
- RouteMatcher để so khớp route.
- ReactiveAdapterRegistry và DataBufferFactory cho các trường hợp tương ứng.

Có thể hình dung hai chiều như sau:

~~~mermaid
flowchart LR
    subgraph SEND[Phía gửi]
        A[Metadata DTO] --> B[Encoder được chọn theo type + MIME]
        B --> C[Metadata bytes]
        C --> D[Composite Metadata entry]
    end
    D --> E[RSocket transport]
    subgraph RECEIVE[Phía nhận]
        E --> F[Composite Metadata entries]
        F --> G[MetadataExtractor]
        G --> H[Decoder được chọn theo MIME + type]
        H --> I[Message headers]
    end
~~~

Điểm cần nhớ:

- Encoder dùng khi ứng dụng gửi object metadata.
- Decoder dùng khi ứng dụng nhận và giải mã metadata.
- MetadataExtractor đăng ký cách chuyển entry đã giải mã thành header mà handler có thể đọc.
- RSocketRequester thực hiện việc đóng gói metadata entry theo MIME type; RSocketStrategies cung cấp codec mà requester cần.
- RSocketStrategies không thay thế cấu trúc wire của Composite Metadata và không tự tạo schema nghiệp vụ.

Không có một cấu hình riêng tên là CompositeMetadataEncoder trong RSocketStrategies. Ứng dụng đăng ký Encoder/Decoder cho kiểu dữ liệu của entry; requester và RSocket layer xử lý cấu trúc composite.

## 4. Cấu hình Encoder và Decoder

Spring cung cấp các codec cơ bản cho String, byte[], ByteBuffer và DataBuffer. Khi cần serialize DTO thành JSON, CBOR hoặc Protobuf, ứng dụng cần đăng ký codec tương ứng. Các implementation JSON/CBOR/Protobuf thường có trong spring-web.

Ví dụ dùng Jackson JSON:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders ->
        encoders.add(new Jackson2JsonEncoder())
    )
    .decoders(decoders ->
        decoders.add(new Jackson2JsonDecoder())
    )
    .build();
~~~

Jackson2JsonEncoder có thể mã hóa DTO thành JSON khi MIME type phù hợp. Jackson2JsonDecoder giải mã JSON thành kiểu ứng dụng được yêu cầu.

Encoder/Decoder được lựa chọn theo kiểu dữ liệu và MIME type. Nếu không có codec nào hỗ trợ cả hai điều kiện, quá trình encode/decode thất bại. Vì vậy, chỉ đăng ký một JSON encoder không có nghĩa mọi MIME type tùy chỉnh đều tự động được hỗ trợ.

Các MIME type JSON có hậu tố +json thường được dùng cho custom metadata, ví dụ:

~~~java
private static final MimeType TENANT_MIME =
    MimeType.valueOf(
        "application/vnd.acme.tenant-v1+json"
    );
~~~

Hãy kiểm tra canEncode và canDecode của codec với MIME type và kiểu DTO thực tế trong phiên bản Spring đang sử dụng. Nếu custom codec chỉ hỗ trợ application/json mà không hỗ trợ MIME type vendor cụ thể, hãy cấu hình supported MIME types hoặc dùng codec tương ứng.

### DTO cho metadata

~~~java
public record TenantContext(String tenantId) {}

public record CorrelationContext(String correlationId) {}

public record InventoryCheckRequest(
    String sku,
    int quantity
) {}

public record InventoryResult(
    String sku,
    boolean available,
    int availableQuantity
) {}
~~~

Metadata DTO nên nhỏ, rõ nghĩa và chứa thông tin ngữ cảnh. Không đưa toàn bộ dữ liệu nghiệp vụ vào metadata; request body vẫn thuộc data section.

## 5. Mã hóa nhiều metadata entry ở phía requester

RSocketRequester cung cấp .metadata(value, mimeType) để thêm metadata object. Mỗi giá trị được mã hóa bằng Encoder phù hợp và gắn MIME type của entry trong Composite Metadata.

Khai báo MIME type:

~~~java
private static final MimeType TENANT_MIME =
    MimeType.valueOf(
        "application/vnd.acme.tenant-v1+json"
    );

private static final MimeType CORRELATION_MIME =
    MimeType.valueOf(
        "application/vnd.acme.correlation-v1+json"
    );
~~~

Gửi nhiều entry:

~~~java
Mono<InventoryResult> checkInventory(
        RSocketRequester requester,
        InventoryCheckRequest request,
        TenantContext tenant,
        CorrelationContext correlation) {

    return requester
        .route("inventory.check")
        .metadata(tenant, TENANT_MIME)
        .metadata(correlation, CORRELATION_MIME)
        .data(request)
        .retrieveMono(InventoryResult.class);
}
~~~

Trong lời gọi trên:

1. route("inventory.check") thêm routing metadata theo định dạng RSocket routing chuẩn.
2. metadata(tenant, TENANT_MIME) thêm tenant entry.
3. metadata(correlation, CORRELATION_MIME) thêm correlation entry.
4. data(request) mã hóa request object vào data section.
5. retrieveMono yêu cầu một response object.

Cả hai custom metadata entry và routing entry được đặt trong Composite Metadata. Data request được mã hóa riêng theo data MIME type của kết nối.

### Cấu hình requester với strategies

~~~java
RSocketStrategies clientStrategies =
    RSocketStrategies.builder()
        .encoders(encoders ->
            encoders.add(new Jackson2JsonEncoder())
        )
        .decoders(decoders ->
            decoders.add(new Jackson2JsonDecoder())
        )
        .build();

RSocketRequester requester =
    RSocketRequester.builder()
        .rsocketStrategies(clientStrategies)
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .metadataMimeType(COMPOSITE_METADATA)
        .tcp("inventory.internal", 7000);
~~~

Client cần Encoder để gửi metadata DTO và Decoder để đọc response. Nếu client cũng đóng vai responder và phải giải mã metadata do server gửi ngược, strategies phía client cần đăng ký MetadataExtractor tương ứng.

## 6. Giải mã metadata ở phía responder

Ở phía nhận, Spring dùng MetadataExtractor để chuyển serialized metadata thành các giá trị có tên. DefaultMetadataExtractor có sẵn hỗ trợ routing metadata chuẩn và đưa route vào key route.

Với custom MIME type, cần đăng ký cách giải mã:

~~~java
RSocketStrategies serverStrategies =
    RSocketStrategies.builder()
        .encoders(encoders ->
            encoders.add(new Jackson2JsonEncoder())
        )
        .decoders(decoders ->
            decoders.add(new Jackson2JsonDecoder())
        )
        .metadataExtractorRegistry(registry -> {
            registry.metadataToExtract(
                TENANT_MIME,
                TenantContext.class,
                "tenant"
            );

            registry.metadataToExtract(
                CORRELATION_MIME,
                CorrelationContext.class,
                "correlation"
            );
        })
        .build();
~~~

Khi build RSocketStrategies, Spring tạo MetadataExtractor dùng các Decoder đã cấu hình. Mỗi đăng ký metadataToExtract xác định:

- MIME type của entry cần đọc.
- Kiểu Java mà Decoder sẽ tạo.
- Tên header để message handler truy cập giá trị.

Ví dụ đăng ký tenant entry có nghĩa: khi responder nhận entry MIME type TENANT_MIME, giải mã thành TenantContext và đặt object vào header tenant.

Nếu một MIME type không có Decoder phù hợp, metadata không thể được giải mã theo cấu hình đó. Vì vậy phải đăng ký Decoder trước hoặc đồng thời với metadata extractor registry.

## 7. Đọc metadata bằng @Header và @Headers

Sau khi MetadataExtractor đưa giá trị vào message headers, @MessageMapping có thể nhận metadata theo tên:

~~~java
@Controller
public class InventoryController {

    private final InventoryService inventoryService;

    public InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @MessageMapping("inventory.check")
    public Mono<InventoryResult> check(
            InventoryCheckRequest request,
            @Header("tenant") TenantContext tenant,
            @Header("correlation") CorrelationContext correlation) {

        return inventoryService.check(
            tenant.tenantId(),
            request.sku(),
            request.quantity(),
            correlation.correlationId()
        );
    }
}
~~~

@Header("tenant") và @Header("correlation") phải khớp đúng tên đã đăng ký trong metadataExtractorRegistry.

Nếu handler cần đọc nhiều giá trị metadata, có thể nhận tất cả dưới dạng Map:

~~~java
@MessageMapping("inventory.check")
public Mono<InventoryResult> check(
        InventoryCheckRequest request,
        @Headers Map<String, Object> headers) {

    TenantContext tenant =
        (TenantContext) headers.get("tenant");

    CorrelationContext correlation =
        (CorrelationContext) headers.get("correlation");

    return inventoryService.check(
        tenant.tenantId(),
        request.sku(),
        request.quantity(),
        correlation.correlationId()
    );
}
~~~

Khi dùng Map, ứng dụng cần kiểm tra kiểu và sự hiện diện của từng key trước khi ép kiểu. Với metadata bắt buộc, có thể validate sớm và trả lỗi nếu thiếu hoặc sai định dạng.

### Metadata mặc định và metadata tùy chỉnh

DefaultMetadataExtractor đã nhận biết routing metadata chuẩn. Không cần tự đăng ký route MIME type chỉ để dùng .route() của RSocketRequester.

Các metadata entry tùy chỉnh như tenant, correlation hoặc tracing cần được đăng ký riêng. Việc một entry xuất hiện trong Composite Metadata không có nghĩa Spring tự động chuyển mọi entry thành header.

## 8. Cấu hình strategies cho RSocketMessageHandler

Trong ứng dụng Spring tự cấu hình server, cần bảo đảm RSocketMessageHandler sử dụng đúng RSocketStrategies:

~~~java
@Configuration
public class RSocketServerConfiguration {

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
            .encoders(encoders ->
                encoders.add(new Jackson2JsonEncoder())
            )
            .decoders(decoders ->
                decoders.add(new Jackson2JsonDecoder())
            )
            .metadataExtractorRegistry(registry -> {
                registry.metadataToExtract(
                    TENANT_MIME,
                    TenantContext.class,
                    "tenant"
                );
                registry.metadataToExtract(
                    CORRELATION_MIME,
                    CorrelationContext.class,
                    "correlation"
                );
            })
            .build();
    }

    @Bean
    RSocketMessageHandler rSocketMessageHandler(
            RSocketStrategies rSocketStrategies) {

        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(rSocketStrategies);
        return handler;
    }
}
~~~

Spring Boot có thể tự cấu hình RSocketMessageHandler dựa trên các bean trong ApplicationContext. Trong trường hợp dùng auto-configuration, hãy khai báo RSocketStrategies bean theo cơ chế cấu hình của phiên bản Spring Boot đang dùng và xác nhận handler thực tế sử dụng bean đó.

Nếu tự tạo RSocketMessageHandler, gọi setRSocketStrategies để gắn encoder, decoder, route matcher và metadata extractor. Chỉ tạo một strategies bean nhưng không gắn vào handler tự tạo sẽ không bảo đảm custom metadata được trích xuất.

### Chia sẻ strategies giữa client và server

Nếu một tiến trình vừa gửi vừa nhận RSocket, có thể tái sử dụng một RSocketStrategies bean. Điều này giúp thống nhất codec và metadata mapping. Tuy nhiên, hai dịch vụ chạy độc lập không chia sẻ bean runtime; mỗi phía phải cấu hình tương thích với cùng hợp đồng wire.

RSocketStrategies không chứa dữ liệu tenant hoặc credential cụ thể của từng request. Nó chỉ định nghĩa cách mã hóa/giải mã và cách trích xuất metadata.

## 9. Metadata DTO và metadata dạng Map

Metadata entry không nhất thiết phải ánh xạ thành một DTO riêng. Một entry JSON có thể chứa Map nếu schema là tập hợp key-value.

Ví dụ đăng ký kiểu generic:

~~~java
MimeType CONTEXT_MAP_MIME =
    MimeType.valueOf(
        "application/vnd.acme.context-v1+json"
    );

RSocketStrategies strategies = RSocketStrategies.builder()
    .decoders(decoders ->
        decoders.add(new Jackson2JsonDecoder())
    )
    .metadataExtractorRegistry(registry -> {
        registry.metadataToExtract(
            CONTEXT_MAP_MIME,
            new ParameterizedTypeReference<Map<String, String>>() {},
            (contextMap, outputMap) -> {
                outputMap.putAll(contextMap);
            }
        );
    })
    .build();
~~~

Trong ví dụ này, Decoder giải mã metadata thành Map<String, String>. Callback quyết định cách đưa các entry trong Map vào message headers.

ParameterizedTypeReference giữ lại thông tin generic mà Java type erasure có thể làm mất. Nếu dùng Map.class đơn thuần, kiểu phần tử cụ thể có thể không được xác định đầy đủ.

Dùng DTO khi metadata có schema ổn định và cần kiểm soát field. Dùng Map khi entry thực sự là một tập key-value linh hoạt, nhưng phải kiểm tra key cho phép, kiểu dữ liệu, kích thước và giá trị.

Không dùng một Map tùy ý để đưa mọi field của client thành header. Chỉ trích xuất các key đã được định nghĩa trong hợp đồng, tránh ghi đè header hệ thống như route hoặc các giá trị bảo mật.

## 10. Khi requester không dùng Composite Metadata

Composite Metadata là mặc định của RSocketRequester và phù hợp khi request cần nhiều loại metadata entry độc lập. Tuy nhiên, một peer có thể dùng một metadata MIME type đơn chứa một object hoặc Map tổng hợp.

Trong trường hợp đó, MetadataExtractor có thể đăng ký MIME type đơn và tự ánh xạ giá trị đã decode vào output map:

~~~java
MimeType CONTEXT_MIME =
    MimeType.valueOf(
        "application/vnd.acme.context+json"
    );

RSocketStrategies strategies =
    RSocketStrategies.builder()
        .decoders(decoders ->
            decoders.add(new Jackson2JsonDecoder())
        )
        .metadataExtractorRegistry(registry -> {
            registry.metadataToExtract(
                CONTEXT_MIME,
                new ParameterizedTypeReference<Map<String, String>>() {},
                (context, output) -> {
                    output.putAll(context);
                }
            );
        })
        .build();
~~~

Đây là một hợp đồng metadata đơn. Không gửi đồng thời nhiều entry khác MIME type vào metadata section theo cách của Composite Metadata nếu SETUP đã khai báo metadata MIME type đơn.

Khi cần route, authentication và tracing độc lập, Composite Metadata thường dễ mở rộng và ít ràng buộc hơn. Khi peer chỉ hỗ trợ một object metadata tổng hợp, cần thống nhất schema object đó ở cả hai phía.

## 11. Encoder và Decoder được chọn như thế nào?

RSocketStrategies tìm codec tương thích theo kiểu dữ liệu và MIME type:

- Encoder cần hỗ trợ kiểu object và MIME type của entry.
- Decoder cần hỗ trợ kiểu đích và MIME type của entry.
- Nếu không tìm thấy codec phù hợp, thao tác encode/decode không thể tiếp tục.

Ví dụ cùng một Jackson encoder có thể xử lý nhiều kiểu DTO JSON nếu MIME type được hỗ trợ:

~~~java
encoders.add(new Jackson2JsonEncoder());
decoders.add(new Jackson2JsonDecoder());
~~~

Nhưng không phải mọi custom MIME type đều được hỗ trợ tự động. Nếu codec có danh sách supported MIME types giới hạn, hãy cấu hình nó để hỗ trợ application/vnd.acme.*+json hoặc cung cấp codec riêng.

Khi có custom binary format, đăng ký Encoder/Decoder chuyên biệt. Đừng cố giải mã dữ liệu Protobuf bằng Jackson JSON chỉ vì cả hai đều là byte array.

### Một MIME type nên có một hợp đồng rõ

| MIME type | Kiểu Java phía nhận | Vai trò |
|---|---|---|
| application/vnd.acme.tenant-v1+json | TenantContext | Tenant context |
| application/vnd.acme.correlation-v1+json | CorrelationContext | Correlation ID |
| application/vnd.acme.trace-v1+json | TraceContext | Trace context |
| message/x.rsocket.routing.v0 | String | Route chuẩn RSocket |

Nếu cùng một MIME type được dùng cho nhiều schema không tương thích, Decoder không thể biết nên tạo kiểu nào. Hãy tách MIME type hoặc định nghĩa envelope có discriminator rõ ràng.

## 12. Versioning và tương thích schema

Metadata là một phần của hợp đồng giữa các dịch vụ. Khi thay đổi schema, cần đảm bảo client và server nâng cấp độc lập vẫn tương thích.

Ví dụ MIME type versioned:

~~~text
application/vnd.acme.tenant-v1+json
application/vnd.acme.tenant-v2+json
~~~

Server có thể đăng ký decoder/extractor cho cả hai version trong giai đoạn chuyển tiếp:

~~~java
RSocketStrategies versionedStrategies = RSocketStrategies.builder()
    .decoders(decoders ->
        decoders.add(new Jackson2JsonDecoder())
    )
    .metadataExtractorRegistry(registry -> {
        registry.metadataToExtract(
            TENANT_V1_MIME,
            TenantContextV1.class,
            "tenantV1"
        );
        registry.metadataToExtract(
            TENANT_V2_MIME,
            TenantContextV2.class,
            "tenantV2"
        );
    })
    .build();
~~~

Không nên đổi ý nghĩa của field cũ trong khi giữ nguyên MIME type. Một client cũ có thể deserialize thành công nhưng hiểu sai giá trị.

Một số quy tắc:

- Thêm field tùy chọn thường dễ tương thích hơn thêm field bắt buộc.
- Không đổi kiểu dữ liệu của field đang dùng.
- Không tái sử dụng tên field cho ý nghĩa mới.
- Định nghĩa rõ hành vi với field lạ và field bị thiếu.
- Duy trì decoder cũ trong thời gian chuyển đổi nếu cần hỗ trợ client cũ.
- Ghi lại MIME type, schema version và thời điểm ngừng hỗ trợ version cũ.

## 13. Kiểm tra lỗi encoding và decoding

Các lỗi thường gặp:

| Triệu chứng | Nguyên nhân | Cách kiểm tra |
|---|---|---|
| .metadata() báo không tìm được Encoder | Không có encoder phù hợp với kiểu object/MIME | Kiểm tra strategies.encoders và canEncode |
| Metadata đến server nhưng không có header | Chưa đăng ký metadataToExtract | Kiểm tra registry và tên header |
| Decode lỗi hoặc tạo DTO sai | JSON schema hoặc MIME type không khớp | Kiểm tra bytes, MIME và DTO |
| Route không được tìm thấy | Sai route hoặc metadata MIME type không đúng | Kiểm tra .route() và Composite Metadata |
| Một entry bị bỏ qua | MIME type chưa được hỗ trợ/extract | Đăng ký decoder/extractor |
| Client và server khác version | Schema không tương thích | Thêm version hoặc giữ tương thích ngược |
| Metadata bắt buộc bị thiếu | Client không gửi entry hoặc gửi sai MIME | Validate ở handler và trả lỗi rõ ràng |

Kết nối RSocket có thể SETUP thành công nhưng request vẫn lỗi khi encode hoặc decode một metadata entry. Vì vậy, khi chẩn đoán cần phân biệt lỗi transport/SETUP với lỗi codec ở từng message.

Không log token, credential hoặc toàn bộ metadata nhạy cảm. Khi debug, có thể ghi MIME type, tên entry và correlation ID đã được che phù hợp.

## 14. Kiểm thử Composite Metadata end-to-end

Unit test cho Encoder/Decoder hữu ích nhưng chưa chứng minh requester và responder thực sự dùng đúng strategies. Nên có integration test chạy qua RSocket transport để kiểm tra cả quá trình.

Ví dụ gửi tenant và correlation metadata:

~~~java
@Test
void encodesAndExtractsCompositeMetadata() {
    Mono<InventoryResult> response = requester
        .route("inventory.check")
        .metadata(
            new TenantContext("tenant-17"),
            TENANT_MIME
        )
        .metadata(
            new CorrelationContext("corr-91"),
            CORRELATION_MIME
        )
        .data(new InventoryCheckRequest("SKU-42", 3))
        .retrieveMono(InventoryResult.class);

    StepVerifier.create(response)
        .expectNextMatches(result ->
            result.sku().equals("SKU-42")
                && result.available()
        )
        .verifyComplete();
}
~~~

Handler phía server nên dùng @Header để nhận hai metadata DTO. Test có thể xác nhận tenant và correlation đã đến service đúng giá trị, không chỉ xác nhận response có dữ liệu.

### Ma trận test nên có

| Trường hợp | Kết quả mong đợi |
|---|---|
| Gửi một custom metadata entry | Entry được decode đúng |
| Gửi nhiều entry khác MIME type | Mỗi entry được decode bằng Decoder tương ứng |
| Gửi route cùng custom metadata | Đúng @MessageMapping và đúng headers |
| Thiếu metadata bắt buộc | Validation thất bại theo hợp đồng |
| Gửi MIME type không được hỗ trợ | Có lỗi hoặc chính sách bỏ qua được định nghĩa |
| Gửi metadata sai JSON | Decode thất bại, log có correlation |
| Gửi version cũ | Decoder cũ xử lý hoặc từ chối rõ ràng |
| Client/server dùng codec khác nhau | Contract test phát hiện không tương thích |
| Metadata quá lớn | Bị giới hạn trước khi tiêu thụ tài nguyên quá mức |

### Kiểm tra codec riêng

Có thể kiểm tra encoder và decoder bằng fixture JSON:

~~~json
{
  "tenantId": "tenant-17"
}
~~~

Test cần xác nhận object sau decode có tenantId đúng. Với contract test giữa hai dịch vụ độc lập, nên dùng DTO riêng ở mỗi phía hoặc JSON fixture dùng chung, tránh việc cả hai phía dùng chung một class khiến sai khác schema không được phát hiện.

## 15. Bảo mật khi giải mã metadata

Metadata có thể chứa tenant, identity, token hoặc tracing context. Giải mã thành công không đồng nghĩa thông tin đó đáng tin cậy.

Các nguyên tắc:

- Không xem tenantId do client gửi là bằng chứng client có quyền truy cập tenant đó.
- Xác thực principal bằng cơ chế bảo mật đã cấu hình.
- Đối chiếu tenant metadata với principal đã xác thực.
- Kiểm tra MIME type và schema trước khi sử dụng giá trị.
- Giới hạn số entry và kích thước metadata.
- Không log credential hoặc dữ liệu cá nhân không cần thiết.
- Dùng TLS cho TCP hoặc WSS khi truyền qua mạng không tin cậy.

MetadataExtractor chỉ chuyển byte thành giá trị ứng dụng. Nó không tự xác thực token, không cấp quyền và không thay thế authorization.

## 16. Quy trình triển khai

Khi thêm một loại Composite Metadata mới, thực hiện theo thứ tự:

1. Chọn MIME type riêng, có namespace và version.
2. Định nghĩa DTO hoặc schema cho entry.
3. Đăng ký Encoder ở phía gửi.
4. Đăng ký Decoder ở phía nhận.
5. Đăng ký metadataToExtract với MIME type, kiểu đích và tên header.
6. Cấu hình RSocketStrategies cho requester và responder.
7. Xác nhận metadata MIME type của kết nối là Composite Metadata.
8. Gửi entry bằng .metadata(value, mimeType).
9. Đọc giá trị bằng @Header hoặc @Headers.
10. Kiểm thử nhiều entry, MIME type không hỗ trợ, schema cũ và trường hợp metadata thiếu.

Encoding và decoding phải được xem là hai nửa của cùng một hợp đồng. Encoder tạo byte theo MIME type; Composite Metadata giữ các entry độc lập; MetadataExtractor chọn Decoder và đưa giá trị vào headers. Khi ba phần này thống nhất, các dịch vụ có thể thêm metadata mới mà không làm thay đổi data payload hoặc buộc phải chia sẻ Java class.

## Ghi nhớ

- Composite Metadata chứa nhiều entry độc lập, mỗi entry có MIME type riêng.
- RSocketStrategies tập hợp Encoder, Decoder, MetadataExtractor và các chiến lược liên quan.
- .metadata(value, mimeType) dùng Encoder phù hợp để mã hóa custom metadata entry.
- MetadataExtractor dùng Decoder để giải mã entry và ánh xạ thành header.
- Routing metadata chuẩn đã được DefaultMetadataExtractor hỗ trợ sẵn.
- Custom metadata cần đăng ký bằng metadataToExtract.
- MIME type của kết nối là Composite Metadata khi cần nhiều entry.
- Codec phải hỗ trợ cả kiểu dữ liệu và MIME type thực tế.
- Hai phía cần thống nhất schema và version.
- Giải mã metadata không đồng nghĩa xác thực hoặc phân quyền.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — RSocketStrategies API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [Spring Framework — RSocketStrategies.Builder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.Builder.html)
- [Spring Framework — MetadataExtractor API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractor.html)
- [Spring Framework — RSocketRequester API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [RSocket Composite Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/CompositeMetadata.md)

