# Composite metadata và nhiều loại metadata trong cùng payload

Trong RSocket, một payload có thể mang dữ liệu nghiệp vụ và metadata đi kèm. Metadata thường chứa thông tin điều khiển hoặc ngữ cảnh như route, thông tin xác thực, trace, tenant và phiên bản hợp đồng. Khi một request cần nhiều loại thông tin như vậy, **Composite Metadata** cho phép ghép nhiều mục metadata có định dạng độc lập vào cùng một vùng metadata của payload.

Bài học này tập trung vào cách Composite Metadata được biểu diễn trên wire, cách phân biệt metadata chuẩn và metadata tùy chỉnh, cách gửi nhiều mục bằng Java/Spring Boot và cách giải mã chúng ở phía nhận. Đây là một phần của quá trình triển khai RSocket client/server qua TCP hoặc WebSocket: các loại metadata có thể đi cùng request-response, fire-and-forget, request-stream hoặc request-channel.

Sau bài học, bạn có thể:

- Giải thích vì sao một payload cần nhiều mục metadata và Composite Metadata giải quyết vấn đề gì.
- Đọc cấu trúc một entry gồm MIME type và nội dung metadata.
- Phân biệt well-known MIME type với MIME type tùy chỉnh.
- Gửi route cùng metadata nghiệp vụ bằng RSocketRequester.
- Đăng ký MetadataExtractor và đọc metadata trong handler Spring.
- Dùng API RSocket Java để mã hóa, giải mã và quản lý vòng đời ByteBuf an toàn.

## 1. Payload có hai vùng độc lập: data và metadata

RSocket biểu diễn nội dung một thông điệp bằng hai vùng:

- **Data** chứa nội dung nghiệp vụ mà ứng dụng trao đổi, chẳng hạn GetOrderRequest, Order, một sự kiện hoặc dữ liệu nhị phân.
- **Metadata** chứa thông tin mô tả hoặc điều khiển cách xử lý thông điệp, chẳng hạn route, thông tin xác thực, tracing hoặc tenant.

Hai vùng có thể dùng cách mã hóa khác nhau. MIME type cho data và MIME type cho metadata được khai báo riêng trong SETUP frame và áp dụng cho kết nối. Metadata có thể được gắn với một request hoặc payload cụ thể; metadata push là một frame riêng dùng để gửi thông báo metadata ở cấp kết nối.

~~~mermaid
flowchart TD
    A[RSocket connection] --> B[SETUP]
    B --> C[Data MIME type]
    B --> D[Metadata MIME type]
    E[Request / Payload frame] --> F[Metadata section]
    E --> G[Data section]
    F --> H[Route]
    F --> I[Authentication]
    F --> J[Tracing]
    F --> K[Application metadata]
    G --> L[Business request or event]
~~~

Ví dụ một request lấy đơn hàng có thể mang:

| Vùng | Nội dung | Mục đích |
|---|---|---|
| Data | orderId = order-42 | Xác định đơn hàng cần truy vấn |
| Metadata: routing | orders.get | Chọn handler xử lý |
| Metadata: authentication | Bearer credential | Xác thực requester |
| Metadata: tenant | tenant-17 | Xác định phạm vi dữ liệu |
| Metadata: tracing | trace/span identifiers | Theo dõi request qua nhiều dịch vụ |

Nếu không có Composite Metadata, vùng metadata thông thường được diễn giải theo một metadata MIME type đã khai báo cho kết nối. Composite Metadata cung cấp một định dạng bao ngoài để mỗi mục metadata bên trong có MIME type riêng.

Điểm cần nhớ: Composite Metadata chỉ cấu trúc **vùng metadata**. Nó không gộp metadata vào data, không thay thế payload và không tự xác thực hay giải mã dữ liệu nghiệp vụ.

## 2. Composite Metadata là gì?

Composite Metadata là một phần mở rộng của RSocket, có MIME type:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

Khi MIME type metadata của kết nối được đặt thành giá trị này, vùng metadata của một payload được hiểu là một chuỗi gồm nhiều entry nối tiếp nhau. Mỗi entry có MIME type riêng và phần byte nội dung tương ứng với MIME type đó.

Một composite metadata có thể chứa các entry độc lập như:

