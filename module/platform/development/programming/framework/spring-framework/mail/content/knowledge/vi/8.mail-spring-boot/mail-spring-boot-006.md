# spring.mail.protocol và test-connection trong Spring Boot Mail

Khi ứng dụng Spring Boot gửi email bằng `JavaMailSender`, có hai câu hỏi cấu hình thường gặp: **ứng dụng sẽ dùng giao thức nào để kết nối đến máy chủ gửi thư** và **có nên kiểm tra kết nối ngay khi ứng dụng khởi động hay không**. Spring Boot cung cấp hai thuộc tính trực tiếp cho hai nhu cầu đó:

- `spring.mail.protocol` chọn giao thức transport của Jakarta Mail, thường là `smtp` hoặc `smtps`.
- `spring.mail.test-connection` yêu cầu Spring Boot kiểm tra khả năng kết nối của sender ở giai đoạn khởi tạo ứng dụng, khi cơ chế tự cấu hình phù hợp.

Hai thuộc tính có mục đích rất khác nhau. `protocol` ảnh hưởng **cách thư viện tạo transport và mở phiên SMTP**. `test-connection` ảnh hưởng **thời điểm ứng dụng thử kết nối và cách khởi động phản ứng với lỗi**. Việc bật kiểm tra kết nối không tự động gửi email thử, cũng không chứng minh email sẽ được giao tới hộp thư của người nhận.

## 1. Vị trí của hai thuộc tính trong luồng gửi email

Một ứng dụng Spring Boot có thể sử dụng `spring-boot-starter-mail` để có `JavaMailSender`. Luồng đơn giản:

```text
application.properties / application.yml
    |
    +--> spring.mail.host
    +--> spring.mail.port
    +--> spring.mail.username / password
    +--> spring.mail.protocol
    +--> spring.mail.properties.mail.* (TLS, auth, timeout...)
    +--> spring.mail.test-connection
                |
                v
       Spring Boot Mail Auto-configuration
                |
                v
       JavaMailSenderImpl bean
                |
                +--> [khi bật test-connection]
                |      mở transport, connect, close
                |
                +--> [khi service cần gửi]
                       JavaMailSender.send(...)
                            |
                            v
                        SMTP / ESP
```

Điều cần nhớ: cấu hình gửi mail thuộc **hạ tầng SMTP** của ứng dụng. Các đối tượng `SimpleMailMessage` hoặc `MimeMessage` chỉ mang dữ liệu của từng bức thư; chúng không quyết định liệu ứng dụng có chạy kiểm tra kết nối khi khởi động hay không.

Bảng phân biệt nhanh:

| Thuộc tính | Ví dụ | Tác dụng chính | Không phải |
| --- | --- | --- | --- |
| `spring.mail.protocol` | `smtp`, `smtps` | Chọn tên transport để Jakarta Mail sử dụng | Một cờ bật/tắt TLS duy nhất |
| `spring.mail.test-connection` | `true`, `false` | Thử kết nối khi khởi động và báo lỗi nếu không thể kết nối | Một email thử hoặc kiểm chứng delivered |
| `spring.mail.host` | `smtp.example.com` | Máy chủ SMTP đích | Domain `From` xuất hiện trong email |
| `spring.mail.port` | `587`, `465` | Cổng kết nối | Bảo đảm TLS được bật đúng |
| `spring.mail.properties.mail.smtp.*` | `auth`, `starttls.enable`, `timeout` | Các tùy chọn giao thức của Jakarta Mail | Cấu hình chung dùng được với mọi protocol prefix |

## 2. Spring Boot tạo `JavaMailSender` như thế nào?

Trong dự án Spring Boot sử dụng Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Nếu dùng Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
```

Starter thêm các thành phần cần thiết cho Spring Mail và Jakarta Mail. Khi điều kiện auto-configuration được đáp ứng, ví dụ có thông tin host mail hoặc cách tạo mail session được hỗ trợ và chưa có sender bean tùy chỉnh thay thế, Spring Boot có thể tạo `JavaMailSenderImpl` để inject vào service.

Ví dụ:

```java
package example.notification;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class AccountMailService {
    private final JavaMailSender mailSender;

    public AccountMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.com");
        message.setTo(recipient);
        message.setSubject("Chào mừng bạn");
        message.setText("Tài khoản của bạn đã được tạo thành công.");
        mailSender.send(message);
    }
}
```

Service chỉ phụ thuộc vào giao diện `JavaMailSender`. `spring.mail.protocol` và `spring.mail.test-connection` được khai báo ở cấu hình ứng dụng thay vì đưa vào từng lời gọi gửi thư.

### Phạm vi của auto-configuration

`spring.mail.test-connection=true` **không phải lệnh tạo sender bean** khi ứng dụng thiếu dependency hoặc không có cấu hình tạo mail sender phù hợp. Nó chỉ điều khiển cơ chế kiểm tra trên sender được Spring Boot nhận diện và hỗ trợ trong cấu hình thực tế.

Nếu ứng dụng tự tạo một implementation `JavaMailSender` tùy chỉnh hoặc bỏ qua auto-configuration, không nên mặc định rằng thuộc tính kiểm tra kết nối sẽ tự hoạt động trên implementation đó. Cần xác định cách bean được tạo và cơ chế validator được áp dụng ở phiên bản Spring Boot đang sử dụng.

## 3. `spring.mail.protocol` là gì?

`spring.mail.protocol` chọn giao thức transport mà `JavaMailSenderImpl` sử dụng qua Jakarta Mail. Giá trị mặc định thông thường là `smtp`.

Ví dụ:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.protocol=smtp
```

