# Kiểm thử metadata, codec, dữ liệu sai và tương thích hợp đồng

RSocket truyền payload cùng metadata qua các interaction như request-response, fire-and-forget, request-stream và request-channel. Một handler có thể chạy đúng với DTO đơn giản nhưng vẫn gặp lỗi khi client gửi MIME type khác, metadata thiếu entry, JSON sai cấu trúc hoặc schema đã tiến hóa giữa hai phiên bản service. Vì vậy, kiểm thử RSocket cần bao phủ cả nội dung data, metadata, codec và hợp đồng giữa producer với consumer.

Metadata quyết định cách định tuyến và mang context của request; codec quyết định cách chuyển đổi bytes thành object; validation quyết định dữ liệu đã decode có hợp lệ với nghiệp vụ hay không; contract tests xác minh hai phía vẫn hiểu cùng một cấu trúc qua các lần phát hành. Các lớp này liên quan nhưng không thay thế nhau: JSON decode thành công không có nghĩa dữ liệu hợp lệ, và metadata được giải mã không có nghĩa người gửi có quyền sử dụng giá trị đó.

Bài học này hướng dẫn xây dựng test cho metadata routing và custom metadata, JSON/CBOR codec, payload sai hoặc thiếu trường, MIME type không tương thích, cùng chiến lược kiểm thử tương thích hợp đồng khi client và server được triển khai độc lập.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt data payload, routing metadata và custom metadata.
- Kiểm thử metadata MIME type, composite metadata và route variables.
- Xác minh custom metadata được giải mã thành header ở server.
- Kiểm thử JSON/CBOR codec ở cấp serialization và qua transport.
- Phân biệt lỗi decode với lỗi validation nghiệp vụ.
- Kiểm thử payload sai định dạng, thiếu trường, sai kiểu và MIME type không hỗ trợ.
- Xác minh lỗi được truyền về đúng interaction mà không làm rò dữ liệu nhạy cảm.
- Thiết kế schema evolution và compatibility matrix cho client/server khác version.
- Dùng StepVerifier và integration tests để kiểm tra contract thực tế.

## 1. Các lớp cần kiểm thử

Một RSocket message có thể được nhìn theo bốn lớp:

| Lớp | Nội dung | Câu hỏi kiểm thử |
|---|---|---|
| Transport/protocol | TCP hoặc WebSocket, frame và interaction | Connection và interaction có được thiết lập đúng không? |
| Metadata | Route, MIME type, authentication hoặc custom context | Server có nhận đúng metadata và route không? |
| Data codec | JSON, CBOR hoặc biểu diễn bytes khác | Hai phía có encode/decode cùng một contract không? |
| Application contract | DTO, required fields và business rules | Dữ liệu đã decode có hợp lệ và tương thích không? |

Không nên chỉ viết unit test cho service rồi kết luận RSocket contract đã đúng. Unit test không kiểm tra metadata framing, MIME type negotiation hoặc codec được sử dụng ở hai đầu transport.

Một test pyramid thực tế:

1. Unit test cho mapper, validator và business rules.
2. Codec test cho encode/decode của DTO.
3. Metadata test cho route, MIME type và extractor.
4. RSocket integration test qua TCP hoặc WebSocket.
5. Contract compatibility test giữa các phiên bản producer/consumer.

~~~mermaid
flowchart TD
    A["Business rules / validation"] --> B["Codec tests: JSON / CBOR"]
    B --> C["Metadata tests: route / custom MIME"]
    C --> D["RSocket integration: real transport"]
    D --> E["Cross-version contract tests"]
~~~

## 2. Kiểm thử routing metadata

Spring RSocket dùng routing metadata để ánh xạ request tới @MessageMapping. Route là một metadata entry có MIME type chuẩn:

~~~text
message/x.rsocket.routing.v0
~~~

Khi client gọi:

~~~java
requester.route("devices.lookup")
        .data(new DeviceQuery("sensor-17"))
        .retrieveMono(DeviceView.class);
~~~

Spring requester tạo routing metadata cho route devices.lookup. Test cần xác minh route đúng được gọi, route sai không vô tình dispatch sang handler khác và route variables được giải mã chính xác.

### 2.1. Kiểm thử route và route variable

Ví dụ handler:

~~~java
@Controller
public class DeviceController {

    private final DeviceService deviceService;

