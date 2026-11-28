# Chất lượng khi vận hành: Triển khai canary hoặc so sánh song song với phạm vi có kiểm soát

## 1. Vì sao cần rollout có kiểm soát?

Một thay đổi prompt, model, retriever hoặc tool có thể cải thiện chất lượng trên benchmark nhưng gây lỗi khi gặp traffic production. Benchmark thường không phản ánh hết task mix, hội thoại dài, dữ liệu mới, tải đồng thời, quota provider và hành vi tool thực tế.

Đưa thay đổi tới toàn bộ người dùng ngay lập tức làm tăng phạm vi ảnh hưởng nếu candidate có lỗi. Ngược lại, chỉ chạy offline evaluation không cho biết candidate hoạt động ra sao dưới tải, với latency, cost, provider limits và dữ liệu thật.

**Canary rollout** và **so sánh song song** giúp quan sát candidate trong phạm vi được giới hạn, có metric guardrails, có thể dừng hoặc rollback trước khi mở rộng.

Trong bài này cần phân biệt ba kỹ thuật:

- **Canary:** candidate nhận một phần traffic thật và response của candidate được phục vụ cho nhóm người dùng được phân công. Mục tiêu chính là kiểm tra độ an toàn khi rollout.
- **Shadow/parallel run:** candidate nhận bản sao input hoặc replay traffic nhưng response candidate không được trả cho người dùng. Mục tiêu là quan sát behavior và so sánh output trong cùng điều kiện.
- **A/B experiment:** người dùng hoặc interaction được phân ngẫu nhiên vào control và treatment để ước lượng tác động của thay đổi lên outcome. Mục tiêu là kiểm tra giả thuyết sản phẩm hoặc chất lượng.

Các kỹ thuật có thể kết hợp. Một model mới có thể được shadow trước, sau đó canary 1–5%, rồi chạy A/B experiment có thiết kế thống kê khi đã đủ điều kiện. Các tỷ lệ và bước cụ thể phải dựa trên traffic, risk và capacity của hệ thống.

Bài học thuộc chương **Chất lượng khi vận hành** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời theo dõi metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua các phiên bản prompt, model và pipeline.

Sau bài học, bạn có thể:

- Phân biệt canary, shadow run và randomized A/B experiment.
- Xác định đơn vị phân nhóm: user, conversation, session hoặc interaction.
- Gán variant ổn định và ghi assignment/exposure/fallback rõ ràng.
- Route request tới nhiều ChatModel/ChatClient trong Spring AI.
- Thiết kế traffic ramp, pause, promote và rollback guardrails.
- Chạy shadow evaluation mà không lặp lại tool side effects hoặc làm nhiễm session memory.
- Thiết kế hypothesis, primary metric, guardrails, sample size và experiment duration.
- Phát hiện sample ratio mismatch, contamination và selection bias.
- Đánh giá quality cùng latency, availability, token usage và cost theo từng arm.
- Nối experiment assignment với metrics, traces, evaluation samples và release ledger.

## 2. Phân biệt canary, shadow và A/B

Ba phương pháp cùng có control/candidate nhưng trả lời các câu hỏi khác nhau.

| Phương pháp | Candidate có nhận traffic? | Response candidate tới user? | Câu hỏi chính |
| --- | --- | --- | --- |
| Canary | Có, một phần traffic thật | Có | Candidate có đủ an toàn để tăng phạm vi không? |
| Shadow/parallel | Có bản sao input hoặc replay | Không | Candidate sẽ hành xử thế nào trên traffic tương tự? |
| A/B experiment | Có, theo random assignment | Có, theo variant được gán | Candidate có cải thiện outcome so với control không? |

### 2.1. Canary là kiểm soát blast radius

Canary thường bắt đầu với một phần nhỏ traffic. Sau mỗi bước, hệ thống kiểm tra health, latency, error rate, quality signals và cost. Nếu các guardrails đạt yêu cầu, tăng traffic; nếu không, dừng hoặc rollback.

Canary có thể được phân theo user, tenant, region, route hoặc weighted traffic. Nếu cần so sánh nhân quả, nên randomize assignment và ghi nhận exposure; một rollout theo region hoặc thời gian chỉ cho thấy sự liên hệ, dễ bị nhiễu bởi khác biệt cohort và seasonality.

### 2.2. Shadow là chạy candidate mà không thay đổi trải nghiệm

Shadow gửi cùng input tới candidate và control, nhưng chỉ control tạo response phục vụ người dùng. Candidate output được lưu ở evidence store hoặc chuyển qua evaluator để so sánh.

Shadow hữu ích khi:

- Candidate chưa đủ tin cậy để phục vụ user.
- Cần đo latency, token usage hoặc provider behavior trên traffic thật.
- Muốn tìm task family mà candidate xử lý kém.
- Cần so response trên cùng input và context snapshot.
- Muốn kiểm tra candidate trước khi mở canary.

Shadow không tự động là A/B test vì candidate không được user trải nghiệm và không tạo outcome hành vi của user.

### 2.3. A/B experiment kiểm tra tác động

A/B phân ngẫu nhiên đơn vị thí nghiệm vào control hoặc treatment. Sau đó so sánh primary outcome và guardrails trên hai nhóm.

Ví dụ: giả thuyết prompt P2 tăng relevance pass rate ít nhất 2 điểm phần trăm mà không làm p95 latency tăng quá 10% hoặc cost/request tăng quá 5%.

A/B cần có:

- Hypothesis và estimand được xác định trước.
- Assignment unit và randomization method.
- Primary metric duy nhất hoặc hierarchy được công bố.
- Guardrail metrics.
- Minimum detectable effect (MDE).
- Sample size và power.
- Experiment duration và stopping rule.
- Rubric/evaluator version giống nhau giữa các arm.
- Exposure và fallback logging.

## 3. Quyết định nên dùng phương pháp nào?

