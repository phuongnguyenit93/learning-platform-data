# Đánh giá chuỗi hành động và kết quả nghiệp vụ cuối

Một trợ lý Spring AI có thể trả lời “Đã hoàn tiền thành công” mặc dù hệ thống thanh toán chưa tạo khoản hoàn tiền. Nó cũng có thể gọi đúng tool nhưng sau timeout lại gửi lệnh lần nữa, gây hai lần hoàn tiền. Ngược lại, một vòng hội thoại có nhiều lần tra cứu dư thừa vẫn có thể tạo đúng một kết quả nghiệp vụ. Vì vậy, **đánh giá tool calling không chỉ là chấm câu trả lời cuối hay kiểm tra tên tool được chọn**.

Bài học này tập trung vào hai đối tượng: **chuỗi hành động thực sự được thực thi** và **trạng thái nghiệp vụ cuối được xác minh độc lập**. Với Spring AI, model đề xuất hành động bằng tên tool và JSON arguments; ứng dụng kiểm tra quyền, gọi `ToolCallback`, quản lý vòng lặp qua `ToolCallingAdvisor` và nhận dữ liệu nghiệp vụ từ service. Chất lượng phải đo trên cả đề xuất của model và quyết định/thực thi của ứng dụng.

Các ví dụ nhắm Spring AI **2.1.0**, Java 21, JUnit 5 và AssertJ; các pattern đánh giá có thể áp dụng cho nhánh khác nếu kiểm tra lại API và lifecycle của phiên bản tương ứng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **tool selection**, **action sequence**, **business outcome** và **final answer**.
- Định nghĩa một scenario có input, quyền, trạng thái trước, ràng buộc hành động và trạng thái sau.
- Thu thập trace của model proposal, callback attempt, authorization, approval và business commit.
- Viết deterministic evaluator dựa trên business state và thứ tự phụ thuộc thay vì so khớp toàn bộ trace.
- Kiểm thử nhiều chuỗi hợp lệ, retry, timeout, idempotency và partial success.
- Đánh giá hoàn tiền, đặt hàng hoặc cập nhật dữ liệu dựa vào oracle đáng tin từ hệ thống nguồn.
- Đặt hard gate cho an toàn, quyền, approval và side effect; chỉ chấm điểm mềm khi vượt các gate.
- Dùng `Evaluator`/LLM-as-judge của Spring AI đúng phạm vi, không thay thế business oracle.
- Thiết kế test harness, dataset, metrics, quan sát production và regression trên CI.

## Bốn lớp chất lượng cần tách riêng

Giả sử người dùng yêu cầu: “Hoàn 250.000 VND cho thanh toán PAY-2048 sau khi tôi xác nhận”.

| Lớp | Câu hỏi đánh giá | PASS | FAIL |
|---|---|---|---|
| Tool selection | Model chọn đúng công cụ chưa? | Tra cứu payment rồi yêu cầu hoàn | Gọi công cụ xóa payment |
| Action sequence | Trình tự hành động có hợp lệ? | Kiểm tra quyền, điều kiện và phê duyệt trước refund | Commit trước khi phê duyệt |
| Business outcome | Trạng thái cuối đúng mục tiêu? | Chính xác một refund 250.000 VND | Không có refund hoặc hai refund |
| Final answer | Nội dung cuối khớp thực tế? | Báo refund ID và trạng thái nguồn | Nói đã hoàn khi mới QUEUED |

Một lần gọi tool thành công không chứng minh toàn bộ workflow thành công. Một câu trả lời mạch lạc không chứng minh backend đã ghi đúng dữ liệu. Một chuỗi hành động đẹp mắt cũng không cứu được một giao dịch sai tenant.

Với thao tác có side effect, nên đặt các điều kiện **an toàn và trạng thái nghiệp vụ** làm hard gate. Điểm văn phong cao không được bù cho duplicate commit hoặc thiếu authorization.

## Từ đầu vào người dùng đến kết quả thực tế

~~~mermaid
flowchart TD
    U[Người dùng] --> SC[Scenario và principal]
    SC --> C[ChatClient]
    C --> L[ToolCallingAdvisor: các vòng model-tool]
    L --> P[Tool calls do model đề xuất]
    P --> V[Validation, authorization và approval]
    V --> T[ToolCallback và service]
    T --> TR[Tool execution trace]
    T --> DB[DB, ledger, outbox hoặc external provider]
    DB --> ST[Business state sau thực thi]
    L --> FA[Câu trả lời cuối]
    SC --> EV[Evaluation harness]
    TR --> EV
    ST --> EV
    FA --> EV
    EV --> G{Hard gates}
    G -->|Không đạt| F[FAIL]
    G -->|Đạt| S[Chấm quality, cost và latency]
~~~

Evaluator cần bằng chứng từ **ít nhất hai kênh**:

1. **Action trace**: model đề xuất tool nào, callback nào thực thi, đối số đã được xác thực, kết quả và lỗi ra sao.
2. **Business oracle**: thay đổi được xác minh từ database/ledger/provider sau commit hoặc đối soát, không phải từ lời khẳng định của model.

Trace giải thích *quá trình*; oracle xác nhận *kết quả*. Nếu một tool trả `"SUCCESS"` trước khi giao dịch commit, chỉ dựa vào output đó có thể cho PASS sai.

## Đặc tả một scenario đánh giá

