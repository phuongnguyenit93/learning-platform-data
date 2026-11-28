# Phân biệt lỗi từng yêu cầu với suy giảm trên cả nhóm

## 1. Một lỗi đơn lẻ chưa phải là suy giảm toàn hệ thống

Một người dùng gửi câu hỏi RAG và nhận HTTP 500. Trace cho thấy lần gọi model bị timeout. Đây là một request thất bại cần được điều tra. Nhưng chỉ từ request đó, chưa thể kết luận toàn bộ dịch vụ đang suy giảm.

Ở chiều ngược lại, dashboard có thể cho thấy tỷ lệ lỗi toàn hệ thống vẫn chỉ 0,2%, trong khi một route quan trọng hoặc một model family đã tăng lỗi lên 15%. Tổng hợp toàn hệ thống có thể che khuất cohort bị ảnh hưởng.

Vì vậy, cần phân biệt hai lớp quan sát:

- **Request-level diagnosis:** điều tra một request cụ thể, tìm nguyên nhân trong trace, log có kiểm soát và event record.
- **Cohort-level monitoring:** phát hiện một nhóm request có hành vi xấu đi theo route, model, prompt version, release, region hoặc loại tác vụ.

Hai lớp bổ sung cho nhau. Metric tổng hợp phát hiện nơi cần điều tra; trace cụ thể giúp giải thích vì sao request đó thất bại. Không dùng một trace đơn lẻ để kết luận xu hướng, cũng không dùng một tỷ lệ tổng hợp để giải thích nguyên nhân của từng request.

Bài thuộc chương **Dashboard và cảnh báo** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module tập trung đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm theo từng phiên bản prompt, model và pipeline.

Sau bài, bạn có thể:

1. Phân biệt lỗi của một request với regression trên một cohort.
2. Điều tra request cụ thể bằng trace, span, event và phiên bản thực thi.
3. Định nghĩa cohort có mẫu số nhất quán và labels hữu hạn.
4. Phân tích error rate, latency distribution và quality score theo nhóm.
5. Nhận biết ảnh hưởng của traffic mix, sampling bias và Simpson's paradox.
6. Chọn baseline, minimum sample size và cách phát hiện thay đổi có ý nghĩa.
7. Dùng exemplars/traces để đi từ metric tổng hợp tới request đại diện.
8. Thiết kế alert và runbook phù hợp với phạm vi ảnh hưởng.

## 2. Hai câu hỏi vận hành khác nhau

| Câu hỏi | Phạm vi | Bằng chứng chính | Hành động |
|---|---|---|---|
| Request này thất bại vì sao? | Một request hoặc một task | Trace, span events, exception class, request outcome | Debug và khắc phục nguyên nhân cụ thể |
| Cohort này có đang suy giảm không? | Một nhóm request trong cửa sổ | SLI, histogram, counts, baseline và sample size | Alert, giới hạn rollout, rollback hoặc điều tra hệ thống |
| Chỉ một khách hàng bị ảnh hưởng? | Một tenant hoặc workload được phép quan sát | Support case, trace được cấp quyền, cohort đã ẩn danh | Xử lý theo phạm vi và kiểm tra ảnh hưởng rộng hơn |
| Một quality case bị fail? | Một evaluation case | Input, reference, response, judge verdict | Review case và evidence |
| Factuality của một release giảm? | Nhiều cases cùng cohort | Evaluation run, pass rate, confidence interval | Chặn release hoặc rollback candidate |

Một request lỗi có thể là outlier ngẫu nhiên, input đặc biệt, một provider attempt thất bại nhưng fallback thành công, hoặc dấu hiệu đầu tiên của outage. Cần dùng thêm dữ liệu để phân biệt.

Nếu request liên quan tới an toàn, bảo mật, mất dữ liệu hoặc tác vụ có side effect không thể đảo ngược, một sự kiện đơn lẻ vẫn có thể cần xử lý incident ngay. Quy tắc “không page từ một request” không áp dụng cho mọi loại rủi ro.

## 3. Request-level record cần lưu những gì?

Một record đủ để điều tra request nên có các trường vận hành có cấu trúc:

| Trường | Mục đích |
|---|---|
| request_id | Tra cứu request trong log/event store |
| trace_id | Mở distributed trace |
| route / feature | Xác định user journey |
| outcome | Kết quả cuối cùng ở user boundary |
| error_class | Phân loại lỗi ổn định |
| started_at / duration | Thời điểm và thời lượng |
| release_version | Phiên bản ứng dụng |
| prompt_version | Prompt thực thi |
| requested_model / response_model | Model yêu cầu và model thực tế |
| retriever/index_version | Phiên bản retrieval/index |
| tool_set_version | Bộ công cụ và cấu hình |
| evaluation_run/case reference | Liên kết kết quả đánh giá nếu có |

Đây là schema ứng dụng đề xuất, không phải một payload mặc định của Spring AI.

Không lưu raw prompt, completion, retrieved document hoặc tool arguments vào metric labels. Nếu nội dung cần thiết cho điều tra, hãy lưu trong hệ thống có quyền truy cập, redaction, retention và audit phù hợp. Một trace ID không nên được đưa thành Prometheus label vì mỗi request có giá trị riêng.

## 4. Request-level trace: lần theo đường đi của một request

Một trace có thể thể hiện request qua nhiều thành phần:

~~~text
HTTP POST /rag/answer
  └─ application.user-turn
      └─ ChatClient.call
          ├─ advisor.memory
          ├─ advisor.retrieval
          │   └─ VectorStore.similaritySearch
          ├─ ChatModel.call
          ├─ tool.searchPolicy
          └─ ChatModel.call
      └─ response.serialize
  └─ async.evaluation.enqueue
~~~

Khi một request chậm hoặc thất bại, trace giúp trả lời:

- Span nào chiếm phần lớn thời gian?
- Model operation nào timeout hoặc bị retry?
- Retrieval có trả quá nhiều context hoặc bị chậm không?
- Tool nào lỗi, và lỗi đó có làm user request thất bại không?
- Model fallback có được sử dụng không?
- Request đã trả kết quả cho người dùng trước khi evaluation chạy chưa?

Trace là bằng chứng ở cấp execution. Nó không tự cho biết tỷ lệ lỗi của cohort. Cần nối trace với metric qua exemplar hoặc liên kết log có kiểm soát.

## 5. Phân loại request outcome ở user boundary

Hãy ghi một terminal outcome cho mỗi user request theo contract của endpoint.

Ví dụ:

~~~text
good
bad_timeout
bad_server_error
bad_provider_failure
bad_tool_failure
bad_invalid_response
cancelled
rejected_invalid_input
rejected_unauthorized
~~~

Có thể chuẩn hóa thành hai giá trị metric là good/bad và lưu error_class chi tiết trong event store. Nếu cancelled hoặc rejected không nằm trong SLI, phải ghi rõ exclusion policy và vẫn theo dõi chúng riêng.

Một request có provider attempt lỗi nhưng fallback thành công có thể là good ở user boundary. Diagnostic metrics vẫn cần ghi provider failure và fallback count để không che khuất dependency đang suy yếu.

Không tăng user request failure counter cho từng model retry. Một request có ba model attempts và một lần fallback thành công vẫn chỉ là một user request outcome.

## 6. Cohort là gì và vì sao cần định nghĩa rõ?

Cohort là nhóm events có chung đặc điểm đủ quan trọng để so sánh. Ví dụ:

- Tất cả request RAG trong một region.
- Request chạy model family A.
- Request sử dụng prompt version v12.
- Streaming requests trên route chat.
- Evaluation cases thuộc factuality của dataset version 4.

Một cohort cần có:

1. Quy tắc membership rõ ràng.
2. Cùng event unit.
3. Cùng outcome definition.
4. Cùng cửa sổ thời gian.
5. Mẫu số có thể so sánh.
6. Đủ số mẫu để diễn giải.

Không so sánh tỷ lệ lỗi của model operations với tỷ lệ lỗi của user requests. Một model operation là một thành phần bên trong request; một request có thể tạo nhiều model operations.

## 7. Chọn cohort dimensions có ích

Các dimensions thường hữu ích cho Spring AI:

| Dimension | Ví dụ | Câu hỏi |
|---|---|---|
| route | chat, rag, agent | Route nào bị ảnh hưởng? |
| feature | support_chat, document_qa | Tính năng nào suy giảm? |
| model_family | model-small, model-large | Model family nào có lỗi? |
| prompt_version | prompt-v12, prompt-v13 | Release prompt nào gây thay đổi? |
| app_release | 2026.11.27-2 | Có liên hệ với deployment không? |
| region | ap-southeast, eu-west | Có lỗi theo khu vực không? |
| stream_mode | true, false | Streaming có khác synchronous không? |
| locale | vi, en, ja | Ngôn ngữ nào bị ảnh hưởng? |
| task_type | answer, summarize, classify | Loại tác vụ nào suy giảm? |

Chỉ dùng dimensions có tập giá trị hữu hạn và được kiểm soát. Không đưa request ID, trace ID, conversation ID, user ID, raw prompt hoặc document ID vào metric labels.

Nếu cần phân tích theo một tenant cụ thể, truy vấn event store hoặc hệ thống support có quyền truy cập thay vì tạo một time series cho từng tenant.

## 8. Đo lỗi theo cohort thay vì chỉ toàn hệ thống

Giả sử metric do ứng dụng định nghĩa:

~~~text
app_ai_user_requests_total{route,outcome,eligible,model_family,prompt_version}
~~~

Trong SLI request, eligible=true là request hợp lệ thuộc denominator; outcome được chuẩn hóa thành good hoặc bad. Request bị loại theo policy có eligible=false hoặc được ghi ở metric riêng. Các error classes chi tiết được lưu trong event/log/trace, không tạo thêm outcome label tùy ý.

Tỷ lệ request xấu theo route:

~~~promql
sum by (route) (
  rate(app_ai_user_requests_total{outcome="bad",eligible="true"}[5m])
)
/
sum by (route) (
  rate(app_ai_user_requests_total{eligible="true"}[5m])
)
~~~

Tỷ lệ request xấu theo model family:

~~~promql
sum by (model_family) (
  rate(app_ai_user_requests_total{outcome="bad",eligible="true"}[5m])
)
/
sum by (model_family) (
  rate(app_ai_user_requests_total{eligible="true"}[5m])
)
~~~

Tỷ lệ request xấu theo prompt version:

~~~promql
sum by (prompt_version) (
  rate(app_ai_user_requests_total{outcome="bad",eligible="true"}[15m])
)
/
sum by (prompt_version) (
  rate(app_ai_user_requests_total{eligible="true"}[15m])
)
~~~

