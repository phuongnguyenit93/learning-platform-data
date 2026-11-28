# Xác định điều kiện chấp nhận và lý do nâng cấp đường cơ sở

> **Chương:** So sánh thí nghiệm
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm giữa các phiên bản prompt, model và pipeline.
>
> **Bối cảnh kỹ thuật:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. Các ngưỡng và số liệu trong bài là ví dụ minh họa. Nhóm triển khai phải thay bằng yêu cầu nghiệp vụ, risk appetite và SLO đã được phê duyệt.

## 1. Một candidate tốt hơn chưa chắc đã đủ điều kiện thay baseline

Giả sử baseline A đạt fact-check pass rate 90%, candidate B đạt 93%. B có vẻ tốt hơn 3 điểm phần trăm. Nhưng trước khi đổi baseline, cần biết:

- Hai kết quả có dùng cùng dataset, eligibility, judge và scoring policy không?
- Candidate có vượt quality floor và không gây critical regression không?
- Chênh lệch có đủ lớn để tạo giá trị thực tế, và uncertainty có cho phép kết luận không?
- Latency, error rate, cost và operational readiness có nằm trong giới hạn không?
- Model/prompt/corpus/tool configuration của candidate có được định danh và tái tạo không?
- Có lý do nghiệp vụ rõ ràng để thay reference hiện tại không?
- Nếu triển khai gặp vấn đề, có thể rollback về đúng baseline trước đó không?

**Acceptance** là quyết định rằng một candidate đáp ứng hợp đồng kiểm thử đã đăng ký. **Baseline upgrade** là quyết định quản trị rằng candidate được chọn làm reference mới cho các thí nghiệm tiếp theo. **Production rollout** là một quyết định triển khai riêng, cần readiness và kế hoạch vận hành.

Ba quyết định có liên quan nhưng không đồng nghĩa. Candidate có thể pass evaluation nhưng chưa được chọn làm baseline; baseline mới có thể được chấp nhận nhưng rollout vẫn cần canary.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Viết acceptance contract trước khi chạy thí nghiệm.
2. Phân biệt superiority, non-inferiority và equivalence.
3. Xác định quality floor, minimum meaningful improvement và guardrails.
4. Đánh giá evidence bằng estimate, confidence interval, coverage và critical review.
5. Phân biệt candidate accepted, baseline promoted và production released.
6. Chọn lý do nâng cấp baseline dựa trên evidence và nhu cầu nghiệp vụ.
7. Quản lý champion/challenger và baseline lineage.
8. Lập quy trình phê duyệt, canary, rollback và hậu kiểm.
9. Xây report có quyết định PROMOTE, REJECT, HOLD hoặc INCONCLUSIVE.
10. Mô hình hóa acceptance policy bằng Java 21 và JUnit 5.

## 2. Định nghĩa chính xác baseline đang đại diện cho điều gì

Baseline là phiên bản tham chiếu dùng để so sánh candidate. Nó không chỉ là tên model.

Một baseline Spring AI nên định danh tối thiểu:

| Thành phần | Ví dụ định danh |
|---|---|
| Application | service version, git commit |
| Prompt | prompt ID, revision, content hash |
| Model | provider, model ID, resolved model revision nếu có |
| Model options | temperature, max tokens, top-p, response format |
| Spring AI | dependency version và provider starter |
| Retrieval | embedding model, vector store, top-k, filters, reranker |
| Corpus | document snapshot, index revision, metadata filters |
| Tools | tool schema, implementation revision, fixture/API version |
| Evaluator | judge model, prompt, rubric, parser revision |
| Dataset | dataset revision, digest, case IDs |
| Policy | eligibility, thresholds, severity, aggregation weights |
| Runtime | Java/JVM, Spring Boot, deployment configuration |

Nếu provider chỉ cung cấp alias động, ghi rõ alias và metadata resolved mà provider trả về. Không tự khẳng định đã pin model revision nếu API không cung cấp khả năng đó.

### Baseline manifest

~~~yaml
baseline:
  baseline_id: "support-rag-2026-11-01"
  application:
    git_commit: "7d31a4c"
    service_version: "1.8.0"
    java_version: "21"
    spring_boot: "4.2.x"
    spring_ai: "2.1.x"
  generation:
    provider: "provider-x"
    model_id: "model-family"
    resolved_revision: "revision-if-provider-exposes-it"
    prompt_id: "support-answer"
    prompt_revision: "v12"
    options_revision: "chat-options-v3"
  retrieval:
    corpus_revision: "policy-corpus-v8"
    index_revision: "vector-index-v8"
    retriever_revision: "retriever-v4"
  evaluation:
    dataset_revision: "support-eval-v6"
    evaluator_revision: "fact-check-judge-v3"
    rubric_revision: "fact-check-v4"
    policy_revision: "acceptance-v2"
~~~

Đây là schema do project tự định nghĩa. Manifest thực tế nên được serialize, hash và lưu cùng kết quả run.

## 3. Viết acceptance contract trước khi xem kết quả

Acceptance contract là tập điều kiện quyết định candidate có được chấp nhận hay không. Contract phải được tạo trước khi chạy candidate để tránh đổi tiêu chuẩn theo kết quả quan sát.

Một contract nên nêu:

1. **Scope:** service, workflow, domain, language và traffic population.
2. **Comparison:** baseline ID, candidate ID, paired/unpaired design.
3. **Primary metric:** metric chính dùng để đưa ra kết luận.
4. **Decision hypothesis:** superiority, non-inferiority hoặc equivalence.
5. **Practical margin:** mức cải thiện hoặc regression có ý nghĩa nghiệp vụ.
6. **Guardrails:** critical failures, per-slice floors, latency, cost, coverage.
7. **Measurement validity:** dataset, judge, telemetry và completeness.
8. **Sample/stopping plan:** N, run blocks, alpha/power nếu dùng kiểm định.
9. **Decision owner:** người/nhóm có quyền phê duyệt.
10. **Rollback condition:** điều kiện dừng rollout hoặc quay lại baseline.

### Ví dụ contract

