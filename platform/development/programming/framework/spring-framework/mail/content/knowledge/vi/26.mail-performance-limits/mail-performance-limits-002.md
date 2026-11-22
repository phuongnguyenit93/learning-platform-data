# Tái sử dụng JavaMailSender và connection configuration

Trong **Spring Framework Mail**, một ứng dụng có thể gửi vài email mỗi ngày hoặc hàng chục nghìn thông báo qua nhiều worker. Nếu mỗi email lại tạo mới toàn bộ cấu hình SMTP, khởi tạo `JavaMailSenderImpl`, đọc secret, cấu hình TLS và tự quản lý kết nối, hệ thống khó kiểm soát tài nguyên, dễ sinh lỗi khác nhau giữa các luồng gửi và khó quan sát hiệu năng.

Tuy nhiên, “tái sử dụng JavaMailSender” cũng thường bị hiểu sai: **tái sử dụng bean `JavaMailSender` hoặc Jakarta Mail `Session` không đồng nghĩa với việc mọi email sẽ dùng chung một kết nối TCP/SMTP đang mở**. Với cách triển khai thông dụng, `JavaMailSenderImpl` có thể mở và đóng SMTP `Transport` cho một lượt `send(...)`, trong khi một lời gọi gửi nhiều thông điệp có thể tận dụng một kết nối trong phạm vi lời gọi đó. Connection pooling hoặc giữ kết nối qua nhiều lời gọi là quyết định riêng của hạ tầng, không phải bảo đảm tự động của Spring Mail.

Bài học này giải thích **đối tượng nào nên tái sử dụng, đối tượng nào không nên chia sẻ, cấu hình connection nên đặt ở đâu và những giới hạn hiệu năng cần hiểu rõ**. Chúng ta sẽ phân biệt chi phí dựng MIME với chi phí kết nối SMTP, thiết kế singleton sender an toàn, quản lý nhiều nhà cung cấp hoặc tenant, giới hạn concurrency/rate, đo lường hiệu năng và kiểm thử bằng SMTP sandbox.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của `JavaMailSender`, `JavaMailSenderImpl`, Jakarta Mail `Session`, `MimeMessage`, `MimeMessageHelper` và SMTP `Transport`.
- Tái sử dụng một **Spring-managed `JavaMailSender` bean** thay vì tạo sender mới cho mỗi email.
- Phân biệt **sender reuse**, **session reuse**, **connection reuse** và **batch send**.
- Cấu hình host, port, credential, TLS, hostname verification và timeout một cách nhất quán.
- Hiểu giới hạn của `send(MimeMessage...)`: có thể giảm số lần connect, nhưng vẫn gửi từng MIME message và có thể gặp partial failure.
- Sử dụng sender từ nhiều thread mà không chia sẻ những `MimeMessage` mutable.
- Giới hạn concurrency, queue backlog và tốc độ gửi theo khả năng SMTP provider.
- Quản lý nhiều SMTP profiles mà không thay đổi cấu hình của singleton trong lúc đang gửi.
- Thiết kế retry/outbox mà không làm tăng số submission ngoài ý muốn.
- Kiểm tra hiệu năng và kết nối thực tế bằng integration test phù hợp.

## 2. Sơ đồ các thành phần trong Spring Mail

```text
Spring Boot application
       |
       +--> NotificationService
       |
       +--> EmailOutboxWorker
       |
       +--> Other business services
                 |
                 v
       JavaMailSender (Spring bean, shared)
                 |
                 v
       JavaMailSenderImpl
         - host / port
         - username / password
         - JavaMail properties
         - Jakarta Mail Session
                 |
                 +--> createMimeMessage()
                 |       |
                 |       v
                 |   MimeMessage (mỗi email một instance)
                 |       |
                 |   MimeMessageHelper (gắn với message đó)
                 |
                 +--> send(...)
                         |
                         v
                    SMTP Transport
                         |
                    TCP / TLS / AUTH
                         |
                         v
                  SMTP relay/provider
```

Mỗi thành phần có vòng đời và nhiệm vụ khác nhau:

| Thành phần | Vai trò | Cách sử dụng thường phù hợp |
|---|---|---|
| `JavaMailSender` | Spring abstraction để xây và gửi email | Inject và **tái sử dụng bean**. |
| `JavaMailSenderImpl` | Triển khai sender, giữ cấu hình SMTP và Jakarta Mail Session | Cấu hình một lần khi khởi động; dùng chung nếu cùng SMTP profile. |
| `jakarta.mail.Session` | Chứa properties, authenticator và context JavaMail | Có thể được sender tái sử dụng; **không phải TCP connection**. |
| `MimeMessage` | Một email cụ thể gồm headers và MIME body | **Tạo riêng cho mỗi message/attempt**. |
| `MimeMessageHelper` | Giúp thêm From, To, Subject, HTML, inline và attachment | Tạo riêng gắn với một `MimeMessage`. |
| SMTP `Transport` | Kết nối giao thức để gửi message lên server | Thường do sender quản lý trong lời gọi `send`; không chia sẻ tùy tiện qua threads. |
| Outbox/queue worker | Điều phối job, retry, concurrency và trạng thái | Quản lý độc lập với tuổi thọ của sender bean. |

**Điểm cốt lõi:** Bean của sender là **cấu hình và năng lực gửi** có thể dùng chung; một `MimeMessage` là **trạng thái của một thư cụ thể** không nên tái sử dụng hoặc bị nhiều thread sửa đồng thời.

## 3. Đừng tạo JavaMailSenderImpl mới cho từng email

Một cách viết thường gặp nhưng không tốt:

```java
public void sendNotice(String recipient, String body) {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("smtp.example.com");
    sender.setPort(587);
    sender.setUsername(System.getenv("SMTP_USER"));
    sender.setPassword(System.getenv("SMTP_PASSWORD"));

    Properties props = sender.getJavaMailProperties();
    props.put("mail.smtp.starttls.enable", "true");

    SimpleMailMessage message = new SimpleMailMessage();
    message.setTo(recipient);
    message.setText(body);

    sender.send(message);
}
```

Những vấn đề:
1. Cấu hình SMTP bị rải rác vào code nghiệp vụ.
2. Secret có thể được đọc và xử lý nhiều lần không cần thiết.
3. Các luồng gửi dễ khác nhau về TLS, hostname check và timeout.
4. Test khó thay `JavaMailSenderImpl` bằng mock.
5. Việc thay provider/secret không có điểm quản lý tập trung.
6. Người đọc có thể nhầm rằng tạo lại sender sẽ có kết nối “mới và an toàn hơn”, trong khi sender instance **không trực tiếp đồng nghĩa** với transport connection.
7. Mỗi bản sao sender có thể giữ thêm đối tượng cấu hình/session và làm vòng đời phức tạp hơn mà không tạo ra lợi ích thiết thực.

Việc tạo sender mới **không nhất thiết** là nguyên nhân chính làm chậm SMTP; phần tốn kém thường là mạng/TLS/AUTH. Nhưng thiết kế này gây rủi ro cấu hình và làm khó tối ưu hóa/đo lường trong dài hạn.

### 3.1. Cách đúng: Dependency Injection

```java
package com.example.mail;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final JavaMailSender mailSender;

    public NotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    // Các phương thức gửi sử dụng cùng bean mailSender.
}
```

Spring quản lý sender và inject vào các service/worker cần dùng. Một profile SMTP thường chỉ cần một bean singleton cấu hình ổn định.

### 3.2. Không cần tự cache sender trong static field

Tránh:

```java
private static JavaMailSender cachedSender;
```

Static global state thường không cần thiết khi đã có Spring dependency injection; nó gây khó khăn cho test, lifecycle và việc dùng nhiều profiles. Để Spring container quản lý bean và truyền dependency qua constructor.

## 4. Vòng đời của JavaMailSenderImpl, Session và Transport

Cần hiểu bốn hành động khác nhau:

```text
Application startup
      |
      v
Create JavaMailSenderImpl bean
      |
      | Configure SMTP properties once
      v
Reuse sender and its mail configuration
      |
      +--> createMimeMessage() -> message A
      +--> createMimeMessage() -> message B
      |
      v
send(message A)
      |  connect / TLS / AUTH / SMTP DATA / close*
      v
send(message B)
         connect / TLS / AUTH / SMTP DATA / close*
```