Ở đây, `protocol=smtp` nghĩa là ứng dụng dùng SMTP transport. Nó **không có nghĩa kết nối sẽ không được mã hóa**. SMTP transport có thể:

- kết nối và giao tiếp SMTP không mã hóa nếu cấu hình và máy chủ cho phép;
- nâng cấp sang TLS bằng **STARTTLS** trên một kết nối SMTP đã mở;
- hoặc dùng **TLS ngay từ đầu** khi bật SSL cho `smtp` transport.

Do đó, không thể dựa vào mỗi `spring.mail.protocol` để kết luận mức bảo vệ kết nối. Cần nhìn đồng thời **protocol, port, TLS settings, authentication** và chính sách của SMTP provider.

### `smtp` và `smtps` khác nhau thế nào?

`smtp` và `smtps` là các **protocol name** được thư viện Jakarta Mail hỗ trợ qua provider transport tương ứng. `smtps` là biến thể SMTP dùng kết nối TLS ngay từ đầu, thường gọi là *implicit TLS*.

| Trường hợp | `spring.mail.protocol` | Port thường gặp | Cơ chế TLS | Các property Jakarta Mail |
| --- | --- | --- | --- | --- |
| SMTP với STARTTLS | `smtp` | `587` | Mở SMTP rồi nâng cấp bằng lệnh `STARTTLS` | `mail.smtp.starttls.*` |
| SMTP với implicit TLS | `smtp` | `465` | Bật TLS ngay từ khi kết nối bằng `mail.smtp.ssl.enable=true` | `mail.smtp.ssl.*` |
| SMTPS transport | `smtps` | `465` | TLS ngay từ đầu qua transport `smtps` | `mail.smtps.*` |
| SMTP không mã hóa, nếu hệ thống cho phép | `smtp` | Phụ thuộc relay | Không có TLS | `mail.smtp.*` |

Port 587 và 465 là các cấu hình thông dụng, **không phải quy tắc bảo đảm cho mọi ESP hoặc SMTP relay nội bộ**. Luôn đối chiếu host, port, TLS mode và cơ chế xác thực với nhà cung cấp cụ thể.

### Một hiểu nhầm về tên protocol

Không cấu hình:

```properties
spring.mail.protocol=https
```

`https` là giao thức web, không phải một SMTP transport của thư viện mail. Tương tự, `spring.mail.protocol=465` cũng không có nghĩa là chọn port 465. Thuộc tính protocol chọn **tên transport**, còn port phải khai báo qua `spring.mail.port`.

Nếu chọn tên transport mà thư viện không hỗ trợ, việc tạo hoặc sử dụng transport có thể phát sinh lỗi. Không nên dùng giá trị bất kỳ mà chưa xác định provider Jakarta Mail tương ứng đã có trên classpath.

## 4. Ví dụ cấu hình SMTP với STARTTLS

Một cấu hình Spring Boot phổ biến:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.protocol=smtp

spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000

spring.mail.test-connection=false
```

Ý nghĩa từng nhóm:

1. `host`, `port` và `protocol` xác định endpoint và transport.
2. `username`/`password` cung cấp thông tin xác thực khi provider yêu cầu. Trong thực tế, dùng biến môi trường hoặc secret manager.
3. `mail.smtp.auth=true` yêu cầu SMTP AUTH theo khả năng server.
4. `mail.smtp.starttls.enable=true` cho phép nâng cấp TLS nếu server hỗ trợ.
5. `mail.smtp.starttls.required=true` buộc STARTTLS phải khả dụng; nếu không có TLS phù hợp, quá trình gửi không tiếp tục như một kết nối SMTP plaintext.
6. Ba timeout ngăn các thao tác kết nối, đọc và ghi bị chặn quá lâu.
7. `test-connection=false` tắt bước kiểm tra kết nối ở khởi động; lần gọi gửi mail sau đó vẫn phải kết nối SMTP thực tế.

**Sự khác biệt giữa `enable` và `required`:** chỉ đặt `starttls.enable=true` không luôn bảo đảm kết nối bắt buộc phải có TLS. Khi chính sách cần mã hóa bắt buộc, phải thiết lập `starttls.required=true` hoặc cấu hình TLS tương đương được provider hỗ trợ.

Giá trị timeout ở đây chỉ minh họa; không có một bộ thông số phù hợp với mọi provider.

## 5. Ví dụ cấu hình implicit TLS trên port 465

Có hai cách tổ chức cấu hình thường gặp, cần **chọn nhất quán một cách**.

### Cách A: Dùng `smtp` transport với SSL bật sẵn

```properties
spring.mail.host=smtp.example.com
spring.mail.port=465
spring.mail.protocol=smtp

spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.ssl.enable=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Ở đây, protocol vẫn là `smtp`, nhưng `mail.smtp.ssl.enable=true` yêu cầu kết nối TLS ngay từ đầu. Các property tiếp tục dùng prefix `mail.smtp.` vì transport đang chọn tên `smtp`.

### Cách B: Chọn `smtps` transport

```properties
spring.mail.host=smtp.example.com
spring.mail.port=465
spring.mail.protocol=smtps

spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtps.auth=true
spring.mail.properties.mail.smtps.connectiontimeout=5000
spring.mail.properties.mail.smtps.timeout=10000
spring.mail.properties.mail.smtps.writetimeout=10000
```

Vì `smtps` là transport name riêng, các tùy chọn transport thông thường được tra cứu dưới **`mail.smtps.*`**, không phải `mail.smtp.*`.

Một lỗi cấu hình dễ gặp:

```properties
spring.mail.protocol=smtps
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.timeout=10000
```

Người viết có thể tưởng rằng các thuộc tính `smtp` áp dụng cho `smtps`. Nhưng khi chọn `smtps` transport, các thuộc tính đặc thù cho giao thức này thường phải dùng prefix `mail.smtps.*`. Sai prefix có thể làm timeout hoặc xác thực không hoạt động như dự kiến.

**Không cần thêm `mail.smtps.starttls.enable=true` để yêu cầu STARTTLS trên implicit TLS.** STARTTLS là một cơ chế nâng cấp kết nối; implicit TLS bảo vệ ngay từ đầu. Hai cách có hành vi giao thức khác nhau.

### Lưu ý về chứng chỉ TLS

Kết nối TLS thành công hay thất bại còn phụ thuộc chứng chỉ máy chủ, hostname, trust store và các chính sách kiểm tra nhận dạng. Trong hệ thống production, cần cấu hình TLS để **xác minh danh tính máy chủ**, không bỏ qua certificate validation chỉ nhằm làm hết lỗi kết nối. Các property như `mail.smtp.ssl.checkserveridentity` hoặc `mail.smtps.ssl.checkserveridentity` có thể liên quan tùy transport và implementation; hành vi xác thực hostname mặc định cần xem trong phiên bản Jakarta Mail và cấu hình bảo mật thực tế.

## 6. `spring.mail.test-connection` thực hiện việc gì?

`spring.mail.test-connection` là thuộc tính boolean của Spring Boot, mặc định thường là `false`.

```properties
spring.mail.test-connection=true
```

Khi bật, trong các cấu hình Spring Boot Mail được hỗ trợ, Spring khởi tạo một thành phần kiểm tra sender và gọi thao tác tương đương `JavaMailSenderImpl.testConnection()` ở giai đoạn khởi tạo context.

Bản chất của thao tác này là:

1. Lấy transport phù hợp với `spring.mail.protocol`.
2. Thử **mở kết nối** đến SMTP host/port.
3. Thực hiện các bước cần thiết để mở phiên, chẳng hạn TLS/authentication theo cấu hình.
4. Đóng transport sau khi kiểm tra.
5. Nếu không thể kết nối, phản ánh lỗi và có thể khiến **Spring ApplicationContext khởi động thất bại**.

Nó **không gửi một email thử** tới người nhận, không chạy toàn bộ lệnh `MAIL FROM`/`RCPT TO`/`DATA` của một email nghiệp vụ và không nhận được phản hồi cuối của hệ thống thư bên nhận.

Sơ đồ:

```text
Khởi động Spring Boot
        |
        v
Tạo / cấu hình JavaMailSenderImpl
        |
        v
spring.mail.test-connection = true?
        |
        +-- Không --> tiếp tục khởi động
        |
        +-- Có ----> mở kết nối SMTP/SMTPS
                         |
                         +-- Thành công --> đóng transport
                         |                 --> khởi động tiếp
                         |
                         +-- Thất bại ----> lỗi khởi tạo bean/context
                                           --> ứng dụng có thể không lên
```

### Vì sao gọi đây là startup validation?

Khi gửi email là chức năng bắt buộc của ứng dụng, biết SMTP đang cấu hình sai ngay tại lúc triển khai có thể hữu ích. Ví dụ:

- Host/port sai hoặc network policy chặn đường ra.
- Username/password không đúng, server yêu cầu xác thực.
- Server bắt buộc TLS nhưng client cấu hình sai.
- Máy chủ SMTP tạm thời không sẵn sàng.

Thay vì chỉ phát hiện lỗi khi một người dùng kích hoạt gửi mail sau đó, hệ thống có thể biết sớm ngay trong startup.

Tuy nhiên, tính khả dụng SMTP là điều kiện **biến động theo thời gian**. Kết nối lúc 9:00 thành công không chứng minh đến 9:05 sẽ còn hoạt động. `test-connection` là một phép kiểm tra tại thời điểm nhất định, không phải giám sát liên tục.

