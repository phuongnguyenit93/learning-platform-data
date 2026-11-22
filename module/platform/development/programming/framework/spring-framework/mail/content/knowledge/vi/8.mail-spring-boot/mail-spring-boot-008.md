# Cấu hình debug protocol và tác động đến log

Khi tích hợp **Spring Framework Mail** trong ứng dụng **Spring Boot**, một lỗi “không gửi được email” có thể xuất phát từ nhiều lớp: dữ liệu địa chỉ, nội dung MIME, cấu hình Spring, kết nối TCP, TLS, đăng nhập SMTP, lệnh gửi thư hoặc chính sách của nhà cung cấp. Log ứng dụng thông thường đôi khi chỉ hiện một dòng như **MailSendException: Mail server connection failed**. Để quan sát các bước trao đổi thực sự giữa SMTP client và mail server, Jakarta Mail cung cấp chế độ **debug protocol**.

Chế độ này rất hữu ích khi chẩn đoán, nhưng thay đổi đáng kể **lượng và loại dữ liệu xuất hiện trong log**. Một bản trace có thể cho thấy server đang dùng, khả năng STARTTLS, phản hồi AUTH, địa chỉ người gửi/người nhận và những chi tiết từ quá trình gửi. Bật debug quá rộng hoặc quá lâu có thể gây lộ thông tin, làm nhiễu log vận hành và tăng chi phí lưu trữ.

Bài học giải thích cách bật debug protocol qua cấu hình Spring Boot, cách đọc các tín hiệu SMTP, sự khác nhau giữa log framework và trace giao thức, cùng cách sử dụng trace an toàn khi xử lý sự cố.

## 1. Trước hết phải phân biệt ba loại thông tin quan sát

Một ứng dụng Spring Boot có thể cùng lúc tạo ra:

1. **Log nghiệp vụ của ứng dụng**: ví dụ đã tạo mail job, chọn template, bắt đầu gửi thông báo, chuyển công việc sang trạng thái retry.
2. **Log của Spring và thư viện gửi thư**: ví dụ class ngoại lệ, nguyên nhân lỗi, hoạt động của component hoặc transport.
3. **Debug protocol SMTP**: thông tin chi tiết về cuộc hội thoại giữa SMTP client và mail server trong một giai đoạn gửi.

Ba lớp này phục vụ những câu hỏi khác nhau:

| Lớp quan sát | Câu hỏi chính | Ví dụ thông tin |
| --- | --- | --- |
| Log nghiệp vụ | “Công việc gửi nào gặp lỗi và nghiệp vụ bị ảnh hưởng thế nào?” | **mailJobId**, loại email, attempt, trạng thái |
| Log Spring Mail/transport | “Component nào và thao tác nào phát sinh ngoại lệ?” | **MailAuthenticationException**, **MailSendException**, cause |
| Debug protocol | “SMTP server đã nhận lệnh nào và phản hồi ra sao?” | **EHLO**, **STARTTLS**, **AUTH**, **MAIL FROM**, **RCPT TO**, **DATA**, các mã **2xx/4xx/5xx** |

**Bật logging DEBUG cho Spring không tự động tương đương với bật protocol debug của Jakarta Mail.** Ngược lại, bật **mail.debug** cũng không tạo ra hệ thống theo dõi nghiệp vụ, mã công việc hay các trạng thái delivery nếu ứng dụng chưa thiết kế những dữ liệu đó.

### Luồng gửi với những điểm có thể quan sát

~~~text
HTTP request / scheduled job
      |
      | [APPLICATION LOG] mailJobId, trạng thái, attempt
      v
Spring service -> JavaMailSender.send(...)
      |
      | [SPRING LOG / EXCEPTION] prepare, parse, send
      v
Jakarta Mail SMTP transport
      |
      | [PROTOCOL DEBUG]
      | DNS/TCP -> greeting -> EHLO -> STARTTLS
      | -> AUTH -> MAIL FROM -> RCPT TO -> DATA
      v
SMTP server chấp nhận hoặc từ chối
      |
      | [PROVIDER EVENT nếu có]
      v
Những bước chuyển phát tiếp theo
      |
      v
Mailbox đích / bounce / trì hoãn / lọc thư
~~~

Một dòng trace SMTP chỉ chứng minh điều transport **quan sát được tại thời điểm đó**. Ví dụ, **250** sau khi server chấp nhận nội dung thư là tín hiệu hoàn thành bước nộp thư, không phải bằng chứng thư đã xuất hiện trong Inbox hay người nhận đã đọc.

## 2. Bật protocol debug qua application.yml của Spring Boot

Spring Boot cho phép truyền các thuộc tính của Jakarta Mail thông qua **spring.mail.properties**. Thuộc tính quan trọng là **mail.debug**.

Ví dụ cấu hình cho môi trường chẩn đoán:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: demo-smtp-user
    password: "set-using-a-secret-provider"
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
      "[mail.debug]": true
      "[mail.debug.auth]": false
~~~

Các tên miền, tài khoản và giá trị chờ chỉ để minh họa. Ứng dụng thật cần sử dụng thông tin SMTP, phương thức TLS và giới hạn timeout phù hợp với provider. Mật khẩu phải được lấy từ cấu hình bí mật an toàn, không lưu mật khẩu thật trong mã nguồn hoặc tài liệu.

Ý nghĩa các thiết lập liên quan:

| Thuộc tính | Công dụng |
| --- | --- |
| **spring.mail.host** | Máy chủ SMTP mà ứng dụng định kết nối |
| **spring.mail.port** | Cổng SMTP, ví dụ 587 khi dùng STARTTLS theo cấu hình provider |
| **mail.smtp.auth** | Yêu cầu thực hiện SMTP AUTH theo cấu hình |
| **mail.smtp.starttls.enable** | Cho phép transport nâng cấp kết nối bằng STARTTLS |
| **mail.smtp.starttls.required** | Yêu cầu STARTTLS thành công trước khi tiếp tục trong cấu hình này |
| **mail.smtp.connectiontimeout** | Timeout kết nối TCP, đơn vị thường là mili giây |
| **mail.smtp.timeout** | Timeout đọc phản hồi/dữ liệu từ socket |
| **mail.smtp.writetimeout** | Timeout khi ghi qua socket |
| **mail.debug** | Bật thông tin debug của Jakarta Mail session/transport |
| **mail.debug.auth** | Điều chỉnh khả năng hiện thông tin AUTH trong debug ở implementation hỗ trợ; nên giữ **false** |