`*` Mô tả hành vi thường gặp của sender SMTP trong cách triển khai chuẩn; cần xác minh khi dùng transport tùy biến hoặc provider API khác.

### 4.1. `Session` không phải kết nối mạng

Một `jakarta.mail.Session` chứa các property và cấu hình cho Jakarta Mail. Nó có thể tồn tại lâu hơn nhiều kết nối SMTP.

Vì vậy:
- Sender/session được tái sử dụng **không chứng minh** TCP socket vẫn mở.
- `createMimeMessage()` không có nghĩa là SMTP connect.
- `getSession()` không phải một phương thức “lấy connection từ pool”.
- Nếu một hệ thống đo số TLS handshakes tăng theo số lần gửi, điều đó không mâu thuẫn với việc chỉ có một sender bean.

### 4.2. Mỗi `send(...)` thường là một vòng gửi

Trong `JavaMailSenderImpl`, gửi SMTP thường bao gồm việc lấy `Transport`, kết nối nếu chưa kết nối, gửi từng MIME message và đóng transport khi kết thúc thao tác. Chi tiết cụ thể phụ thuộc phiên bản Jakarta Mail/Spring và cấu hình.

Không nên mặc định rằng:

```java
sender.send(first);
sender.send(second);
```

sẽ tái sử dụng **cùng một SMTP TCP connection** qua cả hai lời gọi.

### 4.3. Gửi nhiều message trong một lời gọi có khác biệt

```java
sender.send(first, second);
```

Có thể cho phép triển khai sender tái sử dụng `Transport` trong phạm vi cùng lời gọi gửi nhiều message. Điều này có thể giảm chi phí connect/TLS/AUTH so với hai lời gọi đơn lẻ.

Nhưng:
- `first` và `second` vẫn là **hai MIME messages**;
- mỗi message vẫn có SMTP envelope/DATA riêng;
- kết quả có thể thành công một phần;
- không bảo đảm provider luôn giữ connection trong toàn bộ batch;
- không tự tạo một session/pool chung cho các lời gọi tiếp theo.

Đây là một tối ưu cần đo lường và thiết kế error handling, không phải quy tắc “cứ gom càng nhiều message càng tốt”.

## 5. Spring Boot cấu hình JavaMailSender tập trung

Với `spring-boot-starter-mail`, Spring Boot có thể tự cấu hình `JavaMailSender` khi điều kiện auto-configuration và SMTP properties phù hợp.

### 5.1. STARTTLS trên port 587

```yaml
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
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
```

Ý nghĩa:
- `host/port`: endpoint SMTP được provider công bố.
- `username/password`: credential lấy từ cấu hình/secret store.
- `default-encoding`: encoding mặc định Spring dùng ở nơi phù hợp.
- `starttls.enable=true`: sử dụng STARTTLS khi endpoint hỗ trợ.
- `starttls.required=true`: fail nếu server không thể nâng cấp TLS.
- `ssl.checkserveridentity=true`: kiểm tra hostname với certificate của SMTP server.
- `connectiontimeout`: giới hạn thời gian thiết lập TCP.
- `timeout`: giới hạn thời gian đọc dữ liệu từ socket.
- `writetimeout`: giới hạn thời gian ghi dữ liệu tới socket.

Các timeout trong ví dụ là **mili giây** theo Jakarta Mail SMTP properties, không phải đơn vị giây. Con số minh họa phải được điều chỉnh theo độ trễ network, kích thước message và SLA.

### 5.2. Implicit TLS trên port 465

Nếu provider yêu cầu TLS ngay từ đầu kết nối:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
```

STARTTLS và implicit TLS **khác cách khởi tạo kết nối**. Không bật `mail.smtp.ssl.enable=true` trên cổng chỉ chờ EHLO/STARTTLS, và không chỉ bật `starttls.enable` cho cổng implicit TLS.

### 5.3. Vì sao timeout là vấn đề hiệu năng?

Một kết nối SMTP có thể treo khi:
- DNS/TCP/connect gặp sự cố;
- TLS handshake bị chậm;
- server không phản hồi SMTP command;
- tốc độ đọc/ghi mạng giảm;
- gửi attachment lớn qua một đường truyền chậm.

Nếu timeout mặc định quá dài hoặc không giới hạn theo hạ tầng, worker có thể giữ tài nguyên và không xử lý job khác. Nếu timeout quá ngắn, ứng dụng tạo false failures và retry nhiều hơn, làm lưu lượng tăng và có nguy cơ gửi trùng khi kết quả không rõ.

**Timeout phải phối hợp với concurrency limit, job lease, retry policy và kích thước email.** Không chọn các giá trị một cách độc lập.

### 5.4. Không để fallback sang plaintext

Nếu provider yêu cầu STARTTLS, `starttls.required=true` là biện pháp fail closed. Không bỏ `required` để “nhanh hơn” hoặc “tránh handshake lỗi”, vì điều đó có thể khiến authentication và nội dung thư không còn được bảo vệ như mong muốn.

Tối ưu hiệu năng không được đánh đổi việc xác thực server TLS, hostname hoặc bảo vệ credential.

## 6. Cấu hình sender thủ công trong Spring Framework

Không phải ứng dụng nào cũng dùng Boot auto-configuration. Có thể tạo bean tường minh:

```java
package com.example.mail;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class SmtpConfiguration {

    @Bean
    public JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender =
            new JavaMailSenderImpl();

        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
```

Đây là ví dụ phục vụ mục tiêu cấu hình/lifecycle. Trong production:
- Không hardcode credential.
- Có thể inject configuration properties/secret manager.
- Không log biến môi trường chứa secret.
- Không tạo các sender trùng lặp vô nghĩa nếu Boot đã tạo một sender đúng.
- Nếu ứng dụng cần nhiều sender, định danh rõ từng bean/profile.

### 6.1. Tại sao không thay đổi properties ngay trước mỗi lần gửi?

Không nên viết:

```java
sender.setHost(tenantSmtpHost);
sender.setUsername(tenantUsername);
sender.setPassword(tenantPassword);
sender.send(message);
```

trên **một singleton đang được nhiều thread dùng**.

Hai request có thể xen kẽ:
- Thread A thay username của tenant A.
- Thread B thay username thành tenant B.
- Thread A gửi bằng cấu hình của B.

Điều này vừa gây lỗi deliverability vừa có thể làm lộ dữ liệu/credential giữa tenants. Hãy cấu hình một sender ổn định cho mỗi profile hoặc có abstraction chọn sender với isolation được kiểm soát, không mutating bean toàn cục trong lúc gửi.

### 6.2. Configuration is a snapshot

Sau startup, hãy coi cấu hình của một `JavaMailSenderImpl` dùng chung là **gần như bất biến về mặt vận hành**:
- host/port;
- username/secret;
- TLS mode;
- SMTP properties;
- default encoding.

Khi cần đổi secret hoặc provider, thực hiện quy trình refresh có kiểm soát, thay cấu hình/bean instance theo lifecycle phù hợp, và tránh biến đổi đồng thời trên sender đang xử lý nhiều email.

## 7. Tạo MimeMessage và MimeMessageHelper mới cho mỗi email

Tái sử dụng sender nhưng **không tái sử dụng message object**.

Đúng:

```java
public void sendNotice(String recipient, String body)
        throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();

    MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setSubject("Thông báo");
    helper.setText(body, false);

    mailSender.send(message);
}
```

Không nên làm:

```java
// Không giữ lại một MimeMessage mutable làm field của singleton service.
private MimeMessage currentMessage;

