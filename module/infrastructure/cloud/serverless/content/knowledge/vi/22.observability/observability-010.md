# Cảnh báo có ngưỡng hành động và liên kết runbook

## 1. Cảnh báo tốt phải dẫn đến hành động cụ thể

Monitoring thu thập và hiển thị tín hiệu của hệ thống. Alerting quyết định khi nào một tín hiệu cần người hoặc hệ thống tự động phản ứng. Một dashboard có thể hiển thị hàng trăm metric; một cảnh báo chỉ nên phát ra khi có tình huống cần điều tra, khắc phục hoặc đưa ra quyết định.

Trong ứng dụng serverless Java, các vấn đề thường xuất hiện dưới dạng function error, timeout, cold start tăng, throttling, queue backlog, message vào dead-letter queue (DLQ), dependency lỗi hoặc chi phí tăng bất thường. Nếu chỉ đặt một cảnh báo “CPU cao” hay “có exception”, người trực có thể không biết ảnh hưởng đến người dùng là gì, mức độ khẩn cấp ra sao và nên bắt đầu ở đâu.

Một alert có thể hành động được (actionable alert) cần trả lời được các câu hỏi:

- **Điều gì đang xảy ra?** Service, environment, region, version và triệu chứng cụ thể.
- **Ai bị ảnh hưởng?** Tỷ lệ request, tenant, loại sự kiện hoặc luồng nghiệp vụ nào.
- **Mức độ nào?** Có vi phạm SLO, mất dữ liệu, sai nghiệp vụ hay chỉ là tín hiệu cần theo dõi?
- **Khi nào cần phản ứng?** Ngưỡng, thời gian duy trì và số lượng mẫu nào đã bị vượt.
- **Ai chịu trách nhiệm?** Team/service owner và kênh nhận cảnh báo.
- **Bước tiếp theo là gì?** Runbook trực tiếp, dashboard liên quan và hành động an toàn đầu tiên.

Một cảnh báo tốt không chỉ gửi “Error rate > 5%”. Nó nói rõ error rate của `order-api` ở production, version nào bị ảnh hưởng, trong bao lâu, so với SLO/baseline ra sao, có bao nhiêu request lỗi, ai cần xử lý và liên kết đến runbook phù hợp.

## 2. Phân biệt metric, log, trace, alert và runbook

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Metric | Giá trị thay đổi theo thời gian là bao nhiêu? | Error rate, p99 duration, queue age, throttles |
| Log | Một sự kiện cụ thể đã xảy ra như thế nào? | Invocation timeout, validation failure, downstream 503 |
| Trace | Một request đi qua những thành phần nào và chậm ở đâu? | API gateway → Java function → database → payment API |
| Alert | Tình huống nào cần phản ứng ngay hoặc tạo công việc? | SLO burn rate cao trong hai cửa sổ thời gian |
| Dashboard | Tình trạng tổng thể và xu hướng ra sao? | Error/latency/concurrency theo version và region |
| Runbook | Người xử lý cần kiểm tra và thực hiện điều gì? | Xác minh downstream, dừng rollout, rollback hoặc replay DLQ |

Alert không thay thế log và trace. Nó chỉ nên mang đủ ngữ cảnh để người trực chọn đúng dashboard, log query hoặc trace cần xem. Runbook mô tả cách điều tra và hành động; alert phải liên kết trực tiếp đến đúng runbook thay vì chỉ trỏ về trang chủ monitoring.

## 3. Thiết kế ngưỡng từ SLI, SLO và error budget

### 3.1. Chọn SLI có ý nghĩa với người dùng

Service Level Indicator (SLI) là phép đo phản ánh chất lượng dịch vụ mà người dùng nhận được. Các SLI thường dùng cho serverless:

- Tỷ lệ HTTP request thành công trong tổng request hợp lệ.
- Tỷ lệ request hoàn thành trong ngưỡng latency đã cam kết.
- Tỷ lệ message được xử lý thành công trong thời hạn mục tiêu.
- Độ trễ từ lúc event được tạo đến lúc consumer hoàn tất xử lý.
- Tỷ lệ workflow hoàn tất trong SLA.
- Tỷ lệ giao dịch nghiệp vụ thành công mà không tạo side effect trùng.

Không phải mọi metric kỹ thuật đều là SLI. Memory hoặc cold start có thể giúp giải thích nguyên nhân, nhưng người dùng quan tâm request có thành công và đủ nhanh hay không. Chọn SLI ở ranh giới dịch vụ hoặc nghiệp vụ, sau đó dùng metric kỹ thuật để chẩn đoán.

### 3.2. SLO và error budget

Service Level Objective (SLO) là mục tiêu cho SLI trong một cửa sổ thời gian. Ví dụ, SLO availability 99,9% trong 30 ngày cho phép tối đa 0,1% request hợp lệ thất bại trong cửa sổ đó.

Error budget là phần lỗi được phép theo SLO:

\[
Error\ budget = 1 - SLO
\]

Với SLO 99,9%, error budget là 0,1%. Nếu tỷ lệ lỗi thực tế tăng nhanh, nhóm có thể đang tiêu thụ budget nhanh hơn mức cho phép. Alert theo error budget giúp ưu tiên vấn đề có ảnh hưởng đến cam kết dịch vụ thay vì paging cho mọi spike nhỏ.

