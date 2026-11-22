# Xử lý dữ liệu thiếu trong transformer

## 1. Vì sao dữ liệu thiếu là một vấn đề của Transformer?

Một hệ thống nhận sự kiện đơn hàng từ HTTP, Kafka hoặc AMQP rồi chuyển thành một mô hình nội bộ thống nhất. Một producer gửi đầy đủ `orderId`, `region` và `quantity`; producer khác bỏ trống `region` hoặc không gửi `quantity`. Nếu Transformer tự thay các trường thiếu bằng giá trị mặc định không được nghiệp vụ phê duyệt, message có thể vẫn đi qua **Router** nhưng tới **sai channel**, khiến hệ thống xử lý đơn hàng không đúng thị trường hoặc số lượng.

Ví dụ, payload nhận được sau deserialize:

~~~json
{
  "schemaVersion": 1,
  "eventId": "EV-101",
  "orderId": "ORD-101",
  "region": null,
  "quantity": 3,
  "customerNote": null
}
~~~

Hai trường cùng có giá trị `null` nhưng ý nghĩa khác nhau:

- `region` quyết định đường xử lý; nếu không xác định được thị trường, **không được tự đoán "VN"**.
- `customerNote` là thông tin tùy chọn; có thể chuyển thành chuỗi rỗng **nếu hợp đồng đích quy định**.

**Nguyên tắc trọng tâm:** Transformer thực hiện chuyển đổi **có hợp đồng**, không phải nơi lặng lẽ vá mọi dữ liệu hỏng. Cần phân loại được *thiếu trường bắt buộc*, *thiếu trường tùy chọn*, *sai kiểu*, *giá trị không hợp lệ* và *schema không tương thích* trước khi quyết định **biến đổi, từ chối hay chuyển sang nhánh xử lý ngoại lệ**.

Bài thuộc chương **Transformer** của module **SPRING_INTEGRATION_PATTERN**, phục vụ mục tiêu học **Enterprise Integration Patterns** với Spring Integration để thiết kế message flow ít phụ thuộc, dễ mở rộng. Các ví dụ đặt Transformer bên cạnh **Gateway, Filter, Router, Splitter, Aggregator, retry, error channel và correlation**, đồng thời cho thấy cách kiểm thử, theo dõi nhánh xử lý.

Sau bài này, bạn sẽ thiết kế được DTO inbound có thể biểu diễn thiếu dữ liệu, chuyển sang payload nội bộ có bất biến rõ ràng, chọn chiến lược reject/default/derive phù hợp, giữ metadata cần thiết và xây dựng kiểm thử cho cả dữ liệu hợp lệ lẫn dữ liệu thiếu.

## 2. Xác định “thiếu” ở tầng nào

Không phải mọi vấn đề được mô tả là “thiếu dữ liệu” đều xảy ra trong Transformer:

| Tình huống | Ví dụ | Nơi xử lý thích hợp |
|---|---|---|
| **Wire message không thể đọc** | JSON bị cắt, byte stream lỗi | Inbound adapter/decoder |
| **Kiểu dữ liệu không tương thích** | `quantity="n/a"` nhưng schema yêu cầu Integer | Deserializer/schema validation |
| **Thiếu trường bắt buộc** | DTO có `orderId=null` | Validator/Transformer theo contract |
| **Chuỗi trống hoặc chỉ có khoảng trắng** | `region="  "` | Validation rồi normalization |
| **Trường tùy chọn vắng mặt** | Không có `customerNote` | Default có chủ đích |
| **Giá trị đúng kiểu nhưng sai quy tắc** | `quantity=-3` | Business validation |
| **Header bị thiếu** | Không có `traceId` hoặc `tenantId` | Header policy/adapter; chỉ suy từ nguồn tin cậy |
| **Schema version chưa hỗ trợ** | `schemaVersion=3` trong consumer chỉ hỗ trợ v1 | Version gate/migration |

Một số framework deserialize có thể phân biệt **field absent** và **field explicitly null** nếu ta dùng tree model, custom deserializer hoặc presence-aware DTO. Một record Java với nullable fields thường **không còn giữ được khác biệt này** sau khi mapping: cả hai tình huống có thể tạo giá trị `null`. Vì vậy nếu nghiệp vụ cần biết “không truyền trường” khác với “yêu cầu xóa trường”, phải giữ thông tin hiện diện **ngay từ ranh giới parse**.

Ngoài ra, **Spring `Message<?>` không dùng payload bằng `null` như một message hợp lệ thông thường**. “Payload thiếu dữ liệu” ở đây chủ yếu là **trường trong payload bị thiếu**, hoặc header không tồn tại; không biến `null` payload thành một event ngầm có ý nghĩa.

## 3. Hợp đồng inbound và hợp đồng nội bộ

Ở biên hệ thống, dùng kiểu nullable cho những trường có thể bị bỏ qua hoặc gửi sai:

~~~java
record IncomingOrderV1(
    Integer schemaVersion,
    String eventId,
    String orderId,
    String region,
    Integer quantity,
    String customerNote
) {}

record NormalizedOrder(
    String eventId,
    String orderId,
    String region,
    int quantity,
    String customerNote
) {}
~~~

Hai kiểu có vai trò khác nhau:

- `IncomingOrderV1` phản ánh những gì adapter *đã parse được*; `Integer` giúp phân biệt trường thiếu hoặc `null` với số `0`.
- `NormalizedOrder` là hợp đồng **đã kiểm tra**; `quantity` trở thành `int`, các String bắt buộc được đảm bảo không rỗng tại ranh giới chuyển đổi.

| Thuộc tính | Bắt buộc? | Quy tắc | Khi thiếu |
|---|---|---|---|
| `schemaVersion` | Có | Chỉ hỗ trợ 1 trong ví dụ | Reject `MISSING_VERSION` |
| `eventId` | Có | Không blank | Reject `MISSING_EVENT_ID` |
| `orderId` | Có | Không blank | Reject `MISSING_ORDER_ID` |
| `region` | Có | Mã hai chữ cái, chuẩn hóa uppercase | Reject `MISSING_REGION` |
| `quantity` | Có | Số nguyên dương | Reject `MISSING_QUANTITY` hoặc `INVALID_QUANTITY` |
| `customerNote` | Không | Tối đa 500 ký tự, chuẩn hóa khoảng trắng | Có thể thay bằng `""` |

