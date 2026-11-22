# Đánh giá quota, chi phí và khả năng mở rộng

Khi phát triển chức năng gửi email bằng **Spring Framework Mail**, những ví dụ đầu tiên thường rất đơn giản: cấu hình **JavaMailSender**, tạo **SimpleMailMessage** hoặc **MimeMessage**, rồi gọi **send(...)**. Nhưng đưa hệ thống vào production đặt ra những câu hỏi kiến trúc khác hẳn: trong một phút có thể gửi bao nhiêu thư, SMTP provider giới hạn theo số lần kết nối hay theo số người nhận, làm sao không để email marketing chiếm hết quota của email OTP, và cần dự trù chi phí thế nào khi số người dùng tăng gấp mười?

**Quota** là giới hạn sử dụng do nhà cung cấp hoặc hệ thống đặt ra. **Chi phí** là toàn bộ tài nguyên và tiền cần thiết để hoàn tất vòng đời notification, không chỉ phí SMTP. **Khả năng mở rộng** là năng lực tăng khối lượng xử lý mà vẫn giữ thời gian giao hàng, độ tin cậy, bảo mật và khả năng kiểm soát.

Bài học này tập trung vào **quyết định kiến trúc** cho Spring Framework Mail: lập mô hình tải; đọc đúng hợp đồng giới hạn của provider; tính throughput, burst, backlog, concurrency và retry; tổ chức outbox, worker và rate limiting; cô lập tenant và loại email; so sánh SMTP với email API và chiến lược đa provider; lập ngân sách chi phí, theo dõi SLO, thực hiện kiểm thử tải và chuẩn bị kế hoạch ứng phó khi quota cạn.

> **Nguyên tắc quan trọng:** **JavaMailSender không tự cấp thêm quota** và **tăng số worker không đồng nghĩa gửi được nhiều email hơn**. Năng lực thực tế bị ràng buộc bởi provider quotas, giới hạn từng domain/recipient, tốc độ kết nối, chính sách chống abuse, network và downstream processing. Mọi con số giá/giới hạn trong ví dụ dưới đây đều là **giả định minh họa**, không phải báo giá hoặc hạn mức hiện hành của một nhà cung cấp cụ thể.

## 1. Vì sao quota, chi phí và scale phải được đánh giá cùng nhau?

Một kiến trúc mail có thể đáp ứng một mục tiêu nhưng thất bại ở mục tiêu khác:

| Thiết kế | Tưởng như đạt | Rủi ro khi tải lớn |
| --- | --- | --- |
| Gửi SMTP đồng bộ trong HTTP request | Đơn giản, dễ viết | Timeout request, thread bận, khó retry |
| Tạo 100 workers để gửi song song | Throughput tăng | Bị provider throttling, connection overload |
| Retry ngay mọi lỗi | “Chắc sẽ gửi được” | Retry storm, phát sinh chi phí và gửi trùng |
| Một hàng đợi cho mọi email | Ít thành phần | Marketing chặn OTP và password reset |
| Chia email thành nhiều recipients một lần gửi | Giảm số message/API calls | Lộ danh sách người nhận, provider đếm theo recipient |
| Thêm SMTP provider thứ hai | Tăng availability | Phức tạp suppression, identity, dedup và failover |
| Lưu HTML/attachment trong mọi queue message | Ít lookup lúc gửi | Queue/storage/network tốn kém, chứa PII lâu |
| Chỉ đo SMTP accepted | Dễ có dashboard xanh | Không biết delivered, bounced hay delayed |

**Đánh giá đúng** cần nhìn từ sự kiện nghiệp vụ đến người nhận: một business event có thể sinh một hoặc nhiều notifications; mỗi notification có thể được submit nhiều lần; nhà cung cấp có thể tính quota theo đơn vị khác nhau; và message accepted vẫn có thể bị bounce.

### Mục tiêu tối ưu không phải “gửi được nhiều nhất”

Với email OTP, mục tiêu thường là **độ trễ thấp và khả năng đến kịp TTL**. Với hóa đơn, mục tiêu là **độ bền, tính chính xác và khả năng đối soát**. Với newsletter, mục tiêu có thể là **chi phí/recipient, throughput và compliance**. Cùng một provider và một rate limit chung chưa chắc phù hợp cho cả ba.

## 2. Kiến trúc tổng quan của hệ thống gửi mail có kiểm soát

~~~text
                 Business Application
                         |
                         v
                  Notification Intent
                         |
             +-----------+-----------+
             |                       |
             v                       v
      Delivery policy           Template resolver
      consent / suppression     locale / revision
             |                       |
             +-----------+-----------+
                         |
                         v
              Transactional Outbox / Queue
                         |
                         v
                  Priority Scheduler
                         |
             +-----------+------------+
             |            |           |
             v            v           v
         Critical      Transactional  Bulk
         OTP / reset   Receipts       Marketing
             |            |           |
             +------------+-----------+
                          |
                          v
                Quota / Rate Controller
                - account / provider
                - tenant / purpose
                - recipient domain
                - concurrency
                          |
                          v
                  Mail Worker Pool
                          |
                          v
                  JavaMailSender / API
                          |
                          v
                  SMTP / ESP Provider
                          |
               +----------+----------+
               |          |          |
               v          v          v
           Accepted    Throttled    Rejected
               |          |          |
               v          v          v
            Track       Retry      Policy / DLQ
               |
               v
         Delivery webhooks / Bounce / Complaint
               |
               v
         Status + Suppression + Analytics
~~~

**Outbox** giữ ý định gửi bền vững. **Rate controller** áp hạn mức trước khi kết nối hoặc gọi provider. **Workers** thực hiện render/MIME và submission. **Delivery feedback** được xử lý riêng vì SMTP submission thành công chưa chứng minh thư tới hộp thư người nhận.

### Phân biệt ba tầng giới hạn

1. **Business policy**: ai được nhận, khi nào, tối đa bao nhiêu notification, có consent hay không.
2. **System capacity**: số jobs/second, workers, queues, DB, CPU, memory, network, storage.
3. **Provider allowance**: daily/monthly quota, messages/second, recipients/message, connections, payload size, reputation hoặc throttling động.

Mở rộng được tầng 2 mà không mở rộng được tầng 3 chỉ khiến workers xếp hàng và nhận lỗi nhanh hơn.

## 3. Đơn vị đo phải thống nhất trước khi tính

“Gửi 1.000 email” có thể mang nhiều nghĩa:

| Đơn vị | Ví dụ | Vì sao khác nhau? |
| --- | --- | --- |
| **Business events** | 100 đơn hàng được xác nhận | Một event có thể thông báo cho nhiều người |
| **Logical notifications** | 100 email xác nhận đơn | Có thể mỗi người nhận một mail |
| **Messages submitted** | 100 MIME messages | Một message có thể có nhiều recipients |
| **Recipient deliveries attempted** | 120 recipients trong 100 messages | Nhiều providers đếm/bill theo recipient |
| **API requests** | 60 requests tới ESP | Một request có thể chứa batch hoặc nhiều recipients |
| **SMTP transactions** | 100 MAIL FROM/DATA transactions | Không giống số connections hoặc recipients |
| **Attempts** | 107 lần gửi vì retry | Có thể tăng traffic/quota/cost |
| **Accepted recipients** | 102 recipients được provider accepted | Chưa phải delivered |
| **Delivered** | 98 recipients được server đích nhận theo telemetry | Chưa chứng minh đọc |
| **Opened/clicked** | Hành vi đo bằng tracking | Có thể bị client privacy protection làm sai lệch |

Nếu provider thông báo quota **N recipients/day**, công thức dựa trên **N JavaMailSender.send(...) calls/day** có thể hoàn toàn sai, nhất là với To/Cc/Bcc nhiều địa chỉ.

### Một MIME message nhiều người nhận

~~~java
helper.setTo(new String[] {
        "alice@example.test",
        "bob@example.test"
});
helper.setCc("team@example.test");
~~~

Về mặt ứng dụng, đây có thể là một **send(message)**. Nhưng recipient count có thể là ba, chưa kể provider có quy tắc loại bỏ duplicates hoặc tính quota riêng. Hợp đồng cụ thể phải được xác nhận với nhà cung cấp và cách vận chuyển thực tế.

### Bcc không miễn quota

Bcc tránh hiển thị địa chỉ cho các recipients khác nhưng vẫn là người nhận SMTP. Không dùng Bcc như một cách giảm quota hay thay thế chiến lược bulk sending có consent/segmentation.

## 4. Các loại quota của provider

Mỗi provider có một tập giới hạn khác nhau. Đừng chỉ hỏi “quota là bao nhiêu email/ngày”.

| Loại giới hạn | Điều cần xác minh | Tác động kiến trúc |
| --- | --- | --- |
| **Recipient count per day** | Đếm theo UTC, rolling window hay timezone? | Daily capacity và admission control |
| **Send rate** | Recipients/s, messages/s hay requests/s? | Token bucket, pacing |
| **Monthly allowance** | Billing/quota window, overage policy | Budget forecasting, cost alert |
| **Recipients per message** | To/Cc/Bcc combined? | Fan-out và privacy |
| **Connections** | Concurrent SMTP connections, connect frequency | Connection pool, worker concurrency |
| **Requests per API key** | Burst và sustained limits | API throttling, multi-tenant isolation |
| **Max message size** | Header + MIME + attachments, encoded size? | Validation trước enqueue |
| **Max payload/API batch** | Batch recipients/items/bytes | Batch sizing |
| **Authentication/identity** | Verified sender, domain, DKIM, region | Provider routing |
| **Warm-up/anti-abuse** | Dynamic throttling/new account limits | Ramp-up, backoff |
| **Bounce/complaint policy** | Threshold, suspension rules | Suppression và deliverability |
| **Account/subaccount quotas** | Có chia hạn mức theo tenant không? | Fairness, dedicated subaccounts |
| **Storage/retention** | Events, attachments, logs, webhooks | Chi phí ngoài phí gửi |

### Hard limit và soft limit

**Hard limit** là mức vượt vào có thể bị từ chối rõ ràng. **Soft limit** hoặc throttling động phụ thuộc reputation, phản hồi recipients, trạng thái provider hoặc chính sách abuse. Hệ thống cần chịu được việc allowance thay đổi mà không crash/retry storm.

### Quota tăng không đồng nghĩa deliverability tăng

Provider nâng mức gửi từ 10.000 lên 100.000 recipients/day không bảo đảm 100.000 thư tới Inbox. Sending reputation, SPF/DKIM/DMARC, complaints, bounces và tốc độ warm-up vẫn quan trọng.

### Cần biết quota là global hay theo chiều

Một account có thể bị giới hạn vừa theo **total daily**, vừa theo **requests/second**, vừa theo **destination domain**. Rate controller phải thực hiện **tất cả** constraints có liên quan; chỉ một token bucket global không đủ.

## 5. Thu thập dữ liệu thực tế để lập capacity plan

Trước khi chọn worker count hoặc mua gói provider, cần dự báo:

- Số người dùng/tenant và tốc độ tăng.
- Số business events làm phát sinh email theo ngày/giờ.
- Fan-out trung bình và tail: mỗi event gửi bao nhiêu recipients?
- Phân bố traffic: giờ làm việc, batch job, peak campaign.
- Mức trễ chấp nhận: OTP có TTL vài phút hay digest gửi trong ngày?
- Tỷ lệ failures/retries theo provider và domain.
- Kích thước trung bình và p95/p99 MIME (đặc biệt attachments).
- Mix plain/HTML, template rendering và inline images.
- Bounce/complaint/suppression rates.
- Tỉ lệ email không cần gửi do dedup, consent hoặc expired TTL.
- Số region/provider/verified domains phải vận hành.

### Lập bảng theo purpose

| Purpose | Daily logical notifications (giả định) | Peak pattern | Deadline |
| --- | ---: | --- | --- |
| **OTP/login** | 20.000 | Burst trong vài phút | Rất ngắn |
| **Order receipt** | 45.000 | Theo giờ giao dịch | Phút |
| **Operational alert** | 5.000 | Sự cố tạo spike | Ngắn |
| **Marketing** | 150.000 vào ngày campaign | Có thể dàn lịch | Giờ |

Các số này chỉ là **ví dụ giả định** để minh họa cách thiết kế mô hình. Một ngày marketing không nên lấy traffic trung bình ngày thường để dự đoán nhu cầu.

### Tính theo percentile, không chỉ average

Nếu chỉ có **10.000 email/ngày**, trung bình là khoảng 0,116 email/giây. Nhưng 3.000 email có thể đến trong một phút — **50 email/giây** trong peak window. Thiết kế cho 0,116 email/giây sẽ không đáp ứng yêu cầu “gửi gần như ngay lập tức” của burst, dù đáp ứng số email/ngày.

### Cần thống nhất cách tính time window

Tốc độ trung bình theo 24 giờ rất khác tốc độ trong một campaign 15 phút. Capacity planning cần dùng ít nhất:

~~~text
Average recipients/day
Peak recipients/minute
Peak recipients/second
Maximum burst duration
Payload size distribution
Allowed delivery delay per purpose
~~~

## 6. Công thức throughput cơ bản

Giả sử:

- \(E\) = số business events trong một window.
- \(F\) = số recipients trung bình trên một event.
- \(P\) = xác suất một notification vượt qua consent/suppression/dedup.
- \(A\) = số attempts trung bình cho một logical recipient cần gửi.
- \(T\) = độ dài window tính bằng giây.

Số recipients logic thực sự cần gửi xấp xỉ:

\[
R_{\text{logical}} = E \times F \times P
\]

Số recipient attempts:

\[
R_{\text{attempts}} = R_{\text{logical}} \times A
\]

Tốc độ attempts trung bình:

\[
\lambda = \frac{R_{\text{attempts}}}{T}
\]

**Không tự cho rằng provider billing dựa trên attempts.** Một số hệ thống tính theo recipients accepted, một số theo requests/sends hoặc có miễn phí/thang giá; phải áp điều khoản thật lên các biến phù hợp.

### Ví dụ hoàn toàn giả định

Một tháng:

~~~text
Business events:               2.000.000
Recipients per event:          1,2
Pass consent/dedup:            90%
Average attempts per recipient: 1,03
~~~

Khi đó:

~~~text
Logical recipients = 2.000.000 × 1,2 × 0,90
                   = 2.160.000

Recipient attempts = 2.160.000 × 1,03
                   = 2.224.800
~~~

Nếu provider tính tiền theo **recipient attempted**, 2.224.800 là đầu vào mô hình chi phí. Nếu tính theo **recipient accepted**, cần đo số accepted; không thể suy ra chính xác chỉ từ A.

### Đánh giá peak

Giả sử một batch có 2.400 recipients cần xử lý trong 60 giây:

~~~text
Required rate = 2.400 / 60
              = 40 recipients/second
~~~

Nếu provider cap là 20 recipients/s, không thể hoàn tất toàn bộ batch trong 60 giây trên account đó, ngay cả khi server chạy 100 threads. Tối thiểu khoảng 120 giây chỉ để submit 2.400 recipients ở rate 20/s (bỏ qua overhead, traffic khác và errors).

### SLO phải phản ánh giới hạn thực tế

Không nên tuyên bố “99% OTP gửi qua SMTP dưới 5 giây” nếu một burst 2.400 OTP/60s gặp provider chỉ cho 20 recipients/s mà không có reserved capacity hoặc admission control. Deadline, traffic peak và quota phải được thỏa **đồng thời**.

## 7. Tốc độ gửi, concurrency và giới hạn của worker pool

**Rate** là số đơn vị công việc xử lý mỗi giây. **Concurrency** là số tác vụ đang chạy đồng thời. Chúng có liên quan nhưng không đồng nghĩa.

Giả sử provider cho phép tối đa 20 recipient attempts/giây và một lần gửi mất trung bình 400 ms. Theo quan hệ kiểu **Little's Law** ở trạng thái ổn định:

\[
L \approx \lambda \times W
\]

Với throughput 20 attempts/giây và thời gian mỗi attempt 0,4 giây:

~~~text
Average concurrency ≈ 20 × 0,4 = 8 active attempts
~~~

Điều này **không có nghĩa** luôn cấu hình chính xác 8 threads là tối ưu. Latency biến thiên, một attempt có thể chứa nhiều recipients và overhead rendering/DB khác với thời gian SMTP; cần đo theo từng stage và giới hạn độc lập.

### Worker count không phải send rate

~~~text
40 threads × unlimited sends
    -> có thể tạo 100+ requests/s
    -> provider throttle / reject
    -> retries và queue tăng

40 threads + global rate limit 20 recipients/s
    -> attempt được pacing
    -> không vượt quota dự kiến
~~~

Tăng threads từ 20 lên 40 khi provider vẫn cap 20/s chỉ giúp giữ thêm I/O đang chờ, không tự tăng số recipients được chấp nhận. Quá nhiều connections còn có thể gây socket exhaustion, throttling và memory pressure.

### Sizing theo p95 latency

Ngoài latency trung bình, đo **p95/p99 submission latency**. Nếu provider thỉnh thoảng mất 2 giây/attempt và muốn bám rate 20/s trong peak, worker concurrency có thể phải lớn hơn 8 để không bị idle. Tuy nhiên vẫn áp rate limit 20/s và connection cap riêng.

### Tách các giới hạn

~~~text
Max executor threads:            32
Max concurrent SMTP connections: 12
Provider recipient rate:         20/s
Provider daily recipient cap:    50.000/day
Bulk purpose cap:                 8/s
Critical purpose reserve:        at least 5/s
~~~

Đây chỉ là profile minh họa. Hệ thống cần chọn **ngưỡng thực tế thấp hơn hoặc bằng provider contract**, chừa headroom cho bursts, throttling động và hệ thống khác chia cùng credentials.

## 8. Queue backlog và thời gian tiêu hết hàng đợi

Khi tốc độ đến lớn hơn tốc độ xử lý, backlog tăng.

Gọi:

- \(\lambda\) = tốc độ công việc đến (recipients/giây).
- \(\mu\) = tốc độ phục vụ hữu hiệu (recipients/giây).
- \(B\) = backlog hiện tại (recipients tương đương).

Nếu \(\lambda < \mu\) và hai tốc độ tương đối ổn định, thời gian dự kiến để tiêu backlog:

\[
T_{\text{drain}} \approx \frac{B}{\mu-\lambda}
\]

Nếu \(\lambda \geq \mu\), backlog không thể tự giảm dưới giả định tốc độ không đổi.

### Ví dụ

~~~text
Provider effective rate:    18 recipients/s
Traffic arriving:           10 recipients/s
Backlog currently:           4.800 recipients

Net drain rate = 18 - 10 = 8/s
Approx drain time = 4.800 / 8 = 600 seconds = 10 minutes
~~~

Thời gian thực có thể dài hơn do connection setup, job visibility, per-domain throttling, retry và quota window; đây là estimate phục vụ quyết định, không phải SLA cam kết.

### Khi provider downtime

~~~text
Provider capacity: 0/s
New traffic:       8/s
Downtime:          15 minutes

New backlog ≈ 8 × 15 × 60 = 7.200 recipients
~~~

Sau khi provider phục hồi, hệ thống cần **drain strategy**: pacing theo quota, ưu tiên các notification còn thời hạn, bỏ/đánh dấu expired OTP phù hợp và không gửi tất cả cùng lúc.

### Đo tuổi công việc, không chỉ số job

Hai queues có 500 jobs nhưng khác nhau:

~~~text
Queue A: oldest pending age = 10 seconds
Queue B: oldest pending age = 3 hours
~~~

Đối với OTP, 3 giờ là không chấp nhận; đối với digest có thể chưa vi phạm. Dashboard nên theo dõi backlog theo **purpose và oldest age/p95 delay**, không chỉ số email đang đợi.

## 9. Admission control trước khi queue phình không giới hạn

Nếu provider giới hạn 10.000 recipients/ngày nhưng ứng dụng tạo 1.000.000 notifications/ngày, một queue vô hạn không phải giải pháp. Nó chỉ biến vấn đề quota thành vấn đề storage, TTL và chi phí.

**Admission control** quyết định có nên cho công việc mới vào hệ thống hay không dựa trên:

- Delivery purpose và mức quan trọng.
- Quota còn lại và rate dự kiến.
- Deadline và thời gian queue có thể đáp ứng.
- Suppression/consent và các điều kiện không cần gửi.
- Số jobs đang pending.
- Tenant budget, campaign allocation.
- Khả năng failover hoặc dàn lịch.

### Quyết định theo loại email

| Purpose | Khi capacity thiếu | Chính sách gợi ý |
| --- | --- | --- |
| OTP / reset | Deadline rất ngắn | Ưu tiên capacity, hủy đúng thời hạn nếu không thể gửi |
| Fraud/security alert | Quan trọng và có thể khẩn cấp | Reserved capacity, đường dự phòng đã kiểm thử |
| Receipt / invoice | Cần audit | Queue bền vững, retry, cảnh báo trễ |
| Product activity digest | Có thể trì hoãn | Gộp/dàn lịch, tránh gửi trùng |
| Marketing | Thường có tính linh hoạt lịch | Throttle, pause, phân bổ tenant budget |

### Không che giấu việc không đáp ứng được

Nếu OTP không thể được gửi trong TTL, hệ thống nên trả một trạng thái có nghĩa như **TEMPORARILY_UNAVAILABLE** hoặc cho người dùng lựa chọn xác minh khác nếu được hỗ trợ, không trả “đã gửi” chỉ vì đã tạo outbox row.

### Bounded queues

Đặt giới hạn kích thước queue hoặc giới hạn số jobs pending cho từng purpose/tenant. Nhưng không drop bừa các events quan trọng: nếu không nhận thêm được, phải có **backpressure, reject/retry-later ở điểm phát sinh** hoặc cơ chế lưu bền vững theo policy.

## 10. Daily quota và cách giữ phần dự phòng

Quota theo ngày tạo một giới hạn khác với rate theo giây. Một app có thể gửi 5 recipients/second (dưới giới hạn 20/s) nhưng vẫn cạn quota ngày.

### Công thức reservation

~~~text
Daily provider allowance:          50.000 recipients
Reserved for security/critical:    10.000 recipients
Reserved for transactional:        25.000 recipients
Bulk marketing budget:             10.000 recipients
Safety/unallocated headroom:        5.000 recipients
~~~

Tổng allocation bằng 50.000. Đây là ví dụ quản lý **policy budget**, không phải tất cả providers hỗ trợ reservation ở hạ tầng.

Nếu bulk muốn sử dụng capacity chưa dùng của transactional, scheduler có thể cho **borrowable capacity** với điều kiện không làm mất reserve cho critical trong window phù hợp.

### Window reset cần được hiểu chính xác

Một nhà cung cấp có thể dùng:

- Calendar day tại một timezone định nghĩa.
- Rolling 24-hour window.
- Billing month.
- Per-minute hoặc per-second sliding window.
- Tổ hợp nhiều windows đồng thời.

Ứng dụng không thể tự giả định quota reset lúc **00:00 giờ server**. Cần tính theo hợp đồng provider, đồng bộ thời gian đáng tin và kiểm tra quota status qua API/telemetry nếu có.

### Gửi gần cuối quota window

Nếu allowance còn 100 recipients nhưng 500 email transactional đang chờ, không được cho một campaign 100 recipients chiếm hết trước khi critical jobs được xét. Reserve/fairness phải hoạt động **trước khi send**, không chỉ trên báo cáo cuối ngày.

### Adaptive reserve

Vào mùa cao điểm, tỷ lệ critical traffic có thể tăng. Có thể điều chỉnh reserve từ dữ liệu và risk policy; không nên cố định quota marketing vô điều kiện khi OTP đang trễ.

## 11. Rate limiting: thuật toán và phạm vi áp dụng

Các cơ chế phổ biến:

| Thuật toán | Ý tưởng | Phù hợp |
| --- | --- | --- |
| **Token bucket** | Tokens được nạp theo tốc độ, có burst capacity | Provider có burst + sustained rate |
| **Leaky bucket / pacing** | Đầu ra tương đối đều | Tránh spikes khi ESP nhạy cảm |
| **Fixed window** | Đếm theo khoảng thời gian cố định | Daily/hourly quotas, cần xử lý biên window |
| **Sliding window** | Đếm các attempts trong cửa sổ trượt | Quota rolling window |
| **Concurrency semaphore** | Giới hạn số I/O đang chạy | SMTP connections và client resource |
| **Weighted fair scheduling** | Chia năng lực cho tenant/purpose | Tránh starvation |

### Token bucket vận hành thế nào?

~~~text
Rate:     10 tokens/second
Capacity: 30 tokens

At idle: bucket fills up to 30
Burst:   send up to 30 recipient-units
After:   replenish roughly 10 per second
~~~

Nếu provider chỉ cho **exactly 10 requests/s with no burst**, bucket capacity 30 có thể **vi phạm quota**. Thuật toán và cấu hình phải khớp với semantics thật, không phải chọn một library default bất kỳ.

### Cost theo recipients, không chỉ theo messages

Một request có 10 recipients cần tính **10 tokens** nếu limiter bảo vệ recipient quota. Nếu provider đồng thời giới hạn requests/s, cần thêm limiter theo requests.

### Composite permit

~~~text
Request wants 4 recipients
      |
      +-- Global provider rate permits >= 4?
      +-- Daily account quota has >= 4?
      +-- Tenant budget has >= 4?
      +-- Purpose budget allows?
      +-- Recipient-domain throttle allows?
      '--> SMTP connection slot available?
                    |
                    v
                Submit
~~~

Cần thiết kế reservation/rollback của permits khi một phép kiểm tra thất bại; không nên tiêu từng quota rồi bỏ cuộc nửa chừng mà không có định nghĩa semantics. Với quota provider, sau network failure **không thể luôn biết** một attempt đã được tính hay chưa, vì vậy local counters chỉ là ước lượng và cần đối soát.

## 12. Distributed rate limiting trong nhiều replicas

Một limiter in-memory trong mỗi pod:

~~~text
Provider cap: 20 recipients/s

Pod A limiter: 20/s
Pod B limiter: 20/s
Pod C limiter: 20/s

Aggregate possible: 60/s -> vượt cap
~~~

Đây là lỗi rất thường gặp khi scale horizontally. Nếu quotas áp cho **cùng account/API key**, limiter phải điều phối ở cùng phạm vi.

### Các chiến lược

1. **Central sender pool**: một cụm workers có scheduler/limiter chung.
2. **Distributed token bucket**: dùng state atomic ở Redis hoặc datastore phù hợp.
3. **Quota leases**: một controller cấp ngân sách nhỏ theo window cho các workers, reclaim khi hết hạn.
4. **Provider-native throttling feedback**: thích ứng theo response headers/API metrics.
5. **Static partitions**: chia hẳn quota theo subaccount/provider/tenant nếu contract cho phép.

### Phải biết failure mode của limiter

Redis/central limiter unavailable thì làm gì?

- **Fail closed**: tạm dừng submission, tránh spam/vi phạm quota.
- **Conservative local fallback**: chỉ khi đã thiết kế quota tối thiểu cho từng node.
- **Fail open**: thường rủi ro cao với provider quota và email quan trọng.

Quyết định tùy purpose/rủi ro, nhưng cần cấu hình có kiểm thử, không để thư viện tự hành xử một cách không rõ.

### Clock và concurrency

Distributed limiter cần cân nhắc clock skew, atomic updates, network partition và TTL. Nếu dựa vào thời gian từ nhiều nodes khác nhau, window accounting có thể sai. Có thể dùng server-side time hoặc central authority theo thiết kế.

### Limiter không thay thế durable queue

Rate limiter có thể trả **WAIT/NO_PERMIT**; job phải được reschedule an toàn, không giữ một thread ngủ lâu cho mỗi email khi backlog hàng trăm nghìn jobs.

## 13. Fairness: không để một tenant hoặc campaign chiếm toàn bộ năng lực

Với hệ thống đa tenant, một khách hàng enterprise có thể lên lịch gửi 200.000 marketing emails trong khi các tenant khác chỉ cần một vài OTP. Một queue FIFO duy nhất có thể làm các job quan trọng nằm sau toàn bộ campaign.

### Phân lớp lưu lượng

~~~text
                        Email intents
                             |
                +------------+------------+
                |            |            |
                v            v            v
             Critical    Transactional    Bulk
               Queue         Queue        Queue
                |            |            |
                +------------+------------+
                             |
                             v
                    Weighted Scheduler
                             |
                      Global Quota Gate
                             |
                       Sender Workers
~~~

Một policy giả định:

~~~text
Critical minimum:      30% of available rate
Transactional minimum: 40%
Bulk maximum:          30% when contention
Unused reserved rate:  borrowable if safe
~~~

Đây là tỷ lệ gợi ý cho ví dụ; quota thật phải dựa vào traffic profile và SLA. **Priority tuyệt đối** cũng có thể làm bulk starvation nếu critical liên tục, nên cần chiến lược cân bằng/aging cho những jobs không có deadline ngắn.

### Weighted fair queueing và priority

