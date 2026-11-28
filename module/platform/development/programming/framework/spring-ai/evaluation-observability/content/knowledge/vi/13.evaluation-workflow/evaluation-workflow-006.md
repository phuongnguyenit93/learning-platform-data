# So sánh kết quả với đường cơ sở đã xác nhận

Một nhóm phát triển ứng dụng Spring AI vừa đổi prompt và nhận được báo cáo: **tỷ lệ ca đạt tăng từ 82% lên 85%**. Có nên phát hành ngay? Chưa chắc. Trong 100 ca đánh giá, phiên bản mới có thể sửa được 9 ca từng sai nhưng lại làm hỏng 6 ca từng đúng; một trong sáu ca bị hỏng có thể kiểm tra quyền truy cập của tool hoặc tính đúng của một chính sách quan trọng.

Một phép so sánh đáng tin cần nhiều hơn hai tỷ lệ. Nhóm phải biết **đường cơ sở (baseline) đã được xác nhận** là phiên bản nào, được chấm trên dataset và nguồn chuẩn nào, cách chấm có thay đổi không, từng case chuyển trạng thái ra sao, và độ trễ, token, chi phí có thay đổi trong điều kiện đo tương đương hay không.

Bài học thuộc chương **Quy trình đánh giá** trong module **SPRING_AI_EVALUATION_OBSERVABILITY**. Mục tiêu là dùng dataset, relevance, fact checking, kiểm thử RAG/tool calling cùng metrics, traces, token, chi phí và độ trễ để so sánh các phiên bản prompt, model, corpus và pipeline, đồng thời xác định chính xác các ca hồi quy trước khi phát hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt một baseline được **phê duyệt và đóng băng** với một run cũ bất kỳ.
2. Xác định điều kiện để hai run có thể so sánh: dataset, nguồn chuẩn, rubric, judge, phạm vi case và điều kiện vận hành.
3. Lập bảng chuyển trạng thái từng case: `PASS→PASS`, `PASS→FAIL`, `FAIL→PASS` và `FAIL→FAIL`.
4. Giữ riêng các trường hợp `TECHNICAL_ERROR`, `SKIPPED`, `NOT_EVALUATED` để không làm sai tỷ lệ chất lượng.
5. Tính thay đổi tuyệt đối, thay đổi tương đối và số ca hồi quy; phân tích metric-specific regressions.
6. So relevance, groundedness, factual correctness, retrieval và tool contract mà không biến mọi metric thành một điểm trung bình.
7. So p95 latency, token usage và chi phí với đúng điều kiện tải và cách tính.
8. Hiểu tính dao động của LLM, ý nghĩa của phép thử ghép cặp và giới hạn thống kê của dataset nhỏ.
9. Viết bộ so sánh và kiểm thử Java/JUnit cho các trạng thái chính.
10. Thiết kế release gate, quy trình xác nhận và **nâng baseline** có dấu vết kiểm toán.

## 2. Đường cơ sở đã xác nhận là gì?

**Baseline** là mốc tham chiếu để biết hệ thống đang tốt lên hay xấu đi. Tuy nhiên, “đã chạy tuần trước” không tự biến một run thành baseline đáng tin.

Một **verified baseline** cần tối thiểu:

- Có `baselineRunId` cụ thể và trạng thái run hoàn tất theo hợp đồng.
- Có **run manifest** chỉ rõ prompt, model/provider, RAG corpus/index, tool schema, bộ đánh giá và môi trường.
- Có dataset và reference facts **được xác minh**, với version/snapshot đủ để đối chiếu.
- Có rubric và judge version hoặc quy trình human review được chấp thuận.
- Có danh sách trạng thái của từng case và các bằng chứng cần thiết để điều tra.
- Có kết quả kiểm tra tính toàn vẹn: số ca, số ca skip/error/chưa chấm, liên kết evidence.
- Có **quyết định xác nhận**: người hoặc quy trình được phép duyệt, thời điểm duyệt và phạm vi baseline áp dụng.
- Có chính sách lưu artifact, độ tin cậy của dữ liệu và thời hạn xem xét lại baseline.

**Baseline được xác nhận không đồng nghĩa hoàn hảo.** Nó có thể còn lỗi đã biết, nhưng những giới hạn và rủi ro ấy phải được ghi nhận. Khi đưa candidate ra so, mục tiêu là kiểm soát cải tiến và không làm hỏng những hành vi quan trọng đã được xác nhận.

### 2.1. Ba vai trò của baseline

| Loại baseline | Câu hỏi giải quyết | Ví dụ |
| --- | --- | --- |
| **Quality baseline** | Chất lượng nội dung/luồng nghiệp vụ có cải thiện không? | Relevance, groundedness, factuality, tool correctness |
| **Operational baseline** | Tài nguyên và trải nghiệm có tốt hơn không? | Latency, error rate, tokens, cost |
| **Release baseline** | Phiên bản mới có đáp ứng điều kiện an toàn/phát hành so với bản đã duyệt không? | Critical cases, hồi quy, release gates |

Một run có thể được chấp thuận làm mốc quality nhưng thiếu dữ liệu tải để làm mốc latency. Báo cáo phải nêu phạm vi xác nhận, không ngầm dùng một baseline cho tất cả mục tiêu.

### 2.2. Tên alias không phải danh tính bất biến

Nếu lưu `baseline=production` hoặc `model=stable` rồi luôn đọc giá trị “mới nhất”, baseline có thể thay đổi âm thầm. Một phép so sánh tuần trước sẽ không còn tái hiện được.

Nên lưu một **ID bản ghi/snapshot cố định** như:

~~~yaml
baseline:
  name: support-assistant-approved
  baselineRunId: baseline-2026-05-18-v1
  manifestRef: artifact:manifests/baseline-2026-05-18-v1.json
  datasetSnapshotRef: artifact:datasets/support-eval-v3
  rubricVersion: quality-rubric-v2
  approvalRecord: approval-104
  approvedAt: "2026-05-19T08:30:00Z"
  status: APPROVED
~~~

Dữ liệu chỉ là ví dụ. Đây là cấu trúc do hệ thống đánh giá thiết kế, **không phải YAML Spring AI tự sinh**. Nếu muốn dùng tên thân thiện, hãy resolve tên ấy thành `baselineRunId` bất biến trước khi chạy phép so sánh.

## 3. Một ví dụ xuyên suốt: chatbot chính sách và trạng thái đơn hàng

Giả sử dịch vụ *Sao Mai* (hoàn toàn giả định) dùng Spring AI để:

- Trả lời chính sách hoàn phí bằng RAG.
- Dùng tool `getOrderStatus` để lấy trạng thái đơn hàng từ backend.
- Từ chối suy đoán khi không có nguồn hoặc không có quyền.
- Theo dõi thời gian phản hồi và chi phí mỗi nhiệm vụ.

Nguồn hiện hành `policy-v3#refund-pro` quy định gói Pro có thể yêu cầu hoàn phí trong **14 ngày kể từ ngày mua**. Tài liệu cũ `policy-v2#refund-pro` ghi **30 ngày** nhưng đã hết hiệu lực.

Bộ dữ liệu đánh giá có 100 ca, bao gồm hỏi đáp chính sách, câu thiếu nguồn, tài liệu cũ/mâu thuẫn, gọi tool, xác thực quyền và hội thoại nhiều lượt. Baseline đã được review và chấp thuận, candidate thay đổi cách ghép context RAG cùng prompt.

### 3.1. Những câu hỏi cần trả lời sau khi chạy candidate

1. Cùng một case, baseline và candidate đã có output/quality verdict hợp lệ chưa?
2. Case nào chuyển `PASS→FAIL`, đặc biệt ca critical?
3. Case nào `FAIL→PASS` và bằng chứng nào chứng minh đã sửa đúng?
4. Truy xuất `policy-v3` có khá hơn nhưng factual correctness có giảm không?
5. Tool có được gọi đúng tên/arguments và giữ nguyên quyền truy cập không?
6. p95 latency và số model calls có tăng vì context dài hay retries không?
7. Bộ chấm hoặc nguồn chuẩn có thay đổi giữa hai lần đo không?
8. Với mức biến thiên của model, chênh lệch quan sát có đủ ổn định để hành động chưa?

**Bảng tổng hợp một con số không trả lời hết tám câu hỏi này.**

## 4. Trước hết phải xác minh baseline

Một cách tổ chức tốt là ghi **baseline verification record** tách khỏi lần candidate chạy.

### 4.1. Checklist xác nhận

