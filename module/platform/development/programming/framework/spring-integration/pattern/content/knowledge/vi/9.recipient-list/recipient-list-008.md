# Tránh gửi trùng đến cùng một recipient

## 1. Bài toán: fan-out đúng nhưng không xử lý lặp

Trong chương **Recipient list** của module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai các Enterprise Integration Patterns bằng Spring Integration để tạo các luồng thông điệp ít phụ thuộc, dễ mở rộng. Một sự kiện có thể được định tuyến qua Router tới nhiều nhánh, sau đó được Filter, Transformer, Gateway hoặc Service Activator xử lý. Khi thêm retry, error channel và correlation, việc kiểm soát gửi trùng trở thành yêu cầu thiết yếu để kết quả có thể dự đoán và kiểm thử.

Giả sử hệ thống phát sự kiện **payment.completed** cho ba recipient:

- **auditEventsChannel**: ghi nhận giao dịch vào sổ kiểm toán;
- **riskEventsChannel**: xem xét giao dịch có giá trị lớn;
- **notificationEventsChannel**: phát thông báo cho khách hàng khi được yêu cầu.

Một event có thể đến cả ba kênh: đó là **fan-out hợp lệ**, không phải trùng. Trùng là khi **cùng recipient** nhận hoặc thực hiện **cùng tác động nghiệp vụ của cùng event** nhiều lần ngoài hợp đồng.

Ví dụ: event **evt-501** phải gửi một lần đến audit và một lần đến risk. Nếu audit ghi hai bản ghi vì luồng vô tình đưa evt-501 vào audit hai lần, hoặc vì cả router bị retry sau khi nhánh audit đã thành công, chúng ta có lỗi trùng cần xử lý.

Sau bài học, bạn có thể:

1. Phân biệt **trùng destination trong topology**, **trùng message khi giao nhận** và **trùng hiệu ứng nghiệp vụ**.
2. Thiết kế một RecipientListRouter không khai báo lặp recipient khi có nhiều điều kiện.
3. Xây dựng khóa idempotency theo đúng phạm vi **recipient + eventId** thay vì dùng tùy tiện MessageHeaders.ID.
4. Hiểu vì sao dedup trước router không khôi phục được nhánh lỗi một phần.
5. Áp dụng Idempotent Receiver, MetadataStore, transaction và unique constraint ở mức phù hợp.
6. Kiểm thử fan-out, retry, đồng thời, mất kết nối và xử lý lặp theo từng recipient.

## 2. Định nghĩa “trùng” trước khi chọn giải pháp

Trong Spring Integration, **RecipientListRouter** có nhiệm vụ chọn danh sách channel nhận message; mỗi recipient có thể là một destination vô điều kiện hoặc có selector. Message có thể gửi tới nhiều recipient phù hợp. Router **không thay thế một idempotent consumer**.

| Tình huống | Có phải lỗi trùng? | Giải thích |
| --- | --- | --- |
| evt-501 đến audit và risk mỗi nơi một lần | Không | Hai recipient có trách nhiệm khác nhau |
| evt-501 đến audit hai lần vì hai tuyến hội tụ | Có thể | Cùng đích nhận cùng event ngoài dự kiến |
| evt-501 gửi lại sau lỗi nhưng audit đã xử lý trước đó | Có thể | Redelivery phải được xử lý an toàn |
| evt-501 và evt-502 cùng paymentId nhưng là hai sự kiện khác nhau | Không nhất thiết | Có thể là hai thay đổi trạng thái hợp lệ |
| Một event được giao lặp nhưng handler bỏ qua bản lặp | Có giao nhận lặp, không có hiệu ứng lặp | Idempotency giảm rủi ro side effect |
| Một event tạo hai email do người dùng chủ động yêu cầu gửi lại | Phụ thuộc nghiệp vụ | Cần phân biệt thao tác mới với retry cũ |

Chúng ta sẽ phân biệt ba tầng:

**Tầng 1 — Topology:** có bao nhiêu đường/recipient trong cấu hình thực sự dẫn tới cùng destination? Câu hỏi này được giải quyết bằng thiết kế và kiểm thử wiring.

**Tầng 2 — Delivery:** cùng event có thể tới một consumer nhiều lần không? Điều này liên quan đến retry, broker redelivery, failover và vận hành.

**Tầng 3 — Effect:** consumer có tạo tác động nghiệp vụ trùng không? Điều này liên quan đến khóa idempotency, transaction, database constraint và API của hệ thống đích.

Một hệ thống mạnh thường phải xử lý **cả ba**, thay vì chỉ đặt một Set ở router rồi coi vấn đề đã được giải quyết.

~~~mermaid
flowchart TD
    E["PaymentCompleted evt-501"] --> R["RecipientListRouter"]
    R --> A["Audit recipient"]
    R --> F["Risk recipient"]
    R --> N["Notification recipient"]
    A --> D1{"Đã xử lý evt-501<br/>cho audit?"}
    F --> D2{"Đã xử lý evt-501<br/>cho risk?"}
    N --> D3{"Đã xử lý evt-501<br/>cho notification?"}
    D1 -->|"Chưa"| H1["Ghi audit"]
    D2 -->|"Chưa"| H2["Tạo risk review"]
    D3 -->|"Chưa"| H3["Gửi thông báo"]
    D1 -->|"Đã rồi"| SK1["Bỏ qua an toàn"]
    D2 -->|"Đã rồi"| SK2["Bỏ qua an toàn"]
    D3 -->|"Đã rồi"| SK3["Bỏ qua an toàn"]
~~~

## 3. Các nguyên nhân gửi trùng thường gặp

### 3.1. Khai báo lặp một destination

Khi một topology được sinh từ file cấu hình hoặc nhiều module cùng đăng ký recipient, cùng tên channel có thể xuất hiện nhiều lần.

~~~java
// Minh họa cấu hình đáng ngờ: audit được nhắc lại.
IntegrationFlow.from("paymentEventsChannel")
        .routeToRecipients(r -> r
                .recipient("auditEventsChannel")
                .recipient("riskEventsChannel")
                .recipient("auditEventsChannel"))
        .get();
~~~

Không nên dựa vào giả định rằng framework sẽ tự loại bỏ tất cả entry trùng ở mọi phiên bản, mọi loại recipient và mọi đường cấu hình. **Hợp đồng ứng dụng nên cấm khai báo trùng destination** và có test kiểm tra các channel thực nhận.

