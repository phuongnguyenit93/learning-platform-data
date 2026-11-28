# Điểm tổng hợp tốt nhưng một nhóm tình huống suy giảm

Dashboard có thể hiển thị PASS rate tổng thể tăng từ 88% lên 93%, trong khi các câu hỏi chính sách hoàn tiền, truy vấn tiếng Việt có nhiều điều kiện hoặc tool lookup ở trạng thái đặc biệt lại trả lời kém hơn. Nếu chỉ nhìn một con số tổng hợp, regression ở nhóm quan trọng có thể bị che khuất bởi lượng lớn case dễ đang cải thiện.

Đây là một dạng sự cố thường gặp khi đánh giá ứng dụng Spring AI: metric tổng hợp không phản ánh đồng đều mọi task type, độ khó, ngôn ngữ, nguồn tài liệu hoặc đường đi tool. Nguyên nhân có thể đến từ thay đổi phân bố dữ liệu, lỗi riêng của một pipeline, evaluator drift, coverage không đồng đều hoặc cách tổng hợp score.

Bài học thuộc chương **Chẩn đoán sự cố** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời quan sát metrics, traces, cost và latency qua các phiên bản prompt, model và pipeline.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện tình huống aggregate score tốt nhưng subgroup regression.
2. Phân biệt regression thực với thay đổi case mix, sample size hoặc evaluation coverage.
3. Phân đoạn theo task type, difficulty, locale, criterion, retrieval source và tool family.
4. Phát hiện Simpson's paradox và tính tỷ lệ chuẩn hóa theo một reference mix cố định.
5. Kiểm tra evaluator drift, rubric version và sự khác biệt giữa PASS, FAIL, INCONCLUSIVE, SKIPPED.
6. Dùng PromQL và truy vấn result store để drill down.
7. Kết hợp metrics, traces, evaluation evidence và business outcomes để tìm nguyên nhân.
8. Xác định regression có ý nghĩa nghiệp vụ, ưu tiên theo severity và sample confidence.
9. Thiết lập alert/release gate theo subgroup mà không làm cardinality tăng mất kiểm soát.
10. Đề xuất corrective action và xác minh bằng cùng dataset/cohort.

## 2. Nhận diện triệu chứng

Tình huống điển hình:

- PASS rate tổng thể tăng.
- Mean score tổng thể tăng.
- Một nhóm case có critical failures hoặc score giảm mạnh.
- Một số task type có latency/cost tăng.
- Evaluator coverage có thể khác nhau giữa các nhóm.

Ví dụ:

| Metric | Baseline | Candidate | Nhận xét |
| --- | ---: | ---: | --- |
| Overall PASS rate | 88% | 93% | Có vẻ tốt hơn |
| Policy refund PASS | 94% | 76% | Regression lớn |
| General FAQ PASS | 91% | 97% | Cải thiện |
| Order lookup PASS | 89% | 90% | Gần như ổn định |
| Evaluator coverage | 99% | 92% | Candidate thiếu kết quả hơn |
| p95 tool latency | 420 ms | 780 ms | Tool path chậm hơn |

Các số liệu chỉ minh họa. Chưa thể kết luận nguyên nhân chỉ từ bảng này. Cần kiểm tra denominator, case mix, evaluator version, coverage và evidence của từng nhóm.

### 2.1. Dấu hiệu cảnh báo

Điều tra subgroup regression khi có một trong các dấu hiệu:

- Overall PASS tăng nhưng một task type giảm vượt tolerance.
- Mean score tăng nhưng tỷ lệ score dưới critical threshold tăng.
- Critical case FAIL dù aggregate SLO vẫn đạt.
- Candidate có tỷ trọng case dễ cao hơn baseline.
- Một locale, document family hoặc tool family có error rate tăng.
- Một nhóm có evaluator timeout/skipped cao hơn các nhóm khác.
- Business success giảm dù technical success tăng.

### 2.2. Đừng dừng ở dashboard tổng

Dashboard tổng là tín hiệu phát hiện. Nó không đủ để xác định:

- Nhóm nào suy giảm.
- Regression bắt đầu từ release nào.
- Chất lượng model hay evaluator thay đổi.
- Có thiếu sample hay không.
- Tác động có ảnh hưởng đến business outcome không.

Hãy chuyển từ aggregate view sang segment view và case-level evidence.

## 3. Quy trình điều tra tổng quát

Điều tra theo thứ tự để tránh quy kết sai:

~~~mermaid
flowchart TD
    A["Aggregate score looks healthy"] --> B["Validate telemetry and denominator"]
    B --> C["Compare case mix and coverage"]
    C --> D["Slice by bounded segments"]
    D --> E["Check subgroup sample size and uncertainty"]
    E --> F["Verify dataset, rubric and evaluator versions"]
    F --> G["Inspect failed cases, traces and business evidence"]
    G --> H["Identify failing pipeline stage"]
    H --> I["Apply targeted fix"]
    I --> J["Re-run same cohort and regression suite"]
    J --> K["Release gate by aggregate + subgroup + critical cases"]
~~~

Mỗi bước cần có bằng chứng. Nếu telemetry thiếu hoặc denominator không đáng tin, dừng việc diễn giải quality score cho đến khi dữ liệu được sửa.

## 4. Bước 1 — Xác minh metric và denominator

Trước tiên xác nhận aggregate và subgroup đang được tính từ cùng định nghĩa.

### 4.1. Kiểm tra verdict taxonomy

Một evaluation result có thể có:

- PASS: criterion đạt rubric.
- FAIL: criterion không đạt.
- INCONCLUSIVE: evaluator không đủ evidence để kết luận.
- NOT_APPLICABLE: criterion không áp dụng cho case.
- SKIPPED: criterion được chọn nhưng không được thực thi/chấm.
- ERROR/TIMEOUT: evaluator attempt thất bại về kỹ thuật.

