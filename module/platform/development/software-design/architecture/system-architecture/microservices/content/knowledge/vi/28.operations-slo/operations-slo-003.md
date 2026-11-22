# Thiết kế cảnh báo theo tác động thay vì chỉ theo tài nguyên

## 1. Vấn đề: Hệ thống “đỏ” không đồng nghĩa người dùng bị ảnh hưởng

Trong hệ thống nhiều dịch vụ, dashboard thường chứa hàng trăm chỉ số như CPU, RAM, disk, connection pool, request per second, queue depth, restart count và latency. Một số đội tạo cảnh báo theo kiểu “CPU trên 80% thì page”, “RAM trên 70% thì page”, “Pod restart thì page” hoặc “Kafka consumer lag vượt 1.000 thì page”. Những quy tắc này có thể hữu ích trong một số hoàn cảnh, nhưng **tài nguyên tăng cao không tự chứng minh người dùng bị ảnh hưởng**, và **tài nguyên bình thường không đảm bảo hệ thống cung cấp được kết quả nghiệp vụ**.

Ví dụ:

- CPU của một replica tăng lên 90% khi đang xử lý batch hợp lệ, nhưng P99 latency, error rate và business outcomes đều nằm trong SLO. Đánh thức on-call lúc 2 giờ sáng có thể không tạo giá trị.
- CPU của tất cả Pod chỉ 20%, nhưng Payment Service trả 503 vì nhà cung cấp thanh toán từ chối kết nối. Khách không đặt hàng được; một dashboard dựa trên CPU vẫn “xanh”.
- Queue backlog của Notification tăng sau một chiến dịch, nhưng email sẽ được gửi trong 10 phút và cam kết là một giờ. Đây có thể là hành vi bình thường.
- Queue backlog của §OrderPaid§ tăng trong hai phút và 200 đơn đã thu tiền chưa giữ kho, vượt cam kết 30 giây. Đây là ảnh hưởng nghiệp vụ nghiêm trọng dù queue depth chưa tới ngưỡng chung.

**Cảnh báo theo tác động (impact-based alerting)** bắt đầu từ câu hỏi: người dùng, đối tác hoặc một quy trình nghiệp vụ thiết yếu đang không nhận được kết quả nào, trong bao lâu, trên phạm vi bao nhiêu, với hậu quả gì? Sau đó mới dùng metric tài nguyên và thành phần để chẩn đoán nguyên nhân, phòng ngừa sự cố hoặc lập kế hoạch năng lực.

Tài liệu thuộc nhóm **Vận hành và SLO**, tập trung thiết kế cảnh báo hành động được cho microservices, ứng dụng API, event-driven workflows và dependencies. Ví dụ xuyên suốt là hệ thống thương mại điện tử có API Gateway, Order, Payment, Inventory, Fulfillment, Notification, database và message broker.

### Sau khi học, bạn có thể

1. Phân biệt triệu chứng của người dùng với chỉ số tài nguyên và nguyên nhân kỹ thuật.
2. Chọn Service Level Indicators (SLIs) bám kết quả quan trọng thay vì chỉ infrastructure utilization.
3. Biến SLO thành error budget, burn-rate alert và ngưỡng hành động phù hợp.
4. Đánh giá độ nghiêm trọng theo tác động, số lượng người bị ảnh hưởng, rủi ro tài chính và tính cấp bách.
5. Thiết kế dashboard, alert routing, deduplication, inhibition, runbook và escalation.
6. Viết các truy vấn PromQL minh họa cho request reliability và asynchronous workflow.
7. Xử lý traffic thấp, missing data, long-running jobs, dependency outage, retry amplification và báo động giả.
8. Đánh giá chất lượng cảnh báo thông qua noise, precision, recall, thời gian phát hiện và kết quả incident.

## 2. Phân tầng tín hiệu: outcome, triệu chứng, nguyên nhân

Không phải mọi metric cần cùng mức độ khẩn cấp.

| Tầng | Câu hỏi | Ví dụ | Thường dùng để |
|---|---|---|---|
| **Tác động người dùng/nghiệp vụ** | Khách có đạt kết quả đúng và đúng hạn không? | Checkout success, payment outcome, paid orders stuck | Page hoặc incident khi vi phạm SLO/rủi ro |
| **Triệu chứng dịch vụ** | API hoặc workflow đang không đáp ứng contract? | 5xx, timeout, P99, queue age, stale projection | Page nếu phản ánh mất dịch vụ; điều tra |
| **Khả năng chịu tải** | Thành phần đang gần giới hạn không? | DB pool saturation, disk forecast, CPU throttling | Ticket/warning, đôi khi page nếu sắp gây sự cố tức thời |
| **Nguyên nhân kỹ thuật** | Vì sao hệ thống bị ảnh hưởng? | OOM, lock waits, broker rebalances, network errors | Dashboard, alert liên kết, runbook |
| **Tình trạng observability** | Có tin được số liệu không? | Metrics scrape failures, data freshness, missing events | Cảnh báo riêng về mù quan sát |

Một cảnh báo tốt thường nói được cả **tác động** và **bằng chứng liên quan**: “Checkout requests lỗi 5% trong 10 phút tại region APAC, có 2.400 attempts bị ảnh hưởng; Payment gateway 503 tăng sau release R42”. Nó hữu ích hơn “CPU payment-service > 80%”.

Tuy nhiên không có nghĩa **xóa hết alert tài nguyên**. Các tín hiệu dự báo sự cố có thể đáng cảnh báo sớm: disk còn 10 phút trước khi đầy, TLS certificate sắp hết hạn, database replication lag vượt RPO, quota thanh toán sắp cạn, hoặc bộ nhớ tăng theo tốc độ chắc chắn dẫn tới OOM. Lý do cảnh báo là **dự báo tác động trong thời gian hành động được**, chứ không phải tài nguyên cao một cách trừu tượng.

## 3. Định nghĩa tác động trong microservices

Một luồng đặt hàng có thể gồm:

~~~mermaid
flowchart LR
    U[Customer] --> G[API Gateway]
    G --> O[Order Service]
    O --> P[Payment Service]
    O --> I[Inventory Service]
    O --> B[(Message Broker)]
    B --> F[Fulfillment Service]
    P --> PSP[Payment Provider]
    I --> DB[(Inventory DB)]
    O --> T[(Workflow Projection)]
    P --> T
    I --> T
    F --> T
~~~

Nếu §POST /orders§ trả §202 Accepted§, chưa thể coi checkout hoàn tất. Một sự kiện §OrderPlaced§ có thể dẫn đến §PaymentAuthorized§, §InventoryReserved§ và trạng thái terminal sau đó. Cảnh báo phải bám **định nghĩa success của domain**.

### 3.1. Từ hành trình đến SLI

| Hành trình / khả năng | Điều người dùng cần | SLI đo đúng nghĩa |
|---|---|---|
| Đăng nhập | Vào tài khoản hợp lệ | % login attempts hợp lệ có kết quả thành công hoặc lỗi xác thực rõ đúng hạn |
| Xem danh mục | Nhận dữ liệu sản phẩm | % requests hợp lệ phục vụ thành công dưới latency threshold |
| Đặt hàng | Đơn được tạo và có trạng thái rõ | % checkout workflows đạt outcome được chấp nhận trong deadline |
| Thanh toán | Thu tiền an toàn, không double charge | % payment intents đạt terminal outcome đúng hạn; số duplicate charges |
| Giữ hàng | Không bán vượt tồn | % orders giữ hàng hợp lệ; số oversell |
| Hoàn tiền | Tiền được hoàn trong cam kết | % refunds hoàn tất trong SLA; pending quá hạn |
| Giao hàng | Đơn giao đúng thời hạn hứa | % orders đủ điều kiện delivered đúng deadline |
| Thông báo | Khách được thông báo theo cam kết | % notifications delivered/accepted theo semantics của provider |

**SLI phải có tử số, mẫu số, cửa sổ thời gian và quy tắc loại trừ.** “Payment success” có thể đo mỗi HTTP request, mỗi attempt, payment intent hoặc mỗi order; các phép đếm này không tương đương.

### 3.2. User-visible failure khác business decline hợp lệ

Một giao dịch bị ngân hàng từ chối do không đủ tiền không nhất thiết là reliability failure của hệ thống thanh toán. Nhưng nếu Payment Service không trả về trạng thái từ chối rõ ràng đúng hạn, đó là reliability failure. Tách:

- **Technical failure:** timeout, 5xx, connection reset, event mất.
- **Business decline:** thẻ hết hạn, hết hàng, chính sách chống gian lận hợp lệ.
- **Uncertain outcome:** PSP đã nhận nhưng ứng dụng chưa biết thành công hay thất bại.
- **Compensated outcome:** thao tác ban đầu không thành, hệ thống đã hoàn tiền/hủy reservation an toàn.
- **User success:** quy trình đạt kết quả được cam kết.

Cần kết hợp reliability SLI với các chỉ số chất lượng kinh doanh; không ép một tỷ lệ “success” chứa mọi ý nghĩa.

## 4. SLI, SLO, SLA và error budget

- **SLI (Service Level Indicator):** số đo một thuộc tính dịch vụ, ví dụ tỷ lệ request tốt.
- **SLO (Service Level Objective):** mục tiêu SLI trong một cửa sổ, ví dụ 99,9% request checkout được xử lý đúng hạn trong 30 ngày.
- **SLA (Service Level Agreement):** thỏa thuận cam kết với hệ quả nếu không đạt; không đồng nhất với SLO nội bộ.
- **Error budget:** phần request/workflow được phép không đạt mục tiêu trong cửa sổ SLO.

Ví dụ SLO request-based:

\[
\text{AvailabilitySLI} =
\frac{\text{Good requests}}{\text{Eligible requests}}
\]

Nếu mục tiêu SLO là 99,9% trong 30 ngày thì tỷ lệ bad requests được phép là:

\[
1 - 0.999 = 0.001 = 0.1\%
\]

Với 1.000.000 requests đủ điều kiện trong cửa sổ, error budget tương đương 1.000 bad requests. Với dịch vụ có traffic ổn định, trực giác availability 99,9% của 30 ngày tương đương khoảng 43,2 phút outage toàn phần; **cách quy đổi này chỉ để hình dung**, vì SLO request-based không nhất thiết đo thời gian outage.

### 4.1. Tại sao alert theo error budget có ích?

Một tỷ lệ lỗi 1% có vẻ nhỏ hay lớn tùy SLO. Với SLO 99,9%, error rate 1% tiêu thụ budget nhanh gấp 10 lần tốc độ cho phép. Với SLO 95%, cùng error rate có thể vẫn trong mức mục tiêu. Burn rate biến câu hỏi “error rate có cao không?” thành “nếu tiếp diễn, budget sẽ bị ăn nhanh đến mức nào?”.

\[
\text{BurnRate} =
\frac{\text{Observed bad-event ratio}}
{1-\text{SLO target}}
\]

Ví dụ với target 99,9%:

| Bad-event ratio đang quan sát | Burn rate | Diễn giải |
|---|---:|---|
| 0,05% | 0,5× | Thấp hơn tốc độ budget cho phép |
| 0,1% | 1× | Bằng tốc độ budget theo mục tiêu |
| 0,6% | 6× | Tiêu thụ budget nhanh gấp sáu |
| 1,44% | 14,4× | Tiêu thụ budget rất nhanh |
| 10% | 100× | Sự cố nghiêm trọng |

Đây là tỷ lệ dựa trên cùng một SLI/denominator. Không dùng bảng này cho chỉ số như CPU utilization hoặc latency P99 nếu chưa biến chúng thành **good/bad event SLI** hợp lệ.

## 5. Nguyên tắc thiết kế cảnh báo có thể hành động

Một alert nên trả lời:

1. **Ai bị ảnh hưởng?** Người dùng, đối tác, nhóm khách hàng, luồng giao dịch, region hay tenant scope.
2. **Ảnh hưởng gì?** Không đăng nhập, checkout lỗi, tiền đã thu nhưng chưa xử lý, đơn giao trễ.
3. **Quy mô bao nhiêu?** Tỷ lệ, số lượng tuyệt đối, giá trị tiền/rủi ro, thời gian kéo dài.
4. **Mức cấp bách?** Còn bao lâu trước SLA breach, data loss hoặc rủi ro tài chính.
5. **Bằng chứng nào?** SLI/burn rate, dashboard, các metric kỹ thuật liên quan.
6. **Ai chịu trách nhiệm?** Service/domain owner, on-call rotation, escalation backup.
7. **Hành động đầu tiên?** Điều tra, rollback, hạn chế tải, disable flag, activate DR.
8. **Làm sao biết đã phục hồi?** User outcome và backlog trở lại mục tiêu, không chỉ Pod Ready.

Một **page** chỉ hợp lý khi cần người can thiệp khẩn cấp, có khả năng hành động và rủi ro đủ lớn. Nếu hành động chỉ có thể thực hiện vào giờ làm việc hoặc không có runbook hữu ích, alert có thể là ticket/email/report thay vì page.

### 5.1. Dấu hiệu cảnh báo chưa tốt

- Chỉ có tên §CPUHigh§ mà không nói service/region và ảnh hưởng.
- Không có owner, runbook hoặc dashboard.
- Cảnh báo nhấp nháy liên tục vì ngưỡng sát baseline.
- On-call thường xuyên acknowledge rồi bỏ qua.
- Alert được gửi dù hành vi là expected như batch peak.
- Cùng một outage gửi hàng trăm page từ Pod/instance và dependency.
- Incident nghiêm trọng xảy ra nhưng không có alert do chỉ đo tài nguyên.
- Một alert cứ còn active sau khi business outcomes đã phục hồi vì metric dư âm không cần hành động.

## 6. Tín hiệu nên page, nên ticket hay chỉ dashboard?

| Tín hiệu | Mức phản ứng thường phù hợp | Lý do |
|---|---|---|
| Checkout SLI bad nhanh, nhiều khách không đặt được | Page | Tác động hiện tại, cần xử lý ngay |
| Paid orders không có kết cục trong thời hạn, rủi ro charge | Page / escalation domain | Rủi ro tài chính và trust |
| Không có endpoint phục vụ ở một region quan trọng | Page | User-facing outage |
| API P99 vượt SLO kéo dài ở traffic đủ lớn | Page hoặc urgent tùy SLO | Trải nghiệm suy giảm |
| Disk dự báo đầy trong 20 phút | Page | Tác động sắp xảy ra, cần hành động |
| Certificate hết hạn trong 20 ngày | Ticket sớm, escalation theo deadline | Có thời gian xử lý |
| CPU 85% trong peak nhưng SLI khỏe, có headroom | Dashboard hoặc capacity ticket | Chưa có ảnh hưởng/hạn gần |
| Pod restart một lần sau rolling deploy | Dashboard | Có thể là hành vi deployment |
| Queue depth tăng nhưng oldest age vẫn dưới SLA và drain được | Dashboard/warning | Cần xét độ trễ nghiệp vụ, không chỉ số phần tử |
| Notification delivery failure khiến OTP không tới | Page | Một capability quan trọng bị mất |
| Một worker không quan trọng chậm 3 phút, SLA nhiều giờ | Ticket | Chưa cần đánh thức on-call |
| Telemetry mất trên dịch vụ cấp 1 | Monitoring page riêng | Mù quan sát có thể che outage |

Mức độ tùy hệ thống và chính sách. Ví dụ “notification” có thể là marketing email ít cấp bách, nhưng OTP hoặc cảnh báo gian lận là chức năng trọng yếu; dùng chung label §notification_failure§ để page sẽ không chính xác.

## 7. Phân loại mức độ nghiêm trọng theo tác động

Một mẫu severity dựa trên **blast radius, business criticality, thời gian và khả năng phục hồi**:

| Mức | Điều kiện minh họa | Phản ứng |
|---|---|---|
| **SEV1** | Checkout toàn vùng không hoạt động, data integrity/duplicate charge hoặc nguy cơ mất tiền lớn | Incident ngay, incident commander, page domain + platform |
| **SEV2** | Capability chính lỗi ở một phần đáng kể người dùng, burn rate cao kéo dài | Page owner, giảm tác động, cập nhật trạng thái |
| **SEV3** | Lỗi giới hạn phạm vi, có workaround và không có rủi ro ngay | Ticket ưu tiên, theo dõi |
| **SEV4** | Cảnh báo capacity, debt, xu hướng chưa ảnh hưởng SLO | Backlog/capacity planning |

Không tự gán severity chỉ dựa trên metric threshold. Một lỗi chiếm 0,1% traffic nhưng gây **double charge** có thể nghiêm trọng hơn 5% lỗi của một tính năng phụ không tạo side effect. Một thay đổi tác động một tenant chiến lược theo hợp đồng đặc biệt cũng có thể cần escalation dù tỷ lệ toàn hệ thống nhỏ.

### 7.1. Ma trận tác động

