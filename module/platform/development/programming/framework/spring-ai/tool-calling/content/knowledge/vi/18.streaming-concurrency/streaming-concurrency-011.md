# Hủy luồng và xử lý công việc đã bắt đầu hoặc đã tạo tác động

Khi người dùng đóng tab, ngắt kết nối SSE hoặc bấm nút Hủy, ứng dụng có thể nhận tín hiệu cancellation từ Reactor. Tín hiệu này dừng việc phát dữ liệu cho subscriber và được truyền ngược lên publisher theo quy tắc Reactive Streams. Tuy nhiên, một tool callback có thể đã bắt đầu chạy, một giao dịch có thể đã commit hoặc một hệ thống bên ngoài đã nhận lệnh thanh toán/gửi email. Hủy luồng không tự động đảo ngược những tác động đó.

Với Spring AI, một request streaming có thể đi qua nhiều vòng: model phát tool call, ứng dụng thực thi callback, tool result được gửi lại model và model tiếp tục stream. Khi subscription bị hủy, ứng dụng cần ngăn các vòng tiếp theo, truyền yêu cầu dừng đến công việc còn có thể dừng, ghi nhận chính xác những tác động đã hoàn tất và bù trừ khi nghiệp vụ cho phép.

Bài này sử dụng Spring AI 2.1.0, Reactor và Spring Framework làm mốc. Nội dung phân biệt ba khái niệm:

- **Hủy luồng:** subscriber không muốn nhận thêm dữ liệu.
- **Hủy công việc:** ứng dụng yêu cầu một tác vụ đang chạy dừng lại.
- **Hoàn tác hoặc bù trừ:** xử lý nghiệp vụ để đảo ngược hay cân bằng một tác động đã xảy ra.

Ba việc này có thể xảy ra cùng nhau nhưng không đồng nghĩa. Thiết kế đúng phải xác định trạng thái của từng công việc và từng side effect trước khi thông báo cho người dùng rằng yêu cầu đã bị hủy.

## Ba vòng đời cần theo dõi riêng

Không nên dùng một cờ boolean cancelled cho toàn bộ request. Một request có thể mất kết nối trong khi công việc vẫn chạy; một tool có thể hoàn tất dù request đã bị hủy; hoặc công việc có thể cần bù trừ sau khi side effect đã commit.

| Vòng đời | Trạng thái ví dụ | Ý nghĩa |
|---|---|---|
| Subscription/stream | ACTIVE, CANCELLED, COMPLETED, ERROR | Trạng thái truyền dữ liệu tới một subscriber. |
| Run/workflow | RUNNING, CANCEL_REQUESTED, CANCELLED, COMPLETED, FAILED, PARTIAL | Trạng thái của toàn bộ tác vụ AI và các bước nghiệp vụ. |
| Tool operation | NOT_STARTED, RUNNING, COMMITTED, CANCELLED, COMPENSATION_PENDING, COMPENSATED, FAILED | Trạng thái của một lần thực thi công cụ và tác động của nó. |

Ví dụ, người dùng ngắt kết nối SSE trong khi tool đang tạo báo cáo:

1. Subscription chuyển sang CANCELLED.
2. Ứng dụng ghi nhận subscriber đã rời đi.
3. Nếu chính sách yêu cầu dừng run khi không còn subscriber, run chuyển sang CANCEL_REQUESTED.
4. Tool kiểm tra cancellation token và dừng nếu vẫn còn ở giai đoạn có thể dừng an toàn.
5. Nếu file báo cáo đã được tạo và lưu, ứng dụng phải xóa file theo chính sách hoặc giữ lại như một kết quả đã hoàn tất; tín hiệu cancel không tự xóa file.

Một trạng thái stream kết thúc không đủ để suy ra trạng thái nghiệp vụ. Hãy lưu cả hai.

## Reactor cancellation thực sự có nghĩa gì?

Trong Reactive Streams, subscriber có thể gọi Subscription.cancel() để yêu cầu publisher ngừng phát dữ liệu. Reactor truyền tín hiệu hủy ngược qua pipeline. Các toán tử như take, next và timeout cũng có thể gây cancellation.

Một vài điểm quan trọng:

- Cancellation là tín hiệu điều khiển luồng dữ liệu, không phải lệnh rollback nghiệp vụ.
- Publisher hoặc nguồn dữ liệu có thể giải phóng tài nguyên khi nhận cancellation.
- Một nguồn bất đồng bộ có thể hủy request đang chờ nếu client và server hỗ trợ.
- Một tác vụ blocking đang chạy có thể không dừng ngay; khả năng ngắt phụ thuộc scheduler, thread, thư viện I/O và cách callback xử lý interruption.
- Nếu dịch vụ bên ngoài đã nhận và xử lý lệnh, hủy kết nối phía client không bảo đảm dịch vụ đó chưa tạo side effect.
- Cancellation signal không cho biết lý do cụ thể. Nó có thể đến từ người dùng, timeout, take(1), subscriber downstream hoặc một toán tử khác.

Vì vậy, không được coi cancellation như bằng chứng rằng tool chưa chạy hoặc dữ liệu chưa thay đổi.

### doOnCancel và doFinally

Reactor cung cấp hook để quan sát việc hủy:

~~~java
Flux<String> answerStream = chatClient.prompt()
        .user(question)
        .tools(tools)
        .stream()
        .content()
        .doOnCancel(() -> runRegistry.markStreamCancelled(runId))
        .doFinally(signalType ->
                runRegistry.recordStreamTermination(runId, signalType.name()));
~~~

- doOnCancel chạy khi subscription nhận cancellation.
- doFinally chạy khi pipeline kết thúc do complete, error hoặc cancel; callback nhận SignalType.

Hai hook phù hợp để ghi nhận trạng thái, giải phóng tài nguyên cục bộ hoặc phát tín hiệu tới bộ điều phối. Không thực hiện một quy trình bù trừ dài, gọi HTTP blocking hoặc chờ transaction trong doOnCancel/doFinally. Hãy gửi lệnh tới một cancellation coordinator hoặc durable job manager để xử lý theo vòng đời riêng.

Không gắn trực tiếp requestCancel(runId) vào mọi doOnCancel nếu chính sách sản phẩm cho phép công việc tiếp tục sau khi client rời đi. Hãy phân biệt sự kiện subscriber disconnect với yêu cầu hủy nghiệp vụ rõ ràng.

### Ghi nhận nguồn yêu cầu hủy

Vì Reactor cancellation signal không mang theo lý do, hãy ghi nhận nguồn hủy ở nơi phát sinh sự kiện:

~~~java
public enum CancellationSource {
    USER_REQUEST,
    CLIENT_DISCONNECT,
    REQUEST_TIMEOUT,
    ADMIN_ACTION,
    SECURITY_POLICY,
    SERVER_SHUTDOWN
}
~~~

Endpoint cancel có thể lưu USER_REQUEST; timeout handler lưu REQUEST_TIMEOUT; hook của SSE chỉ lưu CLIENT_DISCONNECT. Không suy đoán nguồn hủy từ SignalType.CANCEL. Nguồn và thời điểm hủy giúp quyết định run nên tiếp tục nền, dừng ngay hay chuyển sang compensation.

## Hủy stream của ChatClient và vòng lặp ToolCallingAdvisor

Trong Spring AI 2.x, ChatClient tự đăng ký ToolCallingAdvisor. Advisor quản lý vòng model/tool: gọi model, nhận tool call, thực thi qua ToolCallingManager, nối tool result vào conversation history và gọi model tiếp cho đến khi không còn tool call.

Khi dùng .stream(), response được phát dưới dạng Flux. Nếu subscriber hủy, cancellation được truyền qua pipeline reactive và không nên có iteration mới được khởi tạo sau khi cancellation đã được quan sát. Tuy nhiên, nếu callback đã được dispatch, ứng dụng không được giả định callback hoặc side effect bên dưới đã bị rollback hay dừng tức thì.

Một vòng có thể ở các thời điểm khác nhau khi cancel đến:

| Thời điểm nhận cancel | Điều có thể đã xảy ra | Hành động cần làm |
|---|---|---|
| Trước khi model request được gửi | Chưa có model call hoặc tool execution. | Đánh dấu run hủy và không khởi tạo request. |
| Model đang stream text | Chưa chắc có tool call. | Hủy subscription/model request nếu provider client hỗ trợ. |
| Model đang stream partial tool arguments | Chưa có tool call hoàn chỉnh. | Không dispatch partial arguments; dừng iteration. |
| Model đã trả tool call hoàn chỉnh, chưa dispatch | Chưa có callback chạy. | Kiểm tra cancellation trước khi dispatch và bỏ qua call nếu run đã hủy. |
| Callback đang chạy | Tool có thể đã đọc dữ liệu hoặc tạo side effect. | Truyền cancellation token; chờ trạng thái thực tế và kiểm tra commit boundary. |
| Tool đã commit, model chưa được gọi lại | Side effect đã xảy ra. | Ghi nhận kết quả đã commit; không báo rằng thao tác chưa xảy ra. |
| Model đang tạo câu trả lời cuối | Side effect trước đó có thể đã hoàn tất. | Dừng phần stream còn lại; giữ trạng thái nghiệp vụ đã xác minh. |

Nếu cần kiểm soát chính xác trước từng tool dispatch, phê duyệt hoặc cancellation, ứng dụng có thể tắt auto-registration của ToolCallingAdvisor và tự điều phối bằng ToolCallingManager. Nếu chỉ cần quan sát tiến độ, custom advisor nằm bên trong vòng lặp thường giữ được composition tốt hơn.

## Phân biệt disconnect với yêu cầu hủy nghiệp vụ

Đóng tab hoặc mất mạng là sự kiện transport. Người dùng bấm nút Hủy là một ý định nghiệp vụ rõ ràng. Hai sự kiện này không nên tự động có cùng chính sách.

| Sự kiện | Mặc định nên cân nhắc | Ví dụ |
|---|---|---|
| Browser disconnect | Detach subscriber; run có thể tiếp tục ở nền. | Báo cáo mất 30 giây, người dùng có thể mở lại trang để xem kết quả. |
| Người dùng bấm Hủy | Gửi cancellation request tới run. | Người dùng không muốn tiếp tục tra cứu hoặc xử lý yêu cầu. |
| Request timeout | Dừng chờ của request và áp dụng deadline policy. | Gateway đóng request sau 20 giây. |
| Server shutdown | Lưu trạng thái và bàn giao/khôi phục job theo chính sách. | Instance bị restart khi một tác vụ đang chạy. |
| Policy/security revoke | Dừng các bước tiếp theo và chặn dispatch mới. | Quyền truy cập của user bị thu hồi giữa workflow. |

Nếu ứng dụng chọn hủy run khi subscriber disconnect, hãy công bố hành vi đó và kiểm thử các tình huống mạng chập chờn. Với tác vụ dài hoặc có side effect, thường nên tách job khỏi vòng đời kết nối SSE: SSE chỉ là kênh quan sát trạng thái, còn job có ID và trạng thái bền vững riêng.

## Thiết kế API cho job có thể hủy

Với tác vụ có thể chạy lâu hơn kết nối HTTP, tạo job trước rồi trả về runId:

~~~java
@PostMapping("/reports")
public Mono<ResponseEntity<ReportAccepted>> startReport(
        @RequestBody ReportRequest request) {

    return reportRunService.start(request)
            .map(runId -> ResponseEntity.accepted()
                    .body(new ReportAccepted(runId, "RUNNING")));
}

@GetMapping(value = "/reports/{runId}/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<RunEvent>> events(@PathVariable String runId) {
    return reportRunService.events(runId)
            .doOnCancel(() -> reportRunService.detachSubscriber(runId));
}

@PostMapping("/reports/{runId}/cancel")
public Mono<CancelResult> cancel(@PathVariable String runId) {
    return reportRunService.requestCancellation(runId);
}
~~~

detachSubscriber chỉ ghi nhận kênh theo dõi đã đóng. Endpoint cancel mới gửi yêu cầu dừng nghiệp vụ. runId phải được kiểm tra quyền sở hữu hoặc quyền quản trị trước khi đọc trạng thái, xem event hoặc hủy job.

Trạng thái job nên được lưu bền vững nếu cần tiếp tục sau restart:

~~~java
public enum RunStatus {
    QUEUED,
    RUNNING,
    CANCEL_REQUESTED,
    CANCELLED,
    CANCEL_TOO_LATE,
    COMPLETED,
    COMPLETED_WITH_SIDE_EFFECTS,
    COMPENSATION_PENDING,
    COMPENSATED,
    COMPENSATION_FAILED,
    PARTIAL,
    FAILED
}
~~~

Không dùng một Disposable trong bộ nhớ làm nguồn trạng thái duy nhất cho job dài hạn. Disposable hữu ích để hủy subscription cục bộ, nhưng không sống qua restart và không cho biết một giao dịch bên ngoài đã commit hay chưa.

