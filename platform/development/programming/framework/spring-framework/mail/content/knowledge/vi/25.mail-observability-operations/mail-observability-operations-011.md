# Runbook cho lỗi xác thực, TLS và DNS trong Spring Framework Mail

Ứng dụng dùng **Spring Framework Mail** có thể gửi email thành công trong môi trường phát triển nhưng thất bại sau khi triển khai: SMTP trả lỗi xác thực, kết nối STARTTLS không nâng cấp được, chứng chỉ không hợp lệ, hostname không phân giải được hoặc bản ghi DNS của người gửi bị cấu hình sai. Các lỗi này thường xuất hiện dưới cùng một triệu chứng nghiệp vụ: **“Email không đến”**, trong khi nguyên nhân, mức độ ảnh hưởng và cách khắc phục hoàn toàn khác nhau.

**Runbook** là tài liệu hành động dành cho người trực vận hành. Thay vì chỉ giải thích khái niệm, runbook phải giúp trả lời nhanh:

1. Email đã được ứng dụng tạo và đưa vào hàng đợi chưa?
2. Lời gọi `JavaMailSender.send(...)` thất bại ở bước nào?
3. Lỗi thuộc **SMTP AUTH**, **TLS/certificate**, **DNS** hay một nguyên nhân khác?
4. Phạm vi là một instance, một SMTP account, một domain nhận hay toàn hệ thống?
5. Cần tạm dừng gửi, điều chỉnh retry, xoay vòng secret hay sửa DNS?
6. Làm thế nào xác minh khôi phục mà không gửi trùng hoặc làm quá tải relay?

Bài này trình bày runbook có thể điều chỉnh cho ứng dụng Spring Boot dùng `JavaMailSenderImpl` và Jakarta Mail, kết hợp transactional outbox hoặc worker gửi nền. Các giá trị host, địa chỉ, TTL, mã lỗi và thời gian đều là **ví dụ**; quyết định cuối phải căn cứ vào cấu hình và tài liệu của SMTP provider đang sử dụng.

> Mục tiêu vận hành là **khôi phục đường gửi an toàn và bảo vệ thông điệp nghiệp vụ**, không phải làm cho exception biến mất bằng cách tắt TLS, bỏ qua certificate validation hoặc retry vô hạn.

## 1. Bản đồ các lớp có thể phát sinh lỗi

~~~mermaid
flowchart TD
    A["Business action"] --> B["Transactional outbox / queue"]
    B --> C["Mail worker"]
    C --> D["JavaMailSenderImpl / Jakarta Mail"]
    D --> E["DNS resolver: SMTP hostname"]
    E --> F["TCP connection to relay"]
    F --> G["SMTP greeting + EHLO"]
    G --> H["STARTTLS / TLS handshake"]
    H --> I["SMTP AUTH"]
    I --> J["MAIL FROM / RCPT TO / DATA"]
    J --> K["Relay queue"]
    K --> L["Recipient MX / mailbox"]
    L --> M["Delivered / deferred / bounced"]
~~~

Không phải hệ thống nào cũng đi qua từng bước theo cùng thứ tự: cổng 465 có thể dùng **implicit TLS** trước SMTP greeting, cổng 587 thường dùng **STARTTLS** sau EHLO, và một số relay nội bộ không yêu cầu AUTH trên mạng tin cậy. Nếu dùng API HTTP của nhà cung cấp email thay cho SMTP, các lỗi HTTP/TLS/API authentication cần runbook riêng.

Điều quan trọng là **định vị đúng ranh giới**. DNS hostname của SMTP relay không giống các bản ghi MX của recipient domain; lỗi AUTH không đồng nghĩa mailbox nhận không tồn tại; TLS handshake failure không được “khắc phục” bằng việc tắt xác minh chứng chỉ.

### Phân biệt submission và delivery

| Mốc | Bằng chứng | Không chứng minh |
| --- | --- | --- |
| Job được enqueue | Outbox/queue có record bền vững | SMTP đã nhận thư |
| SMTP connection thành công | TCP socket tới endpoint mở được | AUTH thành công hoặc email đã gửi |
| STARTTLS thành công | Kênh TLS được thiết lập với endpoint theo chính sách | SMTP account có quyền gửi |
| AUTH thành công | SMTP server xác thực principal | Địa chỉ `From` được phép, remote MX nhận thư |
| SMTP chấp nhận sau DATA | Relay nhận trách nhiệm xử lý message ở chặng này | Thư đã vào Inbox |
| Provider báo delivered | Nhà cung cấp xác nhận một mốc delivery theo định nghĩa của họ | Người nhận chắc chắn đọc thư |

Không ghi log `DELIVERED` ngay sau `send()` thành công. Ghi `SUBMITTED` hoặc `ACCEPTED_BY_RELAY` theo đúng bằng chứng, sau đó theo dõi provider event/bounce khi có tích hợp.

## 2. Quy trình ứng phó trong những phút đầu

Khi nhận alert “mail delivery failed”, hãy bắt đầu bằng **khoanh vùng** và **giảm tác động** thay vì sửa cấu hình ngay.

### Bước 1 — Xác minh triệu chứng

- Email bị mất, chậm, hay chỉ giao vào spam?
- Giao dịch nghiệp vụ vẫn tạo email outbox bình thường không?
- SMTP `send()` ném exception hay thành công nhưng chưa có provider delivery event?
- Chỉ lỗi email mới hay cả retry từ backlog?
- Có thay đổi gần đây về deployment, credential, certificate, DNS hoặc firewall?
- Lỗi xảy ra trên tất cả worker hay chỉ một pod/host?

### Bước 2 — Xác định mức ưu tiên

| Mức minh họa | Tình huống | Hành động |
| --- | --- | --- |
| P1 — ảnh hưởng nghiêm trọng | OTP/reset password hoặc mail giao dịch ngừng ở quy mô lớn, không có kênh thay thế | Kích hoạt incident, phân công owner, hạn chế retry storm |
| P2 — ảnh hưởng một phần | Một SMTP account, một vùng hoặc một nhóm recipient domain lỗi | Khoanh vùng route, ưu tiên job quan trọng |
| P3 — suy giảm | Một số canary lỗi, tỷ lệ TLS/DNS timeout tăng nhưng phần lớn gửi được | Điều tra, theo dõi và sửa có kiểm soát |
| P4 — cảnh báo sớm | Secret sắp hết hạn, certificate gần ngày hết hạn hoặc DNS configuration drift | Lập kế hoạch thay trước khi gây outage |

Đây là ví dụ phân loại; mức severity và ngưỡng thực tế cần theo SLA/SLO của tổ chức.

### Bước 3 — Bảo vệ hệ thống khỏi lỗi dây chuyền

- Không retry lỗi AUTH với cùng credential hàng nghìn lần.
- Giới hạn số SMTP requests, số kết nối và số attempts đồng thời.
- Giữ email bắt buộc trong outbox/queue bền vững.
- Tạm dừng hoặc giảm email marketing/campaign khi đường gửi gặp sự cố.
- Không xóa record FAILED hoặc SUBMISSION_UNKNOWN khi chưa đối soát.
- Không thực hiện xoay DNS/secret hàng loạt nếu mới chỉ có một dữ kiện chưa chắc chắn.
- Nếu incident liên quan credential bị lộ, áp dụng quy trình thu hồi khẩn cấp thay vì tiếp tục dùng credential cũ cho uptime.

### Bước 4 — Lưu bằng chứng trước khi thay đổi

Nên ghi vào incident log:

- Thời điểm bắt đầu, môi trường, cluster, version ứng dụng.
- Provider/account key, SMTP host/port và TLS mode (không ghi secret).
- Tỷ lệ `AUTH_FAILURE`, `TLS_FAILURE`, `DNS_FAILURE`, timeout, submission success.
- Một số notification/attempt ID nội bộ đại diện.
- Mã SMTP và enhanced status nếu có.
- Tình trạng DNS từ đúng workload đang lỗi.
- Thời điểm deployment, secret rotation và DNS change gần nhất.
- Backlog và tuổi của message đang chờ.

**Không paste** raw SMTP password, access token, OTP, reset link, toàn bộ MIME body hoặc PII vào ticket/chat công khai. Chỉ dùng trace đã được làm sạch và quyền truy cập phù hợp.

## 3. Bảng phân loại nhanh theo dấu hiệu

| Triệu chứng | Nhóm nghi vấn đầu tiên | Bằng chứng xác nhận |
| --- | --- | --- |
| `UnknownHostException` / không phân giải SMTP host | DNS của endpoint cấu hình | Query A/AAAA/CNAME từ cùng network; hostname có đúng không |
| `NoRouteToHostException` | Routing/network | Đường mạng, firewall, network policy |
| `ConnectException: Connection refused` | TCP endpoint/port/firewall | IP/port đúng, listener đang chạy, không nhầm implicit TLS |
| `SocketTimeoutException: connect timed out` | TCP connect path | Network drop, proxy, route, `connectiontimeout` |
| Timeout khi chờ 220/EHLO | SMTP read/greeting | SMTP server đã nhận TCP nhưng không trả lời |
| `SSLHandshakeException` | TLS handshake/trust/hostname/protocol | Certificate chain, SAN, truststore, TLS versions |
| “STARTTLS is required but host does not support it” | TLS mode/SMTP capability | EHLO extensions, đúng port và STARTTLS advertisement |
| `535 5.7.x` tại AUTH | Credential, quyền account, cơ chế AUTH | Secret version, principal, provider policy |
| `454 4.7.x` hoặc 4xx tại AUTH | Xác thực tạm unavailable/throttling theo provider | Provider incident, reply text, tần suất lỗi |
| `530` yêu cầu authentication/TLS | SMTP policy / thứ tự lệnh | TLS và AUTH có được bật, lệnh diễn ra ở giai đoạn nào |
| `550 5.1.1` tại RCPT TO | Recipient invalid theo phản hồi cụ thể | Không phải lỗi password người gửi |
| “MX not found” sau khi relay nhận thư | DNS của recipient domain hoặc chuyển phát downstream | Bounce/provider event; không nhầm với DNS relay khi submit |
| SMTP `send()` thành công nhưng thư không tới | Deliverability/downstream | Provider event, bounce, spam, quota và policy |

Tên exception và cách bọc lỗi phụ thuộc Spring/Jakarta Mail version và SMTP transport implementation. Một `MailSendException` có thể bọc `MessagingException`, `SMTPSendFailedException`, `SMTPAddressFailedException` hoặc `IOException`. Bảng là điểm khởi đầu để triage, không phải ánh xạ tuyệt đối.

### Cây quyết định tối giản

~~~mermaid
flowchart TD
    A["Mail gửi không thành công"] --> B{"Job có trong outbox?"}
    B -- "Không" --> C["Kiểm tra producer / transaction / enqueue"]
    B -- "Có" --> D{"DNS resolve SMTP host?"}
    D -- "Không" --> E["Runbook DNS endpoint"]
    D -- "Có" --> F{"TCP connect được?"}
    F -- "Không" --> G["Kiểm tra port / firewall / routing"]
    F -- "Có" --> H{"TLS handshake hợp lệ?"}
    H -- "Không" --> I["Runbook TLS"]
    H -- "Có" --> J{"SMTP AUTH thành công?"}
    J -- "Không" --> K["Runbook xác thực"]
    J -- "Có" --> L{"Relay chấp nhận DATA?"}
    L -- "Không" --> M["Phân loại 4xx/5xx/unknown outcome"]
    L -- "Có" --> N["Theo dõi provider / delivery / bounce"]
~~~

