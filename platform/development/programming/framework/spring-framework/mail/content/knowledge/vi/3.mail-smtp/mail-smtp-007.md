# SMTP relay và giới hạn quyền gửi

Khi một ứng dụng Spring gửi email qua SMTP, máy chủ nhận yêu cầu có thể phải **chuyển tiếp thư đến một miền khác**. Hoạt động đó gọi là **SMTP relay**. Tuy nhiên, một máy chủ SMTP không nên chuyển thư ra Internet cho bất kỳ ai kết nối được tới nó: quyền relay cần được kiểm soát bằng chính sách người gửi, xác thực, mạng tin cậy, miền đích và giới hạn lưu lượng.

Hiểu SMTP relay giúp giải thích các tình huống thường gặp như `Relay access denied`, `Authentication required`, gửi được thư nội bộ nhưng không gửi ra ngoài, hoặc gửi thành công một lúc rồi bị giới hạn tốc độ. Trong Spring Framework Mail, việc thiết lập kết nối chỉ là một phần của lời giải; quyền gửi thực tế vẫn do **SMTP server** quyết định.

## 1. SMTP relay là gì?

**SMTP (Simple Mail Transfer Protocol)** là giao thức được sử dụng để gửi và chuyển thư giữa các hệ thống email. **Relay** là hành động một máy chủ SMTP nhận thư rồi chuyển tiếp tới một hệ thống khác thay vì giao thư trực tiếp vào mailbox mà nó phục vụ.

Ví dụ, ứng dụng gửi email từ `no-reply@shop.example` đến `customer@example.net`:

```text
 [Ứng dụng Spring]
        |
        | SMTP submission: xác thực, nộp thư
        v
 [SMTP server / MSA của shop.example]
        |
        | SMTP relay: chuyển thư đến miền example.net
        v
 [MTA phía example.net]
        |
        | Local delivery
        v
 [Mailbox customer@example.net]
        |
        v
 [Mail client của khách hàng]
```

Trong thực tế, có thể có nhiều MTA trung gian. Máy chủ nhận submission có thể vừa đóng vai trò **Mail Submission Agent (MSA)** vừa thực hiện chức năng của **Mail Transfer Agent (MTA)**, hoặc chuyển thư cho một relay khác.

Điểm cần nhớ: **relay không đồng nghĩa với mọi lần nhận email**. Một máy chủ email có thể nhận thư từ Internet để giao cho chính các mailbox của miền mình quản lý, trong khi vẫn **từ chối chuyển tiếp thư đến miền khác** cho các client không được phép.

### Submission, relay và local delivery

| Hoạt động | Bên phát sinh | Bên tiếp nhận | Mục tiêu |
| --- | --- | --- | --- |
| **Submission** | Ứng dụng, mail client hoặc service nội bộ | MSA/SMTP submission server | Nộp một email mới để hệ thống gửi xử lý |
| **Relay** | MTA hoặc client đã được cấp quyền relay | MTA kế tiếp | Chuyển tiếp thư tới đích khác |
| **Local delivery** | Hạ tầng email của miền nhận | MDA/kho lưu trữ | Giao thư vào mailbox thuộc hệ thống nhận |

Submission thường đi qua cổng **587 (STARTTLS)** hoặc **465 (TLS ngay khi kết nối)**. Các MTA trên Internet thường trao đổi với nhau qua **cổng 25**. Cổng là thông lệ triển khai; chính sách trên máy chủ mới quyết định client nào được nộp hoặc relay.

## 2. Vì sao phải giới hạn quyền relay?

Xét một SMTP server do công ty quản lý, nhận kết nối từ nhiều nguồn:

- Một ứng dụng đã được cấu hình tài khoản SMTP hợp lệ cần gửi xác nhận đơn hàng.
- Một máy chủ nội bộ đã được quản trị viên cho phép dùng relay không cần đăng nhập vì nằm trong mạng tin cậy.
- Một MTA từ Internet gửi thư tới `employee@company.example`, là mailbox mà công ty thực sự quản lý.
- Một máy tính lạ trên Internet muốn nhờ SMTP server của công ty gửi hàng nghìn email tới các miền bên ngoài.

Ba tình huống đầu **có thể hợp lệ theo cấu hình**. Tình huống cuối cần bị từ chối. Nếu máy chủ cho phép mọi nguồn chuyển thư đến mọi miền đích, đó là nguy cơ **open relay**.

