# Viết evaluator nghiệp vụ có kiểm tra xác định

> **Chương:** Thực hành tổng hợp  
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt evaluator dùng LLM-as-a-judge với evaluator kiểm tra theo quy tắc nghiệp vụ xác định.
2. Xác định những tiêu chí có thể kiểm tra bằng phép so sánh, allowlist, schema, thời hạn và điều kiện rõ ràng.
3. Tạo output có cấu trúc để evaluator kiểm tra từng fact thay vì đoán ý từ văn xuôi tự do.
4. Viết lớp Evaluator tùy chỉnh theo Spring AI, dùng EvaluationRequest và EvaluationResponse.
5. Đối chiếu giá trị, đơn vị, phạm vi, required facts, citation IDs và hành vi abstention với bộ quy tắc có version.
6. Phân biệt lỗi output, vi phạm chính sách và lỗi hạ tầng evaluation; không biến lỗi kỹ thuật thành kết luận factual.
7. Kết hợp hard business gates với relevance/fact-checking judge ở bước phù hợp.
8. Viết unit tests xác định, lưu metadata và theo dõi regression theo phiên bản rule set.

## 1. Vì sao cần evaluator nghiệp vụ xác định?

LLM-as-a-judge hữu ích khi tiêu chí cần hiểu ngữ nghĩa: câu trả lời có đi đúng ý người dùng không, một claim có được diễn đạt tương đương với tài liệu không, hoặc câu trả lời có dễ hiểu không. Tuy nhiên, nhiều yêu cầu nghiệp vụ có kết quả đúng/sai rõ ràng:

- Hạn mức chi phí không được vượt con số đã phê duyệt.
- Đơn vị tiền tệ phải đúng.
- Ngày làm việc không được nhầm với ngày theo lịch.
- Một hồ sơ phải có đủ trường bắt buộc.
- Citation phải trỏ tới một tài liệu thực sự nằm trong context của lần chạy.
- Khi thiếu căn cứ, hệ thống phải trả về hành động abstain/clarify.

Những điều kiện này không cần model phán đoán. Chúng nên được kiểm tra bằng code thông thường để có kết quả lặp lại, giải thích được và dễ kiểm thử.

### Hai loại evaluator bổ sung nhau

| Loại | Cách quyết định | Phù hợp với |
| --- | --- | --- |
| Deterministic business evaluator | So sánh kiểu dữ liệu, rule, ngưỡng, allowlist, required fields | Số tiền, đơn vị, ngày, trạng thái, quyền, citation ID, schema |
| LLM-as-a-judge | Model diễn giải query, context và response rồi đưa verdict | Relevance, paraphrase, semantic support, clarity, completeness mang tính ngữ nghĩa |

Không nên yêu cầu LLM quyết định một phép so sánh số học có thể kiểm tra chính xác bằng Java. Ngược lại, không nên dùng một vài phép kiểm tra chuỗi để kết luận một đoạn văn dài có faithful hay không.

## 2. Phân loại tiêu chí trước khi viết code

Trước tiên, lập một decision table cho tiêu chí cần đánh giá:

| Tiêu chí | Kiểm tra xác định? | Cách kiểm tra |
| --- | --- | --- |
| Mức phụ cấp ăn tối đa là 350.000 VND/ngày | Có | So sánh số tiền, currency, period và scope |
| Hạn mức khách sạn là 1.200.000 VND/đêm | Có | So sánh số tiền và phạm vi áp dụng |
| Thời hạn là 10 ngày làm việc | Có | So sánh integer và unit WORKING_DAYS |
| Hồ sơ có hóa đơn/chứng từ hợp lệ | Có nếu output biểu diễn field rõ | Kiểm tra required field/boolean |
| Citation trỏ tới POL-02 | Có | ID citation phải thuộc actual retrieved document IDs |
| Câu trả lời có giải thích dễ hiểu | Không hoàn toàn | Rubric/human review hoặc LLM judge |
| Câu trả lời có thực sự trả lời ý định câu hỏi | Thường không | RelevancyEvaluator và kiểm tra nghiệp vụ bổ sung |
| Một câu diễn đạt có đồng nghĩa với policy không | Không hoàn toàn | LLM judge hoặc reviewer |

### Hard gate và soft score

- **Hard gate:** vi phạm thì case không đạt, ví dụ sai hạn mức, sai currency, thiếu chứng từ bắt buộc, citation không tồn tại.
- **Soft score:** có thể đánh giá theo mức độ, ví dụ cách diễn đạt, độ rõ ràng hoặc mức hữu ích.

Không cộng điểm văn phong để bù cho vi phạm hard gate. Một câu trả lời rất trôi chảy nhưng sai số tiền vẫn phải fail.

## 3. Bộ quy tắc nghiệp vụ phải có version

Tiếp tục dùng corpus chính sách công tác hư cấu trong bài trước. Các con số sau chỉ là dữ liệu học tập:

| Rule key | Giá trị chuẩn | Đơn vị | Phạm vi | Nguồn |
| --- | ---: | --- | --- | --- |
| meal_allowance | 350.000 | VND/ngày | Công tác nội địa | POL-01 |
| hotel_cap | 1.200.000 | VND/đêm | Công tác nội địa | POL-03 |
| settlement_deadline | 10 | Ngày làm việc sau khi kết thúc chuyến đi | Công tác nội địa | POL-02 |
| receipt_required | true | Boolean | Hồ sơ quyết toán | POL-04 |

Trong ứng dụng thật, rule set cần được quản lý như dữ liệu nghiệp vụ có nguồn gốc:

- ruleSetVersion hoặc policy version.
- Ngày bắt đầu và kết thúc hiệu lực.
- Đơn vị sở hữu/quy trình phê duyệt.
- Nguồn tài liệu và checksum.
- Quy tắc chuyển đổi đơn vị, rounding và timezone nếu liên quan.