Không gộp evaluator ERROR/TIMEOUT thành quality FAIL. Không bỏ SKIPPED hoặc INCONCLUSIVE khỏi report mà không nêu coverage.

### 4.2. Định nghĩa PASS rate

Với criterion có verdict nhị phân:

\[
\text{PASS rate}
=\frac{\text{PASS}}{\text{PASS}+\text{FAIL}}
\]

Đây là tỷ lệ trên các kết quả đã có kết luận nhị phân. Nó không thể hiện số case chưa được chấm.

### 4.3. Định nghĩa evaluation coverage

Một metric coverage hữu ích:

\[
\text{Coverage}
=\frac{\text{PASS}+\text{FAIL}+\text{INCONCLUSIVE}}
{\text{Selected applicable case-criteria}}
\]

NOT_APPLICABLE cần được xử lý ở bước eligibility trước khi tạo selected applicable case-criteria. SKIPPED không được tính là evaluated. Nếu pipeline có các trạng thái khác, hãy ghi rõ chúng trong metric contract.

### 4.4. Kiểm tra numerator/denominator theo segment

Với mỗi subgroup, lưu ít nhất:

- Selected case-criteria.
- PASS.
- FAIL.
- INCONCLUSIVE.
- SKIPPED.
- Evaluator timeout/error.
- Coverage.
- PASS rate trên decided cases.

Không so PASS rate của nhóm có 20 decided cases với nhóm có 2.000 cases mà bỏ qua uncertainty.

## 5. Bước 2 — Kiểm tra case mix và Simpson's paradox

Aggregate rate là trung bình có trọng số theo số lượng case trong từng nhóm. Nếu tỷ trọng nhóm thay đổi, aggregate có thể cải thiện dù một nhóm giảm.

### 5.1. Ví dụ Simpson's paradox

Giả sử dataset có hai nhóm:

| Nhóm | Baseline PASS | Baseline total | Baseline rate | Candidate PASS | Candidate total | Candidate rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Câu hỏi phổ thông | 90 | 100 | 90% | 864 | 900 | 96% |
| Tình huống phức tạp | 80 | 100 | 80% | 60 | 100 | 60% |
| **Tổng** | **170** | **200** | **85%** | **924** | **1.000** | **92,4%** |

Aggregate tăng từ 85% lên 92,4%, nhưng nhóm phức tạp giảm từ 80% xuống 60%. Candidate có tỷ trọng câu hỏi phổ thông lớn hơn nhiều, nên nhóm dễ che mất regression.

### 5.2. So sánh trên cùng trọng số

Nếu dùng baseline mix làm reference (50% phổ thông, 50% phức tạp):

\[
\text{Baseline standardized}=0.5(90\%)+0.5(80\%)=85\%
\]

\[
\text{Candidate standardized}=0.5(96\%)+0.5(60\%)=78\%
\]

Theo cùng trọng số, candidate giảm 7 percentage points. Đây là cách trả lời câu hỏi “nếu hai release xử lý cùng một mix tình huống, kết quả sẽ thế nào?”.

### 5.3. Phân biệt ba con số

Trong report nên đặt cạnh nhau:

1. Observed aggregate rate: tỷ lệ theo phân bố traffic/dataset thực tế của từng release.
2. Segment rates: tỷ lệ riêng từng nhóm.
3. Standardized rate: tỷ lệ tổng hợp theo một reference mix cố định.

Observed aggregate phản ánh workload thực tế. Standardized rate hỗ trợ so sánh công bằng khi mix khác nhau. Không thay thế một con số cho con số còn lại.

### 5.4. Chọn reference weights

Reference mix có thể là:

- Baseline dataset đã được phê duyệt.
- Một benchmark cố định.
- Tỷ trọng task type mục tiêu của sản phẩm.
- Một phân bố chuẩn hóa do product/data owner thống nhất.

Không đổi reference weights giữa các lần report nếu muốn so trend dài hạn. Ghi version của weighting scheme trong report.

### 5.5. Không dùng unweighted average của subgroup rates tùy tiện

Trung bình đơn giản của các subgroup rate chỉ hợp lý khi muốn mỗi nhóm có trọng số bằng nhau theo chủ đích. Nếu mục tiêu là phản ánh traffic, dùng weighted average theo denominator. Nếu mục tiêu là so release trên mix cố định, dùng reference weights được công bố.

## 6. Bước 3 — Chọn segment có ý nghĩa và cardinality thấp

Phân đoạn để tìm nguyên nhân, nhưng không biến mọi thuộc tính thành metric label.

### 6.1. Các chiều phân đoạn thường hữu ích

| Dimension | Ví dụ giá trị hữu hạn | Câu hỏi điều tra |
| --- | --- | --- |
| task_type | policy, order_lookup, refund, general_chat | Pipeline nào suy giảm? |
| difficulty | simple, medium, complex | Case khó có bị ảnh hưởng? |
| locale | vi, en, other | Có regression theo ngôn ngữ? |
| criterion | relevance, groundedness, fact_check | Chất lượng nào giảm? |
| retrieval_source | policy_kb, faq_kb, none | Nguồn nào có vấn đề? |
| tool_family | order, refund, account, none | Tool path nào lỗi? |
| release_channel | stable, canary | Candidate có khác stable? |
| answer_mode | grounded, abstain, handoff | Hành vi nào thay đổi? |

Taxonomy phải được allowlist và có owner. Gộp giá trị hiếm vào `other` khi phù hợp.

### 6.2. Những dimension không nên đưa vào metric labels

Không dùng:

- case_id, run_id, trace_id.
- user_id, conversation_id, tenant ID tùy ý.
- raw query, prompt, answer hoặc document text.
- order ID, URL, citation URL.
- exception message hoặc tool arguments tự do.
- model/prompt version không giới hạn theo từng commit.

Lưu chúng trong evaluation store, warehouse hoặc trace attributes đã scrub. Metric backend chỉ giữ taxonomy hữu hạn.

