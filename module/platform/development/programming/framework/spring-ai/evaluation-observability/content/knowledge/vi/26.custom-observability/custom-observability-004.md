# Ghi nhận điểm chất lượng và trạng thái giám khảo riêng

> **Chương:** Quan sát tùy chỉnh
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ. Đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm chất lượng qua từng phiên bản prompt, model và pipeline.
>
> **Bối cảnh kỹ thuật:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. Ví dụ dùng Micrometer MeterRegistry/Observation và cần đối chiếu API với dependency BOM thực tế.

## 1. Vì sao phải ghi điểm chất lượng và trạng thái judge riêng?

Một pipeline evaluation có thể gọi LLM judge để đánh giá relevance, factuality, groundedness hoặc citation correctness. Mỗi lần đánh giá tạo ra ít nhất ba loại thông tin khác nhau:

1. **Quality score:** điểm số mà evaluator trả về cho câu trả lời hoặc một tiêu chí.
2. **Case verdict:** kết luận nghiệp vụ dựa trên score và policy, chẳng hạn PASS, FAIL hoặc INCONCLUSIVE.
3. **Judge execution status:** trạng thái thực thi của evaluator, chẳng hạn SUCCEEDED, TIMEOUT, PROVIDER_ERROR hoặc PARSE_ERROR.

Ba thông tin này không thể thay thế nhau.

Ví dụ, judge gọi model thành công, parse được JSON và chấm relevance 0,42. Với threshold 0,70, case có verdict FAIL, nhưng judge execution vẫn SUCCEEDED. Nếu ghi FAIL như một judge error, dashboard sẽ báo sai rằng evaluator đang hỏng.

Ngược lại, judge timeout và không trả score. Không được ghi score bằng 0 vì điều đó biến lỗi hạ tầng thành bằng chứng câu trả lời kém chất lượng.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Tách quality score, case verdict và judge execution status.
2. Chọn Counter, DistributionSummary, Timer và Gauge đúng mục đích.
3. Chuẩn hóa score về scale có ý nghĩa và kiểm tra range.
4. Ghi score distribution mà không tạo metric series theo từng case.
5. Ghi judge status và duration độc lập với verdict.
6. Phân biệt judge failure với answer failure.
7. Xử lý retry, missing score và duplicate evaluation.
8. Thiết kế tag vocabulary có cardinality thấp.
9. Tạo dashboard theo score, status, coverage và latency.
10. Kiểm thử custom metrics bằng SimpleMeterRegistry.
11. Tích hợp custom metrics với Spring AI built-in observations.
12. Đặt giới hạn bảo mật và retention cho evaluation telemetry.

## 2. Ba trục dữ liệu cần tách

| Dữ liệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Quality score | Chất lượng answer được chấm bao nhiêu? | relevance = 0,82 |
| Case verdict | Case có đạt policy không? | PASS |
| Judge status | Evaluator có chạy và trả kết quả hợp lệ không? | SUCCEEDED |

Một evaluation case có thể có các tổ hợp sau:

| Judge status | Score | Verdict | Ý nghĩa |
|---|---:|---|---|
| SUCCEEDED | 0,95 | PASS | Judge chạy tốt, answer đạt |
| SUCCEEDED | 0,42 | FAIL | Judge chạy tốt, answer không đạt |
| SUCCEEDED | 0,65 | INCONCLUSIVE | Có score nhưng policy không cho kết luận |
| TIMEOUT | Không có | Không có | Không thể đánh giá case |
| PARSE_ERROR | Không có | Không có | Judge trả output không parse được |
| SKIPPED | Không có | Không có | Case không thuộc phạm vi đánh giá |

Không suy ra judge status từ verdict. Cũng không suy ra verdict từ status.

## 3. Thiết kế metric schema trước khi viết code

Một schema đơn giản có thể gồm:

| Metric name | Instrument | Tags chính | Ý nghĩa |
|---|---|---|---|
| app.ai.evaluation.score | DistributionSummary | workflow, metric, evaluator | Phân phối score hợp lệ |
| app.ai.evaluation.verdicts | Counter | workflow, metric, evaluator, verdict | Số case PASS/FAIL/INCONCLUSIVE |
| app.ai.judge.executions | Counter | workflow, evaluator, status | Số lần judge theo execution status |
| app.ai.judge.duration | Timer | workflow, evaluator, status | Thời gian một judge attempt |
| app.ai.evaluation.cases | Counter | workflow, state | Số case eligible/scored/skipped |