    public DeviceController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @MessageMapping("tenants.{tenantId}.devices.lookup")
    public Mono<DeviceView> lookup(
            @DestinationVariable("tenantId") String tenantId,
            @Payload DeviceQuery query) {

        return deviceService.find(tenantId, query.deviceId());
    }
}
~~~

Client:

~~~java
Mono<DeviceView> response = requester
        .route("tenants.{tenantId}.devices.lookup", "tenant-42")
        .data(new DeviceQuery("sensor-17"))
        .retrieveMono(DeviceView.class);
~~~

Test nên xác minh:

- tenantId nhận đúng giá trị đã truyền vào route.
- Handler tương ứng được gọi đúng một lần.
- Route không khớp trả lỗi routing theo contract.
- Giá trị route không hợp lệ không làm request được dispatch sang route khác.
- Route variables không được xem là bằng chứng authorization; quyền truy cập tenant vẫn phải được kiểm tra riêng.

### 2.2. Route không phải business payload

Không đưa toàn bộ command vào route string. Route mô tả loại interaction hoặc đích dispatch; data payload mang nội dung nghiệp vụ. Giữ ranh giới này giúp contract ổn định và tránh tạo route động với quá nhiều biến thể.

## 3. Kiểm thử custom metadata

Ứng dụng có thể mang metadata riêng như tenant context, client capability hoặc correlation data. Hãy dùng MIME type riêng, ổn định và có version:

~~~java
static final MimeType TENANT_MIME_TYPE =
        MimeType.valueOf("message/vnd.acme.tenant.v1");
~~~

Khi kết hợp routing metadata với custom metadata, metadata section thường dùng composite metadata:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

Composite metadata chứa nhiều entry, mỗi entry có MIME type riêng. Đây là định dạng phù hợp khi một request có route cùng một hoặc nhiều custom metadata entry.

### 3.1. Cấu hình extractor ở server

RSocketStrategies có thể đăng ký cách giải mã custom metadata thành header:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
        .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                        TENANT_MIME_TYPE,
                        String.class,
                        "tenantId"))
        .build();
~~~

Handler nhận giá trị đã giải mã:

~~~java
@MessageMapping("devices.lookup")
public Mono<DeviceView> lookup(
        @Header("tenantId") String tenantId,
        @Payload DeviceQuery query) {

    return deviceService.find(tenantId, query.deviceId());
}
~~~

Tên header tenantId phải trùng với tên đã đăng ký trong metadata extractor. MIME type và kiểu Java cũng phải khớp với encoder phía client.

### 3.2. Gửi custom metadata từ client

~~~java
Mono<DeviceView> response = requester
        .route("devices.lookup")
        .metadata("tenant-42", TENANT_MIME_TYPE)
        .data(new DeviceQuery("sensor-17"))
        .retrieveMono(DeviceView.class);
~~~

Client và server cần dùng metadata MIME type tương thích. Nếu client gửi metadata theo MIME type tùy chỉnh nhưng server không đăng ký extractor, giá trị có thể không xuất hiện dưới dạng header trong handler. Test phải xác minh hành vi mong muốn khi entry bị thiếu hoặc không được hỗ trợ.

### 3.3. Ma trận kiểm thử metadata

| Trường hợp | Kết quả mong đợi |
|---|---|
| Route chuẩn và custom metadata hợp lệ | Handler nhận đúng route, header và payload |
| Metadata entry bị thiếu | Handler từ chối nếu entry bắt buộc |
| MIME type custom sai | Không giải mã thành header mong đợi |
| Metadata có kiểu bytes thay vì String | Decoder/Extractor xử lý theo contract hoặc phát lỗi |
| Có nhiều entry trong composite metadata | Mỗi entry được giải mã theo MIME type tương ứng |
| Có entry không được ứng dụng biết | Bỏ qua hoặc từ chối theo chính sách đã công bố |
| Route variable sai định dạng | Request bị từ chối hoặc validation thất bại |
| Tenant hợp lệ về cú pháp nhưng không được phép | Authorization từ chối |

Không giả định metadata không biết luôn phải làm connection thất bại. Ứng dụng nên chọn chính sách rõ: bỏ qua entry mở rộng không quan trọng để hỗ trợ tương thích, hoặc từ chối entry bắt buộc/không an toàn. Test phải cố định chính sách đó.

## 4. Kiểm thử data codec

Data MIME type cho biết cách diễn giải data section của payload trên connection. Spring RSocket có thể dùng codec từ RSocketStrategies để chuyển DTO thành JSON, CBOR hoặc kiểu dữ liệu khác.