## 7. Kiểm tra kết nối chứng minh được gì và không chứng minh được gì?

Bảng ranh giới:

| Câu hỏi | `test-connection=true` có trả lời không? | Giải thích |
| --- | --- | --- |
| Ứng dụng có thể thử mở transport SMTP không? | Có | Đó là mục tiêu chính |
| Host/port có thể truy cập tại thời điểm startup không? | Thường có | Nếu kết nối hoàn tất |
| TLS/auth cấu hình có đủ để mở transport không? | Thường có | Phụ thuộc yêu cầu của server và cách transport kết nối |
| `From` tùy chọn có được provider cho phép không? | **Không chắc** | Chính sách sender có thể chỉ được kiểm tra ở `MAIL FROM` hoặc lúc gửi |
| Một địa chỉ `To` có được chấp nhận không? | Không | Chưa thực hiện giao thư tới recipient cụ thể |
| HTML/MIME/attachment có đúng không? | Không | Không tạo và truyền message nghiệp vụ |
| Email có được MX phía nhận chấp nhận không? | Không | Chưa gửi thư ra ngoài |
| Email có vào inbox hay spam không? | Không | Đây là kết quả ở tầng nhận/phân loại |
| Email có được người dùng mở hoặc click không? | Không | Thuộc telemetry tương tác sau gửi |
| SMTP sẽ luôn khả dụng sau khi startup không? | Không | Kiểm tra là một snapshot |

Trường hợp đáng lưu ý: một ESP có thể cho phép đăng nhập và mở transport thành công nhưng sau đó từ chối `MAIL FROM` do domain chưa được xác minh, hạn mức gửi đã hết, thông điệp quá lớn hoặc tài khoản chưa có quyền gửi. Vì thế test connection không thay thế **gửi email thử có kiểm soát** khi muốn đánh giá đường gửi end-to-end.

### Thử kết nối không phải thử giao thư

`JavaMailSender#send(...)` thực hiện gửi thông điệp. Khi trả về thành công, điều đó thường chỉ xác nhận SMTP relay đã tiếp nhận thông điệp ở ranh giới kết nối của ứng dụng; nó vẫn **không chứng minh đã delivered vào mailbox**. `testConnection()` có phạm vi hẹp hơn nữa: chỉ kiểm tra transport kết nối và đóng lại.

Có thể phân biệt ba cấp:

```text
testConnection()
    └── Có thể mở phiên SMTP/SMTPS?

send(message)
    └── Relay SMTP có tiếp nhận quá trình gửi message?

ESP delivered event / receiving system
    └── Máy chủ nhận có chấp nhận thông điệp?

Inbox placement / human reading
    └── Cần nguồn dữ liệu khác; SMTP không tự chứng minh
```

## 8. Bật test-connection khi nào?

Không có quy tắc bật `true` cho mọi dịch vụ. Quyết định phụ thuộc vai trò của email trong ứng dụng và cách ứng dụng được triển khai.

| Bối cảnh | Lựa chọn cân nhắc | Lý do |
| --- | --- | --- |
| Dịch vụ chỉ có nhiệm vụ gửi email, SMTP là phụ thuộc bắt buộc | Có thể bật `true` | Phát hiện lỗi cấu hình hoặc lỗi kết nối ở startup |
| API nghiệp vụ vẫn phải phục vụ khi SMTP tạm lỗi | Thường cân nhắc `false` và health/queue riêng | Tránh làm toàn bộ ứng dụng không khởi động chỉ vì email |
| Môi trường local không có SMTP server | `false` hoặc dùng test SMTP server | Không làm việc phát triển phụ thuộc email thật |
| Test tự động không cần network | `false`, sử dụng mock/fake | Test dễ lặp lại và không phụ thuộc môi trường ngoài |
| Worker chỉ xử lý email với retry/backoff | Tùy chính sách readiness của worker | Có thể kiểm tra startup nhưng vẫn cần retry sau startup |
| Nhiều replica cùng khởi động hoặc autoscaling | Cân nhắc tải kết nối và phụ thuộc bên ngoài | Tránh toàn bộ replica cùng fail startup khi ESP chập chờn |

Ví dụ, dịch vụ bán hàng có thể tiếp tục tạo đơn hàng ngay cả khi SMTP đang chậm, rồi gửi thông báo qua outbox/queue khi hệ thống phục hồi. Nếu bật `test-connection=true` trên toàn API này, việc SMTP outage có thể khiến deployment mới không lên được, dù nghiệp vụ đặt hàng vẫn có thể phục vụ. Ngược lại, với một worker chuyên gửi email và không có chức năng nào khác, fail fast khi cấu hình SMTP sai có thể hợp lý.

### Startup fail nhanh và khả năng phục hồi

`test-connection=true` giúp phát hiện lỗi nhưng cũng tạo **phụ thuộc startup vào SMTP**. Nếu ESP tạm mất kết nối trong thời gian deploy, ứng dụng có thể không khởi tạo được. Với Kubernetes hoặc các nền tảng có cơ chế restart tự động, điều này có thể dẫn đến vòng lặp khởi động thất bại cho tới khi SMTP phục hồi.