Trong YAML, dạng **"[mail.debug]"** là khóa của map **spring.mail.properties**. Cặp dấu ngoặc vuông được đặt trong dấu nháy để tránh sự nhầm lẫn trong cách binding khóa có chứa dấu chấm của Spring Boot. Kết quả mong muốn là property Jakarta Mail có tên chính xác **mail.debug**.

**Không có một property Spring Boot tên là spring.mail.debug với cùng ý nghĩa được bảo đảm trong mọi cấu hình.** Cách truyền property tới Jakarta Mail rõ ràng là dùng **spring.mail.properties["mail.debug"]**.

### Vì sao đặt mail.debug.auth: false?

Trace AUTH có thể chứa thông tin nhạy cảm, đặc biệt nếu người cấu hình bật thêm mức trace chi tiết hoặc dùng implementation cho phép in thông tin đăng nhập. **mail.debug.auth** được một số implementation Jakarta Mail SMTP dùng để điều khiển debug của quá trình xác thực; giá trị **false** là lựa chọn thận trọng và không nên chuyển sang **true** trên hệ thống chứa credential thật.

Ngay cả khi **mail.debug.auth=false**, đừng coi trace là vô hại: nó vẫn có thể chứa địa chỉ, tên host, phản hồi server, định danh nội bộ, và ở một số mức trace/implementation có thể có thêm phần dữ liệu thư. Chính sách bảo vệ log phải áp dụng cho **toàn bộ trace**, không chỉ dòng AUTH.

## 3. Chỉ bật debug trong profile chẩn đoán

Trong quá trình phát triển, có thể tạo một profile riêng, ví dụ **mail-debug**, để bật protocol debug có chủ đích.

**application.yml** chứa cấu hình thông thường:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: demo-smtp-user
    password: "set-using-a-secret-provider"
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
      "[mail.debug]": false
~~~

**application-mail-debug.yml** chỉ chứa các phần cần ghi đè khi điều tra:

~~~yaml
spring:
  mail:
    properties:
      "[mail.debug]": true
      "[mail.debug.auth]": false

logging:
  level:
    org.springframework.mail: DEBUG
~~~

Khi chạy ứng dụng với profile **mail-debug** được kích hoạt, Spring Boot sẽ nạp cấu hình profile tương ứng. Ví dụ tham số chạy:

~~~text
--spring.profiles.active=mail-debug
~~~

Việc có profile riêng giúp nhìn thấy rõ môi trường nào đang bật trace, tránh để debug protocol vô tình tồn tại trong cấu hình mặc định của production.

Nếu ứng dụng dùng nhiều profile cùng lúc, cần hiểu thứ tự và quy tắc ưu tiên cấu hình của Spring Boot. Một property được ghi đè ở nguồn có độ ưu tiên cao hơn có thể thay đổi giá trị **mail.debug**. Khi một cấu hình “không có tác dụng”, hãy kiểm tra **effective configuration** của ứng dụng, các profile đang active và cấu hình Session có được cấp bởi một nguồn khác hay không.

### Trường hợp JavaMail Session được cấu hình bên ngoài

Một số ứng dụng dùng **Spring Boot spring.mail.jndi-name** để lấy **Jakarta Mail Session** từ JNDI/application server, hoặc tự khai báo bean **JavaMailSender**. Trong những trường hợp đó, nguồn cấu hình thực sự của Session có thể nằm ngoài **spring.mail.properties** thường dùng.

Nếu bật **mail.debug** trong YAML mà không thấy trace, cần xác định **JavaMailSender đang sử dụng Session nào**, ai tạo và quản lý nó, thay vì tiếp tục thêm ngẫu nhiên các mức **logging.level**.

## 4. logging.level và mail.debug là hai công tắc khác nhau

Spring Boot có hệ thống logging ứng dụng, thường qua SLF4J và backend như Logback. Có thể điều chỉnh mức log theo logger name:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.mail: DEBUG
~~~

Cấu hình trên làm tăng mức chi tiết đối với logger thuộc **org.springframework.mail** khi có lời gọi ghi log phù hợp. Nó **không nhất thiết** khiến Jakarta Mail in transcript các lệnh SMTP.

Trong khi đó:

~~~yaml
spring:
  mail:
    properties:
      "[mail.debug]": true
~~~

yêu cầu Jakarta Mail **Session** bật chế độ debug. Tùy phiên bản và implementation (ví dụ JavaMail/Jakarta Mail hoặc Angus Mail), dữ liệu debug có thể đi qua luồng debug của Session và/hoặc hạ tầng logger riêng của thư viện.

| Cấu hình | Mục tiêu | Có bảo đảm xuất hiện lệnh SMTP? |
| --- | --- | --- |
| **logging.level.root=DEBUG** | Tăng log cho nhiều logger ứng dụng | **Không**; còn phụ thuộc thư viện gửi và logger |
| **logging.level.org.springframework.mail=DEBUG** | Tăng log của package Spring Mail nếu được phát ra | **Không**; không tự bật Jakarta Mail protocol debug |
| **spring.mail.properties["mail.debug"]=true** | Bật debug của Jakarta Mail Session/transport | **Thường cung cấp trace transport phù hợp**, tùy implementation |
| Debug logging của provider qua **java.util.logging** hoặc logger của implementation | Quan sát nội bộ của thư viện transport | Phụ thuộc tên logger, level, handler/bridge và phiên bản |

Đừng coi **logging.level.root=DEBUG** là giải pháp chung cho lỗi mail. Nó có thể tạo lượng log rất lớn từ toàn ứng dụng nhưng vẫn thiếu chi tiết SMTP mong muốn.

### Vì sao có trace nhưng không có định dạng log của Spring?

