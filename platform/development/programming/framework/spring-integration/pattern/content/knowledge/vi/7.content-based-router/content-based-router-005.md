# Route khi dữ liệu thiếu hoặc sai kiểu

## 1. Vì sao Content-Based Router cần phòng vệ ở đầu vào?

**Content-Based Router (CBR)** trong Enterprise Integration Patterns quyết định channel đích dựa trên nội dung thông điệp. Ví dụ, một đơn hàng có `region = "VN"` được gửi tới `orders.vn`, đơn có `region = "US"` tới `orders.us`. Khi dữ liệu luôn đúng định dạng, việc viết Router rất đơn giản. Nhưng trong hệ thống tích hợp thực tế, message có thể:

- Có đúng kiểu payload nhưng thiếu `orderId`, `region`, `quantity` hoặc header bắt buộc.
- Chứa trường có giá trị `null`, chuỗi rỗng, sai miền giá trị hoặc không được hỗ trợ.
- Mang một payload khác hẳn loại mà flow mong đợi, chẳng hạn `String` hoặc `byte[]` thay vì `IncomingOrderV1`.
- Có JSON sai cú pháp, thiếu trường trong schema, hoặc không thể deserialize.
- Có kiểu dữ liệu đúng và hợp lệ nhưng routing key chưa được cấu hình, ví dụ một thị trường mới.
- Khiến biểu thức SpEL ném ngoại lệ trước khi có thể xác định channel đích.

**Vấn đề cốt lõi:** “không route được” không phải một loại lỗi duy nhất. Nếu đưa tất cả tình huống vào một default channel, hệ thống có thể xử lý nhầm dữ liệu sai; nếu để exception lọt ra ngoài không có chính sách, message có thể bị retry vô hạn hoặc mất dấu.

Bài này thuộc chương **Content-based router** của module **SPRING_INTEGRATION_PATTERN**. Nội dung giúp xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng bằng Spring Integration, kết hợp **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry, error channel và correlation**. Mục tiêu là xác định đúng nhánh xử lý, nêu rõ hợp đồng đầu vào và kiểm thử được cả đường đi dữ liệu hỏng.

Sau bài học, bạn có thể thiết kế CBR an toàn trước dữ liệu thiếu/sai kiểu, phân biệt fallback với error channel, giữ lại ngữ cảnh truy vết và xây ma trận kiểm thử cho từng trường hợp.

## 2. Phân loại lỗi trước khi chọn một route

Hãy phân biệt ít nhất sáu trạng thái dưới đây:

| Trạng thái | Ví dụ | Có message vào Spring Integration chưa? | Đường xử lý gợi ý |
|---|---|---|---|
| **Sai wire format** | JSON bị cắt, thiếu dấu ngoặc | Chưa chắc: lỗi có thể xảy ra ở adapter/decoder | Phân loại lỗi deserialize tại ingress; quarantine hoặc từ chối |
| **Sai kiểu payload runtime** | `String` thay `IncomingOrderV1` | Có, nếu adapter đã phát message chứa String | Type gate → `orders.rejected.type` |
| **Thiếu trường bắt buộc** | `quantity = null` | Có, nếu DTO được tạo/parse | Validation → `orders.rejected.missing` |
| **Giá trị sai quy tắc** | `quantity = -2`, `region = " "` | Có | Filter/validator → `orders.rejected.value` |
| **Version không tương thích** | `schemaVersion = 3` nhưng chỉ hỗ trợ v1 | Có, nếu decode được DTO | Version gate → `orders.rejected.version` |
| **Đúng dữ liệu nhưng chưa có nhánh** | `region = "DE"`, chỉ có VN và US | Có | Router → `orders.unmapped` theo chính sách |

Thêm một trạng thái riêng: **lỗi đánh giá Router** như gọi `payload.region()` trên payload sai kiểu, hoặc gọi phương thức trên `null`. Đây là **exception thực thi**, không phải một routing key mới; chỉ định `defaultOutputChannel` không tự biến exception thành “unknown”.

Thông điệp Spring thường yêu cầu payload khác `null`. Khi nói “payload thiếu dữ liệu” trong bài, ta thường nói đến **trường bên trong payload** bị thiếu hoặc một metadata header không tồn tại; đừng gửi `null` để biểu diễn một sự kiện hợp lệ.

## 3. Thiết kế pipeline phòng vệ nhiều tầng

Không ép một Expression Router duy nhất giải quyết mọi việc. Một pipeline hợp lý là:

