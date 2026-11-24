# Phối hợp MIME type và codec giữa hai ứng dụng độc lập

Khi hai ứng dụng Java độc lập giao tiếp qua RSocket, chúng không chia sẻ class Java hay cấu hình nội bộ. Chúng chỉ trao đổi các byte trong payload. Để hai phía hiểu cùng một thông điệp, requester và responder phải thống nhất **MIME type**, định dạng dữ liệu và codec dùng để mã hóa/giải mã. Nếu một phía gửi JSON nhưng phía kia giải mã theo CBOR, hoặc metadata được gửi bằng một MIME type mà server chưa đăng ký decoder, interaction có thể thất bại dù kết nối RSocket đã được thiết lập thành công.

Trong Spring, RSocketStrategies tập hợp encoder, decoder và MetadataExtractor. RSocketRequester sử dụng các thành phần này ở phía gửi; RSocketMessageHandler sử dụng chúng ở phía nhận. Bài học này hướng dẫn thiết kế hợp đồng MIME type giữa hai ứng dụng độc lập, cấu hình data codec và metadata codec, truyền custom metadata bằng Composite Metadata, trích xuất metadata ở responder và kiểm thử khả năng tương thích.

Sau bài học, bạn có thể:

- Phân biệt data MIME type, metadata MIME type của kết nối và MIME type của từng entry trong Composite Metadata.
- Giải thích cách Spring chọn Encoder và Decoder theo kiểu dữ liệu và MIME type.
- Cấu hình RSocketStrategies ở requester và responder.
- Gửi custom metadata có kiểu bằng RSocketRequester và đọc nó qua @Header.
- Thiết kế hợp đồng JSON/metadata ổn định giữa hai ứng dụng không dùng chung Java DTO.
- Xử lý lỗi do MIME type, codec hoặc schema không tương thích.
- Kiểm thử serialization, deserialization và metadata extraction ở cả hai phía.

## 1. Hai ứng dụng độc lập cần thống nhất điều gì?

Giả sử Order Service chạy ở một tiến trình và Inventory Service chạy ở một tiến trình khác. Order Service gửi yêu cầu kiểm tra tồn kho qua RSocket. Hai ứng dụng có thể dùng các class Java khác nhau, nhưng phải hiểu cùng cấu trúc dữ liệu trên wire.

Một kết nối RSocket cần thống nhất ít nhất:

1. Data MIME type: định dạng byte của phần data.
2. Metadata MIME type: định dạng của toàn vùng metadata trong payload.
3. Entry MIME type: nếu dùng Composite Metadata, mỗi entry có MIME type riêng.
4. Schema: cấu trúc field, kiểu dữ liệu, giá trị bắt buộc và quy tắc version.
5. Codec: encoder/decoder có thể chuyển đổi kiểu dữ liệu ứng dụng sang byte và ngược lại.

~~~mermaid
flowchart LR
    subgraph A[Order Service]
        A1[Java DTO]
        A2[Encoder]
        A3[Data + metadata bytes]
        A1 --> A2 --> A3
    end
    A3 --> B[RSocket transport]
    B --> C[Data + metadata bytes]
    subgraph D[Inventory Service]
        D1[Decoder]
        D2[Application DTO]
        C --> D1 --> D2
    end
~~~

Không cần hai ứng dụng dùng cùng tên class, package hoặc phiên bản thư viện Spring. Chúng cần tuân theo cùng hợp đồng wire. Ví dụ Order Service có thể dùng record InventoryCheckRequest, còn Inventory Service dùng class CheckStockCommand; nếu hai kiểu được mã hóa thành JSON tương thích với cùng schema thì hai phía vẫn giao tiếp được.

Ngược lại, cùng dùng class tên InventoryCheckRequest cũng không bảo đảm tương thích nếu một bên mã hóa trường quantity thành chuỗi còn bên kia chờ số nguyên.

## 2. Phân biệt ba cấp MIME type

RSocket có hai MIME type được khai báo trong SETUP của kết nối: data MIME type và metadata MIME type. Nếu metadata MIME type là Composite Metadata, từng entry trong vùng metadata lại có MIME type riêng.

| Cấp | Khai báo ở đâu? | Mô tả | Ví dụ |
|---|---|---|---|
| Data MIME type | SETUP | Cách diễn giải data payload trên kết nối | application/json |
| Metadata MIME type | SETUP | Cách diễn giải toàn bộ metadata section | message/x.rsocket.composite-metadata.v0 |
| Entry MIME type | Header của từng entry composite | Cách diễn giải nội dung của một metadata entry | application/vnd.acme.tenant-v1+json |

