# Định nghĩa SLI, SLO theo độ sẵn sàng, độ trễ và kết quả nghiệp vụ

## 1. Quan sát REST API từ góc nhìn người sử dụng

Một ứng dụng Spring Boot vẫn chạy, endpoint health trả 200, CPU bình thường, nhưng người mua không thể tạo đơn vì hàng đợi thanh toán bị kẹt. Ở chiều ngược lại, một vài request bị từ chối 400 vì input sai không có nghĩa API đang mất khả dụng. Để đánh giá đúng, đội vận hành cần phân biệt **chỉ số đo**, **mục tiêu chất lượng** và **cảnh báo hành động**.

Trong module **INTEGRATION_API_REST**, bài này kết nối thiết kế resource, HTTP status, timeout, phân trang, idempotency, cache, OpenAPI, bảo mật và kiểm thử Java/Spring với mục tiêu độ tin cậy của API.

- **SLI (Service Level Indicator):** phép đo cụ thể phản ánh một khía cạnh trải nghiệm người dùng, ví dụ tỷ lệ request hợp lệ được phục vụ thành công, tỷ lệ phản hồi trong 300 ms hoặc tỷ lệ đơn hàng đạt trạng thái hoàn tất trong 5 phút.
- **SLO (Service Level Objective):** mục tiêu định lượng cho SLI trong **cửa sổ thời gian** xác định, ví dụ ít nhất 99,9% request hợp lệ hoàn tất thành công trong 28 ngày lăn.
- **SLA (Service Level Agreement):** thỏa thuận với bên sử dụng có thể bao gồm cam kết, điều kiện loại trừ và chế tài. **SLO nội bộ không tự động là SLA pháp lý**.
- **Error budget:** phần kết quả không đạt được phép trong cửa sổ SLO, giúp cân bằng tốc độ phát hành và ổn định hệ thống.

> Một SLI tốt phải trả lời được: **Ai đang sử dụng thao tác nào? Cái gì được tính là một cơ hội phục vụ hợp lệ? Điều kiện nào là kết quả tốt? Đo ở đâu? Trong bao lâu?**

Sau bài học, người học có thể viết định nghĩa SLI có tử số/mẫu số và ranh giới đo; thiết kế SLO availability, latency và business outcome; xuất/đọc số liệu từ Micrometer/Spring; dùng PromQL, nhận biết sai lệch từ cache/retry; lập cảnh báo dựa trên error-budget burn rate; và kiểm thử phép đo, không chỉ test status HTTP.

## 2. Biến lời hứa mơ hồ thành SLI có thể tính toán

Phát biểu “API ổn định 99,9%” chưa thể đo: 99,9% **thời gian tiến trình còn sống**, 99,9% **request trả 2xx**, hay 99,9% **ý định tạo đơn có kết quả đúng**? Mỗi lựa chọn có tập quan sát khác nhau.

Với một SLI dạng tỷ lệ sự kiện:

\[
\mathrm{SLI} = \frac{\text{số sự kiện đủ điều kiện đạt tiêu chí tốt}}{\text{tổng số sự kiện đủ điều kiện}}
\]

Mẫu số phải gồm các sự kiện “xấu” mà mục tiêu muốn phát hiện, không chỉ tập sự kiện vốn đã thành công. Một lỗi phổ biến là **đếm request trả 2xx ở cả tử số lẫn mẫu số**, khiến chỉ số gần 100% ngay khi server trả nhiều 5xx.

### 2.1. Bốn quyết định bắt buộc trong định nghĩa

| Thành phần | Câu hỏi thiết kế | Ví dụ cho GET /api/orders/{id} |
|---|---|---|
| **Population** | Những request/ý định nào đủ điều kiện? | GET đã qua xác thực, đúng route, input hợp lệ; các 5xx phải được tính |
| **Good event** | Điều kiện gì được coi là phục vụ tốt? | Trả representation được phép xem, hoặc 304 đúng quy tắc; không trả 5xx |
| **Measurement point** | Quan sát ở proxy, app, client hay workflow store? | Edge proxy kết hợp HTTP app metrics; đo cả request bị lỗi trước app |
| **Window / aggregation** | Tính theo request hay thời gian, ở khoảng nào? | Tỷ lệ theo request trong 28 ngày lăn, phân tách endpoint quan trọng |

**Không dựa vào HTTP code một cách máy móc**: 404 cho tài nguyên không tồn tại có thể là hành vi đúng; 200 với JSON sai, dữ liệu tenant khác hoặc đơn hàng được tạo trùng vẫn là trải nghiệm xấu. Vì vậy phải viết rõ loại 4xx nào bị loại khỏi availability SLI, loại nào đủ điều kiện và cần thêm SLI nghiệp vụ nào để phát hiện “HTTP xanh nhưng nghiệp vụ đỏ”.

### 2.2. Chọn đơn vị cơ hội: request, ý định hay đơn hàng

- **Request-based:** mỗi HTTP request đủ điều kiện là một cơ hội; thích hợp availability và latency. Một user gửi 10 retries có thể tạo 10 samples dù chỉ một ý định nghiệp vụ.
- **Time-based:** mỗi cửa sổ thời gian, ví dụ một phút, được đánh giá tốt/xấu; phù hợp dịch vụ cần sẵn sàng liên tục nhưng bỏ qua phân bố request giữa giờ cao/thấp điểm.
- **Intent/order-based:** mỗi ý định tạo đơn được dedup hoặc mỗi order đã chấp nhận là một cơ hội; phù hợp đo kết quả cuối cùng của workflow.

Không trộn ba đơn vị trong cùng một phân số. Với tỷ lệ request, một nhóm retry tự động có thể làm chất lượng đo thấp hơn do tăng attempts; với tỷ lệ đơn hàng, phải dùng **business key/intent ID đã deduplicate**, không lấy HTTP request ID làm mẫu số.

