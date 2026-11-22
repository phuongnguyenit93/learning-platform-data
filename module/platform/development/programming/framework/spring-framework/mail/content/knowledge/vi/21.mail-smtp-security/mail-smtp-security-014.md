# Đánh giá rủi ro khi log SMTP debug

Khi email không gửi được, việc bật **SMTP debug** có vẻ là cách nhanh nhất để tìm nguyên nhân. Nhật ký giao thức có thể cho biết client đã kết nối đến host nào, server quảng bá extension gì sau EHLO, STARTTLS có được thực hiện không, AUTH có bị từ chối không và server trả mã lỗi gì ở các bước MAIL FROM, RCPT TO hoặc DATA.

Tuy nhiên, **SMTP debug cũng là một nguồn rò rỉ dữ liệu nhạy cảm**. Một bản transcript quá chi tiết có thể chứa địa chỉ người nhận, tài khoản gửi, tên miền nội bộ, thông điệp lỗi do server trả về, metadata của email, thông tin xác thực hoặc thậm chí nội dung thư tùy provider, phiên bản và cách cấu hình logging. Khi log được đẩy sang hệ thống thu thập tập trung, xuất ra stdout của container, lưu trong CI artifact hoặc chia sẻ trong ticket, phạm vi tiếp cận dữ liệu có thể rộng hơn nhiều so với hệ thống email ban đầu.

Với Spring Framework Mail, cần phân biệt **Jakarta Mail protocol debug**, **logging của Spring/application** và **JSSE/TLS handshake debug**. Mỗi nguồn cung cấp thông tin và tạo rủi ro khác nhau. Việc kết nối SMTP qua TLS **không bảo vệ những bản sao dữ liệu được ứng dụng ghi ra log**.

Nguyên tắc triển khai an toàn:

- **Tắt transcript SMTP debug ở production theo mặc định**.
- Chỉ bật chẩn đoán chi tiết khi có mục đích cụ thể, phạm vi hẹp, quyền truy cập hạn chế và thời hạn kết thúc.
- Không bật tùy chọn ghi lộ AUTH credentials hoặc OAuth tokens.
- Ưu tiên **structured log theo danh sách trường cho phép** thay vì ghi raw transcript.
- Không đưa MIME body, attachment, password reset link, OTP hoặc dữ liệu khách hàng vào log.
- Giới hạn retention, phân quyền, mã hóa và khả năng sao chép sang hệ thống quan sát.
- Khi nghi ngờ đã rò rỉ, xử lý log như một sự cố dữ liệu và thu hồi/đổi credential nếu cần.

Bài học trình bày cách nhận diện, đánh giá và giảm rủi ro log SMTP debug trong ứng dụng Spring Mail, cùng ví dụ cấu hình và quy trình điều tra sự cố có kiểm soát.

## 1. SMTP debug là gì?

SMTP là giao thức dựa trên chuỗi lệnh và phản hồi. Khi ứng dụng dùng **JavaMailSender**, Jakarta Mail transport thực hiện các bước như:

~~~text
Application                         SMTP server
     |                                   |
     |------------- TCP connect ------->|
     |<------------- 220 ---------------|
     |------------- EHLO -------------->|
     |<---------- 250 extensions -------|
     |------------- STARTTLS ---------->|
     |<------------- 220 ---------------|
     |=========== TLS handshake ========|
     |------------- EHLO -------------->|
     |------------- AUTH -------------->|
     |------------- MAIL FROM --------->|
     |------------- RCPT TO ----------->|
     |------------- DATA -------------->|
     |------------- MIME content ------>|
     |<---------- Final response -------|
~~~

**Protocol debug** giúp quan sát một phần quá trình này. Dữ liệu hiện trong transcript cụ thể phụ thuộc Jakarta Mail provider, cấu hình debug, phương thức xác thực và luồng gửi.

### 1.1. Debug có ích ở những vấn đề nào?

Ví dụ:

- Ứng dụng kết nối sai SMTP host hoặc cổng.
- Server không công bố STARTTLS.
- TLS handshake hoặc xác minh certificate thất bại.
- Server không cho phép SMTP AUTH.
- Server từ chối envelope sender.
- Một recipient bị từ chối ở RCPT TO.
- Message bị từ chối tại DATA.
- Provider giới hạn tốc độ.
- Connection bị đóng giữa phiên.

Phần lớn những vấn đề này có thể chẩn đoán bằng **mã lỗi, giai đoạn SMTP và metadata** mà không cần lưu toàn bộ nội dung giao thức.

### 1.2. Debug không phải nguồn sự thật duy nhất

Một bản transcript từ phía client có thể chưa cho thấy diễn biến phía mail server sau khi chấp nhận message. Ngay cả khi ứng dụng thấy SMTP accepted, provider vẫn có thể bounce ở bước chuyển phát tiếp theo.

Tương tự, nếu kết nối bị đứt sau DATA nhưng trước khi response cuối đến client, ứng dụng có thể không biết message đã được chấp nhận hay chưa. Một transcript không đầy đủ không đủ để tuyên bố chắc chắn “chưa gửi”.

## 2. Ba nguồn log thường bị nhầm lẫn

| Nguồn | Cách kích hoạt thường gặp | Nội dung có thể xuất hiện | Phạm vi cần kiểm soát |
| --- | --- | --- | --- |
| **Jakarta Mail debug** | mail.debug hoặc Session.setDebug(...) | SMTP command/response, trạng thái provider; chi tiết phụ thuộc implementation | Session, transport và luồng stdout/debug stream |
| **Spring/application logging** | SLF4J, Logback, Spring Boot logging.level | Exception, event ID, metadata do code chủ động log | Logger, ứng dụng, log pipeline |
| **JSSE/TLS debug** | JVM property javax.net.debug | TLS handshake, certificate, protocol, cipher và có thể thêm dữ liệu nhạy cảm tùy debug mode | Thường ảnh hưởng rộng tới kết nối TLS trong JVM |

Ba cơ chế không thay thế nhau.

### 2.1. Jakarta Mail protocol debug

Ví dụ trong Spring Boot:

~~~yaml
spring:
  mail:
    properties:
      "[mail.debug]": "true"
~~~

Tùy provider, thông tin debug thường được ghi qua **Session debug output**, không nhất thiết đi qua logger SLF4J mà ứng dụng đã cấu hình.

Vì vậy, chỉ điều chỉnh:

~~~yaml
logging:
  level:
    org.springframework.mail: WARN
~~~

không bảo đảm tắt mọi thông tin do **mail.debug** phát ra. Cần kiểm soát cấu hình của Jakarta Mail Session và nơi debug stream được ghi.

### 2.2. Spring/application logging

Ví dụ:

~~~java
log.warn(
        "mail.send.failed eventId={} category={}",
        eventId,
        failureCategory
);
~~~

Application log có thể được thiết kế an toàn hơn vì developer chủ động quyết định trường nào được xuất. Nhưng nếu developer log thẳng **exception.getMessage()**, object MimeMessage hoặc request payload, ứng dụng vẫn có thể làm lộ dữ liệu.

### 2.3. JSSE/TLS debug

Ví dụ JVM option:

~~~text
-Djavax.net.debug=ssl,handshake
~~~