SLO cần xác định rõ:

- Phạm vi: service, API, tenant hoặc workflow nào.
- Điều kiện tính: request hợp lệ nào được đưa vào mẫu số.
- Điều kiện lỗi: status code, timeout, invalid response hoặc event quá hạn nào tính là lỗi.
- Cửa sổ: rolling 7/30 ngày hoặc calendar window.
- Nguồn dữ liệu: metric đáng tin cậy, có đủ coverage và không đếm trùng.

Nếu mẫu số sai, SLO và alert cũng sai. Ví dụ, không nên tính health check nội bộ hoặc request bị từ chối do input sai vào cùng SLI với request nghiệp vụ nếu cam kết dịch vụ không bao gồm chúng.

### 3.3. Burn rate

Error budget burn rate cho biết tốc độ tiêu thụ budget so với tốc độ cho phép. Với error ratio quan sát được `e` và error ratio cho phép `b`:

\[
Burn\ rate = \frac{e}{b}
\]

Với SLO 99,9%, `b = 0,001`. Nếu error rate thực tế là 1%, burn rate bằng 10x. Nếu error rate thực tế đúng 0,1%, burn rate bằng 1x và budget đang được tiêu thụ đúng tốc độ trung bình tương ứng với SLO.

Burn rate cao trong một cửa sổ ngắn có thể là spike thoáng qua. Kết hợp cửa sổ ngắn và dài giúp phân biệt sự cố nghiêm trọng đang diễn ra với dao động nhỏ. Các cặp cửa sổ multi-window/multi-burn-rate thường dùng cho SLO 30 ngày gồm:

| Mức tín hiệu tham khảo | Cửa sổ dài | Cửa sổ ngắn | Burn rate |
| --- | --- | --- | ---: |
| Khẩn cấp | 1 giờ | 5 phút | 14,4x |
| Cao | 6 giờ | 30 phút | 6x |
| Trung bình | 24 giờ | 2 giờ | 3x |
| Thấp, cần theo dõi | 72 giờ | 6 giờ | 1x |

Đây là các mức tham khảo cho SLO theo cửa sổ 30 ngày, không phải ngưỡng mặc định cho mọi dịch vụ. Một alert multi-window thường chỉ fire khi burn rate vượt ngưỡng ở cả cửa sổ ngắn và dài. Cửa sổ ngắn giúp phát hiện sự cố mới; cửa sổ dài giúp xác nhận nó đủ dai dẳng để tiêu thụ đáng kể error budget.

### 3.4. Low traffic và minimum sample size

Một function ít invocation có thể có error rate 100% chỉ vì một request lỗi. Alert tỷ lệ không nên fire mà không xét số lượng mẫu. Có thể kết hợp:

- Tối thiểu số request/event trong cửa sổ.
- Error count tuyệt đối.
- Synthetic probe độc lập với traffic thật.
- Queue age hoặc workflow age cho luồng bất đồng bộ.

Ví dụ: chỉ đánh giá error ratio khi có ít nhất 100 request trong 10 phút; nếu traffic thấp hơn, dùng synthetic probe để kiểm tra availability và cảnh báo riêng khi không có telemetry. Giá trị 100 chỉ là ví dụ, phải hiệu chỉnh theo traffic và mức độ quan trọng.

## 4. Đặt threshold có ngữ cảnh

### 4.1. Threshold tĩnh

Threshold tĩnh phù hợp khi có giới hạn rõ và tương đối ổn định:

- Queue age vượt SLA tối đa.
- DLQ có message mới.
- Concurrent execution đạt gần quota.
- Function timeout tăng trên ngưỡng đã định.
- Dung lượng storage hoặc connection pool vượt giới hạn an toàn.
- Chi phí theo ngày vượt budget đã phê duyệt.

Threshold phải gắn với hành động. Ví dụ, alert queue age vượt 5 phút có thể yêu cầu kiểm tra consumer backlog và downstream. Nếu queue age vượt 30 phút trong khi SLA là 15 phút, mức độ có thể cần paging vì backlog đã vi phạm cam kết.

### 4.2. Threshold tương đối và baseline

Với latency, invocation volume hoặc chi phí có tính mùa vụ, baseline tương đối có thể hữu ích hơn một con số cố định. So sánh với cùng giờ/ngày trong chu kỳ trước hoặc với stable version giúp phát hiện regression.

Không dùng baseline mù quáng. Một sự cố kéo dài có thể khiến baseline tự học theo trạng thái lỗi và xem lỗi là bình thường. Giữ baseline có kiểm soát, loại khoảng thời gian incident/maintenance và có ngưỡng tuyệt đối bảo vệ.

### 4.3. Ngưỡng theo duration và số lần vi phạm

Alert nên quy định điều kiện duy trì, chẳng hạn:

- Error rate vượt 2% trong 5 phút liên tục.
- p99 latency vượt SLO trong hai cửa sổ liên tiếp.
- Queue oldest-message age vượt 10 phút trong 3 lần đánh giá.
- DLQ có ít nhất một message mới trong production.
- Throttling xuất hiện liên tục và có request bị ảnh hưởng.

