# Tránh che lỗi một nhóm bằng điểm trung bình toàn bộ

> **Chương:** So sánh thí nghiệm
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm giữa các phiên bản prompt, model và pipeline.
>
> **Bối cảnh:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. Số liệu trong bài là ví dụ giả lập để học cách tổng hợp và diễn giải kết quả, không phải benchmark thực tế.

## 1. Vì sao điểm trung bình toàn bộ có thể đánh lừa?

Một evaluation report ghi:

> Candidate B đạt 88% PASS, cao hơn baseline A đạt 85%.

Product owner có thể hiểu rằng B tốt hơn trên toàn bộ nghiệp vụ. Nhưng con số đó có thể che các tình huống như:

- B tăng chất lượng ở nhóm câu hỏi FAQ dễ, nhưng giảm mạnh ở policy/hard.
- B xử lý đơn hàng tốt hơn, nhưng gọi sai tool ở nhóm có side effect.
- B có pass rate cao trên những case được chấm, nhưng nhiều case khó bị timeout nên không có verdict.
- B cải thiện nhóm chiếm số lượng lớn, trong khi một nhóm nhỏ nhưng có rủi ro cao bị suy giảm.
- Dataset của A có nhiều câu hỏi khó hơn B, khiến hai tỷ lệ tổng thể không còn so sánh công bằng.

Với hệ thống Spring AI, một con số tổng hợp không đủ để quyết định thay prompt, model, retriever hay tool pipeline. Cần biết **nhóm nào đóng góp vào điểm tổng, nhóm nào suy giảm, số case nào được chấm và lỗi có mức độ nghiêm trọng ra sao**.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao overall pass rate có thể che regression theo business group hoặc difficulty.
2. Phân biệt micro, macro và weighted aggregation.
3. Nhận diện Simpson's paradox và điều kiện để hiện tượng này xảy ra.
4. Chuẩn hóa kết quả A/B trên cùng cơ cấu nhóm.
5. Phát hiện bias do missing verdict, eligibility và sample composition.
6. Thiết kế slice guardrails để critical group không bị điểm nhóm khác bù trừ.
7. Phân biệt nhóm chính, tags chồng lấn và các lát cắt giao nhau.
8. Điều tra case-level regression bằng evidence, RAG snapshots, tool calls và traces.
9. Xây báo cáo Java và quality gate có per-slice decisions.
10. Viết kết luận phản ánh đúng phạm vi dữ liệu và độ bất định.

## 2. Một ví dụ: overall giảm dù candidate tốt hơn trong từng nhóm

Giả sử ta chia case thành hai nhóm theo độ khó: Easy và Hard.

| Arm | Easy PASS | Easy total | Easy rate | Hard PASS | Hard total | Hard rate | Overall |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 90 | 100 | 90% | 10 | 20 | 50% | **100/120 = 83,33%** |
| B | 19 | 20 | **95%** | 11 | 20 | **55%** | **30/40 = 75%** |

Trong từng nhóm:

- Easy: B tăng từ 90% lên 95% (**+5 điểm phần trăm**).
- Hard: B tăng từ 50% lên 55% (**+5 điểm phần trăm**).

Nhưng overall:

- A có 100/120 = 83,33%.
- B có 30/40 = 75%.

**B tốt hơn trong cả hai nhóm nhưng overall thấp hơn**, vì A có 100 case Easy và B chỉ có 20; cơ cấu mẫu hai arm khác nhau rất nhiều. Đây là một ví dụ của **Simpson's paradox**.

Điều này không có nghĩa phép tính overall sai. Nó có nghĩa hai tỷ lệ overall đang phản ánh **hai hỗn hợp nhóm khác nhau**. Nếu dùng chúng để kết luận model nào tốt hơn trên cùng population, ta đã bỏ qua cơ cấu mẫu.

### Điểm cần nhớ

- Overall micro rate trả lời: “Trong tập verdict thực tế của arm này, tỷ lệ PASS là bao nhiêu?”
- Nó không tự trả lời: “Nếu hai arm cùng chạy trên một population có cơ cấu nhóm như nhau, arm nào tốt hơn?”
- Muốn trả lời câu thứ hai, cần so cùng case IDs hoặc chuẩn hóa theo một bộ weights chung đã đăng ký trước.

## 3. Khi nào Simpson's paradox có thể xuất hiện trong A/B?

Một điều kiện thường gặp là **tỷ trọng các nhóm khác nhau giữa A và B**. Một số nguyên nhân:

1. Hai arm chạy trên hai sample sets khác nhau.
2. Traffic được phân bổ không ngẫu nhiên hoặc thay đổi theo thời gian.
3. Một arm bị missing verdict nhiều hơn ở nhóm khó.
4. Eligibility filter khác nhau giữa các run.
5. Sampling plan oversample nhóm khác nhau nhưng report vẫn dùng raw micro average.
6. Data collection diễn ra ở hai giai đoạn có cơ cấu user intents khác nhau.

### Trường hợp dataset giống nhau

Nếu A và B chạy trên **cùng case IDs**, cùng eligibility, có verdict hợp lệ đầy đủ và dùng cùng group labels/weights, cơ cấu nhóm không tự thay đổi giữa hai arm. Khi đó Simpson's paradox do thay đổi composition **không thể** là lời giải thích cho đảo chiều overall trên cùng bộ case đầy đủ.

Nếu report vẫn cho thấy composition khác, hãy kiểm tra:

- A/B có thực sự dùng cùng case IDs?
- Có duplicate hoặc missing rows?
- Eligibility có thay đổi?
- Một số case bị đánh dấu NOT_APPLICABLE ở một arm?
- Có tính retry như case mới?
- Group assignment có bị thay đổi sau khi chạy?
- Mẫu số đang dùng PASS+FAIL hay toàn bộ eligible?

**Missingness có thể tạo ra complete-case bias** dù dataset ban đầu giống nhau. Ví dụ candidate B không có verdict ở nhiều case hard; pass rate chỉ trên case còn lại có thể tăng giả tạo.

## 4. Ba cách tổng hợp: micro, macro và weighted

Giả sử có \(G\) business groups. Với nhóm \(g\):

- \(P_g\): số case PASS;
- \(N_g\): số verdict hợp lệ (PASS + FAIL);
- \(r_g=P_g/N_g\): pass rate của nhóm.

### 4.1. Micro average

\[
R_{\mathrm{micro}}=
\frac{\sum_{g=1}^{G}P_g}
{\sum_{g=1}^{G}N_g}.
\]

Mỗi verdict hợp lệ có trọng số như nhau. Nhóm có nhiều case hơn đóng góp nhiều hơn vào overall.

**Dùng khi:** muốn mô tả tỷ lệ PASS trên tất cả verdict của tập thực tế, hoặc cơ cấu sample đã đại diện đúng population mục tiêu.

**Rủi ro:** một nhóm lớn có thể che một nhóm nhỏ nhưng quan trọng.

### 4.2. Macro average

\[
R_{\mathrm{macro}}=
\frac{1}{G}\sum_{g=1}^{G}r_g.
\]