JSSE debug tập trung vào TLS handshake và certificate processing. Nó không phải transcript SMTP hoàn chỉnh. Một số mode chẩn đoán sâu hơn có thể làm lộ thông tin nhạy cảm về TLS hoặc vật liệu khóa; không nên kích hoạt rộng trong môi trường có người dùng thật.

Do đó, khi cần xem lỗi STARTTLS, chọn mức debug nhỏ nhất cần thiết và kiểm soát output của toàn JVM.

## 3. Các nhóm dữ liệu có thể bị lộ

Một bản SMTP transcript có thể chứa nhiều loại dữ liệu. Mức độ thực tế phụ thuộc provider và điểm log.

| Nhóm dữ liệu | Ví dụ | Rủi ro |
| --- | --- | --- |
| **Thông tin xác thực** | Username, AUTH payload, OAuth bearer token | Account bị chiếm quyền hoặc bị dùng gửi spam |
| **Địa chỉ liên hệ** | MAIL FROM, RCPT TO | Lộ danh sách khách hàng/người nhận |
| **Header message** | Subject, From, To, Message-ID | Lộ giao dịch, danh tính, chủ đề trao đổi |
| **Body** | Email giao dịch, HTML, plain text | Lộ dữ liệu nghiệp vụ hoặc cá nhân |
| **Attachment** | Hóa đơn, báo cáo, bảng lương | Lộ dữ liệu nhạy cảm với dung lượng lớn |
| **Link/token trong email** | Link khôi phục tài khoản, magic link | Có thể dẫn tới chiếm quyền tài khoản |
| **Metadata hạ tầng** | Hostname SMTP, port, IP, extension | Tiết lộ sơ đồ hệ thống hoặc thông tin vận hành |
| **Thông tin certificate/TLS** | SAN, chain, handshake data | Có thể tiết lộ cấu trúc PKI; một số chế độ debug sâu đặc biệt nhạy cảm |
| **Chẩn đoán provider** | Reply text, account/domain policy | Có thể chứa địa chỉ, domain hoặc tham chiếu nội bộ |
| **Correlation metadata** | Event ID, tenant ID, account alias | Vẫn cần bảo vệ nếu có thể liên kết tới cá nhân |

Không phải mọi SMTP debug luôn in đủ các dữ liệu trên. Khi đánh giá, phải xét **dữ liệu nào provider hiện tại thực sự xuất ra**, đồng thời không thiết kế policy dựa trên giả định rằng phiên bản provider tương lai cũng sẽ che mọi trường nhạy cảm.

## 4. Dữ liệu xác thực là rủi ro nghiêm trọng nhất

SMTP AUTH có thể dùng username/password, app password hoặc token theo các mechanism khác nhau.

Ví dụ khái niệm:

~~~text
C: AUTH PLAIN <base64-payload>
S: 235 Authentication successful
~~~

**Base64 là encoding, không phải mã hóa bảo mật.** Nếu một payload chứa credentials được in ra log, người có quyền đọc log có thể giải mã và lạm dụng credential.

### 4.1. AUTH PLAIN và AUTH LOGIN

Một số mechanism xác thực biểu diễn dữ liệu dưới dạng Base64. Không được suy luận rằng dữ liệu “trông như chuỗi khó đọc” là an toàn.

Không lưu:

- Username/password thực tế.
- App password.
- AUTH challenge/response mang thông tin đăng nhập.
- Base64 của thông tin xác thực.
- Header hoặc object chứa secrets.

### 4.2. OAuth2 và XOAUTH2

Nếu ứng dụng sử dụng OAuth2 cho SMTP, một access token vẫn là **bearer credential**. Người có token hợp lệ có thể dùng các quyền mà token mang lại trong thời hạn hiệu lực.

Không chỉ che password rồi cho phép raw OAuth2 token đi qua debug. Cần ngăn ghi cả token, refresh token và những payload xác thực có thể dùng lại.

### 4.3. Chế độ debug AUTH đặc biệt

Một số Jakarta Mail/SMTP provider có tùy chọn như **mail.debug.auth** ảnh hưởng việc in thông tin xác thực khi debug. Các chi tiết có thể khác theo implementation và phiên bản.

**Không bật cấu hình làm lộ AUTH transcript chỉ để chẩn đoán lỗi 535.** Kể cả khi một phiên bản có cơ chế mặc định che thông tin AUTH, vẫn phải xem đó là biện pháp hỗ trợ, không phải bảo đảm rằng raw debug hoàn toàn không có secrets.

### 4.4. Lỗi AUTH thường không cần credential trong log

Để điều tra:

~~~text
smtpAccountAlias=outbound-primary
phase=AUTH
smtpReplyCode=535
enhancedStatus=5.7.8
errorCategory=AUTH_REJECTED
~~~

Thông tin này thường hữu ích hơn việc lưu chính password sai hoặc OAuth token đã bị từ chối.

## 5. Rủi ro lộ địa chỉ người nhận

SMTP envelope bao gồm các lệnh như:

~~~text
MAIL FROM:<notifications@example.org>
RCPT TO:<customer01@example.net>
RCPT TO:<customer02@example.net>
~~~

Nếu transcript được ghi nguyên văn, hệ thống log có thể trở thành một kho dữ liệu chứa người nhận email.

### 5.1. Bcc vẫn có thể xuất hiện trong envelope

Một email có thể không chứa header Bcc trong MIME message được gửi đi, nhưng người nhận Bcc vẫn phải được chuyển cho SMTP server qua envelope recipient thích hợp.

Vì vậy, **xóa hoặc không log header Bcc không có nghĩa transcript SMTP đã ẩn được địa chỉ Bcc**. RCPT TO có thể làm lộ chúng.

### 5.2. Danh sách người nhận là dữ liệu có giá trị

Đối với hệ thống gửi thông báo giao dịch, danh sách RCPT TO có thể bộc lộ:

- Người dùng đang đăng ký dịch vụ.
- Quan hệ giữa khách hàng và sản phẩm.
- Tenant hoặc nhóm tổ chức.
- Thời điểm giao dịch.
- Những liên hệ không công khai.

Không cần nội dung body để một bản log SMTP gây ảnh hưởng đến quyền riêng tư.

### 5.3. Thay địa chỉ đầy đủ bằng tham chiếu

Nên log:

~~~text
recipientRef=customer-42
recipientCount=1
~~~

thay vì:

~~~text
recipientEmail=customer01@example.net
~~~

Nếu cần liên kết ổn định qua nhiều bản ghi, có thể dùng tokenization hoặc **HMAC với khóa bí mật được quản lý an toàn**. Hash email thông thường, không có secret, có thể bị dò bằng danh sách địa chỉ phổ biến và không phải biện pháp ẩn danh chắc chắn.

## 6. Rủi ro đối với Subject và nội dung email

Header **Subject** có thể chứa thông tin tài chính, y tế, pháp lý, trạng thái tài khoản hoặc mã đơn hàng. Body có thể mang thông tin chi tiết hơn.

Một ví dụ email giả định:

~~~text
Subject: Khôi phục mật khẩu
Body: Sử dụng liên kết https://example.org/reset?token=<secret-token>
~~~

Nếu body hoặc URL được ghi ra log, người đọc log có thể lấy token khôi phục tài khoản trước khi nó hết hạn. Điều này đặc biệt nguy hiểm khi log được gửi đến nền tảng giám sát với quyền đọc rộng.

