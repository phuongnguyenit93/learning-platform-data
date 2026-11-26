# Có nên dùng event không

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events là một cách để các module phản ứng với sự kiện nghiệp vụ mà không cần gọi trực tiếp implementation của nhau. Nhưng event không tự động làm kiến trúc tốt hơn. Nó thêm cơ chế dispatch, transaction boundary, xử lý bất đồng bộ, retry, idempotency, quan sát và quản trị contract. Nếu một lời gọi trực tiếp đã diễn đạt đúng quan hệ và đáp ứng yêu cầu, thêm event có thể chỉ làm hệ thống khó hiểu hơn.

Câu hỏi **“Có nên dùng event không?”** cần được trả lời dựa trên bản chất của tương tác: bên gọi cần kết quả ngay hay chỉ thông báo một điều đã xảy ra; các bên có cần độc lập về thời gian triển khai và xử lý không; có bao nhiêu consumer; consistency cần mạnh tới mức nào; và đội ngũ có thể vận hành retry, duplicate, backlog cùng event contract hay không.

Event phù hợp khi một module công bố sự thật nghiệp vụ để một hoặc nhiều module khác tự quyết định phản ứng. Lời gọi trực tiếp phù hợp khi một use case cần yêu cầu một collaborator thực hiện hành động và cần kết quả ngay để tiếp tục hoặc từ chối transaction. Chọn đúng cơ chế giúp giữ ranh giới module rõ ràng mà không tạo ra độ phức tạp không cần thiết.

## 1. Phân biệt điều đang xảy ra: yêu cầu hay sự kiện?

Trước khi chọn công nghệ, hãy xác định ý nghĩa của thông điệp.

- **Command:** yêu cầu một thành phần thực hiện hành động. Ví dụ ReserveInventory hoặc CapturePayment.
- **Event:** thông báo một điều đã xảy ra. Ví dụ OrderConfirmed hoặc PaymentCaptured.
- **Query:** yêu cầu dữ liệu để caller đưa ra quyết định. Ví dụ GetAvailableInventory.

Command thường có một owner chịu trách nhiệm thực hiện và trả kết quả. Event mô tả một fact đã xảy ra; zero, one hoặc nhiều consumer có thể quan tâm. Query thường cần câu trả lời trong luồng hiện tại.

Không đặt tên command như event chỉ để dùng publisher. ReserveInventoryRequested có thể là command nếu người nhận được yêu cầu giữ hàng. InventoryReserved là event nếu việc giữ hàng đã hoàn tất. Nếu consumer nhận một event nhưng thực tế phải quyết định có thực hiện hành động hay không, hãy làm rõ đó là command hay fact.

## 2. Ba lựa chọn giao tiếp phổ biến

Trong Spring Modulith, có thể lựa chọn lời gọi trực tiếp qua public API, application event trong cùng application context hoặc integration event qua broker.

| Cách giao tiếp | Ý nghĩa | Khi phù hợp |
|---|---|---|
| Direct call | Caller gọi public API và nhận kết quả | Cần kết quả ngay, quan hệ phụ thuộc rõ |
| In-process application event | Producer công bố fact cho listener trong ứng dụng | Nhiều phản ứng độc lập, không muốn caller biết consumer |
| Broker/integration event | Công bố contract cho service hoặc hệ thống độc lập | Cần tách triển khai, transport hoặc xử lý ngoài ứng dụng |

Không coi ba cách này là các cấp độ trưởng thành bắt buộc. Một ứng dụng có thể dùng direct call cho use case cần phản hồi tức thì, application event cho các phản ứng nội bộ và broker cho tích hợp bên ngoài. Điều quan trọng là mỗi boundary dùng cơ chế có semantics phù hợp.

## 3. Khi nào nên dùng lời gọi trực tiếp?

Direct call thường là lựa chọn rõ ràng khi caller cần kết quả để quyết định bước tiếp theo. Ví dụ, Checkout cần xác nhận hạn mức tín dụng trước khi chấp nhận đơn. Nếu kết quả từ Credit module quyết định ngay use case thành công hay thất bại, gọi public API có thể dễ hiểu hơn việc phát event rồi chờ một phản hồi qua một quy trình khác.

Nên ưu tiên direct call khi:

