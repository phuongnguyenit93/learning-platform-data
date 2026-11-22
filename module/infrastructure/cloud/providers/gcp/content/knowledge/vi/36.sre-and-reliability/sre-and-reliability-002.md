# Xác định SLI và SLO bằng Cloud Monitoring

Một dịch vụ có thể chạy ổn định theo góc nhìn hạ tầng nhưng vẫn gây khó chịu cho người dùng: trang tải chậm, thao tác thanh toán thất bại hoặc dữ liệu trả về đã cũ. Để quản lý độ tin cậy theo trải nghiệm thực tế, đội vận hành cần xác định điều gì được xem là một lần phục vụ tốt, đo lường điều đó bằng telemetry và đặt mục tiêu có thể kiểm chứng.

Trong Site Reliability Engineering (SRE), **Service Level Indicator (SLI)** là chỉ số đo chất lượng dịch vụ, **Service Level Objective (SLO)** là mục tiêu đặt lên SLI trong một khoảng thời gian, còn **Service Level Agreement (SLA)** là cam kết với khách hàng thường gắn với hậu quả hoặc điều khoản khi không đạt mức dịch vụ. Cloud Monitoring cung cấp Service Monitoring và SLO API để định nghĩa SLI, theo dõi mức đáp ứng SLO, tính error budget và cảnh báo khi ngân sách lỗi bị tiêu thụ quá nhanh.

Trong module CLOUD_PROVIDERS_GCP, SLI/SLO kết nối các dịch vụ như Cloud Run, GKE, Compute Engine, Cloud Load Balancing và cơ sở dữ liệu với hoạt động vận hành. Một hệ thống SLO tốt cần phản ánh điều người dùng quan tâm, có metric đáng tin cậy, phạm vi đo rõ ràng và gắn với quyết định xử lý sự cố cũng như phát hành phần mềm.

Sau bài học này, bạn có thể:

- Phân biệt SLI, SLO, SLA và error budget.
- Chọn SLI về availability, latency và chất lượng nghiệp vụ từ góc nhìn người dùng.
- Phân biệt request-based SLI với windows-based SLI.
- Kiểm tra metric type, metric kind, label và cardinality trước khi dùng metric trong SLO.
- Tạo service và SLO trong Cloud Monitoring Console hoặc qua Cloud Monitoring API.
- Tính error budget, theo dõi compliance và cấu hình cảnh báo burn rate.
- Dùng SLO để ưu tiên độ tin cậy, thay đổi và cải tiến dịch vụ.

## 1. SLI, SLO, SLA và error budget

### Service Level Indicator (SLI)

SLI là phép đo định lượng cho một khía cạnh chất lượng dịch vụ trong một khoảng thời gian. SLI nên là đại diện tốt cho trải nghiệm của người dùng, thay vì chỉ phản ánh trạng thái của máy chủ.

Ví dụ:

- Availability: tỷ lệ request hợp lệ được xử lý thành công.
- Latency: tỷ lệ request hoàn tất dưới một ngưỡng thời gian.
- Freshness: tỷ lệ dữ liệu được cập nhật trong thời gian cho phép.
- Correctness: tỷ lệ kết quả nghiệp vụ đúng theo tiêu chí đã xác định.
- Throughput: tỷ lệ công việc được hoàn tất đúng hạn khi hệ thống có đủ tải.

Một SLI thường được biểu diễn dưới dạng tỷ lệ:

\[
SLI = \frac{\text{số đơn vị phục vụ tốt}}{\text{tổng số đơn vị đủ điều kiện đo}}
\]

Ví dụ, trong 100.000 request đủ điều kiện, có 99.850 request trả kết quả thành công:

\[
SLI_{availability} = \frac{99.850}{100.000} = 99,85\%
\]

SLI có thể được xem ở nhiều cửa sổ thời gian tùy quyết định cần đưa ra: một giờ cho cảnh báo vận hành, vài tuần cho quyết định chiến thuật và vài tháng cho kế hoạch dài hạn. Google Cloud khuyến nghị dùng 28 ngày làm điểm bắt đầu để đo SLI vì đây là khoảng cân bằng giữa nhu cầu chiến thuật và chiến lược.

Định nghĩa "tốt" phải phù hợp với hợp đồng dịch vụ. Với API đọc dữ liệu, HTTP 200 có thể là kết quả tốt; với API tạo đơn hàng, trả HTTP 200 nhưng đơn hàng không được ghi thành công vẫn là thất bại nghiệp vụ. Hãy chọn điểm đo đủ gần với trải nghiệm người dùng để phát hiện đúng vấn đề.

