# Đánh giá biến động qua nhiều lần chạy

> **Chương:** So sánh thí nghiệm
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; kết hợp metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm giữa các phiên bản prompt, model và pipeline.
>
> **Bối cảnh công nghệ:** Java 21, Spring Boot 4.2.x và Spring AI 2.1.x. Các số liệu trong bài là ví dụ tổng hợp để học cách thiết kế phép đo, không phải kết quả benchmark của một model cụ thể.

## 1. Vì sao một lần chạy chưa đủ?

Một bộ regression có 100 tình huống. Hôm nay ứng dụng đạt 91 PASS; chạy lại ngày mai chỉ đạt 87 PASS, dù nhóm không sửa prompt hay code. Nếu chỉ lưu một con số cho mỗi phiên bản, nhóm khó biết:

- Chênh lệch là **dao động ngẫu nhiên** của model hay là regression thật?
- Generator đã tạo câu trả lời khác nhau cho cùng câu hỏi?
- Judge LLM đã đổi verdict dù answer/evidence không đổi?
- Provider chuyển model alias sang backend revision khác?
- Vector index, corpus hoặc tool output thay đổi giữa hai lần chạy?
- Quota, retry, concurrency hay latency đã làm mất verdict ở những case khó?

Với ứng dụng Spring AI, **một run là một mẫu quan sát**, không phải sự thật tuyệt đối về chất lượng model. Cần chạy lặp lại dưới điều kiện được kiểm soát, giữ lại kết quả theo từng case và phân tích độ biến động.

Mục tiêu không phải chỉ tìm ra điểm trung bình cao nhất. Ta cần biết **hệ thống ổn định đến đâu, tình huống nào hay đổi verdict, biến động đến từ generator hay evaluator, và liệu có xu hướng suy giảm theo thời gian hay không**.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **repeatability**, **reproducibility**, stochastic variation và drift.
2. Thiết kế nhiều lần chạy trên cùng dataset với run manifest và run blocks.
3. Tách biến động của generator, retriever, tool và judge.
4. Đo pass rate từng run, trung bình qua runs, độ lệch chuẩn, confidence interval và coverage.
5. Tính **pass probability**, verdict flip rate và độ ổn định theo từng case.
6. Nhận diện flaky cases, lỗi kỹ thuật và biến động do provider/time window.
7. Viết Java 21 aggregator và JUnit tests cho repeated runs.
8. So sánh A/B theo các run blocks ghép cặp, không coi mọi request lặp là quan sát độc lập.
9. Kết hợp score distribution, critical failures, metrics, traces, latency, token và cost trong quyết định release.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa trong evaluation |
|---|---|
| **Repeatability — tính lặp lại** | Cùng nhóm, cùng môi trường và điều kiện gần như không đổi, chạy lại có kết quả tương tự đến mức nào? |
| **Reproducibility — khả năng tái lập** | Nhóm khác có thể dùng manifest, artifacts và môi trường được mô tả để thực hiện lại thí nghiệm và kiểm tra kết luận không? |
| **Stochastic variation — biến động ngẫu nhiên** | Kết quả thay đổi dù cấu hình và dữ liệu đầu vào được giữ cố định, ví dụ do sampling hoặc hành vi serving |
| **Drift — thay đổi theo thời gian** | Chất lượng/phân bố kết quả thay đổi có hệ thống qua thời gian, do model, dữ liệu, traffic, provider hoặc môi trường |
| **Flaky case** | Một tình huống có lúc PASS, lúc FAIL hoặc lúc không có verdict qua các lần chạy |

Một pipeline có thể **repeatable nhưng không reproducible** nếu chỉ máy của một người có cấu hình bí mật chưa được ghi lại. Ngược lại, manifest có thể đầy đủ nhưng hosted LLM vẫn không trả output giống từng token vì provider thay backend hoặc sampling.

### Không đồng nhất temperature=0 với deterministic tuyệt đối

`temperature=0` thường giảm ngẫu nhiên trong sampling, nhưng không đảm bảo output giống từng token giữa các lần gọi API. Provider có thể:

- thay model revision phía sau một alias;
- thay hardware, batching hoặc inference backend;
- cập nhật safety policy, tokenizer hoặc serving logic;
- định tuyến request đến nhiều deployment;
- không hỗ trợ seed hoặc chỉ hỗ trợ seed theo điều kiện nhất định.

Vì vậy, ghi **requested model ID**, resolved revision nếu provider công bố, request options thực tế và response metadata. Nếu không biết resolved revision, ghi `null` hoặc `unknown`; không tự suy đoán.

## 3. Nguồn gây biến động trong ứng dụng Spring AI

Một run có thể thay đổi ở nhiều tầng:

| Tầng | Nguồn biến động | Dấu hiệu |
|---|---|---|
| Generator | Sampling, model alias, provider backend, safety behavior | Answer khác dù question/context giống |
| Prompt | Template revision, biến render, history, truncation | Rendered prompt digest khác |
| Retrieval | Corpus update, index rebuild, embedding, filters, reranker | Retrieved document IDs khác |
| Context assembly | Thứ tự chunks, deduplication, token budget | Context hash/length khác |
| Tool | External state, timeout, retry, API contract, fixture | Tool output/arguments/status khác |
| Judge | Model/prompt/rubric, sampling, parsing | Cùng answer nhưng verdict khác |
| Runtime | JDK/dependencies, concurrency, queue, memory | Latency/error thay đổi |
| Provider/network | Rate limit, overload, routing, region | 429/5xx/timeout, tail latency tăng |
| Dataset | Labels, source documents, case selection | Mẫu số/ground truth thay đổi |
| Telemetry | Sampling, exporter, retention, schema | Trace thiếu hoặc metrics đổi tên |

**Không gộp tất cả biến động thành “model không ổn định”.** Một case FAIL ngẫu nhiên do judge timeout là vấn đề evaluator/availability; một answer sai dù execution hoàn tất là vấn đề quality; context thay đổi là vấn đề retrieval/evidence.

## 4. Đơn vị đo và cấu trúc dữ liệu nhiều lần chạy

Một thí nghiệm repeated-run có các cấp:

~~~text
Experiment
  ├── Arm A (baseline)
  │     ├── Run block 01
  │     │     ├── Case 001 / attempt 1 / assessment
  │     │     └── Case 002 / attempt 1 / assessment
  │     └── Run block 02
  │           └── ...
  └── Arm B (candidate)
        ├── Run block 01
        │     └── ...
        └── Run block 02
              └── ...
~~~

Các định danh:

- `experiment_id`: câu hỏi nghiên cứu và kế hoạch.
- `arm`: biến thể A/B.
- `run_block_id`: một cửa sổ thực thi chứa các run cần ghép cặp, ví dụ A và B trong cùng khung giờ.
- `run_id`: một lần chạy một arm trên dataset.
- `case_id`: tình huống ổn định trong dataset.
- `attempt`: một lần thực thi case; retry là attempt mới, không ghi đè attempt trước.
- `assessment_id`: một lần chấm output bởi judge/rubric cụ thể.

**Không dùng một run_id cho tất cả lần chạy.** Mỗi run cần manifest và kết quả riêng, kể cả khi dùng cùng prompt/model.

### Hai loại lặp lại cần tách riêng