- Caller cần kết quả đồng bộ để tiếp tục hoặc dừng use case.
- Có một collaborator rõ ràng chịu trách nhiệm xử lý.
- Hành động là một phần của cùng quy trình nghiệp vụ và cần phản hồi ngay.
- Việc tách xử lý sang thời điểm khác không tạo giá trị.
- Số consumer và ownership đã rõ.
- Consistency yêu cầu caller quan sát được kết quả trước khi hoàn tất.

Ví dụ:

~~~java
@Service
class CheckoutService {

    private final CreditLimit creditLimit;

    CheckoutService(CreditLimit creditLimit) {
        this.creditLimit = creditLimit;
    }

    public CheckoutResult checkout(CheckoutCommand command) {
        CreditDecision decision =
            creditLimit.authorize(command.customerId(), command.total());

        if (!decision.approved()) {
            return CheckoutResult.rejected(decision.reason());
        }

        return CheckoutResult.accepted(command.orderId());
    }
}
~~~

Ví dụ này minh họa một lời gọi qua abstraction/public API. Nếu hai module nằm trong cùng ứng dụng Spring Modulith, dependency cần tuân thủ module API và hướng dependency được kiến trúc cho phép. Direct call không đồng nghĩa được truy cập repository hoặc package nội bộ của module khác.

## 4. Khi nào nên dùng event?

Event phù hợp khi producer đã hoàn thành một sự kiện và không cần biết mọi consumer sẽ làm gì với nó. Ví dụ Order được xác nhận; Inventory có thể giữ hàng, Notification gửi thông báo và Analytics cập nhật projection. Producer không cần gọi lần lượt từng implementation để hoàn tất trách nhiệm của module Order.

Dấu hiệu event mang lại giá trị:

- Một sự kiện có nhiều consumer độc lập.
- Consumer có thể được thêm hoặc thay đổi mà producer không cần biết implementation.
- Producer chỉ cần công bố fact đã xảy ra.
- Một số phản ứng có thể diễn ra sau khi transaction nguồn commit.
- Consumer có thể xử lý ở thời điểm khác và chấp nhận eventual consistency.
- Các module có ownership riêng và giao tiếp qua contract công khai.
- Việc tách thời gian xử lý giúp giảm latency hoặc cô lập lỗi.

Ví dụ, sau khi Order được xác nhận, việc gửi email xác nhận không nhất thiết phải nằm trong request của khách hàng. Notification module có thể xử lý sau commit. Producer không cần phụ thuộc vào mail provider hoặc logic template.

Event có giá trị khi nó thể hiện một fact có ý nghĩa nghiệp vụ. Không phát event chỉ vì muốn thay một method call bằng một cơ chế gián tiếp.

## 5. Cây quyết định nhanh

Có thể dùng các câu hỏi sau để chọn cơ chế:

~~~mermaid
flowchart TD
    A["Caller cần kết quả ngay để quyết định?"] -->|Có| B["Dùng direct call/public API"]
    A -->|Không| C["Thông điệp mô tả fact đã xảy ra?"]
    C -->|Không| D["Đây là command hoặc query; dùng API/command flow phù hợp"]
    C -->|Có| E["Có consumer độc lập hoặc nhiều phản ứng?"]
    E -->|Không| F["Cân nhắc direct call đơn giản hơn"]
    E -->|Có| G["Các consumer chấp nhận xử lý trễ/eventual consistency?"]
    G -->|Có| H["Dùng event; xác định durability và retry"]
    G -->|Không| I["Giữ orchestration đồng bộ hoặc thiết kế workflow có kết quả rõ"]
~~~

Cây quyết định là hướng dẫn ban đầu, không phải luật cứng. Một event có thể được dùng ngay cả khi chỉ có một consumer nếu nó thể hiện boundary nghiệp vụ quan trọng và consumer cần độc lập. Ngược lại, nhiều consumer không tự động có nghĩa phải dùng broker; application event nội bộ có thể đủ.

## 6. Event giúp giảm coupling ở đâu?

Với direct call, caller thường biết API của collaborator và có thể phụ thuộc vào thời điểm phản hồi, exception hoặc availability của nó. Khi dùng event, producer chỉ cần biết contract event và cơ chế publish. Consumer tự đăng ký quan tâm và sở hữu hành động tiếp theo.

