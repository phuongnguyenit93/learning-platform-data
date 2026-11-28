# Đánh giá theo từng nhóm nghiệp vụ và độ khó

> **Chương:** So sánh thí nghiệm
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm chất lượng giữa các phiên bản prompt, model và pipeline.
>
> **Ngữ cảnh kỹ thuật:** Java 21, Spring Boot 4.2.x, Spring AI 2.1.x. Ví dụ trong bài sử dụng dữ liệu tổng hợp; mọi số liệu là minh họa, không phải kết quả đo hệ thống thật.

## 1. Vấn đề: điểm trung bình tốt hơn nhưng nghiệp vụ quan trọng tệ hơn

Giả sử nhóm vừa cập nhật prompt cho một trợ lý RAG hỗ trợ ba loại nghiệp vụ: **tra cứu chính sách**, **trạng thái đơn hàng** và **hướng dẫn hỗ trợ kỹ thuật**. Kết quả kiểm thử A/B trên cùng 100 tình huống:

- Baseline A: **78/100** case đạt.
- Candidate B: **80/100** case đạt.

Nhìn vào điểm chung, B tăng **2 điểm phần trăm**. Nhưng khi tách nhóm, B lại làm **chính sách** giảm từ 90% xuống 85% — một thay đổi có thể rất đáng lo nếu nhóm này bao gồm quy định có hiệu lực hoặc yêu cầu tuân thủ. Một bản tổng hợp duy nhất đã **che khuất hồi quy nghiệp vụ**.

Tương tự, B có thể tốt trên câu hỏi dễ nhưng sai ở những câu **cần đối chiếu nhiều nguồn** hoặc **phải gọi tool theo thứ tự**. Người dùng không quan tâm bot có 80% PASS chung nếu nó thất bại chính ở trường hợp họ đang cần.

Phương pháp của bài: **định nghĩa nhóm nghiệp vụ (business slices) và độ khó trước khi chạy**, giữ nhãn ổn định, so A/B theo cùng case ID rồi báo cáo cả **chất lượng, coverage, độ bất định, lỗi kỹ thuật, chi phí và độ trễ** cho từng slice.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Thiết kế taxonomy nhóm nghiệp vụ phản ánh mục tiêu sản phẩm và mức rủi ro, không dựa vào tên gọi tùy tiện sau khi thấy kết quả.
2. Xây rubric xác định **độ khó nội tại của tình huống** qua lượng evidence, số bước suy luận, độ nhiễu, tool dependencies và độ mơ hồ.
3. Gắn nhãn một case với nhóm nghiệp vụ, mức khó, scenario, rủi ro và phiên bản nhãn; tránh rò đáp án cho generator.
4. Tính **micro**, **macro**, **business-weighted** pass rate, coverage và paired delta đúng mẫu số.
5. Nhận ra **Simpson's paradox**, sai lệch do cơ cấu mẫu, mất verdict và nhiều slice nhỏ.
6. Viết bộ tổng hợp theo **business group × difficulty** bằng Java 21 và kiểm tra bằng JUnit.
7. So retrieval/tool behavior, relevance/fact checking, token/chi phí/latency trong cùng slice.
8. Đề xuất quality gate và quyết định phát hành có quan tâm đến những nhóm quan trọng, khó và ít dữ liệu.

## 2. Hai trục phân tầng không được trộn lẫn

### Trục A — Nhóm nghiệp vụ

Nhóm nghiệp vụ trả lời: **Người dùng đang muốn hoàn thành công việc gì?**

| Nhóm | Mục tiêu | Ground truth chủ đạo | Rủi ro khi sai |
|---|---|---|---|
| `policy` — tra cứu chính sách | Hỏi quy định đang có hiệu lực, thời hạn, điều kiện | Văn bản hiệu lực, đoạn nguồn, ngày áp dụng | Hiểu sai quy định |
| `orders` — trạng thái đơn hàng giả lập | Xem vận chuyển hoặc lịch sử xử lý | Tool output từ sandbox, hợp đồng API | Báo nhầm trạng thái |
| `tech_support` — hỗ trợ kỹ thuật | Xác định nguyên nhân lỗi, đề xuất bước xử lý | Runbook, KB, phiên bản phần mềm, chuỗi kiểm tra | Hướng dẫn không hiệu quả hoặc thao tác sai |

Trong dự án thật, nhóm nghiệp vụ phải được thống nhất với **product owner và chuyên gia lĩnh vực**. Một nhóm có nhiều loại hành vi AI: tra cứu chính sách có thể dùng RAG, đơn hàng dùng tool, còn hỗ trợ kỹ thuật có thể cần cả RAG và tool.

### Trục B — Độ khó tình huống

Độ khó trả lời: **Để trả lời đúng với bằng chứng hợp lệ, hệ thống cần xử lý phức tạp đến mức nào?**

| Mức | Dấu hiệu điển hình | Ví dụ |
|---|---|---|
| `easy` — dễ | Một chứng cứ rõ, một thao tác đơn giản, ít nhiễu, câu hỏi cụ thể | “Theo văn bản A, hạn nộp là ngày nào?” |
| `medium` — trung bình | Cần so hai nguồn, lọc theo hiệu lực hoặc một tool call có validation | “Chính sách nào áp dụng cho đơn đã tạo trước mốc X?” |
| `hard` — khó | Nhiều bước phụ thuộc, nguồn mâu thuẫn, ngoại lệ, nhiều lần truy xuất/tool, ambiguity đáng kể | “Kết hợp quy định mới, lịch sử trạng thái và ngoại lệ để giải thích cách xử lý” |

**Độ khó không phải một thuộc tính do model đang thử quyết định.** Không được gán `hard` chỉ vì candidate B trả sai hoặc chậm. Làm vậy sẽ tạo nhãn hậu nghiệm (*post-treatment labeling*) và làm mất tính so sánh.

### Những trục khác cần giữ riêng

- **Scenario:** `rag`, `tool`, `rag_tool`, `no_context`.
- **Risk tier:** `low`, `medium`, `high` — hậu quả nghiệp vụ nếu answer sai.
- **Evidence availability:** đủ nguồn, nguồn thiếu, nguồn có mâu thuẫn.
- **Language/style:** tiếng Việt, thuật ngữ chuyên ngành, câu hỏi ngắn hoặc dài.

`hard` **không đồng nghĩa** `high risk`: một câu hỏi đơn giản “có được thanh toán khoản này không?” có thể dễ về suy luận nhưng rất nhạy cảm về rủi ro; một câu phân tích log phức tạp có thể khó nhưng rủi ro thấp trong môi trường demo.

## 3. Một rubric độ khó có thể áp dụng trước khi chạy

Thay vì hỏi reviewer “câu này cảm giác khó không?”, thiết kế các **dấu hiệu có thể ghi lại bằng bằng chứng**:

| Trục | 0 điểm | 1 điểm | 2 điểm |
|---|---|---|---|
| Evidence span | Một đoạn trực tiếp | Hai nguồn hoặc đoạn cần kết hợp | Từ ba nguồn/đoạn phụ thuộc trở lên |
| Reasoning hops | Đọc và trích xuất | Một bước suy luận hoặc đối chiếu | Nhiều bước có phụ thuộc |
| Retrieval distractors | Không có nguồn gây nhiễu | Có nguồn gần giống | Nguồn mâu thuẫn/phiên bản cũ dễ bị nhầm |
| Tool dependencies | Không tool hoặc đọc một kết quả rõ | Một tool + validation hoặc một nhánh điều kiện | Nhiều tool/bước có dependency |
| Ambiguity/exception | Hỏi cụ thể, không ngoại lệ | Có một điều kiện hoặc câu hỏi hơi mơ hồ | Có ngoại lệ/điều kiện mâu thuẫn cần làm rõ |

Một quy ước **minh họa** cho tổng điểm `S`:

\[
S = E + H + R + T + A,\qquad 0 \le S \le 10
\]

| Phân loại | Điểm mẫu | Cần xem thêm |
|---|---:|---|
| `easy` | 0–2 | Câu hỏi có thật sự đủ bằng chứng không? |
| `medium` | 3–5 | Các bước suy luận và retrieval rõ ràng chưa? |
| `hard` | 6–10 | Có đủ nguồn, ngoại lệ và expected claims được chuyên gia review? |

**Các trọng số/ngưỡng hoàn toàn do project định nghĩa**. Đừng gọi đây là thang chuẩn của Spring AI. Nếu một nghiệp vụ không dùng tools, có thể điều chỉnh rubric hoặc thay trục tool bằng thao tác nghiệp vụ khác; phải **version hóa rubric** và giữ nhất quán trong cùng phép so sánh.

### Những lỗi khi gán độ khó

1. **Dùng latency của model để gán khó:** bot chậm có thể do mạng hoặc quota, không phải độ khó nội tại.
2. **Dùng outcome của candidate để gán khó:** case chuyển nhóm sau khi B fail, khiến số liệu có lợi cho một arm.
3. **Dùng token count của answer làm khó:** câu trả lời dài có thể do verbosity, không phải reasoning complexity.
4. **Xem no-context luôn là hard:** từ chối khi thiếu nguồn là một *scenario/criterion riêng*, có thể dễ hoặc khó tùy độ mơ hồ.
5. **Xem nhiều document luôn khó:** ba đoạn dư thừa có thể dễ hơn một điều khoản ngoại lệ khó đọc.

Với dữ liệu lớn, dùng hai reviewer gán nhãn một tập mẫu, đo **tỷ lệ đồng thuận** và giải quyết các trường hợp bất đồng. Có thể báo Cohen's kappa/weighted kappa với nhãn ordinal nếu phù hợp. Lưu `difficulty_rubric_revision`, reviewer policy và ngày xét nhãn, không cần lưu thông tin cá nhân reviewer trong dataset công khai.

## 4. Từ rubric thành schema cho từng case

Một case cần tách **metadata phân tầng** khỏi **ground truth đánh giá** và khỏi **kết quả model**.

### Ví dụ `cases.jsonl` với dữ liệu tổng hợp

