# Đo tỷ lệ đạt, phân bố điểm và số lỗi nghiêm trọng

> **Chương:** So sánh thí nghiệm
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, relevance, fact checking và kiểm thử luồng RAG/tool calling; kết hợp metrics, traces, chi phí và độ trễ để phát hiện suy giảm giữa các phiên bản prompt, model và pipeline.
>
> **Bối cảnh công nghệ:** Java 21, Spring Boot 4.2.x, Spring AI 2.1.x. Các bảng số liệu trong bài là dữ liệu giả lập phục vụ học phương pháp, không phải kết quả benchmark thực tế.

## 1. Vì sao không thể chỉ báo một tỷ lệ PASS?

Một báo cáo evaluation có thể ghi:

> Candidate B đạt 92% PASS, cao hơn baseline A 89%.

Con số đó chưa đủ để quyết định phát hành. Có thể B:

- tăng số câu trả lời đúng nhưng đồng thời tạo thêm một lỗi nghiêm trọng về chính sách;
- có điểm trung bình cao nhưng phân bố tập trung ở các câu dễ;
- không có verdict ở nhiều case khó do judge timeout;
- đạt relevance nhưng sai fact checking;
- trả lời đúng khi không cần tool nhưng gọi sai tool trong một workflow quan trọng;
- giảm chi phí bằng cách bỏ bớt context, khiến các câu hỏi nhiều bước bị suy giảm.

Vì vậy, khi so sánh các phiên bản Spring AI, cần ít nhất ba góc nhìn:

1. **Tỷ lệ đạt (pass rate):** bao nhiêu tình huống được đánh giá là đạt theo rubric đã khóa?
2. **Phân bố điểm (score distribution):** hệ thống đạt ở mức nào, tập trung ở nhóm điểm nào và có đuôi điểm thấp không?
3. **Số lỗi nghiêm trọng (critical failures):** có bao nhiêu tình huống chứa lỗi không thể chấp nhận, dù điểm tổng có cao đến đâu?

Ba góc nhìn này phải đi cùng **evaluation coverage**, lỗi kỹ thuật, phân nhóm nghiệp vụ/độ khó, latency, token và chi phí. Bài này xây một cách đo có mẫu số rõ ràng và có thể truy nguyên đến từng case.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt execution status, assessment status, pass/fail và severity.
2. Định nghĩa pass rate với đúng mẫu số và báo riêng coverage.
3. Xây rubric điểm có mô tả hành vi quan sát được cho từng mức.
4. Đọc histogram, median, percentile và hiểu vì sao mean không đủ.
5. Đếm critical failures theo **case duy nhất** và theo **số sự cố**, tránh double-count.
6. Tính Wilson confidence interval và nhận diện kết quả có mẫu quá nhỏ.
7. Viết Java 21 aggregator cho score distribution, pass rate, error rates và severity.
8. Kết hợp kết quả với Spring AI Evaluators, RAG/tool assertions, metrics, traces và cost.
9. Đưa ra quality gate có quyền phủ quyết khi xuất hiện lỗi nghiêm trọng.

## 2. Mô hình kết quả: bốn khái niệm riêng biệt

Không nên dùng một trường boolean `success` để đại diện tất cả trạng thái.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Execution outcome** | Pipeline có thực thi được không? | `COMPLETED`, `GENERATION_ERROR`, `TOOL_ERROR` |
| **Assessment outcome** | Có chấm được câu trả lời theo rubric không? | `EVALUATED`, `EVALUATION_ERROR`, `NOT_EVALUATED` |
| **Quality verdict** | Câu trả lời có đạt tiêu chí không? | `PASS`, `FAIL` |
| **Severity** | Nếu có lỗi, hậu quả nghiêm trọng đến đâu? | `NONE`, `MINOR`, `MAJOR`, `CRITICAL` |

Ví dụ:

- Generator hoàn tất và trả câu trả lời sai ngày hiệu lực: `COMPLETED + EVALUATED + FAIL`.
- Generator trả lời, nhưng judge timeout: `COMPLETED + EVALUATION_ERROR + NOT_EVALUATED`.
- Tool không phản hồi: `TOOL_ERROR + NOT_EVALUATED`.
- Assistant gọi đúng tool nhưng tự ý báo “đã thanh toán” khi tool trả “đang xử lý”: `COMPLETED + EVALUATED + FAIL`, có thể `CRITICAL` tùy policy.

**Lỗi kỹ thuật không tự động là lỗi chất lượng nội dung.** Tuy nhiên, lỗi kỹ thuật vẫn là một chỉ số vận hành và có thể chặn release bằng operational gate riêng.

### Một case có thể có nhiều đánh giá

Một answer có thể được chấm relevance, fact checking, tool correctness, completeness và safety. Không nên nén tất cả thành một boolean duy nhất mà không lưu từng criterion.

Ví dụ:

~~~json
{
  "caseId": "policy-hard-014",
  "executionStatus": "COMPLETED",
  "assessments": {
    "relevance": {"status": "EVALUATED", "pass": true},
    "factCheck": {"status": "EVALUATED", "pass": false},
    "toolCorrectness": {"status": "NOT_APPLICABLE"},
    "safety": {"status": "EVALUATED", "pass": false}
  }
}
~~~

Case này **liên quan câu hỏi** nhưng sai dữ kiện và vi phạm safety. Một pass rate gộp không thể diễn tả đầy đủ nếu không có policy về cách kết hợp các tiêu chí.

## 3. Định nghĩa pass rate trước khi chạy

Với một metric cụ thể `m` (ví dụ fact checking) và một tập case đủ điều kiện:

\[
\mathrm{PassRate}_m =
\frac{N_{\mathrm{PASS},m}}
{N_{\mathrm{PASS},m}+N_{\mathrm{FAIL},m}}
\]

Mẫu số chỉ bao gồm những case có **verdict hợp lệ** cho metric đó.

### Coverage phải báo song song

\[
\mathrm{EvaluationCoverage}_m =
\frac{N_{\mathrm{PASS},m}+N_{\mathrm{FAIL},m}}
{N_{\mathrm{Eligible},m}}
\]

Ví dụ có 100 case đủ điều kiện fact checking:

- 90 case được chấm hợp lệ;
- 81 PASS và 9 FAIL;
- 10 case còn lại bị generation/evaluation error hoặc skipped.

Khi đó:

\[
\mathrm{PassRate}=81/90=90\%
\]

\[
\mathrm{EvaluationCoverage}=90/100=90\%.
\]

**Không được báo “90% trên 100 case”** vì chỉ 90 case có verdict. Cũng không được coi 10 case lỗi là PASS hoặc tự đổi thành FAIL để làm mẫu số tròn.

### Bảng trạng thái và cách tính

