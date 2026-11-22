# Tách cấu hình khỏi mã nguồn và quản lý secret

Trong một module gửi email bằng **Spring Framework Mail**, code ứng dụng cần biết *khi nào gửi thư, gửi cho ai và nội dung gì*. Thông tin như **SMTP host, port, tên tài khoản, mật khẩu, chính sách TLS và địa chỉ gửi mặc định** thuộc về cấu hình vận hành. Chúng thay đổi theo môi trường và nhà cung cấp email, vì vậy không nên được viết cố định trong các lớp service.

Một cấu hình có thể cần được bảo vệ như **secret** (ví dụ mật khẩu SMTP, API token, OAuth client secret); những cấu hình còn lại không nhất thiết bí mật nhưng vẫn nên tách khỏi mã nguồn (host, port, timeout, email `From`, chế độ TLS). Việc tách đúng giúp cùng một bản build chạy ở local, test, staging và production mà không phải sửa Java hay commit lại dự án mỗi lần đổi nhà cung cấp.

Ví dụ **không nên làm**:

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("smtp.production.example");
sender.setPort(587);
sender.setUsername("notification@company.example");
sender.setPassword("real-password-in-source"); // Không bao giờ lưu secret trong code.
~~~

Nếu mã nguồn được lưu trong Git, đưa lên CI, gửi để review hoặc đóng gói JAR, mật khẩu có thể đi theo nhiều bản sao mà người phát triển khó kiểm soát. Ngay cả khi xóa dòng code về sau, giá trị cũ vẫn có thể tồn tại trong lịch sử commit, log hoặc bản build.

Hướng tiếp cận phù hợp là **code chỉ phụ thuộc vào một mail sender đã được cấu hình**, còn môi trường triển khai cung cấp giá trị cấu hình và secret lúc chạy.

## 1. Phân biệt cấu hình thông thường và secret

| Thông tin | Có cần tách khỏi code? | Có phải secret? | Ví dụ |
| --- | --- | --- | --- |
| SMTP host | Có | Thường không | `smtp.provider.example` |
| SMTP port | Có | Không | `587` hoặc `465` |
| Bật SMTP AUTH | Có | Không | `true` |
| Chế độ STARTTLS/SSL | Có | Không | Bật STARTTLS trên cổng phù hợp |
| Timeout kết nối/đọc/ghi | Có | Không | `5000` ms |
| SMTP username | Có | Có thể nhạy cảm, tùy tổ chức | Tài khoản gửi thư |
| SMTP password / application password | Có | **Có** | Mật khẩu do provider cấp |
| SMTP API token / OAuth client secret | Có | **Có** | Token hoặc client secret |
| OAuth refresh token | Có | **Có** | Token có thể xin access token mới |
| Email `From` và `Reply-To` | Có | Thường không | `no-reply@company.example` |
| Giới hạn số thư/phút | Có | Không | Rate limit của provider |

Tách cấu hình không có nghĩa **tất cả giá trị phải nằm trong secret manager**. Có thể lưu host, port và timeout trong file cấu hình được version control, trong khi mật khẩu chỉ được cấp bởi môi trường chạy hoặc kho bí mật.

Thông tin như username có thể không phải secret tuyệt đối, nhưng việc giới hạn nơi lưu và hiển thị vẫn hữu ích. Tên tài khoản, địa chỉ gửi và ID hệ thống không nên bị log tràn lan nếu chúng làm lộ thông tin hạ tầng.

## 2. Dòng chảy cấu hình của một Spring Mail module

~~~mermaid
flowchart TD
    A["Java service: yêu cầu gửi email"] --> B["JavaMailSender (inject bởi Spring)"]
    C["application.yml: host, port, TLS, timeout"] --> D["Spring Environment / Configuration Binding"]
    E["Environment variables / secret store"] --> D
    D --> F["Mail sender configuration"]
    F --> B
    B --> G["SMTP server"]
~~~

Trong Spring Boot, dependency `spring-boot-starter-mail` đưa các thành phần mail cần thiết vào ứng dụng. Boot có thể tự cấu hình `JavaMailSender` dựa trên `spring.mail.*` khi thỏa điều kiện auto-configuration. Application service chỉ inject `JavaMailSender`, không cần biết mật khẩu lấy từ đâu.

Với **Spring Framework thuần**, cùng nguyên tắc vẫn áp dụng: tự tạo bean `JavaMailSenderImpl` và bind giá trị từ một nguồn cấu hình bên ngoài. Điểm cốt lõi là **không đặt secret trong Java source**, bất kể dùng auto-configuration hay cấu hình thủ công.

## 3. Cấu hình sender trong Spring Boot

### 3.1. Dependency

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Nếu ứng dụng cần tự validate các class cấu hình bằng Bean Validation thì bổ sung dependency validation thích hợp. Riêng ví dụ sender dưới đây không bắt buộc tạo class cấu hình tùy biến.