1. **Generation repeats:** chạy generator nhiều lần trên cùng question/context để đo biến động đầu ra.
2. **Judge repeats:** giữ nguyên answer/evidence snapshot, chấm lại nhiều lần để đo biến động của evaluator.

Nếu vừa sinh lại answer vừa đổi judge, không thể biết verdict flip đến từ generator hay judge. Khi cần chẩn đoán, có thể thực hiện ma trận:

| | Judge J1 | Judge J2 |
|---|---|---|
| Answer snapshot A1 | Chấm A1/J1 | Chấm A1/J2 |
| Answer snapshot A2 | Chấm A2/J1 | Chấm A2/J2 |

Ma trận này giúp quan sát riêng **answer variance** và **judge variance**. Để đánh giá chất lượng production, vẫn phải dùng judge/human policy đã được chọn trước.

## 5. Thiết kế repeated runs có kiểm soát

### 5.1. Khóa các biến trước khi chạy

Trong một thí nghiệm muốn đo độ lặp lại của generator, giữ nguyên:

- dataset revision, case IDs, question và labels;
- prompt template, render policy và context snapshot;
- generator provider/model/options;
- tool fixtures và expected outputs;
- judge model, rubric, thresholds và calibration set;
- JDK, Spring Boot/Spring AI BOM, dependencies và artifact;
- timeout, retry policy, concurrency và token budget.

Nếu mục tiêu là đo **end-to-end pipeline drift**, có thể cho retrieval/tool chạy lại, nhưng phải lưu chính context và tool outputs của mỗi run. Không tuyên bố generator variance khi evidence đầu vào thay đổi.

### 5.2. Dùng run blocks và interleaving

Ví dụ có 5 run blocks. Mỗi block chạy A và B trong cùng cửa sổ thời gian, hoán đổi thứ tự:

| Block | Thứ tự chạy | Mục đích |
|---|---|---|
| 01 | A → B | Baseline |
| 02 | B → A | Giảm ảnh hưởng order/time |
| 03 | A → B | Lặp lại |
| 04 | B → A | Lặp lại |
| 05 | Randomized | Kiểm tra ổn định |

Không bắt buộc dùng đúng 5 blocks. Số lần chạy cần được chọn theo mục tiêu precision, chi phí, mức dao động pilot và yêu cầu thống kê. **Ba lần chạy không phải một con số thần kỳ bảo đảm kết luận đúng.**

### 5.3. Randomize thứ tự case

Nếu provider load tăng dần theo thời gian, chạy toàn bộ case dễ trước rồi mới đến case khó có thể gây confounding. Nên:

1. randomize hoặc interleave case order trong mỗi run;
2. ghi seed dùng để tạo thứ tự;
3. giữ cùng chiến lược giữa các arms;
4. không dùng seed đó như bảo đảm model output giống nhau.

### 5.4. Warmup và cache

Nếu có warmup, xác định trước:

- warmup requests có nằm trong report không;
- cache được bật/tắt hay giữ trạng thái giống nhau;
- cold-start latency và warm latency có báo riêng không.

Không bỏ những request chậm đầu tiên sau khi thấy kết quả rồi mới gọi phần còn lại là benchmark.

## 6. Chọn số lần chạy và độ chính xác mong muốn

Không có một số run cố định phù hợp mọi model, dataset và chi phí.

### Pilot trước, thiết kế sau

Một quy trình thực tế:

1. Chọn một tập pilot đại diện cho nghiệp vụ và độ khó.
2. Chạy lặp để ước lượng biến động giữa các runs và giữa các lần sinh của cùng case.
3. Xác định **mức chênh lệch nhỏ nhất có ý nghĩa** với sản phẩm, ví dụ 2 điểm phần trăm.
4. Ước lượng số run/case cần thiết theo biến động và confidence interval mục tiêu.
5. Đăng ký số lần chạy, retry policy và stopping rule trước khi xem kết quả chính thức.

### Ước lượng sơ bộ cho trung bình run-level metric

Nếu có `R` run blocks độc lập tương đối và độ lệch chuẩn pilot của paired delta là `s`, sai số chuẩn của trung bình xấp xỉ:

\[
SE(\bar{\Delta})=\frac{s}{\sqrt{R}}.
\]

Một ước lượng thô số blocks để có half-width mục tiêu `d`:

\[
R \approx \left(\frac{z\,s}{d}\right)^2.
\]

Với confidence 95%, `z≈1.96` là xấp xỉ planning; khi R nhỏ nên dùng quantile t và thiết kế/power analysis phù hợp. Nếu run blocks có tự tương quan hoặc provider load theo thời gian, số mẫu hiệu dụng thấp hơn R.

**Công thức này không phải power analysis đầy đủ cho mọi repeated binary data.** Với PASS/FAIL trên cùng cases, cần tính đến clustering theo case, run block và missing verdict; có thể dùng hierarchical bootstrap hoặc mixed-effects model khi cần kết luận chính thức.

### Thực tế về chi phí

Nếu dataset có 500 case, 10 runs và mỗi case gọi generator + hai judges, số model calls có thể lên đến hàng chục nghìn. Cần lập ngân sách token, rate limit, quota và thời gian trước khi chạy.

## 7. Chỉ số cho mỗi run

Với mỗi run `r`, báo:

\[
P_r=\frac{PASS_r}{PASS_r+FAIL_r}
\]

\[
C_r=\frac{PASS_r+FAIL_r}{Eligible_r}
\]

Trong đó `P_r` là pass rate trên case có verdict hợp lệ; `C_r` là evaluation coverage. Báo riêng:

- generation error rate;
- tool error rate;
- evaluation error rate;
- skipped/missing rate;
- critical case count/rate;
- score histogram;
- latency, token usage và cost.

### Bảng run-level ví dụ

Giả sử mỗi run có 100 eligible cases:

| Run | PASS | FAIL | Eval error | Generation error | Coverage | Pass rate |
|---|---:|---:|---:|---:|---:|---:|
| R1 | 90 | 8 | 1 | 1 | 98% | 91,84% |
| R2 | 87 | 11 | 1 | 1 | 98% | 88,78% |
| R3 | 89 | 9 | 2 | 0 | 98% | 90,82% |
| R4 | 85 | 12 | 2 | 1 | 97% | 87,63% |
| R5 | 91 | 7 | 1 | 1 | 98% | 92,86% |

Mỗi run đều có tỷ lệ PASS khá cao, nhưng dao động gần 5,2 điểm phần trăm giữa min và max. Cần kiểm tra **run R4**: liệu đây là stochastic variation, lỗi provider, context drift hay một sự cố theo thời điểm?

Với các tỷ lệ đã làm tròn trong bảng, **mean run-level pass rate ≈ 90,38%**, **sample SD ≈ 2,16 điểm phần trăm**, **range ≈ 5,23 điểm phần trăm**. Pooled pass rate là `442/489 ≈ 90,39%` vì các run có 97–98 verdict hợp lệ. Hai cách tổng hợp gần nhau trong ví dụ này, nhưng vẫn phải báo đúng định nghĩa.

Không gộp eval errors vào FAIL; coverage và errors là guardrails riêng.

## 8. Mean qua runs và pooled pass rate là hai cách nhìn

### Mean run-level pass rate

\[
\bar P=\frac{1}{R}\sum_{r=1}^{R}P_r.
\]

Mỗi run có trọng số bằng nhau. Chỉ số này trả lời: **một run điển hình đạt bao nhiêu?**

