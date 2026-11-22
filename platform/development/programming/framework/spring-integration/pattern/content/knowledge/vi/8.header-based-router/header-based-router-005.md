# Header mapper trước khi route

## 1. Vì sao phải map header trước khi định tuyến?

Một hệ thống xử lý đơn hàng nhận message từ **HTTP API**, **Kafka** và **AMQP**. Producer gửi thông tin thị trường trong header để hệ thống chuyển message tới nhánh phù hợp: `VN` vào `orders.vn`, `US` vào `orders.us`, còn dữ liệu khác phải được phân loại. Tuy nhiên, ba nguồn không nhất thiết biểu diễn header giống nhau:

- HTTP có thể gửi `X-Route-Region: vn` dưới dạng request header văn bản.
- Kafka lưu record header dưới dạng cặp tên và `byte[]`; deserializer hoặc header mapper của adapter có thể chuyển thành kiểu khác.
- AMQP có application headers, properties, routing key riêng; không phải tất cả đều được sao chép nguyên tên và kiểu vào Spring `MessageHeaders`.

Nếu Header Router đọc trực tiếp `headers['X-Route-Region']` nhưng Kafka adapter chỉ tạo header `region` có kiểu `byte[]`, biểu thức có thể không tìm thấy giá trị hoặc định tuyến sai. Nếu producer độc hại gắn header `routeKey=orders.admin` và flow tin nguyên giá trị đó, việc dùng header có thể biến thành một lỗ hổng phân quyền.

**Giải pháp:** thiết kế **header mapping và chuẩn hóa đầu vào trước khi route**. Chỉ cho Router đọc một tên header nội bộ ổn định, có kiểu và miền giá trị được kiểm soát; mọi adapter chịu trách nhiệm chuyển hợp đồng trên đường truyền sang hợp đồng ấy.

Bài học thuộc chương **Header-based router** trong module **SPRING_INTEGRATION_PATTERN**. Đây là một phần của mục tiêu thực hành **Enterprise Integration Patterns** bằng Spring Integration để xây dựng flow ít phụ thuộc, kết hợp **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry, error channel, correlation** và khả năng kiểm thử, theo dõi từng nhánh.

**Sau bài này, bạn có thể** phân biệt HeaderMapper và HeaderEnricher, cấu hình luồng mapping → validate → route, phòng vệ trước header thiếu/sai kiểu, thiết kế chính sách tin cậy và kiểm thử header mapping xuyên các transport.

## 2. Ba lớp header phải phân biệt

Trong message system, từ “header” có thể chỉ nhiều đối tượng khác nhau:

| Lớp | Nơi tồn tại | Ví dụ | Trách nhiệm |
|---|---|---|---|
| **Transport/native headers** | HTTP request, Kafka record, AMQP message | `X-Route-Region`, Kafka record header bytes | Phản ánh giao thức và serializer |
| **Spring MessageHeaders** | `Message<?>` trong JVM | `headers['routeKey']`, `id`, `timestamp` | Chứa metadata cho flow nội bộ |
| **Business context** | Command, DTO hoặc context ứng dụng | `orderId`, `tenantId` đã xác thực | Mang giá trị cần cho nghiệp vụ, không phụ thuộc transport |

**Header mapper** dịch giữa native headers và `MessageHeaders` tại ranh giới adapter. **Header enricher** bổ sung/chỉnh sửa header cho một Spring message đang ở trong flow. **Header Router** đọc header để quyết định kênh đích. Chúng liên quan nhưng không làm thay việc cho nhau.

~~~mermaid
flowchart LR
    H["HTTP headers / Kafka bytes / AMQP properties"] --> M["Inbound HeaderMapper"]
    M --> I["Spring MessageHeaders: raw"]
    I --> N["Validation + normalization / HeaderEnricher"]
    N --> C["Header nội bộ: routeKey"]
    C --> R{"Header-based Router"}
    R -->|"VN"| V["orders.vn"]
    R -->|"US"| U["orders.us"]
    R -->|"Không hợp lệ"| F["orders.route.rejected"]
~~~

Thông thường, **inbound mapping diễn ra trước khi Router nhận message**. Outbound mapping là chiều ngược lại: khi Spring message sắp được gửi ra HTTP/Kafka/AMQP, mapper lựa chọn các headers nào được phát ra và cách biểu diễn chúng ở transport.

Không suy luận rằng “đã có header trong HTTP” tức “Spring MessageHeaders có header cùng tên và cùng kiểu”. Mỗi adapter, mapper và cấu hình danh sách header được phép có thể tạo ra kết quả khác nhau.

## 3. Hợp đồng nội bộ cần được công bố trước

Giả sử hệ thống nhận lệnh xử lý đơn hàng:

~~~java
record OrderCommand(String orderId, int quantity) {}
~~~

