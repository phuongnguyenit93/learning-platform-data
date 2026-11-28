# Đăng ký metric chất lượng bằng instrumentation riêng khi cần

Spring AI và hệ sinh thái Micrometer giúp quan sát hoạt động của model, ChatClient, tool và các thành phần dữ liệu. Những tín hiệu như số request, độ trễ, token usage và lỗi kỹ thuật cho biết pipeline đang vận hành ra sao. Nhưng một request hoàn tất thành công về mặt kỹ thuật chưa chắc đã trả lời đúng câu hỏi, truy xuất đúng nguồn hoặc gọi đúng tool. Để đo các thuộc tính đó, ứng dụng thường cần **custom quality instrumentation** gắn với kết quả đánh giá của chính sản phẩm.

Custom instrumentation phải bắt đầu từ hợp đồng đo lường rõ ràng: metric đang đếm đơn vị nào, ai tạo verdict, score có miền giá trị nào, trạng thái nào không được tính là kết quả, và dữ liệu được tổng hợp theo nhóm nào. Nếu không xác định các điểm này, một dashboard có thể báo relevance cao dù nhiều ca chưa được chấm, hoặc báo tool accuracy thấp chỉ vì evaluator timeout.

Bài học thuộc chương **Thiết kế metric** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định khi nào metric vận hành có sẵn chưa đủ và cần instrumentation chất lượng riêng.
2. Phân biệt technical success, task success, quality verdict và evaluator execution outcome.
3. Thiết kế metric contract cho relevance, groundedness, fact checking, retrieval và tool correctness.
4. Chọn Counter, DistributionSummary, Timer hoặc Gauge theo đúng ngữ nghĩa.
5. Đăng ký custom meter bằng Micrometer trong ứng dụng Spring Boot.
6. Gắn custom Observation vào một bước evaluation mà không đưa ID hoặc nội dung nhạy cảm vào metric labels.
7. Tích hợp metric với online evaluator, offline evaluation runner và kết quả kiểm thử hồi quy.
8. Viết PromQL để tính pass rate, mean score, inconclusive rate, evaluator error và latency.
9. Kiểm thử metric bằng SimpleMeterRegistry và kiểm tra contract của dữ liệu.
10. Tránh double counting, cardinality cao và false quality regression.

## 2. Vì sao cần quality instrumentation riêng?

Metric vận hành trả lời những câu hỏi như:

- Model request có hoàn tất không?
- Provider có trả 429 hoặc timeout không?
- Tool handler mất bao lâu?
- Có bao nhiêu token được sử dụng?
- Retrieval dependency có đang lỗi không?

Metric chất lượng trả lời những câu hỏi khác:

- Câu trả lời có liên quan đến yêu cầu không?
- Các claim có được nguồn truy xuất hỗ trợ không?
- Câu trả lời có mâu thuẫn với facts đã biết không?
- Retriever có tìm thấy tài liệu liên quan trong top-k không?
- Model có chọn đúng tool và truyền tham số đúng không?
- Tác vụ nghiệp vụ đã đạt hậu điều kiện chưa?

Một request có thể trả HTTP 200, model call thành công, latency thấp nhưng nội dung sai. Nếu chỉ xem technical metrics, dashboard vẫn xanh.

### 2.1. Ví dụ

Người dùng hỏi trạng thái đơn hàng. Model gọi tool thành công, tool trả về đơn hàng ở trạng thái DELIVERED, model trả lời “Đơn hàng đang được giao”.

| Tầng | Kết quả |
| --- | --- |
| HTTP request | Success |
| Model call | Success |
| Tool execution | Success |
| Business source of truth | Đơn hàng đã giao |
| Fact checking | Fail: câu trả lời mâu thuẫn |
| Task quality | Fail |

Đây là lý do cần metric cho **verified quality outcome**, bên cạnh metric kỹ thuật.

### 2.2. Khi nào không cần custom metric?

Không tạo metric mới chỉ vì có thể tạo. Trước tiên kiểm tra metric/observation hiện có trong phiên bản Spring AI, Spring Boot và Micrometer đang dùng. Nếu metric có sẵn đã biểu diễn đúng đơn vị và semantics cần thiết, hãy tái sử dụng.

Custom metric phù hợp khi:

- Cần một verdict theo rubric riêng của sản phẩm.
- Cần đo kết quả fact checking hoặc relevance.
- Cần phân biệt tool proposed, dispatched, executed và business verified.
- Cần đo coverage của dataset/evaluation run.
- Cần metric theo outcome mà instrumentation mặc định không cung cấp.

Không nhân đôi một metric có sẵn với tên khác nhưng cùng nghĩa. Hai nguồn đếm cùng một event có thể khiến dashboard cộng đôi hoặc tạo hai con số không thể đối chiếu.

## 3. Phân biệt các loại kết quả

Trước khi tạo meter, định nghĩa những kết quả có thể xảy ra. Không dùng một boolean success cho tất cả tầng.

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Technical outcome | Thành phần có thực thi thành công không? | Provider trả response hợp lệ |
| Task outcome | Người dùng có hoàn thành tác vụ theo contract không? | Tìm được trạng thái đơn hàng |
| Quality verdict | Kết quả có đạt rubric không? | Groundedness PASS |
| Evaluator outcome | Evaluator có chạy và trả kết luận không? | Judge timeout |
| Business outcome | Hậu điều kiện nghiệp vụ có được xác minh không? | Refund đã hoàn tất |

Một model attempt thành công không đồng nghĩa task thành công. Tool trả HTTP 200 không đồng nghĩa nghiệp vụ hoàn tất. Evaluator timeout không đồng nghĩa chất lượng FAIL.

### 3.1. Taxonomy verdict

Một tập verdict tối thiểu:

- pass: evaluator đã chấm và kết quả đạt ngưỡng.
- fail: evaluator đã chấm và kết quả không đạt.
- inconclusive: có chạy đánh giá nhưng không đủ evidence hoặc không thể kết luận.
- not_applicable: tiêu chí không áp dụng cho case.
- skipped: case bị bỏ qua theo policy.

Không đưa tất cả trạng thái vào một pass/fail counter. not_applicable và skipped không phải quality failures; inconclusive không phải PASS.

### 3.2. Evaluator execution outcome

Đo riêng trạng thái thực thi evaluator:

- success: evaluator trả kết quả có cấu trúc.
- timeout: hết deadline.
- error: exception, provider failure hoặc output không hợp lệ.
- cancelled: run bị hủy theo yêu cầu.

Ví dụ evaluator có thể thực thi thành công nhưng trả verdict inconclusive. Đây là một lần evaluator execution thành công, nhưng case không có quality conclusion. Hai dimension trả lời hai câu hỏi khác nhau.

## 4. Chọn đơn vị đo trước khi chọn metric type

Quality metric thường thất bại vì trộn lẫn các đơn vị:

