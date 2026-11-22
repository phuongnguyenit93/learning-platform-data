# Discard message mà không có audit

## 1. Lỗi thường gặp: message biến mất nhưng không ai biết vì sao

Trong module **SPRING_INTEGRATION_PATTERN**, Spring Integration giúp tổ chức luồng message bằng các Enterprise Integration Patterns (EIP): **Gateway** tiếp nhận yêu cầu, **Filter** kiểm tra điều kiện, **Transformer** biến đổi payload, **Router** chọn nhánh, **Splitter** tách công việc, **Aggregator** ghép kết quả và **Service Activator** gọi hệ thống khác. Các thành phần kết nối qua channel nên có thể mở rộng độc lập, nhưng việc một message bị loại bỏ ở giữa flow thường khó nhận ra nếu không có chính sách ghi nhận.

Ví dụ một đơn hàng được gửi qua Gateway nhưng có số lượng âm. Filter trả **false** để loại message. Nếu flow không định nghĩa đường **discard**, message có thể kết thúc ở đó mà không có phản hồi nghiệp vụ hoặc hồ sơ ghi nhận phù hợp. Người dùng chỉ thấy request chờ quá hạn; đội vận hành không biết yêu cầu đã bị loại do validation, lỗi routing hay một exception từ dependency.

**Discard** là quyết định không tiếp tục xử lý một message ở đường chính. Điều đó có thể hoàn toàn hợp lý, nhưng **discard không có audit** khiến hệ thống mất khả năng giải thích quyết định, đối soát số lượng công việc và điều tra sự cố.

Các câu hỏi cần trả lời:

1. Message nào đã bị loại và ở **điểm xử lý nào**?
2. Nó bị loại vì **quy tắc nghiệp vụ**, không tìm thấy route hay **quá hạn**?
3. Có phải một message trùng lặp hợp lệ đã được bỏ qua không?
4. Người gửi hoặc workflow gốc đã nhận kết quả **REJECTED / DROPPED / EXPIRED** chưa?
5. Có đủ **correlation ID** và dữ liệu audit để truy vết mà không làm lộ thông tin nhạy cảm?
6. Nếu hệ thống audit hỏng, liệu nghiệp vụ có được phép xác nhận đã xử lý không?

Bài học này phân biệt **discard**, **error**, **fallback** và **dead-letter**; thiết kế một đường audit an toàn, rồi minh họa Java DSL với Spring Integration và phương pháp kiểm thử.

~~~mermaid
flowchart TD
    A[Gateway / Inbound Adapter] --> B[Filter]
    B -->|Pass| C[Router / Service Activator]
    B -->|Reject| D[Discard branch]
    D --> E[Ghi audit với reason code]
    E --> F[Trả REJECTED hoặc xử lý theo policy]
    C --> G[Main outcome]
    E -.-> H[Metrics / Trace]
    G -.-> H
~~~

**Không phải mọi message bị discard đều là sự cố.** Ví dụ Filter bỏ event không thuộc subscription là quyết định bình thường. Tuy nhiên loại bỏ một lệnh nghiệp vụ, message bất thường, dữ liệu không hợp lệ hoặc một nhánh Aggregator hết hạn có thể cần dấu vết audit bền vững. Mức độ ghi nhận phải do chính sách dữ liệu và yêu cầu đối soát quyết định.

## 2. Phân biệt discard, exception, dead-letter và kết quả nghiệp vụ

| Tình huống | Ý nghĩa | Đường xử lý nên cân nhắc |
| --- | --- | --- |
| Filter trả false | Message không đạt predicate | Discard channel, outcome rõ ràng và audit nếu có ý nghĩa nghiệp vụ |
| Router không có route phù hợp | Không xác định nhánh hợp lệ | Default route, reject có cấu trúc hoặc fail fast |
| Dữ liệu hợp lệ nhưng trùng | Không thực thi lần nữa vì idempotency | Ghi duplicate outcome nếu cần đối soát; không tạo side effect |
| Aggregator hết hạn nhóm | Không nhận đủ các phần | Expiry/timeout policy, partial/failed outcome và audit nhóm |
| Handler ném exception | Xử lý thất bại kỹ thuật | Exception hoặc ErrorMessage/error channel tùy ranh giới |
| Message không thể xử lý sau retry | Hết attempt budget hoặc không thể phục hồi | Dead-letter/parking lot kèm nguyên nhân và khả năng replay |
| Message được xử lý thành công | Hoàn tất theo hợp đồng | Success outcome; không ghi nhận như discard |

