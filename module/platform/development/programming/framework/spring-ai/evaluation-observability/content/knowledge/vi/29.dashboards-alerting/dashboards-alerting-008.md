# Tránh cảnh báo nhiễu khi cỡ mẫu nhỏ hoặc dữ liệu đến chậm

## 1. Vì sao một tỷ lệ bất thường chưa đủ để phát cảnh báo?

Một dashboard evaluation hiển thị factuality pass rate 0% trong 5 phút. Nhưng trong khoảng đó chỉ có một case được chấm và case này bị FAIL. Nếu hệ thống page on-call ngay, một mẫu đơn lẻ có thể tạo incident giả.

Một tình huống khác: evaluator xử lý queue chậm 10 phút. Dashboard chỉ nhận verdict sau khi worker hoàn tất. Nếu alert quality dùng cửa sổ 5 phút theo thời điểm xử lý, nó có thể thấy ít case hoặc không có case, rồi diễn giải nhầm thành chất lượng tăng, giảm hoặc bằng zero.

Hai nguồn gây nhiễu thường gặp:

- **Cỡ mẫu nhỏ:** tỷ lệ biến động mạnh khi denominator thấp; một event có thể làm tỷ lệ đổi hàng chục điểm phần trăm.
- **Dữ liệu đến trễ:** event xảy ra trong một cửa sổ nhưng được ingest hoặc xử lý ở cửa sổ sau; query có thể đánh giá một cohort chưa đầy đủ.

Muốn alert đáng tin cậy, cần xem tỷ lệ cùng numerator, denominator, độ bất định, độ mới của dữ liệu và mức độ hoàn tất của pipeline. Khi thiếu dữ liệu, trạng thái đúng thường là “chưa đủ bằng chứng” hoặc “data delayed”, không phải “dịch vụ tốt”.

Bài thuộc chương **Dashboard và cảnh báo** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời theo dõi metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua các phiên bản prompt, model và pipeline.

Sau bài, bạn có thể:

1. Nhận biết tỷ lệ không ổn định do denominator nhỏ.
2. Đặt minimum sample và confidence rule cho quality/error alerts.
3. Dùng Wilson interval và quy tắc lập kế hoạch sample size.
4. Xử lý traffic thấp bằng cohort phù hợp và synthetic checks.
5. Phân biệt event time, processing time và ingest time.
6. Thiết kế watermark, grace period và late-arrival handling.
7. Theo dõi freshness, completeness, queue lag và pending age.
8. Viết PromQL/alert rules có điều kiện sample, no-data và data freshness.
9. Tách quality regression khỏi evaluator/telemetry pipeline incident.

## 2. Tỷ lệ phụ thuộc vào numerator và denominator

Một tỷ lệ thường có dạng:

\[
Rate = \frac{Numerator}{Denominator}
\]

Ví dụ factuality pass rate:

\[
PassRate = \frac{PASS}{PASS + FAIL}
\]

Các outcome ERROR, INVALID, SKIPPED, NOT_APPLICABLE, INCONCLUSIVE và PENDING không nằm trong denominator này. Chúng cần được theo dõi bằng coverage và evaluator-health metrics riêng.

Cùng một tỷ lệ 90% có thể mang ý nghĩa rất khác:

| PASS | FAIL | Pass rate | Cách diễn giải |
|---:|---:|---:|---|
| 9 | 1 | 90% | Chỉ có 10 cases, bất định lớn |
| 90 | 10 | 90% | Có 100 cases |
| 900 | 100 | 90% | Có 1.000 cases, ước lượng ổn định hơn |

Không hiển thị tỷ lệ mà thiếu số lượng. Panel nên có PASS, FAIL, evaluated count, eligible/selected count và cửa sổ thời gian.

Một request error ratio cũng cần denominator là eligible requests. Nếu chỉ có một request trong cửa sổ và request đó lỗi, error ratio là 100%, nhưng chưa chắc cần page. Nếu không có request nào, tỷ lệ không xác định chứ không phải 0%.

## 3. Một event có thể làm tỷ lệ thay đổi bao nhiêu?

Với denominator nhỏ, một event có tác động lớn.

Ví dụ một cohort có 9 PASS và 1 FAIL. Pass rate là 90%. Nếu case tiếp theo PASS:

\[
\frac{10}{11} \approx 90.9\%
\]

Nếu case tiếp theo FAIL:

\[
\frac{9}{11} \approx 81.8\%
\]

Chỉ một case mới có thể làm tỷ lệ đổi hơn 8 điểm phần trăm. Khi denominator là 10.000, một case thường không tạo thay đổi đáng kể.

Điều này không có nghĩa phải bỏ qua cohort nhỏ. Một case lỗi nghiêm trọng vẫn có thể cần điều tra. Nhưng alert về xu hướng thống kê cần phân biệt:
- Một event cần review.
- Một cohort có đủ bằng chứng cho thấy regression.
- Một pipeline không tạo đủ dữ liệu để kết luận.

## 4. Minimum sample size: điều kiện tối thiểu trước khi đánh giá tỷ lệ

Một cách đơn giản là chỉ đánh giá tỷ lệ khi denominator đạt một ngưỡng tối thiểu:

\[
N = PASS + FAIL
\]

Ví dụ quality alert chỉ được phép fire khi \(N \ge 200\) trong cửa sổ 24 giờ.

Ngưỡng 200 chỉ là ví dụ. Không có một con số đúng cho mọi ứng dụng. Sample size phụ thuộc vào:
- Baseline pass/error rate.
- Mức thay đổi cần phát hiện.
- Độ tin cậy mong muốn.
- Tần suất traffic.
- Mức ảnh hưởng của false positive và false negative.
- Số cohort được theo dõi song song.