Nếu hai module cùng muốn audit một sự kiện, cần xác định chúng có thực sự là **hai chức năng khác nhau** hay chỉ là một recipient được thêm hai lần. Hai chức năng độc lập nên có **recipient identity** và channel riêng; nếu cùng một tác động audit, chỉ nên có một đường trực tiếp.

### 3.2. Hai selector cùng đưa vào một channel

Giả sử audit cần nhận event khi **khách hàng VIP hoặc đơn quốc tế**. Không nên cấu hình hai recipient riêng có cùng channel với hai điều kiện rồi mặc nhiên kỳ vọng kết quả chỉ có một lần gửi:

~~~java
// Dễ phát sinh cấu hình lặp recipient auditChannel.
.routeToRecipients(r -> r
        .recipientMessageSelector("auditChannel",
                m -> isVip((OrderEvent) m.getPayload()))
        .recipientMessageSelector("auditChannel",
                m -> isInternational((OrderEvent) m.getPayload())))
~~~

Thay vào đó hãy **gộp điều kiện theo từng channel**:

~~~java
.routeToRecipients(r -> r
        .recipientMessageSelector("auditChannel", m -> {
            OrderEvent event = (OrderEvent) m.getPayload();
            return isVip(event) || isInternational(event);
        }))
~~~

Hai đoạn này là **mảnh DSL minh họa**, không phải phương thức Java đứng độc lập. Điều cần giữ là: **một recipient identity, một định nghĩa điều kiện rõ ràng**. Nếu hai nhánh cần side effect khác nhau dù cùng nhãn “audit”, hãy đặt tên và hợp đồng riêng thay vì gộp.

### 3.3. Hai nhánh hội tụ vào cùng một handler

~~~mermaid
flowchart LR
    E["Event"] --> R["RecipientListRouter"]
    R --> A["auditChannel"]
    R --> B["otherChannel"]
    B --> T["Transformer / Router"]
    T --> A
    A --> H["Audit handler"]
~~~

Trong topology này, audit có thể nhận message **một lần trực tiếp** và **một lần gián tiếp qua otherChannel**. Kiểm tra danh sách recipient trực tiếp là chưa đủ: phải kiểm tra **toàn bộ đồ thị channel và endpoint**, nhất là với Router lồng nhau, PublishSubscribeChannel và Gateway.

### 3.4. Retry toàn bộ fan-out sau lỗi một phần

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as RecipientListRouter
    participant A as Audit
    participant N as Notification
    P->>R: evt-501, lần 1
    R->>A: evt-501
    A-->>R: Đã ghi audit
    R->>N: evt-501
    N--xR: Lỗi tạm thời
    R--xP: Exception
    P->>R: Retry evt-501
    R->>A: evt-501 lần nữa
    Note over A: Cần idempotent receiver
~~~

Đây là nguyên nhân phổ biến nhất trong hệ thống tích hợp nhiều đích. **Retry toàn router** có thể lặp lại các nhánh đã hoàn tất trước khi gặp lỗi.

### 3.5. Redelivery, nhiều producer và concurrency

Ngay cả khi cấu hình mỗi recipient chỉ một lần, event có thể được phát lại vì:

- Producer retry khi chưa nhận acknowledgement.
- Broker giao lại sau consumer crash trước ack.
- Một scheduler đọc lại bản ghi chưa đánh dấu xử lý.
- Hai instance cùng xử lý một hàng đợi do lock/lease sai.
- Hai request đồng thời tạo cùng event nghiệp vụ.

**DirectChannel** không tự deduplicate event. **ExecutorChannel** và **QueueChannel** cũng không tự tạo bảo đảm exactly-once effect. Một channel chịu trách nhiệm truyền message, không tự quyết định tác dụng nghiệp vụ đã được thực hiện.

## 4. Khai báo một lần cho mỗi recipient trong Java DSL

Ví dụ sau minh họa routing có ba đích rõ ràng. **audit** luôn nhận, **risk** nhận giao dịch lớn, **notification** nhận khi người dùng cho phép gửi thông báo.

### 4.1. Model sự kiện và điều kiện

~~~java
import java.math.BigDecimal;

record PaymentCompleted(
        String eventId,
        String paymentId,
        BigDecimal amountVnd,
        boolean notifyCustomer) {}

final class PaymentRoutingRules {
    private static final BigDecimal RISK_LIMIT =
            new BigDecimal("10000000");

    private PaymentRoutingRules() {}

    static boolean requiresRisk(PaymentCompleted event) {
        return event.amountVnd() != null
                && event.amountVnd().compareTo(RISK_LIMIT) >= 0;
    }
}
~~~

**eventId** là định danh ổn định của **một sự kiện logic**, không phải ID mới mỗi lần broker giao lại. Một paymentId có thể có nhiều sự kiện thuộc các loại khác nhau; không dùng paymentId đơn lẻ làm khóa dedup cho toàn bộ lịch sử thanh toán.

### 4.2. Cấu hình flow

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class PaymentRecipientFlowConfig {

    @Bean
    MessageChannel paymentEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel auditEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel riskEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel notificationEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow paymentRecipientsFlow() {
        return IntegrationFlow.from("paymentEventsChannel")
                .routeToRecipients(r -> r
                        // Mỗi channel được đăng ký đúng một lần.
                        .recipient("auditEventsChannel")
                        .recipientMessageSelector("riskEventsChannel", m ->
                                PaymentRoutingRules.requiresRisk(
                                        (PaymentCompleted) m.getPayload()))
                        .recipientMessageSelector(
                                "notificationEventsChannel", m ->
                                        ((PaymentCompleted) m.getPayload())
                                                .notifyCustomer()))
                .get();
    }
}
~~~

Flow này cố tình **không bật applySequence** vì ba recipient xử lý độc lập, không cần Aggregator ghép kết quả. **applySequence=true** tạo metadata phục vụ grouping/sequence, **không** phải công tắc khử trùng.

Tương tự, **ignoreSendFailures=true** không chống duplicate; nó có thể cho router tiếp tục những nhánh còn lại khi gặp lỗi gửi đồng bộ, nhưng không bảo đảm nhánh lỗi được xử lý và không phát hiện được tất cả lỗi async. Với audit bắt buộc, chỉ bật best effort khi đã có cơ chế phục hồi và quan sát tương ứng.

### 4.3. Phân biệt producer và recipient

Producer chỉ gửi một event vào **paymentEventsChannel**:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