| Trạng thái | Có verdict chất lượng? | Tính vào pass-rate denominator? | Báo ở đâu? |
|---|---|---|---|
| `PASS` | Có | Có | Quality |
| `FAIL` | Có | Có | Quality |
| `GENERATION_ERROR` | Không | Không | Execution error |
| `TOOL_ERROR` | Không nếu tool không trả evidence cần thiết | Không cho quality; có cho tool error rate | Operational/tool |
| `EVALUATION_ERROR` | Không | Không | Judge/evaluation error |
| `SKIPPED` | Không | Không | Skipped/coverage |
| `NOT_APPLICABLE` | Không áp dụng metric | Không | Eligibility breakdown |
| `NO_CONTEXT` | Tùy rubric abstention | Chỉ trong metric phù hợp | Retrieval/abstention |

### Định nghĩa mẫu số không được thay giữa các run

Mỗi metric phải có:

- **Eligibility rule:** case nào được tính?
- **Denominator:** tổng case đủ điều kiện hoặc tổng attempts?
- **Retry policy:** attempt nào được chọn?
- **Missing policy:** xử lý case không có verdict ra sao?
- **Revision:** rubric và scoring policy phiên bản nào?

Ví dụ `tool_correctness` chỉ có mẫu số là tool-required cases; `retrieval_recall@k` chỉ áp dụng với case có relevant document IDs; `abstention_pass_rate` chỉ áp dụng cho case mà policy yêu cầu từ chối khi thiếu evidence. Không lấy 100 case của mọi scenario làm mẫu số chung cho mọi metric.

## 4. Rubric điểm có anchor rõ ràng

Một thang điểm hữu ích phải mô tả **hành vi quan sát được**, không chỉ dùng các từ “tốt”, “khá” hay “tệ”.

Ví dụ thang 0–4 cho answer RAG:

| Điểm | Mức | Tiêu chí |
|---:|---|---|
| **4** | Đạt đầy đủ | Trả lời đúng trọng tâm, claim quan trọng được evidence hỗ trợ, không bỏ sót điều kiện cần |
| **3** | Đạt phần chính | Kết luận đúng, có thể thiếu một chi tiết nhỏ không làm thay đổi ý nghĩa hoặc quyết định |
| **2** | Một phần | Có thông tin đúng nhưng thiếu điều kiện quan trọng, trả lời chưa đủ hoặc evidence hỗ trợ yếu |
| **1** | Hầu hết không đạt | Sai một phần lớn, dùng nhầm nguồn hoặc suy diễn vượt quá evidence |
| **0** | Không chấp nhận | Bịa claim trọng yếu, làm ngược policy, tiết lộ dữ liệu hoặc hướng dẫn hành động nguy hiểm |

### Ngưỡng PASS là policy, không phải tính chất tự nhiên của điểm

Một policy mẫu:

~~~yaml
scoring_policy:
  revision: "rag-answer-v2"
  score_scale: [0, 1, 2, 3, 4]
  pass_threshold: 3
  critical_failure_veto: true
  required_criteria:
    - relevance
    - fact_check
    - safety
  combine_rule: "all_required_criteria_pass"
~~~

Với policy này, case chỉ PASS nếu:

1. Điểm đạt ngưỡng `3` trở lên;
2. Tất cả tiêu chí bắt buộc đạt;
3. Không có critical failure.

**Không mặc định mọi dự án phải dùng threshold 3/4.** Rubric, ngưỡng và cách kết hợp cần chuyên gia nghiệp vụ phê duyệt, có version, được hiệu chuẩn với tập human-labeled cases.

### Điểm số là ordinal

Thang 0–4 ở trên là **thang thứ bậc**: 4 tốt hơn 3, 3 tốt hơn 2. Không chắc khoảng cách giữa 0→1 bằng 3→4. Vì vậy:

- Histogram và tỷ lệ từng mức là báo cáo chính.
- Median/percentiles giúp mô tả mức trung tâm và đuôi phân bố.
- Mean có thể báo bổ sung để theo dõi trend nếu rubric được neo ổn định, nhưng không được diễn giải như thước đo khoảng cách tuyệt đối.
- Không thay rubric/threshold giữa A/B rồi so mean như cùng một đại lượng.

## 5. Phân bố điểm quan trọng hơn một con số trung bình

Hai model có thể cùng mean 3,22 nhưng phân bố khác:

<box>
  <title size="md">Ví dụ phân bố điểm trên 100 case</title>
  <text color="secondary" size="xs">Số case ở mỗi mức; dữ liệu giả lập</text>
  | Điểm | Model A | Model B |
  |---:|---:|---:|
  | 0 | 2 | 8 |
  | 1 | 2 | 2 |
  | 2 | 10 | 10 |
  | 3 | 44 | 20 |
  | 4 | 42 | 60 |
  | **Tổng** | **100** | **100** |
</box>

Trong ví dụ:

- A có ít điểm 0 hơn B; B có nhiều điểm 4 hơn, nhưng số điểm 0 cũng tăng từ 2 lên 8.
- Cả hai có mean **3,22**: A = (2 + 20 + 132 + 168)/100; B = (2 + 20 + 60 + 240)/100.
- Nếu điểm 0 đại diện lỗi nghiêm trọng, **không thể chọn B chỉ vì mean cao**.

### Các thống kê nên báo

| Thống kê | Trả lời câu hỏi | Hạn chế |
|---|---|---|
| Count từng điểm | Phân bố ở mức nào? | Cần ghi tổng N |
| Median | Mức giữa của case đã chấm? | Có thể che đuôi xấu |
| P10/P90 | Đuôi thấp/cao của phân bố? | Slice nhỏ khiến quantile bất ổn |
| Mean | Mức điểm trung bình? | Nhạy với điểm cực đoan; ordinal scale |
| Standard deviation/IQR | Mức phân tán? | Không thay cho histogram |
| PASS/FAIL | Bao nhiêu case vượt ngưỡng? | Mất thông tin trong từng mức điểm |
| Critical failure count/rate | Có lỗi không thể chấp nhận? | Cần taxonomy và denominator riêng |

### Chọn percentile có quy ước

Với dataset nhỏ, percentile có nhiều quy ước nội suy. Cần ghi phương pháp (ví dụ **nearest-rank quantile**) và N. Với nearest-rank:

\[
\mathrm{rank}(q)=\lceil qN\rceil
\]

Lấy giá trị tại vị trí rank trong danh sách đã sắp tăng. Ví dụ N=10, P90 lấy phần tử thứ 9. Không so hai báo cáo dùng quantile conventions khác nhau mà không chuyển đổi.

## 6. Phân loại lỗi theo mức độ nghiêm trọng

Severity mô tả **hậu quả của lỗi**, không phải mức độ model tự tin hay số điểm của evaluator.

| Severity | Ý nghĩa | Ví dụ trong ứng dụng AI |
|---|---|---|
| `CRITICAL` | Có khả năng gây thiệt hại lớn, vi phạm policy/quyền, hoặc quyết định sai nghiêm trọng | Bịa điều kiện pháp lý trọng yếu; tiết lộ dữ liệu; gọi tool thực hiện giao dịch trái phép |
| `MAJOR` | Làm sai kết quả nghiệp vụ hoặc khiến người dùng hành động sai đáng kể | Báo sai trạng thái đơn; bỏ qua điều kiện quan trọng; hướng dẫn sai bước khôi phục |
| `MINOR` | Lỗi nhỏ không làm thay đổi quyết định chính | Thiếu chi tiết phụ, format khó đọc, diễn đạt không rõ nhưng không sai kết luận |
| `NONE` | Không phát hiện lỗi theo rubric | Answer đạt các tiêu chí đã kiểm |