Open relay thường bị lạm dụng để phát tán spam, thư lừa đảo và thư rác quy mô lớn. Hậu quả không chỉ là tăng tải máy chủ: IP hoặc miền gửi có thể bị đánh giá kém uy tín, email giao dịch hợp lệ bị từ chối, tài khoản bị khóa hoặc chi phí dịch vụ tăng nhanh.

Vì thế, chính sách relay thường bắt đầu bằng câu hỏi:

> **Ai đang yêu cầu chuyển thư, người đó có quyền chuyển thư qua máy chủ này không, và thư được phép đi tới đâu?**

## 3. Phân biệt nhận thư hợp lệ với cho phép relay

Giả sử `mx.company.example` là MTA nhận email cho miền `company.example`.

| Yêu cầu SMTP | Người kết nối | Đích nhận | Quyết định điển hình | Lý do |
| --- | --- | --- | --- | --- |
| Gửi thư cho `alice@company.example` | MTA bên ngoài | Miền được máy chủ quản lý | **Cho phép nhận**, sau khi qua chính sách kiểm tra | Đây là thư gửi **đến** mailbox mà hệ thống phục vụ |
| Gửi thư cho `bob@example.net` | Client Internet chưa xác thực | Miền bên ngoài | **Từ chối relay** | Máy chủ không có trách nhiệm chuyển thư ra ngoài cho nguồn lạ |
| Gửi thư cho `bob@example.net` | Ứng dụng đã SMTP AUTH hợp lệ | Miền bên ngoài | **Có thể cho phép relay** | Được cấp quyền gửi đi, nếu đáp ứng chính sách bổ sung |
| Gửi thư cho `bob@example.net` | Service từ địa chỉ IP được allowlist | Miền bên ngoài | **Có thể cho phép relay** | Được cấp quyền theo mạng tin cậy |
| Gửi thư cho `alice@company.example` | Client bất kỳ | Miền nội bộ nhưng hộp thư không tồn tại | **Có thể từ chối** | Máy chủ nhận thư cho miền không có nghĩa chấp nhận mọi địa chỉ |

Đừng nhầm **mailbox domain** với **relay domain**. Một máy chủ có thể được cấu hình nhận và giao thư cho miền sở hữu; các miền trung gian cần chuyển tiếp được quản lý bằng chính sách riêng. Chỉ thêm miền vào danh sách đích nhận không có nghĩa ai cũng được relay tùy ý.

Một luồng quyết định đơn giản:

```text
Nhận SMTP RCPT TO:<recipient@domain>
                   |
                   v
      Có quản lý đích nhận này?
              /           \
            Có             Không
            |                |
      Áp dụng chính sách     Client có quyền relay?
      nhận thư nội bộ          /           \
            |               Có            Không
      Nhận/từ chối theo       |              |
      địa chỉ, bộ lọc       Áp dụng       Từ chối:
      và cấu hình           policy       relay denied
                           gửi đi
                              |
                       Chấp nhận/từ chối
```

Sơ đồ chỉ thể hiện nguyên tắc. SMTP server thực tế có thể áp dụng thêm các chính sách đối với người gửi, nguồn kết nối, người nhận, lưu lượng và nội dung trước khi chấp nhận thư.

## 4. Các cách cấp quyền SMTP relay

### 4.1. Xác thực SMTP AUTH

**SMTP AUTH** cho phép client chứng minh danh tính khi nộp thư. Ứng dụng Spring thường cung cấp thông tin xác thực cho SMTP submission server, sau đó máy chủ kiểm tra tài khoản có được phép gửi hay không.

Một quy trình thông dụng:

1. Client kết nối tới endpoint submission.
2. Gửi `EHLO` để nhận danh sách khả năng máy chủ hỗ trợ.
3. Nếu máy chủ và cổng dùng STARTTLS, client nâng cấp kết nối qua `STARTTLS` rồi gửi `EHLO` lại.
4. Client xác thực qua `AUTH` theo phương thức máy chủ cho phép.
5. Máy chủ áp dụng quyền gửi của danh tính đã xác thực cho các lệnh gửi thư tiếp theo.

Trong triển khai thông thường, không nên cho phép gửi mật khẩu SMTP qua kết nối không được bảo vệ. **STARTTLS** nâng cấp kết nối ban đầu sang TLS; cổng 465 thường sử dụng **implicit TLS** (TLS ngay từ đầu).

SMTP AUTH trả lời câu hỏi **client nào đang gửi yêu cầu**. Nó không tự bảo đảm rằng tài khoản đó được phép giả mọi địa chỉ `From` hay gửi không giới hạn. SMTP server vẫn phải kiểm tra các quyền khác.

