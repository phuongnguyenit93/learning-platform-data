# Đặt ngưỡng cho từng tiêu chí và quy tắc tổng hợp kết quả

> **Chương:** Evaluator tùy chỉnh  
> **Module:** `SPRING_AI_EVALUATION_OBSERVABILITY` — đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking, kiểm thử RAG và tool calling; kết hợp metrics, traces, chi phí và độ trễ để phát hiện suy giảm chất lượng giữa các phiên bản prompt, model và pipeline.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **điểm đo được**, **ngưỡng đạt của từng tiêu chí**, **ngưỡng tổng hợp của một case** và **điều kiện phát hành trên cả dataset**.
2. Thiết kế ngưỡng cho relevance, factual groundedness, citation, JSON contract, tool policy và các chỉ số vận hành theo đúng ý nghĩa của mỗi thước đo.
3. Dùng bộ dữ liệu có nhãn để hiệu chuẩn ngưỡng; nhận ra rủi ro của ngưỡng tùy tiện, lệch phân bố và thước đo thay đổi giữa hai phiên bản.
4. Viết mã tổng hợp kết quả có trọng số, điều kiện bắt buộc (*hard gate*), chính sách `NOT_APPLICABLE` và `ERROR`.
5. So sánh các phiên bản prompt/model/pipeline bằng báo cáo theo tiêu chí, nhóm dữ liệu, p95 latency, chi phí và trace.

## 1. Bốn cấp quyết định cần tách biệt

Một lượt đánh giá RAG có thể đạt điểm relevance `0.9`, groundedness `0.92`, citation `1` và tool policy không áp dụng. Câu hỏi "đạt hay trượt?" sẽ có các đáp án khác nhau tùy chính sách. Vì vậy cần phân biệt bốn cấp:

| Cấp | Quyết định | Ví dụ |
|---|---|---|
| **Điểm đo thô** | Evaluator trả ra mức độ hoặc một phép đo | `relevanceScore = 0.90` |
| **Ngưỡng từng tiêu chí** | Điểm có đáp ứng yêu cầu cụ thể? | Relevance cần ít nhất `0.80`; groundedness cần ít nhất `0.95` |
| **Tổng hợp trong một case** | Case có vượt ngưỡng điểm tổng và các hard gate? | Tổng ≥ `0.85`, đồng thời citation và tool permission không vi phạm |
| **Điều kiện của bản phát hành** | Candidate có đạt trên toàn dataset và SLA? | ≥ 95% ca groundedness đạt; 0 tool permission violation; p95 ≤ 3 giây |

Các ngưỡng trong bài đều là **giá trị minh họa** cho một ứng dụng giả định. Spring AI không mặc định rằng relevance phải bằng `0.8` hoặc groundedness phải bằng `0.95`; nhóm sản phẩm phải chọn ngưỡng từ rubric, dữ liệu thực tế và mức chấp nhận rủi ro.

### 1.1. Ngưỡng không thay thế ý nghĩa của điểm

`EvaluationResponse` trong Spring AI cung cấp kết quả `isPass()`, `getScore()`, `getFeedback()` và `getMetadata()`. Các evaluator khác nhau có thể dùng điểm khác nghĩa:

- Bộ kiểm tra JSON hoặc citation dạng nhị phân: `0` nghĩa là vi phạm, `1` nghĩa là đạt hợp đồng.
- Rubric relevance từ 0 đến 4: phải **chuẩn hóa có giải thích** nếu muốn dùng ở một thang 0–1.
- Groundedness theo tỷ lệ claim có căn cứ: `0.9` có thể nghĩa là 9/10 claim đã được hỗ trợ, **nếu** đây chính là định nghĩa scorer.
- Một LLM judge chỉ trả PASS/FAIL: không nên tùy tiện coi `score = 1` là "100% xác suất câu trả lời đúng".
- `p95 latency` hoặc chi phí có đơn vị giây, USD, token: không được gộp trực tiếp vào điểm chất lượng 0–1.

**Trước khi đặt ngưỡng, phải xác nhận điểm thực sự đo điều gì, nằm trong miền nào, chiều tốt/xấu ra sao và có đáng tin cậy hay không.** Không tự gán semantics cho điểm chỉ vì có tên `getScore()`.

## 2. Thiết kế một bảng chính sách ngưỡng

Giả sử trợ lý hỗ trợ đơn hàng trả lời theo RAG và đôi khi gọi tool. Chính sách có thể được thiết kế:

| Tiêu chí | Cách đo | Ngưỡng ở mỗi case | Bắt buộc? | Khi không áp dụng |
|---|---|---|---|---|
| `relevance` | Rubric 0–4, chuẩn hóa [0, 1] | ≥ `0.80` | Mềm | Không có câu trả lời cần chấm về nội dung theo rubric |
| `groundedness` | Tỷ lệ claim có căn cứ hoặc judge đã hiệu chuẩn | ≥ `0.95` | Mềm hoặc hard gate tùy rủi ro | Không có claim cần fact checking theo policy |
| `citation_contract` | Tất cả ID trích dẫn đúng nguồn | = `1` | **Hard gate** nếu yêu cầu citation | Case không yêu cầu nguồn và không chứa claim bắt buộc dẫn chứng |
| `json_contract` | Parse/schema/enum đúng | = `1` | **Hard gate** nếu consumer dùng JSON | Case được phép trả văn bản tự do |
| `tool_permission` | Không có tool thực thi trái quyền/xác nhận | = `1` | **Hard gate** | Không có tool call và kịch bản không yêu cầu tool |
| `unsupported_claim_rate` | Số claim sai nguồn / tổng claim đã chấm | ≤ `0.05` | Theo chính sách | Không có claim để tính tỷ lệ |
| `p95_latency` | Phân vị 95 của nhiều request | ≤ `3.0 giây` ở cấp dataset | Release gate | Chỉ N/A khi bài chạy không đặt SLA và có ghi rõ |
| `cost_per_request` | Chi phí tính theo token và đơn giá | ≤ ngân sách trên request hoặc trung bình dataset | Release gate | Khi không đo được phải báo lỗi dữ liệu đo, không tự cho PASS |

Lưu ý: `tool_permission` chỉ được xem là N/A nếu runtime xác nhận không có hoạt động tool và policy không yêu cầu tool. Nếu có gọi tool trái phép thì **FAIL**, kể cả khi người dùng không yêu cầu thao tác đó.

### 2.1. Ngưỡng có hai chiều

Với một số điểm, **càng cao càng tốt**:

\[
\operatorname{pass}_{\text{high}}(s,t) \iff s \ge t.
\]

Ví dụ relevance 0.86 với ngưỡng 0.80 ⇒ PASS.

Với một số tỷ lệ lỗi/độ trễ/chi phí, **càng thấp càng tốt**:

\[
\operatorname{pass}_{\text{low}}(x,t) \iff x \le t.
\]

