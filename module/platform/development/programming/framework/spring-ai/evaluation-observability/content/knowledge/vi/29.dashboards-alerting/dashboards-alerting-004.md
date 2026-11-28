# Theo dõi tỷ lệ đạt, giám khảo lỗi và tình huống chưa được đánh giá

## 1. Vì sao pass rate một mình không đủ?

Một evaluation run có 1.000 cases. Dashboard báo factuality pass rate là 98%. Con số đó nghe có vẻ tốt, nhưng nếu chỉ 250 cases được chấm, 500 cases bị bỏ qua, 150 cases gặp lỗi judge và 100 cases còn pending thì kết luận 98% rất dễ gây hiểu nhầm.

Pass rate chỉ mô tả những case đã có kết quả đánh giá hợp lệ. Nó không cho biết:

- Bao nhiêu case đủ điều kiện được đưa vào evaluation?
- Bao nhiêu case thực sự được chọn để chấm?
- Bao nhiêu case hoàn tất thành pass hoặc fail?
- Bao nhiêu lần gọi judge bị timeout, rate limit hoặc lỗi?
- Bao nhiêu response của judge không parse được?
- Bao nhiêu case bị skip, không áp dụng hoặc còn pending?
- Score có đáng tin cậy khi sample nhỏ hoặc judge thay đổi không?

Với ứng dụng Spring AI, cần quan sát đồng thời **chất lượng câu trả lời**, **sức khỏe evaluator/judge** và **độ bao phủ evaluation**. Một judge service bị lỗi có thể làm dashboard trống, nhưng điều đó không chứng minh generator đang tốt hay xấu.

Bài thuộc chương **Dashboard và cảnh báo** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module tập trung đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử luồng RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm theo phiên bản prompt, model và pipeline.

Sau bài, bạn có thể:

1. Thiết kế outcome states để phân biệt pass, fail, error, skipped và chưa đánh giá.
2. Xác định đúng mẫu số cho pass rate, judge error rate và evaluation coverage.
3. Theo dõi lỗi kỹ thuật, response không hợp lệ và retry của judge.
4. Phát hiện pending backlog và các nhóm case thường xuyên bị bỏ qua.
5. Đánh giá độ tin cậy của judge bằng human-labeled dataset.
6. Viết PromQL và alert cho quality regression, evaluator outage và coverage thấp.
7. Truy từ dashboard đến evaluation run, trace, case và phiên bản prompt/model/rubric.

## 2. Tách ba câu hỏi: chất lượng, judge health và coverage

Ba nhóm metric cần được hiển thị riêng:

| Nhóm | Câu hỏi | Metric ví dụ |
|---|---|---|
| Answer quality | Các câu trả lời đã được chấm có đạt tiêu chí không? | Pass rate, score distribution, human agreement |
| Judge/evaluator health | Pipeline chấm có hoạt động đúng không? | Attempt error rate, invalid response rate, judge latency |
| Evaluation coverage | Trong các case dự kiến, bao nhiêu case đã có kết quả hợp lệ? | Selection rate, completion coverage, skipped/pending count |

Ví dụ:

- Factuality pass rate giảm từ 96% xuống 88% trong khi judge error rate vẫn thấp: có thể là quality regression thực sự.
- Pass rate vẫn 96% nhưng judge error rate tăng lên 40%: kết quả pass rate chỉ phản ánh một phần nhỏ của workload.
- Judge khỏe và pass rate cao nhưng coverage chỉ 15%: bộ đánh giá có thể bỏ sót phần lớn case.
- Coverage cao nhưng judge-human agreement giảm: evaluator đang chạy ổn định về kỹ thuật nhưng khả năng phán đoán có thể đã drift.

Không gộp ba nhóm thành một score tổng. Mỗi nhóm cần panel, mẫu số và hành động xử lý riêng.

## 3. Mô hình trạng thái cho một evaluation case

Một case có thể đi qua nhiều trạng thái. Hãy định nghĩa rõ trạng thái cuối cùng:

| Outcome | Ý nghĩa | Có được tính vào pass rate? |
|---|---|---|
| PASS | Judge trả kết quả hợp lệ và case đạt criterion | Có, numerator và denominator |
| FAIL | Judge trả kết quả hợp lệ và case không đạt criterion | Có, chỉ denominator |
| ERROR | Không thể hoàn tất đánh giá do lỗi kỹ thuật sau retry policy | Không |
| INVALID | Judge trả output không đúng schema hoặc không thể diễn giải | Không |
| SKIPPED | Case được chọn nhưng chủ động bỏ qua theo policy | Không |
| NOT_APPLICABLE | Criterion không áp dụng cho case này | Không |
| INCONCLUSIVE | Có đánh giá nhưng evidence không đủ để kết luận | Không |
| PENDING | Đang chờ xử lý hoặc chờ judge hoàn tất | Chưa phải outcome cuối |

PASS và FAIL là kết quả chất lượng. ERROR và INVALID phản ánh pipeline đánh giá. SKIPPED và NOT_APPLICABLE phản ánh quyết định về phạm vi. PENDING phản ánh công việc chưa hoàn tất.

Không chuyển ERROR thành FAIL. Nếu judge timeout, hệ thống chưa biết câu trả lời có đúng hay không. Cũng không chuyển SKIPPED thành PASS vì chưa có bằng chứng đánh giá.

PENDING là trạng thái tạm thời; khi hết thời hạn, hệ thống cần chuyển sang retry, ERROR hoặc một terminal state được định nghĩa rõ. Không để case pending vô thời hạn.

## 4. Phân biệt case outcome và judge attempt