### 6.1. Mã OTP và magic link

Không log:

- Mã OTP.
- Link reset password.
- Magic login URL.
- Token xác minh email.
- Mã truy cập một lần.
- Đường dẫn chứa signed query parameter nhạy cảm.

Giữ lại event ID và template key là đủ cho nhiều yêu cầu chẩn đoán.

### 6.2. HTML có thể chứa URL riêng tư

Một URL trong HTML email có thể mang recipient token, unsubscribe token, signed URL hoặc reference tới tài liệu cá nhân. Ngay cả khi phần chữ không nhạy cảm, toàn bộ HTML vẫn có thể chứa secret.

Không sao chép body HTML vào log chỉ vì nghĩ nó là template công khai.

### 6.3. Attachment có thể chứa dữ liệu nhạy cảm lớn

MIME message có thể chứa PDF, CSV, hình ảnh hoặc báo cáo. Trong một số kiểu capture/debug, raw content hoặc Base64 representation của attachment có nguy cơ bị lưu.

Base64 của PDF/CSV không được coi là đã che nội dung. Người có dữ liệu có thể giải mã để khôi phục attachment.

## 7. Rủi ro metadata dù không có body

Ngay cả transcript chỉ có SMTP command và response vẫn có thể tiết lộ:

- SMTP provider và host.
- Các domain liên quan.
- Thời điểm hệ thống gửi.
- IP hoặc thông tin route.
- Kết quả xác thực.
- Địa chỉ sender/recipient.
- Tốc độ gửi hoặc mô hình retry.
- Một số tên nội bộ trong certificate hoặc greeting.

Điều đó có thể giúp người tấn công lập bản đồ hạ tầng hoặc xây dựng các chiến dịch giả mạo.

Bởi vậy, cần đánh giá **metadata như một loại dữ liệu có thể nhạy cảm**, chứ không chỉ kiểm tra body và password.

## 8. Debug TLS không đồng nghĩa an toàn hơn

Một kết nối SMTP qua TLS được mã hóa trên đường truyền. Nhưng sau khi thư viện đã giải mã dữ liệu để xử lý, các thành phần debug có thể ghi thông tin trước hoặc sau TLS vào output theo khả năng của chúng.

~~~text
SMTP server
     |
     | TLS encrypted traffic
     v
Jakarta Mail / JSSE inside JVM
     |
     +-- Application processes message
     |
     +-- Debug / log output
                |
                v
       stdout / file / log collector
~~~

**TLS bảo vệ đường mạng, không tự mã hóa hoặc kiểm soát quyền truy cập của file log**.

### 8.1. JSSE handshake debug

Ví dụ:

~~~text
-Djavax.net.debug=ssl,handshake
~~~

Thông tin handshake có thể đủ để tìm certificate mismatch hoặc protocol negotiation issue. Nhưng nó tác động đến JSSE của runtime, không chỉ một lần gửi SMTP cụ thể.

Không kích hoạt những chế độ xuất TLS key material hoặc debug cực chi tiết trong production nếu không có quy trình bảo mật chuyên biệt.

### 8.2. Certificate chain cũng có thông tin

Certificate có thể chứa domain, SAN hoặc tên tổ chức. Phần lớn không phải bí mật theo định nghĩa của certificate công khai, nhưng nó vẫn có thể làm lộ hạ tầng hoặc endpoint nội bộ khi bị gom vào log tập trung.

### 8.3. Không dùng debug như cách thay hostname verification

Nếu gặp lỗi TLS certificate, phải sửa trust chain, SAN, hostname hoặc cấu hình TLS. Không tắt hostname verification hay dùng trust-all chỉ để kết nối thành công.

## 9. Một threat model ngắn cho SMTP debug

Đánh giá rủi ro nên trả lời bốn câu hỏi:

1. **Tài sản:** dữ liệu nào có thể đi vào log?
2. **Tác nhân:** ai có thể đọc, sửa, sao chép hoặc xuất log?
3. **Đường rò rỉ:** log đi qua những hệ thống và vị trí lưu trữ nào?
4. **Hậu quả:** nếu dữ liệu bị truy cập trái phép, tác động là gì?

### 9.1. Các tác nhân cần cân nhắc

| Tác nhân | Khả năng tiếp cận |
| --- | --- |
| Developer có quyền đọc application log | Có thể xem sự cố nhưng không nhất thiết được phép xem secrets/PII |
| Nhân viên vận hành/đơn vị hỗ trợ | Có thể truy cập collector, dashboard hoặc file dump |
| CI/CD pipeline | Có thể lưu log trong artifact hoặc job output |
| Nhà cung cấp observability | Có thể lưu bản sao theo cấu hình hợp đồng và retention |
| Người có quyền truy cập dashboard bị lộ | Có thể tìm kiếm dữ liệu lịch sử |
| Kẻ tấn công chiếm quyền một log token | Có thể tải hoặc truy vấn log từ xa |
| Người nhận screenshot/ticket | Có thể nhận vô tình phần log được chia sẻ |

Một sự cố log không nhất thiết phải bắt đầu bằng người tấn công. **Quyền đọc quá rộng hoặc chia sẻ transcript trong ticket** cũng là con đường làm lộ dữ liệu.

### 9.2. Đường đi thường bị bỏ sót

~~~text
Jakarta Mail debug
       |
       +-- System.out / stderr
       |       |
       |       +-- Container logs
       |       +-- Kubernetes logging agent
       |
       +-- File log
       |       |
       |       +-- Rotation archive
       |       +-- Backup / snapshot
       |
       +-- Central log pipeline
               |
               +-- Search dashboard
               +-- Alert payload
               +-- Ticket / incident report
               +-- Third-party retention
~~~

Sau khi dữ liệu vào collector, xóa nó khỏi stdout hiện tại không chắc đã loại bỏ được các bản sao lịch sử.

## 10. Ma trận rủi ro minh họa

Có thể dùng mô hình định tính **khả năng xảy ra × mức tác động** để ưu tiên biện pháp bảo vệ. Các mức dưới đây chỉ là ví dụ cho một hệ thống gửi email giao dịch; tổ chức cần hiệu chỉnh theo dữ liệu, kiến trúc và quyền truy cập thực tế.

| Tình huống | Khả năng nếu bật raw debug rộng | Tác động | Ưu tiên |
| --- | --- | --- | --- |
| AUTH payload lộ credential đang dùng | Phụ thuộc provider/debug settings; cần giả định nghiêm trọng nếu được bật | Rất cao: chiếm quyền account gửi | Rất cao |
| Password reset token trong body được capture | Phụ thuộc việc body có bị log | Rất cao: nguy cơ chiếm account | Rất cao |
| RCPT TO lộ danh sách khách hàng | Cao nếu log raw SMTP command | Cao: rò rỉ dữ liệu cá nhân | Cao |
| Subject chứa thông tin giao dịch | Phụ thuộc header capture | Trung bình–cao | Cao |
| Attachment xuất vào transcript/capture | Phụ thuộc implementation/capture mode | Có thể rất cao | Cao |
| Host/port và TLS capability được ghi | Thường có thể xuất hiện | Thấp–trung bình tùy hạ tầng | Trung bình |
| Log được gửi tới nhiều nhà cung cấp | Phụ thuộc pipeline | Mở rộng phạm vi truy cập và retention | Cao |
| Debug bị bật mãi sau xử lý sự cố | Dễ gặp nếu không có expiry/owner | Tăng lượng dữ liệu tích lũy | Cao |
| Log không có redaction nhưng chỉ trong môi trường test giả lập | Thấp hơn nếu hoàn toàn không có dữ liệu thật | Tùy kiểm soát môi trường | Cần quản trị |