**Jakarta Mail Session** hỗ trợ debug output riêng, thường mặc định xuất tới **System.out** (hoặc được provider/ứng dụng cấu hình theo cách khác). Vì vậy, có thể thấy những dòng bắt đầu bằng **DEBUG:** hoặc **DEBUG SMTP:** trong console mà **không có timestamp, thread, MDC/correlation ID và định dạng Logback** như log Spring.

Ví dụ hai dòng dưới đây thuộc hai cơ chế:

~~~text
2026-11-12 10:00:00.001 INFO  [mail-worker-1] MailJobService -
  Submitting mailJobId=MAIL-782 attempt=1

DEBUG SMTP: trying to connect to host "smtp.example.test", port 587
~~~

Dòng đầu do logger ứng dụng ghi theo pattern riêng; dòng thứ hai có thể đến từ debug output của thư viện mail. Việc cả hai cùng hiện trên terminal **không có nghĩa chúng sử dụng cùng logging pipeline**.

### System.out xuất hiện ở đâu khi chạy Spring Boot?

Tùy cách triển khai, debug output có thể xuất hiện trong:

- Console của IDE khi chạy ứng dụng cục bộ.
- Standard output của tiến trình Java.
- Log được Docker hoặc Kubernetes container runtime thu thập từ stdout.
- Log được một process manager, runtime platform hoặc cloud logging collector chuyển tiếp.
- Log của test/CI nếu chạy integration test có bật mail debug.

Do đó, một cấu hình debug tưởng như chỉ dành cho lập trình viên có thể khiến thông tin protocol đi vào **hệ thống log tập trung** với thời hạn lưu giữ và quyền truy cập rộng hơn dự kiến.

Nếu muốn đưa debug output qua SLF4J/Logback, cần có cơ chế cầu nối hoặc cấu hình output của Session/provider tương ứng. **Không giả định việc chỉnh logging.level sẽ tự chuyển một PrintStream của Jakarta Mail thành log có MDC**. Đặc biệt, việc tự chuyển các dòng protocol vào logger phải đi kèm kiểm soát truy cập, mức độ nhạy cảm và cơ chế che dữ liệu.

## 5. Một phiên SMTP debug được diễn giải thế nào?

Sau khi bật **mail.debug**, tùy implementation và mức trace, một đoạn output có thể thể hiện trình tự như sau. Đây là **ví dụ rút gọn, đã ẩn dữ liệu nhạy cảm**, không phải transcript chính xác của mọi server hoặc mọi bản Jakarta Mail:

~~~text
DEBUG SMTP: trying to connect to host "smtp.example.test", port 587
S: 220 smtp.example.test ESMTP ready
C: EHLO app.example.test
S: 250-smtp.example.test
S: 250-STARTTLS
S: 250 AUTH PLAIN LOGIN
C: STARTTLS
S: 220 Ready to start TLS
[TLS handshake hoàn tất]
C: EHLO app.example.test
S: 250-smtp.example.test
S: 250 AUTH PLAIN LOGIN
[SMTP AUTH đã thực hiện; chi tiết xác thực bị ẩn]
S: 235 2.7.0 Authentication successful
C: MAIL FROM:<sender@example.test>
S: 250 Sender accepted
C: RCPT TO:<recipient@example.test>
S: 250 Recipient accepted
C: DATA
S: 354 End data with <CRLF>.<CRLF>
[headers và nội dung email đã được ẩn]
C: .
S: 250 2.0.0 Queued as Q12345
~~~

Nhãn **C:** và **S:** được thêm để giải thích client/server trong ví dụ. Debug output thực tế có thể khác định dạng, số lượng dòng và mức độ chi tiết.

### Đọc các mốc quan trọng

| Mốc | Đang xảy ra điều gì? | Khi lỗi cần kiểm tra |
| --- | --- | --- |
| Kết nối host:port | SMTP client mở đường tới server | Host, DNS, cổng, firewall, timeout |
| **220 greeting** | Server chào khi bắt đầu phiên | Server sẵn sàng hay từ chối kết nối |
| **EHLO** | Client giới thiệu và hỏi khả năng server | Các extension như STARTTLS, AUTH, SIZE |
| **STARTTLS** | Yêu cầu nâng cấp kết nối sang TLS | Chứng chỉ, trust, host name và bắt buộc TLS |
| **AUTH** | Xác thực theo cơ chế được phép | Credential, quyền tài khoản, cơ chế hỗ trợ |
| **MAIL FROM** | Khai báo envelope sender | Domain/quyền gửi, chính sách provider |
| **RCPT TO** | Đề nghị giao thư tới một recipient | Địa chỉ bị từ chối, giới hạn, chính sách |
| **DATA** rồi **354** | Server cho phép gửi nội dung thư | Kích thước, cấu trúc, giới hạn kết nối |
| **250** sau DATA | Server chấp nhận nội dung ở bước nộp thư | Đối chiếu queue/message ID nếu server cung cấp |

Một server có thể có nhiều kết quả **RCPT TO** trong cùng một email: chấp nhận người nhận này nhưng từ chối người khác. Những phản hồi đó không nên bị gộp thành một kết luận “tất cả địa chỉ hợp lệ” hoặc “tất cả đều thất bại”.

Nếu server cho biết **Queued as Q12345**, mã đó có thể dùng đối chiếu với log của provider. Nó không phải định danh toàn cầu được mọi SMTP server giữ nguyên, và cũng không tự chứng minh thư đã được phát đến Inbox cuối cùng.

### Điều debug protocol không cho biết

Ngay cả một transcript đầy đủ của bước nộp SMTP cũng **không bảo đảm** cung cấp:

- Trạng thái thư cuối cùng trong hộp thư người nhận.
- Thư có bị đưa vào Spam hay bị hệ thống nhận chặn sau đó không.
- Người nhận có mở hoặc đọc email không.
- Mọi bước alias/forwarding ở máy chủ trung gian.
- Kết quả cuối cùng nếu kết nối bị mất trước lúc client nhận được phản hồi.

Muốn theo dõi sau bước SMTP submission, có thể cần **delivery events**, webhook, DSN/bounce và công cụ truy vết của nhà cung cấp email. Protocol debug là **quan sát cục bộ của một phiên giao thức**, không phải hệ thống delivery tracking hoàn chỉnh.

## 6. Chẩn đoán sự cố theo vị trí trace dừng lại

