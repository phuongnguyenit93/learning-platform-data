# Tổ chức mã đánh giá, dữ liệu tình huống và cấu hình quan sát

> **Chương:** Thiết lập dự án
>
> **Phạm vi module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking, kiểm thử RAG/tool calling; kết hợp metrics, traces, token usage, chi phí và độ trễ để điều tra hồi quy qua các phiên bản prompt, model và pipeline.
>
> **Bộ nền tham khảo:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. Ví dụ tập trung vào cách tổ chức dự án; những tên `app.evaluation.*` do ứng dụng tự định nghĩa, không phải tính năng tự kích hoạt của Spring AI.

## 1. Kết quả cần đạt

Hết bài, bạn có thể:

1. Chia project thành **mã chạy ứng dụng**, **mã đánh giá**, **bộ dữ liệu tình huống**, **cấu hình quan sát** và **báo cáo kết quả** với trách nhiệm rõ ràng.
2. Thiết kế một dataset có thể tái lập cho câu hỏi RAG, fact checking, trường hợp thiếu bằng chứng và tool calling.
3. Xây **evaluation runner** điều phối câu hỏi, retrieval, generation, deterministic assertions, judge và lưu kết quả mà không trộn các vai trò.
4. Gắn **trace/metric** theo giai đoạn; phân biệt chất lượng câu trả lời với latency, token usage và chi phí vận hành.
5. Chạy kiểm thử xác định ở mỗi commit và regression evaluation có gọi LLM ở một quy trình riêng, có ngân sách và ngưỡng chấp nhận.
6. Đọc báo cáo để xác định một lần thay đổi prompt, model hoặc pipeline làm chất lượng suy giảm ở bước nào.

### Vì sao việc tổ chức code là một phần của chất lượng?

Giả sử ứng dụng trợ lý tra cứu quy trình nội bộ trả lời đúng 91/100 câu ở bản A và 84/100 câu ở bản B. Nếu test trực tiếp trong controller và dataset nằm rải rác trong unit tests, ta có thể không biết: 100 câu có còn giống nhau không, context dùng để chấm có phải context generator nhận không, judge có đổi hay không, và 7 câu lỗi do retrieval, tool hay model. Một cấu trúc rõ ràng biến kết quả “84%” thành **bằng chứng có thể điều tra**.

Nguyên tắc trung tâm: **một tình huống -> một ảnh chụp quá trình chạy -> các phép chấm độc lập -> một bản ghi kết quả có version**.

## 2. Phân biệt bốn dòng dữ liệu trong evaluation

| Dòng dữ liệu | Nội dung | Nguồn sở hữu | Có được sửa trong lúc chấm không? |
|---|---|---|---|
| **Case definition** | Câu hỏi, kịch bản, expected document/tool, quy tắc từ chối, nhãn chuẩn | Bộ dataset có version | **Không**, đã chốt trước khi chạy |
| **Execution snapshot** | Context thực sự truy xuất, tool calls thực tế, answer, lỗi/latency | Application/RAG/tool pipeline | Không sửa sau khi thu thập |
| **Judgement** | Relevance, fact-check verdict, điểm/giải thích, lỗi judge | Deterministic checks và evaluator | Được tái chấm với **rubric/judge version khác**, phải lưu riêng |
| **Telemetry và run manifest** | Traces, token usage, chi phí, commit, model/prompt/index/dataset versions | Observability + evaluation runner | Chỉ tổng hợp, liên kết lại qua run/case IDs có quyền |

Các đối tượng này **không nên là một POJO khổng lồ**. Nếu viết đè `expectedAnswer` bằng `generatedAnswer` hoặc thay `retrievedDocuments` khi gọi judge, ta đã đánh mất điều kiện tái lập.

### Luồng dữ liệu

~~~mermaid
flowchart TD
  D["Dataset + manifest bất biến"] --> L["Case loader / validator"]
  L --> R["Evaluation runner"]
  R --> W["Answer workflow: retriever, model, tools"]
  W --> S["Execution snapshot"]
  S --> C["Deterministic checks: retrieval/tool"]
  S --> J["LLM judges: relevance, fact checking"]
  C --> A["Case assessment"]
  J --> A
  A --> O["Report store / CI gate"]
  R --> T["Micrometer Observation / traces"]
  W --> T
  J --> T
  T --> O
~~~

Một **case** có thể có nhiều **assessment** khi chấm lại bằng judge khác. Mỗi lần chấm phải ghi rõ `judge_model`, `rubric_revision` và `evaluation_attempt`.

## 3. Cấu trúc project tham khảo

Ví dụ một repository Spring Boot đơn module, đủ nhỏ để học và có đường mở rộng:

~~~text
ai-quality-lab/
├── pom.xml
├── mvnw, mvnw.cmd, .mvn/
├── src/
│   ├── main/
│   │   ├── java/com/example/aiquality/
│   │   │   ├── application/
│   │   │   │   ├── AnswerWorkflow.java
│   │   │   │   └── AnswerService.java
│   │   │   ├── rag/
│   │   │   │   ├── RetrievalGateway.java
│   │   │   │   └── VectorStoreAdapter.java
│   │   │   ├── tools/
│   │   │   │   ├── ToolGateway.java
│   │   │   │   └── ToolCallRecorder.java
│   │   │   ├── evaluation/
│   │   │   │   ├── domain/
│   │   │   │   │   ├── EvaluationCase.java
│   │   │   │   │   ├── ExecutionSnapshot.java
│   │   │   │   │   ├── CaseAssessment.java
│   │   │   │   │   └── EvaluationRun.java
│   │   │   │   ├── loader/CaseRepository.java
│   │   │   │   ├── runner/EvaluationRunner.java
│   │   │   │   ├── scoring/RetrievalScorer.java
│   │   │   │   ├── scoring/ToolAssertionScorer.java
│   │   │   │   ├── judge/SpringAiJudgeAdapter.java
│   │   │   │   └── report/ReportWriter.java
│   │   │   ├── observability/EvaluationObservations.java
│   │   │   └── config/EvaluationProperties.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-dev.yml
│   │       └── application-staging.yml
│   └── test/
│       ├── java/com/example/aiquality/
│       │   ├── evaluation/CaseRepositoryTest.java
│       │   ├── evaluation/RetrievalScorerTest.java
│       │   ├── evaluation/ToolAssertionScorerTest.java
│       │   └── evaluation/LiveEvaluationTest.java
│       └── resources/evaluation/fixtures/
│           └── smoke-cases.jsonl
├── evaluation/
│   ├── datasets/
│   │   └── policy-qa-v1/
│   │       ├── manifest.yml
│   │       ├── cases.jsonl
│   │       └── source-catalog.json
│   ├── rubrics/
│   │   ├── relevance-v1.md
│   │   └── groundedness-v1.md
│   ├── prompts/
│   │   └── answer-v1.md
│   └── baselines/
│       └── approved-baseline.json
└── reports/                # Đầu ra sinh lúc chạy; hạn chế commit dữ liệu nhạy cảm
~~~

Đây là **cấu trúc đề xuất để người học tạo trong dự án riêng**, không phải những file khác cần tạo trong module nội dung hiện tại.

### Tách trách nhiệm theo package