Minimum sample là điều kiện chống cảnh báo từ mẫu quá nhỏ; nó không tự chứng minh tỷ lệ đã suy giảm. Công thức sample size và Wilson interval ở trên giả định observations gần độc lập và sampling không bị lệch mạnh. Nếu nhiều cases đến từ cùng một session, tenant hoặc conversation, các observations có thể tương quan và effective sample size nhỏ hơn số case đếm được. Khi sample đạt ngưỡng, vẫn cần so với target, baseline và độ bất định.

## 5. Lập kế hoạch sample size theo sai số mong muốn

Với một tỷ lệ \(\hat p\), công thức xấp xỉ cho sample size khi muốn sai số biên \(e\) ở confidence level tương ứng là:

\[
n \approx \frac{z^2 p(1-p)}{e^2}
\]

Trong đó:
- \(p\) là tỷ lệ kỳ vọng từ baseline hoặc pilot.
- \(z\) là quantile của phân phối chuẩn, ví dụ khoảng 1,96 cho 95%.
- \(e\) là sai số biên mong muốn.

Ví dụ baseline factuality pass rate khoảng 95%, muốn sai số biên xấp xỉ 2 điểm phần trăm ở mức 95%:

\[
n \approx
\frac{1.96^2 \times 0.95 \times 0.05}{0.02^2}
\approx 457
\]

Đây là ước lượng lập kế hoạch, không phải đảm bảo tuyệt đối. Khi sample size nhỏ, tỷ lệ gần 0/1, hoặc sampling không độc lập, cần dùng phương pháp phù hợp hơn như Wilson interval, exact binomial interval hoặc thiết kế phân tầng.

Nếu không biết \(p\), dùng \(p=0.5\) cho ước lượng bảo thủ nhất về sample size của tỷ lệ nhị phân.

## 6. Wilson confidence interval cho tỷ lệ

Wilson interval thường hoạt động tốt hơn xấp xỉ chuẩn đơn giản khi denominator nhỏ hoặc tỷ lệ gần 0/1.

Với \(\hat p=x/n\), z-score \(z\), Wilson interval có tâm:

\[
Center =
\frac{\hat p + \frac{z^2}{2n}}
{1+\frac{z^2}{n}}
\]

Và nửa độ rộng:

\[
HalfWidth =
\frac{
z\sqrt{\frac{\hat p(1-\hat p)}{n}+\frac{z^2}{4n^2}}
}{
1+\frac{z^2}{n}
}
\]

Khoảng tin cậy là:

\[
[Center-HalfWidth,\ Center+HalfWidth]
\]

Ví dụ 9/10 PASS cho point estimate 90%, nhưng interval rộng. Với 900/1.000 PASS, point estimate vẫn 90% nhưng interval hẹp hơn.

Dashboard có thể hiển thị:
- Point estimate.
- Lower confidence bound.
- Upper confidence bound.
- Numerator/denominator.
- Confidence level và method.

Đừng chỉ ghi “90% ± 2%” nếu chưa xác định cách tính interval và giả định sampling.

## 7. Dùng confidence bound để phân biệt regression với uncertainty

Giả sử quality SLO yêu cầu factuality pass rate ít nhất 95%.

Có ba tình huống:

1. Point estimate 90%, nhưng interval là 82–95%: dữ liệu chưa đủ mạnh để khẳng định true rate thấp hơn target.
2. Point estimate 90%, interval là 87–93%: ngay cả upper bound cũng dưới 95%; có bằng chứng rõ hơn cho regression.
3. Point estimate 97%, interval là 96–98%: dữ liệu hỗ trợ kết luận cohort đang trên target.

Với mục tiêu tối thiểu \(T\), một policy bảo thủ có thể:
- **Page/release block:** upper confidence bound thấp hơn \(T\), với minimum sample và coverage đạt.
- **Warning/review:** point estimate thấp hơn \(T\), nhưng interval còn giao với \(T\).
- **No conclusion:** sample quá nhỏ hoặc data incomplete.

Đây là policy ví dụ. Mức severity phụ thuộc risk appetite. Một criterion an toàn quan trọng có thể cần human review ngay cả khi sample nhỏ.

Với error rate có giới hạn tối đa \(E\), bằng chứng mạnh cho vi phạm là lower confidence bound lớn hơn \(E\).

## 8. Vì sao “0 lỗi” trên mẫu nhỏ không có nghĩa rủi ro bằng zero?

Nếu 10 requests đều thành công, observed error rate là 0%. Nhưng điều đó không chứng minh true error rate bằng zero.

Một quy tắc gần đúng thường dùng là “rule of three”: khi quan sát 0 failures trên \(n\) events độc lập, upper 95% bound của error probability xấp xỉ:

\[
UpperBound \approx \frac{3}{n}
\]

Ví dụ:
- 0 lỗi trên 10 requests: upper bound gần 30%.
- 0 lỗi trên 100 requests: upper bound gần 3%.
- 0 lỗi trên 1.000 requests: upper bound gần 0,3%.

Đây là xấp xỉ cho trường hợp zero failures và các observations độc lập. Với traffic phụ thuộc theo session/tenant hoặc có sampling bias, cần thận trọng hơn.

Không biến no-error-on-small-sample thành alert xanh “100% healthy”. Hiển thị sample size và trạng thái insufficient data.

## 9. Minimum sample theo cohort

Không nên dùng một minimum sample chung cho mọi cohort nếu traffic và rủi ro khác nhau.

Ví dụ:

| Cohort | Traffic | Cách xử lý |
|---|---:|---|
| Chat tổng thể | Cao | Có thể áp dụng threshold 500 cases/24h |
| RAG tiếng Việt | Trung bình | Theo dõi riêng nếu sample đủ |
| Agent workflow hiếm | Thấp | Dùng cửa sổ dài hơn hoặc review theo run |
| Prompt candidate canary 1% | Rất thấp | Dùng offline fixed dataset trước khi mở rộng |
| Critical tool action | Rất thấp nhưng rủi ro cao | Event-level safety alert và human review |

Các số lượng minh họa cần được hiệu chỉnh. Không gộp cohort chỉ để đạt minimum sample nếu chúng có behavior, rubric hoặc user promise khác nhau.

Có thể nhóm các cohort nhỏ theo route hoặc model family ở cấp cao hơn nếu định nghĩa chất lượng tương đương. Khi đó, vẫn giữ drill-down để phát hiện một subgroup bị che khuất.

## 10. Traffic thấp: dùng cửa sổ dài hơn hay synthetic checks?

Với route ít traffic, cửa sổ 5 phút thường không đủ sample.

Các lựa chọn:

- Tăng cửa sổ lên 1 giờ, 6 giờ hoặc 24 giờ.
- Gộp cohort tương đương đã được định nghĩa trước.
- Chạy synthetic request định kỳ để kiểm tra availability/latency.
- Chạy offline evaluation trên fixed dataset.
- Dùng human review cho case rủi ro cao.
- Đặt alert về data freshness thay vì quality ratio khi chưa đủ cases.

Synthetic check đo khả năng phục vụ một input kiểm soát. Nó không đại diện cho toàn bộ production traffic và không nên được cộng vào quality denominator của user traffic.

Tách metric synthetic với production bằng label source hoặc traffic_type có danh mục hữu hạn.

## 11. Không dùng for để thay thế minimum sample

Prometheus for yêu cầu biểu thức tiếp tục ở trạng thái true trong một khoảng thời gian trước khi alert chuyển sang firing.

for hữu ích để lọc spike ngắn, nhưng nó không giải quyết sample size:

- Một request lỗi có thể giữ error ratio ở mức 100% trong phần lớn cửa sổ query; việc không có traffic mới không làm tỷ lệ biến mất ngay.
- Một tỷ lệ 90% từ 10 cases vẫn có thể giữ nguyên trong nhiều giờ.
- Dữ liệu đến trễ có thể làm query thiếu sample dù for đã hết.

Dùng đồng thời:
- Minimum denominator.
- Confidence/threshold policy.
- for để chống dao động ngắn.
- Data freshness và completeness checks.

Không tăng for vô hạn để che một query không có mẫu số đúng.

## 12. PromQL: chỉ alert khi đủ evaluated cases

Giả sử counter:

~~~text
app_ai_eval_cases_total{criterion,outcome,source,route}
~~~

Ví dụ point-estimate alert factuality dưới 90%, chỉ khi có ít nhất 200 PASS/FAIL trong 24 giờ:

~~~promql
(
  sum by (route) (
    increase(app_ai_eval_cases_total{
      criterion="factuality",
      source="online_sampled",
      outcome="pass"
    }[24h])
  )
  /
  sum by (route) (
    increase(app_ai_eval_cases_total{
      criterion="factuality",
      source="online_sampled",
      outcome=~"pass|fail"
    }[24h])
  )
) < 0.90
and
sum by (route) (
  increase(app_ai_eval_cases_total{
    criterion="factuality",
    source="online_sampled",
    outcome=~"pass|fail"
  }[24h])
) >= 200
~~~

Set operator and giữ lại series có cùng label set từ hai phía. Vì cả hai vế đều tổng hợp by route, điều kiện sample được áp dụng cho đúng route.

Nếu denominator dưới 200, expression không tạo alert quality regression. Cần panel/alert riêng cho insufficient sample hoặc low traffic nếu đó là vấn đề cần hành động.

## 13. Vì sao không nên dùng or vector(0) cho mọi query?

Một số dashboard dùng or vector(0) để tránh ô trống. Cách này có thể hữu ích cho một counter tổng hợp đã biết chắc absent đồng nghĩa zero, nhưng nguy hiểm với tỷ lệ và data pipeline.

Ví dụ:
- Không có PASS/FAIL vì chưa có traffic.
- Metric chưa được scrape.
- Evaluator đang outage.
- Queue chưa xử lý xong.
- Label mới chưa xuất hiện sau deployment.

Nếu thay tất cả bằng zero, người xem có thể nhầm “không có dữ liệu” thành “0% pass” hoặc “0% error”.

Quy tắc:
- Count event có thể hiển thị zero nếu nguồn dữ liệu có heartbeat/freshness chứng minh pipeline đang hoạt động.
- Ratio có denominator zero phải là N/A.
- Metric absent cần data-availability alert riêng.
- Không tạo một giá trị zero giả để làm dashboard trông đầy đủ.

## 14. Event time, processing time và ingest time

Dữ liệu đến trễ cần ba timestamp rõ ràng:

| Timestamp | Ý nghĩa | Ví dụ |
|---|---|---|
| Event time | Khi sự kiện nghiệp vụ thực sự xảy ra | Model trả response lúc 10:02 |
| Processing time | Khi worker xử lý sự kiện | Evaluator chấm xong lúc 10:09 |
| Ingest time | Khi event được ghi vào telemetry/store | Collector nhận lúc 10:10 |

Một evaluation case có thể được tạo lúc 10:02, chấm xong lúc 10:09 và lưu vào analytics lúc 10:10.

Nếu dashboard nhóm theo processing time, case sẽ xuất hiện trong cửa sổ 10:09. Nếu báo cáo theo event time, case thuộc cửa sổ 10:02.

Hai góc nhìn trả lời câu hỏi khác nhau:
- Event-time quality: chất lượng của traffic phát sinh trong thời kỳ nào?
- Processing-time throughput: evaluator xử lý được bao nhiêu cases trong thời kỳ nào?
- Ingest-time freshness: telemetry đến hệ thống quan sát chậm bao lâu?