Thay vì cho mỗi Router tự đoán các header `X-Route-Region`, `region` hoặc `x-region`, hãy công bố một **header nội bộ duy nhất**:

| Header | Nguồn | Kiểu trong flow | Quy tắc |
|---|---|---|---|
| `routeKey` | Tính từ region đã được chấp nhận | `String` | Chỉ một trong `VN`, `US`, `MISSING`, `INVALID`, `UNSUPPORTED` |
| `requestTraceId` | Request/trace context đã được xác minh | `String` | Dùng quan sát; không quyết định phân quyền |
| `sourceSystem` | Adapter do ứng dụng gán | `String` hoặc enum | Một trong `HTTP`, `KAFKA`, `AMQP` |
| `correlationId` | Quy trình tích hợp/flow hợp lệ | Kiểu được framework/flow quy định | Dùng khi phối hợp message, nhất là Splitter/Aggregator |
| `tenantId` | Identity/authorization service, nếu cần | Kiểu nghiệp vụ được quy định | Không sao chép mù từ header client |

Ở ingress, `routeKey` **không** lấy nguyên từ header do bên ngoài gửi; nó phải được **xây lại** từ header nguồn đã qua quy tắc kiểm tra. Có thể giữ raw header tạm thời trong vùng adapter để chẩn đoán, nhưng không để các handler nghiệp vụ dùng nó thay cho `routeKey`.

Một hợp đồng header cần trả lời: tên chuẩn là gì, giá trị có thể thiếu không, kiểu khi vào JVM là gì, các giá trị được phép, ai có quyền gán, có được phát ra transport khác không và lỗi sẽ đi kênh nào.

## 4. HeaderMapper khác HeaderEnricher như thế nào?

**HeaderMapper** là cầu nối giao thức. Ví dụ, mapper HTTP có thể lấy một số request headers rồi đưa chúng vào Spring message; mapper Kafka có thể chuyển các record headers nhị phân thành giá trị Java theo cấu hình.

**HeaderEnricher** là endpoint trong pipeline đã có `Message<?>`. Nó có thể gán header mặc định, lấy giá trị từ payload, tính header mới hoặc xóa metadata không còn cần thiết. HeaderEnricher không tự hiểu chính sách deserialize của broker nếu adapter chưa decode.

| Công việc | HeaderMapper | HeaderEnricher/Transformer |
|---|---|---|
| Đọc/ghi header từ HTTP hoặc Kafka wire format | Phù hợp | Không trực tiếp |
| Lựa chọn tên header native được đưa vào Spring message | Phù hợp | Có thể lọc lại, nhưng không thay policy tại ranh giới |
| Decode header bytes theo đúng charset/schema | Mapper/adapter phù hợp | Có thể chuẩn hóa thêm sau decode |
| Gán `routeKey` đã chuẩn hóa, kiểm tra whitelist | Có thể trong adapter | Thích hợp trong một bước riêng |
| Tạo header tính từ payload nghiệp vụ | Không phải trách nhiệm mặc định | Thích hợp |
| Chọn channel đích | Không | **Router** làm việc này |

Khi muốn tái sử dụng cùng một Router cho HTTP và Kafka, cách bền vững là để **hai mapper ở biên khác nhau**, nhưng cùng đưa dữ liệu về một **hợp đồng nội bộ** trước khi Router hoạt động.

## 5. Header mapping đầu vào HTTP

Với Spring Integration HTTP, `DefaultHttpHeaderMapper` có cơ chế chọn request headers inbound được đưa vào Spring message. Một ví dụ cấu hình có chủ đích:

~~~java
@Bean
DefaultHttpHeaderMapper inboundHttpHeaderMapper() {
    DefaultHttpHeaderMapper mapper =
        DefaultHttpHeaderMapper.inboundMapper();
    mapper.setInboundHeaderNames(
        "X-Route-Region",
        "X-Request-Id"
    );
    return mapper;
}
~~~

Đây là **bean mapper**; nó chỉ có tác dụng khi được **gắn vào inbound HTTP adapter/gateway** có hỗ trợ thuộc tính `headerMapper`. Chỉ khai báo bean rồi đặt tên không có nghĩa mọi HTTP request đi qua mapper đó. Cách gắn, bộ header mặc định và các tên nội bộ có thể phụ thuộc adapter cùng phiên bản Spring Integration đang dùng.

Các điểm phải kiểm tra khi thử nghiệm:

1. Request header `X-Route-Region` có thực sự xuất hiện trong Spring `MessageHeaders` sau mapper không?
2. Tên header có được chuẩn hóa chữ hoa/chữ thường, thêm prefix hoặc đổi tên không?
3. Nếu client gửi **nhiều giá trị cùng tên**, mapper chọn một giá trị, danh sách hay từ chối?
4. Header không được whitelist có bị loại đúng như mong đợi không?
5. Hệ thống có vô tình đưa `Authorization`, `Cookie` hoặc thông tin xác thực vào downstream message/log không?