Mỗi group có trọng số bằng nhau, bất kể group có 10 hay 10.000 case.

**Dùng khi:** muốn xem hiệu suất trung bình trên các nhóm nghiệp vụ, không để nhóm lớn lấn át nhóm nhỏ.

**Rủi ro:** một nhóm chỉ có vài case có thể ảnh hưởng ngang với nhóm có hàng trăm case; macro không tự xử lý small-N uncertainty.

### 4.3. Weighted average

\[
R_{\mathrm{weighted}}=
\sum_{g=1}^{G}w_g r_g,\qquad
\sum_{g=1}^{G}w_g=1.
\]

Weights được chọn theo mục tiêu:

- tỷ trọng traffic production;
- tỷ trọng population trong sampling frame;
- risk priority được domain owner phê duyệt;
- một phân phối chuẩn hóa cố định để so sánh model versions.

**Dùng khi:** cần ước lượng chất lượng trên một cơ cấu population cụ thể hoặc so sánh các arm đã oversample khác nhau.

**Rủi ro:** weights chọn tùy tiện hoặc thay đổi sau khi xem kết quả sẽ làm report mất tính khách quan.

### So sánh nhanh

| Cách tính | Trọng số | Trả lời câu hỏi |
|---|---|---|
| Micro | Mỗi verdict | Tập verdict thực tế đạt bao nhiêu? |
| Macro | Mỗi group bằng nhau | Trung bình các nhóm đạt bao nhiêu? |
| Weighted | Theo weights cố định | Trên population mục tiêu đã định, đạt bao nhiêu? |

Không có một cách tính đúng cho mọi mục đích. Hãy đăng ký **primary aggregation** trước khi chạy và báo thêm các cách còn lại khi chúng giúp giải thích kết quả.

## 5. Chuẩn hóa A/B bằng một bộ weights cố định

Quay lại ví dụ Easy/Hard:

| Group | A rate | B rate | Weight mục tiêu |
|---|---:|---:|---:|
| Easy | 90% | 95% | 80% |
| Hard | 50% | 55% | 20% |

Nếu population mục tiêu được định nghĩa trước là 80% Easy và 20% Hard:

\[
R_A=0,8(0,90)+0,2(0,50)=0,82.
\]

\[
R_B=0,8(0,95)+0,2(0,55)=0,87.
\]

Trên cùng weights:

- A standardized rate = **82%**.
- B standardized rate = **87%**.
- Delta = **+5 điểm phần trăm**.

Kết quả này cho thấy B tốt hơn khi cả hai arm được đặt trên cùng cơ cấu population đã chọn. Nó không thay thế bảng raw counts, coverage hay per-slice analysis.

### Chọn weights như thế nào?

Weights cần có nguồn và revision:

| Nguồn weight | Khi nào dùng |
|---|---|
| Production traffic mix | Ước lượng trải nghiệm trung bình theo traffic hiện tại |
| Target launch mix | Ước lượng population dự kiến sau rollout |
| Sampling frame probabilities | Chuẩn hóa dữ liệu stratified/oversampled |
| Risk weights | Đánh giá ưu tiên quản trị rủi ro, cần gọi rõ là risk-weighted score |

Không trộn risk weights với traffic weights rồi gọi kết quả là user-facing accuracy. Nếu dùng weights theo mức độ nghiêm trọng, đặt tên metric là **risk-weighted score** và vẫn giữ critical veto riêng.

### Độ nhạy với weights

Nếu kết luận thay đổi mạnh khi weights đổi từ 80/20 sang 70/30, hãy báo sensitivity analysis. Một quyết định vững nên hiểu được ở nhiều cơ cấu hợp lý, đặc biệt khi traffic mix tương lai chưa chắc chắn.

## 6. Ví dụ thứ hai: overall tăng nhưng một business group giảm

Giả sử dataset A/B có cùng 200 case eligible và được chấm đầy đủ:

| Business group | A PASS / N | A rate | B PASS / N | B rate | Delta |
|---|---:|---:|---:|---:|---:|
| Policy | 72/80 | 90% | 64/80 | **80%** | **−10 pp** |
| Orders | 45/60 | 75% | 51/60 | 85% | +10 pp |
| Tech support | 36/60 | 60% | 48/60 | 80% | +20 pp |
| **Overall** | **153/200** | **76,5%** | **163/200** | **81,5%** | **+5 pp** |

Candidate B tăng overall 5 pp. Tuy nhiên, policy giảm 10 pp. Nếu policy chứa các câu hỏi về quyền lợi, điều kiện và thời hạn có hậu quả lớn, mức giảm này có thể không chấp nhận được.

### Vì sao macro cũng không đủ?

Macro A:

\[
(90\%+75\%+60\%)/3=75\%.
\]

Macro B:

\[
(80\%+85\%+80\%)/3\approx81,67\%.
\]

Macro cũng tăng. Nhưng nó vẫn cho phép hai nhóm tăng bù cho policy giảm. **Cả micro lẫn macro đều có thể che một regression cần được giữ thành guardrail riêng.**

Vì vậy, report nên có:

- overall metrics để theo dõi xu hướng chung;
- per-slice metrics để thấy nhóm nào tăng/giảm;
- critical-slice guardrails để đặt giới hạn không được bù trừ;
- case-level drilldown để hiểu nguyên nhân.

## 7. Không để điểm của nhóm khác bù cho lỗi nghiêm trọng

Một số lỗi cần **hard veto**, không được bù bằng điểm trung bình:

- bịa điều kiện pháp lý/chính sách quan trọng;
- tiết lộ dữ liệu ngoài quyền;
- gọi tool có side effect sai đối tượng;
- báo đã thanh toán/đã giao khi tool trả trạng thái ngược lại;
- hướng dẫn thao tác nguy hiểm hoặc phá hủy dữ liệu;
- làm theo prompt injection trong tài liệu và vượt policy.

### Severity và aggregate score là hai trục

| Chỉ số | Vai trò |
|---|---|
| Overall pass rate | Mức đạt chung |
| Per-group pass rate | Mức đạt theo nghiệp vụ |
| Score distribution | Phân bố mức chất lượng |
| Critical case count | Số tình huống có ít nhất một critical failure |
| Critical incident count | Tổng số incidents nghiêm trọng |
| Critical-slice gate | Điều kiện riêng cho nhóm rủi ro cao |

Một case có nhiều critical incidents vẫn chỉ là **một unique critical case** trong critical case rate; incident count được báo riêng. Không để weighted score hoặc macro average thay thế veto.

### Ví dụ quality gate

~~~yaml
quality_gate:
  revision: "business-slice-v2"
  overall:
    minimum_pass_rate: 0.80
    minimum_coverage: 0.98
    maximum_evaluation_error_rate: 0.01
  slice_rules:
    - group: policy
      minimum_pass_rate: 0.88
      maximum_allowed_regression_pp: 2.0
      minimum_evaluated_cases: 50
      critical_failure_max_unique_cases: 0
      on_insufficient_sample: "INCONCLUSIVE"
    - group: orders
      minimum_pass_rate: 0.78
      maximum_allowed_regression_pp: 3.0
      minimum_evaluated_cases: 40
    - group: tech_support
      minimum_pass_rate: 0.65
      maximum_allowed_regression_pp: 5.0
      minimum_evaluated_cases: 40
  decision:
    critical_failure_veto: true
    insufficient_coverage: "BLOCKED"
