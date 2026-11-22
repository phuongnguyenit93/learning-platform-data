# Cảnh báo theo triệu chứng và tốc độ tiêu thụ ngân sách lỗi

Một hệ thống có thể có CPU ở mức 90%, nhiều pod restart hoặc database tăng latency mà người dùng vẫn chưa gặp lỗi rõ rệt. Ngược lại, CPU có thể ở mức bình thường nhưng request đăng nhập thất bại, checkout timeout hoặc API trả dữ liệu không đúng. Nếu đội vận hành chỉ cảnh báo theo tài nguyên, họ có thể nhận nhiều thông báo không phản ánh tác động thực tế và bỏ lỡ sự cố ảnh hưởng trực tiếp tới người dùng.

**Cảnh báo theo triệu chứng (symptom-based alerting)** phát hiện khi dịch vụ không còn đáp ứng điều người dùng cần, chẳng hạn request lỗi, phản hồi chậm hoặc giao dịch không hoàn tất. **Error budget** là phần lỗi hoặc gián đoạn mà một SLO cho phép trong một khoảng thời gian. **Burn rate** mô tả tốc độ tiêu thụ ngân sách lỗi so với tốc độ được phép theo SLO đó.

Bài học này thuộc chương **Khả năng quan sát** của module **CLOUD_ARCHITECTURE**. Mục tiêu là thiết kế cảnh báo gắn với SLI/SLO, phân biệt symptom với cause, phát hiện việc tiêu thụ error budget nhanh bằng burn-rate alert, định tuyến cảnh báo tới đúng người và cải thiện chất lượng phản ứng. Nội dung kết nối hiệu năng, độ tin cậy, vận hành, chi phí và nguyên tắc Well-Architected.

## 1. Vì sao cảnh báo cần bắt đầu từ trải nghiệm người dùng?

Monitoring tạo ra rất nhiều tín hiệu: CPU, memory, network, queue depth, database connections, pod restart, HTTP status và log error. Nhưng vận hành không thể xử lý mọi thay đổi metric như một incident.

Hãy xét Booking API:
- CPU của application tăng lên 85% trong một đợt traffic cao, nhưng request vẫn hoàn tất trong SLO.
- Database connection pool đạt ngưỡng, p95 latency tăng và một phần request timeout.
- Payment confirmation thất bại dù API tổng thể vẫn trả 200 cho các request khác.
- Một background worker chậm 10 phút nhưng người dùng chưa bị ảnh hưởng vì queue có đủ headroom.

Nếu paging dựa vào CPU hoặc mọi warning, đội trực sẽ bị gián đoạn bởi các sự kiện chưa cần can thiệp. Nếu chỉ cảnh báo khi process chết, hệ thống có thể gây ảnh hưởng người dùng trong thời gian dài trước khi được phát hiện.

Cảnh báo tốt cần trả lời:
1. Người dùng có đang gặp lỗi hoặc chậm hơn cam kết không?
2. Tác động xảy ra ở dịch vụ, endpoint, tenant hay workflow nào?
3. SLO đang bị tiêu thụ nhanh tới mức nào?
4. Ai cần hành động và cần làm gì trước?
5. Khi nào nên paging ngay, khi nào tạo ticket hoặc theo dõi?

~~~mermaid
flowchart TB
    U["User journey"] --> SLI["Service level indicators"]
    SLI --> SLO["Service level objectives"]
    SLO --> EB["Error budget"]
    SLI --> BR["Burn rate"]
    BR --> ALERT["Symptom-based alerts"]
    ALERT --> ONCALL["On-call / incident response"]
    ONCALL --> FIX["Mitigation and recovery"]
    FIX --> REVIEW["Post-incident review"]
~~~

## 2. Phân biệt metric, SLI, SLO, SLA và error budget

Các khái niệm này liên quan nhưng không thể dùng thay thế nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Metric | Một phép đo quan sát được | HTTP 5xx count, p95 latency, CPU usage |
| SLI | Chỉ số đại diện cho chất lượng dịch vụ | Tỷ lệ request hợp lệ hoàn tất thành công |
| SLO | Mục tiêu nội bộ cho SLI trong một cửa sổ thời gian | 99,9% availability trong 30 ngày |
| SLA | Cam kết dịch vụ với khách hàng/đối tác, có thể kèm điều khoản | Availability cam kết theo hợp đồng |
| Error budget | Mức lỗi còn được phép theo SLO | 0,1% request lỗi trong cửa sổ SLO |

Một metric chỉ trở thành SLI khi nó phản ánh một khía cạnh chất lượng mà người dùng quan tâm và được định nghĩa rõ. Ví dụ CPU utilization thường là metric nguyên nhân hoặc tín hiệu capacity; nó không tự nó phản ánh availability của Booking API.

### 2.1. Chọn SLI theo user journey

Bắt đầu từ hành động người dùng cần hoàn thành:
- Tìm kiếm phòng và nhận kết quả hợp lệ.
- Đăng nhập và truy cập tài khoản.
- Tạo booking thành công.
- Xác nhận thanh toán.
- Tải tài liệu đã được cấp quyền.