Metric names và tags phải ổn định qua các lần deploy. Không đưa case ID, run ID, user ID hoặc raw prompt thành metric tags.

Các metric này phục vụ câu hỏi tổng hợp. Dữ liệu chi tiết theo từng case vẫn cần được lưu trong evaluation result store có thể truy vấn và audit.

## 4. Chọn đúng Micrometer instrument

| Instrument | Dùng khi | Ví dụ |
|---|---|---|
| Counter | Đếm event tích lũy | Judge timeout count |
| DistributionSummary | Ghi phân phối số đo không phải duration | Quality score 0..1 |
| Timer | Ghi duration và count | Judge evaluation duration |
| Gauge | Đo giá trị tức thời | Số evaluation jobs đang chờ |

### Vì sao score dùng DistributionSummary?

Score là một phép đo số có phân phối. Ta thường cần biết:
- có bao nhiêu score hợp lệ;
- mean score;
- tổng score;
- histogram hoặc percentile;
- tỷ lệ score nằm trong các bucket.

Counter chỉ đếm số lần, không giữ phân phối score. Timer dành cho duration. Gauge chỉ phản ánh giá trị tại thời điểm đọc và không phù hợp để lưu lịch sử từng case.

Không tạo một Gauge cho mỗi case hoặc một meter có tag case ID.

## 5. Chuẩn hóa score và hướng tốt/xấu

Evaluator có thể trả score theo nhiều thang:
- 0 đến 1;
- 1 đến 5;
- 0 đến 100;
- label ordinal như LOW/MEDIUM/HIGH.

Không trộn các thang đo trong cùng một metric series.

Nếu raw score nằm trong khoảng [min, max], có thể chuẩn hóa:

\[
s_{normalized}=\frac{s_{raw}-min}{max-min}
\]

Công thức này giả định score càng cao càng tốt. Với metric mà giá trị thấp mới tốt, cần định nghĩa transformation riêng và lưu rõ semantics. Không tự đảo chiều mọi score.

Ví dụ:
- relevance 0,82: cao hơn là tốt hơn;
- hallucination rate 0,08: thấp hơn là tốt hơn;
- latency 1,2 giây: thấp hơn là tốt hơn nhưng đây là duration, không phải quality score.

Tên metric phải nói rõ semantics. Không đặt tên chung là quality rồi trộn relevance, toxicity, latency và cost.

## 6. Phân biệt raw score, normalized score và verdict threshold

Ba bước xử lý nên được lưu rõ:

1. **Raw score:** giá trị nguyên bản từ evaluator, cùng schema/output version.
2. **Normalized score:** giá trị đã quy về scale thống nhất theo metric definition.
3. **Verdict:** kết quả áp dụng threshold/policy revision lên normalized score.

Ví dụ:

| Raw output | Normalized score | Policy | Verdict |
|---:|---:|---|---|
| 4,5 / 5 | 0,90 | threshold 0,80 | PASS |
| 3,0 / 5 | 0,60 | threshold 0,80 | FAIL |
| 4,0 / 5 | 0,80 | threshold 0,80 | PASS nếu rule là >= |

Boundary condition phải được định nghĩa rõ: dùng lớn hơn hay lớn hơn/bằng. Không thay threshold trong khi batch đang chạy mà không version hóa policy.

Nếu score normalization hoặc rubric thay đổi, hãy tạo metric/policy revision phù hợp và giữ raw evaluation result để có thể audit.

## 7. Score distribution không phải verdict count

Giả sử 1.000 case có score relevance:
- mean = 0,84;
- p50 = 0,90;
- p90 = 0,98;
- 70 case dưới threshold 0,70.

Mean score không cho biết trực tiếp số case PASS nếu threshold hoặc eligibility khác nhau. Verdict count cũng không cho biết phân phối score.

Nên ghi cả:
- score distribution;
- verdict count;
- judge execution status;
- eligible/scored counts.

Không chỉ ghi mean score. Một distribution có hai cụm 0,2 và 0,95 có thể có mean khá cao nhưng vẫn tồn tại một nhóm case thất bại lớn.

Judge confidence cũng là một đại lượng khác với answer quality. Nếu judge trả confidence về mức chắc chắn của chính phán đoán, hãy ghi bằng metric riêng như app.ai.judge.confidence và định nghĩa cách calibration; không gộp confidence vào relevance/factuality score.

## 8. Định nghĩa vocabulary cho judge execution status

Dùng enum có tập giá trị hữu hạn:

| Status | Ý nghĩa |
|---|---|
| SUCCEEDED | Judge trả output hợp lệ, parse và validate thành công |
| INVALID_OUTPUT | Output không tuân thủ schema/contract |
| PARSE_ERROR | Parser không thể đọc output |
| TIMEOUT | Vượt deadline |
| RATE_LIMITED | Provider từ chối do rate limit |
| PROVIDER_ERROR | Lỗi từ provider hoặc transport |
| CANCELLED | Execution bị hủy |
| SKIPPED | Case bị bỏ qua theo eligibility policy |

Phải thống nhất ranh giới giữa INVALID_OUTPUT và PARSE_ERROR. Ví dụ JSON parse được nhưng thiếu field score có thể là INVALID_OUTPUT; JSON syntax lỗi là PARSE_ERROR.

Không dùng exception message làm status. Message có thể thay đổi hoặc chứa dữ liệu nhạy cảm.

## 9. Định nghĩa vocabulary cho case verdict

Verdict mô tả kết quả đánh giá nội dung:

- PASS: score và policy đáp ứng yêu cầu.
- FAIL: score hoặc assertion vi phạm policy.
- INCONCLUSIVE: có kết quả nhưng chưa thể kết luận theo rubric.
- NOT_APPLICABLE: metric không áp dụng cho case theo contract.

Nếu judge execution không thành công, verdict thường là không có kết quả, không phải FAIL. Có thể lưu verdict state là NOT_EVALUATED trong result store, nhưng không cộng nó vào PASS/FAIL denominator.

Tách hai dimension này giúp dashboard phân biệt:
- answer quality đang giảm;
- evaluator đang mất khả năng đánh giá;
- dataset eligibility đang thay đổi.

## 10. Không ghi missing score thành zero

Score bằng 0 là một kết quả có nghĩa nếu evaluator thực sự chấm 0. Missing score là không có phép đo.

Các trường hợp missing:
- judge timeout;
- provider error;
- parse error;
- invalid output;
- case skipped;
- metric không áp dụng;
- pipeline bị hủy trước khi có verdict.

Nếu gán missing = 0, mean score sẽ giảm giả tạo và model bị phạt vì lỗi judge.

Cách xử lý:
- không gọi DistributionSummary.record khi score không hợp lệ hoặc không tồn tại;
- tăng judge status counter;
- tăng case state counter phù hợp;
- báo score coverage riêng;
- giữ nguyên missing reason trong evaluation result store.

## 11. Score validity và range checks

Trước khi record score, xác minh:
- giá trị không null;
- hữu hạn, không phải NaN hoặc infinity;
- nằm trong scale đã đăng ký;
- metric ID thuộc allowlist;
- evaluator output đã qua parser/schema validation;
- case đủ điều kiện cho metric;
- score không bị record lặp do retry/replay.

Ví dụ, nếu normalized score thuộc [0,1], giá trị 1,7 phải bị từ chối. Không clamp về 1,0 một cách âm thầm vì việc đó che lỗi normalization hoặc parser.

Khi score invalid:
- ghi INVALID_OUTPUT/PARSE_ERROR theo nguyên nhân;
- không record score;
- không tạo verdict PASS/FAIL;
- giữ raw output reference ở result store có access control nếu cần điều tra.

## 12. Cardinality: không tạo series theo từng case hoặc run

Các tag phù hợp thường là:

| Tag | Giá trị ví dụ | Phân loại |
|---|---|---|
| workflow | support_answer, order_lookup | Low |
| metric | relevance, groundedness, factuality | Low |
| evaluator | llm_judge, rule_based | Low nếu allowlist |
| status | succeeded, timeout, parse_error | Low |
| verdict | pass, fail, inconclusive | Low |
| environment | staging, prod | Low |

Không dùng:
- case_id;
- run_id;
- request_id;
- user_id;
- prompt text;
- document ID;
- raw model name nếu model IDs thay đổi liên tục;
- exception message.

Dataset revision, prompt revision, rubric revision và provider request ID thường phù hợp hơn với trace attributes hoặc evaluation result store. Chỉ đưa chúng vào metric tags nếu tập giá trị thực sự được giới hạn và có cardinality budget được phê duyệt.

## 13. Đo score distribution bằng DistributionSummary

Trước khi tạo meter, khai báo vocabulary đóng cho các tag. Ví dụ dưới đây dùng enum để caller không thể truyền case ID hoặc tên evaluator tùy ý vào metric labels.

~~~java
package com.example.ai.observability;

public final class EvaluationMetricTags {

    private EvaluationMetricTags() {}

    public enum Workflow {
        SUPPORT_ANSWER("support_answer"),
        ORDER_LOOKUP("order_lookup");