- Logical task.
- Model turn.
- Tool call.
- Retrieval query.
- Evaluation case.
- Claim được fact-check.
- Một tiêu chí trên một case.
- Một evaluation run.

Ví dụ một câu trả lời có 5 claims, evaluator chấm 5 claims. Nếu đếm 5 verdicts như 5 completed tasks, task count bị phóng đại.

### 4.1. Định nghĩa event contract

Một event evaluation nên xác định:

| Trường | Ý nghĩa | Dùng cho metric? |
| --- | --- | --- |
| case_type | Nhóm case hữu hạn | Có |
| criterion | Nhóm tiêu chí hữu hạn như relevance/groundedness | Có |
| verdict | pass/fail/inconclusive/not_applicable/skipped | Có |
| score | Giá trị score theo rubric | Sample trong distribution |
| evaluator_outcome | success/timeout/error/cancelled | Có |
| run_id | ID duy nhất của run | Trace/store |
| case_id | ID duy nhất của case | Evaluation store |
| claim_id | ID claim riêng | Evaluation store |
| rubric_version | Phiên bản rubric | Metadata; chỉ làm tag khi tập version hữu hạn |
| evidence | Source spans/doc references | Evaluation store/trace |

Metric contract phải ghi rõ **mỗi event được ghi đúng một lần ở thời điểm nào**. Retry evaluator không được vô tình đếm một case hoàn tất nhiều lần.

### 4.2. Một case có nhiều criteria

Nếu một case được chấm relevance, groundedness và factual correctness, hãy xác định:

- Mỗi criterion có một verdict riêng.
- Một case có thể PASS relevance nhưng FAIL factual correctness.
- Overall case verdict được tính theo rubric đã công bố.
- Case completion chỉ tăng một lần khi evaluation run chốt trạng thái.

Không lấy trung bình các verdict enum như thể chúng là số liên tục. Nếu cần score tổng hợp, định nghĩa công thức và trọng số rõ ràng.

## 5. Chọn metric type phù hợp

Micrometer cung cấp các meter phổ biến. Hãy chọn theo semantics của dữ liệu.

| Meter | Dùng khi | Ví dụ |
| --- | --- | --- |
| Counter | Đếm event tích lũy | Evaluation cases completed, quality FAIL |
| DistributionSummary | Phân bố giá trị số không phải thời gian | Relevance score, groundedness score, retrieved document count |
| Timer | Đo thời gian thực thi | Evaluator latency, evaluation case duration |
| Gauge | Trạng thái tức thời | Evaluation runs in-flight, queue depth |

### 5.1. Counter cho verdict

Counter phù hợp với số lần case được chốt verdict:

~~~text
app.ai.eval.criterion.completed{case_type="rag",verdict="pass"}
app.ai.eval.criterion.completed{case_type="rag",verdict="fail"}
app.ai.eval.criterion.completed{case_type="rag",verdict="inconclusive"}
~~~

Counter criterion.completed tăng một lần cho mỗi kết quả cuối của một case-criterion theo contract. Nếu cần đếm overall case completion, dùng meter riêng và chỉ tăng khi tất cả criteria bắt buộc đã chốt. Không increment lại khi dashboard query hoặc khi report được đọc.

### 5.2. DistributionSummary cho score

Score relevance từ 0 đến 1 là một phân bố số. DistributionSummary giữ count, total và có thể cấu hình histogram. Nó cho phép tính mean và phân bố theo nhóm.

Không chỉ lưu mean nếu tail distribution quan trọng. Hai phiên bản có mean 0,85 nhưng một phiên bản có nhiều score gần 0 hơn vẫn có thể có rủi ro chất lượng khác.

### 5.3. Timer cho evaluator latency

Timer đo thời gian chạy judge/evaluator. Ghi cả thành công, timeout và error với outcome tag riêng để p95 không chỉ đại diện cho các ca thành công nhanh.

Nếu evaluator chạy bất đồng bộ, timer phải bao trùm toàn bộ khoảng thời gian theo contract: từ lúc nhận case đến khi có verdict cuối hoặc trạng thái lỗi cuối.

### 5.4. Gauge cho backlog

Gauge phù hợp cho số evaluation runs đang chạy hoặc queue depth tại thời điểm scrape. Không dùng Gauge để đếm tổng case đã chấm; đó là Counter.

## 6. Thiết kế metric catalog cho chất lượng Spring AI

Một metric catalog nhỏ, có contract rõ ràng sẽ dễ duy trì hơn hàng chục metric trùng nghĩa.

| Metric logic | Type | Labels hữu hạn | Ý nghĩa |
| --- | --- | --- | --- |
| app.ai.eval.criterion.completed | Counter | case_type, criterion, verdict | Kết quả cuối của một case-criterion |
| app.ai.eval.score | DistributionSummary | case_type, criterion | Phân bố score hợp lệ |
| app.ai.eval.execution | Counter | evaluator, outcome | Kết quả thực thi evaluator |
| app.ai.eval.duration | Timer | evaluator, outcome | Thời gian evaluation |
| app.ai.eval.claim.checked | Counter | claim_type, verdict | Claim đã được kiểm tra |
| app.ai.rag.retrieval.relevant | Counter | case_type | Số relevant documents tìm được trong fixture có nhãn |
| app.ai.tool.selection | Counter | tool_family, selection_outcome | Kết quả đánh giá tool selection |
| app.ai.eval.run.inflight | Gauge | Không hoặc run_type hữu hạn | Run đang thực thi |

Tên trên là **custom metric do ứng dụng định nghĩa**, không khẳng định Spring AI tự export sẵn các meter này.

### 6.1. Không bắt đầu bằng một metric quality score tổng hợp

Một score tổng hợp duy nhất dễ che giấu nguyên nhân:

- Relevance cao nhưng factual correctness thấp.
- Groundedness cao nhưng tool selection sai.
- Retrieval recall tốt nhưng answer synthesis kém.
- PASS rate cao nhưng coverage thấp.

Hãy đo các criteria riêng trước. Nếu sản phẩm cần một overall score, định nghĩa nó ở evaluation report với rubric/version rõ ràng, sau đó mới cân nhắc metric tổng hợp.

### 6.2. Chọn labels có giá trị vận hành

Labels thường có ích:

- case_type: rag, tool, multi_turn, no_tool, other.
- criterion: relevance, groundedness, fact_check, tool_selection, other.
- verdict: pass, fail, inconclusive, not_applicable, skipped.
- evaluator: rule_based, model_judge, human, other.
- evaluator_outcome: success, timeout, error, cancelled.

Chỉ thêm dimension nếu có câu hỏi dashboard/alert cụ thể. Không dùng raw prompt, case ID, run ID, user ID, document ID hoặc exception message làm metric labels.

## 7. Định nghĩa score và ngưỡng trước khi ghi metric