Ví dụ một request:

~~~text
SETUP
  data MIME type     = application/json
  metadata MIME type = message/x.rsocket.composite-metadata.v0

REQUEST_RESPONSE
  metadata:
    message/x.rsocket.routing.v0
      route = inventory.check
    application/vnd.acme.tenant-v1+json
      {"tenantId":"tenant-17"}
    application/vnd.acme.trace-v1+json
      {"correlationId":"corr-91"}
  data:
    {"sku":"SKU-42","quantity":3}
~~~

Data MIME type không phải MIME type của route hoặc tenant metadata. Metadata MIME type composite chỉ mô tả cấu trúc bao ngoài; MIME type của từng entry cho biết cách giải mã nội dung cụ thể.

Khi cần route cùng custom metadata, Composite Metadata thường là định dạng phù hợp. Nếu khai báo metadata MIME type của kết nối là một định dạng metadata đơn, không thể mặc nhiên gửi thêm các entry có định dạng khác như thể chúng nằm trong Composite Metadata.

## 3. MIME type được xác lập ở thời điểm SETUP

Requester khởi tạo kết nối và gửi SETUP frame. SETUP chứa data MIME type và metadata MIME type mà kết nối sử dụng. Đây là thông tin ở cấp kết nối, không phải giá trị có thể thay đổi tùy ý cho từng request.

Điều đó có ba hệ quả:

- Hai phía phải hiểu cùng định dạng data và metadata đã được chọn trong SETUP.
- Codec phải hỗ trợ MIME type tương ứng trước khi ứng dụng gửi hoặc nhận payload.
- Muốn thay đổi định dạng mặc định ở cấp kết nối, cần thay đổi cấu hình kết nối; không thể chỉ đổi MIME type cho một lần gọi RSocketRequester rồi kỳ vọng peer tự suy ra.

RSocket không tự trao đổi danh sách tất cả codec mà mỗi ứng dụng đã cài. Khai báo MIME type không tự cài đặt codec hoặc chuyển đổi schema. Ứng dụng phải cấu hình encoder/decoder tương ứng ở cả hai phía.

Ví dụ khai báo rõ cấu hình ở client:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .metadataMimeType(COMPOSITE_METADATA)
    .tcp("inventory.internal", 7000);
~~~

Trong đó COMPOSITE_METADATA là MimeType có giá trị message/x.rsocket.composite-metadata.v0. Hằng số này chỉ rõ toàn vùng metadata dùng định dạng composite.

Không nhầm MIME type trong SETUP với MIME type của một entry metadata. Ví dụ application/vnd.acme.tenant-v1+json là MIME type của tenant entry; nó không thay thế message/x.rsocket.composite-metadata.v0 khi kết nối cần nhiều loại metadata.

## 4. Encoder và Decoder trong Spring

Encoder chuyển đổi object Java thành byte. Decoder chuyển byte thành kiểu dữ liệu ứng dụng. Spring chọn codec dựa trên kiểu dữ liệu, MIME type và khả năng hỗ trợ của từng Encoder/Decoder.

Với JSON, Spring cung cấp Jackson2JsonEncoder và Jackson2JsonDecoder. Ví dụ cấu hình:

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

Cấu hình này đăng ký codec JSON. Khi ứng dụng gửi một DTO với data MIME type application/json, encoder JSON có thể serialize object. Ở phía nhận, decoder JSON chuyển byte thành kiểu được handler yêu cầu.

RSocketStrategies còn có thể cấu hình:

- MetadataExtractorRegistry để trích xuất metadata.
- RouteMatcher để tùy chỉnh cách so khớp route.
- DataBufferFactory hoặc thành phần liên quan đến buffer theo nhu cầu.
- Các encoder/decoder chuyên biệt cho định dạng ứng dụng.

Không phải mọi codec đều hỗ trợ mọi MIME type. Khi thêm codec mới, hãy xác minh canEncode/canDecode cho đúng kiểu và media type mà hai ứng dụng sử dụng.

### Data codec và metadata codec dùng chung hay riêng?

RSocketStrategies cung cấp tập encoder/decoder cho các thao tác chuyển đổi của Spring. Cùng một Jackson encoder/decoder có thể xử lý cả data JSON và custom metadata JSON nếu MIME type nằm trong các media type mà codec hỗ trợ.

