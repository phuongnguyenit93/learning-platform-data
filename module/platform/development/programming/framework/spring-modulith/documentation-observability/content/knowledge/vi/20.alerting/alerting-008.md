# Đặt ngưỡng theo baseline thay vì giá trị tùy ý

## 1. Vì sao không nên chọn ngưỡng cảnh báo theo cảm tính?

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, các application module như **orders**, **payments**, **inventory** và **notifications** có thể phát domain event, gọi API của module khác và xử lý công việc bất đồng bộ. Nhóm vận hành cần phát hiện khi request lỗi tăng, latency vượt mức chấp nhận, event publication giảm bất thường hoặc listener không xử lý được công việc.

Một cách làm dễ gặp là đặt ngưỡng tùy ý: CPU trên 80%, latency trên 500 ms, event rate giảm 50% hoặc error rate trên 1%. Các con số đó có thể hữu ích ở một hệ thống, nhưng không tự động phù hợp với hệ thống khác. Một endpoint bình thường mất 700 ms có thể bị cảnh báo liên tục; một endpoint thường trả lời trong 20 ms nhưng tăng lên 250 ms có thể đã có dấu hiệu suy giảm rõ rệt dù chưa vượt ngưỡng cố định.

**Baseline** là mức hoạt động tham chiếu được xây dựng từ dữ liệu lịch sử hoặc mục tiêu dịch vụ. Đặt ngưỡng theo baseline giúp cảnh báo nhận biết điều gì bất thường đối với chính dịch vụ, module, loại event và thời điểm hoạt động đó. Tuy nhiên, baseline không thay thế SLO: ngưỡng cảnh báo vẫn phải phản ánh tác động tới người dùng và khả năng hành động của đội trực.

Bài **“Đặt ngưỡng theo baseline thay vì giá trị tùy ý”** thuộc chương **Alerting** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Bài học hướng dẫn kết hợp baseline lịch sử với SLO, traffic volume và thời gian duy trì; xây dựng Prometheus alert rules; giảm cảnh báo giả; và dùng metrics, module spans, logs cùng module graph để điều tra.

Sau bài học, bạn có thể:

- Giải thích baseline, ngưỡng cố định, ngưỡng tương đối và SLO khác nhau thế nào.
- Chọn baseline phù hợp với chu kỳ theo giờ, ngày trong tuần và mùa vụ.
- Kết hợp độ lệch tương đối, mức tuyệt đối, volume tối thiểu và thời gian duy trì.
- Viết PromQL/Prometheus rules để so sánh hiện tại với baseline.
- Dùng error budget burn rate và nhiều cửa sổ thời gian để cảnh báo theo SLO.
- Theo dõi event publication của Spring Modulith mà không nhầm publication với listener success.
- Thiết kế alert có owner, severity, runbook và notification grouping.

## 2. Baseline là gì?

**Baseline** là mô tả định lượng về hoạt động thông thường của một tín hiệu trong điều kiện có thể so sánh. Baseline không chỉ là một con số trung bình. Nó cần cho biết mức điển hình, độ biến động và bối cảnh thời gian của metric.

Ví dụ một dịch vụ có request rate theo giờ:

| Thời điểm | Request rate thường gặp |
| --- | ---: |
| Ngày làm việc, 09:00–10:00 | 120–160 request/giây |
| Ngày làm việc, 13:00–14:00 | 70–100 request/giây |
| Đêm, 02:00–03:00 | 3–8 request/giây |
| Cuối tuần, 10:00–11:00 | 15–30 request/giây |

Nếu đặt cảnh báo request rate thấp hơn 50 request/giây cho mọi thời điểm, hệ thống có thể báo động liên tục vào ban đêm và cuối tuần. Nếu chỉ dùng một baseline trung bình cho cả ngày, mức hoạt động bình thường ở giờ cao điểm và giờ thấp điểm bị trộn lẫn.

Một baseline hữu ích nên được xác định theo:

- **Tín hiệu:** request rate, error ratio, latency, event publication rate, queue/backlog hoặc consumer failure.
- **Phạm vi:** service, route template, module hoặc event type có ý nghĩa vận hành.
- **Cửa sổ thời gian:** 5 phút, 15 phút, 1 giờ hoặc một khoảng dài hơn tùy mục tiêu.
- **Chu kỳ:** giờ trong ngày, ngày trong tuần, ngày lễ hoặc mùa vụ.
- **Mức biến động:** median, percentile hoặc dải dao động lịch sử.
- **Điều kiện áp dụng:** traffic tối thiểu, lịch vận hành và trạng thái triển khai.

### 2.1. Ba loại ngưỡng thường dùng