Header HTTP là **dữ liệu do request cung cấp**, không tự động là sự thật nghiệp vụ. Client có thể tự đặt `X-Route-Region: VN`; nếu route quyết định vùng dữ liệu mà người dùng có quyền truy cập, phải kết hợp kiểm tra danh tính/authorization và dữ liệu nghiệp vụ tại server.

**Lưu ý về quy ước tên:** ví dụ dùng `X-Route-Region` làm tên bên ngoài vì dễ minh họa. Trong code thực tế, không phụ thuộc vào một quy ước `X-` cho mọi giao thức; tên phải được công bố trong contract và kiểm thử mapping.

## 6. Header mapping khi nhận Kafka và AMQP

Kafka header về bản chất là dữ liệu theo cặp tên–`byte[]`. Spring Kafka cung cấp các lựa chọn header mapper/converter, nhưng cách lưu kiểu Java và tái tạo giá trị phụ thuộc mapper, serializer và cấu hình trust. Không thể mặc định đoạn code:

~~~java
String region = (String) message.getHeaders().get("X-Route-Region");
~~~

luôn hợp lệ cho mọi consumer Kafka. Nếu giá trị thực tế vẫn là `byte[]`, phép ép kiểu sẽ thất bại. Một adapter được quản lý đúng phải định nghĩa **cách decode**, chẳng hạn UTF-8 cho một header text đã công bố, và chuyển nó thành kiểu mà bước chuẩn hóa có thể hiểu.

Ví dụ thao tác decode trực tiếp từ Kafka record header trong một adapter tự viết:

~~~java
Header raw = record.headers().lastHeader("route-region");
String region = raw == null
    ? null
    : raw.value() == null
        ? null
        : new String(raw.value(), StandardCharsets.UTF_8);
// Sau decode vẫn phải kiểm tra cú pháp, độ dài và tập giá trị hợp lệ.
~~~

Đây chỉ là minh họa logic tại **transport adapter**, không phải cấu hình Spring Integration Kafka đầy đủ. Trong hệ thống thực, nên xác định rõ hành vi khi header thiếu, có nhiều giá trị, dữ liệu không phải UTF-8 hợp lệ, header quá dài hoặc producer chuyển schema. Có thể dùng decoder báo lỗi với chuỗi byte không hợp lệ thay vì thay ký tự âm thầm.

AMQP có header/application properties bên cạnh các thuộc tính của message như delivery mode, routing key và correlation. `DefaultAmqpHeaderMapper` (ở tầng tích hợp AMQP tương ứng) có thể kiểm soát mapping inbound/outbound. Đừng nhầm **AMQP routing key** của broker với **`routeKey` nội bộ** dùng bởi Spring Integration Header Router; chúng có thể phục vụ hai tầng định tuyến khác nhau.

| Nguồn | Dữ liệu ở biên | Việc adapter phải công bố |
|---|---|---|
| HTTP | Tên và giá trị header HTTP | Whitelist, phân tích multi-value, case normalization |
| Kafka | Record headers ở dạng bytes | Header mapper, encoding, type mapping, trust |
| AMQP | Message properties và application headers | Trường được map, type conversion, metadata broker riêng |
| File/polling adapter | Metadata được adapter tạo | Tên chuẩn và kiểu dữ liệu, không giả định có HTTP headers |

Với mọi nguồn, adapter có thể phát message vào một channel chung sau khi đã chuyển payload/headers về hợp đồng nội bộ. **Header Router downstream không cần biết message ban đầu đến từ giao thức nào.**

## 7. Pipeline chuẩn: inbound mapper → normalize → Header Router

Hãy đặt một bước điều chỉnh header duy nhất sau các adapter. Bước này nhận Spring message và tính routing key theo chính sách thống nhất.

~~~mermaid
flowchart TD
    H["HTTP ingress + mapper"] --> RAW["orders.headers.raw"]
    K["Kafka ingress + decoder/mapper"] --> RAW
    A["AMQP ingress + mapper"] --> RAW
    RAW --> P["Header policy: kiểm tra kiểu, normalize"]
    P --> R{"Header Router: headers.routeKey"}
    R -->|"VN"| V["orders.vn"]
    R -->|"US"| U["orders.us"]
    R -->|"MISSING"| M["orders.route.missing"]
    R -->|"INVALID"| I["orders.route.invalid"]
    R -->|"UNSUPPORTED"| X["orders.route.unsupported"]
    R -.->|"Exception"| E["Error handling riêng"]
~~~

