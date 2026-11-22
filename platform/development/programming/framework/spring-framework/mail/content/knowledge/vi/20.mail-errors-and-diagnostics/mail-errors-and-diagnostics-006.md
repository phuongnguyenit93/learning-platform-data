# Lỗi DNS, timeout và từ chối kết nối

## 1. Tổng quan

Khi gửi email qua **Spring Framework Mail**, ứng dụng thường sử dụng **JavaMailSender** và Jakarta Mail để kết nối tới một **SMTP server**. Trước khi email được gửi, ứng dụng phải tìm được địa chỉ IP của server, thiết lập kết nối TCP, thực hiện TLS hoặc STARTTLS nếu cần, xác thực và trao đổi các lệnh SMTP.

Nếu bất kỳ bước nào thất bại, người dùng có thể chỉ thấy một thông báo chung như “Không gửi được email”. Tuy nhiên, các lỗi sau có bản chất khác nhau:

- **Lỗi DNS**: ứng dụng không phân giải được tên máy chủ SMTP thành địa chỉ IP, hoặc nhận kết quả phân giải không phù hợp.
- **Connection refused**: một nỗ lực kết nối TCP bị từ chối, thường vì không có dịch vụ lắng nghe ở địa chỉ/port đó hoặc có thiết bị mạng chủ động trả lời từ chối.
- **Connect timeout**: không thiết lập được kết nối trong thời gian cho phép, thường vì gói tin bị chặn, thất lạc hoặc đường mạng không phản hồi.
- **Read timeout**: đã có kết nối nhưng ứng dụng chờ phản hồi SMTP quá lâu.
- **Write timeout**: việc ghi dữ liệu lên socket mất nhiều thời gian hơn giới hạn cấu hình.

Một số lỗi nhìn bề ngoài giống lỗi mạng nhưng lại bắt nguồn từ **TLS**, **authentication**, **SMTP provider policy** hoặc **cấu hình sai port**. Để xử lý đúng, cần xác định lỗi xảy ra tại bước nào và phân biệt **không thể kết nối** với **đã kết nối nhưng không thể gửi**.

Trong bài này, mục tiêu là chẩn đoán từng nhóm lỗi có hệ thống, cấu hình timeout hợp lý và quyết định khi nào nên retry mà không tạo nguy cơ gửi email trùng.

## 2. Hành trình kết nối SMTP trong ứng dụng Spring

Luồng đơn giản:

~~~text
Spring application
       |
       | JavaMailSender.send(...)
       v
JavaMailSenderImpl / Jakarta Mail
       |
       | 1. Phân giải DNS cho SMTP host
       v
Hostname -> IP address
       |
       | 2. Kết nối TCP tới host:port
       v
SMTP server greeting
       |
       | 3. EHLO / HELO
       | 4. STARTTLS hoặc TLS từ đầu (theo cấu hình)
       | 5. Authentication nếu yêu cầu
       | 6. MAIL FROM / RCPT TO
       | 7. DATA và nội dung MIME
       | 8. Server trả phản hồi chấp nhận/từ chối
       v
SMTP queue / relay tiếp theo
~~~

Ví dụ cấu hình:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

Khi dùng cấu hình này, ứng dụng cần phân giải **smtp.example.com**. Sau đó nó kết nối trực tiếp tới server theo host và port đã khai báo; không tự yêu cầu DNS tìm bản ghi MX của domain người nhận ở bước nộp email thông thường.

**Lưu ý:** DNS và các bước gửi thư khác nhau có thể thất bại độc lập. Phân giải tên miền thành công chưa có nghĩa TCP port mở; kết nối TCP thành công chưa có nghĩa TLS hoặc SMTP authentication sẽ thành công.

## 3. Phân biệt SMTP submission với DNS MX của người nhận

Đây là một nhầm lẫn phổ biến khi thấy lỗi DNS.

Trong mô hình gửi email bằng nhà cung cấp SMTP:

~~~text
Ứng dụng Spring
      |
      | cấu hình spring.mail.host
      v
smtp.provider.example  <-- ứng dụng kết nối tới host này
      |
      | provider chuyển tiếp email
      v
MX của domain người nhận
      |
      v
Mail server phía nhận
~~~

Ứng dụng Spring cần phân giải tên của **SMTP relay/submission server** đã cấu hình. Việc tìm MX để chuyển phát tới domain đích thường là trách nhiệm của MTA phía cung cấp dịch vụ gửi, không phải của JavaMailSender trong luồng submission này.

| Thành phần DNS | Dùng cho | Khi nào quan trọng |
|---|---|---|
| **A / AAAA** | Ánh xạ hostname tới IPv4/IPv6 | Khi ứng dụng kết nối tới SMTP host |
| **CNAME** | Alias hostname tới tên khác | Nếu SMTP hostname là alias |
| **MX** | Xác định máy chủ nhận mail cho domain | Khi mail server định tuyến thư tới domain đích |
| **TXT SPF/DKIM/DMARC** | Thông tin xác thực/chính sách gửi mail | Vận hành và khả năng chuyển phát, không thay thế phân giải SMTP host |

Nếu ứng dụng báo **UnknownHostException** với smtp.example.com, việc kiểm tra MX của địa chỉ người nhận thường **không** giải quyết nguyên nhân trực tiếp. Hãy bắt đầu từ hostname SMTP trong cấu hình.

## 4. Dấu hiệu nhận biết lỗi DNS

Lỗi DNS xảy ra khi hostname không thể được phân giải hoặc quá trình phân giải gặp sự cố. Java có thể ném **java.net.UnknownHostException**, có thể được bọc bên trong một exception của Jakarta Mail hoặc Spring Mail.

Ví dụ thông báo thường gặp:

~~~text
java.net.UnknownHostException: smtp.example.com
~~~

Nguyên nhân khả dĩ:

- Gõ sai hostname hoặc dùng hostname không tồn tại.
- Host được cấu hình qua biến môi trường sai hoặc rỗng.
- DNS resolver của máy/VM/container không truy cập được.
- DNS server trả **NXDOMAIN** cho tên không tồn tại.
- DNS server trả **SERVFAIL** hoặc timeout.
- Mạng nội bộ yêu cầu DNS riêng nhưng ứng dụng đang dùng resolver khác.
- Có split-horizon DNS: cùng tên nhưng ở mạng nội bộ và ngoài Internet trả kết quả khác nhau.
- DNS cache trong JVM hoặc hệ điều hành chưa cập nhật sau khi bản ghi đổi.
- Host có địa chỉ IPv6 nhưng đường IPv6 của môi trường không hoạt động ổn định.

### Các trường hợp DNS khác nhau

| Tình huống | Đặc điểm | Cách chẩn đoán |
|---|---|---|
| **NXDOMAIN** | Domain/hostname không tồn tại theo DNS trả lời | Kiểm tra tên host, zone, alias |
| **SERVFAIL** | DNS server không xử lý được truy vấn | Kiểm tra resolver và hạ tầng DNS |
| **DNS timeout** | Không nhận được phản hồi từ resolver | Kiểm tra mạng tới DNS server, firewall, container DNS |
| **Trả IP cũ** | Có thể do TTL hoặc cache | Kiểm tra TTL, DNS cache, địa chỉ mới |
| **Trả IP private sai mạng** | Có thể do split DNS hoặc cấu hình môi trường | Kiểm tra resolver đang được dùng và routing |
| **Chỉ có AAAA hoặc ưu tiên IPv6** | Môi trường thiếu đường IPv6 | So sánh A/AAAA và kết nối thực tế |

Một exception Java thường không tự phân biệt tường minh mọi loại phản hồi DNS. Cần đối chiếu với công cụ DNS và log của resolver nếu cần.

## 5. Kiểm tra cấu hình hostname trước khi kiểm tra mạng

