# Lỗi giải mã payload và không tương thích cấu trúc dữ liệu

Một kết nối RSocket có thể được thiết lập thành công nhưng interaction vẫn thất bại khi một phía không giải mã được payload. Java server có thể nhận byte hợp lệ nhưng Jackson không ánh xạ được JSON vào DTO; browser có thể gửi JSON dưới dạng chuỗi đã encode hai lần; hoặc hai dịch vụ dùng cùng tên field nhưng khác kiểu dữ liệu. Với metadata, lỗi còn có thể xuất hiện trước khi handler chạy vì entry được gửi bằng MIME type mà server chưa đăng ký decoder.

RSocket truyền payload gồm data và metadata, nhưng protocol không tự định nghĩa cấu trúc nghiệp vụ của các byte đó. Hai peer phải thống nhất MIME type, serializer, schema và quy tắc tương thích. Vì vậy, cần chẩn đoán riêng lỗi transport/frame, chọn codec, parse, ánh xạ cấu trúc, giải mã metadata và validation nghiệp vụ.

Bài học này tập trung vào client/server Java, Spring Boot và các peer có thể viết bằng JavaScript hoặc ngôn ngữ khác. Bạn sẽ học cách đọc dấu hiệu lỗi, kiểm tra MIME type, cấu hình Jackson, xử lý thay đổi schema an toàn, tạo fixture dùng chung và kiểm thử tương thích hai chiều.

Sau bài học, bạn có thể:

- Phân biệt lỗi transport/protocol với lỗi codec, schema và validation.
- Hiểu vai trò của data MIME type và metadata MIME type trong RSocket.
- Nhận biết JSON sai cú pháp, sai encoding, double encoding và kiểu dữ liệu không khớp.
- Chẩn đoán lỗi Jackson khi ánh xạ JSON vào Java record/DTO.
- Xử lý field thiếu, field mới, null, enum mới, số lớn, decimal và timestamp.
- Giải mã Composite Metadata và custom metadata theo đúng MIME type.
- Thiết kế schema versioning và thay đổi tương thích ngược/tiến.
- Viết contract test bằng fixture để kiểm tra Java và JavaScript.
- Thu thập log hữu ích mà không làm lộ payload hoặc metadata nhạy cảm.

## 1. Payload RSocket không đồng nghĩa với JSON

RSocket truyền các frame có data và metadata. Protocol quy định cách đóng khung, stream ID, interaction model và cách trao đổi payload; nó không bắt buộc data phải là JSON hay metadata phải là một DTO Java cụ thể.

Một Payload có thể chứa:

- Data: byte của nội dung ứng dụng.
- Metadata: byte mô tả route, authentication context, tracing context hoặc thông tin mở rộng.

~~~mermaid
flowchart TD
    A[Application object] --> B[Serializer / Encoder]
    B --> C[Data bytes]
    D[Route / tenant / trace] --> E[Metadata encoder]
    E --> F[Metadata bytes]
    C --> G[RSocket Payload]
    F --> G
    G --> H[Transport TCP or WebSocket]
    H --> I[Remote Payload]
    I --> J[Data decoder]
    I --> K[Metadata decoder]
    J --> L[Application DTO]
    K --> M[Route and metadata context]
~~~

Ví dụ cùng một InventoryCheck có thể được mã hóa bằng JSON, CBOR hoặc Protobuf. Nếu client gửi JSON nhưng server chọn Protobuf decoder, byte vẫn đi qua transport nhưng không thể được diễn giải đúng.

Một nguyên tắc quan trọng: **kiểu Java của object không được gửi qua wire**. Peer nhận byte và chỉ có thể tái tạo object theo codec cùng schema mà hai bên đã thống nhất.

## 2. Phân lớp lỗi trước khi sửa code

Khi thấy lỗi "payload decode failed", hãy xác định lỗi xảy ra ở lớp nào.

| Lớp | Dấu hiệu | Ví dụ nguyên nhân |
|---|---|---|
| DNS/TCP/TLS/WebSocket | Không có RSocket interaction hoàn chỉnh | Host sai, connection refused, TLS handshake, WebSocket upgrade |
| RSocket frame/protocol | Connection hoặc stream bị protocol error | Frame lỗi định dạng, stream state không hợp lệ |
| MIME type/codec selection | Không tìm được decoder phù hợp | Client và server khai báo data MIME type khác nhau |
| Byte decoding | Byte không thể parse | UTF-8 lỗi, JSON hỏng, Protobuf truncated |
| DTO mapping | Parse được nhưng không ánh xạ được object | String thay cho integer, field bắt buộc thiếu |
| Metadata decoding | Route có thể đến nhưng custom metadata lỗi | Entry MIME type không được đăng ký, metadata JSON sai |
| Schema validation | Object tạo được nhưng không hợp lệ | quantity âm, enum không được hỗ trợ |
| Business logic | Handler chạy rồi trả lỗi | Trạng thái nghiệp vụ không cho phép thao tác |

Đừng bắt đầu bằng cách thay đổi DTO hoặc tắt strict deserialization. Trước tiên cần chứng minh byte, MIME type và schema mà hai phía thực sự đang sử dụng.

### Cây chẩn đoán nhanh