Tuy nhiên, data và metadata có hợp đồng khác nhau. Hãy quản lý schema riêng, dù chúng dùng chung implementation JSON. Ví dụ InventoryCheckRequest là data schema; TenantContext là metadata schema. Thay đổi tenant metadata không nên làm thay đổi cấu trúc request data.

## 5. Cấu hình requester độc lập

Ứng dụng client cần encoder để gửi request và metadata, decoder để đọc response. Có thể tạo RSocketStrategies riêng:

~~~java
@Configuration
public class InventoryClientConfiguration {

    @Bean
    RSocketStrategies inventoryClientStrategies() {
        return RSocketStrategies.builder()
            .encoders(encoders ->
                encoders.add(new Jackson2JsonEncoder())
            )
            .decoders(decoders ->
                decoders.add(new Jackson2JsonDecoder())
            )
            .build();
    }

    @Bean
    RSocketRequester inventoryRequester(
            RSocketStrategies inventoryClientStrategies) {

        return RSocketRequester.builder()
            .rsocketStrategies(inventoryClientStrategies)
            .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
            .metadataMimeType(COMPOSITE_METADATA)
            .tcp("inventory.internal", 7000);
    }
}
~~~

Sau đó gửi DTO:

~~~java
Mono<InventoryResult> checkStock(String sku, int quantity) {
    return inventoryRequester
        .route("inventory.check")
        .data(new InventoryCheckRequest(sku, quantity))
        .retrieveMono(InventoryResult.class);
}
~~~

RSocketRequester sử dụng data MIME type đã cấu hình và encoder phù hợp để serialize InventoryCheckRequest. Khi nhận response, nó dùng decoder để tạo InventoryResult.

Ứng dụng client không cần import class DTO từ Inventory Service. Có thể định nghĩa DTO tương ứng trong module hợp đồng riêng hoặc tạo class cục bộ có cùng cấu trúc wire.

## 6. Cấu hình responder độc lập

Ở phía server, Spring cần decoder để chuyển data byte thành tham số handler và encoder để serialize response. Nếu dùng custom metadata, server cũng cần decoder tương ứng và MetadataExtractor để đưa metadata vào message headers.

Ví dụ cấu hình server:

~~~java
@Configuration
public class InventoryRSocketConfiguration {

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
                    TENANT_METADATA_MIME,
                    TenantContext.class,
                    "tenant"
                );
            })
            .build();
    }
}
~~~

Spring Boot có thể sử dụng bean RSocketStrategies để cấu hình message handling. Nếu tự tạo RSocketMessageHandler, cần gắn strategies vào message handler để codec và MetadataExtractor được áp dụng.

Handler nhận data và metadata:

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
            @Header("tenant") TenantContext tenant) {

        return inventoryService.check(
            tenant.tenantId(),
            request.sku(),
            request.quantity()
        );
    }
}
~~~

Route inventory.check được giải mã từ routing metadata. Data được giải mã thành InventoryCheckRequest. Metadata entry có MIME type TENANT_METADATA_MIME được decoder JSON chuyển thành TenantContext và được đưa vào header tên tenant.

Tên trong @Header phải khớp tên đã đăng ký với metadataToExtract. Nếu thiếu cấu hình extraction hoặc decoder, tham số header có thể không được phân giải như mong đợi.

## 7. Phối hợp custom metadata với Composite Metadata

Một payload có thể cần route cùng tenant, correlation ID hoặc thông tin ngữ cảnh khác. Với Spring RSocketRequester, có thể thêm metadata object cùng MIME type riêng.

Khai báo MIME type:

~~~java
private static final MimeType COMPOSITE_METADATA =
    MimeTypeUtils.parseMimeType(
        "message/x.rsocket.composite-metadata.v0"
    );

private static final MimeType TENANT_METADATA_MIME =
    MimeTypeUtils.parseMimeType(
        "application/vnd.acme.tenant-v1+json"
    );

private static final MimeType CORRELATION_METADATA_MIME =
    MimeTypeUtils.parseMimeType(
        "application/vnd.acme.correlation-v1+json"
    );
~~~

Gửi nhiều metadata:

~~~java
Mono<InventoryResult> checkStock(
        InventoryCheckRequest request,
        TenantContext tenant,
        CorrelationContext correlation) {

    return inventoryRequester
        .route("inventory.check")
        .metadata(tenant, TENANT_METADATA_MIME)
        .metadata(correlation, CORRELATION_METADATA_MIME)
        .data(request)
        .retrieveMono(InventoryResult.class);
}
~~~