~~~jsonl
{"id":"pol-001","businessGroup":"policy","difficulty":"easy","scenario":"rag","riskTier":"high","question":"Hạn nộp báo cáo tháng trong quy định hiện hành?","expectedDocumentIds":["policy-v4-chunk-05"],"expectedClaims":["Trước ngày 05 tháng kế tiếp"],"difficultySignals":{"evidence":0,"reasoning":0,"distractors":0,"tools":0,"ambiguity":0},"tags":["deadline"]}
{"id":"pol-002","businessGroup":"policy","difficulty":"hard","scenario":"rag","riskTier":"high","question":"Nếu thời hạn nộp trùng ngày nghỉ và quy định mới có ngoại lệ thì hạn nào áp dụng?","expectedDocumentIds":["policy-v4-chunk-05","policy-v4-chunk-12","calendar-fixture-02"],"expectedClaims":["Áp dụng đúng ngoại lệ và ngày hiệu lực"],"difficultySignals":{"evidence":2,"reasoning":2,"distractors":1,"tools":0,"ambiguity":2},"tags":["multi-hop","exception"]}
{"id":"ord-003","businessGroup":"orders","difficulty":"medium","scenario":"tool","riskTier":"medium","question":"Đơn TEST-003 đã được giao chưa?","expectedToolCalls":[{"name":"getOrderStatus","arguments":{"orderId":"TEST-003"}}],"expectedClaims":["Đang vận chuyển"],"difficultySignals":{"evidence":0,"reasoning":1,"distractors":0,"tools":1,"ambiguity":1},"tags":["sandbox"]}
{"id":"sup-004","businessGroup":"tech_support","difficulty":"hard","scenario":"rag_tool","riskTier":"medium","question":"Vì sao dịch vụ giả lập bị lỗi sau nâng phiên bản và bước khôi phục nào hợp lệ?","expectedDocumentIds":["runbook-v3-08","changelog-v2-11"],"expectedToolCalls":[{"name":"getServiceHealth","arguments":{"serviceId":"SVC-DEMO"}}],"expectedClaims":["Bước xác minh phiên bản và trạng thái trước khôi phục"],"difficultySignals":{"evidence":1,"reasoning":2,"distractors":1,"tools":2,"ambiguity":1},"tags":["diagnostics","multi-step"]}
{"id":"pol-005","businessGroup":"policy","difficulty":"easy","scenario":"no_context","riskTier":"high","question":"Ai duyệt tài liệu chưa công bố X?","expectedDocumentIds":[],"expectedClaims":[],"expectAbstention":true,"difficultySignals":{"evidence":0,"reasoning":0,"distractors":0,"tools":0,"ambiguity":1},"tags":["abstention"]}
~~~

Ở ví dụ `pol-005`, scenario `no_context` không mặc định là hard: tổng điểm bằng 1 nên mức `easy` phù hợp với rubric đã công bố. Nếu reviewer đổi nhãn thành `medium` mà không thay tín hiệu hoặc không có override hợp lệ, validator cần **phát hiện mâu thuẫn** trước khi đóng băng dataset.

### Manifest khóa phiên bản

~~~yaml
dataset_id: "ai-business-slices-demo"
dataset_revision: "v1"
schema_version: 1
case_content_sha256: "sha256:replace-with-actual-digest"
case_count: 5
split: "held-out-regression"
language: vi
business_taxonomy_revision: "biz-groups-v1"
difficulty_rubric_revision: "difficulty-0-to-10-v1"
label_revision: "domain-reviewed-v2"
ground_truth_corpus_revision: "corpus-fixture-v7"
allowed_environments: [test, staging]
business_groups: [policy, orders, tech_support]
difficulties: [easy, medium, hard]
scenarios: [rag, tool, rag_tool, no_context]
~~~

`content_sha256` là checksum **phải được tính thật** từ artifact đã chốt; chuỗi ví dụ ở trên không được coi là hash hợp lệ. Metadata taxonomy, rubric và labels cũng phải có revision/digest tương ứng trong hệ thống thực tế.

**Quan trọng:** manifest trên mô tả **5 case JSONL minh họa**. Ma trận **100 case ở mục 6** là một bộ số liệu giả lập khác để thực hành tính điểm; không sử dụng manifest năm case cho ma trận này. Validator phải báo `case_count mismatch` nếu nội dung file và trường `case_count` khác nhau.

## 5. Chuẩn hóa taxonomy nghiệp vụ

Một taxonomy tốt có các đặc điểm:

- **Giá trị đóng và có chủ sở hữu:** `policy`, `orders`, `tech_support`; không cho phép nhập chuỗi tùy ý như `"Nhóm khách hàng rất khó hôm nay"`.
- **Primary group rõ ràng:** một case thuộc một nhóm chính phục vụ tổng hợp không trùng lặp.
- **Tags phụ có thể nhiều:** `multi-hop`, `distractor`, `tool_error`, `no_context`. Tag phân tích không thay thế primary group.
- **Tiêu chí gán nhóm độc lập với answer:** xem mục đích câu hỏi và workflow thật, không hỏi “model nào giải được”.
- **Có phiên bản:** khi chuyển case từ `policy` sang `tech_support`, phát hành taxonomy/label revision mới hoặc báo cách re-map.
- **Không mặc định nhóm theo danh tính người dùng:** nhóm nghiệp vụ dựa trên **nhiệm vụ**, tránh suy đoán đặc điểm nhạy cảm và bảo vệ dữ liệu cá nhân.

### Nghiệp vụ chồng lấn

Một câu “Đơn hàng bị trễ; chính sách hoàn phí là gì?” vừa có dữ liệu `orders`, vừa cần `policy`.

Hai lựa chọn hợp lệ:

1. **Primary group** theo mục tiêu chính, ví dụ `orders`, và tag `policy_dependency`.
2. **Multi-label phân tích:** giữ cả `orders` và `policy` trong tag thứ cấp, nhưng **không cộng một case hai lần** khi tính micro overall.

Trong báo cáo, ghi rõ metric là **theo primary group** hay **theo tag (chồng lấn)**. Với tag chồng lấn, tổng số trong bảng từng tag có thể lớn hơn tổng số case; không dùng tổng đó làm mẫu số overall.

## 6. Phân phối bộ kiểm thử: không lấy dữ liệu dễ làm mẫu đại diện

Có ít nhất ba cách xây tập case:

| Thiết kế mẫu | Tác dụng | Giới hạn |
|---|---|---|
| **Theo phân phối sử dụng (traffic-based)** | Ước lượng chất lượng trải nghiệm trung bình của workload hiện tại | Nhóm hiếm nhưng rủi ro cao có thể thiếu mẫu |
| **Cân bằng theo slice** | Phát hiện lỗi ở mỗi nhóm nghiệp vụ/độ khó | Không phản ánh trực tiếp tỷ lệ traffic thực |
| **Tăng mẫu nhóm khó/rủi ro (oversampling)** | Phát hiện regression hiếm, tăng độ chính xác trong slice trọng yếu | Nếu tính micro raw, điểm tổng có thể bị lệch khỏi traffic |

Không có một cách lấy mẫu phù hợp cho mọi câu hỏi. Nên có **regression suite cố định** (để so A/B) và **monitoring sample** (để quan sát traffic thực đã được phép xử lý). Hai tập phục vụ mục đích khác nhau và có thể có weights khác nhau.

### Thiết kế ma trận nhóm × mức khó

Ví dụ một bộ 100 case dùng cho chương này:

| Nhóm | Easy | Medium | Hard | Tổng |
|---|---:|---:|---:|---:|
| Policy | 30 | 20 | 10 | 60 |
| Orders | 10 | 10 | 10 | 30 |
| Tech support | 2 | 3 | 5 | 10 |
| **Tổng** | **42** | **33** | **25** | **100** |

Số case cho `tech_support/easy` chỉ có **2** nên không đủ để đưa ra quyết định chắc chắn về phân nhóm đó. Phép so sánh có thể vẫn liệt kê số liệu, nhưng cần cảnh báo `SMALL_N` và thu thập thêm khi nhóm này quan trọng.

**Nguyên tắc:** định trước minimum sample per slice và **không tự sinh kết luận mạnh** từ tỷ lệ 100% trên 1 hoặc 2 case.

## 7. Phân biệt ba phép chấm: kỹ thuật, retrieval/tool và nội dung

Trong ứng dụng Spring AI, không nên nén mọi loại outcome thành một `qualityPass` chung mà không ghi điều kiện.

| Lớp | Kiểm gì? | Cách đo |
|---|---|---|
| **Execution** | Model, vector DB và tool có hoàn tất hợp lệ? | `COMPLETED`, `GENERATION_ERROR`, `TOOL_ERROR`, timeout |
| **Deterministic behavior** | Retrieval đúng nguồn, tool đúng tên/args/schema? | Recall@k, hit@k, assertions |
| **Answer quality** | Có liên quan và được evidence hỗ trợ? | Relevance, fact checking, abstention rubric, human review |
| **Observability** | Mất bao lâu, bao nhiêu token/chi phí, lỗi ở bước nào? | Micrometer metrics/traces và report per case |

### Spring AI Evaluators có trách nhiệm gì?

Spring AI 2.1 cung cấp interface `Evaluator` nhận `EvaluationRequest`. Hai loại phổ biến:

- `RelevancyEvaluator`: chấm answer có phù hợp question và retrieved context.
- `FactCheckingEvaluator`: chấm claim có được tài liệu cung cấp hỗ trợ.

Ví dụ Java minh họa cho case RAG:

~~~java
import java.util.List;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;

String question = "Hạn nộp báo cáo tháng là khi nào?";
List<Document> evidenceActuallyUsed = List.of(
        new Document("Báo cáo phải nộp trước ngày 05 tháng kế tiếp."));
String generatedAnswer = "Trước ngày 05 của tháng tiếp theo.";

EvaluationRequest request = new EvaluationRequest(
        question, evidenceActuallyUsed, generatedAnswer);
// Chuyển request sang RelevancyEvaluator / FactCheckingEvaluator
// với judge model và rubric được khóa cho cả hai arm.
~~~

Đây là **fragment code**, không phải chương trình Java độc lập. Với RAG thật, `evidenceActuallyUsed` phải chứa **chính context generator đã đọc**, sau filter/reranking/truncation; không để judge tự chạy retrieval lại, vì có thể nhận tài liệu khác.