Đừng dùng điểm số như bằng chứng rằng tất cả provider đều log body hoặc credentials. Hãy đánh giá theo dữ liệu thực tế của phiên bản đang dùng và coi **unknown** là lý do để hạn chế debug thay vì mặc định vô hại.

## 11. Phạm vi truy cập là một phần của mức rủi ro

Cùng một bản transcript có tác động khác nhau nếu:

- Chỉ một kỹ sư được cấp quyền truy cập tạm thời.
- Mọi nhân viên kỹ thuật đều có thể tìm kiếm trên dashboard.
- Log được tải lên công cụ SaaS có quyền chia sẻ.
- Nội dung được paste vào issue công khai.
- File được lưu mãi trong build artifact.

Chính sách an toàn cần dùng **least privilege**:

- Chỉ người trực tiếp xử lý sự cố được truy cập.
- Tài khoản truy cập được ghi audit.
- Mọi export phải có mục đích và được phê duyệt theo chính sách.
- Không coi quyền deploy là mặc nhiên có quyền đọc nội dung email của người dùng.
- Tách quyền quan sát metadata với quyền truy cập dữ liệu nhạy cảm.
- Thu hồi quyền tạm thời sau khi kết thúc điều tra.

## 12. Retention và bản sao log

Một hệ thống có thể bật debug trong mười phút nhưng log vẫn được lưu nhiều tháng.

Cần xác định:

- Thời gian giữ trên container node.
- Thời gian giữ ở log collector.
- Thời gian giữ trong backup.
- Alert hoặc ticket có sao chép log hay không.
- Bản export nằm trong máy cá nhân hay không.
- Khả năng xóa hoặc áp dụng retention ở nhà cung cấp dịch vụ.
- Ai được phép yêu cầu xóa và cách kiểm chứng.

**Tắt debug chỉ ngăn thu thập mới, không tự xóa dữ liệu đã ghi.** Nếu credentials hoặc token đã bị lộ, cần đánh giá biện pháp thu hồi/rotation độc lập với việc xóa log.

### 12.1. Không giữ raw transcript lâu hơn nhu cầu xử lý

Nếu một transcript thật sự cần thiết để tìm lỗi khó, nên đặt retention ngắn và một owner có trách nhiệm kết thúc truy cập. Không dùng transcript như kênh logging mặc định cho báo cáo vận hành.

### 12.2. Lưu log đã làm sạch cũng cần giới hạn

Ngay cả event ID hoặc recipient reference vẫn có thể liên kết tới người dùng qua database khác. Pseudonymization giúp giảm lộ trực tiếp nhưng không có nghĩa dữ liệu hoàn toàn vô danh.

## 13. Cấu hình Spring Boot an toàn theo mặc định

Cấu hình cơ bản:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
      "[mail.debug]": "false"
      "[mail.debug.auth]": "false"
~~~

**mail.debug=false** thể hiện rõ ý định không ghi transcript Jakarta Mail theo mặc định.

**mail.debug.auth=false** là một thiết lập phòng vệ ở những provider có hỗ trợ property này; không nên coi nó là bộ lọc duy nhất hoặc bảo đảm rằng mọi thông tin nhạy cảm đã bị ẩn. Các phiên bản có thể khác nhau, nên chính sách an toàn vẫn là **không bật raw protocol debug trong luồng production thông thường**.

Các giá trị host, port và timeout là minh họa; điều chỉnh theo provider và SLA.

### 13.1. Dạng application.properties

~~~properties
spring.mail.host=smtp.example.org
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true

spring.mail.properties[mail.debug]=false
spring.mail.properties[mail.debug.auth]=false

spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=10000
spring.mail.properties[mail.smtp.writetimeout]=10000
~~~

Không lưu username/password thật hoặc token trong repository. Sử dụng secret manager hoặc cơ chế cấu hình bí mật của môi trường triển khai.

### 13.2. Chỉ thay logging.level chưa đủ

Một ví dụ dễ nhầm:

~~~yaml
logging:
  level:
    org.springframework.mail: INFO
~~~

Cấu hình này kiểm soát logger thuộc namespace Spring phù hợp, **không chắc chắn vô hiệu hóa Jakarta Mail Session debug nếu mail.debug=true**.

Cần kiểm tra cả JavaMail properties, Session debug, JVM TLS debug và bộ thu stdout/stderr của runtime.

## 14. Rủi ro khi bật debug bằng Java API

Jakarta Mail Session có API debug:

~~~java
Session session = Session.getInstance(properties);
session.setDebug(true);
~~~

Và một số ứng dụng có thể lấy Session của JavaMailSenderImpl để thay đổi debug trong lúc chạy.

Đây là thao tác cần thận trọng vì Session có thể được dùng lại cho nhiều message hoặc nhiều thread. Một thay đổi debug tưởng như “chỉ cho email hiện tại” có thể ảnh hưởng đến những email khác đang xử lý đồng thời.

### 14.1. Không bật debug toàn cục để điều tra một recipient

Nếu một SMTP Session được dùng chung, bật debug trong khoảng thời gian đang gửi có thể ghi transcript của nhiều recipient và nhiều nghiệp vụ.

Giải pháp tốt hơn:

- Tái hiện lỗi với test SMTP account và dữ liệu giả lập.
- Tạo một môi trường chẩn đoán tách biệt.
- Ghi metadata cho một correlation ID.
- Nếu bắt buộc cần raw debug, cô lập phạm vi bằng process/configuration riêng phù hợp.
- Kết thúc debug và loại bỏ dữ liệu chẩn đoán theo retention.

### 14.2. Không tự thay System.out một cách tùy tiện

Nếu debug đi qua stdout, ứng dụng có thể bị thu thập bởi hạ tầng container logging. Việc thay thế stream trong JVM có thể tác động đến code khác, không phải biện pháp redaction bền vững.

Nên kiểm soát nguồn phát log và đường thu thập thay vì cố “lọc về sau” mọi dữ liệu trên stdout.

## 15. Redaction: nên làm gì và giới hạn ở đâu?

**Redaction** là loại bỏ hoặc che dữ liệu nhạy cảm trước khi dữ liệu được lưu hay chia sẻ.

Ví dụ log đã làm sạch:

~~~text
eventId=mail-456
senderAlias=outbound-primary
recipientRef=user-42
phase=AUTH
smtpReply=535
enhancedStatus=5.7.8
category=AUTH_REJECTED
~~~

Thay vì:

~~~text
AUTH PLAIN <encoded-credentials>
MAIL FROM:<notifications@example.org>
RCPT TO:<customer01@example.net>
~~~

### 15.1. Ưu tiên không phát sinh dữ liệu nhạy cảm

Biện pháp tốt nhất là **không đưa raw transcript vào hệ thống log**. Nếu ứng dụng chỉ log những trường được cho phép ngay từ đầu, nhu cầu redaction giảm đáng kể.