Các query giả định metric được increment một lần cho mỗi terminal user request và mỗi request có đúng một route/model/prompt cohort. Nếu request có nhiều model calls, model_family ở user request metric nên đại diện model chính sách hoặc model cuối cùng theo một quy tắc đã định; để phân tích từng model attempt, dùng metric riêng ở model-operation boundary.

## 9. Xem cả tỷ lệ và số lượng

Tỷ lệ lỗi không cho biết quy mô tuyệt đối.

Ví dụ:

| Cohort | Requests | Bad requests | Error rate |
|---|---:|---:|---:|
| Route A | 100 | 10 | 10% |
| Route B | 100.000 | 500 | 0,5% |

Route A có tỷ lệ cao hơn nhưng Route B tạo ra nhiều bad requests hơn. Mức ưu tiên phụ thuộc impact, severity và khả năng xử lý, không chỉ sort theo error rate.

Dashboard nên có ít nhất:

- Total requests.
- Good requests.
- Bad requests.
- Error ratio.
- Bad request count trong cửa sổ.
- Cohort share của tổng traffic.

Nếu cohort có 1 bad request trên 2 requests, error rate là 50% nhưng sample rất nhỏ. Nếu cohort có 10.000 bad trên 100.000, tỷ lệ chỉ 10% nhưng ảnh hưởng lớn.

## 10. Latency của một request và latency của cả nhóm

Request-level latency cho biết một request cụ thể mất bao lâu và span nào chiếm thời gian. Cohort-level latency mô tả phân phối của nhiều requests.

Không lấy trung bình P95 của từng instance hoặc từng route để tạo P95 toàn hệ thống. Với histogram buckets, hãy cộng bucket rates trước rồi mới tính quantile.

P95 theo route:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(app_ai_request_duration_seconds_bucket{eligible="true"}[5m])
  )
)
~~~

P99 theo model family:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, model_family) (
    rate(app_ai_request_duration_seconds_bucket{eligible="true"}[5m])
  )
)
~~~

Query P99 theo model family giả định request-level histogram có label model_family theo cùng quy tắc attribution đã nêu cho user request metric. Nếu một request gọi nhiều models và không có model đại diện rõ ràng, hãy đo model-operation histogram riêng thay vì gắn một model tùy ý cho toàn request.

Histogram phải được bật với bucket boundaries phù hợp. Nếu bucket không có ngưỡng quan trọng cho SLO, hãy cấu hình lại histogram hoặc đo good-event ratio trực tiếp.

## 11. Một request chậm không có nghĩa P95 đã xấu

P95 là giá trị mà khoảng 95% observations không vượt qua trong cửa sổ đo. Một request 60 giây có thể là outlier trong cohort có hàng nghìn request; nó cần điều tra, nhưng chưa chắc làm P95 thay đổi đáng kể.

Ngược lại, nhiều request tăng từ 1 giây lên 3 giây có thể làm P95 tăng rõ dù không có request nào timeout.

Dùng hai góc nhìn:

- Request trace: tìm nguyên nhân của outlier.
- Histogram/percentile: xác định tail latency của cohort có thay đổi không.

P95 và P99 cũng cần sample đủ lớn. Khi traffic rất thấp, percentile có thể dao động mạnh hoặc không có ý nghĩa.

## 12. So sánh latency component với user latency

Một request có thể gồm:

~~~text
Total user latency
  = authentication
  + advisor chain
  + VectorStore
  + model operation(s)
  + tool execution(s)
  + serialization/network
~~~

Các thành phần có thể chạy tuần tự hoặc song song; công thức trên chỉ là mô hình phân rã khái niệm.

Spring AI có observations cho ChatClient, ChatModel, tools và VectorStore. ChatClient operation duration giúp nhìn invocation; model operation duration giúp xem provider; trace cho thấy thứ tự và thời gian của từng span.

Nếu user latency tăng nhưng model latency ổn định, hãy xem retrieval, tool, advisor, queue hoặc response serialization. Nếu model latency tăng theo một provider/model family, kiểm tra quota, network, token size, retries và provider status.

## 13. Chất lượng của một case và chất lượng của cohort

Một evaluation case có thể được xem xét riêng:

- Query và expected answer.
- Response thực tế.
- Retrieved context/reference.
- Criterion và rubric.
- Judge verdict, score và evidence.
- Human review nếu có.

Cohort quality cần tập hợp nhiều case có cùng tiêu chí và điều kiện so sánh:

\[
PassRate_{cohort} =
\frac{PASS_{cohort}}
{PASS_{cohort} + FAIL_{cohort}}
\]

ERROR, INVALID, SKIPPED, NOT_APPLICABLE, INCONCLUSIVE và PENDING không được đưa vào pass-rate denominator. Chúng phải xuất hiện trong coverage và evaluator-health panels.

Một case fail cho biết có ít nhất một failure cần review. Chỉ khi tỷ lệ hoặc phân phối trên cohort thay đổi với sample đủ lớn mới kết luận quality regression.

## 14. Cohort quality theo prompt và model version

Metric ví dụ:

~~~text
app_ai_eval_cases_total{criterion,outcome,source,prompt_version,model_family}
~~~

Factuality pass rate theo prompt version:

~~~promql
sum by (prompt_version) (
    increase(app_ai_eval_cases_total{
    criterion="factuality",
    outcome="pass",
    source="offline"
  }[24h])
)
/
sum by (prompt_version) (
  increase(app_ai_eval_cases_total{
    criterion="factuality",
    outcome=~"pass|fail",
    source="offline"
  }[24h])
)
~~~

So sánh prompt versions chỉ có ý nghĩa nếu dataset, criterion, rubric, judge model và sampling policy tương đương. Nếu một phiên bản được chạy trên dataset khác, khác biệt pass rate có thể do cohort composition.

Với release gate, tốt nhất chạy candidate và baseline trên cùng bộ cases, lưu run ID và phân tích paired outcomes.

## 15. Traffic mix có thể làm tỷ lệ tổng thay đổi

Một tỷ lệ toàn hệ thống phụ thuộc cả chất lượng từng cohort và tỷ trọng traffic của cohort đó.

Ví dụ:

| Thời kỳ | Request đơn giản | Pass rate đơn giản | Request phức tạp | Pass rate phức tạp | Pass rate chung |
|---|---:|---:|---:|---:|---:|
| A | 900 | 99% | 100 | 80% | 97,1% |
| B | 100 | 99% | 900 | 81% | 82,8% |

Pass rate của nhóm đơn giản giữ nguyên; nhóm phức tạp còn cải thiện từ 80% lên 81%. Tuy nhiên pass rate chung giảm mạnh vì traffic chuyển từ nhóm đơn giản sang nhóm phức tạp.

Đây là ví dụ của **Simpson's paradox**: xu hướng tổng hợp có thể khác với xu hướng trong từng nhóm do tỷ trọng cohort thay đổi.

Khi dashboard tổng thể đổi bất thường:

1. Kiểm tra traffic share theo route/task complexity/model.
2. So tỷ lệ trong từng cohort.
3. So phân phối mix giữa hai thời kỳ.
4. Nếu cần, chuẩn hóa theo một traffic mix cố định.
5. Chỉ kết luận regression sau khi kiểm soát composition.

Không chỉ nhìn aggregate rate để đánh giá prompt hoặc model.

## 16. Chuẩn hóa theo traffic mix

Có thể tính weighted pass rate theo trọng số cohort cố định:

\[
StandardizedPassRate =
\sum_{i=1}^{k} w_i \times PassRate_i
\]

Trong đó:

- \(PassRate_i\) là pass rate của cohort i.
- \(w_i\) là tỷ trọng cố định, tổng các trọng số bằng 1.
- Cùng một bộ trọng số được áp dụng cho các phiên bản cần so sánh.

Ví dụ dùng tỷ trọng baseline: 70% request đơn giản và 30% request phức tạp. Khi so release B, vẫn dùng 70/30 thay vì traffic mix thực tế 10/90.

Chuẩn hóa giúp tách ảnh hưởng composition khỏi thay đổi chất lượng trong từng cohort. Nó không thay thế việc báo cáo raw production mix, vì traffic mix thay đổi cũng có thể là tín hiệu sản phẩm quan trọng.

## 17. Chọn baseline để phát hiện suy giảm

Một baseline hữu ích cần cùng điều kiện so sánh:

- Cùng route hoặc cohort.
- Cùng outcome contract.
- Cùng time-of-day/day-of-week nếu traffic có seasonality.
- Cùng sampling policy.
- Cùng metric instrumentation.
- Ghi rõ prompt/model/rubric/release version.

Có thể dùng các kiểu baseline:

| Baseline | Khi phù hợp | Hạn chế |
|---|---|---|
| Previous release | So candidate với bản trước | Traffic mix có thể đổi |
| Same weekday/hour last week | Workload có seasonality tuần | Sự kiện bất thường có thể làm baseline lệch |
| Rolling 7/28 days | Theo dõi xu hướng | Có thể làm mờ regression mới |
| Fixed golden dataset | So chất lượng release | Không đại diện đầy đủ production |
| Control cohort/canary | So candidate và control đồng thời | Cần chia traffic công bằng |

Không chọn baseline sau khi đã thấy kết quả chỉ để làm regression biến mất. Quy tắc baseline cần được định nghĩa trước.

## 18. So sánh candidate và control trong canary

Một cách phát hiện regression là chạy candidate và control cùng thời điểm trên traffic tương đương.

Ví dụ:

- Control: prompt v12, model family A.
- Candidate: prompt v13, model family A.
- Cùng route, region, sampling policy và task type.
- Chia traffic ngẫu nhiên hoặc theo cơ chế rollout đã kiểm soát.

So sánh:
- Request error ratio.
- P95/P99 latency.
- Factuality/relevance pass rate.
- Completion coverage và judge error rate.
- Cost per successful task.

Nếu traffic được chia theo tenant hoặc user, cần xem hai nhóm có cân bằng về locale, task complexity và route hay không. Một canary nhỏ có thể có traffic mix khác ngẫu nhiên với control.

Không kết luận candidate tốt hơn chỉ từ raw count khi nhóm candidate có ít requests hơn nhiều. So tỷ lệ, sample size và uncertainty.

## 19. Minimum sample size và độ bất định

Một tỷ lệ 9/10 (90%) không chắc chắn bằng 900/1.000 (90%). Dashboard phải hiển thị cả numerator và denominator.

Với một tỷ lệ \(\hat p = x/n\), confidence interval giúp thể hiện độ bất định do sample. Wilson interval thường hữu ích hơn xấp xỉ chuẩn đơn giản khi n nhỏ hoặc p gần 0/1.