~~~mermaid
flowchart TD
    A[Interaction fails] --> B{Transport connected?}
    B -->|No| C[Check DNS TCP TLS WebSocket]
    B -->|Yes| D{RSocket SETUP accepted?}
    D -->|No| E[Check protocol version and setup MIME types]
    D -->|Yes| F{Correct data MIME type?}
    F -->|No| G[Align encoder and decoder]
    F -->|Yes| H{Bytes parse successfully?}
    H -->|No| I[Inspect encoding and serializer]
    H -->|Yes| J{DTO mapping succeeds?}
    J -->|No| K[Check schema and field types]
    J -->|Yes| L{Metadata valid?}
    L -->|No| M[Check Composite Metadata entries]
    L -->|Yes| N[Check domain validation and handler]
~~~

## 3. Kiểm tra data MIME type và metadata MIME type

RSocket SETUP thương lượng MIME type mặc định cho data và metadata của connection. Trong Spring, RSocketRequester có thể cấu hình data MIME type và metadata MIME type.

Ví dụ phía client:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .metadataMimeType(
        MimeType.valueOf(
            "message/x.rsocket.composite-metadata.v0"
        )
    )
    .tcp("inventory.internal", 7000);
~~~

Trong ví dụ:

- Data MIME type là application/json.
- Metadata MIME type là Composite Metadata.
- Các entry bên trong Composite Metadata vẫn có MIME type riêng, chẳng hạn routing metadata hoặc custom tenant metadata.

Không nhầm MIME type của Composite Metadata với MIME type của từng entry. Cũng không cho rằng application/json ở data tự động có nghĩa mọi metadata entry đều là JSON.

Khi chẩn đoán, hãy đối chiếu:

1. Client khai báo data MIME type nào trong SETUP.
2. Server có decoder hỗ trợ MIME type đó không.
3. Client khai báo metadata MIME type nào.
4. Nếu dùng Composite Metadata, từng entry có MIME type nào.
5. MIME type có đúng chính tả và version không.
6. Hai phía có dùng cùng serializer format và cấu hình tương thích không.

Một peer có thể chấp nhận transport và SETUP nhưng lỗi xuất hiện khi handler nhận một payload có cấu trúc không phù hợp. Việc SETUP thành công không chứng minh mọi payload sau đó đều hợp lệ.

## 4. Những lỗi JSON thường gặp

### JSON sai cú pháp

Ví dụ JSON không hợp lệ:

~~~json
{
  "sku": "SKU-42",
  "quantity": 3,
}
~~~

Dấu phẩy cuối sau quantity không được JSON chuẩn chấp nhận. Jackson có thể báo JsonParseException hoặc lỗi cú pháp tương tự.

Cần kiểm tra byte thực tế trước khi parse. Đừng chỉ kiểm tra object ở phía gửi vì serializer hoặc một lớp trung gian có thể thay đổi representation.

### Double-encoded JSON

Một lỗi phổ biến là encode JSON thành String rồi lại đưa String đó vào JSON encoder. Thay vì gửi object JSON, client gửi một JSON string chứa JSON text.

JSON object đúng:

~~~json
{
  "sku": "SKU-42",
  "quantity": 3
}
~~~

JSON string bị encode hai lần:

~~~json
"{\"sku\":\"SKU-42\",\"quantity\":3}"
~~~

Ở trường hợp thứ hai, decoder có thể tạo ra String thay vì InventoryCheckRequest. Khi server mong đợi object, Jackson báo không thể deserialize String thành DTO.

Phía JavaScript nên gửi object cho serializer đúng một lần:

~~~javascript
const request = {
  sku: "SKU-42",
  quantity: 3
};

// RSocket JSON encoder chịu trách nhiệm serialize object.
return requester.route("inventory.check").data(request);
~~~

Nếu API client yêu cầu byte, hãy stringify đúng một lần rồi encode UTF-8. Không truyền một chuỗi JSON đã stringify vào encoder lại tiếp tục stringify.

### Encoding UTF-8

JSON trao đổi giữa các peer nên dùng UTF-8 theo hợp đồng. Các lỗi có thể xảy ra khi:

- Một phía encode bằng charset khác.
- Byte bị cắt giữa một ký tự nhiều byte.
- Dùng charset mặc định của hệ điều hành.
- Coi binary data như text.
- Thêm BOM hoặc ký tự ngoài dự kiến mà parser không chấp nhận.

Ở browser, dùng TextEncoder/TextDecoder với UTF-8. Ở Java, dùng API charset tường minh khi xử lý byte thủ công:

~~~java
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);

String decoded = new String(
    bytes,
    StandardCharsets.UTF_8
);
~~~

Không chuyển mọi payload thành String để debug. Payload Protobuf, CBOR hoặc dữ liệu nhị phân có thể chứa byte không phải text.

## 5. JSON parse được nhưng DTO mapping thất bại

JSON có thể đúng cú pháp nhưng không tương thích với Java DTO.

Ví dụ DTO:

~~~java
public record InventoryCheckRequest(
    String sku,
    Integer quantity,
    Integer contractVersion,
    String requestId,
    Instant requestedAt
) {}
~~~

Payload đúng:

~~~json
{
  "sku": "SKU-42",
  "quantity": 3
}
~~~

Payload sai kiểu:

~~~json
{
  "sku": "SKU-42",
  "quantity": "three"
}
~~~

JSON parser có thể đọc được cấu trúc, nhưng Jackson không thể ánh xạ chuỗi "three" thành Integer. Lỗi thường thuộc nhóm MismatchedInputException hoặc InvalidFormatException.

Cần phân biệt:

- Parse error: JSON không hợp lệ về cú pháp.
- Mapping error: JSON hợp lệ nhưng không thể chuyển sang kiểu Java.
- Validation error: mapping thành công nhưng giá trị không đáp ứng quy tắc nghiệp vụ.

Ví dụ quantity = -3 có thể ánh xạ thành Integer thành công, nhưng phải bị validation từ chối.

## 6. Field thiếu, field thừa và null

Ba trạng thái sau có thể mang ý nghĩa khác nhau:

~~~json
{}
~~~

~~~json
{
  "displayName": null
}
~~~

~~~json
{
  "displayName": ""
}
~~~

- Field vắng mặt: producer không gửi field.
- Null: producer gửi giá trị null rõ ràng.
- Chuỗi rỗng: producer gửi một string có độ dài bằng 0.

Trong command PATCH, field vắng mặt có thể nghĩa là giữ nguyên; null có thể nghĩa là xóa giá trị. Nếu hai phía tự quy ước khác nhau, payload có thể decode thành công nhưng gây sai dữ liệu.

### Field bắt buộc

Nếu DTO cần field quantity nhưng payload không có, primitive int có thể nhận giá trị mặc định 0 trong một số cấu hình mapping; Integer có thể nhận null. Không dựa vào default ngầm để kiểm tra field bắt buộc.

Hãy xác thực rõ sau khi decode hoặc cấu hình Jackson để yêu cầu property bắt buộc cho creator/record phù hợp với phiên bản thư viện đang dùng.

Ví dụ validation:

~~~java
public record InventoryCheckRequest(
    @NotBlank String sku,
    @NotNull @Positive Integer quantity
) {}
~~~

Validation cần được gọi trong luồng xử lý theo cấu hình Spring tương ứng. Annotation trên record không tự đảm bảo mọi đường decode đều thực hiện validation nếu handler không kích hoạt cơ chế đó.

### Field mới và unknown property

Server mới có thể thêm field:

~~~json
{
  "sku": "SKU-42",
  "quantity": 3,
  "warehouseRegion": "south"
}
~~~

Client cũ không có field warehouseRegion. Nếu decoder strict unknown-property, nó có thể từ chối payload. Nếu decoder bỏ qua field lạ, client cũ vẫn đọc được phần nó hiểu.

Chính sách cần dựa vào hướng tương thích:

- Consumer nên bỏ qua field không biết nếu hợp đồng cho phép mở rộng additive.
- Producer không nên bắt consumer cũ phải gửi field mới ngay lập tức.
- Field mới nên optional hoặc có default tương thích.
- Trong contract test, có thể chạy strict validation để phát hiện thay đổi ngoài dự kiến.
- Không tắt FAIL_ON_UNKNOWN_PROPERTIES một cách toàn cục mà không đánh giá rủi ro schema drift.

## 7. Cấu hình Jackson nhất quán trong Spring RSocket

Nếu Spring sử dụng Jackson encoder/decoder, cấu hình ObjectMapper cần nhất quán với quy tắc wire contract. Ví dụ dưới đây đăng ký Java Time module, dùng ISO-8601 cho thời gian và bật kiểm tra unknown property để contract strict trong ví dụ.

~~~java
@Configuration
public class RSocketCodecConfiguration {

    @Bean
    ObjectMapper wireObjectMapper() {
        return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
    }

    @Bean
    RSocketStrategies rSocketStrategies(
            ObjectMapper wireObjectMapper) {

        return RSocketStrategies.builder()
            .encoders(encoders ->
                encoders.add(
                    new Jackson2JsonEncoder(wireObjectMapper)
                )
            )
            .decoders(decoders ->
                decoders.add(
                    new Jackson2JsonDecoder(wireObjectMapper)
                )
            )
            .build();
    }
}
~~~

Các import liên quan thường thuộc Jackson Databind, Jackson datatype-jsr310, Spring HTTP codec và Spring Messaging RSocket. Hãy dùng phiên bản Spring/Jackson đang được project quản lý; constructor và codec API có thể thay đổi giữa các phiên bản.

Nếu muốn consumer bỏ qua field mới, có thể chọn cấu hình khác:

~~~java
ObjectMapper tolerantMapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Không nên áp dụng lựa chọn này một cách mù quáng. Tắt strict unknown-field giúp forward compatibility với field additive, nhưng có thể che giấu việc producer gửi sai tên field hoặc schema bị lệch. Cân nhắc strict contract tests trong CI và tolerant reader policy ở runtime.

## 8. Các lỗi kiểu dữ liệu liên ngôn ngữ

Java và JavaScript không có cùng miền biểu diễn cho mọi kiểu.