Ví dụ tỷ lệ claim không có căn cứ `0.07`, ngưỡng tối đa `0.05` ⇒ FAIL. Không viết chung một toán tử `>=` cho mọi metric. Điều kiện đúng về chiều giúp tránh trường hợp "lỗi càng nhiều càng đạt".

**Không cộng điểm chất lượng và latency như cùng đơn vị.** Nếu muốn dùng một mục tiêu tối ưu nhiều chiều, phải chuẩn hóa và chứng minh cơ sở chọn hàm mục tiêu; đối với release gate, đặt riêng ngưỡng SLA/chi phí thường dễ giải thích hơn.

### 2.2. Ngưỡng trên mỗi case và ngưỡng trên cả dataset khác nhau

Ví dụ `groundedness >= 0.95` là điều kiện **một case** được chấm PASS ở tiêu chí đó. Còn yêu cầu "ít nhất 96% các case có groundedness PASS" là **điều kiện của bản phát hành**.

Nếu có 200 case áp dụng groundedness, trong đó 190 PASS, 7 FAIL và 3 ERROR:

\[
\text{Pass rate (đã chấm)} = \frac{190}{190+7}\approx96.45\%.
\]

Nhưng coverage chỉ là:

\[
\text{Evaluation coverage} = \frac{190+7}{200}=98.5\%.
\]

Nếu release policy yêu cầu coverage `100%` ở nhóm bắt buộc, candidate **chưa đạt** mặc dù pass rate trong các case đã chấm vượt 96%. Phải giải quyết 3 ERROR hoặc công bố chính sách xử lý ngoại lệ có thẩm quyền.

## 3. Chọn ngưỡng từ dataset có nhãn thay vì cảm tính

Giả sử bộ kiểm tra groundedness cho ra điểm 0–1. Trước khi chốt ngưỡng, nhóm cần một tập câu trả lời được người có chuyên môn gắn nhãn như "đủ căn cứ" hoặc "không đủ căn cứ".

### 3.1. Lập bảng kết quả theo ngưỡng

Dataset minh họa có 100 câu trả lời, gồm **60 câu được người đánh giá xác nhận đạt** và **40 câu không đạt**. Kết quả khi thay ngưỡng:

| Ngưỡng PASS | TP | FP | FN | TN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| ≥ 0.70 | 58 | 12 | 2 | 28 | 82.86% | 96.67% |
| ≥ 0.80 | 54 | 6 | 6 | 34 | 90.00% | 90.00% |
| ≥ 0.90 | 45 | 2 | 15 | 38 | 95.74% | 75.00% |

Trong đó **positive** nghĩa là **câu thực sự đáp ứng tiêu chí**:

- **TP (true positive):** câu đạt và evaluator chấm PASS.
- **FP (false positive):** câu không đạt nhưng evaluator vẫn chấm PASS.
- **FN (false negative):** câu đạt nhưng evaluator chấm FAIL.
- **TN (true negative):** câu không đạt và evaluator chấm FAIL.

\[
\operatorname{Precision}=\frac{TP}{TP+FP},\qquad
\operatorname{Recall}=\frac{TP}{TP+FN}.
\]

Khi tăng ngưỡng, evaluator có thể giảm trường hợp **chấp nhận nhầm câu trả lời kém** (FP) nhưng tăng trường hợp **loại nhầm câu trả lời tốt** (FN). Với chatbot chính sách pháp lý hoặc số liệu tài chính, chấp nhận nhầm câu sai có thể nguy hiểm hơn; với trợ lý giải đáp thông thường, mục tiêu có thể cân bằng khác.

Các số trên là **giả định minh họa**. Chúng không chứng minh rằng `0.90` là ngưỡng đúng cho mọi judge. Chỉ chốt ngưỡng trên dữ liệu thực tế, có nhãn đáng tin cậy và phản ánh phân bố sử dụng của sản phẩm.

### 3.2. Quy trình hiệu chuẩn ngưỡng

1. **Viết rubric trước:** định nghĩa thế nào là relevance đủ tốt, claim có căn cứ, trường hợp phải từ chối và các lỗi nghiệp vụ tuyệt đối không chấp nhận.
2. **Chuẩn bị dữ liệu đại diện:** chia theo loại câu hỏi, độ dài, ngôn ngữ, tình huống có/không đủ bằng chứng, thao tác tool, các ca dễ gây hallucination.
3. **Tạo nhãn chuẩn:** nhiều người chấm một phần ca khó, xử lý bất đồng, giữ ví dụ giải thích rõ lý do.
4. **Chạy evaluator cố định:** lưu `criterionVersion`, judge prompt/model version, đầu ra thô và điểm.
5. **Khảo sát các ngưỡng ứng viên:** tính confusion matrix, precision/recall, false-accept và false-reject; không chỉ nhìn average score.
6. **Chọn ngưỡng theo chi phí lỗi:** lỗi vi phạm quyền, nguồn giả hoặc giao dịch sai có thể cần hard gate tuyệt đối.
7. **Đánh giá trên tập holdout:** xác nhận ngưỡng đã chọn hoạt động trên tập dữ liệu không dùng để điều chỉnh ngưỡng.
8. **Phiên bản hóa policy:** khóa ngưỡng trước khi so sánh prompt A/B; theo dõi khi dữ liệu thực tế thay đổi.

Không chỉ chọn ngưỡng cao nhất cho "an toàn": nếu điểm judge chưa được hiệu chuẩn, ngưỡng cao có thể làm giảm nghiêm trọng khả năng trả lời hợp lệ mà vẫn không bảo đảm không có câu sai được chấp nhận.

### 3.3. Nếu evaluator chỉ trả nhị phân

Với một phép kiểm tra JSON Schema, `score∈{0,1}`, ngưỡng `1` mang nghĩa "mọi ràng buộc bắt buộc phải đạt". Đặt `0.8` trên score nhị phân không tạo ra mức chất lượng mới.

Với một `RelevancyEvaluator` hoặc `FactCheckingEvaluator` dựng sẵn, cần kiểm tra tài liệu/API và hành vi điểm của **đúng phiên bản**: nếu chỉ trả kết quả nhị phân, không thể dùng điểm đó như một mức liên tục đã hiệu chuẩn. Khi cần điểm nhiều mức, hãy triển khai judge/rubric riêng với kết quả có cấu trúc, kiểm tra miền điểm và đối chiếu nhãn người đánh giá.

**Tránh nhầm độ tự tin tự khai của mô hình (`confidence`) với xác suất câu trả lời thực sự đúng.** Một trường do mô hình tự sinh có thể sai lệch đáng kể; muốn dùng nó để quyết định ngưỡng cần kiểm định calibration trên dữ liệu gắn nhãn.

## 4. Chọn phương pháp tổng hợp tiêu chí

Các cách tổng hợp phổ biến:

| Chính sách | Cách quyết định | Phù hợp | Rủi ro |
|---|---|---|---|
| **AND / tất cả đạt** | Mọi tiêu chí bắt buộc PASS | Hợp đồng cứng, kiểm thử giao dịch | Một lỗi nhỏ có thể chặn toàn bộ |
| **Weighted mean** | Tổng có trọng số vượt ngưỡng | Nhiều chiều chất lượng mềm | Điểm cao ở mục này có thể che lỗi mục khác |
| **Minimum floor** | Mỗi chiều phải vượt một sàn | Không cho một chiều quá kém | Cần chọn ngưỡng hợp lý cho từng chiều |
| **Hard gate + weighted mean** | Gate bắt buộc đạt, sau đó xét điểm mềm | RAG/tool calling thực tế | Phải quản lý N/A/ERROR cẩn thận |
| **Lexicographic** | So quyền/an toàn trước, rồi chất lượng, rồi latency/cost | Hệ thống ưu tiên rủi ro | Không thể rút gọn tùy ý thành một số |
| **Pareto comparison** | Không cải thiện một chiều bằng suy giảm không chấp nhận ở chiều khác | Phân tích chiến lược A/B | Có thể không có một ứng viên thắng rõ |

Với ứng dụng Spring AI vừa RAG vừa gọi tool, một lựa chọn dễ hiểu là:

- **Hard gate:** quyền gọi tool, JSON hợp đồng bắt buộc, citation không bịa nguồn khi cần.
- **Các chiều chấm điểm:** relevance, groundedness, completeness, clarity nếu đã có thang đo rõ.
- **Giới hạn vận hành:** p95 latency, error rate và chi phí trong phạm vi SLA/ngân sách.

Đây là một **chính sách ví dụ**; nhóm vận hành có thể quyết định groundedness cũng là hard gate cho các ứng dụng rủi ro cao.

## 5. Công thức điểm tổng và dữ liệu không áp dụng

Giả sử có các tiêu chí `i`, trọng số `w_i >= 0` và điểm chuẩn hóa `s_i∈[0,1]`. Chỉ lấy tập tiêu chí đã được chấm và **có áp dụng** `A`:

\[
S=\frac{\sum_{i\in A}w_i s_i}{\sum_{i\in A} w_i},\quad
\sum_{i\in A}w_i>0.
\]

Nếu một tiêu chí **NOT_APPLICABLE**, loại trọng số của nó khỏi cả tử số và mẫu số. Nếu tiêu chí **ERROR**, không âm thầm coi là N/A để tính điểm; phải có policy xử lý lỗi chấm riêng. Nếu không còn tiêu chí nào áp dụng thì điểm tổng **không xác định**, không tự đặt bằng 0 hay 1.

### 5.1. Ví dụ RAG không cần tool

| Tiêu chí | Trọng số | Điểm | Kết quả từng tiêu chí |
|---|---:|---:|---|
| Relevance | 0.30 | 0.88 | PASS (ngưỡng ≥ 0.80) |
| Groundedness | 0.35 | 0.97 | PASS (ngưỡng ≥ 0.95) |
| Citation integrity | 0.20 | 1.00 | PASS (hard gate) |
| Tool permission | 0.15 | null | NOT_APPLICABLE |

\[
S=\frac{0.30(0.88)+0.35(0.97)+0.20(1.0)}
{0.30+0.35+0.20}
=\frac{0.8035}{0.85}
\approx 0.9453.
\]

Nếu ngưỡng điểm tổng là `0.90`, case PASS. Nếu gán N/A thành 0, case chỉ đạt `0.8035` và có thể bị loại sai mặc dù không cần tool.

### 5.2. Tại sao hard gate phải xét riêng?

Đổi kết quả citation thành FAIL `0`, các chiều khác giữ nguyên. Điểm trung bình còn:

\[
S=\frac{0.30(0.88)+0.35(0.97)+0.20(0)}{0.85}
\approx 0.710.
\]

Ngay cả nếu điểm trung bình vượt ngưỡng, case **vẫn phải FAIL** nếu citation là hard gate. Với `tool_permission`, một lần gọi `cancelOrder` trái phép không thể bị relevance cao bù trừ.

### 5.3. Xử lý cùng lúc hard-gate FAIL và ERROR

Một thứ tự tổng hợp có thể dùng:

1. Lưu **đầy đủ kết quả mọi tiêu chí** và những evaluator chưa chạy, không ngắt ghi dữ liệu khi gặp một lỗi.
2. Nếu đã xác nhận **hard gate FAIL** → overall `FAIL`, mã `HARD_GATE_FAILED`.
3. Nếu không có hard-gate FAIL nhưng có **ERROR ở tiêu chí bắt buộc** → overall `ERROR`, mã `INCOMPLETE_EVALUATION`.
4. Nếu tất cả tiêu chí `NOT_APPLICABLE` → overall `NOT_APPLICABLE`, `score = null`.
5. Nếu chỉ có hard gate trọng số 0, tất cả gate PASS → overall `PASS` về điều kiện gate, **không tạo điểm trung bình**.
6. Nếu có tiêu chí chấm điểm → tính weighted mean trên các điểm đã chấm; quyết định tổng dựa trên ngưỡng tổng và các floor nếu policy yêu cầu.

`NOT_APPLICABLE` nghĩa là tiêu chí **không liên quan theo policy**; `ERROR` nghĩa là **đáng lẽ phải chấm nhưng không thể chấm**. Một evaluator chưa chạy do tối ưu ngân sách cũng không tự động N/A: pipeline nên có trạng thái `NOT_RUN` hoặc bản ghi scheduling riêng.

### 5.4. Ngưỡng tối thiểu cho từng chiều

Chỉ dùng weighted mean có thể gây một vấn đề: relevance `0.99`, clarity `0.99`, groundedness `0.30` vẫn có thể cho tổng cao nếu groundedness trọng số thấp.

Cách xử lý:

- Đặt `groundedness >= 0.75` làm **minimum floor** của case, dù trọng số chỉ 0.20.
- Hoặc coi groundedness là **hard gate** nếu rủi ro việc đưa thông tin sai quá lớn.
- Giữ ngưỡng weighted score để phản ánh chất lượng tổng sau khi các floor/gate đã đạt.

Ngưỡng từng tiêu chí cần có ý nghĩa riêng. Không gọi mọi `FAIL` ở tiêu chí mềm là chặn tuyệt đối nếu chính sách cho phép bù trừ; ngược lại, không cho hard gate bị bù trừ bằng điểm trung bình.

## 6. Cài đặt Java: máy quyết định ngưỡng và tổng hợp

Đoạn sau là một lớp Java 17+ độc lập, dùng dữ liệu đánh giá đã được chuẩn hóa và tách rõ **đo điểm** khỏi **áp ngưỡng**. Nó có thể được gọi từ coordinator sau khi chạy các `Evaluator` của Spring AI và các rule RAG/tool tùy chỉnh.