| Kiểm tra | Cách xác minh |
| --- | --- |
| Dataset/version tồn tại | Snapshot có thể đọc, số ca đúng |
| Nhãn và nguồn chuẩn | Reference facts có nguồn/ngày hiệu lực, ca critical được domain review |
| Prompt/model/pipeline | Manifest ghi cấu hình resolved và các thông số thực |
| RAG data | Corpus/index/chunking/embedding/filter versions được ghi khi có |
| Tool/memory | Tool schema, fixture, quyền, conversation isolation được xác định |
| Rubric/judge | Có version và dữ liệu cần để chấm; judge đã kiểm với mẫu người chấm |
| Trạng thái run | Không thiếu ca ngoài chính sách; retry và skip được báo rõ |
| Outcome/evidence | Case/attempt/verdict links khớp; failure list có bằng chứng |
| Vận hành | Latency/error/token/cost có phương pháp đo và coverage phù hợp |
| Phê duyệt | Có người/hệ thống chịu trách nhiệm, ngày xác nhận và điều kiện sử dụng |

Nếu baseline chỉ có 20 câu hỏi thủ công, không có nguồn chuẩn và không lưu outputs, nó vẫn có thể là **mốc khám phá**, nhưng chưa nên được trình bày như verified baseline cho release gate đòi hỏi tính tái lập.

### 4.2. Snapshot bất biến và digest

Nên đóng băng các artifact ảnh hưởng đến kết quả: dataset và nhãn, prompt template, rubric, tool schemas, nguồn RAG tham chiếu và cấu hình.

Một `contentDigest` như SHA-256 giúp phát hiện **bytes của artifact thay đổi**, nhưng không tự bảo đảm dữ liệu đúng nghiệp vụ. Baseline đã xác nhận cần cả integrity **và** xác minh ngữ nghĩa.

Cần ghi rõ giới hạn của nhà cung cấp model: một alias có thể được cập nhật phía provider dù requested model ID không đổi. Nếu provider không cung cấp build/revision bất biến, không thể hứa tái lập tuyệt đối.

### 4.3. Không thay baseline sau khi nhìn điểm candidate

Nếu candidate kém hơn và nhóm thay baseline thành một run khác điểm thấp để tạo cảm giác “đã cải thiện”, phép so sánh không còn trung thực. Quy trình phê duyệt baseline và thời điểm đóng băng phải độc lập với kết quả mong muốn của candidate.

Khi baseline không còn phù hợp do chính sách đổi, phải tiến hành **re-baseline có audit**; không âm thầm sửa labels rồi so với kết quả cũ.

## 5. Thiết kế hợp đồng so sánh trước khi chạy

Hai run chỉ nên so trực tiếp khi **định nghĩa kết quả giống nhau**. Mức tương đương cần xem ở ba lớp: bài kiểm thử, cách chấm và điều kiện thực thi.

### 5.1. Các trường nên giữ nguyên khi kiểm một thay đổi

| Trường | Yêu cầu khi so trực tiếp | Rủi ro nếu khác |
| --- | --- | --- |
| `datasetSnapshotDigest` | Giống hoặc có mapping được xác minh | Các case/nhãn khác nhau |
| Reference facts/source version | Giống | “Đúng” nghĩa khác |
| Rubric version | Giống hoặc đã chuẩn hóa lại | Pass rate không cùng thang đo |
| Judge model/prompt/method | Giống hoặc đánh giá lại song song | Điểm chênh do bộ chấm |
| Case selection, language, grouping | Giống | Phân bố độ khó khác |
| Prompt | **Có thể khác nếu đang thử prompt** | Thay đổi có chủ đích |
| Model | **Có thể khác nếu đang thử model** | Thay đổi có chủ đích |
| Corpus/index/retrieval | **Có thể khác nếu đang thử RAG** | Phải ghi và phân tích yếu tố gây nhiễu |
| Tool fixture/authorization | Thường nên giữ tương đương | Trạng thái backend khác |
| Concurrency/quota/load | Tương đương khi so latency/cost | 429/timeout gây nhiễu |
| Runtime/build/provider endpoint | Ghi đủ để phân tích | Khác hạ tầng hoặc SDK |

**Không có quy tắc “mọi trường đều phải giống”**: cần cho phép chính yếu tố đang thử khác nhau. Điều quan trọng là **có chủ đích và được khai báo** về biến thay đổi, đồng thời giữ hoặc kiểm soát các biến còn lại.

### 5.2. Ba kiểu phép so sánh

**So sánh một biến (controlled change).** Chỉ đổi prompt v4 → v5, giữ dataset, judge, model và các yếu tố khác. Dễ quy kết nguyên nhân hơn.

**So sánh nhiều biến (bundle change).** Đổi prompt, embedding và index cùng lúc. Có thể đo tổng tác động, nhưng không thể khẳng định riêng yếu tố nào làm điểm đổi.

**So sánh trong điều kiện không hoàn toàn tương đương.** Provider alias đổi build, corpus online cập nhật hoặc tải môi trường khác. Vẫn có thể lập báo cáo **mang tính quan sát**, nhưng phải ghi giới hạn và tránh khẳng định nhân quả.

### 5.3. Một comparison contract minh họa

~~~yaml
comparison:
  comparisonId: compare-prompt-v4-v5
  baselineRunId: approved-baseline-v4
  candidateRunId: candidate-prompt-v5
  datasetVersion: support-eval-v3
  datasetDigestRef: artifact:dataset-digest-v3
  referenceVersion: policy-v3
  rubricVersion: quality-rubric-v2
  judgeVersion: judge-v1
  pairedBy: caseId
  intendedChange:
    - promptTemplateVersion
  requiredComparableEvidence:
    - answer
    - effectiveContext
    - metricVerdicts
  policy:
    excludeTechnicalErrorsFromQualityPairs: true
    reportExcludedPairsSeparately: true
    criticalPassToFailAllowed: 0
~~~

Đây là schema gợi ý. `excludeTechnicalErrorsFromQualityPairs` **không** có nghĩa được loại technical errors khỏi báo cáo: chúng phải có chỉ số và gate kỹ thuật riêng.

## 6. Chạy và thu đủ evidence cho hai phiên bản

Cùng dataset, mỗi candidate run có các attempt mới. Không dùng answer từ baseline rồi coi đó là output của candidate.

~~~mermaid
flowchart TD
    A["Immutable test dataset + labels"] --> B["Baseline runner<br/>manifest A"]
    A --> C["Candidate runner<br/>manifest B"]
    B --> D["Actual evidence A<br/>answer, context, tools, usage"]
    C --> E["Actual evidence B<br/>answer, context, tools, usage"]
    D --> F["Evaluator + rubric đã xác nhận"]
    E --> F
    F --> G["Verdicts A/B theo case/metric"]
    G --> H["Paired comparison"]
    D --> I["Telemetry A"]
    E --> J["Telemetry B"]
    H --> K["Report + regression list + gates"]
    I --> K
    J --> K
~~~

### 6.1. Một record cho mỗi attempt

~~~json
{
  "runId": "candidate-prompt-v5",
  "caseId": "REFUND-001",
  "attemptId": "candidate-prompt-v5-REFUND-001-1",
  "configuration": {
    "promptVersion": "prompt-v5",
    "requestedModel": "model-A",
    "pipelineVersion": "rag-v2",
    "corpusVersion": "policy-v3",
    "indexVersion": "index-v3"
  },
  "executionStatus": "COMPLETED",
  "retrievedDocumentIds": [
    "policy-v2#refund-pro",
    "policy-v3#refund-pro"
  ],
  "effectiveContextRefs": [
    "secure-effective-context-ref"
  ],
  "answerRef": "secure-answer-ref",
  "toolEvents": [],
  "telemetry": {
    "traceRef": null,
    "durationMs": 1950,
    "inputTokens": 1680,
    "outputTokens": 185
  }
}
~~~

Đây là **record do hệ thống đánh giá thiết kế**, không phải JSON mặc định của Spring AI. Nếu tracing có sampling, `traceRef=null` là thông tin hợp lệ; không tự đặt trace ID để khiến báo cáo trông đầy đủ.

### 6.2. Reference, retrieved và effective context phải tách riêng

| Context | Thuộc nguồn | Công dụng |
| --- | --- | --- |
| Reference facts/docs | Dataset và nguồn được domain review | Factual correctness |
| Actual retrieved documents | Retriever của **chính attempt** | Retrieval hit@k, rank và freshness |
| Actual effective context | Context thực sự được đưa vào model | Groundedness và phân tích generation |

Nếu baseline truy xuất đúng `policy-v3` còn candidate chỉ lấy `policy-v2`, đây là dấu hiệu retrieval regression. Không được đưa `policy-v3` từ dataset vào `effectiveContext` giả định rồi chấm candidate PASS.