~~~text
Composite Metadata
  ├── message/x.rsocket.routing.v0
  │     └── route: orders.get
  ├── message/x.rsocket.authentication.v0
  │     └── bearer authentication metadata
  ├── application/vnd.acme.tenant-v1+json
  │     └── {"tenantId":"tenant-17"}
  └── message/x.rsocket.tracing-zipkin.v0
        └── trace and span information
~~~

Các mục trên cùng tồn tại trong metadata của một request. Bên nhận dựa vào MIME type của từng entry để chọn đúng decoder hoặc codec. Routing, authentication, tracing và metadata ứng dụng vì thế không phải dùng chung một cấu trúc byte.

Composite Metadata cũng cho phép một ứng dụng thêm metadata riêng mà không phải sửa định dạng của các mục chuẩn. Hai bên chỉ cần thống nhất MIME type, cấu trúc nội dung và quy tắc xử lý cho mục tùy chỉnh.

### Khi nào nên dùng?

Dùng Composite Metadata khi một thông điệp cần nhiều loại ngữ cảnh độc lập, ví dụ:

- Route để chọn handler.
- Authentication để cung cấp credential cho cơ chế bảo mật.
- Tenant hoặc organization để giới hạn phạm vi dữ liệu.
- Trace context để nối dấu vết qua các dịch vụ.
- Locale, API version hoặc feature context nếu hợp đồng ứng dụng thực sự cần.

Nếu chỉ có một mục metadata đơn giản và cả hai phía đã thống nhất một metadata MIME type riêng, có thể dùng định dạng metadata đơn. Không cần tạo nhiều entry chỉ để chuyển một trường dữ liệu nghiệp vụ nhỏ; hãy đặt trường đó trong data nếu nó thuộc nội dung request.

## 3. Cấu trúc nhị phân của một entry

Composite Metadata là các entry được nối tiếp trong một vùng byte. Mỗi entry có cấu trúc sau:

~~~text
+----------------------+--------------------------+
| MIME type header     | 1 byte                   |
+----------------------+--------------------------+
| MIME type string     | 0 hoặc 1..128 byte       |
| (chỉ với MIME tùy chỉnh)                         |
+----------------------+--------------------------+
| Content length       | 3 byte unsigned integer  |
+----------------------+--------------------------+
| Metadata content    | N byte                   |
+----------------------+--------------------------+
~~~

Ba thành phần cần hiểu:

1. **MIME type header** dài một byte. Bit cao nhất cho biết MIME type có phải loại well-known hay không.
2. **MIME type** có thể được nén thành một identifier well-known, hoặc được ghi thành chuỗi US-ASCII khi là MIME type tùy chỉnh.
3. **Metadata content length** là số nguyên không dấu 24-bit theo thứ tự big-endian, cho biết số byte nội dung theo sau. Phần nội dung có độ dài đúng bằng giá trị này.

### Well-known MIME type

Nếu bit cao nhất của byte đầu tiên bằng 1, bảy bit còn lại là identifier của một well-known MIME type. Không có chuỗi MIME type theo sau byte header; parser tra identifier trong registry để tìm tên MIME type.

~~~text
1 | 7-bit well-known MIME type identifier
~~~

Các identifier well-known nằm trong khoảng 0 đến 127. RSocket Java cung cấp enum WellKnownMimeType để làm việc với registry thay vì tự ghi identifier bằng số.

Một số MIME type thường gặp:

| Well-known MIME type | Vai trò |
|---|---|
| MESSAGE_RSOCKET_COMPOSITE_METADATA | Định dạng tổng thể của metadata trên kết nối |
| MESSAGE_RSOCKET_ROUTING | Metadata route |
| MESSAGE_RSOCKET_AUTHENTICATION | Metadata xác thực |
| MESSAGE_RSOCKET_TRACING_ZIPKIN | Metadata tracing theo định dạng Zipkin được hỗ trợ |
| APPLICATION_JSON | Nội dung metadata hoặc data được mã hóa JSON |

Tên enum là tên trong thư viện Java; giá trị MIME type trên wire là chuỗi tương ứng trong registry. Không tự đoán identifier từ thứ tự enum vì registry có thể mở rộng và thứ tự khai báo không phải hợp đồng wire.