### 3.2. `application.yml` chỉ định tên biến thay cho mật khẩu

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    protocol: smtp
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM:no-reply@company.example}
    reply-to: ${MAIL_REPLY_TO:support@company.example}
~~~

Các biểu thức `${...}` là **Spring property placeholders**. Dấu hai chấm trong `${SMTP_PORT:587}` biểu thị giá trị mặc định `587` khi không có cấu hình khác. Riêng `${SMTP_PASSWORD}` **không có giá trị mặc định**: môi trường chạy phải cung cấp nó, giúp tránh vô tình dùng mật khẩu giả hoặc mật khẩu chung.

Ở đây:

- `spring.mail.host`, `port`, `username`, `password`: dùng để cấu hình sender.
- Các khóa `mail.smtp.*` bên trong `spring.mail.properties` là thuộc tính của SMTP transport; cú pháp dạng `"[mail.smtp.auth]"` giữ nguyên tên property có dấu chấm.
- `spring.mail.default-encoding` giúp dựng email có nội dung tiếng Việt/Unicode theo charset phù hợp.
- `app.mail.from` và `app.mail.reply-to` là **thuộc tính do ứng dụng tự định nghĩa**. Spring Boot không tự thêm các header này vào mọi email; application service phải lấy và sử dụng chúng.

Ví dụ bật **STARTTLS** trên cổng thường dùng `587`. Cấu hình TLS phải theo yêu cầu provider. Với SMTP qua TLS ngay từ đầu (SMTPS, cổng thường gặp `465`), có thể phải dùng `mail.smtp.ssl.enable` thay cho chế độ STARTTLS; không giả định hai cấu hình tương đương nhau.

Ba timeout `mail.smtp.connectiontimeout`, `mail.smtp.timeout` và `mail.smtp.writetimeout` giới hạn thời gian chờ trong các pha kết nối, đọc và ghi. Chọn giá trị theo yêu cầu hệ thống; không để mặc định thời gian chờ vô hạn khi luồng HTTP/worker có giới hạn tài nguyên.

### 3.3. Biến môi trường được cấp thế nào?

Những tên như sau có thể được hệ điều hành, container runtime, CI/CD hoặc nền tảng triển khai đưa vào process khi ứng dụng khởi chạy:

~~~text
SMTP_HOST=smtp.provider.example
SMTP_PORT=587
SMTP_USERNAME=<smtp-account>
SMTP_PASSWORD=<value-supplied-by-secret-store>
MAIL_FROM=no-reply@company.example
MAIL_REPLY_TO=support@company.example
~~~

Đây là **sơ đồ tên biến và placeholder**, không phải file chứa credentials thật. Giá trị thực của `SMTP_PASSWORD` cần được cung cấp bằng cơ chế secret của môi trường chạy. Không commit file lưu các giá trị thực vào Git.

Spring Boot cũng hỗ trợ cơ chế **relaxed binding** để ánh xạ biến môi trường như `SPRING_MAIL_HOST`, `SPRING_MAIL_USERNAME`, `SPRING_MAIL_PASSWORD` sang `spring.mail.host`, `spring.mail.username` và `spring.mail.password`. Khi dùng cách này, có thể không cần đặt placeholder `${SMTP_...}` cho mọi thuộc tính. Hãy chọn một quy ước nhất quán để tránh biến môi trường và file cấu hình ghi đè nhau theo cách khó nhận biết.

Ví dụ chạy local với PowerShell, chỉ thiết lập các giá trị *không nhạy cảm*:

~~~powershell
$env:SMTP_HOST = "localhost"
$env:SMTP_PORT = "1025"
$env:MAIL_FROM = "test@example.invalid"
~~~

Nếu làm việc với SMTP production, đừng ghi literal mật khẩu trong lịch sử PowerShell, shell script, lệnh chạy CI hay ảnh chụp màn hình. Hãy để secret manager hoặc nền tảng triển khai cấp giá trị vào môi trường. Biến môi trường giúp tránh lưu secret trong source, nhưng không phải lớp bảo mật tuyệt đối: chúng vẫn có thể lộ qua process inspection, crash dump, debug log hoặc công cụ có quyền trên máy chủ.

### 3.4. Application service không cần biết mật khẩu

~~~java
package com.example.mail.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {
    private final JavaMailSender sender;
    private final String fromAddress;
    private final String replyToAddress;

    public NotificationMailService(
            JavaMailSender sender,
            @Value("${app.mail.from}") String fromAddress,
            @Value("${app.mail.reply-to}") String replyToAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
        this.replyToAddress = replyToAddress;
    }

    public void sendText(String recipient, String subject, String text) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setReplyTo(replyToAddress);
        message.setTo(recipient);
        message.setSubject(subject);
        message.setText(text);
        sender.send(message);
    }
}
~~~

