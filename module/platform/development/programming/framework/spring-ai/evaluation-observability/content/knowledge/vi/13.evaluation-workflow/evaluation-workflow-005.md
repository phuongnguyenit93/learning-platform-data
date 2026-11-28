# Tạo báo cáo tổng hợp cùng danh sách ca thất bại

Một bộ kiểm thử Spring AI có 120 ca trả về dòng thông báo “90 ca đạt”. Thông tin này gần như vô dụng nếu nhóm không biết **120 ca gồm những gì**, bao nhiêu ca thực sự được chạy, ca nào bị bỏ qua, bao nhiêu ca lỗi provider, có ca nào không chấm được, và 30 ca còn lại **thất bại vì điều gì**.

Một báo cáo đánh giá có thể phục vụ hai mục đích khác nhau:

- **Báo cáo tổng hợp (summary report):** giúp người phụ trách phát hành nhìn được phạm vi đánh giá, mức độ đạt, độ bao phủ, sai lệch so với baseline, độ trễ và chi phí.
- **Danh sách ca thất bại (failure list):** giúp kỹ sư tìm chính xác câu hỏi nào, phiên bản cấu hình nào, evidence nào và bước nào khiến case không đạt hoặc không hoàn thành.

Hai phần phải xuất phát từ **cùng tập dữ liệu thực thi và verdict**, liên kết bằng `runId`, `caseId`, `attemptId` và các reference tới evidence/trace. Nếu summary báo 16 ca quality FAIL mà failure list chỉ có 13 ca, báo cáo đã thiếu tính toàn vẹn hoặc đang dùng hai cách đếm không tương thích.

Bài học thuộc chương **Quy trình đánh giá** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Từ tập dữ liệu, tiêu chí relevance/fact checking và kiểm thử RAG/tool calling, chúng ta sẽ xây một report vừa giúp ra quyết định theo chất lượng, vừa dùng metrics, traces, token, chi phí và độ trễ để điều tra hồi quy giữa các phiên bản prompt, model và pipeline.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định cấu trúc của một báo cáo evaluation đầy đủ, có thể truy vết.
2. Tách **trạng thái thực thi** khỏi **kết luận chấm chất lượng** khi tổng hợp.
3. Tính chính xác PASS/FAIL, SKIPPED, TECHNICAL_ERROR, NOT_EVALUATED và coverage với mẫu số rõ ràng.
4. Tạo danh sách ca thất bại có thể dùng trực tiếp để ưu tiên điều tra.
5. Phân loại lỗi retrieval, grounding, factual correctness, citation, tool calling và sự cố runtime/evaluator.
6. Gắn từng failure với expected/actual, cấu hình, tài liệu RAG, tool events và trace evidence.
7. Xây báo cáo theo nhóm ca, độ nghiêm trọng và phiên bản, không chỉ tổng phần trăm.
8. So sánh baseline/candidate, tìm ca hồi quy và ca được sửa trên cùng dataset/rubric.
9. Triển khai bộ tổng hợp bằng Java, kiểm tính nhất quán bằng JUnit.
10. Tách quality metrics khỏi latency, token, cost và đánh giá release gates có trách nhiệm.

## 2. Đầu ra cuối cùng cần có hai phần bổ trợ nhau

Trong một đánh giá có nhiều ca, báo cáo thường được chia thành các khu vực:

| Khu vực | Câu hỏi chính | Độc giả |
| --- | --- | --- |
| **Run identity** | Đang đánh giá phiên bản nào, lúc nào, với dataset/rubric nào? | Reviewer, kỹ sư, quản lý |
| **Execution summary** | Có bao nhiêu ca chạy được, lỗi, bỏ qua, chờ đánh giá? | Vận hành, CI |
| **Quality summary** | Relevance, groundedness, factual correctness, RAG/tool đạt bao nhiêu? | Kỹ thuật AI, domain expert |
| **Slices/segments** | Nhóm ca nào kém? Ca critical nào chưa đạt? | Người điều tra |
| **Baseline comparison** | Thay đổi mới sửa được ca nào, làm hỏng ca nào? | Release reviewer |
| **Operational metrics** | p95 latency, 429, retries, token/cost đã đổi ra sao? | SRE, platform |
| **Failure list** | Chính xác những ca nào cần xử lý? | Developer, QA |
| **Evidence links** | Tài liệu, tool event, trace nào chứng minh kết luận? | Reviewer, auditor |
| **Release decision** | Đủ điều kiện phát hành hay cần chặn/review thêm? | Người phê duyệt |

Một báo cáo tốt cần đáp ứng được cả **đọc nhanh** và **đi sâu**. Tổng quan có thể vừa một trang, còn danh sách lỗi được lưu thành artifact máy đọc được để lọc và mở từng ca.

### 2.1. Kiến trúc dữ liệu từ chạy test tới báo cáo

~~~mermaid
flowchart TD
    A["Versioned dataset + rubric"] --> B["Spring AI evaluation runner"]
    B --> C["Execution attempts"]
    C --> D["Actual answer / RAG context<br/>/ tool evidence / telemetry"]
    C --> E["Quality verdicts by metric"]
    A --> E
    D --> E
    C --> F["Report normalization<br/>one outcome per planned case"]
    E --> F
    F --> G["Execution + quality counts"]
    F --> H["Failure list + evidence refs"]
    F --> I["Coverage + group slices"]
    F --> J["Baseline/candidate diff"]
    D --> K["Latency / usage / traces"]
    G --> L["Report bundle"]
    H --> L
    I --> L
    J --> L
    K --> L
    L --> M["Release gates + investigation"]
~~~

Điểm quan trọng nhất là bước **normalization**: kết quả thô có thể chứa nhiều retry hoặc nhiều lần chấm một attempt. Trước khi cộng số ca, phải xác định **một kết quả được chấp nhận cho mỗi case theo run policy**, đồng thời vẫn giữ lịch sử các attempts và evaluator verdicts.

## 3. Phạm vi và đơn vị đếm: case, attempt, metric, run

Bốn loại bản ghi sau không được dùng lẫn:

| Đơn vị | Định danh | Ý nghĩa | Lỗi dễ gặp |
| --- | --- | --- | --- |
| **Test case** | `caseId` | Một tình huống với input, kỳ vọng và rubric | Đếm retry thành nhiều case |
| **Execution attempt** | `attemptId` | Một lần thực thi case qua pipeline | Gộp output của attempt A với context B |
| **Metric verdict** | `evaluationId` + metric | Một kết luận chấm, có version và evidence | Đếm relevance PASS như case PASS |
| **Evaluation run** | `runId` | Một đợt chạy cùng manifest/config | Gộp ca từ hai phiên bản prompt |

Ví dụ, case `REFUND-001` được thử 3 lần vì provider timeout ở hai lần đầu. Nó vẫn là **một case thuộc run**, nhưng có ba attempts. Nếu cùng answer được chấm bởi cả `judge-v1` và `judge-v2`, số metric verdict tăng nhưng số case không tăng.

### 3.1. Chính sách chọn kết quả cuối phải xác định trước

Một quy tắc phù hợp cho bài thực hành:

1. Với mỗi `caseId` trong dataset snapshot, xác định trạng thái eligibility (eligible/skip).
2. Nếu eligible, lấy các attempts của **đúng run**.
3. Nếu retry kỹ thuật được cho phép, chọn attempt kết thúc theo retry policy đã công bố, không tự ý chọn attempt có điểm cao nhất.
4. Nếu có nhiều lần chạy có chủ đích để đo xác suất, **không** thu gọn bằng cách lấy lần PASS đẹp nhất; báo phân bố kết quả theo lần chạy.
5. Chọn verdict của đúng `rubricVersion`/`judgeVersion` được áp dụng cho report.
6. Gắn metric FAIL và lỗi kỹ thuật của các attempt không được chọn vào **retry/audit detail**, không xóa chúng.

Nếu không thực hiện bước này, summary có thể bị nhân đôi vì retry và quality pass rate sẽ bị làm đẹp hoặc làm xấu một cách ngẫu nhiên.

### 3.2. Report phải khai báo trạng thái vòng đời

Một run có thể là `CREATED`, `RUNNING`, `COMPLETED`, `PARTIAL`, `FAILED` hoặc `CANCELLED`.