**Đặt tên channel đích theo mục đích**, không dùng nguyên giá trị header bên ngoài làm tên bean. Hai trạng thái `MISSING` và `UNSUPPORTED` khác nhau: trường hợp đầu là dữ liệu thiếu; trường hợp sau là dữ liệu có giá trị nhưng chưa có nhánh phù hợp.

Header Router có thể dùng `HeaderValueRouter` nếu chỉ route theo một header, hoặc dùng biểu thức `headers['routeKey']` trong Java DSL. Cả hai đều dựa trên **header đã được map và kiểm tra**, không giải quyết thay lỗi parse/authorization ở ingress.

## 8. Viết bước chuẩn hóa an toàn bằng Java

Một hàm policy thuần Java giúp kiểm thử dữ liệu sai kiểu, null và key không hỗ trợ trước khi gọi Router.

~~~java
public final class InboundHeaderPolicy {

    public Message<?> normalize(Message<?> source) {
        Object raw = source.getHeaders().get("X-Route-Region");
        String routeKey = toRouteKey(raw);

        return MessageBuilder.fromMessage(source)
            .removeHeader("X-Route-Region")
            .setHeader("routeKey", routeKey)
            .build();
    }

    public String toRouteKey(Object raw) {
        if (raw == null) {
            return "MISSING";
        }
        if (!(raw instanceof String text)) {
            return "INVALID";
        }
        String normalized =
            text.trim().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            return "INVALID";
        }
        return switch (normalized) {
            case "VN", "US" -> normalized;
            default -> "UNSUPPORTED";
        };
    }
}
~~~

Ví dụ giả định **adapter đã tạo header có tên `X-Route-Region` và kiểu `String`** theo đúng hợp đồng. Khi Kafka gửi bytes, adapter phải decode trước bước này; nếu chưa decode, policy cố ý đưa message vào `INVALID` thay vì ép kiểu mù quáng. Khi adapter của bạn dùng tên `region`, hãy **sửa mapping ở biên** để cùng đưa vào tên nguồn đã thống nhất, hoặc thiết kế policy đọc một field nội bộ thống nhất.

Các lựa chọn cố ý:

- `null` được phân loại thành `MISSING`.
- Sai kiểu runtime, chuỗi trắng hoặc giá trị trống được phân loại thành `INVALID`.
- Giá trị đúng kiểu nhưng chưa hỗ trợ như `DE` được phân loại thành `UNSUPPORTED`.
- `VN` và `US` được chuẩn hóa uppercase, kể cả khi client gửi `" vn "`.
- `setHeader("routeKey", ...)` **ghi đè** giá trị `routeKey` có thể đã được đưa vào từ bên ngoài; không cho raw client quyết định route nội bộ.
- Header nguồn được gỡ khỏi message sau khi xử lý để consumer không vô tình sử dụng giá trị chưa kiểm tra. Nếu cần điều tra, lưu metadata hạn chế trong audit system phù hợp chứ không log payload tùy tiện.

Giới hạn ví dụ: lớp này chỉ kiểm tra **giá trị routing hint**; nó không xác thực quyền truy cập thị trường, tenant, bản chất payload hay chữ ký request. Những kiểm tra đó thuộc authentication/authorization và business validation ở tầng phù hợp.

## 9. Ghép Header Policy với Router trong Spring Integration Java DSL

Tạo bean cho policy và flow. Ví dụ dùng SpEL để đọc **một header nội bộ**: cách viết này là một expression router có hành vi **header-based routing**. Nếu chỉ cần một header, có thể thay bằng `HeaderValueRouter` chuyên dụng.

~~~java
@Configuration
@EnableIntegration
class HeaderRoutingFlows {

    @Bean
    InboundHeaderPolicy inboundHeaderPolicy() {
        return new InboundHeaderPolicy();
    }

    @Bean
    IntegrationFlow routeOrdersByHeader(InboundHeaderPolicy policy) {
        return IntegrationFlow.from("orders.headers.raw")
            .transform(policy, "normalize")
            .route("headers['routeKey']",
                r -> r.channelMapping("VN", "orders.vn")
                      .channelMapping("US", "orders.us")
                      .channelMapping("MISSING", "orders.route.missing")
                      .channelMapping("INVALID", "orders.route.invalid")
                      .channelMapping("UNSUPPORTED", "orders.route.unsupported")
                      .defaultOutputChannel("orders.route.unclassified"))
            .get();
    }
}
~~~

Các import thường dùng được lược bỏ. Trong ứng dụng thật, cần cấu hình adapter để các nguồn đẩy message đã decode vào `orders.headers.raw`, đồng thời đăng ký consumer thực cho từng channel kết quả.