### Service Level Objective (SLO)

SLO là mục tiêu hiệu năng đặt lên một SLI trong một **compliance period** (khoảng thời gian đánh giá). Ví dụ:

> Trong mỗi khoảng 30 ngày trượt, ít nhất 99,9% request đọc hồ sơ phải thành công và ít nhất 99% request phải có latency dưới 300 ms.

Đây là hai SLO riêng vì availability và latency đo hai khía cạnh khác nhau. Cloud Monitoring mô hình hóa một SLO bằng SLI, goal và period. Một service có thể có nhiều SLO để đo các khía cạnh hoặc nhóm người dùng khác nhau.

### Service Level Agreement (SLA)

SLA là cam kết dịch vụ được thỏa thuận với khách hàng hoặc đối tác. SLA có thể quy định tỷ lệ uptime, phạm vi loại trừ, cách tính, thời gian thông báo và khoản tín dụng dịch vụ nếu không đạt cam kết. SLO thường là mục tiêu vận hành nội bộ, được đặt đủ chặt để đội kỹ thuật phát hiện rủi ro trước khi vi phạm SLA.

Không nên dùng SLO và SLA như hai từ đồng nghĩa. SLO là công cụ điều hành kỹ thuật; SLA là cam kết có điều kiện và hậu quả theo hợp đồng.

### Error budget

Error budget là phần chất lượng dịch vụ được phép không đạt mà SLO vẫn được xem là đáp ứng. Nếu mục tiêu là 99,9%, phần ngân sách lỗi là:

\[
Error\ budget = 1 - 0,999 = 0,001 = 0,1\%
\]

Với SLI theo request, nếu compliance period có 1.000.000 request đủ điều kiện thì ngân sách tương đương 1.000 request không tốt. Với SLI theo thời gian, SLO 99,9% trong 30 ngày tương đương khoảng 43 phút 12 giây không đạt nếu cách đo là tỷ lệ thời gian phục vụ tốt.

Error budget tạo ra cơ sở để cân bằng tốc độ phát hành và độ tin cậy. Khi ngân sách còn nhiều, nhóm có thể tiếp tục thử nghiệm và phát hành trong giới hạn rủi ro đã thống nhất. Khi ngân sách bị tiêu thụ nhanh hoặc đã cạn, nhóm có thể ưu tiên khắc phục lỗi, giảm thay đổi rủi ro và cải thiện năng lực vận hành.

## 2. Thiết kế SLI có ý nghĩa với người dùng

### Bắt đầu từ lời hứa của dịch vụ

Hãy viết điều dịch vụ cam kết với người dùng bằng ngôn ngữ nghiệp vụ trước khi tìm metric:

| Lời hứa với người dùng | SLI có thể đo |
|---|---|
| Người dùng mở trang hồ sơ và nhận được nội dung | Tỷ lệ request hồ sơ thành công |
| Người dùng xem được trang trong thời gian chấp nhận được | Tỷ lệ request có latency dưới 300 ms |
| Đơn hàng được tạo và xác nhận | Tỷ lệ workflow tạo đơn hoàn tất thành công |
| Báo cáo hiển thị dữ liệu cập nhật | Tỷ lệ lần đọc có tuổi dữ liệu nhỏ hơn 10 phút |
| Batch job bắt đầu đúng lịch | Tỷ lệ lần chạy bắt đầu trong vòng 1 phút so với lịch |

Không chọn metric chỉ vì metric đó có sẵn trên dashboard. CPU, memory, số pod hoặc số instance hữu ích để chẩn đoán nguyên nhân, nhưng chúng không trực tiếp cho biết người dùng có hoàn thành công việc hay không. Có thể dùng các metric hạ tầng làm tín hiệu phụ hoặc SLI cho một dịch vụ hạ tầng cụ thể nếu chúng gắn với cam kết của dịch vụ đó.

### Bốn nhóm tín hiệu thường gặp

- **Availability:** request hoặc thao tác được phục vụ thành công.
- **Latency:** request được phục vụ trong giới hạn thời gian.
- **Traffic:** lượng công việc người dùng gửi đến, giúp diễn giải các SLI khác.
- **Errors:** số lỗi hoặc tỷ lệ lỗi; cần định nghĩa lỗi theo tác động tới người dùng.