### 15.2. Regex redaction không đủ để làm sạch SMTP transcript

Một regex tìm dấu @ hoặc từ password không thể xử lý đáng tin cậy:

- AUTH payload Base64.
- OAuth2 token trong payload khác nhau.
- Token trong URL.
- Header được fold qua nhiều dòng.
- Dữ liệu MIME quoted-printable/Base64.
- Ký tự escape hoặc định dạng log mới.
- Partial lines hoặc nhiều command trong một buffer.
- Provider diagnostic thay đổi.

Vì vậy, **đừng dựa vào regex trên raw debug như hàng rào bảo mật duy nhất**.

### 15.3. Nếu buộc phải xử lý raw log

Cần có quy trình:

1. Cô lập nguồn và quyền truy cập.
2. Không gửi bản gốc vào hệ thống collector rộng quyền.
3. Phân loại và loại bỏ secrets/PII bằng bộ xử lý được thiết kế theo format thực tế.
4. Kiểm thử các trường hợp đa dòng, Base64, token và payload lỗi.
5. Kiểm tra bản đã làm sạch trước khi chia sẻ.
6. Giữ bản gốc chỉ trong môi trường có policy đặc biệt và retention ngắn nếu thực sự cần.

Không gắn nhãn “sanitized” cho log khi chưa kiểm tra được mức độ làm sạch.

## 16. Structured logging thay thế raw SMTP debug

Thay vì ghi toàn bộ SMTP command, service có thể ghi lại sự kiện có cấu trúc. Những trường thường đủ cho việc vận hành gồm:

~~~text
eventId
smtpAccountAlias
smtpProvider
smtpPhase
smtpReplyCode
enhancedStatusCode
errorCategory
attemptNumber
nextAttemptAt
durationMillis
connectionMode
outcomeStatus
~~~

Có thể cần thêm recipient reference thay vì email đầy đủ, nhưng phải cân nhắc tính liên kết tới người dùng.

### 16.1. Ví dụ service Spring logging tối thiểu

~~~java
import jakarta.mail.internet.MimeMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ObservedMailDeliveryService {

    private static final Logger log =
            LoggerFactory.getLogger(ObservedMailDeliveryService.class);

    private final JavaMailSender mailSender;

    public ObservedMailDeliveryService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void submit(
            MimeMessage message,
            String eventId,
            String smtpAccountAlias,
            int attempt
    ) {
        long start = System.nanoTime();

        try {
            mailSender.send(message);

            log.info(
                    "mail.submit eventId={} account={} attempt={} "
                  + "result=SMTP_SUBMIT_OK durationMs={}",
                    eventId,
                    smtpAccountAlias,
                    attempt,
                    elapsedMillis(start)
            );
        } catch (MailAuthenticationException ex) {
            log.warn(
                    "mail.submit eventId={} account={} attempt={} "
                  + "result=FAILED category=AUTH durationMs={}",
                    eventId,
                    smtpAccountAlias,
                    attempt,
                    elapsedMillis(start)
            );
            throw ex;
        } catch (MailException ex) {
            log.warn(
                    "mail.submit eventId={} account={} attempt={} "
                  + "result=FAILED category=NEEDS_CLASSIFICATION durationMs={}",
                    eventId,
                    smtpAccountAlias,
                    attempt,
                    elapsedMillis(start)
            );
            throw ex;
        }
    }

    private static long elapsedMillis(long start) {
        return java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start
        );
    }
}
~~~

Ví dụ trên không log recipient, subject, body, attachment, password hay exception message. **SMTP_SUBMIT_OK** chỉ phản ánh lời gọi send đã hoàn tất bình thường, không bảo đảm email đã vào inbox hoặc được đọc.

### 16.2. Phân loại lỗi chuyên sâu không nhất thiết phải in exception message

Một adapter có thể trích xuất **reply code**, **enhanced status code** và **phase** từ exception có cấu trúc của Jakarta Mail provider. Chỉ ghi các trường cần thiết, sau khi kiểm tra chúng không chứa PII.

Không nên làm:

~~~java
log.error("SMTP failed: {}", ex.getMessage());
~~~

với assumption rằng thông điệp lỗi luôn vô hại. Một số thông điệp có thể nhúng địa chỉ, hostname, server response hoặc thông tin khác.

### 16.3. Không vô hiệu hóa mọi log

Không cần chọn giữa **raw transcript đầy đủ** và **không biết gì về hệ thống**. Structured logs, metrics và tracing có thể cung cấp khả năng quan sát tốt hơn cho phần lớn vấn đề thường gặp, trong khi giới hạn dữ liệu nhạy cảm.

## 17. Metrics nào có thể thu thập mà ít rủi ro hơn?

Các metric tổng hợp hữu ích:

| Metric | Mục đích |
| --- | --- |
| Số lần SMTP submit thành công | Theo dõi lưu lượng |
| Tỷ lệ AUTH failure theo account alias | Phát hiện cấu hình hoặc credential lỗi |
| Tỷ lệ 4xx/5xx theo provider | Phát hiện throttling và policy rejection |
| Kết nối timeout | Theo dõi độ ổn định mạng |
| TLS handshake failure | Phát hiện certificate/protocol issue |
| Thời gian hoàn thành gửi | Tìm bottleneck |
| Outbox backlog | Theo dõi số tác vụ chưa gửi |
| Số lần retry trung bình | Đánh giá độ tin cậy |
| UNKNOWN_OUTCOME count | Theo dõi cửa sổ có nguy cơ duplicate |
| Accepted-by-relay versus later bounce | Phân biệt SMTP accept và delivery |

Tránh dùng email đầy đủ, token hoặc event ID có cardinality cực cao làm metric label. Các nền tảng metrics thường không thích hợp để chứa các trường có thể nhận diện người dùng hoặc giá trị độc nhất ở mỗi message.

## 18. Correlation ID và khả năng đối soát

Một **event ID** ổn định có thể nối các bước:

~~~text
Business transaction
       |
       v
Outbox eventId=mail-456
       |
       v
Worker attempt=1
       |
       v
SMTP AUTH / RCPT TO / DATA
       |
       v
Accepted-by-relay or failure status
~~~

Ưu điểm:

- Không cần log Subject và body để biết email nào gặp lỗi.
- Có thể so sánh retry của cùng một tác vụ.
- Hỗ trợ đối soát với provider nếu provider có message reference.
- Giúp xử lý duplicate window.

Event ID cần không chứa trực tiếp credential hoặc thông tin nhạy cảm. Nếu ứng dụng dùng ID có thể truy ngược tới cá nhân, vẫn phải kiểm soát quyền truy cập.

### 18.1. Message-ID có thể hữu ích nhưng chưa đủ

MIME Message-ID giúp nhận diện message ở tầng email. Tuy nhiên:

- Nó không tự bảo đảm exactly-once SMTP.
- Một số provider có thể thay đổi header hoặc cung cấp ID riêng.
- Không nên dùng Message-ID như bằng chứng người nhận đã đọc thư.

Nên lưu correlation ID của ứng dụng và các ID do provider trả về khi có.

## 19. Dùng SMTP fake hoặc capture server để giảm rủi ro

Khi cần quan sát toàn bộ giao thức, lựa chọn an toàn hơn thường là **tái hiện bằng dữ liệu tổng hợp trên SMTP test server**.