### Pooled pass rate

\[
P_{\mathrm{pooled}}=
\frac{\sum_r PASS_r}{\sum_r(PASS_r+FAIL_r)}.
\]

Mỗi verdict hợp lệ có trọng số như nhau. Nếu run có số evaluated khác nhau, pooled rate có thể khác mean run-level.

### Ví dụ

| Run | PASS | FAIL | Pass rate |
|---|---:|---:|---:|
| R1 | 9 | 1 | 90% |
| R2 | 45 | 55 | 45% |

\[
\bar P=(90\%+45\%)/2=67.5\%.
\]

\[
P_{\mathrm{pooled}}=(9+45)/(10+100)=49.09\%.
\]

Hai số trả lời hai câu hỏi khác nhau. **Không được chọn cách tính sau khi thấy cách nào đẹp hơn.** Đăng ký trước metric chính và báo cả hai nếu có ích.

Khi mọi run có cùng case IDs và cùng số verdict hợp lệ, pooled rate bằng trung bình của pass rates run-level. Nếu coverage khác nhau, chúng có thể lệch; phải giải thích lý do.

## 9. Đo độ biến động giữa các runs

Với các pass rates `P_1,...,P_R`:

### Phương sai mẫu

\[
s_P^2=\frac{1}{R-1}\sum_{r=1}^{R}(P_r-\bar P)^2.
\]

### Độ lệch chuẩn mẫu

\[
s_P=\sqrt{s_P^2}.
\]

Đơn vị của `s_P` là điểm tỷ lệ; nhân 100 để biểu diễn điểm phần trăm. Độ lệch chuẩn lớn cho biết run-level result dao động mạnh.

### Range và interquartile range

- `Range = max(P_r) - min(P_r)`: khoảng dao động toàn bộ, nhạy với outlier.
- `IQR = P75 - P25`: độ rộng của 50% runs ở giữa.
- `Median`: trung tâm bền vững hơn mean khi có run bất thường.

Không nên chỉ báo min/max vì một run có outage có thể làm range rất lớn; hãy giữ run bất thường trong báo cáo và phân loại nguyên nhân thay vì xóa.

### Coefficient of variation

\[
CV=\frac{s_P}{\bar P}.
\]

CV có thể dùng khi mean khác 0 và thang đo ratio có ý nghĩa, nhưng với pass rate gần 0 hoặc các metric bị chặn trong [0,1], CV có thể khó diễn giải. Trong evaluation, **SD theo điểm phần trăm, IQR và khoảng tin cậy** thường dễ đọc hơn.

## 10. Biến động theo từng case: pass probability và verdict flips

Run-level mean không cho biết **case nào không ổn định**. Với case `i` chạy `R` lần, định nghĩa:

\[
\hat p_i=\frac{N_{i,\mathrm{PASS}}}
{N_{i,\mathrm{PASS}}+N_{i,\mathrm{FAIL}}}.
\]

`p̂_i` là tỷ lệ PASS quan sát được của case trong các lần có verdict hợp lệ. Ví dụ:

| Case | PASS | FAIL | Error | Pass probability |
|---|---:|---:|---:|---:|
| policy-easy-01 | 10 | 0 | 0 | 100% |
| policy-hard-04 | 6 | 4 | 0 | 60% |
| tool-medium-08 | 4 | 5 | 1 | 44,44% |
| rag-hard-12 | 2 | 8 | 0 | 20% |

Case policy-hard-04 có lúc đạt, lúc không đạt. Nó có thể là **flaky case** cần review evidence/prompt/judge. tool-medium-08 còn có error, nên pass probability phải đọc cùng coverage 9/10.

### Verdict flip rate

Nếu có thứ tự run đã định nghĩa, một case có thể chuyển PASS↔FAIL. Tỷ lệ flip trên các cặp run liền kề đều có verdict hợp lệ:

\[
FlipRate_i=
\frac{N_{\mathrm{adjacent\ verdict\ changes}}}
{N_{\mathrm{adjacent\ valid\ pairs}}}.
\]

Ví dụ chuỗi `PASS, PASS, FAIL, PASS, FAIL` có 4 cặp kề nhau, 3 lần đổi verdict:

\[
FlipRate=3/4=75\%.
\]

Nếu một run bị error giữa hai run, không tự xem hai verdict ở hai phía là **cặp liền kề**. Hãy ghi số cặp có thể so sánh và số bị thiếu.

### Majority agreement / stability

Một chỉ số mô tả khác:

\[
Stability_i=\frac{\max(N_{PASS},N_{FAIL})}
{N_{PASS}+N_{FAIL}}.
\]

Ví dụ 9 PASS, 1 FAIL → stability 90%; 5 PASS, 5 FAIL → 50%. Đây là **độ nhất quán theo đa số**, không phải accuracy. Một case luôn sai có stability 100% nhưng chất lượng vẫn 0%; do đó cần đọc cùng pass probability.

## 11. Biến động score khi dùng rubric nhiều mức

Với điểm ordinal 0–4, có thể lưu phân bố score cho từng case qua runs:

~~~text
Case A: 4, 4, 4, 4, 4
Case B: 4, 3, 4, 3, 4
Case C: 4, 1, 4, 0, 3
~~~

Ba case có thể có mean tương đối gần nhau nhưng độ biến động rất khác.

Nên báo:

- score count ở từng mức 0–4;
- median và IQR;
- mean/SD như thống kê bổ sung;
- số lần vượt/không vượt pass threshold;
- critical severity count và case IDs;
- judge agreement nếu nhiều lần chấm cùng output.

Vì score ordinal, không nên diễn giải variance như một đại lượng khoảng cách tuyệt đối. Nếu rubric đổi giữa runs, score series không còn cùng thang; cần rubric revision mới hoặc re-score snapshots bằng rubric chung.

## 12. Tách generator variance khỏi judge variance

Một cách chẩn đoán rất hữu ích:

### Thí nghiệm A — giữ answer cố định, chạy judge nhiều lần

1. Sinh answer một lần và lưu answer + evidence snapshot.
2. Chạy judge J cùng rubric nhiều lần trên **chính answer/evidence ấy**.
3. Đếm verdict flips, score distribution, judge error rate.

Nếu verdict đổi nhiều, **evaluator không ổn định**. Cần hiệu chuẩn prompt/model hoặc thêm human review trước khi dùng nó làm release gate.

### Thí nghiệm B — giữ input cố định, sinh answer nhiều lần

1. Cố định question, context, tool fixtures và generator config.
2. Sinh nhiều answer độc lập, mỗi lần có attempt ID.
3. Chấm bằng cùng một judge policy (có thể dùng nhiều judges/human calibration nếu cần).
4. Đo pass probability, score distribution và critical failure frequency.

Nếu judge ổn định trên cùng answer nhưng answer khác nhau qua generation repeats, nguồn biến động chủ yếu nằm ở generator hoặc upstream pipeline.

### Ma trận chẩn đoán

| Generator output | Judge verdict | Diễn giải |
|---|---|---|
| Giống nhau | Giống nhau | Repeatable trong quan sát này |
| Khác nhau | Giống nhau | Answer có khác biệt nhưng chưa đổi outcome theo rubric |
| Giống nhau | Khác nhau | Judge/evaluation variance |
| Khác nhau | Khác nhau | Generator variance, có thể kèm judge variance |