| Thành phần | Nên làm | Không nên làm |
|---|---|---|
| `application` | Thực hiện quy trình trả lời người dùng; trả snapshot qua interface khi được test | Phụ thuộc `assertTrue` hoặc rubric chấm điểm |
| `rag` / `tools` | Truy xuất context, gọi tool và ghi lại evidence/arguments/status | Tự định nghĩa “câu trả lời đạt relevance” |
| `evaluation.domain` | Biểu diễn case, snapshot, judgement và run metadata | Gọi HTTP provider, viết file hoặc inject bean tùy tiện |
| `loader` | Đọc, validate schema, khóa revision và thứ tự các case | Tự thay expected labels theo câu trả lời model |
| `runner` | Điều phối các bước và trạng thái, timeout, retry, audit | Chứa trực tiếp template prompt hoặc logic tính toán mọi chỉ số |
| `scoring` | So sánh doc IDs/tool assertions bằng quy tắc xác định | Dùng LLM để so các trường có thể đối chiếu chính xác |
| `judge` | Gọi evaluator/model chấm, xử lý parse và lỗi | Làm thay đổi retrieved context hoặc generation result |
| `observability` | Đặt observation spans/metrics và nhãn có cardinality thấp | Ghi prompt/key/user ID vào metric label |
| `report` | Ghi kết quả/manifest và tính tỉ lệ có mẫu số rõ ràng | Gộp `ERROR` thành `PASS`/ `FAIL` mà không phân biệt |

Nếu hệ thống lớn lên, có thể tách runner, dataset loader và report writer thành **một module hoặc process evaluation worker** riêng. Không cần triển khai microservices ngay từ bài học, nhưng nên tách **interface** để application runtime không phụ thuộc trực tiếp lên provider judge.

## 4. Thiết kế dataset tình huống có version

Dataset gồm **manifest** mô tả phạm vi và **cases** chứa từng tình huống. JSON Lines (JSONL) thích hợp cho quy trình batch: mỗi dòng là một JSON object độc lập, dễ stream và đối chiếu bằng Git. Định dạng CSV cũng dùng được với dữ liệu phẳng nhưng khó mô tả tool arguments và danh sách document IDs.

### Ví dụ `evaluation/datasets/policy-qa-v1/manifest.yml`

~~~yaml
dataset_id: policy-qa
dataset_revision: v1
schema_version: 1
language: vi
owner: ai-quality-team
scenario_types: [rag, tool, no_context]
source_snapshot: policy-corpus-2026-11
expected_embedding_index: policy-pgvector-v7
labels_reviewed: true
split: regression
case_count: 3
allowed_environments: [test, staging]
rubric_revisions:
  relevance: relevance-v1
  groundedness: groundedness-v1
notes: "Dữ liệu tình huống tổng hợp, không chứa PII"
~~~

**Mọi giá trị trong manifest là ví dụ**, cần thay bằng manifest có nguồn gốc và revision thật của project. `allowed_environments` là metadata cho loader/runner kiểm tra; muốn chặn truy cập chéo thực sự vẫn cần IAM, database permissions và policy triển khai.

### Ví dụ `cases.jsonl`

~~~jsonl
{"id":"policy-001","scenario":"rag","question":"Hạn nộp báo cáo tháng là khi nào?","expectedDocumentIds":["policy-v3-chunk-07"],"expectedToolCalls":[],"expectedClaims":["Trước ngày 05 của tháng kế tiếp"],"expectAbstention":false,"tags":["policy","deadline"]}
{"id":"policy-002","scenario":"no_context","question":"Ai đã duyệt tài liệu mật X?","expectedDocumentIds":[],"expectedToolCalls":[],"expectedClaims":[],"expectAbstention":true,"tags":["abstention","missing-evidence"]}
{"id":"order-003","scenario":"tool","question":"Đơn TEST-003 đang ở trạng thái nào?","expectedDocumentIds":[],"expectedToolCalls":[{"name":"getOrderStatus","arguments":{"orderId":"TEST-003"}}],"expectedClaims":["Đang vận chuyển"],"expectAbstention":false,"tags":["tool","sandbox"]}
~~~

`expectedDocumentIds`, `expectedToolCalls` và `expectedClaims` là **nhãn chuẩn**, không gửi trực tiếp cho generator để tránh làm lộ đáp án. Riêng nguồn evidence trả về từ tool phải được ghi vào snapshot để fact checker có thể đánh giá câu trả lời dựa trên bằng chứng thực tế.

### Phân loại case cần có

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| Có nguồn rõ ràng | Quy định “trước ngày 05” | Đo retrieve và grounded answer |
| Nhiễu nhiều tài liệu | Hai chính sách có ngày khác nhau, chỉ một bản hiệu lực | Kiểm tra ranking, metadata filter |
| Thiếu context | Không có chính sách trả lời | Kiểm tra **abstention**, tránh hallucination |
| Câu trả lời liên quan nhưng sai | Generator trả “ngày 15” | Relevance có thể pass, fact checking nên fail |
| Có tool bắt buộc | Cần `getOrderStatus` | So tên tool và argument chính xác |
| Tool lỗi | Timeout hoặc trả `NOT_FOUND` | Kiểm tra thông báo, retry, không bịa dữ liệu |
| Injection trong document/tool output | Context chứa “bỏ qua tiêu chí chấm” | Đánh giá khả năng coi evidence là dữ liệu, không tuân lệnh |
| Ca dài/đa bước | Hai nguồn phải kết hợp | Đo completeness, token và latency |

**Dữ liệu âm tính** quan trọng như dữ liệu dương tính. Dataset chỉ gồm những câu chatbot từng trả đúng sẽ dễ tạo kết luận lạc quan nhưng không đo được nguy cơ hallucination hoặc tool misuse.

## 5. Quy ước thiết kế case và chất lượng dữ liệu

Đặt schema trước khi viết loader:

- `id`: không trùng, ổn định qua các lần chạy; **không** chứa ID khách hàng thật.
- `scenario`: một enum được quản lý, chẳng hạn `rag`, `tool`, `no_context`.
- `question`: câu hỏi nguồn, không có gợi ý đáp án ẩn.
- `expectedDocumentIds`: nhãn retrieval; phải tham chiếu snapshot corpus hợp lệ nếu không rỗng.
- `expectedToolCalls`: danh sách lời gọi dự kiến và tham số được phép kiểm thử.
- `expectedClaims`: mô tả bằng chứng/nhãn cho người kiểm tra; không nhất thiết phải so literal với câu generator.
- `expectAbstention`: khi phải từ chối hoặc nói thiếu dữ kiện.
- `tags`: phân nhóm để theo dõi regression; giới hạn từ điển nhãn.

### Kiểm tra trước khi chạy

1. **Schema:** có đúng trường bắt buộc, loại dữ liệu đúng, không có ID trùng.
2. **Referential integrity:** document IDs được gắn với đúng `source_snapshot`/index version.
3. **Relevance của nhãn:** người đánh giá xác nhận nguồn và expected claims còn hợp lệ.
4. **Isolation:** tập test không chứa credential, PII hoặc tool endpoint production.
5. **Coverage:** có ca đúng, sai, no-context, retrieval failure, tool error và trường hợp edge.
6. **Split:** tránh dùng cùng case để tinh chỉnh prompt và chấm regression mà không ghi nhận nguy cơ overfitting.

**Chỉ ghi dataset revision `v1` là chưa đủ.** Nếu `cases.jsonl` được chỉnh mà vẫn giữ `v1`, hai lần chạy khác nhau có thể cùng mang tên một dataset. Nên chốt Git commit/content hash và quy trình tạo **revision mới** khi thay nhãn, sửa câu hỏi hoặc thay nguồn.