~~~mermaid
flowchart TD
    CHANGE["Candidate prompt / model / retriever / tool"] --> OFFLINE["Offline evaluation and regression suite"]
    OFFLINE --> PASS{"Offline guardrails pass?"}
    PASS -->|No| FIX["Fix candidate and rerun"]
    PASS -->|Yes| SHADOW["Shadow / parallel run"]
    SHADOW --> SHADOWOK{"Operational and quality signals acceptable?"}
    SHADOWOK -->|No| FIX
    SHADOWOK -->|Yes| CANARY["Small canary cohort"]
    CANARY --> SAFE{"Canary guardrails pass?"}
    SAFE -->|No| ROLLBACK["Abort / rollback"]
    SAFE -->|Yes| RAMP["Increase traffic in stages"]
    RAMP --> AB["Controlled A/B or full promotion"]
    AB --> DECIDE{"Experiment decision"}
    DECIDE -->|Benefit and guardrails pass| PROMOTE["Promote candidate"]
    DECIDE -->|Regression / inconclusive| HOLD["Hold, extend or revert"]
~~~

Không phải mọi thay đổi đều cần tất cả các bước. Một chỉnh sửa copy nhỏ có thể dùng canary đơn giản; thay model lớn, prompt có tool instructions hoặc retriever/index cần kiểm tra offline, shadow và canary kỹ hơn.

| Loại thay đổi | Bước nên ưu tiên | Lý do |
| --- | --- | --- |
| Prompt template | Offline replay, shadow, canary | Có thể thay đổi response style, refusal và tool selection |
| Model/provider revision | Shadow, canary, A/B | Latency, cost, quality và serving behavior có thể khác |
| Retriever/index/corpus | Replay retrieval, shadow, canary | Evidence selection có thể đổi |
| Tool schema/implementation | Contract tests, sandbox, canary | Có thể ảnh hưởng quyền và side effects |
| Application runtime/dependency | Deployment canary | Có thể gây lỗi ngoài tầng AI |
| Feature flag/policy | Cohort rollout và audit | Cần kiểm tra đúng nhóm được áp dụng |

## 4. Tách application rollout khỏi model/prompt experiment

Một ứng dụng có thể deploy code mới nhưng vẫn dùng model cũ; hoặc cùng một build có thể route tới hai model. Nếu thay đồng thời application build, prompt, model và tool schema, rất khó xác định nguyên nhân khi quality thay đổi.

Nên theo dõi hai trục:

1. **Deployment version:** application build, dependency, container image, infrastructure config.
2. **AI pipeline version:** prompt, model/provider, generation parameters, retriever/index, tool registry và policy.

| Deployment | AI pipeline | Ý nghĩa |
| --- | --- | --- |
| Build A | Pipeline 1 | Control hiện tại |
| Build B | Pipeline 1 | Kiểm tra runtime change |
| Build A | Pipeline 2 | Kiểm tra AI config change |
| Build B | Pipeline 2 | Candidate kết hợp |

Nếu thay đổi cần đi cùng nhau, xem tổ hợp là một candidate release và đánh giá như một đơn vị. Giữ manifest để biết mỗi interaction đã dùng build và pipeline nào.

## 5. Xác định đơn vị assignment

Đơn vị assignment là đối tượng được gán vào control hoặc candidate. Chọn sai đơn vị có thể làm một người dùng thấy behavior thay đổi liên tục hoặc làm các mẫu trong experiment phụ thuộc nhau.

| Unit | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| User/account | Trải nghiệm cần ổn định qua nhiều conversation | User có nhiều người dùng chung account |
| Conversation/session | Memory và context phụ thuộc lịch sử hội thoại | Một user có thể trải nghiệm cả hai arm ở các session khác |
| Interaction/request | Request độc lập, không phụ thuộc history | Một conversation có thể đổi variant giữa các lượt |
| Tenant/organization | Policy hoặc dữ liệu dùng chung theo tenant | Số tenant ít, statistical power thấp |
| Region/cluster | Kiểm tra deployment hoặc infrastructure | Cohort khác nhau và dễ confounding |

### 5.1. Giữ assignment ổn định

Nếu model/prompt thay đổi giữa các lượt trong cùng conversation, memory được tạo từ control có thể bị candidate sử dụng hoặc ngược lại. Điều này làm kết quả bị nhiễm chéo.

Với conversational assistant, thường nên gán theo conversation hoặc account và giữ assignment đến khi conversation kết thúc. Nếu user có nhiều conversation nhưng trải nghiệm phải nhất quán, gán theo account.

Lưu assignment ở server-side store hoặc tính deterministic từ stable pseudonymous unit ID. Không gán lại variant mỗi request bằng random number mới.

### 5.2. Anonymous users và identity merge

Với anonymous traffic, có thể dùng session identifier first-party có TTL. Khi user đăng nhập và identity được merge, cần một rule rõ:

- Giữ variant đã dùng trong session hiện tại.
- Gán theo account cho conversation mới.
- Ghi identity merge event.
- Không thay assignment giữa một conversation đang chạy.

Không đưa email, phone number hoặc raw user ID vào metric labels.

### 5.3. Stratification

Nếu task family hoặc language ảnh hưởng quality mạnh, có thể stratify trước khi randomize. Ví dụ, tạo assignment độc lập trong từng nhóm RAG/direct chat hoặc vi/en để hai arm có cohort mix gần nhau.

Không chia quá nhiều strata khiến mỗi nhóm quá nhỏ. Chỉ stratify theo các dimensions được xác định trước và có volume đủ.

## 6. Gán variant ổn định bằng hash

Một cách đơn giản là hash experiment ID và pseudonymous unit ID thành bucket từ 0 đến 9.999. Với split 50/50, bucket 0–4.999 là control và 5.000–9.999 là candidate.

~~~java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;

public final class VariantAssigner {

    public enum Variant {
        CONTROL, CANDIDATE
    }

    public record Assignment(
            String experimentId,
            String assignmentUnitRef,
            int bucket,
            Variant variant,
            String allocationVersion) {
    }

    private final byte[] secretKey;

    public VariantAssigner(byte[] secretKey) {
        this.secretKey = secretKey.clone();
    }

    public Assignment assign(
            String experimentId,
            String pseudonymousUnitId,
            int candidatePercent,
            String allocationVersion) {

        if (candidatePercent < 0 || candidatePercent > 100) {
            throw new IllegalArgumentException("Invalid candidate percentage");
        }

        String key = experimentId + ":" + pseudonymousUnitId;
        int bucket = stableBucket(key);

        Variant variant = bucket < candidatePercent * 100
                ? Variant.CANDIDATE
                : Variant.CONTROL;

        return new Assignment(
                experimentId,
                pseudonymousUnitId,
                bucket,
                variant,
                allocationVersion);
    }