Trước tiên xác định **host hiệu lực** mà Spring thực sự dùng. Đừng chỉ nhìn giá trị mặc định trong một file cấu hình:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
~~~

Giá trị này có thể bị override bởi:

- Profile khác như application-prod.yml.
- Environment variable **SPRING_MAIL_HOST**.
- Command-line argument hoặc nguồn property có độ ưu tiên cao hơn.
- Secret/config map trong container orchestration.
- Bean **JavaMailSenderImpl** được cấu hình thủ công và không dùng các property ở trên.

Với nhiều sender, mỗi bean có thể dùng host/port khác nhau. Cần xác nhận sender nào thực tế xử lý notification gặp lỗi.

Không in toàn bộ cấu hình mail để debug vì có thể làm lộ username, password hoặc token. Chỉ log thông tin được phép như hostname, port, tên môi trường và sender logical ID.

### Kiểm tra biến môi trường

Ví dụ khi cấu hình:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

Nếu SMTP_HOST bị gán sai, một môi trường có thể chạy tốt trong khi môi trường khác báo DNS failure. Hãy kiểm tra giá trị host thực tế ở **chính process/container gặp lỗi**.

## 6. Công cụ kiểm tra DNS

Trên Windows với PowerShell:

~~~powershell
Resolve-DnsName smtp.example.com -Type A
Resolve-DnsName smtp.example.com -Type AAAA
Resolve-DnsName smtp.example.com -Type CNAME
~~~

Có thể dùng nslookup:

~~~text
nslookup smtp.example.com
~~~

Trên Linux hoặc môi trường có công cụ tương ứng:

~~~bash
getent hosts smtp.example.com
dig smtp.example.com A
dig smtp.example.com AAAA
nslookup smtp.example.com
~~~

Không phải image container nào cũng cài sẵn dig/nslookup. Nếu ứng dụng chạy trong Kubernetes hoặc Docker, cần kiểm tra DNS **từ cùng network namespace hoặc một môi trường debug có cùng cấu hình DNS**, thay vì chỉ kiểm tra trên laptop.

### Đọc kết quả đúng

- DNS query thành công và có IP: có cơ sở để tiếp tục kiểm tra TCP, nhưng chưa chứng minh ứng dụng kết nối được.
- DNS query thất bại: kiểm tra resolver, hostname, zone, search suffix và policy mạng.
- DNS query thành công trên laptop nhưng thất bại trong container: tập trung vào cấu hình DNS/network của container.
- Kết quả A và AAAA khác nhau: kiểm tra đường IPv4/IPv6 tương ứng.
- Chỉ lỗi một môi trường: so sánh profile, resolver, VPN, proxy và outbound policies.

Không thử thay DNS sản xuất hoặc xóa cache trên diện rộng khi chưa xác định nguyên nhân và phạm vi ảnh hưởng.

## 7. DNS cache và khác biệt giữa JVM với công cụ hệ điều hành

Ứng dụng Java có cơ chế cache kết quả phân giải hostname. Thời gian cache phụ thuộc JVM, security/network properties và môi trường.

Tình huống điển hình:

1. SMTP provider đổi địa chỉ IP hoặc DNS alias.
2. Công cụ dig/nslookup trên máy trả IP mới.
3. Process Java đã chạy lâu vẫn sử dụng kết quả cũ trong một khoảng thời gian.
4. Kết nối từ ứng dụng tiếp tục thất bại.

Điều này không chứng minh JVM chắc chắn cache sai; cần kiểm tra thời điểm thay đổi DNS, DNS TTL, JVM configuration và nơi thực hiện lookup.

Một số thuộc tính Java liên quan:

~~~text
networkaddress.cache.ttl
networkaddress.cache.negative.ttl
~~~

Thời gian hiệu lực và cách cấu hình các thuộc tính phụ thuộc runtime; không nên đặt TTL bằng 0 cho mọi môi trường hoặc tắt cache như một “giải pháp chung”. TTL quá thấp có thể làm tăng tải DNS và độ trễ.

Nếu chỉ cần phục hồi tạm thời, restart một instance có thể làm thay đổi kết quả sử dụng DNS, nhưng việc sửa hostname, resolver hoặc đường mạng mới là cách xử lý nguyên nhân gốc.

## 8. Connection refused là gì?

Lỗi **Connection refused** thường được Java biểu diễn bằng **java.net.ConnectException**:

~~~text
java.net.ConnectException: Connection refused
~~~

Về mặt TCP, lỗi này thường cho thấy một phía đã chủ động từ chối nỗ lực thiết lập kết nối, ví dụ hệ điều hành trả RST khi không có service lắng nghe trên port đích.

Những nguyên nhân phổ biến:

- Hostname được phân giải đúng nhưng **port cấu hình sai**.
- SMTP server không chạy hoặc service chưa bind vào interface cần thiết.
- Server chỉ lắng nghe trên localhost/nội bộ, không lắng nghe IP mà ứng dụng truy cập.
- Firewall, load balancer hoặc gateway chủ động từ chối kết nối.
- Kết nối tới nhầm server do DNS hoặc routing.
- Provider không hỗ trợ port đang chọn.
- NAT, proxy hoặc service mesh định tuyến tới endpoint không có listener.

**Connection refused khác connect timeout:** refused thường cho biết có phản hồi từ chối nhanh, còn timeout thường là không nhận được kết quả thiết lập kết nối trong giới hạn thời gian.

## 9. Phân biệt connection refused, connect timeout và network unreachable

| Triệu chứng | Dấu hiệu | Nguyên nhân cần nghĩ tới |
|---|---|---|
| **Connection refused** | Kết nối bị từ chối nhanh | Sai port, không có listener, firewall reject |
| **Connect timeout** | Chờ đủ thời gian cấu hình rồi thất bại | Gói tin bị drop, network path không phản hồi |
| **Network is unreachable** | Hệ điều hành không có đường tới đích | Routing, interface hoặc VPN |
| **No route to host** | Không có tuyến phù hợp hoặc bị chặn theo chính sách | Route, ACL, firewall, network segment |
| **UnknownHostException** | Chưa có địa chỉ IP dùng được | DNS/config host |
| **Read timed out** | Kết nối đã tồn tại nhưng không nhận phản hồi kịp | Server chậm, mạng, SMTP/TLS phase |

Thông báo lỗi phụ thuộc OS, JDK và implementation; cùng nguyên nhân hạ tầng có thể xuất hiện dưới exception khác nhau. Bảng là hướng chẩn đoán, không phải quy tắc tuyệt đối.

### Ví dụ sai port

Giả sử SMTP provider hỗ trợ submission trên port 587, nhưng ứng dụng dùng port 2526. Nếu không có dịch vụ nào lắng nghe và firewall không drop, client có thể nhận connection refused ngay.

Nếu firewall chặn outbound tới port 587 mà không trả reject, nỗ lực kết nối có thể timeout thay vì refused.

Điểm cần kiểm tra là **host:port và đường mạng thực tế**, không phải chỉ tăng timeout.

## 10. Kiểm tra TCP port bằng công cụ mạng

Trên Windows PowerShell:

~~~powershell
Test-NetConnection smtp.example.com -Port 587
~~~

Trên Linux có netcat:

~~~bash
nc -vz -w 5 smtp.example.com 587
~~~

Nếu có telnet, có thể dùng để quan sát kết nối TCP tới SMTP server:

~~~text
telnet smtp.example.com 587
~~~

Với kết nối SMTP plaintext trước STARTTLS, server thường gửi greeting dạng:

~~~text
220 smtp.example.com ESMTP ready
~~~

**Không sử dụng telnet để nhập credential SMTP** vì phiên này không bảo đảm được bảo vệ bằng TLS. Telnet chỉ phù hợp khi cần kiểm tra listener/greeting trong môi trường được phép.