Một case có thể có nhiều lần gọi judge do retry. Cần lưu hai cấp dữ liệu:

- **Case outcome:** kết quả cuối cùng của criterion trên case sau khi áp dụng retry policy.
- **Judge attempt:** từng lần gọi evaluator/model judge, kể cả lần thất bại.

Ví dụ:

~~~text
Case RAG-042 / factuality
  Attempt 1: timeout
  Attempt 2: HTTP 429
  Attempt 3: valid judgment -> FAIL

Terminal case outcome: FAIL
Attempt error count: 2
Attempt total: 3
~~~

Case này chỉ đóng góp một FAIL vào pass rate. Hai lần lỗi được tính vào judge attempt error rate. Nếu cộng cả ba attempts vào case denominator, pass rate và coverage sẽ sai.

Một case có thể kết thúc ERROR sau khi hết retry. Khi đó không có pass/fail outcome, nhưng case terminal error vẫn cần được ghi nhận.

Lưu attempt ID, case ID, evaluation run ID và trace ID trong evaluation store. Không đưa các ID riêng lẻ này vào Prometheus labels.

## 5. Định nghĩa eligible, selected, applicable và evaluated

Để mẫu số có ý nghĩa, hãy phân biệt các tập case:

1. **Eligible:** case thuộc phạm vi được phép đánh giá theo dataset, consent, route và policy.
2. **Selected:** case được chọn theo sampling policy hoặc được đưa vào run.
3. **Applicable:** criterion thực sự áp dụng cho case đã chọn.
4. **Evaluated:** judge hoàn tất với kết quả hợp lệ là PASS hoặc FAIL.

Ví dụ một bộ dataset có 1.000 cases:

| Bước | Số lượng | Diễn giải |
|---|---:|---|
| Eligible | 1.000 | Thuộc phạm vi đánh giá |
| Selected | 800 | Sampling policy chọn 80% |
| Applicable | 760 | 40 cases không áp dụng criterion |
| Evaluated | 700 | PASS + FAIL |
| ERROR/INVALID | 30 | Judge không trả kết quả hợp lệ |
| SKIPPED | 20 | Thiếu context hoặc bị policy bỏ qua |
| PENDING | 10 | Chưa hoàn tất |

Các con số là ví dụ. Chúng cần reconcile theo một cohort và cùng evaluation run.

Từ đó:

- Selection rate = selected / eligible = 80%.
- Applicability rate = applicable / selected = 95%.
- Completion coverage = evaluated / applicable = 700 / 760 = 92,1%.
- 60 applicable cases chưa có pass/fail result: 30 error/invalid, 20 skipped và 10 pending.

NOT_APPLICABLE cần được báo riêng, không coi là evaluator failure. Nếu có case bị loại trước sampling vì policy, hãy ghi excluded count và reason để người xem biết phạm vi.

## 6. Công thức pass rate đúng mẫu số

Pass rate chỉ tính trên các case có đánh giá hợp lệ:

\[
PassRate =
\frac{PASS}
{PASS + FAIL}
\]

Ví dụ 665 PASS và 35 FAIL:

\[
PassRate = \frac{665}{665 + 35} = 95\%
\]

Nếu có 30 ERROR, 20 SKIPPED và 10 PENDING, chúng không được cộng vào mẫu số pass rate. Nhưng phải hiển thị bên cạnh pass rate và tính vào coverage hoặc các panel trạng thái tương ứng.

Không dùng:

\[
\frac{PASS}{Eligible}
\]

để gọi là pass rate. Công thức này trộn chất lượng với sampling, evaluator health và coverage. Nó có thể được đặt tên là successful assessment yield trên eligible cases nếu đó là chỉ số sản phẩm mong muốn, nhưng không thay thế pass rate.

Luôn hiển thị sample count cạnh tỷ lệ, ví dụ: 665/700 PASS (95%). Một con số 95% mà không có numerator/denominator rất khó diễn giải.

## 7. Tính evaluator error rate ở cấp attempt

Định nghĩa một attempt là một lần evaluator/judge được gọi và có kết quả kỹ thuật:

- COMPLETED: judge trả kết quả có thể diễn giải.
- ERROR: timeout, provider 429/5xx, network error hoặc exception.
- INVALID: output thiếu trường, sai schema, parse failure hoặc không đáp ứng contract.

Attempt error rate:

\[
AttemptErrorRate =
\frac{ERROR + INVALID}
{COMPLETED + ERROR + INVALID}
\]

Nếu một attempt COMPLETED có thể cho PASS, FAIL hoặc INCONCLUSIVE, cả ba vẫn là completed attempts về mặt kỹ thuật. INCONCLUSIVE không phải lỗi transport, nhưng nó không góp vào pass rate.

Nên có panel riêng cho:
- Transport/provider error rate.
- Invalid judge response rate.
- Evaluator application error rate.
- Inconclusive judgment rate.

Một judge có thể trả JSON hợp lệ nhưng không có evidence đủ để kết luận. Đây là INCONCLUSIVE, không nhất thiết là lỗi kỹ thuật.

## 8. Tính terminal case error rate

Attempt error rate và terminal case error rate trả lời hai câu hỏi khác nhau.

- Attempt error rate cho biết từng lần gọi judge có ổn định không.
- Terminal case error rate cho biết sau retry policy có bao nhiêu case không thể đánh giá.

\[
TerminalCaseErrorRate =
\frac{Cases_{ERROR} + Cases_{INVALID}}
{Cases_{PASS} + Cases_{FAIL} + Cases_{ERROR} + Cases_{INVALID} + Cases_{INCONCLUSIVE}}
\]