// Không dùng chung MimeMessageHelper trên nhiều thread.
private MimeMessageHelper sharedHelper;
```

### 7.1. Vì sao MimeMessage không phù hợp để chia sẻ?

`MimeMessage` chứa state mutable:
- `From`, `To`, `Cc`, `Bcc`;
- subject;
- content, multipart parts;
- headers;
- encoding metadata;
- attachment/inline references.

Nếu hai thread cùng sửa một message, thư có thể gửi sai recipient, body hoặc attachment. Đây là vấn đề correctness và bảo mật, không chỉ hiệu năng.

### 7.2. Retry cũng nên tạo message mới

Với retry:
- Giữ **application message key** để liên kết các attempts.
- Tạo **attempt ID mới** cho lượt thử.
- Tạo `MimeMessage` mới từ dữ liệu đã được lưu/đóng băng theo policy.
- Không tái sử dụng một message vừa bị transport mutate hoặc đang được thread khác dùng.

Nếu nội dung email liên quan giao dịch, hãy quyết định rõ dữ liệu render khi retry lấy snapshot ở thời điểm tạo event hay dữ liệu mới nhất. Việc đó ảnh hưởng tính nhất quán hơn nhiều so với chi phí khởi tạo `MimeMessage`.

### 7.3. Header và nội dung phải được thêm trong một lần build rõ ràng

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo(recipient);
helper.setSubject(subject);
helper.setText(plainText, htmlText);

message.setHeader(
    "X-Application-Message-Key",
    messageKey
);

mailSender.send(message);
```

Với inline resources, thường gọi `setText(...)` trước `addInline(...)`. Cấu trúc MIME được xây cho từng message; việc chia sẻ sender không thay đổi thứ tự này.

## 8. Gửi đồng thời: dùng chung sender bean khác dùng chung TCP socket

Một Spring singleton sender có thể được inject vào nhiều service hoặc background workers. Trong cách sử dụng bình thường, **mỗi lời gọi gửi sở hữu thông điệp riêng**, còn SMTP transport được sender/Jakarta Mail xử lý trong từng vòng gửi.

```text
Worker A --- MimeMessage A ---+
                              |
Worker B --- MimeMessage B ---+--> shared JavaMailSender bean
                              |        |
Worker C --- MimeMessage C ---+        +--> SMTP submission A
                                       +--> SMTP submission B
                                       +--> SMTP submission C
```

Không suy ra rằng:
- ba workers chắc chắn dùng cùng một socket;
- chỉ có một connection vì chỉ có một bean;
- tăng số threads đồng nghĩa throughput tăng tuyến tính;
- tạo một singleton sender tự động giới hạn concurrency.

### 8.1. Không dùng một Transport chung cho mọi thread

Nếu tự quản lý SMTP `Transport` cấp thấp, việc giữ một transport lâu dài có thể trông giống tối ưu connection pooling. Tuy nhiên, nó đưa vào nhiều vấn đề:
- trạng thái `connected/disconnected` thay đổi;
- server có thể đóng idle connection;
- nhiều thread có thể xen kẽ SMTP commands;
- lỗi một lượt gửi ảnh hưởng lượt khác;
- reconnect và TLS/AUTH phải được xử lý;
- shutdown phải đóng socket;
- dùng chung transport không có bảo đảm thread-safety chung.

Không tự tạo static `Transport` và chia sẻ tự do giữa các threads. Nếu thật sự cần một connection-management layer riêng, phải thiết kế rõ ownership, synchronization, health check, timeout, reconnect và test với server thực tế. Đó là một thành phần mới có chi phí bảo trì, **không phải tác dụng tự động của JavaMailSender**.

### 8.2. Một bean không phải connection pool

`JavaMailSenderImpl` là SMTP sender abstraction, không phải một thư viện generic connection pool với các tham số như `maxActive`, `maxIdle` và `borrowTimeout` được Spring Mail bảo đảm.

Nếu cần pooling, phải:
- xác nhận implementation cụ thể có hỗ trợ và contract của nó;
- hiểu giới hạn server/provider đối với concurrent connections;
- chứng minh qua benchmark rằng handshake/connect thực sự là bottleneck;
- có cơ chế phát hiện stale connection và reconnect;
- đảm bảo không gây interleaving của các SMTP transactions.

Trong nhiều ứng dụng, **bounded concurrency + queue + dùng chung sender config** đơn giản và an toàn hơn tự phát triển SMTP transport pool.

## 9. Batch send: một lời gọi chứa nhiều MIME messages

Spring `JavaMailSender` có các overload gửi một hoặc nhiều message.

```java
MimeMessage a = createMessageFor("a@example.net");
MimeMessage b = createMessageFor("b@example.net");
MimeMessage c = createMessageFor("c@example.net");

// Một lời gọi send có ba messages.
mailSender.send(a, b, c);
```

`createMessageFor(...)` là helper do ứng dụng định nghĩa, không phải API Spring.

### 9.1. Batch có thể giảm chi phí kết nối

Với những triển khai SMTP phổ biến của `JavaMailSenderImpl`, sender có thể tái sử dụng cùng `Transport` trong phạm vi một `send(MimeMessage...)`, giảm số lần:
- TCP connect;
- TLS handshake;
- SMTP EHLO;
- AUTH.

Tuy nhiên, mỗi message vẫn phải trải qua envelope và DATA riêng.

```text
Một transport connection
  |
  +--> MAIL FROM / RCPT TO / DATA for message A
  |
  +--> MAIL FROM / RCPT TO / DATA for message B
  |
  +--> MAIL FROM / RCPT TO / DATA for message C
  |
  +--> close
```

Việc có tái sử dụng được connection xuyên suốt batch hay không phụ thuộc transport connection có còn hoạt động và sender implementation xử lý lỗi thế nào.

### 9.2. Batch không phải một SMTP message có nhiều người nhận

Hai cách sau khác nhau:

**Ba MIME messages:**

```java
mailSender.send(messageA, messageB, messageC);
```

Mỗi message có nội dung/recipient/Message-ID riêng.

**Một MIME message gửi đến nhiều recipients:**

```java
helper.setTo(new String[] {
    "a@example.net",
    "b@example.net",
    "c@example.net"
});
mailSender.send(oneMessage);
```

Cách thứ hai là một message với nhiều recipients, dẫn tới vấn đề quyền riêng tư (người nhận thấy danh sách To/Cc) và partial recipient acceptance. Với email cá nhân hóa, thường cần tách từng recipient thành message riêng.

### 9.3. Không gom batch quá lớn

Một batch vài nghìn MIME messages có thể:
- giữ nhiều nội dung/attachment trong heap;
- kéo dài một lời gọi gửi, khó áp dụng timeout/worker lease;
- khó phân loại partial success và lưu kết quả từng item;
- gặp server disconnect hoặc rate limit giữa chừng;
- làm một request kiểm thử/production block quá lâu;
- gây backpressure sai tầng nếu batch chờ đủ số lượng mới gửi.

Không có **batch size tối ưu chung** cho mọi provider. Hãy chọn theo kích thước thư, độ trễ kết nối, throughput và khả năng quan sát trạng thái từng message.

### 9.4. Batch phù hợp khi nào?

Có thể cân nhắc nếu:
- nhiều message dùng **cùng SMTP profile**;
- nội dung có kích thước vừa phải;
- có thể quản lý partial failure;
- cần giảm chi phí connect/TLS/AUTH;
- provider không cấm hoặc giới hạn batch theo chính sách;
- queue worker vẫn lưu trạng thái bền vững từng message.

Không nhất thiết phù hợp khi:
- yêu cầu gửi khác tenant/credential;
- email rất lớn hoặc nhiều attachments;
- mỗi email có deadline rất khác nhau;
- cần retry/trace từng job mà batch API làm khó;
- provider đã có HTTP bulk API hoặc cơ chế batching riêng hiệu quả hơn.

## 10. Partial failure trong batch

Một lời gọi:

```java
mailSender.send(messageA, messageB, messageC);
```

không có nghĩa cả ba messages đều thành công hoặc đều thất bại cùng lúc.

Ví dụ:

```text
Message A -> SMTP_ACCEPTED
Message B -> SMTP_ACCEPTED
Message C -> rejected
```

Nếu worker chỉ catch một exception rồi retry **toàn bộ batch**, A và B có thể được gửi lần thứ hai.

### 10.1. Ghi kết quả theo từng message

Với mỗi email logic, nên có:
- message key;
- attempt ID;
- recipient reference;
- outcome;
- timestamp;
- provider/SMTP metadata nếu có.

`MailSendException` của Spring có thể cung cấp thông tin failed messages và nested exceptions trong một số đường gửi. Cách lấy successful/unsent recipients còn phụ thuộc Jakarta Mail và cấu hình transport. Không giả định rằng generic `MailException` luôn cung cấp đủ dữ liệu để phân tách mọi kết quả một cách chắc chắn.