Thay vào đó, có thể:

- Khởi động ứng dụng mà không bắt buộc SMTP luôn online.
- Xử lý yêu cầu gửi bằng queue/outbox bền vững.
- Để worker áp dụng timeout và retry có giới hạn.
- Phát cảnh báo khi số job tồn hoặc lỗi SMTP vượt ngưỡng.
- Chỉ đưa SMTP vào readiness nếu chức năng của instance thật sự không thể hoạt động khi SMTP không sẵn sàng.

Lựa chọn phản ánh **chính sách vận hành**, không phải cái nào luôn “đúng” hơn về mặt kỹ thuật.

## 9. Cấu hình theo môi trường Spring profiles

Một ứng dụng có thể muốn bật test connection trên production nhưng tắt ở local/CI, hoặc ngược lại tùy nhu cầu. Dùng Spring profiles để tách các giá trị này.

Ví dụ file chung `application.yml`:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    test-connection: false
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

Riêng `application-mail-worker.yml`:

```yaml
spring:
  mail:
    test-connection: true
```

Khi chạy với profile `mail-worker`, cấu hình phù hợp được ghi đè. Ví dụ:

```properties
spring.profiles.active=mail-worker
```

Trong hệ thống thực tế, thường nên chọn profile ở môi trường chạy hoặc command-line thay vì commit cố định active profile cho mọi môi trường. Không để tài khoản/mật khẩu production trực tiếp trong file cấu hình.

### Cấu hình bằng biến môi trường

Spring Boot có relaxed binding cho các property đơn giản. Ví dụ:

```text
SPRING_MAIL_PROTOCOL=smtp
SPRING_MAIL_TEST_CONNECTION=true
```

Tuy nhiên các khóa lồng sâu của `spring.mail.properties.mail.smtp.*` cần ánh xạ đúng theo cơ chế configuration binding. Dùng `application.properties`/`application.yml` với key có dấu chấm là cách dễ đọc và ít nhầm; nếu cấu hình hoàn toàn từ môi trường, cần xác minh giá trị thực tế được bind vào Jakarta Mail properties.

Khi có nhiều nguồn cấu hình (defaults, profile, environment, command-line, secret manager), **nguồn có precedence cao hơn** có thể ghi đè giá trị từ file. Vì thế, nếu startup behavior khác mong muốn, trước hết kiểm tra effective configuration và profile đang bật, tránh để lộ mật khẩu trong log.

## 10. test-connection kết hợp timeout: cấu hình không thể thiếu

Một sai sót thường gặp là bật:

```properties
spring.mail.test-connection=true
```

nhưng không cấu hình timeout socket. Khi SMTP endpoint không phản hồi, bước kiểm tra có thể chờ quá lâu, làm chậm khởi động.

Ba thuộc tính đáng quan tâm:

```properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Chúng có ý nghĩa:

- **Connection timeout**: giới hạn thời gian mở kết nối TCP.
- **Read timeout**: giới hạn thời gian chờ một thao tác nhận dữ liệu từ SMTP server.
- **Write timeout**: giới hạn thời gian một thao tác ghi lên socket bị chặn.

Khi dùng `smtps` transport, dùng prefix tương ứng:

```properties
spring.mail.properties.mail.smtps.connectiontimeout=5000
spring.mail.properties.mail.smtps.timeout=10000
spring.mail.properties.mail.smtps.writetimeout=10000
```

Đừng xem ba timeout này là một deadline tổng cho startup hoặc `send()`. DNS resolution, nhiều lần đọc/ghi tuần tự và các bước TLS có thể làm tổng thời gian vượt từng ngưỡng đơn lẻ. Khi phụ thuộc SMTP ảnh hưởng thời gian khởi động, nên quan sát startup latency và đặt chính sách triển khai phù hợp.

### Read timeout quan trọng cả với test connection

Một endpoint có thể chấp nhận TCP nhanh nhưng **không gửi banner SMTP** hoặc phản hồi chậm trong quá trình STARTTLS/AUTH. `connectiontimeout` không xử lý được mọi trường hợp đó. `mail.smtp.timeout` mới giúp ngăn thao tác đọc bị treo.

### Write timeout không chỉ dành cho attachment

Trong phiên kiểm tra kết nối, vẫn có thể có các thao tác ghi giao thức như `EHLO`, `STARTTLS` và `AUTH`. Trong phiên gửi thư thật, write timeout càng quan trọng khi truyền body hoặc attachment. Cả hai bối cảnh đều cần cấu hình đúng khi có thể xảy ra socket write blocking.

## 11. Tự gọi `testConnection()` khi cấu hình bean thủ công

Khi ứng dụng không dùng cơ chế kiểm tra kết nối auto-configured của Spring Boot, `JavaMailSenderImpl` có phương thức `testConnection()` có thể được gọi trực tiếp ở tầng hạ tầng hoặc một lệnh chẩn đoán có kiểm soát.

Ví dụ code sử dụng bean đã khởi tạo:

```java
package example.mail;