JSON MIME type thường dùng:

~~~text
application/json
~~~

CBOR MIME type:

~~~text
application/cbor
~~~

Hai phía phải thống nhất data MIME type và có encoder/decoder tương thích. Nếu server chỉ đăng ký JSON nhưng client gửi CBOR, request có thể thất bại trước khi handler nhận được DTO.

### 4.1. Cấu hình JSON codec

Ví dụ cấu hình strategy với Jackson JSON:

~~~java
RSocketStrategies jsonStrategies =
        RSocketStrategies.builder()
                .encoders(encoders ->
                        encoders.add(new JacksonJsonEncoder()))
                .decoders(decoders ->
                        decoders.add(new JacksonJsonDecoder()))
                .build();
~~~

Ví dụ này dùng Spring Framework 7 với Jackson 3. Với Spring Framework 6/Jackson 2, dùng Jackson2JsonEncoder và Jackson2JsonDecoder tương ứng. Từ Spring Framework 7, các codec Jackson2 đã deprecated để chuyển sang codec Jackson 3; không trộn encoder Jackson 2 với decoder Jackson 3 trong cùng contract.

Dùng cùng strategy cho requester và RSocket server trong integration test để bảo đảm hai phía thống nhất:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(jsonStrategies)
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("localhost", serverPort);
~~~

Ví dụ dùng builder minh họa phía client; server cũng cần cấu hình RSocketMessageHandler hoặc Spring Boot RSocketStrategies bean tương ứng. Trong ứng dụng thực tế, có thể dùng auto-configuration của Spring Boot để chia sẻ codec strategy giữa messaging handler và requester builder.

### 4.2. Cấu hình CBOR codec

Với Spring Framework 7, có thể đăng ký Jackson CBOR codec:

~~~java
RSocketStrategies cborStrategies =
        RSocketStrategies.builder()
                .encoders(encoders ->
                        encoders.add(new JacksonCborEncoder()))
                .decoders(decoders ->
                        decoders.add(new JacksonCborDecoder()))
                .build();

RSocketRequester cborRequester = RSocketRequester.builder()
        .rsocketStrategies(cborStrategies)
        .dataMimeType(MimeTypeUtils.APPLICATION_CBOR)
        .tcp("localhost", serverPort);
~~~

Với Spring Framework 6/Jackson 2, các lớp tương ứng là Jackson2CborEncoder và Jackson2CborDecoder. Cả client và server phải có codec cho MIME type đã chọn; chỉ đổi dataMimeType không tự cài đặt decoder ở peer.

### 4.3. Kiểm thử round-trip DTO

DTO mẫu:

~~~java
public record DeviceQuery(
        String deviceId,
        Instant observedAfter) {
}

public record DeviceView(
        String deviceId,
        String state,
        Instant updatedAt) {
}
~~~

Kiểm thử request-response:

~~~java
StepVerifier.create(
        requester.route("devices.lookup")
                .data(new DeviceQuery(
                        "sensor-17",
                        Instant.parse("2026-01-01T00:00:00Z")))
                .retrieveMono(DeviceView.class))
        .assertNext(view -> {
            assertThat(view.deviceId()).isEqualTo("sensor-17");
            assertThat(view.state()).isEqualTo("ONLINE");
            assertThat(view.updatedAt()).isNotNull();
        })
        .verifyComplete();
~~~

Test này kiểm tra cả encode ở client, transport, decode ở server, xử lý handler, encode response và decode ở client. Nếu chỉ gọi ObjectMapper.writeValueAsBytes rồi đọc lại, test đó mới xác minh Jackson mapping; nó chưa xác minh RSocket dùng đúng MIME type và codec.

### 4.4. JSON và CBOR phải có contract tương đương

Nếu service hỗ trợ cả JSON và CBOR, cùng một DTO cần cho ra cùng ý nghĩa nghiệp vụ:

| Nội dung | JSON | CBOR |
|---|---|---|
| Device ID | String | Text string |
| Timestamp | ISO-8601 hoặc cấu hình Jackson thống nhất | Cách biểu diễn theo CBOR codec đã chọn |
| Nullability | Theo contract DTO | Theo contract DTO |
| Unknown field | Theo chính sách decoder | Theo chính sách decoder |
| Enum | Tên hoặc biểu diễn được cấu hình | Biểu diễn được cấu hình |