MESSAGE_RSOCKET_COMPOSITE_METADATA là MIME type khai báo định dạng cho toàn vùng metadata trong SETUP. Nó không phải entry thông thường được lồng bên trong chính composite metadata đó.

### MIME type tùy chỉnh

Nếu bit cao nhất bằng 0, bảy bit còn lại biểu diễn độ dài MIME type trừ đi một. Các byte tiếp theo chứa MIME type dạng US-ASCII.

~~~text
0 | (MIME type length - 1)
    followed by MIME type bytes
~~~

Định dạng này biểu diễn được MIME type dài từ 1 đến 128 byte. Sau header và chuỗi MIME type, entry chứa độ dài nội dung metadata 24-bit rồi đến nội dung thực tế.

Ví dụ MIME type tùy chỉnh:

~~~text
application/vnd.acme.tenant-v1+json
~~~

MIME type tùy chỉnh nên có tên ổn định, có namespace và thể hiện phiên bản schema nếu cấu trúc có thể thay đổi. Hai phía cần thống nhất cả MIME type lẫn định dạng nội dung; cùng dùng JSON không có nghĩa là hai schema JSON khác nhau có thể giải mã thay thế cho nhau.

### Giới hạn độ dài và kiểm tra dữ liệu

Độ dài nội dung của một entry được biểu diễn bằng 24 bit không dấu, vì vậy trường này có miền giá trị từ 0 đến 16.777.215 byte. Giới hạn thực tế của một thông điệp còn phụ thuộc giới hạn frame, cấu hình fragmentation, bộ nhớ và chính sách của ứng dụng.

Parser phải kiểm tra:

- Có đủ byte để đọc header MIME type.
- Nếu là MIME tùy chỉnh, số byte chuỗi MIME type nằm trong vùng metadata.
- Có đủ ba byte để đọc độ dài nội dung.
- Độ dài khai báo không vượt quá số byte còn lại.
- MIME type và schema nội dung được ứng dụng hỗ trợ.

Không được đọc vượt buffer hoặc tin một độ dài do peer gửi lên mà chưa kiểm tra. Metadata có thể đến từ client không đáng tin cậy.

## 4. Các loại metadata thường gặp trong một payload

Mỗi entry có một mục đích riêng và cần được giải mã theo định dạng tương ứng.

| Loại metadata | MIME type | Nội dung thường chứa |
|---|---|---|
| Routing | message/x.rsocket.routing.v0 | Một hoặc nhiều route tag |
| Authentication | message/x.rsocket.authentication.v0 | Authentication type và credential |
| Tracing | message/x.rsocket.tracing-zipkin.v0 | Trace ID, span ID và cờ tracing |
| Tenant tùy chỉnh | application/vnd.acme.tenant-v1+json | Tenant ID và thông tin phạm vi |
| Correlation tùy chỉnh | application/vnd.acme.correlation-v1+json | Correlation ID hoặc request context |

### Routing metadata

Routing metadata cho biết request cần được chuyển đến route nào. Trong Spring, lời gọi route trên RSocketRequester tạo routing metadata theo định dạng RSocket mà framework hỗ trợ:

~~~java
requester
    .route("orders.get")
    .data(new GetOrderRequest("order-42"))
    .retrieveMono(OrderView.class);
~~~

Route được gửi trong metadata, còn GetOrderRequest được mã hóa trong data. Vì routing là một metadata entry, nó có thể nằm cùng tenant, authentication và tracing trong composite metadata.

### Authentication metadata

Authentication metadata có MIME type chuẩn riêng. Phần content của nó có cấu trúc xác thực, gồm loại xác thực và credential tương ứng. Ví dụ, bearer authentication mang token theo định dạng của Authentication extension.

Không gửi một chuỗi token tùy ý rồi giả định nó tự trở thành authentication metadata hợp lệ. Hãy dùng AuthMetadataCodec hoặc integration bảo mật tương ứng để mã hóa đúng định dạng. Ở phía nhận, credential phải được xác thực và chuyển thành principal hoặc authentication context theo cơ chế bảo mật của ứng dụng.

### Tracing metadata