Ví dụ môi trường test:

~~~text
Spring application (test profile)
            |
            v
Local/test SMTP capture server
            |
            +-- Dữ liệu người gửi giả
            +-- Địa chỉ example.net
            +-- Token giả không có quyền sử dụng
            +-- Attachment giả
            |
            v
Investigation
~~~

Ưu điểm:

- Không dùng credentials production.
- Không gửi tới người nhận thật.
- Có thể kiểm tra STARTTLS, AUTH, RCPT TO hoặc DATA theo kịch bản.
- Cho phép capture toàn bộ message với dữ liệu không nhạy cảm.
- Không cần bật debug trên toàn bộ phiên gửi production.

### 19.1. Không sao chép nguyên dữ liệu production sang test

Nếu tái hiện bằng snapshot từ production, dữ liệu có thể vẫn nhạy cảm. Cần thay thế recipient, token, nội dung và attachment bằng dữ liệu tổng hợp có cấu trúc tương đương.

Một token giả phải thật sự không có quyền sử dụng, không phải token đã hết hạn được lấy nguyên từ log.

### 19.2. Khi test server không tái hiện được lỗi provider

Một số lỗi chỉ xảy ra ở provider thật, ví dụ rate limiting hoặc chính sách tenant. Khi đó có thể cần log metadata của response thực tế, nhưng vẫn tránh raw transcript và secrets. Chỉ bật diagnostic rộng hơn theo quy trình ngoại lệ được phê duyệt.

## 20. Quy trình bật debug có kiểm soát khi thật sự cần

Nếu structured logging không đủ và sự cố không thể tái hiện ở test, hãy thực hiện một quy trình rõ ràng.

### 20.1. Trước khi bật

1. Ghi rõ **mục đích điều tra**: ví dụ STARTTLS negotiation thất bại.
2. Xác định **nguồn cần quan sát**: Jakarta Mail hay JSSE, không bật mọi debug mode.
3. Chỉ định **owner** và người có quyền xem log.
4. Xác định **account, host, thời gian, môi trường** cần chẩn đoán.
5. Xác nhận dữ liệu có thể xuất hiện và độ nhạy cảm.
6. Đặt **thời hạn tự tắt** hoặc kế hoạch rollback cấu hình.
7. Kiểm tra log pipeline và retention của từng bản sao.
8. Chuẩn bị kênh lưu trữ hạn chế thay vì dashboard rộng quyền.
9. Nếu khả thi, dùng account test và recipient giả.
10. Xác định rõ điều kiện thành công để ngừng thu thập.

### 20.2. Trong khi bật

- Chỉ tạo số lần gửi cần thiết.
- Không phát động retry hàng loạt.
- Không dùng email chứa token sống, attachment nhạy cảm hoặc dữ liệu người dùng thật nếu có thể tránh.
- Quan sát output và dừng ngay khi phát hiện credentials hoặc thông tin nhạy cảm.
- Không paste raw transcript vào chat, ticket hoặc issue có quyền rộng.
- Tránh mở debug đồng thời ở nhiều instance nếu một instance đủ tái hiện lỗi.

### 20.3. Sau khi bật

1. Tắt flag debug và xác nhận trên runtime đang chạy.
2. Kiểm tra stdout/stderr, file, collector và bản export đã tạo.
3. Lưu các kết luận cần thiết dưới dạng dữ liệu đã làm sạch.
4. Xóa bản thô theo chính sách và xác minh phạm vi xóa khả thi.
5. Thu hồi quyền tạm thời.
6. Nếu credentials/token đã xuất hiện, xử lý rotation/revocation.
7. Cập nhật runbook để lần sau ít cần raw debug hơn.

**Không có bước kết thúc thì “bật debug tạm thời” có thể biến thành cấu hình thường trực.**

## 21. Xử lý sự cố nếu log đã chứa secrets

Khi phát hiện SMTP debug có thể đã ghi credentials hoặc link có token:

~~~text
Detect potential leak
        |
        v
Disable debug / stop further exposure
        |
        v
Identify log sinks and access scope
        |
        v
Contain access / exports
        |
        v
Revoke or rotate affected secrets
        |
        v
Assess data exposure and obligations
        |
        v
Remove retained copies where possible
        |
        v
Document incident and improve controls
~~~

### 21.1. Ưu tiên ngăn tiếp tục lộ

Không chỉ xóa một file log rồi để debug tiếp tục ghi. Phải tắt nguồn tạo dữ liệu và chặn xuất log mới sang các sink không phù hợp.

### 21.2. Credential cần được thu hồi/đổi

Nếu password SMTP, app password hoặc OAuth token đã được ghi vào nơi không đáng tin cậy, việc xóa log không đảm bảo secret chưa bị sao chép. Cần đánh giá rotation hoặc revocation theo chính sách.

Đối với link reset password hoặc magic login, có thể cần vô hiệu hóa token và phát hành link mới nếu vẫn có nhu cầu hợp lệ.

### 21.3. Xác định phạm vi ảnh hưởng

Các câu hỏi:

- Debug được bật từ lúc nào đến lúc nào?
- Những instance nào chịu ảnh hưởng?
- Log đi vào những collector nào?
- Những ai đã xem hoặc tải xuống?
- Dữ liệu nào có thể nằm trong transcript?
- Có backup, alert, ticket hoặc attachment chứa bản sao không?
- Có yêu cầu báo cáo sự cố theo luật/chính sách hoặc hợp đồng không?

Không khẳng định “không bị lộ” chỉ vì không thấy một bản ghi trên dashboard hiện tại.

## 22. Chính sách debug ở các môi trường

| Môi trường | Chính sách gợi ý |
| --- | --- |
| **Local với dữ liệu giả** | Có thể bật có kiểm soát; tránh dùng credentials thật |
| **Unit/integration test** | Ưu tiên fake transport hoặc SMTP capture, chỉ dùng test secrets |
| **Staging** | Mặc định tắt; bật theo case, dữ liệu tổng hợp, retention hạn chế |
| **Production** | Mặc định tắt; chỉ ngoại lệ có chủ đích, hẹp và có thời hạn |
| **Incident environment** | Cô lập, cấp quyền tạm thời, ghi audit và quản lý output |
| **CI/CD** | Không in secret; chặn debug rộng và bảo vệ build artifacts |

Một profile staging không tự bảo đảm an toàn nếu nó kết nối tới provider thật hoặc dùng dữ liệu production. Hãy đánh giá dữ liệu và quyền truy cập thực tế, không chỉ tên môi trường.

## 23. Cấu hình thực tế và anti-pattern

### 23.1. Anti-pattern: bật raw debug cố định trong cấu hình dùng chung

~~~yaml
spring:
  mail:
    properties:
      "[mail.debug]": "true"
~~~

Nếu file cấu hình này áp dụng cho mọi môi trường, mỗi instance có thể liên tục tạo transcript chứa metadata hoặc dữ liệu nhạy cảm.

### 23.2. Anti-pattern: bật thêm debug AUTH

~~~properties
spring.mail.properties[mail.debug.auth]=true
~~~

Trong provider có hỗ trợ, tùy chọn này có thể làm lộ chi tiết xác thực vốn được che. Không dùng nó như phương pháp thường quy để điều tra lỗi SMTP AUTH.