PaymentCompleted completed = new PaymentCompleted(
        "evt-501",
        "payment-501",
        new BigDecimal("12500000"),
        true);

Message<PaymentCompleted> message = MessageBuilder
        .withPayload(completed)
        .setHeader("eventType", "payment.completed")
        .setHeader("businessCorrelationId", completed.paymentId())
        .build();

// paymentEventsChannel là bean đã được inject từ Spring.
paymentEventsChannel.send(message);
~~~

Đối với evt-501, **audit, risk, notification** đều được chọn. Đây là ba lần gửi tới **ba recipient khác nhau**, không phải ba bản ghi trùng.

Trong sản phẩm, cần xác thực input và eventId, không tin giá trị định danh do client tùy ý nhập để có thể bỏ qua side effect của người khác. Event ID phải gắn với một sự kiện thật; yêu cầu từ cùng nguồn cần có quy tắc idempotency riêng.

## 5. Chặn trùng từ cấu hình và topology

### 5.1. Chuẩn hóa danh sách recipient trước khi đưa vào router

Khi danh sách channel được kết hợp từ nhiều cấu hình, nên xác nhận **mỗi destination xuất hiện một lần** bằng một phép kiểm soát có chủ đích:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class RecipientConfigValidator {
    private RecipientConfigValidator() {}

    static void requireDistinct(List<String> channelNames) {
        Set<String> seen = new HashSet<>();
        for (String name : channelNames) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Recipient name trống");
            }
            if (!seen.add(name)) {
                throw new IllegalArgumentException(
                        "Recipient bị khai báo lặp: " + name);
            }
        }
    }
}
~~~

Ví dụ:

~~~java
List<String> destinations = List.of(
        "auditEventsChannel",
        "riskEventsChannel",
        "auditEventsChannel");

// Fail fast thay vì âm thầm dùng cấu hình mơ hồ.
RecipientConfigValidator.requireDistinct(destinations);
// Ném IllegalArgumentException với auditEventsChannel.
~~~

**Fail fast** hợp lý khi trùng destination luôn là lỗi cấu hình. Nếu nghiệp vụ thật sự muốn **gộp các cấu hình tùy chọn**, có thể dùng LinkedHashMap với khóa là **recipient identity** rồi gộp nhiều điều kiện thành **một predicate OR**. Tuy nhiên, chỉ gộp khi các entry thực sự cùng một tác động nghiệp vụ.

### 5.2. Điều kiện chồng lấn không được xem như hai lệnh gửi

Một recipient có thể phù hợp vì nhiều lý do: VIP, đơn quốc tế, ưu tiên cao. Hãy mô tả những lý do đó trong **một selector** và log lý do chọn recipient nếu cần:

~~~java
static boolean shouldAudit(OrderEvent event) {
    return isVip(event)
            || isInternational(event)
            || isPriority(event);
}
~~~

Nếu cần biết điều kiện nào đúng, có thể trả một đối tượng **RoutingDecision** chứa tập lý do và recipient identity; đừng tạo thêm recipient trùng chỉ để ghi nhận lý do.

### 5.3. Kiểm soát recipient cập nhật động

RecipientListRouter hỗ trợ quản lý recipient lúc runtime (ví dụ qua API quản lý/Control Bus khi cấu hình). Nếu có quy trình tự động cập nhật, yêu cầu operation **add recipient** phải idempotent theo identity hoặc phải đối chiếu với một **source of truth**. Nếu cùng lệnh cập nhật được gửi lại, topology không nên thay đổi ngoài ý định.

Không mở API sửa recipient trực tiếp cho nguồn không tin cậy. Danh sách channel có thể là một phần ranh giới bảo mật: client không được quyền thêm channel nội bộ hoặc bỏ nhánh kiểm toán.

### 5.4. Kiểm tra toàn đồ thị, không chỉ danh sách đầu vào

Ngoài duplicate recipient trong một router, cần review:

- Có hai route khác nhau cùng đưa một event vào auditChannel hay không?
- Có PublishSubscribeChannel trung gian cũng subscribe audit handler không?
- Có Retry Advice đặt ngoài toàn bộ fan-out thay vì ở nhánh lỗi không?
- Có producer khác cùng publish một eventId vào flow lần nữa không?
- Một nhánh có sử dụng Gateway quay lại input của chính router không?

**Một channel trùng tên trong sơ đồ không nhất thiết là lỗi**, nhưng nếu cùng event chạm cùng side effect nhiều lần ngoài yêu cầu, cần thay topology hoặc bổ sung consumer idempotent.

## 6. Khóa idempotency nên đại diện cho điều gì?

**Idempotent Receiver** là consumer có thể nhận cùng một yêu cầu nhiều lần nhưng **kết quả tác động nghiệp vụ** không bị nhân lên ngoài hợp đồng. Điều kiện quan trọng nhất là chọn đúng **identity của lần xử lý**.

Với một Recipient List, khóa thường có dạng:

~~~text
idempotencyKey = recipientId + ":" + eventId
~~~

Ví dụ:

| Recipient | Event ID | Khóa idempotency |
| --- | --- | --- |
| audit | evt-501 | audit:evt-501 |
| risk | evt-501 | risk:evt-501 |
| notification | evt-501 | notification:evt-501 |
| audit | evt-502 | audit:evt-502 |

Lần gửi lại **evt-501** đến audit mang cùng khóa **audit:evt-501** và có thể được bỏ qua nếu audit đã hoàn tất. Nhưng **risk:evt-501** vẫn là tác vụ **khác**, có thể cần thực hiện ngay cả khi audit đã xong.

### 6.1. Vì sao không dedup toàn cục trước router?

Giả sử lần xử lý đầu: audit thành công, risk thất bại. Nếu một cổng đầu vào lưu **eventId=evt-501 đã từng thấy** rồi bỏ toàn bộ event khi producer retry, risk sẽ **không bao giờ nhận lại**.

~~~mermaid
flowchart TD
    A["Replay evt-501"] --> G{"Global dedup<br/>đã thấy evt-501?"}
    G -->|"Đã thấy"| X["Loại toàn bộ"]
    X --> L["Risk chưa xử lý: bị bỏ sót"]
    A --> D{"Per-recipient dedup"}
    D --> AU["Audit đã xong: skip"]
    D --> RI["Risk chưa xong: xử lý"]
~~~