### 2.3. Tách SLI theo hành trình người dùng

| Journey | SLI nên theo dõi | Điều nó không thay thế |
|---|---|---|
| GET chi tiết đơn | Availability và p99/tỷ lệ dưới ngưỡng | Độ đúng quyền của dữ liệu |
| GET collection có cursor | Latency và tỷ lệ paginate hợp đồng | Tính ổn định của thứ tự/cursor |
| POST tạo đơn | HTTP acceptance, latency và business completion | Chỉ 201/202 không xác nhận workflow hoàn tất |
| POST tạo thanh toán | Outcome theo intent và chống thu tiền trùng | HTTP retry success rate |
| Xuất báo cáo bất đồng bộ | Thời gian hoàn tất, tỷ lệ job thành công | Latency của POST nhận job |

**Không dùng một SLO tổng hợp che khuất operation quan trọng.** Một route health check hoặc cache-hit GET có lưu lượng cực lớn có thể làm chỉ số trung bình trông rất tốt, trong khi POST checkout gặp lỗi đáng kể.

## 3. Availability SLI: xác định “phục vụ được” theo HTTP

Một định nghĩa ban đầu cho **GET chi tiết đơn hàng**:

**Population:** HTTP GET tới route template **/api/orders/{id}**, đã đủ điều kiện xử lý, đo tại ranh giới API mà client tiếp cận, gồm cả request bị 5xx/timeout thuộc lỗi dịch vụ. Loại trừ request sai xác thực/ACL hoặc input sai **nếu policy đã công bố rõ**, không loại bỏ request 5xx do DB/hệ thống quá tải.

**Good:** request được phục vụ bằng response đúng contract. Trong phép đo status-only của GET mẫu, **2xx và 304 sau khi kiểm quyền** là xấp xỉ tốt, còn **5xx** là xấu; các redirect 3xx khác chỉ tốt nếu hợp đồng thực sự cho phép. 404 do resource thật sự không tồn tại là **expected outcome** cần đo đúng loại hoặc exclude theo policy.

**SLO ví dụ:** ít nhất **99,9% good / eligible HTTP requests** trong **28 ngày lăn**, đo theo số request. Đây là mục tiêu thiết kế cho ví dụ, không phải “chuẩn ngành” áp vào mọi API.

~~~http
GET /api/orders/ord-17 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 10

{"type":"about:blank","title":"Service Unavailable","status":503}
~~~

Request trên là **bad event** nếu do hệ thống không phục vụ được. Nếu thay bằng 401 cho JWT hết hạn, đó là lỗi authentication của caller, thường **không nằm trong mẫu số availability phục vụ tài nguyên**; nhưng đo 401/403 riêng giúp phát hiện cấu hình xác thực hỏng. **429** có thể là throttle hợp lệ của gói sử dụng hoặc là dấu hiệu quá tải toàn cục: phải quyết định rõ có tính 429 là bad theo SLO nào, không tự mặc định bỏ hết.

### 3.1. Khi 2xx không có nghĩa “tốt”

- Server trả **200** nhưng body JSON bị cắt, schema sai hoặc dữ liệu chủ sở hữu khác: đo bằng contract checks và security tests, không chỉ HTTP success counter.
- Client timeout trước khi nhận header: application metric có thể không ghi một “completed request”; cần edge/client-side measurement hoặc synthetic checks.
- **202 Accepted** chỉ xác nhận công việc đã được nhận theo hợp đồng; fulfillment chưa xảy ra. HTTP availability có thể tốt nhưng business outcome SLI vẫn xấu.
- Server trả **304 Not Modified** cho conditional GET **sau khi đã kiểm quyền** là kết quả đúng; không biến mọi 3xx thành lỗi.
- **499/client disconnect** ở proxy và stream bị ngắt phải được phân loại theo nguyên nhân; không xóa âm thầm nếu do hệ thống chậm khiến người dùng bỏ cuộc.

### 3.2. Availability theo thời gian khác availability theo request

Ví dụ đo theo request: trong 28 ngày có **1.000.000 eligible requests**, mục tiêu 99,9% cho phép tối đa **1.000 bad requests**. Đây là **request error budget**, không phải 40 phút downtime cố định.

Nếu **đo theo thời gian**, 28 ngày có 40.320 phút và 0,1% tương đương **40,32 phút** không đạt tiêu chí. Chỉ nên quy đổi request-based SLO thành “phút downtime” khi có giả định lưu lượng đều và định nghĩa đo cho phép; nếu lỗi xảy ra đúng giờ cao điểm, 5 phút có thể tiêu tốn phần lớn request error budget.

**Không có request không đồng nghĩa service đạt 100% SLO.** Khi mẫu số bằng 0, query nên biểu thị **no data/không đủ dữ liệu**, đồng thời có synthetic monitoring nếu sản phẩm đòi availability ngay cả lúc ít traffic. Đừng viết biểu thức ép mọi cửa sổ trống thành 1.0.

## 4. Latency SLI: tỷ lệ dưới ngưỡng, không chỉ thời gian trung bình

Người mua cảm nhận request chậm hoặc checkout bị treo dù server cuối cùng trả 200. Một SLO độ trễ nên mô tả **bao nhiêu phần trăm request dưới ngưỡng nào**, đo **từ đâu đến đâu** và phân loại những request thất bại như thế nào.

Ví dụ:

| Operation | SLI | SLO minh họa |
|---|---|---|
| GET /api/orders/{id} | Eligible requests có elapsed time ≤ **300 ms** | ≥ **99%** trong 28 ngày |
| GET /api/orders?cursor=... | Eligible requests ≤ **700 ms** | ≥ **95%** trong 28 ngày |
| POST /api/orders | Request hợp lệ được **chấp nhận** ≤ **1 s** | ≥ **99%** trong 28 ngày |
| Async order completion | Ý định được chấp nhận đạt terminal outcome ≤ **5 phút** | Theo **business SLO**, không lấy HTTP acceptance latency |