### 10.2. UNKNOWN vẫn có thể xảy ra

Nếu kết nối bị mất **sau khi server có thể đã nhận DATA** nhưng trước khi application nhận response, kết quả một message có thể là `UNKNOWN`. Một batch bị ngắt giữa chừng đòi hỏi lưu trạng thái riêng cho các message đã chắc chắn accepted, chưa thử và chưa rõ kết quả.

Trong các hệ thống mà chính xác trạng thái từng email quan trọng hơn số handshake, gửi **một email mỗi outbox attempt** thường dễ quản lý hơn. Nếu tối ưu batching, phải có test failure injection và một chính sách reconciliation rõ ràng.

### 10.3. Đừng tạo exactly-once giả bằng message key

Custom header như:

```java
message.setHeader("X-Application-Message-Key", messageKey);
```

hỗ trợ trace, nhưng generic SMTP **không tự deduplicate** vì hai message có cùng header. Một timeout + retry vẫn có thể tạo email trùng. Muốn idempotency phía provider cần cơ chế API/provider thực sự hỗ trợ và phải tuân theo thời hạn/scope của họ.

## 11. Sizing concurrency và backpressure

Throughput của hệ thống không chỉ phụ thuộc số sender objects. Nó bị ảnh hưởng bởi:
- độ trễ TCP/TLS/AUTH;
- độ trễ SMTP commands và provider;
- kích thước MIME/attachment;
- băng thông network;
- số kết nối đồng thời provider cho phép;
- quota theo phút/giây/ngày;
- năng lực render/template và truy vấn database;
- số worker threads;
- chính sách retry và mail backlog.

Một mô hình trực giác:

```text
Số worker đang hoạt động
     ×
Số messages/giây của mỗi worker
     ≈
Tốc độ submission tối đa trước khi áp dụng giới hạn
```

Đây chỉ là phép ước lượng. Thực tế, nhiều worker có thể chờ network đồng thời; throughput sẽ đạt trần tại provider quota, CPU, network hoặc các tài nguyên khác.

### 11.1. Tăng thread không bảo đảm nhanh hơn

Ví dụ một provider cho phép số kết nối SMTP đồng thời thấp. Tăng worker từ 5 lên 100 có thể tạo:
- thêm TCP/TLS handshakes;
- `421`, `451` hoặc rate limit;
- timeouts;
- retry storm;
- CPU/heap/socket usage tăng;
- provider reputation hoặc quota bị ảnh hưởng.

Hãy **giới hạn concurrency** từ phía worker theo dữ liệu benchmark và quy định provider.

### 11.2. Bounded queue và bounded executor

Không nên đưa vô hạn message trực tiếp vào một `ExecutorService` unbounded rồi hy vọng SMTP sẽ theo kịp. Nên có:
- durable outbox/queue;
- số concurrent senders giới hạn;
- rate limiter nếu provider giới hạn tốc độ;
- queue backlog monitoring;
- retry schedule và max attempts;
- chính sách drop/dead-letter hoặc cảnh báo khi backlog vượt SLA.

```text
Business events
      |
      v
Durable outbox
      |
      v
Due-job dispatcher
      |
      v
Bounded worker concurrency
      |
      v
JavaMailSender
      |
      v
SMTP provider (quota + rate limit)
```

### 11.3. Rate limit và concurrency là hai khái niệm khác nhau

- **Concurrency limit:** tối đa bao nhiêu sends đang xử lý cùng lúc.
- **Rate limit:** tối đa bao nhiêu submissions trong một khoảng thời gian.
- **Retry budget:** một email được thử lại bao nhiêu lần và trong bao lâu.

Có thể đáp ứng concurrency nhưng vẫn vi phạm rate limit nếu mỗi send kết thúc nhanh. Cần phối hợp cả ba.

### 11.4. Tránh retry storm

Nếu provider lỗi 2 phút, hàng nghìn jobs có thể cùng tới hạn retry. Không nên để chúng cùng tạo kết nối ở giây đầu tiên provider phục hồi.

Dùng:
- exponential backoff;
- jitter;
- concurrency limit;
- rate limiting;
- circuit breaker;
- dead-letter sau khi hết ngân sách hoặc lỗi vĩnh viễn;
- phân biệt kết quả `UNKNOWN` không được retry mù.

## 12. Những timeout cần hiểu đúng

Ba property phổ biến:

| Property | Mục đích | Rủi ro nếu quá thấp | Rủi ro nếu không hợp lý |
|---|---|---|---|
| `mail.smtp.connectiontimeout` | Thời gian chờ kết nối socket | False failure khi network chậm | Worker treo lúc connect; backlog tăng |
| `mail.smtp.timeout` | Thời gian chờ đọc socket | Timeout khi relay phản hồi chậm | Worker đợi dài khi server ngừng phản hồi |
| `mail.smtp.writetimeout` | Thời gian chờ ghi socket | Fail khi truyền message/attachment lớn | Write stall làm giữ tài nguyên |

Các giá trị dùng đơn vị mili giây theo Jakarta Mail SMTP implementation. Chi tiết triển khai write timeout có thể có chi phí thread/timer/socket phụ trợ theo library/version; khi concurrency rất lớn, cần benchmark thay vì coi nó miễn phí.

### 12.1. Timeout không phải tổng deadline của email

Ba socket timeouts không nhất thiết giới hạn **tổng thời gian** xây MIME + DNS + nhiều SMTP commands + retry + callback. Một request có thể trải qua nhiều giai đoạn nối tiếp, mỗi giai đoạn có timeout riêng.

Nếu SLA yêu cầu xử lý trong 30 giây, cần deadline ở tầng orchestration, worker claim/lease và chính sách retry ngoài các socket timeouts.

### 12.2. Lease timeout phải phù hợp với network behavior

Ví dụ:
- socket read timeout: 30 giây;
- worker lease: 10 giây;
- worker không renew lease;
- SMTP relay phản hồi sau 20 giây.

Worker thứ hai có thể reclaim job trước khi worker thứ nhất gửi xong. Đây là nguy cơ duplicate submission.

Giải pháp có thể gồm:
- lease dài hơn giới hạn gửi hợp lý;
- heartbeat/lease renewal có kiểm soát;
- fencing token khi ghi DB outcome;
- trạng thái `UNKNOWN` khi mất quyền sở hữu và không rõ kết quả;
- provider idempotency nếu có.

**Fencing token chỉ bảo vệ cập nhật database**, không thể thu hồi email đã được upstream accepted.

### 12.3. Timeout và SMTP accepted không đồng nghĩa

Nếu timeout sau khi application đã gửi hết DATA nhưng chưa nhận được response, không thể khẳng định relay chưa nhận thư. Cần ghi attempt `UNKNOWN` và reconciliation theo provider log/webhook, đặc biệt trước khi tự động retry.

Đây là ranh giới giữa **tối ưu hiệu năng** và **tính đúng đắn của side effect**.

## 13. Cấu hình kết nối nhiều SMTP profiles

Một sản phẩm có thể có:
- email giao dịch qua relay A;
- email marketing qua relay B;
- email cảnh báo nội bộ qua relay C.

Mỗi profile khác nhau về:
- host/port/TLS mode;
- sender identity;
- username/secret;
- quota/concurrency;
- envelope sender và DKIM/domain authentication;
- timeout/retry rules;
- logging/monitoring.

Không nên **mutate một sender singleton** trước mỗi lượt gửi để chuyển từ A sang B.

### 13.1. Hai bean riêng có qualifier

Ví dụ cấu hình theo profile:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MultipleMailSenderConfig {

    @Bean("transactionalSender")
    JavaMailSender transactionalSender(
            TransactionalMailProperties config) {
        return MailSenderFactory.create(config);
    }

    @Bean("marketingSender")
    JavaMailSender marketingSender(
            MarketingMailProperties config) {
        return MailSenderFactory.create(config);
    }
}
```

`TransactionalMailProperties`, `MarketingMailProperties` và `MailSenderFactory` là lớp do ứng dụng định nghĩa để áp dụng cấu hình; không phải API có sẵn của Spring Mail. Factory phải tạo sender có TLS/timeout/credential theo từng profile.

Inject rõ ràng:

```java
@Service
public class TransactionalEmailService {