~~~

Đây là policy minh họa do project định nghĩa, không phải cấu hình built-in của Spring AI. Threshold cần được domain owner phê duyệt và khóa trước khi xem kết quả.

## 8. Slice guardrails: điều kiện cho từng nhóm

Một guardrail tốt có đủ các phần:

1. **Slice definition:** business group, difficulty, scenario, risk tier.
2. **Metric:** fact checking, relevance, tool correctness, abstention...
3. **Eligibility:** case nào áp dụng metric.
4. **Minimum coverage:** bao nhiêu case phải có verdict.
5. **Minimum sample:** bao nhiêu case cần có để quyết định tự động.
6. **Regression tolerance:** mức giảm tối đa cho phép.
7. **Critical rule:** lỗi nào veto release.
8. **Action:** PROMOTE, REJECT, BLOCKED hoặc INCONCLUSIVE.

### Guardrail không phải một con số duy nhất

Ví dụ policy/hard có 8 case và 100% PASS. Đây là kết quả mô tả hữu ích, nhưng không đủ để tự động kết luận nhóm policy/hard an toàn. Gate có thể yêu cầu tối thiểu 30 hoặc 50 case, coverage đầy đủ và human review.

Ngưỡng minimum sample là policy theo rủi ro, không phải chuẩn thống kê chung. Cần kết hợp confidence interval/power với khả năng chấp nhận rủi ro.

### Guardrail theo delta

Một nhóm có thể đã có baseline thấp. Chỉ đặt minimum pass rate tuyệt đối có thể không phát hiện regression mới; chỉ đặt delta cũng có thể chấp nhận chất lượng vốn đã quá thấp. Dùng cả hai:

- minimum pass rate;
- maximum allowed regression;
- critical veto;
- minimum coverage/sample.

## 9. Coverage và missingness có thể làm overall đẹp giả

Giả sử cùng 100 case eligible, gồm 60 Easy và 40 Hard:

| Arm | Easy evaluated / PASS | Hard evaluated / PASS | Tổng evaluated | Pass rate |
|---|---:|---:|---:|---:|
| A | 60 / 54 | 40 / 24 | 100 | 78/100 = 78% |
| B | 60 / 57 | 20 / 19 | 80 | 76/80 = 95% |

Nếu chỉ nhìn pass rate trên verdict hợp lệ, B đạt 95% và có vẻ vượt xa A. Nhưng B không có verdict ở **20/40 case Hard**. Coverage:
- A = 100/100 = 100%.
- B = 80/100 = 80%.
- Hard coverage của B = 20/40 = 50%.

Không thể kết luận B có chất lượng 95% trên cùng population. Có thể B bỏ sót đúng những case khó do context overflow, provider timeout hoặc tool failure.

### Báo missingness theo từng nhóm

| Slice | Eligible | Evaluated | Coverage | PASS | Pass rate |
|---|---:|---:|---:|---:|---:|
| Easy | 60 | 60 | 100% | 57 | 95% |
| Hard | 40 | 20 | **50%** | 19 | 95% |

Đây là tín hiệu **measurement gate BLOCKED** nếu policy yêu cầu coverage 98%. Evaluation error/generation error không tự chuyển thành quality FAIL, nhưng chúng phải ảnh hưởng quyết định về độ đầy đủ của phép đo.

## 10. Mẫu số phải nhất quán theo metric

Một case có thể đủ điều kiện cho relevance nhưng không áp dụng retrieval recall hoặc tool correctness. Không được lấy chung một denominator cho tất cả metrics.

| Metric | Eligible cases |
|---|---|
| Relevance | Case có question và answer cần đánh giá |
| Fact checking | Case có evidence/claims đủ để kiểm chứng theo rubric |
| Retrieval recall@k | Case có ground-truth relevant document IDs |
| Tool correctness | Case có expected tool behavior |
| Abstention correctness | Case mà policy yêu cầu từ chối hoặc nêu thiếu dữ kiện |
| Latency | Requests/attempts theo định nghĩa đo đã chọn |
| Cost | Calls/cases có usage và rate card hợp lệ |

Trong mỗi slice cần báo eligible, evaluated, PASS, FAIL, errors, skipped, coverage. Nếu hai arm có eligibility khác nhau, cần điều tra trước khi so sánh.

### Không nhập chung error với fail

- GENERATION_ERROR: không có answer để chấm.
- EVALUATION_ERROR: judge không đưa được verdict.
- TOOL_ERROR: tool không hoạt động hoặc trả lỗi.
- SKIPPED: case không được chạy theo policy.
- NOT_APPLICABLE: metric không áp dụng.
- PASS/FAIL: chỉ khi có verdict hợp lệ.

Một operational gate có thể chặn candidate vì error rate cao dù quality pass rate của các case còn lại vẫn tốt.

## 11. Primary groups, tags và slice intersections

### Primary business group nên loại trừ lẫn nhau

Một case nên có đúng một primary business group để tính micro/macro không double-count:

~~~json
{
  "caseId": "pol-014",
  "primaryBusinessGroup": "policy",
  "difficulty": "hard",
  "scenario": "rag_tool",
  "riskTier": "high",
  "tags": ["deadline", "exception", "requires-citation"]
}
~~~

Tags có thể chồng lấn. Một case có thể vừa deadline, vừa exception, vừa requires-citation; không cộng số lượng các tags thành tổng case count.

### Intersections có giá trị nhưng sample nhỏ

Một report có thể phân tích:
- business group × difficulty;
- business group × scenario;
- risk tier × tool usage;
- difficulty × evidence ambiguity.

Tuy nhiên, 3 groups × 3 difficulties × 4 scenarios đã tạo 36 ô. Nhiều ô sẽ có sample nhỏ. Cần:
- chọn primary slices trước;
- chỉ công bố inference khi đủ sample;
- gắn SMALL_N;
- dùng exploratory label cho các lát cắt phát hiện sau khi xem data;
- tránh kiểm định hàng chục slices rồi chỉ báo ô có kết quả thuận lợi.

### Hierarchical rollup

Nếu có taxonomy cha/con (Policy → HR Policy, Finance Policy), không cộng đồng thời parent và child vào cùng một overall. Parent là rollup của child; phải xác định cấp nào là đơn vị tính chính.

## 12. Traffic mix drift và standardized reporting

Một hệ thống production có thể thay đổi traffic mix theo thời gian:
- đầu tháng nhiều câu hỏi payroll;
- cuối tháng nhiều câu hỏi deadline;
- sau release có nhiều câu hỏi về feature mới.

Overall pass rate thay đổi có thể do:
1. chất lượng model thay đổi;
2. tỷ trọng câu hỏi thay đổi;
3. cả hai cùng thay đổi.

