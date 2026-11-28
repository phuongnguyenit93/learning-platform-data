# Lấy mẫu đánh giá khi vận hành theo mục tiêu chất lượng

## 1. Vì sao cần lấy mẫu evaluation trong production?

Trong môi trường production, một ứng dụng Spring AI có thể xử lý hàng nghìn hoặc hàng triệu requests. Chạy đầy đủ một bộ evaluator cho mọi request có thể quá tốn kém, làm tăng latency, tiêu thụ quota model và tạo thêm dữ liệu cần lưu trữ. Tuy nhiên, chỉ đánh giá một vài ví dụ do nhóm tự chọn cũng không phản ánh được chất lượng thực tế.

Lấy mẫu evaluation giúp chọn một tập request/task đại diện hoặc có rủi ro cao để đo relevance, factual correctness, groundedness, retrieval quality và tool correctness. Kết quả được dùng để theo dõi mục tiêu chất lượng, phát hiện drift, tìm regression và quyết định khi nào cần điều tra sâu hơn.

Lấy mẫu phải bắt đầu từ mục tiêu chất lượng. Nếu mục tiêu là giữ factual correctness trên 98%, chiến lược lấy mẫu phải tạo đủ bằng chứng cho chỉ số đó, theo từng cohort quan trọng. Nếu mục tiêu là phát hiện tool authorization violation, random sampling đơn thuần có thể không đủ vì sự kiện hiếm và có mức độ nghiêm trọng cao.

Trong module SPRING_AI_EVALUATION_OBSERVABILITY, sampling kết nối dữ liệu production với evaluation dataset và cost-performance: request được chọn sẽ tạo evaluation case, được chấm bằng deterministic checks, LLM-as-a-judge hoặc human review, rồi liên kết với usage, cost và trace.

### Kết quả học tập

Sau bài này, người học có thể:

1. Xác định population, sampling unit và quality objective.
2. Chọn giữa census, random, stratified, risk-based và adaptive sampling.
3. Tính sample size theo confidence level và margin of error.
4. Thiết kế sampling đủ sức phát hiện lỗi hiếm.
5. Dùng sampling weights để hiệu chỉnh khi oversample cohort rủi ro.
6. Kết hợp deterministic evaluation, judge model và human review.
7. Kiểm soát bias, missing data, duplicate và privacy.
8. Theo dõi chất lượng theo cohort, release và thời gian.
9. Quản lý sampling budget và xây quy trình phản ứng khi quality objective không đạt.

## 2. Xác định mục tiêu chất lượng trước khi chọn mẫu

Sampling plan phải trả lời được câu hỏi “chúng ta muốn biết điều gì?” trước khi quyết định lấy bao nhiêu request.

| Quality objective | Metric có thể dùng | Sampling cần chú ý |
|---|---|---|
| Câu trả lời đúng sự thật | Factual correctness, claim accuracy | Chọn case có ground truth/evidence; oversample high-risk claims |
| Câu trả lời bám tài liệu | Groundedness, supported claim ratio | Lưu retrieval evidence và output |
| Trả lời đúng intent | Relevance, intent match | Bao phủ task types và ngôn ngữ |
| RAG truy xuất đủ evidence | Recall@k, context precision | Có expected evidence/chunk labels |
| Tool được dùng đúng | Tool selection/argument/execution correctness | Lưu tool decision và tool result |
| Không vi phạm policy | Violation rate, refusal correctness | Risk-based/adversarial sampling và hard gates |
| Đáp ứng trải nghiệm | Task success, latency SLO, complaint rate | Bao phủ cohort, p95 và failure paths |

### Định nghĩa ngưỡng và hành động

Một quality objective cần nêu:

- Metric và cách tính.
- Ngưỡng mục tiêu.
- Cohort/phạm vi áp dụng.
- Cửa sổ thời gian.
- Sample size hoặc độ chính xác cần đạt.
- Cách xử lý khi thiếu mẫu.
- Hành động khi vượt ngưỡng hoặc confidence interval cho thấy suy giảm.

Ví dụ: “Factual correctness toàn bộ task RAG đạt ít nhất 98% trong cửa sổ 7 ngày, đồng thời không có critical unsupported claim ở nhóm high-risk.” Đây là mục tiêu có thể thiết kế sampling và review plan. “AI phải trả lời tốt” thì chưa đủ cụ thể.

Không dùng average toàn hệ thống để che giấu cohort có chất lượng thấp. Nếu task tài chính, pháp lý hoặc quyền truy cập có yêu cầu riêng, cần objective và sampling minimum riêng.

## 3. Population, sampling frame và sampling unit

Ba khái niệm cần tách:

- **Population:** toàn bộ đối tượng mà nhóm muốn đưa ra kết luận, ví dụ mọi task RAG production trong tuần.
- **Sampling frame:** danh sách/stream các đối tượng thực sự có thể được chọn, ví dụ event đã được ghi vào telemetry store.
- **Sampling unit:** đơn vị được chọn và chấm, ví dụ request, task, conversation, attempt hoặc claim.

Sampling frame không bao phủ đầy đủ population sẽ tạo coverage bias. Ví dụ, nếu chỉ lấy requests có response hoàn chỉnh, các timeout và provider failures sẽ bị loại khỏi mẫu; kết quả quality có thể trông tốt hơn thực tế.

### Chọn sampling unit theo câu hỏi

| Unit | Phù hợp khi | Rủi ro nếu chọn sai |
|---|---|---|
| Request | Đo endpoint response hoặc model call | Một task nhiều requests có thể bị đếm nhiều lần |
| Task | Đo kết quả nghiệp vụ cuối cùng | Cần liên kết mọi attempts/operations |
| Conversation/session | Đo chất lượng qua nhiều lượt | Các lượt trong session phụ thuộc nhau |
| Attempt | Phân tích retry và recovery | Không đại diện số task độc lập |
| Claim | Fact checking từng mệnh đề | Nhiều claims trong một answer không độc lập |
| Trace | Điều tra đường đi và latency | Trace sampling không tự tạo ground truth |

Ví dụ người dùng hỏi về đơn hàng, ứng dụng gọi model, tool API rồi model follow-up. Nếu mục tiêu là “task được giải quyết đúng không?”, hãy chọn task làm sampling unit; trace và model calls là dữ liệu con của task.

## 4. Census hay sampling?