| Loại ngưỡng | Cách xác định | Dùng khi nào? |
| --- | --- | --- |
| Ngưỡng cố định | Một giá trị được xác định từ yêu cầu/SLO hoặc giới hạn kỹ thuật | Error ratio tối đa 1%; latency p95 không quá 500 ms |
| Ngưỡng baseline | So sánh với lịch sử tương ứng và độ biến động | Request rate giảm bất thường so với cùng khung giờ các tuần trước |
| Ngưỡng kết hợp | Baseline + giới hạn tuyệt đối + volume tối thiểu + thời gian duy trì | Error ratio tăng gấp 3 baseline nhưng chỉ cảnh báo khi có đủ request và kéo dài |

Không có một loại ngưỡng phù hợp cho mọi tín hiệu. SLO là giới hạn chất lượng dịch vụ cần giữ; baseline cho biết hoạt động hiện tại có khác thường so với lịch sử hay không. Hai góc nhìn bổ sung cho nhau.

## 3. Thu thập dữ liệu trước khi đặt baseline

Không nên đặt baseline từ vài phút dữ liệu hoặc từ một giai đoạn hệ thống đang có sự cố. Cần xác định dữ liệu nào đại diện cho hoạt động bình thường.

### 3.1. Chọn khoảng lịch sử có tính đại diện

Gợi ý thực tế:

- Thu thập tối thiểu một vài chu kỳ đầy đủ; với dịch vụ có biến động theo tuần, nên có nhiều tuần dữ liệu.
- So sánh cùng giờ và cùng thứ trong tuần khi traffic có seasonality.
- Loại trừ hoặc đánh dấu giai đoạn outage, deploy lớn, bảo trì và sự kiện kinh doanh đặc biệt.
- Tách các chế độ hoạt động khác nhau, ví dụ ngày bán hàng bình thường và chiến dịch flash sale.
- Đánh giá lại baseline sau thay đổi lớn về traffic, kiến trúc, capacity hoặc hành vi người dùng.

Một baseline lịch sử bị ảnh hưởng bởi sự cố kéo dài có thể coi trạng thái xấu là bình thường. Vì vậy, không nên tự động cập nhật baseline mà không có bước xem xét dữ liệu bất thường.

### 3.2. Chọn thống kê phù hợp

| Thống kê | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| Mean (trung bình) | Tổng giá trị chia số quan sát | Dễ bị kéo lệch bởi spike hoặc outage |
| Median (trung vị) | Giá trị giữa của tập quan sát | Bền vững hơn trước outlier |
| p90/p95 | Mức mà phần lớn quan sát không vượt qua | Hữu ích cho latency và dải hoạt động |
| Min/max | Biên nhỏ nhất/lớn nhất | Nhạy với outlier, không nên dùng đơn độc |
| MAD (median absolute deviation) | Độ phân tán quanh median | Hữu ích với dữ liệu lệch, cần công cụ tính phù hợp |
| SLO target | Mức chất lượng cam kết | Là mục tiêu dịch vụ, không phải mô tả lịch sử |

Với traffic và latency thường lệch, median và percentile thường có ý nghĩa hơn mean ± một số độ lệch chuẩn. Dải baseline nên được kiểm chứng bằng dữ liệu thực tế, không áp dụng một hệ số thống kê máy móc cho mọi metric.

### 3.3. Không trộn các nhóm có hành vi khác nhau

Một số ví dụ:

- Không gộp request đọc và request ghi nếu chúng có latency khác nhau đáng kể.
- Không gộp mọi module nếu module orders phát event thường xuyên hơn module notifications.
- Không gộp giờ làm việc và ban đêm nếu sản phẩm có chu kỳ sử dụng rõ ràng.
- Không gộp môi trường staging với production.
- Không gộp event type có tần suất khác nhau vào một baseline duy nhất nếu mục tiêu là phát hiện một event cụ thể bị ngừng phát.

Tuy vậy, tránh chia baseline thành quá nhiều nhóm nhỏ. Mỗi chiều bổ sung làm giảm số quan sát trong từng nhóm và khiến baseline kém ổn định. Chỉ phân nhóm khi nó cải thiện khả năng giải thích hoặc hành động.

## 4. Kết hợp baseline với ngưỡng tuyệt đối

Một cảnh báo chỉ dựa trên tỷ lệ thay đổi có thể gây báo động khi baseline gần bằng 0. Ví dụ event rate tăng từ 0.01 lên 0.1 event/giây là tăng 10 lần, nhưng chưa chắc có ý nghĩa vận hành. Ngược lại, một thay đổi nhỏ về tỷ lệ ở traffic rất lớn có thể ảnh hưởng nhiều người dùng.

Một điều kiện cảnh báo tốt thường kết hợp:

1. **Độ lệch tương đối:** hiện tại cao/thấp hơn baseline bao nhiêu lần hoặc bao nhiêu phần trăm.
2. **Mức tuyệt đối:** metric đã vượt giới hạn có ý nghĩa vận hành chưa.
3. **Volume tối thiểu:** có đủ request/event để tỷ lệ có ý nghĩa thống kê không.
4. **Thời gian duy trì:** bất thường có kéo dài đủ lâu để loại nhiễu ngắn hạn không.
5. **Lịch hoạt động:** dịch vụ/module có được kỳ vọng hoạt động trong khung giờ này không.