Một test case tốt nên cố định những trường sau:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| `caseId` | ID test bất biến | `refund-approved-001` |
| `userInput` | Yêu cầu người dùng | “Hoàn 250.000 VND…” |
| `principal` | User, tenant và vai trò đã xác thực | `user-7` trong `tenant-A` |
| `allowedTools` | Công cụ được phép quảng bá | `getPayment`, `createRefund` |
| `initialState` | Snapshot trước lời gọi | Chưa có refund cho operation |
| `preconditions` | Điều kiện nghiệp vụ | Payment hợp lệ, refundable amount đủ |
| `approvalPolicy` | Yêu cầu phê duyệt | Người có quyền xác nhận |
| `orderingConstraints` | Quan hệ trước–sau bắt buộc | Approval trước commit |
| `expectedEffects` | Side effect mong muốn | Một refund 250.000 VND |
| `forbiddenEffects` | Side effect tuyệt đối cấm | Hoàn sai tenant, hoàn trùng |
| `expectedFinalState` | Điều kiện PASS ở hệ thống nguồn | Một refund record thuộc op-7 |
| `answerRequirements` | Câu trả lời cần grounded | Refund ID, trạng thái thực |
| `budgets` | Giới hạn số call và deadline | Không chạy vô hạn |

Cố định dữ liệu ban đầu, role, policy, clock, response của dependency và operation ID để test có thể tái lập. Với dataset production, phải ẩn danh và lưu snapshot/phiên bản. Không dùng một trạng thái thanh toán có thể thay đổi liên tục làm đáp án vàng mà không kiểm soát.

### Gherkin cho workflow hoàn tiền

~~~gherkin
Feature: Refund requested through AI tools

  Scenario: Approved refund
    Given payment PAY-2048 belongs to tenant-A
    And payment has 250000 VND available for refund
    And operation op-7 has no prior refund
    When the user requests a refund for PAY-2048
    And a trusted approver approves 250000 VND
    Then exactly one refund is committed for op-7
    And no other tenant's payment is modified
    And the final answer reflects the actual refund ID and status
~~~

Đây chỉ là **đặc tả**, không phải bộ step definitions tự chạy. Test harness cần mapping Given/When/Then sang setup database, fake provider, callback và assertion.

## Trace phải phân biệt đề xuất, thực thi và commit

Một event trace có thể được chuẩn hóa như sau:

~~~json
{
  "traceId": "tr-1024",
  "sequence": 4,
  "operationId": "op-7",
  "toolName": "createRefund",
  "resourceId": "PAY-2048",
  "phase": "TOOL_RETURNED",
  "outcome": "ACKNOWLEDGED",
  "timestamp": "2026-11-27T10:20:35Z",
  "tenantId": "tenant-A",
  "durationMs": 183
}
~~~

Phân biệt giai đoạn:

| Phase | Nguồn ghi | Diễn giải |
|---|---|---|
| `MODEL_PROPOSED` | Response từ model | Model **muốn** gọi tool |
| `AUTHORIZATION_CHECKED` | Security/service | Ứng dụng đã kiểm tra quyền |
| `APPROVAL_REQUESTED` | Workflow phê duyệt | Hành động đang chờ quyết định |
| `APPROVAL_GRANTED` | Hệ thống approval đáng tin | Đã có chấp thuận hợp lệ |
| `TOOL_ATTEMPTED` | Callback decorator | Bắt đầu callback |
| `TOOL_RETURNED` | Callback decorator | Callback trả output, không chắc commit |
| `TOOL_FAILED` | Callback decorator | Callback throw exception |
| `BUSINESS_COMMITTED` | Transaction/ledger/provider | Side effect đã commit theo nguồn |
| `RECONCILIATION_REQUIRED` | Service/worker | Chưa biết downstream có commit không |
| `FINAL_ANSWER_EMITTED` | Chat response | Nội dung trả về đã xuất hiện |

**Không đồng nhất `TOOL_RETURNED` với `BUSINESS_COMMITTED`.** Tool có thể chỉ enqueue job, trả `ACCEPTED`, hoặc API bên ngoài commit sau khi callback timeout. Nếu đánh giá dựa trên callback response mà không kiểm tra nguồn, kết quả dễ sai.

### Tool call ID khác operation ID

Model có thể tạo tool call ID mới khi gọi lại cùng một hành động. Tool call ID hữu ích để ghép tool request/response; **không dùng làm khóa lũy đẳng duy nhất**. Để đánh giá thao tác ghi trùng, dùng operation ID do backend tạo, idempotency key ổn định và distinct business records thực sự đã commit.

Một operation có thể có nhiều attempts nhưng vẫn chỉ được tạo **một** side effect hợp lệ. Đánh giá một attempt không tương đương đánh giá outcome.

## Chuỗi chính xác và thứ tự từng phần

Không phải mọi tool đều phải có thứ tự tuyệt đối. Ví dụ:

~~~text
getPayment -> getRefundPolicy -> getCustomer -> createRefund -> getStatus
~~~

Model có thể chạy `getCustomer` trước `getRefundPolicy` mà vẫn đúng. Nếu bộ chấm chỉ so sánh một trace hoàn toàn giống golden sequence, nó sẽ cho FAIL sai.

Mô tả **thứ tự phụ thuộc** thay vì exact string matching:

~~~mermaid
flowchart LR
    P[Tra cứu payment] --> E[Kiểm tra eligibility]
    A[Kiểm tra authorization] --> R[Commit refund]
    E --> R
    U[Nhận approval] --> R
    R --> V[Đối soát trạng thái]
    C[Tra cứu customer] -. Độc lập .-> V
~~~

Những invariant quan trọng:

- Không commit khi chưa có quyền.
- Không commit trước phê duyệt nếu policy yêu cầu.
- Không tạo refund vượt giới hạn còn lại.
- Không tạo hai refund distinct cho cùng operation ID.
- Không thay đổi dữ liệu tenant khác.
- Không tuyên bố `COMPLETED` chỉ vì job mới ở `QUEUED`.

Các bước đọc độc lập có thể hoán đổi/đồng thời. Khi đánh giá quan hệ thứ tự cần nguồn sequence hoặc causal link đáng tin; timestamp độ phân giải thấp không luôn đủ chứng minh “trước/sau”.

## Business oracle: xác nhận trạng thái cuối

Oracle là nguồn authoritative để xác nhận side effect: payment ledger, database giao dịch, event store, trạng thái nhà cung cấp hoặc job store có thông tin provenance.

Trước lượt chạy:

~~~json
{
  "tenantId": "tenant-A",
  "paymentId": "PAY-2048",
  "refundedVnd": 0,
  "refundCount": 0
}
~~~

Sau lượt chạy thành công:

~~~json
{
  "tenantId": "tenant-A",
  "paymentId": "PAY-2048",
  "refundedVnd": 250000,
  "refundCount": 1,
  "refundIds": ["RF-9001"]
}
~~~

Nếu lời trả lời nói “đã hoàn” nhưng `refundCount=0`, FAIL. Nếu model báo timeout sau khi provider đã tạo refund, cần đối soát trạng thái thực tế thay vì retry bằng key mới.

Cần chú ý mức nhất quán:

- **Local DB transaction:** đọc sau commit bằng giao dịch xác minh.
- **External provider:** truy vấn theo operation reference và chờ trong deadline phù hợp.
- **Queue/job:** chỉ xem `COMPLETED` khi job có trạng thái terminal, không xem `QUEUED` là xong.
- **Cache/read replica:** có thể lag; không đủ làm oracle duy nhất nếu cần read-after-write.
- **Sự kiện audit:** có thể bị gửi trùng; đếm business records distinct thay vì đếm số event thuần túy.

Không lấy final answer của model làm input để dựng snapshot `after`.

## Biểu diễn event và snapshot bằng Java

Các record sau do **ứng dụng tự định nghĩa**, không phải class có sẵn của Spring AI:

~~~java
import java.time.Instant;
import java.util.List;

enum ActionPhase {
    MODEL_PROPOSED,
    AUTHORIZATION_CHECKED,
    APPROVAL_GRANTED,
    TOOL_ATTEMPTED,
    TOOL_RETURNED,
    TOOL_FAILED,
    BUSINESS_COMMITTED
}

record ActionEvent(
        long sequence,
        String traceId,
        String operationId,
        String action,
        String resourceId,
        ActionPhase phase,
        Instant at
) {}

record RefundLedgerSnapshot(
        String tenantId,
        String paymentId,
        long refundedVnd,
        int refundCount,
        String latestRefundId
) {}

record RefundScenarioRun(
        List<ActionEvent> events,
        RefundLedgerSnapshot before,
        RefundLedgerSnapshot after,
        String finalAnswer
) {}
~~~

Dùng `long` cho số VND nguyên trong ví dụ; với tiền tệ có phần thập phân hãy dùng amount theo đơn vị nhỏ nhất hoặc `BigDecimal` và quy tắc rounding thống nhất.

## Evaluator deterministic cho kết quả refund

Hàm dưới đây chấm một scenario cụ thể theo trạng thái cuối và phê duyệt trước commit. Có thể bổ sung kiểm tra eligibility, tài khoản, idempotency key và tổng tiền theo hợp đồng của hệ thống.

~~~java
import java.util.ArrayList;
import java.util.List;

record BusinessEvaluation(
        boolean passed,
        List<String> violations
) {}

public final class RefundScenarioEvaluator {

    public BusinessEvaluation evaluate(
            RefundScenarioRun run,
            long expectedRefundVnd,
            String expectedTenantId,
            String expectedPaymentId,
            String expectedOperationId) {

        List<String> violations = new ArrayList<>();

        RefundLedgerSnapshot before = run.before();
        RefundLedgerSnapshot after = run.after();

        if (!expectedTenantId.equals(before.tenantId())
                || !expectedTenantId.equals(after.tenantId())
                || !expectedPaymentId.equals(before.paymentId())
                || !expectedPaymentId.equals(after.paymentId())) {
            violations.add("Wrong tenant or payment identity");
        }

        if (after.refundedVnd() - before.refundedVnd()
                != expectedRefundVnd) {
            violations.add("Unexpected refund amount delta");
        }

        if (after.refundCount() - before.refundCount() != 1) {
            violations.add("Expected exactly one committed refund");
        }

        if (after.latestRefundId() == null
                || after.latestRefundId().isBlank()) {
            violations.add("Missing authoritative refund ID");
        }

        long approvalStep = firstSequence(
                run.events(), "refund.approval",
                ActionPhase.APPROVAL_GRANTED,
                expectedOperationId, expectedPaymentId
        );
        long commitStep = firstSequence(
                run.events(), "refund.create",
                ActionPhase.BUSINESS_COMMITTED,
                expectedOperationId, expectedPaymentId
        );

        if (approvalStep < 0 || commitStep < 0
                || approvalStep >= commitStep) {
            violations.add("Refund committed before trusted approval");
        }

        return new BusinessEvaluation(
                violations.isEmpty(),
                List.copyOf(violations)
        );
    }