        private final String tagValue;
        Workflow(String tagValue) { this.tagValue = tagValue; }
        public String tagValue() { return tagValue; }
    }

    public enum Metric {
        RELEVANCE("relevance"),
        GROUNDEDNESS("groundedness"),
        FACTUALITY("factuality"),
        CITATION_CORRECTNESS("citation_correctness");

        private final String tagValue;
        Metric(String tagValue) { this.tagValue = tagValue; }
        public String tagValue() { return tagValue; }
    }

    public enum Evaluator {
        LLM_JUDGE("llm_judge"),
        RULE_BASED("rule_based");

        private final String tagValue;
        Evaluator(String tagValue) { this.tagValue = tagValue; }
        public String tagValue() { return tagValue; }
    }

    public enum JudgeStatus {
        SUCCEEDED("succeeded"),
        INVALID_OUTPUT("invalid_output"),
        PARSE_ERROR("parse_error"),
        TIMEOUT("timeout"),
        RATE_LIMITED("rate_limited"),
        PROVIDER_ERROR("provider_error"),
        CANCELLED("cancelled"),
        SKIPPED("skipped");

        private final String tagValue;
        JudgeStatus(String tagValue) { this.tagValue = tagValue; }
        public String tagValue() { return tagValue; }
    }

    public enum Verdict {
        PASS("pass"),
        FAIL("fail"),
        INCONCLUSIVE("inconclusive"),
        NOT_APPLICABLE("not_applicable");

        private final String tagValue;
        Verdict(String tagValue) { this.tagValue = tagValue; }
        public String tagValue() { return tagValue; }
    }
}
~~~

Ví dụ ghi normalized relevance score:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

public final class EvaluationScoreMetrics {

    private final MeterRegistry registry;

    public EvaluationScoreMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            EvaluationMetricTags.Workflow workflow,
            EvaluationMetricTags.Metric metric,
            EvaluationMetricTags.Evaluator evaluator,
            double normalizedScore) {

        if (workflow == null || metric == null || evaluator == null
                || !Double.isFinite(normalizedScore)
                || normalizedScore < 0.0
                || normalizedScore > 1.0) {
            throw new IllegalArgumentException(
                    "normalizedScore must be finite and within [0, 1]");
        }

        DistributionSummary.builder("app.ai.evaluation.score")
                .description("Distribution of valid normalized evaluation scores")
                .baseUnit("score")
                .tag("workflow", workflow.tagValue())
                .tag("metric", metric.tagValue())
                .tag("evaluator", evaluator.tagValue())
                .publishPercentileHistogram()
                .serviceLevelObjectives(0.50, 0.70, 0.85, 0.95)
                .register(registry)
                .record(normalizedScore);
    }
}
~~~

SLO boundaries ở đây là ví dụ để tạo histogram buckets; chúng không phải ngưỡng chấp nhận mặc định. Dùng percentile histogram khi cần tổng hợp quantiles giữa nhiều instance; percentile tính cục bộ tại process không thể cộng hoặc lấy trung bình để ra percentile fleet-wide.

Micrometer registry sẽ quản lý meter theo name và tag set. Với tập tag hữu hạn, các lần register cùng bộ tags sẽ dùng cùng meter.

## 14. Đếm case verdict bằng Counter

Verdict count là event tích lũy:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class VerdictMetrics {

    private final MeterRegistry registry;

    public VerdictMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            EvaluationMetricTags.Workflow workflow,
            EvaluationMetricTags.Metric metric,
            EvaluationMetricTags.Evaluator evaluator,
            EvaluationMetricTags.Verdict verdict) {

        if (workflow == null || metric == null
                || evaluator == null || verdict == null) {
            throw new IllegalArgumentException("Metric tags are required");
        }
        Counter.builder("app.ai.evaluation.verdicts")
                .description("Evaluation case verdict count")
                .tag("workflow", workflow.tagValue())
                .tag("metric", metric.tagValue())
                .tag("evaluator", evaluator.tagValue())
                .tag("verdict", verdict.tagValue())
                .register(registry)
                .increment();
    }
}
~~~

Chỉ gọi phương thức này khi có verdict hợp lệ. Judge timeout không được ghi thành verdict FAIL.

Với verdict INCONCLUSIVE, hãy giữ một tag value riêng. Không ép mọi kết quả thành PASS/FAIL nếu rubric có trạng thái không kết luận.

## 15. Ghi judge status và duration bằng Counter/Timer