Mục tiêu của protocol debug là **xác định bước cuối cùng mà ứng dụng và server trao đổi được**, rồi đối chiếu với ngoại lệ Spring/Jakarta Mail và cấu hình. Không nên bắt đầu bằng việc bật mọi logger ở mức TRACE mà không có câu hỏi cụ thể.

### Trường hợp A: Không thấy bất kỳ dòng SMTP nào

Nguyên nhân có thể là:

- Logic nghiệp vụ không gọi **JavaMailSender.send(...)** vì điều kiện đầu vào, validation hoặc một exception trước đó.
- Profile **mail-debug** chưa được kích hoạt hoặc thuộc tính **mail.debug** bị ghi đè về **false**.
- Ứng dụng dùng **JavaMailSender** bean hoặc **Session** tự cấu hình/JNDI, nên property ở YAML không đi vào Session đang được sử dụng.
- Debug output chuyển sang luồng hoặc logger khác với nơi đang quan sát.
- Ứng dụng không kết nối SMTP mà dùng một adapter/provider API khác.

**Cách điều tra:** trước hết ghi một log nghiệp vụ ngay trước lời gọi gửi bằng định danh công việc, rồi xác định component gửi mail thực sự đang hoạt động. Nếu trace vẫn không có, kiểm tra profile, effective properties, nguồn tạo Session và đích xuất log. Tránh bắt đầu bằng suy đoán rằng “SMTP server đã không nhận email” vì lúc này có thể **chưa hề có kết nối**.

### Trường hợp B: Lỗi trước khi thấy lời chào 220

Ví dụ:

~~~text
DEBUG SMTP: trying to connect to host "smtp.example.test", port 587
java.net.ConnectException: Connection refused
~~~

Chưa có lời chào SMTP nghĩa là lỗi có thể nằm ở DNS, mạng, port, firewall, proxy hoặc dịch vụ mail chưa lắng nghe. Tăng **logging.level.org.springframework.mail** chưa chắc cung cấp thêm bằng chứng; cần kiểm tra hostname, kết nối và firewall/network policy tại môi trường chạy.

Nếu log chỉ ra **UnknownHostException**, trọng tâm là DNS/tên host. Nếu là **connect timeout**, trọng tâm thường là đường mạng hoặc phía server không phản hồi kịp. Nếu là **Connection refused**, máy đích hoặc thiết bị trung gian có thể từ chối kết nối đến port đó.

### Trường hợp C: Kết nối được nhưng STARTTLS thất bại

Ví dụ giả định:

~~~text
S: 220 SMTP ready
C: EHLO app.example.test
S: 250-smtp.example.test
S: 250 AUTH PLAIN LOGIN
[Không thấy STARTTLS trong danh sách khả năng]
~~~

Nếu ứng dụng cấu hình **mail.smtp.starttls.required=true**, transport có thể thất bại vì server không thông báo hoặc không cho phép STARTTLS. Nếu server thông báo STARTTLS nhưng TLS handshake báo lỗi, cần xem certificate, trust chain, host name hoặc cấu hình phiên bản giao thức liên quan.

**Không tắt kiểm tra TLS hoặc bỏ yêu cầu STARTTLS chỉ để làm email “gửi được”.** Cần đối chiếu port và cơ chế bảo mật được nhà cung cấp hỗ trợ: **STARTTLS trên một kết nối SMTP thông thường** khác với **implicit TLS/SMTPS**. Cấu hình sai loại TLS cũng có thể dẫn đến lỗi kết nối hoặc handshake khó hiểu.

Lưu ý: trace của application/mail transport có thể cho biết các lệnh giao thức trước và sau TLS, nhưng không nhất thiết thể hiện đầy đủ mọi chi tiết TLS handshake. Cần dùng các tín hiệu TLS hoặc lỗi certificate thích hợp khi điều tra sâu hơn.

### Trường hợp D: AUTH thất bại

Một phần trace có thể là:

~~~text
C: EHLO app.example.test
S: 250 AUTH PLAIN LOGIN
[Các bước AUTH bị ẩn]
S: 535 5.7.8 Authentication failed
~~~

Lúc này, cần kiểm tra:

- Username và password/token được cấu hình đúng chưa.
- Tài khoản có được quyền sử dụng SMTP AUTH không.
- Provider yêu cầu app password, OAuth2 hoặc cơ chế AUTH khác không.
- Kết nối có đáp ứng chính sách TLS trước khi xác thực không.
- Tài khoản có bị giới hạn hoặc khóa do chính sách không.

Không nên bật **mail.debug.auth=true** để “xem cho rõ mật khẩu” trong log. Xác minh credential qua nguồn quản lý bí mật và công cụ kiểm tra được cấp quyền; tránh để bất kỳ giá trị xác thực nào đi vào log tập trung.

### Trường hợp E: MAIL FROM hoặc RCPT TO bị từ chối

Ví dụ:

~~~text
C: MAIL FROM:<notify@example.test>
S: 250 Sender accepted
C: RCPT TO:<member@recipient.test>
S: 550 5.7.1 Recipient rejected by policy
~~~

Trace chỉ ra server trả lỗi ở bước **RCPT TO**, cho thấy nên kiểm tra recipient, policy hoặc giới hạn gửi. Nhưng **mã 550 không luôn có nghĩa mailbox không tồn tại**; server có thể từ chối do quy định chống spam, quyền gửi hoặc domain.

Nếu có nhiều recipient, một server có thể nhận người này và từ chối người khác. Vì vậy, cần xem từng phản hồi **RCPT TO** và dữ liệu exception/transport; không gộp một mã lỗi thành kết luận cho toàn bộ danh sách người nhận.

### Trường hợp F: DATA thất bại hoặc timeout sau khi gửi

Ví dụ:

~~~text
C: DATA
S: 354 Continue
[Client truyền nội dung thông điệp]
C: .
[Không quan sát được phản hồi cuối cùng do mất kết nối]
~~~

Đây là một tình huống quan trọng. Máy chủ **có thể** đã nhận đầy đủ nội dung và đưa thư vào hàng đợi, nhưng client mất kết nối trước khi nhận phản hồi. Phía Spring có thể báo **MailSendException**/timeout, trong khi trạng thái tiếp nhận phía server vẫn **không chắc chắn**.