Không hardcode các con số rải rác trong evaluator. Hãy inject một rule catalog bất biến theo version để kết quả của lần chạy cũ có thể tái lập.

### Model không phải nguồn chuẩn của rule

Model có thể đề xuất facts từ context, nhưng evaluator phải so sánh với rule catalog tin cậy do ứng dụng cung cấp. Không lấy mức tiền từ candidate answer, metadata do model sinh hoặc tài liệu không được xác thực rồi dùng chính giá trị đó làm chuẩn để chấm.

## 4. Định nghĩa output contract có cấu trúc

Một evaluator xác định không nên phải đoán con số từ câu văn tự do. Định nghĩa output contract mà generator phải trả về:

```json
{
  "action": "ANSWER",
  "facts": [
    {
      "key": "meal_allowance",
      "value": "350000",
      "unit": "VND_PER_DAY",
      "scope": "DOMESTIC",
      "citations": ["POL-01"]
    }
  ],
  "abstentionReason": null
}
```

Các trường:

| Field | Ý nghĩa |
| --- | --- |
| action | ANSWER, CORRECT_PREMISE hoặc ABSTAIN_OR_CLARIFY |
| facts | Các factual assertions có cấu trúc mà câu trả lời muốn đưa ra |
| key | Khóa rule được phép dùng |
| value | Giá trị chuẩn hóa, ví dụ số tiền dạng chuỗi thập phân |
| unit | Đơn vị chuẩn, không phụ thuộc cách diễn đạt tự nhiên |
| scope | Phạm vi áp dụng của fact |
| citations | Các document IDs được dùng để hỗ trợ fact |
| abstentionReason | Lý do khi không đủ căn cứ trả lời |

### Vì sao cần chuẩn hóa unit và scope?

10 days, 10 working days và 10 calendar days không tương đương. 350000 VND per domestic travel day cũng không có nghĩa áp dụng cho công tác quốc tế. Nếu chỉ kiểm tra con số, evaluator có thể chấp nhận câu trả lời sai phạm vi.

### Không để văn xuôi tự do đi vòng qua evaluator

Đối với luồng cần hard guarantees, render câu trả lời cuối từ các facts đã được xác thực hoặc dùng template có kiểm soát. Nếu cho phép model thêm một đoạn văn tự do chứa factual claims ngoài danh sách facts, deterministic evaluator không thể bảo đảm đoạn văn đó không chứa thông tin sai.

Nếu sản phẩm vẫn cần prose tự do, hãy thêm bước claim extraction và LLM fact checking/human review cho phần đó; không tuyên bố deterministic evaluator đã kiểm tra mọi câu chữ.

## 5. Đưa case metadata vào EvaluationRequest

Spring AI EvaluationRequest có ba thành phần: user text, danh sách Document context và response content. Interface Evaluator có một phương thức evaluate(EvaluationRequest) trả về EvaluationResponse.

Ta cần biết case đang chạy yêu cầu action nào và những fact keys nào là bắt buộc. Ví dụ, harness có thể thêm một Document metadata dành riêng cho evaluation vào dataList. Tài liệu này không được đưa cho generator như evidence; nó chỉ được thêm khi gọi evaluator.

```java
import java.util.List;
import java.util.Map;

import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;

final class EvaluationRequestFactory {
static Document evaluationCaseDocument(
        String caseId,
        String expectedAction,
        List<String> requiredFactKeys,
        String ruleSetVersion) {

    return new Document(
            "__evaluation_case__",
            "Evaluation metadata. Not evidence for the answer.",
            Map.of(
                    "evaluation_only", true,
                    "case_id", caseId,
                    "expected_action", expectedAction,
                    "required_fact_keys",
                    String.join(",", requiredFactKeys),
                    "rule_set_version", ruleSetVersion));
}

static EvaluationRequest createEvaluationRequest(
        String question,
        List<Document> actualRetrievedDocuments,
        Document caseMetadata,
        String structuredCandidateAnswer) {

    var evaluatorContext = new java.util.ArrayList<Document>(
            actualRetrievedDocuments);
    evaluatorContext.add(caseMetadata);

    return new EvaluationRequest(
            question, evaluatorContext, structuredCandidateAnswer);
}
}
```

Document hỗ trợ ID tường minh, text và metadata. Metadata của document nên dùng các kiểu đơn giản như string, number hoặc boolean. Evaluator nhận diện document metadata bằng ID reserved và marker evaluation_only; không được coi nó là evidence và không gửi nó vào prompt của generator.

Trong hệ thống có nhiều tenant, đừng để client bên ngoài tự gửi expected_action, required_fact_keys hoặc rule_set_version. Evaluation harness phải lấy các giá trị này từ dataset/run đã được kiểm soát.

## 6. Tạo rule catalog bất biến

Ví dụ Java dùng BigDecimal cho tiền để tránh sai số floating point:

```java
import java.math.BigDecimal;
import java.util.Map;

record BusinessRule(
        String key,
        BigDecimal numericValue,
        String textValue,
        String unit,
        String scope,
        String sourceDocumentId) {}

record BusinessRuleSet(
        String version,
        Map<String, BusinessRule> rules) {}

final class BusinessRuleCatalog {
    static BusinessRuleSet policyDemoV1() {
        return new BusinessRuleSet(
            "policy-demo-v1",
            Map.of(
                    "meal_allowance",
                    new BusinessRule(
                            "meal_allowance",
                            new BigDecimal("350000"),
                            null,
                            "VND_PER_DAY",
                            "DOMESTIC",
                            "POL-01"),
                    "hotel_cap",
                    new BusinessRule(
                            "hotel_cap",
                            new BigDecimal("1200000"),
                            null,
                            "VND_PER_NIGHT",
                            "DOMESTIC",
                            "POL-03"),
                    "settlement_deadline",
                    new BusinessRule(
                            "settlement_deadline",
                            new BigDecimal("10"),
                            null,
                            "WORKING_DAYS_FROM_TRIP_END",
                            "DOMESTIC",
                            "POL-02"),
                    "receipt_required",
                    new BusinessRule(
                            "receipt_required",
                            null,
                            "true",
                            "BOOLEAN",
                            "SETTLEMENT",
                            "POL-04")));
    }
}
```