### Báo raw và standardized

Mỗi phiên bản report nên có:
- raw micro rate theo sample/traffic thực tế;
- macro rate theo group;
- standardized rate trên weights cố định;
- group distribution/traffic share;
- per-slice coverage và uncertainty.

### Ví dụ

| Week | Policy share | Orders share | Policy rate | Orders rate | Raw overall |
|---|---:|---:|---:|---:|---:|
| W1 | 80% | 20% | 90% | 70% | 86% |
| W2 | 40% | 60% | 92% | 75% | 81,8% |

Từng nhóm đều cải thiện, nhưng raw overall giảm do traffic chuyển sang nhóm Orders có pass rate thấp hơn. Nếu standardized với weights cố định 80/20:
- W1 = 86%.
- W2 = 88,6%.

Hai chỉ số mô tả hai khía cạnh khác nhau:
- raw overall phản ánh trải nghiệm theo traffic thực tế của tuần đó;
- standardized rate phản ánh thay đổi chất lượng trên cơ cấu cố định.

Không bỏ raw traffic metric khi làm standardized report; người vận hành vẫn cần biết trải nghiệm thật trong tuần.

## 13. Không lấy worst slice làm kết luận duy nhất

Per-slice guardrail rất quan trọng, nhưng nếu chỉ nhìn slice tệ nhất:
- một ô n=2 có thể tạo 0% hoặc 100%;
- nhiều slices tạo ra khả năng phát hiện ngẫu nhiên;
- group label có thể chưa ổn định;
- một lỗi judge đơn lẻ có thể làm metric thay đổi mạnh.

Hãy phân biệt:
- **descriptive:** báo mọi slice có count và denominator;
- **diagnostic:** điều tra case failures, kể cả khi N nhỏ;
- **decision-grade:** cần minimum sample, coverage, uncertainty, pre-registered guardrails và review.

Một regression ở nhóm nhỏ vẫn cần điều tra nếu có critical incident. Nhưng đừng diễn giải tỷ lệ 0/2 thành bằng chứng rằng toàn bộ nhóm chắc chắn thất bại.

## 14. Java 21: tính micro, macro và standardized rate theo slice

Ví dụ sau là một aggregator thuần Java. Nó nhận số liệu đã được tổng hợp theo **primary business group** và tính ba cách tổng hợp. Nó cũng kiểm tra per-slice guardrails.

Lớp này không tự đọc dataset, không chạy model và không tự quyết định eligibility. Runner phải xác thực case IDs, labels, metric eligibility và attempt policy trước khi đưa số liệu vào.

### File `SliceAggregation.java`

~~~java
package com.example.aiquality.reporting;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.Set;

public final class SliceAggregation {
    private SliceAggregation() {}

    public enum Decision {
        PROMOTE, REJECT, BLOCKED, INCONCLUSIVE
    }

    public record SliceStats(
            String slice,
            int eligible,
            int evaluated,
            int passed,
            int criticalCases) {

        public SliceStats {
            if (slice == null || slice.isBlank()
                    || eligible < 0
                    || evaluated < 0 || evaluated > eligible
                    || passed < 0 || passed > evaluated
                    || criticalCases < 0 || criticalCases > evaluated) {
                throw new IllegalArgumentException("SliceStats không hợp lệ");
            }
        }

        public OptionalDouble passRate() {
            return ratio(passed, evaluated);
        }

        public OptionalDouble coverage() {
            return ratio(evaluated, eligible);
        }
    }

    public record Aggregate(
            int eligible,
            int evaluated,
            int passed,
            int criticalCases,
            OptionalDouble microRate,
            OptionalDouble macroRate,
            OptionalDouble standardizedRate,
            OptionalDouble coverage,
            Map<String, OptionalDouble> sliceRates) {}

    public record GatePolicy(
            double minimumOverallPassRate,
            double minimumCoverage,
            int minimumEvaluatedPerSlice,
            double maximumSliceRegressionPp,
            Set<String> criticalSlices,
            double minimumCriticalSlicePassRate,
            boolean vetoAnyCriticalCase) {

        public GatePolicy {
            if (!unit(minimumOverallPassRate)
                    || !unit(minimumCoverage)
                    || minimumEvaluatedPerSlice < 1
                    || !Double.isFinite(maximumSliceRegressionPp)
                    || maximumSliceRegressionPp < 0
                    || criticalSlices == null
                    || !unit(minimumCriticalSlicePassRate)) {
                throw new IllegalArgumentException("GatePolicy không hợp lệ");
            }
            criticalSlices = Set.copyOf(criticalSlices);
        }
    }

    public record GateResult(
            Decision decision,
            List<String> reasons,
            Aggregate baseline,
            Aggregate candidate,
            Map<String, Double> sliceDeltasPp) {}

    public static Aggregate aggregate(
            List<SliceStats> rows,
            Map<String, Double> fixedWeights) {

        Map<String, SliceStats> bySlice = index(rows);
        validateWeights(bySlice.keySet(), fixedWeights);

        int eligible = 0, evaluated = 0, passed = 0, critical = 0;
        double macroSum = 0.0;
        int groupsWithVerdict = 0;
        double weightedSum = 0.0;
        boolean allWeightedGroupsHaveVerdict = true;
        Map<String, OptionalDouble> rates = new LinkedHashMap<>();

        for (SliceStats row : bySlice.values()) {
            eligible += row.eligible();
            evaluated += row.evaluated();
            passed += row.passed();
            critical += row.criticalCases();

            OptionalDouble rate = row.passRate();
            rates.put(row.slice(), rate);
            if (rate.isPresent()) {
                macroSum += rate.getAsDouble();
                groupsWithVerdict++;
                weightedSum += fixedWeights.get(row.slice())
                        * rate.getAsDouble();
            } else if (fixedWeights.get(row.slice()) > 0.0) {
                allWeightedGroupsHaveVerdict = false;
            }
        }

        OptionalDouble micro = ratio(passed, evaluated);
        OptionalDouble macro = groupsWithVerdict == 0
                ? OptionalDouble.empty()
                : OptionalDouble.of(macroSum / groupsWithVerdict);
        OptionalDouble standardized =
                allWeightedGroupsHaveVerdict && !bySlice.isEmpty()
                ? OptionalDouble.of(weightedSum)
                : OptionalDouble.empty();

        return new Aggregate(
            eligible, evaluated, passed, critical,
            micro, macro, standardized, ratio(evaluated, eligible),
            Map.copyOf(rates));
    }

