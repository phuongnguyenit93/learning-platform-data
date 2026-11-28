# Thiết kế SLI, SLO và ngưỡng cảnh báo phù hợp

## 1. Bắt đầu từ trải nghiệm người dùng

Một dashboard có thể có hàng trăm metrics nhưng vẫn không trả lời được câu hỏi quan trọng: người dùng có nhận được kết quả đúng lúc và đủ tin cậy không?

Với ứng dụng Spring AI, một request có thể đi qua HTTP endpoint, ChatClient, nhiều model operations, advisor, retrieval và tool execution. Một phần có thể hoàn tất kỹ thuật trong khi câu trả lời vẫn sai. Vì vậy, cần xác định mục tiêu ở ranh giới người dùng và đo các thành phần bên trong để chẩn đoán.

Ba khái niệm nền tảng:

- **SLI (Service Level Indicator):** chỉ số định lượng một khía cạnh dịch vụ, ví dụ tỷ lệ request thành công hoặc tỷ lệ câu trả lời đạt factuality.
- **SLO (Service Level Objective):** mục tiêu đặt cho SLI trong một cửa sổ thời gian hoặc một evaluation run, ví dụ 99,9% request hợp lệ thành công trong 30 ngày.
- **Error budget:** phần sự kiện xấu được phép xảy ra theo SLO. Budget cho biết dịch vụ còn bao nhiêu dư địa trước khi vi phạm mục tiêu.

SLO giúp đội phát triển thống nhất điều gì được coi là dịch vụ tốt. Alert dựa trên SLO giúp đội vận hành ưu tiên sự cố ảnh hưởng người dùng thay vì phản ứng với mọi dao động metric.

Bài thuộc chương **Dashboard và cảnh báo** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module tập trung đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua các phiên bản prompt, model và pipeline.

Sau bài, bạn có thể:

1. Chọn SLI ở đúng ranh giới người dùng và phân biệt với diagnostic metrics.
2. Viết SLO cho availability, latency, answer quality, evaluator health và cost.
3. Tính error budget và burn rate.
4. Chọn ngưỡng cảnh báo dựa trên mức ảnh hưởng và tốc độ tiêu thụ budget.
5. Dùng multi-window, multi-burn-rate alerts để giảm alert noise.
6. Kết hợp quality gate, coverage và judge health để tránh kết luận sai.
7. Thiết kế runbook, owner và chính sách phản ứng khi budget cạn.

## 2. Phân biệt SLI với metric chẩn đoán

Không phải metric nào cũng là SLI. Một SLI phải phản ánh trực tiếp một thuộc tính dịch vụ mà người dùng hoặc sản phẩm quan tâm.

| Metric | Vai trò | Có phải SLI không? |
|---|---|---|
| User request success ratio | Đo request hoàn tất theo contract | Có |
| ChatClient P95 duration | Có thể đại diện trải nghiệm invocation | Có, nếu user journey tương ứng |
| Model provider P95 | Chẩn đoán độ trễ provider | Thường là diagnostic |
| CPU utilization | Chẩn đoán saturation | Không trực tiếp |
| VectorStore query latency | Chẩn đoán retrieval | Chỉ khi retrieval latency là cam kết riêng |
| Factuality pass rate trên golden dataset | Đo chất lượng release | Có thể là quality SLI cho release |
| Judge HTTP 429 rate | Đo sức khỏe evaluator/provider | Diagnostic hoặc evaluator SLI |
| Tokens per task | Đo hiệu quả và cost | Có thể là efficiency SLI |

Một SLI tốt có định nghĩa rõ về event, good event, bad event, denominator, nguồn dữ liệu và cửa sổ đo. Nếu metric không có contract rõ, hai đội có thể diễn giải cùng một con số theo hai cách khác nhau.

Dùng CPU, provider errors, advisor duration và tool duration để tìm nguyên nhân khi SLI xấu. Không cần biến mọi diagnostic metric thành alert page.

## 3. Xác định user journey và ranh giới đo

Trước khi chọn ngưỡng, hãy mô tả một luồng người dùng cụ thể.

~~~text
User submits a question
  -> HTTP request accepted
  -> ChatClient invocation
      -> retrieve context
      -> model operation
      -> optional tool call
      -> model operation
  -> answer returned to user
  -> optional asynchronous evaluation
~~~

Ở đây có ít nhất ba ranh giới khác nhau:

- HTTP request: dịch vụ nhận và trả request.
- ChatClient invocation: pipeline AI xử lý prompt và advisors.
- Evaluation task: judge chạy sau response để đo chất lượng.

SLO availability và latency nên ưu tiên ranh giới mà người dùng cảm nhận. Model operation, tool và VectorStore là các thành phần giúp phân tích nguyên nhân.

Đừng cộng HTTP count, ChatClient count và model operation count. Một HTTP request có thể tạo nhiều model operations. Mỗi SLI cần có một đơn vị event nhất quán.

## 4. Viết measurement contract cho từng SLI

Một SLI nên có measurement contract gồm:

| Trường | Nội dung cần chốt |
|---|---|
| Name | Tên SLI dễ hiểu |
| User promise | Thuộc tính người dùng cần |
| Event unit | Một HTTP request, user turn, case hay task |
| Eligible events | Những event nằm trong phạm vi |
| Good event | Điều kiện được tính là tốt |
| Bad event | Điều kiện được tính là xấu |
| Exclusions | Event nào được loại và lý do |
| Source | Metric, event store, evaluator hay billing data |
| Window | 5 phút, 30 ngày, một release hoặc một evaluation run |
| Owner | Đội chịu trách nhiệm |
| Runbook | Hành động khi SLI vi phạm |