Ví dụ:

~~~mermaid
flowchart LR
    subgraph Direct["Direct calls"]
        O1["Order"] --> I1["Inventory API"]
        O1 --> N1["Notification API"]
        O1 --> A1["Analytics API"]
    end
    subgraph Events["Event publication"]
        O2["Order"] --> E["OrderConfirmed"]
        E --> I2["Inventory listener"]
        E --> N2["Notification listener"]
        E --> A2["Analytics listener"]
    end
~~~

Trong mô hình event, Order không cần import hoặc gọi từng listener. Tuy nhiên, coupling vẫn tồn tại ở contract: consumer cần hiểu event type, schema, semantics và version. Nếu producer đổi ý nghĩa event, consumer có thể bị ảnh hưởng dù không có compile-time dependency.

Event giảm coupling implementation và ownership khi contract được thiết kế tốt. Nó không xóa coupling dữ liệu, ngữ nghĩa, thời gian hoặc vận hành.

## 7. Event có thực sự cần bất đồng bộ không?

Không. Application event trong Spring không mặc định luôn bất đồng bộ. Với event multicaster mặc định, listener thông thường thường chạy đồng bộ trong luồng publish. Cấu hình executor hoặc annotation listener có thể thay đổi hành vi.

Phân biệt:

- **Event-driven:** giao tiếp được kích hoạt bởi một event.
- **Asynchronous:** producer không chờ listener hoàn tất trong cùng call stack.
- **Durable messaging:** message hoặc publication được lưu bền vững để phục hồi sau lỗi.
- **Distributed messaging:** event được truyền qua boundary process/network.

Một event có thể được xử lý đồng bộ trong cùng process. Một message broker có thể được dùng theo cách consumer xử lý gần như tức thì nhưng vẫn độc lập process. Không suy luận durability chỉ từ việc listener chạy async.

Chọn async khi consumer không cần kết quả trong request và hệ thống chấp nhận độ trễ. Nếu caller phải biết giữ hàng thành công trước khi xác nhận đơn, không thể đơn giản chuyển thao tác giữ hàng thành event async rồi coi đơn đã hoàn tất mà không có workflow hoặc trạng thái trung gian phù hợp.

## 8. Khi nào event trong cùng Spring Modulith là đủ?

Nếu producer và consumer là các application module trong cùng một ứng dụng, application event nội bộ có thể là lựa chọn phù hợp. Producer công bố event qua Spring event publisher; listener thuộc module nhận phản ứng qua contract.

Ví dụ:

~~~java
public record OrderConfirmed(
    String orderId,
    Instant occurredAt
) {}
~~~

~~~java
@Service
class OrderApplicationService {

    private final ApplicationEventPublisher events;

    OrderApplicationService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void confirm(Order order) {
        order.confirm();
        events.publishEvent(new OrderConfirmed(
            order.getId(),
            Instant.now()
        ));
    }
}
~~~

~~~java
@Component
class InventoryOrderListener {

    private final InventoryApplicationService inventory;

    InventoryOrderListener(InventoryApplicationService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        inventory.reserveFor(event.orderId());
    }
}
~~~

Ví dụ rút gọn minh họa public event contract và listener ở module nhận. Trong ứng dụng thực tế, cần dùng Clock được quản lý, DTO phù hợp và cấu hình transaction/listener theo phiên bản Spring Modulith đang dùng. @ApplicationModuleListener có semantics riêng về async và transactional event listener; kiểm tra cấu hình thực tế trước khi giả định thời điểm xử lý.

Nếu chỉ có một consumer, không có yêu cầu tách thời gian và lời gọi trực tiếp dễ hiểu hơn, public API có thể là lựa chọn đơn giản. Nếu event diễn đạt fact quan trọng và module khác cần phản ứng độc lập, application event giúp giữ ownership tốt hơn.

## 9. Khi nào cần broker hoặc integration event?

Không cần đưa mọi application event qua broker. Broker có ý nghĩa khi cần giao tiếp qua process/network boundary, consumer triển khai độc lập, lưu trữ message theo semantics transport, hoặc tích hợp với hệ thống bên ngoài.

Cân nhắc broker khi:

- Producer và consumer có vòng đời triển khai riêng.
- Consumer không nằm trong cùng application context.
- Cần buffer khi consumer tạm thời không hoạt động.
- Cần partitioning, consumer group, replay hoặc throughput theo transport.
- Có nhiều hệ thống cần nhận contract tích hợp.
- Cần cô lập availability giữa các service.

Khi dùng broker, phải quản lý thêm schema compatibility, authentication/authorization, network, retry, redelivery, ordering, DLQ, observability và vận hành cluster. Không dùng broker chỉ để tạo cảm giác microservice-ready nếu các module vẫn cùng deploy và application event đáp ứng yêu cầu.

## 10. Khi nào không nên dùng event?

Event thường là lựa chọn không phù hợp trong các trường hợp sau:

- Caller cần câu trả lời ngay và không có workflow bất đồng bộ được thiết kế.
- Tương tác chỉ là một bước nội bộ đơn giản, một collaborator duy nhất và không có nhu cầu tách.
- Consumer phải được gọi theo thứ tự chặt chẽ để tạo một kết quả duy nhất, nhưng event flow không có orchestration rõ.
- Hệ thống không thể chấp nhận eventual consistency hoặc trạng thái trung gian.
- Event chỉ che giấu một command/query mà không mang ý nghĩa fact.
- Không có khả năng vận hành retry, duplicate, backlog hoặc message failure.
- Payload và schema chưa ổn định, consumer không có chiến lược versioning.
- Team chưa có cách quan sát event end-to-end và xác định owner khi xử lý thất bại.

Đặc biệt, không dùng event để tránh thiết kế API. Một OrderService phát CheckCustomerCredit rồi chờ một listener nào đó cập nhật kết quả có thể làm flow khó theo dõi hơn direct call. Nếu thực sự cần workflow async, hãy mô hình hóa trạng thái, correlation, timeout, compensation và kết quả rõ ràng.

## 11. Tránh event cho query cần kết quả tức thì

Query cần một câu trả lời tại thời điểm gọi. Nếu Checkout cần giá hiện tại hoặc hạn mức tín dụng để quyết định có chấp nhận request, query API thường rõ ràng hơn việc phát event CreditLimitRequested và chờ CreditLimitChecked.

Một query có thể được cache hoặc tối ưu riêng. Nếu chuyển query thành event, cần correlation ID, reply event, timeout, reply routing, trạng thái pending và xử lý late reply. Đó là một request/reply messaging pattern, không phải event notification đơn giản.

Dùng request/reply qua broker khi có lý do kiến trúc rõ ràng như boundary network, protocol hoặc khả năng chịu lỗi. Nếu chỉ cần gọi một module trong cùng ứng dụng, public API đồng bộ thường dễ hiểu và dễ kiểm thử hơn.

## 12. Tránh event để điều phối chuỗi hành động đồng bộ

Giả sử quy trình xác nhận đơn phải kiểm tra tồn kho, giữ hàng, tính phí và xác nhận thanh toán trước khi trả kết quả. Nếu mọi bước được phát thành event và mỗi listener phát event tiếp theo, caller khó biết quy trình đã hoàn tất hay đang ở trạng thái nào.

Với quy trình có thứ tự và kết quả cần được tổng hợp, cân nhắc:

- Application service điều phối qua public API.
- Process manager hoặc saga có state rõ ràng nếu quy trình kéo dài và bất đồng bộ.
- Command cho yêu cầu thực hiện hành động.
- Event cho fact sau khi mỗi bước hoàn tất.
- Timeout, retry và compensation được mô hình hóa rõ.

Không dùng một event chain vô danh để thay orchestration. Event có thể là tín hiệu giữa các bước, nhưng vẫn cần một thành phần chịu trách nhiệm tiến trình tổng thể khi nghiệp vụ yêu cầu.

## 13. Transaction và độ tin cậy: event không tự bảo đảm giao nhận

Publish application event không tự động bảo đảm message sẽ được xử lý đúng một lần hoặc tồn tại sau khi process chết. Độ tin cậy phụ thuộc listener type, transaction phase, persistence registry, outbox hoặc broker adapter.

Cần trả lời:

- Event được publish trong transaction nào?
- Listener chạy trước hay sau commit?
- Nếu transaction rollback thì điều gì xảy ra?
- Nếu listener thất bại sau source commit, ai retry?
- Publication state được lưu bền vững ở đâu?
- Consumer có thể nhận duplicate không?
- Business effect và inbox/dedup marker có commit nguyên tử không?
- Nếu external API timeout không rõ kết quả thì làm sao reconcile?

Với Spring Modulith, Event Publication Registry theo dõi publication tới transactional listeners và có thể hỗ trợ phát hiện/phục hồi publication chưa hoàn tất theo cấu hình. Nó không phải một distributed transaction bao trùm mọi consumer hoặc external system. Với external messaging, có thể cần transactional outbox và consumer idempotency.

Không hứa exactly-once chỉ vì dùng event hoặc broker. Thiết kế thực tế thường cần at-least-once delivery kết hợp idempotent consumer.

## 14. Event và eventual consistency

Khi consumer xử lý sau khi producer commit, hai module có thể tạm thời nhìn thấy trạng thái khác nhau. Ví dụ Order đã CONFIRMED nhưng Inventory chưa ghi reservation. Đây là eventual consistency.

Event phù hợp khi nghiệp vụ chấp nhận khoảng thời gian đó và hệ thống có trạng thái minh bạch. UI hoặc API có thể trả CONFIRMATION_PENDING hoặc PROCESSING trong khi consumer hoàn tất. Nếu nghiệp vụ yêu cầu không bao giờ có đơn CONFIRMED khi chưa giữ được hàng, cần điều chỉnh state model hoặc dùng orchestration đồng bộ.

Đánh giá eventual consistency theo:

- Độ trễ tối đa có thể chấp nhận.
- Hành vi UI/API trong thời gian pending.
- Điều kiện chuyển trạng thái thành công/thất bại.
- Retry và thời hạn hoàn tất.
- Compensation nếu bước sau không thành công.
- Cách đối soát khi event bị kẹt hoặc consumer dừng.

Đừng chỉ nói eventual consistency sẽ tự hội tụ. Hãy mô tả thời gian, trạng thái trung gian và quy trình khi không hội tụ.

## 15. Event contract và ownership

Một event công khai là contract. Module phát event chịu trách nhiệm ý nghĩa và schema; consumer chịu trách nhiệm phản ứng theo phần contract mà nó sử dụng.

Contract nên xác định:

- Event type và ý nghĩa nghiệp vụ.
- eventId, occurredAt và correlation metadata.
- Field bắt buộc, optional, nullable và đơn vị.
- Schema version và quy tắc thay đổi tương thích.
- Consumer được phép bỏ qua field/enum nào.
- Payload chứa snapshot hay reference.
- Retention và dữ liệu nhạy cảm.
- Owner producer và danh sách consumer.

Không công bố toàn bộ entity hoặc database row như integration event. Tạo DTO dành riêng cho contract. Domain event nội bộ có thể chi tiết hơn, nhưng không nên làm consumer phụ thuộc cấu trúc persistence của producer.

## 16. Event fan-out và chi phí consumer

Một event có nhiều consumer giúp producer không phải biết từng consumer. Tuy nhiên, fan-out làm tăng số lượng tác vụ, điểm lỗi và tác động khi schema thay đổi.

Ví dụ OrderConfirmed được Inventory, Notification, Analytics và FraudDetection xử lý. Nếu một consumer bị lỗi, producer vẫn có thể hoàn thành use case; nhưng đội vận hành cần biết consumer nào chưa hoàn tất.

Trước khi chọn fan-out, xác định:

- Consumer nào thực sự cần event.
- Consumer nào là critical path và consumer nào best-effort.
- Một consumer lỗi có ảnh hưởng consumer khác không.
- Mỗi consumer có retry và idempotency riêng không.
- Ai sở hữu alert và backlog.
- Consumer mới có thể được thêm mà không làm thay đổi semantics producer không.

Không thêm listener chỉ để ghi log hoặc gửi một metric nếu instrumentation trực tiếp là đủ. Event fan-out có chi phí vận hành; chỉ tạo consumer khi có trách nhiệm nghiệp vụ hoặc dữ liệu riêng.

## 17. Kiểm tra khả năng quan sát trước khi chọn event

Event làm luồng thực thi gián tiếp hơn. Nếu không có metadata và telemetry, việc tìm nguyên nhân có thể khó hơn direct call.