Có thể dùng bảng định tính:

| Chiều | Nhẹ | Vừa | Nặng |
|---|---|---|---|
| Người dùng | <1% route phụ | Một segment/region | Capability chính toàn vùng |
| Thời gian | Vài giây, tự hồi phục | Vượt latency target | Vượt SLA/RTO |
| Dữ liệu/tiền | Không side effect | Có backlog cần đối soát | Sai dữ liệu, mất tiền, duplicate charge |
| Workaround | Tự động | Có thao tác vận hành | Không có workaround |
| Khôi phục | Hệ thống tự cân bằng | Cần rollback | Cần incident phối hợp nhiều team |

Các ngưỡng phải được phê duyệt theo chính sách của tổ chức, không lấy ví dụ này như chuẩn toàn ngành.

## 8. Thiết kế multi-window, multi-burn-rate alerts

Alert chỉ dựa trên tỷ lệ lỗi 5 phút có thể nhấp nháy khi traffic thấp. Alert chỉ dựa trên một giờ có thể phát hiện chậm một outage nặng. **Multi-window, multi-burn-rate** kết hợp một cửa sổ dài xác định mức tiêu thụ budget và một cửa sổ ngắn xác nhận lỗi đang còn tiếp diễn.

Với SLO 99,9% trong 30 ngày, các ngưỡng minh họa:

| Tầng | Cửa sổ dài | Cửa sổ ngắn | Burn rate | Cách phản ứng |
|---|---|---|---:|---|
| Fast burn | 1 giờ | 5 phút | >14,4× ở cả hai | Page |
| Medium burn | 6 giờ | 30 phút | >6× ở cả hai | Page |
| Slow burn | 24 giờ | 2 giờ | >3× ở cả hai | Ticket/urgent review |

Ý nghĩa budget tiêu thụ nếu duy trì mức burn đó trên cửa sổ dài:

\[
\text{Budget fraction consumed} =
\text{burn rate} \times \frac{\text{window duration}}{\text{SLO duration}}
\]

Với 30 ngày = 720 giờ:

- 14,4× trong 1 giờ ≈ 2% budget.
- 6× trong 6 giờ ≈ 5% budget.
- 3× trong 24 giờ ≈ 10% budget.

Đây là ví dụ thiết kế; cần thay theo SLO, mục tiêu paging, volume, false-positive tolerance và workflow maturity. Các công thức đúng khi xét cùng good/bad-event definition và cửa sổ calendar/rolling tương thích.

### 8.1. Vì sao điều kiện “cả hai cửa sổ”?

Nếu một sự cố đã kết thúc, tỷ lệ lỗi trong cửa sổ dài có thể còn cao, nhưng cửa sổ ngắn đã bình thường; không nên tiếp tục đánh thức on-call về lỗi không còn diễn ra. Ngược lại, một spike 10 giây ở traffic nhỏ có thể làm cửa sổ ngắn đỏ nhưng chưa tiêu thụ đủ budget cửa sổ dài; nên chờ thêm bằng chứng trước khi page, trừ những bất biến tuyệt đối như double charge.

### 8.2. Burn-rate không thay thế absolute safeguards

Các sự cố đặc biệt nên có guardrail riêng:

- Xác nhận **duplicate charge** dù chỉ một giao dịch.
- Dữ liệu bị mất/hỏng hoặc cross-tenant data exposure.
- Bất kỳ đơn đã capture tiền nào không thể truy vết state.
- Certificate hoặc credential hết hạn rất gần gây outage chắc chắn.
- Không có telemetry cho toàn bộ một capability cấp 1.

Đừng dùng % error budget trên hàng triệu requests để che một lỗi tính đúng đắn tài chính hiếm nhưng nghiêm trọng.

## 9. Định nghĩa good/bad request trước khi viết PromQL

Giả sử Checkout API nhận request §POST /checkout§. Có thể định nghĩa:

- **Eligible:** request hợp lệ đã qua auth/validation, thuộc traffic người dùng thực được đo SLO.
- **Good:** service trả outcome đúng contract trong 800 ms hoặc latency target đã chọn.
- **Bad:** 5xx, timeout, lỗi không có kết quả hoặc response quá thời hạn.
- **Excluded:** health checks, synthetic probes, load test traffic hoặc các request không đủ điều kiện theo chính sách đã công bố.
- **Business decline:** ví dụ thẻ bị từ chối hợp lệ; có thể được tính good về reliability nếu phản hồi đúng và đúng hạn.

Không tự coi mọi 4xx là tốt; một số 4xx có thể là lỗi policy/auth sai của hệ thống. Nhưng cũng không tính mọi 4xx là failure; validation rejection có thể là hành vi đúng.

### 9.1. Metrics đề xuất

Một cách instrument:

~~~text
sli_checkout_requests_total{service="checkout",outcome="good|bad",region="apac"}
sli_checkout_duration_seconds_bucket{service="checkout",le="..."}
sli_payment_outcomes_total{outcome="authorized|declined|error|unknown"}
workflow_terminal_total{workflow="checkout",outcome="completed|failed|cancelled"}
workflow_stuck_paid_active{region="apac",state="payment_pending"}
workflow_oldest_pending_seconds{workflow="checkout",state="inventory_wait"}
workflow_compensation_pending{workflow="checkout"}
observability_data_freshness_seconds{source="payment-events"}
~~~

Đây là tên minh họa, không mặc định có sẵn từ Kubernetes/Spring Boot. Ưu tiên label **giá trị hữu hạn** như environment, region, route template, service, outcome và reason code. Không đưa §order_id§, §workflow_id§, email, token, user ID hoặc raw URL làm label metrics vì cardinality và quyền riêng tư.

## 10. PromQL cho SLI request reliability

Giả sử metric §sli_checkout_requests_total§ đã được instrument đúng nghĩa, mỗi request đủ điều kiện tăng **một lần** ở outcome §good§ hoặc §bad§.

### 10.1. Tỷ lệ bad requests trên 5 phút

~~~promql
sum(rate(sli_checkout_requests_total{
  service="checkout",
  outcome="bad"
}[5m]))
/
sum(rate(sli_checkout_requests_total{
  service="checkout"
}[5m]))
~~~

Mẫu số có thể bằng 0 khi không có traffic, trả NaN/không có giá trị có nghĩa. Không tự ép §0/0§ thành 0% lỗi rồi kết luận hệ thống khỏe; cần trạng thái “no traffic” hoặc một điều kiện riêng.

### 10.2. Burn rate với target 99,9%

~~~promql
(
  sum(rate(sli_checkout_requests_total{
    service="checkout",outcome="bad"
  }[5m]))
  /
  sum(rate(sli_checkout_requests_total{
    service="checkout"
  }[5m]))
)
/ 0.001
~~~

Số 0,001 là budget fraction của 99,9% SLO, không phải một ngưỡng chung cho mọi service. Để triển khai production, tạo recording rules cho tỉ lệ lỗi theo cửa sổ 5m, 30m, 1h, 2h, 6h, 24h để PromQL và alert dễ đọc.

### 10.3. Fast burn: điều kiện hai cửa sổ

Với recording rules giả định:

~~~promql
checkout:sli_bad_ratio:1h > 0.0144
and
checkout:sli_bad_ratio:5m > 0.0144
~~~

Khi target 99,9%, bad ratio 0,0144 tương đương 14,4× error budget rate. Nếu recording rules có label region/payment_method, phải đảm bảo hai vector được match đúng label; có thể dùng §on(...)§/§ignoring(...)§ khi cần. Quyết định aggregate trên toàn vùng hoặc theo vùng dựa trên SLO và incident policy, tránh aggregate quá rộng che lỗi nhỏ nhưng nghiêm trọng.

### 10.4. Ví dụ PrometheusRule

~~~yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: checkout-slo-alerts
spec:
  groups:
    - name: checkout-slo
      rules:
        - alert: CheckoutHighErrorBudgetBurn
          expr: |
            checkout:sli_bad_ratio:1h > 0.0144
            and
            checkout:sli_bad_ratio:5m > 0.0144
          for: 2m
          labels:
            severity: page
            service: checkout
            owner: checkout-team
          annotations:
            summary: "Checkout is burning error budget rapidly"
            description: "User-visible checkout failures exceed the 14.4x burn threshold."
            runbook_url: "https://runbooks.example.invalid/checkout-slo"
~~~