Để kết luận mạnh hơn, cần lưu rendered prompt, evidence, raw answer được phép, judge prompt/version và assessment output. Nếu chỉ lưu pass/fail thì khó tách nguồn.

## 13. Drift theo thời gian khác stochastic variation

**Variation** là dao động quanh mức tương đối ổn định; **drift** là thay đổi có hệ thống theo thời gian.

Ví dụ:

| Tuần | Pass rate | Corpus | Requested model | Ghi chú |
|---|---:|---|---|---|
| W1 | 91% | corpus-v7 | model-alias-X | Baseline |
| W2 | 90% | corpus-v7 | model-alias-X | Trong dao động pilot |
| W3 | 87% | corpus-v8 | model-alias-X | Corpus update |
| W4 | 84% | corpus-v8 | model-alias-X | Provider thông báo deployment update |

Không thể quy mọi thay đổi cho model alias. Cần đối chiếu manifests, corpus/index, labels, provider metadata và evaluation policy.

### Dấu hiệu variation

- run-level values lên xuống nhưng không có xu hướng rõ;
- cùng điều kiện, cùng case có lúc PASS/FAIL;
- các biến động không đồng bộ với một revision cụ thể;
- SD/IQR tương đối ổn định qua thời gian.

### Dấu hiệu drift

- moving average giảm/tăng kéo dài;
- cùng case/slice ngày càng FAIL;
- thay đổi trùng với corpus, prompt, model deployment hoặc judge revision;
- phân bố retrieval IDs, token usage hoặc latency chuyển dịch có hệ thống.

Không kết luận drift từ hai điểm thời gian đơn lẻ. Cần đủ run history, kiểm soát seasonality/provider load và xác định change points nếu có.

## 14. Thiết kế A/B repeated runs bằng run blocks

Khi so hai variants A và B, tạo các **block ghép cặp theo thời gian**:

| Block | A | B | Delta |
|---|---:|---:|---:|
| 01 | 90% | 92% | +2 pp |
| 02 | 88% | 91% | +3 pp |
| 03 | 91% | 92% | +1 pp |
| 04 | 87% | 89% | +2 pp |
| 05 | 90% | 91% | +1 pp |

Mỗi block nên:

- dùng cùng dataset, labels, scoring policy;
- chạy A và B gần nhau về thời gian;
- randomize thứ tự A/B;
- dùng cùng concurrency/timeout/retry budgets;
- lưu từng run manifest và case results;
- ghi các yếu tố không thể giữ cố định.

### Delta theo block

\[
\Delta_b=P_{B,b}-P_{A,b}.
\]

Trung bình paired delta:

\[
\bar{\Delta}=\frac{1}{B}\sum_{b=1}^{B}\Delta_b.
\]

Độ lệch chuẩn của paired deltas phản ánh **độ biến động giữa các blocks**. Confidence interval t đơn giản có thể dùng nếu blocks đủ độc lập và assumptions phù hợp:

\[
\bar{\Delta}\pm t_{B-1,\,1-\alpha/2}
\frac{s_\Delta}{\sqrt B}.
\]

Đây là CI trên **run-block deltas**, không phải CI đầy đủ cho mọi case trong quần thể. Nếu cần inference nghiêm ngặt, dùng hierarchical/cluster bootstrap hoặc mô hình phù hợp với repeated binary outcomes.

### Đừng giả vờ có pairing khi runs không đồng thời

Nếu A chạy tuần này và B chạy tuần sau, provider/backend/time window có thể khác. Có thể so sánh descriptive nhưng phải gọi là **unpaired temporal comparison** hoặc observational comparison, không gán paired delta cho hai run không có block tương ứng.

## 15. Bootstrap đúng cấu trúc repeated data

Một bộ dữ liệu có thể có 100 case × 5 runs = 500 verdicts. Không nên mặc định 500 verdicts là 500 quan sát độc lập:

- cùng case lặp qua 5 runs tạo phụ thuộc theo case;
- nhiều case trong cùng run cùng chịu provider load/incident;
- cùng tài liệu có thể tạo nhiều câu hỏi tương quan.

### Hierarchical bootstrap khái niệm

1. Lấy mẫu lại **case IDs** (hoặc document/topic clusters nếu cases phụ thuộc).
2. Với mỗi case được chọn, giữ toàn bộ các lần lặp A/B tương ứng để bảo toàn pairing.
3. Nếu cần mô hình hóa run-level shocks, lấy mẫu lại **run blocks** như một tầng.
4. Tính lại metric/paired delta ở mỗi bootstrap replicate.
5. Lấy interval và ghi rõ resampling unit, số lần lặp và seed.

Nếu mục tiêu chỉ mô tả **dao động giữa run-level pass rates**, bootstrap trên run blocks có thể phù hợp hơn. Nếu mục tiêu tổng quát hóa qua **các case mới**, cần resample case IDs. Đừng dùng một bootstrap duy nhất cho mọi câu hỏi.

### Khi nào cần mô hình thống kê nâng cao?

- PASS/FAIL lặp trên case: logistic mixed-effects model có random effects theo case/run nếu cần tách nguồn variance.
- Score ordinal: ordinal mixed model hoặc thống kê mô tả/paired rank methods phù hợp.
- Nhiều nhóm và nhiều lần chạy: hierarchical model để tránh coi mỗi slice là độc lập hoàn toàn.
- Ít run, nhiều case: ước lượng run-level variance còn yếu; tăng số blocks hoặc chỉ báo descriptive.

Các mô hình này cần người có chuyên môn thống kê chọn và kiểm tra assumptions; không cần đưa vào mọi bài regression hằng ngày.

## 16. Java 21: tổng hợp repeated results theo case và run

Ví dụ lớp Java thuần JDK nhận một result cho mỗi `run_id + case_id`. Nó tính:

- run-level pass rate và coverage;
- pass/fail/error counts;
- pass probability theo case;
- verdict flip rate giữa các run liền kề có verdict;
- majority agreement;
- score mean và sample standard deviation (chỉ là thống kê bổ sung trên ordinal scale).

### File `RepeatedRunSummary.java`

~~~java
package com.example.aiquality.repeatability;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.Set;

public final class RepeatedRunSummary {
    private RepeatedRunSummary() {}

    public enum Outcome {
        PASS, FAIL, GENERATION_ERROR, EVALUATION_ERROR, SKIPPED
    }

    public enum Severity {
        NONE, MINOR, MAJOR, CRITICAL
    }

    public record Observation(
            String runId,
            String caseId,
            Outcome outcome,
            Integer score,
            Severity severity) {}

    public record RunSummary(
            String runId,
            int eligible,
            int received,
            int evaluated,
            int passed,
            int failed,
            int criticalCases,
            int generationErrors,
            int evaluationErrors,
            int skipped,
            int missing) {

        public OptionalDouble passRate() {
            return ratio(passed, evaluated);
        }

        public OptionalDouble coverage() {
            return ratio(evaluated, eligible);
        }
    }

    public record CaseStability(
            String caseId,
            int plannedRuns,
            int evaluatedRuns,
            int passed,
            int failed,
            int criticalRuns,
            int generationErrors,
            int evaluationErrors,
            int skipped,
            int missingRuns,
            OptionalDouble passProbability,
            OptionalDouble majorityAgreement,
            OptionalDouble criticalFrequency,
            int adjacentPairs,
            int verdictFlips,
            OptionalDouble flipRate,
            OptionalDouble meanScore,
            OptionalDouble scoreStdDev) {}