**Census** là đánh giá tất cả đối tượng trong population. **Sampling** là đánh giá một phần được chọn theo thiết kế.

| Phương pháp | Ưu điểm | Hạn chế | Dùng khi |
|---|---|---|---|
| Census | Không có sampling error cho population đã quan sát | Tốn evaluator/compute; có thể không khả thi | Deterministic checks rẻ, tập nhỏ hoặc kiểm tra bắt buộc |
| Simple random | Ước lượng population dễ hiểu | Có thể bỏ sót cohort hiếm | Traffic tương đối đồng nhất |
| Stratified | Đảm bảo coverage các cohort | Cần phân tầng và weighting | Nhiều task/model/region khác nhau |
| Risk-based | Tập trung vào sự kiện hậu quả cao | Không tự đại diện population | Safety, authorization, high-impact workflows |
| Systematic | Dễ triển khai theo dòng event | Có thể bias nếu có chu kỳ | Stream không có periodic pattern nguy hiểm |
| Adaptive | Tăng mẫu khi thấy tín hiệu bất thường | Cần version policy và xử lý bias | Monitoring liên tục, có alert/drift |

Một kiến trúc thực tế thường dùng census cho checks rẻ và bắt buộc (schema, authorization result, required fields), random/stratified sample cho chất lượng tổng thể, và risk-based sample cho các trường hợp nguy hiểm hoặc bất thường.

Không gọi một tập chỉ gồm các case bị trigger bởi anomaly là “random sample đại diện”. Đó là tập risk-enriched dùng để phát hiện lỗi; muốn ước lượng tỷ lệ toàn population phải có inclusion probabilities hoặc một random baseline riêng.

## 5. Simple random sampling

Trong simple random sampling, mỗi unit trong population có xác suất được chọn như nhau. Với population có N units và lấy n units không hoàn lại, mỗi unit có inclusion probability:

\[
\pi_i = \frac{n}{N}
\]

Ưu điểm là estimator đơn giản và dễ giải thích. Hạn chế là cohort hiếm có thể không xuất hiện trong mẫu.

### Ví dụ

Một ngày có 100.000 tasks, chọn ngẫu nhiên 1.000 tasks:

\[
\pi = 1000/100000 = 0.01 = 1\%
\]

Mỗi task có cơ hội 1% được chọn. Nếu chỉ 0,1% tasks là tool workflow nhạy cảm, kỳ vọng mẫu chỉ có một case loại này; có thể không đủ để đánh giá tool correctness.

### Triển khai có thể tái lập

- Dùng random seed hoặc deterministic hash để tạo selection ổn định.
- Lưu sampling algorithm/version và population window.
- Lưu inclusion probability hoặc selection weight.
- Chống chọn trùng cùng unit trong một sampling window nếu không chủ ý.
- Giữ sampling frame và số units đủ điều kiện để audit.

Nếu stream rất lớn, có thể dùng hash sampling theo stable ID thay cho lưu toàn bộ danh sách rồi shuffle. Hash phải dùng key ổn định và secret/seed được quản lý nếu tránh bị thao túng selection.

## 6. Stratified sampling theo cohort

Stratified sampling chia population thành các strata không chồng lấn theo một hoặc nhiều thuộc tính, rồi lấy mẫu trong từng stratum.

Ví dụ strata:

- Simple answer, RAG, tool workflow, long-context.
- Model/provider/region.
- Tenant tier hoặc product surface.
- Ngôn ngữ.
- Risk level.
- Release/prompt version.

Mỗi stratum cần có định nghĩa rõ và được gán trước khi biết evaluation outcome. Không tạo stratum dựa trên score cuối rồi dùng nó để báo population pass rate nếu không có thiết kế phù hợp.

### Proportional allocation

Nếu muốn mẫu có tỷ trọng giống population, lấy:

\[
n_h = n \times \frac{N_h}{N}
\]

Trong đó N_h là population size của stratum h, N là tổng population và n là tổng sample size.

Ví dụ traffic có 70% simple, 25% RAG và 5% tool. Với n = 2.000:

- Simple: 1.400 cases.
- RAG: 500 cases.
- Tool: 100 cases.

Đây là phân bổ theo traffic mix. Nếu 100 tool cases không đủ để kiểm tra rủi ro, có thể oversample tool cohort rồi dùng weights khi tính estimate toàn population.

### Disproportionate allocation

Có thể lấy nhiều hơn ở stratum nhỏ nhưng quan trọng. Ví dụ 500 tool cases dù chỉ chiếm 5% traffic. Khi đó không lấy trung bình thô của tất cả sample để suy ra population rate; cần trọng số theo population share/inclusion probability.

## 7. Sampling weights và ước lượng population

Khi inclusion probability khác nhau, mỗi sampled unit cần trọng số:

\[
w_i = \frac{1}{\pi_i}
\]

Với stratified sample, population quality rate có thể ước lượng bằng:

\[
\widehat{Q} =
\sum_{h=1}^{H}
\frac{N_h}{N}\widehat{Q}_h
\]

Trong đó Q̂_h là quality rate quan sát trong stratum h. Công thức này đảm bảo cohort được oversample không làm méo tỷ lệ toàn population.

### Ví dụ

Population:

- Simple: 70%, quality pass 98%.
- RAG: 25%, quality pass 95%.
- Tool: 5%, quality pass 90%.

Quality pass rate có trọng số:

\[
\widehat{Q} =
0.70(0.98)+0.25(0.95)+0.05(0.90)
=0.9685=96.85\%
\]

Nếu lấy sample 500 simple, 500 RAG và 500 tool rồi tính average thô, kết quả là 94,33%. Con số đó mô tả sample đã oversample tool, không phải traffic mix thực tế.

Hãy báo cả:

- Weighted population estimate.
- Unweighted sample result.
- Stratum-level rates và sample sizes.
- Sampling design/version.

Nếu weights rất lớn vì một unit có inclusion probability rất nhỏ, estimator có variance cao. Cần xem effective sample size và thiết kế lại allocation.

## 8. Risk-based sampling cho lỗi nghiêm trọng

Risk-based sampling tăng xác suất chọn các task có khả năng sai hoặc có hậu quả cao:

- Tool gọi operation có side effect.
- Task truy cập dữ liệu nhạy cảm hoặc tenant-scoped.
- Model/prompt mới được rollout.
- RAG retrieval confidence thấp hoặc không tìm thấy evidence.
- Output có unsupported claims hoặc contradiction signals.
- Model fallback, retry nhiều vòng hoặc tool loop bất thường.
- Latency/cost vượt percentile threshold.
- User feedback tiêu cực hoặc escalation.

