# Phân biệt transformer với service activator

## 1. Vì sao cần phân biệt hai endpoint trông rất giống nhau?

Trong chương **Transformer** của module **SPRING_INTEGRATION_PATTERN**, chúng ta thực hành Enterprise Integration Patterns với Spring Integration để tạo các luồng message ít phụ thuộc, dễ mở rộng và kiểm thử được. Bên cạnh Router, Filter, Splitter, Aggregator, Gateway, retry, error channel và correlation, **Transformer** và **Service Activator** là hai thành phần thường được đặt liên tiếp trong cùng một IntegrationFlow.

Chúng dễ gây nhầm lẫn vì cả hai đều có thể nhận một message, gọi một phương thức Java và gửi tiếp một kết quả:

~~~java
// Hai câu lệnh đều có thể nhận input rồi tạo output.
.transform(RawOrder.class, normalizer::normalize)
.handle(NormalizedOrder.class, (order, headers) -> service.process(order))
~~~

Điểm khác nhau quan trọng **không nằm ở việc có gọi method Java hay không**, mà nằm ở **trách nhiệm và hợp đồng của endpoint**:

- **Transformer** thay đổi biểu diễn hoặc nội dung của message để các bước khác sử dụng. Nó phải **tạo một kết quả không null** khi hoạt động thành công.
- **Service Activator** gọi một dịch vụ để thực hiện một thao tác. Nó có thể **chỉ thực hiện tác động mà không trả reply**, hoặc **trả reply** khi là một bước request/reply.

Ví dụ hệ thống đặt hàng nhận đơn ở dạng thô:

~~~mermaid
flowchart LR
    A["RawOrder<br/>amountText='1250000'"] --> T["Transformer<br/>parse + chuẩn hóa"]
    T --> B["NormalizedOrder<br/>amountVnd=1250000"]
    B --> S["Service Activator<br/>ghi nhận đơn"]
    S --> D["Order repository / domain service"]
~~~

Hàm chuyển chuỗi số tiền thành BigDecimal và chuẩn hóa mã quốc gia không cần biết database. Ngược lại, việc **đặt hàng, giữ tồn kho hoặc gọi API thanh toán** là hành vi nghiệp vụ và thường thuộc Service Activator hoặc một adapter/gateway chuyên trách.

**Mục tiêu bài học**

1. Hiểu vai trò của Transformer và Service Activator trong Enterprise Integration Patterns.
2. Phân biệt **output, reply, null, side effect, transaction và lỗi** của mỗi endpoint.
3. Viết Java DSL với .transform(), .handle() và các annotation tương ứng.
4. Hiểu Service Activator cũng có thể trả về message, nhưng điều đó không biến mọi thao tác thành Transformer.
5. Chọn endpoint đúng trong luồng sync/async và request/reply với Gateway.
6. Kiểm thử nghiệp vụ chuyển đổi, hiệu ứng một lần, propagation header và nhánh lỗi.

## 2. Định nghĩa ở mức Enterprise Integration Patterns

### 2.1. Message Transformer: đổi biểu diễn thông điệp

Transformer là một bước xử lý một message đầu vào rồi tạo message có **nội dung hoặc cấu trúc được chuyển đổi**. Ví dụ:

- Chuỗi JSON được parse thành một record/domain DTO.
- Mã tiền tệ được chuẩn hóa, amount chuyển sang BigDecimal.
- Domain object chuyển thành payload phù hợp với một hệ thống khác.
- Bản ghi từ phiên bản schema cũ được chuyển sang schema mới.
- Payload có trường nhạy cảm được chiếu sang DTO chỉ chứa dữ liệu được phép gửi đi.

Mẫu tư duy:

~~~text
Input message
    -> transform(payload[, headers])
    -> Output message
~~~

Khi thành công, Transformer có **một kết quả** cho lần xử lý input thông thường. Nó không nên dùng giá trị null để biểu diễn “không cần xử lý”. Nếu nhu cầu chính là giữ/loại message, hãy dùng **Message Filter** với discard policy rõ ràng.

### 2.2. Service Activator: gọi hành vi dịch vụ

Service Activator kết nối message với **một hàm nghiệp vụ hoặc application service**:

- Tạo đơn hàng trong database.
- Gửi email, SMS hoặc thông báo.
- Tạo yêu cầu đánh giá rủi ro.
- Kích hoạt một dịch vụ domain hoặc gọi một API tích hợp.
- Truy vấn trạng thái và trả về kết quả.

Mẫu tư duy:

~~~text
Input message
    -> invoke service operation
    -> [optional reply message]
~~~

Một Service Activator **không bắt buộc** phải trả reply. Nếu service có phương thức void hoặc endpoint trả null trong chế độ one-way, việc hoàn thành thao tác có thể là **điểm kết thúc hợp lệ**.

Nhưng Service Activator cũng có thể là một bước **request/reply**, chẳng hạn đặt hàng rồi trả về orderId/receipt. Vì thế câu nói “Service Activator không bao giờ trả output” là **sai**.

### 2.3. Bảng phân biệt nhanh

| Khía cạnh | Transformer | Service Activator |
| --- | --- | --- |
| Mục đích chính | Biến đổi payload/message | Gọi thao tác của dịch vụ |
| Câu hỏi thiết kế | “Dữ liệu cần thành dạng nào?” | “Hệ thống cần làm hành động gì?” |
| Java DSL | .transform(...) | .handle(...) |
| Annotation | @Transformer | @ServiceActivator |
| Kết quả thành công | Phải có kết quả khác null | Có thể có reply hoặc không |
| Return null | Lỗi transformation | Có thể hợp lệ trong one-way |
| Side effect | Nên tránh, ưu tiên pure function | Có thể có và thường là trách nhiệm chính |
| Request/reply | Tạo dữ liệu ở chặng chuyển đổi | Có thể trả kết quả của một service call |
| Retry | Thường an toàn nếu hàm thuần | Phải quan tâm idempotency của side effect |
| Thread | Do channel/endpoint quyết định | Do channel/endpoint quyết định |
| Transaction | Không tự có transaction | Không tự có transaction |
| Header/correlation | Có thể giữ, thay hoặc tạo metadata | Có thể dùng header và trả reply |
| Điểm sau cùng | Thường cần downstream xử lý output | Có thể kết thúc flow một chiều |

**Quy tắc thực dụng:** nếu xoá endpoint mà **thế giới bên ngoài không mất một hành động nghiệp vụ nào**, đó thường là Transformer; nếu xoá endpoint khiến một hành động nghiệp vụ không được thực hiện, đó thường là Service Activator. Quy tắc này là gợi ý thiết kế, không phải định nghĩa kỹ thuật tuyệt đối.

## 3. Hợp đồng null và reply là khác biệt quan trọng nhất

### 3.1. Transformer không được trả null