## Truyền cancellation vào tool đang chạy

Một tool callback nên kiểm tra cancellation ở các ranh giới an toàn:

1. Trước khi bắt đầu công việc.
2. Trước mỗi bước I/O hoặc bước tốn tài nguyên.
3. Trước khi thực hiện side effect không thể đảo ngược.
4. Sau khi nhận kết quả từ dịch vụ ngoài và trước khi bắt đầu bước tiếp theo.

Ứng dụng có thể định nghĩa một cancellation token riêng:

~~~java
public interface RunCancellation {
    boolean isCancellationRequested();

    void throwIfCancellationRequested();
}
~~~

Truyền token hoặc run ID đã xác thực qua ToolContext hay một registry theo run. Không lấy cancellation state từ arguments do mô hình tạo.

~~~java
@Component
class ReportTools {

    private final ReportService reportService;
    private final RunControlRegistry runControls;

    ReportTools(ReportService reportService, RunControlRegistry runControls) {
        this.reportService = reportService;
        this.runControls = runControls;
    }

    @Tool(description = "Tạo báo cáo cho người dùng hiện tại")
    public ReportResult generateReport(
            String reportType,
            ToolContext toolContext) {

        String runId = requireTrustedRunId(toolContext);
        RunCancellation cancellation = runControls.cancellationFor(runId);

        cancellation.throwIfCancellationRequested();
        ReportPlan plan = reportService.prepare(reportType);

        cancellation.throwIfCancellationRequested();
        return reportService.generate(plan, cancellation);
    }
}
~~~

RunCancellation, RunControlRegistry và các service trong ví dụ là abstraction của ứng dụng. Với một công việc dài, ReportService.generate cần kiểm tra token bên trong các vòng xử lý và giữa các lần gọi I/O; chỉ kiểm tra một lần ở đầu method không đủ.

### Hủy một HTTP request đang chờ

Nếu service dùng WebClient, cancellation của reactive pipeline có thể được truyền tới request đang chờ ở client. Tuy nhiên, nếu server đích đã nhận request và bắt đầu xử lý, việc client hủy kết nối không bảo đảm server dừng hoặc hoàn tác tác động.

Với thao tác ghi qua HTTP:

- Dùng idempotency key hoặc operation ID do ứng dụng tạo.
- Có endpoint truy vấn trạng thái theo operation ID.
- Nếu API hỗ trợ, dùng endpoint cancel riêng theo operation ID.
- Sau khi cancel, truy vấn trạng thái thực tế trước khi quyết định retry hoặc bù trừ.
- Không gửi lại lệnh ghi chỉ vì client không nhận được response; request trước có thể đã thành công.

### Hủy một tác vụ blocking

Future.cancel(true) hoặc interruption có thể yêu cầu thread dừng, nhưng chỉ có tác dụng nếu tác vụ và thư viện bên dưới hợp tác với interruption. Không dùng nó như bảo đảm rằng JDBC driver, SDK thanh toán, file operation hoặc remote server đã dừng.

Không nuốt InterruptedException. Khôi phục trạng thái interrupt khi cần và thoát khỏi bước xử lý ở ranh giới an toàn. Nếu thao tác đã commit, chuyển sang xử lý trạng thái sau commit thay vì báo CANCELLED giả.

## Phân biệt transaction rollback với side effect đã commit

Cancellation có thể dẫn đến rollback khi thao tác vẫn nằm trong một reactive transaction đang hoạt động. Spring Framework quy định cancel signal trên reactive transaction dẫn tới rollback; điều này áp dụng khi toàn bộ công việc tham gia cùng ReactiveTransactionManager và pipeline chưa commit.

Ví dụ:

~~~java
public Mono<Void> updateOrderReactive(String orderId) {
    return transactionalOperator.transactional(
            orderRepository.markProcessing(orderId)
                    .then(auditRepository.insertProcessingEvent(orderId))
    );
}
~~~

Nếu subscriber hủy pipeline trước khi transaction hoàn tất, TransactionalOperator có thể rollback transaction đó. Hãy kiểm thử với transaction manager và database thực tế.

Nhưng có các ranh giới mà rollback không thể đi qua:

- Một method imperative dùng @Transactional đã kết thúc và commit trước khi callback trả về.
- Một API thanh toán đã chấp nhận giao dịch.
- Email/SMS đã được gửi.
- Một message đã được consumer bên ngoài xử lý.
- File đã được upload sang object storage hoặc một hệ thống khác.
- Một database khác đã commit trong khi không có distributed transaction chung.

Transaction database chỉ bảo đảm atomicity trong phạm vi transaction manager quản lý. Nó không tự rollback một HTTP request hoặc một email đã gửi. Không giữ transaction database mở trong lúc chờ model stream hoặc dịch vụ ngoài; việc đó kéo dài lock và không tạo ra rollback xuyên hệ thống.

## Xác định commit boundary cho từng tool

Mỗi tool có thể có nhiều bước và nhiều loại tác động. Hãy ghi nhận điểm mà tác động trở nên có hiệu lực:

| Tool | Trước commit | Sau commit | Cách xử lý khi cancel đến muộn |
|---|---|---|---|
| Tạo báo cáo | Đang truy vấn và dựng nội dung tạm. | File đã được lưu và có report ID. | Giữ báo cáo, xóa theo policy hoặc đánh dấu kết quả đã hoàn tất. |
| Đặt chỗ | Đang kiểm tra chỗ trống và giữ reservation tạm. | Hệ thống xác nhận booking. | Gửi yêu cầu hủy booking nếu còn được phép; ghi nhận trạng thái hủy riêng. |
| Thanh toán | Đang validate và authorize. | Payment provider xác nhận capture. | Tạo refund/void theo trạng thái provider; không giả định transaction local đã rollback. |
| Gửi email | Đang tạo nội dung và xếp hàng. | Mail service đã nhận/gửi message. | Có thể gửi email đính chính; thường không thể thu hồi email đã gửi. |
| Cập nhật hồ sơ | Đang validate và chuẩn bị thay đổi. | Database transaction commit. | Tạo một lệnh sửa ngược có audit hoặc giữ nguyên thay đổi theo policy. |

Trước commit, cancellation có thể cho phép dừng và bỏ thay đổi chưa commit. Sau commit, trạng thái đúng thường là COMPLETED_WITH_SIDE_EFFECTS, COMPENSATION_PENDING hoặc CANCEL_TOO_LATE, tùy hợp đồng API. Không trả CANCELLED nếu tác động đã xảy ra mà không được bù trừ.

## Xử lý side effect bằng idempotency và operation ledger

Một vấn đề phổ biến là người dùng hủy nhưng không nhận được response; sau đó họ thử lại. Request đầu có thể đã tạo tác động dù browser không thấy kết quả. Nếu request mới thực thi lại, ứng dụng có thể gửi hai email, tạo hai booking hoặc thu tiền hai lần.

Hãy cấp operation ID/idempotency key cho từng thao tác có side effect:

~~~java
public record OperationCommand(
        String runId,
        String operationId,
        String idempotencyKey,
        String action,
        String resourceId) {
}
~~~

Trong database, đặt unique constraint cho idempotency key theo phạm vi phù hợp. Trước khi thực thi:

1. Tìm operation theo idempotency key.
2. Nếu đã COMMITTED, trả lại kết quả đã lưu thay vì thực thi lần nữa.
3. Nếu đang RUNNING, trả trạng thái đang xử lý hoặc nối vào operation hiện tại.
4. Nếu CANCEL_REQUESTED trước commit, dừng ở ranh giới an toàn.
5. Nếu operation thất bại trước side effect, retry theo policy.
6. Nếu kết quả không xác định do timeout, truy vấn trạng thái provider trước khi retry.

Operation ledger nên lưu run ID, operation ID, loại hành động, resource reference, trạng thái, idempotency key, timestamp, kết quả đã lọc và thông tin correlation cần thiết. Không lưu secret hoặc payload nhạy cảm nếu không có nhu cầu và chính sách bảo vệ rõ ràng.

Idempotency không phải rollback. Nó ngăn một lệnh được áp dụng lặp lại ngoài ý muốn và giúp ứng dụng tra cứu kết quả của lần thực thi trước.

## Bù trừ tác động đã hoàn tất bằng Saga

Khi một workflow gồm nhiều dịch vụ không thể dùng chung một transaction, hãy mô hình hóa các bước như một saga. Mỗi bước thành công có thể có một hành động bù trừ tương ứng.