Không thể suy ra “chưa gửi” chỉ vì thiếu dòng **250** trong log client. Retry ngay cùng một email có thể tạo bản sao. Cần đối chiếu provider logs, mã thông điệp nếu có, trạng thái job và chính sách retry đã được thiết kế.

Ngược lại, nếu server trả mã từ chối rõ ràng sau DATA, cần đọc phản hồi và dữ liệu provider để biết lỗi kích thước, nội dung, giới hạn hoặc chính sách. Không coi mọi lỗi tại DATA là lỗi recipient.

### Trường hợp G: SMTP báo thành công nhưng người nhận chưa thấy thư

Trace kết thúc bằng phản hồi thành công sau **DATA**. Điều này thường chỉ chứng minh máy chủ ở chặng nộp thư đã **chấp nhận thông điệp để xử lý tiếp**, không chứng minh đường phát tới Inbox đã hoàn thành.

Khi đó cần chuyển từ **SMTP submission diagnostics** sang **delivery diagnostics**: kiểm tra event, bounce, spam classification, cấu hình miền gửi, SPF/DKIM/DMARC và tình trạng mailbox phía nhận. Việc giữ **mail.debug=true** thêm nhiều giờ thường không tạo thêm thông tin về một thư đã rời khỏi client.

## 7. Tác động của protocol debug đến dữ liệu trong log

Debug protocol có thể ghi lại thông tin mà ứng dụng bình thường không đưa vào log, hoặc ghi một cách ít cấu trúc hơn. Mức độ cụ thể phụ thuộc thư viện, phiên bản, mức trace và điểm xuất log.

| Loại dữ liệu | Vì sao có thể xuất hiện? | Tác động cần lưu ý |
| --- | --- | --- |
| Tên SMTP host, port và server greeting | Kết nối, EHLO, phản hồi SMTP | Tiết lộ chi tiết hạ tầng và nhà cung cấp |
| **MAIL FROM** / **RCPT TO** | Lệnh gửi và lựa chọn recipient | Có thể chứa email cá nhân, định danh nội bộ |
| Mã lỗi, lời nhắn từ server | Phản hồi 4xx/5xx hoặc extended status | Có thể chứa địa chỉ hoặc chính sách nội bộ của provider |
| Thông tin liên quan **AUTH** | Quá trình xác thực SMTP | Nguy cơ rò credential/token nếu bật debug quá sâu hoặc cấu hình không phù hợp |
| Headers và nội dung thư | Một số mức trace hoặc đường log transport có thể ghi dữ liệu trao đổi | Có thể chứa tên, số đơn hàng, liên kết có token, nội dung riêng tư |
| Payload attachment được mã hóa | Có thể xuất hiện khi trace dữ liệu gửi ở mức rất chi tiết | Base64 **có thể giải mã được**, không phải che giấu dữ liệu |
| Mã hàng đợi, Message-ID hoặc diagnostic ID | Server phản hồi khi nhận thông điệp | Dữ liệu dùng để tương quan nhưng vẫn có thể nhạy cảm |

**Không coi Base64 là cách bảo mật dữ liệu.** Nếu log chứa raw MIME hoặc payload attachment Base64, người có quyền đọc log có thể giải mã về byte ban đầu. Một liên kết xác minh tài khoản xuất hiện trong body cũng có thể còn hiệu lực trong khoảng thời gian người khác truy cập được log.

### Những nguy cơ không nằm ở thư viện

Ngay cả khi Jakarta Mail không in password theo cấu hình mặc định, dữ liệu nhạy cảm vẫn có thể bị ghi bởi:

- Mã ứng dụng tự log toàn bộ **MimeMessage**, request DTO hoặc cấu hình SMTP.
- AOP/interceptor log arguments và exceptions mà không lọc dữ liệu.
- HTTP/gateway diagnostics nếu hệ thống gửi mail qua một provider API song song.
- Cơ chế thu thập stdout tự động và đẩy lên hệ thống log chung.
- Một trình chẩn đoán do kỹ sư bật ngoài application.yml.

Do đó, giải pháp không chỉ là đặt **mail.debug.auth=false**, mà còn là xác định **dữ liệu nào có thể xuất hiện, ai có quyền xem, lưu bao lâu và cách xóa/che trước khi chia sẻ**.

### Khuyến nghị vận hành

1. **Mặc định tắt protocol debug** ở môi trường chứa dữ liệu và credential thật.
2. Khi cần chẩn đoán, ưu tiên **mail server thử nghiệm** và địa chỉ/sự kiện giả lập không nhạy cảm.
3. Nếu phải điều tra môi trường vận hành, giới hạn phạm vi và thời gian bật trace; ghi rõ ai chịu trách nhiệm tắt.
4. Giữ **mail.debug.auth=false**; không bật chế độ phơi bày thông tin xác thực.
5. Giới hạn quyền đọc log, thời hạn lưu trữ và việc xuất/chia sẻ log.
6. **Ẩn địa chỉ, token, nội dung và định danh nhạy cảm** trước khi gửi transcript cho người khác.
7. Sau khi có bằng chứng, **tắt debug** và kiểm tra phiên bản ứng dụng/cấu hình đang chạy thực sự đã dùng giá trị tắt.

Không nên dán một đoạn transcript chứa nội dung giao dịch thật vào issue công khai hoặc kênh thảo luận chỉ vì đoạn đó có tiền tố **DEBUG SMTP**.

## 8. Tác động đến dung lượng, hiệu năng và khả năng đọc log

Một API xử lý vài mail mỗi phút và một worker gửi hàng chục nghìn mail mỗi giờ có mức độ ảnh hưởng khác nhau khi bật debug protocol.

### Số lượng log tăng theo số phiên và số người nhận

Mỗi phiên có thể chứa nhiều lệnh:

~~~text
EHLO
STARTTLS
EHLO
AUTH
MAIL FROM
RCPT TO (lặp cho từng recipient)
DATA
phản hồi
QUIT
~~~