Không giả định hai codec luôn dùng cùng representation mặc định. Đặc biệt với timestamp, decimal, enum và binary field, hãy định nghĩa rõ cách biểu diễn rồi kiểm thử cả hai.

## 5. Kiểm thử codec ở cấp đơn vị

Unit test codec hữu ích để phát hiện thay đổi cấu hình Jackson trước khi chạy transport test. Ví dụ:

~~~java
@Test
void serializesDeviceQueryWithStableFieldNames()
        throws Exception {

    JsonMapper mapper = JsonMapper.builder()
            .findAndAddModules()
            .build();

    DeviceQuery query = new DeviceQuery(
            "sensor-17",
            Instant.parse("2026-01-01T00:00:00Z"));

    String json = mapper.writeValueAsString(query);
    DeviceQuery decoded = mapper.readValue(json, DeviceQuery.class);

    assertThat(json).contains("\"deviceId\":\"sensor-17\"");
    assertThat(decoded).isEqualTo(query);
}
~~~

Ví dụ dùng JsonMapper của Jackson 3; findAndAddModules đăng ký các module có trên classpath, bao gồm module Java Time nếu dependency tương ứng có mặt. Với Spring Framework 6/Jackson 2, dùng ObjectMapper và findAndRegisterModules. Nếu ứng dụng dùng mapper được Spring Boot cấu hình, hãy inject mapper đó vào test thay vì tạo mapper mới với cấu hình khác.

Các điểm nên kiểm tra:

- Field name không vô tình đổi do rename property.
- Timestamp có timezone và precision nhất quán.
- Decimal không bị đổi độ chính xác.
- Enum có biểu diễn ổn định.
- Null và absent field có semantics được định nghĩa.
- Unknown field tuân theo chính sách strict hoặc tolerant.
- Binary data được mã hóa theo định dạng đã thống nhất.

## 6. Kiểm thử dữ liệu sai và validation

Có ít nhất ba nhóm lỗi khác nhau:

1. **Decode error**: bytes không phải JSON/CBOR hợp lệ hoặc MIME type không được hỗ trợ.
2. **Binding/validation error**: dữ liệu decode được nhưng thiếu field, sai kiểu hoặc vi phạm constraint.
3. **Business error**: dữ liệu hợp lệ về cấu trúc nhưng không thỏa quy tắc nghiệp vụ.

Không gộp cả ba thành một lỗi BAD_REQUEST không có thông tin. Cần ánh xạ lỗi về interaction theo contract và tránh đưa payload nhạy cảm vào error message.

### 6.1. DTO có constraint

~~~java
public record DeviceCommand(
        @NotBlank String deviceId,
        @NotNull CommandType command,
        @Positive long sequence) {
}
~~~

Validation nên được thực hiện ở ranh giới application trước khi gọi service. Ví dụ dùng Jakarta Validator:

~~~java
public Mono<CommandReceipt> execute(DeviceCommand command) {
    return Mono.defer(() -> {
        Set<ConstraintViolation<DeviceCommand>> violations =
                validator.validate(command);

        if (!violations.isEmpty()) {
            return Mono.error(
                    new ConstraintViolationException(violations));
        }

        return commandService.execute(command);
    });
}
~~~

Đặt logic validate trong pipeline để lỗi đồng bộ cũng được chuyển thành tín hiệu error. Với controller có method validation tự động, vẫn cần test cấu hình thực tế để xác minh validation được kích hoạt cho RSocket handler.

### 6.2. Payload JSON sai định dạng

Có thể gửi chuỗi sai cú pháp với MIME type JSON trong integration test:

~~~java
RSocketStrategies rawStrategies = RSocketStrategies.builder()
        .encoder(new ByteBufferEncoder())
        .build();

RSocketRequester rawJsonRequester = RSocketRequester.builder()
        .rsocketStrategies(rawStrategies)
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("localhost", serverPort);

ByteBuffer malformedJson =
        StandardCharsets.UTF_8.encode("{not-json");

StepVerifier.create(
        rawJsonRequester.route("devices.lookup")
                .data(malformedJson)
                .retrieveMono(DeviceView.class))
        .expectError()
        .verify();
~~~

Data MIME type được khai báo ở cấp connection trong SETUP, không phải truyền lại cho từng request. Ví dụ trên mở connection có data MIME type application/json rồi dùng ByteBufferEncoder để gửi nguyên bytes sai cú pháp. Nếu cần kiểm tra protocol payload ở mức thấp hơn, có thể dùng RSocket client và Payload fixture trực tiếp. Mục tiêu là kiểm tra decoder phía server, không phải chỉ kiểm tra Jackson client.