    private final JavaMailSender sender;

    public TransactionalEmailService(
        @Qualifier("transactionalSender")
        JavaMailSender sender) {
        this.sender = sender;
    }
}
```

Nếu nhiều bean `JavaMailSender` cùng tồn tại, cần `@Qualifier` hoặc một quy ước chọn rõ ràng; đừng để wiring vô tình chọn provider khác.

### 13.2. Profile cho từng tenant

Trong hệ thống multi-tenant:
- chỉ cho phép sender profiles đã được cấu hình/xác minh;
- cách ly secret và domain identity;
- không cho tenant tùy ý chỉ định SMTP host/port từ request;
- hạn chế SSRF/credential exfiltration;
- rate limit riêng theo tenant/provider;
- không cho một tenant dùng From domain chưa được xác thực;
- tránh unbounded cache các sender theo tenant không có eviction/lifecycle policy.

Một số trường hợp có hàng nghìn tenants, mỗi tenant một sender bean tĩnh có thể không phù hợp. Khi đó cần một profile registry/credential resolver có kiểm soát, sender pool/cache với giới hạn rõ ràng hoặc chuyển qua provider API hỗ trợ tenant delegation. **Không đánh đổi isolation bằng cách sửa một singleton đang được nhiều request sử dụng**.

### 13.3. Secret rotation

Khi SMTP credential đổi:
1. Cấp secret mới trong secret manager.
2. Xác nhận cấu hình mới hợp lệ với provider.
3. Triển khai sender/profile mới hoặc refresh theo cơ chế được thiết kế an toàn.
4. Chuyển traffic có kiểm soát.
5. Thu hồi secret cũ sau khi đảm bảo workers cũ không còn cần nó.

Nếu thread A đang gửi bằng sender cũ, không sửa password field của sender giữa handshake/AUTH. Việc thay đổi credential trong lúc active có thể gây lỗi khó tái hiện; nên định nghĩa ownership và lifecycle của sender instance.

## 14. Cấu hình connection và security phải đi cùng nhau

Tối ưu hiệu năng không được bỏ qua:
- STARTTLS required trên endpoint yêu cầu STARTTLS.
- Implicit TLS đúng cổng.
- Hostname verification.
- Truststore/CA hợp lệ.
- Authentication mode theo provider.
- Bảo vệ và rotation secrets.
- Giới hạn From/envelope sender theo domain được phép.
- Không log AUTH commands, password hoặc raw MIME chứa dữ liệu nhạy cảm.

### 14.1. Ví dụ một cấu hình sai

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    properties:
      mail:
        smtp:
          starttls:
            enable: true
          ssl:
            trust: "*"
```

`trust=*` là một lựa chọn không nên dùng để bỏ qua trust chain; thiếu `starttls.required` có thể cho phép fallback không TLS tùy server/transport behavior. Không xem những cách này là tối ưu “giảm lỗi gửi”.

### 14.2. SMTP AUTH khác với domain authentication

Đăng nhập SMTP thành công không chứng minh email đã pass SPF/DKIM/DMARC tại receiver. Những cơ chế này phụ thuộc DNS, envelope sender, DKIM signing và From domain. Tái sử dụng sender bean không làm thay đổi các yêu cầu domain authentication đó.

### 14.3. Kết nối gần server không đồng nghĩa được bỏ TLS

Một SMTP relay nội bộ cùng VPC có thể có chính sách transport riêng, nhưng không nên mặc định nội bộ là an toàn hoặc bỏ xác thực danh tính server. Hãy tuân theo chính sách hạ tầng, chứng chỉ và kiểm soát egress của tổ chức.

## 15. Thiết kế service gửi email hiệu quả và dễ test

Một service tập trung vào **dựng message mới** rồi gọi một sender đã được inject:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReceiptMailer {

    private final JavaMailSender mailSender;

    public ReceiptMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            String orderId,
            String plainText,
            String htmlText) throws MessagingException {

        MimeMessage message =
            mailSender.createMimeMessage();

        MimeMessageHelper helper =
            new MimeMessageHelper(
                message, true, "UTF-8"
            );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject(
            "Xác nhận đơn hàng " + orderId
        );
        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }
}
```

Đặc điểm:
- `JavaMailSender` là dependency shareable đã cấu hình.
- Mỗi lần gọi tạo `MimeMessage` mới.
- Nội dung dùng charset rõ ràng.
- SMTP connection lifecycle do sender/transport quản lý.
- Service không lưu recipient/subject vào field mutable chung.
- Có thể thay sender bằng mock trong unit test.

### 15.1. Không gửi SMTP trực tiếp trong transaction nghiệp vụ dài

Nếu gọi SMTP bên trong transaction cập nhật đơn hàng, một network call chậm có thể giữ database locks lâu. Nếu SMTP accepted rồi transaction bị rollback, email vẫn đã ra ngoài nhưng dữ liệu nghiệp vụ chưa commit.

Với email quan trọng:
- commit business event + outbox item trong cùng database transaction;
- worker gửi sau commit;
- lưu attempts và outcome ở transaction ngắn;
- điều chỉnh concurrency/timeout ở tầng worker.

### 15.2. Không tự đánh dấu delivered sau send

`mailSender.send(message)` không ném exception chỉ cho biết hành động submission hoàn tất theo interface/transport; không chứng minh recipient đã nhìn thấy thư. Dùng `SMTP_ACCEPTED` hoặc trạng thái tương đương, và dùng provider event để theo dõi delivery nếu có.

## 16. Outbox worker và hạn chế số lượng send đồng thời

Một kiến trúc:

```text
OrderService / BillingService
            |
            v
       Database outbox
            |
            v
       Due-job dispatcher
            |
            v
       Bounded worker slots
            |
            v
       ReceiptMailer
            |
            v
       Shared JavaMailSender
            |
            v
       SMTP relay
```

Worker nên:
1. Atomic claim một job đến hạn với lease/fencing.
2. Dựng MIME message mới.
3. Gửi qua sender đã được inject.
4. Ghi `SMTP_ACCEPTED` khi transport báo thành công.
5. Phân loại lỗi tạm thời/vĩnh viễn/unknown.
6. Retry có backoff/jitter và max attempts.
7. Chuyển dead letter hoặc reconciliation khi cần.

Một sender dùng chung **không thay thế** giới hạn số worker. Giới hạn này cần nằm ở executor/dispatcher, queue consumer concurrency hoặc rate limiter.

### 16.1. Ví dụ giới hạn với Semaphore

Một tầng điều phối có thể dùng semaphore để giới hạn số send đang chạy:

```java
import java.util.concurrent.Semaphore;

import org.springframework.mail.javamail.JavaMailSender;

public final class BoundedMailSubmission {

    private final JavaMailSender sender;
    private final Semaphore slots;

    public BoundedMailSubmission(
            JavaMailSender sender,
            int maxConcurrentSends) {

        if (maxConcurrentSends < 1) {
            throw new IllegalArgumentException(
                "maxConcurrentSends must be positive"
            );
        }

        this.sender = sender;
        this.slots = new Semaphore(maxConcurrentSends);
    }