~~~mermaid
flowchart TD
    A["HTTP / broker / file input"] --> D{"Decode & schema"}
    D -->|"Không parse được"| PD["Ingress error / quarantine"]
    D -->|"Parse được"| M["orders.raw: Message<?>"]
    M --> T{"Type & version gate"}
    T -->|"Sai kiểu"| BT["orders.rejected.type"]
    T -->|"Version lạ"| BV["orders.rejected.version"]
    T -->|"Thiếu field"| BM["orders.rejected.missing"]
    T -->|"Sai giá trị"| BI["orders.rejected.value"]
    T -->|"Hợp lệ"| N["Transformer: normalized Order"]
    N --> R{"Content-Based Router: region"}
    R -->|"VN"| V["orders.vn"]
    R -->|"US"| U["orders.us"]
    R -->|"Không khớp"| O["orders.unmapped"]
    T -.->|"Exception bất ngờ"| ER["Error handling"]
    R -.->|"Exception bất ngờ"| ER
~~~

**Type/validation gate** phát biểu điều kiện tối thiểu để một message có thể bước vào luồng nghiệp vụ. **Transformer** tạo payload có cấu trúc và giá trị ổn định. **CBR** định tuyến theo dữ liệu đã xác nhận. **Consumer** downstream thực hiện nghiệp vụ, thay vì kiểm tra lại mọi vấn đề của tầng giao thức.

Lợi ích của phân tách:

1. Không gọi phương thức trên một class không phù hợp trong SpEL.
2. Có metric riêng cho lỗi type, missing, value, version và unknown route.
3. Có thể thay HTTP bằng AMQP/Kafka mà giữ logic phân luồng ứng dụng.
4. Kiểm thử từng tầng không cần kích hoạt các external service.

Không có gì bắt buộc mọi luồng phải dùng đúng bốn endpoint này. Với flow nhỏ, một classifier Java thuần có thể vừa kiểm tra trạng thái đầu vào vừa trả routing key; khi phức tạp hơn, tách validation và routing thành các endpoint độc lập để dễ quan sát.

## 4. Hợp đồng dữ liệu: biểu diễn đúng cả trường có thể thiếu

Giả sử adapter đã decode được một bản tin đơn hàng phiên bản 1:

~~~java
public record IncomingOrderV1(
    Integer schemaVersion,
    String eventId,
    String orderId,
    String region,
    Integer quantity
) {}

public record ValidatedOrder(
    String eventId,
    String orderId,
    String region,
    int quantity
) {}
~~~

Dùng `Integer` thay vì `int` tại DTO inbound để còn phân biệt “trường `quantity` không có hoặc được parse thành null” với “giá trị bằng 0”. Sau bước xác minh, `ValidatedOrder` dùng `int` vì không còn cho phép null.

**Lưu ý:** với một số thư viện JSON và cấu hình deserializer, thiếu trường có thể biến thành giá trị mặc định, bị coi là lỗi ngay khi parse hoặc đi qua constructor không thành công. Contract test của adapter phải xác định hành vi này; không mặc định mọi JSON thiếu trường đều trở thành Java `null`.

Một hợp đồng tối thiểu phải nói rõ:

| Thuộc tính | Quy định trong ví dụ | Ý nghĩa |
|---|---|---|
| `schemaVersion` | Bắt buộc, hiện hỗ trợ 1 | Xác định schema có thể xử lý |
| `eventId` | Không null/blank | Nhận diện sự kiện, phục vụ tracing và chống trùng |
| `orderId` | Không null/blank | Định danh đơn hàng |
| `region` | Không null/blank, chuẩn hóa chữ hoa | Routing key theo thị trường |
| `quantity` | Khác null, lớn hơn 0 | Số lượng hợp lệ |

Cần phân biệt **schema validation** với **business validation**. Ví dụ, “`quantity` phải là số nguyên” là yêu cầu schema, trong khi “khách hàng này không được mua quá 20 sản phẩm” là quy tắc nghiệp vụ, nên vẫn được bảo vệ tại use case ngay cả khi message đã qua Filter.

## 5. Type gate: kiểm tra runtime type trước khi gọi thuộc tính payload

Một Router sử dụng Java function có thể xác định nhánh theo kiểu payload và kiểm tra trường trước khi chuyển tiếp. Việc kiểm tra `instanceof` không đòi parser phải thử gọi method trên một đối tượng không đúng loại.

Đầu tiên, định nghĩa classifier thuần Java. Kết quả là **routing key cố định** chứ không phải tên channel do client cung cấp:

~~~java
public final class IngressClassifier {