SLI cần định nghĩa rõ:
- Event nào là eligible event?
- Event nào được tính good hoặc bad?
- Timeout, cancellation và client abort được tính ra sao?
- Synthetic probe có được tính vào SLI không?
- Request nội bộ, health check và retry có bị tính trùng không?
- Có phân tách theo region, endpoint, tenant hoặc service tier không?

Ví dụ availability SLI đơn giản:

\[
Availability\ SLI = \frac{Good\ Events}{Eligible\ Events}
\]

Nếu trong cửa sổ có 100.000 request hợp lệ và 99.950 request tốt:

\[
SLI = \frac{99,950}{100,000} = 99.95\%
\]

Một request được tính là good cần tuân theo định nghĩa đã thống nhất, chẳng hạn status thành công và hoàn tất trong deadline. Nếu API trả HTTP 200 nhưng workflow không tạo booking đúng, SLI chỉ dựa trên status code có thể đánh giá sai chất lượng.

### 2.2. Latency SLI

Latency có thể được biểu diễn bằng phần trăm request hoàn tất trong một ngưỡng:

\[
Latency\ SLI = \frac{Requests\ within\ threshold}{Eligible\ requests}
\]

Ví dụ SLO yêu cầu 99% request tìm kiếm hoàn tất trong 300 ms. Không nên chỉ theo dõi average latency vì một số request rất chậm có thể bị che bởi số đông request nhanh. Dùng histogram hoặc distribution để tính quantile và tỷ lệ request dưới ngưỡng.

### 2.3. SLO phải có phạm vi và cửa sổ

Một SLO cần nêu:
- Dịch vụ hoặc capability nào được đo.
- Nhóm request nào nằm trong phạm vi.
- SLI và công thức tính.
- Mục tiêu phần trăm.
- Cửa sổ thời gian, ví dụ rolling 30 ngày.
- Nguồn dữ liệu và cách xử lý missing telemetry.
- Owner chịu trách nhiệm.

Không đặt cùng một SLO cho mọi endpoint nếu mức độ quan trọng và khả năng kiểm soát khác nhau. Định nghĩa SLO quá dễ đạt sẽ không tạo tín hiệu; quá khắt khe có thể dẫn tới alert noise và chi phí không cần thiết.

## 3. Error budget: phần lỗi được phép

Nếu SLO availability là 99,9%, error budget là 0,1% bad event trong cửa sổ đánh giá.

\[
Error\ Budget = 1 - SLO
\]

Với 100.000 request đủ điều kiện:
- SLO 99,9% cho phép 100 bad request.
- SLO 99,95% cho phép 50 bad request.
- SLO 99,99% cho phép 10 bad request.

Đối với SLO dựa trên thời gian availability, có thể quy đổi thành thời lượng gián đoạn cho phép trong cửa sổ. Với request-based SLO, budget được tính theo số request lỗi trong tập eligible request.

Error budget tạo cơ sở để cân bằng tốc độ phát triển với độ tin cậy:
- Khi budget còn khỏe, nhóm có dư địa cho thay đổi có kiểm soát.
- Khi budget đang bị tiêu thụ nhanh, cần ưu tiên giảm rủi ro và khắc phục.
- Khi budget cạn, chính sách release có thể hạn chế thay đổi rủi ro cao cho tới khi reliability được cải thiện.

Error budget không có nghĩa nhóm được phép chủ động gây lỗi. Nó là cách định lượng mức độ không hoàn hảo đã được chấp nhận trong thiết kế dịch vụ.

### 3.1. Ví dụ budget theo tháng

Giả sử Booking API có 10 triệu request đủ điều kiện trong 30 ngày và SLO availability là 99,9%.

\[
Budget = 10,000,000 \times 0.001 = 10,000
\]

Nếu đã có 6.000 bad request, budget còn lại là 4.000 request. Nếu bad request tăng nhanh trong một giờ, hệ thống có thể tiêu hết budget trước cuối tháng dù tổng SLI hiện tại vẫn tạm đạt mục tiêu.

Đây là lý do cần quan sát cả error budget còn lại và tốc độ tiêu thụ, không chỉ SLO cuối cửa sổ.

## 4. Symptom-based alert và cause-based alert

**Symptom-based alert** cảnh báo khi dịch vụ đang vi phạm hoặc có nguy cơ vi phạm trải nghiệm người dùng. **Cause-based alert** cảnh báo một nguyên nhân hoặc điều kiện hạ tầng có thể dẫn tới tác động.

| Tín hiệu | Nhóm | Cách sử dụng |
|---|---|---|
| Tỷ lệ booking thất bại tăng | Symptom | Paging nếu vượt ngưỡng tác động |
| p99 latency tìm kiếm vượt SLO | Symptom | Paging theo mức độ và thời lượng |
| Availability SLI giảm mạnh | Symptom | Paging |
| CPU 90% trong thời gian ngắn | Cause/capacity | Dashboard hoặc ticket tùy context |
| Database connection pool cạn | Cause gần | Alert ưu tiên cao nếu có ảnh hưởng |
| Queue oldest age vượt deadline nghiệp vụ | Symptom hoặc near-symptom | Paging nếu xử lý trễ ảnh hưởng khách hàng |
| Một node restart | Cause | Thường không cần paging nếu replica khác vẫn phục vụ |
| Certificate sắp hết hạn | Leading indicator | Ticket/alert trước khi ảnh hưởng |