Đây chỉ là **ngưỡng ví dụ**. Cần đo baseline, nhu cầu người dùng, critical path, downstream budgets và traffic trước khi chọn mục tiêu. Không đặt một ngưỡng duy nhất cho health GET, search nặng và thanh toán bất đồng bộ.

### 4.1. Vì sao p99 không thể được lấy từ average?

Giả sử 99 request mất 50 ms và 1 request mất 10 giây. Average khoảng 149,5 ms, có vẻ tốt với ngưỡng 300 ms; nhưng 1% request chịu chậm 10 giây. Đội sản phẩm phải quyết định trải nghiệm tail latency chấp nhận được thay vì chỉ hiển thị mean.

Có hai cách dùng phổ biến:

- **Ngưỡng SLI:** tỷ lệ request có latency **≤ 300 ms**. Dễ chuyển thành **good / eligible** và error budget cho latency.
- **Percentile (p95/p99):** giá trị latency tại phân vị tương ứng. Hữu ích trong dashboard, nhưng không thể **lấy trung bình các p99** từ nhiều pod để ra p99 toàn hệ thống.

Tính percentile toàn cụm từ **histogram buckets**/distribution phù hợp; không trung bình percentile từ mỗi instance. Histogram có độ phân giải theo buckets: nếu không tạo bucket ở **0.3 giây**, không thể đo chính xác tỷ lệ ≤300 ms bằng metric bucket.

### 4.2. Ranh giới đo latency

Một server timer thường tính từ lúc request vào ứng dụng tới khi hoàn thành xử lý theo instrumentation. Trải nghiệm người dùng có thể thêm **DNS/TLS/network/gateway/queueing/download**. Nên phối hợp:

1. **Edge latency** cho hành trình client thật đi qua gateway/CDN.
2. **Application latency** cho Spring MVC/WebFlux service.
3. **Downstream spans** để chẩn đoán DB/Redis/payment.
4. **Browser RUM hoặc synthetic tests** nếu màn hình người dùng là mục tiêu cuối.

Đừng lấy latency của một trace được **sample** làm mẫu thống kê SLI nếu chiến lược sampling làm mất các request thường hoặc các lỗi. SLI request nên đến từ **counter/histogram có coverage đã kiểm chứng**; tracing giúp phân tích nguyên nhân.

**Timeout cũng cần kế toán:** một request gateway trả 504 sau 5 giây có thể là bad availability **và** bad latency. Nếu một phép tính latency chỉ giữ 2xx, việc loại các request chậm nhất thất bại sẽ làm latency SLI đẹp giả. Ghi định nghĩa denominator rõ: trong ví dụ, tính cả eligible 5xx vào latency nếu quan sát được duration.

## 5. Business outcome SLI: HTTP xanh nhưng đơn hàng không hoàn tất

Một POST /api/orders có thể trả **202 Accepted** trong 80 ms, nhưng đơn bị mắc tại trạng thái PENDING_PAYMENT hàng giờ. HTTP acceptance SLI vẫn tốt; người dùng thì không nhận kết quả.

Định nghĩa workflow SLI riêng:

**Population:** các **ý định tạo đơn hợp lệ đã được API chấp nhận** và đã qua đủ thời gian quan sát (ví dụ hơn 5 phút kể từ acceptance). Mỗi idempotent logical intent chỉ tính **một lần**.

**Good:** ý định đạt **trạng thái kỹ thuật kết thúc hợp lệ** (ví dụ CONFIRMED hoặc REJECTED_WITH_BUSINESS_REASON) trong vòng **5 phút**. Một từ chối do quy tắc nghiệp vụ chính đáng có thể là *terminal outcome tốt về reliability* nhưng là *conversion thất bại* ở góc nhìn kinh doanh.

**SLO minh họa:** ít nhất **99,5% eligible intents** đạt technical terminal outcome trong 5 phút, theo cohort nhận việc trong 28 ngày lăn.

### 5.1. Phân biệt hoàn tất kỹ thuật và thành công thương mại

| Tình huống | HTTP SLI | Technical completion SLI | Business conversion |
|---|---|---|---|
| 201, đơn CONFIRMED nhanh | Tốt | Tốt | Có thể tốt |
| 202, job hoàn tất CONFIRMED trong 3 phút | Tốt | Tốt | Có thể tốt |
| 202, job PENDING quá 5 phút | Tốt lúc nhận việc | **Xấu** | Chưa xác định/thất bại theo policy |
| 202, từ chối vì thẻ không đủ tiền theo rule chính đáng | Tốt | Có thể **tốt** nếu kết thúc rõ, đúng hạn | Không chuyển đổi |
| 201 nhưng tạo hai đơn cho cùng một intent | HTTP có thể 2xx | **Xấu về tính đúng đắn/idempotency** | Dữ liệu kinh doanh sai |
| 500 nhưng payment provider đã thu tiền | HTTP xấu | Outcome chưa rõ, cần reconciliation | Nguy cơ double charge |

Không gọi chỉ số “tỷ lệ đơn được duyệt” là **reliability SLO** khi bản chất phản ánh hành vi người dùng, tín dụng, fraud hoặc nguồn cung. Có thể đo conversion riêng, nhưng đừng dùng nó để đổ lỗi cho API availability.

### 5.2. Chọn nguồn sự thật và điểm chốt thời gian

Với workflow nhiều service, sự kiện “đã hoàn tất” phải đến từ **durable order state/event log** hoặc bảng nghiệp vụ đã đối soát, không chỉ log “đã gửi message” ở HTTP controller. Các trường có ích:

~~~text
intent_id              // duy nhất cho một ý định nghiệp vụ
tenant_id              // phân vùng và bảo mật
accepted_at            // thời điểm ý định đã được chấp nhận bền vững
terminal_at            // thời điểm có terminal technical outcome
terminal_reason        // CONFIRMED, RULE_REJECTED, TECHNICAL_FAILURE...
workflow_version       // giúp giải thích thay đổi tiêu chí
~~~

Một cách tính **cohort đã đủ tuổi** trong PostgreSQL (minh họa, chưa tính loại trừ chính sách):

~~~sql
SELECT
  COUNT(*) AS eligible_intents,
  COUNT(*) FILTER (
    WHERE terminal_at IS NOT NULL
      AND terminal_at <= accepted_at + INTERVAL '5 minutes'
      AND terminal_reason IN ('CONFIRMED', 'RULE_REJECTED')
  ) AS good_intents
FROM order_intents
WHERE accepted_at >= :window_start
  AND accepted_at < :window_end
  AND accepted_at <= :measurement_now - INTERVAL '5 minutes';
~~~

SLI = **good_intents / eligible_intents** khi denominator > 0. **Không** lấy các ý định vừa được nhận 10 giây trước làm “chưa đạt 5 phút” rồi tính chúng là xấu; ngược lại, không chỉ lọc các đơn đã hoàn tất vào denominator. Lọc **tenant/permission** khi hiển thị dữ liệu cho từng khách hàng; SLO toàn hệ thống cần truy cập giám sát được ủy quyền.

Khi hệ thống dùng Kafka/queue, event có thể tới muộn hoặc lặp; cần **dedup theo intent ID** và xác định event-time vs processing-time, late-arrival correction, clock skew và dữ liệu backfill. Nếu thiếu telemetry, chỉ số không được coi mặc nhiên là tốt.

### 5.3. Idempotency và retry ảnh hưởng business SLI

HTTP attempts từ cùng Idempotency-Key không phải các intent khác nhau. Một thanh toán “retry 5 lần rồi thành công” phải tính **một ý định** ở business SLI và có thể tính nhiều attempts ở request SLI. Nếu không tách hai mức, một SDK retry mạnh sẽ làm lệch tỷ lệ theo cách không phản ánh số khách hàng bị ảnh hưởng.

Với job nhận 202, **SLO tính từ accepted_at đã commit**, không từ lúc người dùng bấm trước khi request được server nhận nếu nguồn dữ liệu chưa đo được. Nếu sản phẩm hứa end-to-end từ lúc bấm, cần client-side journey clock và đo thêm network/interaction latency.

## 6. Error budget và mức độ nghiêm trọng của việc tiêu hao

Với SLO availability **99,9%**, ngân sách xấu là **0,1%** eligible opportunities. Nếu có 1.000.000 request trong 28 ngày, budget là **1.000 bad requests**. Khi đã có 750 bad, **đã tiêu 75% budget**; nếu còn 3 ngày mới hết cửa sổ, tốc độ phát sinh lỗi trở thành tín hiệu quan trọng.

Với latency SLO **99% ≤300 ms**, budget là **1% eligible requests chậm/không đạt**. Với business completion **99,5% ≤5 phút**, budget là **0,5% eligible intents không hoàn thành đúng hạn**. Đây là **ba ngân sách khác nhau**, không cộng chúng thành một tổng phần trăm tùy ý.

### 6.1. Burn rate

\[
\mathrm{burn\ rate} =
\frac{\text{bad-event fraction trong cửa sổ quan sát}}{1 - \mathrm{SLO\ target}}
\]

Ví dụ SLO 99,9% có error-budget fraction **0,001**. Nếu trong 1 giờ gần đây có **1,44% bad events**, burn rate = **14,4×**. Với mục tiêu 28 ngày lăn, một giờ ở tốc độ này xấp xỉ tiêu **2,14%** ngân sách nếu tốc độ/traffic phân bố đồng đều; với SLO theo request, không được chuyển burn rate ngắn hạn thành % ngân sách tuyệt đối mà bỏ qua lượng traffic trong cửa sổ.

**Multi-window, multi-burn-rate alerts** giúp giảm nhiễu: ví dụ cảnh báo nhanh khi cửa sổ **1 giờ và 5 phút** đều có burn rate cao, và cảnh báo chậm khi cửa sổ **6 giờ và 30 phút** cùng xấu. Mức **14,4×/6×** là các ngưỡng tham khảo quen thuộc cho một số thiết kế alert, **không phải chuẩn bắt buộc**. Phải hiệu chỉnh theo **SLO window 28 ngày**, request volume, false positives và quy trình trực.

### 6.2. Sử dụng ngân sách để ra quyết định

- **Budget còn nhiều:** vẫn có thể phát hành, nhưng bắt buộc test/canary/rollback và theo dõi SLI.
- **Budget tiêu nhanh:** ưu tiên điều tra và giảm blast radius (rollback, feature flag, giảm tải có kiểm soát).
- **Budget gần hết:** cân nhắc hạn chế thay đổi rủi ro cao, tập trung sự cố có tác động thật thay vì tối ưu vanity metrics.

SLO **không phải công cụ phạt cá nhân**; nó là căn cứ minh bạch để cân bằng độ tin cậy, nhu cầu sản phẩm và chi phí. Một alert tốt cần liên hệ **tác động đến người dùng** và có runbook khả thi, không chỉ kích hoạt khi CPU cao.

## 7. Thu thập SLI HTTP với Spring Boot, Micrometer và Prometheus

Trong Spring MVC, HTTP server observations có thể được ghi qua **Spring Boot Actuator + Micrometer**. WebFlux cũng hỗ trợ observability, nhưng cách hoàn tất request/response streaming cần được kiểm chứng theo phiên bản và runtime. Dữ liệu từ **HTTP timer** giúp tính availability/latency; nó **không tự biết** một đơn hàng đã hoàn tất về mặt nghiệp vụ.