    public record Report(
            List<RunSummary> runs,
            List<CaseStability> cases) {}

    public static Report summarize(
            List<String> orderedRunIds,
            Set<String> expectedCaseIds,
            List<Observation> observations) {

        if (orderedRunIds == null || orderedRunIds.isEmpty()
                || expectedCaseIds == null || expectedCaseIds.isEmpty()
                || observations == null) {
            throw new IllegalArgumentException("Thiếu run/case/observations");
        }

        Set<String> runSet = new HashSet<>(orderedRunIds);
        if (runSet.size() != orderedRunIds.size()
                || runSet.contains(null) || runSet.contains("")) {
            throw new IllegalArgumentException("Run IDs trùng hoặc rỗng");
        }
        if (expectedCaseIds.contains(null)
                || expectedCaseIds.contains("")) {
            throw new IllegalArgumentException("Case ID rỗng");
        }

        Map<String, Map<String, Observation>> byRun = new LinkedHashMap<>();
        for (String runId : orderedRunIds) {
            byRun.put(runId, new HashMap<>());
        }

        for (Observation row : observations) {
            if (row == null || row.runId() == null || row.caseId() == null
                    || row.outcome() == null
                    || !runSet.contains(row.runId())
                    || !expectedCaseIds.contains(row.caseId())) {
                throw new IllegalArgumentException(
                    "Observation có runId/caseId/outcome không hợp lệ");
            }
            if (row.outcome() == Outcome.PASS
                    || row.outcome() == Outcome.FAIL) {
                if (row.score() == null || row.score() < 0 || row.score() > 4) {
                    throw new IllegalArgumentException(
                        "PASS/FAIL phải có score trong khoảng 0..4");
                }
                if (row.severity() == null) {
                    throw new IllegalArgumentException(
                        "Verdict hợp lệ phải có severity");
                }
                if (row.outcome() == Outcome.PASS
                        && row.severity() == Severity.CRITICAL) {
                    throw new IllegalArgumentException(
                        "Critical failure không thể đồng thời là PASS");
                }
            } else if (row.score() != null || row.severity() != null) {
                throw new IllegalArgumentException(
                    "Error/Skipped không được có score/severity");
            }

            Observation previous = byRun.get(row.runId())
                    .putIfAbsent(row.caseId(), row);
            if (previous != null) {
                throw new IllegalArgumentException(
                    "Trùng runId + caseId: " + row.runId()
                    + "/" + row.caseId());
            }
        }

        List<RunSummary> runSummaries = new ArrayList<>();
        for (String runId : orderedRunIds) {
            Map<String, Observation> rows = byRun.get(runId);
            int pass = 0, fail = 0, critical = 0;
            int gen = 0, eval = 0, skipped = 0;

            for (Observation row : rows.values()) {
                switch (row.outcome()) {
                    case PASS -> {
                        pass++;
                        if (row.severity() == Severity.CRITICAL) critical++;
                    }
                    case FAIL -> {
                        fail++;
                        if (row.severity() == Severity.CRITICAL) critical++;
                    }
                    case GENERATION_ERROR -> gen++;
                    case EVALUATION_ERROR -> eval++;
                    case SKIPPED -> skipped++;
                }
            }
            int received = rows.size();
            int missing = expectedCaseIds.size() - received;
            runSummaries.add(new RunSummary(
                runId, expectedCaseIds.size(), received,
                pass + fail, pass, fail, critical, gen, eval, skipped, missing));
        }

        List<CaseStability> caseSummaries = new ArrayList<>();
        for (String caseId : expectedCaseIds) {
            List<Observation> sequence = new ArrayList<>();
            for (String runId : orderedRunIds) {
                Observation row = byRun.get(runId).get(caseId);
                if (row != null) sequence.add(row);
            }
            caseSummaries.add(summarizeCase(caseId, sequence, orderedRunIds));
        }
        caseSummaries.sort(Comparator.comparing(CaseStability::caseId));

        return new Report(List.copyOf(runSummaries),
                List.copyOf(caseSummaries));
    }

    private static CaseStability summarizeCase(
            String caseId,
            List<Observation> sequence,
            List<String> orderedRunIds) {

        int pass = 0, fail = 0, critical = 0;
        int gen = 0, eval = 0, skipped = 0;
        List<Integer> scores = new ArrayList<>();
        Map<String, Observation> byRun = new HashMap<>();
        for (Observation row : sequence) {
            byRun.put(row.runId(), row);
            switch (row.outcome()) {
                case PASS -> {
                    pass++;
                    scores.add(row.score());
                    if (row.severity() == Severity.CRITICAL) critical++;
                }
                case FAIL -> {
                    fail++;
                    scores.add(row.score());
                    if (row.severity() == Severity.CRITICAL) critical++;
                }
                case GENERATION_ERROR -> gen++;
                case EVALUATION_ERROR -> eval++;
                case SKIPPED -> skipped++;
            }
        }

        int adjacentPairs = 0;
        int flips = 0;
        for (int i = 1; i < orderedRunIds.size(); i++) {
            Observation previous = byRun.get(orderedRunIds.get(i - 1));
            Observation current = byRun.get(orderedRunIds.get(i));
            if (isVerdict(previous) && isVerdict(current)) {
                adjacentPairs++;
                if (previous.outcome() != current.outcome()) flips++;
            }
        }

        int evaluated = pass + fail;
        OptionalDouble passProbability = ratio(pass, evaluated);
        OptionalDouble majority = evaluated == 0 ? OptionalDouble.empty()
                : OptionalDouble.of((double) Math.max(pass, fail) / evaluated);
        OptionalDouble criticalFrequency = ratio(critical, evaluated);
        OptionalDouble flipRate = ratio(flips, adjacentPairs);

        OptionalDouble mean = OptionalDouble.empty();
        OptionalDouble stdDev = OptionalDouble.empty();
        if (!scores.isEmpty()) {
            double average = scores.stream().mapToInt(Integer::intValue)
                    .average().orElseThrow();
            mean = OptionalDouble.of(average);
            if (scores.size() > 1) {
                double sumSquares = scores.stream()
                        .mapToDouble(score -> Math.pow(score - average, 2))
                        .sum();
                stdDev = OptionalDouble.of(
                    Math.sqrt(sumSquares / (scores.size() - 1)));
            }
        }

        return new CaseStability(
            caseId, orderedRunIds.size(), sequence.size(), evaluated,
            pass, fail, critical, gen, eval, skipped,
            orderedRunIds.size() - sequence.size(),
            passProbability, majority, criticalFrequency,
            adjacentPairs, flips, flipRate, mean, stdDev);
    }

    private static boolean isVerdict(Observation row) {
        return row != null && (row.outcome() == Outcome.PASS
                || row.outcome() == Outcome.FAIL);
    }

    private static OptionalDouble ratio(int numerator, int denominator) {
        return denominator == 0 ? OptionalDouble.empty()
                : OptionalDouble.of(numerator / (double) denominator);
    }
}
~~~

### Cách đọc output