Nếu TCP connect thành công, tiếp theo cần kiểm tra TLS, authentication và SMTP response. Một TCP probe thành công **không đủ kết luận ứng dụng có thể gửi email**.

### Vì sao ping không phải bài kiểm tra quyết định?

Ping dùng ICMP. Một server có thể chặn ICMP nhưng vẫn cho phép TCP tới port SMTP. Ngược lại, ping thành công chưa chứng minh port 587 đang mở.

Vì thế:

- Dùng DNS lookup để kiểm tra phân giải.
- Dùng TCP port probe để kiểm tra đường mạng tới host:port.
- Dùng TLS/SMTP test có kiểm soát để kiểm tra protocol.
- Chỉ dùng ping như tín hiệu phụ nếu chính sách mạng cho phép.

## 11. Chọn đúng port và chế độ TLS

Các cách kết nối SMTP thường gặp:

| Port | Cách dùng thường gặp | Cơ chế bảo mật |
|---|---|---|
| **587** | Mail submission | Kết nối TCP, sau đó nâng cấp STARTTLS |
| **465** | Submission với TLS ngầm định | TLS bắt đầu ngay sau kết nối |
| **25** | SMTP relay/MTA transfer; đôi khi được hỗ trợ theo chính sách riêng | Có thể hỗ trợ STARTTLS; thường bị chặn outbound ở cloud |
| **2525** | Port thay thế do một số provider hỗ trợ | Phụ thuộc provider |

Đây là quy ước phổ biến, không phải tất cả provider đều hỗ trợ mọi port. Luôn dựa vào tài liệu hoặc cấu hình dịch vụ SMTP của hệ thống đang dùng.

### STARTTLS trên port 587

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
~~~

Với STARTTLS, kết nối SMTP bắt đầu ở trạng thái chưa mã hóa rồi được nâng cấp lên TLS sau khi server quảng bá hỗ trợ. Khi đặt **required: true**, ứng dụng yêu cầu STARTTLS thành công thay vì gửi tiếp không mã hóa nếu server không hỗ trợ.

### TLS ngầm định trên port 465

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
~~~

Đừng cấu hình **ssl.enable: true** với port chỉ hỗ trợ STARTTLS theo cách gây nhầm handshake ngay từ đầu. Khi kết hợp sai port và TLS mode, client có thể chờ greeting/handshake đến timeout hoặc nhận lỗi SSL, không nhất thiết là connection refused.

Với mọi cấu hình, cần xác thực chứng chỉ, hostname và yêu cầu bảo mật thực tế của provider; không tắt certificate validation chỉ để vượt qua lỗi.

## 12. Kiểm tra TLS với OpenSSL

Trong môi trường có OpenSSL, có thể kiểm tra STARTTLS:

~~~bash
openssl s_client -starttls smtp -connect smtp.example.com:587 -servername smtp.example.com
~~~

Với SMTPS/TLS ngầm định:

~~~bash
openssl s_client -connect smtp.example.com:465 -servername smtp.example.com
~~~

Các lệnh này giúp quan sát certificate và TLS negotiation khi kết nối tới server. Chúng không tự xác nhận username/password SMTP hay quyền gửi.

Khi đọc kết quả, chú ý:

- Có mở được kết nối TCP hay không?
- TLS handshake có hoàn thành không?
- Certificate có được xác minh hợp lệ không?
- Tên trên certificate có phù hợp hostname không?
- Server có yêu cầu hoặc hỗ trợ giao thức TLS tương thích không?

**Không kết luận một kênh gửi email an toàn chỉ vì lệnh TLS không báo lỗi rõ ràng.** Cần xác nhận verify result, cấu hình trust và chính sách SMTP phù hợp.

## 13. Connect timeout, read timeout và write timeout trong Jakarta Mail

Trong Spring Boot, có thể truyền JavaMail properties qua **spring.mail.properties**:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
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
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

Ba giá trị timeout ở ví dụ trên được tính theo **mili giây**.

| Property | Thường kiểm soát | Ví dụ |
|---|---|---|
| **mail.smtp.connectiontimeout** | Thời gian chờ thiết lập kết nối TCP | 5.000 ms |
| **mail.smtp.timeout** | Timeout đọc trên socket, chờ dữ liệu/phản hồi | 10.000 ms |
| **mail.smtp.writetimeout** | Timeout ghi dữ liệu lên socket | 10.000 ms |

Nên đặt **đủ cả ba** để tránh một request treo quá lâu trên mạng. Đây là giá trị minh họa; giới hạn phù hợp phụ thuộc latency thực tế, attachment size, network path và SLA.

### Vì sao chỉ đặt connectiontimeout chưa đủ?

Giả sử kết nối TCP đã thành công và server gửi greeting. Khi ứng dụng gửi DATA, server hoặc đường mạng có thể chậm, khiến việc đọc phản hồi cuối mất nhiều thời gian. Connect timeout không bảo vệ giai đoạn đó.

Ngược lại, chỉ đặt read timeout không bảo vệ giai đoạn ban đầu khi không thiết lập được kết nối TCP.

### Timeout không bảo đảm an toàn khi retry

Đặt read timeout = 10 giây không có nghĩa rằng sau 10 giây thất bại, SMTP server chắc chắn chưa nhận email. Nếu server đã nhận DATA nhưng phản hồi bị mất, ứng dụng vẫn có thể nhận timeout và không biết kết quả.

Do đó, timeout là công cụ **giới hạn thời gian chờ**, không phải cơ chế chứng minh email chưa được gửi.

## 14. Khi nào timeout quá thấp hoặc quá cao?

Một timeout quá thấp có thể khiến kết nối khỏe nhưng hơi chậm bị coi là lỗi; một timeout quá cao có thể làm thread bị giữ và kéo dài thời gian phát hiện sự cố.

| Cấu hình | Hệ quả có thể xảy ra |
|---|---|
| Connect timeout quá thấp | Thất bại khi DNS/TCP/network có độ trễ bình thường |
| Read timeout quá thấp | Thất bại trong lúc server xử lý lệnh SMTP hoặc DATA |
| Write timeout quá thấp | Dễ lỗi khi gửi message lớn hoặc mạng chậm |
| Timeout quá cao | Thread bị giữ lâu, giảm throughput, làm chậm retry |
| Không có timeout hữu hạn | Có nguy cơ chờ quá lâu tùy network/runtime |

Khi đặt giá trị:

1. Đo latency kết nối và phản hồi SMTP bình thường.
2. Xem kích thước email, attachment và lượng email đồng thời.
3. Xem giới hạn request/worker/queue của ứng dụng.
4. Đặt các timeout có quan hệ hợp lý với SLA và lịch retry.
5. Theo dõi p95/p99 và tỷ lệ timeout sau khi thay đổi cấu hình.

Không nên tăng timeout vô hạn để “chữa” DNS sai, firewall chặn hoặc port bị từ chối. Những lỗi đó cần sửa đường mạng/cấu hình.

## 15. Một lỗi có thể bị bọc qua nhiều lớp exception

Ứng dụng Spring có thể chỉ catch được **MailException**, trong khi nguyên nhân gốc là lỗi DNS hoặc Java networking.

Ví dụ chuỗi khái niệm:

~~~text
org.springframework.mail.MailSendException
    caused by jakarta.mail.MessagingException
        caused by java.net.UnknownHostException
~~~

Hoặc:

~~~text
MailSendException
    -> MessagingException
        -> java.net.ConnectException: Connection refused
~~~

Không nên phân loại hoàn toàn dựa trên exception ngoài cùng. Cần đọc cause chain và, khi sử dụng Jakarta Mail, có thể cần xem **MessagingException.getNextException()** vì API này hỗ trợ liên kết các exception bên cạnh cơ chế Throwable.getCause().

Một số nhóm thường gặp:

| Exception | Cách hiểu ban đầu |
|---|---|
| **UnknownHostException** | DNS/hostname không thể phân giải |
| **ConnectException** | Kết nối TCP bị từ chối hoặc sự cố kết nối |
| **SocketTimeoutException** | Timeout tại một thao tác socket; cần pha gửi |
| **NoRouteToHostException** | Vấn đề routing hoặc network policy |
| **SSLHandshakeException** | TLS negotiation/certificate không thành công |
| **MailAuthenticationException** | Lỗi xác thực SMTP |
| **MailSendException** | Lỗi gửi ở tầng Spring; xem nguyên nhân chi tiết |
| **MessagingException** | Lỗi Jakarta Mail; xem cause và next exception |

Đừng gom tất cả thành **“SMTP không hoạt động”**. Việc phân loại rõ giúp nhóm vận hành xác định phải sửa DNS, TCP, TLS, credentials hay message content.

## 16. Đọc cause chain của lỗi Spring Mail

Một service có thể ghi nhận loại lỗi đã được chuẩn hóa trong khi không đưa toàn bộ thông tin SMTP vào log. Để làm điều đó, cần tìm được exception gốc thay vì chỉ dựa vào chuỗi message.

Ví dụ duyệt chuỗi **getCause()**:

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import org.springframework.mail.MailException;

public String classifyMailFailure(MailException exception) {
    for (Throwable current = exception;
         current != null;
         current = current.getCause()) {

        if (current instanceof UnknownHostException) {
            return "SMTP_DNS_FAILURE";
        }
        if (current instanceof ConnectException) {
            return "SMTP_CONNECTION_FAILURE";
        }
        if (current instanceof SocketTimeoutException) {
            return "SMTP_SOCKET_TIMEOUT";
        }
    }
    return "SMTP_OTHER_FAILURE";
}
~~~

Đây là ví dụ **tối giản** để minh họa cách đọc nguyên nhân. Trong production cần xử lý vòng lặp bất thường của exception chain và chuỗi **MessagingException.getNextException()** khi có. Ngoài ra, **SMTP_SOCKET_TIMEOUT** chỉ là mã chẩn đoán; nó **chưa đủ để quyết định retry**, vì cần biết timeout xảy ra tại CONNECT, khi chờ SMTP reply hay sau khi truyền DATA.

### Cách duyệt đầy đủ hơn với Jakarta Mail

~~~java
import jakarta.mail.MessagingException;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public static Set<Throwable> collectRelatedErrors(Throwable root) {
    Set<Throwable> seen = Collections.newSetFromMap(
            new IdentityHashMap<>()
    );
    ArrayDeque<Throwable> pending = new ArrayDeque<>();
    pending.add(root);

    while (!pending.isEmpty()) {
        Throwable current = pending.removeFirst();
        if (!seen.add(current)) {
            continue;
        }
        if (current.getCause() != null) {
            pending.addLast(current.getCause());
        }
        if (current instanceof MessagingException mailError) {
            Exception next = mailError.getNextException();
            if (next != null) {
                pending.addLast(next);
            }
        }
    }

    return seen;
}
~~~

Ví dụ này giả định **root không null**. **IdentityHashMap** giúp phát hiện cùng đối tượng exception dù chuỗi liên kết có vòng. Kết quả nên dùng cho việc phân tích nội bộ; không tự động ghi message của mọi exception vào log vì nội dung có thể chứa hostname nội bộ, địa chỉ email hoặc chi tiết nhạy cảm.

## 17. MailSendException và lỗi gửi nhiều message

Nếu ứng dụng gọi **JavaMailSender.send(...)** cho nhiều message, một lệnh có thể thất bại ở một số message nhưng những message khác đã được nộp.

Spring **MailSendException** có API hỗ trợ đọc các message được ghi nhận thất bại, chẳng hạn:

~~~java
try {
    mailSender.send(messages);
} catch (MailSendException exception) {
    Map<Object, Exception> failed =
            exception.getFailedMessages();

    for (Map.Entry<Object, Exception> entry : failed.entrySet()) {
        Object failedMessage = entry.getKey();
        Exception cause = entry.getValue();

        // Ánh xạ failedMessage về notification ID của ứng dụng.
        // Phân loại lỗi dựa trên cause và ngữ cảnh gửi.
    }
}
~~~

Ở đây, **messages** là một mảng MimeMessage đã được tạo và gắn với notification ID ổn định. Phương thức trên minh họa việc tra cứu thông tin lỗi; không phải mã hoàn chỉnh cho batch sender.

Nếu gửi một batch A, B, C mà A đã được chấp nhận còn B bị từ chối, **không nên retry nguyên batch**. Làm vậy có thể gửi lại A lần nữa.

Trong ứng dụng cần tính chính xác cao, có thể thiết kế **một notification/outbox record cho một message hoặc một recipient**, nhằm dễ theo dõi tình trạng từng lần nộp. Kết quả từng người nhận trong một MimeMessage có nhiều recipient có thể phức tạp hơn và cần phân tích **SendFailedException** theo Jakarta Mail.

## 18. Quy trình chẩn đoán theo từng lớp

Một runbook thực tế nên đi từ lỗi đơn giản và ít tốn kém đến lỗi phức tạp.

**Bước 1 — Xác định phạm vi**

- Mọi email đều lỗi hay chỉ một loại notification?
- Lỗi xảy ra trên tất cả instance hay một instance?
- Chỉ production lỗi hay cả staging?
- Bắt đầu sau deploy, đổi secret, đổi DNS hay thay đổi firewall?
- Lỗi liên tục hay chỉ xảy ra theo đợt?

**Bước 2 — Đọc exception thực tế**

- Ghi nhận exception ngoài cùng của Spring và cause chain.
- Tìm UnknownHostException, ConnectException, SocketTimeoutException, SSLHandshakeException.
- Nếu có SMTP reply, ghi nhận mã và lệnh liên quan.
- Xác định timeout xảy ra ở pha nào nếu có bằng chứng.

**Bước 3 — Xác nhận cấu hình hiệu lực**

- SMTP host, port và sender bean đang được dùng.
- Profile và environment variable.
- STARTTLS hay implicit TLS.
- Timeout đã cấu hình hay chưa.
- Outbound network policy của môi trường hiện tại.

**Bước 4 — Kiểm tra DNS**

- Lookup A/AAAA từ chính môi trường chạy ứng dụng.
- So sánh với resolver khác nếu cần.
- Kiểm tra IP, TTL, split DNS hoặc DNS cache.

**Bước 5 — Kiểm tra TCP**

- TCP probe tới đúng host:port.
- Phân biệt refused, timeout và no route.
- Xem firewall/egress rule, NAT, proxy và service mesh.

**Bước 6 — Kiểm tra TLS và SMTP**

- SMTP greeting có tới được không?
- STARTTLS có được quảng bá/hỗ trợ?
- TLS certificate và hostname có hợp lệ không?
- Authentication có được server chấp nhận không?
- Có phản hồi SMTP 4xx/5xx rõ ràng không?

**Bước 7 — Đối chiếu với application logs và metric**

- Độ trễ kết nối/tổng thời gian gửi.
- Tỷ lệ timeout và lỗi từng instance.
- Thời điểm các sự cố cấu hình/deploy.
- Tình trạng pending/retry/unknown trong outbox.

**Không nhảy thẳng sang tăng timeout khi còn chưa xác định host và port đúng.** Một hostname không tồn tại hoặc port không có listener không được sửa bằng cách chờ lâu hơn.

## 19. Chẩn đoán trong Docker và Kubernetes

Một lỗi chỉ xảy ra trong container thường liên quan tới môi trường thực thi, không nhất thiết tới Spring Mail.

Các điểm cần kiểm tra:

| Lớp | Ví dụ vấn đề |
|---|---|
| **Container DNS** | Resolver cấu hình sai, CoreDNS lỗi, DNS policy không đúng |
| **Network namespace** | Container có đường mạng khác host |
| **Egress policy** | NetworkPolicy hoặc firewall chặn outbound SMTP |
| **NAT/route** | Không có đường ra Internet hoặc đường tới private SMTP |
| **Service mesh** | Sidecar/proxy kiểm soát cổng hoặc TLS |
| **Environment variables** | Secret hoặc ConfigMap chưa được cập nhật |
| **IPv6** | Container có DNS AAAA nhưng đường IPv6 không hoạt động |

### Đừng chỉ kiểm tra trên máy phát triển

Nếu developer laptop truy cập SMTP host thành công nhưng pod production báo timeout, phải kiểm tra từ pod hoặc một container debug có cùng namespace và chính sách mạng.

Ví dụ thao tác trong môi trường Kubernetes được cấp quyền:

~~~bash
kubectl exec -n app-namespace deploy/mail-worker -- printenv SPRING_MAIL_HOST
~~~

Lệnh trên chỉ in hostname được phép xem. **Không in SPRING_MAIL_PASSWORD hoặc secret**. Với container không có shell hay công cụ mạng, có thể dùng debug container theo quy trình vận hành đã được cho phép; không tự thay đổi pod production chỉ để thử mạng.

### Kiểm tra NetworkPolicy

NetworkPolicy có thể cho phép ứng dụng truy cập database nhưng không cho outbound tới SMTP provider. Nếu egress bị drop, connect timeout là một triệu chứng thường gặp.

Nếu chỉ một namespace lỗi, so sánh policy, DNS configuration và network route với namespace hoạt động. Nếu chỉ một node lỗi, xem các vấn đề riêng của node, DNS hoặc network agent.

## 20. Cloud provider và outbound SMTP restriction

Một số môi trường cloud giới hạn hoặc lọc các cổng SMTP outbound, đặc biệt port 25. Điều này phụ thuộc nhà cung cấp, tài khoản, vùng và chính sách mạng.

Khi kết nối tới SMTP public thất bại:

1. Kiểm tra provider có cho outbound tới port cần dùng không.
2. Kiểm tra security group/firewall/route table.
3. Xác minh đích được provider hỗ trợ ở port 587 hoặc 465.
4. Kiểm tra SMTP endpoint private/public tương ứng với mạng đang dùng.
5. Kiểm tra allowlist IP nguồn nếu SMTP server giới hạn.

Không tự chuyển từ port 587 sang 25 hay ngược lại mà không xác nhận tài liệu của SMTP provider. Việc đổi port cũng có thể làm thay đổi yêu cầu TLS và authentication.

### Một số trường hợp chỉ xuất hiện khi scale

Khi có nhiều instance cùng gửi:

- SMTP provider có thể giới hạn số kết nối đồng thời.
- NAT hoặc proxy có thể cạn tài nguyên.
- DNS resolver có thể bị quá tải.
- Thời gian mở connection tăng.
- Rate limit có thể gây SMTP 4xx ở các pha sau khi đã kết nối.

Một lỗi “timeout” khi tải cao chưa chắc do thời gian timeout quá thấp. Có thể cần **giới hạn concurrency, kết nối hợp lý, queue và backoff**, thay vì tăng số thread vô hạn.

## 21. Khi DNS đúng nhưng TCP vẫn thất bại

Đây là tình huống thường gặp:

~~~text
DNS:
  smtp.example.com -> 203.0.113.10
  Resolution: SUCCESS

TCP:
  203.0.113.10:587
  Connection: FAILED
~~~

Địa chỉ **203.0.113.10** trong ví dụ là IP dành cho tài liệu minh họa, không phải địa chỉ SMTP thật.

Các bước phân biệt:

- Nếu **Connection refused**: kiểm tra listener, port, load balancer và firewall reject.
- Nếu **Connect timeout**: kiểm tra firewall drop, routing, NAT, provider egress policy hoặc server không phản hồi.
- Nếu **No route to host**: kiểm tra route/interface/VPN/network segmentation.
- Nếu chỉ **IPv6** lỗi: thử xác định kết quả A/AAAA và đường kết nối cho từng address family trong môi trường được phép.
- Nếu chỉ một IP trong nhóm DNS round-robin lỗi: có thể một backend hoặc đường mạng tới một endpoint gặp sự cố.

Không dùng một kết quả DNS thành công để kết luận SMTP provider đang khỏe. DNS, TCP và SMTP là các tầng khác nhau.

## 22. Khi TCP mở nhưng không có SMTP greeting

Kết nối TCP có thể thành công nhưng ứng dụng vẫn bị **read timeout** khi chờ phản hồi đầu tiên.

Các nguyên nhân có thể:

- Có listener nhưng dịch vụ SMTP đang quá tải hoặc treo.
- Kết nối đi qua proxy không nói giao thức SMTP.
- Định tuyến nhầm tới dịch vụ khác.
- Port yêu cầu TLS ngầm định nhưng client chờ greeting plaintext.
- Thiết bị mạng chấp nhận TCP rồi chặn hoặc trì hoãn luồng dữ liệu.

Ví dụ sai chế độ TLS:

~~~text
Client kết nối port 465
Client chờ plaintext SMTP greeting
Server đang chờ TLS ClientHello

=> Hai phía chờ nhau, có thể sinh timeout.
~~~

Giải pháp là dùng **implicit TLS** đúng cách nếu server yêu cầu, không phải vô hạn tăng read timeout.

Tương tự, nếu client bắt đầu TLS ngay trên port chỉ chấp nhận SMTP plaintext trước STARTTLS, handshake có thể lỗi hoặc kết nối bị cắt. Kiểm tra sự tương thích giữa **port, protocol và TLS mode**.

## 23. Khi server chậm phản hồi sau khi đã kết nối

Một **read timeout** có thể phát sinh trong các pha khác nhau:

- Chờ greeting SMTP.
- Chờ EHLO response.
- Chờ STARTTLS negotiation.
- Chờ AUTH response.
- Chờ MAIL FROM/RCPT TO.
- Chờ phản hồi cuối sau DATA.

Mỗi pha có ý nghĩa vận hành khác nhau. Timeout tại greeting có thể liên quan tới server quá tải; timeout tại AUTH có thể liên quan backend authentication; timeout sau DATA gây khó khăn đặc biệt cho retry.

### Ví dụ sau DATA

~~~text
Ứng dụng                         SMTP server
    |                                 |
    | ---- MAIL FROM / RCPT TO ----> |
    | <--- phản hồi thành công ----- |
    | ---- DATA -------------------> |
    | ---- nội dung MIME ----------> |
    | ---- kết thúc DATA ----------> |
    |                                 | có thể đã queue
    |       mất phản hồi 250          X
    v
SocketTimeoutException
~~~

Nếu SMTP server đã đưa mail vào queue nhưng phản hồi bị mất, retry nguyên message có thể tạo bản trùng. Vì vậy không thể chỉ thấy SocketTimeoutException rồi kết luận phải gửi lại ngay.

## 24. Chính sách retry cho DNS, refused và timeout

Đối với ba nhóm lỗi này, có thể tham khảo ma trận:

| Bằng chứng lỗi | Phân loại gợi ý | Hành động |
|---|---|---|
| Hostname sai và không tồn tại ổn định | Configuration / permanent | Dừng, sửa host |
| DNS resolver timeout tạm thời | Transient | Retry với backoff |
| DNS SERVFAIL thoáng qua | Transient | Retry có giới hạn và kiểm tra DNS |
| DNS cache stale sau đổi hạ tầng | Configuration/operational | Xác định TTL/cache và sửa nguyên nhân |
| TCP refused vì sai port | Configuration / permanent | Sửa port hoặc listener |
| TCP refused do service tạm restart | Transient | Retry sau delay |
| TCP connect timeout trước khi gửi bất kỳ byte SMTP nào | Transient | Retry có giới hạn |
| TCP timeout do firewall drop cố định | Configuration/network policy | Sửa egress/route |
| Read timeout tại greeting | Thường transient, nhưng cần ngữ cảnh | Retry có giới hạn nếu chưa submit |
| Read timeout khi chờ phản hồi DATA cuối | Ambiguous / UNKNOWN | Đối soát trước khi retry |
| Write timeout sau khi đã bắt đầu DATA | Có thể ambiguous | Đánh giá lượng dữ liệu và phản hồi đã nhận |
| TLS handshake thất bại do certificate sai | Configuration/security | Sửa TLS, không bỏ qua xác thực |