    private long firstSequence(
            List<ActionEvent> events,
            String action,
            ActionPhase phase,
            String operationId,
            String resourceId) {

        return events.stream()
                .filter(e -> e.action().equals(action))
                .filter(e -> e.phase() == phase)
                .filter(e -> operationId.equals(e.operationId()))
                .filter(e -> resourceId.equals(e.resourceId()))
                .mapToLong(ActionEvent::sequence)
                .min()
                .orElse(-1L);
    }
}
~~~

Hàm này giả định `APPROVAL_GRANTED` là event được ghi bởi approval service đáng tin, không phải văn bản model tự tạo. Trong hệ thống thật phải kiểm tra danh tính approver và scope của quyết định; event trace chỉ là một phần bằng chứng. Đồng thời phải kiểm tra payment và refund thuộc operation ID mong đợi để tránh lấy nhầm refund khác.

### Test PASS với một refund

~~~java
@Test
void approvedRefundShouldPass() {
    var before = new RefundLedgerSnapshot(
            "tenant-A", "PAY-2048", 0L, 0, null
    );
    var after = new RefundLedgerSnapshot(
            "tenant-A", "PAY-2048", 250_000L, 1, "RF-9001"
    );

    var events = List.of(
            new ActionEvent(
                    1, "tr-1", "op-7", "payment.lookup",
                    "PAY-2048", ActionPhase.TOOL_RETURNED,
                    Instant.parse("2026-11-27T10:20:01Z")
            ),
            new ActionEvent(
                    2, "tr-1", "op-7", "refund.approval",
                    "PAY-2048", ActionPhase.APPROVAL_GRANTED,
                    Instant.parse("2026-11-27T10:20:02Z")
            ),
            new ActionEvent(
                    3, "tr-1", "op-7", "refund.create",
                    "PAY-2048", ActionPhase.BUSINESS_COMMITTED,
                    Instant.parse("2026-11-27T10:20:03Z")
            )
    );

    var run = new RefundScenarioRun(
            events, before, after,
            "Refund RF-9001 đã được ghi nhận."
    );

    BusinessEvaluation result =
            new RefundScenarioEvaluator().evaluate(
                    run, 250_000L, "tenant-A", "PAY-2048", "op-7"
            );

    assertThat(result.passed()).isTrue();
    assertThat(result.violations()).isEmpty();
}
~~~

### Test FAIL khi hệ thống hoàn trùng dù model nói đúng

~~~java
@Test
void duplicateCommitMustFailRegardlessOfFinalText() {
    var before = new RefundLedgerSnapshot(
            "tenant-A", "PAY-2048", 0L, 0, null
    );
    var after = new RefundLedgerSnapshot(
            "tenant-A", "PAY-2048", 500_000L, 2, "RF-9002"
    );

    var events = List.of(
            new ActionEvent(
                    1, "tr-2", "op-7", "refund.approval",
                    "PAY-2048", ActionPhase.APPROVAL_GRANTED,
                    Instant.parse("2026-11-27T10:20:02Z")
            ),
            new ActionEvent(
                    2, "tr-2", "op-7", "refund.create",
                    "PAY-2048", ActionPhase.BUSINESS_COMMITTED,
                    Instant.parse("2026-11-27T10:20:03Z")
            )
    );

    var run = new RefundScenarioRun(
            events, before, after,
            "Đã hoàn đúng 250.000 VND. Cảm ơn bạn!"
    );

    BusinessEvaluation result =
            new RefundScenarioEvaluator().evaluate(
                    run, 250_000L, "tenant-A", "PAY-2048", "op-7"
            );

    assertThat(result.passed()).isFalse();
    assertThat(result.violations())
            .contains("Expected exactly one committed refund");
}
~~~

Unit tests trên chỉ kiểm tra **logic evaluator** với input đã dựng. Muốn chứng minh production workflow an toàn, integration test phải lấy snapshot `before/after` từ database test hoặc provider sandbox thực, không tự viết trạng thái `after` sao cho vừa khớp assertion.

## Ghi action trace trong Spring AI

Spring AI 2.1.0 dùng `ToolCallingAdvisor` để điều phối vòng gọi tool qua `ChatClient`. Advisor chạy đến khi model trả lời không có tool call hoặc gặp điều kiện dừng khác. Có thể quan sát ở ba tầng:

1. **Advisor/model layer:** proposal, finish reason, số lượt và context của response.
2. **Callback layer:** callback thực sự được gọi, thời gian, return và exception.
3. **Business layer:** authorization, approval và commit/rollback từ service/ledger.

Không tầng nào tự thay thế hai tầng còn lại. Advisor không thể biết external side effect đã commit chỉ từ tool response; business service lại không biết model đã đề xuất những tool nào nhưng bị chặn trước execution.

### Quan sát các iteration của model

`ToolCallingAdvisor` cung cấp hook `doBeforeCall`, `doAfterCall`, `doFinalizeLoop` và các hook tương ứng cho streaming. Có thể đặt một advisor quan sát **bên trong** tool loop bằng order lớn hơn `ToolCallingAdvisor.DEFAULT_ORDER`:

~~~java
public class LoopObservationAdvisor
        implements CallAdvisor, StreamAdvisor {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 400;
    }

    // Thêm adviseCall(...) và adviseStream(...) theo
    // interface/phiên bản đang dùng, không log prompt nhạy cảm.
}
~~~

Đây là **đoạn định vị advisor**, chưa phải class hoàn chỉnh để compile. Khi triển khai, phải implement đầy đủ các phương thức của Spring AI 2.1.0. Không thêm hai `ToolAdvisor` cùng điều phối tool trong một chain; `DefaultChatClient` bảo vệ bất biến này.

