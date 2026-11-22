# Đánh giá yêu cầu giao nhận, bảo mật và kiểm toán

Một ứng dụng **Spring Framework Mail** có thể gửi được email chỉ với vài dòng `JavaMailSender.send(...)`. Tuy nhiên, **gửi được** chưa đồng nghĩa một kiến trúc email đã đáp ứng nhu cầu sản phẩm, vận hành, bảo mật và kiểm toán. Với email quảng bá, một vài phút chậm có thể chấp nhận được; với biên nhận thanh toán, mất thông báo hoặc gửi trùng có thể gây khiếu nại; với liên kết đặt lại mật khẩu, nội dung và thời hạn phải được bảo vệ; với dữ liệu nhạy cảm, cần chứng minh ai đã yêu cầu gửi, thông tin nào được phép đi ra ngoài và đã có bằng chứng gì về kết quả giao nhận.

Vì vậy, khi quyết định dùng **Spring Mail + SMTP**, **SMTP relay nội bộ**, **email provider API**, **transactional outbox** hay một nền tảng email chuyên biệt, nhóm phát triển phải làm rõ ba nhóm yêu cầu:

1. **Giao nhận:** email được tạo, xếp hàng, gửi tới relay, giao đến mail server đích và xử lý lỗi với mức tin cậy nào?
2. **Bảo mật:** những ai được yêu cầu gửi, nội dung và thông tin xác thực được bảo vệ ra sao, hệ thống có chống giả mạo và lạm dụng không?
3. **Kiểm toán:** sau nhiều ngày hoặc nhiều tháng, tổ chức có thể chứng minh sự kiện gì thực sự đã xảy ra, dựa vào bằng chứng nào và ai được phép xem chúng?

Ba nhóm này gắn chặt với nhau. Một outbox giúp tránh mất yêu cầu, nhưng không mã hóa nội dung. STARTTLS bảo vệ đường truyền, nhưng không chứng minh email đã được giao vào Inbox. Lưu toàn bộ nội dung mail để điều tra có thể giúp truy nguyên, nhưng làm tăng rủi ro rò rỉ dữ liệu và vi phạm chính sách lưu giữ.

Bài học trình bày một **khung đánh giá kiến trúc có thể áp dụng thực tế**, từ cách viết yêu cầu có thể đo được, xác định ranh giới trách nhiệm, lập ma trận quyết định, thiết kế Spring Boot service, đến thử nghiệm giả lập sự cố và tiêu chí nghiệm thu.

> **Nguyên tắc xuyên suốt:** Chỉ tuyên bố mức bảo đảm mà hệ thống có thể quan sát và chứng minh. Đặc biệt, `JavaMailSender.send(...)` thành công thường phản ánh **SMTP submission**, không bảo đảm email xuất hiện trong Inbox hoặc được người nhận đọc.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Thu thập và phân loại yêu cầu giao nhận theo loại email và mức ảnh hưởng nghiệp vụ.
- Phân biệt `REQUESTED`, `QUEUED`, `SMTP_ACCEPTED`, `DELIVERED`, `BOUNCED`, `COMPLAINED` và `UNKNOWN`.
- Xác định mục tiêu SLO/SLI cho độ trễ, tỷ lệ lỗi, tồn đọng và thời gian phát hiện sự cố.
- Hiểu vì sao generic SMTP không cung cấp exactly-once submission khi kết quả mạng không rõ.
- Chọn synchronous send, queue, transactional outbox hoặc provider API dựa trên rủi ro.
- Đánh giá khả năng giao nhận: SPF, DKIM, DMARC, verified From, bounce và suppression.
- Đánh giá bảo mật kết nối TLS, authentication, secrets, quyền gửi, multi-tenant isolation và dữ liệu nhạy cảm.
- Thiết kế audit trail từ business event đến message, attempt, provider event và quyết định manual retry.
- Thiết lập retention, redaction, access control và quy tắc xử lý yêu cầu xóa dữ liệu.
- Viết bảng quyết định có tiêu chí, trọng số, bằng chứng và người phê duyệt.
- Dùng Spring Boot, `JavaMailSender`, outbox, callbacks và tests để biến yêu cầu thành kiến trúc có thể kiểm chứng.
- Nêu giới hạn còn lại sau khi triển khai, không đưa ra cam kết vượt khả năng công nghệ.

## 2. Tại sao quyết định kiến trúc email không bắt đầu bằng thư viện?

Hai hệ thống đều dùng `JavaMailSender` nhưng có thể yêu cầu hoàn toàn khác:

| Hệ thống | Ví dụ email | Hậu quả khi mất | Hậu quả khi trùng | Hậu quả khi lộ nội dung |
|---|---|---|---|---|
| Ứng dụng nội bộ | Báo cáo xây dựng hằng ngày | Thấp hoặc trung bình | Thấp | Tùy dữ liệu |
| Thương mại điện tử | Xác nhận thanh toán | Cao | Trung bình/cao | Có thể lộ thông tin đơn hàng |
| Đăng nhập | Link đặt lại mật khẩu | Cao trong thời hạn ngắn | Dễ gây nhầm, có rủi ro tài khoản | Rất cao nếu lộ token |
| Dịch vụ khách hàng | Phản hồi phiếu hỗ trợ | Trung bình/cao | Tạo nhiều cuộc hội thoại | Có thể chứa dữ liệu cá nhân |
| Marketing | Email chiến dịch | Có thể chấp nhận trì hoãn | Cao về spam complaint | Phụ thuộc danh sách khách hàng |
| Tài chính/pháp lý | Thông báo quan trọng | Cao | Có thể gây tranh chấp | Có thể rất cao |

Không thể trả lời “nên dùng SMTP hay API?” chỉ bằng số dòng code hoặc tốc độ lập trình.

Trình tự phù hợp:

```text
Business outcomes
      |
      v
Risk / data classification
      |
      v
Delivery / security / audit requirements
      |
      v
Candidate architectures
      |
      v
Threat & failure analysis
      |
      v
Proof-of-concept / tests / measurements
      |
      v
Architecture decision record (ADR)
      |
      v
Implementation & operational controls
```

## 3. Xác định ranh giới của một giao dịch email

Một yêu cầu gửi email có thể đi qua nhiều hệ thống:

```text
Business service
     |
     | 1. Request created
     v
Application database / outbox
     |
     | 2. Request durably queued
     v
Dispatcher / mail worker
     |
     | 3. Submission attempted
     v
Spring JavaMailSender / Jakarta Mail
     |
     | 4. SMTP DATA accepted by relay
     v
SMTP provider / relay queue
     |
     | 5. Provider attempts delivery
     v
Recipient mail server
     |
     | 6. Receiving server accepts / rejects
     v
Mailbox / quarantine / spam filters
     |
     | 7. Human may or may not see message
     v
Recipient
```

Có nhiều ranh giới trách nhiệm:
- **Application:** nội dung, người nhận, quyền gửi, lịch, retry và dữ liệu outbox.
- **SMTP relay/provider:** acceptance, retry tới máy chủ nhận, queue, bounce và event nếu dịch vụ hỗ trợ.
- **Recipient mail server:** chính sách nhận, spam, quarantine, mailbox delivery.
- **Email client/người dùng:** hiển thị, lọc, đọc, mở link.

Không được gộp tất cả vào một cột `sent = true` rồi cho rằng đã hoàn thành nghĩa vụ giao nhận.

### 3.1. Phân biệt message logic và submission attempt

- **Email logic:** một thông báo nghiệp vụ, ví dụ “biên nhận cho đơn 123”.
- **Submission attempt:** một lần worker kết nối provider và gửi email.
- **Delivery event:** phản hồi của provider về trạng thái giao tới máy chủ nhận.
- **User interaction:** mở email, nhấp link hoặc tương tác khác.

Một email logic có thể có nhiều attempts do lỗi trước acceptance. Ngược lại, một attempt có thể liên quan nhiều recipients nếu gửi một MIME chung; điều này làm tracking phức tạp hơn.

### 3.2. Cần có source of truth rõ ràng

Một nguồn dữ liệu có thể là nguồn sự thật cho **yêu cầu gửi**, nhưng không nhất thiết là nguồn sự thật cho **delivery**.

Ví dụ:
- Outbox DB: “đã tạo một email logic và đã thực hiện attempt”.
- SMTP reply/provider event: “relay đã chấp nhận”.
- Delivery callback: “provider quan sát thấy mail server đích đã nhận/từ chối”.
- Không nguồn nào mặc định chứng minh người dùng thực sự đã đọc.

## 4. Đặt tên trạng thái theo điều có thể chứng minh

Một mô hình thực dụng:

| Trạng thái | Định nghĩa có thể dùng | Bằng chứng tối thiểu |
|---|---|---|
| `REQUESTED` | Người dùng/hệ thống đã yêu cầu gửi | Business command/event |
| `QUEUED` | Yêu cầu được lưu bền vững | DB transaction commit hoặc durable broker receipt |
| `SENDING` | Worker đã claim và bắt đầu attempt | Attempt record/lease |
| `SMTP_ACCEPTED` | Relay báo chấp nhận submission | Phản hồi SMTP cuối phù hợp hoặc provider confirmation |
| `UNKNOWN` | Không đủ bằng chứng xác định accepted hay không | Exception/timeout + lịch sử attempt |
| `RETRY_WAIT` | Lỗi được chứng minh chưa accepted, có thể retry | Classified outcome + retry policy |
| `DELIVERED` | Provider báo giao theo contract của họ | Webhook/API event được xác thực |
| `DEFERRED` | Giao tới máy chủ đích bị trì hoãn | Provider delivery event |
| `BOUNCED` | Giao thất bại theo provider semantics | Bounce/DSN/provider event |
| `CANCELLED` | Yêu cầu bị hủy trước submission phù hợp | Conditional state transition |
| `EXPIRED` | Quá thời hạn còn được phép gửi | Business deadline |

Không cần bắt mọi dự án dùng đúng tên trên; cần **định nghĩa bằng văn bản** và không trộn trạng thái submission với delivery.

### 4.1. Accepted khác Delivered

SMTP relay chấp nhận một email có thể chỉ là bước đầu. Provider còn phải thử gửi tới mail server đích. Bên nhận có thể tạm hoãn, từ chối, quarantine hoặc xử lý theo chính sách riêng.

Nếu SLO nói “99,9% email giao trong 5 phút”, cần định nghĩa “giao” theo bằng chứng provider nào, có bao gồm các domain từ chối nhận không, và cách xử lý missing callbacks.

### 4.2. Delivered khác Inbox

Một provider callback `delivered` thường có nghĩa server nhận thư đã chấp nhận ở một giai đoạn nhất định, không chứng minh thư được đặt trong Inbox thay vì Spam hoặc người nhận đã mở.

### 4.3. Open tracking không phải bằng chứng đọc đáng tin cậy

Ảnh tracking có thể bị chặn, tải trước hoặc cache bởi mail clients. Vì vậy không dùng “email opened” như bằng chứng duy nhất rằng thông báo pháp lý đã được đọc hay một giao dịch đã được xác nhận.

## 5. Thu thập yêu cầu theo loại email

Không nên cho mọi email dùng cùng một SLA, quyền truy cập hoặc thời hạn lưu dữ liệu.

Một bảng phân loại ban đầu:

| Loại mail | Priority | Độ trễ chấp nhận | Lặp được không? | Nội dung nhạy cảm | Chính sách lưu |
|---|---|---|---|---|---|
| Xác thực/OTP | Cao | Thấp, phải còn hạn | Hạn chế nghiêm ngặt | Token và danh tính | Giữ metadata tối thiểu |
| Hóa đơn/biên nhận | Cao | Theo quy trình pháp lý/nghiệp vụ | Tránh gây hiểu nhầm | Đơn hàng, tiền, PII | Theo chính sách hồ sơ |
| Thông báo ứng dụng | Trung bình | Vài phút tùy loại | Có thể, nhưng cần dedupe | Phụ thuộc payload | Hạn chế theo nhu cầu |
| Báo cáo vận hành | Trung bình | Theo lịch | Tùy SLA | Nội dung doanh nghiệp | Phân quyền và retention |
| Marketing | Thường thấp hơn transactional | Theo chiến dịch | Tránh gửi lặp | Consent, danh sách | Theo mục đích/luật áp dụng |