~~~yaml
acceptance_contract:
  contract_id: "support-assistant-acceptance-v3"
  scope:
    service: "support-assistant"
    language: "vi"
    workflows: ["policy_rag", "order_lookup"]
  comparison:
    baseline_id: "support-rag-2026-11-01"
    candidate_id: "support-rag-candidate-042"
    design: "paired_case_ids"
  primary_metric:
    id: "fact_check_pass_rate"
    hypothesis: "superiority"
    minimum_meaningful_improvement_pp: 1.0
    confidence_level: 0.95
    confidence_convention: "two_sided_95_ci_for_superiority"
  absolute_requirements:
    minimum_pass_rate: 0.92
    minimum_evaluation_coverage: 0.98
  guardrails:
    maximum_critical_cases: 0
    maximum_slice_regression_pp: 2.0
    maximum_p95_latency_ms: 2000
    maximum_cost_per_eligible_case_usd: 0.025
  stopping:
    mode: "fixed_sample"
    planned_paired_cases: 1200
  approval:
    owner: "ai-quality-owner"
    required_reviewers: ["domain-owner", "service-owner"]
~~~

Các con số trên chỉ minh họa cách biểu diễn contract. N phải xuất phát từ pilot, effect size, sampling design và power; không copy con số 1.200 cho mọi experiment.

## 4. Tách ba lớp điều kiện chấp nhận

Một candidate nên được đánh giá qua ba lớp:

| Lớp | Mục đích | Ví dụ điều kiện |
|---|---|---|
| Measurement validity | Đảm bảo phép so sánh đáng tin | Same dataset IDs, manifest đầy đủ, coverage đạt |
| Product quality | Đảm bảo kết quả đáp ứng nghiệp vụ | Quality floor, primary metric, slice guardrails |
| Operational readiness | Đảm bảo có thể vận hành | Latency SLO, error budget, cost budget, rollback |

Nếu measurement validity fail, không nên tiếp tục diễn giải quality delta như bằng chứng release. Nếu product quality fail, operational efficiency tốt không cứu được candidate. Nếu operational readiness fail, candidate có thể có chất lượng tốt nhưng chưa sẵn sàng triển khai.

### Decision states

- **PROMOTE:** candidate đáp ứng acceptance contract và được đề xuất làm baseline mới.
- **REJECT:** có bằng chứng vi phạm một điều kiện bắt buộc hoặc có regression không chấp nhận.
- **HOLD:** kết quả có triển vọng nhưng cần xử lý vấn đề cụ thể trước khi chạy lại.
- **INCONCLUSIVE:** dữ liệu chưa đủ để kết luận superiority/non-inferiority.
- **BLOCKED:** phép đo không hợp lệ hoặc thiếu dữ liệu quan trọng.

Không dùng HOLD và INCONCLUSIVE như cách né quyết định. Report phải nêu rõ điều kiện cần hoàn thành để chuyển trạng thái.

## 5. Chọn đúng giả thuyết: superiority, non-inferiority hay equivalence

Không phải lần nâng cấp nào cũng cần candidate tốt hơn trên mọi metric.

### Superiority

Dùng khi mục tiêu là chứng minh candidate cải thiện primary metric.

Ví dụ:
- baseline fact-check pass rate: 90%;
- candidate: 93%;
- delta: +3 pp;
- contract yêu cầu cải thiện tối thiểu có ý nghĩa 1 pp.

Nếu CI 95% của delta là [+1,2; +4,8] pp, lower bound cao hơn 1 pp, dữ liệu hỗ trợ mức cải thiện vượt MDE theo thiết kế minh họa.

### Non-inferiority

Dùng khi candidate được kỳ vọng có lợi ích khác (giảm cost, giảm latency, thay provider) và nhóm chấp nhận một mức giảm quality nhỏ đã định trước.

Giả sử:
- delta = candidate − baseline;
- non-inferiority margin = −1 pp;
- one-sided 95% lower confidence bound của delta là −0,4 pp.

Lower bound −0,4 pp lớn hơn margin −1 pp, nên có thể kết luận non-inferior theo giả thuyết và assumptions đã đăng ký. Kết quả chưa chứng minh candidate superior vì lower bound vẫn thấp hơn 0. Nếu dùng two-sided 95% CI thay cho one-sided 95% bound, phép kiểm tra sẽ bảo thủ hơn; contract phải ghi rõ convention.

### Equivalence

Dùng khi muốn chứng minh chênh lệch nằm trong một khoảng tương đương hai phía, ví dụ [−1 pp, +1 pp]. CI phải nằm hoàn toàn trong margin đó theo phương pháp equivalence phù hợp (thường là two one-sided tests/TOST). Với TOST ở alpha 5%, cách trình bày thường dùng two-sided 90% CI; phải ghi đúng confidence level và sidedness đã đăng ký.

Không thể kết luận equivalence chỉ vì p-value của kiểm định khác biệt lớn hơn 0,05.

### Bảng chọn hypothesis

| Mục tiêu nâng cấp | Hypothesis phù hợp |
|---|---|
| Cải thiện factuality/relevance | Superiority |
| Giảm cost nhưng quality không giảm quá mức cho phép | Non-inferiority |
| Thay model provider tương đương về chất lượng | Equivalence hoặc non-inferiority tùy mục tiêu |
| Giảm latency với chất lượng giữ trong margin | Non-inferiority |
| Chứng minh candidate tốt hơn baseline | Superiority |
| Không đủ N hoặc interval quá rộng | INCONCLUSIVE |

Margin phải được chọn theo hậu quả nghiệp vụ, không chọn sau khi thấy CI.

## 6. Phân biệt statistical significance và practical significance

Một chênh lệch rất nhỏ có thể có ý nghĩa thống kê khi N lớn nhưng không đủ để biện minh cho chi phí migration. Ngược lại, một improvement lớn ở nhóm critical có thể quan trọng dù interval còn rộng và cần thêm dữ liệu.

Trước khi chạy, xác định:

- **MDE:** mức thay đổi nhỏ nhất đáng để đầu tư.
- **Quality floor:** mức chất lượng tuyệt đối thấp nhất được chấp nhận.
- **Non-inferiority margin:** mức giảm tối đa chấp nhận khi đổi lấy lợi ích khác.
- **Operational budget:** latency/cost/error giới hạn.
- **Risk tolerance:** loại failure nào không được phép xảy ra.

Ví dụ:
- improvement +0,2 pp, CI rất hẹp, nhưng cần thêm 40% cost: có thể không đáng nâng cấp;
- improvement +2 pp trên policy hard cases, cost tăng 3% trong budget: có thể có giá trị lớn;
- average quality tăng nhưng critical failure xuất hiện: reject nếu policy có veto.