Judge execution là một attempt độc lập. Mỗi attempt có status và elapsed duration:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;

public final class JudgeExecutionMetrics {

    private final MeterRegistry registry;

    public JudgeExecutionMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            EvaluationMetricTags.Workflow workflow,
            EvaluationMetricTags.Evaluator evaluator,
            EvaluationMetricTags.JudgeStatus status,
            Duration elapsed) {

        if (workflow == null || evaluator == null || status == null) {
            throw new IllegalArgumentException("Metric tags are required");
        }
        Counter.builder("app.ai.judge.executions")
                .description("Judge execution attempts by terminal status")
                .tag("workflow", workflow.tagValue())
                .tag("evaluator", evaluator.tagValue())
                .tag("status", status.tagValue())
                .register(registry)
                .increment();

        if (elapsed != null && !elapsed.isNegative()) {
            Timer.builder("app.ai.judge.duration")
                    .description("End-to-end duration of a judge attempt")
                    .tag("workflow", workflow.tagValue())
                    .tag("evaluator", evaluator.tagValue())
                    .tag("status", status.tagValue())
                    .publishPercentileHistogram()
                    .register(registry)
                    .record(elapsed);
        }
    }
}
~~~

Timer ở đây đo toàn bộ judge attempt theo boundary đã chọn: chuẩn bị request, gọi judge, parse và validate output. Nếu Spring AI đã tạo observation cho provider model call, hãy giữ span đó làm child; custom Timer đo judge operation end-to-end có boundary rộng hơn.

Không record duration âm. Nếu attempt bị timeout, elapsed time tới deadline vẫn có thể được record cùng status TIMEOUT.

## 16. Đếm judge attempts khác với đếm evaluation cases

Một case có thể tạo nhiều judge attempts do retry:

~~~text
case-42
  attempt-1 -> TIMEOUT
  attempt-2 -> PROVIDER_ERROR
  attempt-3 -> SUCCEEDED -> score 0.82 -> PASS
~~~

Khi đó:
- judge executions = 3;
- timeout count = 1;
- provider error count = 1;
- successful judge count = 1;
- final score count = 1;
- final verdict count = 1.

Không record score 0.82 ba lần. Score distribution đại diện cho kết quả được chấp nhận cuối cùng theo retry policy, không phải mọi attempt. Nếu muốn phân tích raw judge attempts, tạo metric riêng với semantics rõ ràng.

Metrics là bộ đếm không idempotent. Nếu message được replay, cùng một Counter có thể tăng thêm lần nữa. Cần deduplicate ở pipeline/result store trước khi phát metric event hoặc chấp nhận semantics at-least-once và ghi rõ giới hạn.

## 17. Đếm coverage và trạng thái case

Một batch evaluation nên biết:
- eligible cases;
- cases đã được judge thành công;
- cases có verdict;
- skipped cases;
- cases không có score;
- duplicate/replayed result nếu pipeline có thể phát sinh.

Có thể dùng Counter riêng:

~~~java
Counter.builder("app.ai.evaluation.cases")
        .tag("workflow", "support_answer")
        .tag("state", "eligible")
        .register(registry)
        .increment();
~~~

State phải thuộc vocabulary đóng: eligible, scored, skipped, judge_error, invalid_output hoặc inconclusive.

Không tính coverage bằng cách lấy số judge executions chia eligible cases vì retries có thể làm tử số lớn hơn mẫu số. Coverage phải dựa trên số case ID unique có kết quả hợp lệ. Metric aggregate chỉ là telemetry; evaluation result store mới là nguồn sự thật để tính coverage chính xác theo run.

## 18. Batch metrics và run-level report

Metrics backend thường tổng hợp theo thời gian, trong khi evaluation report cần kết quả theo từng run.

Ví dụ report run:

| Field | Value |
|---|---:|
| Eligible cases | 1.000 |
| Unique scored cases | 980 |
| PASS | 900 |
| FAIL | 80 |
| INCONCLUSIVE | 0 |
| Judge execution attempts | 1.030 |
| Judge succeeded attempts | 995 |
| Timeout attempts | 20 |
| Parse error attempts | 15 |
| Score coverage | 98% |

Đừng cố nhét run ID vào metric tags để tạo báo cáo theo batch. Lưu run-level aggregates và per-case outcomes trong database/object store; metrics chỉ phản ánh xu hướng tổng hợp.

## 19. Judge reliability và answer quality trên dashboard

Nên có hai nhóm dashboard riêng.

### Judge health