Mẫu số gồm các case đã có terminal judgment hoặc terminal technical outcome; SKIPPED, NOT_APPLICABLE và PENDING được theo dõi riêng. Nếu retry thành công, case có thể kết thúc PASS hoặc FAIL dù có attempt lỗi trước đó. Vì thế terminal case error rate có thể thấp hơn attempt error rate.

Theo dõi cả hai để biết retry đang cứu được workload hay chỉ che khuất một judge service thiếu ổn định.

## 9. Evaluation coverage và unevaluated cases

Coverage đo mức độ hoàn tất đánh giá trên các case thực sự thuộc phạm vi.

\[
CompletionCoverage =
\frac{PASS + FAIL}
{ApplicableSelectedCases}
\]

Ngoài coverage tổng, nên theo dõi các trạng thái chưa được đánh giá:

| Trạng thái | Lý do phổ biến |
|---|---|
| ERROR | Provider timeout, quota, evaluator crash |
| INVALID | Judge output không parse được hoặc thiếu verdict |
| SKIPPED | Budget limit, sampling rule, thiếu context |
| PENDING | Queue backlog, worker chưa xử lý xong |
| INCONCLUSIVE | Evidence không đủ hoặc judge không chắc chắn |
| NOT_APPLICABLE | Criterion không phù hợp với case |

Coverage thấp không luôn là bug. Ví dụ sampling policy chỉ chọn 10% production traffic là có chủ đích. Hãy so coverage với **target selection rate** và **target completion coverage**, không đòi hỏi mọi eligible case đều phải được chấm.

## 10. Phân biệt skipped, excluded và not applicable

Ba trạng thái này có ý nghĩa khác nhau:

- **Excluded:** case không thuộc phạm vi evaluation ngay từ đầu, ví dụ consent không cho phép hoặc route ngoài scope.
- **Skipped:** case đã được chọn nhưng không chạy evaluation do policy hoặc thiếu dữ liệu.
- **Not applicable:** criterion không có ý nghĩa đối với case, ví dụ tool correctness trên câu hỏi không cần gọi tool.

Nếu gộp chúng thành một skipped counter, bạn sẽ không biết pipeline bỏ case vì policy, vì thiếu dữ liệu hay vì criterion không phù hợp.

Có thể lưu reason codes hữu hạn:

~~~text
excluded_reason:
  consent_restricted
  route_out_of_scope
  unsupported_locale

skipped_reason:
  missing_context
  budget_limit
  duplicate_case
  sampling_cancelled

not_applicable_reason:
  no_tool_expected
  no_retrieval_expected
  citation_not_required
~~~

Reason code phải có danh mục được quản lý. Không đưa raw query hoặc nội dung người dùng vào label.

## 11. Phân loại lỗi của judge

Một lỗi judge cần được phân loại đủ cụ thể để có thể hành động:

| Error class | Ví dụ | Hành động |
|---|---|---|
| TIMEOUT | Judge không phản hồi trong deadline | Kiểm tra latency, timeout và queue |
| RATE_LIMITED | Provider trả 429 | Kiểm tra quota, concurrency và backoff |
| PROVIDER_5XX | Provider trả lỗi server | Kiểm tra provider status và fallback |
| NETWORK | DNS, TLS hoặc connection reset | Kiểm tra network/HTTP client |
| INVALID_OUTPUT | Output không đúng schema | Kiểm tra prompt, model và structured output |
| PARSE_ERROR | Không parse được verdict | Kiểm tra output contract/parser |
| MISSING_EVIDENCE | Thiếu context hoặc reference data | Kiểm tra input dataset và retrieval |
| CONFIGURATION | Thiếu model, rubric hoặc credential config | Kiểm tra deployment/configuration |
| INTERNAL | Bug trong evaluator adapter hoặc persistence | Mở application trace/log |

Đừng dùng exception message làm metric label. Message có thể chứa URL, request ID hoặc dữ liệu động và tạo cardinality không giới hạn. Dùng error class hữu hạn; lưu exception details trong log/trace có quyền truy cập phù hợp.

## 12. Retry policy cho evaluator

Retry có thể cải thiện completion coverage nhưng cũng làm tăng chi phí và che giấu judge instability.

Nguyên tắc:

1. Chỉ retry lỗi tạm thời như timeout, 429, 5xx hoặc connection reset.
2. Không retry một verdict FAIL như thể đó là lỗi kỹ thuật.
3. Không retry vô hạn; giới hạn attempts và deadline cho mỗi case.
4. Dùng exponential backoff có jitter cho provider throttling.
5. Giữ attempt history và error class.
6. Dùng idempotency key khi enqueue/persist kết quả.
7. Khi hết retry, ghi terminal ERROR thay vì bỏ case khỏi dashboard.
8. Nếu judge model/rubric thay đổi giữa retry, tạo một evaluation run/version mới hoặc ghi rõ policy; không trộn các judge versions trong một kết quả so sánh.

Retry không được làm tăng case count. Một case có ba attempts vẫn là một case trong coverage và pass rate.

## 13. Theo dõi judge latency và queue backlog

Evaluator thường gọi thêm một model để chấm kết quả. Vì vậy cần theo dõi latency và queue riêng với generator.

Các metric hữu ích:

- Evaluation attempts per second.
- Judge P50/P95/P99 duration.
- Pending evaluation cases.
- Queue age của case pending lâu nhất hoặc percentile queue age.
- Retry attempts per case.
- Worker concurrency và utilization.
- Timeout/429 rate.
- Cost per evaluated case.

