# Đặt SLI, SLO và cảnh báo theo tác động đến người dùng

## Bối cảnh: giám sát để biết dịch vụ có thực sự phục vụ tốt

Một máy ảo có thể đang `RUNNING`, CPU chưa chạm ngưỡng và memory vẫn còn, nhưng người dùng vẫn gặp timeout khi mở ứng dụng. Ngược lại, CPU có thể tăng cao trong một đợt tải lớn nhưng hệ thống vẫn đáp ứng nhanh và không có lỗi. Nếu chỉ cảnh báo theo trạng thái máy hoặc ngưỡng tài nguyên, đội vận hành dễ bỏ lỡ sự cố ảnh hưởng người dùng hoặc nhận quá nhiều cảnh báo không cần hành động.

Để tập trung vào chất lượng dịch vụ, cần xác định **SLI (Service Level Indicator)**, **SLO (Service Level Objective)** và cảnh báo gắn với tác động thực tế:

- **SLI** là chỉ số đo lường một khía cạnh của dịch vụ mà người dùng quan tâm, ví dụ tỷ lệ request thành công hoặc tỷ lệ request hoàn tất trong 300 ms.
- **SLO** là mục tiêu định lượng cho SLI trong một khoảng thời gian, ví dụ 99,9% request hợp lệ thành công trong cửa sổ 30 ngày.
- **Alert** là tín hiệu yêu cầu con người hoặc hệ thống phản ứng khi có lỗi, mức tiêu thụ error budget hoặc nguy cơ ảnh hưởng người dùng vượt ngưỡng.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, SLI/SLO giúp liên kết CPU, RAM, network, storage, VM, container và serverless với kết quả mà ứng dụng cung cấp. Mục tiêu là biết dịch vụ đang tốt hay xấu theo trải nghiệm, ưu tiên xử lý đúng vấn đề và cân bằng độ tin cậy với tốc độ phát hành.

## 1. SLI, SLO và SLA khác nhau thế nào?

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| SLI | Chỉ số đo lường thực tế | 99,94% request API thành công trong 30 ngày |
| SLO | Mục tiêu nội bộ hoặc mục tiêu dịch vụ cho SLI | Ít nhất 99,9% request API thành công trong 30 ngày |
| SLA | Cam kết chính thức với khách hàng, thường có điều khoản và biện pháp khi không đạt | Nếu availability thấp hơn cam kết, khách hàng có thể đủ điều kiện nhận service credit |

SLI trả lời “dịch vụ đang hoạt động ra sao?”. SLO trả lời “mức chất lượng nào là mục tiêu?”. SLA trả lời “tổ chức cam kết điều gì với khách hàng và hậu quả hợp đồng là gì?”. SLO có thể nghiêm ngặt hơn SLA để tổ chức có biên an toàn trước khi vi phạm cam kết.

Không nên gọi mọi metric là SLI. CPU utilization, số thread hoặc số pod là metric vận hành hữu ích, nhưng chỉ trở thành SLI trực tiếp khi chúng đại diện cho một kết quả người dùng quan tâm. Ví dụ, tỷ lệ request hoàn tất đúng hạn là SLI; CPU cao có thể là tín hiệu chẩn đoán hoặc dự báo nguy cơ làm SLI xấu đi.

## 2. Chọn SLI từ hành trình người dùng

Bắt đầu bằng việc xác định dịch vụ cung cấp điều gì và người dùng nhận ra thất bại như thế nào. Với API, người dùng quan tâm request có thành công và phản hồi đủ nhanh không. Với hệ thống xử lý đơn hàng, họ còn quan tâm đơn có được xử lý đúng và trạng thái có cập nhật kịp thời không. Với dịch vụ lưu trữ, họ quan tâm dữ liệu có thể đọc lại, có đúng và có sẵn khi cần không.

Các nhóm SLI phổ biến:

| Nhóm SLI | Câu hỏi của người dùng | Ví dụ đo lường |
|---|---|---|
| Availability / success | Request có hoàn tất thành công không? | Good requests / valid requests |
| Latency | Phản hồi có đủ nhanh không? | Tỷ lệ request dưới ngưỡng 300 ms; p95/p99 để chẩn đoán |
| Throughput / capacity | Dịch vụ có xử lý được lượng công việc cần thiết không? | Request hoặc job hoàn tất mỗi giây/phút |
| Correctness | Kết quả có đúng không? | Tỷ lệ giao dịch được xác minh đúng hoặc không có lỗi nghiệp vụ |
| Freshness | Dữ liệu có được cập nhật đủ mới không? | Tuổi dữ liệu hoặc độ trễ từ lúc phát sinh đến lúc khả dụng |
| Durability / recoverability | Dữ liệu có được giữ và khôi phục khi cần không? | Tỷ lệ restore test thành công, RPO/RTO đạt mục tiêu |

Không nhất thiết mọi dịch vụ đều cần một SLI cho từng nhóm. Chọn một số ít chỉ số đại diện cho các hành trình quan trọng, có thể đo đáng tin cậy và có người chịu trách nhiệm.