Ví dụ:
- Cảnh báo error ratio khi cao hơn 3 lần baseline **và** lớn hơn 2%.
- Chỉ áp dụng khi có ít nhất 30 request trong cửa sổ đánh giá.
- Điều kiện phải kéo dài 10 phút trước khi chuyển sang firing.
- Nếu SLO error budget bị tiêu thụ nhanh, tạo cảnh báo riêng theo burn rate.

Các con số trên là ví dụ minh họa. Ngưỡng thực tế phải dựa trên SLO, traffic, mức độ ảnh hưởng và thời gian đội vận hành cần để phản ứng.

## 5. Baseline cho các tín hiệu quan trọng

### 5.1. Request rate

Request rate cho biết lượng request đến dịch vụ trong một đơn vị thời gian. Baseline nên xét cùng giờ trong ngày và cùng ngày trong tuần khi traffic có chu kỳ.

Cảnh báo request rate giảm bất thường chỉ có ý nghĩa nếu hệ thống được kỳ vọng có traffic trong khung giờ đó. Một endpoint nội bộ chỉ được gọi theo lịch có thể không nhận request vào ban đêm; không nên page vì rate bằng 0 nếu đây là hành vi bình thường.

Cần kết hợp:
- Request rate hiện tại và baseline cùng khung giờ.
- Mức traffic tối thiểu để xác định dịch vụ đang hoạt động.
- Health check/availability để phân biệt traffic giảm do ít người dùng hay do dịch vụ không nhận request.
- Error ratio và latency để xác định mức giảm traffic có đi cùng lỗi hay không.

### 5.2. Error ratio

Error ratio là tỷ lệ request lỗi trên tổng request đủ điều kiện:

\[
\text{Error ratio} =
\frac{\text{Số request lỗi}}{\text{Tổng request}}
\]

Không dùng số lượng lỗi đơn lẻ làm tín hiệu duy nhất. 10 lỗi trong 10 request và 10 lỗi trong 100.000 request có ý nghĩa khác nhau.

Baseline error ratio có thể được tính từ các cửa sổ lịch sử tương ứng. Tuy nhiên, khi SLO đặt giới hạn lỗi tối đa 0.1%, không được để baseline lịch sử cao hơn mức này biến trạng thái xấu thành bình thường. SLO vẫn là rào chắn độc lập.

### 5.3. Latency

Latency nên được theo dõi bằng histogram để có thể tính percentile có thể tổng hợp giữa instance. Với Micrometer Timer, cần bật percentile histogram hoặc các SLO buckets phù hợp nếu backend cần histogram để tính quantile. Client-side percentile riêng lẻ không thể cộng gộp chính xác qua nhiều instance.

Ví dụ p95 hiện tại theo service:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, job) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Metric và label trong ví dụ phụ thuộc registry và cấu hình ứng dụng. Cần xác minh histogram bucket đã được xuất trước khi dùng query.

Khi so với baseline, nên so sánh cùng route template và khung giờ. Không nên dùng một baseline latency chung cho mọi endpoint nếu thời gian xử lý bình thường khác nhau.

### 5.4. Spring Modulith event publication

Spring Modulith cung cấp các metric quan sát event publication:

- Metric tổng hợp **module.events.published** ghi nhận số event được công bố.
- Metric riêng theo module và event type cho phép theo dõi một loại event cụ thể.
- Các tag có cardinality thấp gồm module identifier, module name và event type.

Ví dụ PromQL minh họa nếu Prometheus registry xuất metric/label theo tên tương ứng:

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
~~~

Tên metric và label có thể được chuẩn hóa theo registry/version. Kiểm tra /actuator/prometheus trước khi dùng query trong production.

Baseline event publication có thể giúp phát hiện:
- Event type quan trọng đột ngột ngừng được phát.
- Module phát event nhiều hơn đáng kể so với nhịp bình thường.
- Lượng event thay đổi bất thường sau deploy.
- Một module không còn phát event trong thời gian mà nghiệp vụ kỳ vọng hoạt động.

**Publication metric không chứng minh listener đã xử lý thành công.** Nếu cần cảnh báo listener thất bại, publication bị tồn đọng hoặc retry tăng, phải theo dõi trạng thái event publication registry hoặc instrument consumer outcome/backlog riêng. Không suy ra consumer success từ counter publication.

### 5.5. Queue và event backlog

Với xử lý bất đồng bộ, backlog thường là tín hiệu quan trọng hơn số event đã phát. Baseline cần xem:
- Số publication đang chờ xử lý.
- Số publication ở trạng thái processing quá lâu.
- Số publication failed/resubmitted.
- Tuổi của publication cũ nhất.
- Tốc độ event đến so với tốc độ consumer hoàn tất.