Cảnh báo nguyên nhân vẫn rất quan trọng. Chúng giúp phát hiện sớm nguy cơ trước khi người dùng bị ảnh hưởng. Nhưng không nên thay thế cảnh báo triệu chứng bằng một danh sách ngưỡng hạ tầng.

Một mô hình thực tế:
- Symptom alerts quyết định cần phản ứng ngay.
- Cause alerts giúp chẩn đoán và ngăn sự cố.
- Informational signals hỗ trợ dashboard, capacity planning và trend.
- Predictive alerts báo trước giới hạn sắp tới nếu có độ tin cậy đủ cao.

## 5. Burn rate là gì?

Burn rate là tốc độ tiêu thụ error budget so với tốc độ tiêu thụ tương ứng với việc dùng hết budget đúng vào cuối cửa sổ SLO.

\[
Burn\ Rate = \frac{Observed\ Error\ Rate}{Allowed\ Error\ Rate}
\]

Trong đó:

\[
Allowed\ Error\ Rate = 1 - SLO
\]

Nếu SLO availability là 99,9%, allowed error rate là 0,1% hay 0,001.

- Burn rate = 1: đang tiêu thụ budget đúng tốc độ cho phép trong cửa sổ.
- Burn rate = 2: tiêu thụ nhanh gấp hai lần tốc độ cho phép.
- Burn rate = 10: tiêu thụ nhanh gấp mười lần.
- Burn rate < 1: mức lỗi hiện tại thấp hơn tốc độ ngân sách cho phép.

Burn rate không phải tỷ lệ lỗi đơn thuần. Nó chuẩn hóa error rate theo mức SLO, cho phép so sánh mức độ nguy hiểm giữa các dịch vụ có SLO khác nhau.

### 5.1. Ví dụ tính toán

SLO availability = 99,9%; allowed error rate = 0,1%.

Nếu error rate quan sát trong 5 phút là 2%:

\[
Burn\ Rate = \frac{2\%}{0.1\%} = 20
\]

Dịch vụ đang tiêu thụ error budget nhanh gấp 20 lần tốc độ cho phép. Tuy nhiên, một khoảng đo 5 phút có thể ít request hoặc bị ảnh hưởng bởi traffic thấp; cần kết hợp cửa sổ khác và số lượng event tối thiểu để giảm false positive.

### 5.2. Ước lượng thời gian tới khi hết budget

Nếu burn rate gần như ổn định, có thể ước lượng:

\[
Time\ to\ exhaust \approx \frac{Remaining\ budget\ fraction \times SLO\ window}{Burn\ rate}
\]

Ví dụ cửa sổ SLO 30 ngày, còn 50% budget và burn rate 10:

\[
Time \approx \frac{0.5 \times 30\ days}{10} = 1.5\ days
\]

Đây là ước lượng đơn giản, giả định burn rate không thay đổi và budget được tiêu thụ đều theo cách đo. Trong thực tế, traffic và lỗi biến động; dùng nó như chỉ báo mức độ khẩn cấp, không phải dự báo chắc chắn.

## 6. Multi-window, multi-burn-rate alerting

Nếu chỉ dùng một cửa sổ dài, alert có thể đến trễ. Nếu chỉ dùng cửa sổ ngắn, một burst rất nhỏ có thể tạo false positive. Một cách tiếp cận là kết hợp nhiều cửa sổ thời gian và burn-rate threshold.

Ví dụ:
- Cửa sổ ngắn phát hiện sự cố đang diễn ra.
- Cửa sổ dài xác nhận lỗi đủ bền vững và có tác động đáng kể.
- Cùng một burn-rate threshold trên cả hai cửa sổ giúp tránh paging vì một spike rất ngắn.

~~~mermaid
flowchart TB
    SLI["SLI error events"] --> W1["Short window"]
    SLI --> W2["Long window"]
    W1 --> C{"Both windows exceed burn threshold?"}
    W2 --> C
    C -->|"Yes"| PAGE["Page on-call"]
    C -->|"No"| KEEP["Keep observing / lower-severity alert"]
~~~

### 6.1. Ví dụ policy minh họa

Giả sử SLO là 99,9% trên 30 ngày. Một policy tham khảo có thể dùng:
- Burn rate 14,4 trong cửa sổ 1 giờ và 5 phút: paging khẩn cấp.
- Burn rate 6 trong cửa sổ 6 giờ và 30 phút: paging mức cao.
- Burn rate 3 trong cửa sổ 24 giờ và 2 giờ: cảnh báo ưu tiên hoặc ticket, tùy policy tổ chức.

Các con số này là ví dụ phổ biến để minh họa cách phối hợp cửa sổ, không phải ngưỡng bắt buộc. Cần điều chỉnh theo SLO window, traffic, mức độ quan trọng, alerting system và chính sách on-call.