**Error channel không đồng nghĩa discard channel.** Một Filter trả false thường là nhánh xử lý bình thường, không nhất thiết ném exception; bởi vậy không được mặc định một error channel chung sẽ ghi nhận mọi message bị loại.

Ngược lại, một exception ở Service Activator không phải một “discard có chủ ý”. Nếu biến mọi lỗi kỹ thuật thành rejected business outcome, có thể che mất dependency outage và làm circuit breaker, retry, alert hoạt động sai.

### Khi nào cần audit bền vững?

- Lệnh thay đổi trạng thái nghiệp vụ như đặt hàng, hủy đơn, ghi giao dịch.
- Message không được xử lý do validation, authorization, route không hợp lệ hoặc hết thời hạn.
- Nhánh Splitter/Aggregator mất kết quả cần đối soát.
- Event bị loại vì là duplicate nhưng vẫn cần chứng minh đã nhận và bỏ qua.
- Quy trình chịu yêu cầu lưu vết, kiểm toán hoặc giải thích quyết định.

Với telemetry lưu lượng lớn, chẳng hạn một event không liên quan subscription và được bỏ qua theo hợp đồng, có thể chỉ cần **counter/log được lấy mẫu** thay vì một bản ghi lâu dài cho từng event. Chính sách phải nói rõ loại nào được lưu và bao lâu.

## 3. Những điểm silent discard phổ biến trong Spring Integration

### 3.1. Filter không có discard branch

Một Filter chỉ trả true/false; trường hợp false bị chặn khỏi đường output chính. Nếu không cấu hình discard channel hoặc exception behavior, caller có thể không có kết quả rõ ràng để biết message đã đi đâu.

~~~java
// Phản ví dụ: không có nhánh ghi nhận message bị loại.
@Bean
public IntegrationFlow incomingOrders() {
    return IntegrationFlow.from("orders.requests")
            .filter(OrderCommand.class, command -> command.quantity() > 0)
            .handle(OrderCommand.class,
                    (command, headers) -> orderService.accept(command))
            .get();
}
~~~

Nếu Gateway gọi đồng bộ mong có reply và Filter loại message, caller có thể chờ reply rồi timeout. Tùy endpoint và channel, việc từ chối có thể được chuyển thành exception khi cấu hình **throwExceptionOnRejection**; nhưng ném exception không tự tương đương một bản ghi audit bền vững.

### 3.2. Router không có nhánh phù hợp

Router nhận event type mà không có mapping hoặc nhánh fallback có thể xử lý theo các thiết lập như **resolutionRequired** và **defaultOutputChannel**. Nếu chính sách cho phép bỏ qua message không tìm thấy route, một route sai sẽ thành mất dữ liệu khó điều tra.

Cách tốt hơn là có **unknown-route outcome** hoặc channel riêng cho message không được định tuyến, kèm lý do như **NO_MATCHING_ROUTE**. Không bật bỏ qua các route lỗi chỉ để giảm log.

### 3.3. Aggregator group bị hết hạn

Aggregator có thể giữ các message theo **correlation ID** cho tới khi đủ số phần hoặc completion strategy đạt điều kiện. Khi nhóm quá hạn, cơ chế expiry/discard tùy cấu hình có thể làm các message đang chờ không còn đi tiếp.

Phải phân biệt **group đã hoàn thành**, **group hết hạn**, **partial result** và **message đến muộn**. Không chỉ nhìn số reply của Gateway rồi đoán nhóm nào bị mất.

### 3.4. Channel và subscriber

Một Publish-Subscribe Channel hoặc endpoint được cấu hình thiếu subscriber/handler, hay một flow kết thúc mà không còn consumer có thể tạo tình huống message không đến nơi mong đợi; hành vi thực tế phụ thuộc loại channel và cấu hình như yêu cầu có subscriber, timeout gửi và error handling.

Không coi mọi message không được nhận là Filter discard. Cần đo và phân loại lỗi **delivery/routing** riêng. Đối với message quan trọng, phải có cơ chế phát hiện đường xử lý không có consumer hoặc lỗi gửi thay vì âm thầm bỏ qua.

### 3.5. Idempotent receiver bỏ message trùng

Một số flow cố ý loại duplicate để tránh side effect lặp lại. Đây là xử lý đúng về mặt nghiệp vụ, nhưng cần audit đủ để trả lời: event nào đã được chấp nhận trước đó, message mới được coi là trùng theo key gì và outcome nào đã được lưu.

**Không ghi đầy đủ payload ở mọi duplicate**; chỉ cần event key, reason code, thời điểm và tham chiếu tới bản ghi xử lý lần đầu nếu chính sách cho phép.

