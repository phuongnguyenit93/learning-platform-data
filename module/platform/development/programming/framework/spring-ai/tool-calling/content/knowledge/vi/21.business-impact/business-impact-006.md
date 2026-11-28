# Retry sau timeout khi chưa biết hành động đã hoàn tất hay chưa

Khi tool gọi một dịch vụ bên ngoài để hoàn tiền, đặt hàng hoặc gửi thông báo, timeout không chứng minh rằng hành động thất bại. Request có thể đã đến server, nghiệp vụ đã commit, nhưng response bị mất trên đường về. Nếu ứng dụng hoặc mô hình gọi lại như thể chưa có gì xảy ra, cùng một hành động có thể được thực hiện hai lần.

Trong tình huống này, kết quả đúng không phải lúc nào cũng là thành công hoặc thất bại. Ứng dụng cần trạng thái thứ ba: **UNKNOWN — chưa xác định được kết quả**. Chỉ retry tự động khi biết request chưa được áp dụng hoặc khi hệ thống đích có hợp đồng idempotency bảo đảm lần gửi lại cùng một operation không tạo thêm tác động.

Với Spring AI, điều này đặc biệt quan trọng vì lỗi tool có thể được gửi lại cho mô hình như một tool result. Nếu callback ném một RuntimeException chứa thông báo timeout, mô hình có thể hiểu nhầm rằng hành động chưa chạy và đề xuất gọi lại. Hãy trả trạng thái nghiệp vụ rõ ràng và để ứng dụng kiểm soát việc retry.

## 1. Timeout không đồng nghĩa với thất bại

Giả sử assistant gọi tool request_refund:

1. Ứng dụng gửi yêu cầu hoàn tiền tới payment provider.
2. Provider ghi nhận giao dịch và thực hiện hoàn tiền.
3. Provider gửi response thành công.
4. Kết nối bị ngắt trước khi ứng dụng nhận response.
5. Tool callback thấy read timeout và báo lỗi.

Ứng dụng biết mình không nhận được response; nó không biết provider đã hoàn tiền hay chưa. Gửi một yêu cầu hoàn tiền mới có thể tạo giao dịch thứ hai.

~~~mermaid
sequenceDiagram
    participant Model as Mô hình
    participant App as Ứng dụng / ToolCallback
    participant Ledger as Operation ledger
    participant Pay as Payment provider

    Model->>App: request_refund(orderId, amount)
    App->>Ledger: Tạo operationId, trạng thái IN_PROGRESS
    App->>Pay: refund(idempotencyKey=operationId)
    Pay->>Pay: Ghi nhận hoàn tiền
    Pay--xApp: Response bị mất / timeout
    App->>Ledger: Đánh dấu UNKNOWN
    App-->>Model: Tool result: UNKNOWN + operationId
    Model->>App: get_refund_status(operationId)
    App->>Ledger: Đọc trạng thái / đối soát provider
    App->>Pay: Tra cứu theo provider reference hoặc idempotency key
    Pay-->>App: Trạng thái giao dịch
    App->>Ledger: Cập nhật SUCCEEDED hoặc FAILED_FINAL
    App-->>Model: Kết quả đã được xác minh
~~~

Không thể suy ra trạng thái bên ngoài chỉ từ exception của HTTP client. Timeout, connection reset, gateway 504 hoặc client cancellation có thể xảy ra sau khi downstream đã nhận và xử lý request.

## 2. Phân loại kết quả trước khi quyết định retry

Hãy phân biệt các kết quả sau:

| Kết quả | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| SUCCEEDED | Có bằng chứng hành động đã hoàn tất | Trả kết quả đã lưu; không chạy lại |
| FAILED_FINAL | Có bằng chứng nghiệp vụ từ chối hoặc không thể thực hiện | Báo lỗi cuối; không retry |
| NOT_SENT | Có bằng chứng request chưa được gửi tới hệ thống đích | Có thể thử lại theo retry policy |
| REJECTED | Hệ thống đích xác nhận không chấp nhận request | Xử lý theo mã lỗi; thường không retry lỗi nghiệp vụ |
| UNKNOWN | Request có thể đã được xử lý nhưng ứng dụng chưa xác minh được | Tra cứu trạng thái hoặc đối soát; không gửi operation mới |
| IN_PROGRESS | Hệ thống đang xử lý hoặc ứng dụng đã bắt đầu attempt | Chờ, poll hoặc trả trạng thái đang xử lý |