Service chỉ giữ địa chỉ `From` và `Reply-To` để tạo message; **không giữ password, không tự mở SMTP connection và không tự quyết định cơ chế TLS**. Thay SMTP provider có thể chỉ cần thay cấu hình, miễn provider mới vẫn hỗ trợ SMTP và các yêu cầu xác thực tương ứng.

Trong sản phẩm thật, địa chỉ người nhận phải được kiểm soát theo nghiệp vụ; không biến method gửi email thành endpoint công khai cho bất kỳ ai đặt địa chỉ và nội dung tùy ý.

## 4. Phân tách cấu hình theo môi trường

Giả sử cùng một module chạy ở **local**, **test**, **staging** và **production**:

| Môi trường | Nguồn SMTP | Secret | Mục tiêu |
| --- | --- | --- | --- |
| Local | SMTP test server như Mailpit/GreenMail | Thường không cần credentials khi test server được cấu hình không AUTH | Xem email thử mà không phát ra Internet |
| Unit test | Mock/fake `JavaMailSender` | Không cần secret thật | Xác nhận nội dung và lời gọi gửi |
| Staging | Sandbox SMTP/provider có hạn chế người nhận | Secret của riêng staging | Kiểm tra tích hợp mà không gửi khách hàng thật |
| Production | SMTP provider thật | Secret riêng của production | Gửi email giao dịch thật, có log/giám sát và giới hạn |

**Không nên dùng cùng một credential cho staging và production.** Nếu tài khoản staging lộ, phạm vi ảnh hưởng phải được cô lập. Cũng không nên cho local developer vô tình sử dụng SMTP production chỉ vì biến môi trường production có sẵn trong máy.

### 4.1. Profile cho local dùng SMTP giả lập

Một ví dụ `application-local.yml` có thể commit vào Git nếu không chứa secret:

~~~yaml
spring:
  mail:
    host: localhost
    port: 1025
    username:
    password:
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
      "[mail.smtp.starttls.required]": false

app:
  mail:
    from: dev@example.invalid
    reply-to: dev-support@example.invalid
~~~

Máy chủ test phải được cấu hình tương ứng: ví dụ SMTP listener ở `localhost:1025` không yêu cầu AUTH/TLS. Cấu hình này **chỉ dùng cho môi trường phát triển có kiểm soát**, không đưa nguyên chế độ kết nối không mã hóa vào production.

Khi kích hoạt profile `local`, Spring Boot lấy các giá trị phù hợp theo cơ chế hợp nhất cấu hình. Có thể chạy với:

~~~text
--spring.profiles.active=local
~~~

hoặc để môi trường triển khai đặt `SPRING_PROFILES_ACTIVE=local`.

**Profile không phải kho bảo vệ secret.** Không commit `application-prod.yml` chứa mật khẩu thật chỉ vì file có chữ “prod”. Nên commit các cấu hình không nhạy cảm trong các profile; giá trị bí mật vẫn lấy từ secret store hoặc môi trường chạy.

### 4.2. Hiểu precedence để tránh cấu hình ngoài ý muốn

Spring Boot có nhiều nguồn cấu hình: file cấu hình, profile-specific configuration, biến môi trường, system properties, command-line arguments và cấu hình được import. Tùy loại nguồn, giá trị có thể ghi đè lên nhau.

Ví dụ, nếu file `application.yml` đặt `spring.mail.host` là `smtp-staging.example` nhưng runtime được cung cấp `SPRING_MAIL_HOST=smtp-prod.example`, host thực tế có thể là production SMTP dù ứng dụng đang chạy với profile staging.

Vì thế, khi cấu hình sai, cần:

1. Xác định **giá trị hiệu lực** và **nguồn cấu hình** trong môi trường chạy.
2. Kiểm tra biến môi trường, command-line arguments và những config import đang được bật.
3. Không log toàn bộ Spring `Environment` hoặc endpoint cấu hình khi có thể chứa secret.
4. Giới hạn quyền thay đổi cấu hình runtime và kiểm soát chặt pipeline triển khai.

Các endpoint quản trị như Spring Boot Actuator `/env` hoặc `/configprops` có thể hỗ trợ kiểm tra nguồn thuộc tính khi được cấu hình an toàn, nhưng phải được bảo vệ truy cập và xử lý/sanitize giá trị nhạy cảm. Không công khai các endpoint đó chỉ để debug SMTP.

## 5. Quản lý secret đúng vòng đời

Tách mật khẩu khỏi code là bước đầu tiên; **quản lý secret** còn gồm cấp phát, phân phối, hạn chế truy cập, thay đổi định kỳ hoặc khi cần và thu hồi.

~~~mermaid
flowchart LR
    A["SMTP provider cấp credential"] --> B["Secret manager / kho bí mật"]
    B -->|"Quyền truy cập tối thiểu"| C["Runtime của ứng dụng"]
    C --> D["JavaMailSender"]
    D --> E["SMTP provider"]
    B --> F["Audit / rotation / revoke"]