Một số nhà cung cấp dùng tài khoản/mật khẩu dành riêng cho ứng dụng, OAuth hoặc token theo cơ chế của họ. Ứng dụng phải tuân theo phương thức thực tế mà endpoint hỗ trợ.

### 4.2. Cho phép theo địa chỉ IP hoặc mạng tin cậy

Một relay nội bộ có thể cấp quyền cho những nguồn kết nối thuộc dải IP được quản trị viên chọn (**IP allowlist**), chẳng hạn một service chỉ được triển khai trong mạng riêng.

Ví dụ về chính sách logic:

```text
trusted_clients:
  - IP của ứng dụng thông báo nội bộ
  - IP của máy chủ batch được quản lý

relay_policy:
  - cho phép trusted_clients trong phạm vi gửi đã quy định
  - cho phép client đã xác thực và có quyền gửi
  - từ chối yêu cầu relay khác
```

Đây là **minh họa chính sách**, không phải cấu hình trực tiếp của một SMTP server cụ thể.

Điểm cần thận trọng:

- Chỉ allowlist các IP thực sự tin cậy. Dải mạng quá rộng có thể vô tình cấp quyền cho thiết bị không kiểm soát.
- Nếu dùng NAT, nhiều ứng dụng có thể chia sẻ cùng IP công khai; cấp quyền theo IP đó có thể mở rộng quyền hơn dự kiến.
- IP có thể đổi theo hạ tầng cloud, container hoặc mạng triển khai; thay đổi hạ tầng cần đi kèm rà soát chính sách.
- Nguồn IP tin cậy vẫn có thể bị chiếm quyền, nên vẫn cần giới hạn tốc độ, người gửi và nhật ký.
- Không nên cấp quyền relay chỉ vì kết nối đến từ Internet mà không có cơ chế ủy quyền phù hợp.

Cho phép theo IP hữu ích với service hạ tầng đã được kiểm soát, nhưng thường kém linh hoạt hơn SMTP AUTH khi ứng dụng chạy ở nhiều môi trường.

### 4.3. Quyền theo tài khoản, miền gửi và đích nhận

**Xác thực thành công chưa đủ để gửi bất cứ thứ gì.** Nhà cung cấp có thể giới hạn một tài khoản hoặc credential ở những phạm vi:

- Chỉ được sử dụng địa chỉ gửi đã xác minh, chẳng hạn `notifications@company.example`.
- Chỉ được gửi từ miền đã xác minh hoặc các alias được cấp quyền.
- Chỉ được gửi đến miền nội bộ, danh sách người nhận thử nghiệm hoặc các miền bên ngoài được chỉ định.
- Chỉ được gửi bằng một credential dành riêng cho ứng dụng hoặc môi trường cụ thể.
- Không được relay thêm từ một nguồn bất thường, vượt hạn ngạch hoặc vi phạm chính sách chống lạm dụng.

Ví dụ, tài khoản `billing-smtp` có thể được phép gửi từ `billing@company.example` nhưng không có quyền đặt `From: ceo@company.example`. Đây là chính sách **sender authorization** do máy chủ hoặc nhà cung cấp quyết định.

## 5. SMTP envelope, header From và quyền gửi

Khi nói “được phép gửi thay ai”, cần tách **SMTP envelope** khỏi **header hiển thị**:

| Phần | Ví dụ | Dùng cho |
| --- | --- | --- |
| `MAIL FROM` | `bounce@company.example` | Địa chỉ envelope sender, thường dùng cho thông báo không giao được |
| `RCPT TO` | `customer@example.net` | Địa chỉ nhận dùng trong phiên SMTP |
| Header `From:` | `Company <notifications@company.example>` | Danh tính người gửi hiển thị trong email |
| Header `Reply-To:` | `support@company.example` | Địa chỉ gợi ý để người nhận trả lời |

Envelope sender và header `From` **không bắt buộc trùng nhau**. Ví dụ nhà cung cấp gửi email có thể dùng một địa chỉ bounce riêng để nhận báo lỗi. Chính sách server có thể kiểm tra cả địa chỉ envelope và địa chỉ trong header nhằm hạn chế giả mạo.

**SMTP AUTH**, **SPF**, **DKIM** và **DMARC** không phải một cơ chế:

- **SMTP AUTH:** xác thực client với máy chủ submission, thường dùng để quyết định quyền nộp/relay.
- **SPF:** hỗ trợ máy chủ nhận đánh giá nguồn IP gửi có được miền liên quan đến SPF cho phép hay không.
- **DKIM:** cung cấp chữ ký mật mã để bên nhận kiểm tra một số header và body đã được ký.
- **DMARC:** áp dụng chính sách dựa trên kết quả SPF/DKIM và sự liên kết miền với header `From`.