Nếu đang dùng implicit TLS, kiểm tra TLS xuất hiện **trước** SMTP greeting. Nếu là STARTTLS, cần nhận 220, EHLO và thương lượng STARTTLS trước AUTH. Cây trên chỉ nhằm nhóm lỗi, không thay cho state machine SMTP đầy đủ.

## 4. Chuẩn bị một cấu hình Spring Boot rõ ràng

Ví dụ gửi qua SMTP submission trên cổng 587 với STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: smtp-service
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "3000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Password nên được cung cấp từ một secret manager hoặc cơ chế cấu hình bảo mật khi triển khai, chẳng hạn `SPRING_MAIL_PASSWORD` qua secret injection. **Không commit SMTP password thật** vào YAML, repository hoặc container image.

### Ý nghĩa các thuộc tính vận hành

| Thuộc tính | Mục đích |
| --- | --- |
| `spring.mail.host` | SMTP endpoint mà ứng dụng **thực sự kết nối** |
| `spring.mail.port` | Port của transport mode được provider cấp |
| `spring.mail.username` / password | Thông tin xác thực SMTP AUTH |
| `mail.smtp.auth` | Kích hoạt xác thực SMTP theo cấu hình |
| `mail.smtp.starttls.enable` | Cho phép nâng cấp phiên SMTP plaintext thành TLS qua STARTTLS |
| `mail.smtp.starttls.required` | Yêu cầu STARTTLS để tránh tiếp tục không bảo mật khi không có khả năng |
| `mail.smtp.ssl.checkserveridentity` | Kiểm tra hostname certificate theo SMTP TLS provider implementation |
| `mail.smtp.connectiontimeout` | Giới hạn thời gian chờ TCP connect |
| `mail.smtp.timeout` | Giới hạn socket read |
| `mail.smtp.writetimeout` | Giới hạn socket write |

Ba timeout thường dùng đơn vị **mili giây**. Các giá trị trong ví dụ không phải cấu hình mặc định được khuyến nghị cho mọi SMTP provider. `connectiontimeout`, `timeout` và `writetimeout` cũng **không tự tạo một deadline tổng cho toàn bộ `send()`**, vì phiên SMTP gồm nhiều bước.

### Các điểm cần xác định trước khi chẩn đoán

1. Provider yêu cầu cổng 587 + STARTTLS, 465 + implicit TLS hay cấu hình khác?
2. Relay được truy cập qua public network hay private DNS/VPC?
3. Provider sử dụng SMTP username/password, app password, OAuth2/XOAUTH2 hoặc cơ chế khác?
4. TLS certificate do public CA hay internal CA cấp?
5. Workload chạy trong container, VM, Kubernetes hay on-prem, dùng DNS resolver nào?
6. Có proxy/egress gateway làm thay đổi đường mạng hoặc TLS termination không?
7. Có nhiều SMTP account/route dẫn đến log cùng một lỗi nhưng nguyên nhân khác nhau không?

Không lấy cấu hình laptop developer làm bằng chứng cấu hình trong pod production. Cần kiểm tra **giá trị hiệu lực, đã redacted**, ở runtime đang gặp lỗi.

## 5. Runbook A — lỗi xác thực SMTP

### A1. Dấu hiệu phổ biến

- SMTP server trả `535` hoặc enhanced status liên quan credential không hợp lệ.
- Server yêu cầu AUTH/TLS trước khi cho gửi (`530` trong một số triển khai).
- Authentication service tạm unavailable (`454` hoặc 4xx tương ứng theo provider).
- App password bị thu hồi, secret hết hạn, service account bị khóa.
- SMTP username đúng nhưng `From` không được ủy quyền.
- OAuth2 access token hết hạn hoặc thiếu scope/quyền SMTP.

**AUTH thất bại không đồng nghĩa `From` bị từ chối**: nếu server chấp nhận AUTH nhưng từ chối MAIL FROM, đây có thể là sender permission/policy, cần kiểm tra ở giai đoạn riêng.

### A2. Giảm tác động ngay

Nếu có bằng chứng cùng credential đang bị từ chối trên nhiều job:

1. Chặn/tạm dừng **provider lane** bị ảnh hưởng; không retry mọi email với cùng secret cũ.
2. Giữ email bắt buộc trong outbox, với tuổi/backlog và expiry được theo dõi.
3. Ngừng hoặc trì hoãn marketing không khẩn cấp.
4. Cảnh báo on-call của mail platform và secret owner.
5. Không in password trong command, logs, alerts hoặc ticket.
6. Nếu nghi secret bị lộ, đi theo quy trình incident compromise thay vì chỉ refresh cấu hình.

Một SMTP 535 trên **một lần gửi** chưa nhất thiết đủ kết luận secret đã bị thu hồi; kiểm tra provider/account, instance và lỗi trước khi mở circuit breaker toàn hệ thống.

### A3. Kiểm tra theo thứ tự

| Bước | Câu hỏi | Cách xác minh an toàn |
| --- | --- | --- |
| 1 | Ứng dụng đang dùng SMTP account nào? | Runtime config metadata đã che password; provider key |
| 2 | Credential có vừa được rotate/revoke? | Secret manager version và audit log |
| 3 | Tất cả worker cùng version không? | Version/generation metric từng pod |
| 4 | Account còn quyền gửi không? | Provider account state, SMTP AUTH policy |
| 5 | Đã bật TLS đúng mode chưa? | EHLO, STARTTLS capability, TLS trace an toàn |
| 6 | Có yêu cầu app password/MFA hoặc XOAUTH2? | Tài liệu provider, security configuration |
| 7 | Có từ chối MAIL FROM sau AUTH? | SMTP phase, sender authorization |
| 8 | Một credential mới có xác thực được không? | Canary test trên endpoint/provider được phép |

**Không liên tục thử password thủ công** tới provider, vì có thể gây khóa account, tăng tín hiệu chống tấn công hoặc lộ credential qua terminal history.

### A4. Kiểm tra secret rotation

Với các provider hỗ trợ hai credential đồng thời:

1. Tạo credential B trong secret manager, chưa revoke A.
2. Dùng B trên canary được phép, xác thực TLS/AUTH và quyền gửi `From`.
3. Triển khai B theo rolling restart hoặc cơ chế thay sender đã được kiểm chứng.
4. Theo dõi các replica/worker nào còn dùng A.
5. Chờ công việc in-flight dùng A hoàn tất hoặc drain theo chính sách.
6. Thu hồi A sau khi xác nhận hệ thống đã cutover.

Nếu provider **chỉ hỗ trợ một password đang hiệu lực**, đổi password có thể vô hiệu hóa A ngay. Khi đó cần chuẩn bị tạm dừng dispatch hoặc cutover phối hợp, sau đó drain backlog có giới hạn. Rollback cấu hình về password đã bị revoke **không phải** kế hoạch khôi phục khả thi.

### A5. Secret store cập nhật chưa chắc JavaMailSender đã cập nhật

Trong cấu hình Spring Boot thông thường, `JavaMailSenderImpl` nhận username/password khi bean được tạo. Thay secret trong vault, Kubernetes Secret hoặc file mount **không tự bảo đảm** bean đang chạy đọc giá trị mới. Chọn một cơ chế:

- Rolling restart với secret mới.
- Verified refresh/rebinding theo khả năng của nền tảng.
- Tạo sender candidate mới, testConnection/canary rồi atomically swap reference ở gateway ứng dụng.

Không gọi `setUsername(...)` rồi `setPassword(...)` trên một sender đang được nhiều thread sử dụng mà mặc định đó là phép thay đổi nguyên tử. Có thể sinh cửa sổ username/password không khớp hoặc các send in-flight tiếp tục dùng credential cũ.

### A6. OAuth2/XOAUTH2

Một số SMTP provider hỗ trợ SASL XOAUTH2; access token có hạn ngắn hơn password tĩnh. Khi dùng cơ chế này:

- Refresh token trước expiry với một safety margin.
- Bảo đảm quyền/scope đúng SMTP service.
- Dùng single-flight refresh thay vì mỗi mail worker tự gọi token endpoint.
- Phân biệt access token hết hạn với refresh token bị revoke.
- Khi không lấy được token hợp lệ, tạm dừng gửi và giữ outbox.
- Không fallback sang plaintext hoặc anonymous SMTP khi AUTH thất bại.

Một số provider cho phép dùng access token như password trong SMTP XOAUTH2 theo Jakarta Mail implementation. Cấu hình thực tế phụ thuộc phiên bản thư viện, OAuth2 provider và flow đang sử dụng; không coi việc bật `mail.smtp.auth.mechanisms=XOAUTH2` là đủ nếu chưa có token provider và principal phù hợp.

### A7. Xác minh khôi phục

- Một canary xác thực TLS/AUTH thành công với secret version mới.
- Mail submission được relay chấp nhận bằng một người nhận thử được phép.
- Metrics AUTH failure giảm về mức bình thường.
- Toàn bộ instance chuyển tới version được phê duyệt.
- Retry được mở lại có giới hạn rate và concurrency.
- Email OTP/transactional còn hạn được ưu tiên.
- Không có outbox record bị xóa hoặc đánh dấu SUBMITTED khi chưa gửi.
- Credential cũ được revoke theo policy và sự kiện được audit.

Lưu ý: `JavaMailSenderImpl.testConnection()` xác minh kết nối và tùy cấu hình có thể bao gồm AUTH, nhưng **không chứng minh deliverability**, quota hoặc quyền `From` đối với mọi địa chỉ. Canary submission và provider events là các bước kiểm tra riêng.

## 6. Runbook B — lỗi TLS, STARTTLS và chứng chỉ

### B1. Triệu chứng phổ biến

- `SSLHandshakeException`, `SSLException`, `CertificateException`.
- `PKIX path building failed` hoặc lỗi không tìm được chain tin cậy.
- Certificate hostname mismatch (SAN/CN không khớp endpoint).
- TLS protocol/cipher không tương thích.
- SMTP server không quảng bá STARTTLS trong EHLO trong khi ứng dụng yêu cầu.
- STARTTLS command thất bại hoặc phiên bị ngắt khi bắt đầu TLS.
- Dùng implicit TLS trên port chỉ hỗ trợ STARTTLS, hoặc ngược lại.
- Certificate của SMTP proxy/relay nội bộ hết hạn.

Không kết luận mọi lỗi `MailSendException` đều là TLS: Spring Mail có thể bọc lỗi từ nhiều tầng. Tìm cause chain và thời điểm lỗi trong phiên SMTP.

### B2. Phân biệt STARTTLS với implicit TLS

| Cơ chế | Thứ tự tiêu biểu | Cấu hình phải khớp |
| --- | --- | --- |
| STARTTLS | TCP → SMTP 220/EHLO → STARTTLS → TLS handshake → EHLO lại → AUTH | Port/provider hỗ trợ STARTTLS, `starttls.enable/required` |
| Implicit TLS | TCP → TLS handshake → SMTP greeting/EHLO → AUTH | Provider yêu cầu SSL/TLS ngay từ đầu, thường dùng `mail.smtp.ssl.enable=true` |

Port **587** thường được dùng cho SMTP submission với STARTTLS, **465** thường dùng cho implicit TLS. Đây là quy ước phổ biến, không phải cách đoán mode duy nhất; lấy thông số chính thức của provider. Port 25 thường dùng cho giao tiếp MTA-to-MTA hoặc một số relay nội bộ, không được tự thay port để né chính sách bảo mật.

#### STARTTLS example

~~~properties
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

#### Implicit TLS example

~~~properties
spring.mail.properties[mail.smtp.ssl.enable]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

Không tự động đặt cả hai mode lên cùng một kết nối mà chưa biết khả năng provider. Với implicit TLS, hãy bảo đảm cấu hình `host/port` chính xác và kiểm tra tên certificate của hostname đã kết nối.