`COMPLETED` ở cấp run nghĩa là tất cả ca đã có trạng thái kết thúc theo hợp đồng ghi kết quả, **không có nghĩa tất cả ca đạt quality**. Với một run `PARTIAL`, cần báo số ca chưa chạy hoặc chưa được ghi, không công bố như báo cáo hoàn tất.

## 4. Chuẩn hóa trạng thái trước khi tổng hợp

Cách vững chắc là lưu **execution status** và **quality status** riêng.

| Trục | Giá trị ví dụ | Cách sử dụng |
| --- | --- | --- |
| Execution | `COMPLETED` | Pipeline sinh output hợp lệ về mặt kỹ thuật |
| Execution | `ERROR` | Pipeline không tạo output hợp lệ do lỗi kỹ thuật |
| Execution | `SKIPPED` | Ca được loại có chủ đích theo policy |
| Execution | `NOT_STARTED` / `CANCELLED` | Chưa được chạy hoặc bị hủy giữa chừng |
| Quality aggregate | `PASS` | Tất cả metric bắt buộc được chấm và đạt |
| Quality aggregate | `FAIL` | Có ít nhất một metric bắt buộc FAIL |
| Quality aggregate | `INCONCLUSIVE` | Không có FAIL nhưng còn metric bắt buộc chưa chấm |
| Metric verdict | `NOT_APPLICABLE` | Metric không áp dụng cho case |

**TECHNICAL_ERROR** thường là nhãn báo cáo cho execution `ERROR`. **NOT_EVALUATED** thường là trạng thái ở cấp metric, không phải đồng nghĩa với `SKIPPED`.

### 4.1. Các trạng thái không được biến thành PASS

- Request HTTP 200 nhưng factual correctness FAIL → **quality FAIL**.
- Tool trả 403 như kỳ vọng của security test → có thể **authorization PASS**.
- Model trả answer nhưng judge timeout → execution COMPLETED, metric NOT_EVALUATED.
- Provider trả 429 sau khi đã hết retry → execution ERROR, không chấm quality.
- Case không được chạy vì sandbox không có, theo quy tắc đã định trước → SKIPPED.
- Case chưa được lịch trình chạy khi batch bị hủy → NOT_STARTED/CANCELLED, **không phải SKIPPED**.

### 4.2. Quy tắc aggregate quality có thể dùng

Với một execution COMPLETED:

- Có **bất kỳ metric bắt buộc FAIL** → aggregate FAIL.
- Không có FAIL, nhưng có metric bắt buộc PENDING/NOT_EVALUATED hoặc thiếu record → aggregate INCONCLUSIVE.
- Tất cả metric bắt buộc PASS → aggregate PASS.
- Một metric NOT_APPLICABLE chỉ được bỏ qua nếu test contract xác nhận metric không bắt buộc trong ca đó.
- Không có metric bắt buộc do lỗi khai báo → không tự PASS.

Khi aggregate là FAIL vì factual correctness, vẫn giữ metric groundedness NOT_EVALUATED nếu thiếu context. Việc chấm thiếu không biến mất chỉ vì đã phát hiện một lỗi khác.

## 5. Ví dụ tính báo cáo tổng hợp với 120 case

Giả sử một run có các kết quả giả định:

~~~text
Dataset selected:                  120
  SKIPPED by approved plan:          4
  Eligible/attempted:             116
    TECHNICAL_ERROR:                5
    COMPLETED:                    111
      Quality PASS:                90
      Quality FAIL:                16
      Quality INCONCLUSIVE:          5
~~~

**Kiểm tra toàn vẹn:** `4 + 5 + 90 + 16 + 5 = 120`. Trong 111 ca COMPLETED, chỉ 106 ca có verdict tổng hợp PASS hoặc FAIL; 5 ca chưa đủ kết luận.

### 5.1. Định nghĩa và mẫu số của từng KPI

| Chỉ số | Công thức | Giá trị ví dụ |
| --- | --- | ---: |
| Skip rate | SKIPPED / selected | 4/120 = 3,33% |
| Eligible technical completion | COMPLETED / eligible | 111/116 ≈ 95,69% |
| Technical error rate | ERROR / eligible | 5/116 ≈ 4,31% |
| Evaluated quality cases | PASS + FAIL | 90 + 16 = 106 |
| Evaluated quality pass rate | PASS / (PASS + FAIL) | 90/106 ≈ 84,91% |
| Evaluation coverage | (PASS + FAIL) / COMPLETED | 106/111 ≈ 95,50% |
| Verified eligible success | PASS / eligible | 90/116 ≈ 77,59% |

Công thức tổng quát:

\[
\mathrm{evaluatedQualityPassRate} =
\frac{N_{\mathrm{PASS}}}{N_{\mathrm{PASS}}+N_{\mathrm{FAIL}}}.
\]

\[
\mathrm{technicalCompletionRate} =
\frac{N_{\mathrm{COMPLETED}}}{N_{\mathrm{eligible}}}.
\]

\[
\mathrm{evaluationCoverage} =
\frac{N_{\mathrm{PASS}}+N_{\mathrm{FAIL}}}
{N_{\mathrm{COMPLETED}}}.
\]

Các phép chia cần có **mẫu số lớn hơn 0**; nếu không có ca được chấm, kết quả là `N/A / INSUFFICIENT_DATA`, không phải 0% hay 100%.

`90/116` là **tỷ lệ ca đủ điều kiện được xác minh đạt**; nó không chứng minh cả 26 ca còn lại đều sai nội dung. Trong số đó có 5 ca lỗi kỹ thuật và 5 ca chưa thể chấm.

### 5.2. KPI chỉ hữu ích khi kèm độ bao phủ

Một candidate có 99 PASS trên 100 ca đã chấm nhưng bỏ qua 900 ca khó không tự động tốt hơn candidate có 850 PASS trên 950 ca được chấm.

Phải hiển thị tối thiểu:

- Selected, eligible, skipped và lý do skip.
- Attempted/completed/error; số ca còn chờ hoặc bị hủy.
- Evaluated PASS/FAIL và NOT_EVALUATED/INCONCLUSIVE.
- Tỷ lệ theo **nhóm tác vụ**, không chỉ tỷ lệ chung.
- Số ca critical có PASS/FAIL/ERROR/SKIPPED/NOT_EVALUATED.

Đặc biệt nếu chạy online sampling, tỷ lệ PASS **trên mẫu được chấm** không tự động là tỷ lệ đúng của toàn traffic.

## 6. Tổng hợp theo metric và nhóm ca

Một ca thường có nhiều metric. Report nên có **hai tầng thống kê**: case aggregate và metric-specific outcomes. Không được cộng tất cả metric PASS rồi chia cho số case.

Ví dụ phân nhóm **106 ca đã có kết luận cuối**:

| Nhóm | Đã chấm | PASS | FAIL | Pass rate |
| --- | ---: | ---: | ---: | ---: |
| Chính sách RAG có nguồn | 45 | 37 | 8 | 82,22% |
| Thiếu nguồn / cần từ chối | 25 | 21 | 4 | 84,00% |
| Tool calling | 22 | 20 | 2 | 90,91% |
| Hội thoại nhiều lượt | 14 | 12 | 2 | 85,71% |
| **Tổng** | **106** | **90** | **16** | **84,91%** |

Số trên chỉ là **minh họa**, không phải benchmark Spring AI.

### 6.1. Những metric cần báo riêng

| Metric | Bằng chứng cần có | Nên kèm |
| --- | --- | --- |
| Relevance | Question + actual answer | Số PASS/FAIL/NOT_EVALUATED |
| Groundedness | Answer + effective context thực tế | Context coverage, judge version |
| Factual correctness | Answer + reference facts/docs đã xác minh | Reference version, human review |
| Retrieval hit@k/Recall@k | Expected relevant IDs + actual retrieved docs | K, số ca có nhãn đủ |
| Citation correctness | Answer citations + source mapping | Tài liệu sai version/không hỗ trợ |
| Tool selection/args | Expected tool + actual invocation | Số ca tool bắt buộc |
| Authorization/side effects | Backend checks + hậu điều kiện | Ca critical và fixture version |
| Schema compliance | Actual output + schema | Parser/contract version |

**Factual correctness khác groundedness.** Model có thể giải thích đúng tài liệu cũ “30 ngày” (grounded theo context), nhưng sai nguồn chính thức hiện hành “14 ngày” (factual FAIL).

**Retrieval hit@k khác answer quality.** Tìm đúng tài liệu không bảo đảm model diễn giải đúng. Vì vậy báo cáo nên cho thấy những ca retrieval PASS nhưng factual FAIL.