**Không nên** dùng `int quantity` ngay ở inbound DTO nếu producer có thể không gửi trường đó: tùy deserializer, field thiếu có thể bị gán `0`, làm mất khả năng phân biệt “không có dữ liệu” với “đã gửi số 0”.

Tương tự, nếu `region` ảnh hưởng phân quyền, giá và kho hàng, không có lý do an toàn để tự đặt mặc định `VN` chỉ vì đa số khách hàng ở Việt Nam. Giá trị mặc định phải là **quy tắc nghiệp vụ đã được công bố**, không phải phỏng đoán của người viết code.

## 4. Pipeline đề xuất: decode, validate, transform rồi mới route

~~~mermaid
flowchart TD
    W["HTTP / Kafka / AMQP input"] --> D{"Decode + schema"}
    D -->|"Không thể parse"| P["Ingress error / quarantine"]
    D -->|"Đã parse"| M["Message<IncomingOrderV1>"]
    M --> V{"Type, version và required fields"}
    V -->|"Không hợp lệ"| R["Rejected result / exception"]
    V -->|"Hợp lệ"| T["Transformer: normalize + map"]
    T --> C["Message<NormalizedOrder>"]
    C --> ROUTE{"Router theo region"}
    ROUTE -->|"VN"| VN["orders.vn"]
    ROUTE -->|"US"| US["orders.us"]
    ROUTE -->|"Khác"| O["orders.unmapped"]
    R --> E["Error policy / rejected channel"]
~~~

**Decode** giải quyết cú pháp và kiểu trên wire. **Validation** quyết định dữ liệu có đáp ứng hợp đồng tối thiểu không. **Transformer** đổi kiểu, chuẩn hóa và dựng model ổn định. **Router** chọn nhánh theo payload đã được kiểm tra.

Trong một flow nhỏ, validation và transformation có thể nằm trong cùng một hàm Java. Tuy vậy, hãy giữ **quy tắc kiểm tra tách biệt và kiểm thử được**, tránh một Transformer dài vừa parse JSON, gọi API, tính giá, gửi email vừa chọn channel.

Filter chỉ trả boolean “qua/không qua”; khi cần nhiều lý do từ chối, một classifier có mã lỗi hoặc một result type cụ thể sẽ dễ quan sát hơn. **Đừng coi `defaultOutputChannel` của Router là nơi tự động xử lý mọi lỗi Transformer**: exception xảy ra trước khi có routing key không tự biến thành key chưa được map.

## 5. Ba quyết định khi gặp trường thiếu

Với mỗi trường, chỉ nên chọn **một chính sách minh bạch**:

| Chính sách | Khi phù hợp | Ví dụ |
|---|---|---|
| **Reject / fail-fast** | Trường bắt buộc, không đủ cơ sở suy ra | Thiếu `orderId`, `quantity` |
| **Default có chủ đích** | Trường tùy chọn, default được quy định rõ | `customerNote = ""` |
| **Derive từ nguồn đáng tin** | Có nguồn khác được xác minh, precedence rõ ràng | `region` từ một identity/tenant context đã được xác thực |

Có thể có thêm lựa chọn **giữ trạng thái thiếu** nếu model nội bộ chấp nhận optional field và handler sau chịu trách nhiệm; điều này phải được thể hiện trong type như `Optional` hoặc field nullable và hợp đồng downstream. Không biến optional thành mandatory ngầm chỉ vì một handler viết thiếu null-check.

Để quyết định, hãy hỏi:

1. Trường này điều khiển quyết định an toàn, giá, tài chính, quyền truy cập hay routing không?
2. Giá trị mặc định có làm thay đổi ý nghĩa nghiệp vụ hoặc che lỗi của producer không?
3. Nếu dùng header thay thế, header ấy có được xác minh, có cùng phạm vi tenant/version và có precedence được công bố không?
4. Hệ thống có đo được tần suất dữ liệu thiếu và nguồn phát sinh không?

**Thiếu dữ liệu không phải bằng chứng có thể retry thành công.** Nếu producer đã tạo một event không có `orderId`, việc đọc lại đúng event từ broker thường không bổ sung trường ấy; cần reject/quarantine hoặc quy trình sửa dữ liệu có kiểm soát, thay vì retry vô hạn.

## 6. Code: Transformer kiểm tra required fields trước khi tạo payload mới

Một cách triển khai là dùng một service thuần Java, không làm I/O trong quá trình biến đổi:

~~~java
final class InvalidOrderException extends RuntimeException {
    private final String reasonCode;

    InvalidOrderException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    String reasonCode() {
        return reasonCode;
    }
}

final class OrderNormalizer {

    NormalizedOrder normalize(IncomingOrderV1 raw) {
        if (raw == null) {
            // Phòng vệ khi gọi hàm Java trực tiếp;
            // payload null không phải message hợp lệ thông thường.
            throw new InvalidOrderException("MISSING_PAYLOAD");
        }
        if (raw.schemaVersion() == null) {
            throw new InvalidOrderException("MISSING_VERSION");
        }
        if (raw.schemaVersion() != 1) {
            throw new InvalidOrderException("UNSUPPORTED_VERSION");
        }

        String eventId =
            required(raw.eventId(), "MISSING_EVENT_ID");
        String orderId =
            required(raw.orderId(), "MISSING_ORDER_ID");
        String region =
            required(raw.region(), "MISSING_REGION")
                .toUpperCase(Locale.ROOT);

        if (!region.matches("[A-Z]{2}")) {
            throw new InvalidOrderException("INVALID_REGION");
        }
        if (raw.quantity() == null) {
            throw new InvalidOrderException("MISSING_QUANTITY");
        }
        if (raw.quantity() <= 0) {
            throw new InvalidOrderException("INVALID_QUANTITY");
        }

        String note = raw.customerNote() == null
            ? ""
            : raw.customerNote().strip();
        if (note.length() > 500) {
            throw new InvalidOrderException("NOTE_TOO_LONG");
        }

        return new NormalizedOrder(
            eventId, orderId, region, raw.quantity(), note);
    }

    private String required(String value, String reasonCode) {
        if (value == null || value.isBlank()) {
            throw new InvalidOrderException(reasonCode);
        }
        return value.strip();
    }
}
~~~

Đặc điểm của thiết kế:

- `normalize()` hoặc trả một `NormalizedOrder` **đầy đủ**, hoặc ném exception có mã lỗi ổn định; không tạo object nửa hợp lệ.
- Chuỗi chỉ có khoảng trắng được xem là **thiếu** đối với trường bắt buộc, thay vì âm thầm route bằng chuỗi trắng.
- `quantity=null` khác `quantity=0`: trường hợp đầu là thiếu, trường hợp sau có giá trị nhưng không hợp lệ.
- `region="de"` được chuẩn hóa thành `DE`. Mã DE **đúng cấu trúc nhưng chưa có mapping** có thể đi `orders.unmapped`; khác trường hợp thiếu region.
- Trường tùy chọn `customerNote` có default `""`; vẫn giới hạn độ dài để tránh message đầu vào bất thường.

`InvalidOrderException` là **class minh họa do ứng dụng định nghĩa**, không phải một exception đặc biệt có sẵn của Spring Integration. Khi được gọi trong một Transformer endpoint, framework có thể bọc exception này trong một messaging/transformation exception; phần xử lý lỗi nên kiểm tra **cause chain** và reason code, không so khớp chuỗi log.

## 7. Cấu hình Transformer trong Spring Integration Java DSL

Kết nối service thuần Java với flow:

~~~java
@Configuration
@EnableIntegration
class OrderTransformFlow {

    @Bean
    OrderNormalizer orderNormalizer() {
        return new OrderNormalizer();
    }

    @Bean
    IntegrationFlow normalizeAndRoute(OrderNormalizer normalizer) {
        return IntegrationFlow.from("orders.decoded")
            .transform(IncomingOrderV1.class, normalizer::normalize)
            .route(NormalizedOrder.class, NormalizedOrder::region,
                r -> r.channelMapping("VN", "orders.vn")
                      .channelMapping("US", "orders.us")
                      .defaultOutputChannel("orders.unmapped"))
            .get();
    }
}
~~~

Ví dụ Java DSL ở mức module, lược bỏ import. Cần cấu hình adapter để đầu vào `orders.decoded` thực sự chứa `IncomingOrderV1`, và có consumer cho `orders.vn`, `orders.us`, `orders.unmapped`.

Khi một order thiếu `quantity`:

1. `OrderNormalizer.normalize()` ném `InvalidOrderException("MISSING_QUANTITY")`.
2. Transformer endpoint chuyển exception theo cơ chế messaging tương ứng; **không tạo `NormalizedOrder`**.
3. Router phía sau **không được chạy** với dữ liệu hỏng.
4. Caller, error handler hoặc poller quyết định reject, retry hay quarantine theo chính sách.

**Giới hạn giả định:** typed transformer được thiết kế cho payload đúng lớp `IncomingOrderV1`. Nếu adapter có thể gửi `String` hoặc `byte[]` không mong đợi, lỗi conversion/type xảy ra trước hoặc khi gọi hàm; nên có type/schema gate riêng thay vì tin rằng mọi sai kiểu sẽ biến thành `MISSING_QUANTITY`.

## 8. Transformer bằng annotation: khi nào hữu ích?

Một endpoint có thể khai báo bằng `@Transformer`:

~~~java
@MessageEndpoint
class AnnotatedOrderTransformer {
    private final OrderNormalizer normalizer = new OrderNormalizer();

    @Transformer(
        inputChannel = "orders.decoded",
        outputChannel = "orders.normalized")
    public NormalizedOrder toInternal(IncomingOrderV1 input) {
        return normalizer.normalize(input);
    }
}
~~~

**Đây là biến thể thay thế** cho flow Java DSL ở mục 7; không đăng ký cả hai cùng consume `orders.decoded` trong một ứng dụng mẫu trừ khi có chủ đích điều phối nhiều subscriber.

Với annotation, output channel được khai báo rõ. Nếu cần Router, dựng flow kế tiếp nhận từ `orders.normalized`. Bất kể cú pháp Java DSL hay annotation, quy tắc vẫn là **Transformer chỉ phát dữ liệu thỏa hợp đồng**, không gửi payload còn thiếu field bắt buộc tới downstream.

Một `@Transformer` trả về đối tượng Java thuần thường được framework tạo reply message và sao chép các header thích hợp từ message gốc theo cơ chế transformer. Nếu bạn **tự xây một `Message<?>`**, cần chủ động xét những header phải giữ hoặc phải loại.

## 9. Không dùng `return null` để loại message

Người mới thường viết:

~~~java
@Transformer(inputChannel = "orders.decoded")
public NormalizedOrder transform(IncomingOrderV1 order) {
    if (order.quantity() == null) {
        return null; // Sai ý định: không phải Filter discard
    }
    return normalizer.normalize(order);
}
~~~

**Transformer trong Spring Integration có hợp đồng tạo output không null.** Trả về `null` không phải cách hợp lệ để nói “bỏ qua message”: hệ thống có thể ném lỗi transformation, ví dụ `MessageTransformationException` hoặc wrapper liên quan, tùy endpoint và phiên bản. Vì thế đừng dùng `null` làm tín hiệu rejection hoặc điều kiện “không thay đổi”.

Chọn đúng pattern:

| Ý định | Pattern phù hợp |
|---|---|
| Không muốn message đi tiếp | **Filter** với discard policy rõ ràng |
| Muốn báo lỗi khi thiếu trường bắt buộc | **Validator/Transformer** ném exception được phân loại |
| Muốn gửi message sai đến nhánh xử lý lỗi nghiệp vụ | **Classifier + Router**, hoặc result type hai trạng thái |
| Muốn giữ payload gốc | Pass-through flow/handler có hợp đồng rõ; không trả null |
| Muốn tùy biến giá trị một trường tùy chọn | Transformer tạo payload đầy đủ với default hợp lệ |

Một Filter mặc định có thể loại message mà không gửi reply. Khi Gateway đang chờ response, việc “drop” dễ gây timeout. Nếu nghiệp vụ bắt buộc trả `ACCEPTED/REJECTED`, dùng result type có cấu trúc thay vì trộn `return null`, exception và discard không được công bố.

## 10. Thiếu, blank, zero và “không hợp lệ” phải tách riêng

Một trường có thể mang giá trị nhưng vẫn không sử dụng được. Ví dụ:

| Giá trị inbound | Phân loại nên xem xét | Không nên làm |
|---|---|---|
| `region=null` | Thiếu trường bắt buộc | Tự chọn VN |
| `region=""` hoặc `"  "` | Blank → thiếu hợp đồng | Đưa tới Router với key trắng |
| `region="de"` | Có giá trị; chuẩn hóa `DE` | Từ chối chỉ vì chữ thường nếu contract cho phép |
| `region="D3"` | Sai định dạng | Xem là thị trường mới hợp lệ |
| `quantity=null` | Thiếu số lượng | Gán `0` rồi xử lý |
| `quantity=0` | Có giá trị nhưng sai quy tắc | Gộp metric với missing |
| `customerNote=null` | Tùy chọn vắng mặt | Ném exception không cần thiết |
| `customerNote="   "` | Chuỗi trống sau normalize | Giữ dữ liệu nhiễu nếu contract không yêu cầu |

Phân loại đúng giúp producer sửa được lỗi; metric có thể trả lời “tỉ lệ thiếu trường” khác với “tỉ lệ gửi sai giá trị”. Với contract phân biệt **zero hợp lệ** (ví dụ số lượng trả lại hàng có thể bằng 0 trong một loại event khác), phải tách DTO/validator theo use case, không dùng quy tắc chung cho tất cả event.

## 11. Default có chủ đích và ưu tiên nguồn giá trị

Có những field có default hợp lệ. Ví dụ, một ghi chú khách hàng tùy chọn có thể mặc định `""` và được hiển thị là “không có ghi chú”. Nhưng default luôn cần **tiêu chí an toàn**:

1. Default phải được mô tả trong schema/hợp đồng public.
2. Nó không được thay đổi route, quyền truy cập hoặc giá trị tiền bạc ngoài ý định.
3. Người vận hành đo được số lần sử dụng default.
4. Các consumer biết khác biệt giữa “giá trị trống có chủ đích” và “không biết giá trị”, khi khác biệt ấy có ý nghĩa.

Ví dụ default quá nguy hiểm:

~~~java
String region = raw.region() == null
    ? "VN"               // Không nên đoán market
    : raw.region();

int quantity = raw.quantity() == null
    ? 1                  // Có thể phát sinh giao dịch sai
    : raw.quantity();
~~~

Nếu một field là **bắt buộc theo business contract**, default không phải “giải pháp chống NullPointerException”. Nó có thể che giấu việc producer vi phạm hợp đồng và làm những bản ghi sai đi qua mọi kiểm tra sau đó.

**Default chỉ nên áp dụng khi nghiệp vụ đồng ý chấp nhận giá trị đó**. Một giá trị bị thiếu không nhất thiết là `0`, `false`, `unknown` hoặc `VN`; mỗi lựa chọn diễn đạt một ý nghĩa khác nhau.

## 12. Có thể lấy dữ liệu thiếu từ header không?

Một số metadata được adapter gán sau khi xác thực có thể giúp Transformer bổ sung dữ liệu. Nhưng phân biệt **header tin cậy** với **header do producer tự khai**.

Ví dụ, một ingress adapter đã xác minh tenant và gắn header `verifiedRegion` từ server-side identity context. Ta có thể đặt chính sách ưu tiên:

~~~text
region trong payload có giá trị
   → kiểm tra tính hợp lệ và đối chiếu quyền với verifiedRegion

region trong payload thiếu
   → chỉ dùng verifiedRegion nếu hợp đồng cho phép
      và header đã được xác minh bởi server

cả hai đều thiếu hoặc mâu thuẫn
   → reject, không suy đoán
~~~

Một hàm lấy header phòng vệ:

~~~java
String trustedRegionOrNull(Message<?> message) {
    Object raw = message.getHeaders().get("verifiedRegion");
    if (raw instanceof String region && !region.isBlank()) {
        return region.strip().toUpperCase(Locale.ROOT);
    }
    return null;
}
~~~

**Đây chỉ là hàm đọc header, không xác minh nguồn.** Tên `verifiedRegion` không làm giá trị tự trở nên đáng tin: inbound header mapper phải ngăn client ghi đè, và adapter/authentication layer phải là chủ thể thực sự gán trường đó. Nếu producer có thể tự đặt `verifiedRegion`, dùng nó để suy route có thể gây cross-tenant routing.

Khi bổ sung từ header, nên giữ mã nguồn quyết định như `VALUE_FROM_TRUSTED_CONTEXT` trong audit/tracing có kiểm soát; tránh đưa metadata xác thực nhạy cảm vào payload public hoặc outbound message.

## 13. Transformer có nhiệm vụ với headers và correlation như thế nào?

Một biến đổi payload không nên vô tình làm mất context dùng để ghép message và trả lời Gateway:

| Header/context | Cần cân nhắc |
|---|---|
| `correlationId` | Gắn các message thuộc cùng quy trình, nhất là Splitter/Aggregator |
| `sequenceNumber/sequenceSize` | Giúp Aggregator biết trình tự và kỳ vọng nhóm |
| `replyChannel` | Cần cho request–reply, đặc biệt khi Gateway chờ kết quả |
| `errorChannel` | Có thể xác định đường lỗi trong một số ngữ cảnh |
| `traceId`/baggage | Chỉ giữ context đã được chọn lọc và an toàn |
| `untrustedRoute`/raw headers | Không tự động phát sang downstream nếu chỉ dùng ở ingress |

Với Transformer trả **payload object**, framework thường xây reply message và xử lý sao chép header phù hợp. Khi tự tạo một message mới bằng `MessageBuilder.withPayload(...)` mà **không sao chép headers**, bạn có thể làm mất correlation/reply information.

Ví dụ chuyển đổi message thủ công:

~~~java
Message<NormalizedOrder> transformMessage(
        Message<IncomingOrderV1> source,
        OrderNormalizer normalizer) {
    NormalizedOrder normalized =
        normalizer.normalize(source.getPayload());

    return MessageBuilder.withPayload(normalized)
        .copyHeaders(source.getHeaders())
        .removeHeader("untrustedRoute")
        .setHeader("normalizationVersion", "v1")
        .build();
}
~~~