### 23.3. Anti-pattern: log nguyên object hoặc raw MIME

~~~java
log.debug("Message: {}", message);
~~~

Việc format object có thể phụ thuộc implementation và không phải một hợp đồng redaction. Cũng không nên dùng **writeTo(...)** để dump toàn bộ MIME message vào logger chỉ vì cần biết email đã được tạo.

### 23.4. Anti-pattern: log mọi exception message

~~~java
log.error("SMTP error: " + exception.getMessage());
~~~

Diagnostic text do provider gửi có thể chứa recipient, host hoặc chi tiết khác. Hãy trích xuất và allowlist dữ liệu cần thiết; không mặc định mọi chuỗi lỗi đều an toàn.

### 23.5. Anti-pattern: tắt TLS để debug dễ hơn

Tắt STARTTLS/hostname verification làm thay đổi hành vi bảo mật thật và có thể đưa dữ liệu xác thực lên đường truyền không an toàn. Nếu cần quan sát handshake, dùng kênh JSSE debug có kiểm soát, không chủ động hạ cấp kết nối.

## 24. Checklist thiết kế một sự kiện log an toàn

Một log event phục vụ chẩn đoán gửi email nên trả lời:

- **Tác vụ nào?** Event ID không nhạy cảm.
- **Account/host nào?** Alias hoặc ID được phép.
- **Giai đoạn nào?** CONNECT, TLS, AUTH, MAIL FROM, RCPT TO, DATA, AFTER_DATA.
- **Kết quả nào?** Accepted by relay, temporary failure, permanent failure, unknown.
- **Mã nào?** SMTP 4xx/5xx và enhanced code nếu đáng tin.
- **Đã thử bao nhiêu lần?** Attempt count.
- **Khi nào thử lại?** Next attempt time.
- **Mất bao lâu?** Duration.
- **Đã redaction chưa?** Không có credential, body hoặc PII không cần thiết.
- **Ai xem được?** Quyền đọc và audit.
- **Giữ bao lâu?** Retention rõ ràng.

Không nhất thiết mọi sự kiện phải có đủ các trường; mục tiêu là ghi **vừa đủ thông tin để quyết định hành động**.

### 24.1. Ví dụ log thành công

~~~text
mail.submit
eventId=mail-456
accountAlias=primary
result=SMTP_SUBMIT_OK
durationMs=812
~~~

### 24.2. Ví dụ log lỗi xác thực

~~~text
mail.submit
eventId=mail-456
accountAlias=primary
phase=AUTH
smtpReply=535
enhancedStatus=5.7.8
category=AUTH_CONFIGURATION
decision=PAUSE_ACCOUNT
~~~

### 24.3. Ví dụ log lỗi recipient

~~~text
mail.submit
eventId=mail-457
recipientRef=customer-42
phase=RCPT_TO
smtpReply=550
enhancedStatus=5.1.1
category=RECIPIENT_REJECTED
decision=NEEDS_ADDRESS_CORRECTION
~~~

### 24.4. Ví dụ kết quả chưa xác định

~~~text
mail.submit
eventId=mail-458
phase=AFTER_DATA
category=UNKNOWN_OUTCOME
decision=REVIEW_DUPLICATE_RISK
~~~

Các trường được chuẩn hóa là mẫu thiết kế của ứng dụng, không phải property hoặc enum mặc định có sẵn trong JavaMailSender.

## 25. Kiểm thử chính sách logging trước khi triển khai

Một bộ kiểm thử nên tập trung vào **hành vi phát sinh log**, không chỉ kiểm tra config file:

1. Chạy luồng gửi thành công với dữ liệu tổng hợp.
2. Gây lỗi AUTH bằng fake SMTP server.
3. Gây lỗi RCPT TO cho recipient giả.
4. Gây lỗi STARTTLS/certificate trong test TLS endpoint.
5. Kiểm tra output của application logger, stdout/stderr và collector test.
6. Xác nhận secret giả và token canary không xuất hiện trong log.
7. Xác nhận event ID, phase, category và mã lỗi vẫn đủ cho chẩn đoán.
8. Kiểm tra việc tắt debug thực sự ngăn transcript mới.
9. Kiểm tra path log trong container và build artifact.
10. Kiểm tra retention/permission theo chính sách của môi trường.

### 25.1. Canary secrets phải là giá trị giả

Có thể tạo password/token giả chỉ dùng cho test, ví dụ một chuỗi có dấu hiệu nhận diện riêng nhưng **không có quyền thực tế**. Không dùng credentials production làm canary.

### 25.2. Không chỉ test một pattern

Một secret có thể xuất hiện:

- Nguyên văn.
- Base64.
- Trong URL encoding.
- Trong MIME quoted-printable.
- Bị chia thành nhiều dòng/chunk.
- Trong stack trace hoặc diagnostic từ provider.

Mục tiêu là **ngăn dữ liệu không cần thiết đi vào log**, không chỉ phát hiện một chuỗi raw duy nhất sau khi đã ghi.

### 25.3. Test phát sinh log không phải QA nội dung email

Kiểm thử logging nhằm bảo vệ secrets/PII và khả năng quan sát. Nó tách biệt với kiểm tra email client hiển thị HTML hoặc provider giao thư tới inbox.

## 26. Tình huống thực hành: SMTP AUTH trả 535

Giả sử service ghi nhận:

~~~text
MailAuthenticationException
SMTP AUTH rejected
Reply: 535 5.7.8
~~~

**Không cần bật mail.debug.auth=true để biết password đang gửi là gì.** Nếu cấu hình sai, việc in password ra log chỉ tạo thêm nguy cơ.

Quy trình hợp lý:

1. Xác định sender account alias và môi trường.
2. Kiểm tra secret reference có đúng phiên bản hay không.
3. Xác nhận SMTP AUTH được cho phép ở provider.
4. Kiểm tra phương thức xác thực phù hợp: app password, OAuth2 hoặc cơ chế khác.
5. Kiểm tra STARTTLS/implicit TLS có hoạt động theo endpoint.
6. Nếu có token refresh, kiểm tra trạng thái token bằng kênh riêng an toàn.
7. Tạm dừng retry mù trên account nếu lỗi cố định.
8. Sau khi sửa, thử lại có kiểm soát.
9. Ghi event category và kết quả, không in credentials.

Nếu provider trả lỗi tạm thời, chẳng hạn AUTH 454, có thể retry có backoff. Nhưng một phản hồi AUTH 535 không được sửa bằng cách log hoặc thử hàng loạt mật khẩu thật.

## 27. Tình huống thực hành: lỗi recipient

Giả sử SMTP trả:

~~~text
550 5.1.1 User unknown
~~~

Không cần lưu địa chỉ đầy đủ ở RCPT TO để biết cần xử lý người nhận nào nếu hệ thống đã có correlation ID và recipient reference.

Quy trình:

1. Liên kết phản hồi với mail event và recipient reference.
2. Xác nhận phase là RCPT TO và enhanced code đáng tin cậy.
3. Phân biệt user unknown với lỗi policy như 550 5.7.1.
4. Cập nhật trạng thái recipient/mail job phù hợp.
5. Không retry nguyên trạng địa chỉ đã được xác định không tồn tại.
6. Không đưa địa chỉ thật vào dashboard rộng quyền nếu không cần.

