# Cấu hình dataMimeType, metadataMimeType và RSocketStrategies

`RSocketRequester` giúp ứng dụng Spring gửi request qua RSocket bằng các kiểu Java và API reactive. Khi gọi `.data(...)`, framework cần biết cách chuyển object thành bytes; khi nhận response, framework cần biết cách giải mã bytes thành kiểu Java. Metadata cũng cần định dạng riêng để responder có thể đọc route, tenant, trace context hoặc thông tin xác thực.

Ba thành phần phối hợp với nhau:

- **`dataMimeType`** xác định định dạng mặc định của phần data trong payload, ví dụ JSON hoặc dữ liệu nhị phân.
- **`metadataMimeType`** xác định định dạng của metadata section. Nếu dùng Composite Metadata, section có thể chứa nhiều entry với MIME type riêng.
- **`RSocketStrategies`** tập hợp encoder, decoder và metadata extractor mà Spring dùng để chuyển đổi payload và trích xuất metadata.

Các giá trị này phải tương thích giữa client và server. Nếu client gửi JSON nhưng server chỉ có decoder CBOR, request có thể đến transport thành công nhưng thất bại khi giải mã. Nếu metadata section được gửi theo Composite Metadata mà phía nhận lại cấu hình một MIME type đơn, route hoặc metadata tùy chỉnh có thể không được đọc đúng.

## 1. Data và metadata là hai phần khác nhau

Một RSocket `Payload` có hai vùng logic: data và metadata. Data mang nội dung chính của thông điệp; metadata mang thông tin điều khiển hoặc ngữ cảnh bổ sung.

Ví dụ request xem trạng thái thiết bị:

| Thành phần | Ví dụ | Mục đích |
|---|---|---|
| Data | `DeviceQuery("device-42")` | Tham số nghiệp vụ của truy vấn |
| Routing metadata | `devices.status` | Chọn handler xử lý |
| Tenant metadata | `tenant-a` | Ngữ cảnh tenant đã xác thực |
| Trace metadata | `trace-9f2...` | Liên kết log và trace |

Data và metadata được mã hóa riêng. `dataMimeType` mô tả định dạng bytes của data; `metadataMimeType` mô tả định dạng bytes của metadata section. Không nên đưa mọi thông tin điều khiển vào DTO data chỉ vì chưa cấu hình metadata codec.

Ví dụ DTO data:

```java
import java.time.Instant;

public record DeviceQuery(String deviceId) {}

public record DeviceStatus(
    String deviceId,
    String state,
    Instant observedAt
) {}
```

`DeviceQuery` và `DeviceStatus` là contract nghiệp vụ. MIME type cho biết hai phía cần serialize/deserialize các kiểu này theo định dạng nào.

## 2. `dataMimeType` xác định định dạng của data

`dataMimeType` là MIME type mặc định cho phần data của payload trên connection. Một số lựa chọn thường gặp:

| MIME type | Nội dung phù hợp | Codec thường dùng |
|---|---|---|
| `application/json` | DTO JSON, record Java, object nghiệp vụ | Jackson JSON encoder/decoder |
| `application/cbor` | Dữ liệu CBOR nhỏ gọn | CBOR encoder/decoder tương ứng |
| `application/octet-stream` | Bytes hoặc dữ liệu nhị phân | Byte array/buffer codec |
| `text/plain` | Chuỗi văn bản đơn giản | String encoder/decoder |
| MIME type riêng | Protobuf hoặc định dạng ứng dụng | Codec tùy chỉnh tương ứng |

MIME type phải khớp với định dạng bytes thực tế. Không đặt `application/json` cho `byte[]` chứa Protobuf hoặc file nén. Ngược lại, không chọn `application/octet-stream` rồi mong Spring tự deserialize bytes thành record JSON nếu chưa có quy tắc chuyển đổi.

`dataMimeType` được khai báo trong quá trình thiết lập connection và dùng làm định dạng mặc định cho data trên connection đó. Nó không phải một tham số thay đổi tùy ý cho từng lần gọi `.data(...)`. Nếu một connection cần trao đổi nhiều loại dữ liệu, hãy dùng một định dạng envelope có discriminator rõ ràng, codec hỗ trợ các kiểu cần thiết hoặc thiết kế connection/contract riêng theo yêu cầu.

## 3. `metadataMimeType` xác định định dạng metadata section

Metadata section có thể được mã hóa theo một MIME type đơn hoặc theo Composite Metadata.

