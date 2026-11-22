# Router theo recipient list

## 1. Bối cảnh: một sự kiện có thể có nhiều người nhận

Trong chương **Message router** của module **SPRING_INTEGRATION_PATTERN**, chúng ta triển khai Enterprise Integration Patterns bằng Spring Integration để tạo luồng thông điệp ít phụ thuộc, dễ mở rộng và dễ kiểm thử. Router quyết định đường đi của message; Filter, Transformer, Splitter, Aggregator và Gateway phối hợp xử lý nghiệp vụ, còn retry, error channel và correlation giúp theo dõi, phục hồi các nhánh khi có lỗi.

Giả sử hệ thống nhận sự kiện **order.accepted**:

- **Audit** phải ghi nhận mọi đơn hàng.
- **Risk review** chỉ xem xét đơn có giá trị từ 10 triệu đồng.
- **International fulfillment** chỉ xử lý đơn giao ra ngoài Việt Nam.

Một đơn giá trị cao giao ra nước ngoài cần tới **cả ba** nơi nhận. Một đơn nhỏ giao trong nước chỉ tới audit. Dùng một router chọn duy nhất một nhánh không đáp ứng được yêu cầu này.

**Recipient List** là mẫu định tuyến một message tới **tập recipient**. Trong Spring Integration, **RecipientListRouter** quản lý danh sách các destination channel. Mỗi recipient có thể có **selector** trả về true/false theo nội dung message; router gửi tới mọi recipient phù hợp.

Sau bài này, bạn có thể:

1. Phân biệt Recipient List với Router một nhánh, Message Filter, PublishSubscribeChannel và Splitter.
2. Định nghĩa recipient cố định, recipient có điều kiện theo payload hoặc headers.
3. Cấu hình RecipientListRouter bằng Java DSL và triển khai các flow đầu ra.
4. Quyết định hành vi khi không recipient nào phù hợp hoặc khi một destination gửi thất bại.
5. Hiểu ý nghĩa của applySequence với Aggregator, cùng giới hạn về ordering, transaction và độ bền.
6. Kiểm thử chính xác tập recipient đã nhận message, nhánh lỗi và ngữ cảnh correlation.

## 2. Recipient List hoạt động như thế nào?

Mỗi lần nhận một message, RecipientListRouter lần lượt đánh giá các điều kiện nhận và chọn **tập channel phù hợp**. Đăng ký recipient không có selector nghĩa là recipient đó luôn được chọn. Các selector độc lập; đúng một điều kiện không làm router dừng xét các điều kiện khác.

~~~mermaid
flowchart LR
    P["Order producer"] --> I["orderEventsChannel"]
    I --> R{"RecipientListRouter"}
    R -->|"Luôn nhận"| A["Audit"]
    R -->|"totalVnd >= 10 triệu"| F["Risk review"]
    R -->|"country != VN"| S["International fulfillment"]
~~~

| Sự kiện | Tổng tiền | Quốc gia nhận | Recipient phù hợp |
| --- | ---: | --- | --- |
| ORD-101 | 800.000 VND | VN | audit |
| ORD-102 | 12.000.000 VND | VN | audit, risk |
| ORD-103 | 15.000.000 VND | SG | audit, risk, international |
| ORD-104 | 500.000 VND | SG | audit, international |

Trong bảng này, audit là recipient vô điều kiện. Với router **chỉ gồm recipient có điều kiện**, có thể xảy ra trường hợp **không có recipient nào**; cần chọn rõ policy xử lý trường hợp đó.

### So sánh với các mẫu liên quan

| Cơ chế | Hành vi | Nên dùng khi |
| --- | --- | --- |
| Router chọn một nhánh (ví dụ Header Value Router phổ biến) | Chọn channel dựa trên một key hoặc biểu thức | Một message đi một loại workflow |
| **RecipientListRouter** | Gửi tới mọi recipient được chọn độc lập | Một sự kiện cần nhiều nhánh xử lý có điều kiện |
| PublishSubscribeChannel | Phát message tới nhiều subscriber đăng ký trên channel | Broadcast sự kiện cho toàn bộ subscriber |
| Message Filter | Giữ hoặc loại một message theo predicate | Một nhánh cần điều kiện chấp nhận riêng |
| Splitter | Chia một payload thành nhiều message con | Xử lý các phần của một tập dữ liệu |
| Aggregator | Gom message thuộc cùng một nhóm | Đợi các kết quả con để tạo một kết quả chung |

**RecipientListRouter** chọn **ai nhận cùng sự kiện**; **Splitter** chọn **cách chia dữ liệu**. Khi cần gửi cùng sự kiện tới nhiều recipient, các recipient có thể xử lý độc lập. Khi cần fan-out rồi ghép kết quả, RecipientListRouter phải được phối hợp với Aggregator và correlation phù hợp.

Không nhầm recipient với địa chỉ email hoặc URL: recipient mà router khai báo là **MessageChannel**. Muốn gửi email, HTTP hay Kafka cần adapter/endpoint phía sau channel đó.

