# Kiểm thử tương thích giữa các ngôn ngữ bằng hợp đồng payload và metadata

Một hệ thống RSocket có thể gồm dịch vụ Java dùng Spring Boot, ứng dụng trình duyệt viết bằng JavaScript và các dịch vụ khác được triển khai bằng ngôn ngữ riêng. Các peer không cần dùng chung class, framework hoặc runtime, nhưng phải hiểu cùng một định dạng dữ liệu trên đường truyền. Nếu Java gửi một trường số nguyên 64 bit còn JavaScript làm tròn giá trị đó, hoặc server mong đợi metadata tenant dạng JSON nhưng browser gửi chuỗi theo MIME type khác, kết nối vẫn có thể mở thành công trong khi interaction thất bại hoặc dữ liệu bị hiểu sai.

Cách giải quyết là thiết kế **hợp đồng wire** cho payload và metadata, sau đó kiểm thử hợp đồng từ từng ngôn ngữ. Hợp đồng phải mô tả MIME type, cấu trúc field, kiểu dữ liệu, quy tắc null, timestamp, số thập phân, enum, version và hành vi khi gặp dữ liệu chưa biết. Bài học này lấy Java/Spring và browser JavaScript giao tiếp qua RSocket WebSocket làm ví dụ, đồng thời áp dụng được cho các peer viết bằng ngôn ngữ khác.

Sau bài học, bạn có thể:

- Phân biệt hợp đồng wire với DTO hoặc class của một ngôn ngữ.
- Thiết kế payload JSON và Composite Metadata có thể đọc từ nhiều runtime.
- Thống nhất MIME type, schema, kiểu số, timestamp, null và enum.
- Cấu hình Spring RSocket để encode/decode theo hợp đồng.
- Serialize và parse cùng fixture bằng Java và JavaScript.
- Kiểm thử tương thích theo cả hai chiều client-server.
- Kiểm thử phiên bản cũ/mới, metadata thiếu, MIME type sai và payload không hợp lệ.
- Chạy kiểm thử qua WebSocket thực trong browser và bảo vệ endpoint bằng WSS, origin validation cùng authentication.

## 1. Tương thích đa ngôn ngữ là tương thích trên wire

Java và JavaScript có thể mô tả cùng một thông điệp bằng các kiểu khác nhau:

| Khái niệm nghiệp vụ | Java | JavaScript | Wire JSON |
|---|---|---|---|
| Mã sản phẩm | String | string | JSON string |
| Số lượng | int | number | JSON integer trong miền đã quy định |
| Mã định danh lớn | long/Long | string hoặc BigInt nội bộ | JSON string |
| Số tiền | BigDecimal | decimal library hoặc string | JSON string theo quy tắc decimal |
| Thời điểm | Instant | Date | ISO 8601 UTC string |
| Có/không | boolean | boolean | JSON boolean |
| Trường tùy chọn | nullable/reference | undefined hoặc null | Quy tắc field vắng mặt/null |

Class Java và object JavaScript không được truyền trực tiếp qua mạng. Encoder chuyển object thành byte; peer nhận byte và decoder diễn giải theo MIME type cùng schema. Vì vậy, hợp đồng cần mô tả byte và ý nghĩa dữ liệu mà hai phía trao đổi.

~~~mermaid
flowchart LR
    subgraph JAVA[Java / Spring]
        A[Java DTO] --> B[Jackson Encoder]
        B --> C[UTF-8 JSON bytes]
    end
    C --> D[RSocket over WebSocket]
    D --> E[UTF-8 JSON bytes]
    subgraph BROWSER[Browser / JavaScript]
        E --> F[TextDecoder and JSON.parse]
        F --> G[JavaScript object]
    end
~~~

Một test chỉ kiểm tra Java serialize rồi Java deserialize lại không chứng minh JavaScript đọc được dữ liệu đó. Tương tự, JavaScript stringify rồi parse trong cùng runtime không chứng minh Spring có thể decode thành DTO. Cần kiểm thử chéo ngôn ngữ.

## 2. Chọn transport phù hợp cho browser

Browser không mở raw TCP socket tùy ý. RSocket client chạy trong browser thường dùng WebSocket; ứng dụng Java backend có thể dùng TCP hoặc WebSocket tùy kiến trúc.