### Dữ liệu từ production

Nếu dùng tình huống thật, trước hết kiểm tra quyền sử dụng, ẩn danh nội dung nhạy cảm và phạm vi cho phép đối với provider judge. Tách dataset gốc được bảo vệ khỏi **synthetic test fixture** trong Git; file manifest có thể dùng `dataset_uri` hoặc content digest, không cần đưa toàn bộ nội dung vào repository.

## 6. Domain model Java độc lập với framework

Một thiết kế dễ test là dùng Java `record` cho đầu vào và kết quả. Các record dưới đây là **phần code minh họa**, có thể chia thành các file riêng trong package `evaluation.domain`.

~~~java
package com.example.aiquality.evaluation.domain;

import java.util.List;
import java.util.Map;
import java.util.Set;

public record ExpectedToolCall(
        String name,
        Map<String, String> arguments) {}

public record EvaluationCase(
        String id,
        String scenario,
        String question,
        List<String> expectedDocumentIds,
        List<ExpectedToolCall> expectedToolCalls,
        List<String> expectedClaims,
        boolean expectAbstention,
        Set<String> tags) {}

public record EvidenceChunk(
        String id,
        String text,
        Map<String, String> metadata) {}

public record RecordedToolCall(
        String name,
        Map<String, String> arguments,
        String status) {}

public record ExecutionSnapshot(
        String answer,
        List<EvidenceChunk> retrievedEvidence,
        List<RecordedToolCall> toolCalls,
        String generatorModelId,
        String promptRevision) {}
~~~

Trong project Java thực, các `public record` trên cần đặt vào **mỗi file `.java` cùng tên**. Đoạn gộp ở đây để nhìn toàn bộ contract và không nhằm được copy nguyên thành một file Java. Có thể dùng schema validation hoặc constructors kiểm tra null/blank, collection không được thay đổi sau khi tạo để bảo vệ tính bất biến.

**Vì sao không dùng `Document` trực tiếp ở domain?** `org.springframework.ai.document.Document` tiện khi giao tiếp với vector store/evaluator, nhưng domain riêng `EvidenceChunk` giúp giữ nguyên **source ID, văn bản đã truy xuất và metadata** ngay cả khi thay adapter hoặc nâng Spring AI. Việc chuyển đổi sang `Document` đặt trong adapter.

### Interface cho application workflow

~~~java
package com.example.aiquality.application;

import com.example.aiquality.evaluation.domain.ExecutionSnapshot;

public interface AnswerWorkflow {
    ExecutionSnapshot answer(String question);
}
~~~

Implementation có thể sử dụng `ChatClient`, `VectorStore` và tools. Đối với RAG, **snapshot phải chứa đúng các document thực tế được đưa vào prompt** sau filtering/reranking/truncation; chỉ lưu top-k trước reranking có thể khiến judge chấm trên nguồn khác với generator.

Trong luồng tool calling, **tool recorder** cần ghi tên tool, arguments đã chuẩn hóa, trạng thái và evidence trả về đã qua chính sách bảo vệ dữ liệu. Nếu tool có tác động thay đổi trạng thái, tests chạy bằng fake/sandbox.

## 7. Chấm xác định trước khi gọi judge

Các lỗi như gọi sai tool, sai tham số hay thiếu document ID có thể so bằng code, không cần trả tiền cho LLM-as-a-Judge.

### Ví dụ retrieval recall@k

Giả sử ground truth chứa hai tài liệu `doc-A` và `doc-B`. Retriever trả `doc-B`, `doc-C`, `doc-D` trong top 3:

\[
\operatorname{Recall@3} =
\frac{|\{\text{doc-A,doc-B}\}\cap\{\text{doc-B,doc-C,doc-D}\}|}
{|\{\text{doc-A,doc-B}\}|} = \frac{1}{2}=0.5
\]

**Recall@k** phản ánh mức tìm được tài liệu cần thiết, không phải chất lượng câu trả lời cuối cùng. Nếu case **không có expected document IDs** (ví dụ no-context hoặc tool-only), trả trạng thái `NOT_APPLICABLE` thay vì tự tính `0/0` hoặc đánh dấu retrieval failure.

~~~java
package com.example.aiquality.evaluation.scoring;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class RetrievalScorer {
    private RetrievalScorer() {}

    public static double recallAtK(
            List<String> expectedIds, List<String> retrievedIds, int k) {

        if (expectedIds == null || expectedIds.isEmpty()) {
            throw new IllegalArgumentException(
                    "Không có ground truth; báo NOT_APPLICABLE ở tầng caller");
        }
        if (k <= 0) {
            throw new IllegalArgumentException("k phải lớn hơn 0");
        }

        Set<String> expected = new HashSet<>(expectedIds);
        Set<String> actual = new HashSet<>(
                retrievedIds.stream().limit(k).toList());
        actual.retainAll(expected);
        return actual.size() / (double) expected.size();
    }
}
~~~

Unit test ví dụ, chạy được **không có API key**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;

class RetrievalScorerTest {
    @Test
    void countsGroundTruthDocumentsInTopThree() {
        double recall = RetrievalScorer.recallAtK(
                List.of("doc-A", "doc-B"),
                List.of("doc-B", "doc-C", "doc-D"), 3);

        assertEquals(0.5, recall, 0.000001);
    }
}
~~~

Với tool calls, so tên tool, arguments đã normalize theo **schema từng tool**, số lần gọi, thứ tự nếu nghiệp vụ yêu cầu và trạng thái thành công/lỗi. Không so chuỗi JSON raw nếu thứ tự key hoặc serialization không có ý nghĩa; cần so về mặt kiểu dữ liệu và business rule.

### Bảng phân vai scorer

| Tiêu chí | Phép đo | Cần judge LLM? |
|---|---|---|
 Trả đúng document ID trong top-k | Recall@k, Hit@k | Không |
 Gọi đúng `getOrderStatus` với orderId fixture | Strict tool assertions | Không |
 Có retry vượt giới hạn | Kiểm tra trace/counter | Không |
 Câu trả lời có liên quan ý định | Relevance rubric | Thường dùng judge/con người |
 Claim có được evidence hỗ trợ | Fact checking/groundedness | Judge, rules hoặc người đánh giá |
 Ngữ điệu/dễ hiểu | Rubric chất lượng | Judge/con người |

## 8. Adapter Spring AI cho relevance và fact checking

Spring AI 2.1 có interface `Evaluator` nhận `EvaluationRequest` và trả `EvaluationResponse`. Những evaluator phổ biến là `RelevancyEvaluator` và `FactCheckingEvaluator`. **Không đưa các evaluator trực tiếp vào controller trả lời**; tạo adapter để runner có thể chấm offline, lưu trạng thái và thay rubric/judge model.

### Chuyển snapshot thành request đúng ngữ cảnh

~~~java
package com.example.aiquality.evaluation.judge;

import java.util.List;
import java.util.Map;

import com.example.aiquality.evaluation.domain.EvidenceChunk;
import com.example.aiquality.evaluation.domain.ExecutionSnapshot;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;

public final class EvaluationRequestMapper {
    private EvaluationRequestMapper() {}

    public static EvaluationRequest from(
            String originalQuestion, ExecutionSnapshot snapshot) {

        List<Document> context = snapshot.retrievedEvidence().stream()
            .map(chunk -> new Document(
                chunk.id(),
                chunk.text(),
                Map.<String, Object>of("source_id", chunk.id())))
            .toList();

        return new EvaluationRequest(
                originalQuestion, context, snapshot.answer());
    }
}
~~~