### 6.2. Tính phần budget bị tiêu thụ

Với burn rate r trong một khoảng thời gian t, phần error budget bị tiêu thụ xấp xỉ:

\[
Budget\ consumed \approx r \times \frac{t}{T}
\]

Trong đó T là SLO window; công thức giả định rate ổn định trong khoảng đo và cùng định nghĩa error event.

Ví dụ burn rate 14,4 kéo dài 1 giờ trong cửa sổ 30 ngày:

\[
14.4 \times \frac{1}{720} = 0.02 = 2\%
\]

Tức khoảng 2% monthly error budget bị tiêu thụ trong một giờ. Kết hợp hai cửa sổ cho phép nhận diện cả mức độ hiện tại và độ bền của sự cố.

### 6.3. Vì sao dùng hai cửa sổ?

Một lỗi kéo dài 20 giây có thể tạo burn rate rất cao trong cửa sổ 1 phút nhưng không đáng paging nếu tổng số request nhỏ và đã tự hồi phục. Cửa sổ dài giúp xác nhận xu hướng có đủ tác động.

Ngược lại, cửa sổ dài 6 giờ có thể làm trễ cảnh báo khi toàn bộ dịch vụ vừa ngừng hoạt động. Cửa sổ ngắn giúp phản ứng nhanh hơn. Multi-window giúp cân bằng tốc độ và độ tin cậy.

## 7. Alert theo symptom: availability, latency, traffic và correctness

Các SLI cần phản ánh dịch vụ thực sự cung cấp cho người dùng.

### 7.1. Availability và request failure

Có thể đo tỷ lệ request hợp lệ không trả được kết quả thành công. Cần thống nhất cách tính:
- 5xx thường là bad event.
- 4xx do input sai của client có thể được loại khỏi availability SLI, trừ các trường hợp hệ thống không cung cấp chức năng đúng.
- Timeout do server thường là bad.
- Client abort trước khi server nhận request có thể cần loại hoặc phân loại riêng.
- Retry phải được tính theo request gốc hoặc operation nghiệp vụ để tránh làm méo tỷ lệ.

Không loại toàn bộ 4xx một cách máy móc. Ví dụ 429 do hệ thống rate-limit user hợp lệ có thể là tác động trải nghiệm; cần xem SLI có mục tiêu đo không.

### 7.2. Latency và tail latency

Cảnh báo có thể dựa trên:
- Tỷ lệ request vượt deadline.
- p95/p99 vượt ngưỡng trong đủ thời gian.
- Số request chậm tuyệt đối cùng tỷ lệ chậm.

Quantile có thể dao động mạnh khi sample nhỏ. Histogram bucket giúp tính tỷ lệ request trong ngưỡng và tổng hợp giữa instance tốt hơn. Không average các p95 của từng pod như thể đó là p95 toàn dịch vụ.

### 7.3. Traffic và saturation

Traffic giảm đột ngột có thể là symptom: gateway không nhận request, DNS lỗi hoặc client không kết nối. Traffic tăng bất thường có thể là demand hợp lệ, bot hoặc retry storm.

Saturation như CPU, memory, thread pool, connection pool, queue depth là nguyên nhân/cảnh báo sớm. Cần kết nối với SLI: nếu saturation cao nhưng SLO vẫn đạt, có thể chỉ cần theo dõi/capacity ticket; nếu latency/error bắt đầu vượt, paging theo symptom.

### 7.4. Correctness và business outcome

HTTP 200 không bảo đảm nghiệp vụ đúng. Có thể đo:
- Booking creation success và read-back consistency.
- Payment confirmation outcome.
- Tỷ lệ prediction/output hợp lệ.
- File upload completion.
- Queue job hoàn thành trước deadline.
- Tỷ lệ giao dịch có state transition hợp lệ.

Các SLI correctness cần có nguồn xác nhận độc lập và không ghi dữ liệu nhạy cảm vào metric label.

## 8. Thiết kế alert rule: từ metric tới hành động

Một alert rule tốt nên mô tả:
- Service và SLO liên quan.
- Điều kiện và cửa sổ đo.
- Mức độ severity.
- Thời gian giữ điều kiện hoặc số lượng event tối thiểu.
- Owner/team nhận cảnh báo.
- Hành động đầu tiên.
- Dashboard/runbook liên quan.
- Cách resolve và suppression.

Ví dụ biểu thức giả lập cho request error ratio:

~~~promql
sum(rate(http_requests_total{service="booking-api",status=~"5.."}[5m]))
/
sum(rate(http_requests_total{service="booking-api"}[5m]))
~~~

Đây là ví dụ PromQL minh họa. Production rule cần loại trừ hoặc phân loại request không thuộc SLI, bảo đảm label cardinality phù hợp và xử lý trường hợp denominator bằng 0.

Một burn-rate expression đơn giản có thể có dạng:

~~~promql
(
  sum(rate(http_requests_total{service="booking-api",status=~"5.."}[5m]))
  /
  sum(rate(http_requests_total{service="booking-api"}[5m]))
) / 0.001
~~~