SPF/DKIM/DMARC chủ yếu hỗ trợ **đánh giá danh tính và độ tin cậy thư ở phía nhận**. Chúng không thay thế việc kiểm tra quyền relay tại SMTP submission server. Một tài khoản SMTP bị lộ vẫn có thể lạm dụng dịch vụ gửi ngay cả khi DNS của miền được cấu hình đúng.

## 6. Giới hạn quyền gửi còn là giới hạn lưu lượng

Ngay cả client hợp lệ cũng không nên có quyền gửi vô hạn. Một relay thường áp dụng các hạn mức để bảo vệ hệ thống, danh tiếng IP/miền và tài nguyên của nhà cung cấp.

| Loại giới hạn | Ý nghĩa | Ví dụ về cách áp dụng |
| --- | --- | --- |
| **Số thư theo thời gian** | Tối đa email trong một phút/giờ/ngày | Theo credential, tenant hoặc ứng dụng |
| **Số người nhận** | Tối đa recipients trên một thư hoặc trong một khoảng thời gian | Tính theo các lệnh `RCPT TO` |
| **Kích thước thư** | Giới hạn tổng kích thước message, gồm MIME/attachment | Từ chối thư quá lớn |
| **Kết nối đồng thời** | Số phiên SMTP được mở cùng lúc | Giới hạn theo IP/tài khoản |
| **Tốc độ lệnh** | Tần suất gửi lệnh hoặc số request trên một kết nối | Chặn burst bất thường |
| **Phạm vi địa chỉ gửi** | Chỉ những sender/miền đã duyệt | Chặn giả mạo danh tính nội bộ |
| **Phạm vi người nhận** | Chỉ nội bộ hoặc tập miền nhận cho phép | Hạn chế email từ staging/test |
| **Danh tiếng và chống lạm dụng** | Chặn traffic bất thường hoặc nội dung bị đánh dấu | Tạm khóa credential, throttle |

Các con số cụ thể phụ thuộc nhà cung cấp, gói dịch vụ và cấu hình vận hành. Không có một “giới hạn SMTP toàn cầu” áp dụng cho mọi server.

### Giới hạn thư khác giới hạn người nhận

Một ứng dụng gửi **một thông điệp cho 50 địa chỉ** có thể chỉ là một lần nộp message, nhưng nhà cung cấp có thể tính thành 50 recipients cho hạn ngạch. Vì vậy, cần xem kỹ nhà cung cấp giới hạn **messages**, **recipients**, hay cả hai.

### Throttling và retry

Khi đạt giới hạn tạm thời, SMTP server có thể yêu cầu giảm tốc bằng phản hồi thuộc nhóm **4xx**. Client hoặc MTA có thể thử lại sau theo cơ chế retry có kiểm soát. Phản hồi thuộc nhóm **5xx** thường thể hiện lỗi vĩnh viễn đối với yêu cầu hiện tại, không nên lặp mù quáng.

Ví dụ minh họa, **mã chi tiết và thông điệp phụ thuộc server**:

```text
421 4.7.0 Temporary rate limit; try again later
451 4.7.1 Temporarily deferred by policy
552 5.3.4 Message size exceeds fixed maximum size
554 5.7.1 Relay access denied
```

Trong ứng dụng Spring, cần phân biệt **lỗi trước khi máy chủ chấp nhận thư** với **trạng thái chưa rõ vì ngắt kết nối**. Nếu mất kết nối ngay sau khi gửi nội dung nhưng trước lúc client nhận phản hồi cuối, máy chủ có thể đã nhận thư. Retry không có cơ chế chống trùng có thể tạo email lặp.

## 7. Open relay: tình huống cần tránh

Một máy chủ được xem là **open relay** khi nó cho phép người gửi không được ủy quyền dùng hạ tầng của mình chuyển thư tới các đích không do nó phụ trách.

```text
Client Internet không xác thực
            |
            | gửi tới bất kỳ domain ngoài nào
            v
     [SMTP relay mở]
            |
            +----> Domain A
            +----> Domain B
            +----> Domain C
```

Rủi ro gồm:

1. Tài nguyên CPU, lưu trữ queue, băng thông và chi phí gửi bị tiêu hao.
2. IP hoặc miền gửi bị đưa vào các hệ thống đánh giá danh tiếng bất lợi.
3. Thư giao dịch hợp lệ bị trì hoãn hoặc từ chối.
4. Khó phân biệt email chính đáng với traffic do bên lạ phát sinh.
5. Nhà cung cấp có thể tạm ngừng dịch vụ do phát hiện lạm dụng.