import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public class MailConnectionDiagnostic {
    private final JavaMailSenderImpl sender;

    public MailConnectionDiagnostic(JavaMailSenderImpl sender) {
        this.sender = sender;
    }

    public void verifySmtpConnection() throws MessagingException {
        sender.testConnection();
    }
}
```

Đoạn code minh họa API, không tự tạo startup check. Muốn gọi ở startup, có thể tạo một bean khởi tạo hoặc runner phù hợp, nhưng cần xem việc fail startup có đúng ý định vận hành hay không.

Nếu dùng `JavaMailSender` qua interface, hãy nhớ **`testConnection()` là API trên `JavaMailSenderImpl`** chứ không phải phương thức bắt buộc của mọi implementation `JavaMailSender`. Vì vậy, code nghiệp vụ gửi email nên tiếp tục phụ thuộc vào interface; code kiểm tra transport có thể nằm trong lớp hạ tầng riêng và biết rõ loại implementation đang kiểm tra.

### Một `@Bean` sender thủ công

```java
package example.mail;

import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class ManualMailConfiguration {
    @Bean
    public JavaMailSender mailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setProtocol("smtp");
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));

        Properties settings = new Properties();
        settings.put("mail.smtp.auth", "true");
        settings.put("mail.smtp.starttls.enable", "true");
        settings.put("mail.smtp.starttls.required", "true");
        settings.put("mail.smtp.connectiontimeout", "5000");
        settings.put("mail.smtp.timeout", "10000");
        settings.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(settings);
        return sender;
    }
}
```

`sender.setProtocol("smtp")` ở đây tương ứng về mục đích với `spring.mail.protocol=smtp` khi Boot cấu hình sender. Tuy nhiên, nếu đã tạo bean thủ công như trên, các thuộc tính `spring.mail.*` **không nhất thiết còn được Boot tự bind vào bean đó**. Đừng đồng thời giữ hai nguồn cấu hình mà không biết nguồn nào thực sự được dùng.

Nếu bật `spring.mail.test-connection=true`, việc validator của Boot có áp dụng cho bean tự khai báo hay không còn phụ thuộc vào loại bean và điều kiện auto-configuration/phiên bản. Cách an toàn là xác định rõ lifecycle của sender trong dự án; không giả định một property có hiệu lực với mọi bean tùy chỉnh.

## 12. Lỗi khởi động và cách chẩn đoán

Khi `spring.mail.test-connection=true`, lỗi SMTP có thể khiến context khởi động thất bại hoặc khiến lỗi BeanCreationException xuất hiện. Thông điệp bên trong có thể chứa cause từ Jakarta Mail hoặc Java networking.

| Biểu hiện/cause | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `UnknownHostException` | DNS không phân giải hostname | Kiểm tra `spring.mail.host`, DNS và network policy |
| `ConnectException: Connection refused` | Cổng không mở hoặc endpoint từ chối | Kiểm tra host, port và outbound firewall |
| `SocketTimeoutException: connect timed out` | TCP connect không hoàn thành | Kiểm tra kết nối mạng, firewall bỏ gói và connection timeout |
| `SocketTimeoutException: Read timed out` | Server không trả dữ liệu đúng hạn | Kiểm tra SMTP banner, TLS/auth và read timeout |
| Lỗi `535 Authentication failed` hoặc tương tự | Username/password hoặc phương thức xác thực sai | Kiểm tra secret, tài khoản và yêu cầu provider |
| `SSLHandshakeException` | Lỗi chứng chỉ, hostname hoặc TLS protocol | Xác minh certificate chain, trust store, TLS mode |
| Thông báo không hỗ trợ STARTTLS | Server không có STARTTLS hoặc dùng sai port/mode | Chọn đúng giao thức/cổng; không tắt TLS bừa |
| Không tìm được transport provider | `spring.mail.protocol` không hợp lệ hoặc thiếu dependency | Kiểm tra protocol name và Jakarta Mail implementation |
| Startup thành công nhưng gửi mail thật bị reject | Sender address, recipient, quota, kích thước hoặc policy bị kiểm tra lúc gửi | Kiểm tra SMTP reply và ESP logs; test connection không bao trùm |

### Sai port và TLS mode có thể tạo triệu chứng khó hiểu

Ví dụ:

```properties
spring.mail.protocol=smtp
spring.mail.port=465
spring.mail.properties.mail.smtp.starttls.enable=true
```

Nếu endpoint 465 thực tế **yêu cầu TLS ngay từ đầu**, client SMTP thông thường đang chờ một banner plaintext, còn server chờ client bắt đầu TLS handshake. Sự không khớp này có thể tạo read timeout hoặc lỗi giao thức.

Cấu hình đúng nên là một trong các dạng tương thích với server:

```properties
# Một cách dùng implicit TLS với smtp transport:
spring.mail.protocol=smtp
spring.mail.port=465
spring.mail.properties.mail.smtp.ssl.enable=true
```

hoặc:

```properties
# Dùng smtps transport:
spring.mail.protocol=smtps
spring.mail.port=465
spring.mail.properties.mail.smtps.auth=true
```

Đừng sửa lỗi bằng cách tăng timeout vô hạn. Hãy xác định server dùng STARTTLS hay implicit TLS trước.

### Lỗi xác thực không nhất thiết là lỗi mật khẩu

Máy chủ có thể từ chối do account bị khóa, application password chưa được cấp, IP chưa được phép, cơ chế AUTH không được hỗ trợ hoặc chính sách bảo mật không chấp nhận phương thức đăng nhập. Kiểm tra thông tin từ SMTP provider; tránh ghi hoặc chia sẻ nguyên thông tin xác thực trong log chẩn đoán.

## 13. Kiểm thử và môi trường CI

`test-connection=true` có thể khiến bài test tải cả Spring ApplicationContext phụ thuộc vào SMTP thật. Điều này làm test dễ thất bại vì DNS, firewall, provider outage hoặc việc thiếu secret.

Với **unit test** service, thường chỉ cần mock `JavaMailSender`:

```java
package example.mail;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class AccountMailerTest {
    @Test
    void sendsMessageThroughInjectedSender() {
        JavaMailSender sender = mock(JavaMailSender.class);

        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo("test@example.net");
        message.setSubject("Test");
        message.setText("Hello");

        sender.send(message);

        verify(sender).send(message);
    }
}
```

Ví dụ chỉ minh họa cách một mock có thể được sử dụng khi test gọi `send`. Trong một unit test nghiệp vụ thực sự, cần inject mock vào **service đang được kiểm thử**, kích hoạt hành vi của service, rồi xác minh nội dung được gửi.

Với **integration test** cấu hình mail, có thể chạy SMTP test server cục bộ hoặc container SMTP giả lập, sau đó đặt `spring.mail.host` và `spring.mail.port` về endpoint đó. Khi muốn test startup validation, bật `test-connection=true` trong môi trường kiểm thử có kiểm soát.

Ví dụ cấu hình cho test SMTP server trên máy cục bộ:

```properties
spring.mail.host=127.0.0.1
spring.mail.port=2525
spring.mail.protocol=smtp
spring.mail.test-connection=true