- judge execution count theo status;
- judge success rate;
- timeout/rate-limit/provider-error/parse-error rate;
- judge duration p50/p95;
- output schema invalid rate;
- score coverage và freshness.

### Answer quality

- score distribution theo metric;
- verdict PASS/FAIL/INCONCLUSIVE;
- score p50/p90 hoặc histogram buckets;
- quality trend theo workflow;
- eligible/scored case counts;
- regression theo dataset/report slices.

Nếu judge success rate giảm, score coverage cũng có thể giảm. Không kết luận answer quality giảm chỉ từ số case được judge thành công. Kiểm tra measurement health trước khi diễn giải quality trend.

## 20. Alerting: cảnh báo đúng loại sự cố

| Alert | Signal | Ý nghĩa |
|---|---|---|
| Judge timeout spike | TIMEOUT rate tăng | Provider/network/deadline issue |
| Judge parse error spike | PARSE_ERROR tăng | Prompt/schema/parser regression |
| Judge success rate low | SUCCEEDED / attempts giảm | Evaluation service không ổn định |
| Score coverage low | Unique scored / eligible giảm | Batch thiếu verdict |
| Quality regression | Score/verdict thay đổi trên cùng benchmark | Answer quality có thể suy giảm |
| Judge duration high | p95 judge duration vượt budget | Evaluation pipeline chậm |
| No fresh evaluation | Không có run hợp lệ trong cửa sổ kỳ vọng | Pipeline bị dừng hoặc stale |

Alert cho judge health không nên kích hoạt cùng action với quality regression. Judge outage cần khôi phục evaluator; quality regression cần điều tra model/prompt/retrieval/tool behavior.

Với batch offline, alert theo run completion/freshness thường có ý nghĩa hơn alert theo từng phút.

## 21. Kết hợp với Spring AI Observation và tracing

Spring AI có thể tạo observations cho ChatClient, ChatModel và các component được instrument. Những observations đó hữu ích để đo provider call, token usage và latency.

Custom evaluation metrics bổ sung domain semantics:
- metric đang được chấm là relevance hay groundedness;
- evaluator role là judge hay rule-based;
- output có parse/validate thành công không;
- case verdict là PASS/FAIL/INCONCLUSIVE;
- normalized score distribution.

Không tạo thêm custom span trùng boundary provider call chỉ để ghi score. Có thể:
- giữ Spring AI model observation cho lần gọi judge;
- thêm business/evaluation case observation bao toàn bộ judge operation;
- record DistributionSummary sau khi score hợp lệ;
- record status Counter cho mỗi attempt;
- lưu run/case reference trong trace hoặc result store theo policy.

## 22. Bảo vệ dữ liệu và kiểm soát metric cardinality

Không đưa các trường sau vào metric tags hoặc span attributes nếu chưa có policy cụ thể:
- raw prompt;
- expected answer;
- generated answer;
- retrieved document text;
- user/account identifiers;
- email, phone, address;
- tool arguments;
- API keys hoặc access tokens.

Dùng tags có vocabulary hữu hạn. Dùng opaque reference cho trace drilldown khi cần, và lưu dữ liệu đầy đủ trong hệ thống có access control, retention và audit.

Metric tags không phải database. Tránh các tags sau:
- run_id;
- case_id;
- request_id;
- document_id;
- prompt hash nếu mỗi request tạo một hash;
- exception message.

Dù hash đã che nội dung, mỗi hash vẫn có thể tạo một time series mới và có thể bị liên kết ngược bằng dictionary attack nếu không được thiết kế cẩn thận.

## 23. JUnit 5: kiểm tra score và judge metrics

Dùng SimpleMeterRegistry để kiểm tra metric name, tags và số đo mà không cần Prometheus server.

### File JudgeMetricsRecorderTest.java

~~~java
package com.example.ai.observability;