### 6.3. Ước lượng cardinality trước khi thêm label

Số series tiềm năng tăng theo tích các label combinations. Ví dụ 5 task types × 3 difficulties × 3 locales × 6 criteria × 4 verdicts đã tạo 1.080 combinations cho một metric family trước khi tính instance và histogram buckets.

Chỉ thêm dimension nếu có câu hỏi vận hành rõ ràng. Có thể dùng batch analysis trong result store để điều tra chiều chi tiết hơn thay vì thêm tất cả vào Prometheus.

## 7. Bước 4 — Kiểm tra sample size và uncertainty

Một subgroup rate thấp có thể do regression hoặc do sample quá nhỏ.

### 7.1. Luôn báo số đếm cùng tỷ lệ

Ví dụ:

- Nhóm A: 19/20 PASS = 95%.
- Nhóm B: 180/200 PASS = 90%.

Chênh lệch 5 pp không đủ để kết luận nhóm A tốt hơn nếu chưa xem uncertainty. Report cần numerator, denominator và interval phù hợp.

### 7.2. Wilson confidence interval

Với tỷ lệ nhị phân, Wilson interval thường ổn định hơn normal approximation khi sample nhỏ hoặc tỷ lệ gần 0/1. Với \(\hat p=x/n\), z là quantile chuẩn và n là sample size:

\[
\text{Center}=
\frac{\hat p+\frac{z^2}{2n}}{1+\frac{z^2}{n}}
\]

\[
\text{Half-width}=
\frac{z}{1+\frac{z^2}{n}}
\sqrt{\frac{\hat p(1-\hat p)}{n}+\frac{z^2}{4n^2}}
\]

Khoảng là Center ± Half-width. Chọn confidence level và phương pháp trước khi so sánh; nếu đánh giá nhiều subgroup cùng lúc, cần cân nhắc multiple comparisons.

Nếu nhiều cases đến từ cùng một conversation/task hoặc được tạo theo cặp baseline/candidate, giả định độc lập của interval nhị thức đơn giản có thể không phù hợp. Dùng paired analysis hoặc bootstrap theo đơn vị độc lập (ví dụ task/conversation) và ghi phương pháp trong report.

### 7.3. Practical significance và statistical uncertainty

Một chênh lệch có ý nghĩa thống kê chưa chắc có ý nghĩa sản phẩm. Ngược lại, một regression lớn ở critical case không nên bị bỏ qua chỉ vì sample nhỏ.

Xác định:

- Minimum sample size cho quyết định tự động.
- Regression tolerance theo criterion.
- Critical case policy.
- Confidence interval hoặc bootstrap method.
- Khi nào kết quả là INCONCLUSIVE và cần thêm data.

### 7.4. Đừng dừng ở p-value

Báo effect size (percentage-point difference hoặc score difference), interval và số lượng case. Với dataset benchmark nhỏ, đọc từng case thay đổi thường hữu ích hơn chỉ dựa vào p-value.

## 8. Bước 5 — Xác minh evaluator và rubric

Subgroup regression có thể do evaluator thay đổi hoặc hoạt động không đồng đều.

### 8.1. Kiểm tra version lineage

So sánh baseline/candidate:

- Dataset version/checksum.
- Rubric version.
- Judge model/version.
- Judge prompt version.
- Evaluator implementation version.
- Scoring threshold.
- Sampling policy.
- Parsing/schema validation version.

Nếu đổi judge model cùng lúc với answer model, chưa thể quy kết score giảm cho ứng dụng.

### 8.2. Kiểm tra evaluator coverage theo subgroup

Evaluator có thể timeout nhiều hơn với output dài, locale nhất định hoặc tool traces lớn. Nếu chỉ tính các case có verdict, nhóm khó có thể trông tốt hơn vì các case khó bị bỏ khỏi denominator.

So sánh coverage và timeout/error rate theo cùng subgroup. Nếu coverage khác biệt lớn, đánh dấu kết quả quality là chưa đủ tin cậy.

### 8.3. Calibration sample

Lấy một tập human-labeled sample phân tầng:

- Case PASS ổn định.
- Case FAIL ổn định.
- Case vừa thay đổi verdict.
- Case critical.
- Case theo locale/difficulty/task type.

Chạy evaluator cũ và mới trên cùng sample. So agreement, false pass, false fail và inconclusive rate theo subgroup.

### 8.4. Rubric ambiguity

Nếu hai evaluator hiểu khác nhau một tiêu chí, hãy kiểm tra rubric:

- Có định nghĩa rõ evidence cần thiết không?
- Có ví dụ positive/negative không?
- Có quy tắc xử lý partial answer không?
- Có phân biệt missing evidence với contradiction không?
- Có nêu rõ khi nào abstain/handoff là hành vi đúng không?

Không sửa rubric giữa một comparison run. Tạo rubric version mới rồi chạy lại cả baseline/candidate.

## 9. Bước 6 — Phân đoạn bằng PromQL

Prometheus phù hợp với những dimension hữu hạn cần theo dõi thường xuyên. Trước khi dùng query, xác minh metric exposition có đúng label keys và meter semantics.

### 9.1. PASS rate theo task type và difficulty

Giả sử metric có các labels hữu hạn `task_type`, `difficulty` và `criterion`:

~~~promql
sum by (task_type, difficulty, criterion) (
  increase(app_ai_eval_criterion_completed_total{verdict="pass"}[1h])
)
/
sum by (task_type, difficulty, criterion) (
  increase(app_ai_eval_criterion_completed_total{verdict=~"pass|fail"}[1h])
)
~~~

Query trả tỷ lệ theo từng subgroup trong một giờ. Nếu một subgroup không có decided cases, kết quả là No Data; không tự chuyển thành 100%.

Nếu query cho 100% nhưng result store có FAIL, đây là telemetry/mapping regression. Kiểm tra raw exposition, verdict label mapping và đối chiếu Counter với committed case-criterion records; coverage cao không tự chứng minh từng verdict được export đúng.