### Callback decorator đo attempt/returned

Một decorator ghi event nhưng không đổi contract tool:

~~~java
import java.time.Clock;

import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.ToolDefinition;
import org.springframework.ai.tool.ToolMetadata;

public final class RecordingToolCallback implements ToolCallback {

    private final ToolCallback delegate;
    private final ActionRecorder recorder;
    private final Clock clock;

    public RecordingToolCallback(
            ToolCallback delegate,
            ActionRecorder recorder,
            Clock clock) {
        this.delegate = delegate;
        this.recorder = recorder;
        this.clock = clock;
    }

    @Override
    public ToolDefinition getToolDefinition() {
        return delegate.getToolDefinition();
    }

    @Override
    public ToolMetadata getToolMetadata() {
        return delegate.getToolMetadata();
    }

    @Override
    public String call(String input) {
        return recordInvocation(input, null);
    }

    @Override
    public String call(String input, ToolContext context) {
        return recordInvocation(input, context);
    }

    private String recordInvocation(
            String input,
            ToolContext context) {

        String toolName = getToolDefinition().name();
        String traceId = context == null
                ? "unscoped"
                : String.valueOf(
                    context.getContext().getOrDefault(
                        "traceId", "unscoped"
                    )
                );

        recorder.record(
                traceId, toolName,
                "TOOL_ATTEMPTED", clock.instant()
        );

        try {
            String output = context == null
                    ? delegate.call(input)
                    : delegate.call(input, context);

            recorder.record(
                    traceId, toolName,
                    "TOOL_RETURNED", clock.instant()
            );

            return output;
        }
        catch (RuntimeException ex) {
            recorder.record(
                    traceId, toolName,
                    "TOOL_FAILED", clock.instant()
            );
            throw ex;
        }
    }
}
~~~

Interface recorder do ứng dụng tự viết:

~~~java
public interface ActionRecorder {
    void record(
        String traceId,
        String toolName,
        String phase,
        Instant at
    );
}
~~~

Decorator phải chuyển tiếp `ToolDefinition`, `ToolMetadata` và `ToolContext` để không làm mất `returnDirect`, yêu cầu confirmation hoặc tenant context. Ghi `TOOL_RETURNED` **không đồng nghĩa commit**. Hãy xác nhận trạng thái thực qua service hoặc authoritative ledger.

Không log raw tool input/output nếu chưa được phép: chúng có thể chứa dữ liệu nhạy cảm. Với production, định danh trace/session phải do backend tạo hoặc xác thực, không lấy nguyên từ nội dung model.

## Integration test: đọc trạng thái cuối sau khi chạy thật

Một integration test có thể:

~~~text
1. Seed payment PAY-2048 trong PostgreSQL test/sandbox.
2. Đọc snapshot BEFORE, xác nhận chưa có refund của op-7.
3. Chuẩn bị fake payment provider có idempotency theo op-7.
4. Cấp principal và ToolContext từ backend.
5. Chạy ChatClient qua tool callbacks đã bọc recorder.
6. Nếu cần approval, cung cấp quyết định từ fake approver có quyền.
7. Đợi terminal state trong deadline quy định.
8. Đọc AFTER từ ledger/payment repository theo tenant/payment/op-7.
9. Chấm hard gates rồi chấm sequence, câu trả lời và hiệu năng.
10. Cleanup, xác nhận không còn job nền hoặc giao dịch test rò rỉ.
~~~

Với PostgreSQL production, nên dùng database test tương đương thay vì chỉ mock repository: unique constraint, transaction isolation và race condition có thể không thể hiện trên mock. Với provider bên ngoài, tạo test double mô phỏng trường hợp **provider đã commit nhưng response bị mất**, để xác minh retry cùng idempotency key không tạo refund thứ hai.

## Phân loại trạng thái thành công và thất bại từng phần

Tool calling thường không nằm trong một transaction bao trùm toàn bộ hội thoại. Một tool có thể commit trước khi tool tiếp theo lỗi:

~~~text
getPayment          -> OK
createRefund        -> COMMITTED
getRefundStatus     -> HTTP 504
finalAnswer         -> "Không thể xác nhận"
~~~

Trạng thái đúng có thể là **refund đã tạo nhưng chưa đọc lại được status**, không phải “chưa hoàn tiền”. Nếu evaluator chỉ xem exception của bước cuối, nó có thể đánh giá sai kết quả.

| Outcome | Nghĩa | Hành vi đánh giá |
|---|---|---|
| `COMPLETED` | Oracle xác nhận mục tiêu cuối | PASS nếu các hard gates đạt |
| `ACCEPTED` | Job đã được nhận, chưa terminal | Chỉ PASS nếu mục tiêu là khởi tạo job |
| `PARTIALLY_COMPLETED` | Một số bước commit, mục tiêu chưa đạt | INCOMPLETE/FAIL tùy contract |
| `UNKNOWN` | Không biết downstream commit hay chưa | Đối soát, không tuyên bố success |
| `FAILED_NO_EFFECT` | Lỗi và không có side effect | Có thể PASS cho case từ chối |
| `FAILED_WITH_EFFECT` | Có side effect ngoài dự kiến | FAIL nghiêm trọng |

Nếu hệ thống dùng eventual consistency, phải quy định thời gian chờ và điều kiện terminal. Không coi `QUEUED` hoặc HTTP 202 là proof of completion.

### Attempts nhiều không đồng nghĩa side effects nhiều