**Metadata MIME type đơn** nghĩa là toàn bộ metadata section được diễn giải theo một định dạng đã thống nhất. Cách này phù hợp khi ứng dụng chỉ cần một khối metadata duy nhất và không cần nhiều entry độc lập.

**Composite Metadata** cho phép một metadata section chứa nhiều entry. Mỗi entry có MIME type riêng, ví dụ routing, authentication hoặc metadata tùy chỉnh. MIME type của envelope là:

```text
message/x.rsocket.composite-metadata.v0
```

Một Composite Metadata section có thể chứa:

| Entry | MIME type của entry | Nội dung minh họa |
|---|---|---|
| Routing | `message/x.rsocket.routing.v0` | `devices.status` |
| Authentication | `message/x.rsocket.authentication.v0` | Credential theo định dạng chuẩn |
| Tenant | `application/vnd.example.tenant+json` | Tenant ID |
| Tracing | `application/vnd.example.trace+json` | Trace context |

Khi dùng `.route(...)` cùng nhiều `.metadata(...)`, Composite Metadata là lựa chọn thông dụng vì routing và metadata tùy chỉnh có thể cùng tồn tại trong một metadata section. Nếu cấu hình metadata MIME type đơn, không được giả định rằng có thể đồng thời gắn nhiều entry MIME type khác nhau.

## 4. Vai trò của `RSocketStrategies`

`RSocketStrategies` là tập hợp các thành phần Spring dùng để chuyển đổi dữ liệu RSocket. Thành phần quan trọng gồm:

- **Encoders:** chuyển object Java thành `DataBuffer`/bytes theo MIME type phù hợp.
- **Decoders:** chuyển bytes nhận được thành object Java.
- **Metadata extractor registry:** nhận diện metadata entry và ánh xạ chúng thành header hoặc giá trị để handler sử dụng.
- **Các thành phần hỗ trợ message conversion:** kết nối codec với mô hình Spring Messaging và reactive.

Khi dùng `RSocketRequester`, encoder được dùng cho object truyền qua `.data(...)` hoặc metadata object. Decoder được dùng cho response trong `retrieveMono(...)` và `retrieveFlux(...)`. Ở phía server, strategies được dùng để giải mã request payload trước khi gọi handler và mã hóa response khi trả về peer.

`RSocketStrategies` là cấu hình chuyển đổi ở tầng Spring, không phải một cơ chế thương lượng codec tự động giữa hai peer. Client và server phải cùng hỗ trợ MIME type và có codec tương ứng. Việc khai báo cùng một chuỗi MIME type không đủ nếu bytes thực tế hoặc cấu trúc DTO khác nhau.

## 5. Cấu hình RSocketRequester.Builder

Ví dụ cấu hình client dùng JSON cho data và Composite Metadata cho metadata:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

public class RSocketClientFactory {
    private static final MimeType DATA_MIME =
        MimeTypeUtils.APPLICATION_JSON;

    private static final MimeType METADATA_MIME =
        MimeType.valueOf("message/x.rsocket.composite-metadata.v0");

    private final RSocketStrategies strategies;

    public RSocketClientFactory(RSocketStrategies strategies) {
        this.strategies = strategies;
    }

    public Mono<RSocketRequester> connect(String host, int port) {
        return RSocketRequester.builder()
            .dataMimeType(DATA_MIME)
            .metadataMimeType(METADATA_MIME)
            .rsocketStrategies(strategies)
            .connectTcp(host, port);
    }
}
```

Ba cấu hình quan trọng được đặt trên builder trước khi kết nối:

1. `dataMimeType(...)` chọn định dạng data mặc định.
2. `metadataMimeType(...)` chọn định dạng metadata section.
3. `rsocketStrategies(...)` cung cấp codec và metadata extractor cho quá trình chuyển đổi.

`connectTcp(...)` trả về `Mono<RSocketRequester>`, do đó việc kết nối vẫn bất đồng bộ. Trong ứng dụng thật, connection nên được quản lý bởi một bean/lifecycle owner và tái sử dụng theo phạm vi phù hợp, không tạo connection mới cho mỗi request. Với WebSocket, dùng phương thức kết nối WebSocket và URI tương ứng; MIME type và strategies vẫn có vai trò tương tự.

## 6. Đăng ký codec cho JSON

Nếu ứng dụng dùng codec JSON mặc định của Spring Boot, có thể không cần tự tạo thêm encoder/decoder. Khi cần tùy chỉnh, ví dụ muốn đăng ký Jackson codec cụ thể, cấu hình `RSocketStrategies`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;

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

Ví dụ trên minh họa việc thêm codec JSON. Khi ứng dụng cần nhiều kiểu payload, phải bảo đảm các encoder/decoder khác vẫn có mặt, ví dụ `String`, `byte[]` hoặc codec đặc thù. Tránh vô tình thay thế toàn bộ codec mặc định chỉ để thêm một codec mới. Hãy kiểm tra `RSocketStrategies` cuối cùng mà ứng dụng sử dụng và thứ tự codec khi có nhiều encoder cùng hỗ trợ một kiểu.

Với Spring Boot, bean `RSocketStrategies` có thể được dùng bởi các thành phần RSocket được auto-configure theo cơ chế của phiên bản đang sử dụng. Nếu tự tạo `RSocketRequester` hoặc server factory, truyền strategies tương ứng một cách tường minh để client/server dùng đúng codec đã định.

## 7. Gửi và nhận DTO qua RSocketRequester

Khi codec JSON đã được cấu hình, client có thể gửi record Java trực tiếp:

```java
Mono<DeviceStatus> status = requester
    .route("devices.status")
    .data(new DeviceQuery("device-42"))
    .retrieveMono(DeviceStatus.class);