**Cùng một ConnectException có thể dẫn đến chính sách khác nhau** khi biết nguyên nhân môi trường. Refused do server restart có thể tự hồi phục, trong khi refused do port cấu hình sai sẽ lặp lại mãi.

### Retry nên có gì?

- Delay trước khi thử lại.
- Exponential backoff hoặc lịch chờ được xác định rõ.
- Jitter để tránh nhiều worker cùng retry.
- Max attempts và max age.
- Circuit breaker hoặc tạm dừng worker khi server lỗi hàng loạt nếu phù hợp.
- Trạng thái **UNKNOWN** cho trường hợp có thể đã được chấp nhận.
- Dữ liệu truy vết notification/event để tránh duplicate ở tầng ứng dụng.

Không retry đồng bộ trong request người dùng một cách vô hạn; nó có thể kéo dài response, giữ thread và tăng áp lực mạng.

## 25. Exponential backoff và jitter

Một công thức gợi ý:

~~~text
delay = min(maxDelay, baseDelay * 2^(retryNumber - 1)) + jitter
~~~

Ví dụ baseDelay = 30 giây, maxDelay = 20 phút:

| Lần retry | Thời gian cơ sở trước jitter |
|---:|---:|
| 1 | 30 giây |
| 2 | 60 giây |
| 3 | 120 giây |
| 4 | 240 giây |
| 5 | 480 giây |
| 6 | 960 giây |
| 7 | 1.200 giây |

Không phải số lần retry nào cũng phù hợp với mọi email. Với OTP thời hạn ngắn, retry sau nhiều phút có thể không còn giá trị. Với hóa đơn hoặc thông báo nghiệp vụ, có thể cần lưu ý định gửi bền vững và phát cảnh báo vận hành.

Ví dụ hàm tính delay:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public Duration retryDelay(int retryNumber) {
    if (retryNumber <= 0) {
        throw new IllegalArgumentException("retryNumber phải dương");
    }

    long seconds = 30L;
    for (int i = 1; i < retryNumber; i++) {
        seconds = Math.min(1_200L, seconds * 2);
    }

    long jitter = ThreadLocalRandom.current().nextLong(0L, 10L);
    return Duration.ofSeconds(seconds + jitter);
}
~~~

Đây là ví dụ đơn giản; policy production có thể dùng full jitter hoặc decorrelated jitter, tùy yêu cầu. Thời điểm retry kế tiếp nên được lưu bền vững trong outbox/queue nếu ứng dụng cần khôi phục sau restart.

## 26. Idempotency và nguy cơ gửi trùng

Khi kết quả SMTP chưa rõ, retry có thể làm người nhận thấy hai email giống nhau.

Ví dụ:

~~~text
Outbox record N-100
        |
        v
Worker A sends SMTP
        |
        v
SMTP accepts DATA
        |
        X worker mất kết nối
        |
        v
N-100 vẫn ở trạng thái PROCESSING
        |
        v
Lease hết hạn, Worker B xử lý lại
        |
        v
Người nhận có thể nhận bản thứ hai
~~~

Các biện pháp giảm rủi ro:

1. Dùng **event ID** và notification key ổn định để không tạo hai outbox record cho cùng sự kiện.
2. Có unique constraint theo event/notification purpose/recipient khi phù hợp.
3. Ghi nhận mỗi attempt và kết quả SMTP/provider nếu có.
4. Phân biệt lỗi trước submission với timeout sau DATA.
5. Đối soát trường hợp UNKNOWN bằng API hoặc event của nhà cung cấp khi có thể.
6. Không coi cùng **Message-ID** là bảo đảm mailbox sẽ loại bỏ duplicate.

Outbox giúp không đánh mất **ý định gửi**, nhưng không tự biến SMTP thành giao dịch exactly-once. Trường hợp không thể đối soát cần một chính sách theo mức độ quan trọng của notification: ưu tiên tránh mất thông báo hay tránh gửi trùng.

## 27. Phân biệt DNS/TCP exception với SMTP reply code

Một **Connection refused** trước khi có SMTP session không phải là phản hồi SMTP **550**. Hai cơ chế khác nhau:

~~~text
TCP connection refused:
  Socket connect()
       |
       X  Không lập được kết nối

SMTP 550:
  TCP connection OK
       |
       v
  SMTP protocol exchange
       |
       v
  Server trả "550 ..."
~~~

| Nhóm | Ví dụ | Chẩn đoán |
|---|---|---|
| DNS error | UnknownHostException | Hostname/resolver |
| TCP error | ConnectException, SocketTimeoutException tại CONNECT | Port, route, firewall, listener |
| TLS error | SSLHandshakeException | Certificate, protocol, TLS mode |
| SMTP protocol response | 421, 450, 550, 554 | Phản hồi server cho một lệnh SMTP |
| SMTP auth error | MailAuthenticationException hoặc SMTP AUTH failure | Credential/quyền |
| Message preparation | MailParseException, MessagingException | Address, MIME, template |

Không áp dụng “retry theo SMTP 4xx/5xx” cho một lỗi TCP chưa từng nhận SMTP reply. Ngược lại, không sửa DNS khi server đã trả một phản hồi SMTP rõ ràng.

## 28. SMTP debug logs: hữu ích nhưng phải giới hạn

Jakarta Mail có cơ chế debug giao thức. Khi cần chẩn đoán trong môi trường kiểm soát, một số cấu hình có thể bật logging chi tiết:

~~~yaml
spring:
  mail:
    properties:
      mail:
        debug: true
~~~

**Không nên bật debug SMTP diện rộng trong production**. Log giao thức có thể tiết lộ địa chỉ, hostname, metadata gửi, nội dung phản hồi hoặc các chi tiết nhạy cảm khác. Tùy provider/phiên bản, debug cũng có cơ chế kiểm soát log authentication; không nên dựa vào giả định rằng mọi secret sẽ tự được che.

Khi debug:

- Dùng môi trường thử nghiệm và recipient kiểm soát.
- Bật trong khoảng thời gian ngắn.
- Bảo vệ log khỏi truy cập không cần thiết.
- Không gửi OTP hoặc dữ liệu cá nhân thật.
- Tắt sau khi điều tra xong.
- Ưu tiên log lỗi chuẩn hóa và metrics trước khi bật protocol trace.

Một log ứng dụng hữu ích thường chỉ cần:

~~~text
notificationId=...
smtpHost=smtp.example.com
smtpPort=587
phase=CONNECT
errorCategory=TCP_CONNECT_TIMEOUT
attempt=2
nextAttemptAt=...
~~~

Không log **spring.mail.password**, token, toàn bộ MIME body hoặc nội dung attachment.

## 29. Ví dụ Spring Mail service và ghi nhận lỗi kết nối

Một service đơn giản gửi email HTML với plain-text alternative:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender sender;
    private final MailFailureRecorder failureRecorder;

    public NotificationMailService(
            JavaMailSender sender,
            MailFailureRecorder failureRecorder
    ) {
        this.sender = sender;
        this.failureRecorder = failureRecorder;
    }

    public void send(
            String notificationId,
            String recipient,
            String subject,
            String plainText,
            String htmlText
    ) {
        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    true,
                    StandardCharsets.UTF_8.name()
            );
            helper.setFrom("notifications@example.com");
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(plainText, htmlText);
        } catch (MessagingException ex) {
            failureRecorder.recordPreparationFailure(
                    notificationId,
                    "MIME_PREPARATION_FAILURE"
            );
            return;
        }

        try {
            sender.send(message);
        } catch (MailException ex) {
            failureRecorder.recordSubmissionFailure(
                    notificationId,
                    ex
            );
        }
    }
}
~~~