### 6.1. Mô hình policy và measurement

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class ThresholdAggregator {

    private ThresholdAggregator() {}

    public enum Direction {
        AT_LEAST, AT_MOST
    }

    // MEASURED nghĩa là có điểm hợp lệ, chưa kết luận PASS/FAIL.
    public enum MeasureState {
        MEASURED, NOT_APPLICABLE, ERROR
    }

    public enum Verdict {
        PASS, FAIL, NOT_APPLICABLE, ERROR
    }

    public record CriterionPolicy(
            String criterionId,
            Direction direction,
            double threshold,
            double weight,
            boolean hardGate) {

        public CriterionPolicy {
            if (criterionId == null || criterionId.isBlank()) {
                throw new IllegalArgumentException("Thiếu criterionId");
            }
            Objects.requireNonNull(direction);
            if (!Double.isFinite(threshold)
                    || threshold < 0 || threshold > 1) {
                throw new IllegalArgumentException("threshold phải thuộc [0,1]");
            }
            if (!Double.isFinite(weight) || weight < 0) {
                throw new IllegalArgumentException("weight không hợp lệ");
            }
            if (weight == 0 && !hardGate) {
                throw new IllegalArgumentException(
                        "Chỉ hard gate được phép có weight = 0");
            }
        }
    }

    public record Measurement(
            String criterionId,
            MeasureState state,
            Double score,
            String reasonCode) {

        public Measurement {
            if (criterionId == null || criterionId.isBlank()) {
                throw new IllegalArgumentException("Thiếu criterionId");
            }
            Objects.requireNonNull(state);
            Objects.requireNonNull(reasonCode);
            if (state == MeasureState.MEASURED) {
                if (score == null || !Double.isFinite(score)
                        || score < 0 || score > 1) {
                    throw new IllegalArgumentException(
                            "MEASURED phải có score trong [0,1]");
                }
            }
            else if (score != null) {
                throw new IllegalArgumentException(
                        "NOT_APPLICABLE và ERROR phải có score = null");
            }
        }
    }

    public record CriterionVerdict(
            String criterionId,
            Verdict verdict,
            Double score,
            String reasonCode) {}

    public record CaseVerdict(
            Verdict verdict,
            Double overallScore,
            String reasonCode,
            List<CriterionVerdict> criteria) {}

    public static CaseVerdict evaluate(
            List<CriterionPolicy> policies,
            List<Measurement> measurements,
            double overallThreshold) {

        Objects.requireNonNull(policies);
        Objects.requireNonNull(measurements);
        if (!Double.isFinite(overallThreshold)
                || overallThreshold < 0 || overallThreshold > 1) {
            throw new IllegalArgumentException(
                    "overallThreshold phải thuộc [0,1]");
        }

        Set<String> policyIds = new HashSet<>();
        for (CriterionPolicy policy : policies) {
            if (!policyIds.add(policy.criterionId())) {
                throw new IllegalArgumentException("Trùng criterion policy");
            }
        }

        Map<String, Measurement> byId = new HashMap<>();
        for (Measurement measurement : measurements) {
            if (byId.putIfAbsent(
                    measurement.criterionId(), measurement) != null) {
                throw new IllegalArgumentException("Trùng measurement");
            }
        }
        if (!policyIds.containsAll(byId.keySet())) {
            throw new IllegalArgumentException(
                    "Measurement có criterionId chưa được khai báo");
        }

        List<CriterionVerdict> details = new ArrayList<>();
        boolean anyHardGateFailed = false;
        boolean anyError = false;
        int measuredCount = 0;
        double weightedSum = 0.0;
        double totalWeight = 0.0;

        for (CriterionPolicy policy : policies) {
            Measurement measurement = byId.get(policy.criterionId());

            if (measurement == null
                    || measurement.state() == MeasureState.ERROR) {
                details.add(new CriterionVerdict(
                        policy.criterionId(), Verdict.ERROR, null,
                        measurement == null
                                ? "MISSING_MEASUREMENT"
                                : measurement.reasonCode()));
                anyError = true;
                continue;
            }

            if (measurement.state() == MeasureState.NOT_APPLICABLE) {
                details.add(new CriterionVerdict(
                        policy.criterionId(), Verdict.NOT_APPLICABLE,
                        null, measurement.reasonCode()));
                continue;
            }

            double score = measurement.score();
            boolean pass = policy.direction() == Direction.AT_LEAST
                    ? score >= policy.threshold()
                    : score <= policy.threshold();

            details.add(new CriterionVerdict(
                    policy.criterionId(),
                    pass ? Verdict.PASS : Verdict.FAIL,
                    score,
                    pass ? "THRESHOLD_MET" : "CRITERION_THRESHOLD_FAILED"));

            measuredCount++;
            if (!pass && policy.hardGate()) {
                anyHardGateFailed = true;
            }

            if (policy.weight() > 0) {
                // Chuyển tỷ lệ lỗi LOW-is-better thành utility 1 - score.
                // Chỉ phù hợp với những tỷ lệ đã chuẩn hóa trong [0,1].
                double utility = policy.direction() == Direction.AT_LEAST
                        ? score : 1.0 - score;
                weightedSum += policy.weight() * utility;
                totalWeight += policy.weight();
            }
        }

        List<CriterionVerdict> immutableDetails = List.copyOf(details);

        if (anyHardGateFailed) {
            return new CaseVerdict(
                    Verdict.FAIL, null, "HARD_GATE_FAILED", immutableDetails);
        }
        if (anyError) {
            return new CaseVerdict(
                    Verdict.ERROR, null, "INCOMPLETE_EVALUATION",
                    immutableDetails);
        }
        if (measuredCount == 0) {
            return new CaseVerdict(
                    Verdict.NOT_APPLICABLE, null, "NO_APPLICABLE_CRITERIA",
                    immutableDetails);
        }
        if (totalWeight == 0) {
            return new CaseVerdict(
                    Verdict.PASS, null, "ONLY_GATES_PASSED",
                    immutableDetails);
        }

        double overallScore = weightedSum / totalWeight;
        boolean overallPass = overallScore >= overallThreshold;
        return new CaseVerdict(
                overallPass ? Verdict.PASS : Verdict.FAIL,
                overallScore,
                overallPass ? "OVERALL_THRESHOLD_MET"
                            : "OVERALL_THRESHOLD_FAILED",
                immutableDetails);
    }
}
```

**Lý do không cộng trực tiếp các điểm `AT_MOST`:** Một điểm `unsupported_claim_rate = 0.02` là **tốt**, nhưng nếu đưa nguyên `0.02` vào weighted mean (nơi điểm cao nghĩa là tốt), nó sẽ kéo tổng xuống như thể chất lượng kém. Trong mã minh họa, tiêu chí `AT_MOST` được chuyển thành **utility score = `1 - score`** trước khi cộng trọng số; điều này phù hợp với tỷ lệ lỗi đã chuẩn hóa trong [0,1]. Việc chuyển đổi phải được ghi trong phiên bản rubric. Với độ trễ tính bằng mili giây hoặc chi phí tính theo USD, không sử dụng công thức `1 - x`; hãy đặt ngưỡng vận hành riêng hoặc thiết kế một hàm utility có đơn vị và ý nghĩa rõ ràng.

Mã sử dụng quy ước:

- Mọi measurement `MEASURED` phải có score hữu hạn trong [0,1]; không chấp nhận NaN, Infinity hoặc score ngoài thang.
- `NOT_APPLICABLE` và `ERROR` có score bằng `null`.
- Nếu thiếu measurement cho một criterion đã khai báo, đánh giá tổng là `ERROR`; không âm thầm bỏ criterion.
- Nếu có hard gate FAIL, tổng FAIL; nếu không có gate FAIL mà có ERROR, tổng ERROR.
- N/A không đóng góp điểm. Trường hợp chỉ còn gate trọng số 0 và tất cả PASS trả overall PASS với score `null`.
- Một tiêu chí `AT_MOST` có trọng số dương đóng góp bằng `1 - score`, chỉ khi score là tỷ lệ [0,1] mà phép chuyển đổi này có ý nghĩa. Trong production, nên khai báo tường minh phương pháp chuyển đổi; các metric có đơn vị vận hành được kiểm tra trong release gate riêng.

### 6.2. Cấu hình policy và kiểm tra một case RAG

```java
import java.util.List;
import static ThresholdAggregator.Direction.AT_LEAST;
import static ThresholdAggregator.MeasureState.MEASURED;
import static ThresholdAggregator.MeasureState.NOT_APPLICABLE;