## 3. Thiết kế rule độc lập, dễ kiểm thử

Hãy bắt đầu bằng hợp đồng payload:

~~~java
import java.math.BigDecimal;

record OrderAccepted(
        String orderId,
        BigDecimal totalVnd,
        String destinationCountry) {}
~~~

Sau đó tách điều kiện chọn recipient thành các hàm thuần:

~~~java
import java.math.BigDecimal;
import java.util.Locale;

final class OrderRoutingRules {
    static final BigDecimal RISK_THRESHOLD =
            new BigDecimal("10000000");

    private OrderRoutingRules() {}

    static boolean requiresRiskReview(OrderAccepted order) {
        return order.totalVnd() != null
                && order.totalVnd().compareTo(RISK_THRESHOLD) >= 0;
    }

    static boolean isInternational(OrderAccepted order) {
        return order.destinationCountry() != null
                && !"VN".equals(order.destinationCountry()
                        .trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Đầu vào cần qua bước validate trước khi routing: orderId không rỗng, tiền không âm, country code hợp lệ. Selector trả false với dữ liệu thiếu không thay thế validation. Trong hệ thống thật, BigDecimal giúp so sánh tiền chính xác hơn double; country code nên sử dụng mã đã chuẩn hóa và danh mục được chấp nhận.

**Rule nên độc lập với hạ tầng.** Một phương thức requiresRiskReview không cần biết tên channel hay gọi risk service. Khi luật thay đổi, có thể unit test hàm đó và giữ nguyên topology chung.

Nếu luật dựa vào header như tenantId hoặc priority, phải quy định rõ kiểu, nguồn gốc và mức độ tin cậy của header. Không sử dụng thông tin do external client tự cung cấp để mở nhánh có đặc quyền trước khi xác thực.

## 4. Cấu hình Java DSL: ba recipient, hai selector

Spring Integration cung cấp phương thức **routeToRecipients** và cấu hình **RecipientListRouterSpec** trong IntegrationFlow DSL. Ví dụ dưới dùng Java 17+; mỗi recipient có một DirectChannel để dễ theo dõi các nhánh đồng bộ.

### 4.1. Tạo các channel và router

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderRecipientRoutingConfig {

    @Bean
    MessageChannel orderEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel auditChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel riskReviewChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel internationalFulfillmentChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow routeAcceptedOrders() {
        return IntegrationFlow.from("orderEventsChannel")
                .routeToRecipients(r -> r
                        .recipient("auditChannel")
                        .recipientMessageSelector("riskReviewChannel", message ->
                                OrderRoutingRules.requiresRiskReview(
                                        (OrderAccepted) message.getPayload()))
                        .recipientMessageSelector(
                                "internationalFulfillmentChannel", message ->
                                        OrderRoutingRules.isInternational(
                                                (OrderAccepted) message.getPayload())))
                .get();
    }
}
~~~

**Đọc cấu hình:**

1. **orderEventsChannel** nhận event từ producer.
2. **routeToRecipients** tạo router dạng recipient list.
3. **recipient("auditChannel")** không có selector nên luôn nhận.
4. **recipientMessageSelector** đánh giá Message<?> cho từng kênh có điều kiện.
5. Cùng message có thể được chọn cho nhiều destination. Đích cần có subscriber/endpoint thực sự nhận.

Danh sách recipient được xác định khi cấu hình flow; **nội dung selector** được đánh giá cho từng message lúc runtime. Không phải cứ có ba recipient thì lần gửi nào cũng tới cả ba.

### 4.2. Gắn các handler vào nhánh

Định nghĩa port để tách routing khỏi dịch vụ cụ thể:

~~~java
interface AuditPort {
    void record(OrderAccepted order);
}

interface RiskReviewPort {
    void review(OrderAccepted order);
}

interface InternationalFulfillmentPort {
    void dispatch(OrderAccepted order);
}
~~~

Các phương thức cấu hình sau có thể đặt trong lớp OrderRecipientRoutingConfig ở trên:

~~~java
@Bean
IntegrationFlow auditFlow(AuditPort auditPort) {
    return IntegrationFlow.from("auditChannel")
            .handle(OrderAccepted.class, (order, headers) -> {
                auditPort.record(order);
                return null;
            })
            .get();
}

@Bean
IntegrationFlow riskReviewFlow(RiskReviewPort port) {
    return IntegrationFlow.from("riskReviewChannel")
            .handle(OrderAccepted.class, (order, headers) -> {
                port.review(order);
                return null;
            })
            .get();
}

@Bean
IntegrationFlow internationalFlow(InternationalFulfillmentPort port) {
    return IntegrationFlow.from("internationalFulfillmentChannel")
            .handle(OrderAccepted.class, (order, headers) -> {
                port.dispatch(order);
                return null;
            })
            .get();
}
~~~

Ứng dụng cần cung cấp bean triển khai ba port. Mỗi flow chỉ biết port mà nó cần, giúp thay adapter audit hoặc cách gửi thông tin giao vận mà không ảnh hưởng rule định tuyến.

### 4.3. Producer phát message

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

OrderAccepted order = new OrderAccepted(
        "ORD-103", new BigDecimal("15000000"), "SG");

Message<OrderAccepted> event = MessageBuilder.withPayload(order)
        .setHeader("eventType", "order.accepted")
        .setHeader("businessCorrelationId", order.orderId())
        .setHeader("schemaVersion", 1)
        .build();

// orderEventsChannel được inject từ Spring context.
boolean accepted = orderEventsChannel.send(event);
~~~

Với ORD-103, cả ba recipient được chọn. Tuy vậy, **send() trả true không chứng minh mọi hệ thống đích đã ghi thành công**. Nếu một nhánh về sau dùng ExecutorChannel, QueueChannel hoặc broker, xử lý có thể hoàn tất sau thời điểm send() trở về.

Trong producer thực tế, nên gắn eventId ổn định để phát hiện trùng lặp khi retry, và dùng trace context từ hệ thống quan sát. Không đặt dữ liệu nhạy cảm vào headers có thể bị ghi log hoặc truyền qua adapter.

## 5. Recipient cố định, SpEL selector và subflow

### 5.1. Selector theo SpEL

Ngoài lambda Java, Java DSL có thể dùng **biểu thức Spring Expression Language**:

~~~java
@Bean
IntegrationFlow routeTextEvents() {
    return IntegrationFlow.from("textEventsChannel")
            .routeToRecipients(r -> r
                    .recipient("allTextChannel")
                    .recipient("priorityTextChannel",
                            "headers['priority'] == 'HIGH'")
                    .recipient("paymentTextChannel",
                            "payload.startsWith('PAYMENT:')"))
            .get();
}
~~~

Ví dụ giả định textEventsChannel và ba channel đích đã được định nghĩa cùng subscriber phù hợp. Message có priority HIGH sẽ đi tới priorityTextChannel, message có payload bắt đầu bằng PAYMENT: đi tới paymentTextChannel. Nếu cùng thỏa hai điều kiện, nó **được gửi tới cả hai**, đồng thời tới allTextChannel.

| API | Đặc điểm |
| --- | --- |
| **recipient(name)** | Luôn chọn recipient |
| **recipient(name, expression)** | Chỉ chọn khi SpEL trả true |
| **recipientMessageSelector(name, predicate)** | Chọn qua hàm nhận Message<?>; dễ unit test rule Java |
| **recipientFlow(...)** | Recipient là một subflow khai báo ngay trong DSL |

Với dữ liệu quan trọng, selector viết bằng Java thuần thường dễ refactor và unit test hơn biểu thức dài. SpEL có thể ngắn gọn cho luật đơn giản theo headers; hãy kiểm tra kiểu và tồn tại của trường để tránh lỗi khi thực thi.

### 5.2. Dùng subflow khi mỗi đích cần thêm bước xử lý

Thay vì đưa tất cả logic vào một handler, một recipient có thể là subflow gồm Transformer rồi Service Activator. Ví dụ DSL có thể dùng **recipientFlow** với biểu thức selector; khi khai báo theo cách này, chính router quản lý điểm vào của subflow.

~~~java
@Bean
IntegrationFlow routeWithRecipientFlow() {
    return IntegrationFlow.from("routingInputChannel")
            .routeToRecipients(r -> r
                    .recipient("auditChannel")
                    .recipientFlow(
                            "headers['eventType'] == 'order.accepted'",
                            flow -> flow
                                    .transform(String.class, String::trim)
                                    .channel("normalizedOrdersChannel")))
            .get();
}
~~~

Đoạn minh họa giả định payload là String và các channel có sẵn; sự kiện kinh doanh typed như OrderAccepted nên dùng Transformer tương ứng. Điểm quan trọng là **recipient có thể mang một chuỗi xử lý riêng**. Mỗi nhánh cần hợp đồng rõ ràng, tránh trộn kiểu payload không tương thích.

## 6. Khi không recipient nào phù hợp

Một recipient list gồm toàn selector có thể không chọn được đích nào. Ví dụ message không phải payment.completed, cũng không phải cảnh báo mức HIGH.

Theo cấu hình mặc định, router **không âm thầm bỏ** message khi không xác định được đích hợp lệ mà ném exception. Khi nghiệp vụ có trường hợp không khớp hợp lệ, nên cấu hình **default output channel**:

~~~java
@Bean
IntegrationFlow routeWithFallback() {
    return IntegrationFlow.from("eventInputChannel")
            .routeToRecipients(r -> r
                    .recipient("paymentEventsChannel",
                            "headers['eventType'] == 'payment.completed'")
                    .recipient("criticalEventsChannel",
                            "headers['severity'] == 'HIGH'")
                    .defaultOutputChannel("unmatchedEventsChannel"))
            .get();
}
~~~

Để chạy ví dụ, tạo các bean channel và handler cho eventInputChannel, paymentEventsChannel, criticalEventsChannel, unmatchedEventsChannel. Một message khớp hai selector được gửi tới hai recipient; một message không khớp selector nào tới unmatchedEventsChannel.

**Không khớp selector** khác **gửi đến recipient đã chọn nhưng lỗi**:

- **Unmatched:** không recipient nào được chọn. Default output channel giải quyết trường hợp này.
- **Unresolved channel:** tên recipient được chọn nhưng bean channel không tồn tại. Mặc định đây là lỗi phân giải destination.
- **Send failure:** channel tồn tại nhưng không chấp nhận send, quá tải, hoặc handler downstream ném exception.
- **Async handling failure:** channel chấp nhận nhiệm vụ nhưng handler chạy sau đó thất bại.

Default output channel không có nghĩa mọi lỗi downstream tự động chuyển về fallback. Cần xác minh từng tình huống bằng test và logging phù hợp. Nếu nghiệp vụ cố tình bỏ message không khớp, có thể dùng **nullChannel** làm đường mặc định, nhưng nên ghi metrics trước khi loại.

## 7. Các tuỳ chọn quan trọng của router

| Tuỳ chọn | Ý nghĩa | Hành vi cần nhớ |
| --- | --- | --- |
| **applySequence** | Tạo metadata correlation/sequence cho các bản gửi | Mặc định false; bật khi cần ghép nhóm |
| **ignoreSendFailures** | Có bỏ qua lỗi gửi để tiếp tục recipient khác không | Mặc định false; true cần cân nhắc nguy cơ che lỗi |
| **sendTimeout** | Thời gian chờ gửi đến channel | Không phải timeout toàn bộ công việc downstream |
| **defaultOutputChannel** | Đích khi không chọn được recipient | Giúp xử lý các message không khớp |
| **resolutionRequired** | Yêu cầu resolve tên channel được chọn | Mặc định true; sai tên nên được phát hiện |

### 7.1. ignoreSendFailures và lỗi một nhánh

Giả sử router gửi đến audit, notification, analytics và **audit handler đồng bộ** ném exception. Với **ignoreSendFailures=false** (mặc định), lỗi có thể truyền ra và các recipient còn lại **không được gọi**. Nếu đặt **ignoreSendFailures=true**, router có thể bỏ qua lỗi gửi của một recipient để tiếp tục gửi các recipient sau.

~~~java
@Bean
IntegrationFlow bestEffortNotifications() {
    return IntegrationFlow.from("notifyInputChannel")
            .routeToRecipients(r -> r
                    .recipient("emailChannel")
                    .recipient("smsChannel")
                    .recipient("analyticsChannel")
                    .ignoreSendFailures(true))
            .get();
}
~~~

Ví dụ này chỉ phù hợp nếu các nhánh được chấp nhận là **best effort**, có giám sát riêng và không yêu cầu một lỗi dừng toàn flow. Không nên bật bỏ qua lỗi cho audit, thanh toán hoặc nghiệp vụ bắt buộc lưu trữ nếu chưa có cơ chế phục hồi độc lập.

Với channel bất đồng bộ, một lần send thành công **không chứng minh handler phía sau đã thành công**. Do đó ignoreSendFailures không thay thế error channel, retry hay cơ chế xác nhận hoàn tất của từng nhánh.

### 7.2. sendTimeout: giới hạn thao tác gửi

~~~java
// Bên trong cấu hình routeToRecipients:
.recipient("billingChannel")
.recipient("auditChannel")
.sendTimeout(2_000L)
~~~

Send timeout giới hạn thời gian chờ khi router gửi tới một channel có thể block hoặc đầy. Nó **không tự giới hạn** thời gian một REST call, giao dịch DB, hay một handler đồng bộ chạy lâu. Khi cần deadline toàn yêu cầu phải thiết kế timeout ở từng tầng phù hợp.

### 7.3. resolutionRequired: phát hiện channel sai tên

Nếu selector chọn tên channel không tồn tại, cấu hình mặc định yêu cầu resolve thành công và ném lỗi. Chỉ cân nhắc bỏ qua channel chưa resolve khi thực sự có chính sách fallback có chủ đích; trong hệ thống production, sai tên channel thường nên **fail fast** để phát hiện lỗi cấu hình sớm.

## 8. applySequence và ghép kết quả từ nhiều nhánh

Khi Recipient List dùng để gửi sự kiện tới audit, notification và analytics độc lập, ta thường **không cần sequence**. Nhưng với bài toán scatter-gather, ví dụ đồng thời hỏi dịch vụ **giá**, **thuế** và **phí vận chuyển**, kết quả từ các nhánh cần được **Aggregator** gom đủ trước khi trả về caller.

~~~mermaid
flowchart LR
    P["Quote request"] --> R["RecipientListRouter<br/>applySequence=true"]
    R --> A["Price calculation"]
    R --> B["Tax calculation"]
    R --> C["Shipping calculation"]
    A --> G["Aggregator"]
    B --> G
    C --> G
    G --> O["Combined quote"]
~~~

~~~java
@Bean
IntegrationFlow quoteRoutingFlow() {
    return IntegrationFlow.from("quoteRequestsChannel")
            .routeToRecipients(r -> r
                    .applySequence(true)
                    .recipient("priceCalculationChannel")
                    .recipient("taxCalculationChannel")
                    .recipient("shippingCalculationChannel"))
            .get();
}
~~~

Đoạn cấu hình định tuyến này chỉ là **một phần** của ví dụ scatter-gather. Cần tạo ba consumer, mỗi consumer phát **reply** tới kênh Aggregator, đồng thời cấu hình release strategy, message store và timeout phù hợp.

Khi **applySequence(true)**, router tạo metadata giúp hệ thống nhóm các message được gửi ra:

| Header | Mục đích |
| --- | --- |
| **correlationId** | Liên kết những message thuộc cùng lần phân phối |
| **sequenceNumber** | Thứ tự của message con trong tập |
| **sequenceSize** | Kích thước tập message dự kiến |

Spring Integration mặc định **không bật** applySequence trên RecipientListRouter. Chỉ bật khi downstream thực sự cần correlation/sequence, chẳng hạn Aggregator. Việc bật sequence không làm các nhánh chạy tuần tự theo thời gian và cũng không bảo đảm nhánh nào sẽ hoàn tất trước.

### Điều kiện hoàn tất của Aggregator

Nếu ba recipient đều phải phát một reply, Aggregator cần thu đủ ba kết quả trước khi release. Nếu một nhánh lỗi hoặc không trả reply, nhóm message có thể tồn tại lâu; vì vậy cần quy định timeout, xử lý nhóm thiếu phần tử và lưu trữ trạng thái khi cần.

Nếu recipient có **selector**, số recipient phù hợp có thể thay đổi theo từng message. Thiết kế Aggregator phải khớp với **tập recipient thực sự được chọn**, thay vì hardcode rằng mọi message đều được gửi tới ba nhánh.

### Correlation nghiệp vụ khác correlation của một lần fan-out

Một đơn hàng có thể phát nhiều sự kiện **order.accepted**, **order.paid** và **order.shipped**. Trường **orderId** là khóa nghiệp vụ tồn tại trong nhiều luồng, còn correlation/sequence phục vụ việc ghép các nhánh có thể chỉ có ý nghĩa trong **một lần** Recipient List định tuyến.

Nếu phải giữ cả hai, lưu business key riêng trong payload hoặc một header như **businessCorrelationId**. Không phụ thuộc MessageHeaders.ID như một khóa nghiệp vụ lâu dài; mỗi message dẫn xuất có thể có ID riêng.

## 9. Thứ tự, đồng bộ, transaction và hiệu ứng phụ

**RecipientListRouter không tự chạy các nhánh song song**. Cách dispatch thực tế phụ thuộc channel đích.

| Channel đích | Hành vi thường gặp | Ảnh hưởng đến recipient |
| --- | --- | --- |
| **DirectChannel** | Handler chạy đồng bộ trên thread gửi | Handler chậm hoặc lỗi có thể ảnh hưởng sender và việc gửi tiếp |
| **ExecutorChannel** | Dispatch được lập lịch qua Executor | Handler có thể chạy sau send, lỗi cần đường xử lý async |
| **QueueChannel** | Message chờ consumer/poller | Send thành công khác với đã xử lý xong |
| **PublishSubscribeChannel** | Tiếp tục fan-out tới nhiều subscriber | Cần xét lỗi, thời gian xử lý và thứ tự của fan-out bên trong |

### 9.1. Được gửi tới nhiều nơi không có nghĩa giao dịch nguyên tử

Xét chuỗi:

1. Audit ghi bản ghi vào database A.
2. Notification đã gửi email.
3. Analytics gặp lỗi khi ghi database B.

Ngay cả khi tất cả các kênh đều đồng bộ, router không tự hoàn tác email đã gửi hay kết quả ở một hệ thống ngoài transaction. Transaction của Spring chỉ bao phủ các tài nguyên thực sự tham gia transaction tương ứng.

Nếu nghiệp vụ yêu cầu **mọi đích phải xử lý tin cậy**, có thể cần:

- **Transactional outbox** để đảm bảo sự kiện được ghi cùng transaction với cập nhật dữ liệu gốc.
- **Broker/persistent storage** nếu message phải tồn tại qua restart.
- **Retry/backoff**, dead-letter queue hoặc error channel cho từng nhánh.
- **Idempotency key** và cơ chế deduplication để không tạo side effect trùng.
- **Monitoring** của từng recipient và cảnh báo nếu tồn đọng quá lâu.

RecipientListRouter giải quyết việc **chọn và chuyển tới các đích**, không tự cam kết end-to-end exactly-once delivery.

### 9.2. Retry toàn router có thể làm lặp nhánh đã thành công

Giả sử audit đã ghi thành công nhưng nhánh risk review lỗi và người gọi retry nguyên message. Audit có thể nhận lần thứ hai.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as RecipientListRouter
    participant A as Audit
    participant F as Risk
    P->>R: event E lần 1
    R->>A: E
    A-->>R: Thành công
    R->>F: E
    F--xR: Exception
    R--xP: Lỗi
    P->>R: Retry E
    R->>A: E một lần nữa
    Note over A: Cần idempotent consumer
~~~

Hãy tạo một **eventId ổn định** cho từng sự kiện, ghi nhận đã xử lý tại consumer qua unique constraint hoặc idempotency store. Nếu có thể, retry **đúng nhánh lỗi** thay vì phát lại toàn bộ flow sau khi các nhánh khác đã thành công.

### 9.3. Chia sẻ payload mutable tạo rủi ro

Các message chuyển tới nhiều recipient có thể chia sẻ cùng tham chiếu payload, đặc biệt khi không yêu cầu tạo thêm sequence headers. Nếu một handler sửa một đối tượng mutable, các nhánh khác có thể quan sát dữ liệu đã bị thay đổi hoặc gặp race condition khi xử lý bất đồng bộ.

Ưu tiên **record và kiểu bất biến**, hoặc tạo bản sao cho các đối tượng mutable. MessageHeaders không cho sửa cấu trúc header map nhưng không tự biến mọi đối tượng bên trong thành immutable.

## 10. Error channel và đường đi của lỗi

Cần phân biệt ba thời điểm phát sinh lỗi:

1. **Đánh giá selector**: selector truy cập payload sai kiểu hoặc SpEL không hợp lệ.
2. **Dispatch**: tên channel không resolve, channel quá tải hoặc không có handler.
3. **Processing**: handler downstream ném exception, đôi khi sau khi router đã trả về.

Với nhánh DirectChannel đồng bộ, exception có thể truyền trực tiếp qua call stack và ảnh hưởng những recipient chưa được gửi. Với nhánh ExecutorChannel hoặc QueueChannel, lỗi có thể xuất hiện sau đó; việc tạo **ErrorMessage** và gửi tới **errorChannel** phụ thuộc endpoint, adapter, poller, executor và cấu hình error handler.

**Không mặc định coi ignoreSendFailures(true) là cơ chế xử lý lỗi đầy đủ.** Nó chỉ ảnh hưởng việc router xử lý một số lỗi gửi. Nó không bảo đảm tất cả nhánh đều chạy, không retry tự động và không thu thập lỗi nghiệp vụ phát sinh ở worker chạy sau.

### Bảng lựa chọn chính sách

| Yêu cầu | Cấu hình/hướng xử lý nên xem xét |
| --- | --- |
| Bắt buộc audit thành công trước khi trả lời | Đồng bộ hoặc commit bền, không bỏ qua lỗi quan trọng |
| Notification được phép best effort | Có thể tiếp tục các recipient còn lại; có metrics và error flow riêng |
| Phải gửi notification lại sau crash | Broker/outbox hoặc message store bền, retry/ack |
| Cần xử lý bất đồng bộ nhưng không mất dữ liệu | Ranh giới durable messaging, consumer idempotent |
| Router không chọn recipient nào | Default output channel, fail fast hoặc discard có chủ đích |

## 11. Tăng khả năng quan sát và quản lý recipient

Một event có thể tới nhiều nhánh, vì vậy chỉ log **event đã vào router** là chưa đủ. Hệ thống nên theo dõi:

| Dữ liệu | Giúp trả lời |
| --- | --- |
| **eventId / businessCorrelationId** | Đây là event nào? Có bị retry hay trùng không? |
| **traceId / spanId** | Các nhánh của một lần gửi chạy ở đâu, mất bao lâu? |
| **recipientName** | Recipient nào đã được chọn và đã nhận? |
| **sendFailures / downstreamFailures** | Lỗi xảy ra khi dispatch hay lúc xử lý? |
| **retryCount** | Nhánh có bị lặp quá nhiều lần không? |
| **queueDepth / age** | Recipient async có đang bị nghẽn không? |
| **unmatchedCount** | Có event nào không phù hợp mọi selector? |

Khi logging, chỉ giữ thông tin cần chẩn đoán; tránh log toàn bộ payload hay headers có token, dữ liệu cá nhân hoặc thông tin nhạy cảm.

### Recipient có thay đổi lúc runtime được không?

Spring Integration hỗ trợ các thao tác quản lý RecipientListRouter như thêm hoặc bỏ recipient thông qua management API/Control Bus/JMX khi được cấu hình. Tuy nhiên, việc thay topology trong hệ thống đang chạy cần kiểm soát quyền quản trị, phiên bản cấu hình và khả năng quan sát. Trong hệ thống ổn định, nên coi thay đổi recipient là một thay đổi có kiểm thử và quy trình triển khai phù hợp.

## 12. Kiểm thử đúng tập recipient

Unit test selector chỉ kiểm tra **điều kiện**. Integration test mới xác nhận **router nối đúng channel** và recipient nhận đúng message.

### 12.1. Unit test các rule

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderRoutingRulesTest {

    @Test
    void identifiesHighValueAndInternational() {
        OrderAccepted domestic = new OrderAccepted(
                "ORD-101", new BigDecimal("800000"), "VN");
        OrderAccepted high = new OrderAccepted(
                "ORD-102", new BigDecimal("12000000"), "VN");
        OrderAccepted abroad = new OrderAccepted(
                "ORD-103", new BigDecimal("15000000"), "SG");

        assertFalse(OrderRoutingRules.requiresRiskReview(domestic));
        assertFalse(OrderRoutingRules.isInternational(domestic));
        assertTrue(OrderRoutingRules.requiresRiskReview(high));
        assertFalse(OrderRoutingRules.isInternational(high));
        assertTrue(OrderRoutingRules.requiresRiskReview(abroad));
        assertTrue(OrderRoutingRules.isInternational(abroad));
    }
}
~~~

### 12.2. Integration test routing có điều kiện

Test dưới tạo một Spring context tối thiểu, ba destination DirectChannel và một Recipient List, sau đó đăng ký subscriber để ghi nhận những recipient được gọi. Nó không cần database hay REST.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(RecipientListRoutingTest.TestConfig.class)
class RecipientListRoutingTest {

    @Configuration
    @EnableIntegration
    static class TestConfig {
        @Bean
        MessageChannel eventInput() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel auditOutput() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel riskOutput() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel crossBorderOutput() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow recipientFlow() {
            return IntegrationFlow.from("eventInput")
                    .routeToRecipients(r -> r
                            .recipient("auditOutput")
                            .recipientMessageSelector("riskOutput", m ->
                                    OrderRoutingRules.requiresRiskReview(
                                            (OrderAccepted) m.getPayload()))
                            .recipientMessageSelector("crossBorderOutput", m ->
                                    OrderRoutingRules.isInternational(
                                            (OrderAccepted) m.getPayload())))
                    .get();
        }
    }

    @Autowired
    @Qualifier("eventInput")
    MessageChannel input;

    @Autowired
    @Qualifier("auditOutput")
    SubscribableChannel audit;

    @Autowired
    @Qualifier("riskOutput")
    SubscribableChannel risk;

    @Autowired
    @Qualifier("crossBorderOutput")
    SubscribableChannel crossBorder;

    @Test
    void dispatchesOneMessageToAllMatchingRecipients() {
        List<String> receivedBy = new ArrayList<>();
        audit.subscribe(m -> receivedBy.add("audit"));
        risk.subscribe(m -> receivedBy.add("risk"));
        crossBorder.subscribe(m -> receivedBy.add("crossBorder"));

        OrderAccepted event = new OrderAccepted(
                "ORD-103", new BigDecimal("15000000"), "SG");

        assertTrue(input.send(
                MessageBuilder.withPayload(event).build()));
        assertEquals(3, receivedBy.size());
        assertTrue(receivedBy.containsAll(
                List.of("audit", "risk", "crossBorder")));
    }
}
~~~

Với DirectChannel đồng bộ, test có thể kiểm tra tập recipient ngay sau send(). Khi thay bằng ExecutorChannel, cần cơ chế đồng bộ test như CountDownLatch và timeout thích hợp. Khi nhiều test dùng cùng Spring context, cần dọn subscriber đăng ký tạm để tránh ảnh hưởng giữa các ca.

### 12.3. Ma trận kiểm thử nên có

| Input | Kết quả mong đợi |
| --- | --- |
| Đơn trong nước, giá trị thấp | Chỉ audit |
| Đơn trong nước, giá trị cao | Audit và risk |
| Đơn quốc tế, giá trị thấp | Audit và international |
| Đơn quốc tế, giá trị cao | Cả ba |
| Không recipient nào khớp, không có audit vô điều kiện | Fallback hoặc exception |
| Channel name sai | Lỗi resolution được quan sát |
| Handler đồng bộ ném exception | Chính sách ignoreSendFailures được áp dụng |
| Handler async ném exception | Có error flow/metrics riêng |
| Retry sau khi một nhánh đã thành công | Consumer không tạo tác động nghiệp vụ trùng |
| Có applySequence và Aggregator | Group, sequenceSize, timeout và release phù hợp |

## 13. Những lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách tránh |
| --- | --- | --- |
| Dùng router một nhánh khi cùng event cần nhiều recipient | Thiếu một hoặc nhiều tác vụ | Dùng RecipientListRouter |
| Cho rằng recipient được gọi theo điều kiện loại trừ nhau | Bỏ qua fan-out tới mọi selector khớp | Viết ma trận kết hợp điều kiện |
| Nhầm recipient với URL/email | Router không có channel hợp lệ | Tạo MessageChannel và adapter |
| Quên fallback khi không có recipient | Lỗi routing ngoài dự kiến | Default channel hoặc fail fast có chủ đích |
| Bật ignoreSendFailures cho audit bắt buộc | Che lỗi gửi thông tin quan trọng | Cơ chế bền và thông báo lỗi phù hợp |
| Tưởng fan-out đồng nghĩa xử lý song song | Nhánh DirectChannel vẫn đồng bộ | Chọn ranh giới async rõ ràng |
| Dùng mutable payload chung | Race condition, tác động chéo giữa các nhánh | Immutable model hoặc defensive copy |
| Retry toàn router không có idempotency | Audit/notification nhận trùng | eventId ổn định, retry theo nhánh |
| Đặt applySequence mà không thiết kế Aggregator | Metadata thiếu mục đích, hiểu sai correlation | Bật khi thật sự cần ghép nhóm |
| Chỉ test selector, không test channel wiring | Sai tên recipient, thiếu handler | Tạo integration test với context thực |

## 14. Bài thực hành: phát sự kiện thanh toán

Thiết kế một flow nhận **PaymentCompleted(paymentId, amountVnd, riskScore, notifyCustomer)** với các yêu cầu:

1. **Audit** nhận mọi sự kiện đã thanh toán.
2. **Fraud inspection** nhận khi riskScore từ 80 trở lên **hoặc** amountVnd từ 20.000.000 trở lên.
3. **Notification** nhận khi notifyCustomer=true.
4. **Analytics** nhận mọi sự kiện nhưng có thể xử lý bất đồng bộ.
5. Mọi nhánh giữ eventId và một businessCorrelationId để truy vết.

Các bước:

- Viết record PaymentCompleted và các selector thuần Java.
- Dùng routeToRecipients để khai báo hai recipient vô điều kiện và hai recipient có điều kiện.
- Tạo IntegrationFlow riêng cho từng recipient; analytics có thể dùng ExecutorChannel với bounded executor.
- Kiểm thử bốn tổ hợp chính của hai điều kiện và một thông điệp có cả hai điều kiện đúng.
- Mô phỏng một nhánh DirectChannel thất bại; so sánh fail fast và ignoreSendFailures(true).
- Đề xuất nâng cấp khi audit bắt buộc tồn tại sau restart: transactional outbox, broker/message store bền, retry, deduplication và giám sát.

### Nâng cao: ghép hai kết quả

Giả sử từ PaymentCompleted cần tính **phí** và **thuế**, rồi hợp nhất hai kết quả. Sử dụng recipient list với applySequence=true, hai recipient tạo message reply vào Aggregator, cấu hình release strategy và timeout. Tự trả lời:

- Nếu một selector không chọn nhánh thuế thì sequenceSize nào hợp lý?
- Nếu nhánh phí xử lý xong nhưng nhánh thuế không trả reply thì nhóm được giữ bao lâu?
- Nếu retry cả message làm một nhánh trả kết quả hai lần thì Aggregator nhận biết bằng cách nào?

### Câu hỏi tự kiểm tra

1. Recipient List khác Router dựa vào header chọn một nhánh ở điểm nào?
2. Một message thỏa ba selector sẽ được gửi tới bao nhiêu recipient?
3. Recipient List khác Splitter thế nào?
4. Default output channel xử lý trường hợp nào; có cứu mọi lỗi downstream không?
5. Tại sao ignoreSendFailures(true) không thay thế error channel?
6. Khi nào cần applySequence=true và cần cấu hình gì ở Aggregator?
7. Vì sao ba DirectChannel không tạo fan-out nguyên tử trên ba hệ thống ngoài?
8. Khi một event được retry, điều gì giúp audit tránh ghi trùng?

## 15. Checklist khi thiết kế recipient list

- Xác định recipient **bắt buộc** và recipient **có điều kiện**.
- Chuẩn hóa payload/header trước khi đánh giá selector.
- Tách rule nghiệp vụ thành hàm có unit test.
- Đảm bảo mỗi recipient channel tồn tại và có endpoint phù hợp.
- Quy định rõ fallback cho message không khớp recipient.
- Quy định chính sách lỗi cho từng nhánh, đặc biệt với ignoreSendFailures.
- Chỉ bật applySequence khi downstream cần grouping/correlation.
- Đánh giá ordering, thread, transaction, durability và backpressure theo channel.
- Có eventId và idempotency nếu retry có thể phát sự kiện trùng.
- Kiểm thử toàn bộ tập recipient, trường hợp lỗi và việc quan sát từng nhánh.

**Kết luận:** RecipientListRouter trả lời câu hỏi **“message này cần được gửi đến những recipient nào?”**. Nó không tự đảm bảo các nhánh xử lý thành công, nguyên tử hay bền vững. Khi tách rõ **quy tắc chọn recipient** khỏi **hợp đồng xử lý và phục hồi của mỗi nhánh**, chúng ta xây dựng được luồng Spring Integration linh hoạt, dễ mở rộng và dễ kiểm chứng.

## Tài liệu tham khảo

- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): RecipientListRouter, danh sách recipient và selector.
- [Spring Integration Reference — Java DSL Routers](https://docs.spring.io/spring-integration/reference/dsl/java-routers.html): routeToRecipients, recipientMessageSelector và recipientFlow.
- [Spring Integration Reference — Common Router Parameters](https://docs.spring.io/spring-integration/reference/router/common-parameters.html): applySequence, defaultOutputChannel, resolutionRequired, sendTimeout, ignoreSendFailures.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, sequence và điều kiện release khi ghép kết quả.