Nếu pending count tăng liên tục trong khi attempts/s không đổi, worker capacity có thể thấp hơn incoming evaluation rate. Nếu judge P95 tăng cùng 429, giảm concurrency hoặc tăng backoff có thể hiệu quả hơn tăng worker count.

Không chạy evaluation đồng bộ trên critical path của user request nếu chưa đo ảnh hưởng đến latency và availability. Online evaluation thường phù hợp với queue bất đồng bộ và sampling có kiểm soát.

## 14. Đo judge score và phân phối kết quả

Nếu evaluator trả score liên tục, lưu score ở thang đo có định nghĩa rõ, ví dụ 0 đến 1. Không trộn score 0–1 với score 0–5 hoặc rubric ordinal nếu chưa chuẩn hóa.

Dashboard nên có:

- Score histogram theo criterion.
- PASS/FAIL theo threshold version.
- INCONCLUSIVE rate.
- Score distribution theo prompt/model version.
- Judge model và rubric version.
- Human agreement theo từng criterion.

Không chỉ hiển thị average score. Hai release có cùng mean 0,85 nhưng phân phối có thể rất khác: một release ổn định quanh 0,85, release khác có nhiều case rất thấp và rất cao.

Nếu score dùng threshold để chuyển thành PASS/FAIL, lưu threshold version. Khi thay threshold, kết quả pass rate có thể đổi dù raw scores không đổi.

## 15. Hiệu chuẩn judge bằng human-labeled dataset

Judge model có thể thiên lệch, thay đổi theo prompt hoặc không hiểu rubric. Hãy giữ một bộ calibration dataset có nhãn do con người xác nhận.

Quy trình:

1. Chọn các case đại diện cho route, locale, độ khó và failure modes.
2. Có ít nhất một nhãn human cho từng criterion; các case quan trọng có thể cần hai reviewer.
3. Chạy judge trên cùng input, rubric và evidence.
4. So sánh judge verdict với human verdict.
5. Tính agreement, false pass và false fail.
6. Review các bất đồng và cập nhật rubric/prompt khi có bằng chứng.
7. Chạy lại calibration sau khi đổi judge model, rubric hoặc evaluator code.

Đừng chỉ nhìn overall agreement. False pass có thể nguy hiểm hơn false fail ở các tác vụ có rủi ro cao. Hãy xem confusion matrix:

| | Human PASS | Human FAIL |
|---|---:|---:|
| Judge PASS | True pass | False pass |
| Judge FAIL | False fail | True fail |

Hai tỷ lệ cần theo dõi riêng:

\[
FalsePassRate = \frac{JudgePass \cap HumanFail}{HumanFail}
\qquad
FalseFailRate = \frac{JudgeFail \cap HumanPass}{HumanPass}
\]

FalsePassRate đo phần case con người xác định FAIL nhưng judge chấp nhận PASS. FalseFailRate đo phần case con người xác định PASS nhưng judge từ chối. Hai tỷ lệ có mẫu số khác nhau, nên không thay thế overall agreement.

Với criterion factuality, false pass là trường hợp judge chấp nhận một câu trả lời mà reviewer xác định là sai. Đây có thể là tín hiệu cần ưu tiên.

## 16. Đo độ bất định và sample size

Một pass rate từ 20 cases có độ bất định cao hơn nhiều so với cùng pass rate từ 2.000 cases.

Dashboard nên hiển thị:
- PASS count và FAIL count.
- Evaluated sample size.
- Confidence interval.
- Evaluation window hoặc run ID.
- Sampling method và dataset version.

Có thể dùng Wilson confidence interval cho tỷ lệ pass để tránh xấp xỉ kém khi sample nhỏ hoặc tỷ lệ gần 0/1. Không cần tính interval cho cohort có denominator bằng zero.

Khi so hai release, ưu tiên chạy trên cùng dataset cases, cùng criterion, cùng judge model và cùng rubric. Nếu cases độc lập, có thể so tỷ lệ và confidence intervals; nếu cùng case được chạy trên cả hai release, phân tích paired outcomes sẽ có ý nghĩa hơn vì giảm ảnh hưởng khác biệt giữa các case.

Không kết luận regression chỉ vì pass rate thay đổi một vài điểm phần trăm nếu sample size quá nhỏ hoặc confidence intervals chồng lấn đáng kể. Với quyết định quan trọng, dùng kiểm định phù hợp và review failed cases.

## 17. Tránh sampling bias trong online evaluation

Online evaluation thường chỉ chấm một phần production traffic. Sampling policy có thể làm score bị lệch nếu không đại diện.

Ví dụ, nếu chỉ chấm những request ngắn và dễ, pass rate sẽ cao hơn thực tế. Nếu chỉ chấm những request bị user thumbs-down, pass rate thấp hơn toàn traffic.

Cần:

- Sampling theo route/feature, locale, model family và độ phức tạp.
- Giữ tỷ lệ sample theo cohort và ghi rõ sampling policy version.
- Bao gồm cả request thành công lẫn request bị retry/escalate.
- Theo dõi missing data và sample exclusions.
- Dùng deterministic sampling khi cần tái lập.
- Tăng sample cho failure modes quan trọng nhưng báo riêng đây là targeted sample.

Nếu dùng oversampling cho rare failures, không lấy pass rate raw của mẫu oversampled làm tỷ lệ production toàn cục. Có thể cần weighting theo tỷ trọng population hoặc hiển thị các cohort riêng.

## 18. Offline, online và human evaluation