Spring Modulith 2.x có event publication lifecycle với các trạng thái như PUBLISHED, PROCESSING, COMPLETED, FAILED và RESUBMITTED; phiên bản mới còn có ABANDONED. Có thể dùng dữ liệu registry để xây dựng metric/health signal phù hợp, nhưng không mặc định mọi trạng thái đều có metric sẵn. Cần instrument theo phiên bản và persistence implementation đang dùng.

## 6. Xây dựng baseline theo cùng thời điểm tuần trước

Một cách đơn giản để bắt đầu là so sánh metric hiện tại với cùng thời điểm của tuần trước. Cách này phù hợp với hệ thống có chu kỳ tuần tương đối ổn định, nhưng có thể sai nếu tuần trước có ngày lễ, chiến dịch hoặc sự cố.

Prometheus hỗ trợ toán tử ¤offset¤ để dịch thời điểm truy vấn về quá khứ. Ví dụ:

~~~promql
sum(rate(http_server_requests_seconds_count[5m]))
/
sum(rate(http_server_requests_seconds_count[5m] offset 1w))
~~~

Kết quả là tỷ lệ request rate hiện tại so với cùng khoảng thời gian cách đây một tuần. Nếu kết quả 0.4, traffic hiện tại bằng khoảng 40% tuần trước tại cùng thời điểm.

Không nên cảnh báo chỉ vì tỷ lệ thấp. Hãy thêm điều kiện baseline lịch sử đủ lớn, khung giờ có hoạt động dự kiến và kiểm tra tín hiệu sức khỏe dịch vụ.

### 6.1. Dùng median của nhiều tuần tương ứng

So sánh một tuần có thể bị ảnh hưởng bởi một sự kiện bất thường. Có thể xây dựng baseline bằng median của các điểm cùng thời điểm trong nhiều tuần trước. Ví dụ sau tạo baseline từ các quan sát cùng thời điểm trong tám tuần trước, lấy mẫu cách nhau một tuần:

~~~promql
quantile_over_time(
  0.5,
  (
    sum by (job) (
      rate(http_server_requests_seconds_count[5m])
    )
  )[8w:1w] offset 1w
)
~~~

Đây là ví dụ subquery; chi phí đánh giá có thể cao nếu áp dụng cho nhiều metric/label. Trong hệ thống lớn, nên dùng recording rules hoặc pipeline phân tích baseline chuyên dụng thay vì tính lại subquery nặng cho mọi alert mỗi lần đánh giá.

Baseline lịch sử cần đủ dữ liệu. Nếu metric mới được tạo, scrape bị gián đoạn hoặc label thay đổi sau deploy, baseline có thể không có giá trị. Trong trường hợp đó, dùng SLO/threshold cố định tạm thời và không coi giá trị baseline rỗng là bình thường.

## 7. Ví dụ recording rules và alert theo baseline

Ví dụ dưới đây tạo request rate, error rate và baseline median theo cùng khung giờ trong tám tuần trước. Các metric names là dạng Prometheus phổ biến; hãy điều chỉnh label service theo hệ thống thực tế.

~~~yaml
groups:
  - name: shop-backend-baseline
    interval: 1m
    rules:
      - record: service:http_requests:rate5m
        expr: |
          sum by (job) (
            rate(http_server_requests_seconds_count[5m])
          )

      - record: service:http_5xx:rate5m
        expr: |
          sum by (job) (
            rate(http_server_requests_seconds_count{status=~"5.."}[5m])
          )

      - record: service:http_5xx_ratio:rate5m
        expr: |
          service:http_5xx:rate5m
          /
          clamp_min(service:http_requests:rate5m, 1e-9)

      - record: service:http_requests:baseline
        expr: |
          quantile_over_time(
            0.5,
            (service:http_requests:rate5m)[8w:1w] offset 1w
          )

      - record: service:http_5xx_ratio:baseline
        expr: |
          quantile_over_time(
            0.5,
            (service:http_5xx_ratio:rate5m)[8w:1w] offset 1w
          )
~~~

Giải thích:
- Recording rule giúp tái sử dụng biểu thức và giảm việc tính lại query phức tạp ở nhiều alert/dashboard.
- Baseline median dùng các quan sát cùng thứ/giờ trong những tuần trước.
- Cửa sổ 5 phút làm mượt nhiễu ngắn hạn; khoảng đánh giá có thể cần thay đổi theo traffic.
- Khi metric thiếu lịch sử, baseline có thể không xuất hiện; phải có quy tắc fallback.

Alert khi error ratio cao hơn baseline:

~~~yaml
groups:
  - name: shop-backend-alerts
    rules:
      - alert: HttpErrorRatioAboveBaseline
        expr: |
          (
            service:http_5xx_ratio:rate5m
            >
            clamp_min(
              service:http_5xx_ratio:baseline * 3,
              0.02
            )
          )
          and on (job)
          (
            service:http_requests:rate5m > 0.1
          )
        for: 10m
        keep_firing_for: 5m
        labels:
          severity: page
          team: commerce-platform
        annotations:
          summary: "HTTP error ratio cao hơn baseline"
          description: "Service {{ $labels.job }} đang có error ratio {{ $value }}; kiểm tra dashboard và runbook."
          runbook_url: "https://runbooks.example.com/http-errors"
~~~

Trong ví dụ:
- Error ratio phải lớn hơn ba lần baseline hoặc tối thiểu 2%, lấy điều kiện nghiêm ngặt hơn.
- Request rate phải lớn hơn 0.1 request/giây, tương đương khoảng 30 request trong 5 phút, để tránh cảnh báo tỷ lệ trên mẫu quá nhỏ.
- Điều kiện phải duy trì 10 phút mới firing.
- keep_firing_for giữ alert trong một khoảng ngắn khi tín hiệu vừa hồi phục, giúp giảm flapping.

Đây là rule minh họa. Cần xác minh metric names, label status/job, evaluation interval, SLO và mức traffic phù hợp trước khi áp dụng. Nếu dịch vụ có traffic thấp, dùng cửa sổ dài hơn hoặc chính sách xử lý low-volume riêng.

## 8. SLO và error budget burn rate

Baseline cho biết hành vi thường thấy; **SLO** xác định chất lượng dịch vụ cần đạt. Nếu SLO là 99.9% availability, tỷ lệ lỗi cho phép trong cửa sổ đo là:

\[
1 - 0.999 = 0.001 = 0.1\%
\]

**Burn rate** cho biết error budget đang bị tiêu thụ nhanh gấp bao nhiêu lần tốc độ cho phép:

\[
\text{Burn rate} =
\frac{\text{Error ratio thực tế}}{1 - \text{SLO}}
\]

Với SLO 99.9%, error ratio 1.44% tương đương burn rate 14.4 lần. Nếu mức tiêu thụ này kéo dài, dịch vụ sẽ cạn error budget nhanh hơn nhiều so với kế hoạch.

### 8.1. Vì sao dùng nhiều cửa sổ thời gian?

Một cửa sổ ngắn phản ứng nhanh nhưng dễ nhiễu; một cửa sổ dài ổn định hơn nhưng có thể phát hiện muộn. Multi-window, multi-burn-rate alert yêu cầu cả cửa sổ dài và ngắn cùng vượt ngưỡng. Cách này giảm cảnh báo do spike thoáng qua nhưng vẫn phát hiện sự cố đang tiêu thụ error budget nhanh.

Ví dụ khởi điểm cho SLO 99.9% theo hướng dẫn Google SRE:

| Mức | Cửa sổ dài | Cửa sổ ngắn | Burn rate | Ý nghĩa |
| --- | --- | --- | ---: | --- |
| Page | 1 giờ | 5 phút | 14.4x | Tiêu thụ nhanh, cần phản ứng ngay |
| Page | 6 giờ | 30 phút | 6x | Sự cố kéo dài, ảnh hưởng đáng kể |
| Ticket | 3 ngày | 6 giờ | 1x | Theo dõi và xử lý theo kế hoạch |

Đây là thông số khởi điểm cho SLO 99.9%, không phải ngưỡng dùng chung cho mọi SLO hoặc dịch vụ.

### 8.2. Ví dụ biểu thức burn rate

Giả sử recording rules đã tạo các error ratio theo nhiều cửa sổ:

~~~promql
(
  service:sli_error_ratio:rate1h > 14.4 * 0.001
  and
  service:sli_error_ratio:rate5m > 14.4 * 0.001
)
or
(
  service:sli_error_ratio:rate6h > 6 * 0.001
  and
  service:sli_error_ratio:rate30m > 6 * 0.001
)
~~~

Biểu thức này minh họa hai điều kiện page cho SLO 99.9%. Trong triển khai thật, cần group theo service có cùng SLO, thêm traffic/volume guard nếu phù hợp và tạo rule riêng cho SLO khác.

### 8.3. Dịch vụ traffic thấp cần cách xử lý riêng

Với dịch vụ chỉ có vài request mỗi giờ, một request lỗi có thể làm error ratio tăng rất cao. Burn rate tính đúng về toán học nhưng chưa chắc đủ để page ngay. Có thể:
- Dùng cửa sổ dài hơn và số lượng mẫu tối thiểu.
- Kết hợp số lỗi tuyệt đối với error ratio.
- Phân biệt lỗi một lần có thể retry với lỗi hệ thống kéo dài.
- Dùng cảnh báo ticket hoặc dashboard cho tín hiệu chưa đủ độ tin cậy.
- Theo dõi queue/event publication nếu hệ thống xử lý bất đồng bộ thay vì chỉ dựa vào HTTP traffic.

## 9. Đặt baseline cho event và module

### 9.1. Event publication giảm bất thường

