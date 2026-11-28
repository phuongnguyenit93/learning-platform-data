# Chất lượng khi vận hành: Đưa lỗi đã xác nhận trở lại bộ dữ liệu kiểm tra hồi quy

## 1. Vì sao lỗi đã sửa vẫn có thể quay lại?

Một lỗi trong ứng dụng Spring AI có thể được sửa bằng cách cập nhật prompt, thay model, điều chỉnh retrieval, đổi tool schema hoặc sửa logic ứng dụng. Nhưng nếu lỗi chỉ được xử lý trong incident ticket mà không trở thành regression case, lần thay đổi tiếp theo có thể làm nó xuất hiện trở lại.

Ví dụ:

- Một prompt mới khiến assistant khẳng định ngày giao hàng dù retrieval context không có bằng chứng.
- Một thay đổi retriever làm mất document chứa điều kiện hoàn tiền.
- Một model mới chọn tool tra cứu sai tenant.
- Một tool timeout khiến assistant nói rằng giao dịch đã hoàn tất dù backend chưa xác nhận.
- Một advisor mới làm conversation memory bị trộn giữa hai phiên.
- Một response trước đây tuân thủ JSON schema nhưng sau khi đổi prompt lại thêm lời giải thích ngoài JSON.
- Một lỗi prompt injection đã được khắc phục nhưng tài liệu độc hại tương tự lại khiến model gọi tool có side effect.

Sửa code hoặc prompt chỉ xử lý phiên bản hiện tại. Regression test lưu lại điều kiện đã gây lỗi, hành vi mong đợi và bằng chứng để CI có thể kiểm tra ở các lần thay đổi sau.

**Mục tiêu:** mỗi lỗi đã xác nhận cần trở thành một case có thể tái hiện, có assertion phù hợp với loại lỗi, có provenance và được chạy lại trong pipeline kiểm thử.

Bài học thuộc chương **Chất lượng khi vận hành** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời theo dõi metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua các phiên bản prompt, model và pipeline.

Sau bài học, bạn có thể:

- Phân biệt incident, confirmed defect, regression case và golden benchmark.
- Chuyển lỗi production thành một test case có input, context, expected behavior và evidence.
- Thu thập snapshot đủ để tái hiện lỗi prompt, model, RAG, tool hoặc memory.
- Tối giản case mà vẫn giữ nguyên điều kiện gây lỗi.
- Chọn assertion theo dimension thay vì phụ thuộc exact string không cần thiết.
- Tạo dataset hồi quy có version, provenance, severity và owner.
- Viết test harness cho Spring AI ChatClient/ChatModel ở application layer.
- Kiểm thử retrieval, generation, tool calling, memory và output schema bằng fixture an toàn.
- Xử lý flaky tests, evaluator failures và model nondeterminism.
- Tích hợp regression suite vào CI, release gate và quy trình theo dõi production.

## 2. Phân biệt incident, defect, regression case và golden benchmark

Các khái niệm này liên quan nhưng có mục đích khác nhau.

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Incident | Sự kiện vận hành cần điều tra | Assistant trả lời sai trạng thái đơn hàng |
| Confirmed defect | Nguyên nhân hoặc hành vi sai đã được xác nhận | Prompt cho phép suy đoán khi context thiếu |
| Regression case | Test tái hiện defect và kiểm tra hành vi đã sửa | Khi thiếu delivery evidence, assistant phải abstain |
| Golden benchmark | Tập case có nhãn tin cậy để đo chất lượng theo rubric | Dataset relevance/groundedness đã adjudicate |
| Smoke test | Kiểm tra nhanh hệ thống có hoạt động cơ bản | ChatClient trả response và health endpoint hoạt động |
| Production monitor | Phát hiện lỗi hoặc drift sau deploy | Tỷ lệ unsupported claims tăng theo model revision |

Một incident có thể chưa có root cause. Chỉ sau khi xác nhận hành vi sai và có đủ thông tin để tạo test, mới promote thành confirmed regression case.

Regression case thường có expected behavior cụ thể cho một defect. Golden benchmark có thể rộng hơn, đại diện cho nhiều task families và được dùng để so sánh chất lượng giữa các phiên bản. Một regression case đã được xác minh có thể được đưa vào golden regression set, nhưng không nên mặc định mọi case đều thuộc held-out benchmark.

### 2.1. Một lỗi cần được lưu ở mức nào?

Một defect có thể được kiểm tra ở nhiều lớp:

- **Unit regression:** logic routing, validation hoặc policy đã sửa không bị phá vỡ.
- **Contract regression:** tool schema, request/response mapping và integration contract vẫn đúng.
- **Retrieval regression:** retriever vẫn trả các evidence cần thiết cho query.
- **Generation regression:** model/prompt không lặp lại hành vi sai khi dùng cùng context snapshot.
- **End-to-end regression:** toàn bộ luồng từ user input đến tool result và final answer hoạt động đúng.
- **Operational regression:** latency, token usage, cost và error rate không vượt guardrail.

Chọn lớp thấp nhất có thể bắt được nguyên nhân, sau đó bổ sung test tích hợp nếu lỗi chỉ xuất hiện khi các thành phần phối hợp.

## 3. Vòng đời từ incident đến regression dataset

Một workflow có thể chia thành các bước sau:

~~~mermaid
flowchart TD
    I["Production incident / feedback"] --> C["Confirm defect and impact"]
    C --> R{"Root cause understood?"}
    R -->|No| D["Collect traces, snapshots, evidence"]
    D --> C
    R -->|Yes| M["Minimize reproducible case"]
    M --> O["Define expected behavior and oracle"]
    O --> T["Create regression case"]
    T --> V["Run against current fixed version"]
    V -->|Fail| F["Fix implementation / prompt / config"]
    F --> V
    V -->|Pass| P["Review and version dataset"]
    P --> CI["Run in CI and release gates"]
    CI --> MON["Monitor production recurrence"]
    MON -->|New evidence| I
~~~

Một state machine đơn giản:

| Trạng thái | Ý nghĩa | Điều kiện chuyển tiếp |
| --- | --- | --- |
| DETECTED | Có report hoặc alert | Tạo incident reference |
| INVESTIGATING | Đang thu thập bằng chứng | Có trace, input và environment |
| CONFIRMED | Hành vi sai đã được xác nhận | Root cause hoặc failure condition đủ rõ |
| REPRODUCIBLE | Có case tái hiện | Chạy lại cho thấy lỗi với điều kiện xác định |
| MINIMIZED | Đã loại dữ liệu không cần thiết | Các yếu tố gây lỗi vẫn còn |
| ASSERTED | Expected behavior và oracle được định nghĩa | Assertion được owner chấp nhận |
| REGRESSION_READY | Test chạy được trên fixed version | Test thất bại với bug reproduction và pass sau fix |
| PUBLISHED | Case được đưa vào dataset version | Review, provenance và split hoàn tất |
| MONITORED | Case được dùng trong CI/production review | Có owner và lịch sử kết quả |
| DEPRECATED | Case không còn áp dụng | Có reason và replacement nếu cần |

Không tạo case chỉ để tăng số lượng regression tests. Một case cần có defect reference, expected behavior và lý do tại sao nó bảo vệ một rủi ro thực tế.

## 4. Xác định điều kiện để một lỗi trở thành regression case

Trước khi tạo test, cần trả lời:

1. Hành vi sai cụ thể là gì?
2. User input hoặc interaction nào làm lỗi xuất hiện?
3. Prompt, model, parameters, advisor, retriever và tool versions nào đã chạy?
4. Context/evidence thực tế tại thời điểm lỗi là gì?
5. Kết quả thực tế khác expected behavior ở điểm nào?
6. Có thể tái hiện lỗi bằng snapshot hoặc fixture không?
7. Assertion nào chứng minh lỗi đã được sửa?
8. Test có thể chạy an toàn và ổn định trong CI không?
9. Case có chứa PII, secrets hoặc dữ liệu tenant cần bảo vệ không?
10. Owner nào chịu trách nhiệm khi case fail hoặc cần cập nhật?

### 4.1. Không nhầm symptom với root cause

Ví dụ: câu trả lời thiếu citation có thể xuất phát từ:

- Retriever không lấy đúng document.
- Context bị cắt do token budget.
- Prompt không yêu cầu citation.
- Model tạo citation nhưng format parser loại bỏ.
- Citation mapper dùng nhầm document IDs.
- Evaluation code đọc sai field response.

Nếu chỉ thêm một expected citation vào output mà không xác định lớp lỗi, test có thể che khuất nguyên nhân thật. Tách regression ở retrieval, prompt/generation và citation mapping khi mỗi lớp có contract riêng.

### 4.2. Mức độ ưu tiên

| Severity | Ví dụ | Regression policy |
| --- | --- | --- |
| Critical | Cross-tenant data leak, unauthorized tool side effect, unsafe disclosure | Bắt buộc gate release; có thể yêu cầu nhiều lớp test |
| High | Hallucinated business fact, sai quyết định nghiệp vụ, tool action sai | Bắt buộc test tự động và review evidence |
| Medium | Thiếu bước quan trọng, citation sai, output schema không ổn định | Regression suite theo task family |
| Low | Formatting hoặc wording ít ảnh hưởng | Smoke/quality suite phù hợp; tránh làm CI quá nhạy |

Severity dựa trên tác động và xác suất tái diễn theo policy của sản phẩm. Không hạ severity chỉ vì lỗi khó tái hiện.

## 5. Thu thập snapshot để tái hiện

LLM output phụ thuộc nhiều yếu tố. Chỉ lưu câu hỏi và câu trả lời thường không đủ.

Một reproduction snapshot có thể cần:

| Thành phần | Thông tin cần lưu |
| --- | --- |
| Interaction | User input, conversation turn, locale, task family |
| Conversation | Các messages cần thiết, memory state/version |
| Prompt | Template version, rendered variables, system/developer instructions được phép lưu |
| Model | Provider, requested/reported model, deployment revision |
| Parameters | Temperature, top-p, max tokens, seed nếu provider hỗ trợ |
| Advisor chain | Advisor names/order, retrieval augmentation config |
| Retrieval | Query đã dùng, document/chunk references, scores và thứ tự |
| Evidence | Snapshot content hoặc secure reference, source version, valid time |
| Tools | Tool names, schema version, arguments đã redaction, fixture result |
| Runtime | Application build, dependency/config versions, feature flags |
| Output | Raw response snapshot, structured response, finish reason |
| Evaluation | Rubric, evaluator model/prompt/version và verdict |
| Trace | Trace/span references, operation timing và error status |

### 5.1. Snapshot và live replay khác nhau

- **Snapshot replay:** dùng lại input, retrieved documents, tool results và config snapshot đã lưu. Mục tiêu là cô lập generation/prompt hoặc orchestration.
- **Live retrieval replay:** chạy lại retriever/index hiện tại. Mục tiêu là kiểm tra retrieval behavior sau thay đổi.
- **Live tool integration test:** gọi sandbox hoặc test service có dữ liệu riêng. Mục tiêu là kiểm tra contract và integration.
- **Production replay:** phát lại traffic đã redaction trong môi trường kiểm soát, với tool writes bị vô hiệu hóa hoặc giả lập.

Không gọi live production tools để tái hiện một bug nếu hành động có thể tạo side effect. Snapshot phải giữ cả version và thời điểm hiệu lực để tránh dùng trạng thái hiện tại thay thế dữ liệu lịch sử.

### 5.2. Không giả định model output sẽ giống hệt

Model provider có thể thay đổi backend, weights hoặc serving implementation mà không cung cấp seed determinism tuyệt đối. Temperature thấp không đảm bảo response byte-for-byte giống nhau.

Với lỗi phụ thuộc generation, lưu raw response ban đầu để forensic; regression test nên kiểm tra hành vi/claim/contract quan trọng. Exact match chỉ phù hợp với output thật sự deterministic như formatter, parser hoặc mapping code.

### 5.3. Bảo vệ dữ liệu trong snapshot

- Redact credentials, access tokens và secrets.
- Pseudonymize identifiers.
- Giữ tenant boundary.
- Chỉ lưu phần conversation cần để tái hiện lỗi.
- Lưu raw evidence trong secure store với retention có kiểm soát.
- Không đưa prompt/completion hoặc tool arguments nhạy cảm vào metric labels.
- Giữ hash/reference để audit mà không cần nhân bản raw content.
- Đánh dấu case không được dùng cho training hoặc mục đích ngoài evaluation nếu policy yêu cầu.

Redaction phải giữ cấu trúc và đặc điểm ngữ nghĩa cần thiết. Nếu thay mọi ID bằng một chuỗi chung làm mất quan hệ giữa các entities, case có thể không còn tái hiện được bug.