Trong production, rule catalog thường đến từ database/configuration service hoặc policy artifact đã ký duyệt. Ví dụ trên chỉ minh họa cấu trúc. Không thay rule set giữa chừng trong cùng một evaluation run.

## 7. Viết custom Evaluator

Output JSON được parse thành DTO. Evaluator kiểm tra:

1. Metadata của evaluation case có tồn tại và hợp lệ không.
2. action có đúng expected action không.
3. Có đủ required facts và không có duplicate keys không.
4. Mọi fact key có trong rule catalog không.
5. Value, unit và scope có khớp rule không.
6. Citation có chứa source ID bắt buộc và source đó có trong actual retrieved context không.
7. Khi expected action là abstain, candidate không được đưa ra facts và phải có lý do.

```java
import java.util.List;

record StructuredBusinessAnswer(
        String action,
        List<StructuredFact> facts,
        String abstentionReason) {}

record StructuredFact(
        String key,
        String value,
        String unit,
        String scope,
        List<String> citations) {}
```

### Triển khai evaluator

```java
import tools.jackson.databind.json.JsonMapper;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;
import org.springframework.ai.evaluation.Evaluator;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class BusinessPolicyEvaluator implements Evaluator {
    private static final String CASE_DOCUMENT_ID = "__evaluation_case__";

    private final JsonMapper jsonMapper;
    private final BusinessRuleSet ruleSet;

    BusinessPolicyEvaluator(
            JsonMapper jsonMapper,
            BusinessRuleSet ruleSet) {
        this.jsonMapper = jsonMapper;
        this.ruleSet = ruleSet;
    }

    @Override
    public EvaluationResponse evaluate(EvaluationRequest request) {
        List<String> violations = new ArrayList<>();
        CaseMetadata caseMetadata = findCaseMetadata(request);

        if (caseMetadata == null) {
            return response(false, 0.0f,
                    "Missing or invalid evaluation case metadata.",
                    Map.of("status", "INVALID_EVALUATION_INPUT"));
        }

        if (!ruleSet.version().equals(caseMetadata.ruleSetVersion())) {
            return response(false, 0.0f,
                    "Evaluation case and evaluator use different rule versions.",
                    Map.of("status", "INVALID_EVALUATION_INPUT",
                            "caseId", caseMetadata.caseId(),
                            "ruleSetVersion", ruleSet.version()));
        }

        if (request.getResponseContent() == null
                || request.getResponseContent().isBlank()) {
            return response(false, 0.0f,
                    "Candidate response is empty.",
                    Map.of("status", "INVALID_CANDIDATE_FORMAT",
                            "caseId", caseMetadata.caseId()));
        }

        StructuredBusinessAnswer answer;
        try {
            answer = jsonMapper.readValue(
                    request.getResponseContent(),
                    StructuredBusinessAnswer.class);
        }
        catch (Exception error) {
            return response(false, 0.0f,
                    "Candidate output is not valid structured JSON.",
                    Map.of(
                            "status", "INVALID_CANDIDATE_FORMAT",
                            "caseId", caseMetadata.caseId()));
        }

        if (answer == null || answer.action() == null || answer.facts() == null) {
            return response(false, 0.0f,
                    "Candidate JSON is missing required fields.",
                    Map.of("status", "INVALID_CANDIDATE_FORMAT",
                            "caseId", caseMetadata.caseId()));
        }

        if (!Set.of("ANSWER", "CORRECT_PREMISE", "ABSTAIN_OR_CLARIFY")
                .contains(caseMetadata.expectedAction())) {
            return response(false, 0.0f,
                    "Evaluation case contains an unknown expected action.",
                    Map.of("status", "INVALID_EVALUATION_INPUT",
                            "caseId", caseMetadata.caseId()));
        }

        Set<String> actualSourceIds = request.getDataList().stream()
                .filter(document -> !isEvaluationMetadata(document))
                .map(Document::getId)
                .collect(java.util.stream.Collectors.toSet());

        validateAction(answer, caseMetadata, violations);
        validateFacts(
                answer, caseMetadata, actualSourceIds, violations);

        boolean pass = violations.isEmpty();
        return response(
                pass,
                pass ? 1.0f : 0.0f,
                pass
                        ? "All deterministic business checks passed."
                        : "Business policy checks failed: "
                                + String.join(", ", violations),
                Map.of(
                        "status", pass ? "PASS" : "POLICY_VIOLATION",
                        "caseId", caseMetadata.caseId(),
                        "ruleSetVersion", ruleSet.version(),
                        "violations", List.copyOf(violations)));
    }

    private void validateAction(
            StructuredBusinessAnswer answer,
            CaseMetadata metadata,
            List<String> violations) {

        if (answer.action() == null
                || !answer.action().equals(metadata.expectedAction())) {
            violations.add("UNEXPECTED_ACTION");
        }

        if ("ABSTAIN_OR_CLARIFY".equals(metadata.expectedAction())) {
            if (answer.facts() != null && !answer.facts().isEmpty()) {
                violations.add("FACTS_PRESENT_WHILE_ABSTAINING");
            }
            if (answer.abstentionReason() == null
                    || answer.abstentionReason().isBlank()) {
                violations.add("ABSTENTION_REASON_MISSING");
            }
        }
        else if (answer.abstentionReason() != null
                && !answer.abstentionReason().isBlank()) {
            violations.add("UNEXPECTED_ABSTENTION_REASON");
        }
        else if (answer.facts().isEmpty()) {
            violations.add("FACTS_REQUIRED_FOR_ANSWER");
        }
    }

    private void validateFacts(
            StructuredBusinessAnswer answer,
            CaseMetadata metadata,
            Set<String> actualSourceIds,
            List<String> violations) {

        List<StructuredFact> facts =
                answer.facts() == null ? List.of() : answer.facts();
        Set<String> seenKeys = new HashSet<>();

        for (StructuredFact fact : facts) {
            if (fact == null) {
                violations.add("NULL_FACT_ENTRY");
                continue;
            }
            if (fact.key() == null || !seenKeys.add(fact.key())) {
                violations.add("MISSING_OR_DUPLICATE_FACT_KEY");
                continue;
            }

            BusinessRule rule = ruleSet.rules().get(fact.key());
            if (rule == null) {
                violations.add("UNKNOWN_FACT_KEY:" + fact.key());
                continue;
            }

            if (!matchesValue(rule, fact.value())) {
                violations.add("VALUE_MISMATCH:" + fact.key());
            }
            if (!rule.unit().equals(fact.unit())) {
                violations.add("UNIT_MISMATCH:" + fact.key());
            }
            if (!rule.scope().equals(fact.scope())) {
                violations.add("SCOPE_MISMATCH:" + fact.key());
            }

            List<String> citations =
                    fact.citations() == null ? List.of() : fact.citations();
            if (!citations.contains(rule.sourceDocumentId())) {
                violations.add("REQUIRED_CITATION_MISSING:" + fact.key());
            }
            if (!actualSourceIds.contains(rule.sourceDocumentId())) {
                violations.add("SOURCE_NOT_IN_ACTUAL_CONTEXT:" + fact.key());
            }
            if (!actualSourceIds.containsAll(citations)) {
                violations.add("CITATION_NOT_IN_ACTUAL_CONTEXT:" + fact.key());
            }
        }

        for (String requiredKey : metadata.requiredFactKeys()) {
            if (!seenKeys.contains(requiredKey)) {
                violations.add("REQUIRED_FACT_MISSING:" + requiredKey);
            }
        }
    }

    private boolean matchesValue(BusinessRule rule, String candidate) {
        if (candidate == null) {
            return false;
        }
        if (rule.numericValue() != null) {
            try {
                return new BigDecimal(candidate)
                        .compareTo(rule.numericValue()) == 0;
            }
            catch (NumberFormatException error) {
                return false;
            }
        }
        return rule.textValue() != null
                && rule.textValue().equalsIgnoreCase(candidate.trim());
    }

    private CaseMetadata findCaseMetadata(EvaluationRequest request) {
        List<Document> matches = request.getDataList().stream()
                .filter(this::isEvaluationMetadata)
                .toList();
        if (matches.size() != 1) {
            return null;
        }

        Document document = matches.get(0);
        Map<String, Object> metadata = document.getMetadata();
        Object caseId = metadata.get("case_id");
        Object expectedAction = metadata.get("expected_action");
        Object requiredKeys = metadata.get("required_fact_keys");
        Object ruleSetVersion = metadata.get("rule_set_version");
        if (!(caseId instanceof String caseIdValue) || caseIdValue.isBlank()
                || !(expectedAction instanceof String actionValue)
                || !(requiredKeys instanceof String requiredKeysValue)
                || !(ruleSetVersion instanceof String versionValue)
                || versionValue.isBlank()) {
            return null;
        }
        if (!Set.of("ANSWER", "CORRECT_PREMISE", "ABSTAIN_OR_CLARIFY")
                .contains(actionValue)) {
            return null;
        }
        List<String> requiredFactKeys = parseCsv(requiredKeysValue);
        if (!ruleSet.rules().keySet().containsAll(requiredFactKeys)) {
            return null;
        }
        if ("ABSTAIN_OR_CLARIFY".equals(actionValue)
                && !requiredFactKeys.isEmpty()) {
            return null;
        }
        return new CaseMetadata(
                caseIdValue,
                actionValue,
                requiredFactKeys,
                versionValue);
    }

    private boolean isEvaluationMetadata(Document document) {
        return CASE_DOCUMENT_ID.equals(document.getId())
                && Boolean.TRUE.equals(
                        document.getMetadata().get("evaluation_only"));
    }

    private List<String> parseCsv(String value) {
        if (value == null || value.isBlank() || "null".equals(value)) {
            return List.of();
        }
        return java.util.Arrays.stream(value.split(","))
                .map(String::trim)
                .filter(part -> !part.isEmpty())
                .toList();
    }

    private EvaluationResponse response(
            boolean pass,
            float score,
            String feedback,
            Map<String, Object> metadata) {
        return new EvaluationResponse(pass, score, feedback, metadata);
    }

    private record CaseMetadata(
            String caseId,
            String expectedAction,
            List<String> requiredFactKeys,
            String ruleSetVersion) {}
}
```