Các giá trị là **ví dụ về cách phân loại**, không phải SLA mặc định mọi công ty phải áp dụng.

### 5.1. Những câu hỏi phải hỏi business owner

1. Điều gì xảy ra nếu một email không được gửi?
2. Điều gì xảy ra nếu người nhận nhận hai bản?
3. Khi nào email trở nên vô dụng hoặc nguy hiểm nếu gửi muộn?
4. Người nhận có kênh khác để lấy nội dung không?
5. Có yêu cầu pháp lý/nghĩa vụ chứng minh đã gửi hoặc đã thông báo không?
6. Nội dung có chứa PII, thông tin tài chính, bí mật thương mại hoặc token không?
7. Email là transactional, marketing hay một loại khác theo chính sách áp dụng?
8. Có cần đa ngôn ngữ, nhiều timezone, attachments hay branding riêng theo tenant?
9. Ai được quyết định gửi lại một email có kết quả chưa rõ?
10. Trong sự cố provider, tiếp tục chờ, failover hay tạm dừng?

## 6. Viết yêu cầu theo cách kiểm thử được

Một yêu cầu kiểu “email phải nhanh, an toàn và có audit đầy đủ” không thể nghiệm thu vì các từ khóa chưa có định nghĩa.

Chuyển thành:

| Mã | Nhóm | Yêu cầu ví dụ | Bằng chứng nghiệm thu |
|---|---|---|---|
| D-01 | Giao nhận | Yêu cầu mail đã commit không mất khi worker restart | Crash/restart test cùng durable DB |
| D-02 | Giao nhận | Trong điều kiện provider khỏe, 99% transactional jobs được submit trong X phút | SLI từ outbox committed → SMTP accepted |
| D-03 | Giao nhận | Attempt UNKNOWN không được auto-resubmit | Fault injection mất final SMTP reply |
| D-04 | Giao nhận | Job hết hạn không được submit | Clock-controlled deadline test |
| S-01 | Bảo mật | SMTP bắt buộc TLS với hostname verification | Test cert mismatch bị từ chối |
| S-02 | Bảo mật | Secrets không nằm trong code/config public | Secret inventory + access review |
| S-03 | Bảo mật | Tenant A không chọn sender/recipient dữ liệu tenant B | Authorization/integration test |
| A-01 | Kiểm toán | Truy được business event → mail job → attempt → provider event | Trace query từ correlation ID |
| A-02 | Kiểm toán | Chỉ nhóm được phép xem dữ liệu nhạy cảm | RBAC test + audit access |
| A-03 | Kiểm toán | Retention/redaction theo phân loại dữ liệu | Retention test và storage policy |

**X phút, tỷ lệ phần trăm và thời hạn lưu** phải do nghiệp vụ/đơn vị vận hành phê duyệt; không lấy các con số ví dụ làm cam kết sản phẩm.

### 6.1. Functional và non-functional requirements

- **Functional:** gửi MIME HTML, attachment, cc/bcc, reply-to, delayed send, multi-provider, unsubscribe.
- **Non-functional:** uptime, throughput, latency, security, audit, recovery time, compliance, isolation, chi phí.

Một quyết định “dùng `JavaMailSender` là đủ” chỉ có ý nghĩa sau khi hai nhóm yêu cầu đã được kiểm tra.

### 6.2. Severity và điều kiện chấp nhận

Mỗi yêu cầu nên có:
- Owner.
- Mức độ `MUST`, `SHOULD`, `COULD`.
- Phạm vi email/tenant.
- Mô tả kiểm thử hoặc metric.
- Hạn chế/ngoại lệ.
- Tiêu chí chấp nhận rủi ro nếu chưa đáp ứng.

## 7. SLI, SLO, SLA và error budget

Ba khái niệm dễ bị nhầm:

- **SLI:** chỉ số quan sát, ví dụ thời gian từ outbox commit đến SMTP accepted.
- **SLO:** mục tiêu nội bộ, ví dụ tỷ lệ submissions được accepted trong một ngưỡng.
- **SLA:** cam kết thương mại/hợp đồng với hệ quả cụ thể nếu không đạt.

Không tuyên bố “99,99% delivered” khi provider không cung cấp callback đầy đủ hoặc thiếu định nghĩa mẫu số.

### 7.1. Các chỉ số gợi ý

```text
queue_latency =
    first_attempt_started_at - outbox_committed_at

submission_latency =
    smtp_accepted_at - outbox_committed_at

provider_delivery_latency =
    provider_delivered_at - smtp_accepted_at

retry_delay =
    next_attempt_started_at - first_failed_at
```

Các giá trị chỉ tính khi timestamp và trạng thái có ý nghĩa; `UNKNOWN` không được coi là thành công hoặc thất bại chắc chắn chỉ để làm đẹp tỷ lệ.

### 7.2. Denominator phải rõ

Ví dụ SLI “tỷ lệ email transactional accepted trong 2 phút” cần quyết định:
- chỉ tính job đủ điều kiện và còn hạn;
- có loại trừ receiver hard bounce không;
- có tính outage ngoài kiểm soát không;
- xử lý mail cancelled thế nào;
- có tính customer-induced invalid address không.

Mẫu số không rõ có thể khiến cùng hệ thống được báo cáo là 95% hoặc 99,9% theo cách tính khác nhau.

### 7.3. Lỗi nằm ở giai đoạn nào?

Dashboard cần tách:
- queue backlog;
- SMTP connection/auth failures;
- acceptance outcomes;
- delivery deferral/bounces;
- bounce processing lag;
- webhook processing failures.

Một số liệu “email failure rate” duy nhất che khuất nguyên nhân và mức kiểm soát.

## 8. Chọn kiến trúc đồng bộ hay bất đồng bộ

Ba hướng thường gặp:

```text
A. Synchronous
HTTP request -> JavaMailSender -> SMTP -> HTTP response

B. Async memory queue
HTTP request -> QueueChannel -> worker -> SMTP

C. Durable outbox
HTTP request -> DB transaction + outbox -> dispatcher -> SMTP
```

| Tiêu chí | Gửi đồng bộ | Queue trong bộ nhớ | Transactional outbox |
|---|---|---|---|
| Dễ làm demo | Rất dễ | Dễ | Phức tạp hơn |
| Caller chờ SMTP | Có | Không nhất thiết | Không |
| Chịu burst | Hạn chế | Có bộ đệm | Có thể mở rộng worker |
| Sống qua restart | Không có work item bền vững mặc định | Không, nếu chỉ memory | Có khi DB được quản lý đúng |
| Gắn với business transaction | Dễ dual-write lỗi | Vẫn có thể mất enqueue | Cùng DB transaction giúp không mất yêu cầu |
| Retry và audit | Phải xây thêm | Phải xây thêm | Có trạng thái/attempt rõ |
| Chi phí vận hành | Thấp ban đầu | Trung bình | Cao hơn nhưng kiểm soát tốt |
| SMTP exactly-once | Không | Không | **Vẫn không** |

### 8.1. Khi nào gửi đồng bộ hợp lý?

Có thể hợp lý khi:
- một công cụ quản trị thử email;
- số lượng thấp;
- business action không cần atomicity với email;
- caller chấp nhận độ trễ và lỗi SMTP;
- không có yêu cầu durability/async/retry cao.

Không nên để request “đặt đơn hàng” chờ SMTP relay nếu email chỉ là thông báo thứ cấp và provider có thể outage.

### 8.2. Khi nào dùng durable outbox?

Đáng cân nhắc khi:
- email gắn với business event đã commit;
- không được mất yêu cầu khi restart;
- cần retry có kiểm soát;
- cần theo dõi từng attempt;
- có nhiều pods/workers;
- yêu cầu audit và incident reconstruction;
- có scheduled messages.

Outbox không thay thế SMTP provider, và cũng không bảo đảm delivery vào Inbox.

### 8.3. Persistent queue hoặc broker là lựa chọn khác

RabbitMQ, Kafka, JMS hoặc persistent Spring Integration MessageStore có thể là một phần của giải pháp. Cần xét:
- transaction giữa business DB và enqueue;
- visibility/ack semantics;
- redelivery;
- dead-letter handling;
- ordering;
- duplicate side effects;
- retention và encryption.

Nếu business DB và broker không có giao dịch atomic chung, **transactional outbox → publisher → broker** có thể là mẫu phù hợp.

## 9. SMTP qua Spring Mail hay HTTP Email API?

Hai phương án đều có thể gửi email, nhưng khác khả năng quan sát và tích hợp.

| Tiêu chí | `JavaMailSender` + SMTP | Provider HTTP API/SDK |
|---|---|---|
| Chuẩn kết nối | SMTP, rộng rãi | API theo vendor |
| MIME và headers | Ứng dụng tự xây/kiểm soát | Phụ thuộc API |
| Acceptance | SMTP reply, không phải delivery | HTTP status/request receipt theo contract |
| Submission idempotency | Không có chuẩn chung | Có thể có nếu vendor hỗ trợ thật |
| Query trạng thái | Thường cần provider portal/log API riêng | Có thể dễ hơn, không bảo đảm |
| Webhooks/delivery events | Có thể dùng song song provider | Thường có nếu vendor cung cấp |
| Port/network policy | SMTP 587/465/relay | HTTPS 443 phổ biến |
| Portability | Cao ở transport level | Vendor lock-in rõ hơn |
| Quota/rate management | Tùy relay và adapter | Có thể có API headers/quota |
| Audit | Phải dựng lớp tương quan | Có thể tận dụng vendor IDs |
| Credential | SMTP credential/OAuth2 | API key/OAuth2 |
| Chi phí | Theo provider/hạ tầng | Theo vendor contract |

### 9.1. Không chọn API chỉ vì trả HTTP 202

`202 Accepted` có thể chỉ nghĩa request được API xếp hàng. Nó **không đồng nghĩa delivered**. Phải đọc contract của provider: idempotency, trạng thái, webhook và retention.

### 9.2. Không chọn SMTP chỉ vì “không lock-in”

MIME và SMTP là chuẩn mở, nhưng:
- rate limits, provider event APIs và authentication khác nhau;
- suppression, template, bounce handling có thể vendor-specific;
- chuyển provider cần verified sender, DNS và quy trình warm-up.

Lớp port/adapter giúp giới hạn phụ thuộc vendor, nhưng không thể xóa mọi khác biệt vận hành.

### 9.3. Một abstraction không nên che giấu capability

Ví dụ:

```java
public interface OutboundMailPort {
    SubmissionAttemptResult submit(MailSubmission command);
}

public record MailProviderCapabilities(
    boolean supportsIdempotentRequests,
    boolean supportsSubmissionLookup,
    boolean supportsDeliveryWebhooks,
    boolean supportsRecipientLevelEvents
) {}
```

Các model này do ứng dụng định nghĩa. Khi provider SMTP không hỗ trợ query/idempotency, adapter phải báo đúng giới hạn thay vì trả một trạng thái “delivered” giả định.

## 10. Tự vận hành SMTP relay hay dùng dịch vụ quản lý?

Quyết định này cần phân tích tổng chi phí sở hữu, không chỉ phí gửi mỗi nghìn email.

**Tự vận hành relay** có thể cung cấp:
- quyền kiểm soát routing;
- log/queue nội bộ;
- tích hợp hạ tầng riêng;
- khả năng tùy biến chính sách sâu.

Nhưng đồng thời cần chịu trách nhiệm:
- uy tín IP/domain;
- chống spam/lạm dụng;
- hardening và patching MTA;
- IP warm-up, feedback loops;
- bounce processing;
- DNS, rDNS, TLS;
- giám sát queue;
- 24/7 incident handling;
- giữ bí mật và dữ liệu.

**Dịch vụ quản lý** có thể giảm gánh vận hành và cung cấp webhooks, suppression, reputation tooling; bù lại thêm chi phí vendor, hợp đồng, data residency và rủi ro phụ thuộc.

### 10.1. Khi nào cần relay nội bộ?

Ví dụ:
- mạng có yêu cầu egress tập trung;
- tổ chức có MTA team chuyên trách;
- cần kiểm soát route và data flow;
- legacy systems đã dùng relay.