**Quy tắc thiết kế:** nếu nhiều recipient có trạng thái xử lý độc lập, việc dedup cũng cần tính đến **từng recipient**. Dedup ở producer/ingress chỉ thích hợp khi toàn bộ tác vụ liên quan đã được giao vào một nơi lưu bền tin cậy hoặc đã có cơ chế tracking từng branch.

### 6.2. Phân biệt các loại ID

| Trường | Phạm vi | Dùng để dedup? |
| --- | --- | --- |
| **MessageHeaders.ID** | ID kỹ thuật của một Spring Message | Không nên dùng làm business idempotency key mặc định |
| **eventId** | Một sự kiện logic đã được định danh ổn định | Thường là thành phần quan trọng |
| **paymentId/orderId** | Đối tượng nghiệp vụ | Cần kết hợp eventType/version nếu một đối tượng có nhiều sự kiện |
| **correlationId** | Liên kết nhóm message/luồng | Không tự đảm bảo một tác động chỉ một lần |
| **sequenceNumber/sequenceSize** | Hỗ trợ grouping khi Splitter/Aggregator | Không tự chống duplicate processing |
| **recipientId** | Một trách nhiệm xử lý cụ thể | Kết hợp eventId để tách trạng thái từng nhánh |
| **attemptId** | Một lần thử vận chuyển/xử lý | Không thay thế eventId vì retry có attemptId mới |

Đừng tạo **eventId mới** mỗi khi retry một sự kiện cũ. Ngược lại, hai yêu cầu nghiệp vụ thật sự khác nhau phải có identity khác nhau; nếu chúng dùng chung khóa, cơ chế dedup có thể bỏ nhầm thao tác hợp lệ.

### 6.3. Khóa phải đến từ nguồn đáng tin

Nếu một client có thể chọn tùy ý eventId giống ID của người khác, nó có thể khiến yêu cầu hợp lệ bị đánh dấu trùng. Vì vậy producer phải xác thực request, gắn định danh bền vững theo miền dữ liệu đã được kiểm chứng, hoặc dùng server event ID được quản lý theo hợp đồng.

Không in khóa chứa thông tin bí mật vào log. Khi dùng một kho idempotency chung giữa nhiều tenant, cần đưa **tenantId đáng tin** vào phạm vi khóa nếu eventId không bảo đảm duy nhất giữa tenant.

## 7. Ví dụ dedup đơn giản trong bộ nhớ

Ví dụ sau cho thấy một thao tác kiểm tra trùng **atomic trong một JVM** bằng một Set đồng thời. Đây là mô hình học thuật để hiểu phạm vi theo recipient, **không phải giải pháp production đảm bảo không mất sự kiện**.

~~~java
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

final class InMemoryRecipientGate {
    private final Set<String> seen =
            ConcurrentHashMap.newKeySet();

    boolean firstTime(String recipientId, String eventId) {
        Objects.requireNonNull(recipientId, "recipientId");
        Objects.requireNonNull(eventId, "eventId");
        if (recipientId.isBlank() || eventId.isBlank()) {
            throw new IllegalArgumentException("Thiếu định danh");
        }
        return seen.add(recipientId + ":" + eventId);
    }
}
~~~

~~~java
InMemoryRecipientGate gate = new InMemoryRecipientGate();

assert gate.firstTime("audit", "evt-501");
assert !gate.firstTime("audit", "evt-501");
assert gate.firstTime("risk", "evt-501");
~~~

**Ưu điểm:** thao tác add của concurrent set có tính nguyên tử trong phạm vi JVM; nhiều thread cùng tranh một khóa thì chỉ một lời gọi nhận true.

**Giới hạn nghiêm trọng:**

1. **Restart:** Set mất dữ liệu, bản replay có thể xử lý lại.
2. **Nhiều instance:** mỗi instance có Set riêng, không loại trùng xuyên cụm.
3. **Đánh dấu quá sớm:** firstTime() thêm khóa **trước khi effect hoàn thành**. Nếu handler ném lỗi sau khi thêm khóa, retry có thể bị chặn dù tác vụ chưa thành công.
4. **Không dọn dữ liệu:** Set lớn dần vô hạn nếu không có retention policy.
5. **Không transaction:** khóa idempotency và tác động DB/HTTP không được commit nguyên tử.

Vì vậy chỉ dùng Set này trong unit test hoặc mô phỏng cục bộ. Không diễn giải nó thành exactly-once delivery.

## 8. Chống tác động trùng trong database bằng transaction

Khi một recipient ghi dữ liệu trong cùng một database, có thể bảo vệ bằng **unique constraint** và **transaction**, để bản ghi nhận diện việc xử lý và side effect được commit cùng nhau.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE recipient_delivery (
    recipient_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL,
    completed_at TIMESTAMPTZ NULL,
    PRIMARY KEY (recipient_id, event_id)
);

CREATE TABLE audit_entry (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(120) NOT NULL UNIQUE,
    payment_id VARCHAR(120) NOT NULL,
    amount_vnd NUMERIC(18, 2) NOT NULL
);
~~~

Mã thao tác ở tầng service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TransactionalAuditConsumer {
    private final DeliveryRepository deliveries;
    private final AuditRepository audits;

    TransactionalAuditConsumer(
            DeliveryRepository deliveries,
            AuditRepository audits) {
        this.deliveries = deliveries;
        this.audits = audits;
    }

    @Transactional
    public void onCompleted(PaymentCompleted event) {
        // INSERT ... ON CONFLICT DO NOTHING.
        // Trả về 1 nếu đã ghi được khóa mới, 0 nếu khóa đã có.
        int acquired = deliveries.tryInsert(
                "audit", event.eventId(), "PROCESSING");
        if (acquired == 0) {
            return; // Đã xử lý hoặc có attempt khác giữ khóa.
        }

        audits.insert(event.eventId(),
                event.paymentId(), event.amountVnd());
        deliveries.markCompleted(
                "audit", event.eventId());
    }
}

interface DeliveryRepository {
    int tryInsert(String recipientId, String eventId, String status);
    void markCompleted(String recipientId, String eventId);
}

interface AuditRepository {
    void insert(String eventId,
                String paymentId,
                java.math.BigDecimal amountVnd);
}
~~~

Đây là **mẫu ứng dụng**: hai repository cần được triển khai; ví dụ giả định chúng sử dụng **cùng transaction manager và database**. Trong transaction đó:

1. Attempt đầu tiên ghi khóa recipient + eventId thành công.
2. Audit effect được tạo và đánh dấu hoàn tất.
3. Nếu một thao tác ném exception làm transaction rollback, **cả khóa xử lý lẫn audit effect** đều không được commit.
4. Attempt khác cùng khóa sẽ chịu sự điều phối của unique constraint/transaction isolation và không tạo bản ghi trùng sau khi commit thành công.

Không dùng một thao tác “SELECT xem có khóa chưa → nếu chưa thì INSERT” không atomic để chống tranh chấp hai thread. Nên dùng unique constraint hoặc CAS/putIfAbsent có hợp đồng concurrency rõ ràng.

### 8.1. Khi effect nằm ngoài database thì sao?

Nếu notification gọi email/HTTP rồi ghi completed vào database, thao tác gửi email **không rollback** khi DB transaction rollback. Ngược lại, ghi completed trước khi gọi email có thể khiến email không bao giờ gửi nếu process chết.

Với dịch vụ ngoài, cân nhắc:

- **Outbox**: ghi ý định thực hiện tác vụ vào DB cùng transaction nghiệp vụ.
- **Worker/consumer**: đọc outbox, retry có giới hạn và quản lý trạng thái.
- **Idempotency key ở phía hệ thống đích** nếu API hỗ trợ, ví dụ eventId + recipientId.
- **Đối soát** khi không thể xác định effect đã diễn ra hay chưa.
- **DLQ/quarantine** cho message đã thử nhiều lần nhưng chưa thành công.

Không hứa exactly-once effect cho hệ thống ngoài chỉ vì có bảng recipient_delivery. Khi API ngoài không hỗ trợ idempotency, có thể cần chấp nhận at-least-once, thêm reconciliation hoặc thiết kế nghiệp vụ chịu được duplicate.

## 9. Idempotent Receiver trong Spring Integration

Spring Integration có **IdempotentReceiverInterceptor** để áp dụng mẫu **Idempotent Receiver** ở endpoint, và **MetadataStoreSelector** để quyết định message đã có một khóa trong metadata store hay chưa.

Quan trọng: **IdempotentReceiverInterceptor mặc định không nhất thiết chặn hoàn toàn duplicate**. Nếu selector bác bỏ message, interceptor có thể gắn header **duplicateMessage=true** rồi vẫn cho handler nhận; để bỏ hoặc chuyển hướng duplicate, cần cấu hình discard channel hoặc chế độ từ chối tương ứng.

### 9.1. Cơ chế kiểm tra metadata

~~~mermaid
flowchart TD
    M["Message tới một recipient"] --> K["Tính idempotency key"]
    K --> S{"MetadataStoreSelector<br/>key đã có?"}
    S -->|"Chưa"| H["Handler xử lý"]
    S -->|"Đã có"| D["Mark duplicate hoặc discard<br/>theo cấu hình"]
    H --> X["Effect / transaction"]
~~~

MetadataStoreSelector thường dựa vào thao tác **putIfAbsent** của một **ConcurrentMetadataStore**. Điều này giúp xử lý xung đột đồng thời tại bước claim key nếu store cung cấp semantics nguyên tử.

**SimpleMetadataStore** mặc định là bộ nhớ cục bộ, không sống qua restart. Nếu có nhiều instance hoặc cần giữ trạng thái sau restart, cân nhắc JdbcMetadataStore, RedisMetadataStore hoặc một store phân tán/bền phù hợp; phải kiểm chứng tính nhất quán, TTL và khả năng giữ key.

### 9.2. Ví dụ dùng MetadataStoreSelector tại endpoint

Ví dụ sau tập trung vào **bộ lọc trùng tại recipient**. Key cần gắn với recipient audit, không dùng một key toàn cục vô tình chặn các recipient khác.

~~~java
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.messaging.Message;

// concurrentMetadataStore phải là bean/store được cấu hình phù hợp.
MetadataStoreSelector selector = new MetadataStoreSelector(
        (Message<?> message) -> {
            PaymentCompleted event =
                    (PaymentCompleted) message.getPayload();
            return "audit:" + event.eventId();
        },
        concurrentMetadataStore);

IdempotentReceiverInterceptor advice =
        new IdempotentReceiverInterceptor(selector);
advice.setDiscardChannel(nullChannel);

// Gắn advice vào endpoint xử lý audit, không gắn chung
// vào đầu router nếu các recipient cần hoàn tất độc lập.
~~~

Đây là **mảnh cấu hình minh họa**, giả định đã có biến concurrentMetadataStore và nullChannel, đồng thời advice còn phải được gắn vào đúng endpoint theo API/cấu hình của phiên bản Spring Integration được sử dụng. Nó không phải một chương trình đứng độc lập.

Nếu không cấu hình discard hay reject, hãy kiểm tra handler có nhận **duplicateMessage** hay không và tự quyết định có được thực hiện side effect. Với **setDiscardChannel(nullChannel)**, duplicate được loại có chủ đích; nên có metric đếm số lần loại, không gọi đó là “sự kiện chưa từng được giao lại”.

**Cảnh báo nghiệp vụ:** MetadataStoreSelector có thể claim key **trước khi effect thành công**. Nếu handler lỗi sau claim, retry có thể bị xem là duplicate. Đây là quyết định rất quan trọng về **at-most-once attempt** và **at-least-once recovery**. Trong flow có side effect bắt buộc, ưu tiên một trạng thái xử lý và transaction rõ ràng, hoặc thiết kế rollback/release/TTL của claim đúng hợp đồng; không chỉ thêm interceptor rồi coi đã có exactly-once.

### 9.3. Nên đặt dedup trước hay sau RecipientListRouter?

| Vị trí | Lợi ích | Nguy cơ |
| --- | --- | --- |
| Trước router | Giảm số lần xử lý message lặp ở mọi nhánh | Có thể làm mất cơ hội phục hồi nhánh từng thất bại |
| Sau router, tại mỗi recipient | Theo dõi trạng thái riêng từng tác vụ | Cần quản lý key và store cho từng recipient |
| Tại database/side-effect boundary | Bảo vệ tác dụng nghiệp vụ ngay nơi phát sinh | Cần transaction/constraint hoặc API idempotent |
| Cả ingress và mỗi recipient | Có thể tối ưu chi phí và vẫn giữ an toàn nếu thiết kế đúng | Phải phân biệt “đã nhận” với “mọi nhánh đã hoàn tất” |