    public static GateResult compare(
            List<SliceStats> baselineRows,
            List<SliceStats> candidateRows,
            Map<String, Double> fixedWeights,
            GatePolicy policy) {

        Map<String, SliceStats> baseline = index(baselineRows);
        Map<String, SliceStats> candidate = index(candidateRows);

        if (!baseline.keySet().equals(candidate.keySet())) {
            throw new IllegalArgumentException(
                "A/B phải có cùng primary slice keys");
        }

        for (String key : baseline.keySet()) {
            if (baseline.get(key).eligible() != candidate.get(key).eligible()) {
                throw new IllegalArgumentException(
                    "Eligible denominator khác nhau ở slice " + key);
            }
        }

        Aggregate a = aggregate(baselineRows, fixedWeights);
        Aggregate b = aggregate(candidateRows, fixedWeights);
        List<String> reasons = new ArrayList<>();
        Map<String, Double> deltas = new LinkedHashMap<>();

        for (String key : baseline.keySet()) {
            OptionalDouble aRate = a.sliceRates().get(key);
            OptionalDouble bRate = b.sliceRates().get(key);
            if (aRate.isPresent() && bRate.isPresent()) {
                deltas.put(key,
                    100.0 * (bRate.getAsDouble() - aRate.getAsDouble()));
            }
        }

        // Safety veto có ưu tiên cao nhất.
        if (policy.vetoAnyCriticalCase() && b.criticalCases() > 0) {
            reasons.add("Candidate có critical failure: "
                    + b.criticalCases() + " unique cases");
            return result(Decision.REJECT, reasons, a, b, deltas);
        }

        if (b.coverage().isEmpty()
                || b.coverage().getAsDouble() < policy.minimumCoverage()) {
            reasons.add("Overall evaluation coverage dưới ngưỡng");
            return result(Decision.BLOCKED, reasons, a, b, deltas);
        }

        for (String key : baseline.keySet()) {
            SliceStats aRow = baseline.get(key);
            SliceStats bRow = candidate.get(key);
            if (aRow.evaluated() < policy.minimumEvaluatedPerSlice()
                    || bRow.evaluated() < policy.minimumEvaluatedPerSlice()) {
                reasons.add("Insufficient sample ở slice " + key);
            }
        }
        if (!reasons.isEmpty()) {
            return result(Decision.INCONCLUSIVE, reasons, a, b, deltas);
        }

        if (b.microRate().isEmpty()
                || b.microRate().getAsDouble()
                    < policy.minimumOverallPassRate()) {
            reasons.add("Overall micro pass rate dưới ngưỡng");
        }

        for (String key : baseline.keySet()) {
            double delta = deltas.get(key);
            if (delta < -policy.maximumSliceRegressionPp()) {
                reasons.add("Regression vượt ngưỡng ở slice " + key
                        + ": " + delta + " pp");
            }
            if (policy.criticalSlices().contains(key)) {
                double rate = b.sliceRates().get(key).orElse(-1.0);
                if (rate < policy.minimumCriticalSlicePassRate()) {
                    reasons.add("Critical slice dưới pass-rate floor: " + key);
                }
            }
        }

        return result(reasons.isEmpty() ? Decision.PROMOTE : Decision.REJECT,
                reasons, a, b, deltas);
    }

    private static GateResult result(
            Decision decision,
            List<String> reasons,
            Aggregate baseline,
            Aggregate candidate,
            Map<String, Double> deltas) {
        return new GateResult(decision, List.copyOf(reasons),
                baseline, candidate, Map.copyOf(deltas));
    }

    private static Map<String, SliceStats> index(List<SliceStats> rows) {
        if (rows == null || rows.isEmpty()) {
            throw new IllegalArgumentException("Không có slice rows");
        }
        Map<String, SliceStats> result = new LinkedHashMap<>();
        for (SliceStats row : rows) {
            if (row == null || result.putIfAbsent(row.slice(), row) != null) {
                throw new IllegalArgumentException("Slice null hoặc duplicate");
            }
        }
        return result;
    }

    private static void validateWeights(
            Set<String> sliceKeys,
            Map<String, Double> weights) {
        if (weights == null || !weights.keySet().equals(sliceKeys)) {
            throw new IllegalArgumentException(
                "Weights phải khớp chính xác primary slice keys");
        }
        double sum = 0.0;
        for (double weight : weights.values()) {
            if (!Double.isFinite(weight) || weight < 0.0) {
                throw new IllegalArgumentException("Weight không hợp lệ");
            }
            sum += weight;
        }
        if (Math.abs(sum - 1.0) > 1.0e-9) {
            throw new IllegalArgumentException("Tổng weights phải bằng 1");
        }
    }

    private static boolean unit(double value) {
        return Double.isFinite(value) && value >= 0.0 && value <= 1.0;
    }

    private static OptionalDouble ratio(int numerator, int denominator) {
        return denominator == 0 ? OptionalDouble.empty()
                : OptionalDouble.of(numerator / (double) denominator);
    }
}
~~~

### Các quy tắc trong helper

- Micro dùng tổng PASS chia tổng verdict hợp lệ.
- Macro lấy trung bình các slice có verdict; slice không có verdict vẫn phải được phản ánh qua coverage.
- Standardized rate dùng fixed weights. Nếu một slice có weight dương nhưng không có verdict, standardized rate trả empty thay vì tự coi nhóm đó đạt 0% hoặc 100%.
- Hàm compare yêu cầu A/B có cùng primary slice keys và cùng eligible count theo từng slice.
- Gate có critical veto, coverage gate, minimum sample, overall floor, slice regression limit và critical-slice floor.
- Hàm chỉ so sánh **aggregate rates**. Nó không tính McNemar hoặc paired confidence interval; muốn làm inference paired phải đưa case-level paired results vào phân tích riêng.
- Unique critical count chỉ đúng nếu mỗi case thuộc đúng một primary group. Với multi-label tags, phải deduplicate theo case ID trước khi tổng hợp.

## 15. JUnit 5: kiểm tra Simpson's paradox và slice veto

### File `SliceAggregationTest.java`

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;

import com.example.aiquality.reporting.SliceAggregation;
import com.example.aiquality.reporting.SliceAggregation.*;

class SliceAggregationTest {

    private static SliceStats row(
            String slice, int eligible, int evaluated,
            int passed, int critical) {
        return new SliceStats(slice, eligible, evaluated, passed, critical);
    }

    @Test
    void standardizedRateExplainsSimpsonsParadox() {
        var weights = Map.of("easy", 0.80, "hard", 0.20);

        var a = SliceAggregation.aggregate(List.of(
            row("easy", 100, 100, 90, 0),
            row("hard", 20, 20, 10, 0)), weights);

        var b = SliceAggregation.aggregate(List.of(
            row("easy", 20, 20, 19, 0),
            row("hard", 20, 20, 11, 0)), weights);

        assertEquals(100.0 / 120.0,
                a.microRate().orElseThrow(), 0.000001);
        assertEquals(30.0 / 40.0,
                b.microRate().orElseThrow(), 0.000001);

        assertEquals(0.82,
                a.standardizedRate().orElseThrow(), 0.000001);
        assertEquals(0.87,
                b.standardizedRate().orElseThrow(), 0.000001);

        assertEquals(0.05,
                b.sliceRates().get("easy").orElseThrow()
                - a.sliceRates().get("easy").orElseThrow(), 0.000001);
        assertEquals(0.05,
                b.sliceRates().get("hard").orElseThrow()
                - a.sliceRates().get("hard").orElseThrow(), 0.000001);
    }