### Severity cần được gán theo policy

Định nghĩa nên xét:

- **Impact:** hậu quả đối với người dùng/hệ thống nếu làm theo answer.
- **Scope:** một người, một nhóm hay nhiều người dùng.
- **Reversibility:** có thể sửa/hoàn tác hay không.
- **Policy violation:** có vượt quyền, tiết lộ dữ liệu hoặc vi phạm quy định?
- **Likelihood:** khả năng người dùng sẽ thực hiện hành động dựa trên output.

Không nên dùng riêng độ dài answer, confidence score hoặc số lượng hallucinated claims để suy ra severity.

### Critical failure là hard veto

Một case có thể đạt điểm cao ở relevance và completeness nhưng vẫn chứa **một claim critical**. Nếu policy định nghĩa critical failure veto, case đó phải FAIL bất kể điểm trung bình.

Ví dụ:

| Criterion | Điểm |
|---|---:|
| Relevance | 4 |
| Completeness | 4 |
| Style | 4 |
| Fact checking | 0 |
| Safety | 0 |

Mean đơn giản là 2.4; nhưng nếu fact checking/safety có lỗi critical, không được để các tiêu chí style/relevance bù trừ thành PASS.

**Severity và score là hai trường độc lập.** Có thể có score 0 do không liên quan nhưng severity minor; hoặc score tổng khá cao nhưng một claim gây hậu quả nghiêm trọng. Ghi cả hai và giải thích mapping trong rubric.

## 7. Đếm lỗi nghiêm trọng: case count khác incident count

Một case có thể có nhiều lỗi:

~~~json
{
  "caseId": "order-021",
  "severity": "CRITICAL",
  "incidents": [
    {"code": "UNAUTHORIZED_TOOL_ACTION", "severity": "CRITICAL"},
    {"code": "FALSE_DELIVERY_CLAIM", "severity": "MAJOR"}
  ]
}
~~~

Khi tổng hợp, phải phân biệt:

1. **Critical case count:** số case duy nhất có ít nhất một critical failure.
2. **Critical incident count:** tổng số incident critical được ghi nhận.
3. **Severity distribution per case:** mỗi case được gán severity cao nhất theo policy để phân nhóm loại trừ lẫn nhau.

Nếu một case có ba critical incidents, critical case count vẫn là **1**, critical incident count là **3**. Không lấy 3 chia cho 100 rồi gọi đó là tỷ lệ case có critical.

### Công thức

\[
\mathrm{CriticalCaseRate}=
\frac{N_{\mathrm{unique\ cases\ with\ critical}}}
{N_{\mathrm{eligible\ cases}}}
\]

\[
\mathrm{CriticalIncidentRate}=
\frac{N_{\mathrm{critical\ incidents}}}
{N_{\mathrm{eligible\ cases}}}
\]

Chỉ số thứ hai có thể lớn hơn 1 nếu một case có nhiều incidents. Khi báo phần trăm, phải ghi rõ đây là **incident trên case**, không phải xác suất một case gặp lỗi.

### Severity weighted score có nguy cơ gây hiểu nhầm

Một số nhóm muốn tính:

\[
W = 5N_{\mathrm{critical}} + 2N_{\mathrm{major}} + N_{\mathrm{minor}}.
\]

Đây chỉ là **chỉ số nội bộ** nếu trọng số đã được chuyên gia phê duyệt. Không có quy tắc phổ quát nói critical luôn gấp 5 lần minor. Weighted score cũng **không được phép bù trừ** critical failure bằng nhiều case tốt. Hãy luôn báo raw critical counts và dùng veto gate riêng.

## 8. Ví dụ một run 100 case: pass rate, điểm và severity

Giả sử có 100 case đủ điều kiện. Một run có:

| Trạng thái | Số case |
|---|---:|
| Evaluated | 94 |
| Generation error | 3 |
| Evaluation error | 2 |
| Skipped | 1 |
| Missing result | 0 |
| **Eligible total** | **100** |

Trong 94 case evaluated, score distribution:

| Điểm | Số case | Tỷ lệ trên 94 evaluated |
|---:|---:|---:|
| 0 | 2 | 2,13% |
| 1 | 5 | 5,32% |
| 2 | 9 | 9,57% |
| 3 | 24 | 25,53% |
| 4 | 54 | 57,45% |
| **Tổng** | **94** | **100%** |

Nếu pass threshold là 3 và không có critical veto trong nhóm score 3/4:

\[
\mathrm{PassRate}= (24+54)/94=78/94\approx82.98\%.
\]

\[
\mathrm{EvaluationCoverage}=94/100=94\%.
\]

Giả sử 16 failed cases được phân theo severity cao nhất:

| Severity | Số case |
|---|---:|
| Critical | 2 |
| Major | 8 |
| Minor | 6 |
| **Tổng failed** | **16** |

Kết quả quan trọng:

- **Pass rate:** 82,98% trên 94 case có verdict.
- **Evaluation coverage:** 94% trên 100 case eligible.
- **Critical case count:** 2.
- **Critical case rate:** 2/100 = 2%.
- **Critical rate trên evaluated:** 2/94 ≈ 2,13%.
- **Generation error rate:** 3/100 = 3%.
- **Evaluation error rate:** 2/100 = 2%.
- **Skipped rate:** 1/100 = 1%.

Điểm trung bình của 94 case:

\[
\bar{x}=\frac{0(2)+1(5)+2(9)+3(24)+4(54)}{94}
=\frac{311}{94}\approx3.31.
\]

Mean 3,31 và pass rate gần 83% nhìn có vẻ tốt, nhưng **2 critical cases** vẫn có thể chặn phát hành.

## 9. So sánh A/B: tỷ lệ tăng không có nghĩa rủi ro giảm

Giả sử cùng dataset 100 eligible cases và cùng scoring policy:

| Metric | Baseline A | Candidate B |
|---|---:|---:|
| Evaluated | 94 | 96 |
| PASS | 78 | 82 |
| FAIL | 16 | 14 |
| Pass rate (trên evaluated) | 82,98% | 85,42% |
| Evaluation coverage | 94% | 96% |
| Critical cases | **2** | **3** |
| Generation errors | 3 | 2 |
| Evaluation errors | 2 | 1 |
| Skipped | 1 | 1 |

B cải thiện pass rate khoảng **2,44 điểm phần trăm** và coverage tăng 2 điểm phần trăm, nhưng critical cases tăng từ 2 lên 3.

**Không đủ dữ liệu để kết luận B an toàn hơn.** Nếu critical failure là veto criterion, B có thể phải bị chặn ngay cả khi overall pass rate tăng.

Ngoài ra, các con số tổng hợp không cho biết critical cases có phải cùng case IDs hay không. Cần paired case-level analysis để biết B đã:

- sửa một critical failure cũ;
- tạo critical failure mới;
- hay giữ nguyên các critical failures và phát sinh thêm một case.

## 10. Phân bố điểm theo nhóm nghiệp vụ và độ khó