Với SLO 99,9%, allowed error ratio là 0,001. Expression này trả burn rate theo error ratio hiện tại. Alert đa cửa sổ cần so sánh nhiều expression/window trong cùng điều kiện, chứ không chỉ alert một expression 5 phút.

### 8.1. Xử lý denominator thấp hoặc bằng 0

Nếu không có request, tỷ lệ lỗi có thể không xác định hoặc tạo kết quả rỗng. Điều này không chứng minh dịch vụ healthy. Bổ sung:
- Synthetic probe có tần suất phù hợp.
- Traffic absence alert khi dự kiến phải có traffic.
- Minimum event count hoặc minimum traffic condition.
- Separate monitoring cho ingress/DNS/edge.

Với dịch vụ ít traffic, request-based SLI cần cân nhắc cửa sổ dài hơn hoặc synthetic transaction, nhưng phải tránh synthetic probe che khuất trải nghiệm thật.

## 9. Paging, ticket và dashboard: phân cấp phản ứng

Không phải alert nào cũng đánh thức on-call.

| Mức | Khi nào dùng | Kênh phản ứng |
|---|---|---|
| Page / Critical | Người dùng đang bị ảnh hưởng nghiêm trọng hoặc budget burn rất nhanh | On-call ngay |
| High | Tác động có khả năng lớn, cần phản ứng trong thời gian ngắn | On-call/incident channel |
| Ticket / Warning | Nguy cơ capacity, trend hoặc budget burn chậm | Ticket có deadline |
| Info | Sự kiện vận hành hoặc thay đổi bình thường | Dashboard/event log |

Page nên được dùng khi:
- Có hành động khẩn cấp mà con người cần thực hiện.
- Tác động xảy ra ngay hoặc sắp gây hậu quả lớn.
- Có owner và runbook.
- Không thể chờ giờ làm việc tiếp theo.

Nếu alert không yêu cầu hành động, nó thường nên là ticket hoặc dashboard signal thay vì page. Paging cho CPU spike không ảnh hưởng người dùng dễ tạo alert fatigue, khiến kỹ sư bỏ lỡ incident thật.

## 10. Giảm alert noise và alert fatigue

Alert fatigue xuất hiện khi người trực nhận quá nhiều cảnh báo trùng, không hữu ích hoặc không cần hành động. Hệ quả là cảnh báo quan trọng có thể bị bỏ qua.

Các nguyên nhân:
- Ngưỡng cố định không gắn với traffic hoặc SLO.
- Alert per-instance nhưng không gộp thành service-level symptom.
- Cùng một incident tạo nhiều alert từ nhiều tầng.
- Alert không có owner hoặc runbook.
- Threshold dao động quanh biên gây flapping.
- Retry storm làm tăng lỗi thứ cấp.
- Dashboard warning bị định tuyến thành page.
- Metric thiếu label/context nên không xác định được phạm vi.

Cách cải thiện:
1. Gộp alert theo incident, service và symptom.
2. Dùng multi-window/multi-burn-rate cho SLO alert.
3. Thêm for-duration hoặc hysteresis cho tín hiệu dao động.
4. Dùng inhibition/suppression có điều kiện, ví dụ suppress pod alert khi đã có region outage page.
5. Phân biệt page, ticket và info.
6. Tự động resolve khi điều kiện phục hồi ổn định.
7. Review alert sau incident và loại rule không dẫn tới hành động.
8. Theo dõi false positive, duplicate và acknowledgement.

Không suppress mọi cảnh báo khi có một incident lớn. Một alert phụ vẫn có thể đại diện cho tác động khác hoặc khu vực chưa được bao phủ; suppression cần có scope rõ.

## 11. Alert routing, ownership và escalation

Một alert chỉ có giá trị khi tới đúng người có thể hành động.

Cần định nghĩa:
- Service owner và primary/secondary on-call.
- Lịch trực và timezone coverage.
- Escalation khi không acknowledge.
- Incident commander khi nhiều service bị ảnh hưởng.
- Team dependency như database, network, identity và security.
- Communications owner nếu cần thông báo khách hàng/đối tác.
- Runbook, dashboard, recent deployment và change context.

Alert payload nên có:
- Tên SLO/service và symptom.
- Severity và burn rate.
- Error ratio/count và các cửa sổ đang vi phạm.
- Region/endpoint/cohort bị ảnh hưởng.
- Bắt đầu từ khi nào và trend.
- Link dashboard/query/runbook.
- Recent change/deploy context nếu có.
- Owner và escalation path.

Tránh đưa raw request body, token, email hoặc PII vào alert. Alert nên chứa identifier đã kiểm soát để analyst truy vấn theo quyền.

## 12. Correlate symptom với cause để chẩn đoán nhanh

Symptom alert quyết định mức khẩn cấp; cause telemetry giúp tìm nguyên nhân. Có thể xây dựng dependency map:

~~~mermaid
flowchart TB
    USER["Search p99 latency SLO breach"] --> API["Booking API"]
    API --> FEAT["Feature / cache lookup"]
    API --> DB["Database"]
    API --> PAY["Payment dependency"]
    FEAT --> REDIS["Redis saturation"]
    DB --> CONN["Connection pool / locks"]
    PAY --> EXT["Provider latency / quota"]
~~~

Khi p99 latency tăng, dashboard có thể đặt cạnh:
- Recent deploy/change.
- API concurrency, thread pool và GC.
- Cache hit/miss, hot key và latency.
- Database connection wait, slow query, lock và replication lag.
- External API latency, quota và 429.
- Network packet loss, DNS và TLS handshake.
- Queue depth/oldest age.

Không tạo một alert riêng cho từng nguyên nhân rồi page tất cả cùng lúc. Có thể giữ cause alert ở mức ticket hoặc warning trừ khi đó là nguy cơ sắp gây outage lớn, ví dụ certificate hết hạn hoặc database storage gần cạn.

## 13. Burn-rate policy theo service tier

Các dịch vụ có impact khác nhau có thể dùng SLO, cửa sổ và escalation khác nhau. Cần tránh áp một policy cho mọi service.

| Service tier | Ví dụ | Alert priority | Hành động khi burn cao |
|---|---|---|---|
| Tier 0 | Booking commit, payment confirmation | Page nhanh | Incident response, mitigation ngay |
| Tier 1 | Search, login, customer API | Page theo burn-rate policy | Rollback, capacity hoặc dependency mitigation |
| Tier 2 | Notification, reporting | Page khi deadline/impact thực tế | Queue drain, retry/backfill |
| Tier 3 | Internal analytics batch | Ticket hoặc page theo data deadline | Reschedule, recompute, adjust capacity |

SLO có thể khác nhau giữa customer-facing và internal workload. Tuy nhiên, nếu internal batch cung cấp dữ liệu cần thiết cho giao dịch ngày hôm sau, deadline của nó vẫn có thể có business impact lớn.

### 13.1. Không để traffic thấp che outage

Một endpoint ít traffic có thể có error ratio 100% nhưng chỉ có một request. Một endpoint traffic lớn có error ratio 1% có thể ảnh hưởng hàng nghìn người. Alert policy nên kết hợp:
- Error ratio.
- Absolute failed event count.
- Burn rate.
- Minimum traffic.
- Synthetic user journey.
- Service criticality.

Không chỉ tối ưu một ngưỡng phần trăm.

## 14. Khi ngân sách lỗi bị tiêu thụ nhanh

Khi burn-rate alert kích hoạt, nhóm cần quy trình có thể lặp lại:

1. Xác nhận SLI, cửa sổ và phạm vi affected service.
2. Kiểm tra traffic/denominator, telemetry gap và duplicate counting.
3. Xác định onset, deployment/config change và dependency changes.
4. Ước lượng user impact và thời gian tới khi budget cạn.
5. Chọn mitigation giảm impact trước khi sửa triệt để.
6. Nếu liên quan release, cân nhắc pause rollout hoặc rollback theo runbook.
7. Giảm load, disable tính năng phụ hoặc chuyển sang degraded mode nếu được phê duyệt.
8. Theo dõi SLI/burn rate sau mitigation.
9. Ghi incident timeline, budget consumed và recovery.
10. Tạo action items để giảm recurrence.

### 14.1. Chính sách release khi budget gần cạn

Tổ chức có thể định nghĩa release policy:
- Budget khỏe: release theo quy trình thông thường.
- Budget bị tiêu thụ nhanh: tăng cường canary, approval hoặc giảm phạm vi release.
- Budget cạn: tạm dừng release có rủi ro cho service tới khi reliability được cải thiện, trừ thay đổi cần thiết để xử lý incident/security.

Đây là policy quản trị nội bộ; error budget không nên tự động khóa mọi deploy nếu một hotfix cần thiết để phục hồi dịch vụ.

## 15. Synthetic monitoring và real-user monitoring

**Real-user monitoring (RUM)** quan sát trải nghiệm từ request/session thực. **Synthetic monitoring** chủ động chạy các transaction thử nghiệm theo lịch hoặc từ nhiều location.

RUM:
- Phản ánh traffic và thiết bị thực.
- Có thể phân tích theo browser, region, cohort và network.
- Chỉ có dữ liệu khi người dùng thực truy cập.
- Cần privacy controls và sampling phù hợp.

Synthetic:
- Phát hiện DNS, TLS, login hoặc user journey hỏng ngay cả khi traffic thật thấp.
- Có thể kiểm tra từ nhiều khu vực.
- Dễ chuẩn hóa và lặp lại.
- Không đại diện hoàn toàn cho mọi user, account, thiết bị hoặc payment path.

Kết hợp cả hai để tránh false healthy khi traffic thấp và tránh synthetic green che giấu vấn đề chỉ ảnh hưởng một cohort.

Synthetic test cần dùng account/dữ liệu test riêng, không tạo booking/payment thật và có cleanup. Nếu cần kiểm tra end-to-end production, thiết kế side effect an toàn và idempotent.

## 16. Well-Architected và các đánh đổi của alerting