Khoảng duy trì giúp giảm false positive do spike ngắn. Nhưng với sự kiện nghiêm trọng như data loss, unauthorized access hoặc double charge, không nên chờ một khoảng dài chỉ để lọc nhiễu. Hãy phân loại severity và định nghĩa điều kiện khẩn cấp riêng.

### 4.4. Hysteresis và recovery threshold

Nếu alert fire ở 80% quota và resolve ngay khi metric tụt xuống 79%, hệ thống có thể liên tục fire/resolve khi metric dao động quanh ngưỡng. Hysteresis dùng ngưỡng resolve thấp hơn ngưỡng fire hoặc yêu cầu điều kiện ổn định trong một khoảng thời gian.

Ví dụ:

- Fire khi concurrency sử dụng trên 85% quota trong 5 phút.
- Resolve khi concurrency xuống dưới 70% trong 10 phút.

Ngưỡng cụ thể cần phù hợp với tốc độ scale và khả năng phục hồi. Đối với alert theo SLO, dùng logic cửa sổ và burn rate thay vì chỉ áp dụng hysteresis cho một gauge đơn lẻ.

## 5. Những tín hiệu quan trọng cho Java serverless

### 5.1. HTTP function

Theo dõi tối thiểu:

| Signal | Ý nghĩa | Khi nào cần alert |
| --- | --- | --- |
| Request count | Traffic thực tế | Traffic giảm về 0 ngoài dự kiến hoặc tăng đột biến gây quá tải |
| Error ratio / 5xx | Request thất bại | Burn rate vượt ngưỡng hoặc lỗi tuyệt đối tăng |
| p95/p99 duration | Tail latency | Vi phạm SLO trong cửa sổ đủ mẫu |
| Timeout count | Function không hoàn tất | Tăng liên tục hoặc ảnh hưởng luồng quan trọng |
| Throttles / rejected concurrency | Không cấp được execution capacity | Có request/event bị trì hoãn hoặc từ chối |
| Cold start / init duration | Chi phí khởi tạo runtime | Regression ảnh hưởng latency hoặc error budget |
| Dependency failure | Database/API ngoài bị lỗi | Lỗi phụ thuộc kéo dài, nhiều function cùng bị ảnh hưởng |

### 5.2. Queue và event consumer

Với function xử lý message, error rate không phản ánh đầy đủ tình trạng. Theo dõi thêm:

- Oldest message age hoặc event lag.
- Queue depth/backlog và tốc độ tăng backlog.
- Retry/redelivery count.
- DLQ message count và tốc độ message đi vào DLQ.
- Batch failure và partial batch response.
- Consumer concurrency và throughput.
- Checkpoint/offset progress với stream.
- Thời gian từ event creation đến business completion.

Queue có backlog nhưng consumer vẫn xử lý thành công có thể là tình huống bình thường trong giờ cao điểm. Alert nên dựa vào age/SLA và xu hướng backlog, không chỉ số lượng message tuyệt đối.

### 5.3. Workflow dài hạn

Với Durable Functions hoặc workflow engine tương tự, cần theo dõi:

- Instance failed/terminated tăng bất thường.
- Instance running lâu hơn SLA nghiệp vụ.
- Activity retry count và activity duration.
- Số workflow chờ external event quá hạn.
- Số workflow stuck ở một state.
- Compensation failure.
- Storage/task hub backlog hoặc provider throttling.

Một instance ở trạng thái `Running` có thể đang chờ timer nhiều giờ theo thiết kế. Chỉ cảnh báo khi tuổi instance hoặc thời gian ở một state vượt SLA dự kiến.

### 5.4. Chi phí và bất thường sử dụng

Theo dõi cost theo service, environment, function, tag và thời gian:

- Chi phí function compute tăng nhanh hơn traffic.
- Invocation tăng bất thường do retry loop hoặc bot traffic.
- Memory/duration tăng sau release.
- Log ingestion hoặc trace volume tăng đột biến.
- Queue transaction, storage operation hoặc egress tăng.
- Concurrency/instance count tăng kéo theo chi phí downstream.

Budget alert thường là cảnh báo tài chính hoặc ticket, không nhất thiết là page on-call. Nếu chi phí tăng do một runaway loop gây ảnh hưởng hệ thống, cần alert vận hành riêng để dừng nguồn phát sinh.

## 6. Severity và định tuyến cảnh báo

### 6.1. Phân loại mức độ

| Severity | Ý nghĩa | Kênh/response điển hình |
| --- | --- | --- |
| SEV1 / Critical | Mất dịch vụ diện rộng, data loss, rủi ro bảo mật hoặc sai giao dịch nghiêm trọng | Page on-call ngay, incident commander và escalation |
| SEV2 / High | Suy giảm đáng kể, một luồng nghiệp vụ quan trọng vi phạm SLO | Page team owner trong giờ trực, cập nhật incident |
| SEV3 / Warning | Có nguy cơ vượt SLO hoặc backlog tăng nhưng chưa ảnh hưởng nghiêm trọng | Ticket/chat channel, xử lý trong ca hoặc giờ làm việc |
| SEV4 / Info | Xu hướng, capacity hoặc budget cần xem xét | Dashboard/report, không page |