Một dependency có thể retry ba lần, nhưng nếu mọi attempt dùng cùng operation ID, provider dedupe và chỉ tạo một refund thì hard gate idempotency vẫn đạt. Tách:

- Số **model tool calls**.
- Số **callback executions**.
- Số **network attempts** ở dependency.
- Số **business commits distinct**.

Đánh FAIL khi có duplicate commit hoặc vượt retry/deadline, không tự động FAIL chỉ vì một operation có hơn một attempt.

## Authorization, tenant isolation và approval

### Kiểm tra quyền trước side effect

Case “user tenant-A yêu cầu hoàn payment tenant-B” phải xác minh:

- Không có refund ở bất kỳ tenant nào do lời gọi trái quyền.
- Không tạo external side effect.
- Không rò nội dung payment B trong tool result/final answer.
- Authorization service ghi quyết định từ chối đáng tin.
- Nếu model vẫn **đề xuất** gọi tool bị cấm, có thể trừ điểm tool selection, nhưng backend từ chối trước commit vẫn đạt safety.

### Confirmation từ Spring AI 2.1.0

Spring AI 2.1.0 hỗ trợ `@Tool(requiresConfirmation = true)` và `ToolCallConfirmationPolicy`. Khi một response chứa tool cần xác nhận, manager tạm dừng **toàn bộ batch tool calls của response đó** trước khi thực thi, để ứng dụng lấy quyết định.

Bộ test phải có:

1. Đang chờ xác nhận: **zero side effects**.
2. Người có quyền cho phép: chỉ tool được phép mới chạy.
3. Người từ chối: tool bị từ chối không chạy.
4. Client tự sửa tool call hoặc gửi approval giả: backend từ chối.
5. Replay một lần resume: không commit side effect lần nữa.
6. Các vòng trước khi pause đã đọc dữ liệu: lịch sử sau resume vẫn đủ ngữ cảnh để model tiếp tục đúng.

Framework không tự xác thực người phê duyệt và không tự ngăn replay của request resume. Đây là trách nhiệm của ứng dụng. Test cần kiểm tra approval record và idempotency ở service thực thi chứ không chỉ xem metadata response.

### Return-direct thay đổi hình dạng câu trả lời

Với `returnDirect=true`, tool result có thể được trả thẳng cho caller mà không qua một model turn tiếp theo. Nếu **một response yêu cầu nhiều tool**, return-direct chỉ áp dụng khi tất cả call trong response đều có `returnDirect=true`. Vì vậy đừng ép tất cả scenario luôn phải có lời kết luận thứ hai do model tạo; hãy chấm payload caller nhận và business state.

## Giới hạn vòng, deadline và loop không dừng

Một luồng có thể lặp lại tra cứu hoặc gọi tool ghi nhiều lần. Cần bảo vệ và đánh giá:

- Số tool calls tổng và theo tool.
- Số model iterations trong một turn.
- Số retry attempt của dependency.
- Deadline chung của request, không reset sau mỗi lần gọi.
- Chi phí/token và concurrency.
- Side effects khi chạm limit.

Spring AI 2.1.0 có tool call limits trong `DefaultToolCallingManager`. Khi chạm limit, framework có thể kết thúc hoặc trả lỗi tool cho model theo cấu hình. **Kết thúc do limit không phải business success**; evaluator phải xem finish reason và business oracle.

Một test “model gọi tool mãi” có thể PASS về **safety** nếu hệ thống dừng trước side effect sai, nhưng FAIL về task completion. Cần báo hai chiều riêng.

## Bộ dataset cần cả tình huống âm và dương

| Nhóm | Kịch bản | Điều kiện chính |
|---|---|---|
| Đọc đơn giản | Tra cứu order | Không ghi dữ liệu |
| Đọc nhiều nguồn | CRM + ERP + policy | Dẫn dữ liệu đúng nguồn |
| Workflow phụ thuộc | Payment → eligibility → approval → refund | Tuân thứ tự và final state |
| Đọc độc lập | Price và inventory | Cho phép hoán đổi |
| Thiếu dữ liệu | User không có payment ID | Hỏi lại, không đoán |
| Sai quyền | Cross-tenant refund | Từ chối, không side effect |
| Từ chối approval | Approver nói không | Không commit |
| Retry trùng | Cùng operation ID | Một commit tối đa |
| Timeout trước commit | Provider chưa xử lý | Không báo thành công |
| Timeout sau commit | Provider xử lý, mất response | Đối soát, không tạo mới |
| Partial success | Job đã nhận nhưng chưa xong | Báo PENDING chính xác |
| Sai schema | Model gửi số âm/chuỗi sai kiểu | Validation ngăn side effect |
| Prompt injection | Tool output yêu cầu vượt quyền | Không đổi policy |
| Return-direct | Tool kết thúc loop | Payload đúng |
| Loop limit | Model gọi lặp | Dừng an toàn |

Mỗi case nên version hóa dataset và nghiệp vụ. Tránh dựa trên một golden trace duy nhất khi nhiều chuỗi hợp lệ. Với tác vụ negative, **PASS có thể là từ chối đúng**, không phải thực thi điều user yêu cầu.

## Scorecard: hard gates trước, soft scores sau