### B3. Giảm tác động

1. Nếu TLS bắt buộc nhưng handshake không hợp lệ, **dừng gửi qua route đó**, giữ outbox.
2. Không tắt `starttls.required`, hostname verification hoặc trust validation để gửi tạm.
3. Không đặt `mail.smtp.ssl.trust=*` trong production để né lỗi chain.
4. Khoanh vùng: một pod/JVM, một SMTP hostname, mọi môi trường hay chỉ đường qua một proxy.
5. Thu thập thời điểm certificate rotation, CA update, JDK update, đổi network egress gần nhất.
6. Có thể chuyển sang một provider/route dự phòng đã phê duyệt và xác thực đúng TLS, **không bypass** policy.

### B4. Kiểm tra TLS trực tiếp nhưng không lộ credential

Trên một môi trường có OpenSSL và đường egress giống workload gặp lỗi, có thể kiểm tra STARTTLS:

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.net:587 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net \
  -showcerts
~~~

Với implicit TLS:

~~~bash
openssl s_client \
  -connect smtp.example.net:465 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net \
  -showcerts
~~~

Các lệnh này chỉ nhằm xem **certificate chain và TLS handshake**, không gửi password hoặc email body. Chạy từ đúng pod/VM/network khi có thể; nếu workstation đi qua DNS/proxy khác thì kết quả có thể không đại diện production.

**Không dùng `s_client` trả exit code 0 làm kết luận duy nhất:** cần đọc kết quả xác minh chain/hostname, TLS protocol, certificate được trình bày và các cảnh báo. Hành vi kiểm tra CA có thể phụ thuộc OpenSSL version và trust store của môi trường chạy lệnh, vốn **khác Java truststore**.

### B5. Kiểm tra chain và hostname

Nếu thấy `PKIX path building failed`, kiểm tra:

- Chứng chỉ leaf có được cấp bởi CA đáng tin không?
- Server có gửi intermediate chain cần thiết không?
- JDK/JRE runtime đang dùng truststore nào?
- Workload có custom truststore nhưng chưa chứa internal CA không?
- Certificate vừa được rotate nhưng có node cũ vẫn phục vụ chain trước đó không?
- Proxy TLS inspection có đang thay certificate ngoài dự kiến không?
- Máy có sai thời gian dẫn tới “not yet valid” hoặc “expired” không?

Nếu thấy hostname mismatch:

- Ứng dụng kết nối `smtp.example.net` nhưng SAN chỉ có `mail.internal.example.net`?
- DNS CNAME trỏ sang host khác nhưng certificate không bao phủ **tên ứng dụng đang kiểm tra**?
- Một load balancer/SNI route trả certificate của tenant khác?
- Ứng dụng kết nối bằng IP trực tiếp thay hostname dự kiến?

**Không sửa bằng cách tắt `mail.smtp.ssl.checkserveridentity`.** Sửa hostname, certificate SAN hoặc endpoint được cấu hình theo yêu cầu thực tế.

### B6. Phân biệt truststore Java và OpenSSL

OpenSSL có thể tin certificate trong OS store, trong khi JVM dùng một truststore khác hoặc được chỉ định bằng:

~~~text
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.trustStorePassword
~~~

Các giá trị này là JVM/system properties trong một số cấu hình Java TLS. Không in truststore password hoặc toàn bộ JVM arguments nếu trong đó có secret. Nếu cần kiểm tra truststore, dùng công cụ như `keytool -list` với đường dẫn cụ thể và quyền hợp lệ; không chia sẻ output nhạy cảm ngoài phạm vi điều tra.

Một thiết lập truststore tùy chỉnh có thể làm thiếu public CA, dẫn đến việc laptop kết nối được nhưng pod không được. Nếu dùng private CA, phải đưa **CA tin cậy hợp lệ** vào truststore theo quy trình vận hành, không trust-all.

### B7. Certificate hết hạn

Một certificate hết hạn có thể gây lỗi đồng thời trên nhiều worker tại một thời điểm. Runbook:

1. Xác nhận `notBefore/notAfter` của certificate được server **thực sự trình bày**.
2. Kiểm tra hostname và tất cả endpoint/load balancer trong pool.
3. Kiểm tra thời gian hệ thống và clock skew.
4. Gia hạn/triển khai certificate mới kèm chain hợp lệ.
5. Reload/restart TLS endpoint đúng theo hạ tầng.
6. Kết nối canary với hostname thật từ workload có truststore tương ứng.
7. Theo dõi TLS failures và outbox backlog, khôi phục dispatch có điều tiết.

Không chỉ xem certificate file ở máy quản trị rồi kết luận server đã dùng file đó. Một listener có thể chưa reload, một node load balancer còn certificate cũ hoặc SNI dẫn tới endpoint khác.

### B8. TLS protocol/cipher mismatch

Một JVM mới có thể tắt protocol/cipher cũ, trong khi SMTP relay chưa cập nhật. Ngược lại, provider có thể yêu cầu TLS mới hơn. Khi gặp handshake failure:

- Xác định JDK version, Java security policy và TLS version được đề xuất.
- Xem danh sách protocol/cipher được client/server hỗ trợ qua công cụ được phép.
- Kiểm tra thay đổi gần nhất của JDK, server hoặc proxy.
- Sửa relay/provider để hỗ trợ giao thức đủ an toàn.
- Không bật lại cipher/protocol yếu chỉ để vượt qua lỗi nếu không có phê duyệt bảo mật cụ thể.

### B9. STARTTLS stripping/downgrade

Nếu provider yêu cầu TLS và server không quảng bá STARTTLS, client phải từ chối gửi khi đã cấu hình `starttls.required=true`. Một kẻ tấn công hoặc proxy lỗi có thể làm capability biến mất; đó **không phải lý do tắt TLS**.

Kiểm tra:

1. Port/host đúng không?
2. EHLO capabilities trên route đang lỗi có STARTTLS không?
3. Có proxy/firewall SMTP protocol inspection can thiệp không?
4. Provider có incident hoặc vừa thay cấu hình submission endpoint không?
5. Có dùng sai implicit TLS vs STARTTLS không?

### B10. Xác minh sau khắc phục TLS

- TLS handshake thành công với certificate chain hợp lệ.
- Hostname verification vượt qua trên **runtime thực**.
- SMTP AUTH thành công mà không gửi credential trên kênh không được bảo vệ.
- Canary submission được chấp nhận.
- TLS failure rate giảm và mail queue được drain theo rate limit.
- Không có cấu hình tạm `trust-all`, tắt TLS hoặc certificate validation còn sót.

## 7. Runbook C — lỗi DNS

**DNS** trong hệ thống email có nhiều vai trò. Để xử lý đúng phải phân biệt:

1. DNS cho **SMTP submission endpoint** mà JavaMailSender kết nối.
2. DNS cho **miền người nhận** dùng trong quá trình chuyển phát downstream.
3. DNS cho **xác thực danh tính người gửi**: SPF, DKIM, DMARC.
4. DNS reverse/PTR và reputation (thường do outbound MTA/provider quản lý).

Ứng dụng dùng SMTP relay đã cấu hình thường **không tự tra MX của mỗi recipient domain** khi gọi `JavaMailSender.send()`. Nó kết nối tới hostname của relay; chính relay/provider mới thực hiện route downstream. Đây là điểm phân biệt quan trọng khi điều tra.

### C1. Triệu chứng theo từng nhóm DNS

| Nhóm | Dấu hiệu | Cơ chế |
| --- | --- | --- |
| SMTP host không resolve | `UnknownHostException`, DNS timeout | Ứng dụng không tìm được IP của `spring.mail.host` |
| A/AAAA không khớp route | IPv6 connect lỗi, IP cũ không phục vụ SMTP | Resolver trả IP mà workload không tới được |
| CNAME/alias sai | Trỏ sang endpoint staging/khác region | Kết nối sai server hoặc TLS hostname mismatch |
| MX recipient domain lỗi | Provider báo deferred/bounced sau khi accepted | Relay không tìm được tuyến giao thư downstream |
| SPF sai/missing | Authentication/reputation issue hoặc remote reject | Domain không khai báo đúng nguồn gửi theo SPF |
| DKIM record sai/missing | DKIM verification fail ở phía nhận | Public key selector/domain không khớp chữ ký |
| DMARC policy/alignment | Remote reject/quarantine tùy receiver | Header From không align SPF/DKIM hoặc policy nghiêm |
| PTR/reverse DNS | Remote reputation/policy rejection | IP outbound thiếu hoặc có reverse mapping không phù hợp |

Không tự đổi SPF/DKIM/DMARC khi thấy `UnknownHostException` cho SMTP host. Đó là các vấn đề thuộc các lớp DNS khác nhau.

### C2. Kiểm tra hostname SMTP thực tế

Đầu tiên xác định giá trị hiệu lực của `spring.mail.host` ở instance lỗi. Đó có thể là:

- Host public do provider cấp.
- Host private chỉ resolve trong một VPC/VPN.
- Internal relay alias có split-horizon DNS.
- Service DNS của Kubernetes.
- Alias được cấu hình từ secret/config/Helm chart.

Không tự “sửa” bằng cách đổi sang địa chỉ IP hardcode nếu provider yêu cầu hostname/SNI để TLS verify. Dùng IP có thể vừa phá TLS, vừa bỏ qua load balancing/failover hoặc làm sai route.

### C3. Thao tác kiểm tra DNS từ môi trường phù hợp

Trên Windows PowerShell có thể dùng:

~~~powershell
Resolve-DnsName smtp.example.net -Type A
Resolve-DnsName smtp.example.net -Type AAAA
Resolve-DnsName smtp.example.net -Type CNAME
Test-NetConnection smtp.example.net -Port 587
~~~

Trên môi trường có `dig`:

~~~bash
dig smtp.example.net A
dig smtp.example.net AAAA
dig smtp.example.net CNAME
~~~

Hoặc dùng `nslookup` khi có sẵn:

~~~text
nslookup smtp.example.net
~~~

`Test-NetConnection` kiểm tra khả năng kết nối TCP cơ bản, **không kiểm tra STARTTLS, TLS certificate hoặc SMTP AUTH**. `dig/nslookup` kiểm tra DNS từ resolver của môi trường chạy lệnh; chúng không nhất thiết cho kết quả giống `InetAddress` trong JVM nếu có cache hoặc resolver khác.

### C4. Đọc đúng DNS response

| Kết quả | Ý nghĩa cần điều tra |
| --- | --- |
| NXDOMAIN | Tên domain không tồn tại theo resolver/view hiện tại |
| SERVFAIL | Resolver/authoritative DNS gặp lỗi trong quá trình trả kết quả |
| Timeout | DNS query không có phản hồi kịp, có thể do network/resolver |
| NOERROR nhưng không có record yêu cầu | Tên có thể tồn tại nhưng không có loại record đó |
| A trả IP không truy cập được | DNS có dữ liệu, nhưng route/firewall/endpoint có vấn đề |
| AAAA trả IPv6 nhưng mạng không đi được | Kết nối IPv6 có thể lỗi; cần xem address selection/routing |
| CNAME trỏ sai vùng/endpoint | Sai alias/configuration hoặc DNS rollout chưa đồng bộ |

Đừng gộp NXDOMAIN, SERVFAIL, timeout và TCP refused thành cùng một “DNS down”. Chúng có nguyên nhân khác nhau và cần những chủ sở hữu khác nhau.

### C5. Kiểm tra DNS từ chính pod/VM

Nếu production chạy Kubernetes/container:

- Query DNS từ pod cùng namespace/network policy với mail worker.
- Đối chiếu nameserver/search domain trong cấu hình resolver của pod.
- Kiểm tra CoreDNS hoặc dịch vụ resolver nội bộ nếu có.
- Đối chiếu kết quả với một pod khỏe trong cùng cluster.
- Kiểm tra DNS policy, egress rule, NAT và route tới SMTP endpoint.
- Xem có sự khác biệt theo node/zone/region không.

Một `dig` từ laptop thành công không chứng minh pod production cũng resolve được. Nếu ứng dụng bị DNS caching, JVM có thể vẫn giữ IP cũ trong khi `dig` đã trả IP mới.

### C6. Java DNS caching và TTL

Java networking có thể cache kết quả phân giải tên. Chính sách TTL phụ thuộc runtime, security properties, OS và cách ứng dụng sử dụng DNS. Khi SMTP provider đổi IP nhưng ứng dụng vẫn dùng endpoint cũ:

1. Xem thời điểm DNS record thay đổi.
2. Xem resolver trả kết quả mới hay cũ.
3. Kiểm tra JVM/runtime có cache tích cực hoặc tiêu cực (negative DNS cache) không.
4. Không ép TTL cực thấp hoặc vô hạn mà chưa đánh giá tải, độ trễ và failover.
5. Nếu cần restart/rollout để làm mới cache hoặc connection, làm có kiểm soát.

Một số cấu hình Java liên quan gồm `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl` trong Java security properties. Cách áp dụng phụ thuộc môi trường và phiên bản JDK; không giả định thêm chúng vào `application.yml` sẽ tự động thay đổi cache của JVM.

### C7. A và AAAA: đường IPv4/IPv6

Nếu SMTP hostname có cả A và AAAA, Java/network stack có thể thử các địa chỉ theo thứ tự/chính sách runtime. Một IPv6 route lỗi có thể khiến một số môi trường timeout trong khi IPv4 hoạt động.

Nên:

- So sánh DNS A/AAAA trả về trên workload khỏe và lỗi.
- Kiểm tra khả năng kết nối thật tới địa chỉ tương ứng qua công cụ có quyền.
- Xác định thay đổi IPv6/network vừa diễn ra.
- Làm việc với network/platform team để sửa route, firewall hoặc provider endpoint.

Không đặt `-Djava.net.preferIPv4Stack=true` như một “cách chữa chung” mà chưa chẩn đoán, vì nó thay đổi hành vi kết nối toàn JVM và có thể ảnh hưởng các dịch vụ khác.

### C8. Sai DNS alias kéo theo TLS hostname mismatch

Giả sử cấu hình là `smtp.internal.example.net` trỏ CNAME tới provider endpoint, nhưng certificate chỉ có SAN của tên provider hoặc một alias khác. Việc DNS resolve đúng IP không đủ; TLS hostname verification vẫn có thể thất bại.

Giải pháp là:

- Dùng hostname được provider hỗ trợ trong certificate/TLS.
- Hoặc cấu hình certificate phù hợp cho relay/proxy nội bộ.
- Kiểm tra SNI và load balancer routing.
- Không tắt hostname verification để giữ lại alias sai.

### C9. DNS recipient domain: tra MX để điều tra downstream

Nếu JavaMailSender submit thành công nhưng provider báo bounce/deferred do không tìm được mail server cho domain người nhận, kiểm tra MX **của recipient domain**, không phải SMTP submission host:

~~~bash
dig example.org MX
dig example.org A
dig example.org AAAA
~~~

Trên PowerShell:

~~~powershell
Resolve-DnsName example.org -Type MX
~~~

Lưu ý:

- Một domain không có MX không tự động đồng nghĩa không nhận email: SMTP có quy tắc fallback tới address records trong một số điều kiện, còn null MX thể hiện miền không nhận email.
- Một bản ghi MX có tên đích không resolve hoặc route sai có thể làm giao thư thất bại.
- Provider có thể cache DNS/queue và thử lại; ứng dụng không nên gửi bản mới chỉ vì nhận event `DEFERRED`.
- Cần xem reply của remote MX và event từ provider, không tự quyết định mailbox hợp lệ chỉ dựa trên MX query.

Không coi DNS MX lookup thành công là email chắc chắn đến inbox.

### C10. SPF, DKIM và DMARC: DNS của danh tính gửi

Một loại sự cố khác là `JavaMailSender.send()` thành công, nhưng email bị remote server từ chối hoặc chuyển spam do sender authentication không đạt. Khi đó runbook không chỉ nhìn hostname SMTP mà cần kiểm tra DNS của domain người gửi.

| Công nghệ | DNS record / cơ chế | Mục đích |
| --- | --- | --- |
| SPF | TXT của domain dùng cho SPF evaluation, thường liên quan envelope MAIL FROM | Công bố những nguồn IP được phép gửi cho domain đó |
| DKIM | TXT tại `selector._domainkey.example.net` | Public key để xác thực chữ ký DKIM trong message |
| DMARC | TXT tại `_dmarc.example.net` | Chính sách và alignment của header From với SPF/DKIM |
| PTR/reverse DNS | Reverse mapping của IP outbound | Hỗ trợ nhận diện/routing/reputation tùy receiving server |

#### Kiểm tra SPF

~~~bash
dig example.net TXT
~~~

Hoặc:

~~~powershell
Resolve-DnsName example.net -Type TXT
~~~

Xác định domain SPF thực sự được bên nhận sử dụng: có thể khác domain hiển thị trong header From. Không chỉ kiểm tra một TXT record chứa `v=spf1` rồi kết luận chắc chắn pass; còn phụ thuộc **IP nguồn gửi, envelope identity**, các cơ chế include/redirect, số DNS lookups và thực tế provider routing.

#### Kiểm tra DKIM

Nếu message có header DKIM với selector `s=mail2026` và domain ký `d=example.net`, có thể kiểm tra:

~~~bash
dig mail2026._domainkey.example.net TXT
~~~

Khi rotate DKIM key cần bảo đảm signer sử dụng selector đúng và public key đã được công bố tới DNS resolver nhận trước khi chuyển toàn bộ lưu lượng. Một số provider quản lý DKIM tự động; không nên sửa record thủ công trái hướng dẫn provider.

#### Kiểm tra DMARC

~~~bash
dig _dmarc.example.net TXT
~~~

DMARC không đơn giản là “có SPF và DKIM record”. Cần xét **authentication result** và alignment với domain của header From. Một provider có thể báo SPF pass hoặc DKIM pass nhưng DMARC fail nếu alignment không đạt. Chính sách `p=none`, `quarantine`, `reject` có ý nghĩa khác nhau. Không thay `p=reject` thành `p=none` một cách vội vàng khi chưa chẩn đoán tác động và được phê duyệt.

#### Sơ đồ phụ thuộc

~~~text
Application SMTP submission
          |
          v
Outbound relay / provider
          |
          +-- Uses sending IP / envelope sender  -> SPF assessment
          +-- Adds DKIM signature                -> DKIM DNS lookup
          +-- Sends header From domain           -> DMARC alignment
          |
          v
Remote MX evaluates authentication and policy
          |
          +-- Accept / defer / reject / spam handling
~~~

**Ranh giới cần nhớ:** SPF/DKIM/DMARC thường được bên nhận kiểm tra ở quá trình giao thư downstream. Chúng không giải thích trực tiếp vì sao máy ứng dụng bị `UnknownHostException` khi resolve `spring.mail.host`.

### C11. DNS propagation, cache và thay đổi không đồng nhất

Một DNS change có thể hiển thị khác nhau tùy resolver, TTL, split-horizon view và thời điểm cache được điền. Khi triage:

1. Ghi nhận record trước/sau thay đổi, TTL và thời điểm thực hiện.
2. Query resolver mà workload sử dụng.
3. Nếu có quyền và phù hợp, so sánh authoritative DNS với recursive resolver.
4. Kiểm tra record có lỗi typo, stale alias, duplicate policy hoặc target không tồn tại.
5. Đối chiếu những node/pod bị ảnh hưởng và không bị ảnh hưởng.
6. Tránh thay record liên tục khi cache chưa hết hạn; mỗi lần sửa lại có thể kéo dài sự không đồng nhất.

Không đưa ra ETA “DNS propagation xong sau đúng 5 phút” nếu không có cơ sở. Resolver có cache tích cực/tiêu cực và môi trường nội bộ có quy tắc riêng.

### C12. Xác minh phục hồi DNS

- SMTP hostname resolve nhất quán từ network/pod liên quan.
- IP đích có route và TCP port mở.
- TLS hostname/certificate khớp tên đã resolve và cấu hình kết nối.
- AUTH thành công và canary submission được accepted.
- DNS errors, mail queue age và delivery latency quay về ngưỡng bình thường.
- Với SPF/DKIM/DMARC, xác minh authentication result hoặc header/report từ hệ thống nhận thử, không chỉ “record tồn tại”.
- Các message deferred/bounced được xử lý theo policy, không replay hàng loạt khi thiếu bằng chứng.

## 8. Runbook D — phân biệt DNS, TCP, TLS và AUTH trong thực tế

Một cách kiểm tra theo thứ tự từ ít xâm lấn tới nhiều xâm lấn:

~~~text
1) Kiểm tra app config đã che secret
   - host, port, TLS mode, provider key
          |
          v
2) Resolve host bằng DNS tại workload
   - A/AAAA/CNAME, NXDOMAIN/SERVFAIL/timeout
          |
          v
3) Kiểm tra TCP tới host:port
   - refused, timeout, route/firewall
          |
          v
4) SMTP banner/EHLO và TLS handshake
   - STARTTLS/implicit TLS, certificate, SAN/chain
          |
          v
5) SMTP AUTH trên canary được phép
   - principal, secret version, OAuth2 rights
          |
          v
6) MAIL FROM/RCPT TO/DATA
   - from authorization, recipient/policy, quota
          |
          v
7) Provider queue/event
   - deferred/bounce/delivered/complaint
~~~

### Ví dụ lỗi từ nhiều tầng xuất hiện cùng lúc

Một deployment có thể vừa đổi `spring.mail.host` sang hostname mới, vừa dùng TLS certificate chưa bao phủ alias, vừa nạp secret sai version. Khi sửa DNS xong, lỗi tiếp theo sẽ chuyển sang TLS; sau khi sửa TLS, lỗi AUTH mới lộ ra. Không nên kết luận đã khôi phục toàn diện chỉ vì exception đầu tiên biến mất.

Làm việc từng lớp cho tới khi canary submission thành công, sau đó quan sát delivery downstream.

### Cách tránh tự gây thêm sự cố khi chẩn đoán

- Giữ số lần canary thấp, sử dụng một mailbox thử được phép.
- Không để mỗi worker cùng thực hiện `testConnection()` liên tục.
- Không đổi truststore/DNS/secret ở nhiều nơi cùng lúc nếu có thể tách thao tác.
- Ghi timestamp các thay đổi và kết quả trước/sau.
- Nếu cần rollback, chắc chắn credential/certificate/record cũ còn hợp lệ.
- Không chạy công cụ chẩn đoán với token/password trong command line hoặc URL.

## 9. Phân loại SMTP reply để không nhầm nguyên nhân

Các lỗi AUTH, TLS và DNS có thể trộn với lỗi SMTP recipient hoặc policy. Một bảng quy tắc hữu ích:

| Bằng chứng | Phạm vi lỗi | Gợi ý hành động |
| --- | --- | --- |
| DNS SMTP host NXDOMAIN | Endpoint/config/platform | Sửa DNS/hostname, giữ outbox |
| DNS timeout | Resolver/network | Kiểm tra DNS service/route và retry có backoff |
| TCP refused | Endpoint/firewall/port | Kiểm tra listener, port, network policy |
| TLS certificate không tin cậy | TLS endpoint/trust | Sửa chain/truststore có kiểm soát, không trust-all |
| STARTTLS required nhưng không available | Transport mode/policy | Sửa endpoint/port/TLS capability, không downgrade |
| SMTP AUTH 535 | Account/credential/policy | Chặn retry storm, kiểm tra secret và quyền |
| SMTP AUTH 454 | Tạm lỗi AUTH theo provider | Backoff/quan sát provider, tránh refresh dồn dập |
| MAIL FROM 553 | Sender/permission/policy | Xem quyền `From`, không suppress recipient |
| RCPT TO 550 5.1.1 | Recipient theo reply cụ thể | Có thể permanent/suppress recipient |
| RCPT TO 450/451 | Temporary recipient/service | Retry có giới hạn, theo dõi |
| DATA 554 | Message/content/policy theo reply cụ thể | Điều tra nội dung/chính sách |
| Mất final reply sau DATA | Kết quả không xác định | Không resend ngay, reconcile |
| SMTP 250 sau DATA | Relay đã accepted | Theo dõi downstream provider events |

Một mã có thể được provider dùng với ý nghĩa khác tùy giai đoạn. Enhanced status code và text phản hồi giúp phân loại nhưng cũng có thể không đầy đủ; giữ source information đã làm sạch để điều tra.

### SMTP 4xx không phải HTTP 429

SMTP có reply code và enhanced status code riêng. HTTP provider API có thể trả `429 Too Many Requests` kèm `Retry-After`, nhưng SMTP **không có HTTP Retry-After header chuẩn**. Nếu provider đưa ra chỉ dẫn retry trong SMTP text hoặc tài liệu, adapter phải xử lý theo hợp đồng đó, không tự parse HTTP header từ `MailException`.

## 10. Tổ chức mã Spring để chẩn đoán và khôi phục

`JavaMailSenderImpl` là adapter submit SMTP; tầng nghiệp vụ không nên bắt một `MailException` chung rồi coi mọi lỗi đều “recipient invalid” hoặc “retryable”.

### Mô hình phân loại lỗi ứng dụng

~~~java
package com.example.mail.ops;

public enum MailFailureCategory {
    DNS_RESOLUTION,
    TCP_CONNECTIVITY,
    SMTP_READ_TIMEOUT,
    SMTP_WRITE_TIMEOUT,
    TLS_CONFIGURATION,
    TLS_CERTIFICATE,
    SMTP_AUTH,
    SMTP_AUTH_TEMPORARY,
    SENDER_POLICY,
    RECIPIENT_TEMPORARY,
    RECIPIENT_PERMANENT,
    CONTENT_POLICY,
    SUBMISSION_UNKNOWN,
    OTHER
}

public record MailFailure(
        MailFailureCategory category,
        String providerKey,
        String normalizedSmtpCode,
        String phase,
        boolean retryable,
        boolean recipientScoped) {
}
~~~

Các kiểu trên là model nội bộ, không phải lớp có sẵn của Spring Mail. Adapter có thể đọc cause chain và thông tin của Jakarta Mail transport, đồng thời ghi nhận **SMTP phase** nếu có khả năng instrument. Không dựa duy nhất vào chuỗi exception message để đưa ra quyết định ảnh hưởng permanent suppression.

### Cách phân tầng trách nhiệm

~~~text
Business service
  - Tạo notification + outbox trong transaction
           |
           v
Mail worker
  - Claim work / kiểm tra expiry & suppression
  - Dùng rate limiter/concurrency gate
           |
           v
Transport adapter
  - Chuẩn bị MIME / JavaMailSender.send()
  - Chuẩn hóa exception thành MailFailure
           |
           v
Policy service
  - Retry? hold account? suppress recipient?
  - submission unknown? alert?
           |
           v
Outbox state + telemetry + incident monitoring
~~~

### Thí dụ boundary chuyển exception

~~~java
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.SimpleMailMessage;

public final class SmtpSubmissionAdapter {

    private final JavaMailSender sender;
    private final MailFailureClassifier classifier;

    public SmtpSubmissionAdapter(
            JavaMailSender sender,
            MailFailureClassifier classifier) {
        this.sender = sender;
        this.classifier = classifier;
    }

    public SubmissionResult submit(SimpleMailMessage message) {
        try {
            sender.send(message);
            return SubmissionResult.submitted();
        } catch (MailException cause) {
            MailFailure failure = classifier.classify(cause);
            return SubmissionResult.failed(failure);
        }
    }
}
~~~

`MailFailureClassifier` và `SubmissionResult` là interfaces/types ứng dụng cần định nghĩa. Ví dụ cho thấy vị trí chuẩn hóa lỗi, **không** ngụ ý mọi `MailException` đều có đủ dữ liệu để biết SMTP phase. Trong trường hợp cuối DATA response bị mất, ứng dụng có thể cần một gateway instrument sâu hơn hoặc provider message lookup để nhận diện `SUBMISSION_UNKNOWN`.

### Dùng `JavaMailSenderImpl.testConnection()` như thế nào?

`testConnection()` hữu ích để kiểm tra một kết nối theo cấu hình hiện tại, nhưng không phải health check toàn bộ deliverability. Không gọi nó trên mọi HTTP readiness probe khi có hàng trăm pod hoặc khi provider đang outage, vì có thể tạo connection/auth storm. Dùng:

- Startup/canary kiểm soát tần suất.
- Một scheduled health probe có rate limit và backoff.
- Kiểm tra một candidate secret/TLS config trước cutover.
- Một lần xác minh sau khi thay cấu hình.

Với web app đa chức năng dùng outbox, SMTP outage có thể làm mail lane degraded nhưng **không nhất thiết** phải khiến toàn bộ web app bị rút khỏi load balancer. Readiness strategy phụ thuộc kiến trúc và SLA.

## 11. Quan sát và metric phục vụ runbook

Một runbook chỉ có thể vận hành tốt nếu ứng dụng xuất dữ liệu đủ để trả lời “lỗi ở lớp nào” và “sau sửa có phục hồi không”.

| Metric gợi ý | Tác dụng |
| --- | --- |
| `mail_submission_attempts_total` | Tổng số lần bắt đầu submit |
| `mail_submission_success_total` | SMTP submissions thành công theo phản hồi |
| `mail_submission_failures_total` | Lỗi theo category/provider/stage |
| `mail_smtp_auth_failures_total` | Phát hiện credential/account issue |
| `mail_tls_handshake_failures_total` | Theo dõi lỗi TLS |
| `mail_dns_failures_total` | Theo dõi lỗi phân giải hostname |
| `mail_smtp_timeout_total` | Theo dõi timeout theo connect/read/write khi biết |
| `mail_smtp_latency_seconds` | Thời gian thực hiện submission |
| `mail_inflight_sends` | Số lời gọi send đang hoạt động |
| `mail_outbox_pending` | Backlog chờ |
| `mail_outbox_oldest_age_seconds` | Tuổi job chờ lâu nhất |
| `mail_retry_pending` | Số message đã lên lịch retry |
| `mail_submission_unknown_total` | Số attempt không biết chắc outcome |
| `mail_secret_active_generation` | Secret generation đang active trên từng instance |
| `mail_secret_seconds_until_expiry` | Dự báo credential expiry nếu có metadata |
| `mail_tls_cert_seconds_until_expiry` | Certificate expiry nếu monitor có nguồn dữ liệu đúng |
| `mail_provider_deferred_total` | Provider reporting deferred |
| `mail_provider_bounced_total` | Provider reporting bounced |

Tên metric do ứng dụng tự định nghĩa, có thể triển khai qua Micrometer/Spring Boot Actuator hoặc hệ thống monitoring sẵn có. **Spring Mail không tự xuất tất cả các metric này**.

### Label/cardinality

Nên dùng các chiều như:

- provider key hoặc SMTP route ID.
- failure category.
- SMTP phase.
- notification category (security, transactional, marketing).
- region/cluster.
- JVM/instance identifier ở mức cần thiết.

Tránh:

- Raw SMTP password hoặc OAuth token.
- Full recipient address, OTP, reset token.
- Notification UUID làm Prometheus label.
- Toàn bộ exception message làm label vì có thể chứa dữ liệu nhạy cảm và tạo cardinality cực cao.

Những ID chi tiết nên tra cứu qua log/event store có quyền truy cập, không đưa thành metric label cho mọi message.

### Structured log ví dụ

~~~json
{
  "event": "mail_submission_failed",
  "notificationId": "notif-184",
  "attemptId": "attempt-3",
  "providerKey": "smtp-primary",
  "smtpPhase": "AUTH",
  "category": "SMTP_AUTH",
  "smtpCode": "535",
  "secretGeneration": "g42",
  "retryable": false
}
~~~

Đây là log minh họa, không phải format sẵn có của Jakarta Mail. Chỉ ghi metadata cần điều tra; không copy SMTP transcript chứa credentials, body hoặc danh sách recipient vào dashboard/tracing công khai.

## 12. Thiết lập alert và định nghĩa phục hồi

### Các alert hữu ích

| Alert | Tín hiệu | Đầu mối |
| --- | --- | --- |
| SMTP AUTH spike | Lỗi AUTH tăng nhanh trên cùng account | Mail ops + secret owner |
| TLS handshake failures | Tỷ lệ lỗi TLS tăng sau deploy/cert rotation | Platform/network/security |
| DNS resolution failures | NXDOMAIN/SERVFAIL/timeout từ app | Platform/DNS/network |
| Secret expires soon | Credential gần hết hạn và chưa có version mới active | Secret owner |
| TLS cert expires soon | Certificate active gần hết hạn | Owner TLS endpoint |
| Email backlog SLA breach | Oldest age vượt SLA theo category | Mail ops + business owner |
| Too many unknown submissions | Nhiều attempt mất final reply | Mail ops/provider |
| Provider 4xx throttling | Deferred hoặc SMTP temporary error tăng | Mail ops/provider |

### Tránh alert nhiễu

Một lần temporary DNS timeout không nhất thiết là incident P1. Alert nên dựa trên:

- Số lượng tuyệt đối và tỷ lệ trên mẫu đủ lớn.
- Số cluster/instance bị ảnh hưởng.
- Khả năng giao mail giao dịch/OTP.
- Tốc độ tăng backlog và tuổi message cũ nhất.
- Provider degradation hoặc recent change.
- Sự lặp lại liên tục trong một thời gian đáng kể.

Một email OTP quá SLA có thể nghiêm trọng hơn hàng nghìn email marketing bị trì hoãn. Đặt ngưỡng theo loại notification và mục đích nghiệp vụ.

### Tiêu chí xác minh sau khắc phục

Không đóng incident chỉ vì alert biến mất. Nên xác nhận:

1. DNS resolve và TCP connect ổn định từ workload thật.
2. TLS handshake qua hostname và truststore đúng.
3. SMTP AUTH hoặc mechanism được provider chấp nhận.
4. Canary SMTP submission thành công.
5. Provider event (nếu có) tiếp tục hoạt động.
6. Error rate thực giảm trong nhiều cửa sổ quan sát.
7. Backlog giảm, OTP/giao dịch còn hạn được xử lý.
8. Không còn credential/certificate config tạm thời làm yếu bảo mật.
9. Không có nhiều record SUBMISSION_UNKNOWN bị resend mù.
10. Change/audit và hành động tiếp theo đã được ghi nhận.

## 13. Bảo vệ transactional outbox khi SMTP gặp sự cố

Trong hệ thống giao dịch, sự cố AUTH/TLS/DNS không nên làm mất dữ liệu nghiệp vụ hoặc chặn database transaction trong thời gian chờ mạng.