Một chính sách relay an toàn phải **phân biệt thư gửi đến miền mà máy chủ nhận quản lý với yêu cầu gửi hộ tới miền ngoài**, rồi chỉ cho phép yêu cầu gửi hộ từ danh tính hoặc nguồn đã được cấp quyền.

### Ví dụ quy tắc relay trong Postfix

Postfix là một MTA phổ biến. Một phần cấu hình minh họa cơ chế từ chối relay trái phép:

```ini
smtpd_relay_restrictions =
    permit_mynetworks,
    permit_sasl_authenticated,
    reject_unauth_destination
```

Ý nghĩa khái niệm:

- `permit_mynetworks`: cho phép nguồn kết nối thuộc mạng tin cậy được khai báo.
- `permit_sasl_authenticated`: cho phép client đã xác thực bằng SASL.
- `reject_unauth_destination`: từ chối các đích mà client không có quyền relay.

Đây là **đoạn cấu hình minh họa**, không phải cấu hình Postfix hoàn chỉnh. Để vận hành an toàn còn phải xác định chính xác `mynetworks`, `mydestination`, `relay_domains`, cổng submission, TLS, SASL, chính sách recipient/sender và các giới hạn khác. Đặc biệt, **không đặt `mynetworks` thành dải mạng quá rộng** vì có thể biến toàn bộ dải đó thành nguồn được quyền relay.

## 8. Đọc một phiên SMTP để hiểu quyền relay

Trong SMTP, máy chủ thường chưa thể quyết định đầy đủ quyền gửi chỉ từ kết nối TCP. Chính sách thường được áp dụng khi client xác thực và khi cung cấp `MAIL FROM`, `RCPT TO`.

### 8.1. Client chưa có quyền relay

Ví dụ minh họa giao tiếp với MTA công ty khi client chưa xác thực và muốn gửi đến miền bên ngoài:

```text
S: 220 mx.company.example ESMTP ready
C: EHLO client.example.org
S: 250-mx.company.example
S: 250 SIZE 10485760
C: MAIL FROM:<someone@other.example>
S: 250 2.1.0 Ok
C: RCPT TO:<customer@example.net>
S: 554 5.7.1 Relay access denied
```

Máy chủ có thể chấp nhận câu lệnh `MAIL FROM` nhưng từ chối ở `RCPT TO` vì người nhận thuộc miền ngoài và client chưa có quyền relay. Thứ tự kiểm tra thực tế tùy cấu hình máy chủ; không phải mọi server đều trả chính xác mã trên.

### 8.2. Client được quyền nộp thư

Ví dụ lược bỏ chi tiết xác thực và trao đổi TLS:

```text
S: 220 smtp.company.example ESMTP ready
C: EHLO spring-app.company.example
S: 250-STARTTLS
S: 250 SIZE 10485760
C: STARTTLS
S: 220 Ready to start TLS
    [Thiết lập TLS thành công]
C: EHLO spring-app.company.example
S: 250-AUTH PLAIN LOGIN
S: 250 SIZE 10485760
C: AUTH ...
S: 235 2.7.0 Authentication successful
C: MAIL FROM:<notifications@company.example>
S: 250 2.1.0 Ok
C: RCPT TO:<customer@example.net>
S: 250 2.1.5 Ok
C: DATA
S: 354 End data with <CR><LF>.<CR><LF>
C: From: notifications@company.example
C: To: customer@example.net
C: Subject: Order confirmed
C:
C: Your order has been confirmed.
C: .
S: 250 2.0.0 Queued as 12345
C: QUIT
S: 221 2.0.0 Bye
```

Đây là transcript **mang tính giáo dục**, không phải lời hướng dẫn gửi lệnh thật hay lộ credential. Chuỗi `AUTH ...` cố ý lược bỏ bí mật xác thực. Trên kết nối thật, những thông tin này không nên xuất hiện trong log ứng dụng.

Phản hồi `250 ... Queued` cho thấy server đã nhận trách nhiệm tiếp tục xử lý message, **chưa bảo đảm người nhận đã thấy thư trong Inbox**.

## 9. Cấu hình Spring Boot để gửi qua SMTP relay

Trong Spring Framework Mail, `JavaMailSender` giúp ứng dụng nộp email tới SMTP server được cấu hình. Quyền relay nằm phía server, nhưng ứng dụng phải kết nối đúng endpoint, đúng cổng và cung cấp credential hợp lệ.