| Loại | Mục đích | Đặc điểm |
|---|---|---|
| Offline dataset evaluation | So sánh prompt/model/pipeline trước release | Dataset và rubric cố định, có thể chạy toàn bộ |
| Online sampled evaluation | Phát hiện drift trên traffic thực tế | Sampling, async queue, privacy policy |
| Human review | Xác nhận judge và đánh giá các case khó | Chậm hơn nhưng cần thiết để calibration |
| Adjudication | Giải quyết bất đồng giữa judges/reviewers | Tập trung vào case rủi ro cao hoặc tranh chấp |

Không trộn các nguồn này thành một pass rate. Gắn source label hoặc filter riêng để so sánh đúng cohort.

Một bộ offline dataset có thể được chạy lặp lại mỗi release. Một sample online có thể thay đổi theo traffic. Human review có thể oversample case fail. Mỗi nguồn có mục tiêu và denominator riêng.

## 19. Phiên bản hóa evaluation run

Mỗi evaluation result nên lưu tối thiểu:

| Trường | Mục đích |
|---|---|
| evaluation_run_id | Nhóm các kết quả thuộc cùng một run |
| dataset_version | Dataset và gold evidence version |
| case_id | Tra cứu case trong evaluation store |
| criterion | Relevance, factuality, groundedness, tool correctness... |
| source | Offline, online_sampled, human_review |
| prompt_version | Prompt được dùng để tạo response |
| generator_model | Model sinh câu trả lời |
| judge_model | Model chấm |
| rubric_version | Quy tắc đánh giá |
| evaluator_version | Phiên bản adapter/evaluator code |
| terminal_outcome | PASS, FAIL, ERROR, INVALID, SKIPPED... |
| score | Score nếu có |
| timestamps | Selected, started, completed |
| trace_id | Truy ngược execution khi cần |

Các ID và timestamps chi tiết lưu trong database/event store. Prometheus chỉ giữ các labels có số giá trị hữu hạn, ví dụ criterion, source, model family và release version đã được kiểm soát.

Nếu dataset hoặc rubric đổi, tạo run/version mới. Không ghi đè kết quả cũ vì sẽ mất khả năng tái lập và so sánh.

## 20. Định nghĩa metric names cho evaluation pipeline

Một schema metric ứng dụng có thể là:

~~~text
app_ai_eval_eligible_cases_total{criterion,source,dataset_version}
app_ai_eval_selected_cases_total{criterion,source,dataset_version}
app_ai_eval_applicable_cases_total{criterion,source,dataset_version}
app_ai_eval_cases_total{criterion,outcome,source,prompt_version,judge_family}
app_ai_eval_attempts_total{criterion,result,error_class,judge_family}
app_ai_eval_duration_seconds
app_ai_eval_pending_cases{source,queue}
app_ai_eval_score{criterion,judge_family}
app_ai_eval_human_reviews_total{criterion,agreement}
~~~

Ý nghĩa:

- eligible: số case-criterion thuộc phạm vi.
- selected: số case-criterion được chọn cho run.
- applicable: số case-criterion thực sự áp dụng.
- cases: terminal outcomes, mỗi case-criterion chỉ được ghi một lần trong một run.
- attempts: mỗi lần gọi judge, kể cả retry.
- duration: thời gian một attempt.
- pending: số case đang chờ.
- score: phân phối score đã chuẩn hóa.
- human_reviews: số lượt calibration/review theo agreement.

Các metric trên là schema do ứng dụng đề xuất, không phải tất cả đều được Spring AI tự xuất. Spring AI cung cấp Evaluator API và observations cho các model operations; ứng dụng cần chuyển kết quả evaluation thành outcome và metrics nghiệp vụ.

## 21. Đếm outcome đúng một lần

Một terminal case counter chỉ được increment khi case chuyển sang trạng thái cuối. Cần bảo đảm event handler idempotent.

Ví dụ logic:

~~~java
enum EvaluationOutcome {
    PASS,
    FAIL,
    ERROR,
    INVALID,
    SKIPPED,
    NOT_APPLICABLE,
    INCONCLUSIVE
}

void recordTerminalOutcome(
        EvaluationCase evaluationCase,
        EvaluationOutcome outcome) {

    if (!terminalStateStore.compareAndSet(
            evaluationCase.id(),
            "PENDING",
            outcome.name())) {
        return;
    }

    meterRegistry.counter(
        "app.ai.eval.cases",
        "criterion", evaluationCase.criterion(),
        "outcome", outcome.name().toLowerCase(),
        "source", evaluationCase.source()
    ).increment();
}
~~~

Đây là pseudocode minh họa. Trong production, compare-and-set phải được thực hiện bền vững trong database hoặc event store. Không dựa vào một map trong bộ nhớ vì worker restart hoặc message redelivery có thể ghi terminal outcome nhiều lần.

Case counter và attempt counter phải được ghi ở hai nơi logic khác nhau. Mỗi retry tạo một attempt event; chỉ terminal transition tạo case outcome event.

## 22. PromQL: pass rate theo criterion

Giả sử terminal outcomes được xuất qua app_ai_eval_cases_total.

Factuality pass rate trong một giờ:

~~~promql
sum(rate(app_ai_eval_cases_total{
  criterion="factuality",
  outcome="pass"
}[1h]))
/
sum(rate(app_ai_eval_cases_total{
  criterion="factuality",
  outcome=~"pass|fail"
}[1h]))
~~~

Relevance pass rate:

~~~promql
sum by (prompt_version) (
  rate(app_ai_eval_cases_total{
    criterion="relevance",
    outcome="pass"
  }[1h])
)
/
sum by (prompt_version) (
  rate(app_ai_eval_cases_total{
    criterion="relevance",
    outcome=~"pass|fail"
  }[1h])
)
~~~