    public String classify(Object payload) {
        if (!(payload instanceof IncomingOrderV1 order)) {
            return "WRONG_TYPE";
        }
        if (order.schemaVersion() == null) {
            return "MISSING_FIELD";
        }
        if (order.schemaVersion() != 1) {
            return "UNSUPPORTED_VERSION";
        }
        if (order.eventId() == null
                || order.orderId() == null
                || order.region() == null
                || order.quantity() == null) {
            return "MISSING_FIELD";
        }
        if (order.eventId().isBlank()
                || order.orderId().isBlank()
                || order.region().isBlank()
                || order.quantity() <= 0) {
            return "INVALID_VALUE";
        }
        return "VALID";
    }
}
~~~

Thứ tự kiểm tra có chủ đích: **đúng kiểu → version → trường bắt buộc → giá trị hợp lệ**. Trường hợp `IncomingOrderV1` có `schemaVersion = null` được phân loại thiếu field thay vì “version lạ”. Chọn độ ưu tiên nhất quán giúp test ổn định và metric có thể so sánh theo thời gian.

`classify(Object)` không ghi database, không gửi HTTP, không ném exception cho các tình huống dữ liệu đã dự kiến. Nó là một hàm dễ unit test và tái sử dụng dù đầu vào đến từ Gateway, queue hay broker adapter.

## 6. Cấu hình Content-Based Router với Java DSL

Đặt classifier vào Spring Integration Router, rồi ánh xạ từng key sang channel có tên cụ thể. Luồng thứ hai chỉ nhận message đã qua gate và biến đổi kiểu dữ liệu trước khi chọn thị trường.

~~~java
@Configuration
@EnableIntegration
public class DefensiveOrderRouting {

    @Bean
    IngressClassifier ingressClassifier() {
        return new IngressClassifier();
    }

    @Bean
    IntegrationFlow ingressGate(IngressClassifier classifier) {
        return IntegrationFlow.from("orders.raw")
            .route(Object.class, classifier::classify, r -> r
                .channelMapping("VALID", "orders.accepted")
                .channelMapping("WRONG_TYPE", "orders.rejected.type")
                .channelMapping("MISSING_FIELD", "orders.rejected.missing")
                .channelMapping("INVALID_VALUE", "orders.rejected.value")
                .channelMapping("UNSUPPORTED_VERSION", "orders.rejected.version")
                .defaultOutputChannel("orders.rejected.unclassified"))
            .get();
    }

    @Bean
    IntegrationFlow routeAcceptedOrders() {
        return IntegrationFlow.from("orders.accepted")
            .transform(IncomingOrderV1.class,
                order -> new ValidatedOrder(
                    order.eventId(),
                    order.orderId(),
                    order.region().trim().toUpperCase(Locale.ROOT),
                    order.quantity()))
            .route(ValidatedOrder.class, ValidatedOrder::region,
                r -> r.channelMapping("VN", "orders.vn")
                      .channelMapping("US", "orders.us")
                      .defaultOutputChannel("orders.unmapped"))
            .get();
    }
}
~~~

Ví dụ dùng Java 17+ cho pattern matching `instanceof` và record, cùng Spring Integration Java DSL. Các import được lược bỏ. **Các channel đầu ra phải có consumer thực sự** (Service Activator, outbound adapter hoặc test receiver); mã trên cố ý tách trách nhiệm phân loại khỏi công việc nghiệp vụ của từng nhánh.

Các channel `orders.rejected.*` nên có handler ghi nhận mã lỗi, nguồn gửi, event ID nếu có, rồi thực hiện chính sách reject/quarantine. Không log nguyên payload khi có thông tin nhạy cảm.

**Điểm cần lưu ý về ánh xạ channel:** các phiên bản và cấu hình Spring Integration có thể hỗ trợ phân giải routing key trực tiếp thành tên channel bên cạnh mapping đã khai báo. Do đó, **không coi `channelMapping` là hàng rào bảo mật duy nhất**. Chỉ trả về key thuộc một tập cố định, chủ động cấu hình chính sách giải quyết channel key/fallback tương thích phiên bản đang dùng, và kiểm thử rằng một giá trị từ bên ngoài không thể điều hướng sang channel tùy ý.

### Kết quả dự kiến của classifier

| Input payload | Routing key đầu tiên | Channel đầu tiên | Route tiếp theo |
|---|---|---|---|
| `IncomingOrderV1(1, "E1", "O1", " vn ", 2)` | `VALID` | `orders.accepted` | `orders.vn` |
| `IncomingOrderV1(1, "E2", "O2", "US", 1)` | `VALID` | `orders.accepted` | `orders.us` |
| `IncomingOrderV1(1, "E3", "O3", "DE", 4)` | `VALID` | `orders.accepted` | `orders.unmapped` |
| `"hello"` | `WRONG_TYPE` | `orders.rejected.type` | Không xử lý đơn |
| `IncomingOrderV1(1, "E4", "O4", null, 3)` | `MISSING_FIELD` | `orders.rejected.missing` | Không gọi Transformer |
| `IncomingOrderV1(1, "E5", "O5", "VN", -1)` | `INVALID_VALUE` | `orders.rejected.value` | Không xử lý đơn |
| `IncomingOrderV1(2, "E6", "O6", "VN", 1)` | `UNSUPPORTED_VERSION` | `orders.rejected.version` | Chuyển hợp đồng version mới |

