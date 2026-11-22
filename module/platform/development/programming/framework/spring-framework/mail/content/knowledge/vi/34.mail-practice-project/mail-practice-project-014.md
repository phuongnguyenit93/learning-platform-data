# Đánh giá khả năng mở rộng và giới hạn của dự án

## 1. Mục tiêu của bài thực hành

Ở những bài đầu của **Spring Framework Mail**, ta thường đánh giá chức năng bằng câu hỏi: “Ứng dụng có gửi được một email hay không?”. Khi hoàn thiện **dự án thực hành**, câu hỏi đó chưa đủ. Một hệ thống có thể gửi thành công 10 email trong môi trường phát triển nhưng gặp vấn đề khi nhận 10.000 yêu cầu cùng lúc, đính kèm nhiều tệp PDF, chạy trên ba pod hoặc bị SMTP provider từ chối gửi trong vài phút.

Mục tiêu bài này là **đánh giá một dự án gửi email Spring Boot/Spring Mail bằng bằng chứng kỹ thuật**, từ đó trả lời:

- Lưu lượng nào dự án xử lý được **với độ trễ chấp nhận được**?
- Giới hạn do mã ứng dụng, bộ nhớ, database, số worker hay SMTP provider?
- Khi có backlog, dự án có làm mất công việc hoặc gửi trùng email?
- Một tenant gửi nhiều có ảnh hưởng tenant khác không?
- Gửi file lớn hoặc gửi tới nhiều người nhận ảnh hưởng memory và quota ra sao?
- Nếu provider chậm, mất kết nối hoặc giảm hạn mức, ứng dụng phục hồi thế nào?
- Hệ thống có đủ metrics, logging và trạng thái để giải thích thất bại?
- Khi tăng tải, nên tối ưu phần nào trước và cần **chấp nhận giới hạn nào**?

Kết quả mong đợi không phải một tuyên bố chung chung như “hệ thống scalable”, mà là **báo cáo gồm giả định, phương pháp đo, số liệu, giới hạn quan sát được và kế hoạch nâng cấp**.

> **Phạm vi minh họa:** Bài dùng một dự án mẫu Spring Boot tạo email theo nghiệp vụ, dựng MIME bằng `MimeMessageHelper`, gửi qua `JavaMailSender`, tùy chọn transactional outbox và worker. Đây là mô hình tham chiếu để người học tự áp dụng vào dự án thực hành của mình, **không phải kết quả benchmark của một repository đã được chạy thực tế**. Mọi giá trị số trong ví dụ là giả định hoặc kết quả tính minh họa, không phải số đo đã xác nhận.

## 2. Định nghĩa “mở rộng được” trước khi đánh giá

Khả năng mở rộng (*scalability*) nghĩa là hệ thống có thể tăng mức công việc hữu ích khi bổ sung tài nguyên hoặc cải tiến kiến trúc, **trong những ràng buộc cụ thể** về độ trễ, độ tin cậy, chi phí, bảo mật và provider limits.

Cần phân biệt:

| Thuộc tính | Câu hỏi |
|---|---|
| **Throughput** | Bao nhiêu email/recipient được provider chấp nhận mỗi giây hoặc mỗi phút? |
| **Latency** | Bao lâu từ khi tạo intent đến khi bắt đầu gửi hoặc được SMTP accepted? |
| **Capacity** | Trong workload và SLO hiện tại, tối đa bao nhiêu request/job có thể xử lý bền vững? |
| **Burst tolerance** | Chịu đợt tăng đột ngột bao lâu mà backlog không mất kiểm soát? |
| **Elasticity** | Tăng/giảm worker có cải thiện throughput mà vẫn tôn trọng quota không? |
| **Reliability** | Sự cố có làm mất intent, trùng attempt hoặc kẹt job không? |
| **Recovery** | Hệ thống giải quyết backlog sau outage nhanh đến mức nào? |
| **Fairness** | Tenant hoặc loại email ít tải có bị những chiến dịch lớn làm đói tài nguyên không? |
| **Operational scalability** | Tăng quy mô có khiến điều tra và hỗ trợ sự cố trở nên không thể thực hiện? |
| **Cost efficiency** | Chi phí DB/Redis/worker/provider/observability trên mỗi đơn vị hữu ích ra sao? |

Đừng nhầm:

- **Số HTTP requests trả `202 Accepted`** với số SMTP messages thực sự submitted.
- **SMTP accepted** với email đã vào hộp thư người nhận.
- **Số threads** với email/giây.
- **Số messages** với **số SMTP envelope recipients**.
- **Lưu job vào Redis/queue** với guarantee exactly-once delivery.

Một đánh giá đúng phải đặt tên chính xác cho từng mốc và số đo.

## 3. Mô hình dự án tham chiếu và ranh giới đo

Một dự án Spring Mail thực hành có thể theo một trong hai kiến trúc.

### Phương án A: gửi đồng bộ

~~~text
HTTP request
    |
    v
Spring Controller
    |
    v
Business/Notification Service
    |
    v
MimeMessageHelper + JavaMailSender
    |
    v
SMTP provider
    |
    v
HTTP response
~~~

Đơn giản, dễ demo, nhưng request giữ thread/connection cho tới khi SMTP call hoàn tất hoặc timeout. Nếu SMTP chậm, web thread pool và latency chịu ảnh hưởng trực tiếp.

### Phương án B: nhận intent bền vững, gửi bất đồng bộ

~~~mermaid
flowchart TD
    A[Business operation or API] --> B[Validate intent and authorization]
    B --> C[Commit business data + mail outbox]
    C --> D[Return queued notification ID]
    C --> E[Due-job scheduler]
    E --> F[Atomic claim and eligibility]
    F --> G[Rate / concurrency gate]
    G --> H[Create MIME and SMTP submit]
    H --> I[Persist outcome and attempts]
    I --> J[Metrics / audit / status query]
    H --> K[Provider feedback if available]
    K --> J
~~~

Phương án B tách thời gian phản hồi HTTP khỏi SMTP, nhưng đòi hỏi thêm database/outbox, scheduler/worker, ownership, retry và cảnh báo backlog. **Bất đồng bộ không làm tăng quota do provider cấp**; nó chủ yếu giúp điều hòa tải, giảm coupling và phục hồi tốt hơn.

Nếu dự án đang gửi đồng bộ, vẫn có thể đánh giá toàn bộ các giới hạn của nó. Phần outbox trong bài được trình bày như **hướng mở rộng**, không giả định mọi dự án đã triển khai.

### Những thành phần nằm trong phạm vi đánh giá

| Thành phần | Trách nhiệm | Chỉ số cần quan sát |
|---|---|---|
| API/application | Xác thực, tạo notification intent | Request rate, latency, error, idempotency |
| Template/render | Render text/HTML, tạo PDF | CPU, memory, render latency |
| Outbox/database | Lưu trạng thái bền vững | Insert/claim latency, backlog, locks |
| Dispatcher | Chọn job và điều phối | Claim rate, age, in-flight jobs |
| Rate limiter | Bảo vệ quota account/tenant | Permit, denied, wait time |
| SMTP adapter | Tạo và submit MIME | Connect/read/write latency, accepted, rejection |
| SMTP provider | Nhận và chuyển email | Published quota, throttling, trace |
| Delivery feedback | Bounce/delivery nếu có | Event delay, dedup, state updates |
| Operations | Metrics, tracing, logs, recovery | Time to detect/recover, alert quality |

## 4. Trước khi đo: lập bản kê năng lực và ràng buộc

Một báo cáo đánh giá có thể bắt đầu bằng bảng:

| Câu hỏi | Dữ liệu cần thu thập |
|---|---|
| Có bao nhiêu Spring Boot replicas? | Số pod/process, CPU/memory limits |
| Mỗi replica có bao nhiêu SMTP workers? | Executor size, queue capacity, in-flight limits |
| Dự án dùng loại mail nào? | `SimpleMailMessage` hay `MimeMessage`, HTML, file |
| SMTP provider nào? | Host/API route, giới hạn thật từ hợp đồng |
| Một account hay nhiều accounts? | Quota scope chia sẻ giữa credentials |
| Provider đếm theo gì? | Message, recipients, daily recipients, connections |
| Email có kích thước bao nhiêu? | P50/P95/P99 attachment/payload bytes |
| Gửi đồng bộ hay outbox? | Contract API và trạng thái lưu trữ |
| Có database/broker nào? | PostgreSQL/MySQL/Redis/RabbitMQ, durability |
| Mỗi tenant gửi ra sao? | Gói dịch vụ, traffic distribution, burst |
| Retry được thực hiện ở đâu? | Worker, interceptor, scheduler, provider |
| Có kiểm tra gửi trùng không? | Business idempotency key, attempt history |
| Có delivery webhooks không? | Khả năng xác định delivered/bounced |

Thông tin thực tế phải đến từ cấu hình và telemetry của dự án được đánh giá. **Không tự suy luận SMTP quota theo tên provider**; các giới hạn thay đổi theo account, gói dịch vụ, reputation, region và chính sách.

### Mẫu phiếu ghi giả định

~~~text
Project/version      : mail-practice / git revision ...
Environment          : staging, isolated
Date/time range      : ...
App replicas         : ...
CPU/RAM per replica  : ...
DB / broker          : ...
Provider/sink        : ...
Account quota scope  : ...
Rate units           : messages/s + recipients/day
Message mix          : 80% text, 15% HTML, 5% PDF
Avg recipients/msg   : ...
Payload size P95     : ...
Warm-up time         : ...
Observation window   : ...
Data privacy         : synthetic recipients/content only
~~~

Ghi giả định ngay từ đầu để người khác hiểu vì sao cùng một hệ thống có kết quả khác nhau trên máy developer và môi trường triển khai.

## 5. Mô tả workload bằng hình dạng tải, không chỉ tổng số email

Hai dự án cùng gửi 100.000 email/ngày vẫn có tải rất khác nhau:

~~~text
Workload A:
  100,000/day distributed evenly
  ~1.16 messages/s on average

Workload B:
  100,000/day
  80,000 submitted over a 10-minute campaign window
  ~133.33 messages/s during the burst
~~~

Nếu provider account chỉ cho phép 20 messages/s, workload B **không thể được submit hết trong 10 phút** qua account đó, dù ứng dụng có 100 worker threads. Cần điều chỉnh lịch, tăng quota được phép hoặc phân bổ tới routes hợp lệ theo chính sách provider.

Các trục cần mô phỏng:

1. **Arrival rate:** requests/second hoặc jobs/second.
2. **Peak factor:** mức burst so với average.
3. **Message mix:** plain text, HTML, nhiều attachments.
4. **Recipient fan-out:** một message có 1, 10 hay 100 recipients.
5. **Payload distribution:** kích thước P50/P95/P99, không chỉ trung bình.
6. **Tenant distribution:** 1 tenant áp đảo hay phân bố đều.
7. **Priority:** OTP/transactional khác marketing/bulk.
8. **Schedule:** nhiều job cùng `scheduled_at` hay rải đều.
9. **Failure mix:** temporary rejects, authentication outage, timeout.
10. **Recovery pattern:** backlog sau restart và rolling deployment.

### Tạo test datasets có phân bố

~~~text
Small transactional:
  1 recipient, text+HTML, no attachment

Medium transactional:
  1 recipient, PDF 300 KiB

Large report:
  1 recipient, XLSX 8 MiB

Multi-recipient:
  20 envelope recipients in one message

Bulk tenant:
  5,000 messages arriving almost simultaneously
~~~

Các kích thước và tỷ lệ trên là ví dụ để tạo fixture. Không dùng dữ liệu khách hàng hay tài khoản SMTP production khi load test.

## 6. Định nghĩa SLI và SLO trước khi benchmark

Một **SLI** (*Service Level Indicator*) là đại lượng quan sát; **SLO** (*Service Level Objective*) là mục tiêu đặt cho SLI trong một cửa sổ.

Đối với hệ thống mail, nên có nhiều mốc:

~~~text
intentCreatedAt
     |
     v
outboxCommittedAt
     |
     v
attemptStartedAt
     |
     v
submittedAt (if SMTP accepted)
     |
     v
deliveredAt (only if trustworthy event exists)
~~~

| SLI | Công thức/định nghĩa | Diễn giải |
|---|---|---|
| API accept latency | `responseAt - requestAt` | Client chờ bao lâu để enqueue |
| Queue delay | `attemptStartedAt - scheduledAt` | Trễ từ lúc được phép gửi tới khi thử |
| SMTP submission latency | `smtpCallCompletedAt - smtpCallStartedAt` | Transport call mất bao lâu |
| End-to-submission | `submittedAt - intentCreatedAt` | Tổng thời gian tới provider accepted |
| Due backlog age | `now - scheduledAt` cho job đã tới hạn | Job trễ nhất bao lâu |
| Acceptance ratio | accepted attempts / definitive attempts | Sức khỏe submission, phải phân loại UNKNOWN |
| Expiry ratio | expired jobs / eligible jobs | Thông báo nào không còn hữu ích |
| Duplicate intent rate | duplicate business intents / total intents | Chống request/event redelivery |