Giả sử module orders thường phát OrderPlaced trong giờ bán hàng. Một cảnh báo có thể so sánh event rate hiện tại với baseline cùng thời điểm:

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
~~~

Có thể xây dựng recording rule baseline cho từng module/event type tương tự request rate. Chỉ cảnh báo khi:
- Baseline đủ lớn để kỳ vọng event được phát.
- Đang ở khung giờ nghiệp vụ có hoạt động.
- Event rate hiện tại giảm đáng kể so với baseline.
- Tình trạng kéo dài đủ lâu.
- Có tín hiệu bổ sung như request rate vẫn cao nhưng event publication giảm.

Không cảnh báo event rate bằng 0 cho một module vốn không phát event vào giờ đó. Nếu label hoặc metric name khác phiên bản ví dụ, kiểm tra /actuator/prometheus và điều chỉnh query.

### 9.2. Publication không đồng nghĩa listener hoàn tất

Spring Modulith event publication metric đếm sự kiện được công bố. Một event có thể có nhiều listener; publisher metric tăng không chứng minh từng listener đã hoàn thành. Để cảnh báo processing:
- Instrument counter/timer cho listener outcome theo module, event type và outcome.
- Theo dõi trạng thái publication registry nếu ứng dụng dùng persistent event publication registry.
- Cảnh báo backlog hoặc publication FAILED/PROCESSING quá lâu bằng dữ liệu có sẵn.
- Dùng trace/module spans để xác định listener hoặc module gây chậm.

Không đưa event ID, order ID, trace ID hoặc user ID vào metric tags để tìm từng publication. Những ID đó phù hợp với logs/traces hoặc giao diện tra cứu nghiệp vụ.

### 9.3. Ví dụ alert event rate thấp

Đây là biểu thức minh họa khi đã có recording rules cho event rate và baseline:

~~~promql
(
  module:event_publications:rate5m
  <
  module:event_publications:baseline * 0.2
)
and on (module_identifier, module_event_type)
(
  module:event_publications:baseline > 0.1
)
~~~

Điều kiện có nghĩa event rate hiện tại thấp hơn 20% baseline và baseline lịch sử lớn hơn 0.1 event/giây. Trong thực tế, cần thêm lịch hoạt động, traffic nghiệp vụ và thời gian duy trì. Với module/event có traffic không đều, dùng cửa sổ dài hơn và tránh page theo một khoảng ngắn.

## 10. Tránh cảnh báo giả và alert flapping

Một alert tốt không chỉ phát hiện đúng vấn đề mà còn phải giữ trạng thái ổn định và đưa ra hành động rõ ràng.

### 10.1. Dùng cửa sổ đánh giá và pending period

Prometheus hỗ trợ:
- **for:** điều kiện phải đúng liên tục trong thời gian này trước khi alert chuyển từ pending sang firing.
- **keep_firing_for:** giữ alert firing thêm một khoảng sau khi điều kiện không còn đúng, giúp tránh flapping hoặc resolve quá nhanh.

Ví dụ:
- Error ratio vượt ngưỡng trong 10 phút mới page.
- Alert giữ firing thêm 5 phút khi hệ thống hồi phục để tránh gửi nhiều thông báo firing/resolved liên tiếp.

Không chọn thời gian quá dài khiến sự cố nghiêm trọng bị phát hiện muộn. Thời gian đánh giá cần phù hợp với SLO và thời gian phản ứng mong muốn.

### 10.2. Dùng recovery threshold hoặc hysteresis

Nếu một metric dao động quanh ngưỡng, có thể tạo khoảng cách giữa điều kiện firing và điều kiện phục hồi. Ví dụ:
- Firing khi error ratio trên 2%.
- Chỉ xem đã phục hồi khi error ratio xuống dưới 1% trong một cửa sổ đủ dài.

Hysteresis giúp tránh alert bật/tắt liên tục khi metric dao động sát một ngưỡng. Cần bảo đảm rule engine và công cụ alert hỗ trợ cách triển khai tương ứng.

### 10.3. Không page mọi chỉ số nội bộ

Ưu tiên alert theo triệu chứng người dùng cảm nhận:
- Request thất bại.
- Latency vượt SLO.
- Event quan trọng không được phát trong khi có traffic.
- Consumer backlog tăng không kiểm soát.
- Publication FAILED hoặc processing bị kẹt quá lâu.

CPU, memory, pod restart hoặc một module metric bất thường có thể hữu ích cho chẩn đoán, nhưng chỉ nên page khi chúng có tác động hoặc nguy cơ rõ ràng. Tín hiệu không cần hành động ngay nên nằm trên dashboard hoặc kênh cảnh báo mức thấp.

## 11. Prometheus alert labels, annotations và Alertmanager

Một alert cần giúp người trực hiểu vấn đề và biết phải làm gì.