### 6.2. Nhãn RAG không đầy đủ thì không nên báo Recall@k giả

Recall@k đòi hỏi biết tập tài liệu liên quan theo định nghĩa metric. Nếu dataset chỉ có một tài liệu chuẩn bắt buộc, `hit@k` có thể phù hợp hơn. Không suy ra Recall@k chính xác cho mọi production request chỉ từ similarity scores.

### 6.3. Nhóm critical có mẫu số riêng

Khi có ca quyền truy cập tài liệu, thao tác có tác dụng phụ hoặc dữ kiện nghiệp vụ quan trọng, cần báo **critical pass**, **critical fail**, **critical error**, **critical skipped/unevaluated**. Một lỗi critical có thể chặn phát hành dù pass rate bình quân tốt.

## 7. Danh sách ca thất bại là công cụ điều tra, không chỉ bảng ID

Nếu summary ghi “16 ca FAIL, 5 ca ERROR”, failure list nên cho phép đi thẳng từ từng dòng đến evidence và người xử lý.

Một hàng tối thiểu:

| Trường | Mục đích |
| --- | --- |
| `runId` / `caseId` / `attemptId` | Định danh chính xác |
| `status` | QUALITY_FAIL, TECHNICAL_ERROR hoặc trạng thái khác |
| `severity` / `critical` | Mức ưu tiên |
| `group` / `tags` | Lọc theo RAG, tool, memory, ngôn ngữ |
| `primaryMetric` | Metric chính bị vi phạm |
| `reasonCode` / `feedback` | Lý do ngắn và nhận xét |
| `expectedSummary` | Chuẩn/điều kiện mong đợi đã xử lý riêng tư |
| `actualSummary` | Hành vi thực tế đã xử lý riêng tư |
| `referenceRefs` | Nguồn chuẩn cho factuality |
| `retrievalRefs` / `toolEventRefs` | Bằng chứng RAG/tool thực tế |
| `traceRef` | Đường dẫn tra spans nếu tracing tồn tại |
| `prompt/model/pipelineVersion` | Khoanh vùng release |
| `retryCount`, latency, tokens/cost | Phân tích nguyên nhân vận hành |
| `owner` / `triageStatus` | Người phụ trách và trạng thái xử lý |

Không nhất thiết hiển thị mọi trường trong bảng tổng quan. Có thể lưu danh sách **thu gọn** và một bản **machine-readable** đầy đủ hơn, nhưng các liên kết phải dẫn đúng attempt.

### 7.1. Một danh sách lỗi minh họa

| Mức | Case | Loại lỗi | Bằng chứng chính | Ưu tiên điều tra |
| --- | --- | --- | --- | --- |
| Critical | `POLICY-017` | FACTUAL_FAIL | Trả “30 ngày”; nguồn hiện hành 14 ngày | Kiểm phiên bản tài liệu |
| Critical | `AUTH-004` | TOOL_AUTH_FAIL | Tool cho phép đọc đơn không có quyền | Kiểm backend authorization |
| High | `RAG-026` | RETRIEVAL_FAIL | Top-5 không chứa tài liệu bắt buộc | Kiểm index/filter |
| High | `TOOL-014` | TOOL_RESULT_FAIL | Tool trả DENIED nhưng chatbot báo thành công | Kiểm xử lý result |
| Medium | `CHAT-042` | RELEVANCE_FAIL | Trả lời lệch chủ đề | Kiểm prompt/model |
| Operational | `GEN-031` | PROVIDER_TIMEOUT | Không có answer sau retry | Kiểm provider/timeout |

Bảng trên **chỉ là các dòng điển hình**, không đại diện toàn bộ 21 ca FAIL/ERROR của ví dụ. Trong artifact đầy đủ, mỗi ca thất bại phải xuất hiện theo quy tắc đếm của báo cáo, hoặc có cơ chế phân trang/giới hạn hiển thị được công bố.

### 7.2. Failure list không được chứa “chứng cứ” tự bịa

Một `traceRef` chỉ hữu ích nếu backend thật có trace đó. Nếu trace bị lấy mẫu và không có, ghi `TRACE_UNAVAILABLE`.

Tương tự, retrieved document IDs phải đến từ attempt thực tế. Không thay actual documents bằng expected documents để làm lỗi trông dễ hiểu hơn. Một câu trả lời không có effective context không nên được chấm groundedness như thể model đã nhìn thấy nguồn chuẩn.

## 8. Danh mục lỗi: giảm thời gian tìm nguyên nhân

Bên cạnh metric FAIL, nên chuẩn hóa taxonomy theo **error family** và **reasonCode**.

| Family | Reason code gợi ý | Hướng điều tra đầu |
| --- | --- | --- |
| RETRIEVAL | `MISSING_REQUIRED_SOURCE` | Query, top-k, filters, corpus |
| RETRIEVAL | `STALE_DOCUMENT` | Index freshness, hiệu lực tài liệu |
| GROUNDING | `UNSUPPORTED_CLAIM` | Effective context, prompt |
| FACTUAL | `WRONG_REFERENCE_FACT` | Nguồn chuẩn, answer |
| CITATION | `INVALID_CITATION` | Citation mapping, source |
| TOOL | `MISSING_REQUIRED_TOOL` | Tool selection/prompt |
| TOOL | `WRONG_TOOL_ARGUMENTS` | Schema, conversation context |
| TOOL | `UNAUTHORIZED_ACTION` | Backend authorization |
| TOOL | `RESULT_MISINTERPRETED` | Tool result và answer |
| MEMORY | `CROSS_CONVERSATION_LEAK` | Session isolation |
| FORMAT | `INVALID_OUTPUT_SCHEMA` | Parser, response contract |
| PROVIDER | `RATE_LIMIT_EXHAUSTED` | RPM/TPM, retry |
| PROVIDER | `PROVIDER_TIMEOUT` | Timeout/latency/network |
| EVALUATOR | `JUDGE_TIMEOUT` | Judge quota và coverage |
| EVIDENCE | `EFFECTIVE_CONTEXT_MISSING` | Capture ở RAG advisor |

**Family không phải kết luận root cause tự động.** Nó là giả thuyết phân loại dựa trên bằng chứng. Lỗi “answer sai” có thể đến từ retrieval, prompt/model, memory hoặc tool. Muốn khẳng định nguyên nhân phải kiểm chứng bằng attempt evidence và thử thay đổi có kiểm soát.

### 8.1. Không gộp ERROR vào FAIL ngữ nghĩa

- `QUALITY_FAIL`: output hợp lệ được tạo, nhưng vi phạm rubric.
- `TECHNICAL_ERROR`: không tạo output hợp lệ vì lỗi runtime/provider/tool.
- `EVALUATION_GAP`: output có, nhưng không đủ evidence hoặc judge lỗi.
- `SKIP`: ca không chạy có chủ đích theo plan.

Một báo cáo release có thể xem **cả bốn nhóm đều là rủi ro cần chú ý** mà vẫn không dùng cùng một mẫu số cho factual pass rate.

### 8.2. Danh sách “ca cần xử lý” rộng hơn danh sách FAIL

Nên có:

- **failures:** các ca quality FAIL và technical ERROR.
- **evaluation gaps:** INCONCLUSIVE/NOT_EVALUATED, thiếu dữ liệu/bộ chấm.
- **skipped cases:** có reason code và policy.
- **unstarted/cancelled:** khi run chưa hoàn tất.

Nhờ đó, nhóm không bỏ sót một ca critical chỉ vì nó “chưa được chấm” chứ không phải “chấm FAIL”.

## 9. Định dạng artifact: report JSON và Markdown

Một report bundle có thể lưu:

~~~text
evaluation-reports/
  <run-id>/
    run-manifest.json
    case-outcomes.jsonl
    metric-verdicts.jsonl
    summary.json
    failures.jsonl
    evaluation-gaps.jsonl
    skipped-cases.jsonl
    report.md
    metrics-summary.json
~~~

Đây là **cấu trúc khuyến nghị do dự án thiết kế**, không phải output có sẵn của Spring AI. Nếu chứa dữ liệu nhạy cảm, các file có thể được phân quyền khác nhau hoặc chỉ chứa references tới evidence store.

### 9.1. Ví dụ summary JSON nhất quán với 120 ca