Nếu không có PASS hoặc FAIL trong cửa sổ, denominator bằng zero và query không có tỷ lệ hợp lệ. Hãy hiển thị N/A/no data thay vì ép thành 0%.

Để có báo cáo theo evaluation run cố định, query từ evaluation store thường phù hợp hơn Prometheus range window vì mỗi run có cohort và dataset version rõ ràng.

## 23. PromQL: attempt error và invalid response rate

Giả sử attempt result có các giá trị completed, error và invalid:

~~~promql
sum(rate(app_ai_eval_attempts_total{
  result=~"error|invalid"
}[10m]))
/
sum(rate(app_ai_eval_attempts_total[10m]))
~~~

Có thể tách error class:

~~~promql
sum by (error_class) (
  rate(app_ai_eval_attempts_total{
    result=~"error|invalid"
  }[10m])
)
~~~

Nếu muốn biết provider timeout cụ thể, lọc error_class="TIMEOUT". Nếu INVALID_OUTPUT tăng, kiểm tra judge prompt và response schema.

Không đưa exception message, raw response hoặc case ID vào labels.

## 24. PromQL: completion coverage và selection rate

Completion coverage trên applicable cases:

~~~promql
sum(rate(app_ai_eval_cases_total{
  outcome=~"pass|fail"
}[1h]))
/
sum(rate(app_ai_eval_applicable_cases_total[1h]))
~~~

Selection rate trên eligible cases:

~~~promql
sum(rate(app_ai_eval_selected_cases_total[1h]))
/
sum(rate(app_ai_eval_eligible_cases_total[1h]))
~~~

Các metric phải được ghi trên cùng cohort, criterion, source và evaluation run scope. Nếu một metric được ghi khi enqueue còn metric khác được ghi khi hoàn tất, hãy dùng cửa sổ phù hợp hoặc báo cáo theo run ID trong evaluation store.

Completion coverage thấp có thể do judge outage, pending backlog, skipped cases hoặc invalid outputs. Mở breakdown outcome và reason để xác định.

## 25. PromQL: pending queue và judge latency

Số case đang chờ:

~~~promql
sum by (queue) (
  app_ai_eval_pending_cases
)
~~~

P95 judge duration:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, judge_family) (
    rate(app_ai_eval_duration_seconds_bucket[5m])
  )
)
~~~

Nếu pending tăng cùng P95 duration, worker có thể đang bị nghẽn hoặc provider chậm. Nếu pending tăng nhưng judge duration ổn định, kiểm tra enqueue rate, worker capacity và scheduler.

Cần có queue age metric nếu muốn phát hiện một case bị chờ quá lâu. Pending count thấp không loại trừ một case quan trọng đã bị stuck.

## 26. PromQL: human agreement và judge calibration

Giả sử ứng dụng ghi:

~~~text
app_ai_eval_human_reviews_total{criterion,agreement}
~~~

Agreement rate:

~~~promql
sum by (criterion) (
  rate(app_ai_eval_human_reviews_total{agreement="agree"}[24h])
)
/
sum by (criterion) (
  rate(app_ai_eval_human_reviews_total[24h])
)
~~~

Đây là tỷ lệ agreement đơn giản, không điều chỉnh cho agreement ngẫu nhiên hoặc class imbalance. Với tập nhãn có nhiều mức hoặc nhiều reviewer, cân nhắc Cohen's kappa, weighted kappa hoặc Krippendorff's alpha phù hợp với thiết kế dữ liệu.

Theo dõi riêng false-pass và false-fail trên calibration set. Một judge có overall agreement cao vẫn có thể có false-pass rate không chấp nhận được ở criterion quan trọng.

## 27. Dashboard nên có những panel nào?

Một dashboard evaluator health/coverage có thể gồm:

| Hàng | Panel | Mục đích |
|---|---|---|
| Quality | Pass rate theo criterion | Theo dõi relevance/factuality/tool correctness |
| Quality | PASS/FAIL counts | Xem numerator/denominator |
| Coverage | Eligible → selected → applicable → evaluated | Phát hiện mất case qua pipeline |
| Coverage | ERROR/INVALID/SKIPPED/INCONCLUSIVE | Biết lý do chưa có verdict |
| Judge health | Attempt error rate theo error class | Phát hiện provider/evaluator outage |
| Judge health | Judge P95/P99 | Theo dõi độ trễ chấm |
| Queue | Pending count và oldest age | Phát hiện backlog/stuck work |
| Calibration | Human agreement, false-pass, false-fail | Đánh giá độ tin cậy judge |
| Release | Pass rate theo prompt/model/rubric version | Phát hiện regression |
| Cost | Cost/evaluated case | Theo dõi overhead của evaluation |

Mọi tỷ lệ cần hiển thị sample size, evaluation window, source và version. Khi denominator bằng zero, ghi no data/N/A thay vì 0%.

## 28. Alert: judge error rate tăng

Ví dụ Prometheus alert khi tỷ lệ attempt error vượt 5% và có đủ attempts:

~~~yaml
groups:
  - name: spring-ai-evaluation
    rules:
      - alert: EvaluationJudgeAttemptErrorRateHigh
        expr: |
          (
            sum(rate(app_ai_eval_attempts_total{
              result=~"error|invalid"
            }[10m]))
            /
            sum(rate(app_ai_eval_attempts_total[10m]))
          ) > 0.05
          and
          sum(increase(app_ai_eval_attempts_total[10m])) >= 50
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Evaluation judge errors are elevated"
          description: "Inspect timeout, rate limit, invalid output and evaluator traces."
~~~