~~~mermaid
flowchart TD
    A[Browser JavaScript] -->|RSocket over WSS| B[WebSocket endpoint / Gateway]
    B --> C[Spring RSocket server]
    D[Java service] -->|RSocket over TCP or WebSocket| C
    C --> E[Business services]
~~~

Các điểm cần nhớ:

- Browser dùng WebSocket hoặc WebSocket Secure (WSS) để mang RSocket frame.
- Java service có thể dùng TCP transport nếu mạng backend cho phép.
- Nếu browser đi qua reverse proxy hoặc gateway, proxy phải hỗ trợ WebSocket upgrade và timeout đủ dài cho kết nối realtime.
- CORS và WebSocket Origin validation là các cơ chế khác nhau. Cấu hình CORS cho HTTP API không tự động thay thế kiểm tra Origin khi bắt tay WebSocket.
- Dùng WSS trong môi trường thật để mã hóa đường truyền.
- Kiểm thử trên browser thật vì hành vi WebSocket, cookie, origin và lifecycle tab khác môi trường Node.js.

RSocket interaction vẫn giữ cùng ngữ nghĩa trên transport được hỗ trợ. Khác biệt transport không làm thay đổi schema payload hoặc MIME type mà hai peer đã thống nhất.

## 3. Định nghĩa hợp đồng payload trước khi viết DTO

Ví dụ route inventory.check nhận yêu cầu kiểm tra tồn kho. Hợp đồng JSON có thể là:

~~~json
{
  "contractVersion": 1,
  "requestId": "req-2026-000042",
  "sku": "SKU-42",
  "quantity": 3,
  "requestedAt": "2026-11-22T10:15:30.000Z"
}
~~~

Response:

~~~json
{
  "contractVersion": 1,
  "requestId": "req-2026-000042",
  "sku": "SKU-42",
  "available": true,
  "availableQuantity": 18,
  "checkedAt": "2026-11-22T10:15:30.125Z"
}
~~~

Hợp đồng phải xác định ý nghĩa của từng field:

| Field | Kiểu wire | Bắt buộc | Quy tắc |
|---|---|---|---|
| contractVersion | integer | Có | Phiên bản schema payload |
| requestId | string | Có | ID ổn định để trace và deduplicate nếu cần |
| sku | string | Có | Không rỗng, quy tắc casing được công bố |
| quantity | integer | Có | Số nguyên dương trong miền giới hạn |
| requestedAt | string | Có | ISO 8601 UTC, hậu tố Z |
| available | boolean | Có | Trạng thái tồn kho |
| availableQuantity | integer | Có | Không âm |

Tên field JSON phân biệt chữ hoa/chữ thường. sku và SKU là hai key khác nhau. Không dựa vào quy tắc tự đổi casing của một serializer nếu hợp đồng công bố tên field cụ thể.

Nên quản lý schema độc lập với DTO. Có thể dùng JSON Schema, AsyncAPI hoặc tài liệu contract tương đương làm nguồn chuẩn. Dù chọn công cụ nào, cần lưu fixture payload và metadata đại diện để tất cả ngôn ngữ dùng trong kiểm thử.

## 4. Thống nhất quy tắc kiểu dữ liệu giữa JVM và JavaScript

Khác biệt kiểu dữ liệu là một trong những nguyên nhân phổ biến nhất khiến hai ngôn ngữ deserialize thành công nhưng hiểu sai giá trị.

### Số nguyên lớn

Java long có thể biểu diễn số nguyên lớn hơn miền an toàn của JavaScript Number. JavaScript Number chỉ biểu diễn chính xác mọi số nguyên đến 2^53 - 1.

Nếu ID hoặc sequence có thể vượt miền này, hãy truyền dưới dạng JSON string:

~~~json
{
  "eventId": "9223372036854775806",
  "sequence": "9223372036854775806"
}
~~~

Java có thể parse string thành long hoặc BigInteger sau khi validate. JavaScript có thể dùng BigInt nội bộ, nhưng JSON.stringify không serialize BigInt trực tiếp; hãy chuyển về string trước khi gửi.

Với quantity nhỏ có giới hạn rõ, JSON number là lựa chọn phù hợp. Hãy công bố miền hợp lệ thay vì để mỗi ngôn ngữ tự suy đoán.

### Số thập phân và tiền tệ

Java BigDecimal giữ độ chính xác thập phân; JavaScript Number dùng floating point nhị phân. Không nên truyền số tiền dạng JSON number nếu yêu cầu chính xác tuyệt đối.