Một acceptance contract tốt ghi cả ngưỡng tuyệt đối và mức thay đổi tương đối. Không để delta tốt che một baseline/candidate vẫn thấp hơn quality floor.

## 7. Điều kiện về tính hợp lệ của phép so sánh

Trước khi đọc metric, kiểm tra:

- baseline và candidate có đúng identity/manifest đã đăng ký;
- dataset revision và expected case IDs có đúng;
- duplicate IDs, missing rows và retries được xử lý đúng;
- metric eligibility và denominator không thay đổi;
- scoring rubric/judge được khóa;
- case labels và slice taxonomy giống nhau;
- context được freeze hay live retrieval đúng với mục tiêu;
- usage/latency telemetry có completeness đủ;
- run timestamps, provider metadata và runtime settings được lưu.

### Khi nào phép so sánh không hợp lệ?

| Vấn đề | Tác động | Hành động |
|---|---|---|
| Dataset revision khác ngoài kế hoạch | Composition confounding | Chạy lại trên common frame hoặc báo riêng |
| Judge thay đổi giữa A/B | Measurement drift | Re-score snapshots bằng cùng judge |
| Candidate thiếu nhiều verdict khó | Complete-case bias | BLOCKED, điều tra missingness |
| Retry policy khác | Cost/latency/quality lệch | Chuẩn hóa policy hoặc phân tích riêng |
| Corpus đổi trong khi mục tiêu chỉ so prompt | Confounding | Freeze corpus/context |
| Model alias thay backend | Identity uncertainty | Ghi resolved metadata; nếu không biết, nêu limitation |
| Tool fixture/API thay đổi | Workflow khác nhau | Khóa fixture hoặc version tool |

Không được “sửa” dữ liệu sau khi xem kết quả mà không ghi deviation. Nếu cần thay đổi contract, phát hành contract revision mới và giải thích vì sao.

## 8. Quality gates: điều kiện bắt buộc trước khi xét promotion

Một acceptance policy có thể gồm:

### Absolute quality floor

Candidate phải đạt ngưỡng tối thiểu của primary metric và những metric bắt buộc. Ví dụ fact-check pass rate ≥ 92%.

### Relative comparison

Candidate phải:
- vượt baseline theo MDE nếu superiority;
- hoặc không kém hơn margin nếu non-inferiority;
- hoặc nằm trong equivalence bounds nếu equivalence.

### Critical veto

Critical failure đã xác minh phải kích hoạt policy riêng. Không để aggregate score bù:
- unauthorized tool execution;
- data leakage;
- prompt injection làm lộ dữ liệu;
- khẳng định trạng thái giao dịch trái với tool result;
- hallucination có hậu quả cao.

### Slice guardrails

Các domain/risk slices quan trọng phải đáp ứng floor và regression tolerance đã đăng ký. Nếu sample quá nhỏ, trả INCONCLUSIVE hoặc human review theo policy.

### Measurement coverage

Coverage, error rate, missing usage và trace completeness phải đạt yêu cầu. Candidate có pass rate cao trên một phần nhỏ case không được coi là đạt.

## 9. Operational gates: quality pass không đồng nghĩa production ready

Candidate được acceptance về quality vẫn phải đáp ứng điều kiện vận hành:

| Nhóm | Điều kiện cần kiểm tra |
|---|---|
| Latency | p95/p99 và TTFT theo SLO |
| Reliability | timeout, 429, 5xx, tool failure, retry rate |
| Cost | serving cost/request, cost per successful case |
| Capacity | throughput, concurrency, queue depth |
| Security | secrets, tenant scope, tool authorization |
| Observability | trace coverage, correlation IDs, alerts |
| Resilience | timeout, fallback, circuit breaker, degraded mode |
| Rollback | artifact/config baseline cũ còn dùng được |
| Data | retention, redaction, privacy controls |
| Compatibility | schema, API contract, deployment constraints |

Đừng coi một test batch chạy concurrency thấp là performance acceptance. Nếu production chịu tải đồng thời, cần load profile tương ứng.

## 10. Vì sao cần lý do nâng cấp baseline được ghi nhận?

Baseline là reference của những thí nghiệm sau. Nếu thay nó tùy tiện:
- các delta trong report cũ/mới không còn cùng điểm tham chiếu;
- regression có thể bị “xóa” bằng cách đổi baseline;
- nhóm khác không biết vì sao model/prompt được chọn;
- không thể tái tạo quyết định;
- việc rollback hoặc audit trở nên khó khăn.

Mỗi baseline upgrade cần một **promotion rationale** gồm:
1. Lý do nghiệp vụ.
2. Evidence so sánh với baseline hiện tại.
3. Acceptance contract revision.
4. Metric đạt/không đạt và uncertainty.
5. Critical/slice review.
6. Operational readiness.
7. Phạm vi rollout.
8. Owner phê duyệt.
9. Baseline predecessor và thời điểm có hiệu lực.
10. Kế hoạch rollback.

### Những lý do nâng cấp hợp lệ

- Quality improvement được chứng minh và có ý nghĩa.
- Model/provider hiện tại bị deprecate hoặc không còn được hỗ trợ.
- Security/privacy/compliance fix bắt buộc.
- Giảm latency/cost đáng kể trong non-inferiority margin.
- Cải thiện tool reliability hoặc RAG grounding.
- Corpus/retriever mới phản ánh nguồn dữ liệu nghiệp vụ được phê duyệt.
- Khắc phục regression production đã xác định.
- Chuẩn hóa runtime/dependency để đáp ứng supportability.

### Những lý do chưa đủ

- “Model mới hơn”.
- “Prompt mới nghe có vẻ tốt hơn”.
- Một vài câu demo trả lời đẹp.
- Overall pass rate tăng nhưng dataset/eligibility khác.
- Cost thấp vì candidate bỏ sót case khó.
- Một p-value nhỏ không có practical value.
- Thay baseline để làm report sau đó trông tích cực hơn.

## 11. Baseline upgrade không phải benchmark reset

Khi nâng baseline, cần giữ lineage:

~~~text
baseline-001 (model A, prompt v4)
        |
        | promotion record PR-042
        v