~~~

### 5.1. Nơi lưu secret

Các lựa chọn thường gặp:

- **Secret manager chuyên dụng:** ví dụ AWS Secrets Manager, Azure Key Vault, Google Cloud Secret Manager hoặc HashiCorp Vault. Thường hỗ trợ phân quyền, audit và phiên bản secret.
- **Secret của nền tảng triển khai:** ví dụ secret/credential của container orchestrator, hosting platform hoặc CI/CD. Cần kiểm tra cơ chế bảo vệ tại chỗ và quyền đọc.
- **Môi trường local:** một secret store của hệ điều hành, công cụ phát triển hoặc file cấu hình cục bộ **không được commit** với quyền truy cập phù hợp.

Không phải mọi loại secret store đều tự làm ứng dụng cập nhật credential khi nó thay đổi. Cách runtime nhận giá trị (environment variable, file mount, API đọc secret, sidecar/agent) phải được quyết định rõ.

### 5.2. Cấp quyền tối thiểu

Tài khoản ứng dụng chỉ nên có quyền **đọc đúng secret cần dùng**. Tài khoản developer, CI và production nên có danh tính truy cập khác nhau. Nếu SMTP provider hỗ trợ, credential nên chỉ có quyền **gửi thư** cho những domain hoặc địa chỉ đã được cấp phép, thay vì quyền quản trị toàn bộ tài khoản email.

Một số nguyên tắc hữu ích:

- Tách secret theo **ứng dụng**, **môi trường** và **quyền sử dụng**.
- Không dùng mật khẩu cá nhân để cấp cho mail sender khi provider có ứng dụng/tài khoản kỹ thuật riêng.
- Không đưa secret vào issue, pull request, screenshot, tài liệu hướng dẫn hoặc message gửi nhóm.
- Kiểm tra ai có quyền xem, sửa và thu hồi secret; ghi nhận hoạt động truy cập khi có tính năng audit.

### 5.3. Secret trong environment variable: tiện nhưng có giới hạn

Biến môi trường thường tiện cho container và CI vì ứng dụng Spring đọc được mà không phải tạo API riêng. Tuy vậy, secret có thể bị lộ qua:

- công cụ liệt kê process hoặc container với quyền phù hợp;
- bản chụp bộ nhớ, crash dump hoặc báo lỗi debug;
- pipeline in ra tất cả biến môi trường;
- phần mềm giám sát thu thập command-line hay cấu hình quá mức;
- nhân viên có quyền xem cấu hình runtime/container.

Vì vậy, không coi việc “đã chuyển mật khẩu sang environment variable” là hoàn thành toàn bộ bảo mật. Vẫn cần giới hạn quyền truy cập, ngăn log bí mật và thiết kế quy trình rotation.

## 6. Đọc secret từ file được mount bằng Config Tree

Thay vì đưa mật khẩu vào biến môi trường, một số nền tảng cấp secret dưới dạng **file** được mount vào container. Spring Boot có cơ chế **Config Tree** để đọc các tệp theo tên thuộc tính.

Ví dụ môi trường cung cấp:

~~~text
/run/secrets/
  spring.mail.password
~~~

Nội dung tệp `spring.mail.password` là mật khẩu SMTP thật do secret store phân phối. Tệp này **không có trong Git** và chỉ được mount ở runtime với quyền đọc thích hợp.

Trong một cấu hình triển khai sử dụng file secrets:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    protocol: smtp
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
~~~

Ở biến thể này, **không khai báo lại `spring.mail.password: ${SMTP_PASSWORD}`** trong cùng file: secret được cung cấp qua config tree dưới tên property `spring.mail.password`. Thực tế cần cấu hình precedence và volume mount theo nền tảng; nên chọn rõ một nguồn chính cho mỗi secret để giảm nhầm lẫn.

Nếu thêm tiền tố `optional:` vào vị trí import, ứng dụng có thể bỏ qua khi thư mục không tồn tại. Với production, thường nên **fail fast** khi thiếu nguồn secret bắt buộc thay vì khởi chạy với kết nối mail vô hiệu; việc fail fast còn cần được kiểm chứng theo hành vi cấu hình và yêu cầu ứng dụng.

Khi file thay đổi, `JavaMailSender` đang tồn tại **không mặc nhiên tự đọc lại credential**. Cần xem khả năng refresh cấu hình của môi trường, hoặc triển khai cơ chế restart/rolling restart an toàn.

### 6.1. Kubernetes Secret và lưu ý bảo vệ

Kubernetes có đối tượng `Secret` có thể được đưa vào Pod dưới dạng biến môi trường hoặc volume. Tuy nhiên, nội dung lưu bằng biểu diễn Base64 trong manifest **không đồng nghĩa được mã hóa an toàn**. Khi sử dụng Kubernetes cần cấu hình RBAC, bảo vệ kho lưu trữ của control plane, bật encryption at rest theo khả năng của cluster và hạn chế ai có quyền đọc Secret hoặc debug Pod.