Trong Spring Integration, Transformer được xây dựng trên hợp đồng **reply-producing**: một phép chuyển đổi thành công phải tạo output. Kể từ Spring Integration 2.0, trả null từ Transformer được coi là lỗi và dẫn tới **MessageTransformationException**, thay vì âm thầm làm message biến mất.

~~~java
// Không dùng cách này để lọc message.
String normalize(String text) {
    if (text == null || text.isBlank()) {
        return null;
    }
    return text.trim();
}
~~~

Nếu text rỗng là **input sai**, ném lỗi có mã rõ ràng:

~~~java
String normalize(String text) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException("EMPTY_TEXT");
    }
    return text.trim();
}
~~~

Nếu text rỗng là **được phép bỏ qua**, dùng Filter:

~~~java
IntegrationFlow.from("inputTextChannel")
        .filter(String.class, text -> !text.isBlank())
        .transform(String.class, String::trim)
        .channel("normalizedTextChannel")
        .get();
~~~

Ví dụ trên giả định các channel được khai báo và có consumer phù hợp. Filter phải có discard policy đáp ứng nghiệp vụ; đừng để một message quan trọng bị loại im lặng.

### 3.2. Service Activator có thể kết thúc one-way

~~~java
IntegrationFlow.from("validatedOrdersChannel")
        .handle(NormalizedOrder.class, (order, headers) -> {
            orderService.place(order);
            return null; // Không tạo reply: flow one-way kết thúc.
        })
        .get();
~~~

Khi endpoint là bước cuối của luồng một chiều, **không cần reply** là thiết kế hợp lý. Không được dùng cách này ở chặng giữa nếu những bước sau **phụ thuộc vào một reply** để tiếp tục.

### 3.3. Service Activator cũng có thể trả reply

~~~java
IntegrationFlow.from("placeOrderRequestsChannel")
        .handle(NormalizedOrder.class,
                (order, headers) -> orderService.placeAndReturnReceipt(order))
        .channel("orderReceiptsChannel")
        .get();
~~~

Khi service trả PlacementReceipt hoặc một đối tượng hợp lệ khác, Spring Integration có thể tạo message kết quả và gửi đến output channel. Đây vẫn là **Service Activator**, vì thao tác có mục đích nghiệp vụ là **đặt hàng**; reply chỉ là kết quả của dịch vụ.

**Cẩn thận với Gateway:** một Gateway đồng bộ đang đợi reply mà gặp Service Activator one-way trả null có thể phải chờ đến timeout hoặc đi vào đường lỗi tùy cấu hình. Một Transformer trả null không giúp “trả về không có kết quả”; đó là lỗi chuyển đổi.

### 3.4. Không có reply khác với không thành công

Một handler one-way có thể ghi database thành công rồi trả null; điều đó **không đồng nghĩa** producer đã nhận được biên nhận đã xử lý. Với ExecutorChannel hoặc QueueChannel, send() thành công còn có thể chỉ nghĩa là message đã được chấp nhận/đưa vào hàng đợi.

Nếu caller cần chắc chắn nghiệp vụ đã hoàn tất, phải thiết kế **acknowledgement, reply hoặc trạng thái xử lý** ở ranh giới thích hợp. Chỉ đổi return type thành void không tạo bảo đảm giao nhận.

## 4. Hai endpoint nằm ở đâu trong pipeline?

Một pipeline đơn hàng minh bạch:

~~~mermaid
flowchart TD
    I["Ingress RawOrder"] --> V["Validation"]
    V --> T["Transformer<br/>RawOrder -> NormalizedOrder"]
    T --> F{"Filter<br/>có cần tiếp tục?"}
    F -->|"Có"| R{"Router<br/>STANDARD / REVIEW"}
    R --> S["Service Activator<br/>placeOrder"]
    R --> M["Service Activator<br/>requestReview"]
    S --> P["Order persisted"]
    M --> Q["Review request persisted"]
    V -.->|"Invalid"| E["Error / quarantine"]
    F -->|"Discard theo policy"| D["Discard handler"]
~~~

Nhờ phân tách, các thành phần được kiểm thử độc lập:

- **Validation/Transformer:** hợp đồng input/output và lỗi dữ liệu.
- **Filter:** quyết định giữ/loại.
- **Router:** chọn channel theo chính sách.
- **Service Activator:** tác động nghiệp vụ và kết quả reply nếu có.
- **Gateway:** kết nối phương thức Java request/reply với flow.
- **Retry/error channel:** xử lý lỗi đúng ranh giới.
- **Correlation:** giúp theo dõi event xuyên các bước, không tự chống trùng.

Một application service đôi khi kết hợp cả việc chuẩn hóa và ghi DB. Tách một bước Transformer **không phải nghĩa vụ hình thức**, nhưng thường làm rõ ranh giới trách nhiệm, giảm tác động khi retry và cho phép đo riêng tỉ lệ lỗi conversion so với lỗi downstream.

## 5. Xây dựng ví dụ đầy đủ: RawOrder → NormalizedOrder → đặt hàng

Ví dụ dùng Java 17+, Spring Framework và Spring Integration Java DSL. Để minh họa rõ sự khác biệt, ta dùng **Transformer thuần Java** và một **service có side effect**; các endpoint Spring chỉ là lớp kết nối messaging.

### 5.1. Model đầu vào và kết quả

~~~java
import java.math.BigDecimal;

record RawOrder(
        String eventId,
        String orderId,
        String amountText,
        String countryCode) {}

record NormalizedOrder(
        String eventId,
        String orderId,
        BigDecimal amountVnd,
        String countryCode) {}

record PlacementReceipt(
        String orderId,
        String status) {}
~~~

**RawOrder** được coi là dữ liệu chưa chuẩn hóa. **NormalizedOrder** mang hợp đồng kiểu dữ liệu mà các bước tiếp theo sử dụng, nhưng **không tự chứng minh** người gửi sở hữu đơn hàng hoặc tenant. Xác thực/ủy quyền là trách nhiệm bổ sung ở trust boundary và service.

### 5.2. Transformer thuần, không side effect

~~~java
import java.math.BigDecimal;
import java.util.Locale;

final class OrderNormalizer {

    NormalizedOrder normalize(RawOrder raw) {
        if (raw == null) {
            throw new IllegalArgumentException("MISSING_ORDER");
        }
        if (raw.eventId() == null || raw.eventId().isBlank()
                || raw.orderId() == null
                || !raw.orderId().matches("ORD-[A-Za-z0-9-]{1,32}")) {
            throw new IllegalArgumentException("INVALID_IDENTIFIERS");
        }
        if (raw.amountText() == null || raw.amountText().isBlank()) {
            throw new IllegalArgumentException("MISSING_AMOUNT");
        }

        BigDecimal amount;
        try {
            amount = new BigDecimal(raw.amountText().trim());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "INVALID_AMOUNT_FORMAT", ex);
        }
        if (amount.signum() <= 0
                || amount.stripTrailingZeros().scale() > 0) {
            throw new IllegalArgumentException("INVALID_AMOUNT_VALUE");
        }