**Không có phép chấm “đúng cho mọi scenario”:** case tool-only có thể thiếu retrieved documents nhưng vẫn có tool evidence; case no-context phải được chấm theo rubric **abstention**, không ép vào fact checking trên một context rỗng. Luôn xác định `eligibleCases` theo **metric và slice**.

## 8. Khóa điều kiện A/B trước khi chia nhóm

Phân tầng không thay thế các điều kiện của paired comparison:

~~~mermaid
flowchart TD
    D["Dataset + taxonomy + difficulty rubric bất biến"] --> A["Baseline A"]
    D --> B["Candidate B"]
    A --> EA["Snapshot/evidence A"]
    B --> EB["Snapshot/evidence B"]
    EA --> JA["Cùng evaluation policy"]
    EB --> JB["Cùng evaluation policy"]
    JA --> PA["Kết quả A theo case ID"]
    JB --> PB["Kết quả B theo case ID"]
    PA --> J["Join theo dataset_revision + case_id"]
    PB --> J
    J --> S["Slice business_group × difficulty"]
    S --> M["Quality, coverage, paired delta, cost, latency"]
    M --> G["Quality gate + human review"]
~~~

Với thí nghiệm **prompt/generator**, nên dùng **frozen-context comparison** để hai arm nhận cùng evidence.

Với thí nghiệm **retriever/reranker**, dùng **end-to-end comparison**: cho hai arm truy xuất context khác nhau theo thiết kế; judge phải chấm answer A theo evidence A, answer B theo evidence B. Nếu thay cả embedding, chunking và model, hãy ghi là **pipeline bundle comparison**, không quy hiệu quả riêng cho prompt.

### Giữ các biến này nhất quán

| Biến | Vì sao quan trọng |
|---|---|
| Dataset/labels/taxonomy/difficulty revisions | Hai arm phải so cùng tình huống và cùng phân tầng |
| Generator model/options | Model/provider và sampling ảnh hưởng câu trả lời |
| Prompt revision | Có thể là biến chủ đích; ghi rõ |
| Corpus/index/embedding/top-k | Quyết định context trong RAG |
| Tool schema/fixtures/permissions | Quyết định hành vi công cụ |
| Judge model/rubric/thresholds | Quyết định PASS/FAIL, có thể drift |
| Timeouts/concurrency/retries | Ảnh hưởng coverage, latency và chi phí |
| Build/JDK/Boot/Spring AI versions | Có thể thay hành vi framework |

Một run manifest không được chứa API keys, raw credential hoặc dữ liệu riêng tư ngoài phạm vi được phép.

## 9. Bộ số liệu giả lập: nhìn theo nghiệp vụ và mức khó

Dùng 100 case trong ma trận tại mục 6. Giả sử **cả A/B đều được chấm hợp lệ trên đủ 100 case**, verdict theo cùng rubric:

| Business group | Difficulty | Số case | A PASS | B PASS |
|---|---|---:|---:|---:|
| Policy | Easy | 30 | 28 | 27 |
| Policy | Medium | 20 | 19 | 18 |
| Policy | Hard | 10 | 7 | 6 |
| Orders | Easy | 10 | 9 | 10 |
| Orders | Medium | 10 | 7 | 8 |
| Orders | Hard | 10 | 5 | 6 |
| Tech support | Easy | 2 | 1 | 2 |
| Tech support | Medium | 3 | 1 | 1 |
| Tech support | Hard | 5 | 1 | 2 |
| **Tổng** | — | **100** | **78** | **80** |

### Tổng hợp theo nghiệp vụ

| Nhóm | A | B | Delta |
|---|---:|---:|---:|
| Policy (60 case) | 54/60 = 90% | 51/60 = 85% | **−5 điểm phần trăm** |
| Orders (30 case) | 21/30 = 70% | 24/30 = 80% | +10 điểm phần trăm |
| Tech support (10 case) | 3/10 = 30% | 5/10 = 50% | +20 điểm phần trăm |
| **Overall (100 case)** | **78%** | **80%** | **+2 điểm phần trăm** |

B tốt hơn overall, **nhưng giảm cả ba mức khó trong nhóm policy**. Nếu policy có rủi ro nghiệp vụ cao, đây có thể là lý do **chặn release** dù điểm tổng tăng.

### Tổng hợp theo độ khó

| Mức | Số case | A PASS | B PASS | Diễn giải |
|---|---:|---:|---:|---|
| Easy | 42 | 38/42 = 90,5% | 39/42 = 92,9% | Tăng nhẹ, nhóm nhiều mẫu |
| Medium | 33 | 27/33 = 81,8% | 27/33 = 81,8% | Không đổi |
| Hard | 25 | 13/25 = 52% | 14/25 = 56% | Tăng 4 điểm phần trăm |

Đây là **hai cách phân tầng của cùng 100 case**, không phải hai bộ test độc lập. Một bản báo cáo tốt cần có **bảng chi tiết business × difficulty**, vì tổng hợp theo độ khó có thể che việc policy-hard giảm từ 7/10 xuống 6/10.

## 10. Micro, macro và weighted metrics: cùng dữ liệu nhưng câu hỏi khác

### 10.1. Micro average — mỗi case có trọng số như nhau

Với các slice loại trừ lẫn nhau, tính:

\[
\mathrm{MicroPassRate}
= \frac{\sum_g N_{g,\mathrm{PASS}}}
{\sum_g N_{g,\mathrm{evaluated}}}
\]

Ở ví dụ:

\[
\mathrm{Micro}_A=78/100=78\%,\qquad
\mathrm{Micro}_B=80/100=80\%.
\]

Micro phản ánh **cơ cấu case thực sự trong dataset**, không tự chứng minh tương ứng với cơ cấu traffic hay rủi ro kinh doanh.

### 10.2. Macro average — mỗi nhóm ngang trọng số

\[
\mathrm{MacroPassRate}
=\frac{1}{G}\sum_{g=1}^{G}
\frac{N_{g,\mathrm{PASS}}}{N_{g,\mathrm{evaluated}}}
\]

Với ba nhóm nghiệp vụ:

\[
\mathrm{Macro}_A=(90+70+30)/3=63.3\%
\]

\[
\mathrm{Macro}_B=(85+80+50)/3=71.7\%.
\]

Macro cho các nhóm nghiệp vụ **trọng số như nhau**, dù `policy` có 60 case và `tech_support` chỉ 10. Nó hữu ích để tránh một nhóm lớn che tất cả nhóm nhỏ, nhưng có thể **rất bất ổn** nếu nhóm nhỏ chỉ có vài case.

### 10.3. Weighted average — cân theo traffic hoặc mức ưu tiên đã chốt

\[
\mathrm{WeightedPassRate}
= \sum_g w_g\,\mathrm{PassRate}_g,
\quad w_g\ge0,\quad \sum_g w_g=1
\]

Giả sử doanh nghiệp đăng ký trước weights `policy=0.50`, `orders=0.30`, `tech_support=0.20`:

\[
\mathrm{Weighted}_A
=0.5(0.90)+0.3(0.70)+0.2(0.30)
=0.72=72\%.
\]

\[
\mathrm{Weighted}_B
=0.5(0.85)+0.3(0.80)+0.2(0.50)
=0.765=76.5\%.
\]

**Weights này chỉ minh họa.** Nếu được suy ra từ traffic, lưu nguồn dữ liệu, giai đoạn và `weight_revision`; nếu dựa trên rủi ro, ghi rõ nguyên tắc kinh doanh. **Không đổi trọng số sau khi thấy kết quả** để làm một arm trông đẹp hơn.

### Khi nào dùng chỉ số nào?

| Chỉ số | Trả lời câu hỏi | Rủi ro diễn giải |
|---|---|---|
| Micro | Trên tập case hiện tại, bao nhiêu phần trăm đạt? | Bị chi phối bởi nhóm có nhiều case |
| Macro business | Nếu mỗi nhóm quan trọng ngang nhau, trung bình thế nào? | Nhóm ít mẫu gây dao động |
| Weighted | Với mục tiêu traffic hoặc business priority, hiệu quả là bao nhiêu? | Dựa vào weights có thể gây tranh luận |
| Per-slice | Nhóm nào tốt/xấu đi? | Nhiều slices nhỏ, multiple comparisons |
| Worst-slice + guardrails | Có nhóm quan trọng nào suy giảm quá mức? | Dễ nhiễu nếu không đặt minimum sample |

**Không dùng macro trên tập tags đa nhãn rồi gọi nó là average trên các nhóm độc lập**: một case có thể nằm ở nhiều tags và gây double-counting.

## 11. Simpson's paradox và cơ cấu mẫu thay đổi

Một điều nghịch lý có thể xảy ra khi hai run **không dùng cùng tập case**: B tốt hơn **trong từng nhóm**, nhưng điểm overall thấp hơn do B có nhiều câu khó hơn.

Ví dụ hai run không ghép cặp, cùng tổng cộng 110 câu nhưng cơ cấu khác:

| Nhóm | Run A | Tỷ lệ A | Run B | Tỷ lệ B |
|---|---:|---:|---:|---:|
| Easy | 90 PASS / 100 | 90% | 10 PASS / 10 | **100%** |
| Hard | 4 PASS / 10 | 40% | 50 PASS / 100 | **50%** |
| **Overall** | **94 / 110** | **85,5%** | **60 / 110** | **54,5%** |

**B tốt hơn trong cả easy và hard**, nhưng overall thấp hơn vì B có 100 câu hard, A chỉ có 10. Đây là một ví dụ của **Simpson's paradox** do phân phối nhóm không tương đương.

Kết luận:

1. Nếu mục tiêu là **so chất lượng model**, dùng **cùng case IDs** và, khi phù hợp, paired comparison.
2. Nếu mục tiêu là **chất lượng trên traffic thực**, cơ cấu câu hỏi có thể thay đổi theo thời gian; báo riêng cơ cấu mẫu và dùng **weights cố định** khi muốn chuẩn hóa.
3. **Không trộn hai run có số mẫu khác nhưng gọi là paired A/B.**
4. Nếu dataset giống nhau nhưng B bị thiếu verdict ở các case hard, tỷ lệ chỉ trên những case còn chấm được cũng có thể bị thiên lệch.