## 4. Một đường discard có thể kiểm tra và truy vết

Một thiết kế đơn giản chia hai nhánh: nhánh chính chỉ xử lý message được chấp nhận, nhánh discard ghi nhận quyết định rồi trả kết quả rõ ràng cho caller.

~~~mermaid
flowchart LR
    A[Gateway: orders.requests] --> B{Filter quantity > 0}
    B -->|Đúng| C[Order Service]
    B -->|Sai| D[orders.invalid]
    D --> E[Audit appendOnce]
    E --> F[REJECTED + reason code]
    C --> G[ACCEPTED / business outcome]
~~~

Với một Filter xác thực **quantity > 0**, nhánh **orders.invalid** có thể gắn reason code cố định **INVALID_QUANTITY**. Nếu nhiều quy tắc khác nhau cùng gửi tới một discard channel, phải xác định lý do riêng bằng validation result, header được tạo ở bước đáng tin cậy, hoặc channel riêng theo loại. **Filter không tự gắn reason code nghiệp vụ** chỉ vì predicate trả false.

### Hợp đồng audit tối thiểu

| Trường | Mục đích |
| --- | --- |
| **auditEventKey** | Khóa duy nhất cho quyết định để chống ghi trùng khi redelivery |
| **correlationId** | Liên kết message với request/workflow gốc |
| **originalMessageId** | Tham chiếu tới Spring Message nếu còn được giữ |
| **flowName / endpointName** | Nêu nơi message bị discard |
| **reasonCode** | Giá trị có cấu trúc như INVALID_QUANTITY, NO_ROUTE, EXPIRED_GROUP |
| **outcome** | REJECTED, DROPPED_DUPLICATE, EXPIRED hoặc các trạng thái có hợp đồng |
| **occurredAt** | Thời điểm quyết định được ghi nhận |
| **tenantScope / operation** | Ngữ cảnh đã xác thực, đúng phạm vi truy cập |
| **schemaVersion** | Giúp đọc được audit khi mô hình dữ liệu thay đổi |

**Payload có thể chứa dữ liệu cá nhân hoặc bí mật**, vì vậy không tự động dump toàn bộ message vào audit. Lưu trường tối thiểu, có mask/redaction, quyền truy cập, thời hạn giữ và chính sách xóa. Nếu cần chứng minh payload không bị thay đổi, có thể dùng digest hoặc reference tới object được bảo vệ, nhưng không thay thế kiểm soát truy cập dữ liệu gốc.

## 5. Ví dụ Spring Integration Java DSL: discard được ghi audit

Ví dụ cho thấy một Gateway đồng bộ gửi **OrderCommand**; Filter loại số lượng không hợp lệ sang channel riêng; handler tại channel đó **ghi audit trước khi trả REJECTED**. Nhánh pass trả outcome từ **OrderService**.

### 5.1. Các kiểu dữ liệu ứng dụng

~~~java
public record OrderCommand(
        String commandId,
        String tenantId,
        int quantity
) {}

public record OrderDecision(
        String commandId,
        String outcome,
        String reasonCode
) {}

public record DiscardAuditEvent(
        String auditEventKey,
        String correlationId,
        String tenantScope,
        String flowName,
        String reasonCode,
        String outcome,
        Instant occurredAt
) {}

public interface OrderService {
    OrderDecision accept(OrderCommand command);
}

public interface DiscardAuditStore {
    // Ghi bền vững và idempotent theo auditEventKey.
    void appendOnce(DiscardAuditEvent event);
}
~~~

Các record/interface này là **kiểu do ứng dụng định nghĩa**, không phải Spring Integration tự cung cấp. Trong ví dụ, **tenantId** giả định đã được **xác thực ở ingress** và truyền qua context đáng tin cậy. Trong production, không được lấy trực tiếp tenant từ dữ liệu client chưa được kiểm tra để làm khóa audit hoặc phân quyền.

### 5.2. Gateway, Filter và discard channel