### Risk score không thay thế xác suất chọn

Có thể tính risk score từ các signals, nhưng cần tách:

- Risk score: mức ưu tiên review.
- Inclusion probability: xác suất unit được chọn.
- Sampling weight: hệ số dùng để ước lượng population nếu cần.

Nếu chỉ lấy top-risk cases, sample phù hợp để tìm lỗi nhưng không đại diện tỷ lệ lỗi toàn bộ traffic. Giữ một random baseline để đo population trend.

### Hard-gate events

Một số sự kiện nên được ghi nhận/đánh giá toàn bộ bằng deterministic rule, không chờ sampling:

- Authorization denied/allowed decision.
- Tool schema validation failures.
- Cross-tenant access attempt.
- Policy enforcement result.
- Output schema violation có thể kiểm tra bằng code.

LLM judge/human review có thể bổ sung giải thích, nhưng không thay thế enforcement check bắt buộc.

## 9. Systematic sampling và các bẫy chu kỳ

Systematic sampling chọn mỗi k-th unit sau một điểm bắt đầu ngẫu nhiên. Ví dụ cứ 100 tasks chọn một task.

Ưu điểm:

- Dễ triển khai trên event stream.
- Phân bố mẫu đều theo thời gian.
- Chi phí tính toán thấp.

Rủi ro:

- Nếu traffic có chu kỳ trùng với k, mẫu có thể thiên lệch.
- Nếu event ordering theo tenant hoặc task type, có thể chọn quá nhiều một nhóm.
- Nếu attacker biết quy tắc chọn, họ có thể né sampling.

Nếu dùng systematic sampling:

1. Chọn random start trong khoảng [0, k-1].
2. Theo dõi event ordering và periodic patterns.
3. Dùng nhiều independent offsets hoặc hash-based selection.
4. So sánh distribution mẫu với population.
5. Version hóa sampling interval và seed.

Không dùng “mỗi request thứ 100” như chiến lược duy nhất nếu thứ tự request có cấu trúc.

## 10. Adaptive sampling và trigger theo tín hiệu

Adaptive sampling thay đổi sampling rate theo thời gian dựa trên signals như error rate, drift, cost spike hoặc release changes.

Ví dụ:

- Baseline: random sample 1% traffic.
- Sau khi release prompt mới: tăng lên 10% trong 2 giờ.
- Khi factual correctness giảm dưới threshold: tăng sampling ở cohort RAG liên quan.
- Khi provider 429 tăng: ưu tiên sample failures/timeouts để điều tra.
- Khi incident kết thúc: quay về baseline sau khi quality ổn định.

### Adaptive sampling cần guardrails

- Luôn giữ random baseline để ước lượng population.
- Ghi sampling policy version và inclusion probability cho từng unit.
- Giới hạn maximum sampling rate theo budget.
- Có minimum sample cho cohort high-risk.
- Có hysteresis để tránh sampling rate dao động liên tục.
- Không thay đổi rule giữa một report window mà không lưu policy revision.

Khi sampling rate thay đổi theo tín hiệu, dữ liệu không thể gộp bằng average thô. Dùng inclusion probabilities/weights hoặc báo riêng các windows.

## 11. Tính sample size cho quality rate

Với mục tiêu ước lượng một tỷ lệ (ví dụ pass rate) trong population lớn, sample size sơ bộ:

\[
n_0 = \frac{z^2 p(1-p)}{e^2}
\]

Trong đó:

- z là quantile theo confidence level (1,96 cho 95% two-sided interval).
- p là tỷ lệ dự kiến.
- e là margin of error tuyệt đối.

Nếu chưa biết p, dùng p = 0,5 để có sample size bảo thủ lớn nhất cho cùng z và e.

### Ví dụ

Muốn ước lượng pass rate với confidence 95%, margin of error ±3 điểm phần trăm, giả định p = 0,95:

\[
n_0 =
\frac{1.96^2 \times 0.95 \times 0.05}{0.03^2}
\approx 203
\]

Nếu chưa biết p và dùng 0,5:

\[
n_0 =
\frac{1.96^2 \times 0.5 \times 0.5}{0.03^2}
\approx 1068
\]

Sample size phụ thuộc precision mong muốn, không phải chỉ phụ thuộc traffic lớn hay nhỏ.

### Finite population correction

Nếu lấy mẫu không hoàn lại từ population hữu hạn N, có thể điều chỉnh:

\[
n = \frac{n_0}{1+\frac{n_0-1}{N}}
\]

Với population nhỏ, correction giảm sample size cần thiết. Nếu sampling có clustering, weighting hoặc nonresponse, cần tính design effect/response adjustment thay vì áp dụng công thức đơn giản một cách máy móc.

## 12. Sample size để phát hiện lỗi hiếm

Nếu một lỗi có prevalence p và mỗi sample độc lập, xác suất không thấy lỗi trong n samples là:

\[
P(\mathrm{miss}) = (1-p)^n
\]

Muốn có xác suất phát hiện ít nhất một lỗi là c, cần:

\[
n \ge \frac{\ln(1-c)}{\ln(1-p)}
\]

### Ví dụ lỗi prevalence 0,1%

Muốn xác suất phát hiện ít nhất một lỗi đạt 95%:

\[
n \ge
\frac{\ln(0.05)}{\ln(0.999)}
\approx 2995
\]

Cần khoảng 2.995 independent samples. Nếu chỉ lấy 100 cases, xác suất phát hiện lỗi prevalence 0,1% chỉ khoảng 9,5%.

Đây là lý do random sampling nhỏ không đủ để chứng minh lỗi nghiêm trọng không tồn tại. Dùng deterministic security checks, adversarial tests, risk-based sampling và incident review cho rare events.

### Zero observed failures không có nghĩa risk bằng zero

Quy tắc gần đúng “rule of three” cho zero observed events: upper 95% bound của event rate xấp xỉ 3/n khi n đủ lớn và assumptions phù hợp. Ví dụ không thấy lỗi trong 300 samples vẫn chỉ gợi ý upper bound khoảng 1%, không chứng minh lỗi không xảy ra.

## 13. Confidence interval và cách báo kết quả