Tracing metadata mang các định danh trace/span và thông tin cần thiết để nối một request với các thao tác downstream. RSocket Java có TracingMetadataCodec cho định dạng tracing được hỗ trợ.

Metadata tracing nên được tạo từ tracing context hiện tại. Không tự tạo trace ID mới ở từng tầng nếu mục tiêu là nối cùng một trace xuyên suốt request.

### Metadata ứng dụng

Metadata ứng dụng dùng MIME type do hệ thống định nghĩa, ví dụ tenant hoặc correlation. Nội dung có thể là JSON, CBOR hoặc định dạng nhị phân riêng. Một metadata entry nên có một trách nhiệm rõ ràng và schema ổn định.

Không dùng tenant metadata làm bằng chứng xác thực. Tenant ID từ client chỉ là dữ liệu yêu cầu; server cần kiểm tra tenant đó có thuộc phạm vi mà principal đã xác thực được phép truy cập hay không.

## 5. Gửi nhiều metadata bằng Spring RSocketRequester

Spring RSocketRequester cung cấp API fluent để gửi data và metadata dưới dạng object. Metadata MIME type của kết nối mặc định là Composite Metadata trong cấu hình Spring hiện hành, cho phép nhiều cặp giá trị metadata và MIME type trong cùng một request. Có thể khai báo rõ để hợp đồng kết nối dễ đọc hơn.

Với RSocket Java ở tầng thấp, RSocketConnector mặc định dùng metadata MIME type application/binary. Nếu tự tạo composite metadata bằng ByteBuf, hãy cấu hình MIME type composite trong SETUP trước khi gửi:

~~~java
RSocketConnector connector = RSocketConnector.create()
    .metadataMimeType("message/x.rsocket.composite-metadata.v0")
    .dataMimeType("application/json");
~~~

Spring RSocketRequester có mặc định riêng như mô tả ở trên; không nên suy ra mặc định của RSocketConnector từ RSocketRequester.

Ví dụ dưới đây gửi route cùng tenant metadata và correlation metadata. Các metadata object được mã hóa bằng encoder phù hợp đã đăng ký trong RSocketStrategies.

~~~java
private static final MimeType COMPOSITE_METADATA =
    MimeTypeUtils.parseMimeType(
        "message/x.rsocket.composite-metadata.v0"
    );

private static final MimeType TENANT_METADATA =
    MimeTypeUtils.parseMimeType(
        "application/vnd.acme.tenant-v1+json"
    );

private static final MimeType CORRELATION_METADATA =
    MimeTypeUtils.parseMimeType(
        "application/vnd.acme.correlation-v1+json"
    );

RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
    .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
    .build();

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .metadataMimeType(COMPOSITE_METADATA)
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .tcp("localhost", 7000);

Mono<OrderView> response = requester
    .route("orders.get")
    .metadata(new TenantMetadata("tenant-17"), TENANT_METADATA)
    .metadata(
        new CorrelationMetadata("corr-8f31"),
        CORRELATION_METADATA
    )
    .data(new GetOrderRequest("order-42"))
    .retrieveMono(OrderView.class);
~~~

Các kiểu TenantMetadata, CorrelationMetadata, GetOrderRequest và OrderView là DTO của ứng dụng. Ví dụ giả định Jackson encoder/decoder có thể xử lý các metadata DTO. Nếu dùng định dạng khác, hãy đăng ký encoder và decoder tương ứng.

Mỗi lời gọi metadata thêm một cặp giá trị và MIME type. Lời gọi route thêm route metadata. Khi gửi, Spring chuyển các giá trị này thành composite metadata theo định dạng đã cấu hình. Data request vẫn được mã hóa riêng bằng data MIME type.

### Gửi authentication metadata

Nếu ứng dụng dùng RSocket Java ở tầng thấp để tự tạo authentication entry, có thể dùng AuthMetadataCodec. Ví dụ bearer token:

~~~java
ByteBuf authContent =
    AuthMetadataCodec.encodeBearerMetadata(
        allocator,
        accessToken.toCharArray()
    );

CompositeMetadataCodec.encodeAndAddMetadata(
    compositeMetadata,
    allocator,
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION,
    authContent
);
~~~