**Lựa chọn thường an toàn hơn:** dedup/idempotency được **định nghĩa tại recipient** và tại nơi ghi effect; optional ingress dedup chỉ dùng khi có một cơ chế phân phối bền đảm bảo event đã được bàn giao cho từng nhánh.

## 10. Thiết kế retry để không gửi lặp vô ý

Trước khi thêm Retry Advice, cần hỏi: **retry điều gì?** Toàn bộ message gửi vào router, chỉ nhánh risk, thao tác HTTP ở một handler, hay giao dịch database?

| Vị trí retry | Tác động | Rủi ro trùng |
| --- | --- | --- |
| Producer gửi lại vào router | Router chọn recipient lại từ đầu | Những nhánh đã thành công có thể được gọi lại |
| Retry quanh toàn bộ router | Toàn bộ fan-out có thể chạy lại | Partial success bị lặp |
| Retry tại riêng notification handler | Chỉ tác vụ notification thử lại | Ít tác động audit/risk hơn, vẫn cần notification idempotent |
| Broker redelivery tới một recipient queue | Recipient đó có thể nhận lại event | Bảo vệ tại consumer và ack đúng |
| Retry thao tác database trong transaction | Có thể rollback rồi thử lại | Bảo vệ bằng unique constraint và ranh giới commit |

### 10.1. Một nhánh thành công, một nhánh thất bại

Đối với audit bắt buộc và notification có thể chậm:

1. Producer ghi **payment.completed** và outbox event trong cùng transaction nếu sự kiện phải tồn tại qua restart.
2. Một dispatcher tạo nhiệm vụ cho từng recipient hoặc phát đến hạ tầng message bền theo hợp đồng.
3. **audit** và **notification** có tiến độ, idempotency key và retry policy riêng.
4. Khi notification thất bại, chỉ thông điệp/tác vụ notification cần retry; audit đã hoàn tất không phải thực hiện lại effect.

~~~mermaid
flowchart LR
    O["Transactional outbox"] --> D["Dispatcher"]
    D --> A["Audit queue"]
    D --> N["Notification queue"]
    A --> AC["Audit consumer<br/>dedup audit:evt"]
    N --> NC["Notification consumer<br/>dedup notification:evt"]
    NC -->|"Transient failure"| RT["Retry + backoff"]
    RT --> NC
~~~

Đây là một **phương án kiến trúc**, không có nghĩa chỉ cấu hình RecipientListRouter là tự tạo outbox, queue bền, ack hay DLQ. Cần triển khai hoặc cấu hình hạ tầng thực.

### 10.2. ignoreSendFailures không thay cho per-recipient retry

Trong RecipientListRouter, **ignoreSendFailures(true)** có thể cho phép tiếp tục gửi các recipient khác khi một lần gửi đồng bộ thất bại. Điều đó hữu ích cho một số luồng best effort, nhưng nó **không** bảo đảm branch lỗi được retry. Ngược lại, nó có thể khiến caller không biết một nhánh quan trọng đã thất bại nếu thiếu giám sát.

Với channel bất đồng bộ, send() thành công chưa chứng minh downstream xử lý thành công. Cần error handling riêng ở worker, poller hoặc adapter.

### 10.3. applySequence và Aggregator không tự khử trùng

Khi bật **applySequence(true)**, router tạo metadata correlation/sequence cho những message được gửi đến các recipient, hữu ích khi downstream Aggregator cần ghép kết quả. Tuy nhiên:

- Hai lần gửi lại cùng sự kiện có thể tạo **hai nhóm phân phối** với correlation khác nhau hoặc làm phát sinh kết quả lặp, tùy pipeline.
- Aggregator vẫn cần release strategy, message store, timeout và chính sách xử lý duplicate/missing result rõ ràng.
- **sequenceNumber** mô tả vị trí trong tập, không phải idempotency key toàn hệ thống.

Không dùng applySequence như một công tắc loại trùng. Khi cần ghép kết quả, phải thiết kế cả **business correlation**, **recipient identity**, **attempt identity** và điều kiện hoàn tất.

## 11. Kiểm thử fan-out: đúng một lần trong một lần gửi

Một test cần chứng minh hai điều:

1. **Một lần send()** với cùng event chọn **đúng tập recipient**, không chọn thừa recipient trong topology hiện tại.
2. **Hai lần send()** với cùng event có thể tạo **hai lần delivery** nếu không có cơ chế dedup; đó là hành vi phải được bảo vệ ở consumer.

Ví dụ dưới đây dùng **QueueChannel** làm đích để lấy message bằng receive(0), không cần tạo Service Activator giả hoặc ngủ thread. Channel chỉ dùng trong test; nó không tạo lưu trữ bền.

### 11.1. Integration test với Spring context

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

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

@SpringJUnitConfig(RecipientDeliveryTest.Config.class)
class RecipientDeliveryTest {

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        MessageChannel testInput() {
            return new DirectChannel();
        }

        @Bean
        QueueChannel testAudit() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel testRisk() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel testNotification() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow recipientFlow() {
            return IntegrationFlow.from("testInput")
                    .routeToRecipients(r -> r
                            .recipient("testAudit")
                            .recipientMessageSelector("testRisk", m ->
                                    PaymentRoutingRules.requiresRisk(
                                            (PaymentCompleted) m.getPayload()))
                            .recipientMessageSelector("testNotification", m ->
                                    ((PaymentCompleted) m.getPayload())
                                            .notifyCustomer()))
                    .get();
        }
    }

    @Autowired
    @Qualifier("testInput")
    MessageChannel input;

    @Autowired
    @Qualifier("testAudit")
    QueueChannel audit;

    @Autowired
    @Qualifier("testRisk")
    QueueChannel risk;

    @Autowired
    @Qualifier("testNotification")
    QueueChannel notification;

    @Test
    void oneSendReachesEachMatchingRecipientOnce() {
        PaymentCompleted event = new PaymentCompleted(
                "evt-801", "pay-801",
                new BigDecimal("15000000"), true);

        assertTrue(input.send(MessageBuilder
                .withPayload(event).build()));

        assertNotNull(audit.receive(0));
        assertNotNull(risk.receive(0));
        assertNotNull(notification.receive(0));

        // Không có message thứ hai trong cùng lần gửi.
        assertNull(audit.receive(0));
        assertNull(risk.receive(0));
        assertNull(notification.receive(0));
    }

    @Test
    void lowAmountWithoutNotificationOnlyReachesAudit() {
        PaymentCompleted event = new PaymentCompleted(
                "evt-802", "pay-802",
                new BigDecimal("100000"), false);

        assertTrue(input.send(MessageBuilder
                .withPayload(event).build()));

        assertEquals("evt-802",
                ((PaymentCompleted) audit.receive(0)
                        .getPayload()).eventId());
        assertNull(audit.receive(0));
        assertNull(risk.receive(0));
        assertNull(notification.receive(0));
    }

    @Test
    void replayIsNotDeduplicatedByRecipientListRouter() {
        PaymentCompleted event = new PaymentCompleted(
                "evt-803", "pay-803",
                new BigDecimal("100000"), false);
        Message<PaymentCompleted> message =
                MessageBuilder.withPayload(event).build();

        assertTrue(input.send(message));
        assertTrue(input.send(message)); // Redelivery cùng event.

        assertNotNull(audit.receive(0));
        assertNotNull(audit.receive(0));
        assertNull(audit.receive(0));
    }
}
~~~