**Labels** nên là các chiều ổn định để phân loại và định tuyến, ví dụ:
- service
- team/owner
- severity
- environment
- module nếu module là tập nhỏ và có ý nghĩa vận hành

**Annotations** nên chứa nội dung mô tả, giá trị hiện tại, dashboard link và runbook URL. Không đưa user ID, request ID, order ID hoặc trace ID vào label của alert vì các giá trị đó làm tăng số alert instance và gây khó grouping. Nếu cần định danh trace, dùng annotation hoặc link được tạo trong quá trình điều tra, không dùng nó làm nhãn phân luồng.

Ví dụ rule có owner và runbook:

~~~yaml
- alert: ModulithEventPublicationBelowBaseline
  expr: |
    module:event_publications:rate5m
      < module:event_publications:baseline * 0.2
  for: 15m
  labels:
    severity: warning
    team: commerce-platform
    service: shop-backend
  annotations:
    summary: "Event publication giảm dưới baseline"
    description: "Kiểm tra module {{ $labels.module_identifier }} và event {{ $labels.module_event_type }}."
    runbook_url: "https://runbooks.example.com/modulith-events"
~~~

Ví dụ này giả định recording rules và labels đã được cấu hình. Cần thêm baseline floor, traffic gate và khung giờ kỳ vọng trước khi dùng rule trong production.

### 11.1. Grouping và routing

Alertmanager hoặc Grafana Alerting có thể:
- Group nhiều alert instance liên quan thành một notification.
- Route theo severity, service hoặc team.
- Đặt group wait, group interval và repeat interval.
- Silence trong maintenance window có kiểm soát.
- Inhibit alert phụ khi alert nguyên nhân gốc đã firing.

Ví dụ: database không truy cập được có thể làm nhiều module cùng tăng latency và error rate. Grouping theo service/team giúp người trực nhận một notification có nhiều tín hiệu liên quan thay vì hàng chục thông báo rời rạc. Inhibition có thể giảm cảnh báo phụ, nhưng phải kiểm tra kỹ để không vô tình che mất một sự cố độc lập.

## 12. Dashboard nên hiển thị baseline như thế nào?

Dashboard hỗ trợ hiểu vì sao alert firing và baseline có còn phù hợp không. Với mỗi tín hiệu quan trọng, nên hiển thị:
- Giá trị hiện tại.
- Median hoặc percentile baseline.
- Dải dao động lịch sử.
- Ngưỡng SLO cố định.
- Traffic volume để diễn giải tỷ lệ.
- Deployment/maintenance annotations nếu có.

Ví dụ bố cục:

| Panel | Hiển thị |
| --- | --- |
| Request rate | Hiện tại so với median cùng khung giờ trong 8 tuần |
| Error ratio | Hiện tại, baseline, SLO limit và số request |
| p95 latency | Histogram quantile hiện tại và SLO latency |
| Event publication | Rate theo module/event type so với baseline |
| Consumer processing | Success/failure, backlog và tuổi publication |
| Error budget | Burn rate theo các cửa sổ thời gian |
| Trace drill-down | Link từ exemplar hoặc điều kiện metric sang trace |
| Module architecture | Link tới module graph/Actuator để xem dependency |

Không nên chỉ vẽ một đường baseline trung bình. Hãy thể hiện độ biến động để người trực biết một thay đổi nhỏ có thực sự bất thường hay vẫn nằm trong dải bình thường.

## 13. Quy trình xây dựng alert từ baseline

1. **Xác định tác động cần phát hiện:** user request lỗi, latency tăng, event quan trọng bị ngừng phát hay consumer backlog tăng.
2. **Chọn SLI:** error ratio, request latency, availability, event publication rate hoặc processing outcome.
3. **Xác định SLO/giới hạn tuyệt đối:** đây là rào chắn không được để baseline hợp thức hóa trạng thái xấu.
4. **Thu thập dữ liệu lịch sử:** bao phủ các chu kỳ hoạt động và đánh dấu outage, deploy, ngày lễ.
5. **Chọn baseline:** median cùng giờ/ngày trong tuần, percentile hoặc dải thống kê phù hợp.
6. **Đặt guardrails:** độ lệch tương đối, mức tuyệt đối, traffic tối thiểu, lịch hoạt động và for duration.
7. **Viết recording/alert rules:** tái sử dụng biểu thức và giữ label ổn định.
8. **Kiểm thử bằng dữ liệu lịch sử:** xem alert có fire trong incident cũ không, có fire vô ích trong giờ thấp điểm không.
9. **Viết runbook:** nêu dashboard, log/trace search, module cần kiểm tra và bước xử lý đầu tiên.
10. **Đo chất lượng alert:** số lần fire, false positive, thời gian phát hiện, thời gian phản ứng và incident bị bỏ lỡ.
11. **Review định kỳ:** cập nhật baseline khi traffic hoặc kiến trúc thay đổi; xóa alert không còn hành động được.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng một ngưỡng cho mọi giờ | Báo giả ở giờ thấp điểm, bỏ lỡ bất thường ở giờ cao điểm | Baseline theo chu kỳ thời gian |
| Chỉ dùng tỷ lệ thay đổi | Báo động khi baseline gần 0 | Thêm absolute floor và volume gate |
| Chỉ dùng baseline lịch sử | Trạng thái xấu kéo dài bị coi là bình thường | Giữ SLO/absolute limit độc lập |
| Dùng mean với dữ liệu nhiều outlier | Baseline bị lệch bởi spike/incident | Dùng median, quantile hoặc thống kê robust |
| Baseline không có đủ lịch sử | Alert không ổn định hoặc không có kết quả | Fallback về SLO/threshold cố định và báo thiếu dữ liệu |
| Cảnh báo event rate bằng 0 mọi lúc | Báo giả khi module không được kỳ vọng hoạt động | Thêm schedule/traffic expectation |
| Dùng publication counter làm listener success | Bỏ lỡ listener failure/backlog | Instrument consumer outcome và theo dõi publication registry |
| Alert mỗi module/instance mà không grouping | Notification storm | Group theo service/team và nguyên nhân |
| Không có owner/runbook | Người trực không biết phải làm gì | Gắn team, severity, runbook |
| Tự động học baseline từ cả thời gian outage | Baseline dần chấp nhận trạng thái lỗi | Loại incident và review quá trình cập nhật |