### 9.2. Coverage theo subgroup

Giả sử runner phát Counter `app.ai.eval.criterion.selected` cho mỗi applicable case-criterion được chọn:

~~~promql
sum by (task_type, difficulty, criterion) (
  increase(app_ai_eval_criterion_completed_total{
    verdict=~"pass|fail|inconclusive"
  }[1h])
)
/
sum by (task_type, difficulty, criterion) (
  increase(app_ai_eval_criterion_selected_total[1h])
)
~~~

Coverage ở đây tính số criterion có kết quả evaluator hợp lệ chia cho số applicable criterion được chọn. SKIPPED và evaluator ERROR/TIMEOUT không nằm trong tử số; theo dõi riêng để giải thích phần thiếu.

### 9.3. Inconclusive rate

~~~promql
sum by (task_type, difficulty, criterion) (
  increase(app_ai_eval_criterion_completed_total{
    verdict="inconclusive"
  }[1h])
)
/
sum by (task_type, difficulty, criterion) (
  increase(app_ai_eval_criterion_completed_total{
    verdict=~"pass|fail|inconclusive"
  }[1h])
)
~~~

Nếu inconclusive tăng riêng ở một locale hoặc nhóm output dài, kiểm tra evaluator timeout, evidence extraction và rubric.

### 9.4. Mean score theo subgroup

~~~promql
sum by (task_type, difficulty, criterion) (
  increase(app_ai_eval_score_sum[1h])
)
/
sum by (task_type, difficulty, criterion) (
  increase(app_ai_eval_score_count[1h])
)
~~~

Chỉ ghi score hợp lệ vào DistributionSummary. Mean phải đi cùng score count, verdict rate và coverage. Không dùng mean để thay PASS rate.

### 9.5. Tool error rate theo tool family

~~~promql
sum by (tool_family, task_type) (
  rate(app_ai_tool_execution_total{outcome=~"timeout|error"}[15m])
)
/
sum by (tool_family, task_type) (
  rate(app_ai_tool_execution_total[15m])
)
~~~

Nếu tool error tăng ở refund nhưng order lookup ổn định, điều tra refund service, schema/policy hoặc permission path. Query chỉ đúng nếu meter có cả hai labels.

### 9.6. Kiểm tra số sample của từng subgroup

~~~promql
sum by (task_type, difficulty, criterion) (
  increase(app_ai_eval_criterion_completed_total{
    verdict=~"pass|fail"
  }[24h])
)
~~~

Dùng query này để hiển thị denominator. Dashboard nên đặt count bên cạnh rate và đánh dấu subgroup dưới minimum sample size.

### 9.7. Giới hạn của PromQL khi phân tích case mix

PromQL tốt cho time series và bounded labels. Standardization theo reference weights, bootstrap confidence interval, case-level diff và join nhiều version metadata thường phù hợp hơn với SQL/analytics warehouse hoặc evaluation result store.

Không thêm case ID, run ID hoặc prompt hash làm label chỉ để thực hiện một truy vấn phân tích.

## 10. Phân tích sâu trong evaluation result store

Result store giữ mỗi case-criterion result cùng lineage, vì vậy có thể phân tích dimensions chi tiết mà không tạo metric cardinality lớn.

### 10.1. Schema tối thiểu

Một bảng result có thể chứa:

| Column | Ý nghĩa |
| --- | --- |
| run_id | Evaluation run reference |
| release | stable/candidate hoặc release cohort |
| case_id | Synthetic/opaque case key |
| task_type | Nhóm tác vụ |
| difficulty | simple/medium/complex |
| locale | vi/en/other |
| criterion | relevance/groundedness/fact_check/... |
| verdict | PASS/FAIL/INCONCLUSIVE/SKIPPED |
| score | Score nếu có |
| rubric_version | Phiên bản rubric |
| evaluator_version | Phiên bản evaluator |
| dataset_version | Phiên bản dataset |
| trace_ref | Trace reference đã scrub |

Case-level identifiers ở đây phục vụ join/diagnosis trong kho có kiểm soát; không được sao chép thành metric labels.

### 10.2. Tính subgroup rate và coverage

SQL minh họa cho một bảng `evaluation_case_results`:

~~~sql
SELECT
    release,
    task_type,
    difficulty,
    criterion,
    SUM(CASE WHEN verdict = 'PASS' THEN 1 ELSE 0 END) AS pass_count,
    SUM(CASE WHEN verdict = 'FAIL' THEN 1 ELSE 0 END) AS fail_count,
    SUM(CASE WHEN verdict = 'INCONCLUSIVE' THEN 1 ELSE 0 END) AS inconclusive_count,
    SUM(CASE WHEN verdict = 'SKIPPED' THEN 1 ELSE 0 END) AS skipped_count,
    SUM(CASE WHEN verdict IN ('PASS', 'FAIL') THEN 1 ELSE 0 END) AS decided_count,
    SUM(CASE WHEN verdict IN ('PASS', 'FAIL', 'INCONCLUSIVE') THEN 1 ELSE 0 END)
        AS evaluated_count,
    1.0 * SUM(CASE WHEN verdict = 'PASS' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN verdict IN ('PASS', 'FAIL') THEN 1 ELSE 0 END), 0)
        AS pass_rate
FROM evaluation_case_results
WHERE dataset_version = 'support-eval-v3'
  AND rubric_version = 'rubric-v2'
GROUP BY release, task_type, difficulty, criterion
ORDER BY task_type, difficulty, criterion, release;
~~~

Query này giả định mỗi row là một selected applicable case-criterion đã có trạng thái cuối, kể cả SKIPPED. Nếu schema lưu evaluator attempts riêng, hãy aggregate attempts trước rồi join với final criterion result để tránh đếm một case nhiều lần.

### 10.3. Chuẩn hóa theo baseline mix