Các bản tin còn đúng kiểu nhưng thiếu `region` **không** được đưa vào `orders.unmapped`: vùng chưa biết khác hoàn toàn với trường bị thiếu.

## 7. Khi nào dùng Filter thay cho classifier Router?

**Filter EIP** trả lời câu hỏi “message này có được tiếp tục không?”, còn **Content-Based Router** trả lời “message được gửi tới đường nào?”. Có thể dùng Filter trước Router khi chỉ có hai trường hợp **chấp nhận** hoặc **loại**, ví dụ:

~~~java
IntegrationFlow.from("orders.parsed")
    .filter(IncomingOrderV1.class,
        order -> order.orderId() != null
            && !order.orderId().isBlank()
            && order.quantity() != null
            && order.quantity() > 0,
        f -> f.discardChannel("orders.rejected"))
    .transform(IncomingOrderV1.class,
        order -> new ValidatedOrder(
            order.eventId(), order.orderId(),
            order.region(), order.quantity()))
    .route(ValidatedOrder.class, ValidatedOrder::region,
        r -> r.channelMapping("VN", "orders.vn")
              .defaultOutputChannel("orders.other"))
    .get();
~~~

**Đây là đoạn minh họa lựa chọn Filter, không phải mã tương đương đầy đủ với gate nhiều nhánh ở mục 6.** Trong hệ thống thật, cần thêm validation cho `eventId` và `region` trước khi Transformer/Router dùng các trường đó. Nếu yêu cầu có báo lỗi riêng theo từng nguyên nhân (sai kiểu, thiếu field, version mới…), classifier nhiều nhánh phù hợp hơn.

Tương tự, dùng `discardChannel` để đẩy message bị Filter loại **không** đồng nghĩa với `errorChannel`. Message không đạt predicate là kết quả dự kiến; exception do lỗi runtime là trường hợp cần error handling.

## 8. Biểu thức SpEL khi header hoặc trường có thể thiếu

Với một Router dựa trên SpEL, hãy xem kỹ sự khác biệt giữa:

~~~text
headers['riskLevel']
headers['riskLevel'] == null ? 'UNKNOWN' : headers['riskLevel']
headers['riskLevel'] == 'HIGH' ? 'REVIEW' : 'AUTO'
~~~

Biểu thức thứ ba có thể đưa **header thiếu** vào nhánh `AUTO`. Nếu `AUTO` là nhánh miễn kiểm duyệt, đó là quyết định nguy hiểm. Thay vào đó, biểu thức thứ hai trả key `UNKNOWN` để xử lý riêng.

Ví dụ flow route theo header:

~~~java
@Bean
IntegrationFlow riskByHeader() {
    return IntegrationFlow.from("orders.risk.in")
        .route(
            "headers['riskLevel'] == null ? 'UNKNOWN' : headers['riskLevel']",
            r -> r.channelMapping("HIGH", "orders.review")
                  .channelMapping("LOW", "orders.auto")
                  .channelMapping("UNKNOWN", "orders.risk.missing")
                  .defaultOutputChannel("orders.risk.unsupported"))
        .get();
}
~~~

Nếu header có giá trị `" "` hoặc `"MEDIUM"`, đây không phải `null`; message sẽ đến nhánh chưa hỗ trợ theo mapping hiện tại (nếu cấu hình fallback hoạt động như dự kiến). Có thể đặt thêm bước kiểm tra/chuẩn hóa header để phân biệt blank với giá trị không được công bố.

Đối với payload là record, `payload.region()` truy cập phương thức accessor. Nếu trước đó Transformer thay kiểu payload thành `String`, gọi phương thức này sẽ thất bại. Một expression với toán tử null-safe có thể giúp trường hợp **một thuộc tính null**, nhưng không thay được kiểm tra **kiểu payload**. Hãy dùng type gate trước Router thay vì tìm cách viết một biểu thức SpEL khổng lồ tự ứng phó mọi kiểu dữ liệu.

**An toàn:** không ghép nguyên dữ liệu do người dùng cung cấp thành chuỗi SpEL để đánh giá. Dùng biểu thức cố định do ứng dụng quản lý; payload/header chỉ cung cấp **giá trị**, không cung cấp mã biểu thức hoặc tên channel tùy ý.

## 9. Default output channel không phải error channel