Với **dataset giống nhau và đủ verdict của cả hai arm**, cơ cấu các nhóm **không thể tự đổi giữa A/B**. Khi đó nghịch lý trên **không phải** lý do khiến cùng một bộ case có điểm overall khác; hãy kiểm tra kết quả, weights, mẫu số và cách nhóm.

## 12. Coverage theo từng nhóm quan trọng không kém PASS rate

Một case có thể:

- `COMPLETED + PASS`: generator trả lời và đáp án đạt rubric.
- `COMPLETED + FAIL`: generator hoàn tất nhưng nội dung không đạt.
- `GENERATION_ERROR + NOT_EVALUATED`: provider, tool hoặc parser sinh lỗi.
- `COMPLETED + EVALUATION_ERROR`: answer có nhưng judge timeout/429/parse verdict lỗi.
- `NO_CONTEXT`: RAG thiếu evidence, cần đánh giá riêng *abstention* theo policy.
- `SKIPPED`: case không chạy vì quota/policy/điều kiện môi trường.

Đối với mỗi **slice s** và **metric m**, hãy xác định tập `Eligible(s,m)` trước khi tính.

\[
\mathrm{Coverage}_{s,m}=
\frac{N_{s,m,\mathrm{PASS}}+N_{s,m,\mathrm{FAIL}}}
{N_{s,m,\mathrm{eligible}}}
\]

\[
\mathrm{PassRate}_{s,m}=
\frac{N_{s,m,\mathrm{PASS}}}
{N_{s,m,\mathrm{PASS}}+N_{s,m,\mathrm{FAIL}}}
\]

Đặc biệt:

- **Fact checking:** chỉ gồm case có evidence đủ để chấm tiêu chí này; tool-only có thể dùng tool evidence, tùy rubric.
- **Retrieval recall@k:** cần ground truth relevant document IDs; không đưa no-context hoặc tool-only khi không áp dụng.
- **Tool correctness:** chỉ gồm case có expected tool behavior.
- **Abstention:** chỉ gồm case mà policy yêu cầu quyết định từ chối/thiếu dữ kiện.

**Không gộp tất cả các tiêu chí vào cùng mẫu số** nếu chúng áp dụng cho những tập case khác nhau.

### Paired coverage theo slice

Với các case mà cả A và B **được chấm hợp lệ** trên tiêu chí m:

\[
P_{s,m}=
\{i\in Eligible(s,m)\mid
V_{A,i}, V_{B,i}\in\{\mathrm{PASS},\mathrm{FAIL}\}\}
\]

\[
\mathrm{PairedCoverage}_{s,m}=
\frac{|P_{s,m}|}{|Eligible(s,m)|}.
\]

Ví dụ trong slice `policy/hard` có **10 case**: A chấm được 10, B chấm được 7, đồng thời hợp lệ trên 7 case. Paired coverage **70%**; không được tuyên bố candidate “90% PASS trên policy/hard” mà không cảnh báo **30% thiếu verdict**.

Lỗi judge **không phải một quality FAIL của generator**, nhưng một run thiếu verdict nghiêm trọng có thể bị **BLOCKED** bởi minimum coverage gate.

### Đếm errors theo hai trục

| Cần biết | Metric riêng |
|---|---|
| Lỗi sinh câu trả lời | `generation_error_rate` |
| Lỗi công cụ | `tool_error_rate` |
| Lỗi của judge | `evaluation_error_rate` |
| Case không chạy | `skipped_rate` |
| Không có evidence | `no_context_rate` và `abstention_pass_rate` |
| Pair có đủ verdict | `paired_coverage` |

Những metric vận hành có thể tính trên **số case được giao** hoặc **số attempts**. Phải công bố mẫu số tương ứng, vì một case có thể retry nhiều lần.

## 13. Paired comparison theo từng slice

Sau khi chốt dataset và scoring policy, với mỗi case có verdict hợp lệ cả A/B, phân vào:

| | B PASS | B FAIL |
|---|---:|---:|
| **A PASS** | Both pass (`a`) | **A-only pass (`b`)** — B hồi quy |
| **A FAIL** | **B-only pass (`c`)** — B cải thiện | Both fail (`d`) |

\[
N_\mathrm{paired}=a+b+c+d
\]

\[
\Delta_\mathrm{paired,s}
=\frac{c_s-b_s}{N_{\mathrm{paired},s}}\times 100
\quad \text{(điểm phần trăm)}.
\]

Ví dụ để minh họa riêng cho **ba nhóm** trong bảng 100 case:

| Business group | Cả hai PASS (`a`) | A-only (`b`) | B-only (`c`) | Cả hai FAIL (`d`) | Tổng |
|---|---:|---:|---:|---:|---:|
| Policy | 49 | 5 | 2 | 4 | 60 |
| Orders | 20 | 1 | 4 | 5 | 30 |
| Tech support | 2 | 1 | 3 | 4 | 10 |
| **Tổng** | **71** | **7** | **9** | **13** | **100** |

Kiểm tra:

- A PASS = `71 + 7 = 78`.
- B PASS = `71 + 9 = 80`.
- Overall delta = `(9 − 7) / 100 = +2` điểm phần trăm.
- Policy delta = `(2 − 5) / 60 = −5` điểm phần trăm.
- Orders delta = `(4 − 1) / 30 = +10` điểm phần trăm.
- Tech support delta = `(3 − 1) / 10 = +20` điểm phần trăm.

Điểm mạnh của bảng bốn ô là cho biết **những ca B sửa được và những ca B phá hỏng**. Từ đó có thể lấy danh sách `case_id` hồi quy trong nhóm policy để đối chiếu evidence, answer và traces.

**Bảng bốn ô là ví dụ phù hợp với các tổng A/B ở mục 9; nó không chỉ ra cặp cụ thể nào đổi ở mỗi mức khó.** Để phân tích kết hợp `business × difficulty`, cần join actual case results rồi đếm b/c của mỗi ô, không đoán phân bổ từ tổng.

## 14. Minimum sample, độ bất định và nhiều phép kiểm

Một lát cắt có `n=2` và tỷ lệ 100% **không chứng minh** mô hình hoàn hảo ở nhóm đó.

### Thiết kế ba mức báo cáo

| Cấp | Mục tiêu | Cách diễn giải |
|---|---|---|
| **Descriptive** | Đưa count, pass rate, delta và error rates | Luôn được, miễn ghi rõ `n` và denominator |
| **Diagnostic** | Tìm case hồi quy, lỗi retrieval/tool cụ thể | Có thể dùng ngay cả trên slice rất nhỏ |
| **Decision-grade** | Dùng để phê duyệt release hoặc kết luận hơn/kém | Cần minimum n, coverage, uncertainty và review |

Chính sách minh họa:

- `n_paired < 20`: **SMALL_N**, chỉ dùng chẩn đoán, không tự tuyên bố cải thiện.
- `20 ≤ n_paired < 50`: mô tả hiệu quả với khoảng bất định; thận trọng khi quyết định.
- `n_paired ≥ 50`: vẫn cần khoảng tin cậy, kiểm tra độ đại diện và correlation.

**Các ngưỡng trên không phải chuẩn thống kê chung.** Cỡ mẫu thực tế phụ thuộc base rate, hiệu ứng tối thiểu cần phát hiện, mức độ độc lập của case, số nhóm và rủi ro của sai quyết định. Cần cân nhắc power analysis và phương pháp thống kê phù hợp.

### Kiểm định paired

Với PASS/FAIL ghép cặp, **McNemar's test** sử dụng cặp không đồng ý (`b` và `c`). Với ít discordant pairs, có thể dùng phiên bản **exact**. Không dùng kiểm định hai tỷ lệ độc lập trên cùng các case vì bỏ mất cấu trúc ghép cặp.

Khi case cùng đến từ một tài liệu/policy, các quan sát có thể **tương quan theo cụm**. Nếu bootstrap delta, hãy resample **nguyên cặp A/B cùng ID** và cân nhắc resample theo **document/topic cluster**.

### Multiple comparisons

Với 3 nhóm × 3 mức khó = 9 ô, cộng thêm nhiều scenario, tags và model versions, số phép so ngày càng lớn. Nếu chỉ chọn ô có p-value thấp nhất sau khi xem dữ liệu, dễ gặp phát hiện tình cờ (*multiple testing problem*).

Các cách giảm rủi ro:

1. **Định trước** một vài primary/critical slices.
2. Đặt minimum n/coverage và hiệu ứng thực tế tối thiểu.
3. Nếu làm nhiều phép kiểm khẳng định, cân nhắc hiệu chỉnh như **Holm** hoặc **Benjamini–Hochberg** phù hợp mục tiêu kiểm soát sai lầm.
4. Xem phân tích exploratory là **khám phá giả thuyết**, không tự gọi bằng chứng xác nhận.
5. Đưa những regression an toàn/tuân thủ quan trọng đến **human review** thay vì chỉ dựa vào p-value.

## 15. Một dạng difficulty drift khác: cùng câu hỏi nhưng dữ liệu thay đổi

Độ khó có thể thay đổi **thực chất** khi corpus hoặc công cụ thay đổi:

- Run A: hỏi thời hạn nộp dựa trên một tài liệu.
- Run B: corpus có thêm ngoại lệ, văn bản sửa đổi và quy định hiệu lực chồng chéo.

Khi đó, dù `case_id` và question không đổi, **điều kiện câu hỏi đã thay**. Không được giữ difficulty label cũ mà không kiểm tra. Cách đúng:

1. **Version hóa corpus/index/tool fixtures**.
2. Chốt ground truth theo phiên bản dữ liệu.
3. Review lại difficulty rubric trước khi tạo **dataset revision mới**.
4. Báo các run cũ/mới **không hoàn toàn tương đương** nếu ground truth hoặc mức suy luận cần thiết đã thay đổi.

Ngoài ra, **độ khó của case** (theo rubric độc lập) và **khó với một model cụ thể** (failure pattern của model) là hai đại lượng khác nhau. Có thể thêm chỉ số `model_failure_frequency` làm kết quả phân tích, nhưng **không ghi đè** difficulty label phục vụ phân tầng thí nghiệm.