Khi candidate và baseline có case mix khác nhau, tính reference weights từ baseline rồi áp dụng cho cả hai release:

~~~sql
WITH subgroup AS (
    SELECT
        release,
        task_type,
        difficulty,
        criterion,
        SUM(CASE WHEN verdict = 'PASS' THEN 1 ELSE 0 END) AS pass_count,
        SUM(CASE WHEN verdict IN ('PASS', 'FAIL') THEN 1 ELSE 0 END) AS decided_count
    FROM evaluation_case_results
    WHERE dataset_version = 'support-eval-v3'
      AND rubric_version = 'rubric-v2'
    GROUP BY release, task_type, difficulty, criterion
),
rates AS (
    SELECT
        release,
        task_type,
        difficulty,
        criterion,
        1.0 * pass_count / NULLIF(decided_count, 0) AS pass_rate,
        decided_count
    FROM subgroup
),
reference_weights AS (
    SELECT
        task_type,
        difficulty,
        criterion,
        1.0 * decided_count
            / SUM(decided_count) OVER (PARTITION BY criterion) AS weight
    FROM subgroup
    WHERE release = 'baseline'
      AND decided_count > 0
),
release_list AS (
    SELECT 'baseline' AS release
    UNION ALL
    SELECT 'candidate' AS release
)
SELECT
    l.release,
    w.criterion,
    CASE
        WHEN COUNT(r.pass_rate) <> COUNT(w.weight) THEN NULL
        ELSE SUM(w.weight * r.pass_rate)
    END AS standardized_pass_rate,
    COUNT(r.pass_rate) AS covered_strata,
    COUNT(w.weight) AS expected_strata
FROM release_list l
CROSS JOIN reference_weights w
LEFT JOIN rates r
  ON r.release = l.release
 AND r.task_type = w.task_type
 AND r.difficulty = w.difficulty
 AND r.criterion = w.criterion
GROUP BY l.release, w.criterion;
~~~

Đây là SQL tham khảo cho database hỗ trợ window functions. Trước khi dùng kết quả:

- Xác nhận tất cả strata có mặt ở cả hai release.
- Query trả NULL nếu candidate thiếu một strata hoặc có pass_rate NULL; covered_strata/expected_strata cho biết mức độ bao phủ.
- Nếu có subgroup rate NULL hoặc decided_count bằng 0, đánh dấu standardized result là incomplete.
- Query chuẩn hóa riêng theo từng criterion. Không cộng score/pass rates của nhiều criterion nếu rubric, scale hoặc mức độ quan trọng khác nhau; nếu cần composite KPI, định nghĩa criterion weights riêng và được product owner phê duyệt.
- Candidate-only strata không nằm trong baseline reference set nên không được tính vào standardized rate; báo riêng và thống nhất reference weights mới nếu muốn đưa chúng vào so sánh.

Nếu thiếu subgroup ở candidate, report phải hiển thị coverage gap thay vì trả một standardized rate có vẻ đầy đủ.

### 10.4. Tách criterion và task-level outcome

Một task có thể có nhiều criteria. Đừng dùng số rows case-criterion làm số logical tasks. Để phân tích business success, dùng task-level table hoặc aggregate một task verdict theo rule đã định nghĩa, ví dụ tất cả criteria bắt buộc phải PASS mới là quality-qualified task.

## 11. Bước 7 — Drill down vào failed cases và traces

Sau khi biết subgroup nào giảm, chọn các case đại diện và case critical để điều tra.

### 11.1. Chọn case có chiến lược

Ưu tiên:

1. Case mới chuyển PASS → FAIL.
2. Case critical có hậu quả nghiệp vụ lớn.
3. Case có score giảm mạnh.
4. Case evaluator inconclusive/timeout.
5. Case có latency/cost outlier.
6. Case PASS ổn định làm control.

Không chỉ đọc case tệ nhất; cần cả control để phân biệt lỗi hệ thống với đặc tính riêng của input.

### 11.2. Trace timeline

Với mỗi case, xem chuỗi:

~~~text
request accepted
  -> task classified
  -> retrieval query
  -> documents ranked
  -> context assembled
  -> model generation
  -> tool selection (if applicable)
  -> tool execution
  -> final answer
  -> evaluator execution
  -> business verification
~~~

Ghi duration, status và trace/span reference cho từng bước. Xác định stage đầu tiên khác baseline.

### 11.3. Kiểm tra retrieval regression

Với RAG subgroup:

- Query normalization có thay đổi không?
- Filter metadata có loại nhầm document không?
- Embedding model/index/chunking version có đổi không?
- Top-k hoặc reranker có thay đổi không?
- Document freshness/ACL có khác không?
- Retrieved chunks có chứa fact cần thiết không?
- Context assembly có cắt mất evidence không?

Đối chiếu retrieval ground truth và trace, không chỉ đọc câu trả lời cuối.

### 11.4. Kiểm tra generation/evaluator

Nếu retrieved context đúng nhưng answer sai:

- Prompt/system instruction có thay đổi không?
- Context ordering hoặc token truncation có khác không?
- Model version/parameters/provider routing có đổi không?
- Output schema/parser có loại field không?
- Tool result có được đưa lại vào conversation đúng cách không?
- Judge rubric/prompt có thiên lệch với locale/format không?

### 11.5. Kiểm tra tool path

Với tool subgroup:

- Model chọn sai tool hay arguments sai?
- Schema có đổi required/optional fields?
- Authorization/policy decision có từ chối hợp lệ?
- Tool timeout/retry có tăng?
- Tool trả ACCEPTED/PENDING hay đã commit?
- Business verifier có dùng source of truth đúng thời điểm?

Tool HTTP success không đồng nghĩa task business success.

### 11.6. Privacy khi lưu evidence

Trace/evaluation records có thể chứa prompt, answer, arguments và retrieved content. Chỉ lưu evidence cần thiết, redact dữ liệu nhạy cảm, giới hạn retention/access và dùng opaque references. Không sao chép raw trace vào ticket hoặc report không được phân quyền.