### 6.3. Kiểm thử thiếu trường và sai kiểu

Ví dụ các payload:

~~~json
{"deviceId":"sensor-17"}
~~~

~~~json
{"deviceId":42,"command":"RESTART","sequence":"first"}
~~~

Trường hợp đầu thiếu command và sequence; trường hợp thứ hai sai kiểu của deviceId và sequence. Kết quả phụ thuộc DTO, Jackson configuration và validation policy. Hãy định nghĩa rõ field nào bắt buộc, field nào có default và test đúng hành vi đó.

### 6.4. MIME type không tương thích

Các trường hợp cần kiểm tra:

- Client gửi application/cbor, server chỉ có JSON decoder.
- Client gửi application/json nhưng data bytes là CBOR.
- Client và server cấu hình metadata MIME type khác nhau.
- Custom metadata entry có MIME type đúng nhưng payload sai representation.
- Data MIME type đúng nhưng DTO schema không tương thích.

Không giả định mọi mismatch đều làm connection đóng. Lỗi có thể được phát hiện ở lúc decode một interaction và trả về như interaction error; lỗi setup hoặc lỗi protocol có thể có phạm vi ảnh hưởng lớn hơn. Test phải xác minh phạm vi lỗi thực tế của cấu hình server.

## 7. Kiểm thử metadata sai và metadata bắt buộc

Với custom metadata bắt buộc như tenant context, không chỉ kiểm tra extractor. Handler hoặc security layer phải từ chối khi giá trị thiếu, rỗng hoặc không hợp lệ:

~~~java
public Mono<DeviceView> lookup(
        @Header(name = "tenantId", required = false) String tenantId,
        @Payload DeviceQuery query) {

    if (tenantId == null || tenantId.isBlank()) {
        return Mono.error(
                new InvalidMetadataException("tenantId is required"));
    }

    return deviceService.find(tenantId, query.deviceId());
}
~~~

Test cần bao phủ:

- Metadata entry không có.
- Metadata value rỗng.
- Metadata sai kiểu hoặc sai encoding.
- Metadata MIME type không khớp.
- Nhiều entry trùng cùng một logical key.
- Tenant hợp lệ nhưng không được Principal hiện tại truy cập.

Không dùng metadata do client gửi làm bằng chứng xác thực. Tenant, user ID hoặc role trong metadata cần được đối chiếu với Authentication đã xác minh.

## 8. Kiểm thử hợp đồng giữa các phiên bản

RSocket protocol xác định cách gửi frame, interaction và metadata; nó không tự định nghĩa schema nghiệp vụ của DTO. Hợp đồng data thường được quản lý ở tầng ứng dụng bằng JSON/CBOR schema, Avro, Protobuf hoặc versioned DTO.

Một contract test cần trả lời:

- Client version N có gọi được server version N+1 không?
- Server version N có đọc được event do client version N+1 phát không?
- Field mới có làm consumer cũ decode thất bại không?
- Enum mới có làm consumer cũ throw exception không?
- MIME type hoặc metadata key có thay đổi không?
- Default, nullability và timestamp có giữ semantics không?

### 8.1. Thay đổi tương thích và breaking change

| Thay đổi | Tác động thường gặp | Khuyến nghị |
|---|---|---|
| Thêm field optional | Thường tương thích nếu consumer cũ bỏ qua unknown field | Test consumer cũ với payload mới |
| Thêm field required | Có thể làm producer cũ không cung cấp đủ dữ liệu | Version contract hoặc có default |
| Xóa/đổi tên field | Consumer cũ có thể không tìm thấy dữ liệu | Giữ alias hoặc phát hành version mới |
| Đổi kiểu String thành Number | Có thể làm decode thất bại | Xem là breaking change |
| Thay đổi enum | Consumer cũ có thể không nhận enum mới | Có fallback/unknown handling hoặc version |
| Đổi semantics của null | Có thể thay đổi nghiệp vụ dù decode thành công | Định nghĩa absent/null/default riêng |
| Đổi timestamp/timezone | Có thể thay đổi thời điểm nghiệp vụ | Chuẩn hóa ISO-8601 UTC và precision |
| Đổi data MIME type | Có thể làm codec phía kia không xử lý được | Thỏa thuận codec trước khi rollout |
| Đổi custom metadata MIME type | Extractor cũ không nhận được entry | Version MIME type và rollout có kiểm soát |