Ví dụ mục tiêu **giả định**:

~~~text
Transactional:
  99% eligible jobs begin SMTP attempt <= 30 seconds
  after scheduledAt (under stated provider quota condition).

Bulk:
  95% jobs begin SMTP attempt within agreed campaign window.

Reliability:
  No durable mail intent lost during application restart test.
~~~

Không mặc định rằng “SMTP `send()` không ném exception” tức là *delivered*. `JavaMailSender` là outbound submission API; inbox delivery phụ thuộc provider và receiving side. Nếu không có nguồn delivery event đáng tin, không đặt SLO kiểu “99.9% vào inbox trong 5 giây” như một phép đo đã có.

### Nêu rõ điều kiện SLO

Một SLO meaningful phải ghi:

- Traffic class nào được tính.
- Cửa sổ đánh giá (ví dụ 7 ngày).
- Bắt đầu và kết thúc tính ở timestamp nào.
- Có loại trừ jobs chưa đến lịch, bị người dùng hủy, hết consent không.
- Có loại trừ hết quota provider không, và việc đó có được thỏa thuận không.
- Nguồn dữ liệu và sampling.

Nếu loại trừ mọi outage và quota denial khỏi SLO, metric có thể trông rất đẹp nhưng không phản ánh trải nghiệm người dùng.

## 7. Quy đổi request rate, message rate và recipient rate

Đây là một trong những bước dễ sai nhất khi đánh giá mail project.

Giả sử mỗi notification intent tạo đúng một SMTP message. Đặt:

- `λ`: notification intents/second.
- `m`: số SMTP messages trung bình trên mỗi intent.
- `r`: số envelope recipients trung bình mỗi message.

Khi đó:

\[
\text{messageDemandPerSecond} = \lambda \times m
\]

\[
\text{recipientDemandPerSecond}
 = \lambda \times m \times r
\]

Nếu:

~~~text
lambda = 12 intents/s
m      = 1 SMTP message/intent
r      = 3 recipients/message
~~~

thì:

~~~text
message demand   = 12/s
recipient demand = 36/s
~~~

Nếu provider giới hạn 20 recipients/s thì bottleneck là **recipient quota**, không nhất thiết message count. Bcc cũng có thể tính vào số envelope recipients. Khi provider áp nhiều loại quota, mỗi giới hạn cần được quy về **đúng đơn vị** trước khi xác định capacity.

**Lưu ý:** `m` và `r` là trung bình để capacity planning; với kiểm tra admission từng job, cần dùng **cost thực tế** của job thay vì làm tròn theo trung bình.

## 8. Mô hình năng lực: bottleneck quyết định throughput bền vững

Đối với workload có một recipient mỗi message, một ước lượng ban đầu:

\[
\mu_{\mathrm{effective}}
 \le \min(\mu_{\mathrm{app}},
         \mu_{\mathrm{DB}},
         \mu_{\mathrm{provider}},
         \mu_{\mathrm{quota}})
\]

Trong đó:

- `μapp`: số message/giây ứng dụng có thể chuẩn bị và submit.
- `μDB`: số job/giây database/outbox có thể claim/update.
- `μprovider`: năng lực xử lý của provider/transport.
- `μquota`: hạn mức theo account/tenant/recipient.

Đây là **mô hình trần đơn giản**, không phải công thức dự báo hoàn hảo. Với fan-out nhiều recipients, phải chuẩn hóa đơn vị; với nhiều provider accounts, tổng capacity còn phụ thuộc quyền routing, quota global và phân phối tải.

Ví dụ minh họa:

| Thành phần | Năng lực giả định |
|---|---:|
| Template + MIME rendering | 180 messages/s |
| Database claim + status persistence | 95 jobs/s |
| SMTP adapter ở concurrency đã cấu hình | 45 messages/s |
| Provider account safe rate | 30 messages/s |
| Tenant aggregate policies | 27 messages/s |

Giả sử mỗi job = một message và một recipient, trần ban đầu là:

\[
\min(180,95,45,30,27)=27\ \text{messages/s}
\]

Tăng CPU để đưa rendering từ 180 lên 400/s **không cải thiện trần 27/s**. Cần xem quota/tenant distribution hoặc workflow trước khi scale thêm app pods.

### Throughput thực tế có thể thấp hơn trần

Do latency variation, connection setup, job cost khác nhau, attachment lớn, head-of-line blocking, retries, quota, GC, DB lock contention, fairness policy và reserved capacity. **Trần lý thuyết chỉ là giả thuyết cần đo**, không nên ghi nó là benchmark đã đạt.

## 9. Little's Law và ước lượng số công việc đang xử lý

Với một hệ thống ổn định và định nghĩa nhất quán:

\[
L = \lambda W
\]

Trong đó:

- `L`: số jobs trung bình ở một đoạn pipeline.
- `λ`: throughput thực tế đi qua đoạn đó, jobs/second.
- `W`: thời gian trung bình một job ở đoạn đó, seconds.

Ví dụ khi SMTP call trung bình 0,4 giây và giữ ổn định 20 submissions/second:

\[
L = 20 \times 0.4 = 8\ \text{in-flight submissions}
\]

Suy ra cần khoảng 8 concurrent operations **trung bình**, và nên có headroom do tail latency, CPU scheduling, TLS setup và biến động mạng. Không chọn concurrency = 8 rồi tin rằng sẽ luôn đạt 20/s.

### Khi queue không ổn định

Nếu:

~~~text
Arrival demand = 40 jobs/s
Accepted service rate = 25 jobs/s
~~~

thì backlog tăng gần:

\[
\Delta Q / \Delta t \approx 40-25=15\ \text{jobs/s}
\]

Sau 10 phút, nếu rate giữ nguyên và bỏ qua expiry/cancellation:

\[
Q \approx 15 \times 600 = 9000\ \text{jobs}
\]

**Không dùng Little's Law một cách máy móc cho queue đang tăng không giới hạn**; giả định trạng thái ổn định không thỏa. Với workload burst, cần tách giai đoạn tích backlog và giai đoạn drain.

## 10. Đánh giá thời gian tiêu backlog sau sự cố

Giả sử SMTP provider ngừng hoạt động 20 phút, hệ thống vẫn nhận 10 jobs/s. Backlog có thể tăng:

\[
10 \times 20 \times 60=12\,000\ \text{jobs}
\]

Khi provider hoạt động trở lại:

~~~text
New demand         = 10 jobs/s
Safe send capacity = 25 jobs/s
Net drain rate     = 15 jobs/s
Backlog            = 12,000 jobs
~~~

Ước lượng:

\[
t_{\mathrm{drain}}
=\frac{12\,000}{25-10}=800\ \text{s}
\]

tương đương khoảng 13 phút 20 giây, **nếu không có daily quota, retries, job expiry hoặc traffic thay đổi**.

Trong thực tế, daily quota có thể cạn khi backlog còn lớn; provider có thể throttle; bulk và transactional lanes có policy khác nhau. Vì vậy dự báo drain cần dùng **quota windows, job cost và priority** chứ không chỉ chia tổng jobs cho số workers.

### Vì sao backlog lớn không có nghĩa cần tăng worker ngay?

Nếu provider chỉ cho 25/s và worker đã gửi được 25/s, thêm replicas không tăng accepted throughput. Ngược lại, nó có thể tăng DB claim contention, Redis rate-gate requests, SMTP connections và nguy cơ job lease hết hạn khi claim nhiều hơn năng lực gửi.

Chỉ scale worker khi bằng chứng cho thấy **ứng dụng chưa sử dụng hết nguồn capacity hợp lệ** và bottleneck thực sự nằm ở worker/CPU/concurrency.

## 11. Giới hạn của thiết kế gửi đồng bộ

Với controller gọi SMTP trực tiếp:

~~~java
@PostMapping("/send")
public ResponseEntity<String> sendMail(
        @RequestBody MailRequest request) {
    mailService.send(request);
    return ResponseEntity.ok("submitted");
}
~~~

Request/response bị gắn với duration của SMTP.

Ví dụ:

~~~text
50 concurrent web threads
SMTP call latency = 2 seconds
~~~

Khi không có bottleneck khác, trần theo concurrency:

\[
\text{theoretical rate} \approx \frac{50}{2}
=25\ \text{requests/s}
\]

Đây là phép tính minh họa, không bao gồm overhead và tail latency. Nếu SMTP latency lên 10 giây, cùng số threads chỉ còn khoảng 5 requests/s; các request khác còn phải chờ/timeout.

### Hệ quả khi SMTP outage

- HTTP latency tăng và web threads bị chiếm.
- Có thể chặn hoạt động nghiệp vụ khác dùng cùng executor.
- Client timeout rồi retry, tạo duplicate business intents.
- Database transaction bị giữ nếu gửi trong `@Transactional`.
- API response có thể nói “email failed” dù provider outcome không chắc chắn.

### Khi nào gửi đồng bộ vẫn hợp lý?

Một công cụ nội bộ lưu lượng thấp, không có giao dịch nghiệp vụ liên quan, cần kết quả SMTP submission ngay và chấp nhận latency có thể dùng direct send. Nhưng phải có timeouts, giới hạn concurrency, kiểm tra quyền, phân biệt accepted với delivered và không giữ DB transaction qua SMTP.

## 12. Giải pháp gửi bất đồng bộ có durable outbox

Một cải tiến thường được đề xuất:

~~~text
POST /notifications
        |
        v
Validate + store mail intent in DB
        |
        v
Return HTTP 202 Accepted
        |
        v
Scheduler/worker polls due jobs
        |
        v
Acquire ownership and quota permit
        |
        v
JavaMailSender.send(...)
        |
        v
Persist submission outcome
~~~

### Ưu điểm

- HTTP response không chờ SMTP.
- Không mất job chưa xử lý khi worker restart nếu lưu đúng durability.
- Có thể retry với backoff/deadline, truy vấn trạng thái để hỗ trợ người dùng.
- Scale workers độc lập web replicas.
- Phân luồng transactional/bulk, quota/fairness.

### Chi phí mới

- Cần database/broker, scheduler/dispatcher và transactional consistency.
- Cần quản lý ownership, leases, attempt state.
- Cần retention, schema migrations và cleanup.
- Cần metrics/alert để phát hiện queue kẹt.
- API phải mô tả trạng thái `QUEUED` thay vì `DELIVERED`.
- Có eventual consistency: người dùng được báo “đã tiếp nhận” trước khi email được submitted.

**Không viết `@Async void send(...)` rồi gọi đó là outbox.** Một executor trong RAM có thể mất jobs khi process chết hoặc redeploy.

## 13. Transactional outbox tránh mất intent trong transaction nghiệp vụ

Sai:

~~~java
@Transactional
public void completeOrder(OrderId orderId) {
    orders.markCompleted(orderId);
    sender.send(buildReceipt(orderId));
}
~~~

SMTP không rollback cùng database. Nếu SMTP accepted rồi DB rollback có thể gây email sai; SMTP timeout làm giữ lock lâu.

Một cách tốt hơn khi cùng database:

~~~text
BEGIN
  UPDATE orders SET status='COMPLETED'
  INSERT INTO mail_outbox (
      id, business_key, status, scheduled_at, ...
  ) VALUES (...)
COMMIT

Worker:
  select due jobs
  submit SMTP outside business transaction
  update outcome in short transaction
~~~

Ví dụ contract:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class OrderCompletionService {
    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderCompletionService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void completeOrder(OrderId id) {
        Order order = orders.complete(id);
        outbox.insertIfAbsent(
                MailIntent.forCompletedOrder(
                        order.id(),
                        order.customerId(),
                        order.version()));
    }
}
~~~

`OrderRepository`, `OrderId`, `MailOutboxRepository` và `MailIntent` là abstractions minh họa, không phải API có sẵn của Spring Mail. `insertIfAbsent` cần unique constraint/UPSERT theo business event key để chống race khi nhiều requests lặp.

Nếu business data và outbox nằm ở hai cơ sở dữ liệu độc lập, `@Transactional` thông thường không tự tạo atomicity xuyên hai stores. Khi đó cần producer outbox cạnh business DB, CDC hoặc cơ chế durable handoff/reconciliation phù hợp.

## 14. Schema outbox và chỉ số cần có khi mở rộng

Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    provider_account_id VARCHAR(100) NOT NULL,
    business_key VARCHAR(180) NOT NULL,
    payload_ref VARCHAR(255) NOT NULL,
    recipient_count INT NOT NULL
        CHECK (recipient_count > 0),
    status VARCHAR(24) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    attempt_count INT NOT NULL DEFAULT 0,
    claim_token UUID,
    lease_until TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    last_error_code VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_mail_business_intent UNIQUE
        (tenant_id, business_key),
    CONSTRAINT chk_mail_status CHECK (status IN (
        'PENDING', 'CLAIMED', 'PROCESSING',
        'RETRY', 'SUBMITTED', 'FAILED',
        'CANCELLED', 'EXPIRED', 'UNKNOWN'
    )),
    CONSTRAINT chk_attempt_count CHECK (attempt_count >= 0)
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (available_at, id)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX idx_mail_outbox_lease
    ON mail_outbox (lease_until)
    WHERE status IN ('CLAIMED', 'PROCESSING');