## 12. Ma trận triệu chứng và nguyên nhân có thể

Dùng ma trận này để chọn nơi điều tra đầu tiên. Đây là giả thuyết, cần xác minh bằng evidence.

| Triệu chứng theo subgroup | Nguyên nhân có thể | Evidence cần kiểm tra |
| --- | --- | --- |
| Relevance giảm ở một locale | Query normalization, tokenizer, embedding hoặc prompt locale | Query, retrieved docs, embedding/index version |
| Groundedness giảm ở policy cases | Context thiếu fact, truncation, source document đổi | Retrieval trace, context refs, claim evidence |
| Fact-check FAIL tăng ở refund | Policy corpus stale hoặc tool/policy mapping sai | Ground truth, document version, business rule |
| Tool selection giảm ở một task type | Tool descriptions/schema overlap hoặc prompt routing đổi | Model tool proposal, schema, selection evaluator |
| Tool timeout tăng ở một family | Dependency riêng, connection pool, retry storm | Tool spans, dependency metrics, timeout logs |
| Inconclusive tăng ở output dài | Judge timeout, token limit, parser/evidence truncation | Evaluator duration, token usage, raw status |
| PASS rate tăng cùng coverage giảm | Case khó bị skip hoặc evaluator không chạy | Selected/completed/skipped counts |
| Overall rate tăng nhưng subgroup giảm | Case mix thay đổi/Simpson's paradox | Segment counts và standardized rate |
| Mean score ổn nhưng critical FAIL tăng | Mean che mất tail/critical case | Score distribution, critical-case list |
| Business success giảm nhưng quality PASS ổn | Tool/business verification, user workflow hoặc delayed outcome | Business events, source-of-truth state, task traces |

### 12.1. Xác định stage đầu tiên bị lệch

So baseline và candidate theo cùng case:

1. Input/task classification.
2. Retrieval result set/ranking.
3. Context assembly.
4. Model output/tool proposal.
5. Tool execution.
6. Final answer.
7. Evaluator verdict.
8. Business verification.

Stage đầu tiên khác nhau thường là nơi đáng điều tra nhất. Nếu mọi stage ứng dụng giống nhau nhưng verdict khác, kiểm tra evaluator/rubric trước.

### 12.2. Phân biệt correlation với root cause

Một nhóm có latency cao và PASS thấp chưa chứng minh latency làm giảm quality. Latency có thể là hậu quả của retry, output dài hoặc dependency lỗi. Cần trace timeline và thay đổi có kiểm soát để kiểm tra giả thuyết.

## 13. Ưu tiên regression theo mức độ ảnh hưởng

Không phải mọi subgroup regression đều có cùng mức độ rủi ro.

### 13.1. Ma trận severity

| Mức | Đặc điểm | Hành động |
| --- | --- | --- |
| Critical | Sai business action, lộ dữ liệu, vi phạm policy hoặc critical case FAIL | Dừng rollout/rollback và xử lý ngay |
| High | Nhóm quan trọng giảm vượt tolerance, ảnh hưởng nhiều tasks | Pause rollout, điều tra trong release window |
| Medium | Regression có giới hạn, có fallback và chưa chạm guardrail | Tạo corrective work, tăng monitoring |
| Low | Chênh lệch nhỏ, sample thấp hoặc chưa có bằng chứng | Theo dõi, thu thêm sample, không kết luận vội |

### 13.2. Xem cả impact và confidence

Ưu tiên dựa trên:

- Business impact nếu case sai.
- Tỷ lệ traffic/volume của subgroup.
- Mức regression (percentage points/score).
- Confidence interval và sample size.
- Criticality của criterion.
- Có fallback/handoff an toàn không.
- Có thể tái hiện bằng fixture không.

Một lỗi hiếm nhưng có thể tạo refund trái phép vẫn cần xử lý Critical dù subgroup sample nhỏ.

### 13.3. Không để aggregate pass bù critical failure

Định nghĩa critical case suite riêng. Một critical FAIL có thể block release dù overall PASS rate vượt target. Không dùng weighted average để che vi phạm policy hoặc business safety gate.

## 14. Chọn corrective action theo root cause

Sau khi xác định stage đầu tiên bị lệch, sửa đúng thành phần và giữ các biến khác ổn định để kiểm chứng.

| Root cause | Corrective action | Verification |
| --- | --- | --- |
| Case mix thay đổi | Báo observed + standardized rates; pin benchmark mix | Recompute trên reference weights |
| Dataset/ground truth lỗi | Review label/document, version dataset | Re-run baseline và candidate với dataset mới |
| Retrieval regression | Sửa chunking/filter/top-k/reranker/index | Recall@k, MRR, context relevance |
| Locale regression | Chuẩn hóa query, kiểm tra language-specific retrieval/prompt | Golden cases theo locale |
| Prompt regression | Sửa instruction, evidence ordering, abstention rule | Same dataset + critical cases |
| Model/provider change | Pin version, canary, so output/usage | Stratified quality, latency, cost |
| Tool selection/schema | Sửa tool description/schema/policy routing | Tool selection/argument tests |
| Dependency/tool latency | Sửa pool/timeout/retry/circuit breaker | Tool p95/error và business success |
| Evaluator drift | Calibrate judge, sửa rubric/evaluator | Human-labeled agreement set |
| Evaluator coverage thấp | Sửa queue/concurrency/quota/timeout | Coverage và evaluator error rate |
| Business verification sai | Sửa source-of-truth contract/idempotency | Business event integration test |

### 14.1. Tránh sửa nhiều biến cùng lúc

Nếu vừa đổi prompt, model, retriever và rubric, kết quả sau sửa không cho biết thay đổi nào có ích. Tách thành các thí nghiệm nhỏ hoặc ghi rõ nhiều biến đã đổi và giới hạn attribution.