Không biến UNKNOWN thành FAILED_FINAL chỉ để đơn giản hóa UI. Nếu không biết hành động đã xảy ra chưa, câu trả lời phải giữ đúng sự không chắc chắn đó.

### Ví dụ những tình huống khác nhau

- Validation thất bại trước khi gọi provider: chắc chắn chưa gửi request; sửa input rồi mới tạo operation mới.
- Provider trả 400 vì số tiền không hợp lệ: request bị từ chối; sửa dữ liệu hoặc báo lỗi, không retry nguyên trạng.
- Provider trả 429 và tài liệu API xác nhận request chưa được xử lý: có thể retry sau thời gian chờ theo hướng dẫn của provider.
- Read timeout sau khi gửi request: kết quả có thể là UNKNOWN.
- Provider trả 200, nhưng ứng dụng chết trước khi ghi kết quả vào database: lần chạy sau cần tra cứu hoặc gửi lại cùng idempotency key.

Phân loại phải dựa trên hợp đồng của client và hệ thống đích. Không phải mọi 5xx đều có cùng ngữ nghĩa; một số gateway có thể trả lỗi sau khi downstream đã commit.

## 3. Vì sao retry mù gây tác động nghiệp vụ?

Giả sử người dùng yêu cầu hoàn tiền 500.000 đồng. Provider đã hoàn tiền nhưng response bị mất. Mô hình nhận thông báo “timeout” rồi gọi lại tool:

| Lần gọi | Điều ứng dụng nhìn thấy | Điều provider có thể đã làm |
| --- | --- | --- |
| Lần 1 | Timeout | Đã hoàn tiền 500.000 đồng |
| Lần 2 | Thành công | Có thể hoàn thêm 500.000 đồng |

Hậu quả có thể là:

- Hoàn tiền hai lần hoặc tạo hai đơn hàng.
- Gửi email/SMS lặp lại.
- Trừ tồn kho nhiều lần.
- Tạo hai lịch hẹn hoặc hai yêu cầu hỗ trợ.
- Ghi nhận hai giao dịch trong hệ thống kế toán.

Mô hình có thể gọi lại cùng tool với tool-call ID khác, arguments được định dạng khác hoặc một request chat mới. Tool-call ID là định danh của lời gọi do model/provider tạo; nó không tự bảo đảm hai lời gọi biểu diễn cùng một ý định nghiệp vụ.

## 4. Phân biệt các loại ID

Đừng dùng chung một ID cho request HTTP, tool call và operation nghiệp vụ:

| ID | Ai tạo | Phạm vi | Dùng để làm gì |
| --- | --- | --- | --- |
| requestId | Ứng dụng | Một request tới API/chat | Correlation log và trace |
| toolCallId | Model/provider | Một tool call trong response | Ghép tool call với tool result trong conversation |
| operationId | Ứng dụng | Một ý định nghiệp vụ cụ thể | Nhận diện hành động qua nhiều attempt/retry |
| attemptId | Ứng dụng | Một lần gửi vật lý | Theo dõi timeout, latency và số lần thử |
| idempotencyKey | Ứng dụng | Hệ thống đích hỗ trợ dedup | Yêu cầu downstream nhận diện cùng một operation |

Thông thường operationId có thể được dùng làm idempotencyKey, nhưng hai khái niệm vẫn có vai trò khác nhau: một cái là định danh nghiệp vụ trong hệ thống của bạn, cái còn lại là token theo hợp đồng API của provider.

operationId phải được tạo khi ứng dụng chấp nhận một hành động nghiệp vụ cụ thể, lưu bền vững và giữ nguyên qua mọi lần retry hoặc resume. Không tạo ID mới trong mỗi lần callback chạy. Không dùng timestamp, UUID do mô hình tự điền hoặc toolCallId làm khóa idempotency duy nhất.

Nếu người dùng chủ động yêu cầu một hành động mới, ứng dụng tạo operation mới. Nếu chỉ đang khôi phục cùng hành động sau timeout, ứng dụng phải lấy lại operation cũ.