Không commit manifest chứa giá trị secret thực tế dù đã Base64. Để quản lý trên GitOps, nên sử dụng cơ chế tham chiếu secret store hoặc giải pháp mã hóa được tổ chức phê duyệt, với quyền truy cập và quy trình giải mã rõ ràng.

### 6.2. Docker Compose secret và file mount

Một cấu hình container có thể mount secret vào `/run/secrets/...` rồi để Spring Boot đọc như ví dụ. Nếu sử dụng file secret từ máy host trong môi trường phát triển, file gốc phải nằm ngoài vùng commit và được quản lý quyền truy cập. Không đưa mật khẩu thẳng vào `environment:` trong file Compose mà cả nhóm chia sẻ công khai.

Trong mọi trường hợp, secret được cấp vào process vẫn cần được bảo vệ trên host/container; mount file không tự bảo đảm rằng process khác cùng quyền không thể đọc được.

## 7. Nếu không dùng Spring Boot: cấu hình `JavaMailSenderImpl`

Ứng dụng Spring Framework thuần có thể khai báo bean một cách tường minh. Ví dụ dưới đây minh họa việc đọc các thuộc tính của Spring `Environment`, thay vì gắn trực tiếp mật khẩu trong lớp:

~~~java
package com.example.mail.config;

import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class SmtpConfiguration {

    @Bean
    public JavaMailSender javaMailSender(Environment env) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(env.getRequiredProperty("mail.smtp.host"));
        sender.setPort(
                env.getRequiredProperty("mail.smtp.port", Integer.class));
        sender.setUsername(env.getRequiredProperty("mail.smtp.username"));
        sender.setPassword(env.getRequiredProperty("mail.smtp.password"));
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");
        return sender;
    }
}
~~~

Ví dụ này yêu cầu các thuộc tính `mail.smtp.host`, `mail.smtp.port`, `mail.smtp.username` và `mail.smtp.password` đã được cung cấp vào `Environment` trước khi bean tạo. Khi thuộc tính bắt buộc thiếu, `getRequiredProperty` giúp phát hiện cấu hình lỗi.

**Nếu ứng dụng đã dùng Spring Boot mail auto-configuration**, thường không cần tạo thêm bean này. Tự khai báo bean sender có thể khiến Boot không tạo bean mặc định theo cách bạn mong đợi. Chỉ dùng cấu hình thủ công khi thật sự cần kiểm soát cách khởi tạo.

## 8. Không nhầm bảo vệ secret với bảo vệ kết nối SMTP

Ngay cả khi password được lưu trong secret manager, nếu ứng dụng gửi credentials qua kết nối không được mã hóa phù hợp thì chúng vẫn có thể bị lộ khi truyền.

Với SMTP qua cổng `587`, quy trình thường có `EHLO`, `STARTTLS` và sau đó SMTP AUTH trên kết nối TLS. Có thể bật:

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
~~~

Ý nghĩa: cho phép STARTTLS và yêu cầu nâng cấp thành công trước khi tiếp tục gửi theo cấu hình này. Nếu SMTP server không hỗ trợ STARTTLS, kết nối phải thất bại theo yêu cầu bảo mật thay vì âm thầm tiếp tục không mã hóa.

Với implicit TLS trên cổng `465`, cấu hình theo hướng dẫn provider thường sử dụng:

~~~yaml
spring:
  mail:
    port: 465
    properties:
      "[mail.smtp.ssl.enable]": true
~~~

Không tự đặt `mail.smtp.ssl.trust=*` để “sửa nhanh” lỗi chứng chỉ hoặc tắt kiểm tra danh tính TLS trong production. Khi có lỗi certificate, hãy khắc phục cấu hình truststore, hostname hoặc chứng chỉ của server.

Các lớp bảo vệ khác nhau:

| Lớp | Bảo vệ điều gì? |
| --- | --- |
| Secret store và phân quyền | Bảo vệ credential lúc lưu trữ, quản lý và cấp phát |
| TLS giữa ứng dụng và SMTP provider | Bảo vệ dữ liệu và thông tin xác thực trên chặng kết nối đó |
| SPF, DKIM, DMARC | Hỗ trợ xác thực/đánh giá tính hợp lệ của nguồn gửi và chống giả mạo domain |
| Bảo vệ log, metrics, tracing | Ngăn ứng dụng vô tình công bố dữ liệu nhạy cảm |

TLS trên một chặng SMTP không đồng nghĩa email được mã hóa đầu cuối; email có thể đi qua nhiều máy chủ và được lưu ở các hộp thư khác nhau. Nếu nghiệp vụ yêu cầu bí mật nội dung, cần đánh giá cơ chế bảo mật nội dung riêng.

## 9. Xoay vòng và thu hồi SMTP credential