Đoạn code là minh họa, không có nghĩa phải sao chép **mọi header** qua mọi ranh giới. Với broker/outbound adapter, cần whitelist metadata được serialize và không đưa nguyên Spring `replyChannel`, `errorChannel` hoặc object nội bộ qua wire tùy tiện. ID/timestamp của Spring message cũng có semantics riêng; **không dùng `MessageHeaders.ID` làm idempotency key nghiệp vụ duy nhất** khi message có thể được tạo lại.

## 14. SpEL và null-safe navigation: hữu ích nhưng không thay validation

Spring Expression Language hỗ trợ các cách đọc thuộc tính và xử lý giá trị thiếu. Ví dụ một expression có thể dùng dạng Elvis:

~~~text
headers['customerNote'] ?: ''
~~~

Hoặc khi đọc thuộc tính có thể null, một cấu hình có thể dùng toán tử null-safe trên đối tượng phù hợp:

~~~text
payload.customer?.name ?: 'UNKNOWN'
~~~

Các expression ở đây mang tính minh họa cách hoạt động của SpEL; chúng phụ thuộc cấu trúc payload và kiểu accessor trong flow cụ thể.

**Lưu ý quan trọng:**

- Elvis và safe-navigation giúp tránh một số lỗi khi đọc `null`, nhưng **không tự kiểm tra quyền, kiểu dữ liệu và miền giá trị**.
- Biểu thức chỉ cần một property không tồn tại trên runtime type vẫn có thể lỗi dù một đoạn khác dùng `?.`.
- Default `'UNKNOWN'` chỉ an toàn nếu hợp đồng xem đó là giá trị hợp lệ cho downstream; với dữ liệu điều khiển Router hoặc authorization, rất có thể cần reject.
- Tránh expression dài chứa nhiều quy tắc nghiệp vụ, vì khó unit test và khó gắn reason code.
- **Không ghép chuỗi SpEL từ input không tin cậy**; expression thuộc cấu hình ứng dụng, payload/header chỉ cung cấp giá trị.

Với chuyển đổi có nhiều required fields, Java validator/Transformer thuần thường dễ đánh giá và dễ kiểm thử hơn một expression được ghép từ nhiều toán tử `?:`.

## 15. Hai chiến lược khi muốn báo lỗi: exception hay result type?

Không phải mọi API đều muốn nhận exception. Một Gateway có thể cần trả:

~~~json
{
  "orderId": "ORD-101",
  "status": "REJECTED",
  "reasonCode": "MISSING_REGION"
}
~~~

Có hai lựa chọn:

**Chiến lược A – Fail-fast bằng exception:** Transformer ném `InvalidOrderException`; ở biên hệ thống, error handler chuyển thành response/rejection record. Phù hợp khi dữ liệu không thỏa hợp đồng và caller hoặc transaction boundary cần một tín hiệu lỗi.

**Chiến lược B – Trả result có trạng thái:** Transformer **luôn trả object không null** thuộc một result type, rồi Router đưa kết quả hợp lệ và bị từ chối tới hai flow khác nhau. Phù hợp khi `REJECTED` là trạng thái nghiệp vụ bình thường và mỗi request cần một phản hồi có cấu trúc.

~~~mermaid
flowchart LR
    IN["IncomingOrderV1"] --> T{"Normalizer/Classifier"}
    T -->|"Accepted"| A["Accepted(NormalizedOrder)"]
    T -->|"Rejected"| R["Rejected(reasonCode)"]
    A --> ROUTE["Business Router"]
    R --> REJ["Rejection handler / reply"]
~~~

**Không lẫn hai kiểu:** nếu Transformer trả `null` để nghĩa là rejected, đó không phải result có trạng thái; và nếu Transformer ném exception, Router đặt sau nó không tự nhận message lỗi để phân nhánh.

## 16. Ví dụ result type thay vì exception cho lỗi dữ liệu dự kiến

Java 17 có sealed interface để biểu diễn hai outcome rõ ràng:

~~~java
sealed interface NormalizationResult
    permits AcceptedOrder, RejectedOrder {}

record AcceptedOrder(NormalizedOrder order)
    implements NormalizationResult {}

record RejectedOrder(String eventId, String reasonCode)
    implements NormalizationResult {}

final class ClassifyingOrderNormalizer {
    private final OrderNormalizer delegate = new OrderNormalizer();

    NormalizationResult normalize(IncomingOrderV1 input) {
        try {
            return new AcceptedOrder(delegate.normalize(input));
        } catch (InvalidOrderException invalid) {
            return new RejectedOrder(
                input == null ? null : input.eventId(),
                invalid.reasonCode());
        }
    }
}
~~~

Chỉ chuyển **những lỗi validation đã dự kiến** sang result `RejectedOrder`. Không nên bắt `RuntimeException` chung rồi biến mọi bug, database outage hoặc lỗi serialization thành “dữ liệu xấu”, vì sẽ che giấu sự cố vận hành.

Flow định tuyến kết quả:

~~~java
@Bean
ClassifyingOrderNormalizer classifyingOrderNormalizer() {
    return new ClassifyingOrderNormalizer();
}

@Bean
IntegrationFlow normalizeWithBusinessOutcome(
        ClassifyingOrderNormalizer classifier) {
    return IntegrationFlow.from("orders.decoded")
        .transform(IncomingOrderV1.class, classifier::normalize)
        .route(NormalizationResult.class,
            result -> result instanceof AcceptedOrder
                ? "ACCEPTED"
                : "REJECTED",
            r -> r.channelMapping("ACCEPTED", "orders.accepted")
                  .channelMapping("REJECTED", "orders.rejected"))
        .get();
}
~~~

Đăng ký bean classifier và flow này trong một lớp cấu hình Spring có `@Configuration`; đây là **biến thể thay thế** cho flow fail-fast ở mục 7, không bật cả hai trên cùng input channel nếu không chủ ý thiết kế competing consumers. Các channel `orders.accepted` và `orders.rejected` nhận **wrapper result type** trong ví dụ này. Nếu consumer nghiệp vụ cần `NormalizedOrder` thay vì `AcceptedOrder`, thêm Transformer mở wrapper **trong nhánh accepted**. Mỗi nhánh cần có owner/handler thực.

**Hợp đồng lỗi:** `RejectedOrder.reasonCode` là mã ổn định do ứng dụng quy định; không sử dụng nguyên exception stack trace làm payload phản hồi cho client. Nếu cần giữ raw message để điều tra, lưu trong kênh quarantine có quyền truy cập và retention phù hợp, không tự đính kèm thông tin nhạy cảm vào error reply công khai.