spring.mail.properties.mail.smtp.auth=false
spring.mail.properties.mail.smtp.starttls.enable=false
spring.mail.properties.mail.smtp.connectiontimeout=2000
spring.mail.properties.mail.smtp.timeout=3000
spring.mail.properties.mail.smtp.writetimeout=3000
```

Cấu hình này chỉ phù hợp nếu test SMTP server thực sự lắng nghe ở port 2525 và cho phép kết nối không xác thực/TLS. **Không sử dụng cấu hình plaintext như vậy cho SMTP Internet production.**

### Những mức kiểm thử khác nhau

| Loại test | Mục tiêu | `test-connection` có đủ không? |
| --- | --- | --- |
| Unit test tạo nội dung | Kiểm tra To, Subject, body, template | Không cần kết nối SMTP |
| Startup connection test | Xác minh transport có thể connect | Có thể dùng `true` |
| SMTP integration test | Xác minh gửi lệnh/data và MIME | Cần gửi thư vào SMTP test server |
| Provider acceptance test | Kiểm tra sender/domain/quota/policy | Cần test gửi thật theo quy tắc provider |
| End-to-end delivery test | Xác nhận delivered/bounce ở hệ thống đích | Cần ESP events hoặc hộp thư thử nghiệm |

Khi dùng CI, không nên để mọi unit test vô tình kết nối vào tài khoản SMTP production. Secrets và mạng ngoài khiến test chậm, không ổn định và có thể tạo yêu cầu gửi thật ngoài ý muốn.

## 14. test-connection không thay thế health check liên tục

Spring Boot có hệ thống Actuator để cung cấp health/readiness theo cấu hình và thành phần hỗ trợ. Tuy nhiên, `spring.mail.test-connection` tự thân là **startup check**, không phải một lịch kiểm tra định kỳ.

Một health indicator hoặc probe riêng có thể kiểm tra khả năng kết nối SMTP, nhưng cần cân nhắc tác động:

- Mỗi lần mở phiên SMTP có thể tốn DNS, TCP, TLS, AUTH và tài nguyên provider.
- Gọi ở tần suất quá cao có thể tăng số kết nối, gặp throttling hoặc khiến server security phát hiện đăng nhập bất thường.
- Đưa SMTP outage vào readiness của **mọi** HTTP instance có thể làm traffic bị rút khỏi toàn bộ ứng dụng dù các API khác vẫn hoạt động.
- Nếu dùng `testConnection()` đồng bộ trong request health, probe có thể bị treo khi thiếu timeout.
- Một lần check thành công chưa bảo đảm các lần gửi sau đó thành công.

Với hệ thống gửi email qua queue, các chỉ số như **số job đang chờ**, **thời gian job lâu nhất**, **tỉ lệ gửi lỗi**, **retry backlog**, **tỉ lệ bounce** và **provider API status** thường cung cấp bức tranh vận hành hữu ích hơn việc mỗi giây mở một SMTP connection mới.

Nếu cần health indicator động cho SMTP, nên xác định phạm vi triển khai, tần suất, timeout và ảnh hưởng tới readiness/liveness một cách có chủ đích. Đừng nhầm lẫn startup check với khả năng hồi phục.

## 15. Một vài câu hỏi thường gặp

### Có phải `spring.mail.protocol=smtps` mới gửi email an toàn?

Không. `smtp` có thể dùng STARTTLS hoặc implicit TLS khi cấu hình đúng. `smtps` là tên transport cho implicit TLS; bảo mật phụ thuộc thiết lập TLS, chứng chỉ, xác thực, chính sách SMTP và server, không chỉ tên giao thức.

### Đặt `spring.mail.protocol=smtp` và port 465 có được không?

Có, **nếu** dùng `mail.smtp.ssl.enable=true` và provider yêu cầu implicit TLS. Nếu chỉ bật STARTTLS với một endpoint chỉ chấp nhận TLS từ byte đầu tiên, có thể bị timeout hoặc lỗi handshake.

### Có phải `spring.mail.test-connection=true` tự gửi một thư tới tài khoản cấu hình?

Không. Nó kiểm tra khả năng mở transport SMTP và đóng lại. Không có địa chỉ người nhận hay nội dung thư thử được gửi chỉ nhờ property này.

### Vì sao khởi động được nhưng `send()` vẫn thất bại?

Vì startup check không bao trùm quy tắc cho `From`, `To`, kích thước thư, nội dung MIME, giới hạn quota hoặc trạng thái mạng thay đổi sau startup. Nhà cung cấp có thể chỉ từ chối khi thực sự có lệnh gửi thư.

### Nếu tắt test connection thì mail có còn gửi được không?

Có. `spring.mail.test-connection=false` chỉ bỏ qua kiểm tra lúc khởi động. Khi service gọi `send()`, transport vẫn kết nối và gửi thư theo cấu hình SMTP bình thường.

### Có nên đặt `test-connection=true` để dùng như readiness probe?

Không mặc định. Thuộc tính này chỉ tác động startup. Một readiness probe cần thiết kế riêng, xét xem SMTP outage có thực sự khiến instance không thể phục vụ chức năng chính hay không.

### Thay đổi `spring.mail.protocol` có cần đổi các property khác không?

Thường có. Nếu đổi từ `smtp` sang `smtps` transport, các tùy chọn riêng như `auth` và timeout có thể phải đổi prefix `mail.smtp.*` thành `mail.smtps.*`. Ngoài ra cần đồng bộ port và TLS mode với provider.

## 16. Cách triển khai trong một dự án thực tế

Giả sử ứng dụng có API đặt hàng và worker gửi email riêng. Hai thành phần dùng cùng nhà cung cấp SMTP nhưng có yêu cầu availability khác nhau.

**Cấu hình API đặt hàng:** API phải phục vụ được cả khi ESP tạm lỗi. Nó ghi yêu cầu email vào outbox để worker xử lý. Trong môi trường này, bật test-connection ở API chưa chắc hữu ích, nhất là nếu API không trực tiếp gửi SMTP. Ưu tiên để API khởi động và duy trì outbox an toàn.

**Cấu hình worker gửi email:** Worker cần kết nối SMTP để làm công việc chính. Có thể dùng:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.protocol=smtp

spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000

spring.mail.test-connection=true
```