Với tỷ lệ pass, không chỉ ghi 97,4%. Báo numerator/denominator, confidence interval và sampling design.

Ví dụ: 487/500 pass = 97,4%; 95% CI cần được tính theo phương pháp phù hợp với sampling design.

Với tỷ lệ gần 0 hoặc 1, Wilson interval thường hoạt động tốt hơn Wald interval đơn giản. Với stratified/weighted/clustered sampling, confidence interval phải phản ánh thiết kế lấy mẫu; không áp dụng binomial interval thô lên weighted sample.

### Những điều phải ghi trong report

- Population và sampling frame.
- Unit và time window.
- Sample size và response/evaluation completion count.
- Selection method, inclusion probability và weights.
- Pass count/fail count.
- Confidence level và interval method.
- Strata/cohorts và sample size từng nhóm.
- Missing/unevaluable cases.

Nếu evaluator không thể chấm một case, không tự loại bỏ mà không báo. Tỷ lệ unevaluable có thể liên quan đến lỗi hệ thống và tạo bias.
## 14. Cluster sampling và các quan sát phụ thuộc nhau

Nhiều evaluation units không độc lập:

- Một conversation có nhiều turns.
- Một task có nhiều claims.
- Một user gửi nhiều requests liên tiếp.
- Một incident tạo ra nhiều lỗi cùng nguyên nhân.
- Một batch có nhiều items dùng chung model/provider conditions.

Nếu lấy 100 turns từ 5 conversations rồi coi đó là 100 observations độc lập, confidence interval có thể quá hẹp vì các turns trong cùng conversation tương quan với nhau.

### Chọn cluster phù hợp

Nếu mục tiêu là đánh giá conversation, lấy conversation làm cluster và chấm toàn bộ hoặc một tập turns bên trong. Nếu mục tiêu là task-level success, lấy task làm unit và gom các attempts của task vào cùng cluster.

### Design effect

Với cluster có kích thước trung bình m và intraclass correlation ρ, một ước lượng đơn giản:

\[
DEFF \approx 1 + (m-1)\rho
\]

Effective sample size xấp xỉ:

\[
n_{\mathrm{eff}} = \frac{n}{DEFF}
\]

Đây là xấp xỉ cho cluster design tương đối đều. Nếu cluster size rất khác nhau hoặc sampling phức tạp, dùng phương pháp survey/cluster-aware phù hợp.

### Ví dụ

Chọn 200 turns từ 20 conversations, trung bình m = 10 turns/conversation. Nếu intraclass correlation ρ = 0,2:

\[
DEFF = 1 + 9(0.2) = 2.8
\]

\[
n_{\mathrm{eff}} \approx 200/2.8 \approx 71
\]

200 turns không tương đương 200 independent observations. Khi báo confidence, cần phản ánh clustering.

## 15. Nonresponse, unevaluable cases và missing data

Không phải unit được chọn nào cũng được chấm thành công. Có thể:

- Không lưu được response/evidence.
- Trace bị drop hoặc payload đã redacted quá mức.
- Judge provider lỗi/timeout.
- Human reviewer chưa hoàn tất.
- Case không có ground truth hoặc expected evidence.
- Sampling frame bị thiếu event do telemetry outage.

Nếu chỉ tính những case dễ đánh giá, kết quả sẽ có bias.

### Theo dõi disposition của mọi sampled unit

| Disposition | Ý nghĩa |
|---|---|
| evaluated | Có kết quả evaluation hợp lệ |
| pending | Chờ evaluator/human review |
| unevaluable | Thiếu dữ liệu hoặc rubric không áp dụng |
| evaluator_error | Judge/evaluator thất bại |
| excluded_by_rule | Bị loại theo tiêu chí định trước |
| duplicate | Trùng unit đã chọn |

Giữ số lượng từng disposition trong report. Không xóa unit unevaluable khỏi denominator mà không giải thích.

### Xử lý nonresponse

- Retry evaluator theo policy có giới hạn.
- Chọn lại unit thay thế chỉ khi design cho phép và ghi lại substitution.
- Dùng response weighting nếu có mô hình nonresponse hợp lý và dữ liệu hỗ trợ.
- Báo sensitivity analysis khi tỷ lệ missing cao.
- Sửa sampling frame/telemetry nếu event bị mất có hệ thống.

Không tự động thay mọi case không chấm được bằng một case mới rồi báo sample size ban đầu; điều đó che giấu nonresponse.

## 16. Tránh selection bias và survivorship bias

Các nguồn bias thường gặp:

| Bias | Ví dụ | Cách giảm |
|---|---|---|
| Success-only bias | Chỉ sample response 200/complete | Đưa timeout/failure vào frame |
| Feedback bias | Chỉ review khi user bấm thumbs down | Có random baseline độc lập |
| Tenant bias | Traffic tenant lớn áp đảo | Stratify/weight theo tenant |
| Language bias | Chỉ sample ngôn ngữ phổ biến | Minimum sample cho từng language |
| Time bias | Chỉ sample giờ hành chính | Bao phủ time zones/peak/off-peak |
| Release bias | Chỉ sample release mới | Theo dõi cả baseline/control |
| Reviewer bias | Reviewer chỉ nhận case dễ | Random assignment và blind review |
| Label leakage | Dùng outcome để quyết định sample rồi ước lượng population | Lưu inclusion probability, tách discovery khỏi estimation |

### User feedback không phải random sample

Users có xu hướng gửi feedback khi trải nghiệm rất tốt hoặc rất tệ. Sample từ feedback hữu ích để tìm failure modes, nhưng không đại diện tỷ lệ quality toàn traffic. Báo feedback sample riêng; giữ random/stratified sample để ước lượng population.

## 17. Kết hợp deterministic evaluator, LLM judge và human review

Không cần dùng LLM judge cho mọi tiêu chí. Chọn evaluator theo loại kiểm tra:

| Evaluator | Phù hợp với | Hạn chế |
|---|---|---|
| Deterministic code | Schema, required fields, authorization flags, exact values | Không hiểu ngữ nghĩa rộng |
| Retrieval metrics | Recall@k, context precision nếu có labels | Cần expected evidence |
| LLM-as-a-judge | Relevance, groundedness, completeness, style | Có bias, variance và cost |
| Human review | Ambiguous cases, calibration, high-risk decisions | Tốn thời gian, cần rubric |
| External fact source | Claim verification với dữ liệu chuẩn | Coverage/freshness của nguồn |

