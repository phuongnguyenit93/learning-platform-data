# Đăng ký encoder, decoder và thứ tự lựa chọn codec

Trong Spring RSocket, object Java không được gửi trực tiếp qua mạng. Framework cần một `Encoder` để chuyển object thành bytes và một `Decoder` để biến bytes nhận được thành object. Việc chọn codec phụ thuộc vào kiểu Java cần chuyển đổi và MIME type của phần data hoặc metadata. Khi có nhiều codec cùng hỗ trợ một kiểu và MIME type, thứ tự đăng ký có thể quyết định codec nào được chọn.

`RSocketStrategies` là nơi tập hợp encoder, decoder, metadata extractor và các thành phần chuyển đổi mà `RSocketRequester` cùng message handler phía server sử dụng. Đăng ký codec đúng giúp client và server hiểu cùng định dạng; sắp xếp codec đúng giúp tránh trường hợp một codec tổng quát hoặc codec mặc định chiếm quyền xử lý trước codec chuyên biệt.

## 1. Encoder và Decoder trong Spring

`Encoder<T>` chuyển một giá trị Java thành `DataBuffer` theo MIME type được yêu cầu. `Decoder<T>` thực hiện chiều ngược lại: nhận bytes và tạo ra giá trị Java. Các codec thường hỗ trợ một hoặc nhiều MIME type và một tập kiểu dữ liệu nhất định.

Spring dùng hai thông tin chính để xác định codec phù hợp:

- **Java type:** kiểu cần encode/decode, ví dụ `DeviceQuery`, `DeviceStatus`, `byte[]` hoặc `String`.
- **MIME type:** định dạng của bytes, ví dụ `application/json`, `application/cbor` hoặc `application/octet-stream`.

Một codec chỉ phù hợp khi nó hỗ trợ cả kiểu Java và MIME type tương ứng. Ví dụ, Jackson JSON encoder phù hợp với DTO có thể serialize thành JSON khi MIME type là JSON; byte array encoder phù hợp với `byte[]` và định dạng nhị phân.

| Codec | Kiểu dữ liệu thường dùng | MIME type thường gặp |
|---|---|---|
| `Jackson2JsonEncoder` | DTO, record, object Java | `application/json`, các MIME type JSON tương thích |
| `Jackson2JsonDecoder` | DTO, record, object Java | `application/json`, các MIME type JSON tương thích |
| `ByteArrayEncoder` / `ByteArrayDecoder` | `byte[]` | `application/octet-stream` |
| `StringEncoder` / `StringDecoder` | `String` | `text/plain` |
| CBOR codec | DTO được biểu diễn bằng CBOR | `application/cbor` |
| Protobuf codec | Protobuf generated message | MIME type Protobuf đã thống nhất |

Tên codec cụ thể có thể thay đổi theo phiên bản Spring và dependency được thêm vào. Điều cần kiểm tra là codec có hỗ trợ đúng `ResolvableType` và MIME type của payload hay không.

## 2. Phân biệt codec của data và metadata

Một RSocket payload có hai phần logic: data và metadata. Cả hai đều là bytes, nhưng chúng có thể dùng MIME type và mục đích khác nhau.

| Phần | Vai trò | Ví dụ |
|---|---|---|
| Data | Nội dung nghiệp vụ của request/response | `DeviceQuery`, `OrderCommand` |
| Metadata | Thông tin định tuyến hoặc ngữ cảnh | Route, tenant, trace ID, credential |

`dataMimeType` cho biết định dạng mặc định của data trong connection. `metadataMimeType` cho biết định dạng của metadata section. Khi metadata dùng Composite Metadata, section là một container chứa nhiều entry; từng entry có MIME type riêng.

Ví dụ client dùng JSON cho data và Composite Metadata cho metadata:

```java
private static final MimeType JSON = MimeTypeUtils.APPLICATION_JSON;
private static final MimeType COMPOSITE = MimeType.valueOf(
    "message/x.rsocket.composite-metadata.v0");

Mono<RSocketRequester> connection = RSocketRequester.builder()
    .dataMimeType(JSON)
    .metadataMimeType(COMPOSITE)
    .rsocketStrategies(strategies)
    .connectTcp(host, port);
```