## 17. Dữ liệu thiếu trong JSON: lỗi xảy ra trước Transformer

Một parser hoặc Jackson adapter có thể gặp:

~~~json
{
  "schemaVersion": 1,
  "eventId": "EV-102",
  "orderId": "ORD-102",
  "region": "US",
  "quantity": "three"
}
~~~

JSON **đúng cú pháp**, nhưng trường `quantity` không đáp ứng schema yêu cầu số nguyên. Tùy cấu hình converter/deserializer, nó có thể:

1. Ném lỗi chuyển kiểu trước khi có `IncomingOrderV1`.
2. Thực hiện coercion nếu phù hợp với chính sách kiểu dữ liệu (không nên đoán).
3. Tạo một object khác kiểu với payload Transformer mong đợi nếu adapter đã cấu hình khác.

Vì vậy, một bài test `OrderNormalizer.normalize()` không chứng minh toàn bộ ingress xử lý đúng dữ liệu sai kiểu. Cần test **wire input → adapter → DTO → Transformer** để đảm bảo hành vi thiếu/sai field nhất quán.

Ví dụ định hướng:

~~~java
IncomingOrderV1 decode(byte[] json, ObjectMapper mapper)
        throws JsonProcessingException {
    return mapper.readValue(json, IncomingOrderV1.class);
}
~~~

Trong hệ thống thật, ranh giới decoder cần giới hạn kích thước và độ sâu dữ liệu, có schema version, kiểm tra nguồn đáng tin và không bật polymorphic deserialization thiếu kiểm soát. Lỗi parse trước Transformer cần có **ingress error handling** riêng; đừng trông đợi `defaultOutputChannel` ở Router sau cùng sẽ nhận lỗi đó.

## 18. Schema evolution và backward compatibility

Khi producer chuyển từ schema v1 sang v2, một field có thể:

- Trở thành optional.
- Đổi tên hoặc đổi kiểu.
- Bị tách thành hai field.
- Có default mới hợp lệ chỉ với v2.

Ví dụ, v2 đổi `region` thành `shippingMarket`. Nếu deserializer tiếp tục tạo DTO v1 với `region=null`, Transformer v1 sẽ thấy missing. Nhưng nguyên nhân thực không hẳn producer gửi dữ liệu hỏng; có thể consumer chưa hỗ trợ version mới.

Một chiến lược rõ ràng:

~~~mermaid
flowchart TD
    IN["Wire event + schemaVersion"] --> V{"Version gate"}
    V -->|"v1"| D1["Decode IncomingOrderV1"]
    V -->|"v2"| D2["Decode IncomingOrderV2"]
    V -->|"Không hỗ trợ"| REJ["Unsupported-version route"]
    D1 --> N1["Transformer v1 → NormalizedOrder"]
    D2 --> N2["Transformer v2 → NormalizedOrder"]
    N1 --> CORE["Core business flow"]
    N2 --> CORE
~~~

Cả hai Transformer đều hướng tới một hợp đồng nội bộ nhưng có thể có validation và default khác nhau theo version. Điều này giúp thay đổi producer/consumer ít phụ thuộc hơn, thay vì nhồi mọi phiên bản vào một `Map<String, Object>` rồi liên tục cast hoặc đọc field có thể thiếu.

**Không mặc định một missing field là backward-compatible.** Mỗi trường mới cần quy tắc rõ ràng về optional/default/migration; kiểm thử contract giữa producer và consumer là bước không thể bỏ qua.

## 19. Error channel, retry và idempotency

Khi Transformer ném lỗi trong Spring Integration, đường truyền lỗi phụ thuộc ranh giới thực thi:

| Bối cảnh | Lỗi Transformer có thể đi đâu? | Điều cần kiểm tra |
|---|---|---|
| `DirectChannel` đồng bộ | Truyền ngược về caller/Gateway | Exception wrapper, API response |
| `ExecutorChannel` | Xảy ra trong worker thread | Error handler/error channel phù hợp |
| `QueueChannel` + poller | Poller nhận lỗi sau khi lấy message | Transaction/error handler/recovery |
| Kafka/AMQP inbound | Listener/container hoặc error flow | Ack/nack, retry, redelivery, DLQ |
| Handler downstream | Lỗi sau khi normalized payload đã được phát | Không quy nhầm cho Transformer |

**Lỗi validation vĩnh viễn** như `MISSING_ORDER_ID` hoặc `INVALID_QUANTITY` thường **không nên retry tự động nhiều lần**: cùng một event sẽ tiếp tục thiếu dữ liệu. Thay vào đó, gửi rejected result hoặc quarantine, yêu cầu producer sửa contract và cho phép replay có chủ đích nếu đã có event mới/bản sửa hợp lệ.

**Lỗi tạm thời** (ví dụ Transformer tự gọi database hay remote service) có thể retry, nhưng đó cũng là dấu hiệu cần cân nhắc **tách I/O khỏi Transformer** để quản lý timeout, retry và transaction ở một handler riêng.

Khi retry sau khi một bước trước Transformer đã ghi dữ liệu, event có thể được xử lý lại. Dùng **event ID ổn định** và idempotency/transaction/outbox thích hợp; `MessageHeaders.ID` có thể khác giữa các lần phát lại.

**Default channel của Router không phải error channel.** Rejection do missing field có thể tạo một `RejectedOrder` và được Router xử lý bình thường; exception do Transformer fail thì cần được bắt ở error boundary đã cấu hình.

## 20. Dữ liệu thiếu trong Splitter/Aggregator và correlation

Giả sử một đơn hàng được Splitter chia thành ba dòng. Dòng thứ hai thiếu `sku` và bị Transformer reject; các dòng còn lại vẫn hợp lệ:

~~~mermaid
flowchart LR
    O["Order O-101"] --> S["Splitter: 3 line items"]
    S --> L1["Line 1"]
    S --> L2["Line 2: thiếu sku"]
    S --> L3["Line 3"]
    L1 --> T{"Transformer / validator"}
    L2 --> T
    L3 --> T
    T -->|"Accepted"| A["Aggregator"]
    T -->|"Rejected result"| ER["Failure result"]
    ER --> A
    A --> END["OrderResult"]
~~~