Nếu worker không kết nối được ngay từ đầu, lỗi startup báo cấu hình hoặc mạng đang có vấn đề. Tuy nhiên, worker vẫn phải thiết kế **retry/backoff** trong runtime vì SMTP có thể đứt sau khi startup thành công.

**Trong CI:** Unit test không kết nối SMTP thật, integration test sử dụng SMTP test server được quản lý trong môi trường kiểm thử. Có thể bật test connection cho test startup cụ thể để xác nhận đúng behavior.

**Trong vận hành:** Quan sát các sự kiện kết nối, gửi, lỗi xác thực, timeout, backlog và delivered/bounce. Không đánh đồng “startup test xanh” với “mọi email đã giao thành công”.

## 17. Ghi nhớ

Hai thuộc tính phối hợp với nhau, nhưng ở hai tầng khác nhau:

```text
spring.mail.protocol
  = lựa chọn transport SMTP/SMTPS
  = ảnh hưởng prefix thuộc tính, TLS mode và cách kết nối

spring.mail.test-connection
  = có thực hiện thử mở/đóng transport khi startup hay không
  = giúp phát hiện sớm lỗi kết nối/cấu hình
  = không tạo email thử, không chứng minh delivered
```

Khi cấu hình Spring Boot Mail, hãy **chọn giao thức theo yêu cầu của SMTP provider**, đặt host/port/TLS/auth/timeout tương ứng, và chỉ bật `test-connection` khi việc phụ thuộc vào SMTP ngay lúc khởi động phù hợp với kiến trúc vận hành. Một phép thử kết nối thành công là tín hiệu khả dụng của transport tại thời điểm đó; khả năng gửi, giao nhận và đọc email cần được xác minh bằng các cơ chế riêng.