~~~

Tùy workload có thể thêm index theo `provider_account_id`, tenant, lane, priority; không tạo tất cả index chỉ vì một ví dụ, vì mỗi index tăng chi phí INSERT/UPDATE.

### Quan sát được điều gì từ bảng?

- `status`: công việc ở bước nào.
- `scheduled_at`: lúc nghiệp vụ mong muốn gửi.
- `available_at`: lúc sớm nhất được thử lại sau quota/retry.
- `attempt_count`: số lần thực sự bắt đầu submission theo contract.
- `claim_token`/`lease_until`: ownership tạm thời.
- `submitted_at`: provider accepted theo semantics adapter.
- `last_error_code`: lý do đã chuẩn hóa, tránh raw SMTP diagnostics.

Không tự gán `submitted_at` khi mới tạo intent. Không suy luận delivered vì `submitted_at` đã có.

## 15. Claim công việc trên nhiều worker không được chỉ SELECT rồi send

Một khi dự án có hai replicas, pattern:

~~~sql
SELECT id FROM mail_outbox
WHERE status = 'PENDING'
  AND available_at <= CURRENT_TIMESTAMP;
~~~

rồi gửi SMTP có thể khiến hai workers **cùng đọc và gửi một job**. Tăng worker từ 1 lên 10 nếu thiếu ownership chưa chắc làm tăng throughput hữu ích; đôi khi chỉ làm tăng email trùng.

Với PostgreSQL có thể claim atomically bằng một transaction ngắn:

~~~sql
WITH chosen AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND available_at <= CURRENT_TIMESTAMP
      AND (expires_at IS NULL
           OR expires_at > CURRENT_TIMESTAMP)
    ORDER BY available_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS job
SET status = 'CLAIMED',
    claim_token = :claim_token,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
FROM chosen
WHERE job.id = chosen.id
RETURNING job.id, job.claim_token;
~~~

Sau khi commit claim, thực hiện SMTP ngoài transaction; sau đó cập nhật outcome với điều kiện:

~~~sql
UPDATE mail_outbox
SET status = 'SUBMITTED',
    submitted_at = CURRENT_TIMESTAMP,
    claim_token = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :id
  AND claim_token = :claim_token
  AND status = 'PROCESSING'
RETURNING id;
~~~

Nếu 0 row được update, worker đã mất ownership hoặc state không hợp lệ; không bỏ điều kiện token để cưỡng ép ghi.

### Giới hạn của SKIP LOCKED

- Tránh workers tranh cùng row **trong transaction claim**.
- Không bảo đảm strict FIFO/fairness.
- Không làm DB và SMTP có một atomic transaction.
- Không xử lý gửi trùng do crash **sau khi provider đã accepted**.
- Có thể tốn tài nguyên khi số rows và frequency polling rất lớn.

Phải benchmark query/index thật trước khi tăng batch size hoặc poll interval. Batch lớn làm job đợi trong worker queue lâu, có thể khiến lease hết hạn khi chưa thực sự gửi.

## 16. State machine và retry phải rõ mới đo được reliability

Một workflow có thể có:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CLAIMED: due and claim
    PENDING --> CANCELLED: user cancel
    PENDING --> EXPIRED: deadline
    CLAIMED --> PROCESSING: attempt recorded
    CLAIMED --> PENDING: released before send
    PROCESSING --> SUBMITTED: SMTP accepted
    PROCESSING --> RETRY: definitive temporary rejection
    PROCESSING --> FAILED: definitive permanent failure
    PROCESSING --> UNKNOWN: ambiguous provider outcome
    RETRY --> CLAIMED: backoff elapsed
    RETRY --> EXPIRED: deadline
    UNKNOWN --> SUBMITTED: provider reconciliation
    UNKNOWN --> RETRY: explicit approved retry policy
~~~

Tên state là **enum ứng dụng tự định nghĩa**; Spring Mail không quản lý job lifecycle này.

Khi test scale, đo:

- Bao nhiêu attempts/job?
- Tỷ lệ `RETRY`, `FAILED`, `UNKNOWN`?
- Bao nhiêu jobs chuyển về PENDING do lease expiry?
- Bao nhiêu stale worker attempted state update bị từ chối?
- Có job nào đứng ở `CLAIMED/PROCESSING` lâu hơn timeout hợp lý?
- Max retry/expiry có được áp đúng theo loại notification?

**Số job SUBMITTED cao không đủ chứng minh reliability** nếu nhiều jobs bị gửi trùng hoặc retry vĩnh viễn.

### Backoff và jitter

Với temporary failure, ví dụ:

\[
d_n = \min(d_{\max},d_0 2^{n-1})
\]

Rồi chọn jitter để không khiến 10.000 jobs lỗi cùng lúc thức dậy chính xác cùng một giây:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryPlanner {
    private RetryPlanner() { }

    public static Instant nextAt(
            Instant now,
            int failedAttemptNumber,
            Duration base,
            Duration max) {
        if (failedAttemptNumber < 1
                || base.isZero()
                || base.isNegative()
                || max.compareTo(base) < 0) {
            throw new IllegalArgumentException("Invalid retry inputs");
        }

        long ceiling = base.toMillis();
        long maximum = max.toMillis();
        for (int i = 1; i < failedAttemptNumber; i++) {
            ceiling = ceiling > maximum / 2
                    ? maximum
                    : Math.min(maximum, ceiling * 2);
        }

        long waitMillis = ThreadLocalRandom.current()
                .nextLong(ceiling + 1);
        return now.plusMillis(waitMillis);
    }
}
~~~

Đây là helper minh họa. Với full jitter, delay có thể gần 0; production có thể đặt minimum delay, dùng provider cooldown và luôn kiểm tra expiresAt/max attempts. Nếu `base.toMillis() == 0` hoặc `max.toMillis() == 0` thì cần validate thêm thay vì gọi `nextLong(0)`; dùng Duration đủ lớn/logic guard thích hợp.

Không retry authentication/config errors như temporary throttling, và không tự refund quota/retry khi provider outcome chưa xác định.

## 17. Giới hạn cứng: SMTP provider và recipient quotas

Ứng dụng có thể tự scale compute, nhưng **không thể tự tạo thêm quota hợp đồng** của SMTP provider:

~~~text
Application produces 100 messages/s
Provider permits 20 messages/s

Sustainable accepted rate <= 20/s
Backlog grows unless source demand is controlled
~~~

Các giới hạn thường phải tra theo tài khoản cụ thể:

| Hạn mức | Cần phân biệt |
|---|---|
| Messages/s | Mỗi MIME message hoặc mỗi API request |
| Recipients/s | Tổng envelope recipients, không chỉ số `send()` |
| Recipients/day | Calendar day hay rolling 24h |
| Messages/day | Có thể khác recipient quota |
| Concurrent connections | Bao nhiêu SMTP connections được mở |
| RCPT per message | Bao nhiêu địa chỉ trong một envelope |
| Size per message | Tính sau MIME/Base64 encoding hay raw file |
| Domain/reputation throttle | Provider có thể giảm tốc động |
| Organization vs credential quota | Nhiều credentials có thể dùng chung account budget |

Khi đánh giá, ghi rõ **đơn vị, cửa sổ và phạm vi** từng hạn mức. Nhiều API keys cùng một provider organization không nhất thiết mang quota độc lập; rotate credential không tự reset budget.

### Không dùng quota rate = 100% mức công bố

Một account có thể còn luồng gửi khác, provider có cooldown/reputation policy, daily windows và response fluctuations. Có thể giữ **headroom có chủ đích** và điều chỉnh theo số đo. Không lấy một tỷ lệ giảm cố định làm “chuẩn” cho mọi provider.

## 18. Rate limiter và concurrency limiter là hai hệ khác nhau

Giả sử application dùng:

~~~java
var executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(5);
executor.setMaxPoolSize(10);
executor.setQueueCapacity(100);
~~~

Đây là **cấu hình executor**, không tự ngăn gửi quá 100 messages/second khi mỗi SMTP call trả nhanh. Nó cũng không bảo vệ 3 replicas mỗi replica có 10 workers cùng sử dụng một account.

Tách:

1. **Rate:** tokens/second/minute.
2. **Daily/rolling budget:** recipients/messages/window.
3. **Concurrency:** số SMTP operations đang diễn ra.
4. **Batch size:** số job claim đồng thời.
5. **Queue capacity:** số job đợi trong process (khác DB backlog).
6. **Tenant fairness:** thứ tự và share được phục vụ.

### Một job phải qua nhiều cổng

~~~text
Due job
  |
  +-- tenant policy allowed?
  +-- provider account quota available?
  +-- recipient cost available?
  +-- active SMTP slot available?
  +-- still before deadline?
  |
  v
Begin submission
~~~

Nếu quota chưa có permit, cập nhật `available_at` và giải phóng claim, **không tăng SMTP attempt count** vì chưa gọi provider.

### Không reserve account rồi tenant riêng rẽ

Nếu account bucket trừ token xong nhưng tenant bucket deny, budget account đã bị mất dù chưa gửi. Với distributed limiter, cần atomic multi-bucket admission hoặc reservation protocol được thiết kế rõ; không dùng hai Redis GET/SET không nguyên tử.

## 19. Fairness giữa tenant và notification lanes

Một queue FIFO:

~~~text
A1, A2, A3, ..., A100000, B1, C1
~~~

có thể khiến tenant B/C chờ lâu dù account còn năng lực hoặc A đã bị quota gate chặn. Rate limiter riêng tenant **không tự bảo đảm fairness khi chọn job**.

Các chiến lược:

| Chiến lược | Khi hữu ích | Giới hạn |
|---|---|---|
| Round robin | Phân bổ lượt chọn đơn giản | Không tính recipient cost khác nhau |
| Weighted round robin | Tenant tiers khác nhau | Cần cấu hình weight đúng |
| Deficit round robin | Job cost thay đổi | Cần duy trì deficit state |
| Priority lanes | OTP/transactional vs bulk | Strict priority có thể làm bulk starvation |
| Reserved rate/capacity | Bảo vệ SLO email quan trọng | Có thể bỏ trống năng lực khi lane nhàn rỗi |

Một test bắt buộc:

~~~text
Tenant A: 10,000 newsletter jobs arriving at once
Tenant B: 10 password reset jobs arriving later

Expected:
  Tenant B has bounded dispatch lag under quota assumptions.
  Tenant A remains within its allocated share.
  Aggregate account quota is not exceeded.
~~~

Một hệ thống có aggregate throughput tốt nhưng để OTP chờ sau hàng nghìn newsletter **không đáp ứng mục tiêu trải nghiệm**.

## 20. Backpressure: không claim nhiều hơn khả năng xử lý

Khi producer nhanh hơn SMTP, cần **backpressure** ở đầu vào hoặc workflow:

~~~text
Producer > Outbox > Dispatcher > Rate gate > SMTP provider
                             ^
                             |
                         Bottleneck
~~~

Nếu dispatcher claim 10.000 jobs rồi đưa vào unbounded executor queue:

- RAM tăng.
- Leases của những jobs chưa tới lượt có thể hết hạn.
- Hủy/đổi lịch khó đồng bộ.
- Một số jobs được retry/reclaim bởi workers khác.
- Shutdown đột ngột để lại nhiều trạng thái khó đối soát.

Nên:

- Chỉ claim một batch phù hợp với in-flight capacity.
- Executor queue có giới hạn và chính sách khi đầy.
- Khi quota deny, **defer job trong DB**, không ngủ trên worker thread.
- Giới hạn producer bulk campaigns hoặc schedule spread-out.
- Dùng priority/fairness theo tenant/lane.
- Đo queue age thay vì chỉ queue size.

### Phản hồi overload từ API

HTTP API có thể:

- Nhận và lưu durable job khi vẫn còn storage capacity/SLA.
- Trả `429 Too Many Requests` cho caller đang vượt product policy.
- Trả `503 Service Unavailable` khi hệ thống không thể ghi nhận intent an toàn.

Không trả `202 Accepted` nếu outbox insert thực sự thất bại. Nếu client timeout sau DB commit, idempotency key và status query giúp tránh tạo thêm intent.

## 21. Connection setup, TLS và SMTP timeouts

Một email gửi ra có thể tốn thời gian tại:

~~~text
DNS lookup
   -> TCP connect
   -> TLS/STARTTLS negotiation
   -> AUTH
   -> MAIL FROM
   -> RCPT TO
   -> DATA / MIME transfer
   -> final SMTP response
~~~

Đánh giá bằng số liệu **end-to-end**, không chỉ thời gian serialize MIME.

Trong Spring Boot, cấu hình gửi mail thường có:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 15000
      mail.smtp.writetimeout: 15000
~~~

Các giá trị timeout là **giả định minh họa**, không phải khuyến nghị chung cho mọi provider. Chọn theo observed latency, network path và business deadlines. Dấu hiệu:

- Timeout quá ngắn: false temporary failures.
- Timeout quá dài: giữ in-flight slots và worker threads.
- Không có timeout: call treo có thể làm capacity giảm dần tới 0.

### Connection reuse

Với `JavaMailSenderImpl`, không được mặc định rằng mỗi lời gọi `send(...)` riêng lẻ sẽ tự tận dụng connection pool bền vững theo mong muốn. Jakarta Mail/SMTP transport connection reuse và cách gửi batch phải được kiểm chứng theo version/implementation. Có thể giảm connection overhead bằng batch hợp lý và adapter/lifecycle thích hợp, nhưng phải cân nhắc partial failures, memory, fairness và quota.

**Không thay đổi cấu hình SMTP host/username/password trên một singleton sender đang phục vụ nhiều threads** để “switch provider” theo từng job. Dùng sender/adapters riêng cho từng account/route và quản lý credential có kiểm soát.

## 22. Attachment lớn và áp lực bộ nhớ

Một job chỉ chứa plain-text email có profile tài nguyên rất khác job mang PDF 20 MiB. Với `ByteArrayResource`, dữ liệu tệp được giữ trong `byte[]` và serialization MIME có thể cần thêm buffers. Phần Base64 của attachment có kích thước lớn hơn raw data, xấp xỉ 4/3 trước overhead xuống dòng và headers.

Ví dụ:

~~~text
50 concurrently prepared attachments
each raw file = 12 MiB

Raw byte[] alone:
  50 * 12 MiB = 600 MiB
~~~

Đây **chưa phải tổng heap footprint**. Có thể còn:

- Bytes tạo bởi generator.
- Byte[] copy ở các layer.
- Object graph của `MimeMessage` và attachments.
- Base64/line buffers.
- Template variables.
- Caches/connection pools/HTTP requests.
- Heap fragmentation và GC overhead.

Một benchmark chỉ dùng email text 2 KiB sẽ **không phản ánh** chi phí khi triển khai PDF/XLSX.

### Hướng cải thiện

1. Đặt max attachment size trước khi enqueue/submission.
2. Không load attachment cho tất cả due jobs trước khi có capacity gửi.
3. Giới hạn số SMTP jobs có file lớn đồng thời.
4. Dùng `FileSystemResource` hoặc một `InputStreamSource` có thể mở luồng mới khi dữ liệu lớn và lifecycle cho phép.
5. Với tài liệu rất lớn, cân nhắc secure download link có authorization và expiry thay vì gửi trực tiếp.
6. Xác định retention và snapshot/version của file khi job có retry.
7. Kiểm tra provider **MIME message-size limit**, không chỉ raw bytes.

### Repeatable stream là yêu cầu quan trọng

`ByteArrayResource` có thể mở luồng đọc mới từ byte[]. `InputStreamResource` thường chỉ đại diện stream đã mở một lần và không phù hợp để serialize MIME nhiều lần. Nếu dùng object storage, custom `InputStreamSource` phải mở được **stream mới cùng version nội dung**, không dùng one-shot stream đã hết.

### Đánh giá tệp bất thường

Test nên có:

~~~text
0-byte attachment
Small PDF < 100 KiB
Medium PDF ~1 MiB
Large XLSX ~10 MiB
Near provider size limit
Above allowed size (must be rejected before SMTP)
Invalid MIME type/extension
Unavailable storage object during retry
~~~

Không dùng nội dung thật của khách hàng cho load test hoặc dump raw attachment vào logs.

## 23. Render template/HTML/CSV cũng có giới hạn

Thời gian xử lý email bao gồm cả:

~~~text
Load business data
   -> resolve recipient/locale
   -> template rendering
   -> HTML escaping
   -> PDF/CSV generation
   -> MIME composition
   -> SMTP submission
~~~

Một template render từ 10 biến khác template truy vấn 1000 records và tạo một file Excel. Nếu app đang CPU-bound ở PDF generator, tăng SMTP workers chỉ tăng số tasks đợi/heap usage.

Các chỉ số cần đo:

- Template rendering latency P50/P95/P99.
- PDF/XLSX creation latency và allocated bytes.
- Cache hit/miss và template version.
- N+1 queries lấy dữ liệu.
- Thời gian đọc object storage.
- MIME serialization duration/bytes.
- GC pauses và heap pressure.

### Tách trách nhiệm khi cần

Nếu document generation rất nặng, cân nhắc:

~~~text
Business event
  -> document generation job
  -> durable immutable attachment reference
  -> notification job
  -> SMTP worker
~~~

Nhưng tách pipeline làm tăng trạng thái và consistency concerns. Quyết định dựa trên measurement, không chỉ vì “microservice tốt hơn”.

### CSV formula injection, HTML và tên file

Khả năng mở rộng không thể đánh đổi an toàn:

- HTML variables phải được escape/sanitize phù hợp.
- Dữ liệu CSV cho spreadsheet có nguy cơ bị diễn giải công thức nếu không xử lý.
- Attachment filename không được chứa path nội bộ/control chars hoặc PII không cần thiết.
- Email body/MIME không được log thô để debug throughput.

## 24. Database: bottleneck ở claim, update và retention

Outbox database thường chịu:

~~~text
INSERT new mail intent
SELECT/UPDATE due jobs for claim
UPDATE attempt started
UPDATE submitted/retry/failure
INSERT status event/history
SELECT status for customer support
DELETE/archive terminal jobs
~~~

Với 1000 jobs/s, một job có thể phát sinh nhiều **DB operations**, không chỉ một INSERT. Nếu mọi update còn đi qua vài indexes và audit tables, write load có thể lớn.

### Cần xem execution plans và row contention

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY')
  AND scheduled_at <= CURRENT_TIMESTAMP
  AND available_at <= CURRENT_TIMESTAMP
ORDER BY available_at, id
LIMIT 100;
~~~

Đây là truy vấn minh họa để phân tích; câu query claim thật cần transaction/lock semantics tương ứng. `EXPLAIN ANALYZE` thực sự chạy truy vấn, nên trên production phải cân nhắc chi phí và lựa chọn môi trường an toàn. Quan sát:

- Index scan hay sequential scan?
- Thời gian scan khi backlog lớn?
- Sort spill/temp disk?
- Rows filtered do chưa đến lịch?
- Lock wait khi nhiều workers?
- Connection pool saturation?

### Index là đánh đổi

Partial index cho due status:

~~~sql
CREATE INDEX idx_mail_outbox_active_due
ON mail_outbox (available_at, id)
WHERE status IN ('PENDING', 'RETRY');
~~~

giúp tìm jobs đến hạn, nhưng mỗi index làm tăng write amplification. Nếu query luôn lọc `provider_account_id`, một index bắt đầu bằng account có thể hợp lý hơn. Quyết định bằng plans và dữ liệu thực, không tạo mọi biến thể index “cho chắc”.

### Retention

Nếu giữ tất cả `SUBMITTED` jobs và raw MIME mãi:

- Bảng lớn dần.
- Index mất hiệu quả.
- Backups/restore lâu hơn.
- PII tồn tại quá nhu cầu.
- Compliance/deletion phức tạp.

Nên xác định retention của active jobs, terminal records, attempts, delivery events và payload riêng. Không xóa job `RETRY` hoặc payload chưa đến lúc gửi; không archive `PROCESSING` mà chưa hiểu outcome.

## 25. PostgreSQL queue, broker hay scheduler chuyên dụng?

Các lựa chọn:

| Phương án | Ưu điểm | Giới hạn |
|---|---|---|
| DB outbox + polling | Dễ atomic với business DB, query status tiện | DB scan/locks/write load, polling overhead |
| DB outbox + CDC relay | Giảm việc quét bảng active, tích hợp broker | CDC vận hành phức tạp, vẫn cần status/idempotency |
| RabbitMQ/Kafka consumer | Độ mở rộng tiêu thụ và buffering tốt | Event redelivery, ordering, retries/expiry/consumer idempotency |
| Delayed broker messages | Hữu ích với scheduled deliveries | Cancellation/durable state/status cần xem kỹ |
| Quartz JDBC JobStore | Cron/calendars/persistent triggers | Không tự quản lý SMTP attempts/delivery |
| Managed notification provider | Có thể cung cấp queue/template/tracking | Vendor semantics, quota, compliance, lock-in |

Không có lựa chọn nào tự bảo đảm exactly-once SMTP side effect. Database là điểm neo tốt cho transactional intent; broker có thể giúp scale consumers nhưng cần **durable handoff** từ business transaction, dedup và status tracking.

### Chọn theo bottleneck đo được

Nếu database chưa quá tải và mail demand thấp, thêm Kafka/Redis chỉ vì “scale” có thể tăng failure modes hơn lợi ích. Nếu claim polling tạo áp lực DB hoặc nhiều consumers cần độc lập, outbox relay/broker có thể đáng giá. Khi move architecture, phải có kế hoạch cutover không tạo hai đường gửi cho cùng job.

## 26. Horizontal scaling: hiệu suất không tăng tuyến tính mãi

Giả sử một worker replica có thể dựng 30 messages/s nhưng provider account chỉ chấp nhận 60/s:

| Replicas | Raw app potential | Accepted cap account | Nhận xét |
|---|---:|---:|---|
| 1 | 30/s | 60/s | App-side bottleneck |
| 2 | 60/s | 60/s | Lý tưởng chạm cap |
| 4 | 120/s | 60/s | Thêm replicas không tăng accepted |
| 8 | 240/s | 60/s | Tăng contention nếu không rate gate |

Tất cả con số là giả định cho ví dụ. Thực tế account quota có thể theo recipients/day, không phải messages/s, và không được xem như hằng số cứng ở mọi thời điểm.

### Khi app scale mà chưa có distributed limiter

~~~text
Pod A: local 30 messages/s
Pod B: local 30 messages/s
Pod C: local 30 messages/s

One shared provider account cap = 60/s
Potential aggregate = 90/s
~~~

Local limiter trên từng pod **không đủ** khi quota áp trên shared provider account. Cần shared admission control hoặc chia budget với cơ chế đảm bảo tổng.

### Scaling còn bị giới hạn bởi downstream

- Database max connections.
- SMTP concurrent connections.
- Redis rate gate throughput.
- Object storage read bandwidth.
- Network egress throughput.
- Provider reputation/recipient acceptance.
- CPU/heap của template + MIME generation.

Mỗi lần tăng replicas cần đo **throughput hữu ích, tail latency, DB waits, Redis latency, SMTP throttling và chi phí**, không chỉ CPU của pod.

## 27. Vertical scaling: nhiều CPU/RAM giải quyết gì?

Tăng CPU/RAM cho một JVM có ích khi:

- HTML/PDF rendering CPU-bound.
- GC pressure do attachments.
- Nhiều MIME instances cùng tồn tại.
- Executor quá ít workers cho SMTP latency.

Nhưng **không giải quyết**:

- Provider account quota.
- Daily recipient limits.
- Network partition.
- Exactly-once SMTP delivery.
- Tenant fairness.
- Database lock contention nếu cùng row/key.

### Quan sát JVM trước khi tăng heap

Những câu hỏi:

- Heap usage có tăng theo concurrent attachments không?
- GC pause/CPU có tương ứng với throughput giảm không?
- Object allocation nào chiếm nhiều?
- Có giữ `byte[]` sau khi gửi vì cache/queue references không?
- Có unbounded executor queues không?
- Số thread chờ socket I/O bao nhiêu?

Một OOM khi đính kèm file lớn có thể giải quyết tốt hơn bằng **bounded concurrency** và file-backed resource, thay vì chỉ tăng heap mãi.

## 28. Bottleneck không nằm ở Spring Mail thì đừng “tối ưu Spring Mail”

Một bảng triệu chứng:

| Triệu chứng | Giả thuyết ưu tiên | Bằng chứng cần |
|---|---|---|
| SMTP 4xx throttle tăng | Account/recipient quota, burst, provider reputation | SMTP codes, rate per scope |
| CPU 100%, SMTP rate còn thấp | Template/PDF/MIME rendering CPU-bound | CPU profiles, render timer |
| GC pauses, heap cao | Attachment buffers, queue trong RAM | Heap/allocations, in-flight count |
| DB CPU cao/locks | Outbox query/index/updates | Query plans, lock metrics |
| HTTP latency cao khi SMTP chậm | Gửi đồng bộ trong request | Endpoint spans, thread dumps |
| Redis latency cao | Distributed rate gate contention | Redis op metrics, key policy |
| Backlog tăng nhưng không có SMTP errors | Rate gate/quota deny, fairness | Permit metrics, due backlog |
| Một tenant chậm bất thường | Head-of-line blocking/fairness | Per-tier backlog age |
| Send attempts trùng | Race claim, replay/UNKNOWN mishandled | Attempt history, claim tokens |
| Provider accepted nhưng user không nhận | Delivery/bounce/spam filtering | Provider trace/delivery events |

**Luôn tìm bottleneck bằng measurement**. Việc thay `SimpleMailMessage` bằng `MimeMessage` hoặc mở thêm threads không mặc định tăng throughput.