~~~json
{
  "schemaVersion": "evaluation-report-v1",
  "runId": "candidate-v2-2026-05-18",
  "runStatus": "COMPLETED",
  "manifestRef": "run-manifest:candidate-v2-2026-05-18",
  "datasetVersion": "support-eval-v3",
  "rubricVersion": "quality-rubric-v2",
  "judgeVersion": "judge-v1",
  "counts": {
    "selected": 120,
    "skipped": 4,
    "eligible": 116,
    "technicalCompleted": 111,
    "technicalError": 5,
    "qualityPass": 90,
    "qualityFail": 16,
    "qualityInconclusive": 5,
    "qualityEvaluated": 106
  },
  "rates": {
    "technicalCompletion": 0.9569,
    "evaluatedQualityPassRate": 0.8491,
    "qualityEvaluationCoverage": 0.9550,
    "verifiedEligibleSuccess": 0.7759
  },
  "artifacts": {
    "failuresRef": "failures.jsonl",
    "evaluationGapsRef": "evaluation-gaps.jsonl",
    "skippedCasesRef": "skipped-cases.jsonl",
    "metricsRef": "metrics-summary.json"
  },
  "releaseDecision": "BLOCKED_PENDING_REVIEW"
}
~~~

Các tỷ lệ làm tròn 4 chữ số; số đếm là nguồn chính cho việc tái tính. Quyết định release ở đây chỉ là **minh họa**, không suy ra tự động từ một ngưỡng Spring AI mặc định nào.

### 9.2. Ví dụ một failure JSONL record

~~~json
{
  "runId": "candidate-v2-2026-05-18",
  "caseId": "POLICY-017",
  "attemptId": "candidate-v2-POLICY-017-r1",
  "failureType": "QUALITY_FAIL",
  "severity": "CRITICAL",
  "primaryMetric": "factualCorrectness",
  "reasonCode": "WRONG_REFERENCE_FACT",
  "group": "policy-rag",
  "expectedSummary": "14 ngày theo policy-v3",
  "actualSummary": "30 ngày theo policy-v2",
  "referenceRefs": ["policy-v3#pro-refund"],
  "actualRetrievedIds": ["policy-v2#pro-refund"],
  "evidenceRefs": ["secure-answer-ref", "secure-context-ref"],
  "traceRef": null,
  "versions": {
    "prompt": "prompt-v5",
    "model": "model-candidate",
    "pipeline": "rag-v2",
    "corpus": "policy-v3"
  },
  "triageStatus": "OPEN"
}
~~~

Đây là **dữ liệu giả định**. `traceRef=null` thể hiện trace không có; không tạo một ID tượng trưng rồi nói đã liên kết thành công. Nếu `actualSummary` hoặc `expectedSummary` chứa dữ liệu cá nhân, phải loại hoặc giới hạn truy cập phù hợp.

### 9.3. Ví dụ khung báo cáo Markdown cho con người

~~~text
# Evaluation report — candidate-v2

Dataset: support-eval-v3
Rubric/Judge: quality-rubric-v2 / judge-v1
Run status: COMPLETED

Execution:
  120 selected, 4 skipped
  116 eligible, 111 completed, 5 technical errors

Quality (on completed cases):
  90 PASS, 16 FAIL, 5 inconclusive
  Evaluated pass rate: 90 / 106 = 84.91%
  Evaluated coverage: 106 / 111 = 95.50%

Critical:
  [counts by PASS / FAIL / ERROR / SKIP / INCONCLUSIVE]

Failures:
  16 quality failures + 5 technical errors
  [full list in failures.jsonl]

Operational:
  [p95 latency, tokens, estimated cost, retries, 429]
  [measurement scope and coverage]

Release decision:
  [gate result + reasons + artifact references]
~~~

Con số và chú thích trong dấu ngoặc vuông là placeholders; khi phát hành một báo cáo thật, phải thay bằng giá trị thực hoặc ghi `NOT_AVAILABLE`.

## 10. Quy trình tạo report: chuẩn hóa → kiểm toàn vẹn → tổng hợp → xuất bản

~~~mermaid
flowchart TD
    A["Dataset snapshot + run manifest"] --> B["All case outcomes"]
    B --> C{"Một kết quả được chọn<br/>theo policy cho mỗi case?"}
    C -- "Chưa" --> X["Giữ run PARTIAL / điều tra duplicates"]
    C -- "Có" --> D["Normalize status + IDs"]
    D --> E["Aggregate counts / per-metric slices"]
    D --> F["Build failure list"]
    D --> G["Build gaps and skipped lists"]
    E --> H["Validate invariants"]
    F --> H
    G --> H
    H --> I{"Counts + IDs nhất quán?"}
    I -- "Không" --> X
    I -- "Có" --> J["Generate JSON/Markdown + gate"]
    J --> K["Immutable report artifacts"]
~~~

Những invariant tối thiểu cần xác minh:

1. `selected = skipped + eligible`.
2. Khi run đã hoàn tất: `eligible = technicalCompleted + technicalError` (với điều kiện không còn cancelled/unstarted).
3. `technicalCompleted = qualityPass + qualityFail + qualityInconclusive` khi aggregate theo một rubric đã xác định.
4. `qualityEvaluated = qualityPass + qualityFail`.
5. `failures` chứa đúng **một dòng cho mỗi case quality FAIL hoặc technical ERROR** theo chính sách xuất bản — không đếm số metric FAIL thay cho số case.
6. `evaluationGaps` chứa đủ các case INCONCLUSIVE.
7. `skippedCases` chứa đủ SKIPPED và reason.
8. Mọi ID trong report phải có trong dataset/run hoặc có giải thích, không trộn attempts giữa hai run.
9. Mọi reference tới evidence và trace đều hợp lệ hoặc được đánh dấu unavailable.
10. Với run PARTIAL, counts phải ghi nhận ca chưa hoàn tất, không giả vờ tất cả eligible đã chạy.

Đặc biệt, **một ca có thể fail ba metric** nhưng vẫn là **một case trong failure list**. Có thể bổ sung danh sách metric violations lồng bên trong dòng đó.

## 11. Java: mô hình dữ liệu cho bộ tổng hợp

Ví dụ Java 17+ sau đây minh họa một **bộ tạo summary đơn giản**, không phụ thuộc provider. Nó giả định người gọi đã chuẩn hóa **một terminal outcome trên mỗi planned case trong một run**. Trong hệ thống thật, dữ liệu raw retries/LLM judge attempts phải được chuẩn hóa trước bước này.

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class EvaluationReportBuilder {

    public enum Execution {
        COMPLETED, ERROR, SKIPPED, CANCELLED, NOT_STARTED
    }

    public enum Quality {
        PASS, FAIL, INCONCLUSIVE, NOT_APPLICABLE
    }

    public record CaseOutcome(
            String caseId,
            String attemptId,
            String group,
            boolean critical,
            Execution execution,
            Quality quality,
            String primaryMetric,
            String reasonCode,
            String traceRef) {

        public CaseOutcome {
            Objects.requireNonNull(caseId);
            Objects.requireNonNull(execution);
            Objects.requireNonNull(quality);
        }
    }

    public record Counts(
            int selected,
            int skipped,
            int eligible,
            int completed,
            int technicalErrors,
            int qualityPass,
            int qualityFail,
            int qualityInconclusive,
            int notFinished,
            int qualityEvaluated) {}

    public record FailureRow(
            String caseId,
            String attemptId,
            String group,
            boolean critical,
            String failureType,
            String primaryMetric,
            String reasonCode,
            String traceRef) {}

    public record GapRow(
            String caseId,
            String attemptId,
            String reasonCode) {}

    public record Report(
            Counts summary,
            List<FailureRow> failures,
            List<GapRow> gaps,
            boolean runExecutionComplete) {}

    public static Report build(List<CaseOutcome> outcomes) {
        Objects.requireNonNull(outcomes);

        Set<String> seenCases = new HashSet<>();
        List<FailureRow> failures = new ArrayList<>();
        List<GapRow> gaps = new ArrayList<>();

        int skipped = 0;
        int completed = 0;
        int errors = 0;
        int pass = 0;
        int fail = 0;
        int inconclusive = 0;
        int notFinished = 0;

        for (CaseOutcome row : outcomes) {
            if (!seenCases.add(row.caseId())) {
                throw new IllegalArgumentException(
                        "Duplicate caseId: " + row.caseId());
            }

            switch (row.execution()) {
                case SKIPPED -> skipped++;

                case ERROR -> {
                    errors++;
                    failures.add(failure(row, "TECHNICAL_ERROR"));
                }

                case COMPLETED -> {
                    completed++;
                    switch (row.quality()) {
                        case PASS -> pass++;
                        case FAIL -> {
                            fail++;
                            failures.add(failure(row, "QUALITY_FAIL"));
                        }
                        case INCONCLUSIVE -> {
                            inconclusive++;
                            gaps.add(new GapRow(
                                    row.caseId(), row.attemptId(),
                                    row.reasonCode()));
                        }
                        case NOT_APPLICABLE -> throw new
                                IllegalArgumentException(
                                "Missing aggregate quality for case "
                                        + row.caseId());
                    }
                }

                case NOT_STARTED, CANCELLED -> {
                    notFinished++;
                    gaps.add(new GapRow(
                            row.caseId(), row.attemptId(),
                            "EXECUTION_NOT_FINISHED"));
                }
            }
        }

        int selected = outcomes.size();
        int eligible = selected - skipped;
        int evaluated = pass + fail;

        Counts counts = new Counts(
                selected, skipped, eligible, completed, errors,
                pass, fail, inconclusive, notFinished, evaluated);

        return new Report(
                counts,
                List.copyOf(failures),
                List.copyOf(gaps),
                notFinished == 0);
    }

    private static FailureRow failure(
            CaseOutcome row, String type) {

        return new FailureRow(
                row.caseId(),
                row.attemptId(),
                row.group(),
                row.critical(),
                type,
                row.primaryMetric(),
                row.reasonCode(),
                row.traceRef());
    }

    private EvaluationReportBuilder() {}
}
~~~