Đừng đưa một SMTP relay không được quản trị vào production chỉ để tránh chi phí provider.

### 10.2. Vendor due diligence

Hãy yêu cầu bằng chứng:
- khả năng delivery tracking và event retention;
- data processing location và subprocessors;
- SLA/support/incident communication;
- bảo mật API keys/SMTP credentials;
- DKIM/domain verification;
- suppression và complaint handling;
- audit access và export;
- portability/export/delete;
- quota và chính sách rate limit;
- sự cố outage và recovery history.

Thông tin vendor cần được xác minh từ tài liệu/hợp đồng hiện hành, không phỏng đoán dựa trên tên thương hiệu.

## 11. Đánh giá khả năng giao nhận: SPF, DKIM, DMARC

**Deliverability** không chỉ là “SMTP kết nối được”. Một provider có thể accepted message nhưng người nhận vẫn từ chối hoặc đưa vào Spam nếu domain authentication/reputation kém.

### 11.1. SPF

SPF giúp domain công bố máy chủ được phép gửi cho **SMTP envelope identity** thích hợp. Một SPF pass **không tự bảo đảm** DMARC pass nếu domain không aligned với Header From.

### 11.2. DKIM

DKIM ký các phần của email bằng private key; người nhận tra public key trong DNS để kiểm tra signature. Cần biết provider nào ký, dùng `d=` domain gì, rotation và canonicalization ra sao.

### 11.3. DMARC

DMARC dựa vào Header From và yêu cầu **SPF pass + alignment** **hoặc** **DKIM pass + alignment** (theo chế độ liên quan). DMARC policy có thể là monitor/quarantine/reject và tạo reporting.

### 11.4. Vì sao kiến trúc phải xem domain identity?

Ví dụ:

```text
Header From: billing@example.com
Envelope MAIL FROM: bounce.vendor.net
DKIM d=vendor.net
```

Ngay cả khi SPF/DKIM pass theo vendor domain, DMARC alignment với `example.com` có thể chưa đúng. Cần cấu hình provider để dùng domain/identity phù hợp, hoặc DKIM aligned theo contract.

### 11.5. Checklist deliverability

- [ ] Domain/sender identity được verified.
- [ ] SPF không có nhiều policy TXT xung đột; lookup được kiểm soát.
- [ ] DKIM ký đúng domain/selector, có rotation plan.
- [ ] DMARC alignment được xác minh bằng email nhận thực tế.
- [ ] Bounce/complaint/unsubscribe được xử lý.
- [ ] Tách transactional và marketing khi cần.
- [ ] Quản lý volume, warm-up và reputation.
- [ ] Theo dõi deferral, spam complaint, hard/soft bounce.

Không tuyên bố “đã có SPF/DKIM/DMARC thì chắc chắn vào Inbox”. Các filters còn xét hành vi, nội dung, reputation và chính sách bên nhận.

## 12. Bounce, complaint và suppression là yêu cầu hệ thống

Một hệ thống chỉ có `JavaMailSender.send` mà không xử lý feedback có thể tiếp tục gửi tới:
- địa chỉ không tồn tại;
- người đã unsubscribe;
- người đã báo spam;
- địa chỉ có hard bounce lặp lại;
- mailbox bị provider chặn.

Điều đó ảnh hưởng uy tín domain và có thể vi phạm chính sách liên lạc.

### 12.1. Phân biệt bounce types theo provider

- **Hard bounce:** thường là lỗi lâu dài, cần kiểm tra/suppress theo policy.
- **Soft bounce/deferred:** có thể tạm thời, provider có thể tự retry.
- **Complaint:** tín hiệu người nhận báo spam, thường đòi hỏi suppression nghiêm ngặt.
- **Unsubscribe:** yêu cầu không nhận loại email được áp dụng.

Không dùng cùng một retry rule cho mọi event.

### 12.2. Suppression phải có precedence cao hơn routing

Nếu recipient bị suppress, việc chuyển từ provider A sang B không làm họ có quyền được gửi trở lại. Suppression/consent là business/security policy **trên tất cả providers**.

### 12.3. Webhook không đồng nghĩa dữ liệu đáng tin chưa kiểm tra

Provider callbacks cần:
- xác minh chữ ký/HMAC theo vendor contract;
- kiểm tra replay/idempotency;
- map provider/account/tenant;
- xử lý out-of-order events;
- có dead-letter và retry;
- không để event không xác thực tự thay đổi trạng thái hệ thống.

## 13. Phân tích thất bại: mất thư, gửi trùng và UNKNOWN

Trong SMTP, một attempt có thể:
1. Thất bại rõ trước khi message được submit.
2. Nhận `250` cuối sau `DATA`: SMTP relay accepted.
3. Timeout khi chờ final reply sau DATA: **kết quả không rõ**.

```text
Application                  SMTP relay
    |                            |
    |------ DATA content ------->|
    |------ end-of-DATA -------->|
    |                            | queues mail
    |<--- final 250 lost --------X
    |                            |
    v                            v
 client timeout             server accepted
```

Nếu retry vô điều kiện, relay có thể nhận **hai submissions**. Nếu không bao giờ retry, một message thực sự chưa accepted có thể bị bỏ qua.

### 13.1. Ba nhãn kết quả an toàn

- `SMTP_ACCEPTED`: có bằng chứng server đã chấp nhận.
- `PROVEN_NOT_ACCEPTED`: có bằng chứng chưa được chấp nhận; sau đó mới xét retryable/permanent.
- `UNKNOWN`: không có bằng chứng đủ mạnh để kết luận.

`MailSendException` hoặc `SocketTimeoutException` không tự là bằng chứng `PROVEN_NOT_ACCEPTED` vì chúng không nhất thiết nói rõ phase giao thức.

### 13.2. RFC Message-ID không tạo exactly-once

RFC `Message-ID` là header định danh email, có ích cho tương quan/threading nhưng **generic SMTP relay không cam kết dedupe theo Message-ID**. Một ứng dụng submit hai lần cùng Message-ID vẫn có thể tạo hai bản.

### 13.3. Quyết định retry cần phân loại nghiệp vụ

Với email marketing, duplicate có thể xấu hơn bỏ một lần. Với cảnh báo sự cố khẩn cấp, bỏ sót có thể nguy hiểm hơn lặp. Khung chính sách phải nêu rõ mức rủi ro được chấp nhận; không để một `@Retryable` chung tự ra quyết định cho mọi loại email.

## 14. Kiến trúc bền vững: business transaction + outbox

Mẫu phổ biến khi email phát sinh từ một business event:

```text
BEGIN DB TX
  update order/payment/customer state
  insert email_outbox(
      message_key, business_event_key,
      payload_ref, status=PENDING
  )
COMMIT
         |
         v
Dispatcher claims due rows
         |
         v
Attempt record committed
         |
         v
SMTP / Email API submission
         |
         v
Persist outcome
```

Yêu cầu:
- Business state và outbox request nằm trong **cùng DB transaction** khi thích hợp.
- Không gửi SMTP trong transaction kéo dài.
- Dispatcher đọc job đã commit.
- Mỗi job có unique business key/idempotency key.
- Mỗi attempt có attempt ID riêng.
- Sau accepted, dừng application submission retry.
- Sau UNKNOWN, chờ reconciliation/chính sách.

### 14.1. Outbox giải quyết gì?

- Không mất yêu cầu do worker restart sau business commit.
- Có thể tách request latency khỏi SMTP provider.
- Có nơi lưu trạng thái/retry/backlog.
- Cho phép audit và correlation.
- Có thể tái khởi động dispatcher.

### 14.2. Outbox không giải quyết gì?

- Không làm SMTP atomic với database.
- Không tự bảo đảm email vào Inbox.
- Không tự bảo vệ nội dung lưu trong DB.
- Không tự ký DKIM đúng.
- Không tự kiểm tra consent/suppression.
- Không tự khiến provider giữ webhook mãi mãi.

## 15. Thiết kế outbox và attempt history cho audit

Ví dụ PostgreSQL:

```sql
CREATE TABLE email_outbox (
    message_key UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    business_event_key VARCHAR(160) NOT NULL,
    mail_type VARCHAR(48) NOT NULL,
    template_id VARCHAR(120) NOT NULL,
    template_version VARCHAR(80) NOT NULL,
    payload_reference VARCHAR(512),
    sender_profile VARCHAR(100) NOT NULL,
    recipient_reference VARCHAR(256) NOT NULL,
    status VARCHAR(40) NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_email_business_event
        UNIQUE (tenant_id, business_event_key)
);

CREATE TABLE email_submit_attempt (
    attempt_id UUID PRIMARY KEY,
    message_key UUID NOT NULL
        REFERENCES email_outbox(message_key),
    attempt_number INTEGER NOT NULL,
    provider_profile VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(48) NOT NULL,
    error_category VARCHAR(120),
    provider_reference VARCHAR(255),
    observed_smtp_phase VARCHAR(64),
    CONSTRAINT uq_submit_attempt_number
        UNIQUE (message_key, attempt_number)
);

CREATE INDEX idx_email_outbox_due
    ON email_outbox(next_attempt_at, send_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX idx_email_attempt_by_message
    ON email_submit_attempt(message_key, started_at);
```

Đây là schema tham khảo, chưa bao gồm tất cả CHECK constraints, audit immutable events, encryption, soft/hard deletion hoặc partitioning.

### 15.1. Unique business key phải được scope

Một key ví dụ:

```text
tenant-42 | order-paid | order-1001 | receipt-v1
```

Không chỉ dùng `order-1001` toàn cục nếu các tenant có thể dùng trùng ID. Key phải thể hiện đúng “một thông báo logic” theo nghiệp vụ.

### 15.2. Không lưu payload plaintext vô thời hạn

`payload_reference` có thể trỏ tới object storage được mã hóa hoặc template snapshot có retention. Cần tách:
- dữ liệu bắt buộc giữ phục vụ audit;
- nội dung cần thiết để retry trong cửa sổ ngắn;
- dữ liệu phải xóa sau mục đích xử lý;
- những thứ không bao giờ được log (OTP, mật khẩu, raw credentials).

## 16. Claim job an toàn trong nhiều worker

Nếu ba pods cùng poll một bảng outbox, không thể chỉ:
1. `SELECT ... status=PENDING`.
2. Gửi email.
3. `UPDATE status=SENT`.

Hai workers có thể lấy cùng row.

Một hướng PostgreSQL:

```sql
WITH due AS (
    SELECT message_key
    FROM email_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND send_at <= :now
      AND next_attempt_at <= :now
      AND (expires_at IS NULL OR expires_at > :now)
    ORDER BY next_attempt_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE email_outbox e
SET status = 'SENDING',
    attempt_count = e.attempt_count + 1,
    lease_token = :leaseToken,
    lease_expires_at = :leaseExpiresAt,
    updated_at = :now
FROM due
WHERE e.message_key = due.message_key
RETURNING
    e.message_key,
    e.attempt_count,
    e.lease_token;
```

Thực hiện trong transaction ngắn, ghi attempt record rồi commit trước khi gọi SMTP.

### 16.1. Lease không đủ để kết luận “chưa gửi”

Nếu worker bị kill sau relay accepted nhưng trước database update, row có thể vẫn `SENDING` và lease hết hạn. **Không tự đổi mọi stale SENDING thành PENDING** để retry; chuyển qua recovery classifier và `UNKNOWN` nếu chưa có proof.

### 16.2. Fencing bảo vệ database, không thu hồi SMTP

Khi ghi accepted:

```sql
UPDATE email_outbox
SET status = 'SMTP_ACCEPTED',
    lease_token = NULL,
    lease_expires_at = NULL,
    updated_at = :now
WHERE message_key = :messageKey
  AND status = 'SENDING'
  AND lease_token = :leaseToken;
```

Row count bằng 0 nghĩa worker không còn sở hữu state tương ứng. Nó không chứng minh SMTP relay đã hoặc chưa accepted.

### 16.3. Transactional guarantees phải công khai

Thiết kế này có thể:
- bảo đảm durable queued job sau commit;
- giảm concurrent duplicate claims;
- lưu attempt history khi DB khả dụng.