| Dữ liệu | Java | JavaScript | Khuyến nghị wire |
|---|---|---|---|
| Số lượng nhỏ | int/Integer | number | JSON integer có giới hạn |
| ID 64-bit | long | number không an toàn ở miền lớn | JSON string |
| Tiền | BigDecimal | Number floating point | Decimal string hoặc minor units |
| Thời gian | Instant | Date (mili giây) | ISO-8601 UTC string |
| Enum | enum | string | String có unknown-value policy |
| Binary | byte[] | Uint8Array | Codec binary đã thống nhất |
| Optional | null/reference | undefined/null | Quy tắc absent/null rõ |

### Số nguyên lớn

JavaScript Number chỉ biểu diễn chính xác mọi số nguyên tới 2^53 - 1. Nếu server gửi long lớn hơn giới hạn này dưới dạng JSON number, browser có thể parse thành một số gần đúng mà không báo lỗi.

Ví dụ nên gửi ID lớn dưới dạng string:

~~~json
{
  "eventSequence": "9223372036854775806"
}
~~~

Java có thể parse sang long/BigInteger sau khi validate; JavaScript có thể dùng BigInt nội bộ và chuyển về string khi serialize.

### Decimal và tiền tệ

Java BigDecimal có độ chính xác thập phân; JavaScript Number dùng floating point nhị phân. Tránh truyền tiền dưới dạng JSON number khi yêu cầu chính xác tuyệt đối.

~~~json
{
  "currency": "VND",
  "amount": "125000.50"
}
~~~

Hợp đồng phải quy định scale, dấu thập phân, currency và rounding. Không thêm dấu phân cách hàng nghìn.

### Timestamp

Dùng ISO-8601 UTC có hậu tố Z:

~~~json
{
  "createdAt": "2026-11-22T10:15:30.125Z"
}
~~~

Java dùng Instant; JavaScript Date chỉ giữ độ chính xác tới mili giây. Nếu cần nano giây, truyền representation riêng có định nghĩa rõ, ví dụ epochSeconds và nanos.

## 9. Enum mới và giá trị chưa biết

Giả sử server thêm trạng thái EXPIRED:

~~~java
public enum ReservationStatus {
    HELD,
    RELEASED,
    EXPIRED
}
~~~

Client cũ chỉ biết HELD và RELEASED. Khi nhận EXPIRED, decoder có thể ném lỗi nếu enum mapping strict.

Các lựa chọn thiết kế:

- Để wire value là string và xử lý unknown value thành UNKNOWN ở application layer.
- Cấu hình enum fallback nếu thư viện hỗ trợ và policy phù hợp.
- Dùng version mới nếu client phải thực hiện logic bắt buộc cho enum mới.
- Triển khai server theo giai đoạn để client cũ có thời gian cập nhật.

Không tự động ánh xạ mọi enum lạ thành một trạng thái nghiệp vụ có side effect. UNKNOWN có thể dùng cho hiển thị hoặc log; các thao tác quan trọng vẫn cần từ chối nếu không hiểu trạng thái.

## 10. Quy tắc đặt tên field và serializer

Tên field là một phần hợp đồng. Java có thể dùng camelCase, snake_case hoặc annotation tùy cấu hình Jackson. JavaScript có thể tự tạo key theo quy ước riêng.

Ví dụ server mong đợi:

~~~json
{
  "orderId": "order-42",
  "createdAt": "2026-11-22T10:15:30Z"
}
~~~

Nhưng client gửi:

~~~json
{
  "order_id": "order-42",
  "created_at": "2026-11-22T10:15:30Z"
}
~~~

Nếu ObjectMapper không cấu hình naming strategy tương ứng hoặc DTO không dùng JsonProperty, field có thể bị bỏ qua hoặc gây lỗi.

Nên chọn một quy ước wire duy nhất và kiểm thử nó. Nếu cần mapping khác tên Java:

~~~java
public record OrderEvent(
    @JsonProperty("order_id") String orderId,
    @JsonProperty("created_at") Instant createdAt
) {}
~~~

Không đổi naming strategy giữa các service mà không version hóa hoặc có giai đoạn tương thích.

## 11. Metadata decode là một đường riêng

RSocket metadata không được giải mã bằng data DTO một cách tự động. Routing metadata, Composite Metadata và custom metadata có format riêng.

Ví dụ Composite Metadata có thể chứa:

- Routing entry với MIME type routing chuẩn.
- Authentication metadata.
- Tenant metadata dạng JSON vendor MIME type.
- Correlation/trace metadata.

Khi Spring không trích xuất custom entry, handler có thể thiếu header dù data JSON hoàn toàn hợp lệ.

### Đăng ký custom metadata extractor

~~~java
@Configuration
public class RSocketMetadataConfiguration {

    static final MimeType TENANT_MIME =
        MimeType.valueOf(
            "application/vnd.acme.tenant-v1+json"
        );

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
            })
            .build();
    }
}
~~~

Handler:

~~~java
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
~~~

Tên header tenant phải khớp tên đã đăng ký trong metadataToExtract. Client phải gửi entry bằng đúng TENANT_MIME và encode JSON theo schema TenantContext đã thống nhất.

Metadata có thể được parse thành object nhưng vẫn không đáng tin cậy về mặt bảo mật. tenantId trong metadata không phải bằng chứng xác thực; server phải xác thực principal và kiểm tra quyền truy cập.

## 12. Phân biệt routing metadata với custom metadata

Một số lỗi thường gặp:

- Gửi route dưới dạng JSON custom trong khi server chờ routing entry chuẩn.
- Gửi Composite Metadata nhưng quên khai báo metadata MIME type ở SETUP.
- Dùng routing MIME type sai.
- Gửi tenant entry dưới application/json nhưng server đăng ký vendor MIME type.
- Gửi entry với length/encoding sai khi tự ghép byte.
- Gửi metadata dạng text trong khi server chờ binary codec.

Dùng encoder/metadata API của thư viện RSocket thay vì tự ghép Composite Metadata bytes. Composite Metadata là định dạng nhị phân gồm header MIME type và length; một chuỗi JSON đơn giản không thể thay thế toàn bộ cấu trúc đó.

Khi debug, log tên MIME type, số byte metadata và loại entry đã nhận. Không log token, credential hoặc toàn bộ metadata thô.

## 13. Schema evolution và tương thích phiên bản

Schema thay đổi theo thời gian. Một service mới có thể giao tiếp với client cũ trong giai đoạn rolling deployment. Cần xác định thay đổi nào tương thích.

| Thay đổi | Tương thích thường gặp | Cách xử lý |
|---|---|---|
| Thêm field optional | Thường tương thích nếu reader bỏ qua unknown field | Có default/optional semantics |
| Thêm field required | Không tương thích với producer cũ | Giai đoạn chuyển tiếp hoặc version mới |
| Xóa field | Có thể phá consumer cũ | Deprecate trước, duy trì alias |
| Đổi tên field | Không tương thích nếu không có alias | Hỗ trợ cả tên cũ/mới trong giai đoạn |
| Đổi kiểu field | Thường không tương thích | Field mới hoặc version mới |
| Thêm enum value | Có điều kiện | Unknown-value policy |
| Đổi ý nghĩa field | Nguy hiểm dù decode thành công | Version mới và migration |
| Đổi data MIME type | Cần hai phía hỗ trợ | Dual-read/dual-write theo kế hoạch |

### Version trong payload

Ví dụ:

~~~json
{
  "contractVersion": 2,
  "orderId": "order-42",
  "priority": "HIGH"
}
~~~

Server có thể chọn schema theo contractVersion. Tuy nhiên, field version chỉ có ích khi decoder đủ linh hoạt để đọc envelope và chuyển đến schema tương ứng. Nếu DTO version 1 không biết contractVersion hoặc decoder strict, cần thiết kế envelope riêng hoặc route/version MIME type phù hợp.

### Version trong MIME type

Với custom metadata hoặc payload format chuyên biệt, có thể dùng vendor MIME type có version:

~~~text
application/vnd.acme.order-v1+json
application/vnd.acme.order-v2+json
application/vnd.acme.tenant-v1+json
~~~

MIME type version giúp codec selection rõ ràng. Nó không thay thế schema validation và không tự động migrate dữ liệu.

## 14. Nếu dùng Protobuf hoặc CBOR

JSON không phải lựa chọn duy nhất. Với codec binary, nguyên tắc vẫn giống nhau: hai peer phải thống nhất MIME type, schema và phiên bản serializer.

### Protobuf

Protobuf dùng field number thay vì tên field JSON làm định danh trên wire. Khi thay đổi schema:

- Không tái sử dụng field number đã xóa.
- Đánh dấu field number/name đã xóa là reserved.
- Thêm field mới bằng field number mới.
- Giữ đúng wire type tương thích.
- Không đổi ý nghĩa field cũ.
- Kiểm thử producer mới với consumer cũ và ngược lại.

Một Protobuf message có thể decode thành công nhưng vẫn hiểu sai nếu hai phía tái sử dụng field number cho ý nghĩa khác. Vì vậy compatibility check của schema quan trọng hơn việc chỉ kiểm tra decoder không ném exception.

### CBOR và serializer khác

CBOR có thể giảm kích thước và hỗ trợ kiểu dữ liệu phong phú hơn JSON, nhưng cần cùng quy tắc mapping và codec. Đừng gửi CBOR bytes với data MIME type application/json.

Nếu đổi serializer, cần triển khai tương thích theo giai đoạn:

1. Server hỗ trợ đọc cả format cũ và mới nếu kiến trúc cho phép.
2. Client mới gửi format mới.
3. Theo dõi số peer còn dùng format cũ.
4. Ngừng format cũ sau khi hết client.
5. Gỡ decoder cũ ở release sau.

## 15. Đọc exception để tìm nguyên nhân

Thông báo exception thường giúp thu hẹp vấn đề:

| Exception/dấu hiệu | Khả năng | Việc kiểm tra |
|---|---|---|
| JsonParseException | JSON sai cú pháp | Byte thực tế, dấu phẩy, quote, truncation |
| MismatchedInputException | JSON shape/type không khớp DTO | Object/array/string/number mong đợi |
| InvalidFormatException | Giá trị không chuyển được kiểu | Enum, date, number format |
| UnrecognizedPropertyException | Field lạ với decoder strict | Schema version, naming, unknown-field policy |
| InvalidDefinitionException | DTO/serializer không được cấu hình đúng | Constructor, record, module, annotation |
| DecodingException | Lỗi ở codec layer | MIME type, decoder và root cause |
| No decoder for type/MIME | Codec không hỗ trợ kiểu hoặc MIME | RSocketStrategies và content type |
| Missing header/metadata | Metadata không được extract | Composite Metadata entry và extractor |
| Validation error | Decode thành công nhưng dữ liệu không hợp lệ | Constraint và business rules |