### 9.1. Dependency

Với ứng dụng Spring Boot dùng Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

`spring-boot-starter-mail` cung cấp tích hợp gửi mail và cơ chế auto-configuration phù hợp của Spring Boot. Nếu dùng Spring Framework thuần, cần tự khai báo implementation của `JavaMailSender` và Jakarta Mail.

### 9.2. Cấu hình SMTP submission trên cổng 587

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM_ADDRESS}
```

Các biến môi trường cung cấp endpoint, tài khoản, mật khẩu và địa chỉ gửi. Ví dụ giả định SMTP server dùng **SMTP AUTH qua STARTTLS trên 587**. Chỉ đặt địa chỉ `from` đã được nhà cung cấp cấp quyền. Các timeout tính bằng mili giây giúp tránh treo quá lâu khi SMTP server không phản hồi.

Nếu provider yêu cầu **implicit TLS trên cổng 465**, cấu hình sẽ khác:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.ssl.enable]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
```

Hai ví dụ là **hai chế độ kết nối thay thế**, tùy SMTP server. Không tự giả định rằng cổng nào cũng hỗ trợ cả STARTTLS lẫn implicit TLS.

### 9.3. Service gửi email

Ví dụ một service gửi email văn bản qua `JavaMailSender`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public NotificationMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendOrderConfirmation(String customerEmail, String orderCode) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom(fromAddress);
        mail.setTo(customerEmail);
        mail.setSubject("Xác nhận đơn hàng " + orderCode);
        mail.setText("Đơn hàng " + orderCode + " đã được ghi nhận.");

        mailSender.send(mail);
    }
}
```

Đoạn code tạo và nộp email. Máy chủ SMTP vẫn là bên quyết định tài khoản đã xác thực có quyền gửi từ `fromAddress` tới `customerEmail` hay không.

Nếu cấu hình hostname, TLS, credential hoặc quyền gửi sai, lời gọi có thể ném một exception thuộc họ `MailException`, ví dụ `MailAuthenticationException` khi xác thực thất bại hoặc `MailSendException` khi xảy ra lỗi gửi. Chi tiết lỗi còn phụ thuộc thư viện Jakarta Mail và máy chủ SMTP. Không nên coi mọi ngoại lệ là lỗi có thể retry ngay.

### 9.4. Quyền gửi cần được thiết lập ở cả hai bên

| Phía ứng dụng Spring | Phía SMTP server / nhà cung cấp |
| --- | --- |
| Chọn hostname và cổng submission đúng | Bật endpoint tương ứng, cho phép mạng kết nối |
| Bật TLS đúng phương thức | Cấu hình TLS và chính sách xác thực |
| Gửi credential qua phương thức được hỗ trợ | Xác thực credential, kiểm tra quyền relay |
| Chọn địa chỉ `From` hợp lệ | Áp dụng danh sách sender/domain đã cho phép |
| Tôn trọng tốc độ và kích thước thư | Áp dụng quota, rate limit, content policy |
| Ghi nhận lỗi và trạng thái nghiệp vụ | Cung cấp phản hồi SMTP, queue, delivery/bounce event nếu có |

Không có cờ `spring.mail.*` nào có thể ép SMTP server từ chối chuyển tiếp phải chấp nhận một client không được cấp quyền.

## 10. Phân biệt lỗi cấu hình với lỗi chính sách relay

Khi làm việc với SMTP server, **mã và thông điệp phản hồi chỉ có tính gợi ý; nhà cung cấp có thể dùng mã cụ thể khác nhau**.

| Dấu hiệu | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `530 Authentication required` | Client chưa xác thực khi server yêu cầu | Kiểm tra cổng submission, `mail.smtp.auth` và cấu hình credential |
| `535 5.7.8 Authentication credentials invalid` | Thông tin xác thực hoặc cơ chế AUTH không được chấp nhận | Kiểm tra tài khoản, secret, quyền ứng dụng và chính sách provider |
| `554 5.7.1 Relay access denied` | Client không có quyền chuyển đến miền đích | Kiểm tra SMTP AUTH, allowlist, quyền relay và miền nhận |
| `550 5.7.1 Sender address rejected` | `MAIL FROM` hoặc `From` không nằm trong danh tính được phép | Dùng địa chỉ/miền đã xác minh hoặc cấu hình ủy quyền gửi |
| `421` hoặc `451` kèm thông báo giới hạn | Throttle, tạm thời vượt hạn ngạch hoặc lỗi phục vụ | Giảm tốc, phân phối queue và retry có backoff |
| `552 Message size exceeds ...` | Message vượt giới hạn kích thước | Giảm attachment hoặc dùng liên kết tải tệp |
| Gửi được nội bộ, lỗi khi gửi miền ngoài | Được quyền nhận/giao nội bộ nhưng chưa có quyền relay | Kiểm tra phân biệt local delivery và relay policy |
| Gửi thành công nhưng người nhận không thấy | Chuyển phát chưa hoàn tất, thư bị lọc hoặc nằm trong Spam | Xem message ID, queue, delivery/bounce và chính sách bên nhận |

### Một ví dụ chẩn đoán

Giả sử ứng dụng gửi từ `internal-app@company.example`:

1. Gửi tới `employee@company.example` được chấp nhận.
2. Gửi tới `customer@example.net` trả `Relay access denied`.
3. Đổi cấu hình sang SMTP submission endpoint đúng, dùng credential có quyền gửi.
4. Máy chủ bắt đầu chấp nhận email ra ngoài với danh tính được cấp phép.

Hai kết quả đầu không mâu thuẫn: máy chủ có thể nhận thư cho **miền nội bộ** mà không có nghĩa đã cấp quyền **relay tới miền ngoài**. Bước xử lý là kiểm tra quyền SMTP, không phải sửa nội dung `SimpleMailMessage`.

## 11. Chính sách relay cho môi trường phát triển, staging và production

Một hệ thống có thể sử dụng các phạm vi quyền gửi khác nhau:

| Môi trường | Chính sách gợi ý | Mục tiêu |
| --- | --- | --- |
| **Local development** | SMTP test server hoặc mail sink chỉ lưu thư kiểm tra, không relay ra Internet | Tránh gửi nhầm cho người thật |
| **Staging / QA** | Credential riêng, giới hạn người nhận hoặc miền được phép | Thử workflow email với phạm vi kiểm soát |
| **Production** | Credential riêng từng ứng dụng, sender/domain đã xác minh, quota và logging phù hợp | Gửi thông báo thật trong quyền đã cấp |

Ví dụ, nếu staging vô tình dùng chung credential production, một script test có thể vượt hạn ngạch hoặc gửi mail thật đến người dùng. Phân tách thông tin xác thực và chính sách người nhận giúp thu hẹp ảnh hưởng.

### Giữ bí mật credential và kiểm soát truy cập

- Không hardcode tên đăng nhập/mật khẩu SMTP trong Java hoặc commit chúng vào repository.
- Truyền secret qua hệ thống quản lý bí mật hoặc cấu hình môi trường của nền tảng triển khai.
- Không đưa giá trị `AUTH`, mật khẩu, token hoặc toàn bộ nội dung thư nhạy cảm vào log.
- Giới hạn quyền của mỗi credential vào ứng dụng và miền gửi cần thiết.
- Thu hồi/đổi credential khi phát hiện rò rỉ; kiểm tra lưu lượng gửi bất thường.

### Giới hạn tốc độ ở tầng ứng dụng

Ngoài quota của SMTP server, ứng dụng có thể có **hàng đợi gửi** và giới hạn concurrency để tránh tạo đột biến. Các nguyên tắc hữu ích:

1. Ghi trạng thái yêu cầu gửi bằng một định danh nghiệp vụ ổn định.
2. Tách quá trình tạo yêu cầu khỏi worker gửi khi cần bảo đảm khả năng phục hồi.
3. Giới hạn số kết nối và tốc độ gửi theo quota thực tế.
4. Khi nhận lỗi tạm thời, retry có **backoff** và giới hạn số lần.
5. Không retry vô hạn đối với lỗi quyền relay hoặc xác thực.
6. Theo dõi tình huống phản hồi không rõ để hạn chế email trùng.

Những nguyên tắc này không làm tăng quyền relay của ứng dụng; chúng giúp sử dụng quyền đã có một cách ổn định.

## 12. Relay, forwarding, bounce và delivery là các trạng thái khác nhau

Cùng là “chuyển thư”, nhưng có nhiều ý nghĩa:

- **SMTP relay:** hạ tầng được ủy quyền nhận và chuyển tiếp thư sang MTA khác trên đường gửi.
- **Forwarding:** một địa chỉ hoặc mailbox có quy tắc tự động chuyển nội dung đến địa chỉ khác; có thể phát sinh thêm chặng SMTP và chính sách xác thực.
- **Bounce / DSN:** thông báo lỗi khi thư không thể giao, có thể phát sinh sau một lần submission đã được chấp nhận.
- **Delivery:** hệ thống nhận thực hiện giao thư vào mailbox hoặc chấp nhận trách nhiệm giao tiếp theo.
- **Read/open:** người nhận sử dụng mail client truy cập nội dung, hoàn toàn khác với việc SMTP server chấp nhận thư.

Vì vậy, ứng dụng Spring nên phân biệt:

```text
Created
   |
   v