### 6.3. Với tool calling, theo dõi hợp đồng và backend

Một ca có thể mong `getOrderStatus(orderId="DH-123")` và backend trả `IN_TRANSIT`. Cần lưu tool name, arguments được xử lý an toàn, authorization outcome, tool result, số lần gọi và câu trả lời cuối.

Một model **đoán đúng trạng thái đơn** nhưng không gọi tool bắt buộc vẫn có thể FAIL tool-contract. Một tool đọc dữ liệu người dùng khác bị backend từ chối là **hành vi PASS** của ca security test, không mặc định là lỗi kỹ thuật.

Với tool tạo giao dịch, dùng sandbox/test double; các lần retry phải có idempotency/hậu điều kiện, không dùng việc so baseline/candidate làm lý do chạy thao tác nguy hiểm trên production.

## 7. Chấm riêng các tiêu chí trước khi tạo điểm tổng

Một case có thể pass relevance và fail factual correctness. Vì vậy bảng điểm cần có cột riêng cho:

| Tiêu chí | Dùng nguồn nào | Lỗi tiêu biểu |
| --- | --- | --- |
| **Relevance** | Question và actual answer | Trả sai chủ đề |
| **Groundedness** | Actual answer + effective context | Khẳng định không có bằng chứng |
| **Factual correctness** | Actual answer + reference facts | Sai số ngày/chính sách |
| **Retrieval hit@k** | Actual retrieved IDs + expected relevant IDs | Bỏ sót nguồn |
| **Citation correctness** | Citation và nội dung nguồn | Dẫn tài liệu cũ/không liên quan |
| **Tool contract** | Expected vs actual tool events | Thiếu tool/sai args |
| **Tool authorization** | Backend access checks | Vượt quyền |
| **Operational budget** | Durations, usage/cost | Quá chậm/đắt |

Spring AI cung cấp các abstraction đánh giá như `Evaluator`, `EvaluationRequest`, `EvaluationResponse`; tùy phiên bản có thể dùng `RelevancyEvaluator` và `FactCheckingEvaluator`. **Kết quả của evaluator phải được diễn giải theo input và rubric của nó.**

`FactCheckingEvaluator` dùng context để kiểm tra sự hỗ trợ của câu trả lời không tự biết nguồn chính sách nào **mới nhất** nếu context không chứa chuẩn ấy. Factual correctness theo chính sách hiện hành cần nguồn độc lập đã xác minh.

### 7.1. Status của metric

Ghi `PASS`, `FAIL`, `NOT_EVALUATED`, `NOT_APPLICABLE` và `PENDING` theo từng metric, cùng `rubricVersion`/`judgeVersion` và reason/evidence refs.

Nếu judge timeout, verdict nên là `NOT_EVALUATED` với `JUDGE_TIMEOUT`; không tự chấm FAIL vì model ứng dụng chưa chắc sai.

### 7.2. Tổng hợp case

Có thể đặt policy:

1. Có metric bắt buộc FAIL → case quality FAIL.
2. Không có FAIL nhưng metric bắt buộc chưa chấm/thiếu → INCONCLUSIVE.
3. Tất cả metric bắt buộc PASS → case quality PASS.
4. Case không thực thi vì SKIPPED/ERROR/CANCELLED → giữ trạng thái riêng, không ép vào PASS/FAIL chất lượng.

Nên xác định policy này **trước khi** quan sát candidate để tránh bỏ qua một metric fail chỉ nhằm qua gate.

## 8. So từng ca theo cặp, không chỉ so hai tỷ lệ

Giả sử **100 case đều có verdict PASS/FAIL hợp lệ ở cả hai run** theo cùng rubric. Baseline có 82 PASS, 18 FAIL; candidate có 85 PASS, 15 FAIL.

Bảng ghép cặp:

| | Candidate PASS | Candidate FAIL | Tổng baseline |
| --- | ---: | ---: | ---: |
| **Baseline PASS** | 76 | 6 | 82 |
| **Baseline FAIL** | 9 | 9 | 18 |
| **Tổng candidate** | **85** | **15** | **100** |

Bảng này có ý nghĩa:

- **76 PASS→PASS:** giữ được kết quả đạt.
- **6 PASS→FAIL:** ca hồi quy (*regressions*).
- **9 FAIL→PASS:** ca được sửa (*improvements/fixes*).
- **9 FAIL→FAIL:** vẫn chưa đạt.

### 8.1. Tính chênh lệch tuyệt đối

\[
P_{\mathrm{baseline}}=\frac{82}{100}=82\%,
\quad
P_{\mathrm{candidate}}=\frac{85}{100}=85\%.
\]

\[
\Delta_{\mathrm{absolute}}=85\%-82\%=+3\text{ điểm phần trăm}.
\]

Tăng **3 điểm phần trăm** khác với tăng **3% tương đối**.

### 8.2. Tính chênh lệch tương đối

\[
\Delta_{\mathrm{relative}}
=\frac{0.85-0.82}{0.82}
\approx3{,}66\%.
\]

Có thể diễn đạt “tăng khoảng 3,66% so với tỷ lệ đạt baseline”, nếu người đọc cần cách đo tương đối.

### 8.3. Số ca sửa được và số ca bị hỏng

\[
\text{Net gained passes}
=\text{FAIL→PASS}-\text{PASS→FAIL}
=9-6=3.
\]

Đây là lý do candidate tăng từ 82 lên 85 PASS. **Không được nói chỉ có 3 ca thay đổi**: thực tế có **15 case đổi verdict**, gồm 9 được sửa và 6 bị hồi quy.

### 8.4. Một ca critical thay đổi có thể quyết định release

Nếu trong 6 ca PASS→FAIL có `AUTH-004` kiểm tra tool không được đọc dữ liệu ngoài quyền, gate có thể phải BLOCK dù chênh lệch trung bình dương.

**Net improvement không bù cho violation của tiêu chí bắt buộc.**

## 9. Không so quality PASS/FAIL khi một phía thiếu verdict

Ví dụ baseline PASS nhưng candidate provider timeout. Đó là suy giảm khả năng hoàn thành hoặc lỗi vận hành, **không tự động là factual FAIL**.

Các transition cần phân loại khác:

| Baseline | Candidate | Phân loại |
| --- | --- | --- |
| PASS | FAIL | Quality regression |
| FAIL | PASS | Fixed quality failure |
| PASS | PASS | Stable pass |
| FAIL | FAIL | Persistent failure |
| PASS | TECHNICAL_ERROR | New technical failure |
| PASS | INCONCLUSIVE | New evaluation gap |
| PASS | SKIPPED | New skip / coverage regression |
| ERROR | PASS | Recovery of technical completion |
| NOT_EVALUATED | PASS | New evidence; chưa thể kết luận model tốt hơn |
| Chưa có case | PASS/FAIL | Newly added case, không có cặp |

### 9.1. Mẫu số của phép ghép cặp

Phải báo:

- `plannedPairs`: case IDs thuộc cả hai dataset được phép so.
- `comparablePairs`: case có verdict PASS/FAIL tương thích ở hai run.
- `excludedPairsByReason`: lỗi kỹ thuật, SKIPPED, INCONCLUSIVE, rubric mismatch, thiếu case.
- `pairedCoverage = comparablePairs/plannedPairs`.
- `technicalCompletion` riêng cho từng run.

Chỉ so `pairedPassRate` trên tập case có cặp hợp lệ và **không** ngầm diễn giải nó là chất lượng toàn dataset nếu coverage giảm.

### 9.2. Ví dụ coverage suy giảm

Giả sử từ 100 case, candidate chỉ tạo được 75 output vì 25 case gặp 429. Trong 75 case có verdict, 72 PASS → 96% trên tập đã chấm. Con số 96% trông tốt hơn baseline 82% nhưng **không chứng minh candidate tốt hơn trên toàn bộ 100 case**.

Report phải nêu 25 technical failures, quality-evaluated coverage và end-to-end success. Release gate có thể chặn vì reliability dù điểm nội dung trên các ca còn lại cao.

### 9.3. Không loại dữ liệu sau khi thấy điểm

Không xóa “ca khó” hoặc ca FAIL khỏi candidate trước khi so, không đánh dấu SKIPPED để tránh hồi quy. Eligibility và skip policy phải xác định từ trước; mọi thay đổi phải có báo cáo và lý do.

## 10. So metric theo case và theo nhóm rủi ro

Aggregate PASS chỉ cho biết một case đáp ứng tất cả tiêu chí bắt buộc hay chưa. Muốn sửa đúng vấn đề, phải có **diff theo metric**.

Ví dụ cùng 100 case có kết quả từng metric được chấm đầy đủ, số liệu giả định:

| Metric | Baseline | Candidate | Chênh | Cần điều tra |
| --- | ---: | ---: | ---: | --- |
| Aggregate quality PASS | 82% | 85% | +3 pp | 6 regressions |
| Relevance PASS | 91% | 95% | +4 pp | Ca nào cải thiện? |
| Retrieval hit@5 | 89% | 94% | +5 pp | Tài liệu mới nào được lấy? |
| Groundedness PASS | 94% | 92% | −2 pp | Context quá dài/nhiễu? |
| Factual correctness PASS | 93% | 92% | −1 pp | Chính sách cũ/mâu thuẫn? |
| Tool contract PASS | 100% | 100% | 0 pp | Có bao nhiêu ca có tool? |

*pp = điểm phần trăm*. Các tỷ lệ metric có thể có **mẫu số khác nhau trong dự án thật**, đặc biệt tool contract chỉ áp dụng cho ca yêu cầu tool. Bảng trên dùng phần trăm minh họa; báo cáo production phải ghi cả số ca đã chấm và chưa chấm cho từng metric.

Candidate lấy nguồn tốt hơn nhưng groundedness và factual correctness giảm. Một nguyên nhân giả định là `topK` lớn hơn khiến context có tài liệu cũ/nhiễu. Đó mới là **giả thuyết**; cần xem actual retrieval, effective context và trace của các ca FAIL để xác minh.

### 10.1. So theo slice

Ngoài nhóm RAG/tool, nên chia theo những chiều có ý nghĩa và có đủ mẫu:

- Câu có nguồn và câu thiếu nguồn.
- Câu có nhiều số liệu hoặc điều kiện gần nhau.
- Chính sách hiện hành và tài liệu từng hết hiệu lực.
- Tool chỉ đọc, tool có tác dụng phụ, bài kiểm quyền.
- Tiếng Việt/tiếng Anh hoặc các ngôn ngữ mà sản phẩm hỗ trợ.
- Multi-turn có memory, single-turn không dùng memory.
- Ca critical và noncritical.
- Nhóm khách hàng/ngữ cảnh phù hợp chính sách dữ liệu.

### 10.2. Ví dụ điểm trung bình che lỗi nhóm

Giả sử candidate tăng mạnh ở câu hỏi thông thường nhưng giảm trên nhóm **thiếu nguồn**, nơi model bắt đầu bịa thay vì từ chối. Tổng PASS tăng không bảo đảm yêu cầu “không hallucinate khi thiếu dữ liệu” đã tốt hơn.

Báo cáo cần có **pass rate theo slice và danh sách ca chuyển PASS→FAIL trong slice ấy**.

### 10.3. Nguồn nhãn là yếu tố không thể bỏ qua

Factual correctness phải so với nguồn đúng thời điểm. Nếu bộ chính sách được cập nhật từ 14 ngày sang 21 ngày giữa hai run, điểm khác nhau có thể do **reference version thay đổi**, không phải do model.

Khi dữ liệu chuẩn thay đổi, hãy tạo snapshot/dataset mới và cân nhắc chạy lại hai phiên bản ứng dụng trên cùng chuẩn mới; không tự so trực tiếp hai pass rate dưới hai chính sách khác nhau.

## 11. Độ dao động và độ tin cậy thống kê của chênh lệch

LLM thường không hoàn toàn xác định. Hai run cùng prompt/model có thể trả khác nhau; provider alias hoặc retrieval có dữ liệu động càng làm điểm biến động.

### 11.1. Vì sao ghép cặp theo case giúp ích?

Trong phép so **có cặp**, mỗi case được dùng làm đối chứng của chính nó. So baseline/candidate trên cùng 100 case hữu ích hơn so 100 câu dễ của baseline với 100 câu khó của candidate.

Sự thay đổi tập trung ở **những case đổi trạng thái**. Trong bảng ví dụ, chỉ có 15 case bất đồng:

- Baseline FAIL → Candidate PASS: 9.
- Baseline PASS → Candidate FAIL: 6.

Các cặp không thay đổi (76 + 9) không trực tiếp cho thấy hướng cải thiện.

### 11.2. Không suy “tốt hơn chắc chắn” từ chênh 3 pp

Với chỉ 15 cặp bất đồng, chênh 9 so với 6 là nhỏ. Nó **không đủ để mặc nhiên kết luận có cải thiện ổn định**.

Khi thiết kế phù hợp, có thể dùng kiểm định McNemar trên nhãn nhị phân của các cặp bất đồng, hoặc **paired bootstrap** trên các case để ước lượng khoảng bất định của chênh lệch. Nếu case không độc lập (nhiều lượt cùng một hội thoại, nhiều câu gần giống từ cùng tài liệu), cần xem xét bootstrap theo **conversation/cluster** thay vì coi mọi dòng hoàn toàn độc lập.

Không nhất thiết phải đưa p-value vào mọi CI job. Nhưng report nên nói rõ **số case, mức bao phủ, số cặp đổi trạng thái và độ dao động**, tránh một chênh lệch nhỏ được diễn giải thành chân lý tuyệt đối.

### 11.3. Chạy lặp để kiểm tính ổn định

Với case nhạy cảm hoặc chênh lệch nhỏ, có thể chạy mỗi cấu hình nhiều lần trong điều kiện tương đương:

~~~text
REFUND-001, baseline:  PASS, PASS, PASS, FAIL, PASS
REFUND-001, candidate: PASS, FAIL, PASS, FAIL, PASS
~~~

Trong ví dụ:

\[
\mathrm{baselinePassFrequency}=\frac45=80\%,\quad
\mathrm{candidatePassFrequency}=\frac35=60\%.
\]

Một lần chạy đơn lẻ có thể tình cờ cho kết quả giống nhau, nhưng phân bố 5 lần gợi ý cần điều tra thêm. **Năm lần vẫn là mẫu nhỏ**, không đủ để hứa ước lượng chính xác.

Lưu từng `attemptId`, seed nếu provider hỗ trợ, timestamp, model/provider details, dataset/rubric versions và cách chọn kết quả. Đừng lấy “lần đẹp nhất” làm đại diện mà không ghi chính sách.

### 11.4. Không dùng kiểm định thống kê để bỏ gate critical

Một lỗi kiểm tra quyền được xác minh có thể cần **BLOCK** ngay cả khi chênh lệch aggregate chưa có ý nghĩa thống kê. Quyết định này dựa trên severity và contract, không phải trung bình.

## 12. So latency, token, cost trong điều kiện vận hành tương đương

Nếu ứng dụng AI đúng hơn nhưng chậm hơn 2 lần hoặc tốn token gấp 3, nhóm có thể cần đổi trade-off. Tuy nhiên, phép so vận hành cần định nghĩa và điều kiện đo riêng.

### 12.1. Bảng operational baseline minh họa

| Chỉ số | Baseline | Candidate | Diễn giải |
| --- | ---: | ---: | --- |
| Technical completion | 100/100 | 100/100 | Cả hai hoàn tất bộ thử |
| p50 end-to-end latency | 1,3 s | 1,7 s | Trung vị tăng |
| p95 end-to-end latency | 2,1 s | 2,8 s | Tail latency xấu hơn |
| Input tokens trung bình/request | 1.250 | 1.650 | Context có thể dài hơn |
| Output tokens trung bình/request | 160 | 190 | Câu trả lời dài hơn |
| Model calls trung bình/request | 1,2 | 1,4 | Có thể nhiều vòng tool/retry |
| Estimated model cost/request | 0,004 USD | 0,0055 USD | Tăng chi phí theo giả định |
| HTTP/provider errors | 0 | 0 | Không thấy lỗi trong mẫu này |

**Các số liệu đều giả định**, không phải benchmark hay giá hiện hành. Phép đo phải ghi cấu hình tải, provider, model, endpoint, sample count, retry policy, cách tính token/cost và thời gian chạy.

### 12.2. Percentile không phải trung bình

`p95 latency` là ngưỡng mà khoảng 95% các quan sát thuộc phạm vi đo không vượt qua. Nó không thể tính từ timer `count` và `sum`; cần phân bố/histogram hoặc dữ liệu request durations phù hợp.

Nếu hai p95 được đo với traffic mix hoặc concurrency khác hẳn, không thể kết luận chỉ từ prompt/model là nguyên nhân.

### 12.3. Độ trễ của lần gọi và của nhiệm vụ khác nhau

Một request tool calling có thể gồm:

~~~text
HTTP /ask                         3.4 s
├── VectorStore                   0.3 s
├── ChatModel call #1             1.1 s
├── Tool getOrderStatus           0.8 s
└── ChatModel call #2             1.0 s
~~~