Đây là ranh giới quan trọng nhất khi dữ liệu có vấn đề:

| Tình huống | Default output channel có giải quyết không? | Tại sao? |
|---|---|---|
| Routing key hợp lệ nhưng không nằm trong các tuyến mong đợi | **Có, khi Router đã được cấu hình phù hợp** | Router tính được key nhưng không có đích phù hợp |
| Header có giá trị `UNKNOWN` được classifier trả về | **Có thể** | Key có thể được map riêng hoặc qua default |
| Biểu thức gọi method không tồn tại trên payload | **Không** | Lỗi trong lúc đánh giá, chưa có routing key |
| JSON không parse được ở inbound adapter | **Không** | Message chưa tới Router |
| Handler ở channel đích ném exception | **Không** | Router đã chuyển message tới đích |
| Queue đích đầy hoặc channel không có subscriber | **Không nhất thiết** | Lỗi gửi/delivery khác với key chưa được ánh xạ |

Nếu Router không phân giải được channel, điều gì xảy ra còn phụ thuộc các tùy chọn resolution/fallback. Khi xử lý giao dịch quan trọng, luôn thiết kế một tuyến dự phòng hoặc exception rõ ràng và test hành vi trên phiên bản Spring Integration cụ thể.

**Error channel** dùng cho luồng xử lý lỗi của một số endpoint/adapter, đặc biệt trong kịch bản bất đồng bộ. Trong một flow đồng bộ qua `DirectChannel`, exception thường có thể truyền ngược tới caller/Gateway. Không mặc định cứ đặt tên `errorChannel` là mọi exception trong mọi thread đều tới đó.

## 10. Đặt ranh giới lỗi parse bên ngoài Router

Giả sử HTTP hoặc broker gửi:

~~~json
{
  "schemaVersion": 1,
  "eventId": "E-100",
  "orderId": "O-100",
  "region": "VN",
  "quantity": "abc"
}
~~~

Nếu schema yêu cầu `quantity` là số nguyên, JSON có thể hợp lệ về mặt cú pháp nhưng **không phù hợp contract**. Tùy Jackson và cấu hình coercion, deserializer có thể ném lỗi hoặc cố chuyển đổi; vì vậy cần test cấu hình thực tế. Không nên đẩy chuỗi `"abc"` vào `Integer` bằng một ép kiểu thủ công trong Router.

Khi dùng adapter tự decode, mã minh họa:

~~~java
public IncomingOrderV1 decode(byte[] json, ObjectMapper mapper)
        throws JsonProcessingException {
    return mapper.readValue(json, IncomingOrderV1.class);
}
~~~

Lời gọi `decode` chạy **trước** khi payload `IncomingOrderV1` được gửi vào `orders.raw`. Nếu lỗi, adapter cần ghi nhận mã lỗi deserialization, tạo phản hồi HTTP phù hợp hoặc áp dụng chính sách ack/reject/DLQ của broker. Chỉ khi decode thành công mới chuyển message sang CBR.

Đối với nguồn không tin cậy, cấu hình giới hạn dung lượng, độ sâu dữ liệu, danh sách kiểu được chấp nhận và tránh dùng polymorphic deserialization tự do. Không để client chọn class hoặc SpEL expression tùy ý. Nên có schema version và kiểm thử tương thích producer/consumer trước khi nâng cấp hợp đồng.

## 11. Khi version, type và missing cùng xuất hiện

Một message có thể đồng thời sai nhiều điều kiện: version lạ, thiếu `region` và có `quantity = -1`. Nếu một Router chỉ trả **một** key, phải xác định quy tắc ưu tiên. Ví dụ classifier ở mục 5 kiểm tra version trước rồi mới kiểm tra các field còn lại.

Có ba cách thiết kế:

1. **Fail-fast một mã lỗi:** lấy lỗi đầu tiên theo thứ tự đã công bố; đơn giản, phù hợp với routing gate.
2. **Tổng hợp nhiều lỗi vào validation result:** trả danh sách lỗi từ một validator; phù hợp khi cần cung cấp phản hồi chi tiết hoặc ghi nhận đầy đủ.
3. **Version-specific decoder/adapter:** tách v1, v2 thành các hợp đồng riêng trước khi tạo model nội bộ thống nhất; phù hợp khi schema khác biệt lớn.

Không nên cố sửa mọi version bằng một `Map<String,Object>` thiếu contract. Ví dụ version 2 đổi nghĩa của `region`; nếu vẫn route bằng cùng biểu thức, message có thể được gửi tới nhánh sai dù không có exception. Lỗi ngữ nghĩa nguy hiểm hơn lỗi kiểu dễ phát hiện.