Traffic và errors thường giúp giải thích thay đổi availability/latency. Chúng không nhất thiết là SLO độc lập. Một hệ thống có thể có nhiều SLI nếu người dùng có các loại công việc khác nhau, ví dụ đọc phải nhanh trong khi ghi phải chính xác.

### Xác định mẫu số và điều kiện loại trừ

Mẫu số phải gồm đúng các đơn vị mà dịch vụ có trách nhiệm xử lý. Hãy thống nhất:

- Request nội bộ, health check, synthetic probe và retry có được tính hay không.
- Request bị người dùng gửi sai dữ liệu có được xem là lỗi dịch vụ không.
- Timeout ở client, gateway hoặc backend được tính ở điểm đo nào.
- Request bị hủy hoặc chưa hoàn tất được xử lý ra sao.
- Các endpoint, tenant, region hoặc loại giao dịch nào thuộc phạm vi SLO.

Ví dụ, lỗi HTTP 4xx do người dùng gửi dữ liệu không hợp lệ thường không phải lỗi availability của backend. Tuy nhiên, nếu dịch vụ trả 4xx sai do bug hoặc do quyền truy cập bị cấu hình nhầm thì trải nghiệm người dùng vẫn bị ảnh hưởng. Cần định nghĩa tiêu chí "good" dựa trên hợp đồng của endpoint và kiểm thử bằng các tình huống thực tế.

### Một SLI nên đo một khía cạnh

Không gộp availability và latency vào cùng một tỷ lệ nếu nhóm cần hiểu rõ nguyên nhân. Một request có thể thành công nhưng quá chậm; request khác có thể thất bại rất nhanh. Hai kết quả này ảnh hưởng người dùng khác nhau và cần hai SLI riêng.

Nếu một sản phẩm có nhiều hành trình quan trọng, hãy tách SLI theo hành trình hoặc nhóm request. Ví dụ, API tìm kiếm có thể cần latency nghiêm ngặt hơn API xuất báo cáo. Việc phân nhóm giúp mục tiêu phù hợp với mức kỳ vọng và tránh một endpoint ít quan trọng che lấp vấn đề của endpoint quan trọng.

## 3. Chọn loại SLI trong Cloud Monitoring

Cloud Monitoring hỗ trợ ba cách mô hình hóa SLI trong SLO API:

| Loại SLI | Cách tính | Khi phù hợp |
|---|---|---|
| Basic SLI | Dựa trên metric và định nghĩa có sẵn cho một số service type | Khi service type đã được Cloud Monitoring nhận diện và có availability/latency SLI dựng sẵn |
| Request-based SLI | Tỷ lệ request tốt trên tổng request trong compliance period | Khi mỗi request là một đơn vị phục vụ và có metric đếm request |
| Windows-based SLI | Tỷ lệ cửa sổ thời gian đạt tiêu chí tốt trên tổng số cửa sổ | Khi chất lượng được đánh giá theo trạng thái từng khoảng thời gian, ví dụ job định kỳ hoặc độ mới dữ liệu |

### Basic SLI

Basic SLI dùng metric có sẵn cho những service type được Cloud Monitoring hỗ trợ. Theo tài liệu Service Monitoring, các loại dịch vụ có metric SLI dựng sẵn bao gồm Cloud Service Mesh, Istio trên GKE và App Engine. Với các service type khác, cần xác minh lựa chọn SLI trong giao diện; nhiều trường hợp phải dùng custom SLI.

### Request-based SLI

Request-based SLI đo tỷ lệ request tốt trên tổng request:

\[
SLI_{request} = \frac{Good\ requests}{Total\ eligible\ requests}
\]

Ví dụ, request tốt là request có response code thuộc nhóm được chấp nhận và latency nhỏ hơn 300 ms. Có thể tạo một SLI availability và một SLI latency riêng bằng cách dùng các điều kiện metric khác nhau.

Metric dùng cho request-based SLI phải có metric kind là `DELTA` hoặc `CUMULATIVE`. Metric `GAUGE` không dùng được cho request-based SLI. Nếu metric lưu histogram hoặc distribution, có thể dùng distribution cut để đếm số quan sát nằm trong ngưỡng tốt.

### Windows-based SLI