Công thức Wilson với z-score:

\[
\frac{
\hat p + \frac{z^2}{2n}
\pm
z\sqrt{\frac{\hat p(1-\hat p)}{n}+\frac{z^2}{4n^2}}
}{
1+\frac{z^2}{n}
}
\]

Với confidence level 95%, z thường lấy xấp xỉ 1,96.

Đừng dùng một ngưỡng sample cố định cho mọi metric. Error rate 1% và P99 latency cần lượng dữ liệu khác nhau. Đặt minimum sample dựa trên mức regression cần phát hiện, baseline và chi phí chấp nhận false alarm.

## 20. Tránh kết luận từ nhiều phép so sánh nhỏ

Nếu dashboard phân rã theo 20 routes, 10 models, 8 prompt versions và 5 regions, sẽ có rất nhiều cohort. Một vài cohort có thể tình cờ có tỷ lệ xấu dù hệ thống không thay đổi.

Khi kiểm tra nhiều cohort cùng lúc:

- Ưu tiên các nhóm đã được xác định trước là quan trọng.
- Hiển thị sample size và confidence interval.
- Xem mức độ ảnh hưởng tuyệt đối, không chỉ p-value.
- Dùng phương pháp kiểm soát multiple comparisons khi làm phân tích thống kê chính thức.
- Xác nhận phát hiện trên cửa sổ khác hoặc canary mới.
- Không page cho mọi cohort nhỏ có một lỗi.

Dashboard dùng để tìm tín hiệu; quyết định thay đổi production cần bằng chứng và context.

## 21. Dùng control chart để nhận biết thay đổi quá trình

Khi metric có biến động tự nhiên, một ngưỡng tĩnh có thể tạo nhiều cảnh báo giả.

Có thể dùng:
- **p-chart:** theo dõi tỷ lệ lỗi/pass khi sample size thay đổi.
- **EWMA:** làm mượt biến động ngắn và phát hiện thay đổi nhỏ kéo dài.
- **CUSUM:** tích lũy độ lệch để phát hiện drift bền vững.
- **Seasonal baseline:** so với cùng khung giờ/ngày trong tuần.

Với p-chart, giới hạn kiểm soát phụ thuộc tỷ lệ nền và sample size. Khi n thay đổi, upper/lower control limits cũng thay đổi. Control limits mô tả biến động thống kê của quá trình; chúng không tự động là product SLO. Một process có thể nằm trong control limits nhưng vẫn không đạt SLO.

Dùng SLO để định nghĩa mức chấp nhận; dùng control chart để nhận biết quá trình thay đổi khác thường.

## 22. Đo error ratio theo thời gian và cohort

Tỷ lệ lỗi theo route trong 15 phút:

~~~promql
sum by (route) (
  rate(app_ai_user_requests_total{outcome="bad",eligible="true"}[15m])
)
/
sum by (route) (
  rate(app_ai_user_requests_total{eligible="true"}[15m])
)
~~~

Số bad requests theo route trong 15 phút:

~~~promql
sum by (route) (
  increase(app_ai_user_requests_total{outcome="bad",eligible="true"}[15m])
)
~~~

Cả hai query cần được xem cùng total request rate. Một route có error ratio cao nhưng chỉ nhận 2 requests có thể cần xem xét khác với route có hàng nghìn failures.

Nếu không có request trong cửa sổ, tỷ lệ không xác định. Hiển thị no data thay vì 0%.

## 23. So sánh error ratio với baseline cùng thời điểm

Ví dụ so error ratio 15 phút hiện tại với cùng khung giờ của tuần trước:

~~~promql
(
  sum by (route) (
    rate(app_ai_user_requests_total{outcome="bad",eligible="true"}[15m])
  )
  /
  sum by (route) (
    rate(app_ai_user_requests_total{eligible="true"}[15m])
  )
)
/
(
  sum by (route) (
    rate(app_ai_user_requests_total{outcome="bad",eligible="true"}[15m] offset 7d)
  )
  /
  sum by (route) (
    rate(app_ai_user_requests_total{eligible="true"}[15m] offset 7d)
  )
)
~~~

Kết quả lớn hơn 1 nghĩa error ratio hiện tại cao hơn baseline cùng thời điểm; nhỏ hơn 1 nghĩa thấp hơn.

Query chỉ có ý nghĩa nếu route, instrumentation và traffic pattern có thể so sánh. Nếu baseline không có errors hoặc không có traffic, phép chia không xác định. Trong production, hãy tạo recording rules, xử lý no-data và dùng baseline window đủ ổn định.

Đây là tín hiệu chẩn đoán, không tự động là alert. Cần thêm absolute error ratio, traffic floor và impact.

## 24. Tách lỗi kỹ thuật và lỗi chất lượng theo cohort

Một request có thể hoàn tất HTTP thành công nhưng answer quality fail. Một request khác có thể timeout trước khi có response và không thể đánh giá factuality.

Hãy duy trì hai outcome domains:

| Domain | Ví dụ | SLI |
|---|---|---|
| Serving outcome | good, timeout, provider failure, tool failure | Availability/error ratio |
| Evaluation outcome | pass, fail, error, invalid, skipped, inconclusive | Quality, judge health, coverage |

Không gộp evaluator ERROR vào generator FAIL. Không coi evaluation pass là bằng chứng request latency/availability đạt. Hai domain có thể liên kết bằng task/case reference trong event store.