Với input `OrderCommand("O-101", 2)` và header `X-Route-Region = " vn "`, policy sẽ gắn `routeKey = "VN"`, rồi Router đưa message tới `orders.vn`. Payload vẫn là `OrderCommand`: bước chuẩn hóa ở đây chủ yếu thay đổi **headers**, không phải business data. Handler ở `orders.vn` có thể gọi use case, ghi dữ liệu hoặc gửi outbound message theo mục đích nghiệp vụ.

**Quan trọng:** `defaultOutputChannel` không được dùng như cách duy nhất để xử lý tất cả lỗi. Nếu policy ném exception hoặc Router không đánh giá được expression, flow đồng bộ có thể báo lỗi về caller; flow bất đồng bộ cần error handling riêng. Default dùng khi có key/đích không được giải quyết theo chính sách router, không phải `catch` cho mọi lỗi runtime.

### Nếu chỉ cần HeaderValueRouter

`HeaderValueRouter` được thiết kế riêng cho lựa chọn dựa trên **một tên header**. Ở mức ý tưởng, ta cấu hình `headerName = "routeKey"`, rồi tạo mappings `VN → orders.vn`, `US → orders.us` cùng default. Không cần tự viết một expression SpEL dài để lấy header đó.

~~~java
HeaderValueRouter router = new HeaderValueRouter("routeKey");
router.setChannelMapping("VN", "orders.vn");
router.setChannelMapping("US", "orders.us");
// Trong ứng dụng, bổ sung mapping cho MISSING/INVALID/UNSUPPORTED,
// cấu hình default và gắn router vào một endpoint/flow duy nhất.
~~~

Khi triển khai, chọn một trong hai biến thể Java DSL hoặc `HeaderValueRouter` trực tiếp; tránh gắn hai Router nối tiếp chỉ vì cùng muốn quyết định theo `routeKey`. Khác biệt quan trọng ở đây không nằm ở cú pháp Router, mà ở **kỷ luật mapping và chuẩn hóa header trước khi route**.

## 10. Vì sao không lấy header client làm routing key trực tiếp?

Một header có thể đến từ đối tượng không đáng tin cậy, bị sửa trên proxy, thiếu sau khi đi qua broker hoặc mang kiểu không mong đợi. Không kiểm soát nguồn sẽ gây ít nhất bốn rủi ro:

| Rủi ro | Ví dụ | Kiểm soát |
|---|---|---|
| **Spoofing** | Client gửi `X-Tenant-Id=admin` | Suy tenant từ identity đã xác thực, không chỉ tin header |
| **Route injection** | Input cung cấp tên `orders.privileged` | Mapping từ tập key whitelist, không phân giải channel theo input tự do |
| **Type confusion** | `routeKey` là bytes/map thay vì String | Decode/type validation trước Router |
| **Untrusted metadata propagation** | Copy token hoặc thông tin phân quyền qua mọi hop | Filter header nhạy cảm và xác định outbound mapping |

Ngay cả khi một giá trị thuộc tập cho phép, **nó vẫn có thể không được phép đối với người gửi hiện tại**. Ví dụ `routeKey="US"` là giá trị hợp lệ về cú pháp nhưng người dùng chỉ được thao tác ở VN. Quyết định authorization phải dựa trên thông tin được xác minh, không được bỏ qua vì Router đã map thành công.

Tránh chấp nhận header `spring_replyChannel`, `errorChannel`, correlation, tracing hay các metadata điều khiển flow dưới dạng input không kiểm soát. Những header có ý nghĩa điều phối có thể dẫn tới phản hồi sai nơi hoặc làm rối quá trình xử lý lỗi nếu bị ghi đè bừa bãi.

Nếu sử dụng SpEL để route, **không tạo expression từ chuỗi người dùng gửi**. Expression là cấu hình của ứng dụng; dữ liệu bên ngoài chỉ đóng vai trò giá trị được kiểm tra, không được dùng để sinh mã thực thi.

## 11. Header bị thiếu, sai kiểu, trùng hoặc có nhiều giá trị

Các trường hợp sau cần hành vi xác định:

| Input sau inbound mapper | Kết quả policy mẫu | Điều cần lưu ý |
|---|---|---|
| Không có `X-Route-Region` | `MISSING` | Không coi là `VN` hoặc default an toàn nếu chưa có quy tắc |
| `null` | `MISSING` | `MessageHeaders` thường không lưu giá trị null; kiểm tra ở biên |
| `" "` | `INVALID` | Blank khác với unknown market |
| `byte[]` chưa decode | `INVALID` | Không ép kiểu thành String |
| `" vn "` | `VN` | Trim + uppercase theo Locale.ROOT |
| `"US"` | `US` | Route có hỗ trợ |
| `"DE"` | `UNSUPPORTED` | Khác lỗi parse; có thể thêm nhánh trong tương lai |
| Header có danh sách nhiều giá trị | `INVALID` nếu không phải String | Adapter cần chính sách đa giá trị tường minh |
| Nhiều header cùng tên ở Kafka | Tùy mapper/adapter | Xác định chọn giá trị cuối, đầu, hoặc reject; không đoán |