        String country = raw.countryCode();
        if (country == null
                || !country.trim().matches("[A-Za-z]{2}")) {
            throw new IllegalArgumentException("INVALID_COUNTRY");
        }

        return new NormalizedOrder(
                raw.eventId(),
                raw.orderId(),
                amount,
                country.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Hàm này chỉ sử dụng input và trả kết quả; không ghi database, gọi HTTP hay gửi event. Với cùng RawOrder hợp lệ, kết quả giống nhau. Trong production, cần kiểm tra giới hạn giá trị tiền, danh sách mã quốc gia hợp lệ và kích thước dữ liệu; regex hai ký tự ở đây chỉ minh họa kiểm tra hình dạng.

### 5.3. Service thực hiện thao tác

~~~java
interface OrderPlacementService {
    // Kết quả kiểu reply: dùng cho request/reply.
    PlacementReceipt placeAndReturnReceipt(NormalizedOrder order);

    // Tác vụ one-way: không cần reply nếu hợp đồng chỉ phát lệnh.
    void place(NormalizedOrder order);
}
~~~

Tầng implementation có thể gọi repository, transaction, outbox, payment adapter hoặc một service khác. Chính vì thế service cần có **idempotency và lỗi nghiệp vụ phù hợp**. Chữ ký method chỉ định nghĩa hợp đồng; nó chưa triển khai cơ chế chống trùng.

### 5.4. Cấu hình Spring Integration Java DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderFlowConfiguration {

    @Bean
    OrderNormalizer orderNormalizer() {
        return new OrderNormalizer();
    }

    @Bean
    MessageChannel rawOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel normalizedOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow normalizeOrders(OrderNormalizer normalizer) {
        return IntegrationFlow.from("rawOrdersChannel")
                .transform(RawOrder.class, normalizer::normalize)
                .channel("normalizedOrdersChannel")
                .get();
    }

    @Bean
    IntegrationFlow placeOrders(OrderPlacementService service) {
        return IntegrationFlow.from("normalizedOrdersChannel")
                .handle(NormalizedOrder.class, (order, headers) -> {
                    service.place(order);
                    return null; // Service Activator one-way.
                })
                .get();
    }
}
~~~

Luồng đi như sau:

1. Producer gửi Message<RawOrder> vào **rawOrdersChannel**.
2. Endpoint **Transformer** tạo NormalizedOrder. Nếu dữ liệu không hợp lệ, bước này ném exception.
3. Message kết quả đi qua **normalizedOrdersChannel**.
4. Endpoint **Service Activator** gọi orderPlacementService.place().
5. Service Activator trả null, nên flow một chiều **kết thúc** ở đây.

Phần chặng cuối không được dùng như một flow **cần reply** từ Gateway. Nếu client cần biên nhận, phải dùng Service Activator trả PlacementReceipt và bố trí replyChannel/outputChannel tương ứng.

### 5.5. Thêm request/reply không cần biến service thành Transformer

~~~java
// Bổ sung trong lớp @Configuration trên, với channel riêng.
@Bean
MessageChannel orderPlacementRequestsChannel() {
    return new DirectChannel();
}

@Bean
MessageChannel orderPlacementReceiptsChannel() {
    return new DirectChannel();
}

@Bean
IntegrationFlow receiptFlow(OrderPlacementService service) {
    return IntegrationFlow.from("orderPlacementRequestsChannel")
            .handle(NormalizedOrder.class,
                    (order, headers) ->
                            service.placeAndReturnReceipt(order))
            .channel("orderPlacementReceiptsChannel")
            .get();
}
~~~

Đây là **Service Activator có reply**. Một consumer phải nhận receipt trên orderPlacementReceiptsChannel. Trong flow sử dụng Gateway, nếu muốn Gateway nhận reply qua header **replyChannel**, có thể thiết kế endpoint reply-producing không có outputChannel tường minh để framework sử dụng replyChannel của request; bảo đảm không có channel trung gian chặn reply hoặc trả null.

### 5.6. Những gì Spring Integration tự làm và không làm

| Hành vi | Framework hỗ trợ | Ứng dụng vẫn phải làm |
| --- | --- | --- |
| Gọi hàm transform hoặc handle | Có | Đảm bảo method đúng hợp đồng |
| Tạo message reply từ payload được trả về | Có | Quy định output/channel cho reply |
| Quản lý channel và endpoint | Có | Đăng ký topology/consumer hợp lệ |
| Đảm bảo Transformer không trả null | Có kiểm tra hợp đồng | Viết logic dữ liệu phù hợp |
| Tự lưu kết quả order vào database | Không | Implement OrderPlacementService |
| Tự chống lặp đơn hàng do broker redelivery | Không | Idempotency và transaction |
| Tự tạo transaction cho mọi handler | Không | Transaction manager/ràng buộc phù hợp |
| Tự bảo đảm end-to-end exactly-once | Không | Thiết kế delivery/recovery |

## 6. Dùng annotation thay cho Java DSL

Nếu ứng dụng tổ chức endpoint bằng annotation, Spring Integration cung cấp **@Transformer** và **@ServiceActivator**. Chúng mô tả trách nhiệm của method trong messaging flow, không chỉ là tên trang trí.

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;

@Component
class AnnotatedOrderEndpoints {
    private final OrderNormalizer normalizer;
    private final OrderPlacementService placement;

    AnnotatedOrderEndpoints(
            OrderNormalizer normalizer,
            OrderPlacementService placement) {
        this.normalizer = normalizer;
        this.placement = placement;
    }

    @Transformer(
            inputChannel = "rawAnnotatedOrdersChannel",
            outputChannel = "normalizedAnnotatedOrdersChannel")
    public NormalizedOrder normalize(RawOrder raw) {
        return normalizer.normalize(raw);
    }