## 16. Code Java 21: tổng hợp paired result theo business × difficulty

Ví dụ bên dưới là một lớp **thuần Java**. Nó nhận verdict đã được runner phân loại cho một tiêu chí cụ thể (ví dụ factuality của các case RAG eligible), đối chiếu dữ liệu A/B theo `caseId` và đếm kết quả theo `business × difficulty`.

### File `SliceComparison.java`

~~~java
package com.example.aiquality.comparison;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;

public final class SliceComparison {
    private SliceComparison() {}

    public enum Business { POLICY, ORDERS, TECH_SUPPORT }
    public enum Difficulty { EASY, MEDIUM, HARD }
    public enum Verdict {
        PASS, FAIL, GENERATION_ERROR, EVALUATION_ERROR,
        SKIPPED, NOT_APPLICABLE
    }

    public record CaseResult(
            String caseId,
            Business business,
            Difficulty difficulty,
            Verdict verdict) {}

    public record SliceKey(Business business, Difficulty difficulty) {}

    public record SliceSummary(
            SliceKey key,
            int total,
            int aEvaluated,
            int bEvaluated,
            int paired,
            int bothPass,
            int aOnly,
            int bOnly,
            int bothFail) {

        public OptionalDouble pairedCoverage() {
            if (total == 0) return OptionalDouble.empty();
            return OptionalDouble.of(paired / (double) total);
        }

        public OptionalDouble pairedDeltaPp() {
            if (paired == 0) return OptionalDouble.empty();
            return OptionalDouble.of(100.0 * (bOnly - aOnly) / paired);
        }
    }

    private static final class Counter {
        int total, aEvaluated, bEvaluated, paired;
        int bothPass, aOnly, bOnly, bothFail;
    }

    public static Map<SliceKey, SliceSummary> compare(
            List<CaseResult> baseline,
            List<CaseResult> candidate) {

        Map<String, CaseResult> a = indexUnique(baseline);
        Map<String, CaseResult> b = indexUnique(candidate);

        if (a.isEmpty() || !a.keySet().equals(b.keySet())) {
            throw new IllegalArgumentException(
                "Hai arm phải có cùng tập case ID và không được rỗng");
        }

        Map<SliceKey, Counter> counts = new LinkedHashMap<>();

        for (Map.Entry<String, CaseResult> item : a.entrySet()) {
            CaseResult av = item.getValue();
            CaseResult bv = b.get(item.getKey());

            if (av.business() != bv.business()
                    || av.difficulty() != bv.difficulty()) {
                throw new IllegalArgumentException(
                    "Metadata slice khác nhau: " + item.getKey());
            }

            SliceKey key = new SliceKey(av.business(), av.difficulty());
            Counter counter = counts.computeIfAbsent(
                    key, ignored -> new Counter());
            counter.total++;

            boolean ae = isEvaluated(av.verdict());
            boolean be = isEvaluated(bv.verdict());
            if (ae) counter.aEvaluated++;
            if (be) counter.bEvaluated++;

            if (!ae || !be) continue;
            counter.paired++;

            if (av.verdict() == Verdict.PASS
                    && bv.verdict() == Verdict.PASS) {
                counter.bothPass++;
            } else if (av.verdict() == Verdict.PASS) {
                counter.aOnly++;
            } else if (bv.verdict() == Verdict.PASS) {
                counter.bOnly++;
            } else {
                counter.bothFail++;
            }
        }

        Map<SliceKey, SliceSummary> result = new LinkedHashMap<>();
        counts.forEach((key, c) ->
            result.put(key, new SliceSummary(
                key, c.total, c.aEvaluated, c.bEvaluated,
                c.paired, c.bothPass, c.aOnly, c.bOnly, c.bothFail)));

        return Collections.unmodifiableMap(result);
    }

    private static boolean isEvaluated(Verdict verdict) {
        return verdict == Verdict.PASS || verdict == Verdict.FAIL;
    }

    private static Map<String, CaseResult> indexUnique(
            List<CaseResult> rows) {
        if (rows == null) {
            throw new IllegalArgumentException("Danh sách verdict bị null");
        }

        Map<String, CaseResult> index = new LinkedHashMap<>();
        for (CaseResult row : rows) {
            if (row == null || row.caseId() == null
                    || row.caseId().isBlank()
                    || row.business() == null
                    || row.difficulty() == null
                    || row.verdict() == null) {
                throw new IllegalArgumentException(
                    "Thiếu ID/metadata/verdict");
            }
            if (index.putIfAbsent(row.caseId(), row) != null) {
                throw new IllegalArgumentException(
                    "Case ID trùng: " + row.caseId());
            }
        }
        return index;
    }
}
~~~

### Những ranh giới quan trọng của helper

- `SliceComparison` chưa biết **Spring AI**, không cần model key hay kết nối mạng. Nó chỉ tổng hợp **một metric đã có verdict PASS/FAIL hợp lệ**.
- Trước khi gọi, runner phải **lọc cùng tập case eligible của metric** ở cả hai arm và xác minh `dataset_revision`, `label_revision`, rubric/judge versions.
- Hàm từ chối **case ID trùng/thiếu** và metadata `business`/`difficulty` khác nhau giữa A/B.
- `aEvaluated`, `bEvaluated` và `paired` tách riêng. Verdict lỗi **không tự chuyển thành FAIL**.
- `OptionalDouble.empty()` thể hiện slice không thể tính được vì thiếu mẫu; khi xuất JSON, dùng `null` và một reason code, không xuất `NaN`.
- Kết quả không tự suy ra **nguyên nhân** một case fail. Muốn điều tra cần liên kết report với RAG snapshots, tool logs và traces.

## 17. Kiểm thử JUnit 5: hồi quy ở nhóm nhỏ có thể bị điểm tổng che

### File `SliceComparisonTest.java`

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;
import com.example.aiquality.comparison.SliceComparison;
import com.example.aiquality.comparison.SliceComparison.*;

class SliceComparisonTest {

    private static CaseResult row(
            String id, Business group, Difficulty level, Verdict value) {
        return new CaseResult(id, group, level, value);
    }

    @Test
    void detectsBusinessRegressionAndMissingJudgeVerdict() {
        List<CaseResult> a = List.of(
            row("p1", Business.POLICY, Difficulty.HARD, Verdict.PASS),
            row("p2", Business.POLICY, Difficulty.HARD, Verdict.PASS),
            row("o1", Business.ORDERS, Difficulty.EASY, Verdict.FAIL),
            row("o2", Business.ORDERS, Difficulty.EASY,
                Verdict.EVALUATION_ERROR));

        // B cố ý trả kết quả không theo thứ tự của A.
        List<CaseResult> b = List.of(
            row("o2", Business.ORDERS, Difficulty.EASY, Verdict.PASS),
            row("p2", Business.POLICY, Difficulty.HARD, Verdict.FAIL),
            row("o1", Business.ORDERS, Difficulty.EASY, Verdict.PASS),
            row("p1", Business.POLICY, Difficulty.HARD, Verdict.PASS));

        var result = SliceComparison.compare(a, b);
        var policy = result.get(new SliceKey(
                Business.POLICY, Difficulty.HARD));
        var orders = result.get(new SliceKey(
                Business.ORDERS, Difficulty.EASY));

        assertEquals(2, policy.paired());
        assertEquals(1, policy.aOnly());
        assertEquals(0, policy.bOnly());
        assertEquals(-50.0, policy.pairedDeltaPp().orElseThrow());

        assertEquals(2, orders.total());
        assertEquals(1, orders.aEvaluated());
        assertEquals(2, orders.bEvaluated());
        assertEquals(1, orders.paired());
        assertEquals(1, orders.bOnly());
        assertEquals(0.5, orders.pairedCoverage().orElseThrow());
    }

    @Test
    void rejectsChangedDifficultyOnSameCaseId() {
        assertThrows(IllegalArgumentException.class, () ->
            SliceComparison.compare(
                List.of(row("p1", Business.POLICY,
                    Difficulty.HARD, Verdict.PASS)),
                List.of(row("p1", Business.POLICY,
                    Difficulty.EASY, Verdict.PASS))));
    }

    @Test
    void rejectsMissingCaseIds() {
        assertThrows(IllegalArgumentException.class, () ->
            SliceComparison.compare(
                List.of(
                    row("p1", Business.POLICY, Difficulty.EASY,
                        Verdict.PASS),
                    row("p2", Business.POLICY, Difficulty.EASY,
                        Verdict.PASS)),
                List.of(row("p1", Business.POLICY,
                    Difficulty.EASY, Verdict.PASS))));
    }
}
~~~

Đây là **mã ví dụ để người học chép vào project Java có JUnit 5**, không phải code đã được compile/test trong nhiệm vụ viết tài liệu. Trong ứng dụng thực, tách kết quả `GENERATION_ERROR`/`EVALUATION_ERROR` để tổng hợp error rate theo từng nhóm và giữ mọi attempt theo retry policy.

## 18. Ghép với Spring AI Evaluators và evidence snapshot

Workflow đánh giá cho từng case:

~~~text
Case metadata (business, difficulty, scenario, risk)
  -> Answer workflow A/B (retriever, generator, tools)
  -> ExecutionSnapshot {answer, context, tool calls, error}
  -> Deterministic checks {retrieval, tool contract}
  -> RelevancyEvaluator / FactCheckingEvaluator (nếu eligible)
  -> Verdict {PASS, FAIL, EVALUATION_ERROR, ...}
  -> SliceComparison theo caseId
  -> Report/quality gate
~~~

Các quy tắc:

1. **Không leak nhãn:** `expectedDocumentIds` và `expectedClaims` chỉ dành cho scorer, không tự đưa vào prompt của generator.
2. **Evidence đúng lần chạy:** judge nhận context sau lọc/rerank/truncation đã cấp cho generator.
3. **Tách judge lỗi:** khi `FactCheckingEvaluator` timeout/429, ghi `EVALUATION_ERROR`; không biến thành câu trả lời sai.
4. **Tool-only:** dùng tool output làm evidence khi rubric hỗ trợ hoặc chấm deterministic correctness; không gán factuality fail chỉ vì `retrievedDocuments` rỗng.
5. **No-context:** chấm abstention theo policy, không buộc mọi case phải có fact-check verdict.
6. **Độ khó label không được sửa sau khi thấy verdict.**