```

Spring chọn encoder phù hợp với `DeviceQuery` và `dataMimeType` của requester. Khi response đến, decoder chuyển bytes thành `DeviceStatus`. Handler server có thể nhận DTO tương ứng:

```java
@Controller
public class DeviceHandler {
    private final DeviceService service;

    public DeviceHandler(DeviceService service) {
        this.service = service;
    }

    @MessageMapping("devices.status")
    public Mono<DeviceStatus> status(@Payload DeviceQuery query) {
        return service.getStatus(query.deviceId());
    }
}
```

Client và server cần cùng hiểu schema của `DeviceQuery` và `DeviceStatus`. Codec chỉ giải quyết serialization; nó không tự bảo đảm hai phiên bản ứng dụng dùng cùng ý nghĩa trường, đơn vị đo hoặc quy tắc tương thích.

## 8. Gửi metadata tùy chỉnh với Composite Metadata

Định nghĩa MIME type và DTO metadata riêng:

```java
public record TenantMetadata(String tenantId) {}

public record TraceMetadata(String traceId) {}
```

```java
static final MimeType TENANT_MIME =
    MimeType.valueOf("application/vnd.example.tenant+json");

static final MimeType TRACE_MIME =
    MimeType.valueOf("application/vnd.example.trace+json");
```

Client có thể thêm nhiều metadata entry cho một request:

```java
Mono<DeviceStatus> status = requester
    .route("devices.status")
    .metadata(new TenantMetadata("tenant-a"), TENANT_MIME)
    .metadata(new TraceMetadata("trace-9f2"), TRACE_MIME)
    .data(new DeviceQuery("device-42"))
    .retrieveMono(DeviceStatus.class);
```

Vì có nhiều entry khác MIME type, connection cần dùng Composite Metadata cho metadata section. Các MIME type tùy chỉnh phải được cả hai phía thống nhất và codec phải giải mã được object tương ứng.

Metadata không phải bằng chứng xác thực. Server phải xác minh principal và kiểm tra tenant có thuộc quyền truy cập của principal hay không. Không tin `tenantId` do client gửi chỉ vì nó đã được decode thành công.

## 9. Cấu hình metadata extractor phía server

Ở server, metadata extractor ánh xạ entry trong Composite Metadata thành header để handler đọc. Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;

@Configuration
public class RSocketServerConfiguration {

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
            .encoders(encoders ->
                encoders.add(new Jackson2JsonEncoder()))
            .decoders(decoders ->
                decoders.add(new Jackson2JsonDecoder()))
            .metadataExtractorRegistry(registry -> {
                registry.metadataToExtract(
                    TENANT_MIME, TenantMetadata.class, "tenant");
                registry.metadataToExtract(
                    TRACE_MIME, TraceMetadata.class, "trace");
            })
            .build();
    }
}
```

Handler có thể nhận các header đã trích xuất:

```java
@MessageMapping("devices.status")
public Mono<DeviceStatus> status(
        @Payload DeviceQuery query,
        @Header("tenant") TenantMetadata tenant,
        @Header("trace") TraceMetadata trace) {

    return deviceService.getStatusForTenant(
        query.deviceId(), tenant.tenantId());
}
```