Nó **không** bảo đảm generic SMTP exactly-once qua mọi failure.

## 17. Reconciliation và câu hỏi “có thể chứng minh đã gửi chưa?”

Khi kết quả `UNKNOWN`, một tổ chức có thể đối chiếu với:
- Provider submission/queue logs.
- Provider message lookup API.
- Webhook được xác thực.
- SMTP relay logs do mình vận hành.
- Provider-specific queue ID hoặc correlation reference.
- Delivery event map được về đúng attempt.

**Không phải mọi provider đều hỗ trợ tra cứu đủ mạnh**, và “không thấy record” có thể do indexing trễ hoặc retention ngắn.

### 17.1. Quy trình đối soát

```text
UNKNOWN attempt
       |
       v
Gather attempt ID, provider, time window
       |
       v
Lookup provider evidence
       |
       +--> Confirmed accepted
       |          |
       |          v
       |     SMTP_ACCEPTED
       |
       +--> Confirmed non-accepted
       |          |
       |          v
       |     Retry / permanent policy
       |
       +--> No reliable conclusion
                  |
                  v
           UNRESOLVED / review
```

### 17.2. Manual resend phải có audit

Nếu cuối cùng phải resend dù không chứng minh được non-acceptance:
- ghi người phê duyệt;
- business rationale;
- loại email;
- expected duplicate impact;
- link tới attempt trước;
- tình trạng consent và expiry;
- nhà cung cấp/route mới nếu có.

Đừng gọi đó là “retry an toàn”. Đó là **quyết định chấp nhận rủi ro gửi trùng**.

## 18. Thiết kế bảo mật theo mô hình đe dọa

Đánh giá security không chỉ hỏi “có TLS không?”. Hãy xem các assets và trust boundaries:

```text
Authenticated user / internal service
             |
             v
Mail request API
    [authn, authz, tenant isolation]
             |
             v
Template renderer + business data
    [data minimization, encoding]
             |
             v
Outbox / object storage
    [encryption, access, retention]
             |
             v
Mail worker / secret store
    [least privilege, TLS, egress policy]
             |
             v
SMTP / email provider
    [vendor controls, verified domain]
             |
             v
Recipient mail ecosystem
    [untrusted destination, no full control]
```

Những đe dọa thường gặp:

| Đe dọa | Ví dụ | Biện pháp |
|---|---|---|
| Gửi mail trái phép | Endpoint thành open relay | Authn/Authz, recipient rules, quotas |
| Lộ secret | SMTP password trong repository/log | Secret manager, rotation, redaction |
| Giả mạo người gửi | Header From tùy ý | Verified sender registry, SPF/DKIM/DMARC |
| Trộn tenant | Tenant A dùng template/data B | Context server-side, row-level permissions |
| Rò nội dung | Log full MIME/attachment | Data minimization, encryption, access controls |
| Email injection | Untrusted header value chứa CRLF | Validate recipients/headers, API an toàn |
| Template XSS/phishing | Không escape untrusted fields | Context-aware escaping, approved templates |
| SSRF qua attachment/URL | Worker tải URL do caller cung cấp | Egress allowlist, fetch policy |
| Replay webhook | Kẻ khác gửi lại delivery event | Signature, timestamp, event dedupe |
| Denial of service | Bulk send gây quá tải | Rate/concurrency quotas, backpressure |
| Mất audit | Operator sửa/xóa lịch sử | Append-only controls, restricted write, export |
| Bypass suppression | Failover sang provider khác | Central suppression/consent |

Mỗi rủi ro cần có owner, control, test và rủi ro còn lại; không chỉ “chọn thư viện được nhiều người dùng”.

## 19. Bảo vệ SMTP transport và xác thực

Một cấu hình Spring Boot cho SMTP STARTTLS submission có thể là:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
```

Đây là cấu hình minh họa; endpoint/port/credential phải theo provider được phê duyệt.

### 19.1. STARTTLS và implicit TLS

- SMTP submission port **587** thường bắt đầu SMTP rồi yêu cầu `STARTTLS`.
- Port **465** thường bắt đầu TLS ngay (implicit TLS); với `protocol=smtp` có thể dùng `mail.smtp.ssl.enable=true`.
- Port **25** thường liên quan relay/server-to-server; không mặc định là cổng submission của ứng dụng.

Đúng hostname nhưng sai port/TLS mode có thể gây lỗi handshake hoặc timeout. Không sửa bằng cách tắt TLS.

### 19.2. Hostname verification

`mail.smtp.ssl.checkserveridentity=true` giúp kiểm tra hostname khớp chứng chỉ. Không dùng `mail.smtp.ssl.trust=*` trong production để lờ đi CA/hostname problems.

### 19.3. Credential

Tùy provider có thể cần:
- SMTP AUTH username/password;
- app password;
- OAuth2;
- certificate/client policy đặc thù;
- IP allowlisting.

Không mặc định username trong `spring.mail.username` phải là Header From; nếu khác, provider phải cấp quyền verified sender tương ứng.

### 19.4. Egress và network controls

Giới hạn outbound traffic tới các SMTP/provider endpoints được quản trị cho phép. Không cho caller tùy ý chỉ định SMTP hostname/port để biến service thành SSRF/tunneling mechanism.

## 20. Quản lý secret và vòng đời credential

Checklist credential:
- Không hardcode password/token vào source.
- Không đưa secrets vào commit, stack trace hoặc metrics labels.
- Lấy từ secret manager/config được bảo vệ.
- Giới hạn quyền đọc secret theo workload.
- Rotate theo lịch và sau incident.
- Có cơ chế rollover sender profile mà không làm lẫn credentials.
- Tách môi trường development/staging/production.
- Dùng test credential chỉ truy cập SMTP sandbox.
- Cân nhắc audit mọi lần truy cập/đổi secret.
- Không bật protocol debug vô hạn trong production.

### 20.1. Quyền theo workload

Một billing worker chỉ cần secret dùng gửi mail cho verified billing sender; không nên có toàn quyền provider API để xóa audit logs, thay domain settings hoặc đọc toàn bộ campaign recipients nếu không cần.

### 20.2. Rotation phải giữ tương thích

Nếu thay token/SMTP account:
1. Chuẩn bị credential mới.
2. Kiểm tra quyền sender/hostname/TLS.
3. Drain những attempts đang dùng profile cũ nếu cần.
4. Chuyển sender route theo version.
5. Theo dõi AUTH errors.
6. Vô hiệu secret cũ theo plan.

Không mutate một `JavaMailSenderImpl` singleton giữa lúc nhiều threads cùng gửi.

## 21. Authorization: ai có quyền gửi gì, cho ai?

Một SMTP credential hoạt động giống “quyền gửi” trong phạm vi provider. Nếu application API cho phép bất kỳ authenticated user nào gọi:
```text
POST /mail/send
to=<any-address>
from=<any-domain>
body=<any-content>
```
thì ứng dụng có nguy cơ trở thành công cụ spam, phishing hoặc rò rỉ dữ liệu.

### 21.1. Xác thực và phân quyền trên business action

Thay vì expose SMTP primitives cho clients, cung cấp các use cases:

```text
POST /orders/{id}/send-receipt
POST /accounts/request-password-reset
POST /support/tickets/{id}/reply
```

Backend quyết định:
- template nào được dùng;
- sender profile nào;
- recipient có thuộc business object không;
- tenant scope;
- dữ liệu nào được đưa vào template;
- rate limit/consent.

### 21.2. Không lấy tenant từ header email

Header `From`, `Reply-To` hoặc một custom header do bên ngoài gửi tới không phải authentication source. Tenant phải lấy từ authenticated server-side context và quyền truy cập dữ liệu.

### 21.3. Recipient validation không chỉ là cú pháp

Ngoài kiểm tra địa chỉ:
- recipient có được phép nhận dữ liệu này không?
- địa chỉ có được xác minh khi nghiệp vụ yêu cầu không?
- người nhận có opt-out/suppression không?
- có nguy cơ gửi PII tới địa chỉ được nhập nhầm không?
- cc/bcc có làm lộ thông tin giữa khách hàng không?

Dùng một thông báo riêng cho từng recipient khi cần isolation và tracking chi tiết.

## 22. Nội dung email và data minimization

Email thường đi qua nhiều hệ thống bên ngoài và có thể được forward, lưu lâu, chụp màn hình hoặc tải xuống. Vì thế không nên xem email như một kênh lưu trữ bí mật được kiểm soát hoàn toàn.

### 22.1. Không đưa quá nhiều dữ liệu vào body

Ví dụ với thông báo hóa đơn:
- gửi mã tham chiếu và mô tả tối thiểu;
- cung cấp link HTTPS tới trang tài khoản được xác thực nếu cần xem dữ liệu chi tiết;
- không gửi toàn bộ hồ sơ tài chính hoặc thông tin nhạy cảm nếu không có business approval.

### 22.2. Link xác thực và token

Đối với reset password:
- token phải có entropy phù hợp, TTL ngắn và một lần sử dụng khi thiết kế yêu cầu;
- không log nguyên URL chứa token;
- không tạo token quá sớm rồi gửi sau khi hết hạn;
- tránh để scanner/pre-fetch kích hoạt hành động nhạy cảm chỉ bằng HTTP GET;
- business action cuối cần kiểm tra xác thực/authorization phù hợp.

### 22.3. Template escaping

HTML content không tin cậy có thể mang dữ liệu do user nhập. Dùng template engine với escaping theo ngữ cảnh; không nối chuỗi HTML từ input thô rồi gọi `helper.setText(html, true)` nếu dữ liệu chưa được xử lý.

### 22.4. Hình ảnh và tracking

Remote images có thể tiết lộ IP, thời điểm mở và client behavior. Đánh giá privacy policy, consent và độ tin cậy của tracking trước khi đưa vào email.

## 23. Attachment, file storage và phân loại dữ liệu

Khi gửi attachment:
- xác định dữ liệu có cần đính kèm hay chỉ nên cấp link có xác thực;
- giới hạn kích thước và loại file;
- kiểm tra quyền đọc file theo tenant và business object;
- quét malware khi nguồn file không tin cậy;
- không dùng tên file do user cung cấp làm filesystem path;
- không lưu attachment bytes vào logs;
- quản lý thời gian sống object storage;
- tránh gửi file đã bị thu hồi quyền truy cập.

### 23.1. Attachment làm tăng rủi ro và chi phí

Một email có file 20 MB có thể khiến:
- MIME/Base64 size tăng đáng kể;
- queue/backlog chiếm tài nguyên;
- SMTP provider từ chối vì size limit;
- recipient server từ chối;
- logs và backups tăng nếu lưu raw content.

Yêu cầu “gửi file bất kỳ” phải được chuyển thành giới hạn và policy cụ thể.

### 23.2. Cân nhắc signed download link

Với tài liệu cần kiểm soát truy cập, một link có thời hạn ngắn đến trang/tệp được xác thực có thể an toàn hơn gửi attachment trực tiếp. Nhưng URL cũng có nguy cơ bị forward, scanner truy cập hoặc token rò qua logs. Cần thiết kế authorization thực tế, không chỉ ký URL là đủ.

## 24. Audit: cần chứng minh điều gì?

**Audit trail** khác **debug log**. Audit trả lời:

- Ai hoặc hệ thống nào yêu cầu gửi?
- Business event nào tạo ra email logic?
- Dữ liệu/template/version nào được phê duyệt?
- Recipient và sender identity nào đã được quyết định?
- Ai có quyền thay đổi recipient, lịch gửi hoặc template?
- Attempt nào được thực hiện, qua provider nào?
- Có bằng chứng accepted/rejected/unknown hay không?
- Provider báo delivery/bounce/complaint gì?
- Ai đã bấm retry/resend, với lý do nào?
- Dữ liệu audit đã được giữ, xóa, redacted như thế nào?

Một dòng `logger.info("Email sent")` thiếu correlation và outcome definition không đáp ứng được các câu hỏi đó.

### 24.1. Audit khác observability

| Thuộc tính | Audit | Application logging/metrics |
|---|---|---|
| Mục đích | Chứng minh một quyết định/sự kiện | Debug và vận hành |
| Đơn vị | Business event, actor, command, attempt | Request, exception, latency |
| Tính bất biến | Thường cần append-only/tamper-evidence | Có thể rotate/aggregate |
| Thời hạn | Theo rủi ro/chính sách/luật áp dụng | Theo nhu cầu vận hành |
| Dữ liệu cá nhân | Tối thiểu cần thiết | Redact/aggregate |
| Quyền truy cập | Hạn chế, có audit access | SRE/developer theo vai trò |
| Correlation | Business key, attempt ID, event ID | Trace/span IDs và labels |

### 24.2. Không dùng raw mail làm audit mặc định

Lưu toàn bộ email content và attachment trong audit vĩnh viễn làm tăng rủi ro riêng tư và phạm vi breach. Nhiều câu hỏi chỉ cần:
- template ID/version;
- hash/snapshot reference theo policy;
- message/attempt IDs;
- sender/recipient reference;
- timestamps;
- verified provider response;
- actor/reason.

Nếu nội dung đầy đủ thật sự bắt buộc cho một quy trình, phải có căn cứ, phân quyền, mã hóa và retention riêng.

## 25. Mô hình sự kiện kiểm toán append-only

Có thể thêm bảng audit events độc lập với outbox state hiện tại:

```sql
CREATE TABLE email_audit_event (
    audit_id UUID PRIMARY KEY,
    message_key UUID NOT NULL,
    attempt_id UUID,
    tenant_id VARCHAR(80) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    actor_type VARCHAR(32) NOT NULL,
    actor_reference VARCHAR(160),
    event_time TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    provider_reference VARCHAR(255),
    evidence_reference VARCHAR(512),
    reason_code VARCHAR(120),
    correlation_id VARCHAR(160),
    previous_event_hash VARCHAR(128),
    event_hash VARCHAR(128)
);