Đây là **sơ đồ minh họa**, không phải trace đã đo. Các spans có quan hệ cha-con không cộng đè lên nhau. Khi so end-to-end latency, tính cả các thành phần thực tế liên quan, retries và thời gian chờ; với streaming có thể theo dõi thêm time to first token.

### 12.4. Token usage và chi phí

Với đơn giá giả định theo triệu token:

\[
\mathrm{modelCost}
=\frac{\mathrm{inputTokens}\cdot\mathrm{priceInputPerMillion}}{10^6}
+\frac{\mathrm{outputTokens}\cdot\mathrm{priceOutputPerMillion}}{10^6}.
\]

Ví dụ input 2.000 tokens giá 2 USD/triệu và output 500 tokens giá 8 USD/triệu:

\[
\mathrm{cost}=\frac{2000\cdot2+500\cdot8}{10^6}
=0{,}008\;\mathrm{USD}.
\]

Đây **chỉ là giá minh họa**. Trong run thật, cần cộng usage theo từng model call, kể cả những lượt tool calling/ retry có tính phí; ghi `priceTableVersion` và tách chi phí **generation** khỏi **evaluation judge**. Tổng chi phí còn có embedding, reranking, vector store, tool backend và hạ tầng.

### 12.5. Giá trị cho mỗi nhiệm vụ thành công

Một chỉ số bổ sung có thể là:

\[
\mathrm{costPerVerifiedSuccess}
=\frac{\mathrm{totalRelevantCost}}
{\mathrm{verifiedSuccessfulTasks}}.
\]

Chỉ số này hữu ích khi candidate tạo nhiều answer hơn nhưng cũng tăng chi phí. Tuy nhiên, phải thống nhất phạm vi `totalRelevantCost` và cách định nghĩa `verifiedSuccessfulTasks`; nếu số thành công bằng 0, kết quả không xác định. Không dùng riêng chỉ số chi phí để bỏ gate về quyền và correctness.

## 13. Danh sách hồi quy là kết quả quan trọng nhất của comparison

Một report tốt phải tạo **failure diff** gồm ít nhất:

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| `caseId` | `REFUND-017` | Xác định tình huống |
| `baselineAttemptId` | `base-REFUND-017-r1` | Xem evidence trước |
| `candidateAttemptId` | `cand-REFUND-017-r1` | Xem evidence sau |
| `transition` | `PASS_TO_FAIL` | Phân loại hồi quy |
| `severity` | `HIGH` | Sắp ưu tiên |
| `metricTransitions` | `groundedness PASS→FAIL` | Khoanh vùng |
| `reasonCode` | `STALE_DOCUMENT_USED` | Lý do sơ bộ |
| `referenceRef` | `policy-v3#refund-pro` | Nguồn chuẩn |
| `actualEvidenceRefs` | Doc IDs, answer refs, tool events | Kiểm chứng |
| `traceRefs` | Có hoặc null | Xem độ trễ/lỗi |
| `baseline/candidateConfig` | Prompt/model/index versions | Nối sự thay đổi |
| `triageStatus` | `OPEN` | Theo dõi sửa lỗi |

### 13.1. Một ca RAG PASS→FAIL

Ví dụ giả định:

~~~json
{
  "caseId": "REFUND-017",
  "transition": "PASS_TO_FAIL",
  "severity": "HIGH",
  "metric": "factualCorrectness",
  "expectedFact": "Gói Pro: 14 ngày kể từ ngày mua",
  "baseline": {
    "answerSummary": "14 ngày",
    "retrievedDocumentIds": ["policy-v3#refund-pro"],
    "promptVersion": "prompt-v4"
  },
  "candidate": {
    "answerSummary": "30 ngày",
    "retrievedDocumentIds": ["policy-v2#refund-pro"],
    "promptVersion": "prompt-v5"
  },
  "referenceDocumentIds": ["policy-v3#refund-pro"],
  "hypothesis": "Candidate chọn tài liệu hết hiệu lực",
  "verification": "Kiểm filter nguồn và effective context",
  "traceRefs": {
    "baseline": null,
    "candidate": null
  }
}
~~~

**Hypothesis không phải root cause đã xác nhận.** Candidate có thể lấy cả hai tài liệu, prompt có thể dùng sai đoạn, hoặc corpus/index có thể thay đổi đồng thời. Cần xem bằng chứng thực tế trước khi quy trách nhiệm cho một thành phần.

### 13.2. Một ca Tool Calling PASS→FAIL

Giả sử baseline gọi `getOrderStatus` với đúng `orderId`, candidate không gọi tool mà suy đoán status dựa trên memory cũ. Answer của candidate tình cờ có thể đúng trong fixture, nhưng **tool contract FAIL**.

Nếu candidate gọi tool thuộc đối tượng không được phép, đó là hồi quy authorization nghiêm trọng; không bù bằng điểm factual correctness hoặc relevance.

### 13.3. Một ca FAIL→PASS cũng cần evidence

Đừng gắn nhãn “fixed” chỉ vì judge mới cho PASS. Cần xác minh candidate đã dùng đúng effective context, câu trả lời phù hợp reference, và không tạo lỗi ở chỗ khác. Khi thay judge, có thể chấm lại cả baseline và candidate bằng cùng rubric/judge để tách biến động phương pháp.

## 14. Java: bộ so sánh hai run theo `caseId`

Ví dụ Java 17+ sau đây triển khai **phần so sánh đã chuẩn hóa**. Nó nhận kết quả tổng hợp PASS/FAIL và một số trạng thái thiếu khả năng so, sau đó đếm các cặp và liệt kê regressions. Mã **không trực tiếp gọi LLM**; kết quả cần được sinh từ pipeline Spring AI và evaluator đã ghi evidence.

### 14.1. Data types và comparator

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class PairedEvaluationComparison {

    public enum Status {
        PASS, FAIL, INCONCLUSIVE,
        TECHNICAL_ERROR, SKIPPED
    }

    public enum Transition {
        STABLE_PASS,
        REGRESSION,
        FIXED,
        STABLE_FAIL,
        NOT_COMPARABLE
    }

    public record CaseOutcome(
            String caseId,
            String attemptId,
            Status status,
            boolean critical) {

        public CaseOutcome {
            Objects.requireNonNull(caseId);
            Objects.requireNonNull(status);
        }
    }

    public record Pair(
            String caseId,
            Status baseline,
            Status candidate,
            Transition transition,
            boolean critical) {}

    public record Summary(
            int plannedPairs,
            int comparablePairs,
            int passPass,
            int passFail,
            int failPass,
            int failFail,
            int notComparable,
            int criticalRegressions,
            List<Pair> pairs) {

        public double pairedBaselinePassRate() {
            return comparablePairs == 0
                    ? Double.NaN
                    : (double) (passPass + passFail) / comparablePairs;
        }

        public double pairedCandidatePassRate() {
            return comparablePairs == 0
                    ? Double.NaN
                    : (double) (passPass + failPass) / comparablePairs;
        }
    }

    public static Summary compare(
            List<CaseOutcome> baseline,
            List<CaseOutcome> candidate) {

        Map<String, CaseOutcome> base = index(baseline);
        Map<String, CaseOutcome> next = index(candidate);

        // Ví dụ áp dụng cho cùng một tập planned cases.
        if (!base.keySet().equals(next.keySet())) {
            throw new IllegalArgumentException(
                    "Case sets differ; align datasets before comparison");
        }

        int pp = 0;
        int pf = 0;
        int fp = 0;
        int ff = 0;
        int incomparable = 0;
        int criticalRegression = 0;

        List<Pair> pairs = new ArrayList<>();

        for (String id : new java.util.TreeSet<>(base.keySet())) {
            CaseOutcome b = base.get(id);
            CaseOutcome c = next.get(id);

            if (b.critical() != c.critical()) {
                throw new IllegalArgumentException(
                        "Critical label changed for " + id);
            }

            Transition transition;
            if (!comparable(b.status())
                    || !comparable(c.status())) {
                transition = Transition.NOT_COMPARABLE;
                incomparable++;
            } else if (b.status() == Status.PASS
                    && c.status() == Status.PASS) {
                transition = Transition.STABLE_PASS;
                pp++;
            } else if (b.status() == Status.PASS
                    && c.status() == Status.FAIL) {
                transition = Transition.REGRESSION;
                pf++;
                if (b.critical()) {
                    criticalRegression++;
                }
            } else if (b.status() == Status.FAIL
                    && c.status() == Status.PASS) {
                transition = Transition.FIXED;
                fp++;
            } else {
                transition = Transition.STABLE_FAIL;
                ff++;
            }

            pairs.add(new Pair(
                    id, b.status(), c.status(),
                    transition, b.critical()));
        }

        int comparablePairs = pp + pf + fp + ff;

        return new Summary(
                pairs.size(),
                comparablePairs,
                pp, pf, fp, ff, incomparable,
                criticalRegression,
                List.copyOf(pairs));
    }

    private static boolean comparable(Status status) {
        return status == Status.PASS || status == Status.FAIL;
    }

    private static Map<String, CaseOutcome> index(
            List<CaseOutcome> outcomes) {

        Objects.requireNonNull(outcomes);
        Map<String, CaseOutcome> indexed = new HashMap<>();
        for (CaseOutcome row : outcomes) {
            Objects.requireNonNull(row);
            if (indexed.putIfAbsent(row.caseId(), row) != null) {
                throw new IllegalArgumentException(
                        "Duplicate caseId: " + row.caseId());
            }
        }
        return indexed;
    }

    private PairedEvaluationComparison() {}
}
~~~