- `RunSummary.passRate` chỉ tính PASS/(PASS+FAIL), không tính errors.
- `RunSummary.coverage` tính verdict hợp lệ/eligible.
- `RunSummary.criticalCases` và `CaseStability.criticalRuns` đếm case/run có severity cao nhất là CRITICAL; aggregator giả định critical veto, nên một observation CRITICAL không thể mang verdict PASS.
- `CaseStability.passProbability` là **tỷ lệ PASS quan sát được** trong các run có verdict, không phải xác suất đã được hiệu chuẩn cho mọi lần chạy tương lai.
- `majorityAgreement` là tỷ lệ verdict theo phía chiếm đa số, **không phải accuracy**.
- `criticalFrequency` là tỷ lệ run có critical trên số run có verdict hợp lệ; cần đọc cùng coverage.
- `flipRate` chỉ xét hai run **liền kề theo thứ tự đã đăng ký** và cả hai có verdict. Một error/missing làm cặp liền kề đó không được tính.
- `scoreStdDev` là sample SD mô tả trên thang ordinal 0–4; đọc cùng histogram và rubric.

Ví dụ này coi danh sách `orderedRunIds` là thứ tự thời gian đã xác định. Nếu runs không theo thời gian, không diễn giải flip rate như xu hướng temporal.

## 17. JUnit 5: kiểm tra repeated runs và flaky cases

### File `RepeatedRunSummaryTest.java`

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import com.example.aiquality.repeatability.RepeatedRunSummary;
import com.example.aiquality.repeatability.RepeatedRunSummary.*;

class RepeatedRunSummaryTest {

    @Test
    void calculatesRunCoverageAndCaseFlipRate() {
        var observations = List.of(
            new Observation("r1", "case-a", Outcome.PASS, 4, Severity.NONE),
            new Observation("r2", "case-a", Outcome.FAIL, 2, Severity.NONE),
            new Observation("r3", "case-a", Outcome.PASS, 4, Severity.NONE),
            new Observation("r1", "case-b", Outcome.FAIL, 1, Severity.NONE),
            new Observation("r2", "case-b",
                    Outcome.EVALUATION_ERROR, null, null),
            new Observation("r3", "case-b", Outcome.FAIL, 1, Severity.NONE));

        var report = RepeatedRunSummary.summarize(
            List.of("r1", "r2", "r3"),
            Set.of("case-a", "case-b"),
            observations);

        var run2 = report.runs().get(1);
        assertEquals(2, run2.eligible());
        assertEquals(1, run2.evaluated());
        assertEquals(0.5, run2.coverage().orElseThrow(), 0.000001);

        var caseA = report.cases().stream()
                .filter(row -> row.caseId().equals("case-a"))
                .findFirst().orElseThrow();
        assertEquals(2.0 / 3.0,
                caseA.passProbability().orElseThrow(), 0.000001);
        assertEquals(1.0,
                caseA.flipRate().orElseThrow(), 0.000001);
    }

    @Test
    void missingRowsReduceCoverageButAreNotFailures() {
        var report = RepeatedRunSummary.summarize(
            List.of("r1", "r2"),
            Set.of("case-a", "case-b"),
            List.of(new Observation(
                "r1", "case-a", Outcome.PASS, 4, Severity.NONE)));

        assertEquals(1, report.runs().get(0).missing());
        assertEquals(2, report.runs().get(1).missing());
        assertEquals(0, report.runs().get(1).failed());
    }

    @Test
    void rejectsDuplicateRunCasePair() {
        assertThrows(IllegalArgumentException.class, () ->
            RepeatedRunSummary.summarize(
                List.of("r1"), Set.of("case-a"),
                List.of(
                    new Observation("r1", "case-a", Outcome.PASS, 4, Severity.NONE),
                    new Observation("r1", "case-a", Outcome.FAIL, 1, Severity.NONE))));
    }

    @Test
    void tracksCriticalFrequencyAcrossRepeatedRuns() {
        var report = RepeatedRunSummary.summarize(
            List.of("r1", "r2", "r3"),
            Set.of("case-a"),
            List.of(
                new Observation("r1", "case-a", Outcome.PASS, 4, Severity.NONE),
                new Observation("r2", "case-a", Outcome.FAIL, 0, Severity.CRITICAL),
                new Observation("r3", "case-a", Outcome.PASS, 4, Severity.NONE)));

        var caseA = report.cases().getFirst();
        assertEquals(1, caseA.criticalRuns());
        assertEquals(1.0 / 3.0,
                caseA.criticalFrequency().orElseThrow(), 0.000001);
        assertEquals(1, report.runs().get(1).criticalCases());
    }

    @Test
    void criticalSeverityCannotBeReportedAsPass() {
        assertThrows(IllegalArgumentException.class, () ->
            RepeatedRunSummary.summarize(
                List.of("r1"), Set.of("case-a"),
                List.of(new Observation(
                    "r1", "case-a", Outcome.PASS, 4, Severity.CRITICAL))));
    }
}
~~~

Đây là **code hướng dẫn**, chưa được build hoặc chạy trong phạm vi viết bài. Người học cần tạo project Java 21 có JUnit 5, đặt đúng package và chạy test. Trong hệ thống thực, cần mở rộng để lưu dataset revision, arm, metric eligibility, severity, attempt policy và expected run/case manifests.

## 18. So sánh hai arm qua nhiều run blocks

Một thí nghiệm A/B repeated có thể lưu:

~~~yaml
experiment_id: "generator-repeatability-001"
dataset:
  id: "vi-rag-regression"
  revision: "v5"
  digest: "sha256:actual-dataset-digest"
planned_run_blocks: 5
arms:
  A:
    prompt_revision: "answer-v3"
    requested_model_id: "model-X"
  B:
    prompt_revision: "answer-v4"
    requested_model_id: "model-X"
fixed:
  judge_model: "judge-Y"
  rubric_revision: "fact-check-v2"
  corpus_revision: "policy-corpus-v8"
  index_revision: "index-v12"
  retrieval_mode: "frozen-context"
  concurrency: 2
  timeout_seconds: 40
  retry_policy_revision: "retry-v1"
~~~

Mỗi block có hai run manifests, một cho A và một cho B. Các trường ví dụ cần được điền bằng metadata thật; không lưu secret values.

### Report paired delta theo block

~~~json
{
  "experimentId": "generator-repeatability-001",
  "metric": "fact_check_pass_rate",
  "blocks": [
    {"blockId":"b01","a":0.90,"b":0.92,"deltaPp":2.0},
    {"blockId":"b02","a":0.88,"b":0.91,"deltaPp":3.0},
    {"blockId":"b03","a":0.91,"b":0.92,"deltaPp":1.0},
    {"blockId":"b04","a":0.87,"b":0.89,"deltaPp":2.0},
    {"blockId":"b05","a":0.90,"b":0.91,"deltaPp":1.0}
  ],
  "meanDeltaPp": 1.8,
  "runBlockCount": 5
}
~~~

Các giá trị là ví dụ giả lập. Nếu mỗi block có case coverage khác nhau, cần quyết định trước dùng **paired case set trong block**, pooled per-block rate hay metric khác. Không tự tính delta từ hai run có denominator/eligibility khác nhau.

### Tách hai nguồn bất định

- **Between-run uncertainty:** kết quả có dao động theo thời điểm/provider run block không?
- **Across-case uncertainty:** kết quả có tổng quát hóa sang những tình huống khác trong quần thể mục tiêu không?