Một thiết kế event cần tối thiểu:

- eventId duy nhất và ổn định qua retry.
- correlationId liên kết business flow.
- causationId nếu cần biết event/command nào gây ra event hiện tại.
- Log structured ở producer và consumer.
- Metrics theo eventType, consumer và outcome.
- Trace context qua các boundary được hỗ trợ.
- Dashboard cho publication incomplete, outbox backlog, queue/lag, retry và DLQ.
- Owner và runbook khi consumer không tiến triển.

Không dùng eventId hoặc customerId làm metric label có cardinality cao. Tránh ghi payload nhạy cảm vào log. Nếu team chưa thể theo dõi event end-to-end, hãy cân nhắc giữ tương tác đồng bộ đơn giản cho tới khi năng lực vận hành được bổ sung.

## 18. So sánh chi phí và trade-off

| Tiêu chí | Direct call | In-process event | Broker event |
|---|---|---|---|
| Kết quả ngay | Có | Không mặc định; tùy listener | Thường không |
| Coupling implementation | Rõ và trực tiếp | Thấp hơn giữa producer/consumer | Thấp hơn qua process boundary |
| Thứ tự xử lý | Dễ biểu đạt trong call flow | Phụ thuộc listener và executor | Phụ thuộc transport/topology |
| Eventual consistency | Không bắt buộc | Có nếu xử lý sau commit/async | Thường có |
| Durability | Theo transaction/call | Cần registry/persistence phù hợp | Theo broker và producer design |
| Retry/duplicate | Caller tự quản lý lỗi call | Cần listener/registry policy | Cần broker/consumer policy |
| Observability | Stack trace thường trực tiếp | Cần correlation/tracing | Cần tracing xuyên service |
| Vận hành | Thường đơn giản hơn | Thêm lifecycle listener | Thêm broker và topology |
| Fan-out | Caller biết từng collaborator | Tự nhiên trong application context | Tự nhiên qua subscriptions |
| Schema evolution | Compile-time có thể giúp | Cần lưu ý event persisted/replay | Cần contract/versioning rõ |

Không có lựa chọn tốt nhất cho mọi tiêu chí. Chọn theo yêu cầu nghiệp vụ và khả năng vận hành, không theo xu hướng kiến trúc.

## 19. Ví dụ quyết định: xác nhận đơn hàng

Giả sử khi khách hàng đặt hàng, hệ thống cần:

1. Kiểm tra dữ liệu và giá.
2. Xác nhận đơn.
3. Giữ tồn kho.
4. Gửi email xác nhận.
5. Cập nhật analytics.

Không nhất thiết mọi bước dùng cùng một cơ chế.

- Kiểm tra dữ liệu và giá cần kết quả ngay: gọi service/public API.
- Giữ tồn kho nếu là điều kiện bắt buộc trước khi xác nhận: dùng orchestration có kết quả rõ, có thể direct call hoặc saga tùy thời gian và boundary.
- Gửi email sau khi đơn được xác nhận: event phù hợp vì không cần chặn response.
- Cập nhật analytics: event phù hợp vì consumer độc lập và có thể xử lý trễ.
- Nếu gửi event tới hệ thống ngoài: dùng integration contract và cơ chế giao nhận bền vững phù hợp.

~~~mermaid
flowchart TD
    A["Checkout request"] --> B["Validate and price via API"]
    B --> C["Reserve inventory / required workflow"]
    C --> D["Commit OrderConfirmed"]
    D --> E["Publish OrderConfirmed event"]
    E --> F["Notification consumer"]
    E --> G["Analytics consumer"]
~~~

Sơ đồ minh họa việc chọn nhiều cơ chế trong một use case. Event không phải lựa chọn duy nhất cho toàn bộ luồng. Nếu giữ hàng là bất đồng bộ, state machine cần thể hiện đơn đang chờ reservation và cách xử lý thất bại.

## 20. Những anti-pattern cần tránh