Có thể dùng string decimal:

~~~json
{
  "currency": "VND",
  "amount": "125000.50"
}
~~~

Hợp đồng phải quy định scale, dấu thập phân, cách làm tròn và currency. Không dùng dấu phân cách hàng nghìn trong wire value. Java parse bằng BigDecimal; JavaScript dùng decimal library hoặc giữ string cho tới khi tính toán.

Một lựa chọn khác là số nguyên minor units, ví dụ amountMinor: 12500050, nhưng cần thống nhất số chữ số thập phân theo currency. Không mặc định mọi currency đều có hai chữ số thập phân.

### Timestamp và timezone

Dùng chuỗi ISO 8601/RFC 3339 có timezone rõ ràng, ưu tiên UTC:

~~~json
{
  "createdAt": "2026-11-22T10:15:30.125Z"
}
~~~

Java có thể dùng Instant. JavaScript có thể parse bằng Date. Hợp đồng cần quy định độ chính xác mili giây hay nano giây; JavaScript Date chỉ giữ độ chính xác tới mili giây. Nếu cần giữ nano giây, truyền timestamp dạng chuỗi với định dạng được định nghĩa hoặc tách epoch seconds và nanos thành hai field.

Không truyền local datetime không có offset nếu sự kiện cần diễn giải giống nhau ở nhiều timezone.

### Null, field vắng mặt và default

JSON phân biệt field không xuất hiện với field có giá trị null. Java DTO nullable và JavaScript undefined/null có thể xử lý khác nhau.

Ví dụ:

~~~json
{
  "displayName": null
}
~~~

Khác với:

~~~json
{}
~~~

Hãy quy định từng field:

- Bắt buộc và không được null.
- Tùy chọn, có thể vắng mặt.
- Có thể null để biểu thị xóa hoặc chưa xác định.
- Có default khi field vắng mặt.
- Không chấp nhận giá trị null.

Đặc biệt với PATCH hoặc cập nhật một phần, null có thể mang nghĩa xóa giá trị còn field vắng mặt nghĩa là giữ nguyên. Không gộp hai trường hợp này nếu nghiệp vụ phân biệt chúng.

## 5. Enum và field mới

Giả sử server có trạng thái:

~~~java
public enum ReservationStatus {
    HELD,
    RELEASED,
    EXPIRED
}
~~~

Client JavaScript có thể chỉ biết HELD và RELEASED. Nếu server thêm EXPIRED, client cũ cần có hành vi xác định.

Các cách thiết kế:

- Cho phép client giữ nguyên unknown enum value và hiển thị trạng thái chung.
- Dùng string thay vì enum đóng trong DTO phía browser.
- Có giá trị UNKNOWN ở lớp domain phía client.
- Version hóa hợp đồng nếu thêm enum làm thay đổi logic bắt buộc.

Không nên để client cũ ném lỗi parse chỉ vì server thêm một giá trị enum mới nếu thay đổi đó được xem là tương thích. Ngược lại, nếu client cần xử lý mọi trạng thái cụ thể, phải định nghĩa chính sách khi gặp giá trị chưa biết.

Với field mới, ưu tiên field tùy chọn và default rõ ràng. Khi đổi tên hoặc đổi kiểu field, cần giai đoạn chuyển tiếp hoặc version mới.

## 6. Data MIME type và metadata MIME type

RSocket SETUP khai báo MIME type cho data và metadata ở cấp kết nối. Khi dùng Composite Metadata, mỗi entry metadata có MIME type riêng.

Ví dụ:

| Thành phần | MIME type | Mục đích |
|---|---|---|
| Data payload | application/json | Request/response DTO |
| Metadata section | message/x.rsocket.composite-metadata.v0 | Bao ngoài nhiều metadata entry |
| Routing entry | message/x.rsocket.routing.v0 | Chọn route |
| Tenant entry | application/vnd.acme.tenant-v1+json | Ngữ cảnh tenant |
| Correlation entry | application/vnd.acme.correlation-v1+json | Trace request |
| Auth entry | MIME type theo extension/hợp đồng bảo mật | Thông tin xác thực |

Không nhầm MIME type của toàn metadata section với MIME type của từng entry. Nếu client khai báo Composite Metadata trong SETUP nhưng gửi một entry custom mà server chưa đăng ký extractor/decoder, Spring có thể không đưa giá trị đó vào handler header.