Đoạn ví dụ dùng **constructor `EvaluationRequest(String, List<Document>, String)`** và `Document(String, String, Map<String,Object>)` của dòng Spring AI 2.1. Metadata trong ví dụ chỉ giữ source ID; nếu cần, mapper phải bảo toàn thêm `page`, `chunk_version`, `source_uri` đã được phép lưu.

**Quy tắc quan trọng:** danh sách context được đưa vào `EvaluationRequest` phải là tài liệu **generator thực sự thấy**, không tự fetch thêm từ vector store sau khi answer đã được tạo.

### Adapter trả kết quả có trạng thái lỗi riêng

~~~java
package com.example.aiquality.evaluation.judge;

import com.example.aiquality.evaluation.domain.ExecutionSnapshot;
import org.springframework.ai.chat.evaluation.FactCheckingEvaluator;
import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.stereotype.Component;

@Component
public class SpringAiJudgeAdapter {
    private final RelevancyEvaluator relevance;
    private final FactCheckingEvaluator factChecking;

    public SpringAiJudgeAdapter(
            RelevancyEvaluator relevance,
            FactCheckingEvaluator factChecking) {
        this.relevance = relevance;
        this.factChecking = factChecking;
    }

    public JudgeVerdict assess(String question, ExecutionSnapshot snapshot) {
        if (snapshot.retrievedEvidence().isEmpty()) {
            return new JudgeVerdict("NO_CONTEXT", null, null);
        }

        EvaluationRequest input =
            EvaluationRequestMapper.from(question, snapshot);
        try {
            boolean relevant = relevance.evaluate(input).isPass();
            boolean grounded = factChecking.evaluate(input).isPass();
            return new JudgeVerdict("COMPLETED", relevant, grounded);
        } catch (RuntimeException ex) {
            // Bên gọi ghi lỗi đã được phân loại, không ghi raw prompt/key.
            return new JudgeVerdict("EVALUATION_ERROR", null, null);
        }
    }

    public record JudgeVerdict(
            String status, Boolean relevancePass, Boolean factCheckPass) {}
}
~~~

Đoạn adapter **cố ý dành cho RAG có context**. Với tool-only, cần chuyển **tool output được phép sử dụng làm evidence** thành context hoặc dùng một rubric chuyên biệt; không kết luận một tool-only answer sai chỉ vì `retrievedEvidence` rỗng.

Các bean `RelevancyEvaluator`, `FactCheckingEvaluator` phải được cấu hình riêng với **judge model** được phép dùng. Trong Spring AI 2.1, `FactCheckingEvaluator.builder(ChatClient.Builder).build()` hỗ trợ judge phổ thông; `forBespokeMinicheck(...)` dành cho Bespoke MiniCheck. Đặt judge options và rubric rõ ràng, kiểm tra chữ ký API trong release thực tế.

**`isPass() == true`** chỉ là verdict của evaluator đang dùng. Để dùng làm release gate, cần đo độ khớp với nhãn con người, ghi judge/rubric version và xử lý các case model output không hợp lệ như **EVALUATION_ERROR**.

## 9. Evaluation runner: điều phối nhưng không trộn trách nhiệm

Runner nhận các dependency qua constructor:

~~~text
EvaluationRunner
  ├─ CaseRepository          # lấy case đã validate
  ├─ AnswerWorkflow          # sinh snapshot, có thể dùng mock
  ├─ RetrievalScorer         # recall/hit rate xác định
  ├─ ToolAssertionScorer     # tên, tham số, kết quả tool
  ├─ SpringAiJudgeAdapter    # relevance/fact checking
  ├─ EvaluationObservations  # mỗi case / mỗi giai đoạn
  └─ ReportWriter            # ghi kết quả và run manifest
~~~

### Các trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | Ảnh hưởng báo cáo |
|---|---|---|
| `PASS` | Case đạt tiêu chí đã quy định | Có trong mẫu đã chấm |
| `FAIL` | Case chấm hợp lệ nhưng không đạt | Có trong mẫu đã chấm |
| `NO_CONTEXT` | RAG không có evidence theo policy | Chấm riêng `abstention`, không tự động gộp vào FAIL |
| `EVALUATION_ERROR` | Judge timeout/429/response format sai | Đếm lỗi đo, không ngầm coi là model trả lời sai |
| `GENERATION_ERROR` | Generator/provider/tool không trả được answer hợp lệ | Đếm lỗi hệ thống; cần phân biệt với chất lượng nội dung |
| `SKIPPED` | Case không đủ điều kiện hoặc bị policy/quota loại | Phải giữ lý do và tổng số bị loại |

**Vì sao không gộp lỗi judge với FAIL?** Nếu provider judge gặp sự cố, relevance pass rate của generator có thể đột ngột giảm dù tất cả answer không thay đổi. Ngược lại, loại tất cả `EVALUATION_ERROR` khỏi mẫu số mà không ghi coverage có thể làm tỷ lệ pass trông cao giả tạo.

### Pseudocode cho một case

~~~text
case = repository.loadAndValidate(caseId)
manifest = runner.freezeRunConfiguration()

try:
    snapshot = answerWorkflow.answer(case.question)
    assert snapshot is immutable and has stable evidence IDs
    deterministic = scoreRetrievalAndTools(case, snapshot)

    if runPolicy.permitsJudge(case, snapshot):
        judge = judgeAdapter.assess(case.question, snapshot)
    else:
        judge = NOT_APPLICABLE or NO_CONTEXT (with reason)

    assessment = combineByExplicitRubric(case, deterministic, judge)
    reportWriter.append(manifest, case, snapshot, assessment, telemetryRefs)
except provider_or_runner_error:
    reportWriter.appendError(caseId, classifiedError)
~~~

**Kết hợp kết quả phải dựa trên policy có version**. Ví dụ `rag-answer-v1` đòi relevance PASS **và** groundedness PASS, nhưng `tool-calling-v1` có thể đòi tool assertion chính xác trước, sau đó mới chấm phần diễn đạt.

### Trường hợp async và retry

Nếu chạy song song nhiều case, gắn **`run_id` và `case_id`** vào bản ghi kết quả và context observability, giới hạn concurrency theo quota provider. Khi retry:

- giữ nguyên case, prompt, context/index revision và judge rubric;
- ghi attempt number, timeout/cause và chi phí phát sinh;
- đánh dấu kết quả được dùng để tổng hợp (ví dụ attempt cuối hợp lệ) bằng một quy tắc công bố trước;
- không retry vô hạn và không thực thi lại tools có side effect mà chưa có idempotency.

Để tránh ghi đè, report writer nên dùng **append-only**, phiên bản artifact hoặc transactional storage khi nhiều worker ghi đồng thời. Chỉ thực thi file cleanup cho **reports** theo chính sách; không xóa dataset gốc.

## 10. Cấu hình runner và observability theo môi trường

Spring Boot externalized configuration cho phép khai báo các tham số chung, còn resource/secret theo môi trường.

**application.yml** (đoạn minh họa):

~~~yaml
spring:
  application:
    name: ai-quality-lab
  ai:
    chat:
      client:
        observations:
          log-prompt: false
          log-completion: false
      observations:
        log-prompt: false
        log-completion: false