Đừng trộn ba timestamp vào cùng một denominator.

## 15. Chọn timestamp cho từng SLI

| Metric | Timestamp phù hợp |
|---|---|
| User request availability | Request terminal time hoặc event time ở serving boundary |
| Request latency | Thời điểm bắt đầu/kết thúc request |
| Evaluation quality theo production traffic | Original request/event time |
| Judge throughput | Evaluation completion/processing time |
| Queue age | Current time trừ enqueue time |
| Telemetry freshness | Ingest time trừ event time |
| Cost ledger | Model operation/billing event time, kèm recorded_at |

Với async evaluation, nếu muốn biết factuality của traffic trong 10:00–10:15, phải nhóm theo timestamp request gốc, không phải timestamp judge hoàn tất.

Đồng thời, cần báo evaluator throughput riêng để biết judge có đang xử lý backlog hay không.

## 16. Watermark và allowed lateness

Trong stream/batch processing, watermark biểu thị mốc event time mà hệ thống cho rằng dữ liệu trước mốc đó đã gần hoàn chỉnh.

Ví dụ:
- Event time hiện tại lớn nhất đã quan sát: 10:30.
- Out-of-orderness bound/watermark lag: 5 phút.
- Watermark: 10:25.

Window 10:00–10:15 có thể phát kết quả lần đầu khi watermark vượt 10:15. Nếu cấu hình allowed lateness thêm 3 phút, pipeline tiếp tục chấp nhận late events cho window đó cho tới khi watermark vượt 10:18; sau đó window mới được finalize theo policy.

Các thuật ngữ:
- **Window:** khoảng event time cần tổng hợp.
- **Out-of-orderness bound:** giả định về mức độ event có thể đến sai thứ tự; thường được dùng để tính watermark sau event time lớn nhất đã quan sát.
- **Allowed lateness:** khoảng thời gian hệ thống tiếp tục chấp nhận late events sau khi watermark đã vượt window end; semantics cụ thể tùy stream processor.
- **Grace period:** thời gian chờ bổ sung do ứng dụng quy định trước khi coi một kết quả vận hành là đủ ổn định để alert/báo cáo.
- **Watermark:** tiến độ event time mà pipeline dùng để quyết định window có thể hoàn tất.
- **Late event:** event đến sau khi window đã được emit/finalize theo policy.

Watermark không đảm bảo không còn event đến trễ. Nó là chính sách vận hành dựa trên distribution độ trễ và trade-off giữa freshness với completeness.

## 17. Thiết kế grace period theo độ trễ thực tế

Không chọn grace period tùy ý. Hãy đo distribution:

\[
EventDelay = IngestTime - EventTime
\]

Theo dõi P50, P95, P99 và max delay theo source/route/region.

Đồng bộ clock giữa producer, worker và collector bằng cơ chế time synchronization phù hợp. EventDelay âm thường là dấu hiệu clock skew hoặc timestamp sai, không phải telemetry đến trước thời điểm sự kiện.

Ví dụ:
- P50: 3 giây.
- P95: 20 giây.
- P99: 90 giây.
- Một số batch evaluator có thể trễ 10 phút.

Nếu quality alert chạy mỗi 5 phút nhưng evaluator thường mất 8 phút, alert event-time sẽ thường xuyên thấy cohort chưa đủ dữ liệu.

Có thể chọn grace period gần P99 hoặc theo SLA hoàn tất evaluation. Tuy nhiên, grace period quá dài làm phát hiện quality regression chậm. Vì vậy cần tách:
- Provisional quality view: dữ liệu hiện có, đánh dấu incomplete.
- Finalized quality view: chỉ chốt sau watermark/grace period.
- Pipeline lag alert: báo khi processing delay vượt mục tiêu.

## 18. Dữ liệu đến muộn cần được cập nhật thế nào?

Một pipeline event-time nên hỗ trợ late arrivals:

1. Ghi event gốc bất biến với event_time và ingest_time.
2. Ghi evaluation result với processed_at và reference tới event gốc.
3. Tạo aggregate theo event-time window.
4. Đánh dấu window provisional trước watermark.
5. Khi watermark vượt window end, emit finalized snapshot.
6. Nếu late event được chấp nhận sau finalize, cập nhật aggregate theo correction policy.
7. Ghi audit để biết số liệu nào đã được điều chỉnh và khi nào.

Không âm thầm ghi đè số liệu đã báo cáo mà không có audit trail. Với báo cáo release, nên lưu snapshot cùng evaluation run ID và dataset version.

## 19. Prometheus counter phản ánh thời điểm ghi nhận

Prometheus counter thường được scrape theo thời gian quan sát. Khi worker hoàn tất và increment counter, sample phản ánh processing/recording time, không tự động quay về event time gốc.

Vì vậy:
- Counter app_ai_eval_cases_total tăng khi evaluator ghi terminal outcome.
- Counter đó phù hợp đo throughput/processing outcomes.
- Nó không tự đủ để tạo event-time quality cohort nếu cases có độ trễ lớn hoặc thay đổi thứ tự.

Đối với event-time reporting, có thể dùng:
- Evaluation/event store truy vấn theo event_time.
- Stream processor có watermark và late-event semantics.
- Periodic rollup được version hóa theo event-time windows.

Prometheus vẫn phù hợp theo dõi processing throughput, queue, lag và operational health.

## 20. Dùng query offset khi dữ liệu có độ trễ ổn định

Nếu telemetry thường đến trễ khoảng 2 phút, một query có thể đọc cửa sổ đã kết thúc cách hiện tại 2 phút:

~~~promql
sum by (route) (
  increase(app_ai_eval_cases_total{
    criterion="factuality",
    outcome="pass",
    source="online_sampled"
  }[15m] offset 2m)
)
/
sum by (route) (
  increase(app_ai_eval_cases_total{
    criterion="factuality",
    outcome=~"pass|fail",
    source="online_sampled"
  }[15m] offset 2m)
)
~~~

Query này đánh giá một cửa sổ processing/ingest-time đã lùi lại. Nó có thể hữu ích khi scrape hoặc remote-write samples được lưu với timestamp gốc nhưng đến Prometheus chậm, hoặc khi muốn chờ một cửa sổ processing-time kết thúc trước khi đánh giá.

Nếu application counter chỉ được increment khi evaluator hoàn tất, counter phản ánh processing time. offset không thể chuyển các increments đó về event time gốc của request. Muốn báo cáo quality theo event-time window, cần event store hoặc stream rollup có event_time và watermark.

Trade-off là alert phát hiện muộn thêm 2 phút. offset không sửa được dữ liệu trễ không giới hạn, không thay thế watermark và không đảm bảo window đã complete.

Nếu delay thay đổi theo queue backlog, hãy theo dõi lag và đánh dấu quality result incomplete khi lag vượt ngưỡng.

## 21. Freshness SLI cho telemetry

Freshness đo dữ liệu mới nhất đã đến muộn bao lâu.

\[
FreshnessLag = IngestTime - EventTime
\]

Một metric application/collector có thể là:

~~~text
app_ai_telemetry_event_lag_seconds{source,stream}
app_ai_telemetry_latest_event_lag_seconds{source,stream}
app_ai_telemetry_last_success_timestamp_seconds{source,stream}
~~~

Trong ví dụ này, event_lag_seconds là histogram để xem phân phối; latest_event_lag_seconds là gauge giữ độ trễ của event mới nhất đã nhận cho mỗi source/stream.

Ví dụ query lag P95 nếu metric histogram được instrument:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, source) (
    rate(app_ai_telemetry_event_lag_seconds_bucket[10m])
  )
)
~~~

Nếu dùng gauge timestamp lần ingest thành công gần nhất:

~~~promql
time() - app_ai_telemetry_last_success_timestamp_seconds
~~~

Freshness target có thể là P95 lag dưới 60 giây cho serving telemetry và dưới 10 phút cho async evaluation. Các ngưỡng cần dựa trên pipeline thực tế.

Freshness tốt không đồng nghĩa completeness tốt. Một số event mới có thể đến nhanh trong khi một partition hoặc một source bị mất dữ liệu.

## 22. Completeness và coverage cho dữ liệu đánh giá

Đối với evaluation pipeline, theo dõi:

- Eligible cases.
- Selected cases.
- Applicable cases.
- Terminal PASS/FAIL.
- ERROR/INVALID/SKIPPED/INCONCLUSIVE.
- Pending cases.
- Expected vs received partitions/batches.
- Event-time watermark và late-arrival count.

Completion coverage:

\[
Coverage =
\frac{PASS + FAIL}{SelectedApplicableCases}
\]

Coverage phải được tính trên cùng cohort và run/window. Nếu denominator chưa ổn định vì event đến trễ, đánh dấu provisional thay vì chốt tỷ lệ.

Một pipeline có freshness tốt nhưng coverage thấp có thể đang skip nhiều cases. Một pipeline coverage cao nhưng freshness thấp có thể hoàn tất nhưng quá muộn để hỗ trợ alert online.

## 23. Theo dõi queue lag và oldest pending age

Với evaluator chạy async, cần metric riêng cho queue:

~~~text
app_ai_eval_pending_cases{queue,source}
app_ai_eval_oldest_pending_age_seconds{queue}
app_ai_eval_queue_lag_seconds{queue}
app_ai_eval_processed_cases_total{queue,outcome}
~~~

Các query gợi ý:

~~~promql
sum by (queue) (app_ai_eval_pending_cases)
~~~

~~~promql
max by (queue) (app_ai_eval_oldest_pending_age_seconds)
~~~

~~~promql
histogram_quantile(
  0.95,
  sum by (le, queue) (
    rate(app_ai_eval_queue_lag_seconds_bucket[10m])
  )
)
~~~

Pending count tăng cho biết backlog lớn; oldest age cho biết có task bị kẹt lâu; queue lag cho biết độ trễ xử lý. Cả ba bổ sung nhau.

Nếu queue rỗng nhưng source không phát heartbeat, pending gauge bằng zero vẫn có thể gây hiểu nhầm. Cần source heartbeat hoặc last-success timestamp.

## 24. PromQL: minimum sample và freshness trong cùng alert

Ví dụ quality alert chỉ fire khi đủ 200 cases và telemetry lag dưới 2 phút:

~~~promql
(
  (
    sum by (route) (
      increase(app_ai_eval_cases_total{
        criterion="factuality",
        source="online_sampled",
        outcome="pass"
      }[24h])
    )
    /
    sum by (route) (
      increase(app_ai_eval_cases_total{
        criterion="factuality",
        source="online_sampled",
        outcome=~"pass|fail"
      }[24h])
    )
  ) < 0.90
)
and
sum by (route) (
  increase(app_ai_eval_cases_total{
    criterion="factuality",
    source="online_sampled",
    outcome=~"pass|fail"
  }[24h])
) >= 200
and on()
(
  max by () (
    app_ai_telemetry_latest_event_lag_seconds{source="online_sampled"}
  )
  < 120
)
~~~

Ví dụ dùng and on() để áp dụng một điều kiện freshness tổng hợp cho từng route series. Metric lag gauge phải hiện diện và labels source/stream phải đúng contract. Khi lag series absent, biểu thức không trả alert quality; do đó phải có alert freshness/absence riêng. Nếu lag được đo riêng theo route, hãy giữ route trong phép tổng hợp và join theo route thay vì dùng freshness toàn cục.