| Mục tiêu | Cách tiếp cận |
| --- | --- |
| OTP không chờ campaign | Reserved quota/priority lanes |
| Tenant lớn không chặn tenant nhỏ | Per-tenant budget hoặc weighted fair shares |
| Marketing không bị bỏ vô hạn | Aging, campaign windows, minimum shares |
| Hóa đơn không bị reorder sai logic | Per-aggregate sequencing nếu nghiệp vụ cần |
| Không vượt provider quota | Global limiter sau scheduler |

### Multi-tenant isolation ở provider

Một provider có thể hỗ trợ subaccounts/API keys với quotas riêng. Điều này giúp phân tách reputation và chi phí, nhưng cần xác nhận:

- Subaccount có **quota độc lập hay cùng parent quota**?
- Domain verification/DKIM có khác nhau không?
- Bounces/complaints được áp cho tenant hay toàn bộ account?
- Có thể phân tích billing/usage theo tenant không?
- Chuyển tenant sang provider khác có hợp đồng/authorization phù hợp không?

Không tạo hàng chục accounts chỉ để lách quota hoặc điều khoản provider; phải thiết kế đúng chính sách và yêu cầu pháp lý.

## 14. Retry amplification: lỗi càng nhiều càng tốn quota

Nếu tất cả send attempts đều có tỷ lệ lỗi độc lập \(p\) và retry cho tới thành công không giới hạn, số attempts kỳ vọng là:

\[
A = \frac{1}{1-p}
\]

Ví dụ \(p=0{,}1\):

~~~text
Expected attempts = 1 / (1 - 0,1)
                  ≈ 1,111 attempts per recipient
~~~

**Mô hình này chỉ đúng với lỗi độc lập và retry không giới hạn**, không phản ánh một outage kéo dài hay hard quota exhausted. Production phải giới hạn attempts và có deadline.

Với tối đa \(N\) attempts, ước lượng theo cùng giả định:

\[
A_N = \sum_{k=0}^{N-1} p^k
\]

Ví dụ 3 attempts với p=0,1:

~~~text
Expected attempts = 1 + 0,1 + 0,01
                  = 1,11
~~~

### Outage làm giả định độc lập sai

Khi ESP gặp sự cố 20 phút, gần như mọi retry trong giai đoạn đó có thể thất bại. Nếu 10.000 jobs retry mỗi 5 giây:

~~~text
10.000 jobs / 5 seconds = 2.000 attempts/s
~~~

Đây có thể gấp hàng trăm lần mức bình thường, gây retry storm và tăng recovery time. Thay vì mỗi job retry sát nhau, dùng **exponential backoff + jitter**, circuit breaker/adaptive throttling và một scheduler điều phối.

### Retry chỉ cho lỗi phù hợp

| Loại outcome | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Transient, chắc chưa accepted** | Không kết nối được SMTP trước khi giao dữ liệu | Retry có backoff |
| **Provider throttled** | Rate/quota feedback | Tôn trọng retry-after/đợi window |
| **Permanent recipient reject** | Địa chỉ sai hoặc không cho phép | Không retry vô hạn, suppression/review |
| **Authentication/config error** | Credentials hoặc verified domain sai | Dừng lane/provider, alert |
| **Template/model invalid** | Thiếu biến required | Không retry SMTP, sửa nội dung |
| **UNKNOWN SMTP result** | Timeout sau khi DATA có thể đã accepted | Reconciliation/risk policy |
| **Recipient complaint/bounce** | Provider report | Suppression và điều tra reputation |

### Retry budget

Ngoài quota gửi, nên có **retry budget**:

~~~text
Max attempts per notification:        5
Max retry traffic share:             15% of provider capacity
Max age for OTP retry:                before token expiry
Max age for transactional retry:      by business SLA
Max daily tenant retry consumption:  configured budget
~~~

Các mức trên là ví dụ, không phải giá trị tối ưu mặc định. Retry budget tránh để một provider outage chiếm toàn bộ capacity khiến traffic mới cũng thất bại.

## 15. Tại sao SMTP outcome có thể mơ hồ?

Một đoạn:

~~~java
sender.send(message);
~~~

có thể ném exception khi socket bị reset. Nhưng vị trí thất bại quan trọng:

~~~text
Client -> SMTP server: MAIL FROM
Client -> SMTP server: RCPT TO
Client -> SMTP server: DATA + message bytes
Server -> Client:      acceptance response
~~~

Nếu client đã truyền đủ DATA nhưng bị mất response, **server có thể đã accepted**. Retry vô điều kiện có thể làm người nhận nhận hai emails giống nhau, cả hai đều tiêu phí/quota theo provider policy.

### Idempotency khác nhau giữa transport

Một số ESP APIs có thể hỗ trợ request idempotency key hoặc querying delivery by request ID; SMTP tiêu chuẩn không có một cơ chế exactly-once chung cho mọi provider. Cần kiểm tra provider hợp đồng thực tế.

### Notification identity

~~~text
notificationId: logical business notification
attemptId:      each transport submission attempt
providerId:     accepted message / request ID if reported
templateRevision: pinned content
recipientId:    logical recipient
~~~

Giữ tách những định danh này giúp đối soát và tránh nhầm “retry cùng notification” với “tạo notification mới”.

### Không dùng Message-ID header như dedup bảo đảm

Email Message-ID hỗ trợ correlation/threading nhưng không khiến SMTP provider tự bỏ một message trùng khi được submit lại. Nếu muốn idempotency, cần business key, provider-supported mechanism nếu có, attempt history và reconciliation.

## 16. Retry backoff, jitter và quota feedback

Một lịch thử có giới hạn có thể dùng:

\[
d_k = \min(d_{\max}, d_0 \times 2^{k-1})
\]

Sau đó thêm jitter, ví dụ chọn một khoảng ngẫu nhiên trong giới hạn an toàn để tránh tất cả jobs thức dậy cùng lúc.

~~~text
Attempt 1: immediate
Attempt 2: after ~1-2 seconds
Attempt 3: after ~2-4 seconds
Attempt 4: after ~4-8 seconds
Attempt 5: after ~8-16 seconds
~~~

**Lịch trên chỉ minh họa**, không dùng nguyên cho OTP nếu TTL còn quá ngắn hoặc quota window cần đợi lâu hơn.

### Tôn trọng Retry-After

Với ESP HTTP API, provider có thể trả **429** và **Retry-After** (nếu được hỗ trợ). App phải hiểu header là seconds hoặc HTTP date theo hợp đồng, đồng thời giới hạn retry theo business expiry. SMTP có mã reply 4xx/5xx và enhanced status codes khác; không gán giả một HTTP status cho SMTP.

### Circuit breaker và bulkhead

Khi provider liên tục timeout:

~~~text
Provider A unhealthy
    -> circuit opens
    -> pause A submissions
    -> reschedule eligible jobs
    -> optional failover to preconfigured B
    -> probe A after cool-down
~~~

Không dùng circuit breaker để tự drop notification hoặc bypass durable status. **Bulkhead** tách thread/connections/pool của từng provider hoặc purpose để một nơi chậm không giữ hết tài nguyên.

### Retry budget theo nguyên nhân

Một provider rate limit 60s nên được xử lý khác mạng chập chờn vài giây. **Lỗi quota depleted cho tới ngày mới** không nên biến thành hàng triệu retries trong cùng window.

## 17. Priority và deadline cho OTP, reset và security mail

Với notification có deadline, **độ trễ tổng** quan trọng hơn raw throughput:

\[
T_{\text{end-to-end}} =
T_{\text{enqueue}} +
T_{\text{queue wait}} +
T_{\text{render}} +
T_{\text{quota wait}} +
T_{\text{submit}} +
T_{\text{provider delivery}}
\]

Không phải mọi phần đều đo được chính xác: **provider delivery** có thể không có telemetry hoặc diễn ra bất đồng bộ. Hệ thống cần định nghĩa SLO theo ranh giới đo có thể xác nhận, ví dụ **accepted by provider** trong một khoảng thời gian, và không gọi nó là user received.

### TTL-based scheduling

~~~text
OTP created at 10:00:00
OTP expires at 10:05:00

At 10:04:55:
  job still pending
  estimated quota wait = 30 seconds
  -> sending now may be useless
~~~

Một scheduler có thể đánh dấu **EXPIRED** hoặc phát thông báo trạng thái thay thế theo nghiệp vụ. Không cố gửi token đã hết hạn như thể vẫn hữu ích.

### Deadline và priority là hai chiều khác nhau

Một alert bảo mật có thể quan trọng nhưng không có hard TTL 30 giây; một OTP có thời hạn rất ngắn. Scheduler nên xét purpose, deadline, expected completion và fairness; không chỉ dùng một số nguyên priority tuyệt đối.

### Reserve capacity phải được thực thi

Nếu bulk job được cấp toàn bộ account quota cho ngày, critical reservation trên bảng giấy không còn tác dụng. Admission controller và quota ledger phải áp reservation trước mọi submission, hoặc dùng provider/subaccount tách biệt khi được phép.

## 18. Chiến lược batch và fan-out

**Batching** có thể giảm overhead API hoặc render, nhưng phải giữ privacy, tracking và quota accounting đúng.

### Một email gửi cho nhiều người không luôn phù hợp

~~~text
To: alice@example.test, bob@example.test, carol@example.test
Subject: Your account details
~~~

Một message gửi nhiều người không phù hợp cho tài khoản cá nhân, OTP, nội dung có dữ liệu riêng hoặc unsubscribe token per-recipient. Nó cũng có thể làm lộ email addresses cho những recipients khác.

### Batch API của ESP khác multi-recipient MIME

Một ESP có thể cho một API request chứa nhiều personalization entries và gửi các messages riêng cho từng recipient. Cần đọc hợp đồng thật:

- Quota đếm một API request hay tất cả recipients?
- Rate limit theo batch objects hay recipients?
- Có idempotency cho từng item không?
- Response có partial success không?
- Mỗi item có provider ID độc lập để đối soát không?
- Payload size tối đa là bao nhiêu?

Không dùng batch chỉ vì giảm request count nếu nó khiến retry partial failures khó kiểm soát.

### Batch window ảnh hưởng latency

Chờ gom 1.000 emails mới gửi có thể tối ưu overhead nhưng làm OTP trễ. Có thể dùng batch cho marketing/digest và single/low-latency submission cho critical. Các batch jobs cần max waiting time và max size có cấu hình.

### Fan-out có thể được giảm bằng nghiệp vụ

Thay vì gửi 20 emails cho 20 hành động nhỏ:

~~~text
20 low-priority events
    -> aggregate daily digest
    -> 1 notification
~~~

Nhưng **không gộp** email mang ý nghĩa pháp lý, giao dịch hoặc bảo mật chỉ để tiết kiệm nếu nghiệp vụ yêu cầu sự kiện riêng. Optimization phải được domain policy cho phép.

## 19. Cấu trúc chi phí: không chỉ có giá gửi thư

Mô hình chi phí production nên tính **total cost of ownership (TCO)**:

\[
C_{\text{total}} =
C_{\text{provider}} +
C_{\text{compute}} +
C_{\text{storage}} +
C_{\text{network}} +
C_{\text{observability}} +
C_{\text{operations}} +
C_{\text{compliance}}
\]

### Các nhóm chi phí

| Nhóm | Ví dụ | Yếu tố làm tăng |
| --- | --- | --- |
| **Provider send charges** | Theo recipients, volume tiers, subscription, overage | Tăng email/recipient count |
| **Dedicated IP / warm-up** | Gói IP riêng, reputation management | Volume/segmentation và deliverability |
| **Compute** | Worker CPU, memory, connections | Render HTML, MIME/attachments, retry |
| **Database** | Outbox rows, indexes, transactions | Attempts/history/retention |
| **Queue/broker** | Storage, requests, data transfer | Backlog và payload size |
| **Attachments/object storage** | Store/read files, scanning | Số lượng, dung lượng, retention |
| **Network egress** | Upload email/attachment, cross-region | Bytes × attempts |
| **Observability** | Logs, traces, metrics | Cardinality, raw MIME, event volume |
| **Delivery feedback** | Webhook ingestion, event retention | Bounce/delivery/open/click signals |
| **Operations** | On-call, incidents, provider support | Sự phức tạp, multi-provider |
| **Compliance/security** | Data residency, audits, encryption, retention | Quyền truy cập, thời gian lưu |

Không có bảng giá áp dụng cho mọi nhà cung cấp. Một provider có tier miễn phí, một provider có phí base + giá theo 1.000 recipients, provider khác tính theo API requests hoặc tùy loại email. Công thức phải phản ánh **hợp đồng/biểu giá đang hiệu lực** khi ra quyết định mua.

## 20. Công thức tính chi phí gửi cho các kịch bản

Giả sử provider tính tiền theo **billable recipient units**, với mức giá \(p\) cho mỗi 1.000 units và phí thuê bao \(C_0\):

\[
C_{\text{provider}} =
C_0 + \frac{R_{\text{billable}}}{1000} \times p
\]

Nếu có tiers, dùng **piecewise pricing** theo từng mức thay vì nhân toàn bộ volume với giá của tier cuối.

### Ví dụ giả định (không phải báo giá)

~~~text
Logical recipient volume/month:  2.160.000
Billable units (assumed):        2.160.000
Illustrative price:             0,15 USD / 1.000 units
Illustrative fixed fee:         50 USD/month
~~~

Tính:

~~~text
Variable fee = 2.160.000 / 1.000 × 0,15 USD
             = 324 USD
Provider estimate = 50 + 324 = 374 USD/month
~~~

Ví dụ này **cố ý giả định billable = logical recipients**. Nếu provider tính theo attempts, accepted recipients, reserved volume hoặc volume tiers, kết quả sẽ khác. Thuế, support plan, IP, network và nội dung đính kèm cũng chưa được cộng.

### Đơn vị chi phí cần dùng nhất quán

Có thể theo dõi:

~~~text
Cost / 1.000 logical notifications
Cost / 1.000 recipient attempts
Cost / 1.000 accepted recipients
Cost / 1.000 delivered recipients (nếu telemetry đủ)
Cost / one successful business notification
~~~

Các số này khác nhau. Nếu 100.000 recipients được submit nhưng chỉ 90.000 recipients delivered, **chi phí/1.000 delivered** cao hơn chi phí/1.000 submit, ngay cả khi provider đơn giá không đổi.

## 21. Mô hình kịch bản tăng trưởng và sensitivity analysis

Không chọn provider dựa trên một projection “giá trung bình tháng tới”. Hãy xây ít nhất ba kịch bản:

| Giả định | Base | Growth | Stress |
| --- | ---: | ---: | ---: |
| Logical recipients/month | 1.000.000 | 3.000.000 | 8.000.000 |
| Attempts/recipient | 1,02 | 1,04 | 1,12 |
| Peak recipients/s | 30 | 120 | 400 |
| MIME size p95 | 100 KiB | 150 KiB | 500 KiB |
| Maximum burst | 5 phút | 15 phút | 30 phút |
| Provider outage exercise | 5 phút | 30 phút | 2 giờ |