Không chỉ báo score distribution toàn bộ dataset. Với module evaluation-observability, cần xem theo:

- `business_group`: policy, orders, tech_support;
- `difficulty`: easy, medium, hard;
- `scenario`: RAG, tool, RAG+tool, no-context;
- `risk_tier`: low, medium, high.

Ví dụ:

| Slice | Evaluated | PASS | Critical | Score 0–1 |
|---|---:|---:|---:|---:|
| Policy / Easy | 28 | 27 | 0 | 0 |
| Policy / Hard | 9 | 6 | **2** | 2 |
| Orders / Medium | 10 | 9 | 0 | 1 |
| Tech support / Hard | 5 | 3 | 0 | 1 |

Đây là ví dụ rút gọn; mỗi slice cần ghi `eligible` và coverage để biết có bao nhiêu case không được chấm. Slice `policy/hard` có 2 critical trong 9 evaluated là tín hiệu cần review ngay dù overall critical rate chỉ 2%.

### Macro, micro và weighted pass rate

**Micro** cho mỗi case trọng số như nhau:

\[
P_{\mathrm{micro}}=\frac{\sum_g PASS_g}{\sum_g Evaluated_g}.
\]

**Macro** cho mỗi nhóm trọng số như nhau:

\[
P_{\mathrm{macro}}=\frac{1}{G}\sum_{g=1}^{G}
\frac{PASS_g}{Evaluated_g}.
\]

**Weighted** dùng weights đã đăng ký trước:

\[
P_{\mathrm{weighted}}=\sum_g w_gP_g,\quad
\sum_gw_g=1.
\]

Weights có thể theo traffic hoặc risk priority, nhưng phải lưu nguồn và revision. Không đổi weights sau khi thấy kết quả để làm candidate đẹp hơn.

**Critical gate không thay bằng weighted average.** Một nhóm policy có lỗi nghiêm trọng không thể được bù bằng điểm tốt của nhóm FAQ dễ.

## 11. Score distribution: histogram, median và đuôi thấp

Một bảng histogram là cách dễ đọc:

~~~text
Score 0 | **
Score 1 | *****
Score 2 | *********
Score 3 | ************************
Score 4 | ******************************************************
~~~

Mỗi dấu sao đại diện một case trong ví dụ 94 evaluated. Trong report thật, dùng count và percentage thay vì ký hiệu để tránh hiểu nhầm độ dài.

### Vì sao cần xem P10?

Nếu P50 = 4 nhưng P10 = 1, phần lớn case đạt điểm cao nhưng nhóm đuôi thấp vẫn rất yếu. Với AI assistant, **đuôi thấp thường chứa những lỗi khó, hiếm hoặc rủi ro cao**.

Các thống kê đề xuất:

- P10/P25: nhóm điểm thấp.
- Median/P50: mức giữa.
- P75/P90: phần trên.
- Min: trường hợp xấu nhất.
- Score counts: phân bố thực tế.
- Critical count: số lỗi nghiêm trọng, không bị percentile che.

### Không lạm dụng mean và standard deviation

Thang điểm 0–4 là ordinal. Mean 3,31 có thể hữu ích để theo dõi trend nếu rubric ổn định, nhưng không thể khẳng định case score 4 “tốt hơn gấp đôi” score 2. Histogram, median và critical counts nên là các chỉ số chính.

Nếu rubric đổi từ 0–4 sang 1–5, hoặc định nghĩa score 3 thay đổi, phải phát hành scoring-policy revision và không so mean cũ/mới như cùng scale.

## 12. Confidence interval cho pass rate

Một tỷ lệ 90% trên 10 case khác với 90% trên 1.000 case. Cần thể hiện **độ bất định**.

Với tỷ lệ quan sát `p̂` và mẫu `n`, Wilson interval là một lựa chọn thường dùng cho tỷ lệ nhị thức:

\[
\mathrm{center}=
\frac{\hat p+\frac{z^2}{2n}}{1+\frac{z^2}{n}}
\]

\[
\mathrm{halfWidth}=
\frac{z}{1+\frac{z^2}{n}}
\sqrt{\frac{\hat p(1-\hat p)}{n}+\frac{z^2}{4n^2}}.
\]

Khoảng tin cậy:

\[
[\mathrm{center}-\mathrm{halfWidth},
\mathrm{center}+\mathrm{halfWidth}].
\]

Với confidence 95%, thường dùng `z≈1.96`. Đây là interval cho tỷ lệ trên các quan sát được mô hình hóa như Bernoulli; nếu cases phụ thuộc theo cùng tài liệu hoặc người dùng, giả định độc lập có thể không đúng.

### Ví dụ minh họa

- 9/10 PASS = 90%, khoảng tin cậy khá rộng.
- 900/1000 PASS = 90%, khoảng tin cậy hẹp hơn.

Cùng điểm 90% nhưng **mức chắc chắn khác nhau**. Không nên promote candidate dựa trên một slice có 2/2 PASS.

### Khi so A/B cùng case IDs

Nếu mỗi case chạy cả A và B, kết quả có cấu trúc paired. Không nên coi hai tỷ lệ như hai mẫu độc lập để kiểm định. Với verdict nhị phân, có thể dùng:

- Bảng `both pass / A-only pass / B-only pass / both fail`.
- McNemar test (exact khi số discordant pairs nhỏ).
- Paired bootstrap, lấy mẫu lại nguyên cặp case.

Confidence interval của **paired delta** nên tôn trọng pairing. Wilson interval riêng từng arm hữu ích cho mô tả pass rate nhưng không thay cho phân tích paired difference.

## 13. Severity taxonomy và critical-failure policy

Trước khi chạy, nhóm nghiệp vụ phải định nghĩa lỗi nào là critical. Ví dụ:

| Domain | Critical failure có thể là |
|---|---|
| Policy | Bịa điều kiện/ngoại lệ trọng yếu khiến người dùng thực hiện sai nghĩa vụ |
| Orders | Khẳng định đã giao/đã thanh toán khi tool chứng minh ngược lại; thực hiện hành động trái quyền |
| Tech support | Hướng dẫn xóa dữ liệu, tắt bảo vệ hoặc chạy thao tác nguy hiểm không được phép |
| RAG security | Làm lộ dữ liệu bị giới hạn hoặc tuân theo prompt injection trong tài liệu |
| Tool calling | Gọi công cụ có side effect vượt quyền hoặc sai đối tượng |

### Severity cao nhất trên case

Nếu một case có nhiều incidents, có thể lưu từng incident nhưng gán case severity bằng mức cao nhất:

`NONE < MINOR < MAJOR < CRITICAL`.

Điều này giúp severity distribution theo case không double-count. Báo thêm incident count khi muốn biết số sự cố.

### Critical failure phải có veto rõ ràng

Ví dụ policy:

~~~yaml
critical_failure_policy:
  revision: "safety-veto-v2"
  any_critical_case_blocks_release: true
  count_unique_cases: true
  severity_owner: "domain-review-board"
  require_human_confirmation: true
  incident_records_retained: true
~~~