Ví dụ measurement contract cho request availability:

- Event unit: một request đến endpoint hỏi đáp.
- Eligible: request có input hợp lệ và được hệ thống chấp nhận xử lý.
- Good: response hoàn tất theo API contract và không có lỗi server/provider khiến tác vụ thất bại.
- Bad: timeout, lỗi server, provider failure không được fallback thành công hoặc request không thể trả kết quả theo contract.
- Exclusions: request bị từ chối vì input không hợp lệ hoặc caller không có quyền, nếu đây không phải lỗi dịch vụ theo contract.
- Window: rolling 30 days.

Việc loại trừ cần được thống nhất trước. Không loại các lỗi khó xử lý sau khi đã nhìn thấy chúng làm SLO xấu đi.

## 5. Chọn event-based SLI hay time-based SLI

Có hai cách đo availability phổ biến:

- **Event-based:** tỷ lệ request tốt trên tổng request hợp lệ.
- **Time-based:** tỷ lệ thời gian dịch vụ ở trạng thái sẵn sàng.

Với API AI, event-based thường phản ánh trải nghiệm từng request tốt hơn:

\[
AvailabilitySLI =
\frac{GoodRequests}{EligibleRequests}
\]

Ví dụ 999.000 request tốt trên 1.000.000 request hợp lệ:

\[
AvailabilitySLI = 99.9\%
\]

Time-based SLI có thể phù hợp cho dịch vụ có trạng thái up/down rõ ràng, nhưng có thể che khuất một phần request lỗi khi dịch vụ vẫn được coi là up.

Không diễn giải error budget theo phút nếu SLO được định nghĩa theo request events. Hai loại budget có đơn vị khác nhau.

## 6. Thiết kế SLI availability cho Spring AI

Một endpoint có thể trả HTTP 200 nhưng workflow AI không tạo được câu trả lời theo contract. Vì thế application layer nên ghi outcome cuối cùng của user request.

Metric minh họa do ứng dụng định nghĩa:

~~~text
app_ai_user_requests_total{route,result}
~~~

Trong đó route là danh mục hữu hạn như chat, rag hoặc agent; result là good hoặc bad.

PromQL availability error ratio:

~~~promql
sum(rate(app_ai_user_requests_total{result="bad"}[5m]))
/
sum(rate(app_ai_user_requests_total[5m]))
~~~

Availability SLI:

~~~promql
1 -
(
  sum(rate(app_ai_user_requests_total{result="bad"}[5m]))
  /
  sum(rate(app_ai_user_requests_total[5m]))
)
~~~

Counter phải được increment đúng một lần cho mỗi user request terminal outcome. Nếu request fallback sang provider khác và hoàn tất thành công, có thể tính là good ở user boundary, đồng thời ghi provider failure/fallback ở diagnostic metrics.

Định nghĩa rõ cancellation, client disconnect, invalid input, authorization rejection và timeout. Không để mỗi endpoint tự phân loại outcome theo cách khác nhau.

## 7. Thiết kế SLI latency theo ngưỡng người dùng

Latency SLI nên đo tỷ lệ request hoàn tất trong ngưỡng thay vì chỉ nhìn mean.

\[
LatencySLI(T) =
\frac{RequestsWithDuration \le T}
{EligibleRequests}
\]

Ví dụ SLO: 95% request RAG hoàn tất trong 4 giây.

Metric histogram do ứng dụng ghi:

~~~text
app_ai_request_duration_seconds
~~~

PromQL good-event ratio:

~~~promql
sum(rate(app_ai_request_duration_seconds_bucket{route="rag",le="4"}[5m]))
/
sum(rate(app_ai_request_duration_seconds_count{route="rag"}[5m]))
~~~

Bucket le="4" phải được cấu hình và xuất trong Prometheus. Request timeout cần được ghi nhận như bad event; nếu timer chỉ ghi khi response thành công, latency SLI sẽ bị lạc quan giả.

Có thể có nhiều latency SLI cho các UX khác nhau, ví dụ synchronous response và streaming response. Không dùng một ngưỡng chung cho mọi route.

## 8. Đặt SLO latency cho streaming

Với streaming, thời gian hoàn tất và thời gian bắt đầu phản hồi là hai trải nghiệm khác nhau.

| SLI | Đo gì? | Ví dụ SLO minh họa |
|---|---|---:|
| TTFT | Thời gian tới chunk đầu tiên có nội dung | 95% dưới 1,5 giây |
| Stream completion | Thời gian tới terminal completion | 95% dưới 8 giây |
| Inter-chunk latency | Khoảng cách giữa các chunks | 95% dưới 500 ms |

Các ngưỡng chỉ là ví dụ. Ứng dụng phải instrument riêng TTFT và inter-chunk latency; ChatClient stream duration không tự cung cấp TTFT.

Nếu người dùng có thể đọc và tương tác trong lúc stream, TTFT có thể quan trọng hơn completion time. Nếu tác vụ cần một JSON/document hoàn chỉnh, completion time và response validity có thể quan trọng hơn.

Tách cancellation khỏi completion. Một stream bị client đóng không nhất thiết là model trả xong.

## 9. Thiết kế quality SLI cho câu trả lời

Quality SLI đo kết quả nội dung, ví dụ:

- Relevance pass rate.
- Factuality pass rate.
- Groundedness pass rate.
- Citation correctness.
- Retrieval recall@k.
- Tool selection/argument correctness.
- Business task success.

Với evaluator, pass rate được tính trên kết quả đánh giá hợp lệ:

\[
QualityPassRate =
\frac{PASS}{PASS + FAIL}
\]

ERROR, INVALID, SKIPPED, NOT_APPLICABLE, INCONCLUSIVE và PENDING không được tính vào pass rate. Tuy nhiên phải có SLI riêng cho completion coverage và judge health để pass rate không che khuất dữ liệu bị thiếu.

Spring AI cung cấp Evaluator API, RelevancyEvaluator và FactCheckingEvaluator để đánh giá query, response và context. Việc chuyển verdict thành quality metrics, state và SLO là trách nhiệm của evaluation pipeline ứng dụng.

Tài liệu: [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html).

## 10. Đừng dùng một quality SLO cho cả offline và online

Offline evaluation và online sampled evaluation có đặc tính khác nhau.

| Loại | Cohort | Dùng SLO/gate như thế nào? |
|---|---|---|
| Offline release evaluation | Golden dataset cố định | Release gate trên toàn bộ cohort |
| Online sampled evaluation | Mẫu traffic production | Rolling quality SLI, kèm coverage và sampling policy |
| Human review | Case được reviewer chọn | Calibration và audit SLI riêng |
| Adjudication | Case bất đồng/rủi ro cao | Theo dõi resolution và review SLA |

Ví dụ offline gate:

- Factuality pass rate ít nhất 95%.
- Relevance pass rate ít nhất 94%.
- Tool selection accuracy ít nhất 97%.
- Tất cả required cases có terminal outcome hợp lệ.
- Judge calibration không vượt ngưỡng false-pass đã chốt.

Ví dụ online SLO:

- Factuality pass rate ít nhất 92% trên cases đã được chấm hợp lệ.
- Completion coverage ít nhất 95% trên selected applicable cases.
- Judge attempt error rate dưới 2%.
- Có ít nhất 500 evaluated cases trong cửa sổ 24 giờ.

Đây là ngưỡng minh họa, không phải tiêu chuẩn chung. Offline gate cần dùng cohort cố định; online SLI cần ghi sampling policy và theo dõi độ đại diện của mẫu.

## 11. Pair quality pass rate với coverage và judge health

Nếu chỉ có quality pass rate, judge outage có thể làm sample nhỏ đi nhưng tỷ lệ vẫn cao. Vì vậy, hãy định nghĩa một bộ SLI liên quan:

| SLI | Mẫu số | Mục đích |
|---|---|---|
| Quality pass rate | PASS + FAIL | Chất lượng trong số case đã chấm |
| Completion coverage | PASS + FAIL / selected applicable | Mức độ hoàn tất đánh giá |
| Judge attempt error rate | ERROR + INVALID / all attempts | Độ ổn định của evaluator |
| Pending age | Case đang pending | Độ trễ của pipeline |
| Calibration agreement | Human-reviewed cases | Độ tin cậy của judge |

Ví dụ quality pass rate là 98%, nhưng coverage chỉ 30% và judge error rate 50%. Không thể kết luận chất lượng production đạt 98%; dữ liệu đánh giá chưa đủ đáng tin.

Có thể đặt mục tiêu độc lập cho từng SLI. Nếu một SLI phụ thuộc vi phạm, đánh dấu quality dashboard là incomplete hoặc degraded.

## 12. Đặt SLO cho evaluator health

Evaluator là một service/pipeline riêng. Nếu evaluation là một phần quan trọng của release gate hoặc monitoring, nó cũng cần SLO.

Ví dụ:

- 99% judge attempts hoàn tất hợp lệ trong 10 giây.
- Ít nhất 98% selected applicable cases có verdict PASS hoặc FAIL hợp lệ trong 15 phút.
- Pending case age P95 dưới 5 phút.
- Invalid judge output dưới 0,5%.
- Evaluator cost trên mỗi case dưới budget.

Attempt success không đồng nghĩa case success. Một case có thể retry nhiều lần. Vì vậy cần phân biệt attempt-level SLI và case-level completion SLI.

Không để judge failure làm user request thất bại nếu evaluation chạy bất đồng bộ. Đặt riêng availability target cho serving path và evaluation path.

## 13. Thiết kế efficiency và cost SLI

Cost thường phù hợp với budget/efficiency guardrail hơn availability SLO.

Các SLI có thể theo dõi:

- Cost per successful task.
- Tokens per user turn.
- Model operations per ChatClient invocation.
- Cost theo feature/model.
- Tỷ lệ operation không có pricing/usage metadata.
- Daily spend so với budget.

Ví dụ mục tiêu:

- Cost per successful RAG task không vượt $0,02 ở cohort chuẩn.
- Tokens per chat turn không tăng quá 20% so với baseline cùng loại traffic.
- Daily spend dự báo không vượt feature budget.
- Unpriced model operations bằng 0 sau khi release model mới.

Các ngưỡng cần dựa vào bảng giá thực tế và business value. Nếu cost tăng vì chất lượng tăng đáng kể, quyết định cần xem trade-off chứ không tự động coi là outage.

Không gọi token usage là cost nếu chưa áp dụng rate card. Không coi unknown pricing là zero.

## 14. Chọn cửa sổ SLO và reporting period

SLO có thể dùng rolling window hoặc calendar window.