Đây là skeleton minh họa các bước kiểm tra chính; trước khi dùng production cần validate chặt hơn các metadata null, enum action, DTO fields và trường hợp dataList rỗng. Ví dụ dùng matches.get(0) sau khi đã kiểm tra đúng một metadata document, tương thích Java 17 trở lên.

### Đăng ký evaluator thành Spring bean

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ai.evaluation.Evaluator;
import tools.jackson.databind.json.JsonMapper;

@Configuration
class BusinessEvaluationConfiguration {

    @Bean
    BusinessRuleSet businessRuleSet() {
        return BusinessRuleCatalog.policyDemoV1();
    }

    @Bean
    Evaluator businessPolicyEvaluator(
            JsonMapper jsonMapper,
            BusinessRuleSet ruleSet) {
        return new BusinessPolicyEvaluator(jsonMapper, ruleSet);
    }
}
```

Trong Spring Boot 4/Spring AI 2.1.x, ví dụ dùng Jackson 3 với package tools.jackson. Spring AI cung cấp JacksonUtils để lấy JsonMapper mặc định đã cấu hình module. Nếu dự án còn ở Spring Boot 3/Spring AI 1.x, mapper và package JSON có thể khác; hãy dùng dependency/version thực tế của dự án.

## 8. Hiểu kết quả của evaluator

Custom evaluator trả EvaluationResponse:

| Field | Ý nghĩa trong ví dụ |
| --- | --- |
| isPass() | Tất cả hard checks đều đạt |
| getScore() | 1.0 nếu pass, 0.0 nếu fail; không phải xác suất |
| getFeedback() | Danh sách mã vi phạm hoặc thông báo pass |
| getMetadata() | Case ID, rule set version, status và violation codes |

Các trạng thái cần phân biệt:

| Status | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| PASS | Output đúng schema và mọi rule đều đạt | Tiếp tục các evaluator khác |
| POLICY_VIOLATION | Output parse được nhưng vi phạm rule | Fail hard gate, lưu violation codes |
| INVALID_CANDIDATE_FORMAT | Output không parse được thành contract | Sửa structured output/prompt hoặc đánh dấu model output invalid |
| INVALID_EVALUATION_INPUT | Thiếu metadata/harness input | Sửa test harness; không kết luận model factual |
| EVALUATION_ERROR | Evaluator gặp lỗi hạ tầng/exception | Retry có giới hạn hoặc đánh dấu chưa đánh giá |

Không dùng cùng một nhãn FAIL cho cả vi phạm nghiệp vụ lẫn lỗi evaluator. Nếu không phân biệt, dashboard sẽ báo model hallucinate khi thực tế test harness truyền sai metadata.

## 9. Ví dụ các case pass và fail

### Case A: số tiền, đơn vị, phạm vi và citation đúng

Candidate:

```json
{
  "action": "ANSWER",
  "facts": [
    {
      "key": "meal_allowance",
      "value": "350000",
      "unit": "VND_PER_DAY",
      "scope": "DOMESTIC",
      "citations": ["POL-01"]
    }
  ],
  "abstentionReason": null
}
```

Nếu rule set là policy-demo-v1, actual context có POL-01, expected action là ANSWER và required key là meal_allowance, kết quả kỳ vọng là PASS.

### Case B: đúng con số nhưng sai đơn vị

Candidate ghi value=350000 nhưng unit=VND_PER_TRIP. Kết quả phải fail UNIT_MISMATCH:meal_allowance. Không được coi hai đơn vị là tương đương chỉ vì con số giống nhau.

### Case C: đúng fact nhưng citation không có trong context

Candidate trích POL-01, nhưng actual retrieved context chỉ có POL-03. Kết quả fail SOURCE_NOT_IN_ACTUAL_CONTEXT. Đây là lỗi provenance/citation của lần chạy, ngay cả khi con số trùng với policy catalog.

Kiểm tra document ID mới chỉ xác nhận tài liệu có mặt trong context. Trong production, hãy pin thêm corpus version hoặc content checksum trong rule catalog và metadata của Document; so sánh chúng trước khi chấp nhận source. Việc citation trỏ tới đúng document cũng chưa chứng minh mọi câu văn trong document hỗ trợ claim; với claim diễn đạt tự do, cần semantic fact checking hoặc review.

### Case D: thiếu required fact

Case TRAVEL-004 yêu cầu receipt_required và settlement_deadline. Nếu candidate chỉ trả deadline, evaluator fail REQUIRED_FACT_MISSING:receipt_required.

### Case E: thiếu ngữ cảnh

Expected action là ABSTAIN_OR_CLARIFY. Candidate phải có facts=[], abstentionReason không rỗng và action đúng. Nếu candidate vẫn khẳng định mức phụ cấp quốc tế 500.000 VND/ngày, evaluator fail vì đưa fact ngoài rule set hoặc sai expected action.

### Case F: giá trị tiền có định dạng tương đương

350000, 350000.00 và 3.5E+5 có thể được so sánh bằng BigDecimal.compareTo, không dùng so sánh chuỗi. Tuy vậy, hãy chuẩn hóa format khi serialize để output dễ đọc và nhất quán.

## 10. Viết unit tests xác định

Khác với integration test dùng LLM judge, unit tests của business evaluator không cần gọi model. Cùng một input, rule set và actual context phải luôn tạo cùng một verdict.

### Test fixture

```java
import org.springframework.ai.util.JacksonUtils;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class BusinessPolicyEvaluatorTest {
    private BusinessPolicyEvaluator evaluator;

    @BeforeEach
    void setUp() {
        evaluator = new BusinessPolicyEvaluator(
                JacksonUtils.getDefaultJsonMapper(),
                BusinessRuleCatalog.policyDemoV1());
    }

    private Document caseMetadata(
            String expectedAction, String requiredKeys) {
        return new Document(
                "__evaluation_case__",
                "Evaluation metadata.",
                Map.of(
                        "evaluation_only", true,
                        "case_id", "TRAVEL-001",
                        "expected_action", expectedAction,
                        "required_fact_keys", requiredKeys,
                        "rule_set_version", "policy-demo-v1"));
    }

    private EvaluationResponse evaluate(
            String expectedAction,
            String requiredKeys,
            List<Document> evidence,
            String candidateJson) {

        var context = new java.util.ArrayList<>(evidence);
        context.add(caseMetadata(expectedAction, requiredKeys));

        return evaluator.evaluate(new EvaluationRequest(
                "Mức phụ cấp ăn tối đa là bao nhiêu?",
                context,
                candidateJson));
    }

    @Test
    void acceptsExactBusinessFactAndCitation() {
        Document policy = new Document(
                "POL-01",
                "Phụ cấp ăn nội địa tối đa 350.000 đồng mỗi ngày.",
                Map.of());

        String candidate = """
                {
                  "action": "ANSWER",
                  "facts": [{
                    "key": "meal_allowance",
                    "value": "350000.00",
                    "unit": "VND_PER_DAY",
                    "scope": "DOMESTIC",
                    "citations": ["POL-01"]
                  }],
                  "abstentionReason": null
                }
                """;

        EvaluationResponse result = evaluate(
                "ANSWER", "meal_allowance",
                List.of(policy), candidate);

        assertThat(result.isPass()).isTrue();
        assertThat(result.getScore()).isEqualTo(1.0f);
    }

    @Test
    void rejectsWrongUnitEvenWhenAmountMatches() {
        Document policy = new Document(
                "POL-01", "Policy text", Map.of());
        String candidate = """
                {
                  "action": "ANSWER",
                  "facts": [{
                    "key": "meal_allowance",
                    "value": "350000",
                    "unit": "VND_PER_TRIP",
                    "scope": "DOMESTIC",
                    "citations": ["POL-01"]
                  }],
                  "abstentionReason": null
                }
                """;

        EvaluationResponse result = evaluate(
                "ANSWER", "meal_allowance",
                List.of(policy), candidate);

        assertThat(result.isPass()).isFalse();
        assertThat(result.getFeedback())
                .contains("UNIT_MISMATCH:meal_allowance");
    }

    @Test
    void rejectsMissingRequiredFact() {
        String candidate = """
                {
                  "action": "ANSWER",
                  "facts": [],
                  "abstentionReason": null
                }
                """;

        EvaluationResponse result = evaluate(
                "ANSWER", "meal_allowance",
                List.of(), candidate);

        assertThat(result.isPass()).isFalse();
        assertThat(result.getFeedback())
                .contains("REQUIRED_FACT_MISSING:meal_allowance");
    }

    @Test
    void rejectsCitationThatWasNotRetrieved() {
        Document unrelated = new Document(
                "POL-03", "Hotel policy", Map.of());
        String candidate = """
                {
                  "action": "ANSWER",
                  "facts": [{
                    "key": "meal_allowance",
                    "value": "350000",
                    "unit": "VND_PER_DAY",
                    "scope": "DOMESTIC",
                    "citations": ["POL-01"]
                  }],
                  "abstentionReason": null
                }
                """;

        EvaluationResponse result = evaluate(
                "ANSWER", "meal_allowance",
                List.of(unrelated), candidate);

        assertThat(result.isPass()).isFalse();
        assertThat(result.getFeedback())
                .contains("SOURCE_NOT_IN_ACTUAL_CONTEXT:meal_allowance");
    }

    @Test
    void acceptsAbstentionWhenCaseRequiresIt() {
        String candidate = """
                {
                  "action": "ABSTAIN_OR_CLARIFY",
                  "facts": [],
                  "abstentionReason": "Corpus không có chính sách công tác quốc tế."
                }
                """;

        EvaluationResponse result = evaluate(
                "ABSTAIN_OR_CLARIFY", "",
                List.of(), candidate);

        assertThat(result.isPass()).isTrue();
    }

    @Test
    void rejectsMalformedCandidateJson() {
        EvaluationResponse result = evaluate(
                "ANSWER", "meal_allowance",
                List.of(), "{not-json");

        assertThat(result.isPass()).isFalse();
        assertThat(result.getMetadata())
                .containsEntry("status", "INVALID_CANDIDATE_FORMAT");
    }
}
```

Các test trên minh họa sáu hành vi: pass khi đúng rule, fail khi sai unit, fail khi thiếu required fact, fail khi citation không có trong context, pass khi abstain đúng và fail riêng cho JSON lỗi. Có thể bổ sung test duplicate key, unknown fact key, sai rule version và action không khớp.

### Test nào nên là unit test, test nào nên là integration test?

| Test | Loại | Có gọi LLM? |
| --- | --- | --- |
| So sánh BigDecimal, unit, scope | Unit | Không |
| Kiểm tra required facts và duplicate keys | Unit | Không |
| Kiểm tra citation ID trong context | Unit | Không |
| Parse structured JSON và metadata | Unit | Không |
| RelevancyEvaluator với judge model | Integration | Có |
| FactCheckingEvaluator với judge model | Integration | Có |
| Chạy end-to-end cả retriever, generator và evaluator | Integration/system | Có thể có |

## 11. Bổ sung kiểm tra ngày và thời hạn nghiệp vụ

Ngày là nguồn lỗi thường gặp vì “10 ngày” có thể là ngày theo lịch hoặc ngày làm việc. Không triển khai bằng cách cộng số ngày trực tiếp nếu policy nói ngày làm việc.

Một deadline evaluator cần:

- Ngày bắt đầu tính hạn.
- Số ngày làm việc.
- Lịch ngày nghỉ theo khu vực/đơn vị.
- Timezone và quy tắc chốt ngày.
- Phiên bản lịch nghỉ.
- Quy tắc xử lý khi hạn rơi vào ngày nghỉ.

Ví dụ service chuyên biệt:

```java
import java.time.LocalDate;