Tùy cấu hình, transport có thể tái sử dụng một kết nối hoặc tạo phiên mới cho các lần gửi. Với danh sách nhiều người nhận, số dòng **RCPT TO** và phản hồi tương ứng tăng lên. Nếu bật mức trace ghi thêm payload, kích thước log có thể còn phụ thuộc **kích thước nội dung và attachment**.

Vì vậy, tác động có thể gồm:

- **Chi phí ghi và lưu log**: stdout, log collector, storage và indexing nhận thêm dữ liệu.
- **Áp lực I/O**: việc xuất nhiều dòng debug có thể gây overhead cho tiến trình.
- **Nhiễu thông tin**: lỗi nghiệp vụ quan trọng bị chìm trong hàng nghìn dòng protocol.
- **Khó tương quan**: nhiều worker gửi mail đồng thời làm output xen kẽ.
- **Nguy cơ kéo dài sự cố**: log collector hoặc đĩa bị quá tải trong khi hệ thống vốn đang lỗi mail.

Không nên dùng protocol debug như một **metric hoặc audit log thường trực**. Hệ thống vận hành nên có log nghiệp vụ có cấu trúc và chỉ số quan sát bền vững; trace SMTP là công cụ điều tra chuyên sâu theo thời điểm.

### Tại sao nhiều phiên SMTP có thể khó đọc?

Khi có nhiều luồng gửi thư:

~~~text
Worker A -> EHLO
Worker B -> EHLO
Worker A -> MAIL FROM
Worker B -> AUTH
Worker A -> RCPT TO
...
~~~

Nếu output không chứa thread ID hoặc mail job ID đáng tin cậy, nhìn vào các dòng gần nhau trong cùng console chưa chắc biết chúng thuộc **cùng một email**. Thậm chí một transport có thể mở kết nối và ghi trace ở thời điểm khác với log nghiệp vụ của request.

Vì vậy, trước khi bật debug, nên ghi log ứng dụng có **mailJobId**, thời điểm bắt đầu, kết quả, số lần thử và thông tin timeout. Chỉ khi cần mới dùng protocol trace để hiểu một tầng lỗi cụ thể.

## 9. Log nghiệp vụ nên bổ trợ protocol debug như thế nào?

Ứng dụng có thể ghi thông tin gọn và có cấu trúc quanh lời gọi **JavaMailSender.send(...)**, thay vì phụ thuộc vào toàn bộ transcript:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;
import org.springframework.stereotype.Service;

@Service
public class InstrumentedMailService {
    private static final Logger log =
            LoggerFactory.getLogger(InstrumentedMailService.class);

    private final JavaMailSender mailSender;

    public InstrumentedMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(
            String mailJobId,
            int attempt,
            String recipient
    ) {
        long startedAt = System.nanoTime();

        MimeMessagePreparator preparator = mime -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, false, "UTF-8");
            helper.setFrom("notifications@example.test");
            helper.setTo(recipient);
            helper.setSubject("Chào mừng");
            helper.setText("Tài khoản của bạn đã được tạo.", false);
        };

        log.info(
                "Mail submission started: jobId={} attempt={} type={}",
                mailJobId, attempt, "WELCOME"
        );

        try {
            mailSender.send(preparator);

            long elapsedMs =
                    (System.nanoTime() - startedAt) / 1_000_000;
            log.info(
                    "Mail submitted: jobId={} attempt={} elapsedMs={}",
                    mailJobId, attempt, elapsedMs
            );
        } catch (MailException ex) {
            long elapsedMs =
                    (System.nanoTime() - startedAt) / 1_000_000;
            log.warn(
                    "Mail submission failed or uncertain: "
                    + "jobId={} attempt={} elapsedMs={} exceptionType={}",
                    mailJobId,
                    attempt,
                    elapsedMs,
                    ex.getClass().getSimpleName()
            );
            throw ex;
        }
    }
}
~~~

Ví dụ này minh họa một số nguyên tắc:

- Log chứa **mailJobId**, loại thông báo, lần thử và thời gian thực hiện.
- Không đưa địa chỉ email người nhận hay nội dung thư vào mỗi dòng log.
- Chỉ ghi **submitted** khi lời gọi gửi hoàn tất mà không báo lỗi; **submitted không đồng nghĩa delivered**.
- Khi có exception, ghi nhận **thất bại hoặc chưa rõ trạng thái**, vì một timeout có thể xảy ra sau khi provider đã nhận dữ liệu.
- Đưa ngoại lệ lên tầng worker/controller để quyết định retry hoặc thông báo lỗi theo nghiệp vụ.

Ở một ứng dụng thực tế, nên lưu kết quả vào mail job hoặc outbox để có thể phục hồi sau khi tiến trình dừng. **Log chỉ mô tả sự kiện đã quan sát, không phải bộ lưu trạng thái xử lý công việc đáng tin cậy**.

Nếu cần stack trace để điều tra, tầng xử lý cuối cùng có thể ghi exception theo chính sách logging và bảo vệ dữ liệu của tổ chức; tránh nhiều tầng cùng log lặp lại một stack trace khổng lồ.

### Correlation ID và giới hạn của debug output

Trong các ứng dụng dùng MDC của SLF4J, log ứng dụng có thể tự động mang **requestId** hoặc **mailJobId**. Nhưng các dòng **Session debug** viết trực tiếp tới một PrintStream không tự động nhận cùng MDC và pattern của Logback.

Đối với công việc gửi nền hoặc **@Async**, dữ liệu MDC ở luồng xử lý request cũng không nhất thiết được truyền nguyên vẹn sang worker. Cần thiết kế cơ chế truyền correlation context thích hợp, hoặc luôn dùng **job ID** được lưu cùng công việc.

Không nên kết luận hai dòng SMTP gần nhau trong log là cùng phiên chỉ dựa trên timestamp. Hãy đối chiếu log ứng dụng, thông tin kết nối và dấu vết provider nếu cần.

## 10. Những cấu hình dễ nhầm khi điều tra SMTP

### Bật debug không đồng nghĩa bật hoặc sửa TLS

**mail.debug=true** chỉ thay đổi khả năng quan sát; nó không tự kích hoạt STARTTLS, không đổi port và không sửa lỗi xác thực.

Các lựa chọn thường thấy:

| Kiểu kết nối | Cấu hình thường gặp | Điểm cần nhớ |
| --- | --- | --- |
| SMTP + STARTTLS | Cổng **587** theo cấu hình provider; **mail.smtp.starttls.enable=true** | Kết nối bắt đầu ở SMTP thông thường rồi nâng cấp sang TLS |
| SMTP yêu cầu STARTTLS | Thêm **mail.smtp.starttls.required=true** | Nếu không thể đàm phán STARTTLS, việc gửi phải thất bại theo chính sách |
| SMTP dùng TLS ngay từ đầu | Thường gặp cổng **465**; với SMTP transport có thể dùng **mail.smtp.ssl.enable=true** | Cơ chế implicit TLS khác với lệnh STARTTLS |
| SMTP không xác thực | **mail.smtp.auth=false** khi provider cho phép | Không nên dùng cấu hình này để bỏ qua yêu cầu AUTH của provider |

Các port chỉ là quy ước phổ biến. Nhà cung cấp có thể công bố thông số khác; cần lấy thông tin chính thức của dịch vụ đang sử dụng.

Khi trace báo lỗi ở TLS handshake, sửa đúng cấu hình bảo mật cho loại kết nối. Không nên giải quyết bằng cách tắt TLS hoặc vô hiệu hóa kiểm tra chứng chỉ.

### mail.debug không phải mail.smtp.debug

Thuộc tính thường dùng để bật debug của Jakarta Mail Session là **mail.debug**. Không nên đoán rằng thêm một property tự tạo như **mail.smtp.debug=true** sẽ có tác dụng tương đương; các thuộc tính của transport phải đúng tên được implementation hỗ trợ.

Lý do nằm ở cách Jakarta Mail sử dụng **Session** và **Transport**:

~~~text
Spring Boot MailProperties
       |
       | spring.mail.properties
       v
Jakarta Mail Session
       |
       | mail.debug = true
       v
Provider / SMTP transport debug
       |
       v
Output của Session/provider
~~~

Ứng dụng có thể thiết lập **Session.setDebug(true)** bằng mã Java, nhưng với Spring Boot, **cấu hình qua profile** thường dễ quan sát, dễ tái tạo và dễ tắt hơn. Đặc biệt, thay đổi trạng thái debug của một **Session được chia sẻ** giữa nhiều worker ở runtime có thể ảnh hưởng những luồng gửi khác đang dùng cùng Session.

Nếu một thư viện hoặc cấu hình khác gọi **setDebug(true)** trực tiếp, thay đổi YAML về **false** chưa chắc đã tắt mọi nguồn protocol trace. Cần tìm đúng nơi tạo và cấu hình Session, đồng thời kiểm tra các logger/handler của provider.

### spring.mail.test-connection chỉ kiểm tra kết nối

Spring Boot có lựa chọn **spring.mail.test-connection** để thử kết nối mail server tại thời điểm khởi động trong những cấu hình phù hợp:

~~~yaml
spring:
  mail:
    test-connection: true
~~~

Tùy cấu hình, việc thử kết nối có thể khiến ứng dụng thất bại ở lúc startup nếu không kết nối được. Khi **mail.debug** đang bật, ta có thể thấy output liên quan tới quá trình kết nối/khởi tạo.

Tuy nhiên, **test-connection thành công không chứng minh một email thật đã gửi được**, vì nó chưa nhất thiết thực hiện **MAIL FROM**, **RCPT TO**, **DATA** cho một thông điệp cụ thể. Một tài khoản có thể kết nối và xác thực được nhưng vẫn bị giới hạn sender, recipient, quota hoặc nội dung thư.

Nên dùng test-connection để kiểm tra một phần tính sẵn sàng và cấu hình, chứ không thay thế thử gửi có kiểm soát hay dữ liệu phát thư của provider.

## 11. Quy trình chẩn đoán có kiểm soát

Khi cần xử lý một sự cố gửi mail, có thể thực hiện theo chuỗi sau:

1. **Xác định triệu chứng cụ thể**: kết nối thất bại, AUTH bị từ chối, recipient bị từ chối, lỗi tại DATA hay thư không xuất hiện trong Inbox.
2. **Lấy bằng chứng hiện có**: mã job, thời điểm gửi, loại **MailException**, chuỗi cause, SMTP status/provider event nếu có.
3. **Kiểm tra cấu hình hiệu lực**: host, port, loại TLS, credentials, timeout, profile Spring Boot, nguồn tạo Mail Session.
4. **Bật mail.debug trong phạm vi nhỏ**: dùng profile chẩn đoán và tài khoản/địa chỉ thử nghiệm khi có thể; giữ **mail.debug.auth=false**.
5. **Thực hiện một lần gửi có thể theo dõi**: chọn thông điệp nhỏ, không chứa bí mật, biết rõ recipient thử nghiệm và thời điểm thao tác.
6. **Đọc điểm cuối cùng trong hội thoại SMTP**: đối chiếu **EHLO**, **STARTTLS**, **AUTH**, **MAIL FROM**, **RCPT TO**, **DATA** và phản hồi server.
7. **Phân loại vấn đề**: sửa dữ liệu hoặc cấu hình, retry có giới hạn khi tạm lỗi, hoặc chuyển sang theo dõi delivery nếu server đã chấp nhận.
8. **Tắt protocol debug và xử lý log an toàn**: xác nhận cấu hình đã tắt; bảo vệ, ẩn hoặc xóa transcript theo chính sách lưu trữ và sự cố.

Quy trình trên tránh việc bật debug toàn ứng dụng trong thời gian dài. Nó cũng giúp phân biệt **lỗi chưa liên hệ được SMTP** với **lỗi sau khi provider đã nhận thông điệp**, là hai tình huống có hậu quả retry khác nhau.

### Một bản ghi sự cố đủ dùng

Thay vì sao chép toàn bộ console, người điều tra có thể ghi lại thông tin đã được lọc:

~~~text
mailJobId:        MAIL-782
mailType:         WELCOME
attempt:          2
smtpTarget:       smtp-provider-a
transportStage:   RCPT_TO
smtpCode:         451
exceptionType:    MailSendException
submissionState:  TEMPORARY_FAILURE
nextAction:       RETRY_WITH_BACKOFF
observedAt:       [timestamp]
~~~