Một mật khẩu hoặc token có thể phải đổi vì chính sách định kỳ, nghi ngờ lộ lọt, thay nhà cung cấp hoặc giới hạn quyền.

### 9.1. Quy trình thay đổi secret có kiểm soát

1. **Cấp credential mới** từ provider với phạm vi gửi phù hợp. Nếu provider cho phép cùng tồn tại credential cũ và mới, sử dụng khoảng chuyển tiếp để tránh ngắt dịch vụ.
2. **Ghi phiên bản mới vào secret store**, không ghi giá trị vào code, ticket hoặc log triển khai.
3. **Triển khai cho ứng dụng** bằng cách cập nhật runtime secret injection rồi restart/refresh sender theo cơ chế đã thiết kế.
4. **Kiểm tra việc nộp thư** với địa chỉ test được phép, theo dõi lỗi xác thực, kết nối và queue gửi.
5. **Thu hồi credential cũ** sau khi xác nhận các instance đã chuyển sang credential mới.
6. **Ghi nhận thời điểm và phạm vi rotation** để phục vụ audit và khôi phục khi cần.

Nếu provider chỉ hỗ trợ một credential tại một thời điểm, cần lên kế hoạch chuyển đổi với thời gian gián đoạn thấp nhất có thể và cơ chế rollback phù hợp.

### 9.2. Secret được cập nhật có tự áp dụng không?

**Không nên giả định có hot reload.** Trong một ứng dụng Spring Boot thông thường, `JavaMailSenderImpl` được cấu hình lúc bean được tạo. Nếu password trên secret manager thay đổi trong khi process vẫn chạy, sender có thể vẫn giữ giá trị cũ.

Phương án thường gặp là **rolling restart** từng instance để nạp credential mới, hoặc dùng một thành phần cấu hình/credential provider có cơ chế refresh được thiết kế rõ. Nếu thư gửi qua queue, cần phối hợp trạng thái retry trong giai đoạn thay đổi để không mất yêu cầu gửi.

### 9.3. Nếu phát hiện secret đã bị commit

Xử lý theo ưu tiên:

1. **Coi credential đã bị lộ** và thu hồi/rotate ngay qua provider hoặc secret store.
2. Kiểm tra tác động: tài khoản nào, dịch vụ nào có thể đã dùng secret, có dấu hiệu gửi thư trái phép hay không.
3. Xóa giá trị khỏi các file nguồn đang theo dõi và thay bằng tham chiếu cấu hình.
4. Đánh giá phạm vi secret trong lịch sử Git, PR, CI artifacts, log và bản sao repository; xử lý lịch sử/các bản sao theo chính sách nhóm.
5. Thêm secret scanning, chính sách review và cơ chế cấp secret để tránh lặp lại.

**Chỉ xóa dòng mật khẩu rồi commit một lần nữa là chưa đủ**, vì các commit cũ vẫn tồn tại. `.gitignore` cũng không loại bỏ file đã được Git theo dõi từ trước.

## 10. Ngăn lộ secret qua log và công cụ vận hành

Không hiển thị secret bằng:

~~~java
// Không nên:
log.info("SMTP configuration password={}", smtpPassword);
log.debug("All configuration: {}", environment);
~~~

Cần lưu ý các nguồn lộ khác:

- Bật mail protocol debug (`mail.debug` / `mail.smtp.debug` tùy ngữ cảnh thư viện) có thể tạo trace với thông tin phiên làm việc. Chỉ bật tạm trong môi trường an toàn, xem xét mask/redact và tắt sau khi điều tra.
- Log exception có thể chứa host, địa chỉ email, phản hồi SMTP và thông tin nội bộ. Không sao chép nguyên log ra kênh công khai.
- Endpoint quản trị, heap dump, profiler, APM và tracing có thể truy cập dữ liệu cấu hình hoặc payload. Giới hạn quyền và retention.
- CI/CD có thể vô tình in biến môi trường khi chạy shell với verbose/xtrace hoặc echo các tham số.
- Tài liệu hướng dẫn nên dùng placeholder như `<smtp-password>`, không dùng credential đang hoạt động “cho tiện”.

Những thông tin có thể ghi nhận để vận hành:

~~~text
mail.provider=primary
mail.smtp.host=smtp.provider.example
mail.smtp.port=587
mail.tls.mode=STARTTLS_REQUIRED
mail.send.result=AUTH_FAILURE
mail.job.id=job-742
~~~

Những trường trên là ví dụ quan sát nghiệp vụ; tránh ghi giá trị `spring.mail.password`, access token hoặc toàn bộ nội dung email vào log.

### 10.1. Không để secret trong source package

Các vị trí rất dễ vô tình phát tán:

~~~text
src/main/resources/application.yml           # Không chứa secret thật.
src/main/resources/application-prod.yml      # Không chứa secret thật.
.env                                         # Có thể dùng local, nhưng không commit.
docker-compose.yml                           # Không chứa password dạng literal.
Dockerfile                                   # Không dùng ENV/ARG cho secret build.
README.md / wiki / issue                     # Chỉ đặt placeholder.
test/resources/*.yml                         # Không chép credential production.
~~~

Nếu dùng file `.env` ở local, hãy đảm bảo file nằm ngoài Git hoặc được ignore ngay từ đầu. Một số công cụ phát triển đọc `.env`, nhưng **Spring Boot mặc định không tự động coi mọi file `.env` trong thư mục dự án là nguồn cấu hình**. Cần xác định rõ ai load biến môi trường trước khi chạy ứng dụng.

Ngoài `.gitignore`, tổ chức có thể dùng secret scanning trước commit và trên repository từ xa. Quét secret là công cụ phát hiện; nó không thay thế việc thu hồi credential đã bị lộ.

## 11. Kiểm tra cấu hình khi khởi động và lúc gửi

### 11.1. Kiểm tra input cấu hình

Những câu hỏi cần xác định:

- SMTP host có được cấp và đúng môi trường không?
- Port có hợp lệ và có khớp chế độ TLS của provider không?
- Khi SMTP AUTH được yêu cầu, username và credential có tồn tại không?
- Giá trị `From` có thuộc domain đã được provider cấp quyền không?
- Timeout có phù hợp với thời gian chờ của request/worker không?
- Mọi instance đang dùng đúng phiên bản secret sau lần rotation gần nhất không?

Ứng dụng có thể áp dụng Bean Validation cho `@ConfigurationProperties` riêng của mình, hoặc dùng bước khởi động kiểm tra những điều kiện bắt buộc. Tuy vậy, **kiểm tra giá trị có mặt** không chứng minh server chấp nhận credentials: xác thực thực sự chỉ được biết khi kết nối tới SMTP provider.

### 11.2. `spring.mail.test-connection` có ý nghĩa gì?

Spring Boot có tùy chọn:

~~~yaml
spring:
  mail:
    test-connection: true
~~~

Khi được hỗ trợ và bật, ứng dụng có thể thử kết nối mail server lúc khởi động để phát hiện một số lỗi cấu hình/sẵn sàng. Điều này có thể khiến startup thất bại khi SMTP provider tạm thời không khả dụng. Một lần kiểm tra kết nối cũng **không bảo đảm email sau này sẽ được chấp nhận**, không bảo đảm quyền gửi tới mọi người nhận và không xác nhận delivery.

Cân nhắc sử dụng trong môi trường cần startup phụ thuộc trực tiếp vào khả năng kết nối SMTP; nếu hệ thống có queue/outbox và chủ động chịu được outage của provider, có thể chọn health/metrics và retry thay vì chặn mọi lần khởi động.

### 11.3. Kiểm thử local không cần production secret

Một unit test có thể mock `JavaMailSender` để xác nhận service tạo thư đúng địa chỉ, subject và text. Với integration test, dùng SMTP giả lập như Mailpit hoặc GreenMail. Không nên đưa credential production vào test pipeline chỉ để kiểm tra cách dựng `SimpleMailMessage`.

Với staging dùng sandbox SMTP, nên hạn chế người nhận hợp lệ để tránh vô tình gửi thư thật đến khách hàng khi chạy automated test.

## 12. Một thiết kế thực tế cho nhiều loại email

Giả sử ứng dụng gửi hai loại thư:

- **Thông báo tài khoản:** `From=no-reply@company.example`, `Reply-To=support@company.example`.
- **Hóa đơn:** `From=billing@company.example`, `Reply-To=billing-help@company.example`.

Cả hai có thể dùng **một `JavaMailSender`** nếu cùng đi qua một SMTP provider và một bộ credentials. Ứng dụng tự chọn header theo loại thông báo, trong khi sender lấy thông tin kết nối từ cấu hình runtime.

~~~text
AccountService / BillingService
             |
             v
NotificationMailService
  - chọn From và Reply-To
  - dựng subject và body
             |
             v
JavaMailSender (Spring-managed bean)
  - SMTP host/port
  - TLS/AUTH/timeouts
  - credential do runtime cấp
             |
             v
SMTP provider
~~~

Nếu hai loại thư phải dùng **hai provider hoặc hai tài khoản SMTP độc lập**, có thể cần hai sender bean được đặt tên/qualifier và cấu hình riêng, hoặc một adapter/provider routing chuyên trách. Khi đó, không để code nghiệp vụ đọc password hoặc tự ghép kết nối; phần hạ tầng mail phụ trách lựa chọn transport, còn service giữ ngữ nghĩa loại thông báo.

### 12.1. Quy ước nên thống nhất trong nhóm

| Quyết định | Gợi ý triển khai |
| --- | --- |
| Cái gì nằm trong Git? | Mẫu YAML và cấu hình không nhạy cảm, không có secret thật |
| Ai cấp password? | Secret manager hoặc nền tảng triển khai |
| Ứng dụng đọc thế nào? | Spring Environment / config binding / config tree theo một quy ước nhất quán |
| Ai được xem secret production? | Chỉ danh tính/runtime và nhóm được phân quyền |
| Khi credential thay đổi? | Rotation + cập nhật runtime + restart/refresh + theo dõi kết quả |
| Khi mail bị lỗi? | Log mã lỗi/trạng thái an toàn, không log password hoặc token |
| Khi test? | Mock sender hoặc SMTP giả lập, không dùng production credentials |

## 13. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Mật khẩu để trong `application-prod.yml` là an toàn vì chỉ production đọc.” | Nếu file nằm trong Git hoặc artifact có thể bị truy cập, secret vẫn lộ. |
| “Environment variable là bí mật tuyệt đối.” | Biến môi trường tránh hardcode nhưng vẫn cần kiểm soát quyền, log, process inspection và runtime. |
| “Đổi secret trên server là ứng dụng tự dùng ngay.” | Sender có thể đã được khởi tạo với giá trị cũ; cần cơ chế refresh hoặc restart. |
| “`.gitignore` bảo vệ cả file đã commit.” | Git vẫn theo dõi file đã được add/commit; phải xử lý cả credential và lịch sử có liên quan. |
| “Base64 trong Kubernetes Secret nghĩa là đã mã hóa.” | Base64 chỉ là biểu diễn dữ liệu; bảo mật phụ thuộc RBAC và cấu hình lưu trữ. |
| “Bật TLS là đủ, không cần quản lý secret.” | TLS bảo vệ kết nối; secret vẫn cần lưu trữ và phân phối an toàn. |
| “`From` là username SMTP.” | Hai giá trị có thể khác nhau; provider quyết định quyền sử dụng địa chỉ gửi. |
| “`app.mail.from` sẽ tự áp dụng cho mọi mail.” | Đây là cấu hình của ứng dụng; code phải đọc và đặt header. |
| “Gửi một email thử thành công là hoàn tất vận hành.” | Còn cần theo dõi lỗi, bounce, quota, rotation và hành vi khi provider gián đoạn. |
| “Muốn debug cứ in toàn bộ `Environment` ra log.” | Có nguy cơ lộ credentials, endpoint và nhiều thuộc tính nhạy cảm. |

## 14. Tình huống tổng hợp: thay SMTP provider không sửa code

Ban đầu ứng dụng dùng provider A. Phần Java đã có:

~~~java
private final JavaMailSender sender;

// ... khi nghiệp vụ yêu cầu:
sender.send(message);
~~~

Khi chuyển sang provider B:

1. Nhà cung cấp mới cấp `SMTP_HOST`, `SMTP_PORT`, SMTP account và secret phù hợp.
2. Nhóm vận hành lưu secret mới trong kho bí mật của production và cấp quyền đọc cho runtime.
3. Cấu hình deployment chuyển tới host/port mới; chế độ TLS/AUTH được điều chỉnh theo hướng dẫn của provider B.
4. Ứng dụng được rollout/restart để `JavaMailSender` nạp cấu hình mới.
5. Gửi email thử tới đích được phép, kiểm tra trạng thái nộp thư, theo dõi lỗi 4xx/5xx và bounce.
6. Sau khi xác nhận toàn bộ instance hoạt động ổn định, thu hồi credential không còn dùng của provider A.

Trong toàn bộ quá trình, các service tạo `SimpleMailMessage` hoặc `MimeMessage` không cần biết SMTP password, không phải build lại vì thay hostname và không cần sửa nội dung nghiệp vụ.

Đó là lợi ích trực tiếp của việc **tách cấu hình sender khỏi mã nguồn**: hệ thống thay đổi điều kiện triển khai và credential một cách có kiểm soát trong khi trách nhiệm của code vẫn rõ ràng. Kết hợp Spring configuration binding, phân quyền secret, TLS, quy trình rotation và giám sát sẽ giúp chức năng gửi mail vừa dễ vận hành vừa giảm nguy cơ lộ thông tin xác thực.

### Tài liệu để tra cứu

- **Spring Boot Reference — Sending Email:** `spring-boot-starter-mail`, `spring.mail.*` và `spring.mail.test-connection`.
- **Spring Boot Reference — Externalized Configuration:** property sources, profile-specific files, environment variables và precedence.
- **Spring Boot Reference — Config Trees:** đọc thuộc tính từ file secret được mount.
- **Spring Framework Reference — Email:** `MailSender`, `JavaMailSender`, `JavaMailSenderImpl` và `MimeMessageHelper`.
- **Jakarta Mail SMTP Provider Properties:** các thuộc tính `mail.smtp.auth`, `mail.smtp.starttls.enable`, `mail.smtp.ssl.enable` và timeout.