import static org.junit.jupiter.api.Assertions.*;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class JudgeMetricsRecorderTest {

    @Test
    void recordsScoreDistributionWithoutCaseIdTag() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        EvaluationScoreMetrics metrics = new EvaluationScoreMetrics(registry);

        metrics.record(
                EvaluationMetricTags.Workflow.SUPPORT_ANSWER,
                EvaluationMetricTags.Metric.RELEVANCE,
                EvaluationMetricTags.Evaluator.LLM_JUDGE,
                0.82);
        metrics.record(
                EvaluationMetricTags.Workflow.SUPPORT_ANSWER,
                EvaluationMetricTags.Metric.RELEVANCE,
                EvaluationMetricTags.Evaluator.LLM_JUDGE,
                0.94);

        var summary = registry.find("app.ai.evaluation.score")
                .tags("workflow", "support_answer",
                      "metric", "relevance",
                      "evaluator", "llm_judge")
                .summary();

        assertNotNull(summary);
        assertEquals(2, summary.count());
        assertEquals(1.76, summary.totalAmount(), 0.000001);
        assertFalse(summary.getId().getTags().stream()
                .anyMatch(tag -> tag.getKey().equals("case_id")));
    }

    @Test
    void rejectsOutOfRangeAndNonFiniteScores() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        EvaluationScoreMetrics metrics = new EvaluationScoreMetrics(registry);

        assertThrows(IllegalArgumentException.class,
                () -> metrics.record(
                        EvaluationMetricTags.Workflow.SUPPORT_ANSWER,
                        EvaluationMetricTags.Metric.RELEVANCE,
                        EvaluationMetricTags.Evaluator.LLM_JUDGE,
                        1.2));
        assertThrows(IllegalArgumentException.class,
                () -> metrics.record(
                        EvaluationMetricTags.Workflow.SUPPORT_ANSWER,
                        EvaluationMetricTags.Metric.RELEVANCE,
                        EvaluationMetricTags.Evaluator.LLM_JUDGE,
                        Double.NaN));

        assertNull(registry.find("app.ai.evaluation.score").summary());
    }

    @Test
    void recordsJudgeTimeoutWithoutCreatingAnAnswerVerdict() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        JudgeExecutionMetrics metrics = new JudgeExecutionMetrics(registry);

        metrics.record(
                EvaluationMetricTags.Workflow.SUPPORT_ANSWER,
                EvaluationMetricTags.Evaluator.LLM_JUDGE,
                EvaluationMetricTags.JudgeStatus.TIMEOUT,
                Duration.ofSeconds(5));

        var executions = registry.find("app.ai.judge.executions")
                .tags("workflow", "support_answer",
                      "evaluator", "llm_judge",
                      "status", "timeout")
                .counter();

        var duration = registry.find("app.ai.judge.duration")
                .tags("workflow", "support_answer",
                      "evaluator", "llm_judge",
                      "status", "timeout")
                .timer();

        assertNotNull(executions);
        assertEquals(1.0, executions.count(), 0.000001);
        assertNotNull(duration);
        assertEquals(1, duration.count());
        assertEquals(5.0, duration.totalTime(java.util.concurrent.TimeUnit.SECONDS),
                0.000001);
        assertNull(registry.find("app.ai.evaluation.verdicts").counter());
    }

    @Test
    void answerFailCanComeFromASuccessfulJudgeExecution() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        JudgeExecutionMetrics judgeMetrics = new JudgeExecutionMetrics(registry);
        VerdictMetrics verdictMetrics = new VerdictMetrics(registry);

        judgeMetrics.record(
                EvaluationMetricTags.Workflow.SUPPORT_ANSWER,
                EvaluationMetricTags.Evaluator.LLM_JUDGE,
                EvaluationMetricTags.JudgeStatus.SUCCEEDED,
                Duration.ofMillis(900));
        verdictMetrics.record(
                EvaluationMetricTags.Workflow.SUPPORT_ANSWER,
                EvaluationMetricTags.Metric.RELEVANCE,
                EvaluationMetricTags.Evaluator.LLM_JUDGE,
                EvaluationMetricTags.Verdict.FAIL);

        var judgeSuccess = registry.find("app.ai.judge.executions")
                .tags("workflow", "support_answer",
                      "evaluator", "llm_judge",
                      "status", "succeeded")
                .counter();
        var answerFail = registry.find("app.ai.evaluation.verdicts")
                .tags("workflow", "support_answer",
                      "metric", "relevance",
                      "evaluator", "llm_judge",
                      "verdict", "fail")
                .counter();

        assertEquals(1.0, judgeSuccess.count(), 0.000001);
        assertEquals(1.0, answerFail.count(), 0.000001);
        assertNull(registry.find("app.ai.judge.executions")
                .tags("workflow", "support_answer",
                      "evaluator", "llm_judge",
                      "status", "provider_error")
                .counter());
    }

    @Test
    void doesNotRecordNegativeDuration() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        JudgeExecutionMetrics metrics = new JudgeExecutionMetrics(registry);

        metrics.record(
                EvaluationMetricTags.Workflow.SUPPORT_ANSWER,
                EvaluationMetricTags.Evaluator.LLM_JUDGE,
                EvaluationMetricTags.JudgeStatus.PROVIDER_ERROR,
                Duration.ofMillis(-1));

        var executions = registry.find("app.ai.judge.executions")
                .tags("workflow", "support_answer",
                      "evaluator", "llm_judge",
                      "status", "provider_error")
                .counter();

        var duration = registry.find("app.ai.judge.duration")
                .tags("workflow", "support_answer",
                      "evaluator", "llm_judge",
                      "status", "provider_error")
                .timer();

        assertEquals(1.0, executions.count(), 0.000001);
        assertNull(duration);
    }
}
~~~