    public void send(MimeMessage message)
            throws InterruptedException {

        slots.acquire();
        try {
            sender.send(message);
        } finally {
            slots.release();
        }
    }
}
```

Với code trên, cần import `jakarta.mail.internet.MimeMessage`. Nếu thread bị interrupt khi chờ slot, tầng caller nên bảo toàn interrupt status hoặc có handling phù hợp để không làm mất job.

Ví dụ này minh họa **giới hạn concurrency trong một process**. Khi có nhiều instances/pods, mỗi instance có semaphore riêng nên tổng concurrency vẫn tăng theo số replicas. Nếu provider có limit toàn account, cần **distributed rate/concurrency control** hoặc chia quota rõ ràng giữa instances.

### 16.2. Không chỉ block vô hạn

`Semaphore.acquire()` có thể chờ vô hạn nếu hàng đợi hoặc hệ thống đã quá tải. Với API đồng bộ, nên có bounded wait hoặc trả trạng thái accepted-to-queue; với worker, nên giới hạn worker count ngay từ dispatcher.

Đừng khởi tạo vô hạn threads chỉ để chờ semaphore. Hãy hạn chế từ upstream và dùng durable queue.

## 17. Tính đúng đắn khi nhiều workers dùng chung sender

Tái sử dụng bean thường an toàn hơn nếu:
- sender được cấu hình trước khi chạy và không mutate config lúc gửi;
- mọi request tạo `MimeMessage` và helper mới;
- template renderer không lưu nội dung mutable chung;
- attachment resources có lifecycle đúng;
- exception/error handling tách theo từng attempt;
- rate/queue limits được áp dụng ngoài sender;
- không dùng chung SMTP `Transport` thủ công;
- callback/sender profiles không bị đổi giữa các tenants.

### 17.1. Đồng bộ hóa toàn bộ send có phải giải pháp?

Có thể thấy:

```java
synchronized (mailSender) {
    mailSender.send(message);
}
```

Đồng bộ hóa như vậy **ép mọi lời gọi đi tuần tự trong cùng process**, có thể làm throughput rất thấp. Nó cũng không tự giải quyết timeout, provider quota, retry hay multi-instance concurrency.

Chỉ serialize sends nếu có yêu cầu cụ thể của transport/thiết kế đã được xác minh. Với bình thường, giới hạn concurrency có cấu trúc rõ ràng sẽ linh hoạt hơn việc khóa cả sender.

### 17.2. Một JavaMailSender cho nhiều services không phải một message chung

Đúng:

```text
BillingService -----+
AccountService -----+--> same JavaMailSender bean
AlertService -------+       |
                            +--> independent MimeMessages
```

Sai:

```text
BillingService -----+
AccountService -----+--> same static MimeMessage
AlertService -------+       |
                            +--> fields overwritten concurrently
```

## 18. Attachment, inline resources và chi phí bộ nhớ

Khi sender được dùng cho email có file đính kèm, các rủi ro hiệu năng có thể nằm ở **dữ liệu MIME**, không phải sender bean.

Ví dụ:
- 100 emails đồng thời, mỗi email đính kèm 20 MiB.
- Nếu ứng dụng giữ byte arrays trong heap, bộ nhớ dành cho attachment có thể rất lớn, chưa kể MIME serialization buffers và overhead.
- Base64 transfer encoding thường làm wire payload tăng khoảng một phần ba trước khi tính line wrapping và MIME overhead.
- Bandwidth và write timeout có thể trở thành bottleneck.

### 18.1. Chọn nguồn attachment có thể đọc lại

`MimeMessageHelper.addAttachment(...)` thường nhận `InputStreamSource` hoặc `File` tùy overload. Nếu nội dung được dùng trong quá trình MIME serialization, stream có thể cần mở lại.

Với dữ liệu nhỏ:

```java
byte[] bytes = createCsvBytes();

helper.addAttachment(
    "report.csv",
    new ByteArrayResource(bytes),
    "text/csv; charset=UTF-8"
);
```

`ByteArrayResource` phù hợp khi bytes đã nằm trong bộ nhớ và có thể tạo InputStream mới. Nhưng với attachments lớn, việc giữ hàng trăm `byte[]` có thể tốn heap; nên cân nhắc file/object storage references và cơ chế stream có thể mở lại, quyền truy cập và cleanup rõ ràng.

### 18.2. Không chia sẻ mutable attachment stream

Không nên giữ một `InputStream` dùng một lần trong singleton service rồi gắn cho nhiều email. Nếu nhiều sends cùng đọc một stream, nội dung có thể bị cắt, lỗi I/O hoặc không thể serialize lại khi retry.

Chọn resource có khả năng tạo stream mới cho mỗi lần dùng; kiểm tra thời hạn tồn tại của tệp hoặc object trong storage trong suốt thời gian send/retry.

### 18.3. Template caching khác sender caching

Có thể cache các template đã compile nếu template engine hỗ trợ và tương thích với concurrency, nhưng **không cache kết quả MIME có chứa thông tin cá nhân** để tái sử dụng cho nhiều recipients. Tách:
- template definition/cache;
- per-message render data;
- per-message MIME object;
- SMTP configuration bean.

## 19. Quan sát hiệu năng trước khi tối ưu

Không đo lường thì rất dễ tối ưu sai điểm nghẽn.

Các giai đoạn nên đo riêng:

```text
enqueue time
   |
   v
queue wait
   |
   v
worker claim
   |
   v
render template
   |
   v
build MIME / attachment access
   |
   v
SMTP connect + TLS + AUTH
   |
   v
SMTP envelope + DATA
   |
   v
persist submission outcome
   |
   v
provider delivery events (nếu có)
```

Một số metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `mail_outbox_backlog` | Bao nhiêu email logic đang chờ xử lý |
| `mail_queue_wait_seconds` | Độ trễ từ enqueue tới worker claim |
| `mail_render_duration_seconds` | Thời gian render template/content |
| `mail_mime_build_duration_seconds` | Thời gian dựng MIME/attachment |
| `mail_smtp_submit_duration_seconds` | Thời gian sender gửi một submission |
| `mail_smtp_connect_failures_total` | Số lỗi kết nối |
| `mail_smtp_timeouts_total` | Số timeout theo nhóm |
| `mail_smtp_auth_failures_total` | Số lỗi credential/auth |
| `mail_smtp_attempts_total` | Số attempts, phân loại outcome |
| `mail_retry_wait_count` | Số job chờ retry |
| `mail_dead_letter_count` | Số job dừng tự động |
| `mail_unknown_outcome_count` | Job cần reconciliation |
| `mail_attachment_bytes` | Phân bố kích thước attachments |
| `mail_active_sends` | Số SMTP submissions đang chạy |

### 19.1. Phân biệt độ trễ từ API và độ trễ delivery

Nếu API chỉ ghi outbox rồi trả `202 Accepted`, HTTP latency có thể thấp dù SMTP provider chậm. Do đó đo:
- thời gian API commit outbox;
- thời gian chờ queue;
- thời gian SMTP accepted;
- thời gian provider delivered/bounced nếu có.

Không coi HTTP response thành công là email đã gửi xong hoặc đã vào Inbox.

### 19.2. Đừng log raw MIME để đo hiệu năng

Structured log có thể chứa:

```json
{
  "event": "mail.smtp_submission",
  "messageKey": "msg-8c21",
  "attemptId": "att-2",
  "profile": "transactional",
  "outcome": "SMTP_ACCEPTED",
  "durationMs": 842,
  "attachmentCount": 1
}
```

Không log:
- SMTP username/password;
- bearer tokens/app passwords;
- full email body, attachment bytes/Base64;
- reset/verification token;
- thông tin cá nhân không cần thiết.

Các trường message key/attempt ID giúp trace mà không cần thu thập nội dung thư.

## 20. Benchmark đúng câu hỏi

Một benchmark hữu ích so sánh các phương án trong cùng điều kiện:
- Một sender bean vs tạo sender mới mỗi lần.
- Gửi một message mỗi `send` vs `send(MimeMessage...)` nhỏ.
- Worker concurrency 1, 4, 8, 16 với cùng provider test.
- Attachments nhỏ vs lớn.
- STARTTLS vs implicit TLS nếu provider hỗ trợ cả hai trên endpoints phù hợp.
- Kết nối gần vs xa mạng ứng dụng.
- Thực hiện trên test server/proxy được kiểm soát thay vì bắn tải bất ngờ vào provider production.

### 20.1. Kiểm soát các yếu tố khi benchmark

Giữ cố định:
- loại MIME và kích thước thư;
- SMTP host/port;
- TLS/AUTH;
- network path;
- JDK, Spring Mail/Jakarta Mail versions;
- số lượng messages;
- warmup;
- rate/provider quotas;
- memory/CPU limits;
- điều kiện lỗi và retry.

Phân biệt:
- throughput submissions/giây;
- p50/p95/p99 latency;
- số connections/TLS handshakes;
- CPU, heap và GC;
- số SMTP 4xx/5xx;
- network bytes và bytes gửi mỗi message.

Không suy diễn rằng một kết quả đo tại localhost đồng nghĩa sẽ nhanh hơn tương ứng trên đường mạng provider thật.

### 20.2. Khi nào batch thực sự có ích?

Nếu phần lớn thời gian nằm ở connect/TLS/AUTH, batch nhỏ có thể có lợi. Nếu phần lớn thời gian là upload nhiều attachments hoặc provider rate limit, giảm số connect có thể ít tác dụng.

Cần đánh giá thêm rủi ro partial failure và tính đúng đắn của outbox. Đôi khi tăng độ phức tạp để tiết kiệm một vài handshake không đáng đổi lấy khó khăn quản lý retry.

## 21. Kiểm thử JavaMailSender reuse không cần SMTP thật

Unit test có thể xác minh service **dùng sender đã được inject** và tạo message mới cho mỗi yêu cầu.

Ví dụ dùng Mockito:

```java
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import org.mockito.ArgumentCaptor;