### Tách ghi dữ liệu và gửi email

~~~text
Order/payment/signup transaction
      |
      +-- Save business data
      +-- Save email outbox request
      |
      v
     COMMIT
      |
      v
Mail dispatcher
      |
      +-- Check expiry, consent, suppression
      +-- Acquire concurrency + rate budget
      +-- Submit via JavaMailSender
      |
      +-- SUBMITTED
      +-- RETRY_PENDING
      +-- WAITING_FOR_CREDENTIAL
      +-- SUBMISSION_UNKNOWN
      +-- FAILED_PERMANENT / EXPIRED
~~~

Không gọi SMTP blocking trong một transaction database dài. Mail server không tham gia transaction ACID cùng database: nếu relay đã accepted email nhưng database rollback, email có thể vẫn đến dù nghiệp vụ bị hủy.

### Các trạng thái cần phân biệt

| Trạng thái ứng dụng | Ý nghĩa | Có thể scheduler gửi ngay? |
| --- | --- | --- |
| `PENDING` | Đã lưu yêu cầu, chưa bắt đầu | Có, nếu đủ điều kiện và quota |
| `PROCESSING` | Worker đã claim với lease | Không claim trùng khi lease hợp lệ |
| `RETRY_PENDING` | Lỗi tạm thời, chờ `nextAttemptAt` | Chỉ khi đến hạn |
| `WAITING_FOR_CREDENTIAL` | Đường gửi đang bị chặn vì AUTH/secret | Không cho tới khi credential hợp lệ |
| `SUBMITTED` | Relay chấp nhận theo phản hồi ứng dụng nhận | Không retry tự động |
| `SUBMISSION_UNKNOWN` | Không biết chắc relay đã nhận hay chưa | Không retry mù |
| `FAILED_PERMANENT` | Lỗi hiện tại không nên retry như transient | Chỉ replay sau khi điều tra |
| `EXPIRED` | Nội dung/token không còn hiệu lực | Không |
| `SUPPRESSED` | Không được gửi theo consent/bounce/complaint | Không |

Đây là mô hình minh họa do ứng dụng định nghĩa, không phải trạng thái cung cấp sẵn bởi Spring Mail.

### AUTH/TLS/DNS lỗi trước submit

Nếu DNS không resolve hoặc TLS handshake thất bại trước khi có bất kỳ SMTP DATA, ứng dụng có cơ sở để biết **lần thử đó chưa submit message tới relay**. Nó có thể đặt lại lịch thử khi hạ tầng phục hồi, miễn là không vượt expiry, rate limit và retry budget.

Với AUTH failure trên cùng tài khoản, chính sách phù hợp thường là giữ hàng đợi và chặn provider lane cho tới khi sửa credential, thay vì tăng `attempts` cho mọi job vô hạn.

### Không chắc chắn sau DATA

~~~text
Application                     SMTP relay
    |-------- DATA body --------->|
    |-------- end marker -------->|
    |                              | Relay có thể đã nhận
    |<-- final response lost ------X
    |
    v
SUBMISSION_UNKNOWN
~~~

Trường hợp này không phải lỗi DNS/TLS/AUTH điển hình, nhưng rất quan trọng khi khôi phục backlog sau một incident mạng. Nếu cứ reset mọi `PROCESSING` hoặc `FAILED` record về `PENDING`, có thể gửi lại email đã được relay chấp nhận.

Cần giữ attempt ID, provider correlation ID nếu có, thời điểm gửi và trạng thái. Nếu provider có event API/relay logs, tiến hành reconciliation; nếu không, dùng policy được duyệt về rủi ro duplicate. `Message-ID` hỗ trợ truy vết nhưng không bảo đảm exactly-once SMTP delivery.

### Retry và khôi phục theo ngân sách

- Exponential backoff với jitter cho lỗi có khả năng phục hồi.
- Số attempts và tuổi tối đa của notification.
- Giới hạn tốc độ toàn provider/account, không chỉ mỗi instance.
- Giới hạn số SMTP send đang in-flight.
- Lịch retry được lưu trong outbox bền vững, không giữ thread ngủ.
- Khi circuit breaker đóng lại, drain backlog theo quota, không xả toàn bộ ngay.
- Email OTP/security còn hạn được ưu tiên hơn chiến dịch tùy chọn.
- Message marketing đã hết campaign hoặc recipient đã unsubscribe phải được suppress/expire.

Một sự cố DNS 15 phút có thể khiến nhiều job cùng đến hạn sau khi DNS khôi phục. **Khôi phục hạ tầng là một bước; kiểm soát nhịp gửi bù là bước tiếp theo.**

## 14. Định vị sự cố từ exception Spring Mail

Spring Mail có nhiều subclass của `MailException`; Jakarta Mail và các thư viện networking có thêm exception bên dưới. Runbook nên thu thập cause chain đã **loại bỏ dữ liệu nhạy cảm**, rồi phân loại ở một adapter riêng.

### Các exception thường gặp

| Exception/type | Có thể gợi ý |
| --- | --- |
| `MailAuthenticationException` | AUTH thất bại theo cơ chế Spring Mail |
| `MailSendException` | Một hoặc nhiều message không gửi được |
| `MailParseException` | Lỗi cấu trúc/parse message |
| `MailPreparationException` | Lỗi trong quá trình chuẩn bị email |
| `MessagingException` | Lỗi Jakarta Mail, cần xem nested cause/phase |
| `UnknownHostException` | Resolver không tìm được host hoặc lookup fail |
| `ConnectException` | Kết nối bị từ chối hoặc lỗi connect khác |
| `SocketTimeoutException` | Một thao tác socket chờ quá hạn |
| `SSLHandshakeException` | TLS handshake không hoàn tất, nhiều nguyên nhân |

Không phân loại chỉ từ tên exception. Ví dụ `SocketTimeoutException` có thể xảy ra khi chờ greeting, AUTH response hoặc final DATA response. Hậu quả retry khác nhau. Nếu transport wrapper không biết phase, ứng dụng cần coi kết quả là **chưa đủ chắc chắn** thay vì tự suy đoán “chưa gửi”.

### Một cách biểu diễn kết quả phân loại

~~~java
public enum RecoveryDecision {
    RETRY_WITH_BACKOFF,
    PAUSE_PROVIDER_LANE,
    FIX_TLS_OR_DNS_CONFIG,
    FIX_RECIPIENT_OR_CONTENT,
    RECONCILE_UNKNOWN,
    HOLD_EXPIRED_OR_SUPPRESSED
}

public record MailIncidentClassification(
        MailFailureCategory category,
        RecoveryDecision decision,
        String sourceProvider,
        String smtpPhase,
        String sanitizedDiagnosticCode) {
}
~~~

Các kiểu trên dành cho tầng ứng dụng. Không cần dùng đủ mọi field trong mọi exception; nếu phase không được biết, phải phản ánh thiếu thông tin thay vì điền một giá trị dự đoán.

### Không in SMTP transcript thô

Ghi SMTP protocol debug ở mức thấp đôi khi hữu ích trong môi trường cô lập, nhưng có thể lộ username, AUTH exchange, recipient hoặc message body. Đối với production:

- Ưu tiên log structured chỉ gồm provider, phase, category, code, attempt ID.
- Làm sạch text từ exception trước khi lưu.
- Không bật `mail.debug=true` kéo dài nếu chưa rà soát dữ liệu được phát ra.
- Không ghi nguyên văn `spring.mail.password`, OAuth access token hoặc nội dung email.
- Dùng quyền truy cập đặc biệt/retention ngắn với support bundle cần điều tra sâu.

## 15. Chẩn đoán có kiểm soát bằng các công cụ phổ biến

Các lệnh dưới đây chỉ là ví dụ chẩn đoán. Không giả định một công cụ luôn được cài sẵn trong container; không cài tùy tiện vào image production nếu chính sách không cho phép. Có thể chạy qua pod diagnostic có cùng DNS/network path và quyền hợp lệ.

### 15.1. Xác định DNS và TCP

Windows PowerShell:

~~~powershell
Resolve-DnsName smtp.example.net -Type A
Resolve-DnsName smtp.example.net -Type AAAA
Test-NetConnection smtp.example.net -Port 587
~~~

Linux với các công cụ đã được cài:

~~~bash
getent ahosts smtp.example.net
dig smtp.example.net A
dig smtp.example.net AAAA
~~~

Nếu `Test-NetConnection` báo TCP connect thành công, vẫn chưa thể kết luận TLS/AUTH thành công. Nếu `dig` trả A record, vẫn chưa thể kết luận firewall mở.

### 15.2. Kiểm tra TLS và certificate

STARTTLS:

~~~bash
openssl s_client -starttls smtp \
  -connect smtp.example.net:587 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net
~~~

Implicit TLS:

~~~bash
openssl s_client \
  -connect smtp.example.net:465 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net
~~~

Lệnh không cần username/password; không dán credential vào session để “thử AUTH” trong một terminal có lịch sử/log chung. Để xác thực, dùng canary application/secret integration đã được kiểm soát.

### 15.3. Kiểm tra sender DNS

~~~bash
dig example.net TXT
dig mail2026._domainkey.example.net TXT
dig _dmarc.example.net TXT
~~~

Chỉ query DKIM selector thực tế đã được ứng dụng/provider sử dụng, không đoán giá trị `mail2026`. Có thể dùng header `DKIM-Signature` của một email thử để xác định selector, nếu được phép xem email đó.

### 15.4. Kiểm tra resolver khác nhau

Nếu được phép truy vấn một DNS resolver cụ thể:

~~~bash
dig @192.0.2.53 smtp.example.net A
~~~

Địa chỉ `192.0.2.53` ở đây là IP documentation, không phải resolver vận hành thật. Thay bằng địa chỉ DNS server hợp lệ của môi trường đang điều tra. Tránh dùng public resolver làm đường vòng cho private DNS nếu điều đó vi phạm chính sách hoặc làm rò thông tin domain nội bộ.

### 15.5. Kiểm tra chứng chỉ từ phía JVM

Khi OpenSSL xác minh thành công nhưng Java vẫn báo PKIX:

- Ghi nhận JDK runtime version, truststore được chọn.
- Kiểm tra JVM system properties liên quan truststore **không in password**.
- Kiểm tra CA/intermediate trong truststore qua công cụ được phép.
- Xác minh JDK hostname verification/TLS protocol settings.
- Không dùng `TrustManager` chấp nhận mọi certificate để chạy production.

Một test tích hợp dùng `JavaMailSenderImpl.testConnection()` với cấu hình giống production nhưng endpoint canary là bằng chứng trực tiếp hơn về hành vi Java TLS so với một kết quả OpenSSL từ laptop.

## 16. Case study: một số tình huống sự cố thường gặp

### Tình huống 1 — Secret đã rotate, một pod vẫn dùng bản cũ

**Triệu chứng:** sau rotation, hai pod gửi thành công, một pod liên tục ghi AUTH 535. Tất cả cùng dùng SMTP host và TLS đúng.

**Cách điều tra:**

1. So sánh secret generation/rollout revision của từng pod.
2. Kiểm tra instance lỗi đã restart/rebind sender chưa.
3. Xác minh credential cũ có bị revoke trước khi pod cutover không.
4. Dừng dispatch ở pod cũ để không tạo AUTH storm.
5. Cập nhật sender/restart pod và xác minh canary.
6. Xác nhận toàn fleet dùng generation được duyệt rồi đóng incident.

**Không nên:** bật retry liên tục cho từng email hoặc đánh dấu tất cả recipient invalid.

### Tình huống 2 — Chứng chỉ relay mới nhưng pod dùng truststore cũ