Khi quality cohort xấu đi nhưng serving SLI ổn định, điều tra prompt, context, model behavior, retrieval relevance và rubric. Khi serving SLI xấu nhưng quality pass rate ổn định, kiểm tra timeout, retries và coverage vì chỉ những response đã chấm mới góp vào quality sample.

## 25. Exemplar: đi từ metric tới trace đại diện

Prometheus exemplar cho phép gắn một trace reference với observation trong histogram/counter mà không biến trace ID thành label thông thường.

Ví dụ khái niệm:

~~~text
app_ai_request_duration_seconds_bucket
  observation: 8.7 seconds
  exemplar:
    trace_id: 4bf92f3577b34da6a3ce929d0e0e4736
~~~

Khi P95 tăng, người trực có thể mở exemplar để xem một trace đại diện. Trace đó giúp hiểu một execution cụ thể, nhưng không phải bằng chứng thống kê cho toàn bộ cohort.

Nếu exemplar chưa được hỗ trợ trong pipeline, có thể dùng log correlation với trace_id và request_id. Hãy giữ sampling policy đủ để có trace đại diện cho lỗi và latency tail; head sampling ngẫu nhiên có thể bỏ lỡ rare failures.

Tail-based sampling có thể ưu tiên giữ traces có error hoặc latency cao, nhưng cần cân nhắc chi phí, memory và sampling policy. Dù dùng cách nào, metric vẫn phải được ghi cho toàn bộ eligible events theo contract.

## 26. Sampling trace khác sampling evaluation

Hai loại sampling phục vụ mục tiêu khác nhau:

- **Trace sampling:** giảm lượng telemetry cần lưu; có thể ưu tiên error/slow traces.
- **Evaluation sampling:** chọn một phần responses để chấm quality; ảnh hưởng trực tiếp tới cohort được dùng tính pass rate.

Không suy ra evaluation coverage từ trace sampling. Một request không có trace được lưu vẫn có thể được đánh giá; một request có trace không có nghĩa evaluator đã chấm nó.

Nếu evaluation sampling không ngẫu nhiên, pass rate có thể bị bias. Ghi sampling policy, cohort và selection rate để diễn giải đúng.

## 27. Phân biệt lỗi đơn lẻ, cohort degradation và dependency incident

| Dấu hiệu | Khả năng | Bước tiếp theo |
|---|---|---|
| Một request lỗi, cohort ổn định | Input đặc biệt hoặc outlier | Mở trace và phân loại nguyên nhân |
| Nhiều requests cùng route lỗi | Route/pipeline regression | So release, advisor, retrieval và traffic |
| Nhiều routes cùng provider lỗi | Provider/dependency incident | Kiểm tra provider, quota và network |
| Chỉ prompt version mới quality giảm | Prompt regression | So failed cases trên cùng dataset |
| P95 tăng ở mọi model, VectorStore ổn định | Shared infrastructure hoặc network | Xem queue, connection pool và runtime |
| Judge errors tăng, serving ổn định | Evaluation pipeline incident | Xem judge provider, retry và queue |
| Aggregate pass rate giảm nhưng cohort rates ổn định | Traffic mix shift | Chuẩn hóa theo cohort weights |
| Một cohort nhỏ có 100% errors nhưng chỉ 1 case | Sample nhỏ | Điều tra case; chưa kết luận cohort trend |

Đây là các pattern để định hướng, không phải kết luận tự động. Trace và cohort data cần được đối chiếu trước khi quyết định.

## 28. Alert theo phạm vi và mức độ ảnh hưởng

Alert request-level và cohort-level nên có hành vi khác nhau.

| Alert | Trigger | Routing |
|---|---|---|
| Critical single event | Security, data loss, unsafe side effect hoặc business invariant bị vi phạm | Incident ngay theo policy |
| Cohort error ratio | Tỷ lệ lỗi cao, đủ traffic và kéo dài | On-call theo service owner |
| Model-specific degradation | Một model family tăng timeout/429/latency | Model/provider owner |
| Prompt quality regression | Quality pass rate giảm trên cohort đủ sample | Release owner / quality owner |
| Evaluation pipeline degradation | Judge error hoặc coverage giảm | Evaluation pipeline owner |
| Outlier request | Một request rất chậm nhưng không có systemic signal | Trace review hoặc support workflow |

Không page vì một request chậm đơn lẻ nếu không có rủi ro nghiêm trọng. Nhưng không được gộp các sự kiện bảo mật hoặc tác vụ nguy hiểm vào quy tắc percentile thông thường.

## 29. Prometheus alert cho cohort error rate

Ví dụ alert khi một route có error ratio trên 5%, đủ 100 requests trong 5 phút và duy trì 5 phút:

~~~yaml
groups:
  - name: spring-ai-cohort-health
    rules:
      - alert: AiRouteErrorRatioHigh
        expr: |
          (
            sum by (route) (
              rate(app_ai_user_requests_total{outcome="bad",eligible="true"}[5m])
            )
            /
            sum by (route) (
              rate(app_ai_user_requests_total{eligible="true"}[5m])
            )
          ) > 0.05
          and
          sum by (route) (
            increase(app_ai_user_requests_total{eligible="true"}[5m])
          ) >= 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "AI request errors are elevated for a route"
          description: "Inspect route cohort, release, model family and representative traces."
~~~