## 29. Thiết kế thí nghiệm hiệu năng có thể lặp lại

Một bài load test tốt cần trả lời rõ:

> Với cấu hình X, loại message Y, thời gian quan sát Z và quota Q, hệ thống đạt throughput nào, latency nào, lỗi nào, và bottleneck nằm đâu?

### Quy trình đề xuất

1. **Chốt build/version:** ghi git revision, Java version, Spring Boot/framework version, config và dependency versions.
2. **Dùng môi trường cô lập:** staging hoặc test deployment có CPU/RAM/DB/Redis được cấp rõ.
3. **Dùng SMTP sink/test double:** tránh gửi thư tới khách hàng hoặc provider account production.
4. **Chuẩn bị synthetic payload:** các fixtures text, HTML, PDF/XLSX theo phân bố.
5. **Đặt baseline:** chạy 1 replica, không quota bottleneck giả để đo app-side capacity.
6. **Warm up:** JVM/JIT, connection pools, caches được khởi động trước khi ghi số đo.
7. **Ramp load có kiểm soát:** tăng rate từng bậc, ví dụ 5, 10, 20, 40, 80 jobs/s.
8. **Giữ mỗi bậc đủ dài:** đo steady state, không chỉ vài giây đầu.
9. **Thu SLI đồng bộ:** HTTP, DB, worker, SMTP sink, OS/JVM.
10. **Chạy lặp:** kiểm tra biến động, mô tả phân tán thay vì chỉ một giá trị đẹp.
11. **Bật provider quota giả:** xác minh rate gate và backlog khi demand vượt supply.
12. **Thử crash/restart:** bảo đảm không mất durable intent.
13. **Lưu giả định và kết quả:** biểu đồ, bảng và giải thích giới hạn.

### Không trộn capacity test và provider reputation test

Một SMTP sink có thể chấp nhận 1000 messages/s, trong khi provider thật chỉ cho phép 20/s hoặc throttle theo account reputation. Kết quả sink chỉ xác nhận **khả năng của phần ứng dụng/transport tới sink**. Muốn biết quota provider thật, cần tài liệu/account policy và thử nghiệm có kiểm soát, không dùng bulk spam để “khám phá trần”.

## 30. Chuẩn bị SMTP sink và môi trường benchmark an toàn

Sơ đồ:

~~~text
Synthetic load generator
         |
         v
Spring Boot API / event producer
         |
         v
PostgreSQL outbox / queue
         |
         v
N mail worker replicas
         |
         v
SMTP sink (Mailpit/GreenMail or controlled stub)
         |
         v
Message/recipient counters and MIME inspection
~~~

Các công cụ sink như Mailpit hoặc GreenMail hữu ích vì nhận SMTP mail thử nghiệm mà không chuyển thư tới người dùng thật. Tùy công cụ/phiên bản, có thể cấu hình latency, lỗi hoặc fake relay responses; nếu không hỗ trợ, tự xây test adapter/stub ở mức phù hợp.

### Dữ liệu phải là synthetic

- Recipient: địa chỉ giả thuộc miền dành cho test, ví dụ `user001@example.test`.
- Sender: profile test, không dùng credential production.
- Body: nội dung giả, không có tài khoản, token hoặc thông tin cá nhân.
- Attachment: PDF/CSV/XLSX fixture không có dữ liệu nhạy cảm.
- Object storage: test bucket có retention và quyền riêng.
- Không bật SMTP debug ghi raw message trong shared logs.

### Test sink có giới hạn của chính nó

Sink có thể trở thành bottleneck CPU/disk/storage khi giữ toàn bộ messages. Nếu sink bắt đầu chậm, kết quả không phản ánh giới hạn của ứng dụng. Theo dõi sink metrics và cân nhắc chế độ discard/counters có kiểm soát nếu chỉ đo throughput; vẫn cần một bộ test riêng kiểm tra MIME correctness.

## 31. Bộ kịch bản load test tối thiểu

| ID | Kịch bản | Mục tiêu đánh giá |
|---|---|---|
| LT-01 | Plain text, 1 recipient, 1 replica | Baseline app-side throughput |
| LT-02 | HTML/template, 1 recipient | Chi phí rendering |
| LT-03 | PDF 300 KiB | Chi phí attachment trung bình |
| LT-04 | XLSX 8 MiB | Heap/GC/memory stress |
| LT-05 | 20 recipients/message | Recipient-cost/SMTP envelope semantics |
| LT-06 | 10x burst trong 30 giây | Backlog và backpressure |
| LT-07 | Tải vượt quota giả | Rate gate, defer, không spam provider |
| LT-08 | Scale 1→2→4→8 worker replicas | Horizontal scaling curve |
| LT-09 | 1 tenant cực lớn + 1 tenant OTP | Fairness và latency theo lane |
| LT-10 | SMTP sink chậm gấp 10 | Timeout, concurrency, queue age |
| LT-11 | Lỗi temporary 4xx được mô phỏng | Retry/backoff, không storm |
| LT-12 | Lỗi authentication | Pause route, không retry nóng |
| LT-13 | App restart khi có PENDING | Durability |
| LT-14 | Worker crash sau claim | Lease recovery |
| LT-15 | Outcome unknown sau DATA | Không resend mù |
| LT-16 | Database transient outage | Không mất state và giữ backpressure |
| LT-17 | Redis limiter outage | Fail-closed hoặc bounded fallback |
| LT-18 | Rolling deploy khi còn backlog | Ownership/duplicate risk |
| LT-19 | 1 giờ steady load | Leaks/retention/GC/DB growth |
| LT-20 | Attachments gần size limit | Validation trước SMTP |

Mỗi test nên ghi **điều kiện pass/fail trước khi chạy**. Chẳng hạn LT-07 pass khi accepted submit rate không vượt safe cap trong các cửa sổ đã định nghĩa, jobs bị deny vẫn ở outbox, và retry/no-permit không tăng SMTP attempt count.

### Test open-loop và closed-loop

- **Closed-loop:** mỗi virtual user chờ response rồi gửi request mới. Khi server chậm, generator tự giảm arrival rate, có thể che hiện tượng quá tải.
- **Open-loop:** generator phát arrival rate đã định, kể cả khi response chậm. Phù hợp mô phỏng bursts và overload; phải bảo đảm generator cũng không tự trở thành bottleneck.

Nên mô tả kiểu load generator và **offered load**; không chỉ công bố số requests hoàn thành.

## 32. Mẫu bảng ghi kết quả benchmark

Một báo cáo có thể dùng cấu trúc:

| Run | Replicas | Offered jobs/s | Accepted messages/s | API p95 | Queue p95 | Error/deny | Bottleneck |
|---|---:|---:|---:|---:|---:|---|---|
| B01 | 1 | … | … | … | … | … | … |
| B02 | 2 | … | … | … | … | … | … |
| B03 | 4 | … | … | … | … | … | … |
| B04 | 4 | … + PDF | … | … | … | … | … |
| B05 | 4 | … + quota | … | … | … | … | … |

**Không điền số ước đoán vào bảng như số đo thật.** Nếu chưa chạy benchmark, để ô trống hoặc đánh dấu `NOT_MEASURED`. Trong báo cáo, cần nêu p50/p95/p99, số lượng mẫu, duration và phương pháp đo.

### Một số câu hỏi đọc kết quả

1. Tăng offered load có còn tăng accepted throughput không?
2. p95/p99 latency có tăng nhanh trước khi throughput bão hòa không?
3. Queue age tăng dù CPU thấp có phải do quota?
4. SMTP accepted rate khác rate gate permits do đâu?
5. Có nhiều attempts hơn số intents không?
6. DB pool/lock waits có tăng theo replicas?
7. Tỷ lệ jobs hết hạn có tăng không?
8. Một tenant có chiếm phần lớn capacity không?
9. Tính bền vững sau restart có được xác nhận không?
10. Cùng test chạy lặp có độ lệch lớn không?

## 33. Một ví dụ đo API latency bằng Spring Boot Micrometer

Khi dùng Spring Boot Actuator/Micrometer, có thể thêm timers ở những boundary chính. Đo chính xác **thời gian xử lý nào** thay vì gọi mọi thứ là send latency.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public final class MailMetrics {
    private final MeterRegistry registry;

    public MailMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordSmtpSubmission(
            String providerGroup,
            String outcome,
            long elapsedNanos) {
        Timer.builder("mail.smtp.submission.duration")
                .description("Duration of one SMTP submission attempt")
                .tags(
                        "provider_group", providerGroup,
                        "outcome", outcome)
                .register(registry)
                .record(elapsedNanos, TimeUnit.NANOSECONDS);
    }

    public void recordQuotaDenied(
            String scopeType,
            String reasonCode) {
        registry.counter(
                "mail.rate.denied",
                "scope_type", scopeType,
                "reason", reasonCode).increment();
    }
}
~~~

Đây là utility minh họa. Trong production:

- Dùng `providerGroup`/`outcome`/`reasonCode` từ enum hoặc allowlist, tránh arbitrary labels.
- Đo theo cùng một clock monotonic cho elapsed duration, ví dụ `System.nanoTime()`.
- Không đưa recipient email, subject, job ID hoặc raw exception vào metric tags.
- Cấu hình histogram/percentiles ở backend phù hợp với lưu lượng và cardinality.
- Khi SMTP exception xảy ra, phân loại an toàn, không coi mọi lỗi là temporary.

### Timer quanh SMTP adapter

~~~java
long started = System.nanoTime();
String outcome = "UNKNOWN";
try {
    mailSender.send(message);
    outcome = "ACCEPTED";
} finally {
    metrics.recordSmtpSubmission(
            "PRIMARY",
            outcome,
            System.nanoTime() - started);
}
~~~

Snippet chỉ minh họa chỗ đo elapsed time. Với hệ thống thật, nên phân loại exception thành temporary/permanent/unknown theo SMTP phase và ghi **attempt result** vào state store. Một `finally` đo duration không phải cơ chế quyết định retry.

## 34. Dashboard cần ba loại thông tin: demand, admission và completion

Một dashboard tổng thể:

~~~text
DEMAND
  intents created/s
  outbox PENDING/RETRY jobs
  oldest due job age
  job payload size distribution

ADMISSION
  jobs claimed/s
  rate gate permits/denials
  SMTP in-flight operations
  DB claim latency and contention

SUBMISSION / FEEDBACK
  SMTP accepted/s
  temporary/permanent errors
  unknown outcomes
  retries, expired jobs
  delivered/bounced if provider events exist
~~~

Một outbox có 1 triệu jobs **lên lịch tháng sau** không hẳn là overload hiện tại. Hãy tách:

~~~text
future scheduled:
  scheduled_at > now

due waiting:
  scheduled_at <= now
  available_at <= now
  status in PENDING/RETRY

deferred due to quota/retry:
  scheduled_at <= now
  available_at > now
~~~

Nếu chỉ xem tổng PENDING, dễ báo động sai; nếu chỉ xem due jobs, có thể bỏ sót lượng công việc bị quota delay quá lâu.

## 35. Truy vấn SQL hỗ trợ đánh giá backlog

Một số truy vấn minh họa PostgreSQL.

**Đếm due jobs:**

~~~sql
SELECT COUNT(*) AS due_jobs
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY')
  AND scheduled_at <= CURRENT_TIMESTAMP
  AND available_at <= CURRENT_TIMESTAMP;
~~~

**Đo tuổi job due lâu nhất:**

~~~sql
SELECT EXTRACT(
    EPOCH FROM (
        CURRENT_TIMESTAMP - MIN(scheduled_at)
    )
) AS oldest_due_age_seconds
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY')
  AND scheduled_at <= CURRENT_TIMESTAMP
  AND available_at <= CURRENT_TIMESTAMP;
~~~

Nếu không có row, `MIN` trả null. Không coi null là “0 giây chờ” rồi làm mất phân biệt trạng thái không có backlog.

**Số jobs theo trạng thái:**

~~~sql
SELECT status, COUNT(*) AS jobs
FROM mail_outbox
GROUP BY status
ORDER BY jobs DESC;
~~~

**Số jobs còn chờ quota/retry theo provider account:**

~~~sql
SELECT provider_account_id, COUNT(*) AS deferred_jobs
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY')
  AND scheduled_at <= CURRENT_TIMESTAMP
  AND available_at > CURRENT_TIMESTAMP
GROUP BY provider_account_id;
~~~

Chạy `COUNT(*)` trên bảng rất lớn mỗi vài giây có thể gây tải DB. Trong production, dùng materialized/aggregated counters hoặc truy vấn được tối ưu theo khối lượng, đồng thời đo chính chi phí của việc observability.

## 36. Percentiles quan trọng hơn latency trung bình

Ví dụ:

~~~text
990 SMTP attempts complete in 100 ms
10 attempts hang for 30 seconds
~~~

Giá trị trung bình có thể trông chấp nhận được với một số workloads nhưng 1% tail latency làm nhiều workers bị giữ hàng chục giây. Đánh giá:

- p50: trải nghiệm phổ biến.
- p95/p99: tail khi tải cao.
- Timeout rate: số attempts vượt ngưỡng/không có outcome rõ.
- In-flight saturation: bao nhiêu SMTP slots đang bị chiếm.
- Queue delay p95/p99 theo lane.
- Oldest due job age.

Không so sánh percentile của hai test có **different load mix, duration, labels hoặc warm-up conditions** như thể chúng cùng một quần thể.

### Coordinated omission

Khi load generator chờ server xong mới gửi request tiếp, các thời kỳ server rất chậm có thể bị **ít mẫu** hơn. Một test closed-loop có thể làm latency báo cáo đẹp hơn thực tế của arrival rate cố định. Khi đánh giá burst, dùng open-loop arrival hoặc một phương pháp có tính đến coordinated omission.

## 37. Stress test: hệ thống xuống cấp như thế nào khi vượt giới hạn?

**Load test** thường hỏi hệ thống hoạt động ra sao ở mức tải mục tiêu. **Stress test** cố ý đẩy vượt capacity để xem điểm gãy và hành vi phục hồi.

Một tiến trình:

~~~text
0-5 minutes:     5 jobs/s
5-10 minutes:   10 jobs/s
10-15 minutes:  20 jobs/s
15-20 minutes:  40 jobs/s
20-25 minutes:  80 jobs/s
25-30 minutes:  step down to 10 jobs/s
~~~

Đây là kịch bản minh họa; phải điều chỉnh theo môi trường để tránh gây ảnh hưởng hạ tầng dùng chung.

Quan sát:

- Điểm nào accepted throughput không còn tăng?
- API chuyển từ `202` sang 429/503 khi nào và với logic gì?
- Queue age tăng nhanh ra sao?
- P95/P99 HTTP và SMTP latency thay đổi thế nào?
- Executor queue có bị unbounded không?
- CPU, heap, GC, DB locks và Redis latency ra sao?
- Job count và state transitions có đúng sau khi giảm tải không?
- Có tạo duplicate submissions hoặc mất intents không?

### Hành vi được mong đợi khi quá tải

Một hệ thống “fail predictably” nên:

1. Giữ các intent đã commit.
2. Không vượt hard provider quota.
3. Không làm cạn mọi thread/connection pool.
4. Trả overload signal trung thực khi không thể nhận thêm.
5. Cấp tài nguyên cho lane quan trọng theo policy.
6. Phục hồi sau khi offered load giảm.
7. Không retry nóng một lỗi cấu hình/SMTP provider.

Một OOM hoặc crash loop khi lần đầu vượt 2x tải mục tiêu là dấu hiệu thiếu backpressure/isolation, ngay cả khi bình thường throughput rất cao.

## 38. Soak test: liệu hệ thống ổn định qua nhiều giờ/ngày?

Một test 2 phút không dễ phát hiện:

- Memory leak hoặc giữ `MimeMessage`/`byte[]`.
- Connection/stream không đóng.
- Outbox/index tăng liên tục.
- Retention/cleanup chạy không kịp.
- Cache lớn dần do template keys/tenant IDs.
- Log volume/metric cardinality tăng không giới hạn.
- Lệch clock, recurring schedule hoặc daily quota reset sai.

Một soak test giữ tải hợp lý trong nhiều giờ, quan sát xu hướng:

~~~text
Heap after GC over time
DB table/index bytes growth
Outbox terminal state count
Open connections, file handles
SMTP in-flight count
Worker queue length
GC pause P99
CPU trend at constant throughput
Rate gate latency
~~~

Lý tưởng nhất là những chỉ số sử dụng tài nguyên **ổn định hoặc có chu kỳ dự đoán được** khi offered load và workload mix ổn định. Nhưng đừng đòi đường memory hoàn toàn phẳng: JVM/GC/caches có hành vi dao động tự nhiên.

### Kiểm tra retention với dữ liệu synthetic

Nếu một triệu terminal jobs được tạo qua soak test, xác định các jobs cũ được archive/xóa theo policy hay tích tụ mãi. Không xóa `PENDING/RETRY` chỉ vì created_at cũ, vì có thể là job hẹn tương lai hoặc đang cần retry.

## 39. Failure injection: thử những sự cố thực tế

Một đánh giá năng lực mở rộng không hoàn chỉnh nếu chỉ đo happy path.

| Failure injection | Điều cần quan sát |
|---|---|
| SMTP connect timeout | Bounded duration, retry policy |
| SMTP read/write timeout | Không giữ slots mãi, outcome classification |
| Provider temporary 4xx | Backoff/jitter, no retry storm |
| Provider permanent 5xx | FAILED/suppression theo policy |
| Auth credential invalid | Pause route, alert, không retry nóng |
| TLS negotiation failure | Không downgrade bảo mật vô điều kiện |
| DB connection loss trước outbox commit | Không báo accepted nếu intent chưa lưu |
| DB loss sau SMTP accepted | UNKNOWN/reconciliation, no blind resend |
| Redis rate gate unavailable | Fail closed/bounded approved fallback |
| Worker kill sau claim | Lease recovery |
| Worker kill sau SMTP DATA | Duplicate-risk handling |
| Broker redelivers event | Business intent idempotency |
| Provider callback gửi trùng | Delivery event dedup |
| Provider callback tới sai thứ tự | State không ghi lùi tùy tiện |
| Object storage tạm lỗi | Retry preparation theo phase, không gửi rỗng |
| Clock skew | Due/lease decisions vẫn được bảo vệ |
| Rolling deployment | Không claim trùng/hồi sinh jobs |

### Giữ kiểm thử có kiểm soát

Lỗi được mô phỏng trên SMTP sink/stub, test database và accounts riêng. Không gây outage thật cho provider hoặc gửi dữ liệu tới recipients không đồng ý. Các kịch bản network loss **sau SMTP DATA** cần test double có khả năng mô phỏng đúng phase; mock ném exception ngay trước `send()` không mô tả được ambiguous outcome.

## 40. Recovery test: xác nhận không mất intent và không replay mù

Một test phục hồi quan trọng:

~~~text
Given:
  1000 PENDING jobs committed in DB

When:
  worker process is killed
  and a new worker starts

Then:
  all eligible jobs remain discoverable
  no job disappears from durable store
  no job is submitted twice solely because two workers raced
~~~

Nhưng một yêu cầu khác cần test riêng:

~~~text
Given:
  provider accepted job #583
  worker crashed before DB status commit

When:
  lease expires

Then:
  job is reconciled or handled via explicit UNKNOWN policy
  not automatically treated as certainly unsent
~~~

**Không tuyên bố exactly-once SMTP delivery** chỉ vì basic restart test không thấy bản trùng. Với SMTP không có distributed atomic transaction với DB, luôn tồn tại cửa sổ outcome ambiguous. Mức chấp nhận duplicate cần được ghi trong requirement.

### Kế hoạch replay/DLQ

Nếu retries vượt ngưỡng, job có thể tới `FAILED` hoặc dead-letter workflow:

- Có lý do chuẩn hóa và attempt history.
- Có quyền replay được kiểm soát.
- Nếu lỗi cấu hình chưa sửa, không phát lại hàng loạt.
- Không tự gửi OTP đã hết hạn.
- Không gửi lại email đã được provider accepted chỉ vì chưa thấy delivery event.
- Có audit người/automation đã kích hoạt replay.

Một DLQ đầy nhưng không ai giám sát không tạo reliability thực tế. Cần owner và runbook.

## 41. Kiểm tra multi-tenant fairness và ranh giới bảo mật

Ứng dụng SaaS có nhiều tenants cần đo **isolation**, không chỉ aggregate throughput.

~~~text
Tenant A: burst 50,000 newsletter jobs
Tenant B: 10 password-reset jobs
Tenant C: 200 order receipts
~~~

Các câu hỏi:

1. Tenant B/C có dispatch lag trong SLA không?
2. Tenant A có vượt tenant-specific cap không?
3. Tổng các tenants có vượt provider account quota không?
4. Credential rotation có vô tình reset quota không?
5. Một tenant có thể chọn sender profile của tenant khác không?
6. Một tenant có thể đọc trạng thái/job/payload của tenant khác không?
7. Tenant A có thể tạo metric key cardinality cao vô hạn không?
8. Nếu quota gate lỗi, có fail open làm tất cả tenants flood provider không?

### Tính công bằng theo đơn vị phù hợp

Round robin theo message count không nhất thiết công bằng nếu tenant A gửi 20 recipients mỗi message còn tenant B chỉ gửi 1. Đánh giá share theo **recipient cost** khi provider quota tính recipients; cân nhắc weighted/deficit round robin nếu cost khác nhau.

### Bảo vệ dữ liệu

- Tenant ID lấy từ authenticated context, không tin request body chưa kiểm tra.
- Payload/attachment references có ACL và version.
- Không cho caller chọn arbitrary SMTP host/password/From.
- Không ghi raw recipient, body hay MIME vào logs.
- Audit quyền replay/cancel/reschedule và thay quota.
- Metrics tags theo provider/lane/tier có allowlist; per-tenant detail ở kho được phân quyền nếu cần.

## 42. Cost model: mở rộng phải xét chi phí toàn hệ thống

Tăng throughput bằng nhiều replicas có thể làm chi phí tăng ở các lớp khác:

| Chi phí | Đơn vị quan sát | Khi tăng tải |
|---|---|---|
| App worker CPU/RAM | vCPU-hour/GiB-hour | Render MIME/PDF, giữ concurrency |
| Database | CPU, IOPS, storage, connections | Insert/update/claim, audits |
| Redis | Requests/s, memory, network | Shared quota/locks |
| Message broker | Throughput, storage, retention | Durable event buffering |
| SMTP provider | Messages, recipients, bytes | Billable usage/quota |
| Object storage | GB stored, read requests, egress | Attachments và retries |
| Monitoring | Time series/log GB/traces | High-cardinality/volume |
| Support/operations | Incident handling time | Bounces, replays, investigations |

Một chỉ số kinh tế có thể là:

\[
\text{costPerAcceptedMessage} =
\frac{\text{cost in measurement window}}
{\text{definitively accepted messages}}
\]

Nếu provider tính theo recipient, nên bổ sung `costPerAcceptedRecipient`. Không chia cho tổng intents khi nhiều jobs mới chỉ queued, vì nó che backlog.

### Headroom là một chi phí có chủ đích

Giữ capacity dự phòng cho OTP hoặc provider failover có thể làm average utilization thấp. Điều này không luôn là lãng phí; nó có thể là chi phí để đáp ứng SLO khi burst/outage. Đưa lựa chọn này vào báo cáo cùng rủi ro, thay vì chỉ tối đa hóa messages/s.

## 43. Risk register: các giới hạn cần được chấp nhận hoặc xử lý

Một dự án thực hành không nhất thiết phải giải quyết tất cả giới hạn production. Điều quan trọng là **nói rõ giới hạn nào còn tồn tại**.

| Rủi ro | Tác động | Dấu hiệu | Giảm thiểu / đánh đổi |
|---|---|---|---|
| Gửi đồng bộ trên web thread | Latency/timeout lan sang HTTP | HTTP p99 tăng theo SMTP | Outbox/worker hoặc bounded concurrency |
| Không có SMTP quota gate | Provider throttle, account restriction | 4xx/5xx theo account | Shared rate admission và headroom |
| No durable outbox | Mất email intent khi crash | Restart test thất bại | Transactional outbox/queue |
| No idempotency key | Client retry tạo job trùng | 2 intents cùng business event | Unique business key |
| No state ownership | Multi-worker gửi trùng | Duplicate attempts | Atomic claim/lease/fencing |
| SMTP outcome ambiguous | Retry gây duplicate | Unknown after DATA | UNKNOWN/reconciliation |
| Unbounded task queue | Heap/GC/OOM | Queue length tăng liên tục | Bounded queue/backpressure |
| Large in-memory attachments | Heap pressure | OOM/P99 GC | File-backed/reopenable source, size caps |
| No tenant fairness | OTP chậm bởi bulk | Lane lag cao | Fair scheduling/reserved capacity |
| Missing cleanup | DB/storage tăng mãi | Table/index growth | Retention/archive |
| Credential in code/logs | Security compromise | Secret scanning finding | Secret manager/RBAC/rotation |
| No delivery feedback | Không biết inbox result | SUBMITTED mãi | Provider event integration hoặc nêu giới hạn đo |
| Incomplete observability | Incident khó chẩn đoán | Chỉ có HTTP metric | Job/attempt/provider metrics và runbook |
| Dependency single provider | Outage ảnh hưởng toàn bộ | Zero accepted rate | Backoff, buffered jobs, approved failover |

### Thứ tự ưu tiên

Không xếp tất cả rủi ro “High”. Ưu tiên theo **khả năng xảy ra, mức độ ảnh hưởng, khả năng phát hiện và cost xử lý** trong bối cảnh thực tế:

~~~text
Risk priority = impact + likelihood + detectability concerns
                considered with implementation cost
~~~

Đây không phải công thức điểm số chuẩn; đội dự án có thể dùng một risk matrix được định nghĩa rõ. Một demo không có provider failover có thể chấp nhận được; một hệ thống xử lý OTP production nhưng không có timeouts và audit lại là rủi ro nghiêm trọng.