**Tất cả số liệu trong bảng là giả định bài tập**; không phải năng lực được xác minh của Spring Mail/provider.

### Tham số nhạy nhất thường là gì?

- **Volume** ảnh hưởng trực tiếp provider fees và queue/storage.
- **Peak rate** quyết định khả năng đạt SLO và rate limits.
- **Retry factor** có thể tăng rất nhanh khi provider lỗi.
- **Payload size** chi phối network, memory và storage.
- **Per-domain delivery rate** có thể là bottleneck dù provider global quota còn dư.
- **Outage duration** quyết định backlog cần giữ và recovery drain time.

### Tính ngưỡng hòa vốn

Giả sử phương án A có phí cố định thấp và phí biến đổi cao; phương án B có phí cố định cao nhưng đơn giá thấp. Có thể giải:

\[
C_{0A}+r\,p_A=C_{0B}+r\,p_B
\]

trong đó \(r\) là số nghìn billable units. Ngưỡng giao nhau chỉ hữu ích khi hai phương án có **độ tin cậy, sender reputation, tính năng compliance và deliverability** tương đương hoặc đã được đánh giá riêng.

### Không bỏ qua migration cost

Một provider rẻ hơn 10% có thể khiến team mất nhiều tháng để tích hợp event tracking, thay domain verification và test compatibility. Chi phí kỹ thuật và rủi ro vận hành có thể vượt phần tiết kiệm phí gửi.

## 22. Chi phí MIME payload, attachments và egress

Một email HTML 30 KiB không có attachment có profile hoàn toàn khác email hóa đơn gắn PDF 5 MiB.

### Base64 làm tăng bytes truyền

Binary attachment thường được MIME transfer encode (ví dụ base64). Base64 có overhead xấp xỉ **4/3** trước khi tính line wrapping và MIME headers.

~~~text
PDF binary size:      5 MiB
Base64 approximate:   5 × 4/3 ≈ 6,67 MiB
MIME overhead:        headers, boundaries, line breaks, body...
~~~

Nếu gửi 10.000 attachments như vậy:

~~~text
Approx encoded payload = 10.000 × 6,67 MiB
                       ≈ 65 GiB
~~~

Đây là ước lượng payload của outbound email, không phải hóa đơn egress: network đường đi, TLS và cách provider nhận dữ liệu có thể khác. Với **nhiều retry**, có thể truyền lại cùng bytes nhiều lần.

### Tại sao file 20 MiB có thể vượt giới hạn 25 MiB?

Max MIME size thường có thể tính **toàn bộ message sau encoding**, không chỉ file gốc. Binary 20 MiB thành khoảng 26,7 MiB base64 trước overhead khác, nên không được lấy attachment limit bằng đúng limit tổng message của provider.

### Có nên chuyển attachment thành link?

Với file lớn, có thể gửi **trusted signed download link** thay vì attach bytes:

~~~text
Recipient receives:
  "Your report is ready"
  https://app.example.test/download/opaque-id
~~~

Lợi ích: giảm egress qua SMTP, email nhẹ hơn và có thể kiểm soát truy cập. Nhưng cần:

- Authentication/authorization cho file.
- TTL của signed link, policy resend.
- Data residency và retention.
- Accessibility, mobile experience.
- Không lộ token/file ID trong logs hoặc analytics.
- Không thay file lịch sử mà email đang tham chiếu.

Không thay attachments pháp lý/bắt buộc bằng links nếu nghiệp vụ hoặc regulation yêu cầu tệp gửi trực tiếp.

## 23. Chi phí lưu outbox và lịch sử attempts

Một hệ thống reliable cần lưu:

~~~text
Notification row
  - notificationId
  - tenant/purpose
  - recipient reference
  - template revision
  - model snapshot reference
  - status and timestamps

Attempt rows
  - attemptId
  - provider
  - started/ended
  - outcome category
  - provider message ID

Delivery events
  - accepted/delivered/bounced/complaint
  - event timestamp
  - source signature validation
~~~

Nếu lưu mỗi email dạng raw MIME 2 MiB trong database, 1 triệu emails sẽ tạo xấp xỉ **2 TB dữ liệu thô** trước index/replicas/backups. Không nên lưu MIME bytes cho mọi notification không giới hạn chỉ để dễ retry.

### Lưu metadata và content riêng

Một lựa chọn:

- Outbox row chứa model reference, template revision, metadata và trạng thái.
- Object storage giữ MIME/attachment khi retention/business policy yêu cầu.
- Attempt history tách khỏi outbox để có thể archive/purge.
- Logs chỉ lưu IDs và reason codes đã redact.
- Content snapshot có encryption và lifecycle policy riêng.

### Cost của database hot table

Nếu outbox chỉ INSERT mà không archive, indexes trên hàng chục triệu rows khiến query due jobs, VACUUM và backups tốn kém. Có thể partition theo thời gian/tenant, index theo status+available_at, archive terminal jobs và thiết kế retention.

### Không xóa hết để giảm phí

Hóa đơn, thông báo giao dịch và sự kiện bảo mật có thể cần audit theo hợp đồng/quy định. Retention phải căn theo **purpose, dữ liệu cá nhân và quy định áp dụng**, không chỉ theo chi phí storage.

## 24. Tối ưu chi phí bằng cách giảm email không cần thiết

Cách tiết kiệm hiệu quả không nhất thiết là chọn provider rẻ nhất. Trước khi gửi, hệ thống có thể giảm những notifications không có giá trị:

1. **Dedup** cùng business event + recipient + purpose theo policy.
2. **Suppression** cho địa chỉ đã hard bounce/complaint/unsubscribe hợp lệ.
3. **Consent** cho marketing, không gửi khi thiếu quyền hợp lệ.
4. **Aggregation/digest** cho low-priority events.
5. **Debounce** khi một trạng thái thay đổi liên tục trong thời gian ngắn.
6. **Expiry** bỏ OTP/notification đã hết giá trị trước send.
7. **Recipient selection** tránh fan-out không cần.
8. **Correct retry classification** không gửi lại permanent failures.
9. **Payload optimization** nén nội dung lưu trữ an toàn khi phù hợp; email attachment không phải lúc nào nên nén.
10. **Template/asset reuse** cache nội dung immutable, không render lại quá mức.

### Đừng “tối ưu” bằng cách bỏ email cần thiết

Với security alert, receipt hoặc thông báo theo luật/hợp đồng, việc gộp/bỏ notification có thể vi phạm yêu cầu. Mọi suppression/aggregation phải được kiểm tra với product owner, legal/security khi áp dụng.

### Đo hiệu quả sau suppression

Nếu 10% notifications không cần gửi được loại trước provider, cost provider giảm tương ứng theo billing basis, nhưng không có nghĩa 10% tổng TCO giảm: phần lớn chi phí cố định, DB và hệ thống có thể vẫn tồn tại.

## 25. Chọn SMTP relay, ESP API hay giải pháp hỗn hợp?

**Spring Framework Mail** cung cấp abstraction gửi qua SMTP dựa trên Jakarta Mail. Một số email service providers còn có HTTP APIs với tính năng batch, templates, tagging, event tracking hoặc idempotency khác nhau.

| Tiêu chí | SMTP qua JavaMailSender | HTTP API của ESP |
| --- | --- | --- |
| **Tích hợp Java** | Spring Mail hỗ trợ trực tiếp | Cần SDK/HTTP client/provider adapter |
| **Chuẩn giao thức** | SMTP phổ biến, có thể đổi relay | API khác nhau theo provider |
| **Thông tin quota** | SMTP replies và provider dashboard/API riêng | Có thể có HTTP headers/quota APIs |
| **Idempotency** | Không có bảo đảm exactly-once chung | Có provider hỗ trợ, phải xác minh |
| **Per-message metadata** | Header/custom tracking tùy provider | Có thể có tags/metadata riêng |
| **Batching/personalization** | MIME/recipients do app quản lý | Có thể hỗ trợ native batches |
| **Attachments** | MIME parts qua Jakarta Mail | Theo API payload/provider policy |
| **Delivery events** | Thường qua provider webhooks/dashboard | Thường có endpoint/event system |
| **Vendor portability** | Cao hơn ở transport cơ bản | Tính năng API dễ bị lock-in |
| **Throughput** | Phụ thuộc SMTP relay/connection reuse | Phụ thuộc API quotas/batch behavior |

### Khi nào SMTP phù hợp?

- Ứng dụng đã dùng Spring Mail và gửi khối lượng vừa phải.
- Không cần các tính năng API chuyên biệt.
- Provider có SMTP endpoint ổn định và quota phù hợp.
- Team muốn giữ transport adapter có tính di động.

### Khi nào HTTP API hữu ích?

- Cần quota feedback theo request, tagging, personalization hoặc events dễ khai thác.
- Có yêu cầu throughput/batch mà provider API hỗ trợ tốt hơn trong hợp đồng.
- Cần tính năng như idempotency keys hoặc webhook correlation và đã xác minh semantics.

**Không kết luận HTTP API luôn nhanh/rẻ hơn SMTP.** Bottleneck có thể nằm ở giới hạn account/recipient, sender reputation hoặc destination domain, không phải giao thức.

### Giữ transport abstraction

~~~java
public interface MailTransport {
    SubmissionOutcome submit(
            PreparedMail mail,
            SubmissionContext context
    );
}
~~~

**PreparedMail**, **SubmissionContext** và **SubmissionOutcome** là contracts do ứng dụng thiết kế. SMTP adapter dùng JavaMailSender, API adapter gọi provider SDK; domain/outbox không cần phụ thuộc vào một vendor cụ thể.

## 26. So sánh một provider với multi-provider

Thêm provider B có thể cải thiện availability, nhưng cũng có chi phí và rủi ro:

| Quyết định | Một provider | Hai providers |
| --- | --- | --- |
| **Tích hợp** | Đơn giản | Phải hỗ trợ hai transports/API models |
| **Sender identities** | Một tập verified domains | Xác minh DKIM/SPF/DMARC với từng provider |
| **Quota** | Một allowance | Có thể có nhiều allowances nhưng không được tự giả định cộng được |
| **Reputation** | Tập trung một nơi | Cần warm-up/monitor từng provider |
| **Delivery events** | Một schema webhook | Phải normalize và dedup |
| **Outage recovery** | Queue chờ phục hồi | Failover có thể gửi tiếp nếu policy cho phép |
| **Chi phí cố định** | Thường thấp hơn | Tăng phí, test, monitoring và support |
| **Incident complexity** | Ít nhánh | Cần phân biệt retries/failover/unknown |

### Failover không được gây gửi trùng

~~~text
Attempt A:
  Send via provider A
  Client timeout after message accepted?
  Outcome UNKNOWN

Naive failover:
  Immediately send via provider B
  -> recipient may get duplicates
~~~

Phải phân biệt **proven provider failure before acceptance** và **unknown submission outcome**. Khi UNKNOWN, cần reconciliation hoặc một business policy rõ về rủi ro gửi trùng, nhất là OTP/ticket.

### Cấu hình tên miền

Nếu hai providers cùng gửi cho một domain, SPF/DKIM/DMARC và Return-Path/bounce handling phải tương thích. Failover mà thiếu sender verification có thể dẫn tới messages bị từ chối hoặc ảnh hưởng reputation. Không dùng provider B như “cửa sau” để vượt anti-abuse suspension của provider A.

### Khi nào multi-provider đáng giá?

Ví dụ:

- Khối lượng lớn, service rất quan trọng.
- Có RTO/SLO được đo và provider outage cost cao.
- Hai providers thực sự độc lập về failure domain.
- Team đủ năng lực vận hành, test, đối soát, suppression.
- Chính sách dữ liệu cho phép đi qua cả hai providers/regions.

Nếu app chỉ gửi vài nghìn emails/tháng và không có yêu cầu availability nghiêm ngặt, **một provider tốt + outbox + monitoring** thường đơn giản hơn nhiều.

## 27. Data residency, privacy và compliance là một phần của lựa chọn

Email thường có PII: tên, địa chỉ, nội dung hóa đơn, mã xác nhận và tài liệu đính kèm. Một provider giá rẻ ở region khác có thể không phù hợp với chính sách dữ liệu.

### Câu hỏi cần có trong vendor evaluation

- Dữ liệu email đi qua những region nào?
- Provider lưu raw content, event logs và attachments bao lâu?
- Có tùy chọn region pinning và data processing agreement phù hợp không?
- Có encryption khi truyền và lưu trữ không?
- Có quyền truy cập nội bộ/role separation và audit logs không?
- Xóa dữ liệu và backups theo quy trình nào?
- Webhooks có chữ ký và replay protection không?
- Bounce/complaint/suppression data có thể xuất/migrate không?
- SLA, support response time và incident disclosure là gì?
- Provider hỗ trợ verified domains, DKIM, DMARC, TLS policy ra sao?

### Không tối ưu bằng cách gửi thiếu bảo mật

Không tắt TLS certificate verification hoặc bỏ suppression để đạt throughput/giá thấp. Một security incident có thể làm mất domain reputation và tạo chi phí lớn hơn khoản tiết kiệm phí SMTP.

### Đừng phát tán raw MIME rộng trong hệ thống

Queue messages hoặc debug logs chứa raw MIME có thể tạo nhiều bản sao PII. Nên dùng metadata + reference tới object storage phân quyền, retention theo purpose và audit, không log OTP hoặc link nhạy cảm.

## 28. Spring Mail configuration và timeout

Một cấu hình Spring Boot SMTP minh họa (giá trị chỉ là ví dụ):

~~~properties
spring.mail.host=smtp.example.test
spring.mail.port=587
spring.mail.username=${MAIL_USERNAME}
spring.mail.password=${MAIL_PASSWORD}
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
~~~

Các timeout có đơn vị **milliseconds** theo JavaMail SMTP properties. **STARTTLS required** yêu cầu nâng cấp TLS; hostname verification giúp tránh kết nối tới server giả. Cần kiểm tra truststore/certificate và provider port/auth mechanism thực tế. Không gửi mật khẩu trực tiếp trong repository; sử dụng secrets/config injection.

### Quota không nằm trong các properties trên

~~~properties
spring.mail.properties.mail.smtp.timeout=10000
~~~

giới hạn thời gian chờ, **không** giới hạn 10.000 email. Hạn mức provider phải được xử lý bởi application-level rate/quota controller hoặc chính sách của ESP.

### Các timeout giảm worker bị treo

Nếu không có timeouts, socket chậm có thể giữ thread lâu. Trong load lớn, điều này làm worker concurrency tiêu hết và queue dồn. Tuy nhiên timeout quá ngắn có thể tăng UNKNOWN outcomes và retries khi mạng chỉ tạm chậm; cần tuning theo latency thực tế.