baseline-002 (model B, prompt v7)
        |
        | promotion record PR-061
        v
baseline-003 (model B, prompt v8, retriever v5)
~~~

Baseline cũ phải được archive/read-only, không xóa. Mỗi promotion tạo một baseline ID mới và trỏ tới predecessor. Kết quả experiment luôn giữ baseline ID tại thời điểm chạy.

### Ba loại thay đổi cần phân biệt

1. **Implementation upgrade:** thay model/prompt/retriever/tool pipeline; cần candidate comparison.
2. **Dataset revision:** thay population/cases/labels; cần dataset migration hoặc benchmark refresh.
3. **Policy revision:** thay threshold/rubric/eligibility/weights; cần policy version và có thể phải re-score.

Không gộp ba loại này thành một “baseline update” duy nhất. Nếu dataset đổi, hãy giữ benchmark revision cũ để đọc lịch sử và tạo series mới có mapping khi cần.

## 12. Champion–challenger và vai trò của baseline

- **Champion:** baseline hiện được chấp nhận và là reference chính.
- **Challenger:** candidate đang được đánh giá.
- **Shadow:** candidate nhận bản sao workload để quan sát, không tác động response production.
- **Canary:** candidate phục vụ một tỷ lệ traffic nhỏ có kiểm soát.
- **Promoted baseline:** challenger đã qua acceptance và được đăng ký thành champion mới.

Challenger không được tự trở thành baseline chỉ vì run cuối cùng có điểm cao. Nó cần qua contract, review và promotion record.

### Khi nào giữ nhiều champion?

Một service có thể có baseline riêng theo:
- locale;
- business workflow;
- risk tier;
- deployment region;
- model capability class.

Chỉ tách baseline nếu có khác biệt nghiệp vụ/technical thực sự và contract riêng. Đừng tạo nhiều baseline để né một regression ở overall.

## 13. Chọn phạm vi promotion

Không nhất thiết phải promote toàn bộ pipeline cùng lúc.

Ví dụ candidate thay đồng thời:
- model;
- prompt;
- retriever;
- index;
- tool schema.

Nếu candidate tốt hơn, chưa biết thành phần nào tạo ra improvement. Với quyết định triển khai, có thể chấp nhận bundle nếu đã kiểm thử đủ. Với mục tiêu học hỏi/attribution, nên chạy ablation hoặc staged experiments để cô lập thay đổi.

### Promotion scope

| Scope | Điều kiện |
|---|---|
| Prompt-only | Model/corpus/retriever/judge giữ nguyên |
| Model-only | Prompt/options giữ nguyên; resolved model identity được ghi |
| Retrieval-only | Generator/judge giữ nguyên; corpus/index snapshot được quản lý |
| Tool-only | Tool schema/fixture và side-effect assertions được version |
| Bundle | Chấp nhận toàn bộ bundle; ghi rõ chưa tách được attribution |

Promotion record phải ghi đúng scope. Không tuyên bố prompt gây ra improvement nếu model và retriever cũng đổi.

## 14. Từ acceptance sang rollout

Quy trình rollout có thể gồm:

1. **Offline evaluation:** chạy benchmark và acceptance contract.
2. **Shadow:** chạy candidate trên traffic copy hoặc replay an toàn; không thực thi side effects thật.
3. **Canary:** mở một tỷ lệ nhỏ traffic với guardrails và owner trực.
4. **Progressive rollout:** tăng traffic khi health metrics ổn định.
5. **Full release:** chỉ khi rollout gates đạt.
6. **Post-release review:** so production metrics với acceptance assumptions.

Với tool có side effect, shadow mode phải mock/sandbox tool hoặc chỉ quan sát quyết định gọi tool; không thực hiện mutation trên production chỉ để đánh giá.

### Canary gate

~~~yaml
canary:
  candidate_id: "support-rag-candidate-042"
  stages:
    - traffic_percent: 1
      minimum_requests: 200
      observation_window_minutes: 30
    - traffic_percent: 5
      minimum_requests: 1000
      observation_window_minutes: 60
    - traffic_percent: 25
      minimum_requests: 5000
      observation_window_minutes: 120
  abort_if:
    critical_incidents: 1
    p95_latency_ms_above: 2000
    error_rate_above: 0.02
  require_owner_acknowledgement: true
~~~

Đây là cấu hình minh họa. Minimum requests và observation windows phải dựa trên traffic, event rate và mức rủi ro. Một cửa sổ 30 phút không có incident không chứng minh rủi ro bằng 0.

## 15. Định nghĩa rollback trước khi deploy

Rollback phải có trigger đo được và artifact đích rõ ràng.

### Trigger có thể gồm

- critical safety/security incident;
- quality signal production vượt regression tolerance;
- p95/p99 hoặc timeout rate vượt SLO;
- provider error/429 tăng vượt ngưỡng;
- tool failure hoặc side-effect mismatch;
- cost/request vượt budget;
- trace/usage telemetry mất khiến không còn khả năng quan sát;
- business owner yêu cầu dừng theo incident policy.

### Rollback record

- candidate baseline ID;
- previous champion baseline ID;
- deployment revision;
- config/model/prompt reference cần khôi phục;
- trigger và timestamp;
- người phê duyệt/incident owner;
- dữ liệu cần giữ cho postmortem;
- xác nhận rollback hoàn tất.

Rollback cần được thử trước rollout lớn. Nếu provider đã deprecate model cũ, cần fallback plan khác thay vì giả định baseline cũ luôn có thể khôi phục.

## 16. Promotion record: ghi lại quyết định

Một record mẫu:

~~~yaml
promotion:
  promotion_id: "PR-042"
  decision: "PROMOTE"
  effective_at: "2026-11-27T10:00:00Z"
  predecessor_baseline_id: "support-rag-2026-11-01"
  promoted_baseline_id: "support-rag-2026-11-27"
  candidate_id: "support-rag-candidate-042"
  acceptance_contract: "support-assistant-acceptance-v3"
  rationale:
    - "Fact-check improvement exceeded the pre-registered practical threshold"
    - "No verified critical regression"
    - "Latency and serving cost remained within approved budgets"
  evidence:
    experiment_report: "experiment-042-report"
    dataset_revision: "support-eval-v6"
    manifest_digest: "sha256:..."
    judge_revision: "fact-check-judge-v3"
  review:
    quality_owner: "approved"
    domain_owner: "approved"
    service_owner: "approved"
  rollout:
    plan: "canary-v2"
    rollback_target: "support-rag-2026-11-01"