### 2.1. Bắt đầu từ hành trình quan trọng

Ví dụ với dịch vụ đặt hàng:

1. Người dùng gửi yêu cầu tạo đơn.
2. API xác thực và kiểm tra dữ liệu.
3. Hệ thống ghi đơn vào database.
4. Event được đưa vào queue.
5. Worker xử lý thanh toán hoặc giao hàng.
6. Người dùng nhìn thấy trạng thái đơn được cập nhật.

Một API trả HTTP 200 chưa chắc toàn bộ hành trình đã hoàn tất. Nếu event bị kẹt trong queue hoặc worker không xử lý, người dùng vẫn thấy đơn ở trạng thái chờ quá lâu. Vì vậy, dịch vụ có thể cần SLI cho success/latency của API và SLI freshness hoặc processing delay cho trạng thái đơn.

### 2.2. Chọn ranh giới đo

Đo ở ranh giới gần người dùng nhất có thể, chẳng hạn tại API gateway hoặc điểm vào dịch vụ. Metric nội bộ của từng VM/pod giúp chẩn đoán, nhưng không luôn phản ánh lỗi từ DNS, load balancer, TLS, network hoặc dependency.

Nếu dịch vụ có nhiều endpoint, phân loại theo hành trình hoặc mức độ quan trọng. Không để endpoint ít sử dụng che khuất lỗi của chức năng cốt lõi, và không để một endpoint lỗi nhỏ làm sai lệch toàn bộ chỉ số nếu người dùng có thể bị ảnh hưởng khác nhau.

## 3. Định nghĩa SLI rõ ràng và có thể kiểm chứng

Một SLI cần nêu chính xác:

- **Population:** request, transaction, job hoặc người dùng nào nằm trong mẫu đo?
- **Good event:** điều kiện nào được tính là thành công?
- **Bad event:** điều kiện nào được tính là thất bại?
- **Measurement point:** đo tại client, gateway, service hay backend?
- **Window:** tổng hợp trong khoảng thời gian nào?
- **Exclusions:** trường hợp nào được loại khỏi mẫu và vì sao?

Ví dụ định nghĩa SLI availability cho API:

```text
valid_requests = các request hợp lệ đến endpoint production
good_requests  = request trả kết quả thành công theo hợp đồng API
                 trong giới hạn timeout đã định nghĩa

availability SLI = good_requests / valid_requests
```

Các lỗi 5xx, timeout và lỗi nội bộ thường là bad events. Một số 4xx do người dùng gửi dữ liệu không hợp lệ có thể được loại khỏi SLI availability của nền tảng, nhưng phải định nghĩa rõ. Nếu 429 do hệ thống giới hạn tải khiến người dùng không thể thực hiện hành động hợp lệ, nó có thể là bad event. Không được loại một loại lỗi chỉ để làm chỉ số đẹp hơn khi người dùng vẫn chịu ảnh hưởng.

### 3.1. SLI latency

Latency SLI nên đo tỷ lệ request hợp lệ hoàn tất dưới ngưỡng đã chọn:

```text
latency SLI = requests_completed_within_threshold / valid_requests
```

Ví dụ: ít nhất 99% request hợp lệ hoàn tất trong 300 ms. Đây là mục tiêu theo tỷ lệ request, khác với việc chỉ nhìn p99. Percentile như p95/p99 rất hữu ích để phân tích phân phối và tail latency; nhưng không nên lấy trung bình p99 của nhiều instance để tính SLI toàn dịch vụ. Hãy tổng hợp histogram hoặc dữ liệu request phù hợp trên toàn population.

### 3.2. SLI cho job, queue và dữ liệu

Với xử lý bất đồng bộ, một job được nhận vào queue không đồng nghĩa đã hoàn tất. Có thể đo:

- Tỷ lệ job hợp lệ hoàn tất thành công.
- Tỷ lệ job hoàn tất trong thời hạn nghiệp vụ.
- Tuổi của message lâu nhất trong queue.
- Độ trễ từ event tạo ra đến lúc kết quả có thể được người dùng sử dụng.

Với pipeline dữ liệu, freshness có thể đo bằng thời gian từ timestamp nguồn đến lúc bản ghi hoặc partition sẵn sàng. Cần xử lý event trễ, dữ liệu đến sai thứ tự và job bị retry để tránh đo sai.

### 3.3. Tránh định nghĩa SLI dễ bị thao túng

Một số sai lầm thường gặp:

- Chỉ đo request đã đến backend, bỏ qua request bị chặn ở gateway hoặc load balancer.
- Chỉ đo health check nội bộ, không đo hành trình người dùng.
- Loại timeout hoặc 429 khỏi mẫu dù chúng làm người dùng không hoàn tất được việc.
- Đếm một retry thành một request thành công mà bỏ qua việc người dùng phải chờ lâu hoặc gửi lại nhiều lần.
- Đo trung bình latency thay vì phân phối và tỷ lệ vượt ngưỡng.
- Chọn denominator thay đổi theo lỗi, khiến lúc hệ thống hỏng thì request thất bại biến mất khỏi mẫu đo.