## 6. Tối giản case nhưng giữ nguyên nguyên nhân

Một production trace có thể chứa nhiều messages, documents và tool calls không liên quan. Case nhỏ hơn thường nhanh, dễ hiểu và ổn định hơn.

Quy trình minimization:

1. Giữ nguyên user input và các context elements đang nghi ngờ.
2. Loại bỏ messages trước đó nếu không ảnh hưởng tới lỗi.
3. Loại bỏ retrieved chunks không liên quan, từng bước một.
4. Thay dữ liệu nhạy cảm bằng fixture có cấu trúc tương đương.
5. Thay live tool bằng deterministic fake nếu lỗi không nằm ở tool provider.
6. Giữ nguyên prompt/model parameters cần thiết để tái hiện.
7. Chạy lại sau mỗi lần rút gọn.
8. Nếu lỗi biến mất, khôi phục phần tử vừa bỏ.
9. Ghi rõ minimal trigger và các assumptions còn lại.

### 6.1. Delta debugging

Có thể chia context thành nhóm và lần lượt loại từng nhóm để tìm phần tử cần thiết. Với tool flow, thử bỏ từng bước hoặc thay một tool result bằng fixture. Với conversation memory, bỏ từng message lịch sử nhưng giữ thứ tự và role.

Không tối giản bằng cách thay đổi đồng thời prompt, model và context; khi đó không biết yếu tố nào làm lỗi biến mất.

### 6.2. Minimal case không nhất thiết là case ngắn nhất

Nếu bug phụ thuộc thứ tự tool calls, temporal context hoặc hai tenant identities, việc rút gọn quá mức sẽ xóa mất điều kiện lỗi. Mục tiêu là bỏ phần không liên quan, không phải giảm số dòng bằng mọi giá.

## 7. Viết expected behavior và oracle

Một regression case cần có oracle: cách xác định kết quả đúng hoặc hành vi được chấp nhận.

| Loại lỗi | Assertion phù hợp |
| --- | --- |
| Unsupported factual claim | Claim không xuất hiện hoặc phải được đánh dấu chưa xác minh |
| Relevance regression | Response đáp ứng intent theo rubric |
| Missing evidence | Assistant abstain hoặc yêu cầu bổ sung dữ liệu |
| Wrong retrieval | Required document/chunk được retrieve hoặc recall đạt ngưỡng |
| Citation mapping | Citation trỏ tới đúng source/chunk |
| Tool selection | Chọn đúng tool hoặc không gọi tool |
| Tool arguments | Arguments tuân thủ schema và business constraints |
| Tool side effect | Không thực hiện action khi authorization/confirmation thiếu |
| Tool failure handling | Không tuyên bố success khi tool chưa xác nhận |
| Structured output | Response parse được và tuân thủ JSON schema |
| Prompt injection | Untrusted context không thay thế policy hoặc kích hoạt action trái phép |
| Memory isolation | Không lộ dữ liệu từ conversation/tenant khác |
| Latency/cost | Không vượt guardrail theo environment và operation |

### 7.1. Assertion theo dimension

Không dùng một boolean pass/fail để gộp nhiều lỗi. Có thể lưu các assertion riêng:

- RELEVANCE_MIN_SCORE
- CLAIM_MUST_BE_SUPPORTED
- MUST_ABSTAIN_WITHOUT_EVIDENCE
- CITATION_MUST_REFERENCE
- TOOL_MUST_BE_CALLED
- TOOL_MUST_NOT_BE_CALLED
- TOOL_ARGUMENT_SCHEMA
- NO_CROSS_TENANT_DATA
- JSON_SCHEMA_VALID
- LATENCY_BUDGET
- COST_BUDGET

Mỗi assertion cần có dimension, severity, evaluator/validator và expected result. Khi một test fail, báo rõ assertion nào fail và evidence nào chứng minh.

### 7.2. Exact match hay semantic assertion?

Dùng exact match khi:

- Output là deterministic formatter hoặc parser.
- Contract yêu cầu một literal value cụ thể.
- Test kiểm tra mapping ID hoặc enum.
- Có một đáp án chuẩn duy nhất theo source snapshot.

Dùng semantic assertion khi:

- Có nhiều cách diễn đạt đúng.
- Đang kiểm tra relevance, completeness hoặc groundedness.
- Cần xác minh một claim hoặc điều kiện.
- Câu trả lời có thể thay đổi theo model nhưng vẫn đúng.

LLM judge có thể hỗ trợ semantic evaluation nhưng phải được hiệu chuẩn. Với defect critical, ưu tiên deterministic oracle hoặc human-reviewed evidence; không để một judge chưa hiệu chuẩn là gate duy nhất.

### 7.3. Positive và negative assertions

Mỗi regression case nên kiểm tra cả điều phải xảy ra và điều bị cấm nếu phù hợp.

Ví dụ với order lookup:

- Phải gọi tool tra cứu trạng thái khi có quyền và đủ order reference.
- Không được gọi tool với tenant khác.
- Không được nói giao dịch hoàn tất khi tool trả timeout.
- Phải yêu cầu làm rõ khi thiếu order reference.

Chỉ kiểm tra output cuối có câu “đang xử lý” có thể bỏ sót tool call sai đã xảy ra trước đó.

## 8. Phân loại regression suite cho Spring AI

Một suite có thể chia theo thành phần để xác định lỗi ở đâu.

### 8.1. Prompt regression

Kiểm tra:

- System instructions vẫn giữ policy.
- Prompt variables được render đúng.
- Few-shot examples không làm lệch task.
- Advisor order không thay đổi ngoài dự kiến.
- Output format constraints vẫn được tuân thủ.
- Untrusted documents không ghi đè instructions.

### 8.2. Model regression

Kiểm tra:

- Requested/reported model đúng với release manifest.
- Response finish reason và token usage được ghi.
- Quality theo rubric không giảm quá margin.
- Model mới không làm tăng refusal sai hoặc unsupported claims.
- Latency, cost và timeout trong guardrails.

### 8.3. RAG regression

Tách retrieval và generation:

- Retrieval test: query → document/chunk IDs, rank, score, filter và metadata.
- Context assembly test: thứ tự, token budget, deduplication và truncation.
- Generation test: dùng pinned context snapshot để kiểm tra response.
- End-to-end test: retriever, advisor, model và citation mapping phối hợp.