~~~

Không ghi tên cá nhân thật nếu không cần. Hệ thống thực tế có thể dùng team/role IDs và approval event IDs.

## 17. Report phải giải thích vì sao candidate được chấp nhận

Một report promotion nên có:

| Phần | Nội dung |
|---|---|
| Decision | PROMOTE/REJECT/HOLD/INCONCLUSIVE/BLOCKED |
| Baseline | Baseline ID và manifest |
| Candidate | Candidate ID và manifest |
| Rationale | Vấn đề nghiệp vụ cần giải quyết |
| Contract | Primary hypothesis, MDE/margin, thresholds |
| Evidence | Estimate, CI, N, coverage, run blocks |
| Guardrails | Critical, slices, quality floor |
| Operations | Latency, reliability, cost, capacity |
| Limitations | Missing metadata, small slices, provider drift |
| Approval | Roles, timestamps, evidence references |
| Rollback | Target baseline và trigger |

### Ví dụ kết luận tốt

> Candidate B được PROMOTE thành baseline mới cho workflow policy RAG. Trên paired dataset revision v6, fact-check pass-rate delta đạt +2,4 pp; CI 95% [1,3; 3,5] pp, vượt MDE +1 pp đã đăng ký. Evaluation coverage đạt 99,5%; không có critical failure đã xác minh. Policy, orders và hard-case guardrails đều đạt. p95 latency là 1,7 giây và serving cost là 0,022 USD/eligible case, nằm trong budget. Promotion áp dụng cho workflow policy RAG; tool workflow orders vẫn giữ baseline hiện tại. Rollout bắt đầu ở canary 1%, rollback target là baseline A.

Đây là ví dụ giả lập. Kết luận thật phải trỏ tới report/manifest đã lưu, không chép số minh họa.

### Ví dụ kết luận INCONCLUSIVE

> Candidate C có pass-rate estimate cao hơn baseline 1,5 pp, nhưng CI 95% là [−0,3; +3,2] pp. Interval chưa chứng minh superiority và chưa đủ hẹp để xác nhận non-inferiority margin −1 pp. Coverage đạt 99%, không có critical event quan sát được. Quyết định là INCONCLUSIVE; cần tăng paired cases theo kế hoạch đã định và giữ baseline hiện tại trong thời gian chờ.

Không diễn giải “không có bằng chứng regression” thành “đã chứng minh an toàn”.

## 18. Khi nào cần nâng cấp dù candidate không thắng benchmark?

Có những lý do bắt buộc hoặc chiến lược:
- model/provider cũ sắp ngừng hoạt động;
- lỗ hổng bảo mật hoặc vi phạm policy cần sửa ngay;
- dependency/runtime không còn được hỗ trợ;
- thay đổi pháp lý hoặc nguồn dữ liệu yêu cầu pipeline mới;
- model cũ có lỗi nghiêm trọng đã xác minh mà benchmark hiện tại chưa bao phủ.

Trong trường hợp này, decision path có thể là **forced migration**:
1. ghi lý do bắt buộc;
2. xác định risk và deadline;
3. bổ sung targeted tests cho failure mode đã biết;
4. so candidate với baseline trên benchmark khả dụng;
5. ghi rõ benchmark không chứng minh superiority nếu không đủ evidence;
6. dùng rollout hạn chế, monitoring tăng cường và rollback/fallback;
7. mở issue để bổ sung dataset sau migration.

Không giả mạo một superiority result để hợp thức hóa migration bắt buộc. Lý do nâng cấp và bằng chứng chất lượng là hai trường riêng.

## 19. Khi nào không nên nâng baseline?

Giữ baseline hiện tại khi:
- candidate không đạt absolute quality floor;
- critical failure đã xác minh và policy veto;
- primary metric không đạt superiority/non-inferiority contract;
- interval quá rộng hoặc sample chưa đủ;
- coverage/eligibility/manifest không hợp lệ;
- regression ở critical slice;
- cost/latency/reliability vượt budget;
- không xác định được candidate identity;
- không có rollback/fallback cho một thay đổi rủi ro cao;
- chỉ có demo hoặc anecdotal feedback mà chưa có evidence đại diện.

Candidate có thể được giữ lại dưới dạng experiment artifact để tiếp tục cải thiện. Không xóa run hoặc đổi baseline để che kết quả không đạt.

## 20. Quản lý nhiều lần thử và tránh chọn kết quả thuận lợi

Nếu nhóm chạy 10 candidates, thay prompt nhiều lần và chỉ promote candidate có kết quả đẹp nhất, selection bias xuất hiện.

Cần:
- đăng ký primary hypothesis và acceptance contract trước;
- lưu mọi candidate/run, kể cả failed;
- ghi số lần thử và những lần xem interim results;
- giữ holdout set hoặc confirmation run khi cần;
- kiểm soát multiple comparisons;
- không reuse holdout cho đến khi nó mất tính độc lập;
- version hóa prompt/model/dataset mỗi lần thay đổi.

### Confirmation run

Khi một candidate có kết quả hứa hẹn trên development evaluation set:
1. đóng băng candidate artifact;
2. chạy confirmation set chưa dùng để tuning;
3. dùng cùng judge/rubric hoặc calibrated evaluation;
4. đánh giá primary metric và guardrails;
5. chỉ sau đó mới xem xét promotion.

Holdout không phải phép màu: nếu holdout bị xem nhiều lần rồi dùng để tuning, nó trở thành development data.

## 21. Java 21: mô hình hóa acceptance decision

Ví dụ sau minh họa policy decision cho một candidate. Nó tách:
- measurement validity;
- absolute quality floor;
- superiority/non-inferiority/equivalence;
- critical veto;
- operational budgets.

Đầu vào là các estimate/CI đã được tính bởi pipeline thống kê. Class này không tự tính confidence interval hoặc p-value.

### File `AcceptanceDecision.java`

~~~java
package com.example.aiquality.acceptance;

import java.util.ArrayList;
import java.util.List;

public final class AcceptanceDecision {
    private AcceptanceDecision() {}

    public enum Hypothesis {
        SUPERIORITY,
        NON_INFERIORITY,
        EQUIVALENCE
    }