- **Event cho mọi method call:** làm flow gián tiếp mà không giảm coupling có ý nghĩa.
- **Event giả dạng command:** tên là fact nhưng consumer thực hiện yêu cầu chưa được xác nhận.
- **Request/reply không cần thiết:** dùng event để lấy câu trả lời tức thì trong cùng process.
- **Event chain không owner:** không có process manager chịu trách nhiệm tiến trình.
- **God event:** một payload chứa nhiều field và nhiều mục đích cho mọi consumer.
- **Hidden synchronous dependency:** producer tưởng không phụ thuộc consumer nhưng listener đồng bộ vẫn làm request chậm hoặc fail.
- **Fire-and-forget không quan sát:** không có retry, registry, outbox hoặc alert.
- **Không idempotency:** retry/redelivery tạo tác dụng phụ trùng.
- **Shared entity event:** consumer phụ thuộc entity persistence của producer.
- **Premature broker:** thêm broker và topology khi in-process event đủ đáp ứng.

Khi gặp một anti-pattern, hãy quay lại câu hỏi caller cần gì, fact nào đã xảy ra và ai sở hữu hành động. Đôi khi giải pháp đúng là đổi event thành direct call; đôi khi cần thiết kế lại thành command, process manager hoặc integration event có contract rõ.

## 21. Quy trình ra quyết định có dùng event

Có thể dùng quy trình sau trong design review:

1. Mô tả tương tác bằng một câu và xác định đó là command, query hay fact.
2. Xác định caller cần kết quả ngay hay chỉ cần công bố điều đã xảy ra.
3. Xác định module sở hữu hành động và dữ liệu.
4. Liệt kê số consumer và mức độ độc lập của từng consumer.
5. Đánh giá yêu cầu consistency và độ trễ tối đa.
6. Chọn direct call, in-process event hoặc broker event.
7. Xác định transaction phase, durability và retry.
8. Xác định duplicate handling, idempotency và ordering.
9. Thiết kế event contract, versioning và data minimization.
10. Xác định log, metrics, trace, alert và owner.
11. Kiểm thử failure path, rollback, replay và consumer unavailable.
12. Ghi lại lý do chọn cùng trade-off chấp nhận.

Nếu không có lợi ích cụ thể từ event, giữ direct call. Nếu event giúp tách ownership và consumer có thể phản ứng độc lập, dùng event với contract và vận hành tương xứng.

## 22. Ví dụ cách ghi quyết định kiến trúc

Một ADR ngắn có thể ghi:

~~~text
Decision: Publish OrderConfirmed as an application event.

Context:
Order confirmation has independent reactions in Inventory,
Notification and Analytics. Order does not need their completion
to return the confirmation result.

Consequences:
- Consumers own their reaction and may process after commit.
- Order does not call consumer implementations directly.
- Consumers must be idempotent and observable.
- Publication recovery and retry policy must be configured.
- The event contract requires versioning and compatibility tests.

Rejected option:
Directly invoking every consumer from Order would make Order
depend on each consumer's availability and implementation.
~~~

Ví dụ này phù hợp khi các consumer thực sự độc lập và kết quả của chúng không phải điều kiện đồng bộ để xác nhận đơn. Nếu Inventory reservation là điều kiện bắt buộc trước khi đơn được xác nhận, cần thay đổi quyết định hoặc mô hình hóa một workflow có trạng thái.

## 23. Kết luận thực hành

Dùng event khi producer công bố một fact có ý nghĩa nghiệp vụ, có consumer độc lập hoặc nhiều phản ứng cần tách khỏi use case nguồn, và hệ thống chấp nhận xử lý theo thời gian riêng. Dùng direct call khi caller cần kết quả ngay, có một collaborator rõ ràng và consistency cần được quyết định trong cùng luồng.

Với Spring Modulith, application event là công cụ giữ ranh giới giữa các module trong cùng ứng dụng; broker event là lựa chọn cho boundary process hoặc hệ thống độc lập. Cả hai đều cần contract rõ, transaction semantics, retry, idempotency và observability tương xứng với mức độ tin cậy yêu cầu.

Quyết định tốt không phải là đưa càng nhiều tương tác thành event càng tốt. Đó là chọn cơ chế đơn giản nhất vẫn đáp ứng đúng semantics, consistency, ownership và khả năng vận hành của nghiệp vụ. Khi chưa có lợi ích rõ ràng, direct call qua public module API thường là điểm bắt đầu hợp lý; khi cần công bố fact để consumer độc lập phản ứng, event trở thành lựa chọn phù hợp.