Severity phải phản ánh impact và urgency, không phản ánh độ khó kỹ thuật. Một lỗi đơn lẻ ở test environment không nên là SEV1 chỉ vì stack trace dài. Ngược lại, một event nghiệp vụ bị mất hoặc một khoản thanh toán bị ghi trùng có thể rất nghiêm trọng dù error rate tổng thấp.

### 6.2. Routing theo owner

Mỗi alert nên có metadata định tuyến:

- `service`: tên service/function.
- `team`: team chịu trách nhiệm.
- `environment`: production, staging hoặc development.
- `severity`: mức độ.
- `region`: vùng triển khai.
- `version`: revision hoặc artifact đang bị ảnh hưởng.
- `runbook_url`: liên kết runbook cụ thể.
- `dashboard_url`: dashboard chẩn đoán.

Alert production phải đến đúng team owner và có escalation nếu không được acknowledge trong thời gian quy định. Alert staging thường không page on-call trừ khi staging là thành phần quan trọng của release hoặc test gate.

### 6.3. Grouping, deduplication và inhibition

Một lỗi database dùng chung có thể khiến 30 function cùng phát alert. Nếu gửi 30 page độc lập, người trực bị ngập thông báo. Alert manager nên nhóm theo dependency, service hoặc incident fingerprint; deduplicate alert cùng nguyên nhân; và inhibition để cảnh báo triệu chứng cấp thấp không che lấp cảnh báo gốc.

Không gộp quá rộng đến mức che mất function hoặc region riêng đang gặp lỗi. Alert group cần hiển thị danh sách instance/service bị ảnh hưởng và có thể drill down.

Maintenance window hoặc deployment silence có thể giảm cảnh báo dự kiến trong thời gian thay đổi. Silence phải có thời hạn, owner và lý do; không dùng silence dài hạn để che lỗi thường trực.

## 7. Runbook phải được liên kết trực tiếp từ alert

### 7.1. Runbook là gì?

Runbook là hướng dẫn vận hành cho một tình huống cụ thể. Nó giúp người trực biết cách xác nhận impact, khoanh vùng nguyên nhân, thực hiện hành động an toàn, xác minh phục hồi và thu thập bằng chứng.

Một runbook tốt cần:

1. Tên tình huống và triệu chứng kích hoạt.
2. Service owner và kênh escalation.
3. Mức độ ảnh hưởng và SLO liên quan.
4. Dashboard, log query và trace filter cần mở.
5. Các bước xác minh theo thứ tự, từ ít rủi ro đến sâu hơn.
6. Hành động giảm thiểu được phép thực hiện.
7. Điều kiện dừng, rollback hoặc chuyển cấp.
8. Cách xác minh phục hồi.
9. Cách xử lý dữ liệu còn tồn, retry hoặc DLQ.
10. Người cập nhật, ngày review và liên kết tài liệu phụ trợ.

### 7.2. Link runbook trong alert

Alert nên chứa URL cụ thể đến trang runbook phù hợp với service và tình huống. Ví dụ cấu trúc metadata:

```yaml
labels:
  service: order-api
  team: payments-platform
  environment: production
  severity: critical
  alert_id: FunctionHighErrorRate
annotations:
  summary: "order-api production error rate is above its SLO threshold"
  description: "Version {{ $labels.version }} has error ratio {{ $value }}."
  runbook_url: "${RUNBOOK_URL}"
  dashboard_url: "${DASHBOARD_URL}"
```

`RUNBOOK_URL` và `DASHBOARD_URL` là placeholder cần được thay bằng URL thật trong repository/wiki vận hành. Không để alert production trỏ đến link giả, trang chủ chung hoặc tài liệu chỉ team tác giả mới có quyền đọc. Kiểm tra quyền truy cập từ tài khoản on-call.

### 7.3. Alert message mẫu

```text
[SEV2] order-api / production / ap-southeast-1

Condition: 5xx error ratio exceeded 2% for 10 minutes.
Impact: 8.4% of valid create-order requests failed in the last 10 minutes.
Candidate: version 42 accounts for most failures; stable version 41 is within baseline.
First action: compare version 42 traces and dependency errors; pause rollout if confirmed.
Owner: payments-platform
Dashboard: ${DASHBOARD_URL}
Runbook: ${RUNBOOK_URL}
```

Alert message cần ngắn đủ để đọc trên điện thoại nhưng có thông tin quyết định. Chi tiết điều tra nằm trong runbook và dashboard.

### 7.4. Runbook không được chứa thao tác nguy hiểm thiếu kiểm soát

Các bước như xóa queue, purge history, rotate key, tăng concurrency lớn hoặc rollback database có thể gây mất dữ liệu hoặc chi phí. Runbook cần nêu rõ:

- Điều kiện được phép thực hiện.
- Quyền/role cần có.
- Ảnh hưởng và cách rollback thao tác.
- Người phê duyệt nếu cần.
- Bước xác minh sau thao tác.

Không đưa secret hoặc token vào runbook. Dùng secret manager và mô tả cách truy cập theo quyền đã cấp.

## 8. Ví dụ Prometheus alert rule

Prometheus rule dưới đây minh họa alert có threshold, thời gian duy trì, owner và runbook link. Tên metric là metric ứng dụng giả định; khi triển khai cần ánh xạ sang exporter hoặc telemetry backend đang dùng.