Ngưỡng 5% và 50 attempts là ví dụ. Hiệu chỉnh theo baseline, provider và mức độ quan trọng của evaluation pipeline.

Nếu judge outage khiến quality coverage giảm mạnh, alert coverage có thể có severity cao hơn. Đừng page chỉ vì một attempt lỗi khi retry hoàn tất và user-facing SLO không bị ảnh hưởng.

## 29. Alert: evaluation coverage giảm hoặc pending backlog tăng

Ví dụ alert coverage thấp:

~~~yaml
groups:
  - name: spring-ai-evaluation-coverage
    rules:
      - alert: EvaluationCompletionCoverageLow
        expr: |
          (
            sum(rate(app_ai_eval_cases_total{
              outcome=~"pass|fail"
            }[30m]))
            /
            sum(rate(app_ai_eval_applicable_cases_total[30m]))
          ) < 0.90
          and
          sum(increase(app_ai_eval_applicable_cases_total[30m])) >= 100
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Evaluation completion coverage is below target"
          description: "Inspect skipped, pending, error and invalid outcomes."
~~~

Ví dụ pending backlog:

~~~yaml
- alert: EvaluationPendingBacklogHigh
  expr: sum(app_ai_eval_pending_cases) > 500
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Evaluation queue backlog is high"
    description: "Check worker capacity, enqueue rate and judge provider latency."
~~~

Ngưỡng coverage 90% và pending 500 cases chỉ là ví dụ. Với online sampling có chủ đích, selection rate thấp có thể đúng; alert cần so completion coverage trên selected applicable cases.

## 30. Alert: quality pass rate giảm

Quality alert nên gắn với criterion, sample size và version. Ví dụ:

~~~yaml
groups:
  - name: spring-ai-quality-gates
    rules:
      - alert: FactualityPassRateBelowTarget
        expr: |
          (
            sum(rate(app_ai_eval_cases_total{
              criterion="factuality",
              outcome="pass"
            }[1h]))
            /
            sum(rate(app_ai_eval_cases_total{
              criterion="factuality",
              outcome=~"pass|fail"
            }[1h]))
          ) < 0.90
          and
          sum(increase(app_ai_eval_cases_total{
            criterion="factuality",
            outcome=~"pass|fail"
          }[1h])) >= 100
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Factuality pass rate is below target"
          description: "Compare prompt/model versions and inspect failed cases."
~~~

Đây là cảnh báo online sample minh họa. Với offline evaluation run, release gate nên dựa trên toàn bộ cohort cố định và kết quả run đã hoàn tất; không dùng một sliding window production thay thế dataset gate.

Nếu judge error rate hoặc coverage đang xấu, đừng coi pass rate là kết quả đầy đủ. Có thể quality panel trông ổn chỉ vì những case khó không được chấm.

## 31. Quy trình điều tra khi pass rate hoặc coverage bất thường

Thực hiện theo thứ tự:

1. Xác nhận source: offline run, online sample hay human review?
2. Kiểm tra eligible, selected, applicable và evaluated counts.
3. Xem breakdown terminal outcomes: PASS, FAIL, ERROR, INVALID, SKIPPED, INCONCLUSIVE.
4. Kiểm tra attempt error classes, retry count và judge provider status.
5. Xem pending count, oldest queue age và worker utilization.
6. So judge model, rubric version, evaluator code và threshold version.
7. So generator model, prompt version, tool-set và retrieval/index version.
8. Mở failed cases và traces; kiểm tra input, retrieved evidence và judge feedback.
9. Kiểm tra calibration set và human disagreement.
10. Quyết định: sửa evaluator, retry transient failures, điều chỉnh sampling, rollback candidate hoặc cập nhật rubric.

Không thay rubric chỉ để pass rate tăng. Trước tiên xác định answer quality thật sự thay đổi hay evaluator đang thay đổi cách chấm.

## 32. Cardinality và bảo vệ dữ liệu

Metric labels cần có số giá trị hữu hạn:

- criterion: relevance, factuality, groundedness, tool_selection, citation.
- outcome: pass, fail, error, invalid, skipped, not_applicable, inconclusive.
- source: offline, online_sampled, human_review.
- error_class: timeout, rate_limited, provider_5xx, invalid_output, parse_error, internal.
- judge_family/model_family: danh mục model được kiểm soát.
- prompt_version/rubric_version: release versions có vòng đời hữu hạn.

Không dùng case ID, evaluation run ID, user ID, conversation ID, trace ID hoặc raw prompt làm metric labels. Lưu chúng trong evaluation store hoặc trace.

Judge input có thể chứa prompt, completion, retrieved documents và tool results. Hãy áp dụng redaction, access control và retention policy. Không bật log raw content chỉ để debug pass rate.

## 33. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| ERROR bị tính là FAIL | Đánh giá generator thấp giả tạo | Tách outcome chất lượng và judge health |
| ERROR bị bỏ khỏi dashboard | Pass rate trông tốt giả tạo | Hiển thị attempt errors và coverage |
| SKIPPED bị tính là PASS | Tăng pass rate không có bằng chứng | Ghi skipped reason riêng |
| Pending bị coi là fail | Báo regression khi job chưa chạy xong | Theo dõi queue và deadline |
| Retry được đếm thành nhiều case | Sai denominator | Tách case outcome và attempt |
| Chỉ hiển thị phần trăm | Không biết sample size | Hiển thị numerator/denominator |
| Không theo dõi eligible/selected | Không biết sampling coverage | Đo từng bước pipeline |
| Trộn offline và online | So sánh cohort không tương đương | Filter theo source và run |
| Đổi judge cùng generator | Không xác định nguyên nhân score đổi | Pin judge/rubric hoặc chạy calibration |
| Không có human calibration | Judge drift không được phát hiện | Duy trì human-labeled set |
| Sampling chỉ lấy case dễ | Pass rate bị thiên lệch | Stratify và audit sampling |
| Alert khi sample quá nhỏ | False positive | Minimum sample và confidence |
| Dùng case ID làm label | Cardinality tăng không giới hạn | Dùng evaluation store/traces |
| Không có pending age | Case bị stuck không được phát hiện | Theo dõi queue age và deadline |