### 7.1. Kiến trúc đo minh họa

~~~mermaid
flowchart LR
    C[Browser / Java client] --> E[Gateway / edge]
    E --> S[Spring MVC hoặc WebFlux]
    S --> D[DB / downstream]
    E --> M[Edge metrics]
    S --> A[Micrometer observations]
    A --> P[Prometheus / metrics backend]
    M --> P
    D --> W[Durable workflow states]
    W --> B[Business SLI aggregation]
    B --> P
    P --> G[Dashboard + SLO / burn-rate alerts]
    S --> T[OpenTelemetry spans + logs]
~~~

**Ranh giới dữ liệu:**

- Gateway quan sát request thất bại **trước khi tới Spring** (TLS, queue, upstream timeout) mà server metrics không nhìn thấy.
- Application timer quan sát **URI template/method/status/outcome**. Route raw ID không nên thành nhãn; gán nhãn theo **route template** để tránh nổ cardinality.
- DB/event store là **nguồn sự thật** của business outcome; counters realtime có thể dùng để cảnh báo nhanh, nhưng phải đối soát và xử lý duplicate/missing events.
- Tracing OpenTelemetry giúp liên hệ các span, còn log giúp đọc chi tiết; **không dùng sampled traces làm mẫu số availability SLI** nếu không có sampling correction đã xác minh.

### 7.2. Cấu hình Spring Boot (minh họa, kiểm tra theo phiên bản)

Với các dependencies **spring-boot-starter-actuator**, **micrometer-registry-prometheus**, và security/config tương ứng, một cấu hình có thể là:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  metrics:
    distribution:
      slo:
        http.server.requests: 300ms,1s
~~~

Phần **management.metrics.distribution.slo.http.server.requests** yêu cầu tạo các histogram/SLO buckets có ngưỡng 300 ms và 1 s cho timer tương ứng, khi phiên bản Micrometer/Spring Boot hỗ trợ cú pháp cấu hình ấy. **Phải kiểm metrics thực xuất ra**; nếu không có bucket 0.3 giây, không thể dùng ví dụ PromQL latency bên dưới mà giả định kết quả hợp lệ. Một số phiên bản/registry còn cần điều chỉnh distribution statistics riêng.

Không phơi **/actuator/prometheus** công khai cho Internet. Đặt ở management interface riêng hoặc mạng quan sát được bảo vệ, có authentication/TLS và network policy. Health endpoint lộ thông tin nhạy cảm cũng phải hạn chế. Bật nhiều metric labels gồm raw path, JWT, userId, tenantId, idempotency key hoặc orderId có thể dẫn đến **cardinality explosion** và rò rỉ thông tin.

### 7.3. Đọc metrics HTTP một cách có điều kiện

Trong Prometheus registry, timer Spring có thể hiện dạng:

~~~text
http_server_requests_seconds_count{
  method="GET",
  uri="/api/orders/{id}",
  status="200",
  outcome="SUCCESS"
} 152394

http_server_requests_seconds_bucket{
  method="GET",
  uri="/api/orders/{id}",
  status="200",
  le="0.3"
} 150812
~~~

Đây là **tên/labels minh họa theo một cách xuất Prometheus thường gặp**; có thể khác theo phiên bản Micrometer, convention, histogram config và gateway. Không hard-code labels trong runbook trước khi inspect metrics thực của ứng dụng. Timer chỉ thu thập quan sát HTTP; **200 không chứng minh JSON đúng business contract hoặc caller có quyền**.

### 7.4. PromQL tính availability trong cửa sổ 28 ngày

Ví dụ SLI status-only: **eligible = GET tới route đã định với status 2xx/304/5xx**, loại các 4xx theo policy của ví dụ; **good = eligible không phải 5xx**. Redirect khác chỉ được tính nếu có trong contract và query được cập nhật. Query:

~~~promql
1 -
(
  sum(increase(http_server_requests_seconds_count{
    method="GET",uri="/api/orders/{id}",status=~"5.."
  }[28d]))
  /
  sum(increase(http_server_requests_seconds_count{
    method="GET",uri="/api/orders/{id}",status=~"2..|304|5.."
  }[28d]))
)
~~~

Ví dụ này **chưa phải availability SLI end-to-end hoàn chỉnh**: nó không biết response sai JSON, 404 sai do logic, timeout ở proxy, request bị chặn trước app hoặc 429 do overload. Cần tích hợp **edge metrics**, synthetic/contract checks và định nghĩa status population thực tế; nhất là quyết định có tính 429 là bad không. Không cộng số request từ edge và app vào **cùng denominator** nếu một request được đo hai lần.

**Cửa sổ trống** làm denominator bằng 0: cần no-data handling, không thay bằng “100% good”. Nếu metric bị mất, scrape target down hoặc label rename, phải có alert **telemetry coverage/target absent**, không mặc định dịch vụ đạt SLO.

Để query **increase(...[28d])** có ý nghĩa, metrics backend phải lưu dữ liệu đủ cửa sổ và có recording rules/query performance thích hợp. **increase** có thể xử lý counter reset trong những samples quan sát được, nhưng không tự tái tạo lưu lượng trong khoảng scrape mất dữ liệu.

### 7.5. PromQL đo tỷ lệ dưới ngưỡng latency 300 ms

Giả sử Prometheus export bucket **le="0.3"**, cùng tập eligible như trên:

~~~promql
sum(increase(http_server_requests_seconds_bucket{
  method="GET",uri="/api/orders/{id}",
  status=~"2..|304|5..",le="0.3"
}[28d]))
/
sum(increase(http_server_requests_seconds_count{
  method="GET",uri="/api/orders/{id}",
  status=~"2..|304|5.."
}[28d]))
~~~

Đây là **good latency / eligible requests**. Nếu client timeout ở edge không có server completion, query app-only sẽ bỏ sót nó; với SLO trải nghiệm người dùng phải bổ sung edge measurements hoặc xử lý event không hoàn thành rõ ràng.