```yaml
groups:
  - name: serverless-function-alerts
    rules:
      - alert: FunctionHighErrorRate
        expr: |
          (
            sum by (service, environment, version) (
              rate(function_invocations_total{outcome="error",environment="production"}[5m])
            )
            /
            clamp_min(
              sum by (service, environment, version) (
                rate(function_invocations_total{environment="production"}[5m])
              ),
              0.001
            )
          ) > 0.02
          and on (service, environment, version)
          sum by (service, environment, version) (
            increase(function_invocations_total{environment="production"}[5m])
          ) >= 100
        for: 10m
        labels:
          severity: page
          team: serverless-platform
        annotations:
          summary: "Function error ratio is above 2%"
          description: "{{ $labels.service }} version {{ $labels.version }} has elevated errors."
          runbook_url: "${RUNBOOK_URL}"
          dashboard_url: "${DASHBOARD_URL}"
```

Trong ví dụ, rule yêu cầu error ratio trên 2%, có ít nhất 100 invocation trong cửa sổ đánh giá và duy trì điều kiện trong 10 phút. `clamp_min` tránh chia cho 0; điều kiện minimum sample ngăn một request đơn lẻ tạo alert tỷ lệ. Cú pháp và cách xử lý missing series cần kiểm tra với phiên bản Prometheus/Alertmanager đang dùng.

Không sao chép nguyên rule cho mọi function. Một function ít traffic có thể cần synthetic check hoặc error count tuyệt đối; một function thanh toán có thể cần ngưỡng nghiêm ngặt hơn. Metric label phải có cardinality giới hạn; không đưa request ID, user ID hoặc nonce vào label.

## 9. Alert theo SLO burn rate

Ví dụ PromQL khái niệm cho một SLI availability với metric `http_requests_total` và label `status_class`:

```promql
sum(rate(http_requests_total{status_class="5xx"}[5m]))
/
sum(rate(http_requests_total[5m]))
```

Error ratio trên được chia cho error budget ratio để tính burn rate. Với SLO 99,9%, error budget ratio là 0,001. Một alert khẩn cấp có thể yêu cầu burn rate trên 14,4x trong cả cửa sổ 5 phút và 1 giờ. Ví dụ biểu thức:

```promql
(
  error_ratio_5m / 0.001 > 14.4
)
and
(
  error_ratio_1h / 0.001 > 14.4
)
```

`error_ratio_5m` và `error_ratio_1h` ở đây là recording rule đã được định nghĩa trước. Đây là minh họa logic multi-window; production cần thêm minimum traffic, lọc request hợp lệ, group label đúng và kiểm tra missing data.

Nếu chỉ có một alert threshold 5xx > 5%, nhóm có thể bỏ lỡ sự cố nhỏ nhưng kéo dài đủ để tiêu thụ error budget, hoặc bị page bởi một spike ngắn không ảnh hưởng đáng kể. Burn rate kết hợp cửa sổ giúp liên kết cảnh báo với mục tiêu dịch vụ.

## 10. Tích hợp với nền tảng cloud

### 10.1. AWS Lambda và CloudWatch

CloudWatch cung cấp metric và alarm cho Lambda. Các metric thường cần theo dõi gồm `Invocations`, `Errors`, `Duration`, `Throttles`, `ConcurrentExecutions` và `AsyncEventsDropped`/metric liên quan đến async invocation khi phù hợp. Cold start/init duration có thể cần telemetry hoặc instrumentation bổ sung tùy runtime và cách quan sát.

CloudWatch Alarm có thể chuyển trạng thái `OK`, `ALARM` hoặc `INSUFFICIENT_DATA`; alarm action có thể gửi SNS hoặc kích hoạt workflow/automation được cấu hình. Với Lambda, cần:

- Phân biệt metric theo function, alias/version khi có dimension phù hợp.
- Không gộp candidate và stable khiến regression bị che.
- Theo dõi event source mapping, queue age và DLQ bằng metric của nguồn event.
- Gắn runbook/dashboard URL vào alarm description hoặc notification template.
- Kiểm tra alarm action có quyền và destination hoạt động.

### 10.2. Azure Functions và Azure Monitor

Azure Functions có thể gửi telemetry qua Application Insights/Azure Monitor. Theo dõi invocation, failure, duration, dependency, exception, host restart và trigger-specific backlog. Azure Monitor alert rule có thể dùng metric alert hoặc log search alert; Action Group định tuyến thông báo đến email, SMS, webhook, ITSM hoặc automation tùy cấu hình.

Khi thiết kế:

- Phân biệt lỗi function với lỗi dependency.
- Dùng operation/correlation ID để nối invocation và dependency trace.
- Chọn dimension theo function name, app, slot, region và version khi dữ liệu hỗ trợ.
- Không query log quá rộng hoặc tạo alert trên một exception lẻ không có impact.
- Gắn runbook link trong alert rule/action payload và kiểm tra quyền truy cập.

### 10.3. Google Cloud Functions và Cloud Run

Cloud Monitoring hỗ trợ alert policy trên metric, log-based metric và SLO. Notification channel có thể gửi email, chat, webhook hoặc tích hợp incident management. Với Cloud Run/function workloads, theo dõi request count, latency, 4xx/5xx, instance count, container startup, concurrency và lỗi dependency.