Đoạn mã trên minh họa việc tạo content theo Bearer Authentication extension và thêm nó thành một entry có MIME type authentication. Trong ứng dụng Spring Security, ưu tiên cấu hình metadata encoder và cơ chế xác thực do integration bảo mật cung cấp để requester và responder dùng cùng một hợp đồng.

Không ghi token hoặc nội dung authentication vào log. Nếu dùng TCP hoặc WebSocket qua mạng không tin cậy, cần cấu hình TLS/WSS và xác minh danh tính peer theo kiến trúc triển khai.

## 6. Đăng ký và đọc metadata ở phía Spring responder

Responder phải biết cách giải mã từng MIME type mà ứng dụng muốn sử dụng. Spring cung cấp MetadataExtractor để chuyển metadata đã serialize thành các cặp tên-giá trị. Handler có thể nhận các giá trị này như header bằng @Header hoặc đọc tập hợp bằng @Headers.

Spring có hỗ trợ sẵn composite metadata và routing metadata. Routing được giải mã thành giá trị route. Với MIME type tùy chỉnh, cần có Decoder tương ứng và đăng ký MIME type vào MetadataExtractor.

~~~java
private static final MimeType TENANT_METADATA =
    MimeTypeUtils.parseMimeType(
        "application/vnd.acme.tenant-v1+json"
    );

private static final MimeType CORRELATION_METADATA =
    MimeTypeUtils.parseMimeType(
        "application/vnd.acme.correlation-v1+json"
    );

@Bean
RSocketStrategies rsocketStrategies() {
    return RSocketStrategies.builder()
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .metadataExtractorRegistry(registry -> {
            registry.metadataToExtract(
                TENANT_METADATA,
                TenantMetadata.class,
                "tenant"
            );
            registry.metadataToExtract(
                CORRELATION_METADATA,
                CorrelationMetadata.class,
                "correlation"
            );
        })
        .build();
}
~~~

Sau khi đăng ký, handler có thể nhận metadata đã giải mã:

~~~java
@Controller
class OrderController {

    @MessageMapping("orders.get")
    Mono<OrderView> getOrder(
            GetOrderRequest request,
            @Header("tenant") TenantMetadata tenant,
            @Header("correlation") CorrelationMetadata correlation) {

        return orderService.findVisibleOrder(
            tenant.tenantId(),
            request.orderId(),
            correlation.correlationId()
        );
    }
}
~~~

Tên trong @Header phải khớp tên được đăng ký trong metadataExtractorRegistry. Ví dụ trên minh họa việc trích xuất metadata tùy chỉnh; routing được Spring xử lý riêng để chọn handler.

Trong cấu hình Spring thuần, hãy gắn RSocketStrategies vào RSocketMessageHandler bằng setRSocketStrategies. Với Spring Boot, dùng cơ chế auto-configuration tương ứng và bảo đảm handler thực tế sử dụng strategies có MetadataExtractor đã đăng ký.

Một luồng xử lý điển hình:

1. Requester gửi payload có route, tenant và correlation metadata.
2. RSocket nhận frame và tách vùng metadata khỏi vùng data.
3. Composite Metadata parser đọc từng entry dựa trên MIME type và độ dài.
4. MetadataExtractor chọn decoder cho các MIME type đã đăng ký.
5. Spring đưa giá trị đã giải mã vào handler dưới dạng header.
6. Handler kiểm tra quyền truy cập và xử lý data request.

Nếu MIME type tùy chỉnh chưa đăng ký hoặc không có decoder phù hợp, responder không thể tự suy ra schema của content. Cần cấu hình codec ở phía nhận trước khi dùng metadata đó trong handler.

## 7. Giải mã Composite Metadata bằng RSocket Java

Khi cần làm việc trực tiếp với Payload và ByteBuf, RSocket Java cung cấp CompositeMetadata để duyệt các entry. Ví dụ:

~~~java
void inspectMetadata(Payload payload) {
    if (!payload.hasMetadata()) {
        return;
    }

    CompositeMetadata entries =
        new CompositeMetadata(payload.sliceMetadata(), false);

    for (CompositeMetadata.Entry entry : entries) {
        String mimeType = entry.getMimeType();

        if (mimeType == null) {
            // Well-known identifier chưa được phiên bản thư viện nhận biết.
            // Bỏ qua nếu tùy chọn; nếu bắt buộc, áp dụng chính sách từ chối.
            continue;
        }

        ByteBuf content = entry.getContent();

        if (WellKnownMimeType.MESSAGE_RSOCKET_ROUTING
                .getString().equals(mimeType)) {
            // Giải mã content bằng routing metadata codec.
        } else if (WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION
                .getString().equals(mimeType)) {
            // Chuyển content cho authentication metadata codec.
        } else if ("application/vnd.acme.tenant-v1+json"
                .equals(mimeType)) {
            // Giải mã content bằng JSON decoder của ứng dụng.
        }
    }
}
~~~

CompositeMetadata duyệt các entry theo thứ tự trong buffer. Entry có MIME type well-known mà phiên bản thư viện chưa nhận biết có thể được biểu diễn bằng ReservedMimeTypeEntry; trong trường hợp đó getMimeType() có thể trả về null. Đây không nhất thiết là metadata bị hỏng: identifier có thể đã được registry mới hơn sử dụng.

Với content cần giải mã, chọn codec theo MIME type. Không giải mã mọi entry thành JSON hoặc String. Ví dụ authentication và routing có cấu trúc riêng; custom tenant JSON phải được xử lý bằng JSON decoder đã thống nhất.

### Mã hóa entry ở tầng thấp

CompositeMetadataCodec cung cấp các phương thức để thêm entry vào CompositeByteBuf. Có thể dùng MIME type tùy chỉnh hoặc WellKnownMimeType:

~~~java
CompositeByteBuf compositeMetadata = allocator.compositeBuffer();

ByteBuf tenantBytes = Unpooled.copiedBuffer(
    tenantJson,
    StandardCharsets.UTF_8
);

CompositeMetadataCodec.encodeAndAddMetadata(
    compositeMetadata,
    allocator,
    "application/vnd.acme.tenant-v1+json",
    tenantBytes
);
~~~

Khi MIME type là well-known, dùng overload nhận WellKnownMimeType. Nếu chỉ có chuỗi MIME type và muốn thư viện tự nén MIME type khi tìm thấy trong registry, dùng encodeAndAddMetadataWithCompression.

Đoạn mã trên mới thêm tenant entry. Để tạo một composite metadata hoàn chỉnh, tiếp tục thêm các entry khác vào cùng compositeMetadata buffer theo thứ tự mà ứng dụng muốn gửi. Khi tạo Payload, truyền buffer này làm metadata và buffer data riêng. Cần quản lý reference count của ByteBuf theo vòng đời Payload; không giải phóng hoặc tái sử dụng buffer khi payload vẫn còn được dùng.

## 8. Phân biệt metadata theo request và metadata theo kết nối

Không phải mọi metadata đều có cùng phạm vi.

| Cơ chế | Phạm vi | Khi sử dụng |
|---|---|---|
| Metadata trong request/payload | Một request hoặc payload trên stream | Route, tenant, auth context hoặc tracing gắn với request |
| Metadata trong SETUP | Khởi tạo kết nối | Thông tin ban đầu hoặc ngữ cảnh kết nối |
| METADATA_PUSH | Toàn bộ kết nối, Stream ID bằng 0 | Thông báo metadata bất đồng bộ sau khi kết nối đã được thiết lập |

Composite Metadata có thể được dùng trong vùng metadata của các payload nếu MIME type metadata của kết nối được cấu hình phù hợp. Metadata Push là một frame riêng ở cấp kết nối; không nên nhầm nó với một entry bổ sung trong payload request.

Ví dụ, tenant context cố định theo một kết nối có thể được xác lập khi SETUP, nhưng nếu một kết nối phục vụ nhiều tenant hoặc mỗi request có quyền truy cập khác nhau, cần truyền và xác thực phạm vi tenant ở đúng cấp request. Không dùng metadata push để thay thế metadata gắn với từng request khi các request có ngữ cảnh khác nhau.

## 9. Thiết kế metadata an toàn và dễ tương thích

Composite Metadata giúp mở rộng hợp đồng, nhưng mỗi entry vẫn là dữ liệu đến từ peer. Hãy thiết kế rõ schema và quy tắc tin cậy.

### Tách vai trò của từng entry