Hãy xác định rõ khi nào một unknown version có thể đưa vào quy trình tương thích và khi nào phải reject. `defaultOutputChannel` của Router thị trường không phải nơi xử lý version mới.

## 12. Retry, idempotency và chính sách phục hồi

Không phải dữ liệu lỗi nào cũng đáng retry:

| Loại lỗi | Retry? | Hướng xử lý |
|---|---|---|
| JSON sai cú pháp/không thể decode | Thường không | Reject/quarantine, lưu metadata đủ để điều tra |
| Payload sai kiểu do producer gửi sai contract | Thường không | Cảnh báo hợp đồng producer–consumer |
| Thiếu trường bắt buộc | Thường không | Trả mã lỗi schema/validation |
| Unknown version | Tùy quy trình rollout | Chờ adapter hỗ trợ hoặc DLQ/quarantine có quản lý |
| Key hợp lệ nhưng chưa hỗ trợ route | Không retry mù | Default channel có chủ sở hữu, phân loại sau |
| Timeout từ service downstream | Có thể | Retry giới hạn, backoff và circuit breaker khi cần |
| Lỗi mạng tới broker | Có thể | Retry theo adapter, xác nhận delivery và tránh phát trùng |

**Một lần retry có thể chạy lại cả handler.** Nếu handler đã cập nhật database rồi lỗi ở bước gửi reply, retry có thể tạo side effect trùng. Cần dùng **eventId/idempotency key**, ràng buộc unique, transaction/outbox hoặc cơ chế tương đương tùy thiết kế. `MessageHeaders.ID` có thể thay đổi khi message được tạo lại; nó không phải khóa chống trùng nghiệp vụ duy nhất.

Khi error handling nằm trong flow đồng bộ, caller có thể bắt exception. Khi dùng `ExecutorChannel` hoặc `QueueChannel` có poller, error path phải được cấu hình cho ngữ cảnh bất đồng bộ. Với broker, ack/nack, redelivery và DLQ phụ thuộc inbound adapter/container; không tự động áp dụng chỉ vì đã tạo một channel tên “error”.

## 13. Correlation khi Router phân nhánh

Giả sử đơn hàng được tách thành ba dòng bởi Splitter, mỗi dòng đi qua một CBR tới kho khác nhau, rồi Aggregator gộp kết quả. Nếu một dòng có payload thiếu hoặc sai kiểu, cần giải quyết **cả quy trình**, không chỉ message lỗi lẻ:

~~~mermaid
flowchart TD
    O["Order O-101"] --> S["Splitter"]
    S --> L1["Line 1, correlation O-101"]
    S --> L2["Line 2, correlation O-101"]
    S --> L3["Line 3, correlation O-101"]
    L1 --> R["Type/validation gate + Router"]
    L2 --> R
    L3 --> R
    R -->|"Hợp lệ"| W["Warehouse handlers"]
    R -->|"Thiếu dữ liệu"| REJ["Rejected line"]
    W --> A["Aggregator"]
    REJ --> POLICY["Group failure policy"]
    POLICY --> A
~~~

Điều cần xác định trước:

- `correlationId` nào nối các dòng với cùng order; `sequenceNumber` và `sequenceSize` có được giữ qua transformer/adapter hay không.
- Message sai dữ liệu có được quy đổi thành một **failure result** để Aggregator hoàn tất nhóm, hay nhóm cần timeout và trả trạng thái chưa đủ.
- Nếu một dòng bị drop bởi Filter, release strategy sẽ biết nhóm thiếu thành viên thế nào.
- Duplicate/redelivery có làm Aggregator nhận một dòng nhiều lần không; có message store hoặc deduplication thích hợp không.

**Không tự động chờ đủ nhóm mãi mãi** nếu một dòng bị reject. Thiết kế timeout, expired-message handling, bù trừ hoặc báo lỗi nhóm theo yêu cầu nghiệp vụ, cùng đường theo dõi correlation để điều tra.

## 14. Kiểm thử từ classifier đơn vị đến toàn flow

Classifier có thể unit test như Java thuần, không cần Spring Integration:

~~~java
@Test
void classifiesMissingFieldsAndWrongType() {
    IngressClassifier classifier = new IngressClassifier();

    assertEquals("WRONG_TYPE", classifier.classify("not-an-order"));
    assertEquals("MISSING_FIELD", classifier.classify(
        new IncomingOrderV1(1, "E-1", "O-1", null, 2)));
    assertEquals("INVALID_VALUE", classifier.classify(
        new IncomingOrderV1(1, "E-2", "O-2", "VN", 0)));
    assertEquals("UNSUPPORTED_VERSION", classifier.classify(
        new IncomingOrderV1(2, "E-3", "O-3", "VN", 2)));
    assertEquals("VALID", classifier.classify(
        new IncomingOrderV1(1, "E-4", "O-4", " vn ", 2)));
}
~~~