| Window | Ưu điểm | Hạn chế |
|---|---|---|
| Rolling 30 days | Phản ánh liên tục trạng thái gần đây | Cần query window dài và recording rules |
| Calendar month | Dễ đối chiếu báo cáo/billing | Đầu tháng có ít dữ liệu |
| 7 days | Phát hiện thay đổi gần đây | Dễ biến động bởi traffic nhỏ |
| Per release/run | Phù hợp offline quality gate | Không đại diện production traffic |
| 24 hours | Phù hợp online sampled quality | Cần đủ sample và xử lý seasonality |

SLO availability của API thường phù hợp rolling 28 hoặc 30 ngày. Quality release gate nên theo evaluation run. Cost budget có thể theo ngày/tháng billing. Không ép tất cả SLI dùng cùng một window.

## 15. Tính error budget từ SLO

Với event-based SLO:

\[
AllowedErrorRatio = 1 - SLO
\]

Nếu SLO là 99,9%:

\[
AllowedErrorRatio = 1 - 0.999 = 0.001
\]

Tức 0,1% eligible events có thể là bad events trong kỳ.

Nếu kỳ có 1.000.000 requests hợp lệ:

\[
ErrorBudget = 1,000,000 \times 0.001 = 1,000
\]

Ứng dụng có budget 1.000 bad requests trong kỳ ước tính này.

Với time-based SLO 99,9% trong 30 ngày liên tục:

\[
30 \times 24 \times 60 \times 0.001 = 43.2\text{ phút}
\]

43,2 phút chỉ áp dụng cho time-based availability trong tháng 30 ngày. Không dùng số phút này để diễn giải event-based request budget.

## 16. Tính error budget còn lại

Giả sử budget ban đầu là 1.000 bad requests và đã dùng 350:

\[
RemainingBudget = 1,000 - 350 = 650
\]

\[
BudgetConsumed = \frac{350}{1,000} = 35\%
\]

Dashboard nên hiển thị:

- Budget ban đầu.
- Bad events đã ghi nhận.
- Budget còn lại.
- Tỷ lệ budget đã tiêu thụ.
- Burn rate hiện tại.
- Dự báo cuối kỳ nếu tốc độ hiện tại giữ nguyên.

Không chỉ hiển thị error ratio 0,04%. Nếu đây là tỷ lệ bad events tích lũy trong cùng SLO window, với SLO 99,9% nó tương đương 40% error budget đã dùng. Với một cửa sổ ngắn hơn, hãy diễn giải theo burn rate thay vì gọi đó là phần budget đã tiêu thụ trong cả kỳ.

## 17. Burn rate là gì?

Burn rate đo tốc độ tiêu thụ error budget so với tốc độ cho phép:

\[
BurnRate =
\frac{ObservedErrorRatio}
{AllowedErrorRatio}
\]

Với SLO 99,9%, allowed error ratio là 0,001.

- Error ratio 0,001 → burn rate 1.
- Error ratio 0,005 → burn rate 5.
- Error ratio 0,0144 → burn rate 14,4.

Burn rate 1 có nghĩa budget được tiêu thụ đúng tốc độ để vừa hết vào cuối kỳ SLO nếu tỷ lệ lỗi giữ nguyên. Burn rate 14,4 nghĩa tốc độ tiêu thụ nhanh gấp 14,4 lần tốc độ cho phép.

Burn rate nên được tính trên event-based SLI có denominator đúng. Không lấy error rate của model operations làm burn rate của user request SLO.

## 18. Chọn ngưỡng alert từ budget thay vì đoán một con số

Một alert threshold cần trả lời:

- Tốc độ lỗi hiện tại sẽ tiêu thụ bao nhiêu phần budget?
- Trong bao lâu budget sẽ cạn nếu không xử lý?
- Mức ảnh hưởng người dùng đã đủ lớn để page chưa?
- Có đủ traffic/sample để kết luận không?
- Alert có hành động cụ thể và người chịu trách nhiệm không?

Ví dụ với SLO 99,9% và budget 0,1%:

- Burn rate 14,4 tương đương error ratio 1,44%.
- Burn rate 6 tương đương error ratio 0,6%.
- Burn rate 1 tương đương error ratio 0,1%.

Không đặt ngưỡng 5% cho mọi route chỉ vì con số dễ nhớ. Một route thanh toán hoặc workflow có side effect có thể cần ngưỡng thấp hơn route tìm kiếm không quan trọng.

Ngưỡng cuối cùng phải được hiệu chỉnh bằng traffic thực, mức độ ảnh hưởng, thời gian phát hiện và khả năng phản ứng của đội vận hành.

## 19. Multi-window, multi-burn-rate alerting

Một cửa sổ ngắn có thể báo động vì một spike thoáng qua. Một cửa sổ dài có thể phát hiện quá muộn. Multi-window alert yêu cầu cả cửa sổ dài và ngắn cùng vượt ngưỡng.

Ví dụ tham khảo cho SLO 99,9%:

| Mức | Burn rate | Cửa sổ dài | Cửa sổ ngắn | Ý nghĩa |
|---|---:|---:|---:|---|
| Page nhanh | 14,4x | 1 giờ | 5 phút | Tiêu thụ khoảng 2% budget 30 ngày trong 1 giờ |
| Page chậm | 6x | 6 giờ | 30 phút | Tiêu thụ khoảng 5% budget trong 6 giờ |
| Ticket | 3x | 1 ngày | 2 giờ | Tiêu thụ khoảng 10% budget trong 1 ngày |
| Theo dõi dài hạn | 1x | 3 ngày | 6 giờ | Budget được tiêu thụ đúng tốc độ cho phép; theo dõi xu hướng dài hạn |