Score chỉ có ý nghĩa khi biết rubric, miền giá trị và cách diễn giải.

Ví dụ relevance score:

- Miền score: 0.0 đến 1.0.
- 0.0: câu trả lời không liên quan theo rubric.
- 0.5: có liên quan một phần nhưng thiếu khía cạnh quan trọng.
- 1.0: đáp ứng đầy đủ yêu cầu liên quan.

Các mức này chỉ là ví dụ. Rubric thật phải mô tả tiêu chí và ví dụ chấm điểm để người đánh giá, rule-based evaluator và model judge áp dụng nhất quán.

### 7.1. Score và verdict không nhất thiết tương đương

Ví dụ này giả định rubric chuẩn hóa score đến hai chữ số thập phân và dùng ngưỡng:

| Score | Verdict |
| --- | --- |
| 0.80–1.00 | PASS |
| 0.00–0.79 | FAIL |
| Không đủ evidence | INCONCLUSIVE |

Không tự chuyển INCONCLUSIVE thành score 0. Cũng không mặc định score 0 luôn là FAIL nếu rubric cho phép score chưa được tính hoặc tiêu chí không áp dụng. Với criterion chỉ có verdict, score có thể null; với criterion có score, caller phải đảm bảo verdict phù hợp với ngưỡng rubric trước khi ghi metric.

### 7.2. Không thay đổi rubric âm thầm

Nếu ngưỡng PASS đổi từ 0.80 sang 0.85, pass rate có thể giảm dù câu trả lời không thay đổi. Khi đó, dashboard đang so hai định nghĩa khác nhau.

Hãy lưu rubric version trong evaluation result store. Chỉ dùng rubric_version làm metric label nếu tập giá trị đồng thời hữu hạn và thực sự cần so sánh rollout. Với báo cáo dài hạn, lưu kết quả chi tiết trong evaluation store và tổng hợp theo batch.

### 7.3. Score ngoài miền hoặc không hữu hạn

Không ghi NaN, positive infinity, negative infinity hoặc score ngoài miền vào DistributionSummary. Kiểm tra score có hữu hạn, nằm trong miền rubric, và evaluator có trả schema đúng không. Nếu không hợp lệ, ghi evaluator outcome error/invalid_output và giữ raw result trong nơi lưu chi tiết có kiểm soát.

## 8. Đăng ký custom meter bằng Micrometer

Trong Spring Boot, có thể inject MeterRegistry vào một bean để đăng ký và cập nhật meter. Dùng cùng một class làm điểm ghi metric giúp các code path không tự đặt tên hoặc tags khác nhau.

### 8.1. Class QualityMetrics

Ví dụ sau dùng Java 17 và Micrometer. Các enum tạo ra tập tag values hữu hạn; score được validate trước khi ghi.

~~~java
import java.time.Duration;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public final class QualityMetrics {

    public enum CaseType {
        RAG("rag"),
        TOOL("tool"),
        MULTI_TURN("multi_turn"),
        OTHER("other");

        private final String tag;

        CaseType(String tag) {
            this.tag = tag;
        }

        public String tag() {
            return tag;
        }
    }

    public enum Criterion {
        RELEVANCE("relevance"),
        GROUNDEDNESS("groundedness"),
        FACT_CHECK("fact_check"),
        TOOL_SELECTION("tool_selection"),
        OTHER("other");

        private final String tag;

        Criterion(String tag) {
            this.tag = tag;
        }

        public String tag() {
            return tag;
        }
    }

    public enum Verdict {
        PASS("pass"),
        FAIL("fail"),
        INCONCLUSIVE("inconclusive"),
        NOT_APPLICABLE("not_applicable"),
        SKIPPED("skipped");

        private final String tag;

        Verdict(String tag) {
            this.tag = tag;
        }

        public String tag() {
            return tag;
        }
    }

    public enum Evaluator {
        RULE_BASED("rule_based"),
        MODEL_JUDGE("model_judge"),
        HUMAN("human"),
        OTHER("other");

        private final String tag;

        Evaluator(String tag) {
            this.tag = tag;
        }

        public String tag() {
            return tag;
        }
    }

    public enum ExecutionOutcome {
        SUCCESS("success"),
        TIMEOUT("timeout"),
        ERROR("error"),
        CANCELLED("cancelled");

        private final String tag;

        ExecutionOutcome(String tag) {
            this.tag = tag;
        }

        public String tag() {
            return tag;
        }
    }

    private final MeterRegistry registry;

    public QualityMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordVerdict(
            CaseType caseType,
            Criterion criterion,
            Verdict verdict,
            Double score
    ) {
        if (score != null) {
            if (!Double.isFinite(score) || score < 0.0 || score > 1.0) {
                throw new IllegalArgumentException(
                        "Score must be finite and within [0, 1]");
            }
            if (verdict == Verdict.INCONCLUSIVE
                    || verdict == Verdict.NOT_APPLICABLE
                    || verdict == Verdict.SKIPPED) {
                throw new IllegalArgumentException(
                        "This verdict must not carry a quality score");
            }
        }

        Counter.builder("app.ai.eval.criterion.completed")
                .tag("case_type", caseType.tag())
                .tag("criterion", criterion.tag())
                .tag("verdict", verdict.tag())
                .register(registry)
                .increment();

        if (score != null) {
            DistributionSummary.builder("app.ai.eval.score")
                    .baseUnit("score")
                    .serviceLevelObjectives(
                            0.25, 0.50, 0.70, 0.79, 0.80, 0.90, 1.00)
                    .tag("case_type", caseType.tag())
                    .tag("criterion", criterion.tag())
                    .register(registry)
                    .record(score);
        }
    }

    public void recordExecution(
            Evaluator evaluator,
            ExecutionOutcome outcome,
            Duration duration
    ) {
        if (duration == null || duration.isNegative()) {
            throw new IllegalArgumentException(
                    "Evaluation duration must be non-negative");
        }

        Counter.builder("app.ai.eval.execution")
                .tag("evaluator", evaluator.tag())
                .tag("outcome", outcome.tag())
                .register(registry)
                .increment();

        Timer.builder("app.ai.eval.duration")
                .tag("evaluator", evaluator.tag())
                .tag("outcome", outcome.tag())
                .serviceLevelObjectives(
                        Duration.ofMillis(100),
                        Duration.ofMillis(250),
                        Duration.ofMillis(500),
                        Duration.ofSeconds(1),
                        Duration.ofSeconds(2))
                .register(registry)
                .record(duration);
    }
}
~~~

### 8.2. Vì sao tách recordVerdict và recordExecution?

Hai method có hai thời điểm và đơn vị khác nhau:

- recordExecution được gọi một lần cho mỗi lần evaluator thực thi kết thúc, kể cả timeout/error.
- recordVerdict được gọi một lần khi criterion có kết quả cuối theo contract. Một evaluator timeout không tạo quality verdict.