Với event-driven service, kết hợp metric từ Pub/Sub hoặc event source như undelivered message, oldest unacked age, backlog và dead-letter delivery. Không chỉ alert trên container instance count vì scale-out có thể là phản ứng bình thường trước traffic tăng.

### 10.4. Provider-neutral alert metadata

Dù dùng nền tảng nào, chuẩn hóa các trường alert ở tầng vận hành:

```json
{
  "alertId": "FunctionHighErrorRate",
  "service": "order-api",
  "environment": "production",
  "region": "ap-southeast-1",
  "version": "42",
  "severity": "SEV2",
  "owner": "payments-platform",
  "startedAt": "2026-11-17T10:15:00Z",
  "summary": "Request error ratio is above the service threshold",
  "runbookUrl": "${RUNBOOK_URL}",
  "dashboardUrl": "${DASHBOARD_URL}"
}
```

Chuẩn hóa giúp routing và incident tooling nhất quán khi service chạy trên nhiều cloud provider. Payload thực tế cần theo schema của alert manager/ITSM đang dùng.

## 11. Java instrumentation để tạo tín hiệu có ích

### 11.1. Metric có cardinality kiểm soát

Java function có thể dùng Micrometer hoặc OpenTelemetry API để phát metric. Nên dùng label có tập giá trị nhỏ như service, operation, outcome, region và version. Không dùng user ID, order ID, request ID hoặc exception message làm label vì số lượng series có thể tăng không giới hạn.