**MailFailureRecorder** là abstraction do ứng dụng thiết kế. Ví dụ trên nhằm làm rõ hai pha **PREPARE** và **SUBMIT**; nó chưa bao gồm outbox, retry worker hay một model lỗi đầy đủ.

Trong triển khai thực:

- Failure recorder phải phân loại exception và cập nhật trạng thái qua transaction database riêng nếu cần.
- Không đánh dấu RETRY vô điều kiện chỉ vì bắt được MailException.
- Phải làm rõ kết quả thành công của **sender.send(message)** và ghi trạng thái submission.
- Phải xử lý ngoại lệ phát sinh từ renderer/attachment nếu có.
- Chỉ tiếp tục công việc nghiệp vụ sau khi biết đã lưu được notification intent hoặc lỗi theo chính sách.
- Với thông báo quan trọng, nên dùng outbox và worker để tránh mất email khi process restart.

### Lưu ý nếu lỗi xuất hiện trong lúc tạo MIME

**MimeMessageHelper** có thể ném MessagingException khi chuẩn bị header/content. Những lỗi này không tương đương với DNS hoặc TCP lỗi. Không retry toàn bộ SMTP trước khi sửa dữ liệu hoặc nguyên nhân chuẩn bị nội dung.

## 30. Ví dụ cấu hình JavaMailSender thủ công