### MailException và outcome

Spring Mail có **MailException** và các subclasses (như MailSendException, MailAuthenticationException). Những lỗi này hữu ích cho phân loại nhưng không đủ để suy ra chắc chắn một SMTP server đã accepted hay chưa trong mọi network failure. Transport adapter cần lưu ngữ cảnh attempts và xử lý UNKNOWN thận trọng.

## 29. Không gửi đồng bộ trực tiếp trong HTTP request

Code dễ viết:

~~~java
@PostMapping("/orders/{id}/confirm")
public ResponseEntity<?> confirm(@PathVariable String id) {
    orderService.confirm(id);
    mailSender.send(...);
    return ResponseEntity.ok().build();
}
~~~

Nhưng:

- Nếu SMTP mất vài giây, HTTP latency tăng.
- Nếu client timeout/retry request, order/email có thể bị lặp.
- DB transaction có thể commit nhưng mail send fail, response gây hiểu nhầm.
- SMTP quota hết khiến request business thất bại dù order đã được xác nhận.
- Burst làm HTTP thread pool bị giữ bởi SMTP I/O.

### Giải pháp outbox

~~~text
HTTP request
    |
    v
BEGIN DB TRANSACTION
  Update order
  Insert notification outbox row
COMMIT
    |
    v
HTTP response: order confirmed, notification queued

Async worker
    |
    v
Rate / quota permit
    |
    v
JavaMailSender.send(...)
    |
    v
Update attempt status / await delivery events
~~~

Trong response/API, phân biệt **business action completed** với **email submitted/delivered**. Không nói “email đã được gửi thành công” nếu mới insert outbox row.

### Outbox phải nằm cùng transaction phù hợp

Nếu order commit và insert outbox ở hai transactions không được ràng buộc, worker có thể mất ý định gửi khi process chết giữa hai bước. Khi business DB và outbox cùng database, có thể commit atomically. Với database/broker khác nhau, cần giải pháp tương đương hoặc chấp nhận giới hạn có chủ đích.

## 30. Ví dụ cấu trúc notification và trạng thái gửi

Một notification record có thể chứa:

~~~java
import java.time.Instant;
import java.util.UUID;

public record NotificationJob(
        UUID notificationId,
        String tenantId,
        String purpose,
        String recipientReference,
        UUID templateRevisionId,
        Instant createdAt,
        Instant availableAt,
        Instant expiresAt,
        int attemptCount
) {
}
~~~

Trạng thái:

~~~java
public enum NotificationState {
    PENDING,
    IN_FLIGHT,
    RETRY_WAIT,
    ACCEPTED,
    UNKNOWN,
    PERMANENT_FAILED,
    EXPIRED,
    CANCELLED
}
~~~

### Sơ đồ state

~~~text
PENDING
  |
  +-- deadline exceeded --> EXPIRED
  |
  '-- quota permit + claim --> IN_FLIGHT
                                |
                 +--------------+----------------+
                 |              |                |
                 v              v                v
              ACCEPTED       RETRY_WAIT         UNKNOWN
                                 |                |
                                 v                v
                              PENDING          RECONCILE
                                 |                |
                                 v                v
                              IN_FLIGHT       terminal or controlled retry
~~~

**ACCEPTED** nghĩa provider/server đã chấp nhận submission theo thông tin client nhận được, chưa phải delivered. **UNKNOWN** giữ các trường hợp không thể chứng minh accepted/rejected. Những trạng thái và tên này là mô hình do ứng dụng tự xây.

### Outbox schema minh họa

~~~sql
CREATE TABLE mail_notification_outbox (
    notification_id UUID PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    dedup_key VARCHAR(250) NOT NULL,
    purpose VARCHAR(60) NOT NULL,
    recipient_ref VARCHAR(200) NOT NULL,
    template_revision_id UUID NOT NULL,
    payload_ref VARCHAR(255) NOT NULL,
    status VARCHAR(40) NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    lease_token UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mail_notification_business
        UNIQUE (tenant_id, dedup_key)
);

CREATE INDEX idx_mail_notification_due
ON mail_notification_outbox (
    available_at,
    notification_id
)
WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

Đây là schema PostgreSQL do ứng dụng thiết kế, **không phải bảng Spring Mail tạo sẵn**. **dedup_key** ngăn tạo intent trùng theo business rules; lease_owner/lease_token giúp chống hai workers cùng gửi nếu claim được triển khai atomic và kiểm tra fencing.

### Không giữ transaction mở trong lúc gửi SMTP

Worker nên:

1. Claim job bằng transaction ngắn.
2. Release DB lock.
3. Đợi permit và submit qua transport với timeout.
4. Ghi result bằng một transaction mới, kiểm tra lease token/version.

Nếu giữ row lock cho toàn bộ thời gian network I/O, một provider chậm có thể gây database lock contention và giảm throughput.

## 31. Ví dụ tách quota controller khỏi JavaMailSender

Trong Spring, **JavaMailSender** chịu trách nhiệm compose/submit SMTP. Một **quota controller** do ứng dụng xây dựng quyết định một job có được bắt đầu attempt hay chưa.

~~~java
import java.time.Instant;

public record QuotaRequest(
        String provider,
        String accountId,
        String tenantId,
        String purpose,
        String recipientDomain,
        int recipientUnits
) {
}

public record PermitDecision(
        boolean allowed,
        Instant retryAt,
        String reason
) {
}

public interface MailQuotaController {

    PermitDecision tryReserve(
            QuotaRequest request,
            Instant now
    );
}
~~~

### Ý nghĩa của contract

- **provider/accountId**: tránh cấp gấp quota cho nhiều accounts chia cùng provider limit.
- **tenantId/purpose**: bảo đảm ngân sách và độ ưu tiên.
- **recipientDomain**: cho phép tôn trọng domain-specific pacing khi cần.
- **recipientUnits**: nếu quota đếm recipients, một message có 3 người nhận cần 3 units.
- **retryAt**: lúc sớm nhất có thể thử lấy permit lại, thay vì sleep vô hạn trong worker.

### Không trộn “permit” với “send accepted”

Một permit là **quyền thử gửi theo local policy**, không chứng minh provider đã tính quota hoặc đã accepted. Sau send phải ghi attempt outcome và đối soát quota theo telemetry provider.

### Reservation atomic

Nếu 10 workers cùng gọi **tryReserve** tại thời điểm bucket còn 5 tokens, chỉ tổng cộng tối đa 5 units được cấp theo đúng semantics; method không được dựa vào đọc số token rồi update không có locking.

### Nhiều quota windows cùng lúc

Một request có thể cần:

~~~text
global recipients/second
global recipients/day
tenant recipients/day
purpose recipients/minute
destination domain pacing
SMTP connection concurrency
~~~

Ứng dụng có thể thực hiện composite check bằng central quota ledger/atomic script hoặc một scheduler cấp allocations; chỉ viết method tryReserve không tự cung cấp tính atomic xuyên các stores.

## 32. Ví dụ worker và cơ chế reschedule không giữ thread chờ

Một worker không nên làm:

~~~java
while (!quotaAvailable) {
    Thread.sleep(1000);
}
~~~

cho mỗi notification; hàng chục nghìn jobs sẽ giữ nhiều threads/connections hoặc gây polling quá nhiều. Thay vào đó, ghi **availableAt** rồi trả worker slot cho job khác.

### Domain contracts

~~~java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public interface MailOutboxStore {
    List<ClaimedMailJob> claimDue(
            String workerId,
            int maxJobs,
            Instant now
    );

    void reschedule(
            UUID notificationId,
            UUID leaseToken,
            Instant nextAt,
            String reason
    );

    void markAccepted(
            UUID notificationId,
            UUID leaseToken,
            String providerMessageId
    );

    void markUnknown(
            UUID notificationId,
            UUID leaseToken,
            String reason
    );
}

public record ClaimedMailJob(
        UUID notificationId,
        UUID leaseToken,
        String tenantId,
        String purpose,
        String provider,
        String accountId,
        String recipientDomain,
        int recipientUnits,
        Instant expiresAt,
        String payloadReference
) {
}
~~~

Các types là **mô hình ứng dụng**, không phải API của Spring Mail. **claimDue** phải atomic và lease-safe; các methods ghi kết quả phải kiểm tra lease token để worker cũ không ghi đè trạng thái worker mới.

### Service dispatcher minh họa

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class MailDispatchService {

    private final MailOutboxStore store;
    private final MailQuotaController quotas;
    private final PreparedMailSender sender;
    private final Clock clock;

    public MailDispatchService(
            MailOutboxStore store,
            MailQuotaController quotas,
            PreparedMailSender sender,
            Clock clock
    ) {
        this.store = store;
        this.quotas = quotas;
        this.sender = sender;
        this.clock = clock;
    }

    public void dispatchBatch(String workerId, int maxJobs) {
        List<ClaimedMailJob> batch = store.claimDue(
                workerId, maxJobs, clock.instant()
        );

        for (ClaimedMailJob job : batch) {
            Instant now = clock.instant();

            if (job.expiresAt() != null
                    && !now.isBefore(job.expiresAt())) {
                // Production: mark EXPIRED under matching lease.
                continue;
            }

            QuotaRequest request = new QuotaRequest(
                    job.provider(),
                    job.accountId(),
                    job.tenantId(),
                    job.purpose(),
                    job.recipientDomain(),
                    job.recipientUnits()
            );

            PermitDecision permit = quotas.tryReserve(
                    request, now
            );

            if (!permit.allowed()) {
                Instant nextAt = permit.retryAt() != null
                        ? permit.retryAt()
                        : now.plus(Duration.ofSeconds(10));
                store.reschedule(
                        job.notificationId(),
                        job.leaseToken(),
                        nextAt,
                        permit.reason()
                );
                continue;
            }

            SubmissionOutcome result = sender.submit(job);

            switch (result.status()) {
                case ACCEPTED -> store.markAccepted(
                        job.notificationId(),
                        job.leaseToken(),
                        result.providerMessageId()
                );
                case UNKNOWN -> store.markUnknown(
                        job.notificationId(),
                        job.leaseToken(),
                        result.reason()
                );
                case RETRYABLE -> store.reschedule(
                        job.notificationId(),
                        job.leaseToken(),
                        now.plus(Duration.ofSeconds(30)),
                        result.reason()
                );
                case PERMANENT_FAILURE -> {
                    // Production: mark PERMANENT_FAILED
                    // under matching lease.
                }
            }
        }
    }
}

public interface PreparedMailSender {
    SubmissionOutcome submit(ClaimedMailJob job);
}

public record SubmissionOutcome(
        SubmissionStatus status,
        String providerMessageId,
        String reason
) {
}

public enum SubmissionStatus {
    ACCEPTED, RETRYABLE, PERMANENT_FAILURE, UNKNOWN
}
~~~

Ví dụ cố tình **chưa cài đặt branch EXPIRED/PERMANENT_FAILURE**, lease heartbeat, provider reply classification và policy backoff đầy đủ. Nó chỉ minh họa rằng **quota denial dẫn tới reschedule**, không giữ thread sleep, và **UNKNOWN** không bị xem là RETRYABLE một cách tự động. Production phải triển khai hai branch còn thiếu trước khi sử dụng.

### Cẩn thận với batch đã claim nhưng chưa gửi

Nếu **claimDue** lấy 500 jobs với lease 30 giây nhưng dispatcher xử lý tuần tự và mỗi SMTP attempt mất 1 giây, lease của jobs cuối có thể hết trước khi tới lượt. Giới hạn batch size, renew lease đúng cách hoặc chỉ claim khi có worker/permit capacity tương ứng.

### Không cấp nhiều permits rồi bỏ quên

Nếu quota token bị reserve trước khi một job expired/cancelled, controller cần policy hoàn trả/capacity accounting phù hợp. Với provider daily quota, một successful local reservation không nhất thiết đã bị provider tính quota.

## 33. Ví dụ Spring scheduling và worker pool

Một scheduler trong Spring Boot có thể kích hoạt dispatcher định kỳ:

~~~java
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

@Configuration
@EnableScheduling
class MailSchedulerConfig {
}

@Component
public class MailDispatchScheduler {

    private final MailDispatchService dispatch;

    public MailDispatchScheduler(MailDispatchService dispatch) {
        this.dispatch = dispatch;
    }

    @Scheduled(fixedDelayString = "${app.mail.dispatch.delay-ms:1000}")
    public void tick() {
        dispatch.dispatchBatch("worker-instance-1", 20);
    }
}
~~~

**worker-instance-1** chỉ là placeholder; khi nhiều replicas phải dùng một instance identity có ý nghĩa và claim leases từ database. Annotation **@Scheduled** chạy trên từng instance có scheduler bật, không tự thực hiện cluster-wide election. Đồng thời không được tự kết luận fixedDelay 1000 ms sẽ đạt 20 emails/s: tốc độ thực còn tùy số jobs, latency, batch, worker threads, permits và schedules.

### Tách scheduling khỏi send pool

Có thể cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class MailWorkersConfig {

    @Bean("mailSendExecutor")
    ThreadPoolTaskExecutor mailSendExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("mail-send-");
        executor.initialize();
        return executor;
    }
}
~~~

Đây là worker pool **hữu hạn**, nhưng bản thân nó không bảo đảm global rate limit, không bảo đảm outbox durability và không kiểm soát số SMTP connections nếu không có semaphore/controller riêng. Sử dụng executor phải có rejection/backpressure policy; không submit hàng trăm nghìn tasks trong memory.

### SMTP connection reuse cần đánh giá

Không được giả định mỗi lời gọi **JavaMailSender.send(message)** sẽ giữ một SMTP connection persistent được share an toàn giữa threads. Spring's JavaMailSenderImpl có hành vi quản lý transport riêng tùy cách gọi; connection pooling/reuse giữa các lời gọi cần được kiểm chứng với implementation và provider. Tối ưu connection setup chỉ khi không vượt connection quota, TLS/auth requirements và concurrency safety.

## 34. An toàn khi compose MIME trong worker

Một worker có thể cần:

~~~text
Outbox job with pinned template revision
      |
      v
Load model snapshot
      |
      v
Render subject + text/plain + text/html
      |
      v
Validate recipient, sender profile, URLs
      |
      v
Compose MimeMessage
      |
      v
Add inline assets / attachments
      |
      v
Submit via transport adapter
~~~

### Không giữ MimeMessage làm payload chính trong queue

**MimeMessage** có thể chứa resources, streams hoặc metadata không thuận tiện để serialize và có thể gây phình storage. Thường lưu **notification ID + template revision + model reference + attachment references**, rồi compose tại worker.