Đừng chỉ dựa vào mã SMTP ba chữ số 550 rồi tự suppression mọi recipient. Cần xem enhanced code và ngữ cảnh provider.

## 28. Tình huống thực hành: STARTTLS handshake lỗi

Giả sử Spring Mail báo:

~~~text
MailSendException
    |
    v
MessagingException
    |
    v
SSLHandshakeException
    |
    v
PKIX path building failed
~~~

Bản transcript SMTP đầy đủ có thể không cần thiết. Có thể:

1. Xác minh host, port và mode TLS.
2. Kiểm tra certificate chain và SAN bằng công cụ TLS được phép.
3. Xác định truststore thực tế của JDK/container.
4. Bật mức JSSE handshake debug tối thiểu trong môi trường cô lập nếu cần.
5. Không tắt certificate verification hoặc trust-all.
6. Ghi kết quả dạng error category, host alias và TLS phase.

TLS handshake debug cũng cần được quản lý vì nó có thể tiết lộ certificate/internal topology và tăng rất nhiều log ở toàn JVM.

## 29. Câu hỏi thường gặp

**1. Bật mail.debug có nguy hiểm không?**

Có thể. Nó có thể xuất thông tin SMTP session và metadata, tùy provider và cấu hình. Nếu output đi vào hệ thống log rộng quyền hoặc chứa secrets/PII, rủi ro rất lớn. Mặc định nên tắt trong production.

**2. SMTP debug có luôn in password không?**

Không phải mọi provider hoặc cấu hình đều in password. Một số có cơ chế che AUTH. Tuy nhiên, không được coi đó là bảo đảm. Đặc biệt tránh những option làm lộ chi tiết xác thực.

**3. AUTH PLAIN được Base64 có an toàn để ghi log không?**

Không. Base64 có thể giải mã dễ dàng. Payload chứa credential vẫn là secret.

**4. mail.debug.auth=true dùng để làm gì?**

Một số SMTP provider dùng property này để điều khiển việc debug thông tin AUTH. Nó có thể làm lộ dữ liệu nhạy cảm và không nên bật như cách chẩn đoán thông thường.

**5. Bật STARTTLS rồi thì log có được mã hóa không?**

Không tự động. STARTTLS bảo vệ chặng SMTP network. Log do ứng dụng/transport ghi ra đi qua pipeline khác và có chính sách bảo vệ riêng.

**6. Có thể chỉ giảm logging.level của Spring để tắt transcript không?**

Không bảo đảm. Jakarta Mail Session debug và JSSE debug có thể đi qua kênh khác với logger Spring/SLF4J.

**7. Vì sao RCPT TO có thể tiết lộ Bcc?**

Bcc cần được chuyển qua envelope recipient tới SMTP server, dù header Bcc không được đưa vào nội dung thư gửi đi. Vì vậy transcript có thể lộ địa chỉ Bcc.

**8. Có nên ghi Subject để debug email không?**

Thường không cần. Subject có thể chứa dữ liệu cá nhân hoặc nghiệp vụ. Dùng template key và event ID thay thế khi có thể.

**9. Có thể log toàn bộ MimeMessage đã Base64 không?**

Không nên. MIME Base64 vẫn có thể giải mã và chứa attachment, dữ liệu cá nhân hoặc token.

**10. Có nên log exception.getMessage() không?**

Cần thận trọng. Message từ provider có thể chứa recipient, account hoặc thông tin khác. Tốt hơn là trích xuất trường cấu trúc đã được xem xét về bảo mật.

**11. Có nên bật javax.net.debug trong production không?**

Chỉ trong trường hợp chẩn đoán đặc biệt, phạm vi tối thiểu và có kiểm soát. Property này có thể ảnh hưởng rộng trong JVM. Không bật debug TLS cực chi tiết hoặc chế độ lộ key material mà không có quy trình bảo mật chuyên biệt.

**12. Redaction bằng regex có đủ không?**

Không đủ để bảo đảm an toàn vì dữ liệu có thể ở dạng Base64, URL encoded, nhiều dòng hoặc format provider riêng. Ưu tiên không phát sinh raw secret ngay từ đầu.

**13. Có thể dùng SHA-256 của email thay cho địa chỉ đầy đủ không?**

Hash thường của địa chỉ có thể bị dò. Nếu cần correlation ổn định, cân nhắc HMAC có secret được quản lý hoặc mapping ID riêng, đồng thời áp dụng phân quyền/retention.

**14. Tắt debug có xóa log cũ không?**

Không. Phải kiểm tra file, stdout collector, backup, alert và export theo pipeline thực tế.

**15. Nếu lỡ ghi password SMTP thì phải làm gì?**

Dừng việc ghi mới, khoanh vùng bản sao và người truy cập, đánh giá rotation/revocation credential, xử lý log theo chính sách và xem xét nghĩa vụ báo cáo sự cố nếu áp dụng.

**16. Có thể chẩn đoán AUTH 535 mà không ghi AUTH payload không?**

Có. Thường chỉ cần account alias, phase AUTH, mã 535, enhanced status và cấu hình provider, sau đó kiểm tra secret qua kênh được bảo vệ.

**17. SMTP debug có giúp chứng minh người nhận đã đọc email không?**

Không. Nó chỉ liên quan tới kết nối client–server và phản hồi SMTP. Delivery và read là các mốc khác.

**18. Có cách nào xem raw protocol an toàn tuyệt đối không?**

Không có bảo đảm tuyệt đối. Có thể giảm rủi ro bằng dữ liệu tổng hợp, môi trường cô lập, quyền hạn chế, thời gian bật ngắn, chặn secrets và xử lý các bản sao sau điều tra.

## 30. Ghi nhớ khi đánh giá rủi ro SMTP debug

**SMTP debug là công cụ chẩn đoán, không phải log vận hành mặc định.** Tùy provider và cấu hình, transcript có thể chứa command/response, sender, recipient, tên miền, thông tin xác thực hoặc nội dung message. Đặc biệt, AUTH payload Base64, OAuth token, password reset link, OTP và attachment không trở nên an toàn chỉ vì được encode hoặc truyền qua TLS.

Trong Spring Framework Mail, hãy phân biệt **mail.debug**, **logging của ứng dụng** và **javax.net.debug**. Bật/tắt logger Spring không tự bảo đảm kiểm soát Session debug. TLS bảo vệ kết nối với SMTP server nhưng không bảo vệ tự động stdout, file log, collector, ticket hoặc bản export.

Ưu tiên **structured logging theo allowlist** gồm event ID, account alias, SMTP phase, reply code, error category, số lần thử và thời gian xử lý. Không lưu raw MIME, credentials và dữ liệu người nhận khi không cần. Với sự cố khó, dùng SMTP test server và dữ liệu giả trước; chỉ bật debug thật theo quy trình có owner, phạm vi, quyền truy cập, retention và thời hạn kết thúc rõ ràng.

Nếu log đã chứa secret, **tắt nguồn rò rỉ, giới hạn truy cập, xác định bản sao và xem xét thu hồi/đổi credential**. Mục tiêu của chẩn đoán an toàn là thu được đủ tín hiệu để sửa lỗi SMTP mà không biến hệ thống logging thành một kênh làm lộ dữ liệu email và thông tin xác thực.