Các import và bean codec trong ví dụ là khung cấu hình. Trong dự án thật, tránh khai báo trùng `RSocketStrategies` nếu Spring Boot đã cung cấp một bean tùy chỉnh tương đương. Đảm bảo codec JSON được đăng ký cho cả data DTO và metadata DTO; nếu metadata được mã hóa theo định dạng khác, cần codec tương ứng cho MIME type đó.

## 10. Setup metadata và metadata của từng request

`RSocketRequester.Builder` còn hỗ trợ setup payload/metadata khi thiết lập connection:

```java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(DATA_MIME)
    .metadataMimeType(METADATA_MIME)
    .setupRoute("client.connect")
    .setupData(new ClientInfo("dashboard", "2.1"))
    .setupMetadata(new ClientAuth(accessToken), AUTH_MIME)
    .rsocketStrategies(strategies)
    .connectTcp(host, port)
    .block();
```

Đoạn mã minh họa ở ranh giới khởi tạo đồng bộ; trong pipeline reactive nên giữ `Mono<RSocketRequester>` thay vì gọi `block()`. Setup metadata phù hợp với thông tin gắn với phiên như client identity hoặc credential ban đầu. Metadata của `.route(...).metadata(...)` phù hợp với ngữ cảnh riêng của từng request như tenant, trace ID hoặc idempotency key.

`dataMimeType` và `metadataMimeType` là định dạng mặc định được khai báo cho connection trong quá trình setup; chúng không tự thay đổi theo từng route. Với Composite Metadata, từng entry có MIME type riêng trong cùng metadata section. Đừng nhầm MIME type của envelope với MIME type của từng entry.

## 11. Khi nào cần codec tùy chỉnh?

Codec tùy chỉnh cần thiết khi định dạng trao đổi không được codec mặc định hỗ trợ hoặc cần tối ưu đặc biệt.

| Nhu cầu | Cách cấu hình |
|---|---|
| JSON DTO | Jackson encoder/decoder tương ứng `application/json` |
| CBOR | CBOR encoder/decoder và `application/cbor` |
| Protobuf | Codec cho generated message và MIME type đã thống nhất |
| Binary `byte[]` | Byte array codec và `application/octet-stream` |
| Metadata domain riêng | Metadata DTO, MIME type riêng và metadata extractor |
| Nhiều metadata entry | Composite Metadata cùng codec cho từng entry |

Một codec cần khai báo MIME type hỗ trợ và kiểu Java có thể encode/decode. Khi có nhiều codec, thứ tự và độ cụ thể của loại hỗ trợ có thể ảnh hưởng codec được chọn. Không đăng ký hai codec cùng ưu tiên cho cùng kiểu và MIME type nếu không có quy tắc rõ ràng.

Đối với binary payload lớn, tránh deserialize toàn bộ thành một object nếu có thể xử lý theo chunk/stream. Codec không thay thế giới hạn kích thước payload, metadata hoặc dữ liệu sau giải nén.

## 12. Tương thích MIME type giữa client và server

MIME type trong SETUP tạo ra contract định dạng cho connection. Client và server cần thống nhất:

1. Data MIME type nào được dùng cho payload.
2. Metadata section là MIME type đơn hay Composite Metadata.
3. Nếu composite, từng entry có MIME type và schema nào.
4. Codec nào encode và decode từng kiểu Java.
5. Phiên bản schema và cách xử lý field mới/không biết.
6. Kiểu lỗi trả về khi MIME type hoặc dữ liệu không được hỗ trợ.

Không nên xem khai báo MIME type là một giao thức content negotiation tự động giống HTTP Accept. Hai peer cần cấu hình tương thích; một bên không tự chuyển JSON sang CBOR chỉ vì decoder JSON không có.

Một số lỗi thường gặp:

- Client đặt `application/json`, server chỉ có CBOR decoder.
- Metadata được gửi dạng Composite nhưng server cấu hình MIME type đơn.
- Client gửi metadata tùy chỉnh nhưng server chưa đăng ký extractor/decoder.
- MIME type chuỗi đúng nhưng DTO hai bên có schema hoặc kiểu trường không tương thích.
- Codec tùy chỉnh ghi đè hoặc làm mất codec mặc định cần cho `String`/`byte[]`.
- Dùng metadata đơn trong khi route và nhiều metadata entry cần Composite Metadata.
- Đổi MIME type trên một phía mà không triển khai đồng bộ phía còn lại.

Khi thay đổi định dạng, hãy triển khai theo chiến lược tương thích: hỗ trợ song song phiên bản cũ/mới trong khoảng chuyển đổi, version hóa MIME type riêng khi schema thực sự không tương thích và chỉ loại bỏ định dạng cũ sau khi các peer đã được nâng cấp.