Nếu test chỉ kiểm tra final answer, khó biết lỗi do retrieval hay generation.

### 8.4. Tool calling regression

Kiểm tra:

- Tool definition/name và schema.
- Tool selection.
- Arguments sau validation.
- Authorization và tenant scope.
- Idempotency và retry.
- Tool timeout/error mapping.
- Tool result được đưa vào model context.
- Final answer phản ánh đúng tool result.

Dùng fake/stub tools cho regression generation và sandbox service cho integration. Không để CI gọi tool có side effect production.

### 8.5. Memory/conversation regression

Kiểm tra:

- Message order và role.
- Conversation ID/session mapping.
- Memory retrieval.
- Summary truncation.
- Tenant/user isolation.
- Không dùng memory cũ sau khi conversation đã kết thúc nếu policy yêu cầu.

### 8.6. Observability và cost regression

Kiểm tra operation spans, error status, model usage, token/cost attribution và metric dimensions. Regression ở observability có thể làm mất khả năng phát hiện lỗi dù generation behavior vẫn đúng.

## 9. Dataset schema cho regression case

Một case nên giữ cả defect reference, input snapshot, environment, expected behavior và metadata của dataset.

~~~json
{
  "caseId": "reg-000184",
  "caseVersion": 2,
  "defect": {
    "incidentRef": "incident-opaque-17",
    "defectRef": "defect-opaque-42",
    "severity": "HIGH",
    "category": "RAG_GROUNDEDNESS",
    "rootCause": "Stale retrieval evidence was treated as current state"
  },
  "input": {
    "snapshotRef": "input-snapshot-opaque",
    "taskFamily": "ORDER_STATUS",
    "locale": "vi-VN",
    "conversationSnapshotRef": "conversation-opaque"
  },
  "pipeline": {
    "promptVersion": "support-v18",
    "modelRevision": "provider-model-rev-42",
    "retrieverVersion": "retriever-v8",
    "toolRegistryVersion": "tools-v6",
    "applicationBuild": "build-2026.11.27.3"
  },
  "evidence": {
    "contextSnapshotRef": "context-opaque",
    "sourceManifestRef": "sources-opaque",
    "toolFixtureSet": "order-tool-fixtures-v4"
  },
  "assertions": [
    {
      "id": "A1",
      "type": "MUST_NOT_ASSERT_UNSUPPORTED_STATUS",
      "dimension": "GROUNDEDNESS",
      "severity": "HIGH"
    },
    {
      "id": "A2",
      "type": "MUST_REQUEST_AUTHORITATIVE_LOOKUP",
      "dimension": "TOOL_CORRECTNESS",
      "severity": "HIGH"
    }
  ],
  "provenance": {
    "createdFrom": "CONFIRMED_PRODUCTION_DEFECT",
    "reviewedBy": "reviewer-opaque",
    "rubricVersion": "support-quality-v5",
    "createdAt": "2026-11-27T12:00:00Z"
  },
  "dataset": {
    "datasetVersion": "support-regression-v12",
    "suite": "RELEASE_GATE",
    "status": "ACTIVE"
  }
}
~~~

Đây là schema minh họa. Không lưu raw PII/secrets trong manifest; snapshot references phải trỏ tới secure store. Mỗi assertion có thể bổ sung oracle reference, threshold, evaluator version và failure message.

### 9.1. Versioning case

Tạo case version mới khi:

- Expected behavior thay đổi theo policy đã được phê duyệt.
- Root cause được làm rõ và cần bổ sung assertion.
- Fixture được thay thế nhưng vẫn giữ cùng defect semantics.
- Rubric thay đổi có ảnh hưởng đến verdict.

Không âm thầm sửa case cũ. Giữ case lineage và lý do thay đổi để hiểu vì sao một release trước đây pass nhưng hiện tại fail.

### 9.2. Deactivate và supersede

Case không còn hợp lệ có thể chuyển DEPRECATED hoặc SUPERSEDED nếu behavior đã được thay thế bởi policy mới. Không xóa case từng bảo vệ một defect quan trọng; giữ lịch sử và link tới replacement case.

## 10. Ví dụ Java: định nghĩa regression contract

Các type dưới đây là application-owned test model. Chúng giúp tách dữ liệu test khỏi cách gọi ChatClient hoặc model provider.

~~~java
import org.springframework.ai.content.Content;
import java.util.List;
import java.util.Map;

public enum AssertionType {
    RELEVANCE_MIN_SCORE,
    CLAIM_MUST_BE_SUPPORTED,
    MUST_ABSTAIN_WITHOUT_EVIDENCE,
    TOOL_MUST_BE_CALLED,
    TOOL_MUST_NOT_BE_CALLED,
    TOOL_ARGUMENT_SCHEMA,
    JSON_SCHEMA_VALID,
    NO_CROSS_TENANT_DATA
}

public record RegressionInput(
        String userText,
        String systemPrompt,
        List<Content> context,
        String conversationRef,
        Map<String, Object> toolFixtures) {
}

public record RegressionAssertion(
        String id,
        AssertionType type,
        String dimension,
        String expectedValue,
        double threshold) {
}

public record RegressionCase(
        String caseId,
        String defectRef,
        String severity,
        String datasetVersion,
        String suite,
        RegressionInput input,
        List<RegressionAssertion> assertions) {
}

public record AssistantResult(
        String responseText,
        List<ToolInvocationRecord> toolInvocations,
        String actualModel,
        String promptVersion) {
}
~~~

Các type như ToolInvocationRecord và Content cần được ánh xạ theo ứng dụng và phiên bản Spring AI đang dùng. RegressionInput dùng context snapshot đã pin; test không tự truy vấn live vector store trừ khi đó là retrieval test.

## 11. JUnit regression test cho các defect đã xác nhận