    @Test
    void criticalFailureVetoesOtherwiseImprovedCandidate() {
        var a = List.of(
            row("policy", 100, 100, 90, 0),
            row("orders", 100, 100, 70, 0));
        var b = List.of(
            row("policy", 100, 100, 95, 1),
            row("orders", 100, 100, 90, 0));

        var policy = new GatePolicy(
            0.80, 0.98, 30, 5.0,
            Set.of("policy"), 0.88, true);

        var result = SliceAggregation.compare(
            a, b, Map.of("policy", 0.5, "orders", 0.5), policy);

        assertEquals(Decision.REJECT, result.decision());
        assertTrue(result.reasons().stream()
                .anyMatch(reason -> reason.contains("critical failure")));
    }

    @Test
    void insufficientCoverageBlocksDecision() {
        var a = List.of(
            row("easy", 60, 60, 54, 0),
            row("hard", 40, 40, 24, 0));
        var b = List.of(
            row("easy", 60, 60, 57, 0),
            row("hard", 40, 20, 19, 0));

        var policy = new GatePolicy(
            0.80, 0.98, 10, 5.0,
            Set.of("hard"), 0.70, true);

        var result = SliceAggregation.compare(
            a, b, Map.of("easy", 0.6, "hard", 0.4), policy);

        assertEquals(Decision.BLOCKED, result.decision());
    }

    @Test
    void rejectsDifferentEligibleDenominators() {
        assertThrows(IllegalArgumentException.class, () ->
            SliceAggregation.compare(
                List.of(row("policy", 100, 100, 90, 0)),
                List.of(row("policy", 90, 90, 85, 0)),
                Map.of("policy", 1.0),
                new GatePolicy(0.8, 0.98, 10, 5.0,
                    Set.of("policy"), 0.8, true)));
    }
}
~~~

Đây là **code hướng dẫn**, chưa được compile hoặc chạy trong phạm vi viết bài. Khi triển khai thật, cần bổ sung test cho zero-evaluated slice, missing primary group, duplicate case IDs, multiple metric eligibility và serialization. Đặc biệt, caller phải xác minh hai arms thực sự dùng cùng case IDs; cùng eligible counts không chứng minh hai tập ID giống nhau.

## 16. Drilldown từ aggregate xuống case

Khi một slice fail guardrail, quy trình điều tra nên đi theo các cấp:

~~~text
Overall dashboard
  -> Business group / difficulty slice
      -> Metric (fact check, relevance, tool correctness)
          -> Case IDs có regression
              -> Execution snapshots
                  -> Retrieval evidence / tool outputs
                      -> Model spans / judge spans / logs
~~~

### Bước 1: xác định nhóm bị che

Bắt đầu từ bảng per-slice:
- nhóm nào có delta âm;
- nhóm nào có coverage thấp;
- nhóm nào có critical cases;
- nhóm nào có sample nhỏ;
- nhóm nào có score distribution dịch về phía điểm thấp.

### Bước 2: lấy danh sách case

Với paired A/B, tạo các tập:
- both pass;
- A-only pass;
- B-only pass;
- both fail.

Ưu tiên review A-only trong slice suy giảm, sau đó kiểm tra B-only để hiểu candidate đang sửa những lỗi nào.

### Bước 3: đối chiếu metadata và evidence

Mỗi case nên có:
- case ID và primary business group;
- difficulty/risk/scenario;
- dataset/label revision;
- prompt/model/judge revisions;
- corpus/index/retrieval settings;
- context snapshot hoặc evidence reference;
- tool call/arguments/results nếu có;
- answer snapshot và evaluator verdict;
- trace reference, latency, token usage và cost.

### Bước 4: phân biệt nguyên nhân

| Bằng chứng | Nơi cần điều tra |
|---|---|
| Relevant document không được retrieve | Index, filters, embeddings, top-k, reranker |
| Document có trong retrieval nhưng mất sau truncation | Context assembly/token budget |
| Context giống nhau, answer thay đổi | Generator model, prompt, decoding options |
| Answer giống nhau, verdict đổi | Judge prompt/model/rubric/parser |
| Tool arguments sai | Tool selection/schema/argument mapping |
| Tool output đúng, answer nói ngược | Tool-result grounding |
| Verdict thiếu ở case hard | Provider timeout, quota, retry, judge capacity |

## 17. Áp dụng cho RAG và tool calling

### RAG: không gộp relevance và fact checking

Một nhóm policy có thể:
- relevance tăng vì answer tập trung đúng câu hỏi;
- fact checking giảm vì answer đưa sai ngày/điều kiện;
- retrieval recall giảm vì tài liệu mới không được index.

Nếu chỉ báo composite pass rate, không thấy được tầng nào gây lỗi.

Báo riêng:
- retrieval recall@k/hit@k trên case có ground truth document IDs;
- context sufficiency sau rerank/truncation;
- answer relevance;
- factuality/groundedness;
- citation correctness;
- abstention correctness khi thiếu evidence.

### Tool calling: đếm lỗi theo workflow

Với nhóm orders:
- đúng tool nhưng sai order ID có thể là major/critical;
- tool timeout là operational error;
- tool trả IN_TRANSIT nhưng assistant nói DELIVERED là content/tool-result failure;
- gọi tool có side effect khi user chỉ yêu cầu tra cứu là policy violation.

Một group có thể có pass rate cao nhưng một workflow critical fail. Gate cần kiểm unique critical cases và tool assertions, không để nhóm FAQ bù.

### No-context và abstention

Không ép mọi case phải có fact-check verdict. Với case thiếu evidence:
- chấm assistant có nhận biết thiếu dữ kiện không;
- có abstain đúng policy không;
- có bịa thông tin để lấp chỗ trống không.

Tỷ lệ abstention đúng phải có eligible denominator riêng.

## 18. Metrics, traces, latency và cost theo slice

Spring AI dùng Micrometer Observation/Tracing để quan sát các thành phần khi chúng được thực thi. Có thể kết hợp các observation logic như:

| Tín hiệu | Cách dùng |
|---|---|
| `spring.ai.chat.client` | Duration của ChatClient/advisor chain |
| `spring.ai.advisor` | Tầng advisor/retrieval processing |
| `gen_ai.client.operation` | ChatModel/EmbeddingModel calls |
| `gen_ai.client.token.usage` | Input/output token usage nếu provider trả |
| `db.vector.client.operation` | VectorStore operations |
| `spring.ai.tool` | Tool execution và errors |
| `app.ai.evaluation.slice` (custom) | Duration/outcome theo business group/difficulty |

Tên exporter có thể chuẩn hóa dấu chấm thành dấu gạch dưới và thêm suffix. Kiểm tra registry thực tế của project khi viết PromQL.

### Metric labels cardinality thấp

Có thể dùng giá trị đóng:
- `business_group`: policy/orders/tech_support;
- `difficulty`: easy/medium/hard;
- `scenario`: rag/tool/rag_tool/no_context;
- `role`: generator/judge/retriever;
- `outcome`: pass/fail/error.