Encoder cho `DeviceQuery` được chọn theo kiểu của object và `dataMimeType`. Khi gửi metadata object với `.metadata(value, mimeType)`, codec cần hỗ trợ kiểu metadata và MIME type cụ thể của entry đó. Ở phía nhận, decoder hoặc metadata extractor cần hiểu cùng MIME type và cấu trúc bytes.

## 3. RSocketStrategies tập hợp codec như thế nào?

`RSocketStrategies` cung cấp danh sách encoder và decoder theo thứ tự, cùng metadata extractor, data buffer factory, route matcher và reactive adapter registry. Client có thể truyền strategies vào `RSocketRequester.Builder`; server dùng strategies để giải mã request, trích xuất metadata và mã hóa response.

Một cấu hình cơ bản:

```java
@Configuration
public class RSocketCodecConfiguration {

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
            .encoders(encoders ->
                encoders.add(new Jackson2JsonEncoder()))
            .decoders(decoders ->
                decoders.add(new Jackson2JsonDecoder()))
            .build();
    }
}
```

Đây là cách thêm JSON encoder/decoder vào danh sách strategies. Builder và Spring Boot có thể cung cấp các codec mặc định tùy phiên bản và classpath. Trước khi thêm codec, hãy kiểm tra danh sách hiện có để tránh đăng ký trùng. Nếu cần tùy chỉnh một codec mặc định, thay thế đúng codec đó hoặc thay đổi vị trí của nó thay vì thêm nhiều codec giống nhau.

Khi một component tự tạo `RSocketRequester`, truyền cùng `RSocketStrategies` mà ứng dụng dự định sử dụng:

```java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(JSON)
    .metadataMimeType(COMPOSITE)
    .rsocketStrategies(strategies)
    .connectTcp(host, port)
    .block(); // Chỉ dùng ở ranh giới bootstrap đồng bộ
```

Trong pipeline reactive, giữ kết quả `Mono<RSocketRequester>` và không gọi `block()` trong handler hoặc service. Trong ứng dụng thật, connection nên được quản lý và tái sử dụng bởi một lifecycle owner.

## 4. Spring chọn codec theo Java type và MIME type

Khi cần encode một object, framework tìm encoder có thể xử lý kiểu Java đó và MIME type được yêu cầu. Khi decode, framework tìm decoder tương ứng với kiểu đích và MIME type của bytes nhận được. Các phương thức kiểm tra khả năng hỗ trợ trong codec là `canEncode(ResolvableType, MimeType)` và `canDecode(ResolvableType, MimeType)`.

Ví dụ về điều kiện lựa chọn:

```java
ResolvableType targetType = ResolvableType.forClass(DeviceQuery.class);
MimeType mimeType = MimeTypeUtils.APPLICATION_JSON;

boolean canEncode = encoder.canEncode(targetType, mimeType);
boolean canDecode = decoder.canDecode(targetType, mimeType);
```

`canEncode` hoặc `canDecode` trả về `true` chỉ nói rằng codec có khả năng xử lý cặp kiểu/MIME type đó. Nó không chứng minh payload cụ thể hợp lệ hoặc hai phía có cùng schema. JSON sai cú pháp vẫn có thể khiến decoder phát lỗi dù MIME type và kiểu đích được hỗ trợ.

Trong quá trình chọn codec, thứ tự danh sách có ý nghĩa: codec phù hợp xuất hiện trước có thể được chọn trước codec phù hợp xuất hiện sau. Vì vậy, nếu hai codec cùng hỗ trợ `DeviceQuery` và `application/json`, codec đứng trước thường quyết định cách bytes được tạo hoặc giải mã. Hãy tránh cấu hình nhiều codec chồng lấn nếu không có lý do rõ ràng.

## 5. Vì sao thứ tự codec quan trọng?

Giả sử ứng dụng có:

- Một JSON codec tổng quát hỗ trợ nhiều DTO.
- Một codec chuyên biệt cho `DeviceQuery` để chuẩn hóa trường hoặc tối ưu định dạng.
- Một binary codec chỉ hỗ trợ `byte[]`.