Mỗi test dùng một event riêng, lấy hết message của những channel liên quan trong test. Nếu có test parallel hoặc Spring context dùng lại rộng hơn, cần tách context/test fixtures để tránh queue còn message từ test khác. Không dùng bản test này để kết luận về broker ack, restart hoặc exactly-once effect.

### 11.2. Unit test validator cấu hình trùng

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class RecipientConfigValidatorTest {
    @Test
    void rejectsDuplicateChannelNames() {
        assertThrows(IllegalArgumentException.class,
                () -> RecipientConfigValidator.requireDistinct(
                        List.of("audit", "risk", "audit")));
    }

    @Test
    void acceptsUniqueRecipientNames() {
        assertDoesNotThrow(() ->
                RecipientConfigValidator.requireDistinct(
                        List.of("audit", "risk", "notification")));
    }
}
~~~

Test này bắt lỗi khai báo lặp **trước khi** topology vận hành. Nó không thay thế integration test vì hai channel khác tên vẫn có thể dẫn tới cùng handler hoặc cùng effect nghiệp vụ.

## 12. Kiểm thử idempotency theo recipient

### 12.1. Cùng event, khác recipient

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class RecipientGateTest {
    @Test
    void sameEventIsUniquePerRecipient() {
        InMemoryRecipientGate gate = new InMemoryRecipientGate();

        assertTrue(gate.firstTime("audit", "evt-901"));
        assertFalse(gate.firstTime("audit", "evt-901"));

        // Risk có quyền xử lý cùng event, vì là recipient khác.
        assertTrue(gate.firstTime("risk", "evt-901"));
        assertFalse(gate.firstTime("risk", "evt-901"));

        // Event khác cũng cần được xử lý.
        assertTrue(gate.firstTime("audit", "evt-902"));
    }
}
~~~

### 12.2. Hai thread cùng claim một khóa

Đối với một tập Set concurrent trong **một JVM**, kiểm thử tranh chấp:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.Test;

class ConcurrentRecipientGateTest {

    @Test
    void onlyOneThreadClaimsTheSameKey() throws Exception {
        InMemoryRecipientGate gate = new InMemoryRecipientGate();
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<Boolean>> results = new ArrayList<>();
            Callable<Boolean> work = () -> {
                start.await();
                return gate.firstTime("audit", "evt-903");
            };

            for (int i = 0; i < 8; i++) {
                results.add(pool.submit(work));
            }

            start.countDown();
            int firstClaims = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) {
                    firstClaims++;
                }
            }

            assertEquals(1, firstClaims);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Test chỉ chứng minh thao tác claim trong **một JVM** có tính nguyên tử. Để xác minh hệ thống nhiều instance, cần test với **store chia sẻ**, crash/restart và transaction của tác động nghiệp vụ. Đừng suy ra từ một test concurrency đơn giản rằng toàn hệ thống đã đạt exactly-once.

### 12.3. Test lỗi giữa chừng

Một test đáng có ở service có side effect:

1. Gửi **evt-904** đến audit.
2. Cố ý ném exception **sau khi đã claim khóa nhưng trước khi commit audit entry**.
3. Cho cùng evt-904 retry.
4. **Mong đợi:** lần retry vẫn có thể hoàn tất audit entry vì transaction đầu đã rollback cả khóa lẫn effect.

Nếu dùng InMemoryRecipientGate và đánh dấu firstTime trước xử lý, test này **sẽ không đạt**: bản retry bị từ chối. Đây là minh chứng vì sao một Set hoặc MetadataStoreSelector độc lập không đủ thay thế giao dịch nghiệp vụ.

### 12.4. Test lỗi sau side effect ở hệ thống ngoài

Mô phỏng notification service **đã gửi email nhưng mất phản hồi**. Khi retry:

- Nếu API của dịch vụ đích hỗ trợ idempotency key, nó nên nhận **cùng key** cho cùng event/recipient và tránh gửi thêm.
- Nếu dịch vụ đích không hỗ trợ, cần ghi nhận trạng thái **UNKNOWN**, đối soát hoặc chính sách business chấp nhận duplicate, thay vì khẳng định chắc chắn email chưa gửi.
- Giám sát số lần retry, duplicate detected và kết quả cuối.

## 13. Monitoring: phân biệt retry hợp lệ và lỗi trùng

| Tín hiệu | Ý nghĩa |
| --- | --- |
| **recipient_delivery_attempts_total{recipient}** | Số attempt gửi tới recipient |
| **recipient_delivery_completed_total{recipient}** | Số tác vụ được đánh dấu hoàn tất |
| **recipient_duplicate_skipped_total{recipient}** | Số bản lặp bị consumer bỏ qua |
| **recipient_delivery_failed_total{recipient,reason}** | Số lỗi tại một recipient |
| **recipient_retry_total{recipient}** | Mức độ retry theo từng nhánh |
| **recipient_backlog_age_seconds{recipient}** | Tuổi của message đang chờ |
| **recipient_unmatched_total** | Event không khớp recipient nào |
| **recipient_config_duplicate_detected_total** | Tín hiệu cấu hình lặp destination |

Không dùng eventId, paymentId hay tenantId có cardinality cao làm label metric. Các ID này có thể xuất hiện trong log/tracing đã lọc nhạy cảm, còn metric nên dựa trên recipient và loại lỗi có tập giá trị giới hạn.

### 13.1. Các câu hỏi vận hành cần trả lời