Đối với dữ liệu JSON, cả hai phía cần thống nhất UTF-8, cấu trúc JSON và quy tắc schema. MIME type application/json không tự mô tả kiểu field hay version nghiệp vụ.

## 7. Thiết kế metadata trung lập với ngôn ngữ

Ví dụ metadata tenant:

~~~json
{
  "tenantId": "tenant-17"
}
~~~

Correlation metadata:

~~~json
{
  "correlationId": "corr-91"
}
~~~

Định nghĩa MIME type vendor có version:

~~~text
application/vnd.acme.tenant-v1+json
application/vnd.acme.correlation-v1+json
~~~

Mỗi entry cần một hợp đồng riêng:

| Entry | Field | Quy tắc |
|---|---|---|
| Tenant | tenantId | String không rỗng; không được xem là bằng chứng đã xác thực |
| Correlation | correlationId | String dùng nối log/trace; không dùng làm quyền truy cập |
| Locale | languageTag | BCP 47, ví dụ vi-VN |
| Trace | trace context | Theo chuẩn tracing đã chọn; validate trước khi sử dụng |

Không đưa mọi thông tin vào một metadata JSON tổng hợp nếu các phần có vòng đời hoặc quyền sở hữu khác nhau. Entry riêng giúp version và kiểm soát quyền rõ ràng hơn.

Routing metadata nên dùng chuẩn RSocket routing và API route của client. Không tự gửi một JSON field route nếu server đang chờ routing entry chuẩn.

## 8. Cấu hình Spring responder

Phía Java Spring cần encoder/decoder cho data JSON và custom metadata JSON. MetadataExtractor đăng ký từng MIME type và đưa object đã decode vào message header.

~~~java
@Configuration
public class RSocketContractConfiguration {

    static final MimeType TENANT_MIME =
        MimeType.valueOf(
            "application/vnd.acme.tenant-v1+json"
        );

    static final MimeType CORRELATION_MIME =
        MimeType.valueOf(
            "application/vnd.acme.correlation-v1+json"
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
                registry.metadataToExtract(
                    CORRELATION_MIME,
                    CorrelationContext.class,
                    "correlation"
                );
            })
            .build();
    }
}
~~~

Handler:

~~~java
@Controller
public class InventoryController {

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

Tên trong @Header phải khớp tên được đăng ký trong metadataToExtract. Cả client và server không cần chia sẻ TenantContext hoặc CorrelationContext class; browser chỉ cần gửi JSON bytes với đúng MIME type và schema.

Nếu server dùng Java Time hoặc kiểu số đặc biệt, cấu hình Jackson module và serialization policy tương ứng. Hãy kiểm tra Jackson configuration của ứng dụng thay vì giả định mọi ObjectMapper có cùng behavior.

## 9. Cấu hình Java requester

Client Java có thể dùng RSocketRequester với cùng hợp đồng:

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

Gửi request và custom metadata:

~~~java
Mono<InventoryResult> check(
        InventoryCheckRequest request,
        TenantContext tenant,
        CorrelationContext correlation) {

    return requester
        .route("inventory.check")
        .metadata(
            tenant,
            RSocketContractConfiguration.TENANT_MIME
        )
        .metadata(
            correlation,
            RSocketContractConfiguration.CORRELATION_MIME
        )
        .data(request)
        .retrieveMono(InventoryResult.class);
}
~~~

Cấu hình này là ví dụ backend Java-to-Java. Browser sẽ dùng WebSocket transport nhưng vẫn gửi cùng data JSON và Composite Metadata entries. Transport khác nhau không có nghĩa schema khác nhau.

## 10. JavaScript serialize payload theo hợp đồng

Ở browser, JSON.stringify tạo chuỗi JSON. TextEncoder chuyển chuỗi thành UTF-8 bytes; ở chiều nhận, TextDecoder và JSON.parse khôi phục object.

~~~javascript
function encodeJson(value) {
  const json = JSON.stringify(value);
  return new TextEncoder().encode(json);
}

function decodeJson(bytes) {
  const json = new TextDecoder("utf-8", { fatal: true })
    .decode(bytes);

  return JSON.parse(json);
}

const request = {
  contractVersion: 1,
  requestId: "req-2026-000042",
  sku: "SKU-42",
  quantity: 3,
  requestedAt: "2026-11-22T10:15:30.000Z"
};

const payloadBytes = encodeJson(request);
~~~

Đoạn mã trên minh họa phần serialize/deserialize của hợp đồng. API tạo RSocket client, encode Composite Metadata và gửi interaction phụ thuộc phiên bản thư viện RSocket JavaScript mà ứng dụng pin. Không nên sao chép một ví dụ API từ phiên bản khác mà chưa xác nhận package version và transport adapter.

Khi tích hợp thư viện browser:

- Cấu hình data MIME type là application/json.
- Cấu hình metadata MIME type là Composite Metadata.
- Encode route bằng routing metadata chuẩn.
- Encode custom metadata entry với đúng MIME type và UTF-8 JSON.
- Decode response bằng UTF-8 và JSON parser.
- Xử lý onError, timeout, close và reconnect theo lifecycle của tab.
- Kiểm tra browser bundle có dùng đúng serializer/encoder mà phiên bản thư viện yêu cầu.

Không tự ghép byte Composite Metadata bằng chuỗi JSON. Composite Metadata là định dạng nhị phân có header MIME type và length; hãy dùng encoder của thư viện RSocket tương ứng.

## 11. Tạo fixture dùng chung cho nhiều ngôn ngữ

Một fixture là dữ liệu mẫu chuẩn mà mọi implementation phải đọc và tạo ra tương đương. Fixture có thể được lưu trong contract repository hoặc package schema dùng chung, nhưng không cần dùng chung class Java/TypeScript.

Ví dụ fixture request:

~~~json
{
  "contractVersion": 1,
  "requestId": "req-2026-000042",
  "sku": "SKU-42",
  "quantity": 3,
  "requestedAt": "2026-11-22T10:15:30.000Z"
}
~~~

Fixture response:

~~~json
{
  "contractVersion": 1,
  "requestId": "req-2026-000042",
  "sku": "SKU-42",
  "available": true,
  "availableQuantity": 18,
  "checkedAt": "2026-11-22T10:15:30.125Z"
}
~~~

Fixture tenant metadata:

~~~json
{
  "tenantId": "tenant-17"
}
~~~

Fixture correlation metadata:

~~~json
{
  "correlationId": "corr-91"
}
~~~

Mỗi fixture nên có mô tả MIME type, route, chiều gửi/nhận và phiên bản schema. Đối với Composite Metadata, kiểm thử cả nội dung từng entry lẫn MIME type của entry. Một fixture JSON đúng nhưng gắn MIME type sai vẫn là request không tương thích.

Không chỉ so sánh chuỗi JSON byte-for-byte nếu thứ tự key không phải một phần hợp đồng. Nên parse JSON rồi so sánh cấu trúc và giá trị. Nếu cần chữ ký số hoặc hash payload, phải định nghĩa canonical JSON hoặc ký trên representation đã chuẩn hóa.

## 12. Kiểm thử Java encode và decode fixture

Có thể dùng Jackson ObjectMapper để kiểm thử DTO Java với fixture. Cấu hình ObjectMapper phải tương ứng cấu hình runtime, bao gồm module thời gian, naming strategy và quy tắc unknown field.

~~~java
class InventoryContractTest {

    private final ObjectMapper mapper =
        new ObjectMapper()
            .registerModule(new JavaTimeModule());