    @ServiceActivator(
            inputChannel = "normalizedAnnotatedOrdersChannel")
    public void place(NormalizedOrder order) {
        placement.place(order);
    }
}
~~~

Ví dụ cần khai báo hai channel, kích hoạt cơ chế annotation endpoint theo cấu hình Spring Integration và có bean OrderPlacementService. Annotation chỉ gắn method vào luồng; **nó không tự biến phép normalize thành side effect** hoặc khiến method void trả một receipt.

Khi dùng **@ServiceActivator** cho phương thức trả PlacementReceipt, kết quả có thể được gửi tới outputChannel hoặc replyChannel như một bước request/reply. Cần định rõ caller có đợi reply hay không và lỗi sẽ được báo theo cơ chế nào.

### 6.1. Một method giống hệt nhau có thể được gắn theo hai cách

~~~java
NormalizedOrder invoke(RawOrder raw) {
    return normalizer.normalize(raw);
}
~~~

Nếu gắn nó với Service Activator, về mặt kỹ thuật nó **vẫn có thể trả reply** chứa NormalizedOrder. Nhưng về mặt thiết kế, method đang thực hiện **transformation**, nên @Transformer giúp diễn đạt hợp đồng tốt hơn, kiểm tra null rõ ràng và khiến ý định của flow minh bạch.

Ngược lại, nếu một method vừa đặt đơn vào database vừa trả PlacementReceipt, nó là **hành vi dịch vụ**. Gắn @Transformer chỉ để “nó có output” che đi side effect và tạo rủi ro khi replay.

## 7. Payload, Message và header propagation

Một Spring Message gồm payload và MessageHeaders. Cả Transformer và Service Activator có thể nhận payload, toàn bộ Message, hoặc các giá trị header thông qua method invocation tùy cách khai báo. Điều cần tránh là nhầm **biến đổi payload** với **được quyền thay đổi metadata routing**.

### 7.1. Transformer trả payload khác với trả Message

Khi Transformer trả một payload:

~~~java
NormalizedOrder normalize(RawOrder raw) {
    return normalizer.normalize(raw);
}
~~~

Framework tạo message kết quả và xử lý việc truyền headers theo cơ chế của endpoint. Trong luồng đã được xác thực, những header cần thiết như businessCorrelationId, trace context hoặc replyChannel có thể cần được giữ qua các chặng.

Transformer cũng có thể trả **Message<NormalizedOrder>** để chỉ rõ payload và một số metadata:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<NormalizedOrder> normalizeMessage(
        Message<RawOrder> incoming) {
    NormalizedOrder output = normalizer.normalize(
            incoming.getPayload());

    return MessageBuilder.withPayload(output)
            .setHeader("normalizedSchemaVersion", 1)
            .build();
}
~~~

**Cảnh báo:** không coi ví dụ trả Message mới là cách chắc chắn xóa mọi header cũ. Spring Integration có quy tắc xử lý/lan truyền headers khi endpoint tạo reply; cần kiểm thử output thực tế trong version đang sử dụng. Để tạo **trust boundary**, hãy kiểm soát adapter ingress, chỉ giữ metadata trong allowlist và không cho client tự quyết định replyChannel, errorChannel, routingSlip hay trustedRoute.

### 7.2. Service Activator có thể dùng headers cho hành động

~~~java
import org.springframework.messaging.MessageHeaders;

// Đây là một method Java được gọi từ .handle() hoặc @ServiceActivator.
PlacementReceipt placeWithContext(
        NormalizedOrder order,
        MessageHeaders headers) {

    Object correlation = headers.get("businessCorrelationId");
    // Có thể ghi correlation đã kiểm tra vào audit context.
    return placement.placeAndReturnReceipt(order);
}
~~~

Đây là mảnh code minh họa; các dependency và xử lý correlation cần định nghĩa trong ứng dụng. Header dùng cho tracing **không tự chứng minh quyền truy cập** hoặc bảo đảm event không trùng. Service Activator cần kiểm tra tenant, actor, quyền và trạng thái nghiệp vụ trước khi thực hiện side effect.

### 7.3. Correlation qua Splitter/Aggregator

Nếu Transformer nằm giữa Splitter và Aggregator, các header **correlationId**, **sequenceNumber** và **sequenceSize** có thể là thành phần quan trọng để Aggregator ghép các kết quả con. Nếu Transformer trả null hoặc ném lỗi với một message con, Aggregator có thể **chờ thiếu thành viên** và cần group timeout/release strategy.

Service Activator đặt tại cùng vị trí có thể trả reply để tham gia aggregation, hoặc trả null và **không tạo phần tử trả về**. Do đó, đặt Service Activator one-way ở giữa một pipeline yêu cầu mọi reply có thể làm luồng bị thiếu kết quả.

| Vị trí | Hành vi trả kết quả | Tác động downstream |
| --- | --- | --- |
| Transformer giữa Splitter/Aggregator | Phải trả result | Mỗi message con thành công đi tiếp |
| Service Activator reply-producing | Có thể trả result | Có thể dùng như một bước xử lý trả kết quả |
| Service Activator one-way | Không có reply | Chỉ hợp lệ nếu pipeline không cần result ở vị trí đó |
| Filter loại message con | Discard theo chính sách | Group phải được thiết kế cho thành viên thiếu |

Không sửa correlation headers tùy tiện chỉ để Aggregator hết timeout. Nếu cần xử lý partial success, hãy thiết kế explicit success/failure results, group timeout và message store phù hợp.

## 8. DirectChannel và ExecutorChannel không làm thay đổi pattern

Một nhầm lẫn thường gặp là “Transformer đồng bộ, Service Activator bất đồng bộ”. Điều đó **không đúng**.

**Channel** và cấu hình endpoint quyết định thread:

- **DirectChannel** dispatch tới subscriber trên thread gửi, thường truyền exception ngược về caller.
- **ExecutorChannel** dùng executor để chạy handler, tạo ranh giới async; caller có thể nhận kết quả send trước khi downstream hoàn tất.
- **QueueChannel** nhận message rồi chờ poller hoặc consumer, nên tác vụ downstream chạy ở thời điểm khác.
- Các adapter broker có ack, redelivery và error handling tùy cấu hình.

~~~mermaid
flowchart TD
    P["Producer"] --> D{"Channel"}
    D -->|"DirectChannel"| ST["Transformer hoặc Service Activator<br/>cùng thread"]
    D -->|"ExecutorChannel"| EX["Executor worker<br/>Transformer hoặc Service Activator"]
    D -->|"QueueChannel"| Q["Poller nhận message"]
    Q --> WK["Transformer hoặc Service Activator"]
    ST -->|"Exception"| C["Caller nhận lỗi"]
    EX -->|"Exception"| E["Error handler / ErrorMessage"]
    WK -->|"Exception"| E
~~~

### 8.1. Nếu một Service Activator trả null trên ExecutorChannel

Phương thức có thể hoàn tất side effect rồi không tạo reply. Nhưng **send() trả true** từ Producer chỉ có nghĩa message đã được chấp nhận theo semantics của channel; nó không đồng nghĩa side effect đã commit.

Nếu cần biết nghiệp vụ đã hoàn tất, phải dùng receipt, trạng thái bền, acknowledgement hoặc event kết quả với correlation phù hợp. Không nên chỉ suy luận từ boolean của send().

### 8.2. Nếu Transformer ném lỗi trên ExecutorChannel

Exception không nhất thiết quay về thread producer; xử lý lỗi có thể thông qua **ErrorMessage** gửi tới errorChannel đã được cấu hình. Đây cũng là cơ chế có thể áp dụng cho Service Activator nếu handler của nó thất bại ở ranh giới async.

**Không mặc định** mọi lỗi đồng bộ được publish vào global errorChannel. Với DirectChannel, exception thông thường truyền qua call stack; với poller/executor của Spring Integration, framework thường có message-based error handling, nhưng phải kiểm tra adapter/executor thực tế.

## 9. Transaction và side effect: nơi nên đặt ranh giới

Transformer có thể được đánh giá như hàm **dữ liệu vào → dữ liệu ra**. Với hàm thuần, chạy lại cùng input thường không tạo side effect trùng.

Service Activator gọi hành vi như:

- INSERT đơn hàng.
- UPDATE số lượng tồn.
- POST charge tới cổng thanh toán.
- Gửi email.
- Phát event đến hệ thống khác.

Các hành động đó không tự an toàn trước retry/redelivery.

### 9.1. Transaction cho Service Activator ghi database

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class JdbcOrderPlacementService implements OrderPlacementService {
    private final OrderRepository orders;

    JdbcOrderPlacementService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    @Transactional
    public void place(NormalizedOrder order) {
        // Repository phải có unique constraint/idempotency theo eventId.
        orders.insertIfAbsent(
                order.eventId(),
                order.orderId(),
                order.amountVnd());
    }

    @Override
    @Transactional
    public PlacementReceipt placeAndReturnReceipt(
            NormalizedOrder order) {
        orders.insertIfAbsent(
                order.eventId(),
                order.orderId(),
                order.amountVnd());
        return new PlacementReceipt(order.orderId(), "ACCEPTED");
    }
}

interface OrderRepository {
    void insertIfAbsent(
            String eventId, String orderId, java.math.BigDecimal amountVnd);
}
~~~

Ví dụ giả định **OrderRepository** được cài đặt thật với unique constraint phù hợp. @Transactional chỉ phát huy khi method được gọi qua Spring proxy/transaction manager đúng cấu hình. Nó không tự làm các API ngoài database rollback.

**Idempotency cần nằm tại nơi side effect xảy ra.** Nếu cùng eventId được broker giao lại, database nên ngăn tạo bản ghi trùng. Nếu hai logical event khác nhau có cùng orderId, nghiệp vụ cần quy định rõ thao tác update/trùng order thay vì dùng eventId như một câu trả lời chung cho mọi yêu cầu.

### 9.2. Transformer đọc DB có nên không?

Không bị cấm về mặt kỹ thuật, nhưng nếu mỗi lần transform phải gọi DB/HTTP để làm giàu nội dung, hãy cân nhắc:

~~~text
RawOrder
  -> Pure Transformer (parse + normalize)
  -> Enricher / Gateway (đọc trạng thái bên ngoài)
  -> Router / Service Activator
~~~

Tách I/O giúp đặt timeout, retry, cache, circuit breaker và observability tại đúng bước. Nếu không thể tách, phải mô tả rõ Transformer không còn thuần, việc gọi lại có thể phụ thuộc trạng thái bên ngoài và test phải kiểm chứng các failure modes.

### 9.3. Thu tiền bên ngoài không được giả định rollback theo DB

Một Service Activator có thể lưu eventId vào database và gọi payment provider. Nếu payment provider đã thu tiền nhưng response mất, transaction DB rollback **không làm tiền quay lại**.

Để an toàn khi retry:

1. Tạo **logical payment operation ID** ổn định.
2. Truyền **idempotency key** ổn định sang provider nếu được hỗ trợ.
3. Lưu trạng thái **PENDING / COMPLETED / UNKNOWN** theo hợp đồng.
4. Với timeout có kết quả chưa rõ, tra cứu/đối soát thay vì phát lệnh mới với khóa mới.
5. Dùng outbox/inbox hoặc broker bền nếu phải hồi phục qua restart.

Không có API transform() hay handle() nào tự tạo **exactly-once side effect end-to-end**. Cần thiết kế ranh giới transaction/delivery cho từng tác động.

## 10. Retry: sự khác biệt về hậu quả

### 10.1. Retry Transformer thuần

Với cùng RawOrder, một normalize() thuần không ghi trạng thái; chạy hai lần cho cùng kết quả hoặc cùng lỗi. Vì vậy về mặt side effect, việc retry tương đối an toàn. Tuy nhiên, retry **dữ liệu sai cố định** như INVALID_AMOUNT_FORMAT vẫn vô ích.

### 10.2. Retry Service Activator

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant S as Service Activator
    participant DB as Order DB
    P->>S: place(evt-500)
    S->>DB: INSERT order
    DB-->>S: Commit thành công
    S--xP: Mất kết nối trước reply
    P->>S: Retry place(evt-500)
    S->>DB: INSERT lần nữa?
    Note over DB: Unique key/idempotent service bảo vệ effect
~~~

**Cùng message gọi lại không đồng nghĩa cùng effect được phép thực hiện lại**. Nếu method Service Activator nằm trong một retry advice mà tác vụ đã hoàn tất trước khi exception được phát ra, lần retry có thể tạo side effect trùng.

### 10.3. Đặt retry ở phạm vi hẹp nhất có ích

Nếu một flow gồm Transformer → Service Activator → Router → Notification:

- Lỗi parse không nên kích hoạt retry toàn pipeline.
- Lỗi transient của database có thể retry tại thao tác DB nếu transaction/idempotency hỗ trợ.
- Lỗi notification không nên vô tình retry thao tác đặt hàng đã thành công.

Với **RequestHandlerRetryAdvice**, cần gắn advice vào đúng endpoint có lỗi có thể phục hồi và định nghĩa recovery/backoff rõ ràng. Không chỉ bọc cả IntegrationFlow rồi giả định mọi bước lặp đều vô hại.

## 11. Lỗi của Transformer khác lỗi của Service Activator

| Loại lỗi | Nơi phát sinh | Hướng xử lý |
| --- | --- | --- |
| JSON sai hoặc số tiền không parse được | Transformer | Từ chối/quarantine, ít khi retry |
| Transformer trả null | Transformer | Lỗi hợp đồng chuyển đổi |
| Không hỗ trợ schemaVersion | Transformer/validation | Cách ly tới khi nâng version |
| DB unavailable | Service Activator | Retry có giới hạn, theo dõi transaction |
| Business rule không cho đặt đơn | Domain service qua Service Activator | Business rejection, không retry mù |
| Payment provider timeout | Service Activator hoặc Gateway | Idempotency/reconciliation |
| Service Activator one-way không trả reply | Thiết kế flow | Hợp lệ nếu không yêu cầu reply |
| Gateway timeout vì không nhận reply | Request/reply integration | Kiểm tra đường reply và hợp đồng endpoint |
| Downstream channel không có subscriber | Wiring/dispatch | Sửa topology, không ghi nhầm thành conversion error |

Trong đường đồng bộ, cả hai loại exception có thể truyền ngược về caller. Trong đường async, Spring Integration có thể phát **ErrorMessage** theo cơ chế error channel. Khi xử lý, hãy phân loại theo **component, root cause và error code**, không chỉ nhìn thấy send failed.

### 11.1. Error channel không tự lưu bền message

Một ErrorMessage được gửi tới errorChannel có thể giúp điều tra; nó không tự tạo DLQ, replay hay exactly-once. Nếu một failed message quan trọng phải sống qua restart, cần consumer lưu bền, broker hoặc MessageStore và policy retry rõ.

Nếu ingress nhận dữ liệu chưa tin cậy, không copy nguyên header **errorChannel** từ client. Giá trị này có thể làm đổi nơi lỗi được gửi, làm lộ thông tin hoặc che khuất lỗi.

## 12. Gateway và request/reply: dùng Service Activator có kết quả

Một Gateway chuyển lời gọi phương thức Java thành request message, thường đợi một reply tương ứng. Gateway **không bắt buộc kết thúc ở Transformer**: endpoint trả reply có thể là Service Activator.

Ví dụ interface gateway:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
interface OrderGateway {
    @Gateway(requestChannel = "orderGatewayRequestsChannel")
    PlacementReceipt place(NormalizedOrder order);
}
~~~

Endpoint:

~~~java
@Bean
IntegrationFlow gatewayOrderFlow(OrderPlacementService service) {
    return IntegrationFlow.from("orderGatewayRequestsChannel")
            .handle(NormalizedOrder.class,
                    (order, headers) ->
                            service.placeAndReturnReceipt(order))
            .get();
}
~~~

Trong ngữ cảnh Gateway, framework có thể dùng **replyChannel header** của request khi handler tạo reply nhưng endpoint không có outputChannel tường minh. Cần cấu hình component scan/gateway registration, channel bean và timeout phù hợp; đây là đoạn minh họa ghép vào Spring context có cấu hình messaging đầy đủ.

**Không thay endpoint trên bằng one-way Service Activator** rồi kỳ vọng Gateway tự biết đặt hàng thành công. Nếu handler không trả reply, caller có thể chờ đến timeout hoặc nhận kết quả thiếu tùy hợp đồng.

### 12.1. Gateway gọi Transformer để chuẩn hóa trước khi trả reply?

Hoàn toàn hợp lệ nếu yêu cầu duy nhất là chuyển RawOrder thành NormalizedOrder và trả dữ liệu đã chuẩn hóa:

~~~text
Gateway<RawOrder, NormalizedOrder>
  -> Transformer
  -> replyChannel
~~~

Khi yêu cầu là **thực hiện đặt đơn và trả receipt**:

~~~text
Gateway<RawOrder, PlacementReceipt>
  -> Transformer
  -> Service Activator trả PlacementReceipt
  -> replyChannel
~~~

Luồng thứ hai thể hiện chính xác nơi nghiệp vụ có side effect. Đừng gọi service ghi DB ngay trong Transformer chỉ vì muốn giảm bớt một endpoint.

## 13. Unit test cho Transformer: không cần Spring context

Vì Transformer thuần Java, unit test phải kiểm tra output hoặc mã lỗi mà không cần Spring Integration chạy.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderNormalizerTest {
    private final OrderNormalizer normalizer = new OrderNormalizer();

    @Test
    void convertsAmountAndUppercasesCountry() {
        RawOrder raw = new RawOrder(
                "evt-101", "ORD-101", "1250000", "vn");

        NormalizedOrder output = normalizer.normalize(raw);

        assertEquals("evt-101", output.eventId());
        assertEquals("ORD-101", output.orderId());
        assertEquals(new BigDecimal("1250000"), output.amountVnd());
        assertEquals("VN", output.countryCode());
    }

    @Test
    void malformedAmountFailsWithoutProducingOutput() {
        RawOrder raw = new RawOrder(
                "evt-102", "ORD-102", "abc", "VN");

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> normalizer.normalize(raw));
        assertEquals("INVALID_AMOUNT_FORMAT", error.getMessage());
    }