### 11.1. Những điểm code này làm được

- Đếm **một case một lần**, phát hiện `caseId` trùng.
- Giữ riêng SKIPPED, ERROR, COMPLETED và NOT_STARTED/CANCELLED.
- Tách quality PASS, FAIL, INCONCLUSIVE trong nhóm COMPLETED.
- Tạo một `FailureRow` cho mỗi case quality FAIL hoặc technical ERROR.
- Tạo danh sách khoảng trống đánh giá/ca chưa hoàn tất riêng.
- Không trả trạng thái run hoàn tất nếu còn NOT_STARTED hoặc CANCELLED.

### 11.2. Những điểm chưa được code này bảo đảm

Đây là ví dụ giáo dục cho một bước **sau normalization**, không phải triển khai đầy đủ của hệ thống báo cáo:

- Nó chưa lấy dataset snapshot để phát hiện **case bị thiếu hoàn toàn** trong danh sách input. Muốn vậy phải đối chiếu `caseId` với tập case đã chọn ban đầu.
- Nó chưa validate mọi tổ hợp trạng thái không hợp lệ (ví dụ ERROR đi cùng quality PASS) hoặc số lượng metric required.
- Nó chưa tổng hợp per-metric results, percentiles, token/cost hoặc critical gate.
- Nó chưa chọn retry attempt nào là bản hợp lệ; việc này phải có policy riêng.
- Nó chưa lưu artifacts vào kho bền vững và không kiểm chứng evidence refs.
- Với `NOT_STARTED` hoặc `CANCELLED`, nó chỉ ghi gap, không có failure row; báo cáo phải hiển thị danh sách đó rõ.
- `runExecutionComplete` không khẳng định mọi metric đã được chấm, chỉ là cờ không còn case ở trạng thái execution chưa kết thúc.

Trong dự án thật, có thể bổ sung validation của `runId`, `rubricVersion`, `attemptId`, required metrics và tính toàn vẹn bằng một schema riêng.

## 12. Java/JUnit: kiểm tổng hợp không bị sai mẫu số

Trước khi tin vào báo cáo AI, cần kiểm các bất biến bằng test thông thường.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class EvaluationReportBuilderTest {

    private EvaluationReportBuilder.CaseOutcome row(
            String id,
            EvaluationReportBuilder.Execution execution,
            EvaluationReportBuilder.Quality quality,
            String reason) {

        return new EvaluationReportBuilder.CaseOutcome(
                id,
                "attempt-" + id,
                "demo",
                false,
                execution,
                quality,
                "factualCorrectness",
                reason,
                null);
    }

    @Test
    void countsFourOutcomeFamiliesSeparately() {
        var report = EvaluationReportBuilder.build(List.of(
                row("pass", EvaluationReportBuilder.Execution.COMPLETED,
                        EvaluationReportBuilder.Quality.PASS, null),
                row("fail", EvaluationReportBuilder.Execution.COMPLETED,
                        EvaluationReportBuilder.Quality.FAIL, "WRONG_FACT"),
                row("error", EvaluationReportBuilder.Execution.ERROR,
                        EvaluationReportBuilder.Quality.NOT_APPLICABLE,
                        "PROVIDER_TIMEOUT"),
                row("skip", EvaluationReportBuilder.Execution.SKIPPED,
                        EvaluationReportBuilder.Quality.NOT_APPLICABLE,
                        "NO_SANDBOX"),
                row("gap", EvaluationReportBuilder.Execution.COMPLETED,
                        EvaluationReportBuilder.Quality.INCONCLUSIVE,
                        "JUDGE_TIMEOUT")));

        var s = report.summary();

        assertEquals(5, s.selected());
        assertEquals(1, s.skipped());
        assertEquals(4, s.eligible());
        assertEquals(3, s.completed());
        assertEquals(1, s.technicalErrors());
        assertEquals(1, s.qualityPass());
        assertEquals(1, s.qualityFail());
        assertEquals(1, s.qualityInconclusive());
        assertEquals(2, s.qualityEvaluated());
        assertEquals(2, report.failures().size());
        assertEquals(1, report.gaps().size());
        assertTrue(report.runExecutionComplete());
    }

    @Test
    void rejectsDuplicateCaseIds() {
        var a = row("A",
                EvaluationReportBuilder.Execution.COMPLETED,
                EvaluationReportBuilder.Quality.PASS, null);

        assertThrows(IllegalArgumentException.class,
                () -> EvaluationReportBuilder.build(List.of(a, a)));
    }

    @Test
    void incompleteBatchIsNotFinal() {
        var report = EvaluationReportBuilder.build(List.of(
                row("A", EvaluationReportBuilder.Execution.COMPLETED,
                        EvaluationReportBuilder.Quality.PASS, null),
                row("B", EvaluationReportBuilder.Execution.NOT_STARTED,
                        EvaluationReportBuilder.Quality.NOT_APPLICABLE,
                        "RUN_CANCELLED")));

        assertFalse(report.runExecutionComplete());
        assertEquals(1, report.summary().notFinished());
    }
}
~~~

Nếu các test qua, ta có cơ sở tin rằng **logic đếm** của bước này đúng với dữ liệu giả lập; điều đó không tự chứng minh evaluator fact checking, model hoặc dataset thật đúng.

### 12.1. Test bổ sung nên thực hiện

- Dataset rỗng → không chia cho 0, báo `N/A` cho tỷ lệ.
- Ca FAIL ba metric → một dòng trong failure list, ba metric violations trong chi tiết.
- Đủ 120 outcome với phân bố 4/5/90/16/5 → counts khớp ví dụ.
- Ca critical bị skip → release gate phát hiện dù quality pass rate cao.
- Số outcome thấp hơn số case trong manifest → run bị coi không đầy đủ.
- Verdict thuộc judge version khác → bị loại khỏi phạm vi report hoặc báo mismatch, không ghép tùy tiện.
- Retry nhiều lần → một accepted outcome, nhưng attempt history vẫn lưu đầy đủ.
- Evidence refs mất quyền hoặc không tồn tại → đánh dấu lỗi dữ liệu báo cáo, không khẳng định đã tra cứu được.

## 13. Tạo Markdown/HTML report an toàn cho con người

Summary có thể được sinh tự động từ `Counts`, nhưng xuất HTML hay Markdown đều cần xử lý dữ liệu đầu vào.

Ví dụ đơn giản không phụ thuộc thư viện ngoại:

~~~java
public final class MarkdownReport {