Ví dụ quy trình đặt và thanh toán đơn hàng:

| Bước | Tác động | Hành động bù trừ có thể có |
|---|---|---|
| 1. Giữ hàng | Tồn kho được reserve. | Giải phóng reservation. |
| 2. Tạo đơn | Đơn hàng chuyển sang trạng thái đã tạo. | Hủy đơn nếu chưa được giao. |
| 3. Thu tiền | Payment được capture. | Refund hoặc void theo trạng thái provider. |
| 4. Gửi xác nhận | Email được gửi. | Gửi email đính chính; không thể đảm bảo thu hồi email cũ. |

Compensation là một nghiệp vụ mới nhằm cân bằng tác động trước đó; nó không phải rollback nguyên tử. Compensation có thể thất bại, cần retry hoặc cần người vận hành can thiệp. Hãy lưu riêng COMPENSATION_PENDING, COMPENSATED và COMPENSATION_FAILED.

Không chạy compensation chỉ vì browser disconnect. Trước tiên phải xác định run có nhận yêu cầu hủy nghiệp vụ hay không, operation nào đã commit và policy có cho phép đảo ngược không.

### Dùng outbox để không mất lệnh bù trừ

Nếu việc hủy cần phát một lệnh compensation tới worker hoặc message broker, ghi trạng thái operation và outbox message trong cùng database transaction. Worker đọc outbox, thực hiện bù trừ với idempotency key rồi cập nhật trạng thái.

Outbox giúp tránh tình huống database đã ghi COMPENSATION_PENDING nhưng ứng dụng chết trước khi publish message. Worker cần hỗ trợ retry, deduplication và dead-letter handling.

## Xử lý race giữa cancel và commit

Một race condition thường gặp:

1. Tool kiểm tra isCancellationRequested() và nhận false.
2. Người dùng gửi cancel.
3. Tool tiếp tục gọi payment provider.
4. Payment provider capture thành công.
5. Run bị đánh dấu CANCELLED.

Kết quả này sai vì trạng thái run nói đã hủy trong khi payment đã commit.

Không chỉ kiểm tra cancellation bằng một lần đọc boolean. Hãy phối hợp run state và operation state bằng thao tác atomic/transaction:

~~~sql
UPDATE tool_operation
SET status = 'COMMITTING', version = version + 1
WHERE operation_id = :operationId
  AND status = 'RUNNING'
  AND cancel_requested = FALSE;
~~~

Nếu update không thay đổi hàng nào, cancellation hoặc một chuyển trạng thái khác đã thắng race; tool không được bắt đầu commit. Nếu operation đã chuyển sang COMMITTING, cancel handler phải biết thao tác đã vượt qua ranh giới an toàn và chuyển sang trạng thái chờ kết quả/compensation theo policy.

Đối với external provider, không thể giữ transaction database mở để khóa provider. Hãy dùng operation ID, idempotency key và state machine để đối soát trạng thái sau request. Cần xử lý cả trường hợp timeout mà provider đã thành công nhưng client chưa nhận response.

## Hủy trước dispatch, trong khi chạy và sau commit

Một coordinator có thể cung cấp các thao tác:

| Thao tác | Thời điểm | Kết quả mong đợi |
|---|---|---|
| requestRunCancellation(runId) | Người dùng gửi yêu cầu hủy. | Atomically chuyển run từ RUNNING sang CANCEL_REQUESTED. |
| checkBeforeModelCall(runId) | Trước mỗi iteration model. | Không tạo model request mới nếu run đã hủy. |
| checkBeforeToolDispatch(runId, toolCallId) | Sau khi tool call hoàn chỉnh, trước dispatch. | Không chạy callback mới nếu cancellation đã thắng. |
| signalRunningOperation(operationId) | Tool đang chạy. | Truyền cancellation token tới công việc hợp tác. |
| recordCommit(operationId, result) | Side effect được xác nhận. | Lưu trạng thái COMMITTED và kết quả đã lọc. |
| scheduleCompensation(operationId) | Cancel đến sau commit và policy cho phép bù trừ. | Tạo công việc bù trừ bền vững. |
| finalizeRun(runId) | Không còn bước nào cần chạy. | Chọn CANCELLED, PARTIAL, COMPLETED hoặc trạng thái compensation phù hợp. |