Ngưỡng 5%, 100 requests và 5 phút là ví dụ. Hiệu chỉnh theo SLO, traffic và mức độ ảnh hưởng. Với route ít traffic, dùng synthetic checks hoặc cửa sổ dài hơn.

## 30. Alert cho quality cohort theo prompt version và model family

Ví dụ alert factuality giảm dưới 90% trên từng cặp prompt version/model family, tối thiểu 200 evaluated cases:

~~~yaml
groups:
  - name: spring-ai-quality-cohort
    rules:
      - alert: AiPromptFactualityRegression
        expr: |
          (
            sum by (prompt_version, model_family) (
              increase(app_ai_eval_cases_total{
                criterion="factuality",
                outcome="pass",
                source="online_sampled"
              }[24h])
            )
            /
            sum by (prompt_version, model_family) (
              increase(app_ai_eval_cases_total{
                criterion="factuality",
                outcome=~"pass|fail",
                source="online_sampled"
              }[24h])
            )
          ) < 0.90
          and
          sum by (prompt_version, model_family) (
            increase(app_ai_eval_cases_total{
              criterion="factuality",
              outcome=~"pass|fail",
              source="online_sampled"
            }[24h])
          ) >= 200
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Factuality is below target for a prompt cohort"
          description: "Compare the candidate with control on the same dataset and judge rubric."
~~~

Không gộp nhiều prompt versions nếu mục tiêu là phát hiện version gây regression. Đồng thời theo dõi coverage và judge error theo cùng source/criterion. Với release gate offline, dùng run report trên fixed dataset thay vì rolling window.

## 31. Điều tra một request cụ thể

Khi nhận một request ID hoặc trace ID:

1. Xác nhận quyền truy cập và tìm request record.
2. Xem outcome cuối cùng ở user boundary.
3. Mở trace và xác định span lỗi/chậm đầu tiên.
4. Xem error class, provider status, retry và fallback.
5. Kiểm tra route, feature, release, prompt version và model thực tế.
6. Xem retrieval query/result metadata và tool execution status nếu được phép.
7. Đối chiếu request với cohort cùng route/version/time window.
8. Xác định đây là outlier, lỗi tái hiện được hay một phần của degradation.
9. Ghi lại root cause và action.
10. Nếu phát hiện pattern lặp lại, tạo cohort query/alert để theo dõi.

Không dán raw user content vào incident channel nếu chưa có quyền và redaction. Trace ID và request ID chỉ là khóa tra cứu, không phải metric dimension.

## 32. Điều tra một cohort đang suy giảm

Khi dashboard cho thấy một cohort xấu đi:

1. Xác nhận denominator, total count và bad count.
2. So với baseline cùng route, seasonality và sampling policy.
3. Phân rã theo model family, prompt version, release, region và task type.
4. Kiểm tra traffic mix và Simpson's paradox.
5. Xem latency histogram, error class, retry và fallback rate.
6. Với quality, xem PASS/FAIL, coverage, judge errors và human calibration.
7. Mở exemplars/traces đại diện ở tail hoặc failed cases.
8. So sánh candidate/control hoặc chạy lại fixed evaluation dataset.
9. Xác định dependency hay application regression.
10. Chọn rollback, canary pause, provider fallback hoặc code/prompt fix.

Không bắt đầu bằng cách tăng timeout hoặc retry nếu chưa hiểu nguyên nhân. Retry có thể làm tăng tải và che khuất provider degradation.

## 33. Dashboard đề xuất

Một dashboard để phân biệt request-level và cohort-level nên có các hàng:

| Hàng | Panels | Dùng để |
|---|---|---|
| Global overview | Total requests, good/bad ratio, P95/P99 | Nhìn sức khỏe tổng thể |
| Cohort breakdown | Error ratio/count by route/model/prompt/release | Tìm nhóm bị ảnh hưởng |
| Traffic mix | Share by route/task/locale/model | Phát hiện composition shift |
| Latency | Histogram, P95/P99, slow request count | Phân biệt outlier và tail degradation |
| Quality | PASS/FAIL, pass rate, coverage by criterion/version | Theo dõi quality regression |
| Evaluator health | Attempt errors, judge latency, pending queue | Đảm bảo score đáng tin |
| Dependency | Provider 429/5xx, VectorStore/tool failures | Xác định shared dependency |
| Trace exemplars | Links tới representative slow/error traces | Điều tra execution cụ thể |
| Release comparison | Control vs candidate, prompt/model version | Đánh giá rollout |

Mọi tỷ lệ cần hiển thị numerator, denominator, time window và sample size. Nếu không có sample, hiển thị no data.

## 34. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng một trace để kết luận toàn hệ thống lỗi | Kết luận quá mức từ outlier | Xem cohort SLI và sample size |
| Chỉ nhìn aggregate | Che cohort xấu | Phân rã theo route/model/version |
| Chỉ nhìn error ratio | Không thấy impact tuyệt đối | Hiển thị bad count và traffic |
| So cohort khác denominator | Tỷ lệ không tương đương | Chuẩn hóa event unit và eligible set |
| Không xem traffic mix | Nhầm composition shift là regression | Stratify/standardize cohort |
| Lấy trung bình P95 của instances | Quantile sai | Aggregate histogram buckets trước |
| Dùng trace ID làm label | Cardinality bùng nổ | Exemplars hoặc log correlation |
| Sampling trace rồi tính request SLI | Bỏ sót requests không được sample | Metrics ghi trên toàn bộ eligible events |
| Gộp model retry thành user request | Sai request outcome | Tách attempt và request boundary |
| Gộp evaluator error thành answer fail | Quality score sai | Tách serving và evaluation outcome |
| Alert cohort nhỏ | False positive | Minimum sample và confidence |
| So prompt versions trên dataset khác | Kết luận không công bằng | Fixed dataset và paired evaluation |