Đây là mẫu minh họa, không phải một format bắt buộc của Spring Mail. Những trường như **transportStage** hoặc **smtpCode** chỉ nên được điền khi có bằng chứng từ exception, trace hoặc provider. Nếu mất kết nối sau DATA, **submissionState** có thể phải là **UNKNOWN**, không nên tự đặt **TEMPORARY_FAILURE** như thể biết chắc chưa gửi.

Trong vận hành, dữ liệu thu thập có thể gồm:

- **Ứng dụng**: log job, thời điểm gọi send, exception class và elapsed time.
- **Transport**: một đoạn trace đã ẩn dữ liệu thể hiện các lệnh và phản hồi liên quan.
- **Provider**: queue ID, rejection reason, delivery/bounce event nếu provider có.
- **Nghiệp vụ**: người dùng đã tạo tài khoản hay chưa, mã xác minh còn hiệu lực hay không, có job retry hay không.

Kết hợp các nguồn này hữu ích hơn một bản log protocol dài nhưng không có mã công việc hoặc bối cảnh.

## 12. Bài tập đọc tình huống

### Tình huống 1: Bật logging.level.org.springframework.mail=DEBUG nhưng không thấy EHLO

**Câu hỏi:** có phải SMTP không được liên hệ?

**Trả lời:** chưa đủ căn cứ. Thuộc tính này điều chỉnh logger của Spring Mail, không tự bật **Jakarta Mail Session debug**. Hãy kiểm tra ứng dụng đã gọi send chưa, rồi bật **mail.debug** đúng Session/profile và quan sát output tương ứng.

### Tình huống 2: Đã bật mail.debug nhưng dòng trace không có timestamp Logback

**Câu hỏi:** cấu hình logging của Spring Boot bị lỗi?

**Trả lời:** không nhất thiết. Jakarta Mail có thể xuất debug trực tiếp ra **System.out** hoặc một luồng debug riêng. Các dòng đó không tự dùng pattern, thread và MDC của Logback, dù cuối cùng vẫn được console hoặc container runtime thu thập.

### Tình huống 3: Trace hiển thị AUTH failed

**Câu hỏi:** có nên bật mail.debug.auth=true để xem credential rồi xác minh?

**Trả lời:** không. Điều tra nguồn credential qua secret manager, quyền tài khoản và cấu hình AUTH/TLS. Không đưa dữ liệu xác thực vào log; giữ **mail.debug.auth=false** và chỉ dùng trace đã loại dữ liệu nhạy cảm.

### Tình huống 4: Server trả 250 sau DATA nhưng khách hàng không thấy thư

**Câu hỏi:** có thể dùng thêm protocol debug để chứng minh người nhận đã đọc thư?

**Trả lời:** không. **250** sau DATA thường thể hiện server chấp nhận thông điệp tại bước nộp. Cần dùng dữ liệu delivery/bounce/provider và kiểm tra phía nhận; protocol trace không theo dõi hành vi đọc.

### Tình huống 5: Connection timed out trước khi server trả 220

**Câu hỏi:** có nên đổi địa chỉ người nhận?

**Trả lời:** không dựa trên triệu chứng này. Lỗi trước khi nhận greeting thường xảy ra ở DNS/TCP/network hoặc SMTP server, trước bước **RCPT TO**. Kiểm tra host, port, đường mạng và **mail.smtp.connectiontimeout**.

### Tình huống 6: Trace chỉ có một số phản hồi RCPT TO thành công

**Câu hỏi:** có thể đánh dấu toàn bộ danh sách recipient là đã gửi?

**Trả lời:** không. Cần xem phản hồi của từng recipient, quá trình DATA, cách transport xử lý partial sends và dữ liệu provider. Việc chấp nhận **RCPT TO** chưa chứng minh phát thư đến mailbox cuối cùng.

### Tình huống 7: Không còn phản hồi sau dòng kết thúc DATA

**Câu hỏi:** retry ngay mọi thư có an toàn?

**Trả lời:** có nguy cơ gửi trùng. Server có thể đã nhận dữ liệu nhưng phản hồi bị mất. Cần ghi nhận trạng thái submit **không xác định**, đối chiếu provider nếu có và áp dụng chính sách retry phù hợp với nghiệp vụ.

### Tình huống 8: Môi trường staging không dùng dữ liệu khách hàng, có thể bật debug liên tục?

**Câu hỏi:** như vậy không có rủi ro?

**Trả lời:** rủi ro thấp hơn nếu dữ liệu hoàn toàn giả lập nhưng vẫn có thông tin hạ tầng, credential, log volume và quyền truy cập. Mặc định nên tắt, chỉ bật khi cần, giới hạn retention và tránh để cấu hình debug vô tình được triển khai sang môi trường khác.

## 13. Ghi nhớ sự khác biệt giữa “biết lỗi” và “thấy giao thức”

~~~text
MailException
    -> Cho biết thao tác mail gặp lỗi ở tầng Spring
    -> Đọc type, cause và trạng thái job

logging.level.org.springframework.mail=DEBUG
    -> Tăng mức log được phát ra bởi logger Spring Mail
    -> Không bảo đảm có SMTP command trace

spring.mail.properties["mail.debug"]=true
    -> Bật debug Jakarta Mail Session/transport
    -> Quan sát cuộc hội thoại giao thức theo implementation
    -> Có thể in ra stdout/debug stream và bị thu vào log tập trung

Provider delivery/bounce events
    -> Bằng chứng ở những bước sau SMTP submission
    -> Cần cơ chế theo dõi riêng khi nghiệp vụ yêu cầu
~~~

**Protocol debug là một kính hiển vi cho quá trình trao đổi SMTP tại ứng dụng, không phải trạng thái gửi thư hoàn chỉnh.** Trong Spring Boot, cần bật đúng **mail.debug** trên Mail Session thực sự được sử dụng, hiểu vị trí debug output xuất hiện và đọc từng phản hồi trong đúng giai đoạn. Quan trọng hơn, phải coi protocol trace là dữ liệu cần bảo vệ: bật có mục đích, che thông tin nhạy cảm, giới hạn phạm vi/thời gian và tắt sau khi điều tra.