    @Test
    void rejectsNegativeOrFractionalVnd() {
        IllegalArgumentException negative = assertThrows(
                IllegalArgumentException.class,
                () -> normalizer.normalize(
                        new RawOrder(
                                "evt-103", "ORD-103", "-10", "VN")));
        assertEquals("INVALID_AMOUNT_VALUE", negative.getMessage());

        assertThrows(IllegalArgumentException.class,
                () -> normalizer.normalize(
                        new RawOrder(
                                "evt-104", "ORD-104", "3.5", "VN")));
    }
}
~~~

Unit test chứng minh phép biến đổi và xử lý input lỗi; nó **không** chứng minh hai channel đã nối với nhau hoặc Service Activator đã thực hiện đúng thao tác.

## 14. Integration test: Transformer tạo output, Service Activator tạo effect

Ví dụ dùng DirectChannel đồng bộ và một service kiểm thử ghi nhận số lời gọi. Trong production, service thật cần database/API và idempotency tương ứng.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TransformerServiceActivatorTest.Config.class)
class TransformerServiceActivatorTest {

    static class RecordingService implements OrderPlacementService {
        final List<String> calls = new CopyOnWriteArrayList<>();

        @Override
        public void place(NormalizedOrder order) {
            calls.add("one-way:" + order.eventId());
        }