Thước đo relevance thường khác groundedness. Một answer “hạn nộp là ngày 15” có thể **liên quan** câu hỏi về hạn nộp nhưng **sai** so với evidence “ngày 05”; vì vậy slice báo **relevance và fact checking riêng**.

## 19. Chẩn đoán theo slice: retrieval và tool gọi có đúng không?

Chỉ báo chất lượng chung không giải thích vì sao một nhóm hard thất bại. Với từng slice, cần đi sâu đến các giai đoạn:

| Tầng | Tiêu chí có thể đo | Dữ liệu để xác minh |
|---|---|---|
| Retrieval | `Hit@k`, `Recall@k`, ranking relevance | Relevant IDs, retrieved IDs, filters, top-k |
| Context assembly | Có đủ bằng chứng sau rerank/truncation? | Context snapshot, token budget, chunk order |
| Generation | Relevance, groundedness, claim completeness | Answer và evidence đúng attempt |
| Tool calling | Đúng tool/typed arguments/sequence? | Expected/actual tool calls, schema version |
| Tool result use | Diễn giải đúng trạng thái tool? | Tool output fixture, answer |
| Abstention | Biết nói thiếu nguồn khi nên từ chối? | `expectAbstention`, rubric riêng |
| Stability | Số lỗi/retries, judge drift | Status, attempts, evaluator version |

### Ví dụ: retrieval recall@3

Một case hard có relevant IDs `["doc-A","doc-B"]`.

- Retriever A trả `["doc-A","doc-C","doc-D"]` → `Recall@3 = 1/2 = 0,5`.
- Retriever B trả `["doc-A","doc-B","doc-D"]` → `Recall@3 = 2/2 = 1`.

Điều này chứng minh B truy xuất được nhiều nguồn relevant hơn trong ví dụ, **không chứng minh answer B chắc chắn đúng**: model có thể vẫn sử dụng sai quy định hoặc bỏ qua ngoại lệ.

Trong nhóm `policy/hard`, nếu **retrieval recall giữ nguyên nhưng fact checking giảm**, hãy xem generator prompt, model và cách tổng hợp evidence. Nếu recall giảm cùng fact checking, ưu tiên xem index, filters, reranking và chunking.

### Lưu ý khi so top-k khác nhau

Nếu A dùng `k=5` và B dùng `k=10`:

1. Để so **ranking quality**, tính recall tại **cùng k** nếu dữ liệu cho phép.
2. Để so **system quality**, chấm factuality trên context *thực sự* cấp generator của mỗi arm; ghi k và token budget khác nhau.
3. Luôn đo latency/token/cost, vì thêm context có thể tăng chi phí dù relevance không tăng.
4. Không áp dụng retrieval recall cho case không có ground truth document IDs; trả `NOT_APPLICABLE`.

### Tool dependency làm tăng độ khó thế nào?

Giả sử yêu cầu hỗ trợ kỹ thuật cần:

~~~text
getServiceHealth(SVC-DEMO)
  -> nếu lỗi: getDeploymentVersion(SVC-DEMO)
  -> đối chiếu runbook còn hiệu lực
  -> đưa khuyến nghị chỉ đọc (không tự thao tác production)
~~~

Phân biệt:

- **Sai hành vi:** tool đã chạy được nhưng assistant gọi sai service ID hoặc bỏ qua bước kiểm tra phiên bản.
- **Lỗi kỹ thuật:** tool trả timeout/503; không có dữ liệu đủ để kết luận.
- **Sai nội dung:** tool trả trạng thái `DEGRADED` nhưng answer nói `HEALTHY`.
- **Đúng abstention:** tool không truy cập được nên assistant nói rõ không đủ dữ liệu theo policy.

Các tình huống **multi-step tool** thường thuộc nhóm khó, nhưng phải dựa trên **rubric trước khi chạy**, không chỉ vì chúng có nhiều tokens.

## 20. Kết hợp metrics, traces, độ trễ và chi phí theo slice

Spring AI dùng Micrometer Observation/Tracing để quan sát các thành phần khi **chúng thực sự được thực thi**:

| Observation/metric logic | Liên hệ phân tích theo nhóm |
|---|---|
| `spring.ai.chat.client` | Tổng thời gian ChatClient/advisor chain |
| `spring.ai.advisor` | Tầng preprocessing/retrieval advisor |
| `gen_ai.client.operation` | Latency gọi ChatModel/EmbeddingModel |
| `gen_ai.client.token.usage` | Input/output token usage khi provider cung cấp |
| `db.vector.client.operation` | VectorStore operations |
| `spring.ai.tool` | Tool execution |
| `app.ai.evaluation.slice` (tự tạo) | Duration của evaluation case gắn business/difficulty |
| `app.ai.evaluation.outcome` (tự tạo) | PASS/FAIL/ERROR theo slice đã giới hạn cardinality |

Các tên trên là **tên logic**; xuất Prometheus có thể thay dấu chấm thành gạch dưới và thêm suffix `_seconds_count`, `_total`. Spring AI **không tự thêm business group hoặc difficulty tags** cho bạn; cần ghi từ tầng evaluation runner.

### Tạo observation tự định nghĩa

Ví dụ một wrapper có các nhãn **giá trị đóng**:

~~~java
package com.example.aiquality.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

@Component
public class SliceObservation {
    private final ObservationRegistry registry;