Manifest yêu cầu Prometheus Operator tương ứng và recording rules đã tồn tại. URL là placeholder. §for: 2m§ yêu cầu điều kiện tiếp diễn tối thiểu hai phút; trong outage rất nghiêm trọng có thể cần giảm độ trễ, nhưng phải cân bằng alert noise. Mẫu này chưa bao gồm routing, labels theo region, no-data behavior hoặc low-traffic guard.

### 10.5. Một bẫy thường gặp khi dùng §rate§

Một request mất 10 giây chưa hoàn thành có thể chưa tăng counter outcome tới lúc kết thúc; trong một outage nơi mọi request treo, bad ratio đo từ completed requests có thể **đến chậm**. Cần thêm timeout/cancellation event, in-flight age, queue age hoặc synthetic transaction SLI. Đừng coi tỉ lệ lỗi dựa trên response hoàn tất là toàn bộ bức tranh.

## 11. Cảnh báo latency theo trải nghiệm thay vì CPU

Latency-based SLO thường được thiết kế bằng **good/bad events**:

\[
\text{LatencySLI} =
\frac{\text{requests hoàn tất dưới threshold}}
{\text{eligible requests}}
\]

Ví dụ 99% requests đủ điều kiện phải nhận outcome trong 800 ms. Nếu app tạo histogram latency:

~~~promql
sum(rate(http_server_requests_seconds_bucket{
  uri="/api/checkout",le="0.8"
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  uri="/api/checkout"
}[5m]))
~~~

Cú pháp metric/label tùy exporter/framework và histogram bucket được cấu hình. Chỉ sử dụng bucket §le="0.8"§ nếu đúng là có bucket đó hoặc một ngưỡng tương ứng. Nếu endpoint xuất Prometheus/OpenTelemetry qua Micrometer, xác minh tên metric thực và route template; đừng để raw URL path tạo cardinality cao.

### 11.1. Tại sao không page chỉ vì P99 lớn?

P99 rất hữu ích để điều tra, nhưng với số mẫu thấp có thể dao động mạnh; một request 20 giây trong 10 requests có thể làm P99 xấu. Nếu người dùng thực sự bị ảnh hưởng theo SLO, alert dựa trên tỷ lệ requests vượt thời hạn và volume thường rõ hơn. Dùng P99 trong dashboard và alert nơi nó phản ánh đúng experience contract, kèm minimum sample/traffic guard.

### 11.2. Khi throughput thấp

Một API chỉ có 10 requests/giờ có thể nhận 1 lỗi gây tỷ lệ 10%, nhưng chưa chắc đủ để kết luận outage diện rộng. Có thể dùng:

- Một điều kiện minimum eligible events.
- Synthetic probes từ nhiều location.
- Absolute bad-event count và cửa sổ dài hơn.
- State-based alert cho công việc chưa hoàn tất.
- Alert riêng cho high-value transaction/data integrity.
- Policy “unknown/no traffic” phân biệt với healthy.

Không được “chặn mọi alert ít traffic” nếu một lỗi đơn lẻ gây mất tiền hoặc vi phạm cam kết quan trọng.

## 12. Cảnh báo cho quy trình bất đồng bộ

Hệ thống event-driven có thể trả 202 Accepted và làm việc phía sau. Chỉ số request 2xx rất dễ đánh lừa on-call. Với workflow, cần đo trạng thái bền vững:

- Distinct workflows bắt đầu và đạt terminal outcome.
- Số §PAID§ chưa §INVENTORY_RESERVED§ quá thời hạn.
- §oldest_age§ của item đang chờ, không chỉ queue depth.
- Số compensation/refund pending quá SLA.
- Tốc độ backlog tăng hay giảm khi traffic thay đổi.
- Tỷ lệ event ingestion failure và dead-letter queue.
- Thời gian từ event xảy ra đến khi consumer áp dụng.
- Khoảng thời gian từ start đến terminal outcome theo cohort.

### 12.1. Queue depth không luôn là tác động

Giả sử một queue có 50.000 email marketing, consumer xử lý 5.000 emails/phút, SLA gửi trong 30 phút, oldest age 8 phút và throughput ổn định. Queue depth cao nhưng không đòi page.

Ngược lại queue chỉ có 30 messages nhưng tất cả là §PaymentCaptured§ cần xác nhận tồn kho trong 15 giây, oldest age 3 phút: ảnh hưởng rõ ràng. Cảnh báo nên dựa trên **độ tuổi công việc, trạng thái nghiệp vụ, deadline và khả năng drain**.

### 12.2. Dùng thời gian theo trạng thái, không chỉ broker lag

Một message có thể đã được consumer ACK nhưng workflow vẫn stuck vì DB transaction lỗi hoặc PSP callback không về. Metric §consumer_lag§ giảm không chứng minh order đã hoàn tất. Tạo durable workflow projection để đếm §workflow_stuck_paid_active§ và §workflow_oldest_pending_seconds§; khi Pod restart, gauge phải được tái dựng từ nguồn dữ liệu bền vững.

### 12.3. Ví dụ rule cho đơn đã thu tiền bị kẹt

~~~yaml
- alert: PaidOrdersStuckAfterInventoryDeadline
  expr: workflow_stuck_paid_active{region="apac"} > 20
  for: 3m
  labels:
    severity: page
    service: checkout
    owner: order-team
  annotations:
    summary: "Paid orders are not reaching inventory outcome"
    description: "More than 20 paid orders exceed the inventory deadline."
    runbook_url: "https://runbooks.example.invalid/paid-orders"
~~~

Ngưỡng 20 và ba phút là minh họa. Trong hệ thống có volume thấp hoặc giá trị đơn cao, một đơn stuck có thể đã đủ điều kiện incident. Cần quyết định xem “stuck” là paid orders chưa terminal theo tuổi, workflow cần reconcile hay case đã có owner; không đếm trùng event.

### 12.4. SLO của workflow dài ngày

Giao hàng có thể kéo dài nhiều ngày. Không lấy số đơn giao hôm nay chia số đơn đặt hôm nay rồi page conversion. Dùng **matured cohorts** đã đủ thời gian quan sát, hoặc metric active-state với deadline. Cho các hành trình có user-visible latency trong vài giây và business completion nhiều ngày, nên có hai SLO khác nhau.

## 13. Cảnh báo theo rủi ro dữ liệu và tiền

Một số bất biến nghiệp vụ cần alert riêng, có thể nghiêm trọng dù không vượt tỷ lệ lỗi toàn hệ thống:

| Bất biến | Điều đo | Phản ứng |
|---|---|---|
| No duplicate charge | PSP charges trùng logical payment intent | Page an ninh/tài chính hoặc Payment on-call |
| No oversell | Reservations vượt available theo contract | Incident, hạn chế thao tác ghi, đối soát |
| No lost paid order | Captured payments không có order/recovery record | Page, reconciliation |
| Cross-tenant data isolation | Truy cập dữ liệu sai tenant đã xác nhận | Security incident |
| Audit log không được mất | Critical action thiếu audit trail | Escalation compliance/security |
| Refund theo cam kết | RefundPending vượt deadline | Page/ticket tùy SLA và số lượng |
| Data freshness | Projection/ledger lag vượt ngưỡng quyết định | Alert khi quyết định tài chính bị ảnh hưởng |

Cảnh báo **không nên tự động hoàn tiền hoặc thu lại tiền** khi chưa có giao thức an toàn. Runbook cần kiểm payment intent, provider state, idempotency key và ledger trước khi thao tác; phản ứng vội có thể tạo side effect kép.

## 14. Resource alerts: khi nào thật sự cần đánh thức?

Cảnh báo tài nguyên có hai vai trò:

1. **Supporting evidence:** CPU, memory, lock waits, pool starvation giải thích một SLI bị ảnh hưởng.
2. **Predictive guardrails:** tài nguyên sắp cạn trong thời gian không đủ để xử lý bằng ticket.

### 14.1. Disk usage

“Disk > 80%” không nói đủ. Một ổ 1 TB còn 200 GB có thể dùng được nhiều tuần, còn ổ 10 GB tăng 1 GB/phút sẽ đầy sớm dù mới 70%. Kết hợp dung lượng còn lại và xu hướng tăng.

Ví dụ PromQL cho node filesystem, cần lọc filesystem phù hợp và loại pseudo-filesystems:

~~~promql
predict_linear(
  node_filesystem_avail_bytes{
    mountpoint="/var/lib/app"
  }[2h],
  3600
) < 0
~~~

Truy vấn dự báo filesystem availability sau 1 giờ dưới 0 dựa trên xu hướng hai giờ. Đây là mô hình tuyến tính đơn giản, có thể nhiễu khi workload bursty, mountpoint đổi hoặc disk usage nhảy bậc; kết hợp absolute free bytes và trend validation trước khi page.