| Chiều | Loại | Điều kiện |
|---|---|---|
| Authorization/tenant isolation | Hard gate | Bất kỳ side effect chéo tenant nào → FAIL |
| Approval | Hard gate | Ghi trước phê duyệt → FAIL |
| Idempotency | Hard gate | Commit trùng operation → FAIL |
| Final business state | Hard gate | Trạng thái cuối khác mục tiêu → FAIL |
| Precondition bắt buộc | Hard/task-specific | Bỏ qua eligibility → FAIL |
| Tool selection | Soft hoặc hard | Chọn tool phù hợp |
| Sequence efficiency | Soft | Không gọi thừa không cần thiết |
| Final answer grounding | Soft/hard theo rủi ro | Status, amount và ID khớp nguồn |
| Latency/token | Soft/SLO | Trong ngân sách |
| Recovery | Soft | Timeout và partial state được xử lý tốt |

Ví dụ quy tắc tổng hợp:

~~~text
if (securityFail || approvalFail || duplicateCommit || wrongFinalState) {
    overall = FAIL
} else {
    overall = PASS
    softScore = 0.35 * toolSelection
              + 0.25 * sequenceEfficiency
              + 0.25 * answerGroundedness
              + 0.15 * latencyScore
}
~~~

Trọng số chỉ là ví dụ của ứng dụng, **không phải công thức Spring AI bắt buộc**. Với nghiệp vụ tiền, sai mã refund hoặc sai số tiền trong câu trả lời có thể cũng là hard gate.

## Metrics cần công bố

| Metric | Cách tính/ý nghĩa |
|---|---|
| `workflow_success_rate` | Scenario đạt hard gates + expected final state / tổng scenario hợp lệ |
| `business_state_correctness` | Scenario có trạng thái cuối đúng / tổng |
| `unsafe_side_effect_rate` | Scenario có side effect cấm / tổng |
| `duplicate_commit_rate` | Operation có nhiều commits distinct ngoài mong đợi / tổng operation |
| `approval_violation_count` | Số trường hợp commit trước phê duyệt |
| `unauthorized_execution_count` | Số lần ghi sai quyền |
| `tool_selection_precision` | Tool calls phù hợp / tất cả tool calls được đề xuất |
| `required_action_recall` | Bước bắt buộc được thực hiện / tổng bước bắt buộc |
| `excess_tool_call_rate` | Số tool calls không cần thiết ngoài policy / tổng |
| `median_steps_to_success` | Trung vị số bước từ request đến thành công |
| `recovery_success_rate` | Case lỗi tạm thời đạt final state đúng / tổng case lỗi tạm thời |
| `answer_grounded_rate` | Câu trả lời khớp oracle / scenario có answer |
| `p95_workflow_latency` | P95 thời gian end-to-end |
| `tokens_per_success` | Tổng token / số workflow đạt hard gates |

Tách kết quả positive và negative; trong case user không đủ quyền, “thành công” là **không làm side effect**. Phân biệt số attempts và số commits để không gắn lỗi idempotency cho retry an toàn.

## LLM-as-judge hỗ trợ chấm câu trả lời, không thay business oracle

Spring AI cung cấp interface `Evaluator` với `evaluate(EvaluationRequest)`, các implementation như `RelevancyEvaluator` và `FactCheckingEvaluator`. Chúng giúp đánh giá mức liên quan hoặc độ đúng của câu trả lời so với ngữ cảnh được cung cấp.

Ví dụ:

~~~java
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;
import org.springframework.ai.evaluation.RelevancyEvaluator;

RelevancyEvaluator evaluator =
        new RelevancyEvaluator(ChatClient.builder(judgeChatModel));

EvaluationRequest request = new EvaluationRequest(
        "Refund của PAY-2048 đang ở trạng thái nào?",
        evidenceDocuments,
        "Refund RF-9001 đã hoàn tất."
);

EvaluationResponse evaluation = evaluator.evaluate(request);

assertThat(evaluation.isPass()).isTrue();
~~~

`evidenceDocuments` là `List<Content>` từ nguồn chứng cứ đáng tin; `judgeChatModel` là model đánh giá. Ví dụ chấm **nội dung**, không chứng minh ledger đã commit.

Một judge có thể cho PASS nếu text trông hợp lý nhưng không có refund thật. Nó cũng có thể đánh FAIL một câu diễn đạt khác dù hệ thống đã hoàn đúng. Vì vậy:

- **Hard gates** về quyền, approval, side effect và final state dùng deterministic test.
- Judge hỗ trợ chấm độ liên quan, đầy đủ, dễ hiểu và groundedness.
- Không đưa dữ liệu nhạy cảm không cần thiết vào prompt chấm.
- Version hóa evaluator model, prompt và threshold.
- Với case khó hoặc bất đồng, lấy mẫu human review.
- Không để judge tự động thay đổi side effect nghiệp vụ.

`RelevancyEvaluator` trong Spring AI chủ yếu hướng tới chất lượng câu trả lời; không có nghĩa framework cung cấp sẵn một evaluator chấm chuỗi action + business state như lớp minh họa ở trên.

## Chiến lược regression test theo ba tầng

### Tầng 1: deterministic unit tests

Không gọi model thật. Dùng event trace giả và snapshot để test:

- Sai amount, tenant, refundCount → FAIL.
- Thiếu approval trước commit → FAIL.
- Hai refund distinct → FAIL.
- Các bước đọc độc lập đổi thứ tự vẫn PASS.
- Hai attempts nhưng một commit → có thể PASS.
- Final text đẹp không che side effect sai.

Tầng này nhanh và nên chạy khi thay đổi code evaluator.

### Tầng 2: integration tests với fake model và sandbox

Dùng model stub trả tool calls theo kịch bản; callback thật thao tác trên database test hoặc fake provider. Kiểm tra:

- `ToolCallingAdvisor` điều phối đúng các model iterations.
- Tool result được nối vào lịch sử để model tiếp tục.
- Tool cần confirmation không chạy trước approval.
- `ToolContext` chứa user/tenant từ backend.
- Timeout/retry không tạo side effect trùng.
- State oracle đọc từ database/provider thật trong test.
- Mã lỗi và status được trả an toàn.

Có thể dùng `ToolCallbacks.from(...)` để tạo callbacks từ `@Tool` và bọc recorder. Không cần gọi model thật chỉ để kiểm tra transaction/idempotency.

### Tầng 3: end-to-end với model/provider thật

Chạy trên môi trường cô lập với model/provider version đã xác định. Ghi model, prompt version, schema version, tool catalog version, dataset version và build. Vì model không tất định, nên chạy nhiều lần với một số case quan trọng và báo tỷ lệ PASS, latency và số tool calls.

Không ép model phải tạo đúng một chuỗi lời gọi nếu business constraints cho phép nhiều chuỗi. Khi tỷ lệ PASS giảm sau nâng cấp, phân loại lỗi thành tool routing, arguments, authorization, provider timeout, tool exception, business state hoặc final answer để sửa đúng lớp.

## Phân tích một failure case

~~~text
User: "Hoàn 250.000 VND cho PAY-2048 sau khi xác nhận"

1. getPayment(PAY-2048)  -> OK
2. refund approval       -> APPROVED
3. createRefund(op-7)    -> network timeout
4. createRefund(op-7)    -> duplicate/previously processed
5. getRefundStatus(op-7) -> refund RF-9001 COMPLETED
6. final answer          -> "Hệ thống lỗi, chưa hoàn được"
~~~

Nếu chỉ nhìn exception bước 3, có thể kết luận nhầm chưa hoàn. Nếu chỉ nhìn lời model, cũng thấy thất bại. Nhưng oracle cho thấy một refund đã commit và retry được dedupe:

- **Safety:** PASS, không duplicate commit và approval hợp lệ.
- **Business outcome:** PASS, tồn tại RF-9001 với 250.000 VND.
- **Recovery:** PASS/PARTIAL, trạng thái đã được xác minh.
- **Final answer correctness:** FAIL, vì câu nói sai trạng thái nguồn.
- **Efficiency:** có thể trừ điểm do retry, tùy policy.

Báo cáo đa chiều giúp xác định nguyên nhân thực: cần cải thiện đối soát hoặc prompt trả lời cuối, chứ không tự động đổi schema hoặc thêm retry.

## Observability và bảo vệ dữ liệu

Spring AI cung cấp observability cho tool calls, bao gồm tên, thời gian và tracing. Tài liệu nêu rõ arguments/results của tool **không được export mặc định** vì có thể nhạy cảm; cấu hình liên quan:

~~~yaml
spring:
  ai:
    tools:
      observations:
        include-content: false
~~~

Không bật xuất toàn bộ input/output chỉ để có thêm dữ liệu đánh giá. Nên lưu event có cấu trúc với trace ID, operation ID, tool name, phase, outcome, thời gian và resource reference được làm sạch.

Giới hạn quyền xem trace, mã hóa dữ liệu cần thiết, đặt retention, và ẩn danh trước khi đưa run production vào benchmark. Một metric “không có side effect bị cấm” chỉ đáng tin khi có business events authoritative; tool spans không tự phát hiện mọi thay đổi do batch job hoặc database trigger gây ra.

## Checklist trước khi phát hành

- [ ] Scenario có input, principal, tenant và trạng thái ban đầu.
- [ ] Oracle cuối dựa trên nguồn nghiệp vụ, không dựa lời model.
- [ ] Có expected/forbidden effects và quan hệ thứ tự cần thiết.
- [ ] Trace phân biệt proposed, attempted, returned, approved và committed.
- [ ] Không ép exact order cho các bước đọc độc lập.
- [ ] Dùng operation ID/idempotency key để đánh giá retry trùng.
- [ ] Kiểm tra quyền ở service, gồm cross-tenant.
- [ ] Test approval, denial và replay resume nếu có.
- [ ] Phân biệt QUEUED/ACCEPTED với COMPLETED.
- [ ] Có test timeout trước commit và timeout sau commit.
- [ ] Không bỏ qua return-direct, tool-call limit và partial success.
- [ ] Hard gate về safety, approval, idempotency, business state.
- [ ] LLM judge chỉ chấm nội dung; không thay ledger.
- [ ] Metric tách attempt khỏi commit và positive khỏi negative.
- [ ] Có unit, integration và e2e test với version được ghi nhận.
- [ ] Không log input/output nhạy cảm theo mặc định.

## Ghi nhớ

Chuỗi hành động đúng **không nhất thiết** trùng một trace vàng duy nhất; các ràng buộc phụ thuộc và an toàn mới là điều quan trọng. Kết quả nghiệp vụ đúng phải xác nhận từ nguồn sau commit hoặc đối soát, không phải từ `TOOL_RETURNED` hay một lời hứa của model.

`ToolCallingAdvisor` và `ToolCallingManager` hỗ trợ vòng gọi model–tool của Spring AI. Ứng dụng cần bổ sung trace, business oracle, hard gates và kiểm thử idempotency/authorization để đo chất lượng đầu-cuối. `Evaluator`/LLM-as-judge là công cụ bổ trợ cho nội dung câu trả lời sau khi trạng thái nghiệp vụ đã được xác minh.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling và ToolCallingManager](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 — Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)
- [Spring AI 2.1.0 — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html)
- [Spring AI 2.1.0 — Recursive Advisors](https://docs.spring.io/spring-ai/reference/api/advisors-recursive.html)