Thêm field không tự động tương thích trong mọi cấu hình. Nếu consumer bật strict unknown-property validation, field mới có thể làm consumer cũ lỗi. Ngược lại, bỏ qua unknown field giúp forward compatibility nhưng có thể che một lỗi đánh máy trong contract. Chọn strictness theo loại message và test chính sách.

### 8.2. Chính sách unknown fields

Với event có nhiều consumer và cần rollout độc lập, consumer thường nên bỏ qua field chưa biết nếu schema cho phép. Với command nội bộ có yêu cầu chặt, strict decoding có thể giúp phát hiện client gửi nhầm field.

Jackson có thể cấu hình FAIL_ON_UNKNOWN_PROPERTIES hoặc annotation như JsonIgnoreProperties(ignoreUnknown = true). Không cấu hình hai nơi mâu thuẫn. Test phải dùng đúng ObjectMapper mà RSocketStrategies đang sử dụng.

### 8.3. Enum evolution

Nếu server phát enum mới, consumer cũ có thể không deserialize được. Các lựa chọn:

- Dùng string field có fallback UNKNOWN.
- Cấu hình enum default cho giá trị không biết nếu codec hỗ trợ.
- Thêm enum mới theo quy trình expand-contract: triển khai consumer chấp nhận trước, sau đó mới phát producer.
- Version contract nếu semantics thay đổi không thể tương thích.

Không ánh xạ một enum mới sang giá trị cũ có semantics khác chỉ để tránh lỗi decode.

## 9. Compatibility matrix và expand-contract rollout

Với client và server triển khai độc lập, kiểm tra ít nhất ma trận phiên bản:

| Client / Producer | Server / Consumer cũ | Server / Consumer mới |
|---|---|---|
| Client cũ | Baseline hiện tại | Phải tiếp tục hỗ trợ trong giai đoạn rollout |
| Client mới | Chỉ hỗ trợ nếu thay đổi backward-compatible | Target version |

Đối với event broker, kiểm tra tương tự giữa producer cũ/mới và consumer cũ/mới. Không chỉ test cặp version mới nhất.

Quy trình expand-contract:

1. Mở rộng consumer để chấp nhận field hoặc enum mới nhưng chưa yêu cầu chúng.
2. Triển khai consumer mới trên toàn bộ fleet.
3. Bắt đầu phát field hoặc enum mới từ producer.
4. Theo dõi lỗi decode và contract metrics.
5. Sau thời gian tương thích, mới bỏ field cũ nếu có version boundary rõ.

Nếu đổi data MIME type hoặc metadata MIME type ở cấp connection, cần rollout theo khả năng hỗ trợ của client/server. Không giả định một connection đã mở có thể tự đổi MIME type giữa chừng.

## 10. Consumer-driven contract tests

Consumer-driven contract test ghi lại những gì consumer thực sự cần từ provider. Với RSocket, contract nên bao gồm:

- Route name và route variables.
- Data MIME type và metadata MIME type.
- Required metadata entry và MIME type của entry.
- Request DTO và response DTO.
- Error semantics cho invalid data và route không tồn tại.
- Các field bắt buộc, nullable và default.
- Schema version hoặc version negotiation nếu có.

Ví dụ contract mô tả route:

~~~yaml
interaction:
  route: devices.lookup
  interactionType: request-response
  dataMimeType: application/json
  requiredMetadata:
    - mimeType: message/vnd.acme.tenant.v1
      valueType: string
  request:
    required:
      - deviceId
    properties:
      deviceId: string
  response:
    required:
      - deviceId
      - state
    properties:
      deviceId: string
      state: string
~~~

Đây là mô hình contract minh họa. Trong dự án, hãy lưu contract ở định dạng schema/tool đã được nhóm thống nhất và đưa vào CI để so sánh thay đổi.

Contract tests nên được chạy với:

- Payload mẫu được tạo từ schema hiện hành.
- Payload lưu từ version trước.
- Payload có field mới không biết.
- Payload thiếu required field.
- Metadata entry đúng và sai MIME type.
- Client contract cũ gọi server mới.
- Client contract mới gọi server cũ nếu chính sách rollout yêu cầu.

## 11. Integration test qua RSocket transport

Unit test codec không xác minh được metadata framing và route dispatch. Integration test nên khởi động một RSocket server thật trên TCP hoặc WebSocket với cùng RSocketStrategies như production.