    @Test
    void readsCanonicalRequestFixture() throws Exception {
        String json = """
            {
              "contractVersion": 1,
              "requestId": "req-2026-000042",
              "sku": "SKU-42",
              "quantity": 3,
              "requestedAt": "2026-11-22T10:15:30.000Z"
            }
            """;

        InventoryCheckRequest request =
            mapper.readValue(json, InventoryCheckRequest.class);

        assertThat(request.contractVersion()).isEqualTo(1);
        assertThat(request.requestId())
            .isEqualTo("req-2026-000042");
        assertThat(request.quantity()).isEqualTo(3);
    }
}
~~~

Kiểm thử chiều encode:

~~~java
@Test
void writesFieldsRequiredByContract() throws Exception {
    InventoryCheckRequest request = sampleRequest();

    JsonNode json = mapper.readTree(
        mapper.writeValueAsBytes(request)
    );

    assertThat(json.path("sku").asText()).isEqualTo("SKU-42");
    assertThat(json.path("quantity").asInt()).isEqualTo(3);
    assertThat(json.path("contractVersion").asInt()).isEqualTo(1);
}
~~~

Kiểm thử cấu trúc thay vì thứ tự field. Nếu field bắt buộc bị thiếu, test phải thất bại. Nếu field tùy chọn vắng mặt, test cần xác nhận default behavior đúng với hợp đồng.

## 13. Kiểm thử JavaScript với cùng fixture

JavaScript đọc fixture bằng JSON.parse và kiểm tra các field theo schema:

~~~javascript
function validateInventoryRequest(value) {
  if (value.contractVersion !== 1) {
    throw new Error("Unsupported contractVersion");
  }

  if (typeof value.requestId !== "string" || value.requestId.length === 0) {
    throw new Error("requestId must be a non-empty string");
  }

  if (typeof value.sku !== "string" || value.sku.length === 0) {
    throw new Error("sku must be a non-empty string");
  }

  if (!Number.isSafeInteger(value.quantity) || value.quantity <= 0) {
    throw new Error("quantity must be a positive safe integer");
  }

  if (typeof value.requestedAt !== "string" ||
      Number.isNaN(Date.parse(value.requestedAt))) {
    throw new Error("requestedAt must be a valid timestamp");
  }

  return value;
}
~~~

Đừng chỉ kiểm tra typeof number cho quantity. JavaScript có thể nhận một số lớn nhưng không biểu diễn chính xác. Number.isSafeInteger kiểm tra cả tính nguyên và miền an toàn.

Test JavaScript cần dùng fixture giống Java test. Nếu browser app có schema validator như Ajv, hãy chạy cùng JSON Schema ở test Node và trong bundle browser để tránh hai nơi định nghĩa validation khác nhau. Việc dùng chung schema không có nghĩa phải dùng chung implementation DTO.

## 14. Kiểm thử chéo ngôn ngữ theo hai chiều

Tạo ma trận test:

| Producer | Consumer | Điều cần xác nhận |
|---|---|---|
| Java | Java | Baseline của backend |
| JavaScript | Java | Browser payload được Spring decode |
| Java | JavaScript | Browser parse được response của server |
| JavaScript | JavaScript | Baseline của browser client |
| Java metadata | Spring metadata extractor | MIME type và header đúng |
| Browser metadata | Spring metadata extractor | Composite entry và DTO metadata tương thích |
| Spring metadata | Browser decoder | Custom entry được parse đúng |
| Browser metadata | Browser decoder | Fixture và encoder nhất quán |

Contract test nên kiểm tra:

1. Cùng field names và casing.
2. Cùng kiểu dữ liệu và miền giá trị.
3. Cùng quy tắc null/absent/default.
4. Cùng format timestamp và decimal.
5. Cùng MIME type ở cấp kết nối và entry.
6. Route metadata được giải mã thành đúng route.
7. Custom metadata được ánh xạ thành đúng header.
8. Unknown field/enum được xử lý theo chính sách đã công bố.
9. Payload không hợp lệ bị từ chối có kiểm soát.

Một test JavaScript gọi JSON.parse thành công không chứng minh WebSocket/RSocket metadata được mã hóa đúng. Cần integration test chạy qua RSocket client và Spring responder.

## 15. Kiểm thử end-to-end qua RSocket WebSocket

Kiểm thử browser thực tế nên chạy với server có endpoint WebSocket. Có thể dùng Playwright hoặc công cụ browser test để mở trang kiểm thử, tạo RSocket client bằng phiên bản thư viện đã pin và thực hiện request-response.

Kịch bản mẫu:

~~~text
1. Browser mở WSS endpoint.
2. Client gửi SETUP với data MIME type application/json.
3. Client gửi metadata MIME type Composite Metadata.
4. Client gọi route inventory.check.
5. Data chứa fixture InventoryCheckRequest.
6. Metadata chứa tenant-v1 và correlation-v1.
7. Spring giải mã data và custom metadata.
8. Handler xác nhận tenant và xử lý tồn kho.
9. Spring encode InventoryResult.
10. Browser decode response và kiểm tra schema.
~~~

Kiểm thử thêm các tình huống:

- Endpoint WebSocket trả lỗi hoặc không upgrade.
- Origin không được cho phép.
- Token hết hạn hoặc thiếu authentication metadata.
- MIME type data không được hỗ trợ.
- Custom metadata thiếu hoặc sai schema.
- Browser đóng tab giữa request.
- Mạng bị ngắt rồi kết nối lại.
- Server gửi enum mới mà browser chưa biết.
- Response chứa số nguyên lớn hoặc decimal.
- Request timeout sau khi server đã commit.

Chạy test trên browser thật hoặc browser automation. Test Node chỉ có WebSocket implementation của Node, không kiểm tra đầy đủ cookie, origin, tab lifecycle và chính sách bảo mật của browser.

## 16. Kiểm thử tương thích phiên bản cũ và mới

Trong triển khai rolling upgrade, client và server có thể không cùng version trong một khoảng thời gian. Hợp đồng cần xác định các thay đổi tương thích.

| Thay đổi | Mức độ tương thích thường gặp | Quy tắc |
|---|---|---|
| Thêm field optional | Có thể tương thích | Client cũ bỏ qua field lạ |
| Thêm field required | Không tương thích nếu client cũ không gửi | Có default hoặc version mới |
| Đổi tên field | Không tương thích | Duy trì alias hoặc chuyển tiếp |
| Đổi kiểu number thành string | Không tương thích | Field mới hoặc version mới |
| Thêm enum value | Có điều kiện | Client cũ cần unknown behavior |
| Xóa field | Có thể phá consumer cũ | Deprecation trước khi xóa |
| Đổi MIME type metadata | Cần hai phía hỗ trợ | Đăng ký đồng thời version cũ/mới |

Một chiến lược an toàn:

1. Server mở rộng decoder để đọc cả v1 và v2.
2. Client mới bắt đầu gửi v2.
3. Quan sát số client còn dùng v1.
4. Ngừng phát v1 sau khi hết client cũ.
5. Gỡ decoder v1 trong một release sau.

Đối với data JSON có thể giữ application/json và dùng contractVersion hoặc version route. Đối với custom metadata, MIME type vendor có version giúp phân biệt schema rõ ràng.

Không đổi ý nghĩa field mà vẫn giữ nguyên version. Điều này nguy hiểm hơn lỗi decode vì dữ liệu có thể được chấp nhận nhưng diễn giải sai.

## 17. Kiểm thử lỗi và dữ liệu biên

Bộ fixture nên có cả dữ liệu hợp lệ và không hợp lệ:

| Case | Ví dụ | Kết quả mong đợi |
|---|---|---|
| Thiếu field bắt buộc | Không có sku | Validation error |
| Sai kiểu | quantity là chuỗi "3" | Reject hoặc coercion theo policy rõ |
| Số nguyên vượt miền an toàn JS | quantity quá 2^53 - 1 | Reject hoặc dùng string |
| Decimal tiền tệ | "125000.50" | Giữ nguyên độ chính xác |
| Timestamp thiếu timezone | "2026-11-22T10:15:30" | Reject nếu hợp đồng yêu cầu UTC |
| Field null | displayName: null | Xử lý theo null semantics |
| Enum lạ | status: "PAUSED" | Unknown/default behavior |
| MIME type sai | tenant-v2 gửi cho decoder chỉ hỗ trợ v1 | Reject hoặc fallback đã định nghĩa |
| Metadata thiếu | Không có tenant entry | Reject request nếu bắt buộc |
| Unicode | Chuỗi có dấu tiếng Việt | UTF-8 round-trip chính xác |
| Payload quá lớn | JSON vượt giới hạn | Từ chối trước khi tiêu thụ tài nguyên quá mức |

Với Unicode, kiểm tra cả chuỗi có dấu tiếng Việt, ký tự ngoài BMP và chuỗi có dạng Unicode normalization khác nhau nếu hệ thống so sánh identifier. JSON UTF-8 có thể biểu diễn Unicode, nhưng quy tắc chuẩn hóa chuỗi là quyết định của hợp đồng nghiệp vụ.

## 18. Bảo mật metadata và browser endpoint

Browser client có một số giới hạn khác native client. WebSocket API trong browser không cho ứng dụng tùy ý đặt mọi HTTP header trong handshake. Do đó, không thiết kế authentication phụ thuộc vào một custom header mà browser không thể gửi.

Các lựa chọn cần được thống nhất với server:

- Cookie bảo mật phù hợp với domain, SameSite và CSRF policy.
- Token ngắn hạn được gửi qua cơ chế authentication metadata/setup đã thống nhất.
- Cấp credential qua HTTPS trước khi mở WSS.
- Kiểm tra Origin tại WebSocket endpoint.
- Dùng TLS và giới hạn thời hạn token.
- Không đặt access token hoặc secret trong query string vì URL có thể xuất hiện trong log.
- Không xem tenantId hoặc userId trong metadata là danh tính đã xác thực.

MetadataExtractor chỉ giải mã byte thành object; nó không xác thực token hoặc cấp quyền. Sau khi xác thực, server phải đối chiếu tenant metadata với principal và kiểm tra quyền trên từng route/tài nguyên.

Không log toàn bộ metadata hoặc payload nếu có token, dữ liệu cá nhân hay thông tin nhạy cảm. Có thể log MIME type, route, correlation ID đã lọc và kết quả authorization.

## 19. Quan sát lỗi tương thích

Nên phân loại metric và log để biết lỗi nằm ở tầng nào:

| Tầng | Metric/log hữu ích |
|---|---|
| Transport | WebSocket handshake failure, close code, reconnect count |
| SETUP | Data/metadata MIME type, setup rejection |
| Routing | Route không tìm thấy, route không hợp lệ |
| Data codec | Decode/encode failure theo DTO và MIME type |
| Metadata codec | Entry MIME type không hỗ trợ, extraction failure |
| Schema | Validation failure theo contractVersion |
| Nghiệp vụ | Error code, correlation ID |
| Versioning | Số client/peer dùng từng contract version |

Không ghi nội dung token, payload nhạy cảm hoặc dữ liệu cá nhân vào metric label. Dùng tên MIME type và version làm dimension có kiểm soát; tránh đưa requestId duy nhất vào metric label vì gây cardinality cao.

## 20. Quy trình xây dựng bộ kiểm thử contract

Khi thêm một client hoặc service viết bằng ngôn ngữ mới, thực hiện theo thứ tự:

1. Chọn route và interaction RSocket.
2. Công bố data MIME type và metadata MIME type.
3. Mô tả payload schema và custom metadata schema.
4. Quy định kiểu số, decimal, timestamp, null, enum và Unicode.
5. Tạo fixture request, response và metadata.
6. Viết test encode/decode riêng trong từng ngôn ngữ.
7. Chạy test chéo: Java tạo fixture cho JavaScript và ngược lại.
8. Chạy integration test qua transport thực, đặc biệt WSS cho browser.
9. Kiểm tra version cũ/mới và dữ liệu biên.
10. Kiểm tra authentication, Origin và metadata bắt buộc.
11. Theo dõi lỗi codec/schema sau triển khai.
12. Chỉ loại bỏ schema cũ khi không còn peer sử dụng.

Hợp đồng payload và metadata là nền tảng để các ứng dụng khác ngôn ngữ giao tiếp ổn định. Khi fixture, MIME type, schema và quy tắc tương thích được kiểm thử từ cả hai phía, hệ thống có thể thay đổi runtime hoặc ngôn ngữ mà không làm thay đổi ý nghĩa dữ liệu trên wire.

## Ghi nhớ

- Tương thích đa ngôn ngữ là tương thích wire format, không phải dùng chung DTO.
- Browser RSocket thường dùng WebSocket/WSS; browser không mở raw TCP socket tùy ý.
- Data MIME type và metadata MIME type được khai báo ở SETUP; Composite Metadata có MIME type riêng cho từng entry.
- JavaScript Number không biểu diễn chính xác mọi Java long; ID lớn nên truyền dưới dạng string.
- Tiền tệ cần quy tắc decimal chính xác; timestamp cần timezone và độ chính xác rõ.
- Field vắng mặt, null và default có thể mang ý nghĩa khác nhau.
- Enum và field mới cần unknown behavior để hỗ trợ rolling upgrade.
- Metadata phải có schema, MIME type và version; tenant metadata không phải bằng chứng xác thực.
- Contract test phải chạy hai chiều Java ↔ JavaScript và qua RSocket transport thật.
- Browser test cần kiểm tra WSS, Origin, cookie/token và lifecycle tab.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [RSocket Composite Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/CompositeMetadata.md)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — RSocketStrategies API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [RSocket JavaScript](https://github.com/rsocket/rsocket-js)
- [MDN — WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [MDN — Number.MAX_SAFE_INTEGER](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Number/MAX_SAFE_INTEGER)
- [JSON Schema](https://json-schema.org/learn/getting-started-step-by-step)