Windows-based SLI xem một khoảng thời gian là tốt hoặc xấu theo tiêu chí đã đặt. Ví dụ, một cửa sổ 5 phút được xem là tốt nếu tỷ lệ request thành công trong cửa sổ đạt ít nhất 99%. SLI cuối cùng là số cửa sổ tốt chia cho tổng cửa sổ đủ điều kiện.

Loại này phù hợp với dịch vụ xử lý theo chu kỳ, tác vụ batch, freshness hoặc hệ thống mà người dùng quan tâm đến việc một khoảng thời gian có duy trì chất lượng yêu cầu hay không. Cần chọn window period phù hợp với chu kỳ vận hành và độ phân giải metric; Cloud Monitoring yêu cầu window period tối thiểu 60 giây và là một phần nguyên của ngày.

## 4. Chuẩn bị metric cho SLI

### Nguồn metric

Cloud Monitoring có thể dùng:

- Metric nền tảng và metric dịch vụ Google Cloud.
- Metric ứng dụng do code hoặc OpenTelemetry xuất ra.
- Metric Prometheus được thu thập qua Google Cloud Managed Service for Prometheus.
- Log-based metric được tạo từ Cloud Logging khi log có cấu trúc và phản ánh sự kiện phù hợp.
- Metric tùy chỉnh được gửi qua Cloud Monitoring API.

Ví dụ metric:

| Dịch vụ / nguồn | Metric hoặc tín hiệu | SLI gợi ý |
|---|---|---|
| External HTTPS Load Balancer | `loadbalancing.googleapis.com/https/request_count` | Tỷ lệ request thành công |
| Ứng dụng HTTP | Tổng request và request thành công do ứng dụng xuất | Availability |
| Ứng dụng có histogram latency | Distribution của thời gian xử lý | Tỷ lệ request dưới ngưỡng latency |
| GKE với Prometheus | Counter request theo route/status | Availability hoặc latency |
| Batch workflow | Metric thời điểm bắt đầu/kết thúc hoặc trạng thái job | Tỷ lệ job hoàn tất đúng hạn |
| Pipeline dữ liệu | Tuổi dữ liệu hoặc thời điểm cập nhật cuối | Freshness |

Tên metric, monitored resource và label thay đổi theo dịch vụ. Hãy kiểm tra Metrics Explorer và Metrics list của đúng dịch vụ trước khi tạo SLI.

### Kiểm tra metric kind và cardinality

Trong Metrics Explorer, chọn metric và xem thông tin metric kind, value type, monitored resource và labels. Với request-based SLI, xác nhận metric kind là `DELTA` hoặc `CUMULATIVE`. Tránh metric có label chứa timestamp, user ID hoặc request ID vì chúng tạo ra cardinality rất cao, tăng chi phí và làm truy vấn khó quản lý.

Một metric tốt cho SLI cần:

- Có đủ coverage cho request hoặc workflow thuộc phạm vi đo.
- Có định nghĩa ổn định qua các lần deploy.
- Có nhãn để tách good và total theo tiêu chí rõ ràng.
- Có thể tổng hợp theo service mà không làm mất ngữ nghĩa.
- Không đếm lặp request do retry hoặc fan-out ngoài ý muốn.
- Có dữ liệu liên tục đủ để phát hiện thiếu telemetry.

Thiếu metric không đồng nghĩa dịch vụ hoạt động tốt. Cần theo dõi độ đầy đủ của telemetry và xử lý trường hợp không có dữ liệu như một vấn đề quan sát riêng.

## 5. Thực hành: tạo SLI availability cho HTTPS Load Balancer

Ví dụ này dùng metric HTTPS Load Balancer có sẵn để đo tỷ lệ request có response code class `200` trên tổng request. Đây là mẫu minh họa theo tài liệu Google Cloud. Với API thực tế, hãy điều chỉnh điều kiện good theo hợp đồng của ứng dụng; nếu 3xx là kết quả hợp lệ hoặc cần loại trừ một nhóm lỗi nghiệp vụ, hãy thay filter cho phù hợp.

### Bước 1: Kiểm tra metric trong Metrics Explorer

1. Mở Google Cloud Console và chọn project chứa HTTPS Load Balancer.
2. Vào **Monitoring → Metrics Explorer**.
3. Chọn monitored resource type `http_lb_rule`.
4. Chọn metric `loadbalancing.googleapis.com/https/request_count`.
5. Kiểm tra metric kind; request count phải phù hợp với request-based SLI.
6. Thêm filter `response_code_class = 200` để chỉ lấy request tốt theo ví dụ.
7. Dùng phép tổng hợp `sum` để gộp các time series thuộc phạm vi dịch vụ.
8. Mở chế độ JSON của biểu đồ để xem metric filter và cách căn chỉnh/tổng hợp.