    private int stableBucket(String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secretKey, "HmacSHA256"));
            byte[] digest = mac.doFinal(
                    value.getBytes(StandardCharsets.UTF_8));

            return new BigInteger(1, digest)
                    .mod(BigInteger.valueOf(10_000))
                    .intValueExact();
        }
        catch (Exception ex) {
            throw new IllegalStateException(
                    "Cannot compute experiment bucket", ex);
        }
    }
}
~~~

Đây là implementation minh họa. Secret key phải được quản lý bởi secret manager và version hóa; không log key. assignmentUnitRef nên là opaque/pseudonymous reference. Nếu cần audit hoặc key rotation, lưu assignment record bền vững thay vì chỉ tính lại từ key mới.

### 6.1. Điều chỉnh tỷ lệ candidate

Trong ví dụ trên, candidatePercent = 5 nghĩa là 5% bucket được gán candidate. Tăng lên 10% sẽ thêm bucket mới nếu cùng experiment ID, unit ID và key version. Tuy nhiên, nếu thay key, allocation algorithm hoặc experiment ID, assignment có thể thay đổi.

Không thay allocationVersion giữa experiment mà không tạo event/version mới. Với A/B đã bắt đầu, không tự ý đổi tỷ lệ giữa hai arm vì có thể làm hỏng randomization và diễn giải thống kê.

### 6.2. Persist assignment

Assignment record nên gồm:

~~~json
{
  "experimentId": "prompt-quality-2026-11",
  "assignmentUnitRef": "unit-opaque-72",
  "variant": "CANDIDATE",
  "bucket": 7214,
  "allocationVersion": "allocation-v2",
  "assignedAt": "2026-11-27T12:00:00Z",
  "expiresAt": "2026-12-27T12:00:00Z"
}
~~~

Record là ví dụ. Không lưu raw account identifier hoặc PII nếu opaque reference là đủ. Assignment store cần unique key theo experiment + unit để chống race và duplicate.

## 7. Assignment, exposure và treatment thực tế

Gán variant chưa có nghĩa candidate đã được chạy. Request có thể bị cache, bị reject trước model call, hoặc fallback về control do candidate provider timeout.

Phân biệt:

- **Assigned:** unit được phân vào variant.
- **Eligible:** interaction đủ điều kiện theo experiment scope.
- **Exposed:** candidate/control thực sự nhận request thuộc experiment.
- **Completed:** model operation hoàn tất và có response/status.
- **Fallback:** request được route sang variant khác với assignment.
- **Evaluated:** interaction có kết quả evaluator/human review.

~~~mermaid
flowchart LR
    A["Assignment"] --> E["Eligible request"]
    E --> X["Exposure event"]
    X --> C{"Model call"}
    C -->|Assigned model| DONE["Completed"]
    C -->|Fallback| FB["Fallback event"]
    DONE --> EV["Evaluation"]
    FB --> EV
~~~

Lưu các event với experiment ID, variant, assignment version, actual provider/model, exposure timestamp và outcome status.

### 7.1. Intention-to-treat và actual exposure

Khi phân tích A/B, primary analysis thường nên giữ unit theo nhóm được assign ban đầu (intention-to-treat). Nếu candidate lỗi và fallback về control, interaction vẫn thuộc treatment assignment. Nếu chỉ loại các request fallback ra khỏi treatment, bạn có thể tạo selection bias vì fallback thường xảy ra ở những request khó hoặc lúc hệ thống bất ổn.

Báo thêm actual exposure và fallback rate để hiểu mức độ tuân thủ treatment. Per-protocol analysis có thể hữu ích như phân tích phụ, nhưng không thay thế ITT.

### 7.2. Không dùng assignment event làm denominator cho mọi metric

Ví dụ, model latency chỉ tính trên model calls thực sự được bắt đầu; user task success có thể tính trên eligible assigned units; evaluator pass rate tính trên cases đã có nhãn. Mỗi metric cần định nghĩa denominator rõ.

## 8. Route tới nhiều ChatModel/ChatClient trong Spring AI

Spring AI cho phép tạo ChatClient từ ChatModel. Một ứng dụng có thể tạo nhiều ChatClient gắn với các model khác nhau, sau đó chọn client theo assignment.

### 8.1. Khai báo hai ChatClient

~~~java
@Configuration
public class ChatClientConfiguration {

    @Bean
    @Qualifier("controlChatClient")
    ChatClient controlChatClient(
            @Qualifier("controlChatModel") ChatModel controlModel) {
        return ChatClient.builder(controlModel).build();
    }

    @Bean
    @Qualifier("candidateChatClient")
    ChatClient candidateChatClient(
            @Qualifier("candidateChatModel") ChatModel candidateModel) {
        return ChatClient.builder(candidateModel).build();
    }
}
~~~

Tên bean controlChatModel và candidateChatModel là ví dụ; cần khai báo provider/model configuration tương ứng trong ứng dụng. Nếu dùng cùng provider với hai deployment khác nhau, cấu hình hai ChatModel riêng hoặc một gateway router có versioned route.

### 8.2. Chọn client theo assignment

~~~java
@Service
public class ExperimentChatService {

    private final ChatClient controlClient;
    private final ChatClient candidateClient;
    private final AssignmentService assignments;
    private final ExposureRecorder exposures;

    public ExperimentChatService(
            @Qualifier("controlChatClient") ChatClient controlClient,
            @Qualifier("candidateChatClient") ChatClient candidateClient,
            AssignmentService assignments,
            ExposureRecorder exposures) {
        this.controlClient = controlClient;
        this.candidateClient = candidateClient;
        this.assignments = assignments;
        this.exposures = exposures;
    }