## 5. Hợp đồng idempotency

Một API hỗ trợ idempotency nên có hành vi:

- Lần đầu nhận key mới và payload hợp lệ: xử lý operation, lưu kết quả gắn với key.
- Nhận lại cùng key và cùng payload: trả lại kết quả đã lưu hoặc trạng thái hiện tại mà không tạo tác động phụ lần nữa.
- Nhận cùng key nhưng payload khác: từ chối vì xung đột, không ghi đè request ban đầu.
- Nhận key khác: xem là operation khác theo hợp đồng của API.

Ví dụ:

~~~text
POST /refunds
Idempotency-Key: op-refund-7f31

{
  "orderId": "ORD-100",
  "amount": 500000,
  "currency": "VND"
}
~~~

Nếu response bị timeout, lần gửi lại phải dùng cùng key op-refund-7f31 và cùng payload đã chuẩn hóa. Không tạo op-refund-8a92 chỉ vì request trước chưa trả response.

Idempotency cần được thực hiện ở phía nhận request. Chỉ lưu key ở ứng dụng nhưng downstream không kiểm tra key thì chưa bảo vệ được side effect ở downstream.

### Kiểm tra payload cùng key

Lưu fingerprint của payload đã chuẩn hóa cùng key:

~~~java
String requestHash = requestHasher.sha256(
    tenantId,
    orderId,
    amount,
    currency
);

OperationRecord operation =
    operationStore.getOrCreate(operationId, requestHash);

if (!operation.requestHash().equals(requestHash)) {
    throw new IdempotencyConflictException(operationId);
}
~~~

Đoạn mã minh họa hợp đồng; getOrCreate cần được bảo vệ bằng unique constraint hoặc transaction để hai request đồng thời không tạo hai operation cho cùng key. Không lưu toàn bộ dữ liệu nhạy cảm vào key; key nên là định danh opaque, còn fingerprint chỉ gồm các trường cần xác minh.

## 6. Lưu operation ledger bền vững

Với thao tác có tác động phụ, hãy lưu một bản ghi operation trước khi gọi hệ thống đích:

| Trường | Mục đích |
| --- | --- |
| operation_id | Khóa duy nhất của ý định nghiệp vụ |
| tenant_id, actor_id | Phạm vi và người khởi tạo đã xác thực |
| operation_type | Ví dụ REFUND hoặc CREATE_BOOKING |
| request_hash | Phát hiện cùng key nhưng payload khác |
| status | IN_PROGRESS, SUCCEEDED, FAILED_FINAL, UNKNOWN |
| provider_reference | Mã giao dịch phía hệ thống đích nếu có |
| result_payload | Kết quả đã chuẩn hóa, có thể trả lại cho retry |
| attempt_count | Số lần gửi thực tế |
| created_at, updated_at | Theo dõi thời gian và đối soát |

State machine cơ bản:

~~~mermaid
stateDiagram-v2
    [*] --> IN_PROGRESS: Tạo operation
    IN_PROGRESS --> SUCCEEDED: Có xác nhận thành công
    IN_PROGRESS --> FAILED_FINAL: Có xác nhận thất bại cuối
    IN_PROGRESS --> UNKNOWN: Mất response / timeout không rõ kết quả
    UNKNOWN --> RECONCILING: Bắt đầu đối soát
    RECONCILING --> SUCCEEDED: Provider xác nhận đã xử lý
    RECONCILING --> FAILED_FINAL: Provider xác nhận không xử lý
    RECONCILING --> UNKNOWN: Chưa đủ dữ liệu
~~~

Không tự chuyển UNKNOWN về IN_PROGRESS rồi gửi một request mới với key khác. Nếu provider hỗ trợ idempotency, có thể gửi lại cùng operation/key theo hợp đồng của provider. Nếu không hỗ trợ, ưu tiên tra cứu bằng provider reference hoặc merchant reference.

### Ràng buộc lưu trữ