Mỗi lời gọi metadata thêm một entry vào Composite Metadata. Route cũng được biểu diễn bằng routing metadata. Data request vẫn được mã hóa riêng theo data MIME type của kết nối.

Server đăng ký cả hai entry:

~~~java
.metadataExtractorRegistry(registry -> {
    registry.metadataToExtract(
        TENANT_METADATA_MIME,
        TenantContext.class,
        "tenant"
    );
    registry.metadataToExtract(
        CORRELATION_METADATA_MIME,
        CorrelationContext.class,
        "correlation"
    );
})
~~~

Handler có thể nhận cả hai:

~~~java
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
~~~

Các kiểu TenantContext và CorrelationContext là DTO độc lập của ứng dụng. Client và server không cần dùng chung Java class nhưng phải thống nhất MIME type và schema JSON.

### Routing metadata được xử lý riêng

Khi gọi route("inventory.check"), Spring thêm routing metadata theo định dạng chuẩn RSocket. Không cần tự tạo một custom JSON entry cho route nếu dùng API route của RSocketRequester.

Routing metadata và custom metadata có thể cùng nằm trong Composite Metadata. Điều này giúp responder vừa chọn đúng @MessageMapping vừa trích xuất tenant/correlation context.

## 8. Thiết kế schema để hai ứng dụng không phụ thuộc class Java

MIME type cho biết cách giải mã byte, nhưng không mô tả đầy đủ cấu trúc nghiệp vụ. Hai ứng dụng cần một hợp đồng schema.

Ví dụ request JSON:

~~~json
{
  "sku": "SKU-42",
  "quantity": 3
}
~~~

Response JSON:

~~~json
{
  "sku": "SKU-42",
  "available": true,
  "availableQuantity": 18
}
~~~

Client có thể định nghĩa:

~~~java
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

Server có thể định nghĩa class khác:

~~~java
public class CheckStockCommand {
    private String sku;
    private int quantity;

    // Constructor, getters and setters
}
~~~

Điều quan trọng là hai class ánh xạ đến cùng field và kiểu dữ liệu trên wire. Các khác biệt như tên field, casing, kiểu số, format ngày giờ hoặc xử lý null có thể gây lỗi dù cả hai phía đều dùng JSON.

Hãy thống nhất:

- Tên field và quy tắc casing.
- Kiểu dữ liệu và miền giá trị.
- Field bắt buộc và field tùy chọn.
- Giá trị mặc định khi field vắng mặt.
- Format timestamp và timezone.
- Quy tắc enum và giá trị không nhận diện.
- Cách xử lý field mới hoặc field đã bị loại bỏ.

Không dùng Java native serialization làm hợp đồng giữa các ứng dụng độc lập. Nó gắn wire format với class implementation và khó tương thích khi thay đổi phiên bản.

## 9. Versioning MIME type và schema

Với custom metadata, nên đặt MIME type có namespace và version để biểu thị hợp đồng:

~~~text
application/vnd.acme.tenant-v1+json
application/vnd.acme.correlation-v1+json
~~~

Khi schema thay đổi không tương thích, có thể tạo MIME type mới:

~~~text
application/vnd.acme.tenant-v2+json
~~~

Server có thể đăng ký decoder/extractor cho cả v1 và v2 trong giai đoạn chuyển tiếp. Client chọn version mà server hỗ trợ theo hợp đồng triển khai.

Với data MIME type, có thể dùng application/json chung và version hóa schema bằng field version hoặc envelope. Nếu hai phiên bản data không tương thích, cần một cơ chế version rõ ràng ở cấp route, metadata hoặc MIME type được cả hai phía hiểu.

| Thay đổi | Tương thích thường gặp | Hướng xử lý |
|---|---|---|
| Thêm field tùy chọn | Có thể tương thích | Decoder cũ bỏ qua field lạ nếu cấu hình cho phép |
| Thêm field bắt buộc | Thường không tương thích | Có default hoặc version mới |
| Đổi kiểu field | Không tương thích | Version schema mới |
| Đổi tên field | Không tương thích nếu không có alias | Duy trì alias hoặc version mới |
| Xóa field đang dùng | Có thể phá client cũ | Giai đoạn deprecation |
| Thêm giá trị enum | Phụ thuộc client có xử lý giá trị lạ không | Định nghĩa unknown/default behavior |