Nếu codec JSON tổng quát đứng trước codec chuyên biệt và cả hai đều trả `true` cho `DeviceQuery` cùng MIME type, codec tổng quát có thể được dùng. Codec chuyên biệt dù đã đăng ký vẫn không được gọi.

Nguyên tắc sắp xếp thường dùng:

1. Codec chuyên biệt cho một kiểu hoặc MIME type cụ thể.
2. Codec cho định dạng ứng dụng có phạm vi hỗ trợ rõ ràng.
3. Codec tổng quát như JSON cho nhiều DTO.
4. Codec fallback hoặc codec ít đặc hiệu hơn, nếu có.

Không có lợi ích khi đưa mọi custom codec lên đầu một cách máy móc. Chỉ ưu tiên codec có phạm vi cụ thể và cần thắng một codec khác đang overlap. Với các MIME type khác nhau, thứ tự không ảnh hưởng nếu chỉ một codec hỗ trợ MIME type đang dùng.

## 6. Đặt codec chuyên biệt trước codec tổng quát

Các builder API nhận consumer của danh sách codec, do đó có thể thêm codec vào đầu danh sách:

```java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> {
        encoders.add(0, new DeviceQueryEncoder());
        encoders.add(new Jackson2JsonEncoder());
    })
    .decoders(decoders -> {
        decoders.add(0, new DeviceQueryDecoder());
        decoders.add(new Jackson2JsonDecoder());
    })
    .build();
```

Ví dụ giả định `DeviceQueryEncoder` và `DeviceQueryDecoder` là codec ứng dụng đã được triển khai và chỉ nhận kiểu/MIME type chuyên biệt. Codec JSON tổng quát xử lý các DTO còn lại. Nếu builder đã có codec mặc định, cần kiểm tra danh sách và chèn/thay thế tại vị trí phù hợp để không tạo bản sao không cần thiết.

Một cách khác để tránh xung đột là dùng MIME type riêng cho codec chuyên biệt, ví dụ `application/vnd.example.device-query-v1`. Khi MIME type khác nhau, codec JSON tổng quát chỉ nên nhận định dạng mà nó thực sự hỗ trợ. MIME type riêng cần được cả client và server triển khai đồng bộ.

## 7. Thay thế hoặc cấu hình Jackson codec

Nếu cần cấu hình Jackson với `ObjectMapper` riêng, hãy dùng cùng cấu hình module, naming strategy, date/time và polymorphic typing mà contract yêu cầu:

```java
@Configuration
public class RSocketCodecConfiguration {

    @Bean
    RSocketStrategies rSocketStrategies(ObjectMapper objectMapper) {
        return RSocketStrategies.builder()
            .encoders(encoders -> {
                encoders.removeIf(Jackson2JsonEncoder.class::isInstance);
                encoders.add(0, new Jackson2JsonEncoder(objectMapper));
            })
            .decoders(decoders -> {
                decoders.removeIf(Jackson2JsonDecoder.class::isInstance);
                decoders.add(0, new Jackson2JsonDecoder(objectMapper));
            })
            .build();
    }
}
```

Đoạn mã loại bỏ Jackson codec cùng loại trước khi thêm bản dùng `ObjectMapper` của ứng dụng. Cách này tránh hai Jackson codec cạnh tranh cùng MIME type. Hãy xác minh API constructor của Spring Framework version trong dự án; nếu phiên bản dùng constructor hoặc cấu hình codec khác, giữ nguyên nguyên tắc thay thế codec cũ bằng một codec có cấu hình rõ ràng.

Không bật polymorphic deserialization không giới hạn chỉ để hỗ trợ nhiều kiểu DTO. Dữ liệu nhận qua mạng không đáng tin cậy; chỉ cho phép kiểu cần thiết và validate dữ liệu sau khi decode.

## 8. Codec cho metadata tùy chỉnh

Composite Metadata có thể chứa nhiều entry. Mỗi entry có MIME type riêng và có thể được decode thành một kiểu Java riêng.

Ví dụ định nghĩa tenant metadata:

```java
public record TenantMetadata(String tenantId) {}

static final MimeType TENANT_MIME =
    MimeType.valueOf("application/vnd.example.tenant+json");
```

Client thêm entry metadata:

```java
Mono<DeviceStatus> result = requester
    .route("devices.status")
    .metadata(new TenantMetadata("tenant-a"), TENANT_MIME)
    .data(new DeviceQuery("device-42"))
    .retrieveMono(DeviceStatus.class);
```

Để encode `TenantMetadata`, strategies phía client phải có encoder hỗ trợ kiểu này và `TENANT_MIME`. Nếu dùng Jackson JSON codec hỗ trợ MIME type `application/*+json`, có thể dùng codec đó. Nếu dùng định dạng khác, đăng ký codec tương ứng.

Ở server, `MetadataExtractorRegistry` ánh xạ entry thành header:

```java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
    .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
    .metadataExtractorRegistry(registry ->
        registry.metadataToExtract(
            TENANT_MIME, TenantMetadata.class, "tenant"))
    .build();
```

Handler nhận metadata đã trích xuất:

```java
@MessageMapping("devices.status")
public Mono<DeviceStatus> status(
        @Payload DeviceQuery query,
        @Header("tenant") TenantMetadata tenant) {
    return deviceService.getStatusForTenant(
        query.deviceId(), tenant.tenantId());
}
```

Metadata extractor cần decoder tương thích với MIME type và kiểu đích. Nếu không có decoder phù hợp, entry có thể không được trích xuất như mong muốn hoặc request phát sinh lỗi. Không xem tenant metadata là bằng chứng xác thực; server vẫn phải xác minh quyền của principal.

## 9. Phân biệt metadata extractor với decoder thông thường

Decoder thông thường chuyển data bytes của payload thành kiểu Java mà handler hoặc requester yêu cầu. Metadata extractor xử lý metadata section và ánh xạ các entry được nhận diện thành giá trị hoặc header trong message context.

| Thành phần | Đầu vào | Kết quả |
|---|---|---|
| Data decoder | Data bytes + target Java type + MIME type | DTO hoặc object nghiệp vụ |
| Data encoder | DTO/object + MIME type | Data bytes |
| Metadata decoder được extractor sử dụng | Metadata entry + MIME type + target type | Metadata object |
| Metadata extractor | Metadata section, thường là Composite Metadata | Header/value trong message context |

Routing metadata có thể được framework xử lý thông qua route matcher và metadata conventions. Metadata tùy chỉnh như tenant hoặc trace cần được đăng ký nếu handler muốn nhận thành header có kiểu. Không cần tự giải mã routing entry bằng code nghiệp vụ khi Spring đã xử lý route mapping.

## 10. Kiểm tra thứ tự codec đang được dùng

Khi có lỗi codec selection, hãy xem danh sách thực tế sau khi build strategies. `RSocketStrategies` cung cấp danh sách encoder/decoder để kiểm tra:

```java
strategies.encoders().forEach(codec ->
    log.info("RSocket encoder: {}", codec.getClass().getName()));

strategies.decoders().forEach(codec ->
    log.info("RSocket decoder: {}", codec.getClass().getName()));
```

Có thể kiểm tra codec nào hỗ trợ một cặp kiểu/MIME type:

```java
ResolvableType type = ResolvableType.forClass(DeviceQuery.class);
MimeType mime = MimeTypeUtils.APPLICATION_JSON;

strategies.encoders().stream()
    .filter(codec -> codec.canEncode(type, mime))
    .forEach(codec -> log.info("Can encode with {}", codec.getClass().getName()));
```

Nếu có nhiều codec được in ra, tất cả đều tuyên bố có thể encode cặp kiểu/MIME type đó. Hãy kiểm tra thứ tự trong danh sách và quyết định codec nào cần được ưu tiên. Đừng log payload hoặc metadata thực tế chỉ để chẩn đoán codec.

## 11. Kiểm thử codec và thứ tự lựa chọn

Nên kiểm thử ở ba mức:

1. **Codec unit test:** xác minh encoder tạo bytes đúng và decoder tái tạo object đúng với MIME type đã chọn.
2. **Strategies test:** xác minh danh sách codec, codec nào hỗ trợ type/MIME và thứ tự ưu tiên.
3. **RSocket integration test:** xác minh requester và server thật dùng cùng contract, routing và metadata extractor trên transport.

Ví dụ kiểm tra khả năng hỗ trợ:

```java
ResolvableType queryType = ResolvableType.forClass(DeviceQuery.class);
MimeType json = MimeTypeUtils.APPLICATION_JSON;

assertThat(strategies.encoders().get(0).canEncode(queryType, json))
    .isTrue();
```

Đây chỉ là kiểm tra codec đầu tiên có hỗ trợ cặp type/MIME hay không. Nếu test cần chứng minh một codec cụ thể được chọn, hãy assert class hoặc vị trí của codec và thực hiện encode/decode thật; `canEncode` riêng lẻ không chứng minh quá trình lựa chọn của mọi đường xử lý.

Các trường hợp nên có:

- Hai codec cùng hỗ trợ một type/MIME để xác minh thứ tự ưu tiên.
- Codec chuyên biệt được đặt trước codec tổng quát.
- MIME type không được hỗ trợ phải thất bại rõ ràng.
- JSON sai cú pháp phát lỗi decode, không bị biến thành empty completion.
- Metadata entry tùy chỉnh được encode và trích xuất đúng.
- Composite Metadata chứa routing và nhiều entry tùy chỉnh.
- Client và server dùng cùng MIME type nhưng schema không tương thích phải được phát hiện.
- Codec mặc định cho `String` và `byte[]` vẫn hoạt động sau khi thêm codec tùy chỉnh.

## 12. Lỗi thường gặp khi đăng ký codec

- Đăng ký codec nhưng codec không hỗ trợ MIME type đang dùng.
- Codec chuyên biệt nằm sau codec tổng quát có cùng khả năng hỗ trợ.
- Thêm Jackson codec trùng với codec mặc định mà không kiểm tra danh sách.
- Chỉ cấu hình encoder phía client nhưng quên decoder phía server, hoặc ngược lại.
- Dùng MIME type của Composite Metadata như MIME type của từng entry.
- Cấu hình decoder cho data nhưng không đăng ký metadata extractor cho entry tùy chỉnh.
- Dùng cùng MIME type cho hai định dạng bytes khác nhau.
- Thay `RSocketStrategies` của Spring Boot và vô tình làm mất codec mặc định cần thiết.
- Giả định MIME type giống nhau đồng nghĩa schema DTO giống nhau.
- Bật deserialize kiểu Java tùy ý từ dữ liệu do peer gửi.

## 13. Quy tắc thiết kế

1. Chọn codec theo cả Java type và MIME type; kiểm tra `canEncode`/`canDecode` khi chẩn đoán.
2. Dùng `RSocketStrategies` làm nơi tập trung quản lý encoder, decoder và metadata extractor.
3. Đặt codec chuyên biệt trước codec tổng quát khi chúng có phạm vi hỗ trợ chồng lấn.
4. Tránh codec trùng; thay thế codec mặc định có chủ đích khi cần tùy chỉnh.
5. Giữ lại codec mặc định cho `String`, `byte[]` và các kiểu ứng dụng đang dùng.
6. Cấu hình encoder và decoder tương thích ở cả client lẫn server.
7. Dùng metadata extractor để ánh xạ entry Composite Metadata thành header có kiểu.
8. Phân biệt MIME type của metadata envelope với MIME type của từng entry.
9. Kiểm thử thứ tự codec và encode/decode thực tế qua transport.
10. Giới hạn dữ liệu, validate sau decode và không tin metadata do peer gửi.

Spring lựa chọn codec dựa trên kiểu Java và MIME type mà payload yêu cầu. `RSocketStrategies` lưu các codec theo thứ tự, vì vậy codec phù hợp đứng trước có thể được chọn trước codec tổng quát ở sau. Khi đăng ký encoder, decoder và metadata extractor có chủ đích, client `RSocketRequester` và server handler sẽ chuyển đổi data/metadata nhất quán, dễ kiểm thử và ít gặp lỗi do codec cạnh tranh.