var policies = List.of(
        new ThresholdAggregator.CriterionPolicy(
                "relevance", AT_LEAST, 0.80, 0.30, false),
        new ThresholdAggregator.CriterionPolicy(
                "groundedness", AT_LEAST, 0.95, 0.35, false),
        new ThresholdAggregator.CriterionPolicy(
                "citation_contract", AT_LEAST, 1.00, 0.20, true),
        new ThresholdAggregator.CriterionPolicy(
                "tool_permission", AT_LEAST, 1.00, 0.15, true)
);

var measurements = List.of(
        new ThresholdAggregator.Measurement(
                "relevance", MEASURED, 0.88, "RUBRIC_SCORE"),
        new ThresholdAggregator.Measurement(
                "groundedness", MEASURED, 0.97, "CLAIMS_SUPPORTED"),
        new ThresholdAggregator.Measurement(
                "citation_contract", MEASURED, 1.00, "VALID_CITATIONS"),
        new ThresholdAggregator.Measurement(
                "tool_permission", NOT_APPLICABLE, null, "NO_TOOL_ACTIVITY")
);

var result = ThresholdAggregator.evaluate(
        policies, measurements, 0.90);

System.out.println(result.verdict());      // PASS
System.out.println(result.overallScore()); // xấp xỉ 0.9453
System.out.println(result.criteria().size()); // 4
```

Tập `measurements` phải do các evaluator thực tế tạo ra. Lệnh kiểm tra tool chỉ được tạo N/A khi policy và runtime chứng minh case không yêu cầu và không gọi tool. Không giao cho model tự sinh `NO_TOOL_ACTIVITY` để né kiểm tra quyền.

### 6.3. Cầu nối với Spring AI `Evaluator`

Khi `RelevancyEvaluator`, `FactCheckingEvaluator` hay custom `Evaluator` trả `EvaluationResponse`, lớp điều phối có thể ghi nhận điểm và lỗi thực thi:

```java
import org.springframework.ai.evaluation.Evaluator;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;

static ThresholdAggregator.Measurement evaluateSpring(
        String criterionId, Evaluator evaluator, EvaluationRequest request) {
    try {
        EvaluationResponse response = evaluator.evaluate(request);
        if (response == null) {
            return new ThresholdAggregator.Measurement(
                    criterionId, ThresholdAggregator.MeasureState.ERROR,
                    null, "JUDGE_NO_RESPONSE");
        }

        double score = response.getScore();
        if (!Double.isFinite(score) || score < 0 || score > 1) {
            return new ThresholdAggregator.Measurement(
                    criterionId, ThresholdAggregator.MeasureState.ERROR,
                    null, "INVALID_SCORE");
        }
        return new ThresholdAggregator.Measurement(
                criterionId, ThresholdAggregator.MeasureState.MEASURED,
                score, response.isPass()
                        ? "EVALUATOR_PASS" : "EVALUATOR_FAIL");
    }
    catch (RuntimeException exception) {
        // Ghi chi tiết exception/trace vào nơi có kiểm soát quyền.
        return new ThresholdAggregator.Measurement(
                criterionId, ThresholdAggregator.MeasureState.ERROR,
                null, "EVALUATOR_ERROR");
    }
}
```

Đây là **adapter minh họa**, không phải chức năng tự động của Spring AI. Nó chỉ phù hợp khi evaluator trả `score` có ý nghĩa, nằm trong [0,1] và đã được thống nhất với ngưỡng của `CriterionPolicy`. Nếu một evaluator chỉ trả kết quả nhị phân hoặc đặt `score` theo quy ước khác, phải dùng `isPass()` làm quyết định gốc hoặc có adapter đổi sang thang đo đã được hiệu chuẩn. **Không tùy ý áp ngưỡng 0.8 lên một điểm chưa rõ ngữ nghĩa.** Có thể giữ cả `isPass()` trong raw result để phát hiện cấu hình threshold không nhất quán.

## 7. Kiểm thử các quy tắc tổng hợp

### 7.1. Ca cần có trong unit test

| Tình huống | Kỳ vọng |
|---|---|
| Relevance `0.88`, groundedness `0.97`, citation PASS, tool N/A | Tổng PASS ở ngưỡng 0.90 |
| Citation `0`, relevance/groundedness cao | Tổng FAIL do hard gate |
| Tool có thực thi trái quyền | `tool_permission` FAIL; tổng FAIL dù điểm tổng tiềm năng cao |
| Groundedness ERROR vì judge timeout | Tổng ERROR khi không có hard-gate FAIL |
| Citation N/A theo policy, các tiêu chí còn lại có điểm | Loại trọng số citation khỏi mẫu số |
| Tất cả N/A | Tổng N/A, `overallScore = null` |
| Chỉ hard gates trọng số 0 và tất cả đạt | Tổng PASS, không sinh overallScore |
| Criterion bị thiếu dữ liệu đánh giá | Tổng ERROR với `MISSING_MEASUREMENT` |
| Measurement chứa `NaN`, Infinity, score âm hoặc lớn hơn 1 | Từ chối input |
| Cùng criterionId xuất hiện hai lần | Từ chối cấu hình/measurement |
| Ngưỡng 0.8, score đúng bằng 0.8 | PASS khi quy tắc dùng `>=` |
| Một điểm lỗi `AT_MOST` cao hơn max | FAIL theo tiêu chí, hard gate chặn nếu được khai báo |

### 7.2. Ví dụ JUnit 5 cho hard gate và ERROR

```java
import static org.junit.jupiter.api.Assertions.*;
import static ThresholdAggregator.Direction.AT_LEAST;
import static ThresholdAggregator.MeasureState.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class ThresholdAggregatorTest {
    private final List<ThresholdAggregator.CriterionPolicy> policy =
            List.of(
                    new ThresholdAggregator.CriterionPolicy(
                            "relevance", AT_LEAST, .80, .60, false),
                    new ThresholdAggregator.CriterionPolicy(
                            "citation", AT_LEAST, 1.0, .40, true)
            );

    @Test
    void hardGateFailureBlocksEvenHighRelevance() {
        var measurements = List.of(
                new ThresholdAggregator.Measurement(
                        "relevance", MEASURED, 1.0, "OK"),
                new ThresholdAggregator.Measurement(
                        "citation", MEASURED, 0.0, "UNKNOWN_SOURCE")
        );

        var outcome = ThresholdAggregator.evaluate(
                policy, measurements, .50);
        assertEquals(ThresholdAggregator.Verdict.FAIL, outcome.verdict());
        assertEquals("HARD_GATE_FAILED", outcome.reasonCode());
        assertNull(outcome.overallScore());
    }

    @Test
    void judgeTimeoutIsNotAZeroScore() {
        var measurements = List.of(
                new ThresholdAggregator.Measurement(
                        "relevance", ERROR, null, "JUDGE_TIMEOUT"),
                new ThresholdAggregator.Measurement(
                        "citation", MEASURED, 1.0, "VALID_CITATION")
        );

        var outcome = ThresholdAggregator.evaluate(
                policy, measurements, .80);
        assertEquals(ThresholdAggregator.Verdict.ERROR, outcome.verdict());
        assertNull(outcome.overallScore());
    }
}
```

Đây là ví dụ hướng dẫn, chưa được chạy trong môi trường của dự án. Khi tích hợp thật, nên có kiểm thử với evaluator stub không gọi model, kiểm thử data capture, và một tập ca hồi quy chạy qua ứng dụng Spring AI đúng phiên bản dependency của dự án.

## 8. Quy tắc tổng hợp ở cấp bản phát hành

Một điểm PASS của từng case vẫn chưa đủ để quyết định phát hành. Release gate cần kiểm tra **toàn bộ phân bố kết quả**, dữ liệu có được chấm đủ hay không, và những sự cố hiếm nhưng nghiêm trọng.

Ví dụ cấu hình chính sách giả định:

```yaml
releasePolicyVersion: support-ai-release-v2
datasetVersion: support-rag-v7
criterionVersions:
  relevance: relevance-v3
  groundedness: groundedness-v2
  citation_contract: citation-v1
  tool_permission: tool-policy-v2