Với Spring AI 2.1.0, Tool Call Confirmation là cơ chế tạm dừng trước khi tool call được thực thi và chờ quyết định của con người. Nó phù hợp với phê duyệt trước side effect. Confirmation khác với cancellation: confirmation quyết định có cho phép call chạy hay không; cancellation yêu cầu dừng một run hoặc operation đang diễn ra.

## Không dùng một transaction bao trùm toàn bộ tool loop

Một tool loop có thể kéo dài qua nhiều model call, nhiều callback và nhiều hệ thống. Không mở transaction database bao trùm toàn bộ loop:

- Model provider có thể mất nhiều giây hoặc timeout.
- Tool có thể gọi dịch vụ ngoài không tham gia transaction.
- Một tool result có thể cần được gửi lại model trước khi biết bước tiếp theo.
- Người dùng có thể hủy hoặc cần phê duyệt giữa các iteration.
- Transaction dài giữ connection/lock và làm tăng nguy cơ deadlock.

Hãy dùng transaction ngắn cho từng thay đổi dữ liệu cục bộ. Ghi trạng thái workflow bền vững giữa các bước. Nếu nhiều dịch vụ cần phối hợp, dùng saga/outbox và compensation thay vì cố giả lập một transaction phân tán.

## Trạng thái trả về cho người dùng

Khi nhận cancellation, hãy xác định điều gì đã thực sự xảy ra trước khi trả trạng thái:

| Trạng thái | Khi dùng | Thông điệp phù hợp |
|---|---|---|
| CANCELLED | Dừng trước khi có side effect hoặc mọi thay đổi chưa commit đã rollback. | “Yêu cầu đã được hủy.” |
| CANCEL_REQUESTED | Đã nhận yêu cầu hủy nhưng tool đang chạy/chưa xác định kết quả. | “Đang dừng tác vụ và kiểm tra trạng thái.” |
| COMPLETED_WITH_SIDE_EFFECTS | Tác động đã commit trước khi hủy đến. | “Thao tác đã hoàn tất trước khi yêu cầu hủy được xử lý.” |
| COMPENSATION_PENDING | Đã commit và đang thực hiện bù trừ. | “Thao tác đã phát sinh; hệ thống đang xử lý yêu cầu hoàn tác.” |
| COMPENSATED | Hành động bù trừ đã hoàn tất và được xác minh. | “Tác động đã được bù trừ.” |
| COMPENSATION_FAILED | Bù trừ thất bại hoặc cần can thiệp. | “Không thể tự động hoàn tác; yêu cầu cần được hỗ trợ.” |
| PARTIAL | Một số bước hoàn tất, một số bước chưa chạy hoặc thất bại. | Nêu rõ phần đã hoàn tất và phần còn lại. |

Không thông báo “Đã hủy thanh toán” nếu mới chỉ gửi yêu cầu hủy tới payment provider. Chỉ xác nhận khi provider trả trạng thái void/refund phù hợp và ứng dụng đã lưu kết quả.

## Kiểm thử cancellation và side effect

Các test cần điều khiển thời điểm cancel bằng latch/barrier hoặc fake service thay vì dựa vào Thread.sleep() tùy ý.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Cancel trước khi model call bắt đầu | Không gửi request tới model. |
| Cancel khi model đang stream text | Stream dừng và không khởi tạo iteration mới. |
| Cancel khi partial tool arguments đang được stream | Callback không chạy vì chưa có tool call hoàn chỉnh. |
| Cancel sau tool call hoàn chỉnh nhưng trước dispatch | Gate kiểm tra cancellation chặn callback. |
| Cancel trong khi callback đang chạy | Callback dừng tại cancellation checkpoint nếu có thể; trạng thái operation phản ánh thực tế. |
| Callback blocking không hợp tác với interruption | Run không báo đã dừng operation cho tới khi xác định được trạng thái. |
| Cancel trước commit trong reactive transaction | Transaction rollback theo cấu hình và transaction manager thực tế. |
| Cancel sau commit database | Không giả định rollback; chuyển sang policy giữ kết quả hoặc compensation. |
| Cancel sau payment capture | Tra cứu provider và thực hiện void/refund nếu nghiệp vụ cho phép. |
| Client disconnect nhưng job chạy nền | Subscriber detached; job tiếp tục theo policy. |
| Người dùng bấm Hủy | Run nhận cancellation request có xác thực. |
| Hai cancel request đồng thời | Chỉ một chuyển trạng thái hợp lệ; xử lý idempotent. |
| Cancel race với commit | Atomic transition xác định bên thắng; không báo sai trạng thái. |
| Retry sau khi response bị mất | Idempotency key ngăn side effect trùng. |
| Compensation thất bại | Lưu COMPENSATION_FAILED và tạo cảnh báo/hàng đợi xử lý. |
| Server restart giữa workflow | Run và operation được khôi phục từ durable state/outbox. |