    public SliceObservation(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T observe(
            String business,
            String difficulty,
            Supplier<T> operation) {

        // business, difficulty phải là enum/allowlist được validate.
        return Observation.createNotStarted(
                "app.ai.evaluation.slice", registry)
            .lowCardinalityKeyValue("business_group", business)
            .lowCardinalityKeyValue("difficulty", difficulty)
            .observe(operation::get);
    }
}
~~~

Wrapper này đo **thời gian trong Supplier**, không tự suy PASS/FAIL. Runner cần ghi outcome bằng một counter riêng hoặc trong assessment store **sau khi verdict đã được xác nhận**. Nên chuyển hai tham số `String` thành enums hoặc validation bắt buộc; nếu gọi wrapper với các chuỗi không giới hạn sẽ gây **metric-cardinality explosion**.

### Nên gắn label nào?

| Attribute | Metric label? | Ghi chú |
|---|---|---|
| `business_group` | Có, khi taxonomy giới hạn | Ba nhóm trong ví dụ |
| `difficulty` | Có | Easy/medium/hard |
| `scenario` | Có | RAG/tool/no_context |
| `role` | Có | Generator/judge/retriever |
| `outcome` | Có, enum giới hạn | Pass/fail/technical error |
| `arm` | Có, khi phép so A/B rõ ràng | A/B, không dùng giá trị tùy ý |
| `run_id`, `case_id` | **Không** | Cardinality cao; để trong report có quyền |
| Raw question/prompt/context/user ID | **Không** | Có thể nhạy cảm |
| Provider secret, bearer token | **Không bao giờ** | Secret |

**Cẩn thận với tích nhãn:** 3 business × 3 difficulty × 4 scenario × 4 role × 5 outcome × 2 arm có thể tạo **1.440 series cho một metric** trước khi tính model, environment và histogram buckets. Chỉ dùng tổ hợp thực sự cần, tránh histogram cho mọi slice nhỏ, giám sát cardinality và chi phí lưu trữ.

### Latency per slice

Đo riêng:

- **User-facing:** thời gian từ API nhận request đến answer/lỗi; không cộng judge chạy offline.
- **Generator:** thời gian gọi model trả lời người dùng.
- **Retrieval/tool:** vector DB, embedding và tool spans.
- **Evaluation:** thời gian judge/rubric/ghi report (nếu chạy offline).

Với cùng case:

\[
\Delta t_i=t_{B,i}-t_{A,i}.
\]

Mean/median của **paired deltas** giúp biết candidate chậm hơn trên những loại câu nào. Phân vị `p95(B) - p95(A)` **không bằng** `p95(t_B - t_A)` nói chung; nếu có ít case trong một slice thì percentile rất bất ổn.

### Token và chi phí theo từng nhóm

\[
C_{\mathrm{call}} =
\frac{T_{\mathrm{input}}}{10^6}P_{\mathrm{input}}
+\frac{T_{\mathrm{output}}}{10^6}P_{\mathrm{output}}.
\]

\[
C_{\mathrm{case}} =
C_{\mathrm{generator}} + C_{\mathrm{judge}}
+ C_{\mathrm{embedding/retrieval/tool}}.
\]

`P` là giá theo **một triệu token**, cần model, bảng giá, thời điểm và loại token. Các provider có thể tính riêng cached input, reasoning tokens, retries hoặc batch calls. Với token usage không được trả, ghi `USAGE_MISSING`, không tự thay bằng 0.

Khi tính **mean cost/case của slice**, cần công bố mẫu số và xử lý missing usage nhất quán. Hai cách báo có ích:

1. **Actual spend**: dùng giá thật ở từng lần chạy để xét ngân sách.
2. **Normalized cost**: tính lại trên cùng rate card (nếu có đủ usage) để so hiệu quả kỹ thuật A/B.

**Không cộng token type `input`, `output` và `total` vào cùng một tổng**: có thể đếm hai lần cùng tokens.

## 21. Quality gate nhiều tầng và ưu tiên nhóm trọng yếu

Một quality gate nên có **overall guardrails** và **business/difficulty guardrails**:

~~~yaml
quality_gate_revision: "slice-gate-v1"
primary_metric: "fact_check_pass_rate"
overall:
  min_paired_coverage: 0.98
  min_paired_fact_check_delta_pp: 0.0
  max_generation_error_rate: 0.02
  max_evaluation_error_rate: 0.01
  max_generator_p95_latency_ratio: 1.20
  max_normalized_cost_per_case_ratio: 1.15
critical_slices:
  - business_group: policy
    risk_tier: high
    max_allowed_fact_check_regression_pp: 1.0
    min_paired_coverage: 0.98
    min_paired_cases_for_automatic_decision: 30
    on_small_n: "HUMAN_REVIEW_REQUIRED"
  - business_group: orders
    difficulty: hard
    tool_assertion_must_not_regress: true
    min_paired_coverage: 0.95
decision_values: [PROMOTE, REJECT, BLOCKED, INCONCLUSIVE]
~~~

**Đây là policy minh họa, không phải cấu hình built-in của Spring AI.** Các ngưỡng phải được thảo luận với chuyên gia nghiệp vụ, theo risk appetite, baseline và năng lực phép đo. `on_small_n` nên kích hoạt thu thập thêm case/review chứ không hợp thức hóa một kết luận chắc chắn.

### Áp dụng vào ví dụ 100 case

- Overall: B tăng `+2 pp`.
- `policy`: B giảm `−5 pp`, vượt giới hạn ví dụ **1 pp**.
- `tech_support`: B tăng `+20 pp` nhưng chỉ có 10 case, cần xem uncertainty.

**Quyết định minh họa: `BLOCKED/REVIEW`, chưa tự promote B**, vì có regression ở nhóm policy rủi ro cao. Cần kiểm tra các case A-only, evidence, retrieval và nhãn người chấm trước khi sửa prompt hoặc điều chỉnh gate. Không thay ngưỡng từ 1 pp thành 6 pp **sau khi thấy** điểm để nhận kết quả mong muốn.

### Tách ba loại điều kiện gate

| Loại | Ví dụ | Ý nghĩa |
|---|---|---|
| **Measurement gate** | Dataset hash khớp, coverage ≥ 98%, judge ổn | Có đủ dữ liệu để kết luận? |
| **Quality gate** | Policy factuality không suy giảm quá 1 pp | Có đạt yêu cầu nghiệp vụ không? |
| **Operational gate** | Lỗi, p95, cost trong ngân sách | Có vận hành được không? |

Nếu measurement gate thất bại, kết quả thường là `INCONCLUSIVE/BLOCKED`, **không nên tự tuyên bố B thua hoặc thắng về chất lượng**.

## 22. Quy trình điều tra một slice bị hồi quy

Giả sử `policy/hard` có B PASS 6/10, A PASS 7/10. Chênh lệch chỉ **một case** nên không đủ để nói hồi quy chắc chắn về mặt thống kê, nhưng vì nhóm rủi ro cao, cần điều tra:

1. **Ghép các case ID** và xác định A-only/B-only trong riêng slice.
2. **Kiểm tra nhãn:** case có đúng corpus hiệu lực, expected claims và độ khó đã review?
3. **Đối chiếu retrieval:** relevant doc IDs có được tìm, rerank/truncation có làm mất evidence?
4. **Đối chiếu generator:** prompt/model/options nào đổi, answer đã bịa thêm claim nào?
5. **Đối chiếu judge:** rubric/model, parse response, false pass/false fail đã hiệu chuẩn?
6. **Đối chiếu traces:** latency tăng ở vector DB, ChatModel hay tool?
7. **Đối chiếu token/cost:** context dài hơn, output dài hơn hay retry tăng?
8. **Đề xuất thay đổi:** sửa một nguyên nhân có bằng chứng, chạy lại trên dataset giữ nguyên.

### Bảng chẩn đoán nhanh

| Biểu hiện trong slice | Ưu tiên kiểm tra |
|---|---|
| Retrieval recall giảm, factuality giảm | Corpus/index/filter/reranker/chunking |
| Recall giữ nguyên, factuality giảm | Generator prompt/model/context assembly |
| Relevance cao nhưng fact checking thấp | Claim bịa, số liệu sai, context thiếu |
| Tool args sai nhưng answer nghe đúng | Tool contract/selection, deterministic assertions |
| B lỗi ở nhiều case hard | Provider timeout, context budget, rate limits |
| Judge errors tập trung ở policy | Rubric, token limit, output parser, prompt injection |
| Quality giữ nguyên nhưng p95 tăng | Vector DB/provider/tool/queue |
| Token tăng, chất lượng không đổi | Top-k, long-context duplication, prompt verbosity |
| Điểm tổng tăng nhưng policy giảm | Guardrail nhóm trọng yếu, case A-only của policy |

**Không đổ lỗi mặc định cho generator.** Chất lượng có thể suy giảm do retrieval, tool contract, label drift, judge drift hoặc việc tổng hợp báo cáo sai mẫu số.

## 23. Báo cáo nhiều lớp: bảng nào dành cho ai?

Một report hữu ích gồm ít nhất bốn lớp:

| Lớp | Độc giả | Nội dung |
|---|---|---|
| **Executive overview** | Product owner/release manager | Chỉ số chính, rủi ro nhóm critical, quyết định và giới hạn |
| **Business slices** | Chuyên gia nghiệp vụ | Policy/orders/tech-support, count, pass/coverage, A-only/B-only |
| **Difficulty/intersections** | AI/ML engineers | Easy/medium/hard, 3×3 table, small-n warnings |
| **Case-level diagnostics** | Người sửa lỗi | Case ID, evidence/version, traces, tool calls, errors, token/cost |

### Run manifest rút gọn

~~~yaml
run_id: "slice-eval-A"
arm: A
environment: staging
git_commit: "replace-with-git-sha"
java_version: "21"
spring_boot_version: "4.2.x"
spring_ai_bom_version: "2.1.x"
generator_model: "provider-model-id"
prompt_revision: "answer-v3"
judge_model: "judge-model-id"
rubric_revision: "factuality-rubric-v2"
dataset_revision: "ai-business-slices-v1"
dataset_digest: "sha256:replace-with-actual-digest"
business_taxonomy_revision: "biz-groups-v1"
difficulty_rubric_revision: "difficulty-0-to-10-v1"
label_revision: "domain-reviewed-v2"
corpus_revision: "corpus-fixture-v7"
index_revision: "index-build-v12"
tool_fixture_revision: "sandbox-orders-v3"
scoring_policy_revision: "quality-policy-v3"
cost_rate_card_revision: "price-rates-revision"
telemetry_schema_revision: "observability-v2"
~~~

### Case result rút gọn

~~~jsonl
{"runId":"slice-eval-A","caseId":"pol-002","businessGroup":"policy","difficulty":"hard","scenario":"rag","riskTier":"high","metric":"fact_check","eligible":true,"executionStatus":"COMPLETED","assessmentStatus":"FAIL","evidenceRef":"restricted://evidence/pol-002","traceRef":"restricted://traces/pol-002","latencyMs":870,"inputTokens":420,"outputTokens":81,"usageStatus":"REPORTED"}
{"runId":"slice-eval-A","caseId":"ord-003","businessGroup":"orders","difficulty":"medium","scenario":"tool","metric":"tool_correctness","eligible":true,"executionStatus":"COMPLETED","assessmentStatus":"PASS","toolAssertionPass":true,"traceRef":"restricted://traces/ord-003","usageStatus":"MISSING"}
~~~

Các đường dẫn `restricted://...` và các số chỉ là **ví dụ**. Nội dung evidence thật, tool outputs, credentials và thông tin cá nhân phải được lưu theo chính sách bảo mật; report chia sẻ rộng nên dùng references thay raw documents.

### Quy tắc khi tổng hợp report

1. **Một dòng per case/metric/arm** hoặc một schema tương đương rõ ràng; không ghi đè nhiều attempts.
2. Với mỗi metric báo: `eligible`, `PASS`, `FAIL`, `errors`, `skipped`, `coverage`.
3. Với mỗi slice báo: `N`, paired N, delta (pp), interval/uncertainty và `SMALL_N` khi áp dụng.
4. Phân biệt `micro overall`, `macro business`, `weighted` và **weights revision**.
5. Đính kèm top case regressions A-only để review; không chỉ chọn các case candidate thắng.
6. Lưu baseline report bất biến và phiên bản của scoring code.

## 24. CI và lịch chạy phù hợp từng tầng

| Tầng | Thời điểm | Dữ liệu và mục tiêu |
|---|---|---|
| Unit | Mọi commit | Validator taxonomy/difficulty, Java comparator, xử lý missing |
| Component offline | Mọi pull request | Fake generator/retriever/tool với dataset tổng hợp |
| Live smoke | Manual/CI được cấp quyền | Vài case để kiểm provider, judge, metrics và traces |
| Nightly regression | Theo lịch | Dataset có version, A/B hoặc baseline/current, slice report |
| Release gate | Trước triển khai | Business critical slices, paired analysis, cost/p95, human review |
| Post-deploy monitoring | Theo policy dữ liệu | Drift của traffic mix, vận hành, quality sample đã được phép |

### Preflight trước mọi so sánh

~~~text
assert dataset_A.sha256 == dataset_B.sha256
assert case_ids_A == case_ids_B
assert business_taxonomy_revision_A == business_taxonomy_revision_B
assert difficulty_rubric_revision_A == difficulty_rubric_revision_B
assert label_revision_A == label_revision_B
assert judge_model_A == judge_model_B
assert scoring_policy_A == scoring_policy_B
assert intended_manifest_diff == actual_manifest_diff
assert no_duplicate_or_missing_case_ids()
assert sandbox_permissions_and_quota_are_valid()

run_or_load_results()
select_attempt_by_published_policy()
filter_metric_eligible_cases()
pair_by_case_id()
aggregate_business_and_difficulty_slices()
compute_coverage_errors_confidence_and_guardrails()
publish_versioned_report_for_review()
~~~

**Khi so retriever**, context hashes A/B có thể khác theo thiết kế; đừng biến `context_A == context_B` thành điều kiện bắt buộc. Khi so prompt/model trong **frozen-context mode**, thì phải kiểm context tương đương cho hai arm.

## 25. Lỗi thường gặp và cách khắc phục

| Lỗi | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Gán difficulty sau khi thấy B fail | Bias từ outcome đang đo | Gán trước khi chạy, khóa rubric |
| Case ở hai arm bị đổi business group | Không còn so cùng slice | Validator fail, review labels |
| Chỉ dùng micro pass rate | Che regression nhóm nhỏ/critical | Báo macro, per-slice, worst-case guardrails |
| Lấy macro của tags chồng lấn rồi gọi overall | Đếm trùng case | Primary group rõ ràng; tags là phân tích phụ |
| Chỉ có 2 case ở một slice nhưng kết luận hơn hẳn | Bất định cao | Gắn `SMALL_N`, thu thêm mẫu |
| Judge lỗi nhưng bị tính FAIL | Gây regression giả | Tách `EVALUATION_ERROR` và coverage |
| Thay corpus/index nhưng giữ difficulty cũ | Ground truth/rubric không phù hợp | Review dữ liệu và tạo revision mới |
| So group pass rate từ hai tập không cùng mix | Simpson's paradox | Pair IDs hoặc chuẩn hóa weights |
| Chỉ so final answer ở tool case | Bỏ sót gọi sai tool/args | Deterministic assertions |
| Chấm factuality trên evidence retriever chạy lại | Judge không thấy context generator đã dùng | Lưu snapshot thực tế |
| Tính p95 từ max hoặc trung bình | Sai nghĩa thống kê | Raw durations/histogram và đủ mẫu |
| Gắn case ID vào metric label | Bùng nổ time series, rò dữ liệu | Giới hạn labels; IDs để trong report |
| Cộng input/output/total tokens | Đếm đôi | Chọn input+output hoặc total, kiểm usage |
| Đổi weights sau khi thấy B thắng | Báo cáo có thiên lệch | Đăng ký weights/policy trước |

## 26. Bài thực hành và tiêu chí hoàn thành

### Bài A — Kiểm toán rubric độ khó

1. Tạo dataset 12 case gồm `policy`, `orders` và `tech_support`.
2. Mỗi case có `difficultySignals` theo năm trục của mục 3.
3. Viết validator tính điểm 0–10 và đối chiếu nhãn easy/medium/hard.
4. Chủ động gán sai difficulty cho một case; xác nhận validator **phát hiện**.
5. Cho hai reviewer gán nhãn một tập con, lưu các bất đồng và quy trình hòa giải.

**Đạt:** nhãn không phụ thuộc outcome model; case bị mâu thuẫn rubric không âm thầm đi qua preflight.

### Bài B — Tính micro/macro/weighted trên bộ 100 case giả lập

Sử dụng bảng 3×3 ở mục 9:

- Micro: `A=78%`, `B=80%`.
- Macro business: `A≈63,3%`, `B≈71,7%`.
- Với weights `0,5 / 0,3 / 0,2`: `A=72%`, `B=76,5%`.
- Kiểm tra slice `policy`: `A=90%`, `B=85%`.

**Đạt:** nêu đúng vì sao mỗi chỉ số khác nhau, quyết định có cần **review/block** nhóm policy không, không đánh đồng trọng số với traffic thật.

### Bài C — Kiểm tra Java `SliceComparison`

1. Chép `SliceComparison.java` và `SliceComparisonTest.java` vào một project Java 21 có JUnit 5.
2. Chạy test cho **join theo ID**, phân loại `EVALUATION_ERROR` và phát hiện difficulty đổi giữa A/B.
3. Thêm test case bị trùng ID.
4. Thêm slice chỉ toàn `EVALUATION_ERROR` và kiểm tra `OptionalDouble.empty()`.
5. Mở rộng record để lưu `datasetRevision` và kiểm tra revision không đổi.

**Đạt:** kết quả không phụ thuộc thứ tự mảng, không điền FAIL cho error và không trả phần trăm giả cho slice thiếu mẫu.

### Bài D — So prompt A/B trên RAG

1. Khóa 20–50 case `policy` và `tech_support` với ground truth.
2. Dùng frozen context và cùng generator/judge/rubric; chỉ thay prompt.
3. Chấm relevance, fact checking, lưu A-only/B-only theo `business × difficulty`.
4. Tính paired coverage và đánh dấu `SMALL_N`.
5. Đối chiếu các case policy regression với context snapshots, model traces và human labels.

### Bài E — Tool calling và độ khó nhiều bước

Tạo 10 case sandbox, có `getOrderStatus`, `getServiceHealth`, timeout và wrong arguments. Gắn độ khó theo **tool dependencies**. Đo tỷ lệ đúng tool/args, lỗi kỹ thuật, answer grounding và user-facing latency; **không chạy tool có side effect ngoài sandbox**.

### Bài F — Độ trễ và chi phí

Chạy ít case có quyền gọi provider hoặc mock usage hợp lệ. Tách:

- token/chi phí **generator**;
- token/chi phí **judge**;
- latency API **người dùng**;
- latency **evaluation batch**.

Báo `USAGE_MISSING` khi provider không trả dữ liệu, không tự ước giá bằng một model khác. Nếu dùng histogram/p95, cần đủ mẫu trong slice.

### Câu hỏi tự kiểm tra

1. Vì sao không gán hard chỉ vì candidate B trả sai?
2. `Business group` khác `scenario` và `risk tier` như thế nào?
3. Vì sao `micro=80%` có thể cùng tồn tại với policy giảm 5 điểm phần trăm?
4. Macro business khác micro ở cách trọng số như thế nào?
5. Tại sao một case có hai tags không được tính hai lần ở overall?
6. `Simpson's paradox` có thể xuất hiện khi nào?
7. Case no-context có mặc định là hard không?
8. Vì sao metric fact checking và tool correctness không nên có chung mẫu số?
9. A có 10 verdict, B chỉ có 7 verdict trong slice 10 case; paired coverage tối đa là bao nhiêu?
10. Tại sao 100% PASS trên 2 case không đủ để promote model?
11. Nếu judge đổi giữa hai arm, làm thế nào để đánh giá công bằng?
12. Vì sao `case_id` không phù hợp làm Prometheus label?

**Gợi ý:** (1) outcome labeling gây bias; (2) mục đích, loại pipeline và hậu quả khi sai là ba trục khác; (3) overall có các nhóm khác cải thiện; (4) micro theo số case, macro mỗi group ngang nhau; (5) tránh double-counting; (6) cơ cấu mẫu/weights thay đổi; (7) không; (8) eligibility khác nhau; (9) 70%; (10) mẫu quá ít; (11) tái chấm hai arm cùng judge/rubric; (12) cardinality cao và rủi ro riêng tư.

## 27. Checklist trước khi đưa kết quả phân tầng vào quyết định

- [ ] Nhóm nghiệp vụ và độ khó được định nghĩa **trước khi chạy**, có taxonomy/rubric revision.
- [ ] Dataset có case IDs duy nhất, labels/ground truth và checksum không đổi giữa A/B.
- [ ] Có primary business group không chồng lấn; tags phụ được báo rõ là multi-label.
- [ ] Difficulty dựa trên evidence/reasoning/tool/ambiguity, không dựa vào việc model fail.
- [ ] Có reviewer/validation cho case label mâu thuẫn; không âm thầm sửa nhãn sau khi thấy kết quả.
- [ ] Có bảng phân bố business × difficulty, số lượng và cảnh báo `SMALL_N`.
- [ ] Có báo **micro, macro, weighted** (khi phù hợp) và nguồn weights.
- [ ] Đánh giá cùng câu hỏi, cùng eligibility và cùng judge/rubric cho hai arm.
- [ ] RAG sử dụng đúng evidence snapshot từng arm; không chạy lại retrieval ngầm.
- [ ] Tool selection/args/schema được chấm bằng deterministic assertions khi có thể.
- [ ] Fact checking, relevance, retrieval, tool correctness, abstention có **mẫu số riêng**.
- [ ] Lỗi generation/judge/tool và skipped **không bị nhập chung với FAIL**.
- [ ] Báo coverage của A/B và **paired coverage theo slice**.
- [ ] Có bảng both pass/A-only/B-only/both fail cho các nhóm quan trọng.
- [ ] Có minimum sample/uncertainty và chính sách nhiều phép kiểm để tránh kết luận quá mức.
- [ ] Có guardrails cho nhóm rủi ro cao, không chỉ overall pass rate.
- [ ] Có latency/token/cost theo vai trò và có dữ liệu để giải thích hồi quy.
- [ ] Observability labels có cardinality thấp, không chứa user ID, case ID hoặc raw prompt.
- [ ] Run manifests ghi model/prompt/corpus/index/judge/rubric, taxonomy, sampling và price revision.
- [ ] Có quyết định `PROMOTE`, `REJECT`, `BLOCKED` hoặc `INCONCLUSIVE` kèm lý do và review.

## Tài liệu tham khảo

1. [Spring AI 2.1 — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): `Evaluator`, `EvaluationRequest` và cách đo relevance/groundedness trong kiểm thử AI.
2. [Spring AI — Evaluators (dòng 2.1)](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/evaluation/evaluators.html): ví dụ `RelevancyEvaluator`, `FactCheckingEvaluator` và judge rubric; kiểm tra release/Javadoc tương ứng khi dùng code.
3. [Spring AI — RAG](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html): retrieval, query transform, reranking và context assembly.
4. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): các observations của ChatClient, ChatModel, VectorStore, tool và token usage.
5. [Spring AI 2.1 — Metrics Reference](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/observability/metrics.html): Prometheus metrics, token types và histogram latency.
6. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) và [Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Actuator, Micrometer và OpenTelemetry.
7. [NIST Engineering Statistics Handbook](https://www.itl.nist.gov/div898/handbook/): thiết kế thí nghiệm, phân tích thống kê và độ bất định.
8. [SciPy — Exact Binomial Test](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html): nền tảng tính kiểm định McNemar exact trên các cặp bất đồng.
9. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): percentile latency và giới hạn của histograms.
10. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ secrets và dữ liệu nhạy cảm trong logs/telemetry.

> **Ghi nhớ:** Đừng hỏi chỉ “Model B có tăng PASS không?” mà hãy hỏi **“B có tốt hơn ở nghiệp vụ nào, mức khó nào, trên bao nhiêu case được chấm hợp lệ, có gây hồi quy ở nhóm quan trọng và phải trả giá bao nhiêu về thời gian/chi phí?”**. Phân tầng đúng, rubric độ khó độc lập, paired comparison và quality gate rõ ràng giúp kết quả Spring AI đáng tin hơn nhiều so với một con số accuracy tổng hợp.