    public String answer(AssistantRequest request) {
        Assignment assignment = assignments.assign(
                request.experimentId(),
                request.assignmentUnitRef());

        ChatClient selected = assignment.variant()
                == Variant.CANDIDATE
                ? candidateClient
                : controlClient;

        exposures.recordStarted(
                request.interactionId(),
                assignment);

        try {
            String answer = selected.prompt()
                    .system(request.systemPrompt())
                    .user(request.userText())
                    .call()
                    .content();

            exposures.recordCompleted(
                    request.interactionId(),
                    assignment);
            return answer;
        }
        catch (RuntimeException ex) {
            exposures.recordFailed(
                    request.interactionId(),
                    assignment,
                    ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
~~~

Đây là skeleton minh họa. AssistantRequest cung cấp experimentId và assignmentUnitRef đã được tạo theo unit policy. AssignmentService là wrapper đọc experiment configuration (candidatePercent, allocationVersion và secret-key version), gọi VariantAssigner, persist kết quả theo unique key experiment + unit và kiểm tra eligibility. ExposureRecorder nên ghi event qua transactional outbox hoặc cơ chế bền vững; không để lỗi ghi telemetry làm thay đổi kết quả model call ngoài policy đã định.

### 8.3. Fallback có kiểm soát

Nếu candidate model lỗi, fallback sang control có thể giữ availability nhưng cần:

- Ghi assignedVariant = CANDIDATE.
- Ghi actualVariant/model = CONTROL.
- Ghi fallbackReason và retry count.
- Không ghi candidate như thể đã phục vụ thành công.
- Phân tích fallback rate như một guardrail.
- Không thay assignment ban đầu trong A/B analysis.

Với canary, fallback rate cao là tín hiệu candidate chưa ổn định. Với A/B, fallback có thể làm giảm treatment compliance và cần được báo cáo.

## 9. Thiết kế traffic ramp cho canary

Canary nên có các bước tăng traffic và khoảng quan sát. Một lịch minh họa:

| Giai đoạn | Candidate traffic | Điều kiện trước khi đi tiếp |
| --- | ---: | --- |
| Internal/synthetic | 0% user traffic | Smoke tests và contract checks đạt |
| Canary 1 | 1% | Không có critical errors; đủ exposure tối thiểu |
| Canary 2 | 5% | Availability, latency, cost và quality trong guardrails |
| Canary 3 | 10–25% | Không có regression theo task family quan trọng |
| Canary 4 | 50% | Hệ thống ổn định qua peak/off-peak phù hợp |
| Full rollout | 100% | Owner phê duyệt và rollback path sẵn sàng |

Các tỷ lệ là ví dụ, không phải mặc định. Với traffic nhỏ, 1% có thể tạo quá ít samples; với tool hoặc policy rủi ro cao, 1% vẫn có thể quá rộng. Có thể bắt đầu bằng một tenant nội bộ hoặc allowlist.

### 9.1. Pause giữa các bước

Không tăng traffic chỉ vì đã hết một khoảng thời gian. Chỉ promote khi:

- Đủ số exposure hợp lệ.
- Metric window hoàn chỉnh.
- Không có guardrail violation.
- Quality labels đủ mature hoặc có proxy signals đáng tin.
- Không có incident chưa giải quyết.
- Người chịu trách nhiệm đã xem kết quả.

Nếu volume thấp, có thể cần kéo dài thời gian quan sát. Nếu volume cao, vẫn phải bảo đảm có đủ thời gian để thấy các chu kỳ traffic và delayed outcomes liên quan.

### 9.2. Dùng metric analysis tự động

Một progressive delivery controller có thể query Prometheus hoặc provider metrics và tự động pause/abort theo AnalysisRun. Argo Rollouts hỗ trợ canary steps, weighted traffic, pause và analysis; controller có thể abort rollout khi analysis thất bại. Đây là ví dụ hạ tầng; ứng dụng Spring AI vẫn cần tự export quality metrics và experiment metadata phù hợp.

## 10. Guardrails: quyết định tiếp tục, pause hay rollback

Không dùng một quality score duy nhất. Guardrails nên bao gồm cả operational health và product quality.

| Dimension | Metric gợi ý | Ví dụ guardrail |
| --- | --- | --- |
| Availability | Model call success, HTTP 5xx, timeout | Không vượt error budget |
| Latency | p95/p99, TTFT, stream duration | Không tăng quá mức đã chấp thuận |
| Cost | Cost/request, tokens/request | Không vượt budget |
| Relevance | Human-calibrated relevance pass | Không giảm quá non-inferiority margin |
| Factuality | Fact-check defect rate | Không tăng critical unsupported claims |
| RAG | Empty retrieval, recall@K, citation coverage | Không làm giảm evidence quality |
| Tools | Tool success, invalid arguments, side-effect errors | Không tăng lỗi execution |
| Safety | Refusal correctness, policy violations | Không có critical safety regression |
| User outcome | Task completion, correction, complaint | Không suy giảm theo cohort |

### 10.1. Guardrail cần định nghĩa trước

Mỗi guardrail cần có:

- Metric name và unit.
- Population/denominator.
- Cohort và dimension.
- Aggregation window.
- Minimum sample count.
- Threshold hoặc non-inferiority margin.
- Owner và action khi vi phạm.
- Quy tắc xử lý missing/late data.

Ví dụ: relevance pass rate candidate không thấp hơn control quá 1 điểm phần trăm, với confidence interval đã định nghĩa. Threshold phải dựa trên baseline và mức rủi ro của sản phẩm, không sao chép một số chung.

### 10.2. Immediate stop và statistical stop

Một số điều kiện cần dừng ngay, không chờ đủ sample:

- Data leak hoặc cross-tenant exposure.
- Tool side effect sai hoặc unauthorized.
- Critical safety/policy violation.
- Candidate trả dữ liệu bí mật.
- Provider/model outage gây mất khả năng phục vụ.

Các metric mềm như relevance pass rate có thể cần đủ mẫu và confidence interval. Không rollback chỉ vì một vài case xấu nếu chưa hiểu variance, trừ khi case đó thuộc nhóm critical đã định nghĩa.

### 10.3. Non-inferiority và improvement

Một canary có thể chỉ cần chứng minh candidate không làm quality xấu đi quá mức cho phép. A/B experiment có thể kiểm tra candidate cải thiện primary metric.

Đặt margin trước khi chạy:

- Non-inferiority: candidate không kém control quá margin Δ.
- Superiority: candidate cải thiện hơn control theo hướng đã xác định.
- Equivalence: khác biệt nằm trong khoảng ±Δ, nếu mục tiêu là chứng minh hai variant tương đương.

Không chọn margin sau khi đã xem kết quả.

## 11. Shadow/parallel run an toàn

Shadow run rất hữu ích cho AI vì cùng một input có thể tạo output khác nhau theo model/prompt. Tuy nhiên, shadow candidate có thể thực thi tool hoặc ghi memory nếu cấu hình không kiểm soát.

### 11.1. Không chạy side effect hai lần

Với tool có side effect như tạo đơn hàng, gửi email, thanh toán, xóa dữ liệu hoặc cập nhật hồ sơ:

- Tắt tool execution ở shadow candidate; chỉ quan sát tool-call proposal.
- Hoặc thay tool bằng stub/mock trả fixture.
- Hoặc dùng sandbox với dataset và credentials riêng.
- Không gửi lại lệnh thật chỉ để so sánh output.
- Không để candidate gọi API write qua cùng identity production.

Nếu mục tiêu là so tool selection, có thể đánh giá tool name/arguments trên proposal đã redaction mà không thực thi. Nếu mục tiêu là kiểm tra implementation, dùng sandbox hoặc contract tests.

### 11.2. Tách session memory

Không để shadow candidate ghi vào memory đang phục vụ user. Dùng session namespace riêng hoặc memory adapter read-only. Nếu candidate cần history, lấy immutable snapshot tại thời điểm interaction rồi truyền cho candidate.

Nếu dùng Spring AI session advisors, mỗi ChatClient call có thể đi qua advisor chain để đọc/ghi session. Cần cấu hình riêng để shadow execution không ghi vào production session.

### 11.3. Bảo vệ dữ liệu và chi phí

Shadow tạo thêm model calls, token usage và evidence copies. Cần:

- Sampling rate và budget.
- Rate limit riêng cho shadow provider.
- Redaction và tenant isolation.
- Retention cho candidate outputs.
- Async queue để không tăng latency user path.
- Circuit breaker khi shadow service quá tải.
- Không export raw prompt/completion vào metrics/traces mặc định.

### 11.4. Shadow comparison

Lưu kết quả control/candidate gắn cùng interaction snapshot:

~~~json
{
  "comparisonId": "cmp-01JABC",
  "interactionRef": "interaction-opaque",
  "control": {
    "modelRevision": "model-a",
    "responseRef": "response-control"
  },
  "candidate": {
    "modelRevision": "model-b",
    "responseRef": "response-candidate",
    "executionMode": "SHADOW_NO_TOOLS"
  },
  "evaluatorVersion": "judge-v4",
  "rubricVersion": "quality-v7",
  "comparisonStatus": "READY"
}
~~~

Không so exact string đơn thuần. Đánh giá theo relevance, groundedness, completeness, format, tool proposal, latency, tokens và cost. Với response pair, có thể dùng blind pairwise human review với thứ tự A/B được randomize.

## 12. Thiết kế A/B experiment cho prompt/model

### 12.1. Viết hypothesis và estimand

Một hypothesis tốt xác định thay đổi, population, outcome và mức cải thiện mong đợi.

Ví dụ:

“Trên các conversation thuộc task family RAG_QA trong giai đoạn thử nghiệm, candidate model B tăng relevance pass rate so với model A ít nhất 2 điểm phần trăm, trong khi fact-check defect rate không tăng và p95 latency không vượt guardrail.”

Estimand cần nêu rõ đơn vị: per assigned conversation, per eligible interaction hay per completed model call. Chọn theo câu hỏi sản phẩm.

### 12.2. Chọn primary metric

Primary metric nên gắn với mục tiêu chính:

- Relevance pass rate theo human-calibrated evaluator.
- Task completion rate.
- Factuality defect rate.
- Correct tool execution rate.
- User correction rate nếu định nghĩa rõ.

Không chọn quá nhiều primary metrics rồi chỉ báo metric thuận lợi. Các metric khác là secondary hoặc guardrails.

### 12.3. Đặt guardrails độc lập

A/B có thể cải thiện relevance nhưng tăng latency, cost hoặc tool errors. Guardrails cần được định nghĩa trước và có thể chặn promotion dù primary metric tăng.

### 12.4. Randomize đúng đơn vị

- Gán theo conversation nếu memory/state phụ thuộc history.
- Gán theo user/account nếu cần trải nghiệm nhất quán xuyên session.
- Gán theo tenant nếu config hoặc business data được chia sẻ ở cấp tenant.
- Tránh gán theo từng token hoặc từng model call bên trong một tool loop.

Giữ cùng assignment trong toàn bộ interaction. Không để model generation đầu dùng control nhưng tool continuation dùng candidate.

## 13. Sample size và statistical power

Một kết quả A/B không có ý nghĩa chỉ vì candidate score cao hơn control trên vài chục case. Cần tính sample size theo baseline rate, MDE, significance level và statistical power.

Với hai nhóm có kích thước bằng nhau, outcome nhị phân và normal approximation, một công thức gần đúng là:

\[
n_{\text{per arm}} \approx
\frac{2(z_{1-\alpha/2}+z_{1-\beta})^2\bar p(1-\bar p)}
{\delta^2}
\]

Trong đó:

- α là false-positive rate cho kiểm định hai phía.
- 1−β là statistical power.
- \(\bar p\) là tỷ lệ trung bình dự kiến giữa hai arm.
- δ là absolute difference tối thiểu cần phát hiện.
- n là số independent units mỗi arm.

Ví dụ: baseline 90%, muốn phát hiện tăng lên 92%, α = 0,05, power = 0,80. Với \(\bar p \approx 0,91\), δ = 0,02 và z values xấp xỉ 1,96 và 0,84, cần khoảng 3.200 independent units mỗi arm theo phép tính gần đúng.

Đây chỉ là ước lượng ban đầu. Dùng power analysis phù hợp với outcome, allocation ratio, clustering và multiple comparisons thực tế. Với lỗi hiếm, cần phương pháp chính xác hơn hoặc theo dõi defect counts trên sample lớn hơn.

### 13.1. Cluster assignment và repeated interactions

Nếu randomize theo user nhưng mỗi user có nhiều conversations, outcomes có thể tương quan trong cùng user. Sample size hiệu dụng nhỏ hơn số interactions.

Một design effect gần đúng cho cluster sampling:

\[
DE = 1 + (m-1)\rho
\]

Trong đó m là số observations trung bình mỗi cluster và ρ là intraclass correlation. Cần tăng sample size hoặc dùng phân tích cluster-robust/hierarchical phù hợp.

Nếu randomize theo conversation nhưng user có nhiều conversations ở cả hai arm, user có thể bị contamination do học hoặc hành vi thay đổi. Chọn unit theo cơ chế tác động của treatment.

### 13.2. Chờ đủ label maturity

Evaluator/human review có thể đến muộn. Không kết luận candidate tốt hơn chỉ vì candidate có nhiều case đã được chấm sớm hơn control. So sánh trên cùng maturity horizon và hiển thị label coverage theo arm.

## 14. Sample ratio mismatch và kiểm tra randomization

Nếu thiết kế 50/50 nhưng quan sát 70/30, cần điều tra trước khi diễn giải quality metrics.

Sample Ratio Mismatch (SRM) có thể đến từ:

- Assignment bug hoặc hashing không ổn định.
- Một arm lỗi sớm trước exposure logging.
- Cache hoặc routing bỏ qua assignment.
- User/session identity không nhất quán.
- Filter eligibility khác nhau giữa hai arm.
- Event ingestion bị mất theo variant.
- Candidate timeout khiến exposure event không được ghi.

Có thể dùng chi-square goodness-of-fit để so observed assignment counts với expected allocation. Với hai arm 50/50, expected count mỗi arm là N/2. Kiểm tra theo assignment population, không chỉ completed calls.

Nếu SRM vượt ngưỡng kiểm tra đã đặt, dừng phân tích và tìm nguyên nhân. Không sửa counts hoặc bỏ nhóm bị lệch để làm tỷ lệ trông cân bằng.

## 15. Sequential monitoring và stopping rules

Nếu liên tục xem p-value sau mỗi vài phút rồi dừng ngay khi p < 0,05, false-positive rate thực tế sẽ cao hơn mức đã định nghĩa. Hãy lập kế hoạch trước:

- Fixed horizon: chốt sample size và kết thúc khi đạt đủ.
- Group sequential: quy định số lần interim analysis và alpha spending.
- Bayesian monitoring: định nghĩa prior, decision threshold và stopping rule.
- Guardrail stop: dừng ngay khi xảy ra critical harm, độc lập với primary significance.

Không dừng sớm vì candidate đang có vẻ tốt nếu chưa dùng phương pháp sequential được thiết kế trước. Không tiếp tục một candidate nguy hiểm chỉ để đủ sample size.

## 16. Phân tích kết quả theo đúng population

Báo cáo cần có:

- Assigned counts theo arm.
- Eligible counts và exposed counts.
- Completed calls và fallback counts.
- Evaluation/human label coverage.
- Primary outcome và confidence interval.
- Guardrail metrics.
- Cohort breakdown theo task family, language, RAG/tool usage.
- Cost, latency và token usage.
- Missingness, late labels và SRM status.
- Experiment version và analysis code/version.

### 16.1. Intention-to-treat là phân tích chính

Giữ unit theo assigned variant, kể cả khi candidate fallback. Báo thêm actual model exposure để hiểu compliance. Không loại interaction lỗi khỏi treatment arm vì sẽ làm candidate trông tốt hơn.

### 16.2. Không gộp task mix khác nhau

Nếu candidate nhận nhiều câu hỏi RAG khó hơn, raw overall relevance có thể thấp hơn dù trong từng cohort candidate tốt hơn. So sánh theo strata và nếu cần standardize theo baseline traffic mix đã định trước.

### 16.3. Multiple comparisons

Nếu kiểm tra nhiều prompt variants, nhiều models và nhiều metrics, xác suất tìm thấy một kết quả “có ý nghĩa” do ngẫu nhiên tăng. Chọn primary metric, giới hạn số hypothesis chính hoặc dùng correction/experiment design phù hợp. Không cherry-pick subgroup sau khi xem kết quả.

### 16.4. Đánh giá bằng cùng evaluator

Nếu dùng LLM judge, cùng evaluator model, prompt, rubric và decoding configuration phải áp dụng cho cả hai arm. Blind candidate/control identity khi phù hợp. Giữ random human audit để phát hiện judge bias hoặc evaluator drift.

## 17. Metrics và telemetry theo variant

Các metric dưới đây là ví dụ do ứng dụng tự định nghĩa, không phải metric mặc định Spring AI:

| Metric | Ý nghĩa |
| --- | --- |
| ai_experiment_assignments_total | Số unit được gán theo variant |
| ai_experiment_exposures_total | Số interaction thực sự nhận variant |
| ai_experiment_fallback_total | Số interaction fallback khỏi assigned variant |
| ai_experiment_model_calls_total | Model calls theo actual provider/model |
| ai_experiment_quality_evaluated_total | Số cases có evaluation result |
| ai_experiment_relevance_pass_total | Relevance pass outcomes |
| ai_experiment_factcheck_fail_total | Fact-check failures |
| ai_experiment_task_success_total | Task success outcomes |
| ai_experiment_latency_seconds | Latency theo operation/variant |
| ai_experiment_cost_estimated_total | Estimated cost theo variant |
| ai_experiment_tool_failures_total | Tool execution failures |
| ai_experiment_label_coverage | Label maturity/coverage theo arm |

Dùng labels có cardinality thấp và được kiểm soát như experiment name đang active, variant, provider, model family, task family và operation. Không dùng interactionId, traceId, user ID, prompt, raw response hoặc tool arguments làm metric labels. Chi tiết exposure và outcome cần lưu trong event/analytics store.

### 17.1. Assignment ratio

~~~promql
sum by (experiment, variant) (
  increase(ai_experiment_assignments_total[1h])
)
~~~

So observed counts với expected allocation. Đây là metric để kiểm tra assignment, không thay thế SRM test trên đúng population và time window.

### 17.2. Fallback rate

~~~promql
sum by (experiment, variant) (
  rate(ai_experiment_fallback_total[15m])
)
/
sum by (experiment, variant) (
  rate(ai_experiment_exposures_total[15m])
)
~~~

Mẫu số cần được định nghĩa nhất quán. Nếu fallback được ghi trước exposure, dùng eligible/attempted routing denominator riêng.

### 17.3. Relevance pass rate

~~~promql
sum by (experiment, variant) (
  rate(ai_experiment_relevance_pass_total[1h])
)
/
sum by (experiment, variant) (
  rate(ai_experiment_quality_evaluated_total[1h])
)
~~~

Đây là raw evaluated-sample ratio. Nếu sample inclusion probabilities khác nhau hoặc label maturity khác nhau, dùng weighted analysis trong analytics layer thay vì coi query này là population estimate.

### 17.4. Cost theo exposure

~~~promql
sum by (experiment, variant) (
  rate(ai_experiment_cost_estimated_total[1h])
)
/
sum by (experiment, variant) (
  rate(ai_experiment_exposures_total[1h])
)
~~~

Kiểm tra cost estimate đã bao gồm generation, retries, embeddings, reranking và shadow calls đúng phạm vi chưa. Nếu cost metric được ghi ở nhiều operation, không cộng trùng.

## 18. Correlate experiment với Spring AI observations và traces

Spring AI cung cấp ChatClient/ChatModel observations và hỗ trợ metrics/traces cho các operation liên quan. Application layer cần bổ sung experiment metadata để phân tích theo variant.

Nên ghi:

- experiment ID và variant.
- assignment version và exposure status.
- prompt/model/retriever/tool versions.
- requested và actual provider/model.
- fallback reason.
- task family và language ở dạng taxonomy hữu hạn.
- latency, usage và operation outcome.

OpenTelemetry spans có parent/child relationships, attributes, events, links và status. Dùng trace để điều tra một interaction cụ thể; dùng metrics aggregate để so sánh arm. Không đưa unique IDs hoặc raw prompt vào metric labels.

### 18.1. Async evaluation và trace linkage

Nếu evaluation worker chạy sau response:

- Lưu interaction/exposure reference trong event.
- Propagate trace context nếu công việc là continuation của cùng trace.
- Hoặc tạo trace mới và link tới originating span/context.
- Ghi evaluator version và rubric version.
- Không giả định worker span luôn nằm trong cùng trace nếu queue tạo execution boundary.

### 18.2. Đừng để observability làm nhiễm experiment

Nếu candidate bật nhiều logging hơn control, candidate có thể có latency/cost cao chỉ vì telemetry overhead. Giữ instrumentation tương đương giữa arms. Bật debug payload chỉ trong phạm vi nhỏ, có quyền truy cập và retention phù hợp.

## 19. Feature flags và experiment governance

Một experiment registry nên lưu:

- Experiment ID, owner và status.
- Hypothesis và target population.
- Control/candidate config references.
- Assignment unit và allocation.
- Start/end time.
- Primary metric và guardrails.
- MDE, power, sample size và stopping rule.
- Eligibility/exclusion criteria.
- Rubric/evaluator versions.
- Rollback plan và decision log.

Mỗi request cần evaluate feature flag một lần ở boundary thích hợp và lưu assignment cho cả conversation. Không gọi flag service giữa tool loop để đổi variant ở giữa execution.

### 19.1. Không thay đổi treatment giữa chừng

Nếu cần thay prompt hoặc model candidate trong lúc experiment đang chạy, tạo candidate version mới hoặc experiment mới. Không ghi đè config của variant cũ; nếu không, các exposures cùng nhãn variant sẽ thực tế dùng treatment khác nhau.

### 19.2. Kill switch

Có kill switch để dừng candidate ngay khi xảy ra critical failure. Kill switch phải:

- Route new requests về stable.
- Không thay đổi assignment history đã lưu.
- Ghi event abort và reason.
- Giữ candidate logs/evidence cần cho điều tra theo retention.
- Xử lý in-flight requests và session state.
- Có thể khôi phục stable capacity nhanh.

## 20. Rollback và promotion

Một quy trình canary nên có trạng thái rõ:

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Shadow: Offline checks pass
    Shadow --> Canary: Shadow guardrails pass
    Canary --> Paused: Step completed
    Paused --> Canary: Promote traffic step
    Paused --> Aborted: Guardrail violated
    Canary --> Promoted: All steps pass
    Promoted --> [*]
    Aborted --> RolledBack: Stable route restored
    RolledBack --> [*]
~~~

Rollback cần kiểm tra:

- Traffic route trở về stable.
- Stable replicas/model quota còn đủ capacity.
- Candidate không còn nhận traffic mới.
- Conversation assignment không làm session state trộn lẫn.
- Tool side effects đã bắt đầu được xử lý idempotently.
- Queue và async evaluations vẫn giữ provenance.
- Metrics tiếp tục phân biệt candidate đã abort.
- Incident và decision log được lưu.

Không xóa candidate artifacts ngay sau rollback; giữ version reference để replay và tạo regression tests.

## 21. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Randomize mỗi request | Variant đổi trong cùng conversation | Sticky assignment theo user/session |
| Ghi assignment nhưng không ghi exposure | Tưởng candidate đã chạy dù chưa có model call | Tách assignment/exposure/completion |
| Fallback không được ghi | Candidate failure bị che | Ghi assigned và actual variant riêng |
| Chỉ phân tích completed requests | Loại bỏ treatment failures | ITT trên assigned units |
| Shadow chạy tool thật | Side effects lặp | Disable/mock/sandbox tool |
| Shadow ghi live memory | Nhiễm session | Memory namespace riêng/read-only snapshot |
| Candidate có telemetry khác control | So sánh latency/cost không công bằng | Instrumentation tương đương |
| SRM bị bỏ qua | Kết luận experiment sai | Kiểm tra assignment counts trước outcome |
| Xem p-value liên tục | False positive tăng | Predefine stopping rule |
| Đổi evaluator giữa hai arm | Quality score không so sánh được | Cùng evaluator/rubric version |
| Task mix khác nhau | Aggregate bị Simpson's paradox | Stratify và standardize |
| Không đủ label maturity | So sánh lệch theo thời gian | Chờ cùng maturity horizon |
| Chạy nhiều variants không correction | False discovery | Pre-register primary hypotheses |
| Không giữ stable capacity | Rollback chậm | Duy trì rollback capacity |

## 22. Quy trình triển khai end-to-end

1. Chọn candidate change và xác định phạm vi ảnh hưởng.
2. Chạy offline evaluation, regression tests và tool contract tests.
3. Xác định canary, shadow hay A/B theo câu hỏi cần trả lời.
4. Chọn assignment unit phù hợp với memory và user experience.
5. Viết hypothesis, primary metric, guardrails và stopping rule.
6. Tính sample size/MDE và xác định label maturity.
7. Tạo experiment/rollout registry và immutable config references.
8. Implement sticky assignment và persist assignment version.
9. Ghi eligible, exposure, actual model, fallback và completion events.
10. Route control/candidate bằng ChatClient/ChatModel riêng.
11. Shadow candidate trong sandbox/read-only mode nếu cần.
12. Canary theo từng bước, pause và kiểm tra guardrails.
13. Chạy A/B experiment theo random assignment nếu cần causal estimate.
14. Theo dõi SRM, label coverage, quality, latency, cost và tool errors.
15. Phân tích ITT và subgroup theo cohort đã định trước.
16. Promote hoặc rollback theo policy.
17. Giữ evidence, release ledger và decision log.
18. Đưa defect đã xác nhận vào evaluation dataset và regression suite.

## 23. Checklist kiểm thử production

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Cùng user/conversation gửi nhiều requests | Variant không đổi theo assignment unit |
| Assignment key rotation | Assignment record cũ vẫn được giữ và tra cứu |
| Candidate traffic tăng từ 5% lên 10% | Cohort cũ không đổi nếu cùng allocation scheme |
| Candidate provider timeout | Fallback được ghi với assigned/actual variant |
| Request bị cache trước model call | Có assignment nhưng không giả exposure |
| Tool loop có nhiều model calls | Cùng variant trong toàn interaction |
| Shadow candidate nhận traffic copy | Response candidate không được trả cho user |
| Shadow tool có side effect | Tool bị disable/mock/sandbox |
| Shadow memory | Không ghi vào production session |
| Control/candidate instrumentation | Cùng mức telemetry overhead |
| A/B 50/50 | Assignment counts không có SRM đáng kể |
| Assignment và exposure khác nhau | Dashboard hiển thị riêng |
| Candidate failure bị fallback | ITT giữ treatment assignment |
| Labels đến trễ | So sánh trên cùng maturity horizon |
| Judge model đổi | Không trộn evaluator versions trong primary metric |
| Sample size chưa đủ | Không promote chỉ dựa trên score dao động |
| Critical safety/tool incident | Kill switch dừng candidate ngay |
| Rollback | Stable route và capacity hoạt động |
| Experiment kết thúc | Assignment, exposure, decision và evidence được lưu |

## 24. Bài tập thực hành

### Bài 1. Canary cho prompt version

Tạo control prompt và candidate prompt. Route 1% traffic vào candidate, theo dõi relevance, latency, cost và fallback. Mô phỏng lỗi candidate và kiểm tra rollback.

### Bài 2. Shadow model comparison

Gửi cùng input snapshot tới hai ChatClient. Candidate không được trả response cho user. So output bằng cùng evaluator/rubric và lưu comparison record.

### Bài 3. Sticky assignment

Implement VariantAssigner bằng HMAC. Gửi nhiều request cùng conversation và xác minh variant ổn định. Rotate key rồi kiểm tra assignment record cũ không bị thay đổi.

### Bài 4. Tool-safe shadow

Tạo một tool có side effect. Chạy candidate ở shadow mode với tool stub và fixture result. Xác minh không có lệnh write nào tới hệ thống production.

### Bài 5. A/B sample size

Chọn baseline relevance 90%, MDE 2 điểm phần trăm, alpha 0,05 và power 80%. Tính sample size gần đúng mỗi arm; sau đó điều chỉnh nếu assignment theo user có repeated interactions.

### Bài 6. SRM investigation

Tạo tình huống expected 50/50 nhưng observed 60/40. Dùng chi-square goodness-of-fit và điều tra assignment, exposure logging, fallback và event loss.

### Bài 7. ITT và fallback

Tạo candidate có tỷ lệ timeout 5% và fallback về control. Tính outcome theo assigned arm và actual exposure; giải thích vì sao loại fallback khỏi treatment có thể gây bias.

### Bài 8. Sequential stopping

Viết stopping rule trước khi experiment chạy. Phân biệt immediate critical stop, fixed-horizon analysis và group-sequential interim analysis.

### Bài 9. Canary dashboard

Tạo dashboard theo experiment/variant gồm assignment, exposure, fallback, quality, p95 latency, token usage, cost và tool failures. Hiển thị sample count và label coverage.

## 25. Tổng kết

Canary và so sánh song song giúp đưa thay đổi AI vào production có kiểm soát:

- Canary giới hạn blast radius và tăng traffic theo các bước có guardrails.
- Shadow/parallel run quan sát candidate mà không phục vụ response cho user; cần bảo vệ tool side effects và session memory.
- A/B experiment randomize unit để ước lượng tác động, cần hypothesis, sample size, power và stopping rule.
- Assignment unit phải phù hợp với conversation state; assignment cần ổn định.
- Ghi riêng assignment, exposure, actual model, fallback và completion.
- ITT là phân tích chính khi treatment có fallback hoặc non-compliance.
- Spring AI hỗ trợ tạo nhiều ChatClient từ ChatModel; application layer chịu trách nhiệm routing và experiment assignment.
- Guardrails phải bao gồm availability, latency, cost, relevance, fact checking, RAG, tool correctness và safety.
- Kiểm tra SRM, label maturity, task mix, evaluator version và multiple comparisons.
- Traces phục vụ điều tra từng execution; metrics aggregate phục vụ quyết định rollout.
- Rollback cần stable capacity, kill switch, session consistency và decision log.

Mục tiêu là biến một thay đổi prompt/model/pipeline thành rollout có giả thuyết, assignment, exposure, guardrails và bằng chứng rõ ràng. Khi candidate được thử trong phạm vi phù hợp và có cách dừng an toàn, nhóm phát triển có thể học từ traffic thật mà vẫn kiểm soát tác động lên người dùng.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html): tạo ChatClient từ ChatModel, sử dụng nhiều chat models và advisor chains.
- [Spring AI 2.1.0 Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): observations, metrics và traces cho các AI operations.
- [Argo Rollouts — Canary Deployment Strategy](https://argo-rollouts.readthedocs.io/en/stable/features/canary/): weighted traffic, rollout steps, pause, analysis và abort.
- [Argo Rollouts — Analysis and Progressive Delivery](https://argo-rollouts.readthedocs.io/en/latest/features/analysis/): AnalysisRuns, experiments và điều khiển promotion/abort.
- [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/): spans, parent relationships, attributes, events, links và status.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): nối trace context giữa services và processes.