## 35. Bài tập tự kiểm tra

### Bài 1 — Một request timeout

Một request RAG timeout ở model call. Cohort có 5.000 requests trong 15 phút và chỉ một request lỗi. Có thể kết luận toàn cohort suy giảm không?

**Đáp án:** Chưa. Điều tra trace request đó, xem error ratio/count và baseline cohort. Một lỗi vẫn cần ghi nhận nhưng chưa đủ bằng chứng cho systemic degradation.

### Bài 2 — Error ratio và impact

Route A có 10 lỗi/100 requests; route B có 500 lỗi/100.000 requests. Route nào có error ratio cao hơn và route nào có nhiều bad requests hơn?

**Đáp án:** A có error ratio 10%, cao hơn B là 0,5%. B có 500 bad requests, nhiều hơn A là 10. Cần xem cả tỷ lệ và impact.

### Bài 3 — P95 và outlier

Một request mất 60 giây nhưng 999 requests còn lại đều dưới 2 giây. Điều đó có bắt buộc P95 vượt 2 giây không?

**Đáp án:** Không. Một outlier có thể không làm P95 thay đổi đáng kể. Trace vẫn cần được điều tra riêng.

### Bài 4 — Simpson's paradox

Pass rate từng cohort giữ nguyên nhưng aggregate pass rate giảm sau khi traffic chuyển sang nhóm khó hơn. Có phải prompt regression không?

**Đáp án:** Chưa. So tỷ lệ trong từng cohort và chuẩn hóa theo traffic mix cố định trước khi kết luận.

### Bài 5 — Prompt version mới

Prompt v13 có factuality 88% trên 100 cases, prompt v12 có 94% trên 2.000 cases nhưng dùng dataset khác. Có thể kết luận v13 kém hơn không?

**Đáp án:** Chưa đủ. Chạy cả hai versions trên cùng fixed dataset, cùng rubric và judge version; xem sample size và uncertainty.

### Bài 6 — Trace sampling

Chỉ 10% traces được lưu nhưng metric request error counter ghi toàn bộ requests. Error rate nên tính từ nguồn nào?

**Đáp án:** Từ request counter đầy đủ, không tính từ traces được sample. Trace sampling phục vụ điều tra, không thay thế SLI.

### Bài 7 — Quality tốt, coverage thấp

Pass rate là 99%, nhưng completion coverage chỉ 20%. Có thể báo chất lượng production là 99% không?

**Đáp án:** Không. Chỉ 20% applicable selected cases có verdict hợp lệ. Phải đánh dấu quality data incomplete và điều tra evaluator/queue/sampling.

### Bài 8 — Provider incident

Ba routes cùng tăng model timeout trên một provider, trong khi VectorStore latency ổn định. Hướng điều tra đầu tiên là gì?

**Đáp án:** Kiểm tra provider status, quota, HTTP client/network, 429/5xx, concurrency và fallback. Đây có thể là shared dependency degradation.

## 36. Checklist trước khi dùng dashboard để kết luận regression

- [ ] Request outcome được ghi một lần tại user boundary?
- [ ] Model attempts và user requests được đo riêng?
- [ ] Request record liên kết được với trace?
- [ ] Cohort dimensions có membership và cardinality rõ?
- [ ] Mỗi tỷ lệ có numerator, denominator và sample size?
- [ ] Có cả bad count và error ratio?
- [ ] Latency được xem bằng histogram/percentile?
- [ ] Cohort được so với baseline cùng seasonality?
- [ ] Traffic mix được kiểm tra trước khi kết luận?
- [ ] Có fixed dataset hoặc control cohort để so prompt/model?
- [ ] Quality pass rate đi kèm completion coverage và judge health?
- [ ] Trace sampling không được dùng thay request metrics?
- [ ] Exemplar/trace link không tạo high-cardinality labels?
- [ ] Alert có minimum sample, impact threshold và owner?
- [ ] Có quy trình điều tra request-level và cohort-level riêng?
- [ ] Có ngoại lệ xử lý ngay cho security/data-loss/safety incidents?

## 37. Tài liệu tham khảo

1. [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient, ChatModel, tool và VectorStore observations.
2. [Spring AI 2.1.0 — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator API và các evaluator có sẵn.
3. [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): tổng hợp histogram và tính quantiles.
4. [Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/): counters, labels, request failures và latency.
5. [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/): spans, trace context và phân tích distributed execution.
6. [OpenTelemetry — Exemplars](https://opentelemetry.io/docs/specs/otel/metrics/data-model/): liên kết metric observations với trace context.
7. [Google SRE Book — Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/): triệu chứng, metric tổng hợp và cách xây monitoring có ích.

*Metric names, labels, cohort rules và thresholds trong bài là ví dụ do ứng dụng định nghĩa. Trước khi kết luận regression, xác nhận event boundary, denominator, traffic mix, sampling policy, sample size và baseline. Dùng trace để giải thích một execution cụ thể; dùng metrics và evaluation cohorts để xác định phạm vi ảnh hưởng.*