Ví dụ cấu hình requester trong test:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(testStrategies)
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("localhost", serverPort);
~~~

Trong test Spring Boot, serverPort nên lấy từ cổng ngẫu nhiên do test server cấp. Tránh hardcode port để nhiều test có thể chạy song song.

Một fixture server có thể dùng RSocketServer cùng RSocketMessageHandler.responder() để kiểm tra routing và handler thật. Đảm bảo controller được đăng ký với handler và strategy được cấu hình trước khi bind transport. Luôn dispose requester/connection và server trong @AfterEach hoặc try/finally để tránh test leak.

### 11.1. Kiểm thử metadata và data cùng lúc

~~~java
StepVerifier.create(
        requester.route("devices.lookup")
                .metadata("tenant-42", TENANT_MIME_TYPE)
                .data(new DeviceQuery("sensor-17"))
                .retrieveMono(DeviceView.class))
        .assertNext(view ->
                assertThat(view.deviceId()).isEqualTo("sensor-17"))
        .verifyComplete();
~~~

Test này xác minh metadata và DTO đi qua cùng một interaction. Để chứng minh custom header được extractor giải mã, handler test nên trả về hoặc ghi nhận tenant đã nhận, sau đó assertion kiểm tra đúng giá trị.

### 11.2. Kiểm thử sai payload qua transport

Test này dùng rawJsonRequester và malformedJson đã tạo ở phần 6.2:

~~~java
StepVerifier.create(
        rawJsonRequester.route("devices.lookup")
                .data(malformedJson)
                .retrieveMono(DeviceView.class))
        .expectError()
        .verify();
~~~

Nếu fixture không thể gửi ByteBuffer thô theo strategy hiện tại, dùng RSocket client cấp thấp hoặc Payload fixture để gửi raw bytes. Không thay thế test decoder phía server bằng một unit test chỉ xác minh client từ chối dữ liệu.

## 12. StepVerifier cho các trường hợp bất đồng bộ

StepVerifier giúp kiểm tra giá trị, thứ tự signal, lỗi và cancellation:

~~~java
StepVerifier.create(service.lookup(validQuery))
        .assertNext(result ->
                assertThat(result.state()).isEqualTo("ONLINE"))
        .verifyComplete();
~~~

Kiểm thử lỗi validation:

~~~java
StepVerifier.create(service.execute(invalidCommand))
        .expectError(ConstraintViolationException.class)
        .verify();
~~~

Kiểm thử thứ tự stream:

~~~java
StepVerifier.create(service.events("sensor-17"))
        .expectNext(firstEvent)
        .expectNext(secondEvent)
        .thenCancel()
        .verify();
~~~

Với timeout, retry hoặc backoff, dùng virtual time nếu publisher được tạo bên trong supplier của StepVerifier.withVirtualTime. Không dùng Thread.sleep trong reactive tests vì test sẽ chậm và dễ flaky.

## 13. Property-based và fuzz testing

Payload đến từ mạng có thể chứa dữ liệu bất thường mà các ví dụ thủ công không bao phủ. Có thể bổ sung property-based tests để sinh:

- Chuỗi Unicode, ký tự điều khiển và chuỗi rất dài.
- Số âm, số vượt giới hạn, số thập phân có precision cao.
- Timestamp thiếu timezone hoặc sai format.
- Field null, absent hoặc có kiểu không đúng.
- Enum value chưa biết.
- Metadata rỗng, trùng lặp hoặc bytes không hợp lệ.
- Payload sát giới hạn và vượt giới hạn.

Các property hữu ích:

1. Payload hợp lệ encode rồi decode vẫn giữ semantics.
2. Payload không hợp lệ bị từ chối mà không làm process crash.
3. Parser không đọc vượt giới hạn đã cấu hình.
4. Metadata không được phép không làm thay đổi tenant hoặc authorization context.
5. Log/error response không chứa secret hoặc toàn bộ raw payload.

Fuzz test nên chạy trong môi trường kiểm thử cô lập, có timeout và giới hạn tài nguyên để payload cực lớn không làm cạn bộ nhớ CI.

## 14. Bảo mật trong kiểm thử metadata và payload

Metadata có thể mang bearer token, session context hoặc tenant identifier. Payload có thể chứa dữ liệu cá nhân và thông tin nghiệp vụ. Test fixture cần dùng dữ liệu giả:

- Token giả và key test.
- Email, số điện thoại và ID tổng hợp.
- Không sao chép production payload vào repository.
- Không ghi nguyên bytes vào assertion message hoặc test log.
- Kiểm tra redaction ở cả error log và debug log.

Kiểm thử authorization riêng với metadata parsing. Một tenant ID decode thành công chỉ chứng minh bytes đã được giải mã; nó không chứng minh caller được phép truy cập tenant đó.

## 15. Các lỗi thường gặp

### Chỉ test DTO bằng ObjectMapper

Không kiểm tra RSocket MIME type, metadata framing hoặc route dispatch. Bổ sung integration test qua transport.

### Dùng cùng codec nhưng quên MIME type

Encoder có thể tạo JSON nhưng peer không biết phải dùng decoder nào. Kiểm tra data MIME type ở cả client và server.

### Dùng custom metadata mà không đăng ký extractor

Handler không nhận được header như mong đợi. Kiểm tra MIME type, extractor và tên header.

### Cho rằng composite metadata là tùy chọn khi có nhiều entry

Route và nhiều custom metadata cần một metadata format mà cả hai phía hiểu. Dùng composite metadata theo contract.

### Chỉ test dữ liệu hợp lệ

Malformed JSON, missing field, wrong type và enum mới thường xuất hiện sau rollout. Bổ sung negative và cross-version tests.

### Xem decode thành công là validation thành công

DTO có thể decode nhưng thiếu tenant, sequence âm hoặc command không hợp lệ. Chạy validation và test business constraints.

### Bỏ qua unknown field mà không có chính sách

Tolerant decoding giúp forward compatibility nhưng có thể che lỗi đánh máy. Chọn strictness theo loại contract và cố định bằng test.

### Test chỉ với client/server cùng version

Không phát hiện lỗi rollout độc lập. Chạy compatibility matrix cho version cũ và mới.

### Test server không giải phóng connection

Các test sau có thể fail ngẫu nhiên hoặc treo vì server/connection vẫn mở. Dispose tài nguyên trong cleanup hook.

## 16. Checklist kiểm thử

Trước khi phát hành thay đổi RSocket contract, hãy xác nhận:

1. Route và route variables được kiểm thử.
2. Routing metadata MIME type và composite metadata được kiểm thử.
3. Custom metadata có MIME type, extractor và tên header thống nhất.
4. Metadata bắt buộc bị từ chối khi thiếu hoặc sai.
5. JSON/CBOR encode-decode round-trip được kiểm thử.
6. Timestamp, decimal, enum, null và unknown fields có contract rõ.
7. Payload malformed, missing field và wrong type có negative tests.
8. MIME type mismatch và unsupported codec được kiểm thử.
9. Decode error, validation error và business error được phân biệt.
10. Lỗi được trả về đúng interaction và không làm rò payload nhạy cảm.
11. Client cũ/server mới và client mới/server cũ được kiểm thử theo rollout policy.
12. Schema evolution có compatibility matrix và consumer-driven tests.
13. Integration tests dùng transport thật và port ngẫu nhiên.
14. Test luôn dispose requester, connection và server.
15. Property-based/fuzz tests có giới hạn thời gian và tài nguyên.
16. Test fixture chỉ dùng dữ liệu giả, không chứa production secret.

## 17. Tổng kết

Kiểm thử RSocket contract cần đi qua metadata, codec, validation và compatibility. Metadata test xác minh route, MIME type, composite entry và custom header; codec test xác minh data được encode/decode đúng; negative test xác minh payload sai hoặc thiếu trường bị từ chối có kiểm soát; contract test xác minh client và server khác phiên bản vẫn giao tiếp theo chính sách rollout.

Hãy kết hợp unit tests cho validator/mapper, codec tests cho JSON/CBOR, metadata tests cho extractor và integration tests qua TCP hoặc WebSocket. Định nghĩa rõ unknown fields, enum evolution, nullability, timestamp, required fields và MIME types. Khi có contract rõ và test cho cả phiên bản cũ lẫn mới, nhóm có thể phát hành client/server độc lập mà giảm nguy cơ lỗi decode, sai routing hoặc thay đổi semantics ngoài dự kiến.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference — RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html#rsocket-requester)
- [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
- [RSocket Protocol — Metadata and MIME Types](https://rsocket.io/about/protocol/)
- [Jackson Databind Documentation](https://github.com/FasterXML/jackson-databind)