Mỗi metadata type nên có một trách nhiệm rõ ràng:

- Routing chọn handler.
- Authentication cung cấp credential cho cơ chế xác thực.
- Tracing liên kết các span.
- Tenant mô tả phạm vi dữ liệu được yêu cầu.
- Correlation giúp liên kết log hoặc kết quả với một request.

Không gộp tất cả vào một JSON metadata lớn nếu các mục có vòng đời, quyền tin cậy hoặc decoder khác nhau. Ngược lại, cũng không tạo một entry riêng cho từng trường nhỏ nếu chúng cùng một schema và luôn được sử dụng cùng nhau.

### Kiểm tra dữ liệu và quyền

- Xác thực MIME type và giới hạn độ dài metadata trước khi giải mã.
- Từ chối hoặc bỏ qua metadata tùy theo chính sách đối với loại không được hỗ trợ.
- Kiểm tra tenant ID dựa trên principal đã xác thực; không tin tenant ID chỉ vì client gửi lên.
- Không ghi access token, password hoặc credential vào log.
- Không coi metadata là cơ chế mã hóa. Dùng TLS trên TCP hoặc WSS khi dữ liệu cần bảo vệ trên đường truyền.
- Giới hạn số lượng entry và tổng kích thước metadata để tránh tiêu thụ CPU/bộ nhớ quá mức.
- Đảm bảo codec chỉ đọc dữ liệu theo đúng MIME type, không thử lần lượt nhiều decoder trên cùng một byte sequence.

### Quản lý schema và phiên bản

Với metadata tùy chỉnh, nên dùng MIME type có namespace và version. Ví dụ:

~~~text
application/vnd.acme.tenant-v1+json
application/vnd.acme.correlation-v1+json
~~~

Khi schema thay đổi không tương thích, tạo MIME type version mới hoặc định nghĩa quy tắc tương thích rõ ràng. Hai phiên bản ứng dụng có thể cùng kết nối nhưng không nhất thiết hiểu cùng một metadata type.

Một entry không được nhận diện có thể bỏ qua nếu nó là metadata tùy chọn và không ảnh hưởng tính đúng đắn. Nếu entry đó là bắt buộc để xác thực hoặc định tuyến đúng, responder phải từ chối request theo chính sách của ứng dụng. Không âm thầm xử lý request khi thiếu thông tin bảo mật bắt buộc.

### Thứ tự và entry trùng lặp

Composite Metadata là chuỗi entry nên thứ tự xuất hiện được giữ trong buffer. Tuy nhiên, không nên để tính đúng đắn của nghiệp vụ phụ thuộc vào thứ tự nếu hợp đồng không quy định rõ.

Nếu cùng một MIME type xuất hiện nhiều lần, cần xác định chính sách: chỉ cho phép một entry, lấy entry đầu/cuối hay hỗ trợ danh sách. Tránh để các tầng khác nhau hiểu entry trùng lặp theo cách khác nhau, đặc biệt với tenant hoặc authentication metadata.

## 10. Kiểm thử Composite Metadata

Kiểm thử nên bao gồm cả cấu trúc wire và cách ứng dụng sử dụng metadata đã giải mã.

| Trường hợp | Điều cần xác nhận |
|---|---|
| Một entry well-known | MIME identifier và content được đọc đúng |
| Một entry MIME tùy chỉnh | Độ dài MIME type và content được giải mã đúng |
| Nhiều entry nối tiếp | Tất cả entry được đọc đúng thứ tự |
| Có routing và custom metadata | Spring chọn đúng handler và trích xuất đúng header |
| Metadata type chưa hỗ trợ | Entry tùy chọn được bỏ qua hoặc entry bắt buộc bị từ chối theo chính sách |
| Độ dài entry không hợp lệ | Parser phát hiện dữ liệu thiếu hoặc vượt giới hạn |
| Entry lặp lại | Hành vi đúng theo quy tắc ứng dụng |
| Payload không có metadata | Handler xử lý trường hợp thiếu metadata rõ ràng |
| Credential không hợp lệ | Cơ chế bảo mật từ chối request |

Ví dụ kiểm thử tích hợp ở tầng Spring nên xác nhận rằng handler nhận đúng tenant và correlation từ hai metadata MIME type khác nhau:

~~~java
StepVerifier.create(
    requester.route("orders.get")
        .metadata(
            new TenantMetadata("tenant-17"),
            TENANT_METADATA
        )
        .metadata(
            new CorrelationMetadata("corr-8f31"),
            CORRELATION_METADATA
        )
        .data(new GetOrderRequest("order-42"))
        .retrieveMono(OrderView.class)
)
.expectNextMatches(order ->
    order.tenantId().equals("tenant-17")
)
.verifyComplete();
~~~

Bên cạnh kết quả nghiệp vụ, nên kiểm tra log hoặc tracing test để chắc chắn correlation context được truyền xuyên suốt. Với test bảo mật, cần chứng minh server từ chối tenant không thuộc quyền của principal thay vì chỉ kiểm tra tenant metadata đã được deserialize thành công.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Server không đọc được composite metadata | Metadata MIME type trong SETUP không phải composite metadata | Cấu hình metadataMimeType đồng nhất ở hai phía |
| Chỉ nhận được một loại metadata | Client chỉ gửi một entry hoặc server chỉ trích xuất một MIME type | Kiểm tra các lời gọi metadata và cấu hình MetadataExtractor |
| Metadata tùy chỉnh không xuất hiện trong @Header | Chưa đăng ký MIME type hoặc thiếu decoder | Đăng ký metadataToExtract và decoder phù hợp |
| MIME type tùy chỉnh không giải mã được | Chuỗi MIME type không đúng US-ASCII hoặc header length sai | Kiểm tra MIME type và dùng CompositeMetadataCodec |
| MIME type trả về null khi duyệt entry | Well-known identifier chưa có trong registry của phiên bản thư viện | Kiểm tra reserved entry và quyết định có cần nâng cấp/forward |
| Authentication bị từ chối | Content không theo Authentication extension hoặc credential không hợp lệ | Dùng AuthMetadataCodec/Spring Security metadata encoder và xác thực ở server |
| Metadata bị sai khi buffer được giải phóng | ByteBuf slice được giữ sau vòng đời payload | Copy hoặc retain buffer đúng cách và release đúng một lần |
| Server xử lý sai tenant | Tin metadata tenant do client cung cấp mà không kiểm tra quyền | Ràng buộc tenant với principal đã xác thực |

## 12. Quy trình triển khai thực tế

Khi thêm một metadata type vào hệ thống RSocket, hãy thực hiện theo thứ tự:

1. Xác định thông tin đó thuộc metadata hay data. Metadata phù hợp với ngữ cảnh điều khiển; nội dung nghiệp vụ chính nên nằm trong data.
2. Chọn MIME type chuẩn nếu đã có extension tương ứng. Chỉ tạo MIME type tùy chỉnh khi ứng dụng cần schema riêng.
3. Chọn encoding cho content, ví dụ JSON, CBOR hoặc byte format chuyên biệt.
4. Cấu hình metadata MIME type của kết nối là Composite Metadata ở cả requester và responder.
5. Đăng ký encoder phía gửi và decoder/MetadataExtractor phía nhận.
6. Xác định chính sách với entry thiếu, lặp, không hỗ trợ hoặc sai định dạng.
7. Kiểm thử request có nhiều metadata type, trường hợp không có metadata và trường hợp dữ liệu không đáng tin cậy.
8. Đánh giá kích thước metadata, logging, TLS và quyền truy cập trước khi triển khai.

Composite Metadata cho phép các thành phần độc lập cùng bổ sung ngữ cảnh cho một request RSocket. Khi mỗi entry có MIME type, schema, decoder và chính sách tin cậy rõ ràng, hệ thống có thể mở rộng metadata mà không làm data payload phụ thuộc vào từng loại ngữ cảnh.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [RSocket Composite Metadata extension](https://github.com/rsocket/rsocket/blob/master/Extensions/CompositeMetadata.md)
- [Spring Framework: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocket Java: CompositeMetadata](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/metadata/CompositeMetadata.html)
- [RSocket Java: CompositeMetadataCodec](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/metadata/CompositeMetadataCodec.html)
- [RSocket Java: WellKnownMimeType](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/metadata/WellKnownMimeType.html)