CREATE INDEX idx_email_audit_message
    ON email_audit_event(message_key, event_time);

CREATE INDEX idx_email_audit_attempt
    ON email_audit_event(attempt_id, event_time);
```

Sự kiện ví dụ:
- `MAIL_REQUESTED`.
- `OUTBOX_COMMITTED`.
- `MAIL_CLAIMED`.
- `SUBMISSION_STARTED`.
- `SMTP_ACCEPTED`.
- `SUBMISSION_OUTCOME_UNKNOWN`.
- `PROVIDER_DELIVERED`.
- `PROVIDER_BOUNCED`.
- `MANUAL_RESEND_APPROVED`.
- `MAIL_CANCELLED`.
- `AUDIT_ACCESS_GRANTED` hoặc sự kiện truy cập ở hệ thống audit control riêng.

### 25.1. Audit event không thay business transaction

Để không có trạng thái business commit nhưng audit bị thiếu, cân nhắc insert audit event trong cùng local transaction với outbox/business state. Đối với provider event từ bên ngoài, lưu raw signed metadata/normalized event theo pipeline được kiểm soát.

### 25.2. Hash chain không tự làm database bất biến

Các cột `previous_event_hash` và `event_hash` chỉ có ý nghĩa nếu implementation thật sự:
- định nghĩa canonical serialization;
- ràng buộc thứ tự sự kiện;
- hash và verify nhất quán;
- bảo vệ key/signing nếu có;
- ghi anchor/checkpoint ra trust boundary độc lập;
- hạn chế quyền sửa/xóa.

Nếu DBA có thể thay mọi row rồi tính lại mọi hash mà không có anchor, một hash chain đơn thuần chưa cung cấp tamper evidence mạnh.

### 25.3. Audit có thể cần WORM hoặc immutable storage

Với yêu cầu kiểm toán cao, đánh giá append-only event store, object storage versioning/Object Lock theo policy, signed export hoặc cơ chế bất biến tương ứng. Không tuyên bố database table thông thường là WORM chỉ vì ứng dụng không có endpoint DELETE.

## 26. Audit events phải có thời gian và nguồn tin rõ

Một event nên ghi:
- `occurredAt`: thời điểm nguồn nói sự kiện xảy ra.
- `observedAt/ingestedAt`: thời điểm ứng dụng nhận/ghi event.
- Source: application/provider/webhook/operator.
- Evidence reference.
- Provider/account/tenant correlation.
- Trust/verification status.

Ví dụ provider gửi webhook trễ 30 phút:

```text
Provider deliveredAt: 09:01Z
App webhook ingestedAt: 09:31Z
```

Không được ghi đè hai mốc thành một “deliveredAt 09:31” nếu muốn đo delivery latency.

### 26.1. Clock skew

Các hệ thống có thể lệch đồng hồ. Dùng UTC instants, time synchronization, và ghi nguồn timestamp. Khi tranh chấp, audit cần biết “thời điểm được nguồn ghi nhận” không nhất thiết là “thời điểm chân lý tuyệt đối”.

### 26.2. Event order

Webhooks có thể đến ngoài thứ tự. Đừng để event `DEFERRED` đến muộn ghi đè `DELIVERED` đã được xác nhận mà không áp state transition policy.

### 26.3. Correlation ID

Sử dụng:
- business event key;
- messageKey;
- attemptId;
- provider reference;
- webhook eventId;
- traceId.

Không đồng nhất tất cả thành một ID vì chúng có phạm vi khác nhau.

## 27. Privacy và retention phải là phần của kiến trúc

Câu hỏi “giữ audit 7 năm” không thể trả lời chung cho mọi tổ chức và khu vực pháp lý. Thời hạn phù hợp phụ thuộc:
- loại dữ liệu;
- mục đích sử dụng;
- hợp đồng;
- luật/quy định áp dụng;
- nghĩa vụ pháp lý;
- chính sách quản trị hồ sơ.

**Cần có bộ phận pháp lý/privacy/security phê duyệt retention thực tế.** Bài này đưa khung kỹ thuật, không thay tư vấn pháp lý.

### 27.1. Tách retention của các lớp

| Dữ liệu | Mục đích | Chiến lược |
|---|---|---|
| Raw MIME/attachment | Retry ngắn hạn, hỗ trợ điều tra đặc biệt | Hạn chế, mã hóa, xóa theo policy |
| Outbox job | Trạng thái thực thi | Giữ qua retry/cửa sổ recovery |
| Attempt history | Debug và audit submission | Giữ metadata theo risk tier |
| Provider delivery events | Giao nhận và complaint | Giữ dữ liệu tối thiểu và provenance |
| Consent/suppression | Không gửi trái ý người nhận | Theo chính sách quyền và mục đích |
| Aggregate metrics | SLO/capacity planning | Có thể aggregate, giảm PII |
| Immutable audit | Bằng chứng bắt buộc | Retention/phân quyền được phê duyệt |

### 27.2. Quyền xóa và nhu cầu lưu bằng chứng

Một yêu cầu xóa dữ liệu có thể xung đột với nghĩa vụ lưu trữ một số hồ sơ. Cần cơ chế đánh giá từng loại dữ liệu và căn cứ áp dụng, không xóa sạch logs/consent vô điều kiện cũng không giữ toàn bộ vĩnh viễn.

### 27.3. Phân biệt suppression với marketing profile

Khi người dùng unsubscribe, hệ thống có thể cần giữ một bản ghi suppression tối thiểu để không gửi trở lại. Không nhất thiết cần giữ toàn bộ profile hoặc nội dung chiến dịch.

### 27.4. Mã hóa và quyền truy cập

- Encryption at rest theo sensitivity.
- Access control ở DB/object store.
- KMS/key rotation.
- Backups và retention phù hợp.
- Audit truy cập dữ liệu nhạy cảm.
- Redaction/pseudonymization cho logs.
- Không xuất dump production sang laptop/test environment.

## 28. Data residency, vendor và trách nhiệm hợp đồng

Nếu email chứa dữ liệu được phân loại:
- Provider có lưu MIME/body và attachments không?
- Lưu ở khu vực nào và trong bao lâu?
- Có chuyển dữ liệu sang subprocessors không?
- Nhân viên hỗ trợ provider có truy cập nội dung không?
- Có yêu cầu hợp đồng xử lý dữ liệu không?
- Các quyền xóa/export có khả dụng trong thời hạn nào?
- Logs/webhooks của provider có thể chứa PII gì?
- Gửi mail quốc tế có các điểm trung chuyển ngoài kiểm soát không?

Không thể bảo đảm “dữ liệu không rời quốc gia” chỉ vì ứng dụng và database đặt trong một khu vực; email gửi tới hệ sinh thái bên ngoài có thể đi qua nhiều hệ thống. Phải nêu ranh giới và đánh giá theo chính sách thực tế.

### 28.1. Data Processing Agreement và compliance evidence

Đối với vendor được chọn, yêu cầu nhóm pháp lý/security kiểm tra tài liệu, chứng nhận, phạm vi và thời hạn hiệu lực. Không dựa vào chứng nhận ở cấp marketing như bằng chứng mọi cấu hình đang triển khai đã compliant.

### 28.2. Shared responsibility

Ví dụ provider có TLS và audit logs, nhưng ứng dụng vẫn chịu trách nhiệm:
- chọn đúng recipient;
- bảo vệ API keys;
- không gửi dữ liệu không được phép;
- xử lý unsubscribe;
- xác thực webhooks;
- phân quyền audit;
- xóa dữ liệu nội bộ theo policy.

## 29. Thiết kế Spring Boot: phân tầng trách nhiệm

Một kiến trúc dễ kiểm soát:

```text
Application use case
  └─ MailRequestService
       ├─ authorization / consent / templates
       ├─ outbox transaction
       └─ audit MAIL_REQUESTED

DueMailDispatcher
  ├─ atomic claim / lease / attempt
  ├─ MailContentRenderer
  ├─ OutboundMailPort
  │    ├─ SpringSmtpAdapter(JavaMailSender)
  │    └─ ProviderHttpApiAdapter(optional)
  ├─ outcome classifier
  └─ audit outcome events

ProviderEventEndpoint
  ├─ signature verification
  ├─ event idempotency
  └─ delivery status projection

Operations
  ├─ metrics / alerts
  ├─ reconciliation
  ├─ admin audit
  └─ maintenance pause/drain
```

### 29.1. Tầng application không biết SMTP transport chi tiết

Ví dụ port:

```java
package com.example.mail.domain;

import java.util.UUID;

public interface OutboundMailPort {
    SubmissionResult submit(MailSubmission submission);
}

public record MailSubmission(
    UUID messageKey,
    UUID attemptId,
    String senderProfile,
    String recipient,
    String subject,
    String plainText,
    String htmlText
) {}

public enum SubmissionStatus {
    SMTP_ACCEPTED,
    PROVEN_NOT_ACCEPTED_RETRYABLE,
    PROVEN_NOT_ACCEPTED_PERMANENT,
    UNKNOWN
}

public record SubmissionResult(
    UUID attemptId,
    SubmissionStatus status,
    String providerReference,
    String safeReasonCode
) {}
```

Các kiểu này là model của ứng dụng, không phải API có sẵn trong Spring Mail.

### 29.2. SMTP adapter dùng JavaMailSender

```java
package com.example.mail.adapters;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class SpringSmtpAdapter
        implements OutboundMailPort {

    private final JavaMailSender sender;

    public SpringSmtpAdapter(JavaMailSender sender) {
        this.sender = sender;
    }

    @Override
    public SubmissionResult submit(MailSubmission command) {
        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom("no-reply@example.com");
            helper.setTo(command.recipient());
            helper.setSubject(command.subject());
            helper.setText(
                command.plainText(),
                command.htmlText()
            );

            message.setHeader(
                "X-Application-Message-Key",
                command.messageKey().toString()
            );

        } catch (MessagingException ex) {
            return new SubmissionResult(
                command.attemptId(),
                SubmissionStatus.PROVEN_NOT_ACCEPTED_PERMANENT,
                null,
                "MIME_PREPARATION_ERROR"
            );
        }

        try {
            sender.send(message);

            return new SubmissionResult(
                command.attemptId(),
                SubmissionStatus.SMTP_ACCEPTED,
                null,
                null
            );
        } catch (MailException ex) {
            // JavaMailSender abstraction không luôn cung cấp
            // bằng chứng phase SMTP chính xác.
            // Không mặc định every exception = safe retry.
            return new SubmissionResult(
                command.attemptId(),
                SubmissionStatus.UNKNOWN,
                null,
                "SUBMISSION_RESULT_NOT_CONFIRMED"
            );
        }
    }
}
```

Ví dụ cố ý **conservative**: khi không có dữ liệu đáng tin về SMTP phase, exception sau `send` được coi `UNKNOWN`. Trong production:
- không hardcode From; lấy verified identity từ sender profile;
- không để recipient bất kỳ bypass authorization;
- dùng template renderer đã được kiểm tra;
- phân biệt các lỗi build message trước network và lỗi submission;
- lấy provider reference khi adapter thực sự có;
- ghi state/audit bằng transaction tại tầng orchestration.

Không cần gắn mọi quyết định vào adapter; mail worker phải persist kết quả và xử lý retry/UNKNOWN.

## 30. Audit ở tầng ứng dụng: một service minh họa

Một interface audit tách logic:

```java
public interface MailAuditSink {
    void append(MailAuditEvent event);
}