## 15. Checklist trước khi bật alert production

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Alert phát hiện tác động gì? | Có liên hệ với user experience hoặc rủi ro vận hành cụ thể |
| Baseline lấy từ đâu? | Có đủ lịch sử và cùng khung hoạt động |
| Baseline có bị ảnh hưởng bởi incident/deploy? | Đã đánh dấu hoặc loại dữ liệu không đại diện |
| Có SLO/absolute guardrail? | Baseline không thể hợp thức hóa chất lượng thấp |
| Có traffic volume tối thiểu? | Không page từ tỷ lệ trên mẫu quá nhỏ |
| Có for duration? | Loại spike ngắn nhưng không trì hoãn quá mức |
| Có low-traffic policy? | Dịch vụ ít request có cách xử lý riêng |
| Alert labels có ổn định? | Chỉ dùng service/team/severity/module có giới hạn |
| Có owner và runbook? | Người trực biết nơi kiểm tra và hành động đầu tiên |
| Notification được grouping/routing? | Tránh nhiều page cho cùng nguyên nhân |
| Có dashboard baseline? | Có thể giải thích vì sao điều kiện fire |
| Có kiểm thử lịch sử? | Đã xem false positive và incident bị bỏ lỡ |
| Có review định kỳ? | Baseline và ngưỡng được cập nhật theo thay đổi thực tế |

## 16. Ghi nhớ

**Baseline cho biết điều gì là bình thường đối với chính dịch vụ trong bối cảnh có thể so sánh; SLO cho biết mức chất lượng dịch vụ cần giữ.** Không nên thay mọi ngưỡng cố định bằng một con số baseline duy nhất. Hãy kết hợp baseline theo chu kỳ, giới hạn tuyệt đối, volume tối thiểu và thời gian duy trì để cảnh báo có ý nghĩa.

Với Spring Modulith, dùng event publication metrics để theo dõi nhịp phát event theo module/event type; instrument riêng consumer outcome và backlog nếu cần biết listener có hoàn tất hay không. Kết hợp request metrics, latency histogram, module spans, logs và module graph để xác định module liên quan sau khi alert firing.

Một alert production tốt có owner, severity, runbook, routing và grouping rõ ràng. Sau mỗi incident, đánh giá alert phát hiện quá sớm, quá muộn hay thiếu thông tin; cập nhật baseline từ dữ liệu đại diện và không để thời gian sự cố biến thành chuẩn hoạt động mới.

## Tài liệu tham khảo

- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): biểu thức alert, pending duration, labels, annotations và keep_firing_for.
- [Prometheus — Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/): grouping, routing, silences và inhibition.
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): error budget burn rate và multi-window, multi-burn-rate alerts.
- [Grafana — Alerting Best Practices](https://grafana.com/docs/grafana/latest/alerting/guides/best-practices/): symptom-based alerting, actionability, pending periods, grouping và review.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo frequency, duration và timer behavior.
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): percentile histogram, aggregable quantiles và SLO buckets.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module observations, event publication metrics và module metadata.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): event publication lifecycle và trạng thái listener publication.

> **Giới hạn:** Metric names, label names và PromQL trong bài là ví dụ theo cấu hình Prometheus phổ biến; cần xác minh output thực tế của /actuator/prometheus. Baseline query, SLO và thời gian pending phải được hiệu chỉnh theo traffic, lịch hoạt động và mục tiêu dịch vụ. Bài thuộc STEP 4; Content QA và refactor chuyên môn được thực hiện ở bước QA tiếp theo.