Không dùng `case_id`, `run_id`, raw prompt, user ID hoặc document ID làm Prometheus labels. Đặt identifiers trong report store/trace attributes theo retention và access policy.

### So sánh latency

Báo riêng:
- user-facing request latency;
- retrieval/vector DB latency;
- generator latency;
- tool latency;
- judge/evaluation latency.

Không cộng span cha và span con hai lần. p95 của slice nhỏ có thể rất bất ổn; luôn ghi sample count.

### Cost

Tính cost theo từng role:
- generator;
- judge;
- embedding;
- tool/provider fee nếu thuộc scope.

\[
C_{\mathrm{call}}=
\frac{T_{\mathrm{input}}}{10^6}P_{\mathrm{input}}
+\frac{T_{\mathrm{output}}}{10^6}P_{\mathrm{output}}.
\]

Báo actual spend và normalized cost khi rate card thay đổi. Missing usage phải có trạng thái riêng, không gán cost bằng 0. Không cộng input, output và total tokens cùng lúc.

## 19. Uncertainty và multiple comparisons trong slice reports

Khi chia dataset thành nhiều groups/intersections, mỗi slice có sample nhỏ hơn overall. Một slice 100% PASS trên 3 case không đủ để kết luận nhóm đó an toàn.

Báo cho từng slice:
- eligible N;
- evaluated N;
- pass/fail counts;
- coverage;
- interval/uncertainty nếu mục tiêu suy luận;
- SMALL_N flag;
- critical count;
- delta A/B.

### Nhiều slice làm tăng khả năng phát hiện tình cờ

3 business groups × 3 difficulty levels × 4 scenarios tạo 36 cells. Nếu chạy kiểm định trên tất cả và chỉ báo những cell có p-value thấp, nguy cơ false positives tăng.

Cách làm:
1. định trước primary slices và critical slices;
2. phân biệt exploratory với confirmatory;
3. dùng Holm/Bonferroni hoặc Benjamini–Hochberg khi phù hợp;
4. công bố số lượng slices đã kiểm tra;
5. tránh đổi taxonomy/weights sau khi xem kết quả.

### Không dùng CI để hợp thức hóa critical failure

Một critical event đã được xác minh có thể kích hoạt veto dù CI của overall pass rate vẫn cao. CI mô tả bất định của metric; safety policy đặt giới hạn rủi ro riêng.

## 20. Quality gate nhiều tầng

Một gate hoàn chỉnh nên có bốn lớp:

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Measurement | Dữ liệu có đủ và đúng không? | Dataset hash, same case IDs, coverage |
| Overall quality | Chất lượng tổng đạt yêu cầu không? | Micro/standardized pass rate |
| Slice quality | Nhóm quan trọng có suy giảm không? | Policy floor, maximum regression |
| Safety/operations | Có lỗi veto hoặc vấn đề vận hành không? | Critical count, error rate, p95, cost |

### Quy tắc ưu tiên quyết định

1. Critical failure đã xác minh và policy veto → **REJECT**.
2. Coverage/manifest/eligibility không hợp lệ → **BLOCKED**.
3. Sample dưới minimum hoặc uncertainty quá lớn → **INCONCLUSIVE**.
4. Overall/per-slice guardrail vi phạm → **REJECT**.
5. Tất cả gate đạt → **PROMOTE**.

Trong production, nhóm có thể chọn escalation/human review cho một số critical incidents; trạng thái review không được tự chuyển thành PROMOTE trước khi có kết luận.

## 21. Report schema gợi ý

Một summary tổng thể:

~~~json
{
  "experimentId": "slice-comparison-006",
  "datasetRevision": "business-eval-v5",
  "scoringPolicyRevision": "quality-v3",
  "weightsRevision": "traffic-mix-2026q4",
  "fixedWeights": {
    "policy": 0.40,
    "orders": 0.30,
    "tech_support": 0.30
  },
  "overall": {
    "microPassRateA": 0.765,
    "microPassRateB": 0.815,
    "macroPassRateA": 0.75,
    "macroPassRateB": 0.8167,
    "standardizedPassRateA": 0.765,
    "standardizedPassRateB": 0.815,
    "coverageA": 1.0,
    "coverageB": 1.0
  },
  "slices": [
    {
      "group": "policy",
      "eligible": 80,
      "evaluatedA": 80,
      "evaluatedB": 80,
      "passA": 72,
      "passB": 64,
      "deltaPp": -10.0,
      "criticalCasesB": 0
    }
  ],
  "decision": "REJECT",
  "reasons": ["Policy regression exceeds the registered guardrail"]
}
~~~

Số liệu trong JSON là ví dụ minh họa, không phải report được tạo từ ứng dụng. Lưu đủ slice rows cho mọi primary group, không chỉ policy.

### Manifest cần lưu

- dataset revision/digest và case IDs;
- primary taxonomy/difficulty/risk revisions;
- eligibility/scoring policy;
- fixed weights và nguồn weights;
- generator/judge provider/model/prompt versions;
- corpus/index/retriever/tool fixture revisions;
- run ID, timestamps, environment, git commit;
- attempts/retry policy;
- trace references, latency, token usage, cost rate card.

## 22. CI workflow cho slice-aware evaluation

~~~mermaid
flowchart TD
  A["Load dataset and manifests"] --> B["Validate case IDs, taxonomy, eligibility"]
  B --> C["Run baseline and candidate"]
  C --> D["Collect answer, evidence, tool and trace snapshots"]
  D --> E["Evaluate each metric with its own denominator"]
  E --> F["Aggregate micro, macro and fixed-weighted rates"]
  F --> G["Compute per-slice coverage, deltas and critical counts"]
  G --> H{"Measurement gate passes?"}
  H -- "No" --> I["BLOCKED / INCONCLUSIVE"]
  H -- "Yes" --> J{"Critical veto or slice regression?"}
  J -- "Yes" --> K["REJECT / HUMAN REVIEW"]
  J -- "No" --> L["PROMOTE"]
~~~

### Preflight

~~~text
assert dataset_revision_A == dataset_revision_B
assert case_ids_A == case_ids_B
assert primary_group_A == primary_group_B
assert difficulty_revision_A == difficulty_revision_B
assert metric_eligibility_A == metric_eligibility_B
assert scoring_policy_A == scoring_policy_B
assert fixed_weights_revision_is_registered()
assert no_duplicate_case_id_per_arm()
assert retry_selection_policy_is_fixed()

run_baseline_and_candidate()
collect_execution_snapshots()
evaluate_each_metric_on_eligible_cases()
compute_slice_counts_and_coverage()
compute_micro_macro_and_standardized_rates()
evaluate_critical_and_slice_guardrails()
publish_report_with_case_level_references()
~~~

Khi cố ý so sánh retriever khác nhau, context hashes có thể khác; hãy lưu snapshot thay vì yêu cầu context giống nhau. Khi so prompt ở frozen-context mode, context của hai arm phải được xác minh tương đương theo thiết kế.