### Cascade evaluation

Một pipeline tiết kiệm có thể:

1. Chạy deterministic gates cho mọi unit đủ điều kiện.
2. Chạy evaluator nhẹ trên random sample.
3. Chạy judge model trên sample hoặc case có tín hiệu rủi ro.
4. Chuyển disagreement/near-threshold/high-impact cases sang human review.
5. Ghi kết quả và cost riêng cho từng evaluator stage.

Nếu deterministic gate fail nghiêm trọng, không cần gọi thêm judge để quyết định pass/fail. Có thể vẫn gửi human review để phân tích nguyên nhân nếu cần.

## 18. Hiệu chuẩn LLM-as-a-judge bằng human labels

LLM judge có thể thay đổi theo prompt, model version và rubric. Không coi judge score là ground truth nếu chưa kiểm tra độ phù hợp.

### Calibration set

Tạo tập human-labeled đại diện, bao gồm:

- Case rõ ràng pass/fail.
- Case borderline gần threshold.
- RAG có evidence thiếu hoặc mâu thuẫn.
- Tool calls đúng/sai arguments.
- Nhiều ngôn ngữ và task types.
- Adversarial hoặc high-risk examples.

Đo:

- Agreement giữa judge và human.
- False positive/false negative.
- Precision/recall cho nhãn fail quan trọng.
- Confusion matrix theo cohort.
- Disagreement rate và adjudication rate.

Nếu judge có false negative cao trên critical violations, không dùng judge đó làm gate duy nhất.

### Sampling cho human review

Có thể phân bổ human review:

- Random subset để ước lượng agreement đại diện.
- Oversample judge-human disagreement.
- Oversample near-threshold cases.
- Oversample high-risk cohorts.
- Review định kỳ một phần cases đã được judge pass để phát hiện false negatives.

Giữ random calibration subset riêng. Nếu chỉ review disagreement, không thể ước lượng agreement toàn population một cách trực tiếp.

## 19. Sampling theo mục tiêu và độ rủi ro

Một sampling plan thực tế thường là kết hợp nhiều lane:

| Lane | Mục tiêu | Selection |
|---|---|---|
| Baseline random | Ước lượng quality population | Random sample với inclusion probability rõ |
| Cohort coverage | Theo dõi từng task/model/region | Stratified sample, minimum per stratum |
| Risk review | Phát hiện lỗi nghiêm trọng | Risk-based oversampling |
| Release watch | Kiểm tra prompt/model mới | Tăng sample trong canary window |
| Incident follow-up | Điều tra lỗi đã phát hiện | Targeted sample theo failure signature |
| Human calibration | Kiểm tra judge reliability | Random + disagreement + high-risk |

Không gộp tất cả lanes thành một sample rate duy nhất. Mỗi lane có mục tiêu và estimator khác nhau. Baseline random dùng để ước lượng population; risk/incident lane dùng để tìm lỗi và giải thích nguyên nhân.

### Ví dụ tỷ lệ lấy mẫu

Một chính sách minh họa:

- Random baseline: 1% tasks toàn traffic.
- New release: 10% cohort mới trong 2 giờ đầu.
- High-risk tool workflow: tối thiểu 200 cases/ngày hoặc census deterministic gates.
- Judge-human calibration: 5% judge results, cộng thêm toàn bộ disagreement.

Các con số là ví dụ, không phải default chung. Cần tính lại theo traffic, cost, error prevalence và mức rủi ro.

## 20. Budget cho sampling và evaluator workload

Sampling rate cần phù hợp ngân sách:

\[
B_{\mathrm{sampling}} =
N_{\mathrm{selected}} \times
\left(
C_{\mathrm{deterministic}} +
C_{\mathrm{judge}} +
C_{\mathrm{human}}
\right)
\]

Trong đó C_human có thể biểu diễn reviewer minutes × internal cost rate hoặc chỉ theo capacity giờ công, tùy mục tiêu báo cáo.

### Ví dụ

Một ngày có 100.000 tasks:

- Random baseline 1%: 1.000 tasks.
- 20% baseline cần judge, mỗi judge cost 0,002 USD: 200 × 0,002 = 0,40 USD.
- 100 risk cases được judge, cùng đơn giá: 0,20 USD.
- 50 cases human review, mỗi case trung bình 3 phút: 150 reviewer minutes.

Model evaluator cost trong ví dụ là 0,60 USD, chưa gồm deterministic compute, storage, telemetry và human labor cost. Nếu judge chạy hai lần/case, cost tăng tương ứng. Dùng pilot usage thực để lập budget, không xem số giả định là provider pricing.

### Sampling budget cap

- Max selected units per hour/day.
- Max judge calls/tokens/cost.
- Max human review minutes/capacity.
- Max payload/trace bytes.
- Max retention/storage.
- Ưu tiên baseline và high-risk lanes theo policy.

Khi budget gần cạn, không âm thầm tắt high-risk checks. Có thể giảm noncritical random sample theo policy, giữ deterministic hard gates và phát cảnh báo coverage suy giảm.

## 21. Online sampling và offline evaluation

Hai pipeline bổ trợ nhau:

| Online sampling | Offline evaluation |
|---|---|
| Lấy mẫu từ production traffic | Chạy dataset cố định |
| Phản ánh traffic mix thực tế | Có expected outcomes và reproducibility tốt hơn |
| Phát hiện drift/unknown cases | Regression test trước release |
| Có thể thiếu ground truth | Có thể xây labels/evidence |
| Bị giới hạn privacy/cost/latency | Có thể chạy judge/human review sâu |
| Kết quả phụ thuộc thời gian/provider state | Có thể pin candidate/config versions tốt hơn |

Online sample phát hiện vấn đề mới. Các failure modes được xác nhận nên được biến thành offline regression cases để tránh lặp lại.

### Feedback loop

~~~mermaid
flowchart LR
    P["Production traffic"] --> S["Sampling policy"]
    S --> E["Online evaluators"]
    E --> H["Human review / adjudication"]
    H --> F["Confirmed failure cases"]
    F --> D["Versioned evaluation dataset"]
    D --> R["Offline regression run"]
    R --> C["Prompt/model/RAG/tool changes"]
    C --> P
~~~

Dataset regression không thay thế online monitoring. Online monitoring cũng không thay thế test cố định trước release.

## 22. Sampling traces và sampling evaluation không giống nhau