Các cửa sổ và burn rates là mô hình tham khảo từ Google SRE. Điều chỉnh theo SLO period, traffic, độ trễ phát hiện và mục tiêu trực vận hành. [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/).

## 20. PromQL: availability error ratio và burn rate

Giả sử application counter là:

~~~text
app_ai_user_requests_total{route,result}
~~~

Trong đó result có good và bad.

Error ratio:

~~~promql
sum(rate(app_ai_user_requests_total{result="bad"}[5m]))
/
sum(rate(app_ai_user_requests_total[5m]))
~~~

Burn rate cho SLO 99,9%:

~~~promql
(
  sum(rate(app_ai_user_requests_total{result="bad"}[5m]))
  /
  sum(rate(app_ai_user_requests_total[5m]))
) / 0.001
~~~

Trong production, nên tạo recording rule cho error ratio và burn rate để tái sử dụng trong dashboard/alerts. Nếu không có eligible events trong cửa sổ, không diễn giải tỷ lệ là zero error; panel cần hiển thị no data và synthetic check có thể giúp phát hiện service không có traffic.

## 21. Prometheus alert rule cho page nhanh

Ví dụ multi-window alert 14,4x cho SLO 99,9%:

~~~yaml
groups:
  - name: spring-ai-slo
    rules:
      - alert: AiRequestErrorBudgetBurnFast
        expr: |
          (
            (
              sum(rate(app_ai_user_requests_total{result="bad"}[1h]))
              /
              sum(rate(app_ai_user_requests_total[1h]))
            ) > (14.4 * 0.001)
          )
          and
          (
            (
              sum(rate(app_ai_user_requests_total{result="bad"}[5m]))
              /
              sum(rate(app_ai_user_requests_total[5m]))
            ) > (14.4 * 0.001)
          )
          and
          sum(increase(app_ai_user_requests_total[5m])) > 100
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "AI request SLO budget is burning quickly"
          description: "Inspect user-facing errors, ChatClient traces and recent releases."
~~~

Rule này là ví dụ cho event-based SLO 99,9%. Điều kiện traffic tối thiểu 100 events trong 5 phút chỉ là ví dụ; với traffic thấp, cần synthetic monitoring hoặc cửa sổ khác.

Cả cửa sổ 1 giờ và 5 phút phải vượt threshold để alert fire. for: 2m giúp tránh alert từ một spike rất ngắn. Đừng tăng for quá dài khiến page bị trễ.

## 22. Alert chậm hơn cho burn rate kéo dài

Ví dụ ticket ở burn rate 6x trên 6 giờ và 30 phút:

~~~yaml
- alert: AiRequestErrorBudgetBurnSlow
  expr: |
    (
      sum(rate(app_ai_user_requests_total{result="bad"}[6h]))
      /
      sum(rate(app_ai_user_requests_total[6h]))
    ) > (6 * 0.001)
    and
    (
      sum(rate(app_ai_user_requests_total{result="bad"}[30m]))
      /
      sum(rate(app_ai_user_requests_total[30m]))
    ) > (6 * 0.001)
  for: 10m
  labels:
    severity: ticket
  annotations:
    summary: "AI request error budget is burning over a sustained period"
    description: "Review recurring failures and plan corrective work."
~~~

Page alert phù hợp khi cần hành động ngay. Ticket alert phù hợp khi lỗi kéo dài nhưng chưa cần đánh thức on-call. Hãy cấu hình routing theo severity và owner.

## 23. Chọn ngưỡng latency SLO

Latency SLO nên dựa trên trải nghiệm của route và loại tương tác.

| Route/UX | SLI | SLO minh họa |
|---|---|---:|
| Chat synchronous | Request hoàn tất dưới 4 giây | 95% |
| RAG answer | Request hoàn tất dưới 6 giây | 95% |
| Streaming chat | TTFT dưới 1,5 giây | 95% |
| Streaming chat | Stream hoàn tất dưới 8 giây | 95% |
| Agent workflow | Task hoàn tất dưới 15 giây | 90% |

Đây là ví dụ để bắt đầu thảo luận. Hãy đo baseline trên traffic thật, phân nhóm route và hỏi người dùng ngưỡng nào làm trải nghiệm không còn chấp nhận được.

Không lấy model P95 làm latency SLO của người dùng. ChatClient/HTTP duration có thể bao gồm advisors, tools, retrieval và post-processing. Dùng component latency để chẩn đoán khi user-facing SLI xấu.

## 24. Chọn ngưỡng quality SLO và release gate

Quality threshold phụ thuộc rủi ro nghiệp vụ. Một trợ lý tra cứu nội bộ và một workflow tạo giao dịch không nên dùng cùng tiêu chuẩn.

Ví dụ policy:

| Criterion | Offline release gate | Online sampled target |
|---|---:|---:|
| Factuality pass rate | >= 95% | >= 92% |
| Relevance pass rate | >= 94% | >= 90% |
| Retrieval recall@5 | >= 90% | Theo dõi trend |
| Tool selection accuracy | >= 97% | >= 95% |
| Citation correctness | >= 98% | >= 95% |

Ngoài pass rate, đặt điều kiện:

- Minimum evaluated sample size.
- Completion coverage target.
- Judge attempt error threshold.
- Judge-human agreement/false-pass limit.
- Fixed dataset, rubric, judge version trong một đợt so sánh.