import java.util.Properties;

class ReceiptMailerTest {

    @Test
    void buildsSeparateMessagesUsingInjectedSender()
            throws Exception {

        JavaMailSender sender = mock(JavaMailSender.class);

        MimeMessage first = new MimeMessage(
            Session.getInstance(new Properties())
        );
        MimeMessage second = new MimeMessage(
            Session.getInstance(new Properties())
        );

        when(sender.createMimeMessage())
            .thenReturn(first, second);

        ReceiptMailer service = new ReceiptMailer(sender);

        service.send(
            "a@example.net", "ORD-A",
            "Nội dung A", "<p>Nội dung A</p>"
        );

        service.send(
            "b@example.net", "ORD-B",
            "Nội dung B", "<p>Nội dung B</p>"
        );

        ArgumentCaptor<MimeMessage> captured =
            ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender, times(2))
            .send(captured.capture());

        assertThat(captured.getAllValues())
            .containsExactly(first, second);

        assertThat(first).isNotSameAs(second);
    }
}
```

Bài test này:
- không cần SMTP server;
- kiểm tra mỗi lời gọi tạo message riêng;
- không chứng minh TCP reuse hoặc số TLS handshakes;
- không nên được gọi là connection-performance benchmark.

### 21.1. Test nội dung mà không gửi thật

Có thể gọi `saveChanges()` trên message đã capture rồi đọc `getSubject()`, recipients và duyệt MIME parts để kiểm tra plain/HTML/attachment.

Nếu mục tiêu là kiểm thử nội dung, dùng `MimeMessage` in-memory thật thay vì mock cả MIME object. Nhưng điều đó vẫn là test tại ranh giới I/O, chưa kiểm chứng SMTP transport.

## 22. Integration test với SMTP sandbox

Để kiểm tra thực tế:
- host/port config;
- TLS mode;
- connection/handshake;
- SMTP AUTH;
- thời gian gửi;
- batch behavior;
- lỗi khi server đóng connection;
- partial failure

cần một SMTP test server hoặc provider sandbox.

### 22.1. GreenMail/Mailpit dùng để làm gì?

Một SMTP sandbox có thể nhận MIME message mà không chuyển tới recipient Internet. Tùy tool, có thể quan sát:
- số message đã nhận;
- headers;
- body;
- recipient;
- timestamps;
- SMTP commands và kết nối trong mức độ tool hỗ trợ.

GreenMail hoặc Mailpit có ích cho happy-path integration. Không phải server nào cũng hỗ trợ trả lỗi tùy chỉnh ở từng SMTP phase; cần fault-injecting SMTP relay riêng khi muốn test reconnect, 421/451/550 hoặc disconnect sau DATA.

### 22.2. Cấu hình sender test riêng

```java
JavaMailSenderImpl sender = new JavaMailSenderImpl();