### 14.2. Ý nghĩa và giới hạn của comparator

Mã trên:

- Ghép theo `caseId` chứ không theo thứ tự hoàn thành.
- Phát hiện ID bị trùng và case set khác nhau.
- Giữ riêng các cặp không có verdict PASS/FAIL ở cả hai bên.
- Đếm từng loại transition và critical regressions.
- Chỉ tính paired pass rate trên `comparablePairs`.
- Trả `Double.NaN` khi không có cặp hợp lệ; lớp xuất báo cáo nên hiển thị **N/A** thay vì phần trăm giả.

**Quan trọng:** comparator giả định một `CaseOutcome` đã được chọn theo retry/repeated-run policy, có cùng dataset/reference/rubric và cách chấm tương thích. Nó **không tự kiểm** SHA-256 của dataset, judge version, attempt evidence hay quyền của tool. Các bước validation này phải thực hiện trước.

Nếu `NOT_COMPARABLE` xuất hiện, report phải lưu lý do (SKIPPED, ERROR, INCONCLUSIVE...), không chỉ một con số tổng. Trong ví dụ đã rút gọn, lý do có thể suy từ `baseline/candidate status` của từng `Pair`.

### 14.3. Kiểm toán trước khi chạy comparator

~~~text
assert baseline.manifest.datasetDigest
       == candidate.manifest.datasetDigest
assert baseline.referenceVersion
       == candidate.referenceVersion
assert baseline.rubricVersion
       == candidate.rubricVersion
assert baseline.judgeVersion
       == candidate.judgeVersion
assert case IDs and critical labels match

baselineOutcomes = normalizeAttempts(baseline, policy)
candidateOutcomes = normalizeAttempts(candidate, policy)

pairComparison = compare(baselineOutcomes, candidateOutcomes)
~~~

Đây là **pseudocode** cho hợp đồng so sánh, không phải mã Java chạy được nguyên văn. Nếu cần thay judge, có thể chấm lại **cả hai** tập answer/evidence dưới cùng judge/rubric, thay vì bỏ qua kiểm tra.

## 15. JUnit: kiểm các chuyển trạng thái quan trọng

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class PairedEvaluationComparisonTest {

    private PairedEvaluationComparison.CaseOutcome row(
            String id,
            PairedEvaluationComparison.Status status,
            boolean critical) {

        return new PairedEvaluationComparison.CaseOutcome(
                id, "attempt-" + id, status, critical);
    }

    @Test
    void detectsRegressionsAndFixes() {
        var base = List.of(
                row("A", PairedEvaluationComparison.Status.PASS, false),
                row("B", PairedEvaluationComparison.Status.PASS, true),
                row("C", PairedEvaluationComparison.Status.FAIL, false),
                row("D", PairedEvaluationComparison.Status.FAIL, false));

        var candidate = List.of(
                row("A", PairedEvaluationComparison.Status.PASS, false),
                row("B", PairedEvaluationComparison.Status.FAIL, true),
                row("C", PairedEvaluationComparison.Status.PASS, false),
                row("D", PairedEvaluationComparison.Status.FAIL, false));

        var summary = PairedEvaluationComparison.compare(
                base, candidate);

        assertEquals(4, summary.plannedPairs());
        assertEquals(4, summary.comparablePairs());
        assertEquals(1, summary.passPass());
        assertEquals(1, summary.passFail());
        assertEquals(1, summary.failPass());
        assertEquals(1, summary.failFail());
        assertEquals(1, summary.criticalRegressions());
        assertEquals(0.5, summary.pairedBaselinePassRate());
        assertEquals(0.5, summary.pairedCandidatePassRate());
    }

    @Test
    void missingVerdictDoesNotBecomeQualityFail() {
        var base = List.of(
                row("A", PairedEvaluationComparison.Status.PASS, true));

        var candidate = List.of(
                row("A",
                        PairedEvaluationComparison.Status.TECHNICAL_ERROR,
                        true));

        var summary = PairedEvaluationComparison.compare(
                base, candidate);

        assertEquals(0, summary.comparablePairs());
        assertEquals(1, summary.notComparable());
        assertEquals(0, summary.passFail());
        assertTrue(Double.isNaN(
                summary.pairedCandidatePassRate()));
    }

    @Test
    void rejectsDifferentCaseSets() {
        assertThrows(IllegalArgumentException.class,
                () -> PairedEvaluationComparison.compare(
                        List.of(row("A",
                                PairedEvaluationComparison.Status.PASS,
                                false)),
                        List.of(row("B",
                                PairedEvaluationComparison.Status.PASS,
                                false))));
    }

    @Test
    void rejectsChangedCriticalLabels() {
        assertThrows(IllegalArgumentException.class,
                () -> PairedEvaluationComparison.compare(
                        List.of(row("A",
                                PairedEvaluationComparison.Status.PASS,
                                true)),
                        List.of(row("A",
                                PairedEvaluationComparison.Status.PASS,
                                false))));
    }
}
~~~

Đây là unit tests cho **logic so sánh**, không phải kiểm thử thực tế của Spring AI. Khi triển khai cần thêm integration tests cho retrieval evidence, tool fixture/quyền, judge errors, trace linking và kiểm tra tính toàn vẹn của manifest.

## 16. Đưa kết quả comparison vào báo cáo có thể dùng để quyết định

Một comparison report nên có cả dữ liệu máy đọc được và phiên bản tóm tắt cho con người.

### 16.1. Ví dụ JSON

~~~json
{
  "schemaVersion": "comparison-report-v1",
  "comparisonId": "baseline-v4-vs-candidate-v5",
  "baselineRunId": "approved-baseline-v4",
  "candidateRunId": "candidate-prompt-v5",
  "comparisonContractRef": "contract-prompt-v4-v5",
  "scope": {
    "datasetVersion": "support-eval-v3",
    "rubricVersion": "quality-rubric-v2",
    "judgeVersion": "judge-v1"
  },
  "pairedSummary": {
    "plannedPairs": 100,
    "comparablePairs": 100,
    "passPass": 76,
    "passFail": 6,
    "failPass": 9,
    "failFail": 9,
    "baselinePassRate": 0.82,
    "candidatePassRate": 0.85,
    "absoluteChangePercentagePoints": 3
  },
  "critical": {
    "newCriticalRegressions": 1
  },
  "operations": {
    "baselineP95LatencyMs": 2100,
    "candidateP95LatencyMs": 2800
  },
  "artifacts": {
    "regressionsRef": "regressions.jsonl",
    "fixedCasesRef": "fixed-cases.jsonl",
    "nonComparableRef": "non-comparable.jsonl"
  },
  "releaseGate": {
    "status": "BLOCKED_QUALITY",
    "reason": "Critical PASS_TO_FAIL detected"
  }
}
~~~

Các số liệu hoàn toàn **minh họa**. Trạng thái BLOCKED ở ví dụ xuất phát từ **gate do nhóm định nghĩa**, không phải quy tắc mặc định của Spring AI.

### 16.2. Báo cáo ngắn cho reviewer

Một bản tóm tắt nên trả lời theo thứ tự:

1. **Đang so gì?** Baseline run, candidate run, change intent.
2. **Độ tin cậy?** Dataset/rubric/judge tương thích, paired coverage, run statuses.
3. **Kết quả chung?** PASS baseline/candidate và chênh lệch.
4. **Đổi trạng thái?** PASS→FAIL, FAIL→PASS, critical regressions.
5. **Từng nhóm/metric?** RAG factuality, groundedness, tool correctness.
6. **Vận hành?** p95, token, 429, cost và điều kiện đo.
7. **Quyết định?** Gate status, blockers, điều cần điều tra.
8. **Bằng chứng?** Links tới case/evidence/trace có thật.