Để **khảo sát p99** của GET ở dashboard:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      method="GET",uri="/api/orders/{id}"
    }[5m])
  )
)
~~~

Query này yêu cầu **classic histogram buckets**; với native histograms, cú pháp khác. P99 tính bằng histogram là **ước lượng**, không tương đương “99% request dưới 300 ms” nếu bucket/ngưỡng khác nhau. Không tính p99 bằng **avg(p99_per_pod)**. Dùng tỷ lệ dưới ngưỡng để tính error budget, percentile để điều tra tail latency.

### 7.6. Java/Spring: ghi business outcome có cardinality được kiểm soát

Một recorder Micrometer đơn giản có thể ghi **sự kiện chuyển trạng thái đã được xác nhận**, không ghi một sự kiện cho mỗi HTTP retry:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
final class OrderOutcomeMetrics {
    private final Counter completed;
    private final Counter failed;

    OrderOutcomeMetrics(MeterRegistry registry) {
        completed = Counter.builder("orders.workflow.outcomes")
            .description("Durable terminal order outcomes")
            .tag("result", "completed")
            .register(registry);
        failed = Counter.builder("orders.workflow.outcomes")
            .description("Durable terminal order outcomes")
            .tag("result", "technical_failure")
            .register(registry);
    }

    void recordUniqueTerminalTransition(boolean success) {
        if (success) completed.increment();
        else failed.increment();
    }
}
~~~

**Đây là lớp đo minh họa**, không tự bảo đảm “unique”: chỉ gọi sau khi **transition bền vững đã được commit**, dedup event theo intent ID trước khi ghi nếu nguồn là at-least-once message. Counter in-memory/Prometheus có thể reset khi pod restart hoặc mất samples khi scrape; vì vậy **không xem nó là nguồn sự thật duy nhất** cho SLO business xuyên nhiều ngày. Dữ liệu business nên lấy từ state store/event warehouse có cơ chế replay/đối soát.

Không thêm **orderId, accountId, email, token hoặc traceId** làm tags. Dùng các kết quả hữu hạn (**completed**, **technical_failure**, **rule_rejected**) hoặc nhóm operation ổn định. Khi cần điều tra một order cụ thể, dùng **trace/log bảo vệ bằng quyền**, không biến nó thành một time series riêng.

## 8. Traces, logs và metrics đóng vai trò khác nhau

| Tín hiệu | Câu hỏi chính | Cảnh báo sử dụng |
|---|---|---|
| **Metrics** | SLI đang xấu bao nhiêu? Xu hướng/rate/error budget? | Thiếu scrape, sample bias, cardinality và aggregation |
| **Traces** | Request này đi qua gateway/DB/downstream nào và chậm ở đâu? | Sampling có thể bỏ mẫu; trace context không phải credential |
| **Structured logs** | Sự kiện, reason code, kết quả/exception cụ thể là gì? | PII/secret, log injection và chi phí lưu trữ |
| **Synthetic checks / RUM** | Người dùng bên ngoài còn hoàn thành journey không? | Synthetic không đại diện hết traffic; RUM chịu bias trình duyệt |
| **Business state/event store** | Đơn nào được nhận, hoàn tất đúng hạn hay trùng? | Event muộn/duplicate, quyền truy cập và tính đúng đắn của state |

**W3C Trace Context** dùng headers như **traceparent** để liên kết spans. Khi client retry, các attempts có thể có spans khác nhau; **Idempotency-Key** vẫn giữ theo logical intent. Đừng gán trace ID làm idempotency key, và đừng lấy sampled span count làm số lượng đơn.

Một log có ích có thể chứa **operation=orders.create**, **status=503**, **error_code=PAYMENT_UPSTREAM_TIMEOUT**, duration bucket, environment, service version và trace ID khi chính sách cho phép. Không log raw **Authorization, cookie, request body có PII**, hoặc credentials dưới dạng baggage/tracestate. Mỗi service phải kiểm authentication/authorization độc lập với tracing; việc nhận traceparent từ Internet không chứng minh caller đáng tin.

## 9. SLO specification: từ số liệu đến dashboard và cảnh báo

Một SLO có thể dùng để điều hành chỉ khi **có người sở hữu, nguồn đo, rule tính, target, window và hành động phản ứng**. Bảng định nghĩa (SLO specification) mẫu:

| Trường | Availability GET | Latency GET | Workflow completion |
|---|---|---|---|
| **Service/operation** | orders-api / GET detail | orders-api / GET detail | orders workflow / create intent |
| **Population** | Eligible GET 2xx/3xx/5xx theo policy | Cùng eligible GET | Unique accepted intent đã đủ tuổi 5 phút |
| **Good** | 2xx/304 đúng contract; 5xx bad | Request kết thúc trong ≤300 ms | Technical terminal outcome ≤5 phút |
| **Target** | ≥99,9% | ≥99% | ≥99,5% |
| **Window** | 28 ngày lăn | 28 ngày lăn | Cohort 28 ngày lăn, chờ đủ thời gian |
| **Primary source** | Edge + app metrics đã đối soát | Histogram ở boundary đã chọn | Durable order intent states |
| **Owner** | API platform + Orders team | Orders team | Orders/Payment owners |
| **Alert/runbook** | 5xx burn, edge vs app diff | Slow-request burn, dependency latency | Stuck intents, reconciliation backlog |

Trước khi triển khai, thảo luận **có tính 429 do throttling không**, **404 che tài nguyên không tồn tại** có được coi good/neutral, **client disconnect** tính ra sao, request từ health/synthetic có nằm trong denominator không, route version cũ có chung objective không. Nếu không, đội A có thể tính 99,9% còn đội B tính 99,5% trên cùng hệ thống mà cả hai đều “đúng với query của mình”.