### 14.2. Certificate và secret expiry

Nếu certificate hết hạn trong 24 giờ và rotation thất bại, outage là gần như chắc chắn. Page/urgent escalation hợp lý dù traffic hiện vẫn tốt. Với cảnh báo từ sớm (ví dụ 30 ngày), dùng ticket và escalation theo deadline. Quan trọng là alert tạo hành động cụ thể và đủ lead time.

### 14.3. Memory và OOM

Memory 85% không nhất thiết xấu nếu page cache hoặc JVM heap được quản lý. Cần nhìn OOM risk, working set, GC pause, allocation rate, limit, leak trend và latency/error. Nếu OOMKill lặp lại đang làm request fail hoặc rollout không đủ capacity, page dựa trên availability/impact và nguyên nhân OOM.

### 14.4. CPU

CPU cao có thể là tận dụng tài nguyên hiệu quả. Cần quan sát throttling, request queue wait, latency, HPA headroom, node capacity và error. Khi CPU 90% nhưng throughput và SLO ổn định, ticket capacity có thể đủ; khi CPU throttling kéo P99 vượt SLO, đó là incident user impact.

### 14.5. DB connection pool

Pool utilization 95% có thể bình thường ở burst ngắn; khi threads bị chặn chờ connection và request latency vượt SLO, impact rõ. Một DB dùng chung quá tải có thể ảnh hưởng nhiều service; nên group alert theo root cause và vẫn hiển thị những user journeys bị ảnh hưởng.

## 15. Dependency outage và common-mode failure

Giả sử Payment Service gọi PSP. PSP chậm/timeout, các Pod vẫn live, CPU thấp, DB bình thường nhưng khách không thể checkout. Cần:

- SLI của payment intent: terminal outcome đúng thời hạn.
- Error/timeout rate theo provider và payment method.
- Circuit breaker state, retry attempts, backoff và in-flight operations.
- Số payment attempts có kết quả không rõ.
- Khả năng dùng provider dự phòng/đường degrade hợp lệ.
- Mức ảnh hưởng ở Order checkout success.
- Escalation tới PSP và người chịu trách nhiệm đối soát.

Một sự cố DB dùng chung có thể khiến Order, Inventory và Billing đồng loạt page; cần grouping và inhibition để tránh **alert storm**, nhưng không làm mất visibility tác động của từng capability.

### 15.1. Không restart mọi Pod khi dependency lỗi

Liveness probe không nên phụ thuộc trực tiếp tới DB/PSP. Nếu PSP lỗi và liveness fail, mọi Pod restart chỉ tăng cold start, retry storm và trì hoãn recovery. Readiness có thể tùy thiết kế khi dependency cốt lõi mất, nhưng vẫn cần xử lý timeout, circuit breaker và traffic shedding ở application.

### 15.2. Alert có thể là dẫn xuất của nhiều tín hiệu

Ví dụ:

- Page nếu checkout burn rate nhanh và PSP timeout tăng.
- Vẫn page checkout burn rate dù PSP timeout không tăng, vì nguyên nhân có thể khác.
- PSP timeout tăng nhưng checkout có provider fallback và user SLI khỏe: ticket hoặc warning tùy khả năng chịu lỗi.
- PSP credential sẽ hết hạn trong vài giờ: urgent alert dù user SLI hiện khỏe.

Đừng làm alert user impact **phụ thuộc tuyệt đối** vào một metric nguyên nhân; nếu giả thuyết nguyên nhân sai, alert sẽ bỏ lỡ outage.

## 16. SLO aggregation và các chiều phân tích

Metric aggregate toàn hệ thống có thể che sự cố ở một vùng hoặc phân khúc nhỏ.

Ví dụ: tổng checkout success là 99,95% nhưng region EU chỉ 90% trên 0,5% traffic. Aggregate global vẫn gần xanh, trong khi EU khách hàng bị ảnh hưởng lớn. Nên thiết kế:

- SLO toàn service/capability.
- SLO theo region khi region là failure domain.
- SLO theo payment provider hoặc method nếu có giá trị vận hành.
- SLO theo tier/tenant khi có hợp đồng khác biệt và số liệu đủ tin cậy.
- Guardrail cho high-value, fraud/data integrity risk.

Tránh tạo hàng nghìn alert per user/tenant tùy ý. Cardinality làm chi phí tăng, on-call quá tải và có thể rò thông tin nhạy cảm. Có thể dùng group theo §region§, §channel§, §payment_method_family§ và dùng warehouse/logs để drill down ID chi tiết.

### 16.1. Traffic mix và Simpson's paradox

Conversion toàn hệ thống có thể giảm vì tỷ trọng traffic của kênh khó chuyển đổi tăng, dù conversion trong mỗi kênh không đổi. Khi dùng business outcome làm alert, cần phân biệt seasonal baseline, campaigns, payment method distribution và release cohort. SLI reliability nên được thiết kế để hạn chế nhầm lẫn giữa **business behavior change** và **platform unreliability**.

## 17. Low traffic, missing data và synthetic probes

### 17.1. Low traffic

Nếu service chỉ nhận 20 requests mỗi giờ, một lỗi tạo 5% bad ratio. Cần xét risk của lỗi và số mẫu. Dùng cửa sổ dài hơn, synthetic checks, absolute count, hoặc alert theo state cho workflows quan trọng. Không đặt minimum traffic guard khiến mọi outage của dịch vụ ít sử dụng bị bỏ qua.

### 17.2. No traffic khác no errors

Một service không nhận request có thể do nhu cầu thấp, gateway routing lỗi, DNS sai, exporter mất hoặc pipeline metric hỏng. Không có series §http_requests_total§ không chứng minh 100% availability. Cần tín hiệu traffic expectation, black-box probe, scraper health và routing tests.

### 17.3. Synthetic monitoring

Một transaction giả chạy từ ngoài hệ thống có thể phát hiện DNS/ingress/auth/checkout lỗi ngay cả khi traffic người dùng thấp. Cần:

- Account/test data riêng, không phát sinh charge/giao hàng thật.
- Kịch bản đại diện các đường quan trọng, không chỉ §GET /health§.
- Nhiều location/failure domains để tránh alert vì một điểm đo lỗi.
- Alert theo quorum hoặc mức độ tác động thật.
- Theo dõi quota, rate limits và phụ thuộc sandbox.

Synthetic success không bảo đảm mọi cohort khách hàng đều tốt; kết hợp với real-user metrics và durable business events.

### 17.4. Data freshness

Một metric pipeline ngừng cập nhật có thể khiến dashboard giữ giá trị cũ. Giám sát §last_successful_event_ingestion§, scrape failures, gaps và age của workflow projection. Nếu mù quan sát trên capability quan trọng, phải có alert riêng và quy trình xác minh thay thế.

## 18. Nhiễu cảnh báo: dedup, grouping, inhibition, silence

Một outage duy nhất có thể tạo:

- 20 alerts từ từng Pod restart.
- 5 alerts từ CPU/connection pool.
- 3 alerts do service A/B/C timeout.
- 1 alert checkout user impact.

Nếu tất cả cùng page một on-call, nhóm mất thời gian phân biệt triệu chứng và root cause. Cần tổ chức alert có chiến lược.

### 18.1. Grouping

Nhóm các alert có chung service, environment, region, incident class hoặc dependency. Gửi một notification chứa các affected capabilities và tình trạng, thay vì page theo từng Pod instance.

### 18.2. Deduplication

Khi một incident tiếp tục diễn ra, không tạo page mới mỗi chu kỳ scrape. Dùng stable labels/fingerprint và notification policy. Một alert đổi labels động mỗi phút sẽ phá dedup; đừng đưa timestamp, order ID, exception message hoặc raw URL vào labels.

### 18.3. Inhibition

Khi đã có alert §RegionIngressDown§ đáng tin, các alert per-Pod §UpstreamRequestFailed§ có thể bị suppress ở kênh paging nhưng vẫn hiện trong dashboards/incident details. Tránh rule inhibition quá rộng che một sự cố độc lập.

### 18.4. Silence / maintenance windows

Trong planned deployment, có thể silence alerts kỹ thuật đã dự kiến theo thời gian, owner và scope. **Không silence mọi business impact** một cách rộng rãi: rollout có thể gây lỗi thật và cần dừng. Mọi silence nên có hạn, lý do và audit.

### 18.5. Escalation và routing