Các trường trên là **policy do dự án tự xây**, không phải cấu hình tự động của Spring AI. Nếu critical label do LLM judge dự đoán, cần human confirmation cho release gate; judge không nên tự quyết định bỏ qua một critical incident.

## 14. Java 21: tổng hợp pass rate, score distribution và severity

Ví dụ một aggregator thuần Java, không phụ thuộc provider model. Input là **một verdict đã được chọn theo retry policy cho mỗi case**.

### File `EvaluationSummary.java`

~~~java
package com.example.aiquality.reporting;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.Set;

public final class EvaluationSummary {
    private EvaluationSummary() {}

    public enum Status {
        EVALUATED, GENERATION_ERROR, EVALUATION_ERROR, SKIPPED
    }

    public enum Severity {
        NONE, MINOR, MAJOR, CRITICAL
    }

    public record CaseResult(
            String caseId,
            Status status,
            Integer score,
            Severity severity) {}

    public record Summary(
            int eligible,
            int received,
            int evaluated,
            int passed,
            int failed,
            int generationErrors,
            int evaluationErrors,
            int skipped,
            int missing,
            int criticalCases,
            int majorCases,
            int minorCases,
            Map<Integer, Integer> scoreCounts,
            OptionalDouble meanScore,
            OptionalDouble medianScore,
            OptionalDouble p10Score,
            OptionalDouble p90Score) {

        public OptionalDouble passRate() {
            return ratio(passed, evaluated);
        }

        public OptionalDouble evaluationCoverage() {
            return ratio(evaluated, eligible);
        }

        public OptionalDouble criticalRatePerEligible() {
            return ratio(criticalCases, eligible);
        }

        public OptionalDouble generationErrorRate() {
            return ratio(generationErrors, eligible);
        }

        public OptionalDouble evaluationErrorRate() {
            return ratio(evaluationErrors, eligible);
        }
    }

    public static Summary summarize(
            List<CaseResult> rows,
            int eligibleCaseCount,
            int passThreshold) {

        if (rows == null || eligibleCaseCount < 0
                || passThreshold < 0 || passThreshold > 4) {
            throw new IllegalArgumentException("Tham số đầu vào không hợp lệ");
        }

        Set<String> seen = new HashSet<>();
        int evaluated = 0, passed = 0, failed = 0;
        int generationErrors = 0, evaluationErrors = 0, skipped = 0;
        int critical = 0, major = 0, minor = 0;
        Map<Integer, Integer> scoreCounts = new java.util.TreeMap<>();
        List<Integer> scores = new ArrayList<>();

        for (CaseResult row : rows) {
            if (row == null || row.caseId() == null
                    || row.caseId().isBlank() || row.status() == null) {
                throw new IllegalArgumentException("Case result thiếu dữ liệu");
            }
            if (!seen.add(row.caseId())) {
                throw new IllegalArgumentException(
                    "Case ID bị lặp: " + row.caseId());
            }

            if (row.status() == Status.EVALUATED) {
                if (row.score() == null || row.score() < 0 || row.score() > 4
                        || row.severity() == null) {
                    throw new IllegalArgumentException(
                        "Evaluated case phải có score 0..4 và severity");
                }
                evaluated++;
                scores.add(row.score());
                scoreCounts.merge(row.score(), 1, Integer::sum);

                boolean isPass = row.score() >= passThreshold
                        && row.severity() != Severity.CRITICAL;
                if (isPass) passed++; else failed++;

                switch (row.severity()) {
                    case CRITICAL -> critical++;
                    case MAJOR -> major++;
                    case MINOR -> minor++;
                    case NONE -> { }
                }
            } else {
                if (row.score() != null) {
                    throw new IllegalArgumentException(
                        "Case chưa evaluated không được có score");
                }
                switch (row.status()) {
                    case GENERATION_ERROR -> generationErrors++;
                    case EVALUATION_ERROR -> evaluationErrors++;
                    case SKIPPED -> skipped++;
                    case EVALUATED -> throw new IllegalStateException();
                }
            }
        }

        int received = rows.size();
        if (received > eligibleCaseCount) {
            throw new IllegalArgumentException(
                "Số result lớn hơn eligible case count");
        }
        int missing = eligibleCaseCount - received;

        Collections.sort(scores);
        double sum = scores.stream().mapToInt(Integer::intValue).sum();
        OptionalDouble mean = scores.isEmpty()
                ? OptionalDouble.empty()
                : OptionalDouble.of(sum / scores.size());

        return new Summary(
            eligibleCaseCount, received, evaluated, passed, failed,
            generationErrors, evaluationErrors, skipped, missing,
            critical, major, minor,
            Map.copyOf(scoreCounts),
            mean,
            nearestRank(scores, 0.50),
            nearestRank(scores, 0.10),
            nearestRank(scores, 0.90));
    }

    private static OptionalDouble ratio(int numerator, int denominator) {
        return denominator == 0 ? OptionalDouble.empty()
                : OptionalDouble.of(numerator / (double) denominator);
    }

    private static OptionalDouble nearestRank(
            List<Integer> sorted, double quantile) {
        if (sorted.isEmpty()) return OptionalDouble.empty();
        int rank = (int) Math.ceil(quantile * sorted.size());
        return OptionalDouble.of(sorted.get(Math.max(0, rank - 1)));
    }
}
~~~

### Giới hạn có chủ đích của aggregator

- Hàm nhận **một result cho mỗi case**. Nếu hệ thống có nhiều attempts, runner phải áp dụng retry/selection policy đã version hóa trước.
- `eligibleCaseCount` phải lấy từ dataset đã validate. Code kiểm tra missing count nhưng không thể biết ID nào mất nếu chỉ nhận một số nguyên; bản production nên nhận cả **expected case ID set** để kiểm tra chính xác.
- Severity trong ví dụ là **mức cao nhất trên case**, không phải số incident. Nếu cần incident count, lưu một collection incidents riêng.
- Critical veto được áp dụng ngay trong pass calculation; các tiêu chí bắt buộc khác (relevance, fact-check, safety) cần được kết hợp trong một assessment policy rõ ràng trước khi tạo `CaseResult`.
- Quantile dùng **nearest-rank**; khi báo cáo phải giữ cùng quy ước ở mọi run.
- Khi không có evaluated case, các ratio/quantile trả `OptionalDouble.empty()`; report writer nên xuất `null` và reason code, không ghi `NaN` vào JSON.

## 15. Unit test cho summary và critical veto

### File `EvaluationSummaryTest.java`

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import com.example.aiquality.reporting.EvaluationSummary;
import com.example.aiquality.reporting.EvaluationSummary.*;

class EvaluationSummaryTest {

    private static CaseResult evaluated(
            String id, int score, Severity severity) {
        return new CaseResult(id, Status.EVALUATED, score, severity);
    }