Định nghĩa và phiên bản SLI cần được tài liệu hóa để các nhóm hiểu cùng một cách và có thể kiểm toán.

## 4. Đặt SLO có ý nghĩa

SLO cần có mục tiêu, population, cửa sổ thời gian và nguồn đo. Ví dụ:

> Trong mỗi cửa sổ trượt 30 ngày, ít nhất 99,9% request hợp lệ đến API production phải hoàn tất thành công.

Một SLO khác có thể đặt cho latency:

> Trong mỗi cửa sổ trượt 30 ngày, ít nhất 99% request hợp lệ phải hoàn tất trong 300 ms.

SLO nên phản ánh nhu cầu người dùng và khả năng vận hành thực tế. Mục tiêu 99,999% không có ý nghĩa nếu hệ thống chưa có kiến trúc, telemetry và quy trình phục hồi tương ứng. SLO quá dễ đạt không tạo động lực cải thiện; SLO quá chặt có thể tiêu tốn chi phí lớn mà không tạo thêm giá trị tương xứng.

### 4.1. Chọn cửa sổ thời gian

Các cửa sổ thường dùng:

- **Rolling window:** ví dụ 30 ngày gần nhất; phản ánh chất lượng liên tục và cập nhật mỗi lần đo.
- **Calendar window:** ví dụ tháng dương lịch; dễ báo cáo nhưng sự cố sát ranh giới tháng có thể bị chia nhỏ.
- **Short window:** vài phút hoặc một giờ; hữu ích cho cảnh báo nhanh nhưng ít phù hợp để định nghĩa cam kết dài hạn độc lập.

SLO và cảnh báo có thể dùng nhiều cửa sổ. SLO theo 30 ngày giúp đánh giá mục tiêu; alert dùng 5 phút, 1 giờ hoặc 6 giờ để phát hiện tốc độ tiêu thụ error budget.

### 4.2. Chọn mức mục tiêu dựa trên nhu cầu

Để chọn SLO, hãy xem:

1. Mức gián đoạn hoặc chậm trễ người dùng có thể chấp nhận.
2. Cam kết hợp đồng hoặc SLA nếu có.
3. Kiến trúc hiện tại, failure domain, dependency và khả năng khôi phục.
4. Lịch sử SLI và biến động theo giờ/ngày/mùa.
5. Chi phí để cải thiện thêm một mức độ tin cậy.
6. Năng lực đo lường và xử lý cảnh báo của đội vận hành.

Nên bắt đầu từ dữ liệu thực tế, sau đó thống nhất SLO với product owner, kỹ thuật và vận hành. Khi thay đổi SLO, cần ghi rõ lý do, thời điểm hiệu lực và tác động đến error budget.

### 4.3. SLO cho nhiều cấp dịch vụ

Một sản phẩm có thể có SLO ở cấp tổng thể và SLI/SLO riêng cho các thành phần quan trọng. Ví dụ, trang web có thể đặt SLO cho thao tác người dùng hoàn tất; API gateway, database và queue có metric nội bộ giúp tìm nguyên nhân. Không nên nhân cơ học SLO của từng thành phần để suy ra SLO tổng thể nếu các dependency không độc lập hoặc có retry/fallback.

Với dịch vụ có nhiều endpoint, có thể đặt SLO riêng cho luồng quan trọng như đăng nhập, thanh toán hoặc tìm kiếm. Trọng số cần phản ánh lưu lượng hoặc tầm quan trọng nghiệp vụ, không chỉ số lượng endpoint.

## 5. Error budget: phần lỗi được phép trong SLO

Error budget là phần không đạt SLI tối đa mà SLO cho phép trong cửa sổ đo. Với SLO dựa trên tỷ lệ request thành công:

```text
error_budget_fraction = 1 - SLO_target
allowed_bad_events = valid_events x error_budget_fraction
```

Ví dụ SLO availability 99,9% có error budget 0,1%. Nếu có 1.000.000 request hợp lệ trong cửa sổ, tối đa 1.000 request có thể là bad event mà vẫn đạt mục tiêu.

### 5.1. Tính thời gian gián đoạn tương đương

Nếu SLO được định nghĩa theo thời gian availability liên tục, mục tiêu 99,9% trong cửa sổ 30 ngày cho phép:

\[
30\times24\times60\times(1-0.999)=43.2\text{ phút}
\]

Đây là phép quy đổi cho SLO theo thời gian. Nếu SLO được tính theo request, số phút downtime không trực tiếp tương đương error budget vì lưu lượng thay đổi theo thời điểm. Một phút lỗi trong giờ cao điểm có thể tiêu thụ nhiều budget hơn một phút lỗi lúc ít người dùng.

### 5.2. Dùng error budget để ra quyết định

Error budget giúp nhóm quyết định khi nào cần ưu tiên độ tin cậy:

- Budget còn nhiều: tiếp tục phát hành theo quy trình bình thường và theo dõi.
- Budget tiêu thụ nhanh: giảm rủi ro rollout, tăng kiểm thử hoặc hoãn thay đổi không khẩn cấp.
- Budget gần cạn hoặc đã cạn: ưu tiên sửa nguyên nhân, giảm thay đổi rủi ro cao và cải thiện khả năng phục hồi.