Với integration test, có thể thay consumer production ở các channel đích bằng `QueueChannel` trong **test configuration**. Gửi message tới `orders.raw`, sau đó `receive(timeout)` ở channel mong đợi và xác nhận **các channel còn lại không nhận được gì**. Không dùng đồng thời queue test và handler production trên cùng tên channel.

Ma trận kiểm thử nên bao gồm:

| Trường hợp | Dữ liệu | Kết quả mong đợi |
|---|---|---|
| Thị trường hợp lệ, chưa chuẩn hóa | `region=" vn "` | `orders.vn`, payload đã normalize |
| Route hợp lệ khác | `region="US"` | `orders.us` |
| Thị trường mới nhưng hợp lệ | `region="DE"` | `orders.unmapped` |
| Payload sai class | `String`, `byte[]` | `orders.rejected.type`, không gọi Transformer |
| Thiếu order ID | `orderId=null` | `orders.rejected.missing` |
| Thiếu quantity | `quantity=null` | `orders.rejected.missing` |
| Quantity sai | `quantity=-1` | `orders.rejected.value` |
| Version chưa hỗ trợ | `schemaVersion=2` | `orders.rejected.version` |
| JSON không parse được | Wire bytes lỗi | Adapter error, không vào `orders.raw` |
| Header bắt buộc thiếu | Không có `riskLevel` | Nhánh missing/unknown như đã định |
| SpEL/handler ném lỗi | Method không tồn tại hoặc handler lỗi | Exception/error handling, không coi là unmapped |
| Hai order qua Splitter | Cùng/nhiều correlation ID xen kẽ | Không trộn nhóm, timeout/reject có chủ đích |

### Ví dụ integration test một đường đi

Giả sử test context đã cung cấp `orders.vn` là `PollableChannel` và không tạo consumer production cùng tên:

~~~java
@Autowired
ApplicationContext context;

@Test
void sendsValidatedOrderToVn() {
    MessageChannel input =
        context.getBean("orders.raw", MessageChannel.class);
    PollableChannel vn =
        context.getBean("orders.vn", PollableChannel.class);

    Message<IncomingOrderV1> inputMessage = MessageBuilder
        .withPayload(new IncomingOrderV1(
            1, "E-10", "O-10", " vn ", 3))
        .setHeader("correlationId", "O-10")
        .build();

    assertTrue(input.send(inputMessage));
    Message<?> output = vn.receive(1000);

    assertNotNull(output);
    assertInstanceOf(ValidatedOrder.class, output.getPayload());
    assertEquals("VN",
        ((ValidatedOrder) output.getPayload()).region());
    assertEquals("O-10",
        output.getHeaders().get("correlationId"));
}
~~~

Đây là phần thân test minh họa: ứng dụng test phải khởi tạo flow, bean input/channel đúng tên và thay các consumer đích bằng queue phù hợp. Với flow bất đồng bộ, dùng timeout có giới hạn hoặc assertion có điều kiện; không trông chờ `Thread.sleep` cố định để đo độ hoàn thành.

## 15. Quan sát lỗi routing trong vận hành

Một báo cáo “message bị mất” thường có thể phân tích bằng dữ liệu tại từng boundary:

| Điểm quan sát | Metric/log nên có | Câu hỏi |
|---|---|---|
| Inbound adapter | Decode success/failure, schema version | Message có đến Router không? |
| Type gate | Tỷ lệ WRONG_TYPE, MISSING_FIELD, INVALID_VALUE | Input producer có đúng contract không? |
| Normalizer | Transform error, field normalization | Dữ liệu trước/sau có khác bất thường không? |
| Content-Based Router | Số message theo key/channel, fallback count | Route có nhận key mới chưa hỗ trợ không? |
| Consumer đích | Processing duration, timeout, failed count | Có xử lý xong hay kẹt ở nhánh? |
| Error/retry | Retry attempts, DLQ/quarantine, error category | Có retry nhầm lỗi vĩnh viễn không? |
| Aggregator | Correlation ID, group size, expiry | Có message con bị reject làm nhóm thiếu không? |

Không ghi nguyên payload hoặc thông tin khách hàng vào metric tag; dùng mã lỗi có tập giá trị hữu hạn và tên route chuẩn hóa để tránh **high-cardinality**. Có thể dùng các cơ chế observation/tracing của Spring khi đã cấu hình để nối log qua Gateway, Filter, Transformer, Router, adapter và handler.