app:
  evaluation:
    enabled: ${EVALUATION_ENABLED:false}
    dataset-uri: ${EVALUATION_DATASET_URI:classpath:evaluation/fixtures/smoke-cases.jsonl}
    max-cases: ${EVALUATION_MAX_CASES:20}
    max-concurrency: ${EVALUATION_MAX_CONCURRENCY:2}
    max-retries: ${EVALUATION_MAX_RETRIES:1}
    mode: ${EVALUATION_MODE:offline}
    report-path: ${EVALUATION_REPORT_PATH:./reports}

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  tracing:
    sampling:
      probability: ${TRACING_SAMPLE_RATE:0.10}
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: ${OTLP_TRACES_ENDPOINT:http://localhost:4318/v1/traces}
~~~

**Chú ý:**

- `app.evaluation.*` là **custom properties**. Viết `@ConfigurationProperties(prefix="app.evaluation")` và code điều phối thì chúng mới có tác dụng; Spring AI không tự chạy evaluation job khi thấy `enabled: true`.
- `dataset-uri` có thể là classpath resource của smoke tests; dataset lớn được cấp qua đường dẫn/object store và kiểm tra checksum/version trước khi dùng.
- `report-path` phải được giới hạn quyền ghi, không dùng đường dẫn tùy ý do API client nhập vào.
- `max-cases`, `max-concurrency`, `max-retries` cần được runner thực thi và có giới hạn trên ở CI.
- `management.opentelemetry.tracing.export.otlp.endpoint` là **trace-specific OTLP endpoint**; với OTLP HTTP thường có `/v1/traces`.
- `sampling.probability` là tỷ lệ lấy mẫu tracing; môi trường lab cần trace chi tiết có thể dùng 1.0, production phải cân nhắc chi phí và chính sách dữ liệu.
- **Actuator/Prometheus chỉ có tác dụng khi project có các dependencies tương ứng** và endpoint được cấu hình bảo vệ thích hợp.

### Dependency liên quan

Ví dụ Maven cho Spring Boot 4.2/Spring AI 2.1, sau khi đã import BOM tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-starter-model-openai</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-opentelemetry</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Runner có thể chạy **test scope** hoặc một **evaluation worker application** tùy cách triển khai; nếu các class runner thuộc `src/main` nhưng phụ thuộc các thư viện chỉ có `test` scope, cần điều chỉnh kiến trúc. Đừng đưa dependency test-only vào runtime chỉ vì muốn gọi evaluator từ một HTTP endpoint.

### Cấu hình dev, CI và staging

| Môi trường | Dataset | Model/credentials | Trace export | Kiểu kiểm thử |
|---|---|---|---|---|
| Local | Fixtures nhỏ | Fake/local hoặc dev key | Local collector | Debug và smoke |
| Pull request CI | Synthetic fixtures cố định | Mock/fake, không key thật | Có thể tắt external export | Unit và deterministic assertions |
| Nightly evaluation | Dataset regression có version | Judge/generator test credentials | Tenant evaluation riêng | LLM-as-a-Judge có quota |
| Staging release | Snapshot được phê duyệt | Staging-only model/project/key | Staging backend | Regression và performance |
| Production | Dữ liệu nghiệp vụ được phép | Prod identities | Prod backend | Monitoring, canary theo policy |

Không dùng dataset production chưa được phép trên máy nhà phát triển. Cần tránh để nightly tests có quyền chạy tools sản xuất; dùng tool stubs và sandbox.

## 11. Thêm observation ở tầng evaluation

Spring AI tự tạo observations cho một số `ChatClient`, `ChatModel`, `EmbeddingModel`, vector store và tools. Nhưng framework không tự biết **một case thuộc bộ regression nào** và trạng thái `PASS/FAIL/EVALUATION_ERROR` theo policy của bạn. Do đó bổ sung một observation ở **tầng runner**.

Ví dụ dùng **Micrometer Observation**:

~~~java
package com.example.aiquality.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.Locale;
import java.util.function.Supplier;

public final class EvaluationObservations {
    private final ObservationRegistry registry;

    public EvaluationObservations(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T observeCase(
            String scenario, Supplier<T> evaluationCall) {

        Observation observation = Observation.start(
                "app.ai.evaluation.case", registry)
            .lowCardinalityKeyValue("scenario",
                    scenario.toLowerCase(Locale.ROOT));

        try (Observation.Scope ignored = observation.openScope()) {
            T result = evaluationCall.get();
            observation.lowCardinalityKeyValue("outcome", "completed");
            return result;
        } catch (RuntimeException exception) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(exception);
            throw exception;
        } finally {
            observation.stop();
        }
    }
}
~~~

Đây là **wrapper minh họa**, outcome `completed` chỉ có nghĩa callback kết thúc, **không đồng nghĩa quality PASS**. Runner cần ánh xạ trạng thái `PASS/FAIL/NO_CONTEXT/EVALUATION_ERROR` thành metric/assessment riêng, với số lượng label đã giới hạn.

**Không đưa `case_id`, `run_id`, `question`, full model response, user identifier hay raw document ID vào low-cardinality metric keys**. ID có thể lưu trong report store có bảo vệ và liên kết với trace ID qua metadata cho phép. Traces cũng cần kiểm soát attribute và sampling để tránh rò rỉ dữ liệu.

### Các điểm quan sát hữu ích

~~~text
EvaluationRun (run manifest)
└── EvaluationCase (custom Observation)
    ├── Retrieval (Spring AI VectorStore operation, nếu dùng)
    ├── Generation (ChatClient + ChatModel)
    ├── Tool execution (nếu model gọi tool)
    ├── Deterministic scoring (custom timer)
    ├── Relevance judge (ChatModel)
    ├── Fact-check judge (ChatModel)
    └── Report write (custom timer)
~~~

**Cây span thực tế** tùy framework instrumentation, xử lý bất đồng bộ và context propagation. Nếu job chạy qua queue/thread pool, phải truyền trace context đúng cách; nếu không, mọi span có thể tách thành traces rời dù cùng một case.

### Các metric đại diện

| Tên observation/metric logic | Vai trò |
|---|---|
| `spring.ai.chat.client` | Đo thời gian ChatClient/advisor pipeline |
| `gen_ai.client.operation` | Đo thao tác gọi model |
| `gen_ai.client.token.usage` | Đếm token khi provider cung cấp usage |
| `db.vector.client.operation` | Đo truy vấn và thao tác vector |
| `spring.ai.tool` | Đo thực thi tool |
| `app.ai.evaluation.case` (tự định nghĩa) | Đo thời gian một case evaluation |
| `app.ai.evaluation.outcome` (nếu tự định nghĩa) | Đếm PASS/FAIL/ERROR theo rubric và scenario |

Tên time series xuất sang Prometheus có thể khác tên observation logic; ví dụ tên có dấu chấm được chuẩn hóa và timer có hậu tố `_seconds_count`, `_seconds_sum`. **Kiểm tra tên thực trên `/actuator/metrics` hoặc `/actuator/prometheus` sau khi chạy một case**, không suy đoán metric đã xuất hiện khi chỉ khởi động app.

## 12. Tách telemetry generator, judge và công việc phụ trợ

Nếu cùng một model provider phục vụ generator và judge, thống kê chỉ theo `model_id` có thể không phân biệt hai vai trò. Runner nên ghi role có giá trị giới hạn như `generator`, `judge_relevance`, `judge_fact`, `embedding`, `tool`.

| Dimension | Dùng ở đâu | Ghi chú |
|---|---|---|
| `environment` | Metric label / resource attribute | dev, test, staging, prod |
| `role` | Metric label / trace | Danh sách đóng, số lượng nhỏ |
| `scenario` | Metric label | rag, tool, no_context |
| `outcome` | Metric label | pass, fail, skipped, error |
| `model_id` | Trace, hoặc metric label nếu tập model bị giới hạn | Tránh bùng nổ cardinality ở các model IDs tùy ý |
| `run_id`, `case_id` | Report store / trace metadata được kiểm soát | **Không** dùng làm metric label |
| `prompt_revision`, `dataset_revision` | Run manifest và report | Có thể rất nhiều; không tự động đưa vào label |

Không chỉ nhìn metric generator; judge có thể tiêu tốn nhiều tokens và gây độ trễ của **evaluation job**, dù không ảnh hưởng latency của người dùng nếu chạy offline.

### Ghi chi phí và tokens

Với mỗi lần gọi, nếu provider trả usage:

\[
C_i = \frac{T_{\mathrm{input},i}}{10^6} P_{\mathrm{input},i}
    + \frac{T_{\mathrm{output},i}}{10^6} P_{\mathrm{output},i}
\]

Trong đó đơn giá `P` tính theo **một triệu token** của model và ngày áp dụng. Chi phí một case:

\[
C_{\mathrm{case}} = C_{\mathrm{generator}} +
 C_{\mathrm{judge\_relevance}} + C_{\mathrm{judge\_fact}} +
 C_{\mathrm{embedding}} + C_{\mathrm{tool/retrieval}}
\]

Đây là mô hình cơ bản; giá có thể thay đổi theo cached input, reasoning token, batch API, retries và region. **Spring AI không tự bảo đảm mọi response có token usage hoặc tự cung cấp bảng giá**. Lưu cả **thiếu dữ liệu usage** và đơn giá/nguồn pricing trong báo cáo, không điền số 0 khi provider không báo.

Độ trễ cần đo riêng **generator request**, **judge request** và **thời gian toàn bộ batch**. Đừng cộng thời gian chấm offline vào latency trải nghiệm người dùng. So p95 chỉ khi đủ số lượng mẫu, warmup và workload tương đương.

## 13. Thiết kế report để lần chạy có thể so sánh

Một report nên có **manifest chung** và các **case results**; không chỉ lưu bảng tổng hợp.

### Run manifest (ví dụ)

~~~yaml
run_id: "eval-staging-20261127-001"
started_at: "2026-11-27T12:00:00Z"
environment: staging
git_commit: "example-commit-sha"
java_version: "21"
spring_boot_version: "4.2.0"
spring_ai_bom_version: "2.1.0"
dataset_revision: "policy-qa-v1"
dataset_sha256: "replace-with-actual-file-digest"
source_snapshot: "policy-corpus-2026-11"
index_revision: "policy-pgvector-v7"
generator_model: "provider-generator-model"
judge_model: "provider-judge-model"
prompt_revision: "answer-v1"
rubric_revision: "relevance-v1,groundedness-v1"
embedding_model: "provider-embedding-model"
runtime:
  max_concurrency: 2
  max_retries: 1
  tracing_sample_probability: 1.0
~~~

Các trường `git_commit`, `sha256`, model và timestamp trong ví dụ là **placeholder/minh họa**, phải được điền từ runtime/build thực tế. Không chứa API keys, password hoặc raw prompt trong manifest.

### Kết quả từng case (JSONL)

~~~jsonl
{"runId":"eval-staging-20261127-001","caseId":"policy-001","scenario":"rag","status":"PASS","retrievedDocumentIds":["policy-v3-chunk-07"],"retrievalRecallAt3":1.0,"relevancePass":true,"factCheckPass":true,"generatorLatencyMs":820,"judgeLatencyMs":1140,"inputTokens":410,"outputTokens":65,"tokenUsageStatus":"REPORTED"}
{"runId":"eval-staging-20261127-001","caseId":"policy-002","scenario":"no_context","status":"PASS","retrievedDocumentIds":[],"retrievalRecallAt3":null,"abstentionPass":true,"relevancePass":null,"factCheckPass":null,"tokenUsageStatus":"MISSING"}
{"runId":"eval-staging-20261127-001","caseId":"order-003","scenario":"tool","status":"EVALUATION_ERROR","toolAssertionPass":true,"relevancePass":null,"factCheckPass":null,"errorCode":"JUDGE_TIMEOUT","tokenUsageStatus":"UNKNOWN"}
~~~

**Mọi số liệu trong ví dụ là giả lập**, không phải kết quả test thực tế. `null` biểu thị **không áp dụng hoặc chưa được chấm**, không nên tự thay `null` thành `false`; thuộc tính `errorCode` giúp tách lỗi đánh giá khỏi lỗi của câu trả lời.

### Định nghĩa mẫu số công khai

Giả sử một bộ có **100 case**: 82 PASS, 8 FAIL, 5 EVALUATION_ERROR, 3 GENERATION_ERROR, 2 SKIPPED.

| Chỉ số | Công thức với dữ liệu giả lập | Ý nghĩa |
|---|---|---|
| `evaluated_pass_rate` | `82 / (82 + 8) = 91.1%` | Tỷ lệ pass **trong các case đã có verdict hợp lệ** |
| `evaluation_coverage` | `(82 + 8) / 100 = 90%` | Tỷ lệ case được chấm hợp lệ |
| `evaluation_error_rate` | `5 / 100 = 5%` | Hạ tầng/judge chấm lỗi |
| `generation_error_rate` | `3 / 100 = 3%` | Lỗi tạo đáp án |
| `skipped_rate` | `2 / 100 = 2%` | Case không chạy |

**91.1% không đồng nghĩa 91.1% của toàn bộ 100 case đã đạt**. Báo cáo phải đi cùng coverage và các tỷ lệ lỗi. Tỷ lệ pass đơn lẻ thiếu mẫu số có thể che giấu một judge backend đang lỗi hàng loạt.

Khi tính chỉ số theo từng `scenario` hoặc `tag`, cần hiển thị **số lượng case** và tránh kết luận dựa trên vài mẫu; với đánh giá có rủi ro, thêm khoảng tin cậy/kiểm định và review của con người.

## 14. Baseline, thresholds và phát hiện regression

Một baseline là kết quả đã được kiểm tra của **tổ hợp code + prompt + model + dataset + corpus/index + rubric/judge + cấu hình chạy**.

### Ví dụ policy release gate

~~~yaml
quality_gate_revision: qa-gate-v1
dataset_revision: policy-qa-v1
minimum_evaluation_coverage: 0.98
maximum_evaluation_error_rate: 0.01
minimum_retrieval_recall_at_5: 0.92
minimum_relevance_pass_rate: 0.90
minimum_fact_check_pass_rate: 0.95
maximum_generation_error_rate: 0.02
maximum_p95_generator_latency_ms: 3000
maximum_mean_estimated_cost_per_case_usd: 0.03
~~~

Những ngưỡng này **chỉ là ví dụ**. Để chọn đúng, cần baseline đã quan sát, yêu cầu sản phẩm, chi phí ngân sách, mức rủi ro câu sai và độ biến thiên phép đo. Với judge không ổn định, so một lần chạy vượt ngưỡng nhẹ không đủ để khẳng định regression; có thể lặp lại hoặc lấy mẫu con người kiểm tra.

### Phân tích nguyên nhân theo tín hiệu

| Triệu chứng | Nơi cần kiểm tra trước | Dữ liệu đối chiếu |
|---|---|---|
 Recall@k giảm, fact-check giảm | Retrieval/index/embedding | Index revision, top-k, filters, chunking, vector query trace |
 Recall@k giữ nguyên, groundedness giảm | Generator/prompt/model | Context snapshot, prompt revision, answer, judge rubric |
 Tool argument success giảm | Tool schema/prompt/pipeline | Tool recorder, expected arguments, exceptions, tool spans |
 Quality giữ nguyên, p95 tăng | Provider/retriever/tool/GC | Trace spans, concurrency, request size, tokens, retries |
 Token tăng nhưng answer không tốt hơn | Prompt/context expansion hoặc model change | Prompt template, chunk count, input/output token metrics |
 Pass rate giảm khi judge được nâng | Rubric/judge drift | Bộ calibration có nhãn con người, judge model/revision |
 Coverage giảm, nhiều EVALUATION_ERROR | Judge API/quota/timeout | Error codes, provider 429, retries và service health |

Để so **prompt A và B**, giữ dataset, judge, rubric, corpus, model, retrieval parameters và workload tương đương. Nếu nâng Spring AI/Boot hoặc thay model cùng lúc, phải ghi đây là **thay đổi nhiều biến** và không quy chênh lệch cho riêng prompt.

## 15. CI: phân tầng test nhanh và test tốn chi phí

Không nên chạy hàng trăm lời gọi judge trong mọi lần commit. Chia test thành các tầng:

| Tầng | Khi chạy | Dependency ngoài | Mục tiêu |
|---|---|---|---|
| **Unit** | Mọi commit/PR | Không | Loader, validation, scorer, schema |
| **Component/integration offline** | Mọi PR | Database test, fake provider | RAG wiring, tool schema và timeout |
| **Live AI smoke** | Manual hoặc CI được cấp phép | Provider test key | Một vài case để xác nhận model/observability |
| **Nightly regression** | Theo lịch | Dataset, model và judge test | Phát hiện đổi chất lượng, chi phí, độ trễ |
| **Release/canary evaluation** | Khi chuẩn bị release | Staging hoặc traffic sample đã được phép | So baseline và điều kiện vận hành |

### Ví dụ tránh live test chạy vô ý

~~~java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

@Tag("live-evaluation")
@EnabledIfEnvironmentVariable(
    named = "RUN_LIVE_AI_EVALUATION", matches = "true")
class LiveEvaluationTest {

    @Test
    void runsApprovedSmokeDataset() {
        // Gọi evaluation runner với fixture nhỏ,
        // provider TEST credentials và ngân sách đã cấu hình.
        // Kiểm tra verdict + coverage + error rate.
    }
}
~~~

Đây là **skeleton** thể hiện chính sách kích hoạt. Để có test hữu ích, cần inject runner, chạy fixture, xác nhận kết quả/telemetry và ghi report; đừng dùng một test method rỗng làm release gate. `@EnabledIfEnvironmentVariable` chỉ chặn method chạy khi biến chưa bật, không thay thế quản lý secrets của CI.

### Quy trình CI gợi ý

~~~mermaid
flowchart TD
  A["Pull request"] --> B["Lint dataset + validate manifest"]
  B --> C["Unit tests: scorer + loader"]
  C --> D["Component tests: fake model/vector/tool"]
  D --> E{"PASS?"}
  E -->|Không| F["Chặn merge, chỉ rõ case lỗi"]
  E -->|Có| G["Có điều kiện để chạy live evaluation"]
  G --> H["Nightly/manual: quota + sandbox credentials"]
  H --> I["Run manifest + case results + traces"]
  I --> J["Compare baseline, coverage, quality, cost/latency"]
  J --> K["Review hồi quy và phê duyệt release"]
~~~

**Để giữ tính tái lập**, CI cần dùng phiên bản JDK/Boot/Spring AI cố định, Maven/Gradle Wrapper, khóa dependency graph khi phù hợp, và lấy model/dataset/index theo revision đã công bố.

## 16. Bảo vệ dữ liệu và chống nhiễm phép đánh giá

Kết quả evaluation có thể chứa nội dung nhạy cảm dù API key đã được tách:

- **Prompt và context** có thể mang thông tin nội bộ; hạn chế lưu nguyên văn trong logs/traces.
- **Expected answer hoặc label** không được cung cấp cho generator dưới dạng hidden hints.
- **Retrieved document** có thể chứa chỉ dẫn tấn công prompt injection. Judge phải coi đó là dữ liệu cần phân tích, không coi là instruction hệ thống.
- **Tool fixtures** dùng ID giả và sandbox. Không chạy tool có tác động thật khi chấm test.
- **Dataset labels** có thể sai hoặc lỗi thời. Cần người sở hữu, quy trình review và version khi chỉnh.
- **Judge model** có thiên lệch; với ca quan trọng, đo false pass/false fail bằng nhãn người chấm.

Chỉ lưu chi tiết cần thiết để phân tích. Nếu cần lưu full context để tái hiện một lỗi, đặt trong kho riêng có quyền đọc hạn chế, mã hóa, retention và audit; report công khai chỉ giữ mã tham chiếu đã cho phép.

### Tách chất lượng model và chất lượng evaluator

Một “regression” có thể do evaluator đổi:

~~~text
Generator A + corpus C + judge J1 -> 90 PASS
Generator A + corpus C + judge J2 -> 83 PASS
~~~

Kết luận đúng ban đầu là **hai judge không đồng ý trên cùng đầu ra**. Phải đo agreement của judge với nhãn người chấm, hiệu chuẩn rubric và/hoặc chấm lại baseline; không tự nói generator kém đi.

## 17. Lỗi cấu trúc phổ biến

| Dấu hiệu | Nguyên nhân | Cách sửa |
|---|---|---|
 Case đổi nhưng `dataset_revision` giữ nguyên | Dataset không được version hóa | Sinh revision mới hoặc lưu digest, chặn sai checksum |
 Test relevance dùng context khác generator | Retriever tự chạy lại trong judge | Lưu `ExecutionSnapshot` sau generation và tái dùng đúng context |
 Test RAG pass nhưng tool gọi sai | Chỉ chấm final answer | Thêm deterministic tool assertions |
 `PASS` giảm khi judge timeout | Gộp `EVALUATION_ERROR` vào `FAIL` | Tách verdict và coverage, ghi error code |
 Metrics tạo hàng triệu series | Dùng case ID/prompt làm label | Dùng các enum role/scenario/outcome |
 Không thấy trace con của runner | Không truyền trace context sang async task | Kiểm tra context propagation/executor instrumentation |
 Chi phí judge cao bất thường | Cùng case bị gọi judge nhiều lần, retry không giới hạn | Giới hạn attempts/concurrency, ghi usage theo role |
 CI vô tình gọi tài khoản production | Test key/profile không tách | Tắt live trong PR, cấp test identity/sandbox |
 Kết quả không tái lập qua máy | JVM, BOM, model, corpus hoặc dataset khác | Run manifest + dependency graph + pin revisions |
 Không có `/actuator/prometheus` | Thiếu registry/exposure hoặc endpoint bị chặn | Kiểm tra dependencies, Actuator config và network permissions |
 Report thiếu expected source IDs | Không validate manifest/reference integrity | Kiểm tra dữ liệu trước chạy, gán `NOT_APPLICABLE` khi không có ground truth |
 Judge prompt làm sai no-context case | Chấm fact checking khi không có evidence | Nhánh xử lý abstention, không ép mọi case vào cùng evaluator |

## 18. Bài thực hành hoàn chỉnh

### Bài A — Tạo bộ dữ liệu tối thiểu

Tạo dataset 12 case trong project học:

1. **Bốn case RAG** có document ID chuẩn và câu trả lời mẫu.
2. **Ba case thiếu context** cần từ chối.
3. **Ba case tool calling** với expected tool name/arguments, gồm một tool lỗi.
4. **Hai case injection/nhiễu** buộc generator bỏ qua chỉ dẫn trong tài liệu.

Viết `manifest.yml`, `cases.jsonl` và đặt dataset revision. Viết validator kiểm tra ID trùng, format, missing reference và môi trường được phép.

**Tiêu chí đạt:** validator phát hiện ít nhất một case cố ý có ID trùng và một case tham chiếu document không tồn tại; dataset hợp lệ có thể load lại ra đúng 12 case.

### Bài B — Tách runner và scorer

Viết một `AnswerWorkflow` giả lập, trả cố định một `ExecutionSnapshot`. Sau đó:

- dùng `RetrievalScorer` tính `recall@k`;
- so tool name/arguments bằng code;
- giữ `NO_CONTEXT`, `EVALUATION_ERROR` và `FAIL` thành trạng thái riêng;
- xuất JSONL result không chứa API key, prompt nhạy cảm hoặc PII.

**Tiêu chí đạt:** toàn bộ unit tests không cần model provider, không kết nối mạng và cho kết quả xác định.

### Bài C — Thêm judge và quan sát

Với một tài khoản test được phép và quota nhỏ:

1. Cấu hình judge model độc lập với generator.
2. Chọn 3 case RAG đã được người chấm gắn nhãn PASS/FAIL.
3. Dùng `EvaluationRequest` chứa **chính context đã dùng khi sinh answer**.
4. Chạy relevance và fact checking; lưu judge model/rubric version và verdict.
5. Ghi observation theo `scenario`, `role`, `outcome`; kiểm tra metrics/traces tại backend test.
6. Tính số tokens/chi phí nếu provider trả usage; đánh dấu `MISSING` nếu không có.

**Tiêu chí đạt:** có thể liên hệ case report với telemetry của run tương ứng mà không dùng `case_id` làm metric label; judge fail và judge error không bị nhập chung.

### Bài D — Phân tích một hồi quy giả lập

Giữ nguyên dataset, model, judge và rubric; sửa retrieval top-k từ 5 xuống 1 trong **môi trường học**. Chạy lại các case RAG:

- So `retrieval_recall@k`, fact check, latency, input tokens.
- Tìm trong snapshot case nào mất tài liệu cần thiết.
- Viết một trang nhận xét có số lượng mẫu, giá trị trước/sau, nguyên nhân dự kiến và giới hạn kết luận.

Không khẳng định thay top-k luôn làm chất lượng giảm: kết quả tùy dataset, ranking, context budget và generator. Mục tiêu là luyện **quy nguyên nhân theo evidence**.

### Câu hỏi tự kiểm tra

1. Tại sao phải giữ `CaseDefinition`, `ExecutionSnapshot` và `CaseAssessment` thành ba đối tượng khác nhau?
2. Vì sao `expectedDocumentIds` không được lộ cho generator?
3. Khi `expectedDocumentIds` rỗng ở no-context case, `recall@k` nên là 0, 1 hay không áp dụng?
4. Vì sao một tool gọi sai tham số cần deterministic assertion, dù judge cho answer pass?
5. Cách tính `evaluated_pass_rate` khác `evaluation_coverage` như thế nào?
6. Phải lưu những revision nào để tái lập một hồi quy fact checking?
7. Tại sao metric không nên có tag `case_id`?
8. Thế nào là phân biệt lỗi model sinh, lỗi judge, retrieval failure và chất lượng câu trả lời?

**Gợi ý:** (1) dữ liệu chuẩn, bằng chứng chạy và kết quả đo phải độc lập; (2) tránh rò nhãn/đáp án; (3) `NOT_APPLICABLE`; (4) hành vi tool là contract có thể kiểm tra bằng code; (5) pass trên case có verdict khác tỷ lệ case được chấm; (6) dataset, corpus/index, generator, prompt, judge/rubric, framework và tool schema; (7) cardinality cao và nguy cơ lộ ID; (8) các trạng thái và error code tách biệt.

## 19. Checklist trước khi chấp nhận một pipeline evaluation

- [ ] Có cấu trúc package tách production flow khỏi loader/scorer/judge/report.
- [ ] Dataset được version hóa, schema rõ, source IDs hợp lệ và có case âm tính.
- [ ] Runner giữ **execution snapshot** bất biến và dùng cùng context khi gọi judge.
- [ ] Retrieval và tool contract được chấm deterministic khi có thể.
- [ ] Relevance/fact checking có rubric, judge model và phiên bản riêng.
- [ ] Có trạng thái `PASS`, `FAIL`, `NO_CONTEXT`, `GENERATION_ERROR`, `EVALUATION_ERROR`, `SKIPPED`.
- [ ] Run manifest có Git commit, dependency versions, dataset/model/prompt/index/rubric revisions.
- [ ] Metrics, traces, token usage, chi phí và latency có phân tách vai trò và môi trường.
- [ ] Không gắn case ID, prompt, user ID hay secrets vào metric labels.
- [ ] PR tests offline; live evaluation có test credential, quota, giới hạn retry và phê duyệt phù hợp.
- [ ] Báo cáo có mẫu số, coverage, error rate và đủ dữ liệu để chẩn đoán regression.
- [ ] Baseline được chốt; thay đổi nhiều biến phải được ghi nhận rõ.

## Tài liệu tham khảo chính thức

1. [Spring AI 2.1 — Project Setup](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/get-started/project-setup.html): BOM, dependency và ma trận Spring Boot 4.2.
2. [Spring AI 2.1 — Evaluators](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/evaluation/evaluators.html): `Evaluator`, `RelevancyEvaluator`, `FactCheckingEvaluator` và `EvaluationRequest`.
3. [Spring AI — EvaluationRequest JavaDoc](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/evaluation/EvaluationRequest.html): constructor dùng `List<Document>` ở dòng 2.1.
4. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient/ChatModel, VectorStore, tool và metrics/token usage.
5. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) và [Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Actuator, Micrometer, tracing với OpenTelemetry/OTLP.
6. [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): resource attributes, exporters và quản lý signals.
7. [Micrometer — Observation Concepts](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): API `ObservationRegistry`, scopes và cardinality của key-values.
8. [JUnit 5 — Conditional Test Execution](https://junit.org/junit5/docs/current/user-guide/#writing-tests-conditional-execution): `@EnabledIfEnvironmentVariable` và kiểm soát live tests.
9. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): tránh đưa secrets, personal data và credentials vào logs.

> **Ghi nhớ:** Một evaluation đáng tin cậy bắt đầu từ **cấu trúc mã và dữ liệu đúng**. Tách tình huống chuẩn, snapshot chạy, phép chấm, telemetry và báo cáo theo version; nhờ đó khi relevance, fact checking, tool success, token cost hoặc latency đổi, nhóm có đủ bằng chứng để tìm đúng nguyên nhân thay vì chỉ nhìn một tỷ lệ PASS.