    public static String render(
            EvaluationReportBuilder.Report report) {

        var s = report.summary();
        StringBuilder out = new StringBuilder();

        out.append("# Evaluation summary\n\n");
        out.append("| Metric | Count |\n");
        out.append("| --- | ---: |\n");
        out.append("| Selected | ").append(s.selected()).append(" |\n");
        out.append("| Skipped | ").append(s.skipped()).append(" |\n");
        out.append("| Eligible | ").append(s.eligible()).append(" |\n");
        out.append("| Technical completed | ")
                .append(s.completed()).append(" |\n");
        out.append("| Technical error | ")
                .append(s.technicalErrors()).append(" |\n");
        out.append("| Quality PASS | ")
                .append(s.qualityPass()).append(" |\n");
        out.append("| Quality FAIL | ")
                .append(s.qualityFail()).append(" |\n");
        out.append("| Inconclusive | ")
                .append(s.qualityInconclusive()).append(" |\n");

        out.append("\n## Failures\n\n");
        out.append("| Case | Type | Reason |\n");
        out.append("| --- | --- | --- |\n");

        for (var failure : report.failures()) {
            out.append("| ")
                    .append(safe(failure.caseId())).append(" | ")
                    .append(safe(failure.failureType())).append(" | ")
                    .append(safe(failure.reasonCode())).append(" |\n");
        }

        return out.toString();
    }

    private static String safe(String value) {
        if (value == null) return "N/A";
        // Ngăn chuỗi tuỳ ý phá cấu trúc bảng Markdown.
        return value.replace("|", "\\|")
                .replace("\r", " ")
                .replace("\n", " ");
    }

    private MarkdownReport() {}
}
~~~

Ở ví dụ, `safe()` chỉ xử lý ký tự phá bảng **Markdown**, không phải một bộ lọc HTML/security hay biện pháp ẩn dữ liệu cá nhân hoàn chỉnh. Khi xuất HTML, cần escaping theo context HTML; khi tạo liên kết tới evidence, chỉ dùng URL được cấp từ hệ thống đáng tin và có kiểm soát truy cập.

Trong môi trường CI, người đọc nên có thể tải cả `summary.json` và `failures.jsonl`; bản Markdown chỉ để đọc nhanh, không thay artifact máy đọc được.

## 14. Xếp ưu tiên danh sách lỗi thay vì đọc theo thứ tự dataset

Một failure list 500 dòng thường quá dài. Hãy sắp theo **mức rủi ro và tác động**, nhưng đừng giấu toàn bộ lỗi ít nghiêm trọng.

### 14.1. Ma trận ưu tiên

| Ưu tiên | Ví dụ | Hành động |
| --- | --- | --- |
| **P0 / Critical** | Tool vượt quyền, rò dữ liệu, thao tác gây tác dụng phụ sai | Chặn release, xử lý khẩn |
| **P1 / High** | Factual error trên chính sách quan trọng, missing evidence có tác động lớn | Điều tra trước mở rộng rollout |
| **P2 / Medium** | Relevance sai ở một nhóm hữu hạn, citation kém | Lập kế hoạch sửa và regression |
| **P3 / Low** | Lỗi trình bày không gây hiểu sai, format thứ yếu | Theo dõi/sửa sau theo tiêu chí sản phẩm |
| **Operational** | 429, timeout, judge failure, unscored case | Sửa độ tin cậy và coverage |

Phân loại `critical` phải dựa trên nghiệp vụ và quyền, **không tự động đánh giá** mọi câu trả lời sai là cùng một mức nguy hiểm. Với nguồn gây ảnh hưởng thực tế, cần domain review.

### 14.2. Gom nhóm lỗi có thể giảm số lần điều tra

Nếu 20 ca FAIL đều truy xuất `policy-v2` thay `policy-v3`, một root cause về index freshness có thể giải quyết nhiều ca. Nên báo:

- `failureFamily` và `reasonCode`.
- `corpusVersion`/`indexVersion`.
- Nhóm question/intent.
- Model/prompt/pipeline version.
- First observed và số ca bị ảnh hưởng.

Tuy nhiên, việc gom 20 case vào một issue không có nghĩa report mất 19 case. Failure list vẫn phải giữ mỗi case và tham chiếu issue liên quan.

### 14.3. Tránh coi LLM judge feedback là root cause chắc chắn

Nếu evaluator ghi “answer không có căn cứ”, đây là **verdict và feedback**, chưa chứng minh lỗi nằm ở retriever. Cần xem actual retrieved docs, effective context, prompt, model/tool events.

Một số vấn đề có thể do judge đánh giá sai hoặc rubric không phù hợp. Các ca có tác động cao nên được người am hiểu nghiệp vụ xác minh.

## 15. So sánh baseline/candidate: danh sách hồi quy quan trọng hơn điểm tổng

Một candidate có pass rate cao hơn vẫn có thể làm hỏng một ca critical từng PASS. Vì vậy report cần danh sách **transition theo case**.

Ví dụ cùng 100 case, được chấm trên cùng dataset và rubric:

- Baseline PASS 81.
- Candidate PASS 85.
- 10 ca `FAIL → PASS`.
- 6 ca `PASS → FAIL`.
- Còn lại không thay đổi nhãn PASS/FAIL.

Kiểm tra: `81 + 10 − 6 = 85`.

### 15.1. Bảng chuyển trạng thái

| Trạng thái baseline → candidate | Số ca | Ý nghĩa |
| --- | ---: | --- |
| FAIL → PASS | 10 | Ca đã được sửa theo rubric |
| PASS → FAIL | 6 | **Regression** cần điều tra |
| PASS → PASS | 75 | Giữ được kết quả đạt |
| FAIL → FAIL | 9 | Lỗi vẫn tồn tại |
| **Tổng** | **100** | Cùng một bộ case |

Dù candidate tăng 4 điểm phần trăm, vẫn có **6 ca hồi quy**. Nếu một trong số đó là ca kiểm tra quyền tool, release gate nên chặn dù điểm tổng cải thiện.

### 15.2. Điều kiện bắt buộc để so công bằng

Kiểm tra trước khi tạo report diff:

1. Dataset ID/version và snapshot/digest có tương đương không?
2. Reference facts và ngày hiệu lực của nguồn có giống nhau không?
3. Rubric/judge version hoặc phương pháp chấm có tương thích không?
4. Các ca có cùng eligibility và skip policy không?
5. Model/provider và điều kiện tải nào thay đổi?
6. Có ca lỗi kỹ thuật hoặc NOT_EVALUATED ở một phía không?

Nếu baseline PASS nhưng candidate không chạy vì provider ERROR, đó là **completion regression** hoặc missing evidence, không tự động là `PASS → FAIL về factual correctness`.

### 15.3. Phân loại transition đầy đủ hơn

Khi cần, dùng các nhóm:

- `NEW_QUALITY_FAILURE`: PASS → FAIL.
- `FIXED_FAILURE`: FAIL → PASS.
- `PERSISTENT_FAILURE`: FAIL → FAIL.
- `PERSISTENT_PASS`: PASS → PASS.
- `NEW_TECHNICAL_ERROR`: candidate ERROR.
- `NEW_EVALUATION_GAP`: candidate chưa có verdict.
- `NEW_SKIP`: candidate không chạy.
- `UNCOMPARABLE`: case/rubric/source thay đổi.

**Không** xếp ERROR và INCONCLUSIVE vào cùng nhóm FAIL ngữ nghĩa chỉ để vẽ bảng đẹp.

### 15.4. So theo từng metric cũng cần thiết

Một ca có factual PASS ở cả hai bản nhưng groundedness chuyển PASS → FAIL thì đó là hồi quy groundedness. Ngược lại, retrieval hit@k có thể tăng trong khi factual correctness giảm. Báo cáo nên có transition theo metric trọng yếu và nhóm case.

## 16. Liên kết báo cáo với metrics, traces và chi phí

Một report có PASS/FAIL nhưng thiếu telemetry vẫn trả lời được “ca nào sai”, song khó biết vì sao latency tăng hoặc chi phí thay đổi.

| Tín hiệu | Nguồn | Nên báo theo |
| --- | --- | --- |
| Technical failure rate | Runner/provider/tool outcomes | Run, group, release |
| p50/p95/p99 latency | Timers/histogram/tracing | Phạm vi request và sample size |
| Retrieval latency | VectorStore spans/metrics | RAG pipeline/index |
| Model latency | ChatModel observations | Model/provider/version |
| Tool errors/timeout | Tool/backend events | Tool type, outcome |
| Token usage | Provider usage nếu có | Model call, attempt, run |
| Estimated cost | Token + pricing version + thành phần khác | Request, completed task, run |
| Judge latency/cost | Evaluation stage | Tách khỏi chi phí ứng dụng |
| Quality pass rate | Rubric + labels/evidence | Dataset/metric/group |
| Failure trace reference | Tracing backend | Một attempt cụ thể |