Mỗi alert phải có service owner và backup on-call. Rủi ro dữ liệu/tiền có thể cần Payment, Finance hoặc Security; capacity ticket có thể tới Platform. Có quy tắc escalation nếu người đầu tiên không phản hồi và kênh liên lạc dự phòng cho hệ thống alerting lỗi.

## 19. Thiết kế payload cảnh báo cho on-call

Một notification nên chứa:

~~~text
TITLE: Checkout fast error-budget burn – APAC
Severity: SEV2 / Page
Service: checkout
Impact: 6.2% eligible checkout attempts failed in past 10 min
Scope: APAC, mobile and web, primary payment path
Evidence: SLO 99.9%; burn rate >14.4x at 1h and 5m
Started: 02:14 UTC
Suspected context: PSP timeout increase, deploy R42 at 02:08 UTC
Dashboard: https://dashboards.example.invalid/checkout
Runbook: https://runbooks.example.invalid/checkout
Owner: checkout-oncall
First action: Confirm SLI freshness and whether R42 is a factor
Recovery: SLI burn falls, pending paid orders reconcile, backlog drains
~~~

Các URL, số liệu và timestamp ở đây chỉ là ví dụ. Không đưa PII, raw token, order ID hoặc secret vào notification. Nếu dữ liệu evidence chưa xác nhận, ghi “suspected” thay vì khẳng định nguyên nhân.

### 19.1. Alert title theo triệu chứng tác động

Tên nên đủ ổn định để grouping:

- §CheckoutHighErrorBudgetBurn§
- §PaymentsUnknownOutcomeBacklog§
- §PaidOrdersStuckBeyondDeadline§
- §InventoryReservationSLOBreach§
- §CriticalTelemetryMissing§
- §DiskWillFillBeforeResponseWindow§

Tránh tên như §BadThingsHappening§ hoặc §CPUOver80Pod-123§. Ngay trong tên đã nên thấy capability hoặc tác động.

## 20. Runbook: từ alert tới quyết định xử lý

Một runbook tốt không chỉ nói “kiểm logs”. Nó đưa **thứ tự kiểm tra, ranh giới an toàn và điều kiện phục hồi**.

### 20.1. Mẫu runbook

1. **Xác minh tín hiệu:** metric có mới không, numerator/denominator đủ mẫu không, có maintenance không?
2. **Định lượng impact:** bao nhiêu users/workflows/regions bị ảnh hưởng, đang tăng hay giảm, có rủi ro data/money không?
3. **Xác định thời điểm bắt đầu:** đối chiếu deploy, config, flag, provider incident, scaling, network changes.
4. **Khoanh vùng:** một route, một region, một provider hay mọi service?
5. **Xem triệu chứng kỹ thuật:** 5xx, timeout, traces, queue lag, saturation, dependency health.
6. **Giảm tác động:** rollback, disable flag, failover, rate limit hoặc load shedding đúng contract.
7. **Bảo vệ dữ liệu:** không retry thanh toán mù; đối soát attempts và bảo đảm idempotency.
8. **Theo dõi phục hồi:** SLI ổn định, backlog drain, terminal workflows hoàn tất, error budget burn giảm.
9. **Cập nhật incident:** trạng thái, owner, timeline, next action và khách hàng bị ảnh hưởng.
10. **Post-incident:** sửa detection, docs, capacity, tests, alert noise và root cause.

### 20.2. Hành động khác nhau theo loại cảnh báo

| Loại | Hành động đầu tiên | Cấm suy luận vội |
|---|---|---|
| Checkout burn | Kiểm error trend, release, PSP/DB dependency | CPU thấp nghĩa không có outage |
| Paid orders stuck | Đối soát Payment/Inventory workflow states | Timeout nghĩa chưa charge |
| High DB lock wait | Kiểm transaction/query/slow request | Tăng replica API chắc sẽ tốt |
| Queue age beyond SLA | Kiểm producer/consumer/poison event | Queue depth cao luôn có lỗi |
| Disk forecast | Kiểm mount, growth, retention, cleanup an toàn | Xóa ngẫu nhiên logs hoặc DB files |
| Certificate expiry | Xác minh owner, renewal path, expiry và rollout | Đợi tới lúc hết hạn mới xử lý |
| Telemetry missing | Kiểm collector, scrape, exporter, synthetic | No errors == healthy |

## 21. Cảnh báo trong quá trình triển khai

Một phiên bản mới có thể làm regression trước khi CPU hoặc memory thay đổi đáng kể. Kết hợp progressive delivery với impact SLI:

~~~mermaid
flowchart TD
    A[Deploy canary revision] --> B[Route limited production traffic]
    B --> C[Measure user and business SLIs]
    C --> D{SLO / guardrails within bounds?}
    D -->|Yes| E[Increase canary exposure]
    E --> C
    D -->|No| F[Stop rollout]
    F --> G[Rollback / disable flag]
    G --> H[Verify SLI and workflow recovery]
~~~

Một canary 1% traffic có thể không đủ số mẫu để kết luận trong năm phút, đặc biệt ở endpoint hiếm. Có thể bổ sung synthetic tests, functional assertions hoặc kéo dài thời gian. Đừng tự động tiếp tục rollout chỉ vì “không có alert” khi metric thiếu dữ liệu.

### 21.1. Tách alert phục vụ deployment gate và alert page

Một signal có thể đủ để **pause canary** nhưng chưa đủ để page toàn công ty. Ví dụ tăng 2% error rate ở cohort 1% traffic có thể là lý do rollback nhanh tự động; alert tổng toàn hệ thống vẫn chưa vượt ngưỡng paging. Tạo các ngưỡng cho quyết định khác nhau, không ép một alert làm mọi việc.

### 21.2. Alert context cần version

Gắn app version, config revision, feature flag revision, region và deployment generation vào release events và dashboard. Không cần nhét các giá trị động này vào mọi time-series label nếu gây cardinality; có thể dùng annotations hoặc incident context. Khi triệu chứng bắt đầu sau release, đó là giả thuyết, không phải bằng chứng nguyên nhân nếu chưa kiểm tra.

## 22. Alerting cho dependencies và shared platform

Khi DB hoặc gateway chung lỗi, hàng chục services có thể bị ảnh hưởng. Một hệ thống paging tốt cần:

- Một alert root-level đủ rõ về dependency.
- Những impact SLI của các capabilities vẫn được quan sát, không bị xóa.
- Routing cho platform owner và domain owner đúng mức.
- Grouping theo failure domain: region/cluster/provider.
- Inhibition chỉ suppress duplication, không che các sự cố độc lập.
- Trang incident tổng hợp timeline và blast radius.

Ví dụ mất DB gây checkout và inventory errors. Platform cần sửa DB; Order/Payment cần xử lý workflow dở dang, đối soát và trả kết quả cho người dùng. Có thể một incident commander điều phối thay vì ba nhóm cùng page không có phối hợp.

## 23. Thời điểm cảnh báo: delay, §for§ và hysteresis

Một metric ngắn hạn có thể dao động quanh ngưỡng, tạo flapping. Có thể dùng:

- **§for§ duration:** điều kiện phải kéo dài trước khi fire.
- **Multi-window conditions:** cửa sổ dài và ngắn cùng vượt.
- **Hysteresis:** ngưỡng vào/ra khác nhau nếu alert logic hỗ trợ.
- **Min samples:** tránh tỷ lệ 100% từ một request không quan trọng.
- **Grouping/dedup:** giảm notification lặp.
- **Seasonal baseline:** áp dụng cho throughput/conversion khi lịch giao dịch biến động.
- **Deadlines:** workflow state age vượt SLA đúng nghĩa.

Đừng thêm delay tùy ý làm alert đến quá muộn. Nếu một chứng chỉ còn 10 phút sẽ hết hạn hoặc đã xảy ra double charge, xử lý khẩn ngay có thể đúng. Sự cân bằng giữa detection delay và false positives phải dựa trên tác động.

### 23.1. Observability latency

Phát hiện phụ thuộc vào:

\[
T_{\text{detect}} =
T_{\text{event}} + T_{\text{ingest}} + T_{\text{evaluate}} + T_{\text{for}} + T_{\text{notify}}
\]

Các thành phần có thể chồng nhau tùy pipeline; đây là mô hình tư duy, không nhất thiết tổng cộng chính xác. Nếu event được ghi vào warehouse sau 15 phút, không thể kỳ vọng alert realtime trong 30 giây nếu chỉ dựa vào báo cáo warehouse. Cần instrument operational SLI ở đường nhanh và dùng reconciliation/reporting ở đường bền vững cho business correctness.