**Đừng vô tình cho phép “giá trị cuối thắng”** đối với header ảnh hưởng phân quyền hoặc dữ liệu nghiệp vụ nếu producer được phép gửi lặp. Đặc biệt khi đi qua reverse proxy, HTTP header case-insensitive và có thể bị gộp theo quy tắc riêng. Nên có contract test cho nhiều giá trị và các biến thể tên.

Một policy thực tế có thể trả đối tượng `HeaderValidationResult(status, routeKey, reasonCode)`, thay vì chỉ String. Khi đó, Transformer ghi lại status vào header riêng hoặc đưa message vào rejection channel để phân biệt missing, wrong type, malformed và forbidden.

## 12. HeaderMapper inbound và outbound không đối xứng mặc định

Một cấu hình chọn inbound headers không chứng minh outbound adapter sẽ phát chính những headers ấy. Với nhiều giao thức, hai chiều cần chính sách riêng:

~~~text
HTTP / Kafka / AMQP inbound
    └── HeaderMapper IN: cho phép một số native headers
         └── Validation / normalization
              └── Internal flow: routeKey, trace context, eventId
                   └── Outbound adapter
                        └── HeaderMapper OUT: chỉ phát metadata được phép
~~~

Ví dụ `routeKey` là header điều phối **nội bộ**; nếu downstream service không cần nó, không nên gửi ra HTTP response hoặc broker event. Ngược lại, `eventId` hoặc trace context có thể cần phát qua broker để duy trì idempotency/tracing và phải được ghi rõ trong hợp đồng wire format.

Nếu một adapter outbound mặc định map toàn bộ `MessageHeaders`, có nguy cơ lộ thông tin điều phối, request context, class name, hoặc dữ liệu nhạy cảm. Hãy xác định danh sách outbound header và kiểu được serialize; kiểm thử message thực tế trên wire, không chỉ kiểm tra Spring message trong bộ nhớ.

## 13. Correlation và các EIP khác khi qua header mapping

Một flow có thể gồm **Gateway → Splitter → Router → Aggregator**. Ở đây `correlationId`, `sequenceNumber` và `sequenceSize` có ý nghĩa điều phối nhóm. Header mapping sai có thể làm message con bị gom nhầm hoặc không được giải phóng.

~~~mermaid
flowchart LR
    G["Gateway: Order O-101"] --> S["Splitter"]
    S --> L1["Line 1 + correlation"]
    S --> L2["Line 2 + correlation"]
    L1 --> HM["Header mapping / normalization"]
    L2 --> HM
    HM --> R{"Header Router: warehouse"}
    R --> A["Warehouse A"]
    R --> B["Warehouse B"]
    A --> AG["Aggregator: correlation O-101"]
    B --> AG
    AG --> RES["OrderSummary"]
~~~

Nếu chuyển message qua broker giữa Router và Aggregator:

1. Kiểm tra header mapper có truyền đúng **correlation key** và metadata sequence cần thiết không.
2. Không dùng một `correlationId` do người dùng tự chọn làm khóa duy nhất của nhóm nếu chưa xác minh quyền/nguồn.
3. Nếu một line bị reject do header mapping hoặc unsupported route, thiết kế **failure result**, timeout hoặc release strategy thay vì chờ đủ nhóm mãi mãi.
4. Khi có redelivery, dùng event/line ID ổn định để tránh tính một kết quả hai lần; `MessageHeaders.ID` mới không đảm bảo chống trùng.

Router theo header cũng có thể kết hợp **Filter** để bỏ các message không đạt điều kiện, **Transformer** để dựng metadata nội bộ và **Gateway** để nhận kết quả. Mỗi pattern có một trách nhiệm: HeaderMapper ở biên giao thức, Router chọn nhánh, business handler xử lý lệnh, Aggregator gom kết quả theo correlation.

## 14. Phân biệt fallback, rejection, exception và retry

Không phải mọi trường hợp không đến nhánh VN/US đều là một lỗi như nhau:

| Trường hợp | Tuyến xử lý phù hợp | Có nên retry? |
|---|---|---|
| Thiếu header region | `orders.route.missing` | Thường không, trừ khi nguồn dữ liệu sẽ được bổ sung có chủ đích |
| Header sai kiểu/blank | `orders.route.invalid` | Thường không; sửa mapping/producer |
| Region có giá trị mới chưa hỗ trợ | `orders.route.unsupported` | Không retry mù; có quy trình phân loại |
| Router không tìm được channel | Default route hoặc exception theo config | Sửa cấu hình hoặc bổ sung consumer |
| Mapper/Normalizer ném exception | Error handling theo ngữ cảnh | Tùy lỗi có tạm thời không |
| Downstream tạm mất kết nối database | Handler/retry advice hoặc broker policy | Có thể retry giới hạn + backoff |
| Duplicate do broker phát lại | Idempotency ở service/storage | Không tạo side effect trùng |