### 16.1. Ví dụ trace cho một ca factual FAIL

~~~text
POST /ask                        1.8 s (technical success)
└── ChatClient                   1.6 s
    ├── VectorStore retrieval    0.3 s
    └── ChatModel                1.1 s

Actual retrieved: policy-v2#refund
Actual answer: "30 ngày"
Reference: policy-v3#refund, "14 ngày"
Factual correctness: FAIL
~~~

Lỗi ở đây có dấu hiệu retrieval/corpus freshness; trace giúp thấy bước thực thi nhưng **không tự xác minh câu trả lời đúng nguồn**. Phải đối chiếu evidence và reference facts.

### 16.2. Ví dụ trace cho một ca technical ERROR

~~~text
POST /ask                       25.0 s (error)
└── ChatClient                  24.8 s
    └── ChatModel provider      24.5 s (timeout)

Execution: ERROR
Reason: PROVIDER_TIMEOUT
Answer quality: NOT_EVALUATED
~~~

Đây là lỗi vận hành. Không có output hợp lệ để chấm factual correctness nên không được cộng vào quality FAIL, nhưng phải đưa vào technical error rate và release gate.

### 16.3. Cách ước tính chi phí

Với bảng giá **giả định** theo triệu token:

\[
\mathrm{modelCost} =
\frac{\mathrm{inputTokens}\times \mathrm{inputPricePerMillion}}
{10^6}
+
\frac{\mathrm{outputTokens}\times \mathrm{outputPricePerMillion}}
{10^6}.
\]

Ví dụ 2.000 input tokens giá 2 USD/triệu và 500 output tokens giá 8 USD/triệu:

\[
\frac{2000\times2+500\times8}{10^6}
=0{,}008\ \mathrm{USD}.
\]

Một attempt có tool calling có thể gọi ChatModel nhiều lần; phải cộng usage của các model calls. Chi phí thực tế còn có embedding, reranking, backend, retry, cache và judge. Cần lưu `priceTableVersion`, đơn vị tiền và phương pháp ước tính; không tự coi phí của ca ERROR là 0 nếu provider có thể đã xử lý/tính phí một phần.

### 16.4. p95 không thể suy từ tổng thời gian và count

Nếu chỉ có timer `sum` và `count`, tính được mean nhưng không tính được p95. Cần dữ liệu phân bố/histogram được cấu hình và cách tổng hợp hợp lệ. Một giá trị p95 không có cửa sổ đo và phạm vi request rất khó dùng để so phiên bản.

### 16.5. Không dùng case ID làm metric labels

`caseId`, raw prompt, user ID và trace ID có thể tạo high cardinality và rủi ro thông tin. Đưa chúng vào **artifact/evidence store** có quyền, còn metrics nên dùng tags có tập giá trị nhỏ như `runCategory`, `releaseVersion`, `stage`, `status`.

## 17. Báo cáo production: lấy mẫu và nhãn đến muộn

Offline report thường dựa trên dataset đã có nguồn chuẩn. Với production traffic, chỉ một phần câu trả lời có thể được chấm ngay; nhãn có thể chờ chuyên gia hoặc không có vì quyền riêng tư.

Một dashboard online cần tách:

- Tổng request production thuộc phạm vi đo.
- Request hoàn thành kỹ thuật và error.
- Số được chọn mẫu để đánh giá.
- Số mẫu đã có verdict PASS/FAIL.
- Số mẫu PENDING/NOT_EVALUATED.
- Sampling policy, phân tầng/nhóm rủi ro.
- Thay đổi cơ cấu câu hỏi giữa các cửa sổ thời gian.

Nếu lấy mẫu ưu tiên ca bị người dùng báo sai, tỷ lệ lỗi trong mẫu này sẽ cao hơn traffic thông thường; nó rất hữu ích để **điều tra**, nhưng không tự là ước lượng không thiên lệch của tỷ lệ lỗi toàn hệ thống.

### 17.1. Một ví dụ mẫu số online

Giả sử:

~~~text
Production requests:      10.000
Selected for review:         300
Review completed:            240
Quality PASS:                216
Quality FAIL:                 24
Review pending/unavailable:   60
~~~

Tỷ lệ PASS trên tập được chấm: `216/240=90%`. Coverage của mẫu: `240/300=80%`. Đây **không phải** bằng chứng 90% toàn bộ 10.000 request production đúng, trừ khi thiết kế lấy mẫu/ước lượng và xử lý nhãn thiếu hỗ trợ kết luận ấy.

### 17.2. Drift khác regression

Nếu tỷ trọng câu hỏi không có nguồn tăng, pass rate tổng có thể giảm dù năng lực model trong từng nhóm không đổi. Vì vậy summary nên báo quality theo **nhóm tác vụ và tỷ trọng traffic**. Nếu đổi judge/rubric, đánh dấu điểm gãy trên biểu đồ, không quy thay đổi score cho model ngay lập tức.

## 18. Release gates: lấy từ báo cáo, không tự chọn sau khi thấy điểm

Một release gate giả định:

~~~yaml
releaseGate:
  datasetVersion: support-eval-v3
  rubricVersion: quality-rubric-v2
  required:
    criticalCasesSkipped: 0
    criticalCasesNotEvaluated: 0
    criticalFunctionalTests: must-pass
  quality:
    factualCorrectnessPassRate: ">= 0.98"
    groundednessPassRate: ">= 0.95"
    noNewCriticalRegression: true
  operations:
    minEligibleTechnicalCompletion: 0.99
    p95LatencyMs: "<= 2500"
    maxModelCostUsdPerRequest: 0.01
~~~

**Ngưỡng hoàn toàn minh họa**, không phải mặc định của Spring AI. Một hệ thống thật phải định nghĩa ngưỡng theo nghiệp vụ, rủi ro, cỡ mẫu và độ tin cậy rubric.

### 18.1. Báo cáo gate nên có trạng thái rõ

| Gate outcome | Ý nghĩa |
| --- | --- |
| `PASS` | Đủ bằng chứng, mọi điều kiện cần đều đạt |
| `BLOCKED_QUALITY` | Có metric/case bắt buộc FAIL |
| `BLOCKED_TECHNICAL` | Technical error/SLO vi phạm |
| `BLOCKED_INSUFFICIENT_EVIDENCE` | Critical skip, chưa chấm hoặc run partial |
| `NEEDS_REVIEW` | Cần chuyên gia xác minh ca quan trọng |

**Chặn phát hành vì thiếu bằng chứng khác với chấm factual correctness FAIL.** Report phải giữ đúng lý do để nhóm sửa vấn đề phù hợp.

### 18.2. Không được bù lỗi nghiêm trọng bằng điểm trung bình

Nếu có một ca tool vượt quyền nhưng 119 ca khác đều PASS relevance, release gate về authorization vẫn phải FAIL nếu là tiêu chí bắt buộc. Điểm tổng hợp chỉ phục vụ tóm tắt, không thay các gate chức năng và an toàn.

## 19. Quyền riêng tư, lưu trữ và chất lượng dữ liệu báo cáo

Failure list có thể chứa thông tin nghiệp vụ nhạy cảm. Trước khi xuất report:

1. Không đưa API key, token xác thực, password vào JSON/Markdown.
2. Dùng `questionRef`/`answerRef` nếu raw question/answer chứa dữ liệu cá nhân.
3. Lưu actual retrieved context và tool results trong evidence store phân quyền, có thời hạn lưu.
4. Chỉ lưu các IDs/metadata cần thiết trong bảng tổng quan.
5. Không gửi dữ liệu production cho external LLM judge nếu chưa có cơ chế kiểm soát phù hợp.
6. Ghi version và ngày hiệu lực của nguồn chuẩn, tránh làm mờ phân biệt chính sách cũ/mới.
7. Khi report có liên kết tải, kiểm tra quyền truy cập và khả năng hết hạn của link.
8. Giữ audit khi sửa nhãn/expected facts hoặc judge version.
9. Không silently overwrite báo cáo đã dùng để phê duyệt release.

Một báo cáo đầy đủ về mặt kỹ thuật chưa chắc được phép chia sẻ nguyên vẹn với mọi người. Có thể cung cấp **executive summary không nhạy cảm** và **evidence details được phân quyền**.