casePolicy:
  overallScoreAtLeast: 0.90
  hardGates: [citation_contract, tool_permission]

datasetGates:
  relevancePassRateAtLeast: 0.92
  groundednessPassRateAtLeast: 0.95
  citationPassRateAtLeast: 0.99
  permissionViolationsAllowed: 0
  mandatoryEvaluationCoverageAtLeast: 1.00
  p95LatencyMsAtMost: 3000
  averageApplicationCostUsdAtMost: 0.01
```

Đây là **schema cấu hình minh họa**, không phải file cấu hình được Spring AI hỗ trợ mặc định. Ứng dụng phải tự tải cấu hình, kiểm tra tính hợp lệ và triển khai quyết định release theo dữ liệu thực.

### 8.1. PASS rate phải có mẫu số chính xác

Cho một tiêu chí:

- `PASS = 180`
- `FAIL = 10`
- `NOT_APPLICABLE = 5`
- `ERROR = 5`

Tổng 200 ca. Khi đó:

\[
\text{PassRate}_{\text{evaluated}}=
\frac{180}{180+10} \approx 94.74\%.
\]

Tỷ lệ có thể chấm trong số ca thực sự **áp dụng**:

\[
\text{Coverage}_{\text{applicable}} =
\frac{180+10}{180+10+5} \approx 97.44\%.
\]

Tỷ lệ N/A trên toàn dataset là `5/200 = 2.5%`. Nếu chỉ báo "94.74% PASS" mà không báo `5 ERROR` và `5 N/A`, nhóm vận hành có thể đánh giá sai mức độ đầy đủ của bằng chứng.

**Không nên gộp N/A vào mẫu số PASS/FAIL** nếu N/A được policy cho phép; đồng thời không âm thầm loại những case ERROR khỏi kiểm tra coverage.

### 8.2. Macro average và micro average

Khi dataset có các nhóm không cân bằng (ví dụ 900 câu hỏi đơn giản và 100 ca tool nhạy cảm), tính pass rate gộp trên toàn dataset có thể che tình trạng nhóm nhỏ:

- **Micro average:** tính tổng PASS chia tổng case đã chấm. Nhóm nhiều mẫu có ảnh hưởng lớn.
- **Macro average:** tính pass rate từng nhóm rồi lấy trung bình các nhóm (nếu các nhóm được coi quan trọng ngang nhau).
- **Worst-slice floor:** yêu cầu mỗi nhóm quan trọng vượt một ngưỡng sàn, ví dụ tool cancellation có 0 vi phạm.

Không có một kiểu trung bình đúng cho mọi sản phẩm. Hãy nêu rõ tập case, phân nhóm, mẫu số và trọng số. Với nhóm có rất ít mẫu, phần trăm dao động mạnh; cần báo cả số ca thực tế và độ bất định khi kết luận.

### 8.3. p95 latency phải tính trên nhiều request

**p95 không phải độ trễ của một request đơn lẻ.** Với `n` số đo độ trễ xếp tăng dần, một cách tính mẫu thường dùng là *nearest-rank percentile*:

\[
\operatorname{p95} = x_{\lceil 0.95n\rceil},
\]

trong đó `x_k` là phần tử thứ `k` của dãy đã sắp xếp, bắt đầu từ 1. Các công cụ monitoring có thể dùng cách ước lượng phân vị/histogram khác; cần thống nhất cửa sổ thời gian, tập request, phương pháp và loại bỏ/bao gồm timeout theo policy.

Ví dụ có 100 request, nếu phần tử thứ 95 sau sắp xếp là 2.8 giây thì p95 là 2.8 giây. Không thể suy ra p95 = 2.8 chỉ từ một response của model. Cần thêm phép đo số mẫu, tỷ lệ lỗi và sự phân bố giữa các phiên bản để nhận ra thắt nút cổ chai.

### 8.4. Chi phí và độ trễ phải tách luồng ứng dụng khỏi luồng chấm

Nếu một custom evaluator sử dụng LLM-as-a-judge cho mọi request, việc kiểm tra chất lượng có thể làm tăng token, chi phí và latency. Cần phân biệt:

| Phạm vi | Chỉ số cần báo |
|---|---|
| **Ứng dụng phục vụ người dùng** | p50/p95 latency, token input/output, chi phí model, số vòng tool, retrieval latency |
| **Pipeline đánh giá** | Judge call count, judge tokens/cost, judge p95 latency, error rate |
| **Phát hành theo dataset** | Pass rate/coverage từng tiêu chí, hard gate violations, SLA/chi phí theo chính sách |

Không so sánh hai phiên bản như thể A tốn ít hơn B nếu một lần đánh giá A chạy 1 judge còn B chạy 3 judge. Giữ điều kiện đo tương đồng hoặc báo hai loại chi phí riêng.

## 9. Theo dõi ngưỡng và kết quả qua metrics, traces

Spring AI có cơ chế quan sát dựa trên Micrometer cho những thành phần như ChatClient, ChatModel, advisor, vector store và tool (tùy cách tích hợp, phiên bản và nhà cung cấp). Các kết quả đánh giá là dữ liệu nghiệp vụ **do ứng dụng tự thu thập và gắn nhãn**, không tự có dashboard release chỉ vì đã triển khai `Evaluator`.

Một bản ghi chấm có thể chứa:

```json
{
  "runId": "eval-run-017",
  "caseId": "refund-case-031",
  "datasetVersion": "support-rag-v7",
  "criterionId": "groundedness",
  "criterionVersion": "groundedness-v2",
  "score": 0.91,
  "threshold": 0.95,
  "status": "FAIL",
  "reasonCode": "CRITERION_THRESHOLD_FAILED",
  "feedback": "Một khẳng định chưa được nguồn hỗ trợ.",
  "promptVersion": "refund-prompt-v8",
  "modelVersion": "model-c",
  "pipelineVersion": "rag-v6",
  "traceId": "trace-example",
  "evaluationError": null
}
```

Trong thực tế, `traceId` và `caseId` phải liên kết tới đúng lượt chạy. Nên giữ raw output, tài liệu truy xuất và đối số tool trong hệ thống lưu trữ có phân quyền; **tránh dùng PII, văn bản người dùng hoặc ID giao dịch có cardinality cao làm metric tag**. Metric tags phù hợp hơn với `criterionId`, `status`, `reasonCode` và phiên bản đã kiểm soát.

| Tín hiệu | Nguồn quan sát | Hướng điều tra |
|---|---|---|
| Relevance giảm dưới ngưỡng sau khi thay prompt | Query rewrite, prompt version, output model | Prompt mới lạc trọng tâm hoặc bỏ yêu cầu |
| Groundedness giảm nhưng retrieval recall giữ nguyên | Retrieved chunks thực sự vào prompt, model version, token budget | Generation thêm claim, context bị cắt |
| Citation hard gate FAIL tăng | Mapping source/chunk ID, trace retrieval, nội dung trích dẫn | ID không thống nhất, model trích tài liệu lạ |
| Tool permission gate FAIL | Tool execution record, auth context, xác nhận và thứ tự | Tool được gọi sai quyền/luồng |
| ERROR tăng, pass rate không đổi | Judge timeout, rate limit, snapshot capture errors | Hạ tầng chấm không ổn định |
| p95 tăng vượt SLA | Model, retriever, tool spans, số lần retry | Thay top-k, context quá dài, tool loop |
| Chi phí trung bình tăng | Token usage, số call, model price snapshot | Model mới đắt, nhiều chunk, judge chạy đồng bộ |

Khi một chỉ số xuống dưới ngưỡng, hãy xem **những case đổi trạng thái** từ PASS sang FAIL hoặc N/A/ERROR, không chỉ đồ thị trung bình. Có thể nhóm theo `promptVersion`, `modelVersion`, `pipelineVersion`, `datasetVersion` rồi truy ngược `traceId` của các ca bị ảnh hưởng.

## 10. Chọn ngưỡng phát hành và giữ so sánh công bằng

Một quy trình đánh giá candidate B so với baseline A:

1. **Đóng băng dataset và thước đo**: giữ `caseId`, snapshot RAG/tool, tiêu chí, rubric, ngưỡng và phiên bản judge giống nhau cho cả A/B.
2. **Chạy hai phiên bản** trên cùng tập ca, giới hạn cấu hình nếu muốn cô lập tác động của một biến.
3. **Tính kết quả từng criterion** và các nhóm quan trọng (tool, không có nguồn, nhiều ngôn ngữ, câu hỏi khó).
4. **Áp dụng hard gates**: quyền, nguồn giả, ràng buộc cấu trúc bắt buộc không được bù bởi điểm mềm.
5. **Kiểm tra coverage và lỗi judge**; không kết luận B tốt hơn nếu nhiều ca chưa chấm được.
6. **Đối chiếu p95, error rate và chi phí** trong môi trường đo có tính tương đương.
7. **Phân tích sự khác biệt theo case/trace**, ghi nhận nguyên nhân và quyết định điều chỉnh prompt, retriever, tool schema hay model.

Ví dụ báo cáo giả định:

| Chỉ số trên 200 case | A | B | Đánh giá |
|---|---:|---:|---|
| Relevance pass rate | 93% | 96% | B tốt hơn |
| Groundedness pass rate | 97% | 94% | B giảm dưới ngưỡng release 95% |
| Citation violation | 1 | 0 | B cải thiện |
| Tool permission violation | 0 | 1 | **B bị hard gate chặn** |
| Ca đánh giá ERROR | 0 | 3 | B chưa có coverage đầy đủ |
| p95 application latency | 2.3 s | 3.1 s | B vượt SLA 3.0 s |
| Application cost/request | 0.008 USD | 0.012 USD | B vượt ngân sách 0.010 USD |

Kết quả B tăng relevance nhưng vẫn **không đủ điều kiện phát hành** theo chính sách giả định: groundedness giảm, có vi phạm quyền tool, p95 và chi phí vượt ngưỡng, còn ERROR. Đây là lý do một điểm tổng chất lượng không thể thay thế nhiều điều kiện ra quyết định.

### 10.1. Không tối ưu ngưỡng trên cùng tập dữ liệu dùng để báo thành tích

Nếu liên tục thay ngưỡng đến khi candidate B đạt PASS trên tập kiểm thử, đó là một dạng **overfitting policy vào dataset**. Cần tách tập hiệu chuẩn, tập giữ lại để xác nhận, và dữ liệu hồi quy có kiểm soát phiên bản. Khi thêm một lớp câu hỏi mới hoặc nguồn dữ liệu thay đổi, đánh giá lại tính thích hợp của ngưỡng; nếu thay ngưỡng thì phải chấm lại baseline dưới cùng policy để so sánh công bằng.

### 10.2. Những tình huống yêu cầu diễn giải theo nhóm

- **Trung bình tốt nhưng nhóm tool xấu:** không cho số đông câu hỏi đơn giản che các ca có hành động.
- **Relevance tốt nhưng groundedness kém:** kiểm tra retrieval và generation riêng để xác định thiếu nguồn hay suy đoán.
- **Không có bằng chứng:** nếu chính sách buộc từ chối, chấm abstention; không xem việc không có claim là mọi tiêu chí đều PASS.
- **Data drift:** phân bố câu hỏi, tài liệu hoặc policy thay đổi; báo cáo slice và cập nhật bộ dữ liệu.
- **Judge drift:** đổi model/prompt judge làm thay đổi thước đo; cần hiệu chuẩn lại trên nhãn chuẩn trước khi kết luận chất lượng ứng dụng thay đổi.

## 11. Những lỗi cần tránh khi đặt ngưỡng

1. **Dùng một ngưỡng cho mọi tiêu chí.** Relevance, tỷ lệ claim sai, độ trễ và chi phí có thang và chiều khác nhau.
2. **Ngầm hiểu score là xác suất.** Một rubric 0–1 không tự chứng minh `0.8 = 80% đúng`.
3. **Lấy score của judge chỉ có PASS/FAIL làm điểm liên tục.** Thang cần được mô tả và hiệu chuẩn.
4. **Coi N/A là 0 hoặc 1.** Làm méo mẫu số và điểm tổng của những case không thuộc phạm vi.
5. **Ẩn ERROR khỏi điều kiện phát hành.** Lỗi hệ thống chấm chưa cho phép kết luận chất lượng.
6. **Để hard gate bị bù trừ.** Một hành động trái phép vẫn FAIL dù các tiêu chí mềm đạt điểm cao.
7. **Không chia tập hiệu chuẩn và holdout.** Tối ưu ngưỡng trên một tập sẽ báo thành tích lạc quan giả.
8. **Chỉ nhìn trung bình, bỏ qua ca xấu và nhóm rủi ro.** Cần worst-slice và số ca cụ thể.
9. **Không khóa criterion/judge/dataset version.** A/B có thể đang đo bằng hai thước khác nhau.
10. **Gộp latency hoặc cost vào điểm chất lượng không rõ đơn vị.** Nên dùng release gates riêng.
11. **Dùng p95 của một request.** Phân vị cần tập mẫu và quy tắc tính tường minh.
12. **Không lưu reasonCode và trace.** Không phân biệt được lỗi ở retrieval, generation, tool hay judge.

## 12. Bài thực hành tự luyện

**Bối cảnh:** Một trợ lý Spring AI tư vấn chính sách bảo hành bằng RAG và dùng `lookupOrder` khi cần kiểm tra tình trạng đơn. Nhóm muốn phát hành prompt B thay cho A nhưng phải giữ được độ chính xác và thời gian phản hồi.

**Yêu cầu:**

1. Thiết kế ba rubric có điểm: `relevance` 0–4, `groundedness` 0–1, `citation_contract` 0/1. Xác định điểm chuẩn hóa, ngưỡng từng tiêu chí và một hard gate.
2. Định nghĩa `tool_permission` là hard gate, nhưng N/A khi ca không cần tool và runtime không có tool call.
3. Tạo ít nhất **12 case**: ca bình thường, không có nguồn, câu hỏi khó, nguồn giả, thiếu trích dẫn, phải gọi tool, gọi tool ngoài quyền, lỗi judge và thiếu retrieval capture.
4. Chọn ngưỡng từ tập dữ liệu có nhãn; thử ít nhất ba ngưỡng relevance và tính TP, FP, FN, TN, precision, recall.
5. Dùng `ThresholdAggregator` để tính kết quả của mỗi case, kiểm thử trường hợp N/A, ERROR và hard gate FAIL.
6. Tổng hợp theo dataset: pass rate từng tiêu chí, coverage, error count, các nhóm dữ liệu, p95 latency và chi phí.
7. Chạy A/B theo cùng thước đo, ghi lại ba ca hồi quy quan trọng nhất với `caseId`, `criterionVersion`, `reasonCode` và `traceId`.
8. Giải thích quyết định phát hành dựa trên hard gates, coverage, điểm từng chiều và SLA.

**Câu hỏi tự kiểm tra:**

- Tại sao điểm groundedness 0.90 có thể PASS trong ứng dụng này nhưng FAIL trong ứng dụng khác?
- Vì sao một `UNKNOWN_SOURCE` phải chặn phát hành khi citation là hard gate, ngay cả nếu relevance đạt 1.0?
- Nếu 90% ca PASS nhưng 10% evaluator ERROR, báo cáo cần nêu gì ngoài pass rate?
- Tại sao `unsupported_claim_rate` và relevance không nên cộng trực tiếp bằng cùng một công thức?
- Nếu đổi ngưỡng từ 0.8 lên 0.9, bạn cần làm gì để so sánh A và B công bằng?

## 13. Checklist triển khai

- [ ] Mỗi tiêu chí có tên, định nghĩa score, chiều cao/thấp tốt, ngưỡng và phiên bản rubric.
- [ ] Ngưỡng được hiệu chuẩn với dữ liệu có nhãn và kiểm tra lại trên tập holdout.
- [ ] Phân biệt ngưỡng từng case, ngưỡng tổng và ngưỡng phát hành toàn dataset.
- [ ] Chỉ chuyển đổi score giữa các thang khi có phép biến đổi rõ ràng.
- [ ] `NOT_APPLICABLE`, `ERROR` và trường hợp chưa chạy được biểu diễn minh bạch.
- [ ] Mọi hard gate được kiểm tra riêng; không bị điểm trung bình che khuất.
- [ ] Kết quả theo từng criterion có reasonCode, feedback, evidence và phiên bản.
- [ ] Báo cáo có pass rate, coverage, error rate và các nhóm dữ liệu rủi ro.
- [ ] SLA/chi phí được đo bằng đúng đơn vị, mẫu và thời gian; p95 là phân vị trên tập request.
- [ ] Kết quả A/B dùng cùng dataset, rubric và judge version hoặc đã chấm lại baseline.
- [ ] Có trace/case ID để truy nguyên khi quality gate FAIL hoặc chỉ số vận hành vượt ngưỡng.

## Tổng kết

Đặt ngưỡng là quyết định về **mức chất lượng và mức rủi ro mà ứng dụng chấp nhận**, không phải thao tác tùy ý trên một số do evaluator trả về. Với Spring AI, hãy hiểu semantics của từng `EvaluationResponse`, hiệu chuẩn từ dữ liệu có nhãn, xác định ngưỡng cho từng criterion rồi tổng hợp bằng policy rõ ràng: điều kiện bắt buộc, weighted score, N/A, ERROR và release gates. Báo cáo theo tiêu chí, nhóm dữ liệu và phiên bản cùng metrics/traces/chi phí/độ trễ sẽ giúp nhóm biết candidate thật sự cải thiện ở đâu và vì sao một bản phát hành cần được chặn.

## Tài liệu tham khảo

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): `Evaluator`, `EvaluationRequest`, `EvaluationResponse`, relevance và fact checking.
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): theo dõi model, ChatClient, advisor, vector store và tool.
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): hành vi công cụ, tham số và vòng đời thực thi.
- [Spring AI — EvaluationResponse API](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/evaluation/EvaluationResponse.html): dữ liệu pass, score, feedback, metadata.
- [Google — Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml): đánh giá metric, độ phức tạp và cải tiến hệ thống học máy.
- [scikit-learn — Precision/Recall](https://scikit-learn.org/stable/auto_examples/model_selection/plot_precision_recall.html): nguyên tắc precision/recall khi chọn ngưỡng.
- [Micrometer — Documentation](https://docs.micrometer.io/): metrics, histogram, percentile, traces và observation trong Java.