Điều kiện freshness không chứng minh toàn bộ event-time window hoàn chỉnh. Nếu delay thay đổi mạnh, dùng watermark/rollup hoặc event store để xác định completeness.

## 25. Alert riêng cho telemetry stale hoặc missing

Không có sample quality có thể do ít traffic hoặc pipeline hỏng. Cần tách hai trường hợp.

Ví dụ alert khi telemetry source không có event thành công trong 5 phút:

~~~yaml
groups:
  - name: spring-ai-telemetry
    rules:
      - alert: AiEvaluationTelemetryStale
        expr: |
          time() -
          app_ai_telemetry_last_success_timestamp_seconds{
            source="online_sampled"
          } > 300
        for: 2m
        labels:
          severity: warning
          team: ai-quality
        annotations:
          summary: "Online evaluation telemetry is stale"
          description: "Check evaluator workers, queue lag and telemetry export."
~~~

Ví dụ alert khi metric heartbeat hoàn toàn biến mất:

~~~yaml
- alert: AiEvaluationTelemetryMetricMissing
  expr: absent(app_ai_telemetry_last_success_timestamp_seconds{source="online_sampled"})
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Evaluation telemetry heartbeat is missing"
    description: "Verify scrape target, exporter and source pipeline."
~~~

absent() chỉ phát hiện series không tồn tại theo selector. Với nhiều source/partition, nên có expected-source inventory hoặc heartbeat metric theo source/partition hữu hạn để phát hiện thiếu một phần.

Lưu ý: increase() và rate() trong Prometheus ước lượng mức tăng dựa trên các samples scrape trong range; kết quả increase() có thể là số thập phân do extrapolation ở biên cửa sổ. Minimum count dùng trong alert vì thế là guard gần đúng. Nếu cần denominator nguyên chính xác cho báo cáo evaluation run hoặc release gate, truy vấn evaluation store theo event IDs/run ID.

Không coi stale telemetry là quality pass rate 0% hoặc 100%. Đó là telemetry/pipeline health incident.

## 26. Alert cho oldest pending age

Ví dụ evaluator case bị pending hơn 10 phút:

~~~yaml
- alert: AiEvaluationOldestPendingTooHigh
  expr: max by (queue) (app_ai_eval_oldest_pending_age_seconds) > 600
  for: 5m
  labels:
    severity: warning
    team: ai-quality
  annotations:
    summary: "Evaluation cases are waiting too long"
    description: "Inspect queue consumers, provider latency and retry backlog."
~~~

Ngưỡng 600 giây là ví dụ. Nếu không có pending cases, gauge cần có semantics rõ: zero khi queue rỗng và series vẫn được scrape. Nếu metric biến mất khi queue rỗng, alert phải xử lý no-series riêng.

Đặt alert age theo SLA hoàn tất evaluation, không theo một con số tùy ý. Release gate có thể cần chờ lâu hơn online monitoring.

## 27. Late arrival và backfill

Có những nguồn dữ liệu đến trễ theo batch hoặc replay:

- Human review được nhập sau vài giờ.
- Provider billing export đến ngày hôm sau.
- Evaluation worker replay event sau outage.
- Dataset import chạy theo batch.
- Trace exporter retry sau mất kết nối.

Không nên dùng cùng một freshness target cho tất cả sources. Mỗi source cần:
- Expected arrival cadence.
- Maximum acceptable lag.
- Completeness expectation.
- Late-arrival policy.
- Backfill window.
- Owner.

Backfill có thể làm thay đổi aggregate lịch sử. Ghi correction event hoặc snapshot version để giải thích tại sao báo cáo hôm qua khác với báo cáo hôm nay.

Không increment lại counter như thể event mới vừa xảy ra nếu đang replay dữ liệu lịch sử. Dùng event store có idempotency key và metric riêng cho backfill/replay throughput.

## 28. Idempotency khi nhận event trễ hoặc retry

Một event có thể được gửi nhiều lần do broker redelivery hoặc worker retry. Cần idempotency để không đếm trùng.

Một event record có thể có:

~~~json
{
  "eventId": "eval-event-1042-final",
  "caseId": "case-1042",
  "evaluationRunId": "run-2026-11-27-01",
  "eventTime": "2026-11-27T10:02:00Z",
  "processedAt": "2026-11-27T10:09:00Z",
  "ingestedAt": "2026-11-27T10:10:00Z",
  "outcome": "FAIL",
  "source": "online_sampled",
  "eventVersion": 1
}
~~~

Schema là ví dụ ứng dụng đề xuất. Dùng unique event ID hoặc composite idempotency key phù hợp với semantics. Nếu một case được adjudicate và verdict thay đổi, tạo event/version mới có quan hệ supersedes; không ghi đè lịch sử mà không lưu audit.

Metrics counter nên được cập nhật sau khi event đã được commit/idempotently accepted. Nếu database commit thành công nhưng metric update thất bại, có thể cần outbox hoặc reconciliation để tránh thiếu count.

## 29. Tách quality regression khỏi evaluator lag

Một dashboard evaluation nên có hai vùng riêng:

| Vùng | Metric | Khi xấu cần làm gì? |
|---|---|---|
| Quality | PASS/FAIL, pass rate, score distribution | Review failed cases và prompt/model |
| Coverage | Selected, applicable, evaluated, skipped | Kiểm tra policy và completeness |
| Evaluator health | Attempt errors, invalid output, latency | Kiểm tra judge/provider |
| Pipeline freshness | Event lag, watermark age, last success | Kiểm tra telemetry/worker |
| Queue | Pending count, oldest age, consumer lag | Tăng capacity hoặc xử lý stuck jobs |
| Backfill | Late events, replay count, corrections | Đối soát aggregate và event IDs |