    @Test
    void computesPassCoverageAndCriticalCasesSeparately() {
        var rows = List.of(
            evaluated("a", 4, Severity.NONE),
            evaluated("b", 3, Severity.NONE),
            evaluated("c", 1, Severity.CRITICAL),
            evaluated("d", 2, Severity.MAJOR),
            new CaseResult("e", Status.EVALUATION_ERROR, null, null),
            new CaseResult("f", Status.GENERATION_ERROR, null, null));

        var result = EvaluationSummary.summarize(rows, 8, 3);

        assertEquals(8, result.eligible());
        assertEquals(4, result.evaluated());
        assertEquals(2, result.passed());
        assertEquals(2, result.failed());
        assertEquals(1, result.criticalCases());
        assertEquals(1, result.evaluationErrors());
        assertEquals(1, result.generationErrors());
        assertEquals(2, result.missing());
        assertEquals(0.5, result.passRate().orElseThrow(), 0.000001);
        assertEquals(0.5, result.evaluationCoverage().orElseThrow(), 0.000001);
        assertEquals(0.125,
                result.criticalRatePerEligible().orElseThrow(), 0.000001);
    }

    @Test
    void criticalFailureVetoesAnOtherwisePassingScore() {
        var result = EvaluationSummary.summarize(
            List.of(evaluated("critical", 4, Severity.CRITICAL)), 1, 3);

        assertEquals(0, result.passed());
        assertEquals(1, result.failed());
        assertEquals(1, result.criticalCases());
    }

    @Test
    void rejectsDuplicateCaseIds() {
        assertThrows(IllegalArgumentException.class, () ->
            EvaluationSummary.summarize(
                List.of(
                    evaluated("same", 4, Severity.NONE),
                    evaluated("same", 3, Severity.NONE)),
                2, 3));
    }

    @Test
    void emptyEvaluationHasNoPassRateOrScoreQuantile() {
        var result = EvaluationSummary.summarize(
            List.of(new CaseResult(
                "x", Status.EVALUATION_ERROR, null, null)), 1, 3);

        assertTrue(result.passRate().isEmpty());
        assertTrue(result.medianScore().isEmpty());
        assertEquals(0.0,
                result.evaluationCoverage().orElseThrow(), 0.000001);
    }
}
~~~

Đây là **code hướng dẫn**, không phải một project đã được build. Người học cần tạo package và dependency JUnit 5 trong project Java 21 rồi chạy test. Trong ứng dụng production, nên có test bổ sung cho metric eligibility, expected case ID set, multiple criteria và serialization.

## 16. Tích hợp Spring AI Evaluators đúng vai trò

Spring AI 2.1 có interface `Evaluator` và `EvaluationRequest` để đánh giá một response. Hai evaluator thường dùng:

- `RelevancyEvaluator`: answer có liên quan question/context?
- `FactCheckingEvaluator`: claim có được evidence hỗ trợ?

Ví dụ dựng request:

~~~java
import java.util.List;
import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;

String question = "Hạn nộp báo cáo tháng là khi nào?";
List<Document> evidenceActuallyUsed = List.of(
    new Document("Báo cáo phải nộp trước ngày 05 tháng kế tiếp."));
String answer = "Hạn nộp là trước ngày 15 tháng kế tiếp.";

EvaluationRequest request = new EvaluationRequest(
    question, evidenceActuallyUsed, answer);
// Gửi request đến evaluator đã cấu hình judge model và rubric.
~~~

Đây là fragment code minh họa. Với RAG thật, `evidenceActuallyUsed` phải là **context chính xác đã cấp cho generator**, sau retrieval, filter, rerank và truncation.

### Không để một evaluator quyết định tất cả

Ví dụ answer “Hạn nộp là ngày 15” có thể:

- relevance PASS vì liên quan câu hỏi về hạn nộp;
- fact checking FAIL vì evidence nói ngày 05;
- severity MAJOR hoặc CRITICAL tùy hậu quả và policy.

Một judge trả `isPass()` chỉ đại diện cho **một criterion**. Cần lưu verdict từng evaluator, version judge, rubric, evidence digest và cách kết hợp cuối cùng.

### Judge error không được biến thành FAIL

Nếu judge timeout, 429, trả JSON không parse được hoặc không có verdict:

`assessmentStatus = EVALUATION_ERROR`.

Không tạo `score=0` hoặc `severity=CRITICAL` chỉ vì judge lỗi. Đây là lỗi vận hành của evaluator; report cần đưa vào evaluation error rate và coverage.

## 17. RAG, tool calling và critical errors theo nghiệp vụ

### RAG: relevance và factuality khác nhau

| Answer | Relevance | Fact checking | Severity có thể |
|---|---|---|---|
| Đúng ngày 05 theo tài liệu | PASS | PASS | NONE |
| Nói ngày 15 thay vì ngày 05 | Có thể PASS | FAIL | MAJOR/CRITICAL tùy policy |
| Nêu thêm ngoại lệ không có trong nguồn | Có thể PASS | FAIL | MAJOR hoặc CRITICAL |
| Không trả lời khi context đủ rõ | FAIL | Có thể NOT_APPLICABLE | MINOR/MAJOR |
| Từ chối khi context không có bằng chứng | PASS theo abstention policy | NOT_APPLICABLE | NONE |

Retrieval cũng cần đo riêng:

- Recall@k/hit@k trên case có ground-truth document IDs.
- Context có đúng phiên bản, đúng ngày hiệu lực và không bị truncation?
- Có nguồn cũ/distractor gây nhầm?
- Có prompt injection trong tài liệu khiến assistant làm sai?

**Không đánh đồng retrieval error với hallucination**: cả hai có thể cùng góp phần, nhưng cần snapshot để truy nguyên.

### Tool calling: severity không chỉ dựa vào final answer

Một case tool nên lưu:

~~~json
{
  "caseId": "order-021",
  "expectedTool": "getOrderStatus",
  "expectedArguments": {"orderId": "TEST-021"},
  "actualTool": "getOrderStatus",
  "actualArguments": {"orderId": "TEST-021"},
  "toolResult": {"status": "IN_TRANSIT"},
  "finalAnswer": "Đơn hàng đang được vận chuyển."
}
~~~

Các kiểm tra:

1. Đúng tool name và schema.
2. Arguments đúng giá trị/kiểu và đúng đối tượng.
3. Không gọi tool có side effect ngoài quyền.
4. Diễn giải tool result đúng.
5. Tool timeout/5xx được ghi `TOOL_ERROR`, không tự tính là fact-check FAIL.

Một thao tác thanh toán sai người nhận có thể là **critical**, dù model có giải thích trôi chảy và các tiêu chí style/relevance đạt.

## 18. Metrics, traces, latency và cost theo kết quả

Spring AI kết hợp Micrometer Observation và tracing để quan sát các thành phần khi chúng được gọi. Các tín hiệu có thể hỗ trợ điều tra:

| Tín hiệu | Dùng để hiểu |
|---|---|
| `spring.ai.chat.client` | Duration của ChatClient/advisor chain |
| `spring.ai.advisor` | Tầng advisor nào chậm |
| `gen_ai.client.operation` | Duration ChatModel/EmbeddingModel |
| `gen_ai.client.token.usage` | Input/output tokens khi provider trả usage |
| `db.vector.client.operation` | VectorStore operations |
| `spring.ai.tool` | Tool call duration/error |
| `app.ai.evaluation.case` (custom) | Duration một case evaluation |
| `app.ai.evaluation.outcome` (custom) | Kết quả PASS/FAIL/ERROR với tags giới hạn |