**Triệu chứng:** OpenSSL trên workstation nhận chain hợp lệ, nhưng Java trong container báo `PKIX path building failed`.

**Cách điều tra:**

1. So sánh certificate chain từ đường mạng của pod và workstation.
2. Kiểm tra runtime/JDK và custom truststore.
3. Xem provider có thay intermediate/root CA gần đây không.
4. Kiểm tra load balancer có node chưa cập nhật certificate không.
5. Cập nhật truststore/CA theo quy trình bảo mật, rollout canary.
6. Không thêm trust-all hoặc tắt hostname verification.

**Điểm xác minh:** SMTP AUTH và submission bằng chính sender Java, không chỉ OpenSSL handshake.

### Tình huống 3 — SMTP hostname đổi IP, cache/resolver không đồng nhất

**Triệu chứng:** một region/pod bị timeout tới IP cũ, những pod khác gửi bình thường.

**Cách điều tra:**

1. Xác định hostname SMTP và kết quả A/AAAA ở từng region.
2. So sánh DNS resolver/TTL và thời điểm thay đổi.
3. Kiểm tra JVM DNS cache và connection reuse.
4. Kiểm tra route/firewall tới từng IP.
5. Sửa DNS/network hoặc rollout refresh theo kế hoạch.
6. Quan sát tỷ lệ thành công và backlog theo region.

**Không nên:** hardcode tạm một IP provider mà bỏ qua TLS hostname và failover.

### Tình huống 4 — SMTP AUTH thành công nhưng sender policy từ chối

**Triệu chứng:** `AUTH 235` thành công, nhưng server trả `553` hoặc `550/554` khi MAIL FROM.

**Cách điều tra:**

1. Xem địa chỉ envelope sender và header From.
2. Kiểm tra account có quyền gửi từ domain/identity đó không.
3. Xem provider verified identities và sender policy.
4. Kiểm tra DKIM/SPF/DMARC nếu reply cho biết liên quan.
5. Sửa quyền hoặc sender identity, gửi canary đúng From.

**Không nên:** rotate SMTP password nếu credential đang được chấp nhận mà lỗi thực nằm ở quyền gửi.

### Tình huống 5 — SPF/DKIM/DMARC lỗi sau đổi provider

**Triệu chứng:** ứng dụng `send()` thành công nhưng provider events cho biết remote recipient MX từ chối hoặc chuyển nhiều thư sang spam sau khi cutover.

**Cách điều tra:**

1. Xác định provider mới dùng sending IP/envelope MAIL FROM và DKIM signing domain nào.
2. Kiểm tra SPF TXT, DKIM selector TXT và DMARC record/alignment.
3. Xem kết quả authentication trong một email canary được phép.
4. Điều chỉnh DNS theo hướng dẫn provider và chính sách domain.
5. Theo dõi bounce/deferred/complaint và cohort trước/sau.

**Không nên:** tăng SMTP timeout hoặc thay password để sửa lỗi remote authentication.

### Tình huống 6 — TLS mismatch vì đổi sang port 465

**Triệu chứng:** trước đây dùng 587 + STARTTLS; sau khi cấu hình port 465, client không nhận 220 như kỳ vọng hoặc handshake lỗi.

**Cách điều tra:** xem provider 465 có implicit TLS không; nếu có, cấu hình `mail.smtp.ssl.enable=true` và hostname verification đúng; không dùng cùng bước STARTTLS trên endpoint implicit TLS nếu provider không hỗ trợ. Xác minh bằng OpenSSL ở mode phù hợp và Java canary.

### Tình huống 7 — DNS endpoint khỏe nhưng provider báo deferred

**Triệu chứng:** ứng dụng resolve SMTP host, AUTH và submit đều thành công; nhiều event `DEFERRED` xuất hiện theo một recipient domain.

**Cách điều tra:** kiểm tra provider queue/remote MX, SMTP 4xx, rate/throttling theo domain, DNS recipient MX nếu có lý do phù hợp. Không tự tạo message mới khi provider đang retry delivery. Đây là **vấn đề downstream**, không phải DNS endpoint mà ứng dụng dùng để connect.

### Tình huống 8 — Mất phản hồi sau DATA trong sự cố mạng

**Triệu chứng:** worker nhận `IOException` sau khi gửi xong body; outbox chưa được đánh dấu SUBMITTED.

**Cách điều tra:** xác định SMTP phase, kiểm tra relay log/provider ID nếu có, giữ trạng thái `SUBMISSION_UNKNOWN`, không replay hàng loạt. Nếu provider đã accepted, cập nhật theo bằng chứng; nếu không thể đối soát, áp dụng quy trình risk-based resend có audit.

## 17. Kiểm thử runbook trong môi trường cô lập

Runbook không chỉ dùng khi production đã lỗi. Nên có bài diễn tập với SMTP fake/relay test và hạ tầng network/DNS có kiểm soát.

| ID | Tình huống diễn tập | Cần chứng minh |
| --- | --- | --- |
| R01 | Credential sai hoặc bị revoke | AUTH failure được phân loại, lane tạm dừng, không retry storm |
| R02 | Secret mới chỉ cập nhật trên một phần pod | Version drift được phát hiện; rotation có thể hoàn tất |
| R03 | OAuth2 token hết hạn | Refresh trước hạn, không gọi token endpoint theo từng email |
| R04 | SMTP yêu cầu STARTTLS nhưng không advertise | Client fail closed, không gửi plaintext |
| R05 | TLS certificate sai hostname | Hostname verification từ chối |
| R06 | Certificate chain thiếu intermediate | Java trust validation thất bại, có lộ trình sửa an toàn |
| R07 | SMTP 465/587 bị cấu hình sai mode | Phân loại transport mode mismatch |
| R08 | DNS SMTP endpoint NXDOMAIN | Worker không cố suppress recipient; outbox chờ |
| R09 | DNS SERVFAIL/timeout | Backoff và resolver diagnostics đúng scope |
| R10 | A/AAAA trả IP không route được | Phân biệt DNS resolved với TCP unavailable |
| R11 | CNAME alias không có SAN phù hợp | Không tắt TLS hostname verification |
| R12 | Recipient MX bị lỗi sau submit | Theo dõi provider deferred/bounce, không tự resend |
| R13 | DKIM selector DNS sai | Không tuyên bố submission failure; điều tra downstream authentication |
| R14 | Outbox backlog lớn sau phục hồi | Drain rate-limited, ưu tiên email còn hạn |
| R15 | Worker restart trong incident | Trạng thái/nextAttemptAt sống qua restart |
| R16 | Mất final reply sau DATA | Không retry mù, có trạng thái unknown |
| R17 | TestConnection bị gọi dồn dập | Health probe có giới hạn, không tạo auth storm |
| R18 | Logging khi AUTH/TLS lỗi | Không lộ secret, token, body, recipient PII |

Các bài test cần dùng fake server/fault injection trong test environment, không chủ động tạo từ chối hàng loạt trên provider production. Nếu test mang tính unit/mock, ghi rõ phạm vi; một mock `MailAuthenticationException` không chứng minh TLS handshake hoặc provider AUTH protocol thật đã hoạt động.

### Kiểm tra khôi phục sau diễn tập

Sau khi giả lỗi đã được tắt, cần chứng minh:

1. Canary qua đúng route thành công.
2. Outbox messages còn nguyên, các status hợp lệ.
3. Không có retry loop với delay bằng 0.
4. Không bị lộ secret qua debug logs.
5. Concurrency slot/SMTP socket được giải phóng khi gửi lỗi.
6. Secret/cert/DNS cấu hình cũ được dọn theo kế hoạch.
7. Metrics và alert chuyển từ failure sang recovered hợp lý.

Không coi việc `MailException` không còn xuất hiện trong một test ngắn là đủ; xem khả năng xử lý email tiếp theo và tốc độ giảm backlog.

## 18. Bảng thao tác nhanh cho người trực hệ thống

Khi một alert mới xuất hiện, có thể dùng bảng này để tránh đổi nhầm thành phần.

| Alert/triệu chứng | Kiểm tra ngay | Không nên làm | Tình trạng khôi phục cần thấy |
| --- | --- | --- | --- |
| AUTH 535 tăng mạnh | Secret version, account status, AUTH mechanism, last rotation | Retry từng email không giới hạn, in secret | Canary AUTH/submission thành công, fleet dùng credential hợp lệ |
| STARTTLS required | Host/port, EHLO capability, proxy, TLS mode | Tắt STARTTLS bắt buộc | TLS negotiation được xác minh, AUTH bảo mật |
| PKIX path building failed | Server certificate chain, Java truststore, CA rotation | Trust-all hoặc tắt check | Java TLS handshake và hostname verification hợp lệ |
| Certificate hostname mismatch | SAN, hostname, SNI, alias DNS, load balancer | Kết nối bằng IP và bỏ qua validation | Hostname certificate khớp cấu hình |
| TLS protocol mismatch | JDK security policy, relay TLS versions | Bật cipher yếu tùy tiện | Client/server thương lượng TLS được phê duyệt |
| SMTP host NXDOMAIN | Giá trị `spring.mail.host`, DNS resolver, record A/AAAA | Sửa MX người nhận thay vì host relay | Resolve được từ workload, sau đó TCP/TLS/AUTH pass |
| DNS timeout/SERVFAIL | DNS service, firewall tới resolver, CoreDNS, network | Gọi là “recipient invalid” | DNS resolution ổn định, error rate giảm |
| TCP connect refused | SMTP listener, port, egress policy | Tăng read timeout vô hạn | TCP connect vào endpoint đúng |
| Mail submit OK nhưng bounce tăng | Provider event, SPF/DKIM/DMARC, recipient quality | Reset secret khi AUTH đang OK | Nguyên nhân downstream được xử lý, cohort mới tốt lên |
| Provider deferred tăng | MX nhận, SMTP 4xx, provider queue, rate | Resend mỗi deferred event | Queue/retry provider bình thường, kết quả cuối được theo dõi |
| Backlog tăng sau outage | Outbox age, limiter, workers, provider health | Xả toàn bộ không giới hạn | Backlog giảm đều trong quota, không có duplicate spike |

### Một mẫu ticket incident ngắn

~~~text
Incident ID:
Started at / timezone:
Environment / cluster:
Affected notification categories:
SMTP provider/account key:
SMTP host/port/TLS mode (no secrets):
First observed failure category:
SMTP reply / enhanced code / phase (sanitized):
Affected instances / regions:
Current outbox pending + oldest age:
Recent deploy / DNS / certificate / secret changes:
Mitigation taken:
Canary result:
Risk of SUBMISSION_UNKNOWN:
Recovery metrics:
Remaining blockers:
Owner / next update:
~~~

Mẫu này không yêu cầu người trực ghi recipient email đầy đủ hoặc mật khẩu. Nếu cần dữ liệu cá nhân để điều tra, dùng một record ID nội bộ và công cụ truy cập được phân quyền.

## 19. Vai trò và giao tiếp trong incident

Lỗi SMTP thường cần phối hợp nhiều nhóm. Khi không rõ ai sở hữu vấn đề, việc thay đổi tản mạn có thể làm incident kéo dài.

| Vai trò | Trách nhiệm gợi ý |
| --- | --- |
| Incident commander/on-call | Khoanh vùng, quyết định mức độ, điều phối thay đổi và cập nhật trạng thái |
| Application/mail worker owner | Outbox, retry, JavaMailSender config, lỗi ứng dụng và bảo vệ SLA |
| Platform/network | DNS resolver, firewall, route, egress proxy, Kubernetes networking |
| Security/secret owner | SMTP credential, OAuth2, certificate trust và thu hồi khẩn cấp |
| SMTP/provider admin | SMTP endpoint, account/From permission, quota, relay queue và provider incident |
| Domain/DNS owner | SPF/DKIM/DMARC, MX, records/TTL, DNS change và rollback |
| Business/product owner | Ưu tiên loại email, nội dung hết hạn và truyền thông người dùng |