- Event **evt-501** đã vào router bao nhiêu lần?
- Những recipient nào được chọn cho event đó ở từng lần?
- Nhánh audit đã **nhận**, **được claim**, **commit effect** hay mới chỉ được lập lịch?
- Nếu nhánh notification thất bại, lần retry có đi tới đúng nhánh chưa hoàn tất không?
- Có bao nhiêu duplicate bị bỏ qua **đúng theo chính sách** và bao nhiêu duplicate effect thực sự xảy ra?
- Có worker nào liên tục nhận lại cùng event nhưng không tiến tới trạng thái completed không?

**Received, accepted, processed, committed và acknowledged** là những trạng thái khác nhau. Không chỉ ghi log send() thành công rồi coi cả nghiệp vụ đã xong.

## 14. Bài thực hành: recipient list an toàn khi retry

Hãy thiết kế một flow nhận:

~~~java
record ShipmentCreated(
        String eventId,
        String shipmentId,
        String tenantId,
        boolean needsFraudReview,
        boolean notifyCustomer) {}
~~~

Yêu cầu:

1. **audit** phải nhận mọi sự kiện.
2. **fraudReview** chỉ nhận khi needsFraudReview=true.
3. **notification** chỉ nhận khi notifyCustomer=true.
4. Recipient audit không được xuất hiện hai lần nếu hai module cấu hình cùng tác vụ audit.
5. Một event được redeliver có thể được xử lý lại tại nhánh chưa thành công nhưng không được tạo **audit effect** trùng.
6. Việc khởi động lại ứng dụng không được làm mất trạng thái dedup của các effect bắt buộc.
7. Các attempt đồng thời có cùng recipient + eventId không được tạo hai record nghiệp vụ.

**Các bước thực hiện:**

1. Viết RecipientListRouter Java DSL với mỗi recipient identity đúng một lần.
2. Viết hàm thuần trả Boolean cho hai recipient có điều kiện và unit test tất cả tổ hợp.
3. Dùng QueueChannel trong integration test để kiểm tra số message nhận của từng recipient sau một lần gửi.
4. Gửi lại **cùng eventId** hai lần, chứng minh router **không** tự khử giao nhận lặp.
5. Thêm khóa **recipientId + eventId** ở consumer, viết test một event có thể qua hai recipient độc lập.
6. Dùng unique constraint/transaction khi ghi audit để test crash trước commit và retry thành công.
7. Mô phỏng notification nhận request nhưng mất phản hồi; chọn idempotency key với hệ thống đích và chiến lược đối soát.
8. Viết phương án mở rộng với transactional outbox và queue/broker bền khi producer/consumer chạy trên nhiều instance.

**Nâng cao:** Bật applySequence ở một flow scatter-gather khác, cho một recipient gửi lại kết quả và thiết kế Aggregator xử lý nhóm trùng, nhánh thiếu reply, timeout và release strategy. Giải thích vì sao sequence metadata không thay thế khóa idempotency.

### Câu hỏi tự kiểm tra

1. Một event gửi tới audit và risk là duplicate hay fan-out hợp lệ?
2. Vì sao hai recipient có selector khác nhau nhưng cùng channel có thể tạo thiết kế khó kiểm soát?
3. Vì sao chỉ dùng Set loại trùng trước RecipientListRouter có thể làm mất nhánh lỗi?
4. Khi nào nên dùng recipientId + eventId thay vì eventId đơn lẻ?
5. MessageHeaders.ID có phù hợp làm khóa chống duplicate nghiệp vụ không?
6. MetadataStoreSelector dựa vào thao tác nào để claim key đồng thời?
7. Vì sao SimpleMetadataStore không đủ cho yêu cầu chống trùng sau restart?
8. Nếu handler ném exception sau khi claim nhưng trước khi hoàn tất effect, hệ thống phải làm gì?
9. Retry toàn router và retry riêng nhánh notification khác nhau thế nào?
10. Khi nào unique constraint trong database chưa đủ chống gửi email/HTTP lặp?

## 15. Checklist thiết kế trước khi triển khai

- **Mỗi recipient identity được khai báo một lần** trong cấu hình; những selector cùng đích được gộp có chủ đích.
- **Đồ thị channel** không vô tình dẫn cùng event về cùng side effect hai đường.
- **Event ID** ổn định qua retry/redelivery và khác biệt đúng giữa các sự kiện thực.
- **Idempotency key** có đúng scope recipient, tenant và loại tác vụ.
- **Dedup tại recipient** cho phép từng nhánh phục hồi độc lập sau partial failure.
- **Claim key** và effect có transaction/state-machine phù hợp; không đánh dấu completed quá sớm.
- **Concurrent requests** được bảo vệ bằng unique constraint/atomic operation, không dùng check-then-put.
- **MetadataStore** có độ bền và khả năng chia sẻ phù hợp với mô hình nhiều instance.
- **Retry/backoff và DLQ** được thiết kế cho từng nhánh khi có thể.
- **External side effects** có idempotency/reconciliation hoặc chấp nhận duplicate rõ ràng.
- **applySequence** chỉ dùng khi grouping thật sự cần; không coi đó là cơ chế dedup.
- **Observability** phân biệt received, attempted, completed, duplicate skipped và failed.
- **Test** bao phủ một lần gửi, bản replay, branch failure, concurrent claims và restart.

**Kết luận:** Để tránh gửi trùng đến cùng một recipient, hãy kiểm soát topology và điều kiện của Recipient List, sau đó bảo vệ **tác động nghiệp vụ theo recipient** bằng event ID ổn định và cơ chế idempotency phù hợp. Không thể suy ra “exactly once” từ một RecipientListRouter, từ một Set trong bộ nhớ hoặc từ một lần send() thành công. Cách thiết kế đúng là làm rõ ý nghĩa của **mỗi recipient**, **mỗi event** và **mỗi trạng thái hoàn tất**, rồi kiểm thử cả đường thành công lẫn retry sau lỗi một phần.

## Tài liệu tham khảo

- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): RecipientListRouter và recipient selector.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): IdempotentReceiverInterceptor, duplicateMessage, discard channel và MetadataStoreSelector.
- [Spring Integration Reference — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): SimpleMetadataStore, concurrent/persistent stores và khử trùng.
- [Spring Integration API — MetadataStoreSelector](https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html): key strategy và thao tác putIfAbsent.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, QueueChannel, ExecutorChannel và tác động của ranh giới async.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): cấu hình IntegrationFlow và recipient endpoint.