Error budget không phải mục tiêu để “đốt hết”. Đây là giới hạn rủi ro được chấp nhận, không phải quota lỗi cần sử dụng. Cũng không nên tự động đóng băng mọi phát hành chỉ vì budget thấp nếu có bản vá bảo mật hoặc thay đổi khẩn cấp cần thiết; cần policy cân bằng giữa rủi ro bảo mật và độ tin cậy.

### 5.3. Ví dụ bảng theo dõi budget

| SLI/SLO | Target | Error budget | Đo lường |
|---|---:|---:|---|
| API availability | 99,9% | 0,1% request | Good requests / valid requests |
| API latency | 99% dưới 300 ms | 1% request vượt ngưỡng | Requests dưới 300 ms / valid requests |
| Job completion | 99,5% trong 5 phút | 0,5% job trễ hoặc thất bại | Job đúng hạn / eligible jobs |

Các ví dụ là mục tiêu minh họa. SLO thực tế cần được chọn theo hành vi người dùng, mức quan trọng và dữ liệu baseline của dịch vụ.

## 6. Cảnh báo theo tốc độ tiêu thụ error budget

Cảnh báo chỉ dựa vào “CPU trên 90%” hoặc “memory trên 85%” thường tạo nhiều tín hiệu không gắn trực tiếp với sự cố. Cảnh báo theo **error budget burn rate** tập trung vào tốc độ dịch vụ đang tiêu thụ ngân sách lỗi.

Burn rate là tỷ lệ giữa error rate quan sát được và error rate cho phép theo SLO:

```text
allowed_error_rate = 1 - SLO_target
observed_error_rate = bad_events / valid_events
burn_rate = observed_error_rate / allowed_error_rate
```

Nếu SLO là 99,9%, error rate cho phép là 0,1%. Nếu trong một cửa sổ quan sát, 1% request bị lỗi thì burn rate là 10 lần tốc độ cho phép. Nếu tốc độ đó kéo dài, budget sẽ cạn nhanh hơn kế hoạch.

### 6.1. Vì sao cần nhiều cửa sổ?

Một cửa sổ rất ngắn phản ứng nhanh nhưng dễ bị nhiễu bởi một spike nhỏ. Một cửa sổ dài ổn định hơn nhưng có thể phát hiện quá muộn. Kết hợp cửa sổ ngắn và dài giúp alert vừa phản ứng với sự cố rõ rệt, vừa tránh báo động do một vài request lỗi ngẫu nhiên.

Ví dụ, alert có thể yêu cầu burn rate cao đồng thời trong 5 phút và 1 giờ. Một điều kiện khác có thể theo dõi burn rate vừa phải trong 30 phút và 6 giờ. Ngưỡng cụ thể phải hiệu chỉnh theo SLO, lưu lượng và thời gian đội vận hành cần để phản ứng.

### 6.2. Ví dụ burn rate

Giả sử SLO availability 99,9%, error budget fraction là 0,001:

| Error rate quan sát | Burn rate | Diễn giải |
|---:|---:|---|
| 0,1% | 1x | Đúng bằng tốc độ tiêu thụ tối đa theo mục tiêu |
| 0,2% | 2x | Tiêu thụ budget nhanh gấp đôi |
| 1% | 10x | Budget bị tiêu thụ rất nhanh |
| 5% | 50x | Sự cố lớn, có thể cần phản ứng khẩn cấp |

Burn rate cần được tính từ cùng định nghĩa population và bad event với SLI. Nếu metric alert dùng denominator khác SLO, kết quả có thể gây hiểu nhầm.

### 6.3. Mẫu multi-window, multi-burn-rate

Với SLO 99,9% theo cửa sổ 30 ngày (720 giờ), có thể bắt đầu thử nghiệm các ngưỡng minh họa:

| Mức | Burn rate | Cửa sổ dài và ngắn | Ý nghĩa gần đúng |
|---|---:|---|---|
| Critical/page | 14,4x | 1 giờ và 5 phút | Có thể tiêu thụ khoảng 2% error budget trong 1 giờ |
| Warning/ticket | 6x | 6 giờ và 30 phút | Có thể tiêu thụ khoảng 5% error budget trong 6 giờ |

Điều kiện yêu cầu cả cửa sổ dài và ngắn vượt ngưỡng giúp tránh alert khi chỉ có một spike ngắn. Các con số là điểm khởi đầu thường dùng cho SLO 30 ngày, không phải ngưỡng bắt buộc. Cần điều chỉnh theo lưu lượng, mức độ nghiêm trọng, thời gian phản ứng và khả năng phân biệt sự cố thật.

### 6.4. Ví dụ Prometheus alert rule

Giả sử ứng dụng xuất counter `http_requests_total` với label `service`, `environment` và `outcome`, trong đó `outcome` có giá trị `good` hoặc `bad` theo định nghĩa SLI. Có thể tạo recording rule cho error ratio rồi dùng nhiều cửa sổ:

```yaml
groups:
  - name: orders-api-slo
    rules:
      - record: service:sli_error_ratio:rate5m
        expr: |
          sum(rate(http_requests_total{
            service="orders-api",
            environment="prod",
            outcome="bad"
          }[5m]))
          /
          clamp_min(sum(rate(http_requests_total{
            service="orders-api",
            environment="prod",
            outcome=~"good|bad"
          }[5m])), 1e-9)

      - alert: OrdersApiHighErrorBudgetBurn
        expr: |
          (
            sum(rate(http_requests_total{
              service="orders-api",
              environment="prod",
              outcome="bad"
            }[5m]))
            /
            clamp_min(sum(rate(http_requests_total{
              service="orders-api",
              environment="prod",
              outcome=~"good|bad"
            }[5m])), 1e-9)
          ) > 0.0144
          and
          (
            sum(rate(http_requests_total{
              service="orders-api",
              environment="prod",
              outcome="bad"
            }[1h]))
            /
            clamp_min(sum(rate(http_requests_total{
              service="orders-api",
              environment="prod",
              outcome=~"good|bad"
            }[1h])), 1e-9)
          ) > 0.0144
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "Orders API is burning its availability error budget quickly"
          description: "Investigate user-visible failures, dependencies and recent changes."
```

Ví dụ giả định metric đã được instrument đúng và label `outcome` phản ánh cùng SLI với SLO. Trong hệ thống thực, nên dùng recording rule riêng cho từng cửa sổ, thêm điều kiện số request tối thiểu để tránh kích hoạt dựa trên mẫu quá nhỏ, và kiểm tra cú pháp với phiên bản Prometheus đang chạy. `clamp_min` trong ví dụ chỉ tránh mẫu số bằng không; nó không thay thế chính sách xử lý low traffic.

## 7. Cảnh báo phải dẫn đến hành động

Một alert tốt cho người trực biết điều gì đang ảnh hưởng, mức độ khẩn cấp và bước đầu cần kiểm tra. Không nên page chỉ vì một metric vượt ngưỡng nếu chưa có dấu hiệu ảnh hưởng dịch vụ hoặc nguy cơ sắp xảy ra.

### 7.1. Phân biệt alert triệu chứng và alert nguyên nhân

- **Symptom alert:** người dùng đang gặp lỗi, latency tăng, job trễ hoặc SLO burn nhanh. Đây thường là tín hiệu phù hợp để page.
- **Cause/resource alert:** CPU, RAM, disk, connection pool hoặc network đang gần giới hạn. Tín hiệu này hữu ích để phát hiện sớm, nhưng chỉ nên page khi có nguy cơ rõ ràng hoặc đã gây tác động.
- **Diagnostic signal:** log, trace và metric chi tiết giúp tìm nguyên nhân sau khi alert được kích hoạt.

Ví dụ, CPU 95% trong một phút có thể không cần page nếu latency và error rate vẫn bình thường. Nhưng nếu CPU throttling kéo dài khiến tỷ lệ request dưới 300 ms giảm và burn rate tăng, cần page theo SLO và dùng CPU metric để chẩn đoán.

### 7.2. Phân loại mức độ phản ứng

| Mức | Khi nào dùng | Kênh phản ứng |
|---|---|---|
| Page / Critical | Tác động lớn đang diễn ra, SLO budget burn nhanh, cần người phản ứng ngay | On-call trực tiếp, incident channel |
| Warning | Xu hướng xấu hoặc budget tiêu thụ đáng kể nhưng chưa cần đánh thức người trực | Ticket, chat nhóm vận hành hoặc ca làm việc |
| Info | Thay đổi trạng thái, dự báo hoặc thông tin phục vụ capacity planning | Dashboard, log hoặc báo cáo |

Mỗi alert cần có owner, severity, service/environment, link dashboard, runbook và điều kiện clear. Alert không có người chịu trách nhiệm hoặc không có hành động cụ thể sẽ tạo nhiễu.

### 7.3. Gắn alert với người dùng và phạm vi ảnh hưởng

Alert nên nêu:

- Dịch vụ và hành trình người dùng bị ảnh hưởng.
- Tỷ lệ lỗi hoặc latency hiện tại so với SLO.
- Số request/user/tenant bị ảnh hưởng nếu đo được.
- Vùng, endpoint, phiên bản hoặc nhóm workload liên quan.
- Thời điểm bắt đầu và tốc độ tăng của sự cố.
- Thay đổi gần đây, dependency hoặc deployment có liên quan nếu đã xác định.

Không nên suy đoán nguyên nhân trong tiêu đề alert. Hãy mô tả triệu chứng và liên kết dữ liệu để người trực kiểm tra.

## 8. Kết nối SLI với metric compute và hạ tầng

Metric hạ tầng không thay thế SLI, nhưng giúp giải thích vì sao SLI xấu đi. Cần theo dõi theo các lớp của compute stack:

| Lớp | Metric hữu ích | Có thể ảnh hưởng SLI như thế nào |
|---|---|---|
| VM/host CPU | CPU utilization, steal time, load, throttling, run queue | Tăng thời gian xử lý, timeout hoặc giảm throughput |
| VM/host memory | Working set, swap, page fault, OOM, memory pressure | GC pause, reclaim, OOM kill hoặc process restart |
| Storage | IOPS, throughput, queue depth, latency, volume fullness | Database chậm, ghi thất bại hoặc job bị trễ |
| Network | Packet loss, retransmission, RTT, connection errors, bandwidth | Request timeout, lỗi dependency hoặc giảm thông lượng |
| Container/orchestrator | Pod pending, restart, throttling, node pressure, readiness | Replica thiếu, rollout chậm hoặc request bị phân phối sai |
| Serverless | Cold start, concurrency, throttling, duration, invocation errors | Tăng latency hoặc request không được xử lý |
| Dependency | Database pool, queue age, cache hit, downstream error | Hành trình người dùng không hoàn tất dù compute còn khỏe |

Nên gắn nhãn metric theo service, environment, region/zone, workload và phiên bản để phân tích đúng phạm vi. Tránh tạo cardinality quá cao bằng cách đưa user ID, request ID hoặc dữ liệu cá nhân vào label metric; những thuộc tính chi tiết phù hợp hơn với log hoặc trace.

### 8.1. Dashboard theo thứ tự từ trải nghiệm đến nguyên nhân

Một dashboard vận hành hữu ích có thể sắp xếp:

1. SLI/SLO hiện tại và error budget còn lại.
2. Error rate, latency distribution và throughput theo endpoint/hành trình.
3. Phạm vi ảnh hưởng theo region, zone, tenant hoặc phiên bản.
4. Metric dependency như database, queue, cache và external API.
5. CPU, memory, storage, network và trạng thái VM/container/serverless.
6. Deployment, config change và incident annotation theo timeline.

Cách sắp xếp này giúp người trực nhận ra tác động trước, sau đó đi xuống các thành phần có khả năng gây ra sự cố.

## 9. Dùng metrics, logs và traces để điều tra

Ba loại telemetry bổ trợ nhau:

- **Metrics:** chuỗi số liệu theo thời gian, phù hợp phát hiện xu hướng, tính SLI và kích hoạt alert.
- **Logs:** sự kiện chi tiết có timestamp và ngữ cảnh, phù hợp tìm lỗi cụ thể, request hoặc thay đổi.
- **Traces:** hành trình của một request qua nhiều service, phù hợp xác định thành phần nào tạo ra latency hoặc lỗi.

Khi alert SLO kích hoạt, hãy dùng metric để xác định phạm vi và thời điểm; log để tìm sự kiện lỗi; trace để theo request qua API, database, queue và dependency. Cần có correlation ID hoặc trace ID để liên kết dữ liệu mà không đưa các ID duy nhất thành label metric có cardinality cao.

### 9.1. Ví dụ điều tra latency tăng

Giả sử SLI latency của API giảm từ 99,2% xuống 94% request dưới 300 ms. Dashboard cho thấy chỉ endpoint tạo đơn bị ảnh hưởng ở một region. Trace cho thấy phần lớn thời gian nằm ở thao tác ghi database. Database metric thể hiện write latency và queue depth tăng; cùng thời điểm, storage volume có IOPS gần giới hạn.

Chuỗi dữ liệu giúp nhóm xác định vấn đề nằm ở đường ghi dữ liệu và storage, thay vì mở rộng CPU cho toàn bộ API fleet. Hướng xử lý có thể là giảm tải ghi, điều chỉnh cấu hình database/storage, tăng capacity phù hợp hoặc rollback thay đổi gần đây. Sau khi xử lý, xác minh SLI phục hồi và burn rate giảm.

### 9.2. Synthetic monitoring và low traffic

Một dịch vụ ít request có thể không có đủ mẫu để tính SLI theo request trong từng cửa sổ ngắn. Synthetic monitoring gửi giao dịch kiểm tra định kỳ từ góc nhìn bên ngoài, ví dụ đăng nhập thử, truy vấn API hoặc tải một trang quan trọng.

Synthetic check hữu ích để phát hiện lỗi khi traffic thấp và kiểm tra đường đi từ DNS, TLS, gateway đến ứng dụng. Tuy nhiên, synthetic traffic không đại diện hoàn toàn cho hành vi người dùng thật; cần phân biệt kết quả synthetic với request thực và tránh để test account hoặc dữ liệu kiểm tra ảnh hưởng nghiệp vụ.

Khi traffic thấp, có thể:

- Dùng cửa sổ đo dài hơn để tăng số mẫu.
- Kết hợp synthetic check với SLI từ traffic thật.
- Đặt điều kiện sample count tối thiểu trước khi tính burn rate.
- Cảnh báo riêng khi không có telemetry hoặc không đủ mẫu.
- Không diễn giải “không có request lỗi” thành availability hoàn hảo nếu dịch vụ không có request nào.

## 10. Ví dụ thiết kế SLI/SLO cho các mô hình compute

### 10.1. Dịch vụ API chạy trên VM hoặc container