### 9.1. Cảnh báo từ burn rate, không chỉ ngưỡng CPU

Với availability SLO 99,9%, error fraction budget = **0,001**. Một rule minh họa:

~~~text
bad_fraction_1h = bad_requests_1h / eligible_requests_1h
bad_fraction_5m = bad_requests_5m / eligible_requests_5m

fast_burn =
    (bad_fraction_1h / 0.001 > 14.4)
    AND (bad_fraction_5m / 0.001 > 14.4)

slow_burn =
    (bad_fraction_6h / 0.001 > 6)
    AND (bad_fraction_30m / 0.001 > 6)
~~~

Đây là **pseudocode alert**, không phải rule Prometheus hoàn chỉnh; cần labels, grouping, request volume threshold, no-data policy và routing tới người trực. **Không page chỉ vì một request 500 trong năm phút khi traffic quá ít** mà không cân nhắc độ tin cậy thống kê; dùng synthetic checks khi nhu cầu phục vụ không phụ thuộc traffic.

Cảnh báo phải đi kèm **dashboard theo route, service version, vùng triển khai, gateway/app, tỷ lệ 429/5xx, latency histogram, saturation và dependency**. Tránh phân vùng theo raw userId/orderId trong metrics; muốn điều tra cá nhân, dùng logs/traces có quyền và retention phù hợp.

### 9.2. Khi SLO không còn phản ánh mục tiêu

Review lại khi chuyển **201 đồng bộ sang 202 bất đồng bộ**, thêm caching/CDN, đổi timeout ở gateway, thay cách tính business terminal state, nâng cấp Spring observation semantics hoặc chuyển tính 429 từ exclude sang bad. **Version hóa định nghĩa SLI/SLO**, đánh dấu điểm thay đổi trên dashboard và đừng nối hai chuỗi số liệu không tương thích rồi kết luận chất lượng tăng.

Ngược lại, **không đổi denominator chỉ để dashboard xanh**. Bất kỳ loại trừ nào (bot traffic, health checks, client-invalid requests) đều cần lý do, phạm vi, ngày áp dụng và kiểm thử.

### 9.3. Kết nối với OpenAPI và HTTP contract

**OpenAPI** mô tả request/response, security và các mã **200, 202, 409, 429, 503**, header Retry-After cùng schema **Problem Details** khi API có những hành vi đó. Nhưng OpenAPI không tự bảo đảm **99,9% availability**, deadline workflow hay tính duy nhất của business intent. **HTTP contract là thứ server phải thực hiện đúng trên từng request; SLO đo tỷ lệ các request/ý định đạt trải nghiệm đã xác định theo thời gian.** Khi chuyển từ 201 sang 202, phải cập nhật cả OpenAPI, integration tests và **business completion SLI**.

## 10. Kiểm thử phép đo, không chỉ kiểm thử endpoint

### 10.1. Unit test công thức và recorder Micrometer

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SliMetricTest {
    static double goodRatio(long good, long eligible) {
        if (eligible <= 0 || good < 0 || good > eligible) {
            throw new IllegalArgumentException("Invalid SLI sample");
        }
        return (double) good / eligible;
    }

    @Test
    void calculatesRatioAndAvoidsNoTrafficAsSuccess() {
        assertEquals(0.999, goodRatio(999, 1000), 1e-9);
        assertThrows(IllegalArgumentException.class,
            () -> goodRatio(0, 0));
    }

    @Test
    void recordsOnlyApprovedOutcomeLabels() {
        try (var registry = new SimpleMeterRegistry()) {
            var recorder = new OrderOutcomeMetrics(registry);
            recorder.recordUniqueTerminalTransition(true);
            assertEquals(1.0,
                registry.get("orders.workflow.outcomes")
                    .tag("result", "completed")
                    .counter().count());
        }
    }
}
~~~

Test chứng minh **công thức cơ bản** và cách recorder đếm trong bộ nhớ, **không chứng minh event đã dedup hoặc metrics exporter chạy thật**. Thêm integration tests với DB/event queue và nhiều deliveries của **cùng intent ID** để bảo đảm metric không nhân đôi; test lại khi process restart hoặc backfill.

### 10.2. MockMvc / WebTestClient: kiểm HTTP và metric cùng lúc

Với Spring MVC, dùng **MockMvc**; với WebFlux, dùng **WebTestClient**. Trong một integration test có fixture đã xác thực:

~~~java
// Fragment: MockMvc có SecurityFilterChain và controller đã cấu hình.
mvc.perform(get("/api/orders/{id}", "ord-17")
        .with(jwt()
            .jwt(j -> j.claim("tenant_id", "tenant-A"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.read"))))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value("ord-17"));

// Sau HTTP call, đọc MeterRegistry hoặc scrape test endpoint
// và xác minh đúng route template/method/status, KHÔNG có
// orderId/JWT/tenantId trong labels.
~~~

Trong thực tế cần nạp registry/observation config đúng và **xác minh metric xuất ra sau request**; một test gọi Mockito service mà không đi qua Servlet/WebFlux instrumentation sẽ không chứng minh HTTP SLI. **jwt()** là principal giả của Spring Security Test, không xác minh chữ ký/issuer/audience; cần test JwtDecoder riêng. Với HTTP qua gateway, kiểm thêm **một request được đếm một lần tại boundary đã chọn**.

### 10.3. Tình huống failure-injection bắt buộc

| Tình huống | Kỳ vọng quan sát |
|---|---|
| GET đúng quyền trả 200 | Good availability; latency bucket đúng |
| JWT không hợp lệ/tenant khác | HTTP 401/403/404 đúng policy, không lộ data; classification SLI nhất quán |
| DB outage trả 503 | Bad availability, latency nếu đủ điều kiện; không “sửa” thành 404 |
| Gateway timeout trước khi app nhận request | Edge SLI xấu; app metric có thể không có, cần đối soát |
| GET từ CDN cache hit | Edge phục vụ client; app metric có thể không tăng |
| 202 nhận job rồi workflow bị kẹt | HTTP acceptance tốt, **business completion xấu** sau cửa sổ |
| Retry POST với cùng Idempotency-Key | Nhiều HTTP attempts, **một logical intent** |
| Event terminal bị gửi hai lần | Business SLI không tăng gấp đôi |
| Scrape Prometheus mất 20 phút | Telemetry coverage alert; không tự giả định 100% |
| SSE đã gửi 200 rồi stream đứt | Không thể đổi 200 thành 500; có stream completion/error SLI riêng |
| Quota 429 do plan vs overload 429 | Tách classification và policy như đã định |
| SLO bucket latency 0.3s bị gỡ | Contract test cảnh báo thiếu bucket, dashboard không tạo tỷ lệ sai |

Với failure-injection cần chỉ rõ **phạm vi cho phép**, tránh chạy outage tests trên production không kiểm soát. Trong Testcontainers/staging, dùng fake Clock cho workflow deadline, fault simulation cho payment và timeout, và test sự kiện late/duplicate bằng dữ liệu bền vững thay vì Sleep ngẫu nhiên.

## 11. Bài tập thực hành

**Bài 1 — Tử số/mẫu số.** Trong một ngày GET order có 9.970 request 2xx/3xx, 30 request 5xx, 100 request 401 do token hết hạn. Chính sách loại 401 khỏi eligible. **Đáp án:** eligible = 10.000, good = 9.970; availability SLI = **99,7%**. Nếu SLO là 99,9%, cửa sổ này dưới mục tiêu.

**Bài 2 — Ngân sách lỗi.** 28 ngày có 2.000.000 eligible requests và SLO 99,9%; 1.600 request xấu. **Đáp án:** budget = **2.000** bad requests; đã tiêu **80%**, còn 400. Không kết luận còn “8 phút downtime” nếu đây là request-based SLI.

**Bài 3 — P99 và average.** 99 request mất 50 ms, 1 request mất 10 giây. Average có đủ để kết luận 99% dưới 300 ms? **Đáp án:** Cần đếm latency ≤300 ms: 99/100 = 99%; p99 và average có cách diễn giải khác và phụ thuộc định nghĩa/ước lượng percentile.

**Bài 4 — 202 Accepted.** API trả 202 trong 50 ms, nhưng 20% job không đạt terminal state sau 5 phút. **Đáp án:** HTTP acceptance SLI có thể đạt; **business completion SLI** không đạt nếu target cao hơn 80%. Cần workflow intent cohort, không chỉ HTTP timer.

**Bài 5 — PromQL.** Query availability chỉ tính status=200 ở cả tử và mẫu, trả 100%. **Đáp án:** Denominator bị sai; phải gồm cả bad eligible responses, ví dụ 5xx. Tách expected 4xx theo policy và xem xét edge timeouts.

**Bài 6 — Trùng sự kiện.** Kafka consumer nhận terminal event của cùng intent ba lần, counter completed tăng ba. **Đáp án:** Cần idempotent event processing/dedup theo intent ID hoặc tính lại từ durable state; counter không tự bảo đảm tính duy nhất.

**Bài 7 — Latency histogram.** Product yêu cầu 99% GET ≤300 ms nhưng Prometheus chỉ có bucket 0.1s và 1s. **Đáp án:** Không thể đo chính xác tỷ lệ dưới 300 ms từ hai bucket đó; cấu hình bucket 0.3s hoặc chọn metric/thiết kế đo phù hợp rồi kiểm exporter.

**Bài 8 — Tín hiệu vận hành.** App metrics báo 99,99% availability, gateway báo nhiều 504 trong giờ cao điểm. **Đáp án:** App chưa thấy requests bị timeout ở edge. Xác định boundary SLO từ phía client, dùng edge+app để điều tra và tránh double-counting.

## 12. Checklist trước khi áp dụng SLO

- [ ] Chỉ rõ service, operation, người dùng, eligible population và điều kiện good/bad?
- [ ] Có định nghĩa nguồn đo, đơn vị **request/time/intent** và cửa sổ lăn?
- [ ] Availability loại trừ 4xx/429 có chủ đích, không che mất 5xx và edge timeouts?
- [ ] Latency có ngưỡng/buckets đúng, phân biệt histogram ratio với percentile?
- [ ] Business outcome dựa vào **durable terminal states**, dedup và cohort đủ tuổi?
- [ ] Error budget tính riêng từng SLO; burn-rate alert có nhiều cửa sổ và no-data policy?
- [ ] Micrometer/Actuator/Prometheus được cấu hình và **kiểm thực tế** sau deploy?
- [ ] Metrics labels không có raw path, JWT, PII, userId, orderId hoặc key cardinality cao?
- [ ] Trace/log/counter được đối chiếu nhưng sampled traces không làm denominator?
- [ ] Dashboard phân route/phiên bản/vùng triển khai, có owner và runbook?
- [ ] Có MockMvc/WebTestClient, integration DB, fault injection và telemetry coverage tests?
- [ ] Khi đổi contract (202, cache, quota, version), SLO được review và version hóa?

**Kết luận:** **SLI** là phép đo được định nghĩa bằng **eligible events, good events, nguồn đo và cửa sổ**; **SLO** đặt mục tiêu cụ thể cho availability, latency và kết quả nghiệp vụ. Một REST API chỉ thật sự quan sát tốt khi số liệu phản ánh **điều người dùng nhận được**, không chỉ process đang sống hay HTTP trả 200. Spring/Micrometer/Prometheus cung cấp nền tảng đo request, còn **business state, bảo mật, hợp đồng HTTP và kiểm thử lỗi** quyết định liệu con số SLO có đáng tin để hành động hay không.