    public enum Decision {
        PROMOTE,
        REJECT,
        HOLD,
        INCONCLUSIVE,
        BLOCKED
    }

    public record Evidence(
            boolean manifestsMatchContract,
            boolean datasetAndEligibilityValid,
            boolean judgeCalibrationValid,
            double evaluationCoverage,
            int eligibleCases,
            int evaluatedCases,
            double baselinePassRate,
            double candidatePassRate,
            double deltaCiLower,
            double deltaCiUpper,
            int criticalCases,
            double candidateP95LatencyMs,
            double candidateCostPerEligibleUsd,
            double timeoutRate) {

        public Evidence {
            if (!unit(evaluationCoverage)
                    || eligibleCases <= 0
                    || evaluatedCases < 0 || evaluatedCases > eligibleCases
                    || !unit(baselinePassRate)
                    || !unit(candidatePassRate)
                    || !Double.isFinite(deltaCiLower)
                    || !Double.isFinite(deltaCiUpper)
                    || deltaCiLower < -1.0 || deltaCiUpper > 1.0
                    || deltaCiLower > deltaCiUpper
                    || criticalCases < 0 || criticalCases > evaluatedCases
                    || !nonNegative(candidateP95LatencyMs)
                    || !nonNegative(candidateCostPerEligibleUsd)
                    || !unit(timeoutRate)) {
                throw new IllegalArgumentException("Evidence không hợp lệ");
            }
        }
    }

    public record Policy(
            Hypothesis hypothesis,
            double minimumPassRate,
            double minimumCoverage,
            int minimumEvaluatedCases,
            double minimumMeaningfulImprovement,
            double nonInferiorityMargin,
            double equivalenceMargin,
            double maximumP95LatencyMs,
            double maximumCostPerEligibleUsd,
            double maximumTimeoutRate,
            boolean vetoCriticalCases) {

        public Policy {
            if (hypothesis == null
                    || !unit(minimumPassRate)
                    || !unit(minimumCoverage)
                    || minimumEvaluatedCases < 1
                    || !unit(minimumMeaningfulImprovement)
                    || !unit(nonInferiorityMargin)
                    || nonInferiorityMargin == 0.0
                    || !unit(equivalenceMargin)
                    || equivalenceMargin == 0.0
                    || !nonNegative(maximumP95LatencyMs)
                    || !nonNegative(maximumCostPerEligibleUsd)
                    || !unit(maximumTimeoutRate)) {
                throw new IllegalArgumentException("Policy không hợp lệ");
            }
        }
    }

    public record Result(
            Decision decision,
            List<String> reasons) {}

    public static Result evaluate(Evidence e, Policy p) {
        List<String> reasons = new ArrayList<>();

        if (e == null || p == null) {
            return result(Decision.BLOCKED, "Missing evidence or policy");
        }

        if (!e.manifestsMatchContract()
                || !e.datasetAndEligibilityValid()
                || !e.judgeCalibrationValid()) {
            return result(Decision.BLOCKED,
                    "Measurement identity, dataset or judge validation failed");
        }

        if (p.vetoCriticalCases() && e.criticalCases() > 0) {
            return result(Decision.REJECT,
                    "Verified critical cases trigger the safety veto");
        }

        if (e.evaluationCoverage() < p.minimumCoverage()
                || e.evaluatedCases() < p.minimumEvaluatedCases()) {
            return result(Decision.INCONCLUSIVE,
                    "Coverage or evaluated sample is below the registered minimum");
        }

        if (e.candidatePassRate() < p.minimumPassRate()) {
            reasons.add("Candidate is below the absolute quality floor");
        }

        if (e.candidateP95LatencyMs() > p.maximumP95LatencyMs()) {
            reasons.add("Candidate exceeds the p95 latency budget");
        }

        if (e.candidateCostPerEligibleUsd()
                > p.maximumCostPerEligibleUsd()) {
            reasons.add("Candidate exceeds the cost budget");
        }

        if (e.timeoutRate() > p.maximumTimeoutRate()) {
            reasons.add("Candidate exceeds the timeout-rate budget");
        }

        switch (p.hypothesis()) {
            case SUPERIORITY -> {
                if (e.deltaCiLower() <= p.minimumMeaningfulImprovement()) {
                    reasons.add("CI lower bound does not exceed the practical improvement threshold");
                }
            }
            case NON_INFERIORITY -> {
                if (e.deltaCiLower() <= -p.nonInferiorityMargin()) {
                    reasons.add("CI does not establish non-inferiority");
                }
            }
            case EQUIVALENCE -> {
                if (e.deltaCiLower() <= -p.equivalenceMargin()
                        || e.deltaCiUpper() >= p.equivalenceMargin()) {
                    reasons.add("CI is not fully inside the equivalence bounds");
                }
            }
        }

        if (!reasons.isEmpty()) {
            boolean uncertaintyOnly = reasons.size() == 1
                    && (reasons.getFirst().contains("CI")
                        || reasons.getFirst().contains("non-inferiority")
                        || reasons.getFirst().contains("equivalence"));
            return new Result(
                    uncertaintyOnly ? Decision.INCONCLUSIVE : Decision.REJECT,
                    List.copyOf(reasons));
        }

        return result(Decision.PROMOTE,
                "All registered acceptance conditions passed");
    }

    private static boolean unit(double value) {
        return Double.isFinite(value) && value >= 0.0 && value <= 1.0;
    }

    private static boolean nonNegative(double value) {
        return Double.isFinite(value) && value >= 0.0;
    }

    private static Result result(Decision decision, String reason) {
        return new Result(decision, List.of(reason));
    }
}
~~~

Ghi chú về ví dụ code:
- Java 21 hỗ trợ record, switch expression và sequenced collections như `getFirst()`.
- deltaCiLower và deltaCiUpper phải là bound của đúng paired/unpaired estimand và confidence convention đã định nghĩa; không lấy hiệu hai CI độc lập để thay paired CI.
- Các rate/margin trong Java dùng thang proportion: `0.01` tương ứng 1 điểm phần trăm; latency dùng milliseconds và cost dùng USD.
- Code dùng CI bound như rule đơn giản minh họa. Production policy cần xác định alpha, sidedness, method và multiple-testing adjustment.
- `baselinePassRate` được giữ để tính delta point estimate; acceptance superiority dựa vào CI lower bound đã tính từ pipeline.
- Guardrails theo slice/critical workflow cần được đánh giá trước khi truyền kết quả cuối vào decision engine; ví dụ code này chỉ nhận tổng critical count.
- Hai record validate các miền giá trị cơ bản; production vẫn cần kiểm tra policy completeness, hypothesis-specific margins, alpha/method metadata và tương thích giữa contract với estimand.
- HOLD là trạng thái workflow khi chờ xử lý hoặc phê duyệt; helper thống kê này chỉ trả PROMOTE, REJECT, INCONCLUSIVE hoặc BLOCKED.