**Default output channel** chủ yếu xử lý routing key không có tuyến phù hợp, không tự bắt lỗi deserialize, lỗi type cast, expression exception hoặc lỗi handler. Với `DirectChannel`, ngoại lệ có thể lan ngược caller; với `ExecutorChannel` hoặc polling consumer, error path phải được cấu hình theo cơ chế bất đồng bộ tương ứng.

Nếu outbound adapter thất bại **sau khi nghiệp vụ đã commit**, retry có thể làm cùng nghiệp vụ chạy lại. Dùng idempotency key, transaction/outbox hoặc thiết kế bù trừ thích hợp tùy hệ thống. Không nhầm việc channel chấp nhận message với việc downstream đã xử lý thành công.

## 15. Kiểm thử unit cho header mapping policy

Kiểm tra bảng giá trị ngay tại policy giúp tách lỗi normalization khỏi lỗi Router:

~~~java
@Test
void normalizesAndClassifiesRegion() {
    InboundHeaderPolicy policy = new InboundHeaderPolicy();

    assertEquals("VN", policy.toRouteKey(" vn "));
    assertEquals("US", policy.toRouteKey("US"));
    assertEquals("MISSING", policy.toRouteKey(null));
    assertEquals("INVALID", policy.toRouteKey(" "));
    assertEquals("INVALID", policy.toRouteKey(new byte[] {86, 78}));
    assertEquals("UNSUPPORTED", policy.toRouteKey("DE"));
}

@Test
void overwritesUntrustedRouteKey() {
    InboundHeaderPolicy policy = new InboundHeaderPolicy();
    Message<OrderCommand> inbound = MessageBuilder
        .withPayload(new OrderCommand("O-101", 2))
        .setHeader("X-Route-Region", " vn ")
        .setHeader("routeKey", "orders.privileged")
        .build();

    Message<?> normalized = policy.normalize(inbound);

    assertEquals("VN", normalized.getHeaders().get("routeKey"));
    assertNull(normalized.getHeaders().get("X-Route-Region"));
    assertEquals("O-101",
        ((OrderCommand) normalized.getPayload()).orderId());
}
~~~

Ví dụ dùng JUnit 5 và các kiểu được định nghĩa ở trên. Unit test này chưa chứng minh HTTP/Kafka header thực sự đến đúng key; nó chỉ xác minh policy với **Spring message đã có header**.

## 16. Integration test cho luồng header → channel

Trong test context, thay các consumer production của `orders.vn`, `orders.us` và các rejection channel bằng những `QueueChannel` để kiểm tra message nhận được. Đừng vừa khai báo queue test vừa chạy consumer production có cùng tên.

Ví dụ phần thân test khi context đã có flow và các channel đích test:

~~~java
@Autowired
ApplicationContext context;

@Test
void routesMappedHeaderToVietnam() {
    MessageChannel input = context.getBean(
        "orders.headers.raw", MessageChannel.class);
    PollableChannel vn = context.getBean(
        "orders.vn", PollableChannel.class);
    PollableChannel us = context.getBean(
        "orders.us", PollableChannel.class);

    Message<OrderCommand> order = MessageBuilder
        .withPayload(new OrderCommand("O-501", 3))
        .setHeader("X-Route-Region", " vn ")
        .build();

    assertTrue(input.send(order));
    Message<?> routed = vn.receive(1000);

    assertNotNull(routed);
    assertEquals("VN", routed.getHeaders().get("routeKey"));
    assertEquals("O-501",
        ((OrderCommand) routed.getPayload()).orderId());
    assertNull(us.receive(0));
}
~~~

Kiểm thử thêm các tình huống:

| Test | Input | Kết quả mong đợi |
|---|---|---|
| HTTP header hợp lệ | `X-Route-Region: vn` | Mapper đưa vào đúng kiểu, Router đến `orders.vn` |
| Kafka header UTF-8 | Bytes của `"US"` | Adapter decode thành String, route `orders.us` |
| Raw Kafka bytes chưa decode | `byte[]` trong Spring header | Policy đưa `INVALID`, không tự cast |
| Thiếu header | Không có giá trị | `orders.route.missing` |
| Header blank | `" "` | `orders.route.invalid` |
| Region chưa hỗ trợ | `"DE"` | `orders.route.unsupported` |
| Header bị giả mạo | Có sẵn `routeKey=orders.admin` | Policy ghi đè; không chuyển tới channel ngoài whitelist |
| HTTP multi-value | Hai region khác nhau | Xử lý theo chính sách multi-value, không ngầm chọn |
| Wrong payload | Không phải `OrderCommand` | Payload/schema gate hoặc consumer xử lý lỗi đúng policy |
| Downstream lỗi | Service ném exception | Quan sát error path; không coi là lỗi header mapping |
| Correlation xuyên broker | Splitter → adapter → Aggregator | Header cần thiết không mất, không gộp nhầm |