Filter tổng request:

~~~text
metric.type="loadbalancing.googleapis.com/https/request_count"
resource.type="http_lb_rule"
~~~

Filter request tốt:

~~~text
metric.type="loadbalancing.googleapis.com/https/request_count"
resource.type="http_lb_rule"
metric.label."response_code_class"="200"
~~~

Trong môi trường có nhiều load balancer, thêm label filter để giới hạn đúng forwarding rule, project, backend hoặc phạm vi dịch vụ. Nếu không giới hạn, SLI có thể vô tình gộp traffic của nhiều ứng dụng.

### Bước 2: Xác định service trong Cloud Monitoring

Cloud Monitoring gắn SLO với một service. Trong Console:

1. Mở **Monitoring → Services**.
2. Chọn service đã được tự động phát hiện, hoặc nhấn **Define service** để tạo custom service.
3. Đặt tên và mô tả service theo đơn vị mà người dùng nhận biết, ví dụ `customer-api-prod`.
4. Chọn resource hoặc tiêu chí nhận diện phù hợp với các metric của service.
5. Lưu service và mở trang chi tiết.

Với Cloud Run, GKE hoặc ứng dụng tự triển khai, không nên giả định rằng availability/latency SLI dựng sẵn luôn có sẵn. Nếu service type không có metric chuẩn, hãy định nghĩa custom service và custom SLI từ metric của Load Balancer, ứng dụng hoặc Prometheus.

### Bước 3: Tạo SLO trên Console

1. Tại trang chi tiết service, chọn **Create SLO**.
2. Chọn SLI availability hoặc custom metric theo nguồn metric.
3. Chọn request-based evaluation nếu đang đếm good request / total request.
4. Xác nhận metric và filter đúng phạm vi service.
5. Đặt goal, ví dụ `0.99` tương đương 99%.
6. Chọn compliance period, ví dụ rolling 30 days hoặc calendar week tùy nhu cầu báo cáo.
7. Xem lại định nghĩa và lưu SLO.

Quyền tạo SLO thường cần vai trò Monitoring Editor (`roles/monitoring.editor`) hoặc vai trò tùy chỉnh có đủ quyền Cloud Monitoring tương ứng.

## 6. Tạo SLO bằng Cloud Monitoring API

Cloud Monitoring API v3 cho phép tạo SLO dưới một service đã tồn tại. Request-based SLI cho ví dụ Load Balancer có thể được biểu diễn bằng `goodTotalRatio`:

~~~json
{
  "displayName": "99% successful HTTPS requests per calendar week",
  "serviceLevelIndicator": {
    "requestBased": {
      "goodTotalRatio": {
        "totalServiceFilter": "metric.type=\"loadbalancing.googleapis.com/https/request_count\" resource.type=\"http_lb_rule\"",
        "goodServiceFilter": "metric.type=\"loadbalancing.googleapis.com/https/request_count\" resource.type=\"http_lb_rule\" metric.label.\"response_code_class\"=\"200\""
      }
    }
  },
  "goal": 0.99,
  "calendarPeriod": "WEEK"
}
~~~

Ví dụ trên minh họa cấu trúc API. Trước khi sử dụng, cần bổ sung filter để chỉ đo load balancer của service đang xét và xác nhận nhãn response code của metric trong project. `goal` là số thập phân lớn hơn 0 và không vượt quá 0.9999; `0.99` nghĩa là 99%. `calendarPeriod` đánh giá từ đầu kỳ lịch; nếu muốn đánh giá theo khoảng trượt, dùng `rollingPeriod`.

Tạo SLO bằng REST:

~~~bash
export PROJECT_ID="my-production-project"
export SERVICE_ID="customer-api-prod"

curl -X POST \
  "https://monitoring.googleapis.com/v3/projects/${PROJECT_ID}/services/${SERVICE_ID}/serviceLevelObjectives" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data-binary @slo.json
~~~

Trong ví dụ này, lưu JSON ở trên thành `slo.json`. Service phải tồn tại trước khi gọi endpoint tạo SLO. Có thể dùng API GET hoặc danh sách SLO để xác nhận resource name và cấu hình đã lưu.

### Rolling period và calendar period

Cloud Monitoring hỗ trợ hai cách xác định compliance period:

- **Rolling period:** đánh giá trên khoảng thời gian trượt tính ngược từ thời điểm hiện tại, ví dụ 7 ngày hoặc 30 ngày.
- **Calendar period:** đánh giá từ đầu ngày, tuần, hai tuần hoặc tháng theo lịch.

Với API, `rollingPeriod` có dạng duration và phải là số ngày nguyên, tối đa 30 ngày. `calendarPeriod` hỗ trợ `DAY`, `WEEK`, `FORTNIGHT` và `MONTH`. Chọn rolling period khi muốn cửa sổ luôn cập nhật; chọn calendar period khi báo cáo và trách nhiệm vận hành được tổng kết theo chu kỳ lịch.

## 7. Tính và sử dụng error budget

### Error budget theo request

Giả sử API có SLO availability 99,9% trong 30 ngày. Trong kỳ có 2.000.000 request đủ điều kiện:

\[
Error\ budget = (1 - 0,999) \times 2.000.000 = 2.000
\]

Như vậy, tối đa 2.000 request không tốt vẫn nằm trong mục tiêu của kỳ. Nếu đã có 1.200 request lỗi, phần budget còn lại là 800 request.

### Error budget theo thời gian

Với mục tiêu 99,9% trong 30 ngày:

\[
30 \times 24 \times 60 \times 0,001 = 43,2\text{ phút}
\]

Đây là phép quy đổi cho SLI đo tỷ lệ thời gian tốt. Với request-based SLI, cần tính theo số request đủ điều kiện thay vì quy đổi trực tiếp thành downtime.

### Dùng budget trong quyết định phát hành

| Trạng thái budget | Hành động gợi ý |
|---|---|
| Còn nhiều và burn rate ổn định | Tiếp tục kế hoạch phát hành, vẫn theo dõi thay đổi rủi ro cao |
| Tiêu thụ nhanh hơn bình thường | Điều tra thay đổi gần đây, tăng quan sát, cân nhắc tạm dừng rollout |
| Gần cạn | Ưu tiên sửa lỗi và giảm rủi ro; xem xét hoãn tính năng không thiết yếu |
| Đã cạn | Thực hiện chính sách reliability của nhóm, tập trung khôi phục SLO trước khi tiếp tục thay đổi rủi ro |

Error budget không phải mục tiêu để cố tình sử dụng hết. Nó là cách lượng hóa mức rủi ro mà nhóm và khách hàng có thể chấp nhận trong một kỳ.

## 8. Cảnh báo theo SLO và burn rate

Một cảnh báo CPU cao chỉ cho biết tài nguyên đang chịu tải; cảnh báo burn rate cho biết dịch vụ đang tiêu thụ ngân sách lỗi nhanh đến mức nào. Cloud Monitoring cho phép tạo alerting policy gắn với SLO để thông báo khi burn rate vượt ngưỡng trong một khoảng thời gian.

Burn rate là tốc độ tiêu thụ error budget đã được chuẩn hóa. Burn rate bằng 1 có nghĩa là nếu tốc độ lỗi hiện tại tiếp tục trong toàn bộ compliance period thì ngân sách sẽ vừa bị tiêu thụ hết. Burn rate lớn hơn 1 cho biết tốc độ tiêu thụ nhanh hơn mức cho phép của SLO.

### Tạo SLO alert trong Console

1. Mở **Monitoring → Services** và chọn service.
2. Trong phần trạng thái hiện tại, tìm SLO cần giám sát.
3. Chọn hành động tạo SLO alert.
4. Chọn burn-rate threshold và thời lượng vi phạm phù hợp với độ khẩn cấp.
5. Chọn notification channel như email, SMS hoặc kênh tích hợp được tổ chức sử dụng.
6. Viết documentation cho alert: SLO nào bị ảnh hưởng, service nào, dashboard/runbook nào cần mở và hành động ban đầu.

Nên có cảnh báo cho sự cố tiêu thụ budget nhanh và cảnh báo cho xu hướng dài hơn. Cửa sổ ngắn giúp phát hiện sự cố đột ngột; cửa sổ dài giúp nhận ra sự suy giảm kéo dài. Ngưỡng phải dựa trên lưu lượng thực tế, mức độ quan trọng của dịch vụ và khả năng phản ứng của đội vận hành.

### Những điều cần chú ý