Khi điều tra sai nhánh, kiểm tra lần lượt **wire format → runtime type → validation result → normalized payload → routing key → mapping/fallback → downstream channel/consumer → exception path**. Cách truy vết có cấu trúc nhanh hơn việc chỉ xem log của handler cuối.

## 16. Sai lầm phổ biến

**Gọi accessor quá sớm.** Dùng `payload.region()` khi chưa xác nhận payload là `IncomingOrderV1` có thể ném lỗi runtime. Type gate trước, Router nghiệp vụ sau.

**Gom thiếu field và unknown key vào cùng default.** `region=null` là dữ liệu không hợp đồng; `region="DE"` có thể là dữ liệu hợp lệ nhưng chưa được hỗ trợ. Hai tình huống cần chính sách khác nhau.

**Tin rằng default channel bắt mọi exception.** Default không giải quyết deserialize error, lỗi SpEL hoặc handler exception. Phải xác định error path theo từng ranh giới đồng bộ/bất đồng bộ.

**Nhầm Filter discard với error channel.** Filter từ chối theo predicate khác với code ném exception. Nếu cần biết vì sao message sai, trả key lỗi có ý nghĩa hoặc cấu trúc validation result.

**Lấy `Map`/`String` làm payload ở mọi lớp.** Mọi handler phải tự parse và cast, làm tăng lỗi runtime. Decode một lần tại ingress và chuyển sang contract rõ ràng.

**Dùng input để tạo expression hoặc tên channel tự do.** Dữ liệu không tin cậy không được phép quyết định class, SpEL code hoặc channel ngoài whitelist.

**Retry dữ liệu sai vô hạn.** Lỗi schema/type thường chỉ có thể giải quyết ở producer hoặc sau migration. Retry chỉ hợp lý khi nguyên nhân tạm thời; kèm idempotency và giới hạn.

**Chỉ test happy path.** Router có thể hoạt động với VN/US nhưng xử lý sai khi thiếu `quantity`, `riskLevel` hoặc version mới. Ma trận đầu vào lỗi là một phần bắt buộc của hợp đồng.

**Không tính tác động đến nhóm Splitter/Aggregator.** Message con bị reject có thể khiến Aggregator chờ hết hạn hoặc không bao giờ release. Phải quyết định failure-result/timeout/compensation.

## 17. Bài thực hành tổng hợp

Xây dựng luồng **DefensiveOrderRouter** bằng Spring Integration theo các bước:

1. **Ingress:** nhận JSON từ một adapter và tạo `IncomingOrderV1`. Tách đường lỗi parse khỏi message flow.
2. **Type/version gate:** phân loại `WRONG_TYPE`, `MISSING_FIELD`, `INVALID_VALUE`, `UNSUPPORTED_VERSION` và `VALID`.
3. **Transformer:** chuẩn hóa `region` về uppercase và chuyển sang `ValidatedOrder`.
4. **Content-Based Router:** `VN → orders.vn`, `US → orders.us`, còn lại tới `orders.unmapped`.
5. **Header router:** kiểm tra `riskLevel`, thiếu header phải đi nhánh riêng, không ngầm coi là rủi ro thấp.
6. **Xử lý lỗi:** mỗi rejection channel có người nhận; thiết kế exception/error channel và chính sách retry cho handler tạm thời thất bại.
7. **Kiểm thử:** dùng classifier unit test và integration test với queue đích, chứng minh không có message lỗi lọt sang nhánh nghiệp vụ.
8. **Mở rộng:** tách dòng hàng và gộp kết quả; thử thiếu một message con, timeout, redelivery và kiểm tra correlation.

**Tiêu chí hoàn thành:** có bảng hợp đồng dữ liệu, sơ đồ các nhánh, test cho đủ tình huống thiếu/sai kiểu/version/unknown route, chính sách retry khác nhau theo nguyên nhân, số liệu routing theo channel và ví dụ truy vết một event từ ingress tới kết quả cuối.

## 18. Ghi nhớ

**Route khi dữ liệu thiếu hoặc sai kiểu** không nên thực hiện bằng một biểu thức phức tạp cố đoán mọi trường hợp. Trong Spring Integration, hãy phân chia **decode → type gate → validate → transform → content-based route → business handler**. Những dữ liệu bị loại phải có reason và kênh tiếp nhận rõ ràng; key hợp lệ nhưng chưa hỗ trợ dùng fallback; exception runtime đi theo error handling phù hợp.

Khi áp dụng kết hợp với **Filter, Transformer, Gateway, Splitter/Aggregator, retry, error channel và correlation**, một CBR phòng vệ tốt giúp message flow vừa linh hoạt trước dữ liệu mới, vừa an toàn trước dữ liệu hỏng, đồng thời dễ kiểm thử và theo dõi trong môi trường phân tán.