### Payload có thể ảnh hưởng concurrency

Giả sử 40 workers đồng thời tải attachments 20 MiB vào RAM:

~~~text
40 × 20 MiB ≈ 800 MiB chỉ riêng binary attachments
~~~

Chưa tính MIME base64, HTML, heap overhead và Java objects. Để scale, cần giới hạn attachment size, dùng streaming/resource handling phù hợp và load-test memory. Không mở worker count quá cao khi p99 MIME size lớn.

### MIME size validation trước transport

Một job quá lớn cho provider sẽ thất bại dù retry 100 lần. Cần ước lượng/bound encoded payload trước submission. Nếu chưa có kích thước chính xác, có thể validate raw file size và thiết kế safety margin cho base64/header overhead; provider total-message limit phải được xác minh.

### Plain text và HTML cùng template model

Nếu hệ thống gửi HTML, nên cung cấp **text/plain** alternative hữu ích khi phù hợp. Đây là chất lượng nội dung và compatibility, không phải cách tăng quota. Rendering HTML và plain có overhead; cache immutable template source, không cache output cá nhân hóa chung giữa người dùng.

## 35. SLO/SLA: đo đúng thời điểm và kết quả

Một hệ thống mail có nhiều điểm mốc:

~~~text
Notification created
        |
        v
Outbox committed
        |
        v
Worker claimed
        |
        v
Quota permit acquired
        |
        v
Provider accepted
        |
        v
Recipient mail server accepted / delivered event
        |
        v
User opened/read (không luôn đo được)
~~~

### Những định nghĩa SLO có thể dùng

| SLO | Ranh giới đo | Cảnh báo về ý nghĩa |
| --- | --- | --- |
| **Queue admission latency** | Notification intent → outbox committed | Không nói gì về SMTP |
| **Time to first attempt** | Outbox committed → worker first try | Thể hiện scheduler/quota capacity |
| **Time to provider acceptance** | Outbox committed → accepted | Có thể đo từ app và responses |
| **Delivery latency** | Outbox created → provider delivered signal | Phụ thuộc telemetry webhook |
| **Expired unsent ratio** | Jobs hết TTL trước attempt/success | Cực quan trọng cho OTP |
| **Acceptance success rate** | Accepted / attempted | Không phải Inbox placement |
| **Duplicate suppression rate** | Duplicate intents không tạo sends | Phụ thuộc business key/policy |

### SLO nên phân theo purpose

Một SLO minh họa:

~~~text
Critical OTP:
  99% eligible notifications accepted by provider
  within 30 seconds, excluding explicit provider outages
  only if contract actually allows such exclusion

Transactional receipt:
  99,9% accepted within 5 minutes

Marketing:
  99% accepted within scheduled 4-hour campaign window
~~~

Các số đều là **giả định minh họa**. Không dùng như default production. Nếu SLO loại trừ provider outages, cách tính exclusions phải được công bố minh bạch, tránh “báo cáo đẹp” bằng cách bỏ đúng các sự cố quan trọng.

### Theo dõi p95/p99 thay vì mean

Mean 2 giây không loại trừ một nhóm nhỏ OTP chờ 10 phút. Nên đo percentiles của **queue wait, quota wait, SMTP submit latency, end-to-end acceptance latency**, và phân theo tenant/purpose/provider đủ mức để tìm bottleneck mà không tạo metric cardinality quá cao.

### Error budget và capacity

Nếu SLO 99,9%, allowance lỗi theo định nghĩa đó là 0,1% events trong window. Khi backlog, throttling hoặc provider outage sử dụng nhiều error budget, cần điều chỉnh rollout/campaign và capacity reservation thay vì chỉ tăng workers.

## 36. Observability: quota và trạng thái gửi

Các metrics do ứng dụng tự triển khai:

| Metric logic | Loại | Ý nghĩa |
| --- | --- | --- |
| **mail_outbox_pending_jobs** | Gauge | Số jobs đang chờ |
| **mail_outbox_oldest_age_seconds** | Gauge | Tuổi job cũ nhất |
| **mail_outbox_expired_total** | Counter | Số jobs hết TTL |
| **mail_send_attempts_total** | Counter | Lần thử theo outcome |
| **mail_send_acceptance_total** | Counter | Recipients/messages accepted, định nghĩa units rõ |
| **mail_send_throttled_total** | Counter | Throttling/rate rejects |
| **mail_send_unknown_total** | Counter | Outcome không chắc |
| **mail_send_latency_seconds** | Histogram/Timer | Latency submit |
| **mail_quota_remaining_units** | Gauge | Local/provider reported allowance, source rõ |
| **mail_quota_denials_total** | Counter | Local controller không cấp permit |
| **mail_quota_wait_seconds** | Histogram/Timer | Thời gian chờ quota |
| **mail_retry_attempts_total** | Counter | Thử lại theo reason |
| **mail_provider_connection_failures_total** | Counter | Lỗi network/TLS/auth |
| **mail_delivery_bounced_total** | Counter | Bounce từ provider feedback |
| **mail_delivery_complaints_total** | Counter | Complaints |
| **mail_monthly_billable_units_estimate** | Gauge | Ước lượng units billable |

**Đây là tên logic minh họa**, không phải metrics mặc định có sẵn trong Spring Framework Mail. Nhiều monitoring registries tự dùng hậu tố **_total** cho counters hoặc thay đổi naming convention; kiểm tra tên export thực tế.

### Labels nên giữ thấp cardinality

~~~text
provider=primary|secondary
purpose=critical|transactional|bulk
result=accepted|throttled|retryable|unknown|permanent
region=region-a|region-b
tenant_tier=free|business|enterprise
~~~

Không gắn recipient email, notificationId, Message-ID, subject, raw provider error string hoặc attempt ID vào metrics labels vì có thể gây high cardinality và lộ PII. Những IDs chi tiết phù hợp hơn trong logs/traces có phân quyền và TTL.

### Định nghĩa units ngay trong dashboard

Một gauge **mail_quota_remaining_units=1000** không có nghĩa gì nếu không biết units là recipients/day, requests/minute hay SMTP connections. Nên lưu labels **quota_kind** và **window** hữu hạn, có tài liệu về nguồn cập nhật/staleness.

### Provider quota feedback có thể stale

Dashboard provider có thể cập nhật trễ hoặc API rate limit hiển thị ước lượng. Local counter và authoritative provider usage có thể khác; cần một reconciliation job và safety margin. Không dùng một nguồn dữ liệu stale như bằng chứng chắc chắn còn quota cho burst.

## 37. Delivery webhooks, bounces và suppression

Submission accepted chưa bảo đảm thư được phát tới mailbox cuối. Khi provider cung cấp feedback:

~~~text
SMTP/API ACCEPTED
     |
     v
Provider processing
     |
     +--> DELIVERED
     +--> SOFT_BOUNCE
     +--> HARD_BOUNCE
     +--> COMPLAINT
     '--> DEFERRED / UNKNOWN
                |
                v
         Event ingestion service
                |
                v
         Update notification state
                |
                v
         Suppression / reputation policy
~~~

### Webhooks phải được xác thực

Không tin một HTTP POST nói “delivered” chỉ vì nó tới URL webhook. Cần signature verification, timestamp/replay protection, TLS, allowlist policy khi phù hợp và lưu provider event ID để chống xử lý trùng.

### Events có thể out-of-order/duplicate

Provider có thể gửi webhook nhiều lần hoặc delivery event đến trước sự kiện accepted được ghi trong database do độ trễ hệ thống. Consumer phải idempotent, lưu event timestamps và áp state transitions theo semantics provider; không để một webhook cũ ghi đè trạng thái mới.

### Suppression là cách bảo vệ chi phí lẫn reputation

Gửi tiếp tới địa chỉ đã hard bounce có thể tăng chi phí và làm xấu reputation. Khi một người unsubscribe marketing, phải dừng marketing theo consent policy; không dùng suppression chung mà vô tình chặn mọi email bảo mật bắt buộc nếu không phù hợp purpose.

### Cost per delivered cần feedback đáng tin

Nếu provider không có signal delivered đầy đủ, không tự tạo metric “cost per delivered” chính xác từ số accepted. Có thể báo **accepted cost** hoặc **estimated delivery cost** với nhãn ước lượng.

## 38. Load test trước khi tăng quota

Một bài kiểm thử tải cần trả lời:

1. Hệ thống enqueue được bao nhiêu jobs/giây?
2. Quota controller cấp permits đúng aggregate limit dưới nhiều replicas không?
3. Worker pool giữ ổn định CPU/RAM/connections?
4. Outbox drain nhanh thế nào sau một outage?
5. Critical messages có còn đáp ứng deadline khi bulk traffic rất cao?
6. Provider trả throttling thì retry có kiểm soát hay tạo storm?
7. Payload p95/p99 kích thước lớn ảnh hưởng memory/egress ra sao?
8. Multi-provider fallback có tạo duplicates hay mất suppression state không?

### Không load-test bằng email tới người nhận thật

Hàng trăm nghìn synthetic emails gửi vào địa chỉ thật có thể vi phạm chính sách provider, ảnh hưởng reputation và gây phiền nhiễu. Dùng **fake transport, SMTP sink/fixture, local test server hoặc provider sandbox** theo hợp đồng. Nếu cần test provider thực với volume, phải phối hợp quota/support và dùng môi trường được ủy quyền.

### Ma trận test

| Kịch bản | Input | Tiêu chí quan sát |
| --- | --- | --- |
| **Steady state** | 50% quota trong nhiều giờ | Backlog gần ổn định, resource ổn |
| **Short burst** | 10× baseline 2 phút | Queue tăng có giới hạn, critical SLO |
| **Long campaign** | 100% bulk allowance | Không chiếm reserve của critical |
| **Provider throttle** | Inject 429 hoặc SMTP temporary reply | Backoff/jitter, retry share |
| **Provider outage** | 0 capacity trong 30 phút | Durable backlog, recovery drain |
| **Network timeout UNKNOWN** | Server accepts nhưng response mất | Không blind resend |
| **Large attachments** | p95/p99 MIME size | Heap, egress, encoding overhead |
| **Cluster scale** | 1 → 4 → 16 replicas | Tổng provider rate không vượt cap |
| **Tenant hotspot** | Một tenant 90% traffic | Fairness cho tenants khác |
| **Daily quota near empty** | Chỉ còn 1% allowance | Reserve cho critical |
| **Cache/DB slowdown** | Outbox DB latency tăng | Bounded workers, no duplicate claims |
| **Delivery feedback storm** | Webhooks burst/duplicate | Signature/dedup, no state corruption |

### Mô hình môi trường test

~~~text
Load generator
      |
      v
Notification API / Business event simulator
      |
      v
Outbox database
      |
      v
1/4/16 worker replicas
      |
      v
Shared quota controller
      |
      v
Fake MailTransport
  - deterministic latency distribution
  - injected accepts/failures/throttles
  - records recipient units/s
      |
      v
Metrics and assertions
~~~

Điểm quan trọng: fake transport phải mô phỏng **units của provider** (recipients, requests, windows), không chỉ đếm method calls. Nó có thể intentionally fail để kiểm tra retry amplification.

## 39. Ví dụ kiểm thử quota bằng fake controller

Một contract nhỏ:

~~~java
public interface MailQuotaController {
    PermitDecision tryReserve(QuotaRequest request, java.time.Instant now);
}
~~~

Test logic cho provider cap 20 recipient-units trong một fixed-second window:

~~~text
Given:
  Global quota allows at most 20 recipient-units/second.
  5 workers concurrently request 6 recipient-units each.

When:
  All attempt reservation in the same second.

Then:
  Total allowed units <= 20.
  Remaining requests are denied/rescheduled.
  No worker exceeds account allocation due to race.
~~~

### Negative test quan trọng

Nếu mỗi pod dùng limiter 20/s riêng:

~~~text
Pod A: 20/s
Pod B: 20/s
Aggregate: 40/s
Expected global cap: 20/s
=> Test must fail for naive design
~~~

### Kiểm thử refresh window

Fixed window có thể cho 20 units ở cuối giây A và 20 ở đầu giây B — tổng 40 units trong một khoảng trượt ngắn. Nếu provider áp **rolling-window** chặt, limiter fixed-second có thể không tương đương. Cần test theo window semantics thật.

### Kiểm thử expired jobs

~~~text
Given:
  OTP job expires at 10:05:00
  Quota next eligible at 10:05:20

Then:
  Job should not be queued to send an already invalid OTP
  Mark expired / surface a meaningful retry alternative
~~~

Không test rằng một retry loop sẽ “cuối cùng gửi được”, vì goal có deadline.

### Kiểm thử failure after provider accepted

Fake transport:

~~~text
1. Records message as accepted.
2. Simulates connection reset before client sees response.
3. Returns UNKNOWN.
~~~

Expected: system records UNKNOWN and uses reconciliation/policy, **not immediately submits again on another provider**. Đây là test đặc biệt quan trọng nếu có failover.

## 40. Runbook: gần hết daily quota

Tình huống:

~~~text
Provider daily allowance: 50.000 recipients
Reported used:           49.300
Local estimated pending:  2.000
Critical expected:           500
Bulk expected:             1.500
~~~

Nếu cho jobs chạy FIFO, bulk có thể chiếm 700 units còn lại và critical jobs mới đến không có quota.

### Bước 1 — Xác minh đơn vị và cửa sổ

- Con số 49.300 là recipients/day hay requests/day?
- Provider reports có cập nhật trễ không?
- Daily window reset theo timezone/rolling 24h hay lịch cố định?
- Có application khác chia cùng account/API key không?
- Provider có cả rate theo giây hoặc subaccount limit không?

### Bước 2 — Chuyển traffic về chính sách ưu tiên

1. Pause/dàn lịch bulk hoặc campaign theo quyền operator.
2. Giữ reserve cho OTP, security và receipts theo SLO.
3. Không tăng worker count chỉ vì quota ít.
4. Cập nhật estimated next eligible time cho jobs chưa gửi.
5. Nếu critical queue vẫn vượt allowance, kích hoạt escalation/provisioning/failover được phê duyệt.

### Bước 3 — Kiểm tra các jobs có deadline

Không gửi OTP khi token đã hết hạn. Những notifications khác có thể giữ trong durable outbox đến window tiếp theo, nhưng phải hiển thị delay rõ; không báo đã gửi khi mới xếp hàng.

### Bước 4 — Quota recovery

Sau khi window reset/provider mở quota:

~~~text
Rate limit remains active.
Critical queue drains first within fairness policy.
Transactional queue drains next.
Bulk queue resumes at controlled pace.
~~~

Không chạy **send all pending immediately**; burst có thể vi phạm per-second quota dù daily quota đã reset.

### Bước 5 — Điều chỉnh lâu dài