### 14.2. Giữ regression fixture

Mọi case đã phát hiện regression nên được thêm vào regression suite sau khi:

- Ground truth được review.
- Không chứa customer data.
- Có expected behavior rõ.
- Có criterion/rubric version.
- Có owner cập nhật khi policy thay đổi.

Không thêm một case sai ground truth vào suite chỉ để khóa output hiện tại.

## 15. Alert và release gate theo subgroup

Alert subgroup hữu ích khi taxonomy ổn định, có volume đủ và owner xử lý rõ.

### 15.1. Tạo recording rules

Ví dụ:

~~~yaml
groups:
  - name: spring-ai-subgroup-quality
    interval: 5m
    rules:
      - record: app_ai_eval:pass_rate_6h
        expr: |
          sum by (task_type, difficulty, criterion) (
            increase(app_ai_eval_criterion_completed_total{verdict="pass"}[6h])
          )
          /
          sum by (task_type, difficulty, criterion) (
            increase(app_ai_eval_criterion_completed_total{verdict=~"pass|fail"}[6h])
          )
      - record: app_ai_eval:decided_cases_6h
        expr: |
          sum by (task_type, difficulty, criterion) (
            increase(app_ai_eval_criterion_completed_total{verdict=~"pass|fail"}[6h])
          )
~~~

Rule cần được kiểm tra bằng promtool và scrape fixture. Tên labels phải khớp metric exposition.

### 15.2. Alert khi subgroup giảm so với baseline

Giả sử baseline được publish thành Gauge có cùng label dimensions:

~~~promql
app_ai_eval:pass_rate_6h
  < on (task_type, difficulty, criterion)
  (app_ai_eval:baseline_pass_rate - 0.05)
and on (task_type, difficulty, criterion)
  app_ai_eval:decided_cases_6h >= 30
~~~

Điều kiện minh họa: PASS rate thấp hơn baseline ít nhất 5 percentage points và có tối thiểu 30 decided case-criteria. Chọn ngưỡng theo rủi ro, baseline maturity và sample size; không coi 30 là chuẩn chung.

Baseline Gauge phải được tạo từ một run đã được duyệt, có cùng rubric/evaluator contract và reference cohort. Khi baseline version thay đổi, cập nhật Gauge có kiểm soát và ghi lại version trong release report.

### 15.3. Alert coverage riêng

Tạo alert khi coverage theo subgroup giảm dưới threshold hoặc evaluator error tăng. Nếu PASS rate tăng nhưng coverage giảm, ưu tiên cảnh báo evaluator/coverage thay vì gửi quality-improved notification.

### 15.4. Offline evaluation nên dùng release gate

Với dataset batch, chạy gate sau khi tất cả selected cases có trạng thái cuối:

- Overall thresholds.
- Subgroup thresholds.
- Critical case assertions.
- Minimum sample/coverage.
- Evaluator availability.
- Cost/latency guardrails.

Không dùng rate alert ngắn để kết luận batch chạy một lần mỗi ngày.

### 15.5. Hạn chế alert noise

- Chỉ alert subgroup có owner và hành động cụ thể.
- Dùng minimum sample size và duration/batch consistency.
- Gộp các dimension hiếm thành other.
- Không alert trên mọi case ID.
- Có suppression khi evaluator coverage thấp hoặc dataset chưa mature.
- Đưa link tới report/trace search thay vì nhúng raw content vào alert.

## 16. Ví dụ điều tra end-to-end

Một candidate prompt được triển khai để cải thiện trợ lý chính sách. Dashboard tổng cho thấy PASS rate tăng, nhưng phản hồi từ nhóm hỗ trợ cho biết câu hỏi hoàn tiền phức tạp thường thiếu điều kiện.

### 16.1. Quan sát ban đầu

| Chỉ số | Baseline | Candidate |
| --- | ---: | ---: |
| Overall PASS | 85% (170/200) | 92,4% (924/1.000) |
| General/simple | 90% (90/100) | 96% (864/900) |
| Complex/refund | 80% (80/100) | 60% (60/100) |
| Complex coverage | 100% | 100% |
| Judge error rate | 1% | 1% |

Coverage và evaluator availability của nhóm phức tạp ổn định, nên thiếu evaluator không giải thích được regression. Case mix candidate nghiêng mạnh về nhóm phổ thông.

### 16.2. Chuẩn hóa mix

Dùng baseline weights 50/50:

- Baseline standardized PASS = 85%.
- Candidate standardized PASS = 78%.

Aggregate observed tăng 7,4 pp nhưng standardized giảm 7 pp. Candidate chưa thể được coi là cải thiện đồng đều.

### 16.3. Drill down

Chọn 10 case refund chuyển PASS → FAIL và 5 case PASS ổn định. Trace cho thấy:

- Retrieval vẫn trả đúng policy document.
- Context chứa điều kiện thời hạn và loại giao dịch.
- Candidate prompt ưu tiên trả lời ngắn và thường bỏ qua ngoại lệ.
- Fact checker phát hiện claim thiếu điều kiện.

Giả thuyết root cause là prompt instruction về tóm tắt làm mất các điều kiện bắt buộc ở câu trả lời refund.

### 16.4. Sửa và xác minh

1. Thêm rule yêu cầu nêu đủ điều kiện/ngoại lệ từ evidence.
2. Giữ model, retriever, dataset và rubric cố định.
3. Chạy lại toàn bộ dataset và critical refund cases.
4. Kiểm tra subgroup rate, score distribution và groundedness.
5. Xác minh latency/cost không vượt guardrail.
6. Chỉ mở rollout khi aggregate, subgroup và critical cases cùng đạt.

Ví dụ này minh họa cách tìm nguyên nhân; số liệu và trace behavior không đại diện cho một hệ thống cụ thể.

## 17. Checklist đóng sự cố

### 17.1. Data integrity