- Burn rate được tính dựa trên SLI và compliance/lookback period được chọn trong alert.
- Cảnh báo burn-rate của SLO hiện giới hạn lookback/compliance period tối đa 24 giờ; việc giám sát ngân sách dài hạn có thể dùng SLO compliance dashboard song song.
- Với lưu lượng thấp, một vài lỗi có thể tạo tỷ lệ lỗi cao trong cửa sổ ngắn. Cân nhắc threshold lớn hơn, thời lượng phù hợp hoặc điều kiện tối thiểu về traffic.
- Cần có notification channel hoạt động và runbook rõ ràng; alert không có người nhận hoặc không có hành động tiếp theo sẽ ít giá trị.

## 9. Áp dụng SLI/SLO cho Cloud Run, GKE và dịch vụ dữ liệu

Cloud Monitoring không tự biết định nghĩa "thành công" của mọi ứng dụng. Với mỗi nền tảng, hãy chọn điểm đo và nguồn metric phản ánh đúng hành trình:

| Nền tảng | Nguồn đo gợi ý | Ví dụ SLI |
|---|---|---|
| Cloud Run | Metric request của ứng dụng hoặc Cloud Run, metric HTTPS Load Balancer, OpenTelemetry | Tỷ lệ request thành công; tỷ lệ request dưới 300 ms |
| GKE | Metric Prometheus của ứng dụng, service mesh hoặc load balancer | Tỷ lệ request tốt theo route; tỷ lệ latency dưới ngưỡng |
| Compute Engine | Metric từ ứng dụng, load balancer, uptime check hoặc log-based metric | Tỷ lệ giao dịch thành công; tỷ lệ health probe hợp lệ |
| BigQuery | Metric hoàn tất job, độ trễ truy vấn, metric nghiệp vụ | Tỷ lệ truy vấn quan trọng hoàn tất trong ngưỡng; tỷ lệ pipeline cập nhật dữ liệu đúng hạn |
| Cloud Storage | Metric thao tác, log hoặc synthetic test theo luồng ứng dụng | Tỷ lệ thao tác đọc/ghi thành công của workload |

Đối với GKE-based services và custom services, giao diện SLO thường yêu cầu chọn `Other` để xây dựng custom SLI. Nếu dùng Google Cloud Managed Service for Prometheus, metric Prometheus đã thu thập có thể được chọn làm custom SLI khi đáp ứng điều kiện metric kind và cấu trúc dữ liệu.

Với Cloud Run hoặc GKE, nếu metric request ở tầng nền tảng không thể phân biệt các hành trình nghiệp vụ, hãy xuất metric ứng dụng có nhãn route hoặc operation đã được chuẩn hóa. Không đưa user ID, order ID hoặc request ID vào label của SLI; dùng label có tập giá trị hữu hạn như service, route template, region hoặc status class.

## 10. Những lỗi thiết kế SLI/SLO thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Chọn CPU hoặc memory làm SLI chính cho API | Metric tốt nhưng người dùng vẫn có thể gặp lỗi | Đo request success, latency hoặc workflow outcome |
| Đếm mọi HTTP 4xx là lỗi dịch vụ | Ngân sách lỗi bị tiêu thụ bởi dữ liệu đầu vào không hợp lệ | Phân loại mã lỗi theo hợp đồng API |
| Đo ở backend nhưng bỏ qua lỗi tại gateway | SLI không bao phủ toàn bộ hành trình người dùng | Đo tại load balancer hoặc điểm vào phù hợp, bổ sung metric backend để chẩn đoán |
| Gộp tất cả endpoint vào một SLO | Endpoint quan trọng có thể bị che bởi traffic lớn từ endpoint ít quan trọng | Tách SLI theo hành trình hoặc loại request |
| Đặt SLO 100% | Không có error budget để điều hành rủi ro và mục tiêu khó thực tế | Đặt mục tiêu có cơ sở dữ liệu lịch sử và kỳ vọng người dùng |
| Dùng metric GAUGE cho request-based SLI | SLI không đáp ứng yêu cầu metric kind | Chọn metric DELTA/CUMULATIVE hoặc thiết kế windows-based phù hợp |
| Metric có cardinality quá cao | Tăng chi phí, khó tổng hợp và truy vấn | Dùng label có tập giá trị hữu hạn |
| Thiếu traffic nhưng SLI vẫn được xem là tốt | Không có dữ liệu không chứng minh dịch vụ tốt | Theo dõi độ đầy đủ metric và uptime/synthetic check |
| Chỉ xem SLO theo tháng | Phát hiện sự cố vận hành quá muộn | Kết hợp alert burn rate ngắn hạn với compliance period dài hơn |
| Thay đổi metric mà không quản lý phiên bản SLO | Kết quả giữa các kỳ không còn so sánh được | Ghi lại thay đổi định nghĩa, ngày hiệu lực và lý do |