Nếu evaluator retry ba lần rồi lần thứ ba thành công, execution counter tăng ba lần với ba outcome tương ứng, còn criterion verdict counter tăng một lần khi criterion được chốt.

### 8.3. Không tạo meter theo raw input

Ví dụ dùng enum giúp code chỉ có thể truyền các giá trị taxonomy đã định nghĩa. Nếu input đến từ model/provider/plugin, phải map vào enum trước. Không truyền tên tool, model ID, prompt hoặc exception message trực tiếp vào tag.

### 8.4. Đăng ký meter sớm hay lazy?

Micrometer meter thường được tạo khi builder được register. Ví dụ trên tạo meter khi method được gọi lần đầu. Nếu dashboard cần hiển thị zero cho mọi criterion/case type ngay từ đầu, có thể pre-register tập tổ hợp nhỏ đã biết trong lifecycle khởi động.

Không pre-register tích Descartes của nhiều chiều lớn. Chỉ khởi tạo các series mà dashboard thật sự cần; theo dõi scrape và exporter output để xác nhận zero được xuất như kỳ vọng.

## 9. Gắn custom Observation với bước evaluation

Metrics tổng hợp theo nhóm. Observation tạo một phạm vi hoạt động có thể liên kết logs/traces và thời gian thực thi. Khi ứng dụng đã dùng Micrometer Observation/Tracing, có thể thêm custom Observation cho evaluator hoặc quality check.

### 9.1. Ví dụ custom Observation

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public final class EvaluationObservation {

    private final ObservationRegistry observationRegistry;

    public EvaluationObservation(
            ObservationRegistry observationRegistry
    ) {
        this.observationRegistry = observationRegistry;
    }

    public void observe(
            QualityMetrics.CaseType caseType,
            QualityMetrics.Criterion criterion,
            String runReference,
            Runnable evaluation
    ) {
        // runReference phải là opaque reference, không chứa PII hoặc prompt text.
        Observation.createNotStarted(
                        "app.ai.evaluation",
                        observationRegistry)
                .lowCardinalityKeyValue(
                        "case_type", caseType.tag())
                .lowCardinalityKeyValue(
                        "criterion", criterion.tag())
                .highCardinalityKeyValue(
                        "evaluation_run_ref", runReference)
                .observe(evaluation);
    }
}
~~~

Đây là ví dụ API Micrometer Observation. Observation được tạo trước khi có verdict; sau khi evaluator chạy, code ghi verdict bằng QualityMetrics. Không đưa raw prompt, user ID hay dữ liệu riêng tư vào span attributes.

### 9.2. Low-cardinality và high-cardinality

Low-cardinality values có thể được chuyển thành metric tags qua Observation handler. Chỉ dùng các giá trị hữu hạn như component, case_type, criterion và outcome.

High-cardinality values phù hợp hơn với trace/span attributes nếu tracing backend và privacy policy cho phép. Không đưa run ID, case ID, conversation ID hoặc trace ID thành metric tags. Dù high-cardinality không tạo series metric qua handler chuẩn, dữ liệu này vẫn cần retention, access control và giới hạn kích thước.

### 9.3. Không tạo Observation trùng với Spring AI

Spring AI có instrumentation cho các hoạt động framework như ChatClient/model/tool tùy phiên bản và cấu hình. Custom Observation nên bao quanh bước nghiệp vụ chưa được đo, ví dụ evaluation, rubric scoring hoặc business verification. Tránh tạo span mới lặp lại cùng operation chỉ để có một tên metric khác.

## 10. Tích hợp với online và offline evaluation

Custom quality metric có thể được ghi từ hai luồng chính.

### 10.1. Online evaluation

Online evaluation kiểm tra một phần traffic production hoặc những tác vụ có rủi ro cao.

Luồng tham khảo:

1. Request hoàn tất và lưu kết quả/trace cần thiết theo policy.
2. Chọn sample hoặc trigger evaluator theo rule.
3. Evaluator chạy đồng bộ hoặc bất đồng bộ.
4. Ghi evaluator execution outcome.
5. Nếu có verdict hợp lệ, ghi quality metric đúng một lần.
6. Lưu evidence và evaluator metadata vào kho kết quả.

Không nhất thiết chạy model judge cho mọi request. Sampling giúp kiểm soát cost và latency; nhưng báo cáo phải nêu tỷ lệ sampling và phương pháp chọn mẫu để tránh diễn giải sample như toàn bộ traffic.

### 10.1.1. Ghi execution và verdict ở đúng điểm

Ví dụ luồng đồng bộ:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

long started = System.nanoTime();
QualityMetrics.ExecutionOutcome outcome =
        QualityMetrics.ExecutionOutcome.ERROR;

try {
    EvaluationResult result = evaluator.evaluate(input);

    qualityMetrics.recordVerdict(
            result.caseType(),
            result.criterion(),
            result.verdict(),
            result.score());

    outcome = QualityMetrics.ExecutionOutcome.SUCCESS;
    return result;
} catch (TimeoutException ex) {
    outcome = QualityMetrics.ExecutionOutcome.TIMEOUT;
    throw ex;
} finally {
    qualityMetrics.recordExecution(
            QualityMetrics.Evaluator.MODEL_JUDGE,
            outcome,
            Duration.ofNanos(System.nanoTime() - started));
}
~~~

Đây là skeleton tích hợp; EvaluationResult, evaluator và input thuộc domain của ứng dụng. Runtime exception khác được giữ ở outcome ERROR mặc định. Với async evaluator, đặt finally tương đương tại completion/cancel callback thay vì ngay sau khi tạo Future/Publisher.

### 10.2. Offline evaluation

Offline evaluation chạy dataset có version, fixture và rubric cố định:

1. Tạo evaluation run với dataset/rubric/model/prompt metadata.
2. Chạy từng case và thu kết quả.
3. Ghi metric tổng hợp theo case_type/criterion/verdict.
4. Ghi run summary và case-level evidence vào evaluation store.
5. So sánh với baseline cùng dataset, rubric và điều kiện càng tương đồng càng tốt.

Không đưa từng run ID/case ID thành labels trong Prometheus. Dùng metrics để xem xu hướng tổng hợp; dùng evaluation store để drill down.

### 10.3. Đừng trộn online và offline trong cùng một mẫu số

Online sample có thể bị lệch bởi traffic distribution và sampling policy. Offline dataset có thể cân bằng case types và chứa nhiều edge cases. Nếu gộp chúng thành một pass rate duy nhất, dashboard không còn cho biết nguồn thay đổi đến từ đâu.

Có thể dùng một label hữu hạn evaluation_mode=online|offline nếu cần so sánh. Định nghĩa mẫu số và thời gian tổng hợp riêng cho từng mode.