        @Override
        public PlacementReceipt placeAndReturnReceipt(
                NormalizedOrder order) {
            calls.add("reply:" + order.eventId());
            return new PlacementReceipt(order.orderId(), "ACCEPTED");
        }
    }

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        RecordingService service() {
            return new RecordingService();
        }

        @Bean
        MessageChannel rawTestInput() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel receiptTestInput() {
            return new DirectChannel();
        }

        @Bean
        QueueChannel receiptTestOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow oneWayFlow(RecordingService service) {
            OrderNormalizer normalizer = new OrderNormalizer();
            return IntegrationFlow.from("rawTestInput")
                    .transform(RawOrder.class, normalizer::normalize)
                    .handle(NormalizedOrder.class, (order, headers) -> {
                        service.place(order);
                        return null;
                    })
                    .get();
        }

        @Bean
        IntegrationFlow replyFlow(RecordingService service) {
            return IntegrationFlow.from("receiptTestInput")
                    .handle(NormalizedOrder.class, (order, headers) ->
                            service.placeAndReturnReceipt(order))
                    .channel("receiptTestOutput")
                    .get();
        }
    }

    @Autowired
    @Qualifier("rawTestInput")
    MessageChannel rawInput;

    @Autowired
    @Qualifier("receiptTestInput")
    MessageChannel receiptInput;

    @Autowired
    @Qualifier("receiptTestOutput")
    QueueChannel receipts;

    @Autowired
    RecordingService service;

    @BeforeEach
    void reset() {
        service.calls.clear();
        while (receipts.receive(0) != null) {
            // Dọn queue của test trước nếu context được tái sử dụng.
        }
    }

    @Test
    void transformerFeedsOneWayServiceActivator() {
        RawOrder raw = new RawOrder(
                "evt-201", "ORD-201", "90000", "vn");

        assertTrue(rawInput.send(
                MessageBuilder.withPayload(raw).build()));

        assertEquals(List.of("one-way:evt-201"), service.calls);
    }

    @Test
    void malformedInputNeverCallsOrderService() {
        RawOrder raw = new RawOrder(
                "evt-202", "ORD-202", "not-a-number", "VN");

        assertThrows(RuntimeException.class,
                () -> rawInput.send(
                        MessageBuilder.withPayload(raw).build()));

        assertTrue(service.calls.isEmpty());
    }

    @Test
    void serviceActivatorCanProduceAReply() {
        NormalizedOrder order = new NormalizedOrder(
                "evt-203", "ORD-203",
                new java.math.BigDecimal("75000"), "VN");

        assertTrue(receiptInput.send(
                MessageBuilder.withPayload(order).build()));

        Message<?> response = receipts.receive(0);
        assertNotNull(response);
        PlacementReceipt receipt =
                (PlacementReceipt) response.getPayload();

        assertEquals("ORD-203", receipt.orderId());
        assertEquals("ACCEPTED", receipt.status());
        assertEquals(List.of("reply:evt-203"), service.calls);
        assertNull(receipts.receive(0));
    }
}
~~~