| Thành phần | Ví dụ định nghĩa |
|---|---|
| SLI availability | Request hợp lệ trả kết quả thành công trong timeout / tổng request hợp lệ |
| SLO availability | 99,9% trong cửa sổ trượt 30 ngày |
| SLI latency | Request hoàn tất trong 300 ms / tổng request hợp lệ |
| SLO latency | 99% trong cửa sổ trượt 30 ngày |
| Alert | Burn rate availability hoặc latency vượt ngưỡng multi-window; page khi tác động đủ lớn |
| Diagnostic metrics | CPU throttling, memory pressure, pod restart, VM network, database latency |

Với container, pod `Ready` là một tín hiệu thành phần, không phải SLI cuối cùng. Với VM, instance `running` cũng không chứng minh API hoạt động. SLI nên đo request qua endpoint thực tế.

### 10.2. Worker xử lý queue

| Thành phần | Ví dụ định nghĩa |
|---|---|
| SLI success | Job hoàn tất thành công / job hợp lệ được nhận |
| SLI timeliness | Job hoàn tất trong 5 phút / job hợp lệ |
| SLO | 99,5% job hoàn tất trong 5 phút trong 30 ngày |
| Alert | Tỷ lệ job trễ tăng hoặc tuổi message lâu nhất vượt ngưỡng; page khi backlog đe dọa cam kết nghiệp vụ |
| Diagnostic metrics | Queue depth, oldest message age, worker concurrency, retry, dead-letter count, CPU/RAM |

Queue depth tăng đơn lẻ chưa chắc là sự cố nếu worker vẫn xử lý nhanh hơn tốc độ message đến. Tuổi message và tỷ lệ hoàn tất đúng hạn thường phản ánh tác động người dùng tốt hơn.

### 10.3. Serverless function

| Thành phần | Ví dụ định nghĩa |
|---|---|
| SLI success | Invocation hoàn tất theo hợp đồng / invocation hợp lệ |
| SLI latency | Invocation hoàn tất trong ngưỡng / invocation hợp lệ |
| Alert | Error rate, throttling hoặc duration làm SLO burn nhanh |
| Diagnostic metrics | Cold start, concurrency, timeout, memory, retry và downstream latency |

Invocation có thể được retry tự động. Cần phân biệt số lần thử với số công việc logic duy nhất; nếu không, retry có thể làm tăng số lần thành công được đếm trong khi người dùng vẫn chịu độ trễ hoặc xử lý trùng.

### 10.4. Nền tảng VM hoặc compute nội bộ

Nếu tổ chức cung cấp compute platform cho các nhóm nội bộ, người dùng của nền tảng có thể là đội ứng dụng. SLI có thể đo tỷ lệ yêu cầu tạo VM thành công trong thời hạn, thời gian cấp phát p95, tỷ lệ node/container sẵn sàng hoặc tỷ lệ volume attach thành công.

Ví dụ SLO:

- 99% yêu cầu tạo VM hợp lệ được cấp phát trong vòng 5 phút trong 30 ngày.
- 99,9% yêu cầu attach volume hợp lệ hoàn tất trong thời hạn xác định.
- 99% node pool scale-out có node Ready trong 8 phút.

Đây là SLO của nền tảng compute, khác với SLO của ứng dụng chạy trên VM. Một ứng dụng có thể hoạt động tốt dù một yêu cầu tạo VM mới chậm; ngược lại, nền tảng có thể cấp VM đúng hạn nhưng ứng dụng vẫn lỗi do cấu hình hoặc dependency.

## 11. Quy trình phản ứng khi SLO alert kích hoạt

Một alert cần dẫn đến quy trình rõ ràng thay vì chỉ gửi thông báo. Runbook có thể theo trình tự:

1. **Xác nhận tác động:** xem SLI, error budget burn, endpoint, region, tenant và thời điểm bắt đầu.
2. **Xác định phạm vi:** kiểm tra sự cố ảnh hưởng toàn dịch vụ hay một phần traffic, một phiên bản hoặc một miền lỗi.
3. **Kiểm tra thay đổi gần đây:** deployment, image, config, scaling policy, network rule hoặc database migration.
4. **Đi xuống dependency:** dùng trace và metric để kiểm tra database, queue, cache, storage và external API.
5. **Kiểm tra compute:** CPU, memory, throttling, OOM, pod pending/restart, VM health, disk I/O và network.
6. **Chọn hành động giảm tác động:** rollback, scale-out, failover, disable feature, giảm tải hoặc chuyển traffic theo runbook.
7. **Xác minh phục hồi:** SLI cải thiện, burn rate giảm, backlog được xử lý và health check ổn định.
8. **Ghi nhận hậu kiểm:** timeline, nguyên nhân, tác động, thời gian phát hiện/phục hồi và hành động phòng ngừa.

Không nên scale-out một cách máy móc nếu nút thắt là database hoặc quota; tăng số worker có thể làm dependency quá tải hơn. Hành động cần dựa trên bằng chứng và hiểu biết về giới hạn của toàn hệ thống.