## 11. Chọn tiêu chí chất lượng cho RAG

RAG có nhiều điểm đo. Không dùng một relevance score để đại diện toàn bộ pipeline.

| Tiêu chí | Đơn vị đánh giá | Cách đo gợi ý |
| --- | --- | --- |
| Retrieval precision@k | Query có ground truth | Tỷ lệ documents được lấy top-k là relevant |
| Retrieval recall@k | Query có tập relevant docs chuẩn | Tỷ lệ relevant docs tìm được trong top-k |
| MRR | Query | Reciprocal rank của relevant result đầu tiên |
| nDCG@k | Query có graded relevance | Chất lượng thứ tự xếp hạng |
| Context relevance | Retrieved chunk/query | Judge hoặc human rubric |
| Answer relevance | Câu trả lời/case | Câu trả lời có đáp ứng câu hỏi |
| Groundedness | Claim/answer | Claim có evidence hỗ trợ |
| Faithfulness | Answer/source context | Nội dung có trung thành với context |
| Citation correctness | Citation/claim | Citation có thực sự hỗ trợ claim |

### 11.1. Chỉ tính retrieval recall khi có ground truth

Recall@k cần biết tập tài liệu liên quan chuẩn. Nếu không có ground truth, không thể gọi số retrieved documents là recall. Có thể ghi documents count hoặc evaluator relevance proxy, nhưng phải đặt tên đúng.

### 11.2. Không lấy chunk count thay cho quality

Retriever trả 20 chunks không có nghĩa tốt hơn trả 5 chunks. Số lượng là operational/context-size metric. Relevance, recall và groundedness là quality metric cần rubric hoặc nhãn tham chiếu.

### 11.3. Ghi rõ cấp đo

Nếu chấm 10 chunks trong một query, hãy phân biệt chunk-level relevance samples, query-level retrieval verdict và task-level answer verdict. Nếu không, một query trả nhiều chunks có thể chi phối score trung bình hơn query khác.

## 12. Chọn tiêu chí chất lượng cho tool calling

Tool calling cũng cần đo theo nhiều bước. Một lần model đề xuất tool không đồng nghĩa tool đã được chạy; tool chạy thành công không đồng nghĩa business action đã hoàn tất.

### 12.1. Các giai đoạn cần phân biệt

| Giai đoạn | Sự kiện | Metric gợi ý |
| --- | --- | --- |
| Tool proposal | Model đề xuất tool/function | Proposed tool family |
| Tool selection | Tool được chọn có đúng với expected action không? | Selection verdict |
| Argument validation | Arguments có đúng schema và policy không? | Argument validation outcome |
| Dispatch | Dispatcher cho phép hoặc từ chối | Dispatch decision |
| Execution | Handler thực sự chạy | Execution outcome/latency |
| Business verification | Source of truth xác nhận hậu điều kiện | Verified business outcome |

Một tool bị policy từ chối không phải execution timeout. Một handler trả response thành công nhưng business operation còn PENDING không phải verified completion.

### 12.2. Tool selection accuracy

Với dataset có expected tool:

\[
\text{Tool selection accuracy}
=\frac{\text{Cases chọn đúng tool}}{\text{Cases có expected tool}}
\]

Phải định nghĩa rõ case không cần tool, trường hợp nhiều tool hợp lệ và trường hợp tool được chọn đúng nhưng arguments sai.

### 12.3. Business verification

Với thao tác ghi dữ liệu như tạo refund, chỉ ghi verified success khi source of truth xác nhận trạng thái hoàn tất theo contract. Nếu tool trả ACCEPTED/PENDING, metric nên biểu diễn accepted/pending hoặc operation state riêng.

Nếu timeout xảy ra sau khi backend có thể đã nhận lệnh, hãy kiểm tra operation ID/idempotency state trước retry. Không ghi business failure chỉ dựa vào việc client không nhận được response.

## 13. PromQL cho quality metrics

Micrometer Prometheus registry thường chuẩn hóa tên meter thành tên metric Prometheus và thêm hậu tố theo loại meter. Các truy vấn dưới đây giả định exporter đang phát đúng các series minh họa; hãy kiểm tra scrape output thực tế trước khi dùng.

### 13.1. PASS rate trên các verdict có kết luận

~~~promql
sum by (case_type, criterion) (
  rate(app_ai_eval_criterion_completed_total{verdict="pass"}[15m])
)
/
sum by (case_type, criterion) (
  rate(app_ai_eval_criterion_completed_total{verdict=~"pass|fail"}[15m])
)
~~~

Mẫu số chỉ gồm PASS và FAIL, tức những criterion có verdict nhị phân. Không đưa INCONCLUSIVE, NOT_APPLICABLE hoặc SKIPPED vào mẫu số này. Nếu mẫu số bằng 0 hoặc query rỗng, hiển thị N/A/no evaluated criteria.

### 13.2. Inconclusive rate

~~~promql
sum by (case_type, criterion) (
  rate(app_ai_eval_criterion_completed_total{verdict="inconclusive"}[15m])
)
/
sum by (case_type, criterion) (
  rate(app_ai_eval_criterion_completed_total{
    verdict=~"pass|fail|inconclusive"
  }[15m])
)
~~~

Inconclusive rate tăng có thể cho thấy thiếu evidence, rubric chưa rõ, evaluator không ổn định hoặc case/criterion mix thay đổi. Hãy xem evaluator execution error riêng để tìm nguyên nhân.

### 13.3. Mean score đúng cách

DistributionSummary xuất count và sum. Mean theo nhóm cần lấy tổng sum chia tổng count:

~~~promql
sum by (case_type, criterion) (
  rate(app_ai_eval_score_sum[15m])
)
/
sum by (case_type, criterion) (
  rate(app_ai_eval_score_count[15m])
)
~~~

Không lấy trung bình của các mean theo instance hoặc từng case group nếu số sample khác nhau. Tính tổng có trọng số bằng sum/count.

### 13.4. Tỷ lệ evaluator execution error

~~~promql
sum by (evaluator) (
  rate(app_ai_eval_execution_total{outcome=~"timeout|error"}[5m])
)
/
sum by (evaluator) (
  rate(app_ai_eval_execution_total[5m])
)
~~~

Đây là tỷ lệ evaluator attempts kết thúc timeout/error. Nó không phải quality failure rate.

### 13.5. Evaluator latency p95

Nếu Timer histogram được bật:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, evaluator, outcome) (
    rate(app_ai_eval_duration_seconds_bucket[5m])
  )
)
~~~

Giữ outcome để thấy latency khác nhau giữa success, timeout và error. Nếu chỉ quan sát success, percentile có thể trông tốt dù các lần timeout bị bỏ khỏi histogram.

### 13.6. Tỷ lệ score đạt ngưỡng

Nếu DistributionSummary publish histogram/SLO buckets tại các mốc 0.79, 0.80 và 1.00:

~~~promql
sum by (case_type, criterion) (
  rate(app_ai_eval_score_bucket{le="1.0"}[15m])
)
-
sum by (case_type, criterion) (
  rate(app_ai_eval_score_bucket{le="0.79"}[15m])
)
~~~

Với score được chuẩn hóa đến hai chữ số thập phân, biểu thức đếm sample từ 0.80 đến 1.00 bằng cách lấy bucket đến 1.0 trừ bucket đến 0.79. Nếu rubric dùng score liên tục không làm tròn, hãy ghi một Counter pass-threshold riêng hoặc thiết kế boundary theo precision thực tế; không suy ra score lớn hơn hoặc bằng 0.8 từ bucket đến 0.8. Tỷ lệ score đạt ngưỡng cần chia cho tổng score count. Hãy xác minh bucket boundaries và cách exporter tạo bucket; SLO bucket phải được cấu hình trước.

### 13.7. Offline run không nhất thiết phù hợp với rate ngắn

Nếu evaluation runner chỉ chạy mỗi đêm, rate trong 5 phút có thể rỗng hầu hết thời gian. Dùng increase trên cửa sổ bao trùm batch hoặc đọc run summary từ evaluation store. Không biến thời gian không chạy batch thành PASS rate 100%.

## 14. Cấu hình DistributionSummary và histogram có kiểm soát

Nếu chỉ cần mean score, count và sum thường đủ. Nếu cần phân bố, threshold share hoặc quantile, cấu hình histogram có chủ đích.

Ví dụ score có miền 0..1 và các ngưỡng cần theo dõi:

~~~java
DistributionSummary.builder("app.ai.eval.score")
        .baseUnit("score")
        .serviceLevelObjectives(
                0.25, 0.50, 0.70, 0.79, 0.80, 0.90, 1.00)
        .tag("case_type", caseType.tag())
        .tag("criterion", criterion.tag())
        .register(registry)
        .record(score);
~~~

SLO boundaries cho phép xem số sample nằm dưới/trên các mốc đã chọn. Nếu cần percentile histogram tổng quát, có thể bật percentile histogram theo backend/registry hỗ trợ; việc đó làm tăng series count và chi phí lưu trữ.

Trước khi bật:

1. Chọn threshold có ý nghĩa theo rubric.
2. Tính số label combinations.
3. Nhân với số bucket và số series phụ.
4. Kiểm tra scrape output.
5. Đánh giá query cost và retention.

Không tạo histogram cho mọi metric chỉ vì có thể.

## 15. Đặt instrumentation ở đúng ranh giới

Ghi metric quá sớm hoặc quá muộn đều tạo semantics sai.

### 15.1. Ghi execution outcome khi evaluator kết thúc

Một lần evaluator có thể:

- Thành công và trả verdict.
- Thành công nhưng verdict inconclusive.
- Timeout.
- Lỗi parse/schema.
- Bị hủy.

Execution counter/timer ghi ở cuối mỗi attempt. Quality verdict counter chỉ ghi khi case được chốt verdict hợp lệ.

### 15.2. Ghi verdict một lần tại điểm commit kết quả

Nếu evaluation pipeline có retry, queue redelivery hoặc worker restart, cần idempotency cho việc ghi kết quả. Không ghi criterion completed mỗi lần message được xử lý nếu cùng một run/case/criterion đã được chốt trước đó.

Một lựa chọn là lưu evaluation result với unique key gồm run ID, case ID và criterion; chỉ khi insert/transition trạng thái thành công mới phát metric criterion completion. Metric không phải source of truth để deduplicate. Nếu cần đếm overall case completion, phát một metric riêng đúng một lần sau khi tất cả criteria bắt buộc đã chốt.

### 15.3. Phân biệt streaming partial và final result

Trong streaming response, score tạm thời hoặc partial claim extraction chưa phải verdict cuối. Chỉ ghi quality verdict khi evaluation contract xác nhận hoàn tất. Nếu cần theo dõi partial processing, tạo metric riêng có tên và semantics rõ.

### 15.4. Không đo evaluator bằng chính verdict mà nó tạo

Evaluator execution error cần được ghi kể cả khi không có quality verdict. Nếu chỉ tạo metric trong nhánh có verdict, evaluator timeout sẽ biến mất khỏi dashboard và quality coverage bị đánh giá quá cao.

## 16. Calibration và độ tin cậy của model judge

Model judge là một evaluator có thể sai, thiên lệch hoặc thay đổi theo model/prompt version. Metric judge score không tự động là ground truth.

### 16.1. Đối chiếu với human-labeled sample

Tạo một tập sample được con người đánh giá theo cùng rubric. So sánh:

- Agreement rate giữa judge và human.
- Precision/recall cho nhãn FAIL quan trọng.
- False pass rate.
- False fail rate.
- Tỷ lệ inconclusive.
- Độ ổn định giữa các lần judge cùng input.

Các thống kê này nên được tính trên tập sample có ground truth, lưu confusion matrix và metadata trong evaluation store. Metric production có thể theo dõi agreement rate theo nhóm hữu hạn nếu sample được thiết kế đại diện.

### 16.2. Version của judge

Khi đổi judge model, system prompt hoặc rubric, phân bố verdict có thể thay đổi dù ứng dụng chính không đổi. Lưu judge model/version, judge prompt version và rubric version trong run metadata. Nếu cần canary comparison trên metrics, dùng release cohort hữu hạn và có thời hạn.

### 16.3. Không dùng model judge làm oracle duy nhất

Kết hợp deterministic checks, source-of-truth verification, retrieval ground truth, human review và model judge. Với tác vụ quan trọng, false pass có thể đắt hơn evaluator cost; chọn kiểm tra phù hợp với mức rủi ro.

## 17. Cardinality, privacy và cost của quality instrumentation

Quality instrumentation có thể làm cardinality tăng nhanh nếu gắn dataset/case/version ID vào tags.

Không dùng các giá trị sau làm metric labels:

- prompt text, answer text hoặc user query.
- user ID, tenant ID, conversation ID.
- evaluation run ID, case ID, claim ID.
- document ID, chunk ID hoặc citation URL.
- raw tool name từ plugin tùy ý.
- judge exception message hoặc raw provider response.

Giữ các chi tiết này trong evaluation store, trace hoặc log có phân quyền. Metric labels chỉ nên có tập giá trị hữu hạn như case_type, criterion, verdict, evaluator và outcome.

### 17.1. Cost của evaluator

Model judge cũng tiêu thụ token và có latency/cost. Nếu cần đo, tách:

- judge input/output tokens.
- judge request count.
- judge cost estimate hoặc provider billed cost.
- evaluator latency.
- số case có verdict hợp lệ.