Nếu Transformer ném exception hoặc Filter drop dòng thứ hai, Aggregator có thể nhận **thiếu một thành viên** so với `sequenceSize`. Không được mặc định Aggregator vẫn tự release nhóm thành công.

Có hai hướng hợp lệ theo nghiệp vụ:

1. **Fail whole order:** kiểm tra toàn bộ item trước khi Splitter; nếu thiếu required field, trả lỗi đơn hàng mà không phát các dòng con.
2. **Partial outcome:** mỗi dòng tạo một `AcceptedLine` hoặc `RejectedLine`; Aggregator nhận đủ result và kết luận thành công một phần hay thất bại.

Trong hướng thứ hai, phải giữ `correlationId`, sequence metadata và event/line ID khi Transformer đổi payload. Có thể cần `groupTimeout`, release strategy và expired-message handling để tránh giữ nhóm vô hạn khi có sự cố không tạo result.

**Đừng dùng `return null` trong Transformer để “bỏ một line”**; nó có thể sinh exception và không cung cấp failure result cần thiết để Aggregator hoàn tất.

## 21. Unit test cho trường hợp thiếu dữ liệu

Lớp `OrderNormalizer` là Java thuần, nên test không cần Spring context:

~~~java
@Test
void rejectsMissingRequiredFields() {
    OrderNormalizer normalizer = new OrderNormalizer();

    InvalidOrderException missingRegion = assertThrows(
        InvalidOrderException.class,
        () -> normalizer.normalize(new IncomingOrderV1(
            1, "EV-1", "ORD-1", null, 2, null)));
    assertEquals("MISSING_REGION", missingRegion.reasonCode());

    InvalidOrderException missingQuantity = assertThrows(
        InvalidOrderException.class,
        () -> normalizer.normalize(new IncomingOrderV1(
            1, "EV-2", "ORD-2", "VN", null, null)));
    assertEquals("MISSING_QUANTITY", missingQuantity.reasonCode());
}

@Test
void defaultsOnlyOptionalNote() {
    OrderNormalizer normalizer = new OrderNormalizer();

    NormalizedOrder output = normalizer.normalize(
        new IncomingOrderV1(
            1, "EV-3", " ORD-3 ", " vn ", 3, null));

    assertEquals("ORD-3", output.orderId());
    assertEquals("VN", output.region());
    assertEquals(3, output.quantity());
    assertEquals("", output.customerNote());
}

@Test
void distinguishesMissingFromInvalidQuantity() {
    OrderNormalizer normalizer = new OrderNormalizer();

    InvalidOrderException invalid = assertThrows(
        InvalidOrderException.class,
        () -> normalizer.normalize(
            new IncomingOrderV1(
                1, "EV-4", "ORD-4", "US", 0, "")));
    assertEquals("INVALID_QUANTITY", invalid.reasonCode());
}
~~~

Đây là unit test JUnit 5 minh họa, import được lược bỏ. Kiểm tra một lần cho từng trường bắt buộc và cả giá trị biên: `null`, blank, khoảng trắng, zero, số âm, region sai định dạng, version thiếu hoặc không hỗ trợ. Đối với tiền tệ/giá, thêm các trường hợp precision, scale và range theo hợp đồng cụ thể.

## 22. Integration test: chứng minh Transformer không làm lọt message sai

Với Java DSL ở mục 7, trong **test configuration** có thể dùng `QueueChannel` làm đích `orders.vn`, `orders.us` và `orders.unmapped`. Gửi vào `orders.decoded` bằng `MessageBuilder`, rồi xác nhận channel nhận hoặc không nhận message.

Ví dụ phần thân test, giả định Spring context đã khởi tạo flow và các channel test:

~~~java
@Autowired
ApplicationContext context;

@Test
void acceptedOrderReachesCorrectRoute() {
    MessageChannel input =
        context.getBean("orders.decoded", MessageChannel.class);
    PollableChannel vn =
        context.getBean("orders.vn", PollableChannel.class);

    Message<IncomingOrderV1> message = MessageBuilder
        .withPayload(new IncomingOrderV1(
            1, "EV-10", "ORD-10", " vn ", 2, null))
        .setHeader("correlationId", "ORDER-10")
        .build();

    assertTrue(input.send(message));
    Message<?> output = vn.receive(1000);

    assertNotNull(output);
    assertInstanceOf(NormalizedOrder.class, output.getPayload());
    assertEquals("VN",
        ((NormalizedOrder) output.getPayload()).region());
    assertEquals("ORDER-10",
        output.getHeaders().get("correlationId"));
}
~~~

Với message bị từ chối trong flow đồng bộ, hãy kiểm tra exception/cause chain và **không có message nào đến nhánh nghiệp vụ**. Với flow result type, xác minh `orders.rejected` nhận `RejectedOrder(reasonCode)` và accepted không nhận.

### Ma trận integration test

| Trường hợp | Dữ liệu | Kết quả mong đợi |
|---|---|---|
| Happy path VN | `region=" vn "` | NormalizedOrder vào `orders.vn` |
| Happy path US | `region="US"` | Vào `orders.us` |
| Market mới hợp lệ | `region="DE"` | Vào `orders.unmapped`, **không** coi là thiếu |
| Thiếu region | `region=null` | Rejection/exception; không vào Router |
| Region blank | `region="  "` | Rejection có reason code |
| Region sai định dạng | `region="D3"` | `INVALID_REGION` |
| Thiếu quantity | `quantity=null` | `MISSING_QUANTITY` |
| Quantity không hợp lệ | `quantity=0` hoặc âm | `INVALID_QUANTITY` |
| Thiếu customerNote | `customerNote=null` | Default `""` nếu contract cho phép |
| Thiếu version | `schemaVersion=null` | `MISSING_VERSION` |
| Version chưa hỗ trợ | `schemaVersion=2` | `UNSUPPORTED_VERSION` |
| JSON sai kiểu quantity | Wire `"three"` | Decode/schema error ở ingress |
| Payload sai runtime type | `String` | Type/conversion error, không gán nhầm missing |
| Correlation cần giữ | Header correlation tồn tại | Reply/child message giữ metadata theo hợp đồng |
| Retry cùng event | Một `eventId` gửi lại | Không tạo side effect trùng theo nghiệp vụ |