sender.setHost("127.0.0.1");
sender.setPort(testSmtpPort);
sender.getJavaMailProperties().put(
    "mail.smtp.connectiontimeout", "3000"
);
sender.getJavaMailProperties().put(
    "mail.smtp.timeout", "3000"
);
```

`testSmtpPort` là port do test server cung cấp. Môi trường test có thể không dùng TLS/AUTH để kiểm tra MIME submission đơn giản, nhưng phải có bộ integration test khác mô phỏng **đúng TLS mode và certificate verification** nếu chúng là yêu cầu production.

### 22.3. Điều gì cần xác minh về connection reuse?

Test có thể ghi nhận số TCP connections/SMTP sessions trên server thử nghiệm khi:
1. Gửi hai messages bằng hai lời gọi `send` riêng.
2. Gửi cùng hai messages bằng một lời gọi `send(first, second)`.
3. Gửi đồng thời nhiều messages từ một singleton sender.
4. Buộc server đóng connection giữa batch.
5. Cho server delay reply để kiểm tra timeout và worker lease.

Đừng hardcode giả định "cứ dùng singleton là đúng một connection". Hãy đo đúng implementation, library versions và provider configuration mà dự án dự định dùng.

### 22.4. Phân biệt test transport với test database workflow

- SMTP test xác minh kết nối và server thấy message.
- Outbox integration test xác minh trạng thái, transaction, retries, concurrency và dead-letter.
- End-to-end provider test xác minh delivery/webhooks/domain authentication nếu cần.

Không dùng một test gửi tới localhost rồi suy ra hệ thống production có exactly-once email delivery.

## 23. Sự cố thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Mỗi email có một SMTP connection mới dù sender singleton | `send` quản lý `Transport` theo lượt gọi | Đo connection lifecycle; cân nhắc batch nhỏ nếu phù hợp. |
| Không tăng throughput dù tăng số workers | Provider quota/rate, network, attachments hoặc DB bottleneck | Đo p95 latency và quota, đặt concurrency hợp lý. |
| Dùng chung sender nhưng gửi sai SMTP account | Runtime thay username/host trên singleton | Tách immutable sender profiles; không mutate shared config. |
| Gửi sai recipient khi chạy đa thread | Chia sẻ `MimeMessage`/helper mutable | Tạo MIME message mới cho từng email. |
| Memory tăng mạnh khi gửi nhiều attachments | Byte arrays/MIME parts được giữ cùng lúc | Bounded concurrency, nguồn stream có thể đọc lại, giới hạn kích thước. |
| Worker timeout khi provider chậm | Socket timeout không phù hợp hoặc provider outage | Điều chỉnh theo SLA, backoff và circuit breaker. |
| Duplicate email sau timeout | SMTP có thể accepted nhưng app không nhận response | Ghi `UNKNOWN`; reconcile trước retry. |
| Batch bị lỗi giữa chừng | Partial success, không có per-message outcome | Lưu kết quả từng message; không retry toàn batch mù. |
| TLS handshake thất bại trên port 587 | Dùng implicit TLS hoặc cert/chain sai | STARTTLS đúng mode, hostname verification, truststore. |
| STARTTLS không được hỗ trợ | Sai host/port hoặc relay/proxy | Xác minh provider capabilities, fail closed. |
| Lỗi tăng sau secret rotation | Threads đang dùng cấu hình cũ/mới xen kẽ | Thay sender/profile có kiểm soát, không mutate bean sống. |
| Tưởng Session là socket pool | Nhầm JavaMail Session với TCP connection | Phân biệt cấu hình và network transport. |
| Quá nhiều SMTP connections | Worker concurrency vượt provider limits | Bounded worker pool, rate limit và backpressure. |
| Queue backlog tăng khi server lỗi | Retry dồn dập hoặc không có circuit breaker | Backoff + jitter, quota, dead-letter/alert. |
| Unit test yêu cầu SMTP thật | Service tự tạo `JavaMailSenderImpl` | Constructor injection và mock `JavaMailSender`. |
| Gửi nhanh hơn nhưng mất lịch sử retry | Batch send không liên kết từng outbox row | Ghi attempt/outcome per-message và audit. |

## 24. Checklist thiết kế và vận hành

### 24.1. Thiết kế sender

- [ ] Một sender bean được cấu hình ổn định cho mỗi SMTP profile.
- [ ] Service phụ thuộc vào `JavaMailSender` interface.
- [ ] Không tạo `JavaMailSenderImpl` trong mỗi business method.
- [ ] Không mutate host/credentials/properties của singleton lúc có concurrent sends.
- [ ] Không giữ `MimeMessage` hoặc `MimeMessageHelper` làm shared state.
- [ ] Không chia sẻ `Transport` thủ công khi chưa có thiết kế ownership/thread-safety.
- [ ] Các sender profiles được phân biệt bằng qualifier hoặc registry có kiểm soát.

### 24.2. Connection/security

- [ ] Host/port theo provider.
- [ ] STARTTLS required hoặc implicit TLS đúng mode.
- [ ] TLS certificate chain và hostname verification.
- [ ] Credential từ secret manager/env được bảo vệ.
- [ ] Timeout connect/read/write được cấu hình rõ.
- [ ] Lease/worker deadline tương thích với timeout.
- [ ] Có quy trình rotation credential và certificate.
- [ ] Không dùng trust-all hoặc plaintext fallback để “tăng throughput”.

### 24.3. Hiệu năng

- [ ] Đo thời gian render MIME và SMTP submission riêng.
- [ ] Có giới hạn concurrent senders và provider rate.
- [ ] Queue/outbox durable, có backlog metrics.
- [ ] Retry có backoff/jitter, budget và dead-letter.
- [ ] Có trạng thái `UNKNOWN` cho submission outcome không rõ.
- [ ] Không tạo unbounded thread pool hoặc queue trong bộ nhớ.
- [ ] Batch size được đo và xử lý partial failure.
- [ ] Attachment sizes và memory được giới hạn.
- [ ] Log có message key/attempt ID, không lộ nội dung thư.

### 24.4. Kiểm thử

- [ ] Unit test inject mock `JavaMailSender`.
- [ ] MIME object được tạo mới cho mỗi message.
- [ ] Integration test với SMTP sandbox kiểm tra cấu hình gửi.
- [ ] Transport test kiểm tra connection count và reconnect behavior nếu cần.
- [ ] Outbox test kiểm tra retry, lease, idempotency và dead-letter.
- [ ] Test concurrency không làm gửi nhầm tenant/provider.
- [ ] Test khi provider đóng connection giữa batch.
- [ ] Test large attachments và write timeout.
- [ ] Test secret rotation/cấu hình mới không xen lẫn tài khoản.
- [ ] Test không gửi thư thật ngoài ý muốn.

## 25. Bài tập thực hành

### Bài 1 — Refactor sender lifecycle

Một service đang tạo `new JavaMailSenderImpl()` trong mỗi method. Hãy chuyển sang constructor injection của một `JavaMailSender` bean cấu hình tập trung. Nêu lợi ích về test và consistency.

### Bài 2 — Session khác connection

Vẽ sơ đồ vòng đời khi một singleton sender gửi hai messages bằng **hai** lời gọi `send`. Giải thích vì sao cùng JavaMail `Session` không có nghĩa cùng TCP socket.

### Bài 3 — STARTTLS configuration

Viết `application.yml` cho port 587 với `starttls.enable`, `starttls.required`, `ssl.checkserveridentity` và ba timeout. Không hardcode secret.

### Bài 4 — Implicit TLS

Chuyển cấu hình sang port 465 khi provider yêu cầu implicit TLS. Nêu khác biệt với STARTTLS.

### Bài 5 — Thread-safety của MIME

Hai worker cùng gửi email cá nhân hóa. Thiết kế cách dùng chung sender nhưng tạo `MimeMessage`/helper riêng; minh họa lỗi nếu dùng một shared MimeMessage.

### Bài 6 — Benchmark batch

Dùng SMTP test server đo thời gian và số TCP connections khi gửi 50 messages bằng 50 lời gọi riêng, sau đó chia thành 10 batches × 5 messages. Giữ nguyên kích thước thư và cấu hình; so sánh throughput/p95 latency.

### Bài 7 — Partial failure

Một batch có 3 messages, 2 accepted và 1 failed. Thiết kế cách ghi outcome cho từng message key mà không retry lại các message đã accepted.

### Bài 8 — Bounded concurrency

Provider chỉ chấp nhận một số connections đồng thời. Thiết kế worker pool và rate limiter, giải thích khác biệt giữa concurrency limit và rate limit.

### Bài 9 — Multi-tenant sender

Hai tenants dùng SMTP accounts khác nhau. Viết thiết kế sender registry/profiles không mutate singleton config giữa các thread và không gửi nhầm From/recipient.

### Bài 10 — Secret rotation

Mô phỏng credential đổi khi worker vẫn đang gửi. Đề xuất cách thay sender/profile có kiểm soát thay vì sửa password của bean được dùng chung.

### Bài 11 — Timeout và lease

Socket timeout 30 giây nhưng worker lease 10 giây. Phân tích nguy cơ hai workers cùng gửi và đề xuất điều chỉnh lease/heartbeat/fencing/reconciliation.

### Bài 12 — Attachment memory

Có 100 emails đồng thời, mỗi attachment 20 MiB. Đánh giá khả năng heap tăng, Base64 overhead và lựa chọn nguồn attachment có thể đọc lại.

### Bài 13 — Retry sau timeout

SMTP relay có thể đã nhận message nhưng app mất response. Thiết kế `UNKNOWN`, attempt history và đối soát trước khi retry.

### Bài 14 — Unit test sender reuse

Mock `JavaMailSender`, stub hai `createMimeMessage()` trả hai instances, gọi service hai lần và assert send được gọi với hai đối tượng khác nhau.

### Bài 15 — Transport integration

Dùng GreenMail hoặc SMTP test relay để kiểm tra STARTTLS/implicit TLS trong trường hợp được hỗ trợ, kết nối bị đóng giữa batch và server trả `421`. Không dùng provider production để tạo lỗi hàng loạt.

### Bài 16 — Tìm bottleneck

Cho các metric: queue wait cao, MIME render thấp, SMTP submit p95 cao, provider 4xx tăng. Hãy đề xuất một kế hoạch điều tra trước khi tăng số worker threads.

### Bài 17 — Event-driven outbox

Thiết kế job gửi email có message key, attempt ID, SMTP_ACCEPTED/UNKNOWN, backoff và dead letter. Giải thích vì sao sender singleton không tự cung cấp exactly-once behavior.

### Bài 18 — Quyền riêng tư và performance logs

Viết một structured log cho SMTP submission gồm message key, profile, duration, outcome, attachment size; không chứa recipient đầy đủ, password, token hoặc MIME body.

## 26. Tổng kết

**Tái sử dụng JavaMailSender và connection configuration** nghĩa là dùng một **sender bean ổn định, do Spring quản lý** cho cùng SMTP profile, thay vì liên tục dựng lại hạ tầng cấu hình trong business code. Sender bean có thể được inject vào nhiều services/workers; mỗi email vẫn phải có **MimeMessage và MimeMessageHelper riêng**.

Cần nhớ những ranh giới quan trọng:

1. **Reuse sender ≠ reuse SMTP TCP connection.** Jakarta Mail `Session` là cấu hình/context, không phải socket pool.
2. Một lời gọi `send(MimeMessage...)` có thể tận dụng kết nối trong cùng batch, nhưng phải xử lý **partial failures** và không được retry toàn batch mù quáng.
3. Cấu hình **host, port, TLS, hostname verification, credential và timeout** tập trung, thống nhất; không mutate singleton khi nhiều thread đang gửi.
4. **Concurrency limit, rate limit và retry budget** phải được thiết kế ở worker/queue, không trông chờ sender bean tự giới hạn.
5. Với nhiều SMTP accounts/tenants, dùng **profiles riêng hoặc registry có isolation**, không đổi username/password của một shared instance theo từng request.
6. Tối ưu dựa trên **benchmark thực tế**: đo queue wait, MIME build, connect/TLS/AUTH, SMTP submit, attachments và provider limits.
7. Giữ correctness: **outbox, attempt history, idempotency, UNKNOWN reconciliation và dead-letter** để không gửi trùng khi timeout hoặc partial failure.
8. Phân biệt unit test không mạng, SMTP integration test và provider delivery/E2E test; không dùng một kết quả `send()` thành công để tuyên bố email đã tới Inbox.

Khi thiết kế đúng vòng đời bean và đối tượng MIME, cấu hình kết nối tập trung, kiểm soát concurrency và đo lường từng tầng, Spring Framework Mail có thể xử lý email ổn định và dễ mở rộng hơn mà không phải đánh đổi an toàn, khả năng truy nguyên hoặc tính đúng đắn của quá trình gửi.