## 22. JUnit 5: kiểm tra acceptance states

### File `AcceptanceDecisionTest.java`

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

import com.example.aiquality.acceptance.AcceptanceDecision;
import com.example.aiquality.acceptance.AcceptanceDecision.*;

class AcceptanceDecisionTest {

    private static Policy superiorityPolicy() {
        return new Policy(
            Hypothesis.SUPERIORITY,
            0.92, 0.98, 100,
            0.01, 0.01, 0.01,
            2000, 0.025, 0.01, true);
    }

    private static Evidence goodEvidence() {
        return new Evidence(
            true, true, true,
            0.995, 1200, 1194,
            0.90, 0.93,
            0.012, 0.048,
            0,
            1700, 0.022, 0.005);
    }

    @Test
    void promotesCandidateWhenEveryGatePasses() {
        var result = AcceptanceDecision.evaluate(
            goodEvidence(), superiorityPolicy());

        assertEquals(Decision.PROMOTE, result.decision());
    }

    @Test
    void blocksInvalidMeasurementManifest() {
        var e = goodEvidence();
        var invalid = new Evidence(
            false, e.datasetAndEligibilityValid(),
            e.judgeCalibrationValid(), e.evaluationCoverage(),
            e.eligibleCases(), e.evaluatedCases(),
            e.baselinePassRate(), e.candidatePassRate(),
            e.deltaCiLower(), e.deltaCiUpper(),
            e.criticalCases(), e.candidateP95LatencyMs(),
            e.candidateCostPerEligibleUsd(), e.timeoutRate());

        assertEquals(Decision.BLOCKED,
            AcceptanceDecision.evaluate(invalid, superiorityPolicy()).decision());
    }

    @Test
    void returnsInconclusiveWhenCoverageIsTooLow() {
        var lowCoverage = new Evidence(
            true, true, true, 0.80,
            1200, 960, 0.90, 0.93,
            0.012, 0.048, 0,
            1700, 0.022, 0.005);

        assertEquals(Decision.INCONCLUSIVE,
            AcceptanceDecision.evaluate(lowCoverage, superiorityPolicy()).decision());
    }

    @Test
    void criticalFailureOverridesGoodAggregateMetrics() {
        var e = goodEvidence();
        var critical = new Evidence(
            true, true, true, 0.80,
            e.eligibleCases(), 960,
            e.baselinePassRate(), e.candidatePassRate(),
            e.deltaCiLower(), e.deltaCiUpper(),
            1, e.candidateP95LatencyMs(),
            e.candidateCostPerEligibleUsd(), e.timeoutRate());

        assertEquals(Decision.REJECT,
            AcceptanceDecision.evaluate(critical, superiorityPolicy()).decision());
    }

    @Test
    void nonInferiorityCanAcceptAnEfficiencyUpgrade() {
        var policy = new Policy(
            Hypothesis.NON_INFERIORITY,
            0.90, 0.98, 100,
            0.01, 0.01, 0.01,
            1500, 0.015, 0.01, true);

        var e = new Evidence(
            true, true, true, 0.995,
            1200, 1194, 0.92, 0.925,
            -0.004, 0.018, 0,
            1200, 0.012, 0.003);

        assertEquals(Decision.PROMOTE,
            AcceptanceDecision.evaluate(e, policy).decision());
    }

    @Test
    void equivalenceRequiresTheWholeIntervalInsideBothMargins() {
        var policy = new Policy(
            Hypothesis.EQUIVALENCE,
            0.90, 0.98, 100,
            0.01, 0.01, 0.01,
            2000, 0.025, 0.01, true);

        var e = new Evidence(
            true, true, true, 0.995,
            1200, 1194, 0.92, 0.921,
            -0.005, 0.008, 0,
            1500, 0.020, 0.004);

        assertEquals(Decision.PROMOTE,
            AcceptanceDecision.evaluate(e, policy).decision());
    }

    @Test
    void rejectsCandidateThatMissesLatencyBudget() {
        var e = goodEvidence();
        var slow = new Evidence(
            true, true, true, e.evaluationCoverage(),
            e.eligibleCases(), e.evaluatedCases(),
            e.baselinePassRate(), e.candidatePassRate(),
            e.deltaCiLower(), e.deltaCiUpper(), 0,
            2500, e.candidateCostPerEligibleUsd(), e.timeoutRate());

        assertEquals(Decision.REJECT,
            AcceptanceDecision.evaluate(slow, superiorityPolicy()).decision());
    }
}
~~~

Đây là code hướng dẫn, chưa được compile hoặc chạy trong phạm vi viết bài. Hãy đặt đúng package, thêm JUnit 5 và kiểm tra lại policy semantics trước khi dùng trong CI. Ví dụ decision engine cố ý đơn giản; hệ thống thật cần thêm per-slice guardrails, cost completeness, latency sample count, CI metadata, approval state và rollback readiness.

## 23. Quy trình promotion từ candidate thành baseline mới

~~~mermaid
flowchart TD
  A["Register candidate and acceptance contract"] --> B["Freeze manifest, dataset, judge and policy"]
  B --> C["Run paired evaluation and operational tests"]
  C --> D["Validate measurement coverage and identity"]
  D --> E{"Measurement valid?"}
  E -- "No" --> F["BLOCKED"]
  E -- "Yes" --> G["Evaluate quality hypothesis and guardrails"]
  G --> H{"Critical veto or hard gate failure?"}
  H -- "Yes" --> I["REJECT"]
  H -- "No" --> J{"Evidence sufficient?"}
  J -- "No" --> K["INCONCLUSIVE / HOLD"]
  J -- "Yes" --> L["Review rationale and approvals"]
  L --> M{"Owners approve?"}
  M -- "No" --> N["HOLD / REJECT"]
  M -- "Yes" --> O["Create immutable promotion record"]
  O --> P["Register new baseline ID"]
  P --> Q["Shadow / canary rollout"]
  Q --> R{"Production gates pass?"}
  R -- "No" --> S["Rollback to predecessor"]
  R -- "Yes" --> T["Complete rollout and post-release review"]