Không giả định mọi JSON decoder đều tự bỏ qua hoặc xử lý field lạ giống nhau trong mọi cấu hình. Hãy xác định rõ ObjectMapper và schema policy ở cả hai ứng dụng.

## 10. Khi nào cần codec khác JSON?

JSON dễ đọc và phù hợp cho nhiều API, nhưng không phải lựa chọn duy nhất. Một hệ thống có thể dùng CBOR, Protobuf hoặc định dạng nhị phân khác nếu cả hai phía hỗ trợ.

| Định dạng | Đặc điểm | Cân nhắc |
|---|---|---|
| JSON | Dễ đọc, phổ biến, tương thích rộng | Kích thước lớn hơn một số định dạng nhị phân |
| CBOR | Nhị phân, cấu trúc gần JSON | Cần codec và schema thống nhất |
| Protobuf | Schema rõ, gọn và hiệu quả | Cần quản lý .proto và tương thích field number |
| Custom binary | Có thể tối ưu theo nghiệp vụ | Tăng chi phí duy trì và kiểm thử liên thông |

Khi dùng codec khác JSON, đăng ký Encoder/Decoder tương ứng trong RSocketStrategies và khai báo MIME type thống nhất. Đừng chỉ đổi dataMimeType ở client; server cũng phải có decoder hỗ trợ định dạng đó.

Với Protobuf, nên version hóa schema bằng quy tắc tương thích của Protobuf. Không tái sử dụng field number đã bị loại bỏ và không đổi kiểu field tùy tiện. MIME type chỉ nhận diện định dạng; schema vẫn phải được quản lý riêng.

## 11. Lỗi thường gặp khi MIME type và codec không khớp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Client serialize được nhưng server không decode | Server thiếu decoder hoặc media type không khớp | Đăng ký decoder đúng MIME type |
| Server trả response nhưng client không đọc được | Client thiếu decoder cho response MIME type | Đăng ký codec tương ứng ở requester |
| Metadata không xuất hiện trong @Header | Chưa đăng ký metadataToExtract hoặc tên header sai | Kiểm tra registry và @Header |
| Route không được ánh xạ | Metadata MIME type không phải composite hoặc route entry sai | Cấu hình Composite Metadata và dùng route() |
| Một custom metadata entry bị bỏ qua | MIME type không được nhận diện/extract | Đăng ký MIME type và decoder |
| JSON decode thành sai kiểu | Schema field, casing hoặc kiểu dữ liệu khác nhau | Đồng bộ schema và kiểm thử contract |
| Kết nối thất bại ở SETUP | MIME type hoặc tính năng SETUP không được peer chấp nhận | Kiểm tra cấu hình kết nối và hỗ trợ protocol |
| Không encode được DTO | Không có Encoder phù hợp cho class/media type | Thêm codec hoặc dùng kiểu được hỗ trợ |

Cần phân biệt lỗi thiết lập kết nối với lỗi chuyển đổi payload. Kết nối có thể SETUP thành công nhưng request sau đó vẫn lỗi vì server không decode được data hoặc metadata.

## 12. Kiểm thử hợp đồng giữa hai ứng dụng

Unit test codec chỉ xác nhận một ứng dụng tự encode/decode được dữ liệu của nó. Để chứng minh hai ứng dụng độc lập tương thích, cần kiểm thử theo hợp đồng wire.

Một bộ kiểm thử nên có:

1. Client serialize request bằng MIME type đã công bố.
2. Server decode request thành DTO của server.
3. Server trích xuất custom metadata theo MIME type riêng.
4. Server encode response.
5. Client decode response thành DTO của client.
6. Thử schema cũ và mới trong giai đoạn nâng cấp.
7. Thử MIME type không được hỗ trợ và xác nhận lỗi có thể chẩn đoán.

Ví dụ kiểm thử request qua RSocketRequester:

~~~java
@Test
void clientAndServerAgreeOnDataAndMetadata() {
    Mono<InventoryResult> response = requester
        .route("inventory.check")
        .metadata(
            new TenantContext("tenant-17"),
            TENANT_METADATA_MIME
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

Test cần chạy qua transport và message handler thực tế để kiểm tra cả SETUP MIME type, encoder/decoder, routing metadata và MetadataExtractor.

### Kiểm thử codec riêng

Có thể kiểm tra round-trip trong từng ứng dụng:

~~~java
@Test
void jsonCodecRoundTrip() {
    InventoryCheckRequest request =
        new InventoryCheckRequest("SKU-42", 3);

    // Dùng Encoder/Decoder từ RSocketStrategies trong test.
    // Xác nhận object sau decode có cùng field và giá trị.
}
~~~

Để tránh hai ứng dụng vô tình dùng chung cùng một DTO khiến test không phát hiện khác biệt schema, có thể tạo contract test với DTO riêng ở client và server, hoặc kiểm tra JSON mẫu được lưu như fixture hợp đồng.

### Kiểm thử metadata extraction

Gửi request với tenant metadata và xác nhận handler nhận đúng tenant. Bổ sung các trường hợp:

- Không có tenant metadata.
- MIME type không được hỗ trợ.
- JSON metadata sai schema.
- Metadata quá lớn.
- Tenant không được phép truy cập tài nguyên.
- Metadata version cũ trong giai đoạn chuyển đổi.

Không coi việc deserialize tenant thành công là bằng chứng tenant đã được xác thực. Server vẫn phải ràng buộc tenant với principal đã xác thực và kiểm tra quyền truy cập.

## 13. Bảo mật và giới hạn metadata

Metadata thường chứa thông tin điều khiển hoặc ngữ cảnh. Nó có thể ảnh hưởng đến route, tenant, authentication và tracing. Vì vậy cần:

- Xác thực MIME type và kích thước metadata.
- Không tin tenant ID hoặc role chỉ vì client gửi trong metadata.
- Dùng authentication metadata theo extension hoặc cơ chế bảo mật đã cấu hình.
- Không ghi access token hoặc credential vào log.
- Dùng TLS cho TCP hoặc WSS khi truyền qua mạng không tin cậy.
- Giới hạn số entry và tổng kích thước Composite Metadata.
- Từ chối metadata bắt buộc nhưng không hợp lệ; chỉ bỏ qua entry tùy chọn theo chính sách rõ ràng.

Metadata không thay thế data payload. Trường nghiệp vụ như quantity, orderId hoặc danh sách sản phẩm nên nằm trong data. Metadata phù hợp với ngữ cảnh định tuyến, tenant, correlation, tracing và authentication.

## 14. Quy trình phối hợp MIME type và codec

Khi hai ứng dụng độc lập cần kết nối RSocket, hãy thực hiện theo thứ tự:

1. Công bố data MIME type và metadata MIME type ở cấp kết nối.
2. Quyết định có dùng Composite Metadata để mang nhiều entry không.
3. Đặt MIME type riêng cho từng custom metadata entry.
4. Mô tả schema data và metadata độc lập với class Java.
5. Đăng ký Encoder ở phía gửi và Decoder ở phía nhận.
6. Đăng ký MetadataExtractor cho custom metadata cần đưa vào message headers.
7. Cấu hình RSocketRequester và RSocketMessageHandler/RSocketStrategies phù hợp.
8. Kiểm thử request, response, routing, metadata và schema compatibility qua transport thật.
9. Version hóa schema khi có thay đổi không tương thích.
10. Theo dõi lỗi encode/decode và từ chối metadata không hợp lệ theo chính sách.

MIME type xác định cách diễn giải byte; codec thực hiện chuyển đổi byte và object; schema xác định ý nghĩa của field. Ba phần này phải được quản lý như một hợp đồng chung giữa các ứng dụng. Khi hợp đồng được công bố và kiểm thử độc lập, hai hệ thống có thể phát triển khác nhau mà vẫn giao tiếp RSocket ổn định.

## Ghi nhớ

- Data MIME type và metadata MIME type được khai báo trong SETUP ở cấp kết nối.
- Composite Metadata là MIME type của toàn metadata section; từng entry có MIME type riêng.
- MIME type không tự cung cấp codec hoặc schema.
- RSocketStrategies tập hợp encoder, decoder và metadata extractor của Spring.
- RSocketRequester dùng encoder/decoder phía client; RSocketMessageHandler dùng strategies phía server.
- Custom metadata cần MIME type, decoder và MetadataExtractor phù hợp để đọc qua @Header.
- Hai ứng dụng không cần dùng chung Java DTO, nhưng phải thống nhất schema trên wire.
- Version hóa MIME type hoặc schema khi thay đổi không tương thích.
- Kiểm thử contract qua transport thật và không xem metadata do client gửi là bằng chứng xác thực.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — RSocket Strategies and Metadata](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — RSocketRequester API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Spring Framework — RSocketStrategies API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [RSocket Composite Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/CompositeMetadata.md)