~~~java
@MessagingGateway(defaultRequestChannel = "orders.requests")
public interface OrderGateway {
    OrderDecision submit(OrderCommand command);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class OrderFlowConfiguration {

    @Bean
    public IntegrationFlow ordersFlow(OrderService orderService) {
        return IntegrationFlow.from("orders.requests")
                .filter(
                        OrderCommand.class,
                        command -> command.quantity() > 0,
                        endpoint -> endpoint.discardChannel("orders.invalid")
                )
                .handle(
                        OrderCommand.class,
                        (command, headers) -> orderService.accept(command)
                )
                .get();
    }

    @Bean
    public IntegrationFlow invalidOrdersFlow(
            DiscardAuditStore auditStore,
            Clock clock
    ) {
        return IntegrationFlow.from("orders.invalid")
                .handle(OrderCommand.class, (command, headers) -> {
                    String correlation = String.valueOf(
                            headers.getOrDefault(
                                    "correlationId", command.commandId()));

                    String auditKey = command.tenantId()
                            + ":" + command.commandId()
                            + ":quantity-validation";

                    auditStore.appendOnce(new DiscardAuditEvent(
                            auditKey,
                            correlation,
                            command.tenantId(),
                            "orders.quantity-filter",
                            "INVALID_QUANTITY",
                            "REJECTED",
                            clock.instant()
                    ));

                    return new OrderDecision(
                            command.commandId(),
                            "REJECTED",
                            "INVALID_QUANTITY"
                    );
                })
                .get();
    }
}
~~~

Những điều quan trọng trong ví dụ:

1. **Filter pass** thì message đi tới OrderService. Nhánh này không ghi discard audit.
2. **Filter reject** thì message gốc đi tới **orders.invalid**; handler nhận và tạo audit event với lý do cố định.
3. **appendOnce** phải ghi bền vững và loại trùng theo khóa nghiệp vụ. Đây là hợp đồng của storage adapter, không phải một tính năng tự động chỉ nhờ tên phương thức.
4. Chỉ sau khi appendOnce hoàn tất, handler trả **OrderDecision(REJECTED)**; Gateway đồng bộ có thể nhận reply từ nhánh discard nhờ reply headers được truyền theo message.
5. Nếu auditStore thất bại, handler **không trả REJECTED thành công như thể audit đã ghi**. Exception cần được xử lý theo failure policy.
6. Trong một ứng dụng thật, **OrderService** cũng phải trả outcome hợp lệ; nếu muốn có validation đa điều kiện, nên dùng validator tạo reason code riêng thay vì ép mọi lỗi thành INVALID_QUANTITY.

Ví dụ không kèm implementation database và HTTP gateway vì bài tập trung vào luồng discard và audit. Các import thông thường được lược bớt. Khi đưa vào ứng dụng thực, cần kiểm thử end-to-end **request–reply**, transaction boundary và hành vi lỗi của auditStore với phiên bản Spring Integration đang sử dụng.

### Cẩn thận về khóa chống trùng

**auditEventKey** ở ví dụ gắn với **commandId + tenant + bước validation**, ngầm giả định cùng một commandId biểu diễn cùng một lệnh logic. Nếu ứng dụng cho phép commandId dùng lại hoặc có nhiều lần xử lý độc lập, phải bổ sung **workflowAttempt** hoặc định danh decision phù hợp. Chỉ dùng **Spring Message ID** làm khóa chống trùng không đủ trong mọi trường hợp, vì broker redelivery hoặc việc tái tạo Message có thể sinh Message ID mới.

## 6. Audit thất bại: fail closed hay best effort?

Bản thân đường audit là một dependency có thể lỗi. Cần xác định trước mức độ bắt buộc đối với mỗi loại discard.

| Mức yêu cầu | Cách hành xử khi audit lỗi | Ví dụ |
| --- | --- | --- |
| **Bắt buộc (compliance / đối soát)** | Không xác nhận quyết định đã được ghi; trả lỗi kỹ thuật hoặc ghi outbox trong giao dịch | Lệnh hủy, yêu cầu tài chính quan trọng |
| **Durable eventual audit** | Ghi outbox/queue bền vững rồi ACK, publisher chuyển vào audit store sau | Lưu vết event nghiệp vụ cần chống mất |
| **Best effort** | Có thể ghi log/metric, không chặn đường chính khi mất telemetry | Lọc sự kiện kỹ thuật không ảnh hưởng nghiệp vụ |

Nếu yêu cầu có audit **bắt buộc**, đừng bắt exception rồi im lặng:

~~~java
// Phản ví dụ: báo REJECTED dù audit có thể chưa được ghi.
try {
    auditStore.appendOnce(event);
} catch (Exception ignored) {
    // Im lặng.
}
return new OrderDecision(commandId, "REJECTED", "INVALID_QUANTITY");
~~~

Phương án đáng tin cậy là thực hiện quyết định nghiệp vụ và **ghi audit/outbox trong một transaction phù hợp**. Nếu ghi ra hai hệ thống độc lập, không có atomic transaction xuyên hệ thống thì vẫn tồn tại cửa sổ crash; cần outbox, eventual delivery và idempotent consumer.

**Wire Tap** có thể gửi một bản sao của message sang kênh quan sát độc lập, rất hữu ích để chẩn đoán. Tuy nhiên không thể tự xem một wire tap bất đồng bộ là bằng chứng audit bền vững: còn phụ thuộc message delivery, consumer, queue, transaction và việc ghi storage có thành công hay không.

## 7. Đừng dùng error channel thay cho discard channel

Trong Spring Integration, một Filter reject bình thường không phải exception. Vì vậy việc tạo một global error channel chưa chắc thu được message bị Filter bỏ.

~~~mermaid
flowchart TD
    A[Message tới Filter] --> B{Predicate}
    B -->|True| C[Đường chính]
    B -->|False| D[Discard channel]
    E[Handler ném exception] --> F[Error path]
    F --> G[ErrorMessage nếu boundary hỗ trợ]
    D --> H[Discard audit]
    G --> I[Error audit / retry policy]
~~~

- **Discard audit** giải thích quyết định không tiếp tục xử lý: message bị loại ở bước nào, theo quy tắc nào.
- **Error handling** giải thích một xử lý thất bại ngoài dự kiến hoặc một exception được chủ động ném.
- **Dead-letter handling** giải thích một message không thể xử lý sau retry, hết thời hạn hoặc lỗi không thể phục hồi.

Với Gateway đồng bộ qua **DirectChannel**, exception có thể truyền về caller. Với endpoint bất đồng bộ/poller/adapter, exception có thể được đóng gói thành **ErrorMessage** theo cấu hình error channel. Không mặc định mọi exception hay discard đều đi qua cùng một error flow.

Nếu Filter được cấu hình **throwExceptionOnRejection(true)**, một reject trở thành exception; điều này có thể phù hợp với một số hợp đồng lỗi, nhưng **vẫn phải bảo đảm audit nếu bắt buộc**, không chỉ dựa vào log exception.

## 8. Router: không có route cũng phải có quyết định rõ

Giả sử Router nhận loại message **PAYMENT**, **STOCK** và **SHIPPING**. Khi xuất hiện event type chưa được hỗ trợ, một cấu hình permissive có thể bỏ hoặc chuyển về default output; một cấu hình nghiêm ngặt có thể ném exception. Cần quyết định dựa trên contract thay vì im lặng.

~~~mermaid
flowchart LR
    A[Router] -->|PAYMENT| B[Payment channel]
    A -->|STOCK| C[Stock channel]
    A -->|SHIPPING| D[Shipping channel]
    A -->|Unknown| E[Unroutable branch]
    E --> F[Audit: NO_MATCHING_ROUTE]
    F --> G[REJECTED / DLQ theo policy]
~~~

Đường **Unroutable** có thể xử lý:

- Event mới mà consumer chưa được nâng version.
- Key routing sai do Transformer hoặc mapping lỗi.
- Tenant/region không có cấu hình route.
- Message không đạt hợp đồng domain.

Đừng tự động gửi mọi Unknown vào một nhánh xử lý chính bất kỳ. Audit cần lưu **router name**, **route key đã chuẩn hóa**, **message correlation**, **reason code**, nhưng không nên ghi payload nhạy cảm toàn bộ.

Ngoài ra cần đo **unroutable_total** theo operation/flow; nếu chỉ ghi log mà không có cảnh báo khi rate tăng, lỗi cấu hình vẫn có thể kéo dài.

## 9. Aggregator: discard vì timeout, duplicate và late arrival

Aggregator thường gom message của cùng một **correlation group**. Chẳng hạn Splitter tách một đơn thành ba nhánh: **stock**, **pricing**, **shipping**. Aggregator chỉ hoàn tất khi nhận đủ ba kết quả hoặc completion strategy cho phép partial result.

Nếu nhánh stock không trả do circuit OPEN, nhóm có thể bị giữ đến deadline. Khi group hết hạn, những message đã có hoặc đến muộn phải được xử lý theo **expiry policy**.

| Trường hợp | Dấu vết audit nên có |
| --- | --- |
| Nhóm chưa đủ trước deadline | AGGREGATION_TIMEOUT, correlation/group key và các nhánh còn thiếu |
| Nhóm được release partial | PARTIAL_RELEASE, danh sách nhánh có/thiếu |
| Message trễ sau group expiry | LATE_ARRIVAL, thời điểm expiry và nhánh message |
| Duplicate branch reply | DUPLICATE_PART, event/branch key trùng |
| Group hoàn tất bình thường | COMPLETED (không phải discard), tổng số nhánh hợp lệ |

Trong Spring Integration, Aggregator có các khả năng cấu hình **group timeout, group expiry, discard channel** và xử lý message đến sau khi group đã hết hạn; hành vi chính xác phụ thuộc cấu hình và phiên bản. Không cho rằng đặt một group timeout tự động tạo hồ sơ audit cho mọi message bị loại.

### Correlation và sequence headers

Splitter thường thêm các header phục vụ correlation như **CORRELATION_ID**, **SEQUENCE_NUMBER**, **SEQUENCE_SIZE**. Nếu Transformer hoặc fallback tạo Message mới mà không giữ các header cần thiết, Aggregator có thể không gom đúng hoặc bị timeout.

Một audit event cho nhánh bị discard nên có **correlation/group key, step name, sequence number, source event ID** và outcome. Nếu luồng đa tenant, phải tránh ghép hai message cùng correlation string nhưng thuộc các tenant khác nhau.

**Không giữ Gateway đồng bộ chờ vô hạn** chỉ vì không thấy reply từ một nhánh. Cần partial/timeout/failure outcome và chính sách dọn group rõ ràng.

## 10. Retry, idempotency và audit không trùng

Các message có thể được phát lại bởi broker, retry advice hoặc caller. Một message bị Filter reject lần đầu có thể quay lại và bị reject thêm nhiều lần.

Có hai loại thông tin cần phân biệt:

- **Quyết định discard của một lệnh logic:** có thể muốn ghi **một audit decision** với auditEventKey ổn định.
- **Mỗi lần delivery/attempt:** có thể cần metrics/log riêng để điều tra việc broker redelivery hoặc retry loop.

Không ghi mỗi redelivery thành một quyết định nghiệp vụ mới nếu đó là cùng một lệnh. Nhưng cũng không che mất hành vi retry vô hạn: đo **delivery_attempts** hoặc log có sampling cho hoạt động thực tế.

### Ví dụ idempotency và outbox

~~~text
Trong cùng một transaction:

1. Kiểm tra message đã có decision theo logical key chưa.
2. Nếu chưa, ghi business outcome = REJECTED.
3. Ghi discard audit hoặc outbox event có unique eventId.
4. Commit.

Publisher:
5. Phát outbox event tới audit consumer.
6. Nếu broker ACK mất, có thể phát lại cùng eventId.
7. Audit consumer dùng eventId để append idempotent.
~~~

Đây là thiết kế khái niệm, không phải cú pháp SQL. **Unique constraint**/idempotent write ở storage mới bảo đảm một key không ghi nhiều quyết định. Một ConcurrentHashMap chỉ bảo đảm trong một JVM còn sống và không đủ cho multi-pod hoặc restart.

Đối với thao tác ghi có side effect, lệnh đã được xử lý trước khi reply bị mất cần được đối soát; không thể vì audit thấy message lại mà thực hiện nghiệp vụ thêm lần nữa.

## 11. Bảo mật dữ liệu trong audit

Audit không phải giấy phép sao chép toàn bộ message sang một kho log lâu dài. Đặc biệt trong đa tenant, message có thể mang tên khách hàng, địa chỉ, token, dữ liệu thanh toán hoặc thông tin riêng tư.

Những quy tắc thiết thực:

1. **Data minimization:** chỉ lưu trường cần giải thích quyết định, ví dụ reason code và tham chiếu nghiệp vụ đã được phép.
2. **Redaction:** không ghi secrets, access token, API key hay payload chứa thông tin nhạy cảm nếu không có chính sách đặc biệt.
3. **Access control:** nhân sự/ứng dụng chỉ được đọc audit của tenant và workflow họ có quyền.
4. **Retention:** có TTL, quy tắc lưu trữ và xóa theo nghĩa vụ pháp lý/nghiệp vụ.
5. **Integrity:** dùng storage chống sửa đổi không được phép, audit người truy cập và thay đổi khi cần.
6. **Cardinality:** không đưa order ID, tenant ID chi tiết, correlation ID, email vào mọi metric tag.
7. **Separation of duties:** event audit được chuẩn hóa độc lập với payload nghiệp vụ; không dựa vào một dòng console log làm bằng chứng tuân thủ.

Khi cần lưu dữ liệu liên quan đến an ninh hoặc giao dịch quan trọng, phối hợp với quy trình bảo mật/pháp chế thay vì tự định nghĩa retention tùy tiện.

## 12. Kiểm thử: Filter reject có audit và trả reply rõ ràng

Một test cho discard không chỉ assert rằng handler chính không được gọi. Cần xác minh **vì sao message bị loại**, **audit được ghi** và **caller không phải chờ timeout**.

Ví dụ JUnit 5 kết hợp Mockito ở một integration test đã khởi tạo **OrderGateway**, **OrderService** và **DiscardAuditStore**. Giả sử các dependency được inject bằng fake/mock, method appendOnce được verify qua mock:

~~~java
@Test
void invalidOrderIsAuditedAndReturnsRejected() {
    OrderCommand command =
            new OrderCommand("cmd-17", "tenant-a", -5);

    OrderDecision result = gateway.submit(command);

    assertEquals("REJECTED", result.outcome());
    assertEquals("INVALID_QUANTITY", result.reasonCode());
    assertEquals("cmd-17", result.commandId());

    verify(auditStore).appendOnce(argThat(event ->
            event.reasonCode().equals("INVALID_QUANTITY")
            && event.outcome().equals("REJECTED")
            && event.auditEventKey().contains("cmd-17")
    ));
    verifyNoInteractions(orderService);
}
~~~

Test trên cần test fixture cấu hình Gateway/IntegrationFlow và các mock bean; nó không phải một class JUnit độc lập có thể chạy ngoài context.

### Ma trận kiểm thử quan trọng

| Kịch bản | Kỳ vọng |
| --- | --- |
| Quantity hợp lệ | Chạy main handler, không ghi INVALID_QUANTITY audit |
| Quantity âm | Filter reject, ghi đúng một decision và trả REJECTED |
| Quantity bằng 0 | Kết quả theo hợp đồng validate, không silently drop |
| Event type không có route | Có NO_MATCHING_ROUTE outcome/audit |
| Audit store tạm không khả dụng | Không báo audit đã ghi nếu write chưa thành công |
| Message bị broker redeliver | Không tạo nhiều decision trùng theo auditEventKey |
| Duplicate cùng command ID nhưng khác attempt thật | Khóa audit phân biệt đúng workflowAttempt |
| Router/Filter lỗi do bug | Error path, không giả thành rejected business event |
| Aggregator thiếu nhánh | Timeout/partial outcome và audit group/branch |
| Late arrival sau Aggregator expiry | Không hồi sinh group sai; có dấu vết late event |
| Splitter tạo nhiều nhánh | Giữ correlation, sequence metadata trên outcome/discard |
| Gateway đồng bộ nhận discard | Có reply hoặc exception rõ, không treo vô hạn |
| Flow bất đồng bộ | ErrorMessage và discard path được phân loại khác nhau |
| Nhiều pod ghi cùng decision | Unique constraint/idempotent write không tạo duplicate |
| Audit chứa payload nhạy cảm | Không log raw secret/PII ngoài chính sách |

### Test lỗi audit

Có thể cấu hình fake auditStore ném exception khi appendOnce và kiểm tra Gateway nhận lỗi kỹ thuật hoặc durable fallback theo policy. Không nên viết test chỉ xác minh REJECTED reply được gửi ngay cả khi audit bắt buộc đã thất bại; điều đó khuyến khích mất audit.

### Test quan sát bằng counter

Một metric **discard_total{flow,reason}** tăng khi message bị loại. Metric có thể ghi nhận mọi delivery, còn **audit decision store** có thể chỉ có một bản ghi trên logical key. Test nên phân biệt hai đơn vị này để không cho rằng metric count phải luôn bằng số dòng audit.

## 13. Giám sát các discard trong production

| Tín hiệu | Mục đích |
| --- | --- |
| **discard_total** theo flow và reason | Phát hiện loại bỏ tăng bất thường |
| **discard_to_input_ratio** | Tỷ lệ loại bỏ trong số message nhận |
| **audit_write_success/failure** | Biết hệ thống audit còn hoạt động không |
| **audit_queue_depth / oldest_age** | Phát hiện backlog nếu dùng outbox |
| **unknown_route_total** | Nhận diện version mismatch hoặc router thiếu mapping |
| **aggregation_expired_total** | Nhóm thiếu reply hoặc timeout |
| **duplicate_discard_total** | Phát hiện retry/redelivery quá nhiều |
| **Gateway rejected/timeout rate** | Caller có nhận kết quả rõ hay chỉ timeout? |
| **ErrorMessage rate** | Phân biệt exception kỹ thuật với business discard |
| **correlation/trace ID trong log** | Lần theo một message qua các EIP |

Cảnh báo cần dựa trên baseline của flow. Ví dụ tỷ lệ **INVALID_QUANTITY** tăng đột biến có thể do một client mới gửi sai payload; **NO_MATCHING_ROUTE** tăng sau deploy có thể báo mismatch version; **audit_write_failure** trên đường bắt buộc có thể cần cảnh báo nhanh vì ảnh hưởng khả năng đối soát.

Với metrics, dùng nhãn **flow**, **stage**, **reasonCode**, **outcome**, **tenant_group** có cardinality kiểm soát. Không dùng mỗi orderId hoặc correlationId làm tag, vì sẽ tạo hàng triệu time series. ID chi tiết phù hợp hơn trong log/trace có phân quyền.

### Không nhầm mức độ thành công

Một hệ thống có thể trả HTTP 200 khi bỏ qua event không cần xử lý; điều này **không phải** lỗi nếu phù hợp contract. Ngược lại, một Gateway trả timeout vì Filter silently discard là triệu chứng workflow chưa có phản hồi phù hợp, dù không có exception nào ở handler.

Chất lượng audit được đo bằng **khả năng giải thích** và **đối soát**: message đã được nhận ở đâu, quyết định gì, vì sao, đã trả outcome nào và có thể truy vết qua các thành phần hay không.

## 14. Những sai lầm cần tránh

1. **Filter trả false và không có discard channel:** message bị loại nhưng caller không biết lý do.
2. **Chỉ bật error channel và nghĩ sẽ bắt mọi discard:** một reject bình thường không phải exception.
3. **Gửi message tới discard channel nhưng không có handler:** chuyển vị trí mất message chứ chưa tạo audit.
4. **Ghi audit bằng log payload nguyên văn:** lộ dữ liệu và không bảo đảm bền vững.
5. **Ghi audit sau khi trả ACK thành công:** crash có thể làm mất sự kiện audit.
6. **Không có audit key ổn định:** redelivery tạo nhiều bản ghi quyết định nghiệp vụ.
7. **Audit key chỉ là messageId mới của mỗi delivery:** không chống trùng lệnh logic.
8. **Dùng cùng một reasonCode cho mọi validation:** không biết thực sự quy tắc nào bị vi phạm.
9. **Nhầm duplicate discard với lỗi upstream:** kích hoạt Retry hoặc Circuit Breaker không cần thiết.
10. **Không xử lý Aggregator group timeout:** nhóm hết hạn mà không có outcome hay lịch sử.
11. **Không giữ correlation khi Transformer tạo message mới:** khó lần theo nhánh bị loại.
12. **Dùng wire tap best-effort để đáp ứng audit bắt buộc:** mất event vẫn có thể xảy ra.
13. **Cho audit failure bị catch và bỏ qua:** caller tưởng hệ thống đã ghi dấu vết.
14. **Giữ audit vô hạn:** rủi ro lưu trữ, bảo mật và vi phạm chính sách retention.

## 15. Checklist triển khai

- [ ] Liệt kê các điểm có thể discard: Filter, Router, Aggregator expiry, duplicate handling và channel không có consumer.
- [ ] Mỗi discard có **reasonCode, flow/stage, correlation** và outcome rõ ràng khi nghiệp vụ yêu cầu.
- [ ] Phân biệt discard bình thường, lỗi kỹ thuật, dead-letter và fallback.
- [ ] Với Filter, cấu hình **discardChannel** hoặc exception policy; không để Gateway chờ reply mơ hồ.
- [ ] Trả rejected result hoặc error có hợp đồng; không coi mọi discard là success.
- [ ] Ghi audit tối thiểu, không lưu raw secrets/PII không cần thiết.
- [ ] Nếu audit bắt buộc, dùng storage bền vững hoặc outbox giao dịch, không catch lỗi rồi im lặng.
- [ ] Dùng auditEventKey ổn định và idempotent write để chống redelivery.
- [ ] Có retention, phân quyền và khả năng tra cứu theo correlation ID.
- [ ] Với Splitter/Aggregator, giữ sequence headers và audit timeout/late-arrival.
- [ ] Test main path, discard path, audit failure, duplicate và request–reply của Gateway.
- [ ] Theo dõi discard rate, audit write failures, unknown routes và expired groups.
- [ ] Không để một message quan trọng bị loại mà không thể giải thích và đối soát.

**Discard message mà không có audit** là lỗi thiết kế khiến hệ thống có thể “chạy thành công” về kỹ thuật nhưng mất khả năng chứng minh điều gì đã xảy ra với message. Trong Spring Integration, cần biến một nhánh loại bỏ thành **quyết định có lý do, có correlation, có outcome và mức audit phù hợp**. Khi kết hợp Filter/Router/Aggregator với discard channel, storage bền vững, idempotency, error handling và quan sát theo EIP, ta có thể loại message đúng nghiệp vụ mà vẫn truy vết, kiểm thử và đối soát được.