| Khía cạnh | Thiết kế tốt | Rủi ro cần kiểm soát | Bằng chứng |
|---|---|---|---|
| **Độ tin cậy** | Alert theo SLI/SLO, burn rate, có owner và runbook | Alert chậm, missing telemetry, false positive | Incident drill, SLO dashboard, alert review |
| **Bảo mật** | Alert privilege/data access bất thường, bảo vệ payload | PII/secret trong alert, quyền SIEM quá rộng | Access review, redaction test, audit |
| **Hiệu quả hiệu năng** | Theo dõi latency và user journey, phát hiện saturation sớm | Metrics cardinality cao, query tốn tài nguyên | Query cost, scrape/ingestion health |
| **Tối ưu chi phí** | Page đúng lúc, phân tầng hot/warm telemetry | SIEM/log volume và on-call toil quá lớn | Cost per service, alert actionability |
| **Vận hành xuất sắc** | Escalation, incident workflow, feedback loop | Alert fatigue, không có ownership | MTTD/MTTA/MTTR, duplicate rate |
| **Bền vững** | Thu thập đúng tín hiệu và retention hợp lý | Telemetry thừa, lưu trữ và compute phân tích lãng phí | Data minimization, retention/cost review |

Các đánh đổi quan trọng:
- Cửa sổ ngắn phát hiện nhanh nhưng nhiễu hơn; cửa sổ dài ổn định nhưng trễ.
- Burn-rate alert phản ánh budget consumption nhưng phụ thuộc chất lượng SLI.
- Page nhiều giúp phát hiện nhanh nhưng tăng fatigue và chi phí on-call.
- SLI request-based phù hợp API nhiều traffic; synthetic hoặc workflow SLI có thể cần cho dịch vụ ít traffic.
- Alert theo symptom giảm noise từ nguyên nhân vô hại nhưng cần cause telemetry tốt để điều tra.
- Phân tách SLO quá nhiều giúp thấy cohort nhưng tăng độ phức tạp và cardinality.

## 17. Quy trình thiết kế alerting theo SLO

Một quy trình review thực tế:

1. **Vẽ user journey:** xác định hành động người dùng cần hoàn tất.
2. **Chọn SLI:** success, latency, freshness, correctness hoặc workflow completion.
3. **Viết SLO:** mục tiêu, cửa sổ, phạm vi, denominator và owner.
4. **Tính error budget:** tỷ lệ lỗi và số lượng/số phút lỗi tương ứng.
5. **Đo baseline:** traffic, error distribution, latency, seasonality và missing telemetry.
6. **Chọn burn-rate thresholds:** nhiều cửa sổ theo mức criticality và response time.
7. **Tạo symptom alerts:** chỉ page khi có tác động/đe dọa SLO đáng kể.
8. **Bổ sung cause alerts:** capacity, dependency, expiry và pipeline health.
9. **Định tuyến:** owner, severity, on-call, escalation và runbook.
10. **Giảm noise:** dedup, grouping, inhibition, hysteresis và resolve policy.
11. **Kiểm thử:** synthetic failure, traffic burst, low denominator, telemetry loss và burn simulation.
12. **Review:** false positive, missed incident, time-to-detect, toil và budget policy.

### Checklist trước khi đưa alert vào production

| Hạng mục | PASS khi |
|---|---|
| User impact | Alert mô tả một symptom hoặc nguy cơ cụ thể |
| SLI/SLO | Có định nghĩa, phạm vi và owner |
| Burn calculation | Allowed error rate và cửa sổ được xác định đúng |
| Multi-window | Ngưỡng và điều kiện kết hợp đã được test |
| Denominator | Có xử lý traffic thấp/0 và minimum event count |
| Actionability | Có người nhận, hành động và runbook |
| Severity | Page/ticket/info phù hợp mức độ |
| Noise control | Có grouping/dedup/suppression có phạm vi |
| Diagnosis | Có dashboard cause metrics và deploy context |
| Privacy | Alert không chứa secret/PII thừa |
| Resilience | Telemetry pipeline và alert route được kiểm thử |
| Review | Có quy trình chỉnh rule sau incident |

## 18. ADR minh họa — Burn-rate alerts cho Booking API

> **Bối cảnh:** Booking API có SLO availability 99,9% trong rolling 30 ngày. Hệ thống nhận traffic biến động theo giờ. Alert CPU hiện tại tạo nhiều page nhưng không phản ánh trực tiếp trải nghiệm booking.
>
> **Phương án A:** Page khi CPU vượt 80% trong 5 phút. Dễ triển khai và hữu ích cho capacity, nhưng có thể page dù SLO vẫn đạt hoặc bỏ lỡ lỗi do dependency.
>
> **Phương án B:** Dùng request-based availability SLI và latency SLI, tạo multi-window burn-rate alerts; CPU/DB/cache giữ vai trò cause alerts.
>
> **Quyết định minh họa:** Chọn B. Dùng burn-rate policy nhanh cho Tier 0 booking flow; ngưỡng chậm hơn cho báo cáo. Cause alert được định tuyến tới dashboard/ticket trừ nguy cơ imminent.
>
> **Alert payload:** service, SLO, burn rate, error ratio/count, short/long window, region, endpoint, dashboard, runbook và owner.
>
> **Mitigation:** pause risky rollout, rollback nếu có liên hệ rõ, giới hạn concurrency hoặc chuyển fallback đã được phê duyệt; theo dõi SLI sau hành động.
>
> **Kiểm chứng:** inject 5xx, latency, low traffic, zero traffic, metric gap, duplicate series và traffic burst; kiểm tra page chỉ phát khi điều kiện đã thống nhất.
>
> **Điều kiện xem xét lại:** SLI không đại diện user journey, false positive cao hoặc workload/traffic pattern thay đổi đáng kể.