Trace sampling quyết định span nào được export/lưu trong observability backend. Evaluation sampling quyết định task/request nào được đưa qua quality evaluator. Hai chính sách có thể liên quan nhưng không đồng nhất.

Ví dụ:

- Evaluation chọn task để chấm quality, nhưng trace của task có thể đã bị head-sampled và không còn.
- Tail sampling giữ trace lỗi/chậm, nhưng không có expected answer hoặc human label để tính factual correctness.
- Một trace có nhiều spans; không tính mỗi span thành một evaluation case.

### Liên kết hai loại sampling

- Khi chọn task để evaluation, ưu tiên giữ correlation ID/trace reference nếu có.
- Với high-risk/incident tasks, có thể tăng trace retention theo policy.
- Ghi rõ trace missing là missing evidence, không tự loại case khỏi sample.
- Tránh capture raw prompt/completion nếu không cần và chưa có kiểm soát privacy.

Sampling trace nên được cấu hình ở Collector/backend theo kiến trúc observability; evaluation sampling nằm ở evaluation scheduler/data pipeline.

## 23. Data contract cho sampled evaluation item

Một sampled item cần đủ metadata để tái lập selection và evaluation:

~~~yaml
sampledEvaluationItem:
  sampleId: sample-2026-11-27-000123
  samplingPolicyVersion: prod-quality-sampling-v3
  population:
    name: production-rag-tasks
    windowStart: 2026-11-27T00:00:00Z
    windowEnd: 2026-11-28T00:00:00Z
    frameCount: 100000
  selection:
    method: stratified_random
    stratum: rag
    inclusionProbability: 0.02
    weight: 50
    selectedAt: 2026-11-27T10:15:30Z
  owner:
    taskId: task-000456
    requestId: req-000789
    traceId: 4bf92f3577b34da6a3ce929d0e0e4736
  cohort:
    taskType: rag
    modelAlias: model-x
    release: prompt-12
    riskLevel: medium
  evaluation:
    status: pending
    rubricVersion: quality-rubric-v4
    evaluatorVersion: judge-pipeline-v2
~~~

Schema chỉ minh họa. Không lưu raw user text, secrets hoặc dữ liệu nhạy cảm trong selection metadata. Có thể lưu secure reference tới payload đã được redacted trong data store có phân quyền.

### Những field quan trọng

- Population window và frame count.
- Sampling policy/algorithm version.
- Method, stratum và inclusion probability.
- Selection timestamp và stable unit ID.
- Candidate/release/model/task cohort.
- Evaluator/rubric version.
- Disposition và evaluation status.
- Reference đến cost/trace/result artifacts.

## 24. Privacy, retention và data minimization

Production evaluation có thể đưa user content, retrieved documents và tool results vào judge hoặc human review. Chỉ chọn dữ liệu cần thiết:

- Redact PII/secrets trước khi lưu hoặc chuyển cho evaluator nếu không cần thiết.
- Giữ metadata và secure references thay vì duplicate toàn bộ payload.
- Tách quyền truy cập raw payload khỏi dashboard aggregate.
- Giới hạn retention theo mục tiêu điều tra và policy dữ liệu.
- Ghi audit khi reviewer mở dữ liệu nhạy cảm.
- Không gửi dữ liệu tenant này vào evaluator context của tenant khác.
- Kiểm tra provider/data processing terms trước khi gửi production content tới judge model.

Sampling rate thấp không làm mất yêu cầu privacy. Một sample duy nhất vẫn có thể chứa dữ liệu nhạy cảm.
## 25. Theo dõi quality objective theo cửa sổ thời gian

Production quality thay đổi theo traffic mix, model provider, prompt release, index version và dữ liệu nguồn. Một con số toàn tháng có thể che giấu suy giảm vừa mới xảy ra.

Thiết kế dashboard theo:

- Rolling windows: 1 giờ, 24 giờ, 7 ngày hoặc cửa sổ phù hợp traffic.
- Release windows: trước/sau khi rollout prompt/model/index.
- Cohort: RAG, tool, long-context, language, region, risk.
- Sample size và confidence interval.
- Random baseline và risk-enriched samples tách biệt.

### Không so sánh các cửa sổ có sample mix khác nhau

Giả sử hôm qua 80% traffic là simple tasks, hôm nay 50% là RAG. Quality average có thể giảm dù chất lượng trong từng cohort không đổi. Báo cohort rates và weighted estimate theo một traffic mix reference cố định khi muốn so trend.

Có thể duy trì hai view:

- **Observed mix:** chất lượng theo traffic mix thực tế của từng cửa sổ.
- **Standardized mix:** chất lượng được tính lại theo cohort weights cố định để so thay đổi chất lượng kỹ thuật.

Hai view trả lời hai câu hỏi khác nhau; cần hiển thị tên rõ ràng.

## 26. Alert khi quality objective có nguy cơ không đạt

Alert không nên chỉ dựa trên một sample nhỏ hoặc một judge result đơn lẻ. Kết hợp:

- Point estimate.
- Confidence interval hoặc uncertainty range.
- Minimum sample size.
- Consecutive windows hoặc sustained degradation.
- Critical hard-gate events.
- Cohort-specific thresholds.

### Ví dụ rule

Một policy minh họa:

- Factual correctness mục tiêu >= 98%.
- Chỉ cảnh báo trend khi có ít nhất 200 evaluated cases trong cohort/window.
- Warning nếu lower confidence bound xuống dưới 98% trong hai windows liên tiếp.
- Critical alert ngay khi deterministic hard gate phát hiện cross-tenant access violation.
- Tăng risk sampling khi retrieval failure hoặc unsupported-claim signals tăng.

Đây chỉ là ví dụ. Với lỗi nghiêm trọng, không đợi sample size hoặc hai windows nếu có deterministic evidence đáng tin.

### Tránh alert flapping

- Dùng hysteresis: ngưỡng clear alert khác ngưỡng fire alert.
- Yêu cầu sustained condition cho metric noisy.
- Gộp alert cùng nguyên nhân.
- Có cooldown cho adaptive sampling rate.
- Giữ immediate alert cho hard-gate/security events.

## 27. Adaptive sampling không được làm sai ước lượng

Giả sử baseline random sampling là 1%, nhưng khi cost spike xảy ra, hệ thống tăng sampling lên 20% cho task có cost cao. Nếu gộp tất cả selected cases rồi tính failure rate thô, task cost cao sẽ bị overrepresented.