Các class recorder ở các mục trước cần nằm trong package tương ứng. Đây là ví dụ hướng dẫn, chưa được compile hoặc chạy trong phạm vi viết bài; khi đưa vào project, thêm Micrometer Core và JUnit 5 theo BOM.

## 24. Quy trình ghi metrics cho một evaluation case

~~~text
Eligible case
    |
    v
Start judge attempt
    |
    +--> Record judge duration and terminal status
    |
    v
Judge output valid?
    |
    +-- No --> Record judge status only
    |
    +-- Yes
          |
          v
      Normalize score
          |
          v
      Validate score range
          |
          +-- Invalid --> INVALID_OUTPUT / PARSE_ERROR
          |
          +-- Valid
                |
                v
            Persist unique case result
                |
                v
            Record score distribution
                |
                v
            Apply versioned threshold policy
                |
                v
            Record PASS / FAIL / INCONCLUSIVE
~~~

Trình tự này giúp phân biệt execution health với answer quality. Trong hệ thống thực tế, persist result và publish metrics có thể không nằm trong một transaction chung; cần outbox/event processing hoặc cơ chế replay có deduplication để tránh mất hoặc đếm trùng metrics.

### Ví dụ case

- Case đủ điều kiện.
- Judge attempt 1 timeout sau 5 giây.
- Retry attempt 2 thành công sau 1,2 giây.
- Output hợp lệ, relevance score = 0,82.
- Threshold revision v3 là 0,80.
- Verdict = PASS.

Metrics:
- judge executions: timeout +1, succeeded +1;
- judge duration: record 5 giây và 1,2 giây;
- score distribution: record 0,82 một lần;
- verdict count: PASS +1;
- unique scored cases: +1.

## 25. Checklist trước khi đưa score và judge metrics vào production

- [ ] Quality score, case verdict và judge status được tách riêng.
- [ ] Score scale và hướng tốt/xấu được định nghĩa.
- [ ] Raw score và normalized score không bị trộn lẫn.
- [ ] Missing score không bị ghi thành zero.
- [ ] Score được validate finite và range trước khi record.
- [ ] DistributionSummary dùng cho score distribution.
- [ ] Counter dùng cho verdict và judge status.
- [ ] Timer dùng cho judge attempt duration.
- [ ] Retry attempts không làm score distribution bị đếm trùng.
- [ ] Judge failure không bị ghi thành answer FAIL.
- [ ] INCONCLUSIVE và NOT_APPLICABLE có semantics rõ.
- [ ] Metric names/tags có schema ổn định.
- [ ] Không dùng case_id/run_id/request_id làm metric tags.
- [ ] Dataset/prompt/rubric revisions được lưu trong report hoặc trace theo policy.
- [ ] Score coverage dựa trên unique eligible cases.
- [ ] Result store là nguồn sự thật cho run-level report.
- [ ] Counter replay/delivery semantics được hiểu và xử lý.
- [ ] Judge health và answer quality có dashboard/alert riêng.
- [ ] Spring AI built-in observations không bị duplicate.
- [ ] Raw prompts, answers, documents và secrets không xuất hiện trong telemetry.
- [ ] Unit tests kiểm tra score range, tags, status và duration.
- [ ] Integration tests xác minh exporter/histogram theo BOM thực tế.

## Tài liệu tham khảo

1. [Micrometer — Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html): ghi nhận phân phối các giá trị số.
2. [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo duration, count và histogram.
3. [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): đếm event tích lũy.
4. [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): percentile histograms và SLO buckets.
5. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registry và metrics endpoint.
6. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): built-in observations và token usage.
7. [OpenTelemetry — Semantic Conventions for GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/): model operation và token usage attributes.
8. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm trong telemetry.

> **Ghi nhớ:** Score cho biết chất lượng answer; verdict cho biết case có đạt policy; judge status cho biết evaluator có chạy thành công. Hãy ghi score bằng DistributionSummary, verdict/status bằng Counter, duration bằng Timer, giữ tag vocabulary hữu hạn và không biến lỗi judge thành score 0 hoặc answer FAIL.