- Đặt unique constraint trên operation_id.
- Lưu request_hash và từ chối payload khác với key đã dùng.
- Cập nhật trạng thái có điều kiện để hai worker không cùng claim một operation.
- Lưu provider reference và kết quả đủ để trả lại response sau restart.
- Giữ ledger lâu hơn khoảng thời gian mà client, gateway hoặc worker có thể retry.
- Không xóa key ngay khi thành công; nếu xóa quá sớm, retry muộn có thể tạo side effect mới.

## 7. Thực thi tool theo operationId

Tạo operation ở tầng ứng dụng và truyền ID qua ToolContext. Context này không được gửi cho mô hình; model chỉ cung cấp arguments nghiệp vụ như mã đơn hàng và số tiền.

~~~java
Map<String, Object> toolContext = Map.of(
    "tenantId", authenticatedTenant.id(),
    "actorId", authenticatedPrincipal.id(),
    "operationId", operation.id()
);

String answer = chatClient.prompt()
    .user("Yêu cầu hoàn tiền cho đơn ORD-100.")
    .tools(refundTools)
    .toolContext(toolContext)
    .call()
    .content();
~~~

Ứng dụng phải tạo và lưu operation.id() trước khi chạy tool. Khi khôi phục cùng hành động sau timeout hoặc confirmation pause, tải lại operation ID đã lưu. Không tạo một operation mới chỉ vì một request chat mới được gửi.

Tool callback:

~~~java
@Tool(description = "Yêu cầu hoàn tiền cho đơn hàng.")
public RefundOutcome requestRefund(
        @ToolParam(description = "Mã đơn hàng") String orderId,
        @ToolParam(description = "Số tiền cần hoàn") BigDecimal amount,
        ToolContext context) {

    String tenantId = (String) context.getContext().get("tenantId");
    String operationId = (String) context.getContext().get("operationId");

    return refundService.executeOnce(
        tenantId, orderId, amount, operationId);
}
~~~

Service kiểm tra operation ledger trước khi gửi provider:

~~~java
public RefundOutcome executeOnce(
        String tenantId,
        String orderId,
        BigDecimal amount,
        String operationId) {

    OperationClaim claim =
        operationStore.claimOrGet(operationId, tenantId, orderId, amount);
    OperationRecord operation = claim.operation();

    if (operation.isSucceeded()) {
        return operation.savedRefundOutcome();
    }
    if (operation.isInProgress() && !claim.claimedByThisAttempt()) {
        return RefundOutcome.pending(operationId, operation.status());
    }
    if (operation.isUnknown()) {
        return RefundOutcome.unknown(operationId);
    }
    if (operation.isFailedFinal()) {
        return RefundOutcome.failed(operationId);
    }

    try {
        // operationId được gửi như idempotency key của provider.
        ProviderRefund response = paymentProvider.refund(
            orderId, amount, operationId);
        operationStore.markSucceeded(operationId, response.reference(), response);
        return RefundOutcome.succeeded(operationId, response.reference());
    }
    catch (SocketTimeoutException ex) {
        // Đây là read timeout sau khi request đã gửi; connect timeout
        // được adapter phân loại NOT_SENT nếu biết chắc chưa gửi request.
        operationStore.markUnknown(operationId);
        return RefundOutcome.unknown(operationId);
    }
}
~~~

Đây là pseudocode tập trung vào luồng trạng thái. OperationClaim cho biết attempt hiện tại có giành được quyền thực thi hay chỉ đọc một operation đang chạy bởi worker khác. claimOrGet atomically tạo/claim operation và lưu trạng thái IN_PROGRESS trước khi trả về; chỉ attempt đã claim mới gọi provider. Trong triển khai thật, claimOrGet phải xử lý cạnh tranh bằng transaction/unique constraint; lời gọi mạng nên nằm ngoài transaction database dài; cập nhật trạng thái cần compare-and-set hoặc version để không ghi đè kết quả mới hơn. Nếu provider có idempotency, truyền operation ID làm key theo đúng hợp đồng của provider.

## 8. Trả trạng thái UNKNOWN cho mô hình

Đừng trả một thông báo chung như “Refund failed” khi thực tế chỉ có timeout. Hãy trả một kết quả có cấu trúc:

~~~java
public record RefundOutcome(
    String operationId,
    String status,
    String message,
    String providerReference
) {
    static RefundOutcome unknown(String operationId) {
        return new RefundOutcome(
            operationId,
            "UNKNOWN",
            "Chưa xác minh được kết quả. Hãy kiểm tra trạng thái operation trước khi yêu cầu hành động mới.",
            null
        );
    }
}
~~~