Một test harness có thể đọc các case thuộc suite và chạy qua adapter của ứng dụng.

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ConfirmedDefectRegressionTest {

    @Autowired
    private AssistantUnderTest assistantUnderTest;

    @Autowired
    private RegressionOracle regressionOracle;

    static Stream<RegressionCase> confirmedDefects() {
        return RegressionDataset.load("support-regression-v12")
                .stream()
                .filter(testCase ->
                        "RELEASE_GATE".equals(testCase.suite()));
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("confirmedDefects")
    void confirmedDefectMustStayFixed(RegressionCase testCase) {
        AssistantResult result = assistantUnderTest.run(
                testCase.input());

        for (RegressionAssertion assertion : testCase.assertions()) {
            AssertionOutcome outcome =
                    regressionOracle.evaluate(assertion, result, testCase);

            assertTrue(
                    outcome.passed(),
                    () -> "Case " + testCase.caseId()
                            + " failed assertion " + assertion.id()
                            + ": " + outcome.reason());
        }
    }
}
~~~

Đây là skeleton minh họa; RegressionDataset, AssistantUnderTest và RegressionOracle là các thành phần do ứng dụng xây dựng. JUnit cung cấp parameterized tests; Spring AI cung cấp ChatClient/ChatModel để adapter thực thi request. Không có một regression dataset runner mặc định nào được giả định ở đây.

### 11.1. Adapter sử dụng ChatClient

~~~java
import org.springframework.ai.chat.client.ChatClient;

public final class SpringAiAssistantAdapter
        implements AssistantUnderTest {

    private final ChatClient chatClient;
    private final ToolFixtureScope toolFixtures;
    private final RegressionPromptFactory promptFactory;

    public SpringAiAssistantAdapter(
            ChatClient chatClient,
            ToolFixtureScope toolFixtures,
            RegressionPromptFactory promptFactory) {
        this.chatClient = chatClient;
        this.toolFixtures = toolFixtures;
        this.promptFactory = promptFactory;
    }

    @Override
    public AssistantResult run(RegressionInput input) {
        toolFixtures.install(input.toolFixtures());
        try {
            String response = chatClient.prompt()
                    .system(input.systemPrompt())
                    .user(promptFactory.renderUserMessage(input))
                    .call()
                    .content();

            return new AssistantResult(
                    response,
                    toolFixtures.invocations(),
                    toolFixtures.actualModel(),
                    toolFixtures.promptVersion());
        }
        finally {
            toolFixtures.reset();
        }
    }
}
~~~

Đây là adapter minh họa cho flow đơn giản. RegressionPromptFactory là thành phần ứng dụng dùng để render user input cùng pinned context theo đúng contract production; nếu context được cấp qua advisor thì factory/advisor test phải dùng snapshot đó. Ứng dụng thực tế cần tạo scope mới cho từng test, inject advisors phù hợp và thu thập tool invocations qua callback hoặc instrumentation. Không dùng chung mutable fixture state giữa các test song song.

### 11.2. Oracle không phải lúc nào cũng là LLM

RegressionOracle có thể dispatch theo assertion type:

- Schema validator cho JSON.
- Exact comparison cho deterministic mapping.
- Source lookup hoặc fixture assertion cho factual claim.
- Tool invocation recorder cho tool selection/arguments.
- Evaluator đã calibration cho relevance/groundedness.
- Human-reviewed expected labels cho defect cần chuyên môn.

Giữ oracle version và failure reason trong test report. Nếu oracle lỗi hoặc unavailable, kết quả test là INCONCLUSIVE/INFRA_FAILURE theo policy, không tự coi là PASS.

## 12. RAG regression: tách retrieval khỏi generation

Một lỗi RAG thường bị che bởi final answer. Tách thành ba nhóm test.

### 12.1. Retrieval fixture test

Dùng query snapshot và expected evidence set:

~~~json
{
  "caseId": "rag-retrieval-042",
  "query": "Điều kiện hoàn tiền cho đơn đã giao là gì?",
  "requiredDocumentRefs": [
    "policy-refund-v7",
    "order-status-policy-v3"
  ],
  "forbiddenDocumentRefs": [
    "policy-refund-legacy-v2"
  ],
  "minimumRecallAtK": 1.0,
  "topK": 5,
  "filter": {
    "tenantRef": "tenant-fixture-a",
    "locale": "vi-VN"
  }
}
~~~

Các references là fixture IDs. Assertion có thể yêu cầu document bắt buộc xuất hiện trong top K và tài liệu hết hiệu lực không được chọn. Không hardcode similarity score tuyệt đối nếu embedding/index changes làm scale thay đổi; ưu tiên rank, membership và threshold đã calibration.

### 12.2. Context assembly test

Kiểm tra:

- Document ordering.
- Chunk deduplication.
- Metadata propagation.
- Tenant filters.
- Token budget/truncation.
- Source version và citation IDs.
- Không ghép context của hai tenant.
- Prompt instructions vẫn tách biệt với retrieved content.

### 12.3. Generation test với pinned context

Dùng đúng context snapshot đã gây lỗi. Test này cô lập prompt/model response khỏi retrieval drift. Khi candidate prompt/model thay đổi, chạy cùng context và assertions để xem unsupported claim có quay lại không.

### 12.4. Full RAG integration test

Chạy retrieval + context assembly + generation trong môi trường integration. Dùng vector store test hoặc index fixture có version; không dựa vào corpus production thay đổi liên tục. Ghi retrieved document IDs để khi fail biết lỗi nằm ở retrieval hay generation.

## 13. Tool-calling regression: kiểm tra proposal, execution và final answer

Tool calling có nhiều điểm có thể sai:

1. Model đề xuất tool name.
2. Arguments được parse và validate.
3. Authorization kiểm tra principal/tenant.
4. Tool thực thi.
5. Tool trả result hoặc error.
6. Result được đưa lại vào model.
7. Assistant tạo final answer.

Một regression case cần xác định đang kiểm tra bước nào.

### 13.1. Fake tool và fixture result

- Dùng fake tool trả kết quả cố định cho generation regression.
- Ghi tool name, validated arguments và invocation count.
- Assert không gọi tool khi thiếu confirmation hoặc permission.
- Assert timeout/error không bị biến thành success.
- Assert retry không gây side effect lặp.
- Dùng sandbox riêng cho integration test.

Không gọi email/payment/order write thật trong test dataset replay. Nếu cần test idempotency hoặc authorization, dùng test service có thể reset và audit.

### 13.2. Ví dụ tool contract

~~~json
{
  "caseId": "tool-order-017",
  "expected": {
    "toolName": "lookupOrderStatus",
    "arguments": {
      "orderReference": "ORDER-FIXTURE-17"
    },
    "maxInvocations": 1,
    "authorizationScope": "TENANT_FIXTURE_A",
    "toolOutcome": "TIMEOUT"
  },
  "assistantAssertions": [
    "MUST_NOT_CLAIM_ORDER_DELIVERED",
    "MUST_EXPLAIN_STATUS_UNAVAILABLE"
  ]
}
~~~

Test cần kiểm tra cả tool invocation và final response. Một câu trả lời nghe có vẻ hợp lý vẫn có thể che giấu việc tool được gọi với arguments sai.

## 14. Memory và multi-turn regression

Với conversation có memory, một case chỉ chứa câu hỏi cuối cùng có thể không tái hiện được lỗi.

Lưu snapshot theo thứ tự:

- Conversation/session reference.
- Message role và content snapshot.
- Memory store version hoặc fixture.
- Advisor chain và configuration.
- Tenant/user scope.
- Turn index.
- Expected memory facts và forbidden facts.

Các assertions quan trọng:

- Fact được lưu ở turn trước có thể được dùng khi còn hiệu lực.
- Fact đã bị sửa hoặc thu hồi không được dùng như hiện tại.
- Memory của conversation A không xuất hiện trong conversation B.
- Tenant A không đọc được memory tenant B.
- Tool result được lưu đúng scope và không bị biến thành claim vượt quá evidence.

Chạy multi-turn case tuần tự trong một isolated session. Reset memory trước mỗi test để tránh test order ảnh hưởng kết quả.

## 15. Dataset version, split và leakage prevention

Một regression dataset có thể được sử dụng cho nhiều mục đích, nhưng cần phân loại rõ.

| Dataset/suite | Mục đích | Có thể dùng để sửa prompt? |
| --- | --- | --- |
| Active regression suite | Ngăn defect đã biết quay lại | Có, nhưng phải ghi nhận đã dùng trong development |
| Development cases | Phân tích và cải thiện prompt/model | Có |
| Calibration set | Hiệu chuẩn evaluator/judge | Có cho calibration |
| Validation set | Chọn candidate và threshold | Có kiểm soát; không dùng để báo cáo cuối không thiên lệch |
| Held-out test set | Đánh giá cuối độc lập | Không dùng để tune |
| Production audit sample | Kiểm tra chất lượng traffic thực | Chỉ sau khi label được xác minh và policy cho phép |

### 15.1. Regression case được dùng để sửa lỗi

Khi một case làm prompt engineer thay đổi prompt cho đến khi pass, case đó đã trở thành development feedback. Vẫn giữ nó trong regression suite để bảo vệ lỗi đã biết, nhưng không báo cáo nó như held-out proof rằng prompt tổng quát hóa tốt.

Dùng held-out cases khác để kiểm tra candidate sau khi tuning. Nếu một defect có nhiều biến thể, giữ một phần biến thể chưa dùng trong quá trình sửa để kiểm tra khả năng tổng quát hóa.

### 15.2. Group split

Tránh đưa cùng conversation, near-duplicate, source document hoặc business entity vào cả development và held-out test nếu chúng có thể tiết lộ đáp án. Group split theo dependency phù hợp với task.

### 15.3. Dataset manifest

Mỗi dataset version nên có:

- Version và parent version.
- Case IDs và case versions.
- Inclusion/exclusion rules.
- Defect references và severity distribution.
- Rubric/evaluator versions.
- Snapshot/source manifest.
- Split membership.
- Content hashes.
- Reviewer/owner approvals.
- Change log và build timestamp.

Dataset version cần immutable. Thay case hoặc assertion tạo version mới, không sửa lịch sử.

## 16. Kiểm soát nondeterminism và flaky regression tests

LLM generation có thể dao động giữa các lần chạy. Một test flaky làm giảm niềm tin vào CI và khiến nhóm có xu hướng bỏ qua cảnh báo.

### 16.1. Phân loại nguồn nondeterminism

- Model sampling hoặc provider backend changes.
- Retrieval ranking thay đổi.
- Concurrent updates vào vector index.
- Tool fixture không deterministic.
- Current time hoặc random values trong prompt.
- Shared memory/session state giữa tests.
- Evaluator model thay đổi.
- Network/provider timeout hoặc rate limit.

Pin những dependency cần thiết và mock những dependency không thuộc phạm vi test.

### 16.2. Chiến lược kiểm tra

- Dùng exact assertions cho deterministic contract.
- Dùng semantic thresholds cho response tự nhiên.
- Dùng multiple-run evaluation khi bug phụ thuộc sampling.
- Ghi run count và variance.
- Chọn confidence/acceptance rule trước khi chạy.
- Tách product regression khỏi provider/infrastructure failures.
- Không dùng automatic retry để biến một failure thành pass mà không ghi flaky signal.

### 16.3. Khi test không ổn định

1. Giữ raw output và run metadata của tất cả lần chạy.
2. So sánh retrieved context, prompt version, model revision và tool fixtures.
3. Xác định assertion nào dao động.
4. Kiểm tra oracle/evaluator có ổn định không.
5. Chỉ tăng số lần chạy khi có hypothesis về stochasticity.
6. Nếu test cần quarantine, tạo issue, owner và expiry date.
7. Không xóa case critical chỉ vì nó khó chạy ổn định; chuyển sang deterministic layer hoặc sandbox phù hợp.

## 17. CI pipeline và release gates

Một pipeline thực tế có thể chia thành nhiều mức:

~~~mermaid
flowchart TD
    PR["Pull request / config change"] --> U["Unit and contract tests"]
    U --> R["Fast regression subset"]
    R -->|Fail| BLOCK["Block merge"]
    R -->|Pass| D["Full regression dataset"]
    D -->|Critical failure| BLOCK
    D -->|Pass| E["Semantic evaluation / quality thresholds"]
    E -->|Fail or inconclusive| REVIEW["Manual review / rerun by policy"]
    E -->|Pass| I["Integration and sandbox tests"]
    I -->|Fail| BLOCK
    I -->|Pass| S["Stage / shadow"]
    S --> C["Canary guardrails"]
    C -->|Violation| ROLLBACK["Pause or rollback"]
    C -->|Pass| RELEASE["Promote release"]
~~~

### 17.1. Fast suite và full suite

- Fast suite chạy các unit/contract và critical regression cases trong pull request.
- Full suite chạy toàn bộ regression dataset, semantic evaluators và integration tests ở CI/staging.
- Expensive model evaluations có thể chạy theo schedule hoặc trước release lớn, nhưng critical defect cases cần có gate phù hợp.
- Dataset version và evaluator version phải được pin trong build report.

### 17.2. Quy tắc fail/pass/inconclusive

Phân biệt:

- **FAIL:** assistant hoặc pipeline vi phạm expected behavior.
- **PASS:** mọi assertion bắt buộc đạt.
- **INCONCLUSIVE:** thiếu evidence, judge không chắc chắn hoặc output không thể đánh giá.
- **INFRA_FAILURE:** provider, network, fixture service hoặc test infrastructure lỗi.
- **FLAKY:** kết quả không ổn định qua lần chạy theo policy.

Không đổi INCONCLUSIVE/INFRA_FAILURE thành PASS. Release policy có thể yêu cầu rerun hoặc human review; critical gate không được tự động bỏ qua.

### 17.3. Failure report có thể hành động

Khi test fail, báo:

- Case ID và defect reference.
- Dataset/case version.
- Prompt/model/retriever/tool versions.
- Assertion ID và expected/actual summary.
- Evidence snapshot reference.
- Trace/span reference.
- Evaluator/rubric version.
- Run timestamp và environment.
- Link tới owner/runbook nội bộ nếu có.

Không in raw PII, secrets hoặc toàn bộ conversation vào public CI logs.

## 18. Regression metrics và dashboard

Các metric dưới đây là ví dụ do ứng dụng tự định nghĩa:

| Metric | Ý nghĩa |
| --- | --- |
| ai_regression_cases_total | Số case theo suite/category/severity |
| ai_regression_runs_total | Tổng số lần chạy theo result |
| ai_regression_failures_total | Số regression failures |
| ai_regression_inconclusive_total | Số lần không thể kết luận |
| ai_regression_infra_failures_total | Lỗi hạ tầng test/provider |
| ai_regression_flaky_total | Case có kết quả dao động |
| ai_regression_duration_seconds | Thời gian chạy case/suite |
| ai_regression_dataset_version | Dataset version đang được dùng |
| ai_regression_reopened_defects_total | Defect đã tái xuất hiện |
| ai_regression_assertion_failures_total | Số assertion fail theo dimension |
| ai_regression_evaluator_disagreement_total | Bất đồng giữa evaluator và reference labels |

Metric names là custom application metrics. Labels nên giới hạn ở suite, category, severity, result, environment và release cohort. Không đưa case IDs, trace IDs, raw prompts hoặc user identifiers vào Prometheus labels.

### 18.1. Regression failure rate

~~~promql
sum(rate(ai_regression_failures_total[1h]))
/
sum(rate(ai_regression_runs_total[1h]))
~~~

Đây là failure rate trên test runs trong cùng window. Nếu suite mix hoặc số lần chạy thay đổi, xem thêm breakdown theo severity/category và case counts.

### 18.2. Inconclusive rate

~~~promql
sum(rate(ai_regression_inconclusive_total[1h]))
/
sum(rate(ai_regression_runs_total[1h]))
~~~

Inconclusive tăng có thể là evaluator drift, thiếu evidence hoặc oracle quality giảm. Không gộp với PASS.

### 18.3. Thời gian regression suite

~~~promql
histogram_quantile(
  0.95,
  sum by (le, suite) (
    rate(ai_regression_duration_seconds_bucket[1h])
  )
)
~~~

Theo dõi p95 để phát hiện suite chậm do provider latency, dataset tăng hoặc integration test bị nghẽn. Giữ CI budget và chia suite theo chi phí.

### 18.4. Dashboard

Hiển thị:

- Regression cases active theo severity/category.
- Pass/fail/inconclusive/infra/flaky.
- Reopened defects theo release.
- Assertion failures theo relevance, groundedness, retrieval, tools, memory, schema.
- Dataset version và evaluator version.
- CI duration và provider cost.
- Case quarantine/deprecated với owner và expiry.
- Production incidents liên kết với regression cases.

## 19. Ví dụ end-to-end: assistant bịa trạng thái đơn hàng

### 19.1. Incident

Assistant trả lời “Đơn hàng đã được giao hôm nay” dù retrieval context chỉ chứa trạng thái “đang vận chuyển” từ một snapshot cũ. Người dùng dựa vào câu trả lời và liên hệ bộ phận hỗ trợ.

### 19.2. Xác nhận defect

Điều tra trace cho thấy:

- Query rewrite bỏ mất order reference.
- Retriever trả document cũ.
- Prompt yêu cầu trả lời trực tiếp thay vì abstain khi thiếu evidence.
- Không có authoritative order lookup trong luồng này.

Root cause được xác nhận là pipeline cho phép model biến context lỗi thời thành trạng thái hiện tại.

### 19.3. Tạo minimal case

- Input: hỏi trạng thái đơn hàng với order reference fixture.
- Context: document cũ nói “đang vận chuyển”, có source version và valid time.
- Tool fixture: order lookup trả TIMEOUT hoặc evidence chưa có.
- Prompt: phiên bản tái hiện lỗi.
- Expected: không khẳng định đơn đã giao; nêu chưa thể xác minh và hướng dẫn thử lại.

### 19.4. Assertions

1. Không xuất hiện claim “đã giao” nếu evidence không hỗ trợ.
2. Nếu order lookup được yêu cầu, arguments phải chứa đúng order reference và tenant scope.
3. Khi tool timeout, final response phải nói trạng thái chưa xác minh.
4. Không gọi tool lặp quá giới hạn.
5. Citation không được trỏ tới source version hết hiệu lực như trạng thái hiện tại.

### 19.5. Regression coverage

- Retrieval test xác minh stale document không được dùng như source hiện hành.
- Prompt/generation test dùng pinned context snapshot.
- Tool contract test xác minh timeout mapping.
- End-to-end test xác minh final answer không vượt evidence.
- Production monitor theo dõi unsupported order status claims.

Khi prompt/model/retriever được cập nhật, toàn bộ các lớp liên quan chạy lại. Nếu defect tái xuất hiện, CI report chỉ ra assertion và trace tương ứng.

## 20. Quản lý ownership và maintenance của regression cases

Regression dataset cần được duy trì như một phần của sản phẩm:

- Mỗi case có owner theo domain hoặc component.
- Defect reference phải trỏ tới incident/issue có thể audit.
- Severity và business impact được ghi.
- Case có creation date, last reviewed date và review cadence.
- Fixture dependencies có version và retention.
- Case deprecated phải có reason và replacement nếu cần.
- Dataset release có reviewer/approver.
- Flaky case có owner, issue và expiry date.
- Case critical không được xóa chỉ để làm CI xanh.

Khi policy hoặc product behavior thay đổi có chủ đích, owner đánh giá case cũ và cập nhật version mới. Không chỉnh expected output chỉ để candidate hiện tại pass nếu chưa có product/domain approval.

## 21. Quy trình triển khai end-to-end

1. Nhận incident hoặc defect report và xác định interaction reference.
2. Thu thập trace, prompt/model/config versions và evidence snapshot.
3. Xác nhận hành vi sai, impact và root cause.
4. Tạo reproduction trong môi trường an toàn.
5. Tối giản input/context/tool fixtures nhưng giữ nguyên trigger.
6. Xác định expected behavior và oracle theo dimension.
7. Tạo regression case có defect reference, severity, provenance và owner.
8. Chạy test với version gây lỗi để chứng minh reproduction.
9. Sửa prompt/model routing/retrieval/tool/application logic.
10. Chạy lại case để xác nhận fix.
11. Chạy regression suite liên quan để phát hiện side effects.
12. Review case, version dataset và xác định split phù hợp.
13. Thêm case vào fast/full CI suite theo severity.
14. Theo dõi case sau release và liên kết production recurrence.
15. Cập nhật/deprecate case khi policy thay đổi qua approval.

## 22. Checklist kiểm thử production

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Incident chưa xác nhận root cause | Chưa được promote thành confirmed regression case |
| Bug tái hiện với snapshot | Test thất bại trên version gây lỗi |
| Fix được áp dụng | Regression case pass với expected behavior |
| Context snapshot thay đổi | Case version/evidence manifest được cập nhật |
| Retrieval regression | Expected documents/ranks được kiểm tra riêng |
| Generation regression | Dùng pinned context để cô lập prompt/model |
| Tool timeout | Assistant không tuyên bố tool action thành công |
| Tool có side effect | Test dùng fake/sandbox và idempotency |
| Memory multi-turn | Session được reset và tenant isolation được kiểm tra |
| Model output dao động | Dùng semantic assertions và lưu run metadata |
| Evaluator unavailable | Kết quả là inconclusive/infra failure, không phải pass |
| Golden case đã dùng để tune prompt | Không báo cáo như held-out test |
| Dataset version thay đổi | Manifest và change log được tạo |
| Regression case flaky | Có owner, reason và expiry; không âm thầm bỏ qua |
| Critical regression fail | Release gate chặn promotion |
| CI log có PII/secret | Redaction ngăn dữ liệu nhạy cảm bị lộ |
| Production defect tái xuất hiện | Incident liên kết về case và assertion đã fail |

## 23. Bài tập thực hành

### Bài 1. Chuyển incident thành regression case

Chọn một lỗi hallucination đã xác nhận. Thu thập prompt, model, context và output snapshot. Viết expected behavior cùng ít nhất hai assertions độc lập.

### Bài 2. Tối giản RAG reproduction

Tạo context gồm nhiều chunks, trong đó chỉ một chunk gây lỗi. Dùng delta debugging để tìm minimal context và chứng minh lỗi vẫn tái hiện.

### Bài 3. Viết JUnit parameterized regression test

Tạo 5 regression cases với các assertion khác nhau. Chạy chúng qua một AssistantUnderTest adapter và báo case ID/assertion ID khi fail.

### Bài 4. Tách retrieval và generation tests

Tạo một retrieval fixture có required/forbidden document refs. Sau đó dùng pinned context để kiểm tra generation riêng. Mô phỏng lỗi ở từng lớp.

### Bài 5. Tool timeout regression

Dùng fake tool trả timeout. Assert tool được gọi đúng một lần, assistant không khẳng định action thành công và không tạo side effect thật.

### Bài 6. Semantic assertion

Viết một assertion kiểm tra factual claim được hỗ trợ mà không yêu cầu exact string. Hiệu chuẩn evaluator trên human-reviewed labels và thêm trạng thái inconclusive.

### Bài 7. Dataset version và leakage

Tạo regression dataset v1, sau đó thêm case từ một incident mới để tạo v2. Đánh dấu case đã dùng để tune prompt và giữ held-out cases độc lập.

### Bài 8. CI release gate

Thiết kế fast suite và full suite. Mô phỏng critical regression fail, evaluator unavailable và flaky test; xác định từng trường hợp block, rerun hay manual review.

## 24. Tổng kết

Đưa lỗi đã xác nhận trở lại bộ dữ liệu kiểm tra hồi quy giúp chất lượng ứng dụng AI được bảo vệ qua từng lần thay đổi:

- Incident phải được điều tra và xác nhận trước khi thành regression case.
- Snapshot giữ input, prompt, model, context, tool fixtures, memory và runtime versions cần thiết.
- Minimization giúp tạo case nhỏ, dễ tái hiện mà vẫn giữ nguyên trigger.
- Expected behavior cần oracle và assertion theo đúng dimension.
- RAG test phải tách retrieval, context assembly và generation.
- Tool test phải kiểm tra proposal, arguments, authorization, execution result và final answer.
- Memory test phải giữ multi-turn order và tenant/session isolation.
- Spring AI cung cấp ChatClient/ChatModel và Evaluator để xây adapter; dataset runner và regression oracle do application/test layer xây dựng.
- Regression suite khác held-out benchmark; case dùng để tune không được báo cáo như test độc lập.
- Nondeterminism cần được đo và phân loại; evaluator/infra failures không được coi là PASS.
- CI gate cần phân biệt FAIL, INCONCLUSIVE, INFRA_FAILURE và FLAKY.
- Dataset version, provenance, owner và change log giúp regression cases được duy trì lâu dài.

Một lỗi chỉ thực sự được bảo vệ sau khi có test tái hiện, assertion chứng minh hành vi đúng và case được chạy lại trong quy trình thay đổi phần mềm. Mỗi defect đã xác nhận trở thành một phần của bộ nhớ kiểm thử của hệ thống, giúp nhóm phát triển không phải học lại cùng một bài học sau mỗi lần nâng cấp.

## Tài liệu tham khảo

- [Spring AI Reference — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html): ChatClient, prompt, advisors và tích hợp ChatModel.
- [Spring AI Reference — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator, EvaluationRequest, RelevancyEvaluator và FactCheckingEvaluator.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): observations, metrics và traces cho AI operations.
- [JUnit 5 User Guide — Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests): chạy cùng test logic với nhiều input/cases.
- [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/): spans, attributes, events và trace context để điều tra interaction.