**Test chứng minh:**

- Transform tạo output đủ hợp đồng để Service Activator nhận được.
- Input sai làm transform thất bại và **không gọi service**.
- Service Activator có thể trả một PlacementReceipt khi được thiết kế request/reply.
- Một Service Activator kết thúc one-way **không cần tạo reply**.

Đây chỉ là integration test trong một Spring context với DirectChannel. Nó **không** chứng minh idempotency sau broker redelivery hoặc độ bền transaction sau restart. Khi cần đảm bảo những đặc tính đó, phải kiểm thử repository/broker thực tế với unique constraint và failover.

## 15. Bài test phản ví dụ: không dùng null ở Transformer

Có thể thiết kế một flow kiểm thử riêng như sau:

~~~java
// Chỉ dùng trong test về hợp đồng lỗi, không triển khai production.
@Bean
IntegrationFlow illegalTransformerFlow() {
    return IntegrationFlow.from("illegalTransformInput")
            .transform(String.class, value -> (String) null)
            .channel("unusedOutput")
            .get();
}
~~~

Khi message String đi qua illegalTransformInput, kết quả null phải được coi là lỗi transformation, không phải Filter discard. Test có thể kiểm tra RuntimeException và root cause/wrapper phù hợp với phiên bản Spring Integration, đồng thời xác nhận unusedOutput không nhận message.

Đừng thêm một Service Activator one-way chỉ để “nuốt lỗi” của Transformer: muốn loại message theo điều kiện, dùng Filter trước bước transform hoặc một discard/error flow rõ ràng.

## 16. Ma trận lựa chọn endpoint trong tình huống thực tế

| Nhu cầu | Pattern phù hợp | Lý do |
| --- | --- | --- |
| Chuyển JSON String thành OrderDto | Transformer | Thay đổi cấu trúc dữ liệu |
| Chuyển amountText sang BigDecimal | Transformer | Chuẩn hóa dữ liệu |
| Map schema v1 sang schema v2 | Transformer | Đổi biểu diễn message |
| Ẩn bớt trường khi gửi dữ liệu ra ngoài | Transformer | Chiếu sang output schema thích hợp |
| Giữ/loại event theo điều kiện | Filter | Không phải phép biến đổi |
| Chọn kênh đơn hàng cần review | Router | Quyết định destination |
| Lưu đơn hàng vào database | Service Activator | Side effect nghiệp vụ |
| Lấy báo giá từ service ngoài và trả kết quả | Gateway hoặc Service Activator có reply | Gọi hành vi/dịch vụ có I/O |
| Gửi SMS nhưng không đợi reply | Service Activator one-way hoặc adapter gửi SMS | Lệnh có side effect |
| Đặt hàng và trả biên nhận | Service Activator có reply | Hành động nghiệp vụ trả kết quả |
| Gửi một event đến nhiều đích theo điều kiện | Recipient List | Fan-out |
| Tách một đơn thành các line item | Splitter | Sinh nhiều message con |
| Ghép kết quả nhiều line item | Aggregator | Nhóm và release results |
| Đổi các headers đã kiểm tra | Header Enricher/Transformer | Metadata transformation có hợp đồng |
| Gọi cùng một API nhiều lần với retry | Service Activator/Gateway + Retry Advice | Retry cần quản lý idempotency |

### 16.1. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A{"Bước cần làm gì?"} -->|"Chỉ đổi dữ liệu"| T["Transformer"]
    A -->|"Chỉ quyết định giữ/loại"| F["Filter"]
    A -->|"Chọn đường đi"| R["Router"]
    A -->|"Gọi thao tác nghiệp vụ"| S{"Có cần reply?"}
    S -->|"Không"| O["Service Activator one-way"]
    S -->|"Có"| Q["Service Activator reply-producing"]
    T --> N{"Có thể trả null?"}
    N -->|"Có thể không có dữ liệu hợp lệ"| G["Validate/Filter hoặc báo lỗi trước"]
    N -->|"Không"| DONE["Trả output không null"]
~~~

Khi một thao tác vừa chuyển đổi dữ liệu vừa có side effect, ưu tiên tách hai trách nhiệm nếu điều đó giúp quản lý lỗi, retry và transaction. Nhưng không cần tạo nhiều endpoint chỉ vì quy tắc hình thức: nếu việc gọi một service đồng thời trả một DTO là một thao tác nghiệp vụ duy nhất, một Service Activator có reply có thể hoàn toàn phù hợp.

## 17. Các sai lầm thường gặp

### 17.1. Dùng Transformer để gửi email

~~~java
// Phản ví dụ: service bên ngoài có side effect trong Transformer.
EmailPayload transform(OrderAccepted order) {
    emailClient.sendConfirmation(order);
    return new EmailPayload(order.orderId());
}
~~~

Nếu endpoint bị retry, email có thể gửi lần nữa. Một thiết kế rõ hơn:

~~~text
OrderAccepted
  -> Transformer: OrderAccepted -> EmailCommand
  -> Service Activator / outbound adapter: gửi email
  -> Ghi trạng thái + idempotency/retry riêng
~~~

Trong ví dụ này EmailPayload, EmailCommand và emailClient là các kiểu/dependency minh họa; không phải API mặc định của Spring Integration.

### 17.2. Dùng Service Activator để thay cho Filter

~~~java
// Cách dễ gây nhầm trong pipeline nhiều bước:
.handle(RawOrder.class, (raw, headers) ->
        isAllowed(raw) ? raw : null)
~~~

Nếu trả null, Service Activator có thể kết thúc flow one-way. Nhưng người đọc khó nhận ra đó là **một quyết định discard**, và thiếu một discard policy rõ ràng. Khi mục tiêu là loại message, dùng Filter với thông báo/lưu trữ phù hợp.

### 17.3. Dùng Transformer nhưng không trả output hợp lệ

~~~java
.transform(RawOrder.class, raw ->
        raw.amountText() == null ? null : normalizer.normalize(raw))
~~~

Transformer trả null không có nghĩa Filter discard, mà là vi phạm hợp đồng. Hãy ném lỗi cụ thể hoặc dùng Filter trước nếu trường hợp đó được phép bỏ qua.