**Thử cả ở wire boundary.** Với HTTP, tạo request thật trong integration test và kiểm tra Spring message sau mapper. Với Kafka/AMQP, kiểm tra dữ liệu nhận từ broker/client test và kiểu của từng header sau mapping. Nếu chỉ mock sẵn `MessageHeaders`, bạn có thể bỏ sót lỗi bytes/string hoặc đổi tên header do adapter.

## 17. Observability: đo được message đi nhánh nào

Mỗi điểm trong pipeline nên có dữ liệu quan sát đủ để chẩn đoán:

- **Inbound adapter:** tỉ lệ decode thành công/thất bại, loại transport, schema/mapper version.
- **Header mapper:** header nào được chấp nhận, số message thiếu header bắt buộc, lỗi type conversion.
- **Normalization:** số lượng `MISSING`, `INVALID`, `UNSUPPORTED`; không đưa giá trị header tùy ý làm metric label.
- **Router:** số message theo `VN`, `US` và các nhánh từ chối; số lần default route.
- **Consumer:** độ trễ p95/p99, retry, lỗi, backlog nếu có queue.
- **Correlation/tracing:** event ID và trace context được chọn lọc; tránh log token, cookie, payload nhạy cảm.

Khi tìm lỗi “message không đến đúng nhánh”, hãy kiểm tra theo thứ tự: **native header trên wire → inbound mapper → tên/kiểu Spring header → normalization result → routing key → channel mapping → consumer đích → error path**.

Nếu dùng Micrometer/observation trong Spring Integration, cấu hình tên endpoint/channel nhất quán và giữ cardinality metric ở mức thấp. Cần có chủ sở hữu cho các rejection channel để tránh message bị nhận nhưng không được xử lý tiếp.

## 18. Bài thực hành: thêm Kafka mà không sửa Header Router

Thực hiện một flow xử lý đơn hàng:

1. **Công bố hợp đồng:** `OrderCommand`, raw header `X-Route-Region` và header nội bộ `routeKey` với các giá trị cho phép.
2. **HTTP inbound:** cấu hình `DefaultHttpHeaderMapper` cho đúng một số request headers cần thiết, gắn mapper vào adapter.
3. **Header policy:** viết `InboundHeaderPolicy` để phân loại null, sai kiểu, blank, unsupported và chuẩn hóa uppercase.
4. **Header Router:** ánh xạ `VN → orders.vn`, `US → orders.us` cùng các rejection routes.
5. **Kafka inbound:** parse payload, decode Kafka record header theo contract rồi đưa vào cùng channel `orders.headers.raw`. Không sửa logic chọn route ở downstream.
6. **Lỗi và recovery:** thêm consumer có chủ sở hữu cho rejection channels; phân biệt lỗi mapping không retry với lỗi downstream tạm thời có thể retry.
7. **Test:** unit test policy; flow test từng nhánh; HTTP/Kafka contract test header types, multi-value và header giả mạo.
8. **Mở rộng:** dùng Splitter/Aggregator và kiểm tra correlation khi message qua broker; quan sát backlog, timeout và kết quả nhóm thiếu thành viên.

**Tiêu chí hoàn thành:** cùng giá trị region hợp lệ tạo cùng routing key và nhánh đích dù đến từ HTTP hay Kafka; missing/wrong type không lọt vào nhánh nghiệp vụ; channel name không phụ thuộc trực tiếp input không tin cậy; header mapping outbound không lộ metadata thừa; trace/correlation giữ được khi cần; mọi lỗi có đường xử lý và được kiểm thử.

## 19. Ghi nhớ

**Header mapper trước khi route** là nguyên tắc giữ ranh giới rõ ràng: **native headers → Spring MessageHeaders → validate/normalize → routing key nội bộ → Header Router**. HeaderMapper giải quyết giao thức và kiểu dữ liệu, HeaderEnricher/Transformer giải quyết việc chuẩn hóa và bổ sung metadata, Router quyết định kênh nhận.

Không tin header do producer/client gửi chỉ vì nó tồn tại; không nhầm fallback với error channel; không quên mapping outbound và correlation khi flow đi qua broker. Khi thiết kế theo cách này, Spring Integration có thể mở rộng thêm HTTP, Kafka, AMQP hoặc nguồn theo lịch mà vẫn giữ quy tắc định tuyến ổn định, dễ kiểm thử và quan sát.