## 11. Quy trình triển khai SLO trong một nhóm SRE

1. **Xác định service và người dùng:** thống nhất service boundary, hành trình quan trọng và chủ sở hữu.
2. **Viết lời hứa:** mô tả điều người dùng mong đợi bằng câu có thể kiểm chứng.
3. **Định nghĩa SLI:** chọn good event, total event, ngưỡng và điều kiện loại trừ.
4. **Kiểm tra telemetry:** xác nhận metric có coverage, nhãn, metric kind và cardinality phù hợp.
5. **Đo baseline:** quan sát dữ liệu lịch sử để hiểu phân bố, mùa vụ, traffic thấp và các đợt lỗi.
6. **Thống nhất goal và period:** đặt mục tiêu phù hợp với tác động kinh doanh, lịch sử vận hành và SLA nếu có.
7. **Tạo service, SLI, SLO:** cấu hình trong Cloud Monitoring và kiểm tra dashboard.
8. **Tạo alert và runbook:** chọn burn-rate threshold, notification channel và người chịu trách nhiệm.
9. **Đưa budget vào quy trình thay đổi:** thống nhất cách xử lý khi budget giảm nhanh hoặc cạn.
10. **Rà soát định kỳ:** đánh giá SLI có còn đại diện cho trải nghiệm người dùng và metric có còn đáng tin cậy hay không.

Không nên sao chép một mức SLO giống nhau cho mọi dịch vụ. Một dịch vụ nội bộ dùng vài lần mỗi ngày có thể không cần cùng mục tiêu với API thanh toán công khai. Hãy để mức độ quan trọng của hành trình, tác động của lỗi và chi phí cải thiện quyết định mục tiêu.

## 12. Checklist trước khi công bố SLO

- [ ] Service boundary và chủ sở hữu đã được xác định.
- [ ] SLI phản ánh một khía cạnh chất lượng mà người dùng quan tâm.
- [ ] Good event, total event và điều kiện loại trừ đã được mô tả rõ.
- [ ] Metric có coverage, metric kind và label phù hợp.
- [ ] Không dùng label có cardinality quá cao.
- [ ] Có kiểm tra thiếu telemetry và traffic thấp.
- [ ] Goal và compliance period dựa trên dữ liệu lịch sử và nhu cầu dịch vụ.
- [ ] Error budget được tính và nhóm thống nhất cách sử dụng.
- [ ] SLO đã được tạo và xác minh trên Cloud Monitoring.
- [ ] Burn-rate alert có ngưỡng, notification channel và runbook.
- [ ] Có quy trình rà soát khi service, metric hoặc hợp đồng người dùng thay đổi.

## 13. Kết luận

SLI biến trải nghiệm dịch vụ thành phép đo; SLO đặt mục tiêu có thể kiểm chứng lên phép đo đó; error budget giúp đội ngũ quyết định mức rủi ro có thể chấp nhận trong từng kỳ. Cloud Monitoring cung cấp công cụ để gắn service với metric, định nghĩa request-based hoặc windows-based SLI, tạo SLO, xem compliance và cảnh báo theo burn rate.

Hãy bắt đầu từ lời hứa với người dùng, chọn metric đủ gần với trải nghiệm thực tế, kiểm tra chất lượng telemetry rồi mới đặt mục tiêu. Khi SLO được gắn với dashboard, cảnh báo và quy trình phát hành, đội ngũ có thể dùng dữ liệu độ tin cậy để ưu tiên công việc và cải thiện dịch vụ một cách có chủ đích.

## Tài liệu tham khảo

- [Concepts in service monitoring – Google Cloud Observability](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring)
- [Creating an SLO – Google Cloud Observability](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/create-slo)
- [Creating a service-level indicator from metrics](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/api/identifying-custom-sli)
- [ServiceLevelObjectives REST API – Cloud Monitoring](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/services.serviceLevelObjectives)
- [Alerting on your burn rate – Google Cloud Observability](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/alerting-on-budget-burn-rate)
- [Overview of service-level indicators](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/sli-metrics/overview)