- [ ] Dataset version/checksum giống baseline hoặc thay đổi đã được công bố.
- [ ] Rubric/evaluator version được ghi.
- [ ] PASS/FAIL/INCONCLUSIVE/SKIPPED được phân biệt.
- [ ] Numerator, denominator và coverage được lưu.
- [ ] Case mix được so sánh.
- [ ] Reference weights có version.

### 17.2. Diagnosis

- [ ] Subgroup regression được xác định.
- [ ] Sample size/uncertainty được đánh giá.
- [ ] Evaluator calibration được kiểm tra.
- [ ] Case-level diffs được xem.
- [ ] Trace xác định stage đầu tiên lệch.
- [ ] Business source of truth được kiểm tra nếu có task outcome.

### 17.3. Remediation

- [ ] Root cause có evidence.
- [ ] Corrective action chỉ thay biến cần thiết.
- [ ] Regression fixture được thêm sau review.
- [ ] Cùng dataset/cohort được chạy lại.
- [ ] Aggregate + subgroup + critical gates đạt.
- [ ] Cost/latency/safety guardrails không bị vi phạm.

### 17.4. Incident report

Report đóng sự cố cần ghi:

- Symptom và thời điểm bắt đầu.
- Affected task types/criteria/locales.
- Observed và standardized rates.
- Coverage, sample sizes và uncertainty.
- Root cause và evidence references.
- Corrective change và versions.
- Re-run result.
- Release decision và follow-up owner.

## 18. Bài thực hành

**Bối cảnh:** một release mới có PASS rate tổng tăng từ 89% lên 94%. Khi phân đoạn, nhóm RAG tiếng Việt phức tạp giảm từ 91% xuống 68%, trong khi general chat tăng từ 90% lên 98%. Evaluator timeout tăng riêng ở RAG tiếng Việt; retrieval p95 tăng 40%.

### Phần A — Xác minh số liệu

1. Tính coverage theo từng subgroup.
2. Kiểm tra PASS/FAIL/INCONCLUSIVE/SKIPPED counts.
3. So sánh case mix baseline/candidate.
4. Tính standardized rate theo baseline weights.
5. Đánh giá sample size và uncertainty.

### Phần B — Tìm root cause

1. Kiểm tra evaluator timeout theo locale/difficulty.
2. Kiểm tra retrieval query, document recall và index version.
3. Xem trace của case PASS → FAIL và control cases.
4. Xác định retrieval latency tăng là nguyên nhân hay hệ quả.
5. Kiểm tra judge prompt/rubric có thay đổi không.

### Phần C — Đề xuất hành động

1. Chọn corrective action có thể kiểm chứng.
2. Định nghĩa subgroup release gate.
3. Xác định critical cases cần block release.
4. Chọn metric/alert theo dõi sau rollout.
5. Viết tiêu chí re-run và rollback.

### Câu hỏi tự kiểm tra

- Vì sao aggregate PASS rate có thể tăng khi subgroup giảm?
- Simpson's paradox xảy ra khi case mix thay đổi thế nào?
- Khi nào dùng observed rate và khi nào dùng standardized rate?
- Vì sao không nên dùng unweighted average của mọi subgroup?
- Tại sao coverage phải được phân đoạn giống PASS rate?
- Khi nào sample nhỏ vẫn phải block release?
- Vì sao evaluator version cần được cố định trong comparison?
- Những dimension nào phù hợp làm metric labels?
- Khi nào nên chuyển từ PromQL sang result store/SQL?
- Trace giúp tìm stage đầu tiên bị lệch như thế nào?
- Vì sao critical failure không được bù bằng aggregate score?
- Điều kiện nào cần đạt trước khi mở lại rollout?

## 19. Những điều cần ghi nhớ

1. **Aggregate tốt không chứng minh mọi nhóm đều tốt.** Luôn phân đoạn theo task type, difficulty, locale và criterion phù hợp.
2. **Case mix có thể đảo ngược kết luận.** Đặt observed rate, subgroup rate và standardized rate cạnh nhau.
3. **Denominator và coverage là bắt buộc.** PASS rate cao với coverage thấp có thể là false green.
4. **Không gộp evaluator error với quality FAIL.** Theo dõi evaluator availability riêng.
5. **Báo count và uncertainty.** Tỷ lệ không có numerator/denominator dễ gây hiểu nhầm.
6. **Giữ taxonomy labels hữu hạn.** Case/run/user/trace IDs thuộc result store hoặc trace.
7. **Dùng PromQL cho trend và SQL/result store cho phân tích chi tiết.** Không tăng cardinality để thay thế analytics.
8. **Drill down theo trace và evidence.** Tìm stage đầu tiên khác baseline thay vì đoán từ correlation.
9. **Critical cases có gate riêng.** Aggregate không được bù cho lỗi an toàn/nghiệp vụ nghiêm trọng.
10. **Sửa đúng nguyên nhân và chạy lại cùng cohort.** Giữ các biến không liên quan cố định.
11. **Alert subgroup cần sample size, owner và hành động.** Tránh noise từ nhóm hiếm.
12. **Release decision phải dựa trên aggregate, subgroup, coverage và guardrails.**

## Tài liệu tham khảo

- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): alert theo tín hiệu và độ tin cậy dịch vụ.
- [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/): vector matching và selectors.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): rate, increase và histogram functions.
- [Prometheus — Instrumentation Practices](https://prometheus.io/docs/practices/instrumentation/): metric design và cardinality.
- [Micrometer Reference — Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html): score distributions.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): latency measurements.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): traces cho ChatClient, model và tool.
- [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/): trace/span context và attributes.
- [NIST/SEMATECH e-Handbook — Confidence Intervals for Proportions](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm): khoảng tin cậy cho tỷ lệ.

**Lưu ý:** các ngưỡng, metric names và query trong bài là ví dụ cần điều chỉnh theo rubric, taxonomy, registry và phiên bản thực tế. Không kết luận regression khi chưa xác minh data completeness, evaluator lineage và business impact.