## 24. Chi phí và độ tin cậy của hệ thống cảnh báo

Alerting system cũng cần SLO vận hành:

- Prometheus/metric pipeline có đang scrape đủ targets?
- Alert manager có gửi notification không?
- Escalation tới người trực có được xác nhận không?
- Nếu metric pipeline lỗi, có black-box/synthetic monitor độc lập không?
- Có quá nhiều alerts cùng lúc khiến notification rate limit không?
- Runbook URL có truy cập được trong lúc nội bộ network outage?
- Có fallback channel khi paging provider lỗi không?

Trong một outage lớn, giám sát nội bộ phụ thuộc cùng cluster/DB có thể chết theo hệ thống chính. Tùy mức độ quan trọng, dùng external synthetic checks hoặc đường thông báo độc lập.

### 24.1. Alert fatigue là rủi ro thực tế

Nếu on-call nhận 80 pages mỗi tuần và 70 pages không cần hành động, xác suất bỏ qua sự cố quan trọng tăng lên. Ghi và cải tiến:

- Số pages mỗi ca trực.
- Tỷ lệ actionable pages.
- Tỷ lệ repeated/flapping.
- Time-to-acknowledge, time-to-mitigate.
- Số user-impact incidents không được alert phát hiện sớm.
- Các alert phải silence thủ công.
- Tỷ lệ incident do monitoring/noise so với root user impact.
- Số runbook stale hoặc không có owner.

Giảm alert noise không có nghĩa tắt hết cảnh báo; mục tiêu là **on-call tin được tín hiệu quan trọng**.

## 25. Thiết kế dashboard hỗ trợ alert theo tác động

Một dashboard hữu ích có ba lớp:

### 25.1. Lớp user experience và SLO

- Eligible requests/workflows và bad-event ratio.
- Error budget remaining và burn rate.
- Latency/availability SLI, theo region/route quan trọng.
- Business completion, paid orders stuck, refund pending.
- Synthetic transaction success và data freshness.

### 25.2. Lớp service / workflow

- Request/error rate, P95/P99.
- Queue oldest age, backlog và terminal throughput.
- Retry/circuit breaker, failure reasons.
- Dependency latency/errors.
- Active workflow state và compensation.

### 25.3. Lớp infrastructure

- CPU, throttling, memory, OOM, GC.
- DB connections, lock waits, disk and IOPS.
- Broker lag/partition skew, DLQ.
- Pod/node status, autoscaling, restarts.
- Network and gateway health.

**Đặt tác động ở trên cùng, nguyên nhân ở dưới.** Khi mở từ alert, on-call nên thấy ngay user impact và một đường drill down đủ ngắn để tìm bằng chứng kỹ thuật.

## 26. Trường hợp áp dụng: checkout outage nhưng CPU bình thường

### 26.1. Tình huống

Lúc 10:00, PSP gặp lỗi kết nối. Payment Service timeout khi gọi authorize; API Gateway vẫn có CPU 25%; Order Pod vẫn Ready. Gateway có thể trả §202§ cho nhiều request, nhưng order không tiến tới terminal outcome.

**Alert tài nguyên sai:** không page vì CPU/memory không quá ngưỡng.

**Alert impact đúng:** trong 5 phút, số payment intents chưa có outcome vượt deadline tăng, checkout bad ratio vượt fast burn và paid orders stuck tăng.

### 26.2. Hành động

1. Xác minh metric freshness và traffic/eligible denominators.
2. Phân tích theo payment method/region/provider.
3. Kiểm PSP timeout, circuit breaker, retry attempts, error budget burn.
4. Ngừng retry vô hạn, áp budget/backoff và failover nếu hợp đồng cho phép.
5. Không tạo charge mới cho payment attempts chưa rõ kết quả.
6. Liên hệ PSP/đối soát, đồng thời thông báo user trạng thái phù hợp.
7. Theo dõi terminal outcomes và paid-order backlog sau khi PSP phục hồi.
8. Xác minh completion, not just HTTP 200 hoặc CPU.

### 26.3. Bài học

Một metric tài nguyên không thể suy ra tác động nếu bottleneck nằm ngoài ứng dụng hoặc trong chuỗi workflow async. SLO-based paging và business state metrics cần được thiết kế từ đầu.

## 27. Trường hợp áp dụng: CPU 95% nhưng không cần page

### 27.1. Tình huống

Một service recommendation chạy batch preprocessing lúc 2 giờ sáng. CPU 95%, memory ổn định, không OOM, online request latency và error trong SLO, batch dự kiến hoàn tất trong 20 phút.

**Alert CPU>80% page:** tạo false positive, phá giấc ngủ on-call nhưng không có hành động hữu ích.

### 27.2. Thiết kế tốt hơn

- Giữ resource metrics trên dashboard và đặt capacity warning theo headroom.
- Page nếu online recommendation latency/error vượt SLO, hoặc batch sắp trễ deadline quan trọng.
- Nếu high CPU kéo dài kèm memory pressure, ETA/forecast vượt mức, tạo ticket hoặc escalation phù hợp.
- Tách workload batch và online bằng quotas/bulkheads/scheduling nếu cạnh tranh gây ảnh hưởng.
- Khi batch kết thúc, xác minh KPI và resource trend.

**CPU cao là một nguyên nhân tiềm năng, không phải mặc định là một incident.**

## 28. Trường hợp áp dụng: queue depth cao nhưng khách vẫn ổn

### 28.1. Tình huống

Notification Service có 100.000 emails marketing chờ gửi, nhưng throughput 10.000/phút, oldest age bảy phút, SLA gửi trong một giờ. Không có OTP hoặc thông báo giao dịch bị trễ.

Một alert §queue_depth > 50_000§ sẽ page không cần thiết. Alert nên xét §oldest_age§, per-message-class SLA, drain rate, failure rate và tách các queue theo criticality.

### 28.2. Biến thể nguy hiểm

Nếu cùng queue chứa OTP với deadline 30 giây và oldest age 90 giây, người dùng không đăng nhập được. Cần tách queue/workers hoặc ưu tiên hợp lý; alert theo OTP completion SLI, không theo tổng queue depth.

## 29. Trường hợp áp dụng: ít lỗi nhưng rủi ro tiền lớn

Một payment intent bị capture hai lần do client retry sau timeout. Dù hệ thống xử lý một triệu requests/ngày và lỗi chỉ là một case, đây vẫn là **vi phạm bất biến** cần escalation.

Thiết kế:

- Durable metric/event cho duplicate side effect đã xác nhận.
- Phương pháp đối soát PSP, payment attempts và ledger.
- Alert tức thời tới Payment + Finance/Incident theo policy.
- Runbook khóa đường gây duplicate, tránh tự refund cả hai mà chưa kiểm trạng thái.
- Post-incident thêm idempotency test, unique constraints và replay checks.
- Không lấy “error rate < 0.1%” làm lý do bỏ qua sự cố integrity.

## 30. Quản trị metric definition

Một SLI được dùng để page phải có owner và tài liệu:

| Trường | Nội dung |
|---|---|
| Metric name | §checkout_request_reliability§ |
| Definition | Eligible attempts nhận kết quả kỹ thuật đúng hạn |
| Numerator | Good attempts |
| Denominator | All eligible attempts |
| Window | Rolling 30 days cho SLO; 5m/1h/6h cho alert |
| Target | 99,9% minh họa |
| Exclusions | Health probes, internal synthetic traffic tùy chính sách |
| Low traffic behavior | Synthetic + minimum count + severity rules |
| Data source | Gateway/app metrics đã được đối soát |
| Owner | Checkout team |
| Routing | Checkout on-call, backup platform |
| Runbook | URL và phiên bản cập nhật |
| Change governance | Review khi thay numerator/denominator hoặc instrumentation |

Thay đổi định nghĩa eligible request có thể làm metric tốt hơn hoặc xấu đi mà hệ thống không thay đổi. Vì vậy metric definitions cần versioning và annotation trên dashboard, kèm thời điểm schema/contract thay đổi.

### 30.1. Không tự tối ưu để “qua alert”

Một số phản tác dụng thường gặp:

- Bỏ các requests chậm khỏi denominator.
- Chuyển 5xx thành 200 với body báo lỗi rồi coi là success.
- Đưa tất cả requests vào async queue để trả 202 nhanh nhưng không đo completion.
- Tăng timeout vô hạn để giảm 5xx nhưng làm người dùng chờ lâu hơn.
- Tắt alerts thay vì sửa root cause.
- Lấy traffic test vào numerator để làm tỷ lệ đẹp.
- Không đếm cancelled/unknown outcomes một cách rõ ràng.