## 13. Bảo mật và giới hạn tài nguyên

MIME type và codec không phải cơ chế bảo mật. Metadata có thể chứa tenant, trace hoặc credential; data có thể chứa thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm.

- Dùng TLS cho TCP/WebSocket khi dữ liệu đi qua mạng không đáng tin cậy.
- Xác thực peer và ủy quyền từng route; không tin role hoặc tenant chỉ vì có trong metadata.
- Không ghi token, password hoặc payload nhạy cảm vào log.
- Giới hạn kích thước data và metadata trước khi giải mã sâu nếu transport/decoder hỗ trợ.
- Giới hạn số entry Composite Metadata, độ dài route và độ dài từng trường.
- Kiểm soát độ sâu cấu trúc JSON và số phần tử collection để tránh payload gây tốn CPU/bộ nhớ.
- Chỉ đăng ký decoder cho MIME type thực sự được hỗ trợ.

Nếu dùng JSON polymorphic typing, cấu hình danh sách kiểu được phép và tránh bật cơ chế deserialize tùy ý từ tên class do peer gửi. Dữ liệu trên wire luôn là dữ liệu không tin cậy, kể cả khi MIME type đúng.

## 14. Kiểm thử và chẩn đoán

Nên kiểm thử cả hai phía của connection:

| Kiểm thử | Điều cần xác minh |
|---|---|
| Data JSON | DTO encode/decode đúng ở client và server |
| Binary payload | `byte[]` được giữ nguyên, không bị serialize thành JSON ngoài ý muốn |
| Composite Metadata | Routing và nhiều metadata entry được đọc đúng |
| Metadata extractor | Tenant/trace header được ánh xạ đúng kiểu |
| MIME mismatch | Lỗi giải mã/unsupported MIME được báo rõ, không biến thành dữ liệu rỗng |
| Schema compatibility | Client/server phiên bản khác nhau xử lý field mới theo contract |
| Setup metadata | Client identity/auth metadata được nhận đúng ở connection setup |
| Security | Metadata giả mạo không vượt qua xác thực/ủy quyền |
| Payload limits | Data/metadata quá lớn bị từ chối theo chính sách |

Có thể dùng `StepVerifier` để xác minh `Mono`/`Flux` sau khi payload đã được giải mã. Kiểm thử tích hợp nên khởi chạy requester và responder thật qua TCP hoặc WebSocket, vì unit test codec riêng không xác minh được MIME type trong SETUP, routing metadata và metadata section trên wire.

Khi điều tra lỗi, ghi nhận MIME type data, MIME type metadata, route, loại codec và correlation ID. Không log toàn bộ metadata hoặc payload nếu chúng có thể chứa secret. Theo dõi số lỗi encode/decode, unsupported MIME type, metadata extraction failure, payload size và latency theo route.

## 15. Quy tắc thiết kế

1. Chọn `dataMimeType` theo định dạng bytes thực tế của data.
2. Chọn `metadataMimeType` theo cấu trúc metadata section; dùng Composite Metadata khi cần nhiều entry khác MIME type.
3. Cấu hình `RSocketStrategies` với encoder/decoder tương ứng ở cả client và server.
4. Đăng ký metadata extractor cho entry tùy chỉnh mà handler cần đọc.
5. Không coi MIME type là content negotiation tự động; hai peer phải triển khai contract tương thích.
6. Dùng setup metadata cho ngữ cảnh connection và request metadata cho ngữ cảnh từng tương tác.
7. Giữ codec mặc định cần thiết khi thêm codec tùy chỉnh; kiểm tra thứ tự và kiểu được hỗ trợ.
8. Version hóa schema/MIME type khi thay đổi không tương thích.
9. Bảo vệ metadata/data và giới hạn kích thước trước khi decode sâu.
10. Kiểm thử qua transport thật để xác minh encoding, decoding, routing và metadata extraction.

`dataMimeType` cho biết cách đọc data, `metadataMimeType` cho biết cách đọc metadata section, còn `RSocketStrategies` cung cấp codec và extractor để chuyển đổi hai phần đó thành kiểu Java. Khi client và server thống nhất MIME type, schema và codec, `RSocketRequester` có thể trao đổi DTO và metadata rõ ràng qua TCP hoặc WebSocket mà không làm logic nghiệp vụ phụ thuộc vào chi tiết bytes của giao thức.