Phân tích growth, campaign scheduling, suppression, dedicated capacity và hợp đồng provider. Cần có capacity alert trước khi chỉ còn 1% quota, thay vì xử lý khẩn cấp mỗi ngày.

## 41. Runbook: provider throttling hoặc outage

### Triệu chứng

~~~text
mail_send_throttled_total rises
mail_quota_wait_seconds rises
mail_outbox_oldest_age_seconds rises
SMTP timeout/reply 4xx increases
~~~

Không được kết luận tất cả 4xx là một mã quota giống nhau; SMTP enhanced codes và provider diagnostics cần được giải thích theo hợp đồng.

### Quy trình

1. Xác nhận lỗi kết nối/auth/TLS hay actual rate limit.
2. Kiểm tra allowance, account reputation và restriction.
3. Giảm submission pacing hoặc mở circuit breaker nếu phù hợp.
4. Đặt retry-after/backoff + jitter cho transient cases.
5. Đảm bảo retry share không chiếm hết capacity.
6. Không retry permanent recipient failures và auth misconfiguration vô hạn.
7. Cân nhắc failover chỉ khi outcome chắc chắn an toàn hoặc có reconciliation.
8. Kiểm tra backlog/expired jobs sau recovery.
9. Ghi sự cố theo purpose và mức độ ảnh hưởng người dùng.

### Đừng giải quyết bằng cách tăng parallelism

Thêm pods/threads thường làm throttling nặng hơn nếu provider đang hạn chế. Cần giảm attempt rate, xử lý nguyên nhân và khôi phục dần theo feedback.

### Unknown outcomes trong outage

Nếu worker bị timeout sau khi truyền message, không thể suy ra chắc “chưa gửi”. Một đối tượng outbox **UNKNOWN** cần tra provider logs/message ID khi có, hoặc áp business risk policy; không tự động failover rồi gửi lại mà không biết.

### Chuẩn bị cho lần tới

Có circuit breaker/health status, quota gauges, retry budgets, failover dry run và runbook quy định rõ ai có quyền chuyển provider, pause campaign hoặc tăng budget.

## 42. Runbook: chi phí tăng đột biến

Một sự tăng chi phí không nhất thiết phản ánh số người dùng tăng. Có thể do:

- Retry storm.
- Gửi trùng business notifications.
- Marketing campaign lên sai danh sách/segment.
- Một tenant bị abuse hoặc account credentials lộ.
- Attachments tăng kích thước/number.
- Provider chuyển tier hoặc thay billing basis.
- Cross-region egress và logs/observability tăng.
- Cùng event bị publish lại nhiều lần do bug outbox/consumer.
- Suppression không hoạt động khiến gửi tới hard-bounced recipients.

### Phân tích “cost per meaningful unit”

~~~text
Monthly spend
    |
    +-- Provider send fee
    +-- Fixed fees and extra services
    +-- Egress / large payloads
    +-- Storage / logs
    '-- Operations

Compare against:
    logical notifications
    recipient attempts
    accepted recipients
    delivered events (if trustworthy)
    business actions triggering email
~~~

Nếu **attempts/logical recipient** tăng từ 1,02 lên 1,40, đó có thể là tín hiệu retry storm. Nếu logical notifications cũng tăng bốn lần nhưng business events không tăng, cần tìm duplicate fan-out hoặc loop.

### Bước xử lý

1. Phân tách cost theo provider, tenant, purpose, day.
2. Đối chiếu attempts, accepted, bounces và webhooks.
3. Kiểm tra retry ratio theo error category.
4. Phân loại billable units thực từ provider invoices/usage API.
5. Kiểm tra campaign schedule/recipient selection và consent.
6. Kiểm tra bytes per message, attachments, retention và log volume.
7. Áp budget/pause có kiểm soát cho traffic không critical.
8. Fix root cause, không chỉ mua quota thêm.

### Chargeback/showback theo tenant

Một multi-tenant platform có thể hiển thị estimated cost by tenant. Nhưng cần ghi rõ shared fixed costs phân bổ thế nào, và billable units do provider tính có thể khác local units. Tránh dùng con số ước lượng như hóa đơn chính thức nếu chưa reconciliation.

## 43. Chọn kiến trúc theo bối cảnh thực tế

Không phải ứng dụng nào cũng cần 20 services và nhiều providers. Một lựa chọn tốt phải cân bằng độ tin cậy với chi phí vận hành.

| Bối cảnh | Kiến trúc gợi ý | Điểm cần chú ý |
| --- | --- | --- |
| **Ứng dụng nội bộ, email thưa** | Spring Mail + job queue nhỏ + timeout | Cấu hình sender và error handling |
| **SaaS gửi transactional vừa phải** | DB outbox + worker + global rate limiter | Reliability, quota, tenant isolation |
| **OTP với deadline ngắn** | Priority lane + reserved capacity + expiry | Latency, fallback policy |
| **Bulk newsletter** | Scheduler + per-campaign pacing + suppression | Reputation, cost, consent |
| **Multi-tenant lớn** | Fair queues + shared/distributed quota + subaccounts | Fairness, billing, reputation |
| **High-availability business-critical** | Outbox + multi-provider adapters + reconciliation | Unknown outcomes, domains, compliance |
| **Large reports/attachments** | Object storage + secure links hoặc streaming | Egress, privacy, TTL |
| **Strict audit/financial** | Pinned template/model + attempt history + feedback | Retention, accurate submission statuses |

### Mẫu quyết định theo thứ tự

~~~text
What are the email purposes and deadlines?
                  |
                  v
What is peak recipient rate + daily/monthly volume?
                  |
                  v
What units/limits does provider actually enforce?
                  |
                  v
Can one provider satisfy rate + quota + compliance + SLO?
           |                                  |
          Yes                                No
           |                                  |
           v                                  v
Single provider + outbox                Evaluate larger tier,
+ global limiter                        second provider, batching,
           |                              or changed requirements
           +----------------+-----------------+
                            |
                            v
              What must be durable/traceable?
                            |
                            v
                  Build retry + UNKNOWN policy
                            |
                            v
                 Load test and instrument cost
                            |
                            v
                 Rollout with safety headroom
~~~

### Điều kiện loại trừ

Một provider có giá thấp nhưng không đáp ứng data residency hoặc không hỗ trợ domain verification cần thiết thì không phải lựa chọn hợp lệ. Tương tự, một architecture có raw throughput cao nhưng gửi OTP sau khi hết TTL không đáp ứng business goal.

## 44. Ví dụ thiết kế capacity cho hệ thống thương mại

Giả sử một nền tảng có traffic giả định:

~~~text
Normal day:
  OTP:            15.000
  Receipts:       35.000
  Alerts:          2.000
  Total logical:  52.000 recipients

Peak event:
  3.000 OTP requests over 2 minutes

Bulk campaign:
  120.000 recipients over 3 hours

Provider fictional profile:
  100.000 recipient units/day
  40 recipient units/s sustained
~~~

### Nhận xét về daily quota

Normal day 52.000 units đã chiếm hơn nửa daily quota, nhưng campaign 120.000 recipients **không thể hoàn tất trong cùng một ngày** dưới allowance 100.000 ngay cả khi không có normal traffic. Cần dàn qua nhiều window, tăng allowance một cách hợp lệ, chuyển sang capacity khác hoặc điều chỉnh campaign target.

### Nhận xét về OTP burst

~~~text
3.000 recipients / 120 s = 25 recipients/s
~~~

Con số này dưới cap 40/s, nhưng chỉ còn khoảng 15/s cho các lưu lượng khác **nếu cap áp chung**, chưa tính retries. Cần reserved rate/priority và đo latency, không chia đều 40/s theo FIFO.

### Nhận xét về campaign rate

~~~text
120.000 recipients / (3 × 3.600 s)
≈ 11,1 recipients/s
~~~

Campaign rate này phù hợp với 40/s sustained theo giả định, nhưng daily quota vẫn là bottleneck. Điều đó minh họa **rate và volume window là hai điều kiện độc lập**.

### Quyết định sơ bộ

- Không gửi toàn bộ campaign trong một ngày với quota hiện tại.
- Reserved lane cho OTP và transactional.
- Campaign scheduler dàn qua windows/quotas được cho phép.
- DB outbox + atomic claim + expiry cho OTP.
- Distributed limiter vì nhiều replicas chia một account.
- Theo dõi daily remaining, p95 acceptance latency, retry budget.
- Đo chi phí và negotiation tier nếu volume tăng bền vững.

Ví dụ này không chứng minh provider thực nào có capability trên; nó minh họa cách phân tích các ràng buộc trước khi chọn công nghệ.

## 45. Những sai lầm kiến trúc thường gặp

### Sai lầm 1 — Lấy số method calls làm số recipients

**Vấn đề:** một send(message) có thể có nhiều To/Cc/Bcc. Nếu provider đếm theo recipient, local quota sai.

**Cách làm:** theo đúng units provider quy định và đếm recipients trước attempt.

### Sai lầm 2 — Tính capacity theo average/day

**Vấn đề:** traffic dồn trong 1 phút có thể cao hàng trăm lần average.

**Cách làm:** forecast peak per-second/per-minute, burst duration và SLO.

### Sai lầm 3 — Tăng threads khi bị provider 429/throttle

**Vấn đề:** làm throttling và retry storm nặng hơn.

**Cách làm:** pacing, global limiter, backoff và quota feedback.

### Sai lầm 4 — Mỗi pod có limiter 20/s khi account cap 20/s

**Vấn đề:** aggregate rate tăng theo số pods, vượt account quota.

**Cách làm:** distributed limiter hoặc quota partitions có tổng được kiểm soát.

### Sai lầm 5 — Có daily limiter nhưng không có per-second limiter

**Vấn đề:** còn 10.000 quota ngày nhưng burst 1.000 requests/s bị từ chối.

**Cách làm:** composite constraints theo windows.

### Sai lầm 6 — Có per-second limiter nhưng không có daily budget

**Vấn đề:** tốc độ luôn dưới cap nhưng vẫn cạn quota ngày.

**Cách làm:** quota ledger theo đúng rolling/calendar windows.

### Sai lầm 7 — Dùng một FIFO queue cho OTP và marketing

**Vấn đề:** critical email chờ batch hàng loạt.

**Cách làm:** priority lanes/reserve/fair scheduling.

### Sai lầm 8 — Priority tuyệt đối khiến bulk không bao giờ gửi

**Vấn đề:** starvation khi critical traffic liên tục.

**Cách làm:** fairness, aging, borrowing có policy và SLO riêng.

### Sai lầm 9 — Chờ permit bằng Thread.sleep cho mỗi job

**Vấn đề:** giữ threads, không scale khi backlog lớn.

**Cách làm:** availableAt/reschedule, trả worker slot.

### Sai lầm 10 — Queue vô hạn như một giải pháp quota

**Vấn đề:** backlog, storage cost và expired jobs tăng mãi.

**Cách làm:** admission control, bounded queue/backpressure và dàn lịch.

### Sai lầm 11 — Retry mọi exception ngay lập tức

**Vấn đề:** amplification, chi phí, gửi trùng và overload.

**Cách làm:** classification, backoff/jitter, circuit breaker và retry budget.

### Sai lầm 12 — Coi timeout là chắc chắn chưa gửi

**Vấn đề:** provider có thể đã accepted khi client mất response.

**Cách làm:** UNKNOWN/reconciliation, không blind failover.

### Sai lầm 13 — Dùng Message-ID làm idempotency bảo đảm

**Vấn đề:** SMTP không tự dedup submissions theo Message-ID.

**Cách làm:** business notification key, attempts và provider-supported idempotency.

### Sai lầm 14 — Coi SMTP accepted là delivered

**Vấn đề:** thư vẫn có thể bounce/defer/spam.

**Cách làm:** tách provider acceptance và delivery feedback.

### Sai lầm 15 — Chỉ đo số emails sent

**Vấn đề:** không biết quota, latency, backlog, expired OTP và cost.

**Cách làm:** metrics theo units, purpose, window và states.

### Sai lầm 16 — Lấy giá provider per-1.000 × Java send calls

**Vấn đề:** billing basis có thể là recipients, attempts, API usage hoặc tiers.

**Cách làm:** dùng provider invoice/usage contract và reconcile.

### Sai lầm 17 — Bỏ qua MIME base64 overhead

**Vấn đề:** attachment gần giới hạn kích thước bị reject.

**Cách làm:** validate encoded total-message size với safety margin.

### Sai lầm 18 — Tăng worker count bất chấp heap

**Vấn đề:** attachments lớn làm heap/OOM dù SMTP cap không thay đổi.

**Cách làm:** benchmark p95/p99 payload, bounded concurrency, streaming.

### Sai lầm 19 — Gửi email trực tiếp trong DB transaction

**Vấn đề:** network I/O giữ locks, không atomic với SMTP.

**Cách làm:** transactional outbox, worker độc lập.

### Sai lầm 20 — Claim quá nhiều outbox jobs

**Vấn đề:** lease hết hạn trước khi tới lượt gửi, hai workers có thể cùng submit.

**Cách làm:** claim theo capacity thực, heartbeat/fencing, reschedule đúng state.

### Sai lầm 21 — Failover mọi UNKNOWN attempt

**Vấn đề:** provider A có thể đã accepted; provider B gửi thêm gây trùng.

**Cách làm:** reconciliation, risk policy, provider IDs.

### Sai lầm 22 — Nghĩ multi-provider tự tăng total quota hợp pháp

**Vấn đề:** accounts có thể chia parent allowance, warm-up/reputation khác; không được dùng để lách suspension.

**Cách làm:** xác minh hợp đồng, domain identities và independent failure domains.

### Sai lầm 23 — Không đồng bộ suppression giữa providers

**Vấn đề:** người đã unsubscribe/hard bounce ở A vẫn nhận mail qua B.

**Cách làm:** suppression policy chung, event ingestion/idempotency.

### Sai lầm 24 — Quên data residency vì provider rẻ

**Vấn đề:** dữ liệu/attachments có thể đi qua region không được phép.

**Cách làm:** compliance là điều kiện lựa chọn trước tối ưu giá.

### Sai lầm 25 — Log raw MIME để theo dõi chi phí

**Vấn đề:** PII/token rò rỉ, tăng logging cost.

**Cách làm:** log metadata/bytes/IDs đã redact, retention rõ.

### Sai lầm 26 — Tính tiền theo local estimate mà không đối soát

**Vấn đề:** local counters khác provider invoice do retries, partial successes hoặc windows.

**Cách làm:** usage reconciliation định kỳ và gắn nhãn số ước lượng.

### Sai lầm 27 — Gửi OTP đã hết hạn sau outage

**Vấn đề:** spam vô ích, tăng phí và trải nghiệm kém.