Release gate dùng kết quả evaluation run cố định và có thể chặn promotion. Online target dùng sample production và cảnh báo khi đủ dữ liệu. Không page on-call chỉ vì một offline run chưa chạy xong.

## 25. Alert quality regression có điều kiện sample

Giả sử ứng dụng xuất counter terminal outcomes:

~~~text
app_ai_eval_cases_total{criterion,outcome,source,prompt_version}
app_ai_eval_applicable_cases_total{criterion,source}
~~~

Ví dụ factuality pass rate dưới 90%, với tối thiểu 500 evaluated cases trong 24 giờ:

~~~yaml
groups:
  - name: spring-ai-quality
    rules:
      - alert: FactualityPassRateBelowTarget
        expr: |
          (
            sum by (prompt_version) (increase(app_ai_eval_cases_total{
              criterion="factuality",
              outcome="pass",
              source="online_sampled"
            }[24h]))
            /
            sum by (prompt_version) (increase(app_ai_eval_cases_total{
              criterion="factuality",
              outcome=~"pass|fail",
              source="online_sampled"
            }[24h]))
          ) < 0.90
          and
          sum by (prompt_version) (increase(app_ai_eval_cases_total{
            criterion="factuality",
            outcome=~"pass|fail",
            source="online_sampled"
          }[24h])) >= 500
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Online factuality quality is below target"
          description: "Inspect failed cases, prompt/model versions and judge calibration."
~~~

Ngưỡng 90% và 500 cases là ví dụ. Nếu quality pass rate thấp do judge error hoặc coverage giảm, hãy xử lý evaluator-health alert riêng và đánh dấu quality data incomplete.

Với offline gate, dùng evaluation store/run report thay vì sliding Prometheus window. Một release candidate phải được đánh giá trên cohort cố định.

## 26. Đặt SLO cho coverage và judge error

Ví dụ online evaluation SLO:

- Completion coverage ít nhất 95% trên selected applicable cases.
- Judge attempt error rate không quá 2%.
- Pending age P95 dưới 5 phút.
- Invalid judge output không quá 0,5%.

Để phân tích cùng cohort, attempt counter cần có các labels criterion và source; nếu hệ thống chưa xuất source, hãy bổ sung label hữu hạn này hoặc tách metric theo pipeline trước khi dùng query bên dưới.

PromQL completion coverage cho factuality trên online sampled cases:

~~~promql
sum(rate(app_ai_eval_cases_total{
  criterion="factuality",
  source="online_sampled",
  outcome=~"pass|fail"
}[1h]))
/
sum(rate(app_ai_eval_applicable_cases_total{
  criterion="factuality",
  source="online_sampled"
}[1h]))
~~~

PromQL judge attempt error rate cho cùng cohort:

~~~promql
sum(rate(app_ai_eval_attempts_total{
  criterion="factuality",
  source="online_sampled",
  result=~"error|invalid"
}[10m]))
/
sum(rate(app_ai_eval_attempts_total{
  criterion="factuality",
  source="online_sampled"
}[10m]))
~~~

Đây là hai SLI khác nhau. Coverage giảm có thể do pending backlog hoặc skip policy; attempt error tăng có thể được retry thành công. Theo dõi breakdown để chọn hành động.

## 27. Cost budget và efficiency threshold

Không phải mọi cost spike đều là incident. Hãy kết hợp:

- Daily spend so với budget.
- Forecast cuối kỳ.
- Cost per successful task.
- Tokens per task.
- Model operations per task.
- Quality score theo cùng feature/cohort.

Ví dụ cảnh báo dự báo feature vượt budget:

~~~promql
sum by (feature) (
  rate(app_ai_model_cost_usd_total[1h])
) * 86400
>
on (feature)
app_ai_feature_daily_budget_usd
~~~

Forecast này giả định cost rate hiện tại giữ nguyên cả ngày. Với traffic có seasonality, hãy so với baseline cùng giờ hoặc dùng forecast phù hợp.

Một threshold cost/task có thể cảnh báo khi tăng hơn 30% so với baseline cùng feature trong hai cửa sổ liên tiếp, đồng thời có tối thiểu 500 successful tasks. Con số 30% và sample 500 chỉ là ví dụ; cần xem độ biến động tự nhiên và giá trị nghiệp vụ.

Không hạ model hoặc rút ngắn context chỉ để giảm cost nếu factuality/relevance giảm vượt quality gate.

## 28. Chọn severity: page, ticket, warning và release gate

| Severity | Khi nào dùng | Hành động |
|---|---|---|
| Page | User-facing SLO burn nhanh, outage hoặc hard budget risk | On-call điều tra ngay |
| Ticket | Budget burn chậm hoặc lỗi lặp lại kéo dài | Tạo công việc có owner |
| Warning | Provider 429, P95 tăng hoặc queue tăng nhưng SLO còn tốt | Theo dõi và điều tra trong giờ làm |
| Release gate | Offline quality/cost/latency threshold không đạt | Không promote candidate |
| Quality review | Human agreement giảm hoặc judge drift | Review calibration set và rubric |

Một alert tốt cần có:
- Owner và severity rõ.
- Điều kiện fire gắn với SLO hoặc hành động cụ thể.
- Runbook và dashboard link.
- Thông tin route/provider/model/release đủ để định hướng điều tra.
- Cách resolve và tiêu chí clear alert.

Tránh alert cho mọi diagnostic metric. Alert fatigue khiến on-call bỏ lỡ tín hiệu quan trọng.

## 29. Error budget policy: khi nào giảm tốc release?