Tên exception và cách Spring bọc lỗi có thể khác theo phiên bản. Luôn xem root cause và vị trí xảy ra, không chỉ exception ngoài cùng.

### Đọc root cause

Khi log lỗi, ghi:

- Route hoặc interaction type.
- Data MIME type và metadata MIME type.
- Contract/schema version nếu có.
- DTO type đích.
- Exception class và root cause.
- Request/correlation ID đã được làm sạch.
- Stream ID nếu tầng instrumentation cung cấp.

Không ghi nguyên payload hoặc token để tìm lỗi. Thay vào đó, dùng fixture tái hiện đã loại bỏ dữ liệu nhạy cảm, byte length, hash hoặc mẫu dữ liệu giả.

## 16. Quy trình chẩn đoán từng bước

Khi nhận lỗi decode trong production, đi theo thứ tự:

1. Xác nhận transport và RSocket connection đã được thiết lập.
2. Xác định lỗi ở SETUP, connection-level hay stream-level.
3. Ghi route, interaction type và stream ID nếu có.
4. Đọc data MIME type và metadata MIME type đã thương lượng.
5. Xác định serializer/codec ở cả hai peer.
6. Lấy fixture hoặc payload giả lập cùng cấu trúc để tái hiện.
7. Kiểm tra UTF-8, JSON syntax hoặc binary format.
8. Decode payload bằng đúng ObjectMapper/codec runtime.
9. So sánh field name, type, null, default, enum và timestamp.
10. Kiểm tra metadata entry riêng, MIME type và extractor.
11. Chạy schema validation và business validation riêng.
12. Kiểm thử chéo với phiên bản producer/consumer cũ và mới.
13. Sửa contract hoặc codec, bổ sung regression test.
14. Triển khai theo giai đoạn và theo dõi decode failure rate.

Không sửa nhiều biến cùng lúc. Ví dụ đổi DTO, tắt unknown property và thay MIME type cùng một release sẽ khiến khó xác định nguyên nhân thực sự.

## 17. Tạo golden fixture dùng chung

Golden fixture là payload mẫu chuẩn được lưu trong repository contract hoặc bộ test. Java, JavaScript và các service khác cùng đọc fixture đó.

Ví dụ request fixture:

~~~json
{
  "contractVersion": 1,
  "requestId": "req-42",
  "sku": "SKU-42",
  "quantity": 3,
  "requestedAt": "2026-11-22T10:15:30.000Z"
}
~~~

Response fixture:

~~~json
{
  "contractVersion": 1,
  "requestId": "req-42",
  "sku": "SKU-42",
  "available": true,
  "availableQuantity": 18,
  "checkedAt": "2026-11-22T10:15:30.125Z"
}
~~~

Metadata fixture:

~~~json
{
  "tenantId": "tenant-17"
}
~~~

Mỗi fixture cần ghi rõ:

- Data hay metadata.
- MIME type.
- Route và interaction type.
- Schema/contract version.
- Producer/consumer direction.
- Các field bắt buộc và tùy chọn.
- Kết quả parse/validation mong đợi.

Không so sánh raw JSON string theo thứ tự key nếu thứ tự key không thuộc hợp đồng. Parse JSON rồi so sánh cấu trúc và giá trị. Nếu payload được ký số hoặc hash, cần canonicalization được định nghĩa riêng.

## 18. Contract test Java với Jackson

Một test Java nên dùng cùng ObjectMapper và module như runtime. Ví dụ:

~~~java
class InventoryPayloadContractTest {

    private final ObjectMapper mapper =
        JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();

    @Test
    void decodesCanonicalFixture() throws Exception {
        String json = """
            {
              "contractVersion": 1,
              "requestId": "req-42",
              "sku": "SKU-42",
              "quantity": 3,
              "requestedAt": "2026-11-22T10:15:30.000Z"
            }
            """;

        InventoryCheckRequest request =
            mapper.readValue(json, InventoryCheckRequest.class);

        assertThat(request.sku()).isEqualTo("SKU-42");
        assertThat(request.quantity()).isEqualTo(3);
        assertThat(request.requestId()).isEqualTo("req-42");
    }
}
~~~

Kiểm thử encode:

~~~java
@Test
void encodesExpectedWireFields() throws Exception {
    InventoryCheckRequest request = sampleRequest();

    JsonNode tree = mapper.readTree(
        mapper.writeValueAsBytes(request)
    );

    assertThat(tree.path("sku").asText()).isEqualTo("SKU-42");
    assertThat(tree.path("quantity").asInt()).isEqualTo(3);
    assertThat(tree.path("contractVersion").asInt()).isEqualTo(1);
}
~~~

Test cần xác nhận cả chiều đọc và chiều ghi. Một DTO đọc được fixture không chứng minh serializer sẽ tạo đúng field names hoặc format timestamp khi phát ra.

## 19. Contract test JavaScript

JavaScript đọc cùng fixture và kiểm tra schema:

~~~javascript
function validateInventoryRequest(value) {
  if (value.contractVersion !== 1) {
    throw new Error("Unsupported contractVersion");
  }

  if (typeof value.requestId !== "string" ||
      value.requestId.length === 0) {
    throw new Error("requestId must be a non-empty string");
  }

  if (typeof value.sku !== "string" ||
      value.sku.length === 0) {
    throw new Error("sku must be a non-empty string");
  }

  if (!Number.isSafeInteger(value.quantity) ||
      value.quantity <= 0) {
    throw new Error("quantity must be a positive safe integer");
  }

  if (typeof value.requestedAt !== "string" ||
      Number.isNaN(Date.parse(value.requestedAt))) {
    throw new Error("requestedAt must be a valid timestamp");
  }

  return value;
}
~~~

Nếu dùng JSON Schema, có thể chạy cùng schema trong test JavaScript bằng validator như Ajv và dùng validator tương ứng phía Java. Hãy pin schema version và validator version để tránh kết quả khác nhau giữa môi trường.

Contract test hai chiều cần xác nhận:

| Producer | Consumer | Điều cần xác nhận |
|---|---|---|
| Java | JavaScript | Browser parse được payload do Java tạo |
| JavaScript | Java | Jackson decode đúng payload từ browser |
| Java | Java | Backend round-trip |
| JavaScript | JavaScript | Browser serializer/parser |
| Java metadata | Spring extractor | MIME type và metadata object đúng |
| Browser metadata | Spring extractor | Composite entry được decode đúng |

Test Java round-trip riêng lẻ không đủ để chứng minh tương thích liên ngôn ngữ.

## 20. Kiểm thử qua RSocket thật

Sau unit contract test, cần integration test qua transport thật để kiểm tra cả SETUP, MIME type, routing metadata và codec.

Một kịch bản request-response:

~~~mermaid
sequenceDiagram
    participant C as JavaScript / Java client
    participant R as RSocket transport
    participant S as Spring responder
    C->>R: SETUP with data/metadata MIME types
    R->>S: Connection established
    C->>R: REQUEST_RESPONSE + route metadata
    C->>R: JSON data bytes
    R->>S: Payload
    S->>S: Decode data and extract metadata
    S->>S: Validate DTO
    S-->>R: Encoded response payload
    R-->>C: Response bytes
    C->>C: Decode and validate response
~~~

Test cần xác nhận:

- SETUP dùng MIME type mong đợi.
- Route được trích xuất đúng.
- Data được decode thành đúng DTO.
- Custom metadata được ánh xạ đúng header.
- Response được encode theo contract.
- Lỗi decode trả về error có thể quan sát và không làm lộ payload.
- Một stream lỗi không bị hiểu nhầm là toàn bộ connection hỏng nếu protocol/session vẫn hoạt động.

Nếu browser là một peer, chạy test qua WebSocket/WSS trong browser automation hoặc browser runtime tương đương. Test Node thuần không kiểm tra hết hành vi WebSocket, cookie và Origin của browser.

## 21. Test dữ liệu biên và schema compatibility

Bộ test nên bao gồm cả payload hợp lệ và payload phải bị từ chối.

| Case | Payload | Kết quả mong đợi |
|---|---|---|
| Field bắt buộc thiếu | Không có sku | Validation/decode failure theo contract |
| Sai kiểu | quantity là "three" | Mapping failure |
| Quantity âm | quantity = -1 | Domain validation failure |
| Field mới | Có warehouseRegion | Consumer cũ bỏ qua hoặc xử lý theo policy |
| Null | displayName = null | Theo null semantics |
| Field vắng mặt | Không có displayName | Theo absent/default semantics |
| Enum mới | status = "EXPIRED" | Unknown-value policy |
| ID lớn | String số 64-bit | Giữ nguyên chính xác |
| Decimal | amount = "125000.50" | Không mất độ chính xác |
| Timestamp không timezone | Local datetime | Reject nếu contract yêu cầu UTC |
| Unicode | Tiếng Việt và ký tự ngoài BMP | Round-trip chính xác |
| JSON double encoded | String chứa JSON | Reject hoặc phát hiện sai shape |
| MIME type sai | JSON bytes gắn MIME khác | Không chọn sai decoder |
| Metadata thiếu | Không có tenant entry | Reject nếu tenant là bắt buộc |
| Payload truncated | JSON/binary bị cắt | Decode failure có phân loại |

### Compatibility matrix

Kiểm thử producer/consumer cũ và mới:

| Producer | Consumer | Mục tiêu |
|---|---|---|
| v1 | v1 | Baseline |
| v1 | v2 | Consumer mới đọc dữ liệu cũ |
| v2 | v1 | Consumer cũ chịu được field mới nếu contract cho phép |
| v2 | v2 | Phiên bản hiện tại |
| v2 metadata | v1 metadata decoder | Xác nhận chính sách version/fallback |

Nếu thay đổi không tương thích, phải dùng version mới hoặc triển khai giai đoạn chuyển tiếp. Không để hai phía cùng deploy một thay đổi breaking trong rolling upgrade mà không có cơ chế tương thích.

## 22. Quan sát và log lỗi decode an toàn

Metric nên phân loại lỗi theo lớp:

- Codec selection failure.
- JSON/binary parse failure.
- DTO mapping failure.
- Metadata extraction failure.
- Schema validation failure.
- Business validation failure.
- Unsupported contract version.