Tên trên là tên observation logic; Prometheus exporter có thể chuẩn hóa dấu chấm thành gạch dưới và thêm suffix như `_seconds_count`, `_total`.

### Metric labels có cardinality thấp

Nên dùng:

- `business_group`: policy/orders/tech_support;
- `difficulty`: easy/medium/hard;
- `scenario`: rag/tool/rag_tool/no_context;
- `role`: generator/judge/retriever;
- `outcome`: pass/fail/generation_error/evaluation_error.

Không đưa `case_id`, `run_id`, user ID, raw prompt, document IDs hoặc tool arguments vào Prometheus labels. Lưu các định danh đó trong report store có quyền truy cập và retention.

### Độ trễ theo role

Phân biệt:

- **User-facing latency:** từ request đến answer/error, không cộng judge offline.
- **Generator latency:** thời gian model tạo answer.
- **Retrieval/tool latency:** vector DB, embedding, tool execution.
- **Evaluation latency:** thời gian judge chấm sau generation.

Không cộng span cha và span con như hai công việc độc lập; span cha có thể bao gồm duration của span con.

### Chi phí theo case

\[
C_{\mathrm{model}}=
\frac{T_{\mathrm{input}}}{10^6}P_{\mathrm{input}}
+\frac{T_{\mathrm{output}}}{10^6}P_{\mathrm{output}}.
\]

\[
C_{\mathrm{case}}=
C_{\mathrm{generator}}+C_{\mathrm{judge}}
+C_{\mathrm{embedding/retrieval/tool}}.
\]

Giá `P` là đơn giá theo một triệu token, cần model, thời điểm, currency và token categories. Tách chi phí generator và judge; không cộng input, output và total tokens cùng lúc. Nếu provider không trả usage, ghi `USAGE_MISSING` thay vì cost=0.

### Critical errors và latency

Một lỗi critical có thể xảy ra ở request rất nhanh hoặc rất chậm. Không dùng latency để suy ra severity. Khi critical rate tăng, hãy xem trace của **case cụ thể** để biết lỗi xuất phát từ retrieval, generation, tool hay policy guard.

## 19. Báo cáo kết quả: một summary phải tự giải thích được

Một summary tối thiểu:

~~~json
{
  "runId": "rag-eval-2026-11-27-A",
  "datasetRevision": "vi-business-v1",
  "scoringPolicyRevision": "rag-answer-v2",
  "eligibleCases": 100,
  "receivedResults": 100,
  "evaluated": 94,
  "pass": 78,
  "fail": 16,
  "passRate": 0.8298,
  "evaluationCoverage": 0.94,
  "generationErrors": 3,
  "evaluationErrors": 2,
  "skipped": 1,
  "missing": 0,
  "criticalCases": 2,
  "severityByCase": {
    "critical": 2,
    "major": 8,
    "minor": 6
  },
  "scoreDistribution": {
    "0": 2,
    "1": 5,
    "2": 9,
    "3": 24,
    "4": 54
  },
  "meanScore": 3.31,
  "medianScore": 4,
  "p10Score": 2,
  "p90Score": 4
}
~~~

Đây là dữ liệu **minh họa đã làm tròn**, không phải report được tạo từ ứng dụng. Trong report thật cần lưu:

- `run_id`, timestamp UTC, environment, git commit và artifact digest;
- dataset revision/hash, case count, split, label revision;
- generator/judge provider/model/options, prompt/rubric revisions;
- corpus/index/embedding/top-k và tool schema/fixture revisions;
- eligibility/scoring policy, pass threshold, severity taxonomy;
- metric counts, denominator, coverage, confidence interval;
- token usage, rate card, cost, latency, trace references;
- per-case verdict và evidence snapshot có kiểm soát quyền.

### Báo cáo theo từng slice

Mỗi dòng `business_group × difficulty × metric` nên có:

| Field | Ý nghĩa |
|---|---|
| `eligible` | Số case áp dụng metric |
| `evaluated` | Có verdict hợp lệ |
| `pass` / `fail` | Kết quả nội dung |
| `pass_rate` | PASS / evaluated |
| `coverage` | evaluated / eligible |
| `critical_case_count` | Case duy nhất có critical |
| `score_counts` | Histogram 0–4 |
| `p10/p50/p90` | Phân vị điểm theo quy ước |
| `generation/evaluation_error` | Lỗi theo nguồn |
| `p95_latency/cost` | Hiệu quả vận hành nếu đủ mẫu |

Không gộp các metric có eligibility khác nhau vào cùng một denominator. `tool_correctness`, `fact_check` và `retrieval_recall` thường có các tập eligible khác nhau.

## 20. Quality gate: critical failure có quyền phủ quyết

Ví dụ gate:

~~~yaml
quality_gate:
  revision: "release-quality-v3"
  minimum_evaluation_coverage: 0.98
  minimum_pass_rate: 0.90
  maximum_evaluation_error_rate: 0.01
  maximum_generation_error_rate: 0.02
  critical_failure:
    max_unique_cases: 0
    any_critical_blocks_release: true
  critical_slices:
    - business_group: policy
      risk_tier: high
      minimum_coverage: 0.99
      require_human_review: true
  operational:
    maximum_generator_p95_ms: 3000
    maximum_mean_cost_usd_per_case: 0.03
~~~

Các ngưỡng trên là **minh họa**, không phải mặc định Spring AI. Trong sản phẩm thật, phải dựa vào risk appetite, yêu cầu nghiệp vụ, baseline, độ tin cậy judge và ngân sách.

### Tách ba lớp gate

| Gate | Ví dụ | Nếu không đạt |
|---|---|---|
| Measurement | Dataset hash đúng, coverage đủ, judge hoạt động | `BLOCKED` hoặc `INCONCLUSIVE` |
| Quality/safety | Pass rate đạt, critical count bằng 0 | `REJECT` hoặc human review |
| Operational | Error rate, p95 và cost trong giới hạn | Không promote cho tới khi xử lý |

Nếu `criticalCases > 0` và policy quy định veto, candidate **không được promote chỉ vì pass rate tăng**. Cần điều tra case, xác minh severity với domain expert và chạy lại sau khi sửa.

## 21. Các sai lầm khi đọc score và severity

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Chỉ báo pass rate | Che score thấp và lỗi critical | Báo histogram, coverage, severity |
| Coi error là FAIL | Nhầm lỗi vận hành với chất lượng answer | Tách status và denominator |
| Đếm incident thành số case | Một case có nhiều lỗi bị đếm trùng | Báo unique critical cases và incident count |
| Dùng mean làm metric duy nhất | Ordinal scale, che đuôi thấp | Histogram, median, P10, critical count |
| Severity suy ra từ score | Điểm cao có thể chứa một lỗi nguy hiểm | Severity độc lập, veto |
| Judge tự gán critical không review | Judge có false positive/negative | Human confirmation và calibration |
| Không ghi eligibility | So metric khác mẫu số | Version hóa eligibility policy |
| Bỏ case judge timeout | Coverage giảm bị che | Evaluation error rate và coverage |
| So p95 trên slice n=3 | Quantile rất bất ổn | Small-N warning hoặc thu thêm mẫu |
| Đổi rubric giữa A/B | Không cùng thước đo | Khóa rubric hoặc chấm lại cả hai |
| Cộng token sai | Có thể đếm đôi input/output/total | Ghi token categories đúng provider |
| Critical rate dùng incident count | Có thể >100% và bị gọi sai | Phân biệt case rate/incident rate |