Chỉ có nhiều runs trên cùng 10 cases sẽ ước lượng độ lặp lại của 10 cases đó khá hơn, nhưng **không tự tạo ra 100 tình huống mới độc lập**. Muốn khái quát qua case population, cần đủ case đại diện.

## 19. Phát hiện flaky cases và ưu tiên điều tra

Một quy tắc sàng lọc đơn giản có thể dùng pass probability:

| Pass probability quan sát | Nhãn chẩn đoán minh họa |
|---:|---|
| `p̂ ≥ 0.9` | Stable pass candidate |
| `0.1 < p̂ < 0.9` | Potentially flaky / mixed outcome |
| `p̂ ≤ 0.1` | Stable fail candidate |

Đây là **heuristic nội bộ**, không phải chuẩn chung. Với ít runs, 1/1 PASS cho `p̂=100%` không đủ chứng minh ổn định. Luôn ghi số run, coverage, CI hoặc uncertainty.

### Ưu tiên review

Ưu tiên cao khi một case:

- có critical failure dù chỉ một lần;
- thường xuyên chuyển PASS↔FAIL;
- nằm trong business/risk slice quan trọng;
- có evidence/tool output thay đổi bất ngờ;
- có judge disagreement hoặc evaluation errors lặp lại.

**Một critical failure hiếm vẫn có thể là release blocker.** Không được dùng tỷ lệ trung bình để che một sự cố nghiêm trọng.

### Flaky không nhất thiết là model sampling

Kiểm tra theo thứ tự:

1. question/prompt/context digest có giống nhau không?
2. retrieved document IDs và tool fixtures có giống nhau không?
3. requested/resolved model và request options có đổi không?
4. generator output có khác, hay chỉ judge verdict khác?
5. có timeout, retries, 429/5xx hoặc sampling trace không?
6. có concurrency/queue/cache/time-of-day effect không?

## 20. Quan sát latency, token và cost qua nhiều lần chạy

Với mỗi run, lưu:

- generator p50/p95 latency;
- retrieval, embedding, vector DB và tool latency;
- judge latency riêng;
- input/output/cached/reasoning tokens khi provider báo;
- retry count và error codes;
- actual cost theo rate card thời điểm chạy;
- normalized cost nếu tính lại trên cùng rate card.

### So latency qua runs

Nếu run R1 có p95 1,2 giây và R5 có p95 2,8 giây, cần xem histogram/trace và sample size. Không kết luận chỉ dựa trên hai quantile:

- p95 từ 20 requests rất bất ổn;
- một outage/provider overload có thể tạo tail;
- judge offline không được cộng vào user-facing latency;
- span cha có thể bao gồm span con, không cộng hai lần.

### So token và chi phí

\[
C_{\mathrm{model}}=
\frac{T_{\mathrm{input}}}{10^6}P_{\mathrm{input}}
+\frac{T_{\mathrm{output}}}{10^6}P_{\mathrm{output}}.
\]

Tổng cost/case cần cộng các calls thực tế: generator, judge(s), embedding nếu tính trong scope và tool/provider fees nếu có. Không cộng `input`, `output` và `total` đồng thời; không coi usage missing là zero.

Nếu rate card thay đổi theo thời gian, báo:

1. **Actual spend** để hiểu hóa đơn thực tế.
2. **Normalized cost** với cùng bảng giá nếu muốn so mức tiêu thụ tài nguyên.

## 21. Metrics và traces trong Spring AI

Spring AI dùng Micrometer Observation/Tracing để ghi nhận hoạt động khi các thành phần tương ứng được gọi. Một số observation/metric logic thường gặp:

| Tín hiệu | Dùng trong repeated-run analysis |
|---|---|
| `spring.ai.chat.client` | Duration ChatClient/advisors |
| `spring.ai.advisor` | Thời gian từng advisor |
| `gen_ai.client.operation` | ChatModel/EmbeddingModel operation duration |
| `gen_ai.client.token.usage` | Input/output token usage |
| `db.vector.client.operation` | VectorStore operations |
| `spring.ai.tool` | Tool execution/errors |
| `app.ai.evaluation.run` (custom) | Số liệu tổng hợp theo run/block |
| `app.ai.evaluation.case` (custom) | Duration/outcome theo case, nếu cardinality policy cho phép ở metrics |

### Metric labels cardinality thấp

Có thể dùng `environment`, `arm`, `role`, `scenario` và `outcome` có giá trị đóng. Không dùng `run_id`, `case_id`, user ID, raw prompt hay document ID làm Prometheus labels.

Run/case IDs nên nằm trong report store có phân quyền và có thể được dùng làm trace attributes theo policy. Traces có sampling/retention, nên không thay thế manifest và case result.

### Gắn run context

Runner có thể gắn run block và arm vào observation context nếu instrumentation hỗ trợ. Không giả định Spring AI tự tạo dimension `run_block_id` hoặc `arm`; cần bổ sung ở tầng ứng dụng. Giữ các giá trị metric labels trong tập hữu hạn để tránh cardinality explosion.

## 22. Quality gate cho biến động và critical failures

Một policy mẫu:

~~~yaml
repeatability_gate:
  revision: "repeatability-v2"
  minimum_run_blocks: 5
  minimum_case_coverage_per_run: 0.98
  maximum_run_pass_rate_sd_pp: 2.0
  maximum_case_flip_rate: 0.10
  maximum_generation_error_rate: 0.02
  maximum_evaluation_error_rate: 0.01
  critical_failure:
    maximum_unique_cases: 0
    any_critical_blocks_release: true
  operational:
    maximum_generator_p95_ms: 3000
    maximum_normalized_cost_per_case_usd: 0.03
  small_sample_action: "INCONCLUSIVE"
~~~

Các ngưỡng này **chỉ là ví dụ**, không phải default của Spring AI. Phải hiệu chuẩn theo baseline/pilot, sample size, business risk, model provider và ngân sách. Không lấy một mức SD 2 pp áp cho mọi dataset.

### Ba trạng thái quyết định

| Quyết định | Khi nào |
|---|---|
| `PROMOTE` | Đạt quality/operational gates, đủ runs/coverage, không có critical veto và biến động trong giới hạn |
| `REJECT` | Có regression chất lượng rõ, critical failure hoặc operational budget bị vi phạm |
| `INCONCLUSIVE/BLOCKED` | Thiếu run/coverage, judge không ổn định, manifest mismatch hoặc độ bất định quá lớn |

**Measurement gate phải được kiểm tra trước quality gate.** Nếu 30% case không có verdict, không nên gọi candidate thua về nội dung; kết quả cần BLOCKED/INCONCLUSIVE cho tới khi sửa phép đo.