## 19. Bài tập thực hành: cảnh báo khi Booking API đốt error budget

Booking API có:
- SLO availability 99,9% trong 30 ngày.
- SLO latency: 99% request tìm kiếm hoàn tất dưới 300 ms.
- Traffic bình thường 2.000 request/giây, nhưng có thể giảm xuống dưới 20 request/giây lúc đêm khuya.
- CPU thường dao động từ 40% tới 85%.
- Payment confirmation là một workflow riêng và có thể lỗi dù API search vẫn hoạt động.

Một rule hiện tại page nếu CPU trên 80% trong 5 phút. Trong đợt campaign, CPU ở 88% nhưng SLO availability vẫn đạt. Một đêm khác CPU chỉ 35%, nhưng payment confirmation timeout 8% trong 10 phút.

**Yêu cầu:**
1. Xác định symptom SLI riêng cho search, booking commit và payment confirmation.
2. Tính allowed error ratio theo SLO 99,9%.
3. Tính burn rate khi error ratio là 1%, 2% và 8%.
4. Thiết kế multi-window burn-rate policy cho incident nghiêm trọng và degradation kéo dài.
5. Xử lý low-traffic/zero-traffic để không có false healthy.
6. Phân loại CPU, DB connections, payment latency thành cause alerts.
7. Thiết kế page/ticket routing và alert payload.
8. Đề xuất mitigation và release policy khi budget bị tiêu thụ nhanh.
9. Thiết kế synthetic probe cho payment confirmation mà không tạo giao dịch thật.
10. Chọn metric đánh giá alert quality sau 30 ngày.

### Hướng giải quyết

- Tách SLI theo workflow. Search đo success và latency; booking commit đo transaction hoàn tất đúng; payment confirmation đo kết quả xác nhận theo semantics provider/ứng dụng.
- SLO 99,9% có allowed error ratio 0,1% (0,001).
- Với error ratio 1%, burn rate = 1% / 0,1% = 10.
- Với 2%, burn rate = 20.
- Với 8%, burn rate = 80.
- Khi traffic thấp, kết hợp minimum event count, cửa sổ dài và synthetic checks; zero traffic trong khung giờ phải có request cần phục vụ có thể là symptom riêng.
- CPU 88% là cause/capacity signal; nếu SLI vẫn đạt thì không nhất thiết page. Payment timeout 8% là symptom của workflow payment và có thể cần page dù CPU thấp.
- Alert payload có workflow, SLI/SLO, burn rate, failed count, short/long window, region, provider, recent deploy, dashboard và runbook.
- Mitigation gồm rollback thay đổi có liên quan, giảm concurrency, retry có budget, circuit breaker hoặc chuyển manual review/fallback theo policy nghiệp vụ.
- Synthetic payment nên dùng sandbox hoặc provider test mechanism; production probe chỉ dùng authorization/verification path an toàn, không tạo charge thật.
- Review page actionability, false positive, duplicate alerts, MTTD, MTTA, MTTC, budget consumed và incident missed.

### Câu hỏi tự kiểm tra

1. Metric khác SLI như thế nào?
2. Vì sao CPU không phải availability SLI?
3. Error budget của SLO 99,9% là bao nhiêu?
4. Burn rate 10 có ý nghĩa gì?
5. Vì sao multi-window alert tốt hơn một cửa sổ ngắn duy nhất?
6. Cách tính budget consumed phụ thuộc giả định nào?
7. Khi nào cần page và khi nào tạo ticket?
8. Làm sao phân biệt symptom alert với cause alert?
9. Vì sao traffic thấp làm error ratio thiếu ổn định?
10. Synthetic monitoring bổ sung điều gì cho real-user monitoring?
11. Làm sao tránh alert storm khi một dependency lỗi?
12. Error budget nên ảnh hưởng tới release policy như thế nào?

Cảnh báo hiệu quả bắt đầu từ điều người dùng cần hoàn thành và cam kết chất lượng mà dịch vụ đã đặt ra. SLI/SLO xác định thế nào là tốt hoặc lỗi; error budget lượng hóa phần lỗi được phép; burn rate cho thấy ngân sách đang bị tiêu thụ nhanh tới đâu. Kết hợp multi-window alerts, cause telemetry, ownership và runbook giúp đội vận hành phản ứng đúng lúc, giảm alert fatigue và đưa quyết định reliability dựa trên dữ liệu.