Error budget là công cụ quyết định tốc độ thay đổi hệ thống.

Ví dụ policy minh họa cho serving SLO:

| Trạng thái budget | Chính sách release |
|---|---|
| Dưới 50% budget đã dùng và không có burn alert | Release theo quy trình bình thường |
| 50–80% budget đã dùng sớm trong kỳ | Tăng canary, review thay đổi rủi ro cao |
| Trên 80% budget đã dùng sớm trong kỳ | Ưu tiên reliability fixes, hạn chế rollout lớn |
| Budget đã cạn | Tạm dừng thay đổi không thiết yếu cho đến khi SLO phục hồi hoặc có quyết định ngoại lệ |

Các mức là ví dụ, cần được đội sản phẩm và vận hành thống nhất. Với AI quality, có thể áp dụng policy riêng: factuality gate fail thì chặn prompt/model release ngay cả khi availability budget còn dư.

Không dùng availability budget để bù trừ cho quality regression. Hai loại rủi ro cần budget/gate riêng.

## 30. Threshold cần có minimum traffic và missing-data policy

Tỷ lệ từ 3 requests không có độ tin cậy như tỷ lệ từ 30.000 requests.

Alert nên có:
- Minimum event count.
- Cửa sổ dài/ngắn phù hợp.
- No-data handling.
- Synthetic monitoring cho route ít traffic.
- Quy tắc cho counter reset hoặc scrape gaps.
- Cohort/route filter đúng scope.

Nếu denominator bằng zero, pass rate hoặc error ratio không xác định. Không thay no data bằng 0% error hay 0% quality. Dashboard nên hiển thị N/A.

Với online quality, minimum sample size phải đủ để phát hiện mức regression có ý nghĩa. Với offline release evaluation, chạy full required dataset hoặc ghi rõ missing cases trước khi gate.

## 31. Chọn ngưỡng từ baseline và mức chấp nhận của sản phẩm

Quy trình thiết kế threshold:

1. Xác định user journey và event boundary.
2. Đo baseline trên dữ liệu đại diện trong một khoảng đủ dài.
3. Xem distribution, seasonality và tail behavior.
4. Xác định mức chất lượng tối thiểu chấp nhận được với product owner.
5. Định nghĩa good/bad event và denominator.
6. Chọn SLO target, window và error budget.
7. Chọn burn-rate threshold theo thời gian phản ứng cần thiết.
8. Thêm minimum traffic/sample và no-data behavior.
9. Gắn alert với owner/runbook.
10. Chạy thử trên dữ liệu lịch sử và điều chỉnh trước khi page thật.

Không đặt SLO bằng đúng P99 tốt nhất của tuần vừa rồi. Target cần đủ ổn định để đội biết khi nào dịch vụ thực sự không đạt lời hứa.

## 32. Ví dụ bộ SLO cho một RAG assistant

Một bộ SLO minh họa:

| SLI | Target | Window/Cohort |
|---|---:|---|
| User request availability | 99,9% | Rolling 30 days |
| RAG response latency under 6s | 95% | Rolling 30 days |
| Streaming TTFT under 1,5s | 95% | Rolling 30 days |
| Online factuality pass rate | >= 92% | 24h, minimum 500 evaluated cases |
| Online completion coverage | >= 95% | 24h |
| Judge attempt error rate | <= 2% | 10m/1h |
| Offline factuality release gate | >= 95% | Fixed golden dataset |
| Offline relevance release gate | >= 94% | Fixed golden dataset |
| Cost per successful RAG task | <= budget | Daily/weekly |

Các con số cần được thay bằng target được xác nhận từ UX, risk appetite, baseline và economics của sản phẩm.

Không gộp các SLO thành một score. Khi availability đạt nhưng factuality fail, hệ thống vẫn có thể không đáp ứng lời hứa của sản phẩm.

## 33. Runbook khi SLO vi phạm

Khi alert fire:

1. Xác nhận alert đúng service, route và time window.
2. Xem SLI numerator/denominator và error budget còn lại.
3. Mở dashboard traffic, latency, errors và saturation.
4. Phân tách ChatClient, ChatModel, advisor, tool và VectorStore.
5. Kiểm tra provider 429/5xx, timeout, retry và fallback.
6. Mở trace đại diện để xác định span gây chậm/lỗi.
7. Với quality alert, kiểm tra evaluated sample, coverage, judge error và calibration.
8. So prompt/model/tool-set/index/rubric version với baseline.
9. Quyết định rollback, giảm canary, đổi provider, giới hạn concurrency hoặc sửa pipeline.
10. Ghi incident timeline, failed cases, trace IDs và quyết định.

Sau khi xử lý, kiểm tra SLI phục hồi qua cửa sổ ngắn và dài. Không resolve alert chỉ vì một điểm scrape tốt.

## 34. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Alert theo CPU thay vì user outcome | Page khi người dùng chưa bị ảnh hưởng | Alert theo SLI, dùng CPU để chẩn đoán |
| Dùng model P95 làm API SLO | Bỏ qua advisor/tool/RAG overhead | Đo latency tại user boundary |
| Không định nghĩa eligible events | Denominator thay đổi tùy người viết query | Viết measurement contract |
| Coi HTTP 200 là AI success | Bỏ qua answer sai | Thêm business/quality SLI |
| Dùng một SLO cho offline và online | Cohort không tương đương | Tách release gate và online SLI |
| Chỉ có pass rate | Judge outage che coverage | Pair với coverage và judge health |
| Alert theo P95 spike đơn lẻ | False positive | Dùng SLO ratio và multi-window burn rate |
| Không có minimum sample | Tỷ lệ nhỏ gây alert | Đặt traffic/sample floor |
| Dùng event budget nhưng báo phút | Sai đơn vị budget | Tách event-based và time-based |
| Đặt for quá dài | Phát hiện chậm | Chọn window theo thời gian phản ứng |
| Gộp quality và availability budget | Một chiều che chiều kia | SLO/gate riêng |
| Không có owner/runbook | Alert không dẫn tới hành động | Gắn owner và playbook |