**Không giấu 6 ca hồi quy sau con số +3 pp.** Danh sách regressions là artifact bắt buộc để đưa ra quyết định hoặc phân công sửa.

## 17. Release gate với baseline đã xác nhận

Để kiểm soát triển khai, có thể định nghĩa những điều kiện mang tính **không được hồi quy**, bên cạnh yêu cầu tỷ lệ tổng.

~~~yaml
releaseGates:
  comparison:
    baselineApprovalRequired: true
    datasetAndRubricComparable: true
    minPairedCoverage: 0.99
    maxCriticalPassToFail: 0
  functionalSafety:
    toolAuthorization: must-pass
    toolIdempotency: must-pass
  quality:
    minAggregatePassRate: 0.90
    factualCorrectnessPassRate: ">= 0.98"
    groundednessPassRate: ">= 0.95"
  operations:
    minTechnicalCompletion: 0.99
    p95LatencyMs: "<= 2500"
    estimatedCostUsdPerRequest: "<= 0.01"
  evidence:
    criticalNotEvaluated: 0
    criticalSkipped: 0
~~~

Đây là **ngưỡng giả định** để học cách thiết kế gate. Ví dụ 100 case trong phần trước chưa đạt một số ngưỡng này; không được suy ra chúng đã được chọn riêng cho hệ thống thật. Trong sản phẩm thực tế, xác định threshold theo rủi ro, dataset đủ đại diện và điều kiện vận hành.

### 17.1. Những trường hợp cần BLOCK dù tỷ lệ trung bình tăng

- Một ca quyền tool chuyển PASS→FAIL.
- Reference facts hoặc nguồn chuẩn không còn hợp lệ.
- Critical case bị SKIPPED hoặc judge không chấm được.
- Có dữ liệu evidence bị ghép nhầm giữa attempts.
- Technical error tăng vượt giới hạn chấp nhận.
- p95 latency hoặc chi phí vượt ngân sách bắt buộc.
- Candidate được chấm bằng rubric khác nhưng báo là so sánh trực tiếp.

### 17.2. Gate có thể chặn vì thiếu bằng chứng mà không gán quality FAIL

Một ca critical hoàn tất nhưng effective context bị mất làm groundedness NOT_EVALUATED. Gate nên chặn hoặc yêu cầu review vì **không đủ bằng chứng**, đồng thời giữ verdict NOT_EVALUATED. Việc chặn release là **quyết định quản trị**, không phải bằng chứng câu trả lời đã sai.

### 17.3. Canary sau khi offline gate đạt

Offline evaluation tốt không bảo đảm mọi câu production đúng; traffic, tài liệu, tool backend và provider có thể khác.

Nếu triển khai canary, nên so theo release/prompt/model version, quan sát error rate, latency/tokens/cost và mẫu quality đã được xác minh. Cần phân biệt thay đổi do **traffic mix** với chất lượng trong từng nhóm; mẫu rủi ro không tự đại diện cho toàn traffic.

## 18. Khi nào được nâng candidate thành baseline mới?

Baseline cần được cập nhật để không so mãi với công nghệ hoặc chính sách cũ. Nhưng việc **promote baseline** phải có quy trình riêng, không tự động “candidate mới nhất = baseline”.

### 18.1. Quy trình đề xuất

~~~mermaid
flowchart TD
    A["Candidate đã chạy và có report"] --> B["Xác nhận comparison contract"]
    B --> C{"Quality + safety + ops gates?"}
    C -- "Không" --> D["BLOCK / sửa / chạy lại"]
    C -- "Có" --> E["Review critical regressions<br/>và evidence"]
    E --> F{"Được phê duyệt?"}
    F -- "Không" --> D
    F -- "Có" --> G["Đóng băng candidate manifest<br/>và dataset/rubric"]
    G --> H["Tạo approval record mới"]
    H --> I["Cập nhật alias baseline trỏ<br/>tới run ID mới"]
    I --> J["Giữ nguyên baseline cũ<br/>để audit/rollback"]
~~~

Nguyên tắc:

- Lưu **baseline cũ bất biến**, không ghi đè artifact.
- Ghi `approvedAt`, người/nhóm duyệt, lý do và điều kiện.
- Nếu cần đổi rubric/dataset vì chính sách mới, tạo **chuẩn đo mới**, ghi rõ điểm lịch sử không thể so tuyệt đối.
- Nếu model provider không cho pin revision, ghi giới hạn tái lập.
- Nếu có waiver cho regression không critical, phải có phạm vi, thời hạn và người chịu trách nhiệm.
- Việc promote không tự xác nhận deployment production ổn định; tiếp tục quan sát sau triển khai.

### 18.2. Khi chính sách nguồn thay đổi

Giả sử chính sách hoàn phí thay từ 14 ngày sang 21 ngày. Không nên:

1. Sửa âm thầm expected answer của dataset-v3.
2. Giữ tên baseline-v4.
3. So điểm candidate mới với baseline cũ và kết luận prompt tốt hơn.

Thay vào đó, tạo `policy-v4`, dataset snapshot mới với nhãn được review; đánh giá lại cả baseline app và candidate trên nguồn chuẩn mới khi có thể. Ghi đây là **re-benchmark** và lưu quan hệ với baseline cũ.

## 19. Điều tra các điểm bất thường trong phép so

### 19.1. Điểm tăng nhưng nhiều ca critical regress

**Dấu hiệu:** aggregate +3 pp, có một ca tool authorization PASS→FAIL.

**Hướng xử lý:** chặn release, xem actual tool events và backend authorization; xác minh lỗi xảy ra trong candidate hay do fixture. Không dùng 9 ca được sửa để bù 1 lỗi phân quyền.

### 19.2. Retrieval tăng, factual correctness giảm

**Dấu hiệu:** hit@k tăng nhưng model trả sai điều khoản.

**Giả thuyết:** candidate lấy thêm tài liệu cũ, context dài làm mất câu chính, prompt ít ràng buộc citation, hoặc judge/source khác.

**Kiểm tra:** actual retrieved docs, effective context, source dates, prompt, answer và rubric của đúng attempts.

### 19.3. Điểm không đổi, chi phí và latency tăng

**Dấu hiệu:** quality PASS tương đương, p95 tăng 2,1s → 2,8s, tokens tăng.

**Giả thuyết:** top-k lớn, thêm tool round, retry hoặc model response dài.

**Kiểm tra:** trace spans, số lời gọi model, context size, usage từng call, concurrency/quota và bảng giá. Có thể tối ưu pipeline mà không cần đổi model.

### 19.4. Candidate có vẻ tốt vì nhiều ca lỗi không được chấm

**Dấu hiệu:** quality evaluated pass rate tăng, technical completion giảm.

**Nguyên nhân có thể:** provider 429, timeout hoặc judge gặp quota, khiến những ca khó không có verdict.

**Xử lý:** báo evaluation coverage và technical error riêng; không công bố cải thiện toàn diện trước khi chạy đủ cặp hợp lệ hoặc xử lý missingness.

### 19.5. Tất cả điểm đổi cùng lúc sau khi cập nhật judge

**Giả thuyết:** evaluator/rubric mới có độ nghiêm khác.

**Kiểm tra:** chấm lại cùng một bộ answer/effective context đã lưu bằng hai judge; đưa bộ chấm về cùng phiên bản cho phép so. Không cần chạy lại generation nếu evidence đủ để isolating judge effect.

### 19.6. Cùng cấu hình nhưng kết quả dao động

**Giả thuyết:** sampling variance, provider alias drift, corpus động, memory shared state, tool fixture, thời gian/ngữ cảnh thực thi.

**Kiểm tra:** attempts lặp, phiên bản resolved/observed, input isolation, timestamps và môi trường. Không cam kết reproducibility tuyệt đối khi một nguồn bên ngoài không thể pin.

## 20. Bài thực hành: từ verified baseline đến báo cáo hồi quy

**Bối cảnh:** một trợ lý Spring AI dùng RAG để tra chính sách giả định và tool `getOrderStatus`. Nhóm muốn thay prompt trả lời và thử tăng `topK` để cải thiện relevance.

### Vòng A — Chọn baseline đã xác nhận

1. Tạo dataset 100 case với reference facts, source IDs, các ca thiếu nguồn, tool contract và quyền truy cập.
2. Chạy phiên bản hiện hành; lưu run manifest và actual evidence.
3. Chấm relevance, groundedness, factual correctness, retrieval và tool.
4. Review thủ công mẫu các verdict và tất cả ca critical.
5. Kiểm integrity, counts và skip/error/coverage.
6. Tạo approval record; lưu baseline run ID và artifacts bất biến.