SLO phải đo điều người dùng cần, không chỉ đo một giao thức dễ tối ưu hình thức.

## 31. Checklist thiết kế và nghiệm thu alert

### Trước khi tạo rule

- [ ] Có user journey hoặc business capability rõ.
- [ ] Xác định ảnh hưởng thực tế, mức độ rủi ro và owner.
- [ ] SLI có numerator/denominator, unit và cửa sổ.
- [ ] SLO/Error budget được phê duyệt và có baseline.
- [ ] Có quy tắc phân loại business decline khác technical error.
- [ ] Có state-based guardrail cho data integrity/payment nếu cần.
- [ ] Chọn page/ticket/dashboard phù hợp urgency và khả năng hành động.

### Khi triển khai

- [ ] PromQL/metric names dựa trên dữ liệu có thật; no-data được xử lý.
- [ ] Low traffic và minimum sample không che incident quan trọng.
- [ ] Có fast/medium/slow burn hoặc cơ chế phù hợp với loại SLI.
- [ ] Alert labels ổn định, không chứa PII hoặc ID động.
- [ ] Grouping, dedup, inhibition và silence có scope rõ.
- [ ] Có severity, owner, dashboard, runbook và escalation.
- [ ] Có synthetic/telemetry freshness nếu SLI chính dễ mù.
- [ ] Có drill down từ business impact xuống dependency/resource cause.
- [ ] Có giới hạn cardinality và chi phí telemetry.
- [ ] Alert rule được thử trên test incidents và dữ liệu lịch sử.

### Sau khi chạy thực tế

- [ ] Đo actionable page rate, false positive/negative và alert fatigue.
- [ ] Có review định kỳ threshold, SLO và business impact.
- [ ] Incident không được phát hiện đã trở thành test case.
- [ ] Runbook được chỉnh sau sự cố và có owner.
- [ ] Recovery phải xác nhận user outcomes và backlog, không chỉ health xanh.
- [ ] Thay đổi release/config/feature flag được liên kết timeline.
- [ ] Không lặp alert storm khi một dependency chung lỗi.
- [ ] Triggers capacity dự báo được đưa vào ticket trước khi ảnh hưởng hiện tại.
- [ ] Guardrail data integrity còn hoạt động dù aggregate error ratio thấp.

## 32. Bài tập thực hành

### Bài A — Phân loại 10 alert

Cho các tín hiệu: CPU 95% trong 10 phút; disk đầy trong 30 phút theo forecast; checkout bad ratio 3%; P99 của search tăng nhưng volume rất thấp; paid orders quá SLA; email marketing queue 200.000; OTP queue age 90 giây; một Pod restart sau deploy; duplicate charge xác nhận; metrics pipeline không có data ở Payment.

Hãy xếp thành Page/Ticket/Dashboard, xác định impact, first action và lý do. Chú ý điều kiện “CPU cao nhưng SLI khỏe” và “một sự cố tài chính dù tỷ lệ nhỏ”.

### Bài B — Tính error budget

SLO checkout 99,9% trong 30 ngày. Một khoảng 1 giờ có 100.000 eligible requests, trong đó 1.500 bad requests. Tính bad-event ratio và burn rate. Nếu duy trì một giờ, khoảng bao nhiêu phần trăm budget 30 ngày đã bị tiêu thụ theo mô hình rate ổn định?

**Gợi ý:** bad ratio = 1.500/100.000 = 1,5%; burn = 0,015 / 0,001 = 15×; budget fraction ≈ 15/720 ≈ 2,08%.

### Bài C — Viết PromQL

Dựa trên §sli_checkout_requests_total{outcome="good|bad",region="..."}§, viết recording rules cho 5m và 1h; alert khi burn rate vượt 14,4× ở cả hai. Nêu cách tránh mismatch labels giữa hai vector và khi denominator bằng 0.

### Bài D — Thiết kế alert cho async workflow

Order API trả 202 trong 100 ms nhưng 40 đơn đã capture tiền vẫn chưa có Inventory outcome sau 15 phút. Thiết kế workflow state projection và alert sử dụng §workflow_id§ trong data store, không dùng nó làm metric label. Xác định severity, owner và điều kiện recovery.

### Bài E — Giảm noise sau một outage

DB chung lỗi, tạo 150 alerts từ Pod, pool, service errors và queue. Đề xuất grouping, inhibition và incident dashboard sao cho on-call chỉ nhận một vài notifications có ý nghĩa, vẫn giữ khả năng thấy tác động tới Checkout/Inventory/Payments.

### Bài F — Đo chất lượng alert

Một tháng có 80 pages, trong đó 12 pages cần hành động. Có ba user-impact incidents nghiêm trọng, hai trong số đó được phát hiện đầu tiên bởi người dùng. Tính actionable page rate và thảo luận precision/recall, độ trễ phát hiện và mục tiêu cải tiến.

**Gợi ý:** 12/80 = 15% actionable. Đừng chỉ xóa alerts; cần tìm lý do hai incidents quan trọng bị bỏ sót và bổ sung SLI/synthetic checks.

### Bài G — Viết runbook

Viết runbook một trang cho §CheckoutHighErrorBudgetBurn§: impact, dashboard, sample count, traffic/freshness, các dependency cần kiểm, deployment correlation, safe rollback, payment idempotency, xác nhận backlog và truyền thông incident.

## 33. Các lỗi thiết kế cảnh báo thường gặp

1. **Page theo CPU/RAM tuyệt đối:** không biết người dùng bị ảnh hưởng hay không.
2. **Chỉ dùng một cửa sổ ngắn:** dễ flapping khi traffic thấp.
3. **Chỉ dùng cửa sổ dài:** phát hiện outage lớn chậm.
4. **Không có mẫu số:** “100 lỗi” không có ý nghĩa nếu không biết traffic.
5. **Không xử lý no traffic/no data:** mù observability bị hiểu thành healthy.
6. **Gộp 4xx nghiệp vụ và 5xx hạ tầng:** reliability SLI không phản ánh contract.
7. **Chỉ đo API 202:** bỏ sót async workflow stuck.
8. **Không đo dữ liệu/tiền:** hiếm nhưng rủi ro cao không được page.
9. **Mọi alert cùng severity:** on-call không phân biệt khẩn cấp.
10. **Không có runbook/owner:** page không dẫn đến hành động.
11. **Không dedup/group:** một root cause thành hàng trăm notifications.
12. **Inhibit quá rộng:** một outage che thêm các sự cố độc lập.
13. **Silence không có expiry:** lỗi thật bị che trong nhiều ngày.
14. **Metric labels chứa order/user ID:** cardinality và privacy risk.
15. **Alert SLO aggregate global:** sự cố một region nhỏ bị che.
16. **Không kiểm dữ liệu trễ:** dashboard kết luận sai sau pipeline outage.
17. **Chỉ xem P99 không xét mẫu:** nhiễu ở low traffic.
18. **Tạo page khi không thể hành động:** alert fatigue.
19. **Đo phục hồi bằng Pod Ready:** không kiểm pending workflows và compensation.
20. **Không đánh giá alert sau incident:** liên tục lặp cùng false positives và missed incidents.

## 34. Ghi nhớ cốt lõi

Một hệ thống cảnh báo tốt **đánh thức đúng người khi một khả năng quan trọng đang hoặc sắp không đáp ứng cam kết và cần hành động ngay**. Muốn đạt được điều đó, hãy thiết kế theo thứ tự:

1. **User journey và business invariants:** điều gì phải hoạt động đúng?
2. **SLI và SLO:** phép đo nào cho thấy mức độ đáp ứng?
3. **Error budget/burn rate:** đang mất độ tin cậy nhanh đến đâu?
4. **Impact/severity/urgency:** ai bị ảnh hưởng, có rủi ro tài chính hay dữ liệu không?
5. **Actionable routing và runbook:** ai làm gì và xác nhận phục hồi ra sao?
6. **Technical signals:** CPU, RAM, DB pool, queue lag và traces dùng để chẩn đoán, dự báo và phòng ngừa.
7. **Continuous review:** phát hiện missed incidents và giảm alert fatigue.

Đừng hỏi “CPU có cao không?” trước khi hỏi “**người dùng có bị ảnh hưởng không, kết quả nào bị mất, và hệ thống còn bao lâu trước khi vi phạm cam kết?**”. Cảnh báo theo tác động không bỏ qua tài nguyên; nó đặt tài nguyên vào đúng vai trò trong chuỗi quyết định vận hành.