Nên kiểm thử cả cancellation signal của Reactor, explicit cancel API, timeout và disconnect. Chúng có thể cùng tạo cancellation ở pipeline nhưng phải được ghi nhận đúng nguồn để áp dụng chính sách phù hợp.

## Bài tập thực hành

Xây dựng luồng tạo báo cáo có thể hủy:

1. Endpoint POST tạo report run và trả runId.
2. Endpoint SSE chỉ theo dõi event của run; browser disconnect chỉ detach subscriber.
3. Endpoint POST /reports/{runId}/cancel gửi cancellation request có xác thực.
4. Tool tạo báo cáo nhận run ID từ ToolContext và kiểm tra cancellation giữa các bước.
5. Trước khi lưu file cuối, tool dùng atomic state transition để kiểm tra cancellation.
6. Nếu file chưa commit, dừng và dọn file tạm.
7. Nếu file đã lưu, ghi operation COMMITTED; không trả CANCELLED giả.
8. Nếu policy yêu cầu xóa báo cáo sau commit, tạo compensation job qua outbox.
9. Thử ngắt SSE, bấm Hủy trước commit, bấm Hủy sau commit và restart worker.
10. Thử gửi lại cùng command với idempotency key để xác minh không tạo báo cáo trùng.

Bạn hoàn thành khi có thể trả lời chính xác: subscription đã hủy chưa, run có nhận cancel request không, tool nào đã bắt đầu, operation nào đã commit và compensation nào còn đang chờ.

## Danh sách kiểm tra trước khi triển khai

- [ ] Tách trạng thái subscription, run và từng tool operation.
- [ ] Phân biệt browser disconnect với explicit business cancellation.
- [ ] Dùng doOnCancel/doFinally để quan sát và cleanup nhẹ; không chạy compensation dài trong hook.
- [ ] Kiểm tra cancellation trước model call và trước tool dispatch.
- [ ] Truyền cancellation token tới công việc dài và kiểm tra ở các checkpoint an toàn.
- [ ] Không giả định callback blocking hoặc remote service dừng ngay khi subscriber cancel.
- [ ] Xác định commit boundary cho từng tool có side effect.
- [ ] Chỉ dựa vào reactive transaction rollback khi thao tác thực sự nằm trong transaction đó và chưa commit.
- [ ] Có idempotency key và operation ledger cho thao tác ghi.
- [ ] Dùng saga/compensation khi cần đảo ngược side effect đã commit.
- [ ] Lưu compensation request bền vững bằng outbox khi cần xử lý nền.
- [ ] Có atomic transition để giải quyết race giữa cancel và commit.
- [ ] Không retry lệnh ghi khi chưa đối soát trạng thái lần chạy trước.
- [ ] Tách job dài khỏi vòng đời SSE và hỗ trợ resume/status lookup.
- [ ] Trả trạng thái chính xác: CANCELLED, CANCEL_REQUESTED, COMPLETED_WITH_SIDE_EFFECTS, COMPENSATION_PENDING hoặc PARTIAL.
- [ ] Có test cho disconnect, explicit cancel, timeout, partial tool call, commit race, duplicate request và restart.

Hủy luồng chỉ dừng việc truyền dữ liệu. Hủy công việc cần cơ chế hợp tác ở tầng ứng dụng và tool. Với tác động đã commit, ứng dụng phải ghi nhận kết quả hoặc chạy một hành động bù trừ có thể kiểm chứng. Khi ba vòng đời này được quản lý riêng, người dùng nhận được trạng thái trung thực và hệ thống tránh lặp hoặc bỏ sót side effect.

## Tài liệu tham khảo

- [Spring AI 2.1.0 – ToolCallingAdvisor và tool execution lifecycle](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 – Tool Calling và Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring Framework – Programmatic Transaction Management và Cancel Signals](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework 6.2 – Reactive Transaction Cancel Signals](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Project Reactor – Mono doOnCancel và doFinally](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