**Sản phẩm:** baseline manifest, dataset/rubric version, approval record và per-case outcomes.

### Vòng B — Thử đúng một biến

Đổi prompt `prompt-v4` → `prompt-v5`, giữ dataset, corpus/index, model, rubric/judge, tool fixtures và điều kiện tải tương đương. Chạy candidate, tạo attempt IDs mới; lưu actual context, answer, tool events và metrics.

**Sản phẩm:** hai tập results có case IDs tương ứng và bằng chứng riêng.

### Vòng C — Tạo paired comparison

Lập ma trận 2×2, đếm `PASS→FAIL` và `FAIL→PASS`. Tạo danh sách regressions kèm severity, metric, reason, evidence refs. Tách mọi cặp có TECHNICAL_ERROR/SKIPPED/INCONCLUSIVE.

**Sản phẩm:** report JSON/Markdown, regression list, noncomparable list và paired coverage.

### Vòng D — So metric và vận hành

Đọc riêng relevance, groundedness, factual correctness, hit@k và tool authorization; đo technical completion, p95, token và cost. Khi số liệu xấu đi, mở actual retrieved/effective context và trace của các ca tiêu biểu.

**Sản phẩm:** bảng baseline/candidate theo metric, nhóm case và operational metrics.

### Vòng E — Thử nhiều thay đổi và kiểm giới hạn kết luận

Đổi đồng thời `topK`, corpus hoặc model. Giải thích tại sao phép đo chỉ phản ánh **tác động tổng**, chưa đủ tách riêng nguyên nhân. Thiết kế thêm run một biến để kiểm giả thuyết.

**Sản phẩm:** comparison contract mới, ghi các yếu tố gây nhiễu và kế hoạch kiểm chứng.

### Vòng F — Đề xuất release và nâng baseline

Thiết lập quality/safety/latency/cost gates **trước khi chấm**. Nếu có critical regressions, chặn phát hành. Nếu mọi gate cần thiết đạt và được review, lập approval record mới và nâng candidate thành baseline mới, giữ baseline cũ để audit.

**Sản phẩm:** quyết định có lý do, dấu vết phê duyệt và kế hoạch quan sát sau rollout.

### Checklist nghiệm thu

- [ ] Baseline có ID và approval record, không trỏ mơ hồ vào `latest`.
- [ ] Dataset/reference/rubric/judge có version hoặc snapshot để so.
- [ ] Ghi được intended changes và điều kiện thử.
- [ ] Không ghép answer/context/tool events giữa các attempts.
- [ ] Có verdict từng metric và case aggregate.
- [ ] Ma trận paired PASS/FAIL đếm đúng mọi cặp có thể so.
- [ ] Có danh sách PASS→FAIL, FAIL→PASS và critical regressions.
- [ ] TECHNICAL_ERROR, SKIPPED, INCONCLUSIVE được báo riêng.
- [ ] Có số cặp hợp lệ/mẫu số, không dùng tỷ lệ “đẹp” khi thiếu cặp.
- [ ] Có báo theo nhóm RAG, thiếu nguồn, tool và quyền.
- [ ] p95, input/output tokens và cost có cách đo/đơn giá rõ.
- [ ] Có ghi giới hạn do stochasticity, model alias hoặc dữ liệu động.
- [ ] Release gate không bị vượt qua nhờ trung bình hoặc thiếu evidence.
- [ ] Quy trình promote baseline giữ nguyên lịch sử và có người chịu trách nhiệm.

### Câu hỏi tự kiểm tra

1. Vì sao một run đã chạy tuần trước chưa chắc là baseline đã được xác nhận?
2. Baseline PASS 82/100, candidate PASS 85/100; có thể kết luận candidate không gây hồi quy không?
3. Trong ma trận PASS→FAIL = 6 và FAIL→PASS = 9, có bao nhiêu case đổi kết quả và net gain là bao nhiêu?
4. 3 điểm phần trăm khác với 3% tương đối ra sao?
5. Khi một ca baseline PASS còn candidate provider timeout, nên gọi là quality regression hay technical completion regression?
6. Tại sao phải khóa rubric và judge version khi so?
7. Khi nguồn chuẩn chuyển từ policy-v3 sang policy-v4, nên xử lý baseline và dataset thế nào?
8. Candidate tăng hit@5 nhưng giảm groundedness; bằng chứng nào cần xem trước khi kết luận nguyên nhân?
9. Một model alias không pin revision ảnh hưởng reproducibility thế nào?
10. Tại sao phải lưu per-case transitions thay vì chỉ aggregate pass rate?
11. Đánh giá nhiều lần có thể giúp gì khi một ca LLM trả PASS/FAIL không ổn định?
12. Khi nào phải ưu tiên critical regression hơn ý nghĩa thống kê của chênh lệch trung bình?
13. p95 latency được đo ở concurrency khác nhau có thể so trực tiếp không?
14. Một ca có tool answer đúng nhưng không gọi tool bắt buộc nên được chấm ra sao?
15. Khi judge timeout, có thể chấm lại cùng answer/context mà không gọi model generation không? Điều kiện gì?
16. Candidate đạt quality nhưng chi phí gấp đôi; nên xem thêm những metric nào?
17. Khi report có 100 planned pairs và 25 candidate technical errors, 75 ca còn lại PASS 96%, có nên kết luận chất lượng toàn bộ đã tăng?
18. Quy trình nâng candidate thành baseline mới cần lưu những dữ liệu phê duyệt nào?

## 21. Các sai lầm thường gặp

**Chọn baseline chỉ vì điểm thấp hơn candidate.** Baseline phải có phê duyệt và phạm vi xác nhận rõ.

**Chỉ lưu tên `production` hay `stable`.** Alias có thể thay đổi; cần resolved run/model/source identities và snapshot.

**So hai dataset khác nhau mà không nói.** Pass rate tăng có thể do tập mới dễ hơn.

**Thay rubric/judge và quy thay đổi điểm cho model.** Phải giữ cách chấm tương thích hoặc chấm lại cùng evidence.

**Bỏ qua mọi case candidate ERROR rồi báo 100% PASS.** Cần technical completion, coverage và noncomparable list.

**So theo vị trí dòng trong CSV.** Batch song song có thể trả kết quả khác thứ tự; ghép theo `caseId` và đúng run.

**Đếm retry như nhiều case.** Một case có nhiều attempts nhưng phải có normalization policy.

**Chỉ báo chênh lệch +3 pp.** Cần nêu 9 fixes, 6 regressions và severity của từng ca.

**Tìm nguồn retrieved ở dataset thay vì actual evidence.** Sẽ bỏ sót retrieval failure và groundedness bị chấm sai.

**Gộp lỗi quyền tool vào relevance.** Tool authorization/side effects cần gate riêng.

**Nói p95 tăng là do model dù concurrency/quota khác.** Cần kiểm điều kiện tải và spans.

**Kết luận có ý nghĩa thống kê từ một vài ca.** Phải nêu cỡ mẫu, biến thiên và giới hạn suy luận.

**Đưa prompt, user ID hoặc token bí mật làm metric tags.** Gây rủi ro riêng tư và cardinality lớn; dùng evidence refs có quyền.

**Tự động promote mọi candidate mới.** Phải qua gate, review, approval và giữ baseline cũ bất biến.

## 22. Tổng kết

**So sánh với đường cơ sở đã xác nhận** là một quy trình có kiểm soát, không phải phép trừ hai tỷ lệ PASS. Cần có verified baseline với manifest, dataset/source snapshot, rubric/judge, bằng chứng và quyết định phê duyệt; một comparison contract nêu yếu tố thay đổi và những điều kiện giữ nguyên; cùng một bảng **paired per-case transitions** để phân biệt ca được sửa và ca bị hồi quy.

Trong ứng dụng Spring AI, cần so riêng relevance, groundedness, factual correctness, retrieval, tool behavior và các chỉ số vận hành như p95 latency, token, retries và chi phí. Các ca ERROR, SKIPPED hoặc chưa chấm không được giả làm quality PASS/FAIL; chúng có mẫu số và gate riêng. Một candidate có điểm trung bình cao hơn vẫn có thể bị chặn vì một hồi quy nghiêm trọng.

Khi báo cáo giữ đúng `runId`, `caseId`, `attemptId`, phiên bản cấu hình, context thật, tool events và trace/usage thực, nhóm có thể biến chênh lệch điểm thành **danh sách bằng chứng có thể điều tra**, kiểm chứng nguyên nhân và nâng baseline một cách có trách nhiệm.

### Tài liệu tham khảo

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring Boot — Production-ready Features (Actuator)](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