## 20. Bài thực hành: tạo summary + failure list cho 120 ca

**Bối cảnh:** chatbot Spring AI xử lý chính sách hoàn phí giả định bằng RAG và đọc trạng thái đơn qua tool `getOrderStatus`. Mục tiêu là xuất một bộ artifacts có thể dùng để kiểm release và mở từng ca lỗi.

### Phần A — Chuẩn bị dữ liệu

Tạo dataset 120 case với 4 nhóm: chính sách có nguồn, thiếu nguồn, tool calling và hội thoại nhiều lượt. Mỗi ca cần `caseId`, group, critical flag, expected facts/tool behavior và rubric.

Chạy runner có giới hạn đồng thời, giữ `runId`, `attemptId`, config versions và attempt evidence.

### Phần B — Gắn trạng thái đúng

Mô phỏng một số ca quality FAIL, provider timeout/429, evaluator timeout và SKIPPED có chủ đích. Với mỗi case, ghi execution outcome và các metric verdict độc lập.

Áp dụng quy tắc aggregate. Xác nhận một ca `COMPLETED + FACTUAL_FAIL` không bị tính là technical error, và một ca `COMPLETED + NOT_EVALUATED` không biến thành PASS.

### Phần C — Xây báo cáo tổng hợp

Tính selected, eligible, skipped, completed, errors, quality PASS/FAIL/INCONCLUSIVE, coverage và các tỷ lệ có mẫu số. Chia nhóm và báo các ca critical.

Kiểm invariant tổng đếm, xử lý trường hợp `denominator=0` bằng N/A. Không dùng pass rate chung khi một nhóm trọng yếu có quá ít ca.

### Phần D — Xuất failure list

Với mỗi case quality FAIL hoặc technical ERROR, lưu `caseId`, `attemptId`, family, reason, severity, expected/actual summary đã xử lý riêng tư, evidence refs và trace ref nếu có.

Đồng thời xuất danh sách evaluation gaps và skipped cases. Sắp failure list theo mức ưu tiên mà vẫn giữ đầy đủ các ca.

### Phần E — So baseline/candidate

Chạy cùng dataset và rubric trên hai phiên bản prompt hoặc RAG. Tạo bảng `PASS→FAIL` và `FAIL→PASS`, kèm ca biến thành ERROR/INCONCLUSIVE. Kiểm tra rằng report không gán lỗi kỹ thuật cho model factuality.

### Phần F — Liên kết vận hành

Đo p95 latency bằng telemetry có histogram hoặc phân bố phù hợp; ghi input/output tokens và chi phí ước tính theo model, tách chi phí evaluator. Với ít nhất một failure, dùng trace/evidence để đề xuất một giả thuyết có thể kiểm chứng.

### Checklist nghiệm thu

- [ ] Báo cáo khai báo dataset/prompt/model/pipeline/rubric/judge versions.
- [ ] Run status rõ, không gắn COMPLETED cho run partial.
- [ ] Tập planned case được đối chiếu với outcomes.
- [ ] Một case có retry không bị đếm nhiều lần.
- [ ] Execution và evaluation statuses không bị trộn.
- [ ] Mọi tỷ lệ có mẫu số và xử lý denominator=0.
- [ ] Báo cáo quality theo nhóm và critical.
- [ ] Tổng số quality FAIL + technical ERROR khớp failure list.
- [ ] Có danh sách riêng cho INCONCLUSIVE và SKIPPED.
- [ ] Mỗi failure có reason, metric và evidence/trace ref nếu khả dụng.
- [ ] So baseline/candidate trên phạm vi tương thích.
- [ ] Có bảng các ca regression, không chỉ điểm tổng.
- [ ] p95/token/cost được báo theo phạm vi/giả định đo rõ.
- [ ] Không công bố raw dữ liệu nhạy cảm ngoài quyền cho phép.
- [ ] Release gate chặn lỗi critical hoặc thiếu bằng chứng bắt buộc.

### Câu hỏi tự kiểm tra

1. Vì sao không thể gọi HTTP 200 là quality PASS?
2. Một case có 3 metric FAIL được đếm một hay ba lần trong failure list cấp case?
3. Khi một case chạy lại hai lần sau timeout, chọn attempt để tổng hợp theo quy tắc nào?
4. Với 120 case, 4 skipped, 5 technical errors, 90 PASS, 16 FAIL và 5 inconclusive, hãy tính technical completion và evaluated quality pass rate.
5. Vì sao cần tách failures, evaluation gaps và skipped cases?
6. Một trace thành công có đủ để kết luận factual correctness PASS không?
7. Khi retrieval tìm được tài liệu cũ nhưng answer bám sát tài liệu đó, groundedness và factual correctness có thể khác nhau thế nào?
8. Vì sao cần giữ per-metric report và version judge/rubric?
9. Candidate tăng từ 81 lên 85 PASS nhưng có 6 ca PASS→FAIL: bạn cần xem gì trước khi cho phát hành?
10. Nếu judge timeout khiến case chưa chấm, có nên ghi chất lượng FAIL không? Release gate có thể làm gì?
11. Vì sao p95 không thể tính từ timer sum và count?
12. Một mẫu online ưu tiên ticket báo lỗi có đại diện cho toàn traffic không?
13. Có thể ghi raw user input làm metric tag để lọc theo từng case không?
14. Một report có 16 quality FAIL và 5 technical ERROR nhưng failure list chỉ 18 case là vấn đề gì?

## 21. Những sai lầm thường gặp

**Sai lầm 1 — Chỉ báo “số ca đạt”.** Thiếu mẫu số, coverage và nhóm lỗi.

**Sai lầm 2 — Đếm retry như nhiều case.** Phải phân biệt case và attempt.

**Sai lầm 3 — Cộng metric PASS rồi chia cho tổng case.** Một case có nhiều metrics; mỗi tỷ lệ cần mẫu số và phạm vi riêng.

**Sai lầm 4 — Gộp technical error vào factual FAIL.** Khi không có output hợp lệ, không đủ dữ liệu để chấm câu trả lời.

**Sai lầm 5 — Xóa ca chưa chấm để tăng pass rate.** Phải báo INCONCLUSIVE và evaluation coverage.

**Sai lầm 6 — Hiển thị 10 lỗi đầu nhưng không nói danh sách bị cắt.** Artifacts phải giữ được đầy đủ ca lỗi hoặc công bố phân trang rõ.

**Sai lầm 7 — Dùng expected documents thay actual context.** Che lỗi RAG retrieval, làm groundedness giả tạo.

**Sai lầm 8 — Coi judge feedback là nguyên nhân chắc chắn.** Cần trace và execution evidence xác minh.

**Sai lầm 9 — Thấy pass rate tăng rồi bỏ qua ca regression critical.** So per-case transition.

**Sai lầm 10 — So hai run khác dataset/rubric không ghi chú.** Có thể làm kết luận cải thiện sai.

**Sai lầm 11 — Quên skip/error trong release gate.** Ca critical chưa kiểm không thể được xem như đã PASS.

**Sai lầm 12 — Dùng raw prompt/ID nhạy cảm trong dashboard.** Vừa rò dữ liệu vừa làm metric cardinality tăng.

## 22. Tổng kết

Một báo cáo đánh giá Spring AI có giá trị khi nó giải quyết được hai câu hỏi song song: **toàn bộ ứng dụng và các nhóm tác vụ đạt đến đâu**, và **chính xác ca nào chưa đạt hoặc không thể đánh giá, vì sao**.

**Summary report** phải công bố run/dataset/rubric versions, số ca selected/eligible/completed/skipped/error, quality PASS/FAIL/INCONCLUSIVE, các mẫu số, slices, hồi quy so baseline và số liệu độ trễ/chi phí. **Failure list** phải chứa từng case có quality FAIL hoặc technical ERROR với reason code, metric, severity, expected/actual evidence và trace reference có thật. Các ca NOT_EVALUATED và SKIPPED cần danh sách riêng.

Khi summary, failure list và các evidence artifacts liên kết đúng bằng `runId`, `caseId` và `attemptId`, nhóm có thể biến một điểm số thành kế hoạch điều tra cụ thể, sửa đúng khâu RAG, model, tool hoặc evaluator, rồi chạy lại bộ hồi quy trước khi phát hành.

### Tài liệu tham khảo

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