## 44. Lộ trình cải tiến từ dự án học tập tới môi trường production

Không nhất thiết xây mọi tính năng ngay. Một lộ trình theo rủi ro và bottleneck thực tế:

### Giai đoạn 0: hoàn thiện chức năng và khả năng quan sát

**Mục tiêu:** biết mỗi email đang ở đâu và lỗi thuộc giai đoạn nào.

- Tách code nghiệp vụ khỏi `JavaMailSender` bằng một mail transport adapter.
- Validate sender/recipient, filename, MIME type và attachment size.
- Bật SMTP timeouts và TLS/auth phù hợp provider.
- Đặt correlation/job ID, metrics căn bản.
- Dùng SMTP sink trong kiểm thử.
- Ghi lại scope quota và workload giả định.

**Exit criteria:** có thể giải thích một email gửi thất bại ở bước chuẩn bị, network submission hay downstream delivery mà không phải log raw MIME.

### Giai đoạn 1: bảo vệ transaction và lưu intent bền vững

**Mục tiêu:** không bỏ sót yêu cầu gửi đã commit khi worker restart.

- Tạo mail outbox lưu cùng transaction nghiệp vụ.
- Business idempotency key với unique constraint.
- API trả queued status, không nói delivered.
- Dispatcher đọc due jobs, state machine và attempt history.
- Có retention hợp lý.

**Exit criteria:** restart sau enqueue không làm mất intents; request retry không tạo hai intents cho cùng event.

### Giai đoạn 2: chịu tải và provider limitations

**Mục tiêu:** hoạt động ổn định khi demand vượt supply.

- Bounded SMTP worker pool và backpressure.
- Distributed rate gate theo account/tenant.
- Tách rate, recipient cost, daily quota và concurrency.
- Defer denied jobs trong outbox, không giữ thread ngủ.
- Retry/backoff/jitter và expiry theo loại notification.
- Fair scheduling giữa bulk và transactional.

**Exit criteria:** offered load tăng không gây flood provider, OOM hoặc starvation theo SLA đã định.

### Giai đoạn 3: nâng cao độ tin cậy và vận hành

**Mục tiêu:** xử lý failure modes và backlog chủ động.

- Atomic claim/lease/fencing cho multi-replica.
- State `UNKNOWN` và quy trình reconciliation.
- Failure injection/soak tests.
- Dashboard oldest due age và alerts.
- DLQ/replay có authorization.
- Runbook provider outage/credential rotation.

**Exit criteria:** một sự cố đã được mô phỏng có cách phục hồi được chứng minh và có evidence trong metrics/state store.

### Giai đoạn 4: scale theo sản phẩm và tổ chức

**Mục tiêu:** hỗ trợ nhiều domains/teams/providers.

- Typed notification API/contracts và versioning.
- Tách worker deployment hoặc Notification Service khi thực sự cần.
- Multi-provider routing theo quyền sender và quota.
- Provider feedback/delivery state nếu sản phẩm cần.
- Cost/retention/privacy policies.
- Capacity planning và review theo chu kỳ.

**Exit criteria:** bổ sung tenant/template/provider mới mà không sửa business code và không mở rộng quyền SMTP secret không cần thiết.

## 45. Tình huống đánh giá mẫu: báo cáo cuối kỳ cho một dự án

Giả sử dự án Spring Boot có:

~~~text
Project      : Mail Notification Practice
Flow         : API creates jobs -> DB outbox -> worker -> SMTP
App replicas : 2
Workers/pod  : 4
Provider cap : 40 recipients/s
Daily quota  : 50,000 recipients/day
Message mix  : 90% 1-recipient text/HTML
               10% 1-recipient PDF attachment
Target       : up to 15,000 notifications in 15 minutes
~~~

Tất cả là **giả định minh họa**, không phải môi trường đã được benchmark.

### Bước 1: tính nhu cầu cao điểm

\[
\text{requested rate}
 = \frac{15000}{15\times60}
 \approx 16.67\ \text{jobs/s}
\]

Nếu mỗi job gửi đúng một message đến một recipient, nhu cầu trung bình của cửa sổ campaign là 16,67 recipients/s.

### Bước 2: kiểm tra quota account

Provider safe cap giả định là 40 recipients/s, nên riêng rate/s không tạo giới hạn ở mục tiêu 16,67/s. Nhưng cần xem:

- Daily quota remaining có đủ 15.000 không?
- Các ứng dụng khác dùng cùng account có gửi song song không?
- Có burst cao hơn 40/s do tất cả jobs cùng `scheduled_at`?
- Provider có concurrency/size limits riêng không?

### Bước 3: ước lượng concurrent workers

Giả sử một SMTP call có thời gian **trung bình giả định** 0,3 giây:

\[
L \approx 16.67\times0.3\approx5
\]

Với hai pods × bốn workers = tám slots, số workers lý thuyết có thể đủ theo trung bình. Nhưng nếu p99 SMTP latency tới 10 giây, tail pressure có thể cao. Cần test với latency distribution thực, không chốt cấu hình chỉ bằng phép tính trên.

### Bước 4: xem workload có file PDF

Nếu 10% jobs tạo PDF ~3 MiB, tại thời điểm cao điểm memory overhead có thể tăng. Không được lấy số bytes trung bình của toàn bộ messages để bỏ qua P99 size. Benchmark mixed workload và bounded in-flight attachments.

### Bước 5: đo thực tế

Một bảng ghi chưa điền số:

| Điều cần đo | Giá trị hiện tại |
|---|---|
| HTTP enqueue p95 | NOT_MEASURED |
| SMTP call p95/p99 | NOT_MEASURED |
| Accepted recipients/s | NOT_MEASURED |
| Maximum due backlog | NOT_MEASURED |
| Oldest due age | NOT_MEASURED |
| CPU peak / heap peak / GC p99 | NOT_MEASURED |
| Provider throttle responses | NOT_MEASURED |
| Unknown outcomes | NOT_MEASURED |
| Duplicate business intents | NOT_MEASURED |
| Time to drain after 5-minute outage | NOT_MEASURED |

Không kết luận “đạt 16,67/s” khi chưa có kết quả test. Tính toán cho thấy mục tiêu **có thể hợp lý theo một số giả định**, còn benchmark và integration failure tests mới xác nhận được.

### Bước 6: đưa ra kết luận có điều kiện

Một báo cáo đúng có thể viết:

> “Theo mô hình tải giả định, nhu cầu trung bình 16,67 recipients/s thấp hơn safe provider cap 40 recipients/s. Tuy nhiên chưa đo p95 SMTP latency, attachment memory và concurrency behavior nên chưa thể xác nhận đạt SLO. Ưu tiên chạy mixed-load benchmark và failure test trước khi scale hoặc triển khai production.”

Đây là kết luận có giá trị hơn một con số capacity bịa ra hoặc lời khẳng định “Spring Mail hỗ trợ hàng triệu email”.

## 46. Mẫu báo cáo đánh giá cuối dự án

Người học có thể viết báo cáo cuối kỳ theo cấu trúc:

~~~markdown
# Mail Project Scalability Assessment

## 1. System under test
- Project/build revision:
- App architecture:
- Infrastructure:
- SMTP sink/provider:

## 2. Scope and assumptions
- Workload classes:
- Provider/account limits:
- Tenant and lane policies:
- Exclusions/known unknowns:

## 3. SLO / acceptance criteria
- HTTP enqueue latency:
- SMTP submission latency:
- Oldest due backlog:
- Loss / duplication constraints:
- Security requirements:

## 4. Test design
- Data generation:
- Load pattern:
- Warm-up/duration/repetitions:
- Metrics collection:
- Failure injections:

## 5. Observed results
- Throughput and p50/p95/p99:
- CPU/memory/DB/Redis/SMTP:
- Error and retry counts:
- Backlog and recovery:

## 6. Bottlenecks
- Primary bottleneck:
- Supporting evidence:
- Whether provider quota or app capacity:

## 7. Limitations and risks
- Not measured:
- Remaining design risks:
- Security/privacy/operational limits:

## 8. Recommendations
- Short-term:
- Medium-term:
- Long-term:
- Expected trade-offs/costs:

## 9. Decision
- Supported workload envelope:
- Unsupported scenarios:
- Next review trigger:
~~~

Trong phần **Observed results**, chỉ điền dữ liệu đã có nguồn đo. Với test chưa chạy, ghi rõ `NOT_MEASURED`. Nếu gửi mail thật bị hạn chế bởi account policy, dùng SMTP sink để đo app-side và ghi quota provider từ nguồn chính thức của account như một ràng buộc **chưa được stress test**.

### Kết quả cần đủ để người khác lặp lại

Không chỉ gửi một ảnh biểu đồ. Kèm:

- Tên/phiên bản môi trường.
- Cấu hình traffic generator.
- Query/definition của từng metric.
- Tải được phát và tải được chấp nhận.
- Số lần test, độ dài và warm-up.
- Workload mix và kích thước attachment.
- Các điều kiện thất bại/giới hạn đã quan sát.
- Những giới hạn dữ liệu chưa đo hoặc không kiểm chứng.

## 47. Bảng tiêu chí tự đánh giá dự án thực hành

Có thể dùng bảng dưới để chấm **mức sẵn sàng** của một dự án gửi email. Điểm số chỉ là khung học tập, không phải chứng nhận production readiness.

| Nhóm | Câu hỏi đánh giá | Minh chứng mong đợi |
|---|---|---|
| Chức năng | Gửi đúng To/Subject/body và MIME/attachment? | MIME unit test, SMTP sink |
| Ranh giới | Business code có phụ thuộc trực tiếp SMTP? | Module/dependency graph |
| Synchronous impact | Provider chậm có giữ HTTP thread/transaction? | Endpoint span và failure test |
| Durability | Request đã commit có được xử lý sau restart? | Outbox persistence test |
| Idempotency | Event/request retry có tạo trùng intent? | Unique constraint + retry test |
| Worker ownership | Nhiều workers có cùng claim một job? | Concurrency test |
| Retry | Temporary/permanent/unknown được phân biệt? | Classification tests |
| Provider quota | Đếm đúng messages/recipients/window? | Quota policy và test |
| Concurrency | In-flight SMTP operations có giới hạn? | Runtime metrics/load test |
| Backpressure | Overload có làm RAM/queue tăng vô hạn? | Stress test |
| Fairness | Bulk có làm chậm OTP/transactional? | Multi-tenant mixed test |
| Attachment | File lớn có gây heap pressure? | P95/P99 size và GC metrics |
| Observability | Phát hiện được backlog/attempt/unknown? | Dashboards/alerts |
| Recovery | Worker/DB/provider outage có runbook? | Failure injection |
| Security | Secrets/recipient/payload có được bảo vệ? | RBAC/logging review |
| Cost | Có biết cost theo message/recipient? | Cost model |
| Evidence | Có số đo và giới hạn quan sát? | Benchmark report có điều kiện |

### Cách tự cho điểm đơn giản

Với mỗi nhóm, chọn:

- **0 — Chưa có:** không có triển khai hoặc evidence.
- **1 — Có một phần:** hoạt động ở happy path, thiếu thử lỗi/measurement.
- **2 — Có minh chứng:** có kiểm thử hoặc số đo phù hợp với workload được công bố.

Không cộng điểm rồi tuyên bố “production-grade” nếu còn một rủi ro nghiêm trọng như SMTP credentials bị lộ hoặc không kiểm soát được gửi trùng trong nghiệp vụ nhạy cảm. Một **blocking issue** có thể quan trọng hơn tổng điểm cao.

### Đề bài thực hành

Hãy tạo một bản đánh giá cho dự án của mình với ba mức tải:

~~~text
Level 1: Normal load
  1 recipient/message, no attachment

Level 2: Peak traffic
  10x baseline for 5 minutes, mixed HTML/PDF

Level 3: Degraded provider
  SMTP latency increases and 20% temporary rejections
~~~

Với mỗi mức, ghi offered jobs/s, accepted messages/s, queue delay p95, oldest due age, CPU/heap, attempt outcomes và backlog drain. Sau đó giải thích: giới hạn là provider quota, worker capacity, database, template renderer hay nơi khác?

Tỷ lệ 20% là **giả định của test double**, không phải tỷ lệ lỗi thực tế của bất kỳ provider nào. Không cần gây lỗi thật trên tài khoản SMTP production.

## 48. Các ngộ nhận khi nói về khả năng mở rộng

### “Thêm 10 pods thì gửi nhanh gấp 10”

Không nếu tất cả dùng chung một quota account hoặc database/SMTP connection limit. Đo accepted throughput sau scale, không chỉ tổng CPU potential.

### “Spring Mail gửi được bao nhiêu email một giây?”

Không có một con số phổ quát. Nó phụ thuộc provider, network, MIME size, connection behavior, CPU/DB, worker pool, quota và workload mix. Cần đo **dự án cụ thể**.

### “Gửi async là đủ không mất mail”