**Cách làm:** expiry check trước first/next attempts.

### Sai lầm 28 — Chỉ nâng tier mà không giảm email dư

**Vấn đề:** tiếp tục gửi duplicate/no-consent/expired notifications.

**Cách làm:** dedup, suppression, aggregation theo business policy trước.

### Sai lầm 29 — Load-test vào mailbox người dùng thật

**Vấn đề:** ảnh hưởng sender reputation, chi phí và làm phiền.

**Cách làm:** fake provider/test fixture/sandbox được cấp phép.

### Sai lầm 30 — Hứa exactly-once vì có outbox

**Vấn đề:** SMTP response mất hoặc broker redelivery có thể tạo multiple attempts.

**Cách làm:** stable notification identity, idempotency và UNKNOWN policies; truyền đạt chính xác delivery guarantees.

## 46. Bài tập tình huống và hướng giải

### A. 2.400 recipients trong một phút, provider 20/s

**Hỏi:** thêm 100 workers có giải quyết deadline 60 giây không?

**Đáp:** không. Năng lực tối đa theo rate chỉ khoảng 1.200 units trong phút nếu không có burst allowance; cần quota/rate hợp lệ cao hơn, phân bổ traffic khác hoặc thay deadline. Queue vẫn lưu công việc nhưng không làm tăng provider throughput.

### B. 3 pods, mỗi pod limiter 10/s, provider cap 15/s

**Hỏi:** rủi ro?

**Đáp:** aggregate có thể 30/s, gấp đôi cap. Dùng central/distributed rate controller hoặc phân bổ quotas tổng không vượt 15/s.

### C. 100 sends, mỗi send có 3 recipients

**Hỏi:** nếu provider bill theo recipient thì dùng 100 hay 300 units?

**Đáp:** tối đa 300 recipient slots trước khi xét duplicates/provider-specific rules. Không mặc định 100 vì chỉ có 100 lời gọi send.

### D. Outbox có 10.000 marketing jobs, OTP chờ 20 giây

**Hỏi:** tối ưu scheduler thế nào?

**Đáp:** priority lanes và reserved critical capacity; không dùng FIFO chung. Kiểm tra TTL và P99 acceptance latency riêng cho OTP.

### E. SMTP authentication failed sau rotate secret

**Hỏi:** có nên retry mỗi giây?

**Đáp:** không. Đây thường là lỗi config/auth, cần dừng hoặc mở circuit, alert và sửa credentials; retry vô hạn chỉ làm backlog và connection attempts tăng.

### F. Network reset sau DATA

**Hỏi:** có thể gửi lại qua provider B?

**Đáp:** chỉ sau reconciliation hoặc theo risk policy chấp nhận trùng có chủ đích. Timeout không chứng minh provider A chưa accepted.

### G. Provider có monthly fee thấp nhưng giữ content ở region không được phép

**Hỏi:** có chọn vì giá rẻ?

**Đáp:** không. Data residency, privacy và hợp đồng là ràng buộc bắt buộc.

### H. Attachment PDF 20 MiB, max MIME 25 MiB

**Hỏi:** file 20 MiB chắc chắn gửi được không?

**Đáp:** không. Base64 tăng khoảng 33%, cộng MIME overhead, có thể vượt 25 MiB. Cần validate encoded size hoặc gửi link an toàn nếu policy cho phép.

### I. Provider quota còn 100 units, bulk cần 100 và OTP sắp tới

**Hỏi:** cho bulk dùng hết không?

**Đáp:** không nếu policy đã reserve critical. Quota scheduler/admission cần giữ phần dự phòng hoặc quyết định ưu tiên phù hợp.

### J. Daily cap chưa hết nhưng provider throttle liên tục

**Hỏi:** vì sao?

**Đáp:** có thể vi phạm per-second/request/connection/domain limit hoặc bị dynamic reputation throttling. Daily volume chỉ là một ràng buộc.

### K. Queue trống nhưng delivered rate giảm

**Hỏi:** worker scale có giúp?

**Đáp:** chưa chắc. Queue trống và accepted ổn cho thấy submission không phải bottleneck; kiểm tra bounce, destination server behavior, authentication/reputation và provider events.

### L. Cost tăng nhưng số business events không tăng

**Hỏi:** điều tra gì đầu tiên?

**Đáp:** recipient fan-out, duplicate notifications, retry attempts, payload bytes, provider billing units và logs; có thể là retry/loop chứ không phải tăng nhu cầu.

### M. Một tenant gửi 90% traffic

**Hỏi:** có nên chia quota theo tenant?

**Đáp:** nếu fairness/SLA cần, dùng weighted shares/budgets và có thể subaccounts; kiểm tra parent quota và reputation isolation.

### N. OTP còn TTL 10 giây, quota next available 40 giây

**Hỏi:** cứ queue đến lúc có permit?

**Đáp:** không nếu token sẽ vô hiệu. Mark EXPIRED và cho client/UX một cách xử lý phù hợp, tránh gửi token chết.

### O. Provider API nhận batch 1.000 recipients

**Hỏi:** có phải chỉ tốn một quota unit?

**Đáp:** không tự suy ra. Một API request có thể được tính thành 1.000 recipient units, và partial success cần theo dõi theo item. Đọc contract cụ thể.

### P. Outbox worker đã nhận permit, nhưng crash trước SMTP

**Hỏi:** có nên tính quota đã sử dụng?

**Đáp:** phải tách local reservation với provider usage. Có thể reclaim local capacity theo policy, nhưng không dùng local ledger như báo cáo billable authoritative.

### Q. Outbox worker gửi thành công rồi crash trước markAccepted

**Hỏi:** retry thế nào?

**Đáp:** outcome có thể UNKNOWN với worker mới. Dùng attempt history/provider reconciliation nếu có; không mặc định gửi lại.

### R. Worker load test đạt 400 sends/s nhưng provider cap 50 recipients/s

**Hỏi:** hệ thống có scale tốt không?

**Đáp:** local benchmark chỉ chứng minh năng lực compose/attempt, không chứng minh provider throughput được phép. End-to-end capacity phải tính limiter/quota và provider acceptance.

### S. Marketing muốn gửi newsletter ngay khi daily cap đã hết

**Hỏi:** có thể tự tạo account phụ để vượt hạn mức?

**Đáp:** không thiết kế để lách policies. Cần provider-approved quota expansion, schedule phù hợp hoặc phương án hợp đồng khác.

### T. Một provider rẻ hơn 15% nhưng không có signed delivery webhooks

**Hỏi:** lựa chọn thế nào?

**Đáp:** đánh giá chi phí tổng cùng security/integration/observability requirements. Không thể chỉ so giá/1.000 recipients nếu cần trạng thái delivery tin cậy và sự kiện không thể xác thực.

## 47. Mẫu Architecture Decision Record cho hệ thống mail

Khi quyết định đổi provider hoặc tăng scale, nên ghi một **Architecture Decision Record (ADR)** để có thể giải thích tại sao team chọn mức quota/chi phí/độ tin cậy cụ thể.

~~~text
Title:
  Mail delivery capacity and provider strategy

Status:
  Proposed / Accepted / Superseded

Context:
  - Business purposes: OTP, receipts, campaigns
  - Daily/monthly logical recipients
  - Peak units/second and burst duration
  - Payload size p95/p99
  - Current provider quotas and billing terms
  - Delivery/privacy/security requirements

Decision drivers:
  - Critical acceptance latency SLO
  - Quota headroom and retry budget
  - Data residency and authentication
  - Operational complexity
  - Total cost of ownership

Options:
  A. Single SMTP provider + durable outbox
  B. Single ESP HTTP API + durable outbox
  C. Primary + secondary provider with failover

Chosen option:
  ...

Expected capacity:
  - Recipients/day
  - Recipients/second sustained
  - Burst reserve
  - Backlog drain time after 30-minute outage

Failure policy:
  - Retryable / permanent / UNKNOWN
  - TTL and expiry
  - Reconciliation and dedup
  - Circuit breaker and incident controls

Cost assumptions:
  - Billable unit definition
  - Base/variable price
  - Storage/egress/compute/on-call
  - Growth sensitivity

Validation:
  - Fake-provider load tests
  - Quota aggregation across replicas
  - Deliverability/security review
  - Provider contract and invoice reconciliation

Revisit triggers:
  - 75% daily quota usage for sustained period
  - p99 SLO failure
  - Vendor pricing change
  - New region/compliance requirement
  - Retry/UNKNOWN ratio outside budget
~~~

Các trigger trên chỉ là **mẫu minh họa**; chọn ngưỡng dựa trên SLO, mức reserve và traffic profile. Việc ghi ADR tránh lỗi “đổi công nghệ vì nhà cung cấp đang giảm giá” mà bỏ quên failure behavior hoặc tổng chi phí.

### Những câu hỏi ADR cần trả lời thẳng

1. Đơn vị quota và billing thực sự là gì?
2. Nếu provider chỉ chạy 50% công suất, critical notifications còn đạt deadline không?
3. Nếu quota hết, traffic nào bị pause trước?
4. Nếu SMTP accepted nhưng response mất, hệ thống làm gì?
5. Ai có quyền tạm dừng bulk hoặc chuyển provider?
6. Có thể xác nhận trạng thái người nhận ở mức nào?
7. Metrics nào cho biết backlog đang vượt khả năng drain?
8. Khi số recipients tăng gấp 5, phần nào phải thay đổi?

## 48. Checklist trước khi triển khai và mở rộng

### Dữ liệu và mô hình tải

- Xác định **event → logical notification → recipients → attempts**.
- Có estimates trung bình, p95, p99 và burst windows.
- Có dự báo volume theo tháng/quý và traffic campaigns.
- Có payload size profile, attachments và retention.
- Có deadline/SLO theo purpose, không chỉ tổng emails/day.
- Có thống kê duplicate/suppression/consent để tránh ước lượng cao hoặc thấp sai.

### Provider contract

- Biết quota theo recipients/messages/API requests.
- Biết daily/monthly và rate windows, timezone/reset semantics.
- Biết connection, max MIME size, batch limits.
- Có thông tin quota usage/remaining và độ trễ cập nhật.
- Kiểm tra verified domains, SPF/DKIM/DMARC, TLS/auth.
- Xác minh region, data processing terms và retention.
- Biết bounce/complaint/reporting và khả năng signed webhooks.
- Có escalation/support khi cần tăng quota.

### Chi phí

- Phân biệt billable units và attempts.
- Tính fixed, variable và tier/overage.
- Tính compute/DB/queue/egress/attachments/monitoring/on-call.
- Có base/growth/stress scenarios.
- Có cost per logical/accepted/delivered unit với định nghĩa rõ.
- Có budget alerts và showback/chargeback khi multi-tenant.
- Có reconciliation với invoices, không chỉ local estimates.

### Throughput và worker design

- Dùng durable outbox/queue khi cần reliability.
- Worker bounded concurrency và timeout hợp lý.
- Có global/distributed limiter đúng quota scope.
- Có cả rate và volume windows.
- Có per-purpose/tenant fairness và critical reserve.
- Có per-domain pacing nếu provider/delivery thực tế yêu cầu.
- Permit denial reschedule, không giữ threads sleep.
- Claim jobs atomic với lease/fencing và batch sizing phù hợp.
- Không giữ DB transaction mở qua SMTP I/O.

### Retry và availability

- Phân loại retryable, permanent, throttled và UNKNOWN.
- Có exponential backoff/jitter, retry budget và expiry.
- Có circuit breaker/bulkhead và health status.
- Multi-provider failover được review cho unknown outcomes.
- Có suppression policy chung và webhook dedup.
- Không khẳng định exactly-once SMTP.
- Có runbook khi quota hết, outage, provider reject hoặc cost spike.

### Security và privacy

- Không gửi credentials hoặc raw tokens vào logs.
- Template/recipient links được validate.
- MIME/attachments có size limit, storage/streaming policy.
- Data residency được xem là ràng buộc.
- Webhooks được xác thực, chống replay và idempotent.
- Suppression/consent được tôn trọng theo purpose.
- Có retention và quyền truy cập content/attempt history.

### Kiểm thử và vận hành

- Fake/sandbox provider mô phỏng đúng quota units và windows.
- Test nhiều replicas không vượt global cap.
- Test burst, outage, recover/drain, retry storm.
- Test expired OTP và priority fairness.
- Test large MIME + attachments và memory usage.
- Test UNKNOWN-after-acceptance và provider failover.
- Theo dõi oldest pending age, quota remaining, p99 time to acceptance.
- Theo dõi estimated vs provider-reported usage/cost.
- Có alerts trước khi quota/budget thực sự cạn.
- Có kế hoạch tăng tier/capacity khi ngưỡng dự báo bị vượt.

## 49. Tóm tắt nguyên tắc cốt lõi

~~~text
JavaMailSender
    = SMTP transport abstraction
    != quota manager
    != durable job queue
    != delivery confirmation

Business events
    != logical notifications
    != recipient units
    != send attempts
    != provider billable units

Daily quota
    != per-second rate
    != concurrent connection limit

More threads/pods
    != more provider allowance

Peak throughput
    -> size by burst and deadlines, not average/day

Queue backlog
    -> watch oldest age and net drain rate

Global quota across pods
    -> distributed coordination

Critical vs bulk
    -> reserved capacity and fair scheduling

Retry
    -> classify failures, backoff, jitter, budget

UNKNOWN submission
    -> reconciliation, not automatic double-send

Transactional outbox
    -> durable intent
    != exactly-once SMTP

MIME attachments
    -> encoding overhead, storage, network cost

Provider billing
    -> verify unit and price tiers

SMTP accepted
    != delivered
    != opened

Best provider choice
    -> quota + SLO + reputation + security + compliance
       + operations + total cost
~~~

**Đánh giá quota, chi phí và khả năng mở rộng** trong Spring Framework Mail là một quyết định **end-to-end**, không chỉ là chọn SMTP host hoặc đặt số luồng cho JavaMailSender. Cần bắt đầu bằng việc xác định **đơn vị tải thật** (business events, notifications, recipients và attempts), so khớp các cửa sổ quota với traffic peak và deadline nghiệp vụ, rồi thiết kế **outbox bền vững, limiter toàn cụm, scheduler công bằng và retry có kiểm soát**. Chi phí phải bao gồm **giá provider, lưu trữ, băng thông, attachments, compute, logging và vận hành**, đồng thời tách **accepted** khỏi **delivered**. Khi có đủ metrics, thử nghiệm tải bằng provider giả lập/sandbox, chính sách UNKNOWN và runbook xử lý cạn quota, hệ thống có thể tăng quy mô mà không hy sinh khả năng gửi email quan trọng, an toàn dữ liệu hoặc ngân sách.