Định nghĩa đơn vị rõ: tokens per evaluator attempt hay tokens per completed case. Retry có thể làm tăng cost của một case; đừng chia cost cho attempts nếu dashboard muốn cost per completed case.

### 17.2. Đừng đưa score từng claim vào một metric tag

Score là sample value của DistributionSummary, không phải label value. Ví dụ không tạo tag score="0.81", score="0.82" ...; điều đó tạo cardinality gần như vô hạn. Ghi score bằng record(value).

## 18. Dashboard và alert cho chất lượng

Dashboard chất lượng nên có các panel riêng:

| Panel | Chỉ số | Câu hỏi |
| --- | --- | --- |
| Criterion coverage | completed criteria / expected criteria | Có bao nhiêu criterion đã có kết quả cuối? |
| PASS rate | pass / (pass + fail) | Trong ca có kết luận, bao nhiêu ca đạt? |
| Inconclusive | inconclusive / decided-or-completed | Judge có thường xuyên thiếu kết luận không? |
| Score distribution | Mean, buckets hoặc quantiles | Phân bố score thay đổi thế nào? |
| Evaluator availability | timeout/error rate | Có thể tin kết quả đánh giá không? |
| Evaluator latency | p50/p95 | Đánh giá mất bao lâu? |
| RAG retrieval quality | recall/precision proxy có ground truth | Retriever có lấy đúng tài liệu? |
| Tool selection | selection accuracy | Model chọn đúng tool? |
| Verified business outcome | confirmed success/failure/pending | Tác vụ nghiệp vụ có hoàn tất? |
| Judge cost | tokens/cost per completed case | Chi phí kiểm tra chất lượng? |

Overall case coverage cần một meter case-level riêng hoặc run summary trong evaluation store. Không lấy criterion.completed chia cho số cases expected vì một case có thể chứa nhiều criteria.

### 18.1. Alert quality regression

Một alert quality regression cần:

- So sánh cùng case_type/criterion và cùng rubric.
- Có cỡ mẫu tối thiểu.
- Theo dõi coverage để biết mẫu có đủ không.
- Duy trì ngưỡng trong một khoảng thời gian hoặc một số batch liên tiếp.
- Tách thay đổi judge/evaluator khỏi thay đổi model/prompt đang được đánh giá.

Ví dụ: cảnh báo khi PASS rate giảm hơn 5 điểm phần trăm so với baseline trên ít nhất 200 decided cases trong batch. Đây chỉ là ngưỡng minh họa; chọn theo SLO và mức rủi ro.

### 18.2. Alert evaluator unavailable

Nếu evaluator timeout/error tăng, quality dashboard có thể thiếu kết quả. Cảnh báo evaluator availability riêng. Không báo quality regression khi chưa có đủ verdict; báo evaluation coverage thấp hoặc evaluator unavailable.

### 18.3. Theo dõi score drift

Mean score ổn định không đảm bảo phân bố ổn định. Theo dõi histogram/quantile và tỷ lệ score dưới threshold. So sánh cùng rubric, cùng case mix và cùng evaluator calibration.

## 19. Kiểm thử custom quality instrumentation

Metric quality cần test cả **giá trị**, **sự hiện diện**, **đơn vị đếm** và **thời điểm ghi**. Test chỉ kiểm tra meter tồn tại sẽ không phát hiện double counting hoặc score sai miền.

### 19.1. Unit test với SimpleMeterRegistry

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class QualityMetricsTest {

    @Test
    void recordsAValidZeroScoreAsARealSample() {
        var registry = new SimpleMeterRegistry();
        var metrics = new QualityMetrics(registry);

        metrics.recordVerdict(
                QualityMetrics.CaseType.RAG,
                QualityMetrics.Criterion.RELEVANCE,
                QualityMetrics.Verdict.FAIL,
                0.0);

        var verdictCounter = registry.find(
                        "app.ai.eval.criterion.completed")
                .tag("case_type", "rag")
                .tag("criterion", "relevance")
                .tag("verdict", "fail")
                .counter();

        var scoreSummary = registry.find("app.ai.eval.score")
                .tag("case_type", "rag")
                .tag("criterion", "relevance")
                .summary();

        assertEquals(1.0, verdictCounter.count(), 0.000001);
        assertEquals(1L, scoreSummary.count());
        assertEquals(0.0, scoreSummary.totalAmount(), 0.000001);
    }

    @Test
    void inconclusiveVerdictDoesNotCreateAScoreSample() {
        var registry = new SimpleMeterRegistry();
        var metrics = new QualityMetrics(registry);

        metrics.recordVerdict(
                QualityMetrics.CaseType.RAG,
                QualityMetrics.Criterion.GROUNDEDNESS,
                QualityMetrics.Verdict.INCONCLUSIVE,
                null);

        var verdictCounter = registry.find(
                        "app.ai.eval.criterion.completed")
                .tag("verdict", "inconclusive")
                .counter();
        var scoreSummary = registry.find("app.ai.eval.score")
                .tag("criterion", "groundedness")
                .summary();

        assertEquals(1.0, verdictCounter.count(), 0.000001);
        assertNull(scoreSummary);
    }

    @Test
    void invalidScoreIsRejectedBeforeAnyVerdictIsRecorded() {
        var registry = new SimpleMeterRegistry();
        var metrics = new QualityMetrics(registry);

        assertThrows(IllegalArgumentException.class, () ->
                metrics.recordVerdict(
                        QualityMetrics.CaseType.RAG,
                        QualityMetrics.Criterion.RELEVANCE,
                        QualityMetrics.Verdict.PASS,
                        1.5));

        var verdictCounter = registry.find(
                        "app.ai.eval.criterion.completed")
                .tag("verdict", "pass")
                .counter();

        assertNull(verdictCounter);
    }
}
~~~

Các test này giả định class QualityMetrics ở cùng package hoặc đã được import. Nếu project dùng JUnit assertion helpers khác, điều chỉnh import tương ứng.

### 19.2. Test execution outcome riêng

Với evaluator timeout:

- Execution counter tăng một với outcome timeout.
- Timer có một sample với outcome timeout.
- Quality verdict counter không tăng.
- Score summary không có sample mới.

Với evaluator success nhưng verdict inconclusive:

- Execution counter tăng một với outcome success.
- Quality verdict counter tăng một với verdict inconclusive.
- Score summary không ghi sample nếu rubric không tạo score.

### 19.3. Integration test với Prometheus registry

SimpleMeterRegistry kiểm tra logic Micrometer, nhưng không chứng minh tên series và histogram bucket sau exporter. Integration test nên:

1. Khởi tạo Prometheus registry được dùng trong ứng dụng.
2. Ghi fixture PASS, FAIL, INCONCLUSIVE và evaluator timeout.
3. Lấy scrape exposition.
4. Xác minh metric names, labels, count/sum và bucket boundaries.
5. Xác minh không có case ID, run ID, prompt hoặc user ID trong labels.
6. So sánh series count với cardinality budget.