## 23. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Chạy một lần rồi kết luận | Không thấy variation | Repeated runs và per-case stability |
| Gọi temperature=0 là deterministic | Hosted serving vẫn có thể đổi | Ghi metadata và đo thực nghiệm |
| Gộp generator và judge repeats | Không biết tầng nào biến động | Re-score frozen answers riêng |
| Đếm N×R verdicts độc lập | Các lần chạy cùng case phụ thuộc nhau | Case/run-block aware analysis |
| Xóa run xấu vì “outlier” | Che outage/drift thật | Giữ lại, phân loại nguyên nhân |
| Retry ghi đè kết quả đầu | Mất bằng chứng flaky/error | Mỗi attempt có ID riêng |
| So A tuần này với B tuần sau như paired | Time/provider confounding | Run blocks/interleaving |
| Chỉ báo mean pass rate | Che SD, IQR và flaky cases | Report mean, spread, CI, case stability |
| Bỏ error khỏi coverage | Candidate có vẻ ổn định giả tạo | Report error rates/coverage |
| Dùng pass probability làm accuracy | Tính lặp lại không phải correctness | Đọc cùng ground truth/human labels |
| Đếm critical incidents như unique cases | Double count case | Báo case count và incident count riêng |
| Không lưu context/tool outputs | Không truy nguyên biến động upstream | Execution snapshots có kiểm soát |
| Dùng run_id làm metric label | Cardinality tăng rất nhanh | Report store/trace reference |
| Coi 5 runs là đủ cho mọi bài toán | Không có số run phổ quát | Pilot, precision/power, assumptions |

## 24. Bài thực hành có hướng dẫn

### Bài A — Tạo repeated-run dataset

1. Chọn 20–50 cases tổng hợp gồm RAG, tool và no-context.
2. Khóa dataset revision, prompt, model ID/options, rubric và fixtures.
3. Chạy 5 run độc lập hoặc dùng fixture generator tạo chuỗi kết quả giả lập.
4. Mỗi record lưu `run_id`, `case_id`, attempt, status, score và evidence reference.
5. Không ghi đè retries; phân biệt generator và judge errors.

**Tiêu chí đạt:** có thể tái dựng run order và biết chính xác case nào thiếu verdict.

### Bài B — Tính stability theo case

Dùng các chuỗi:

- case A: PASS, PASS, PASS, PASS, PASS;
- case B: PASS, FAIL, PASS, FAIL, PASS;
- case C: FAIL, FAIL, FAIL, FAIL, FAIL;
- case D: PASS, EVALUATION_ERROR, PASS, FAIL, PASS.

Tính pass probability, majority agreement, adjacent pairs và flip rate. Giải thích vì sao case C ổn định nhưng vẫn sai, còn case D phải đọc cùng coverage.

### Bài C — Tách generator và judge variance

1. Sinh 10 answer snapshots cho cùng một question/context.
2. Chấm mỗi snapshot 3 lần bằng cùng judge/rubric.
3. Tạo ma trận answer × judge attempts.
4. So variation giữa answers và verdict variation trên cùng answer.
5. Lấy mẫu các bất đồng để human review.

**Tiêu chí đạt:** chỉ ra nguồn biến động chủ yếu nằm ở generator, judge hay cả hai.

### Bài D — A/B theo 5 run blocks

1. Khóa dataset và evaluation policy.
2. Mỗi block chạy cả A và B trong cùng time window, randomize thứ tự.
3. Tính run-level pass rate/coverage và delta theo block.
4. Tính mean delta, SD và CI phù hợp; cảnh báo nếu số blocks ít.
5. Phân tích các case flip và critical failures.

### Bài E — Điều tra drift

Tạo timeline giả lập có pass rate giảm sau corpus update và provider deployment update. Đối chiếu run manifests, retrieved IDs, model metadata, traces và token/latency. Viết kết luận phân biệt **correlation** với nguyên nhân đã chứng minh.

### Câu hỏi tự kiểm tra

1. Vì sao một run không đủ mô tả chất lượng?
2. Temperature=0 có bảo đảm hosted LLM trả cùng answer không?
3. Repeatability khác reproducibility như thế nào?
4. Vì sao cần tách generation repeats và judge repeats?
5. Pass probability 100% trên một run chứng minh điều gì?
6. Vì sao N cases × R runs không mặc định là N×R quan sát độc lập?
7. Run blocks giúp giảm loại confounding nào?
8. Flip rate có tính cặp có một run error không?
9. Khi nào variation trở thành dấu hiệu drift?
10. Vì sao một critical failure hiếm vẫn có thể chặn release?

**Gợi ý:** (1) chưa ước lượng variation; (2) không; (3) lặp lại cùng điều kiện so với khả năng nhóm khác tái tạo quy trình; (4) để tách hai nguồn; (5) chỉ một quan sát; (6) cùng case và run có phụ thuộc; (7) time/provider load và order; (8) không, chỉ cặp liền kề có verdict; (9) có xu hướng hệ thống và liên hệ thay đổi; (10) hậu quả nghiêm trọng không được bù bởi trung bình.

## 25. Checklist trước khi công bố repeatability report

- [ ] Experiment plan ghi giả thuyết, metric chính, run count và stopping rule.
- [ ] Dataset, labels, prompt, judge/rubric và corpus/index revisions được khóa theo mục tiêu.
- [ ] Mỗi lần chạy có run_id riêng; run blocks có thứ tự và timestamp.
- [ ] Attempts/retries không ghi đè nhau.
- [ ] Generator variance và judge variance được phân biệt.
- [ ] Mỗi run có pass rate, coverage, error rates và critical counts.
- [ ] Báo mean run-level và pooled rate với định nghĩa rõ.
- [ ] Báo SD/IQR/range hoặc interval để mô tả variation.
- [ ] Có per-case pass probability, flip rate và coverage.
- [ ] Không gọi stability là accuracy; kiểm tra bằng ground truth/human review.
- [ ] A/B được interleave/randomize trong run blocks khi cần so sánh paired.
- [ ] Bootstrap/CI tôn trọng cấu trúc case/run block.
- [ ] Không coi N×R verdicts là độc lập nếu cùng case được chạy lại.
- [ ] Drift được phân biệt với dao động ngẫu nhiên và có manifest diff.
- [ ] Critical failures có hard veto theo policy.
- [ ] Metrics/traces/latency/token/cost được ghi theo role và run policy.
- [ ] Không đưa run_id/case_id/PII/secrets vào metric labels.
- [ ] Report giữ artifacts, snapshots, judge metadata và limitations.
- [ ] Quyết định PROMOTE/REJECT/INCONCLUSIVE/BLOCKED có bằng chứng.

## Tài liệu tham khảo

1. [Spring AI — Evaluation](https://docs.spring.io/spring-ai/reference/api/testing.html): `Evaluator`, `EvaluationRequest` và đánh giá câu trả lời.
2. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient, ChatModel, VectorStore, tool observations và tracing.
3. [Spring AI 2.1 — Metrics](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/observability/metrics.html): operation metrics và token usage.
4. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer counters, timers và histograms.
5. [NIST Engineering Statistics Handbook](https://www.itl.nist.gov/div898/handbook/): thống kê mô tả, variance, sampling và confidence intervals.
6. [NIST — Measurement Process Characterization](https://www.itl.nist.gov/div898/handbook/mpc/mpc.htm): đánh giá biến động và hệ thống đo lường.
7. [SciPy — Bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html): nguyên lý bootstrap confidence intervals.
8. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): percentile latency và histogram buckets.
9. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm trong log/telemetry.

> **Ghi nhớ:** Một kết quả evaluation không phải một con số cố định. Hãy chạy lặp trong điều kiện được ghi lại, lưu từng attempt, đo biến động theo run và theo case, tách generator khỏi judge, rồi phân biệt **dao động ngẫu nhiên** với **drift có hệ thống**. Chỉ khi coverage, độ ổn định, critical failures, latency và chi phí cùng đạt policy, nhóm mới có đủ bằng chứng để quyết định phát hành.