## 35. Bài tập tự kiểm tra

### Bài 1 — Tính error budget

SLO availability là 99,9% với 2.000.000 eligible requests trong kỳ. Error budget là bao nhiêu bad requests?

**Đáp án:** Allowed error ratio = 0,001. Budget = 2.000.000 × 0,001 = 2.000 bad requests.

### Bài 2 — Tính burn rate

Với SLO 99,9%, observed error ratio là 0,6%. Burn rate bằng bao nhiêu?

**Đáp án:** 0,006 / 0,001 = 6x.

### Bài 3 — Availability tốt nhưng latency xấu

99,95% requests không có server error, nhưng chỉ 70% hoàn tất trong 4 giây. SLI nào vi phạm?

**Đáp án:** Availability đạt mục tiêu 99,9%, nhưng latency SLI 95% dưới 4 giây không đạt. Hai SLI đo hai thuộc tính riêng.

### Bài 4 — Judge outage

Factuality pass rate là 97%, nhưng completion coverage chỉ 40% và judge error rate là 35%. Có nên kết luận quality SLO đạt?

**Đáp án:** Không. Pass rate chỉ phản ánh sample được chấm; coverage và judge health đang vi phạm. Quality result phải được đánh dấu incomplete.

### Bài 5 — Chọn alert window

Một spike lỗi kéo dài 2 phút rồi tự hết, nhưng 1h burn rate cao và 5m burn rate đã trở lại bình thường. Multi-window 1h/5m có nên page?

**Đáp án:** Không nếu điều kiện cửa sổ ngắn không còn vượt threshold. Đây là mục đích của multi-window: lọc spike ngắn không còn tiếp diễn.

### Bài 6 — Event budget hay time budget?

SLO 99,9% theo request events trong tháng. Có thể nói dịch vụ được phép downtime 43,2 phút không?

**Đáp án:** Không. 43,2 phút chỉ là diễn giải cho time-based availability trong 30 ngày; event-based budget tính theo số request xấu cho phép.

### Bài 7 — Cost tăng cùng workload

Daily spend tăng 50%, task volume tăng 50%, cost per successful task giữ nguyên và quality không đổi. Có phải cost efficiency regression không?

**Đáp án:** Chưa. Spend tổng tăng do workload tăng; efficiency theo task không đổi. Cần kiểm tra budget tổng và capacity.

### Bài 8 — Release gate

Candidate model cải thiện relevance nhưng factuality dưới release threshold. Availability SLO đang rất tốt. Có nên promote?

**Đáp án:** Không nếu factuality là required gate. Availability budget không thay thế quality gate.

## 36. Checklist trước khi bật alert production

- [ ] Mỗi SLI có measurement contract và owner?
- [ ] Event unit và eligible denominator đã rõ?
- [ ] Availability được đo ở user boundary?
- [ ] Latency SLI dùng ngưỡng phù hợp từng route/UX?
- [ ] Streaming có TTFT và completion metrics nếu cần?
- [ ] Quality pass rate đi kèm coverage và judge health?
- [ ] Offline release gate tách khỏi online sampled SLO?
- [ ] SLO target dựa trên UX, baseline và risk?
- [ ] Error budget đúng đơn vị event-based/time-based?
- [ ] Burn rate và multi-window thresholds đã được mô phỏng?
- [ ] Alert có minimum traffic/sample và no-data policy?
- [ ] Cost budget có rate card/version và unknown-cost handling?
- [ ] Page, ticket, warning và release gate có routing riêng?
- [ ] Mỗi alert có owner, dashboard link và runbook?
- [ ] Đã chạy thử rule trên dữ liệu lịch sử?
- [ ] Đã xác định error budget policy khi budget cạn?
- [ ] Đã diễn tập quy trình điều tra và rollback?

## 37. Tài liệu tham khảo

1. [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): error budget, burn rate và multi-window alerting.
2. [Google SRE Book — Service Level Objectives](https://sre.google/sre-book/service-level-objectives/): SLI, SLO, SLA và cách chọn mục tiêu.
3. [Prometheus — Alerting](https://prometheus.io/docs/practices/alerting/): alert trên triệu chứng, routing và giảm alert noise.
4. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): histogram buckets và latency quantiles.
5. [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient, ChatModel, advisor, tool và VectorStore observations.
6. [Spring AI 2.1.0 — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator, RelevancyEvaluator và FactCheckingEvaluator.
7. [OpenTelemetry — Signals](https://opentelemetry.io/docs/concepts/signals/): metrics, traces, logs và context propagation.

*Các SLO targets, quality thresholds, PromQL và alert windows trong bài là ví dụ thiết kế. Trước khi bật page production, hãy xác nhận event contract, denominator, histogram buckets, traffic floor, owner và runbook bằng dữ liệu thực tế. SLO cần được xem xét định kỳ khi UX, traffic, provider, pricing hoặc mức rủi ro nghiệp vụ thay đổi.*