## 23. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Chỉ báo overall micro | Nhóm lớn che nhóm nhỏ | Báo per-slice và guardrails |
| Chỉ báo macro | Slice n rất nhỏ có trọng số ngang | Báo N, coverage, uncertainty |
| Chọn weights sau khi xem kết quả | Tạo report thiên lệch | Đăng ký weights trước |
| Gọi risk-weighted score là traffic accuracy | Nhầm mục tiêu weights | Đặt tên metric đúng mục đích |
| So A/B có composition khác bằng raw micro | Simpson's paradox | Paired case IDs hoặc standardize |
| Bỏ missing verdict | Candidate có thể bỏ sót case khó | Coverage theo slice và measurement gate |
| Cộng tags chồng lấn vào overall | Double-count case | Primary group loại trừ lẫn nhau |
| Cộng parent và child groups | Double-count rollup | Chọn một cấp taxonomy |
| Chỉ nhìn worst slice | Small-N/noise và multiple testing | Phân biệt descriptive/diagnostic/decision-grade |
| Cho nhóm tốt bù critical failure | Che rủi ro nghiệp vụ | Critical hard veto |
| Dùng chung denominator mọi metric | Eligibility khác nhau | Metric-specific denominator |
| Đếm retry thành case mới | Phóng đại N | Attempt ID riêng, case ID ổn định |
| So p95 của slice n nhỏ | Percentile không ổn định | Ghi sample count và interval |
| Gắn case ID vào metric labels | Cardinality và privacy risk | Report store/trace reference |

## 24. Bài thực hành

### Bài A — Tìm Simpson's paradox

Dùng bảng Easy/Hard ở mục 2:
1. Tính micro rate A và B.
2. Tính macro rate A và B.
3. Tính standardized rate với weights 80/20.
4. Giải thích vì sao raw overall đảo chiều.
5. Nêu điều kiện để không còn composition mismatch.

**Đạt:** phân biệt được raw sample result và standardized comparison.

### Bài B — Phát hiện nhóm bị che

Dùng bảng Policy/Orders/Tech support ở mục 6:
1. Tính micro và macro.
2. Xác định nhóm regression.
3. Viết policy gate cho Policy.
4. Quyết định candidate có được promote không.
5. Chỉ ra case-level evidence cần xem.

**Đạt:** không để overall +5 pp che policy −10 pp.

### Bài C — Phân tích missingness

Dùng bảng Easy/Hard ở mục 9:
1. Tính overall pass rate trên evaluated.
2. Tính coverage overall và theo slice.
3. Xác định vì sao B đạt 95% nhưng chưa thể promote.
4. Phân biệt quality fail với operational error.

### Bài D — Chạy Java aggregator

1. Tạo Java 21 project và thêm JUnit 5.
2. Chép `SliceAggregation.java` và `SliceAggregationTest.java`.
3. Chạy test Simpson's paradox, critical veto, insufficient coverage và eligible mismatch.
4. Thêm validation expected case ID sets để bảo đảm A/B cùng IDs.
5. Thêm export JSON có eligible, evaluated, pass, fail, coverage, criticalCases theo từng slice.

**Đạt:** code không phụ thuộc thứ tự rows, không tính weights sai và không promote candidate có critical veto.

### Bài E — RAG/tool drilldown

Tạo:
- 10 policy RAG cases;
- 10 orders tool cases;
- 5 tech-support multi-step cases.

Gắn primary group, difficulty, scenario và risk tier. Chạy baseline/candidate, lưu evidence snapshots, tool calls, traces, rồi tạo report theo từng slice.

### Câu hỏi tự kiểm tra

1. Micro và macro khác nhau ở trọng số nào?
2. Simpson's paradox cần điều kiện composition nào?
3. Khi A/B có cùng case IDs và đầy đủ verdict, vì sao composition không tự thay đổi?
4. Vì sao missingness ở nhóm Hard có thể làm pass rate B tăng giả tạo?
5. Fixed weights cần được chọn lúc nào?
6. Vì sao macro không thay thế critical-slice guardrail?
7. Khi nào một case có thể được tính vào nhiều tags nhưng chỉ một primary group?
8. Vì sao không cộng parent và child vào cùng overall?
9. Relevance và fact checking có dùng cùng denominator không?
10. Critical failure đã xác minh có thể bị weighted average bù trừ không?

**Gợi ý:** (1) micro theo verdict, macro theo group; (2) tỷ trọng nhóm khác nhau; (3) group counts giống nhau nếu eligible/labels giữ nguyên; (4) case khó không có verdict bị loại khỏi denominator; (5) trước khi xem kết quả; (6) macro vẫn cho phép bù trừ; (7) tags chồng lấn, primary group loại trừ lẫn nhau; (8) double-count; (9) thường không; (10) không khi policy có veto.

## 25. Checklist trước khi ra quyết định

- [ ] Overall luôn đi cùng per-slice counts và coverage.
- [ ] Primary business group loại trừ lẫn nhau.
- [ ] Tags chồng lấn không được cộng thành overall.
- [ ] Micro, macro và standardized weights có định nghĩa rõ.
- [ ] Fixed weights có nguồn/revision và được đăng ký trước.
- [ ] A/B dùng cùng case IDs, eligibility và taxonomy khi mục tiêu là paired comparison.
- [ ] Composition differences được báo và giải thích.
- [ ] Missingness/error rates được tách theo group/difficulty.
- [ ] Mỗi metric có denominator riêng.
- [ ] Critical failure có hard veto hoặc escalation policy.
- [ ] Per-slice minimum sample, coverage và regression tolerance được xác định trước.
- [ ] Small-N slices không bị diễn giải quá mức.
- [ ] Multiple comparisons được kiểm soát.
- [ ] Có case-level drilldown cho regression.
- [ ] RAG evidence và tool outputs đúng attempt được lưu.
- [ ] Latency/token/cost được phân tích theo role và slice phù hợp.
- [ ] Report lưu dataset, model, prompt, judge, corpus/index và weights revisions.
- [ ] Quyết định PROMOTE/REJECT/BLOCKED/INCONCLUSIVE có reasons rõ ràng.

## Tài liệu tham khảo

1. [NIST Engineering Statistics Handbook](https://www.itl.nist.gov/div898/handbook/): thiết kế thí nghiệm, sampling và phân tích tỷ lệ.
2. [Simpson's Paradox — Encyclopedia of Mathematics](https://encyclopediaofmath.org/wiki/Simpson_paradox): hiện tượng đảo chiều khi tổng hợp các nhóm có cơ cấu khác nhau.
3. [Spring AI — Evaluation](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator và EvaluationRequest cho đánh giá câu trả lời.
4. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): observations, traces và token usage.
5. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer metrics, timers và histograms.
6. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): percentile và histogram buckets.
7. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm trong logs và telemetry.

> **Ghi nhớ:** Overall là một góc nhìn cần thiết, nhưng không thể thay thế phân tích từng nhóm. Hãy công bố micro/macro/weighted cùng per-slice coverage, critical failures và case-level evidence. Khi nhóm rủi ro cao suy giảm, điểm tốt ở nhóm khác không được dùng để che đi regression đó.