Tag có cardinality thấp:

- service.
- peer.
- route.
- data MIME type.
- metadata MIME type.
- contract version.
- codec.
- error category.
- transport.

Không đưa requestId duy nhất, userId, tenantId tùy ý hoặc raw payload vào metric label.

Structured log có thể ghi:

~~~json
{
  "event": "rsocket.payload.decode.failed",
  "service": "inventory-service",
  "peer": "order-service",
  "route": "inventory.check",
  "transport": "tcp",
  "dataMimeType": "application/json",
  "metadataMimeType": "message/x.rsocket.composite-metadata.v0",
  "targetType": "InventoryCheckRequest",
  "contractVersion": 1,
  "errorCategory": "DTO_MAPPING",
  "exception": "MismatchedInputException",
  "payloadBytes": 148,
  "correlationId": "corr-91"
}
~~~

Ví dụ payloadBytes là số byte, không phải nội dung. correlationId cần được kiểm soát theo chính sách log. Không ghi token, credential, PII hoặc payload thô.

## 23. Các lỗi sửa chữa dễ làm vấn đề nghiêm trọng hơn

| Cách sửa vội | Rủi ro | Cách sửa đúng |
|---|---|---|
| Tắt mọi validation | Dữ liệu sai lọt vào domain | Phân biệt decode và domain validation |
| Bỏ qua mọi unknown field | Che giấu producer gửi sai tên | Có strict contract test và tolerant runtime policy phù hợp |
| Ép mọi number về String | Làm thay đổi wire contract | Quy định kiểu từng field |
| Chuyển mọi payload thành UTF-8 String | Phá binary codec | Dựa vào MIME type |
| Bắt mọi exception rồi trả null | Mất nguyên nhân và tạo lỗi thứ cấp | Phân loại và trả lỗi có ngữ nghĩa |
| Retry mọi decode failure | Payload sai không tự trở nên hợp lệ | Chỉ retry lỗi transient |
| Đổi DTO mà không fixture test | Peer khác ngôn ngữ vẫn lỗi | Golden fixtures và cross-language tests |
| Tự ghép Composite Metadata | Sai MIME/length/header | Dùng API encoder chuẩn |
| Log payload đầy đủ | Rò rỉ dữ liệu nhạy cảm | Log metadata kỹ thuật đã làm sạch |
| Dùng cùng DTO class làm contract | Các ngôn ngữ khác không chia sẻ được class | Schema độc lập với runtime |

## 24. Quy trình xử lý lỗi trong production

1. Thu thập correlation ID, route, interaction type và thời điểm lỗi.
2. Xác định lỗi ở transport, SETUP, connection hay stream.
3. Đối chiếu data MIME type và metadata MIME type.
4. Xác định serializer/codec thực tế ở client và server.
5. Lấy payload fixture đã làm sạch để tái hiện.
6. Parse byte bằng codec đúng với runtime.
7. Kiểm tra field name, kiểu, null, default, enum, number và timestamp.
8. Kiểm tra custom metadata entry và MetadataExtractor.
9. Phân biệt decode failure với validation/business error.
10. Tạo regression test bằng fixture gây lỗi.
11. Cập nhật schema hoặc codec theo chiến lược versioning.
12. Chạy compatibility matrix cũ/mới và integration test RSocket.
13. Triển khai theo giai đoạn, theo dõi error rate theo codec/version.
14. Gỡ schema/codec cũ khi không còn peer sử dụng.

Quy trình này giúp sửa đúng nguyên nhân. Một lỗi do MIME type sai cần sửa negotiation hoặc codec registration; một lỗi do enum mới cần unknown-value policy hoặc versioning; một lỗi do quantity âm cần domain validation, không phải thay serializer.

## Ghi nhớ

- RSocket truyền byte; protocol không tự định nghĩa schema nghiệp vụ của data.
- Data MIME type và metadata MIME type là hai cấu hình riêng.
- Composite Metadata chứa các entry có MIME type riêng.
- JSON sai cú pháp khác JSON hợp lệ nhưng không map được DTO.
- Double encoding có thể khiến server nhận String thay vì object.
- Field vắng mặt, null và giá trị mặc định có semantics khác nhau.
- Java long, BigDecimal, Instant và enum cần quy tắc wire rõ khi giao tiếp với JavaScript.
- Schema evolution cần chính sách field mới, field bắt buộc, enum mới và version.
- Metadata decode phải được kiểm tra riêng với data decode.
- Golden fixture và contract test hai chiều mới chứng minh tương thích liên ngôn ngữ.
- Log MIME type, route, codec và exception category; không log token hoặc payload nhạy cảm.
- Chỉ retry lỗi transient; payload sai schema cần sửa contract hoặc producer/consumer.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [RSocket Composite Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/CompositeMetadata.md)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — RSocketStrategies API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [Spring Framework — Jackson2JsonDecoder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/json/Jackson2JsonDecoder.html)
- [Jackson — Deserialization Features](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/DeserializationFeature.html)
- [JSON Schema](https://json-schema.org/learn/getting-started-step-by-step)
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating)
- [MDN — JSON.parse](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/JSON/parse)
- [MDN — Number.MAX_SAFE_INTEGER](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Number/MAX_SAFE_INTEGER)