## 22. Thực hành có hướng dẫn

### Bài A — Tính ba chỉ số từ run 100 case

Sử dụng dữ liệu tại mục 8:

- 94 evaluated, 78 PASS, 16 FAIL;
- 3 generation errors, 2 evaluation errors, 1 skipped;
- 2 critical, 8 major, 6 minor.

Hãy tính:

1. Pass rate trên evaluated.
2. Evaluation coverage trên eligible.
3. Critical case rate trên eligible.
4. Generation error rate và evaluation error rate.
5. Score mean và median theo nearest-rank convention.

**Tiêu chí đạt:** phân biệt đúng mọi denominator và nhận ra critical gate có thể chặn release.

### Bài B — So A/B khi pass rate tăng nhưng critical tăng

Dùng bảng mục 9:

1. Tính delta pass rate theo điểm phần trăm.
2. Tính delta coverage.
3. So critical count và critical case rate.
4. Đề xuất quyết định theo policy veto.
5. Nêu những case-level evidence cần review trước khi quyết định.

**Tiêu chí đạt:** không chọn candidate chỉ vì pass rate cao hơn.

### Bài C — Implement Java summary

1. Đưa `EvaluationSummary` và `EvaluationSummaryTest` vào project Java 21/JUnit 5.
2. Thêm case score 4 nhưng severity CRITICAL; xác nhận vẫn FAIL.
3. Thêm duplicate ID và invalid score 5; xác nhận validator reject.
4. Thêm case `EVALUATION_ERROR`; xác nhận không có score và không tính vào pass denominator.
5. Mở rộng aggregator để nhận expected case ID set và kiểm missing IDs cụ thể.

### Bài D — Đánh giá RAG/tool theo metric riêng

Chuẩn bị:

- 10 RAG cases có relevant document IDs;
- 10 tool-required cases có expected tool/arguments;
- 5 no-context cases cần abstention.

Tạo report riêng cho:

- retrieval recall@k;
- relevance;
- fact checking;
- tool correctness;
- abstention.

Không đưa tool-only vào retrieval denominator nếu metric không áp dụng.

### Bài E — Human calibration cho critical severity

1. Tạo 20 ví dụ synthetic gồm critical/major/minor/none.
2. Hai reviewer gán severity độc lập theo taxonomy.
3. Đối chiếu bất đồng và làm rõ rubric.
4. So judge output với human decisions, tính false critical/false negative.
5. Chỉ dùng critical gate sau khi có policy review và quy trình escalation.

### Câu hỏi tự kiểm tra

1. Vì sao pass rate 90% trên 10 case khác 90% trên 1.000 case?
2. Evaluation error có được tính vào pass-rate denominator không?
3. Score 4 có thể vẫn FAIL không? Trong trường hợp nào?
4. Vì sao severity phải độc lập với score?
5. Một case có ba critical incidents thì critical case count bằng bao nhiêu?
6. P10 giúp phát hiện điều gì mà mean không thể hiện rõ?
7. Tại sao histogram và median phù hợp hơn mean đơn lẻ với score ordinal?
8. Vì sao relevance PASS có thể đi cùng fact checking FAIL?
9. Critical failure veto có thể làm thay đổi quyết định khi candidate có pass rate cao hơn như thế nào?
10. Khi nào Wilson interval không đủ để mô tả độ bất định?

**Gợi ý:** (1) sample size và độ bất định khác; (2) không; (3) có critical veto hoặc tiêu chí bắt buộc khác fail; (4) hậu quả không đồng nghĩa chất lượng trung bình; (5) một unique case, ba incidents; (6) đuôi điểm thấp; (7) ordinal scale và phân bố; (8) câu trả lời liên quan nhưng sai dữ kiện; (9) gate có quyền chặn; (10) paired data, clustering hoặc sampling bias.

## 23. Checklist trước khi công bố kết quả

- [ ] Rubric, pass threshold, required criteria và severity taxonomy đã được version hóa.
- [ ] Metric eligibility và denominator được định nghĩa trước khi chạy.
- [ ] Báo pass rate **cùng evaluation coverage**.
- [ ] Generation, tool, judge errors và skipped được phân loại riêng.
- [ ] Có histogram/count cho từng score; mean chỉ là chỉ số bổ sung.
- [ ] Có median, percentile và sample count với quy ước tính rõ ràng.
- [ ] Critical case count được đếm theo case duy nhất, incident count báo riêng.
- [ ] Critical failure veto được định nghĩa và phê duyệt.
- [ ] Có phân tích theo business group, difficulty, scenario và risk tier.
- [ ] Mỗi slice có eligible/evaluated/pass/fail/coverage và cảnh báo small N.
- [ ] A/B dùng cùng dataset, labels, rubric và eligibility; pairing được kiểm tra.
- [ ] Judge errors không bị biến thành FAIL của generator.
- [ ] RAG judge nhận đúng evidence đã cấp cho generator.
- [ ] Tool correctness được kiểm bằng assertions cho tool name/arguments.
- [ ] Confidence interval/paired analysis phù hợp với thiết kế lấy mẫu.
- [ ] Token, latency và cost tách generator khỏi judge.
- [ ] Trace/report có thể truy nguyên mà không ghi secrets/PII vào metric labels.
- [ ] Quality gate phân biệt measurement, quality/safety và operational criteria.
- [ ] Mọi critical cases đã được review/escalate theo policy.

## Tài liệu tham khảo

1. [Spring AI 2.1 — Evaluators](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/evaluation/evaluators.html): `EvaluationRequest`, `RelevancyEvaluator` và `FactCheckingEvaluator`.
2. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient, ChatModel, VectorStore, tool observations và tracing.
3. [Spring AI 2.1 — Metrics](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/observability/metrics.html): model operation metrics và token usage.
4. [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer counters, timers và histogram.
5. [NIST Engineering Statistics Handbook](https://www.itl.nist.gov/div898/handbook/): thống kê mô tả, tỷ lệ, confidence intervals và thiết kế thí nghiệm.
6. [NIST — Wilson Score Interval](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm): ước lượng tỷ lệ và khoảng tin cậy.
7. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): percentile latency và histogram buckets.
8. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm trong logs và telemetry.

> **Ghi nhớ:** Một báo cáo Spring AI đáng tin không dừng ở câu “đạt 92%”. Hãy công bố **PASS trên mẫu số nào, phân bố điểm ra sao, bao nhiêu case có critical failure, bao nhiêu case không được chấm và lỗi nằm ở generator hay evaluator**. Critical failures phải có quyền phủ quyết độc lập; không để điểm trung bình hoặc chi phí thấp che khuất rủi ro nghiệp vụ.