## 34. Bài tập tự kiểm tra

### Bài 1 — Pass rate cao nhưng coverage thấp

Có 100 eligible cases, 80 selected, 10 not applicable, 50 PASS, 10 FAIL, 5 ERROR và 5 PENDING. Pass rate và completion coverage là bao nhiêu?

**Đáp án:** Applicable selected = 80 - 10 = 70. Pass rate = 50 / (50 + 10) = 83,3%. Completion coverage = 60 / 70 = 85,7%. Còn 10 applicable cases chưa có verdict hợp lệ.

### Bài 2 — Retry có làm tăng case count?

Một case timeout hai lần rồi lần thứ ba trả FAIL. Có bao nhiêu case outcome và bao nhiêu attempt?

**Đáp án:** Một terminal case outcome là FAIL và ba judge attempts, trong đó hai attempt lỗi.

### Bài 3 — Judge error hay answer fail?

Judge provider trả HTTP 429 trước khi đọc response. Nên ghi outcome gì?

**Đáp án:** Attempt ERROR với error class RATE_LIMITED. Sau retry policy, nếu không chấm được thì terminal case ERROR. Không ghi FAIL.

### Bài 4 — Judge output không hợp schema

Judge trả JSON thiếu verdict. Đây là FAIL hay INVALID?

**Đáp án:** INVALID vì không có judgment hợp lệ. Ghi parse/schema error và retry theo policy nếu lỗi có thể tạm thời.

### Bài 5 — Not applicable

Một case không yêu cầu tool nhưng tool correctness evaluator được chạy. Kết quả nên là gì?

**Đáp án:** NOT_APPLICABLE, không phải PASS. Case không có kỳ vọng tool để kiểm tra.

### Bài 6 — Judge agreement giảm

Pass rate giữ nguyên nhưng human agreement giảm từ 94% xuống 78% sau khi đổi judge model. Cần điều tra gì?

**Đáp án:** Calibration set, false-pass/false-fail, judge prompt, rubric compatibility và score threshold. Pass rate ổn định không chứng minh judge còn đáng tin.

### Bài 7 — Online pass rate tăng đột ngột

Pass rate tăng từ 88% lên 99%, nhưng selected cases giảm 80% và phần lớn case phức tạp không còn được chọn. Có thể kết luận chất lượng tốt hơn không?

**Đáp án:** Không. Đây có thể là sampling bias. So cohort và sampling policy, kiểm tra selection rate theo độ khó/route và chạy lại trên dataset cố định.

### Bài 8 — Pending backlog tăng

Pending cases tăng từ 100 lên 2.000 trong khi judge P95 không đổi. Cần xem gì?

**Đáp án:** Enqueue rate, worker capacity, scheduler, queue consumer lag và retry backlog. Latency của từng attempt ổn định không có nghĩa pipeline xử lý đủ throughput.

## 35. Checklist trước khi phát hành evaluator dashboard

- [ ] Có terminal outcome riêng cho PASS, FAIL, ERROR, INVALID, SKIPPED, NOT_APPLICABLE và INCONCLUSIVE?
- [ ] PENDING được theo dõi như trạng thái đang xử lý?
- [ ] Có tách case outcome khỏi judge attempt?
- [ ] Retry không làm tăng case denominator?
- [ ] Pass rate chỉ tính PASS/(PASS+FAIL)?
- [ ] Attempt error rate có denominator là tất cả judge attempts?
- [ ] Có eligible, selected, applicable và evaluated counts?
- [ ] Có completion coverage và selection rate?
- [ ] Có breakdown theo error class và skipped reason?
- [ ] Có judge P95/P99, pending count và queue age?
- [ ] Có human-labeled calibration dataset?
- [ ] Có false-pass, false-fail và agreement metrics?
- [ ] Có sample size, confidence interval, source và version?
- [ ] Có tách offline, online sampled và human review?
- [ ] Có pin dataset, generator, judge, rubric và evaluator versions?
- [ ] Metric labels có cardinality hữu hạn?
- [ ] Có alert cho judge errors, coverage, backlog và quality regression?
- [ ] Có runbook truy từ alert đến case, trace và release?

## 36. Tài liệu tham khảo

1. [Spring AI 2.1.0 — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator API, RelevancyEvaluator và FactCheckingEvaluator.
2. [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/): model observations, metrics và traces.
3. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer metrics, histogram và Actuator endpoints.
4. [Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/): counters, failures, in-progress work và latency.
5. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): histogram buckets và quantiles.
6. [NIST — AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework): quản trị, đo lường và theo dõi rủi ro AI.
7. [OpenTelemetry — Signals](https://opentelemetry.io/docs/concepts/signals/): metrics, traces, logs và context propagation.

*Các metric names, outcome states, PromQL và ngưỡng alert trong bài là schema minh họa do ứng dụng định nghĩa. Hãy thống nhất state machine và denominator với pipeline thực tế, kiểm tra metric exposition, pin judge/rubric versions và xác nhận chất lượng judge bằng human-labeled cases trước khi dùng dashboard làm release gate.*