Ví dụ Micrometer:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class OrderMetrics {
    private final Counter success;
    private final Counter failure;
    private final Timer duration;

    public OrderMetrics(MeterRegistry registry) {
        this.success = Counter.builder("order_function_invocations")
                .tag("outcome", "success")
                .register(registry);
        this.failure = Counter.builder("order_function_invocations")
                .tag("outcome", "failure")
                .register(registry);
        this.duration = Timer.builder("order_function_duration")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void recordSuccess() {
        success.increment();
    }

    public void recordFailure() {
        failure.increment();
    }

    public Timer duration() {
        return duration;
    }
}
```

Đây là ví dụ instrumentation; cách export metric phụ thuộc runtime và nền tảng. Với function ngắn hạn, cần bảo đảm metric được flush/export trước khi execution environment bị dừng hoặc dùng extension/collector phù hợp. Không để metric export đồng bộ làm tăng đáng kể latency của handler.

### 11.2. Structured logging

Log có cấu trúc giúp query theo service, function, invocation ID, trace ID, version và error code. Ví dụ JSON:

```json
{
  "timestamp": "2026-11-17T10:15:30Z",
  "level": "ERROR",
  "service": "order-api",
  "function": "CreateOrder",
  "version": "42",
  "invocationId": "inv-91",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "errorCode": "PAYMENT_PROVIDER_TIMEOUT",
  "dependency": "payment-provider",
  "message": "Payment request exceeded timeout"
}
```

Không ghi access token, secret, thông tin thẻ hoặc payload nhạy cảm. Dùng error code ổn định thay cho exception message làm dimension/label.

### 11.3. Trace context và correlation

Propagation trace context qua HTTP header hoặc message metadata giúp nối function với dependency. Với OpenTelemetry, dùng trace/span ID để tìm trace lỗi từ alert. Cần giữ correlation ID qua queue, retry và workflow; không tạo ID mới làm mất liên hệ với event gốc.

Sampling có thể khiến trace của một số request không được lưu. Alert không nên phụ thuộc hoàn toàn vào trace sampling; metric phải đủ để phát hiện vấn đề và trace dùng để điều tra sâu.

## 12. Runbook mẫu cho các alert serverless phổ biến

### 12.1. Function error rate cao

**Trigger:** error ratio vượt ngưỡng SLO trong hai cửa sổ đánh giá hoặc error count tăng liên tục với sample đủ lớn.

**Kiểm tra:**

1. Xác định service, region, function, version và thời điểm bắt đầu.
2. So sánh error rate của stable/candidate và các region khác.
3. Mở trace/log theo invocation ID và error code.
4. Kiểm tra dependency failure, deploy gần nhất, secret/config và quota.
5. Xác định lỗi validation đầu vào hay lỗi runtime/dependency.

**Hành động:**

- Nếu regression gắn với version mới, dừng rollout và rollback traffic theo quy trình release.
- Nếu dependency dùng chung đang lỗi, áp dụng timeout/circuit breaker và thông báo owner dependency.
- Nếu lỗi do input độc hại hoặc traffic bất thường, bật rate limit/WAF rule theo quy trình được phê duyệt.
- Không retry mù quáng request không idempotent.

**Xác minh phục hồi:** error ratio và burn rate giảm về mức bình thường, latency ổn định, không có backlog hoặc side effect trùng cần đối soát.

### 12.2. Queue age hoặc backlog tăng

**Trigger:** oldest message age vượt SLA hoặc backlog tăng liên tục trong khi consumer throughput thấp hơn producer rate.

**Kiểm tra:**

1. Xác định queue/subscription, partition, consumer version và thời điểm backlog bắt đầu tăng.
2. Kiểm tra consumer concurrency, throttles, timeout và retry count.
3. Kiểm tra downstream database/API có bị throttling hoặc hết connection không.
4. Xem DLQ, poison message và schema version của message lỗi.
5. Ước lượng tốc độ backlog tăng và thời gian xử lý hết nếu giữ throughput hiện tại.

**Hành động:**

- Tăng concurrency chỉ khi downstream còn capacity và quota cho phép.
- Dừng hoặc rollback candidate nếu consumer mới gây lỗi/throughput giảm.
- Cách ly poison message theo chính sách; không xóa message để làm giảm backlog.
- Nếu downstream quá tải, giảm consumer rate hoặc áp dụng backpressure.

**Xác minh phục hồi:** oldest message age giảm, backlog có xu hướng đi xuống, DLQ không tăng bất thường và business completion lag trở lại SLA.

### 12.3. DLQ có message mới

**Trigger:** DLQ count tăng hoặc có message mới trong production queue quan trọng.

**Kiểm tra:**

1. Xác định message ID, source queue, event type và schema version.
2. Đọc error metadata và retry history mà không log payload nhạy cảm.
3. Kiểm tra consumer release, permission, dependency và poison payload.
4. Xác định message có thể replay an toàn không và consumer có idempotent không.

**Hành động:**

- Sửa nguyên nhân trước khi replay.
- Giữ message trong DLQ/quarantine trong khi điều tra.
- Replay theo batch nhỏ và theo dõi kết quả.
- Không purge DLQ chỉ để xóa alert.

**Xác minh phục hồi:** message được xử lý hoặc có quyết định nghiệp vụ rõ ràng; DLQ count và tuổi message được kiểm soát.

### 12.4. Throttling hoặc concurrency gần quota

**Trigger:** throttles tăng hoặc concurrency duy trì trên ngưỡng capacity đã định.

**Kiểm tra:**

1. Xác định function/region và quota account/service.
2. Kiểm tra invocation rate, duration, retry storm và event source batch.
3. Xác định downstream connection/throughput có chịu được scale-out không.
4. Kiểm tra traffic bất thường hoặc loop gọi lẫn nhau.

**Hành động:**

- Giảm nguồn traffic hoặc retry storm nếu có thể.
- Điều chỉnh reserved/provisioned concurrency hoặc quota theo kế hoạch capacity.
- Tăng batch size/concurrency chỉ khi semantics và downstream cho phép.
- Áp dụng backpressure và giới hạn client.

**Xác minh phục hồi:** throttles giảm, latency/queue age ổn định và downstream không bị quá tải.

### 12.5. Chi phí tăng bất thường

**Trigger:** cost rate vượt budget hoặc tăng nhiều so với baseline trong cửa sổ đủ dài.

**Kiểm tra:**

1. Phân rã chi phí theo service, function, region, tag và loại tài nguyên.
2. So sánh invocation, duration, memory, log ingestion, egress và retry.
3. Kiểm tra deploy gần nhất, traffic bất thường và recursive trigger.
4. Xác định phần tăng là workload hợp lệ hay loop/lỗi.

**Hành động:**

- Giới hạn nguồn traffic hoặc tạm dừng trigger theo quy trình được phê duyệt nếu có runaway loop.
- Sửa retry policy, log verbosity hoặc payload size nếu đó là nguyên nhân.
- Không giảm memory/concurrency tùy tiện nếu có thể làm timeout và retry tăng thêm.

**Xác minh phục hồi:** cost rate trở về baseline hợp lý, business workload vẫn được xử lý và không tạo backlog ngoài SLA.

## 13. Kiểm thử alert và runbook

Alert rule cũng là code cần được kiểm thử và review. Trước production:

- Dùng dữ liệu mẫu để xác minh rule fire đúng khi vượt threshold.
- Kiểm tra rule không fire khi traffic thấp hoặc metric missing ngoài dự kiến.
- Kiểm tra alert resolve khi điều kiện hồi phục.
- Kiểm tra notification đến đúng team/kênh và có đủ labels.
- Mở runbook link từ alert bằng tài khoản on-call.
- Thực hành runbook trong game day hoặc incident simulation.
- Kiểm tra hành động rollback/scale/replay có quyền và guardrail.
- Kiểm tra alert grouping, deduplication, escalation và silence expiry.
- Xác minh alert khi telemetry backend hoặc notification channel lỗi.

Không chỉ test biểu thức query. Một rule có thể đúng nhưng không ai nhận được notification vì Action Group/SNS/webhook sai quyền hoặc URL runbook không truy cập được.

### 13.1. Test threshold với fixture

Có thể chuẩn bị các bộ dữ liệu:

| Fixture | Kết quả mong đợi |
| --- | --- |
| Error ratio thấp, traffic bình thường | Không fire |
| Error ratio cao nhưng chỉ một request | Không page nếu minimum sample chưa đạt |
| Error ratio cao và kéo dài | Fire đúng severity |
| Một spike ngắn rồi hồi phục | Không fire nếu chưa vượt thời gian duy trì |
| Metric không có dữ liệu | Alert telemetry missing hoặc trạng thái unknown theo policy |
| Candidate lỗi, stable bình thường | Alert gắn nhãn candidate version |
| Stable và candidate cùng lỗi do dependency | Alert cho dependency/service impact, không quy lỗi riêng candidate |
| Queue backlog tăng nhưng age còn trong SLA | Warning hoặc không alert tùy policy |
| DLQ có message production | Fire theo severity của queue nghiệp vụ |

### 13.2. Review runbook định kỳ

Mỗi runbook cần owner, ngày review và version. Sau incident, cập nhật bước điều tra theo bằng chứng mới; loại bỏ lệnh đã lỗi thời; kiểm tra URL dashboard/query còn hoạt động; xác nhận quyền truy cập và escalation contact. Runbook không được coi là hoàn tất chỉ vì có một trang tài liệu cùng tên alert.

## 14. Giảm alert fatigue

Alert fatigue xảy ra khi người trực nhận quá nhiều cảnh báo ít giá trị, lặp lại hoặc không có hành động rõ. Theo thời gian, họ có thể bỏ qua cả alert quan trọng.

Các cách giảm:

- Chỉ page cho impact khẩn cấp; warning tạo ticket hoặc gửi channel.
- Dùng SLO burn rate thay vì page cho mọi threshold nhỏ.
- Kết hợp minimum sample và thời gian duy trì.
- Group alert theo incident/dependency.
- Deduplicate cùng fingerprint và suppress symptom khi root-cause alert đã fire.
- Tự động resolve khi condition phục hồi ổn định.
- Đặt owner cho từng alert và xóa alert không có người chịu trách nhiệm.
- Đo số alert/incident, tỷ lệ false positive, số page ngoài giờ và thời gian acknowledge.
- Review alert sau mỗi incident và sau mỗi thay đổi kiến trúc.

Không giảm alert fatigue bằng cách tắt cảnh báo khó chịu mà chưa xác định lý do. Nếu alert không actionable, hãy sửa query, threshold, routing hoặc runbook.

## 15. Quản lý missing data và lỗi hệ thống alerting

Không có metric không đồng nghĩa service khỏe. Function có thể không phát metric do exporter lỗi, permission bị thu hồi, network bị chặn hoặc telemetry pipeline gặp sự cố.

Phân biệt:

- **Zero traffic:** không có request/event thật trong khoảng thời gian đó.
- **Zero errors:** có request nhưng không ghi nhận lỗi.
- **Missing telemetry:** không có sample hoặc pipeline không gửi dữ liệu.
- **Stale data:** metric cuối cùng quá cũ so với chu kỳ cập nhật.

Với service quan trọng, cần alert riêng cho telemetry pipeline, heartbeat hoặc synthetic probe. Không dùng `or vector(0)` hoặc biến missing series thành 0 một cách vô điều kiện nếu điều đó có thể che việc exporter chết.

Notification path cũng cần được giám sát: kiểm tra alarm engine, webhook, SNS/Action Group/notification channel và escalation service. Có thể dùng synthetic alert test định kỳ để xác minh toàn bộ đường đi từ rule đến người nhận.

## 16. Checklist thiết kế alert có runbook

- [ ] Alert gắn với SLI/SLO hoặc một giới hạn vận hành có hành động rõ.
- [ ] Có threshold, cửa sổ đánh giá, thời gian duy trì và minimum sample khi cần.
- [ ] Severity phản ánh impact và urgency.
- [ ] Có service owner, team, environment, region và version.
- [ ] Alert phân biệt candidate/stable hoặc các cohort quan trọng.
- [ ] Message mô tả triệu chứng, impact và điều kiện đã vượt.
- [ ] Có `runbook_url` trực tiếp đến đúng tình huống.
- [ ] Có dashboard/log/trace link giúp điều tra.
- [ ] Runbook có bước xác minh, hành động an toàn, rollback/escalation và xác minh phục hồi.
- [ ] URL và quyền truy cập đã được kiểm tra bằng tài khoản on-call.
- [ ] Alert grouping, deduplication, inhibition và silence có giới hạn.
- [ ] Có alert cho missing telemetry và notification pipeline.
- [ ] Có test cho fire, resolve, missing data và routing.
- [ ] Có owner và ngày review cho rule/runbook.
- [ ] Có quy trình cập nhật sau incident và loại bỏ alert không còn giá trị.

## 17. Kết luận

Alert có ngưỡng hành động giúp đội vận hành tập trung vào vấn đề ảnh hưởng đến người dùng và mục tiêu dịch vụ. Bắt đầu từ SLI/SLO và error budget, chọn threshold có xét thời gian, sample size và burn rate, rồi phân loại severity theo impact. Với serverless, cần theo dõi cả HTTP errors/latency/concurrency lẫn queue age, retry, DLQ, workflow age và cost anomaly.

Mỗi alert production cần có owner, metadata, dashboard và runbook URL trực tiếp. Runbook phải mô tả cách xác minh, hành động an toàn, điều kiện rollback/escalation và cách xác nhận phục hồi. Kiểm thử cả rule lẫn notification path, giám sát missing telemetry và review sau incident để giữ cảnh báo có giá trị. Một alert chỉ thực sự hữu ích khi người nhận hiểu chuyện gì đang xảy ra và biết bước tiếp theo cần làm.