`@Async` không tự bền vững qua restart. Một durable outbox/broker và transaction boundary đúng mới xử lý được intent persistence.

### “Có SKIP LOCKED thì bảo đảm exactly-once”

`SKIP LOCKED` giúp workers không claim cùng row tại thời điểm tranh chấp DB, không tạo atomic transaction với SMTP. Crash sau accepted vẫn có duplicate risk.

### “MailSender.send không lỗi nghĩa là người nhận đã đọc thư”

Không. SMTP accepted khác inbox delivery, và delivered khác opened/read. Chỉ ghi trạng thái đúng evidence mình có.

### “Đặt pool size 100 là được 100 mail/giây”

Pool size là concurrency; tốc độ còn phụ thuộc thời gian mỗi call, quota và overhead.

### “Số HTTP 202/s chính là throughput gửi mail”

HTTP 202 thường nghĩa là intent đã được chấp nhận để xử lý. Cần đo riêng SMTP accepted/recipient rate và queue lag.

### “Vượt quota thì cứ retry liên tục”

Retry storm tạo thêm tải và có thể bị provider hạn chế mạnh hơn. Dùng backoff/jitter, rate gate, max attempts và deadline.

### “Redis rate limiter local trên mỗi pod là distributed”

Không. Mỗi pod có budget riêng thì tổng có thể vượt quota. Cần shared atomic admission theo account/tenant scope thực tế.

### “Một message bằng một recipient”

Không khi To/Cc/Bcc có nhiều envelope recipients. Tính cost theo đơn vị provider áp.

### “Attachment 10 MiB dùng đúng 10 MiB heap”

Không chắc. Có thể có generator buffers, copies, MIME/Base64 overhead và nhiều in-flight messages. Đo memory theo workload thực.

### “Không có SMTP errors nghĩa là hệ thống khỏe”

Có thể worker không gửi gì vì quota gate deny hoặc queue bị kẹt. Xem demand, admission, backlog age và accepted throughput cùng nhau.

### “Chỉ cần theo dõi trung bình latency”

Tail latency p95/p99, timeouts và oldest due age có thể tiết lộ vấn đề mà average che giấu.

### “Cứ lưu toàn bộ raw MIME để debug”

Không phù hợp mặc định vì PII, attachments và credentials có thể bị lộ. Dùng job/attempt IDs, reason codes, synthetic fixtures và retention có kiểm soát.

### “Càng nhiều index database càng nhanh”

Index tăng chi phí write/space. Chọn theo query plans, rate updates và retention.

### “Có DLQ thì không mất email”

Một DLQ không có owner, monitoring, replay policy hoặc expiration semantics không giải quyết được tác động của lỗi.

### “Dùng một provider phụ là có HA hoàn chỉnh”

Failover cần verified sender/domain, quota riêng, template/payload consistency và không chuyển khi outcome tuyến cũ UNKNOWN. Hai providers có thể dùng chung dependency hoặc cùng bị ảnh hưởng reputation.

### “Benchmark SMTP sink chứng minh deliverability production”

Sink chỉ chứng minh pipeline tới một đích thử nghiệm. Deliverability tới mailbox thật chịu spam filtering, reputation, DNS records và chính sách người nhận; không được suy luận từ sink acceptance.

## 49. Câu hỏi thường gặp

**Dự án Spring Framework Mail cần bao nhiêu worker?** Không có con số cố định. Ước lượng từ target accepted rate và SMTP latency, rồi benchmark dưới provider quota và tail latency thật. Chỉ claim lượng jobs phù hợp capacity.

**Nên đo số mail/giây hay recipient/giây?** Cả hai nếu provider có giới hạn tương ứng. Một message nhiều recipients có cost khác một message một recipient.

**Dùng `SimpleMailMessage` có nhanh hơn `MimeMessage` không?** Plain-text message có thể giảm chi phí MIME content/attachments, nhưng accepted throughput vẫn chịu SMTP/provider/network. Quyết định theo yêu cầu nội dung và đo từng workload; đừng tự chọn một con số “nhanh hơn bao nhiêu”.

**Có cần Kafka ngay khi vượt 1000 emails/ngày?** Không. Số emails/ngày không tự quyết định broker. Xem burst, durability, owner, database capacity và nhu cầu nhiều consumers. DB outbox có thể đủ ở nhiều quy mô.

**Khi nào dùng transactional outbox?** Khi business update và notification intent cần cùng commit, và mất một yêu cầu gửi khi process chết là không chấp nhận được.

**Dùng `@TransactionalEventListener(AFTER_COMMIT)` có đủ bền vững không?** Không mặc định; có thể crash sau commit trước khi listener ghi durable intent. Phù hợp best-effort hoặc có reconciliation riêng.

**Khi HTTP trả 202, mail có thể chưa gửi không?** Đúng. API nên cung cấp notification/job ID và status query; không gọi queued là delivered.

**Nếu provider throttle thì tăng pods có tốt không?** Thường không khi đã chạm provider cap. Nên giảm burst, dùng account-wide limiter, lên lịch hợp lý hoặc tăng quota hợp lệ.

**Có nên tạo nhiều SMTP credentials để tăng quota?** Không mặc định. Nhiều credentials có thể chia một provider account/organization budget; không dùng credential rotation để né quota.

**Làm sao ngăn tenant lớn chiếm tài nguyên?** Account + tenant budgets, fair scheduling theo lane/cost, bounded worker queues và reserved capacity phù hợp.

**Có thể dùng one-shot InputStream cho attachment không?** Không nên khi MIME serialization có thể đọc lại. Dùng byte[] cho file nhỏ hoặc nguồn mở stream mới từ immutable payload.

**Đếm backlog bằng tổng số PENDING có chính xác không?** Chưa đủ. Tách future scheduled, due now và quota/retry deferred, đồng thời đo oldest due age.

**Tại sao cần p99?** Một số ít SMTP calls treo dài có thể chiếm nhiều worker slots và làm queue trễ dù average thấp.

**Cách xác định DB là bottleneck?** Xem query plans, lock waits, connection pool, insert/claim/update latency, CPU/IO và xu hướng theo offered load. Không kết luận chỉ từ số rows.

**Có nên lưu raw MIME trong database?** Chỉ khi có nhu cầu rõ và đáp ứng bảo mật/retention; thường nên lưu intent/payload references và submission metadata, tránh PII không cần thiết.

**Có thể bảo đảm exactly-once email delivery?** Không thể cam kết tuyệt đối qua SMTP thuần trong mọi trường hợp network/DB failure. Có thể bảo đảm chống tạo trùng business intent và giảm duplicate bằng reconciliation/idempotency theo provider capability.

**Nếu SMTP timeout thì có chắc mail chưa gửi?** Không. Nếu mất kết nối sau DATA, provider có thể đã accepted. Cần phân loại phase và giữ outcome UNKNOWN khi không chắc.

**Nên retry bao nhiêu lần?** Phụ thuộc loại email, error class, deadline và provider policies. Không retry vĩnh viễn hoặc gửi OTP sau khi đã hết hạn.

**Đo delivery time bằng `submitted_at` được không?** Không. `submitted_at` là submission accepted; delivery event, nếu provider cung cấp, mới hỗ trợ `delivered_at`.

**Tại sao load test qua SMTP sink khác production?** Sink không có reputation/spam filters/quota như provider thật và có performance khác. Tách kết quả app-side capacity khỏi provider-limited capacity.

**Một kết quả benchmark duy nhất có đủ không?** Không lý tưởng. Nên có warm-up, duration, nhiều lần chạy, workload mix, p95/p99, confidence/variability và điều kiện môi trường được ghi lại.

**Có cần chạy 24 giờ load test không?** Tùy rủi ro, đặc biệt khi có daily quota, retention, memory leaks hoặc recurring schedules. Một soak test dài giúp phát hiện vấn đề mà benchmark ngắn không thấy.

**Có nên fail open khi Redis rate limiter down?** Không mặc định. Với durable outbox, fail closed giữ intent và giảm nguy cơ flood provider; fallback cần ngân sách toàn cụm được phê duyệt.

**Scale riêng SMTP worker có lợi không?** Có khi web request và SMTP workload có failure/CPU profiles khác nhau, nhưng chỉ tăng accepted throughput nếu còn headroom ở provider/DB và rate gate.

**Làm sao biết cần thay provider?** Đo quota, acceptance ratio, delivered/bounce events, latency, outage behavior, cost và đáp ứng SLA. Đừng quyết định chỉ từ số thread hoặc một lỗi 4xx.

**Nếu hệ thống vượt giới hạn nhưng không mất job, đã đạt chưa?** Chưa chắc. Nếu OTP bị trễ tới hết hạn, backlog không drain được hoặc tenant fairness sai, hệ thống có thể vẫn không đáp ứng SLO.

**Báo cáo đánh giá thiếu số liệu nên viết gì?** Ghi `NOT_MEASURED`, trình bày giả định/mô hình tính, nêu phép đo cần làm và không kết luận mức capacity đã đạt.

## 50. Tổng kết: chỉ công bố khả năng mở rộng khi có bằng chứng

Đánh giá khả năng mở rộng của một **dự án Spring Framework Mail** không dừng ở việc đếm số lần gọi `JavaMailSender.send(...)` trong một giây. Cần xem toàn bộ vòng đời:

~~~text
Business demand / scheduled arrivals
                  |
                  v
    API / notification intent
                  |
                  v
         Durable outbox
                  |
                  v
      Claim / dispatch / queue
                  |
                  v
      Eligibility + fair policy
                  |
                  v
      Account/tenant rate gates
                  |
                  v
         SMTP concurrency
                  |
                  v
   MIME rendering + JavaMailSender
                  |
                  v
       Provider SMTP accepted
                  |
                  v
   Delivery feedback if available
~~~

Ở mỗi bước, xác định **đơn vị đo, giới hạn, trạng thái khi lỗi và nguồn dữ liệu**:

| Câu hỏi cuối cùng | Cách trả lời có căn cứ |
|---|---|
| Dự án xử lý được bao nhiêu công việc? | Offered load, accepted throughput và SLO theo workload |
| Giới hạn chính ở đâu? | Compare component metrics, quota, saturation, query plans |
| Tăng replicas có cải thiện? | So throughput/p95/p99/cost ở 1, 2, 4 replicas |
| Burst có làm mất job? | Durable outbox + stress/restart tests |
| Có gửi trùng? | Idempotency, ownership và ambiguous outcome tests |
| Quota provider có bị vượt? | Account/tenant admission và đúng cost units |
| Bulk có chặn email quan trọng? | Fairness/lane tests và oldest due age |
| Attachment lớn có an toàn? | Heap/GC, size caps, streaming/retention |
| Provider outage có phục hồi? | Failure injection và backlog drain measurement |
| Có thể hỗ trợ vận hành? | Trạng thái, audit, metrics, alerts và runbook |
| Giới hạn nào chưa biết? | Danh sách `NOT_MEASURED` và phương án xác minh |

Ba nguyên tắc quan trọng nhất:

1. **Khả năng mở rộng phải được định nghĩa trong một workload envelope.** Một app chạy tốt với email text một recipient chưa chắc chịu được file lớn, multi-recipient hoặc bulk tenant burst.
2. **Bottleneck thật quyết định capacity.** Nếu quota provider là 20 recipients/s, tăng CPU và replicas không tạo thêm quota. Nếu bottleneck ở template rendering, thêm providers cũng không sửa được CPU-bound code.
3. **Hiệu năng không được đánh đổi độ tin cậy và an toàn.** Một hệ thống có throughput cao nhưng làm mất committed intents, retry mù khi SMTP outcome UNKNOWN, làm OTP hết hạn hoặc lộ dữ liệu cá nhân chưa được xem là đáp ứng yêu cầu.

### Sản phẩm nộp cho bài thực hành

Người học nên kết thúc bằng **một báo cáo có thể kiểm chứng**, không chỉ một đoạn nhận xét:

- Sơ đồ kiến trúc thực tế và các boundaries.
- Bảng giả định tải, provider quota và môi trường.
- SLO cùng định nghĩa SLI rõ ràng.
- Kịch bản benchmark/load/stress/failure.
- Bảng số đo thực và biểu đồ nếu có.
- Phân tích bottleneck và dự báo backlog/capacity có điều kiện.
- Risk register, giới hạn chưa được kiểm chứng.
- Lộ trình cải tiến ưu tiên theo tác động/chi phí.

Nếu dự án chỉ là demo chưa có outbox, multi-worker hoặc delivery feedback, hãy nói rõ đó là **giới hạn hiện tại**, trình bày hướng cải tiến và phương pháp đo trước khi quyết định mở rộng. Sự minh bạch này có giá trị kiến trúc hơn việc tự gán nhãn “sẵn sàng production”.

**Kết luận:** Một dự án Spring Mail mở rộng tốt không chỉ gửi được nhiều email hơn; nó biết **khi nào được phép gửi**, **giữ được công việc khi phải chờ**, **khôi phục được sau sự cố**, **bảo vệ quota và từng tenant**, và **có bằng chứng cho mọi cam kết về thông lượng, độ trễ và độ tin cậy**.