Để tránh bias:

1. Ghi inclusion probability thực tế tại thời điểm chọn.
2. Giữ sampling policy version và trigger reason.
3. Duy trì baseline random lane độc lập.
4. Tính weighted estimate với inclusion probability phù hợp.
5. Báo risk sample riêng để điều tra.

Nếu xác suất chọn phụ thuộc vào signals liên quan đến outcome và không biết inclusion probability, không tuyên bố weighted population estimate không bias. Hãy dùng sample đó để discovery/triage.

### Adaptive sampling và feedback loop

Khi evaluator phát hiện nhiều lỗi, sampling rate có thể tăng. Khi sampling rate tăng, số lỗi quan sát được cũng có thể tăng dù population error rate không đổi. Dashboard cần tách:

- Số lượng lỗi tuyệt đối.
- Tỷ lệ lỗi có trọng số.
- Sampling rate.
- Số cases được chọn/đánh giá.
- Trigger/policy version.

Nếu chỉ nhìn số lỗi count, nhóm có thể nhầm sampling intensity tăng thành quality suy giảm.

## 28. Sampling scheduler và selection pseudocode

Một scheduler có thể áp dụng nhiều lanes theo thứ tự:

~~~text
onProductionTask(task):
  emit deterministic checks for mandatory gates

  if task matches incident or high-risk trigger:
    enqueue risk_review with reason and inclusion metadata

  if randomBaselineSelect(task.stableId, baselinePolicy):
    enqueue baseline_evaluation

  if task belongs to a cohort with coverage deficit:
    evaluate cohort quota and select by stratified policy

  if release is in canary window:
    apply release_watch policy

  before dispatch:
    check evaluator budget and queue capacity
    redact/minimize payload
    persist sample metadata and selection probability

  evaluate with configured cascade
  persist disposition, scores, cost and trace reference
~~~

Đây là pseudocode. Nếu một task được chọn bởi nhiều lanes, có thể deduplicate evaluation execution nhưng vẫn ghi mọi selection reason/inclusion logic. Không gộp risk lane vào baseline mà làm mất xác suất chọn của baseline.

### Deterministic hash selection

Một cách chọn ổn định:

~~~text
bucket = HMAC_SHA256(secretSeed, stableTaskId) mod 10000
selected = bucket < thresholdBasisPoints
~~~

Ví dụ threshold 100 tương ứng xấp xỉ 1% selection. HMAC giúp người gửi request khó dự đoán selection nếu secret seed được bảo vệ. Cần rotate/version seed theo policy và bảo đảm stableTaskId không chứa PII trực tiếp.

Hash sampling tạo selection ổn định theo ID; nếu cùng ID xuất hiện ở nhiều windows, cần thêm window key hoặc chủ ý deduplicate để kiểm soát việc chọn lặp.

## 29. Quản lý sample quota và cohort coverage

Stratified sampling cần theo dõi quota:

| Stratum | Population share | Minimum sample | Selected | Evaluated | Coverage |
|---|---:|---:|---:|---:|---:|
| Simple | 70% | 500 | 700 | 680 | 97,1% |
| RAG | 25% | 300 | 350 | 330 | 94,3% |
| Tool | 5% | 200 | 200 | 190 | 95,0% |

Số liệu bảng là ví dụ. Coverage có thể định nghĩa là evaluated/selected; cần báo thêm selected/population nếu frame count có sẵn. Không gọi evaluated/selected là population coverage.

### Quota scheduling

- Ưu tiên strata chưa đạt minimum sample.
- Giữ max cap để tránh một cohort tiêu hết evaluator budget.
- Dành một phần budget cho random baseline.
- Dành capacity riêng cho critical risk/incident reviews.
- Nếu quota không đạt vì traffic thấp, báo insufficient sample thay vì lấy dữ liệu cũ không tương thích.

Với cohort rất nhỏ, census có thể phù hợp hơn random sample. Nếu chỉ có 12 tool workflows trong ngày, đánh giá cả 12 có thể khả thi và tạo coverage rõ hơn.

## 30. Tách sampling cho release canary và continuous monitoring

Sampling khi release mới có mục tiêu khác baseline monitoring:

### Release canary

- Chọn traffic cohort được route sang candidate mới.
- Dùng randomization hoặc controlled routing để có comparison group.
- Tăng sample ở release mới trong thời gian canary.
- So quality, latency, cost và failure rates với control.
- Giữ hard gates ở mọi request có thể kiểm tra deterministic.

### Continuous monitoring

- Duy trì baseline random sample theo thời gian.
- Stratify theo task type, region, language và model.
- Tăng sample khi drift/anomaly xuất hiện.
- Human review định kỳ để hiệu chuẩn evaluator.
- Biến confirmed failure thành regression case.

Không so canary sample được oversample high-risk với baseline random sample bằng average thô. Cần cùng cohort/weights hoặc báo riêng hai sample design.

## 31. Drift detection và thay đổi sampling plan

Quality có thể drift vì:

- User intent hoặc traffic mix thay đổi.
- Prompt/model/deployment version đổi.
- Retrieval index, embedding model hoặc chunking đổi.
- Knowledge base stale hoặc source data đổi.
- Tool API/schema/permission đổi.
- Provider latency/quota/backend thay đổi.
- Judge model/rubric thay đổi.

Theo dõi cả input/data drift và outcome/quality drift. Input distribution thay đổi chưa chắc quality đã giảm; quality score thay đổi cũng có thể do evaluator drift.

### Sampling plan khi có drift

1. Phát hiện cohort/feature distribution thay đổi.
2. Giữ baseline random sample để xác định population impact.
3. Tăng sampling ở cohort bị ảnh hưởng.
4. Kiểm tra human-labeled subset để loại evaluator drift.
5. So sánh với previous release/index/rubric.
6. Khi nguyên nhân được xác nhận, cập nhật dataset và regression suite.
7. Hạ sampling rate sau khi quality ổn định theo policy.

Ghi lại trigger, start/end time, sample policy revision và lý do thay đổi. Không hồi tố thay đổi inclusion probabilities của samples đã chọn.

## 32. Bài thực hành: thiết kế production sampling cho RAG và tool calling

Giả sử hệ thống xử lý 100.000 tasks/ngày, traffic mix:

- 70% simple answer.
- 25% RAG.
- 5% tool workflows.

Quality objectives:

- Overall factual correctness >= 98%.
- RAG groundedness >= 97%.
- Tool correctness >= 99,5%.
- Không có critical authorization violation.
- Phát hiện regression sau prompt/model release trong 2 giờ.

Thực hiện:

1. Xác định task là sampling unit và lưu attempt/trace/model calls làm child records.
2. Định nghĩa population window, frame và disposition cho timeout/unevaluable.
3. Chạy deterministic authorization/schema checks cho mọi task có thể áp dụng.
4. Thiết kế random baseline để ước lượng overall quality.
5. Tạo strata simple/RAG/tool với minimum sample theo mục tiêu.
6. Oversample tool cohort và lưu inclusion probabilities/weights.
7. Tính sample size cho pass rate và rare-event detection.
8. Tạo risk lane cho retrieval confidence thấp, retries, fallback và negative feedback.
9. Tăng release-watch sampling trong canary window.
10. Dùng deterministic evaluator, LLM judge và human review theo cascade.
11. Theo dõi evaluator errors, nonresponse và missing traces.
12. Tính weighted population estimate và báo stratum rates riêng.
13. Theo dõi sampling cost, judge calls và human review capacity.
14. Tạo alert khi objective có nguy cơ không đạt hoặc hard gate fail.
15. Chuyển confirmed failures thành offline regression cases.

### Ví dụ sampling budget

Một policy minh họa:

| Lane | Số cases/ngày | Mục đích |
|---|---:|---|
| Random baseline | 1.000 | Ước lượng overall quality |
| RAG cohort | 300 | Theo dõi groundedness |
| Tool risk review | 200 | Kiểm tra tool correctness |
| Release watch | 300 | So sánh candidate mới |
| Human calibration | 100 | Đo judge agreement |

Một task có thể thuộc nhiều lane. Nếu deduplicate evaluator execution, vẫn phải lưu selection reasons và xác suất inclusion phù hợp. Không cộng các dòng như thể chắc chắn có 1.900 distinct tasks.

### Kết quả cần ghi

| Chỉ số | Giá trị cần thu |
|---|---|
| Population/frame count | Số tasks đủ điều kiện |
| Selected/evaluated | Số được chọn và số có kết quả |
| Stratum coverage | Sample size và quality từng cohort |
| Weighted quality | Ước lượng theo population mix |
| Risk findings | Số lỗi high-risk và disposition |
| Evaluator cost | Model calls/tokens/cost |
| Human capacity | Reviewer minutes và pending queue |
| Latency | Selection-to-evaluation delay |
| Bias indicators | Missing, duplicate, unevaluable, feedback-only share |

Không điền số đo giả định vào kết quả thực hành. Ghi rõ policy, frame và giới hạn của evaluator.

### Câu hỏi tự kiểm

**Câu 1:** Sample có 50% tool cases trong khi production chỉ có 5%. Có thể lấy average thô để báo overall quality không?

Không. Đây là disproportionate sample; cần population weights hoặc báo riêng từng stratum.

**Câu 2:** Chỉ lấy các request có thumbs down có đủ để ước lượng quality toàn traffic không?

Không. Feedback sample bị selection bias. Duy trì random baseline và báo feedback lane riêng.

**Câu 3:** Không thấy critical failure trong 100 random samples có chứng minh failure rate bằng zero không?

Không. Sample size chưa đủ để loại trừ lỗi hiếm; dùng hard checks, adversarial tests và risk-based review.

**Câu 4:** Sampling rate tăng từ 1% lên 20% sau alert, số lỗi count tăng gấp đôi. Có thể kết luận quality giảm gấp đôi không?

Không. Sampling intensity thay đổi. Xem weighted rate, baseline lane và policy version.

**Câu 5:** 200 turns đến từ 20 conversations có tương đương 200 observations độc lập không?

Không nhất thiết. Turns trong cùng conversation có thể tương quan; dùng cluster-aware analysis.

## 33. Checklist trước khi vận hành sampling

- [ ] Quality objectives, metric, threshold và hành động được định nghĩa.
- [ ] Population, sampling frame và sampling unit được xác định.
- [ ] Timeout, failure, cancelled và unevaluable units có disposition rõ.
- [ ] Census/risk/random/stratified/adaptive lanes được phân biệt.
- [ ] Có random baseline để ước lượng population.
- [ ] Cohort quan trọng có minimum sample hoặc census policy.
- [ ] Inclusion probability và weights được lưu khi selection không đồng đều.
- [ ] Oversampled/risk-enriched results không bị dùng như random estimate.
- [ ] Sample size phù hợp margin of error/confidence/rare-event objective.
- [ ] Clustered observations được xử lý đúng.
- [ ] Nonresponse, duplicate và missing data được báo cáo.
- [ ] LLM judge được calibration với human labels.
- [ ] Human review có random subset và high-risk/disagreement lanes.
- [ ] Sampling budget có cap cho judge, storage và reviewer capacity.
- [ ] Trace sampling và evaluation sampling được phân biệt.
- [ ] Privacy, redaction, access control và retention được áp dụng.
- [ ] Sampling policy, seed, version và trigger được audit.
- [ ] Adaptive sampling giữ baseline và weights phù hợp.
- [ ] Dashboard hiển thị quality, sample size, CI, coverage và sampling rate.
- [ ] Alert có minimum sample, hysteresis và hard-gate exceptions.
- [ ] Confirmed failures được chuyển thành offline regression cases.
- [ ] Release canary và continuous monitoring có sampling plan riêng.

### Tài liệu chính thức để triển khai

- Spring AI Observability: https://docs.spring.io/spring-ai/reference/observability/
- Micrometer Observation: https://docs.micrometer.io/micrometer/reference/observation.html
- OpenTelemetry Sampling: https://opentelemetry.io/docs/concepts/sampling/
- OpenTelemetry GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- Prometheus Histograms and Summaries: https://prometheus.io/docs/practices/histograms/

**Kết luận:** sampling có ích khi xác suất chọn, population, cohort và mục tiêu chất lượng được định nghĩa rõ. Duy trì random baseline để ước lượng production, stratify để bảo đảm coverage, risk-based sampling để tìm lỗi nghiêm trọng và human review để hiệu chuẩn judge. Ghi inclusion probability, missing data, cost và policy version giúp kết quả có thể giải thích, so sánh và audit; các failure đã xác nhận cần quay lại offline regression dataset.