interface BusinessCalendar {
    LocalDate addWorkingDays(LocalDate startDate, int workingDays);
    String version();
}

record DeadlineRule(
        int workingDays,
        String calendarVersion,
        String countingConvention) {}

final class DeadlineCalculator {
static LocalDate calculateDeadline(
        LocalDate tripEndDate,
        DeadlineRule rule,
        BusinessCalendar calendar) {

    if (!calendar.version().equals(rule.calendarVersion())) {
        throw new IllegalStateException(
                "Business calendar version mismatch");
    }
    return calendar.addWorkingDays(
            tripEndDate, rule.workingDays());
}
}
```

Đoạn code cố ý để BusinessCalendar là interface: cách tính ngày nghỉ phụ thuộc lịch của tổ chức và quy định áp dụng. Unit test phải dùng một calendar fixture có version cố định. Không giả định thứ Bảy, Chủ nhật hoặc ngày lễ ở mọi quốc gia đều có cùng quy tắc.

## 12. Ghép deterministic evaluator với LLM judge

Hai nhóm evaluator nên chạy theo thứ tự:

1. Parse output contract và chạy deterministic business gates.
2. Nếu hard gate fail, lưu violations và dừng các judge calls không cần thiết.
3. Nếu hard gate pass, chạy RelevancyEvaluator để kiểm tra câu trả lời có bám câu hỏi/context không.
4. Nếu cần, tách atomic claims rồi chạy FactCheckingEvaluator hoặc judge chuyên biệt.
5. Gộp kết quả nhưng giữ từng verdict riêng; không làm mất nguyên nhân fail.

Ví dụ orchestration:

```java
import java.util.List;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;
import org.springframework.ai.evaluation.Evaluator;