Nếu không dùng Spring Boot auto-configuration, có thể tạo **JavaMailSenderImpl** bằng Java:

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailSenderConfiguration {

    @Bean
    JavaMailSender mailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername("configured-user");
        sender.setPassword("configured-secret");
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
~~~

Trong ví dụ, các chuỗi **configured-user** và **configured-secret** chỉ minh họa. Không hard-code credential thật trong mã nguồn. Ứng dụng cần lấy chúng từ cấu hình/secret manager được bảo vệ.

Nếu tạo bean thủ công, hãy xác nhận nó dùng đúng host, port và JavaMail properties. **spring.mail.properties** có thể không tự áp dụng lên một bean JavaMailSenderImpl được cấu hình tùy chỉnh nếu code tự tạo và không đọc những property đó.

Với nhiều SMTP sender, hãy xác định bean nào đang gửi email lỗi qua tên logic hoặc **@Qualifier**. Hai sender có thể có hostname, port, TLS và timeout khác nhau.

## 31. Chẩn đoán bằng ví dụ tình huống

### Trường hợp A — Chỉ production gặp UnknownHostException

Triệu chứng:

~~~text
Production:
  UnknownHostException: smtp.internal.example

Developer machine:
  DNS lookup thành công
~~~

Cách suy luận:

1. Xác minh production đang dùng đúng host và profile.
2. Tra cứu DNS từ pod/VM production.
3. Kiểm tra private DNS zone và resolver có thể truy cập zone đó không.
4. Kiểm tra DNS policy và kết nối VPN/private network.
5. Nếu DNS đã đổi gần đây, xem TTL/cache.

Không sửa SMTP username/password trước khi đã giải quyết DNS.

### Trường hợp B — DNS thành công nhưng port 587 bị refused

Triệu chứng:

~~~text
DNS: OK
TCP smtp.example.com:587: Connection refused
~~~

Cần kiểm tra:

- Provider có hỗ trợ port 587 ở endpoint đó không?
- Service có đang chạy và lắng nghe port không?
- Có load balancer, firewall reject hoặc policy chặn không?
- Có nhầm hostname của web/API server thành SMTP server không?

Tăng connectiontimeout sẽ không làm một listener không tồn tại bắt đầu hoạt động.

### Trường hợp C — Chỉ container báo connect timeout

Triệu chứng:

~~~text
Laptop: TCP to SMTP host OK
Container: TCP connect timeout
~~~

Cần kiểm tra:

- NetworkPolicy egress.
- Cloud security group/firewall.
- NAT gateway/route table.
- Outbound port filtering.
- IPv4/IPv6 và resolver của container.

Chỉ sau khi có đường TCP thông suốt mới chuyển sang kiểm tra TLS và AUTH.

### Trường hợp D — Kết nối TCP được nhưng read timeout ngay đầu

Triệu chứng:

~~~text
TCP connection established
No SMTP greeting before read timeout
~~~

Nguyên nhân có thể:

- Port đang nói TLS ngầm định trong khi client chờ plaintext greeting.
- Service SMTP bị treo hoặc quá tải.
- Proxy trả kết nối nhưng không chuyển tiếp được dữ liệu.
- Đang kết nối nhầm dịch vụ.

Kiểm tra bằng công cụ TLS/SMTP phù hợp trước khi tăng timeout.

### Trường hợp E — Chỉ email có attachment lớn bị write timeout

Triệu chứng:

~~~text
Email nhỏ: gửi được
Email có attachment lớn: write timeout
~~~

Hướng điều tra:

- Kích thước MIME sau base64 encoding.
- Thời gian gửi trên đường mạng thực tế.
- Giới hạn message của SMTP provider.
- Upload bandwidth, proxy và thiết bị mạng.
- mail.smtp.writetimeout đã phù hợp chưa.

Cân nhắc nén file hoặc gửi liên kết tải an toàn, thay vì chỉ tăng write timeout. Nếu timeout xảy ra sau khi truyền dữ liệu, đánh giá khả năng message đã được nhận.

### Trường hợp F — SMTP đã nhận email nhưng worker không cập nhật được database

Triệu chứng:

~~~text
JavaMailSender.send(message): returns successfully
Update outbox SUBMITTED: database timeout
~~~

Đây không phải lỗi kết nối SMTP. Worker cần khôi phục thao tác ghi trạng thái hoặc đối soát, không tự gửi lại email chỉ vì database update lỗi.

### Trường hợp G — Chỉ một backend/IP trong nhóm DNS gây lỗi

Triệu chứng:

~~~text
smtp.example.com -> IP A, IP B

IP A: kết nối thành công
IP B: connect timeout
~~~

Ứng dụng có thể lỗi không liên tục tùy địa chỉ được chọn. Hãy ghi nhận IP đích thực tế nếu hạ tầng cho phép, kiểm tra load balancer/route và liên hệ provider. Không cố định IP trong cấu hình production nếu provider yêu cầu sử dụng DNS hoặc có thể đổi endpoint.

## 32. Kiểm thử các tình huống mạng trong môi trường thử nghiệm

Để phát hiện lỗi trước production, nên có integration test hoặc môi trường SMTP sandbox mô phỏng:

| Tình huống | Điều cần xác nhận |
|---|---|
| Host không tồn tại | Ứng dụng ghi nhận lỗi DNS và không coi là lỗi recipient |
| Port đóng | Có connection failure; thông báo lỗi được chuẩn hóa |
| Kết nối bị drop | Connect timeout hữu hạn, worker không treo vĩnh viễn |
| Server không trả greeting | Read timeout được ghi nhận |
| TLS mode sai | Cấu hình lỗi, không tắt validation để vượt qua |
| Provider trả 421 tạm thời | Retry theo policy, có backoff |
| Timeout sau DATA | Đánh dấu UNKNOWN, không gửi lại vô điều kiện |
| SMTP được chấp nhận, DB update lỗi | Không tự gửi lại vì lỗi database |
| Chỉ một recipient trong batch lỗi | Không retry những recipient đã được chấp nhận |

Một số công cụ SMTP giả lập/test server có thể thu thập MIME mà không gửi ra Internet. Với việc mô phỏng mất kết nối sau DATA, cần test server có khả năng điều khiển luồng SMTP hoặc proxy test được thiết kế cho mục đích đó.

**Không thử lỗi kết nối trên SMTP production bằng cách cố tình gửi hàng loạt email hoặc tắt firewall tùy tiện.** Việc kiểm thử phải được thực hiện trong môi trường được phép với dữ liệu giả.

## 33. Theo dõi metric và cảnh báo

Các metric nên tách theo lớp lỗi:

| Metric | Ý nghĩa |
|---|---|
| **mail_dns_failure_total** | Số lần lỗi phân giải hostname |
| **mail_connect_refused_total** | Số lần TCP refused |
| **mail_connect_timeout_total** | Số lần connect timeout |
| **mail_read_timeout_total** | Số lần read timeout |
| **mail_write_timeout_total** | Số lần write timeout |
| **mail_tls_failure_total** | Số lần TLS negotiation thất bại |
| **mail_auth_failure_total** | Số lần SMTP authentication lỗi |
| **mail_submission_success_total** | Số lần nộp thư được xác nhận |
| **mail_unknown_outcome_total** | Số lần kết quả nộp không rõ |
| **mail_outbox_oldest_pending_age** | Độ tuổi notification còn chờ |

Không chỉ tính số lỗi tổng cộng. Nếu đồng thời thấy:

- DNS failures tăng: kiểm tra resolver, hostname và thay đổi DNS.
- Refused tăng: kiểm tra server listener, port và firewall reject.
- Connect timeout tăng: kiểm tra egress, route và network capacity.
- Read timeout tăng: kiểm tra SMTP response latency và pha xảy ra lỗi.
- UNKNOWN tăng: kiểm tra mạng ở giai đoạn DATA/response và quy trình đối soát.

### Thông tin log nên có

~~~text
notificationId=...
senderId=transactional-mail
smtpHost=smtp.example.com
smtpPort=587
errorCategory=DNS_FAILURE
sendPhase=RESOLVE
attempt=1
elapsedMs=...
~~~

Không log mật khẩu, OTP, link chứa token, body MIME, nội dung attachment hoặc toàn bộ địa chỉ của khách hàng nếu không thật sự cần và không có kiểm soát truy cập.

### Cảnh báo theo ngưỡng

Ví dụ hệ thống có thể cảnh báo khi:

- Lỗi DNS xảy ra liên tục trên nhiều instance.
- SMTP connect timeout tăng đột biến sau deploy.
- Một sender có tỷ lệ refused cao trong khi sender khác bình thường.
- Outbox pending age vượt SLA.
- Nhiều message vào UNKNOWN và chưa được đối soát.
- Retry queue tăng nhanh hơn throughput xử lý.

Ngưỡng cảnh báo phải phù hợp lưu lượng thực tế để tránh báo động giả khi số lượng email rất nhỏ.

## 34. Một số ngộ nhận cần tránh

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “DNS tra được IP nghĩa là SMTP hoạt động” | DNS chỉ là bước tìm địa chỉ; TCP/TLS/AUTH vẫn có thể lỗi |
| “Ping thất bại nghĩa là port 587 bị chặn” | ICMP và TCP là hai giao thức khác nhau |
| “Connection refused nghĩa là SMTP từ chối email” | Refused thường xảy ra ở TCP, trước các lệnh SMTP |
| “Connect timeout và read timeout giống nhau” | Một lỗi xảy ra khi thiết lập kết nối, một lỗi khi chờ dữ liệu |
| “Tăng timeout sẽ sửa host sai” | Hostname/port sai cần sửa cấu hình |
| “Lỗi DNS nghĩa là MX của người nhận sai” | Ứng dụng submission thường lookup SMTP host được cấu hình |
| “Port 465 luôn dùng STARTTLS” | Port 465 thường yêu cầu TLS ngầm định |
| “Port 587 luôn dùng TLS ngầm định” | Port 587 thường dùng SMTP rồi STARTTLS |
| “MailSendException luôn retry được” | Cần cause, pha gửi và SMTP reply |
| “Read timeout chứng minh email chưa gửi” | Sau DATA có thể đã được server chấp nhận |
| “send() không ném exception tức đã vào Inbox” | Chỉ biết submission thành công ở chặng đang xử lý |
| “Một lần retry chắc chắn không trùng vì có Message-ID” | SMTP không bảo đảm deduplication theo Message-ID |

## 35. Bảng kiểm chẩn đoán nhanh

Khi gặp lỗi DNS, timeout hoặc refused, có thể đi theo trình tự:

1. **Xác định exception gốc**: UnknownHostException, ConnectException, SocketTimeoutException hay lỗi TLS/SMTP khác?
2. **Đối chiếu môi trường**: instance, profile, sender bean và thời điểm deploy.
3. **Kiểm tra host và port hiệu lực**: không in credential vào log.
4. **Thử DNS tại nơi ứng dụng chạy**: A/AAAA, resolver và cache.
5. **Thử TCP tới host:port**: phân biệt refused, timeout, no route.
6. **Kiểm tra firewall/egress**: cloud, container, network policy, NAT, proxy.
7. **Đối chiếu TLS mode**: STARTTLS hay implicit TLS, certificate và hostname.
8. **Kiểm tra các timeout**: connectiontimeout, timeout, writetimeout.
9. **Xác định pha lỗi**: CONNECT, GREETING, AUTH, RCPT TO, DATA hay chờ final reply.
10. **Đặt retry policy đúng**: retry lỗi tạm thời trước submission; dừng lỗi cấu hình; đối soát UNKNOWN.
11. **Theo dõi outbox và từng notification**: tránh retry nguyên batch hoặc gửi trùng.
12. **Quan sát sau khi sửa**: tỷ lệ lỗi, latency, pending age và kết quả chuyển phát.

Đây là luồng chẩn đoán để lựa chọn hành động. Không phải mọi mục đều cần thực hiện khi nguyên nhân đã được xác định rõ từ một bước trước.

## 36. Ghi nhớ

Trong Spring Framework Mail, **lỗi DNS**, **Connection refused** và **timeout** nằm ở các pha khác nhau của quá trình kết nối SMTP:

- **DNS failure** cho biết ứng dụng chưa phân giải được SMTP hostname hoặc gặp lỗi resolver.
- **Connection refused** thường cho biết TCP connection bị từ chối; hãy kiểm tra host, port, listener và firewall reject.
- **Connect timeout** thường chỉ ra đường TCP không phản hồi kịp; hãy kiểm tra routing, network policy, NAT và outbound filtering.
- **Read/write timeout** xảy ra khi kết nối đã tồn tại nhưng trao đổi dữ liệu không hoàn thành trong giới hạn, và phải xét thêm pha SMTP.

Hãy cấu hình **mail.smtp.connectiontimeout**, **mail.smtp.timeout** và **mail.smtp.writetimeout** hữu hạn, kiểm tra DNS và TCP từ chính môi trường chạy ứng dụng, đối chiếu STARTTLS/implicit TLS theo port và đọc cả exception chain của Spring/Jakarta Mail.

Khi triển khai retry, **chỉ thử lại khi lỗi có khả năng tạm thời và có đủ bằng chứng thư chưa được chấp nhận**. Nếu timeout xảy ra sau khi DATA có thể đã đến SMTP server, đánh dấu **UNKNOWN** và đối soát trước khi phát lại. Tách submission status khỏi delivery status, ghi nhật ký lỗi chuẩn hóa và theo dõi notification bằng idempotency/outbox khi cần.

**Chẩn đoán đúng tầng lỗi trước khi sửa cấu hình hoặc retry** là cách giúp hệ thống gửi email ổn định, tránh kéo dài transaction, tránh retry vô ích và giảm nguy cơ gửi trùng.