public record MailAuditEvent(
    String messageKey,
    String attemptId,
    String tenantId,
    String eventType,
    String actorReference,
    java.time.Instant eventTime,
    String reasonCode
) {}
```

Trong business transaction:

```java
@Transactional
public MailRequestReceipt requestReceipt(
        PaymentCompletedEvent event) {

    authorization.checkCanNotify(event);
    String businessKey = businessKeys.forPayment(event);

    EmailOutboxRow row =
        outbox.insertIfAbsent(businessKey, event);

    audit.append(new MailAuditEvent(
        row.messageKey(),
        null,
        event.tenantId(),
        "MAIL_REQUESTED",
        "payment-service",
        clock.instant(),
        null
    ));

    return new MailRequestReceipt(row.messageKey());
}
```

`PaymentCompletedEvent`, repositories, và `MailRequestReceipt` ở đây là các loại do ứng dụng định nghĩa. Thực thi `insertIfAbsent` phải dựa trên unique constraint/transaction, không chỉ `SELECT` kiểm tra trước rồi mới `INSERT` không có khóa.

### 30.1. Tránh “audit call” ngoài transaction bị mất

Nếu outbox insert commit nhưng audit append ở một service mạng khác thất bại, có thể thiếu sự kiện. Tùy yêu cầu, cần:
- insert audit event cùng transaction;
- hoặc ghi audit outbox event để publish bền vững;
- hoặc thiết kế phương án reconcile.

### 30.2. Audit append phải theo semantics “sự kiện đã xảy ra”

Không ghi `SMTP_ACCEPTED` trước khi có bằng chứng. Cũng không ghi `DELIVERED` chỉ vì worker không ném exception.

## 31. Đánh giá lịch gửi, timezone và deadline

Nếu sản phẩm cần scheduled emails, yêu cầu bổ sung:

- `sendAt` biểu diễn thời điểm tuyệt đối.
- `ZoneId` cho lịch theo giờ địa phương/lặp.
- DST gap/overlap policy.
- Cancellation/rescheduling.
- Expiration của OTP/reset link/promotion.
- Catch-up sau downtime.
- Durable schedule definitions và occurrences.
- Unique key cho mỗi recurrence.
- Quota/rate khi backlog dồn sau bảo trì.

### 31.1. Không dùng Thread.sleep cho lịch dài

```java
Thread.sleep(millisUntilSend);
mailSender.send(message);
```

không có khả năng sống qua restart và giữ thread vô ích. Persist scheduled job rồi dùng due-job dispatcher.

### 31.2. Không đồng nhất “đã đến hạn” và “đã được giao”

SLO cho scheduling cần phân biệt:
- `sendAt`: không được gửi trước mốc này;
- `claimedAt`: worker bắt đầu xử lý;
- `smtpAcceptedAt`: relay accepted;
- `deliveredAt`: provider/recipient xác nhận theo semantics của họ.

### 31.3. Thời gian trên nhiều hệ thống

Sử dụng `Instant`/UTC cho timestamps kỹ thuật, `ZoneId` cho ý định người dùng và `Clock` inject để test. Không phụ thuộc `ZoneId.systemDefault()` khi lịch thuộc timezone của recipient.

## 32. Thiết kế queue, backpressure và capacity

Một yêu cầu “gửi 1 triệu email trong một giờ” không thể giải bằng tăng `maxMessagesPerPoll` mà không xét provider quotas.

Các thông số:
- average/peak requests per second;
- size của MIME/attachment;
- max concurrent SMTP connections;
- provider accepted rate;
- per-domain throttling;
- queue capacity;
- retry budget;
- consumer count;
- email category priorities;
- tenant isolation.

### 32.1. Throughput cần tính từ bottleneck

Ví dụ nếu provider chỉ cho 20 submissions/giây, một triệu emails cần ít nhất khoảng 50.000 giây ở giới hạn đó, chưa tính retries và overhead. Không thể cam kết xong trong một giờ bằng cách tạo thêm 100 workers khi upstream quota không thay đổi.

### 32.2. QueueChannel memory không durable

Trong Spring Integration, `QueueChannel` mặc định có thể là hàng đợi trong bộ nhớ. Để đáp ứng durability, cần persistent MessageStore/broker hoặc outbox. Nếu queue đầy, producer phải nhận backpressure thay vì âm thầm mất job.

### 32.3. Concurrency và rate là hai giới hạn khác nhau

- Concurrency: bao nhiêu gửi đồng thời?
- Rate: bao nhiêu gửi mỗi giây/phút?
- Capacity: lưu tối đa bao nhiêu jobs chờ?
- Retry budget: một job được thử lại tối đa bao nhiêu lần?

Một poller interval không thay thế được cả bốn.

## 33. Kiến trúc multi-tenant và blast radius

Một tổ chức có nhiều tenants/campaigns cần xem:
- verified sender domain theo tenant;
- credential/SMTP account isolation;
- quota và reputation isolation;
- outbox tenant key;
- template/data isolation;
- webhook correlation theo provider account;
- audit access control;
- retention theo data class;
- route failover policy.

### 33.1. Một credential chung có đủ không?

Có thể dùng shared provider account nếu tất cả sender identities đã được xác thực và quyền truy cập được kiểm soát. Nhưng shared account có rủi ro:
- một tenant gây spam làm ảnh hưởng reputation của nhiều tenant;
- quota chung bị chiếm;
- logs và provider events khó phân tách;
- compromise có phạm vi rộng.

Phải cân đối giữa isolation, chi phí account/domain và vận hành.

### 33.2. Không để failover vượt qua ranh giới quyền

Nếu provider A lỗi, chuyển sang provider B chỉ hợp lệ khi:
- domain được verified trên B;
- dữ liệu được phép xử lý qua B;
- suppression vẫn áp dụng;
- quota B đủ;
- không có `UNKNOWN` ở A được resend mù;
- audit ghi quyết định routing.

## 34. Monitoring và alert phục vụ cả ba nhóm yêu cầu

Bảng metric gợi ý:

| Metric | Nhóm | Điều muốn biết |
|---|---|---|
| `mail_outbox_pending_count` | Giao nhận | Bao nhiêu yêu cầu còn chờ? |
| `mail_oldest_due_age_seconds` | Giao nhận | Email quá hạn bao lâu? |
| `mail_smtp_submission_latency_seconds` | Giao nhận | Relay acceptance chậm ra sao? |
| `mail_smtp_outcomes_total{status}` | Giao nhận | Accepted, rejected, unknown? |
| `mail_provider_delivery_events_total{type}` | Giao nhận | Delivered, bounce, complaint? |
| `mail_unknown_attempt_count` | Giao nhận/kiểm toán | Những trường hợp chưa xác định? |
| `mail_reconciliation_lag_seconds` | Kiểm toán | UNKNOWN tồn tại bao lâu? |
| `mail_webhook_signature_failures_total` | Bảo mật | Có callback không hợp lệ? |
| `mail_unauthorized_send_attempts_total` | Bảo mật | Có nỗ lực gửi trái quyền? |
| `mail_suppression_blocked_total` | Bảo mật/giao nhận | Có ngăn gửi sai consent? |
| `mail_audit_append_failures_total` | Kiểm toán | Có rủi ro mất bằng chứng? |
| `mail_provider_rate_limited_total` | Giao nhận | Quota/provider throttle? |

### 34.1. Metric labels phải kiểm soát cardinality

Không đưa email address, messageKey, attemptId, raw tenant ID tùy ý vào labels. Sử dụng provider/profile/category/outcome trong phạm vi được kiểm soát; IDs chi tiết nằm ở logs/audit có quyền truy cập.

### 34.2. Alert cần gắn hành động

Ví dụ:
- UNKNOWN tăng đột biến → pause auto retry và điều tra relay/network.
- Backlog vượt SLA → kiểm tra worker/quota.
- DMARC fail rate tăng → kiểm tra provider/domain alignment.
- Audit append lỗi → kích hoạt quy trình bảo vệ chứng cứ/incident.
- Complaints tăng → pause campaign, kiểm tra consent/suppression.

### 34.3. Tránh log full SMTP transcript dài hạn

Protocol debug có thể lộ headers, recipient metadata hoặc credentials trong một số môi trường. Chỉ bật trong cửa sổ có kiểm soát, redact và phân quyền.

## 35. Đánh giá RTO, RPO và continuity

Một giải pháp email quan trọng cần có kế hoạch khi:
- database unavailable;
- SMTP provider outage;
- secret rotation lỗi;
- webhook delivery delayed;
- worker cluster bị restart;
- region không khả dụng.

### 35.1. RPO và dữ liệu nào được bảo vệ?

**RPO** đặt mục tiêu lượng dữ liệu có thể mất trong thảm họa. Nếu outbox được persist trên DB nhưng backup/replication có RPO dài, vẫn có khả năng mất email jobs khi vùng dữ liệu bị sự cố.

Cần xem toàn bộ chuỗi:
- business transaction;
- outbox;
- attempt/audit events;
- queue;
- provider references;
- backups và cross-region replication nếu được phép.

### 35.2. RTO và mức xử lý sau phục hồi

**RTO** là mục tiêu khôi phục dịch vụ. Sau khi hệ thống trở lại:
- các jobs chưa hết hạn được gửi theo quota;
- stale `SENDING` được reconcile;
- không bulk-resend UNKNOWN;
- recurring schedules được materialize bù;
- các token đã hết hạn không được gửi.

RTO của application không đồng nghĩa delivery SLA của người nhận.

### 35.3. Failover không phải luôn an toàn

Provider A timeout sau DATA có thể đã accepted. Chuyển ngay sang provider B tạo duplicate. Failover policy cần evidence, permission, domain auth và route-level audit.

## 36. Kiểm thử theo yêu cầu giao nhận

Các bài test nên kiểm tra **bằng chứng và ranh giới**, không chỉ “send không ném exception”.

### 36.1. Unit tests

- Unique business event tạo một outbox row.
- Scheduler không claim job chưa tới `sendAt`.
- Job `EXPIRED` không submit.
- Provider route được chọn đúng.
- Suppressed recipient không được gửi.
- Unknown outcome không auto retry.
- Status transitions không nhảy từ `REQUESTED` thẳng sang `DELIVERED` chỉ vì worker chạy.
- Audit event chỉ ghi outcome đã có bằng chứng.

### 36.2. Integration tests với SMTP sandbox

- STARTTLS/implicit TLS đúng mode.
- Sender và recipient hợp lệ.
- MIME plain+HTML+attachment đúng.
- SMTP permanent reject.
- SMTP temporary reject.
- Auth failure.
- Socket timeout.
- Certificate hostname mismatch.
- Provider returns accepted; outbox cập nhật đúng.
- Provider accepted rồi worker DB update lỗi.

### 36.3. Fault injection sau DATA

Đây là test đặc biệt quan trọng:

```text
Fake relay receives full DATA
        |
        v
Fake relay stores message
        |
        v
Final 250 response is dropped
        |
        v
JavaMailSender throws timeout
        |
        v
Application marks UNKNOWN
        |
        v