### 11.1. Nội dung tối thiểu của runbook

- Tên alert, SLI/SLO liên quan và điều kiện kích hoạt.
- Mức độ nghiêm trọng, owner và người trực.
- Dashboard có metric SLI, burn rate và dependency.
- Truy vấn log/trace hoặc liên kết đến công cụ điều tra.
- Các bước xác nhận và hành động an toàn ban đầu.
- Điều kiện rollback/failover/scale và giới hạn cần lưu ý.
- Kênh thông báo, escalation và cách cập nhật incident.
- Điều kiện đóng alert và xác nhận phục hồi.

## 12. Những nhầm lẫn thường gặp

**CPU thấp nghĩa là dịch vụ khỏe.** Dịch vụ có thể lỗi vì database, DNS, network, storage hoặc dependency dù CPU còn dư.

**CPU cao luôn cần page.** CPU cao có thể là trạng thái bình thường khi tải lớn. Cần page khi nó gây hoặc sắp gây tác động người dùng, hoặc có nguy cơ cạn capacity rõ ràng.

**SLO 99,9% tương đương luôn có 43,2 phút downtime.** Con số này chỉ là phép quy đổi cho SLO availability theo thời gian trong cửa sổ 30 ngày. SLO theo request phụ thuộc phân bố lưu lượng.

**p99 của từng instance có thể lấy trung bình để thành p99 toàn dịch vụ.** Percentile không cộng gộp tuyến tính. Hãy tổng hợp histogram hoặc dữ liệu request phù hợp.

**Không có request lỗi nghĩa là SLI bằng 100%.** Khi không có mẫu hoặc telemetry mất, SLI có thể không xác định. Cần phân biệt zero traffic, no data và success.

**Mọi lỗi 4xx đều phải loại khỏi availability.** Một số 4xx là lỗi đầu vào của client, nhưng 429 hoặc lỗi do policy/service làm người dùng không thể hoàn tất có thể là bad event. Phải định nghĩa theo hợp đồng và tác động.

**SLO càng cao càng tốt.** Mục tiêu quá cao có thể làm tăng chi phí và giảm tốc độ phát hành mà không mang lại giá trị tương xứng. Chọn mục tiêu theo nhu cầu và khả năng thực tế.

**Alert càng nhiều càng an toàn.** Alert nhiễu khiến người trực bỏ qua tín hiệu quan trọng. Chỉ page khi cần hành động ngay; các tín hiệu chẩn đoán có thể ở dashboard hoặc ticket.

## 13. Checklist xây dựng SLI/SLO và alert

### Định nghĩa SLI/SLO

- [ ] Đã xác định hành trình người dùng và chức năng quan trọng.
- [ ] Mỗi SLI có population, good/bad event, điểm đo, cửa sổ và exclusion rõ ràng.
- [ ] Availability, latency, freshness hoặc job completion được chọn theo loại dịch vụ.
- [ ] SLO có mục tiêu và cửa sổ phù hợp với nhu cầu người dùng.
- [ ] SLI đo từ ranh giới gần người dùng và không bỏ sót lỗi gateway/dependency.
- [ ] Có xử lý low traffic, missing telemetry và synthetic monitoring.

### Error budget và cảnh báo

- [ ] Error budget được tính từ cùng định nghĩa SLI với SLO.
- [ ] Có dashboard theo dõi budget còn lại và burn rate.
- [ ] Alert dùng nhiều cửa sổ hoặc cơ chế chống nhiễu phù hợp.
- [ ] Page gắn với tác động người dùng hoặc nguy cơ nghiêm trọng sắp xảy ra.
- [ ] Mỗi alert có owner, severity, dashboard và runbook.
- [ ] Alert routing và escalation đã được thử nghiệm.

### Vận hành và cải tiến

- [ ] Metrics, logs và traces có thể liên kết bằng service/resource/trace context.
- [ ] Dashboard thể hiện trải nghiệm trước, tài nguyên và dependency sau.
- [ ] Runbook có bước xác nhận, giảm tác động, phục hồi và hậu kiểm.
- [ ] Error budget được dùng trong quyết định phát hành và ưu tiên reliability.
- [ ] SLI/SLO được rà soát khi sản phẩm, tải hoặc hành trình người dùng thay đổi.

## Kết luận

SLI đo chất lượng dịch vụ từ góc nhìn người dùng; SLO đặt mục tiêu định lượng cho SLI trong một cửa sổ; error budget biểu diễn phần lỗi được phép. Cảnh báo nên tập trung vào tác động và tốc độ tiêu thụ budget, kết hợp nhiều cửa sổ để phát hiện sự cố mà hạn chế nhiễu. Metric compute như CPU, RAM, storage và network vẫn rất cần thiết, nhưng chủ yếu giúp giải thích nguyên nhân sau khi SLI cho thấy vấn đề. Khi định nghĩa population và good/bad event rõ ràng, xây dashboard theo hành trình người dùng và gắn alert với runbook có thể hành động, đội vận hành sẽ ưu tiên đúng sự cố và cải thiện độ tin cậy có cơ sở.