### 17.4. Trả reply sai kiểu rồi mong Gateway hiểu

Nếu Gateway khai báo phương thức trả PlacementReceipt nhưng Service Activator trả một String tùy ý, framework có thể không chuyển đổi được hoặc phát sinh lỗi mapping/casting tùy ngữ cảnh. Hãy kiểm thử **kiểu reply**, timeout và error handling.

### 17.5. Bỏ qua correlation và headers tin cậy

Transformer không được làm mất businessCorrelationId ở chặng cần truy vết, cũng không nên sao chép header điều khiển từ client chưa xác thực. Service Activator không được dùng tenantId hoặc role do client tự gắn header như bằng chứng ủy quyền.

### 17.6. Đồng nhất một lần gửi với một lần commit

Input đi qua DirectChannel đồng bộ không bảo đảm một transaction bao trùm cả hệ thống ngoài. Input vào QueueChannel cũng không có nghĩa consumer đã hoàn tất. Cần xác định nơi trả acknowledgement và nơi commit side effect.

### 17.7. Bọc một retry chung quanh toàn bộ flow

Nếu Transformer → Place Order → Notification đã thực hiện Place Order thành công nhưng Notification lỗi, retry từ đầu có thể gọi Place Order lại. Cần đặt retry ở đúng bước có thể phục hồi và làm consumer idempotent.

## 18. Bài thực hành: xử lý đơn xuất kho

Thiết kế một luồng nhận:

~~~java
record RawShipment(
        String eventId,
        String shipmentId,
        String weightGramsText,
        String destinationCountry) {}

record NormalizedShipment(
        String eventId,
        String shipmentId,
        long weightGrams,
        String destinationCountry) {}

record ShipmentReceipt(
        String shipmentId,
        String status) {}
~~~

Hợp đồng nghiệp vụ:

1. Input chứa trọng lượng dạng chuỗi và country code chưa chuẩn hóa.
2. Trọng lượng phải là số nguyên dương và không vượt ngưỡng do nghiệp vụ quy định.
3. Đơn xuất kho hợp lệ cần được **lưu** và **đặt lịch giao hàng**.
4. Một event có thể bị broker giao lại khi consumer crash.
5. Hệ thống phải trả receipt nếu đi qua Gateway đồng bộ; còn trong flow async phải công bố status tracking.

**Các bước thực hiện**

1. Viết **ShipmentNormalizer** thuần Java nhận RawShipment và trả NormalizedShipment. Không gọi database/HTTP.
2. Viết unit test cho input đúng, weightText không parse được, weight âm, quá ngưỡng và countryCode không hợp lệ.
3. Tạo **ShipmentSchedulingService** có hai phương thức: schedule() one-way và scheduleWithReceipt().
4. Khai báo IntegrationFlow với **.transform()** rồi **.handle()**; kiểm thử output của Transformer và số lần gọi service.
5. Tạo request/reply flow với Service Activator trả ShipmentReceipt, kiểm thử QueueChannel hoặc Gateway reply.
6. Cố ý cho Transformer trả null rồi quan sát lỗi transformation trong integration test.
7. Đổi input sang ExecutorChannel và kiểm tra khác biệt của đường xử lý exception/ErrorMessage.
8. Thiết kế idempotency key theo **tenant + eventId + logicalActionId** cho thao tác schedule.
9. Mô phỏng schedule thành công rồi mất reply; retry phải không tạo hai lịch giao hàng.
10. Thêm metrics riêng cho transform failures, service failures và duplicate side effects được ngăn.

### Câu hỏi phân tích

1. Một method vừa parse weight vừa gọi DB có nên được đặt trong Transformer không? Vì sao?
2. Nếu cần bỏ các event chỉ dùng để thống kê, Filter hay Transformer phù hợp hơn?
3. Có thể dùng Service Activator trả ShipmentReceipt mà không có Transformer sau nó không?
4. Khi Gateway đồng bộ nhận null từ Service Activator, caller sẽ biết kết quả thế nào?
5. Nếu Service Activator đã commit DB rồi downstream lỗi, retry ở phạm vi nào là hợp lý?
6. Vì sao Transformer trả null khác với Service Activator one-way trả null?
7. Những header nào cần kiểm soát khi message từ HTTP được đưa vào flow?
8. Nếu một message con không được Transformer trả output, Aggregator phải xử lý ra sao?

## 19. Checklist trước khi phát hành

- Phần **chuyển đổi payload** và phần **thao tác nghiệp vụ** được phân định rõ.
- Transformer luôn trả output không null khi thành công; input sai có lỗi phân loại.
- Filter được dùng khi ý định là **giữ hoặc loại** message.
- Service Activator one-way chỉ dùng khi không cần reply ở chặng đó.
- Service Activator reply-producing có hợp đồng kết quả rõ cho Gateway/downstream.
- Dữ liệu có kiểu rõ ràng, tránh ép kiểu mơ hồ và trả reply sai type.
- Headers cần thiết cho reply/error/correlation được giữ theo đúng trust boundary.
- Channel được lựa chọn theo semantics đồng bộ/bất đồng bộ và có consumer thật.
- Transaction, retry và idempotency được đặt tại các side effect quan trọng.
- Error channel và quarantine có consumer/retention phù hợp; không mặc định durable.
- Có unit test cho Transformer và integration test cho các loại endpoint.
- Test bao phủ dữ liệu không hợp lệ, null result, no-reply và reply hợp lệ.
- Metrics/log phân biệt lỗi **transform** với lỗi **service operation** và lỗi **downstream dispatch**.

**Kết luận:** Transformer và Service Activator đều có thể xuất hiện như một hàm nhận message và trả kết quả trong Spring Integration, nhưng chúng biểu đạt **hai hợp đồng khác nhau**. Dùng **Transformer** cho phép biến đổi dữ liệu phải tạo output; dùng **Service Activator** để kích hoạt một hành vi dịch vụ, có hoặc không có reply. Khi tách đúng trách nhiệm và xác định rõ ranh giới retry, transaction và Gateway, các luồng Router–Filter–Transformer–Service Activator dễ kiểm thử, quan sát và phục hồi hơn.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Transformers](https://docs.spring.io/spring-integration/reference/transformer.html): hợp đồng Transformer, output, null result, annotation và Java DSL.
- [Spring Integration Reference — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): cách gọi service, reply và MessageHandler.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request/reply và replyChannel.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): exception, DirectChannel, ExecutorChannel và ErrorMessage.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): .transform(), .handle(), IntegrationFlow và endpoint.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): Channel semantics, transaction boundary và async dispatch.
- [Enterprise Integration Patterns — Message Translator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html): nền tảng khái niệm Transformer.
- [Enterprise Integration Patterns — Messaging Adapter](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingAdapter.html): nền tảng kết nối ứng dụng dịch vụ với hệ thống messaging.