Next poll MUST NOT automatically resubmit
```

Test này trực tiếp chứng minh workflow không biến một timeout thiếu bằng chứng thành duplicate.

### 36.4. Test nhiều instances

Hai workers cùng claim due job:
- chỉ một transaction claim thành công;
- worker cũ không ghi đè status sau khi lease token đổi;
- restart không tạo job logic thứ hai;
- stale lease recovery không gửi lại UNKNOWN.

## 37. Kiểm thử bảo mật và quyền riêng tư

Các trường hợp tối thiểu:

| Kiểm thử | Kết quả mong đợi |
|---|---|
| SMTP certificate hostname mismatch | Kết nối bị từ chối |
| Startup thiếu secret | Không dùng credential rỗng/fallback không an toàn |
| Tenant A gọi gửi dữ liệu B | Bị từ chối và audit |
| User đưa CRLF vào header-like input | Không tạo header injection |
| Template có HTML user nhập | Được escape đúng context |
| Attachment không được phép | Bị từ chối |
| Recipient bị unsubscribed | Không submit marketing |
| Webhook thiếu signature/hết hạn | Bị từ chối |
| Webhook replay cùng eventId | Không gây state transition trùng |
| Log sự cố SMTP | Không chứa password/token/raw MIME |
| Người không có quyền đọc audit | Bị từ chối và có log truy cập phù hợp |
| Tạo mail vượt quota | Bị throttled/backpressured |
| Provider failover | Không bypass consent/tenant/UNKNOWN |

### 37.1. SAST/DAST không thay business authorization tests

Static analysis có thể tìm secret hardcode hoặc các lỗi phổ biến nhưng khó chứng minh rằng một recipient thuộc đúng đơn hàng/tenant. Cần viết tests theo use cases và trust boundaries thực tế.

### 37.2. Đánh giá third-party dependencies

Spring Mail dùng Jakarta Mail provider và các libraries khác. Theo chính sách tổ chức, cần quản lý BOM, vulnerability scanning, license, patch cadence và thay đổi behavior khi nâng version.

## 38. Kiểm thử tính đầy đủ và độ tin cậy của audit

Audit cần được thử trong failure modes:

1. Business transaction commit và audit được tạo.
2. Business transaction rollback thì không ghi bằng chứng “đã yêu cầu thành công”.
3. SMTP accepted nhưng outcome DB update lỗi → record cần đối soát.
4. Provider webhook duplicate → chỉ một normalized event effect theo policy.
5. Provider webhook out-of-order → không ghi đè trạng thái đúng.
6. Audit store tạm outage → có buffering/recovery hoặc fail-closed theo risk tier.
7. Operator manual resend → có actor, reason, approval, attempt link.
8. Template version thay đổi → trace lại version được dùng.
9. Data retention job chạy → xóa/redact đúng policy, không xóa bằng chứng đang legal hold.
10. Restore backup → audit sequence/correlation còn dùng được.

### 38.1. Tamper evidence test

Nếu dùng hash chain/signed exports:
- sửa một event cũ trong test store;
- verify công cụ phát hiện integrity mismatch;
- kiểm tra anchor độc lập;
- kiểm tra quyền của actor không thể vừa sửa evidence vừa sửa anchor.

### 38.2. Đừng coi log retention là compliance

Log rotation 30 ngày không tự đáp ứng nghĩa vụ chứng cứ 1 năm hoặc 7 năm; cũng không có nghĩa phải giữ toàn bộ PII trong log cho từng đó thời gian. Phải có data classification và retention matrix được phê duyệt.

## 39. Lập bảng chấm điểm phương án kiến trúc

Một ma trận giúp ghi rõ ưu/nhược thay vì chọn theo cảm tính. Điểm ví dụ 1–5; trọng số cũng chỉ là minh họa.

| Tiêu chí | Trọng số ví dụ | Direct SMTP | SMTP + Outbox | Provider API + Outbox |
|---|---:|---:|---:|---:|
| Không mất business request sau restart | 5 | 1 | 4 | 4 |
| Quan sát submission/delivery | 5 | 2 | 3 | 4 |
| Xử lý UNKNOWN và audit attempts | 5 | 1 | 4 | 4 |
| Chi phí triển khai ban đầu thấp | 2 | 5 | 3 | 2 |
| Khả năng chuyển provider | 3 | 4 | 3 | 2 |
| Security/tenant controls tự xây | 5 | 2 | 4 | 4 |
| Operational burden thấp | 3 | 3 | 3 | 4 |
| Kiểm soát dữ liệu/nội dung | 4 | 3 | 3 | 3 |

**Các điểm trên không phải đánh giá một vendor hoặc benchmark thực nghiệm.** Chúng minh họa cách một nhóm điền điểm khi đã thu thập bằng chứng về lựa chọn cụ thể.

### 39.1. Quy trình chấm điểm

1. Đặt criteria từ business requirements.
2. Phân loại **hard gates** và soft trade-offs.
3. Gán trọng số với business/security/operations.
4. Chấm điểm từ POC, hợp đồng và tests.
5. Ghi nguồn bằng chứng.
6. Tính điểm có trọng số nếu hữu ích.
7. Ghi risk acceptance/unknowns.
8. Chốt ADR có người phê duyệt.

### 39.2. Hard gate không được bù bằng điểm cao

Nếu yêu cầu bắt buộc là data processing trong một phạm vi được phép, một phương án vi phạm điều kiện đó không thể được chọn chỉ vì giá rẻ và API tiện dụng.

Ví dụ hard gates:
- Bắt buộc TLS/hostname verification.
- Tenant isolation.
- Retention/deletion theo policy.
- Domain ownership/verified sender.
- Có khả năng xuất audit evidence theo nghĩa vụ.
- Không lưu token nhạy cảm không được phép.

### 39.3. Total Cost of Ownership

Ngoài phí provider:
- developer implementation effort;
- monitoring/on-call;
- domain warm-up và reputation;
- compliance/security reviews;
- integration tests;
- incident response;
- backups/audit retention;
- provider migration;
- training/documentation.

Chi phí thấp ở POC có thể trở thành chi phí vận hành cao.

## 40. Architecture Decision Record (ADR) mẫu

Một ADR nên trả lời **tại sao chọn** và **không chọn** các phương án.

```markdown
# ADR-001: Kiến trúc gửi email giao dịch

## Trạng thái
Accepted / Proposed / Superseded

## Bối cảnh
- Payment events cần tạo email receipt sau khi DB commit.
- API không được đợi SMTP.
- Không tự retry nếu submission outcome UNKNOWN.
- Có audit chain từ order -> message -> attempt.

## Các lựa chọn
A. Gửi trực tiếp qua JavaMailSender trong HTTP request.
B. JavaMailSender qua transactional outbox.
C. Provider HTTP API qua transactional outbox.

## Quyết định
Chọn B cho giai đoạn hiện tại vì ...
Dùng port OutboundMailPort để hỗ trợ C nếu cần.

## Bảo đảm
- Outbox không mất request sau commit trong phạm vi DB durability.
- Có attempt history và retry policy.
- Không tuyên bố exactly-once SMTP/delivery.

## Rủi ro còn lại
- UNKNOWN khi mất final SMTP response.
- Provider outage và delivery deferral.
- Phụ thuộc DNS/reputation.

## Bằng chứng
- Integration tests: ...
- Threat review: ...
- Provider documentation: ...
- SLO dashboard: ...

## Người phê duyệt
Business owner / Security / Engineering / Operations

## Ngày rà soát lại
...
```

Các dấu `...` cần được thay bằng thông tin thật; ADR không nên dừng ở câu “dùng Spring Mail vì dễ”.

## 41. Quy trình phê duyệt trước production

<escape>**</escape>Giai đoạn 1 — Discovery:
- xác định loại email, volume, PII, deadline;
- phỏng vấn owners;
- tạo requirement IDs và sơ đồ data flow.

Giai đoạn 2 — Architecture:
- chọn SMTP/API, provider, queue/outbox;
- threat model và failure analysis;
- thiết kế state machine và audit;
- xác định trust boundaries.

Giai đoạn 3 — Evidence:
- đo POC throughput;
- thử TLS, DNS/auth;
- fault-injection UNKNOWN;
- verify webhook signatures;
- test restart/DB failure;
- kiểm tra retention.

Giai đoạn 4 — Approval:
- business SLO và error budget;
- security/privacy approval;
- operations runbook;
- vendor/compliance review;
- ADR/risk register.

Giai đoạn 5 — Rollout:
- canary provider/profile;
- giới hạn concurrency;
- monitoring/alerts;
- incident rehearsal;
- rollback/failover policy;
- review sau một chu kỳ vận hành.

**Không nên coi “gửi thử một email thành công” là chứng chỉ kiến trúc đủ an toàn.**

## 42. Ví dụ áp dụng: biên nhận thanh toán

### 42.1. Yêu cầu

- Payment state là nguồn sự thật, không phụ thuộc email.
- Khi payment committed, email request được persist cùng transaction.
- Có idempotency key theo tenant/payment/receipt type.
- Không gửi trùng một cách tự động nếu SMTP outcome UNKNOWN.
- Nội dung không chứa dữ liệu thẻ thanh toán không cần thiết.
- Có thể truy nguyên template version, recipient và submission attempts.
- Nếu provider rejected/timeout, operator có bằng chứng để xử lý.
- Retention theo chính sách hồ sơ và privacy được phê duyệt.

### 42.2. Kiến trúc gợi ý

```text
Payment DB transaction
  ├─ settle payment
  ├─ insert email_outbox
  └─ append MAIL_REQUESTED audit
             |
             v
Due dispatcher + claim
             |
             v
Renderer + verified sender profile
             |
             v
Spring JavaMailSender / provider
             |
             v
Submit outcome / UNKNOWN handling
             |
             v