Submitted to SMTP server
   |
   +-- Rejected now -----------------> Submission failure
   |
   v
Accepted by SMTP server
   |
   +-- Temporary relay problem ------> Queue/retry
   |
   +-- Permanent later failure ------> Bounce/DSN (nếu có)
   |
   v
Delivered by receiving infrastructure
   |
   v
Visible to recipient (folder/client dependent)
```

Nếu provider có webhook phản ánh `delivered`, `bounced`, `deferred` hoặc sự kiện tương đương, có thể dùng chúng để cập nhật trạng thái nghiệp vụ. Kết quả `mailSender.send(...)` một mình không chứng minh được email đã tới hộp thư đích.

## 13. Tình huống tự luyện

### Tình huống A: Vì sao MTA nhận thư nội bộ nhưng không chuyển ra ngoài?

Ứng dụng chưa xác thực gửi email tới `staff@company.example` thành công, nhưng gửi tới `friend@example.net` bị `Relay access denied`.

**Giải thích:** máy chủ có thể có trách nhiệm nhận thư cho `company.example`, nhưng không cấp quyền relay đến miền bên ngoài cho client chưa xác thực. Cần dùng submission endpoint và danh tính được cấp quyền hoặc mạng tin cậy theo cấu hình.

### Tình huống B: Có SMTP AUTH rồi vẫn không gửi được với địa chỉ bất kỳ?

Ứng dụng dùng tài khoản `service-a` xác thực thành công, nhưng đặt `From: director@company.example` bị từ chối.

**Giải thích:** xác thực chứng minh client là `service-a`; chính sách có thể chỉ cho phép địa chỉ/miền đã ủy quyền. Cần chọn sender hợp lệ hoặc xin cấp đúng quyền gửi thay, không tắt chính sách xác thực miền.

### Tình huống C: Gửi 100 email liên tiếp, 20 email cuối nhận lỗi tạm thời

Một batch job tạo đột biến vượt hạn mức phút của nhà cung cấp.

**Giải thích:** relay có thể vẫn hợp lệ nhưng bị **rate limit**. Nên sử dụng queue, giảm tốc theo quota và retry có backoff đối với mã lỗi tạm thời. Không nên chuyển sang dùng một SMTP server không kiểm soát để né hạn mức.

### Tình huống D: SMTP trả `250 Queued` nhưng người nhận báo không có thư

**Giải thích:** server chỉ xác nhận đã tiếp nhận thông điệp. MTA có thể còn đang retry, thư bị lọc, bị bounce ở chặng sau hoặc đã nằm trong Spam. Cần kiểm tra thông tin giao thư của hạ tầng.

### Tình huống E: Chỉ IP nội bộ được phép relay, nhưng một service cloud mới bị từ chối

**Giải thích:** IP nguồn mới không nằm trong phạm vi tin cậy đã định nghĩa. Có thể chuyển service sang SMTP AUTH hoặc cập nhật allowlist một cách có kiểm soát; đồng thời rà soát phạm vi địa chỉ IP sau NAT.

## 14. Tóm tắt nguyên tắc thiết kế

**SMTP relay** là việc một server chuyển tiếp thư đến hệ thống khác. Muốn relay an toàn, máy chủ phải xác định **đích nhận mà mình phụ trách** và **client nào được quyền gửi hộ tới đích khác**. Quyền relay có thể cấp qua SMTP AUTH, allowlist nguồn tin cậy, quyền theo tài khoản/miền và chính sách người nhận; sau đó tiếp tục được điều chỉnh bằng quota, rate limit và kiểm tra chống lạm dụng.

Trong ứng dụng Spring, `JavaMailSender` cần cấu hình đúng host, cổng, TLS, credential và địa chỉ người gửi. Các cấu hình này giúp client làm đúng nhiệm vụ **submission**. Quyền relay, giới hạn lưu lượng và kết quả chuyển phát là trách nhiệm của SMTP server cùng các hệ thống email phía sau. Nắm rõ sự phân chia này giúp xử lý lỗi chính xác mà không nhầm “đã gửi từ ứng dụng” với “đã giao thư tới người nhận”.