Kiểm thử phải có **contract test ở ranh giới adapter** nếu muốn phân biệt JSON field không tồn tại với JSON `null`, hoặc bảo đảm mapper không tự thay `Integer null` thành `0`. Một unit test Java không thể chứng minh chi tiết của converter đầu vào.

## 23. Observability: nhìn ra lỗi producer thay vì che bằng default

Một số metric/log đề xuất:

| Tín hiệu | Ý nghĩa |
|---|---|
| `transform.accepted.count` | Số payload chuyển đổi thành công |
| `transform.missing.count` theo reason | Trường bắt buộc nào thường bị thiếu |
| `transform.invalid.count` theo reason | Giá trị sai miền/format |
| `transform.default.used.count` theo field | Có đang phải bù dữ liệu tùy chọn quá nhiều không |
| `transform.error.count` | Lỗi runtime ngoài validation dự kiến |
| `transform.duration` | Transformer có bị chậm, gọi I/O không cần thiết không |
| `router.unmapped.count` | Có market hợp lệ nhưng chưa hỗ trợ không |
| `dlq/quarantine.count` | Dữ liệu cần điều tra hoặc gửi lại |

Đây là **tên metric đề xuất**, không nhất thiết là tên meter mặc định của Spring Integration. Nếu dùng Micrometer/observation, chỉ đưa reason code, endpoint và schema version với miền giá trị hữu hạn vào metric tags. Không dùng `eventId`, `orderId` hay raw payload làm tag, tránh high cardinality và rò rỉ dữ liệu.

Một quy trình điều tra nên đi theo: **wire payload → decoder/schema → DTO hiện diện/nullable → validation reason → normalized payload → Router key → handler outcome → error/retry**. Giữ event ID và correlation context trong trace/log có kiểm soát để lần được message qua các bước.

**Nếu tỉ lệ `MISSING_REGION` tăng đột biến sau khi producer nâng version**, không nên vội thêm default `VN`; trước hết kiểm tra schema evolution và adapter mapping.

## 24. Sai lầm thường gặp

**“Thiếu gì thì mặc định để không bị NullPointerException.”** Sai. Default một field bắt buộc có thể thay đổi route, giá hoặc quyền truy cập.

**“Transformer trả null là cách bỏ message.”** Sai. Transformer cần kết quả không null; dùng Filter, classifier hoặc rejection result.

**“Trường có kiểu `int` nên không thể thiếu.”** Sai ở ranh giới JSON: giá trị mặc định của primitive có thể làm mất thông tin hiện diện.

**“Giá trị blank và missing giống unsupported route.”** Không. Blank là vi phạm hợp đồng, còn `DE` có thể hợp lệ nhưng chưa có nhánh xử lý.

**“Safe navigation trong SpEL nghĩa là input đã được validate.”** Sai. `?.` hoặc Elvis chỉ xử lý một số trường hợp null và không kiểm tra business rule.

**“Đọc header tên `verifiedRegion` tức header đó đáng tin.”** Sai. Cần kiểm soát nguồn và chống producer ghi đè.

**“Mọi lỗi Transformer đều retry.”** Sai. Dữ liệu thiếu vĩnh viễn khác lỗi mạng/DB tạm thời.

**“Một Transformer trả payload mới không ảnh hưởng correlation.”** Không thể giả định. Cần kiểm tra message header propagation và ranh giới serialize.

**“Có defaultOutputChannel thì Transformer sẽ không lỗi.”** Sai. Default Router chỉ áp dụng khi Router tính được key mà không phân giải được đích theo cấu hình.

**“Bắt mọi RuntimeException rồi trả REJECTED là an toàn.”** Sai. Cách đó che bug và sự cố vận hành dưới mã lỗi dữ liệu.

## 25. Bài thực hành: xử lý dữ liệu thiếu trong đơn hàng

Xây flow **OrderNormalization** như sau:

1. **Ingress:** nhận JSON có `schemaVersion` và decode thành DTO nullable, tách lỗi parse khỏi lỗi validation.
2. **Validation:** xác định required fields `eventId, orderId, region, quantity` và chính sách cho `customerNote`.
3. **Transformer:** chuẩn hóa region uppercase, loại khoảng trắng thừa, tạo `NormalizedOrder`; chỉ default cho trường optional.
4. **Router:** `VN → orders.vn`, `US → orders.us`, market mới hợp lệ đến `orders.unmapped`.
5. **Rejection:** thử cả fail-fast exception và result type `AcceptedOrder/RejectedOrder`; chọn một hợp đồng chính cho ứng dụng.
6. **Header policy:** thêm `verifiedRegion` từ context đã xác thực, kiểm thử thiếu/mâu thuẫn và quyền ưu tiên giữa các nguồn.
7. **Error/retry:** phân loại lỗi validation là non-retryable; kiểm thử error channel hoặc response của Gateway và broker recovery theo adapter.
8. **Correlation:** đưa một order qua Splitter/Transformer/Aggregator, thử thiếu một line và quy tắc failure result/timeout.
9. **Observability:** đo missing/invalid/default/route theo reason code và schema version.
10. **Contract test:** thử JSON field absent, explicit null, sai kiểu, version mới và payload quá lớn.

**Tiêu chí hoàn thành:** không có message thiếu trường bắt buộc tới consumer nghiệp vụ; trường tùy chọn có default được công bố; Transformer không trả `null`; một reason code giải thích mỗi rejection; metadata cần thiết được giữ; retry không lặp vô hạn; test xác minh được cả đường đi và đường lỗi.

## 26. Ghi nhớ

**Xử lý dữ liệu thiếu trong Transformer** là một quyết định về **hợp đồng dữ liệu**, không chỉ là thao tác tránh `NullPointerException`. Hãy xác định rõ trường bắt buộc và tùy chọn, phân biệt missing với blank/invalid/unsupported, chỉ dùng default khi được cho phép và không tự suy giá trị ảnh hưởng routing hoặc authorization.

Với **Spring Integration**, một luồng an toàn là **decode → validate → transform → route**, có đường rejection/exception phù hợp, giữ correlation và thực hiện retry theo nguyên nhân. Khi Transformer luôn trả payload nội bộ hợp lệ hoặc một outcome rõ ràng, các **Router, Filter, Gateway, Splitter, Aggregator** và handler downstream có thể tập trung vào nhiệm vụ riêng, giúp message flow ổn định, dễ kiểm thử và dễ theo dõi.