Provider events / audit
```

### 42.3. Những gì không được cam kết

- Không thể chắc chắn người nhận đã đọc biên nhận.
- Không thể hứa generic SMTP exactly-once trong mọi lỗi mạng.
- Không được tự ý chuyển toàn bộ dữ liệu payment sang body email.
- Không được nói success chỉ dựa vào enqueue trong bộ nhớ.

## 43. Ví dụ áp dụng: email xác minh và reset password

Các yêu cầu khác với biên nhận:

- TTL ngắn.
- Token một lần sử dụng.
- Không log token/link.
- Có rate limit theo account/IP/tenant.
- Không tiết lộ email tồn tại hay không qua API response.
- Không gửi email đã expired khi backlog được xử lý sau downtime.
- Link không kích hoạt hành động nhạy cảm chỉ bởi prefetch.
- Nếu UNKNOWN, cân nhắc yêu cầu người dùng bắt đầu flow mới thay vì resend token cũ.
- Audit chỉ ghi metadata phù hợp, không lưu plaintext token lâu dài.

### 43.1. Gửi nhanh khác gửi chắc chắn tới Inbox

Một provider có độ trễ SMTP thấp vẫn không kiểm soát mailbox filters. Thiết kế sản phẩm có thể cần UI cho phép request lại token có giới hạn, thay vì giả định deliverability tuyệt đối.

### 43.2. Tránh tạo nhiều token hợp lệ cùng lúc ngoài ý muốn

Nếu user retry nhiều lần, quy tắc token rotation/invalidation phải rõ. Email duplicate không được phép dẫn tới bỏ qua bảo vệ ở tầng xác thực.

## 44. Ví dụ áp dụng: marketing campaign

Đây là nhóm yêu cầu khác:
- Consent và unsubscribe.
- Suppression/hard bounce/complaint.
- Quota/rate limit và reputation.
- Phân tách sender/domain/profile.
- Tôn trọng quiet hours/timezone.
- Hạn chế duplicate campaign.
- Không gửi bù chiến dịch đã hết giá trị sau downtime.
- Privacy/tracking policy.
- Khả năng dừng campaign và drain những attempts đang chạy.

### 44.1. Dừng marketing không được ảnh hưởng transactional không cần thiết

Một provider account dùng chung có thể khiến marketing tăng complaints làm ảnh hưởng biên nhận. Cân nhắc route isolation và quota riêng theo policy.

### 44.2. Metrics marketing khác email giao dịch

Marketing thường quan tâm suppression, complaint, bounce và conversion, nhưng không được diễn giải open tracking như bằng chứng người nhận đã thật sự đọc.

## 45. RACI và trách nhiệm vận hành

Một hệ thống kiểm soát tốt có ownership rõ:

| Chủ thể | Vai trò thường có |
|---|---|
| Business owner | Chấp nhận mức rủi ro mất/trùng, deadline, SLA |
| Engineering | Thiết kế state machine, outbox, adapters, tests |
| Security | Threat model, secrets, TLS, RBAC, hardening |
| Privacy/Legal | Data classification, retention, vendor obligations |
| SRE/Operations | Monitoring, backup, incident, provider routing |
| Marketing/Customer Ops | Consent, suppression, complaint workflows |
| Provider/Vendor | Dịch vụ SMTP/API, logs/webhooks theo contract |
| Audit/Compliance | Tiêu chí bằng chứng và quy trình kiểm tra |

Không một vai trò riêng lẻ nên tự quyết định tất cả requirement nếu ảnh hưởng dữ liệu cá nhân, nghĩa vụ pháp lý hoặc quyền gửi đại diện tổ chức.

## 46. Những hiểu lầm nguy hiểm

| Hiểu lầm | Giải thích đúng |
|---|---|
| “Spring Mail gửi được là đủ” | Cần delivery, security, audit requirements và operations |
| “`send()` không ném lỗi nghĩa là đã vào Inbox” | Thường chỉ phản ánh submission thành công |
| “SMTP timeout nghĩa là chưa gửi” | Relay có thể accepted trước khi response mất |
| “Thêm RetryTemplate đảm bảo không mất” | Có thể gây duplicate nếu không xét UNKNOWN |
| “Outbox đảm bảo exactly-once” | Outbox không làm SMTP atomic |
| “SPF/DKIM/DMARC đảm bảo delivered” | Chỉ là các tín hiệu xác thực domain quan trọng |
| “TLS là đủ bảo mật” | Còn authorization, secrets, content, privacy và logs |
| “Provider webhook đáng tin tuyệt đối” | Phải verify, dedupe và xử lý out-of-order |
| “Message-ID giúp relay dedupe” | Generic SMTP không cam kết vậy |
| “Giữ raw email mãi là audit tốt” | Tăng rủi ro dữ liệu và retention không cần thiết |
| “Có hash trong DB là immutable” | Cần chain/anchor/quyền truy cập thật |
| “Provider có compliance badge nên app compliant” | Shared responsibility, config và data flow vẫn cần xét |
| “Failover luôn tăng reliability” | UNKNOWN + failover có thể nhân đôi submissions |
| “Đã delivered nghĩa là người nhận đọc” | Delivery event không chứng minh đọc |
| “Không cần phân biệt transactional và marketing” | Consent, reputation, deadlines và policy khác nhau |
| “Hệ thống chạy UTC thì không cần ZoneId” | Lịch theo giờ địa phương vẫn cần zone rules |

## 47. Checklist đánh giá trước khi chốt phương án

### 47.1. Giao nhận

- [ ] Đã phân nhóm email và định nghĩa impact khi mất/trùng.
- [ ] Có state machine rõ, accepted khác delivered.
- [ ] Có SLI/SLO đo được và mẫu số được phê duyệt.
- [ ] Có durable outbox/queue khi business cần.
- [ ] Có unique business key/idempotency.
- [ ] SMTP UNKNOWN không bị auto retry.
- [ ] Có retry budget/backoff/deadline.
- [ ] Có provider events và reconciliation phù hợp.
- [ ] Có giới hạn concurrency/rate/queue capacity.
- [ ] Có kế hoạch restart/region outage/catch-up.
- [ ] Có khả năng xử lý recipient-level outcomes nếu cần.

### 47.2. Bảo mật

- [ ] SMTP/API kết nối bằng TLS đúng mode, kiểm tra hostname.
- [ ] Credential/secret quản lý ngoài source, quyền tối thiểu.
- [ ] Sender/domain verified, SPF/DKIM/DMARC aligned.
- [ ] Recipient/tenant authorization rõ.
- [ ] Không có open relay hoặc arbitrary SMTP destination.
- [ ] Template escaping/HTML, CRLF headers được kiểm soát.
- [ ] PII/token/attachment được giảm thiểu và bảo vệ.
- [ ] Suppression và consent áp dụng trước gửi.
- [ ] Webhook được xác thực và chống replay.
- [ ] Multi-provider failover không bypass quyền.
- [ ] Có threat model và security tests.

### 47.3. Kiểm toán

- [ ] Trace được business event → job → attempt → provider event.
- [ ] Mỗi audit event có actor/source/time/provenance.
- [ ] Có trạng thái UNKNOWN và manual action audit.
- [ ] Có template/version hoặc content reference phù hợp.
- [ ] Có chính sách immutability/tamper evidence nếu yêu cầu.
- [ ] Retention/deletion/backup được phê duyệt.
- [ ] Không lưu body/secret không cần thiết.
- [ ] Audit access được phân quyền và ghi nhận.
- [ ] Có khả năng export evidence theo quyền.
- [ ] Test được failure trong audit pipeline.

### 47.4. Quyết định kiến trúc

- [ ] Đã xét SMTP, provider API và relay nội bộ.
- [ ] Ghi hard gates và trade-offs.
- [ ] Có POC/integration test cho rủi ro lớn.
- [ ] TCO và vendor dependencies được đánh giá.
- [ ] Có ADR và risk acceptance.
- [ ] Có owner và runbook sự cố.
- [ ] Có canary/rollback plan.
- [ ] Những gì hệ thống **không bảo đảm** được viết rõ.

## 48. Bài tập thực hành

### Bài 1 — Viết yêu cầu có thể đo được

Một nhóm nói “email hóa đơn phải đáng tin”. Viết ít nhất 6 requirements có mã, owner, acceptance test và phân biệt request durability với delivery.

### Bài 2 — Phân loại email

Phân nhóm OTP, hóa đơn, báo cáo tuần, email marketing theo: deadline, mức nhạy cảm, rủi ro bỏ sót, rủi ro duplicate và retention.

### Bài 3 — Vẽ ranh giới giao nhận

Vẽ flow Spring service → outbox → worker → SMTP relay → recipient server. Chỉ ra nơi có thể quan sát `SMTP_ACCEPTED`, `DELIVERED` và nơi không thể xác nhận đã vào Inbox.

### Bài 4 — State machine

Thiết kế state machine có `PENDING`, `SENDING`, `SMTP_ACCEPTED`, `RETRY_WAIT`, `UNKNOWN`, `BOUNCED`. Viết quy tắc chuyển trạng thái không cho UNKNOWN tự trở lại PENDING.

### Bài 5 — SLI và mẫu số

Định nghĩa SLI “99% transactional emails accepted trong 2 phút”. Làm rõ mẫu số, cancelled/expired, missing timestamps và provider outage.

### Bài 6 — Chọn kiến trúc

So sánh direct `JavaMailSender`, memory queue và transactional outbox cho một hệ thống thương mại điện tử. Nêu hard gates và quyết định có giải thích.

### Bài 7 — SMTP vs HTTP API

Lập ma trận so sánh hai providers giả định: SMTP-only và HTTP API có idempotency + webhook. Xác định điều cần kiểm chứng từ contract trước khi chấm điểm.

### Bài 8 — Thiết kế outbox

Viết schema cho `email_outbox` và `email_submit_attempt` với unique business key, lease/fencing, retry và provider reference.

### Bài 9 — UNKNOWN sau DATA

Giả lập relay nhận hết DATA rồi làm rơi final 250. Test client có timeout nhưng job thành `UNKNOWN` và không tự submit lại.

### Bài 10 — Crash sau accepted

Worker nhận 250 nhưng update DB lỗi. Thiết kế recovery không reset stale SENDING thành PENDING và có reconciliation.

### Bài 11 — Domain authentication

Cho Header From `billing@example.com`, Return-Path vendor domain và DKIM `d=vendor.net`. Phân tích SPF/DKIM pass có đảm bảo DMARC alignment không.

### Bài 12 — Threat model

Một endpoint cho phép user nhập arbitrary From/To/HTML. Lập threat table cho open relay, phishing, CRLF injection, cross-tenant leak và XSS/phishing content.

### Bài 13 — Secret rotation

Thiết kế quy trình xoay credential SMTP khi đang có 50 active workers, đảm bảo không log secret và không dùng chung sender mutable giữa tenants.

### Bài 14 — Webhook security

Provider gửi các events delivered/bounce không theo thứ tự và có duplicate. Thiết kế signature verification, event dedupe và state transitions.

### Bài 15 — Audit trail

Từ business event `order-paid`, thiết kế các audit events cho outbox commit, attempt, SMTP accepted, webhook delivered và manual resend. Cho biết mỗi event cần evidence nào.

### Bài 16 — Retention matrix

Phân biệt retention của raw MIME, attachment, outbox, attempt metadata, provider events và consent/suppression. Giải thích trường nào cần privacy/legal approval.

### Bài 17 — Tamper-evident audit

Thiết kế hash-chained events có independent anchor. Mô tả một test sửa lịch sử để kiểm tra cơ chế phát hiện thay đổi.

### Bài 18 — Multi-tenant failover

Provider A timeout sau DATA; tenant A muốn chuyển ngay sang provider B. Phân tích UNKNOWN, domain verification, permission, consent và audit trước khi quyết định.

### Bài 19 — Disaster recovery

Ứng dụng outage 2 giờ, 10.000 jobs tồn đọng và 500 stale SENDING. Thiết kế recovery, backpressure, expired jobs, reconciliation và canary resume.

### Bài 20 — Architecture Decision Record

Soạn ADR lựa chọn giữa SMTP + outbox và provider API + outbox. Có requirements, hard gates, chi phí, rủi ro, test evidence, owner và ngày review.

## 49. Tổng kết

**Đánh giá yêu cầu giao nhận, bảo mật và kiểm toán** là bước bắt buộc trước khi lựa chọn kiến trúc email cho những ứng dụng Spring Framework Mail có rủi ro thực tế.

Những kết luận chính:

1. **Bắt đầu từ hậu quả nghiệp vụ**, không bắt đầu từ một dependency Maven/Gradle hay số dòng code.
2. **Định nghĩa ranh giới giao nhận**: queued, SMTP accepted, delivered và opened là các sự kiện khác nhau với bằng chứng khác nhau.
3. **Viết yêu cầu đo và kiểm thử được** cho độ trễ, tỷ lệ lỗi, retry, deadline, privacy và khả năng truy nguyên.
4. **Transactional outbox** giúp giữ yêu cầu qua restart và gắn email với business transaction, nhưng không làm SMTP exactly-once.
5. **UNKNOWN phải là trạng thái hạng nhất** khi server có thể đã accepted nhưng client mất phản hồi; retry mù có thể tạo email trùng.
6. **Deliverability** cần verified From, SPF/DKIM/DMARC alignment, reputation, bounce/complaint handling và suppression.
7. **Bảo mật** gồm TLS đúng, secret management, authorization, tenant isolation, hạn chế nội dung và bảo vệ attachments — không chỉ bật STARTTLS.
8. **Audit** cần sự kiện có actor, correlation, provenance và evidence; không đồng nghĩa giữ raw MIME hoặc debug log mãi mãi.
9. **Privacy, retention và vendor obligations** phải được đánh giá theo dữ liệu và quy định thực tế, không suy diễn từ một chứng nhận của nhà cung cấp.
10. **SMTP relay, provider API và outbox** là các lựa chọn có trade-offs; chọn bằng hard gates, POC, tests, tổng chi phí và ADR.
11. **Vận hành phải có owner, SLO/metrics, reconciliation, incident runbook và disaster recovery**, không dừng ở một test gửi mail thành công.
12. **Bảo đảm chưa thể chứng minh phải được ghi rõ là rủi ro còn lại**, thay vì hứa “đã gửi chắc chắn, không bao giờ trùng và luôn vào Inbox”.

Một kiến trúc email trưởng thành không phải là kiến trúc có nhiều thành phần nhất, mà là kiến trúc **đáp ứng những cam kết cần thiết, bảo vệ dữ liệu, giữ được bằng chứng và giải thích trung thực điều gì đã xảy ra khi mạng hoặc nhà cung cấp gặp sự cố**.