Mô hình có thể giải thích rằng kết quả đang được xác minh. Nhưng prompt hướng dẫn chưa đủ để ngăn model gọi lại tool ghi. Ứng dụng cần thực thi trạng thái operation:

- Khi operation là UNKNOWN hoặc IN_PROGRESS, chỉ cung cấp tool đọc trạng thái.
- Tool ghi kiểm tra operation ledger và từ chối tạo operation khác cho cùng ý định đang mở.
- Nếu model yêu cầu lại hành động, callback trả trạng thái hiện tại của operation cũ.
- Chỉ cho phép một operation mới khi người dùng thực sự tạo một ý định mới và ứng dụng đã tạo operation ID mới.

Tạo tool tra cứu trạng thái chỉ đọc:

~~~java
@Tool(description = "Tra cứu trạng thái một yêu cầu hoàn tiền đã được tạo.")
public RefundOutcome getRefundStatus(
        @ToolParam(description = "Mã operation do ứng dụng cấp") String operationId) {
    return refundService.getStatusForCurrentPrincipal(operationId);
}
~~~

Tool status phải xác minh operation thuộc đúng tenant và principal được phép xem. Không cho model truy vấn operation ID của người dùng khác.

## 9. Khi nào được retry?

Retry là cơ chế phục hồi lỗi tạm thời, không phải phản ứng mặc định với mọi exception.

| Tình huống | Retry? | Điều kiện |
| --- | --- | --- |
| DNS/connect failure trước khi request được gửi | Có thể | Có bằng chứng chưa gửi; vẫn tuân thủ deadline |
| HTTP 429 | Có thể | Theo Retry-After hoặc hợp đồng provider; dùng cùng operation key |
| HTTP 503 | Có thể | Chỉ khi provider xác định request chưa được áp dụng hoặc API idempotent |
| Read timeout sau khi gửi request | Không retry mù | Tra cứu trạng thái hoặc retry cùng idempotency key |
| Connection reset sau khi gửi body | Không retry mù | Kết quả có thể đã được commit |
| Validation/authorization error | Không | Sửa input hoặc quyền trước khi tạo operation mới |
| Provider xác nhận từ chối cuối | Không | Trả kết quả từ chối |
| Operation UNKNOWN | Chưa gửi operation mới | Đối soát trước; retry cùng key nếu downstream bảo đảm dedup |

### Retry có giới hạn

Với thao tác idempotent và lỗi transient, đặt:

- Số lần thử tối đa.
- Exponential backoff để tăng khoảng nghỉ giữa các lần thử.
- Jitter để nhiều client không retry cùng thời điểm.
- Deadline tổng của operation.
- Retry budget theo service hoặc tenant.
- Circuit breaker để ngừng gọi downstream đang lỗi kéo dài.

Một công thức minh họa:

~~~text
delay(attempt) = random(0, min(maxDelay, baseDelay * 2^attempt))
~~~

Không retry lỗi nghiệp vụ, lỗi xác thực, thiếu quyền hoặc payload không hợp lệ. Tôn trọng Retry-After khi provider gửi. Chỉ một tầng nên sở hữu retry policy cho một lời gọi; nếu gateway, service, tool callback và agent đều tự retry, số lần thực thi có thể nhân lên.

Resilience4j Retry hỗ trợ maxAttempts, waitDuration và hàm tính khoảng nghỉ. Cấu hình retry chỉ quyết định khi nào thử lại; nó không tự làm cho thao tác có side effect trở thành idempotent.

## 10. Spring AI xử lý exception tool như thế nào?

Spring AI chuyển exception từ tool thành ToolExecutionException rồi giao cho ToolExecutionExceptionProcessor.

DefaultToolExecutionExceptionProcessor mặc định:

- Gửi message của RuntimeException về mô hình như tool result để mô hình có thể phản hồi.
- Ném lại checked exception và Error.

Property spring.ai.tools.throw-exception-on-error mặc định là false. Đặt true để ném lỗi tool cho caller xử lý:

~~~properties
spring.ai.tools.throw-exception-on-error=true
~~~

Nếu tool ném RuntimeException chỉ với nội dung “timeout”, mô hình có thể xem đó là thất bại và gọi lại. Với kết quả không chắc chắn, ưu tiên trả một kết quả nghiệp vụ có status UNKNOWN và operation ID. Nếu cần exception đi tới ứng dụng, dùng processor phù hợp để log/handle ở caller và không làm lộ exception message nội bộ cho mô hình.

Nếu tự triển khai ToolCallback, hãy ném ToolExecutionException khi callback thực sự thất bại theo contract của Spring AI. Không chuyển một timeout chưa rõ kết quả thành lỗi nghiệp vụ cuối cùng.

## 11. Nếu hệ thống đích không hỗ trợ idempotency

Không phải API nào cũng nhận idempotency key. Khi đó ứng dụng không thể tự tạo bảo đảm dedup ở phía provider chỉ bằng cách lưu một key nội bộ.

Các lựa chọn:

1. Dùng merchant reference hoặc external reference duy nhất nếu provider cho phép gửi và tra cứu.
2. Sau timeout, gọi API status/query để tìm giao dịch theo reference trước khi gửi lại.
3. Đối chiếu webhook/event từ provider với operation ledger.
4. Nếu không có cách xác minh, giữ trạng thái UNKNOWN, dừng retry tự động và chuyển sang quy trình reconciliation hoặc người vận hành.

Không suy luận rằng provider không có giao dịch chỉ vì truy vấn trạng thái chưa thấy ngay; dữ liệu có thể eventual-consistent. Cần backoff cho các lần query status và một ngưỡng thời gian trước khi chuyển sang manual review.

## 12. Nhiều bước nghiệp vụ và compensation

Một workflow có thể gồm nhiều side effect:

1. Tạo đơn hàng.
2. Thu tiền.
3. Đặt lịch giao hàng.
4. Gửi email xác nhận.

Nếu bước 3 timeout, không chạy lại toàn bộ workflow từ bước 1. Mỗi bước cần operation ID riêng, trạng thái riêng và idempotency riêng. Workflow orchestration phải biết bước nào đã hoàn tất, bước nào đang chạy và bước nào chưa xác định.

Với quy trình dài, có thể dùng Saga:

- Mỗi bước ghi nhận kết quả thành công.
- Nếu bước sau thất bại cuối cùng, workflow có thể chạy compensation đã định nghĩa.
- Compensation là một hành động nghiệp vụ mới, cũng cần idempotency và kiểm tra trạng thái.
- Nếu một bước đang UNKNOWN, hãy đối soát trước khi quyết định chạy bước tiếp theo hoặc compensation.

Transactional outbox giúp ghi thay đổi database và event cần publish trong cùng transaction cục bộ. Consumer vẫn phải deduplicate event bằng event ID vì message broker có thể giao lại. Outbox không làm một external API call trở thành atomic với database; vẫn cần operation ledger và idempotency ở ranh giới dịch vụ.

## 13. Kiểm thử timeout và retry

Không chỉ mock exception timeout. Cần mô phỏng trường hợp downstream đã commit nhưng response bị mất:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Timeout trước khi gửi request | Có thể retry theo policy |
| Provider commit rồi đóng kết nối | Operation thành UNKNOWN; không tạo operation mới |
| Retry cùng key, cùng payload | Provider hoặc service trả kết quả cũ, không lặp side effect |
| Cùng key nhưng payload khác | Từ chối bằng idempotency conflict |
| Hai callback đồng thời cùng operation ID | Chỉ một attempt được claim; không thực thi trùng |
| Process restart sau provider success | Reconcile tìm lại provider reference và cập nhật SUCCEEDED |
| Provider không hỗ trợ idempotency | Timeout dẫn tới status query hoặc manual reconciliation |
| Model yêu cầu lại tool sau UNKNOWN | Tool chỉ trả trạng thái operation cũ hoặc bị chặn |
| Operation đã SUCCEEDED | Retry trả kết quả đã lưu, không gọi provider |
| Validation hoặc authorization thất bại | Không retry |
| Retry budget hết | Dừng retry và giữ trạng thái có thể điều tra |
| Nhiều tầng cùng retry | Kiểm tra tổng số attempt không vượt budget |