final class EvaluationOrchestrator {
record CombinedEvaluation(
        EvaluationResponse business,
        EvaluationResponse relevancy,
        List<EvaluationResponse> factChecks) {}

CombinedEvaluation evaluateAll(
        EvaluationRequest request,
        Evaluator businessEvaluator,
        Evaluator relevancyEvaluator,
        List<String> atomicClaims,
        java.util.function.Function<String, String> renderValidatedAnswer,
        java.util.function.BiFunction<List<Document>, String, EvaluationResponse>
                factChecker) {

    EvaluationResponse business =
            businessEvaluator.evaluate(request);

    if (!business.isPass()) {
        return new CombinedEvaluation(
                business, null, List.of());
    }

    List<Document> actualEvidence = request.getDataList().stream()
            .filter(document -> !Boolean.TRUE.equals(
                    document.getMetadata().get("evaluation_only")))
            .toList();

    EvaluationRequest judgeRequest = new EvaluationRequest(
            request.getUserText(),
            actualEvidence,
            renderValidatedAnswer.apply(request.getResponseContent()));

    EvaluationResponse relevancy =
            relevancyEvaluator.evaluate(judgeRequest);

    List<EvaluationResponse> factChecks = atomicClaims.stream()
            .map(claim -> factChecker.apply(actualEvidence, claim))
            .toList();

    return new CombinedEvaluation(
            business, relevancy, factChecks);
}
}
```

Đây là khung orchestration. Trong dự án thực tế, render câu trả lời từ facts đã được xác thực trước khi gửi vào RelevancyEvaluator; không dùng chuỗi JSON nội bộ làm câu trả lời hiển thị. Fact checker cần được gắn với đúng evidence cho từng claim; ví dụ có thể dùng một closure giữ context đã chọn. Không truyền evaluation metadata document vào LLM judge vì đó không phải evidence và có thể làm nhiễu kết quả.

### Không gộp mọi kết quả thành một boolean duy nhất

Lưu riêng:

- Business gate: pass/fail và violation codes.
- Relevance: pass/fail và feedback.
- Fact checking: verdict theo từng claim.
- Retrieval: Recall@k/Precision@k.
- Required-fact coverage và citation support.

Một case có thể pass business rules nhưng fail relevance. Một case khác có thể pass relevance nhưng fail fact checking. Khi chỉ lưu một boolean tổng hợp, đội phát triển sẽ không biết cần sửa rule, retriever, prompt hay model.

## 13. Khi nào dùng DecisionModel?

Spring AI 2.1.0 bổ sung DecisionModel cho các quyết định có tập kết quả hữu hạn như yes/no, lựa chọn một category hoặc score. Đây vẫn là một model API: model chọn kết quả và có thể trả thông tin về mức độ tin cậy/likelihood.

Phân biệt:

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Phân loại câu hỏi vào nhóm “hoàn tiền”, “đổi vé”, “khác” | DecisionModel hoặc classifier |
| Diễn giải câu hỏi mơ hồ thành intent có cấu trúc | Model decision/classification, sau đó validate |
| Kiểm tra số tiền có bằng hạn mức 350.000 không | Java BigDecimal |
| Kiểm tra ngày làm việc theo lịch đã version | BusinessCalendar deterministic |
| Kiểm tra citation ID có tồn tại trong context | Java set/map lookup |
| Kiểm tra claim có được diễn đạt tương đương với policy không | FactCheckingEvaluator hoặc human review |

DecisionModel giúp chuẩn hóa đầu ra của một quyết định do model suy luận. Nó không biến suy luận của model thành một quy tắc xác định. Khi có ngưỡng, đơn vị, ngày hoặc quyền truy cập rõ ràng, hãy dùng code làm hard gate cuối.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Lấy giá trị chuẩn từ candidate answer | Model tự định nghĩa đáp án rồi tự được chấm đúng | Inject rule catalog tin cậy |
| So sánh tiền bằng double | Sai số dấu phẩy động | Dùng BigDecimal |
| Chỉ so sánh con số | Bỏ sót currency, period và scope | Kiểm tra cả value, unit, scope |
| Chỉ kiểm tra citation có trong corpus | Citation có thể không nằm trong context model đã nhận | Kiểm tra actual retrieved IDs |
| Chỉ kiểm tra citation ID tồn tại | Không chứng minh nội dung citation hỗ trợ claim | Kết hợp source mapping và semantic fact check |
| Cho model thêm prose không kiểm tra | Có thể chứa claim ngoài structured facts | Render từ facts đã xác thực hoặc kiểm tra prose riêng |
| Dùng một boolean cho mọi lỗi | Không phân biệt policy violation và evaluator error | Lưu status/error category riêng |
| Rule thay đổi trong lúc chạy | Cùng run có thể được chấm theo hai policy | Pin immutable rule set version |
| Lịch ngày nghỉ không có version | Deadline không tái lập được | Lưu calendar version và convention |
| Cho LLM ghi đè hard gate | Có thể chấp nhận vi phạm nghiệp vụ | Hard gate luôn có quyền quyết định cuối |

## 15. Quan sát evaluator và quản lý cardinality

Evaluator cũng là một operation cần đo. Với deterministic evaluator, có thể theo dõi:

- Số lần đánh giá theo outcome.
- Số lượng policy violations theo nhóm rule.
- Tỷ lệ candidate JSON không hợp lệ.
- Thời gian thực thi evaluator.
- Số case thiếu metadata hoặc sai rule version.

Tên metric minh họa:

| Metric | Ý nghĩa |
| --- | --- |
| ai.business_evaluation.total | Tổng số lần gọi business evaluator |
| ai.business_evaluation.duration | Thời gian thực thi |
| ai.business_evaluation.policy_violation | Số case vi phạm rule |
| ai.business_evaluation.invalid_output | Output không parse được |
| ai.business_evaluation.input_error | Metadata/context evaluation không hợp lệ |

Tags chỉ nên chứa giá trị hữu hạn như evaluator version, outcome và rule category. Không đưa raw question, candidate answer, user ID, document text hoặc trace ID vào metric labels. Trace ID có thể nằm trong trace/log correlation.

### Lưu metadata để tái lập

Mỗi evaluation result nên ghi:

- run ID, dataset ID/version và case ID.
- rule set version và business calendar version nếu có.
- corpus/index version và actual retrieved document IDs.
- generator model, prompt và pipeline version.
- evaluator version và output schema version.
- pass/fail, violation codes, feedback và duration.
- trace ID, usage và cost nếu có model judge đi kèm.

## 16. Bài thực hành tổng hợp

Bạn có một candidate answer cho câu hỏi về hạn mức khách sạn:

```json
{
  "action": "ANSWER",
  "facts": [
    {
      "key": "hotel_cap",
      "value": "1200000",
      "unit": "VND_PER_NIGHT",
      "scope": "INTERNATIONAL",
      "citations": ["POL-03"]
    }
  ],
  "abstentionReason": null
}
```

Actual retrieved context có POL-03, rule set yêu cầu hạn mức 1.200.000 VND/đêm cho công tác nội địa.

**Yêu cầu:**

1. Candidate có pass không? Liệt kê violations.
2. Vì sao chỉ so sánh value là chưa đủ?
3. Nếu expected action của case là ABSTAIN_OR_CLARIFY thì cần kiểm tra thêm gì?
4. Nếu POL-03 không nằm trong actual context thì evaluator nên ghi violation nào?
5. Vì sao không nên để LLM judge ghi đè kết quả deterministic?
6. Nêu hai test bổ sung cho business evaluator.

### Đáp án gợi ý

1. Fail vì scope không khớp. Violation là SCOPE_MISMATCH:hotel_cap.
2. Cùng một số tiền có thể áp dụng cho nội địa hoặc quốc tế, theo đêm hoặc theo chuyến; unit và scope là một phần của nghĩa nghiệp vụ.
3. Action phải là ABSTAIN_OR_CLARIFY, facts phải rỗng và abstentionReason phải có nội dung.
4. Ghi SOURCE_NOT_IN_ACTUAL_CONTEXT:hotel_cap; citation phải tồn tại trong evidence thực tế đã cấp cho model.
5. Deterministic rule là policy hard gate đã được phê duyệt. LLM judge có thể đánh giá ngữ nghĩa nhưng không có quyền thay đổi hạn mức hoặc ngoại lệ.
6. Test thiếu required fact và test sai ruleSetVersion; có thể thêm duplicate fact key hoặc candidate JSON malformed.

## Ghi nhớ

- **Dùng code cho quy tắc xác định:** số tiền, đơn vị, phạm vi, thời hạn, required fields và citation IDs.
- **Dùng structured output:** facts có key, value, unit, scope và citations để evaluator kiểm tra từng mục.
- **Rule catalog phải tin cậy và có version:** không lấy chuẩn từ chính câu trả lời đang được chấm.
- **Kiểm tra actual context:** citation phải trỏ tới nguồn thực sự được retrieve; source mapping vẫn cần semantic check khi xác minh claim.
- **Tách trạng thái lỗi:** policy violation, invalid candidate và evaluator infrastructure error không phải cùng một kết luận.
- **Chạy hard gate trước LLM judge:** judge không ghi đè vi phạm nghiệp vụ đã xác định.
- **Đo và lưu provenance:** dataset, corpus, rule set, calendar, prompt, model, evaluator và trace version phải gắn với kết quả.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI 2.1.x API — Evaluator](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/evaluation/Evaluator.html)
- [Spring AI 2.1.x API — EvaluationRequest](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/evaluation/EvaluationRequest.html)
- [Spring AI 2.1.x API — EvaluationResponse](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/evaluation/EvaluationResponse.html)
- [Spring AI 2.1.x API — JacksonUtils](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/util/JacksonUtils.html)
- [Spring Boot — JSON and Jackson 3](https://docs.spring.io/spring-boot/reference/features/json.html)
- [Spring AI 2.1.0 GA — Decision Models](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/)