~~~

### Trình tự có thể audit

1. Tạo candidate ID và contract revision.
2. Freeze manifest và dataset.
3. Chạy experiment, lưu raw outcomes và telemetry.
4. Kiểm tra measurement validity.
5. Đánh giá primary hypothesis, absolute floors và guardrails.
6. Tạo report có decision và reasons.
7. Lấy phê duyệt từ quality/domain/service owners.
8. Tạo promotion record và baseline ID mới.
9. Triển khai shadow/canary theo rollout plan.
10. Đánh giá production gates và đóng promotion.

## 24. Mẫu decision report và promotion checklist

### Report ngắn

~~~yaml
decision_report:
  experiment_id: "support-rag-042"
  baseline_id: "support-rag-2026-11-01"
  candidate_id: "support-rag-candidate-042"
  contract_revision: "support-assistant-acceptance-v3"
  decision: "PROMOTE"
  primary_metric:
    id: "fact_check_pass_rate"
    baseline: 0.90
    candidate: 0.93
    delta_pp: 3.0
    ci_95_pp: [1.2, 4.8]
    hypothesis: "SUPERIORITY"
    minimum_meaningful_improvement_pp: 1.0
  measurement:
    eligible_cases: 1200
    evaluated_cases: 1194
    coverage: 0.995
    manifest_valid: true
    judge_calibrated: true
  guardrails:
    critical_cases: 0
    maximum_slice_regression_pp: 0.8
    p95_latency_ms: 1700
    cost_per_eligible_case_usd: 0.022
  rationale:
    - "Primary metric exceeded the registered improvement threshold"
    - "Absolute quality and operational budgets passed"
    - "No critical or slice guardrail regression"
  approvals:
    quality_owner: "APPROVED"
    domain_owner: "APPROVED"
    service_owner: "APPROVED"
  predecessor_baseline_id: "support-rag-2026-11-01"
  promoted_baseline_id: "support-rag-2026-11-27"
  rollback_target: "support-rag-2026-11-01"
~~~

Ví dụ này là dữ liệu giả lập. Trong report thực tế, CI phải được tính từ paired/unpaired design đã đăng ký và các slice rows phải được đính kèm.

### Checklist trước khi nâng baseline

- [ ] Có lý do nghiệp vụ cụ thể cho promotion.
- [ ] Baseline và candidate có manifest/identity rõ ràng.
- [ ] Acceptance contract được đăng ký trước.
- [ ] Dataset, eligibility, judge và rubric được version hóa.
- [ ] Primary hypothesis và practical margin được chọn đúng.
- [ ] Absolute quality floor đạt.
- [ ] Superiority/non-inferiority/equivalence được kết luận đúng method.
- [ ] CI, N, coverage và run blocks được báo.
- [ ] Critical failures đã được review và veto policy được áp dụng.
- [ ] Per-slice guardrails đạt hoặc có disposition rõ.
- [ ] Latency, reliability, cost và capacity đạt operational budgets.
- [ ] Serving cost được tách khỏi offline evaluation cost.
- [ ] Multiple testing và interim peeking được ghi nhận.
- [ ] Candidate có thể tái tạo từ manifest.
- [ ] Baseline predecessor được giữ lại.
- [ ] Promotion rationale và approvals được lưu.
- [ ] Rollback target và trigger được xác định.
- [ ] Canary/shadow plan được chuẩn bị.
- [ ] Post-release review owner và thời điểm đánh giá được xác định.

## 25. Những nguyên tắc cần giữ khi nâng cấp baseline

1. Baseline là một artifact có version, manifest và lineage; không phải tên model đơn lẻ.
2. Acceptance contract phải có trước khi xem kết quả.
3. Superiority, non-inferiority và equivalence là ba câu hỏi khác nhau.
4. Statistical significance không tự chứng minh practical value.
5. Critical failure không được bù bởi average score, latency thấp hay cost rẻ.
6. Candidate pass evaluation chưa đồng nghĩa được promote hoặc production release.
7. Dataset revision và policy revision phải được quản lý riêng với implementation revision.
8. Mọi lần thử đều phải lưu, kể cả candidate bị reject.
9. Forced migration cần được ghi rõ lý do và risk mitigation, không giả làm superiority.
10. Promotion phải giữ predecessor, approvals, evidence và rollback path.

## Tài liệu tham khảo

1. [NIST Engineering Statistics Handbook](https://www.itl.nist.gov/div898/handbook/): hypothesis testing, confidence intervals và experimental design.
2. [FDA — Non-Inferiority Clinical Trials](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/non-inferiority-clinical-trials): nguyên tắc margin và diễn giải non-inferiority; ví dụ thuộc lĩnh vực lâm sàng, chỉ tham khảo khái niệm thống kê.
3. [ICH E9(R1) Estimands and Sensitivity Analysis](https://www.ich.org/page/efficacy-guidelines): định nghĩa estimand và sensitivity analysis.
4. [Google SRE Workbook — Implementing SLOs](https://sre.google/workbook/implementing-slos/): SLO, error budget và quyết định rollout.
5. [Google SRE Workbook — Canarying Releases](https://sre.google/workbook/canarying-releases/): canary deployment và so sánh candidate.
6. [Spring AI — Evaluation](https://docs.spring.io/spring-ai/reference/api/testing.html): evaluator và evaluation request.
7. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): Observation, traces và token usage.
8. [OpenTelemetry — Semantic Conventions for GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/): model call và token usage conventions.
9. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm trong logs và telemetry.

> **Ghi nhớ:** Nâng baseline là một quyết định có bằng chứng và có chủ sở hữu. Hãy định nghĩa acceptance contract trước, xác nhận measurement validity, chọn đúng hypothesis, kiểm tra quality và operational gates, rồi ghi promotion rationale cùng predecessor và rollback path. Một candidate chỉ trở thành baseline mới khi nhóm có thể giải thích rõ vì sao nó được chọn và tái tạo được evidence dẫn đến quyết định đó.