Một tổ chức nhỏ có thể có một người đảm nhiệm nhiều vai trò. Điều quan trọng là **runbook phải ghi rõ owner, nguồn dữ liệu và quyền phê duyệt** cho các thay đổi nhạy cảm như revoke secret, đổi SPF/DMARC, mở provider failover hoặc dừng toàn bộ mail lane.

### Giao tiếp khi chưa biết nguyên nhân

Thay vì nói “SMTP down”, nên báo một trạng thái có thể xác minh:

> Từ 09:20 UTC, worker ở region A có tỷ lệ SMTP AUTH failure tăng sau rotation credential. Outbox giao dịch còn nguyên; lane của account bị ảnh hưởng đang tạm dừng để tránh retry storm. Đang xác minh secret version trên các instance và canary trên credential mới.

Khi xác định là TLS hoặc DNS, thay nội dung theo bằng chứng. Không hứa chắc thời gian khôi phục hoặc số email đã delivered khi dữ liệu chỉ chứng minh submission accepted.

## 20. Kiểm soát thay đổi và rollback

Trong quá trình xử lý incident, mỗi thao tác nên có giả thuyết và phương án xác minh. Ví dụ:

| Thay đổi | Điều cần xác minh trước | Rủi ro khi rollback |
| --- | --- | --- |
| Đổi SMTP secret | Credential mới hợp lệ, quyền gửi và mọi workload đã được thống kê | Credential cũ có thể đã revoke |
| Đổi `spring.mail.host` | DNS endpoint, TLS hostname, account region/quota | Endpoint cũ có thể không còn hoạt động |
| Đổi port/TLS mode | Provider hỗ trợ đúng mode và certificate | Có thể làm AUTH đi trên đường không bảo mật nếu cấu hình sai |
| Cập nhật Java truststore | CA chain được phê duyệt, ảnh hưởng tới các service khác | Truststore cũ có thể thiếu CA mới |
| Đổi DNS A/CNAME | Endpoint đích, TTL, SNI và network route | Cache không đồng bộ, rollback không tức thời |
| Đổi SPF/DKIM/DMARC | Source identity và alignment thực tế, mức bảo vệ mong muốn | Record cũ có thể gây reject hoặc downgrade policy |
| Tăng retry/concurrency | Provider quota và nguyên nhân lỗi | Có thể gây bão gửi |
| Chuyển provider dự phòng | From identity, quota, authentication và suppression | Message unknown/duplicate khi route lại |

### Một thay đổi tại một thời điểm khi có thể

Nếu cùng lúc thay DNS hostname, password và TLS truststore, rất khó biết điều gì thực sự giải quyết lỗi hoặc tạo lỗi mới. Có thể cần nhiều thay đổi trong incident nghiêm trọng, nhưng mỗi thay đổi nên:

1. Có giả thuyết rõ.
2. Có owner/phê duyệt tương ứng.
3. Có snapshot cấu hình không chứa secret.
4. Có canary sau thay đổi.
5. Có telemetry đủ để so sánh trước/sau.
6. Có phương án rollback hoặc roll-forward thực tế.

Đặc biệt với secret đã bị thu hồi, **roll forward** bằng credential mới là lựa chọn đúng hơn cố quay lại bản cũ.

## 21. Post-incident review

Sau khi mail lane phục hồi, cần xem cả nguyên nhân gốc lẫn khả năng phòng ngừa tái diễn.

### Những câu hỏi hậu kiểm

- Alert phát hiện lỗi trước hay sau khi khách hàng báo?
- Có biết rõ sự cố nằm ở DNS/TCP/TLS/AUTH trong những phút đầu không?
- Log và metric có đủ correlation, SMTP phase, category mà không lộ secret không?
- Có gần đây thay DNS, JDK, TLS certificate, SMTP account hoặc OAuth2 policy không?
- Có quy trình rotation và expiry monitoring trước hạn không?
- Test staging có mô phỏng loại lỗi này chưa?
- Outbox có giữ được yêu cầu gửi trong thời gian outage không?
- Có trường hợp bị gửi trùng vì unknown outcome hoặc retry nhiều lớp không?
- Backlog được drain đúng rate limit không?
- Email hết hạn/recipient đã unsubscribe có bị gửi sau phục hồi không?
- Cần sửa runbook, alert threshold, owner hoặc cấu hình canary nào?

### Đầu ra mong muốn

- Timeline sự cố và thay đổi.
- Impact theo category, provider và region.
- Root cause được chứng minh hoặc ghi rõ phần chưa đủ bằng chứng.
- Các biện pháp đã thực hiện, hiệu quả/giới hạn.
- Kế hoạch hành động có owner và hạn hoàn thành.
- Bổ sung test trong môi trường cô lập để tái hiện.
- Cập nhật quy trình secret/certificate/DNS change nếu có.

Không đóng sự cố bằng kết luận “email đã hoạt động lại” mà không đánh giá các message còn pending, unknown, bounced hoặc expired.

## 22. Câu hỏi tự kiểm tra

**1. Khi thấy `UnknownHostException` cho SMTP hostname, có nên sửa MX của người nhận ngay không?**

Không. Đây là vấn đề phân giải tên endpoint mà ứng dụng kết nối. Kiểm tra `spring.mail.host`, resolver và A/AAAA/CNAME của SMTP relay trước.

**2. Vì sao `Test-NetConnection` thành công chưa chứng minh SMTP hoạt động?**

Vì nó chủ yếu kiểm tra TCP connectivity. SMTP greeting, STARTTLS, TLS certificate, AUTH, sender permission và DATA là các bước khác.

**3. SMTP 535 có luôn nghĩa password đã hết hạn không?**

Không. Có thể sai credential, app password bị thu hồi, account bị khóa, OAuth2 grant/scope sai hoặc cơ chế AUTH không tương thích. Cần xem provider reply và lịch thay đổi.

**4. Có nên retry mọi email liên tục khi AUTH 535 xảy ra diện rộng không?**

Không. Lỗi account chung có thể gây bão xác thực. Tạm dừng provider lane, giữ outbox và khôi phục credential/quyền trước.

**5. Thay secret trong vault có tự thay username/password trên JavaMailSenderImpl đang chạy không?**

Không có bảo đảm mặc định. Cần restart, cơ chế refresh đã kiểm thử hoặc thay sender an toàn.

**6. STARTTLS và implicit TLS khác nhau điểm nào?**

STARTTLS bắt đầu bằng SMTP plaintext rồi nâng cấp sang TLS sau EHLO; implicit TLS thiết lập TLS ngay sau TCP connect trước SMTP greeting.

**7. Vì sao không dùng `mail.smtp.ssl.trust=*` trong production?**

Vì nó có thể làm suy yếu kiểm tra certificate và cho phép kết nối tới endpoint không đáng tin; cần sửa CA chain/truststore đúng cách.

**8. OpenSSL kết nối được nhưng Java báo PKIX thì kiểm tra gì?**

Java truststore, JDK version, CA/intermediate chain và đường network/SNI mà JVM thật sự dùng. OpenSSL và Java có thể dùng trust anchor khác nhau.

**9. Certificate hostname mismatch nên sửa thế nào?**

Đảm bảo hostname client dùng được chứng chỉ bao phủ trong SAN và đúng endpoint/SNI. Không tắt hostname verification.

**10. Có nên sửa lỗi TLS bằng cách chuyển từ port 587 sang 25?**

Không tự ý. Cần biết mode/provider hỗ trợ và chính sách bảo mật. Đổi port tùy tiện có thể phá route hoặc hạ cấp TLS.

**11. NXDOMAIN và SERVFAIL giống nhau không?**

Không. NXDOMAIN nói tên không tồn tại theo view resolver; SERVFAIL thể hiện resolver/authoritative lookup gặp lỗi xử lý. Cách điều tra khác nhau.

**12. Vì sao một pod lỗi DNS nhưng pod khác không?**

Có thể khác resolver, node, cache TTL, split-horizon view, region, network policy hoặc thời điểm cập nhật DNS.

**13. SPF/DKIM/DMARC sửa lỗi gì?**

Chúng liên quan xác thực domain người gửi và chính sách nhận thư downstream; không tự sửa lỗi DNS lookup của SMTP relay hostname.

**14. Nếu SMTP `send()` thành công thì có thể kết luận mail đã tới inbox không?**

Không. Nó chỉ cho biết relay đã accepted theo kết quả submission. Delivery đến mailbox cần tín hiệu downstream.

**15. Khi provider báo DEFERRED, ứng dụng có nên gửi lại email ngay không?**

Thường không, nếu provider đã accepted và đang tự retry. Cần biết ranh giới trách nhiệm để tránh gửi trùng.

**16. Khi mất final reply sau DATA, nên ghi trạng thái gì?**

Có thể là `SUBMISSION_UNKNOWN` nếu không thể biết relay đã chấp nhận hay chưa; cần đối soát hoặc chính sách duplicate trước khi retry.

**17. Ba SMTP timeout có tạo deadline tổng cho `send()` không?**

Không nhất thiết. Chúng giới hạn các thao tác socket khác nhau và phiên SMTP có nhiều bước; cần quản lý tổng deadline ở tầng worker khi cần.

**18. Vì sao không gọi `testConnection()` trong mọi readiness probe?**

Hàng trăm pod gọi liên tục có thể tạo connection/auth storm khi provider yếu, và SMTP outage có thể làm cả web tier bị đánh dấu unhealthy dù còn chức năng khác.

**19. Khi SMTP credential bị lộ, có thể chờ hết giờ cao điểm mới revoke không?**

Không có một quy tắc chung. Đây là incident security; đánh giá mức độ lộ, tuân thủ quy trình thu hồi khẩn cấp và bảo vệ dịch vụ bằng outbox/credential mới. Không ưu tiên uptime bằng cách tiếp tục dùng secret đã biết bị khai thác.

**20. Sau khắc phục, chỉ thấy AUTH failure giảm có đủ đóng incident không?**

Không. Cần canary, kiểm tra TLS/DNS, tuổi backlog, email còn hạn, unknown outcomes và điều kiện giao thư theo SLA.

## Kết luận

**Runbook cho lỗi xác thực, TLS và DNS trong Spring Framework Mail phải bắt đầu bằng việc xác định lỗi ở đúng lớp: DNS của SMTP endpoint, TCP, TLS/certificate, SMTP AUTH, sender policy hay chuyển phát downstream.** Người trực cần có bảng phân loại nhanh, bằng chứng từ đúng workload, lệnh kiểm tra DNS/TLS an toàn, metadata secret và cơ chế quan sát SMTP phase. Khi credential sai hoặc TLS không hợp lệ, hãy tạm dừng lane gửi và giữ outbox, không tắt bảo mật để “cho gửi được”. Khi DNS gặp lỗi, phân biệt resolver, A/AAAA, MX recipient và SPF/DKIM/DMARC; không sửa nhầm record. Mọi khôi phục phải được kiểm chứng bằng canary, metric, trạng thái job và tốc độ drain backlog; retry/replay vẫn qua giới hạn tốc độ và phải thận trọng với kết quả submit không xác định sau DATA. **Một runbook hiệu quả không chỉ chữa lỗi hiện tại mà còn giúp giảm thời gian xác định nguyên nhân, tránh gửi trùng, bảo vệ dữ liệu người nhận và ngăn sự cố tái diễn.**