### 19.4. Test idempotency và retry

Giả lập cùng run/case/criterion được xử lý hai lần do queue redelivery. Chỉ lần chuyển trạng thái từ pending sang terminal mới được ghi criterion completion. Evaluator attempts vẫn được ghi riêng cho mỗi lần thực thi.

Metric không thay thế idempotency ở evaluation result store. Nếu result store không có cơ chế deduplicate, Counter có thể tăng hai lần cho một case dù dashboard không có cách phát hiện.

## 20. Bài thực hành

**Bối cảnh:** một trợ lý Spring AI dùng RAG để trả lời chính sách, gọi tool tra cứu đơn và có evaluator model judge để chấm relevance, groundedness, fact checking và tool selection.

### Phần A — Thiết kế metric contract

1. Chọn đơn vị đo cho task, evaluation case, criterion, claim và tool call.
2. Định nghĩa verdict pass/fail/inconclusive/not_applicable/skipped.
3. Định nghĩa evaluator execution outcome success/timeout/error/cancelled.
4. Chỉ ra thời điểm ghi case completed và cách tránh đếm đôi khi retry.
5. Quy định score domain, threshold và cách xử lý score missing.

### Phần B — Chọn meter

Ghép từng nhu cầu với Counter, DistributionSummary, Timer hoặc Gauge:

1. Số kết quả case-criterion PASS/FAIL.
2. Phân bố relevance score từ 0 đến 1.
3. Model judge latency.
4. Số evaluation runs đang in-flight.
5. Số claims đã được fact-check.
6. Số evaluator timeout.

Giải thích vì sao không nên dùng một Gauge cho tổng số case đã hoàn tất hoặc dùng score làm label.

### Phần C — Triển khai instrumentation

1. Tạo class QualityMetrics với MeterRegistry.
2. Dùng enum hoặc allowlist cho case_type, criterion, verdict và evaluator.
3. Ghi execution outcome riêng với quality verdict.
4. Chỉ ghi DistributionSummary khi có score hợp lệ.
5. Thêm custom Observation bao quanh evaluation.
6. Xác minh high-cardinality attributes không trở thành metric labels.

### Phần D — Viết PromQL

1. Tính PASS rate trên PASS + FAIL.
2. Tính INCONCLUSIVE rate.
3. Tính mean score bằng tổng sum chia tổng count.
4. Tính evaluator error rate.
5. Tính p95 evaluator latency.
6. Tính tỷ lệ score trên ngưỡng 0.8 nếu histogram bucket đã được cấu hình.

### Phần E — Phân tích sự cố

Sau một lần deploy:

- PASS rate relevance giảm từ 94% xuống 86%.
- Inconclusive rate tăng từ 2% lên 9%.
- Evaluator timeout tăng từ 0,5% lên 6%.
- Mean score groundedness gần như không đổi.
- Evaluation coverage giảm từ 98% xuống 83%.

Hãy xác định:

1. Có đủ bằng chứng để kết luận chất lượng ứng dụng giảm không?
2. Phần nào có thể do evaluator availability?
3. Cần kiểm tra rubric, judge version và dataset mix nào?
4. Cần mở traces/logs/evaluation records nào?
5. Alert nào nên phát trước: quality regression hay evaluator unavailable?

### Câu hỏi tự kiểm tra

- Vì sao technical success không đồng nghĩa quality PASS?
- Vì sao evaluator timeout không được ghi thành quality FAIL?
- Một case có ba criteria thì criterion completion được đếm mấy lần, và overall case completion được đếm ở thời điểm nào?
- Khi nào dùng DistributionSummary thay Counter?
- Vì sao score là sample value chứ không phải label?
- Khi nào cần custom Observation bên cạnh Spring AI observations?
- Vì sao online sample và offline dataset không nên gộp mẫu số?
- Retrieval recall cần loại ground truth nào?
- Vì sao tool execution success khác business verified success?
- Làm sao tránh đếm case hai lần khi evaluator retry?
- Vì sao cần human-labeled sample để calibrate model judge?
- Khi nào nên bật histogram cho quality score?

## 21. Những điều cần ghi nhớ

1. **Chỉ thêm custom instrumentation khi metric có sẵn không trả lời đúng câu hỏi chất lượng.** Tránh nhân đôi meter cùng semantics.
2. **Tách technical outcome, task outcome, quality verdict, evaluator outcome và business outcome.** Chúng có đơn vị và thời điểm ghi khác nhau.
3. **Định nghĩa metric contract trước khi viết code.** Chọn rõ case, criterion, claim, score domain và điểm chốt kết quả.
4. **Counter đếm verdict, DistributionSummary ghi score, Timer đo evaluator latency, Gauge đo trạng thái tức thời.**
5. **Evaluator execution error không phải quality FAIL.** Ghi execution metrics kể cả khi không có verdict.
6. **Score chỉ được ghi khi hợp lệ theo rubric.** Missing, inconclusive và not applicable không được tự chuyển thành zero.
7. **Ghi criterion verdict đúng một lần.** Dùng idempotency ở result store để xử lý retry và redelivery; overall case completion có meter riêng.
8. **Dùng labels hữu hạn.** Case type, criterion, verdict và evaluator phù hợp; ID và nội dung request thuộc trace/store.
9. **Metrics tổng hợp, evaluation store giữ bằng chứng.** Dùng traces để điều tra từng bước và report để drill down.
10. **Model judge cần calibration.** Theo dõi agreement với human labels, evaluator availability và version drift.
11. **Histogram có chi phí cardinality.** Chọn bucket theo rubric và câu hỏi dashboard.
12. **Quality dashboard phải có coverage.** PASS rate không đủ nếu evaluator đang timeout hoặc nhiều case chưa hoàn tất.

## Tài liệu tham khảo

- [Micrometer Reference — Meter Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): meter, registry và tags.
- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): đếm event tích lũy.
- [Micrometer Reference — Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html): phân bố giá trị số.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo duration và count.
- [Micrometer Reference — Observations](https://docs.micrometer.io/micrometer/reference/observation.html): Observation API, low/high-cardinality key values.
- [Micrometer Reference — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): histogram, SLO boundaries và percentile.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): MeterRegistry, custom meters và export.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): observability cho ChatClient, model và tool.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): bucket, count, sum và quantile.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): rate, increase và histogram_quantile.
- [OpenTelemetry — Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/): semantics của measurements và aggregation.

**Lưu ý phiên bản:** API Micrometer, Observation handlers, Prometheus naming convention và Spring AI instrumentation phụ thuộc phiên bản và cấu hình. Các metric app.ai trong bài là ví dụ custom của ứng dụng, không phải danh sách mặc định. Trước khi triển khai, xác minh API của dependency đang dùng, scrape exposition và contract evaluator thực tế.