Với Spring AI, mock ChatModel để yêu cầu tool call, dùng fake payment provider để điều khiển thời điểm commit và timeout, rồi kiểm tra số lần provider thực sự thực hiện side effect. Kiểm tra cả tool result mà mô hình nhận được và trạng thái trong operation ledger.

## 14. Lỗi thiết kế thường gặp

| Biểu hiện | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Hoàn tiền hai lần | Tạo idempotency key mới sau timeout | Tái sử dụng operation ID của cùng ý định |
| Model gọi lại tool liên tục | Trả timeout như lỗi thất bại thông thường | Trả UNKNOWN, cung cấp status tool và chặn action mới |
| Không biết giao dịch nào thuộc request nào | Chỉ log requestId hoặc toolCallId | Lưu operationId và provider reference |
| Cùng key nhưng payload thay đổi | Không lưu request fingerprint | Từ chối idempotency conflict |
| Retry vô hạn | Không có max attempts hoặc deadline | Bounded retry, backoff và retry budget |
| Provider đã thành công nhưng DB vẫn IN_PROGRESS | Process chết trước khi lưu kết quả | Reconciliation job tra cứu provider |
| Dùng transaction DB bao quanh HTTP call dài | Giữ lock trong lúc chờ network | Ghi operation state trước, gọi provider ngoài transaction, cập nhật state sau |
| Retry toàn bộ ChatClient turn | Lặp lại cả những tool đã thành công | Resume từ operation state và chỉ chạy bước còn thiếu |
| Dùng compensation khi outcome còn UNKNOWN | Chưa biết side effect gốc có xảy ra không | Đối soát trước khi compensation |

## Bài thực hành

Một assistant hỗ trợ đơn hàng có tool request_refund gọi payment provider. Người dùng yêu cầu hoàn 500.000 đồng cho đơn ORD-100. Provider đã thực hiện hoàn tiền nhưng response bị mất, khiến callback timeout.

Hãy thiết kế:

1. Server tạo và lưu operationId trước khi tool chạy.
2. ToolContext truyền tenantId và operationId tới callback.
3. Operation ledger có unique key, request hash và trạng thái IN_PROGRESS, SUCCEEDED, FAILED_FINAL, UNKNOWN.
4. Payment provider nhận cùng idempotency key trong mọi attempt của cùng operation.
5. Khi timeout, tool trả UNKNOWN thay vì báo hoàn tiền thất bại.
6. Assistant dùng tool get_refund_status để tra cứu trước khi yêu cầu hành động mới.
7. Nếu provider không hỗ trợ idempotency/status lookup, thiết kế quy trình manual reconciliation.
8. Viết test cho provider commit rồi mất response, retry đồng thời, key/payload mismatch, process restart và retry budget hết.

Sau khi hoàn thành, hãy giải thích vì sao timeout không chứng minh operation thất bại, vì sao toolCallId không thay thế operationId và khi nào có thể retry cùng idempotency key.

## Ghi nhớ

Timeout chỉ cho biết ứng dụng chưa nhận được response; nó không chứng minh side effect chưa xảy ra. Hãy phân biệt FAILED_FINAL với UNKNOWN, tạo operation ID ở server và giữ nguyên idempotency key qua mọi attempt của cùng một ý định. Lưu trạng thái operation bền vững, tra cứu hoặc đối soát khi kết quả chưa rõ, và chỉ retry tự động khi request chắc chắn chưa được áp dụng hoặc downstream có hợp đồng idempotency. Với Spring AI, đừng để một RuntimeException timeout mơ hồ trở thành chỉ dẫn cho mô hình gọi lại hành động; trả trạng thái nghiệp vụ rõ ràng và để ứng dụng kiểm soát bước tiếp theo.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling / Exception Handling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [AWS Builders' Library — Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
- [AWS Well-Architected — Make mutating operations idempotent](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel04-bp04.html)
- [Amazon EC2 — Ensuring idempotency in API requests](https://docs.aws.amazon.com/ec2/latest/devguide/ec2-api-idempotency.html)
- [AWS Prescriptive Guidance — Retry with backoff](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html)
- [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry)