Nếu quality pass rate giảm nhưng coverage/freshness/judge health ổn định, khả năng regression nội dung cao hơn.

Nếu pass rate có vẻ cao nhưng coverage thấp, lag cao hoặc judge errors tăng, không kết luận quality đạt. Đánh dấu quality signal là incomplete.

## 30. Alertmanager grouping và inhibition để giảm noise

Khi nhiều series cùng vi phạm, Alertmanager có thể group alerts theo service, route, criterion hoặc severity để giảm notification trùng.

Ví dụ:
- Group theo alertname, service, route.
- Không group theo trace ID hoặc request ID.
- Inhibit quality alerts chi tiết khi evaluator telemetry stale ở cùng source/route.
- Vẫn giữ alert telemetry stale để người trực biết nguyên nhân dashboard quality không đáng tin.

Inhibition chỉ ngăn notification của alert phụ khi alert chính đang firing; nó không xóa alert state. Cấu hình matcher phải đủ chặt để không suppress các service/route khác.

Không dùng inhibition để che tất cả alerts khi có một provider issue chung nếu một số alert còn phản ánh user impact độc lập.

Tài liệu: [Alertmanager — Configuration](https://prometheus.io/docs/alerting/latest/configuration/).

## 31. Ví dụ alert policy theo trạng thái dữ liệu

| Trạng thái | Điều kiện | Hành động |
|---|---|---|
| Healthy evidence | Sample đủ, freshness đạt, coverage đạt, quality trên target | Hiển thị kết quả bình thường |
| Low sample | Denominator dưới minimum | Không fire quality regression; tiếp tục thu thập |
| Quality warning | Point estimate dưới target, interval còn giao target | Review cases và theo dõi |
| Confirmed quality regression | Confidence bound vượt qua ngưỡng vi phạm, sample đủ | Alert quality owner/release owner |
| Data stale | Lag vượt freshness target | Alert telemetry/evaluator owner |
| Coverage low | Selected applicable không có verdict hợp lệ | Kiểm tra queue, skip và judge errors |
| Source missing | Heartbeat/expected partition không có | Điều tra scrape/export/source outage |
| Late correction | Backfill thay đổi aggregate lịch sử | Ghi audit và cập nhật report version |

Đây là policy mẫu. Với một số criterion có rủi ro cao, có thể tạo human-review alert ngay cả khi sample nhỏ. Điều đó khác với việc tuyên bố đã có bằng chứng thống kê cho toàn cohort.

## 32. Runbook khi alert quality không đủ sample

Khi quality alert không fire do sample thấp hoặc dashboard hiển thị N/A:

1. Xác nhận traffic thật của route/cohort.
2. Kiểm tra eligible và selected counts.
3. Kiểm tra sampling policy có thay đổi không.
4. Xem source heartbeat và last-success timestamp.
5. Kiểm tra pending count, oldest age và queue lag.
6. Xem event-time/processing-time delay distribution.
7. Nếu traffic thấp có chủ đích, chờ cửa sổ dài hơn hoặc chạy synthetic check cho serving health.
8. Với release candidate, chạy fixed offline dataset thay vì chờ production traffic.
9. Ghi trạng thái insufficient evidence trong dashboard/report.
10. Không gán pass/fail giả để lấp dữ liệu thiếu.

Nếu một tác vụ có rủi ro cao, thực hiện manual review theo policy ngay cả khi sample nhỏ.

## 33. Runbook khi dữ liệu đến trễ

Khi freshness alert fire:

1. Xác định source, stream, partition và environment.
2. So event time, processing time và ingest time.
3. Kiểm tra queue depth, oldest message age và consumer lag.
4. Kiểm tra evaluator/provider latency, rate limit và retry.
5. Kiểm tra Collector/exporter, scrape target và storage ingestion.
6. Xác định window đang provisional hay đã finalized.
7. Kiểm tra late event count và watermark progress.
8. Nếu cần replay/backfill, dùng idempotent event IDs và audit correction.
9. Đối soát aggregate sau khi backlog được xử lý.
10. Chỉ bỏ trạng thái incomplete khi freshness và completeness đạt target.

Không rollback prompt chỉ vì quality dashboard thiếu dữ liệu do evaluator đang chậm. Trước tiên xác định signal có đáng tin cậy không.

## 34. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Alert từ 1/1 failure | Page do mẫu quá nhỏ | Minimum sample và confidence policy |
| 0/10 được xem là error rate zero đáng tin | Đánh giá thấp rủi ro | Hiển thị interval/sample count |
| Dùng for thay minimum sample | Tỷ lệ nhỏ vẫn fire lâu dài | Kết hợp denominator guard |
| Denominator zero thành 0% | No data bị hiểu là healthy | Hiển thị N/A và freshness alert |
| Dùng processing time cho traffic quality | Cases đến trễ rơi sai cửa sổ | Nhóm theo event time |
| Coi counter Prometheus là event-time store | Không thể xử lý late arrivals chính xác | Event store/watermark rollup |
| Không đo queue age | Không biết cases bị kẹt | Oldest pending age |
| Grace period quá dài | Phát hiện regression chậm | Đo lag distribution và đặt SLA |
| Backfill increment counter lần nữa | Đếm trùng lịch sử | Idempotency và correction events |
| Gộp cohort không tương đương | Che regression subgroup | Chỉ aggregate nhóm có cùng semantics |
| Alert quality khi telemetry stale | False quality incident | Tách data freshness và quality alerts |
| Chỉ dùng heartbeat tổng | Một partition mất dữ liệu bị che | Heartbeat theo source/partition |

## 35. Bài tập tự kiểm tra

### Bài 1 — Cỡ mẫu nhỏ

Một cohort có 1 PASS và 1 FAIL. Pass rate là 50%. Có nên page vì quality regression không?

**Đáp án:** Chưa đủ bằng chứng cho xu hướng cohort. Ghi nhận hai cases, review nếu có rủi ro cao và chờ sample theo policy.

### Bài 2 — Minimum sample

Một alert yêu cầu tối thiểu 200 evaluated cases/24h. Cohort có 199 cases và pass rate 70%. Alert quality có fire không?

**Đáp án:** Không theo rule đó. Dashboard cần hiển thị insufficient sample và theo dõi coverage/traffic/freshness riêng.

### Bài 3 — Zero failures

Có 0 failures trên 20 requests. Có thể kết luận error probability bằng zero không?

**Đáp án:** Không. Rule of three cho upper 95% bound xấp xỉ 3/20 = 15%.

### Bài 4 — Đến trễ

Một request xảy ra lúc 10:02, judge hoàn tất lúc 10:09 và event được ingest lúc 10:10. Nó thuộc quality event-time window nào?

**Đáp án:** Window chứa 10:02. Processing throughput thuộc window chứa 10:09; ingest freshness được tính từ 10:10 trừ 10:02.

### Bài 5 — Queue backlog

Quality pass rate hiện là 98%, nhưng oldest pending age tăng lên 20 phút và coverage giảm còn 50%. Có thể báo quality đạt không?

**Đáp án:** Không. Quality result incomplete; cần điều tra queue/evaluator lag và không suy diễn từ các cases đã chấm.

### Bài 6 — Offset query

Telemetry có delay ổn định 2 phút. Dùng [15m] offset 2m có tác dụng gì và trade-off nào?

**Đáp án:** Query đọc một cửa sổ đã lùi lại 2 phút để giảm thiếu dữ liệu mới đến. Đổi lại alert phát hiện muộn hơn và offset không xử lý được delay biến động.

### Bài 7 — Backfill

Worker replay 1.000 evaluation events đã xử lý trước đó. Làm sao tránh tăng counter terminal outcome thêm 1.000 lần?

**Đáp án:** Idempotent event IDs/unique constraints; chỉ metric hóa events mới được commit. Ghi replay/correction metrics riêng.

### Bài 8 — Thiếu một partition

Heartbeat tổng vẫn có dữ liệu nhưng partition region-b không có event mới. Cần làm gì?

**Đáp án:** Theo dõi heartbeat/last-success theo source và partition hữu hạn, so với expected partition inventory; không chỉ dùng heartbeat toàn cục.

## 36. Checklist trước khi bật alert

- [ ] Mọi ratio panel đều có numerator, denominator và sample size?
- [ ] Quality denominator chỉ gồm PASS + FAIL?
- [ ] ERROR, INVALID, SKIPPED, NOT_APPLICABLE và PENDING có panel riêng?
- [ ] Có minimum sample phù hợp với baseline và risk?
- [ ] Có confidence interval hoặc uncertainty policy?
- [ ] Zero failures trên sample nhỏ không bị coi là zero risk?
- [ ] Low-traffic route có long window hoặc synthetic checks?
- [ ] Synthetic traffic tách khỏi production quality cohort?
- [ ] for không bị dùng thay minimum sample?
- [ ] Denominator zero hiển thị N/A/no data?
- [ ] Event time, processing time và ingest time được lưu riêng?
- [ ] Evaluation quality được nhóm theo event time?
- [ ] Processing throughput được đo theo processing time?
- [ ] Có watermark/grace period và late-arrival policy?
- [ ] Có freshness, completeness, queue lag và oldest pending age?
- [ ] Stale/missing telemetry có alert riêng?
- [ ] Backfill/replay dùng idempotency và audit correction?
- [ ] Alert quality chỉ fire khi data completeness đạt policy?
- [ ] Có runbook cho insufficient sample và delayed data?
- [ ] Alertmanager grouping/inhibition không che user-impact alerts?

## 37. Tài liệu tham khảo

1. [Prometheus — Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/): range vectors, offset modifier và selectors.
2. [Prometheus — Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): rate, increase, absent, time và histogram quantiles.
3. [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): for, keep_firing_for, labels và annotations.
4. [Prometheus — Alertmanager configuration](https://prometheus.io/docs/alerting/latest/configuration/): grouping, routing, inhibition và notification.
5. [Prometheus — Instrumentation practices](https://prometheus.io/docs/practices/instrumentation/): metric semantics và theo dõi failures/in-progress work.
6. [NIST/SEMATECH — e-Handbook of Statistical Methods](https://www.itl.nist.gov/div898/handbook/): confidence intervals và phương pháp thống kê.
7. [Brown, Cai, DasGupta — Interval Estimation for a Binomial Proportion](https://doi.org/10.1214/ss/1009213286): phân tích các phương pháp interval cho tỷ lệ nhị thức.
8. [Apache Flink — Time and Order in Streams](https://nightlies.apache.org/flink/flink-docs-stable/docs/concepts/time/): event time, processing time, watermarks và late events.
9. [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): chọn cửa sổ alert và giảm cảnh báo nhiễu.
10. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): observations và metrics cho ChatClient/ChatModel.

*Các sample thresholds, grace periods, lag targets và PromQL trong bài là ví dụ. Hãy hiệu chỉnh bằng traffic, event-delay distribution, risk và SLA của từng pipeline. Khi dữ liệu chưa đủ hoặc chưa hoàn tất, thể hiện rõ trạng thái incomplete/insufficient evidence thay vì tự điền tỷ lệ zero hoặc kết luận quality đạt.*
